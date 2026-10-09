"""Coordinateur de mise à jour Solenso."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SolensoApi, SolensoAuthError, SolensoError
from .const import CONF_STATIONS, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)

type SolensoConfigEntry = ConfigEntry[SolensoCoordinator]


class SolensoCoordinator(DataUpdateCoordinator[dict[int, dict[str, Any]]]):
    """Récupère les données de toutes les centrales du compte."""

    config_entry: SolensoConfigEntry

    def __init__(self, hass: HomeAssistant, entry: SolensoConfigEntry, api: SolensoApi) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=DEFAULT_SCAN_INTERVAL,
        )
        self.api = api
        self.stations: list[dict[str, Any]] = entry.data[CONF_STATIONS]

    async def _async_update_data(self) -> dict[int, dict[str, Any]]:
        data: dict[int, dict[str, Any]] = {}
        try:
            for station in self.stations:
                data[station["id"]] = await self.api.get_station_real_data(station["id"])
        except SolensoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SolensoError as err:
            raise UpdateFailed(str(err)) from err
        return data
