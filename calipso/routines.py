#!/usr/bin/env python3
"""
calipso/routines.py - rutinas/timers de Calipso (SPEC 7 "Importantes", Fase 4).

V0 honesta: Calipso es una app local que puede estar apagada, asi que "periodico"
significa "se ejecuta cuando toca mientras el server este vivo". Persistimos
`last_run` para no repetir de mas entre reinicios. No abre nada a internet ni
escala a API: las rutinas v0 son tareas locales seguras (reflect, learn, backup).

El modulo es puro de I/O + logica de vencimiento; el server inyecta los handlers
que ejecutan cada `kind`. La logica de "due" recibe `now` para poder probarse.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import uuid
from typing import Any, Callable

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))

KINDS = ("reflect", "learn", "backup")

# Rutinas por defecto la primera vez (deshabilitadas: Pedro decide encenderlas).
DEFAULTS = [
    {"kind": "reflect", "label": "Reflexionar memoria episodica", "interval_minutes": 1440},
    {"kind": "learn", "label": "Aprender preferencias", "interval_minutes": 1440},
    {"kind": "backup", "label": "Backup de runtime", "interval_minutes": 1440},
]


def _file() -> pathlib.Path:
    CALIPSO_HOME.mkdir(parents=True, exist_ok=True)
    return CALIPSO_HOME / "routines.json"


def _parse(ts: str | None) -> datetime.datetime | None:
    if not ts:
        return None
    try:
        return datetime.datetime.fromisoformat(ts)
    except Exception:
        return None


def _seed() -> list[dict[str, Any]]:
    routines = []
    for d in DEFAULTS:
        routines.append({
            "id": f"rt_{uuid.uuid4().hex[:10]}",
            "kind": d["kind"],
            "label": d["label"],
            "interval_minutes": d["interval_minutes"],
            "enabled": False,
            "last_run": None,
            "last_status": None,
        })
    return routines


def load() -> list[dict[str, Any]]:
    f = _file()
    if not f.exists():
        routines = _seed()
        save(routines)
        return routines
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else _seed()
    except Exception:
        return _seed()


def save(routines: list[dict[str, Any]]) -> None:
    _file().write_text(json.dumps(routines, ensure_ascii=False, indent=2),
                        encoding="utf-8")


def get(routine_id: str) -> dict[str, Any] | None:
    for r in load():
        if r.get("id") == routine_id:
            return r
    return None


def add(kind: str, label: str, interval_minutes: int,
        enabled: bool = False) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"kind no soportado: {kind}")
    routine = {
        "id": f"rt_{uuid.uuid4().hex[:10]}",
        "kind": kind,
        "label": label or kind,
        "interval_minutes": max(1, int(interval_minutes)),
        "enabled": bool(enabled),
        "last_run": None,
        "last_status": None,
    }
    routines = load()
    routines.append(routine)
    save(routines)
    return routine


def update(routine_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    routines = load()
    out = None
    for r in routines:
        if r.get("id") == routine_id:
            if "enabled" in patch:
                r["enabled"] = bool(patch["enabled"])
            if "interval_minutes" in patch:
                r["interval_minutes"] = max(1, int(patch["interval_minutes"]))
            if "label" in patch:
                r["label"] = str(patch["label"])
            out = r
            break
    if out is not None:
        save(routines)
    return out


def remove(routine_id: str) -> bool:
    routines = load()
    kept = [r for r in routines if r.get("id") != routine_id]
    if len(kept) == len(routines):
        return False
    save(kept)
    return True


def next_due_at(routine: dict[str, Any]) -> datetime.datetime | None:
    last = _parse(routine.get("last_run"))
    if last is None:
        return None  # nunca corrio: vence ya
    return last + datetime.timedelta(minutes=int(routine.get("interval_minutes", 1)))


def is_due(routine: dict[str, Any], now: datetime.datetime) -> bool:
    if not routine.get("enabled"):
        return False
    due_at = next_due_at(routine)
    return due_at is None or now >= due_at


def due(routines: list[dict[str, Any]], now: datetime.datetime) -> list[dict[str, Any]]:
    return [r for r in routines if is_due(r, now)]


def mark_run(routine_id: str, now: datetime.datetime, status: str) -> None:
    routines = load()
    for r in routines:
        if r.get("id") == routine_id:
            r["last_run"] = now.isoformat(timespec="seconds")
            r["last_status"] = status
            break
    save(routines)


def run_due(now: datetime.datetime,
            handlers: dict[str, Callable[[dict[str, Any]], Any]]) -> list[dict[str, Any]]:
    """Ejecuta las rutinas vencidas usando los handlers inyectados.

    Devuelve un resumen por rutina ejecutada. Un handler que lanza no rompe las
    demas: se registra `error`.
    """
    ran: list[dict[str, Any]] = []
    for r in due(load(), now):
        handler = handlers.get(r["kind"])
        if handler is None:
            continue
        try:
            handler(r)
            status = "ok"
        except Exception as e:  # pragma: no cover - depende del handler
            status = f"error: {e}"
        mark_run(r["id"], now, status)
        ran.append({"id": r["id"], "kind": r["kind"], "status": status})
    return ran
