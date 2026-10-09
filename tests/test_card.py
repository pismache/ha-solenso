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
