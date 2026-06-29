#!/usr/bin/env python3
"""
test_prompt_compiler.py - contrato de lenguaje interno/context engineering.
"""
from __future__ import annotations

from calipso import prompt_compiler


def check(name: str, cond: bool, fails: list[str]) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def main() -> int:
    fails: list[str] = []
    ctx = prompt_compiler.compile_context(
        "Eres Calipso.",
        identity="Pedro habla con Calipso.",
        core="Pedro prefiere comunicacion directa.",
        recalled=[{"score": 0.91, "text": "Atlas es importante para Pedro."}],
        repo_brief="branch main, cambios pendientes",
        goal_block="Meta: terminar Calipso",
        runtime="local listo",
        features={"type": "code", "needs_repo": True, "needs_web": False},
        core_limit=1000,
    )
    check("incluye sistema", "Eres Calipso." in ctx, fails)
    check("incluye memoria nucleo", "Pedro prefiere comunicacion directa." in ctx, fails)
    check("incluye contrato interno", "Lenguaje interno de Calipso" in ctx, fails)
    check("contrato trata memoria como editable", "no como verdad absoluta" in ctx, fails)
    check("incluye recuerdos", "Atlas es importante" in ctx, fails)
    check("incluye repo/meta/runtime", all(x in ctx for x in (
        "branch main", "Meta: terminar Calipso", "local listo")), fails)
    check("orden estable antes de volatil", ctx.index("Memoria nucleo") < ctx.index("Recuerdos relevantes"), fails)

    contract = prompt_compiler.internal_contract({"needs_repo": True, "needs_web": True})
    check("marca repo y web", "Repo requerido: si. Web requerida: si." in contract, fails)
    check("contrato multilingue", "idioma" in contract and "mismo idioma" in contract, fails)
    brief = prompt_compiler.agent_brief({
        "role": "revisor",
        "persona": "Heraclito",
        "task": "buscar riesgos",
        "intensity": "think",
        "skill_name": "Revisor",
    }, "revisa este cambio")
    check("brief de agente incluye subtarea", "buscar riesgos" in brief, fails)
    check("brief de agente incluye permisos", "sin aprobacion explicita" in brief, fails)
    check("brief de agente incluye pedido original", "revisa este cambio" in brief, fails)

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: prompt compiler verificable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
