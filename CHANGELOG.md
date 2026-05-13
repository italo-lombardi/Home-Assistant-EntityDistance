# Changelog

## [Unreleased]

## [0.1.0-alpha.4] - 2026-05-13

### Added
- **Icons** — `icons.json` with MDI icons for all sensors, binary sensor (open/closed states), and button

### Changed
- **Today Zone Time sensors** — removed `DIAGNOSTIC` category; now shown as regular sensors alongside Today Proximity Time
- **Update Count sensors** — renamed to `Update Count Last 30 min (A/B)` to make the 30-minute window explicit; updated in all 11 language files
- **Integration icon** — lightened background from dark navy to medium blue-slate (`#405d95`)

## [0.1.0-alpha.3] - 2026-05-13

### Added
- **Today zone time sensors** — 5 new sensors tracking minutes spent in each proximity zone today (Very Near, Near, Medium, Far, Very Far); reset at midnight
- **Direction Level sensor** — numeric companion to Direction: -1 = approaching, 0 = stationary, 1 = diverging; enables automation comparisons without string matching
- **Entity Distance People Card** (`entity-distance-people-card`) — new Lovelace card with entity avatars side-by-side; shows entity pictures if available, falls back to initials; same slug-based config as Card A
- Both Lovelace cards now auto-registered as Lovelace resources on integration load

### Changed
- **Update Count replaces Update Frequency** — `Update Frequency (A/B)` sensors replaced by `Update Count (A/B)`: raw integer count of location updates in the last 30 minutes (window extended from 5 → 30 min for meaningful signal across all GPS modes)
- **Stationary threshold raised** — movement < 50 m between updates classified as stationary (was 5 m); prevents GPS jitter from falsely showing approaching/diverging
- **Default GPS error radius raised** — 100 m → 150 m (covers Android indoors which commonly reports 100 m accuracy)
- **Entity Distance Card rewritten** — now uses LitElement via `customElements.whenDefined` (same pattern as EntityAvailability card); pair selection via slug dropdown auto-populated from live hass states; full options editor with sections for Main Display, Movement, Time Together, Diagnostics, Layout
- Resync silence threshold uses `>=` instead of `>` (off-by-one fix)

### Removed
- **Data Staleness sensors** — removed `Location Age (A/B)` sensors; `Last Update (A/B)` timestamp sensors serve the same purpose more accurately (staleness was a frozen snapshot, not live)

## [0.1.0-alpha.2] - 2026-05-13

### Added
- **Proximity Zone Number sensor** — numeric equivalent of Proximity Zone (1 = Very Near … 5 = Very Far); use in automations without string comparisons
- **Configurable zone thresholds** — new optional "Zone Thresholds" step in config/options flow to customize Very Near / Near / Medium / Far distances; defaults updated to 100 / 500 / 2000 / 10000 m
- Validation: zone thresholds must be strictly ascending (Very Near < Near < Medium < Far)

### Fixed
- Refresh Location button now sends `request_location_update` via `notify.mobile_app_*` (works on iOS and Android); previously called a non-existent service and always failed
- Sensors no longer go Unknown after reconfiguring — coordinator immediately recalculates from current state on reload instead of waiting for next GPS event
- Internal `_show_advanced` temp key no longer leaks into config entry data
- `mock_config_entry` test fixture now sets `entry.options = {}` to match coordinator's merged data read

### Changed
- Default GPS error radius: 100 m → 150 m (covers Android indoors which commonly reports 100 m accuracy)
- Proximity Zone "Mid" renamed to "Medium" in UI (internal key `mid` unchanged)
- Proximity zone defaults: Very Near 50 m → 100 m, Near 200 m → 500 m, Mid 1 km → 2 km, Far 5 km → 10 km
- Coordinator reads from merged `entry.data + entry.options` (was `entry.data` only)
- Sensor renames: "Closing Speed" → "Approach Speed", "ETA" → "Estimated Arrival Time", "Data Staleness" → "Location Age"
- UI label improvements: "Nearby distance" → "Nearby threshold", "Away distance" → "Away threshold", "Update delay" → "Location update delay", "Max GPS inaccuracy" → "Max GPS error radius", "Max speed filter" → "Max plausible speed", "Updates needed to be reliable" → "Consecutive updates required for reliability"
- Error messages made more precise and consistent with field labels
- Config flow step 1 title changed from "Entity Pair" to "Choose Entities"

## [0.1.0-alpha.1] - 2026-05-13

