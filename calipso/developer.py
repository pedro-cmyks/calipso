#!/usr/bin/env python3
"""
calipso/developer.py - loop incremental de laboratorio.

Este modulo no intenta editar codigo automaticamente todavia. Su primera tarea
es convertir una meta en una siguiente accion auditable: job persistente,
artifact, evidencia y subtarea en progreso.
"""
from __future__ import annotations

from typing import Any

from calipso import goals, jobs


def _next_subtask(goal: dict[str, Any]) -> dict[str, Any] | None:
    for item in goal.get("subtasks") or []:
        if item.get("status") not in {"done", "cancelled"}:
            return item
    return None


def _artifact(goal: dict[str, Any], subtask: dict[str, Any]) -> str:
    criteria = "\n".join(
        f"- [{'x' if c.get('done') else ' '}] {c.get('text', '')}"
        for c in goal.get("criteria") or [])
    evidence = "\n".join(
        f"- {e.get('kind', 'nota')}: {e.get('text', '')}"
        for e in (goal.get("evidence") or [])[-8:])
    if not evidence:
        evidence = "- sin evidencia previa"
    return (
        f"# Siguiente accion\n\n"
        f"Meta: {goal.get('title')}\n\n"
        f"Objetivo: {goal.get('objective')}\n\n"
        f"Subtarea activa: {subtask.get('text')}\n\n"
        "## Criterios\n\n"
        f"{criteria}\n\n"
        "## Evidencia reciente\n\n"
        f"{evidence}\n\n"
        "## Instruccion operativa\n\n"
        "- Trabajar solo el incremento necesario para esta subtarea.\n"
        "- Guardar evidencia verificable al terminar.\n"
        "- No marcar la meta completa sin contrastar criterios.\n"
    )


def advance_goal(project_root: str | None, goal_id: str) -> dict[str, Any] | None:
    goal = goals.load(project_root, goal_id)
    if not goal:
        return None
    subtask = _next_subtask(goal)
    if not subtask:
        job = jobs.start(
            "goal_step", "Meta sin subtareas pendientes", project_root=project_root,
            goal_id=goal_id, subtask_id=None)
        jobs.write_artifact(
            project_root, job["id"], "next-action.md",
            "No quedan subtareas pendientes. Revisa criterios antes de cerrar la meta.")
        jobs.update(project_root, job["id"], status="done")
        goals.add_evidence(
            project_root, goal_id, "next_action",
            "No quedan subtareas pendientes; revisar criterios.", job_id=job["id"])
        return {"goal": goals.load(project_root, goal_id), "job": jobs.load(project_root, job["id"])}

    goals.set_subtask(project_root, goal_id, subtask["id"], "doing")
    goal = goals.load(project_root, goal_id) or goal
    subtask = next(
        (s for s in goal.get("subtasks", []) if s.get("id") == subtask["id"]),
        subtask)
    job = jobs.start(
        "goal_step", f"Siguiente accion: {subtask.get('text')}",
        project_root=project_root, goal_id=goal_id, subtask_id=subtask.get("id"))
    artifact = jobs.write_artifact(
        project_root, job["id"], "next-action.md", _artifact(goal, subtask),
        content_type="text/markdown")
    jobs.update(project_root, job["id"], status="done", artifact=artifact["name"])
    goals.add_evidence(
        project_root, goal_id, "next_action",
        f"Siguiente accion preparada: {subtask.get('text')}",
        job_id=job["id"], subtask_id=subtask.get("id"), artifact=artifact["name"])
    return {"goal": goals.load(project_root, goal_id), "job": jobs.load(project_root, job["id"])}
