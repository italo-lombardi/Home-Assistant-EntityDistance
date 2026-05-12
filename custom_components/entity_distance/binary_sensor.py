from __future__ import annotations

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
from .models import PairState


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

    entity_a_name = _friendly_name(entry.data["entity_a"])
    entity_b_name = _friendly_name(entry.data["entity_b"])

    async_add_entities([ProximityBinarySensor(coordinator, entry, entity_a_name, entity_b_name)])


class ProximityBinarySensor(CoordinatorEntity[EntityDistanceCoordinator], BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_device_class = BinarySensorDeviceClass.PRESENCE
    _attr_translation_key = "proximity"

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        entity_a_name: str,
        entity_b_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_proximity"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Entity Distance — {entity_a_name} & {entity_b_name}",
            manufacturer="Entity Distance",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _pair(self) -> PairState:
        return self.coordinator.data.pair

    @property
    def is_on(self) -> bool | None:
        if not self._pair.data_valid:
            return None
        return self._pair.proximity
