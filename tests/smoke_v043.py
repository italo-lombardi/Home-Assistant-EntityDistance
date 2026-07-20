#!/usr/bin/env python3
"""Smoke tests for Entity Distance v0.4.3 — altitude, GPS attrs, person source fallback.

Run against a live HA instance with test entities injected.
Usage:
    python3 tests/smoke_v043.py

Requirements:
    - HA running at http://localhost:8123
    - Long-lived token in HA_TOKEN env var: export HA_TOKEN=<your-token>
    - entity_distance integration configured with device_tracker.test_alice + device_tracker.test_bob
    - Integration slug: test_alice_test_bob
"""

import json
import os
import sys
import time
import urllib.request

HA = "http://localhost:8123"
TOKEN = os.environ.get("HA_TOKEN")
if not TOKEN:
    print("ERROR: set HA_TOKEN environment variable before running smoke tests")
    print("  export HA_TOKEN=<your-long-lived-token>")
    sys.exit(1)
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
SLUG = "test_alice_test_bob"

PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

results: list[tuple[str, bool, str]] = []
_nudge = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def api(path, method="GET", data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{HA}/api{path}", headers=HEADERS, method=method, data=body)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def inject(
    entity_id, lat, lon, accuracy=10, altitude=None, speed=None, course=None, vertical_accuracy=None
):
    global _nudge
    _nudge += 1
    attrs = {
        "latitude": lat + _nudge * 0.000001,
        "longitude": lon,
        "gps_accuracy": accuracy,
        "source_type": "gps",
    }
    if altitude is not None:
        attrs["altitude"] = altitude
    if speed is not None:
        attrs["speed"] = speed
    if course is not None:
        attrs["course"] = course
    if vertical_accuracy is not None:
        attrs["vertical_accuracy"] = vertical_accuracy
    api(f"/states/{entity_id}", method="POST", data={"state": "not_home", "attributes": attrs})


def inject_and_wait(alice_kwargs, bob_kwargs, wait=3):
    """Inject both entities twice and wait for coordinator to settle.

    Two injects are needed because the coordinator computes direction/speed from
    delta between previous and current state — a single inject has no prev_state.
    The HA REST POST /api/states endpoint fires state_changed only when attributes
    differ; _nudge ensures each call produces a unique state.
    """
    alice_lat = alice_kwargs.pop("lat")
    alice_lon = alice_kwargs.pop("lon")
    bob_lat = bob_kwargs.pop("lat")
    bob_lon = bob_kwargs.pop("lon")
    inject("device_tracker.test_alice", alice_lat, alice_lon, **alice_kwargs)
    inject("device_tracker.test_bob", bob_lat, bob_lon, **bob_kwargs)
    time.sleep(1)
    inject("device_tracker.test_alice", alice_lat, alice_lon, **alice_kwargs)
    inject("device_tracker.test_bob", bob_lat, bob_lon, **bob_kwargs)
    time.sleep(wait)


def inject_person(entity_id, source_entity_id):
    """Inject a person entity pointing at a source device tracker."""
    api(
        f"/states/{entity_id}",
        method="POST",
        data={
            "state": "not_home",
            "attributes": {
                "source": source_entity_id,
                "latitude": 53.3498,
                "longitude": -6.2603,
                "gps_accuracy": 10,
            },
        },
    )


def state(entity_id):
    try:
        return api(f"/states/{entity_id}")
    except Exception:
        return None


def check(name, condition, detail=""):
    ok = bool(condition)
    results.append((name, ok, detail))
    mark = PASS if ok else FAIL
    print(f"  {mark}  {name}" + (f"  [{detail}]" if detail else ""))
    return ok


def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ---------------------------------------------------------------------------
# Test groups
# ---------------------------------------------------------------------------


def test_basic_sensors():
    section("Basic sensors — distance, proximity, direction")
    inject("device_tracker.test_alice", 53.3498, -6.2603)
    inject("device_tracker.test_bob", 53.3600, -6.2603)
    time.sleep(3)

    s = state(f"sensor.{SLUG}_distance")
    check("Distance sensor exists", s is not None)
    if s:
        val = float(s["state"]) if s["state"] not in ("unknown", "unavailable") else None
        check("Distance > 0", val and val > 0, f"{val} m")

    s = state(f"sensor.{SLUG}_proximity_zone")
    check("Proximity zone exists", s is not None)

    s = state(f"binary_sensor.{SLUG}_in_proximity")
    check("In proximity binary sensor exists", s is not None)

    s = state(f"sensor.{SLUG}_direction")
    check("Direction sensor exists", s is not None)

    s = state(f"sensor.{SLUG}_approach_speed")
    check("Closing speed sensor exists", s is not None)

    s = state(f"sensor.{SLUG}_estimated_arrival_time")
    check("ETA sensor exists", s is not None)


