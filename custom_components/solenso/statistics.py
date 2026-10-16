"""Production horaire écrite dans les statistiques de Home Assistant, pour le tableau Énergie.

Le cloud garde, pour chaque onduleur et chaque entrée PV, le cumul du jour par pas de
15 minutes. Quand la passerelle DTU perd Internet, elle renvoie ses mesures plus tard :
le cloud complète alors la journée après coup. Un capteur ne peut pas réécrire le passé ;
une statistique externe (comme celle de l'add-on Linky) le peut. On y écrit donc la
production heure par heure, à l'heure où elle a été produite, et on réécrit les dernières
journées à chaque nouvelle lecture : une mesure arrivée en retard prend sa vraie place.

Au premier lancement, l'historique disponible dans le cloud est repris jour par jour.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta, tzinfo
import logging

from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .api import SolensoApi, SolensoAuthError, SolensoError
from .const import (
    BACKFILL_EMPTY_DAYS,
    BACKFILL_MAX_DAYS,
    BACKFILL_REQUEST_DELAY,
    CATCH_UP_MAX_DAYS,
    DOMAIN,
)
from .module_pb import MicroDay

_LOGGER = logging.getLogger(__name__)

Days = dict[int, MicroDay]


def statistic_id(sid: int) -> str:
    """Identifiant de la statistique de production d'une centrale."""
    return f"{DOMAIN}:production_{sid}"


def hourly_production(days: Days, day: date, tz: tzinfo) -> dict[datetime, float]:
    """Énergie produite (Wh) par heure, clé = début de l'heure en UTC.

    Chaque point donne le cumul du jour à son horodatage : l'énergie entre deux points
    est comptée dans l'heure où se termine l'intervalle (08:45 → 08:30-08:45 → 8 h).
    """
    hours: dict[datetime, float] = {}
    for micro in days.values():
        for points in micro.ports.values():
            previous = 0.0
            for stamp, point in zip(micro.times, points):
                try:
                    hour, minute = (int(x) for x in stamp.split(":")[:2])
                    end = datetime.combine(day, time(hour, minute), tzinfo=tz)
                except ValueError:
                    continue
                delta = point.energy - previous
                previous = max(previous, point.energy)
                if delta <= 0:
                    continue  # point manquant (0) ou correction du cloud : rien à ajouter
                bucket = (end - timedelta(minutes=1)).replace(minute=0, second=0, microsecond=0)
                if bucket.date() != day:
                    bucket = datetime.combine(day, time(0), tzinfo=tz)
                key = bucket.astimezone(UTC)
                hours[key] = hours.get(key, 0.0) + delta
    return hours


def _day_hours(day: date) -> list[datetime]:
    """Débuts d'heure (UTC) d'une journée locale, changements d'heure compris."""
    start = dt_util.start_of_local_day(day).astimezone(UTC)
    end = dt_util.start_of_local_day(day + timedelta(days=1)).astimezone(UTC)
    hours, current = [], start
    while current < end:
        hours.append(current)
        current += timedelta(hours=1)
    return hours


def build_rows(
    base_sum: float, days: Iterable[tuple[date, Days]], now: datetime
) -> list[dict]:
    """Lignes horaires (début, cumul du jour, somme) de chaque journée, jusqu'à l'heure en cours."""
    tz = dt_util.get_default_time_zone()
    current_hour = now.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    rows: list[dict] = []
    total = base_sum
    for day, data in days:
        hourly = hourly_production(data, day, tz)
        day_total = 0.0
        for start in _day_hours(day):
            if start > current_hour:
                break
            energy = hourly.get(start, 0.0)
            day_total += energy
            total += energy
            rows.append({"start": start, "state": round(day_total, 2), "sum": round(total, 2)})
    return rows


