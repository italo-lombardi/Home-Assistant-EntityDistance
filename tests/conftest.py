"""Shared fixtures for entity_distance tests."""

from __future__ import annotations

from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntry
import pytest

from custom_components.entity_distance.models import PairData, PairState


@pytest.fixture
def mock_config_entry():
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {
        "entity_a": "person.alice",
        "entity_b": "person.bob",
        "entry_threshold_m": 500,
        "exit_threshold_m": 700,
        "debounce_s": 0,
        "max_accuracy_m": 200,
        "max_speed_kmh": 150,
        "resync_silence_s": 600,
        "resync_hold_s": 60,
        "min_updates_reliable": 3,
        "updates_window_s": 300,
        "require_reliable": False,
    }
    entry.options = {}
    return entry


@pytest.fixture
def mock_pair_state():
    return PairState(entity_a_id="person.alice", entity_b_id="person.bob")


@pytest.fixture
def mock_pair_data(mock_pair_state):
    return PairData(pair=mock_pair_state)


def make_state(
    entity_id: str,
    lat: float,
    lon: float,
    accuracy: float | None = None,
    domain: str = "person",
):
    from homeassistant.core import State

    attrs = {"latitude": lat, "longitude": lon}
    if accuracy is not None:
        attrs["gps_accuracy"] = accuracy
    return State(entity_id, "home", attrs)


def make_zone_state(entity_id: str, lat: float, lon: float, radius: float = 100):
    from homeassistant.core import State

    attrs = {"latitude": lat, "longitude": lon, "radius": radius}
    return State(entity_id, "zoning", attrs)
