"""Direct mode: the key and certificate, Device Code sign-in, REST plus stream, and signing in again. JLR itself is
mocked at the vendored client's network methods; the keys, certificate and token storage are real."""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from cryptography import x509
from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.jlr_data_hub.const import (
    CONF_ACCOUNT_ID,
    CONF_CLIENT_ID,
    CONF_MODE,
    CONF_STORAGE_ID,
    CONF_STREAM_USERNAME,
    CONF_VIN,
    DOMAIN,
    MODE_DIRECT,
)
from custom_components.jlr_data_hub.jlr_datahub import Config, DeviceAuthorization, JLRClient, Tokens
from custom_components.jlr_data_hub.jlr_datahub.crypto import b64url
from custom_components.jlr_data_hub.jlr_datahub.signals import parse_signals

from .conftest import VIN

CLIENT = "custom_components.jlr_data_hub.jlr_datahub.client.JLRClient"
REST = {"Vehicle": {"Powertrain": {"TractionBattery": {"StateOfCharge": {"Displayed": "64"}, "Range": "250"}},
                    "TraveledDistance": "108900000"}, "timestamp": "2026-11-24T21:00:00Z"}
JOURNEYS = [{"journeyId": "1", "startTime": "2026-11-23T19:28:26Z", "endTime": "2026-11-23T20:05:14Z",
             "duration": 2208, "distance": {"value": 31.06, "unit": "km"}},
            {"journeyId": "0", "startTime": "2026-11-22T10:00:00Z", "endTime": "2026-11-22T10:30:00Z",
             "distance": {"value": 5, "unit": "km"}}]


def fake_jwt(claims: dict) -> str:
    return ".".join(b64url(json.dumps(x).encode()) for x in ({"alg": "none"}, claims)) + ".sig"


def signed_in_tokens() -> Tokens:
    now = time.time()
    return Tokens(access_token="access", expires_at=now + 300, refresh_token="refresh", refresh_expires_at=now + 86400)


def fake_poll(self: JLRClient, auth, should_stop=lambda: False) -> Tokens:
    tokens = signed_in_tokens()
    self.save_tokens(tokens)
    return tokens


@pytest.fixture(autouse=True)
def config_dir(hass: HomeAssistant, tmp_path: Path):
    hass.config.config_dir = str(tmp_path)
    yield tmp_path


@pytest.fixture
def jlr():
    auth = DeviceAuthorization("device", "ABCD-EFGH", "https://auth.example/device",
                               "https://auth.example/device?user_code=ABCD-EFGH", time.time() + 600, 5, "verifier")
    with (
        patch(f"{CLIENT}.start_device_authorization", return_value=auth) as start,
        patch(f"{CLIENT}.poll_device_token", autospec=True, side_effect=fake_poll),
        patch(f"{CLIENT}.client_credentials", return_value=Tokens(
            fake_jwt({"dsas": {"account_id": "acc-9"}, "categories": ["ev"]}), time.time() + 300)),
        patch(f"{CLIENT}.snapshot", return_value=(parse_signals(REST), {})) as snapshot,
        patch(f"{CLIENT}.journeys", return_value=JOURNEYS),
        patch("custom_components.jlr_data_hub.jlr_datahub.stream.Stream.start") as stream_start,
    ):
        yield {"start": start, "snapshot": snapshot, "stream_start": stream_start}


