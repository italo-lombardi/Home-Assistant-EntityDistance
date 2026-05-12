# Changelog

## [Unreleased]

### Added
- **Proximity Zone Number sensor** — numeric equivalent of Proximity Zone (1 = Very Near … 5 = Very Far); use in automations without string comparisons
- **Configurable zone thresholds** — new optional "Zone Thresholds" step in config/options flow to customize Very Near / Near / Medium / Far distances; defaults updated to 100 / 500 / 2000 / 10000 m
- Validation: zone thresholds must be strictly ascending (Very Near < Near < Medium < Far)

### Fixed
- Refresh Location button now resolves `person.*` entity devices via `person.source` attribute; previously skipped with "no device found" warning
- Internal `_show_advanced` temp key no longer leaks into config entry data
- `mock_config_entry` test fixture now sets `entry.options = {}` to match coordinator's merged data read

### Changed
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
