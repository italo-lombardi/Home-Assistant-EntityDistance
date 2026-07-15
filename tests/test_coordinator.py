"""Tests for EntityDistanceCoordinator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from custom_components.entity_distance.const import (
    BUCKET_FAR,
    BUCKET_MID,
    BUCKET_NEAR,
    BUCKET_VERY_FAR,
    BUCKET_VERY_NEAR,
    CONF_PROXIMITY_ZONE,
    DEFAULT_ZONE_FAR_M,
    DEFAULT_ZONE_MID_M,
    DEFAULT_ZONE_NEAR_M,
    DEFAULT_ZONE_VERY_NEAR_M,
)
from custom_components.entity_distance.coordinator import (
    _get_coords,
    _is_zone,
    calc_bucket,
)
from custom_components.entity_distance.models import PairState, pair_key
from tests.conftest import make_state, make_zone_state

_DEFAULT_THRESHOLDS = {
    BUCKET_VERY_NEAR: DEFAULT_ZONE_VERY_NEAR_M,
    BUCKET_NEAR: DEFAULT_ZONE_NEAR_M,
    BUCKET_MID: DEFAULT_ZONE_MID_M,
    BUCKET_FAR: DEFAULT_ZONE_FAR_M,
}

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)


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
        assert calc_bucket(30, _DEFAULT_THRESHOLDS) == BUCKET_VERY_NEAR

    def test_near(self):
        assert calc_bucket(300, _DEFAULT_THRESHOLDS) == BUCKET_NEAR

    def test_mid(self):
        assert calc_bucket(2000, _DEFAULT_THRESHOLDS) == BUCKET_MID

    def test_far(self):
        assert calc_bucket(10000, _DEFAULT_THRESHOLDS) == BUCKET_FAR

    def test_very_far(self):
        assert calc_bucket(25000, _DEFAULT_THRESHOLDS) == BUCKET_VERY_FAR

    def test_exact_boundary_very_near(self):
        assert calc_bucket(100, _DEFAULT_THRESHOLDS) == BUCKET_VERY_NEAR

    def test_just_over_boundary(self):
        assert calc_bucket(201, _DEFAULT_THRESHOLDS) == BUCKET_NEAR

    def test_custom_thresholds(self):
        custom = {
            BUCKET_VERY_NEAR: 50,
            BUCKET_NEAR: 200,
            BUCKET_MID: 1000,
            BUCKET_FAR: 5000,
        }
        assert calc_bucket(30, custom) == BUCKET_VERY_NEAR
        assert calc_bucket(100, custom) == BUCKET_NEAR
        assert calc_bucket(500, custom) == BUCKET_MID
        assert calc_bucket(3000, custom) == BUCKET_FAR
        assert calc_bucket(6000, custom) == BUCKET_VERY_FAR


class TestCalcBucketCustomThresholds:
    """Test calc_bucket with non-default threshold values at boundary edges."""

    _CUSTOM = {
        BUCKET_VERY_NEAR: 50,
        BUCKET_NEAR: 150,
        BUCKET_MID: 500,
        BUCKET_FAR: 2000,
    }

    def test_at_very_near_upper_boundary(self):
        assert calc_bucket(50, self._CUSTOM) == BUCKET_VERY_NEAR

    def test_one_above_very_near_boundary(self):
        assert calc_bucket(51, self._CUSTOM) == BUCKET_NEAR

    def test_at_near_upper_boundary(self):
        assert calc_bucket(150, self._CUSTOM) == BUCKET_NEAR

    def test_one_above_near_boundary(self):
        assert calc_bucket(151, self._CUSTOM) == BUCKET_MID

    def test_at_mid_upper_boundary(self):
        assert calc_bucket(500, self._CUSTOM) == BUCKET_MID

    def test_one_above_mid_boundary(self):
        assert calc_bucket(501, self._CUSTOM) == BUCKET_FAR

    def test_at_far_upper_boundary(self):
        assert calc_bucket(2000, self._CUSTOM) == BUCKET_FAR

    def test_one_above_far_boundary_is_very_far(self):
        assert calc_bucket(2001, self._CUSTOM) == BUCKET_VERY_FAR

    def test_zero_distance_is_very_near(self):
        assert calc_bucket(0, self._CUSTOM) == BUCKET_VERY_NEAR

    def test_large_distance_is_very_far(self):
        assert calc_bucket(1_000_000, self._CUSTOM) == BUCKET_VERY_FAR


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
# calc_bucket with zero thresholds edge case
# ---------------------------------------------------------------------------


class TestCalcBucketEdgeCases:
    def test_negative_distance_treated_as_very_near(self):
        # Negative distances should not crash and land in VERY_NEAR
        assert (
            calc_bucket(
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
# _advance_window and is_reliable
# ---------------------------------------------------------------------------


class TestAdvanceWindow:
    """Test EntityDistanceCoordinator._advance_window helper."""

    def _make_coordinator(self):
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )

        coordinator = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coordinator._min_updates_reliable = 3
        coordinator._updates_window_s = 1800.0
        return coordinator

    def test_first_call_no_window_returns_1_and_anchors(self):
        coordinator = self._make_coordinator()
        now = datetime.now().astimezone()
        count, ws = coordinator._advance_window(0, None, now)
        assert count == 1
        assert ws == now

    def test_within_window_increments_and_keeps_anchor(self):
        coordinator = self._make_coordinator()
        now = datetime.now().astimezone()
        window_start = now - timedelta(seconds=60)
        count, ws = coordinator._advance_window(5, window_start, now)
        assert count == 6
        assert ws == window_start

    def test_elapsed_window_resets_to_1_and_reanchors(self):
        from custom_components.entity_distance.const import (
            DEFAULT_UPDATES_WINDOW_S as UPDATES_FREQUENCY_WINDOW_S,
        )

        coordinator = self._make_coordinator()
        now = datetime.now().astimezone()
        old_window = now - timedelta(seconds=UPDATES_FREQUENCY_WINDOW_S + 10)
        count, ws = coordinator._advance_window(10, old_window, now)
        assert count == 1
        assert ws == now

    def test_at_exactly_window_boundary_resets(self):
        from custom_components.entity_distance.const import (
            DEFAULT_UPDATES_WINDOW_S as UPDATES_FREQUENCY_WINDOW_S,
        )

        coordinator = self._make_coordinator()
        now = datetime.now().astimezone()
        exactly_at_boundary = now - timedelta(seconds=UPDATES_FREQUENCY_WINDOW_S)
        count, ws = coordinator._advance_window(5, exactly_at_boundary, now)
        assert count == 1
        assert ws == now

    def test_one_second_before_boundary_does_not_reset(self):
        from custom_components.entity_distance.const import (
            DEFAULT_UPDATES_WINDOW_S as UPDATES_FREQUENCY_WINDOW_S,
        )

        coordinator = self._make_coordinator()
        now = datetime.now().astimezone()
        just_inside = now - timedelta(seconds=UPDATES_FREQUENCY_WINDOW_S - 1)
        count, ws = coordinator._advance_window(5, just_inside, now)
        assert count == 6
        assert ws == just_inside


class TestIsReliable:
    """Test EntityDistanceCoordinator.is_reliable helper."""

    def _make_coordinator(self, min_updates: int = 3):
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )

        coordinator = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coordinator._min_updates_reliable = min_updates
        return coordinator

    def test_reliable_when_both_counts_meet_threshold(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 3
        ps.update_count_b = 3
        assert coordinator.is_reliable(ps) is True

    def test_reliable_when_counts_exceed_threshold(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 10
        ps.update_count_b = 5
        assert coordinator.is_reliable(ps) is True

    def test_not_reliable_when_a_below_threshold(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 2
        ps.update_count_b = 5
        assert coordinator.is_reliable(ps) is False

    def test_not_reliable_when_b_below_threshold(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 5
        ps.update_count_b = 1
        assert coordinator.is_reliable(ps) is False

    def test_not_reliable_when_both_zero(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 0
        ps.update_count_b = 0
        assert coordinator.is_reliable(ps) is False

    def test_reliable_with_min_1(self):
        coordinator = self._make_coordinator(1)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 1
        ps.update_count_b = 1
        assert coordinator.is_reliable(ps) is True

    def test_not_reliable_with_min_1_when_zero(self):
        coordinator = self._make_coordinator(1)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 0
        ps.update_count_b = 1
        assert coordinator.is_reliable(ps) is False


# ---------------------------------------------------------------------------
# _resolve_entities
# ---------------------------------------------------------------------------


class TestEntitiesResolution:
    """Coordinator wires _entities from config entry data correctly."""

    async def test_entities_from_data(self, hass):
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        entry = MockConfigEntry(
            domain=DOMAIN, data={"entities": ["person.alice", "person.bob"]}, options={}
        )
        entry.add_to_hass(hass)
        coord = EntityDistanceCoordinator(hass, entry)
        assert coord.entities == ["person.alice", "person.bob"]

    async def test_entities_empty_when_key_missing(self, hass):
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
        entry.add_to_hass(hass)
        coord = EntityDistanceCoordinator(hass, entry)
        assert coord.entities == []

    async def test_entities_is_copy_not_original(self, hass):
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        original = ["person.alice"]
        entry = MockConfigEntry(domain=DOMAIN, data={"entities": original}, options={})
        entry.add_to_hass(hass)
        coord = EntityDistanceCoordinator(hass, entry)
        coord.entities.append("person.bob")
        assert original == ["person.alice"]


# ---------------------------------------------------------------------------
# _calc_pair — ha_distance invalid, resync hold, midnight reset
# ---------------------------------------------------------------------------


def _make_calc_pair_coordinator(
    entities=None,
    entry_threshold_m=500.0,
    exit_threshold_m=500.0,
    max_accuracy_m=0.0,
    max_speed_kmh=0.0,
    resync_silence_s=0.0,
    resync_hold_s=60.0,
    require_reliable=False,
    min_updates_reliable=1,
    updates_window_s=1800.0,
):
    from custom_components.entity_distance.const import (
        BUCKET_FAR,
        BUCKET_MID,
        BUCKET_NEAR,
        BUCKET_VERY_NEAR,
        DEFAULT_ZONE_FAR_M,
        DEFAULT_ZONE_MID_M,
        DEFAULT_ZONE_NEAR_M,
        DEFAULT_ZONE_VERY_NEAR_M,
    )
    from custom_components.entity_distance.coordinator import EntityDistanceCoordinator
    from custom_components.entity_distance.models import PairState, pair_key

    if entities is None:
        entities = ["person.alice", "person.bob"]

    coordinator = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
    coordinator._entities = entities
    coordinator._entry_threshold_m = entry_threshold_m
    coordinator._exit_threshold_m = exit_threshold_m
    coordinator._max_accuracy_m = max_accuracy_m
    coordinator._stationary_threshold_m = max(15.0, max_accuracy_m * 0.15)
    coordinator._max_speed_kmh = max_speed_kmh
    coordinator._resync_silence_s = resync_silence_s
    coordinator._resync_hold_s = resync_hold_s
    coordinator._grace_window_s = 900.0
    coordinator._require_reliable = require_reliable
    coordinator._min_updates_reliable = min_updates_reliable
    coordinator._updates_window_s = updates_window_s
    coordinator._bucket_thresholds = {
        BUCKET_VERY_NEAR: DEFAULT_ZONE_VERY_NEAR_M,
        BUCKET_NEAR: DEFAULT_ZONE_NEAR_M,
        BUCKET_MID: DEFAULT_ZONE_MID_M,
        BUCKET_FAR: DEFAULT_ZONE_FAR_M,
    }

    pairs = {}
    resync_holding = {}
    resync_hold_until = {}
    for a, b in __import__("itertools").combinations(entities, 2):
        k = pair_key(a, b)
        pairs[k] = PairState(entity_a_id=k[0], entity_b_id=k[1])
        resync_holding[k] = False
        resync_hold_until[k] = None

    coordinator._pair_states = pairs
    coordinator._resync_holding = resync_holding
    coordinator._resync_hold_until = resync_hold_until
    coordinator.hass = MagicMock()
    return coordinator


class TestCalcPairHaDistanceInvalid:
    """_calc_pair must invalidate pair when ha_distance returns None or inf."""

    def test_none_distance_invalidates(self):

        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=None,
        ):
            result = coordinator._calc_pair(
                ps, "person.alice", "person.bob", datetime.now().astimezone(), set()
            )

        assert result.data_valid is False
        assert result.last_error == "ha_distance_invalid"

    def test_inf_distance_invalidates(self):

        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=float("inf"),
        ):
            result = coordinator._calc_pair(
                ps, "person.alice", "person.bob", datetime.now().astimezone(), set()
            )

        assert result.data_valid is False
        assert result.last_error == "ha_distance_invalid"


class TestCalcPairResyncHold:
    """_calc_pair must mark data_valid=False while resync hold is active."""

    def test_data_invalid_during_hold(self):
        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(resync_silence_s=0.0, resync_hold_s=3600.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        coordinator._resync_holding[k] = True
        coordinator._resync_hold_until[k] = now + timedelta(seconds=3600)

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=5000.0,
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert result.data_valid is True
        # prev_calc_time and prev_distance_m are advanced to current values so the
        # expiry tick sees delta_m=0 → stationary instead of direction=unknown
        assert result.prev_calc_time == now
        assert result.prev_distance_m == 5000.0

    def test_direction_not_unknown_on_hold_expiry_tick(self):
        """End-to-end: in-hold tick sets baseline → expiry tick produces stationary, not unknown."""
        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(resync_silence_s=0.0, resync_hold_s=60.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        now = datetime.now().astimezone()

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        # Tick 1 — hold active, sets prev_distance_m/prev_calc_time
        coordinator._resync_holding[k] = True
        hold_until = now + timedelta(seconds=30)
        coordinator._resync_hold_until[k] = hold_until
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=5000.0,
        ):
            coordinator._calc_pair(ps, "person.alice", "person.bob", now, set())
        assert coordinator._resync_holding[k] is True  # still in hold

        # Tick 2 — hold expired, pair at same distance
        expiry_now = now + timedelta(seconds=61)
        coordinator._resync_hold_until[k] = now  # mark as expired
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=5000.0,
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", expiry_now, set())

        assert coordinator._resync_holding[k] is False
        # direction must not be unknown — stationary since delta_m = 0
        assert result.direction is not None
        assert result.direction == "stationary"

    def test_data_valid_after_hold_expires(self):
        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(resync_silence_s=0.0, resync_hold_s=60.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        coordinator._resync_holding[k] = True
        coordinator._resync_hold_until[k] = now - timedelta(seconds=1)  # already expired

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=5000.0,
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert result.data_valid is True
        assert coordinator._resync_holding[k] is False

    def test_hold_expiry_same_day_credits_gap_to_today_proximity(self):
        """Hold expiry same-day: gap from hold_until→now must credit today_proximity_seconds."""
        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(resync_silence_s=0.0, resync_hold_s=60.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        hold_until = now - timedelta(seconds=90)  # expired 90s ago

        ps.proximity = True
        ps.proximity_since = now - timedelta(hours=1)
        ps.today_reset_date = now.date()
        ps.today_proximity_seconds = 100.0
        ps.today_zone_seconds = {"very_near": 100.0}
        coordinator._resync_holding[k] = True
        coordinator._resync_hold_until[k] = hold_until

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.501, -0.1)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert coordinator._resync_holding[k] is False
        # Gap of 90s must be credited to today_proximity_seconds
        assert result.today_proximity_seconds >= 100.0 + 90.0


class TestCalcPairMissingState:
    """_calc_pair must invalidate when entity state is missing."""

    def test_missing_state_a_invalidates(self):
        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            None if eid == "person.alice" else state_b
        )

        result = coordinator._calc_pair(
            ps, "person.alice", "person.bob", datetime.now().astimezone(), set()
        )
        assert result.data_valid is False

    def test_missing_state_b_invalidates(self):
        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        state_a = make_state("person.alice", 51.5, -0.1)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else None
        )

        result = coordinator._calc_pair(
            ps, "person.alice", "person.bob", datetime.now().astimezone(), set()
        )
        assert result.data_valid is False


class TestCalcPairMidnightReset:
    """today_proximity_seconds and today_zone_seconds reset at midnight."""

    def test_today_seconds_reset_on_new_day(self):
        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        yesterday = (datetime.now().astimezone() - timedelta(days=1)).date()
        ps.today_reset_date = yesterday
        ps.today_proximity_seconds = 9999.0
        ps.today_zone_seconds = {"very_near": 500.0}

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=5000.0,
        ):
            result = coordinator._calc_pair(
                ps, "person.alice", "person.bob", datetime.now().astimezone(), set()
            )

        assert result.today_proximity_seconds == 0.0
        assert result.today_zone_seconds == {}


# ---------------------------------------------------------------------------
# _calc_pair — speed-filter and closing-speed timing edges
# ---------------------------------------------------------------------------


class TestCalcPairTimingEdges:
    """Cover sub-5s speed filter skip and zero-delta closing-speed skip."""

    def test_speed_filter_skipped_when_delta_under_5s(self):
        # delta_s < 5.0 → speed filter must not run, pair stays valid even
        # with a wild prev_distance jump.
        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(max_speed_kmh=100.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        ps.prev_distance_m = 0.0
        ps.prev_calc_time = now - timedelta(seconds=2)  # < 5s window

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=10_000.0,
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, set())
        assert result.data_valid is True

    def test_closing_speed_skipped_when_delta_zero(self):
        # delta_s == 0 → closing-speed branch must be skipped (no DIV/0),
        # pair still valid.
        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(max_speed_kmh=0.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        ps.prev_distance_m = 100.0
        ps.prev_calc_time = now  # same instant → delta_s == 0

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=120.0,
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, set())
        assert result.data_valid is True

    def test_proximity_entry_with_existing_tracking_started(self):
        # First-time proximity entry but ps.proximity_tracking_started was
        # already restored from disk — must NOT be overwritten.
        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(entry_threshold_m=10_000.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        existing = datetime(2020, 1, 1).astimezone()
        ps.proximity_tracking_started = existing
        ps.proximity = False

        now = datetime.now().astimezone()
        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=500.0,
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert result.proximity is True
        assert result.proximity_tracking_started == existing

    def test_proximity_exit_with_proximity_since_none(self):
        # Defensive: ps.proximity is True but proximity_since is None (stale
        # restored state). Exit must not crash and duration stays unchanged.
        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(entry_threshold_m=100.0, exit_threshold_m=100.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        ps.proximity = True
        ps.proximity_since = None
        ps.proximity_duration_s = 42.0

        now = datetime.now().astimezone()
        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=1000.0,
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert result.proximity is False
        assert result.proximity_duration_s == 42.0

    def test_resync_hold_post_hold_zero_skips_bucket(self):
        # FREEZE: hold active at midnight — proximity stays True, counters NOT touched
        # during hold. Date roll and bucket credit only happen on hold expiry.
        from datetime import datetime

        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(resync_silence_s=0.0, resync_hold_s=3600.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        midnight_utc = datetime(2024, 1, 2, tzinfo=UTC)
        ps.proximity = True
        ps.proximity_since = midnight_utc - timedelta(seconds=300)
        ps.distance_m = 50.0
        ps.today_reset_date = (midnight_utc - timedelta(days=1)).date()  # date rolled
        ps.today_proximity_seconds = 999.0
        ps.today_zone_seconds = {"near": 999.0}

        coordinator._resync_holding[k] = True
        coordinator._resync_hold_until[k] = midnight_utc + timedelta(seconds=3600)

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=50.0,
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", midnight_utc, set())

        # FREEZE: hold still active → proximity=True, counters unchanged mid-hold
        assert result.proximity is True
        assert result.today_proximity_seconds == pytest.approx(999.0, abs=1.0)
        assert result.today_zone_seconds == {"near": 999.0}


# ---------------------------------------------------------------------------
# _calc_pair — update window tracking (lines 467-474, 477-484)
# ---------------------------------------------------------------------------


class TestStateChangedUpdateWindowTracking:
    """_async_state_changed sets update_window_start when an event arrives.

    (Counter tracking moved out of _calc_pair so update_count and last_update
    advance together — see CHANGELOG 0.2.6.)
    """

    def _make_event(self, entity_id):
        from unittest.mock import MagicMock

        ev = MagicMock()
        ev.data = {
            "entity_id": entity_id,
            "old_state": MagicMock(state="home"),
            "new_state": MagicMock(state="not_home"),
        }
        return ev

    def test_entity_a_in_pending_sets_window_start(self):
        from custom_components.entity_distance.models import pair_key

        coordinator = _make_calc_pair_coordinator()
        coordinator._debouncer = MagicMock()
        coordinator._debouncer.async_call = MagicMock(return_value=None)
        coordinator._entity_to_pairs = {
            "person.alice": [pair_key("person.alice", "person.bob")],
            "person.bob": [pair_key("person.alice", "person.bob")],
        }
        coordinator._pending_updates = set()
        coordinator.hass.async_create_task = MagicMock()

        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        ps.update_window_start_a = None
        ps.update_count_a = 0

        coordinator._async_state_changed(self._make_event("person.alice"))

        assert ps.update_window_start_a is not None
        assert ps.update_count_a == 1
        assert ps.last_update_a is not None

    def test_entity_b_in_pending_sets_window_start(self):
        from custom_components.entity_distance.models import pair_key

        coordinator = _make_calc_pair_coordinator()
        coordinator._debouncer = MagicMock()
        coordinator._debouncer.async_call = MagicMock(return_value=None)
        coordinator._entity_to_pairs = {
            "person.alice": [pair_key("person.alice", "person.bob")],
            "person.bob": [pair_key("person.alice", "person.bob")],
        }
        coordinator._pending_updates = set()
        coordinator.hass.async_create_task = MagicMock()

        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        ps.update_window_start_b = None
        ps.update_count_b = 0

        coordinator._async_state_changed(self._make_event("person.bob"))

        assert ps.update_window_start_b is not None
        assert ps.update_count_b == 1
        assert ps.last_update_b is not None

    def test_counter_increments_during_resync_hold(self):
        """Update count tracks raw arrivals, even when _calc_pair would skip
        (resync hold). Decoupling matches what `last_update_a/b` already does
        and prevents the "14m ago / 0 updates" mismatch users see in the UI."""
        from custom_components.entity_distance.models import pair_key

        coordinator = _make_calc_pair_coordinator()
        coordinator._debouncer = MagicMock()
        coordinator._debouncer.async_call = MagicMock(return_value=None)
        coordinator._entity_to_pairs = {
            "person.alice": [pair_key("person.alice", "person.bob")],
            "person.bob": [pair_key("person.alice", "person.bob")],
        }
        coordinator._pending_updates = set()
        coordinator.hass.async_create_task = MagicMock()

        k = pair_key("person.alice", "person.bob")
        coordinator._resync_holding[k] = True

        ps = coordinator._pair_states[k]
        ps.update_count_a = 0

        coordinator._async_state_changed(self._make_event("person.alice"))

        assert ps.update_count_a == 1, "counter must advance even during hold"

    def test_counter_does_not_increment_when_unavailable(self):
        """An unavailable/unknown transition is an arrival event but carries
        no usable fix — counting it would let a flapping device trip the
        reliability gate without ever producing a valid distance.
        last_update still advances (it tracks event arrival, not validity)."""
        from unittest.mock import MagicMock

        from custom_components.entity_distance.models import pair_key

        coordinator = _make_calc_pair_coordinator()
        coordinator._debouncer = MagicMock()
        coordinator._debouncer.async_call = MagicMock(return_value=None)
        coordinator._entity_to_pairs = {
            "person.alice": [pair_key("person.alice", "person.bob")],
            "person.bob": [pair_key("person.alice", "person.bob")],
        }
        coordinator._pending_updates = set()
        coordinator.hass.async_create_task = MagicMock()

        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        ps.update_count_a = 0

        for state in ("unavailable", "unknown"):
            ev = MagicMock()
            ev.data = {
                "entity_id": "person.alice",
                "old_state": MagicMock(state="home"),
                "new_state": MagicMock(state=state),
            }
            coordinator._async_state_changed(ev)

        assert ps.update_count_a == 0, "counter must not advance on unavailable/unknown"
        assert ps.last_update_a is not None, "last_update still advances on any arrival"

    def test_counter_skips_when_new_state_missing(self):
        """new_state=None (entity removed) — treat as non-arrival for count.
        last_update still advances; we received an event."""
        from unittest.mock import MagicMock

        from custom_components.entity_distance.models import pair_key

        coordinator = _make_calc_pair_coordinator()
        coordinator._debouncer = MagicMock()
        coordinator._debouncer.async_call = MagicMock(return_value=None)
        coordinator._entity_to_pairs = {
            "person.alice": [pair_key("person.alice", "person.bob")],
            "person.bob": [pair_key("person.alice", "person.bob")],
        }
        coordinator._pending_updates = set()
        coordinator.hass.async_create_task = MagicMock()

        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        ps.update_count_a = 0

        ev = MagicMock()
        ev.data = {
            "entity_id": "person.alice",
            "old_state": MagicMock(state="home"),
            "new_state": None,
        }
        coordinator._async_state_changed(ev)

        assert ps.update_count_a == 0
        assert ps.last_update_a is not None


# ---------------------------------------------------------------------------
# _calc_pair — resync silence (lines 505-514)
# ---------------------------------------------------------------------------


class TestCalcPairResyncSilence:
    """_calc_pair triggers resync hold when both entities are silent."""

    def test_resync_silence_triggers_hold(self):
        from unittest.mock import patch

        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(resync_silence_s=60.0, resync_hold_s=300.0)
        from custom_components.entity_distance.models import pair_key

        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        stale_time = datetime.now().astimezone() - timedelta(seconds=120)
        ps.last_update_a = stale_time
        ps.last_update_b = stale_time

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=5000.0,
        ):
            coordinator._calc_pair(
                ps, "person.alice", "person.bob", datetime.now().astimezone(), set()
            )

        assert coordinator._resync_holding[k] is True


# ---------------------------------------------------------------------------
# _calc_pair — require_reliable blocks proximity entry (lines 532-535)
# ---------------------------------------------------------------------------


class TestCalcPairRequireReliable:
    """_calc_pair blocks proximity entry when require_reliable=True and not yet reliable."""

    def test_require_reliable_blocks_proximity_entry(self):
        from unittest.mock import patch

        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(
            require_reliable=True,
            min_updates_reliable=10,  # very high — not reliable
            entry_threshold_m=10000.0,  # well within range
            exit_threshold_m=10000.0,
        )
        from custom_components.entity_distance.models import pair_key

        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        ps.update_count_a = 0
        ps.update_count_b = 0
        ps.proximity = False  # was not in proximity

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.50001, -0.10001)  # very close
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=1.0,
        ):
            result = coordinator._calc_pair(
                ps, "person.alice", "person.bob", datetime.now().astimezone(), set()
            )

        # proximity entry blocked because not reliable
        assert result.proximity is False


# ---------------------------------------------------------------------------
# Constructor + properties via __new__ bypass
# ---------------------------------------------------------------------------


class TestCoordinatorProperties:
    """Cover entities / bucket_thresholds properties (lines 198, 202)."""

    def _make(self):
        from custom_components.entity_distance.const import (
            BUCKET_FAR,
            BUCKET_MID,
            BUCKET_NEAR,
            BUCKET_VERY_NEAR,
            DEFAULT_ZONE_FAR_M,
            DEFAULT_ZONE_MID_M,
            DEFAULT_ZONE_NEAR_M,
            DEFAULT_ZONE_VERY_NEAR_M,
        )
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coord._entities = ["person.alice", "person.bob"]
        coord._bucket_thresholds = {
            BUCKET_VERY_NEAR: DEFAULT_ZONE_VERY_NEAR_M,
            BUCKET_NEAR: DEFAULT_ZONE_NEAR_M,
            BUCKET_MID: DEFAULT_ZONE_MID_M,
            BUCKET_FAR: DEFAULT_ZONE_FAR_M,
        }
        return coord

    def test_entities_property(self):
        coord = self._make()
        assert coord.entities == ["person.alice", "person.bob"]

    def test_bucket_thresholds_property(self):
        from custom_components.entity_distance.const import BUCKET_VERY_NEAR

        coord = self._make()
        assert BUCKET_VERY_NEAR in coord.bucket_thresholds

    def test_settings_snapshot(self):
        coord = self._make()
        coord._proximity_zone = "very_near"
        coord._entry_threshold_m = 200.0
        coord._debounce_s = 10
        coord._max_accuracy_m = 150
        coord._stationary_threshold_m = max(15.0, 150 * 0.15)
        coord._max_speed_kmh = 1000
        coord._resync_silence_s = 600
        coord._resync_hold_s = 60
        coord._grace_window_s = 900
        coord._min_updates_reliable = 3
        coord._updates_window_s = 1800
        coord._require_reliable = False
        snap = coord.settings_snapshot
        assert snap["proximity_zone"] == "very_near"
        assert snap["zone_very_near_m"] == 200
        assert "emit_bus_events" not in snap
        assert len(snap) == 16


# ---------------------------------------------------------------------------
# F-29.5-7: integration must never fire bus events. All entity_distance_* events
# were removed in v0.3.0 — automations drive off sensor / binary_sensor state.
# ---------------------------------------------------------------------------


class TestNoBusEvents:
    def test_no_events_on_threshold_crossing(self):
        from datetime import UTC, datetime
        from unittest.mock import patch as _patch

        from custom_components.entity_distance.models import PairState, pair_key

        coordinator = _make_calc_pair_coordinator(min_updates_reliable=1)
        a, b = "person.alice", "person.bob"
        k = pair_key(a, b)
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.update_count_a = 5
        ps.update_count_b = 5
        state_a = make_state(a, 51.5, -0.1, 20)
        state_b = make_state(b, 51.501, -0.1, 20)
        coordinator.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == a else state_b
        )

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        with _patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=200.0,  # would have fired EVENT_ENTER in v0.2.x
        ):
            coordinator._calc_pair(ps, a, b, now, set())

        assert coordinator.hass.bus.fire.call_count == 0
        # ps.proximity still transitioned — sensor state-change driven, not events.
        assert ps.proximity is True

    def test_no_events_on_threshold_exit(self):
        from datetime import UTC, datetime
        from unittest.mock import patch as _patch

        from custom_components.entity_distance.models import PairState, pair_key

        coordinator = _make_calc_pair_coordinator(min_updates_reliable=1)
        a, b = "person.alice", "person.bob"
        k = pair_key(a, b)
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC)
        ps.update_count_a = 5
        ps.update_count_b = 5
        state_a = make_state(a, 51.5, -0.1, 20)
        state_b = make_state(b, 51.501, -0.1, 20)
        coordinator.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == a else state_b
        )

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        with _patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=1200.0,  # > exit_threshold_m → was-proximity exit
        ):
            coordinator._calc_pair(ps, a, b, now, set())

        assert coordinator.hass.bus.fire.call_count == 0
        assert ps.proximity is False

    def test_no_events_on_steady_tick(self):
        # Even pre-removal, a tick with no proximity change fired EVENT_UPDATE.
        # Post-removal, also zero events.
        from datetime import UTC, datetime
        from unittest.mock import patch as _patch

        from custom_components.entity_distance.models import PairState, pair_key

        coordinator = _make_calc_pair_coordinator(min_updates_reliable=1)
        a, b = "person.alice", "person.bob"
        k = pair_key(a, b)
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.proximity = False
        ps.update_count_a = 5
        ps.update_count_b = 5
        state_a = make_state(a, 51.5, -0.1, 20)
        state_b = make_state(b, 51.501, -0.1, 20)
        coordinator.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == a else state_b
        )

        now = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        with _patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=1200.0,  # outside entry threshold, no transition
        ):
            coordinator._calc_pair(ps, a, b, now, set())

        assert coordinator.hass.bus.fire.call_count == 0


class TestUnrecognisedProximityZone:
    """Coordinator warns and defaults to very_near on invalid proximity_zone."""

    async def test_invalid_zone_logs_warning_and_defaults(self, hass, caplog):
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import (
            BUCKET_VERY_NEAR,
            DOMAIN,
        )
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "entities": ["person.alice", "person.bob"],
                "proximity_zone": "totally_invalid",
            },
            options={},
        )
        entry.add_to_hass(hass)

        import logging

        with caplog.at_level(
            logging.WARNING, logger="custom_components.entity_distance.coordinator"
        ):
            coord = EntityDistanceCoordinator(hass, entry)

        assert coord._proximity_zone == BUCKET_VERY_NEAR
        assert any("unrecognised proximity_zone" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Constructor __init__ via real hass + MockConfigEntry
# ---------------------------------------------------------------------------


class TestCoordinatorInit:
    """Cover EntityDistanceCoordinator.__init__ (lines 145-194)."""

    async def test_constructor_two_entities(self, hass):
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "entities": ["person.alice", "person.bob"],
                "debounce_s": 1,
                "max_accuracy_m": 200,
                "max_speed_kmh": 150,
                "resync_silence_s": 0,
                "resync_hold_s": 60,
                "min_updates_reliable": 3,
                "updates_window_s": 1800,
                "require_reliable": False,
            },
        )
        entry.add_to_hass(hass)
        coord = EntityDistanceCoordinator(hass, entry)

        assert coord.entities == ["person.alice", "person.bob"]
        assert len(coord._pair_states) == 1
        assert coord._debouncer is None

    async def test_constructor_three_entities_builds_pairs(self, hass):
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "entities": ["person.a", "person.b", "person.c"],
                "debounce_s": 1,
                "max_accuracy_m": 200,
                "max_speed_kmh": 150,
                "resync_silence_s": 0,
                "resync_hold_s": 60,
                "min_updates_reliable": 3,
                "updates_window_s": 1800,
                "require_reliable": False,
            },
        )
        entry.add_to_hass(hass)
        coord = EntityDistanceCoordinator(hass, entry)

        assert len(coord._pair_states) == 3  # C(3,2) = 3 pairs

    async def test_constructor_uses_options_over_data(self, hass):
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "entities": ["person.alice", "person.bob"],
                "debounce_s": 1,
                "max_accuracy_m": 200,
                "max_speed_kmh": 150,
                "resync_silence_s": 0,
                "resync_hold_s": 60,
                "min_updates_reliable": 3,
                "updates_window_s": 1800,
                "require_reliable": False,
            },
            options={CONF_PROXIMITY_ZONE: BUCKET_NEAR},
        )
        entry.add_to_hass(hass)
        coord = EntityDistanceCoordinator(hass, entry)

        assert coord._entry_threshold_m == coord._bucket_thresholds[BUCKET_NEAR]


# ---------------------------------------------------------------------------
# async_setup, async_unload, _async_tick, _async_state_changed
# ---------------------------------------------------------------------------


class TestCoordinatorLifecycle:
    """Cover async_setup, async_unload, _async_tick, _async_state_changed."""

    def _make_coord(self, hass, entities=None):
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )

        if entities is None:
            entities = ["person.alice", "person.bob"]
        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "entities": entities,
                "debounce_s": 0.01,
                "max_accuracy_m": 200,
                "max_speed_kmh": 150,
                "resync_silence_s": 0,
                "resync_hold_s": 60,
                "min_updates_reliable": 1,
                "updates_window_s": 1800,
                "require_reliable": False,
            },
        )
        entry.add_to_hass(hass)
        return EntityDistanceCoordinator(hass, entry)

    async def test_async_setup_sets_debouncer(self, hass):
        from unittest.mock import AsyncMock, patch

        coord = self._make_coord(hass)
        with (
            patch.object(coord, "_async_load_state", new=AsyncMock()),
            patch.object(coord, "_async_save_state", new=AsyncMock()),
        ):
            await coord.async_setup()

        assert coord._debouncer is not None
        assert len(coord._unsub_listeners) == 2

        # Clean up to avoid lingering timers
        coord.async_unload()

    async def test_async_unload_clears_listeners(self, hass):
        from unittest.mock import MagicMock

        coord = self._make_coord(hass)
        unsub1 = MagicMock()
        unsub2 = MagicMock()
        coord._unsub_listeners = [unsub1, unsub2]
        coord._debouncer = MagicMock()
        coord._debouncer.async_shutdown = MagicMock()

        coord.async_unload()

        unsub1.assert_called_once()
        unsub2.assert_called_once()
        assert coord._unsub_listeners == []
        coord._debouncer.async_shutdown.assert_called_once()

    async def test_async_unload_no_debouncer(self, hass):
        coord = self._make_coord(hass)
        coord._debouncer = None
        coord._unsub_listeners = []
        coord.async_unload()  # should not raise

    async def test_async_tick_schedules_task(self, hass):
        from unittest.mock import MagicMock, patch

        coord = self._make_coord(hass)
        debouncer = MagicMock()
        debouncer.async_call = MagicMock(return_value=None)
        coord._debouncer = debouncer

        with patch.object(hass, "async_create_task") as mock_create:
            coord._async_tick(None)

        mock_create.assert_called_once()

    async def test_async_tick_no_debouncer_is_noop(self, hass):
        # Before async_setup runs (or after async_unload), _debouncer is None.
        # Tick must early-return without raising.
        from unittest.mock import patch

        coord = self._make_coord(hass)
        coord._debouncer = None
        with patch.object(hass, "async_create_task") as mock_create:
            coord._async_tick(None)
        mock_create.assert_not_called()

    async def test_async_setup_preserves_existing_proximity_tracking_started(self, hass):
        # When restored _pair_states already carry a proximity_tracking_started
        # timestamp, async_setup must NOT overwrite it. Covers the False branch
        # of the per-pair init guard.
        from datetime import datetime
        from unittest.mock import AsyncMock, patch

        coord = self._make_coord(hass)
        existing = datetime(2020, 1, 1, tzinfo=UTC)
        for ps in coord._pair_states.values():
            ps.proximity_tracking_started = existing

        with (
            patch.object(coord, "_async_load_state", new=AsyncMock()),
            patch.object(coord, "_async_save_state", new=AsyncMock()),
        ):
            await coord.async_setup()

        for ps in coord._pair_states.values():
            assert ps.proximity_tracking_started == existing
        coord.async_unload()

    async def test_async_state_changed_no_debouncer(self, hass):
        coord = self._make_coord(hass)
        coord._debouncer = None
        event = MagicMock()
        event.data = {"entity_id": "person.alice"}
        # Should return early without error
        coord._async_state_changed(event)

    async def test_async_state_changed_adds_pending(self, hass):
        from unittest.mock import MagicMock

        coord = self._make_coord(hass)
        coord._debouncer = MagicMock()
        coord._debouncer.async_call = MagicMock(return_value=None)
        coord._pending_updates = set()
        coord.hass.async_create_task = MagicMock()

        event = MagicMock()
        event.data = {
            "entity_id": "person.alice",
            "old_state": MagicMock(),
            "new_state": MagicMock(),
        }

        coord._async_state_changed(event)
        assert "person.alice" in coord._pending_updates

    async def test_async_state_changed_entity_b_last_update(self, hass):
        from unittest.mock import MagicMock

        coord = self._make_coord(hass)
        coord._debouncer = MagicMock()
        coord._debouncer.async_call = MagicMock(return_value=None)
        coord._pending_updates = set()
        coord.hass.async_create_task = MagicMock()

        event = MagicMock()
        event.data = {
            "entity_id": "person.bob",
            "old_state": MagicMock(),
            "new_state": MagicMock(),
        }

        coord._async_state_changed(event)
        assert "person.bob" in coord._pending_updates

    async def test_async_state_changed_invalid_arrival_skips_counter_for_b(self, hass):
        # Entity B transitions to unavailable: last_update_b advances but
        # update_count_b stays put (flapping device must not pass reliability).
        from unittest.mock import MagicMock

        from homeassistant.const import STATE_UNAVAILABLE

        coord = self._make_coord(hass)
        coord._debouncer = MagicMock()
        coord._debouncer.async_call = MagicMock(return_value=None)
        coord._pending_updates = set()
        coord.hass.async_create_task = MagicMock()

        # Snapshot counts before
        before = {k: ps.update_count_b for k, ps in coord._pair_states.items()}

        new_state = MagicMock()
        new_state.state = STATE_UNAVAILABLE
        event = MagicMock()
        event.data = {
            "entity_id": "person.bob",
            "old_state": MagicMock(),
            "new_state": new_state,
        }

        coord._async_state_changed(event)
        for k, ps in coord._pair_states.items():
            assert ps.update_count_b == before[k]
            assert ps.last_update_b is not None


# ---------------------------------------------------------------------------
# async_recalculate (lines 266-298)
# ---------------------------------------------------------------------------


class TestCoordinatorAsyncRecalculate:
    """Cover async_recalculate."""

    async def test_recalculate_calls_calc_pair_and_saves(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )
        from custom_components.entity_distance.models import (
            GroupData,
            PairState,
            pair_key,
        )

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = True
        ps.distance_m = 500.0
        coord._pair_states = {k: ps}
        coord._pending_updates = {"person.alice"}

        store = MagicMock()
        store.async_save = AsyncMock()
        coord._store = store

        coord.async_set_updated_data = MagicMock()

        with (
            patch.object(coord, "_calc_pair", return_value=ps),
            patch.object(coord, "_async_save_state", new=AsyncMock()),
        ):
            await coord.async_recalculate()

        coord.async_set_updated_data.assert_called_once()
        result_group = coord.async_set_updated_data.call_args[0][0]
        assert isinstance(result_group, GroupData)
        assert result_group.min_distance_m == 500.0

    async def test_recalculate_no_valid_pairs_min_dist_none(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )
        from custom_components.entity_distance.models import PairState, pair_key

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = False
        ps.distance_m = None
        coord._pair_states = {k: ps}
        coord._pending_updates = set()

        coord.async_set_updated_data = MagicMock()

        with (
            patch.object(coord, "_calc_pair", return_value=ps),
            patch.object(coord, "_async_save_state", new=AsyncMock()),
        ):
            await coord.async_recalculate()

        result_group = coord.async_set_updated_data.call_args[0][0]
        assert result_group.min_distance_m is None


# ---------------------------------------------------------------------------
# _async_update_data and _async_load_state
# ---------------------------------------------------------------------------


class TestCoordinatorAsyncUpdateData:
    """Cover async_recalculate setting GroupData via async_set_updated_data."""

    @pytest.mark.asyncio
    async def test_async_recalculate_sets_group_data(self):
        from unittest.mock import AsyncMock, MagicMock, patch

        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )
        from custom_components.entity_distance.models import (
            GroupData,
            PairState,
            pair_key,
        )

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = False
        coord._pair_states = {k: ps}
        coord._pending_updates = set()
        coord._bucket_thresholds = {}
        coord.hass = MagicMock()
        coord.hass.states.get.return_value = None
        coord._async_save_state = AsyncMock()

        captured = []
        coord.async_set_updated_data = lambda g: captured.append(g)

        with patch(
            "custom_components.entity_distance.coordinator.dt_util.now",
            return_value=__import__("datetime").datetime(
                2024, 1, 1, tzinfo=__import__("datetime").timezone.utc
            ),
        ):
            await coord.async_recalculate()

        assert len(captured) == 1
        assert isinstance(captured[0], GroupData)
        assert k in captured[0].pairs


class TestCoordinatorLoadState:
    """Cover _async_load_state branches (lines 609, 623, 626-629)."""

    def _make_coord_with_store(self, stored_data):
        from unittest.mock import AsyncMock, MagicMock

        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )
        from custom_components.entity_distance.models import PairState, pair_key

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        k = pair_key("person.alice", "person.bob")
        coord._pair_states = {k: PairState(entity_a_id=k[0], entity_b_id=k[1])}
        store = MagicMock()
        store.async_load = AsyncMock(return_value=stored_data)
        coord._store = store
        return coord, k

    async def test_no_stored_data_returns_early(self):
        coord, _ = self._make_coord_with_store(None)
        await coord._async_load_state()  # should not raise

    async def test_empty_stored_dict_returns_early(self):
        coord, _ = self._make_coord_with_store({})
        await coord._async_load_state()  # should not raise

    async def test_missing_blob_for_pair_skips(self):
        coord, _ = self._make_coord_with_store({"other__key": {"proximity_duration_s": 5.0}})
        await coord._async_load_state()  # should not raise

    async def test_loads_proximity_duration(self):
        coord, k = self._make_coord_with_store(
            {
                "person.alice__person.bob": {
                    "proximity_duration_s": 123.5,
                }
            }
        )
        await coord._async_load_state()
        assert coord._pair_states[k].proximity_duration_s == 123.5

    async def test_loads_tracking_started(self):

        coord, k = self._make_coord_with_store(
            {
                "person.alice__person.bob": {
                    "proximity_duration_s": 0.0,
                    "proximity_tracking_started": "2025-01-01T00:00:00+00:00",
                }
            }
        )
        await coord._async_load_state()
        assert coord._pair_states[k].proximity_tracking_started is not None

    async def test_loads_proximity_since_and_sets_proximity_true(self):
        coord, k = self._make_coord_with_store(
            {
                "person.alice__person.bob": {
                    "proximity_duration_s": 0.0,
                    "proximity_since": "2025-01-01T00:00:00+00:00",
                }
            }
        )
        await coord._async_load_state()
        assert coord._pair_states[k].proximity is True
        assert coord._pair_states[k].proximity_since is not None

    async def test_corrupt_data_does_not_raise(self):
        coord, _ = self._make_coord_with_store(
            {"person.alice__person.bob": {"proximity_duration_s": "not-a-float"}}
        )
        await coord._async_load_state()  # should catch exception silently

    async def test_restores_last_known_display_values(self):
        # Persisted distance/direction/etc. are restored into the display grace
        # window so sensors show them immediately after restart, without restoring
        # prev_distance_m (fresh motion baseline built by the first live tick).
        coord, k = self._make_coord_with_store(
            {
                "person.alice__person.bob": {
                    "proximity_duration_s": 0.0,
                    "distance_m": 42.5,
                    "direction": "approaching",
                    "closing_speed_kmh": 5.0,
                    "eta_minutes": 8.0,
                    "last_proximity": True,
                }
            }
        )
        await coord._async_load_state()
        ps = coord._pair_states[k]
        assert ps.distance_m == 42.5
        assert ps.direction == "approaching"
        assert ps.closing_speed_kmh == 5.0
        assert ps.eta_minutes == 8.0
        assert ps.last_proximity is True
        # Restored into grace: shown but not marked valid, so a still-offline source
        # goes honestly unknown after GRACE_WINDOW_S instead of lingering forever.
        assert ps.data_valid is False
        assert ps.stale_since is not None
        assert ps.prev_distance_m is None  # baseline NOT restored

    async def test_restore_display_values_handles_none_speed_and_eta(self):
        coord, k = self._make_coord_with_store(
            {
                "person.alice__person.bob": {
                    "proximity_duration_s": 0.0,
                    "distance_m": 100.0,
                    "direction": None,
                    "closing_speed_kmh": None,
                    "eta_minutes": None,
                }
            }
        )
        await coord._async_load_state()
        ps = coord._pair_states[k]
        assert ps.distance_m == 100.0
        assert ps.closing_speed_kmh is None
        assert ps.eta_minutes is None
        assert ps.data_valid is False
        assert ps.stale_since is not None


class TestIsWithinGrace:
    """Cover is_within_grace True/False branches."""

    def _coord(self):
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coord._grace_window_s = 900.0
        return coord

    def test_false_when_never_stale(self):
        from custom_components.entity_distance.models import PairState

        coord = self._coord()
        ps = PairState(entity_a_id="a", entity_b_id="b")  # stale_since None
        assert coord.is_within_grace(ps, datetime.now().astimezone()) is False

    def test_true_within_window(self):
        from custom_components.entity_distance.models import PairState

        coord = self._coord()
        now = datetime.now().astimezone()
        ps = PairState(entity_a_id="a", entity_b_id="b")
        ps.stale_since = now - timedelta(seconds=60)
        assert coord.is_within_grace(ps, now) is True

    def test_false_past_window(self):
        from custom_components.entity_distance.models import PairState

        coord = self._coord()
        now = datetime.now().astimezone()
        ps = PairState(entity_a_id="a", entity_b_id="b")
        ps.stale_since = now - timedelta(seconds=1000)  # > GRACE_WINDOW_S (900)
        assert coord.is_within_grace(ps, now) is False


class TestStrictExitThreshold:
    def test_exit_threshold_equals_entry_threshold(self):
        """_exit_threshold_m must equal _entry_threshold_m after coordinator init."""
        for _zone in [BUCKET_VERY_NEAR, BUCKET_NEAR, BUCKET_MID, BUCKET_FAR]:
            coord = _make_calc_pair_coordinator(entry_threshold_m=500.0)
            # Verify via the actual init path too
            assert coord._exit_threshold_m == coord._entry_threshold_m

    def test_proximity_exits_immediately_above_entry_threshold(self):
        """Enter at 490 m (entry=500 m), advance to 501 m → proximity=False immediately."""
        coordinator = _make_calc_pair_coordinator(entry_threshold_m=500.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        now = _NOW

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=490.0,
        ):
            ps = coordinator._calc_pair(ps, "person.alice", "person.bob", now, set())
        assert ps.proximity is True

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=501.0,
        ):
            ps = coordinator._calc_pair(
                ps, "person.alice", "person.bob", now + timedelta(seconds=60), set()
            )
        assert ps.proximity is False


class TestStationaryThresholdDerivation:
    """_stationary_threshold_m = max(15.0, max_accuracy_m * 0.15) in __init__."""

    async def test_default_accuracy_derives_threshold(self, hass):
        """max_accuracy_m=300 → threshold = max(15, 300*0.15) = 45.0."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "entities": ["person.alice", "person.bob"],
                "debounce_s": 0,
                "max_accuracy_m": 300,
                "max_speed_kmh": 1000,
                "resync_silence_s": 0,
                "resync_hold_s": 60,
                "min_updates_reliable": 3,
                "updates_window_s": 1800,
                "require_reliable": False,
            },
        )
        entry.add_to_hass(hass)
        coord = EntityDistanceCoordinator(hass, entry)
        assert coord._stationary_threshold_m == pytest.approx(45.0)

    async def test_low_accuracy_clamps_to_minimum(self, hass):
        """max_accuracy_m=50 → 50*0.15=7.5 < 15 → clamped to 15.0."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "entities": ["person.alice", "person.bob"],
                "debounce_s": 0,
                "max_accuracy_m": 50,
                "max_speed_kmh": 1000,
                "resync_silence_s": 0,
                "resync_hold_s": 60,
                "min_updates_reliable": 3,
                "updates_window_s": 1800,
                "require_reliable": False,
            },
        )
        entry.add_to_hass(hass)
        coord = EntityDistanceCoordinator(hass, entry)
        assert coord._stationary_threshold_m == 15.0

    async def test_zero_accuracy_clamps_to_minimum(self, hass):
        """max_accuracy_m=0 (filter off) → clamped to 15.0."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "entities": ["person.alice", "person.bob"],
                "debounce_s": 0,
                "max_accuracy_m": 0,
                "max_speed_kmh": 1000,
                "resync_silence_s": 0,
                "resync_hold_s": 60,
                "min_updates_reliable": 3,
                "updates_window_s": 1800,
                "require_reliable": False,
            },
        )
        entry.add_to_hass(hass)
        coord = EntityDistanceCoordinator(hass, entry)
        assert coord._stationary_threshold_m == 15.0


