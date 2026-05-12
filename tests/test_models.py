"""Tests for PairState and PairData models."""

from __future__ import annotations

from custom_components.entity_distance.models import PairData, PairState


class TestPairStateDefaults:
    def test_defaults(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        assert ps.distance_m is None
        assert ps.direction is None
        assert ps.proximity is False
        assert ps.data_valid is False
        assert ps.today_proximity_seconds == 0.0
        assert ps.proximity_duration_s == 0.0
        assert ps.update_count_a == 0
        assert ps.update_count_b == 0
        assert ps.update_window_start_a is None
        assert ps.update_window_start_b is None

    def test_pair_data_wraps_state(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        pd = PairData(pair=ps)
        assert pd.pair is ps
