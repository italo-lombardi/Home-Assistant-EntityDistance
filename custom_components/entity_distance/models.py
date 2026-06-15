from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

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

    direction: str | None = None
    closing_speed_kmh: float | None = None
    eta_minutes: float | None = None

    proximity: bool = False
    proximity_since: datetime | None = None
    proximity_duration_s: float = 0.0
    proximity_tracking_started: datetime | None = None
    last_seen_together: datetime | None = None

    today_proximity_seconds: float = 0.0
    today_reset_date: date | None = None
    today_zone_seconds: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        pass

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


@dataclass
class GroupData:
    """Coordinator data for a group of entities (one or more pairs)."""

    pairs: dict[tuple[str, str], PairState] = field(default_factory=dict)
    min_distance_m: float | None = None
    any_in_proximity: bool = False
    all_in_proximity: bool = False
