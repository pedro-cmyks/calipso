#!/usr/bin/env python3
"""
calipso/goals.py - metas persistentes de Calipso.

Goal Mode es deliberadamente markdown/json-first: una meta debe sobrevivir
recargas, cambios de chat y procesos largos. Esta primera version no intenta
resolver el proyecto completo; da identidad, criterios, subtareas, evidencia y
estado activo para que Calipso pueda perseguir trabajo entre turnos.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import uuid
from typing import Any

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))

ACTIVE_STATES = {"active", "waiting", "blocked"}
FINAL_STATES = {"complete", "cancelled"}
VALID_STATES = ACTIVE_STATES | FINAL_STATES


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
    d = _goals_dir(project_root) / goal_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _active_file(project_root: str | None) -> pathlib.Path:
    return _goals_dir(project_root) / "active.txt"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _title_from(objective: str) -> str:
    clean = " ".join(objective.strip().split())
    if not clean:
        return "Meta sin titulo"
    return clean[:82] + ("..." if len(clean) > 82 else "")


def detect(text: str) -> str | None:
    """Extrae una meta desde lenguaje natural si Pedro la esta declarando."""
    clean = " ".join((text or "").strip().split())
    if not clean:
        return None
    patterns = [
        r"^meta\s*:\s*(.+)$",
        r"^mi objetivo es\s+(.+)$",
        r"^persigue esto hasta dejarlo listo\s*:\s*(.+)$",
        r"^quiero que sigas con esto hasta completarlo\s*:\s*(.+)$",
        r"^dejame listo\s+(.+)$",
        r"^déjame listo\s+(.+)$",
    ]
    for pattern in patterns:
        m = re.match(pattern, clean, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip(" .")
    return None


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
        "status": "active",
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
    p = _goal_dir(project_root, goal["id"]) / "goal.json"
    p.write_text(json.dumps(goal, ensure_ascii=False, indent=2), encoding="utf-8")


def load(project_root: str | None, goal_id: str) -> dict[str, Any] | None:
    p = _goal_dir(project_root, goal_id) / "goal.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def set_active(project_root: str | None, goal_id: str | None) -> None:
    p = _active_file(project_root)
    if goal_id:
        p.write_text(goal_id, encoding="utf-8")
    elif p.exists():
        p.unlink()


def active(project_root: str | None) -> dict[str, Any] | None:
    p = _active_file(project_root)
    if not p.exists():
        return None
    goal_id = p.read_text(encoding="utf-8").strip()
    goal = load(project_root, goal_id) if goal_id else None
    if not goal or goal.get("status") in FINAL_STATES:
        set_active(project_root, None)
        return None
    return goal


def list_goals(project_root: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    root = _goals_dir(project_root)
    for p in sorted(root.glob("*/goal.json"), key=lambda x: x.stat().st_mtime,
                    reverse=True)[:limit]:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def update(project_root: str | None, goal_id: str, **changes: Any) -> dict[str, Any] | None:
    goal = load(project_root, goal_id)
    if not goal:
        return None
    if "status" in changes and changes["status"]:
        status = str(changes["status"])
        if status not in VALID_STATES:
            raise ValueError(f"estado invalido: {status}")
        goal["status"] = status
        if status in FINAL_STATES:
            current = active(project_root)
            if current and current.get("id") == goal_id:
                set_active(project_root, None)
    for key in ("title", "objective", "criteria", "subtasks"):
        if key in changes and changes[key] is not None:
            goal[key] = changes[key]
    if changes.get("blocker"):
        goal.setdefault("blockers", []).append({
            "ts": _now(), "text": str(changes["blocker"])
        })
        goal["status"] = "blocked"
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
    # Auto-cierre si todos los criterios quedaron completos
    closed = check_auto_close(project_root, goal_id)
    return closed if closed else goal


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
    if status == "done":
        closed = check_auto_close(project_root, goal_id)
        if closed:
            return closed
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


def check_auto_close(project_root: str | None, goal_id: str) -> dict[str, Any] | None:
    """Cierra automáticamente la meta si todos los criterios tienen done=True.

    Devuelve la meta actualizada si fue cerrada, o None si no se cerró.
    Solo actúa sobre metas en estado activo (no final ni ya cerradas).
    """
    goal = load(project_root, goal_id)
    if not goal:
        return None
    if goal.get("status") in FINAL_STATES:
        return None
    criteria = goal.get("criteria") or []
    if not criteria:
        return None
    if not all(c.get("done") for c in criteria):
        return None

    goal["status"] = "complete"
    current = active(project_root)
    if current and current.get("id") == goal_id:
        set_active(project_root, None)
    goal.setdefault("evidence", []).append({
        "ts": _now(),
        "kind": "auto_close",
        "text": f"Meta cerrada automáticamente: todos los criterios ({len(criteria)}) completados.",
    })
    _write(project_root, goal)
    event(project_root, goal_id, "auto_closed",
          criteria_done=len(criteria), title=goal.get("title"))
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