### Fixed
- `Debouncer` import moved to `homeassistant.helpers.debounce` (removed from `helpers.event`)
- `DeviceEntryType` import moved to `homeassistant.helpers.device_registry`
- `hass.bus.async_fire` → `hass.bus.fire` (method does not exist in HA)
- `_calc_bucket` import corrected from `const` to `coordinator`
- `OptionsFlow.__init__` no longer accepts `config_entry` param; uses `self.config_entry`
- `async_get_options_flow` no longer passes stale `config_entry` arg (would cause `TypeError`)
- `last_update_a`/`last_update_b` now set per-entity in state-change event handler (not overwritten on every recalculate, fixing staleness detection)
- `proximity_duration_s` double-accumulation bug fixed; live session value computed in sensor
- Update frequency divide-by-near-zero guarded (`elapsed_s < 1.0 → 0.0`)
- Max speed selector cap raised from 500 to 2000 km/h (allows 1000 km/h default)

### Changed
- Default entry threshold: 500 m → 200 m
- Default exit threshold: 700 m → 500 m (300 m hysteresis)
- Default debounce: 2 s → 10 s
- Default max GPS accuracy: 200 m → 100 m
- Default max speed: 150 km/h → 1000 km/h
- Diagnostic sensor names now use entity friendly names instead of "(A)"/"(B)" suffixes
- Friendly names resolved from `hass.states.get().name` with fallback to entity_id-derived name
- Config/options flow: added "Configure advanced filters" toggle on thresholds step; skips advanced step when off
- Config/options flow: improved field labels and descriptions with plain-English explanations and examples
- `already_in_progress` abort now shows translated message
- Stale in-progress flows aborted automatically when user reopens setup dialog

## [0.1.0] - 2026-05-12

### Added
- Initial release
- 16 sensors per pair: distance, proximity zone (bucket), proximity duration, last seen together, today proximity time, direction, closing speed, ETA, GPS accuracy A/B, last update A/B, update frequency A/B, data staleness A/B
- Binary sensor: in proximity (hysteresis with entry/exit thresholds)
- Button: refresh location (triggers mobile_app update)
- 4 HA events: entity_distance_enter, entity_distance_leave, entity_distance_update, entity_distance_enter_unreliable
- Support for person, device_tracker, sensor, and zone entities
- Zone-to-zone and person-to-zone distance tracking
- GPS accuracy and speed filters
- Reliability tracking (min updates in rolling window)
- Event-driven updates (no polling) via Debouncer
- 3-step config flow + options flow
- 11 language translations


## [0.1.0-alpha.1] - 2026-05-13

### Fixed
- `Debouncer` import moved to `homeassistant.helpers.debounce` (removed from `helpers.event`)
- `DeviceEntryType` import moved to `homeassistant.helpers.device_registry`
- `hass.bus.async_fire` → `hass.bus.fire` (method does not exist in HA)
- `_calc_bucket` import corrected from `const` to `coordinator`
- `OptionsFlow.__init__` no longer accepts `config_entry` param; uses `self.config_entry`
- `async_get_options_flow` no longer passes stale `config_entry` arg (would cause `TypeError`)
- `last_update_a`/`last_update_b` now set per-entity in state-change event handler (not overwritten on every recalculate, fixing staleness detection)
- `proximity_duration_s` double-accumulation bug fixed; live session value computed in sensor
- Update frequency divide-by-near-zero guarded (`elapsed_s < 1.0 → 0.0`)
- Max speed selector cap raised from 500 to 2000 km/h (allows 1000 km/h default)

### Changed
- Default entry threshold: 500 m → 200 m
- Default exit threshold: 700 m → 500 m (300 m hysteresis)
- Default debounce: 2 s → 10 s
- Default max GPS accuracy: 200 m → 100 m
- Default max speed: 150 km/h → 1000 km/h
- Diagnostic sensor names now use entity friendly names instead of "(A)"/"(B)" suffixes
- Friendly names resolved from `hass.states.get().name` with fallback to entity_id-derived name
- Config/options flow: added "Configure advanced filters" toggle on thresholds step; skips advanced step when off
- Config/options flow: improved field labels and descriptions with plain-English explanations and examples
- `already_in_progress` abort now shows translated message
- Stale in-progress flows aborted automatically when user reopens setup dialog

## [0.1.0] - 2026-05-12

### Added
- Initial release
- 16 sensors per pair: distance, proximity zone (bucket), proximity duration, last seen together, today proximity time, direction, closing speed, ETA, GPS accuracy A/B, last update A/B, update frequency A/B, data staleness A/B
- Binary sensor: in proximity (hysteresis with entry/exit thresholds)
- Button: refresh location (triggers mobile_app update)
- 4 HA events: entity_distance_enter, entity_distance_leave, entity_distance_update, entity_distance_enter_unreliable
- Support for person, device_tracker, sensor, and zone entities
- Zone-to-zone and person-to-zone distance tracking
- GPS accuracy and speed filters
- Reliability tracking (min updates in rolling window)
- Event-driven updates (no polling) via Debouncer
- 3-step config flow + options flow
- 11 language translations
