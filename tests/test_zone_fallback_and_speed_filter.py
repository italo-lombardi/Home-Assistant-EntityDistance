"""Tests for zone-coordinate fallback (HA 2026.7) and accuracy-adjusted speed filter."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import State

from custom_components.entity_distance.coordinator import (
    _find_zone_by_name,
    _resolve_coords,
)
from custom_components.entity_distance.models import pair_key
from tests.conftest import make_state, make_zone_state

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_hass(zone_states: list[State] | None = None, extra: dict[str, State] | None = None):
    """Return a minimal hass mock with a state machine."""
    hass = MagicMock()
    zone_states = zone_states or []
    extra = extra or {}

    state_map: dict[str, State] = {s.entity_id: s for s in zone_states}
    state_map.update(extra)

    hass.states.get.side_effect = lambda eid: state_map.get(eid)
    hass.states.async_all.side_effect = lambda domain: [
        s for s in state_map.values() if s.entity_id.startswith(f"{domain}.")
    ]
    return hass


def _make_coord_coordinator(
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
    hass=None,
):
    import itertools

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

    if entities is None:
        entities = ["person.alice", "person.bob"]

    coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
    coord._entities = entities
    coord._entry_threshold_m = entry_threshold_m
    coord._exit_threshold_m = exit_threshold_m
    coord._max_accuracy_m = max_accuracy_m
    coord._stationary_threshold_m = max(15.0, max_accuracy_m * 0.15)
    coord._max_speed_kmh = max_speed_kmh
    coord._resync_silence_s = resync_silence_s
    coord._resync_hold_s = resync_hold_s
    coord._grace_window_s = 900.0
    coord._require_reliable = require_reliable
    coord._min_updates_reliable = min_updates_reliable
    coord._updates_window_s = updates_window_s
    coord._bucket_thresholds = {
        BUCKET_VERY_NEAR: DEFAULT_ZONE_VERY_NEAR_M,
        BUCKET_NEAR: DEFAULT_ZONE_NEAR_M,
        BUCKET_MID: DEFAULT_ZONE_MID_M,
        BUCKET_FAR: DEFAULT_ZONE_FAR_M,
    }

    pairs = {}
    resync_holding = {}
    resync_hold_until = {}
    for a, b in itertools.combinations(entities, 2):
        k = pair_key(a, b)
        from custom_components.entity_distance.models import PairState

        pairs[k] = PairState(entity_a_id=k[0], entity_b_id=k[1])
        resync_holding[k] = False
        resync_hold_until[k] = None

    coord._pair_states = pairs
    coord._resync_holding = resync_holding
    coord._resync_hold_until = resync_hold_until
    coord.hass = hass or MagicMock()
    return coord


# ---------------------------------------------------------------------------
# _find_zone_by_name
# ---------------------------------------------------------------------------


class TestFindZoneByName:
    def test_fast_path_direct_object_id(self):
        zone = make_zone_state("zone.home", 51.5, -0.1)
        hass = _make_hass([zone])
        result = _find_zone_by_name(hass, "home")
        assert result is zone

    def test_fast_path_slugified_name(self):
        zone = make_zone_state("zone.my_work", 51.6, -0.2)
        hass = _make_hass([zone])
        result = _find_zone_by_name(hass, "My Work")
        assert result is zone

    def test_slow_path_state_name_match(self):
        # Zone with object_id "office" but State.name "The Office"
        zone = State(
            "zone.office",
            "0",
            {
                "latitude": 51.5,
                "longitude": -0.1,
                "radius": 50,
                "friendly_name": "The Office",
            },
        )
        hass = _make_hass([zone])
        result = _find_zone_by_name(hass, "The Office")
        assert result is zone

    def test_slow_path_case_insensitive(self):
        zone = State(
            "zone.work",
            "0",
            {
                "latitude": 51.5,
                "longitude": -0.1,
                "radius": 50,
                "friendly_name": "Work",
            },
        )
        hass = _make_hass([zone])
        result = _find_zone_by_name(hass, "work")
        assert result is zone

    def test_no_match_returns_none(self):
        zone = make_zone_state("zone.home", 51.5, -0.1)
        hass = _make_hass([zone])
        result = _find_zone_by_name(hass, "nowhere")
        assert result is None

    def test_empty_name_returns_none(self):
        hass = _make_hass([])
        result = _find_zone_by_name(hass, "")
        assert result is None

    def test_no_zones_returns_none(self):
        hass = _make_hass([])
        result = _find_zone_by_name(hass, "home")
        assert result is None


# ---------------------------------------------------------------------------
# _resolve_coords
# ---------------------------------------------------------------------------


class TestResolveCoords:
    def test_gps_coords_returned_as_is(self):
        state = make_state("person.alice", 51.5, -0.1, accuracy=20)
        hass = _make_hass()
        result, fallback = _resolve_coords(state, hass)
        assert result == (51.5, -0.1, 20)
        assert fallback is False

    def test_zone_entity_no_fallback(self):
        zone = make_zone_state("zone.home", 51.5, -0.1)
        hass = _make_hass([zone])
        result, fallback = _resolve_coords(zone, hass)
        # zone.home has lat/lon → _get_coords succeeds, no fallback needed
        assert result is not None
        assert fallback is False

    def test_zone_entity_no_coords_returns_none_not_fallback(self):
        # Zone entity with no lat/lon (misconfigured) — must return None, False
        # not attempt a recursive zone fallback.
        zone = State("zone.broken", "0", {})
        hass = _make_hass([zone])
        result, fallback = _resolve_coords(zone, hass)
        assert result is None
        assert fallback is False

    def test_not_home_state_returns_none(self):
        state = State("person.alice", "not_home", {})
        hass = _make_hass()
        result, fallback = _resolve_coords(state, hass)
        assert result is None
        assert fallback is False

    def test_unavailable_state_returns_none(self):
        state = State("person.alice", STATE_UNAVAILABLE, {})
        hass = _make_hass()
        result, fallback = _resolve_coords(state, hass)
        assert result is None
        assert fallback is False

    def test_unknown_state_returns_none(self):
        state = State("person.alice", STATE_UNKNOWN, {})
        hass = _make_hass()
        result, fallback = _resolve_coords(state, hass)
        assert result is None
        assert fallback is False

    def test_home_state_no_gps_uses_zone_fallback(self):
        state = State("person.alice", "home", {})
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        hass = _make_hass([zone])
        result, fallback = _resolve_coords(state, hass)
        assert fallback is True
        assert result == (51.5, -0.1, 100.0)

    def test_named_zone_state_no_gps_uses_zone_fallback(self):
        state = State("person.alice", "work", {})
        zone = make_zone_state("zone.work", 51.6, -0.2, radius=50)
        hass = _make_hass([zone])
        result, fallback = _resolve_coords(state, hass)
        assert fallback is True
        assert result == (51.6, -0.2, 50.0)

    def test_zone_not_found_returns_none(self):
        state = State("person.alice", "home", {})
        hass = _make_hass([])  # no zones
        result, fallback = _resolve_coords(state, hass)
        assert result is None
        assert fallback is False

    def test_zone_fallback_missing_radius_returns_none_accuracy(self):
        state = State("person.alice", "home", {})
        zone = State("zone.home", "0", {"latitude": 51.5, "longitude": -0.1})  # no radius
        hass = _make_hass([zone])
        result, fallback = _resolve_coords(state, hass)
        assert fallback is True
        assert result is not None
        lat, lon, acc = result
        assert acc is None

    def test_gps_coords_take_priority_over_zone_fallback(self):
        # person has both GPS coords AND state="home" — GPS must win
        state = make_state("person.alice", 51.5, -0.1, accuracy=10)
        # state is "home" from make_state default
        zone = make_zone_state("zone.home", 99.0, 99.0, radius=100)
        hass = _make_hass([zone])
        result, fallback = _resolve_coords(state, hass)
        assert fallback is False
        assert result[0] == 51.5  # GPS lat, not zone lat


# ---------------------------------------------------------------------------
# Speed filter — noise budget and co-location guard
# ---------------------------------------------------------------------------


class TestSpeedFilterNoiseBudget:
    """Accuracy-adjusted speed filter: GPS bounce in same car must not reject."""

    def _run_speed_filter(
        self,
        prev_dist,
        new_dist,
        delta_s,
        acc_a,
        acc_b,
        prev_acc_a=None,
        prev_acc_b=None,
        max_speed_kmh=1000.0,
    ):

        coord = _make_coord_coordinator(max_speed_kmh=max_speed_kmh)
        k = pair_key("person.alice", "person.bob")
        ps = coord._pair_states[k]

        now = datetime.now().astimezone()
        ps.prev_distance_m = prev_dist
        ps.prev_calc_time = now - timedelta(seconds=delta_s)
        ps.accuracy_a = prev_acc_a
        ps.accuracy_b = prev_acc_b

        state_a = make_state("person.alice", 51.5, -0.1, accuracy=acc_a)
        state_b = make_state("person.bob", 51.5, -0.1, accuracy=acc_b)
        coord.hass.states.get.side_effect = lambda eid: (
            state_a if eid == "person.alice" else state_b
        )
        coord.hass.states.async_all.return_value = []

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=new_dist,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", now, set())
        return result

    def test_gps_bounce_in_same_car_passes(self):
        # Two phones in same car. Bounce-back: 1285m delta in 5s = 924 km/h raw.
        # noise_budget = 200+200+200+200=800m, adjusted=485m → 349 km/h < 1000. Passes.
        result = self._run_speed_filter(
            prev_dist=1285.0,
            new_dist=0.0,
            delta_s=5.0,
            acc_a=200.0,
            acc_b=200.0,
            prev_acc_a=200.0,
            prev_acc_b=200.0,
            max_speed_kmh=1000.0,
        )
        assert result.data_valid is True

    def test_true_teleport_rejected(self):
        # 50km jump in 60s, small accuracy. adjusted_delta >> threshold.
        result = self._run_speed_filter(
            prev_dist=0.0,
            new_dist=50_000.0,
            delta_s=60.0,
            acc_a=10.0,
            acc_b=10.0,
            prev_acc_a=10.0,
            prev_acc_b=10.0,
            max_speed_kmh=1000.0,
        )
        assert result.data_valid is False
        assert result.last_error == "speed_filter"

    def test_none_accuracy_degrades_to_raw_behavior(self):
        # No accuracy reported → noise_budget=0, adjusted=raw delta.
        # 50km/60s = 3000 km/h > 1000 → rejected.
        result = self._run_speed_filter(
            prev_dist=0.0,
            new_dist=50_000.0,
            delta_s=60.0,
            acc_a=None,
            acc_b=None,
            prev_acc_a=None,
            prev_acc_b=None,
            max_speed_kmh=1000.0,
        )
        assert result.data_valid is False
        assert result.last_error == "speed_filter"

    def test_colocation_guard_skips_filter(self):
        # prev_dist=0, new_dist=5m → abs(5-0)=5m.
        # noise_budget = 50+50+50+50=200m → 5 <= 200 → guard false → block skipped.
        # Filter skipped entirely.
        result = self._run_speed_filter(
            prev_dist=0.0,
            new_dist=5.0,
            delta_s=5.0,
            acc_a=50.0,
            acc_b=50.0,
            prev_acc_a=50.0,
            prev_acc_b=50.0,
            max_speed_kmh=1.0,  # absurdly low — would trigger on raw
        )
        assert result.data_valid is True

    def test_speed_filter_disabled_when_max_speed_zero(self):
        result = self._run_speed_filter(
            prev_dist=0.0,
            new_dist=100_000.0,
            delta_s=10.0,
            acc_a=10.0,
            acc_b=10.0,
            max_speed_kmh=0.0,
        )
        assert result.data_valid is True


# ---------------------------------------------------------------------------
# Zone fallback in _calc_pair — is_zone extension and filter skips
# ---------------------------------------------------------------------------


class TestCalcPairZoneFallback:
    """_calc_pair with zone-fallback entity: accuracy/speed/direction guards correct."""

    def _calc_pair_with_zone(
        self,
        person_state,
        zone,
        other_state,
        max_speed_kmh=1000.0,
        max_accuracy_m=150.0,
        prev_dist=None,
        prev_calc_offset_s=None,
    ):
        hass = _make_hass(
            zone_states=[zone],
            extra={
                person_state.entity_id: person_state,
                other_state.entity_id: other_state,
            },
        )
        coord = _make_coord_coordinator(
            entities=[person_state.entity_id, other_state.entity_id],
            max_speed_kmh=max_speed_kmh,
            max_accuracy_m=max_accuracy_m,
            hass=hass,
        )
        k = pair_key(person_state.entity_id, other_state.entity_id)
        ps = coord._pair_states[k]
        now = datetime.now().astimezone()
        if prev_dist is not None:
            ps.prev_distance_m = prev_dist
            ps.prev_calc_time = now - timedelta(seconds=prev_calc_offset_s or 60)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=5.0,
        ):
            result = coord._calc_pair(ps, person_state.entity_id, other_state.entity_id, now, set())
        return result

    def test_zone_fallback_accuracy_filter_skipped(self):
        # Person at home via scanner. Zone radius=200m > max_accuracy_m=150m.
        # Without the fix: accuracy filter would reject acc=200m.
        person = State("person.alice", "home", {})
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=200)
        other = make_state("person.bob", 51.5, -0.1, accuracy=10)
        result = self._calc_pair_with_zone(person, zone, other, max_accuracy_m=150.0)
        assert result.data_valid is True
        assert result.last_error != "accuracy_filter_a"

    def test_zone_fallback_speed_filter_skipped(self):
        # Person transitions from GPS (500m away) to zone fallback (0m).
        # prev_distance_m=500m, new=5m, delta_s=5s → raw 360 km/h.
        # Speed filter must be skipped because zone_fallback_a=True.
        person = State("person.alice", "home", {})
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        other = make_state("person.bob", 51.5, -0.1, accuracy=10)
        result = self._calc_pair_with_zone(
            person,
            zone,
            other,
            max_speed_kmh=50.0,  # low threshold — would reject raw delta
            prev_dist=500.0,
            prev_calc_offset_s=5,
        )
        assert result.data_valid is True
        assert result.last_error != "speed_filter"

    def test_zone_fallback_nulls_prev_distance_m(self):
        # After zone fallback tick, ps.prev_distance_m must be None so
        # the next GPS tick doesn't compare against the zone centroid.
        person = State("person.alice", "home", {})
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        other = make_state("person.bob", 51.5, -0.1, accuracy=10)
        result = self._calc_pair_with_zone(person, zone, other)
        assert result.prev_distance_m is None

    def test_zone_fallback_does_not_store_radius_as_accuracy(self):
        # ps.accuracy_a must be None after a zone-fallback tick so stale
        # zone radius doesn't inflate noise_budget_m on the next GPS tick.
        # Use radius=200 so the pre-nulling value (200) is distinguishable
        # from an entity that never had accuracy (None).
        # Also assert accuracy_b is preserved — the null must be one-sided.
        person = State("person.alice", "home", {})
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=200)
        other = make_state("person.bob", 51.5, -0.1, accuracy=10)
        result = self._calc_pair_with_zone(person, zone, other)
        assert result.accuracy_a is None  # zone-fallback side: nulled
        assert result.accuracy_b == 10.0  # GPS side: preserved

    def test_zone_fallback_direction_not_computed(self):
        # Direction must be None when zone fallback active (no reliable baseline).
        person = State("person.alice", "home", {})
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        other = make_state("person.bob", 51.5, -0.1, accuracy=10)
        result = self._calc_pair_with_zone(
            person,
            zone,
            other,
            prev_dist=500.0,
            prev_calc_offset_s=60,
        )
        assert result.direction is None
        assert result.closing_speed_kmh is None

    def test_zone_fallback_data_valid(self):
        person = State("person.alice", "home", {})
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        other = make_state("person.bob", 51.5, -0.1, accuracy=10)
        result = self._calc_pair_with_zone(person, zone, other)
        assert result.data_valid is True

    def test_gps_entity_unaffected_by_zone_fallback_changes(self):
        # Entity with GPS coords: zone_fallback=False, behavior identical to before.
        person = make_state("person.alice", 51.5, -0.1, accuracy=20)
        other = make_state("person.bob", 51.6, -0.2, accuracy=20)
        hass = _make_hass(extra={person.entity_id: person, other.entity_id: other})
        coord = _make_coord_coordinator(
            entities=["person.alice", "person.bob"],
            max_accuracy_m=0.0,
            max_speed_kmh=0.0,
            hass=hass,
        )
        k = pair_key("person.alice", "person.bob")
        ps = coord._pair_states[k]
        now = datetime.now().astimezone()
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=200.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", now, set())
        assert result.data_valid is True
        assert result.accuracy_a == 20.0  # GPS accuracy preserved

    def test_require_reliable_skips_zone_fallback_pair(self):
        # require_reliable=True must NOT block proximity for zone-fallback pairs.
        person = State("person.alice", "home", {})
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        other = make_state("person.bob", 51.5, -0.1, accuracy=10)
        hass = _make_hass(
            zone_states=[zone],
            extra={person.entity_id: person, other.entity_id: other},
        )
        coord = _make_coord_coordinator(
            entities=["person.alice", "person.bob"],
            require_reliable=True,
            min_updates_reliable=10,  # unreachable without many GPS updates
            entry_threshold_m=100.0,
            hass=hass,
        )
        k = pair_key("person.alice", "person.bob")
        ps = coord._pair_states[k]
        now = datetime.now().astimezone()
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=5.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", now, set())
        assert result.proximity is True

    def test_both_entities_home_via_scanner_distance_zero(self):
        # Two people both at home via scanner → both use zone.home coords → dist≈0.
        person_a = State("person.alice", "home", {})
        person_b = State("person.bob", "home", {})
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        hass = _make_hass(
            zone_states=[zone],
            extra={person_a.entity_id: person_a, person_b.entity_id: person_b},
        )
        coord = _make_coord_coordinator(
            entities=["person.alice", "person.bob"],
            entry_threshold_m=200.0,
            hass=hass,
        )
        k = pair_key("person.alice", "person.bob")
        ps = coord._pair_states[k]
        now = datetime.now().astimezone()
        # ha_distance with identical coords = 0
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=0.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", now, set())
        assert result.data_valid is True
        assert result.proximity is True


# ---------------------------------------------------------------------------
# Resync silence with zone fallback — per-side staleness
# ---------------------------------------------------------------------------


class TestResyncSilenceZoneFallback:
    """Resync silence must use _is_zone() directly, not the composite flag."""

    def test_stale_gps_partner_triggers_resync_when_one_entity_is_zone_fallback(self):
        # person.alice is home via scanner (zone fallback), person.bob is GPS
        # but silent for > resync_silence_s. Resync must still fire.
        person_a = State("person.alice", "home", {})
        person_b = make_state("person.bob", 51.6, -0.2, accuracy=20)
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        hass = _make_hass(
            zone_states=[zone],
            extra={person_a.entity_id: person_a, person_b.entity_id: person_b},
        )
        coord = _make_coord_coordinator(
            entities=["person.alice", "person.bob"],
            resync_silence_s=600.0,
            resync_hold_s=60.0,
            hass=hass,
        )
        k = pair_key("person.alice", "person.bob")
        ps = coord._pair_states[k]
        now = datetime.now().astimezone()
        # Both last_update times stale (> 600s ago)
        ps.last_update_a = now - timedelta(seconds=700)
        ps.last_update_b = now - timedelta(seconds=700)

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            coord._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert coord._resync_holding[k] is True

    def test_true_zone_entity_still_skips_resync(self):
        # zone.home as entity_b (real zone entity) — resync must not fire
        # when the person side (alice) is fresh.
        person_a = make_state("person.alice", 51.5, -0.1, accuracy=20)
        zone_b = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        hass = _make_hass(
            zone_states=[zone_b],
            extra={person_a.entity_id: person_a, zone_b.entity_id: zone_b},
        )
        coord = _make_coord_coordinator(
            entities=["person.alice", "zone.home"],
            resync_silence_s=600.0,
            resync_hold_s=60.0,
            hass=hass,
        )
        k = pair_key("person.alice", "zone.home")
        ps = coord._pair_states[k]
        now = datetime.now().astimezone()
        # alice is fresh (10s ago), zone has no last_update (never emits state_changed)
        ps.last_update_a = now - timedelta(seconds=10)
        ps.last_update_b = None  # zone entity never updates via state_changed

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            coord._calc_pair(ps, "person.alice", "zone.home", now, set())

        assert coord._resync_holding[k] is False


# ---------------------------------------------------------------------------
# Direction computed for true zone-vs-person pairs
# ---------------------------------------------------------------------------


class TestDirectionZoneVsPerson:
    """Direction/speed/ETA must be computed when one entity is a real zone (not zone_fallback)."""

    def test_true_zone_vs_person_direction_approaching(self):
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        person = make_state("person.bob", 51.6, -0.2, accuracy=10)
        hass = _make_hass(zone_states=[zone], extra={person.entity_id: person})
        coord = _make_coord_coordinator(
            entities=["zone.home", "person.bob"],
            hass=hass,
        )
        k = pair_key("zone.home", "person.bob")
        ps = coord._pair_states[k]
        now = datetime.now().astimezone()
        ps.prev_distance_m = 500.0
        ps.prev_calc_time = now - timedelta(seconds=60)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,  # closer → approaching
        ):
            result = coord._calc_pair(ps, "zone.home", "person.bob", now, set())
        assert result.direction == "approaching"
        assert result.closing_speed_kmh is not None

    def test_true_zone_vs_person_direction_diverging(self):
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        person = make_state("person.bob", 51.6, -0.2, accuracy=10)
        hass = _make_hass(zone_states=[zone], extra={person.entity_id: person})
        coord = _make_coord_coordinator(
            entities=["zone.home", "person.bob"],
            hass=hass,
        )
        k = pair_key("zone.home", "person.bob")
        ps = coord._pair_states[k]
        now = datetime.now().astimezone()
        ps.prev_distance_m = 100.0
        ps.prev_calc_time = now - timedelta(seconds=60)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=1500.0,  # farther → diverging
        ):
            result = coord._calc_pair(ps, "zone.home", "person.bob", now, set())
        assert result.direction == "diverging"

    def test_zone_vs_person_gps_teleport_rejected(self):
        # Person GPS jumps 99.5km in 60s → ~5970 km/h, max=150 → direction must be None
        # prev_distance_m must also be nulled so next tick starts fresh
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        person = make_state("person.bob", 51.6, -0.2, accuracy=10)
        hass = _make_hass(zone_states=[zone], extra={person.entity_id: person})
        coord = _make_coord_coordinator(
            entities=["zone.home", "person.bob"],
            max_speed_kmh=150.0,
            hass=hass,
        )
        k = pair_key("zone.home", "person.bob")
        ps = coord._pair_states[k]
        now = datetime.now().astimezone()
        ps.prev_distance_m = 500.0
        ps.prev_calc_time = now - timedelta(seconds=60)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100000.0,
        ):
            result = coord._calc_pair(ps, "zone.home", "person.bob", now, set())
        assert result.direction is None
        assert result.closing_speed_kmh is None
        assert result.prev_distance_m is None  # baseline nulled so next tick starts fresh

    def test_zone_vs_person_gps_teleport_rejected_when_speed_disabled(self):
        # max_speed_kmh=0 (disabled) must still reject GPS teleport for direction via DEFAULT_MAX_SPEED_KMH
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        person = make_state("person.bob", 51.6, -0.2, accuracy=10)
        hass = _make_hass(zone_states=[zone], extra={person.entity_id: person})
        coord = _make_coord_coordinator(
            entities=["zone.home", "person.bob"],
            max_speed_kmh=0.0,  # speed filter disabled
            hass=hass,
        )
        k = pair_key("zone.home", "person.bob")
        ps = coord._pair_states[k]
        now = datetime.now().astimezone()
        ps.prev_distance_m = 500.0
        ps.prev_calc_time = now - timedelta(seconds=60)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=500000.0,  # ~29970 km/h — well above DEFAULT_MAX_SPEED_KMH=1000
        ):
            result = coord._calc_pair(ps, "zone.home", "person.bob", now, set())
        assert result.direction is None
        assert result.prev_distance_m is None

    def test_zone_vs_person_delta_s_zero_direction_none(self):
        # Same-millisecond double update: delta_s=0 → direction and speed must stay None
        zone = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        person = make_state("person.bob", 51.6, -0.2, accuracy=10)
        hass = _make_hass(zone_states=[zone], extra={person.entity_id: person})
        coord = _make_coord_coordinator(
            entities=["zone.home", "person.bob"],
            hass=hass,
        )
        k = pair_key("zone.home", "person.bob")
        ps = coord._pair_states[k]
        now = datetime.now().astimezone()
        ps.prev_distance_m = 500.0
        ps.prev_calc_time = now  # same instant → delta_s=0
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            result = coord._calc_pair(ps, "zone.home", "person.bob", now, set())
        assert result.direction is None
        assert result.closing_speed_kmh is None


class TestZoneZonePair:
    """Two real zone entities as a pair — fixed points, no GPS noise, no state changes."""

    def _make_zone_zone_coord(self, zone_a, zone_b, prev_dist=None, prev_offset_s=None):
        hass = _make_hass(
            zone_states=[zone_a, zone_b],
            extra={zone_a.entity_id: zone_a, zone_b.entity_id: zone_b},
        )
        coord = _make_coord_coordinator(
            entities=[zone_a.entity_id, zone_b.entity_id],
            max_speed_kmh=150.0,
            resync_silence_s=600.0,
            hass=hass,
        )
        k = pair_key(zone_a.entity_id, zone_b.entity_id)
        ps = coord._pair_states[k]
        now = datetime.now().astimezone()
        if prev_dist is not None:
            ps.prev_distance_m = prev_dist
            ps.prev_calc_time = now - timedelta(seconds=prev_offset_s or 60)
        return coord, k, ps, now

    def test_zone_zone_data_valid(self):
        zone_a = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        zone_b = make_zone_state("zone.work", 51.6, -0.2, radius=50)
        coord, k, ps, now = self._make_zone_zone_coord(zone_a, zone_b)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=10000.0,
        ):
            result = coord._calc_pair(ps, zone_a.entity_id, zone_b.entity_id, now, set())
        assert result.data_valid is True

    def test_zone_zone_direction_stationary_on_first_tick(self):
        # Both sides zone-based → genuinely stationary relative to each other, even
        # with no prior baseline. Reports "stationary" instead of leaving it unknown.
        zone_a = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        zone_b = make_zone_state("zone.work", 51.6, -0.2, radius=50)
        coord, k, ps, now = self._make_zone_zone_coord(zone_a, zone_b)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=10000.0,
        ):
            result = coord._calc_pair(ps, zone_a.entity_id, zone_b.entity_id, now, set())
        assert result.direction == "stationary"
        assert result.closing_speed_kmh == 0.0

    def test_zone_zone_direction_stationary_on_second_tick(self):
        zone_a = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        zone_b = make_zone_state("zone.work", 51.6, -0.2, radius=50)
        coord, k, ps, now = self._make_zone_zone_coord(
            zone_a, zone_b, prev_dist=10000.0, prev_offset_s=60
        )
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=10000.0,
        ):
            result = coord._calc_pair(ps, zone_a.entity_id, zone_b.entity_id, now, set())
        assert result.direction == "stationary"

    def test_zone_zone_speed_filter_skipped(self):
        # Speed filter (line 561) is skipped for zone pairs (is_zone_a=True) — data_valid
        # is not affected by large distance deltas. The patched distance also triggers the
        # direction teleport guard (~36000 km/h > DEFAULT_MAX_SPEED_KMH=1000), so direction
        # stays None and prev_distance_m is nulled. In production zone-zone pairs always
        # return the same distance (fixed points), so the teleport guard never fires there.
        zone_a = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        zone_b = make_zone_state("zone.work", 51.6, -0.2, radius=50)
        coord, k, ps, now = self._make_zone_zone_coord(
            zone_a, zone_b, prev_dist=100.0, prev_offset_s=5
        )
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=50000.0,  # ~36000 km/h — speed filter skipped, direction teleport guard fires
        ):
            result = coord._calc_pair(ps, zone_a.entity_id, zone_b.entity_id, now, set())
        assert result.data_valid is True
        assert result.last_error != "speed_filter"
        assert result.direction is None  # teleport guard fired
        assert result.prev_distance_m is None  # baseline nulled by teleport guard

    def test_zone_zone_resync_hold_not_triggered(self):
        zone_a = make_zone_state("zone.home", 51.5, -0.1, radius=100)
        zone_b = make_zone_state("zone.work", 51.6, -0.2, radius=50)
        coord, k, ps, now = self._make_zone_zone_coord(zone_a, zone_b)
        ps.last_update_a = now - timedelta(seconds=3600)
        ps.last_update_b = now - timedelta(seconds=3600)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=10000.0,
        ):
            coord._calc_pair(ps, zone_a.entity_id, zone_b.entity_id, now, set())
        assert coord._resync_holding[k] is False
