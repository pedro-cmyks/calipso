#!/usr/bin/env python3
"""
calipso/connectors.py - health y limites de conectores/modelos.

V0 combina señales reales disponibles (CLI instalado/login, HTTP up, gasto API
registrado) con bloqueos configurables. Donde el proveedor no expone cuota exacta,
Calipso no inventa: marca la cuota como desconocida o manual.
"""
from __future__ import annotations

from typing import Any

from calipso import capabilities


def limits_status(cfg: dict[str, Any], monthly_report: dict[str, Any]) -> dict[str, Any]:
    limits = cfg.get("limits", {})
    api_limit = float(limits.get("api_monthly_usd") or 0)
    api_spend = float(monthly_report.get("api_cost_usd") or 0)
    warn_ratio = float(limits.get("api_warn_ratio") or 0.8)
    api_ratio = (api_spend / api_limit) if api_limit > 0 else 0.0
    api_over = api_limit > 0 and api_spend >= api_limit
    api_warn = api_limit > 0 and api_ratio >= warn_ratio
    api_blocked = bool(limits.get("block_api_when_over_budget", True) and api_over)
    sub_blocked = limits.get("subscription_blocked") or {}
    return {
        "api": {
            "limit_usd": api_limit,
            "spent_usd": api_spend,
            "ratio": round(api_ratio, 3),
            "warn": api_warn,
            "blocked": api_blocked,
            "reason": "presupuesto API agotado" if api_blocked else (
                "presupuesto API cerca del limite" if api_warn else ""),
        },
        "subscription": {
            client: {
                "blocked": bool(sub_blocked.get(client, False)),
                "reason": "bloqueado manualmente" if sub_blocked.get(client, False) else "",
                "quota_known": False,
            }
            for client in ("claude", "codex")
        },
    }


def health_status(cfg: dict[str, Any], monthly_report: dict[str, Any],
                  subscription: dict[str, dict[str, Any]],
                  api_up: bool, local_up: bool,
                  discovered: dict[str, Any] | None = None) -> dict[str, Any]:
    limits = limits_status(cfg, monthly_report)
    api = {
        "up": api_up,
        "ready": bool(api_up and not limits["api"]["blocked"]),
        "model": cfg.get("api", {}).get("model"),
        "base_url": cfg.get("api", {}).get("base_url"),
        **limits["api"],
    }
    local = {
        "up": local_up,
        "ready": bool(local_up),
        "model": cfg.get("local", {}).get("model"),
        "base_url": cfg.get("local", {}).get("base_url"),
    }
    subs = {}
    for client, state in subscription.items():
        limit = limits["subscription"].get(client, {})
        subs[client] = {
            **state,
            "blocked": bool(limit.get("blocked")),
            "quota_known": bool(limit.get("quota_known", False)),
            "quota_reason": limit.get("reason", ""),
            "ready": bool(state.get("ready") and not limit.get("blocked")),
        }
    return {
        "api": api,
        "local": local,
        "subscription": subs,
        "limits": limits,
        "discovered": discovered or {},
    }


def backend_availability(backends: dict[str, dict[str, Any]],
                         health: dict[str, Any]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for key, backend in backends.items():
        route = backend.get("route")
        if route == "local":
            out[key] = bool(health.get("local", {}).get("ready"))
        elif route == "api":
            out[key] = bool(health.get("api", {}).get("ready"))
        elif route == "subscription":
            client = backend.get("client")
            out[key] = bool(health.get("subscription", {}).get(client, {}).get("ready"))
        else:
            out[key] = False
    return out


def backend_quota_low(backends: dict[str, dict[str, Any]],
                      health: dict[str, Any]) -> dict[str, bool]:
    out: dict[str, bool] = {}
    api_low = bool(health.get("api", {}).get("warn") or health.get("api", {}).get("blocked"))
    for key, backend in backends.items():
        route = backend.get("route")
        if route == "api":
            out[key] = api_low
        elif route == "subscription":
            client = backend.get("client")
            sub = health.get("subscription", {}).get(client, {})
            out[key] = bool(sub.get("blocked"))
        else:
            out[key] = False
    return out


def routing_summary(project_root: str | None, health: dict[str, Any]) -> dict[str, Any]:
    backends = capabilities.load_backends(project_root)
    return {
        "available": backend_availability(backends, health),
        "quota_low": backend_quota_low(backends, health),
    }
