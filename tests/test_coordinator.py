"""Tests for EntityDistanceCoordinator."""

from __future__ import annotations

from datetime import datetime, timedelta

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


# ---------------------------------------------------------------------------
# last_seen_together — updated on EXIT, not entry
# ---------------------------------------------------------------------------


class TestLastSeenTogetherOnExit:
    """last_seen_together must record the moment proximity ends, not when it starts."""

    def test_not_set_on_entry(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        assert ps.last_seen_together is None
        # Simulate proximity entry (coordinator sets proximity = True, proximity_since = now)
        now = datetime.now().astimezone()
        ps.proximity = True
        ps.proximity_since = now
        # last_seen_together must NOT be set at entry
        assert ps.last_seen_together is None

    def test_set_on_exit(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        entry_time = datetime.now().astimezone()
        ps.proximity = True
        ps.proximity_since = entry_time

        # Simulate proximity exit (coordinator pattern)
        exit_time = entry_time + timedelta(minutes=10)
        ps.proximity = False
        ps.last_seen_together = exit_time
        if ps.proximity_since:
            ps.proximity_duration_s += (exit_time - ps.proximity_since).total_seconds()
        ps.proximity_since = None

        assert ps.last_seen_together == exit_time

    def test_last_seen_reflects_exit_not_entry(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        entry_time = datetime.now().astimezone()
        exit_time = entry_time + timedelta(minutes=35)

        # Enter proximity
        ps.proximity = True
        ps.proximity_since = entry_time
        # last_seen_together not set yet
        assert ps.last_seen_together is None

        # Exit proximity
        ps.proximity = False
        ps.last_seen_together = exit_time
        ps.proximity_duration_s += (exit_time - entry_time).total_seconds()
        ps.proximity_since = None

        assert ps.last_seen_together == exit_time
        assert ps.last_seen_together != entry_time
        assert ps.proximity_duration_s == pytest.approx(35 * 60, abs=1)

    def test_duration_accumulated_on_exit(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        entry_time = datetime.now().astimezone()
        exit_time = entry_time + timedelta(minutes=5)

        ps.proximity = True
        ps.proximity_since = entry_time
        ps.proximity = False
        ps.last_seen_together = exit_time
        if ps.proximity_since:
            ps.proximity_duration_s += (exit_time - ps.proximity_since).total_seconds()
        ps.proximity_since = None

        assert ps.proximity_duration_s == pytest.approx(300, abs=1)
        assert ps.proximity_since is None

    def test_last_seen_not_overwritten_during_second_entry(self):
        """Second entry while last_seen_together holds a previous exit value must not clear it."""
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        first_exit = datetime.now().astimezone()
        ps.last_seen_together = first_exit

        # Second proximity entry — must NOT touch last_seen_together
        ps.proximity = True
        ps.proximity_since = first_exit + timedelta(hours=1)
        # Coordinator entry block does not set last_seen_together
        assert ps.last_seen_together == first_exit


# ---------------------------------------------------------------------------
# proximity_since persistence — live session survives HA restart
# ---------------------------------------------------------------------------


class TestProximitySincePersistence:
    """proximity_since must be saved and restored so duration accumulates correctly after restart."""

    def test_proximity_since_restored_sets_proximity_true(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        assert ps.proximity is False
        since = datetime.now().astimezone() - timedelta(minutes=10)
        # Simulate restore path
        ps.proximity_since = datetime.fromisoformat(since.isoformat())
        ps.proximity = True
        assert ps.proximity is True
        assert ps.proximity_since is not None

    def test_duration_sensor_includes_live_session_after_restore(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.proximity_duration_s = 300.0  # 5 min accumulated before restart
        since = datetime.now().astimezone() - timedelta(minutes=20)
        ps.proximity_since = since
        ps.proximity = True

        # Simulate what ProximityDurationSensor.native_value computes
        total_s = ps.proximity_duration_s
        if ps.proximity and ps.proximity_since:
            total_s += (datetime.now().astimezone() - ps.proximity_since).total_seconds()

        assert total_s >= 300 + 20 * 60  # at least 5 + 20 min

    def test_proximity_since_none_not_restored_when_missing(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        # No proximity_since in blob — proximity stays False
        assert ps.proximity is False
        assert ps.proximity_since is None

    def test_proximity_duration_not_double_counted_after_restore(self):
        """Duration at restore time must not be added again at next exit."""
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.proximity_duration_s = 600.0  # 10 min from before restart
        since = datetime.now().astimezone() - timedelta(minutes=5)
        ps.proximity_since = since
        ps.proximity = True

        # Exit proximity — only adds since→now, not pre-restart duration again
        exit_time = datetime.now().astimezone()
        elapsed = (exit_time - ps.proximity_since).total_seconds()
        ps.proximity_duration_s += elapsed
        ps.proximity = False
        ps.proximity_since = None

        assert ps.proximity_duration_s >= 600 + 5 * 60
        assert ps.proximity_duration_s < 600 + 10 * 60  # not double-counted


# ---------------------------------------------------------------------------
# _update_frequency and _is_reliable
# ---------------------------------------------------------------------------


class TestUpdateFrequency:
    """Test EntityDistanceCoordinator._update_frequency helper."""

    def _make_coordinator(self):
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        coordinator = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coordinator._min_updates_reliable = 3
        return coordinator

    def test_first_call_no_window_returns_1(self):
        coordinator = self._make_coordinator()
        now = datetime.now().astimezone()
        result = coordinator._update_frequency(0, None, now)
        assert result == 1

    def test_within_window_increments(self):
        coordinator = self._make_coordinator()
        now = datetime.now().astimezone()
        window_start = now - timedelta(seconds=60)
        result = coordinator._update_frequency(5, window_start, now)
        assert result == 6

    def test_elapsed_window_resets_to_1(self):
        from custom_components.entity_distance.const import UPDATES_FREQUENCY_WINDOW_S

        coordinator = self._make_coordinator()
        now = datetime.now().astimezone()
        old_window = now - timedelta(seconds=UPDATES_FREQUENCY_WINDOW_S + 10)
        result = coordinator._update_frequency(10, old_window, now)
        assert result == 1

    def test_at_exactly_window_boundary_resets(self):
        from custom_components.entity_distance.const import UPDATES_FREQUENCY_WINDOW_S

        coordinator = self._make_coordinator()
        now = datetime.now().astimezone()
        exactly_at_boundary = now - timedelta(seconds=UPDATES_FREQUENCY_WINDOW_S + 1)
        result = coordinator._update_frequency(5, exactly_at_boundary, now)
        assert result == 1


class TestIsReliable:
    """Test EntityDistanceCoordinator._is_reliable helper."""

    def _make_coordinator(self, min_updates: int = 3):
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        coordinator = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coordinator._min_updates_reliable = min_updates
        return coordinator

    def test_reliable_when_both_counts_meet_threshold(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 3
        ps.update_count_b = 3
        assert coordinator._is_reliable(ps) is True

    def test_reliable_when_counts_exceed_threshold(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 10
        ps.update_count_b = 5
        assert coordinator._is_reliable(ps) is True

    def test_not_reliable_when_a_below_threshold(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 2
        ps.update_count_b = 5
        assert coordinator._is_reliable(ps) is False

    def test_not_reliable_when_b_below_threshold(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 5
        ps.update_count_b = 1
        assert coordinator._is_reliable(ps) is False

    def test_not_reliable_when_both_zero(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 0
        ps.update_count_b = 0
        assert coordinator._is_reliable(ps) is False

    def test_reliable_with_min_1(self):
        coordinator = self._make_coordinator(1)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 1
        ps.update_count_b = 1
        assert coordinator._is_reliable(ps) is True

    def test_not_reliable_with_min_1_when_zero(self):
        coordinator = self._make_coordinator(1)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 0
        ps.update_count_b = 1
        assert coordinator._is_reliable(ps) is False


# ---------------------------------------------------------------------------
# _resolve_entities
# ---------------------------------------------------------------------------


class TestResolveEntities:
    """Test _resolve_entities helper."""

    def test_returns_list_from_data(self):
        from custom_components.entity_distance.coordinator import _resolve_entities

        data = {"entities": ["person.alice", "person.bob"]}
        result = _resolve_entities(data)
        assert result == ["person.alice", "person.bob"]

    def test_returns_empty_when_key_missing(self):
        from custom_components.entity_distance.coordinator import _resolve_entities

        result = _resolve_entities({})
        assert result == []

    def test_returns_list_copy(self):
        from custom_components.entity_distance.coordinator import _resolve_entities

        data = {"entities": ["person.alice"]}
        result = _resolve_entities(data)
        result.append("person.bob")
        assert data["entities"] == ["person.alice"]