async def test_flow_signs_in_and_keeps_the_key(hass: HomeAssistant, jlr, config_dir: Path) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "direct"})
    assert result["step_id"] == "direct"
    pem = result["description_placeholders"]["certificate"]
    cert = x509.load_pem_x509_certificate(pem.encode())
    assert cert.signature_algorithm_oid.dotted_string == "1.2.840.113549.1.1.10"  # RSASSA-PSS

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CLIENT_ID: "cid", CONF_VIN: "short"})
    assert result["errors"] == {CONF_VIN: "invalid_vin"}
    assert result["description_placeholders"]["certificate"] == pem  # same key on a retry

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CLIENT_ID: " cid ", CONF_VIN: VIN.lower(), CONF_STREAM_USERNAME: "streamer"})
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    assert result["description_placeholders"] == {"url": "https://auth.example/device?user_code=ABCD-EFGH",
                                                  "code": "ABCD-EFGH"}
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data[CONF_MODE] == MODE_DIRECT and data[CONF_VIN] == VIN and data[CONF_CLIENT_ID] == "cid"
    assert data[CONF_STREAM_USERNAME] == "streamer" and data[CONF_ACCOUNT_ID] == "acc-9"  # from the token
    folder = config_dir / ".storage" / DOMAIN / data[CONF_STORAGE_ID]
    assert {p.name for p in folder.iterdir()} >= {"client-key.pem", "dpop-key.pem", "tokens.json", "config.json"}
    assert os.stat(folder / "client-key.pem").st_mode & 0o777 == 0o600
    await hass.async_block_till_done()

    entry = result["result"]
    assert entry.state is ConfigEntryState.LOADED
    assert float(hass.states.get("sensor.jlr_vehicle_battery").state) == 64
    assert float(hass.states.get("sensor.jlr_vehicle_odometer").state) == 108900
    assert float(hass.states.get("sensor.jlr_vehicle_last_trip").state) == 31.06
    assert "soc_used" not in hass.states.get("sensor.jlr_vehicle_last_trip").attributes
    jlr["stream_start"].assert_called_once()

    # Removing the entry removes the key.
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert not folder.exists()


async def test_abandoned_flow_drops_its_key(hass: HomeAssistant, jlr, config_dir: Path) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "direct"})
    folder = config_dir / ".storage" / DOMAIN
    assert len(list(folder.iterdir())) == 1
    hass.config_entries.flow.async_abort(result["flow_id"])
    await hass.async_block_till_done(wait_background_tasks=True)
    assert list(folder.iterdir()) == []


async def test_refused_client_id(hass: HomeAssistant, jlr) -> None:
    from custom_components.jlr_data_hub.jlr_datahub import JLRError
    jlr["start"].side_effect = JLRError("Invalid client credentials", code="invalid_client")
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "direct"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_CLIENT_ID: "x", CONF_VIN: VIN})
    assert result["errors"] == {"base": "signin_start"}
    assert result["description_placeholders"]["error"] == "Invalid client credentials"


async def direct_entry(hass: HomeAssistant, signed_in: bool) -> MockConfigEntry:
    from custom_components.jlr_data_hub.coordinator import make_client, storage_dir
    client = await hass.async_add_executor_job(make_client, storage_dir(hass, "abc"))
    await hass.async_add_executor_job(client.save_config, Config("cid", VIN, "streamer", "acc"))
    if signed_in:
        await hass.async_add_executor_job(client.save_tokens, signed_in_tokens())
    entry = MockConfigEntry(domain=DOMAIN, unique_id=VIN, title="JLR", data={
        CONF_MODE: MODE_DIRECT, CONF_STORAGE_ID: "abc", CONF_CLIENT_ID: "cid", CONF_VIN: VIN,
        CONF_STREAM_USERNAME: "streamer", CONF_ACCOUNT_ID: "acc"})
    entry.add_to_hass(hass)
    return entry


async def test_stream_messages_update_entities(hass: HomeAssistant, jlr) -> None:
    entry = await direct_entry(hass, signed_in=True)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    coordinator = entry.runtime_data
    assert coordinator.client.config.stream_username == "streamer"
    assert float(hass.states.get("sensor.jlr_vehicle_battery").state) == 64

    # The stream calls back on its own thread, with newer values.
    message = {"name": "Vehicle.Powertrain.TractionBattery.StateOfCharge.Displayed", "value": "63",
               "timestamp": "2026-11-24T21:05:00Z"}
    t = threading.Thread(target=coordinator._stream_signals, args=(parse_signals(message), "topic"))
    t.start()
    t.join()
    await hass.async_block_till_done()
    assert float(hass.states.get("sensor.jlr_vehicle_battery").state) == 63
    # A REST poll with older values doesn't undo it.
    await coordinator.async_refresh()
    assert float(hass.states.get("sensor.jlr_vehicle_battery").state) == 63

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert coordinator.stream.stop_event.is_set()


async def test_lapsed_sign_in_asks_to_sign_in_again(hass: HomeAssistant, jlr) -> None:
    entry = await direct_entry(hass, signed_in=False)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    [flow] = hass.config_entries.flow.async_progress()
    assert flow["step_id"] == "reauth_direct"
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    assert result["type"] is FlowResultType.SHOW_PROGRESS
    await hass.async_block_till_done()
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert (Path(hass.config.config_dir) / ".storage" / DOMAIN / "abc").exists()  # same key, kept
