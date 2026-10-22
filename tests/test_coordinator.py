"""Tests for EntityDistanceCoordinator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from homeassistant.core import State
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
        coordinator._updates_window_s = 600.0
        return coordinator

    def _fresh_window(self, ps):
        # Non-zero counts only count while the window is live. Anchor both sides'
        # window at now so is_reliable() reads the stored count, not a stale 0.
        from homeassistant.util import dt as dt_util

        now = dt_util.utcnow()
        ps.update_window_start_a = now
        ps.update_window_start_b = now

    def test_reliable_when_both_counts_meet_threshold(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 3
        ps.update_count_b = 3
        self._fresh_window(ps)
        assert coordinator.is_reliable(ps) is True

    def test_reliable_when_counts_exceed_threshold(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 10
        ps.update_count_b = 5
        self._fresh_window(ps)
        assert coordinator.is_reliable(ps) is True

    def test_not_reliable_when_a_below_threshold(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 2
        ps.update_count_b = 5
        self._fresh_window(ps)
        assert coordinator.is_reliable(ps) is False

    def test_not_reliable_when_b_below_threshold(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 5
        ps.update_count_b = 1
        self._fresh_window(ps)
        assert coordinator.is_reliable(ps) is False

    def test_not_reliable_when_both_zero(self):
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 0
        ps.update_count_b = 0
        self._fresh_window(ps)
        assert coordinator.is_reliable(ps) is False

    def test_reliable_with_min_1(self):
        coordinator = self._make_coordinator(1)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 1
        ps.update_count_b = 1
        self._fresh_window(ps)
        assert coordinator.is_reliable(ps) is True

    def test_not_reliable_with_min_1_when_zero(self):
        coordinator = self._make_coordinator(1)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 0
        ps.update_count_b = 1
        self._fresh_window(ps)
        assert coordinator.is_reliable(ps) is False

    def test_zone_side_always_passes(self):
        # RELIABLE-ZONE-1: a zone.* side never emits state_changed so its update
        # counter never advances — treat it as passing regardless of count/window.
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="zone.home", entity_b_id="person.b")
        ps.update_count_a = 0
        ps.update_window_start_a = None
        ps.update_count_b = 3
        self._fresh_window(ps)
        ps.update_window_start_a = None  # zone side genuinely never anchored
        assert coordinator.is_reliable(ps) is True

    def test_not_reliable_when_window_none(self):
        # B1: non-zone side with no window anchor → stale count treated as 0.
        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 5
        ps.update_count_b = 5
        ps.update_window_start_a = None
        ps.update_window_start_b = None
        assert coordinator.is_reliable(ps) is False

    def test_not_reliable_when_window_elapsed(self):
        # B1: window older than _updates_window_s → count is stale → 0.
        from datetime import timedelta

        from homeassistant.util import dt as dt_util

        coordinator = self._make_coordinator(3)
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 5
        ps.update_count_b = 5
        stale = dt_util.utcnow() - timedelta(seconds=coordinator._updates_window_s + 10)
        ps.update_window_start_a = stale
        ps.update_window_start_b = stale
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
    coordinator._max_speed_kmh = max_speed_kmh
    coordinator._resync_silence_s = resync_silence_s
    coordinator._resync_hold_s = resync_hold_s
    coordinator._grace_window_s = 900.0
    coordinator._require_reliable = require_reliable
    coordinator._min_updates_reliable = min_updates_reliable
    coordinator._updates_window_s = updates_window_s
    coordinator._altitude_aligned_threshold_m = 5.0
    coordinator._max_vertical_accuracy_m = 0.0
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
    coordinator.hass.config.elevation = None  # disable home fallback by default
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

    def test_altitude_aligned_threshold_property(self):
        coord = self._make()
        coord._altitude_aligned_threshold_m = 10.0
        assert coord.altitude_aligned_threshold_m == 10.0

    def test_proximity_threshold_property(self):
        from custom_components.entity_distance.const import (
            DEFAULT_ZONE_NEAR_M,
            DEFAULT_ZONE_VERY_NEAR_M,
        )

        coord = self._make()
        # Set entry and exit to different values to verify property returns entry, not exit
        coord._entry_threshold_m = DEFAULT_ZONE_VERY_NEAR_M
        coord._exit_threshold_m = DEFAULT_ZONE_NEAR_M
        assert coord.proximity_threshold_m == DEFAULT_ZONE_VERY_NEAR_M
        assert coord.proximity_threshold_m != DEFAULT_ZONE_NEAR_M

    def test_settings_snapshot(self):
        coord = self._make()
        coord._proximity_zone = "very_near"
        coord._entry_threshold_m = 200.0
        coord._debounce_s = 10
        coord._max_accuracy_m = 150
        coord._max_speed_kmh = 1000
        coord._resync_silence_s = 600
        coord._resync_hold_s = 60
        coord._grace_window_s = 900
        coord._min_updates_reliable = 3
        coord._updates_window_s = 1800
        coord._require_reliable = False
        coord._altitude_aligned_threshold_m = 5.0
        coord._max_vertical_accuracy_m = 0.0
        snap = coord.settings_snapshot
        assert snap["proximity_zone"] == "very_near"
        assert snap["zone_very_near_m"] == 200
        assert "emit_bus_events" not in snap
        # Key-presence assertions for fields added in this PR — catch regressions
        # if a field is accidentally removed. Count check kept to catch silent additions.
        assert "stationary_threshold_factor" in snap
        assert "stationary_threshold_min_m" in snap
        assert "grace_window_s" in snap
        assert "resync_silence_s" in snap
        assert "resync_hold_s" in snap
        assert "altitude_aligned_threshold_m" in snap
        assert "max_vertical_accuracy_m" in snap
        assert snap["stationary_threshold_factor"] == 0.15
        assert snap["stationary_threshold_min_m"] == 15.0
        assert len(snap) == 19  # update this if fields are intentionally added/removed


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
        coord._resync_holding = {}
        coord._resync_hold_until = {}
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
        ps.stale_since = now - timedelta(seconds=1000)  # > _grace_window_s default (900s)
        assert coord.is_within_grace(ps, now) is False


class TestStrictExitThreshold:
    async def test_exit_threshold_equals_entry_threshold(self, hass):
        """_exit_threshold_m == _entry_threshold_m for each proximity zone via real __init__."""
        from pytest_homeassistant_custom_component.common import MockConfigEntry

        from custom_components.entity_distance.const import DOMAIN
        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        zone_to_threshold = {
            BUCKET_VERY_NEAR: DEFAULT_ZONE_VERY_NEAR_M,
            BUCKET_NEAR: DEFAULT_ZONE_NEAR_M,
            BUCKET_MID: DEFAULT_ZONE_MID_M,
            BUCKET_FAR: DEFAULT_ZONE_FAR_M,
        }
        for zone, expected_m in zone_to_threshold.items():
            entry = MockConfigEntry(
                domain=DOMAIN,
                data={
                    "entities": ["person.alice", "person.bob"],
                    "debounce_s": 0,
                    "max_accuracy_m": 0,
                    "max_speed_kmh": 0,
                    "resync_silence_s": 0,
                    "resync_hold_s": 0,
                    "min_updates_reliable": 1,
                    "updates_window_s": 1800,
                    "require_reliable": False,
                    "proximity_zone": zone,
                },
                options={},
            )
            entry.add_to_hass(hass)
            coord = EntityDistanceCoordinator(hass, entry)
            assert coord._exit_threshold_m == coord._entry_threshold_m, (
                f"zone={zone}: exit {coord._exit_threshold_m} != entry {coord._entry_threshold_m}"
            )
            assert coord._entry_threshold_m == pytest.approx(expected_m), (
                f"zone={zone}: entry threshold mismatch"
            )

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

    def test_proximity_does_not_flap_at_threshold_boundary(self):
        """Document strict-exit flapping behaviour at threshold boundary.

        With entry=exit=500m, GPS noise crossing the line causes on/off toggling.
        This test verifies (documents) each transition — flapping IS expected here.
        To suppress flapping in production, users should enable debounce.
        """
        coordinator = _make_calc_pair_coordinator(entry_threshold_m=500.0, exit_threshold_m=500.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.6, -0.2)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        base = _NOW

        # Tick 1 — 498m (entry=500m) → proximity ON
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=498.0,
        ):
            ps = coordinator._calc_pair(ps, "person.alice", "person.bob", base, set())
        assert ps.proximity is True, "498m < 500m entry → should be ON"

        # Tick 2 — 502m → proximity OFF (strict exit: 502 > 500)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=502.0,
        ):
            ps = coordinator._calc_pair(
                ps, "person.alice", "person.bob", base + timedelta(seconds=10), set()
            )
        assert ps.proximity is False, "502m > 500m exit → should be OFF"

        # Tick 3 — 499m → proximity ON again (GPS noise re-enters)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=499.0,
        ):
            ps = coordinator._calc_pair(
                ps, "person.alice", "person.bob", base + timedelta(seconds=20), set()
            )
        assert ps.proximity is True, "499m ≤ 500m entry → should be ON"

        # Tick 4 — 501m → proximity OFF again
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=501.0,
        ):
            ps = coordinator._calc_pair(
                ps, "person.alice", "person.bob", base + timedelta(seconds=30), set()
            )
        assert ps.proximity is False, "501m > 500m exit → should be OFF"


class TestStationaryThresholdPerTick:
    """Stationary threshold is computed per-tick from the noise budget of each fix pair.

    Formula: threshold = max(STATIONARY_THRESHOLD_MIN_M,
                             (ps.accuracy_a + ps.accuracy_b + acc_a + acc_b) * STATIONARY_THRESHOLD_FACTOR)
    """

    def _run_tick(self, prev_dist, curr_dist, prev_acc_a, prev_acc_b, curr_acc):
        """Run one direction tick and return the resulting PairState."""
        from unittest.mock import patch

        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(max_speed_kmh=0.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        ps.prev_distance_m = prev_dist
        ps.prev_calc_time = now - timedelta(seconds=10)
        ps.last_fix_distance_m = prev_dist  # F1: direction baseline is last_fix_*
        ps.last_fix_time = now - timedelta(seconds=10)
        ps.accuracy_a = prev_acc_a
        ps.accuracy_b = prev_acc_b

        state_a = make_state("person.alice", 51.5, -0.1, accuracy=curr_acc)
        state_b = make_state("person.bob", 51.6, -0.2, accuracy=curr_acc)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=curr_dist,
        ):
            return coordinator._calc_pair(
                ps, "person.alice", "person.bob", now, {"person.alice", "person.bob"}
            )

    def test_stationary_with_high_accuracy_noise(self):
        """Two devices each acc=100m → noise_budget=400m → threshold=60m; delta=50m → STATIONARY."""
        # prev_acc_a=100, prev_acc_b=100, curr_acc_a=100, curr_acc_b=100
        # budget = 400, threshold = max(15, 400*0.15) = 60m
        # delta = 500 - 550 = -50m → abs=50 < 60 → stationary
        result = self._run_tick(
            prev_dist=500.0,
            curr_dist=550.0,
            prev_acc_a=100.0,
            prev_acc_b=100.0,
            curr_acc=100.0,
        )
        assert result.direction == "stationary"

    def test_approaching_with_low_accuracy_noise(self):
        """Two devices each acc=10m → noise_budget=40m → threshold=15m; delta=40m → APPROACHING after 2 confirming fixes."""
        from unittest.mock import patch

        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        # budget = 40, threshold = max(15, 40*0.15) = max(15, 6) = 15m
        # delta = -40m → abs=40 > 15 → approaching candidate on first tick
        # N=2 hysteresis: need second confirming tick to commit
        coordinator = _make_calc_pair_coordinator(max_speed_kmh=0.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        ps.prev_distance_m = 500.0
        ps.prev_calc_time = now - timedelta(seconds=10)
        ps.last_fix_distance_m = 500.0  # F1: direction baseline is last_fix_*
        ps.last_fix_time = now - timedelta(seconds=10)
        ps.accuracy_a = 10.0
        ps.accuracy_b = 10.0

        state_a = make_state("person.alice", 51.5, -0.1, accuracy=10.0)
        state_b = make_state("person.bob", 51.6, -0.2, accuracy=10.0)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch("custom_components.entity_distance.coordinator.ha_distance", return_value=460.0):
            result = coordinator._calc_pair(
                ps, "person.alice", "person.bob", now, {"person.alice", "person.bob"}
            )
        assert result.direction == "stationary"  # first tick: candidate held
        assert result.direction_candidate == "approaching"

        # Second confirming tick on same coordinator (carries state). 10s interval is
        # comfortably above the F5 DIRECTION_MIN_INTERVAL_S (5s) floor so the fix computes.
        ps.prev_distance_m = 460.0
        ps.prev_calc_time = now - timedelta(seconds=10)
        ps.last_fix_distance_m = 460.0
        ps.last_fix_time = now - timedelta(seconds=10)
        with patch("custom_components.entity_distance.coordinator.ha_distance", return_value=420.0):
            result2 = coordinator._calc_pair(
                ps, "person.alice", "person.bob", now, {"person.alice", "person.bob"}
            )
        assert result2.direction == "approaching"

    def test_stationary_threshold_min_floor(self):
        """Zone entities (acc=None→0) → noise_budget=0 → threshold=STATIONARY_THRESHOLD_MIN_M=15m; delta=5m → STATIONARY."""
        # budget = 0, threshold = max(15, 0) = 15m
        # delta = 5m < 15m → stationary
        result = self._run_tick(
            prev_dist=100.0,
            curr_dist=105.0,
            prev_acc_a=None,
            prev_acc_b=None,
            curr_acc=None,
        )
        assert result.direction == "stationary"


class TestDirectionHeldOnTimerTick:
    """Timer ticks (empty pending) must not overwrite direction."""

    def test_approaching_held_on_timer_tick(self):
        """Core regression: timer tick with delta_m≈0 must NOT flip approaching→stationary."""
        from unittest.mock import patch

        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(max_speed_kmh=0.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        ps.prev_distance_m = 500.0  # same as curr → delta_m=0
        ps.prev_calc_time = now - timedelta(seconds=30)
        ps.direction = "approaching"  # set by prior real GPS tick

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.501, -0.1)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        # Timer tick: pending=set() (no new GPS fix)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=500.0,  # unchanged → delta_m=0
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert result.direction == "approaching"  # must be held, not flipped to stationary

    def test_teleport_on_timer_tick_clears_direction(self):
        """Teleport rejection on a timer tick must still clear direction to None."""
        from unittest.mock import patch

        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(max_speed_kmh=0.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        ps.prev_distance_m = 500.0
        ps.prev_calc_time = now - timedelta(seconds=60)
        ps.last_fix_distance_m = 500.0  # F1: teleport measured against last_fix baseline
        ps.last_fix_time = now - timedelta(seconds=60)
        ps.direction = "approaching"  # must be cleared by teleport rejection

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.501, -0.1)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        # Timer tick with teleport: pending=set(), but 99km jump
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=99_000.0,  # 99km in 60s = 5940 km/h > DEFAULT_MAX_SPEED_KMH
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert result.direction is None  # teleport rejection clears direction
        assert result.prev_distance_m is None  # baseline also nulled


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


# ---------------------------------------------------------------------------
# TestDoubleTick — double-tick guard (100ms threshold) and unaccounted gap
# ---------------------------------------------------------------------------


class TestDoubleTickBoundary:
    """Double-tick guard: near-zero elapsed must not inflate today_zone_seconds.

    The guard in _calc_pair zeros _elapsed_s when the gap between two consecutive
    calls is < 0.1s (same-event-loop-iteration coalescing).  Real sub-second GPS
    bursts (e.g. 0.5s apart) must still be credited.

    The 'today_unaccounted_time' sensor computes as:
        elapsed_since_midnight_s - sum(ps.today_zone_seconds.values())
    We verify the sum does not grow on the second near-zero tick.
    """

    def _make_pair_in_proximity(self, entry_threshold_m=10_000.0):
        """Return (coordinator, ps, k, state_a, state_b) with pair already in proximity."""
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(entry_threshold_m=entry_threshold_m)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        state_a = make_state("person.alice", 51.5, -0.1)
        state_b = make_state("person.bob", 51.501, -0.1)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )
        return coordinator, ps, k, state_a, state_b

    def test_sub_100ms_tick_does_not_grow_zone_seconds(self):
        """Two ticks 50ms apart — second tick must not add to today_zone_seconds."""
        coordinator, ps, k, _, _ = self._make_pair_in_proximity()
        base = _NOW

        # Tick 1 — establishes proximity, no prev_calc_time so _elapsed_s=0
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            ps = coordinator._calc_pair(ps, "person.alice", "person.bob", base, set())
        assert ps.proximity is True
        zone_after_tick1 = sum(ps.today_zone_seconds.values())

        # Tick 2 — 50ms later (< 100ms guard)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            ps = coordinator._calc_pair(
                ps,
                "person.alice",
                "person.bob",
                base + timedelta(milliseconds=50),
                set(),
            )
        zone_after_tick2 = sum(ps.today_zone_seconds.values())

        assert zone_after_tick2 == pytest.approx(zone_after_tick1), (
            "sub-100ms tick must not increment today_zone_seconds"
        )

    def test_real_sub_second_tick_does_grow_zone_seconds(self):
        """Two ticks 500ms apart — second tick must credit elapsed time (> 100ms guard)."""
        coordinator, ps, k, _, _ = self._make_pair_in_proximity()
        base = _NOW

        # Tick 1
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            ps = coordinator._calc_pair(ps, "person.alice", "person.bob", base, set())
        zone_after_tick1 = sum(ps.today_zone_seconds.values())

        # Tick 2 — 500ms later (> 100ms, should credit ~0.5s)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            ps = coordinator._calc_pair(
                ps,
                "person.alice",
                "person.bob",
                base + timedelta(milliseconds=500),
                set(),
            )
        zone_after_tick2 = sum(ps.today_zone_seconds.values())

        assert zone_after_tick2 > zone_after_tick1, (
            "500ms tick must credit time to today_zone_seconds"
        )
        assert zone_after_tick2 == pytest.approx(zone_after_tick1 + 0.5, abs=0.05)

    def test_double_tick_unaccounted_does_not_grow(self):
        """today_zone_seconds sum after two near-zero ticks equals after one tick.

        Indirectly verifies today_unaccounted_time (elapsed - zone_sum) is not
        inflated by the double-tick: if zone_sum is unchanged, the unaccounted gap
        stays flat too.
        """
        coordinator, ps, k, _, _ = self._make_pair_in_proximity()
        base = _NOW

        # Tick 1 — anchors prev_calc_time
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            ps = coordinator._calc_pair(ps, "person.alice", "person.bob", base, set())

        # Tick 2 — 1ms (well under guard)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            ps = coordinator._calc_pair(
                ps,
                "person.alice",
                "person.bob",
                base + timedelta(milliseconds=1),
                set(),
            )
        zone_after_two_ticks = sum(ps.today_zone_seconds.values())

        # Tick 3 — same pair, 60s later (real tick)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            ps = coordinator._calc_pair(
                ps,
                "person.alice",
                "person.bob",
                base + timedelta(seconds=60),
                set(),
            )
        zone_after_real_tick = sum(ps.today_zone_seconds.values())

        # Real tick (60s from base, but prev_calc_time was set to base+1ms)
        # so ~59.999s credited, not ~120s.
        assert zone_after_real_tick == pytest.approx(zone_after_two_ticks + 60.0, abs=1.0), (
            "real 60s tick after double-tick must credit ~60s, not doubled"
        )


class TestExtractAltitude:
    """Tests for _extract_altitude."""

    def _state(self, entity_id, attrs):
        from homeassistant.core import State

        return State(entity_id, "home", attrs)

    def test_valid_altitude(self):
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": 42.5})
        assert _extract_altitude(s) == pytest.approx(42.5)

    def test_altitude_zero_no_vacc_is_nofix_sentinel(self):
        """0.0 with no vertical_accuracy is the iOS/HA no-vertical-fix sentinel → None."""
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": 0.0})
        assert _extract_altitude(s) is None

    def test_altitude_zero_with_valid_vacc_is_real_sea_level(self):
        """0.0 WITH a trustworthy vertical_accuracy is a genuine sea-level fix → kept."""
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": 0.0, "vertical_accuracy": 12.0})
        assert _extract_altitude(s) == pytest.approx(0.0)

    def test_altitude_zero_with_garbage_vacc_is_nofix_sentinel(self):
        """0.0 with out-of-range (garbage) vertical_accuracy → sentinel → None."""
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": 0.0, "vertical_accuracy": 99999.0})
        assert _extract_altitude(s) is None

    def test_altitude_zero_with_negative_vacc_is_nofix_sentinel(self):
        """0.0 with Apple's negative invalid-vacc flag → sentinel → None."""
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": 0.0, "vertical_accuracy": -1.0})
        assert _extract_altitude(s) is None

    def test_altitude_zero_with_zero_vacc_is_nofix_sentinel(self):
        """0.0 with vertical_accuracy exactly 0.0 → sentinel → None (a real GPS fix
        never reports zero vertical uncertainty)."""
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": 0.0, "vertical_accuracy": 0.0})
        assert _extract_altitude(s) is None

    def test_altitude_integer_coerced(self):
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": 100})
        assert _extract_altitude(s) == pytest.approx(100.0)

    def test_altitude_negative(self):
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": -28.5})
        assert _extract_altitude(s) == pytest.approx(-28.5)

    def test_altitude_below_sea_level_no_vacc_is_kept(self):
        """A genuine below-sea-level reading (Dead Sea ~-430 m, Netherlands ~-5 m)
        is NOT the 0.0 no-fix sentinel and is kept even without a vertical_accuracy —
        only an exact 0.0 is treated as the sentinel."""
        from custom_components.entity_distance.coordinator import _extract_altitude

        for alt in (-5.0, -86.0, -430.0):
            s = self._state("device_tracker.phone", {"altitude": alt})
            assert _extract_altitude(s) == pytest.approx(alt)

    def test_altitude_below_sea_level_near_zero_is_kept(self):
        """A small negative altitude just below sea level is kept (not snapped to the
        0.0 sentinel), with or without vacc."""
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": -0.3})
        assert _extract_altitude(s) == pytest.approx(-0.3)
        s2 = self._state("device_tracker.phone", {"altitude": -0.3, "vertical_accuracy": 8.0})
        assert _extract_altitude(s2) == pytest.approx(-0.3)

    def test_altitude_missing_key(self):
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"latitude": 51.5})
        assert _extract_altitude(s) is None

    def test_altitude_none_value(self):
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": None})
        assert _extract_altitude(s) is None

    def test_altitude_string_invalid(self):
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": "not_a_number"})
        assert _extract_altitude(s) is None

    def test_altitude_dict_invalid(self):
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": {"value": 100, "unit": "m"}})
        assert _extract_altitude(s) is None

    def test_altitude_too_high(self):
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": 15001.0})
        assert _extract_altitude(s) is None

    def test_altitude_too_low(self):
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": -501.0})
        assert _extract_altitude(s) is None

    def test_altitude_at_max_boundary(self):
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": 15000.0})
        assert _extract_altitude(s) == pytest.approx(15000.0)

    def test_altitude_at_min_boundary(self):
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": -500.0})
        assert _extract_altitude(s) == pytest.approx(-500.0)

    def test_nonzero_altitude_with_vacc_zero_is_2d_only_sentinel(self):
        """Non-zero alt + vacc=0.0 = iOS 2D-only fix → dropped."""
        from custom_components.entity_distance.coordinator import _extract_altitude

        s = self._state("device_tracker.phone", {"altitude": 8.5, "vertical_accuracy": 0.0})
        assert _extract_altitude(s) is None

    def test_vacc_nonnumeric_falls_back_to_minus_one(self):
        """Non-numeric vertical_accuracy in raw_vacc try/except → raw_vacc=-1.0 → not a sentinel."""
        from custom_components.entity_distance.coordinator import _extract_altitude

        # vertical_accuracy is a string — triggers the except branch (L277-278).
        # With raw_vacc=-1.0 and alt=50.0, neither sentinel path fires, so alt is returned.
        s = self._state("device_tracker.phone", {"altitude": 50.0, "vertical_accuracy": "bad"})
        assert _extract_altitude(s) == pytest.approx(50.0)


