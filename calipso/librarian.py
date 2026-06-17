#!/usr/bin/env python3
"""
calipso/librarian.py - inbox curado para memoria de largo plazo.

La memoria episodica puede acumular volumen, pero el core markdown debe crecer
por propuestas revisables. Este modulo guarda propuestas, registra aceptar/
descartar y promueve solo cuando Pedro o Calipso supervisado lo aprueba.
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


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _slug(project_root: str | None) -> str:
    if not project_root:
        return "global"
    p = pathlib.Path(project_root).resolve()
    return re.sub(r"[^a-z0-9]+", "-", str(p).lower()).strip("-")[:80] or "root"


def _store(project_root: str | None) -> pathlib.Path:
    d = CALIPSO_HOME / "projects" / _slug(project_root) / "librarian"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _inbox_file(project_root: str | None) -> pathlib.Path:
    return _store(project_root) / "inbox.json"


def _log_file(project_root: str | None) -> pathlib.Path:
    return _store(project_root) / "events.jsonl"


def _load(project_root: str | None) -> dict[str, Any]:
    p = _inbox_file(project_root)
    if not p.exists():
        return {"proposals": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        data = {"proposals": []}
    data.setdefault("proposals", [])
    return data


def _save(project_root: str | None, data: dict[str, Any]) -> None:
    _inbox_file(project_root).write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _event(project_root: str | None, action: str, **data: Any) -> dict[str, Any]:
    entry = {"ts": _now(), "action": action, **data}
    with open(_log_file(project_root), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _core_dir(project_root: str | None, scope: str) -> pathlib.Path:
    if scope == "global" or not project_root:
        d = CALIPSO_HOME / "global" / "core"
    else:
        d = pathlib.Path(project_root).resolve() / ".calipso" / "core"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_target(target: str | None) -> str:
    raw = (target or "aprendido").strip().lower()
    raw = re.sub(r"[^a-z0-9_-]+", "-", raw).strip("-")
    return raw or "aprendido"


def list_proposals(project_root: str | None = None,
                   status: str | None = "pending") -> list[dict[str, Any]]:
    proposals = _load(project_root)["proposals"]
    if status:
        proposals = [p for p in proposals if p.get("status") == status]
    return sorted(proposals, key=lambda p: p.get("updated_at", p.get("created_at", "")),
                  reverse=True)


def events(project_root: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    p = _log_file(project_root)
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except Exception:
            continue
    return rows


def propose(project_root: str | None, text: str, scope: str = "project",
            target: str = "aprendido", rationale: str | None = None,
            source: dict[str, Any] | None = None) -> dict[str, Any]:
    clean = " ".join((text or "").strip().split())
    if not clean:
        raise ValueError("propuesta vacia")
    scope = scope if scope in {"global", "project"} else "project"
    data = _load(project_root)
    proposal = {
        "id": f"mem_{uuid.uuid4().hex[:12]}",
        "text": clean,
        "scope": scope,
        "target": _safe_target(target),
        "rationale": rationale or "",
        "source": source or {},
        "status": "pending",
        "created_at": _now(),
        "updated_at": _now(),
    }
    data["proposals"].append(proposal)
    _save(project_root, data)
    _event(project_root, "proposed", proposal_id=proposal["id"],
           scope=scope, target=proposal["target"])
    return proposal


def update(project_root: str | None, proposal_id: str, **changes: Any) -> dict[str, Any] | None:
    data = _load(project_root)
    for proposal in data["proposals"]:
        if proposal.get("id") != proposal_id:
            continue
        for key in ("text", "scope", "target", "rationale"):
            if key in changes and changes[key] is not None:
                proposal[key] = changes[key]
        proposal["scope"] = proposal["scope"] if proposal["scope"] in {"global", "project"} else "project"
        proposal["target"] = _safe_target(proposal.get("target"))
        proposal["updated_at"] = _now()
        _save(project_root, data)
        _event(project_root, "updated", proposal_id=proposal_id)
        return proposal
    return None


def accept(project_root: str | None, proposal_id: str) -> dict[str, Any] | None:
    data = _load(project_root)
    for proposal in data["proposals"]:
        if proposal.get("id") != proposal_id:
            continue
        if proposal.get("status") != "pending":
            return proposal
        scope = proposal.get("scope") or "project"
        target = _safe_target(proposal.get("target"))
        core = _core_dir(project_root, scope) / f"{target}.md"
        existing = core.read_text(encoding="utf-8") if core.exists() else ""
        bullet = f"- {proposal['text']}"
        promoted = bullet not in existing
        if promoted:
            with open(core, "a", encoding="utf-8") as f:
                f.write(bullet + "\n")
        proposal["status"] = "accepted"
        proposal["promoted"] = promoted
        proposal["core_path"] = str(core)
        proposal["updated_at"] = _now()
        _save(project_root, data)
        _event(project_root, "accepted", proposal_id=proposal_id,
               scope=scope, target=target, promoted=promoted, core_path=str(core))
        return proposal
    return None


def discard(project_root: str | None, proposal_id: str,
            reason: str | None = None) -> dict[str, Any] | None:
    data = _load(project_root)
    for proposal in data["proposals"]:
        if proposal.get("id") != proposal_id:
            continue
        proposal["status"] = "discarded"
        proposal["discard_reason"] = reason or ""
        proposal["updated_at"] = _now()
        _save(project_root, data)
        _event(project_root, "discarded", proposal_id=proposal_id, reason=reason or "")
        return proposal
    return None


def suggest_from_text(project_root: str | None, text: str,
                      source: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Heuristica local: convierte lineas marcadas en propuestas de memoria."""
    proposals: list[dict[str, Any]] = []
    for raw in (text or "").splitlines():
        line = raw.strip(" -\t")
        if not line:
            continue
        low = line.lower()
        if low.startswith(("recordar:", "memoria:", "aprendizaje:")):
            line = line.split(":", 1)[1].strip()
        elif not any(k in low for k in ("pedro prefiere", "calipso debe", "este proyecto", "recordar")):
            continue
        scope = "global" if "pedro" in low or "global" in low else "project"
        proposals.append(propose(
            project_root, line, scope=scope, target="aprendido",
            rationale="sugerido por bibliotecario local", source=source))
    return proposals