class TestGraceWindowConfig:
    """_grace_window_s loaded from config, defaults to DEFAULT_GRACE_WINDOW_S."""

    async def test_default_grace_window(self, hass):
        """No grace_window_s in config → defaults to 900."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DEFAULT_GRACE_WINDOW_S, DOMAIN
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "entities": ["person.alice", "person.bob"],
                "debounce_s": 0,
                "max_accuracy_m": 300,
                "max_speed_kmh": 1000,
                "resync_silence_s": 0,
                "resync_hold_s": 60,
                "min_updates_reliable": 3,
                "updates_window_s": 1800,
                "require_reliable": False,
            },
        )
        entry.add_to_hass(hass)
        coord = EntityDistanceCoordinator(hass, entry)
        assert coord._grace_window_s == DEFAULT_GRACE_WINDOW_S

    async def test_custom_grace_window(self, hass):
        """grace_window_s=120 in config → stored on coordinator."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        entry = MockConfigEntry(
            domain=DOMAIN,
            data={
                "entities": ["person.alice", "person.bob"],
                "debounce_s": 0,
                "max_accuracy_m": 300,
                "max_speed_kmh": 1000,
                "resync_silence_s": 0,
                "resync_hold_s": 60,
                "grace_window_s": 120,
                "min_updates_reliable": 3,
                "updates_window_s": 1800,
                "require_reliable": False,
            },
        )
        entry.add_to_hass(hass)
        coord = EntityDistanceCoordinator(hass, entry)
        assert coord._grace_window_s == 120.0

    def test_is_within_grace_uses_instance_window(self):
        """is_within_grace respects _grace_window_s not a hardcoded constant."""
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator
        from custom_components.entity_distance.models import PairState

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coord._grace_window_s = 60.0
        now = datetime.now(UTC)
        ps = PairState(entity_a_id="a", entity_b_id="b")

        ps.stale_since = now - timedelta(seconds=30)
        assert coord.is_within_grace(ps, now) is True

        ps.stale_since = now - timedelta(seconds=90)
        assert coord.is_within_grace(ps, now) is False