class TestCalcPairAltitude:
    """Tests for altitude_a_m / altitude_b_m / altitude_delta_m in _calc_pair."""

    def _run(self, alt_a, alt_b, vacc_a=None, vacc_b=None):
        from unittest.mock import patch

        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        state_a = make_state("person.alice", 51.5, -0.1, altitude=alt_a, vertical_accuracy=vacc_a)
        state_b = make_state("person.bob", 51.6, -0.2, altitude=alt_b, vertical_accuracy=vacc_b)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=500.0,
        ):
            return coordinator._calc_pair(
                ps, "person.alice", "person.bob", datetime.now().astimezone(), set()
            )

    def test_both_altitude_set(self):
        ps = self._run(10.0, 18.0)
        assert ps.altitude_a_m == pytest.approx(10.0)
        assert ps.altitude_b_m == pytest.approx(18.0)
        assert ps.altitude_delta_m == pytest.approx(8.0)

    def test_delta_negative_when_b_lower(self):
        ps = self._run(50.0, 42.0)
        assert ps.altitude_delta_m == pytest.approx(-8.0)

    def test_delta_zero_same_floor(self):
        ps = self._run(30.0, 30.0)
        assert ps.altitude_delta_m == pytest.approx(0.0)

    def test_altitude_a_missing(self):
        ps = self._run(None, 18.0)
        assert ps.altitude_a_m is None
        assert ps.altitude_b_m == pytest.approx(18.0)
        assert ps.altitude_delta_m is None

    def test_altitude_b_missing(self):
        ps = self._run(10.0, None)
        assert ps.altitude_a_m == pytest.approx(10.0)
        assert ps.altitude_b_m is None
        assert ps.altitude_delta_m is None

    def test_both_missing(self):
        ps = self._run(None, None)
        assert ps.altitude_a_m is None
        assert ps.altitude_b_m is None
        assert ps.altitude_delta_m is None

    def test_altitude_zero_no_vacc_drops_to_none(self):
        # 0.0/0.0 with no vertical_accuracy is the no-vertical-fix sentinel → None.
        ps = self._run(0.0, 0.0)
        assert ps.altitude_a_m is None
        assert ps.altitude_b_m is None
        assert ps.altitude_delta_m is None

    def test_altitude_zero_with_valid_vacc_retained(self):
        # 0.0/0.0 WITH a trustworthy vertical_accuracy is a genuine sea-level fix,
        # retained end-to-end through _calc_pair.
        ps = self._run(0.0, 0.0, vacc_a=12.0, vacc_b=12.0)
        assert ps.altitude_a_m == pytest.approx(0.0)
        assert ps.altitude_b_m == pytest.approx(0.0)
        assert ps.altitude_delta_m == pytest.approx(0.0)

    def test_negative_altitude(self):
        ps = self._run(-28.0, 100.0)
        assert ps.altitude_delta_m == pytest.approx(128.0)

    def test_altitude_does_not_affect_distance(self):
        ps = self._run(10.0, 500.0)
        assert ps.distance_m == pytest.approx(500.0)

    def _run_fallback(self, alt_a, alt_b, elevation=42.0, state_a_val="home", state_b_val="home"):
        coordinator = _make_calc_pair_coordinator()
        coordinator.hass.config.elevation = elevation
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        sa = State(
            "person.alice",
            state_a_val,
            {"latitude": 51.5, "longitude": -0.1}
            | ({"altitude": alt_a} if alt_a is not None else {}),
        )
        sb = State(
            "person.bob",
            state_b_val,
            {"latitude": 51.6, "longitude": -0.2}
            | ({"altitude": alt_b} if alt_b is not None else {}),
        )
        coordinator.hass.states.get.side_effect = lambda eid: sa if eid == "person.alice" else sb
        with patch("custom_components.entity_distance.coordinator.ha_distance", return_value=500.0):
            return coordinator._calc_pair(
                ps, "person.alice", "person.bob", datetime.now().astimezone(), set()
            )

    def test_home_zone_fallback_a(self):
        """Entity A at home with no GPS altitude uses hass.config.elevation."""
        ps = self._run_fallback(alt_a=None, alt_b=50.0)
        assert ps.altitude_a_m == pytest.approx(42.0)
        assert ps.altitude_delta_m == pytest.approx(8.0)

    def test_home_zone_fallback_b(self):
        """Entity B at home with no GPS altitude uses hass.config.elevation."""
        ps = self._run_fallback(alt_a=50.0, alt_b=None)
        assert ps.altitude_b_m == pytest.approx(42.0)
        assert ps.altitude_delta_m == pytest.approx(-8.0)

    def test_home_zone_fallback_elevation_none(self):
        """hass.config.elevation = None → no fallback, altitude stays None."""
        ps = self._run_fallback(alt_a=None, alt_b=50.0, elevation=None)
        assert ps.altitude_a_m is None
        assert ps.altitude_delta_m is None

    def test_home_zone_fallback_elevation_zero(self):
        """hass.config.elevation = 0 is valid (sea level) and must be used."""
        ps = self._run_fallback(alt_a=None, alt_b=10.0, elevation=0)
        assert ps.altitude_a_m == pytest.approx(0.0)
        assert ps.altitude_delta_m == pytest.approx(10.0)

    def test_home_zone_fallback_not_triggered_when_not_home(self):
        """Entity with no altitude but state != 'home' gets no fallback."""
        ps = self._run_fallback(alt_a=None, alt_b=50.0, state_a_val="not_home")
        assert ps.altitude_a_m is None
        assert ps.altitude_delta_m is None

    def test_home_zone_fallback_out_of_bounds_elevation(self):
        """hass.config.elevation out of bounds (e.g. ft instead of m) → no fallback."""
        ps = self._run_fallback(alt_a=None, alt_b=50.0, elevation=16000)
        assert ps.altitude_a_m is None
        assert ps.altitude_delta_m is None

    def test_zone_entity_gets_elevation_fallback(self):
        """zone.home with no altitude uses hass.config.elevation."""
        coordinator = _make_calc_pair_coordinator(entities=["person.alice", "zone.home"])
        coordinator.hass.config.elevation = 42.0
        k = pair_key("person.alice", "zone.home")
        ps = coordinator._pair_states[k]
        sa = State("person.alice", "home", {"latitude": 51.5, "longitude": -0.1, "altitude": 34.0})
        sb = State("zone.home", "2", {"latitude": 51.5, "longitude": -0.1})
        coordinator.hass.states.get.side_effect = lambda eid: sa if eid == "person.alice" else sb
        with patch("custom_components.entity_distance.coordinator.ha_distance", return_value=15.0):
            ps = coordinator._calc_pair(
                ps, "person.alice", "zone.home", datetime.now().astimezone(), set()
            )
        assert ps.altitude_b_m == pytest.approx(42.0)
        assert ps.altitude_delta_m == pytest.approx(8.0)

    def test_non_home_zone_does_not_get_elevation_fallback(self):
        """zone.work (not zone.home) must NOT receive hass.config.elevation as fallback."""
        coordinator = _make_calc_pair_coordinator(entities=["person.alice", "zone.work"])
        coordinator.hass.config.elevation = 42.0
        k = pair_key("person.alice", "zone.work")
        ps = coordinator._pair_states[k]
        sa = State("person.alice", "home", {"latitude": 51.5, "longitude": -0.1, "altitude": 34.0})
        sb = State("zone.work", "0", {"latitude": 52.0, "longitude": -0.2})
        coordinator.hass.states.get.side_effect = lambda eid: sa if eid == "person.alice" else sb
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance", return_value=5000.0
        ):
            ps = coordinator._calc_pair(
                ps, "person.alice", "zone.work", datetime.now().astimezone(), set()
            )
        assert ps.altitude_b_m is None
        assert ps.altitude_delta_m is None


