#!/usr/bin/env python3
"""
test_skills.py - skills internos de Calipso.

Verifica que las habilidades declarativas existen, que se infieren para agentes
tipicos y que el endpoint las expone para la UI.
"""
from calipso import server, skills


def main() -> int:
    fails = []

    def check(name, cond, extra=""):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' ' + extra) if extra else ''}")
        if not cond:
            fails.append(name)

    expected = {"planner", "researcher", "coder", "reviewer", "writer",
                "librarian", "verifier", "synthesizer"}
    check("registro contiene skills base", expected.issubset(skills.REGISTRY))

    check("codigo -> coder",
          skills.infer({"type": "code", "role": "ingeniero", "task": "arreglar bug"}) == "coder")
    check("memoria -> librarian",
          skills.infer({"type": "analysis", "role": "bibliotecario",
                        "task": "clasificar memoria en AGENTS.md"}) == "librarian")
    check("verificacion -> verifier",
          skills.infer({"type": "analysis", "role": "revisor",
                        "task": "verificar pruebas"}) == "verifier")

    api = server.api_skills()
    ids = {s["id"] for s in api["skills"]}
    check("endpoint expone skills", expected.issubset(ids))
    check("endpoint trae prompt", all(s.get("prompt") for s in api["skills"]))

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: skills internos disponibles e inferibles")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
