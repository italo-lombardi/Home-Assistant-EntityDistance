from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import itertools
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from homeassistant.util.location import distance as ha_distance

from .const import (
    BUCKET_FAR,
    BUCKET_MID,
    BUCKET_NEAR,
    BUCKET_VERY_FAR,
    BUCKET_VERY_NEAR,
    CONF_DEBOUNCE_S,
    CONF_ENTITIES,
    CONF_ENTRY_THRESHOLD_M,
    CONF_EXIT_THRESHOLD_M,
    CONF_MAX_ACCURACY_M,
    CONF_MAX_SPEED_KMH,
    CONF_MIN_UPDATES_RELIABLE,
    CONF_REQUIRE_RELIABLE,
    CONF_RESYNC_HOLD_S,
    CONF_RESYNC_SILENCE_S,
    CONF_UPDATES_WINDOW_S,
    CONF_ZONE_FAR_M,
    CONF_ZONE_MID_M,
    CONF_ZONE_NEAR_M,
    CONF_ZONE_VERY_NEAR_M,
    DEFAULT_DEBOUNCE_S,
    DEFAULT_ENTRY_THRESHOLD_M,
    DEFAULT_EXIT_THRESHOLD_M,
    DEFAULT_MAX_ACCURACY_M,
    DEFAULT_MAX_SPEED_KMH,
    DEFAULT_MIN_UPDATES_RELIABLE,
    DEFAULT_REQUIRE_RELIABLE,
    DEFAULT_RESYNC_HOLD_S,
    DEFAULT_RESYNC_SILENCE_S,
    DEFAULT_UPDATES_WINDOW_S,
    DEFAULT_ZONE_FAR_M,
    DEFAULT_ZONE_MID_M,
    DEFAULT_ZONE_NEAR_M,
    DEFAULT_ZONE_VERY_NEAR_M,
    DIRECTION_APPROACHING,
    DIRECTION_DIVERGING,
    DIRECTION_STATIONARY,
    DOMAIN,
    EVENT_ENTER,
    EVENT_ENTER_UNRELIABLE,
    EVENT_LEAVE,
    EVENT_UPDATE,
    STATIONARY_THRESHOLD_M,
)
from .models import GroupData, PairState, pair_key

_LOGGER = logging.getLogger(__name__)


def _is_zone(state: State) -> bool:
    return state.entity_id.startswith("zone.")


def _get_coords(state: State) -> tuple[float, float, float | None] | None:
    attrs = state.attributes

    lat: float | None = None
    lon: float | None = None
    accuracy: float | None = None

    loc = attrs.get("location")
    if isinstance(loc, (list, tuple)) and len(loc) >= 2:
        try:
            lat, lon = float(loc[0]), float(loc[1])
        except (TypeError, ValueError):
            lat = lon = None

    if lat is None:
        try:
            lat = float(attrs["latitude"])
            lon = float(attrs["longitude"])
        except (KeyError, TypeError, ValueError):
            lat = lon = None

    if lat is None:
        try:
            parts = str(state.state).split(",")
            lat, lon = float(parts[0]), float(parts[1])
        except (IndexError, ValueError):
            lat = lon = None

    if lat is None or lon is None:
        _LOGGER.warning(
            "entity_distance: cannot extract coords from %s",
            state.entity_id,
        )
        return None

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        _LOGGER.warning(
            "entity_distance: invalid coords for %s",
            state.entity_id,
        )
        return None

    try:
        accuracy = float(attrs["gps_accuracy"])
    except (KeyError, TypeError, ValueError):
        accuracy = None

    _LOGGER.debug(
        "entity_distance: coords resolved for %s — lat=%.2f lon=%.2f acc=%s",
        state.entity_id,
        lat,
        lon,
        f"{accuracy:.1f}m" if accuracy is not None else "none",
    )
    return lat, lon, accuracy


def calc_bucket(distance_m: float, thresholds: dict[str, float]) -> str:
    for bucket, threshold in thresholds.items():
        if distance_m <= threshold:
            return bucket
    return BUCKET_VERY_FAR


def _resolve_entities(data: dict) -> list[str]:
    return list(data.get(CONF_ENTITIES, []))


