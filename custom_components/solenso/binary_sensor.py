"""Capteurs binaires Solenso : connexion des passerelles DTU."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .coordinator import SolensoConfigEntry, SolensoCoordinator
from .entity import dtu_device, link_only


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolensoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        DtuConnectivity(coordinator, sid, dtu)
        for sid, station in (coordinator.data or {}).items()
        for dtu in station.dtus.values()
    )


class DtuConnectivity(CoordinatorEntity[SolensoCoordinator], BinarySensorEntity):
    """La DTU communique-t-elle avec le cloud ?"""

    _attr_has_entity_name = True
    _attr_translation_key = "dtu_connected"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: SolensoCoordinator, sid: int, dtu: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._sid = sid
        self._dtu_id = dtu["id"]
        sn = dtu.get("sn") or str(dtu["id"])
        self._attr_unique_id = f"dtu_{sn}_connected"
        self._attr_device_info = link_only(dtu_device(sid, dtu))

    @property
    def _dtu(self) -> dict[str, Any] | None:
        station = (self.coordinator.data or {}).get(self._sid)
        return station.dtus.get(self._dtu_id) if station else None

    @property
    def available(self) -> bool:
        dtu = self._dtu
        return super().available and dtu is not None and "connect" in (dtu.get("warn_data") or {})

    @property
    def is_on(self) -> bool | None:
        dtu = self._dtu
        return None if dtu is None else bool((dtu.get("warn_data") or {}).get("connect"))
