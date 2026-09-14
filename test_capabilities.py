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
    d4 = cap.parse_directives("/nube mi numero es 3865-4421, buscame vuelos")
    check("parse /nube -> nube True", d4["nube"] is True)
    check("parse /nube limpia el slash", "/nube" not in d4["clean"])
    check("parse /nube conserva el resto", "buscame vuelos" in d4["clean"])
    d5 = cap.parse_directives("hola que tal")
    check("sin /nube -> nube False", d5["nube"] is False)

    d6 = cap.parse_directives("/redacta respondele que si a este mensaje")
    check("parse /redacta -> redacta True", d6["redacta"] is True)
    check("parse /redacta limpia el slash", "/redacta" not in d6["clean"])
    check("parse /redacta conserva el resto", "respondele" in d6["clean"])
    check("sin /redacta -> redacta False", cap.parse_directives("hola")["redacta"] is False)
    d7 = cap.parse_directives("/otra")
    check("parse /otra -> otra True", d7["otra"] is True)
    check("sin /otra -> otra False", cap.parse_directives("hola")["otra"] is False)

    d8 = cap.parse_directives("/mia respondele a ana que confirmo")
    check("parse /mia -> mia True", d8["mia"] is True)
    check("parse /mia limpia el slash", "/mia" not in d8["clean"])
    check("parse /mia conserva el resto", "respondele a ana" in d8["clean"])
    check("sin /mia -> mia False", cap.parse_directives("hola")["mia"] is False)

    # /goal (spec goals 2026-09-13, seccion 4): el resto CRUDO, con las rutas
    # absolutas que :244 borra de `clean`, y `meta:` como alias
    d9 = cap.parse_directives("/goal crea saludo.py hasta: pytest en verde en: /tmp/repo")
    check("parse /goal -> goal con el resto crudo",
          d9["goal"] == "crea saludo.py hasta: pytest en verde en: /tmp/repo")
    check("parse /goal limpia el slash de clean", "/goal" not in d9["clean"])
    check("sin /goal -> goal None", cap.parse_directives("hola")["goal"] is None)
    check("parse /goal solo -> goal vacio", cap.parse_directives("/goal")["goal"] == "")
    d10 = cap.parse_directives("meta: dejame listo el iPhone")
    check("parse meta: -> goal", d10["goal"] == "dejame listo el iPhone")
    d11 = cap.parse_directives("/goal /claude crea saludo.py")
    check("parse /goal saca los slash del texto", d11["goal"] == "crea saludo.py")
    check("parse /goal /claude fuerza la ruta", d11["force_route"] == "subscription"
          and d11["force_model"] == "claude")
    check("un /goal en el medio no es goal",
          cap.parse_directives("hola /goal x")["goal"] is None)
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
