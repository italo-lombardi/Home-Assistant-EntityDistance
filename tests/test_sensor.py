"""Tests for sensor entities."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from custom_components.entity_distance.const import (
    BUCKET_FAR,
    BUCKET_MID,
    BUCKET_NEAR,
    BUCKET_VERY_FAR,
    BUCKET_VERY_NEAR,
    DEFAULT_ZONE_FAR_M,
    DEFAULT_ZONE_MID_M,
    DEFAULT_ZONE_NEAR_M,
    DEFAULT_ZONE_VERY_NEAR_M,
    DIRECTION_APPROACHING,
    DIRECTION_DIVERGING,
    DIRECTION_STATIONARY,
)
from custom_components.entity_distance.models import GroupData, PairState, pair_key
from custom_components.entity_distance.sensor import (
    BucketLevelSensor,
    DirectionLevelSensor,
    ProximityDurationSensor,
    ProximityRateSensor,
    TodayZoneTimeSensor,
    UpdateCountSensor,
)

_BUCKET_LEVEL_MAP = {
    BUCKET_VERY_NEAR: 1,
    BUCKET_NEAR: 2,
    BUCKET_MID: 3,
    BUCKET_FAR: 4,
    BUCKET_VERY_FAR: 5,
}

_DEFAULT_THRESHOLDS = {
    BUCKET_VERY_NEAR: DEFAULT_ZONE_VERY_NEAR_M,
    BUCKET_NEAR: DEFAULT_ZONE_NEAR_M,
    BUCKET_MID: DEFAULT_ZONE_MID_M,
    BUCKET_FAR: DEFAULT_ZONE_FAR_M,
}


def _make_sensor(cls, pair_state: PairState):
    """Build a sensor instance with a minimal coordinator/entry mock."""
    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    coordinator.altitude_aligned_threshold_m = 5.0
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
    return sensor


class TestSensorValues:
    def _make_pair(self, **kwargs) -> PairState:
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        for k, v in kwargs.items():
            setattr(ps, k, v)
        ps.data_valid = True
        return ps

    def test_distance_value(self):
        ps = self._make_pair(distance_m=300.0)
        assert ps.distance_m == 300.0

    def test_proximity_duration_minutes(self):
        ps = self._make_pair(proximity_duration_s=3600.0)
        assert round(ps.proximity_duration_s / 60, 1) == 60.0

    def test_today_proximity_time_minutes(self):
        ps = self._make_pair(today_proximity_seconds=1800.0)
        assert round(ps.today_proximity_seconds / 60, 1) == 30.0

    def test_direction(self):
        ps = self._make_pair(direction=DIRECTION_APPROACHING)
        assert ps.direction == DIRECTION_APPROACHING

    def test_eta_none_when_not_approaching(self):
        ps = self._make_pair(direction="diverging", eta_minutes=None)
        assert ps.eta_minutes is None

    def test_diagnostic_accuracy(self):
        ps = self._make_pair(accuracy_a=15.0, accuracy_b=30.0)
        assert ps.accuracy_a == 15.0
        assert ps.accuracy_b == 30.0


class TestBucketLevelSensor:
    """Test that BucketLevelSensor.native_value maps each bucket to 1-5."""

    # Representative distances that land in each bucket with default thresholds
    _BUCKET_DISTANCES = [
        (50, BUCKET_VERY_NEAR, 1),
        (300, BUCKET_NEAR, 2),
        (2000, BUCKET_MID, 3),
        (10000, BUCKET_FAR, 4),
        (25000, BUCKET_VERY_FAR, 5),
    ]

    def _make_sensor(self, distance_m: float) -> BucketLevelSensor:
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.distance_m = distance_m
        ps.data_valid = True
        return _make_sensor(BucketLevelSensor, ps)

    def test_very_near_returns_1(self):
        sensor = self._make_sensor(50)
        assert sensor.native_value == 1

    def test_near_returns_2(self):
        sensor = self._make_sensor(300)
        assert sensor.native_value == 2

    def test_mid_returns_3(self):
        sensor = self._make_sensor(2000)
        assert sensor.native_value == 3

    def test_far_returns_4(self):
        sensor = self._make_sensor(10000)
        assert sensor.native_value == 4

    def test_very_far_returns_5(self):
        sensor = self._make_sensor(25000)
        assert sensor.native_value == 5

    def test_none_distance_returns_none(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.distance_m = None
        ps.data_valid = True
        sensor = _make_sensor(BucketLevelSensor, ps)
        assert sensor.native_value is None


class TestProximityDurationSensor:
    """Test ProximityDurationSensor.native_value live session calculation."""

    def _make_sensor(self, ps: PairState) -> ProximityDurationSensor:
        return _make_sensor(ProximityDurationSensor, ps)

    def test_returns_none_when_tracking_not_started(self):
        # proximity_tracking_started=None means no tracking yet → None
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.proximity_tracking_started = None
        sensor = self._make_sensor(ps)
        assert sensor.native_value is None

    def test_still_returns_value_when_data_invalid(self):
        # data_valid=False but coordinator available → cumulative sensor returns value, not None
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = False
        ps.proximity_tracking_started = datetime.now().astimezone()
        ps.proximity_duration_s = 300.0
        sensor = self._make_sensor(ps)
        assert sensor.native_value is not None

    def test_no_live_session_returns_stored_minutes(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.proximity_tracking_started = datetime.now().astimezone()
        ps.proximity = False
        ps.proximity_duration_s = 3600.0  # 60 minutes stored
        ps.proximity_since = None
        sensor = self._make_sensor(ps)
        assert sensor.native_value == 60.0

    def test_live_session_adds_elapsed_seconds(self):
        # Set proximity_since 120 seconds in the past
        now = datetime.now().astimezone()
        past = now - timedelta(seconds=120)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.proximity_tracking_started = past
        ps.proximity = True
        ps.proximity_since = past
        ps.proximity_duration_s = 0.0
        sensor = self._make_sensor(ps)
        value = sensor.native_value
        assert value is not None
        # At least 120s / 60 = 2.0 min; allow up to 3 min for test slowness
        assert 2.0 <= value <= 3.0

    def test_stored_plus_live_session_combined(self):
        now = datetime.now().astimezone()
        past = now - timedelta(seconds=60)  # 1 minute live
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.proximity_tracking_started = past
        ps.proximity = True
        ps.proximity_since = past
        ps.proximity_duration_s = 3600.0  # 60 min stored
        sensor = self._make_sensor(ps)
        value = sensor.native_value
        assert value is not None
        # stored (60 min) + live (~1 min) = ~61 min
        assert 61.0 <= value <= 62.0

    def test_zero_stored_zero_live_returns_zero(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.proximity_tracking_started = datetime.now().astimezone()
        ps.proximity = False
        ps.proximity_since = None
        ps.proximity_duration_s = 0.0
        sensor = self._make_sensor(ps)
        assert sensor.native_value == 0.0


# ---------------------------------------------------------------------------
# Helpers for sensors with extra constructor parameters
# ---------------------------------------------------------------------------


def _make_zone_sensor(bucket: str, pair_state: PairState) -> TodayZoneTimeSensor:
    """Build a TodayZoneTimeSensor with the given bucket and PairState."""
    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    k = pair_key(pair_state.entity_a_id, pair_state.entity_b_id)
    coordinator.data = GroupData(pairs={k: pair_state})
    coordinator.bucket_thresholds = _DEFAULT_THRESHOLDS
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = TodayZoneTimeSensor.__new__(TodayZoneTimeSensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._pair_key = k
    sensor._bucket = bucket
    sensor._sensor_key = f"today_zone_time_{bucket}"
    sensor._attr_unique_id = f"test_sensor_{bucket}"
    sensor._attr_device_info = {}
    return sensor


def _make_count_sensor(which: str, pair_state: PairState) -> UpdateCountSensor:
    """Build an UpdateCountSensor for entity 'a' or 'b'."""
    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    k = pair_key(pair_state.entity_a_id, pair_state.entity_b_id)
    coordinator.data = GroupData(pairs={k: pair_state})
    coordinator.bucket_thresholds = _DEFAULT_THRESHOLDS
    coordinator.updates_window_s = 1800.0
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = UpdateCountSensor.__new__(UpdateCountSensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._pair_key = k
    sensor._which = which
    sensor._sensor_key = f"update_count_{which}"
    sensor._attr_unique_id = f"test_sensor_count_{which}"
    sensor._attr_device_info = {}
    return sensor


# ---------------------------------------------------------------------------
# DirectionLevelSensor tests
# ---------------------------------------------------------------------------


class TestDirectionLevelSensor:
    """Test DirectionLevelSensor.native_value maps direction strings to -1/0/1."""

    def _ps(self, direction) -> PairState:
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.direction = direction
        ps.data_valid = True
        return ps

    def test_approaching_returns_minus_one(self):
        sensor = _make_sensor(DirectionLevelSensor, self._ps(DIRECTION_APPROACHING))
        assert sensor.native_value == -1

    def test_stationary_returns_zero(self):
        sensor = _make_sensor(DirectionLevelSensor, self._ps(DIRECTION_STATIONARY))
        assert sensor.native_value == 0

    def test_diverging_returns_one(self):
        sensor = _make_sensor(DirectionLevelSensor, self._ps(DIRECTION_DIVERGING))
        assert sensor.native_value == 1

    def test_none_direction_returns_none(self):
        sensor = _make_sensor(DirectionLevelSensor, self._ps(None))
        assert sensor.native_value is None

    def test_unknown_direction_string_returns_none(self):
        # An unrecognised string is not in _DIRECTION_LEVEL; .get() returns None
        sensor = _make_sensor(DirectionLevelSensor, self._ps("sideways"))
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# TodayZoneTimeSensor tests
# ---------------------------------------------------------------------------


class TestTodayZoneTimeSensor:
    """Test TodayZoneTimeSensor.native_value per bucket."""

    def _ps(self, data_valid: bool, zone_seconds: dict | None = None) -> PairState:
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = data_valid
        if zone_seconds is not None:
            ps.today_zone_seconds = zone_seconds
        return ps

    def test_still_returns_value_when_data_invalid(self):
        sensor = _make_zone_sensor(BUCKET_VERY_NEAR, self._ps(False))
        assert sensor.native_value is not None

    def test_returns_zero_when_bucket_not_in_dict(self):
        # today_zone_seconds is empty; the bucket key is absent → default 0.0
        sensor = _make_zone_sensor(BUCKET_NEAR, self._ps(True, {}))
        assert sensor.native_value == 0.0

    def test_very_near_bucket_minutes(self):
        sensor = _make_zone_sensor(BUCKET_VERY_NEAR, self._ps(True, {BUCKET_VERY_NEAR: 120.0}))
        assert sensor.native_value == 2.0  # 120 / 60

    def test_near_bucket_minutes(self):
        sensor = _make_zone_sensor(BUCKET_NEAR, self._ps(True, {BUCKET_NEAR: 300.0}))
        assert sensor.native_value == 5.0  # 300 / 60

    def test_mid_bucket_minutes(self):
        sensor = _make_zone_sensor(BUCKET_MID, self._ps(True, {BUCKET_MID: 600.0}))
        assert sensor.native_value == 10.0  # 600 / 60

    def test_far_bucket_minutes(self):
        sensor = _make_zone_sensor(BUCKET_FAR, self._ps(True, {BUCKET_FAR: 1800.0}))
        assert sensor.native_value == 30.0  # 1800 / 60

    def test_very_far_bucket_minutes(self):
        sensor = _make_zone_sensor(BUCKET_VERY_FAR, self._ps(True, {BUCKET_VERY_FAR: 3600.0}))
        assert sensor.native_value == 60.0  # 3600 / 60

    def test_rounds_to_one_decimal(self):
        # 100 s / 60 = 1.6666… → rounded to 1 decimal = 1.7
        sensor = _make_zone_sensor(BUCKET_MID, self._ps(True, {BUCKET_MID: 100.0}))
        assert sensor.native_value == round(100.0 / 60, 1)

    def test_only_requested_bucket_is_read(self):
        # Sensor for BUCKET_NEAR should ignore BUCKET_FAR data
        zone = {BUCKET_FAR: 9999.0, BUCKET_NEAR: 60.0}
        sensor = _make_zone_sensor(BUCKET_NEAR, self._ps(True, zone))
        assert sensor.native_value == 1.0  # 60 / 60

    def test_not_diagnostic(self):
        from homeassistant.const import EntityCategory

        sensor = _make_zone_sensor(BUCKET_VERY_NEAR, self._ps(True, {}))
        assert sensor.entity_category is None or sensor.entity_category != EntityCategory.DIAGNOSTIC


# ---------------------------------------------------------------------------
# UpdateCountSensor tests
# ---------------------------------------------------------------------------


class TestUpdateCountSensor:
    """Test UpdateCountSensor.native_value for each entity."""

    def _ps(self, data_valid: bool, count_a: int = 0, count_b: int = 0) -> PairState:
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = data_valid
        ps.update_count_a = count_a
        ps.update_count_b = count_b
        return ps

    def test_still_returns_value_when_data_invalid_a(self):
        sensor = _make_count_sensor("a", self._ps(False, count_a=5))
        assert sensor.native_value is not None

    def test_still_returns_value_when_data_invalid_b(self):
        sensor = _make_count_sensor("b", self._ps(False, count_b=3))
        assert sensor.native_value is not None

    def test_returns_update_count_a(self):
        sensor = _make_count_sensor("a", self._ps(True, count_a=42, count_b=7))
        assert sensor.native_value == 42

    def test_returns_update_count_b(self):
        sensor = _make_count_sensor("b", self._ps(True, count_a=42, count_b=7))
        assert sensor.native_value == 7

    def test_zero_count_a_still_returns_zero_when_valid(self):
        sensor = _make_count_sensor("a", self._ps(True, count_a=0, count_b=99))
        assert sensor.native_value == 0

    def test_zero_count_b_still_returns_zero_when_valid(self):
        sensor = _make_count_sensor("b", self._ps(True, count_a=99, count_b=0))
        assert sensor.native_value == 0

    def test_expired_window_returns_zero_for_a(self):
        from datetime import timedelta

        ps = self._ps(True, count_a=5, count_b=3)
        # Use the coordinator's window (1800s set in _make_count_sensor)
        ps.update_window_start_a = datetime.now().astimezone() - timedelta(seconds=1800 + 60)
        sensor = _make_count_sensor("a", ps)
        assert sensor.native_value == 0

    def test_active_window_returns_count_for_b(self):
        ps = self._ps(True, count_a=1, count_b=7)
        ps.update_window_start_b = datetime.now().astimezone()
        sensor = _make_count_sensor("b", ps)
        assert sensor.native_value == 7

    def test_active_window_returns_count_for_a(self):
        ps = self._ps(True, count_a=4, count_b=1)
        ps.update_window_start_a = datetime.now().astimezone()
        sensor = _make_count_sensor("a", ps)
        assert sensor.native_value == 4

    def test_expired_window_returns_zero_for_b(self):
        from datetime import timedelta

        ps = self._ps(True, count_a=2, count_b=9)
        ps.update_window_start_b = datetime.now().astimezone() - timedelta(seconds=1800 + 60)
        sensor = _make_count_sensor("b", ps)
        assert sensor.native_value == 0


# ---------------------------------------------------------------------------
# ProximityRateSensor tests
# ---------------------------------------------------------------------------


class TestProximityRateSensor:
    """Test ProximityRateSensor.native_value rate calculation."""

    def _ps(self, **kwargs) -> PairState:
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.proximity = False
        ps.proximity_since = None
        ps.proximity_duration_s = 0.0
        ps.proximity_tracking_started = None
        for k, v in kwargs.items():
            setattr(ps, k, v)
        return ps

    def _make_sensor(self, ps: PairState) -> ProximityRateSensor:
        return _make_sensor(ProximityRateSensor, ps)

    def test_still_returns_value_when_data_invalid(self):
        now = datetime.now().astimezone()
        ps = self._ps(
            data_valid=False,
            proximity_tracking_started=now - timedelta(hours=1),
        )
        sensor = self._make_sensor(ps)
        assert sensor.native_value is not None

    def test_returns_none_when_tracking_started_is_none(self):
        ps = self._ps(data_valid=True, proximity_tracking_started=None)
        sensor = self._make_sensor(ps)
        assert sensor.native_value is None

    def test_no_live_session(self):
        # Tracking started 1 hour ago; 30 min of stored proximity, not currently close.
        # Rate = 1800 / 3600 * 100 = 50.0
        now = datetime.now().astimezone()
        ps = self._ps(
            proximity_tracking_started=now - timedelta(hours=1),
            proximity_duration_s=1800.0,
            proximity=False,
        )
        sensor = self._make_sensor(ps)
        assert sensor.native_value == 50.0

    def test_live_session_adds_elapsed(self):
        # Tracking started 2 hours ago; 0 s stored; currently proximate for ~1 hour.
        # Rate ≈ 3600 / 7200 * 100 = 50.0
        now = datetime.now().astimezone()
        ps = self._ps(
            proximity_tracking_started=now - timedelta(hours=2),
            proximity_duration_s=0.0,
            proximity=True,
            proximity_since=now - timedelta(hours=1),
        )
        sensor = self._make_sensor(ps)
        value = sensor.native_value
        assert value is not None
        assert 48.0 <= value <= 52.0

    def test_capped_at_100(self):
        # Tracking started 1 hour ago but 2 hours of stored proximity — impossible in
        # practice, but the clamp must cap the result at 100.0.
        now = datetime.now().astimezone()
        ps = self._ps(
            proximity_tracking_started=now - timedelta(hours=1),
            proximity_duration_s=7200.0,
            proximity=False,
        )
        sensor = self._make_sensor(ps)
        assert sensor.native_value == 100.0

    def test_zero_proximity_duration_returns_zero(self):
        now = datetime.now().astimezone()
        ps = self._ps(
            proximity_tracking_started=now - timedelta(hours=1),
            proximity_duration_s=0.0,
            proximity=False,
        )
        sensor = self._make_sensor(ps)
        assert sensor.native_value == 0.0

    def test_tracking_started_in_future_returns_none(self):
        # tracking_started in the future gives total_s <= 0 → None
        now = datetime.now().astimezone()
        ps = self._ps(
            proximity_tracking_started=now + timedelta(seconds=10),
            proximity_duration_s=0.0,
            proximity=False,
        )
        sensor = self._make_sensor(ps)
        assert sensor.native_value is None

    def test_proximity_since_none_when_proximity_false(self):
        # proximity=False but proximity_since is set — should NOT add elapsed time
        now = datetime.now().astimezone()
        ps = self._ps(
            proximity_tracking_started=now - timedelta(hours=2),
            proximity_duration_s=3600.0,
            proximity=False,
            proximity_since=now - timedelta(hours=1),
        )
        sensor = self._make_sensor(ps)
        # 3600 / 7200 = 50.0 — proximity_since must not be added when proximity=False
        assert sensor.native_value == 50.0

    def test_clock_skew_beyond_1s_logs_warning(self, caplog):
        # tracking_started more than 1 s in the future → None returned + warning logged
        import logging

        now = datetime.now().astimezone()
        ps = self._ps(
            proximity_tracking_started=now + timedelta(seconds=5),
            proximity_duration_s=0.0,
            proximity=False,
        )
        sensor = self._make_sensor(ps)
        with caplog.at_level(logging.WARNING, logger="custom_components.entity_distance.sensor"):
            value = sensor.native_value
        assert value is None
        assert "clock skew" in caplog.text

    def test_clock_skew_under_1s_no_warning(self, caplog):
        # tracking_started 0.5 s in the future → None but no warning (sub-second jitter)
        import logging

        now = datetime.now().astimezone()
        ps = self._ps(
            proximity_tracking_started=now + timedelta(milliseconds=500),
            proximity_duration_s=0.0,
            proximity=False,
        )
        sensor = self._make_sensor(ps)
        with caplog.at_level(logging.WARNING, logger="custom_components.entity_distance.sensor"):
            value = sensor.native_value
        assert value is None
        assert "clock skew" not in caplog.text


# ---------------------------------------------------------------------------
# TodayUnaccountedTimeSensor tests
# ---------------------------------------------------------------------------


def _make_unaccounted_sensor(pair_state):
    from custom_components.entity_distance.sensor import TodayUnaccountedTimeSensor

    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    k = pair_key(pair_state.entity_a_id, pair_state.entity_b_id)
    coordinator.data = GroupData(pairs={k: pair_state})
    coordinator.bucket_thresholds = _DEFAULT_THRESHOLDS
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = TodayUnaccountedTimeSensor.__new__(TodayUnaccountedTimeSensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._pair_key = k
    sensor._sensor_key = "today_unaccounted_time"
    sensor._attr_unique_id = "test_unaccounted"
    sensor._attr_device_info = {}
    return sensor


class TestTodayUnaccountedTimeSensor:
    """Test TodayUnaccountedTimeSensor: today's elapsed seconds minus accounted bucket time."""

    def test_returns_full_elapsed_when_zone_seconds_empty(self):
        from homeassistant.util import dt as dt_util

        now = dt_util.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed_min = (now - midnight).total_seconds() / 60
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.today_zone_seconds = {}
        sensor = _make_unaccounted_sensor(ps)
        value = sensor.native_value
        assert value is not None
        assert value == pytest.approx(elapsed_min, abs=1.0)

    def test_zero_when_all_elapsed_accounted(self):
        from homeassistant.util import dt as dt_util

        now = dt_util.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed_s = (now - midnight).total_seconds()
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.today_zone_seconds = {"very_near": elapsed_s}
        sensor = _make_unaccounted_sensor(ps)
        value = sensor.native_value
        assert value is not None
        assert 0.0 <= value < 1.0

    def test_partial_account(self):
        from homeassistant.util import dt as dt_util

        now = dt_util.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed_min = (now - midnight).total_seconds() / 60
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        # 600 s = 10 min accounted across two buckets.
        ps.today_zone_seconds = {"near": 300.0, "mid": 300.0}
        sensor = _make_unaccounted_sensor(ps)
        value = sensor.native_value
        assert value is not None
        # max(0,...) clamp handles the early-morning window where elapsed < 10 min.
        expected = max(0.0, elapsed_min - 10.0)
        assert value == pytest.approx(expected, abs=1.0)

    def test_never_negative_when_overshoot(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.today_zone_seconds = {"very_near": 999_999.0}
        sensor = _make_unaccounted_sensor(ps)
        assert sensor.native_value == 0.0

    def test_returns_none_when_unavailable(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = False
        sensor = _make_unaccounted_sensor(ps)
        sensor.coordinator.last_update_success = False
        assert sensor.native_value is None

    def test_available_when_pair_invalid_but_coordinator_ok(self):
        # Sensor reports unaccounted time including invalid windows — must not
        # gate on data_valid.
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = False
        ps.today_zone_seconds = {}
        sensor = _make_unaccounted_sensor(ps)
        sensor.coordinator.last_update_success = True
        assert sensor.available is True
        assert sensor.native_value is not None

    def test_attributes_expose_tracking_started(self):
        from datetime import UTC, datetime

        ts = datetime.now(UTC)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.proximity_tracking_started = ts
        sensor = _make_unaccounted_sensor(ps)
        attrs = sensor.extra_state_attributes
        assert attrs["tracking_started"] == ts.isoformat()

    def test_attributes_empty_when_tracking_not_started(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.proximity_tracking_started = None
        sensor = _make_unaccounted_sensor(ps)
        assert sensor.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# BucketSensor tests
# ---------------------------------------------------------------------------


class TestBucketSensor:
    """Test BucketSensor.native_value zone label."""

    from custom_components.entity_distance.sensor import BucketSensor as _BucketSensor

    def _make_sensor(self, distance_m):
        from custom_components.entity_distance.sensor import BucketSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.distance_m = distance_m
        ps.data_valid = True
        return _make_sensor(BucketSensor, ps)

    def test_none_distance_returns_none(self):
        from custom_components.entity_distance.sensor import BucketSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.distance_m = None
        ps.data_valid = True
        sensor = _make_sensor(BucketSensor, ps)
        assert sensor.native_value is None

    def test_very_near(self):
        from custom_components.entity_distance.const import BUCKET_VERY_NEAR

        sensor = self._make_sensor(50)
        assert sensor.native_value == BUCKET_VERY_NEAR

    def test_very_far(self):
        from custom_components.entity_distance.const import BUCKET_VERY_FAR

        sensor = self._make_sensor(50000)
        assert sensor.native_value == BUCKET_VERY_FAR


# ---------------------------------------------------------------------------
# ProximityDurationSensor — additional edge cases
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# DistanceSensor native_value + extra_state_attributes
# ---------------------------------------------------------------------------


class TestDistanceSensor:
    from custom_components.entity_distance.sensor import DistanceSensor as _DS

    def _make(self, distance_m):
        from custom_components.entity_distance.sensor import DistanceSensor

        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.distance_m = distance_m
        ps.data_valid = True
        return _make_sensor(DistanceSensor, ps)

    def test_returns_distance_m(self):
        sensor = self._make(250.0)
        assert sensor.native_value == 250.0

    def test_returns_none_when_no_distance(self):
        sensor = self._make(None)
        assert sensor.native_value is None

    def test_extra_attrs_contain_entity_ids(self):
        sensor = self._make(100.0)
        attrs = sensor.extra_state_attributes
        assert attrs["entity_a"] == "person.alice"
        assert attrs["entity_b"] == "person.bob"


# ---------------------------------------------------------------------------
# ClosingSpeedSensor native_value
# ---------------------------------------------------------------------------


class TestClosingSpeedSensor:
    def _make(self, closing_speed_kmh):
        from custom_components.entity_distance.sensor import ClosingSpeedSensor

        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.closing_speed_kmh = closing_speed_kmh
        ps.data_valid = True
        return _make_sensor(ClosingSpeedSensor, ps)

    def test_returns_rounded_speed(self):
        sensor = self._make(55.555)
        assert sensor.native_value == round(55.555, 1)

    def test_returns_none_when_no_speed(self):
        sensor = self._make(None)
        assert sensor.native_value is None

    def test_zero_speed(self):
        sensor = self._make(0.0)
        assert sensor.native_value == 0.0


# ---------------------------------------------------------------------------
# EtaSensor native_value
# ---------------------------------------------------------------------------


class TestEtaSensor:
    def _make(self, eta_minutes):
        from custom_components.entity_distance.sensor import EtaSensor

        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.eta_minutes = eta_minutes
        ps.data_valid = True
        return _make_sensor(EtaSensor, ps)

    def test_returns_rounded_eta(self):
        sensor = self._make(12.345)
        assert sensor.native_value == round(12.345, 1)

    def test_returns_none_when_no_eta(self):
        sensor = self._make(None)
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# GpsAccuracySensor native_value
# ---------------------------------------------------------------------------


def _make_gps_sensor(which: str, pair_state: PairState):
    from custom_components.entity_distance.sensor import GpsAccuracySensor

    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    k = pair_key(pair_state.entity_a_id, pair_state.entity_b_id)
    coordinator.data = GroupData(pairs={k: pair_state})
    coordinator.bucket_thresholds = _DEFAULT_THRESHOLDS
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = GpsAccuracySensor.__new__(GpsAccuracySensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._pair_key = k
    sensor._which = which
    sensor._sensor_key = f"gps_accuracy_{which}"
    sensor._attr_unique_id = f"test_gps_{which}"
    sensor._attr_device_info = {}
    return sensor


class TestGpsAccuracySensor:
    def test_returns_accuracy_a(self):
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        ps.accuracy_a = 15.0
        ps.accuracy_b = 30.0
        sensor = _make_gps_sensor("a", ps)
        assert sensor.native_value == pytest.approx(15.0)

    def test_returns_accuracy_b(self):
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        ps.accuracy_a = 15.0
        ps.accuracy_b = 30.0
        sensor = _make_gps_sensor("b", ps)
        assert sensor.native_value == pytest.approx(30.0)

    def test_rounds_to_one_decimal(self):
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        ps.accuracy_a = 3.9049
        sensor = _make_gps_sensor("a", ps)
        assert sensor.native_value == pytest.approx(3.9)

    def test_returns_none_when_no_accuracy(self):
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        ps.accuracy_a = None
        sensor = _make_gps_sensor("a", ps)
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# LastUpdateSensor native_value
# ---------------------------------------------------------------------------


def _make_last_update_sensor(which: str, pair_state: PairState):
    from custom_components.entity_distance.sensor import LastUpdateSensor

    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    k = pair_key(pair_state.entity_a_id, pair_state.entity_b_id)
    coordinator.data = GroupData(pairs={k: pair_state})
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = LastUpdateSensor.__new__(LastUpdateSensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._pair_key = k
    sensor._which = which
    sensor._sensor_key = f"last_update_{which}"
    sensor._attr_unique_id = f"test_last_update_{which}"
    sensor._attr_device_info = {}
    return sensor


class TestLastUpdateSensor:
    def test_returns_last_update_a(self):
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        now = datetime.now().astimezone()
        ps.last_update_a = now
        sensor = _make_last_update_sensor("a", ps)
        assert sensor.native_value == now

    def test_returns_last_update_b(self):
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        now = datetime.now().astimezone()
        ps.last_update_b = now
        sensor = _make_last_update_sensor("b", ps)
        assert sensor.native_value == now

    def test_returns_none_when_not_set(self):
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        sensor = _make_last_update_sensor("a", ps)
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# LastSeenTogetherSensor native_value
# ---------------------------------------------------------------------------


class TestLastSeenTogetherSensor:
    def _make(self, last_seen):
        from custom_components.entity_distance.sensor import LastSeenTogetherSensor

        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        ps.last_seen_together = last_seen
        return _make_sensor(LastSeenTogetherSensor, ps)

    def test_returns_timestamp(self):
        now = datetime.now().astimezone()
        sensor = self._make(now)
        assert sensor.native_value == now

    def test_returns_none_when_not_set(self):
        sensor = self._make(None)
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# TodayProximityTimeSensor native_value
# ---------------------------------------------------------------------------


class TestTodayProximityTimeSensor:
    def _make(self, data_valid, today_proximity_seconds):
        from custom_components.entity_distance.sensor import TodayProximityTimeSensor

        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = data_valid
        ps.today_proximity_seconds = today_proximity_seconds
        return _make_sensor(TodayProximityTimeSensor, ps)

    def test_still_returns_value_when_data_invalid(self):
        sensor = self._make(False, 600.0)
        assert sensor.native_value is not None

    def test_returns_minutes(self):
        sensor = self._make(True, 600.0)
        assert sensor.native_value == 10.0

    def test_zero_returns_zero(self):
        sensor = self._make(True, 0.0)
        assert sensor.native_value == 0.0


# ---------------------------------------------------------------------------
# ProximityTrackingStartedSensor native_value
# ---------------------------------------------------------------------------


class TestProximityTrackingStartedSensor:
    def _make(self, tracking_started):
        from custom_components.entity_distance.sensor import (
            ProximityTrackingStartedSensor,
        )

        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.data_valid = True
        ps.proximity_tracking_started = tracking_started
        return _make_sensor(ProximityTrackingStartedSensor, ps)

    def test_returns_datetime(self):
        now = datetime.now().astimezone()
        sensor = self._make(now)
        assert sensor.native_value == now

    def test_returns_none_when_not_set(self):
        sensor = self._make(None)
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# MinDistanceSensor native_value
# ---------------------------------------------------------------------------


class TestMinDistanceSensor:
    def _make(self, min_distance_m):
        from custom_components.entity_distance.models import GroupData
        from custom_components.entity_distance.sensor import MinDistanceSensor

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.data = GroupData(min_distance_m=min_distance_m)
        entry = MagicMock()
        entry.entry_id = "test_entry"
        sensor = MinDistanceSensor.__new__(MinDistanceSensor)
        sensor.coordinator = coordinator
        sensor._entry = entry
        sensor._attr_unique_id = "test_min_distance"
        sensor._attr_device_info = {}
        return sensor

    def test_returns_min_distance(self):
        sensor = self._make(123.4)
        assert sensor.native_value == 123.4

    def test_returns_none_when_no_valid_pairs(self):
        sensor = self._make(None)
        assert sensor.native_value is None


# ---------------------------------------------------------------------------
# TodayZoneTimeSensor extra_state_attributes
# ---------------------------------------------------------------------------


class TestTodayZoneTimeSensorAttributes:
    def test_very_near_has_range_from_zero(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.today_zone_seconds = {}
        sensor = _make_zone_sensor(BUCKET_VERY_NEAR, ps)
        attrs = sensor.extra_state_attributes
        assert attrs.get("range_from_m") == 0
        assert "range_to_m" in attrs

    def test_near_has_lower_bound(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.today_zone_seconds = {}
        sensor = _make_zone_sensor(BUCKET_NEAR, ps)
        attrs = sensor.extra_state_attributes
        assert "range_from_m" in attrs
        assert "range_to_m" in attrs

    def test_very_far_has_range_from_far_threshold(self):
        # NEW-2: very_far is not a threshold key (idx == -1). Its lower bound is the
        # far threshold; range_to_m is absent (unbounded tail).
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.today_zone_seconds = {}
        sensor = _make_zone_sensor(BUCKET_VERY_FAR, ps)
        thresholds = sensor.coordinator.bucket_thresholds
        far_threshold = thresholds[list(thresholds.keys())[-1]]
        attrs = sensor.extra_state_attributes
        assert attrs["range_from_m"] == far_threshold
        assert "range_to_m" not in attrs

    def test_unknown_bucket_omits_range_from(self):
        # Bucket not present in coordinator.bucket_thresholds — idx falls to -1,
        # which is the very_far case: range_from_m is the far threshold (lower bound
        # of the unbounded tail), range_to_m stays absent (no upper bound).
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.today_zone_seconds = {}
        sensor = _make_zone_sensor("nonexistent_bucket", ps)
        attrs = sensor.extra_state_attributes
        assert attrs["range_from_m"] == 20000
        assert "range_to_m" not in attrs

    def test_bucket_with_none_upper_omits_range_to(self):
        # Bucket present but threshold value is None (open-ended tail) — range_to_m
        # must be omitted, range_from_m still set.
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.today_zone_seconds = {}
        sensor = _make_zone_sensor(BUCKET_NEAR, ps)
        sensor.coordinator = MagicMock()
        sensor.coordinator.bucket_thresholds = {
            BUCKET_VERY_NEAR: 100.0,
            BUCKET_NEAR: None,  # open-ended
        }
        attrs = sensor.extra_state_attributes
        assert "range_from_m" in attrs
        assert "range_to_m" not in attrs


# ---------------------------------------------------------------------------
# ProximityDurationSensor — additional edge cases
# ---------------------------------------------------------------------------


class TestProximityDurationSensorEdgeCases:
    """Additional edge cases for ProximityDurationSensor."""

    def test_proximity_true_but_proximity_since_none_uses_only_stored(self):
        # proximity=True but proximity_since=None: can't add live elapsed → use stored only
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.proximity_tracking_started = datetime.now().astimezone()
        ps.proximity = True
        ps.proximity_since = None
        ps.proximity_duration_s = 120.0  # 2 min stored
        sensor = _make_sensor(ProximityDurationSensor, ps)
        assert sensor.native_value == 2.0

    def test_rounds_to_one_decimal(self):
        # 100 s / 60 = 1.6666... → 1.7
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.proximity_tracking_started = datetime.now().astimezone()
        ps.proximity = False
        ps.proximity_since = None
        ps.proximity_duration_s = 100.0
        sensor = _make_sensor(ProximityDurationSensor, ps)
        assert sensor.native_value == round(100.0 / 60, 1)


# ---------------------------------------------------------------------------
# Sensors tested via _make_extra_sensor helper (new-style, no duplicate names)
# DirectionSensor, EntityStateSensor, ProximityTrackingStartedSensor
# ---------------------------------------------------------------------------


def _make_extra_sensor(cls, ps: PairState, **kwargs):
    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    k = pair_key(ps.entity_a_id, ps.entity_b_id)
    coordinator.data = GroupData(pairs={k: ps})
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
    for attr, val in kwargs.items():
        setattr(sensor, attr, val)
    return sensor


class TestGraceWindowDisplay:
    """During the display grace window, sensors show last value; base available True."""

    def test_shows_last_value_within_grace_despite_invalid(self):
        from custom_components.entity_distance.sensor import DistanceSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.distance_m = 123.4
        ps.data_valid = False  # invalid, but within grace
        sensor = _make_extra_sensor(DistanceSensor, ps)
        sensor.coordinator.is_within_grace.return_value = True
        sensor.coordinator.last_update_success = True
        assert sensor.native_value == 123.4
        assert sensor.available is True

    def test_unknown_when_invalid_and_past_grace(self):
        from custom_components.entity_distance.sensor import DistanceSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.distance_m = 123.4
        ps.data_valid = False
        sensor = _make_extra_sensor(DistanceSensor, ps)
        sensor.coordinator.is_within_grace.return_value = False
        sensor.coordinator.last_update_success = True
        assert sensor.native_value is None
        assert sensor.available is False


class TestDirectionSensor:
    def test_returns_direction(self):
        from custom_components.entity_distance.sensor import DirectionSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.direction = DIRECTION_APPROACHING
        ps.data_valid = True
        sensor = _make_extra_sensor(DirectionSensor, ps)
        assert sensor.native_value == DIRECTION_APPROACHING

    def test_returns_none_when_no_direction(self):
        from custom_components.entity_distance.sensor import DirectionSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.direction = None
        ps.data_valid = True
        sensor = _make_extra_sensor(DirectionSensor, ps)
        assert sensor.native_value is None

    def test_returns_none_when_data_invalid(self):
        from custom_components.entity_distance.sensor import DirectionSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.direction = DIRECTION_APPROACHING
        ps.data_valid = False
        sensor = _make_extra_sensor(DirectionSensor, ps)
        assert sensor.native_value is None


class TestClosingSpeedSensorExtra:
    def test_returns_rounded_speed(self):
        from custom_components.entity_distance.sensor import ClosingSpeedSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.closing_speed_kmh = 12.3456
        ps.data_valid = True
        sensor = _make_extra_sensor(ClosingSpeedSensor, ps)
        assert sensor.native_value == 12.3

    def test_returns_none_when_no_speed(self):
        from custom_components.entity_distance.sensor import ClosingSpeedSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.closing_speed_kmh = None
        ps.data_valid = True
        sensor = _make_extra_sensor(ClosingSpeedSensor, ps)
        assert sensor.native_value is None

    def test_returns_none_when_data_invalid(self):
        from custom_components.entity_distance.sensor import ClosingSpeedSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.closing_speed_kmh = 5.0
        ps.data_valid = False
        sensor = _make_extra_sensor(ClosingSpeedSensor, ps)
        assert sensor.native_value is None


class TestEtaSensorExtra:
    def test_returns_rounded_eta(self):
        from custom_components.entity_distance.sensor import EtaSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.eta_minutes = 7.777
        ps.data_valid = True
        sensor = _make_extra_sensor(EtaSensor, ps)
        assert sensor.native_value == 7.8

    def test_returns_none_when_no_eta(self):
        from custom_components.entity_distance.sensor import EtaSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.eta_minutes = None
        ps.data_valid = True
        sensor = _make_extra_sensor(EtaSensor, ps)
        assert sensor.native_value is None

    def test_returns_none_when_data_invalid(self):
        from custom_components.entity_distance.sensor import EtaSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.eta_minutes = 3.0
        ps.data_valid = False
        sensor = _make_extra_sensor(EtaSensor, ps)
        assert sensor.native_value is None

    def test_eta_status_approaching(self):
        from custom_components.entity_distance.sensor import EtaSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.eta_minutes = 5.0
        ps.data_valid = True
        sensor = _make_extra_sensor(EtaSensor, ps)
        assert sensor.extra_state_attributes["eta_status"] == "approaching"

    def test_eta_status_stationary(self):
        from custom_components.entity_distance.sensor import EtaSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.eta_minutes = None
        ps.direction = "stationary"
        ps.data_valid = True
        sensor = _make_extra_sensor(EtaSensor, ps)
        assert sensor.extra_state_attributes["eta_status"] == "stationary"

    def test_eta_status_not_approaching(self):
        from custom_components.entity_distance.sensor import EtaSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.eta_minutes = None
        ps.direction = "diverging"
        ps.data_valid = True
        sensor = _make_extra_sensor(EtaSensor, ps)
        assert sensor.extra_state_attributes["eta_status"] == "not_approaching"


class TestGpsAccuracySensorExtra:
    def test_returns_accuracy_a(self):
        from custom_components.entity_distance.sensor import GpsAccuracySensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.accuracy_a = 12.5
        ps.accuracy_b = 30.0
        sensor = _make_extra_sensor(GpsAccuracySensor, ps, _which="a")
        assert sensor.native_value == pytest.approx(12.5)

    def test_returns_accuracy_b(self):
        from custom_components.entity_distance.sensor import GpsAccuracySensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.accuracy_a = 12.5
        ps.accuracy_b = 30.0
        sensor = _make_extra_sensor(GpsAccuracySensor, ps, _which="b")
        assert sensor.native_value == pytest.approx(30.0)

    def test_returns_none_when_accuracy_missing(self):
        from custom_components.entity_distance.sensor import GpsAccuracySensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.accuracy_a = None
        sensor = _make_extra_sensor(GpsAccuracySensor, ps, _which="a")
        assert sensor.native_value is None

    def test_rounds_to_one_decimal(self):
        from custom_components.entity_distance.sensor import GpsAccuracySensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.accuracy_a = 3.9049
        sensor = _make_extra_sensor(GpsAccuracySensor, ps, _which="a")
        assert sensor.native_value == pytest.approx(3.9)


class TestLastUpdateSensorExtra:
    def test_returns_last_update_a(self):
        from custom_components.entity_distance.sensor import LastUpdateSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ts = datetime.now().astimezone()
        ps.last_update_a = ts
        sensor = _make_extra_sensor(LastUpdateSensor, ps, _which="a")
        assert sensor.native_value == ts

    def test_returns_last_update_b(self):
        from custom_components.entity_distance.sensor import LastUpdateSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ts = datetime.now().astimezone()
        ps.last_update_b = ts
        sensor = _make_extra_sensor(LastUpdateSensor, ps, _which="b")
        assert sensor.native_value == ts

    def test_returns_none_when_no_update(self):
        from custom_components.entity_distance.sensor import LastUpdateSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        sensor = _make_extra_sensor(LastUpdateSensor, ps, _which="a")
        assert sensor.native_value is None


class TestEntityStateSensor:
    def test_returns_state_string(self):
        from custom_components.entity_distance.sensor import EntityStateSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        sensor = _make_extra_sensor(EntityStateSensor, ps, _tracked_entity_id="person.a")
        hass = MagicMock()
        state_mock = MagicMock()
        state_mock.state = "home"
        hass.states.get.return_value = state_mock
        sensor.hass = hass
        assert sensor.native_value == "home"

    def test_returns_none_when_entity_missing(self):
        from custom_components.entity_distance.sensor import EntityStateSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        sensor = _make_extra_sensor(EntityStateSensor, ps, _tracked_entity_id="person.a")
        hass = MagicMock()
        hass.states.get.return_value = None
        sensor.hass = hass
        assert sensor.native_value is None


class TestProximityTrackingStartedSensorExtra:
    def test_returns_none_when_not_set(self):
        from custom_components.entity_distance.sensor import (
            ProximityTrackingStartedSensor,
        )

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        sensor = _make_extra_sensor(ProximityTrackingStartedSensor, ps)
        assert sensor.native_value is None

    def test_returns_timestamp(self):
        from custom_components.entity_distance.sensor import (
            ProximityTrackingStartedSensor,
        )

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ts = datetime.now().astimezone()
        ps.proximity_tracking_started = ts
        sensor = _make_extra_sensor(ProximityTrackingStartedSensor, ps)
        assert sensor.native_value == ts


# ---------------------------------------------------------------------------
# SettingsSensor tests
# ---------------------------------------------------------------------------


class TestSettingsSensor:
    def _make(self):
        from custom_components.entity_distance.sensor import SettingsSensor

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.last_update_success = True
        coordinator.settings_snapshot = {
            "proximity_zone": "very_near",
            "proximity_threshold_m": 200,
            "debounce_s": 10,
            "max_accuracy_m": 150,
            "max_speed_kmh": 1000,
            "resync_silence_s": 600,
            "resync_hold_s": 60,
            "min_updates_reliable": 3,
            "updates_window_s": 1800,
            "require_reliable": False,
            "zone_very_near_m": 200,
            "zone_near_m": 1000,
            "zone_mid_m": 5000,
            "zone_far_m": 20000,
        }
        entry = MagicMock()
        entry.entry_id = "test"
        sensor = SettingsSensor.__new__(SettingsSensor)
        sensor.coordinator = coordinator
        sensor._entry = entry
        sensor._attr_unique_id = "test_settings"
        sensor._attr_device_info = {}
        return sensor

    def test_state_summary(self):
        sensor = self._make()
        # Format: "proximity=<zone> · zones vn/n/m/f m · debounce s"
        assert (
            sensor.native_value
            == "proximity ≤ 200m (very_near) · zones 200/1000/5000/20000m · debounce 10s"
        )

    def test_attributes_carry_all_settings(self):
        sensor = self._make()
        attrs = sensor.extra_state_attributes
        assert attrs["proximity_zone"] == "very_near"
        assert attrs["zone_very_near_m"] == 200
        assert attrs["zone_far_m"] == 20000
        assert attrs["require_reliable"] is False
        # All 13 keys present.
        assert len(attrs) == 14

    def test_unavailable_when_coordinator_failed(self):
        sensor = self._make()
        sensor.coordinator.last_update_success = False
        assert sensor.available is False


class TestAsyncSetupEntrySensor:
    """Test sensor.py async_setup_entry zone-pair branching."""

    @pytest.mark.asyncio
    async def test_zone_pair_gets_only_three_sensors(self):
        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.sensor import async_setup_entry

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.entities = ["zone.home", "zone.work"]
        coordinator.data = MagicMock()

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass = MagicMock()
        hass.states.get.return_value = None
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        mock_add = MagicMock(side_effect=lambda entities: added.extend(entities))

        await async_setup_entry(hass, entry, mock_add)

        types = [type(e).__name__ for e in added]
        # Zone-zone pair: 7 per-pair sensors (Distance/Bucket/BucketLevel/AltitudeSensor×2/AltitudeDeltaSensor/Settings)
        # plus 1 group-level Settings → 8 total, 2 of them SettingsSensor.
        assert set(types) == {
            "DistanceSensor",
            "BucketSensor",
            "BucketLevelSensor",
            "AltitudeSensor",
            "AltitudeDeltaSensor",
            "SettingsSensor",
        }
        assert len(added) == 8
        assert sum(1 for t in types if t == "SettingsSensor") == 2

    @pytest.mark.asyncio
    async def test_person_pair_gets_full_sensor_set(self):
        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.sensor import async_setup_entry

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.entities = ["person.alice", "person.bob"]
        coordinator.data = MagicMock()

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass = MagicMock()
        hass.states.get.return_value = None
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        mock_add = MagicMock(side_effect=lambda entities: added.extend(entities))

        await async_setup_entry(hass, entry, mock_add)

        types = [type(e).__name__ for e in added]
        assert "EntityStateSensor" in types
        assert "ClosingSpeedSensor" in types
        assert "TodayZoneTimeSensor" in types
        assert "AltitudeSensor" in types
        assert "AltitudeDeltaSensor" in types

    @pytest.mark.asyncio
    async def test_three_entities_get_group_sensor(self):
        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.sensor import async_setup_entry

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.entities = ["person.alice", "person.bob", "person.carol"]
        coordinator.data = MagicMock()

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass = MagicMock()
        hass.states.get.return_value = None
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        mock_add = MagicMock(side_effect=lambda entities: added.extend(entities))

        await async_setup_entry(hass, entry, mock_add)

        types = [type(e).__name__ for e in added]
        assert "MinDistanceSensor" in types

    @pytest.mark.asyncio
    async def test_two_entities_no_group_sensor(self):
        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.sensor import async_setup_entry

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.entities = ["person.alice", "person.bob"]
        coordinator.data = MagicMock()

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass = MagicMock()
        hass.states.get.return_value = None
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        mock_add = MagicMock(side_effect=lambda entities: added.extend(entities))

        await async_setup_entry(hass, entry, mock_add)

        types = [type(e).__name__ for e in added]
        assert "MinDistanceSensor" not in types

    @pytest.mark.asyncio
    async def test_friendly_name_uses_state_name_when_available(self):
        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.sensor import async_setup_entry

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.entities = ["person.alice", "person.bob"]
        coordinator.data = MagicMock()

        entry = MagicMock()
        entry.entry_id = "test_entry"

        def _get_state(eid):
            s = MagicMock()
            s.name = "Alice Smith" if "alice" in eid else "Bob Jones"
            return s

        hass = MagicMock()
        hass.states.get.side_effect = _get_state
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        await async_setup_entry(hass, entry, lambda entities: added.extend(entities))
        assert len(added) > 0


class TestAltitudeSensor:
    def _make(self, which: str, alt_a=None, alt_b=None, data_valid=True):
        from custom_components.entity_distance.sensor import AltitudeSensor

        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.altitude_a_m = alt_a
        ps.altitude_b_m = alt_b
        ps.data_valid = data_valid
        sensor = _make_sensor(AltitudeSensor, ps)
        sensor._which = which
        sensor._attr_name = f"Altitude ({which})"
        return sensor

    def test_native_value_a(self):
        sensor = self._make("a", alt_a=42.5)
        assert sensor.native_value == pytest.approx(42.5)

    def test_native_value_b(self):
        sensor = self._make("b", alt_b=100.0)
        assert sensor.native_value == pytest.approx(100.0)

    def test_rounds_to_one_decimal(self):
        sensor = self._make("a", alt_a=36.0101038187096)
        assert sensor.native_value == pytest.approx(36.0)

    def test_none_when_altitude_missing(self):
        sensor = self._make("a", alt_a=None)
        assert sensor.native_value is None

    def test_none_when_not_show_value(self):
        sensor = self._make("a", alt_a=42.5, data_valid=False)
        assert sensor.native_value is None

    def test_zero_altitude_is_valid(self):
        sensor = self._make("a", alt_a=0.0)
        assert sensor.native_value == pytest.approx(0.0)

    def test_negative_altitude(self):
        sensor = self._make("a", alt_a=-28.5)
        assert sensor.native_value == pytest.approx(-28.5)

    def test_extra_attrs_has_entities(self):
        sensor = self._make("a", alt_a=42.5)
        attrs = sensor.extra_state_attributes
        assert attrs["entity_a"] == "person.alice"
        assert attrs["entity_b"] == "person.bob"


class TestAltitudeDeltaSensor:
    def _make(self, delta=None, alt_a=None, alt_b=None, data_valid=True):
        from custom_components.entity_distance.sensor import AltitudeDeltaSensor

        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.altitude_delta_m = delta
        ps.altitude_a_m = alt_a
        ps.altitude_b_m = alt_b
        ps.data_valid = data_valid
        return _make_sensor(AltitudeDeltaSensor, ps)

    def test_positive_delta(self):
        assert self._make(delta=8.0).native_value == pytest.approx(8.0)

    def test_negative_delta(self):
        assert self._make(delta=-8.0).native_value == pytest.approx(-8.0)

    def test_zero_delta(self):
        assert self._make(delta=0.0).native_value == pytest.approx(0.0)

    def test_rounds_to_one_decimal(self):
        assert self._make(delta=-28.9898961812904).native_value == pytest.approx(-29.0)

    def test_none_when_delta_none(self):
        assert self._make(delta=None).native_value is None

    def test_none_when_not_show_value(self):
        assert self._make(delta=8.0, data_valid=False).native_value is None

    def test_extra_attrs_has_entities(self):
        attrs = self._make(delta=8.0).extra_state_attributes
        assert attrs["entity_a"] == "person.alice"
        assert attrs["entity_b"] == "person.bob"

    def test_extra_attrs_has_threshold(self):
        from custom_components.entity_distance.const import DEFAULT_ALTITUDE_ALIGNED_THRESHOLD_M

        attrs = self._make(delta=8.0).extra_state_attributes
        assert attrs["altitude_threshold_m"] == DEFAULT_ALTITUDE_ALIGNED_THRESHOLD_M

    def test_extra_attrs_altitude_a_b_when_show_value(self):
        attrs = self._make(delta=8.0, alt_a=42.0, alt_b=50.0).extra_state_attributes
        assert attrs["altitude_a_m"] == pytest.approx(42.0)
        assert attrs["altitude_b_m"] == pytest.approx(50.0)

    def test_extra_attrs_altitude_a_b_none_when_not_show_value(self):
        attrs = self._make(
            delta=8.0, alt_a=42.0, alt_b=50.0, data_valid=False
        ).extra_state_attributes
        assert "altitude_a_m" not in attrs
        assert "altitude_b_m" not in attrs

    def test_extra_attrs_altitude_a_b_none_values(self):
        attrs = self._make(delta=None, alt_a=None, alt_b=None).extra_state_attributes
        assert attrs["altitude_a_m"] is None
        assert attrs["altitude_b_m"] is None


class TestGpsSpeedSensor:
    def _make(self, which: str, speed_a=None, speed_b=None, data_valid=True):
        from custom_components.entity_distance.sensor import GpsSpeedSensor

        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.speed_a_kmh = speed_a
        ps.speed_b_kmh = speed_b
        ps.data_valid = data_valid
        sensor = _make_sensor(GpsSpeedSensor, ps)
        sensor._which = which
        sensor._attr_name = f"GPS Speed ({which})"
        return sensor

    def test_native_value_a(self):
        assert self._make("a", speed_a=50.0).native_value == pytest.approx(50.0)

    def test_native_value_b(self):
        assert self._make("b", speed_b=30.0).native_value == pytest.approx(30.0)

    def test_rounds_to_one_decimal(self):
        assert self._make("a", speed_a=12.345).native_value == pytest.approx(12.3)

    def test_none_when_not_available(self):
        assert self._make("a", speed_a=50.0, data_valid=False).native_value is None

    def test_none_when_speed_absent(self):
        assert self._make("a", speed_a=None).native_value is None

    def test_entity_category_diagnostic(self):
        from homeassistant.const import EntityCategory

        sensor = self._make("a", speed_a=5.0)
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC


class TestGpsHeadingSensor:
    def _make(self, which: str, heading_a=None, heading_b=None, data_valid=True):
        from custom_components.entity_distance.sensor import GpsHeadingSensor

        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.heading_a_deg = heading_a
        ps.heading_b_deg = heading_b
        ps.data_valid = data_valid
        sensor = _make_sensor(GpsHeadingSensor, ps)
        sensor._which = which
        sensor._attr_name = f"GPS Heading ({which})"
        return sensor

    def test_native_value_a(self):
        assert self._make("a", heading_a=270.0).native_value == 270

    def test_native_value_b(self):
        assert self._make("b", heading_b=90.0).native_value == 90

    def test_rounds_to_integer(self):
        assert self._make("a", heading_a=237.6).native_value == 238

    def test_360_normalizes_to_0(self):
        assert self._make("a", heading_a=359.6).native_value == 0

    def test_none_when_not_available(self):
        assert self._make("a", heading_a=270.0, data_valid=False).native_value is None

    def test_none_when_heading_absent(self):
        assert self._make("a", heading_a=None).native_value is None

    def test_entity_category_diagnostic(self):
        from homeassistant.const import EntityCategory

        sensor = self._make("a", heading_a=270.0)
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC


class TestGpsVerticalAccuracySensor:
    def _make(self, which: str, vacc_a=None, vacc_b=None, data_valid=True):
        from custom_components.entity_distance.sensor import GpsVerticalAccuracySensor

        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.vertical_accuracy_a_m = vacc_a
        ps.vertical_accuracy_b_m = vacc_b
        ps.data_valid = data_valid
        sensor = _make_sensor(GpsVerticalAccuracySensor, ps)
        sensor._which = which
        sensor._attr_name = f"GPS Vertical Accuracy ({which})"
        return sensor

    def test_native_value_a(self):
        assert self._make("a", vacc_a=8.0).native_value == pytest.approx(8.0)

    def test_native_value_b(self):
        assert self._make("b", vacc_b=12.0).native_value == pytest.approx(12.0)

    def test_rounds_to_one_decimal(self):
        assert self._make("a", vacc_a=84.049).native_value == pytest.approx(84.0)

    def test_none_when_not_available(self):
        assert self._make("a", vacc_a=8.0, data_valid=False).native_value is None

    def test_none_when_vacc_absent(self):
        assert self._make("a", vacc_a=None).native_value is None

    def test_entity_category_diagnostic(self):
        from homeassistant.const import EntityCategory

        sensor = self._make("a", vacc_a=8.0)
        assert sensor.entity_category == EntityCategory.DIAGNOSTIC
