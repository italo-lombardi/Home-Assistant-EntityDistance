"""Tests for async_setup_entry and async_unload_entry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.entity_distance.const import CONF_ENTITIES, DOMAIN


class TestCoordinatorSetupAndUnload:
    def _make_coordinator(self, entities: list[str]) -> MagicMock:
        coord = MagicMock()
        coord.entities = entities
        coord.async_setup = AsyncMock()
        coord._async_recalculate = AsyncMock()
        coord.async_recalculate = AsyncMock()
        coord.async_unload = MagicMock()
        return coord

    @pytest.mark.asyncio
    async def test_setup_entry_stores_coordinator(self):
        from custom_components.entity_distance import async_setup_entry

        hass = MagicMock()
        hass.data = {}
        hass.config_entries = MagicMock()
        hass.config_entries.async_forward_entry_setups = AsyncMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {CONF_ENTITIES: ["person.alice", "person.bob"]}
        entry.options = {}

        coordinator = self._make_coordinator(["person.alice", "person.bob"])

        with (
            patch(
                "custom_components.entity_distance.EntityDistanceCoordinator",
                return_value=coordinator,
            ),
            patch(
                "custom_components.entity_distance._async_install_card",
                new=AsyncMock(),
            ),
        ):
            await async_setup_entry(hass, entry)

        assert DOMAIN in hass.data
        assert "test_entry" in hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_unload_entry_removes_coordinator(self):
        from custom_components.entity_distance import async_unload_entry

        hass = MagicMock()
        coordinator = self._make_coordinator(["person.alice", "person.bob"])
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(hass, entry)

        assert result is True
        coordinator.async_unload.assert_called_once()
        assert "test_entry" not in hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_unload_entry_noop_when_platforms_fail(self):
        from custom_components.entity_distance import async_unload_entry

        hass = MagicMock()
        coordinator = self._make_coordinator(["person.alice", "person.bob"])
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=False)

        result = await async_unload_entry(hass, entry)

        assert result is False
        coordinator.async_unload.assert_not_called()
        assert "test_entry" in hass.data[DOMAIN]

    async def test_unload_entry_missing_coordinator(self):
        # Defensive path: entry already gone from hass.data[DOMAIN]. Unload
        # must still succeed (platforms unloaded) without calling coordinator.
        from custom_components.entity_distance import async_unload_entry

        hass = MagicMock()
        hass.data = {DOMAIN: {}}

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        result = await async_unload_entry(hass, entry)
        assert result is True


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class TestModuleHelpers:
    def test_get_version_reads_manifest(self):
        from custom_components.entity_distance import _get_version

        version = _get_version()
        assert isinstance(version, str)
        assert version.count(".") == 2

    @pytest.mark.asyncio
    async def test_async_setup_returns_true(self):
        from custom_components.entity_distance import async_setup

        hass = MagicMock()
        result = await async_setup(hass, {})
        assert result is True

    @pytest.mark.asyncio
    async def test_async_update_options_reloads_entry(self):
        from custom_components.entity_distance import _async_update_options

        hass = MagicMock()
        hass.config_entries = MagicMock()
        hass.config_entries.async_reload = AsyncMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"

        await _async_update_options(hass, entry)

        hass.config_entries.async_reload.assert_called_once_with("test_entry")


# ---------------------------------------------------------------------------
# _async_purge_stale_resources
# ---------------------------------------------------------------------------


class TestPurgeStaleResources:
    @pytest.mark.asyncio
    async def test_no_lovelace_data(self):
        from custom_components.entity_distance import _async_purge_stale_resources

        hass = MagicMock()
        hass.data = {}
        await _async_purge_stale_resources(hass)

    @pytest.mark.asyncio
    async def test_lovelace_attribute_error(self):
        from custom_components.entity_distance import _async_purge_stale_resources

        hass = MagicMock()
        lovelace = MagicMock(spec=[])
        hass.data = {"lovelace": lovelace}
        await _async_purge_stale_resources(hass)

    @pytest.mark.asyncio
    async def test_loads_resources_when_not_loaded(self):
        from custom_components.entity_distance import _async_purge_stale_resources

        hass = MagicMock()
        resources = MagicMock()
        resources.loaded = False
        resources.async_load = AsyncMock()
        resources.async_items = MagicMock(return_value=[])
        hass.data = {"lovelace": MagicMock(resources=resources)}

        await _async_purge_stale_resources(hass)

        resources.async_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_when_not_storage_collection(self):
        from custom_components.entity_distance import _async_purge_stale_resources

        hass = MagicMock()
        resources = MagicMock()
        resources.loaded = True
        resources.async_items = MagicMock(return_value=[{"id": "x", "url": "/foo"}])
        resources.async_delete_item = AsyncMock()
        hass.data = {"lovelace": MagicMock(resources=resources)}

        await _async_purge_stale_resources(hass)

        resources.async_delete_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_deletes_stale_resource(self):
        from homeassistant.components.lovelace.resources import (
            ResourceStorageCollection,
        )

        from custom_components.entity_distance import _async_purge_stale_resources

        hass = MagicMock()
        resources = MagicMock(spec=ResourceStorageCollection)
        resources.loaded = True
        resources.async_items = MagicMock(
            return_value=[
                {"id": "stale", "url": f"/{DOMAIN}/old-card.js"},
                {"id": "keep", "url": f"/{DOMAIN}/entity-distance-pair-card.js"},
                {"id": "other", "url": "/other-domain/file.js"},
            ]
        )
        resources.async_delete_item = AsyncMock()
        hass.data = {"lovelace": MagicMock(resources=resources)}

        await _async_purge_stale_resources(hass)

        resources.async_delete_item.assert_called_once_with("stale")


# ---------------------------------------------------------------------------
# _async_install_card
# ---------------------------------------------------------------------------


class TestInstallCard:
    @pytest.mark.asyncio
    async def test_returns_early_when_already_installed(self):
        from custom_components.entity_distance import _async_install_card

        hass = MagicMock()
        hass.data = {DOMAIN: {"_card_installed": True}}
        hass.async_add_executor_job = AsyncMock()

        await _async_install_card(hass)

        hass.async_add_executor_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_installs_cards_and_sets_flag(self):
        from custom_components.entity_distance import _async_install_card

        hass = MagicMock()
        hass.data = {}
        hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
        hass.http = MagicMock()
        hass.http.async_register_static_paths = AsyncMock()

        with (
            patch(
                "custom_components.entity_distance._async_purge_stale_resources",
                new=AsyncMock(),
            ),
            patch(
                "custom_components.entity_distance._async_register_lovelace_resource",
                new=AsyncMock(),
            ),
            patch("custom_components.entity_distance._get_version", return_value="0.2.5"),
            patch("custom_components.entity_distance.Path") as mock_path_cls,
        ):
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.__truediv__ = MagicMock(return_value=mock_path)
            mock_path_cls.return_value.parent = mock_path
            await _async_install_card(hass)

        assert hass.data[DOMAIN]["_card_installed"] is True

    @pytest.mark.asyncio
    async def test_skips_missing_card_file(self):
        from custom_components.entity_distance import _async_install_card

        hass = MagicMock()
        hass.data = {}
        hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
        hass.http = MagicMock()
        hass.http.async_register_static_paths = AsyncMock()

        register_resource = AsyncMock()

        with (
            patch(
                "custom_components.entity_distance._async_purge_stale_resources",
                new=AsyncMock(),
            ),
            patch(
                "custom_components.entity_distance._async_register_lovelace_resource",
                new=register_resource,
            ),
            patch("custom_components.entity_distance._get_version", return_value="0.2.5"),
            patch("custom_components.entity_distance.Path") as mock_path_cls,
        ):
            mock_path = MagicMock()
            mock_path.exists.return_value = False
            mock_path.__truediv__ = MagicMock(return_value=mock_path)
            mock_path_cls.return_value.parent = mock_path
            await _async_install_card(hass)

        register_resource.assert_not_called()
        hass.http.async_register_static_paths.assert_not_called()

    @pytest.mark.asyncio
    async def test_swallows_static_path_already_registered(self):
        from custom_components.entity_distance import _async_install_card

        hass = MagicMock()
        hass.data = {}
        hass.async_add_executor_job = AsyncMock(side_effect=lambda fn, *a: fn(*a))
        hass.http = MagicMock()
        hass.http.async_register_static_paths = AsyncMock(side_effect=RuntimeError("dup"))

        register_resource = AsyncMock()

        with (
            patch(
                "custom_components.entity_distance._async_purge_stale_resources",
                new=AsyncMock(),
            ),
            patch(
                "custom_components.entity_distance._async_register_lovelace_resource",
                new=register_resource,
            ),
            patch("custom_components.entity_distance._get_version", return_value="0.2.5"),
            patch("custom_components.entity_distance.Path") as mock_path_cls,
        ):
            mock_path = MagicMock()
            mock_path.exists.return_value = True
            mock_path.__truediv__ = MagicMock(return_value=mock_path)
            mock_path_cls.return_value.parent = mock_path
            await _async_install_card(hass)

        assert register_resource.call_count == 3
        assert hass.data[DOMAIN]["_card_installed"] is True


# ---------------------------------------------------------------------------
# _async_register_lovelace_resource
# ---------------------------------------------------------------------------


class TestRegisterLovelaceResource:
    @pytest.mark.asyncio
    async def test_no_lovelace_logs_info(self):
        from custom_components.entity_distance import _async_register_lovelace_resource

        hass = MagicMock()
        hass.data = {}

        await _async_register_lovelace_resource(hass, "x.js", "/x", "1.0")

    @pytest.mark.asyncio
    async def test_creates_when_no_existing(self):
        from homeassistant.components.lovelace.resources import (
            ResourceStorageCollection,
        )

        from custom_components.entity_distance import _async_register_lovelace_resource

        hass = MagicMock()
        resources = MagicMock(spec=ResourceStorageCollection)
        resources.loaded = True
        resources.async_items = MagicMock(return_value=[])
        resources.async_create_item = AsyncMock()
        hass.data = {"lovelace": MagicMock(resources=resources)}

        await _async_register_lovelace_resource(hass, "entity-distance-pair-card.js", "/x", "0.2.4")

        resources.async_create_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_loads_when_not_loaded(self):
        from homeassistant.components.lovelace.resources import (
            ResourceStorageCollection,
        )

        from custom_components.entity_distance import _async_register_lovelace_resource

        hass = MagicMock()
        resources = MagicMock(spec=ResourceStorageCollection)
        resources.loaded = False
        resources.async_load = AsyncMock()
        resources.async_items = MagicMock(return_value=[])
        resources.async_create_item = AsyncMock()
        hass.data = {"lovelace": MagicMock(resources=resources)}

        await _async_register_lovelace_resource(hass, "entity-distance-pair-card.js", "/x", "0.2.4")

        resources.async_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_appends_to_data_when_no_create_item(self):
        from custom_components.entity_distance import _async_register_lovelace_resource

        hass = MagicMock()
        resources = MagicMock(spec=["loaded", "async_items", "data"])
        resources.loaded = True
        resources.async_items = MagicMock(return_value=[])
        resources.data = [{"type": "module", "url": "/sentinel"}]
        hass.data = {"lovelace": MagicMock(resources=resources)}

        await _async_register_lovelace_resource(
            hass,
            "entity-distance-pair-card.js",
            "/entity-distance-pair-card.js",
            "0.2.4",
        )

        assert len(resources.data) == 2
        assert resources.data[1]["type"] == "module"

    @pytest.mark.asyncio
    async def test_neither_create_item_nor_data_append_is_noop(self):
        # Defensive: resources object has neither async_create_item nor a
        # mutable data list. Function must return cleanly without raising
        # AND without attempting either insertion path.
        from custom_components.entity_distance import _async_register_lovelace_resource

        hass = MagicMock()
        resources = MagicMock(spec=["loaded", "async_items"])
        resources.loaded = True
        resources.async_items = MagicMock(return_value=[])
        hass.data = {"lovelace": MagicMock(resources=resources)}

        await _async_register_lovelace_resource(hass, "entity-distance-pair-card.js", "/x", "0.2.4")

        # Neither path should have been touched. spec=[...] guarantees these
        # attrs don't exist; assert that nothing pretended to add them.
        assert not hasattr(resources, "async_create_item")
        assert not hasattr(resources, "data")

    @pytest.mark.asyncio
    async def test_dedup_skips_non_storage_collection(self):
        # Duplicates exist but resources is not a ResourceStorageCollection —
        # the delete branch is skipped per iteration, loop still completes
        # without attempting deletion.
        from custom_components.entity_distance import _async_register_lovelace_resource

        hass = MagicMock()
        resources = MagicMock(spec=["loaded", "async_items", "async_delete_item"])
        resources.loaded = True
        resources.async_delete_item = AsyncMock()
        url_base = "/entity-distance-pair-card.js"
        resources.async_items = MagicMock(
            return_value=[
                {"id": "1", "url": f"{url_base}?automatically-added&0.2.4"},
                {"id": "2", "url": f"{url_base}?automatically-added&0.2.3"},
            ]
        )
        hass.data = {"lovelace": MagicMock(resources=resources)}

        await _async_register_lovelace_resource(
            hass,
            "entity-distance-pair-card.js",
            f"{url_base}?automatically-added&0.2.4",
            "0.2.4",
        )

        # Non-StorageCollection → delete must be skipped despite duplicates present.
        resources.async_delete_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_removes_duplicates_keeps_first(self):
        from homeassistant.components.lovelace.resources import (
            ResourceStorageCollection,
        )

        from custom_components.entity_distance import _async_register_lovelace_resource

        hass = MagicMock()
        resources = MagicMock(spec=ResourceStorageCollection)
        resources.loaded = True
        url_base = "/entity-distance-pair-card.js"
        existing = [
            {"id": "1", "url": f"{url_base}?automatically-added&0.2.4"},
            {"id": "2", "url": f"{url_base}?automatically-added&0.2.3"},
            {"id": "3", "url": f"{url_base}?automatically-added&0.2.2"},
        ]
        resources.async_items = MagicMock(return_value=existing)
        resources.async_delete_item = AsyncMock()
        resources.async_update_item = AsyncMock()
        hass.data = {"lovelace": MagicMock(resources=resources)}

        await _async_register_lovelace_resource(
            hass, "entity-distance-pair-card.js", url_base, "0.2.4"
        )

        assert resources.async_delete_item.call_count == 2
        resources.async_update_item.assert_not_called()

    @pytest.mark.asyncio
    async def test_updates_url_when_version_changed(self):
        from homeassistant.components.lovelace.resources import (
            ResourceStorageCollection,
        )

        from custom_components.entity_distance import _async_register_lovelace_resource

        hass = MagicMock()
        resources = MagicMock(spec=ResourceStorageCollection)
        resources.loaded = True
        url_base = "/entity-distance-pair-card.js"
        existing = [{"id": "1", "url": f"{url_base}?automatically-added&0.2.3"}]
        resources.async_items = MagicMock(return_value=existing)
        resources.async_delete_item = AsyncMock()
        resources.async_update_item = AsyncMock()
        hass.data = {"lovelace": MagicMock(resources=resources)}

        await _async_register_lovelace_resource(
            hass, "entity-distance-pair-card.js", url_base, "0.2.4"
        )

        resources.async_update_item.assert_called_once()

    @pytest.mark.asyncio
    async def test_updates_dict_url_when_not_storage(self):
        from custom_components.entity_distance import _async_register_lovelace_resource

        hass = MagicMock()
        # Not ResourceStorageCollection — plain object with mutable dict items
        resources = MagicMock(spec=["loaded", "async_items"])
        resources.loaded = True
        url_base = "/entity-distance-pair-card.js"
        item = {"id": "1", "url": f"{url_base}?automatically-added&0.2.3"}
        resources.async_items = MagicMock(return_value=[item])
        hass.data = {"lovelace": MagicMock(resources=resources)}

        await _async_register_lovelace_resource(
            hass, "entity-distance-pair-card.js", url_base, "0.2.4"
        )

        assert item["url"] == f"{url_base}?automatically-added&0.2.4"

    @pytest.mark.asyncio
    async def test_no_change_when_url_already_current(self):
        from homeassistant.components.lovelace.resources import (
            ResourceStorageCollection,
        )

        from custom_components.entity_distance import _async_register_lovelace_resource

        hass = MagicMock()
        resources = MagicMock(spec=ResourceStorageCollection)
        resources.loaded = True
        url_base = "/entity-distance-pair-card.js"
        existing = [{"id": "1", "url": f"{url_base}?automatically-added&0.2.4"}]
        resources.async_items = MagicMock(return_value=existing)
        resources.async_delete_item = AsyncMock()
        resources.async_update_item = AsyncMock()
        hass.data = {"lovelace": MagicMock(resources=resources)}

        await _async_register_lovelace_resource(
            hass, "entity-distance-pair-card.js", url_base, "0.2.4"
        )

        resources.async_update_item.assert_not_called()
        resources.async_delete_item.assert_not_called()
