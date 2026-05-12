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
)
from custom_components.entity_distance.models import PairData, PairState
from custom_components.entity_distance.sensor import BucketLevelSensor, ProximityDurationSensor

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
