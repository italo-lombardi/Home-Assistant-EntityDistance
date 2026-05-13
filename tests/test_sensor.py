"""Tests for sensor entities."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock

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
from custom_components.entity_distance.models import PairData, PairState
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
        (1000, BUCKET_MID, 3),
        (5000, BUCKET_FAR, 4),
        (20000, BUCKET_VERY_FAR, 5),
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
        sensor = self._make_sensor(1000)
        assert sensor.native_value == 3

    def test_far_returns_4(self):
        sensor = self._make_sensor(5000)
        assert sensor.native_value == 4

    def test_very_far_returns_5(self):
        sensor = self._make_sensor(20000)
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

    def test_returns_none_when_data_invalid(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = False
        sensor = self._make_sensor(ps)
        assert sensor.native_value is None

    def test_no_live_session_returns_stored_minutes(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
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
    coordinator.data = PairData(pair=pair_state)
    coordinator.bucket_thresholds = _DEFAULT_THRESHOLDS
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = TodayZoneTimeSensor.__new__(TodayZoneTimeSensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._bucket = bucket
    sensor._sensor_key = f"today_zone_time_{bucket}"
    sensor._attr_unique_id = f"test_sensor_{bucket}"
    sensor._attr_device_info = {}
    return sensor


def _make_count_sensor(which: str, pair_state: PairState) -> UpdateCountSensor:
    """Build an UpdateCountSensor for entity 'a' or 'b'."""
    coordinator = MagicMock()
    coordinator.data = PairData(pair=pair_state)
    coordinator.bucket_thresholds = _DEFAULT_THRESHOLDS
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = UpdateCountSensor.__new__(UpdateCountSensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
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

    def test_returns_none_when_data_invalid(self):
        sensor = _make_zone_sensor(BUCKET_VERY_NEAR, self._ps(False))
        assert sensor.native_value is None

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

    def test_returns_none_when_data_invalid_a(self):
        sensor = _make_count_sensor("a", self._ps(False, count_a=5))
        assert sensor.native_value is None

    def test_returns_none_when_data_invalid_b(self):
        sensor = _make_count_sensor("b", self._ps(False, count_b=3))
        assert sensor.native_value is None

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

    def test_returns_none_when_data_invalid(self):
        now = datetime.now().astimezone()
        ps = self._ps(
            data_valid=False,
            proximity_tracking_started=now - timedelta(hours=1),
        )
        sensor = self._make_sensor(ps)
        assert sensor.native_value is None

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


# ---------------------------------------------------------------------------
# TodayUnaccountedTimeSensor tests
# ---------------------------------------------------------------------------


def _make_unaccounted_sensor(pair_state):
    from custom_components.entity_distance.sensor import TodayUnaccountedTimeSensor
    coordinator = MagicMock()
    coordinator.data = PairData(pair=pair_state)
    coordinator.bucket_thresholds = _DEFAULT_THRESHOLDS
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = TodayUnaccountedTimeSensor.__new__(TodayUnaccountedTimeSensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._sensor_key = "today_unaccounted_time"
    sensor._attr_unique_id = "test_unaccounted"
    sensor._attr_device_info = {}
    return sensor


class TestTodayUnaccountedTimeSensor:
    """Test TodayUnaccountedTimeSensor gap calculation."""

    def test_returns_none_when_prev_calc_time_is_none(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.prev_calc_time = None
        sensor = _make_unaccounted_sensor(ps)
        assert sensor.native_value is None

    def test_recent_calc_returns_small_gap(self):
        # prev_calc_time 30 seconds ago → gap ≈ 0.5 min
        now = datetime.now().astimezone()
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.prev_calc_time = now - timedelta(seconds=30)
        sensor = _make_unaccounted_sensor(ps)
        value = sensor.native_value
        assert value is not None
        assert 0.0 <= value <= 1.0

    def test_long_gap_returns_expected_minutes(self):
        # prev_calc_time 60 minutes ago → gap ≈ 60 min
        now = datetime.now().astimezone()
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.prev_calc_time = now - timedelta(minutes=60)
        sensor = _make_unaccounted_sensor(ps)
        value = sensor.native_value
        assert value is not None
        assert 59.0 <= value <= 61.0

    def test_gap_never_negative(self):
        # prev_calc_time slightly in the future (clock drift) → max(gap, 0) = 0
        now = datetime.now().astimezone()
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.prev_calc_time = now + timedelta(seconds=5)
        sensor = _make_unaccounted_sensor(ps)
        assert sensor.native_value == 0.0


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


class TestProximityDurationSensorEdgeCases:
    """Additional edge cases for ProximityDurationSensor."""

    def test_proximity_true_but_proximity_since_none_uses_only_stored(self):
        # proximity=True but proximity_since=None: can't add live elapsed → use stored only
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.proximity = True
        ps.proximity_since = None
        ps.proximity_duration_s = 120.0  # 2 min stored
        sensor = _make_sensor(ProximityDurationSensor, ps)
        assert sensor.native_value == 2.0

    def test_rounds_to_one_decimal(self):
        # 100 s / 60 = 1.6666... → 1.7
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.proximity = False
        ps.proximity_since = None
        ps.proximity_duration_s = 100.0
        sensor = _make_sensor(ProximityDurationSensor, ps)
        assert sensor.native_value == round(100.0 / 60, 1)
