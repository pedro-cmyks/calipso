#!/usr/bin/env python3
"""
calipso/tools/commands.py - comandos allowlist para el loop desarrollador.

Nunca ejecuta texto libre ni usa shell. Cada comando tiene un id estable, una
lista de argumentos y una descripcion humana para que la UI pueda mostrarlo sin
exponer a Pedro a detalles innecesarios.
"""
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

from calipso import goals, jobs


def _python() -> str:
    return sys.executable or "python"


ALLOWLIST: dict[str, dict[str, Any]] = {
    "py_compile_core": {
        "title": "Compilar modulos principales",
        "description": "Verifica sintaxis de servidor, contexto, conectores, adjuntos, jobs, goals y developer loop.",
        "args": [
            "{python}", "-m", "py_compile",
            "calipso/server.py",
            "calipso/attachments.py",
            "calipso/backup.py",
            "calipso/chronology.py",
            "calipso/connectors.py",
            "calipso/developer.py",
            "calipso/doclinks.py",
            "calipso/github.py",
            "calipso/goals.py",
            "calipso/jobs.py",
            "calipso/librarian.py",
            "calipso/prompt_compiler.py",
            "calipso/routines.py",
            "calipso/skills.py",
            "calipso/verification.py",
            "calipso/tools/commands.py",
            "launch_calipso.py",
        ],
        "timeout": 120,
    },
    "ui_syntax": {
        "title": "Verificar UI web",
        "description": "Revisa sintaxis del JavaScript inline en calipso/web/index.html.",
        "args": ["{python}", "test_ui.py"],
        "timeout": 120,
    },
    "docs_check": {
        "title": "Verificar documentos guia",
        "description": "Revisa coherencia minima de SPEC, AGENTS, LIBRARY y RUNBOOK.",
        "args": ["{python}", "test_docs.py"],
        "timeout": 120,
    },
    "docs_links": {
        "title": "Validar links/rutas de docs",
        "description": "Verifica que las referencias internas (calipso/..., test_*.py) citadas en los docs existan.",
        "args": ["{python}", "check_doc_links.py"],
        "timeout": 60,
    },
    "test_attachments": {
        "title": "Probar adjuntos",
        "description": "Ejecuta test_attachments.py.",
        "args": ["{python}", "test_attachments.py"],
        "timeout": 120,
    },
    "test_proposals": {
        "title": "Probar propuestas",
        "description": "Ejecuta test_proposals.py.",
        "args": ["{python}", "test_proposals.py"],
        "timeout": 120,
    },
    "test_commands": {
        "title": "Probar runner allowlist",
        "description": "Ejecuta test_commands.py.",
        "args": ["{python}", "test_commands.py"],
        "timeout": 120,
    },
    "test_developer": {
        "title": "Probar developer loop",
        "description": "Ejecuta test_developer.py.",
        "args": ["{python}", "test_developer.py"],
        "timeout": 120,
    },
    "test_goals": {
        "title": "Probar Goal Mode",
        "description": "Ejecuta test_goals.py.",
        "args": ["{python}", "test_goals.py"],
        "timeout": 120,
    },
    "test_jobs": {
        "title": "Probar jobs persistentes",
        "description": "Ejecuta test_jobs.py.",
        "args": ["{python}", "test_jobs.py"],
        "timeout": 120,
    },
    "test_skills": {
        "title": "Probar skills internos",
        "description": "Ejecuta test_skills.py.",
        "args": ["{python}", "test_skills.py"],
        "timeout": 120,
    },
    "test_orchestrator": {
        "title": "Probar orquestador",
        "description": "Ejecuta test_orchestrator.py.",
        "args": ["{python}", "test_orchestrator.py"],
        "timeout": 120,
    },
    "test_verification": {
        "title": "Probar verificacion fuerte",
        "description": "Ejecuta test_verification.py.",
        "args": ["{python}", "test_verification.py"],
        "timeout": 120,
    },
    "test_librarian": {
        "title": "Probar bibliotecario",
        "description": "Ejecuta test_librarian.py.",
        "args": ["{python}", "test_librarian.py"],
        "timeout": 120,
    },
    "test_connectors": {
        "title": "Probar conectores y cuotas",
        "description": "Ejecuta test_connectors.py.",
        "args": ["{python}", "test_connectors.py"],
        "timeout": 120,
    },
    "test_launch": {
        "title": "Probar lanzamiento personal",
        "description": "Ejecuta test_launch.py.",
        "args": ["{python}", "test_launch.py"],
        "timeout": 120,
    },
    "test_prompt_compiler": {
        "title": "Probar lenguaje interno",
        "description": "Ejecuta test_prompt_compiler.py.",
        "args": ["{python}", "test_prompt_compiler.py"],
        "timeout": 120,
    },
}


