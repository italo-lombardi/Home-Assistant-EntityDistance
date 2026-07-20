"""Tests for multi-entity group tracking (3+ entities)."""

from __future__ import annotations

from datetime import UTC, datetime
import itertools
from unittest.mock import MagicMock, patch

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State

from custom_components.entity_distance.models import GroupData, PairState, pair_key


class TestGroupData:
    def _make_group(self, entities: list[str]) -> GroupData:
        pairs = {}
        for a, b in itertools.combinations(entities, 2):
            k = pair_key(a, b)
            pairs[k] = PairState(entity_a_id=k[0], entity_b_id=k[1])
        return GroupData(pairs=pairs)

    def test_three_entities_creates_three_pairs(self):
        gd = self._make_group(["person.alice", "person.bob", "person.carol"])
        assert len(gd.pairs) == 3

    def test_four_entities_creates_six_pairs(self):
        gd = self._make_group(["person.a", "person.b", "person.c", "person.d"])
        assert len(gd.pairs) == 6

    def test_pair_key_consistent_regardless_of_order(self):
        k1 = pair_key("person.alice", "person.bob")
        k2 = pair_key("person.bob", "person.alice")
        assert k1 == k2

    def test_any_in_proximity_false_by_default(self):
        gd = self._make_group(["person.alice", "person.bob", "person.carol"])
        assert gd.any_in_proximity is False

    def test_all_in_proximity_false_by_default(self):
        gd = self._make_group(["person.alice", "person.bob", "person.carol"])
        assert gd.all_in_proximity is False

    def test_min_distance_none_by_default(self):
        gd = self._make_group(["person.alice", "person.bob"])
        assert gd.min_distance_m is None

    def test_any_in_proximity_computed(self):
        gd = self._make_group(["person.alice", "person.bob", "person.carol"])
        k = list(gd.pairs.keys())[0]
        gd.pairs[k].proximity = True
        gd.any_in_proximity = any(ps.proximity for ps in gd.pairs.values())
        assert gd.any_in_proximity is True

    def test_all_in_proximity_requires_all_pairs(self):
        gd = self._make_group(["person.alice", "person.bob", "person.carol"])
        for ps in gd.pairs.values():
            ps.proximity = True
        gd.all_in_proximity = all(ps.proximity for ps in gd.pairs.values())
        assert gd.all_in_proximity is True

    def test_all_in_proximity_false_if_any_pair_not_proximate(self):
        gd = self._make_group(["person.alice", "person.bob", "person.carol"])
        pairs = list(gd.pairs.values())
        pairs[0].proximity = True
        pairs[1].proximity = False
        pairs[2].proximity = True
        gd.all_in_proximity = all(ps.proximity for ps in gd.pairs.values())
        assert gd.all_in_proximity is False


class TestPairKeyHelper:
    def test_sorts_alphabetically(self):
        assert pair_key("z.entity", "a.entity") == ("a.entity", "z.entity")

    def test_same_result_both_orders(self):
        assert pair_key("person.bob", "person.alice") == pair_key("person.alice", "person.bob")

    def test_unique_keys_for_different_pairs(self):
        k1 = pair_key("person.alice", "person.bob")
        k2 = pair_key("person.alice", "person.carol")
        assert k1 != k2


