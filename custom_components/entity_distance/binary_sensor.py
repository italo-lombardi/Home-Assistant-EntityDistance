from __future__ import annotations

import itertools
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import BUCKETS, DEFAULT_ALTITUDE_ALIGNED_THRESHOLD_M, DOMAIN
from .coordinator import EntityDistanceCoordinator, calc_bucket
from .models import PairState, friendly_name, pair_key

_LOGGER = logging.getLogger(__name__)

_HOME_ZONE_ENTITY_ID = "zone.home"


def _show(coordinator: EntityDistanceCoordinator, ps: PairState) -> bool:
    """True when a binary sensor should reflect the pair's last-known state.

    Matches the sensor platform's grace behaviour: valid now, or lost signal
    recently enough to still be inside the display grace window (so it holds its
    last on/off instead of flapping to unknown).
    """
    return ps.data_valid or coordinator.is_within_grace(ps, dt_util.now())


def _zone_match_value(entity_id: str, state) -> str:
    """Value to compare against the other side's tracker state for same-zone matching.

    Mirrors the logic in HA's device_tracker.entity:
      - zone.home → literal "home" (STATE_HOME)
      - any other zone → State.name (friendly_name, falls back to object_id)
      - non-zone entity → its raw state
    """
    if not entity_id.startswith("zone."):
        return state.state
    if entity_id == _HOME_ZONE_ENTITY_ID:
        return "home"
    # State.name returns the configured friendly_name, or object_id if unset.
    return state.name


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EntityDistanceCoordinator = hass.data[DOMAIN][entry.entry_id]

    def _friendly_name(entity_id: str) -> str:
        return friendly_name(hass, entity_id)

    entities_list = coordinator.entities
    group_name = " & ".join(_friendly_name(e) for e in entities_list)

    _LOGGER.debug(
        "entity_distance: binary_sensor platform setup — entry=%s entities=%s",
        entry.entry_id,
        entities_list,
    )

    sensors: list = []

    for a, b in itertools.combinations(entities_list, 2):
        k = pair_key(a, b)
        a_name = _friendly_name(k[0])
        b_name = _friendly_name(k[1])
        pair_dev = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{k[0]}__{k[1]}")},
            name=f"{a_name} & {b_name}",
            manufacturer="Entity Distance",
            entry_type=DeviceEntryType.SERVICE,
            via_device=(DOMAIN, entry.entry_id),
        )
        is_zone_pair = k[0].startswith("zone.") and k[1].startswith("zone.")
        sensors.append(ProximityBinarySensor(coordinator, entry, pair_dev, k, a_name, b_name))
        sensors.append(ReliableBinarySensor(coordinator, entry, pair_dev, k))
        sensors.append(AltitudeAlignedBinarySensor(coordinator, entry, pair_dev, k))
        if not is_zone_pair:
            sensors.append(SameZoneBinarySensor(coordinator, entry, pair_dev, k))
        for bucket in BUCKETS:
            sensors.append(BucketBinarySensor(coordinator, entry, pair_dev, k, bucket))

    # Group-level: any_in_proximity (only useful for 3+ entities)
    if len(entities_list) > 2:
        group_dev = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Entity Distance — {group_name}",
            manufacturer="Entity Distance",
            entry_type=DeviceEntryType.SERVICE,
        )
        sensors.append(AnyInProximityBinarySensor(coordinator, entry, group_dev))
        sensors.append(AllInProximityBinarySensor(coordinator, entry, group_dev))

    async_add_entities(sensors)


