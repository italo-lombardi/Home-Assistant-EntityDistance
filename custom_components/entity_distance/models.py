from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from homeassistant.core import HomeAssistant, State

_HOME_ZONE_ENTITY_ID = "zone.home"


def _zone_match_value(entity_id: str, state: State) -> str:
    """Value to compare against the other side's tracker state for same-zone matching.

    Mirrors the logic in HA's device_tracker.entity (see
    homeassistant/components/device_tracker/legacy.py – async_update_listeners /
    _async_update_zone_state in core; search for STATE_HOME and zone.name handling).
    If HA changes how tracker states are derived from zone names, update here too.

      - zone.home → literal "home" (STATE_HOME)
      - any other zone → State.name (friendly_name, falls back to object_id)
      - non-zone entity → its raw state
    """
    if not entity_id.startswith("zone."):
        return state.state
    if entity_id == _HOME_ZONE_ENTITY_ID:
        return "home"
    # State.name returns the configured friendly_name, or object_id if unset.
    return state.name


_DOMAIN_PRIORITY: dict[str, int] = {
    "person": 0,
    "device_tracker": 1,
    "zone": 2,
    "sensor": 3,
}


def _entity_priority(entity_id: str) -> tuple[int, str]:
    domain = entity_id.split(".")[0]
    return (_DOMAIN_PRIORITY.get(domain, 99), entity_id)


def pair_key(a: str, b: str) -> tuple[str, str]:
    """Return a stable priority-ordered tuple key for an entity pair."""
    ordered = sorted([a, b], key=_entity_priority)
    return (ordered[0], ordered[1])


@dataclass
class PairState:
    entity_a_id: str
    entity_b_id: str

    distance_m: float | None = None
    prev_distance_m: float | None = None
    prev_calc_time: datetime | None = None
    # Bucket of the last valid distance. Persisted so a cross-midnight _invalidate()
    # credits the correct zone even after distance_m may have been superseded.
    last_bucket: str | None = None

    direction: str | None = None
    closing_speed_kmh: float | None = None
    eta_minutes: float | None = None

    proximity: bool = False
    proximity_since: datetime | None = None
    proximity_duration_s: float = 0.0
    proximity_tracking_started: datetime | None = None
    last_seen_together: datetime | None = None
    # Last proximity value while the pair was valid. Read by binary sensors during
    # the display grace window so in_proximity holds its last on/off instead of
    # dropping to off the instant a fix is missed. Accrual never reads this.
    last_proximity: bool = False

    today_proximity_seconds: float = 0.0
    today_reset_date: date | None = None
    today_zone_seconds: dict[str, float] = field(default_factory=dict)

    altitude_a_m: float | None = None
    altitude_b_m: float | None = None
    altitude_delta_m: float | None = None
    # GPS attributes read directly from device tracker (via person source fallback for person entities).
    # Not persisted — ephemeral readings with no meaningful grace-window value.
    speed_a_kmh: float | None = None
    speed_b_kmh: float | None = None
    heading_a_deg: float | None = None
    heading_b_deg: float | None = None
    vertical_accuracy_a_m: float | None = None
    vertical_accuracy_b_m: float | None = None

    accuracy_a: float | None = None
    accuracy_b: float | None = None
    last_update_a: datetime | None = None
    last_update_b: datetime | None = None

    update_count_a: int = 0
    update_count_b: int = 0
    update_window_start_a: datetime | None = None
    update_window_start_b: datetime | None = None

    data_valid: bool = False
    last_error: str | None = None
    # When the pair first went invalid while it had prior valid data. Drives the
    # display grace window (show last value instead of unknown). None when valid.
    stale_since: datetime | None = None


@dataclass
class GroupData:
    """Coordinator data for a group of entities (one or more pairs)."""

    pairs: dict[tuple[str, str], PairState] = field(default_factory=dict)
    min_distance_m: float | None = None
    any_in_proximity: bool = False
    all_in_proximity: bool = False


def friendly_name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    if state and state.name:
        return state.name
    return entity_id.split(".")[-1].replace("_", " ").title()