class TestGroupSensors:
    def _make_min_distance_sensor(self, group_data: GroupData):
        from custom_components.entity_distance.sensor import MinDistanceSensor

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.data = group_data
        entry = MagicMock()
        entry.entry_id = "test_group_entry"
        sensor = MinDistanceSensor.__new__(MinDistanceSensor)
        sensor.coordinator = coordinator
        sensor._entry = entry
        sensor._attr_unique_id = "test_group_min_distance"
        sensor._attr_device_info = {}
        return sensor

    def test_min_distance_returns_none_when_not_set(self):
        gd = GroupData(pairs={})
        sensor = self._make_min_distance_sensor(gd)
        assert sensor.native_value is None

    def test_min_distance_returns_value(self):
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.distance_m = 350.0
        ps.data_valid = True
        gd = GroupData(pairs={k: ps}, min_distance_m=350.0)
        sensor = self._make_min_distance_sensor(gd)
        assert sensor.native_value == 350.0

    def test_min_distance_picks_smallest_across_pairs(self):
        entities = ["person.alice", "person.bob", "person.carol"]
        pairs = {}
        distances = [100.0, 500.0, 1000.0]
        for i, (a, b) in enumerate(itertools.combinations(entities, 2)):
            k = pair_key(a, b)
            ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
            ps.distance_m = distances[i]
            ps.data_valid = True
            pairs[k] = ps
        min_dist = min(ps.distance_m for ps in pairs.values() if ps.distance_m is not None)
        gd = GroupData(pairs=pairs, min_distance_m=min_dist)
        sensor = self._make_min_distance_sensor(gd)
        assert sensor.native_value == 100.0


# ---------------------------------------------------------------------------
# Helpers shared by _calc_pair test classes
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)

_BUCKET_THRESHOLDS = {"very_near": 100, "near": 500, "mid": 2000, "far": 10000}


def _make_coordinator(
    max_accuracy_m: float = 200.0,
    max_speed_kmh: float = 1000.0,
    entry_threshold_m: float = 500.0,
    exit_threshold_m: float = 500.0,
    require_reliable: bool = False,
    min_updates_reliable: int = 3,
):
    """Create a minimal EntityDistanceCoordinator without calling __init__."""
    from custom_components.entity_distance.coordinator import EntityDistanceCoordinator

    coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
    coord.hass = MagicMock()
    coord._entry = MagicMock()
    coord._entities = ["person.alice", "person.bob"]
    coord._pair_states = {}
    coord._max_accuracy_m = max_accuracy_m
    coord._max_speed_kmh = max_speed_kmh
    coord._entry_threshold_m = entry_threshold_m
    coord._exit_threshold_m = exit_threshold_m
    coord._bucket_thresholds = _BUCKET_THRESHOLDS
    coord._resync_silence_s = 0  # disable resync logic by default
    coord._resync_hold_s = 60
    coord._grace_window_s = 900.0
    coord._resync_holding = {}
    coord._resync_hold_until = {}
    coord._min_updates_reliable = min_updates_reliable
    coord._require_reliable = require_reliable
    coord._altitude_aligned_threshold_m = 5.0
    coord._max_vertical_accuracy_m = 0.0
    return coord


def _make_state(entity_id: str, lat: float, lon: float, accuracy: float | None = None) -> State:
    attrs: dict = {"latitude": lat, "longitude": lon}
    if accuracy is not None:
        attrs["gps_accuracy"] = accuracy
    return State(entity_id, "home", attrs)


def _fresh_pair() -> PairState:
    k = pair_key("person.alice", "person.bob")
    return PairState(entity_a_id=k[0], entity_b_id=k[1])


# ---------------------------------------------------------------------------
# TestCalcPairInvalidations
# ---------------------------------------------------------------------------


