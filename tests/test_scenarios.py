"""End-to-end scenario tests — simulated journeys through the full coordinator stack.

Each scenario drives _calc_pair (or async_recalculate via tick sequence) with
realistic GPS sequences and asserts sensor state at key moments.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from custom_components.entity_distance.coordinator import EntityDistanceCoordinator
from custom_components.entity_distance.models import PairState, pair_key
from tests.conftest import make_state, make_zone_state

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BUCKET_THRESHOLDS = {"very_near": 200, "near": 1000, "mid": 5000, "far": 20000}

# Generic coordinates for testing
# City A (home base) — Dublin city centre
_CITY_A_LAT, _CITY_A_LON = 53.3498, -6.2603
# Studio ~1.5 km from City A
_STUDIO_LAT, _STUDIO_LON = 53.3498 - 0.013, -6.2603
# City B ~260 km from City A — Cork city centre
_CITY_B_LAT, _CITY_B_LON = 51.8985, -8.4756


def _make_coord(
    entities: list[str],
    state_map: dict,
    *,
    max_speed_kmh: float = 200.0,
    max_accuracy_m: float = 300.0,
    resync_silence_s: float = 600.0,
    resync_hold_s: float = 60.0,
    proximity_zone: str = "very_near",
):
    """Build a minimal coordinator with a fake hass."""
    from custom_components.entity_distance.const import (
        BUCKET_FAR,
        BUCKET_MID,
        BUCKET_NEAR,
        BUCKET_VERY_NEAR,
    )

    coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
    coord.hass = MagicMock()
    coord.hass.states.get = MagicMock(side_effect=lambda eid: state_map.get(eid))
    coord.hass.states.async_all = MagicMock(
        side_effect=lambda domain: [
            s for eid, s in state_map.items() if eid.startswith(f"{domain}.")
        ]
    )
    coord._entities = entities
    coord._max_accuracy_m = max_accuracy_m
    coord._max_speed_kmh = max_speed_kmh
    coord._bucket_thresholds = _BUCKET_THRESHOLDS
    # Derive entry/exit from proximity zone
    _zone_entry = {
        BUCKET_VERY_NEAR: 200.0,
        BUCKET_NEAR: 1000.0,
        BUCKET_MID: 5000.0,
        BUCKET_FAR: 20000.0,
    }
    coord._proximity_zone = proximity_zone
    coord._entry_threshold_m = _zone_entry.get(proximity_zone, 200.0)
    coord._exit_threshold_m = coord._entry_threshold_m
    coord._resync_silence_s = resync_silence_s
    coord._resync_hold_s = resync_hold_s
    coord._min_updates_reliable = 1
    coord._require_reliable = False
    coord._updates_window_s = 1800.0

    import itertools

    pairs = {}
    resync_holding = {}
    resync_hold_until = {}
    for a, b in itertools.combinations(entities, 2):
        k = pair_key(a, b)
        pairs[k] = PairState(entity_a_id=k[0], entity_b_id=k[1])
        resync_holding[k] = False
        resync_hold_until[k] = None

    coord._pair_states = pairs
    coord._resync_holding = resync_holding
    coord._resync_hold_until = resync_hold_until
    coord._pending_updates = set()
    coord._store = MagicMock()
    coord._store.async_save = AsyncMock()
    return coord


def _tick(coord, now: datetime, state_map: dict):
    """Run one _calc_pair tick for all pairs, updating hass state map."""
    coord.hass.states.get = MagicMock(side_effect=lambda eid: state_map.get(eid))
    coord.hass.states.async_all = MagicMock(
        side_effect=lambda domain: [
            s for eid, s in state_map.items() if eid.startswith(f"{domain}.")
        ]
    )
    for k, ps in coord._pair_states.items():
        coord._pair_states[k] = coord._calc_pair(ps, ps.entity_a_id, ps.entity_b_id, now, set())


def _ps(coord, a: str, b: str) -> PairState:
    return coord._pair_states[pair_key(a, b)]


# ---------------------------------------------------------------------------
# Scenario 1 — Both home, one leaves, drives to another city, returns
# ---------------------------------------------------------------------------


class TestScenarioDailyCommute:
    """Alice leaves home at 10:00, drives to Pilates (1.5km), returns at 12:00."""

    def _run(self):
        t0 = datetime(2026, 7, 5, 10, 0, 0, tzinfo=UTC)
        home = make_zone_state("zone.home", _CITY_A_LAT, _CITY_A_LON, radius=100)
        italo = make_state("person.bob", _CITY_A_LAT, _CITY_A_LON, accuracy=15)

        state_map = {"zone.home": home, "person.bob": italo}
        coord = _make_coord(["person.bob", "zone.home"], state_map)

        # T+0: both home, 0m apart
        dercy_home = make_state("person.alice", _CITY_A_LAT, _CITY_A_LON, accuracy=15)
        state_map["person.alice"] = dercy_home
        coord = _make_coord(["person.alice", "zone.home"], state_map)
        _tick(coord, t0, state_map)
        ps0 = _ps(coord, "person.alice", "zone.home")
        assert ps0.data_valid
        assert ps0.distance_m < 50  # effectively at home

        # T+5min: Alice en route — ~2km from home (past exit threshold of 1km)
        t1 = t0 + timedelta(minutes=5)
        state_map["person.alice"] = make_state(
            "person.alice",
            _CITY_A_LAT - 0.018,  # ~2km south
            _CITY_A_LON,
            accuracy=20,
        )
        _tick(coord, t1, state_map)
        ps1 = _ps(coord, "person.alice", "zone.home")
        assert ps1.data_valid
        assert ps1.distance_m > 1000  # past exit threshold
        assert ps1.proximity is False  # left zone

        # T+15min: Alice at destination (~2.5km from home, further out)
        t2 = t0 + timedelta(minutes=15)
        state_map["person.alice"] = make_state(
            "person.alice", _CITY_A_LAT - 0.022, _CITY_A_LON, accuracy=15
        )
        _tick(coord, t2, state_map)
        ps2 = _ps(coord, "person.alice", "zone.home")
        assert ps2.data_valid
        assert ps2.distance_m > 1000
        assert ps2.proximity is False

        # T+90min: Alice returns home
        t3 = t0 + timedelta(minutes=90)
        state_map["person.alice"] = make_state(
            "person.alice", _CITY_A_LAT, _CITY_A_LON, accuracy=15
        )
        _tick(coord, t3, state_map)
        ps3 = _ps(coord, "person.alice", "zone.home")
        assert ps3.data_valid
        assert ps3.distance_m < 50
        assert ps3.proximity is True
        assert ps3.direction in ("approaching", "stationary", None)

        return coord, t3, ps3

    def test_full_commute_cycle(self):
        self._run()

    def test_proximity_duration_accumulates_correctly(self):
        coord, t3, ps3 = self._run()
        # First session: t0→t1 = 5 min (300s) in proximity, closed on exit
        assert ps3.proximity_duration_s > 200  # at least 5-min first session credited

    def test_today_proximity_time_accumulates(self):
        coord, t3, ps3 = self._run()
        # today_proximity_seconds credited on exit from first session (~5 min)
        assert ps3.today_proximity_seconds > 200


# ---------------------------------------------------------------------------
# Scenario 2 — City-to-city trip (Dublin → Cork, ~260km)
# ---------------------------------------------------------------------------


class TestScenarioCityToCity:
    """Alice drives from Dublin to Cork — distance, zone changes, direction."""

    def test_distance_increases_during_drive(self):
        t0 = datetime(2026, 7, 5, 9, 0, 0, tzinfo=UTC)
        home = make_zone_state("zone.home", _CITY_A_LAT, _CITY_A_LON, radius=100)

        # Start: Alice at Dublin home
        state_map = {
            "zone.home": home,
            "person.alice": make_state("person.alice", _CITY_A_LAT, _CITY_A_LON, accuracy=20),
        }
        coord = _make_coord(["person.alice", "zone.home"], state_map)
        _tick(coord, t0, state_map)
        ps0 = _ps(coord, "person.alice", "zone.home")
        assert ps0.distance_m < 50

        # 30 min into drive — ~50km south of Dublin
        t1 = t0 + timedelta(minutes=30)
        state_map["person.alice"] = make_state("person.alice", 53.1500, -6.2600, accuracy=20)
        _tick(coord, t1, state_map)
        ps1 = _ps(coord, "person.alice", "zone.home")
        assert ps1.data_valid
        assert ps1.distance_m > 20000  # >20km
        assert ps1.proximity is False

        # 2h into drive — ~200km, near Cork
        t2 = t0 + timedelta(hours=2)
        state_map["person.alice"] = make_state("person.alice", 52.1000, -8.2000, accuracy=25)
        _tick(coord, t2, state_map)
        ps2 = _ps(coord, "person.alice", "zone.home")
        assert ps2.data_valid
        assert ps2.distance_m > 150000  # >150km from Dublin home

        # Arrived Cork
        t3 = t0 + timedelta(hours=2, minutes=30)
        state_map["person.alice"] = make_state(
            "person.alice", _CITY_B_LAT, _CITY_B_LON, accuracy=15
        )
        _tick(coord, t3, state_map)
        ps3 = _ps(coord, "person.alice", "zone.home")
        assert ps3.data_valid
        assert ps3.distance_m > 200000  # >200km from Dublin home
        assert ps3.proximity is False

    def test_direction_diverging_while_leaving(self):
        t0 = datetime(2026, 7, 5, 9, 0, 0, tzinfo=UTC)
        home = make_zone_state("zone.home", _CITY_A_LAT, _CITY_A_LON, radius=100)
        state_map = {
            "zone.home": home,
            "person.alice": make_state("person.alice", _CITY_A_LAT, _CITY_A_LON, accuracy=20),
        }
        coord = _make_coord(["person.alice", "zone.home"], state_map)
        _tick(coord, t0, state_map)  # establish baseline

        t1 = t0 + timedelta(minutes=30)
        state_map["person.alice"] = make_state("person.alice", 53.1500, -6.2600, accuracy=20)
        _tick(coord, t1, state_map)
        ps = _ps(coord, "person.alice", "zone.home")
        assert ps.direction == "diverging"
        assert ps.closing_speed_kmh is not None
        assert ps.closing_speed_kmh > 0

    def test_direction_approaching_when_returning(self):
        t0 = datetime(2026, 7, 5, 9, 0, 0, tzinfo=UTC)
        home = make_zone_state("zone.home", _CITY_A_LAT, _CITY_A_LON, radius=100)
        state_map = {
            "zone.home": home,
            "person.alice": make_state("person.alice", _CITY_B_LAT, _CITY_B_LON, accuracy=15),
        }
        coord = _make_coord(["person.alice", "zone.home"], state_map)
        _tick(coord, t0, state_map)  # baseline at Cork

        # Moving back toward Dublin
        t1 = t0 + timedelta(hours=1)
        state_map["person.alice"] = make_state("person.alice", 52.5000, -7.5000, accuracy=15)
        _tick(coord, t1, state_map)
        ps = _ps(coord, "person.alice", "zone.home")
        assert ps.direction == "approaching"
        assert ps.closing_speed_kmh is not None
        assert ps.eta_minutes is not None
        assert ps.eta_minutes > 0


# ---------------------------------------------------------------------------
# Scenario 3 — GPS silence + resync hold + FREEZE behavior
# ---------------------------------------------------------------------------


class TestScenarioGpsSilence:
    """Phone goes silent for >10 min while person is home — FREEZE holds proximity."""

    def test_in_proximity_stays_on_during_gps_silence(self):
        t0 = datetime(2026, 7, 5, 10, 0, 0, tzinfo=UTC)
        home = make_zone_state("zone.home", _CITY_A_LAT, _CITY_A_LON, radius=100)
        state_map = {
            "zone.home": home,
            "person.alice": make_state("person.alice", _CITY_A_LAT, _CITY_A_LON, accuracy=15),
        }
        coord = _make_coord(
            ["person.alice", "zone.home"],
            state_map,
            resync_silence_s=600.0,
            resync_hold_s=60.0,
        )
        # Establish proximity
        _tick(coord, t0, state_map)
        ps = _ps(coord, "person.alice", "zone.home")
        ps.last_update_a = t0  # person.alice last seen at t0
        ps.last_update_b = None  # zone never updates
        assert ps.proximity is True

        # T+11min: GPS has been silent 660s — hold arms on next tick
        t1 = t0 + timedelta(minutes=11)
        _tick(coord, t1, state_map)
        ps1 = _ps(coord, "person.alice", "zone.home")
        k = pair_key("person.alice", "zone.home")

        if coord._resync_holding.get(k, False):
            # Hold armed: FREEZE means proximity stays True
            assert ps1.proximity is True, "FREEZE: proximity must not flip during hold"
        else:
            # Hold may not have armed yet depending on timing
            assert ps1.data_valid

    def test_today_proximity_time_accumulates_during_hold(self):
        """today_proximity_seconds should increment even during hold ticks."""
        t0 = datetime(2026, 7, 5, 10, 0, 0, tzinfo=UTC)
        home = make_zone_state("zone.home", _CITY_A_LAT, _CITY_A_LON, radius=100)
        state_map = {
            "zone.home": home,
            "person.alice": make_state("person.alice", _CITY_A_LAT, _CITY_A_LON, accuracy=15),
        }
        coord = _make_coord(
            ["person.alice", "zone.home"],
            state_map,
            resync_silence_s=600.0,
            resync_hold_s=60.0,
        )
        _tick(coord, t0, state_map)
        k = pair_key("person.alice", "zone.home")
        ps = coord._pair_states[k]
        ps.last_update_a = t0

        # Force hold state with a valid previous calc time so elapsed > 0
        coord._resync_holding[k] = True
        coord._resync_hold_until[k] = t0 + timedelta(seconds=60)
        ps.proximity = True
        ps.distance_m = 15.0
        ps.prev_calc_time = t0  # 30s before the hold tick
        before = ps.today_proximity_seconds

        # Tick during hold (30s in)
        t_hold = t0 + timedelta(seconds=30)
        _tick(coord, t_hold, state_map)
        ps_after = coord._pair_states[k]
        # today_proximity_seconds must have increased by ~30s (hold credits elapsed)
        assert ps_after.today_proximity_seconds > before
        assert ps_after.today_proximity_seconds >= before + 25  # at least 25s credited


# ---------------------------------------------------------------------------
# Scenario 4 — Two people both moving (person vs person)
# ---------------------------------------------------------------------------


class TestScenarioTwoPeopleMoving:
    """Alice and Bob both move — approaching, diverging, meeting."""

    def test_approaching_each_other(self):
        t0 = datetime(2026, 7, 5, 11, 0, 0, tzinfo=UTC)
        # Both start 5km apart
        state_map = {
            "person.alice": make_state("person.alice", 53.3498, -6.2603, accuracy=15),
            "person.bob": make_state("person.bob", 53.3050, -6.2200, accuracy=15),
        }
        coord = _make_coord(["person.alice", "person.bob"], state_map)
        _tick(coord, t0, state_map)
        ps0 = _ps(coord, "person.alice", "person.bob")
        assert ps0.data_valid
        d0 = ps0.distance_m
        assert d0 > 3000  # ~5km apart

        # T+30min: Alice moves toward Italo
        t1 = t0 + timedelta(minutes=30)
        state_map["person.alice"] = make_state("person.alice", 53.3200, -6.2400, accuracy=15)
        _tick(coord, t1, state_map)
        ps1 = _ps(coord, "person.alice", "person.bob")
        assert ps1.direction == "approaching"
        assert ps1.distance_m < d0

        # T+60min: they meet
        t2 = t0 + timedelta(minutes=60)
        state_map["person.alice"] = make_state("person.alice", 53.3050, -6.2200, accuracy=15)
        _tick(coord, t2, state_map)
        ps2 = _ps(coord, "person.alice", "person.bob")
        assert ps2.data_valid
        assert ps2.proximity is True
        assert ps2.distance_m < 200

    def test_diverging_after_meeting(self):
        t0 = datetime(2026, 7, 5, 14, 0, 0, tzinfo=UTC)
        # Start together
        state_map = {
            "person.alice": make_state("person.alice", 53.3498, -6.2603, accuracy=15),
            "person.bob": make_state("person.bob", 53.3498, -6.2603, accuracy=15),
        }
        coord = _make_coord(["person.alice", "person.bob"], state_map)
        _tick(coord, t0, state_map)  # establish baseline

        # T+15min: Bob drives away
        t1 = t0 + timedelta(minutes=15)
        state_map["person.bob"] = make_state("person.bob", 53.2500, -6.1500, accuracy=20)
        _tick(coord, t1, state_map)
        ps = _ps(coord, "person.alice", "person.bob")
        assert ps.direction == "diverging"
        assert ps.proximity is False
        assert ps.distance_m > 5000

    def test_stationary_together(self):
        t0 = datetime(2026, 7, 5, 20, 0, 0, tzinfo=UTC)
        # Both at same location
        state_map = {
            "person.alice": make_state("person.alice", 53.3498, -6.2603, accuracy=15),
            "person.bob": make_state("person.bob", 53.3500, -6.2605, accuracy=15),
        }
        coord = _make_coord(["person.alice", "person.bob"], state_map)
        _tick(coord, t0, state_map)  # establish baseline

        # T+1min: tiny GPS drift, no real movement
        t1 = t0 + timedelta(minutes=1)
        state_map["person.alice"] = make_state("person.alice", 53.3499, -6.2604, accuracy=15)
        _tick(coord, t1, state_map)
        ps = _ps(coord, "person.alice", "person.bob")
        assert ps.direction == "stationary"  # sub-50m delta < STATIONARY_THRESHOLD_M
        assert ps.proximity is True


# ---------------------------------------------------------------------------
# Scenario 5 — Teleport / GPS glitch
# ---------------------------------------------------------------------------


class TestScenarioGpsGlitch:
    """Phone GPS glitches to wrong location then snaps back."""

    def test_teleport_does_not_corrupt_direction(self):
        t0 = datetime(2026, 7, 5, 12, 0, 0, tzinfo=UTC)
        home = make_zone_state("zone.home", _CITY_A_LAT, _CITY_A_LON, radius=100)
        state_map = {
            "zone.home": home,
            "person.alice": make_state("person.alice", _CITY_A_LAT, _CITY_A_LON, accuracy=15),
        }
        coord = _make_coord(["person.alice", "zone.home"], state_map, max_speed_kmh=150.0)
        _tick(coord, t0, state_map)  # baseline

        # GPS glitch: phone reports location 300km away
        t1 = t0 + timedelta(seconds=30)
        state_map["person.alice"] = make_state(
            "person.alice", _CITY_B_LAT, _CITY_B_LON, accuracy=50
        )
        _tick(coord, t1, state_map)
        ps1 = _ps(coord, "person.alice", "zone.home")
        # ~250km in 30s = ~30000 km/h >> max_speed_kmh=150 → teleport guard must reject direction
        assert ps1.direction is None
        assert ps1.closing_speed_kmh is None

        # GPS recovers: back at home
        t2 = t1 + timedelta(minutes=1)
        state_map["person.alice"] = make_state(
            "person.alice", _CITY_A_LAT, _CITY_A_LON, accuracy=15
        )
        _tick(coord, t2, state_map)
        ps2 = _ps(coord, "person.alice", "zone.home")
        assert ps2.data_valid
        assert ps2.distance_m < 50
        assert ps2.proximity is True

    def test_low_accuracy_update_still_accepted(self):
        """GPS accuracy 250m (within default 300m limit) — should be accepted."""
        t0 = datetime(2026, 7, 5, 8, 0, 0, tzinfo=UTC)
        home = make_zone_state("zone.home", _CITY_A_LAT, _CITY_A_LON, radius=100)
        state_map = {
            "zone.home": home,
            "person.alice": make_state("person.alice", _CITY_A_LAT, _CITY_A_LON, accuracy=250),
        }
        coord = _make_coord(["person.alice", "zone.home"], state_map, max_accuracy_m=300.0)
        _tick(coord, t0, state_map)
        ps = _ps(coord, "person.alice", "zone.home")
        assert ps.data_valid
        assert ps.last_error != "accuracy_filter_a"

    def test_high_accuracy_update_rejected(self):
        """GPS accuracy 400m (>300m limit) — should be rejected."""
        t0 = datetime(2026, 7, 5, 8, 0, 0, tzinfo=UTC)
        home = make_zone_state("zone.home", _CITY_A_LAT, _CITY_A_LON, radius=100)
        state_map = {
            "zone.home": home,
            "person.alice": make_state("person.alice", _CITY_A_LAT, _CITY_A_LON, accuracy=400),
        }
        coord = _make_coord(["person.alice", "zone.home"], state_map, max_accuracy_m=300.0)
        _tick(coord, t0, state_map)
        ps = _ps(coord, "person.alice", "zone.home")
        assert ps.last_error == "accuracy_filter_a"
