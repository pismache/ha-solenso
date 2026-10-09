"""La carte Lovelace est servie et chargée automatiquement."""

from unittest.mock import AsyncMock, MagicMock
import uuid

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL

from custom_components.solenso.frontend import (
    CARD_FILE,
    CARD_URL,
    async_register_card,
    async_unregister_card,
)


class FakeResources:
    """Imite la collection de ressources Lovelace en mode « stockage »."""

    def __init__(self, items=None):
        self.items = {i["id"]: i for i in items or []}
        self.loaded = False

    async def async_load(self):
        self.loaded = True

    def async_items(self):
        return list(self.items.values())

    async def async_create_item(self, data):
        item = {"id": uuid.uuid4().hex, "url": data["url"], "type": data["res_type"]}
        self.items[item["id"]] = item
        return item

    async def async_update_item(self, item_id, updates):
        self.items[item_id] = {**self.items[item_id], "url": updates["url"], "type": updates["res_type"]}

    async def async_delete_item(self, item_id):
        del self.items[item_id]


def _frontend(hass, resources=None):
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    urls = set()
    hass.data[DATA_EXTRA_MODULE_URL] = MagicMock(add=urls.add)
    hass.data.pop("solenso_card_registered", None)
    if resources is not None:
        hass.data["lovelace"] = MagicMock(resources=resources)
    else:
        hass.data.pop("lovelace", None)
    return urls


async def test_resource_created_once(hass):
    resources = FakeResources()
    urls = _frontend(hass, resources)
    await async_register_card(hass, "0.4.2")
    await async_register_card(hass, "0.4.2")
    items = resources.async_items()
    assert len(items) == 1 and items[0]["type"] == "module"
    assert items[0]["url"].startswith(f"{CARD_URL}?v=0.4.2-")
    assert urls == set()  # pas de double chargement
    config = hass.http.async_register_static_paths.call_args.args[0][0]
    assert config.url_path == CARD_URL and config.path == str(CARD_FILE)
    assert CARD_FILE.is_file()


async def test_manual_resource_is_reused_and_duplicates_removed(hass):
    resources = FakeResources(
        [
            {"id": "a", "url": "/solenso/solenso-card.js", "type": "module"},
            {"id": "b", "url": "/solenso/solenso-card.js?v=old", "type": "module"},
            {"id": "c", "url": "/hacsfiles/autre-carte.js", "type": "module"},
        ]
    )
    _frontend(hass, resources)
    await async_register_card(hass, "0.4.2")
    urls = sorted(i["url"] for i in resources.async_items())
    assert len(urls) == 2
    assert urls[0] == "/hacsfiles/autre-carte.js"
    assert urls[1].startswith(f"{CARD_URL}?v=0.4.2-")


async def test_yaml_mode_falls_back_to_extra_js(hass):
    urls = _frontend(hass, resources=None)
    await async_register_card(hass, "0.4.2")
    assert len(urls) == 1 and urls.pop().startswith(f"{CARD_URL}?v=0.4.2-")


async def test_card_skipped_without_frontend(hass):
    hass.http = MagicMock(async_register_static_paths=AsyncMock())
    hass.data.pop(DATA_EXTRA_MODULE_URL, None)
    hass.data.pop("solenso_card_registered", None)
    await async_register_card(hass, "0.4.2")
    hass.http.async_register_static_paths.assert_not_awaited()


async def test_unregister_removes_only_our_resource(hass):
    resources = FakeResources(
        [
            {"id": "a", "url": "/solenso/solenso-card.js?v=1", "type": "module"},
            {"id": "c", "url": "/hacsfiles/autre-carte.js", "type": "module"},
        ]
    )
    hass.data["lovelace"] = MagicMock(resources=resources)
    await async_unregister_card(hass)
    assert [i["id"] for i in resources.async_items()] == ["c"]


async def test_card_available_even_when_cloud_is_down(hass, aioclient_mock, enable_custom_integrations):
    """La carte doit être déclarée même si Solenso ne répond pas au démarrage."""
    from homeassistant.config_entries import ConfigEntryState
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.solenso.const import BASE_URL, CONF_STATIONS, DOMAIN

    resources = FakeResources()
    _frontend(hass, resources)
    aioclient_mock.post(f"{BASE_URL}/iam/auth_login", status=503)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"username": "a@b.fr", "password": "x", CONF_STATIONS: [{"id": 1, "name": "Maison"}]},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert len(resources.async_items()) == 1

    # Suppression du compte : la ressource part avec.
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert resources.async_items() == []
