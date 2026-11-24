"""Turns any Data Hub payload into flat signals: {"name": VSS path, "value", "unit", "timestamp": epoch seconds}.

Accepts the nested VSS shape the REST API sends and the {name, value, unit, timestamp} objects the stream sends.
"""
from __future__ import annotations

import datetime as dt
from typing import Any


def parse_time(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def parse_signals(payload: Any) -> list[dict]:
    out: list[dict] = []
    fallback = parse_time(payload.get("timestamp")) if isinstance(payload, dict) else None

    def walk(node: Any, path: str, ts: float | None) -> None:
        if isinstance(node, dict):
            name = node.get("name") or node.get("vssIdentifier")
            if isinstance(name, str) and name.startswith("Vehicle") and "value" in node:
                if isinstance(node["value"], (str, int, float, bool)):
                    unit = node.get("unit")
                    out.append({"name": name, "value": node["value"],
                                "unit": None if unit in (None, "none") else unit,
                                "timestamp": parse_time(node.get("timestamp")) or ts})
                return
            own = parse_time(node.get("Timestamp")) or ts
            for key, child in node.items():
                if not path and key == "timestamp":
                    continue
                walk(child, f"{path}.{key}" if path else key, own)
        elif isinstance(node, list):
            for child in node:
                walk(child, path, ts)
        elif path.startswith("Vehicle") and isinstance(node, (str, int, float, bool)):
            out.append({"name": path, "value": node, "unit": None, "timestamp": ts})

    walk(payload, "", fallback)
    return out


SOC = ("Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed",
       "Vehicle.Powertrain.TractionBattery.StateOfCharge.Current")
CHARGING_STATUS = "Vehicle.Powertrain.TractionBattery.Charging.Status"
ODOMETER = "Vehicle.TraveledDistance"


def number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None  # the car sends -1 for "not set"
