"""Tests for EntityDistanceCoordinator."""

from __future__ import annotations

from custom_components.entity_distance.const import (
    BUCKET_FAR,
    BUCKET_MID,
    BUCKET_NEAR,
    BUCKET_VERY_FAR,
    BUCKET_VERY_NEAR,
)
from custom_components.entity_distance.coordinator import (
    _calc_bucket,
    _get_coords,
    _is_zone,
)
from tests.conftest import make_state, make_zone_state


class TestGetCoords:
    def test_lat_lon_attrs(self):
        state = make_state("person.alice", 51.5, -0.1, accuracy=20)
        result = _get_coords(state)
        assert result == (51.5, -0.1, 20)

    def test_location_attr(self):
        from homeassistant.core import State

        state = State("person.alice", "home", {"location": [51.5, -0.1]})
        result = _get_coords(state)
        assert result is not None
        assert result[0] == 51.5

    def test_state_string(self):
        from homeassistant.core import State

        state = State("sensor.gps", "51.5,-0.1", {})
        result = _get_coords(state)
        assert result is not None
        assert abs(result[0] - 51.5) < 0.001

    def test_invalid_returns_none(self):
        from homeassistant.core import State

        state = State("person.alice", "home", {})
        result = _get_coords(state)
        assert result is None

    def test_out_of_range_lat(self):
        from homeassistant.core import State

        state = State("person.alice", "home", {"latitude": 95.0, "longitude": 0.0})
        result = _get_coords(state)
        assert result is None


class TestCalcBucket:
    def test_very_near(self):
        assert _calc_bucket(30) == BUCKET_VERY_NEAR

    def test_near(self):
        assert _calc_bucket(150) == BUCKET_NEAR

    def test_mid(self):
        assert _calc_bucket(800) == BUCKET_MID

    def test_far(self):
        assert _calc_bucket(3000) == BUCKET_FAR

    def test_very_far(self):
        assert _calc_bucket(10000) == BUCKET_VERY_FAR

    def test_exact_boundary_very_near(self):
        assert _calc_bucket(50) == BUCKET_VERY_NEAR

    def test_just_over_boundary(self):
        assert _calc_bucket(51) == BUCKET_NEAR


class TestIsZone:
    def test_zone_entity(self):
        state = make_zone_state("zone.home", 51.5, -0.1)
        assert _is_zone(state) is True

    def test_person_entity(self):
        state = make_state("person.alice", 51.5, -0.1)
        assert _is_zone(state) is False
