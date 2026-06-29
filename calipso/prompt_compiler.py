#!/usr/bin/env python3
"""
calipso/prompt_compiler.py - lenguaje interno de Calipso.

El modelo no recibe solamente "lo que Pedro escribio". Calipso compila el turno:
identidad, memoria, intencion, proyecto, meta activa, herramientas y evidencia
esperada. Esta capa mantiene ese contrato pequeno, auditable y testeable.
"""
from __future__ import annotations

from typing import Any


def internal_contract(features: dict[str, Any] | None = None) -> str:
    features = features or {}
    task_type = features.get("type") or "chat"
    needs_repo = bool(features.get("needs_repo"))
    needs_web = bool(features.get("needs_web"))
    return "\n".join([
        "=== Lenguaje interno de Calipso ===",
        f"Tipo de tarea inferido: {task_type}.",
        "Traduce el pedido natural de Pedro a una tarea clara antes de responder.",
        "Usa memoria como contexto probabilistico y editable, no como verdad absoluta.",
        "Si un dato del perfil de Pedro esta desactualizado o contradicho por Pedro, prioriza lo nuevo.",
        "Manten una sola voz visible: Pedro habla con Calipso, no con cada backend.",
        "Detecta el idioma de cada turno y responde SIEMPRE en ese mismo idioma, aunque el resto del sistema este en español. Si el mensaje mezcla idiomas en la misma oracion, usa el idioma dominante.",
        "Tono: directo, natural, cercano. Como un colega de confianza que conoce bien a Pedro. "
        "Para chat conversacional: sin headers, sin listas innecesarias, sin frases de apertura como 'Claro,' o 'Por supuesto,'. "
        "Para tareas tecnicas: conciso, especifico, con evidencia cuando aplique.",
        "Actua antes de describir: si una tarea es directamente ejecutable, ejecutala. "
        "No describas el plan antes de actuar a menos que sea complejo o irreversible.",
        "Ante un roadblock tecnico: valida primero que hay disponible (que CLI esta instalado, "
        "que modelo responde, que dep existe), prueba alternativas si las hay, y reporta el "
        "resultado real — nunca digas 'depende de que X tengas' sin haber verificado primero.",
        "No muestres razonamiento interno; muestra decisiones, evidencia y pendientes cuando importen.",
        "Pide confirmacion antes de escribir, gastar, publicar, borrar o promover memoria sensible.",
        "Para cambios operativos, separa idea, implementado, verificado y pendiente.",
        f"Repo requerido: {'si' if needs_repo else 'no'}. Web requerida: {'si' if needs_web else 'no'}.",
    ])


def context_sections(system: str, identity: str = "", core: str = "",
                     recalled: list[dict[str, Any]] | None = None,
                     repo_brief: str = "", goal_block: str = "",
                     runtime: str = "", features: dict[str, Any] | None = None,
                     core_limit: int = 5000) -> list[tuple[str, str]]:
    """Devuelve secciones ordenadas de contexto: estable -> volatil -> estado."""
    sections: list[tuple[str, str]] = [("Sistema", system)]
    if identity:
        sections.append(("Constitucion de Calipso", identity))
    if core:
        sections.append(("Memoria nucleo", core[:core_limit]))
    sections.append(("Contrato interno", internal_contract(features)))
    if recalled:
        lines = "\n".join(
            f"- ({item.get('score')}) {item.get('text')}"
            for item in recalled
            if item.get("text"))
        if lines:
            sections.append(("Recuerdos relevantes", lines))
    if repo_brief:
        sections.append(("Repo", repo_brief))
    if goal_block:
        sections.append(("Meta activa", goal_block))
    if runtime:
        sections.append(("Estado operativo", runtime))
    return [(title, body) for title, body in sections if str(body or "").strip()]


def render_context(sections: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"=== {title} ===\n{body}" for title, body in sections)


def agent_brief(agent: dict[str, Any], request: str | None = None) -> str:
    """Brief estandar para agentes internos creados por el orquestador."""
    lines = [
        "=== Brief interno del agente ===",
        f"Rol: {agent.get('role') or 'agente'}.",
        f"Persona/modelo interno: {agent.get('persona') or agent.get('model_id') or 'sin asignar'}.",
        f"Subtarea: {agent.get('task') or 'sin subtarea'}.",
        f"Intensidad: {agent.get('intensity') or 'balanced'}.",
        f"Skill: {agent.get('skill_name') or agent.get('skill') or 'ninguno'}.",
        "Trabaja solo tu subtarea y entrega una salida integrable.",
        "Respeta permisos: no escribas, publiques, borres ni gastes sin aprobacion explicita.",
        "Si necesitas contexto que no tienes, dilo como supuesto o pendiente.",
        "Entrega evidencia, riesgo o prueba sugerida cuando aplique.",
    ]
    if request:
        lines.insert(1, f"Pedido original de Pedro: {request}.")
    return "\n".join(lines)


def compile_context(system: str, identity: str = "", core: str = "",
                    recalled: list[dict[str, Any]] | None = None,
                    repo_brief: str = "", goal_block: str = "",
                    runtime: str = "", features: dict[str, Any] | None = None,
                    core_limit: int = 5000) -> str:
    return render_context(context_sections(
        system, identity=identity, core=core, recalled=recalled,
        repo_brief=repo_brief, goal_block=goal_block, runtime=runtime,
        features=features, core_limit=core_limit))
