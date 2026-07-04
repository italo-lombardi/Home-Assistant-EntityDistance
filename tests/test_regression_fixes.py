"""Regression tests for bugs fixed in 0.2.5.

Covers:
- C1  async_migrate_entry v1→v2 (missing migration restored)
- C2  proximity_duration_s gap credited on HA restart
- C3  cross-midnight today_proximity_seconds flush
- W3  _CARD_INSTALLED_KEY cleared on last-entry unload
- W4  AnyInProximity / AllInProximity return None when all pairs invalid
- W5  today_proximity_seconds only accumulates after reliability check
- W6  last_seen_together stamped on was_proximity (in-prox ticks + EXIT)
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.entity_distance.binary_sensor import (
    AllInProximityBinarySensor,
    AnyInProximityBinarySensor,
)
from custom_components.entity_distance.const import CONF_ENTITIES, DOMAIN
from custom_components.entity_distance.models import GroupData, PairState, pair_key

# ---------------------------------------------------------------------------
# Shared helpers (mirror test_group_tracking.py conventions)
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
_BUCKET_THRESHOLDS = {"very_near": 100, "near": 500, "mid": 2000, "far": 10000}


def _make_coordinator(
    entry_threshold_m: float = 500.0,
    exit_threshold_m: float = 700.0,
    require_reliable: bool = False,
    min_updates_reliable: int = 3,
    max_speed_kmh: float = 1000.0,
    max_accuracy_m: float = 200.0,
):
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
    coord._resync_silence_s = 0
    coord._resync_hold_s = 60
    coord._resync_holding = {}
    coord._resync_hold_until = {}
    coord._min_updates_reliable = min_updates_reliable
    coord._require_reliable = require_reliable
    return coord


def _make_state(entity_id: str, lat: float, lon: float, accuracy: float | None = None):
    from homeassistant.core import State

    attrs: dict = {"latitude": lat, "longitude": lon}
    if accuracy is not None:
        attrs["gps_accuracy"] = accuracy
    return State(entity_id, "home", attrs)


def _fresh_pair() -> PairState:
    k = pair_key("person.alice", "person.bob")
    return PairState(entity_a_id=k[0], entity_b_id=k[1])


def _make_group_sensor(sensor_cls, group_data: GroupData):
    coordinator = MagicMock()
    coordinator.data = group_data
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = sensor_cls.__new__(sensor_cls)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._attr_unique_id = "test_sensor"
    sensor._attr_device_info = {}
    return sensor


# ---------------------------------------------------------------------------
# C1 — async_migrate_entry
# ---------------------------------------------------------------------------


class TestAsyncMigrateEntry:
    @pytest.mark.asyncio
    async def test_version2_entry_skipped(self):
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        entry = MagicMock()
        entry.version = 2
        result = await async_migrate_entry(hass, entry)
        assert result is True

    @pytest.mark.asyncio
    async def test_v1_with_entity_a_b_migrates_to_entities_list(self):
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = MagicMock()
        entry.version = 1
        entry.entry_id = "abc123"
        entry.data = {"entity_a": "person.alice", "entity_b": "person.bob"}

        with patch(
            "custom_components.entity_distance.er.async_migrate_entries",
            new=AsyncMock(),
        ):
            result = await async_migrate_entry(hass, entry)

        assert result is True
        hass.config_entries.async_update_entry.assert_called_once()
        call_kwargs = hass.config_entries.async_update_entry.call_args[1]
        assert CONF_ENTITIES in call_kwargs["data"]
        assert set(call_kwargs["data"][CONF_ENTITIES]) == {"person.alice", "person.bob"}
        assert call_kwargs["version"] == 2

    @pytest.mark.asyncio
    async def test_v1_with_entities_already_present_migrates_without_overwrite(self):
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        hass.config_entries = MagicMock()
        entry = MagicMock()
        entry.version = 1
        entry.entry_id = "abc123"
        entry.data = {CONF_ENTITIES: ["person.alice", "person.bob"]}

        with patch(
            "custom_components.entity_distance.er.async_migrate_entries",
            new=AsyncMock(),
        ):
            result = await async_migrate_entry(hass, entry)

        assert result is True
        call_kwargs = hass.config_entries.async_update_entry.call_args[1]
        assert call_kwargs["data"][CONF_ENTITIES] == ["person.alice", "person.bob"]

    @pytest.mark.asyncio
    async def test_v1_without_any_entity_data_returns_false(self):
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        entry = MagicMock()
        entry.version = 1
        entry.entry_id = "abc123"
        entry.data = {}

        result = await async_migrate_entry(hass, entry)
        assert result is False

    @pytest.mark.asyncio
    async def test_unique_id_migration_renames_old_format(self):
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        hass.config_entries = MagicMock()
        captured_fn = {}

        async def _capture_migrate(h, entry_id, fn):
            captured_fn["fn"] = fn

        entry = MagicMock()
        entry.version = 1
        entry.entry_id = "ENTRY1"
        entry.data = {"entity_a": "person.alice", "entity_b": "person.bob"}

        with patch(
            "custom_components.entity_distance.er.async_migrate_entries",
            side_effect=_capture_migrate,
        ):
            await async_migrate_entry(hass, entry)

        fn = captured_fn["fn"]

        # Old-format uid: "ENTRY1_distance"
        old_entity = MagicMock()
        old_entity.unique_id = "ENTRY1_distance"
        result = fn(old_entity)
        assert result is not None
        assert "person.alice__person.bob_distance" in result["new_unique_id"]

    @pytest.mark.asyncio
    async def test_unique_id_migration_skips_already_migrated(self):
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        hass.config_entries = MagicMock()
        captured_fn = {}

        async def _capture_migrate(h, entry_id, fn):
            captured_fn["fn"] = fn

        entry = MagicMock()
        entry.version = 1
        entry.entry_id = "ENTRY1"
        entry.data = {"entity_a": "person.alice", "entity_b": "person.bob"}

        with patch(
            "custom_components.entity_distance.er.async_migrate_entries",
            side_effect=_capture_migrate,
        ):
            await async_migrate_entry(hass, entry)

        fn = captured_fn["fn"]

        # Already-migrated uid contains __ with a domain
        already = MagicMock()
        already.unique_id = "ENTRY1_person.alice__person.bob_distance"
        assert fn(already) is None

    @pytest.mark.asyncio
    async def test_unique_id_migration_skips_unrelated_entries(self):
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        hass.config_entries = MagicMock()
        captured_fn = {}

        async def _capture_migrate(h, entry_id, fn):
            captured_fn["fn"] = fn

        entry = MagicMock()
        entry.version = 1
        entry.entry_id = "ENTRY1"
        entry.data = {"entity_a": "person.alice", "entity_b": "person.bob"}

        with patch(
            "custom_components.entity_distance.er.async_migrate_entries",
            side_effect=_capture_migrate,
        ):
            await async_migrate_entry(hass, entry)

        fn = captured_fn["fn"]

        other = MagicMock()
        other.unique_id = "OTHER_ENTRY_distance"
        assert fn(other) is None


# ---------------------------------------------------------------------------
# C2 — proximity_duration_s gap on restart
# ---------------------------------------------------------------------------


class TestProximityRestartGap:
    @pytest.mark.asyncio
    async def test_proximity_since_credits_elapsed_on_load(self):
        """On restore, elapsed time since proximity_since is added to proximity_duration_s."""
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coord._pair_states = {
            pair_key("person.alice", "person.bob"): _fresh_pair(),
        }

        two_hours_ago = datetime.now(UTC) - timedelta(hours=2)
        stored = {
            "person.alice__person.bob": {
                "today_reset_date": datetime.now(UTC).date().isoformat(),
                "today_proximity_seconds": 0.0,
                "today_zone_seconds": {},
                "proximity_duration_s": 100.0,
                "proximity_tracking_started": two_hours_ago.isoformat(),
                "last_seen_together": None,
                "proximity_since": two_hours_ago.isoformat(),
            }
        }

        store_mock = AsyncMock()
        store_mock.async_load = AsyncMock(return_value=stored)
        coord._store = store_mock

        await coord._async_load_state()

        ps = coord._pair_states[pair_key("person.alice", "person.bob")]
        assert ps.proximity is True
        # Base was 100s, plus ~7200s elapsed — must be substantially more than 100
        assert ps.proximity_duration_s > 7000
        assert ps.proximity_duration_s < 100 + 7200 + 60  # allow 60s clock slack

    @pytest.mark.asyncio
    async def test_no_proximity_since_does_not_add_gap(self):
        """When proximity_since is absent, proximity_duration_s unchanged."""
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coord._pair_states = {
            pair_key("person.alice", "person.bob"): _fresh_pair(),
        }

        stored = {
            "person.alice__person.bob": {
                "today_reset_date": datetime.now(UTC).date().isoformat(),
                "today_proximity_seconds": 0.0,
                "today_zone_seconds": {},
                "proximity_duration_s": 300.0,
                "proximity_tracking_started": None,
                "last_seen_together": None,
                "proximity_since": None,
            }
        }

        store_mock = AsyncMock()
        store_mock.async_load = AsyncMock(return_value=stored)
        coord._store = store_mock

        await coord._async_load_state()

        ps = coord._pair_states[pair_key("person.alice", "person.bob")]
        assert ps.proximity is False
        assert ps.proximity_duration_s == 300.0


# ---------------------------------------------------------------------------
# C3 — cross-midnight today_proximity_seconds flush
# ---------------------------------------------------------------------------


class TestCrossMidnightFlush:
    def test_proximity_time_flushed_before_midnight_reset(self):
        """When date rolls over while in proximity, pre-midnight slice goes to proximity_duration_s."""
        coord = _make_coordinator(entry_threshold_m=500.0, exit_threshold_m=700.0)
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 22, 0, 0, tzinfo=UTC)
        # prev_calc_time 30 min before midnight on June 1
        ps.prev_calc_time = datetime(2024, 6, 1, 23, 30, 0, tzinfo=UTC)
        ps.today_reset_date = date(2024, 6, 1)
        ps.today_proximity_seconds = 0.0
        ps.proximity_duration_s = 0.0

        # now = 00:10 on June 2 — crosses midnight
        now = datetime(2024, 6, 2, 0, 10, 0, tzinfo=UTC)

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", now, set())

        # today_proximity_seconds must have been reset (new day)
        assert result.today_reset_date == date(2024, 6, 2)
        # The new day's today_proximity_seconds is only the 10 min after midnight
        assert result.today_proximity_seconds == pytest.approx(600.0, abs=2.0)
        # The 2h pre-midnight slice (proximity_since=22:00 → midnight) credited to lifetime
        assert result.proximity_duration_s == pytest.approx(7200.0, abs=2.0)

    def test_zone_seconds_also_flushed_before_midnight_reset(self):
        """today_zone_seconds flush before midnight also records zone bucket."""
        coord = _make_coordinator()
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = False
        ps.prev_calc_time = datetime(2024, 6, 1, 23, 45, 0, tzinfo=UTC)
        ps.today_reset_date = date(2024, 6, 1)
        ps.today_zone_seconds = {}

        now = datetime(2024, 6, 2, 0, 5, 0, tzinfo=UTC)

        # dist_m = 300 → "near" bucket (100 < 300 <= 500)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=300.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert result.today_reset_date == date(2024, 6, 2)
        # Only post-midnight (5 min) goes to today's bucket — pre-midnight is yesterday's data
        assert result.today_zone_seconds.get("near", 0.0) == pytest.approx(300.0, abs=2.0)

    def test_no_flush_when_prev_calc_time_is_none(self):
        """When prev_calc_time is None there is nothing to flush — no error."""
        coord = _make_coordinator()
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.prev_calc_time = None
        ps.today_reset_date = date(2024, 6, 1)

        now = datetime(2024, 6, 2, 0, 10, 0, tzinfo=UTC)

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=300.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert result.today_reset_date == date(2024, 6, 2)
        assert result.today_proximity_seconds == 0.0


# ---------------------------------------------------------------------------
# W3 — _CARD_INSTALLED_KEY cleared on last-entry unload
# ---------------------------------------------------------------------------


class TestCardInstalledKeyUnload:
    @pytest.mark.asyncio
    async def test_card_flag_cleared_when_last_entry_unloads(self):
        from custom_components.entity_distance import (
            _CARD_INSTALLED_KEY,
            async_unload_entry,
        )

        coordinator = MagicMock()
        coordinator.async_unload = MagicMock()

        hass = MagicMock()
        hass.data = {
            DOMAIN: {
                "only_entry": coordinator,
                _CARD_INSTALLED_KEY: True,
            }
        }

        entry = MagicMock()
        entry.entry_id = "only_entry"
        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        await async_unload_entry(hass, entry)

        assert _CARD_INSTALLED_KEY not in hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_card_flag_preserved_when_other_entries_remain(self):
        from custom_components.entity_distance import (
            _CARD_INSTALLED_KEY,
            async_unload_entry,
        )

        coordinator = MagicMock()
        coordinator.async_unload = MagicMock()
        other_coordinator = MagicMock()

        hass = MagicMock()
        hass.data = {
            DOMAIN: {
                "entry_a": coordinator,
                "entry_b": other_coordinator,
                _CARD_INSTALLED_KEY: True,
            }
        }

        entry = MagicMock()
        entry.entry_id = "entry_a"
        hass.config_entries = MagicMock()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

        await async_unload_entry(hass, entry)

        assert hass.data[DOMAIN][_CARD_INSTALLED_KEY] is True


# ---------------------------------------------------------------------------
# W4 — AnyInProximity / AllInProximity return None when all pairs invalid
# ---------------------------------------------------------------------------


class TestGroupBinarySensorUnavailable:
    def _make_group_data_all_invalid(self, entities: list[str]) -> GroupData:
        import itertools

        pairs = {}
        for a, b in itertools.combinations(entities, 2):
            k = pair_key(a, b)
            ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
            ps.data_valid = False
            pairs[k] = ps
        return GroupData(pairs=pairs, any_in_proximity=False, all_in_proximity=False)

    def test_any_in_proximity_returns_none_when_all_invalid(self):
        gd = self._make_group_data_all_invalid(["person.alice", "person.bob", "person.carol"])
        sensor = _make_group_sensor(AnyInProximityBinarySensor, gd)
        assert sensor.is_on is None

    def test_all_in_proximity_returns_none_when_all_invalid(self):
        gd = self._make_group_data_all_invalid(["person.alice", "person.bob", "person.carol"])
        sensor = _make_group_sensor(AllInProximityBinarySensor, gd)
        assert sensor.is_on is None

    def test_any_in_proximity_returns_false_when_valid_none_proximate(self):
        import itertools

        pairs = {}
        for a, b in itertools.combinations(["person.alice", "person.bob", "person.carol"], 2):
            k = pair_key(a, b)
            ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
            ps.data_valid = True
            ps.proximity = False
            pairs[k] = ps
        gd = GroupData(pairs=pairs, any_in_proximity=False, all_in_proximity=False)
        sensor = _make_group_sensor(AnyInProximityBinarySensor, gd)
        assert sensor.is_on is False

    def test_all_in_proximity_returns_true_when_all_valid_and_proximate(self):
        import itertools

        pairs = {}
        for a, b in itertools.combinations(["person.alice", "person.bob", "person.carol"], 2):
            k = pair_key(a, b)
            ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
            ps.data_valid = True
            ps.proximity = True
            pairs[k] = ps
        gd = GroupData(pairs=pairs, any_in_proximity=True, all_in_proximity=True)
        sensor = _make_group_sensor(AllInProximityBinarySensor, gd)
        assert sensor.is_on is True

    def test_any_returns_none_single_pair_invalid(self):
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = False
        gd = GroupData(pairs={k: ps}, any_in_proximity=False, all_in_proximity=False)
        sensor = _make_group_sensor(AnyInProximityBinarySensor, gd)
        assert sensor.is_on is None


# ---------------------------------------------------------------------------
# W5 — today_proximity_seconds only accumulates after reliability check
# ---------------------------------------------------------------------------


class TestTodayProximityAfterReliabilityCheck:
    def test_duration_not_accumulated_when_reliability_blocks_entry(self):
        """When require_reliable blocks proximity entry, today_proximity_seconds must not grow."""
        coord = _make_coordinator(
            entry_threshold_m=500.0,
            exit_threshold_m=700.0,
            require_reliable=True,
            min_updates_reliable=5,
        )
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = False
        ps.prev_calc_time = datetime(2024, 6, 1, 11, 55, 0, tzinfo=UTC)  # 5 min ago
        ps.today_reset_date = _NOW.date()
        ps.today_proximity_seconds = 0.0
        # update_count_a/b = 0 → not reliable (need >= 5)

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        # Reliability check blocked proximity entry
        assert result.proximity is False
        # today_proximity_seconds must be 0 since proximity was rejected
        assert result.today_proximity_seconds == 0.0

    def test_duration_accumulates_when_already_in_proximity(self):
        """In-proximity ticks always accumulate even with require_reliable."""
        coord = _make_coordinator(
            entry_threshold_m=500.0,
            exit_threshold_m=700.0,
            require_reliable=True,
            min_updates_reliable=1,
        )
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = True  # already in proximity
        ps.proximity_since = datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC)
        ps.prev_calc_time = datetime(2024, 6, 1, 11, 55, 0, tzinfo=UTC)
        ps.today_reset_date = _NOW.date()
        ps.today_proximity_seconds = 3300.0  # 55 min
        # update_count_a/b = 5 → reliable
        ps.update_count_a = 5
        ps.update_count_b = 5

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.proximity is True
        # Should have added ~300s (5 min elapsed)
        assert result.today_proximity_seconds == pytest.approx(3600.0, abs=2.0)


# ---------------------------------------------------------------------------
# W6 — last_seen_together stamped on was_proximity ticks
# ---------------------------------------------------------------------------


class TestLastSeenTogetherSemantics:
    def test_stamped_on_exit_tick(self):
        """EXIT tick: was_proximity=True → last_seen_together = now."""
        coord = _make_coordinator(entry_threshold_m=500.0, exit_threshold_m=700.0)
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.510, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC)

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=800.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.proximity is False
        assert result.last_seen_together == _NOW

    def test_stamped_on_in_proximity_tick(self):
        """In-proximity tick: was_proximity=True → last_seen_together updated each tick."""
        coord = _make_coordinator(entry_threshold_m=500.0, exit_threshold_m=700.0)
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC)
        old_lts = datetime(2024, 6, 1, 10, 0, 0, tzinfo=UTC)
        ps.last_seen_together = old_lts

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.proximity is True
        assert result.last_seen_together == _NOW
        assert result.last_seen_together != old_lts

    def test_not_stamped_on_entry_tick(self):
        """ENTRY tick (was_proximity=False): last_seen_together should not be set."""
        coord = _make_coordinator(entry_threshold_m=500.0, exit_threshold_m=700.0)
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = False
        ps.last_seen_together = None

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.proximity is True
        assert result.last_seen_together is None

    def test_not_stamped_when_never_in_proximity(self):
        """Outside-proximity tick: last_seen_together stays None."""
        coord = _make_coordinator(entry_threshold_m=500.0, exit_threshold_m=700.0)
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.520, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = False
        ps.last_seen_together = None

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=2500.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.proximity is False
        assert result.last_seen_together is None


# ---------------------------------------------------------------------------
# New guards added in review pass
# ---------------------------------------------------------------------------


class TestMigrationNewGuards:
    @pytest.mark.asyncio
    async def test_v1_with_single_entity_returns_false(self):
        """CONF_ENTITIES list with <2 items must return False (IndexError guard)."""
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        entry = MagicMock()
        entry.version = 1
        entry.entry_id = "abc123"
        entry.data = {CONF_ENTITIES: ["person.alice"]}  # only 1 entity

        result = await async_migrate_entry(hass, entry)
        assert result is False

    @pytest.mark.asyncio
    async def test_unknown_version_returns_false(self):
        """Version > 2 must return False rather than silently succeeding."""
        from custom_components.entity_distance import async_migrate_entry

        hass = MagicMock()
        entry = MagicMock()
        entry.version = 99
        result = await async_migrate_entry(hass, entry)
        assert result is False


class TestSetupEntryResourceLeak:
    @pytest.mark.asyncio
    async def test_coordinator_unloaded_when_setup_raises(self):
        """If async_setup or async_recalculate raises, coordinator.async_unload() is called."""
        from custom_components.entity_distance import async_setup_entry

        coordinator = MagicMock()
        coordinator.async_setup = AsyncMock(side_effect=RuntimeError("boom"))
        coordinator.async_unload = MagicMock()

        hass = MagicMock()
        hass.data = {}
        entry = MagicMock()
        entry.entry_id = "test_entry"
        entry.data = {CONF_ENTITIES: ["person.alice", "person.bob"]}
        entry.options = {}

        with (
            patch(
                "custom_components.entity_distance.EntityDistanceCoordinator",
                return_value=coordinator,
            ),
            pytest.raises(RuntimeError, match="boom"),
        ):
            await async_setup_entry(hass, entry)

        coordinator.async_unload.assert_called_once()


class TestInvalidateWhileInProximity:
    def test_invalidate_while_in_proximity_credits_duration(self):
        """_invalidate() must credit elapsed proximity time when pair is in proximity."""

        coord = _make_coordinator()
        state_b = _make_state("person.bob", 51.5, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: None if eid == "person.alice" else state_b
        )

        ps = _fresh_pair()
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC)
        ps.proximity_duration_s = 0.0

        result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.data_valid is False
        assert result.last_error == "entity_not_found"
        # proximity cleared
        assert result.proximity is False
        assert result.proximity_since is None
        # 1 hour (11:00→12:00) credited
        assert result.proximity_duration_s == pytest.approx(3600.0, abs=1.0)

    def test_invalidate_while_in_proximity_credits_today_seconds_same_day(self):
        """_invalidate() same-day: today_proximity_seconds must NOT be re-added (already in ticks)."""
        coord = _make_coordinator()
        state_b = _make_state("person.bob", 51.5, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: None if eid == "person.alice" else state_b
        )

        ps = _fresh_pair()
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC)
        ps.today_reset_date = _NOW.date()
        # 3600s already accumulated tick-by-tick before _invalidate fires
        ps.today_proximity_seconds = 3600.0

        result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.data_valid is False
        # today_proximity_seconds must stay 3600 — not 7200 (double-count)
        assert result.today_proximity_seconds == pytest.approx(3600.0, abs=1.0)

    def test_invalidate_date_rolled_credits_post_midnight_only(self):
        """_invalidate() cross-midnight: only post-midnight slice added to today counters."""
        coord = _make_coordinator()
        state_b = _make_state("person.bob", 51.5, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: None if eid == "person.alice" else state_b
        )

        ps = _fresh_pair()
        ps.proximity = True
        # Started 23:50 on June 1, invalidated 00:10 on June 2 → 20min total, 10min post-midnight
        ps.proximity_since = datetime(2024, 6, 1, 23, 50, 0, tzinfo=UTC)
        ps.today_reset_date = date(2024, 6, 1)
        ps.today_proximity_seconds = 0.0
        ps.distance_m = 50.0

        now = datetime(2024, 6, 2, 0, 10, 0, tzinfo=UTC)
        result = coord._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert result.data_valid is False
        assert result.today_reset_date == date(2024, 6, 2)
        # only 10 min post-midnight credited to today
        assert result.today_proximity_seconds == pytest.approx(600.0, abs=2.0)
        # lifetime gets full 20 min
        assert result.proximity_duration_s == pytest.approx(1200.0, abs=2.0)


class TestPrevCalcTimePersistence:
    @pytest.mark.asyncio
    async def test_prev_calc_time_restored_from_storage(self):
        """prev_calc_time is persisted and restored so today-gap isn't lost on restart."""
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coord._pair_states = {
            pair_key("person.alice", "person.bob"): _fresh_pair(),
        }

        prev_time = datetime(2024, 6, 1, 11, 30, 0, tzinfo=UTC)
        stored = {
            "person.alice__person.bob": {
                "today_reset_date": prev_time.date().isoformat(),
                "today_proximity_seconds": 0.0,
                "today_zone_seconds": {},
                "proximity_duration_s": 0.0,
                "proximity_tracking_started": None,
                "last_seen_together": None,
                "proximity_since": None,
                "prev_calc_time": prev_time.isoformat(),
            }
        }

        store_mock = AsyncMock()
        store_mock.async_load = AsyncMock(return_value=stored)
        coord._store = store_mock

        await coord._async_load_state()

        ps = coord._pair_states[pair_key("person.alice", "person.bob")]
        assert ps.prev_calc_time == prev_time


