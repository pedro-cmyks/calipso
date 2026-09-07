#!/usr/bin/env python3
"""
calipso/plugins.py — Gestión de plugins de Claude Code.

Lee installed_plugins.json y plugin-catalog-cache.json de ~/.claude/plugins/
para exponer qué hay instalado y qué está disponible en el marketplace.
La instalación delega en `claude -p "/plugin <nombre>"`.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess

CLAUDE_HOME = pathlib.Path(os.environ.get("CLAUDE_HOME",
                           os.path.expanduser("~/.claude")))
PLUGINS_DIR = CLAUDE_HOME / "plugins"
INSTALLED_FILE = PLUGINS_DIR / "installed_plugins.json"
CATALOG_FILE   = PLUGINS_DIR / "plugin-catalog-cache.json"
MARKETPLACE_FILE = PLUGINS_DIR / "marketplaces" / "claude-plugins-official" / ".claude-plugin" / "marketplace.json"


def _read_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def list_installed() -> list[dict]:
    data = _read_json(INSTALLED_FILE)
    result = []
    for key, entries in data.get("plugins", {}).items():
        entry = entries[0] if entries else {}
        name, _, marketplace = key.partition("@")
        result.append({
            "id": key,
            "name": name,
            "marketplace": marketplace or "custom",
            "version": entry.get("version", "unknown"),
            "scope": entry.get("scope", "user"),
            "installedAt": entry.get("installedAt", ""),
            "installPath": entry.get("installPath", ""),
        })
    result.sort(key=lambda p: p["name"])
    return result


def _marketplace_meta() -> dict[str, dict]:
    data = _read_json(MARKETPLACE_FILE)
    return {p["name"]: p for p in data.get("plugins", [])}


def list_catalog(search: str = "", limit: int = 50) -> list[dict]:
    catalog = _read_json(CATALOG_FILE).get("catalog", {}).get("plugins", {})
    meta = _marketplace_meta()
    installed_names = {p["name"] for p in list_installed()}

    result = []
    for key, info in catalog.items():
        name, _, marketplace = key.partition("@")
        m = meta.get(name, {})
        if search and search.lower() not in name.lower() \
                and search.lower() not in (m.get("description") or "").lower() \
                and search.lower() not in (m.get("category") or "").lower():
            continue
        result.append({
            "id": key,
            "name": name,
            "marketplace": marketplace,
            "description": m.get("description", ""),
            "author": (m.get("author") or {}).get("name", ""),
            "category": m.get("category", ""),
            "homepage": m.get("homepage", ""),
            "installed": name in installed_names,
        })

    result.sort(key=lambda p: (not p["installed"], p["name"]))
    return result[:limit]


def install(plugin_name: str) -> dict:
    exe = shutil.which("claude")
    if not exe:
        return {"ok": False, "error": "claude CLI no encontrado"}
    env = {**os.environ}
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    # el CLI no necesita las credenciales del servidor ni de litellm
    # (revision de seguridad 2026-09-07, punto 2)
    env.pop("CALIPSO_TOKEN", None)
    env.pop("LITELLM_MASTER_KEY", None)
    try:
        result = subprocess.run(
            [exe, "-p", f"/plugin {plugin_name}"],
            capture_output=True, text=True, timeout=120, env=env
        )
        ok = result.returncode == 0
        return {
            "ok": ok,
            "stdout": result.stdout[-800:],
            "stderr": result.stderr[-400:],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
