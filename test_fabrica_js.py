"""
test_fabrica_js.py — Puente: pytest corre tambien los tests del cliente.

Los modulos de calipso/web/fabrica son JavaScript puro, sin DOM, y se
testean con el runner que Node trae de fabrica. Se corren desde aca para
que `pytest` siga siendo el unico comando que hay que saber.
"""
from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest

FABRICA = pathlib.Path(__file__).parent / "calipso" / "web" / "fabrica"


def node() -> str | None:
    """Node del PATH, o el que fnm haya instalado. None si no hay."""
    directo = shutil.which("node")
    if directo:
        return directo
    versiones = sorted(
        (pathlib.Path.home() / ".local/share/fnm/node-versions")
        .glob("v*/installation/bin/node"))
    return str(versiones[-1]) if versiones else None


def test_los_modulos_del_cliente_pasan_sus_tests():
    ejecutable = node()
    if ejecutable is None:
        pytest.skip("node no esta instalado: los tests del cliente NO corrieron")
    # el directorio va como cwd, NO como argumento: Node 22 trata un
    # argumento posicional como modulo de entrada y sale con
    # "Cannot find module <dir>" sin correr un solo test
    r = subprocess.run([ejecutable, "--test"], cwd=str(FABRICA),
                       capture_output=True, text=True, timeout=180)
    assert r.returncode == 0, r.stdout + r.stderr
