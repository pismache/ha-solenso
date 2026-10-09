"""Capteurs Solenso : centrale et micro-onduleurs."""

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
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import STALE_DATA_DELAY
from .coordinator import MicroState, PortState, SolensoConfigEntry, SolensoCoordinator
from .entity import link_only, micro_device, station_device

# --- Centrale ----------------------------------------------------------------


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
    """Description d'un capteur de centrale."""

    value_fn: Callable[[dict[str, Any]], Any]


def _energy(key: str, translation_key: str, precision: int) -> SolensoSensorDescription:
    return SolensoSensorDescription(
        key=translation_key,
        translation_key=translation_key,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=precision,
        value_fn=lambda d: _float(d, key),
    )


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
    _energy("today_eq", "energy_today", 2),
    _energy("month_eq", "energy_month", 1),
    _energy("year_eq", "energy_year", 0),
    _energy("total_eq", "energy_total", 0),
    SolensoSensorDescription(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_last_update,
    ),
)

# --- Micro-onduleurs ---------------------------------------------------------


@dataclass(frozen=True, kw_only=True)
class MicroSensorDescription(SensorEntityDescription):
    """Description d'un capteur de micro-onduleur."""

    value_fn: Callable[[MicroState], Any]


@dataclass(frozen=True, kw_only=True)
class PortSensorDescription(SensorEntityDescription):
    """Description d'un capteur par entrée PV."""

    value_fn: Callable[[PortState], Any]


MICRO_SENSORS: tuple[MicroSensorDescription, ...] = (
    MicroSensorDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda m: m.power,
    ),
    MicroSensorDescription(
        key="energy_today",
        translation_key="energy_today",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        value_fn=lambda m: m.energy,
    ),
    MicroSensorDescription(
        key="temperature",
        translation_key="temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda m: m.temperature,
    ),
    MicroSensorDescription(
        key="grid_voltage",
        translation_key="grid_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda m: m.grid_voltage,
    ),
    MicroSensorDescription(
        key="grid_frequency",
        translation_key="grid_frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=2,
        value_fn=lambda m: m.grid_frequency,
    ),
    MicroSensorDescription(
        key="last_update",
        translation_key="last_update",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda m: m.last_update,
    ),
)

PORT_SENSORS: tuple[PortSensorDescription, ...] = (
    PortSensorDescription(
        key="pv_voltage",
        translation_key="pv_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda p: p.voltage,
    ),
    PortSensorDescription(
        key="pv_current",
        translation_key="pv_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda p: p.current,
    ),
)
# Avec plusieurs panneaux par onduleur, puissance et énergie sont aussi détaillées par entrée.
MULTI_PORT_SENSORS: tuple[PortSensorDescription, ...] = (
    PortSensorDescription(
        key="pv_power",
        translation_key="pv_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda p: p.power,
    ),
    PortSensorDescription(
        key="pv_energy",
        translation_key="pv_energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=3,
        value_fn=lambda p: p.energy,
    ),
)


def _ports(micro: dict[str, Any]) -> list[int]:
    ports = micro.get("port_array")
    if isinstance(ports, list) and ports:
        return [int(p) for p in ports]
    return [1]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolensoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Créer les capteurs de chaque centrale et de chaque micro-onduleur."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = []
    for station in coordinator.stations:
        sid = station["id"]
        entities.extend(SolensoSensor(coordinator, station, d) for d in SENSORS)
        for micro in coordinator.micros.get(sid, []):
            entities.extend(MicroSensor(coordinator, sid, micro, d) for d in MICRO_SENSORS)
            ports = _ports(micro)
            multi = len(ports) > 1
            for port in ports:
                for description in PORT_SENSORS + (MULTI_PORT_SENSORS if multi else ()):
                    entities.append(PortSensor(coordinator, sid, micro, port, description, multi))
    async_add_entities(entities)


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
        self._attr_device_info = station_device(station)

    @property
    def _data(self) -> dict[str, Any] | None:
        station = (self.coordinator.data or {}).get(self._sid)
        return station.real if station else None

    @property
    def available(self) -> bool:
        return super().available and self._data is not None

    @property
    def native_value(self) -> Any:
        data = self._data
        return None if data is None else self.entity_description.value_fn(data)


class _MicroEntity(CoordinatorEntity[SolensoCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: SolensoCoordinator, sid: int, micro: dict[str, Any]) -> None:
        super().__init__(coordinator)
        self._sid = sid
        self._micro_id: int = micro["id"]
        self._sn: str = micro.get("sn") or str(micro["id"])
        self._attr_device_info = link_only(micro_device(sid, micro))

    @property
    def _state(self) -> MicroState | None:
        station = (self.coordinator.data or {}).get(self._sid)
        return station.micros.get(self._micro_id) if station else None

    @property
    def available(self) -> bool:
        return super().available and self._state is not None


class MicroSensor(_MicroEntity):
    """Capteur global d'un micro-onduleur."""

    entity_description: MicroSensorDescription

    def __init__(self, coordinator, sid, micro, description: MicroSensorDescription) -> None:
        super().__init__(coordinator, sid, micro)
        self.entity_description = description
        self._attr_unique_id = f"micro_{self._sn}_{description.key}"

    @property
    def native_value(self) -> Any:
        state = self._state
        return None if state is None else self.entity_description.value_fn(state)


class PortSensor(_MicroEntity):
    """Capteur d'une entrée PV d'un micro-onduleur."""

    entity_description: PortSensorDescription

    def __init__(self, coordinator, sid, micro, port: int, description, multi: bool) -> None:
        super().__init__(coordinator, sid, micro)
        self.entity_description = description
        self._port = port
        self._attr_unique_id = f"micro_{self._sn}_{description.key}_{port}"
        if multi:
            self._attr_translation_key = f"{description.translation_key}_port"
            self._attr_translation_placeholders = {"port": str(port)}

    @property
    def native_value(self) -> Any:
        state = self._state
        if state is None:
            return None
        port = state.ports.get(self._port)
        if port is None:
            # Pas encore de mesure aujourd'hui : panneau à l'arrêt.
            return 0.0
        return self.entity_description.value_fn(port)