class TestSensorAvailableAndDataValid:
    def test_distance_sensor_returns_none_when_data_invalid(self):
        from custom_components.entity_distance.sensor import DistanceSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.distance_m = 500.0
        ps.data_valid = False
        # Use inline construction matching existing test pattern
        from unittest.mock import MagicMock

        from custom_components.entity_distance.models import pair_key as pk

        coordinator = MagicMock()
        k = pk("person.a", "person.b")
        coordinator.data.pairs = {k: ps}
        entry = MagicMock()
        entry.entry_id = "test"
        s = DistanceSensor.__new__(DistanceSensor)
        s.coordinator = coordinator
        s._pair_key = k
        s._attr_unique_id = "test_dist"
        s._attr_device_info = {}
        assert s.native_value is None

    def test_sensor_available_false_when_data_invalid(self):
        from custom_components.entity_distance.sensor import DistanceSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.distance_m = 500.0
        ps.data_valid = False
        from unittest.mock import MagicMock

        from custom_components.entity_distance.models import pair_key as pk

        coordinator = MagicMock()
        coordinator.last_update_success = True
        k = pk("person.a", "person.b")
        coordinator.data.pairs = {k: ps}
        entry = MagicMock()
        entry.entry_id = "test"
        s = DistanceSensor.__new__(DistanceSensor)
        s.coordinator = coordinator
        s._pair_key = k
        s._attr_unique_id = "test_dist"
        s._attr_device_info = {}
        assert s.available is False


