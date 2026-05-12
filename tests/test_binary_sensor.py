"""Tests for proximity binary sensor."""

from __future__ import annotations

from custom_components.entity_distance.models import PairState


class TestProximityHysteresis:
    def _make_pair(self, proximity: bool, data_valid: bool = True) -> PairState:
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        ps.proximity = proximity
        ps.data_valid = data_valid
        return ps

    def test_in_proximity_is_on(self):
        ps = self._make_pair(proximity=True)
        assert ps.proximity is True

    def test_not_in_proximity_is_off(self):
        ps = self._make_pair(proximity=False)
        assert ps.proximity is False

    def test_invalid_data_returns_none(self):
        ps = self._make_pair(proximity=False, data_valid=False)
        assert ps.data_valid is False
