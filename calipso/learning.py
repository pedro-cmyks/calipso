#!/usr/bin/env python3
"""
calipso/learning.py — Bucle de aprendizaje: telemetría → pesos de ruteo.

Como el router de GPT-5 (entrenado con señales reales: cambios/fallbacks,
preferencia, correctitud), Calipso ajusta la AFINIDAD de cada backend por tipo
de tarea según lo observado. Conservador: pasos pequeños y mínimo de muestras
para no sobre-reaccionar al ruido.

Ámbitos (responde a "¿global o del repo?"):
  - GLOBAL: toda la telemetría → ~/.calipso/capabilities.json.
  - PROYECTO: telemetría filtrada por repo → <repo>/.calipso/capabilities.json.
"""
from __future__ import annotations

import json
import os
import pathlib

from calipso import capabilities, telemetry

STEP = float(os.environ.get("CALIPSO_LEARN_STEP", "0.05"))
MIN_SAMPLES = int(os.environ.get("CALIPSO_LEARN_MIN", "3"))


def _backend_key(ev: dict) -> str | None:
    """Clave del MODELO en el registro. Prefiere model_id (lo loguea el chat);
    cae a una reconstrucción por ruta para telemetría antigua."""
    if ev.get("model_id"):
        return ev["model_id"]
    route, model = ev.get("route_used"), ev.get("model")
    if route and model:
        return f"{route}:{model}"
    return None


def analyze(events: list[dict]) -> dict:
    """Agrega por (task_type, backend): muestras, fallos, latencia."""
    stats: dict[str, dict[str, dict]] = {}
    for ev in events:
        if ev.get("kind") != "chat_turn":
            continue
        tt, bk = ev.get("task_type"), _backend_key(ev)
        if not tt or not bk:
            continue
        d = stats.setdefault(tt, {}).setdefault(bk, {"n": 0, "fails": 0, "lat": 0})
        d["n"] += 1
        if ev.get("fallbacks"):
            d["fails"] += 1
        d["lat"] += ev.get("latency_ms", 0) or 0
    return stats


def propose(stats: dict, step: float = STEP, min_samples: int = MIN_SAMPLES) -> dict:
    """Por cada task_type: sube al backend ganador, baja a los que fallan mucho."""
    deltas: dict[str, dict[str, float]] = {}
    for tt, backends in stats.items():
        elig = {b: d for b, d in backends.items() if d["n"] >= min_samples}
        if not elig:
            continue

        def score(d):
            fail_rate = d["fails"] / d["n"]
            avg_lat = d["lat"] / d["n"]
            return (1 - fail_rate, -avg_lat)  # menos fallos, luego menos latencia

        winner = max(elig, key=lambda b: score(elig[b]))
        deltas.setdefault(winner, {})[tt] = step
        for b, d in elig.items():
            if b != winner and d["fails"] / d["n"] >= 0.5:
                deltas.setdefault(b, {})[tt] = -step
    return deltas


def apply(deltas: dict, target_file: str | pathlib.Path) -> list[dict]:
    """Aplica los deltas a las strengths del mapa de capacidades (clamp 0..1)."""
    target = pathlib.Path(target_file)
    current: dict = {}
    if target.exists():
        try:
            current = json.loads(target.read_text(encoding="utf-8"))
        except Exception:
            current = {}
    backends = current.setdefault("backends", {})
    defaults = capabilities.REGISTRY
    changed = []
    for bk, tts in deltas.items():
        strengths = backends.setdefault(bk, {}).setdefault("strengths", {})
        for tt, delta in tts.items():
            base = strengths.get(
                tt, defaults.get(bk, {}).get("strengths", {}).get(tt, 0.4))
            new = round(min(1.0, max(0.0, base + delta)), 3)
            if new != base:
                strengths[tt] = new
                changed.append({"backend": bk, "task": tt,
                                "from": round(base, 3), "to": new})
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    return changed


def learn(project_root: str | None = None, project: str | None = None) -> dict:
    """Corre el ciclo. Si 'project'/'project_root' se dan, aprende por repo."""
    events = telemetry.recent(2000)
    if project:
        events = [e for e in events if e.get("project") == project]
    stats = analyze(events)
    deltas = propose(stats)
    if not deltas:
        return {"changed": [], "reason": "sin suficientes muestras todavía",
                "scope": "project" if project else "global"}
    target = (pathlib.Path(project_root) / ".calipso" / "capabilities.json"
              if project_root else capabilities.CAP_FILE)
    changed = apply(deltas, target)
    return {"changed": changed, "target": str(target),
            "scope": "project" if project else "global"}


if __name__ == "__main__":
    print(json.dumps(learn(), indent=2, ensure_ascii=False))
