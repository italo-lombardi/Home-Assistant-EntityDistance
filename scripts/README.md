# Simulation scripts

Manual/live testing helpers. These talk to a **running** Home Assistant via its
REST API — they are not part of the pytest suite.

## `simulate_movement.py`

Drives the test `device_tracker` entities through movement scenarios so you can
watch Entity Distance sensors react (distance, direction, closing speed, ETA,
proximity, and the grace window).

```sh
export HA_URL=http://localhost:8123
export HA_TOKEN=<long-lived access token>
# optional overrides:
# export SIM_ENTITY_A=device_tracker.test_alice
# export SIM_ENTITY_B=device_tracker.test_bob

python3 scripts/simulate_movement.py walk     # converge on foot
python3 scripts/simulate_movement.py drive    # fast approach then park
python3 scripts/simulate_movement.py flight   # teleport → speed filter + grace
python3 scripts/simulate_movement.py blip      # brief signal loss → grace hold
python3 scripts/simulate_movement.py all
```

Each step waits ~65 s so the coordinator's 1-minute tick picks up the move.
Coordinates are generic (Dublin area) — no real user data. Re-runnable any time.

**What to watch:**
- `walk` / `drive` → `sensor.<pair>_direction` = `approaching`, distance shrinking,
  `binary_sensor.<pair>_in_proximity` turns on near the end.
- `flight` → the in-flight fix should trip the speed filter (`last_error=speed_filter`);
  with the grace window, sensors hold last value for a tick instead of flapping.
- `blip` → while the source is `unavailable`, distance / direction / in_proximity
  should **hold** their last value (grace), not go `unknown`.
