"""Mise à disposition de la carte Lovelace livrée avec l'intégration."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CARD_FILE = Path(__file__).parent / "solenso-card.js"
CARD_URL = "/solenso/solenso-card.js"
_DATA_KEY = "solenso_card_registered"


def _resources(hass: HomeAssistant) -> Any | None:
    """Collection des ressources Lovelace, si elle est gérée par l'interface (mode « stockage »)."""
    resources = getattr(hass.data.get("lovelace"), "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return None  # mode YAML : les ressources sont dans les fichiers, on n'y touche pas
    return resources


def _ours(item: dict[str, Any]) -> bool:
    return str(item.get("url", "")).split("?")[0] == CARD_URL


async def _async_set_resource(hass: HomeAssistant, url: str) -> bool:
    """Créer ou mettre à jour la ressource de la carte. Retourne False si impossible."""
    resources = _resources(hass)
    if resources is None:
        return False
    if not getattr(resources, "loaded", True):
        await resources.async_load()
        resources.loaded = True
    ours = [item for item in resources.async_items() if _ours(item)]
    if not ours:
        await resources.async_create_item({"res_type": "module", "url": url})
        return True
    first, *duplicates = ours
    if first.get("url") != url or first.get("type") != "module":
        await resources.async_update_item(first["id"], {"res_type": "module", "url": url})
    for item in duplicates:
        await resources.async_delete_item(item["id"])
    return True


async def async_register_card(hass: HomeAssistant, version: str) -> None:
    """Servir la carte et la faire charger par le tableau de bord (une seule fois par démarrage)."""
    if hass.data.get(_DATA_KEY) or hass.http is None:
        return
    try:
        from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL, add_extra_js_url  # noqa: PLC0415
        from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

        if DATA_EXTRA_MODULE_URL not in hass.data:
            # Interface web non chargée (tests, installation minimale) : rien à faire.
            return
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
        )
        # Version + empreinte du fichier : le navigateur recharge la carte dès qu'elle change.
        digest = await hass.async_add_executor_job(
            lambda: hashlib.sha256(CARD_FILE.read_bytes()).hexdigest()[:8]
        )
        url = f"{CARD_URL}?v={version}-{digest}"
        # Ressource Lovelace en priorité (méthode la plus fiable, celle de HACS) ;
        # sinon (tableaux de bord en YAML) chargement par l'interface web.
        if not await _async_set_resource(hass, url):
            add_extra_js_url(hass, url)
        hass.data[_DATA_KEY] = True
    except Exception:  # noqa: BLE001 - la carte ne doit jamais bloquer les capteurs
        _LOGGER.warning("Impossible de proposer la carte Solenso", exc_info=True)


async def async_unregister_card(hass: HomeAssistant) -> None:
    """Retirer la ressource quand l'intégration est supprimée."""
    resources = _resources(hass)
    if resources is None:
        return
    try:
        for item in list(resources.async_items()):
            if _ours(item):
                await resources.async_delete_item(item["id"])
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Ressource de la carte non retirée", exc_info=True)
