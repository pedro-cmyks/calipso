#!/usr/bin/env python3
"""
calipso/developer.py - loop incremental de laboratorio.

Convierte una meta en accion auditable (advance_goal) y, opcionalmente,
genera un brief listo para que un agente de suscripcion produzca un diff
real (draft_brief). El brief se pasa a server.py que invoca al CLI.
"""
from __future__ import annotations

import pathlib
from typing import Any

from calipso import goals, jobs

_DRAFT_SYSTEM = """\
Eres un agente de codigo trabajando en el proyecto Calipso.
Tu unica tarea es implementar la subtarea indicada editando el archivo dado.

FORMATO DE RESPUESTA — MUY IMPORTANTE:
- Tu respuesta es el CONTENIDO COMPLETO del archivo, listo para escribir en disco.
- PRIMERA LINEA: la primera linea real del archivo (shebang, import, comentario, etc.).
- ULTIMA LINEA: la ultima linea real del archivo.
- CERO texto antes ni despues del contenido del archivo.
- CERO bloques markdown (sin ```, sin ```python, sin ```).
- CERO explicaciones, encabezados, ni frases como "Aqui esta el archivo".
- Si el archivo empieza con "#!/usr/bin/env python3", tu respuesta empieza con eso.
- Si el archivo termina con un salto de linea, tu respuesta tambien.

Reglas de edicion:
- Implementa SOLO lo que la subtarea pide. No toques nada mas.
- Mantén el estilo, indentacion y estructura del archivo original.
- Si el archivo no necesita cambios, devuelve el archivo original exacto.
"""


import re as _re

# Patrones que indican que una línea es código real (no prose de LLM)
_CODE_START = _re.compile(
    r'^(#!/|#|from |import |"""|\'\'\''
    r'|class |def |async def |@|if |for |while |try:|with |raise |return '
    r'|[A-Z_][A-Z_0-9]* ?=|[a-z_][a-z_0-9]* ?=|\s*$)'
)


def _strip_fences(text: str) -> str:
    """Elimina bloques markdown y prose inicial que Claude añade pese al prompt."""
    lines = text.splitlines(keepends=True)

    # Caso 1: hay fences explícitos — extraer contenido interno
    fence_start, fence_end = None, None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if fence_start is None and s.startswith("```"):
            fence_start = i
        elif fence_start is not None and s.startswith("```"):
            fence_end = i
            break
    if fence_start is not None and fence_end is not None and fence_end > fence_start:
        return "".join(lines[fence_start + 1:fence_end])

    # Caso 2: no hay fences pero hay prose antes del código.
    # Si la primera línea no-blank NO es código, buscamos la primera que sí lo sea.
    first_nonblank = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if first_nonblank is None:
        return text
    if _CODE_START.match(lines[first_nonblank]):
        return text  # ya empieza con código, no tocar

    # Primera línea es prose → buscar primer línea de código
    for i in range(first_nonblank + 1, len(lines)):
        if lines[i].strip() and _CODE_START.match(lines[i]):
            return "".join(lines[i:])

    return text


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


def draft_brief(
    project_root: str | None,
    goal_id: str,
    file_path: str,
) -> dict[str, Any] | None:
    """Prepara el brief para que un agente genere el contenido nuevo del archivo.

    Devuelve {system, user_msg, path, current_content, subtask, job} o None si
    la meta no existe o no tiene subtarea activa/pendiente.
    El llamador (server.py) invoca al CLI y crea la propuesta.
    """
    goal = goals.load(project_root, goal_id)
    if not goal:
        return None

    subtask = next(
        (s for s in goal.get("subtasks", []) if s.get("status") == "doing"),
        None,
    ) or _next_subtask(goal)
    if not subtask:
        return None

    root = pathlib.Path(project_root or ".")
    target = root / file_path
    current = ""
    if target.exists() and target.is_file():
        try:
            current = target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return None  # binario, no editable

    criteria = "\n".join(
        f"- [{'x' if c.get('done') else ' '}] {c.get('text', '')}"
        for c in goal.get("criteria") or [])
    evidence = "\n".join(
        f"- {e.get('kind', 'nota')}: {e.get('text', '')}"
        for e in (goal.get("evidence") or [])[-6:]) or "- sin evidencia previa"

    user_msg = (
        f"Meta: {goal.get('title')}\n"
        f"Objetivo: {goal.get('objective')}\n\n"
        f"Subtarea a implementar: {subtask.get('text')}\n\n"
        f"Criterios de la meta:\n{criteria}\n\n"
        f"Evidencia reciente:\n{evidence}\n\n"
        f"Archivo a editar: {file_path}\n\n"
        f"Contenido actual:\n```\n{current}\n```\n\n"
        "Devuelve el contenido completo del archivo con los cambios necesarios."
    )

    job = jobs.start(
        "goal_draft", f"Borrador: {subtask.get('text')}",
        project_root=project_root, goal_id=goal_id,
        subtask_id=subtask.get("id"), file_path=file_path)

    return {
        "system": _DRAFT_SYSTEM,
        "user_msg": user_msg,
        "path": file_path,
        "current_content": current,
        "subtask": subtask,
        "job": job,
    }