class TestCalcPairInvalidations:
    def test_entity_a_missing(self):
        coord = _make_coordinator()
        state_b = _make_state("person.bob", 51.5, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: None if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()

        result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.data_valid is False
        assert result.last_error == "entity_not_found"

    def test_entity_b_missing(self):
        coord = _make_coordinator()
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else None
        )
        ps = _fresh_pair()

        result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.data_valid is False
        assert result.last_error == "entity_not_found"

    def test_entity_a_unavailable(self):
        coord = _make_coordinator()
        state_a = State("person.alice", STATE_UNAVAILABLE, {"latitude": 51.5, "longitude": -0.1})
        state_b = _make_state("person.bob", 51.5, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()

        result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.data_valid is False
        assert result.last_error == "entity_unavailable"

    def test_entity_b_unknown(self):
        coord = _make_coordinator()
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = State("person.bob", STATE_UNKNOWN, {"latitude": 51.5, "longitude": -0.09})
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()

        result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.data_valid is False
        assert result.last_error == "entity_unavailable"

    def test_coord_extraction_fails(self):
        coord = _make_coordinator()
        # States present but no lat/lon attributes
        state_a = State("person.alice", "home", {})
        state_b = State("person.bob", "home", {})
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()

        result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.data_valid is False
        assert result.last_error == "coord_extraction_failed"

    def test_accuracy_filter_a(self):
        coord = _make_coordinator(max_accuracy_m=200.0)
        # entity_a has accuracy 500m, which exceeds max_accuracy_m 200m
        state_a = _make_state("person.alice", 51.5, -0.1, accuracy=500.0)
        state_b = _make_state("person.bob", 51.501, -0.1, accuracy=20.0)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=111.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.data_valid is False
        assert result.last_error == "accuracy_filter_a"

    def test_accuracy_filter_b(self):
        coord = _make_coordinator(max_accuracy_m=200.0)
        state_a = _make_state("person.alice", 51.5, -0.1, accuracy=20.0)
        # entity_b has accuracy 500m, exceeds max
        state_b = _make_state("person.bob", 51.501, -0.1, accuracy=500.0)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=111.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.data_valid is False
        assert result.last_error == "accuracy_filter_b"

    def test_accuracy_filter_skipped_for_zone_entity(self):
        """Zone entities should bypass the accuracy filter even with high gps_accuracy."""
        coord = _make_coordinator(max_accuracy_m=200.0)
        # zone entity with very poor accuracy — should not be filtered
        state_a = State(
            "zone.home",
            "zoning",
            {"latitude": 51.5, "longitude": -0.1, "gps_accuracy": 9999.0},
        )
        state_b = _make_state("person.bob", 51.501, -0.1, accuracy=20.0)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "zone.home" else state_b
        )
        ps = PairState(entity_a_id="person.bob", entity_b_id="zone.home")

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=111.0,
        ):
            result = coord._calc_pair(ps, "zone.home", "person.bob", _NOW, set())

        assert result.data_valid is True
        assert result.last_error is None

    def test_speed_filter(self):
        coord = _make_coordinator(max_speed_kmh=150.0)
        state_a = _make_state("person.alice", 51.5, -0.1, accuracy=20.0)
        state_b = _make_state("person.bob", 51.501, -0.1, accuracy=20.0)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()
        # Simulate a previous distance and time so speed check fires
        ps.prev_distance_m = 0.0
        ps.prev_calc_time = datetime(2024, 6, 1, 11, 59, 0, tzinfo=UTC)  # 60s earlier

        # Distance jumped 100_000m in 60s → implied speed = 100000/60*3.6 = 6000 km/h > 150
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100_000.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.data_valid is False
        assert result.last_error == "speed_filter"


# ---------------------------------------------------------------------------
# TestCalcPairProximityTransitions
# ---------------------------------------------------------------------------


class TestCalcPairProximityTransitions:
    def test_enters_proximity(self):
        coord = _make_coordinator(entry_threshold_m=500.0, exit_threshold_m=500.0)
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()
        ps.proximity = False

        # 200m is well inside entry_threshold_m of 500m
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=200.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.proximity is True
        assert result.proximity_since == _NOW

    def test_exits_proximity(self):
        coord = _make_coordinator(entry_threshold_m=500.0, exit_threshold_m=500.0)
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.510, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC)
        prior_lts = datetime(2024, 6, 1, 11, 59, 0, tzinfo=UTC)
        ps.last_seen_together = prior_lts

        # 800m is beyond exit_threshold_m of 500m
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=800.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.proximity is False
        # last_seen_together holds the last in-proximity stamp, not cleared on exit
        assert result.last_seen_together == prior_lts

    def test_stays_in_proximity(self):
        coord = _make_coordinator(entry_threshold_m=500.0, exit_threshold_m=500.0)
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC)

        # 150m — inside both thresholds, proximity stays True
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=150.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.proximity is True

    def test_stays_outside(self):
        coord = _make_coordinator(entry_threshold_m=500.0, exit_threshold_m=500.0)
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.520, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()
        ps.proximity = False

        # 2200m — outside entry threshold, stays False
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=2200.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.proximity is False