# ---------------------------------------------------------------------------
# Pass-3 new coverage: updates_window_s property, _invalidate zone credit,
# resync-hold proximity flush, async_forward_entry_setups resource leak
# ---------------------------------------------------------------------------


class TestCoordinatorUpdatesWindowProperty:
    def test_updates_window_s_returns_configured_value(self):
        """updates_window_s property exposes _updates_window_s."""
        coord = _make_coordinator()
        coord._updates_window_s = 3600.0
        assert coord.updates_window_s == 3600.0


class TestInvalidateCreditsZoneBucket:
    def test_invalidate_cross_midnight_credits_zone_bucket(self):
        """_invalidate() cross-midnight credits today_zone_seconds for post-midnight slice."""
        coord = _make_coordinator()
        state_b = _make_state("person.bob", 51.5, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: None if eid == "person.alice" else state_b
        )

        ps = _fresh_pair()
        ps.proximity = True
        # Started 23:50 June 1, invalidated 00:10 June 2 → 10 min post-midnight
        ps.proximity_since = datetime(2024, 6, 1, 23, 50, 0, tzinfo=UTC)
        ps.today_reset_date = date(2024, 6, 1)
        ps.today_proximity_seconds = 0.0
        ps.today_zone_seconds = {}
        ps.distance_m = 50.0  # very_near bucket

        now = datetime(2024, 6, 2, 0, 10, 0, tzinfo=UTC)
        result = coord._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert result.data_valid is False
        assert result.today_reset_date == date(2024, 6, 2)
        # 10 min post-midnight credited to proximity and zone
        assert result.today_proximity_seconds == pytest.approx(600.0, abs=2.0)
        assert result.today_zone_seconds.get("very_near", 0.0) == pytest.approx(600.0, abs=2.0)


