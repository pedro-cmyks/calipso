from __future__ import annotations

import copy
import json
import os
import pathlib
from typing import Any

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
CONFIG_FILE = CALIPSO_HOME / "config.json"

# El embedder de la memoria episodica vive en Ollama (spec memoria por Ollama
# 2026-09-12). Vive ACA y no en memory.py (ruling 8.11) para que `carga` lo
# lea sin arrastrar chromadb. EMBED_MODEL es el nombre TAL COMO lo devuelve
# /api/ps (`bge-m3:latest`; `bge-m3` a secas no matchea, ruling 8.1); el tag
# de la coleccion (`bge-m3`) lo deriva memoria_embed.embed_tag. Las
# dimensiones son fijas por config (ruling 8.2: nada consulta /api/show al
# construir la funcion de embeddings; cambiar de modelo es cambiar las dos
# variables juntas y reindexar). La URL es la del Ollama local; el smoke la
# apunta a un proxy para cortarla a mitad.
EMBED_MODEL = os.environ.get("CALIPSO_EMBED_MODEL", "bge-m3:latest")
EMBED_DIMS = int(os.environ.get("CALIPSO_EMBED_DIMS", "1024"))
EMBED_URL = os.environ.get("CALIPSO_EMBED_URL", "http://localhost:11434")

DEFAULT_CONFIG: dict[str, Any] = {
    "projects": {
        "recent": [],
    },
    "routing": {
        "policy": "subscription_first",
        "subscription_client": "claude",
        "api_only_when_forced": True,
    },
    "limits": {
        "api_monthly_usd": 5.0,
        "api_warn_ratio": 0.8,
        "block_api_when_over_budget": True,
        "subscription_blocked": {
            "claude": False,
            "codex": False,
        },
    },
    "subscription": {
        "claude": ["claude.cmd", "-p", "{prompt}"],
        "codex": ["codex.cmd", "exec", "--output-last-message", "{output}", "{prompt}"],
    },
    "api": {
        "base_url": "http://localhost:4000/v1/chat/completions",
        "api_key_env": "LITELLM_MASTER_KEY",
        "api_key_default": "sk-litellm-local",
        "model": "deepseek-chat",
    },
    "local": {
        "base_url": "http://localhost:11434/api/generate",
        "model": "qwen2.5:7b",
    },
    "classifier": {
        "base_url": "http://localhost:11434/api/generate",
        "model": "qwen2.5:3b",
    },
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return copy.deepcopy(DEFAULT_CONFIG)
    return _merge(DEFAULT_CONFIG, data)


def save_config(data: dict[str, Any]) -> dict[str, Any]:
    cfg = _merge(load_config(), data)
    CALIPSO_HOME.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return cfg


def dispatch_config() -> dict[str, Any]:
    cfg = load_config()
    subscription = copy.deepcopy(cfg["subscription"])
    if os.name == "nt" and subscription.get("claude", [""])[0] == "claude":
        subscription["claude"][0] = "claude.cmd"
    if os.name == "nt" and subscription.get("codex", [""])[0] == "codex":
        subscription["codex"][0] = "codex.cmd"
    if subscription.get("codex") == ["codex.cmd", "exec", "{prompt}"]:
        subscription["codex"] = [
            "codex.cmd", "exec", "--output-last-message", "{output}", "{prompt}"]
    api = cfg["api"].copy()
    api["api_key"] = os.environ.get(
        api.get("api_key_env", "LITELLM_MASTER_KEY"),
        api.get("api_key_default", "sk-litellm-local"))
    return {
        "subscription": subscription,
        "api": {
            "base_url": api["base_url"],
            "api_key": api["api_key"],
            "model": api["model"],
        },
        "local": cfg["local"],
        "classifier": cfg["classifier"],
    }
