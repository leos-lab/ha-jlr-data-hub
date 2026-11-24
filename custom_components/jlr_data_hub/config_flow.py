"""Config flow: read an existing jlr-server, or hold this Home Assistant's own JLR credential (key, certificate,
Device Code sign-in)."""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_ACCOUNT_ID,
    CONF_CLIENT_ID,
    CONF_MODE,
    CONF_SCAN_INTERVAL,
    CONF_STORAGE_ID,
    CONF_STREAM_USERNAME,
    CONF_TOKEN,
    CONF_URL,
    CONF_VIN,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MODE_DIRECT,
    MODE_SERVER,
)
from .coordinator import DirectCoordinator, ServerAPI, ServerAuthError, ServerError, make_client, remove_storage, storage_dir
from .jlr_datahub import Config, DeviceAuthorization, JLRClient, JLRError
from .jlr_datahub.crypto import jwt_claims

_LOGGER = logging.getLogger(__name__)

PASSWORD = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
URL = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))


def _title(vin: str) -> str:
    return f"JLR …{vin[-6:]}" if vin else "JLR"


def _finish_direct_setup(client: JLRClient) -> None:
    """After sign-in: the stream's account ID is in the streaming token, so it needn't be typed in."""
    cfg = client.config
    if cfg.stream_username and not cfg.account_id:
        try:
            claims = jwt_claims(client.client_credentials().access_token)
        except JLRError as err:
            _LOGGER.warning("Couldn't read the stream account ID: %s", err)
            return
        account = (claims.get("dsas") or {}).get("account_id")
        if account:
            client.save_config(Config(cfg.client_id, cfg.vin, cfg.stream_username, str(account)))


class JLRConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._client: JLRClient | None = None
        self._storage_id: str | None = None
        self._certificate: str | None = None
        self._auth: DeviceAuthorization | None = None
        self._signin_task: asyncio.Task | None = None
        self._signin_error: str | None = None
        self._cancel = threading.Event()
        self._created = False

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> OptionsFlow:
        return JLROptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=[MODE_SERVER, MODE_DIRECT])

    # MARK: Via jlr-server

    async def _check_server(self, url: str, token: str) -> tuple[dict | None, str | None]:
        if not url.startswith(("http://", "https://")):
            url = f"http://{url}"
        api = ServerAPI(async_get_clientsession(self.hass), url, token)
        try:
            status = await api.get("status")
        except ServerAuthError:
            return None, "invalid_auth"
        except ServerError:
            return None, "cannot_connect"
        vin = (status.get("config") or {}).get("vin") or ""
        if not status.get("configured") or len(vin) != 17:
            return None, "server_not_configured"
        return {"url": api.base, "vin": vin.upper(), "signed_in": status.get("signedIn")}, None

    async def async_step_server(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            info, error = await self._check_server(user_input[CONF_URL].strip(), user_input[CONF_TOKEN].strip())
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(info["vin"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=_title(info["vin"]),
                    data={CONF_MODE: MODE_SERVER, CONF_URL: info["url"], CONF_TOKEN: user_input[CONF_TOKEN].strip(),
                          CONF_VIN: info["vin"]})
        return self.async_show_form(
            step_id="server",
            data_schema=self.add_suggested_values_to_schema(
                vol.Schema({vol.Required(CONF_URL): URL, vol.Required(CONF_TOKEN): PASSWORD}), user_input),
            errors=errors)

    # MARK: Direct

    async def async_step_direct(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if self._client is None:
            self._storage_id = uuid.uuid4().hex
            self._client = await self.hass.async_add_executor_job(
                make_client, storage_dir(self.hass, self._storage_id))
        if self._certificate is None:
            # Made once per flow, so it doesn't change under someone who has already uploaded it.
            self._certificate = (await self.hass.async_add_executor_job(self._client.certificate_pem)).strip()
        errors: dict[str, str] = {}
        placeholders = {"certificate": self._certificate, "error": ""}
        if user_input is not None:
            vin = user_input[CONF_VIN].strip().upper()
            if len(vin) != 17:
                errors[CONF_VIN] = "invalid_vin"
            else:
                await self.async_set_unique_id(vin)
                self._abort_if_unique_id_configured()
                config = Config(user_input[CONF_CLIENT_ID].strip(), vin,
                                (user_input.get(CONF_STREAM_USERNAME) or "").strip(),
                                (user_input.get(CONF_ACCOUNT_ID) or "").strip())
                await self.hass.async_add_executor_job(self._client.save_config, config)
                error = await self._start_signin()
                if error is None:
                    return await self.async_step_signin()
                errors["base"] = "signin_start"
                placeholders["error"] = error
        schema = vol.Schema({
            vol.Required(CONF_CLIENT_ID): str,
            vol.Required(CONF_VIN): str,
            vol.Optional(CONF_STREAM_USERNAME): str,
            vol.Optional(CONF_ACCOUNT_ID): str,
        })
        # hassfest wants links passed in as placeholders, not written into strings.json.
        placeholders["portal_url"] = "https://developer.jlr.com"
        return self.async_show_form(step_id="direct", data_schema=self.add_suggested_values_to_schema(schema, user_input),
                                    errors=errors, description_placeholders=placeholders)

    async def _start_signin(self) -> str | None:
        assert self._client
        try:
            self._auth = await self.hass.async_add_executor_job(self._client.start_device_authorization)
        except JLRError as err:
            return str(err)
        except Exception as err:  # network errors from httpx
            return f"Couldn't reach JLR: {err}"
        self._signin_task = None
        self._signin_error = None
        return None

    async def _wait_for_signin(self) -> None:
        assert self._client and self._auth
        try:
            await self.hass.async_add_executor_job(self._client.poll_device_token, self._auth, self._cancel.is_set)
            await self.hass.async_add_executor_job(_finish_direct_setup, self._client)
        except JLRError as err:
            self._signin_error = str(err)
        except Exception as err:
            self._signin_error = f"Couldn't reach JLR: {err}"

    async def async_step_signin(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._auth
        if self._signin_task is None:
            self._signin_task = self.hass.async_create_task(self._wait_for_signin(), eager_start=False)
        if not self._signin_task.done():
            return self.async_show_progress(
                step_id="signin", progress_action="signin", progress_task=self._signin_task,
                description_placeholders={
                    "url": self._auth.verification_uri_complete or self._auth.verification_uri,
                    "code": self._auth.user_code})
        if self._signin_error:
            return self.async_show_progress_done(next_step_id="signin_failed")
        return self.async_show_progress_done(next_step_id="signin_done")

    async def async_step_signin_failed(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason="signin_failed", description_placeholders={"error": self._signin_error or ""})

    async def async_step_signin_done(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._client
        cfg = self._client.config
        await self.hass.async_add_executor_job(self._client.http.close)
        self._created = True
        data = {CONF_MODE: MODE_DIRECT, CONF_STORAGE_ID: self._storage_id, CONF_CLIENT_ID: cfg.client_id,
                CONF_VIN: cfg.vin, CONF_STREAM_USERNAME: cfg.stream_username, CONF_ACCOUNT_ID: cfg.account_id}
        if self.source == "reauth":
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=data)
        return self.async_create_entry(title=_title(cfg.vin), data=data)

    # MARK: Reauth

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        if entry_data.get(CONF_MODE) == MODE_DIRECT:
            return await self.async_step_reauth_direct()
        return await self.async_step_reauth_server()

    async def async_step_reauth_direct(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            entry = self._get_reauth_entry()
            self._storage_id = entry.data[CONF_STORAGE_ID]
            if self._client is None:
                self._client = await self.hass.async_add_executor_job(
                    make_client, storage_dir(self.hass, self._storage_id))
            await self.hass.async_add_executor_job(self._client.save_config, DirectCoordinator.config_from_entry(entry))
            error = await self._start_signin()
            if error is None:
                return await self.async_step_signin()
            errors["base"] = "signin_start"
            placeholders["error"] = error
        return self.async_show_form(step_id="reauth_direct", errors=errors, description_placeholders=placeholders)

    async def async_step_reauth_server(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        if user_input is not None:
            info, error = await self._check_server(entry.data[CONF_URL], user_input[CONF_TOKEN].strip())
            if error:
                errors["base"] = error
            elif info["vin"] != entry.unique_id:
                errors["base"] = "wrong_vehicle"
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: user_input[CONF_TOKEN].strip()})
        return self.async_show_form(step_id="reauth_server", data_schema=vol.Schema({vol.Required(CONF_TOKEN): PASSWORD}),
                                    errors=errors, description_placeholders={"url": entry.data[CONF_URL]})

    @callback
    def async_remove(self) -> None:
        """The flow ended: stop polling for a sign-in, and drop a key that never became an entry."""
        self._cancel.set()
        if self._client is not None:
            client = self._client
            self.hass.async_add_executor_job(client.http.close)
            if not self._created and self.source != "reauth" and self._storage_id:
                self.hass.async_add_executor_job(remove_storage, storage_dir(self.hass, self._storage_id))


class JLROptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        entry = self.config_entry
        if entry.data[CONF_MODE] == MODE_SERVER:
            schema = vol.Schema({vol.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): NumberSelector(
                NumberSelectorConfig(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL, step=5,
                                     unit_of_measurement="s", mode=NumberSelectorMode.BOX))})
        else:
            schema = vol.Schema({vol.Optional(CONF_STREAM_USERNAME): str, vol.Optional(CONF_ACCOUNT_ID): str})
            current = {k: entry.options.get(k, entry.data.get(k, "")) for k in (CONF_STREAM_USERNAME, CONF_ACCOUNT_ID)}
            return self.async_show_form(step_id="init", data_schema=self.add_suggested_values_to_schema(schema, current))
        return self.async_show_form(step_id="init", data_schema=self.add_suggested_values_to_schema(schema, entry.options))