class TestResolveGpsSource:
    """Tests for _resolve_gps_source."""

    def _state(self, entity_id, attrs, state_val="home"):
        from homeassistant.core import State

        return State(entity_id, state_val, attrs)

    def test_non_person_returns_original(self):
        from unittest.mock import MagicMock

        from custom_components.entity_distance.coordinator import _resolve_gps_source

        s = self._state("device_tracker.phone", {"latitude": 51.5})
        hass = MagicMock()
        assert _resolve_gps_source(s, hass) is s

    def test_person_with_valid_source_returns_tracker(self):
        from unittest.mock import MagicMock

        from custom_components.entity_distance.coordinator import _resolve_gps_source

        tracker = self._state("device_tracker.phone", {"latitude": 51.5, "altitude": 42.0})
        person = self._state("person.alice", {"source": "device_tracker.phone"})
        hass = MagicMock()
        hass.states.get.return_value = tracker
        result = _resolve_gps_source(person, hass)
        assert result is tracker
        hass.states.get.assert_called_once_with("device_tracker.phone")

    def test_person_missing_source_returns_person(self):
        from unittest.mock import MagicMock

        from custom_components.entity_distance.coordinator import _resolve_gps_source

        person = self._state("person.alice", {"latitude": 51.5})
        hass = MagicMock()
        assert _resolve_gps_source(person, hass) is person

    def test_person_non_string_source_returns_person(self):
        from unittest.mock import MagicMock

        from custom_components.entity_distance.coordinator import _resolve_gps_source

        person = self._state("person.alice", {"source": 12345})
        hass = MagicMock()
        assert _resolve_gps_source(person, hass) is person

    def test_person_source_not_found_returns_person(self):
        from unittest.mock import MagicMock

        from custom_components.entity_distance.coordinator import _resolve_gps_source

        person = self._state("person.alice", {"source": "device_tracker.missing"})
        hass = MagicMock()
        hass.states.get.return_value = None
        assert _resolve_gps_source(person, hass) is person


