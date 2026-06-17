#!/usr/bin/env python3
"""
test_orchestrator.py — Agentes dinámicos: plan -> equipo concreto.
Verifica que cada subtarea se mapea a un modelo del tier pedido (disponible),
con su persona, y que el planner se normaliza. Sin llamar a ningún LLM real.
"""
from calipso import capabilities, orchestrator as orch

ALL = {k: True for k in capabilities.REGISTRY}


def fake_planner(_prompt):
    # simula la salida del LLM planner para una peticion de 2 partes
    return {"agents": [
        {"role": "planificador", "task": "disenar el enfoque", "tier": "frontier",
         "intensity": "ultra", "type": "reasoning", "quirk": "estrategico"},
        {"role": "programador", "task": "escribir el codigo", "tier": "frontier",
         "intensity": "think", "type": "code", "quirk": "limpio"},
        {"role": "redactor", "task": "resumir para el usuario", "tier": "small",
         "intensity": "fast", "type": "summarize", "quirk": "breve"},
    ], "synthesis": "junta plan, codigo y resumen"}


def main() -> int:
    fails = []

    def check(name, cond, extra=""):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' '+extra) if extra else ''}")
        if not cond:
            fails.append(name)

    p = orch.plan("haz un plan, escribe el codigo y resumelo", fake_planner)
    check("plan normaliza 3 agentes", len(p["agents"]) == 3)

    team = orch.build_team(p, ALL)
    check("equipo tiene 3 agentes", len(team["agents"]) == 3)
    by_role = {a["role"]: a for a in team["agents"]}

    # el programador (frontier, code) deberia caer en codex o un frontier de codigo
    prog = by_role["programador"]
    check("programador -> tier frontier", prog["tier"] == "frontier", f"({prog['persona']}:{prog['model_id']})")
    check("programador -> modelo de codigo", "code" in capabilities.REGISTRY[prog["model_id"]]["strengths"])
    # el redactor (small) -> tier small
    check("redactor -> tier small", by_role["redactor"]["tier"] == "small",
          f"({by_role['redactor']['persona']})")
    # cada agente tiene persona, modelo, intensidad
    check("agentes con persona+modelo+intensidad",
          all(a.get("persona") and a.get("model") and a.get("intensity") for a in team["agents"]))
    check("agentes con skill interno",
          all(a.get("skill") and a.get("skill_name") for a in team["agents"]))

    # system prompt incorpora rol y quirk
    sysp = orch.agent_system(prog, "Eres parte de Calipso.", "haz el cambio")
    check("system del agente incluye rol", "programador" in sysp and "limpio" in sysp)
    check("system del agente incluye skill", "Skill:" in sysp)
    check("system del agente incluye brief interno",
          "Brief interno del agente" in sysp and "haz el cambio" in sysp)

    # fallback: planner vacio -> 1 agente generico
    p2 = orch.plan("hola", lambda _: {"agents": []})
    check("planner vacio -> 1 agente", len(p2["agents"]) == 1)

    # sintesis prompt
    sp = orch.synthesis_prompt("peticion X", [{"persona": "Aristoteles", "role": "plan", "output": "el plan"}])
    check("synthesis incluye resultados", "Aristoteles" in sp and "el plan" in sp)

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: plan -> equipo dinamico (modelo por tier + persona + intensidad)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
