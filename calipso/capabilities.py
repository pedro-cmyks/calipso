#!/usr/bin/env python3
"""
calipso/capabilities.py — Registro a nivel de MODELO + ruteo por puntaje.

La unidad es el MODELO (no la ruta): la ruta es solo el transporte. Cada modelo
declara para qué es bueno, su tier, su costo y su persona (nombre de filósofo,
como los agentes de Codex). Así Calipso elige Haiku vs Opus vs Codex vs local por
afinidad+costo+intensidad, prefiere suscripciones sobre APIs pagas, y descubre
modelos nuevos de cualquier proveedor (Ollama/LiteLLM) dándoles un prior por tier
que luego el aprendizaje calibra.

EJE DE INTENSIDAD ("ultrathink"): 0 fast · 1 balanced · 2 think · 3 ultra.
Calipso lo deriva de la complejidad; Pedro lo fuerza con slash o palabras clave.
Mayor intensidad => exige un tier más alto y más esfuerzo (effort de Anthropic).

Editable en ~/.calipso/capabilities.json (global) y <repo>/.calipso/capabilities.json
(por repo) — ahí escribe el bucle de aprendizaje.
"""
from __future__ import annotations

import copy
import json
import os
import pathlib

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
CAP_FILE = CALIPSO_HOME / "capabilities.json"

TIER_RANK = {"small": 0, "mid": 1, "frontier": 2, "apex": 3}

# Niveles de intensidad y el tier MÍNIMO que exigen.
EFFORT = {"fast": 0, "balanced": 1, "think": 2, "ultra": 3}
EFFORT_NAME = {v: k for k, v in EFFORT.items()}
EFFORT_MIN_TIER = {0: 0, 1: 0, 2: 1, 3: 2}
# Traducción del nivel al parámetro 'effort' estilo Anthropic (para sub/api).
EFFORT_PARAM = {0: "low", 1: "medium", 2: "high", 3: "xhigh"}

# Registro declarativo. cost = penalización de preferencia (0 local · 1 sub · 3 api).
# model = lo que se pasa al CLI/--model o al payload. persona = nombre interno.
REGISTRY: dict[str, dict] = {
    "local:qwen2.5:3b": {
        "route": "local", "client": None, "model": "qwen2.5:3b",
        "tier": "small", "persona": "Diogenes", "cost": 0, "speed": 0.35,
        "max_complexity": 2, "private_ok": True,
        "strengths": {"trivial": 1.0, "translate": 0.9, "summarize": 0.9,
                      "private": 1.0, "reasoning": 0.4},
    },
    "local:qwen2.5:7b": {
        "route": "local", "client": None, "model": "qwen2.5:7b",
        "tier": "small", "persona": "Epicteto", "cost": 0, "speed": 0.3,
        "max_complexity": 3, "private_ok": True,
        "strengths": {"trivial": 1.0, "translate": 1.0, "summarize": 1.0,
                      "private": 1.0, "writing": 0.6, "reasoning": 0.55,
                      "code": 0.3, "analysis": 0.5},
    },
    "subscription:claude:haiku": {
        "route": "subscription", "client": "claude", "model": "haiku",
        "tier": "small", "persona": "Seneca", "cost": 1, "speed": 0.95,
        "max_complexity": 3, "private_ok": False,
        "strengths": {"trivial": 0.9, "translate": 0.9, "summarize": 0.9,
                      "writing": 0.85, "reasoning": 0.7, "code": 0.75,
                      "analysis": 0.75},
    },
    "subscription:claude:sonnet": {
        "route": "subscription", "client": "claude", "model": "sonnet",
        "tier": "mid", "persona": "Hipatia", "cost": 1, "speed": 0.9,
        "max_complexity": 5, "private_ok": False,
        "strengths": {"reasoning": 0.9, "writing": 0.95, "analysis": 0.9,
                      "code": 0.9, "refactor": 0.9, "agentic": 0.8,
                      "repo": 0.8, "summarize": 0.85},
    },
    "subscription:claude:opus": {
        "route": "subscription", "client": "claude", "model": "opus",
        "tier": "frontier", "persona": "Aristoteles", "cost": 1, "speed": 0.85,
        "max_complexity": 5, "private_ok": False,
        "strengths": {"reasoning": 1.0, "refactor": 1.0, "writing": 1.0,
                      "analysis": 0.97, "code": 0.95, "agentic": 0.9,
                      "repo": 0.9},
    },
    "subscription:codex:gpt-5.5": {
        "route": "subscription", "client": "codex", "model": "gpt-5.5",
        "tier": "frontier", "persona": "Arquimedes", "cost": 1, "speed": 0.9,
        "max_complexity": 5, "private_ok": False,
        "strengths": {"code": 1.0, "agentic": 1.0, "repo": 1.0, "exec": 1.0,
                      "refactor": 0.92, "reasoning": 0.8, "analysis": 0.8},
    },
    "api:deepseek-chat": {
        "route": "api", "client": None, "model": "deepseek-chat",
        "tier": "mid", "persona": "Confucio", "cost": 3, "speed": 0.85,
        "max_complexity": 5, "private_ok": False,
        "strengths": {"reasoning": 0.9, "analysis": 0.85, "writing": 0.8,
                      "code": 0.8, "summarize": 0.8},
    },
    "api:claude-fable-5": {
        "route": "api", "client": None, "model": "claude-fable-5",
        "tier": "apex", "persona": "Platon", "cost": 3, "speed": 0.8,
        "max_complexity": 5, "private_ok": False,
        "strengths": {"reasoning": 1.0, "analysis": 1.0, "writing": 1.0,
                      "refactor": 1.0, "code": 1.0, "agentic": 0.95},
    },
}