class ProximityBinarySensor(CoordinatorEntity[EntityDistanceCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PRESENCE
    _attr_translation_key = "proximity"

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        pair_key_val: tuple[str, str],
        entity_a_name: str,
        entity_b_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._pair_key = pair_key_val
        key_str = f"{pair_key_val[0]}__{pair_key_val[1]}"
        self._attr_unique_id = f"{entry.entry_id}_{key_str}_proximity"
        self._attr_device_info = device_info

    @property
    def _pair(self) -> PairState:
        return self.coordinator.data.pairs.get(self._pair_key) or PairState(
            entity_a_id=self._pair_key[0], entity_b_id=self._pair_key[1]
        )

    @property
    def is_on(self) -> bool | None:
        ps = self._pair
        if ps.data_valid:
            return ps.proximity
        # Within grace: hold the last valid proximity value instead of the
        # _invalidate-forced False, so a blip doesn't flip in_proximity off.
        if self.coordinator.is_within_grace(ps, dt_util.now()):
            return ps.last_proximity
        return None

    @property
    def extra_state_attributes(self) -> dict:
        return {"hold_active": self.coordinator._resync_holding.get(self._pair_key, False)}


class SameZoneBinarySensor(CoordinatorEntity[EntityDistanceCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "same_zone"

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        pair_key_val: tuple[str, str],
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._pair_key = pair_key_val
        key_str = f"{pair_key_val[0]}__{pair_key_val[1]}"
        self._attr_unique_id = f"{entry.entry_id}_{key_str}_same_zone"
        self._attr_device_info = device_info

    @property
    def is_on(self) -> bool:
        # Never returns None — "same zone" is a definite yes/no. Missing
        # state, unknown/unavailable, or not_home all mean "no confirmed
        # named zone match" → False.
        state_a = self.hass.states.get(self._pair_key[0])
        state_b = self.hass.states.get(self._pair_key[1])
        if state_a is None or state_b is None:
            return False
        # A `zone.*` entity's state is a tracker count (e.g. "3"), not the
        # zone name. HA's device_tracker / person sets state to either the
        # literal "home" (for zone.home, see device_tracker/entity.py) or the
        # zone State.name — which is the configured friendly_name (or falls
        # back to object_id). Match that lookup so renamed/non-home zones
        # also resolve correctly.
        zone_a = _zone_match_value(self._pair_key[0], state_a)
        zone_b = _zone_match_value(self._pair_key[1], state_b)
        _no_zone = {"unknown", "unavailable", "not_home"}
        if zone_a in _no_zone or zone_b in _no_zone:
            return False
        return zone_a == zone_b


class BucketBinarySensor(CoordinatorEntity[EntityDistanceCoordinator], BinarySensorEntity):
    """On while the pair's current distance falls in a specific bucket."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        pair_key_val: tuple[str, str],
        bucket: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._pair_key = pair_key_val
        self._bucket = bucket
        self._attr_translation_key = f"in_{bucket}"
        key_str = f"{pair_key_val[0]}__{pair_key_val[1]}"
        self._attr_unique_id = f"{entry.entry_id}_{key_str}_in_{bucket}"
        self._attr_device_info = device_info

    @property
    def _pair(self) -> PairState:
        return self.coordinator.data.pairs.get(self._pair_key) or PairState(
            entity_a_id=self._pair_key[0], entity_b_id=self._pair_key[1]
        )

    @property
    def is_on(self) -> bool | None:
        ps = self._pair
        if not _show(self.coordinator, ps) or ps.distance_m is None:
            return None
        current = calc_bucket(ps.distance_m, self.coordinator.bucket_thresholds)
        return current == self._bucket


class AnyInProximityBinarySensor(CoordinatorEntity[EntityDistanceCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PRESENCE
    _attr_translation_key = "any_in_proximity"

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_any_in_proximity"
        self._attr_device_info = device_info

    @property
    def is_on(self) -> bool | None:
        pairs = self.coordinator.data.pairs
        if not any(_show(self.coordinator, ps) for ps in pairs.values()):
            return None
        return self.coordinator.data.any_in_proximity


class AllInProximityBinarySensor(CoordinatorEntity[EntityDistanceCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PRESENCE
    _attr_translation_key = "all_in_proximity"

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_all_in_proximity"
        self._attr_device_info = device_info

    @property
    def is_on(self) -> bool | None:
        pairs = self.coordinator.data.pairs
        if not any(_show(self.coordinator, ps) for ps in pairs.values()):
            return None
        return self.coordinator.data.all_in_proximity


class ReliableBinarySensor(CoordinatorEntity[EntityDistanceCoordinator], BinarySensorEntity):
    """On while both sides of the pair have ≥ min_updates_reliable fresh GPS fixes
    in the rolling window. Surfaces the same signal that used to ride along as the
    `reliable: bool` field in the (now-removed) bus-event payload, so automations
    can gate on data confidence via a state-change trigger."""

    _attr_has_entity_name = True
    _attr_translation_key = "reliable"

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        pair_key_val: tuple[str, str],
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._pair_key = pair_key_val
        key_str = f"{pair_key_val[0]}__{pair_key_val[1]}"
        self._attr_unique_id = f"{entry.entry_id}_{key_str}_reliable"
        self._attr_device_info = device_info

    @property
    def _pair(self) -> PairState:
        return self.coordinator.data.pairs.get(self._pair_key) or PairState(
            entity_a_id=self._pair_key[0], entity_b_id=self._pair_key[1]
        )

    @property
    def is_on(self) -> bool | None:
        ps = self._pair
        if not _show(self.coordinator, ps):
            return None
        return self.coordinator.is_reliable(ps)


class AltitudeAlignedBinarySensor(CoordinatorEntity[EntityDistanceCoordinator], BinarySensorEntity):
    """On when both entities are at the same altitude (within threshold)."""

    _attr_has_entity_name = True
    _attr_translation_key = "altitude_aligned"

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        pair_key_val: tuple[str, str],
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._pair_key = pair_key_val
        key_str = f"{pair_key_val[0]}__{pair_key_val[1]}"
        self._attr_unique_id = f"{entry.entry_id}_{key_str}_altitude_aligned"
        self._attr_device_info = device_info

    @property
    def _pair(self) -> PairState:
        return self.coordinator.data.pairs.get(self._pair_key) or PairState(
            entity_a_id=self._pair_key[0], entity_b_id=self._pair_key[1]
        )

    @property
    def is_on(self) -> bool | None:
        ps = self._pair
        if ps.altitude_delta_m is None:
            return None
        return abs(ps.altitude_delta_m) <= DEFAULT_ALTITUDE_ALIGNED_THRESHOLD_M

    @property
    def extra_state_attributes(self) -> dict:
        return {"threshold_m": DEFAULT_ALTITUDE_ALIGNED_THRESHOLD_M}
