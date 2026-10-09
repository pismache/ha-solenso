"""Intégration Home Assistant pour les centrales solaires Solenso (cloud monitor.solenso.net)."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration

from .api import SolensoApi
from .const import DOMAIN
from .coordinator import SolensoConfigEntry, SolensoCoordinator
from .entity import dtu_device, station_device
from .frontend import async_register_card

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: SolensoConfigEntry) -> bool:
    """Mettre en place une entrée de configuration."""
    api = SolensoApi(
        async_get_clientsession(hass), entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    coordinator = SolensoCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Enregistrer centrale puis DTU avant les onduleurs, qui s'y rattachent.
    registry = dr.async_get(hass)
    for station in coordinator.stations:
        registry.async_get_or_create(config_entry_id=entry.entry_id, **station_device(station))
        dtus = list(coordinator.data[station["id"]].dtus.values())
        known = {d.get("sn") for d in dtus}
        # DTU citées par les onduleurs mais absentes de la liste (appel en échec).
        for micro in coordinator.micros.get(station["id"], []):
            sn = micro.get("dtu_sn")
            if sn and sn not in known:
                known.add(sn)
                dtus.append({"id": micro.get("dtu_id") or sn, "sn": sn})
        for dtu in dtus:
            registry.async_get_or_create(
                config_entry_id=entry.entry_id, **dtu_device(station["id"], dtu)
            )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    integration = await async_get_integration(hass, DOMAIN)
    await async_register_card(hass, str(integration.version))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SolensoConfigEntry) -> bool:
    """Décharger une entrée de configuration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