# Personas para modelos descubiertos sin entrada propia.
PERSONA_POOL = ["Tales", "Heraclito", "Parmenides", "Zenon", "Pitagoras",
                "Anaximandro", "Empedocles", "Protagoras", "Gorgias", "Anaxagoras"]

WEIGHTS = {"capability": 1.0, "cost": 0.25, "speed": 0.2, "quota": 0.6, "tier": 0.15}


def tier_prior(tier: str) -> dict:
    """Perfil inicial para un modelo nuevo según su tier (lo calibra el aprendizaje)."""
    base = {
        "small": {"speed": 0.7, "max_complexity": 3,
                  "strengths": {"trivial": 0.9, "summarize": 0.8, "reasoning": 0.6,
                                "code": 0.6}},
        "mid": {"speed": 0.85, "max_complexity": 5,
                "strengths": {"reasoning": 0.85, "analysis": 0.8, "code": 0.8,
                              "writing": 0.8}},
        "frontier": {"speed": 0.85, "max_complexity": 5,
                     "strengths": {"reasoning": 0.95, "code": 0.9, "analysis": 0.92,
                                   "agentic": 0.85, "repo": 0.85, "refactor": 0.9}},
        "apex": {"speed": 0.8, "max_complexity": 5,
                 "strengths": {"reasoning": 1.0, "code": 1.0, "analysis": 1.0}},
    }
    return base.get(tier, base["mid"])


# --------------------------------------------------------------------- overrides
def _apply_overrides(backends: dict, path: pathlib.Path) -> None:
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return
    for k, v in data.get("backends", {}).items():
        if k not in backends and not (
                isinstance(v, dict) and v.get("route") and v.get("model")):
            continue
        tgt = backends.setdefault(k, {})
        for kk, vv in v.items():
            if kk == "strengths" and isinstance(vv, dict):
                tgt.setdefault("strengths", {}).update(vv)
            else:
                tgt[kk] = vv


def load_backends(project_root: str | None = None) -> dict[str, dict]:
    backends = copy.deepcopy(REGISTRY)
    _apply_overrides(backends, CAP_FILE)
    if project_root:
        _apply_overrides(
            backends, pathlib.Path(project_root) / ".calipso" / "capabilities.json")
    return backends


def discover(route: str, model_name: str, tier: str = "mid",
             registry: dict | None = None) -> str:
    """Registra un modelo descubierto (Ollama/LiteLLM) con prior por tier.
    Devuelve su clave. Si ya existe, no lo pisa."""
    registry = registry if registry is not None else REGISTRY
    key = f"{route}:{model_name}"
    if key not in registry:
        prior = tier_prior(tier)
        idx = len([k for k in registry if k.startswith("__discovered")])
        registry[key] = {
            "route": route, "client": None, "model": model_name, "tier": tier,
            "persona": PERSONA_POOL[idx % len(PERSONA_POOL)],
            "cost": 0 if route == "local" else 3,
            "private_ok": route == "local", **prior,
        }
    return key


# ----------------------------------------------------------------- intensidad
def derive_effort(complexity: int) -> int:
    return {1: 0, 2: 1, 3: 1, 4: 2, 5: 3}.get(int(complexity), 1)


_FAST_WORDS = ("rapido", "rápido", "breve", "corto", "/fast")
_THINK_WORDS = ("piensa bien", "analiza a fondo", "/think")
_ULTRA_WORDS = ("ultrathink", "ultra think", "piensa profundo", "maximo esfuerzo",
                "/ultrathink", "/ultra")


