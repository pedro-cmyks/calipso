"""Tests de eficiencia: atribucion prorrateada por costo API equivalente.

Los tests de arriba montan sus asientos a mano, con la forma VIEJA del
consumo de capacidad (una transferencia a direccion). Los de abajo pasan
por el pagador de verdad, que hoy escribe la forma NUEVA (un consumo de
cristal): sin ellos, este archivo entero podia quedar verde mientras la
eficiencia de produccion informaba cero en silencio, porque el modulo
filtraba por `TipoAsiento.TRANSFERENCIA` y un consumo de cristal le es
invisible — y un denominador vacio no levanta, devuelve cero por mil.
"""
import json

import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import eficiencia as ef
from calipso.economia import pagador as pag
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"
W = "2026-W35"
SEMANAS = [W]

SUS = {"claude_max": cap.Suscripcion("claude_max", 100_000, 1_000, 200, 500)}


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


def _montar_trabajo(k, id, api_mm, unidades):
    """Trabajo con gasto de API y de capacidad, etiquetado por ref."""
    ref = f"trabajo:{id}"
    k.acunar(TS, W, f"trabajo:{id}", api_mm + 100_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    k.destruir(TS, W, f"trabajo:{id}", api_mm, motivo="api", ref=ref)
    k.transferir(TS, W, f"trabajo:{id}", t.DIRECCION, unidades * 100,
                 motivo="capacidad", ref=ref,
                 detalle_extra={"suscripcion": "claude_max",
                                "unidades": unidades})


def test_costos_de_trabajo_en_api_equivalente(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    costos = ef.costos_de_trabajo(k.libro.asientos(), "p1", SUS)
    # capacidad: 100 unidades * 500 mm api-equiv = 50_000
    assert costos == {"api": 50_000, "sus:claude_max": 50_000}


def test_atribucion_prorratea_por_costo(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"}, detalle_extra={"trabajo": "p1"})
    atribuida = ef.atribucion_por_suscripcion(k.libro.asientos(), SEMANAS, SUS)
    assert atribuida == {"claude_max": 15_000}  # 30k * 50k/100k


def test_eficiencia_por_suscripcion(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"}, detalle_extra={"trabajo": "p1"})
    got = ef.eficiencia_suscripcion(k.libro.asientos(), SUS["claude_max"],
                                    SEMANAS, SUS)
    assert got == 300  # 15_000 * 1000 // 50_000


def test_eficiencia_departamento(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"}, detalle_extra={"trabajo": "p1"})
    got = ef.eficiencia_departamento(k.libro.asientos(), "dep:a", SEMANAS,
                                     SUS, duenos={"p1": "dep:a"})
    assert got == 300  # 30_000 * 1000 // 100_000


def test_eficiencia_departamento_ventana_y_gasto_directo(k):
    """El denominador respeta la ventana y suma el gasto directo del dep."""
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)  # 100k equiv en W35
    # gasto del trabajo FUERA de la ventana: excluido
    k.destruir(TS, "2026-W34", "trabajo:p1", 10_000, motivo="api",
               ref="trabajo:p1")
    # gasto directo del departamento EN la ventana: 20k
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    k.destruir(TS, W, "dep:a", 20_000, motivo="api")
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"}, detalle_extra={"trabajo": "p1"})
    got = ef.eficiencia_departamento(k.libro.asientos(), "dep:a", SEMANAS,
                                     SUS, duenos={"p1": "dep:a"})
    assert got == 250  # 30_000 * 1000 // (100_000 + 20_000)


def test_capital_y_ventas_sin_trabajo_no_atribuyen(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    k.acunar(TS, W, t.TESORO, 1_000_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    k.acunar(TS, W, "dep:a", 99_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"})  # venta sin trabajo: no atribuible
    atribuida = ef.atribucion_por_suscripcion(k.libro.asientos(), SEMANAS, SUS)
    assert atribuida == {}


def test_eficiencia_sin_consumo_es_cero():
    assert ef.eficiencia_pormil(0, 0) == 0
    assert ef.eficiencia_pormil(5_000, 0) == 0


# -- por el camino de produccion -------------------------------------------
@pytest.fixture
def economia(tmp_path):
    """Un pagador de verdad sobre una economia minima: el unico camino por
    el que entra un cargo de suscripcion de fabrica en produccion.

    Devuelve solo el pagador: cada lectura y cada escritura pide un
    `leer_kernel()` fresco, porque el pagador escribe con el suyo y un
    Kernel viejo tiene el libro cacheado en memoria (escribir con el
    duplicaria el `seq`).
    """
    eco = tmp_path / "economia"
    eco.mkdir()
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA,
                             techo_api_ciclo_mm=500_000))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    return pag.Pagador.desde_entorno(tmp_path)


def test_la_eficiencia_ve_el_consumo_que_escribe_el_pagador(economia):
    """El agujero que este test tapa: el pagador cobra la suscripcion en
    cristales y `eficiencia` filtraba por transferencia. Con el denominador
    ciego, `eficiencia_suscripcion` no falla — informa 0 por mil, y ese
    numero va derecho al informe de renovacion que lee Pedro."""
    p = economia
    b = bus_mod.Bus(p.ruta_bus)
    b.alta(TS, W, "p1", "dep:a", "radar", 10_000, 20_000,
           {"gasto_max_mm": 50_000})
    p.cargar_suscripcion(TS, W, "trabajo:p1", "claude_max", unidades=100)
    assert p.pendientes() == []
    p.leer_kernel().acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
                           {"tipo": "firma_pedro"},
                           detalle_extra={"trabajo": "p1"})

    asientos = p.leer_kernel().libro.asientos()
    # 100 unidades x 500 mm de API equivalente = 50.000, igual que si la
    # unidad se hubiera comprado en monedas: cambia la divisa del asiento,
    # no lo que esa capacidad vale medida en API
    assert ef.costos_de_trabajo(asientos, "p1", SUS) == {"sus:claude_max": 50_000}
    assert ef.eficiencia_suscripcion(asientos, SUS["claude_max"],
                                     SEMANAS, SUS) == 600
    assert ef.eficiencia_departamento(asientos, "dep:a", SEMANAS, SUS,
                                      duenos={"p1": "dep:a"}) == 600


def test_el_consumo_directo_del_departamento_no_se_pierde_ni_se_duplica(
        economia):
    """`costo_api_directo` descartaba TODO consumo de cristal antes de
    mirarle el tipo: el origen de un consumo es el POOL, nunca la cuenta
    del departamento, que viaja en `detalle['titular']`. Y el corte tiene
    que seguir separando lo directo de lo de un trabajo, o
    `eficiencia_departamento` cuenta dos veces el mismo consumo (una por
    titular y otra por ref)."""
    p = economia
    b = bus_mod.Bus(p.ruta_bus)
    b.alta(TS, W, "p1", "dep:a", "radar", 10_000, 20_000,
           {"gasto_max_mm": 50_000})
    p.cargar_suscripcion(TS, W, "dep:a", "claude_max", unidades=10)
    p.cargar_suscripcion(TS, W, "trabajo:p1", "claude_max", unidades=100)
    assert p.pendientes() == []

    asientos = p.leer_kernel().libro.asientos()
    # lo directo: 10 unidades del departamento, y NO las 100 del trabajo
    assert ef.costo_api_directo(asientos, "dep:a", SEMANAS, SUS) == 5_000
    assert ef.costos_de_trabajo(asientos, "p1", SUS) == {"sus:claude_max": 50_000}
    # el denominador del departamento es la suma, sin repetir el trabajo
    p.leer_kernel().acunar(TS, W, "dep:a", 55_000, t.SubtipoAcunacion.VENTA,
                           {"tipo": "firma_pedro"},
                           detalle_extra={"trabajo": "p1"})
    assert ef.eficiencia_departamento(p.leer_kernel().libro.asientos(),
                                      "dep:a", SEMANAS, SUS,
                                      duenos={"p1": "dep:a"}) == 1_000
