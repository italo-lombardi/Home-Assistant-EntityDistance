# Entity Distance for Home Assistant

Track the distance between any two entities — people, devices, or zones — with rich sensors for direction, closing speed, ETA, and proximity detection.

## Features

- Person-to-person, person-to-zone, device-to-zone, and zone-to-zone distance tracking
- 16 sensors per pair: distance, proximity zone, proximity duration, last seen together, today proximity time, direction, closing speed, ETA, GPS accuracy, last update, update frequency, and data staleness
- Proximity binary sensor with configurable entry/exit hysteresis thresholds
- Direction of travel — approaching, diverging, or stationary (GPS jitter filtered)
- ETA sensor — estimated minutes until together (only when approaching)
- Closing speed sensor — convergence rate in km/h
- Today proximity time — total minutes together today, resets at midnight
- GPS accuracy and implied speed filters — reject unreliable location updates
- Reliability tracking — min update count in rolling window before proximity events fire
- 4 HA events — `entity_distance_enter`, `entity_distance_leave`, `entity_distance_update`, `entity_distance_enter_unreliable`
- Diagnostic sensors — GPS accuracy, last update, update frequency, data staleness per entity
- Refresh button — triggers mobile app location update
- Multiple pairs — add as many entity pairs as needed, each with its own device and sensors
- Event-driven updates, no polling

## Setup

1. Install via HACS
2. Go to **Settings → Devices & Services → Add Integration**
3. Search for **Entity Distance**
4. Select two entities (person, device_tracker, sensor, or zone)
5. Configure proximity thresholds and optional filters

> This is an unofficial integration not affiliated with Home Assistant.
