from __future__ import annotations

from datetime import UTC, datetime
import itertools
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfLength, UnitOfSpeed, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    BUCKET_FAR,
    BUCKET_MID,
    BUCKET_NEAR,
    BUCKET_VERY_FAR,
    BUCKET_VERY_NEAR,
    BUCKETS,
    DIRECTION_APPROACHING,
    DIRECTION_DIVERGING,
    DIRECTION_STATIONARY,
    DIRECTIONS,
    DOMAIN,
)
from .coordinator import EntityDistanceCoordinator, calc_bucket
from .models import PairState, pair_key

_LOGGER = logging.getLogger(__name__)


_BUCKET_LEVEL = {
    BUCKET_VERY_NEAR: 1,
    BUCKET_NEAR: 2,
    BUCKET_MID: 3,
    BUCKET_FAR: 4,
    BUCKET_VERY_FAR: 5,
}

_DIRECTION_LEVEL = {
    DIRECTION_APPROACHING: -1,
    DIRECTION_STATIONARY: 0,
    DIRECTION_DIVERGING: 1,
}


def _group_device_info(entry: ConfigEntry, group_name: str) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"Entity Distance — {group_name}",
        manufacturer="Entity Distance",
        entry_type=DeviceEntryType.SERVICE,
    )


def _pair_device_info(
    entry: ConfigEntry, pair_key_val: tuple[str, str], a_name: str, b_name: str
) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{pair_key_val[0]}__{pair_key_val[1]}")},
        name=f"{a_name} & {b_name}",
        manufacturer="Entity Distance",
        entry_type=DeviceEntryType.SERVICE,
        via_device=(DOMAIN, entry.entry_id),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: EntityDistanceCoordinator = hass.data[DOMAIN][entry.entry_id]

    def _friendly_name(entity_id: str) -> str:
        state = hass.states.get(entity_id)
        if state and state.name:
            return state.name
        return entity_id.split(".")[-1].replace("_", " ").title()

    entities_list = coordinator.entities
    group_name = " & ".join(_friendly_name(e) for e in entities_list)

    _LOGGER.debug(
        "entity_distance: sensor platform setup — entry=%s entities=%s",
        entry.entry_id,
        entities_list,
    )

    all_sensors: list = []

    # Pre-register group device so pair devices can reference it via via_device.
    try:
        dev_reg = dr.async_get(hass)
        dev_reg.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Entity Distance — {group_name}",
            manufacturer="Entity Distance",
            entry_type=DeviceEntryType.SERVICE,
        )
    except Exception:  # noqa: BLE001
        pass

    for a, b in itertools.combinations(entities_list, 2):
        k = pair_key(a, b)
        a_name = _friendly_name(k[0])
        b_name = _friendly_name(k[1])
        pair_dev = _pair_device_info(entry, k, a_name, b_name)
        is_zone_pair = k[0].startswith("zone.") and k[1].startswith("zone.")
        if is_zone_pair:
            all_sensors.extend(
                [
                    DistanceSensor(coordinator, entry, pair_dev, k),
                    BucketSensor(coordinator, entry, pair_dev, k),
                    BucketLevelSensor(coordinator, entry, pair_dev, k),
                    SettingsSensor(coordinator, entry, pair_dev, k),
                ]
            )
        else:
            all_sensors.extend(
                [
                    EntityStateSensor(coordinator, entry, pair_dev, k, a_name, b_name, "a", k[0]),
                    EntityStateSensor(coordinator, entry, pair_dev, k, a_name, b_name, "b", k[1]),
                    TodayUnaccountedTimeSensor(coordinator, entry, pair_dev, k),
                    DistanceSensor(coordinator, entry, pair_dev, k),
                    BucketSensor(coordinator, entry, pair_dev, k),
                    BucketLevelSensor(coordinator, entry, pair_dev, k),
                    ProximityDurationSensor(coordinator, entry, pair_dev, k),
                    ProximityTrackingStartedSensor(coordinator, entry, pair_dev, k),
                    ProximityRateSensor(coordinator, entry, pair_dev, k),
                    LastSeenTogetherSensor(coordinator, entry, pair_dev, k),
                    TodayProximityTimeSensor(coordinator, entry, pair_dev, k),
                    TodayZoneTimeSensor(coordinator, entry, pair_dev, k, BUCKET_VERY_NEAR),
                    TodayZoneTimeSensor(coordinator, entry, pair_dev, k, BUCKET_NEAR),
                    TodayZoneTimeSensor(coordinator, entry, pair_dev, k, BUCKET_MID),
                    TodayZoneTimeSensor(coordinator, entry, pair_dev, k, BUCKET_FAR),
                    TodayZoneTimeSensor(coordinator, entry, pair_dev, k, BUCKET_VERY_FAR),
                    DirectionSensor(coordinator, entry, pair_dev, k),
                    DirectionLevelSensor(coordinator, entry, pair_dev, k),
                    ClosingSpeedSensor(coordinator, entry, pair_dev, k),
                    EtaSensor(coordinator, entry, pair_dev, k),
                    GpsAccuracySensor(coordinator, entry, pair_dev, k, a_name, b_name, "a"),
                    GpsAccuracySensor(coordinator, entry, pair_dev, k, a_name, b_name, "b"),
                    LastUpdateSensor(coordinator, entry, pair_dev, k, a_name, b_name, "a"),
                    LastUpdateSensor(coordinator, entry, pair_dev, k, a_name, b_name, "b"),
                    UpdateCountSensor(coordinator, entry, pair_dev, k, a_name, b_name, "a"),
                    UpdateCountSensor(coordinator, entry, pair_dev, k, a_name, b_name, "b"),
                    SettingsSensor(coordinator, entry, pair_dev, k),
                ]
            )

    # Group-level sensors (on the parent group device)
    group_dev = _group_device_info(entry, group_name)
    all_sensors.append(SettingsSensor(coordinator, entry, group_dev))
    if len(entities_list) > 2:
        all_sensors.extend(
            [
                MinDistanceSensor(coordinator, entry, group_dev),
            ]
        )

    async_add_entities(all_sensors)


