#!/usr/bin/env python3
"""
calipso/verification.py - recomendador y runner de verificacion por tipo de cambio.
"""
from __future__ import annotations

import datetime
from typing import Any

from calipso import goals, jobs
from calipso.tools import commands


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _add(plan: list[dict[str, str]], command_id: str, reason: str) -> None:
    if any(item["command_id"] == command_id for item in plan):
        return
    found = {c["id"]: c for c in commands.list_commands()}.get(command_id, {})
    plan.append({
        "command_id": command_id,
        "title": found.get("title", command_id),
        "reason": reason,
    })


def recommend(files: list[dict[str, Any]] | None = None,
              proposals: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    files = files or []
    proposals = proposals or []
    paths = [str(f.get("path") or "") for f in files]
    paths.extend(str(p.get("path") or "") for p in proposals)
    paths = [p for p in paths if p]
    plan: list[dict[str, str]] = []
    types: set[str] = set()

    for path in paths:
        lower = path.lower()
        if lower.endswith(".py"):
            types.add("python")
            _add(plan, "py_compile_core", f"{path} es Python")
        if lower.startswith("calipso/web/") or lower.endswith((".html", ".css", ".js", ".ts", ".tsx", ".jsx")):
            types.add("frontend")
            _add(plan, "ui_syntax", f"{path} toca UI/frontend")
        if lower.endswith((".md", ".txt")) or lower in {"agents.md", "spec.md", "library.md", "runbook.md", "calipso.md"}:
            types.add("docs")
            _add(plan, "docs_check", f"{path} toca documentacion")
            _add(plan, "docs_links", f"{path} toca documentacion: validar links/rutas")
        if "attachments" in lower:
            types.add("attachments")
            _add(plan, "test_attachments", f"{path} toca adjuntos")
        if "proposal" in lower or "proposals" in lower:
            types.add("proposals")
            _add(plan, "test_proposals", f"{path} toca propuestas")
        if "commands" in lower or "tools/" in lower:
            types.add("commands")
            _add(plan, "test_commands", f"{path} toca runner allowlist")
        if "developer" in lower:
            types.add("developer")
            _add(plan, "test_developer", f"{path} toca developer loop")
        if "goals" in lower:
            types.add("goals")
            _add(plan, "test_goals", f"{path} toca Goal Mode")
        if "jobs" in lower:
            types.add("jobs")
            _add(plan, "test_jobs", f"{path} toca jobs")
        if "skills" in lower:
            types.add("skills")
            _add(plan, "test_skills", f"{path} toca skills")
        if "orchestrator" in lower:
            types.add("orchestrator")
            _add(plan, "test_orchestrator", f"{path} toca orquestador")
        if "verification" in lower:
            types.add("verification")
            _add(plan, "test_verification", f"{path} toca verificacion fuerte")
        if "librarian" in lower or "memory" in lower or "chronology" in lower or "cronologia" in lower:
            types.add("librarian")
            _add(plan, "test_librarian", f"{path} toca bibliotecario/memoria")
            # test_memory.py es de los de main(): pytest no colecta nada de el.
            # Sin esta linea, tocar la memoria da verde sin correr una sola
            # assertion sobre DONDE aterriza lo que Calipso recuerda.
            _add(plan, "test_memoria_ambito",
                 f"{path} toca en que ambito aterriza lo que se recuerda")
            # test_memoria_carta.py es de los mismos: pytest no colecta nada
            # de test_memory.py, asi que sin esta linea tocar la carta de un
            # departamento tambien daria verde sin correr sus tests.
            _add(plan, "test_memoria_carta",
                 f"{path} toca la carta que Pedro le escribe a un departamento")
        if "prompt_compiler" in lower or "context" in lower or "pedro-perfil" in lower or "pedro-cronologia" in lower:
            types.add("prompt_compiler")
            _add(plan, "test_prompt_compiler", f"{path} toca lenguaje interno/contexto")
            # test_prompt_compiler es de los de main(): pytest no colecta nada
            # de el. Sin esta linea, tocar prompt_compiler.py y correr la
            # verificacion que el repo indica da verde sin ejecutar una sola
            # de las assertions que cuidan que la lista de departamentos salga
            # del registro y no de tres nombres escritos a mano.
            _add(plan, "test_contrato_departamentos",
                 f"{path} toca los departamentos que el contrato le nombra al modelo")
        if "connectors" in lower or "capabilities" in lower or "costs" in lower or "config" in lower:
            types.add("connectors")
            _add(plan, "test_connectors", f"{path} toca conectores/cuotas")
        if "launch" in lower or "runbook" in lower or "manifest" in lower or "sw.js" in lower:
            types.add("launch")
            _add(plan, "test_launch", f"{path} toca lanzamiento personal")
        if "calipso/permisos/" in lower or "test_permisos" in lower:
            types.add("permisos")
            # el motor de permisos aparecia SOLO dentro de la rama del
            # inbox, que corre test_inbox: tocar `almacen.py` no disparaba
            # nada y tocar `motor.py` corria los tests del agregador, no los
            # del motor. El corte del no permanente niega antes de crear la
            # solicitud -- no deja item en ninguna bandeja -- asi que es
            # justo lo que un verde sin assertions no atraparia.
            # la condicion tiene dos mitades porque el paquete y sus tests
            # no comparten prefijo: `calipso/permisos/` cubre el motor, y
            # `test_permisos` cubre `test_permisos.py`/`test_permisos_server.py`,
            # que viven en la raiz del repo, no adentro de la carpeta.
            _add(plan, "test_permisos", f"{path} toca el motor de permisos")
        if ("inbox" in lower or "economia/bus.py" in lower
                or "economia/cola.py" in lower or "permisos/motor.py" in lower
                or "librarian.py" in lower):
            types.add("inbox")
            # los cuatro adaptadores (descriptor()/como_items()) viven al
            # lado de cada origen, no en calipso/inbox.py: tocar el codigo
            # mas propenso a romper el contrato del inbox tiene que
            # disparar sus tests igual que tocar el agregador.
            _add(plan, "test_inbox", f"{path} toca el inbox")

    if not plan:
        _add(plan, "py_compile_core", "verificacion base si no hay cambios clasificados")
        types.add("base")

    return {
        "generated_at": _now(),
        "change_types": sorted(types),
        "files": paths,
        "commands": plan,
        "summary": " + ".join(item["command_id"] for item in plan),
    }


def run_plan(project_root: str, plan: dict[str, Any],
             goal_id: str | None = None) -> dict[str, Any]:
    command_items = plan.get("commands") or []
    title = f"Verificacion fuerte: {plan.get('summary') or 'plan'}"
    job = jobs.start(
        "verification_plan", title, project_root=project_root,
        goal_id=goal_id, commands=[c.get("command_id") for c in command_items],
        change_types=plan.get("change_types") or [])
    results: list[dict[str, Any]] = []
    status = "done"
    for item in command_items:
        command_id = item.get("command_id")
        if not command_id:
            continue
        result = commands.run(project_root, command_id, goal_id)
        result_job = result.get("job") or {}
        entry = {
            "command_id": command_id,
            "title": item.get("title"),
            "reason": item.get("reason"),
            "status": result.get("status"),
            "returncode": result.get("returncode"),
            "child_job_id": result_job.get("id"),
        }
        results.append(entry)
        jobs.event(project_root, job["id"], "command_result", **entry)
        if result.get("status") != "done":
            status = "failed"
    report = {
        "status": status,
        "plan": plan,
        "results": results,
        "generated_at": _now(),
    }
    lines = [
        f"# Verificacion fuerte",
        "",
        f"Estado: {status}",
        f"Tipos: {', '.join(plan.get('change_types') or []) or 'base'}",
        "",
        "## Comandos",
    ]
    for r in results:
        lines.append(
            f"- {r['command_id']}: {r['status']} (exit {r['returncode']}) - {r.get('reason') or ''}")
    jobs.write_artifact(project_root, job["id"], "verification-report.json", report)
    jobs.write_artifact(project_root, job["id"], "verification-report.md", "\n".join(lines))
    jobs.update(project_root, job["id"], status=status, results=results)
    jobs.event(project_root, job["id"], status)
    if goal_id:
        goals.add_evidence(
            project_root, goal_id, "verification",
            f"Verificacion fuerte -> {status}",
            job_id=job["id"], artifact="verification-report.md", results=results)
    return {"job": jobs.load(project_root, job["id"]), "report": report}
