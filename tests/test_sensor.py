"""Tests for sensor entities."""

from __future__ import annotations

from custom_components.entity_distance.const import DIRECTION_APPROACHING
from custom_components.entity_distance.models import PairState


class TestSensorValues:
    def _make_pair(self, **kwargs) -> PairState:
        ps = PairState(entity_a_id="person.alice", entity_b_id="person.bob")
        for k, v in kwargs.items():
            setattr(ps, k, v)
        ps.data_valid = True
        return ps

    def test_distance_value(self):
        ps = self._make_pair(distance_m=300.0)
        assert ps.distance_m == 300.0

    def test_proximity_duration_minutes(self):
        ps = self._make_pair(proximity_duration_s=3600.0)
        assert round(ps.proximity_duration_s / 60, 1) == 60.0

    def test_today_proximity_time_minutes(self):
        ps = self._make_pair(today_proximity_seconds=1800.0)
        assert round(ps.today_proximity_seconds / 60, 1) == 30.0

    def test_direction(self):
        ps = self._make_pair(direction=DIRECTION_APPROACHING)
        assert ps.direction == DIRECTION_APPROACHING

    def test_eta_none_when_not_approaching(self):
        ps = self._make_pair(direction="diverging", eta_minutes=None)
        assert ps.eta_minutes is None

    def test_diagnostic_accuracy(self):
        ps = self._make_pair(accuracy_a=15.0, accuracy_b=30.0)
        assert ps.accuracy_a == 15.0
        assert ps.accuracy_b == 30.0
