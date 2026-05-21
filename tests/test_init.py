"""Tests for async_setup_entry, async_unload_entry, and async_migrate_entry."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.entity_distance.const import (
    CONF_ENTITIES,
    CONF_ENTITY_A,
    CONF_ENTITY_B,
    DOMAIN,
)


class TestAsyncMigrateEntry:
    def _make_entry(self, version: int, data: dict) -> MagicMock:
        entry = MagicMock()
        entry.version = version
        entry.entry_id = "test_entry"
        entry.data = data
        return entry

    @pytest.mark.asyncio
    async def test_migration_v1_with_entity_a_b(self):
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_entry(1, {CONF_ENTITY_A: "person.alice", CONF_ENTITY_B: "person.bob"})

        with patch(
            "custom_components.entity_distance.er.async_migrate_entries",
            new=AsyncMock(),
        ):
            result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = hass.config_entries.async_update_entry.call_args
        new_data = call_kwargs[1]["data"]
        assert new_data[CONF_ENTITIES] == ["person.alice", "person.bob"]
        assert call_kwargs[1]["version"] == 2

    @pytest.mark.asyncio
    async def test_migration_v1_missing_entity_data_returns_false(self):
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        entry = self._make_entry(1, {})  # no entity_a or entity_b

        result = await async_migrate_entry(hass, entry)
        assert result is False

    @pytest.mark.asyncio
    async def test_migration_v1_already_has_entities_skips_overwrite(self):
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_entry(
            1,
            {
                CONF_ENTITIES: ["person.alice", "person.carol"],
                CONF_ENTITY_A: "person.alice",
                CONF_ENTITY_B: "person.bob",
            },
        )

        with patch(
            "custom_components.entity_distance.er.async_migrate_entries",
            new=AsyncMock(),
        ):
            result = await async_migrate_entry(hass, entry)

        assert result is True
        call_kwargs = hass.config_entries.async_update_entry.call_args
        new_data = call_kwargs[1]["data"]
        # CONF_ENTITIES already present — should not be overwritten with entity_a/b
        assert new_data[CONF_ENTITIES] == ["person.alice", "person.carol"]

    @pytest.mark.asyncio
    async def test_migration_already_v2_noop(self):
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_entry(2, {CONF_ENTITIES: ["person.alice", "person.bob"]})

        result = await async_migrate_entry(hass, entry)
        assert result is True
        hass.config_entries.async_update_entry.assert_not_called()

    @pytest.mark.asyncio
    async def test_migration_v1_renames_entity_registry_unique_ids(self):
        """_migrate_unique_id callback renames old-format unique_ids to pair-prefixed format."""
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        hass.config_entries.async_update_entry = MagicMock()
        entry = self._make_entry(1, {CONF_ENTITY_A: "person.alice", CONF_ENTITY_B: "person.bob"})

        captured_callback = None

        async def _capture_migrate_entries(h, entry_id, callback):
            nonlocal captured_callback
            captured_callback = callback

        with patch(
            "custom_components.entity_distance.er.async_migrate_entries",
            side_effect=_capture_migrate_entries,
        ):
            await async_migrate_entry(hass, entry)

        assert captured_callback is not None

        # Old-format unique_id: {entry_id}_{sensor_key}
        old_entity = MagicMock()
        old_entity.unique_id = "test_entry_distance"
        result = captured_callback(old_entity)
        assert result == {"new_unique_id": "test_entry_person.alice__person.bob_distance"}

        # Already migrated (contains __ with domain.name before it)
        migrated_entity = MagicMock()
        migrated_entity.unique_id = "test_entry_person.alice__person.bob_distance"
        assert captured_callback(migrated_entity) is None

        # Different entry_id — not touched
        other_entity = MagicMock()
        other_entity.unique_id = "other_entry_distance"
        assert captured_callback(other_entity) is None


class TestCoordinatorSetupAndUnload:
    def _make_coordinator(self, entities: list[str]) -> MagicMock:
        coord = MagicMock()
        coord.entities = entities
        coord.async_setup = AsyncMock()
        coord._async_recalculate = AsyncMock()
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
