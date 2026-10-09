"""Capteurs Solenso."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN, MANUFACTURER, STALE_DATA_DELAY
from .coordinator import SolensoConfigEntry, SolensoCoordinator


def _float(data: dict[str, Any], key: str) -> float | None:
    try:
        return float(data[key])
    except (KeyError, TypeError, ValueError):
        return None


def _last_update(data: dict[str, Any]) -> datetime | None:
    """Horodatage de la dernière remontée (heure locale de la centrale)."""
    raw = data.get("last_data_time") or data.get("data_time")
    if not raw:
        return None
    parsed = dt_util.parse_datetime(str(raw))
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_util.get_default_time_zone())
    return parsed


def _power(data: dict[str, Any]) -> float | None:
    """Puissance instantanée, forcée à 0 quand la dernière remontée est trop ancienne."""
    last = _last_update(data)
    if last is not None and dt_util.now() - last > STALE_DATA_DELAY:
        return 0.0
    return _float(data, "real_power")


@dataclass(frozen=True, kw_only=True)
class SolensoSensorDescription(SensorEntityDescription):
    """Description d'un capteur Solenso."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[SolensoSensorDescription, ...] = (
    SolensoSensorDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_power,
    ),
    SolensoSensorDescription(
        key="energy_today",
        translation_key="energy_today",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value_fn=lambda d: _float(d, "today_eq"),
    ),
    SolensoSensorDescription(
        key="energy_month",
        translation_key="energy_month",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        value_fn=lambda d: _float(d, "month_eq"),
    ),
    SolensoSensorDescription(
        key="energy_year",
        translation_key="energy_year",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value_fn=lambda d: _float(d, "year_eq"),
    ),
    SolensoSensorDescription(
        key="energy_total",
        translation_key="energy_total",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=0,
        value_fn=lambda d: _float(d, "total_eq"),
    ),
    SolensoSensorDescription(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_last_update,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolensoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Créer les capteurs de chaque centrale."""
    coordinator = entry.runtime_data
    async_add_entities(
        SolensoSensor(coordinator, station, description)
        for station in coordinator.stations
        for description in SENSORS
    )


class SolensoSensor(CoordinatorEntity[SolensoCoordinator], SensorEntity):
    """Capteur d'une centrale Solenso."""

    _attr_has_entity_name = True
    entity_description: SolensoSensorDescription

    def __init__(
        self,
        coordinator: SolensoCoordinator,
        station: dict[str, Any],
        description: SolensoSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._sid: int = station["id"]
        self._attr_unique_id = f"{self._sid}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(self._sid))},
            name=station["name"],
            manufacturer=MANUFACTURER,
            model="Centrale photovoltaïque",
            configuration_url=f"https://monitor.solenso.net/platform/station/view/detail?id={self._sid}",
        )

    @property
    def _data(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get(self._sid)

    @property
    def available(self) -> bool:
        return super().available and self._data is not None

    @property
    def native_value(self) -> Any:
        data = self._data
        return None if data is None else self.entity_description.value_fn(data)
