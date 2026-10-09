"""Descriptions d'appareils partagées par les plateformes."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo

from .const import DOMAIN, MANUFACTURER


def station_device(station: dict[str, Any]) -> DeviceInfo:
    sid = station["id"]
    return DeviceInfo(
        identifiers={(DOMAIN, str(sid))},
        name=station["name"],
        manufacturer=MANUFACTURER,
        model="Centrale photovoltaïque",
        configuration_url=f"https://monitor.solenso.net/platform/station/view/detail?id={sid}",
    )


def dtu_device(sid: int, dtu: dict[str, Any]) -> DeviceInfo:
    sn = dtu.get("sn") or str(dtu["id"])
    return DeviceInfo(
        identifiers={(DOMAIN, f"dtu_{sn}")},
        name=f"DTU {sn}",
        manufacturer=MANUFACTURER,
        model="DTU",
        serial_number=sn,
        sw_version=dtu.get("init_soft_ver") or None,
        hw_version=dtu.get("init_hard_ver") or None,
        via_device=(DOMAIN, str(sid)),
    )


def micro_device(sid: int, micro: dict[str, Any]) -> DeviceInfo:
    sn = micro.get("sn") or str(micro["id"])
    via = (DOMAIN, f"dtu_{micro['dtu_sn']}") if micro.get("dtu_sn") else (DOMAIN, str(sid))
    return DeviceInfo(
        identifiers={(DOMAIN, f"micro_{sn}")},
        name=f"Micro-onduleur {sn}",
        manufacturer=MANUFACTURER,
        model=micro.get("model_no") or micro.get("init_hard_no") or "Micro-onduleur",
        serial_number=sn,
        sw_version=micro.get("init_soft_ver") or None,
        hw_version=micro.get("init_hard_ver") or None,
        via_device=via,
    )
