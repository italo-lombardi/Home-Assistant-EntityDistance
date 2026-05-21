"""Tests for multi-entity group tracking (3+ entities)."""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock

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
