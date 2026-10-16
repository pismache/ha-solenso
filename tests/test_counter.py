"""Compteur de production cumulée destiné au tableau Énergie."""

from datetime import date, datetime, timedelta

from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)
import pytest

from custom_components.solenso.const import BASE_URL, CONF_STATIONS, DOMAIN, HOYMILES_URL
from custom_components.solenso.sensor import Counter, accumulate, catch_up

LOGIN = f"{BASE_URL}/iam/auth_login"
REAL = f"{BASE_URL}/pvm-data/data_count_station_real_data"
ENTITY = "sensor.maison_energy_produced"
EMPTY = {"status": "0", "data": {"list": []}}

D1, D2 = date(2026, 10, 9), date(2026, 10, 10)


# --- Règle de calcul ----------------------------------------------------------


def test_first_reading_is_the_baseline():
    assert accumulate(Counter(), 1200.0, D1) == Counter(1200.0, 1200.0, D1)


def test_rises_during_the_day_are_added():
    c = Counter(10_000.0, 1200.0, D1)
    c = accumulate(c, 1500.0, D1)
    c = accumulate(c, 2500.0, D1)
    assert c == Counter(11_300.0, 2500.0, D1)


def test_drop_or_repeat_adds_nothing_then_resumes_above_the_old_max():
    c = Counter(10_000.0, 2500.0, D1)
    c = accumulate(c, 2490.0, D1)  # correction du cloud
    c = accumulate(c, 2490.0, D1)
    assert c.total == 10_000.0
    c = accumulate(c, 2600.0, D1)
    assert c.total == 10_100.0


def test_new_day_counts_from_zero():
    c = Counter(10_000.0, 5210.0, D1)
    c = accumulate(c, 0.0, D1)  # remise à zéro à minuit, encore datée de la veille
    assert c.total == 10_000.0
    c = accumulate(c, 40.0, D2)
    assert c == Counter(10_040.0, 40.0, D2, D1, 5210.0)


def test_new_day_with_yesterday_value_not_reset_is_ignored():
    c = Counter(10_000.0, 5210.0, D1)
    c = accumulate(c, 5210.0, D2)
    assert c.total == 10_000.0
    c = accumulate(c, 35.0, D2)
    assert c == Counter(10_035.0, 35.0, D2, D1, 5210.0)


def test_missing_or_older_data_changes_nothing():
    c = Counter(10_000.0, 500.0, D2)
    assert accumulate(c, None, D2) == c
    assert accumulate(c, 800.0, None) == c
    assert accumulate(c, 9_000.0, D1) == c
    assert accumulate(c, -5.0, D2) == c


def test_late_data_for_yesterday_is_caught_up_once():
    # La DTU a décroché à 15 h : la veille s'arrête à 10 736 Wh, puis le reste arrive en différé.
    c = accumulate(Counter(50_000.0, 10_736.0, D1), 200.0, D2)
    assert c == Counter(50_200.0, 200.0, D2, D1, 10_736.0)
    c = catch_up(c, D1, 15_100.0)
    assert c == Counter(54_564.0, 200.0, D2, D1, 15_100.0)
    # Relue une heure plus tard, la veille n'est plus comptée une deuxième fois.
    assert catch_up(c, D1, 15_100.0) == c
    # Le jour courant continue normalement.
    assert accumulate(c, 900.0, D2).total == 55_264.0


def test_late_data_before_the_new_day_starts():
    # Cette nuit, avant la première remontée du jour : la journée courante est encore la veille.
    c = Counter(50_000.0, 10_736.0, D1)
    c = catch_up(c, D1, 15_100.0)
    assert c == Counter(54_364.0, 15_100.0, D1)
    # Le matin, la valeur figée de la veille ne fait rien perdre ni compter en double.
    c = accumulate(c, 10_736.0, D1)
    assert c.total == 54_364.0
    c = accumulate(c, 150.0, D2)
    assert c == Counter(54_514.0, 150.0, D2, D1, 15_100.0)


def test_catch_up_ignores_rounding_and_unknown_days():
    c = Counter(50_000.0, 3671.0, D2, D1, 10_736.0)
    assert catch_up(c, D2, 3675.0) == c  # simple arrondi entre sources
    assert catch_up(c, D1, 10_740.0) == c
    assert catch_up(c, date(2026, 10, 1), 99_000.0) == c  # jour trop ancien
    assert catch_up(Counter(), D1, 5000.0) == Counter()


def test_micro_energy_ahead_of_station_total_is_counted():
    c = Counter(50_000.0, 3000.0, D2, D1, 10_736.0)
    c = catch_up(c, D2, 3400.0)
    assert c == Counter(50_400.0, 3400.0, D2, D1, 10_736.0)
    # La centrale rattrape ensuite : rien de compté en double.
    assert accumulate(c, 3400.0, D2) == c
    assert accumulate(c, 3500.0, D2).total == 50_500.0