# ---------------------------------------------------------------------------
# TestCalcPairDirection
# ---------------------------------------------------------------------------


class TestCalcPairDirection:
    def test_first_calc_no_prev_distance(self):
        coord = _make_coordinator()
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()
        # No previous data → direction stays None

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=300.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.direction is None

    def test_stationary(self):
        coord = _make_coordinator()
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()
        ps.prev_distance_m = 300.0  # current will also be 300.0 → delta < 50m
        ps.prev_calc_time = datetime(2024, 6, 1, 11, 59, 0, tzinfo=UTC)

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=300.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.direction == "stationary"

    def test_approaching(self):
        coord = _make_coordinator()
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()
        ps.prev_distance_m = 600.0  # current 200m → delta = -400m → approaching
        ps.prev_calc_time = datetime(2024, 6, 1, 11, 59, 0, tzinfo=UTC)

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=200.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.direction == "approaching"
        assert result.eta_minutes is not None

    def test_diverging(self):
        coord = _make_coordinator()
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        ps = _fresh_pair()
        ps.prev_distance_m = 200.0  # current 800m → delta = +600m → diverging
        ps.prev_calc_time = datetime(2024, 6, 1, 11, 59, 0, tzinfo=UTC)

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=800.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.direction == "diverging"


# ---------------------------------------------------------------------------
# TestCalcPairEvents
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TestCalcPairNoEvents — v0.3.0 removed all entity_distance_* bus events.
# Verify coordinator never calls hass.bus.fire while still mutating ps.proximity
# correctly so sensor / binary_sensor consumers see the right state.
# ---------------------------------------------------------------------------


class TestCalcPairNoEvents:
    def _setup(self, require_reliable: bool = False, min_updates: int = 1):
        coord = _make_coordinator(
            entry_threshold_m=500.0,
            exit_threshold_m=500.0,
            require_reliable=require_reliable,
            min_updates_reliable=min_updates,
        )
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        return coord

    def test_enter_transition_no_event_but_proximity_set(self):
        coord = self._setup(min_updates=1)
        ps = _fresh_pair()
        ps.proximity = False
        ps.update_count_a = 5
        ps.update_count_b = 5

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=200.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert coord.hass.bus.fire.call_count == 0
        assert result.proximity is True

    def test_leave_transition_no_event_but_proximity_cleared(self):
        coord = self._setup()
        ps = _fresh_pair()
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC)
        ps.update_count_a = 5
        ps.update_count_b = 5

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=800.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert coord.hass.bus.fire.call_count == 0
        assert result.proximity is False

    def test_steady_tick_fires_no_events(self):
        coord = self._setup()
        ps = _fresh_pair()
        ps.proximity = False
        ps.update_count_a = 5
        ps.update_count_b = 5

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=1200.0,
        ):
            coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert coord.hass.bus.fire.call_count == 0

    def test_enter_unreliable_transition_no_event(self):
        # Pre-v0.3.0 this fired entity_distance_enter_unreliable. Now zero events
        # and ps.proximity still flips on (require_reliable=False default).
        coord = self._setup(min_updates=10)
        ps = _fresh_pair()
        ps.proximity = False
        ps.update_count_a = 1  # below min_updates_reliable of 10
        ps.update_count_b = 1

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=200.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert coord.hass.bus.fire.call_count == 0
        assert result.proximity is True
        assert coord.is_reliable(result) is False
