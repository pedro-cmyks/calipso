#!/usr/bin/env python3
"""
calipso/skills.py - habilidades internas de Calipso.

Un skill es un musculo operativo: una rutina corta que especializa a un agente.
No es un modelo ni una identidad separada. El orquestador lo usa para darle a
cada agente una forma de trabajar mas concreta.
"""
from __future__ import annotations


REGISTRY: dict[str, dict] = {
    "planner": {
        "name": "Planificador",
        "prompt": (
            "Primero separa objetivo, restricciones, riesgos y pasos. "
            "Entrega un plan corto, ejecutable y con criterios de exito."
        ),
    },
    "researcher": {
        "name": "Investigador",
        "prompt": (
            "Distingue hechos, fuentes, supuestos y lagunas. Si falta evidencia, "
            "senala que habria que verificar antes de concluir."
        ),
    },
    "coder": {
        "name": "Editor de codigo",
        "prompt": (
            "Trabaja con cambios pequenos y coherentes. Respeta patrones del repo, "
            "minimiza superficie y piensa en pruebas/verificacion."
        ),
    },
    "reviewer": {
        "name": "Revisor",
        "prompt": (
            "Busca riesgos, regresiones, huecos de pruebas, estados falsamente "
            "verificados y controles que parezcan funcionar pero no hagan nada."
        ),
    },
    "writer": {
        "name": "Redactor",
        "prompt": (
            "Convierte el contenido en una respuesta clara, humana y breve. "
            "Mantiene una sola voz: Calipso."
        ),
    },
    "librarian": {
        "name": "Bibliotecario",
        "prompt": (
            "Clasifica conocimiento antes de guardarlo: identidad, handoff, core "
            "global, core de proyecto, episodio o telemetria. No promociones ruido."
        ),
    },
    "verifier": {
        "name": "Verificador",
        "prompt": (
            "No aceptes 'implementado' como 'funciona'. Define una prueba razonable, "
            "ejecutala si es posible y separa verificado de pendiente."
        ),
    },
    "synthesizer": {
        "name": "Sintetizador",
        "prompt": (
            "Une resultados parciales en una sola respuesta coherente para Pedro. "
            "No expongas el proceso interno salvo que ayude a decidir."
        ),
    },
}


def infer(agent: dict) -> str:
    """Elige un skill por tipo/rol/subtarea sin llamar a ningun modelo."""
    task_type = str(agent.get("type") or "").lower()
    role = str(agent.get("role") or "").lower()
    task = str(agent.get("task") or "").lower()
    text = f"{role} {task}"

    if any(w in text for w in ("biblioteca", "memoria", "handoff", "agents.md",
                               "calipso.md", "library.md", "recordar")):
        return "librarian"
    if task_type in {"repo", "code", "refactor", "exec"} or any(
            w in text for w in ("codigo", "code", "bug", "repo", "implementar")):
        return "coder"
    if any(w in text for w in ("verificar", "prueba", "tests", "riesgo", "revis")):
        return "verifier" if "verificar" in text or "prueba" in text else "reviewer"
    if task_type in {"analysis", "reasoning"} or any(
            w in text for w in ("plan", "estrategia", "descomponer")):
        return "planner"
    if task_type in {"summarize", "writing", "translate"} or any(
            w in text for w in ("redact", "resum", "escribir", "correo")):
        return "writer"
    if any(w in text for w in ("investig", "buscar", "web", "fuente")):
        return "researcher"
    if any(w in text for w in ("sintesis", "sintetiz", "combina")):
        return "synthesizer"
    return "synthesizer"


def prompt(skill_id: str) -> str:
    skill = REGISTRY.get(skill_id) or REGISTRY["synthesizer"]
    return f"Skill: {skill['name']}. {skill['prompt']}"
