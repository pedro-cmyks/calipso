#!/usr/bin/env python3
"""
calipso/chronology.py - cronologia personal curada de Pedro.

La cronologia no reemplaza el perfil. El perfil explica rasgos duraderos; la
cronologia conserva cambios fechados, estado actual e historia de proyectos.
Las escrituras pasan por el bibliotecario: este modulo solo lee y formatea.
"""
from __future__ import annotations

import datetime
import os
import pathlib
import re
from typing import Any


CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))

FILENAME = "pedro-cronologia"
DEFAULT_TEXT = """# Cronologia de Pedro

> Linea de tiempo curada. Sirve para distinguir hechos actuales, cambios de
> etapa y contexto historico sin convertir el perfil de Pedro en una jaula.
> Agregar entradas por propuesta del bibliotecario.

Formato sugerido:

2026-06-16 | Calipso | Pedro esta construyendo Calipso como laboratorio y asistente personal.
"""


def path() -> pathlib.Path:
    d = CALIPSO_HOME / "global" / "core"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{FILENAME}.md"


def ensure() -> pathlib.Path:
    p = path()
    if not p.exists():
        p.write_text(DEFAULT_TEXT, encoding="utf-8")
    return p


def _parse_entry(line: str) -> dict[str, str] | None:
    raw = line.strip()
    if not raw.startswith("- "):
        return None
    body = raw[2:].strip()
    match = re.match(r"(?P<date>\d{4}-\d{2}-\d{2}|actual|unknown)\s*\|\s*(?P<topic>[^|]+)\|\s*(?P<text>.+)", body, re.I)
    if match:
        return {
            "date": match.group("date"),
            "topic": match.group("topic").strip(),
            "text": match.group("text").strip(),
            "raw": raw,
        }
    match = re.match(r"\[(?P<date>[^\]]+)\]\s*(?P<text>.+)", body)
    if match:
        return {
            "date": match.group("date").strip(),
            "topic": "",
            "text": match.group("text").strip(),
            "raw": raw,
        }
    return {"date": "unknown", "topic": "", "text": body, "raw": raw}


def load(limit: int = 80) -> dict[str, Any]:
    p = ensure()
    text = p.read_text(encoding="utf-8")
    entries = [
        entry for line in text.splitlines()
        if (entry := _parse_entry(line))
    ]
    entries = entries[-limit:]
    return {
        "path": str(p),
        "name": p.name,
        "stem": p.stem,
        "chars": len(text),
        "preview": text[:2000],
        "entries": entries,
    }


def format_entry(text: str, topic: str = "Pedro",
                 date: str | None = None) -> str:
    clean = " ".join((text or "").strip().split())
    if not clean:
        raise ValueError("entrada vacia")
    topic_clean = " ".join((topic or "Pedro").strip().split()) or "Pedro"
    when = (date or datetime.date.today().isoformat()).strip()
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", when):
        when = "unknown"
    return f"{when} | {topic_clean} | {clean}"
