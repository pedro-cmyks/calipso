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

# Piso deliberadamente flojo: no es un trinquete sobre cuantos tests hay
# (hoy 111), es una red contra que desaparezcan TODOS de golpe.
PISO_DE_TESTS = 90


def node() -> str | None:
    """Node del PATH, o el que fnm haya instalado. None si no hay."""
    directo = shutil.which("node")
    if directo:
        return directo
    versiones = sorted(
        (pathlib.Path.home() / ".local/share/fnm/node-versions")
        .glob("v*/installation/bin/node"))
    return str(versiones[-1]) if versiones else None


def conteo_tap(salida: str, etiqueta: str) -> int | None:
    """El numero de la linea de resumen `# <etiqueta> N`, o None si no esta."""
    visto = None
    for linea in salida.splitlines():
        partes = linea.strip().split()
        if len(partes) == 3 and partes[0] == "#" and partes[1] == etiqueta:
            try:
                visto = int(partes[2])
            except ValueError:
                pass
    return visto


def test_los_modulos_del_cliente_pasan_sus_tests():
    ejecutable = node()
    if ejecutable is None:
        pytest.skip("node no esta instalado: los tests del cliente NO corrieron")
    # el directorio va como cwd, NO como argumento: Node 22 trata un
    # argumento posicional como modulo de entrada y sale con
    # "Cannot find module <dir>" sin correr un solo test
    r = subprocess.run([ejecutable, "--test"], cwd=str(FABRICA),
                       capture_output=True, text=True, timeout=180)
    salida = r.stdout + r.stderr
    assert r.returncode == 0, salida
    # Codigo 0 no alcanza: `node --test` en un directorio sin archivos de
    # test imprime "# pass 0" y sale con 0. Sin mirar el conteo, el dia que
    # los *.test.js se muevan, se renombren o cambie el glob del runner, los
    # tests del cliente desaparecen enteros y la suite sigue en verde.
    pasaron = conteo_tap(salida, "pass")
    fallaron = conteo_tap(salida, "fail")
    assert pasaron is not None and fallaron is not None, (
        "no se pudo leer el resumen TAP de node --test; salida completa:\n"
        + salida)
    assert fallaron == 0, f"fallaron {fallaron} tests del cliente:\n{salida}"
    assert pasaron >= PISO_DE_TESTS, (
        f"solo pasaron {pasaron} tests del cliente y el piso es "
        f"{PISO_DE_TESTS}: o se movieron los *.test.js de {FABRICA}, o "
        f"cambio el glob con el que el runner los junta.\n{salida}")