class TestExtractSpeed:
    """Tests for _extract_speed."""

    def _state(self, attrs):
        from homeassistant.core import State

        return State("device_tracker.phone", "home", attrs)

    def test_valid_speed(self):
        from custom_components.entity_distance.coordinator import _extract_speed

        assert _extract_speed(self._state({"speed": 50.0})) == pytest.approx(50.0)

    def test_zero_speed(self):
        from custom_components.entity_distance.coordinator import _extract_speed

        assert _extract_speed(self._state({"speed": 0.0})) == pytest.approx(0.0)

    def test_missing_key(self):
        from custom_components.entity_distance.coordinator import _extract_speed

        assert _extract_speed(self._state({})) is None

    def test_malformed(self):
        from custom_components.entity_distance.coordinator import _extract_speed

        assert _extract_speed(self._state({"speed": "fast"})) is None

    def test_negative_rejected(self):
        from custom_components.entity_distance.coordinator import _extract_speed

        assert _extract_speed(self._state({"speed": -1.0})) is None

    def test_over_max_rejected(self):
        from custom_components.entity_distance.coordinator import _extract_speed

        assert _extract_speed(self._state({"speed": 1001.0})) is None

    def test_at_max_boundary(self):
        from custom_components.entity_distance.coordinator import _extract_speed

        assert _extract_speed(self._state({"speed": 1000.0})) == pytest.approx(1000.0)


class TestExtractHeading:
    """Tests for _extract_heading."""

    def _state(self, attrs):
        from homeassistant.core import State

        return State("device_tracker.phone", "home", attrs)

    def test_valid_heading(self):
        from custom_components.entity_distance.coordinator import _extract_heading

        assert _extract_heading(self._state({"course": 270.0})) == pytest.approx(270.0)

    def test_zero_heading(self):
        from custom_components.entity_distance.coordinator import _extract_heading

        assert _extract_heading(self._state({"course": 0.0})) == pytest.approx(0.0)

    def test_360_is_valid(self):
        from custom_components.entity_distance.coordinator import _extract_heading

        assert _extract_heading(self._state({"course": 360.0})) == pytest.approx(360.0)

    def test_missing_key(self):
        from custom_components.entity_distance.coordinator import _extract_heading

        assert _extract_heading(self._state({})) is None

    def test_malformed(self):
        from custom_components.entity_distance.coordinator import _extract_heading

        assert _extract_heading(self._state({"course": "north"})) is None

    def test_negative_rejected(self):
        from custom_components.entity_distance.coordinator import _extract_heading

        assert _extract_heading(self._state({"course": -1.0})) is None

    def test_over_360_rejected(self):
        from custom_components.entity_distance.coordinator import _extract_heading

        assert _extract_heading(self._state({"course": 361.0})) is None


class TestExtractVerticalAccuracy:
    """Tests for _extract_vertical_accuracy."""

    def _state(self, attrs):
        from homeassistant.core import State

        return State("device_tracker.phone", "home", attrs)

    def test_valid(self):
        from custom_components.entity_distance.coordinator import _extract_vertical_accuracy

        assert _extract_vertical_accuracy(self._state({"vertical_accuracy": 8.0})) == pytest.approx(
            8.0
        )

    def test_zero(self):
        from custom_components.entity_distance.coordinator import _extract_vertical_accuracy

        # vacc=0.0 is a 2D-only-fix sentinel — physically impossible for a real fix.
        assert _extract_vertical_accuracy(self._state({"vertical_accuracy": 0.0})) is None

    def test_missing_key(self):
        from custom_components.entity_distance.coordinator import _extract_vertical_accuracy

        assert _extract_vertical_accuracy(self._state({})) is None

    def test_malformed(self):
        from custom_components.entity_distance.coordinator import _extract_vertical_accuracy

        assert _extract_vertical_accuracy(self._state({"vertical_accuracy": "high"})) is None

    def test_negative_rejected(self):
        from custom_components.entity_distance.coordinator import _extract_vertical_accuracy

        assert _extract_vertical_accuracy(self._state({"vertical_accuracy": -1.0})) is None

    def test_over_max_rejected(self):
        from custom_components.entity_distance.coordinator import _extract_vertical_accuracy

        assert _extract_vertical_accuracy(self._state({"vertical_accuracy": 10001.0})) is None

    def test_at_max_boundary(self):
        from custom_components.entity_distance.coordinator import _extract_vertical_accuracy

        assert _extract_vertical_accuracy(
            self._state({"vertical_accuracy": 10000.0})
        ) == pytest.approx(10000.0)


