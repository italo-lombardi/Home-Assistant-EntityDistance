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
