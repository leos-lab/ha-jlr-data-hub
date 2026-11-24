"""Constants for the JLR Data Hub integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "jlr_data_hub"

CONF_MODE = "mode"
MODE_DIRECT = "direct"
MODE_SERVER = "server"

# Direct mode
CONF_STORAGE_ID = "storage_id"
CONF_CLIENT_ID = "client_id"
CONF_VIN = "vin"
CONF_STREAM_USERNAME = "stream_username"
CONF_ACCOUNT_ID = "account_id"

# Server mode
CONF_URL = "url"
CONF_TOKEN = "token"
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 300

# Direct mode: REST is a backstop to the stream, and it keeps the sign-in refreshed. JLR's server polls at the same
# rates.
DIRECT_POLL = timedelta(minutes=10)
DIRECT_JOURNEYS = timedelta(minutes=30)
JOURNEY_DAYS = 14

USER_AGENT = "ha-jlr-data-hub"
CERTIFICATE_NAME = "Home Assistant JLR Data Hub"
