#!/usr/bin/env python3
"""
test_catastro_server.py - integracion del catastro con el servidor: el
techo de ROOT en `_switch_project` (hallazgo S4 del spec de ojos y manos,
"El techo de ROOT va en _switch_project, no en el endpoint de abrir
proyecto"), `_repo_brief` recibiendo la raiz como parametro, los dos
endpoints GET /api/catastro, y la migracion de la rutina catastro en el
arranque.

El trabajo real corre en `_catastro_server_subproceso.py`, en un PROCESO
PROPIO -- nunca adentro de este proceso de pytest. La razon esta en el
docstring de ese archivo: `calipso.server` fija `CALIPSO_HOME` (y cada
submodulo el suyo: memory.py, jobs.py, chats.py...) la primera vez que
algo lo importa en el proceso, y si otro archivo de la suite
(`test_seguridad_puertas.py`, `test_economia_brief.py`, `test_mesa_
server.py`...) ya hizo ese import con el `~/.calipso` real antes de que
este archivo corriera, fijar variables de entorno despues no cambia nada:
el modulo ya esta en `sys.modules`. Se probo asi primero y escribia en el
`~/.calipso` real de Pedro. Un proceso nuevo no tiene ese problema.

Este archivo solo lanza el subproceso UNA vez (fixture de modulo) y
convierte cada resultado en un test propio, para que quede legible en el
reporte de pytest cual fallo -- no para volver a correr la logica aca.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

import pytest

_SCRIPT = pathlib.Path(__file__).with_name("_catastro_server_subproceso.py")


@pytest.fixture(scope="module")
def resultados():
    with tempfile.TemporaryDirectory(prefix="calipso_catastro_srv_out_") as tmp:
        salida = pathlib.Path(tmp) / "resultado.json"
        proc = subprocess.run(
            [sys.executable, str(_SCRIPT), str(salida)],
            capture_output=True, text=True, timeout=120)
        if proc.returncode != 0 or not salida.exists():
            raise AssertionError(
                "el subproceso de test_catastro_server.py no termino bien "
                f"(returncode={proc.returncode}):\n"
                f"--- stdout ---\n{proc.stdout}\n"
                f"--- stderr ---\n{proc.stderr}")
        return json.loads(salida.read_text(encoding="utf-8"))


def _afirmar(resultados: dict, nombre: str) -> None:
    ok = resultados["resultados"].get(nombre)
    error = resultados["errores"].get(nombre)
    assert ok is True, f"{nombre} fallo en el subproceso: {error}"


def test_switch_project_dentro_de_una_raiz_declarada_funciona(resultados):
    _afirmar(resultados, "switch_project_dentro_de_una_raiz_declarada_funciona")


def test_switch_project_fuera_de_las_raices_da_400_y_no_mueve_root(resultados):
    _afirmar(resultados, "switch_project_fuera_de_las_raices_da_400_y_no_mueve_root")


def test_switch_project_la_raiz_no_puede_ser_barra(resultados):
    _afirmar(resultados, "switch_project_la_raiz_no_puede_ser_barra")


def test_api_project_open_delega_en_switch_project_y_respeta_el_techo(resultados):
    _afirmar(resultados, "api_project_open_delega_en_switch_project_y_respeta_el_techo")


def test_api_chats_con_project_path_en_el_body_respeta_el_techo(resultados):
    _afirmar(resultados, "api_chats_con_project_path_en_el_body_respeta_el_techo")


def test_activate_respeta_el_techo(resultados):
    _afirmar(resultados, "activate_respeta_el_techo")


def test_repo_brief_no_mueve_root_y_describe_otro_proyecto(resultados):
    _afirmar(resultados, "repo_brief_no_mueve_root_y_describe_otro_proyecto")


def test_endpoint_catastro_lista(resultados):
    _afirmar(resultados, "endpoint_catastro_lista")


def test_endpoint_catastro_detalle_404_si_no_existe(resultados):
    _afirmar(resultados, "endpoint_catastro_detalle_404_si_no_existe")


def test_endpoint_catastro_detalle_trae_el_brief_sin_mover_root(resultados):
    _afirmar(resultados, "endpoint_catastro_detalle_trae_el_brief_sin_mover_root")


def test_asegurar_rutina_catastro_agrega_si_falta_y_es_idempotente(resultados):
    _afirmar(resultados, "asegurar_rutina_catastro_agrega_si_falta_y_es_idempotente")
