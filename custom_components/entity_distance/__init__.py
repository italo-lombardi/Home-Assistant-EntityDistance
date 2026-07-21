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

from .const import (
    BUCKET_FAR,
    BUCKET_MID,
    BUCKET_NEAR,
    BUCKET_VERY_NEAR,
    CONF_ENTITIES,
    CONF_PROXIMITY_ZONE,
    DOMAIN,
)
from .coordinator import EntityDistanceCoordinator
from .models import pair_key

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.BUTTON]

CARD_FILENAME = "entity-distance-pair-card.js"
CARD_URL = f"/{DOMAIN}/{CARD_FILENAME}"
PEOPLE_CARD_FILENAME = "entity-distance-avatar-card.js"
PEOPLE_CARD_URL = f"/{DOMAIN}/{PEOPLE_CARD_FILENAME}"
GROUP_CARD_FILENAME = "entity-distance-group-card.js"
GROUP_CARD_URL = f"/{DOMAIN}/{GROUP_CARD_FILENAME}"
_CARD_INSTALLED_KEY = "_card_installed"


def _get_version() -> str:
    manifest = Path(__file__).parent / "manifest.json"
    with manifest.open() as f:
        return json.load(f).get("version", "0.0.0")


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate config entry to current VERSION."""
    if entry.version == 1:
        # v1 → v2: convert entity_a/entity_b pair keys to CONF_ENTITIES list.
        # Falls through to the v2 → v3 block below — chained migration, intentional.
        new_data = dict(entry.data)
        if CONF_ENTITIES not in new_data:
            entity_a = new_data.get("entity_a")
            entity_b = new_data.get("entity_b")
            if entity_a and entity_b:
                new_data[CONF_ENTITIES] = [entity_a, entity_b]
            else:
                _LOGGER.error(
                    "entity_distance: cannot migrate entry %s — no entity data found",
                    entry.entry_id,
                )
                hass.config_entries.async_update_entry(entry, version=2, minor_version=1)
                return False

        entities = new_data[CONF_ENTITIES]
        if len(entities) < 2:
            _LOGGER.error(
                "entity_distance: cannot migrate entry %s — fewer than 2 entities",
                entry.entry_id,
            )
            hass.config_entries.async_update_entry(entry, version=2, minor_version=1)
            return False

        k = pair_key(entities[0], entities[1])
        pair_prefix = f"{k[0]}__{k[1]}_"
        entry_id_prefix = f"{entry.entry_id}_"

        def _migrate_unique_id(entity_entry: er.RegistryEntry) -> dict | None:
            uid = entity_entry.unique_id
            if not uid.startswith(entry_id_prefix):
                return None
            suffix = uid[len(entry_id_prefix) :]
            if "__" in suffix and "." in suffix.split("__")[0]:
                return None
            return {"new_unique_id": f"{entry_id_prefix}{pair_prefix}{suffix}"}

        await er.async_migrate_entries(hass, entry.entry_id, _migrate_unique_id)
        hass.config_entries.async_update_entry(entry, data=new_data, version=2, minor_version=1)
        _LOGGER.info(
            "entity_distance: migrated entry %s from VERSION 1 to VERSION 2",
            entry.entry_id,
        )

    if entry.version == 2:
        # VERSION 2 → 3: replace entry/exit thresholds with proximity_zone enum.
        merged = {**entry.data, **entry.options}
        # 200 was DEFAULT_ENTRY_THRESHOLD_M in v2 — missing key correctly falls back to old default.
        entry_m = merged.get("entry_threshold_m", 200)
        vn = merged.get("zone_very_near_m", 100)
        n = merged.get("zone_near_m", 500)
        m = merged.get("zone_mid_m", 2000)
        f = merged.get("zone_far_m", 10000)
        zones = [
            (BUCKET_VERY_NEAR, vn),
            (BUCKET_NEAR, n),
            (BUCKET_MID, m),
            (BUCKET_FAR, f),
        ]
        proximity_zone = min(zones, key=lambda z: abs(z[1] - entry_m))[0]
        new_options = {
            k: v
            for k, v in entry.options.items()
            if k not in ("entry_threshold_m", "exit_threshold_m")
        }
        new_options[CONF_PROXIMITY_ZONE] = proximity_zone
        # Also strip from data if they ended up there (v1→v2 path stored in data)
        new_data = {
            k: v
            for k, v in entry.data.items()
            if k not in ("entry_threshold_m", "exit_threshold_m")
        }
        hass.config_entries.async_update_entry(
            entry, data=new_data, options=new_options, version=3, minor_version=1
        )
        _LOGGER.info(
            "entity_distance: migrated entry %s from VERSION 2 to VERSION 3 — proximity_zone=%s",
            entry.entry_id,
            proximity_zone,
        )

    if entry.version > 3:
        _LOGGER.error(
            "entity_distance: entry %s has unknown version %s — cannot migrate",
            entry.entry_id,
            entry.version,
        )
        return False

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})

    _LOGGER.debug(
        "entity_distance: setting up entry %s — entities=%s",
        entry.entry_id,
        entry.data.get(CONF_ENTITIES, []),
    )

    coordinator = EntityDistanceCoordinator(hass, entry)
    try:
        await coordinator.async_setup()
        await coordinator.async_recalculate()
    except Exception:
        coordinator.async_unload()
        raise

    hass.data[DOMAIN][entry.entry_id] = coordinator

    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except Exception:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        coordinator.async_unload()
        raise

    entry.async_on_unload(entry.add_update_listener(_async_update_options))

    await _async_install_card(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: EntityDistanceCoordinator = hass.data[DOMAIN].pop(entry.entry_id, None)
        if coordinator:
            coordinator.async_unload()
        # Clear the card-installed flag when the last entry unloads so resources
        # are re-registered on next setup (handles reload and version upgrades).
        remaining = [k for k in hass.data[DOMAIN] if k != _CARD_INSTALLED_KEY]
        if not remaining:
            hass.data[DOMAIN].pop(_CARD_INSTALLED_KEY, None)

    return unload_ok


async def _async_update_options(hass: HomeAssistant, entry: ConfigEntry) -> None:
    _LOGGER.debug("entity_distance: options updated — reloading entry %s", entry.entry_id)
    await hass.config_entries.async_reload(entry.entry_id)


KNOWN_FILENAMES = {CARD_FILENAME, PEOPLE_CARD_FILENAME, GROUP_CARD_FILENAME}


async def _async_purge_stale_resources(hass: HomeAssistant) -> None:
    """Remove Lovelace resources for old/renamed entity_distance card filenames."""
    try:
        resources = hass.data["lovelace"].resources
    except (KeyError, AttributeError):
        return
    if not resources.loaded:
        await resources.async_load()
    if not isinstance(resources, ResourceStorageCollection):
        return
    for r in list(resources.async_items()):
        url = r.get("url", "")
        if f"/{DOMAIN}/" in url and not any(f in url for f in KNOWN_FILENAMES):
            await resources.async_delete_item(r["id"])
            _LOGGER.info("entity_distance: removed stale Lovelace resource %s", url)


async def _async_install_card(hass: HomeAssistant) -> None:
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(_CARD_INSTALLED_KEY):
        return

    version = await hass.async_add_executor_job(_get_version)

    await _async_purge_stale_resources(hass)

    for filename, url in [
        (CARD_FILENAME, CARD_URL),
        (PEOPLE_CARD_FILENAME, PEOPLE_CARD_URL),
        (GROUP_CARD_FILENAME, GROUP_CARD_URL),
    ]:
        source = Path(__file__).parent / "frontend" / filename
        exists = await hass.async_add_executor_job(source.exists)
        if not exists:
            _LOGGER.warning("entity_distance: card JS not found at %s", source)
            continue
        try:
            await hass.http.async_register_static_paths([StaticPathConfig(url, str(source), True)])
        except RuntimeError as err:
            _LOGGER.debug("entity_distance: static path %s already registered (%s)", url, err)
        await _async_register_lovelace_resource(hass, filename, url, version)

    domain_data[_CARD_INSTALLED_KEY] = True


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
    if first.get("url") != resource_url:
        if isinstance(resources, ResourceStorageCollection):
            await resources.async_update_item(
                first["id"], {"res_type": "module", "url": resource_url}
            )
            _LOGGER.info("entity_distance: updated Lovelace resource to %s", resource_url)
        else:
            first["url"] = resource_url
