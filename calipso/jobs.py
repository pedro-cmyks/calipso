#!/usr/bin/env python3
"""
calipso/jobs.py - registro persistente de trabajos largos.

Primera version: no intenta ser un scheduler completo. Da identidad, estado y
eventos persistidos a procesos largos para que la UI y Calipso puedan reconstruir
que estaba pasando aunque el usuario cambie de panel o recargue.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import uuid
from typing import Any

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))


def _slug(project_root: str | None) -> str:
    if not project_root:
        return "global"
    p = pathlib.Path(project_root).resolve()
    return str(p).replace(":", "").replace("\\", "-").replace("/", "-").strip("-")


def _jobs_dir(project_root: str | None) -> pathlib.Path:
    d = CALIPSO_HOME / "projects" / _slug(project_root) / "jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _job_dir(project_root: str | None, job_id: str) -> pathlib.Path:
    d = _jobs_dir(project_root) / job_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def start(kind: str, title: str, project_root: str | None = None,
          **data: Any) -> dict[str, Any]:
    job = {
        "id": f"job_{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "title": title,
        "status": "running",
        "created_at": _now(),
        "updated_at": _now(),
        **data,
    }
    d = _job_dir(project_root, job["id"])
    (d / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2),
                                encoding="utf-8")
    event(project_root, job["id"], "start", title=title, kind=kind, **data)
    return job


def load(project_root: str | None, job_id: str) -> dict[str, Any] | None:
    p = _job_dir(project_root, job_id) / "job.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def update(project_root: str | None, job_id: str, status: str | None = None,
           **data: Any) -> dict[str, Any] | None:
    job = load(project_root, job_id)
    if not job:
        return None
    if status:
        job["status"] = status
    job.update(data)
    job["updated_at"] = _now()
    p = _job_dir(project_root, job_id) / "job.json"
    p.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    return job


def event(project_root: str | None, job_id: str, action: str,
          **data: Any) -> dict[str, Any]:
    entry = {"ts": _now(), "job_id": job_id, "action": action, **data}
    p = _job_dir(project_root, job_id) / "events.jsonl"
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def events(project_root: str | None, job_id: str, limit: int = 200) -> list[dict[str, Any]]:
    p = _job_dir(project_root, job_id) / "events.jsonl"
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def artifact_path(project_root: str | None, job_id: str, name: str) -> pathlib.Path:
    safe = name.replace("\\", "_").replace("/", "_").replace("..", "_").strip("._")
    if not safe:
        safe = "artifact.txt"
    return _job_dir(project_root, job_id) / "artifacts" / safe


def write_artifact(project_root: str | None, job_id: str, name: str,
                   content: str | bytes | dict | list,
                   content_type: str | None = None) -> dict[str, Any]:
    p = artifact_path(project_root, job_id, name)
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, (dict, list)):
        raw = json.dumps(content, ensure_ascii=False, indent=2)
        content_type = content_type or "application/json"
        p.write_text(raw, encoding="utf-8")
        size = len(raw.encode("utf-8"))
    elif isinstance(content, bytes):
        p.write_bytes(content)
        size = len(content)
        content_type = content_type or "application/octet-stream"
    else:
        p.write_text(content, encoding="utf-8")
        size = len(content.encode("utf-8"))
        content_type = content_type or "text/plain"
    meta = {
        "name": p.name,
        "path": str(p),
        "content_type": content_type,
        "size": size,
        "updated_at": _now(),
    }
    event(project_root, job_id, "artifact", artifact=meta)
    return meta


def artifacts(project_root: str | None, job_id: str) -> list[dict[str, Any]]:
    d = _job_dir(project_root, job_id) / "artifacts"
    if not d.exists():
        return []
    out = []
    for p in sorted(d.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if not p.is_file():
            continue
        out.append({
            "name": p.name,
            "path": str(p),
            "size": p.stat().st_size,
            "updated_at": datetime.datetime.fromtimestamp(
                p.stat().st_mtime).isoformat(timespec="seconds"),
        })
    return out


def read_artifact(project_root: str | None, job_id: str, name: str,
                  max_bytes: int = 500_000) -> bytes:
    p = artifact_path(project_root, job_id, name)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(name)
    if p.stat().st_size > max_bytes:
        raise ValueError("artifact demasiado grande")
    return p.read_bytes()


def list_jobs(project_root: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    root = _jobs_dir(project_root)
    for p in sorted(root.glob("*/job.json"), key=lambda x: x.stat().st_mtime,
                    reverse=True)[:limit]:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out
