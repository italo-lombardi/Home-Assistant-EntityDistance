#!/usr/bin/env python3
"""Smoke tests for Entity Distance v0.4.6 — altitude 0.0 no-vertical-fix sentinel drop.

Fix verified end-to-end against live HA (coordinator._extract_altitude):
    An altitude of exactly 0.0 is the iOS/HA no-vertical-fix sentinel (CLLocation
    defaults to 0.0 on a 2D-only fix). It is DROPPED to None when it arrives with an
    absent / negative / garbage (vacc > 10000) vertical_accuracy, and KEPT when a
    valid vertical_accuracy accompanies it (a genuine sea-level fix). Dropping it
    stops a phantom sea-level reading from poisoning the altitude sensors and the
    elevation delta.

Reproduces the reporter's signature: one entity sits at a stable ~34 m while the
other reports 0.0 with no vertical fix. Pre-fix the pair showed a bogus ±34 m
elevation difference; post-fix the 0.0-side altitude and the elevation difference
read unknown/unavailable instead.

Downstream entities exercised:
    sensor.<slug>_altitude_test_alice
    sensor.<slug>_altitude_test_bob
    sensor.<slug>_elevation_difference
    binary_sensor.<slug>_same_altitude

LIVE-CONFIG CONSTRAINT:
    - debounce_s = 5 on the test_alice_test_bob entry → sleep 7s after each inject.
    - The pair is injected twice at the same close position (~11 m apart, within the
      proximity zone) so the coordinator has a prev_state and the altitude sensors
      populate — mirrors smoke_v044's altitude setup.

Usage:
    python3 tests/smoke_v049.py

Requirements:
    - HA running at http://localhost:8123
    - Long-lived token in HA_TOKEN env var: export HA_TOKEN=<your-token>
    - entity_distance configured with device_tracker.test_alice + device_tracker.test_bob
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

results: list[tuple[str, bool, str]] = []
_nudge = _random.randint(10000, 99999)

# Alice and Bob sit ~11 m apart — within the proximity threshold so same_altitude
# is evaluable and the altitude sensors populate.
_ALICE_LAT = 53.3498
_BOB_LAT = 53.3499
_LON = -6.2603

UNSET = ("unknown", "unavailable")


def api(path, method="GET", data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{HA}/api{path}", headers=HEADERS, method=method, data=body)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def inject(entity_id, lat, lon, accuracy=10, altitude=None, vertical_accuracy=None):
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
    if vertical_accuracy is not None:
        attrs["vertical_accuracy"] = vertical_accuracy
    api(f"/states/{entity_id}", method="POST", data={"state": "not_home", "attributes": attrs})


def inject_pair(alice_alt, alice_vacc, bob_alt, bob_vacc):
    """Inject the pair twice at the same close position so the coordinator settles.

    Two injects are needed because altitude_delta is computed against prev_state; a
    single inject has no prior fix. Positions are fixed (~11 m apart) so direction/
    proximity stay stable and the altitude sensors populate. State is "not_home" so
    the home-elevation fallback never backfills a dropped sentinel altitude.
    """
    for _ in range(2):
        inject(
            "device_tracker.test_alice", _ALICE_LAT, _LON,
            altitude=alice_alt, vertical_accuracy=alice_vacc,
        )
        inject(
            "device_tracker.test_bob", _BOB_LAT, _LON,
            altitude=bob_alt, vertical_accuracy=bob_vacc,
        )
        time.sleep(7)  # debounce_s=5 on this entry


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


def test_sentinel_dropped_no_vacc():
    section("Altitude 0.0 with NO vertical_accuracy → sentinel dropped")

    # Alice: 0.0 and no vertical fix → must drop. Bob: stable 34 m with a real vacc.
    inject_pair(alice_alt=0.0, alice_vacc=None, bob_alt=34.0, bob_vacc=10.0)

    sa = state(f"sensor.{SLUG}_altitude_test_alice")
    check(
        "Altitude A unavailable/unknown (0.0 no-fix sentinel dropped)",
        sa is not None and sa["state"] in UNSET,
        sa["state"] if sa else "missing",
    )

    sb = state(f"sensor.{SLUG}_altitude_test_bob")
    check(
        "Altitude B still shows the stable 34 m",
        sb is not None and sb["state"] not in UNSET and abs(float(sb["state"]) - 34.0) < 0.5,
        sb["state"] if sb else "missing",
    )

    se = state(f"sensor.{SLUG}_elevation_difference")
    check(
        "Elevation difference unknown/unavailable (delta None, no bogus ±34)",
        se is not None and se["state"] in UNSET,
        se["state"] if se else "missing",
    )


def test_sentinel_kept_with_valid_vacc():
    section("Altitude 0.0 WITH valid vertical_accuracy → kept (real sea level)")

    # Alice: a genuine 0.0 sea-level fix carrying a valid vacc → must be kept.
    inject_pair(alice_alt=0.0, alice_vacc=12.0, bob_alt=34.0, bob_vacc=10.0)

    sa = state(f"sensor.{SLUG}_altitude_test_alice")
    check(
        "Altitude A shows 0.0 (valid vacc → sentinel kept)",
        sa is not None and sa["state"] not in UNSET and abs(float(sa["state"]) - 0.0) < 0.5,
        sa["state"] if sa else "missing",
    )

    se = state(f"sensor.{SLUG}_elevation_difference")
    check(
        "Elevation difference shows a real signed delta (~34)",
        se is not None and se["state"] not in UNSET and abs(abs(float(se["state"])) - 34.0) < 0.5,
        se["state"] if se else "missing",
    )


def test_sentinel_dropped_garbage_vacc():
    section("Altitude 0.0 with garbage vertical_accuracy (99999) → sentinel dropped")

    # vacc 99999 > 10000 upper bound → _extract_vertical_accuracy returns None →
    # the 0.0 altitude is treated as an untrustworthy no-fix sentinel and dropped.
    inject_pair(alice_alt=0.0, alice_vacc=99999.0, bob_alt=34.0, bob_vacc=10.0)

    sa = state(f"sensor.{SLUG}_altitude_test_alice")
    check(
        "Altitude A unavailable/unknown (garbage vacc → sentinel dropped)",
        sa is not None and sa["state"] in UNSET,
        sa["state"] if sa else "missing",
    )

    se = state(f"sensor.{SLUG}_elevation_difference")
    check(
        "Elevation difference unknown/unavailable (delta None)",
        se is not None and se["state"] in UNSET,
        se["state"] if se else "missing",
    )


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
    print("\nEntity Distance v0.4.6 Smoke Tests — altitude 0.0 no-vertical-fix sentinel")
    print(f"HA: {HA}  slug: {SLUG}\n")

    test_sentinel_dropped_no_vacc()
    test_sentinel_kept_with_valid_vacc()
    test_sentinel_dropped_garbage_vacc()

    ok = summary()
    sys.exit(0 if ok else 1)
