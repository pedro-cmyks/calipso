"""Registro durable de las reacciones de Pedro a las propuestas de un
departamento: lo que descarto, lo que veto ("no mas") y lo que financio, con
SUS palabras. El jefe lo lee en cada decision y aprende (un modelo sin
memoria propia "aprende" teniendo el registro delante). El "no mas" ademas
arma un piso determinista: `esta_vetada`.

Vive al lado de la carta, en memoria/departamento/<clave>/reacciones.json.
NO importa calipso.memory A PROPOSITO: memory.py importa chromadb en el tope
(memory.py:36) y jefe.py -que lee este registro- se cuida de no arrastrar eso
(jefe.py:38). Por eso el layout se replica aca; `_slug` tiene que quedar
IDENTICO a memory._slug.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re

from calipso.economia import candado


class ErrorReacciones(Exception):
    pass


REACCIONES = ("descarto", "no_mas", "financio")


def _home() -> pathlib.Path:
    return pathlib.Path(os.environ.get(
        "CALIPSO_HOME", os.path.expanduser("~/.calipso")))


def _slug(nombre: str) -> str:
    # identico a calipso.memory._slug: la carta y las reacciones tienen que
    # caer en el MISMO directorio del departamento. memory._slug recibe un
    # pathlib.Path y hace str(path); replicar ese str(Path(...)) deja la
    # equivalencia byte-a-byte para cualquier entrada, no solo los nombres
    # de un solo token.
    return re.sub(r"[^a-z0-9]+", "-",
                  str(pathlib.Path(nombre)).lower()).strip("-")[:80] or "root"


def _ruta(nombre: str) -> pathlib.Path:
    return _home() / "memoria" / "departamento" / _slug(nombre) / "reacciones.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def leer(nombre: str) -> list[dict]:
    """Las reacciones del departamento, mas viejas primero. `[]` si no hay
    archivo. Un archivo PRESENTE pero ilegible NO es lista vacia: levanta,
    para no perder un "no mas" ni reescribirlo con vacio (espeja
    permisos._leer_solicitudes, no config())."""
    ruta = _ruta(nombre)
    if not ruta.exists():
        return []
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ErrorReacciones(
            f"no se pueden leer las reacciones ({ruta}): {exc}") from None
    if not isinstance(data, list):
        raise ErrorReacciones(f"reacciones ilegibles: {ruta}")
    return data


def anotar(nombre: str, reaccion: str, forma: dict | None,
           palabras: str, propuesta_id: str) -> None:
    """Appendea una reaccion al registro del departamento. Escritura
    atomica (nunca write_text pelado). Si el archivo esta corrupto, `leer`
    levanta y no se anota (no se lo lleva por delante)."""
    if reaccion not in REACCIONES:
        raise ErrorReacciones(f"reaccion desconocida: {reaccion}")
    data = leer(nombre)
    data.append({"ts": _now(), "reaccion": reaccion,
                 "forma": forma or None,
                 "palabras": (palabras or "").strip(),
                 "propuesta_id": propuesta_id})
    candado.escribir_json_atomico(_ruta(nombre), data)


def esta_vetada(reacciones: list, clave: str) -> bool:
    """El piso del "no mas": True si alguna reaccion es un `no_mas` sobre esa
    `clave`. PURA -- opera sobre una lista ya leida para que el jefe no relea
    disco. Ignora `promete`/`tarda`: la identidad es la `clave`."""
    return any(r.get("reaccion") == "no_mas"
               and (r.get("forma") or {}).get("clave") == clave
               for r in reacciones)
