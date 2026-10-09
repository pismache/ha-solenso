"""Client pour l'API cloud Solenso (monitor.solenso.net, plateforme Hoymiles en marque blanche).

Deux points d'entrée partagent le même jeton de session :
- la passerelle Solenso (monitor.solenso.net/platform/api/gateway), corps {"body": ...}
  et jeton en cookie : connexion, centrales, données temps réel ;
- l'API Hoymiles (neapi.hoymiles.com), corps JSON brut et jeton dans l'en-tête
  Authorization : appareils et données par micro-onduleur (réponse protobuf).
"""

from __future__ import annotations

import base64
import hashlib
import logging
from typing import Any

import aiohttp

from .const import BASE_URL, HOYMILES_URL
from .module_pb import MicroDay, ModuleDataDecodeError, decode_module_day_data

_LOGGER = logging.getLogger(__name__)

_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://monitor.solenso.net",
    "Referer": "https://monitor.solenso.net/platform/",
    "User-Agent": "Mozilla/5.0 (HomeAssistant solenso integration)",
}
_TIMEOUT = aiohttp.ClientTimeout(total=30)


class SolensoError(Exception):
    """Erreur générique de l'API."""


class SolensoConnectionError(SolensoError):
    """Le cloud est injoignable ou a renvoyé une réponse illisible."""


class SolensoAuthError(SolensoError):
    """Identifiants refusés."""


class _ApiStatusError(SolensoError):
    """Réponse JSON avec un statut d'erreur (souvent un jeton expiré)."""


def hash_password(password: str) -> str:
    """Hash utilisé par la page de connexion : md5hex(pw) + '.' + base64(sha256(pw))."""
    raw = password.encode()
    md5 = hashlib.md5(raw).hexdigest()  # noqa: S324 - imposé par le serveur
    sha = base64.b64encode(hashlib.sha256(raw).digest()).decode()
    return f"{md5}.{sha}"


def _is_ok(response: dict[str, Any]) -> bool:
    return str(response.get("status")) == "0"


class SolensoApi:
    """Accès au cloud Solenso / Hoymiles."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._token: str | None = None

    async def _request(
        self, url: str, payload: dict[str, Any], headers: dict[str, str], *, binary: bool = False
    ) -> dict[str, Any] | bytes:
        try:
            async with self._session.post(
                url, json=payload, headers=headers, timeout=_TIMEOUT
            ) as resp:
                if resp.status in (401, 403):
                    raise _ApiStatusError(f"HTTP {resp.status}")
                if resp.status >= 400:
                    raise SolensoConnectionError(f"HTTP {resp.status} sur {url}")
                raw = await resp.read()
                content_type = resp.headers.get("Content-Type", "")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise SolensoConnectionError(f"{url} : {err}") from err

        # Une erreur (jeton expiré...) revient en JSON même sur un appel binaire ; un
        # protobuf valide ne peut pas commencer par « { » (champ 15 de type 3).
        if binary and "json" not in content_type and not raw.lstrip().startswith(b"{"):
            return raw
        try:
            import json

            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as err:
            raise SolensoConnectionError(f"Réponse illisible sur {url}") from err
        if not isinstance(data, dict):
            raise SolensoConnectionError(f"Réponse inattendue sur {url}")
        if binary:
            # Une réponse JSON là où on attendait du binaire est une erreur.
            raise _ApiStatusError(f"{data.get('message')} (status {data.get('status')})")
        return data

    async def _gateway(self, path: str, body: dict[str, Any], *, auth: bool = True) -> dict[str, Any]:
        headers = dict(_HEADERS)
        if auth and self._token:
            headers["Cookie"] = f"solenso_token={self._token}"
            headers["token"] = self._token
        return await self._request(
            f"{BASE_URL}/{path}", {"body": body, "WAITING_PROMISE": True}, headers
        )

    async def _hoymiles(self, path: str, body: dict[str, Any], *, binary: bool = False):
        headers = dict(_HEADERS)
        if self._token:
            headers["Authorization"] = self._token
        result = await self._request(f"{HOYMILES_URL}/{path}", body, headers, binary=binary)
        if not binary and not _is_ok(result):
            raise _ApiStatusError(f"{result.get('message')} (status {result.get('status')})")
        return result

    async def login(self) -> None:
        """Se connecter et mémoriser le token."""
        res = await self._gateway(
            "iam/auth_login",
            {"user_name": self._username, "password": hash_password(self._password)},
            auth=False,
        )
        token = (res.get("data") or {}).get("token") if _is_ok(res) else None
        if not token:
            _LOGGER.debug("Connexion refusée : %s", res)
            raise SolensoAuthError(res.get("message") or "connexion refusée")
        self._token = token

    async def _with_relogin(self, call):
        """Exécuter un appel, en se reconnectant une fois si le jeton a expiré."""
        if not self._token:
            await self.login()
        try:
            return await call()
        except _ApiStatusError as err:
            _LOGGER.debug("Erreur %s, nouvelle connexion", err)
            await self.login()
            try:
                return await call()
            except _ApiStatusError as err2:
                raise SolensoError(str(err2)) from err2

    async def _gateway_authed(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        async def call():
            res = await self._gateway(path, body)
            if not _is_ok(res):
                raise _ApiStatusError(f"{path} : {res.get('message')} (status {res.get('status')})")
            return res

        return await self._with_relogin(call)

    # --- Centrale -----------------------------------------------------------

    async def get_stations(self) -> list[dict[str, Any]]:
        """Liste des centrales du compte : [{'id': int, 'name': str, ...}]."""
        res = await self._gateway_authed("pvm/station_select_by_page", {"page": 1, "page_size": 50})
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
        res = await self._gateway_authed("pvm-data/data_count_station_real_data", {"sid": sid})
        return res.get("data") or {}

    # --- Appareils (API Hoymiles) --------------------------------------------

    async def _hoymiles_list(self, path: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        res = await self._with_relogin(lambda: self._hoymiles(path, body))
        data = res.get("data") or {}
        items = data.get("list") if isinstance(data, dict) else data
        return [item for item in items or [] if isinstance(item, dict)]

    async def get_micros(self, sid: int) -> list[dict[str, Any]]:
        """Micro-onduleurs de la centrale (id, sn, modèle, versions, ports, dtu_id)."""
        return await self._hoymiles_list(
            "pvm/api/0/dev/micro/select_by_station",
            {"sid": sid, "page_size": 1000, "page_num": 1, "show_warn": 0},
        )

    async def get_dtus(self, sid: int) -> list[dict[str, Any]]:
        """Passerelles DTU de la centrale (id, sn, versions, état de connexion)."""
        return await self._hoymiles_list(
            "pvm/api/0/dev/dtu/select_by_station",
            {"sid": sid, "page_size": 100, "page_num": 1},
        )

    async def get_module_day_data(self, sid: int, date: str) -> dict[int, MicroDay]:
        """Mesures du jour par micro-onduleur ({id: MicroDay}), pas de 15 minutes."""
        raw = await self._with_relogin(
            lambda: self._hoymiles(
                "pvm-data/api/0/module/data/down_module_day_data",
                {"sid": sid, "date": date},
                binary=True,
            )
        )
        if not raw:
            return {}
        try:
            return decode_module_day_data(raw)
        except ModuleDataDecodeError as err:
            raise SolensoConnectionError(f"Données par onduleur illisibles : {err}") from err