class EntityDistanceCoordinator(DataUpdateCoordinator[GroupData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=None,
        )
        self._entry = entry
        self._unsub_listeners: list = []
        self._debouncer: Debouncer | None = None

        data = {**entry.data, **entry.options}
        self._entities: list[str] = _resolve_entities(data)
        self._entry_threshold_m: float = data.get(CONF_ENTRY_THRESHOLD_M, DEFAULT_ENTRY_THRESHOLD_M)
        self._exit_threshold_m: float = data.get(CONF_EXIT_THRESHOLD_M, DEFAULT_EXIT_THRESHOLD_M)
        self._debounce_s: float = data.get(CONF_DEBOUNCE_S, DEFAULT_DEBOUNCE_S)
        self._max_accuracy_m: float = data.get(CONF_MAX_ACCURACY_M, DEFAULT_MAX_ACCURACY_M)
        self._max_speed_kmh: float = data.get(CONF_MAX_SPEED_KMH, DEFAULT_MAX_SPEED_KMH)
        self._resync_silence_s: float = data.get(CONF_RESYNC_SILENCE_S, DEFAULT_RESYNC_SILENCE_S)
        self._resync_hold_s: float = data.get(CONF_RESYNC_HOLD_S, DEFAULT_RESYNC_HOLD_S)
        self._min_updates_reliable: int = data.get(
            CONF_MIN_UPDATES_RELIABLE, DEFAULT_MIN_UPDATES_RELIABLE
        )
        self._updates_window_s: float = data.get(CONF_UPDATES_WINDOW_S, DEFAULT_UPDATES_WINDOW_S)
        self._require_reliable: bool = data.get(CONF_REQUIRE_RELIABLE, DEFAULT_REQUIRE_RELIABLE)
        self._bucket_thresholds: dict[str, float] = {
            BUCKET_VERY_NEAR: data.get(CONF_ZONE_VERY_NEAR_M, DEFAULT_ZONE_VERY_NEAR_M),
            BUCKET_NEAR: data.get(CONF_ZONE_NEAR_M, DEFAULT_ZONE_NEAR_M),
            BUCKET_MID: data.get(CONF_ZONE_MID_M, DEFAULT_ZONE_MID_M),
            BUCKET_FAR: data.get(CONF_ZONE_FAR_M, DEFAULT_ZONE_FAR_M),
        }

        self._pair_states: dict[tuple[str, str], PairState] = {}
        for a, b in itertools.combinations(self._entities, 2):
            k = pair_key(a, b)
            self._pair_states[k] = PairState(entity_a_id=k[0], entity_b_id=k[1])

        # Reverse index: entity_id → list of pair keys it belongs to (O(1) lookup in state_changed)
        self._entity_to_pairs: dict[str, list[tuple[str, str]]] = {e: [] for e in self._entities}
        for k in self._pair_states:
            self._entity_to_pairs[k[0]].append(k)
            self._entity_to_pairs[k[1]].append(k)

        # Per-pair resync state
        self._resync_holding: dict[tuple[str, str], bool] = dict.fromkeys(self._pair_states, False)
        self._resync_hold_until: dict[tuple[str, str], datetime | None] = dict.fromkeys(
            self._pair_states
        )

        self._pending_updates: set[str] = set()
        self._store: Store = Store(hass, 1, f"{DOMAIN}_group_state_{entry.entry_id}")

    @property
    def entities(self) -> list[str]:
        return self._entities

    @property
    def bucket_thresholds(self) -> dict[str, float]:
        return self._bucket_thresholds

    @property
    def updates_window_s(self) -> float:
        return self._updates_window_s

    @property
    def settings_snapshot(self) -> dict[str, float | int | bool]:
        """All proximity / filter settings the coordinator was constructed with.
        Exposed so a diagnostic sensor can present them on the device card."""
        return {
            "entry_threshold_m": self._entry_threshold_m,
            "exit_threshold_m": self._exit_threshold_m,
            "debounce_s": self._debounce_s,
            "max_accuracy_m": self._max_accuracy_m,
            "max_speed_kmh": self._max_speed_kmh,
            "resync_silence_s": self._resync_silence_s,
            "resync_hold_s": self._resync_hold_s,
            "min_updates_reliable": self._min_updates_reliable,
            "updates_window_s": self._updates_window_s,
            "require_reliable": self._require_reliable,
            "zone_very_near_m": self._bucket_thresholds[BUCKET_VERY_NEAR],
            "zone_near_m": self._bucket_thresholds[BUCKET_NEAR],
            "zone_mid_m": self._bucket_thresholds[BUCKET_MID],
            "zone_far_m": self._bucket_thresholds[BUCKET_FAR],
        }

    async def async_setup(self) -> None:
        await self._async_load_state()

        now = dt_util.now()
        for ps in self._pair_states.values():
            if ps.proximity_tracking_started is None:
                ps.proximity_tracking_started = now

        await self._async_save_state()

        self._debouncer = Debouncer(
            self.hass,
            _LOGGER,
            cooldown=self._debounce_s,
            immediate=False,
            function=self.async_recalculate,
        )

        unsub = async_track_state_change_event(self.hass, self._entities, self._async_state_changed)
        unsub_tick = async_track_time_interval(self.hass, self._async_tick, timedelta(minutes=1))
        self._unsub_listeners = [unsub, unsub_tick]
        _LOGGER.debug("entity_distance: tracking %s", self._entities)

    @callback
    def async_unload(self) -> None:
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()
        if self._debouncer:
            self._debouncer.async_shutdown()
        _LOGGER.debug("entity_distance: unloaded coordinator for %s", self._entry.entry_id)

    @callback
    def _async_tick(self, _now: datetime) -> None:
        if self._debouncer is not None:
            self.hass.async_create_task(self._debouncer.async_call())

    @callback
    def _async_state_changed(self, event) -> None:
        if self._debouncer is None:
            return
        entity_id = event.data.get("entity_id")
        old_state = event.data.get("old_state")
        new_state = event.data.get("new_state")
        _LOGGER.debug(
            "entity_distance: state change — %s: %s → %s",
            entity_id,
            old_state.state if old_state else "none",
            new_state.state if new_state else "none",
        )
        now = dt_util.now()
        # An unavailable/unknown transition is an arrival event (so last_update
        # advances), but it carries no usable fix — counting it toward
        # update_count would let a flapping device trip the reliability gate
        # without ever producing a valid distance. Filter at the bump site.
        new_state_str = new_state.state if new_state else None
        is_valid_arrival = new_state_str not in (None, STATE_UNAVAILABLE, STATE_UNKNOWN)
        # Mark last_update and bump update counter for all pairs involving this
        # entity (O(1) via reverse index). Counters track valid raw arrivals,
        # decoupled from the calc-pair hold/skip logic — so users see
        # update_count and last_update move together for valid observations.
        for k in self._entity_to_pairs.get(entity_id, []):
            ps = self._pair_states[k]
            if entity_id == ps.entity_a_id:
                ps.last_update_a = now
                if is_valid_arrival:
                    ps.update_count_a, ps.update_window_start_a = self._advance_window(
                        ps.update_count_a, ps.update_window_start_a, now
                    )
            else:
                ps.last_update_b = now
                if is_valid_arrival:
                    ps.update_count_b, ps.update_window_start_b = self._advance_window(
                        ps.update_count_b, ps.update_window_start_b, now
                    )
        self._pending_updates.add(entity_id)
        self.hass.async_create_task(self._debouncer.async_call())

    async def async_recalculate(self) -> None:
        now = dt_util.now()
        pending = set(self._pending_updates)
        self._pending_updates.clear()

        pair_states_out: dict[tuple[str, str], PairState] = {}

        for k, ps in self._pair_states.items():
            entity_a = ps.entity_a_id
            entity_b = ps.entity_b_id
            pair_states_out[k] = self._calc_pair(ps, entity_a, entity_b, now, pending)

        self._pair_states = pair_states_out

        # Compute group aggregates — only count pairs with valid data
        valid_pairs = [
            ps for ps in self._pair_states.values() if ps.data_valid and ps.distance_m is not None
        ]
        min_dist: float | None = min((ps.distance_m for ps in valid_pairs), default=None)
        any_prox = any(ps.proximity for ps in self._pair_states.values() if ps.data_valid)
        all_prox = (
            bool(valid_pairs)
            and len(valid_pairs) == len(self._pair_states)
            and all(ps.proximity for ps in valid_pairs)
        )

        group = GroupData(
            pairs=dict(self._pair_states),
            min_distance_m=min_dist,
            any_in_proximity=any_prox,
            all_in_proximity=all_prox,
        )
        self.async_set_updated_data(group)
        await self._async_save_state()

    def _calc_pair(
        self,
        ps: PairState,
        entity_a: str,
        entity_b: str,
        now: datetime,
        pending: set[str],
    ) -> PairState:
        k = pair_key(entity_a, entity_b)
        state_a = self.hass.states.get(entity_a)
        state_b = self.hass.states.get(entity_b)

        _LOGGER.debug(
            "entity_distance: recalculate pair (%s, %s) — a=%s b=%s",
            entity_a,
            entity_b,
            state_a.state if state_a else "missing",
            state_b.state if state_b else "missing",
        )

        def _invalidate(reason: str) -> PairState:
            # If invalidated while in proximity, close the session to avoid crediting
            # unavailability window as proximity time on next valid observation.
            was_prox = ps.proximity
            if ps.proximity and ps.proximity_since:
                elapsed = max(0.0, (now - ps.proximity_since).total_seconds())
                ps.proximity_duration_s += elapsed
                # Only credit today counters when the date rolled — same-day invalidation
                # must not double-count time already accumulated tick-by-tick.
                inv_date_rolled = ps.today_reset_date is None or ps.today_reset_date != now.date()
                if inv_date_rolled:
                    ps.today_proximity_seconds = 0.0
                    ps.today_zone_seconds = {}
                    ps.today_reset_date = now.date()
                    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    midnight_utc = midnight.astimezone(UTC)
                    prox_since_utc = ps.proximity_since.astimezone(UTC)
                    pre_inv = max(0.0, (midnight_utc - prox_since_utc).total_seconds())
                    post_inv = max(0.0, elapsed - pre_inv)
                    ps.today_proximity_seconds += post_inv
                    if ps.distance_m is not None and post_inv > 0:
                        inv_bucket = calc_bucket(ps.distance_m, self._bucket_thresholds)
                        ps.today_zone_seconds[inv_bucket] = (
                            ps.today_zone_seconds.get(inv_bucket, 0.0) + post_inv
                        )
                # same day: today counters already reflect prior ticks via _elapsed_s
            ps.proximity = False
            ps.proximity_since = None
            ps.data_valid = False
            ps.last_error = reason
            ps.prev_calc_time = None
            ps.prev_distance_m = None
            if was_prox:
                self.hass.bus.fire(
                    EVENT_LEAVE,
                    {
                        "entity_a": entity_a,
                        "entity_b": entity_b,
                        "distance_m": ps.distance_m,
                        "entry_threshold_m": self._entry_threshold_m,
                        "exit_threshold_m": self._exit_threshold_m,
                        "reliable": False,
                        "direction": None,
                        "closing_speed_kmh": None,
                    },
                )
            return ps

        if state_a is None or state_b is None:
            _LOGGER.warning("entity_distance: pair (%s, %s) — entity not found", entity_a, entity_b)
            return _invalidate("entity_not_found")

        if state_a.state in (STATE_UNAVAILABLE, STATE_UNKNOWN) or state_b.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            return _invalidate("entity_unavailable")

        coords_a = _get_coords(state_a)
        coords_b = _get_coords(state_b)

        if coords_a is None or coords_b is None:
            return _invalidate("coord_extraction_failed")

        lat_a, lon_a, acc_a = coords_a
        lat_b, lon_b, acc_b = coords_b

        is_zone_a = _is_zone(state_a)
        is_zone_b = _is_zone(state_b)

        if (
            not is_zone_a
            and acc_a is not None
            and self._max_accuracy_m > 0
            and acc_a > self._max_accuracy_m
        ):
            _LOGGER.warning(
                "entity_distance: accuracy filter rejected %s (acc=%.1fm > max=%.1fm)",
                entity_a,
                acc_a,
                self._max_accuracy_m,
            )
            return _invalidate("accuracy_filter_a")

        if (
            not is_zone_b
            and acc_b is not None
            and self._max_accuracy_m > 0
            and acc_b > self._max_accuracy_m
        ):
            _LOGGER.warning(
                "entity_distance: accuracy filter rejected %s (acc=%.1fm > max=%.1fm)",
                entity_b,
                acc_b,
                self._max_accuracy_m,
            )
            return _invalidate("accuracy_filter_b")

        dist_m = ha_distance(lat_a, lon_a, lat_b, lon_b)
        if dist_m is None or not (0 <= dist_m < float("inf")):
            _LOGGER.error(
                "entity_distance: ha_distance returned invalid value %r for pair (%s, %s)",
                dist_m,
                entity_a,
                entity_b,
            )
            return _invalidate("ha_distance_invalid")

        _LOGGER.debug(
            "entity_distance: pair (%s, %s) dist=%.1fm a_acc=%s b_acc=%s",
            entity_a,
            entity_b,
            dist_m,
            f"{acc_a:.1f}m" if acc_a is not None else "none",
            f"{acc_b:.1f}m" if acc_b is not None else "none",
        )

        if (
            not is_zone_a
            and not is_zone_b
            and ps.prev_distance_m is not None
            and ps.prev_calc_time is not None
            and self._max_speed_kmh > 0
        ):
            delta_s = max(0.0, (now - ps.prev_calc_time).total_seconds())
            if delta_s >= 5.0:
                implied_speed_kmh = abs(dist_m - ps.prev_distance_m) / delta_s * 3.6
                if implied_speed_kmh > self._max_speed_kmh:
                    _LOGGER.warning(
                        "entity_distance: speed filter rejected pair (%s, %s) — %.1f km/h > max %.1f km/h",
                        entity_a,
                        entity_b,
                        implied_speed_kmh,
                        self._max_speed_kmh,
                    )
                    return _invalidate("speed_filter")

        direction: str | None = None
        closing_speed_kmh: float | None = None
        eta_minutes: float | None = None

        if ps.prev_distance_m is not None and ps.prev_calc_time is not None:
            delta_m = dist_m - ps.prev_distance_m
            delta_s = max(0.0, (now - ps.prev_calc_time).total_seconds())

            if abs(delta_m) < STATIONARY_THRESHOLD_M:
                direction = DIRECTION_STATIONARY
            elif delta_m < 0:
                direction = DIRECTION_APPROACHING
            else:
                direction = DIRECTION_DIVERGING

            if delta_s > 0:
                closing_speed_kmh = abs(delta_m / delta_s) * 3.6
                if direction == DIRECTION_APPROACHING and closing_speed_kmh > 0:
                    closing_speed_m_per_s = closing_speed_kmh / 3.6
                    eta_minutes = dist_m / closing_speed_m_per_s / 60
                    eta_minutes = min(eta_minutes, 1440.0)

        was_proximity = ps.proximity

        # Capture baseline distance/time before writing new values so C3 flush
        # and speed filter use the correct previous-tick values.
        prev_distance_m_snapshot = ps.prev_distance_m
        prev_calc_time_snapshot = ps.prev_calc_time

        ps.distance_m = dist_m
        ps.prev_distance_m = dist_m
        ps.prev_calc_time = now
        ps.direction = direction
        ps.closing_speed_kmh = closing_speed_kmh
        ps.eta_minutes = eta_minutes
        ps.accuracy_a = acc_a
        ps.accuracy_b = acc_b
        ps.data_valid = True
        ps.last_error = None

        reliable = self._is_reliable(ps)

        # Resync silence — check before proximity transitions so hold returns early
        # without mutating ps.proximity, preventing EVENT_ENTER from being lost.
        # Skip for zone entities — zones never emit state_changed so staleness is
        # always huge; treating that as a resync condition causes a permanent loop.
        if (
            self._resync_silence_s > 0
            and not is_zone_a
            and not is_zone_b
            and ps.last_update_a is not None
            and ps.last_update_b is not None
        ):
            staleness_a = (now - ps.last_update_a).total_seconds()
            staleness_b = (now - ps.last_update_b).total_seconds()
            if (
                staleness_a >= self._resync_silence_s
                and staleness_b >= self._resync_silence_s
                and not self._resync_holding.get(k, False)
            ):
                self._resync_holding[k] = True
                self._resync_hold_until[k] = now + timedelta(seconds=self._resync_hold_s)
                _LOGGER.debug(
                    "entity_distance: resync silence detected for pair (%s, %s) — holding for %.0fs",
                    entity_a,
                    entity_b,
                    self._resync_hold_s,
                )

        if self._resync_holding.get(k, False):
            hold_until = self._resync_hold_until.get(k)
            if hold_until and now < hold_until:
                _LOGGER.debug(
                    "entity_distance: in resync hold for pair (%s, %s)", entity_a, entity_b
                )
                # Close any open proximity session before returning — the hold window
                # should not be counted as valid proximity time.
                if ps.proximity and ps.proximity_since:
                    elapsed = max(0.0, (now - ps.proximity_since).total_seconds())
                    ps.proximity_duration_s += elapsed
                    # Only credit today counters when the date rolled — same-day hold must
                    # not double-count time already accumulated tick-by-tick in today_proximity_seconds.
                    hold_date_rolled = (
                        ps.today_reset_date is None or ps.today_reset_date != now.date()
                    )
                    if hold_date_rolled:
                        ps.today_proximity_seconds = 0.0
                        ps.today_zone_seconds = {}
                        ps.today_reset_date = now.date()
                        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                        midnight_utc = midnight.astimezone(UTC)
                        prox_since_utc = ps.proximity_since.astimezone(UTC)
                        pre_hold = max(0.0, (midnight_utc - prox_since_utc).total_seconds())
                        post_hold = max(0.0, elapsed - pre_hold)
                        ps.today_proximity_seconds += post_hold
                        if ps.distance_m is not None and post_hold > 0:
                            hold_bucket = calc_bucket(ps.distance_m, self._bucket_thresholds)
                            ps.today_zone_seconds[hold_bucket] = (
                                ps.today_zone_seconds.get(hold_bucket, 0.0) + post_hold
                            )
                    ps.proximity = False
                    ps.proximity_since = None
                    self.hass.bus.fire(
                        EVENT_LEAVE,
                        {
                            "entity_a": entity_a,
                            "entity_b": entity_b,
                            "distance_m": ps.distance_m,
                            "entry_threshold_m": self._entry_threshold_m,
                            "exit_threshold_m": self._exit_threshold_m,
                            "reliable": False,
                            "direction": None,
                            "closing_speed_kmh": None,
                        },
                    )
                # Null the baseline so the first post-hold tick doesn't trigger a
                # spurious speed-filter rejection against a stale prev_distance_m.
                ps.prev_calc_time = None
                ps.prev_distance_m = None
                ps.data_valid = False
                return ps
            self._resync_holding[k] = False
            self._resync_hold_until[k] = None
            # Reset staleness clocks so the hold doesn't re-arm immediately on
            # the very next tick — treat hold expiry as a fresh observation.
            ps.last_update_a = now
            ps.last_update_b = now

        # Proximity transitions — after hold check so early-return doesn't leave
        # ps.proximity mutated without a corresponding event being fired.
        if not ps.proximity and dist_m <= self._entry_threshold_m:
            ps.proximity = True
            ps.proximity_since = now
            if ps.proximity_tracking_started is None:
                ps.proximity_tracking_started = now
        elif ps.proximity and dist_m > self._exit_threshold_m:
            ps.proximity = False
            if ps.proximity_since:
                ps.proximity_duration_s += (now - ps.proximity_since).total_seconds()
            ps.proximity_since = None

        # Stamp last_seen_together on every in-proximity tick and on EXIT so it
        # always reflects the last confirmed time they were within the exit threshold.
        if was_proximity:
            ps.last_seen_together = now

        if self._require_reliable and not reliable and not was_proximity and ps.proximity:
            ps.proximity = False
            ps.proximity_since = None
            _LOGGER.debug(
                "entity_distance: proximity entry blocked for pair (%s, %s) — not yet reliable",
                entity_a,
                entity_b,
            )

        # Daily reset with cross-midnight flush.
        # Zero daily counters first, then write the pre-midnight slice, so the
        # flush data is not overwritten by the reset (bug: previously zeroed after writing).
        # Use was_proximity and prev_distance_m_snapshot so flags/bucket reflect the
        # previous tick, not the current one.
        # Guard flush on original_reset_date (before overwrite) to avoid stale prev_calc_time
        # from a cross-day restart inflating today's counters.
        today = now.date()
        date_rolled = ps.today_reset_date != today
        original_reset_date = ps.today_reset_date
        if date_rolled:
            ps.today_proximity_seconds = 0.0
            ps.today_zone_seconds = {}
            ps.today_reset_date = today
            if prev_calc_time_snapshot is not None and original_reset_date is not None:
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                midnight_utc = midnight.astimezone(UTC)
                if was_proximity and ps.proximity_since is not None:
                    # Use proximity_since as start of the proximity slice so the
                    # full session since entry (not just last tick) is credited.
                    prox_since_utc = ps.proximity_since.astimezone(UTC)
                    prox_pre_midnight = max(0.0, (midnight_utc - prox_since_utc).total_seconds())
                    ps.proximity_duration_s += prox_pre_midnight
                    # Advance proximity_since to midnight so the EXIT handler on
                    # this tick does not re-count the pre-midnight interval.
                    ps.proximity_since = midnight
                # Pre-midnight zone seconds are yesterday's data — do NOT write to
                # today's today_zone_seconds (which was just zeroed). The post-midnight
                # slice is credited correctly by the _elapsed_s block below.

        # Accumulate today totals using the finalised proximity state (after reliability check).
        # When the date rolled, count only from midnight to now (post-midnight portion).
        _elapsed_s: float = 0.0
        if prev_calc_time_snapshot is not None:
            if date_rolled:
                midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
                _elapsed_s = max(
                    0.0,
                    (now.astimezone(UTC) - midnight.astimezone(UTC)).total_seconds(),
                )
            else:
                _elapsed_s = max(0.0, (now - prev_calc_time_snapshot).total_seconds())

        if _elapsed_s > 0:
            # Bucket time accumulates regardless of proximity — sensors report
            # time-at-distance for each zone, not time-in-proximity-at-distance.
            # On EXIT tick, _elapsed_s covers time when pair was inside threshold —
            # use prev_distance_m_snapshot (the proximity-era distance) for the bucket.
            bucket_for_elapsed = calc_bucket(
                prev_distance_m_snapshot
                if was_proximity and prev_distance_m_snapshot is not None
                else dist_m,
                self._bucket_thresholds,
            )
            ps.today_zone_seconds[bucket_for_elapsed] = (
                ps.today_zone_seconds.get(bucket_for_elapsed, 0.0) + _elapsed_s
            )
            if ps.proximity or was_proximity:
                ps.today_proximity_seconds += _elapsed_s

        event_data = {
            "entity_a": entity_a,
            "entity_b": entity_b,
            "distance_m": dist_m,
            "entry_threshold_m": self._entry_threshold_m,
            "exit_threshold_m": self._exit_threshold_m,
            "reliable": reliable,
            "direction": direction,
            "closing_speed_kmh": closing_speed_kmh,
        }

        if not was_proximity and ps.proximity:
            event = EVENT_ENTER if reliable else EVENT_ENTER_UNRELIABLE
            self.hass.bus.fire(event, event_data)
            _LOGGER.debug("entity_distance: fired %s for pair (%s, %s)", event, entity_a, entity_b)
        elif was_proximity and not ps.proximity:
            self.hass.bus.fire(EVENT_LEAVE, event_data)
        else:
            self.hass.bus.fire(EVENT_UPDATE, event_data)

        return ps

    def _advance_window(
        self, count: int, window_start: datetime | None, now: datetime
    ) -> tuple[int, datetime]:
        """Advance the rolling-window update counter for one side of a pair.

        Returns (new_count, new_window_start). When the window is unset or
        elapsed past `_updates_window_s`, the count restarts at 1 and the
        window anchors at `now`. The count and window-reset boundaries are
        deliberately co-located here — splitting them across two helpers (as
        an earlier refactor did) made it possible to drift the `>` boundary
        on one side without the other.
        """
        if window_start is None or (now - window_start).total_seconds() > self._updates_window_s:
            return 1, now
        return count + 1, window_start

    def _is_reliable(self, ps: PairState) -> bool:
        return (
            ps.update_count_a >= self._min_updates_reliable
            and ps.update_count_b >= self._min_updates_reliable
        )

    async def _async_update_data(self) -> GroupData:
        valid_pairs = [
            ps for ps in self._pair_states.values() if ps.data_valid and ps.distance_m is not None
        ]
        min_dist: float | None = min((ps.distance_m for ps in valid_pairs), default=None)
        any_prox = any(ps.proximity for ps in self._pair_states.values() if ps.data_valid)
        all_prox = (
            bool(valid_pairs)
            and len(valid_pairs) == len(self._pair_states)
            and all(ps.proximity for ps in valid_pairs)
        )
        return GroupData(
            pairs=dict(self._pair_states),
            min_distance_m=min_dist,
            any_in_proximity=any_prox,
            all_in_proximity=all_prox,
        )

    async def _async_save_state(self) -> None:
        payload: dict = {}
        for k, ps in self._pair_states.items():
            today = ps.today_reset_date
            payload[f"{k[0]}__{k[1]}"] = {
                "today_reset_date": today.isoformat() if today else None,
                "today_proximity_seconds": ps.today_proximity_seconds,
                "today_zone_seconds": ps.today_zone_seconds,
                "proximity_duration_s": ps.proximity_duration_s,
                "proximity_tracking_started": ps.proximity_tracking_started.isoformat()
                if ps.proximity_tracking_started
                else None,
                "last_seen_together": ps.last_seen_together.isoformat()
                if ps.last_seen_together
                else None,
                "proximity_since": ps.proximity_since.isoformat() if ps.proximity_since else None,
                "prev_calc_time": ps.prev_calc_time.isoformat() if ps.prev_calc_time else None,
                "last_bucket": calc_bucket(ps.distance_m, self._bucket_thresholds)
                if ps.distance_m is not None
                else None,
            }
        await self._store.async_save(payload)

    async def _async_load_state(self) -> None:
        stored = await self._store.async_load()
        if not stored:
            return
        now_load = dt_util.now()
        today = now_load.date()
        for k, ps in self._pair_states.items():
            try:
                store_key = f"{k[0]}__{k[1]}"
                blob = stored.get(store_key)
                if not blob:
                    continue
                stored_date_str = blob.get("today_reset_date")
                if stored_date_str:
                    stored_date = date.fromisoformat(stored_date_str)
                    if stored_date == today:
                        ps.today_proximity_seconds = float(blob.get("today_proximity_seconds", 0.0))
                        ps.today_zone_seconds = dict(blob.get("today_zone_seconds", {}))
                        ps.today_reset_date = stored_date
                last_seen_str = blob.get("last_seen_together")
                if last_seen_str:
                    ps.last_seen_together = datetime.fromisoformat(last_seen_str)
                ps.proximity_duration_s = float(blob.get("proximity_duration_s", 0.0))
                tracking_started_str = blob.get("proximity_tracking_started")
                if tracking_started_str:
                    ps.proximity_tracking_started = datetime.fromisoformat(tracking_started_str)
                proximity_since_str = blob.get("proximity_since")
                if proximity_since_str:
                    ps.proximity_since = datetime.fromisoformat(proximity_since_str)
                    ps.proximity = True
                    # Anchor on prev_calc_time so same-day restarts don't double-count
                    # time already reflected in the stored proximity_duration_s.
                    prev_calc_time_str = blob.get("prev_calc_time")
                    gap_anchor = (
                        datetime.fromisoformat(prev_calc_time_str)
                        if prev_calc_time_str
                        else ps.proximity_since
                    )
                    gap_s = max(0.0, (now_load - gap_anchor).total_seconds())
                    ps.proximity_duration_s += gap_s
                    # Split at midnight: only post-midnight portion belongs to today.
                    # Route through UTC to avoid DST boundary errors.
                    midnight = now_load.replace(hour=0, minute=0, second=0, microsecond=0)
                    midnight_utc = midnight.astimezone(UTC)
                    gap_anchor_utc = gap_anchor.astimezone(UTC)
                    now_load_utc = now_load.astimezone(UTC)
                    today_anchor_utc = max(gap_anchor_utc, midnight_utc)
                    post_midnight_s = max(0.0, (now_load_utc - today_anchor_utc).total_seconds())
                    ps.today_reset_date = today
                    ps.today_proximity_seconds += post_midnight_s
                    # Credit zone bucket for the restart gap using persisted last_bucket.
                    last_bucket = blob.get("last_bucket")
                    if last_bucket is not None and post_midnight_s > 0:
                        ps.today_zone_seconds[last_bucket] = (
                            ps.today_zone_seconds.get(last_bucket, 0.0) + post_midnight_s
                        )
                    # Advance proximity_since to now_load so the next EXIT does not
                    # double-count the already-credited interval.
                    ps.proximity_since = now_load
                    # Set prev_calc_time to now_load so the first tick's date-rolled
                    # block does not try to flush a stale pre-restart prev_calc_time.
                    ps.prev_calc_time = now_load
                else:
                    prev_calc_time_str = blob.get("prev_calc_time")
                    if prev_calc_time_str:
                        ps.prev_calc_time = datetime.fromisoformat(prev_calc_time_str)
            except Exception:  # noqa: BLE001
                _LOGGER.warning(
                    "entity_distance: failed to restore persisted state for pair %s, starting fresh",
                    k,
                    exc_info=True,
                )
                # Reset to a clean state so corrupt data doesn't leave proximity=True
                # with a stale proximity_since that inflates counters on next EXIT.
                self._pair_states[k] = PairState(entity_a_id=k[0], entity_b_id=k[1])