class TestResyncHoldFlushesProximity:
    def test_hold_closes_proximity_session(self):
        """Resync hold early-return credits proximity_duration_s before nulling."""
        coord = _make_coordinator()
        k = pair_key("person.alice", "person.bob")
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        coord._resync_silence_s = 10.0
        coord._resync_hold_s = 300.0
        coord._resync_holding = {k: True}
        hold_until = _NOW + timedelta(seconds=250)
        coord._resync_hold_until = {k: hold_until}

        ps = _fresh_pair()
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC)
        ps.today_reset_date = _NOW.date()
        ps.today_proximity_seconds = 0.0
        ps.proximity_duration_s = 0.0
        ps.data_valid = True
        ps.last_update_a = _NOW - timedelta(seconds=20)
        ps.last_update_b = _NOW - timedelta(seconds=20)

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=100.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        # Hold fires → proximity session closed
        assert result.proximity is False
        assert result.proximity_since is None
        assert result.proximity_duration_s == pytest.approx(3600.0, abs=1.0)
        assert result.data_valid is True


@pytest.mark.asyncio
async def test_platform_setup_failure_cleans_up_coordinator():
    """If async_forward_entry_setups raises, coordinator is unloaded and hass.data cleared."""
    from custom_components.entity_distance import async_setup_entry

    coordinator = MagicMock()
    coordinator.async_setup = AsyncMock()
    coordinator.async_recalculate = AsyncMock()
    coordinator.async_unload = MagicMock()

    hass = MagicMock()
    hass.data = {}
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {CONF_ENTITIES: ["person.alice", "person.bob"]}
    entry.options = {}

    async def _forward_raises(entry, platforms):
        raise RuntimeError("platform boom")

    hass.config_entries.async_forward_entry_setups = _forward_raises

    with (
        patch(
            "custom_components.entity_distance.EntityDistanceCoordinator",
            return_value=coordinator,
        ),
        patch(
            "custom_components.entity_distance._async_install_card",
            new_callable=AsyncMock,
        ),
        pytest.raises(RuntimeError, match="platform boom"),
    ):
        await async_setup_entry(hass, entry)

    coordinator.async_unload.assert_called_once()
    assert "test_entry" not in hass.data.get(DOMAIN, {})


