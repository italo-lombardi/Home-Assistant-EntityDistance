from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


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
    last_seen_together: datetime | None = None

    today_proximity_seconds: float = 0.0
    today_reset_date: date | None = None

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
class PairData:
    pair: PairState
