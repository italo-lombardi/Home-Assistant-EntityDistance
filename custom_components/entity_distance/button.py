from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import EntityDistanceCoordinator

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

    entity_a_name = _friendly_name(entry.data["entity_a"])
    entity_b_name = _friendly_name(entry.data["entity_b"])

    async_add_entities([RefreshButton(coordinator, entry, entity_a_name, entity_b_name)])


class RefreshButton(CoordinatorEntity[EntityDistanceCoordinator], ButtonEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "refresh"

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        entity_a_name: str,
        entity_b_name: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_refresh"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Entity Distance — {entity_a_name} & {entity_b_name}",
            manufacturer="Entity Distance",
            entry_type=DeviceEntryType.SERVICE,
        )

    async def async_press(self) -> None:
        registry = er.async_get(self.hass)
        entity_a = self._entry.data["entity_a"]
        entity_b = self._entry.data["entity_b"]

        for entity_id in (entity_a, entity_b):
            if entity_id.startswith("zone."):
                continue
            device_id = self._resolve_device_id(registry, entity_id)
            if device_id is None:
                _LOGGER.warning(
                    "entity_distance: refresh — no device found for %s, skipping",
                    entity_id,
                )
                continue
            notify_service = self._resolve_notify_service(device_id)
            if notify_service is None:
                _LOGGER.warning(
                    "entity_distance: refresh — no notify service found for device %s (%s), skipping",
                    device_id,
                    entity_id,
                )
                continue
            try:
                await self.hass.services.async_call(
                    "notify",
                    notify_service,
                    {"message": "request_location_update"},
                    blocking=False,
                )
                _LOGGER.debug(
                    "entity_distance: location refresh requested for %s via notify.%s",
                    entity_id,
                    notify_service,
                )
            except Exception as err:
                _LOGGER.warning("entity_distance: refresh failed for %s: %s", entity_id, err)

    def _resolve_device_id(self, registry: er.EntityRegistry, entity_id: str) -> str | None:
        entry = registry.async_get(entity_id)
        if entry is not None and entry.device_id is not None:
            return entry.device_id

        # person.* entities have no device_id — resolve via active source tracker
        if entity_id.startswith("person."):
            state = self.hass.states.get(entity_id)
            source = state.attributes.get("source") if state else None
            if source:
                source_entry = registry.async_get(source)
                if source_entry is not None and source_entry.device_id is not None:
                    return source_entry.device_id

        return None

    def _resolve_notify_service(self, device_id: str) -> str | None:
        try:
            from homeassistant.components.mobile_app.util import (
                get_notify_service,
                webhook_id_from_device_id,
            )
        except ImportError:
            return None

        webhook_id = webhook_id_from_device_id(self.hass, device_id)
        if webhook_id is None:
            return None
        return get_notify_service(self.hass, webhook_id)
