#!/usr/bin/env python3
"""Smoke tests for Entity Distance v0.4.5 — Reset Proximity Duration button + duration display.

New in 0.4.5:
  - ResetProximityDurationButton: pressing it zeroes proximity_duration_s for all pairs
  - Duration card display rolls over to days (Nd Nh) and weeks (Nw Nd) — frontend-only, no REST check
  - Storage cleanup: async_remove_entry deletes .storage/entity_distance_group_state_<entry_id>

Usage:
    python3 tests/smoke_v045.py

Requirements:
    - HA running at http://localhost:8123
    - Long-lived token in HA_TOKEN env var: export HA_TOKEN=<your-token>
    - entity_distance integration configured with device_tracker.test_alice + device_tracker.test_bob
    - Integration slug: test_alice_test_bob
"""

import json
import os
import random as _random
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
_nudge = _random.randint(10000, 99999)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def api(path, method="GET", data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{HA}/api{path}", headers=HEADERS, method=method, data=body)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def inject(entity_id, lat, lon, accuracy=10):
    global _nudge
    _nudge += 1
    attrs = {
        "latitude": lat + _nudge * 0.000001,
        "longitude": lon,
        "gps_accuracy": accuracy,
        "source_type": "gps",
    }
    api(f"/states/{entity_id}", method="POST", data={"state": "not_home", "attributes": attrs})


def state(entity_id):
    try:
        return api(f"/states/{entity_id}")
    except Exception:
        return None


def press_button(entity_id):
    api("/services/button/press", method="POST", data={"entity_id": entity_id})


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


def test_reset_proximity_duration_button_exists():
    section("Reset Proximity Duration button — entity exists")
    s = state(f"button.entity_distance_{SLUG}_reset_proximity_duration")
    check("Reset proximity duration button exists", s is not None, str(s))
    if s:
        check(
            "Button state is not unavailable",
            s["state"] != "unavailable",
            s["state"],
        )


def test_proximity_duration_sensor_exists():
    section("Proximity Duration sensor — entity exists and is numeric")
    # Inject entities to ensure coordinator has run at least once
    inject("device_tracker.test_alice", 53.3498, -6.2603)
    inject("device_tracker.test_bob", 53.3510, -6.2603)
    time.sleep(4)

    s = state(f"sensor.{SLUG}_proximity_duration")
    check("Proximity duration sensor exists", s is not None)
    if s:
        check("Not unavailable", s["state"] != "unavailable", s["state"])
        if s["state"] not in ("unknown", "unavailable"):
            try:
                val = float(s["state"])
                check("Duration is numeric (minutes)", True, f"{val} min")
            except ValueError:
                check("Duration is numeric (minutes)", False, s["state"])


def test_reset_proximity_duration_zeroes_sensor():
    section("Reset Proximity Duration button — press succeeds and sensor stays at 0")

    btn_id = f"button.entity_distance_{SLUG}_reset_proximity_duration"
    s_btn = state(btn_id)
    if s_btn is None:
        print(f"  {SKIP}  Reset button not found — skipping")
        return

    ts_before = s_btn["state"]

    press_button(btn_id)
    time.sleep(4)

    s_btn_after = state(btn_id)
    check(
        "Button state timestamp updated after press",
        s_btn_after is not None and s_btn_after["state"] != ts_before,
        f"before={ts_before} after={s_btn_after['state'] if s_btn_after else '?'}",
    )

    # Find all proximity_duration sensors for this SLUG
    all_states = api("/states")
    duration_sensors = [
        s for s in all_states
        if f"{SLUG}_proximity_duration" in s["entity_id"]
        and s["entity_id"].startswith("sensor.")
    ]
    check(
        "At least one proximity_duration sensor exists",
        len(duration_sensors) > 0,
        f"count={len(duration_sensors)}",
    )
    if not duration_sensors:
        return

    # At least one must be ≤ 0.5 min (the one paired with this button)
    any_near_zero = any(
        s["state"] not in ("unknown", "unavailable") and float(s["state"]) <= 0.5
        for s in duration_sensors
    )
    check(
        "At least one proximity_duration sensor is ≤ 0.5 min (reset confirmed)",
        any_near_zero,
        str({s["entity_id"]: s["state"] for s in duration_sensors}),
    )


def test_refresh_button_exists():
    section("Refresh button — still present (regression guard)")
    s = state(f"button.entity_distance_{SLUG}_refresh_location")
    check("Refresh button exists", s is not None)
    if s:
        check("Refresh button not unavailable", s["state"] != "unavailable", s["state"])


def test_basic_sensors_regression():
    section("Basic sensors regression — distance + proximity still work")
    inject("device_tracker.test_alice", 53.3498, -6.2603)
    inject("device_tracker.test_bob", 53.3600, -6.2603)
    time.sleep(3)

    s = state(f"sensor.{SLUG}_distance")
    check("Distance sensor exists", s is not None)
    if s and s["state"] not in ("unknown", "unavailable"):
        check("Distance > 0", float(s["state"]) > 0, f"{s['state']} m")

    s = state(f"sensor.{SLUG}_proximity_zone")
    check("Proximity zone sensor exists", s is not None)

    s = state(f"binary_sensor.{SLUG}_in_proximity")
    check("In proximity binary sensor exists", s is not None)


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


if __name__ == "__main__":
    print("\nEntity Distance v0.4.5 Smoke Tests")
    print(f"HA: {HA}  slug: {SLUG}\n")

    test_reset_proximity_duration_button_exists()
    test_proximity_duration_sensor_exists()
    test_reset_proximity_duration_zeroes_sensor()
    test_refresh_button_exists()
    test_basic_sensors_regression()

    ok = summary()
    sys.exit(0 if ok else 1)
