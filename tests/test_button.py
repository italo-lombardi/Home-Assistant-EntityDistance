"""Tests for RefreshButton."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.entity_distance.button import RefreshButton


def _make_button(entities: list[str], hass=None):
    coordinator = MagicMock()
    coordinator.entities = entities
    entry = MagicMock()
    entry.entry_id = "test_entry"
    device_info = MagicMock()

    btn = RefreshButton.__new__(RefreshButton)
    btn.coordinator = coordinator
    btn._entry = entry
    btn._attr_unique_id = f"{entry.entry_id}_refresh"
    btn._attr_device_info = device_info
    btn.hass = hass or MagicMock()
    return btn


class TestRefreshButtonInit:
    def test_unique_id(self):
        btn = _make_button(["person.alice", "person.bob"])
        assert btn._attr_unique_id == "test_entry_refresh"


class TestResolveDeviceId:
    def test_returns_device_id_from_registry(self):
        btn = _make_button(["person.alice"])
        registry = MagicMock()
        entry = MagicMock()
        entry.device_id = "device_123"
        registry.async_get.return_value = entry

        result = btn._resolve_device_id(registry, "person.alice")
        assert result == "device_123"

    def test_returns_none_when_entry_missing(self):
        btn = _make_button(["person.alice"])
        registry = MagicMock()
        registry.async_get.return_value = None

        result = btn._resolve_device_id(registry, "person.alice")
        assert result is None

    def test_returns_none_when_device_id_none(self):
        btn = _make_button(["person.alice"])
        registry = MagicMock()
        entry = MagicMock()
        entry.device_id = None
        registry.async_get.return_value = entry

        result = btn._resolve_device_id(registry, "person.alice")
        assert result is None

    def test_person_falls_back_to_source_tracker(self):
        btn = _make_button(["person.alice"])
        registry = MagicMock()

        # person.alice has no device_id
        person_entry = MagicMock()
        person_entry.device_id = None

        # source tracker has device_id
        source_entry = MagicMock()
        source_entry.device_id = "device_from_source"

        def _get(eid):
            if eid == "person.alice":
                return person_entry
            if eid == "device_tracker.phone":
                return source_entry
            return None

        registry.async_get.side_effect = _get

        state = MagicMock()
        state.attributes = {"source": "device_tracker.phone"}
        btn.hass.states.get.return_value = state

        result = btn._resolve_device_id(registry, "person.alice")
        assert result == "device_from_source"

    def test_person_source_no_state(self):
        btn = _make_button(["person.alice"])
        registry = MagicMock()
        person_entry = MagicMock()
        person_entry.device_id = None
        registry.async_get.return_value = person_entry
        btn.hass.states.get.return_value = None

        result = btn._resolve_device_id(registry, "person.alice")
        assert result is None

    def test_person_source_no_source_attribute(self):
        btn = _make_button(["person.alice"])
        registry = MagicMock()
        person_entry = MagicMock()
        person_entry.device_id = None
        registry.async_get.return_value = person_entry

        state = MagicMock()
        state.attributes = {}
        btn.hass.states.get.return_value = state

        result = btn._resolve_device_id(registry, "person.alice")
        assert result is None

    def test_person_source_entry_has_no_device_id(self):
        btn = _make_button(["person.alice"])
        registry = MagicMock()
        person_entry = MagicMock()
        person_entry.device_id = None
        source_entry = MagicMock()
        source_entry.device_id = None

        def _get(eid):
            if eid == "person.alice":
                return person_entry
            return source_entry

        registry.async_get.side_effect = _get
        state = MagicMock()
        state.attributes = {"source": "device_tracker.phone"}
        btn.hass.states.get.return_value = state

        result = btn._resolve_device_id(registry, "person.alice")
        assert result is None

    def test_non_person_entity_with_no_device_id_returns_none(self):
        # device_tracker.* (or any non-person) with no device_id on entry skips
        # the person.* source-resolution fallback and returns None directly.
        btn = _make_button(["device_tracker.phone"])
        registry = MagicMock()
        entry = MagicMock()
        entry.device_id = None
        registry.async_get.return_value = entry

        result = btn._resolve_device_id(registry, "device_tracker.phone")
        assert result is None


class TestResolveNotifyService:
    def test_returns_service_when_mobile_app_available(self):
        btn = _make_button(["person.alice"])
        with (
            patch(
                "custom_components.entity_distance.button.RefreshButton._resolve_notify_service"
            ) as mock_resolve,
        ):
            mock_resolve.return_value = "mobile_app_alice"
            result = btn._resolve_notify_service("device_123")
            assert result == "mobile_app_alice"

    def test_returns_none_on_import_error(self):
        btn = _make_button(["person.alice"])
        with patch.dict(
            "sys.modules", {"homeassistant.components.mobile_app.util": None}
        ):
            result = btn._resolve_notify_service("device_123")
            assert result is None

    def test_returns_none_when_webhook_id_none(self):
        btn = _make_button(["person.alice"])
        mock_util = MagicMock()
        mock_util.webhook_id_from_device_id.return_value = None
        with patch.dict(
            "sys.modules", {"homeassistant.components.mobile_app.util": mock_util}
        ):
            result = btn._resolve_notify_service("device_123")
            assert result is None

    def test_returns_service_name(self):
        btn = _make_button(["person.alice"])
        mock_util = MagicMock()
        mock_util.webhook_id_from_device_id.return_value = "webhook_abc"
        mock_util.get_notify_service.return_value = "mobile_app_alice_phone"
        with patch.dict(
            "sys.modules", {"homeassistant.components.mobile_app.util": mock_util}
        ):
            result = btn._resolve_notify_service("device_123")
            assert result == "mobile_app_alice_phone"


class TestAsyncPress:
    @pytest.mark.asyncio
    async def test_skips_zone_entities(self):
        btn = _make_button(["zone.home", "person.alice"])
        registry = MagicMock()

        # person.alice has device + notify service
        alice_entry = MagicMock()
        alice_entry.device_id = "device_alice"
        registry.async_get.return_value = alice_entry

        btn.hass.services.async_call = AsyncMock()

        with (
            patch(
                "custom_components.entity_distance.button.er.async_get",
                return_value=registry,
            ),
            patch.object(
                btn, "_resolve_notify_service", return_value="mobile_app_alice"
            ),
        ):
            await btn.async_press()

        # Only alice should have triggered a service call (zone.home skipped)
        btn.hass.services.async_call.assert_called_once_with(
            "notify",
            "mobile_app_alice",
            {"message": "request_location_update"},
            blocking=False,
        )

    @pytest.mark.asyncio
    async def test_skips_entity_with_no_device_id(self):
        btn = _make_button(["person.alice"])
        registry = MagicMock()
        registry.async_get.return_value = None

        btn.hass.services.async_call = AsyncMock()

        with patch(
            "custom_components.entity_distance.button.er.async_get",
            return_value=registry,
        ):
            await btn.async_press()

        btn.hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_entity_with_no_notify_service(self):
        btn = _make_button(["person.alice"])
        registry = MagicMock()
        alice_entry = MagicMock()
        alice_entry.device_id = "device_alice"
        registry.async_get.return_value = alice_entry

        btn.hass.services.async_call = AsyncMock()

        with (
            patch(
                "custom_components.entity_distance.button.er.async_get",
                return_value=registry,
            ),
            patch.object(btn, "_resolve_notify_service", return_value=None),
        ):
            await btn.async_press()

        btn.hass.services.async_call.assert_not_called()

    @pytest.mark.asyncio
    async def test_calls_notify_for_each_non_zone_entity(self):
        btn = _make_button(["person.alice", "person.bob"])
        registry = MagicMock()

        def _reg_get(eid):
            e = MagicMock()
            e.device_id = f"device_{eid.split('.')[1]}"
            return e

        registry.async_get.side_effect = _reg_get
        btn.hass.services.async_call = AsyncMock()

        def _notify(device_id):
            return f"mobile_app_{device_id.split('_')[1]}"

        with (
            patch(
                "custom_components.entity_distance.button.er.async_get",
                return_value=registry,
            ),
            patch.object(btn, "_resolve_notify_service", side_effect=_notify),
        ):
            await btn.async_press()

        assert btn.hass.services.async_call.call_count == 2

    @pytest.mark.asyncio
    async def test_deduplicates_entities(self):
        # Same entity appears twice — should only call notify once
        btn = _make_button(["person.alice", "person.alice"])
        registry = MagicMock()
        alice_entry = MagicMock()
        alice_entry.device_id = "device_alice"
        registry.async_get.return_value = alice_entry

        btn.hass.services.async_call = AsyncMock()

        with (
            patch(
                "custom_components.entity_distance.button.er.async_get",
                return_value=registry,
            ),
            patch.object(
                btn, "_resolve_notify_service", return_value="mobile_app_alice"
            ),
        ):
            await btn.async_press()

        btn.hass.services.async_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_continues_after_service_call_exception(self):
        btn = _make_button(["person.alice", "person.bob"])
        registry = MagicMock()

        def _reg_get(eid):
            e = MagicMock()
            e.device_id = f"device_{eid.split('.')[1]}"
            return e

        registry.async_get.side_effect = _reg_get
        # First call raises, second succeeds
        btn.hass.services.async_call = AsyncMock(
            side_effect=[Exception("network error"), None]
        )

        with (
            patch(
                "custom_components.entity_distance.button.er.async_get",
                return_value=registry,
            ),
            patch.object(btn, "_resolve_notify_service", return_value="mobile_app_x"),
        ):
            # Should not raise
            await btn.async_press()

        assert btn.hass.services.async_call.call_count == 2


# ---------------------------------------------------------------------------
# async_setup_entry + RefreshButton.__init__
# ---------------------------------------------------------------------------


class TestAsyncSetupEntry:
    """Cover async_setup_entry (lines 25-43) and RefreshButton.__init__ (lines 56-59)."""

    @pytest.mark.asyncio
    async def test_setup_entry_adds_refresh_button(self):
        from custom_components.entity_distance.button import (
            RefreshButton,
            async_setup_entry,
        )
        from custom_components.entity_distance.const import DOMAIN

        coordinator = MagicMock()
        coordinator.entities = ["person.alice", "person.bob"]

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass = MagicMock()
        hass.states.get.return_value = None
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        await async_setup_entry(hass, entry, lambda entities: added.extend(entities))

        assert len(added) == 1
        assert isinstance(added[0], RefreshButton)

    @pytest.mark.asyncio
    async def test_setup_entry_friendly_name_from_state(self):
        from custom_components.entity_distance.button import async_setup_entry
        from custom_components.entity_distance.const import DOMAIN

        coordinator = MagicMock()
        coordinator.entities = ["person.alice", "person.bob"]

        entry = MagicMock()
        entry.entry_id = "test_entry"

        def _get_state(eid):
            s = MagicMock()
            s.name = "Alice" if "alice" in eid else "Bob"
            return s

        hass = MagicMock()
        hass.states.get.side_effect = _get_state
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        await async_setup_entry(hass, entry, lambda entities: added.extend(entities))
        assert len(added) == 1

    @pytest.mark.asyncio
    async def test_refresh_button_init_sets_attrs(self):
        from custom_components.entity_distance.button import RefreshButton

        coordinator = MagicMock()
        entry = MagicMock()
        entry.entry_id = "my_entry"
        device_info = MagicMock()

        btn = RefreshButton(coordinator, entry, device_info)

        assert btn._attr_unique_id == "my_entry_refresh"
        assert btn._attr_device_info is device_info
        assert btn._entry is entry
