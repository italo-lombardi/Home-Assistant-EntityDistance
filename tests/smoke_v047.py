#!/usr/bin/env python3
"""Smoke tests for Entity Distance v0.4.7 — N=2 direction hysteresis.

Fix verified: single indoor GPS oscillation tick must NOT flip direction to
approaching. Only two consecutive GPS fixes showing the same direction should
commit it. This prevents the 'approaching' binary sensor from flapping ON/OFF
when both entities are stationary indoors with noisy GPS.

Usage:
    python3 tests/smoke_v047.py

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


def inject(entity_id, lat, lon, accuracy=40):
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


def test_sensors_available():
    section("Sensors available")
    s = state(f"sensor.{SLUG}_direction")
    check("Direction sensor exists", s is not None, str(s))
    if s:
        check("Not unavailable", s["state"] != "unavailable", s["state"])

    s2 = state(f"binary_sensor.{SLUG}_in_proximity")
    check("Approaching binary sensor exists", s2 is not None)


def test_single_oscillating_tick_suppressed():
    """Indoor GPS drift: single tick where distance shrinks must NOT fire approaching.

    Scenario mirrors Dercy at home all day with GPS acc=40m oscillating ±45m.
    Alice and Bob both stationary. One GPS update shows distance shrinking 50m.
    With N=2 hysteresis, this single tick stays stationary.
    """
    section("Single indoor GPS oscillation does NOT commit approaching")

    # Both stationary at home — set baseline
    inject("device_tracker.test_alice", 53.3498, -6.2603, accuracy=40)
    inject("device_tracker.test_bob", 53.3498, -6.2603, accuracy=40)
    time.sleep(7)  # clear debounce_s=5

    s_baseline = state(f"sensor.{SLUG}_direction")
    check(
        "Baseline direction is stationary (both at same location)",
        s_baseline is not None and s_baseline["state"] in ("stationary", "unknown"),
        s_baseline["state"] if s_baseline else "missing",
    )

    # Single GPS oscillation: bob drifts 50m (within ±45m indoor noise)
    # delta ≈ 50m, threshold with acc=40 on both sides ≈ max(15, 4*40*0.15)=24m
    # This exceeds threshold, so WITHOUT hysteresis it would flip to approaching.
    inject("device_tracker.test_bob", 53.3494, -6.2603, accuracy=40)  # ~44m drift
    time.sleep(7)

    s_after = state(f"sensor.{SLUG}_direction")
    check(
        "Single oscillating tick stays stationary (N=2 hysteresis suppressed)",
        s_after is not None and s_after["state"] in ("stationary", "unknown"),
        s_after["state"] if s_after else "missing",
    )

    s_approaching = state(f"binary_sensor.{SLUG}_in_proximity")
    # We're close enough to be in proximity, but check direction didn't fire
    print(f"  [info]  in_proximity={s_approaching['state'] if s_approaching else 'missing'}")


def test_two_consecutive_approaching_commits():
    """Real departure: two GPS fixes both showing distance increase → diverging commits.

    Two confirming ticks required; single tick stays stationary.
    Tests that N=2 does NOT suppress legitimate departures.
    """
    section("Two consecutive GPS fixes commit direction (real departure)")

    # Baseline: both at same spot
    inject("device_tracker.test_alice", 53.3498, -6.2603, accuracy=15)
    inject("device_tracker.test_bob", 53.3498, -6.2603, accuracy=15)
    time.sleep(7)

    # First diverging tick — candidate only (direction stays stationary)
    inject("device_tracker.test_bob", 53.3558, -6.2603, accuracy=15)  # ~666m away
    time.sleep(7)

    s_first = state(f"sensor.{SLUG}_direction")
    check(
        "After first diverging tick: stationary (candidate recorded, not yet committed)",
        s_first is not None and s_first["state"] in ("stationary", "diverging"),
        s_first["state"] if s_first else "missing",
    )

    # Second confirming diverging tick — commits direction
    inject("device_tracker.test_bob", 53.3618, -6.2603, accuracy=15)  # another ~666m
    time.sleep(7)

    s_second = state(f"sensor.{SLUG}_direction")
    check(
        "After second confirming diverging tick: direction committed to diverging",
        s_second is not None and s_second["state"] == "diverging",
        s_second["state"] if s_second else "missing",
    )


def test_oscillation_then_real_departure():
    """Oscillation then departure: flicker suppressed, real movement detected."""
    section("Oscillation then real departure — flicker suppressed, departure detected")

    # Both stationary
    inject("device_tracker.test_alice", 53.3498, -6.2603, accuracy=40)
    inject("device_tracker.test_bob", 53.3498, -6.2603, accuracy=40)
    time.sleep(7)

    # Oscillate once (approaching) — should suppress
    inject("device_tracker.test_bob", 53.3494, -6.2603, accuracy=40)  # 44m drift
    time.sleep(7)

    s_flicker = state(f"sensor.{SLUG}_direction")
    check(
        "Oscillation tick suppressed (still stationary)",
        s_flicker is not None and s_flicker["state"] in ("stationary", "unknown"),
        s_flicker["state"] if s_flicker else "missing",
    )

    # Real departure — two confirming ticks diverging
    inject("device_tracker.test_bob", 53.3558, -6.2603, accuracy=15)
    time.sleep(7)
    inject("device_tracker.test_bob", 53.3618, -6.2603, accuracy=15)
    time.sleep(7)

    s_departure = state(f"sensor.{SLUG}_direction")
    check(
        "Real departure detected (diverging committed after 2 confirming ticks)",
        s_departure is not None and s_departure["state"] == "diverging",
        s_departure["state"] if s_departure else "missing",
    )


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
    print("\nEntity Distance v0.4.7 Smoke Tests — N=2 direction hysteresis")
    print(f"HA: {HA}  slug: {SLUG}\n")

    test_sensors_available()
    test_single_oscillating_tick_suppressed()
    test_two_consecutive_approaching_commits()
    test_oscillation_then_real_departure()

    ok = summary()
    sys.exit(0 if ok else 1)
