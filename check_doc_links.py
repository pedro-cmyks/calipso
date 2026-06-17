#!/usr/bin/env python3
"""
check_doc_links.py - corre el validador de links/rutas de la documentacion.

Sale 0 si todas las referencias internas existen; 1 si hay drift. Pensado para
correr como comando allowlist de verificacion (`docs_links`).
"""
from __future__ import annotations

from calipso import doclinks


def main() -> int:
    result = doclinks.audit()
    print(f"refs internas revisadas: {result['checked']}")
    if result["ok"]:
        print("OK: todas las referencias internas de los docs existen")
        return 0
    print("ROTAS:")
    for b in result["broken"]:
        print(f"  - {b['doc']}: {b['ref']}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
