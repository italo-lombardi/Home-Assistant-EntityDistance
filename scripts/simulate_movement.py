#!/usr/bin/env python3
"""Drive Entity Distance test device_trackers through movement scenarios.

Read-only-safe simulator for manual/live testing against a running Home Assistant.
Moves `device_tracker.*` (and `person.*` via their tracker) test entities through
realistic patterns so you can watch the distance / direction / proximity / grace
behaviour react. Nothing here is a unit test — it talks to a live HA REST API.

Usage:
    export HA_URL=http://localhost:8123
    export HA_TOKEN=<long-lived token>
    python3 scripts/simulate_movement.py walk
    python3 scripts/simulate_movement.py drive
    python3 scripts/simulate_movement.py flight
    python3 scripts/simulate_movement.py blip      # grace-window test
    python3 scripts/simulate_movement.py all

Scenarios are declarative (SCENARIOS dict) so they can be re-run and extended.
Coordinates are generic (Dublin area) — no real user data.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

HA_URL = os.environ.get("HA_URL", "http://localhost:8123").rstrip("/")
HA_TOKEN = os.environ.get("HA_TOKEN", "")

# Two movers used by the scenarios. Override via env if your test entities differ.
A = os.environ.get("SIM_ENTITY_A", "device_tracker.test_alice")
B = os.environ.get("SIM_ENTITY_B", "device_tracker.test_bob")

# Generic anchor (Dublin city centre) — NOT real user data.
BASE_LAT, BASE_LON = 53.3498, -6.2603


def _set(entity_id: str, state: str, lat=None, lon=None, accuracy=10) -> None:
    attrs: dict = {}
    if lat is not None:
        attrs = {"latitude": lat, "longitude": lon, "gps_accuracy": accuracy}
    body = {"state": state, "attributes": attrs}
    req = urllib.request.Request(
        f"{HA_URL}/api/states/{entity_id}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as e:  # pragma: no cover - live-only
        print(f"  ! {entity_id}: HTTP {e.code}")


def _gps(entity_id: str, lat: float, lon: float, accuracy: int = 10) -> None:
    _set(entity_id, "not_home", lat, lon, accuracy)


def _step(msg: str, secs: float = 65.0) -> None:
    # Default dwell exceeds the 60s coordinator tick so each step is picked up.
    print(f"  {msg} (waiting {secs:.0f}s for a tick)")
    time.sleep(secs)


def walk() -> None:
    """Two people converge on foot: ~1.4 m/s, distance shrinks → approaching → together."""
    print("Scenario: WALK toward each other")
    # Start ~600 m apart along a line.
    for i in range(7):
        frac = i / 6  # 0 → 1
        _gps(A, BASE_LAT, BASE_LON - 0.004 * (1 - frac))
        _gps(B, BASE_LAT, BASE_LON + 0.004 * (1 - frac))
        _step(f"step {i + 1}/7 — closing", 65)


def drive() -> None:
    """One drives toward the other on a highway: ~25 m/s, fast approach, then stop."""
    print("Scenario: DRIVE toward, then park")
    for i in range(5):
        frac = i / 4
        _gps(A, BASE_LAT + 0.02 * (1 - frac), BASE_LON, accuracy=8)
        _gps(B, BASE_LAT, BASE_LON)
        _step(f"leg {i + 1}/5 — driving in", 65)
    _step("parked together", 65)


def flight() -> None:
    """Intercontinental jump: single huge position change → should trip speed filter
    (teleport) and, with the grace window, hold last value rather than flap."""
    print("Scenario: FLIGHT (teleport)")
    _gps(A, BASE_LAT, BASE_LON)
    _gps(B, BASE_LAT, BASE_LON + 0.001)
    _step("boarding — together", 65)
    # ~1600 km jump in one tick.
    _gps(A, 40.4168, -3.7038)  # Madrid
    _step("in-flight fix (teleport) — expect speed_filter + grace hold", 65)
    _gps(A, 40.4168, -3.7038)
    _step("landed — recovering", 65)


def blip() -> None:
    """Brief signal loss while together: source goes unavailable for one tick.
    With the grace window, distance/direction/in_proximity should HOLD, not flip
    to unknown."""
    print("Scenario: BLIP (grace-window test)")
    _gps(A, BASE_LAT, BASE_LON)
    _gps(B, BASE_LAT, BASE_LON + 0.0002)  # ~15 m apart, in proximity
    _step("together, valid", 65)
    _set(A, "unavailable")  # signal loss
    _step("source unavailable — grace should HOLD last value (not unknown)", 65)
    _gps(A, BASE_LAT, BASE_LON)  # recover
    _step("recovered", 65)


SCENARIOS = {"walk": walk, "drive": drive, "flight": flight, "blip": blip}


def main() -> int:
    if not HA_TOKEN:
        print("Set HA_TOKEN (and optionally HA_URL). Aborting.")
        return 1
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    names = list(SCENARIOS) if which == "all" else [which]
    for name in names:
        fn = SCENARIOS.get(name)
        if not fn:
            print(f"Unknown scenario '{name}'. Options: {', '.join(SCENARIOS)}, all")
            return 1
        fn()
    print("Done. Inspect the entity_distance sensors in HA.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
