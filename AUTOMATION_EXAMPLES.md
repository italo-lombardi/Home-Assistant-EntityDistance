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

## 8. Alert when two people are on different floors

Fires when the elevation difference exceeds 30 m (safe GPS noise margin)
and they are close horizontally. Requires mobile app GPS on both devices.

```yaml
automation:
  - alias: "Alice and Bob on different floors"
    trigger:
      - platform: state
        entity_id: binary_sensor.alice_bob_same_altitude
        to: "off"
        for:
          seconds: 30
    condition:
      - condition: numeric_state
        entity_id: sensor.alice_bob_distance
        below: 100          # close horizontally
      - condition: template
        value_template: >
          {{ state_attr('sensor.alice_bob_elevation_difference', 'altitude_a_m') is not none
             and state_attr('sensor.alice_bob_elevation_difference', 'altitude_b_m') is not none }}
    action:
      - service: notify.mobile_app_alice
        data:
          message: >
            Bob is {{ states('sensor.alice_bob_elevation_difference') | float | abs | round(0) }} m
            {{ 'above' if states('sensor.alice_bob_elevation_difference') | float < 0 else 'below' }} you.
```

## 9. Notify when two people reach the same floor

```yaml
automation:
  - alias: "Alice and Bob reunited on same floor"
    trigger:
      - platform: state
        entity_id: binary_sensor.alice_bob_same_altitude
        to: "on"
        for:
          seconds: 10
    condition:
      - condition: state
        entity_id: binary_sensor.alice_bob_in_proximity
        state: "on"
    action:
      - service: notify.mobile_app_alice
        data:
          message: "Bob is on your floor (within 5 m altitude)."
```

## 10. Gate an automation on altitude data being available

Not all entities provide altitude. Check before acting on altitude sensors.

```yaml
automation:
  - alias: "Floor-aware meeting reminder"
    trigger:
      - platform: time
        at: "09:00:00"
    condition:
      # Only run if both entities have valid altitude data
      - condition: not
        conditions:
          - condition: state
            entity_id: sensor.alice_bob_elevation_difference
            state: "unknown"
      - condition: state
        entity_id: binary_sensor.alice_bob_same_altitude
        state: "off"
    action:
      - service: notify.mobile_app_alice
        data:
          message: >
            Good morning! Alice is
            {{ (states('sensor.alice_bob_elevation_difference') | float | abs | round(0)) }} m
            {{ 'above' if states('sensor.alice_bob_elevation_difference') | float < 0 else 'below' }}
            Bob. Head to floor {{ 'B' if states('sensor.alice_bob_elevation_difference') | float < 0 else 'above' }}.
```

> **GPS vertical accuracy:** Consumer GPS altitude is ±10–30 m. Use thresholds ≥ 30 m
> in automations to avoid false triggers. The `Same Altitude` binary sensor defaults to
> a 5 m threshold — increase via **Configure → Advanced Filters → Same altitude threshold**
> if you see false positives.

---

## 11. Notify when someone starts moving (speed threshold)

Uses GPS Speed to detect when a tracked person starts traveling — more reliable than
zone exit alone (catches movement before a zone boundary is crossed).

```yaml
automation:
  - alias: "Alice started moving"
    trigger:
      - platform: numeric_state
        entity_id: sensor.alice_bob_gps_speed_alice
        above: 5          # km/h — walking threshold
        for:
          seconds: 30     # debounce: sustained movement, not a GPS blip
    action:
      - service: notify.mobile_app_bob
        data:
          message: "Alice is on the move ({{ states('sensor.alice_bob_gps_speed_alice') | round(0) }} km/h)."
```

## 12. Detect vehicle vs. on-foot travel

GPS Speed bands: walking ≤ 7 km/h, cycling ≤ 25 km/h, driving > 25 km/h.

```yaml
automation:
  - alias: "Alice is driving home"
    trigger:
      - platform: numeric_state
        entity_id: sensor.alice_bob_gps_speed_alice
        above: 25
        for:
          seconds: 60
    condition:
      - condition: numeric_state
        entity_id: sensor.alice_bob_distance
        below: 10000      # within 10 km of home
      - condition: state
        entity_id: binary_sensor.alice_bob_in_proximity
        state: "off"
    action:
      - service: notify.mobile_app_bob
        data:
          message: "Alice is driving — ETA {{ states('sensor.alice_bob_eta') | round(0) }} min."
```

## 13. Alert when GPS fix quality is poor before acting on altitude

Gate altitude-based automations on vertical accuracy to avoid false triggers.

```yaml
automation:
  - alias: "Floor-aware meeting — only when GPS is accurate"
    trigger:
      - platform: state
        entity_id: binary_sensor.alice_bob_same_altitude
        to: "off"
        for:
          seconds: 20
    condition:
      # Both devices have good vertical fix
      - condition: numeric_state
        entity_id: sensor.alice_bob_gps_vertical_accuracy_alice
        below: 20         # metres
      - condition: numeric_state
        entity_id: sensor.alice_bob_gps_vertical_accuracy_bob
        below: 20
      - condition: state
        entity_id: binary_sensor.alice_bob_in_proximity
        state: "on"
    action:
      - service: notify.mobile_app_alice
        data:
          message: >
            You and Bob are on different floors
            ({{ states('sensor.alice_bob_elevation_difference') | float | abs | round(0) }} m apart vertically).
```

---

**Tip:** because sensors keep their last value for a short grace window during
brief GPS gaps, prefer `for:` durations on triggers where a momentary blip
shouldn't fire the automation — and gate on `binary_sensor.<pair>_reliable`
when data confidence matters.
