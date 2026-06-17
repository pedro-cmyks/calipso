#!/usr/bin/env python3
"""
test_launch.py - checklist de salud para lanzamiento personal.
"""
from __future__ import annotations

import os
import tempfile

_HOME = tempfile.mkdtemp(prefix="calipso_launch_")
os.environ["CALIPSO_HOME"] = _HOME
os.environ["CALIPSO_TOKEN"] = "test-token"

from fastapi.testclient import TestClient  # noqa: E402

import calipso.server as server  # noqa: E402


def check(name: str, cond: bool, fails: list[str]) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def main() -> int:
    fails: list[str] = []
    client = TestClient(server.app)
    r = client.get("/api/launch/checklist?token=test-token")
    check("endpoint responde", r.status_code == 200, fails)
    data = r.json()
    keys = {item["key"] for item in data.get("items", [])}
    check("incluye servidor", "server" in keys, fails)
    check("incluye seguridad", {"security_token", "totp"}.issubset(keys), fails)
    check("incluye PWA/lanzadores", {"pwa", "launchers"}.issubset(keys), fails)
    check("incluye modelos", "models" in keys, fails)
    check("summary humano", bool(data.get("summary")), fails)

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: checklist de lanzamiento verificable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
