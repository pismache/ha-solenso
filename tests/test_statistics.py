"""Production horaire dans les statistiques (tableau Énergie), réécrite quand la DTU envoie en différé."""

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse
import pytest

from custom_components.solenso.module_pb import MicroDay, Point
from custom_components.solenso.statistics import build_rows, hourly_production, statistic_id

from .test_micros import DTU_LIST, DTUS, LAYOUT, LOGIN, MICRO_LIST, MICROS, MODULE, REAL, SID, _entry
from .test_micros import encode_day, encode_micro

PARIS = ZoneInfo("Europe/Paris")
DAY = date(2026, 10, 15)


def micro(micro_id: int, series: list[tuple[str, float]]) -> MicroDay:
    return MicroDay(micro_id, [t for t, _ in series], {1: [Point(energy=e) for _, e in series]})


def utc(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=PARIS).astimezone(UTC)


# --- Calcul heure par heure ------------------------------------------------------


def test_energy_goes_to_the_hour_the_interval_ends_in():
    days = {
        1: micro(1, [("09:00", 100.0), ("09:15", 180.0), ("09:30", 300.0), ("10:00", 500.0), ("10:15", 650.0)]),
        2: micro(2, [("09:15", 50.0), ("10:00", 150.0)]),
    }
    hours = hourly_production(days, DAY, PARIS)
    assert hours == {
        utc(DAY, 8): 100.0,  # 08:45-09:00
        utc(DAY, 9): 400.0 + 150.0,  # 09:00-10:00 : 400 pour l'un, 50 + 100 pour l'autre
        utc(DAY, 10): 150.0,
    }


def test_missing_points_and_cloud_corrections_add_nothing():
    days = {1: micro(1, [("12:00", 1000.0), ("12:15", 0.0), ("12:30", 1200.0), ("12:45", 1190.0), ("13:00", 1300.0)])}
    hours = hourly_production(days, DAY, PARIS)
    assert hours == {utc(DAY, 11): 1000.0, utc(DAY, 12): 300.0}


async def test_rows_are_cumulative_and_stop_at_the_current_hour(hass: HomeAssistant):
    await hass.config.async_set_time_zone("Europe/Paris")
    yesterday = {1: micro(1, [("12:00", 1000.0), ("13:00", 3000.0)])}
    today = {1: micro(1, [("09:00", 200.0), ("15:00", 900.0)])}
    now = datetime(2026, 10, 16, 11, 20, tzinfo=PARIS)
    rows = build_rows(50_000.0, [(DAY, yesterday), (date(2026, 10, 16), today)], now)
    assert len(rows) == 24 + 12  # toute la veille, aujourd'hui de 0 h à 11 h
    assert rows[23]["sum"] == 53_000.0 and rows[23]["state"] == 3000.0
    assert rows[-1]["start"] == utc(date(2026, 10, 16), 11)
    assert rows[-1]["sum"] == 53_200.0  # le point de 15 h n'est pas encore là


async def test_daylight_saving_day_has_25_hours(hass: HomeAssistant):
    await hass.config.async_set_time_zone("Europe/Paris")
    rows = build_rows(0.0, [(date(2026, 10, 25), {})], datetime(2026, 10, 27, tzinfo=PARIS))
    assert len(rows) == 25


# --- Dans Home Assistant, avec la vraie base de statistiques -----------------------


@pytest.fixture
def mock_recorder_before_hass(async_test_recorder):
    """Préparer la base de statistiques avant Home Assistant."""


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _day_body(series: list[tuple[str, float]]) -> bytes:
    return encode_day(
        encode_micro(101, [t for t, _ in series], {1: [(31.0, 5.0, 150.0, e) for _, e in series]},
                     [20.0] * len(series), [230.0] * len(series), [50.0] * len(series))
    )


def _mock(aioclient_mock, by_date: dict[str, bytes]):
    async def module(method, url, data):
        return AiohttpClientMockResponse(
            method, url, response=by_date.get(data["date"], b""),
            headers={"Content-Type": "application/octet-stream"},
        )

    t = (dt_util.now() - timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
    aioclient_mock.clear_requests()
    aioclient_mock.post(LOGIN, json={"status": "0", "data": {"token": "tok"}})
    aioclient_mock.post(LAYOUT, json={"status": "0", "data": []})
    aioclient_mock.post(REAL, json={"status": "0", "data": {"real_power": "0", "today_eq": "0", "month_eq": "1",
                                                             "year_eq": "1", "total_eq": "1", "data_time": t}})
    aioclient_mock.post(MICROS, json=MICRO_LIST)
    aioclient_mock.post(DTUS, json=DTU_LIST)
    aioclient_mock.post(MODULE, side_effect=module)


async def _hours(hass: HomeAssistant, day: date) -> dict[int, float]:
    start = dt_util.start_of_local_day(day)
    result = await hass.async_add_executor_job(
        statistics_during_period, hass, start, start + timedelta(days=1),
        {statistic_id(SID)}, "hour", None, {"sum", "change"},
    )
    return {
        dt_util.as_local(dt_util.utc_from_timestamp(r["start"])).hour: r["change"]
        for r in result.get(statistic_id(SID), [])
    }


async def test_history_then_late_data_lands_on_the_right_hour(
    recorder_mock, hass: HomeAssistant, aioclient_mock, monkeypatch
):
    monkeypatch.setattr("custom_components.solenso.statistics.BACKFILL_REQUEST_DELAY", 0)
    await hass.config.async_set_time_zone("Europe/Paris")
    today = dt_util.now().date()
    d1, d2 = today - timedelta(days=1), today - timedelta(days=2)
    # Hier, la DTU a décroché à 15 h : le cloud n'a que la matinée.
    by_date = {
        d2.isoformat(): _day_body([("12:00", 1000.0), ("14:00", 4000.0)]),
        d1.isoformat(): _day_body([("12:00", 2000.0), ("15:00", 6000.0)]),
    }
    _mock(aioclient_mock, by_date)
    entry = _entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    await async_wait_recording_done(hass)

    # Premier lancement : l'historique est repris, chaque énergie à son heure.
    assert (await _hours(hass, d2))[11] == 1000.0
    assert sum((await _hours(hass, d2)).values()) == 4000.0
    assert (await _hours(hass, d1))[11] == 2000.0 and (await _hours(hass, d1))[14] == 4000.0
    assert sum((await _hours(hass, d1)).values()) == 6000.0

    # Cette nuit, la DTU renvoie l'après-midi : 16 h à 18 h s'ajoutent à la veille.
    by_date[d1.isoformat()] = _day_body([("12:00", 2000.0), ("15:00", 6000.0), ("17:00", 8500.0), ("18:00", 9200.0)])
    _mock(aioclient_mock, by_date)
    coordinator = entry.runtime_data
    coordinator._previous_cache.clear()  # une heure a passé : la veille est relue
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)

    hours = await _hours(hass, d1)
    assert hours[16] == 2500.0 and hours[17] == 700.0  # à leur vraie heure, pas à l'heure du rattrapage
    assert sum(hours.values()) == 9200.0
    assert sum((await _hours(hass, d2)).values()) == 4000.0  # avant-veille intacte
