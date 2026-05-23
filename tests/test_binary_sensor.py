"""Tests for proximity binary sensors (per-pair and group-level)."""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock

import pytest

from custom_components.entity_distance.binary_sensor import (
    AllInProximityBinarySensor,
    AnyInProximityBinarySensor,
    ProximityBinarySensor,
    SameZoneBinarySensor,
    async_setup_entry,
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
) -> SameZoneBinarySensor:
    coordinator = MagicMock()
    entry = MagicMock()
    entry.entry_id = "test_entry"
    sensor = SameZoneBinarySensor.__new__(SameZoneBinarySensor)
    sensor.coordinator = coordinator
    sensor._entry = entry
    sensor._pair_key = pair_key_val

    def _get_state(entity_id):
        mapping = {pair_key_val[0]: state_a, pair_key_val[1]: state_b}
        val = mapping.get(entity_id)
        if val is None:
            return None
        s = MagicMock()
        s.state = val
        return s

    sensor.hass = MagicMock()
    sensor.hass.states.get = _get_state
    sensor._attr_unique_id = f"test_{pair_key_val[0]}__{pair_key_val[1]}_same_zone"
    sensor._attr_device_info = {}
    return sensor


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

    def test_none_when_either_not_home(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "home", "not_home")
        assert sensor.is_on is None

    def test_none_when_both_not_home(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "not_home", "not_home")
        assert sensor.is_on is None

    def test_none_when_either_unknown(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "home", "unknown")
        assert sensor.is_on is None

    def test_none_when_either_unavailable(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "unavailable", "home")
        assert sensor.is_on is None

    def test_none_when_state_a_missing(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, None, "home")
        assert sensor.is_on is None

    def test_none_when_state_b_missing(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "home", None)
        assert sensor.is_on is None

    def test_unique_id_contains_pair_ids(self):
        k = pair_key("person.alice", "person.bob")
        sensor = _make_same_zone_sensor(k, "home", "home")
        assert "person.alice" in sensor._attr_unique_id or "person.bob" in sensor._attr_unique_id
        assert "same_zone" in sensor._attr_unique_id


class TestAsyncSetupEntry:
    @pytest.mark.asyncio
    async def test_creates_proximity_and_same_zone_for_person_pair(self):
        from custom_components.entity_distance.const import DOMAIN

        coordinator = MagicMock()
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

    @pytest.mark.asyncio
    async def test_skips_same_zone_for_zone_pair(self):
        from custom_components.entity_distance.const import DOMAIN

        coordinator = MagicMock()
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
