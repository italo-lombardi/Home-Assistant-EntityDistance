from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.components.lovelace.resources import ResourceStorageCollection
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .coordinator import EntityDistanceCoordinator

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

CARD_FILENAME = "entity-distance-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"
_CARD_INSTALLED = False


def _get_version() -> str:
    manifest = Path(__file__).parent / "manifest.json"
    with manifest.open() as f:
        return json.load(f).get("version", "0.0.0")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    coordinator = EntityDistanceCoordinator(hass, entry)
    await coordinator.async_setup()
    await coordinator._async_recalculate()

    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    await _async_install_card(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: EntityDistanceCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.async_unload()

    return unload_ok


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_install_card(hass: HomeAssistant) -> None:
    global _CARD_INSTALLED
    if _CARD_INSTALLED:
        return

    source = Path(__file__).parent / "frontend" / CARD_FILENAME
    if not source.exists():
        _LOGGER.warning("entity_distance: card JS not found at %s", source)
        return

    version = await hass.async_add_executor_job(_get_version)

    try:
        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(source), True)])
    except Exception:  # noqa: BLE001
        _LOGGER.debug("entity_distance: static path %s already registered", CARD_URL)

    await _async_register_lovelace_resource(hass, version)
    _CARD_INSTALLED = True


async def _async_register_lovelace_resource(hass: HomeAssistant, version: str) -> None:
    resource_url = f"{CARD_URL}?automatically-added&{version}"

    try:
        resources = hass.data["lovelace"].resources
    except (KeyError, AttributeError):
        _LOGGER.info(
            "entity_distance: could not auto-register Lovelace resource. "
            "Add manually: url: %s?%s, type: module",
            CARD_URL,
            version,
        )
        return

    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True

    existing = [r for r in resources.async_items() if CARD_FILENAME in r.get("url", "")]

    if not existing:
        if getattr(resources, "async_create_item", None):
            await resources.async_create_item({"res_type": "module", "url": resource_url})
            _LOGGER.info("entity_distance: registered %s as Lovelace resource", resource_url)
        elif getattr(resources, "data", None) and getattr(resources.data, "append", None):
            resources.data.append({"type": "module", "url": resource_url})
        return

    # Remove duplicates — keep only the first, update it to current version
    for r in existing[1:]:
        if isinstance(resources, ResourceStorageCollection):
            await resources.async_delete_item(r["id"])
            _LOGGER.info("entity_distance: removed duplicate Lovelace resource %s", r["url"])

    first = existing[0]
    if first.get("url") != resource_url and isinstance(resources, ResourceStorageCollection):
        await resources.async_update_item(first["id"], {"res_type": "module", "url": resource_url})
        _LOGGER.info("entity_distance: updated Lovelace resource to %s", resource_url)
