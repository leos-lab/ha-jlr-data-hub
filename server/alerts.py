"""Warnings worth telling the owner about, raised from the car's reports, and Apple push to send them.

A rule is active or not given the latest value of every signal. When one becomes active an alert is opened (and
pushed); when it stops being active the alert is closed. Fault codes on the diagnostics feed open an alert each time
a new one arrives.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature

from jlr_datahub.crypto import b64url
from jlr_datahub.signals import number

log = logging.getLogger("jlr.alerts")

LV = "Vehicle.LowVoltageBattery."
CHARGING_STATUS = "Vehicle.Powertrain.TractionBattery.Charging.Status"
DRIVE_CYCLE = "Vehicle.System.DriveCycle.Status"


@dataclass
class Rule:
    key: str
    title: str
    check: Callable[[dict], str | None]  # the alert's message when active, else None
    severity: str = "warning"


def _lv_voltage(v: dict) -> str | None:
    volts = number(v.get(LV + "CurrentVoltage"))
    # Only meaningful parked: while driving or charging the DC-DC holds it at ~14 V.
    if volts is None or volts == 0 or v.get(DRIVE_CYCLE) not in (None, "KEY_REMOVED", "KEY_ON_ENGINE_OFF"):
        return None
    return f"{volts:.1f} V while parked. A healthy 12 V battery rests around 12.4–12.8 V." if volts < 11.9 else None


RULES = [
    Rule("lv-low", "12 V battery low",
         lambda v: {"BATTERY_LOW": "The car says its 12 V battery is low.",
                    "BATTERY_EMPTY": "The car says its 12 V battery is empty."}.get(v.get(LV + "IsBatteryLow"))),
    Rule("lv-health", "12 V battery needs attention",
         lambda v: {"REPLACE": "The car says the 12 V battery should be replaced.",
                    "RECOVER": "The car says the 12 V battery needs recovering (a long charge).",
                    "CHARGE": "The car says the 12 V battery needs charging."}.get(v.get(LV + "StateOfHealth"))),
    Rule("lv-voltage", "12 V battery voltage low", _lv_voltage),
    Rule("charge-fault", "Charging fault",
         lambda v: "The car reported a charging fault." if v.get(CHARGING_STATUS) == "FAULT" else None),
]


def evaluate(store, now: float | None = None) -> list[dict]:
    """Opens and closes rule alerts against the latest values. Returns the alerts just opened."""
    latest = store.latest_values()
    opened = []
    for rule in RULES:
        message = rule.check(latest)
        open_alert = store.open_alert(rule.key)
        if message and not open_alert:
            opened.append(store.add_alert(rule.key, rule.title, message, rule.severity,
                                          started=store.latest_report_time() or now or time.time()))
        elif not message and open_alert:
            store.close_alert(open_alert["id"], now or time.time())
    return opened


def diagnostic_alerts(store, signals: list[dict]) -> list[dict]:
    """One alert per new fault-code value on the diagnostics feed (Vehicle.Diagnostics.<module>.DTC|DID.<id>)."""
    opened = []
    for s in signals:
        name = s["name"]
        if not name.startswith("Vehicle.Diagnostics."):
            continue
        parts = name.split(".")
        module = parts[2] if len(parts) > 2 else "?"
        key = f"diag:{name}:{json.dumps(s['value'])}"
        if store.alert_exists(key):
            continue
        battery = module in ("BECM", "BCCM", "BMCM", "OBCM", "BCM")
        opened.append(store.add_alert(
            key, f"{'Battery' if battery else 'Fault'} code from {module}",
            f"{'.'.join(parts[3:])} = {s['value']}", "warning" if battery else "info",
            started=s.get("timestamp") or time.time(), closed=True))
    return opened


class APNs:
    """Token-based Apple push (ES256 JWT), HTTP/2. The key is the team's AuthKey_<KEYID>.p8."""

    def __init__(self, key_dir: Path, team_id: str, topic: str):
        self.team_id, self.topic = team_id, topic
        keys = sorted(key_dir.glob("AuthKey_*.p8")) if key_dir.exists() else []
        self.key = serialization.load_pem_private_key(keys[0].read_bytes(), None) if keys else None
        self.key_id = keys[0].stem.removeprefix("AuthKey_") if keys else None
        self.http = httpx.Client(http2=True, timeout=15)
        self._jwt: tuple[float, str] | None = None

    @property
    def enabled(self) -> bool:
        return self.key is not None and bool(self.team_id) and bool(self.topic)

    def _token(self) -> str:
        if self._jwt and time.time() - self._jwt[0] < 40 * 60:
            return self._jwt[1]
        header = b64url(json.dumps({"alg": "ES256", "kid": self.key_id}).encode())
        claims = b64url(json.dumps({"iss": self.team_id, "iat": int(time.time())}).encode())
        der = self.key.sign(f"{header}.{claims}".encode(), ec.ECDSA(hashes.SHA256()))
        r, s = decode_dss_signature(der)
        jwt = f"{header}.{claims}.{b64url(r.to_bytes(32, 'big') + s.to_bytes(32, 'big'))}"
        self._jwt = (time.time(), jwt)
        return jwt

    def send(self, device: dict, title: str, body: str, extra: dict | None = None) -> tuple[int, str]:
        host = "api.sandbox.push.apple.com" if device.get("environment") != "production" else "api.push.apple.com"
        payload = {"aps": {"alert": {"title": title, "body": body}, "sound": "default",
                           "interruption-level": "time-sensitive", "thread-id": "jlr"}, **(extra or {})}
        r = self.http.post(f"https://{host}/3/device/{device['token']}", json=payload, headers={
            "authorization": f"bearer {self._token()}", "apns-topic": self.topic, "apns-push-type": "alert",
            "apns-priority": "10"})
        reason = ""
        if r.status_code != 200:
            try:
                reason = r.json().get("reason", "")
            except Exception:
                reason = r.text[:100]
        return r.status_code, reason