class TestHoldFlushCrossMidnight:
    def test_hold_after_midnight_resets_today_counters(self):
        """Hold firing after midnight date-rolls today counters and credits post-midnight only."""
        from custom_components.entity_distance.models import pair_key

        coord = _make_coordinator()
        coord._resync_silence_s = 10.0
        coord._resync_hold_s = 300.0
        k = pair_key("person.alice", "person.bob")
        coord._resync_holding = {k: True}
        hold_until = datetime(2024, 6, 2, 0, 10, 0, tzinfo=UTC) + timedelta(seconds=200)
        coord._resync_hold_until = {k: hold_until}

        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = True
        # Proximity started 23:55 on June 1
        ps.proximity_since = datetime(2024, 6, 1, 23, 55, 0, tzinfo=UTC)
        ps.distance_m = 50.0
        ps.today_reset_date = date(2024, 6, 1)  # yesterday
        ps.today_proximity_seconds = 3000.0
        ps.proximity_duration_s = 0.0

        # Hold fires at 00:10 on June 2 — crosses midnight
        now = datetime(2024, 6, 2, 0, 10, 0, tzinfo=UTC)

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=50.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", now, set())

        # Date rolled → today counters reset
        assert result.today_reset_date == date(2024, 6, 2)
        assert result.today_proximity_seconds == pytest.approx(
            600.0, abs=2.0
        )  # 10 min post-midnight
        # lifetime counter: 15 min total (23:55 → 00:10)
        assert result.proximity_duration_s == pytest.approx(900.0, abs=2.0)
        assert result.proximity is False


