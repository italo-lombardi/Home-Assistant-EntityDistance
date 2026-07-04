"""Tests for new sensors: EntityStateSensor, TodayUnaccountedTimeSensor, persistence, tick."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from homeassistant.util import dt as dt_util
import pytest

from custom_components.entity_distance.models import GroupData, PairState, pair_key
from custom_components.entity_distance.sensor import (
    EntityStateSensor,
    TodayUnaccountedTimeSensor,
)

_DEFAULT_THRESHOLDS = {}


def _make_sensor(cls, pair_state: PairState, extra=None):
    coordinator = MagicMock()
    k = pair_key(pair_state.entity_a_id, pair_state.entity_b_id)
    coordinator.data = GroupData(pairs={k: pair_state})
    coordinator.bucket_thresholds = _DEFAULT_THRESHOLDS
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = cls.__new__(cls)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._pair_key = k
    sensor._sensor_key = "test"
    sensor._attr_unique_id = "test_sensor"
    sensor._attr_device_info = {}
    if extra:
        for k2, v in extra.items():
            setattr(sensor, k2, v)
    return sensor


# ---------------------------------------------------------------------------
# EntityStateSensor
# ---------------------------------------------------------------------------


class TestEntityStateSensor:
    def _make(self, entity_id: str, state_value: str | None) -> EntityStateSensor:
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        sensor = _make_sensor(
            EntityStateSensor,
            ps,
            {
                "_tracked_entity_id": entity_id,
                "_which": "a",
            },
        )
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
    def _make(
        self, today_zone_seconds: dict[str, float] | None = None
    ) -> TodayUnaccountedTimeSensor:
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        ps.today_zone_seconds = today_zone_seconds or {}
        return _make_sensor(TodayUnaccountedTimeSensor, ps)

    def test_returns_zero_when_all_time_accounted(self):
        # Account for all of today's elapsed seconds.
        now = dt_util.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed = (now - midnight).total_seconds()
        sensor = self._make({"very_near": elapsed})
        val = sensor.native_value
        assert val is not None
        # Floating-point + rounding tolerance.
        assert 0.0 <= val < 1.0

    def test_returns_full_elapsed_when_nothing_accounted(self):
        now = dt_util.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed_min = (now - midnight).total_seconds() / 60
        sensor = self._make({})
        val = sensor.native_value
        assert val is not None
        assert val == pytest.approx(elapsed_min, abs=1.0)

    def test_returns_partial_when_partially_accounted(self):
        # 600 s accounted leaves elapsed - 600 s unaccounted (clamped to 0).
        now = dt_util.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed_min = (now - midnight).total_seconds() / 60
        sensor = self._make({"near": 600.0, "far": 300.0})
        val = sensor.native_value
        assert val is not None
        expected = max(0.0, elapsed_min - 15.0)
        assert val == pytest.approx(expected, abs=1.0)

    def test_never_negative_when_accounted_overshoots(self):
        # Accounted time exceeds elapsed (should clamp to 0, not go negative).
        sensor = self._make({"very_near": 999_999.0})
        val = sensor.native_value
        assert val is not None
        assert val >= 0.0


# ---------------------------------------------------------------------------
# Persistence: _async_save_state / _async_load_state
# ---------------------------------------------------------------------------


class TestPersistence:
    def _make_coordinator(self, stored_data=None):
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )

        hass = MagicMock()
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {
            "entities": ["person.alice", "person.bob"],
        }
        entry.options = {}

        store = AsyncMock()
        store.async_load = AsyncMock(return_value=stored_data)
        store.async_save = AsyncMock()

        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])

        coordinator = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coordinator.hass = hass
        coordinator._entry = entry
        coordinator._entities = ["person.alice", "person.bob"]
        coordinator._pair_states = {k: ps}
        coordinator._store = store
        coordinator.logger = MagicMock()
        return coordinator

    @pytest.mark.asyncio
    async def test_load_restores_today_counters_same_day(self):
        today = dt_util.now().date().isoformat()
        k = pair_key("person.alice", "person.bob")
        stored = {
            f"{k[0]}__{k[1]}": {
                "today_reset_date": today,
                "today_proximity_seconds": 1800.0,
                "today_zone_seconds": {"very_far": 3600.0},
                "proximity_duration_s": 600.0,
                "last_seen_together": None,
            }
        }
        coordinator = self._make_coordinator(stored)
        await coordinator._async_load_state()
        ps = coordinator._pair_states[k]
        assert ps.today_proximity_seconds == 1800.0
        assert ps.today_zone_seconds == {"very_far": 3600.0}
        assert ps.proximity_duration_s == 600.0

    @pytest.mark.asyncio
    async def test_load_discards_today_counters_stale_day(self):
        yesterday = (dt_util.now().date() - timedelta(days=1)).isoformat()
        k = pair_key("person.alice", "person.bob")
        stored = {
            f"{k[0]}__{k[1]}": {
                "today_reset_date": yesterday,
                "today_proximity_seconds": 9999.0,
                "today_zone_seconds": {"very_near": 9999.0},
                "proximity_duration_s": 100.0,
                "last_seen_together": None,
            }
        }
        coordinator = self._make_coordinator(stored)
        await coordinator._async_load_state()
        ps = coordinator._pair_states[k]
        assert ps.today_proximity_seconds == 0.0
        assert ps.today_zone_seconds == {}
        assert ps.proximity_duration_s == 100.0

    @pytest.mark.asyncio
    async def test_load_restores_last_seen_together(self):
        today = dt_util.now().date().isoformat()
        ts = "2026-05-13T10:00:00+00:00"
        k = pair_key("person.alice", "person.bob")
        stored = {
            f"{k[0]}__{k[1]}": {
                "today_reset_date": today,
                "today_proximity_seconds": 0.0,
                "today_zone_seconds": {},
                "proximity_duration_s": 0.0,
                "last_seen_together": ts,
            }
        }
        coordinator = self._make_coordinator(stored)
        await coordinator._async_load_state()
        ps = coordinator._pair_states[k]
        assert ps.last_seen_together is not None
        assert ps.last_seen_together.isoformat() == ts

    @pytest.mark.asyncio
    async def test_load_handles_no_stored_data(self):
        coordinator = self._make_coordinator(None)
        await coordinator._async_load_state()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        assert ps.today_proximity_seconds == 0.0
        assert ps.proximity_duration_s == 0.0

    @pytest.mark.asyncio
    async def test_save_persists_today_counters(self):
        coordinator = self._make_coordinator()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        ps.today_reset_date = dt_util.now().date()
        ps.today_proximity_seconds = 300.0
        ps.today_zone_seconds = {"very_far": 1200.0}
        ps.proximity_duration_s = 60.0
        ps.last_seen_together = None
        await coordinator._async_save_state()
        coordinator._store.async_save.assert_called_once()
        saved = coordinator._store.async_save.call_args[0][0]
        store_key = f"{k[0]}__{k[1]}"
        assert saved[store_key]["today_proximity_seconds"] == 300.0
        assert saved[store_key]["today_zone_seconds"] == {"very_far": 1200.0}
        assert saved[store_key]["proximity_duration_s"] == 60.0