def test_altitude_sensors():
    section("Altitude sensors — Altitude A/B, Elevation Difference, Same Altitude")
    inject("device_tracker.test_alice", 53.3498, -6.2603, altitude=42.0)
    inject("device_tracker.test_bob", 53.3600, -6.2603, altitude=50.0)
    time.sleep(3)

    s = state(f"sensor.{SLUG}_altitude_test_alice")
    check("Altitude A exists", s is not None)
    if s and s["state"] not in ("unknown", "unavailable"):
        check("Altitude A = 42", abs(float(s["state"]) - 42.0) < 0.5, s["state"])

    s = state(f"sensor.{SLUG}_altitude_test_bob")
    check("Altitude B exists", s is not None)
    if s and s["state"] not in ("unknown", "unavailable"):
        check("Altitude B = 50", abs(float(s["state"]) - 50.0) < 0.5, s["state"])

    s = state(f"sensor.{SLUG}_elevation_difference")
    check("Elevation difference exists", s is not None)
    if s and s["state"] not in ("unknown", "unavailable"):
        check("Elevation diff = 8.0", abs(float(s["state"]) - 8.0) < 0.5, s["state"])
        attrs = s.get("attributes", {})
        check(
            "elevation_difference has altitude_a_m attr",
            "altitude_a_m" in attrs,
            str(attrs.get("altitude_a_m")),
        )
        check(
            "elevation_difference has altitude_b_m attr",
            "altitude_b_m" in attrs,
            str(attrs.get("altitude_b_m")),
        )

    s = state(f"binary_sensor.{SLUG}_same_altitude")
    check("Same altitude binary sensor exists", s is not None)
    if s:
        check("Same altitude = off (8m > 5m threshold)", s["state"] == "off", s["state"])


def test_same_altitude_threshold():
    section("Same Altitude — within threshold")
    # Two injects needed — coordinator requires prev_state to compute altitude delta
    inject("device_tracker.test_alice", 53.3498, -6.2603, altitude=100.0)
    inject("device_tracker.test_bob", 53.3600, -6.2603, altitude=103.0)
    time.sleep(2)
    inject("device_tracker.test_alice", 53.3498, -6.2603, altitude=100.0)
    inject("device_tracker.test_bob", 53.3600, -6.2603, altitude=103.0)
    time.sleep(4)

    s = state(f"binary_sensor.{SLUG}_same_altitude")
    if s:
        # 3m diff < 5m default threshold → should be ON
        check("Same altitude = on (3m < 5m threshold)", s["state"] == "on", s["state"])


def test_gps_speed_sensors():
    section("GPS Speed sensors")
    inject("device_tracker.test_alice", 53.3498, -6.2603, speed=5.0)
    inject("device_tracker.test_bob", 53.3600, -6.2603, speed=3.0)
    time.sleep(3)

    s = state(f"sensor.{SLUG}_gps_speed_test_alice")
    check("GPS Speed A exists", s is not None)
    if s and s["state"] not in ("unknown", "unavailable"):
        check("GPS Speed A = 5.0", abs(float(s["state"]) - 5.0) < 0.1, s["state"])

    s = state(f"sensor.{SLUG}_gps_speed_test_bob")
    check("GPS Speed B exists", s is not None)
    if s and s["state"] not in ("unknown", "unavailable"):
        check("GPS Speed B = 3.0", abs(float(s["state"]) - 3.0) < 0.1, s["state"])


def test_gps_heading_sensors():
    section("GPS Heading sensors")
    inject("device_tracker.test_alice", 53.3498, -6.2603, course=270.0)
    inject("device_tracker.test_bob", 53.3600, -6.2603, course=90.0)
    time.sleep(3)

    s = state(f"sensor.{SLUG}_gps_heading_test_alice")
    check("GPS Heading A exists", s is not None)
    if s and s["state"] not in ("unknown", "unavailable"):
        check("GPS Heading A = 270", abs(float(s["state"]) - 270.0) < 0.5, s["state"])

    s = state(f"sensor.{SLUG}_gps_heading_test_bob")
    check("GPS Heading B exists", s is not None)
    if s and s["state"] not in ("unknown", "unavailable"):
        check("GPS Heading B = 90", abs(float(s["state"]) - 90.0) < 0.5, s["state"])


