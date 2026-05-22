# Changelog

## [Unreleased]

## [0.2.1] - upcoming

### Added
- **Group Card** (`entity-distance-group-card`) — force-directed SVG graph showing all group entities as circles with labeled connecting lines
  - Lines colored by proximity zone; thicker with glow effect when a pair is in proximity
  - Per-line labels: distance and/or zone text independently configurable per pair
  - Direction arrow on each line (↑ diverging, ↓ approaching, • stationary); hidden when both distance and zone labels are disabled
  - Grid-based initial node layout by entity count: 2 = vertical pair, 3 = triangle, 4 = 2×2, 5 = 3-row with center middle node
  - Adaptive label placement: entity name + state above circle for top-row nodes, below for bottom-row nodes
  - Background rectangles behind text labels to prevent line overlap
  - `fixed_layout` option: equal spacing regardless of real distance
  - Per-entity hide toggle in editor (eye icon) — hidden entities and all their connecting lines are removed from the graph
  - Badge: "X of N pairs in proximity" counting only visible pairs
  - `pair_settings` per-pair config keyed by sorted entity ID pair (`"entity_a,entity_b"`)
  - Tap a line to open the HA more-info panel for that pair's distance sensor
  - Editor: group selector dropdown, entity order list with ↑/↓ reorder and hide toggle, title field, equal spacing checkbox, per-pair distance/zone label toggles
  - Auto-discovers available groups from hass.states in the visual editor
  - `ResizeObserver` ensures correct width in the HA sections layout
  - Idle animation: slow node drift for 6 s after last state update

### Fixed
- Accuracy filter and speed filter no longer leave `data_valid = True` after rejecting a GPS reading — both now call `_invalidate()` so downstream sensors correctly reflect unavailable data
- Proximity duration sensor no longer returns `None` when `data_valid` is `False` but tracking has started — gates on `proximity_tracking_started` instead
- Config flow now rejects equal entry/exit threshold values (previously only rejected exit < entry, allowing a deadlock where entry could never be exited)
- Resync hold now marks `data_valid = False` while the hold is active — prevents stale data from appearing valid to sensors during the silence window
- `UpdateCountSensor` returned stale count after 30-min window expired — now returns `0` when window has elapsed (`sensor.py`)
- Pair Card diagnostics showed full device-prefixed label ("Dercy & Italo GPS Accuracy") instead of short metric label — labels are now hardcoded, `friendly_name` parsing removed
- Pair Card and Avatar Card pair discovery used v0.1.0 `sensor.entity_distance_` prefix — now discovers pairs via `entity_a` attribute presence; all entity ID lookups use `sensor.${slug}_` pattern
- Entity state badges overlapped the divider line below the hero row — added top padding to `.entity-states`
- Lovelace resource updater skipped non-`ResourceStorageCollection` setups — added fallback direct assignment
- Stale Lovelace resources from renamed cards (`entity-distance-card.js`, `entity-distance-people-card.js`) now auto-purged on startup
- Group card blank in `sections` layout — `ResizeObserver` now triggers layout after real card width is known
- `shouldUpdate` in Pair Card and Avatar Card accessed `old.states[id]` without optional chaining — could throw on first render
- `last_seen_together` now records when proximity **ends** (exit) rather than when it begins (entry) — "Last seen together" now means the last completed together session; Pair Card shows "Together now" while `in_proximity` is on
- Proximity duration sensor no longer resets to near-zero after HA restart — `proximity_since` is now persisted and restored, so an active session continues accumulating correctly across restarts
- Pair Card "Proximity duration since" timestamp now includes time-of-day, not just date
- Pair Card speed stat box label now reads "Diverging speed" when entities are moving apart instead of "Approach speed"
- `datetime.fromtimestamp` in resync hold replaced with `now + timedelta(seconds=...)` for timezone consistency
- `except Exception` in `button.py` now carries `# noqa: BLE001` suppression comment

### Changed
- `TodayZoneTimeSensor` exposes `range_from_m` / `range_to_m` state attributes so users can see the distance bounds of each zone bucket
- Proximity duration and proximity rate stat boxes now share one row when both are enabled
- Lovelace cards renamed: `entity-distance-card` → `entity-distance-pair-card`, `entity-distance-people-card` → `entity-distance-avatar-card`; JS files, `__init__.py` constants, and README updated accordingly
- Group card badge shows "X of N pairs in proximity" instead of generic "In Proximity" label
- Card versions bumped to `0.2.0`; console log now includes `— github.com/italo-lombardi` suffix

## [0.2.1b7] - 2026-05-22

### Fixed
- Accuracy filter and speed filter no longer leave `data_valid = True` after rejecting a GPS reading — both now call `_invalidate()` so downstream sensors correctly reflect unavailable data
- Proximity duration sensor no longer returns `None` when `data_valid` is `False` but tracking has started — gates on `proximity_tracking_started` instead
- Config flow now rejects equal entry/exit threshold values (previously only rejected exit < entry, allowing a deadlock where entry could never be exited)
- Resync hold now marks `data_valid = False` while the hold is active — prevents stale data from appearing valid to sensors during the silence window

## [0.2.0] - 2026-05-21

> **Breaking change:** v0.2.0 is not compatible with v0.1.0 config entries. Delete and recreate all Entity Distance integrations after upgrading.

### Added
- **Group tracking** — select 2–5 entities in a single config entry; all pairwise distances are tracked automatically (2 entities = 1 pair, 3 = 3 pairs, 4 = 6 pairs, 5 = 10 pairs)
- Group-level sensors for groups with 3+ entities: Min Distance (sensor), Any In Proximity (binary sensor), All In Proximity (binary sensor)
- Per-pair sub-devices linked to the group device in the HA device registry via `via_device`
- `CONF_ENTITIES` config key (list) replaces the old `entity_a` / `entity_b` pair
- `MINOR_VERSION = 1` added to satisfy HA 2024.3+ config flow requirements
- New config flow validation errors: `too_few_entities`, `too_many_entities` (> 5 entities), `duplicate_entities`
- Reverse entity-to-pairs index in coordinator for O(1) state change routing
- NaN/Infinity guard after `ha_distance()` call
- Domain priority ordering for entity pairs: `person > device_tracker > zone > sensor` — person always listed first in device and sensor names
- Pre-release detection in release workflow: tags matching `vX.Y.ZbN`, `vX.Y.ZaN`, `vX.Y.ZrcN` are automatically marked as GitHub pre-releases

### Changed
- Config flow Step 1 now uses a multi-select entity picker instead of two single-entity pickers
- Button now sends location refresh to all entities in the group (deduplicated)
- Pair device identifiers use entity IDs (not friendly names) — stable across entity renames
- `_calc_pair` is now a sync method (no awaits)
- `any_in_proximity` and `all_in_proximity` filter by `data_valid` before computing
- Group entity IDs fixed — `min_distance`, `any_in_proximity`, `all_in_proximity` no longer have duplicate device name suffix
- `PairData` legacy wrapper class removed
- `async_migrate_entry`, `CONF_ENTITY_A`, `CONF_ENTITY_B` removed — no migration path from v0.1.0

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
