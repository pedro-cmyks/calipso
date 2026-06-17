#!/usr/bin/env python3
"""
test_connectors.py - health, limites y disponibilidad de conectores.
"""
from __future__ import annotations

from calipso import connectors


def check(name: str, cond: bool, fails: list[str]) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def sample_cfg() -> dict:
    return {
        "api": {
            "model": "gpt-test",
            "base_url": "http://localhost:4000/v1/chat/completions",
        },
        "local": {
            "model": "qwen-test",
            "base_url": "http://localhost:11434/api/generate",
        },
        "limits": {
            "api_monthly_usd": 1.0,
            "api_warn_ratio": 0.8,
            "block_api_when_over_budget": True,
            "subscription_blocked": {"claude": True, "codex": False},
        },
    }


def main() -> int:
    fails: list[str] = []

    warn = connectors.limits_status(sample_cfg(), {"api_cost_usd": 0.85})
    check("API avisa cerca del presupuesto", warn["api"]["warn"] is True, fails)
    check("API aun no bloquea bajo limite", warn["api"]["blocked"] is False, fails)
    check("Claude bloqueado manualmente", warn["subscription"]["claude"]["blocked"] is True, fails)

    over = connectors.limits_status(sample_cfg(), {"api_cost_usd": 1.25})
    check("API bloquea al superar presupuesto", over["api"]["blocked"] is True, fails)
    check("razon humana de bloqueo", "agotado" in over["api"]["reason"], fails)

    health = connectors.health_status(
        sample_cfg(),
        {"api_cost_usd": 1.25},
        {
            "claude": {"installed": True, "ready": True, "error": ""},
            "codex": {"installed": True, "ready": True, "error": ""},
        },
        api_up=True,
        local_up=True,
    )
    check("API up pero no lista si presupuesto agotado", health["api"]["ready"] is False, fails)
    check("local listo si Ollama responde", health["local"]["ready"] is True, fails)
    check("Claude no listo si esta bloqueado", health["subscription"]["claude"]["ready"] is False, fails)
    check("Codex listo si probe y limite permiten", health["subscription"]["codex"]["ready"] is True, fails)

    backends = {
        "local_model": {"route": "local"},
        "api_model": {"route": "api"},
        "claude_model": {"route": "subscription", "client": "claude"},
        "codex_model": {"route": "subscription", "client": "codex"},
    }
    available = connectors.backend_availability(backends, health)
    quota_low = connectors.backend_quota_low(backends, health)
    check("disponibilidad local verdadera", available["local_model"] is True, fails)
    check("API no disponible si esta bloqueada", available["api_model"] is False, fails)
    check("Claude no disponible si bloqueo manual", available["claude_model"] is False, fails)
    check("Codex disponible", available["codex_model"] is True, fails)
    check("API marcada como cuota baja", quota_low["api_model"] is True, fails)
    check("local no se marca cuota baja", quota_low["local_model"] is False, fails)

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: conectores y cuotas verificables")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