def test_gps_vertical_accuracy_sensors():
    section("GPS Vertical Accuracy sensors")
    inject("device_tracker.test_alice", 53.3498, -6.2603, vertical_accuracy=8.0)
    inject("device_tracker.test_bob", 53.3600, -6.2603, vertical_accuracy=12.0)
    time.sleep(3)

    s = state(f"sensor.{SLUG}_gps_vertical_accuracy_test_alice")
    check("GPS Vertical Accuracy A exists", s is not None)
    if s and s["state"] not in ("unknown", "unavailable"):
        check("GPS Vertical Accuracy A = 8.0", abs(float(s["state"]) - 8.0) < 0.1, s["state"])

    s = state(f"sensor.{SLUG}_gps_vertical_accuracy_test_bob")
    check("GPS Vertical Accuracy B exists", s is not None)
    if s and s["state"] not in ("unknown", "unavailable"):
        check("GPS Vertical Accuracy B = 12.0", abs(float(s["state"]) - 12.0) < 0.1, s["state"])


def test_combined_inject():
    section("Combined inject — all GPS attrs in one update")
    inject_and_wait(
        {
            "lat": 53.3498,
            "lon": -6.2603,
            "altitude": 55.0,
            "speed": 12.5,
            "course": 180.0,
            "vertical_accuracy": 6.0,
        },
        {
            "lat": 53.3600,
            "lon": -6.2603,
            "altitude": 60.0,
            "speed": 0.0,
            "course": 0.0,
            "vertical_accuracy": 9.0,
        },
        wait=4,
    )

    checks = [
        (f"sensor.{SLUG}_altitude_test_alice", 55.0, "Altitude A"),
        (f"sensor.{SLUG}_altitude_test_bob", 60.0, "Altitude B"),
        (f"sensor.{SLUG}_elevation_difference", 5.0, "Elevation diff"),
        (f"sensor.{SLUG}_gps_speed_test_alice", 12.5, "GPS Speed A"),
        (f"sensor.{SLUG}_gps_speed_test_bob", 0.0, "GPS Speed B"),
        (f"sensor.{SLUG}_gps_heading_test_alice", 180.0, "GPS Heading A"),
        (f"sensor.{SLUG}_gps_heading_test_bob", 0.0, "GPS Heading B"),
        (f"sensor.{SLUG}_gps_vertical_accuracy_test_alice", 6.0, "GPS VAccuracy A"),
        (f"sensor.{SLUG}_gps_vertical_accuracy_test_bob", 9.0, "GPS VAccuracy B"),
    ]
    for entity_id, expected, label in checks:
        s = state(entity_id)
        if s and s["state"] not in ("unknown", "unavailable"):
            check(
                label,
                abs(float(s["state"]) - expected) < 0.5,
                f"{s['state']} (expected {expected})",
            )
        else:
            check(label, False, f"state={s['state'] if s else 'missing'}")


def test_person_source_fallback():
    section("Person source fallback — altitude/speed/heading via device_tracker")
    # Inject source device tracker with full GPS attrs
    inject(
        "device_tracker.test_alice_phone",
        53.3498,
        -6.2603,
        altitude=70.0,
        speed=8.0,
        course=45.0,
        vertical_accuracy=5.0,
    )
    # Inject person entity pointing at the source tracker
    inject_person("person.test_alice_person", "device_tracker.test_alice_phone")
    inject("device_tracker.test_bob", 53.3600, -6.2603, altitude=75.0)

    # Check if a person-based pair exists (slug may differ)
    person_slug = "test_alice_person_test_bob"
    time.sleep(3)

    s = state(f"sensor.{person_slug}_altitude_test_alice_person")
    if s is None:
        print(f"  {SKIP}  Person pair not configured — skipping source fallback test")
        print(
            "         (configure person.test_alice_person + device_tracker.test_bob in integration)"
        )
        return

    check(
        "Person altitude reads from source tracker (70m)",
        s["state"] not in ("unknown", "unavailable") and abs(float(s["state"]) - 70.0) < 0.5,
        s["state"],
    )
    s = state(f"sensor.{person_slug}_gps_speed_test_alice_person")
    if s:
        check(
            "Person GPS speed reads from source tracker (8.0)",
            s["state"] not in ("unknown", "unavailable") and abs(float(s["state"]) - 8.0) < 0.1,
            s["state"],
        )


def test_out_of_range_rejection():
    section("Out-of-range GPS attr rejection")
    # Altitude out of range (>15000m) → should show unknown/previous value
    inject("device_tracker.test_alice", 53.3498, -6.2603, altitude=20000.0)
    inject("device_tracker.test_bob", 53.3600, -6.2603, altitude=50.0)
    time.sleep(3)

    s = state(f"sensor.{SLUG}_altitude_test_alice")
    # Either unknown or the previous valid value — not 20000
    if s and s["state"] not in ("unknown", "unavailable"):
        check(
            "Altitude 20000m rejected (not > 15000)",
            float(s["state"]) <= 15000.0,
            s["state"],
        )
    else:
        check("Altitude 20000m rejected (unknown)", True, "unknown")

    # Speed out of range (>1000 km/h) → unknown
    inject("device_tracker.test_alice", 53.3498, -6.2603, speed=2000.0)
    time.sleep(3)
    s = state(f"sensor.{SLUG}_gps_speed_test_alice")
    if s:
        check(
            "Speed 2000 km/h rejected",
            s["state"] in ("unknown", "unavailable") or float(s["state"]) <= 1000.0,
            s["state"],
        )


