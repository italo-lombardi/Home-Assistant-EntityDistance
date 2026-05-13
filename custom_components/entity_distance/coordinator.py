from __future__ import annotations

from datetime import datetime, date, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.location import distance as ha_distance

from .const import (
    BUCKET_FAR,
    BUCKET_MID,
    BUCKET_NEAR,
    BUCKET_VERY_FAR,
    BUCKET_VERY_NEAR,
    CONF_DEBOUNCE_S,
    CONF_ENTITY_A,
    CONF_ENTITY_B,
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
    UPDATES_FREQUENCY_WINDOW_S,
)
from .models import PairData, PairState

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
        _LOGGER.warning("entity_distance: cannot extract coords from %s", state.entity_id)
        return None

    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        _LOGGER.warning(
            "entity_distance: invalid coords for %s: lat=%s lon=%s",
            state.entity_id,
            lat,
            lon,
        )
        return None

    try:
        accuracy = float(attrs["gps_accuracy"])
    except (KeyError, TypeError, ValueError):
        accuracy = None

    return lat, lon, accuracy


def _calc_bucket(distance_m: float, thresholds: dict[str, float]) -> str:
    for bucket, threshold in thresholds.items():
        if distance_m <= threshold:
            return bucket
    return BUCKET_VERY_FAR


