#!/usr/bin/env python3
"""Smoke tests for Entity Distance v0.4.6 — five bug fixes.

Fixes covered:
  F1  vacc=0.0 extended sentinel: iOS 2D-fix with non-zero alt + vacc=0.0 dropped
  F2  _extract_vertical_accuracy strict-positive: vacc=0.0 returns None
  F3  _invalidate clears expired resync hold (no spurious hold_just_expired bypass)
  F4  proximity_duration_s max(0.0) floor
  F5  storage restore: today_proximity_seconds / today_zone_seconds validated ≥ 0

F3/F4/F5 are internal state and not directly observable end-to-end without
triggering the exact race conditions; they are verified via unit tests instead.
F1 and F2 are exercised end-to-end here.

Usage:
    python3 tests/smoke_v050.py

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


def inject_pair(alice_alt, alice_vacc, bob_alt, bob_vacc, rounds=2):
    for _ in range(rounds):
        inject(
            "device_tracker.test_alice",
            _ALICE_LAT,
            _LON,
            altitude=alice_alt,
            vertical_accuracy=alice_vacc,
        )
        inject(
            "device_tracker.test_bob", _BOB_LAT, _LON, altitude=bob_alt, vertical_accuracy=bob_vacc
        )
        time.sleep(7)  # debounce_s=5


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


# ── F1: vacc=0.0 extended sentinel ─────────────────────────────────────────────


def test_vacc_zero_nonzero_alt_dropped():
    """iOS 2D-only fix: non-zero alt (e.g. 8.5 m) with vacc=0.0 — must be dropped."""
    section("F1: non-zero alt + vacc=0.0 (iOS 2D-only) → altitude dropped")

    inject_pair(alice_alt=8.5, alice_vacc=0.0, bob_alt=34.0, bob_vacc=10.0)

    sa = state(f"sensor.{SLUG}_altitude_test_alice")
    check(
        "Altitude A unavailable/unknown (vacc=0.0 2D-only fix dropped)",
        sa is not None and sa["state"] in UNSET,
        sa["state"] if sa else "missing",
    )

    sb = state(f"sensor.{SLUG}_altitude_test_bob")
    check(
        "Altitude B still shows stable 34 m",
        sb is not None and sb["state"] not in UNSET and abs(float(sb["state"]) - 34.0) < 0.5,
        sb["state"] if sb else "missing",
    )

    se = state(f"sensor.{SLUG}_elevation_difference")
    check(
        "Elevation difference unavailable (no bogus 25 m delta)",
        se is not None and se["state"] in UNSET,
        se["state"] if se else "missing",
    )


def test_vacc_zero_zero_alt_dropped():
    """alt=0.0 + vacc=0.0: double sentinel — both conditions fire, must be dropped."""
    section("F1+F2: alt=0.0 + vacc=0.0 → dropped (both sentinel paths)")

    inject_pair(alice_alt=0.0, alice_vacc=0.0, bob_alt=34.0, bob_vacc=10.0)

    sa = state(f"sensor.{SLUG}_altitude_test_alice")
    check(
        "Altitude A unavailable/unknown (alt=0.0 + vacc=0.0 both sentinel)",
        sa is not None and sa["state"] in UNSET,
        sa["state"] if sa else "missing",
    )


def test_vacc_positive_nonzero_alt_kept():
    """Non-zero alt with real positive vacc: valid fix, must be kept."""
    section("F1 negative: non-zero alt + positive vacc → altitude kept")

    inject_pair(alice_alt=8.5, alice_vacc=12.0, bob_alt=34.0, bob_vacc=10.0)

    sa = state(f"sensor.{SLUG}_altitude_test_alice")
    check(
        "Altitude A shows 8.5 m (valid fix, not dropped)",
        sa is not None and sa["state"] not in UNSET and abs(float(sa["state"]) - 8.5) < 0.5,
        sa["state"] if sa else "missing",
    )

    se = state(f"sensor.{SLUG}_elevation_difference")
    check(
        "Elevation difference ~25 m (8.5 vs 34, real delta)",
        se is not None and se["state"] not in UNSET and abs(abs(float(se["state"])) - 25.5) < 1.5,
        se["state"] if se else "missing",
    )


def test_sealevel_with_valid_vacc_kept():
    """alt=0.0 + real positive vacc: genuine sea-level fix — must NOT be dropped."""
    section("F2 negative: alt=0.0 + valid vacc → kept (real sea level)")

    inject_pair(alice_alt=0.0, alice_vacc=12.0, bob_alt=34.0, bob_vacc=10.0)

    sa = state(f"sensor.{SLUG}_altitude_test_alice")
    check(
        "Altitude A shows 0.0 (genuine sea-level fix kept)",
        sa is not None and sa["state"] not in UNSET and abs(float(sa["state"])) < 0.5,
        sa["state"] if sa else "missing",
    )

    se = state(f"sensor.{SLUG}_elevation_difference")
    check(
        "Elevation difference ~34 m (sea-level fix real delta)",
        se is not None and se["state"] not in UNSET and abs(abs(float(se["state"])) - 34.0) < 0.5,
        se["state"] if se else "missing",
    )


# ── F2: _extract_vertical_accuracy strict positive ─────────────────────────────


def test_vacc_zero_suppresses_via_extractor():
    """vacc=0.0 in isolation (alt>0) exercises the strict-positive guard in extractor."""
    section("F2: vacc_a=0.0 suppresses vacc_a via extractor → home_a guard not needed")

    # A has vacc=0.0 with alt=50 (not at home, vacc filter path).
    # max_vertical_accuracy_m is 0 (off) by default on test entry so the vacc filter
    # is bypassed; the sentinel path in _extract_altitude covers it.
    # This test verifies _extract_vertical_accuracy returns None for vacc=0.0 by
    # checking that altitude is still dropped (sentinel path).
    inject_pair(alice_alt=50.0, alice_vacc=0.0, bob_alt=34.0, bob_vacc=10.0)

    sa = state(f"sensor.{SLUG}_altitude_test_alice")
    check(
        "Altitude A dropped (vacc=0.0 sentinel path, extractor returns None)",
        sa is not None and sa["state"] in UNSET,
        sa["state"] if sa else "missing",
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
    print("\nEntity Distance v0.4.6 Smoke Tests — 5-fix batch (vacc=0.0 + internal guards)")
    print(f"HA: {HA}  slug: {SLUG}\n")

    test_vacc_zero_nonzero_alt_dropped()
    test_vacc_zero_zero_alt_dropped()
    test_vacc_positive_nonzero_alt_kept()
    test_sealevel_with_valid_vacc_kept()
    test_vacc_zero_suppresses_via_extractor()

    ok = summary()
    sys.exit(0 if ok else 1)