def test_diagnostic_category():
    section("Diagnostic sensors — exist and return numeric/unknown state")
    # entity_category is not exposed via REST API states endpoint.
    # Verify the sensors exist and have valid state (numeric or unknown — not unavailable/missing).
    diag_entities = [
        f"sensor.{SLUG}_gps_speed_test_alice",
        f"sensor.{SLUG}_gps_heading_test_alice",
        f"sensor.{SLUG}_gps_vertical_accuracy_test_alice",
        f"sensor.{SLUG}_gps_accuracy_test_alice",
        f"sensor.{SLUG}_last_update_test_alice",
        f"sensor.{SLUG}_update_count_last_30_min_test_alice",
    ]
    for eid in diag_entities:
        s = state(eid)
        short = eid.split(f"{SLUG}_")[1]
        check(f"{short} exists", s is not None)
        if s:
            check(f"{short} not unavailable", s["state"] != "unavailable", s["state"])


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def summary():
    section("Summary")
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    failed = [(name, detail) for name, ok, detail in results if not ok]
    print(f"\n  {passed}/{total} passed")
    if failed:
        print("\n  FAILURES:")
        for name, detail in failed:
            print(f"    {FAIL}  {name}  [{detail}]")
    print()
    return len(failed) == 0


def test_approaching_binary_sensor():
    section("Approaching binary sensor")
    # Two injects: first establishes prev_state, second moves Alice closer to Bob.
    # Alice starts north of Bob; second inject moves Alice slightly south (toward Bob).
    inject("device_tracker.test_alice", 53.3600, -6.2603)  # same lat as Bob
    inject("device_tracker.test_bob", 53.3500, -6.2603)
    time.sleep(2)
    inject("device_tracker.test_alice", 53.3550, -6.2603)  # moved south, closer to Bob
    inject("device_tracker.test_bob", 53.3500, -6.2603)
    time.sleep(4)

    s = state(f"binary_sensor.{SLUG}_approaching")
    check("Approaching binary sensor exists", s is not None)
    if s:
        check(
            "Approaching = on (Alice moving toward Bob)",
            s["state"] == "on",
            s["state"],
        )

    # Now move Alice away from Bob
    inject("device_tracker.test_alice", 53.3550, -6.2603)
    inject("device_tracker.test_bob", 53.3500, -6.2603)
    time.sleep(2)
    inject("device_tracker.test_alice", 53.3600, -6.2603)  # moved north, away from Bob
    inject("device_tracker.test_bob", 53.3500, -6.2603)
    time.sleep(4)

    s = state(f"binary_sensor.{SLUG}_approaching")
    if s:
        check(
            "Approaching = off (Alice moving away from Bob)",
            s["state"] == "off",
            s["state"],
        )


def test_vertical_accuracy_filter():
    section("Vertical accuracy filter — altitude suppressed when vacc exceeds threshold")
    # Default config has max_vertical_accuracy_m = 0 (disabled), so inject with high vacc
    # and confirm altitude still shows (filter off).
    inject("device_tracker.test_alice", 53.3498, -6.2603, altitude=80.0, vertical_accuracy=100.0)
    inject("device_tracker.test_bob", 53.3600, -6.2603, altitude=85.0, vertical_accuracy=5.0)
    time.sleep(3)

    s = state(f"sensor.{SLUG}_altitude_test_alice")
    if s and s["state"] not in ("unknown", "unavailable"):
        check(
            "Altitude shown when filter disabled (max_vacc=0)",
            abs(float(s["state"]) - 80.0) < 0.5,
            s["state"],
        )
    else:
        check(
            "Altitude shown when filter disabled (max_vacc=0)",
            False,
            s["state"] if s else "missing",
        )

    # Note: enabling filter requires reconfiguring the integration via UI.
    # This test only verifies the default-disabled path (filter=0 → altitude always shown).
    print("  (filter=enabled path requires UI reconfigure — verified via unit tests)")


if __name__ == "__main__":
    print("\nEntity Distance v0.4.3 Smoke Tests")
    print(f"HA: {HA}  slug: {SLUG}\n")

    test_basic_sensors()
    test_altitude_sensors()
    test_same_altitude_threshold()
    test_gps_speed_sensors()
    test_gps_heading_sensors()
    test_gps_vertical_accuracy_sensors()
    test_combined_inject()
    test_person_source_fallback()
    test_out_of_range_rejection()
    test_diagnostic_category()
    test_approaching_binary_sensor()
    test_vertical_accuracy_filter()

    ok = summary()
    sys.exit(0 if ok else 1)
