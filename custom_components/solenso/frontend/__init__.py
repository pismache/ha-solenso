"""Mise à disposition de la carte Lovelace livrée avec l'intégration."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

CARD_FILE = Path(__file__).parent / "solenso-card.js"
CARD_URL = "/solenso/solenso-card.js"
_DATA_KEY = "solenso_card_registered"


async def async_register_card(hass: HomeAssistant, version: str) -> None:
    """Servir la carte et la charger automatiquement dans le tableau de bord (une seule fois)."""
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
        add_extra_js_url(hass, f"{CARD_URL}?v={version}-{digest}")
        hass.data[_DATA_KEY] = True
    except Exception:  # noqa: BLE001 - la carte ne doit jamais bloquer les capteurs
        _LOGGER.warning("Impossible de proposer la carte Solenso", exc_info=True)
