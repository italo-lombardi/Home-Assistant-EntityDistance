from __future__ import annotations

from datetime import datetime
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfLength, UnitOfSpeed, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BUCKET_FAR,
    BUCKET_MID,
    BUCKET_NEAR,
    BUCKET_VERY_FAR,
    BUCKET_VERY_NEAR,
    BUCKETS,
    DIRECTIONS,
    DOMAIN,
)
from .coordinator import EntityDistanceCoordinator, _calc_bucket
from .models import PairState

_LOGGER = logging.getLogger(__name__)


_BUCKET_LEVEL = {
    BUCKET_VERY_NEAR: 1,
    BUCKET_NEAR: 2,
    BUCKET_MID: 3,
    BUCKET_FAR: 4,
    BUCKET_VERY_FAR: 5,
}


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

    entity_a_name = _friendly_name(entry.data["entity_a"])
    entity_b_name = _friendly_name(entry.data["entity_b"])

    async_add_entities(
        [
            DistanceSensor(coordinator, entry, entity_a_name, entity_b_name),
            BucketSensor(coordinator, entry, entity_a_name, entity_b_name),
            BucketLevelSensor(coordinator, entry, entity_a_name, entity_b_name),
            ProximityDurationSensor(coordinator, entry, entity_a_name, entity_b_name),
            LastSeenTogetherSensor(coordinator, entry, entity_a_name, entity_b_name),
            TodayProximityTimeSensor(coordinator, entry, entity_a_name, entity_b_name),
            DirectionSensor(coordinator, entry, entity_a_name, entity_b_name),
            ClosingSpeedSensor(coordinator, entry, entity_a_name, entity_b_name),
            EtaSensor(coordinator, entry, entity_a_name, entity_b_name),
            GpsAccuracySensor(coordinator, entry, entity_a_name, entity_b_name, "a"),
            GpsAccuracySensor(coordinator, entry, entity_a_name, entity_b_name, "b"),
            LastUpdateSensor(coordinator, entry, entity_a_name, entity_b_name, "a"),
            LastUpdateSensor(coordinator, entry, entity_a_name, entity_b_name, "b"),
            UpdateFrequencySensor(coordinator, entry, entity_a_name, entity_b_name, "a"),
            UpdateFrequencySensor(coordinator, entry, entity_a_name, entity_b_name, "b"),
            DataStalenessSensor(coordinator, entry, entity_a_name, entity_b_name, "a"),
            DataStalenessSensor(coordinator, entry, entity_a_name, entity_b_name, "b"),
        ]
    )


