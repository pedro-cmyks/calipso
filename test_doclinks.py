#!/usr/bin/env python3
"""
test_doclinks.py - validador de links/rutas: catch de drift sin falsos positivos.
"""
from __future__ import annotations

import pathlib
import tempfile

from calipso import doclinks


def check(name: str, cond: bool, fails: list[str]) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def main() -> int:
    fails: list[str] = []

    # 1) Los docs reales del repo no tienen referencias internas rotas.
    real = doclinks.audit()
    check("docs reales sin links rotos", real["ok"], fails)
    check("revisa varias referencias", real["checked"] >= 10, fails)
    if not real["ok"]:
        print("   broken:", real["broken"])

    # 2) En un repo sintetico, detecta una ref rota y no marca las validas.
    with tempfile.TemporaryDirectory() as d:
        root = pathlib.Path(d)
        (root / "calipso").mkdir()
        (root / "calipso" / "server.py").write_text("x", encoding="utf-8")
        (root / "test_real.py").write_text("x", encoding="utf-8")
        (root / "SPEC.md").write_text(
            "Existe `calipso/server.py` y `test_real.py`.\n"
            "No existe `calipso/fantasma.py` ni `test_nope.py`.\n"
            "Ignora URLs `https://github.com/x/y` y runtime `~/.calipso/x.json` "
            "y placeholders `<slug>` y `CALIPSO_HOME/routines.json`.\n",
            encoding="utf-8")
        res = doclinks.audit(root)
        refs = {b["ref"] for b in res["broken"]}
        check("detecta calipso/fantasma.py", "calipso/fantasma.py" in refs, fails)
        check("detecta test_nope.py", "test_nope.py" in refs, fails)
        check("no marca calipso/server.py", "calipso/server.py" not in refs, fails)
        check("no marca test_real.py", "test_real.py" not in refs, fails)
        check("ignora URL", not any("github.com" in r for r in refs), fails)
        check("ignora runtime ~", not any(r.startswith("~") for r in refs), fails)
        check("ignora CALIPSO_HOME", not any("CALIPSO_HOME" in r for r in refs), fails)

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: validador de links/rutas verificable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
