"""Sensors: battery, range, charging, tyres, 12 V, odometer, service, the last trip, and the stream's state."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfLength,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPressure,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import JLRConfigEntry
from .coordinator import JLRData
from .entity import JLREntity
from .jlr_datahub.signals import parse_time
from .vehicle import CHARGING_STATES, SIDES

STREAM_STATES = ["off", "connecting", "live", "waiting", "dropped", "error"]


@dataclass(frozen=True, kw_only=True)
class JLRSensorDescription(SensorEntityDescription):
    value_fn: Callable[[JLRData], Any]
    attrs_fn: Callable[[JLRData], dict[str, Any] | None] | None = None


def _trip_distance_km(trip: dict | None) -> float | None:
    if not trip:
        return None
    d = trip.get("distance")
    if isinstance(d, dict):
        try:
            value = float(d.get("value"))
        except (TypeError, ValueError):
            return None
        unit = str(d.get("unit") or "km").lower()
        value = value / 1000 if unit in ("m", "metre", "meter", "metres", "meters") else value
        value = value * 1.609344 if unit in ("mi", "mile", "miles") else value
        return round(value, 2) if value >= 0 else None
    return None


def _trip_attrs(data: JLRData) -> dict[str, Any] | None:
    trip = data.last_trip
    if not trip:
        return None

    def ts(key: str) -> str | None:
        t = parse_time(trip.get(key))
        return None if t is None else datetime.fromtimestamp(t).astimezone().isoformat()

    def measure(key: str) -> Any:
        v = trip.get(key)
        return v.get("value") if isinstance(v, dict) else v

    attrs: dict[str, Any] = {
        "journey_id": trip.get("journeyId"),
        "start_time": ts("startTime"),
        "end_time": ts("endTime"),
        "duration_minutes": round(trip["duration"] / 60, 1) if isinstance(trip.get("duration"), (int, float)) else None,
        "average_speed_kmh": measure("averageSpeed"),
        # From jlr-server, which works these out from its battery history. Missing when it charged in between, or
        # in direct mode.
        "soc_start": trip.get("socStart"),
        "soc_end": trip.get("socEnd"),
        "soc_used": trip.get("socUsed"),
    }
    for key in ("startLocation", "endLocation"):
        loc = trip.get(key)
        if isinstance(loc, dict):
            prefix = "start" if key == "startLocation" else "end"
            attrs[f"{prefix}_latitude"] = loc.get("latitude")
            attrs[f"{prefix}_longitude"] = loc.get("longitude")
    return {k: v for k, v in attrs.items() if v is not None}


def _stream_attrs(data: JLRData) -> dict[str, Any] | None:
    s = data.stream or {}
    keys = ("detail", "topics", "messages", "last_message_at", "connections", "last_connection_seconds")
    return {k: s.get(k) for k in keys if s.get(k) is not None} or None


def _stream_state(data: JLRData) -> str | None:
    state = (data.stream or {}).get("state")
    return state if state in STREAM_STATES else None


SENSORS: list[JLRSensorDescription] = [
    JLRSensorDescription(
        key="battery", translation_key="battery", device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.state.battery_level),
    JLRSensorDescription(
        key="range", translation_key="range", device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS, state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0, value_fn=lambda d: d.state.range_km),
    JLRSensorDescription(
        key="charging_state", translation_key="charging_state", device_class=SensorDeviceClass.ENUM,
        options=CHARGING_STATES, value_fn=lambda d: d.state.charging_state,
        attrs_fn=lambda d: {"status": d.state.charging_status} if d.state.charging_status else None),
    JLRSensorDescription(
        key="charge_limit", translation_key="charge_limit", native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: d.state.charge_limit),
    JLRSensorDescription(
        key="time_to_full", translation_key="time_to_full", device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES, value_fn=lambda d: d.state.minutes_to_full),
    JLRSensorDescription(
        key="charge_session_energy", translation_key="charge_session_energy", device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR, state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.state.session_energy_kwh),
    *[
        JLRSensorDescription(
            key=f"tyre_pressure_{side}", translation_key=f"tyre_pressure_{side}",
            device_class=SensorDeviceClass.PRESSURE, native_unit_of_measurement=UnitOfPressure.KPA,
            state_class=SensorStateClass.MEASUREMENT, suggested_display_precision=0,
            value_fn=lambda d, side=side: d.state.tyre_pressure_kpa(side),
            attrs_fn=lambda d, side=side: {"warning": w} if (w := d.state.tyre_warning(side)) else None)
        for side in SIDES
    ],
    JLRSensorDescription(
        key="lv_battery_voltage", translation_key="lv_battery_voltage", device_class=SensorDeviceClass.VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT, state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC, value_fn=lambda d: d.state.lv_voltage),
    JLRSensorDescription(
        key="lv_battery_level", translation_key="lv_battery_level", device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC, entity_registry_enabled_default=False,
        value_fn=lambda d: d.state.lv_soc),
    JLRSensorDescription(
        key="odometer", translation_key="odometer", device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS, state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0, value_fn=lambda d: d.state.odometer_km),
    JLRSensorDescription(
        key="service_distance", translation_key="service_distance", device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS, suggested_display_precision=0,
        value_fn=lambda d: d.state.service_distance_km),
    JLRSensorDescription(
        key="last_trip", translation_key="last_trip", device_class=SensorDeviceClass.DISTANCE,
        native_unit_of_measurement=UnitOfLength.KILOMETERS, suggested_display_precision=1,
        value_fn=lambda d: _trip_distance_km(d.last_trip), attrs_fn=_trip_attrs),
    JLRSensorDescription(
        key="last_reported", translation_key="last_reported", device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC, value_fn=lambda d: d.state.reported_at),
    JLRSensorDescription(
        key="stream", translation_key="stream", device_class=SensorDeviceClass.ENUM, options=STREAM_STATES,
        entity_category=EntityCategory.DIAGNOSTIC, value_fn=_stream_state, attrs_fn=_stream_attrs),
]


async def async_setup_entry(hass: HomeAssistant, entry: JLRConfigEntry,
                            async_add_entities: AddConfigEntryEntitiesCallback) -> None:
    coordinator = entry.runtime_data
    async_add_entities(JLRSensor(coordinator, d) for d in SENSORS)


class JLRSensor(JLREntity, SensorEntity):
    entity_description: JLRSensorDescription

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        fn = self.entity_description.attrs_fn
        return fn(self.coordinator.data) if fn else None
