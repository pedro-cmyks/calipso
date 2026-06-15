#!/usr/bin/env python3
"""
calipso/sessions.py — Perfiles de sesión.

Cada sesión tiene su propio ELENCO de agentes (= los modelos del registro, con
nombre propio). Por sesión y por agente se configura:
  - name      : el nombre del agente en esta sesión (cambia por sesión, editable)
  - intensity : intensidad de uso de ESE modelo en ESTA sesión (fast/.../ultra o None)
  - enabled   : si el agente participa en esta sesión

Cada sesión nueva toma un "roster" temático distinto (filósofos, científicos,
escritores…), así el elenco cambia de una sesión a otra. Pedro puede renombrar
o reconfigurar cualquiera.
"""
from __future__ import annotations

import json
import os
import pathlib

from calipso import capabilities

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
SESS_DIR = CALIPSO_HOME / "sessions"
ACTIVE_FILE = CALIPSO_HOME / "active_session"

ROSTERS = [
    ["Aristoteles", "Platon", "Socrates", "Heraclito", "Diogenes", "Epicteto",
     "Seneca", "Hipatia", "Arquimedes", "Tales", "Heron", "Confucio", "Kant",
     "Pitagoras", "Zenon", "Epicuro"],
    ["Newton", "Euler", "Gauss", "Turing", "Lovelace", "Ramanujan", "Noether",
     "Hilbert", "Cantor", "Godel", "Curie", "Tesla", "Bohr", "Fermi", "Dirac",
     "Maxwell"],
    ["Borges", "Cervantes", "Cortazar", "Neruda", "Rulfo", "Paz", "Allende",
     "Quiroga", "Storni", "Mistral", "Vallejo", "Lispector", "Saramago",
     "Bolano", "Pizarnik", "Onetti"],
]

VALID_INTENSITY = set(capabilities.EFFORT) | {None}


def list_models() -> list[str]:
    return list(capabilities.REGISTRY.keys())


def _default_agents(roster: list[str]) -> dict:
    agents = {}
    for i, mid in enumerate(list_models()):
        agents[mid] = {"name": roster[i % len(roster)], "intensity": None,
                       "enabled": True}
    return agents


def _path(sid: str) -> pathlib.Path:
    return SESS_DIR / f"{sid}.json"


def save(prof: dict) -> dict:
    SESS_DIR.mkdir(parents=True, exist_ok=True)
    _path(prof["id"]).write_text(
        json.dumps(prof, ensure_ascii=False, indent=2), encoding="utf-8")
    return prof


def load(sid: str) -> dict | None:
    p = _path(sid)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def list_sessions() -> list[dict]:
    SESS_DIR.mkdir(parents=True, exist_ok=True)
    return [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(SESS_DIR.glob("*.json"))]


def set_active(sid: str) -> None:
    CALIPSO_HOME.mkdir(parents=True, exist_ok=True)
    ACTIVE_FILE.write_text(sid, encoding="utf-8")


def create(name: str | None = None) -> dict:
    SESS_DIR.mkdir(parents=True, exist_ok=True)
    n = len(list(SESS_DIR.glob("*.json")))
    sid = f"s{n + 1}"
    roster_idx = n % len(ROSTERS)
    prof = {
        "id": sid, "name": name or f"Sesion {n + 1}", "roster": roster_idx,
        "agents": _default_agents(ROSTERS[roster_idx]),
    }
    save(prof)
    set_active(sid)
    return prof


def active() -> dict:
    """Sesión activa; crea una si no hay ninguna."""
    if ACTIVE_FILE.exists():
        prof = load(ACTIVE_FILE.read_text(encoding="utf-8").strip())
        if prof:
            # asegura que modelos nuevos del registro tengan entrada
            roster = ROSTERS[prof.get("roster", 0)]
            for i, mid in enumerate(list_models()):
                prof["agents"].setdefault(
                    mid, {"name": roster[i % len(roster)], "intensity": None,
                          "enabled": True})
            return prof
    return create()


def set_agent(sid: str, model_id: str, name: str | None = None,
              intensity: str | None = "_keep", enabled: bool | None = None) -> dict:
    prof = load(sid)
    if not prof:
        raise KeyError(sid)
    a = prof["agents"].setdefault(
        model_id, {"name": model_id, "intensity": None, "enabled": True})
    if name is not None:
        a["name"] = name
    if intensity != "_keep":
        if intensity not in VALID_INTENSITY:
            raise ValueError(f"intensidad invalida: {intensity}")
        a["intensity"] = intensity
    if enabled is not None:
        a["enabled"] = bool(enabled)
    return save(prof)


def apply(prof: dict, model_id: str, persona_default: str, route: str) -> dict:
    """Devuelve {name, enabled, intensity} efectivos del agente en la sesión."""
    a = (prof.get("agents") or {}).get(model_id, {})
    return {
        "name": a.get("name") or persona_default,
        "enabled": a.get("enabled", True),
        "intensity": a.get("intensity"),
    }


if __name__ == "__main__":
    p = create("demo")
    print("sesion", p["id"], "agentes:",
          {k: v["name"] for k, v in list(p["agents"].items())[:4]})
