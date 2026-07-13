"""Tests for proximity binary sensors (per-pair and group-level)."""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock

import pytest

from custom_components.entity_distance.binary_sensor import (
    AllInProximityBinarySensor,
    AnyInProximityBinarySensor,
    BucketBinarySensor,
    ProximityBinarySensor,
    ReliableBinarySensor,
    SameZoneBinarySensor,
    async_setup_entry,
)
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
from custom_components.entity_distance.models import GroupData, PairState, pair_key


def _make_group_data(entities: list[str], proximity_map: dict | None = None) -> GroupData:
    pairs = {}
    for a, b in itertools.combinations(entities, 2):
        k = pair_key(a, b)
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = True
        if proximity_map:
            ps.proximity = proximity_map.get(k, False)
        pairs[k] = ps
    any_prox = any(ps.proximity for ps in pairs.values() if ps.data_valid)
    all_prox = bool(pairs) and all(ps.proximity for ps in pairs.values() if ps.data_valid)
    return GroupData(pairs=pairs, any_in_proximity=any_prox, all_in_proximity=all_prox)


def _make_proximity_sensor(
    group_data: GroupData, pair_key_val: tuple[str, str]
) -> ProximityBinarySensor:
    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    coordinator.data = group_data
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = ProximityBinarySensor.__new__(ProximityBinarySensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._pair_key = pair_key_val
    sensor._attr_unique_id = f"test_{pair_key_val[0]}__{pair_key_val[1]}_proximity"
    sensor._attr_device_info = {}
    return sensor


def _make_any_sensor(group_data: GroupData) -> AnyInProximityBinarySensor:
    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    coordinator.data = group_data
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = AnyInProximityBinarySensor.__new__(AnyInProximityBinarySensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._attr_unique_id = "test_any_in_proximity"
    sensor._attr_device_info = {}
    return sensor


def _make_all_sensor(group_data: GroupData) -> AllInProximityBinarySensor:
    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    coordinator.data = group_data
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = AllInProximityBinarySensor.__new__(AllInProximityBinarySensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._attr_unique_id = "test_all_in_proximity"
    sensor._attr_device_info = {}
    return sensor


def _make_same_zone_sensor(
    pair_key_val: tuple[str, str],
    state_a: str | None,
    state_b: str | None,
    name_a: str | None = None,
    name_b: str | None = None,
) -> SameZoneBinarySensor:
    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = SameZoneBinarySensor.__new__(SameZoneBinarySensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._pair_key = pair_key_val

    def _get_state(entity_id):
        mapping = {pair_key_val[0]: state_a, pair_key_val[1]: state_b}
        names = {pair_key_val[0]: name_a, pair_key_val[1]: name_b}
        val = mapping.get(entity_id)
        if val is None:
            return None
        s = MagicMock()
        s.state = val
        # MagicMock's `.name` is reserved by Mock — must set via configure_mock.
        nm = names.get(entity_id)
        if nm is not None:
            s.configure_mock(name=nm)
        else:
            # Fallback: object_id (HA's State.name default).
            s.configure_mock(name=entity_id.split(".", 1)[1])
        return s

    sensor.hass = MagicMock()
    sensor.hass.states.get = _get_state
    sensor._attr_unique_id = f"test_{pair_key_val[0]}__{pair_key_val[1]}_same_zone"
    sensor._attr_device_info = {}
    return sensor


class TestProximityBinarySensor:
    def test_hold_active_false_when_not_holding(self):
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = True
        ps.proximity = True
        gd = GroupData(pairs={k: ps})
        sensor = _make_proximity_sensor(gd, k)
        sensor.coordinator._resync_holding = {k: False}
        assert sensor.extra_state_attributes == {"hold_active": False}

    def test_hold_active_true_when_holding(self):
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = True
        ps.proximity = True
        gd = GroupData(pairs={k: ps})
        sensor = _make_proximity_sensor(gd, k)
        sensor.coordinator._resync_holding = {k: True}
        assert sensor.extra_state_attributes == {"hold_active": True}

    def test_is_on_true_when_valid_and_proximity(self):
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = True
        ps.proximity = True
        sensor = _make_proximity_sensor(GroupData(pairs={k: ps}), k)
        assert sensor.is_on is True

    def test_is_on_none_when_invalid_and_no_grace(self):
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = False
        sensor = _make_proximity_sensor(GroupData(pairs={k: ps}), k)
        sensor.coordinator.is_within_grace.return_value = False
        assert sensor.is_on is None

    def test_is_on_holds_last_proximity_during_grace(self):
        # BUG regression: _invalidate forces ps.proximity=False, but during the
        # display grace window the sensor must hold last_proximity (True), not flip
        # off on a blip.
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = False  # invalidated
        ps.proximity = False  # forced False by _invalidate
        ps.last_proximity = True  # was together before the blip
        sensor = _make_proximity_sensor(GroupData(pairs={k: ps}), k)
        sensor.coordinator.is_within_grace.return_value = True
        assert sensor.is_on is True


class TestSameZoneBinarySensor:
    def test_true_when_both_same_named_zone(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "home", "home")
        assert sensor.is_on is True

    def test_true_when_both_same_non_home_zone(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "work", "work")
        assert sensor.is_on is True

    def test_false_when_different_zones(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "home", "work")
        assert sensor.is_on is False

    def test_false_when_either_not_home(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "home", "not_home")
        assert sensor.is_on is False

    def test_false_when_both_not_home(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "not_home", "not_home")
        assert sensor.is_on is False

    def test_false_when_either_unknown(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "home", "unknown")
        assert sensor.is_on is False

    def test_false_when_either_unavailable(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "unavailable", "home")
        assert sensor.is_on is False

    def test_false_when_state_a_missing(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, None, "home")
        assert sensor.is_on is False

    def test_false_when_state_b_missing(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "home", None)
        assert sensor.is_on is False

    def test_unique_id_contains_pair_ids(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "home", "home")
        assert "person.alice" in sensor._attr_unique_id or "person.bob" in sensor._attr_unique_id
        assert "same_zone" in sensor._attr_unique_id

    def test_true_when_person_in_zone_object_id(self):
        # zone.* state is a count (e.g. "3"), not a name. Compare object_id instead.
        k = pair_key("person.alice", "zone.home")
        sensor = _make_same_zone_sensor(k, "home", "3")
        assert sensor.is_on is True

    def test_false_when_person_not_in_zone(self):
        k = pair_key("person.alice", "zone.home")
        sensor = _make_same_zone_sensor(k, "work", "3")
        assert sensor.is_on is False

    def test_false_when_person_state_not_home_with_zone(self):
        # not_home is in the "_no_zone" filter set — pair zone-vs-not_home → False.
        k = pair_key("person.alice", "zone.home")
        sensor = _make_same_zone_sensor(k, "not_home", "3")
        assert sensor.is_on is False

    def test_renamed_zone_matches_via_friendly_name(self):
        # zone.work renamed to "My Office" → device_tracker sets person.state = "My Office".
        # Comparison must use State.name (friendly_name), not object_id.
        k = pair_key("person.alice", "zone.work")
        sensor = _make_same_zone_sensor(k, "My Office", "3", name_a="alice", name_b="My Office")
        assert sensor.is_on is True

    def test_renamed_zone_mismatched_state_returns_false(self):
        k = pair_key("person.alice", "zone.work")
        sensor = _make_same_zone_sensor(k, "Home", "3", name_a="alice", name_b="My Office")
        assert sensor.is_on is False

    def test_zone_home_uses_literal_home_not_friendly_name(self):
        # zone.home is special-cased in HA: state is always literal STATE_HOME ("home"),
        # regardless of any friendly_name override. Match that exact behavior.
        k = pair_key("person.alice", "zone.home")
        sensor = _make_same_zone_sensor(k, "home", "3", name_a="alice", name_b="My House")
        assert sensor.is_on is True


def _make_bucket_sensor(
    pair_key_val: tuple[str, str],
    bucket: str,
    distance_m: float | None,
    data_valid: bool = True,
) -> BucketBinarySensor:
    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    ps = PairState(entity_a_id=pair_key_val[0], entity_b_id=pair_key_val[1])
    ps.data_valid = data_valid
    ps.distance_m = distance_m
    coordinator.data = GroupData(pairs={pair_key_val: ps})
    coordinator.bucket_thresholds = {
        BUCKET_VERY_NEAR: DEFAULT_ZONE_VERY_NEAR_M,
        BUCKET_NEAR: DEFAULT_ZONE_NEAR_M,
        BUCKET_MID: DEFAULT_ZONE_MID_M,
        BUCKET_FAR: DEFAULT_ZONE_FAR_M,
    }
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = BucketBinarySensor.__new__(BucketBinarySensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._pair_key = pair_key_val
    sensor._bucket = bucket
    sensor._attr_unique_id = f"test_{pair_key_val[0]}__{pair_key_val[1]}_in_{bucket}"
    sensor._attr_device_info = {}
    return sensor


class TestBucketBinarySensor:
    def test_very_near_on_when_under_100m(self):
        k = pair_key("person.alice", "person.bob")
        s = _make_bucket_sensor(k, BUCKET_VERY_NEAR, 50.0)
        assert s.is_on is True

    def test_very_near_off_when_far(self):
        k = pair_key("person.alice", "person.bob")
        s = _make_bucket_sensor(k, BUCKET_VERY_NEAR, 5000.0)
        assert s.is_on is False

    def test_near_on_in_band(self):
        k = pair_key("person.alice", "person.bob")
        s = _make_bucket_sensor(k, BUCKET_NEAR, 500.0)
        assert s.is_on is True

    def test_mid_on_in_band(self):
        k = pair_key("person.alice", "person.bob")
        s = _make_bucket_sensor(k, BUCKET_MID, 3000.0)
        assert s.is_on is True

    def test_far_on_in_band(self):
        k = pair_key("person.alice", "person.bob")
        s = _make_bucket_sensor(k, BUCKET_FAR, 15000.0)
        assert s.is_on is True

    def test_very_far_on_above_far(self):
        k = pair_key("person.alice", "person.bob")
        s = _make_bucket_sensor(k, BUCKET_VERY_FAR, 50000.0)
        assert s.is_on is True

    def test_returns_none_when_data_invalid(self):
        k = pair_key("person.alice", "person.bob")
        s = _make_bucket_sensor(k, BUCKET_VERY_NEAR, 50.0, data_valid=False)
        assert s.is_on is None

    def test_returns_none_when_distance_missing(self):
        k = pair_key("person.alice", "person.bob")
        s = _make_bucket_sensor(k, BUCKET_VERY_NEAR, None)
        assert s.is_on is None

    def test_exactly_one_bucket_on_at_a_time(self):
        k = pair_key("person.alice", "person.bob")
        on_count = sum(
            1
            for b in (
                BUCKET_VERY_NEAR,
                BUCKET_NEAR,
                BUCKET_MID,
                BUCKET_FAR,
                BUCKET_VERY_FAR,
            )
            if _make_bucket_sensor(k, b, 1500.0).is_on
        )
        assert on_count == 1

    def test_exact_threshold_lands_in_lower_bucket(self):
        # _calc_bucket uses `<= threshold`; exactly 200.0 m should be very_near.
        k = pair_key("person.alice", "person.bob")
        assert _make_bucket_sensor(k, BUCKET_VERY_NEAR, 200.0).is_on is True
        assert _make_bucket_sensor(k, BUCKET_NEAR, 200.0).is_on is False
        # 1000.0 m exactly → near (not mid).
        assert _make_bucket_sensor(k, BUCKET_NEAR, 1000.0).is_on is True
        assert _make_bucket_sensor(k, BUCKET_MID, 1000.0).is_on is False


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_proximity_and_same_zone_for_person_pair(self):
        from custom_components.entity_distance.const import DOMAIN

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.entities = ["person.alice", "person.bob"]
        coordinator.data = MagicMock()

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass = MagicMock()
        hass.states.get.return_value = None
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        mock_add = MagicMock(side_effect=lambda entities: added.extend(entities))

        await async_setup_entry(hass, entry, mock_add)

        types = [type(e).__name__ for e in added]
        assert "ProximityBinarySensor" in types
        assert "SameZoneBinarySensor" in types
        assert "ReliableBinarySensor" in types

    @pytest.mark.asyncio
    async def test_skips_same_zone_for_zone_pair(self):
        from custom_components.entity_distance.const import DOMAIN

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.entities = ["zone.home", "zone.work"]
        coordinator.data = MagicMock()

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass = MagicMock()
        hass.states.get.return_value = None
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        mock_add = MagicMock(side_effect=lambda entities: added.extend(entities))

        await async_setup_entry(hass, entry, mock_add)

        types = [type(e).__name__ for e in added]
        assert "ProximityBinarySensor" in types
        assert "SameZoneBinarySensor" not in types

    @pytest.mark.asyncio
    async def test_creates_group_sensors_for_three_entities(self):
        from custom_components.entity_distance.const import DOMAIN

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.entities = ["person.alice", "person.bob", "person.carol"]
        coordinator.data = MagicMock()

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass = MagicMock()
        hass.states.get.return_value = None
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        mock_add = MagicMock(side_effect=lambda entities: added.extend(entities))

        await async_setup_entry(hass, entry, mock_add)

        types = [type(e).__name__ for e in added]
        assert "AnyInProximityBinarySensor" in types
        assert "AllInProximityBinarySensor" in types

    @pytest.mark.asyncio
    async def test_no_group_sensors_for_two_entities(self):
        from custom_components.entity_distance.const import DOMAIN

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.entities = ["person.alice", "person.bob"]
        coordinator.data = MagicMock()

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass = MagicMock()
        hass.states.get.return_value = None
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        mock_add = MagicMock(side_effect=lambda entities: added.extend(entities))

        await async_setup_entry(hass, entry, mock_add)

        types = [type(e).__name__ for e in added]
        assert "AnyInProximityBinarySensor" not in types
        assert "AllInProximityBinarySensor" not in types

    @pytest.mark.asyncio
    async def test_friendly_name_falls_back_to_entity_id(self):
        from custom_components.entity_distance.const import DOMAIN

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.entities = ["person.alice", "person.bob"]
        coordinator.data = MagicMock()

        entry = MagicMock()
        entry.entry_id = "test_entry"

        hass = MagicMock()
        hass.states.get.return_value = None
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        mock_add = MagicMock(side_effect=lambda entities: added.extend(entities))

        await async_setup_entry(hass, entry, mock_add)
        assert len(added) > 0

    @pytest.mark.asyncio
    async def test_friendly_name_uses_state_name(self):
        from custom_components.entity_distance.const import DOMAIN

        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.entities = ["person.alice", "person.bob"]
        coordinator.data = MagicMock()

        entry = MagicMock()
        entry.entry_id = "test_entry"

        state_mock = MagicMock()
        state_mock.name = "Alice"

        hass = MagicMock()
        hass.states.get.return_value = state_mock
        hass.data = {DOMAIN: {"test_entry": coordinator}}

        added = []
        mock_add = MagicMock(side_effect=lambda entities: added.extend(entities))

        await async_setup_entry(hass, entry, mock_add)
        assert len(added) > 0

    def test_is_on_when_proximity_true(self):
        k = pair_key("person.alice", "person.bob")
        gd = _make_group_data(["person.alice", "person.bob"], {k: True})
        sensor = _make_proximity_sensor(gd, k)
        assert sensor.is_on is True

    def test_is_off_when_proximity_false(self):
        k = pair_key("person.alice", "person.bob")
        gd = _make_group_data(["person.alice", "person.bob"], {k: False})
        sensor = _make_proximity_sensor(gd, k)
        assert sensor.is_on is False

    def test_returns_none_when_data_invalid(self):
        k = pair_key("person.alice", "person.bob")
        gd = _make_group_data(["person.alice", "person.bob"])
        gd.pairs[k].data_valid = False
        sensor = _make_proximity_sensor(gd, k)
        assert sensor.is_on is None

    def test_unique_id_uses_entity_ids(self):
        k = pair_key("person.alice", "person.bob")
        gd = _make_group_data(["person.alice", "person.bob"])
        sensor = _make_proximity_sensor(gd, k)
        assert "person.alice" in sensor._attr_unique_id or "person.bob" in sensor._attr_unique_id

    def test_tracks_correct_pair_in_group(self):
        entities = ["person.alice", "person.bob", "person.carol"]
        k_ab = pair_key("person.alice", "person.bob")
        k_ac = pair_key("person.alice", "person.carol")
        proximity_map = {k_ab: True, k_ac: False}
        gd = _make_group_data(entities, proximity_map)

        sensor_ab = _make_proximity_sensor(gd, k_ab)
        sensor_ac = _make_proximity_sensor(gd, k_ac)

        assert sensor_ab.is_on is True
        assert sensor_ac.is_on is False


class TestAnyInProximityBinarySensor:
    def test_false_when_no_pairs_proximate(self):
        gd = _make_group_data(["person.alice", "person.bob", "person.carol"])
        sensor = _make_any_sensor(gd)
        assert sensor.is_on is False

    def test_true_when_one_pair_proximate(self):
        entities = ["person.alice", "person.bob", "person.carol"]
        k = list(itertools.combinations(["person.alice", "person.bob", "person.carol"], 2))[0]
        k = pair_key(*k)
        proximity_map = {k: True}
        gd = _make_group_data(entities, proximity_map)
        sensor = _make_any_sensor(gd)
        assert sensor.is_on is True

    def test_true_when_all_pairs_proximate(self):
        entities = ["person.alice", "person.bob", "person.carol"]
        pairs = list(itertools.combinations(entities, 2))
        proximity_map = {pair_key(*p): True for p in pairs}
        gd = _make_group_data(entities, proximity_map)
        sensor = _make_any_sensor(gd)
        assert sensor.is_on is True

    def test_uses_coordinator_data_attribute(self):
        gd = _make_group_data(["person.alice", "person.bob", "person.carol"])
        gd.any_in_proximity = True
        sensor = _make_any_sensor(gd)
        assert sensor.is_on is True


class TestAllInProximityBinarySensor:
    def test_false_when_no_pairs_proximate(self):
        gd = _make_group_data(["person.alice", "person.bob", "person.carol"])
        sensor = _make_all_sensor(gd)
        assert sensor.is_on is False

    def test_false_when_only_one_pair_proximate(self):
        entities = ["person.alice", "person.bob", "person.carol"]
        all_pairs = list(itertools.combinations(entities, 2))
        k_first = pair_key(*all_pairs[0])
        proximity_map = {k_first: True}
        gd = _make_group_data(entities, proximity_map)
        sensor = _make_all_sensor(gd)
        assert sensor.is_on is False

    def test_true_when_all_pairs_proximate(self):
        entities = ["person.alice", "person.bob", "person.carol"]
        pairs = list(itertools.combinations(entities, 2))
        proximity_map = {pair_key(*p): True for p in pairs}
        gd = _make_group_data(entities, proximity_map)
        gd.all_in_proximity = True
        sensor = _make_all_sensor(gd)
        assert sensor.is_on is True

    def test_uses_coordinator_data_attribute(self):
        gd = _make_group_data(["person.alice", "person.bob", "person.carol"])
        gd.all_in_proximity = False
        sensor = _make_all_sensor(gd)
        assert sensor.is_on is False

    def test_false_for_two_entity_group_when_not_proximate(self):
        gd = _make_group_data(["person.alice", "person.bob"])
        sensor = _make_all_sensor(gd)
        assert sensor.is_on is False


# ---------------------------------------------------------------------------
# ReliableBinarySensor — exposes coordinator.is_reliable() as a binary sensor
# so automations can gate on data confidence via a state-change trigger.
# ---------------------------------------------------------------------------


def _make_reliable_sensor(
    pair_key_val: tuple[str, str],
    ps: PairState,
    is_reliable_return: bool,
) -> ReliableBinarySensor:
    coordinator = MagicMock()
    coordinator.is_within_grace.return_value = False
    coordinator.data = MagicMock()
    coordinator.data.pairs = {pair_key_val: ps}
    coordinator.is_reliable = MagicMock(return_value=is_reliable_return)
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = ReliableBinarySensor.__new__(ReliableBinarySensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._pair_key = pair_key_val
    sensor._attr_unique_id = f"test_{pair_key_val[0]}__{pair_key_val[1]}_reliable"
    sensor._attr_device_info = {}
    return sensor


class TestReliableBinarySensor:
    def test_on_when_both_sides_above_threshold(self):
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = True
        ps.update_count_a = 5
        ps.update_count_b = 5
        sensor = _make_reliable_sensor(k, ps, is_reliable_return=True)
        assert sensor.is_on is True

    def test_off_when_either_side_below_threshold(self):
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = True
        ps.update_count_a = 1
        ps.update_count_b = 5
        sensor = _make_reliable_sensor(k, ps, is_reliable_return=False)
        assert sensor.is_on is False

    def test_none_when_data_invalid(self):
        k = pair_key("person.alice", "person.bob")
        ps = PairState(entity_a_id=k[0], entity_b_id=k[1])
        ps.data_valid = False
        sensor = _make_reliable_sensor(k, ps, is_reliable_return=True)
        # is_on must be None when data_valid is False — coordinator.is_reliable
        # not consulted.
        assert sensor.is_on is None
        sensor.coordinator.is_reliable.assert_not_called()

    def test_falls_back_to_empty_pair_when_missing(self):
        # _pair property returns a fresh PairState when the pair key is absent
        # from coordinator.data.pairs. data_valid defaults to False → is_on=None.
        k = pair_key("person.alice", "person.bob")
        coordinator = MagicMock()
        coordinator.is_within_grace.return_value = False
        coordinator.data = MagicMock()
        coordinator.data.pairs = {}
        coordinator.is_reliable = MagicMock(return_value=True)
        entry = MagicMock()
        entry.entry_id = "test_entry"
        sensor = ReliableBinarySensor.__new__(ReliableBinarySensor)
        sensor.coordinator = coordinator
        sensor._entry = entry
        sensor._pair_key = k
        sensor._attr_unique_id = "test_reliable_missing"
        sensor._attr_device_info = {}
        assert sensor.is_on is None
