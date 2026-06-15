#!/usr/bin/env python3
"""
test_capabilities.py — El router por puntaje elige por AFINIDAD, no por orden.

Verifica los casos que pidió Pedro:
  - código/repo -> codex gana a claude (afinidad, no orden fijo).
  - razonar/escribir -> claude gana a codex.
  - se prefiere suscripción (costo ~0) sobre API paga cuando ambas sirven.
  - trivial/privado -> local (gratis, y único apto si es privado).
  - si la suscripción ganadora tiene cuota agotada, pasa al siguiente APTO
    (otra suscripción o API), no a local por defecto.
"""
from calipso import capabilities as cap

ALL = {k: True for k in cap.DEFAULT_BACKENDS}


def top(features, available=None, quota_low=None):
    r = cap.choose(features, available or ALL, quota_low)
    return r[0]["key"] if r else None, r


def main() -> int:
    fails = []

    def check(name, got, expected):
        ok = got == expected
        print(f"  [{'OK' if ok else 'FAIL'}] {name}: {got}"
              + ("" if ok else f"  (esperaba {expected})"))
        if not ok:
            fails.append(name)

    # repo/código -> codex
    g, r = top({"type": "repo", "complexity": 4})
    check("repo -> codex", g, "subscription:codex")

    # refactor de código -> codex (mejor en code/repo)
    g, _ = top({"type": "code", "complexity": 4})
    check("code -> codex", g, "subscription:codex")

    # razonar -> claude por encima de codex
    g, r = top({"type": "reasoning", "complexity": 3})
    check("reasoning -> claude", g, "subscription:claude")

    # escribir -> claude
    g, _ = top({"type": "writing", "complexity": 3})
    check("writing -> claude", g, "subscription:claude")

    # suscripción preferida sobre API paga cuando ambas sirven (razonar)
    keys = [x["key"] for x in r]
    sub_before_api = (keys.index("subscription:claude")
                      < keys.index("api:deepseek-chat"))
    check("suscripcion antes que api", sub_before_api, True)

    # trivial/privado -> local (y único apto si privado)
    g, r = top({"type": "translate", "complexity": 1, "private": True})
    check("privado -> local", g, "local")
    check("privado excluye no-locales", len(r), 1)

    # cuota de claude agotada en tarea de razonar -> siguiente apto (no local)
    g, _ = top({"type": "reasoning", "complexity": 4},
               quota_low={"subscription:claude": True})
    check("claude sin cuota -> otra suscripcion/api (no local)",
          g in ("subscription:codex", "api:deepseek-chat"), True)

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: el router puntua y selecciona por afinidad/costo/cuota")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
