# Entity Distance for Home Assistant

Track the distance between any two or more entities — people, devices, or zones — with rich sensors for direction, closing speed, ETA, and proximity detection.

## Features

- Person-to-person, person-to-zone, device-to-zone, and zone-to-zone distance tracking
- **Group tracking** — select 2–5 entities; all pairwise distances are tracked under one config entry
- **Group sensors** — for 3+ entities: Min Distance, Any In Proximity, All In Proximity
- 26 sensors per pair: distance, proximity zone, proximity zone level, proximity duration, proximity rate, proximity tracking started, last seen together, today proximity time, today zone times, direction, direction level, closing speed, ETA, GPS accuracy, last update, update count, entity state, today unaccounted time
- **Same Zone** binary sensor per pair — ON when both entities share the same named zone, OFF otherwise (never `unknown`)
- Proximity binary sensor driven by zone boundaries — select which zone triggers "In Proximity"; exit is automatically the next zone out (natural hysteresis, no redundant threshold settings)
- Direction of travel — approaching, diverging, or stationary (GPS jitter filtered)
- ETA sensor — estimated minutes until together (only when approaching)
- Closing speed sensor — convergence rate in km/h
- Today proximity time — total minutes together today, resets at midnight
- GPS accuracy and implied speed filters — reject unreliable location updates
- **HA 2026.7 compatible** — sensors stay valid when a person is home via WiFi/BT scanner (zone coordinate fallback)
- Reliability tracking — min update count in rolling window before proximity events fire
- Diagnostic sensors — GPS accuracy, last update, update count per entity
- Refresh button — triggers mobile app location update for all entities in the group
- Event-driven updates, no polling
- State persistence — proximity duration, today times, and last seen together survive HA restarts

## Lovelace Cards

Three custom cards are auto-registered on startup — no manual resource setup needed.

- **Pair Card** (`entity-distance-pair-card`) — data-focused card: distance, direction, zone, speed, ETA, proximity stats
- **Avatar Card** (`entity-distance-avatar-card`) — people-focused card with entity avatars side-by-side
- **Group Card** (`entity-distance-group-card`) — force-directed SVG graph showing all group entities as circles connected by labeled, color-coded lines; lines glow when a pair is in proximity; per-node label position and visibility configurable in the editor

## Setup

1. Install via HACS
2. Go to **Settings → Devices & Services → Add Integration**
3. Search for **Entity Distance**
4. Select 2–5 entities (person, device_tracker, sensor, or zone)
5. Configure proximity thresholds and optional filters

For a group of 3 or more entities, all pairwise distances are tracked automatically. Each pair gets its own sub-device; group-level sensors appear on the group device.

> This is an unofficial integration not affiliated with Home Assistant.
