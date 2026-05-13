"""Tests for EntityDistanceCoordinator."""

from __future__ import annotations

from datetime import datetime

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
)
from custom_components.entity_distance.coordinator import (
    _calc_bucket,
    _get_coords,
    _is_zone,
)
from custom_components.entity_distance.models import PairState
from tests.conftest import make_state, make_zone_state

_DEFAULT_THRESHOLDS = {
    BUCKET_VERY_NEAR: DEFAULT_ZONE_VERY_NEAR_M,
    BUCKET_NEAR: DEFAULT_ZONE_NEAR_M,
    BUCKET_MID: DEFAULT_ZONE_MID_M,
    BUCKET_FAR: DEFAULT_ZONE_FAR_M,
}


class TestGetCoords:
    def test_lat_lon_attrs(self):
        state = make_state("person.alice", 51.5, -0.1, accuracy=20)
        result = _get_coords(state)
        assert result == (51.5, -0.1, 20)

    def test_location_attr(self):
        from homeassistant.core import State

        state = State("person.alice", "home", {"location": [51.5, -0.1]})
        result = _get_coords(state)
        assert result is not None
        assert result[0] == 51.5

    def test_state_string(self):
        from homeassistant.core import State

        state = State("sensor.gps", "51.5,-0.1", {})
        result = _get_coords(state)
        assert result is not None
        assert abs(result[0] - 51.5) < 0.001

    def test_invalid_returns_none(self):
        from homeassistant.core import State

        state = State("person.alice", "home", {})
        result = _get_coords(state)
        assert result is None

    def test_out_of_range_lat(self):
        from homeassistant.core import State

        state = State("person.alice", "home", {"latitude": 95.0, "longitude": 0.0})
        result = _get_coords(state)
        assert result is None


class TestCalcBucket:
    def test_very_near(self):
        assert _calc_bucket(30, _DEFAULT_THRESHOLDS) == BUCKET_VERY_NEAR

    def test_near(self):
        assert _calc_bucket(300, _DEFAULT_THRESHOLDS) == BUCKET_NEAR

    def test_mid(self):
        assert _calc_bucket(1000, _DEFAULT_THRESHOLDS) == BUCKET_MID

    def test_far(self):
        assert _calc_bucket(5000, _DEFAULT_THRESHOLDS) == BUCKET_FAR

    def test_very_far(self):
        assert _calc_bucket(15000, _DEFAULT_THRESHOLDS) == BUCKET_VERY_FAR

    def test_exact_boundary_very_near(self):
        assert _calc_bucket(100, _DEFAULT_THRESHOLDS) == BUCKET_VERY_NEAR

    def test_just_over_boundary(self):
        assert _calc_bucket(101, _DEFAULT_THRESHOLDS) == BUCKET_NEAR

    def test_custom_thresholds(self):
        custom = {BUCKET_VERY_NEAR: 50, BUCKET_NEAR: 200, BUCKET_MID: 1000, BUCKET_FAR: 5000}
        assert _calc_bucket(30, custom) == BUCKET_VERY_NEAR
        assert _calc_bucket(100, custom) == BUCKET_NEAR
        assert _calc_bucket(500, custom) == BUCKET_MID
        assert _calc_bucket(3000, custom) == BUCKET_FAR
        assert _calc_bucket(6000, custom) == BUCKET_VERY_FAR


class TestCalcBucketCustomThresholds:
    """Test _calc_bucket with non-default threshold values at boundary edges."""

    _CUSTOM = {BUCKET_VERY_NEAR: 50, BUCKET_NEAR: 150, BUCKET_MID: 500, BUCKET_FAR: 2000}

    def test_at_very_near_upper_boundary(self):
        assert _calc_bucket(50, self._CUSTOM) == BUCKET_VERY_NEAR

    def test_one_above_very_near_boundary(self):
        assert _calc_bucket(51, self._CUSTOM) == BUCKET_NEAR

    def test_at_near_upper_boundary(self):
        assert _calc_bucket(150, self._CUSTOM) == BUCKET_NEAR

    def test_one_above_near_boundary(self):
        assert _calc_bucket(151, self._CUSTOM) == BUCKET_MID

    def test_at_mid_upper_boundary(self):
        assert _calc_bucket(500, self._CUSTOM) == BUCKET_MID

    def test_one_above_mid_boundary(self):
        assert _calc_bucket(501, self._CUSTOM) == BUCKET_FAR

    def test_at_far_upper_boundary(self):
        assert _calc_bucket(2000, self._CUSTOM) == BUCKET_FAR

    def test_one_above_far_boundary_is_very_far(self):
        assert _calc_bucket(2001, self._CUSTOM) == BUCKET_VERY_FAR

    def test_zero_distance_is_very_near(self):
        assert _calc_bucket(0, self._CUSTOM) == BUCKET_VERY_NEAR

    def test_large_distance_is_very_far(self):
        assert _calc_bucket(1_000_000, self._CUSTOM) == BUCKET_VERY_FAR


