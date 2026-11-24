"""Server mode: the config flow, entities from a real jlr-server response, and a refused token."""
from __future__ import annotations

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.jlr_data_hub.const import CONF_MODE, CONF_TOKEN, CONF_URL, CONF_VIN, DOMAIN, MODE_SERVER

from .conftest import URL, VIN, load


def mock_server(aioclient_mock: AiohttpClientMocker, status: int = 200) -> None:
    aioclient_mock.clear_requests()
    if status != 200:
        for path in ("status", "state", "journeys"):
            aioclient_mock.get(f"{URL}/api/{path}", status=status)
        return
    aioclient_mock.get(f"{URL}/api/status", json=load("server_status.json"))
    aioclient_mock.get(f"{URL}/api/state", json=load("server_state.json"))
    aioclient_mock.get(f"{URL}/api/journeys", json=load("server_journeys.json"))


def server_entry() -> MockConfigEntry:
    return MockConfigEntry(domain=DOMAIN, unique_id=VIN, title="JLR",
                           data={CONF_MODE: MODE_SERVER, CONF_URL: URL, CONF_TOKEN: "secret", CONF_VIN: VIN})


async def test_flow_creates_entry(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_server(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "server"})
    assert result["step_id"] == "server"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL + "/", CONF_TOKEN: " secret "})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_MODE: MODE_SERVER, CONF_URL: URL, CONF_TOKEN: "secret", CONF_VIN: VIN}
    assert result["result"].unique_id == VIN
    assert aioclient_mock.mock_calls[0][3]["Authorization"] == "Bearer secret"
    await hass.async_block_till_done()


async def test_flow_errors(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "server"})
    mock_server(aioclient_mock, 401)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL, CONF_TOKEN: "bad"})
    assert result["errors"] == {"base": "invalid_auth"}
    mock_server(aioclient_mock, 500)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL, CONF_TOKEN: "x"})
    assert result["errors"] == {"base": "cannot_connect"}


async def test_flow_aborts_for_a_car_already_set_up(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    server_entry().add_to_hass(hass)
    mock_server(aioclient_mock)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "server"})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_URL: URL, CONF_TOKEN: "secret"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "already_configured"


async def test_entities(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_server(aioclient_mock)
    entry = server_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    def state(entity_id: str):
        s = hass.states.get(entity_id)
        assert s is not None, entity_id
        return s

    assert float(state("sensor.jlr_vehicle_battery").state) == 90.0
    assert float(state("sensor.jlr_vehicle_range").state) == 334.0
    assert state("sensor.jlr_vehicle_charge_limit").state == "unknown"  # the car sent -1
    assert state("sensor.jlr_vehicle_charging_state").state == "complete"
    assert float(state("sensor.jlr_vehicle_time_to_full").state) == 0.0
    assert float(state("sensor.jlr_vehicle_odometer").state) == 54321.0
    assert float(state("sensor.jlr_vehicle_distance_to_service").state) == 9800.0
    assert float(state("sensor.jlr_vehicle_tyre_pressure_front_left").state) == 243.0
    assert float(state("sensor.jlr_vehicle_12_v_battery").state) == 14.1
    assert state("binary_sensor.jlr_vehicle_lock").state == "off"  # locked
    assert state("binary_sensor.jlr_vehicle_door_front_left").state == "off"
    assert state("binary_sensor.jlr_vehicle_window_rear_right").state == "off"
    assert state("binary_sensor.jlr_vehicle_boot").state == "off"
    assert state("binary_sensor.jlr_vehicle_bonnet").state == "off"
    assert state("binary_sensor.jlr_vehicle_plugged_in").state == "unknown"
    assert state("binary_sensor.jlr_vehicle_jlr_sign_in").state == "on"
    assert state("sensor.jlr_vehicle_stream").state == "live"
    trip = state("sensor.jlr_vehicle_last_trip")
    assert float(trip.state) == 31.06
    assert trip.attributes["soc_used"] == 6 and trip.attributes["soc_start"] == 80
    assert trip.attributes["duration_minutes"] == 36.8
    tracker = state("device_tracker.jlr_vehicle_location")
    assert (tracker.attributes["latitude"], tracker.attributes["longitude"]) == (51.5007, -0.1246)

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_refused_token_starts_reauth(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_server(aioclient_mock, 401)
    entry = server_entry()
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_ERROR
    [flow] = hass.config_entries.flow.async_progress()
    assert flow["context"]["source"] == "reauth" and flow["step_id"] == "reauth_server"

    mock_server(aioclient_mock)
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {CONF_TOKEN: "new"})
    assert result["type"] is FlowResultType.ABORT and result["reason"] == "reauth_successful"
    assert entry.data[CONF_TOKEN] == "new"


async def test_options_change_the_interval(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    mock_server(aioclient_mock)
    entry = server_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(result["flow_id"], {"scan_interval": 30})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.runtime_data.update_interval.total_seconds() == 30
