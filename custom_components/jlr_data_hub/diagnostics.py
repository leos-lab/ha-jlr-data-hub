"""Diagnostics, with the VIN, credentials and positions redacted."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import JLRConfigEntry
from .const import CONF_ACCOUNT_ID, CONF_CLIENT_ID, CONF_STREAM_USERNAME, CONF_TOKEN, CONF_URL, CONF_VIN

REDACT = {CONF_TOKEN, CONF_URL, CONF_VIN, CONF_CLIENT_ID, CONF_STREAM_USERNAME, CONF_ACCOUNT_ID, "unique_id",
          "title", "startLocation", "endLocation", "latitude", "longitude"}
PRIVATE_SIGNALS = ("Latitude", "Longitude", "VIN", "LicensePlate")


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: JLRConfigEntry) -> dict[str, Any]:
    data = entry.runtime_data.data
    signals = {
        name: "**REDACTED**" if name.endswith(PRIVATE_SIGNALS) else {"value": s.value, "unit": s.unit,
                                                                     "timestamp": s.timestamp}
        for name, s in sorted(data.state.signals.items())
    }
    return {
        "entry": async_redact_data({"data": dict(entry.data), "options": dict(entry.options)}, REDACT),
        "signals": signals,
        "last_trip": async_redact_data(data.last_trip or {}, REDACT),
        "stream": data.stream,
        "signed_in": data.signed_in,
    }
