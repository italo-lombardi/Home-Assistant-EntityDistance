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
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .const import CONF_ENTITIES, CONF_ENTITY_A, CONF_ENTITY_B, DOMAIN
from .coordinator import EntityDistanceCoordinator
from .models import pair_key

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

CARD_FILENAME = "entity-distance-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"
PEOPLE_CARD_FILENAME = "entity-distance-people-card.js"
PEOPLE_CARD_URL = f"/{DOMAIN}/{PEOPLE_CARD_FILENAME}"
_CARD_INSTALLED = False


def _get_version() -> str:
    manifest = Path(__file__).parent / "manifest.json"
    with manifest.open() as f:
        return json.load(f).get("version", "0.0.0")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry from VERSION 1 (pair) to VERSION 2 (group)."""
    if entry.version == 1:
        new_data = dict(entry.data)
        if CONF_ENTITIES not in new_data:
            if CONF_ENTITY_A in new_data and CONF_ENTITY_B in new_data:
                new_data[CONF_ENTITIES] = [new_data[CONF_ENTITY_A], new_data[CONF_ENTITY_B]]
            else:
                _LOGGER.error(
                    "entity_distance: cannot migrate entry %s — no entity data found",
                    entry.entry_id,
                )
                return False

        # Migrate entity registry unique_ids:
        # Old format: "{entry_id}_{sensor_key}"  (e.g. "abc_distance")
        # New format: "{entry_id}_{a}__{b}_{sensor_key}"  (e.g. "abc_person.alice__person.bob_distance")
        entities = new_data[CONF_ENTITIES]
        k = pair_key(entities[0], entities[1])
        pair_prefix = f"{k[0]}__{k[1]}_"
        entry_id_prefix = f"{entry.entry_id}_"

        def _migrate_unique_id(entity_entry: er.RegistryEntry) -> dict | None:
            uid = entity_entry.unique_id
            if not uid.startswith(entry_id_prefix):
                return None
            suffix = uid[len(entry_id_prefix) :]
            # Already migrated (contains __ separator with entity domain)
            if "__" in suffix and "." in suffix.split("__")[0]:
                return None
            new_uid = f"{entry_id_prefix}{pair_prefix}{suffix}"
            _LOGGER.debug(
                "entity_distance: migrating unique_id %s → %s",
                uid,
                new_uid,
            )
            return {"new_unique_id": new_uid}

        await er.async_migrate_entries(hass, entry.entry_id, _migrate_unique_id)

        hass.config_entries.async_update_entry(entry, data=new_data, version=2, minor_version=1)
        _LOGGER.info(
            "entity_distance: migrated entry %s from VERSION 1 to VERSION 2",
            entry.entry_id,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    _LOGGER.debug(
        "entity_distance: setting up entry %s — entities=%s",
        entry.entry_id,
        entry.data.get(CONF_ENTITIES, [entry.data.get("entity_a"), entry.data.get("entity_b")]),
    )

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
    _LOGGER.debug("entity_distance: options updated — reloading entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_install_card(hass: HomeAssistant) -> None:
    global _CARD_INSTALLED
    if _CARD_INSTALLED:
        return

    version = await hass.async_add_executor_job(_get_version)

    for filename, url in [
        (CARD_FILENAME, CARD_URL),
        (PEOPLE_CARD_FILENAME, PEOPLE_CARD_URL),
    ]:
        source = Path(__file__).parent / "frontend" / filename
        if not source.exists():
            _LOGGER.warning("entity_distance: card JS not found at %s", source)
            continue
        try:
            await hass.http.async_register_static_paths([StaticPathConfig(url, str(source), True)])
        except Exception:  # noqa: BLE001
            _LOGGER.debug("entity_distance: static path %s already registered", url)
        await _async_register_lovelace_resource(hass, filename, url, version)

    _CARD_INSTALLED = True


async def _async_register_lovelace_resource(
    hass: HomeAssistant, filename: str, card_url: str, version: str
) -> None:
    resource_url = f"{card_url}?automatically-added&{version}"

    try:
        resources = hass.data["lovelace"].resources
    except (KeyError, AttributeError):
        _LOGGER.info(
            "entity_distance: could not auto-register Lovelace resource. "
            "Add manually: url: %s?%s, type: module",
            card_url,
            version,
        )
        return

    if not resources.loaded:
        await resources.async_load()
        resources.loaded = True

    existing = [r for r in resources.async_items() if filename in r.get("url", "")]

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
