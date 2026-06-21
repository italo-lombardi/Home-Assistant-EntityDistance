# Changelog

## [Unreleased]

## [0.3.0] - 2026-06-21

### Breaking

- **Bus events are now opt-in (default off).** The integration previously fired
  `entity_distance_update` on every coordinator tick (~1 minute) plus
  `entity_distance_enter` / `entity_distance_leave` /
  `entity_distance_enter_unreliable` on threshold crossings. On a typical
  install this generated hundreds of thousands of bus-only events per pair
  over a recorder retention window — events with no history-panel value that
  bloated the recorder `events` table.
- **`entity_distance_update` is removed.** Even with the new opt-in flag
  enabled, the per-tick generic event no longer fires. Only the three
  threshold-crossing events do.
- **Migration for users with existing automations:** automations using
  `event_type: entity_distance_update` triggers will not fire after upgrading.
  Replace them with state-change triggers on
  `binary_sensor.<pair>_in_proximity` (preferred — does not pollute the
  recorder), or, if you still need event-based triggers for enter/leave,
  enable **Settings → Devices & services → Entity Distance → Configure →
  Advanced → Emit proximity bus events** and switch to
  `entity_distance_enter` / `entity_distance_leave`. See README → Events for
  a `recorder.exclude.event_types` snippet.

### Added

- `emit_bus_events` config option (default `False`) on the Advanced step of
  both initial setup and Options. When on, fires
  `entity_distance_enter` / `entity_distance_enter_unreliable` /
  `entity_distance_leave` on threshold crossings only — never per tick.
- `Settings` sensor exposes `emit_bus_events` so the device card surfaces
  whether bus events are enabled.

### Internal

- `EVENT_UPDATE` import dropped from `coordinator.py`.
- 470+ tests passing, 100% coverage. New `TestEmitBusEventsGate` covers
  default-off, opt-in threshold-only, and opt-in no-per-tick behaviors.

## [0.2.7] - 2026-06-18

### Added

- 5 per-pair bucket `binary_sensor.<pair>_in_<bucket>` (exactly-one-on); use as automation triggers or `history_stats` inputs.
- `Settings` diagnostic sensor (group + per-pair). State = summary `entry/exit · debounce · zones`; 14 settings as attrs.
- `entity-distance-pair-card` + `entity-distance-avatar-card`: `show_settings` option (default off), two-line wrap-friendly stat-box.
- `today_unaccounted_time` exposes `tracking_started` attribute (context for large initial values on install day).

### Fixed

