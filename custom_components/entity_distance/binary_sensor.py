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

from .const import DOMAIN
from .coordinator import EntityDistanceCoordinator
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
        sensors.append(ProximityBinarySensor(coordinator, entry, pair_dev, k, a_name, b_name))

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
        return self.coordinator.data.pairs[self._pair_key]

    @property
    def is_on(self) -> bool | None:
        if not self._pair.data_valid:
            return None
        return self._pair.proximity


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
        return self.coordinator.data.all_in_proximity
