#!/usr/bin/env python3
"""Smoke test for Entity Distance v0.4.8 — shutdown-crash fix.

Reproduces/guards the crash fixed in 0.4.8:
  RuntimeError: Executor shutdown has been called
A full HA stop never unloads config entries, so the coordinator's state-change
debouncer was never cancelled; a pending debounced async_recalculate could fire
during teardown and reach Store.async_save -> run_in_executor after the event
loop's default executor had been torn down. The fix shuts the debouncer down on
EVENT_HOMEASSISTANT_STOP and early-returns from recalculate/save during teardown.

A shutdown-timing crash cannot be fully self-driven over the HTTP API — it needs
a real HA process restart (homeassistant.restart, which exits with the restart
code; NOT a config-entry reload). This script is therefore two-phase:

  Phase ARM (default): inject a coordinate change to ARM the debouncer, then
  either (a) if SMOKE_RESTART=1 is set, POST /api/services/homeassistant/restart
  to trigger the stop-with-pending-debounce window, or (b) print a manual
  "restart HA now" instruction and SKIP. Returns immediately — NO sleep, so the
  debounce timer is still pending when the stop begins.

  Phase CHECK (SMOKE_PHASE=check, run AFTER HA is back up): GET /api/error_log
  and assert 'Executor shutdown has been called' is ABSENT. The arming
  timestamp is passed back via SMOKE_SINCE (epoch seconds) so stale pre-fix log
  lines from older boots are ignored.

Usage:
    # 1. Arm + restart (opt-in auto restart):
    SMOKE_RESTART=1 python3 tests/smoke_v052.py
    # ...prints SMOKE_SINCE=<epoch>. Wait for HA to come back, then:
    SMOKE_PHASE=check SMOKE_SINCE=<epoch> python3 tests/smoke_v052.py

    # Or arm, restart HA yourself, then check:
    python3 tests/smoke_v052.py            # arms, prints manual instruction + SMOKE_SINCE
    SMOKE_PHASE=check SMOKE_SINCE=<epoch> python3 tests/smoke_v052.py

Requirements:
    - HA running at http://localhost:8123
    - Long-lived token in HA_TOKEN env var: export HA_TOKEN=<your-token>
    - entity_distance configured with device_tracker.test_alice + test_bob
"""

import json
import os
import random as _random
import sys
import time
import urllib.error
import urllib.request

HA = "http://localhost:8123"
TOKEN = os.environ.get("HA_TOKEN")
if not TOKEN:
    print("ERROR: set HA_TOKEN environment variable before running smoke tests")
    print("  export HA_TOKEN=<your-long-lived-token>")
    sys.exit(1)

HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"

CRASH_MARKER = "Executor shutdown has been called"
_LON = -6.2603
_ALICE_LAT = 53.3498
_BOB_LAT = 53.3499
_nudge = _random.randint(10000, 99999)


def api(path, method="GET", data=None, raw=False):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(f"{HA}/api{path}", headers=HEADERS, method=method, data=body)
    with urllib.request.urlopen(req, timeout=10) as r:
        payload = r.read()
        return payload.decode() if raw else json.loads(payload)


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


def section(title):
    print(f"\n{'─' * 60}\n  {title}\n{'─' * 60}")


def phase_arm() -> int:
    section("ARM: inject a state change to leave a debounce timer pending")
    since = int(time.time())
    # Inject ONCE and return immediately — do NOT sleep. The coordinator's
    # debouncer now has a pending timer; a stop started now hits the bug window.
    inject("device_tracker.test_alice", _ALICE_LAT, _LON)
    inject("device_tracker.test_bob", _BOB_LAT, _LON)
    print(f"  armed debounce at epoch {since}")

    if os.environ.get("SMOKE_RESTART") == "1":
        try:
            api("/services/homeassistant/restart", method="POST", data={})
            print(f"  {PASS}  restart requested (homeassistant.restart)")
        except urllib.error.HTTPError as e:
            # e.g. invalid-config rejection — can't restart; treat as SKIP.
            print(f"  {SKIP}  restart rejected ({e.code}); restart HA manually")
        except urllib.error.URLError:
            # Connection dropped = HA is going down, which is the expected case.
            print(f"  {PASS}  connection closed — HA is stopping")
    else:
        print(f"  {SKIP}  SMOKE_RESTART not set — restart HA now, manually")

    print("\n  NEXT: once HA is back up, run:")
    print(f"    SMOKE_PHASE=check SMOKE_SINCE={since} python3 tests/smoke_v052.py")
    print(f"\nSMOKE_SINCE={since}")
    return since


def phase_check() -> bool:
    section("CHECK: error log must not contain the executor-shutdown crash")
    since = int(os.environ.get("SMOKE_SINCE", "0"))
    try:
        log = api("/error_log", raw=True)
    except Exception as e:  # noqa: BLE001
        print(f"  {FAIL}  could not fetch /api/error_log: {e}")
        return False

    # The error log is plain text without reliable per-line timestamps across
    # all HA versions; scope by substring presence. SMOKE_SINCE is informational
    # (the arming boot) — a fresh post-fix boot's log should simply lack the
    # marker entirely.
    hits = [ln for ln in log.splitlines() if CRASH_MARKER in ln]
    ok = not hits
    mark = PASS if ok else FAIL
    print(f"  {mark}  '{CRASH_MARKER}' absent from error log"
          + (f"  [since≈{since}]" if since else ""))
    if hits:
        print("  offending lines:")
        for ln in hits[:6]:
            print(f"    {ln}")
    return ok


def main() -> int:
    phase = os.environ.get("SMOKE_PHASE", "arm")
    if phase == "check":
        return 0 if phase_check() else 1
    phase_arm()
    # Arming phase has no pass/fail of its own — it sets up the CHECK run.
    return 0


if __name__ == "__main__":
    sys.exit(main())