- `Same Zone` always Off for person↔zone pairs. `zone.*` state is a count, not the zone name. Now compares `zone.home` → literal `"home"` (HA's `STATE_HOME`) and any other zone → `State.name` (matches `device_tracker.entity` exactly), so renamed/non-home zones also resolve.
- `Today Mid/Far/Very Far Time` sensors stuck at 0m. Accumulator was gated by `proximity`, impossible above 500 m. Bucket time now accrues on every valid tick; `today_proximity_time` stays gated.
- `Today Unaccounted Time` formula. Old: minutes since last `prev_calc_time` (returned `None` on invalidation, the case it should be reporting). New: `(now − midnight) − sum(today_zone_seconds)`. Clamped to 0.
- Persistence-load tests timezone-flaky (`date.today()` vs `dt_util.now().date()`).

### Internal

- Rename `_calc_bucket` → `calc_bucket` (now used cross-module).
- `TodayUnaccountedTimeSensor.available` no longer gates on `data_valid`.
- `strings.json` keys + 10 locale translations for new entities.
- 461 passing, 100% coverage.

## [0.2.6] - 2026-06-17

### Fixed

- **Update count diverged from `Last Update` in resync hold** — `update_count_a/b` was incremented inside `_calc_pair`, gated by the resync-hold early-return. `last_update_a/b`, however, is stamped in `_async_state_changed` on every state event. During a hold (or any tick that bails before the counter block), users saw `Last Update: 14m ago` while `Update Count Last 30 min: 0`. Counter increment moved to `_async_state_changed` so both fields advance together. Hold ticks no longer suppress the diagnostic counter (which was misleading anyway — observations were arriving, the integration just declined to use them for distance). Counter still skips `unavailable`/`unknown` arrivals so flapping devices cannot trip the reliability gate without producing a valid fix. Internally, `_update_frequency` was folded into a single `_advance_window(count, window_start, now) -> (count, window_start)` so the count-reset and window-reset boundaries cannot drift apart in a future change.
- **Pair card and avatar card showed `Xh (Y+1)m` instead of `Xh Ym` for proximity duration** — `_formatMinutes` did `Math.floor(min/60)` then `Math.round(min % 60)`, so a sensor value of 29822.78 min rendered `497h 3m` while the sensor source was 497h 2m. Reformatted via `Math.round(min*60)` into total seconds, then `Math.floor` into h/m so the displayed split is internally consistent. Applied to both `entity-distance-pair-card.js` and `entity-distance-avatar-card.js`.
- **Pair card and avatar card relative time floor-rounded, sensor side rounds** — `_formatTs` used `Math.floor(diffMs / 60000)` and floor-of-hours, so a 1h 55m old timestamp showed "1h ago" while HA's built-in formatter (used elsewhere) rounds to "2h ago". Switched to `Math.round` for minutes/hours/days so the card matches sensor displays side-by-side. Applied to both pair and avatar cards.

## [0.2.5] - 2026-06-15

### Fixed

- **Same-day hold flush double-counted `today_proximity_seconds`** — resync hold firing on the same calendar day re-added the full elapsed session to today counters on top of what tick-by-tick accumulation had already credited. Today counters are now only written in the hold flush when the date actually rolled (matching the daily-reset guard). Cross-midnight hold still correctly credits only the post-midnight slice.
- **`_invalidate()` double-counted `today_proximity_seconds`** — same bug as the hold flush: same-day invalidation (GPS gone unavailable, entity removed) re-added the full proximity session elapsed to today counters. Fixed with the same `inv_date_rolled` guard; cross-midnight invalidation credits only the post-midnight slice.
- **`today_zone_seconds` accumulated on every tick regardless of proximity** — zone bucket seconds were written outside the `(ps.proximity or was_proximity)` guard, so every non-proximity tick inflated zone totals. Moved inside the guard so `sum(today_zone_seconds.values())` always equals `today_proximity_seconds`.
- **`EVENT_LEAVE` payload missing 6 fields at `_invalidate()` and hold flush** — both sites fired `EVENT_LEAVE` with only `{entity_a, entity_b}`. Any automation reading `distance_m`, `reliable`, etc. got a `KeyError`. Both sites now emit the full 8-field payload matching the normal EXIT path, with `reliable=False` and `direction=None`.
- **Sensors returned non-`None` when `available=False`** — `ProximityDurationSensor`, `LastSeenTogetherSensor`, `GpsAccuracySensor`, `LastUpdateSensor`, `TodayUnaccountedTimeSensor`, `ProximityTrackingStartedSensor`, and `MinDistanceSensor` all violated the HA contract that `native_value` must return `None` when `available=False`. All guarded. `MinDistanceSensor` gains its own `available` property. `EntityStateSensor` previously checked only `coordinator.last_update_success`; now checks `self.available` (which also gates on `data_valid`).
- **DST boundary midnight arithmetic** — all 5 midnight-computation sites used naive `datetime.replace()` subtraction. On DST fall-back night the subtraction silently under-counted by 1h; on spring-forward it over-counted. All sites now route through UTC via `.astimezone(UTC)` before differencing.
- **`data-entity` attribute in Group Card not fully encoded** — `p.distEntityId.replace(/"/g, "")` stripped only double-quotes. Replaced with the existing `_encodeAttr()` helper that encodes `&`, `"`, `<`, `>`.
- **HA minimum version badge incorrect** — README badge showed `2024.1+` but `hacs.json` requires `2024.3.0`. Corrected.
- **Manual Lovelace resource URLs outdated** — README snippet referenced `?0.2.4` cache-bust version. Updated to `?0.2.5`.
- **`SECURITY.md` listed only `0.1.x` as supported** — updated to `0.2.x ✅ / 0.1.x ❌`.

- **Config entry migration missing** — `async_migrate_entry` (v1 single-pair → v2 group format) was accidentally removed in a cleanup commit. Any user upgrading from 0.1.x got a permanently disabled entry. Migration is restored, with added guards: fewer-than-2-entity lists return `False`, and unknown future versions also return `False` instead of silently succeeding.
- **Proximity duration lost on restart** — when HA restarted while a pair was in proximity, the elapsed time from `proximity_since` to the shutdown was silently discarded. Duration is now credited on restore, and `proximity_since` is advanced to `now` to prevent double-counting. `prev_calc_time` is also set to `now` on restore so the first tick's midnight-flush block does not attempt to flush a stale pre-restart timestamp.
- **Cross-midnight today-time gap** — the pre-midnight interval was added to `today_proximity_seconds` then immediately overwritten by the daily reset (a no-op). Fixed: pre-midnight proximity time is now credited to `proximity_duration_s` (the lifetime counter that survives resets) using `was_proximity` and `prev_distance_m` for correct bucket/flag, and the post-midnight slice is accumulated separately.
- **Resync-hold could permanently suppress EVENT_ENTER** — the proximity entry/exit block ran before the resync-hold early-return, leaving `ps.proximity = True` persisted when the hold fired. Next tick `was_proximity` was True so ENTER never fired; LEAVE fired with no paired ENTER, breaking all automations. Proximity transitions now execute after the hold check.
- **`prev_distance_m`/`prev_calc_time` written before hold check** — hold ticks wrote a bad baseline so the first post-hold tick triggered a spurious speed-filter rejection. These fields are now written after all early-return paths.
- **`_invalidate()` left `ps.proximity = True` stale** — entity going unavailable while in proximity left proximity state and `proximity_since` set, so the next valid observation would credit the entire unavailability window as proximity time. `_invalidate()` now closes the session (credits elapsed duration) and clears proximity.
- **`_updates_window_s` configured but never read** — all window comparisons used the module-level constant `UPDATES_FREQUENCY_WINDOW_S`, silently ignoring the user-configured window. Fixed at all call sites in the coordinator.
- **`datetime.now().astimezone()` used throughout** — on deployments where the OS timezone differs from the HA timezone (common in Docker), daily resets fired at OS midnight instead of HA midnight. All coordinator datetime calls replaced with `dt_util.now()`.
- **`_async_update_data` returned incomplete GroupData** — HA-internal `async_refresh()` calls produced GroupData with `min_distance_m=None` and `any/all_in_proximity=False` always. Now populates all aggregates correctly.
- **Coordinator resource leak on setup failure** — if `async_setup()` or `async_recalculate()` raised, state-change listeners remained active on a zombie coordinator. The coordinator is now unloaded on setup exception.
- **`source.exists()` blocking call on event loop** — called synchronously in `_async_install_card`; moved to `async_add_executor_job`.
- **Bare `except Exception` on static path registration** — swallowed genuine errors (e.g. `AttributeError`, I/O failures) and set `_CARD_INSTALLED_KEY = True`, meaning the card was never served and the error was never retried. Narrowed to `except RuntimeError`.
- **Today-time accumulated before reliability check** — `today_proximity_seconds` was incremented on ticks the reliability filter then rolled back. Accumulation now happens after the check.
- **`AnyInProximity` / `AllInProximity` returned `False` when all pairs had bad GPS** — sensors now return `None` (unavailable) when every pair has `data_valid = False`.
- **`last_seen_together` stamped at wrong moment** — was set on the EXIT detection tick; now stamped on every in-proximity tick and on EXIT.
- **`today_zone_seconds` dataclass field used `None` sentinel** — `field(default_factory=dict)` replaces the `__post_init__` workaround.
- **`_CARD_INSTALLED_KEY` not cleared on last-entry unload** — flag now cleared when no entries remain, preventing stale resources after full reload.
- **GPS coordinates logged at 6 decimal places in DEBUG** — reduced to 2 d.p. (~1 km resolution) to avoid logging precise household locations in debug output that is commonly attached to bug reports.
- **Zone breakdown sensors always blank in Pair Card** — card used `today_very_near_time` / `today_medium_time` patterns but backend creates `today_zone_time_very_near` / `today_zone_time_mid`. All zone suffixes corrected; `_watchIds` updated to match.
- **XSS via `entity_picture` in Group Card** — `entity_picture` URL was interpolated raw into SVG `innerHTML`. Added `_encodeAttr()` helper and applied it to the `href` attribute.
- **Card self-reported version stuck at 0.2.3** — all three cards now report `0.2.5`, matching the manifest and cache-busting URL.
- **Error message contradicted validation rule** — `exit_below_entry` error said "greater than or equal to" but validation rejects equal values. Fixed to "strictly greater than".
- **HACS minimum HA version too low** — `hacs.json` listed `2024.1.0`; `MINOR_VERSION` requires 2024.3+. Updated to `"homeassistant": "2024.3.0"`.
- **`TOTAL_INCREASING` state class on proximity duration sensor** — `ProximityDurationSensor` was incorrectly set to `TOTAL_INCREASING`, which requires a strictly non-decreasing value. The sensor's `native_value` includes a live term `now - proximity_since` that resets to zero on EXIT, causing HA statistics to mark the series as inconsistent. Corrected to `MEASUREMENT`. Daily-reset sensors (`TodayProximityTimeSensor`, `TodayZoneTimeSensor`) correctly use `MEASUREMENT` and were not changed.
- **Duplicate window constant** — `UPDATES_FREQUENCY_WINDOW_S` now derives from `DEFAULT_UPDATES_WINDOW_S`.
- **Dead constant removed** — `BUCKET_THRESHOLDS_DEFAULT` was never used.

## [0.2.4] - 2026-05-31

### Fixed
- **Card install race**: replaced module-level `_CARD_INSTALLED` global with a `hass.data[DOMAIN]` flag, preventing duplicate Lovelace resource registration when multiple config entries set up concurrently
- **Speed filter false rejects**: increased minimum elapsed-time gate from `>0` to `>=5s` before computing implied speed; eliminates spurious `speed_filter` invalidations caused by GPS jitter on rapid successive state events
- **Coord-extraction log spam**: warning log now includes only the relevant location attributes (`latitude`, `longitude`, `location`, `gps_accuracy`) instead of the full state attribute dict, avoiding megabyte-sized log entries for entities with large attribute payloads (e.g. `media_player`)
- **State restore visibility**: persisted state restore failures now log with `exc_info=True`, so the underlying exception is visible instead of being silently swallowed
- **Lovelace `resources.loaded` mutation**: removed direct mutations of `ResourceStorageCollection.loaded`; Home Assistant manages this internally
- **Coordinator API hygiene**: renamed `_async_recalculate` → `async_recalculate` since it is invoked from `async_setup_entry`; the leading underscore was misleading

## [0.2.3] - 2026-05-23

### Added
- **Same Zone binary sensor** — `binary_sensor.*_same_zone` per pair: `ON` when both entities report the same named zone (e.g. both at `home`, both at `work`), `OFF` when they differ, `unavailable` when either entity is `not_home`, `unknown`, or `unavailable`
- **Zone-zone pair sensor reduction** — pairs where both entities are `zone.*` now create only Distance, Proximity Zone, and Proximity Zone Number sensors (motion-dependent sensors skipped: proximity, today-time, direction, speed, ETA, GPS accuracy, state, update count)

## [0.2.2] - 2026-05-22

### Added
- **Group Card: per-node label settings** — `node_settings` config key allows per-entity control of label visibility and position
  - `show_name`: show or hide the entity name label (default: `true`)
  - `show_state`: show or hide the entity state label (default: `true`, inherits global `show_state`)
  - `label_position`: `above`, `below`, or `auto` (default: `auto` — uses centroid-based detection)
  - All three settings are editable in the card editor under a new "Node Labels" section

### Fixed
- **Group Card**: connection line labels on horizontal edges (top row and bottom row) now always appear on the outward-facing side of the line — top-row labels go above, bottom-row labels go below
- **Group Card**: middle node (5-node layout) name/state label no longer flips between above and below on each hass state update — `_nodeLabelSide` cache now resets only on config change, not on every render
- **Group Card**: idle animation (slow node drift) now skips entirely when `fixed_layout: true` — nodes stay on their grid positions with no movement
- **Group Card**: node positions are now clamped to canvas bounds when an existing node is reused after a canvas resize
- **Group Card**: entity list change (add/remove entity) now correctly resets the settled flag and re-runs the force simulation
- **Group Card**: centroid epsilon guard prevents erratic line label flip when edge midpoint is very close to graph centroid
- **Group Card** (code quality): `_zoneColor` and `_dirArrow` use lookup objects instead of if-chains; `_watchIds` uses `flatMap`; `combinations()` hoisted out of loop; node label above/below duplication extracted to `_nodeLabel()` helper; editor pair settings extracted to `_renderPairSettings()`

## [0.2.1] - 2026-05-22

### Added
- **Group Card** (`entity-distance-group-card`) — force-directed SVG graph showing all group entities as circles with labeled connecting lines
  - Lines colored by proximity zone; thicker with glow effect when a pair is in proximity
  - Per-line labels: distance and/or zone text independently configurable per pair
  - Direction arrow on each line (↑ diverging, ↓ approaching, • stationary); hidden when both distance and zone labels are disabled
  - Grid-based initial node layout by entity count: 2 = vertical pair, 3 = triangle, 4 = 2×2, 5 = 3-row with center middle node
  - Adaptive label placement: entity name + state above circle for top-row nodes, below for bottom-row nodes
  - Background rectangles behind text labels to prevent line overlap
  - `fixed_layout` option: equal spacing regardless of real distance (default on)
  - Per-entity hide toggle in editor (eye icon) — hidden entities and all their connecting lines are removed from the graph
  - Badge: "X of N pairs in proximity" counting only visible pairs
  - `pair_settings` per-pair config keyed by sorted entity ID pair (`"entity_a,entity_b"`)
  - Tap a line to open the HA more-info panel for that pair's distance sensor
  - Editor: group selector dropdown, entity order list with ↑/↓ reorder and hide toggle, title field, equal spacing checkbox, per-pair distance/zone label toggles
  - Auto-discovers available groups from hass.states using clique detection — correctly separates multiple config entries
  - `ResizeObserver` ensures correct width in the HA sections layout
  - Idle animation: slow node drift for 6 s after last state update
  - `touch-action: manipulation` on SVG — no tap delay on mobile/Companion app

### Fixed
- Accuracy filter and speed filter no longer leave `data_valid = True` after rejecting a GPS reading — both now call `_invalidate()` so downstream sensors correctly reflect unavailable data
- Proximity duration sensor no longer returns `None` when `data_valid` is `False` but tracking has started — gates on `proximity_tracking_started` instead
- Config flow now rejects equal entry/exit threshold values (previously only rejected exit < entry, allowing a deadlock where entry could never be exited)
- Resync hold now marks `data_valid = False` while the hold is active — prevents stale data appearing valid during silence window
- Group card group discovery uses clique detection instead of BFS — multiple config entries sharing an entity no longer merge into one combined group
- `UpdateCountSensor` returned stale count after 30-min window expired — now returns `0` when window has elapsed
- Pair Card diagnostics showed full device-prefixed label ("Dercy & Italo GPS Accuracy") — labels now hardcoded, `friendly_name` parsing removed
- Pair Card and Avatar Card pair discovery used v0.1.0 `sensor.entity_distance_` prefix — now discovers pairs via `entity_a` attribute; entity ID lookups use `sensor.${slug}_` pattern
- Entity state badges overlapped the divider line below the hero row — added top padding to `.entity-states`
- Lovelace resource updater skipped non-`ResourceStorageCollection` setups — added fallback direct assignment
- Stale Lovelace resources from renamed cards (`entity-distance-card.js`, `entity-distance-people-card.js`) now auto-purged on startup
- Group card blank in `sections` layout — `ResizeObserver` now triggers layout after real card width is known
- `shouldUpdate` in Pair Card and Avatar Card accessed `old.states[id]` without optional chaining — could throw on first render
- `last_seen_together` now records when proximity **ends** (exit) rather than when it begins (entry) — Pair Card shows "Together now" while `in_proximity` is on
- Proximity duration sensor no longer resets to near-zero after HA restart — `proximity_since` is now persisted and restored
- Pair Card "Proximity duration since" timestamp now includes time-of-day, not just date
- Pair Card speed stat box label now reads "Diverging speed" when entities are moving apart
- `datetime.fromtimestamp` in resync hold replaced with `now + timedelta(seconds=...)` for timezone consistency
- `except Exception` in `button.py` now carries `# noqa: BLE001` suppression comment
- `validate.yml` CI workflow now has `permissions: contents: read` — resolves GitHub code scanning warnings

### Changed
- `TodayZoneTimeSensor` exposes `range_from_m` / `range_to_m` state attributes
- Proximity duration and proximity rate stat boxes now share one row when both are enabled
- Lovelace cards renamed: `entity-distance-card` → `entity-distance-pair-card`, `entity-distance-people-card` → `entity-distance-avatar-card`
- Group card badge shows "X of N pairs in proximity" instead of generic "In Proximity" label
- Card versions bumped to `0.2.0`; console log includes `— github.com/italo-lombardi` suffix

## [0.2.1b8] - 2026-05-22

### Fixed
- Group card group discovery uses clique detection instead of connected-components BFS — multiple config entries sharing an entity no longer merge into one combined group
- Group card `getStubConfig` no longer produces a merged entity list when multiple config entries exist

### Changed
- Group card `fixed_layout` defaults to `true` (equal spacing) for new cards
- Group card SVG gets `touch-action: manipulation` — eliminates 300 ms tap delay on mobile/Companion app
- `validate.yml` CI workflow gets `permissions: contents: read` — resolves GitHub code scanning warnings
- README screenshot paths corrected to `assets/screenshots/`
- `info.md` updated with Lovelace Cards section describing all three cards

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
