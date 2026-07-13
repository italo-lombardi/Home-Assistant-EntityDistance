# Automation Examples — Entity Distance

Practical automations built on the sensors this integration creates. Entity IDs
below use placeholder pair names like `alice_bob` — replace with your own
(the pair ID is your two entities joined by `_`, e.g. `person_alice` &
`zone_home` → `..._alice_home_...`).

Per-pair sensors referenced here:

- `sensor.<pair>_distance` — metres between the pair
- `sensor.<pair>_proximity_zone` — `very_near` / `near` / `mid` / `far` / `very_far`
- `sensor.<pair>_direction` — `approaching` / `diverging` / `stationary`
- `sensor.<pair>_approach_speed` — km/h (closing speed)
- `sensor.<pair>_estimated_arrival_time` — minutes, with an `eta_status` attribute
- `binary_sensor.<pair>_in_proximity` — ON inside the proximity zone
- `binary_sensor.<pair>_reliable` — ON when both sides have enough recent fixes
- `sensor.<pair>_today_proximity_time` — minutes spent in proximity today

---

## 1. Notify when two people come together

```yaml
automation:
  - alias: "Alice and Bob are together"
    trigger:
      - platform: state
        entity_id: binary_sensor.alice_bob_in_proximity
        to: "on"
    action:
      - service: notify.mobile_app_my_phone
        data:
          message: "Alice and Bob are now near each other."
```

## 2. Turn on the porch light when someone is approaching home

Uses `direction` so it only fires when the distance is *shrinking*, not just
when they happen to be far.

```yaml
automation:
  - alias: "Porch light on approach"
    trigger:
      - platform: state
        entity_id: sensor.alice_home_direction
        to: "approaching"
    condition:
      - condition: numeric_state
        entity_id: sensor.alice_home_distance
        below: 2000
    action:
      - service: light.turn_on
        target:
          entity_id: light.porch
```

## 3. Announce ETA when arrival is imminent

```yaml
automation:
  - alias: "Announce imminent arrival"
    trigger:
      - platform: numeric_state
        entity_id: sensor.alice_home_estimated_arrival_time
        below: 5
    condition:
      # Only when actually approaching (ETA exists), not stale/stationary.
      - condition: state
        entity_id: sensor.alice_home_estimated_arrival_time
        attribute: eta_status
        state: "approaching"
    action:
      - service: tts.google_translate_say
        target:
          entity_id: media_player.kitchen
        data:
          message: >
            Alice is about
            {{ states('sensor.alice_home_estimated_arrival_time') | int }}
            minutes away.
```

## 4. Alert when a pair drifts far apart

```yaml
automation:
  - alias: "Pair separated"
    trigger:
      - platform: state
        entity_id: sensor.alice_bob_proximity_zone
        to: "very_far"
        for: "00:10:00"
    action:
      - service: notify.mobile_app_my_phone
        data:
          message: "Alice and Bob have been far apart for 10 minutes."
```

## 5. Only act on trustworthy data

Gate any distance-based automation on the `reliable` sensor so a single noisy
GPS fix doesn't trigger it.

```yaml
automation:
  - alias: "Reliable proximity alert"
    trigger:
      - platform: state
        entity_id: binary_sensor.alice_bob_in_proximity
        to: "on"
    condition:
      - condition: state
        entity_id: binary_sensor.alice_bob_reliable
        state: "on"
    action:
      - service: notify.mobile_app_my_phone
        data:
          message: "Alice and Bob are together (confirmed)."
```

## 6. Daily time-together summary

```yaml
automation:
  - alias: "Daily together summary"
    trigger:
      - platform: time
        at: "21:00:00"
    action:
      - service: notify.mobile_app_my_phone
        data:
          message: >
            Alice and Bob spent
            {{ states('sensor.alice_bob_today_proximity_time') }} minutes
            near each other today.
```

## 7. Group-level: anyone home

For a group config (3+ entities), the group device exposes aggregate sensors.

```yaml
automation:
  - alias: "Someone arrived home"
    trigger:
      - platform: state
        entity_id: binary_sensor.entity_distance_family_any_in_proximity
        to: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.hallway
```

---

**Tip:** because sensors keep their last value for a short grace window during
brief GPS gaps, prefer `for:` durations on triggers where a momentary blip
shouldn't fire the automation — and gate on `binary_sensor.<pair>_reliable`
when data confidence matters.
