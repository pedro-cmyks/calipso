"""Almacen local de ejemplos de la voz de Pedro: lo que el trae con /mia
(su version final editada de un borrador). Es su voz de verdad -- texto
escrito para una persona, no una orden a Calipso -- asi que el compositor
lo prioriza (ver voz.ejemplos_de_voz).

Local y del usuario: vive en CALIPSO_HOME, no sale de la maquina, no se
comparte entre proyectos. JSON plano, como chats.py.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib


def _archivo() -> pathlib.Path:
    # la ruta se resuelve en cada llamada (no al importar) para que los tests
    # puedan redirigir CALIPSO_HOME a un temp sin pelear con el orden de import.
    home = pathlib.Path(os.environ.get(
        "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
    return home / "voz_ejemplos.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def cargar() -> list[dict]:
    """La lista de ejemplos guardados. `[]` si no hay archivo o esta corrupto
    (el almacen no puede tumbar el chat por un JSON roto)."""
    ruta = _archivo()
    if not ruta.exists():
        return []
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def guardar(texto: str) -> None:
    """Appendea `texto` como ejemplo de la voz de Pedro. Un texto vacio no se
    guarda; un texto ya presente no se duplica (dedup por contenido)."""
    t = (texto or "").strip()
    if not t:
        return
    data = cargar()
    if any(e.get("texto") == t for e in data):
        return
    data.append({"texto": t, "ts": _now()})
    ruta = _archivo()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def texto_del_gesto(clean: str) -> str:
    """El texto a guardar de un mensaje /mia. Vacio si no hay nada real: el
    mensaje vacio, o el quirk de parse_directives que deja `clean` == "/mia"
    cuando el mensaje era solo el slash (el fallback `" ".join(keep) or
    message`)."""
    t = (clean or "").strip()
    if not t or t.lower() == "/mia":
        return ""
    return t
