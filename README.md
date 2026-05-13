# Entity Distance for Home Assistant

<a href="https://github.com/italo-lombardi/Home-Assistant-EntityDistance/releases"><img src="https://img.shields.io/github/v/release/italo-lombardi/Home-Assistant-EntityDistance" alt="GitHub Release"></a>
<a href="https://github.com/hacs/integration"><img src="https://img.shields.io/badge/HACS-Custom-41BDF5.svg" alt="HACS Custom"></a>
<a href="https://www.home-assistant.io/"><img src="https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg" alt="Home Assistant"></a>
<a href="https://github.com/italo-lombardi/Home-Assistant-EntityDistance/blob/main/LICENSE"><img src="https://img.shields.io/github/license/italo-lombardi/Home-Assistant-EntityDistance?logo=gnu&logoColor=white" alt="License"></a>

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=italo-lombardi&repository=Home-Assistant-EntityDistance&category=integration)
[![Add to Home Assistant](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=entity_distance)

Track the distance between any two entities — people, devices, or zones — with sensors for direction, closing speed, ETA, and proximity detection.

---

## Features

- **Person-to-person, person-to-zone, device-to-zone, zone-to-zone** — any combination of `person`, `device_tracker`, `sensor`, or `zone` entities
- **16 sensors per pair** — distance, proximity zone, proximity zone level, proximity duration, last seen together, today proximity time, direction, closing speed, ETA, GPS accuracy, last update, update frequency, data staleness (per entity)
- **Proximity binary sensor** — ON/OFF with configurable entry/exit hysteresis to prevent flickering
- **Direction of travel** — approaching, diverging, or stationary
- **ETA** — estimated minutes until together, only when approaching
- **Closing speed** — convergence rate in km/h
- **Today proximity time** — total minutes together today, resets at midnight
- **GPS accuracy filter** — reject updates with poor GPS fix quality
- **Speed filter** — reject physically implausible location jumps (e.g. GPS teleports)
- **Reliability tracking** — require consistent updates before proximity events fire
- **4 HA events** — fire automations without polling
- **Diagnostic sensors** — GPS accuracy, last update, update frequency, staleness per tracked entity
- **Refresh button** — force immediate mobile app location update
- **Multiple pairs** — each pair gets its own HA device; add as many as needed
- **Vincenty distance** — uses HA's built-in ellipsoidal distance calculation, more accurate than Haversine

---

## Installation

### HACS (Recommended)

1. Click the badge above or open **HACS → Integrations → Custom repositories**
2. Add `https://github.com/italo-lombardi/Home-Assistant-EntityDistance` with category **Integration**
3. Install **Entity Distance**
4. Restart Home Assistant

### Manual

1. Copy `custom_components/entity_distance/` into your HA `config/custom_components/` directory
2. Restart Home Assistant

---

## Configuration

Go to **Settings → Devices & Services → Add Integration → Entity Distance**.

### Step 1: Entity Pair

Select the two entities to track. Supported types: `person`, `device_tracker`, `sensor`, `zone`.

| Field | Description |
|-------|-------------|
| First entity | First entity to track |
| Second entity | Second entity to track — must be different from the first |

<!-- screenshot: step 1 entity pair -->

### Step 2: Proximity Settings

| Field | Default | Description |
|-------|---------|-------------|
| Nearby threshold (m) | 200 | Entities must be closer than this to trigger a proximity event |
| Away threshold (m) | 500 | Entities must move further than this before proximity ends (hysteresis) |
| Location update delay (s) | 10 | Seconds to wait before processing a location update — smooths GPS jitter |
| Configure proximity zone thresholds | Off | Turn on to customize Very Near / Near / Mid / Far zone distances |
| Configure advanced filters | Off | Turn on to configure GPS accuracy, speed, and reliability filters |

<!-- screenshot: step 2 proximity settings -->

### Step 3: Zone Thresholds (optional)

Only shown when "Configure proximity zone thresholds" is enabled in Step 2.

| Field | Default | Description |
|-------|---------|-------------|
| Very Near threshold (m) | 100 | Distance at or below which entities are Very Near |
| Near threshold (m) | 500 | Distance at or below which entities are Near |
| Mid threshold (m) | 2000 | Distance at or below which entities are Mid |
| Far threshold (m) | 10000 | Distance at or below which entities are Far (beyond this is Very Far) |

Thresholds must be strictly increasing: Very Near < Near < Mid < Far.

<!-- screenshot: step 3 zone thresholds -->

### Step 4: Advanced Filters (optional)

Only shown when "Configure advanced filters" is enabled in Step 2.

| Field | Default | Description |
|-------|---------|-------------|
| Max GPS inaccuracy (m) | 150 | Ignore updates where GPS error exceeds this radius (0 = off) |
| Max speed filter (km/h) | 1000 | Ignore updates implying movement faster than this — catches GPS teleports, allows flights (0 = off) |
| Only trigger when data is reliable | Off | Require several consistent updates before firing proximity events |
| Updates needed to be reliable | 3 | Consecutive updates required before data is considered reliable |

<!-- screenshot: step 4 advanced filters -->

All settings can be changed after setup via **Configure** on the integration card.

---

## Entities

Each configured pair creates one HA device with 19 entities.

### Sensors

| Entity | Description | Device Class |
|--------|-------------|--------------|
| Distance | Distance between entities in meters | `distance` |
| Proximity Zone | Very Near / Near / Medium / Far / Very Far | `enum` |
| Proximity Zone Number | Numeric zone level: 1 (Very Near) to 5 (Very Far) | — |
| Proximity Duration | Minutes currently in proximity (live, includes current session) | `duration` |
| Last Seen Together | Timestamp of last proximity entry | `timestamp` |
| Today Proximity Time | Total minutes together today — resets at midnight | `duration` |
| Direction | Approaching / Diverging / Stationary | `enum` |
| Approach Speed | Convergence rate in km/h | `speed` |
| Estimated Arrival Time | Minutes until together (only when approaching) | `duration` |
| GPS Accuracy (Name A) | GPS fix accuracy of entity A in meters | `distance` |
| GPS Accuracy (Name B) | GPS fix accuracy of entity B in meters | `distance` |
| Last Update (Name A) | Timestamp of last location change for entity A | `timestamp` |
| Last Update (Name B) | Timestamp of last location change for entity B | `timestamp` |
| Update Frequency (Name A) | Location updates/min over last 5-min window | — |
| Update Frequency (Name B) | Location updates/min over last 5-min window | — |
| Location Age (Name A) | Seconds since last update from entity A | `duration` |
| Location Age (Name B) | Seconds since last update from entity B | `duration` |

> GPS Accuracy, Last Update, Update Frequency, and Location Age are diagnostic sensors — collapsed by default in the HA UI. Sensor names use the entities' friendly names (e.g. "GPS Accuracy (Italo)") instead of generic A/B labels.

### Binary Sensor

| Entity | Description | Device Class |
|--------|-------------|--------------|
| In Proximity | ON when within nearby distance, OFF when beyond away distance | `presence` |

### Button

| Entity | Description |
|--------|-------------|
| Refresh Location | Triggers mobile app `update_sensor_states` for both entities |

<!-- screenshot: device card with all entities -->

---

## Proximity Zone Thresholds

Default thresholds (configurable via **Configure** → **Configure proximity zone thresholds**):

| Zone | Default Distance | Level |
|------|-----------------|-------|
| Very Near | ≤ 100 m | 1 |
| Near | ≤ 500 m | 2 |
| Medium | ≤ 2 km | 3 |
| Far | ≤ 10 km | 4 |
| Very Far | > 10 km | 5 |

The **Proximity Zone Level** sensor exposes the same information as a number (1–5), useful for automations that compare or threshold on zone level without working with strings.

<!-- screenshot: zone thresholds config step -->

---

## Events

Four events are fired on the HA event bus:

| Event | Fired when |
|-------|------------|
| `entity_distance_enter` | Entities enter proximity (reliable data) |
| `entity_distance_enter_unreliable` | Entities enter proximity (unreliable data) |
| `entity_distance_leave` | Entities leave proximity |
| `entity_distance_update` | Location updated while proximity state unchanged |

### Event payload

```yaml
entity_a: person.alice
entity_b: person.bob
distance_m: 320.5
entry_threshold_m: 200
exit_threshold_m: 500
reliable: true
direction: approaching
closing_speed_kmh: 12.3
```

---

## Automation Ideas

### Notify when entities are nearby

```yaml
automation:
  - alias: "Notify when nearby"
    trigger:
      - platform: state
        entity_id: binary_sensor.entity_distance_alice_bob_proximity
        to: "on"
    action:
      - service: notify.mobile_app
        data:
          title: "Alice and Bob are nearby"
          message: >
            {{ states('sensor.entity_distance_alice_bob_distance') }} m apart
```

### Notify when approaching

```yaml
automation:
  - alias: "Notify on approach"
    trigger:
      - platform: state
        entity_id: sensor.entity_distance_alice_bob_direction
        to: "approaching"
    action:
      - service: notify.mobile_app
        data:
          title: "Someone is approaching"
          message: >
            ETA: {{ states('sensor.entity_distance_alice_bob_eta') }} min
```

### Use in an automation with event trigger

```yaml
automation:
  - alias: "React to proximity enter"
    trigger:
      - platform: event
        event_type: entity_distance_enter
        event_data:
          entity_a: person.alice
          entity_b: person.bob
    action:
      - service: notify.mobile_app
        data:
          title: "Together"
          message: >
            Distance: {{ trigger.event.data.distance_m | round(0) }} m
```

---

## Lovelace Card

The integration ships a custom card — `entity-distance-card` — automatically registered as a Lovelace resource when the integration loads.

### Minimal config

```yaml
type: custom:entity-distance-card
entity_a: person.alice
entity_b: person.bob
```

### Full config

```yaml
type: custom:entity-distance-card
entity_a: person.alice
entity_b: person.bob
entry_id: abc123def456  # optional: explicit config entry ID
```

The card shows distance, direction, proximity zone, closing speed, ETA, and time together today.

If auto-registration fails (e.g. YAML-only Lovelace mode), add manually:

```yaml
resources:
  - url: /entity_distance/entity-distance-card.js?0.1.0-alpha.1
    type: module
```

<!-- screenshot: lovelace card -->

---

## Zone Support

Zones (`zone.*`) are supported as either entity in a pair:

- Zones use `latitude`/`longitude` attributes — GPS accuracy and speed filters are not applied to zones
- Person-to-zone: direction and ETA work normally
- Zone-to-zone: distance is static; direction always stationary

---

## Contributing

Contributions welcome!

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit with clear messages
4. Open a Pull Request against `main`

### Development Setup

```bash
git clone https://github.com/italo-lombardi/Home-Assistant-EntityDistance.git
python -m venv venv
source venv/bin/activate
pip install -r requirements_test.txt
```

### Running Tests

```bash
python -m pytest tests/ -v
```

### Guidelines

- Follow [Home Assistant integration development guidelines](https://developers.home-assistant.io/)
- Add translations for any new user-facing strings
- Write tests for new functionality
- Keep PRs focused — one feature or fix per PR

---

## Inspiration

Inspired by [HA-Member-Adjacency](https://github.com/1bobby-git/HA-Member-Adjacency). Entity Distance is a full rewrite with direction/speed/ETA sensors, diagnostic entities, full test coverage, CI/CD, and HACS submission.

---

## License

This project is licensed under the GNU General Public License v3.0. See the [LICENSE](LICENSE) file for details.

> This is an unofficial integration not affiliated with Home Assistant.