def _pair_key_str(k: tuple[str, str]) -> str:
    return f"{k[0]}__{k[1]}"


class EntityDistanceSensorBase(CoordinatorEntity[EntityDistanceCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        pair_key_val: tuple[str, str],
        sensor_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._pair_key = pair_key_val
        self._sensor_key = sensor_key
        self._attr_unique_id = f"{entry.entry_id}_{_pair_key_str(pair_key_val)}_{sensor_key}"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._pair.data_valid

    @property
    def _pair(self) -> PairState:
        return self.coordinator.data.pairs.get(self._pair_key) or PairState(
            entity_a_id=self._pair_key[0], entity_b_id=self._pair_key[1]
        )


class DistanceSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_translation_key = "distance"

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "distance")

    @property
    def native_value(self) -> float | None:
        if not self._pair.data_valid:
            return None
        return self._pair.distance_m

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "entity_a": self._pair.entity_a_id,
            "entity_b": self._pair.entity_b_id,
        }


class BucketSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = BUCKETS
    _attr_translation_key = "bucket"

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "bucket")

    @property
    def native_value(self) -> str | None:
        if self._pair.distance_m is None or not self._pair.data_valid:
            return None
        return calc_bucket(self._pair.distance_m, self.coordinator.bucket_thresholds)


class BucketLevelSensor(EntityDistanceSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "bucket_level"

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "bucket_level")

    @property
    def native_value(self) -> int | None:
        if self._pair.distance_m is None or not self._pair.data_valid:
            return None
        bucket = calc_bucket(self._pair.distance_m, self.coordinator.bucket_thresholds)
        return _BUCKET_LEVEL[bucket]


class ProximityDurationSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_translation_key = "proximity_duration"

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "proximity_duration")

    @property
    def native_value(self) -> float | None:
        if not self.available:
            return None
        ps = self._pair
        if ps.proximity_tracking_started is None:
            return None
        total_s = ps.proximity_duration_s
        if ps.proximity and ps.proximity_since:
            total_s += (dt_util.now() - ps.proximity_since).total_seconds()
        return round(total_s / 60, 1)


class LastSeenTogetherSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_seen_together"

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "last_seen_together")

    @property
    def native_value(self) -> datetime | None:
        if not self.available:
            return None
        return self._pair.last_seen_together


class TodayProximityTimeSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_translation_key = "today_proximity_time"

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "today_proximity_time")

    @property
    def native_value(self) -> float | None:
        if not self._pair.data_valid:
            return None
        return round(self._pair.today_proximity_seconds / 60, 1)


class TodayZoneTimeSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, coordinator, entry, device_info, k, bucket: str):
        super().__init__(coordinator, entry, device_info, k, f"today_zone_time_{bucket}")
        self._bucket = bucket
        self._attr_translation_key = f"today_zone_time_{bucket}"

    @property
    def native_value(self) -> float | None:
        if not self._pair.data_valid:
            return None
        return round(self._pair.today_zone_seconds.get(self._bucket, 0.0) / 60, 1)

    @property
    def extra_state_attributes(self) -> dict:
        thresholds = self.coordinator.bucket_thresholds
        buckets = list(thresholds.keys())
        upper = thresholds.get(self._bucket)
        idx = buckets.index(self._bucket) if self._bucket in buckets else -1
        lower = thresholds[buckets[idx - 1]] if idx > 0 else 0
        attrs: dict = {}
        if idx >= 0:
            attrs["range_from_m"] = lower
        if upper is not None:
            attrs["range_to_m"] = upper
        return attrs


class DirectionSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = DIRECTIONS
    _attr_translation_key = "direction"

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "direction")

    @property
    def native_value(self) -> str | None:
        if not self._pair.data_valid:
            return None
        return self._pair.direction


class DirectionLevelSensor(EntityDistanceSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "direction_level"

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "direction_level")

    @property
    def native_value(self) -> int | None:
        if not self._pair.data_valid or self._pair.direction is None:
            return None
        return _DIRECTION_LEVEL.get(self._pair.direction)


class ClosingSpeedSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.SPEED
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_translation_key = "closing_speed"

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "closing_speed")

    @property
    def native_value(self) -> float | None:
        if not self._pair.data_valid:
            return None
        return (
            round(self._pair.closing_speed_kmh, 1)
            if self._pair.closing_speed_kmh is not None
            else None
        )


class EtaSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_translation_key = "eta"

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "eta")

    @property
    def native_value(self) -> float | None:
        if not self._pair.data_valid:
            return None
        return round(self._pair.eta_minutes, 1) if self._pair.eta_minutes is not None else None


class GpsAccuracySensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, device_info, k, a_name, b_name, which: str):
        super().__init__(coordinator, entry, device_info, k, f"gps_accuracy_{which}")
        self._which = which
        name = a_name if which == "a" else b_name
        self._attr_name = f"GPS Accuracy ({name})"

    @property
    def native_value(self) -> float | None:
        if not self.available:
            return None
        return self._pair.accuracy_a if self._which == "a" else self._pair.accuracy_b


class LastUpdateSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, device_info, k, a_name, b_name, which: str):
        super().__init__(coordinator, entry, device_info, k, f"last_update_{which}")
        self._which = which
        name = a_name if which == "a" else b_name
        self._attr_name = f"Last Update ({name})"

    @property
    def native_value(self) -> datetime | None:
        if not self.available:
            return None
        return self._pair.last_update_a if self._which == "a" else self._pair.last_update_b


class UpdateCountSensor(EntityDistanceSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "updates"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:update"

    def __init__(self, coordinator, entry, device_info, k, a_name, b_name, which: str):
        super().__init__(coordinator, entry, device_info, k, f"update_count_{which}")
        self._which = which
        name = a_name if which == "a" else b_name
        window_min = round(coordinator.updates_window_s / 60)
        self._attr_name = f"Update Count Last {window_min} min ({name})"

    @property
    def native_value(self) -> int | None:
        if not self._pair.data_valid:
            return None
        if self._which == "a":
            window_start = self._pair.update_window_start_a
            count = self._pair.update_count_a
        else:
            window_start = self._pair.update_window_start_b
            count = self._pair.update_count_b
        if window_start is None:
            return count
        now = dt_util.now()
        if (now - window_start).total_seconds() > self.coordinator.updates_window_s:
            return 0
        return count


class EntityStateSensor(EntityDistanceSensorBase):
    _attr_icon = "mdi:account-circle-outline"

    def __init__(
        self, coordinator, entry, device_info, k, a_name, b_name, which: str, entity_id: str
    ):
        super().__init__(coordinator, entry, device_info, k, f"entity_state_{which}")
        self._which = which
        self._tracked_entity_id = entity_id
        name = a_name if which == "a" else b_name
        self._attr_name = f"State ({name})"

    @property
    def native_value(self) -> str | None:
        if not self.available:
            return None
        state = self.hass.states.get(self._tracked_entity_id)
        if state is None:
            return None
        return state.state


class ProximityTrackingStartedSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "proximity_tracking_started"

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "proximity_tracking_started")

    @property
    def native_value(self) -> datetime | None:
        if not self.available:
            return None
        return self._pair.proximity_tracking_started