# --- Capteur dans Home Assistant ---------------------------------------------


def real(today_wh: float, when: datetime) -> dict:
    t = when.strftime("%Y-%m-%d %H:%M:%S")
    return {
        "status": "0",
        "data": {
            "real_power": "300",
            "today_eq": str(today_wh),
            "month_eq": "100000",
            "year_eq": "5000000",
            "total_eq": "22000000",
            "data_time": t,
            "last_data_time": t,
        },
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


def _entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="a@b.fr",
        title="Maison",
        data={"username": "a@b.fr", "password": "x", CONF_STATIONS: [{"id": 1234567, "name": "Maison"}]},
    )


def _mock_cloud(aioclient_mock, payload):
    aioclient_mock.clear_requests()
    aioclient_mock.post(LOGIN, json={"status": "0", "data": {"token": "tok"}})
    aioclient_mock.post(REAL, json=payload)
    aioclient_mock.post(f"{HOYMILES_URL}/pvm/api/0/dev/micro/select_by_station", json=EMPTY)
    aioclient_mock.post(f"{HOYMILES_URL}/pvm/api/0/dev/dtu/select_by_station", json=EMPTY)
    aioclient_mock.post(f"{BASE_URL}/pvm/layout_select_all", json={"status": "0", "data": []})


async def _setup(hass, aioclient_mock, payload) -> MockConfigEntry:
    _mock_cloud(aioclient_mock, payload)
    entry = _entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _refresh(hass, aioclient_mock, entry, payload) -> float:
    _mock_cloud(aioclient_mock, payload)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    return float(hass.states.get(ENTITY).state)


async def test_counter_follows_the_day_and_crosses_midnight(hass: HomeAssistant, aioclient_mock):
    now = dt_util.now().replace(hour=11, minute=0, second=0, microsecond=0)
    entry = await _setup(hass, aioclient_mock, real(2000, now))
    state = hass.states.get(ENTITY)
    assert state.attributes["state_class"] == "total_increasing"
    assert state.attributes["unit_of_measurement"] == "kWh"
    assert float(state.state) == 2.0

    assert await _refresh(hass, aioclient_mock, entry, real(3500, now + timedelta(hours=1))) == 3.5
    # Le cloud remet le jour à zéro : le compteur ne bouge pas.
    assert await _refresh(hass, aioclient_mock, entry, real(0, now + timedelta(hours=2))) == 3.5
    # Lendemain matin : seule la nouvelle production s'ajoute.
    tomorrow = now + timedelta(days=1)
    assert await _refresh(hass, aioclient_mock, entry, real(250, tomorrow)) == 3.75


async def test_counter_keeps_its_value_when_cloud_is_down(hass: HomeAssistant, aioclient_mock):
    now = dt_util.now().replace(hour=11, minute=0, second=0, microsecond=0)
    entry = await _setup(hass, aioclient_mock, real(2000, now))
    aioclient_mock.clear_requests()
    aioclient_mock.post(REAL, status=500)
    aioclient_mock.post(LOGIN, status=500)
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY).state == "2.0"


async def test_counter_resumes_after_restart(hass: HomeAssistant, aioclient_mock):
    now = dt_util.now().replace(hour=15, minute=0, second=0, microsecond=0)
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(ENTITY, "123.0"),
                {"total": 123_000.0, "last_today": 1000.0, "last_day": now.date().isoformat()},
            )
        ],
    )
    # Pendant l'arrêt, la production du jour est passée de 1 000 à 4 000 Wh : rattrapée.
    await _setup(hass, aioclient_mock, real(4000, now))
    assert float(hass.states.get(ENTITY).state) == 126.0


async def test_counter_restores_yesterday_for_catch_up(hass: HomeAssistant, aioclient_mock):
    now = dt_util.now().replace(hour=15, minute=0, second=0, microsecond=0)
    yesterday = (now - timedelta(days=1)).date().isoformat()
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(ENTITY, "123.0"),
                {"total": 123_000.0, "last_today": 1000.0, "last_day": now.date().isoformat(),
                 "prev_day": yesterday, "prev_max": 10_736.0},
            )
        ],
    )
    entry = await _setup(hass, aioclient_mock, real(1000, now))
    counter = next(
        e for e in hass.data["sensor"].entities if e.entity_id == ENTITY
    )._counter
    assert counter.prev_day.isoformat() == yesterday and counter.prev_max == 10_736.0
    assert entry.runtime_data is not None
