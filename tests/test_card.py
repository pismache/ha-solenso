"""La carte Lovelace est servie et chargée automatiquement."""

from unittest.mock import AsyncMock, MagicMock

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL

from custom_components.solenso.frontend import CARD_FILE, CARD_URL, async_register_card


async def test_card_registered_once(hass):
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    urls = set()
    hass.data[DATA_EXTRA_MODULE_URL] = MagicMock(add=urls.add)
    await async_register_card(hass, "0.3.0")
    await async_register_card(hass, "0.3.0")
    assert len(urls) == 1
    url = urls.pop()
    assert url.startswith(f"{CARD_URL}?v=0.3.0-") and len(url.rsplit("-", 1)[1]) == 8
    hass.http.async_register_static_paths.assert_awaited_once()
    config = hass.http.async_register_static_paths.call_args.args[0][0]
    assert config.url_path == CARD_URL and config.path == str(CARD_FILE)
    assert CARD_FILE.is_file()


async def test_card_skipped_without_frontend(hass):
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    hass.data.pop(DATA_EXTRA_MODULE_URL, None)
    await async_register_card(hass, "0.3.0")
    hass.http.async_register_static_paths.assert_not_awaited()


async def test_card_available_even_when_cloud_is_down(hass, aioclient_mock, enable_custom_integrations):
    """La carte doit être déclarée même si Solenso ne répond pas au démarrage."""
    from homeassistant.config_entries import ConfigEntryState
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.solenso.const import BASE_URL, CONF_STATIONS, DOMAIN

    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    urls = set()
    hass.data[DATA_EXTRA_MODULE_URL] = MagicMock(add=urls.add)
    aioclient_mock.post(f"{BASE_URL}/iam/auth_login", status=503)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "a@b.fr", "password": "x", CONF_STATIONS: [{"id": 1, "name": "Maison"}]},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert any(u.startswith(CARD_URL) for u in urls)