def list_commands() -> list[dict[str, Any]]:
    return [
        {
            "id": key,
            "title": value["title"],
            "description": value["description"],
            "timeout": value.get("timeout", 120),
        }
        for key, value in ALLOWLIST.items()
    ]


def _args(command_id: str) -> list[str]:
    item = ALLOWLIST.get(command_id)
    if not item:
        raise KeyError(command_id)
    return [
        _python() if part == "{python}" else part
        for part in item["args"]
    ]


def run(project_root: str, command_id: str, goal_id: str | None = None,
        timeout: int | None = None) -> dict[str, Any]:
    item = ALLOWLIST.get(command_id)
    if not item:
        raise KeyError(command_id)
    args = _args(command_id)
    max_time = int(timeout or item.get("timeout") or 120)
    job = jobs.start(
        "command", item["title"], project_root=project_root,
        command_id=command_id, args=args, goal_id=goal_id)
    try:
        result = subprocess.run(
            args, cwd=project_root, text=True, encoding="utf-8",
            errors="replace", capture_output=True, timeout=max_time)
        status = "done" if result.returncode == 0 else "failed"
        jobs.write_artifact(project_root, job["id"], "stdout.txt", result.stdout or "")
        jobs.write_artifact(project_root, job["id"], "stderr.txt", result.stderr or "")
        jobs.write_artifact(project_root, job["id"], "result.json", {
            "command_id": command_id,
            "args": args,
            "returncode": result.returncode,
            "status": status,
        })
        jobs.update(
            project_root, job["id"], status=status,
            returncode=result.returncode, command_id=command_id)
        jobs.event(
            project_root, job["id"], status,
            returncode=result.returncode)
        if goal_id:
            goals.add_evidence(
                project_root, goal_id, "command",
                f"{item['title']} -> {status} (exit {result.returncode})",
                job_id=job["id"], command_id=command_id,
                artifact="stdout.txt")
        return {
            "job": jobs.load(project_root, job["id"]),
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "status": status,
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        jobs.write_artifact(project_root, job["id"], "stdout.txt", stdout)
        jobs.write_artifact(project_root, job["id"], "stderr.txt", stderr)
        jobs.write_artifact(project_root, job["id"], "result.json", {
            "command_id": command_id,
            "args": args,
            "timeout": max_time,
            "status": "timeout",
        })
        jobs.update(project_root, job["id"], status="timeout", command_id=command_id)
        jobs.event(project_root, job["id"], "timeout", timeout=max_time)
        if goal_id:
            goals.add_evidence(
                project_root, goal_id, "command",
                f"{item['title']} -> timeout ({max_time}s)",
                job_id=job["id"], command_id=command_id,
                artifact="stderr.txt")
        return {
            "job": jobs.load(project_root, job["id"]),
            "stdout": stdout,
            "stderr": stderr,
            "returncode": None,
            "status": "timeout",
        }


def result_summary(run_result: dict[str, Any]) -> str:
    job = run_result.get("job") or {}
    return json.dumps({
        "job_id": job.get("id"),
        "status": run_result.get("status"),
        "returncode": run_result.get("returncode"),
    }, ensure_ascii=False)
