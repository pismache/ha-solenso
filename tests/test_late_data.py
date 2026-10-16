"""Données en retard : DTU qui décroche en journée, puis renvoie ses mesures en différé."""

from datetime import datetime, timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMockResponse
import pytest

from custom_components.solenso.coordinator import is_daylight as real_is_daylight

from .test_micros import (
    DTU_LIST,
    DTUS,
    LAYOUT,
    LOGIN,
    MICRO_LIST,
    MICROS,
    MODULE,
    REAL,
    _entry,
    encode_day,
    encode_micro,
    slots,
)

POWER = "sensor.maison_power"
MICRO_POWER = "sensor.micro_onduleur_112100000001_power"
MICRO_ENERGY = "sensor.micro_onduleur_112100000001_energy_today"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _real(today_wh: float, minutes_ago: int) -> dict:
    t = (dt_util.now() - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%d %H:%M:%S")
    return {"status": "0", "data": {"real_power": "2522.3", "today_eq": str(today_wh), "month_eq": "1",
                                    "year_eq": "1", "total_eq": "1", "data_time": t}}


def _day(times: list[str], wh_101: float, wh_102: float) -> bytes:
    return encode_day(
        encode_micro(101, times, {1: [(31.0, 5.0, 150.0, wh_101)]}, [20.0], [230.0], [50.0]),
        encode_micro(102, times, {1: [(31.0, 5.0, 150.0, wh_102)]}, [20.0], [230.0], [50.0]),
    )


async def _setup(hass, aioclient_mock, real: dict, by_date: dict[str, bytes]):
    async def module(method, url, data):
        body = by_date.get(data["date"], b"")
        return AiohttpClientMockResponse(
            method, url, response=body, headers={"Content-Type": "application/octet-stream"}
        )

    aioclient_mock.post(LOGIN, json={"status": "0", "data": {"token": "tok"}})
    aioclient_mock.post(LAYOUT, json={"status": "0", "data": []})
    aioclient_mock.post(REAL, json=real)
    aioclient_mock.post(MICROS, json=MICRO_LIST)
    aioclient_mock.post(DTUS, json=DTU_LIST)
    aioclient_mock.post(MODULE, side_effect=module)
    entry = _entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_frozen_data_in_daylight_is_unavailable_not_zero(
    hass: HomeAssistant, aioclient_mock, daylight
):
    # Dernière remontée il y a 2 h alors que le soleil est haut : la DTU a décroché.
    today = dt_util.now().date().isoformat()
    await _setup(hass, aioclient_mock, _real(10_736, 120), {today: _day(slots(4, 120), 677.0, 650.0)})
    assert hass.states.get(POWER).state == "unavailable"
    assert hass.states.get(MICRO_POWER).state == "unavailable"
    assert hass.states.get("sensor.micro_onduleur_112100000001_pv_voltage").state == "unavailable"
    # Les énergies restent lisibles : elles sont acquises.
    assert float(hass.states.get(MICRO_ENERGY).state) == 0.677
    assert float(hass.states.get("sensor.maison_energy_today").state) == 10.736


async def test_frozen_data_at_night_reads_zero(hass: HomeAssistant, aioclient_mock):
    today = dt_util.now().date().isoformat()
    await _setup(hass, aioclient_mock, _real(10_736, 120), {today: _day(slots(4, 120), 677.0, 650.0)})
    assert float(hass.states.get(POWER).state) == 0
    assert float(hass.states.get(MICRO_POWER).state) == 0


async def test_fresh_data_in_daylight_is_shown(hass: HomeAssistant, aioclient_mock, daylight):
    today = dt_util.now().date().isoformat()
    await _setup(hass, aioclient_mock, _real(2000, 3), {today: _day(slots(4, 5), 1000.0, 1000.0)})
    assert float(hass.states.get(POWER).state) == 2522.3
    assert float(hass.states.get(MICRO_POWER).state) == 150.0


async def test_yesterday_is_read_at_most_once_an_hour(hass: HomeAssistant, aioclient_mock):
    now = dt_util.now()
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    entry = await _setup(
        hass, aioclient_mock, _real(200, 3),
        {now.date().isoformat(): _day(slots(2, 5), 100.0, 100.0), yesterday: _day(["18:00"], 1.0, 1.0)},
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    dates = [c[2]["date"] for c in aioclient_mock.mock_calls if str(c[1]) == MODULE]
    assert dates.count(yesterday) == 1
    assert dates.count(now.date().isoformat()) == 2



async def test_daylight_follows_the_sun(hass: HomeAssistant):
    # Fonction importée au chargement du module : c'est la vraie, pas celle simulée par conftest.
    hass.config.latitude, hass.config.longitude = 47.98, -1.03  # Mayenne
    await hass.config.async_set_time_zone("Europe/Paris")
    tz = dt_util.get_default_time_zone()
    assert real_is_daylight(hass, datetime(2026, 10, 15, 14, 0, tzinfo=tz))
    assert not real_is_daylight(hass, datetime(2026, 10, 15, 23, 0, tzinfo=tz))
    assert not real_is_daylight(hass, datetime(2026, 10, 15, 8, 30, tzinfo=tz))  # soleil encore trop bas
