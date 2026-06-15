#!/usr/bin/env python3
"""
calipso/costs.py — Tracker de costos de Calipso.

Tus tres bocas cuestan distinto:
  - SUSCRIPCIÓN (claude/codex): tarifa FIJA mensual (no por token).
  - API (LiteLLM): POR TOKEN -> el gasto variable que vigilar.
  - LOCAL (Ollama): GRATIS (solo electricidad).

Este módulo lleva un libro mayor (JSONL) de cada petición con tokens + costo
estimado, y produce un reporte mensual: total + desglose por modelo / ruta / día.

Precios y suscripciones se editan abajo (o vía ~/.calipso/pricing.json).
Cuando enciendas LiteLLM, su /spend/logs da el gasto API real y exacto; este
tracker funciona igual sin él usando la tabla de precios.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
LEDGER = CALIPSO_HOME / "costs.jsonl"

# Precio por TOKEN en USD: (entrada, salida).  $/1M tokens / 1e6.
# Aproximados y editables — ajusta a los precios reales de tus proveedores.
PRICING: dict[str, tuple[float, float]] = {
    "deepseek-chat":      (0.27 / 1e6, 1.10 / 1e6),
    "gpt-4o":             (2.50 / 1e6, 10.0 / 1e6),
    "claude-sonnet-4-6":  (3.00 / 1e6, 15.0 / 1e6),
}

# Suscripciones de tarifa FIJA mensual (USD). Edita con tus planes reales.
SUBSCRIPTIONS: dict[str, float] = {
    "claude_max":   100.0,   # tu plan Claude (Pro/Max)
    "chatgpt_plus":  20.0,   # tu plan ChatGPT/Codex
}


def _load_overrides() -> None:
    """Permite sobreescribir precios/suscripciones sin tocar código."""
    cfg = CALIPSO_HOME / "pricing.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            for k, v in data.get("pricing", {}).items():
                PRICING[k] = (v[0], v[1])
            SUBSCRIPTIONS.update(data.get("subscriptions", {}))
        except Exception:
            pass


_load_overrides()


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Costo USD de una petición API según la tabla de precios."""
    pin, pout = PRICING.get(model, (0.0, 0.0))
    return prompt_tokens * pin + completion_tokens * pout


def log_usage(route: str, model: str, prompt_tokens: int = 0,
              completion_tokens: int = 0, client: str | None = None) -> dict:
    """Registra una petición en el libro mayor. Local/suscripción => costo 0
    por token (la suscripción se cuenta aparte como tarifa fija)."""
    cost = estimate_cost(model, prompt_tokens, completion_tokens) if route == "api" else 0.0
    entry = {
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        "route": route, "client": client, "model": model,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "cost_usd": round(cost, 6),
    }
    try:
        CALIPSO_HOME.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return entry


def _iter_ledger():
    if not LEDGER.exists():
        return
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def monthly_report(month: str | None = None) -> dict:
    """Reporte del mes 'YYYY-MM' (por defecto, el actual)."""
    if month is None:
        month = datetime.datetime.now().strftime("%Y-%m")

    api_total = 0.0
    by_model: dict[str, dict] = {}
    by_route: dict[str, dict] = {}
    by_day: dict[str, float] = {}
    requests = 0

    for e in _iter_ledger():
        if not e.get("ts", "").startswith(month):
            continue
        requests += 1
        cost = e.get("cost_usd", 0.0)
        toks = e.get("prompt_tokens", 0) + e.get("completion_tokens", 0)
        api_total += cost
        m = by_model.setdefault(e.get("model", "?"),
                                {"cost": 0.0, "tokens": 0, "requests": 0})
        m["cost"] += cost; m["tokens"] += toks; m["requests"] += 1
        r = by_route.setdefault(e.get("route", "?"),
                                {"cost": 0.0, "tokens": 0, "requests": 0})
        r["cost"] += cost; r["tokens"] += toks; r["requests"] += 1
        day = e.get("ts", "")[:10]
        by_day[day] = by_day.get(day, 0.0) + cost

    subs_total = sum(SUBSCRIPTIONS.values())
    for d in (by_model, by_route):
        for v in d.values():
            v["cost"] = round(v["cost"], 4)
    return {
        "month": month,
        "requests": requests,
        "api_cost_usd": round(api_total, 4),
        "subscriptions_usd": round(subs_total, 2),
        "subscriptions": SUBSCRIPTIONS,
        "grand_total_usd": round(api_total + subs_total, 2),
        "by_model": by_model,
        "by_route": by_route,
        "by_day": {k: round(v, 4) for k, v in sorted(by_day.items())},
    }


if __name__ == "__main__":
    print(json.dumps(monthly_report(), indent=2, ensure_ascii=False))
