"""Coordinateur de mise à jour Solenso."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import SolensoApi, SolensoAuthError, SolensoError
from .const import (
    CONF_STATIONS,
    DEFAULT_SCAN_INTERVAL,
    DEVICES_REFRESH_INTERVAL,
    DOMAIN,
    MICRO_STALE_DELAY,
)
from .module_pb import MicroDay

_LOGGER = logging.getLogger(__name__)

type SolensoConfigEntry = ConfigEntry[SolensoCoordinator]


@dataclass
class PortState:
    """Dernières valeurs d'une entrée PV (un panneau)."""

    power: float = 0.0
    voltage: float = 0.0
    current: float = 0.0
    energy: float = 0.0


@dataclass
class MicroState:
    """Dernières valeurs d'un micro-onduleur."""

    last_update: datetime | None = None
    asleep: bool = True
    ports: dict[int, PortState] = field(default_factory=dict)
    temperature: float | None = None
    grid_voltage: float | None = None
    grid_frequency: float | None = None

    @property
    def power(self) -> float:
        return round(sum(p.power for p in self.ports.values()), 2)

    @property
    def energy(self) -> float:
        return round(sum(p.energy for p in self.ports.values()), 2)


@dataclass
class StationData:
    """Données d'une centrale."""

    real: dict[str, Any]
    micros: dict[int, MicroState] = field(default_factory=dict)
    dtus: dict[int, dict[str, Any]] = field(default_factory=dict)


def _last(values: list[float], index: int) -> float | None:
    if not values:
        return None
    return values[min(index, len(values) - 1)]


def micro_state(day: MicroDay | None, day_date: date, now: datetime) -> MicroState:
    """Calculer l'état courant d'un onduleur à partir de sa série du jour."""
    if day is None or not day.times:
        return MicroState()
    index = len(day.times) - 1
    try:
        hour, minute = (int(x) for x in day.times[index].split(":")[:2])
        last_update = datetime.combine(day_date, time(hour, minute), tzinfo=now.tzinfo)
    except ValueError:
        last_update = None
    asleep = last_update is not None and now - last_update > MICRO_STALE_DELAY

    ports: dict[int, PortState] = {}
    for port, points in day.ports.items():
        if not points:
            continue
        point = points[min(index, len(points) - 1)]
        if asleep:
            # Un panneau endormi ne produit plus ; l'énergie du jour reste acquise.
            ports[port] = PortState(energy=point.energy)
        else:
            ports[port] = PortState(point.power, point.voltage, point.current, point.energy)

    return MicroState(
        last_update=last_update,
        asleep=asleep,
        ports=ports,
        temperature=None if asleep else _last(day.temperature, index),
        grid_voltage=None if asleep else _last(day.grid_voltage, index),
        grid_frequency=None if asleep else _last(day.grid_frequency, index),
    )


def _positions(items: list[dict[str, Any]]) -> dict[int, dict[str, int]]:
    """Première position connue de chaque onduleur (le port 1 pour un onduleur à plusieurs entrées)."""
    positions: dict[int, dict[str, int]] = {}
    for item in sorted(items, key=lambda i: (i.get("port") or 0)):
        try:
            micro_id, row, column = int(item["mi_id"]), int(item["x"]), int(item["y"])
        except (KeyError, TypeError, ValueError):
            continue
        positions.setdefault(micro_id, {"row": row, "column": column, "array": int(item.get("aid") or 0)})
    return positions


class SolensoCoordinator(DataUpdateCoordinator[dict[int, StationData]]):
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
        # Inventaire des micro-onduleurs par centrale : {sid: [micro, ...]}
        self.micros: dict[int, list[dict[str, Any]]] = {}
        # Position de chaque onduleur sur le plan : {sid: {id onduleur: {"row", "column", "array"}}}
        self.layout: dict[int, dict[int, dict[str, int]]] = {}
        self._micros_fetched_at: datetime | None = None
        self._module_warned = False

    async def _refresh_inventory(self) -> None:
        now = dt_util.utcnow()
        if self._micros_fetched_at and now - self._micros_fetched_at < DEVICES_REFRESH_INTERVAL:
            return
        for station in self.stations:
            try:
                self.micros[station["id"]] = await self.api.get_micros(station["id"])
            except SolensoAuthError:
                raise
            except SolensoError as err:
                _LOGGER.warning("Liste des micro-onduleurs indisponible : %s", err)
                self.micros.setdefault(station["id"], [])
            try:
                self.layout[station["id"]] = _positions(await self.api.get_layout(station["id"]))
            except SolensoAuthError:
                raise
            except SolensoError as err:
                _LOGGER.debug("Disposition des panneaux indisponible : %s", err)
                self.layout.setdefault(station["id"], {})
        self._micros_fetched_at = now

    async def _station(self, sid: int, previous: StationData | None) -> StationData:
        station = StationData(real=await self.api.get_station_real_data(sid))

        try:
            station.dtus = {d["id"]: d for d in await self.api.get_dtus(sid) if "id" in d}
        except SolensoAuthError:
            raise
        except SolensoError as err:
            _LOGGER.debug("État des DTU indisponible : %s", err)
            station.dtus = previous.dtus if previous else {}

        if not self.micros.get(sid):
            return station
        now = dt_util.now()
        try:
            days = await self.api.get_module_day_data(sid, now.date().isoformat())
        except SolensoAuthError:
            raise
        except SolensoError as err:
            if not self._module_warned:
                _LOGGER.warning("Données par micro-onduleur indisponibles : %s", err)
                self._module_warned = True
            station.micros = previous.micros if previous else {}
            return station
        self._module_warned = False
        station.micros = {
            micro["id"]: micro_state(days.get(micro["id"]), now.date(), now)
            for micro in self.micros[sid]
        }
        return station

    async def _async_update_data(self) -> dict[int, StationData]:
        previous = self.data or {}
        data: dict[int, StationData] = {}
        try:
            await self._refresh_inventory()
            for station in self.stations:
                data[station["id"]] = await self._station(station["id"], previous.get(station["id"]))
        except SolensoAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except SolensoError as err:
            raise UpdateFailed(str(err)) from err
        return data
