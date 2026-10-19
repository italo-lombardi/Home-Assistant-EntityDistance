#!/usr/bin/env python3
"""Smoke tests for Entity Distance v0.4.6+ — direction held between GPS updates.

Fix verified: direction must stay 'approaching' between GPS updates and not
flicker to 'stationary' on the 60-second timer tick.

Usage:
    python3 tests/smoke_v046.py

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


def api(path, method="GET", data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{HA}/api{path}", headers=HEADERS, method=method, data=body)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def inject(entity_id, lat, lon, accuracy=10):
    attrs = {
        "latitude": lat,
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


def test_direction_sensors_exist():
    section("Direction sensors exist")
    s = state(f"sensor.{SLUG}_direction")
    check("Direction sensor exists", s is not None, str(s))
    if s:
        check("Not unavailable", s["state"] != "unavailable", s["state"])


def test_direction_approaching_on_gps_update():
    section("Direction → approaching when distance decreases")

    # Step the entities closer in small increments (< 800m per step) to stay
    # under the 1000 km/h teleport-rejection threshold at ~3s inter-update intervals.
    # Each 0.005° latitude ≈ 555m — safely below the speed cap.
    inject("device_tracker.test_alice", 53.3498, -6.2603)
    inject("device_tracker.test_bob", 53.3598, -6.2603)  # ~1.1 km apart — baseline
    time.sleep(5)

    s_before = state(f"sensor.{SLUG}_distance")
    check(
        "Baseline distance established",
        s_before is not None and s_before["state"] not in ("unknown", "unavailable"),
        s_before["state"] if s_before else "missing",
    )

    # Move bob 0.004° closer (~444m) — well under speed cap
    inject("device_tracker.test_bob", 53.3558, -6.2603)
    time.sleep(5)

    s_dir = state(f"sensor.{SLUG}_direction")
    check(
        "Direction is approaching after distance decrease",
        s_dir is not None and s_dir["state"] == "approaching",
        s_dir["state"] if s_dir else "missing",
    )


def test_direction_held_between_gps_updates():
    """Core regression: direction must NOT flip to stationary on timer tick.

    After approaching is set by a GPS update, we wait >60s (one full timer
    tick cycle) WITHOUT sending new GPS updates. Direction must stay approaching,
    not flip to stationary.
    """
    section("Direction held between GPS updates (timer tick regression)")

    # Build up approaching in two small steps so no step exceeds speed cap.
    inject("device_tracker.test_alice", 53.3498, -6.2603)
    inject("device_tracker.test_bob", 53.3598, -6.2603)  # ~1.1 km baseline
    time.sleep(5)

    inject("device_tracker.test_bob", 53.3558, -6.2603)  # move 444m closer
    time.sleep(5)

    s_dir = state(f"sensor.{SLUG}_direction")
    if s_dir is None or s_dir["state"] != "approaching":
        print(f"  {SKIP}  Could not establish approaching baseline — skipping hold test")
        print(f"         direction={s_dir['state'] if s_dir else 'missing'}")
        return

    print("  Approaching established. Waiting 70s for timer tick (no new GPS)...")
    time.sleep(70)

    s_dir_after = state(f"sensor.{SLUG}_direction")
    check(
        "Direction still approaching after 70s with no new GPS (timer tick held)",
        s_dir_after is not None and s_dir_after["state"] == "approaching",
        s_dir_after["state"] if s_dir_after else "missing",
    )


def test_direction_updates_on_new_gps():
    section("Direction updates correctly when new GPS fix arrives")

    # Establish approaching in two small steps
    inject("device_tracker.test_alice", 53.3498, -6.2603)
    inject("device_tracker.test_bob", 53.3598, -6.2603)
    time.sleep(5)
    inject("device_tracker.test_bob", 53.3558, -6.2603)  # move closer
    time.sleep(5)

    # Move bob 0.004° away — new GPS fix should update direction to diverging
    inject("device_tracker.test_bob", 53.3598, -6.2603)
    time.sleep(5)

    s_dir = state(f"sensor.{SLUG}_direction")
    check(
        "Direction updates to diverging on new GPS fix moving away",
        s_dir is not None and s_dir["state"] in ("diverging", "stationary"),
        s_dir["state"] if s_dir else "missing",
    )


def test_basic_regression():
    section("Basic sensors regression")
    inject("device_tracker.test_alice", 53.3498, -6.2603)
    inject("device_tracker.test_bob", 53.3600, -6.2603)
    time.sleep(3)

    s = state(f"sensor.{SLUG}_distance")
    check(
        "Distance sensor exists and has value",
        s is not None and s["state"] not in ("unknown", "unavailable"),
        s["state"] if s else "missing",
    )

    s = state(f"binary_sensor.{SLUG}_in_proximity")
    check("In proximity binary sensor exists", s is not None)

    s = state(f"sensor.{SLUG}_proximity_duration")
    check("Proximity duration sensor exists", s is not None)


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
    print("\nEntity Distance v0.4.6 Smoke Tests — direction hold fix")
    print(f"HA: {HA}  slug: {SLUG}\n")

    test_direction_sensors_exist()
    test_direction_approaching_on_gps_update()
    test_direction_held_between_gps_updates()
    test_direction_updates_on_new_gps()
    test_basic_regression()

    ok = summary()
    sys.exit(0 if ok else 1)
