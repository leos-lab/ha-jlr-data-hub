"""JLR Data Hub: read-only data from a Jaguar or Land Rover, through JLR's owner API (EU Data Act access).

Two ways in: this Home Assistant holds its own JLR credential (direct), or it reads an existing jlr-server that
holds one (server). JLR allows one credential per account, so a car has one or the other.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import CONF_MODE, CONF_STORAGE_ID, CONF_VIN, MODE_DIRECT
from .coordinator import (
    DirectCoordinator,
    JLRCoordinator,
    ServerCoordinator,
    make_client,
    remove_storage,
    storage_dir,
)

PLATFORMS = [Platform.BINARY_SENSOR, Platform.DEVICE_TRACKER, Platform.SENSOR]

type JLRConfigEntry = ConfigEntry[JLRCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: JLRConfigEntry) -> bool:
    if entry.data[CONF_MODE] == MODE_DIRECT:
        client = await hass.async_add_executor_job(make_client, storage_dir(hass, entry.data[CONF_STORAGE_ID]))
        config = DirectCoordinator.config_from_entry(entry)
        if config != client.config:
            await hass.async_add_executor_job(client.save_config, config)
        if not client.signed_in:
            await hass.async_add_executor_job(client.http.close)
            raise ConfigEntryAuthFailed("Sign in to JLR again.")
        coordinator: JLRCoordinator = DirectCoordinator(hass, entry, client)
        try:
            await coordinator.async_config_entry_first_refresh()
        except Exception:
            await hass.async_add_executor_job(client.http.close)
            raise
        coordinator.start_stream()
    else:
        vin = entry.unique_id or entry.data.get(CONF_VIN, "")
        coordinator = ServerCoordinator(hass, entry, vin)
        await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _reload(hass: HomeAssistant, entry: JLRConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: JLRConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_shutdown()
    return ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Direct mode: the key and tokens go with the entry. (The JLR portal credential stays until you delete it.)"""
    if entry.data.get(CONF_MODE) == MODE_DIRECT and entry.data.get(CONF_STORAGE_ID):
        await hass.async_add_executor_job(remove_storage, storage_dir(hass, entry.data[CONF_STORAGE_ID]))

