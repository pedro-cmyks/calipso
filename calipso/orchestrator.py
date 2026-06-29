#!/usr/bin/env python3
"""
calipso/orchestrator.py — Agentes DINÁMICOS (orquestación multi-agente).

En vez de un roster fijo, Calipso DESCOMPONE la petición y CREA un equipo de
agentes a medida por subtarea: cada agente recibe un rol, un quirk/estilo, un
modelo (por tier) y una intensidad. Luego se ejecutan y un sintetizador combina
sus resultados.

  plan(request, llm_json)  -> {"agents":[{role,task,tier,intensity,quirk,type}], "synthesis":...}
  build_team(plan, ...)    -> mapea cada agente a un MODELO concreto + persona
  agent_system(agent)      -> el system prompt con su personalidad y subtarea
  synthesis_prompt(...)     -> el prompt para combinar los resultados

El planner (un LLM) se INYECTA (llm_json) para poder testear sin modelo.
"""
from __future__ import annotations

from calipso import capabilities
from calipso import prompt_compiler
from calipso import skills
try:
    from calipso import resource_dispatcher as _rd
except Exception:
    _rd = None  # type: ignore[assignment]

PLANNER_SYSTEM = (
    "Eres el planificador de Calipso. Descompón la PETICIÓN en un EQUIPO PEQUEÑO "
    "de agentes (1 a 3) con subtareas claras. Para cada agente elige:\n"
    "  tier: small (fácil/rápido) | mid (normal) | frontier (difícil) | apex (lo más duro)\n"
    "  intensity: fast | balanced | think | ultra\n"
    "  type: trivial|translate|summarize|writing|reasoning|analysis|code|repo|agentic\n"
    "  quirk: un rasgo/estilo corto para ese agente\n"
    "Si la petición es simple, UN solo agente. Responde SOLO JSON.\n\n"
    "EJEMPLO:\n"
    "Peticion: arregla el bug de login y escribe un changelog amable.\n"
    'Respuesta: {"agents":[{"role":"ingeniero","task":"corregir el bug de login",'
    '"tier":"frontier","intensity":"think","type":"code","quirk":"meticuloso"},'
    '{"role":"redactor","task":"changelog amable","tier":"small","intensity":"fast",'
    '"type":"writing","quirk":"cercano"}],"synthesis":"junta el fix y el changelog"}\n\n'
    "Ahora planifica para:\n{request}\n\nJSON:"
)

VALID_TIERS = set(capabilities.TIER_RANK)
VALID_INTENS = set(capabilities.EFFORT)
VALID_TYPES = {"trivial", "translate", "summarize", "writing", "reasoning",
               "analysis", "code", "repo", "agentic", "exec"}


def plan(request: str, llm_json) -> dict:
    """Llama al planner (llm_json: prompt->dict) y normaliza el plan."""
    try:
        raw = llm_json(PLANNER_SYSTEM.replace("{request}", request))
        agents = raw.get("agents") or []
    except Exception:
        agents = []
    if not agents:  # fallback: un agente genérico
        agents = [{"role": "asistente", "task": request, "tier": "mid",
                   "intensity": "balanced", "type": "reasoning", "quirk": ""}]
    norm = []
    for a in agents[:3]:
        norm.append({
            "role": str(a.get("role", "agente"))[:40],
            "task": str(a.get("task", request))[:400],
            "tier": a.get("tier") if a.get("tier") in VALID_TIERS else "mid",
            "intensity": a.get("intensity") if a.get("intensity") in VALID_INTENS else "balanced",
            "type": a.get("type") if a.get("type") in VALID_TYPES else "reasoning",
            "quirk": str(a.get("quirk", ""))[:80],
        })
    return {"agents": norm, "synthesis": str(raw.get("synthesis", "") if agents else "")[:300]}


def pick_model(tier: str, task_type: str, available: dict,
               project_root: str | None = None):
    """El mejor modelo DISPONIBLE para ese tier+tarea (prefiere el tier pedido).

    Si resource_dispatcher está activo, filtra modelos locales sin RAM suficiente
    antes de elegir.
    """
    if _rd is not None:
        try:
            snap = _rd.ResourceSnapshot.take()
            # Descarta modelos locales que no tienen RAM suficiente ahora mismo.
            patched = dict(available)
            for key, m in capabilities.load_backends(project_root).items():
                if m.get("route") == "local" and patched.get(key):
                    model_name = m.get("model", "")
                    dec = _rd.gate(model_name, route="local", snap=snap)
                    if dec.action in ("reroute", "defer"):
                        patched[key] = False
            available = patched
        except Exception:
            pass  # si falla el diagnóstico, continúa sin filtrar

    backends = capabilities.load_backends(project_root)
    cands = [(k, m) for k, m in backends.items() if available.get(k)]
    if not cands:
        return None
    exact = [(k, m) for k, m in cands if m.get("tier") == tier]
    pool = exact or cands
    pool.sort(key=lambda km: (
        km[1].get("strengths", {}).get(task_type, 0.4)
        - 0.1 * km[1].get("cost", 1)), reverse=True)
    return pool[0]


def build_team(plan_obj: dict, available: dict, project_root: str | None = None,
               session: dict | None = None) -> dict:
    """Convierte el plan en un equipo concreto: cada agente con su MODELO real."""
    agents = []
    for a in plan_obj.get("agents", []):
        picked = pick_model(a["tier"], a["type"], available, project_root)
        if not picked:
            continue
        key, m = picked
        persona = m.get("persona", key)
        if session:
            persona = (session.get("agents", {}).get(key, {}).get("name")) or persona
        skill_id = skills.infer(a)
        agents.append({
            "persona": persona, "role": a["role"], "task": a["task"],
            "quirk": a["quirk"], "intensity": a["intensity"],
            "skill": skill_id, "skill_name": skills.REGISTRY[skill_id]["name"],
            "model_id": key, "route": m["route"], "client": m.get("client"),
            "model": m.get("model"), "tier": m.get("tier"),
        })
    return {"agents": agents, "synthesis": plan_obj.get("synthesis", "")}


def agent_system(agent: dict, base: str = "", request: str | None = None) -> str:
    """System prompt del agente: identidad + rol + quirk + subtarea."""
    bits = [base] if base else []
    bits.append(
        f"Eres {agent['persona']}, un agente de Calipso con el rol de "
        f"{agent['role']}." + (f" Estilo: {agent['quirk']}." if agent['quirk'] else ""))
    bits.append(prompt_compiler.agent_brief(agent, request))
    if agent.get("skill"):
        bits.append(skills.prompt(agent["skill"]))
    bits.append(f"Tu SUBTAREA: {agent['task']}\n"
                "Hazla bien y entrega solo tu parte, lista para integrarse.")
    return "\n".join(bits)


def synthesis_prompt(request: str, results: list[dict]) -> str:
    parts = [f"PETICIÓN ORIGINAL de Pedro:\n{request}\n",
             "RESULTADOS DE TU EQUIPO:"]
    for r in results:
        parts.append(f"\n[{r['persona']} — {r['role']}]\n{r['output']}")
    parts.append("\nCombina estos resultados en UNA respuesta final coherente "
                 "para Pedro. No menciones el proceso interno; entrega el resultado.")
    return "\n".join(parts)