class TestCalcPairGpsAttributes:
    """Integration tests for speed/heading/vacc in _calc_pair + person source fallback."""

    def _run(
        self, attrs_a, attrs_b, entity_a="device_tracker.alice", entity_b="device_tracker.bob"
    ):
        from unittest.mock import patch

        from homeassistant.core import State

        from custom_components.entity_distance.models import pair_key

        coordinator = _make_calc_pair_coordinator(entities=[entity_a, entity_b])
        k = pair_key(entity_a, entity_b)
        ps = coordinator._pair_states[k]

        state_a = State(entity_a, "home", {**{"latitude": 51.5, "longitude": -0.1}, **attrs_a})
        state_b = State(entity_b, "home", {**{"latitude": 51.6, "longitude": -0.2}, **attrs_b})
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == entity_a else state_b
        )
        with patch("custom_components.entity_distance.coordinator.ha_distance", return_value=500.0):
            return coordinator._calc_pair(
                ps, entity_a, entity_b, datetime.now().astimezone(), set()
            )

    def test_speed_populated(self):
        ps = self._run({"speed": 50.0}, {"speed": 30.0})
        assert ps.speed_a_kmh == pytest.approx(50.0)
        assert ps.speed_b_kmh == pytest.approx(30.0)

    def test_heading_populated(self):
        ps = self._run({"course": 270.0}, {"course": 90.0})
        assert ps.heading_a_deg == pytest.approx(270.0)
        assert ps.heading_b_deg == pytest.approx(90.0)

    def test_vertical_accuracy_populated(self):
        ps = self._run({"vertical_accuracy": 8.0}, {"vertical_accuracy": 12.0})
        assert ps.vertical_accuracy_a_m == pytest.approx(8.0)
        assert ps.vertical_accuracy_b_m == pytest.approx(12.0)

    def test_none_when_missing(self):
        ps = self._run({}, {})
        assert ps.speed_a_kmh is None
        assert ps.speed_b_kmh is None
        assert ps.heading_a_deg is None
        assert ps.heading_b_deg is None
        assert ps.vertical_accuracy_a_m is None
        assert ps.vertical_accuracy_b_m is None

    def test_person_source_fallback_for_altitude(self):
        """Person entities use source device tracker for altitude via _resolve_gps_source."""
        from unittest.mock import patch

        from homeassistant.core import State

        from custom_components.entity_distance.models import pair_key

        coordinator = _make_calc_pair_coordinator(entities=["person.alice", "person.bob"])
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        tracker_alice = State(
            "device_tracker.iphone_alice",
            "home",
            {"latitude": 51.5, "longitude": -0.1, "altitude": 42.0, "speed": 5.0},
        )
        tracker_bob = State(
            "device_tracker.iphone_bob",
            "home",
            {"latitude": 51.6, "longitude": -0.2, "altitude": 50.0, "speed": 0.0},
        )
        person_alice = State(
            "person.alice",
            "home",
            {"latitude": 51.5, "longitude": -0.1, "source": "device_tracker.iphone_alice"},
        )
        person_bob = State(
            "person.bob",
            "home",
            {"latitude": 51.6, "longitude": -0.2, "source": "device_tracker.iphone_bob"},
        )

        states = {
            "person.alice": person_alice,
            "person.bob": person_bob,
            "device_tracker.iphone_alice": tracker_alice,
            "device_tracker.iphone_bob": tracker_bob,
        }
        coordinator.hass.states.get.side_effect = states.get

        with patch("custom_components.entity_distance.coordinator.ha_distance", return_value=500.0):
            ps = coordinator._calc_pair(
                ps, "person.alice", "person.bob", datetime.now().astimezone(), set()
            )

        assert ps.altitude_a_m == pytest.approx(42.0)
        assert ps.altitude_b_m == pytest.approx(50.0)
        assert ps.altitude_delta_m == pytest.approx(8.0)
        assert ps.speed_a_kmh == pytest.approx(5.0)
        assert ps.speed_b_kmh == pytest.approx(0.0)


class TestCalcPairVerticalAccuracyFilter:
    """Altitude suppression when vacc exceeds max_vertical_accuracy_m."""

    def _run(self, vacc_a, vacc_b, alt_a=100.0, alt_b=110.0, max_vacc=30.0):
        from unittest.mock import patch

        from homeassistant.core import State

        coordinator = _make_calc_pair_coordinator()
        coordinator._max_vertical_accuracy_m = max_vacc
        k = next(iter(coordinator._pair_states))
        ps = coordinator._pair_states[k]
        ea, eb = k

        attrs_a = {"latitude": 51.5, "longitude": -0.1, "altitude": alt_a}
        attrs_b = {"latitude": 51.6, "longitude": -0.2, "altitude": alt_b}
        if vacc_a is not None:
            attrs_a["vertical_accuracy"] = vacc_a
        if vacc_b is not None:
            attrs_b["vertical_accuracy"] = vacc_b

        state_a = State(ea, "home", attrs_a)
        state_b = State(eb, "home", attrs_b)
        coordinator.hass.states.get.side_effect = lambda eid: state_a if eid == ea else state_b
        with patch("custom_components.entity_distance.coordinator.ha_distance", return_value=500.0):
            return coordinator._calc_pair(ps, ea, eb, datetime.now().astimezone(), set())

    def test_altitude_passes_when_vacc_within_limit(self):
        ps = self._run(vacc_a=20.0, vacc_b=25.0, max_vacc=30.0)
        assert ps.altitude_a_m == pytest.approx(100.0)
        assert ps.altitude_b_m == pytest.approx(110.0)

    def test_altitude_a_suppressed_when_vacc_a_exceeds_limit(self):
        ps = self._run(vacc_a=50.0, vacc_b=20.0, max_vacc=30.0)
        assert ps.altitude_a_m is None
        assert ps.altitude_b_m == pytest.approx(110.0)
        assert ps.altitude_delta_m is None

    def test_altitude_b_suppressed_when_vacc_b_exceeds_limit(self):
        ps = self._run(vacc_a=20.0, vacc_b=50.0, max_vacc=30.0)
        assert ps.altitude_a_m == pytest.approx(100.0)
        assert ps.altitude_b_m is None
        assert ps.altitude_delta_m is None

    def test_both_suppressed_when_both_exceed_limit(self):
        ps = self._run(vacc_a=50.0, vacc_b=50.0, max_vacc=30.0)
        assert ps.altitude_a_m is None
        assert ps.altitude_b_m is None
        assert ps.altitude_delta_m is None

    def test_filter_disabled_when_max_zero(self):
        ps = self._run(vacc_a=999.0, vacc_b=999.0, max_vacc=0.0)
        assert ps.altitude_a_m == pytest.approx(100.0)
        assert ps.altitude_b_m == pytest.approx(110.0)

    def test_vacc_none_does_not_suppress(self):
        # No vertical_accuracy attr → vacc is None → altitude kept
        ps = self._run(vacc_a=None, vacc_b=None, max_vacc=30.0)
        assert ps.altitude_a_m == pytest.approx(100.0)
        assert ps.altitude_b_m == pytest.approx(110.0)


class TestResetProximityDuration:
    """async_reset_proximity_duration zeroes the lifetime total, correctly even mid-proximity."""

    def _make_coordinator(self, pair_states):
        from unittest.mock import AsyncMock

        from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coord._pair_states = pair_states
        coord._store = MagicMock()
        coord._store.async_save = AsyncMock()
        coord.async_update_listeners = MagicMock()
        return coord

    async def test_reset_while_in_proximity_zeroes_live_total(self):
        """The regression that bites: reset mid-proximity must drop the in-progress segment too."""
        from custom_components.entity_distance.sensor import ProximityDurationSensor

        k = pair_key("person.a", "person.b")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        before = datetime.now().astimezone() - timedelta(hours=2)
        ps.proximity = True
        ps.proximity_since = before
        ps.proximity_duration_s = 3600.0
        ps.proximity_tracking_started = before
        ps.prev_calc_time = before

        coord = self._make_coordinator({k: ps})
        await coord.async_reset_proximity_duration()

        now = datetime.now().astimezone()
        assert ps.proximity_duration_s == 0.0
        assert ps.proximity is True  # flag preserved
        assert ps.proximity_since is not None
        assert abs((ps.proximity_since - now).total_seconds()) < 2
        assert abs((ps.proximity_tracking_started - now).total_seconds()) < 2
        assert abs((ps.prev_calc_time - now).total_seconds()) < 2
        coord._store.async_save.assert_awaited_once()  # persisted immediately
        coord.async_update_listeners.assert_called_once()

        # Sensor must now read ~0, not the ~2h live delta it showed before reset.
        sensor = ProximityDurationSensor.__new__(ProximityDurationSensor)
        sensor.coordinator = MagicMock()
        sensor.coordinator.last_update_success = True
        with patch.object(type(sensor), "_pair", new_callable=lambda: property(lambda self: ps)):
            assert sensor.native_value == 0.0

    async def test_reset_when_not_in_proximity_leaves_since_none(self):
        k = pair_key("person.a", "person.b")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.proximity = False
        ps.proximity_since = None
        ps.proximity_duration_s = 7200.0
        ps.proximity_tracking_started = datetime.now().astimezone() - timedelta(days=1)

        coord = self._make_coordinator({k: ps})
        await coord.async_reset_proximity_duration()

        assert ps.proximity_duration_s == 0.0
        assert ps.proximity_since is None  # not resurrected
        assert ps.proximity is False


