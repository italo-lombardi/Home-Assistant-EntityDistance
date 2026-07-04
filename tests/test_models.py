"""Tests for PairState and pair_key models."""

from __future__ import annotations

from datetime import datetime

from custom_components.entity_distance.models import PairState, pair_key


class TestPairKey:
    def test_person_before_zone(self):
        assert pair_key("zone.home", "person.alice") == ("person.alice", "zone.home")

    def test_person_before_device_tracker(self):
        assert pair_key("device_tracker.phone", "person.alice") == (
            "person.alice",
            "device_tracker.phone",
        )

    def test_device_tracker_before_zone(self):
        assert pair_key("zone.home", "device_tracker.phone") == (
            "device_tracker.phone",
            "zone.home",
        )

    def test_zone_before_sensor(self):
        assert pair_key("sensor.gps", "zone.home") == ("zone.home", "sensor.gps")

    def test_same_domain_alphabetical(self):
        a, b = pair_key("person.bob", "person.alice")
        assert a == "person.alice"
        assert b == "person.bob"

    def test_symmetric(self):
        assert pair_key("person.alice", "zone.home") == pair_key(
            "zone.home", "person.alice"
        )

    def test_unknown_domain_last(self):
        assert pair_key("custom.thing", "person.alice")[0] == "person.alice"


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


class TestPairStateInit:
    def test_required_fields_stored(self):
        ps = PairState(entity_a_id="person.alice", entity_b_id="zone.home")
        assert ps.entity_a_id == "person.alice"
        assert ps.entity_b_id == "zone.home"

    def test_optional_nullable_fields_default_none(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        assert ps.prev_distance_m is None
        assert ps.prev_calc_time is None
        assert ps.closing_speed_kmh is None
        assert ps.eta_minutes is None
        assert ps.proximity_since is None
        assert ps.last_seen_together is None
        assert ps.today_reset_date is None
        assert ps.accuracy_a is None
        assert ps.accuracy_b is None
        assert ps.last_update_a is None
        assert ps.last_update_b is None
        assert ps.update_window_start_a is None
        assert ps.update_window_start_b is None
        assert ps.last_error is None

    def test_set_distance(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.distance_m = 250.5
        assert ps.distance_m == 250.5

    def test_set_proximity_since(self):
        now = datetime.now().astimezone()
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.proximity = True
        ps.proximity_since = now
        assert ps.proximity is True
        assert ps.proximity_since == now

    def test_set_data_valid(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.data_valid = True
        assert ps.data_valid is True

    def test_set_last_error(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.last_error = "coord_extraction_failed"
        assert ps.last_error == "coord_extraction_failed"

    def test_accumulate_today_proximity_seconds(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.today_proximity_seconds += 120.0
        ps.today_proximity_seconds += 60.0
        assert ps.today_proximity_seconds == 180.0

    def test_accumulate_proximity_duration_s(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.proximity_duration_s += 3600.0
        assert ps.proximity_duration_s == 3600.0

    def test_update_counts_increment(self):
        ps = PairState(entity_a_id="person.a", entity_b_id="person.b")
        ps.update_count_a = 5
        ps.update_count_b = 3
        assert ps.update_count_a == 5
        assert ps.update_count_b == 3
