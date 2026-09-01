#!/usr/bin/env python3
"""
test_plantel_ilegibles.py — la valvula de la gramatica de proponer.
"""
from calipso.plantel import ilegibles

W = "2026-W36"


def test_lo_ilegible_queda_anotado(tmp_path):
    ilegibles.anotar(tmp_path, W, "dep:atlas", "una idea larga")
    filas = ilegibles.colapsados(tmp_path)
    assert len(filas) == 1
    assert filas[0]["crudo"] == "una idea larga"
    assert filas[0]["veces"] == 1


def test_el_mismo_texto_se_colapsa_con_su_contador(tmp_path):
    """A temperatura 0 la repeticion es byte a byte: 200 tics tienen que dar
    una fila con un contador, no 200 filas."""
    for _ in range(200):
        ilegibles.anotar(tmp_path, W, "dep:atlas", "la misma idea")
    filas = ilegibles.colapsados(tmp_path)
    assert len(filas) == 1 and filas[0]["veces"] == 200


def test_dos_departamentos_no_se_mezclan(tmp_path):
    ilegibles.anotar(tmp_path, W, "dep:atlas", "misma idea")
    ilegibles.anotar(tmp_path, W, "dep:taller", "misma idea")
    assert len(ilegibles.colapsados(tmp_path)) == 2


def test_sin_archivo_la_lista_es_vacia(tmp_path):
    assert ilegibles.colapsados(tmp_path) == []


def test_una_linea_rota_no_voltea_la_lectura(tmp_path):
    """Append-only escrito por un proceso que puede morir a la mitad: una
    linea cortada no puede esconder las demas."""
    ilegibles.anotar(tmp_path, W, "dep:atlas", "buena")
    ruta = ilegibles.ruta(tmp_path)
    with ruta.open("a", encoding="utf-8") as f:
        f.write("{esto no es json\n")
    assert len(ilegibles.colapsados(tmp_path)) == 1