class TestLoadStateLastBucketCredit:
    @pytest.mark.asyncio
    async def test_today_zone_seconds_credited_on_restart(self):
        """last_bucket persisted and credited to today_zone_seconds on proximity restart."""
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )
        from custom_components.entity_distance.models import pair_key

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coord._pair_states = {
            pair_key("person.alice", "person.bob"): _fresh_pair(),
        }
        coord._bucket_thresholds = _BUCKET_THRESHOLDS

        # Stored: in proximity since 14:00, prev_calc=14:30, last_bucket=very_near
        stored = {
            "person.alice__person.bob": {
                "today_reset_date": "2024-06-01",
                "today_proximity_seconds": 1800.0,
                "today_zone_seconds": {"very_near": 1800.0},
                "proximity_duration_s": 1800.0,
                "proximity_tracking_started": "2024-06-01T12:00:00+00:00",
                "last_seen_together": None,
                "proximity_since": "2024-06-01T14:00:00+00:00",
                "prev_calc_time": "2024-06-01T14:30:00+00:00",
                "last_bucket": "very_near",
            }
        }
        store_mock = MagicMock()
        store_mock.async_load = AsyncMock(return_value=stored)
        coord._store = store_mock

        # Restart at 15:00 same day
        now_load = datetime(2024, 6, 1, 15, 0, 0, tzinfo=UTC)
        with patch(
            "custom_components.entity_distance.coordinator.dt_util.now",
            return_value=now_load,
        ):
            await coord._async_load_state()

        k = pair_key("person.alice", "person.bob")
        ps = coord._pair_states[k]
        # 30 min gap (14:30→15:00) credited to proximity_duration_s
        assert ps.proximity_duration_s == pytest.approx(1800.0 + 1800.0, abs=2.0)
        # same 30 min credited to today's zone seconds
        assert ps.today_zone_seconds.get("very_near", 0.0) == pytest.approx(
            1800.0 + 1800.0, abs=2.0
        )


# ---------------------------------------------------------------------------
# Pass-6: sensor available=False guard coverage (M1)
# ---------------------------------------------------------------------------


def _make_unavailable_sensor(cls, ps_kwargs=None, extra_kwargs=None):
    """Build a sensor with available=False (data_valid=False, last_update_success=True)."""
    from unittest.mock import MagicMock

    from custom_components.entity_distance.models import pair_key as pk

    ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
    ps.data_valid = False  # → available=False
    if ps_kwargs:
        for k, v in ps_kwargs.items():
            setattr(ps, k, v)
    coordinator = MagicMock()
    coordinator.last_update_success = True
    k = pk("person.a", "person.b")
    coordinator.data = MagicMock()
    coordinator.data.pairs = {k: ps}
    coordinator.data.min_distance_m = 100.0
    entry = MagicMock()
    entry.entry_id = "test"
    sensor = cls.__new__(cls)
    sensor.coordinator = coordinator
    sensor._pair_key = k
    sensor._entry = entry
    sensor._attr_unique_id = "test"
    sensor._attr_device_info = {}
    if extra_kwargs:
        for attr, val in extra_kwargs.items():
            setattr(sensor, attr, val)
    return sensor


