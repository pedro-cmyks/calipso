#!/usr/bin/env python3
"""
calipso/discovery.py — Descubrimiento automático de modelos + aviso de updates.

Pregunta a cada proveedor qué modelos tiene (Ollama /api/tags, LiteLLM /v1/models)
y los registra en el REGISTRY con un prior por tier (que el aprendizaje calibra).
Además informa de updates: versiones de los CLIs instalados, si hay versión más
nueva en npm, y qué modelos son NUEVOS respecto al último vistazo.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import urllib.request

from calipso import aduana, capabilities

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
SNAP = CALIPSO_HOME / "discovered.json"

NPM_PKG = {"claude": "@anthropic-ai/claude-code", "codex": "@openai/codex"}


def _get_json(url: str, timeout: float = 2.0):
    """Loopback por default: `discover_ollama` / `discover_litellm` aceptan
    cualquier `base`, pero los llamadores de produccion (`discover`,
    `resource_dispatcher.ollama_installed_models`) usan el por defecto
    (localhost). Un llamador con otro `base` no cruza: limite conocido,
    listado en el canario. `_npm_latest` NO pasa por aca: se traga toda
    excepcion, y el libro de la aduana nunca podria decir `fallo`."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def guess_tier(name: str) -> str:
    n = name.lower()
    if any(x in n for x in ("fable", "ultra-")):
        return "apex"
    if any(x in n for x in ("opus", "gpt-5.5", "405b", "70b", "72b")):
        return "frontier"
    if any(x in n for x in ("mini", "haiku", "small", "spark", "1b", "1.5b",
                            "3b", "4b")):
        return "small"
    return "mid"


def discover_ollama(base: str = "http://localhost:11434") -> list[str]:
    data = _get_json(base + "/api/tags")
    names = [m.get("name", "") for m in (data or {}).get("models", [])]
    # fuera los modelos de embeddings (no sirven para chatear)
    return [n for n in names if n and "embed" not in n.lower() and "bge" not in n.lower()]


def discover_litellm(base: str = "http://localhost:4000") -> list[str]:
    data = _get_json(base + "/v1/models")
    return [m.get("id", "") for m in (data or {}).get("data", []) if m.get("id")]


def discover(register: bool = True) -> dict:
    """Descubre modelos vivos y (opcional) los registra. Devuelve lo encontrado."""
    local = discover_ollama()
    api = discover_litellm()
    added = []
    if register:
        for n in local:
            key = f"local:{n}"
            if key not in capabilities.REGISTRY:
                capabilities.discover("local", n, tier="small")
                added.append(key)
        for n in api:
            key = f"api:{n}"
            if key not in capabilities.REGISTRY:
                capabilities.discover("api", n, tier=guess_tier(n))
                added.append(key)
    return {"local": local, "api": api, "added": added}


def _cli_version(client: str) -> str | None:
    exe = (shutil.which(f"{client}.cmd") or shutil.which(f"{client}.exe")
           or shutil.which(client))
    if not exe:
        return None
    try:
        r = subprocess.run([exe, "--version"], capture_output=True, text=True,
                           timeout=5, encoding="utf-8", errors="replace")
        return (r.stdout or r.stderr).strip().splitlines()[0][:60]
    except Exception:
        return None


def _npm_latest(pkg: str, quien: aduana.Quien) -> str | None:
    """La version publicada en npm. El urlopen va inline: el `with` de la
    aduana vive en la funcion que hace la llamada (spec seccion 3). Carga
    `nada`: no lleva nada de Pedro."""
    url = f"https://registry.npmjs.org/{pkg}/latest"
    try:
        with aduana.cruzar(quien, "version en npm", destino=url,
                           carga=None) as cruce:
            with urllib.request.urlopen(url, timeout=4) as r:
                crudo = r.read()
            cruce.entro(len(crudo))
        data = json.loads(crudo.decode())
    except Exception:
        return None
    return data.get("version") if isinstance(data, dict) else None


def updates(quien: aduana.Quien) -> dict:
    """Estado de updates: versiones CLI (+ latest npm), modelos nuevos vs snapshot."""
    found = discover(register=True)
    current = ({f"local:{n}" for n in found["local"]}
               | {f"api:{n}" for n in found["api"]})
    prev = set()
    if SNAP.exists():
        try:
            prev = set(json.loads(SNAP.read_text(encoding="utf-8")).get("models", []))
        except Exception:
            prev = set()
    new_models = sorted(current - prev)
    try:
        CALIPSO_HOME.mkdir(parents=True, exist_ok=True)
        SNAP.write_text(json.dumps({"models": sorted(current)}, ensure_ascii=False),
                        encoding="utf-8")
    except Exception:
        pass

    clis = {}
    for client, pkg in NPM_PKG.items():
        installed = _cli_version(client)
        latest = _npm_latest(pkg, quien) if installed else None
        outdated = bool(installed and latest and latest not in installed)
        clis[client] = {"installed": installed, "latest": latest, "outdated": outdated}
    clis["ollama"] = {"installed": _cli_version("ollama"), "latest": None,
                      "outdated": False}

    return {"clis": clis, "new_models": new_models,
            "available_models": sorted(current)}


if __name__ == "__main__":
    print(json.dumps(updates(aduana.Quien(
        origen="gesto", proyecto="cli", desde={"credencial": "maquina"})),
        indent=2, ensure_ascii=False))