class EntityDistanceCoordinator(DataUpdateCoordinator[PairData]):
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
        self._entity_a: str = data[CONF_ENTITY_A]
        self._entity_b: str = data[CONF_ENTITY_B]
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

        self._pair_state = PairState(
            entity_a_id=self._entity_a,
            entity_b_id=self._entity_b,
        )
        self._resync_holding: bool = False
        self._resync_hold_until: datetime | None = None
        self._store: Store = Store(hass, 1, f"{DOMAIN}_state_{entry.entry_id}")

    @property
    def bucket_thresholds(self) -> dict[str, float]:
        return self._bucket_thresholds

    async def async_setup(self) -> None:
        await self._async_load_state()

        self._debouncer = Debouncer(
            self.hass,
            _LOGGER,
            cooldown=self._debounce_s,
            immediate=False,
            function=self._async_recalculate,
        )

        unsub_a = async_track_state_change_event(
            self.hass, [self._entity_a], self._async_state_changed
        )
        unsub_b = async_track_state_change_event(
            self.hass, [self._entity_b], self._async_state_changed
        )
        unsub_tick = async_track_time_interval(
            self.hass, self._async_tick, timedelta(minutes=1)
        )
        self._unsub_listeners = [unsub_a, unsub_b, unsub_tick]
        _LOGGER.debug("entity_distance: tracking %s and %s", self._entity_a, self._entity_b)

    @callback
    def async_unload(self) -> None:
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()
        if self._debouncer:
            self._debouncer.async_cancel()
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
        now = datetime.now().astimezone()
        if entity_id == self._entity_a:
            self._pair_state.last_update_a = now
        elif entity_id == self._entity_b:
            self._pair_state.last_update_b = now
        self.hass.async_create_task(self._debouncer.async_call())

    async def _async_recalculate(self) -> None:
        state_a = self.hass.states.get(self._entity_a)
        state_b = self.hass.states.get(self._entity_b)

        ps = self._pair_state
        now = datetime.now().astimezone()

        if state_a is None or state_b is None:
            _LOGGER.warning("entity_distance: one or both entities not found")
            ps.data_valid = False
            self.async_set_updated_data(PairData(pair=ps))
            return

        if state_a.state in (STATE_UNAVAILABLE, STATE_UNKNOWN) or state_b.state in (
            STATE_UNAVAILABLE,
            STATE_UNKNOWN,
        ):
            _LOGGER.warning(
                "entity_distance: entity unavailable — a=%s b=%s",
                state_a.state,
                state_b.state,
            )
            ps.data_valid = False
            self.async_set_updated_data(PairData(pair=ps))
            return

        coords_a = _get_coords(state_a)
        coords_b = _get_coords(state_b)

        if coords_a is None or coords_b is None:
            ps.data_valid = False
            ps.last_error = "coord_extraction_failed"
            self.async_set_updated_data(PairData(pair=ps))
            return

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
                self._entity_a,
                acc_a,
                self._max_accuracy_m,
            )
            self.async_set_updated_data(PairData(pair=ps))
            return

        if (
            not is_zone_b
            and acc_b is not None
            and self._max_accuracy_m > 0
            and acc_b > self._max_accuracy_m
        ):
            _LOGGER.warning(
                "entity_distance: accuracy filter rejected %s (acc=%.1fm > max=%.1fm)",
                self._entity_b,
                acc_b,
                self._max_accuracy_m,
            )
            self.async_set_updated_data(PairData(pair=ps))
            return

        dist_m = ha_distance(lat_a, lon_a, lat_b, lon_b)
        if dist_m is None:
            _LOGGER.error(
                "entity_distance: ha_distance returned None for %s/%s",
                self._entity_a,
                self._entity_b,
            )
            ps.data_valid = False
            self.async_set_updated_data(PairData(pair=ps))
            return

        if (
            not is_zone_a
            and not is_zone_b
            and ps.prev_distance_m is not None
            and ps.prev_calc_time is not None
            and self._max_speed_kmh > 0
        ):
            delta_s = (now - ps.prev_calc_time).total_seconds()
            if delta_s > 0:
                implied_speed_kmh = abs(dist_m - ps.prev_distance_m) / delta_s * 3.6
                if implied_speed_kmh > self._max_speed_kmh:
                    _LOGGER.warning(
                        "entity_distance: speed filter rejected update (%.1f km/h > max %.1f km/h)",
                        implied_speed_kmh,
                        self._max_speed_kmh,
                    )
                    self.async_set_updated_data(PairData(pair=ps))
                    return

        direction: str | None = None
        closing_speed_kmh: float | None = None
        eta_minutes: float | None = None

        if ps.prev_distance_m is not None and ps.prev_calc_time is not None:
            delta_m = dist_m - ps.prev_distance_m
            delta_s = (now - ps.prev_calc_time).total_seconds()

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

        was_proximity = ps.proximity
        if not ps.proximity and dist_m <= self._entry_threshold_m:
            ps.proximity = True
            ps.proximity_since = now
            ps.last_seen_together = now
        elif ps.proximity and dist_m > self._exit_threshold_m:
            ps.proximity = False
            if ps.proximity_since:
                ps.proximity_duration_s += (now - ps.proximity_since).total_seconds()
            ps.proximity_since = None

        today = now.date()
        if ps.today_reset_date != today:
            ps.today_proximity_seconds = 0.0
            ps.today_zone_seconds = {}
            ps.today_reset_date = today

        if ps.prev_calc_time is not None:
            elapsed = (now - ps.prev_calc_time).total_seconds()
            if ps.proximity:
                ps.today_proximity_seconds += elapsed
            current_bucket = _calc_bucket(dist_m, self._bucket_thresholds)
            ps.today_zone_seconds[current_bucket] = (
                ps.today_zone_seconds.get(current_bucket, 0.0) + elapsed
            )

        ps.update_count_a = self._update_frequency(ps.update_count_a, ps.update_window_start_a, now)
        if (
            ps.update_window_start_a is None
            or (now - ps.update_window_start_a).total_seconds() > UPDATES_FREQUENCY_WINDOW_S
        ):
            ps.update_window_start_a = now

        ps.update_count_b = self._update_frequency(ps.update_count_b, ps.update_window_start_b, now)
        if (
            ps.update_window_start_b is None
            or (now - ps.update_window_start_b).total_seconds() > UPDATES_FREQUENCY_WINDOW_S
        ):
            ps.update_window_start_b = now

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

        # resync silence: if both entities silent for resync_silence_s, hold updates
        if (
            self._resync_silence_s > 0
            and ps.last_update_a is not None
            and ps.last_update_b is not None
        ):
            staleness_a = (now - ps.last_update_a).total_seconds()
            staleness_b = (now - ps.last_update_b).total_seconds()
            if (
                staleness_a >= self._resync_silence_s
                and staleness_b >= self._resync_silence_s
                and not self._resync_holding
            ):
                self._resync_holding = True
                self._resync_hold_until = datetime.fromtimestamp(
                    now.timestamp() + self._resync_hold_s, tz=now.tzinfo
                )
                _LOGGER.warning(
                    "entity_distance: resync silence detected — holding updates for %.0fs",
                    self._resync_hold_s,
                )

        if self._resync_holding and self._resync_hold_until:
            if now < self._resync_hold_until:
                _LOGGER.debug("entity_distance: in resync hold, skipping update")
                self.async_set_updated_data(PairData(pair=ps))
                return
            self._resync_holding = False
            self._resync_hold_until = None

        # require_reliable: block proximity=True entry when data unreliable
        if self._require_reliable and not reliable and not was_proximity and ps.proximity:
            ps.proximity = False
            ps.proximity_since = None
            _LOGGER.debug("entity_distance: proximity entry blocked — data not yet reliable")
        event_data = {
            "entity_a": self._entity_a,
            "entity_b": self._entity_b,
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
            _LOGGER.debug("entity_distance: fired %s", event)
        elif was_proximity and not ps.proximity:
            self.hass.bus.fire(EVENT_LEAVE, event_data)
            _LOGGER.debug("entity_distance: fired %s", EVENT_LEAVE)
        else:
            self.hass.bus.fire(EVENT_UPDATE, event_data)

        self.async_set_updated_data(PairData(pair=ps))
        await self._async_save_state()

    def _update_frequency(self, count: int, window_start: datetime | None, now: datetime) -> int:
        if window_start is None:
            return 1
        elapsed = (now - window_start).total_seconds()
        if elapsed > UPDATES_FREQUENCY_WINDOW_S:
            return 1  # caller must reset window_start too
        return count + 1

    def _is_reliable(self, ps: PairState) -> bool:
        return (
            ps.update_count_a >= self._min_updates_reliable
            and ps.update_count_b >= self._min_updates_reliable
        )

    async def _async_update_data(self) -> PairData:
        return PairData(pair=self._pair_state)

    async def _async_save_state(self) -> None:
        ps = self._pair_state
        today = ps.today_reset_date
        await self._store.async_save({
            "today_reset_date": today.isoformat() if today else None,
            "today_proximity_seconds": ps.today_proximity_seconds,
            "today_zone_seconds": ps.today_zone_seconds,
            "proximity_duration_s": ps.proximity_duration_s,
            "last_seen_together": ps.last_seen_together.isoformat() if ps.last_seen_together else None,
        })

    async def _async_load_state(self) -> None:
        stored = await self._store.async_load()
        if not stored:
            return
        try:
            stored_date_str = stored.get("today_reset_date")
            if not stored_date_str:
                return
            stored_date = date.fromisoformat(stored_date_str)
            today = datetime.now().astimezone().date()
            ps = self._pair_state
            if stored_date == today:
                ps.today_proximity_seconds = float(stored.get("today_proximity_seconds", 0.0))
                ps.today_zone_seconds = dict(stored.get("today_zone_seconds", {}))
                ps.today_reset_date = stored_date
            last_seen_str = stored.get("last_seen_together")
            if last_seen_str:
                ps.last_seen_together = datetime.fromisoformat(last_seen_str)
            ps.proximity_duration_s = float(stored.get("proximity_duration_s", 0.0))
        except Exception:
            _LOGGER.warning("entity_distance: failed to restore persisted state, starting fresh")