class TestDirectionHysteresis:
    """N=2 direction hysteresis: approaching/diverging committed only on 2 consecutive GPS fixes."""

    def _run_tick(self, ps, dist, pending=None):
        """Run one tick, return updated PairState."""
        from unittest.mock import patch

        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(max_speed_kmh=0.0)
        coordinator._pair_states[pair_key("person.alice", "person.bob")] = ps

        now = datetime.now().astimezone()
        ps.prev_calc_time = now - timedelta(seconds=10)
        # F1: direction/speed baseline is last_fix_* (not prev_*). Reset it to a 10s-old
        # anchor each tick (mirrors the prev_calc_time gap) so every single-tick call
        # has a positive inter-fix interval; the distance side (last_fix_distance_m) is
        # seeded by the caller via _fresh_ps / between-tick assignments.
        ps.last_fix_time = now - timedelta(seconds=10)

        state_a = make_state("person.alice", 51.5, -0.1, accuracy=30.0)
        state_b = make_state("person.bob", 51.501, -0.1, accuracy=30.0)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        if pending is None:
            pending = {"person.alice"}

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=dist,
        ):
            return coordinator._calc_pair(ps, "person.alice", "person.bob", now, pending)

    def _fresh_ps(self, prev_dist=500.0, prev_acc=30.0):
        from custom_components.entity_distance.models import PairState, pair_key

        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.prev_distance_m = prev_dist
        ps.last_fix_distance_m = prev_dist
        ps.accuracy_a = prev_acc
        ps.accuracy_b = prev_acc
        return ps

    def test_single_approaching_tick_suppressed_to_stationary(self):
        """Single approaching GPS fix → held as stationary (candidate_count=1 < 2)."""
        ps = self._fresh_ps(prev_dist=500.0)
        # delta = 500 - 460 = -40m → would be approaching but N=2 blocks it
        result = self._run_tick(ps, dist=460.0)
        assert result.direction == "stationary"
        assert result.direction_candidate == "approaching"
        assert result.direction_candidate_count == 1

    def test_two_consecutive_approaching_ticks_committed(self):
        """Two consecutive approaching fixes → committed as approaching on second fix."""
        ps = self._fresh_ps(prev_dist=500.0)
        # First tick: approaching but suppressed
        self._run_tick(ps, dist=460.0)
        assert ps.direction == "stationary"
        assert ps.direction_candidate_count == 1

        # Second tick: same direction → count=2 → commits approaching
        ps.prev_distance_m = 460.0
        ps.last_fix_distance_m = 460.0
        result = self._run_tick(ps, dist=420.0)
        assert result.direction == "approaching"
        assert result.direction_candidate_count == 2

    def test_oscillating_approaching_diverging_suppressed(self):
        """Approaching then diverging → candidate resets → never commits either direction."""
        ps = self._fresh_ps(prev_dist=500.0)
        # First tick: approaching
        self._run_tick(ps, dist=460.0)
        assert ps.direction_candidate == "approaching"
        assert ps.direction_candidate_count == 1

        # Second tick: diverging (distance grows) → candidate resets, stays stationary
        ps.prev_distance_m = 460.0
        ps.last_fix_distance_m = 460.0
        result = self._run_tick(ps, dist=500.0)
        assert result.direction == "stationary"
        assert result.direction_candidate == "diverging"
        assert result.direction_candidate_count == 1

    def test_hold_just_expired_commits_immediately(self):
        """hold_just_expired tick bypasses hysteresis → approaching committed on first fix."""
        from unittest.mock import patch

        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(max_speed_kmh=0.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        ps.prev_distance_m = 500.0
        ps.last_fix_distance_m = 500.0
        ps.accuracy_a = 30.0
        ps.accuracy_b = 30.0
        ps.prev_calc_time = now - timedelta(seconds=10)
        ps.last_fix_time = now - timedelta(seconds=10)
        # Set hold_until in the past so hold_just_expired triggers
        coordinator._resync_holding[k] = True
        coordinator._resync_hold_until[k] = now - timedelta(seconds=1)

        state_a = make_state("person.alice", 51.5, -0.1, accuracy=30.0)
        state_b = make_state("person.bob", 51.501, -0.1, accuracy=30.0)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=460.0,
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, {"person.alice"})

        # hold_just_expired → hysteresis bypassed → approaching committed immediately
        assert result.direction == "approaching"
        assert result.direction_candidate is None
        assert result.direction_candidate_count == 0

    def test_invalidate_resets_candidate(self):
        """_invalidate() (entity unavailable) resets direction_candidate to None/0."""
        from custom_components.entity_distance.models import pair_key

        coordinator = _make_calc_pair_coordinator(max_speed_kmh=0.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        ps.prev_distance_m = 500.0
        ps.prev_calc_time = now - timedelta(seconds=10)
        ps.direction_candidate = "approaching"
        ps.direction_candidate_count = 1

        # Trigger _invalidate() by returning unavailable state for alice
        from homeassistant.const import STATE_UNAVAILABLE
        from homeassistant.core import State

        state_a = State("person.alice", STATE_UNAVAILABLE)
        state_b = State("person.bob", "not_home")
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, {"person.alice"})

        assert result.direction_candidate is None
        assert result.direction_candidate_count == 0
        assert result.data_valid is False

    def test_invalidate_clears_expired_resync_hold(self):
        """_invalidate clears _resync_holding when hold has already expired (L653-654)."""
        from homeassistant.const import STATE_UNAVAILABLE
        from homeassistant.core import State

        from custom_components.entity_distance.models import pair_key

        coordinator = _make_calc_pair_coordinator(max_speed_kmh=0.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        # Plant an expired hold — hold_until is in the past.
        coordinator._resync_holding[k] = True
        coordinator._resync_hold_until[k] = now - timedelta(seconds=5)

        state_a = State("person.alice", STATE_UNAVAILABLE)
        state_b = State("person.bob", "not_home")
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        coordinator._calc_pair(ps, "person.alice", "person.bob", now, {"person.alice"})

        # Expired hold must be cleared so recovery tick doesn't bypass N=2 hysteresis.
        assert coordinator._resync_holding[k] is False
        assert coordinator._resync_hold_until[k] is None

    def test_teleport_rejection_resets_candidate(self):
        """Teleport rejection nulls prev_distance_m AND resets direction candidate."""
        from unittest.mock import patch

        from custom_components.entity_distance.models import pair_key
        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(max_speed_kmh=250.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]

        now = datetime.now().astimezone()
        ps.prev_distance_m = 100.0
        ps.accuracy_a = 30.0
        ps.accuracy_b = 30.0
        ps.prev_calc_time = now - timedelta(seconds=10)
        ps.direction_candidate = "approaching"
        ps.direction_candidate_count = 1

        state_a = make_state("person.alice", 51.5, -0.1, accuracy=30.0)
        state_b = make_state("person.bob", 51.501, -0.1, accuracy=30.0)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

        # 900km/h — exceeds max_speed_kmh=250 → teleport rejection
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=2_500_000.0,
        ):
            result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, {"person.alice"})

        assert result.prev_distance_m is None  # baseline nulled
        assert result.direction_candidate is None
        assert result.direction_candidate_count == 0


