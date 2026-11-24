"""The car's latest signals and typed readings, independent of where the signals came from.

Real cars send every value as a string
("90", "CLOSED", "LOCKED"), use the catalogue's paths, leave units out, and send -1 for "not set". The REST schema
and the catalogue disagree on a few paths and units, so each reading tries both.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from .jlr_datahub.signals import parse_time

SOC = ("Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed",
       "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current")
RANGE = ("Vehicle.Powertrain.TractionBattery.Range", "Vehicle.Powertrain.Range")
CHARGE_LIMIT = "Vehicle.Powertrain.TractionBattery.Charging.ChargeLimit"
PLUGGED_IN = ("Vehicle.Powertrain.TractionBattery.Charging.ChargingPort.AnyPosition.IsChargingCableConnected",
              "Vehicle.Powertrain.TractionBattery.Charging.IsPlugConnected")
CHARGING_STATUS = ("Vehicle.Powertrain.TractionBattery.Charging.Status",
                   "Vehicle.Powertrain.TractionBattery.Charging.Mode")
IS_CHARGING = "Vehicle.Powertrain.TractionBattery.Charging.IsCharging"
TIME_TO_COMPLETE = "Vehicle.Powertrain.TractionBattery.Charging.TimeToComplete"
SESSION_ENERGY = "Vehicle.Powertrain.TractionBattery.Charging.Session.Energy"
LOCK = ("Vehicle.Body.Door.Lock.Status", "Vehicle.Body.IsLocked")
ALARM = "Vehicle.Body.Security.Alarm.Mode"
ODOMETER = "Vehicle.TraveledDistance"
SERVICE_DISTANCE = "Vehicle.Service.DistanceToService"
LV_VOLTAGE = "Vehicle.LowVoltageBattery.CurrentVoltage"
LV_SOC = "Vehicle.LowVoltageBattery.StateOfCharge"
WASHER_FLUID = "Vehicle.Body.Windshield.Front.WasherFluid.IsLevelLow"
LATITUDE = "Vehicle.CurrentLocation.Latitude"
LONGITUDE = "Vehicle.CurrentLocation.Longitude"

# Front left / front right / rear left / rear right. The catalogue names "Front Left Door" as DriverSide, whatever
# side the steering wheel is on, so DriverSide is read as left, as JLR labels it.
SIDES = ("front_left", "front_right", "rear_left", "rear_right")
_DOORS = {
    "front_left": ("Vehicle.Cabin.Door.Row1.DriverSide", "Vehicle.Cabin.Door.Row1.Left"),
    "front_right": ("Vehicle.Cabin.Door.Row1.PassengerSide", "Vehicle.Cabin.Door.Row1.Right"),
    "rear_left": ("Vehicle.Cabin.Door.Row2.DriverSide", "Vehicle.Cabin.Door.Row2.Left"),
    "rear_right": ("Vehicle.Cabin.Door.Row2.PassengerSide", "Vehicle.Cabin.Door.Row2.Right"),
}
_WINDOWS = {
    "front_left": ("Vehicle.Cabin.Door.Row1.DriverSide.Window.Position", "Vehicle.Cabin.Window.Row1.Left.IsOpen"),
    "front_right": ("Vehicle.Cabin.Door.Row1.PassengerSide.Window.Position", "Vehicle.Cabin.Window.Row1.Right.IsOpen"),
    "rear_left": ("Vehicle.Cabin.Door.Row2.DriverSide.Window.Position", "Vehicle.Cabin.Window.Row2.Left.IsOpen"),
    "rear_right": ("Vehicle.Cabin.Door.Row2.PassengerSide.Window.Position", "Vehicle.Cabin.Window.Row2.Right.IsOpen"),
}
_TYRES = {
    "front_left": "Vehicle.Chassis.Axle.Row1.Wheel.Left.Tire",
    "front_right": "Vehicle.Chassis.Axle.Row1.Wheel.Right.Tire",
    "rear_left": "Vehicle.Chassis.Axle.Row2.Wheel.Left.Tire",
    "rear_right": "Vehicle.Chassis.Axle.Row2.Wheel.Right.Tire",
}
BONNET = "Vehicle.Body.Hood.IsOpen"
BOOT = "Vehicle.Body.Trunk.Rear.IsOpen"

CHARGING_STATES = ["charging", "complete", "plugged_in", "unplugged", "fault"]

_TRUE = {"TRUE", "YES", "ON", "LOCKED", "OPEN", "AJAR", "ACTIVE", "WIRED", "CONNECTED", "FOLDED", "ENABLED", "LOW", "1"}
_FALSE = {"FALSE", "NO", "OFF", "UNLOCKED", "CLOSED", "INACTIVE", "NOTCONNECTED", "NOT_CONNECTED", "UNFOLDED",
          "DISABLED", "NORMAL", "0"}


def as_number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def as_token(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return str(value).strip().upper()


def as_bool(value: Any) -> bool | None:
    """True/false for the yes-or-no enums the car uses; None for UNKNOWN and anything else."""
    if isinstance(value, bool):
        return value
    token = as_token(value)
    if token in _TRUE:
        return True
    if token in _FALSE:
        return False
    return None


@dataclass
class Signal:
    name: str
    value: Any
    unit: str | None
    timestamp: float | None


class VehicleState:
    """The latest value of every signal. Newer timestamps win, so the stream and REST can be merged in any order."""

    def __init__(self) -> None:
        self.signals: dict[str, Signal] = {}

    @classmethod
    def from_signals(cls, signals: list[dict]) -> "VehicleState":
        state = cls()
        state.merge(signals)
        return state

    def merge(self, signals: list[dict]) -> bool:
        """Merges flat signals ({name, value, unit, timestamp}); timestamps may be epoch seconds or ISO strings.
        Returns whether anything changed."""
        changed = False
        for s in signals:
            name = s.get("name")
            if not isinstance(name, str):
                continue
            ts = s.get("timestamp")
            ts = parse_time(ts) if isinstance(ts, str) else ts
            old = self.signals.get(name)
            if old and old.timestamp is not None and ts is not None and ts < old.timestamp:
                continue
            new = Signal(name, s.get("value"), s.get("unit"), ts)
            if old != new:
                self.signals[name] = new
                changed = True
        return changed

    def signal(self, *paths: str) -> Signal | None:
        for p in paths:
            if p in self.signals:
                return self.signals[p]
        return None

    def value(self, *paths: str) -> Any:
        s = self.signal(*paths)
        return None if s is None else s.value

    def positive(self, *paths: str) -> float | None:
        """A number, or None when missing or negative (the car sends -1 for "not set")."""
        v = as_number(self.value(*paths))
        return v if v is not None and v >= 0 else None

    @property
    def reported_at(self) -> dt.datetime | None:
        ts = max((s.timestamp for s in self.signals.values() if s.timestamp), default=None)
        return None if ts is None else dt.datetime.fromtimestamp(ts, dt.timezone.utc)

    # Battery and charging

    @property
    def battery_level(self) -> float | None:
        return self.positive(*SOC)

    @property
    def range_km(self) -> float | None:
        return self.positive(*RANGE)

    @property
    def charge_limit(self) -> float | None:
        return self.positive(CHARGE_LIMIT)

    @property
    def plugged_in(self) -> bool | None:
        return as_bool(self.value(*PLUGGED_IN))

    @property
    def charging_status(self) -> str | None:
        """The raw status ("CHARGING", "FULLYCHARGED", "NOT-CHARGING", …)."""
        return as_token(self.value(*CHARGING_STATUS))

    @property
    def charging_state(self) -> str | None:
        status = self.charging_status
        if status in ("CHARGING", "AC-CHARGING", "DC-CHARGING", "INITIALIZATION"):
            return "charging"
        if status in ("FULLYCHARGED", "BULKCHARGED"):
            return "complete"
        if status == "FAULT":
            return "fault"
        if as_bool(self.value(IS_CHARGING)) is True:
            return "charging"
        plugged = self.plugged_in
        if plugged is True:
            return "plugged_in"
        if plugged is False or status == "NOT-CHARGING":
            return "unplugged"
        return None

    @property
    def is_charging(self) -> bool | None:
        state = self.charging_state
        return None if state is None else state == "charging"

    @property
    def minutes_to_full(self) -> float | None:
        """Minutes until charging stops at the limit. The car keeps the last estimate after it stops, so this is 0
        once complete and unknown when not charging."""
        state = self.charging_state
        if state == "complete":
            return 0
        if state not in ("charging", "plugged_in"):
            return None
        s = self.signal(TIME_TO_COMPLETE)
        v = None if s is None else as_number(s.value)
        if v is None or v < 0:
            return None
        return v / 60 if (s.unit or "").lower().startswith("s") else v

    @property
    def session_energy_kwh(self) -> float | None:
        return self.positive(SESSION_ENERGY)

    # Security and openings

    @property
    def locked(self) -> bool | None:
        s = self.signal(*LOCK)
        if s is not None:
            return as_bool(s.value)
        doors = [as_bool(self.value(*(f"{p}.IsLocked" for p in paths))) for paths in _DOORS.values()]
        doors = [d for d in doors if d is not None]
        return all(doors) if doors else None

    @property
    def alarm(self) -> str | None:
        return as_token(self.value(ALARM))

    def door_open(self, side: str) -> bool | None:
        return as_bool(self.value(*(f"{p}.IsOpen" for p in _DOORS[side])))

    def window_open(self, side: str) -> bool | None:
        v = self.value(*_WINDOWS[side])
        n = as_number(v)
        if n is not None and not isinstance(v, bool) and as_token(v) not in ("0", "1"):
            return n > 0  # a position in percent
        return as_bool(v)

    @property
    def bonnet_open(self) -> bool | None:
        return as_bool(self.value(BONNET))

    @property
    def boot_open(self) -> bool | None:
        return as_bool(self.value(BOOT))

    # Tyres

    def tyre_pressure_kpa(self, side: str) -> float | None:
        """The catalogue says hPa, the REST schema kPa; the size of the number tells them apart (I-Pace: "243")."""
        raw = as_number(self.value(f"{_TYRES[side]}.Pressure"))
        if raw is None or raw <= 0:
            return None
        return raw / 10 if raw > 600 else raw

    def tyre_warning(self, side: str) -> str | None:
        """"NORMAL", "WARNING_LOW_SOFT", "WARNING_LOW_HARD", "WARNING_HIGH", "NO_SENSORS"."""
        return as_token(self.value(f"{_TYRES[side]}.IsPressureLow"))

    @property
    def tyre_problem(self) -> bool | None:
        warnings = [self.tyre_warning(s) for s in SIDES]
        known = [w for w in warnings if w is not None]
        return any(w.startswith("WARNING") for w in known) if known else None

    # Odometer, service, 12 V

    @property
    def odometer_km(self) -> float | None:
        """The catalogue says km, but cars send metres (an I-Pace reported 108 863 000), so past 2 million it's
        metres."""
        raw = self.positive(ODOMETER)
        if raw is None:
            return None
        return raw / 1000 if raw > 2_000_000 else raw

    @property
    def service_distance_km(self) -> float | None:
        return self.positive(SERVICE_DISTANCE)

    @property
    def lv_voltage(self) -> float | None:
        return self.positive(LV_VOLTAGE)

    @property
    def lv_soc(self) -> float | None:
        return self.positive(LV_SOC)

    @property
    def washer_fluid_low(self) -> bool | None:
        token = as_token(self.value(WASHER_FLUID))
        return None if token is None else token == "LOW"

    # Location

    @property
    def location(self) -> tuple[float, float, dt.datetime | None] | None:
        lat, lon = self.signal(LATITUDE), self.signal(LONGITUDE)
        if lat is None or lon is None:
            return None
        la, lo = as_number(lat.value), as_number(lon.value)
        if la is None or lo is None or (la == 0 and lo == 0) or not (-90 <= la <= 90 and -180 <= lo <= 180):
            return None
        ts = lat.timestamp or lon.timestamp
        return la, lo, None if ts is None else dt.datetime.fromtimestamp(ts, dt.timezone.utc)
