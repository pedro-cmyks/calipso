#!/usr/bin/env python3
"""
calipso/routines.py - rutinas/timers de Calipso (SPEC 7 "Importantes", Fase 4).

V0 honesta: Calipso es una app local que puede estar apagada, asi que "periodico"
significa "se ejecuta cuando toca mientras el server este vivo". Persistimos
`last_run` para no repetir de mas entre reinicios. Las tres rutinas viejas
(reflect, learn, backup) son tareas locales seguras que no abren red; la
rutina "departamento" (Tarea 6 del plan de plantel) SI escala a API: despierta
al jefe de un departamento, que decide en el escalon local y puede contratar.
La rutina "cierre" dispara el pulso semanal de la economia (ver DEFAULTS,
mas abajo, para por que nace apagada). La rutina "consumo" mide el uso real
de las suscripciones de CLI (Claude, Codex) leyendo lo que esos procesos ya
escriben solos en disco -- ver calipso/consumo.py para el porque y el como.

El modulo es puro de I/O + logica de vencimiento; el server inyecta los handlers
que ejecutan cada `kind`. La logica de "due" recibe `now` para poder probarse.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import pathlib
import threading
import uuid
from typing import Any, Callable

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))

KINDS = ("reflect", "learn", "backup", "departamento", "catastro", "cierre", "consumo")


class ErrorRutinas(Exception):
    """El archivo esta pero no se pudo leer -- no es lo mismo que "nunca
    hubo rutinas". Los llamadores que ESCRIBEN (add/update/remove/mark_run)
    la usan para negarse a tocar el archivo: pisarlo con el seed seria
    persistir una lectura rota, y con eso Pedro pierde todas sus rutinas de
    verdad, incluida la de departamento con su `cuenta`."""


# Rutinas por defecto la primera vez. Las tres viejas nacen deshabilitadas
# (Pedro decide encenderlas): son mantenimiento -- reflexionar, aprender,
# hacer backup -- y no hay sintoma que dependa de que corran solas.
#
# "catastro" es la excepcion, y nace HABILITADA. La diferencia no es
# capricho: es justamente la rutina que existe para que Pedro no tenga que
# acordarse de prenderla. El pedido que la motiva fue textual -- "todos mis
# proyectos deberian de estar en contexto de calipso de alguna manera o pues
# ser accesible" -- y una rutina que nace apagada no cumple eso hasta que
# alguien la prenda a mano, que es exactamente el estado de hoy que el spec
# ataca. Ademas es la unica de las cuatro sin costo real: no llama a ningun
# modelo, no gasta de la economia, no escribe fuera de ~/.calipso -- son
# `stat()` y `git rev-parse`/`git log` de solo lectura sobre las raices
# declaradas. `catastro.cargar()` igual no depende de que esta rutina haya
# corrido: la primera lectura de la vida del catastro escanea sola aunque
# la rutina siga deshabilitada (ver calipso/catastro.py:cargar).
#
# "cierre" es la contraparte exactamente opuesta: nace deshabilitada como
# las tres viejas, y a proposito. El handler dispara
# `economia.operacion.cerrar_semana_operativa` -- el mismo pulso que hoy
# solo corre a mano via POST /api/economia/cierre -- y eso significa
# expirar pedro-tokens, declarar quiebras de departamentos y liquidar
# trabajos que no rinden, todo solo mientras Pedro no esta mirando.
# Prender ese piloto automatico es una decision suya, no una que el
# codigo tome por default.
#
# "consumo" vuelve al grupo de "catastro": nace HABILITADA, por la misma
# razon. El handler (calipso/consumo.py) solo hace stat()/open() de solo
# lectura sobre jsonl que Claude Code y Codex YA escriben solos en
# ~/.claude y ~/.codex -- nada de red, nada de subprocesos, nada de
# modelos, y sobre todo nada de PREGUNTARLE al CLI su propio estado:
# medido en esta maquina, dos llamadas triviales para consultarlo subieron
# el used_percent de la ventana de 5 horas de Codex de 7.0 a 9.0. Un probe
# que pregunta se come la cuota que quiere medir; uno que solo lee lo que
# ya esta escrito no gasta nada. No hay ningun costo, ni ninguna decision
# irreversible (a diferencia de "cierre"), que justifique que nazca apagada.
DEFAULTS = [
    {"kind": "reflect", "label": "Reflexionar memoria episodica", "interval_minutes": 1440},
    {"kind": "learn", "label": "Aprender preferencias", "interval_minutes": 1440},
    {"kind": "backup", "label": "Backup de runtime", "interval_minutes": 1440},
    {"kind": "catastro", "label": "Escanear catastro de proyectos",
     "interval_minutes": 60, "enabled_por_defecto": True},
    {"kind": "cierre", "label": "Cerrar semana operativa de la economia",
     "interval_minutes": 1440},
    {"kind": "consumo", "label": "Medir consumo real de las suscripciones",
     "interval_minutes": 60, "enabled_por_defecto": True},
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
            "enabled": bool(d.get("enabled_por_defecto", False)),
            "last_run": None,
            "last_status": None,
        })
    return routines


def _cargar_estricto() -> list[dict[str, Any]]:
    """Como `load`, pero NO se traga una corrupcion: la deja subir como
    `ErrorRutinas`. `load` (abajo) es la version tolerante que usan los
    lectores (el panel, el ticker) para no romper cuando el archivo esta a
    medio escribir; esta version la usan los que ESCRIBEN
    (add/update/remove/mark_run), que no pueden confundir "no se pudo leer"
    con "no hay rutinas" y guardar un seed encima de un archivo real."""
    f = _file()
    if not f.exists():
        routines = _seed()
        save(routines)
        return routines
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ErrorRutinas(f"{f} no se pudo leer: {exc}") from exc
    if not isinstance(data, list):
        raise ErrorRutinas(f"{f} no contiene una lista")
    return data


def load() -> list[dict[str, Any]]:
    """Tolerante a proposito: la usan lectores que no pueden reventar (el
    panel, el ticker). Un archivo ausente o ilegible da el seed SIN
    persistirlo -- persistirlo es trabajo de `_cargar_estricto` mas
    `add`/`update`/etc, que si pueden negarse a escribir."""
    try:
        return _cargar_estricto()
    except ErrorRutinas:
        return _seed()


def save(routines: list[dict[str, Any]]) -> None:
    """Atomico a proposito: temporal en el mismo directorio + os.replace, y
    un finally que borra el temporal si el replace no llego a pasar. Con
    write_text un lector concurrente (el ticker en su propio hilo, un
    endpoint en el threadpool de FastAPI) podia ver un JSON a medias,
    `_cargar_estricto` lo reportaba como ilegible, y ANTES de este cambio
    ese lector caia al seed y lo guardaba encima -- Pedro perdia todas sus
    rutinas, incluida la de departamento con su `cuenta`, por una escritura
    que ya iba a terminar bien un instante despues. Mismo patron que
    calipso/plantel/interruptor.py."""
    p = _file()
    tmp = p.with_name(f"{p.name}.tmp{os.getpid()}.{threading.get_ident()}")
    try:
        tmp.write_text(json.dumps(routines, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, p)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def get(routine_id: str) -> dict[str, Any] | None:
    for r in load():
        if r.get("id") == routine_id:
            return r
    return None


def add(kind: str, label: str, interval_minutes: int,
        enabled: bool = False, cuenta: str | None = None) -> dict[str, Any]:
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
        # que departamento despierta esta rutina. None para las de siempre;
        # el ticker le pasa la rutina entera al handler y sin esto no sabria
        # a quien despertar
        "cuenta": cuenta,
    }
    # _cargar_estricto (no `load`): add tambien es load->modify->save, y no
    # puede agregar la rutina nueva a un seed fantasma y guardarlo encima
    # de un archivo real que no se pudo leer.
    routines = _cargar_estricto()
    routines.append(routine)
    save(routines)
    return routine


def update(routine_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
    try:
        routines = _cargar_estricto()
    except ErrorRutinas:
        # no se pudo leer de verdad: no tocar el archivo. Guardar un seed
        # encima seria peor que no escribir nada.
        return None
    out = None
    for r in routines:
        if r.get("id") == routine_id:
            if "enabled" in patch:
                r["enabled"] = bool(patch["enabled"])
            if "interval_minutes" in patch:
                r["interval_minutes"] = max(1, int(patch["interval_minutes"]))
            if "label" in patch:
                r["label"] = str(patch["label"])
            if "cuenta" in patch:
                # Pedro crea la rutina por curl sin el campo y la ve verde:
                # sin poder parchearlo tendria que borrarla y recrearla.
                r["cuenta"] = patch["cuenta"]
            out = r
            break
    if out is not None:
        save(routines)
    return out


def remove(routine_id: str) -> bool:
    try:
        routines = _cargar_estricto()
    except ErrorRutinas:
        return False
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
    try:
        routines = _cargar_estricto()
    except ErrorRutinas:
        # el ticker corre esto despues de CADA rutina vencida: si el
        # archivo no se pudo leer ahora, la proxima vuelta (60s) lo
        # reintenta. No tocarlo es mejor que reescribirlo con un seed.
        return
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
