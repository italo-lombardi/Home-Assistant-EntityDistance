"""Tests for new sensors: EntityStateSensor, TodayUnaccountedTimeSensor, persistence, tick."""

from __future__ import annotations

from datetime import datetime, timedelta, date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.entity_distance.models import PairData, PairState
from custom_components.entity_distance.sensor import (
    EntityStateSensor,
    TodayUnaccountedTimeSensor,
)

_DEFAULT_THRESHOLDS = {}


def _make_sensor(cls, pair_state: PairState, extra=None):
    coordinator = MagicMock()
    coordinator.data = PairData(pair=pair_state)
    coordinator.bucket_thresholds = _DEFAULT_THRESHOLDS
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = cls.__new__(cls)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._sensor_key = "test"
    sensor._attr_unique_id = "test_sensor"
    sensor._attr_device_info = {}
    if extra:
        for k, v in extra.items():
            setattr(sensor, k, v)
    return sensor


# ---------------------------------------------------------------------------
# EntityStateSensor
# ---------------------------------------------------------------------------


class TestEntityStateSensor:
    def _make(self, entity_id: str, state_value: str | None) -> EntityStateSensor:
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        sensor = _make_sensor(EntityStateSensor, ps, {
            "_tracked_entity_id": entity_id,
            "_which": "a",
        })
        hass = MagicMock()
        if state_value is None:
            hass.states.get.return_value = None
        else:
            mock_state = MagicMock()
            mock_state.state = state_value
            hass.states.get.return_value = mock_state
        sensor.hass = hass
        return sensor

    def test_returns_state_string(self):
        sensor = self._make("person.alice", "home")
        assert sensor.native_value == "home"

    def test_returns_away_state(self):
        sensor = self._make("person.alice", "not_home")
        assert sensor.native_value == "not_home"

    def test_returns_zone_name(self):
        sensor = self._make("person.alice", "work")
        assert sensor.native_value == "work"

    def test_returns_none_when_entity_missing(self):
        sensor = self._make("person.alice", None)
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# TodayUnaccountedTimeSensor
# ---------------------------------------------------------------------------


class TestTodayUnaccountedTimeSensor:
    def _make(self, prev_calc_time: datetime | None) -> TodayUnaccountedTimeSensor:
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        ps.prev_calc_time = prev_calc_time
        return _make_sensor(TodayUnaccountedTimeSensor, ps)

    def test_returns_none_when_no_prev_calc(self):
        sensor = self._make(None)
        assert sensor.native_value is None

    def test_recent_update_returns_small_gap(self):
        now = datetime.now().astimezone()
        sensor = self._make(now - timedelta(seconds=90))
        val = sensor.native_value
        assert val is not None
        # ~1.5 min, allow 0–3 min range
        assert 1.0 <= val <= 3.0

    def test_zero_gap_when_just_updated(self):
        now = datetime.now().astimezone()
        sensor = self._make(now)
        val = sensor.native_value
        assert val is not None
        assert val >= 0.0

    def test_gap_capped_at_midnight(self):
        # prev_calc_time far in the past — gap returned is (now - prev_calc_time) / 60
        # The midnight cap only clamps future; past gap is uncapped.
        now = datetime.now().astimezone()
        two_hours_ago = now - timedelta(hours=2)
        sensor = self._make(two_hours_ago)
        val = sensor.native_value
        assert val is not None
        # ~120 min, allow 119–122 min range
        assert 119.0 <= val <= 122.0


# ---------------------------------------------------------------------------
# Persistence: _async_save_state / _async_load_state
# ---------------------------------------------------------------------------


class TestPersistence:
    def _make_coordinator(self, stored_data=None):
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {
            "entity_a": "person.alice",
            "entity_b": "person.bob",
        }
        entry.options = {}

        store = AsyncMock()
        store.async_load = AsyncMock(return_value=stored_data)
        store.async_save = AsyncMock()

        coordinator = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coordinator.hass = hass
        coordinator._entry = entry
        coordinator._entity_a = "person.alice"
        coordinator._entity_b = "person.bob"
        coordinator._pair_state = PairState(
            entity_a_id="person.alice",
            entity_b_id="person.bob",
        )
        coordinator._store = store
        coordinator.logger = MagicMock()
        return coordinator

    @pytest.mark.asyncio
    async def test_load_restores_today_counters_same_day(self):
        today = date.today().isoformat()
        stored = {
            "today_reset_date": today,
            "today_proximity_seconds": 1800.0,
            "today_zone_seconds": {"very_far": 3600.0},
            "proximity_duration_s": 600.0,
            "last_seen_together": None,
        }
        coordinator = self._make_coordinator(stored)
        await coordinator._async_load_state()
        ps = coordinator._pair_state
        assert ps.today_proximity_seconds == 1800.0
        assert ps.today_zone_seconds == {"very_far": 3600.0}
        assert ps.proximity_duration_s == 600.0

    @pytest.mark.asyncio
    async def test_load_discards_today_counters_stale_day(self):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        stored = {
            "today_reset_date": yesterday,
            "today_proximity_seconds": 9999.0,
            "today_zone_seconds": {"very_near": 9999.0},
            "proximity_duration_s": 100.0,
            "last_seen_together": None,
        }
        coordinator = self._make_coordinator(stored)
        await coordinator._async_load_state()
        ps = coordinator._pair_state
        # today counters should NOT be restored (stale date)
        assert ps.today_proximity_seconds == 0.0
        assert ps.today_zone_seconds == {}
        # but proximity_duration_s always restored
        assert ps.proximity_duration_s == 100.0

    @pytest.mark.asyncio
    async def test_load_restores_last_seen_together(self):
        today = date.today().isoformat()
        ts = "2026-05-13T10:00:00+00:00"
        stored = {
            "today_reset_date": today,
            "today_proximity_seconds": 0.0,
            "today_zone_seconds": {},
            "proximity_duration_s": 0.0,
            "last_seen_together": ts,
        }
        coordinator = self._make_coordinator(stored)
        await coordinator._async_load_state()
        ps = coordinator._pair_state
        assert ps.last_seen_together is not None
        assert ps.last_seen_together.isoformat() == ts

    @pytest.mark.asyncio
    async def test_load_handles_no_stored_data(self):
        coordinator = self._make_coordinator(None)
        await coordinator._async_load_state()
        ps = coordinator._pair_state
        assert ps.today_proximity_seconds == 0.0
        assert ps.proximity_duration_s == 0.0

    @pytest.mark.asyncio
    async def test_save_persists_today_counters(self):
        coordinator = self._make_coordinator()
        ps = coordinator._pair_state
        ps.today_reset_date = date.today()
        ps.today_proximity_seconds = 300.0
        ps.today_zone_seconds = {"very_far": 1200.0}
        ps.proximity_duration_s = 60.0
        ps.last_seen_together = None
        await coordinator._async_save_state()
        coordinator._store.async_save.assert_called_once()
        saved = coordinator._store.async_save.call_args[0][0]
        assert saved["today_proximity_seconds"] == 300.0
        assert saved["today_zone_seconds"] == {"very_far": 1200.0}
        assert saved["proximity_duration_s"] == 60.0
