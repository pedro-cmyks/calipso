#!/usr/bin/env python3
"""
calipso/tools/commands.py - comandos allowlist para el loop desarrollador.

Nunca ejecuta texto libre ni usa shell. Cada comando tiene un id estable, una
lista de argumentos y una descripcion humana para que la UI pueda mostrarlo sin
exponer a Pedro a detalles innecesarios.

Dos cosas del allowlist que no eran ciertas hasta este cambio, verificadas
con un repo de prueba antes de arreglarlas:

1. La mayoria de las entradas (py_compile_core, ui_syntax, docs_check,
   docs_links, toda la familia test_*) traen argumentos RELATIVOS
   ("test_ui.py", "calipso/server.py") y `run()` las corria con
   `cwd=project_root`. Como `project_root` es lo que el catastro (y antes,
   `/api/project/open`) haya abierto, un repo ajeno con su propio
   "test_ui.py" en la raiz se ejecutaba EN VEZ del test_ui.py de Calipso --
   confirmado corriendo `commands.run(<repo ajeno>, "ui_syntax")` antes de
   este arreglo. Estos comandos existen para validar el codigo de Calipso,
   no el proyecto que este abierto; ahora corren siempre con
   `cwd=CALIPSO_REPO_ROOT`, sin importar que `project_root` se les pase.
2. Los cuatro comandos de git (`git_status`, `git_diff`, `git_diff_staged`,
   `git_log`) SI tienen que correr contra `project_root` -- ese es su punto
   -- pero `git` ejecuta lo que declare el `.git/config` del repo que lee.
   Un `.git/config` con `core.fsmonitor = "comando; false"` corre ese
   comando en un `git status` normal, sin pedir permiso -- confirmado con
   un repo de prueba antes de este arreglo, y tambien confirmado que
   `commands.run(<repo con ese config>, "git_status")` lo disparaba. Ahora
   estos cuatro van con `-c core.fsmonitor= -c diff.external=
   -c core.pager=cat` y `GIT_CONFIG_GLOBAL=/dev/null` en el entorno.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from typing import Any

from calipso import goals, jobs

# Raiz del repo de Calipso (el que contiene el paquete calipso/): dos
# niveles arriba de este archivo (calipso/tools/commands.py). Los comandos
# de "scope": "calipso" siempre corren aca, nunca en project_root -- ver
# el punto 1 del docstring de arriba.
CALIPSO_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


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
    "test_streaming": {
        "title": "Probar streaming",
        "description": "Ejecuta test_streaming.py.",
        "args": ["{python}", "test_streaming.py"],
        "timeout": 120,
    },
    "test_capabilities": {
        "title": "Probar ruteo de modelos",
        "description": "Ejecuta test_capabilities.py.",
        "args": ["{python}", "test_capabilities.py"],
        "timeout": 120,
    },
    "test_memory": {
        "title": "Probar memoria hibrida",
        "description": "Ejecuta test_memory.py (requiere Ollama con bge-m3).",
        "args": ["{python}", "test_memory.py"],
        "timeout": 180,
    },
    "test_routines": {
        "title": "Probar rutinas y backup",
        "description": "Ejecuta test_routines.py.",
        "args": ["{python}", "test_routines.py"],
        "timeout": 120,
    },
    "test_github": {
        "title": "Probar conector GitHub",
        "description": "Ejecuta test_github.py.",
        "args": ["{python}", "test_github.py"],
        "timeout": 120,
    },
    "test_doclinks": {
        "title": "Probar validador de links",
        "description": "Ejecuta test_doclinks.py.",
        "args": ["{python}", "test_doclinks.py"],
        "timeout": 60,
    },
    "test_sessions": {
        "title": "Probar sesiones y rosters",
        "description": "Ejecuta test_sessions.py.",
        "args": ["{python}", "test_sessions.py"],
        "timeout": 120,
    },
    "test_learning": {
        "title": "Probar aprendizaje y overrides",
        "description": "Ejecuta test_learning.py.",
        "args": ["{python}", "test_learning.py"],
        "timeout": 120,
    },
    "test_all": {
        "title": "Correr todos los tests",
        "description": "Corre la suite completa de scripts de test (excluye test_memory que requiere Ollama vivo).",
        "args": [
            "{python}", "-c",
            (
                "import subprocess, sys\n"
                "tests = [\n"
                "  'test_streaming.py','test_capabilities.py','test_orchestrator.py',\n"
                "  'test_skills.py','test_jobs.py','test_goals.py','test_developer.py',\n"
                "  'test_commands.py','test_verification.py','test_librarian.py',\n"
                "  'test_connectors.py','test_launch.py','test_prompt_compiler.py',\n"
                "  'test_proposals.py','test_attachments.py','test_sessions.py',\n"
                "  'test_learning.py','test_routines.py','test_github.py','test_doclinks.py',\n"
                "]\n"
                "failed=[]\n"
                "for t in tests:\n"
                "  r=subprocess.run([sys.executable,t],capture_output=True,text=True)\n"
                "  status='OK' if r.returncode==0 else 'FAIL'\n"
                "  print(f'[{status}] {t}')\n"
                "  if r.returncode!=0: failed.append(t); print(r.stdout[-400:])\n"
                "print(f'\\n{len(tests)-len(failed)}/{len(tests)} OK')\n"
                "sys.exit(len(failed))\n"
            ),
        ],
        "timeout": 300,
    },
    "git_status": {
        "title": "Git status",
        "description": "Muestra el estado actual del repositorio (archivos modificados, staged, untracked).",
        "args": ["git", "status"],
        "timeout": 10,
        # a diferencia de todo lo de arriba, este SI corre contra el
        # proyecto que este abierto -- es su punto -- y por eso lleva el
        # blindaje de git en _args()/run().
        "scope": "project",
    },
    "git_diff": {
        "title": "Git diff",
        "description": "Muestra los cambios sin stagear en el repositorio.",
        "args": ["git", "diff"],
        "timeout": 10,
        "scope": "project",
    },
    "git_diff_staged": {
        "title": "Git diff staged",
        "description": "Muestra los cambios ya en staging area (listos para commit).",
        "args": ["git", "diff", "--staged"],
        "timeout": 10,
        "scope": "project",
    },
    "git_log": {
        "title": "Git log reciente",
        "description": "Muestra los ultimos 10 commits del repositorio.",
        "args": ["git", "log", "--oneline", "-10"],
        "timeout": 10,
        "scope": "project",
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
    args = [
        _python() if part == "{python}" else part
        for part in item["args"]
    ]
    if args and args[0] == "git":
        # blindaje contra lo que declare el .git/config del repo que se
        # lee: ver el punto 2 del docstring del modulo.
        args = ["git", "-c", "core.fsmonitor=", "-c", "diff.external=",
                "-c", "core.pager=cat", *args[1:]]
    return args


def _cwd_para(command_id: str, project_root: str) -> str:
    """Los comandos que validan el codigo de Calipso (compilar, tests,
    docs) corren siempre en el repo de Calipso, nunca en project_root: ver
    el punto 1 del docstring del modulo. Los de "scope": "project" (los
    cuatro de git) son al reves -- su punto es leer el proyecto abierto."""
    item = ALLOWLIST[command_id]
    if item.get("scope") == "project":
        return project_root
    return str(CALIPSO_REPO_ROOT)


def _env_seguro(args: list[str]) -> dict[str, str]:
    env = os.environ.copy()
    if args and args[0] == "git":
        env["GIT_CONFIG_GLOBAL"] = os.devnull
    return env


def run(project_root: str, command_id: str, goal_id: str | None = None,
        timeout: int | None = None) -> dict[str, Any]:
    item = ALLOWLIST.get(command_id)
    if not item:
        raise KeyError(command_id)
    args = _args(command_id)
    cwd = _cwd_para(command_id, project_root)
    env = _env_seguro(args)
    max_time = int(timeout or item.get("timeout") or 120)
    job = jobs.start(
        "command", item["title"], project_root=project_root,
        command_id=command_id, args=args, goal_id=goal_id)
    try:
        result = subprocess.run(
            args, cwd=cwd, env=env, text=True, encoding="utf-8",
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
