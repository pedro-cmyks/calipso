#!/usr/bin/env python3
"""
test_sessions.py — Perfiles de sesión: nombres por sesión + config por agente.
"""
import os
import tempfile

os.environ["CALIPSO_HOME"] = tempfile.mkdtemp(prefix="calipso_sess_")

from calipso import sessions, capabilities  # noqa: E402


def main() -> int:
    fails = []

    def check(name, cond):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}")
        if not cond:
            fails.append(name)

    s1 = sessions.create("uno")
    s2 = sessions.create("dos")

    # cada sesión tiene su propio roster (nombres distintos)
    a_mid = list(capabilities.REGISTRY)[0]
    n1 = s1["agents"][a_mid]["name"]
    n2 = s2["agents"][a_mid]["name"]
    check("rosters distintos por sesión", n1 != n2)
    check("todos los modelos tienen agente", len(s1["agents"]) == len(capabilities.REGISTRY))

    # configurar un agente: nombre + intensidad + enabled
    mid = "subscription:claude:opus"
    sessions.set_agent(s2["id"], mid, name="Newton", intensity="ultra")
    sessions.set_agent(s2["id"], "local:qwen2.5:3b", enabled=False)
    prof = sessions.load(s2["id"])
    check("renombró el agente", prof["agents"][mid]["name"] == "Newton")
    check("fijó intensidad del agente", prof["agents"][mid]["intensity"] == "ultra")
    check("deshabilitó un agente", prof["agents"]["local:qwen2.5:3b"]["enabled"] is False)

    # activa() devuelve la última activa (s2)
    check("sesión activa = s2", sessions.active()["id"] == s2["id"])

    # cambiar de activa
    sessions.set_active(s1["id"])
    check("cambió de sesión activa", sessions.active()["id"] == s1["id"])

    # intensidad inválida -> error
    try:
        sessions.set_agent(s1["id"], mid, intensity="turbo")
        check("rechaza intensidad inválida", False)
    except ValueError:
        check("rechaza intensidad inválida", True)

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: perfiles de sesión (nombres + intensidad + enabled por agente)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
