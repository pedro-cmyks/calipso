#!/usr/bin/env python3
"""
test_capabilities.py — Ruteo a nivel de MODELO: afinidad + tier + intensidad.

Verifica lo que pidió Pedro:
  - tarea trivial rápida -> modelo chico/barato (Haiku/local), no Opus.
  - repo/código -> Codex (Arquímedes), por afinidad.
  - razonar con /ultrathink -> exige tier frontier (Opus/Aristóteles).
  - parse_directives capta slash y palabras de intensidad.
  - discover() agrega un modelo nuevo con prior por tier + persona.
"""
from calipso import capabilities as cap

ALL = {k: True for k in cap.REGISTRY}


def top(features, effort):
    r = cap.choose(features, effort, ALL)
    return (r[0]["key"], r[0]["persona"]) if r else (None, None)


def main() -> int:
    fails = []

    def check(name, cond, extra=""):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' ' + extra) if extra else ''}")
        if not cond:
            fails.append(name)

    # trivial rápido -> modelo chico (tier small). No Opus.
    k, p = top({"type": "translate", "complexity": 1}, cap.EFFORT["fast"])
    check("trivial rápido -> tier small", cap.REGISTRY[k]["tier"] == "small", f"({p}:{k})")

    # repo/código -> Codex (gpt-5.5 disponible con la cuenta ChatGPT)
    k, p = top({"type": "repo", "complexity": 4}, cap.EFFORT["think"])
    check("repo -> Codex", k == "subscription:codex:gpt-5.5", f"({p})")

    # razonar con ultra -> exige frontier (Opus o superior)
    k, p = top({"type": "reasoning", "complexity": 3}, cap.EFFORT["ultra"])
    check("ultra reasoning -> frontier+", cap.TIER_RANK[cap.REGISTRY[k]["tier"]] >= 2, f"({p}:{k})")
    check("ultra reasoning -> Opus (Aristóteles)", k == "subscription:claude:opus", f"({p})")

    # ultra excluye los chicos
    ranked = cap.choose({"type": "reasoning", "complexity": 3}, cap.EFFORT["ultra"], ALL)
    smalls = [r for r in ranked if cap.REGISTRY[r["key"]]["tier"] == "small"]
    check("ultra excluye tier small", len(smalls) == 0)

    # parse_directives
    d = cap.parse_directives("arregla el bug /ultrathink")
    check("parse /ultrathink -> effort ultra", d["effort"] == cap.EFFORT["ultra"])
    check("parse limpia el slash", "/ultrathink" not in d["clean"])
    d2 = cap.parse_directives("resume esto rápido")
    check("palabra 'rápido' -> effort fast", d2["effort"] == cap.EFFORT["fast"])
    d3 = cap.parse_directives("/model opus piensa")
    check("/model captura el modelo", d3["force_model"] == "opus")

    # discovery
    reg = dict(cap.REGISTRY)
    key = cap.discover("api", "gpt-5.5", tier="frontier", registry=reg)
    check("discover agrega modelo nuevo", key == "api:gpt-5.5" and key in reg)
    check("discover asigna persona", bool(reg[key].get("persona")))

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: ruteo a nivel de modelo + intensidad + descubrimiento")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
