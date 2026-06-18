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

from .const import BUCKETS, DOMAIN
from .coordinator import EntityDistanceCoordinator, calc_bucket
from .models import PairState, pair_key

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EntityDistanceCoordinator = hass.data[DOMAIN][entry.entry_id]

    def _friendly_name(entity_id: str) -> str:
        state = hass.states.get(entity_id)
        if state and state.name:
            return state.name
        return entity_id.split(".")[-1].replace("_", " ").title()

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
        if not self._pair.data_valid:
            return None
        return self._pair.proximity


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
    def is_on(self) -> bool | None:
        state_a = self.hass.states.get(self._pair_key[0])
        state_b = self.hass.states.get(self._pair_key[1])
        if state_a is None or state_b is None:
            return None
        # For zone.* entries the entity state is a count (e.g. "3"), not the
        # zone name. Use the entity's object_id so a person whose state is
        # "home" matches zone.home.
        zone_a = (
            self._pair_key[0].split(".", 1)[1]
            if self._pair_key[0].startswith("zone.")
            else state_a.state
        )
        zone_b = (
            self._pair_key[1].split(".", 1)[1]
            if self._pair_key[1].startswith("zone.")
            else state_b.state
        )
        _unknown = {"unknown", "unavailable", "not_home"}
        if zone_a in _unknown or zone_b in _unknown:
            return None
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
        if not ps.data_valid or ps.distance_m is None:
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
        if not any(ps.data_valid for ps in pairs.values()):
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
        if not any(ps.data_valid for ps in pairs.values()):
            return None
        return self.coordinator.data.all_in_proximity
