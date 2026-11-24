"""Coordinators: one that talks to JLR itself (stream + REST backstop), one that reads an existing jlr-server."""
from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CERTIFICATE_NAME,
    CONF_ACCOUNT_ID,
    CONF_CLIENT_ID,
    CONF_SCAN_INTERVAL,
    CONF_STORAGE_ID,
    CONF_STREAM_USERNAME,
    CONF_TOKEN,
    CONF_URL,
    CONF_VIN,
    DEFAULT_SCAN_INTERVAL,
    DIRECT_JOURNEYS,
    DIRECT_POLL,
    DOMAIN,
    JOURNEY_DAYS,
    USER_AGENT,
)
from .jlr_datahub import Config, JLRClient, JLRError, SignInRequired, Stream
from .jlr_datahub.signals import parse_time
from .vehicle import VehicleState

_LOGGER = logging.getLogger(__name__)


@dataclass
class JLRData:
    state: VehicleState = field(default_factory=VehicleState)
    last_trip: dict | None = None
    stream: dict | None = None
    signed_in: bool | None = None


def latest_trip(items: list[dict]) -> dict | None:
    """The journey that started last."""
    dated = [(parse_time(j.get("startTime")), j) for j in items if isinstance(j, dict)]
    dated = [(t, j) for t, j in dated if t is not None]
    return max(dated, key=lambda x: x[0])[1] if dated else None


def storage_dir(hass: HomeAssistant, storage_id: str) -> Path:
    """Where direct mode keeps its keys and tokens (0600 files in a 0700 folder)."""
    return Path(hass.config.path(".storage", DOMAIN, storage_id))


def make_client(path: Path) -> JLRClient:
    """Blocking: creates the keys on first use and an HTTP client."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(mode=0o700, exist_ok=True)
    return JLRClient(path, user_agent=USER_AGENT, certificate_name=CERTIFICATE_NAME)


def remove_storage(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)


class JLRCoordinator(DataUpdateCoordinator[JLRData]):
    """Shared by both modes so the entities don't care where the data came from."""

    config_entry: ConfigEntry
    vin: str


class DirectCoordinator(JLRCoordinator):
    """Holds this Home Assistant's own JLR credential: stays on the stream, and polls REST every 10 minutes as a
    backstop (which also keeps the sign-in refreshed)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: JLRClient) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} direct", update_interval=DIRECT_POLL)
        self.client = client
        self.vin = entry.data[CONF_VIN]
        self.data = JLRData()
        self._next_journeys = 0.0
        self.stream = Stream(client, self._stream_signals)
        self.stream.name = f"jlr-stream-{self.vin[-6:]}"

    @staticmethod
    def config_from_entry(entry: ConfigEntry) -> Config:
        d = {**entry.data, **entry.options}
        return Config(d[CONF_CLIENT_ID], d[CONF_VIN], d.get(CONF_STREAM_USERNAME, ""), d.get(CONF_ACCOUNT_ID, ""))

    def start_stream(self) -> None:
        self.stream.start()

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        self.stream.stop_event.set()
        self.stream.wake.set()
        if self.stream.is_alive():
            await self.hass.async_add_executor_job(self.stream.join, 10)
        await self.hass.async_add_executor_job(self.client.http.close)

    def _stream_signals(self, signals: list[dict], topic: str) -> None:
        """Called on the stream's thread."""
        self.hass.loop.call_soon_threadsafe(self._apply_stream, signals)

    @callback
    def _apply_stream(self, signals: list[dict]) -> None:
        if self.data.state.merge(signals):
            self.data.stream = dict(self.stream.status)
            # Not async_set_updated_data: that would push back the REST poll, which keeps the sign-in alive.
            self.async_update_listeners()

    def _fetch(self) -> tuple[list[dict], list[dict] | None]:
        signals, errors = self.client.snapshot()
        for resource, error in errors.items():
            _LOGGER.debug("%s: %s", resource, error)
        journeys = None
        if time.time() >= self._next_journeys:
            now = time.time()
            try:
                journeys = self.client.journeys(now - JOURNEY_DAYS * 86400, now)
                self._next_journeys = now + DIRECT_JOURNEYS.total_seconds()
            except JLRError as err:
                if err.status not in (403, 404):
                    _LOGGER.warning("Couldn't read journeys: %s", err)
                self._next_journeys = now + DIRECT_JOURNEYS.total_seconds()
        return signals, journeys

    async def _async_update_data(self) -> JLRData:
        try:
            signals, journeys = await self.hass.async_add_executor_job(self._fetch)
        except SignInRequired as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except JLRError as err:
            raise UpdateFailed(str(err)) from err
        data = self.data or JLRData()
        data.state.merge(signals)
        if journeys is not None:
            data.last_trip = latest_trip(journeys) or data.last_trip
        data.stream = dict(self.stream.status)
        data.signed_in = self.client.signed_in
        return data


class ServerCoordinator(JLRCoordinator):
    """Reads an existing jlr-server, which holds the credential, stays on the stream and keeps history (so trips
    come with the battery they used)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, vin: str) -> None:
        seconds = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(hass, _LOGGER, config_entry=entry, name=f"{DOMAIN} server",
                         update_interval=timedelta(seconds=seconds))
        self.api = ServerAPI(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN])
        self.vin = vin

    async def _async_update_data(self) -> JLRData:
        try:
            state, journeys, status = await asyncio.gather(
                self.api.get("state"), self.api.get("journeys", days=JOURNEY_DAYS), self.api.get("status"))
        except ServerAuthError as err:
            raise ConfigEntryAuthFailed("The jlr-server token was refused.") from err
        except ServerError as err:
            raise UpdateFailed(str(err)) from err
        return JLRData(state=VehicleState.from_signals(state.get("signals") or []),
                       last_trip=latest_trip(journeys.get("items") or []),
                       stream=status.get("stream"), signed_in=status.get("signedIn"))


class ServerError(Exception):
    pass


class ServerAuthError(ServerError):
    pass


class ServerAPI:
    def __init__(self, session: aiohttp.ClientSession, url: str, token: str) -> None:
        self.session = session
        self.base = url.rstrip("/")
        self.token = token

    async def get(self, path: str, **params: Any) -> dict:
        try:
            async with self.session.get(f"{self.base}/api/{path}", params=params or None,
                                        headers={"Authorization": f"Bearer {self.token}"},
                                        timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 401:
                    raise ServerAuthError("Bad token")
                if r.status >= 400:
                    raise ServerError(f"jlr-server: HTTP {r.status} for /api/{path}")
                return await r.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ServerError(f"Couldn't reach jlr-server: {err}") from err
