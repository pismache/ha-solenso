"""Décodage de la réponse protobuf de `down_module_day_data` (cloud Hoymiles).

Aucun schéma officiel n'est publié ; la structure ci-dessous a été relevée sur
une centrale de 16 micro-onduleurs Sol-H350 (Hoymiles HM-350 rebadgés) :

    ModuleDayData {
      1: int    sid
      2: string date              "2026-10-09"
      3: repeated Micro {
        1: int  micro id          (id de dev/micro/select_by_station)
        2: Day {
          2: repeated string time "08:30", "08:45"... (pas de 15 min)
          4: repeated Port {
            1: int port
            2: Series { 1: repeated Point { 1: f32 V, 2: f32 A, 3: f32 W, 4: f32 Wh du jour } }
          }
          5: packed f32  fréquence réseau (Hz)
          6: packed f32  température (°C)
          7: packed f32  tension réseau (V)
        }
      }
    }

Les valeurs nulles sont omises par l'encodeur protobuf : un champ absent vaut 0.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import struct


class ModuleDataDecodeError(ValueError):
    """Charge utile illisible."""


@dataclass
class Point:
    voltage: float = 0.0
    current: float = 0.0
    power: float = 0.0
    energy: float = 0.0


@dataclass
class MicroDay:
    micro_id: int
    times: list[str] = field(default_factory=list)
    ports: dict[int, list[Point]] = field(default_factory=dict)
    grid_frequency: list[float] = field(default_factory=list)
    temperature: list[float] = field(default_factory=list)
    grid_voltage: list[float] = field(default_factory=list)


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        if pos >= len(buf):
            raise ModuleDataDecodeError("varint tronqué")
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, pos
        shift += 7
        if shift > 63:
            raise ModuleDataDecodeError("varint trop long")


def _fields(buf: bytes):
    """Itère sur (numéro, type, valeur) ; valeur = int, bytes ou float selon le type."""
    pos = 0
    while pos < len(buf):
        key, pos = _varint(buf, pos)
        num, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _varint(buf, pos)
        elif wire == 1:
            if pos + 8 > len(buf):
                raise ModuleDataDecodeError("double tronqué")
            value = struct.unpack_from("<d", buf, pos)[0]
            pos += 8
        elif wire == 2:
            length, pos = _varint(buf, pos)
            if pos + length > len(buf):
                raise ModuleDataDecodeError("champ tronqué")
            value = buf[pos : pos + length]
            pos += length
        elif wire == 5:
            if pos + 4 > len(buf):
                raise ModuleDataDecodeError("float tronqué")
            value = struct.unpack_from("<f", buf, pos)[0]
            pos += 4
        else:
            raise ModuleDataDecodeError(f"type de champ {wire} non géré")
        yield num, wire, value


def _floats(wire: int, value) -> list[float]:
    """Flottants « packed » (type 2) ou isolés (type 5)."""
    if wire == 5:
        return [round(value, 3)]
    if wire == 2:
        if len(value) % 4:
            raise ModuleDataDecodeError("liste de flottants mal alignée")
        return [round(v, 3) for v in struct.unpack(f"<{len(value) // 4}f", value)]
    return []


def _point(buf: bytes) -> Point:
    point = Point()
    for num, wire, value in _fields(buf):
        if wire != 5:
            continue
        if num == 1:
            point.voltage = round(value, 2)
        elif num == 2:
            point.current = round(value, 3)
        elif num == 3:
            point.power = round(value, 2)
        elif num == 4:
            point.energy = round(value, 2)
    return point


def _port(buf: bytes) -> tuple[int, list[Point]]:
    port, points = 1, []
    for num, wire, value in _fields(buf):
        if num == 1 and wire == 0:
            port = value
        elif num == 2 and wire == 2:
            points.extend(_point(p) for n, w, p in _fields(value) if n == 1 and w == 2)
    return port, points


def _day(micro: MicroDay, buf: bytes) -> None:
    for num, wire, value in _fields(buf):
        if num == 2 and wire == 2:
            micro.times.append(value.decode("utf-8", "replace"))
        elif num == 4 and wire == 2:
            port, points = _port(value)
            micro.ports.setdefault(port, []).extend(points)
        elif num == 5:
            micro.grid_frequency.extend(_floats(wire, value))
        elif num == 6:
            micro.temperature.extend(_floats(wire, value))
        elif num == 7:
            micro.grid_voltage.extend(_floats(wire, value))


def decode_module_day_data(buf: bytes) -> dict[int, MicroDay]:
    """Décoder la réponse complète : {id micro-onduleur: MicroDay}."""
    micros: dict[int, MicroDay] = {}
    try:
        for num, wire, value in _fields(buf):
            if num != 3 or wire != 2:
                continue
            micro_id, day = None, None
            for n, w, v in _fields(value):
                if n == 1 and w == 0:
                    micro_id = v
                elif n == 2 and w == 2:
                    day = v
            if micro_id is None:
                continue
            micro = micros.setdefault(micro_id, MicroDay(micro_id))
            if day is not None:
                _day(micro, day)
    except (struct.error, UnicodeDecodeError, IndexError) as err:
        raise ModuleDataDecodeError(str(err)) from err
    return micros
