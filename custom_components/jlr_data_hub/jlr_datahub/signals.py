"""Turns any Data Hub payload into flat signals: {"name": VSS path, "value", "unit", "timestamp": epoch seconds}.

Accepts the nested VSS shape the REST API sends, {name, value, unit, timestamp} objects, and what the stream really
sends: arrays of {vssIdentifier, signalValue, signalTimestamp (epoch milliseconds, as a string), unit}.

The stream repeats some signals within one message: first in metric, then in the car's display units, both
labelled the same (range 331 then 205, both "km"; odometer in metres, then in miles). The first copy wins.
"""
from __future__ import annotations

import datetime as dt
from typing import Any


def parse_time(value: Any) -> float | None:
    """ISO 8601, or epoch seconds or milliseconds (a number or a string of digits)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool) or isinstance(value, str) and value.isdigit():
        n = float(value)
        return n / 1000 if n > 1e11 else n
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
            key = "value" if "value" in node else "signalValue"
            if isinstance(name, str) and name.startswith("Vehicle") and key in node:
                if isinstance(node[key], (str, int, float, bool)):
                    unit = node.get("unit")
                    out.append({"name": name, "value": node[key],
                                "unit": None if unit in (None, "none") else unit,
                                "timestamp": parse_time(node.get("timestamp", node.get("signalTimestamp"))) or ts})
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
    seen: set[str] = set()
    return [s for s in out if not (s["name"] in seen or seen.add(s["name"]))]


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