class TestSensorAvailableFalseReturnsNone:
    def test_last_seen_together_still_returns_value_when_data_invalid(self):
        from datetime import UTC, datetime

        from custom_components.entity_distance.sensor import LastSeenTogetherSensor

        s = _make_unavailable_sensor(
            LastSeenTogetherSensor, {"last_seen_together": datetime.now(UTC)}
        )
        assert s.native_value is not None

    def test_gps_accuracy_returns_none(self):
        from custom_components.entity_distance.sensor import GpsAccuracySensor

        s = _make_unavailable_sensor(GpsAccuracySensor, {"accuracy_a": 10.0}, {"_which": "a"})
        s._sensor_key = "gps_accuracy_a"
        assert s.native_value is None

    def test_last_update_still_returns_value_when_data_invalid(self):
        from datetime import UTC, datetime

        from custom_components.entity_distance.sensor import LastUpdateSensor

        s = _make_unavailable_sensor(
            LastUpdateSensor, {"last_update_a": datetime.now(UTC)}, {"_which": "a"}
        )
        s._sensor_key = "last_update_a"
        assert s.native_value is not None

    def test_proximity_tracking_started_still_returns_value_when_data_invalid(self):
        from datetime import UTC, datetime

        from custom_components.entity_distance.sensor import (
            ProximityTrackingStartedSensor,
        )

        s = _make_unavailable_sensor(
            ProximityTrackingStartedSensor,
            {"proximity_tracking_started": datetime.now(UTC)},
        )
        s._sensor_key = "proximity_tracking_started"
        assert s.native_value is not None

    def test_today_unaccounted_returns_none(self):
        # TodayUnaccountedTimeSensor intentionally does NOT gate on data_valid —
        # its purpose is reporting time during invalid windows. Returns None
        # only when coordinator itself failed.
        from datetime import UTC, datetime
        from unittest.mock import MagicMock

        from custom_components.entity_distance.sensor import TodayUnaccountedTimeSensor

        s = _make_unavailable_sensor(
            TodayUnaccountedTimeSensor, {"prev_calc_time": datetime.now(UTC)}
        )
        s._sensor_key = "today_unaccounted_time"
        # data_valid=False but coordinator OK → still reports.
        assert s.native_value is not None
        # Coordinator failure → None.
        s.coordinator = MagicMock()
        s.coordinator.last_update_success = False
        assert s.native_value is None

    def test_entity_state_returns_none_when_coordinator_failed(self):
        from unittest.mock import MagicMock

        from custom_components.entity_distance.models import pair_key as pk
        from custom_components.entity_distance.sensor import EntityStateSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        coordinator = MagicMock()
        coordinator.last_update_success = False  # coordinator failed
        k = pk("person.a", "person.b")
        coordinator.data = MagicMock()
        coordinator.data.pairs = {k: ps}
        entry = MagicMock()
        entry.entry_id = "test"
        s = EntityStateSensor.__new__(EntityStateSensor)
        s.coordinator = coordinator
        s._pair_key = k
        s._entry = entry
        s._tracked_entity_id = "person.a"
        s._attr_unique_id = "test"
        s._attr_device_info = {}
        hass = MagicMock()
        state_mock = MagicMock()
        state_mock.state = "home"
        hass.states.get.return_value = state_mock
        s.hass = hass
        assert s.native_value is None

    def test_proximity_duration_still_returns_value_when_data_invalid(self):
        from datetime import UTC, datetime

        from custom_components.entity_distance.sensor import ProximityDurationSensor

        s = _make_unavailable_sensor(
            ProximityDurationSensor,
            {
                "proximity_tracking_started": datetime.now(UTC),
                "proximity_duration_s": 3600.0,
            },
        )
        s._sensor_key = "proximity_duration"
        assert s.native_value is not None


# ---------------------------------------------------------------------------
# Pass-6 M2: REG-1, REG-3, REG-4 dedicated coverage
# ---------------------------------------------------------------------------


class TestReg1PrevCalcTimeAnchor:
    @pytest.mark.asyncio
    async def test_prev_calc_time_anchors_gap_not_proximity_since(self):
        """REG-1: gap credited on restart anchors on prev_calc_time, not proximity_since."""
        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )
        from custom_components.entity_distance.models import pair_key

        coord = EntityDistanceCoordinator.__new__(EntityDistanceCoordinator)
        coord._pair_states = {pair_key("person.alice", "person.bob"): _fresh_pair()}

        # proximity_since = 10:00, prev_calc_time = 11:30 (1.5h gap in stored duration)
        # Restart at 12:00 → gap should be 30min (12:00 - 11:30), not 2h (12:00 - 10:00)
        stored = {
            "person.alice__person.bob": {
                "today_reset_date": "2024-06-01",
                "today_proximity_seconds": 5400.0,
                "today_zone_seconds": {},
                "proximity_duration_s": 5400.0,
                "proximity_tracking_started": "2024-06-01T09:00:00+00:00",
                "last_seen_together": None,
                "proximity_since": "2024-06-01T10:00:00+00:00",
                "prev_calc_time": "2024-06-01T11:30:00+00:00",
                "last_bucket": "near",
            }
        }
        store_mock = MagicMock()
        store_mock.async_load = AsyncMock(return_value=stored)
        coord._store = store_mock

        now_load = datetime(2024, 6, 1, 12, 0, 0, tzinfo=UTC)
        with patch(
            "custom_components.entity_distance.coordinator.dt_util.now",
            return_value=now_load,
        ):
            await coord._async_load_state()

        k = pair_key("person.alice", "person.bob")
        ps = coord._pair_states[k]
        # gap = 12:00 - 11:30 = 1800s → total = 5400 + 1800 = 7200
        assert ps.proximity_duration_s == pytest.approx(5400.0 + 1800.0, abs=2.0)
        # If anchored on proximity_since (10:00) it would be 5400 + 7200 = 12600 — wrong


class TestReg3CrossMidnightZoneSeconds:
    def test_zone_seconds_only_post_midnight_after_date_roll(self):
        """REG-3: cross-midnight _calc_pair credits today_zone_seconds only for post-midnight slice."""
        coord = _make_coordinator()
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 23, 0, 0, tzinfo=UTC)
        ps.prev_calc_time = datetime(2024, 6, 1, 23, 50, 0, tzinfo=UTC)
        ps.today_reset_date = date(2024, 6, 1)
        ps.today_proximity_seconds = 3000.0
        ps.today_zone_seconds = {}
        ps.distance_m = 50.0  # very_near

        # dist_m = 50 → very_near bucket; 10 min after midnight
        now = datetime(2024, 6, 2, 0, 10, 0, tzinfo=UTC)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=50.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", now, set())

        assert result.today_reset_date == date(2024, 6, 2)
        # today_zone_seconds must equal today_proximity_seconds (10 min post-midnight only)
        zone_total = sum(result.today_zone_seconds.values())
        assert zone_total == pytest.approx(result.today_proximity_seconds, abs=2.0)
        assert zone_total == pytest.approx(600.0, abs=2.0)


