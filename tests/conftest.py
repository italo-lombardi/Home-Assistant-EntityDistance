"""Shared fixtures for entity_distance tests."""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock

from homeassistant.config_entries import ConfigEntry
import pytest

from custom_components.entity_distance.models import GroupData, PairState, pair_key


@pytest.fixture
def mock_config_entry():
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {
        "entities": ["person.alice", "person.bob"],
        "debounce_s": 0,
        "max_accuracy_m": 200,
        "max_speed_kmh": 150,
        "resync_silence_s": 600,
        "resync_hold_s": 60,
        "grace_window_s": 900,
        "min_updates_reliable": 3,
        "updates_window_s": 300,
        "require_reliable": False,
    }
    entry.options = {}
    return entry


@pytest.fixture
def mock_group_config_entry():
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_group_entry_id"
    entry.data = {
        "entities": ["person.alice", "person.bob", "person.carol"],
        "debounce_s": 0,
        "max_accuracy_m": 200,
        "max_speed_kmh": 150,
        "resync_silence_s": 600,
        "resync_hold_s": 60,
        "grace_window_s": 900,
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
def mock_group_data(mock_group_config_entry):
    entities = mock_group_config_entry.data["entities"]
    pairs = {}
    for a, b in itertools.combinations(entities, 2):
        k = pair_key(a, b)
        pairs[k] = PairState(entity_a_id=k[0], entity_b_id=k[1])
    return GroupData(pairs=pairs)


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