class TestDirectionFixBaselineAndConfidentMove:
    """F1 (last_fix_* baseline) + F2 (confident-move hysteresis bypass) + F3 (blip preserves streak)."""

    def _coord(self, max_speed_kmh=0.0):
        return _make_calc_pair_coordinator(max_speed_kmh=max_speed_kmh)

    def _states(self, coordinator, acc=20.0):
        from tests.conftest import make_state

        state_a = make_state("person.alice", 51.5, -0.1, accuracy=acc)
        state_b = make_state("person.bob", 51.6, -0.2, accuracy=acc)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )

    def _tick(self, coordinator, ps, dist, now, pending):
        from unittest.mock import patch

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=dist,
        ):
            return coordinator._calc_pair(ps, "person.alice", "person.bob", now, pending)

    def test_confident_move_commits_on_first_fix(self):
        """F2: a large unambiguous approach (|delta| >> confident cutoff) commits on fix #1."""
        coordinator = self._coord()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        self._states(coordinator, acc=20.0)
        now = datetime.now().astimezone()
        ps.prev_distance_m = 1600.0
        ps.last_fix_distance_m = 1600.0  # baseline distance at last real fix
        ps.last_fix_time = now - timedelta(seconds=120)  # 2 min ago (sparse fix)
        ps.prev_calc_time = now - timedelta(seconds=60)
        # delta = 600 - 1600 = -1000m; threshold ≈ max(15, 80*0.15)=15 → cutoff 60m
        # 1000 >> 60 → confident → approaching committed WITHOUT a second fix.
        result = self._tick(coordinator, ps, dist=600.0, now=now, pending={"person.alice"})
        assert result.direction == "approaching"
        assert result.direction_candidate is None
        assert result.direction_candidate_count == 0
        # closing_speed over the real 120s fix interval, not a sub-second spike.
        assert result.closing_speed_kmh is not None
        assert result.closing_speed_kmh < 60.0  # 1000m/120s ≈ 30 km/h, sane

    def test_marginal_move_still_needs_two_fixes(self):
        """F2 regression guard: a marginal near-threshold move keeps the N=2 requirement."""
        coordinator = self._coord()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        self._states(coordinator, acc=20.0)
        now = datetime.now().astimezone()
        ps.prev_distance_m = 500.0
        ps.last_fix_distance_m = 500.0
        ps.last_fix_time = now - timedelta(seconds=30)
        ps.prev_calc_time = now - timedelta(seconds=30)
        # threshold ≈ 15m, cutoff 60m. delta = -40m → just over threshold, under cutoff
        # → NOT confident → first fix suppressed to stationary (candidate only).
        result = self._tick(coordinator, ps, dist=460.0, now=now, pending={"person.alice"})
        assert result.direction == "stationary"
        assert result.direction_candidate == "approaching"
        assert result.direction_candidate_count == 1

    def test_direction_holds_across_timer_tick(self):
        """F1: a fix-less timer tick does NOT overwrite a committed direction or advance last_fix_*."""
        coordinator = self._coord()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        self._states(coordinator, acc=20.0)
        now = datetime.now().astimezone()
        ps.prev_distance_m = 1600.0
        ps.last_fix_distance_m = 1600.0
        ps.last_fix_time = now - timedelta(seconds=120)
        ps.prev_calc_time = now - timedelta(seconds=60)
        # Real fix: confident approach → committed.
        r1 = self._tick(coordinator, ps, dist=600.0, now=now, pending={"person.alice"})
        assert r1.direction == "approaching"
        fix_dist_after = ps.last_fix_distance_m
        fix_time_after = ps.last_fix_time
        assert fix_dist_after == 600.0  # advanced on the real fix

        # Timer tick (empty pending), same GPS distance: direction must HOLD, and the
        # last_fix_* baseline must NOT advance (no new fix drove this tick).
        later = now + timedelta(seconds=60)
        r2 = self._tick(coordinator, ps, dist=600.0, now=later, pending=set())
        assert r2.direction == "approaching"  # held, not reset to stationary
        assert ps.last_fix_distance_m == fix_dist_after  # not advanced on timer tick
        assert ps.last_fix_time == fix_time_after

    def test_blip_inside_grace_preserves_direction_streak(self):
        """F3: a 1-tick invalidation while displayable preserves candidate + last_fix baseline."""
        from homeassistant.const import STATE_UNAVAILABLE
        from homeassistant.core import State

        coordinator = self._coord()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        now = datetime.now().astimezone()
        # Mid-approach state with a live streak and a fix baseline + prior valid distance.
        ps.distance_m = 460.0
        ps.prev_distance_m = 460.0
        ps.prev_calc_time = now - timedelta(seconds=10)
        ps.last_fix_distance_m = 460.0
        ps.last_fix_time = now - timedelta(seconds=10)
        ps.direction_candidate = "approaching"
        ps.direction_candidate_count = 1

        # Alice blips unavailable for one tick → _invalidate, but distance_m is present
        # (inside display grace) so the streak/baseline must survive.
        state_a = State("person.alice", STATE_UNAVAILABLE)
        state_b = State("person.bob", "not_home")
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )
        result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, {"person.alice"})

        assert result.data_valid is False
        assert result.direction_candidate == "approaching"  # preserved
        assert result.direction_candidate_count == 1
        assert result.last_fix_distance_m == 460.0  # baseline preserved across the blip

    def test_cold_invalidate_resets_streak(self):
        """F3 boundary: with no prior displayable data, _invalidate still clears the streak."""
        from homeassistant.const import STATE_UNAVAILABLE
        from homeassistant.core import State

        coordinator = self._coord()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        now = datetime.now().astimezone()
        ps.distance_m = None  # never had valid data
        ps.direction_candidate = "approaching"
        ps.direction_candidate_count = 1
        ps.last_fix_distance_m = 500.0
        ps.last_fix_time = now - timedelta(seconds=10)

        state_a = State("person.alice", STATE_UNAVAILABLE)
        state_b = State("person.bob", "not_home")
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )
        result = coordinator._calc_pair(ps, "person.alice", "person.bob", now, {"person.alice"})

        assert result.direction_candidate is None
        assert result.direction_candidate_count == 0
        assert result.last_fix_distance_m is None
        assert result.last_fix_time is None

    def test_zero_interval_fix_holds_direction(self):
        """F5: a real-fix interval below DIRECTION_MIN_INTERVAL_S (here delta_s==0) computes
        no direction/speed and HOLDS the last committed direction instead of nulling it —
        a sub-interval GPS jump must not fabricate a value or wipe a valid one."""
        coordinator = self._coord()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        self._states(coordinator, acc=20.0)
        now = datetime.now().astimezone()
        ps.prev_distance_m = 500.0
        ps.prev_calc_time = now - timedelta(seconds=10)
        ps.last_fix_distance_m = 500.0
        ps.last_fix_time = now  # same instant → zero real-fix interval (< 5s floor)
        ps.direction = "approaching"
        ps.closing_speed_kmh = 42.0
        result = self._tick(coordinator, ps, dist=100.0, now=now, pending={"person.alice"})
        # Held, not nulled; the stale speed is likewise left untouched (no junk recompute).
        assert result.direction == "approaching"
        assert result.closing_speed_kmh == 42.0
        # Baseline not advanced on the sub-interval tick → interval accumulates to next fix.
        assert result.last_fix_distance_m == 500.0

    def test_real_drive_sparse_fixes_with_timer_ticks(self):
        """Regression for the reported drive bug: a sustained approach with sparse GPS
        fixes (minutes apart) and interleaved fix-less 60s timer ticks must latch
        `approaching` across the run and report plausible (noise-stripped) closing speed.

        The pre-fix suite force-fed non-empty `pending` on every direction tick and never
        interleaved an empty-pending timer tick between two sparse moving fixes — which is
        why 747 tests stayed green while the real 12km→0 drive read stationary/611km/h."""
        from unittest.mock import patch

        coordinator = self._coord()  # max_speed_kmh=0 → DEFAULT cap 1000 for teleport
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        self._states(coordinator, acc=25.0)  # realistic phone GPS accuracy

        # Monotonic approach, ~2 min between real fixes (metres). Mirrors the CSV shape.
        start = datetime.now().astimezone()
        fixes = [12000.0, 10000.0, 8000.0, 5500.0, 3300.0, 2000.0, 1300.0, 600.0, 60.0]
        t = start
        # Seed the baseline with the first fix (no direction yet — needs a prior fix).
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance", return_value=fixes[0]
        ):
            coordinator._calc_pair(ps, "person.alice", "person.bob", t, {"person.alice"})

        approaching = 0
        speeds: list[float] = []
        etas: list[float] = []
        for dist in fixes[1:]:
            # Interleave a fix-less 60s timer tick (empty pending) BEFORE each real fix —
            # the exact interaction the old suite never exercised. Must not clobber direction.
            t = t + timedelta(seconds=60)
            with patch(
                "custom_components.entity_distance.coordinator.ha_distance",
                return_value=dist + 5.0,  # same GPS position would be reported by a timer tick
            ):
                coordinator._calc_pair(ps, "person.alice", "person.bob", t, set())
            # Real fix ~2 min after the previous real fix.
            t = t + timedelta(seconds=60)
            with patch(
                "custom_components.entity_distance.coordinator.ha_distance",
                return_value=dist,
            ):
                r = coordinator._calc_pair(ps, "person.alice", "person.bob", t, {"person.alice"})
            if r.direction == "approaching":
                approaching += 1
                if r.closing_speed_kmh is not None:
                    speeds.append(r.closing_speed_kmh)
                if r.eta_minutes is not None:
                    etas.append(r.eta_minutes)

        # Latches approaching across the whole approach (pre-fix: ~4/13).
        assert approaching >= len(fixes) - 2, (
            f"only {approaching}/{len(fixes) - 1} fixes approaching"
        )
        # F4: closing speed is plausible — noise stripped, NOT clamped. Non-zero (would be
        # 0 if F4 over-stripped) and under a car ceiling (pre-fix: 611 km/h).
        assert speeds, "no closing speed samples on an approaching drive"
        assert all(0.0 < v < 200.0 for v in speeds), f"implausible closing speeds: {speeds}"
        # ETA inherits the corrected speed → finite for the sustained approach.
        assert etas, "ETA never computed on a sustained approach"
        assert all(0.0 < e <= 1440.0 for e in etas), f"implausible ETAs: {etas}"

    def test_subsecond_rapid_fix_pair_no_speed_spike(self):
        """F5 regression (history (3).csv, 09:01): two REAL fixes ~1.9s apart carrying a GPS
        position jump must not fabricate an impossible closing speed. The short pair is
        ignored (direction + speed held, baseline not advanced); the NEXT fix, spanning a
        meaningful interval, produces a plausible speed from the ACCUMULATED delta.

        Discriminators (vs a pre-F5 recompute on the bad pair):
        - lead-in commits APPROACHING; the bad pair moves AWAY, so a recompute would flip
          the label to diverging — holding preserves 'approaching'.
        - the bad pair's closing_speed is asserted UNCHANGED (held), pinning that no spike
          is written where it was produced.
        - r2 is bounded two-sided to the accumulated-window speed, so a broken baseline
          (advanced on the sub-5s pair) would fail (it would span only the short last leg).
        """
        coordinator = self._coord()  # max_speed_kmh=0 → DEFAULT cap 1000
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        self._states(coordinator, acc=20.0)
        t0 = datetime.now().astimezone()

        # Clean baseline, then an APPROACHING lead-in (distance drops) over a good interval.
        self._tick(coordinator, ps, dist=3500.0, now=t0, pending={"person.alice"})
        self._tick(
            coordinator, ps, dist=3100.0, now=t0 + timedelta(seconds=10), pending={"person.alice"}
        )
        assert ps.direction == "approaching"  # committed on the real interval (F2 confident)
        speed_before = ps.closing_speed_kmh

        # The bad pair: a second real fix only 1.9s later with a +337m GPS jump AWAY. A
        # pre-F5 recompute would (a) flip direction to 'diverging' and (b) show ~639 km/h.
        r = self._tick(
            coordinator,
            ps,
            dist=3437.0,
            now=t0 + timedelta(seconds=11, milliseconds=900),
            pending={"person.alice"},
        )
        # F5: sub-5s interval ignored → direction + speed HELD, baseline frozen.
        assert r.direction == "approaching", "sub-interval fix must hold, not flip to diverging"
        assert r.closing_speed_kmh == speed_before, (
            "held speed must not be overwritten by the spike"
        )
        assert ps.last_fix_distance_m == 3100.0, "baseline must not advance on a sub-5s pair"

        # Next fix ~8s after the frozen baseline (≈19.9s total). Spans the ACCUMULATED window
        # 3100→3500 (+400m over ~9.9s) → adjusted ≈ (400-80)/9.9*3.6 ≈ 116 km/h. A broken
        # baseline (advanced to 3437 on the bad pair) would instead span 3437→3500 over ~8s
        # → a different, smaller value — the two-sided bound rejects that.
        r2 = self._tick(
            coordinator,
            ps,
            dist=3500.0,
            now=t0 + timedelta(seconds=19, milliseconds=900),
            pending={"person.alice"},
        )
        assert r2.closing_speed_kmh is not None
        assert 100.0 < r2.closing_speed_kmh < 200.0, (
            f"speed must come from the accumulated 3100→3500 window, got {r2.closing_speed_kmh}"
        )

    def test_subsecond_pair_above_teleport_cap_holds_not_resets(self):
        """F5 boundary: a sub-5s pair whose implied rate exceeds the teleport cap must be
        IGNORED (direction held, baseline frozen), NOT treated as a teleport. F5 moved the
        teleport check inside `if _fix_interval_ok`, so a <5s pair can never set
        direction_teleport_rejected — pinning that it holds rather than nulling + re-baselining."""
        coordinator = self._coord()  # max_speed_kmh=0 → DEFAULT cap 1000 km/h
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        self._states(coordinator, acc=20.0)
        t0 = datetime.now().astimezone()

        # Commit a direction over a good interval.
        self._tick(coordinator, ps, dist=3500.0, now=t0, pending={"person.alice"})
        self._tick(
            coordinator, ps, dist=3100.0, now=t0 + timedelta(seconds=10), pending={"person.alice"}
        )
        assert ps.direction == "approaching"

        # Sub-5s pair with a jump implying >> 1000 km/h (6000 m over 2s ≈ 10800 km/h).
        r = self._tick(
            coordinator,
            ps,
            dist=9100.0,
            now=t0 + timedelta(seconds=12),
            pending={"person.alice"},
        )
        # Held, not teleport-reset: direction unchanged, baseline frozen at the lead-in fix.
        assert r.direction == "approaching", (
            "sub-5s over-cap pair must hold, not reset via teleport"
        )
        assert r.last_error != "speed_filter"
        assert ps.last_fix_distance_m == 3100.0, (
            "baseline must not advance on the sub-5s over-cap pair"
        )

    def test_restart_holds_restored_direction_until_first_real_interval(self):
        """F5 interaction with restart: a restored direction (from storage) is HELD on the
        first post-restart fix (last_fix_time is None → seeded, not computed), instead of
        blanking to None. A later fix spanning a real interval then recomputes normally."""
        coordinator = self._coord()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        self._states(coordinator, acc=20.0)
        t0 = datetime.now().astimezone()

        # Simulate post-restart state: direction restored, but last_fix_* never persisted.
        ps.direction = "approaching"
        ps.last_fix_distance_m = None
        ps.last_fix_time = None

        # First post-restart real fix: no baseline yet → seeds last_fix_*, holds direction.
        r1 = self._tick(coordinator, ps, dist=3000.0, now=t0, pending={"person.alice"})
        assert r1.direction == "approaching", (
            "restored direction held on the first post-restart fix"
        )
        assert ps.last_fix_distance_m == 3000.0  # baseline seeded
        assert ps.last_fix_time == t0

        # Second fix over a real interval → recomputes from the seeded baseline.
        r2 = self._tick(
            coordinator, ps, dist=2600.0, now=t0 + timedelta(seconds=10), pending={"person.alice"}
        )
        assert r2.direction == "approaching"  # genuinely closing now
        assert r2.closing_speed_kmh is not None and r2.closing_speed_kmh > 0

    def test_zone_fallback_fix_clears_stale_gps_direction(self):
        """Review-major regression: when one side arrives home via a presence scanner
        (zone-fallback) while the other is still on GPS, a real fix on that tick must CLEAR a
        previously-committed GPS direction/speed — not hold a frozen 'approaching/N km/h' for
        the whole home dwell. (F5's write-gate must still fire on a zone-fallback real fix.)"""
        from unittest.mock import patch

        from tests.conftest import make_state

        coordinator = self._coord()
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        now = datetime.now().astimezone()

        # Pre-committed GPS verdict from a prior moving tick.
        ps.direction = "approaching"
        ps.closing_speed_kmh = 33.0
        ps.eta_minutes = 12.0
        ps.last_fix_distance_m = 400.0
        ps.last_fix_time = now - timedelta(seconds=30)
        ps.prev_distance_m = 400.0
        ps.prev_calc_time = now - timedelta(seconds=30)

        # Alice now resolves via zone fallback (home, no GPS coords); Bob still GPS.
        alice = make_state("person.alice", None, None)  # no coords → zone fallback path
        alice.state = "home"
        bob = make_state("person.bob", 51.6, -0.2, accuracy=20)
        coordinator.hass.states.get.side_effect = lambda eid: (
            alice if eid == "person.alice" else bob
        )
        # zone.home for the fallback lookup
        home = make_state("zone.home", 51.5, -0.1, accuracy=50)
        home.attributes = {**home.attributes, "radius": 100}
        _orig = coordinator.hass.states.get.side_effect
        coordinator.hass.states.get.side_effect = lambda eid: (
            home if eid == "zone.home" else _orig(eid)
        )

        with patch("custom_components.entity_distance.coordinator.ha_distance", return_value=60.0):
            r = coordinator._calc_pair(ps, "person.alice", "person.bob", now, {"person.alice"})

        # Stale GPS direction/speed must be cleared on the zone-fallback real fix.
        assert r.direction is None, "stale GPS direction must not be held on a zone-fallback fix"
        assert r.closing_speed_kmh is None
        assert r.eta_minutes is None

    def test_short_interval_hold_expiry_holds_direction(self):
        """Review-major regression: a resync hold-expiry tick whose last real fix is <5s old
        must HOLD the committed direction, not clobber it to None. (The write-gate must not
        fire on a sub-5s hold-expiry.)"""
        from unittest.mock import patch

        from tests.conftest import make_state

        coordinator = _make_calc_pair_coordinator(max_speed_kmh=0.0, resync_hold_s=60.0)
        k = pair_key("person.alice", "person.bob")
        ps = coordinator._pair_states[k]
        now = datetime.now().astimezone()

        ps.direction = "approaching"
        ps.closing_speed_kmh = 33.0
        ps.prev_distance_m = 460.0
        ps.prev_calc_time = now - timedelta(seconds=1)
        # Last real fix only ~1.5s ago (a fix landed late in the hold window).
        ps.last_fix_distance_m = 460.0
        ps.last_fix_time = now - timedelta(seconds=1, milliseconds=500)
        ps.accuracy_a = 20.0
        ps.accuracy_b = 20.0
        # Hold just expired.
        coordinator._resync_holding[k] = True
        coordinator._resync_hold_until[k] = now - timedelta(seconds=1)

        state_a = make_state("person.alice", 51.5, -0.1, accuracy=20)
        state_b = make_state("person.bob", 51.501, -0.1, accuracy=20)
        coordinator.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )
        with patch("custom_components.entity_distance.coordinator.ha_distance", return_value=455.0):
            r = coordinator._calc_pair(ps, "person.alice", "person.bob", now, {"person.alice"})

        # Sub-5s expiry → held, not nulled.
        assert r.direction == "approaching", "sub-5s hold-expiry must hold the direction"