class ProximityRateSensor(EntityDistanceSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_translation_key = "proximity_rate"
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "proximity_rate")

    @property
    def native_value(self) -> float | None:
        ps = self._pair
        if not ps.data_valid or ps.proximity_tracking_started is None:
            return None
        now = dt_util.now()
        total_s = (now - ps.proximity_tracking_started).total_seconds()
        if total_s <= 0:
            return None
        prox_s = ps.proximity_duration_s
        if ps.proximity and ps.proximity_since:
            prox_s += (now - ps.proximity_since).total_seconds()
        return round(min(prox_s / total_s * 100, 100.0), 1)


class TodayUnaccountedTimeSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_translation_key = "today_unaccounted_time"

    def __init__(self, coordinator, entry, device_info, k):
        super().__init__(coordinator, entry, device_info, k, "today_unaccounted_time")

    @property
    def available(self) -> bool:
        # Reports the unaccounted slice of today regardless of pair validity —
        # the metric's purpose includes invalid windows (GPS gone, holds, restarts).
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> float | None:
        if not self.available:
            return None
        ps = self._pair
        now = dt_util.now()
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elapsed_s = max(0.0, (now.astimezone(UTC) - midnight.astimezone(UTC)).total_seconds())
        accounted_s = sum(ps.today_zone_seconds.values())
        return round(max(0.0, elapsed_s - accounted_s) / 60, 1)

    @property
    def extra_state_attributes(self) -> dict:
        # Surface tracking-start so a large initial value on a fresh install is
        # visibly explained: time before tracking began is unaccounted by
        # definition (the metric counts from midnight, not from setup).
        ps = self._pair
        attrs: dict = {}
        if ps.proximity_tracking_started is not None:
            attrs["tracking_started"] = ps.proximity_tracking_started.isoformat()
        return attrs


class MinDistanceSensor(CoordinatorEntity[EntityDistanceCoordinator], SensorEntity):
    """Minimum distance across all pairs in the group. Only shown for groups with 3+ entities."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_translation_key = "min_distance"

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_min_distance"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> float | None:
        if not self.available:
            return None
        return self.coordinator.data.min_distance_m


class SettingsSensor(CoordinatorEntity[EntityDistanceCoordinator], SensorEntity):
    """Diagnostic sensor exposing all proximity / filter settings.

    State is a concise summary: ``"<entry>/<exit>m · <debounce>s · zones
    <vn>/<n>/<m>/<f>m"``. Full settings dict surfaced via
    ``extra_state_attributes``. Registered on the group device once and on
    every pair device so the per-pair Lovelace card can reference a
    pair-slug-derived entity_id.
    """

    _attr_has_entity_name = True
    _attr_translation_key = "settings"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        pair_key_val: tuple[str, str] | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        if pair_key_val is None:
            self._attr_unique_id = f"{entry.entry_id}_settings"
        else:
            self._attr_unique_id = f"{entry.entry_id}_{_pair_key_str(pair_key_val)}_settings"
        self._attr_device_info = device_info

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> str:
        s = self.coordinator.settings_snapshot
        return (
            f"{int(s['entry_threshold_m'])}/{int(s['exit_threshold_m'])}m "
            f"· {int(s['debounce_s'])}s "
            f"· zones {int(s['zone_very_near_m'])}/{int(s['zone_near_m'])}"
            f"/{int(s['zone_mid_m'])}/{int(s['zone_far_m'])}m"
        )

    @property
    def extra_state_attributes(self) -> dict:
        return self.coordinator.settings_snapshot
