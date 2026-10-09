"""Configuration de l'intégration Solenso par l'interface."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SolensoApi, SolensoAuthError, SolensoConnectionError, SolensoError
from .const import CONF_SID, CONF_STATIONS, DOMAIN

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_SID): vol.Coerce(int),
    }
)
REAUTH_SCHEMA = vol.Schema({vol.Required(CONF_PASSWORD): str})


class SolensoConfigFlow(ConfigFlow, domain=DOMAIN):
    """Flux de configuration Solenso."""

    VERSION = 1

    async def _discover(self, api: SolensoApi, sid: int | None) -> list[dict[str, Any]]:
        """Trouver les centrales du compte, en retombant sur l'identifiant saisi si besoin."""
        await api.login()
        stations: list[dict[str, Any]] = []
        try:
            stations = await api.get_stations()
        except SolensoAuthError:
            raise
        except SolensoError as err:
            _LOGGER.debug("Liste des centrales indisponible : %s", err)
        if sid is not None:
            known = {s["id"]: s for s in stations}
            stations = [known.get(sid, {"id": sid, "name": f"Centrale {sid}"})]
        for station in stations:
            # Vérifie que les données sont lisibles pour chaque centrale retenue.
            await api.get_station_real_data(station["id"])
        return [{"id": s["id"], "name": s["name"]} for s in stations]

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            await self.async_set_unique_id(username.lower())
            self._abort_if_unique_id_configured()
            api = SolensoApi(
                async_get_clientsession(self.hass), username, user_input[CONF_PASSWORD]
            )
            try:
                stations = await self._discover(api, user_input.get(CONF_SID))
            except SolensoAuthError:
                errors["base"] = "invalid_auth"
            except SolensoConnectionError:
                errors["base"] = "cannot_connect"
            except SolensoError:
                errors["base"] = "station_not_found"
            except Exception:
                _LOGGER.exception("Erreur inattendue")
                errors["base"] = "unknown"
            else:
                if not stations:
                    errors["base"] = "no_station"
                else:
                    title = stations[0]["name"] if len(stations) == 1 else f"Solenso ({username})"
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_USERNAME: username,
                            CONF_PASSWORD: user_input[CONF_PASSWORD],
                            CONF_STATIONS: stations,
                        },
                    )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(USER_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            api = SolensoApi(
                async_get_clientsession(self.hass),
                entry.data[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await api.login()
            except SolensoAuthError:
                errors["base"] = "invalid_auth"
            except SolensoConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_PASSWORD: user_input[CONF_PASSWORD]}
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            description_placeholders={"username": entry.data[CONF_USERNAME]},
            errors=errors,
        )