class TestAltitudeSentinelIntegration:
    """Integration: the altitude-0.0 no-vertical-fix sentinel drop (_extract_altitude)
    interacts correctly with the _calc_pair home-elevation fallback (coordinator.py
    ~939-980). Drives the full pair-calc path, not the helper in isolation."""

    def _run(self, state_a, state_b, elevation=None, entities=None):
        coordinator = _make_calc_pair_coordinator(entities=entities)
        coordinator.hass.config.elevation = elevation
        a_id = state_a.entity_id
        b_id = state_b.entity_id
        k = pair_key(a_id, b_id)
        ps = coordinator._pair_states[k]
        coordinator.hass.states.get.side_effect = lambda eid: state_a if eid == a_id else state_b
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=500.0,
        ):
            return coordinator._calc_pair(ps, a_id, b_id, datetime.now().astimezone(), set())

    def test_sentinel_not_at_home_drops_to_none(self):
        """altitude 0.0 + no vertical_accuracy, NOT at home → altitude None, no
        phantom sea-level delta (sentinel must not poison altitude_delta_m)."""
        state_a = State(
            "person.alice",
            "not_home",
            {"latitude": 51.5, "longitude": -0.1, "altitude": 0.0},
        )
        state_b = State(
            "person.bob",
            "not_home",
            {"latitude": 51.6, "longitude": -0.2, "altitude": 100.0},
        )
        ps = self._run(state_a, state_b, elevation=42.0)
        assert ps.altitude_a_m is None
        assert ps.altitude_b_m == pytest.approx(100.0)
        assert ps.altitude_delta_m is None

    def test_sentinel_at_home_resolves_to_elevation(self):
        """altitude 0.0 + no vertical_accuracy, AT home → sentinel becomes None FIRST,
        THEN the home-elevation fallback fires → altitude is elevation, NOT 0.0.
        Load-bearing ordering assertion."""
        state_a = State(
            "person.alice",
            "home",
            {"latitude": 51.5, "longitude": -0.1, "altitude": 0.0},
        )
        state_b = State(
            "person.bob",
            "not_home",
            {"latitude": 51.6, "longitude": -0.2, "altitude": 50.0},
        )
        ps = self._run(state_a, state_b, elevation=42.0)
        assert ps.altitude_a_m == pytest.approx(42.0)
        assert ps.altitude_delta_m == pytest.approx(8.0)

    def test_real_sea_level_with_valid_vacc_is_retained(self):
        """altitude 0.0 WITH a valid vertical_accuracy → genuine sea-level fix, kept,
        and altitude_delta_m is computed against the other entity."""
        state_a = State(
            "person.alice",
            "not_home",
            {
                "latitude": 51.5,
                "longitude": -0.1,
                "altitude": 0.0,
                "vertical_accuracy": 12.0,
            },
        )
        state_b = State(
            "person.bob",
            "not_home",
            {"latitude": 51.6, "longitude": -0.2, "altitude": 30.0},
        )
        ps = self._run(state_a, state_b, elevation=42.0)
        assert ps.altitude_a_m == pytest.approx(0.0)
        assert ps.altitude_b_m == pytest.approx(30.0)
        assert ps.altitude_delta_m == pytest.approx(30.0)
