#!/usr/bin/env python3
"""
test_plantel_ilegibles.py — la valvula de la gramatica de proponer.
"""
from calipso.plantel import ilegibles

W = "2026-W36"
OTRA_SEMANA = "2026-W37"


def test_lo_ilegible_queda_anotado(tmp_path):
    ilegibles.anotar(tmp_path, W, "dep:atlas", "una idea larga")
    filas = ilegibles.colapsados(tmp_path, W)
    assert len(filas) == 1
    assert filas[0]["crudo"] == "una idea larga"
    assert filas[0]["veces"] == 1


def test_el_mismo_texto_se_colapsa_con_su_contador(tmp_path):
    """A temperatura 0 la repeticion es byte a byte: 200 tics tienen que dar
    una fila con un contador, no 200 filas."""
    for _ in range(200):
        ilegibles.anotar(tmp_path, W, "dep:atlas", "la misma idea")
    filas = ilegibles.colapsados(tmp_path, W)
    assert len(filas) == 1 and filas[0]["veces"] == 200


def test_dos_departamentos_no_se_mezclan(tmp_path):
    ilegibles.anotar(tmp_path, W, "dep:atlas", "misma idea")
    ilegibles.anotar(tmp_path, W, "dep:taller", "misma idea")
    assert len(ilegibles.colapsados(tmp_path, W)) == 2


def test_sin_archivo_la_lista_es_vacia(tmp_path):
    assert ilegibles.colapsados(tmp_path, W) == []


def test_una_linea_rota_no_voltea_la_lectura(tmp_path):
    """Append-only escrito por un proceso que puede morir a la mitad: una
    linea cortada no puede esconder las demas."""
    ilegibles.anotar(tmp_path, W, "dep:atlas", "buena")
    ruta = ilegibles.ruta(tmp_path)
    with ruta.open("a", encoding="utf-8") as f:
        f.write("{esto no es json\n")
    assert len(ilegibles.colapsados(tmp_path, W)) == 1


def test_una_linea_con_bytes_invalidos_no_revienta_la_lectura(tmp_path):
    """El corte a mitad de escritura REAL: `anotar` escribe en castellano
    con `ensure_ascii=False`, asi que un proceso que muere a mitad de un
    caracter multibyte deja UTF-8 invalido, no solo JSON invalido -- ese es
    EL caso realista, no uno raro. `UnicodeDecodeError` no es un `OSError`;
    sin `errors="replace"` en la lectura, esto tumbaria TODA la lectura
    antes incluso de llegar a separar las lineas, y una linea rota si
    esconderia todas las demas."""
    ilegibles.anotar(tmp_path, W, "dep:atlas", "buena")
    ruta = ilegibles.ruta(tmp_path)
    with ruta.open("ab") as f:
        # el arranque de una "ñ" en utf-8 (0xC3 0xB1) sin su byte de
        # continuacion: la escritura murio a mitad del caracter
        f.write(b'{"crudo": "campa\xc3')
    assert len(ilegibles.colapsados(tmp_path, W)) == 1


def test_una_semana_no_ve_lo_ilegible_de_otra(tmp_path):
    """`semana` filtra de verdad: sin esto, `veces` es un contador de por
    vida y un ilegible de hace tres meses no se va nunca de la bandeja."""
    ilegibles.anotar(tmp_path, W, "dep:atlas", "de esta semana")
    ilegibles.anotar(tmp_path, OTRA_SEMANA, "dep:atlas", "de la otra semana")
    filas = ilegibles.colapsados(tmp_path, W)
    assert len(filas) == 1 and filas[0]["crudo"] == "de esta semana"