class TestReg4ExitBucketUsesProximityDistance:
    def test_exit_tick_credits_proximity_era_bucket_not_exit_distance(self):
        """REG-4: on EXIT tick, zone bucket credited is from proximity-era distance, not exit distance."""
        coord = _make_coordinator(entry_threshold_m=500.0, exit_threshold_m=700.0)
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        # dist_m on exit will be 800m (far bucket), but proximity-era was 50m (very_near)
        state_b = _make_state("person.bob", 51.508, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 11, 55, 0, tzinfo=UTC)
        ps.prev_calc_time = datetime(2024, 6, 1, 11, 55, 0, tzinfo=UTC)
        ps.prev_distance_m = 50.0  # proximity-era distance → very_near
        ps.today_reset_date = _NOW.date()
        ps.today_proximity_seconds = 0.0
        ps.today_zone_seconds = {}

        # EXIT: dist_m = 800m (far bucket), but prev_distance_m_snapshot = 50m (very_near)
        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=800.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.proximity is False
        # Zone bucket must be very_near (proximity-era), NOT far (exit distance)
        assert result.today_zone_seconds.get("very_near", 0.0) > 0.0
        assert result.today_zone_seconds.get("far", 0.0) == 0.0


# ---------------------------------------------------------------------------
# Pass-6 B1: same-day hold must NOT double-count today_proximity_seconds
# ---------------------------------------------------------------------------


class TestHoldSameDayNoDoubleCount:
    def test_same_day_hold_does_not_double_count_today_proximity(self):
        """B1: same-day resync hold must not add post_hold to today_proximity_seconds again."""
        from custom_components.entity_distance.models import pair_key

        coord = _make_coordinator()
        k = pair_key("person.alice", "person.bob")
        coord._resync_silence_s = 10.0
        coord._resync_hold_s = 300.0
        coord._resync_holding = {k: True}
        hold_until = _NOW + timedelta(seconds=200)
        coord._resync_hold_until = {k: hold_until}

        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.501, -0.1, 20)
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = True
        ps.proximity_since = datetime(2024, 6, 1, 11, 0, 0, tzinfo=UTC)
        ps.today_reset_date = _NOW.date()  # same day — no date roll
        # Simulate 3600s already accumulated tick-by-tick
        ps.today_proximity_seconds = 3600.0
        ps.proximity_duration_s = 0.0
        ps.distance_m = 50.0

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=50.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.proximity is False
        # today_proximity_seconds must be unchanged (still 3600s) — hold must NOT add elapsed again
        assert result.today_proximity_seconds == pytest.approx(3600.0, abs=1.0)
        # lifetime counter gets elapsed (12:00 - 11:00 = 3600s)
        assert result.proximity_duration_s == pytest.approx(3600.0, abs=1.0)


# ---------------------------------------------------------------------------
# Pass-6 H1: today_zone_seconds tracks bucket time regardless of proximity
# ---------------------------------------------------------------------------


class TestZoneSecondsOnlyDuringProximity:
    def test_non_proximity_tick_credits_zone_seconds(self):
        """H1 (revised): today_zone_seconds tracks time-at-distance independent of proximity.
        Bucket time accrues on every valid tick so per-zone Today sensors report
        wall time spent in each distance band, not proximity-gated time."""
        coord = _make_coordinator()
        state_a = _make_state("person.alice", 51.5, -0.1, 20)
        state_b = _make_state("person.bob", 51.520, -0.1, 20)  # 2km away — not in proximity
        coord.hass.states.get = MagicMock(
            side_effect=lambda eid: state_a if eid == "person.alice" else state_b
        )
        coord.hass.bus.fire = MagicMock()

        ps = _fresh_pair()
        ps.proximity = False
        ps.prev_calc_time = datetime(2024, 6, 1, 11, 55, 0, tzinfo=UTC)
        ps.today_reset_date = _NOW.date()
        ps.today_zone_seconds = {}
        ps.today_proximity_seconds = 0.0

        with patch(
            "custom_components.entity_distance.coordinator.ha_distance",
            return_value=2200.0,
        ):
            result = coord._calc_pair(ps, "person.alice", "person.bob", _NOW, set())

        assert result.proximity is False
        # 2200 m → 'far' bucket; 5-min tick → 300 s credited to far.
        assert result.today_zone_seconds.get("far", 0.0) == pytest.approx(300.0, abs=2.0)
        # Proximity total stays gated — must not grow on non-proximity ticks.
        assert result.today_proximity_seconds == 0.0


# ---------------------------------------------------------------------------
# Pass-6: coverage for two remaining uncovered branches
# ---------------------------------------------------------------------------


class TestRemainingCoverageBranches:
    def test_proximity_duration_none_when_tracking_started_absent_but_available(self):
        """ProximityDurationSensor returns None when available=True but proximity_tracking_started=None."""
        from unittest.mock import MagicMock

        from custom_components.entity_distance.models import pair_key as pk
        from custom_components.entity_distance.sensor import ProximityDurationSensor

        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        ps.proximity_tracking_started = None
        coordinator = MagicMock()
        coordinator.last_update_success = True
        k = pk("person.a", "person.b")
        coordinator.data = MagicMock()
        coordinator.data.pairs = {k: ps}
        entry = MagicMock()
        entry.entry_id = "test"
        s = ProximityDurationSensor.__new__(ProximityDurationSensor)
        s.coordinator = coordinator
        s._pair_key = k
        s._entry = entry
        s._attr_unique_id = "test"
        s._attr_device_info = {}
        assert s.native_value is None

    def test_min_distance_returns_none_when_coordinator_failed(self):
        """MinDistanceSensor.native_value returns None when coordinator.last_update_success=False."""
        from unittest.mock import MagicMock

        from custom_components.entity_distance.coordinator import (
            EntityDistanceCoordinator,
        )
        from custom_components.entity_distance.sensor import MinDistanceSensor

        coordinator = MagicMock(spec=EntityDistanceCoordinator)
        coordinator.last_update_success = False
        coordinator.data = MagicMock()
        coordinator.data.min_distance_m = 100.0
        entry = MagicMock()
        entry.entry_id = "test"
        s = MinDistanceSensor.__new__(MinDistanceSensor)
        s.coordinator = coordinator
        s._entry = entry
        s._attr_unique_id = "test_min"
        s._attr_device_info = {}
        assert s.native_value is None
