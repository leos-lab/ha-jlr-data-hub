"""Typed readings from real I-Pace signals (every value a string, -1 for "not set", odometer in metres)."""
from custom_components.jlr_data_hub.coordinator import latest_trip
from custom_components.jlr_data_hub.vehicle import VehicleState, as_bool

from .conftest import load

SOC = "Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed"


def real_state() -> VehicleState:
    return VehicleState.from_signals(load("server_state.json")["signals"])


def test_readings_from_a_real_car():
    s = real_state()
    assert s.battery_level == 90
    assert s.range_km == 334
    assert s.charge_limit is None  # "-1"
    assert s.charging_status == "FULLYCHARGED" and s.charging_state == "complete"
    assert s.minutes_to_full == 0  # the car keeps "107" after it finishes
    assert s.is_charging is False
    assert s.locked is True
    assert s.alarm == "ALARM_ARMED"
    assert [s.door_open(x) for x in ("front_left", "front_right", "rear_left", "rear_right")] == [False] * 4
    assert [s.window_open(x) for x in ("front_left", "rear_right")] == [False, False]
    assert s.bonnet_open is False and s.boot_open is False
    assert s.tyre_pressure_kpa("front_left") == 243 and s.tyre_pressure_kpa("rear_right") == 233
    assert s.tyre_problem is False
    assert s.odometer_km == 54321  # 54 321 000 m
    assert s.service_distance_km == 9800
    assert s.lv_voltage == 14.1 and s.lv_soc is None
    assert s.washer_fluid_low is True
    lat, lon, ts = s.location
    assert (lat, lon) == (51.5007, -0.1246) and ts is not None
    assert s.reported_at is not None


def test_minus_one_is_unavailable():
    s = VehicleState.from_signals([
        {"name": SOC, "value": "-1"},
        {"name": "Vehicle.Powertrain.TractionBattery.Range", "value": -1},
        {"name": "Vehicle.TraveledDistance", "value": "-1"},
        {"name": "Vehicle.Chassis.Axle.Row1.Wheel.Left.Tire.Pressure", "value": "-1"},
        {"name": "Vehicle.CurrentLocation.Latitude", "value": "0"},
        {"name": "Vehicle.CurrentLocation.Longitude", "value": "0"},
    ])
    assert s.battery_level is None and s.range_km is None and s.odometer_km is None
    assert s.tyre_pressure_kpa("front_left") is None
    assert s.location is None


def test_newer_values_win_whatever_the_order():
    s = VehicleState()
    assert s.merge([{"name": SOC, "value": "80", "timestamp": "2026-11-24T21:00:00Z"}])
    assert not s.merge([{"name": SOC, "value": "70", "timestamp": "2026-11-24T20:00:00Z"}])
    assert s.battery_level == 80
    assert s.merge([{"name": SOC, "value": 75, "timestamp": 1795600000.0}])
    assert s.battery_level == 75


def test_units_and_alternative_paths():
    s = VehicleState.from_signals([
        {"name": "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current", "value": 55.5},
        {"name": "Vehicle.Chassis.Axle.Row1.Wheel.Left.Tire.Pressure", "value": 2430},  # hPa
        {"name": "Vehicle.TraveledDistance", "value": 12345},  # km
        {"name": "Vehicle.Powertrain.TractionBattery.Charging.Status", "value": "CHARGING"},
        {"name": "Vehicle.Powertrain.TractionBattery.Charging.TimeToComplete", "value": 5400, "unit": "s"},
        {"name": "Vehicle.Cabin.Window.Row1.Left.IsOpen", "value": True},
        {"name": "Vehicle.Cabin.Door.Row1.PassengerSide.Window.Position", "value": "40"},
        {"name": "Vehicle.Chassis.Axle.Row2.Wheel.Left.Tire.IsPressureLow", "value": "WARNING_LOW_SOFT"},
    ])
    assert s.battery_level == 55.5
    assert s.tyre_pressure_kpa("front_left") == 243
    assert s.odometer_km == 12345
    assert s.charging_state == "charging" and s.minutes_to_full == 90
    assert s.window_open("front_left") is True and s.window_open("front_right") is True
    assert s.tyre_problem is True


def test_plugged_in_without_status():
    s = VehicleState.from_signals([{"name": "Vehicle.Powertrain.TractionBattery.Charging.ChargingPort.AnyPosition"
                                             ".IsChargingCableConnected", "value": "CONNECTED"}])
    assert s.plugged_in is True and s.charging_state == "plugged_in"
    assert as_bool("UNKNOWN") is None


def test_latest_trip_is_the_last_to_start():
    items = load("server_journeys.json")["items"]
    assert latest_trip(list(reversed(items)))["journeyId"] == items[0]["journeyId"]
    assert latest_trip([]) is None
