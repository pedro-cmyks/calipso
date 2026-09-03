"""Registro durable de los VEREDICTOS de Pedro sobre las promesas de un
departamento: cuando un trabajo financiado llega a su plazo, Pedro marca si
cumplio o no. De esos veredictos sale el STANDING (cumplio N de M), que el
jefe ve en su prompt (aprende a prometer lo que puede cumplir) y Pedro ve en
la mesa (financia con el historial a la vista). Es el PvP: reputacion, no
plata.

Vive al lado de la carta y de las reacciones, en
memoria/departamento/<clave>/promesas.json. NO importa calipso.memory A
PROPOSITO (memory.py importa chromadb; jefe.py lo evita). Mismo molde que
reacciones.py; `_slug` identico a memory._slug.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re

from calipso.economia import candado


class ErrorPromesas(Exception):
    pass


def _home() -> pathlib.Path:
    return pathlib.Path(os.environ.get(
        "CALIPSO_HOME", os.path.expanduser("~/.calipso")))


def _slug(nombre: str) -> str:
    # identico a calipso.memory._slug: la carta, las reacciones y las
    # promesas caen en el MISMO directorio del departamento. memory._slug
    # recibe un pathlib.Path y hace str(path); replicar ese str(Path(...))
    # deja la equivalencia byte-a-byte para cualquier entrada, no solo los
    # nombres de un solo token.
    return re.sub(r"[^a-z0-9]+", "-",
                  str(pathlib.Path(nombre)).lower()).strip("-")[:80] or "root"


def _ruta(nombre: str) -> pathlib.Path:
    return _home() / "memoria" / "departamento" / _slug(nombre) / "promesas.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def leer(nombre: str) -> list[dict]:
    """Los veredictos del departamento, mas viejos primero. `[]` si no hay
    archivo. PRESENTE pero ilegible levanta (fallo cerrado): no se pierde un
    veredicto ni se reescribe con vacio."""
    ruta = _ruta(nombre)
    if not ruta.exists():
        return []
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ErrorPromesas(
            f"no se pueden leer las promesas ({ruta}): {exc}") from None
    if not isinstance(data, list):
        raise ErrorPromesas(f"promesas ilegibles: {ruta}")
    return data


def juzgada(nombre: str, propuesta_id: str) -> bool:
    """True si ese trabajo ya tiene veredicto (para no traerlo de nuevo a
    'por juzgar' ni juzgarlo dos veces)."""
    return any(v.get("propuesta_id") == propuesta_id for v in leer(nombre))


def anotar(nombre: str, propuesta_id: str, forma: dict | None,
           cumplio: bool, palabras: str) -> None:
    """Appendea un veredicto. Un trabajo se juzga UNA vez: si ya hay
    veredicto para `propuesta_id`, no se agrega otro (gana el primero).
    Escritura atomica."""
    data = leer(nombre)
    if any(v.get("propuesta_id") == propuesta_id for v in data):
        return
    data.append({"ts": _now(), "propuesta_id": propuesta_id,
                 "forma": forma or None, "cumplio": bool(cumplio),
                 "palabras": (palabras or "").strip()})
    candado.escribir_json_atomico(_ruta(nombre), data)


def standing(nombre: str) -> dict:
    """El historial de promesas del departamento: `{"cumplidas", "total"}`.
    Derivado de los veredictos."""
    vs = leer(nombre)
    return {"cumplidas": sum(1 for v in vs if v.get("cumplio")),
            "total": len(vs)}
