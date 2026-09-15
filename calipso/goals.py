#!/usr/bin/env python3
"""
calipso/goals.py - el goal que corre (spec 2026-09-13) sobre el Goal Mode viejo.

Un goal es una tarea con objetivo, criterio medible, tope y compuertas que
Calipso persigue golpe a golpe con unas manos headless (claude/codex) dentro
de un sandbox, y que Pedro cierra. Este modulo es el ALMACEN: los campos, las
transiciones (cerradas, atomicas, `transicionar` es lo unico que escribe
`status`), el puntero global `activo.json`, el ledger de golpes
(`golpes.jsonl`, dos filas por golpe: `inicio` antes de invocar, `fin`
despues), la tabla de compuertas y la gramatica de `/goal`. El bucle vive en
`goals_runner.py`, las manos en `goals_manos.py`, el hook en `goals_hook.py`.

Lo viejo (create/update/add_evidence/set_criterion/set_subtask/events) se
conserva para developer.py, tools/commands.py y verification.py; `detect` y
`check_auto_close` desaparecieron (ruling 15.3: "sin tope no corre" y "nadie
es complete sin juez"). Los goals nuevos viven en `~/.calipso/goals/<id>/`;
los viejos siguen en `~/.calipso/projects/<slug>/goals/<id>/` y `load` mira
las dos carpetas.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import pathlib
import re
import threading
import uuid
from typing import Any

from calipso import goals_hook
from calipso import telemetry

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))

PROPOSED = "proposed"
ACTIVE = "active"
WAITING = "waiting"
BLOCKED = "blocked"
COMPLETE = "complete"
FAILED = "failed"
CANCELLED = "cancelled"

ACTIVE_STATES = {PROPOSED, ACTIVE, WAITING, BLOCKED}
FINAL_STATES = {COMPLETE, CANCELLED, FAILED}
VALID_STATES = ACTIVE_STATES | FINAL_STATES

# Las transiciones cerradas (spec seccion 3). `blocked` es del Goal Mode viejo
# y solo sale hacia active/cancelled/complete. De un final no se sale.
TRANSICIONES: dict[str, set[str]] = {
    PROPOSED: {ACTIVE, CANCELLED},
    ACTIVE: {WAITING, FAILED, CANCELLED},
    WAITING: {ACTIVE, COMPLETE, CANCELLED, FAILED},
    BLOCKED: {ACTIVE, CANCELLED, COMPLETE},
    COMPLETE: set(), CANCELLED: set(), FAILED: set(),
}

# La tabla de compuertas: la decision de Pedro afinada el 2026-09-13 (spec
# seccion 8, ruling 15.14). Ruling que el implementador no toca (plan, R1).
COMPUERTAS: dict[str, tuple[str, ...]] = {
    "directo": ("repo", "web", "instalar_en_goal", "raices"),
    "pregunta": ("merge", "push", "borrar_fuera", "raiz_nueva",
                 "instalar_home", "instalar_sistema"),
    "nunca": ("gastar", "publicar", "correo", "datos_de_pedro",
              "rpm_ostree_rebase", "flatpak_remote_delete"),
}
NIVEL_DE: dict[str, str] = {f: nivel for nivel, fs in COMPUERTAS.items() for f in fs}

TOPE_DEFECTO = {"golpes": 20, "minutos": 120, "unidades": 60, "mm": 0}
MANOS = ("claude", "codex")
VERBOS = ("dale", "no", "parar", "segui", "estado")
CRITERIOS = ("comando", "archivo", "numero", "revisor")


class ErrorGoal(ValueError):
    """Una transicion que no existe, un tope invalido, un goal que no esta."""


# --------------------------------------------------------------------------
# rutas: lo viejo por proyecto, lo nuevo global
# --------------------------------------------------------------------------

def _slug(project_root: str | None) -> str:
    if not project_root:
        return "global"
    p = pathlib.Path(project_root).resolve()
    return str(p).replace(":", "").replace("\\", "-").replace("/", "-").strip("-")


def _goals_dir(project_root: str | None) -> pathlib.Path:
    d = CALIPSO_HOME / "projects" / _slug(project_root) / "goals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _goal_dir(project_root: str | None, goal_id: str) -> pathlib.Path:
    """La carpeta del goal: la nueva si existe ahi, si no la vieja del
    proyecto (que se crea al pedirla, como siempre)."""
    nueva = raiz_goals() / goal_id
    if (nueva / "goal.json").exists():
        return nueva
    d = _goals_dir(project_root) / goal_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def raiz_goals() -> pathlib.Path:
    d = CALIPSO_HOME / "goals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def dir_goal(goal_id: str) -> pathlib.Path:
    d = raiz_goals() / goal_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def raiz_trabajo() -> pathlib.Path:
    """La raiz de los clones y las carpetas de trabajo de los goals: env
    CALIPSO_GOALS_TRABAJO o `~/.local/share/calipso/goals`. FUERA de
    ~/.calipso a proposito (ruling del controlador 2026-09-14): ~/.calipso
    esta en DENY_READ del sandbox (goals_manos) y en PROTEGIDAS del hook
    (goals_hook), y el martillo tiene que poder leer y escribir su propio
    clon. Se resuelve por llamada (los tests la mueven por env) y NO crea
    nada: sin la env apunta al home real y este modulo no lo toca."""
    return pathlib.Path(os.environ.get(
        "CALIPSO_GOALS_TRABAJO", os.path.expanduser("~/.local/share/calipso/goals")))


def dir_trabajo(goal_id: str) -> pathlib.Path:
    """`raiz_trabajo()/<id>`: ahi viven `repo/` (el clon) y `trabajo/` (la
    carpeta del goal sin repo). goal.json, events, golpes, contrato.md,
    compuertas.json y hook.jsonl siguen en `dir_goal` (los leen el server
    y el hook, que corren fuera del sandbox)."""
    d = raiz_trabajo() / goal_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def ruta_activo() -> pathlib.Path:
    return raiz_goals() / "activo.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _title_from(objective: str) -> str:
    clean = " ".join(objective.strip().split())
    if not clean:
        return "Meta sin titulo"
    return clean[:82] + ("..." if len(clean) > 82 else "")


def _escribir_json_atomico(p: pathlib.Path, data: Any) -> None:
    """Molde catastro._guardar_json: temporal en el mismo directorio +
    os.replace, para que un lector concurrente nunca vea un JSON a medio
    escribir (Trampa 17: el _write viejo no era atomico)."""
    tmp = p.with_name(f"{p.name}.tmp{os.getpid()}.{threading.get_ident()}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


# --------------------------------------------------------------------------
# lo viejo que queda
# --------------------------------------------------------------------------

def propose_criteria(objective: str) -> list[dict[str, Any]]:
    base = [
        "Objetivo entendido y descompuesto en subtareas",
        "Cambios necesarios implementados",
        "Validacion ejecutada con evidencia guardada",
        "Riesgos o bloqueos documentados",
        "Siguiente accion clara para Pedro",
    ]
    low = objective.lower()
    if any(w in low for w in ("iphone", "celular", "pwa", "movil", "móvil")):
        base = [
            "Calipso abre desde el dispositivo objetivo",
            "Acceso seguro definido (Tailscale/token/TOTP)",
            "Experiencia tipo app instalada o documentada",
            "Prueba visual realizada y guardada como evidencia",
            "Pasos de recuperacion documentados si localhost cae",
        ]
    elif any(w in low for w in ("github", "repo", "pull request", "pr")):
        base = [
            "Repositorio identificado y conectado",
            "Flujo de rama/commit/PR definido",
            "Permisos y riesgos de escritura claros",
            "Cambio validado antes de publicar",
            "Evidencia de estado remoto guardada",
        ]
    elif any(w in low for w in ("lanzar", "launch", "produccion", "producción")):
        base = [
            "Checklist de lanzamiento completo",
            "Flujos criticos probados",
            "Seguridad y acceso revisados",
            "Plan de rollback o recuperacion documentado",
            "Evidencia de verificacion adjunta",
        ]
    return [
        {"id": f"c{i + 1}", "text": text, "done": False, "evidence": []}
        for i, text in enumerate(base)
    ]


def propose_subtasks(objective: str) -> list[dict[str, Any]]:
    items = [
        "Aclarar alcance y estado actual",
        "Inspeccionar repo/configuracion relevante",
        "Implementar el siguiente incremento verificable",
        "Validar con prueba automatica o visual",
        "Registrar evidencia y actualizar literatura",
    ]
    return [
        {"id": f"t{i + 1}", "text": text, "status": "pending"}
        for i, text in enumerate(items)
    ]


def create(project_root: str | None, objective: str, title: str | None = None,
           criteria: list[dict[str, Any]] | list[str] | None = None,
           subtasks: list[dict[str, Any]] | list[str] | None = None,
           make_active: bool = True, **data: Any) -> dict[str, Any]:
    """El Goal Mode viejo: nace `active` y (si make_active) apunta el
    `activo.json` global. Los goals que corren nacen con `crear`."""
    goal_id = f"goal_{uuid.uuid4().hex[:12]}"
    normalized_criteria = _normalize_items(
        criteria if criteria is not None else propose_criteria(objective),
        prefix="c", done_key=True)
    normalized_subtasks = _normalize_items(
        subtasks if subtasks is not None else propose_subtasks(objective),
        prefix="t", status_key=True)
    goal = {
        "id": goal_id,
        "title": title or _title_from(objective),
        "objective": objective.strip(),
        "status": ACTIVE,
        "criteria": normalized_criteria,
        "subtasks": normalized_subtasks,
        "evidence": [],
        "blockers": [],
        "created_at": _now(),
        "updated_at": _now(),
        **data,
    }
    _write(project_root, goal)
    event(project_root, goal_id, "created", objective=goal["objective"])
    if make_active:
        set_active(project_root, goal_id)
    return goal


def _normalize_items(items: list[dict[str, Any]] | list[str], prefix: str,
                     done_key: bool = False, status_key: bool = False) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, item in enumerate(items or []):
        if isinstance(item, dict):
            row = dict(item)
            row.setdefault("id", f"{prefix}{i + 1}")
            if done_key:
                row.setdefault("done", False)
                row.setdefault("evidence", [])
            if status_key:
                row.setdefault("status", "pending")
        else:
            row = {"id": f"{prefix}{i + 1}", "text": str(item)}
            if done_key:
                row["done"] = False
                row["evidence"] = []
            if status_key:
                row["status"] = "pending"
        out.append(row)
    return out


def _write(project_root: str | None, goal: dict[str, Any]) -> None:
    goal["updated_at"] = _now()
    _escribir_json_atomico(_goal_dir(project_root, goal["id"]) / "goal.json", goal)


def load(project_root: str | None, goal_id: str) -> dict[str, Any] | None:
    """Primero la carpeta nueva (`~/.calipso/goals/<id>`), despues la vieja
    del proyecto. Un JSON roto es None (nunca levanta)."""
    for p in (raiz_goals() / goal_id / "goal.json",
              _goals_dir(project_root) / goal_id / "goal.json"):
        if not p.exists():
            continue
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def set_active(project_root: str | None, goal_id: str | None) -> None:
    """El puntero GLOBAL `~/.calipso/goals/activo.json` (ruling 15.3: no del
    slug del ROOT conmutable). `project_root` se guarda al lado del id para
    que `activo()` pueda cargar un goal VIEJO (que vive bajo el slug del
    proyecto); los nuevos viven en la carpeta global y lo ignoran."""
    p = ruta_activo()
    if goal_id:
        _escribir_json_atomico(p, {"id": goal_id, "proyecto": project_root})
    elif p.exists():
        with contextlib.suppress(OSError):
            p.unlink()


def activo() -> dict[str, Any] | None:
    """El goal al que apunta activo.json, si existe y no es final. Un
    goal.json roto devuelve None SIN borrar el puntero (Trampa 17): lo
    reconcilia el arranque, no un lector cualquiera."""
    p = ruta_activo()
    if not p.exists():
        return None
    try:
        puntero = json.loads(p.read_text(encoding="utf-8"))
        goal_id = puntero.get("id")
    except Exception:
        return None
    goal = load(puntero.get("proyecto"), goal_id) if goal_id else None
    if not goal:
        return None
    if goal.get("status") in FINAL_STATES:
        set_active(None, None)
        return None
    return goal


def active(project_root: str | None) -> dict[str, Any] | None:
    """Compatibilidad: los catorce sitios del server que llaman
    `goals.active(str(ROOT))` ven el activo global."""
    return activo()


def list_goals(project_root: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Los nuevos (globales) y los viejos del proyecto, por mtime."""
    rutas = list(raiz_goals().glob("*/goal.json"))
    rutas += list(_goals_dir(project_root).glob("*/goal.json"))
    out: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for p in sorted(rutas, key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            g = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if g.get("id") in vistos:
            continue
        vistos.add(g.get("id"))
        out.append(g)
        if len(out) >= limit:
            break
    return out


def update(project_root: str | None, goal_id: str, **changes: Any) -> dict[str, Any] | None:
    """Lo viejo. Sigue escribiendo `status` para developer/tests viejos
    SOLO en un goal viejo (sin `tope`); en un goal que corre levanta
    ValueError (transicionar es la unica puerta). La puerta HTTP (`PUT
    /api/goals/{id}`) rechaza status/active para todos."""
    goal = load(project_root, goal_id)
    if not goal:
        return None
    if goal.get("tope") and (changes.get("status") or changes.get("blocker")):
        # un goal que corre (spec seccion 3, invariante 2): ni complete ni
        # nada por aca; solo transicionar (que valida y apunta activo.json).
        # `blocker` cuenta como status: escribia BLOCKED directo y dejaba al
        # goal donde el runner no puede estacionarlo ni fallarlo (invariante 6)
        raise ValueError("un goal que corre solo cambia de status por goals.transicionar")
    if "status" in changes and changes["status"]:
        status = str(changes["status"])
        if status not in VALID_STATES:
            raise ValueError(f"estado invalido: {status}")
        goal["status"] = status
        if status in FINAL_STATES:
            current = activo()
            if current and current.get("id") == goal_id:
                set_active(project_root, None)
    for key in ("title", "objective", "criteria", "subtasks"):
        if key in changes and changes[key] is not None:
            goal[key] = changes[key]
    if changes.get("blocker"):
        goal.setdefault("blockers", []).append({
            "ts": _now(), "text": str(changes["blocker"])
        })
        goal["status"] = BLOCKED
    _write(project_root, goal)
    event(project_root, goal_id, "updated", changes={k: v for k, v in changes.items() if k != "criteria"})
    return goal


def add_evidence(project_root: str | None, goal_id: str, kind: str, text: str,
                 **data: Any) -> dict[str, Any] | None:
    goal = load(project_root, goal_id)
    if not goal:
        return None
    item = {"ts": _now(), "kind": kind, "text": text, **data}
    goal.setdefault("evidence", []).append(item)
    _write(project_root, goal)
    event(project_root, goal_id, "evidence", evidence=item)
    return goal


def set_criterion(project_root: str | None, goal_id: str, criterion_id: str,
                  done: bool, evidence: str | None = None) -> dict[str, Any] | None:
    """Marca un criterio viejo. Ya NO auto-cierra (ruling 15.3)."""
    goal = load(project_root, goal_id)
    if not goal:
        return None
    found = None
    for item in goal.get("criteria") or []:
        if item.get("id") == criterion_id:
            found = item
            break
    if not found:
        raise KeyError(criterion_id)
    found["done"] = bool(done)
    if evidence:
        ev = {"ts": _now(), "text": evidence}
        found.setdefault("evidence", []).append(ev)
        goal.setdefault("evidence", []).append({
            "ts": ev["ts"],
            "kind": "criterion",
            "text": evidence,
            "criterion_id": criterion_id,
        })
    _write(project_root, goal)
    event(project_root, goal_id, "criterion", criterion_id=criterion_id, done=bool(done))
    return goal


def set_subtask(project_root: str | None, goal_id: str, subtask_id: str,
                status: str) -> dict[str, Any] | None:
    goal = load(project_root, goal_id)
    if not goal:
        return None
    found = None
    for item in goal.get("subtasks") or []:
        if item.get("id") == subtask_id:
            found = item
            break
    if not found:
        raise KeyError(subtask_id)
    found["status"] = status
    _write(project_root, goal)
    event(project_root, goal_id, "subtask", subtask_id=subtask_id, status=status)
    return goal


def _next_id(items: list[dict[str, Any]], prefix: str) -> str:
    n = 0
    for it in items or []:
        m = re.match(rf"{prefix}(\d+)$", str(it.get("id") or ""))
        if m:
            n = max(n, int(m.group(1)))
    return f"{prefix}{n + 1}"


def add_criterion(project_root: str | None, goal_id: str, text: str) -> dict[str, Any] | None:
    goal = load(project_root, goal_id)
    if not goal:
        return None
    items = goal.setdefault("criteria", [])
    item = {"id": _next_id(items, "c"), "text": str(text).strip(),
            "done": False, "evidence": []}
    items.append(item)
    _write(project_root, goal)
    event(project_root, goal_id, "criterion_added", criterion_id=item["id"])
    return goal


def add_subtask(project_root: str | None, goal_id: str, text: str) -> dict[str, Any] | None:
    goal = load(project_root, goal_id)
    if not goal:
        return None
    items = goal.setdefault("subtasks", [])
    item = {"id": _next_id(items, "t"), "text": str(text).strip(), "status": "pending"}
    items.append(item)
    _write(project_root, goal)
    event(project_root, goal_id, "subtask_added", subtask_id=item["id"])
    return goal


def edit_item_text(project_root: str | None, goal_id: str, kind: str,
                   item_id: str, text: str) -> dict[str, Any] | None:
    """Edita el texto de un criterio (`criteria`) o subtarea (`subtasks`)."""
    key = "criteria" if kind == "criteria" else "subtasks"
    goal = load(project_root, goal_id)
    if not goal:
        return None
    for item in goal.get(key) or []:
        if item.get("id") == item_id:
            item["text"] = str(text).strip()
            _write(project_root, goal)
            event(project_root, goal_id, "item_edited", kind=key, item_id=item_id)
            return goal
    raise KeyError(item_id)


def remove_item(project_root: str | None, goal_id: str, kind: str,
                item_id: str) -> dict[str, Any] | None:
    key = "criteria" if kind == "criteria" else "subtasks"
    goal = load(project_root, goal_id)
    if not goal:
        return None
    items = goal.get(key) or []
    kept = [it for it in items if it.get("id") != item_id]
    if len(kept) == len(items):
        raise KeyError(item_id)
    goal[key] = kept
    _write(project_root, goal)
    event(project_root, goal_id, "item_removed", kind=key, item_id=item_id)
    return goal


def event(project_root: str | None, goal_id: str, action: str,
          **data: Any) -> dict[str, Any]:
    entry = {"ts": _now(), "goal_id": goal_id, "action": action, **data}
    p = _goal_dir(project_root, goal_id) / "events.jsonl"
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def events(project_root: str | None, goal_id: str, limit: int = 200) -> list[dict[str, Any]]:
    p = _goal_dir(project_root, goal_id) / "events.jsonl"
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


# --------------------------------------------------------------------------
# lo nuevo: crear, transicionar, escribir
# --------------------------------------------------------------------------

def validar_tope(tope: dict | None) -> dict:
    t = {**TOPE_DEFECTO, **(tope or {})}
    for k in ("golpes", "minutos", "unidades", "mm"):
        try:
            t[k] = int(t[k])
        except (TypeError, ValueError):
            raise ErrorGoal(f"tope invalido: {k}={t[k]!r}")
        if t[k] < 0:
            raise ErrorGoal(f"tope invalido: {k}={t[k]}")
    if t["golpes"] == 0 or t["minutos"] == 0 or t["unidades"] == 0:
        raise ErrorGoal("sin tope no corre: golpes, minutos y unidades tienen que ser > 0")
    return t


def validar_raices(raices: list | None) -> list[str]:
    """Las raices declaradas (la propuesta, `raiz:`, una `raiz_nueva`
    aprobada), normalizadas (`~`, `..`, enlaces) y acotadas: `/`, el home,
    un ancestro del home y las protegidas del hook (goals_hook.PROTEGIDAS,
    y lo que cuelga de ellas) NO son raices validas (ruling del cierre
    2026-09-14: en el smoke la propuesta declaro `~` como raiz, el sandbox
    la hubiera hecho escribible entera y devolvio EROFS por casualidad).
    Una raiz relativa no dice nada (seria contra el cwd del server) y se
    rechaza. Se guarda la forma absoluta que declaro Pedro (sin seguir
    enlaces: en la Ally `/home` es un enlace a `/var/home` y la ruta que
    escribio es la que quiere ver); los enlaces se siguen solo para
    compararla. ErrorGoal con la ruta y que hacer."""
    out: list[str] = []
    home = pathlib.Path(os.path.expanduser("~")).resolve()
    protegidas = [pathlib.Path(os.path.expanduser(x)).resolve() for x in goals_hook.PROTEGIDAS]
    for r in raices or []:
        texto = str(r or "").strip()
        if not texto:
            raise ErrorGoal("raiz vacia; declara una carpeta concreta")
        expandida = os.path.expanduser(texto)
        if not os.path.isabs(expandida):
            raise ErrorGoal(f"raiz relativa: {texto}; declara una ruta absoluta")
        p = pathlib.Path(os.path.abspath(expandida))
        real = p.resolve()
        if real == pathlib.Path("/") or real == home or real in home.parents \
                or any(real == q or q in real.parents for q in protegidas):
            raise ErrorGoal(f"raiz demasiado amplia: {texto}; declara una carpeta concreta")
        out.append(str(p))
    return out


def validar_criterio(criterio: dict | None) -> dict:
    c = dict(criterio or {"tipo": "revisor", "texto": ""})
    if c.get("tipo") not in CRITERIOS:
        raise ErrorGoal(f"criterio invalido: {c.get('tipo')!r} (son {CRITERIOS})")
    if c["tipo"] == "comando" and not str(c.get("comando") or "").strip():
        raise ErrorGoal("criterio comando sin comando")
    if c["tipo"] == "archivo" and not str(c.get("ruta") or "").strip():
        raise ErrorGoal("criterio archivo sin ruta")
    if c["tipo"] == "numero":
        try:
            float(c.get("umbral"))
        except (TypeError, ValueError):
            raise ErrorGoal("criterio numero sin umbral")
        if not c.get("metrica"):
            raise ErrorGoal("criterio numero sin metrica")
    return c


def nuevo_id() -> str:
    """Un id de goal. Lo reserva `_proponer_goal` ANTES de invocar la cabeza
    para que la propuesta cruce la aduana y quede en el ledger como el
    golpe 0 con su id (invariantes 3 y 9): el goal nace despues, con
    `crear(..., goal_id=)`."""
    return f"goal_{uuid.uuid4().hex[:12]}"


def crear(texto: str, *, proyecto: str | None, titulo: str | None = None,
          criterio: dict | None = None, tope: dict | None = None,
          compuertas: dict | None = None, manos: str = "claude",
          plan: list[str] | None = None, privado: bool = False,
          dominios: list[str] | None = None, propuesta: dict | None = None,
          departamento: str | None = None, goal_id: str | None = None) -> dict[str, Any]:
    """Un goal que corre. Nace `proposed` y NO se activa: lo activa el dale
    de Pedro por `transicionar`. `proyecto` es la ruta del repo de origen
    (None = goal sin repo); el clon (`repo`) lo escribe el runner al
    arrancar. `session_id` es el de la sesion headless (--session-id en el
    golpe 1, --resume despues). `goal_id`: uno reservado con `nuevo_id`
    (la propuesta ya escribio su golpe 0 ahi); sin el, uno nuevo."""
    if manos not in MANOS:
        raise ErrorGoal(f"manos invalidas: {manos!r} (son {MANOS})")
    texto = " ".join((texto or "").split())
    if not texto:
        raise ErrorGoal("un goal sin texto")
    goal_id = goal_id or nuevo_id()
    if (dir_goal(goal_id) / "goal.json").exists():
        raise ErrorGoal(f"el goal {goal_id} ya existe")
    raices = validar_raices((compuertas or {}).get("raices"))
    proyecto_nombre = (pathlib.Path(proyecto).name if proyecto else "sin-repo") or "sin-repo"
    goal = {
        "id": goal_id,
        "title": titulo or _title_from(texto),
        "objective": texto,
        "status": PROPOSED,
        "criterio": validar_criterio(criterio),
        "tope": validar_tope(tope),
        "compuertas": {"niveles": dict(NIVEL_DE), "raices": raices},
        "dominios": list(dominios or []),
        "proyecto": proyecto,
        "proyecto_nombre": proyecto_nombre,
        "repo": None,
        "privado": bool(privado),
        "manos": manos,
        "plan": list(plan or []),
        "propuesta": propuesta,
        "departamento": departamento,
        "session_id": str(uuid.uuid4()),
        "espera": None,
        "ultima_nota": None,
        "criteria": [], "subtasks": [], "evidence": [], "blockers": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    _escribir_json_atomico(dir_goal(goal_id) / "goal.json", goal)
    event(None, goal_id, "created", objective=texto, proyecto=proyecto)
    telemetry.log_event("goal", accion="creado", goal_id=goal_id, manos=manos,
                        privado=bool(privado), tope=goal["tope"])
    return goal


def escribir(goal: dict[str, Any]) -> None:
    """Escribe goal.json (atomico) SIN tocar status: si el status en memoria
    no es el del disco, alguien transiciono en el medio y este dict esta
    viejo -- se levanta antes de pisar (transicionar es la unica puerta)."""
    actual = load(None, goal["id"])
    if actual is None:
        raise ErrorGoal(f"goal inexistente: {goal['id']}")
    if actual.get("status") != goal.get("status"):
        raise ErrorGoal(f"status viejo en memoria ({goal.get('status')} != "
                        f"{actual.get('status')}): transicionar es la unica puerta")
    goal["updated_at"] = _now()
    _escribir_json_atomico(dir_goal(goal["id"]) / "goal.json", goal)


def transicionar(goal_id: str, a: str, motivo: str = "",
                 **extra: Any) -> dict[str, Any]:
    """La UNICA puerta de `status`. Transiciones cerradas (TRANSICIONES),
    escritura atomica, evento `transicion`, el puntero global (a `active`
    apunta; a un final lo borra si apuntaba) y una fila de telemetria.
    `extra["motivo_detalle"]` (dict) se guarda en `goal["espera"]` junto al
    motivo cuando `a == waiting`; el resto de `extra` va al evento.
    Invariante 8: a `active` con OTRO goal no final (active o waiting)
    apuntado por activo.json levanta: si no, set_active pisaria el puntero
    y el que espera desapareceria de activo(), del _goal_context y de la
    #goalBar (muerte silenciosa)."""
    goal = load(None, goal_id)
    if goal is None:
        raise ErrorGoal(f"goal inexistente: {goal_id}")
    de = goal.get("status")
    if a not in VALID_STATES:
        raise ErrorGoal(f"estado invalido: {a!r}")
    if a not in TRANSICIONES.get(de, set()):
        raise ErrorGoal(f"transicion invalida: {de} -> {a}")
    detalle = extra.pop("motivo_detalle", None)
    if a == ACTIVE:
        otro = activo()                 # None si el apuntado es final
        if otro and otro.get("id") != goal_id:
            esp = (otro.get("espera") or {}).get("motivo")
            raise ErrorGoal(f"ya hay un goal en curso: {otro['id']} ({otro.get('status')}"
                            + (f", esperando: {esp}" if esp else "") + ")")
        goal["espera"] = None
        goal.setdefault("activado_en", _now())
    elif a == WAITING:
        goal["espera"] = {"motivo": motivo, **(detalle or {})}
    goal["status"] = a
    if a in FINAL_STATES:
        goal["cerrado_en"] = _now()
        goal["motivo_cierre"] = motivo
    goal["updated_at"] = _now()
    _escribir_json_atomico(dir_goal(goal_id) / "goal.json", goal)
    if a == ACTIVE:
        set_active(None, goal_id)
    elif a in FINAL_STATES:
        puntero = None
        with contextlib.suppress(Exception):
            puntero = json.loads(ruta_activo().read_text(encoding="utf-8")).get("id")
        if puntero == goal_id:
            set_active(None, None)
    event(None, goal_id, "transicion", de=de, a=a, motivo=motivo, **extra)
    telemetry.log_event("goal", accion="transicion", goal_id=goal_id, de=de, a=a,
                        motivo=motivo)
    return goal


def nota_de_pedro(goal_id: str, texto: str) -> dict[str, Any]:
    """`/goal segui <nota>` o la respuesta del inbox: al ledger y al goal."""
    goal = load(None, goal_id)
    if goal is None:
        raise ErrorGoal(f"goal inexistente: {goal_id}")
    goal["ultima_nota"] = texto
    escribir(goal)
    return event(None, goal_id, "nota_pedro", texto=texto)


RESPUESTAS_QUE_APLICAN = ("pregunta", "compuerta", "raiz_nueva")
# Los waiting que no esperan nada del martillo sino a Pedro (ruling del
# cierre 2026-09-14, "Pedro no se pierde"): cada uno estaciona una solicitud
# `retomar` (si = seguir, no = cancelar) para que aparezca en el inbox.
MOTIVOS_RETOMAR = ("tope", "cuota", "no_convergencia", "parado por Pedro", "server apagado",
                   "server reiniciado")
FACTOR_TOPE_RETOMAR = 1.5


def ampliar_tope(goal: dict[str, Any], factor: float = FACTOR_TOPE_RETOMAR) -> dict[str, Any]:
    """El si de Pedro a un waiting por tope: golpes, minutos y unidades
    suben `factor` (redondeo hacia arriba; `mm` no, lo gobierna la ruta
    api). Recarga antes de escribir (last-writer-wins) y deja el evento."""
    g = load(None, goal["id"])
    if g is None:
        raise ErrorGoal(f"goal inexistente: {goal['id']}")
    viejo = {**TOPE_DEFECTO, **(g.get("tope") or {})}
    nuevo = dict(viejo)
    for k in ("golpes", "minutos", "unidades"):
        nuevo[k] = int(-(-viejo[k] * factor // 1))
    g["tope"] = validar_tope(nuevo)
    escribir(g)
    event(None, goal["id"], "tope_ampliado", de=viejo, a=g["tope"], factor=factor)
    return g


def aplicar_respuesta(goal_id: str, respuesta: str, nota: str | None = None) -> dict[str, Any]:
    """Lo que la respuesta de Pedro a una espera cambia en el goal ANTES de
    retomar (decision 16): `aprobada` sobre una compuerta suma la
    preautorizacion al goal (decision 9) y reescribe compuertas.json (el
    hook la lee); sobre una raiz nueva suma la raiz; sobre un `tope`
    (solicitud `retomar`) amplia el tope un 50 %; y siempre deja la nota en
    el ledger, con la `nota` que Pedro escribio al responder (carril 3:
    `solicitud["nota"]`) si la hubo. NO transiciona: eso es del que llama.
    La llaman el runner (el si del inbox) y `_retomar_goal` (un `/goal
    segui` es un si): un si sin aplicar dejaria al hook denegando y al
    martillo preguntando de nuevo. Sobre otra espera no toca nada."""
    goal = load(None, goal_id)
    if goal is None:
        raise ErrorGoal(f"goal inexistente: {goal_id}")
    espera = goal.get("espera") or {}
    motivo = espera.get("motivo")
    if motivo not in RESPUESTAS_QUE_APLICAN and motivo not in MOTIVOS_RETOMAR:
        return goal
    si = respuesta == "aprobada"
    c = goal.setdefault("compuertas", {})
    if si and motivo == "compuerta" and isinstance(espera.get("compuerta"), dict):
        pre = list(c.get("preautorizadas") or [])
        pre.append({"familia": espera["compuerta"].get("familia"),
                    "forma": espera["compuerta"].get("forma") or {}})
        c["preautorizadas"] = pre
    if si and motivo == "raiz_nueva" and espera.get("raiz"):
        c["raices"] = list(c.get("raices") or []) + validar_raices([espera["raiz"]])
    escribir(goal)
    escribir_compuertas(goal)
    if si and motivo == "tope":
        ampliar_tope(goal)
    texto = f"Pedro respondio: {'si' if si else 'no'} a: {espera.get('pregunta') or motivo}"
    if nota:
        texto += f" -- {nota}"
    nota_de_pedro(goal_id, texto)
    if nota:
        # la nota tal cual es lo que el martillo lee en el prompt (NOTA DE
        # PEDRO): el "respondio si a" es para el ledger, no para el
        g = load(None, goal_id)
        g["ultima_nota"] = nota
        escribir(g)
    return load(None, goal_id)


# --------------------------------------------------------------------------
# golpes.jsonl: dos filas por golpe
# --------------------------------------------------------------------------

def _ruta_golpes(goal_id: str) -> pathlib.Path:
    return dir_goal(goal_id) / "golpes.jsonl"


def _anotar_golpe(goal_id: str, fila: dict) -> dict:
    with open(_ruta_golpes(goal_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    return fila


def golpe_inicio(goal_id: str, n: int, **fila: Any) -> dict:
    """ANTES de invocar (invariante 3): n, manos, paso, ts."""
    return _anotar_golpe(goal_id, {"n": int(n), "fase": "inicio", "ts": _now(), **fila})


def golpe_fin(goal_id: str, n: int, **fila: Any) -> dict:
    """DESPUES: unidades, duracion_ms, veredicto_del_golpe, comandos,
    diff_stat, secretos_tapados, exit, cobro, rate_limit, juez..."""
    return _anotar_golpe(goal_id, {"n": int(n), "fase": "fin", "ts_fin": _now(), **fila})


def golpes(goal_id: str) -> list[dict]:
    """Las filas fundidas por n, en orden. Un golpe con inicio y sin fin
    queda con `fase: inicio` (lo corto el apagado o un crash)."""
    p = _ruta_golpes(goal_id)
    if not p.exists():
        return []
    por_n: dict[int, dict] = {}
    for linea in p.read_text(encoding="utf-8").splitlines():
        try:
            fila = json.loads(linea)
        except json.JSONDecodeError:
            continue
        n = int(fila.get("n", 0))
        por_n[n] = {**por_n.get(n, {}), **fila}
    return [por_n[n] for n in sorted(por_n)]


def consumo(goal: dict[str, Any]) -> dict:
    """Lo gastado contra el tope: golpes (los que cuentan), minutos (suma de
    duracion_ms, 2 decimales), unidades (todas, incluidas las de un golpe
    que no cuenta: la cuota se gasto igual) y mm."""
    filas = golpes(goal["id"])
    g = sum(1 for f in filas if f.get("cuenta_para_tope", True) is not False)
    ms = sum(int(f.get("duracion_ms") or 0) for f in filas)
    u = sum(int(f.get("unidades") or 0) for f in filas)
    mm = sum(int(f.get("mm") or 0) for f in filas)
    return {"golpes": g, "minutos": round(ms / 60_000, 2), "unidades": u, "mm": mm}


def tope_alcanzado(goal: dict[str, Any]) -> str | None:
    """El primer tope tocado (spec seccion 3: el primero que se alcanza
    para), en el orden golpes, minutos, unidades, mm. `mm: 0` no frena."""
    t = {**TOPE_DEFECTO, **(goal.get("tope") or {})}
    c = consumo(goal)
    for k in ("golpes", "minutos", "unidades", "mm"):
        if t[k] and c[k] >= t[k]:
            return k
    return None


# --------------------------------------------------------------------------
# la gramatica de /goal
# --------------------------------------------------------------------------

_RE_TOPE = re.compile(r"(\d+)\s*(h|m|min|minutos?|golpes?|unidades?)\b", re.IGNORECASE)
_CLAVES = ("hasta", "tope", "en", "raiz", "con")
_RE_CLAVE = re.compile(r"\b(hasta|tope|en|raiz|con)\s*:\s*", re.IGNORECASE)


def parse_tope(texto: str) -> dict:
    """`2h` -> minutos 120; `20 golpes`; `60 unidades`; `1h 10 golpes`;
    `45m`. Parcial: solo las claves que aparecieron (crear completa con
    TOPE_DEFECTO)."""
    out: dict = {}
    for n, unidad in _RE_TOPE.findall(texto or ""):
        u = unidad.lower()
        if u == "h":
            out["minutos"] = out.get("minutos", 0) + int(n) * 60
        elif u in ("m", "min") or u.startswith("minuto"):
            out["minutos"] = out.get("minutos", 0) + int(n)
        elif u.startswith("golpe"):
            out["golpes"] = int(n)
        elif u.startswith("unidad"):
            out["unidades"] = int(n)
    return out


def parse_criterio(texto: str) -> dict:
    """`pytest en verde` / `pytest -q x` -> comando; `existe <ruta>` ->
    archivo; `que salga 0: <cmd>` -> comando; lo demas -> revisor."""
    t = " ".join((texto or "").split())
    low = t.lower()
    m = re.match(r"que salga 0\s*:\s*(.+)$", low)
    if m:
        return {"tipo": "comando", "comando": t[m.start(1):].strip()}
    m = re.match(r"existe\s+(\S+)$", low)
    if m:
        return {"tipo": "archivo", "ruta": t.split(None, 1)[1].strip()}
    if low.startswith("pytest"):
        if low in ("pytest", "pytest en verde", "pytest verde", "pytest pasa"):
            return {"tipo": "comando", "comando": "pytest -q"}
        return {"tipo": "comando", "comando": t}
    for exe in ("npm test", "make ", "cargo test", "go test"):
        if low.startswith(exe):
            return {"tipo": "comando", "comando": t}
    return {"tipo": "revisor", "texto": t}


def parse_goal_texto(texto: str) -> dict:
    """La gramatica de `/goal`: un verbo (dale/no/parar/segui/estado) o el
    texto del goal, mas `hasta:`, `tope:`, `en:`, `raiz:`, `con:` en
    cualquier orden. `segui <nota>` deja la nota; `segui con: codex` deja
    `con`."""
    t = " ".join((texto or "").split())
    out = {"verbo": None, "texto": "", "hasta": None, "tope": {}, "en": None,
           "raiz": None, "con": None, "nota": None}
    if not t:
        return out
    primera = t.split(None, 1)[0].lower().strip(".,!")
    resto = t.split(None, 1)[1] if " " in t else ""
    if primera in VERBOS:
        out["verbo"] = primera
        t = resto
    partes = _RE_CLAVE.split(t)
    out["texto"] = partes[0].strip()
    for i in range(1, len(partes), 2):
        clave, valor = partes[i].lower(), partes[i + 1].strip()
        if clave == "tope":
            out["tope"] = parse_tope(valor)
        elif clave in ("hasta", "en", "raiz", "con"):
            out[clave] = valor or None
    if out["verbo"] == "segui" and out["texto"]:
        out["nota"] = out["texto"]
    return out


# --------------------------------------------------------------------------
# la propuesta heuristica, las compuertas del hook, los textos
# --------------------------------------------------------------------------

def propuesta_sin_modelo(texto: str, en: str | None) -> dict:
    """Cuando no hay cabeza frontera (goal privado, sin suscripcion): una
    propuesta por palabras clave, marcada con `aviso`. El chat la muestra
    igual y Pedro decide."""
    low = (texto or "").lower()
    familias = ["repo"] if en else []
    if any(w in low for w in ("busca", "buscar", "precio", "cuanto", "web", "http", "servicio")):
        familias.append("web")
    if any(w in low for w in ("instala", "install", "pip", "npm", "venv")):
        familias.append("instalar_en_goal")
    m = re.search(r"\bhasta\s+que\s+(.+)$", low)
    criterio = parse_criterio(m.group(1)) if m else {"tipo": "revisor", "texto": ""}
    return {"titulo": _title_from(texto), "criterio": criterio, "tope": dict(TOPE_DEFECTO),
            "familias": familias, "raices": [], "dominios": [],
            "plan": ["entender el pedido", "hacer el cambio minimo", "verificar", "resumir"],
            "manos": "claude",
            "aviso": "sin cabeza frontera disponible: propuesta heuristica, revisala"}


def compuertas_de(goal: dict[str, Any]) -> dict:
    """El JSON que lee el hook (goals_hook.py) en cada decision: el clon (o
    la carpeta de trabajo, bajo `dir_trabajo`: fuera de ~/.calipso), las
    raices, los dominios, la tabla de niveles y las preautorizaciones que
    Pedro dio A ESTE goal (decision 9)."""
    carpeta = dir_goal(goal["id"])
    cwd = goal.get("repo") or str(dir_trabajo(goal["id"]) / "trabajo")
    return {
        "goal": goal["id"],
        "clon": goal.get("repo"),
        "cwd": cwd,
        "raices": [os.path.expanduser(r) for r in (goal.get("compuertas") or {}).get("raices") or []],
        "dominios": list(goal.get("dominios") or []),
        "niveles": dict((goal.get("compuertas") or {}).get("niveles") or NIVEL_DE),
        "preautorizadas": list((goal.get("compuertas") or {}).get("preautorizadas") or []),
        "venv": str(pathlib.Path(cwd) / ".venv"),
        "registro": str(carpeta / "hook.jsonl"),
    }


def escribir_compuertas(goal: dict[str, Any]) -> pathlib.Path:
    p = dir_goal(goal["id"]) / "compuertas.json"
    _escribir_json_atomico(p, compuertas_de(goal))
    return p


def contexto_recortado(goal: dict[str, Any]) -> str:
    """Lo que entra al system del turno (spec seccion 2): estado, ultimo
    golpe y lo que espera. NUNCA el ledger."""
    filas = golpes(goal["id"])
    ultimo = filas[-1] if filas else None
    lines = [
        "=== Goal activo ===",
        f"id: {goal.get('id')}",
        f"titulo: {goal.get('title')}",
        f"estado: {goal.get('status')}",
        f"objetivo: {goal.get('objective')}",
    ]
    if ultimo:
        v = ultimo.get("veredicto_del_golpe") or {}
        lines.append(f"ultimo golpe: {ultimo.get('n')} ({ultimo.get('fase')}): "
                     f"{v.get('estado', '?')} - {v.get('resumen', '')}")
    espera = goal.get("espera") or {}
    if goal.get("status") == WAITING and espera:
        lines.append(f"espera: {espera.get('motivo', '')}"
                     + (f" - {espera['pregunta']}" if espera.get("pregunta") else ""))
    return "\n".join(lines)


def resumen(goal: dict[str, Any]) -> str:
    """`/goal estado` y los cierres del chat."""
    t = {**TOPE_DEFECTO, **(goal.get("tope") or {})}
    c = consumo(goal)
    lines = [
        f"goal {goal.get('id')}: {goal.get('title')}",
        f"estado: {goal.get('status')}",
        f"consumo: {c['golpes']}/{t['golpes']} golpes, {c['minutos']}/{t['minutos']} minutos, "
        f"{c['unidades']}/{t['unidades']} unidades",
        f"criterio: {json.dumps(goal.get('criterio') or {}, ensure_ascii=False)}",
        f"manos: {goal.get('manos')}; repo: {goal.get('repo') or 'sin repo'}",
    ]
    espera = goal.get("espera") or {}
    if goal.get("status") == WAITING and espera:
        lines.append("espera: " + json.dumps(espera, ensure_ascii=False))
    filas = golpes(goal["id"])
    if filas:
        v = filas[-1].get("veredicto_del_golpe") or {}
        lines.append(f"ultimo golpe {filas[-1].get('n')}: {v.get('estado', '?')} - {v.get('resumen', '')}")
    return "\n".join(lines)


def structured_output_de(stdout: str) -> dict | None:
    """El veredicto de una sesion `--output-format stream-json --json-schema`:
    `result.structured_output` de la ULTIMA linea `result`, o `result.result`
    parseado como JSON. None si no hay result o no es JSON."""
    ultimo = None
    for linea in (stdout or "").splitlines():
        linea = linea.strip()
        if not linea.startswith("{"):
            continue
        try:
            fila = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if fila.get("type") == "result":
            ultimo = fila
    if not ultimo:
        return None
    so = ultimo.get("structured_output")
    if isinstance(so, dict):
        return so
    try:
        v = json.loads(ultimo.get("result") or "")
        return v if isinstance(v, dict) else None
    except (TypeError, json.JSONDecodeError):
        return None
