#!/usr/bin/env python3
"""Smoke tests for Entity Distance v0.4.7 — two derived trigger-worthy attributes.

Covered:
  A1  last_seen_together.apart_duration_s — seconds since last together while
      apart; 0.0 while together. Lets a "reunited after N hours" automation fire
      on numeric_state of the attribute (a gap predicate the bare timestamp
      state can't express).
  A2  min_distance.closest_pair / closest_pair_entities — which pair owns the
      group minimum (no state of its own). Only present for 3+ entity groups.

A1 runs against the standard 2-entity fixture (device_tracker.test_alice +
device_tracker.test_bob). A2 needs a 3+ entity group; it auto-skips (reports
SKIP, not FAIL) when the min_distance sensor is absent, so the file is safe to
run against the standard 2-entity config.

Usage:
    python3 tests/smoke_v051.py

Requirements:
    - HA running at http://localhost:8123
    - Long-lived token in HA_TOKEN env var: export HA_TOKEN=<your-token>
    - entity_distance configured with device_tracker.test_alice + device_tracker.test_bob
    - Integration slug: test_alice_test_bob
    - A2 only: a 3+ entity group whose min_distance sensor entity_id is passed
      via MIN_DISTANCE_ENTITY env var (else A2 skips)
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
# A2: optional 3+ entity group's min_distance sensor entity_id.
MIN_DISTANCE_ENTITY = os.environ.get("MIN_DISTANCE_ENTITY")
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

results: list[tuple[str, bool, str]] = []
_nudge = _random.randint(10000, 99999)

_ALICE_LAT = 53.3498
_BOB_LAT = 53.3499
_FAR_LAT = 54.0000  # ~72 km away → well outside proximity
_LON = -6.2603
UNSET = ("unknown", "unavailable")


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


def inject_pair(alice_lat, bob_lat, rounds=2):
    for _ in range(rounds):
        inject("device_tracker.test_alice", alice_lat, _LON)
        inject("device_tracker.test_bob", bob_lat, _LON)
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


def skip(name, detail=""):
    print(f"  {SKIP}  {name}" + (f"  [{detail}]" if detail else ""))


def section(title):
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── A1: last_seen_together.apart_duration_s ────────────────────────────────────


def test_apart_duration_zero_while_together():
    """Together (within proximity) → apart_duration_s must be 0.0."""
    section("A1: together → apart_duration_s == 0.0")

    inject_pair(_ALICE_LAT, _BOB_LAT)  # ~11 m apart → in proximity

    s = state(f"sensor.{SLUG}_last_seen_together")
    attrs = s.get("attributes", {}) if s else {}
    check(
        "apart_duration_s is 0.0 while together",
        "apart_duration_s" in attrs and float(attrs["apart_duration_s"]) == 0.0,
        str(attrs.get("apart_duration_s", "missing")),
    )


def test_apart_duration_grows_while_apart():
    """Move far apart, wait, re-poll: apart_duration_s must become positive and grow."""
    section("A1: apart → apart_duration_s positive and increasing")

    # Pull Bob ~72 km away so the pair leaves proximity; last_seen_together freezes.
    inject_pair(_ALICE_LAT, _FAR_LAT)

    # Proximity exit is debounced/confirmed over a couple of coordinator ticks, so
    # apart_duration_s can still read 0.0 on the first poll right after the move.
    # Poll (bounded) until it goes positive before asserting it then grows.
    first = None
    for _ in range(6):
        s1 = state(f"sensor.{SLUG}_last_seen_together")
        a1 = s1.get("attributes", {}) if s1 else {}
        v = float(a1["apart_duration_s"]) if "apart_duration_s" in a1 else None
        if v is not None and v > 0.0:
            first = v
            break
        time.sleep(7)
    check(
        "apart_duration_s positive once apart",
        first is not None and first > 0.0,
        str(first),
    )
    if first is None:
        return  # never went positive → nothing to compare against; FAIL recorded

    time.sleep(10)
    # apart_duration_s is a read-time @property (dt_util.now() - last_seen_together),
    # so a second poll alone already advances it; the extra inject keeps the pair apart
    # so last_seen_together does not re-stamp between reads.
    inject("device_tracker.test_alice", _ALICE_LAT, _LON)
    time.sleep(7)

    s2 = state(f"sensor.{SLUG}_last_seen_together")
    a2 = s2.get("attributes", {}) if s2 else {}
    second = float(a2["apart_duration_s"]) if "apart_duration_s" in a2 else None
    check(
        "apart_duration_s grew after waiting",
        first is not None and second is not None and second > first,
        f"{first} → {second}",
    )


# ── A2: min_distance.closest_pair (3+ entity groups only) ──────────────────────


def test_closest_pair_present():
    """min_distance sensor on a 3+ entity group exposes closest_pair + entities."""
    section("A2: min_distance.closest_pair present (3+ entity group)")

    if not MIN_DISTANCE_ENTITY:
        skip(
            "closest_pair — no 3+ entity group configured",
            "set MIN_DISTANCE_ENTITY to a group's sensor.<group>_min_distance",
        )
        return

    s = state(MIN_DISTANCE_ENTITY)
    if s is None or s["state"] in UNSET:
        skip("closest_pair — min_distance sensor unavailable", s["state"] if s else "missing")
        return

    attrs = s.get("attributes", {})
    check(
        "closest_pair is a non-empty 'A & B' string",
        isinstance(attrs.get("closest_pair"), str) and " & " in attrs["closest_pair"],
        str(attrs.get("closest_pair", "missing")),
    )
    ents = attrs.get("closest_pair_entities")
    check(
        "closest_pair_entities is a 2-entity list",
        isinstance(ents, list) and len(ents) == 2,
        str(ents),
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
    print("\nEntity Distance v0.4.7 Smoke Tests — apart_duration_s + closest_pair attributes")
    print(f"HA: {HA}  slug: {SLUG}\n")

    test_apart_duration_zero_while_together()
    test_apart_duration_grows_while_apart()
    test_closest_pair_present()

    ok = summary()
    sys.exit(0 if ok else 1)
