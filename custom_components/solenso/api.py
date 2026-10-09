"""Client pour l'API cloud Solenso (monitor.solenso.net, plateforme Hoymiles en marque blanche)."""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

import aiohttp

from .const import BASE_URL

_LOGGER = logging.getLogger(__name__)

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json;charset=UTF-8",
    "Origin": "https://monitor.solenso.net",
    "Referer": "https://monitor.solenso.net/platform/",
    "User-Agent": "Mozilla/5.0 (HomeAssistant solenso integration)",
}


class SolensoError(Exception):
    """Erreur générique de l'API."""


class SolensoConnectionError(SolensoError):
    """Le cloud est injoignable ou a renvoyé une réponse illisible."""


class SolensoAuthError(SolensoError):
    """Identifiants refusés."""


def hash_password(password: str) -> str:
    """Hash utilisé par la page de connexion : md5hex(pw) + '.' + base64(sha256(pw))."""
    raw = password.encode()
    md5 = hashlib.md5(raw).hexdigest()  # noqa: S324 - imposé par le serveur
    sha = base64.b64encode(hashlib.sha256(raw).digest()).decode()
    return f"{md5}.{sha}"


def _is_ok(response: dict[str, Any]) -> bool:
    return str(response.get("status")) == "0"


class SolensoApi:
    """Accès au cloud Solenso."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None

    async def _post(self, path: str, body: dict[str, Any], *, auth: bool = True) -> dict[str, Any]:
        headers = dict(_HEADERS)
        if auth and self._token:
            # La page web envoie le token en cookie ; d'autres clients Hoymiles
            # l'envoient en en-tête. On fait les deux.
            headers["Cookie"] = f"solenso_token={self._token}"
            headers["token"] = self._token
        try:
            async with self._session.post(
                f"{BASE_URL}/{path}",
                json={"body": body, "WAITING_PROMISE": True},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status >= 400:
                    raise SolensoConnectionError(f"HTTP {resp.status} sur {path}")
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise SolensoConnectionError(f"{path} : {err}") from err
        except ValueError as err:
            raise SolensoConnectionError(f"Réponse illisible sur {path}") from err
        if not isinstance(data, dict):
            raise SolensoConnectionError(f"Réponse inattendue sur {path}")
        return data

    async def login(self) -> None:
        """Se connecter et mémoriser le token."""
        res = await self._post(
            "iam/auth_login",
            {"user_name": self._username, "password": hash_password(self._password)},
            auth=False,
        )
        token = (res.get("data") or {}).get("token") if _is_ok(res) else None
        if not token:
            _LOGGER.debug("Connexion refusée : %s", res)
            raise SolensoAuthError(res.get("message") or "connexion refusée")
        self._token = token

    async def _authed(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        """Appel authentifié, avec une reconnexion si le token a expiré."""
        if not self._token:
            await self.login()
        res = await self._post(path, body)
        if not _is_ok(res):
            _LOGGER.debug("Réponse %s sur %s, nouvelle connexion", res.get("status"), path)
            await self.login()
            res = await self._post(path, body)
        if not _is_ok(res):
            raise SolensoError(f"{path} : {res.get('message')} (status {res.get('status')})")
        return res

    async def get_stations(self) -> list[dict[str, Any]]:
        """Liste des centrales du compte : [{'id': int, 'name': str, ...}]."""
        res = await self._authed("pvm/station_select_by_page", {"page": 1, "page_size": 50})
        data = res.get("data") or {}
        items = data.get("list") if isinstance(data, dict) else data
        stations = []
        for item in items or []:
            sid = item.get("id") or item.get("sid")
            if sid is None:
                continue
            stations.append({**item, "id": int(sid), "name": item.get("name") or f"Centrale {sid}"})
        return stations

    async def get_station_real_data(self, sid: int) -> dict[str, Any]:
        """Données temps réel d'une centrale (puissance en W, énergies en Wh)."""
        res = await self._authed("pvm-data/data_count_station_real_data", {"sid": sid})
        return res.get("data") or {}
