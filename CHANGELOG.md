# Changelog

## [Unreleased]

## [0.2.0] - 2026-05-21

### Added
- **Group tracking** — select 2–5 entities in a single config entry; all pairwise distances are tracked automatically (2 entities = 1 pair, 3 = 3 pairs, 4 = 6 pairs, 5 = 10 pairs)
- Group-level binary sensors for groups with 3+ entities: Min Distance (sensor), Any In Proximity (binary sensor), All In Proximity (binary sensor)
- Per-pair sub-devices are linked to the group device in the HA device registry via `via_device`
- `CONF_ENTITIES` config key (list) replaces the old `entity_a` / `entity_b` pair; existing entries are migrated automatically on first load
- Config entry version bumped from 1 to 2; `async_migrate_entry` handles the upgrade without data loss
- `MINOR_VERSION = 1` added to satisfy HA 2024.3+ config flow requirements
- New config flow validation errors: `too_few_entities` (< 2 entities selected), `too_many_entities` (> 5 entities selected), and `duplicate_entities`
- Reverse entity-to-pairs index in coordinator for O(1) state change routing
- NaN/Infinity guard after `ha_distance()` call

### Changed
- Config flow Step 1 now uses a multi-select entity picker instead of two single-entity pickers
- Button now sends location refresh to all entities in the group (deduplicated — each device refreshed once regardless of how many pairs it appears in)
- Storage schema updated to a per-pair keyed dict (`person.alice__person.bob: {...}`) to support multiple pairs per entry
- Pair device identifiers now use entity IDs (not friendly names) to prevent orphaned devices on entity rename
- `_calc_pair` is now a sync method (removed erroneous `async` — contains no awaits)
- `any_in_proximity` and `all_in_proximity` now filter by `data_valid` before computing

### Changed (deps)
- Bump `pytest-homeassistant-custom-component` to `>=0.13.331` (HA core 2026.5.2)

## [0.1.0] - 2026-05-14

### Added
- Track distance between any two people, devices, or zones
- Sensors: distance, proximity zone, direction, approach speed, estimated arrival time
- Proximity duration — total time spent together, live and accumulated
- Proximity Rate — percentage of tracked time spent together (since tracking started)
- Today proximity time and breakdown by zone (Very Near, Near, Medium, Far, Very Far)
- Last seen together timestamp
- Proximity Tracking Started — when tracking began for this pair (set once, never resets)
- Entity state sensors — mirrors the current Home Assistant state of each tracked person (Home, Away, zone name)
- Today Unaccounted Time — how many minutes today have no GPS data
- Binary sensor: In Proximity (with hysteresis to prevent flickering)
- Button: Refresh Location — requests an immediate GPS update from both devices
- 4 automation events: enter proximity, leave proximity, update, enter (unreliable)
- Configurable proximity thresholds — customize when each zone starts and ends
- Advanced filters — GPS accuracy limit, speed sanity check, reliability requirement
- Two Lovelace cards — data-focused card and people card with avatars
- Cards auto-register as Lovelace resources on load
- Pair history resets automatically if you reconfigure with different entities
- All sensors refresh every minute even when devices don't move
- State persists across HA restarts
- 11 language translations (English, German, French, Spanish, Italian, Portuguese, Dutch, Polish, Danish, Norwegian, Swedish)

### Fixed
- Proximity duration no longer double-counts time across restarts
- Direction sensor correctly uses a 50 m stationary threshold to ignore GPS jitter
- Location refresh button works on both iOS and Android
- Sensors no longer go Unknown after reconfiguring the integration
- Update count correctly tracks per-entity, not shared between both people