class EntityDistanceSensorBase(CoordinatorEntity[EntityDistanceCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: EntityDistanceCoordinator,
        entry: ConfigEntry,
        entity_a_name: str,
        entity_b_name: str,
        sensor_key: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._sensor_key = sensor_key
        self._attr_unique_id = f"{entry.entry_id}_{sensor_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Entity Distance — {entity_a_name} & {entity_b_name}",
            manufacturer="Entity Distance",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def _pair(self) -> PairState:
        return self.coordinator.data.pair


class DistanceSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_translation_key = "distance"

    def __init__(self, coordinator, entry, a_name, b_name):
        super().__init__(coordinator, entry, a_name, b_name, "distance")

    @property
    def native_value(self) -> float | None:
        return self._pair.distance_m


class BucketSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = BUCKETS
    _attr_translation_key = "bucket"

    def __init__(self, coordinator, entry, a_name, b_name):
        super().__init__(coordinator, entry, a_name, b_name, "bucket")

    @property
    def native_value(self) -> str | None:
        if self._pair.distance_m is None:
            return None
        return _calc_bucket(self._pair.distance_m, self.coordinator.bucket_thresholds)


class BucketLevelSensor(EntityDistanceSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_translation_key = "bucket_level"

    def __init__(self, coordinator, entry, a_name, b_name):
        super().__init__(coordinator, entry, a_name, b_name, "bucket_level")

    @property
    def native_value(self) -> int | None:
        if self._pair.distance_m is None:
            return None
        bucket = _calc_bucket(self._pair.distance_m, self.coordinator.bucket_thresholds)
        return _BUCKET_LEVEL[bucket]


class ProximityDurationSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_translation_key = "proximity_duration"

    def __init__(self, coordinator, entry, a_name, b_name):
        super().__init__(coordinator, entry, a_name, b_name, "proximity_duration")

    @property
    def native_value(self) -> float | None:
        if not self._pair.data_valid:
            return None
        total_s = self._pair.proximity_duration_s
        if self._pair.proximity and self._pair.proximity_since:
            total_s += (datetime.now().astimezone() - self._pair.proximity_since).total_seconds()
        return round(total_s / 60, 1)


class LastSeenTogetherSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_translation_key = "last_seen_together"

    def __init__(self, coordinator, entry, a_name, b_name):
        super().__init__(coordinator, entry, a_name, b_name, "last_seen_together")

    @property
    def native_value(self) -> datetime | None:
        return self._pair.last_seen_together


class TodayProximityTimeSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_translation_key = "today_proximity_time"

    def __init__(self, coordinator, entry, a_name, b_name):
        super().__init__(coordinator, entry, a_name, b_name, "today_proximity_time")

    @property
    def native_value(self) -> float | None:
        if not self._pair.data_valid:
            return None
        return round(self._pair.today_proximity_seconds / 60, 1)


class DirectionSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = DIRECTIONS
    _attr_translation_key = "direction"

    def __init__(self, coordinator, entry, a_name, b_name):
        super().__init__(coordinator, entry, a_name, b_name, "direction")

    @property
    def native_value(self) -> str | None:
        return self._pair.direction


class ClosingSpeedSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.SPEED
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_translation_key = "closing_speed"

    def __init__(self, coordinator, entry, a_name, b_name):
        super().__init__(coordinator, entry, a_name, b_name, "closing_speed")

    @property
    def native_value(self) -> float | None:
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

    def __init__(self, coordinator, entry, a_name, b_name):
        super().__init__(coordinator, entry, a_name, b_name, "eta")

    @property
    def native_value(self) -> float | None:
        return round(self._pair.eta_minutes, 1) if self._pair.eta_minutes is not None else None


class GpsAccuracySensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, a_name, b_name, which: str):
        super().__init__(coordinator, entry, a_name, b_name, f"gps_accuracy_{which}")
        self._which = which
        name = a_name if which == "a" else b_name
        self._attr_name = f"GPS Accuracy ({name})"

    @property
    def native_value(self) -> float | None:
        return self._pair.accuracy_a if self._which == "a" else self._pair.accuracy_b


class LastUpdateSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, a_name, b_name, which: str):
        super().__init__(coordinator, entry, a_name, b_name, f"last_update_{which}")
        self._which = which
        name = a_name if which == "a" else b_name
        self._attr_name = f"Last Update ({name})"

    @property
    def native_value(self) -> datetime | None:
        return self._pair.last_update_a if self._which == "a" else self._pair.last_update_b


class UpdateFrequencySensor(EntityDistanceSensorBase):
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "updates/min"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, a_name, b_name, which: str):
        super().__init__(coordinator, entry, a_name, b_name, f"update_frequency_{which}")
        self._which = which
        name = a_name if which == "a" else b_name
        self._attr_name = f"Update Frequency ({name})"

    @property
    def native_value(self) -> float | None:
        if not self._pair.data_valid:
            return None
        count = self._pair.update_count_a if self._which == "a" else self._pair.update_count_b
        window_start = (
            self._pair.update_window_start_a
            if self._which == "a"
            else self._pair.update_window_start_b
        )
        if window_start is None or count == 0:
            return 0.0
        elapsed_s = (datetime.now().astimezone() - window_start).total_seconds()
        if elapsed_s < 1.0:
            return 0.0
        elapsed_min = elapsed_s / 60
        return round(count / elapsed_min, 2)


class DataStalenessSensor(EntityDistanceSensorBase):
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, entry, a_name, b_name, which: str):
        super().__init__(coordinator, entry, a_name, b_name, f"data_staleness_{which}")
        self._which = which
        name = a_name if which == "a" else b_name
        self._attr_name = f"Data Staleness ({name})"

    @property
    def native_value(self) -> float | None:
        last = self._pair.last_update_a if self._which == "a" else self._pair.last_update_b
        if last is None:
            return None
        return round((datetime.now().astimezone() - last).total_seconds(), 0)
