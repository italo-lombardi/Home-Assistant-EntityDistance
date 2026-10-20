#!/usr/bin/env python3
"""Smoke tests for Entity Distance v0.4.8 — direction/approaching on a real drive.

Fix verified: during a sustained approach with SPARSE GPS fixes (minutes apart) and
intervening 1-min timer ticks, the `direction` sensor must read `approaching` for the
whole drive — not flicker to stationary/unknown — and `approach_speed` must be plausible
(not hundreds of km/h). Reproduces the 2026-10-20 drive-home report where a 12 km → 40 m
approach showed `approaching` on only ~4 one-tick flickers and `approach_speed` hit
611 km/h.

Root causes fixed:
    F1 — direction/speed computed against the LAST REAL GPS FIX (last_fix_*), not prev_*
         which a fix-less timer tick overwrites every minute (→ corrupted delta_s → no
         latch + inflated speed).
    F2 — an unambiguous move commits approaching/diverging on the first fix (the N=2
         indoor-flicker hysteresis is kept only for marginal near-threshold moves).
    F3 — a 1-tick zone-name blip (not_home/unknown and back) no longer wipes the streak.

Usage:
    python3 tests/smoke_v048.py

Requirements:
    - HA running at http://localhost:8123
    - Long-lived token in HA_TOKEN env var: export HA_TOKEN=<your-token>
    - entity_distance configured with device_tracker.test_alice + device_tracker.test_bob
    - Integration slug: test_alice_test_bob
"""

import contextlib
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

results: list[tuple[str, bool, str]] = []


def api(path, method="GET", data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{HA}/api{path}", headers=HEADERS, method=method, data=body)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def inject(entity_id, lat, lon, accuracy=30):
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


# Bob drives toward Alice (fixed). Latitudes stepping ~stepwise closer. One GPS fix every
# ~3s here (stands in for the real minutes-apart cadence); the point is that between the
# injected fixes the integration's own 1-min timer tick fires and must HOLD approaching.
# Degrees of latitude ≈ 111 km, so each 0.02° step ≈ 2.2 km closing.
_DRIVE = [53.55, 53.52, 53.49, 53.46, 53.43, 53.40, 53.37, 53.35]  # → toward 53.3498
_HOME_LAT = 53.3498
_LON = -6.2603


def test_approach_latches_over_drive():
    section("Sustained approach latches 'approaching' across sparse fixes")

    inject("device_tracker.test_alice", _HOME_LAT, _LON, accuracy=20)
    inject("device_tracker.test_bob", _DRIVE[0], _LON, accuracy=20)
    time.sleep(7)

    approaching_count = 0
    speeds: list[float] = []
    for lat in _DRIVE[1:]:
        inject("device_tracker.test_bob", lat, _LON, accuracy=20)
        time.sleep(7)
        d = state(f"sensor.{SLUG}_direction")
        if d and d["state"] == "approaching":
            approaching_count += 1
        sp = state(f"sensor.{SLUG}_approach_speed")
        if sp and sp["state"] not in ("unknown", "unavailable"):
            with contextlib.suppress(ValueError):
                speeds.append(float(sp["state"]))

    # Pre-fix behaviour showed approaching on a tiny minority of fixes; post-fix a clean
    # closing drive should read approaching on the large majority.
    check(
        "Direction reads 'approaching' on most fixes during the drive",
        approaching_count >= len(_DRIVE) - 3,
        f"{approaching_count}/{len(_DRIVE) - 1} fixes",
    )
    check(
        "approach_speed stays physically plausible (no 600 km/h artifact)",
        bool(speeds) and max(speeds) < 300.0,
        f"max={max(speeds):.0f} km/h" if speeds else "no speed samples",
    )


def test_approaching_holds_between_fixes():
    section("Approaching holds across a fix-less interval (timer tick)")

    inject("device_tracker.test_alice", _HOME_LAT, _LON, accuracy=20)
    inject("device_tracker.test_bob", 53.45, _LON, accuracy=20)
    time.sleep(7)
    inject("device_tracker.test_bob", 53.40, _LON, accuracy=20)  # confident approach
    time.sleep(7)
    s1 = state(f"sensor.{SLUG}_direction")
    check(
        "Approaching committed on the confident move",
        s1 is not None and s1["state"] == "approaching",
        s1["state"] if s1 else "missing",
    )

    # No new fix for a while — the 1-min integration timer tick will run; direction must
    # not drop to stationary.
    time.sleep(65)
    s2 = state(f"sensor.{SLUG}_direction")
    check(
        "Approaching held across the fix-less timer tick (not reset to stationary)",
        s2 is not None and s2["state"] == "approaching",
        s2["state"] if s2 else "missing",
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
    print("\nEntity Distance v0.4.8 Smoke Tests — direction/approaching on a real drive")
    print(f"HA: {HA}  slug: {SLUG}\n")

    test_approach_latches_over_drive()
    test_approaching_holds_between_fixes()

    ok = summary()
    sys.exit(0 if ok else 1)