def parse_directives(message: str) -> dict:
    """Extrae slash-commands y palabras de intensidad. Devuelve overrides + msg limpio."""
    out = {"clean": message, "effort": None, "force_model": None,
           "force_route": None, "help": False, "force_web": False,
           "force_team": False}
    low = message.lower()
    tokens = message.split()
    keep = []
    for t in tokens:
        tl = t.lower()
        if tl in ("/help", "/?"):
            out["help"] = True
        elif tl == "/web":
            out["force_web"] = True
        elif tl in ("/plan", "/team", "/equipo"):
            out["force_team"] = True
        elif tl in ("/fast",):
            out["effort"] = EFFORT["fast"]
        elif tl in ("/think",):
            out["effort"] = EFFORT["think"]
        elif tl in ("/ultrathink", "/ultra"):
            out["effort"] = EFFORT["ultra"]
        elif tl in ("/local", "/claude", "/codex", "/api"):
            out["force_route"] = "subscription" if tl in ("/claude", "/codex") else tl[1:]
            if tl in ("/claude", "/codex"):
                out["force_model"] = tl[1:]  # marcador de cliente
        elif tl == "/model":
            keep.append(t)  # el valor lo toma el siguiente token abajo
        else:
            keep.append(t)
    # /model <valor>
    if "/model" in [t.lower() for t in tokens]:
        idx = [t.lower() for t in tokens].index("/model")
        if idx + 1 < len(tokens):
            out["force_model"] = tokens[idx + 1]
            keep = [t for i, t in enumerate(tokens)
                    if i not in (idx, idx + 1) and not t.startswith("/")]
    else:
        keep = [t for t in keep if not t.startswith("/")]
    # palabras clave de intensidad (si no hubo slash explícito)
    if out["effort"] is None:
        if any(w in low for w in _ULTRA_WORDS):
            out["effort"] = EFFORT["ultra"]
        elif any(w in low for w in _THINK_WORDS):
            out["effort"] = EFFORT["think"]
        elif any(w in low for w in _FAST_WORDS):
            out["effort"] = EFFORT["fast"]
    out["clean"] = " ".join(keep).strip() or message
    return out


# --------------------------------------------------------------------- scoring
def score_model(features: dict, effort: int, m: dict,
                available: bool, quota_low: bool = False) -> float | None:
    if not available:
        return None
    if features.get("private") and not m.get("private_ok"):
        return None
    if m.get("max_complexity", 5) < features.get("complexity", 2):
        return None
    if TIER_RANK.get(m.get("tier", "mid"), 1) < EFFORT_MIN_TIER[effort]:
        return None  # no alcanza la intensidad pedida

    cap = m.get("strengths", {}).get(features.get("type", "reasoning"), 0.4)
    cap *= 1.0 if cap >= 0.6 else 0.7
    score = (
        WEIGHTS["capability"] * cap
        - WEIGHTS["cost"] * m.get("cost", 1)
        + WEIGHTS["speed"] * m.get("speed", 0.5)
        - (WEIGHTS["quota"] if quota_low else 0.0)
    )
    if effort <= 1:  # tareas livianas: penaliza el overkill de tier alto
        score -= WEIGHTS["tier"] * TIER_RANK.get(m.get("tier", "mid"), 1)
    return round(score, 4)


def choose(features: dict, effort: int, available: dict[str, bool],
           quota_low: dict[str, bool] | None = None,
           project_root: str | None = None) -> list[dict]:
    """Ranking de modelos aptos para (features, effort). Mayor puntaje primero."""
    quota_low = quota_low or {}
    backends = load_backends(project_root)
    ranked = []
    for key, m in backends.items():
        s = score_model(features, effort, m, available.get(key, False),
                        quota_low.get(key, False))
        if s is None:
            continue
        ranked.append({
            "key": key, "route": m["route"], "client": m.get("client"),
            "model": m.get("model"), "persona": m.get("persona", key),
            "tier": m.get("tier"), "score": s,
        })
    ranked.sort(key=lambda r: r["score"], reverse=True)
    return ranked


if __name__ == "__main__":
    av = {k: True for k in REGISTRY}
    for feat, eff in [
        ({"type": "translate", "complexity": 1}, 0),
        ({"type": "repo", "complexity": 4}, 2),
        ({"type": "reasoning", "complexity": 3}, 3),
    ]:
        top = choose(feat, eff, av)
        print(feat, EFFORT_NAME[eff], "->",
              [(r["persona"], r["key"], r["score"]) for r in top[:3]])
