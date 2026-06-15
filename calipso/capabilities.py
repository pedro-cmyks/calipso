#!/usr/bin/env python3
"""
calipso/capabilities.py — Ruteo por PUNTAJE de capacidad (no un gate que prueba).

Modelado en cómo rutean los mejores:
  - Router de GPT-5: decide por tipo/complejidad/herramientas/intención y elige
    modelo + esfuerzo.
  - MoE (DeepSeek/Kimi): un "gating" puntúa la AFINIDAD de cada experto y elige
    el mejor; no prueba secuencialmente.

Aquí cada backend declara para qué es bueno, su costo y sus límites. `choose()`
puntúa los backends DISPONIBLES para las features de la tarea y devuelve el
ranking. Así Claude vs Codex se elige por afinidad a la tarea (no en orden), se
prefieren suscripciones (costo marginal ~0) sobre APIs pagas, y local gana en lo
trivial/privado.

El mapa es declarativo y editable (~/.calipso/capabilities.json) para que el
BUCLE DE APRENDIZAJE (telemetría → reflexión) pueda reescribir los pesos con el
tiempo, igual que el router de GPT-5 se entrena con señales reales.
"""
from __future__ import annotations

import copy
import json
import os
import pathlib

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
CAP_FILE = CALIPSO_HOME / "capabilities.json"

# Costo = penalización de preferencia (menor = preferido):
#   0 = local (gratis) · 1 = suscripción (tarifa fija, marginal ~0) · 3 = API (paga)
# strengths: afinidad 0..1 por tipo de tarea.
# speed: 0..1 (mayor = más rápido).  max_complexity: 1..5.
DEFAULT_BACKENDS: dict[str, dict] = {
    "local": {
        "route": "local", "client": None, "cost": 0, "speed": 0.3,
        "max_complexity": 3, "private_ok": True,
        "strengths": {"trivial": 1.0, "translate": 1.0, "summarize": 1.0,
                      "private": 1.0, "reasoning": 0.5, "writing": 0.5,
                      "code": 0.3, "agentic": 0.2, "repo": 0.2},
    },
    "subscription:claude": {
        "route": "subscription", "client": "claude", "cost": 1, "speed": 0.9,
        "max_complexity": 5, "private_ok": False,
        "strengths": {"reasoning": 1.0, "refactor": 1.0, "writing": 1.0,
                      "analysis": 0.95, "code": 0.95, "agentic": 0.85,
                      "repo": 0.85, "summarize": 0.8, "trivial": 0.6},
    },
    "subscription:codex": {
        "route": "subscription", "client": "codex", "cost": 1, "speed": 0.9,
        "max_complexity": 5, "private_ok": False,
        "strengths": {"code": 1.0, "agentic": 1.0, "repo": 1.0, "exec": 1.0,
                      "refactor": 0.9, "reasoning": 0.8, "analysis": 0.8,
                      "writing": 0.7, "trivial": 0.6},
    },
    "api:deepseek-chat": {
        "route": "api", "client": None, "cost": 3, "speed": 0.85,
        "max_complexity": 5, "private_ok": False,
        "strengths": {"reasoning": 0.9, "analysis": 0.85, "writing": 0.8,
                      "code": 0.8, "summarize": 0.8, "agentic": 0.6},
    },
}

# Pesos del puntaje (también editables por el bucle de aprendizaje).
WEIGHTS = {"capability": 1.0, "cost": 0.25, "speed": 0.2, "quota": 0.6}


def load_backends() -> dict[str, dict]:
    backends = copy.deepcopy(DEFAULT_BACKENDS)
    if CAP_FILE.exists():
        try:
            data = json.loads(CAP_FILE.read_text(encoding="utf-8"))
            for k, v in data.get("backends", {}).items():
                backends.setdefault(k, {}).update(v)
        except Exception:
            pass
    return backends


def score_backend(features: dict, backend: dict,
                  available: bool, quota_low: bool = False) -> float | None:
    """Puntúa un backend para una tarea. None = excluido (no apto)."""
    if not available:
        return None
    if features.get("private") and not backend.get("private_ok"):
        return None  # privado: solo backends que no salen de la máquina
    complexity = features.get("complexity", 2)
    if backend.get("max_complexity", 5) < complexity:
        return None  # no alcanza la calidad necesaria

    task = features.get("type", "reasoning")
    cap = backend.get("strengths", {}).get(task, 0.4)
    # un backend que apenas cubre una tarea compleja vale menos
    cap *= 1.0 if cap >= 0.6 else 0.7

    score = (
        WEIGHTS["capability"] * cap
        - WEIGHTS["cost"] * backend.get("cost", 1)
        + WEIGHTS["speed"] * backend.get("speed", 0.5)
        - (WEIGHTS["quota"] if quota_low else 0.0)
    )
    return round(score, 4)


def choose(features: dict, available: dict[str, bool],
           quota_low: dict[str, bool] | None = None) -> list[dict]:
    """Devuelve el ranking de backends aptos (mayor puntaje primero).

    features: {type, complexity(1-5), private(bool), needs_repo(bool)}
    available: {backend_key: bool}
    quota_low: {backend_key: bool}  (cuota/saldo casi agotado)
    """
    quota_low = quota_low or {}
    backends = load_backends()
    ranked = []
    for key, backend in backends.items():
        s = score_backend(features, backend, available.get(key, False),
                          quota_low.get(key, False))
        if s is None:
            continue
        ranked.append({
            "key": key, "route": backend["route"], "client": backend.get("client"),
            "score": s,
        })
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked


if __name__ == "__main__":
    # Demo: todo disponible
    av = {k: True for k in DEFAULT_BACKENDS}
    for feat in [
        {"type": "translate", "complexity": 1, "private": True},
        {"type": "repo", "complexity": 4},
        {"type": "reasoning", "complexity": 3},
    ]:
        top = choose(feat, av)
        print(feat, "->", [(r["key"], r["score"]) for r in top[:3]])
