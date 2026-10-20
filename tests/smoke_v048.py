#!/usr/bin/env python3
"""Smoke tests for Entity Distance v0.4.6 — direction/approaching/speed on a real drive.

Fixes verified end-to-end against live HA:
    F1 — direction/speed computed against the LAST REAL GPS FIX (last_fix_*), not prev_*
         which a fix-less 60s timer tick overwrites. Fixes the 611 km/h approach_speed and
         the stale-direction-between-fixes.
    F2 — an unambiguous move commits approaching/diverging on the FIRST fix; the N=2
         indoor-flicker hysteresis is kept only for marginal near-threshold moves.
    F3 — a 1-tick GPS dropout inside the display grace window keeps the approaching streak,
         so a real fix after the dropout re-latches immediately.
    F4 — closing_speed/ETA computed from the noise-budget-adjusted delta: strips GPS
         jitter (no 611 km/h) but does NOT clamp — a genuine fast approach still shows speed.

LIVE-CONFIG CONSTRAINTS (verified against the test_alice_test_bob pair):
    - max_speed_kmh = 0 → direction teleport cap falls back to DEFAULT_MAX_SPEED_KMH = 1000.
      With fixes injected ~7s apart, any step implying > 1000 km/h (> ~1944 m) is rejected
      as a teleport and direction never commits. Every closing step MUST stay under ~1944 m.
    - Confident-move cutoff at accuracy=20 is ~60 m (4 × max(15, 80×0.15)). Steps must
      exceed 60 m to commit on the first fix. So each closing step lands in ~[60 m, 1944 m];
      0.01° lat ≈ 1112 m (~571 km/h over 7s) sits safely in that band.
    - debounce_s = 5 → sleep 7s after each inject.

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

_HOME_LAT = 53.3498
_LON = -6.2603


def api(path, method="GET", data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{HA}/api{path}", headers=HEADERS, method=method, data=body)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def inject(entity_id, lat, lon, accuracy=20):
    attrs = {
        "latitude": lat,
        "longitude": lon,
        "gps_accuracy": accuracy,
        "source_type": "gps",
    }
    api(f"/states/{entity_id}", method="POST", data={"state": "not_home", "attributes": attrs})


def blip(entity_id):
    """Inject a 1-tick GPS dropout: a bare state with NO coordinates.

    Mirrors a phone that reports presence but briefly loses its fix (or a transient
    not_home/unknown between fixes). Coord extraction fails for this tick →
    _invalidate("coord_extraction_failed") → the pair enters the display grace window,
    exactly like the mid-drive zone-name oscillation that F3 protects against. Distinct
    from inject(), which always attaches coords and resolves to a valid fix.
    """
    api(
        f"/states/{entity_id}",
        method="POST",
        data={"state": "not_home", "attributes": {"source_type": "gps"}},
    )


def state(entity_id):
    try:
        return api(f"/states/{entity_id}")
    except Exception:
        return None


def _speed(slug=SLUG):
    sp = state(f"sensor.{slug}_approach_speed")
    if sp and sp["state"] not in ("unknown", "unavailable"):
        with contextlib.suppress(ValueError):
            return float(sp["state"])
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


def test_sensors_available():
    section("Sensors available")
    s = state(f"sensor.{SLUG}_direction")
    check("Direction sensor exists", s is not None, str(s["state"]) if s else "missing")
    s2 = state(f"binary_sensor.{SLUG}_approaching")
    check("Approaching binary sensor exists", s2 is not None)


def test_f1_approaching_holds_across_fixless_timer_tick():
    section("F1: 'approaching' holds across a fix-less 60s timer tick; post-gap speed sane")

    # Steps sized under the 1000 km/h teleport cap: 0.01° ≈ 1112 m / 7s ≈ 571 km/h,
    # above the ~60 m confident cutoff so F2 commits on the first fix.
    inject("device_tracker.test_alice", _HOME_LAT, _LON, accuracy=20)
    inject("device_tracker.test_bob", _HOME_LAT + 0.04, _LON, accuracy=20)  # lead-in #1 (teleport)
    time.sleep(7)
    inject(
        "device_tracker.test_bob", _HOME_LAT + 0.03, _LON, accuracy=20
    )  # lead-in #2 (seeds baseline)
    time.sleep(7)

    inject(
        "device_tracker.test_bob", _HOME_LAT + 0.02, _LON, accuracy=20
    )  # confident fix, clean baseline
    time.sleep(7)
    s1 = state(f"sensor.{SLUG}_direction")
    check(
        "approaching committed on the confident closing fix (F2 first-fix)",
        s1 is not None and s1["state"] == "approaching",
        s1["state"] if s1 else "missing",
    )

    # No new GPS fix for >60s → the 60s timer tick fires. Direction must HOLD.
    time.sleep(65)
    s2 = state(f"sensor.{SLUG}_direction")
    check(
        "approaching held across the fix-less 60s timer tick (not reset to stationary)",
        s2 is not None and s2["state"] == "approaching",
        s2["state"] if s2 else "missing",
    )

    # TRUE F1 discriminator: the post-gap fix is differenced against the last REAL fix
    # (~72s ago), not against the timer tick's position. Pre-F1 divided the same ~1112 m
    # move by a few seconds → 600+ km/h. Fixed code → tens of km/h.
    inject("device_tracker.test_bob", _HOME_LAT + 0.01, _LON, accuracy=20)
    time.sleep(7)
    s3 = state(f"sensor.{SLUG}_direction")
    check(
        "approaching still reads after the gap when a new fix arrives",
        s3 is not None and s3["state"] == "approaching",
        s3["state"] if s3 else "missing",
    )
    spv = _speed()
    check(
        "approach_speed on the post-gap fix is plausible (F1: no tick-corrupted delta_s)",
        spv is not None and spv < 300.0,
        f"{spv:.0f} km/h" if spv is not None else "missing",
    )


def test_f2_confident_first_fix_vs_marginal_needs_two():
    section("F2: confident move commits on first fix; marginal still needs N=2")

    # acc=20 → noise_budget 80, stationary_thresh 15, confident cutoff 60 m.
    # Confident step ~0.01° (~1112 m, ~571 km/h) is far above 60 m and under 1000 km/h.
    #
    # Carryover guard: the FIRST inject of a test jumps from the previous test's end
    # position, which usually implies > 1000 km/h over 7s → teleport-rejected → last_fix_*
    # nulled. So we spend TWO lead-in fixes establishing a clean motion baseline before
    # asserting: inject #1 absorbs the teleport, inject #2 seeds last_fix_*, and the
    # assertion is made on a later fix whose baseline is a real prior fix.
    inject("device_tracker.test_alice", _HOME_LAT, _LON, accuracy=20)
    inject("device_tracker.test_bob", 53.42, _LON, accuracy=20)  # lead-in #1 (absorbs teleport)
    time.sleep(7)
    inject("device_tracker.test_bob", 53.41, _LON, accuracy=20)  # lead-in #2 (seeds last_fix_*)
    time.sleep(7)
    inject("device_tracker.test_bob", 53.40, _LON, accuracy=20)  # confident fix on a clean baseline
    time.sleep(7)
    d1 = state(f"sensor.{SLUG}_direction")
    check(
        "Confident move commits 'approaching' on a single fix (no N=2 wait)",
        d1 is not None and d1["state"] == "approaching",
        d1["state"] if d1 else "missing",
    )

    # Marginal sub-test. Keep moving on the SAME clean baseline (no big jump → no teleport),
    # down to a settle point, then make a marginal ~40 m move (15 < Δ < 60): it must stay
    # stationary on one fix and after a timer tick, committing only on the 2nd agreeing fix.
    inject("device_tracker.test_bob", 53.39, _LON, accuracy=20)  # keep closing, stays confident
    time.sleep(7)
    base_lat = 53.38
    inject("device_tracker.test_bob", base_lat, _LON, accuracy=20)  # settle fix, resets candidate
    time.sleep(7)
    marginal_lat = base_lat - 0.00036  # ~40 m closer
    inject("device_tracker.test_bob", marginal_lat, _LON, accuracy=20)  # 1st marginal fix
    time.sleep(7)
    dm1 = state(f"sensor.{SLUG}_direction")
    check(
        "Marginal move stays 'stationary' on a single tick (N=2 not yet met)",
        dm1 is not None and dm1["state"] == "stationary",
        dm1["state"] if dm1 else "missing",
    )
    time.sleep(65)
    dm_tick = state(f"sensor.{SLUG}_direction")
    check(
        "Marginal move still 'stationary' after a fix-less timer tick",
        dm_tick is not None and dm_tick["state"] == "stationary",
        dm_tick["state"] if dm_tick else "missing",
    )
    inject("device_tracker.test_bob", marginal_lat - 0.00036, _LON, accuracy=20)  # 2nd marginal
    time.sleep(7)
    dm2 = state(f"sensor.{SLUG}_direction")
    check(
        "Second agreeing marginal fix commits 'approaching' (N=2 satisfied)",
        dm2 is not None and dm2["state"] == "approaching",
        dm2["state"] if dm2 else "missing",
    )


def test_f3_blip_preserves_streak():
    section("F3: a 1-tick dropout inside grace keeps the approaching streak")

    _STEP = 0.012  # ~1334 m closing per fix: > 60 m cutoff, < 1944 m teleport bound
    inject("device_tracker.test_alice", _HOME_LAT, _LON, accuracy=20)
    inject("device_tracker.test_bob", _HOME_LAT + 3 * _STEP, _LON, accuracy=20)
    time.sleep(7)
    inject("device_tracker.test_bob", _HOME_LAT + 2 * _STEP, _LON, accuracy=20)
    time.sleep(7)
    inject("device_tracker.test_bob", _HOME_LAT + 1 * _STEP, _LON, accuracy=20)
    time.sleep(7)
    s_before = state(f"sensor.{SLUG}_direction")
    check(
        "Approaching committed before the blip",
        s_before is not None and s_before["state"] == "approaching",
        s_before["state"] if s_before else "missing",
    )

    # The blip: one tick with no GPS fix → _invalidate → display grace. (These during-blip
    # checks are grace-display sanity; they pass on old code too. The re-latch below is the
    # real F3 discriminator.)
    blip("device_tracker.test_bob")
    time.sleep(7)
    s_blip = state(f"sensor.{SLUG}_direction")
    check(
        "Direction not reset to stationary by the 1-tick blip (held in grace)",
        s_blip is not None and s_blip["state"] != "stationary",
        s_blip["state"] if s_blip else "missing",
    )

    # F3 discriminator: ONE real fix after the dropout. Pre-F3 the blip nulled last_fix_*,
    # so this fix writes direction=None → 'unknown'. F3 preserves the baseline → re-latches.
    inject("device_tracker.test_bob", _HOME_LAT, _LON, accuracy=20)
    time.sleep(7)
    s_after = state(f"sensor.{SLUG}_direction")
    check(
        "Approaching re-latched on the FIRST fix after the blip (F3 streak survived)",
        s_after is not None and s_after["state"] == "approaching",
        s_after["state"] if s_after else "missing",
    )


def test_f4_approach_speed_strips_noise_not_speed():
    section("F4: approach_speed strips GPS noise, does not inflate or clamp")

    # Part A — NOISY approach. acc=150 → noise budget 600 m. Bob closes ~888 m/fix
    # (0.008°). OLD raw code: 888/7·3.6 ≈ 457 km/h. F4: max(0,888-600)=288 → ~148 km/h.
    inject("device_tracker.test_alice", _HOME_LAT, _LON, accuracy=150)
    inject("device_tracker.test_bob", 53.44, _LON, accuracy=150)
    time.sleep(7)
    noisy: list[float] = []
    for lat in (53.432, 53.424, 53.416, 53.408, 53.400):
        inject("device_tracker.test_bob", lat, _LON, accuracy=150)
        time.sleep(7)
        v = _speed()
        if v is not None:
            noisy.append(v)
    check(
        "Noisy approach never shows an inflated speed (OLD raw delta → ~457 km/h)",
        bool(noisy) and max(noisy) < 200.0,
        f"max={max(noisy):.0f} km/h" if noisy else "no samples",
    )
    check(
        "Noisy approach still shows a non-zero speed (noise stripped, pair not invalidated)",
        bool(noisy) and max(noisy) > 0.0,
        f"max={max(noisy):.0f} km/h" if noisy else "no samples",
    )

    # Part B — GENUINE fast approach. acc=20 → budget 80 m. ~244 m/fix (0.0022°).
    # F4: max(0,244-80)=164 → ~84 km/h. Proves F4 strips a NOISE margin, not a km/h clamp.
    inject("device_tracker.test_alice", _HOME_LAT, _LON, accuracy=20)
    inject("device_tracker.test_bob", 53.36, _LON, accuracy=20)
    time.sleep(7)
    fast: list[float] = []
    for lat in (53.3578, 53.3556, 53.3534):
        inject("device_tracker.test_bob", lat, _LON, accuracy=20)
        time.sleep(7)
        v = _speed()
        if v is not None:
            fast.append(v)
    check(
        "Genuine fast approach shows a non-trivial speed (not clamped to 0 by noise strip)",
        bool(fast) and max(fast) > 30.0,
        f"max={max(fast):.0f} km/h" if fast else "no samples",
    )
    check(
        "Genuine fast approach is still physically plausible",
        bool(fast) and max(fast) < 200.0,
        f"max={max(fast):.0f} km/h" if fast else "no samples",
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
    print("\nEntity Distance v0.4.6 Smoke Tests — direction/approaching/speed on a real drive")
    print(f"HA: {HA}  slug: {SLUG}\n")

    test_sensors_available()
    test_f1_approaching_holds_across_fixless_timer_tick()
    test_f2_confident_first_fix_vs_marginal_needs_two()
    test_f3_blip_preserves_streak()
    test_f4_approach_speed_strips_noise_not_speed()

    ok = summary()
    sys.exit(0 if ok else 1)
