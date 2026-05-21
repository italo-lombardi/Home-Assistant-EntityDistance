# Entity Distance for Home Assistant

Track the distance between any two or more entities — people, devices, or zones — with rich sensors for direction, closing speed, ETA, and proximity detection.

## Features

- Person-to-person, person-to-zone, device-to-zone, and zone-to-zone distance tracking
- **Group tracking** — select 2–5 entities; all pairwise distances are tracked under one config entry
- **Group sensors** — for 3+ entities: Min Distance, Any In Proximity, All In Proximity
- 26 sensors per pair: distance, proximity zone, proximity zone level, proximity duration, proximity rate, proximity tracking started, last seen together, today proximity time, today zone times, direction, direction level, closing speed, ETA, GPS accuracy, last update, update count, entity state, today unaccounted time
- Proximity binary sensor with configurable entry/exit hysteresis thresholds
- Direction of travel — approaching, diverging, or stationary (GPS jitter filtered)
- ETA sensor — estimated minutes until together (only when approaching)
- Closing speed sensor — convergence rate in km/h
- Today proximity time — total minutes together today, resets at midnight
- GPS accuracy and implied speed filters — reject unreliable location updates
- Reliability tracking — min update count in rolling window before proximity events fire
- 4 HA events — `entity_distance_enter`, `entity_distance_leave`, `entity_distance_update`, `entity_distance_enter_unreliable`
- Diagnostic sensors — GPS accuracy, last update, update count per entity
- Refresh button — triggers mobile app location update for all entities in the group
- Event-driven updates, no polling

## Setup

1. Install via HACS
2. Go to **Settings → Devices & Services → Add Integration**
3. Search for **Entity Distance**
4. Select 2–5 entities (person, device_tracker, sensor, or zone)
5. Configure proximity thresholds and optional filters

For a group of 3 or more entities, all pairwise distances are tracked automatically. Each pair gets its own sub-device; group-level sensors appear on the group device.

> This is an unofficial integration not affiliated with Home Assistant.
