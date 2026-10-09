"""Intégration Home Assistant pour les centrales solaires Solenso (cloud monitor.solenso.net)."""

from __future__ import annotations

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration

from .api import SolensoApi
from .const import DOMAIN
from .coordinator import SolensoConfigEntry, SolensoCoordinator
from .entity import dtu_device, micro_device, station_device
from .frontend import async_register_card

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def _register_card(hass: HomeAssistant) -> None:
    integration = await async_get_integration(hass, DOMAIN)
    await async_register_card(hass, str(integration.version))


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Déclarer la carte dès le démarrage, sans attendre le cloud Solenso."""
    await _register_card(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: SolensoConfigEntry) -> bool:
    """Mettre en place une entrée de configuration."""
    api = SolensoApi(
        async_get_clientsession(hass), entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD]
    )
    coordinator = SolensoCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    # Créer tous les appareils ici, puis les rattacher : centrale > DTU > onduleurs.
    registry = dr.async_get(hass)

    def create(info, parent=None):
        device = registry.async_get_or_create(config_entry_id=entry.entry_id, **info)
        if parent is not None and device.via_device_id != parent.id:
            device = registry.async_update_device(device.id, via_device_id=parent.id) or device
        return device

    for station in coordinator.stations:
        sid = station["id"]
        station_dev = create(station_device(station))
        dtus = list(coordinator.data[sid].dtus.values())
        known = {d.get("sn") for d in dtus}
        # DTU citées par les onduleurs mais absentes de la liste (appel en échec).
        for micro in coordinator.micros.get(sid, []):
            sn = micro.get("dtu_sn")
            if sn and sn not in known:
                known.add(sn)
                dtus.append({"id": micro.get("dtu_id") or sn, "sn": sn})
        dtu_devs = {d.get("sn"): create(dtu_device(sid, d), station_dev) for d in dtus}
        for micro in coordinator.micros.get(sid, []):
            create(micro_device(sid, micro), dtu_devs.get(micro.get("dtu_sn"), station_dev))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Filet de sécurité si l'interface web n'était pas prête au démarrage.
    await _register_card(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SolensoConfigEntry) -> bool:
    """Décharger une entrée de configuration."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
