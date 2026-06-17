#!/usr/bin/env python3
"""
test_docs.py - coherencia minima de la literatura viva de Calipso.
"""
from __future__ import annotations

import pathlib


ROOT = pathlib.Path(__file__).resolve().parent


REQUIRED = {
    "SPEC.md": [
        "Fase 1 - Developer Loop minimo",
        "Fase 2 - Adjuntos reales",
        "Fase 3 - Verificacion fuerte",
        "Fase 4 - Bibliotecario activo",
        "Fase 5 - Conectores vivos y cuotas",
        "Fase 6 - Launch personal",
        "Fase 7 - Lenguaje interno / Prompt Compiler",
        "Adjuntos v0 existe",
        "Bibliotecario activo v0",
        "test_connectors.py",
        "test_launch.py",
        "test_prompt_compiler.py",
        "Goal Mode",
    ],
    "AGENTS.md": [
        "Calipso",
        "Adjuntos v0",
        "Goal Mode minimo",
        "Runner allowlist",
        "Bibliotecario activo v0",
        "Conectores/cuotas v0",
        "Launch personal v0",
        "GitHub remoto v0",
        "Rutinas/timers v0",
        "Lenguaje interno / Prompt Compiler",
    ],
    "LIBRARY.md": [
        "CALIPSO.md",
        "AGENTS.md",
        "SPEC.md",
        "pedro-perfil.md",
        "prompt_compiler.py",
    ],
    "RUNBOOK.md": [
        "Calipso",
        "localhost",
    ],
}


def check(name: str, cond: bool, fails: list[str]) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def main() -> int:
    fails: list[str] = []
    for filename, phrases in REQUIRED.items():
        path = ROOT / filename
        check(f"{filename} existe", path.exists(), fails)
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for phrase in phrases:
            check(f"{filename}: {phrase}", phrase in text, fails)
    spec = (ROOT / "SPEC.md").read_text(encoding="utf-8", errors="replace")
    check("Fase 2 marcada v0", "- [x] Adjuntar carpeta/proyecto" in spec, fails)
    check("Fase 3 conserva pendientes", "Mapeo tipo de cambio" in spec, fails)
    check("Fase 4 marcada v0", "- [x] Inbox de memoria" in spec, fails)
    check("Fase 5 marcada v0", "- [x] Health real Claude/Codex/Ollama/LiteLLM" in spec, fails)
    check("Fase 6 marcada v0", "- [x] Checklist de salud visible" in spec, fails)
    check("Fase 7 marcada v0", "- [x] Crear `calipso/prompt_compiler.py`" in spec, fails)
    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: documentos guia coherentes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
