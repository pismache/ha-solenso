"""Intégration Home Assistant pour les centrales solaires Solenso (cloud monitor.solenso.net)."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SolensoApi
from .coordinator import SolensoConfigEntry, SolensoCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: SolensoConfigEntry) -> bool:
    """Mettre en place une entrée de configuration."""
    api = SolensoApi(
        async_get_clientsession(hass), entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    coordinator = SolensoCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SolensoConfigEntry) -> bool:
    """Décharger une entrée de configuration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