class ProductionStatistics:
    """Tient à jour la statistique de production d'une centrale."""

    def __init__(self, hass: HomeAssistant, api: SolensoApi, station: dict) -> None:
        self.hass = hass
        self.api = api
        self.sid: int = station["id"]
        self.name: str = station.get("name") or f"Centrale {self.sid}"
        self.statistic_id = statistic_id(self.sid)
        self._backfill: asyncio.Task | None = None
        self._signature: tuple | None = None

    @property
    def _recorder_ready(self) -> bool:
        return "recorder" in self.hass.config.components

    def _metadata(self) -> dict:
        from homeassistant.components.recorder.models import StatisticMeanType  # noqa: PLC0415

        return {
            "mean_type": StatisticMeanType.NONE,
            "has_sum": True,
            "name": f"{self.name} Production",
            "source": DOMAIN,
            "statistic_id": self.statistic_id,
            "unit_class": "energy",
            "unit_of_measurement": UnitOfEnergy.WATT_HOUR,
        }

    def _import(self, rows: list[dict]) -> None:
        from homeassistant.components.recorder.models import StatisticData  # noqa: PLC0415
        from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
            async_add_external_statistics,
        )

        if rows:
            async_add_external_statistics(
                self.hass, self._metadata(), [StatisticData(**row) for row in rows]
            )

    async def _last_row(self) -> dict | None:
        from homeassistant.components.recorder import get_instance  # noqa: PLC0415
        from homeassistant.components.recorder.statistics import get_last_statistics  # noqa: PLC0415

        result = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, self.statistic_id, False, {"sum"}
        )
        rows = result.get(self.statistic_id) or []
        return rows[0] if rows else None

    async def _sum_before(self, day: date) -> float:
        """Somme à la fin de la journée précédant `day` (0 au tout début de l'historique)."""
        from homeassistant.components.recorder import get_instance  # noqa: PLC0415
        from homeassistant.components.recorder.statistics import (  # noqa: PLC0415
            statistics_during_period,
        )

        end = dt_util.start_of_local_day(day)
        result = await get_instance(self.hass).async_add_executor_job(
            statistics_during_period,
            self.hass, end - timedelta(days=2), end, {self.statistic_id}, "hour", None, {"sum"},
        )
        rows = result.get(self.statistic_id) or []
        return float(rows[-1]["sum"] or 0.0) if rows else 0.0

    async def _fetch(self, day: date) -> Days:
        return await self.api.get_module_day_data(self.sid, day.isoformat())

    async def async_update(self, known: dict[date, Days], now: datetime | None = None) -> None:
        """Réécrire les dernières journées avec les mesures connues (aujourd'hui, veille...)."""
        if not self._recorder_ready or (self._backfill and not self._backfill.done()):
            return
        now = now or dt_util.now()
        today = now.date()
        last = await self._last_row()
        if last is None:
            self._backfill = self.hass.async_create_background_task(
                self._async_backfill(dict(known), now), f"{DOMAIN} historique {self.sid}"
            )
            return

        last_day = dt_util.as_local(dt_util.utc_from_timestamp(last["start"])).date()
        start_day = max(min(today - timedelta(days=1), last_day), today - timedelta(days=CATCH_UP_MAX_DAYS))
        signature = (
            start_day,
            now.replace(minute=0, second=0, microsecond=0),
            tuple(
                (day, round(sum(sum(p.energy for p in pts) for m in data.values() for pts in m.ports.values()), 1))
                for day, data in sorted(known.items())
            ),
        )
        if signature == self._signature:
            return

        base = float(last["sum"] or 0.0) if start_day > last_day else await self._sum_before(start_day)
        days: list[tuple[date, Days]] = []
        day = start_day
        while day <= today:
            data = known.get(day)
            if data is None:
                data = await self._fetch(day)  # journée manquée (Home Assistant éteint...)
            days.append((day, data))
            day += timedelta(days=1)
        self._import(build_rows(base, days, now))
        self._signature = signature

    async def _async_backfill(self, known: dict[date, Days], now: datetime) -> None:
        """Premier lancement : reprendre l'historique du cloud, du plus ancien au plus récent."""
        today = now.date()
        collected: list[tuple[date, Days]] = []
        empty = 0
        for offset in range(BACKFILL_MAX_DAYS + 1):
            day = today - timedelta(days=offset)
            data = known.get(day)
            if data is None:
                if offset:
                    await asyncio.sleep(BACKFILL_REQUEST_DELAY)
                try:
                    data = await self._fetch(day)
                except SolensoAuthError:
                    _LOGGER.warning("Historique interrompu : identifiants refusés")
                    break
                except SolensoError as err:
                    _LOGGER.warning("Historique interrompu au %s : %s", day, err)
                    break
            if any(pts for m in data.values() for pts in m.ports.values()):
                empty = 0
            else:
                empty += 1
                if empty >= BACKFILL_EMPTY_DAYS:
                    break  # avant la mise en service, ou historique non conservé par le cloud
            collected.append((day, data))
        # Retirer les journées vides du début : l'historique commence à la première production.
        collected.reverse()
        while collected and not any(pts for m in collected[0][1].values() for pts in m.ports.values()):
            collected.pop(0)
        if not collected:
            _LOGGER.debug("Aucun historique de production dans le cloud")
            return
        _LOGGER.info(
            "Historique de production repris depuis le %s (%d jours)", collected[0][0], len(collected)
        )
        self._import(build_rows(0.0, collected, now))