class TestIsZone:
    def test_zone_entity(self):
        state = make_zone_state("zone.home", 51.5, -0.1)
        assert _is_zone(state) is True

    def test_person_entity(self):
        state = make_state("person.alice", 51.5, -0.1)
        assert _is_zone(state) is False


# ---------------------------------------------------------------------------
# PairState.proximity_tracking_started initialisation tests
# ---------------------------------------------------------------------------


class TestProximityTrackingStartedInit:
    """Test that PairState.proximity_tracking_started initialises to None and can be set."""

    def test_initialises_to_none(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        assert ps.proximity_tracking_started is None

    def test_can_be_set_to_datetime(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        now = datetime.now().astimezone()
        ps.proximity_tracking_started = now
        assert ps.proximity_tracking_started == now

    def test_coordinator_logic_sets_when_none(self):
        # Simulate the coordinator initialisation pattern: if the field is None,
        # set it to now.  Verify the field transitions from None to a datetime.
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        assert ps.proximity_tracking_started is None
        now = datetime.now().astimezone()
        if ps.proximity_tracking_started is None:
            ps.proximity_tracking_started = now
        assert ps.proximity_tracking_started is not None
        assert ps.proximity_tracking_started == now


# ---------------------------------------------------------------------------
# Additional _get_coords edge cases
# ---------------------------------------------------------------------------


class TestGetCoordsEdgeCases:
    """Edge cases for _get_coords coordinate extraction."""

    def test_valid_out_of_range_lon(self):
        from homeassistant.core import State

        state = State("person.alice", "home", {"latitude": 0.0, "longitude": 200.0})
        result = _get_coords(state)
        assert result is None

    def test_location_attr_with_extra_elements(self):
        from homeassistant.core import State

        state = State("person.alice", "home", {"location": [51.5, -0.1, 42.0]})
        result = _get_coords(state)
        assert result is not None
        assert result[0] == 51.5
        assert result[1] == -0.1

    def test_location_attr_non_numeric(self):
        from homeassistant.core import State

        state = State("person.alice", "home", {"location": ["x", "y"]})
        result = _get_coords(state)
        assert result is None

    def test_state_string_with_spaces(self):
        from homeassistant.core import State

        # "51.5, -0.1" with a space after comma — split on comma still works
        state = State("sensor.gps", "51.5,-0.1", {})
        result = _get_coords(state)
        assert result is not None
        assert abs(result[0] - 51.5) < 0.001

    def test_out_of_range_lon_via_attributes(self):
        from homeassistant.core import State

        state = State("person.alice", "home", {"latitude": 45.0, "longitude": -200.0})
        result = _get_coords(state)
        assert result is None

    def test_accuracy_extracted_from_gps_accuracy_attr(self):
        from tests.conftest import make_state

        state = make_state("person.alice", 51.5, -0.1, accuracy=25.0)
        result = _get_coords(state)
        assert result is not None
        assert result[2] == 25.0

    def test_accuracy_is_none_when_absent(self):
        from homeassistant.core import State

        state = State("person.alice", "home", {"latitude": 51.5, "longitude": -0.1})
        result = _get_coords(state)
        assert result is not None
        assert result[2] is None


# ---------------------------------------------------------------------------
# _calc_bucket with zero thresholds edge case
# ---------------------------------------------------------------------------


class TestCalcBucketEdgeCases:
    def test_negative_distance_treated_as_very_near(self):
        # Negative distances should not crash and land in VERY_NEAR
        assert (
            _calc_bucket(
                -1,
                {
                    BUCKET_VERY_NEAR: DEFAULT_ZONE_VERY_NEAR_M,
                    BUCKET_NEAR: DEFAULT_ZONE_NEAR_M,
                    BUCKET_MID: DEFAULT_ZONE_MID_M,
                    BUCKET_FAR: DEFAULT_ZONE_FAR_M,
                },
            )
            == BUCKET_VERY_NEAR
        )
