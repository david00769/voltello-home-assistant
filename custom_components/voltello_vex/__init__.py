"""Voltello (Village Energy VE-X) for Home Assistant: the control state Voltello applies.

Unofficial. Read-only. One config entry per Voltello service point.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from homeassistant.helpers.storage import Store

from .api import VexClient
from .const import CONF_API_KEY, CONF_BASE_URL, CONF_CUSTOMER_ID, DOMAIN, STORAGE_VERSION
from .coordinator import VexCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

type VexConfigEntry = ConfigEntry[VexCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: VexConfigEntry) -> bool:
    client = VexClient(async_get_clientsession(hass), entry.data[CONF_BASE_URL], entry.data[CONF_API_KEY],
                       entry.data[CONF_CUSTOMER_ID])
    coordinator = VexCoordinator(hass, entry, client)
    await coordinator.async_load_poll_state()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # No update listener: options are read on every tick, so saving them needs no reload.
    return True


async def async_unload_entry(hass: HomeAssistant, entry: VexConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: VexConfigEntry) -> None:
    """Delete the stored polling state with the entry."""
    await Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}").async_remove()
