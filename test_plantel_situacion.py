"""Tests de lo que el jefe mira antes de decidir (spec seccion 4.1)."""
import json

import pytest

from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.bus import Bus
from calipso.economia.capacidad import Suscripcion
from calipso.economia.cola import Cola
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.plantel import situacion as sit

TS = "2026-08-26T10:00:00"
W = "2026-W35"


@pytest.fixture
def fabrica(tmp_path):
    """Una fabrica chica y de verdad: dos departamentos con plata, la semana
    abierta y una suscripcion. Mismo armado que test_economia_pagador."""
    eco = tmp_path / "economia"
    eco.mkdir()
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=25_000,
                             techo_api_ciclo_mm=3_000,
                             explorar_explotar_pct=30, agresividad_pct=40))
    r.alta(deps.Departamento("mercado", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=15_000))
    sus = {"claude_max": Suscripcion(nombre="claude_max",
                                     costo_mensual_mm=200_000,
                                     capacidad_ciclo=2_000, reserva_personal=200,
                                     costo_api_mm_por_unidad=500)}
    pt.emitir_semana(k, TS, W, 4_000, 1_000)
    k.acunar(TS, W, "dep:atlas", 400_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    k.acunar(TS, W, "dep:mercado", 150_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    return k, r, Bus(eco / "bus.jsonl"), Cola(eco / "cola.jsonl"), sus


def test_la_situacion_trae_la_billetera_y_las_perillas(fabrica):
    k, r, bus, cola, sus = fabrica
    s = sit.situacion(k, r, bus, cola, sus, W, "dep:atlas")
    assert s["cuenta"] == "dep:atlas" and s["nombre"] == "atlas"
    assert s["zona"] == "fabrica"
    assert s["saldo_mm"] == 400_000
    assert s["disponible_mm"] == 400_000
    assert s["presupuesto_semanal_mm"] == 25_000
    assert s["explorar_explotar_pct"] == 30 and s["agresividad_pct"] == 40
    assert s["techo_api_ciclo_mm"] == 3_000 and s["gasto_api_ciclo_mm"] == 0


def test_separa_por_estado_y_por_dueno(fabrica):
    """La distincion que gobierna la decision. Y ojo con los estados del bus:
    `alta` es una propuesta sin financiar; `financiada` es un trabajo vivo.
    `bus.activas()` devuelve SOLO las financiadas."""
    k, r, bus, cola, sus = fabrica
    bus.alta(TS, W, "p1", "dep:atlas", "radar de precios", 10_000, 30_000,
             {"gasto_max_mm": 50_000})
    bus.alta(TS, W, "p2", "dep:mercado", "encuesta", 5_000, 8_000,
             {"gasto_max_mm": 20_000})
    bus.alta(TS, W, "p3", "dep:atlas", "copiar el metodo", 3_000, 6_000,
             {"gasto_max_mm": 9_000})
    bus.marcar(TS, W, "p1", "financiada")      # p1 pasa a ser trabajo vivo

    s = sit.situacion(k, r, bus, cola, sus, W, "dep:atlas")
    assert [x["id"] for x in s["trabajos"]] == ["p1"]
    assert s["trabajos"][0]["titulo"] == "radar de precios"
    assert "gastado_mm" in s["trabajos"][0]
    assert [x["id"] for x in s["propuestas_propias"]] == ["p3"]
    assert [x["id"] for x in s["propuestas_ajenas"]] == ["p2"]
    assert s["propuestas_ajenas"][0]["dueno"] == "dep:mercado"


def test_un_preseed_financiado_no_es_un_trabajo(fabrica):
    """Un pre-seed financiado no produce un trabajo, produce capital: la
    plata ya esta en la cuenta del departamento (no en trabajo:<id>), asi
    que desaparece de `trabajos` en cuanto se financia -mostrarlo ahi seria
    mentirle al jefe sobre que tiene algo pendiente que seguir."""
    k, r, bus, cola, sus = fabrica
    bus.alta(TS, W, "p1", "dep:atlas", "arranco de cero", 200_000, 200_000,
             {"gasto_max_mm": 200_000}, tipo="preseed")
    bus.marcar(TS, W, "p1", "financiada")
    s = sit.situacion(k, r, bus, cola, sus, W, "dep:atlas")
    assert s["trabajos"] == []
    assert s["propuestas_propias"] == []


def test_un_preseed_sin_financiar_cuenta_como_propuesta_propia(fabrica):
    """Mientras espera que Pedro elija, un pre-seed sin financiar SI cuenta
    para el techo de propuestas propias -el mismo motivo por el que
    `TECHO_PROPUESTAS` sigue valiendo para un departamento quebrado."""
    k, r, bus, cola, sus = fabrica
    bus.alta(TS, W, "p1", "dep:atlas", "arranco de cero", 200_000, 200_000,
             {"gasto_max_mm": 200_000}, tipo="preseed")
    s = sit.situacion(k, r, bus, cola, sus, W, "dep:atlas")
    assert [x["id"] for x in s["propuestas_propias"]] == ["p1"]
    assert s["trabajos"] == []


def test_una_propuesta_muerta_ya_no_se_decide(fabrica):
    """Sobre lo liquidado no se opina ni se trabaja: solo ensuciaria el
    prompt y el jefe podria elegir un id que ya no existe."""
    k, r, bus, cola, sus = fabrica
    bus.alta(TS, W, "p1", "dep:mercado", "encuesta", 5_000, 8_000,
             {"gasto_max_mm": 20_000})
    bus.marcar(TS, W, "p1", "financiada")
    bus.marcar(TS, W, "p1", "muerta")
    s = sit.situacion(k, r, bus, cola, sus, W, "dep:atlas")
    assert s["propuestas_ajenas"] == [] and s["trabajos"] == []


def test_la_capacidad_trae_el_precio_de_ahora(fabrica):
    """El jefe necesita saber si sobra capacidad barata para animarse a
    explorar: sin el precio, la perilla explorar/explotar es un numero suelto."""
    k, r, bus, cola, sus = fabrica
    s = sit.situacion(k, r, bus, cola, sus, W, "dep:atlas")
    cap_ = s["capacidad"]
    assert cap_["nombre"] == "claude_max"
    assert cap_["capacidad_fabrica"] == 1_800
    assert cap_["precio_base_mm"] == 100
    assert cap_["consumido"] == 0
    # nada consumido: hoy el precio nunca baja del base, porque el piso del
    # factor sigue en 100. Cuando entre el plan del precio esto pasa a 40 y
    # el sesgo de la Tarea 3 empieza a inclinarse solo.
    assert cap_["precio_mm"] == 100
    assert cap_["fraccion_ciclo_pct"] == 25


def test_sin_suscripciones_la_capacidad_es_none(fabrica):
    k, r, bus, cola, _ = fabrica
    s = sit.situacion(k, r, bus, cola, {}, W, "dep:atlas")
    assert s["capacidad"] is None


def test_una_semana_que_no_es_operativa_no_revienta(fabrica):
    """El jefe puede despertar en una semana sin PT emitido — el ciclo no
    existe y la capacidad no se puede precificar, pero mirar no falla."""
    k, r, bus, cola, sus = fabrica
    s = sit.situacion(k, r, bus, cola, sus, "2026-W99", "dep:atlas")
    assert s["capacidad"] is None
    assert s["saldo_mm"] == 400_000


def test_las_salidas_de_la_semana_alimentan_el_tope_de_agresividad(fabrica):
    """Lo ya comprometido en la semana es contra lo que se mide la
    agresividad: sin esto el tope no puede calcularse."""
    k, r, bus, cola, sus = fabrica
    k.destruir(TS, W, "dep:atlas", 7_000, motivo="api")
    s = sit.situacion(k, r, bus, cola, sus, W, "dep:atlas")
    assert s["salidas_semana_mm"] == 7_000
    assert s["gasto_api_ciclo_mm"] == 7_000


def test_es_deterministica(fabrica):
    """Dos plegados del mismo libro dan lo mismo: es la propiedad que
    permite testearla y la que el mapa ya exige."""
    k, r, bus, cola, sus = fabrica
    assert sit.situacion(k, r, bus, cola, sus, W, "dep:atlas") == \
           sit.situacion(k, r, bus, cola, sus, W, "dep:atlas")


def test_una_propuesta_descartada_desaparece_de_las_propias(fabrica):
    """El jefe tiene un techo de propuestas sin financiar. Descartar una tiene
    que devolverle lugar, o la fabrica se apaga sola al cuarto dia."""
    from calipso.economia import bus as bus_mod
    k, r, b, cola, sus = fabrica
    b.alta(TS, W, "p1", "dep:atlas", "una", 10_000, 10_000,
           {"gasto_max_mm": 10_000})
    antes = sit.situacion(k, r, b, cola, sus, W, "dep:atlas")
    assert len(antes["propuestas_propias"]) == 1
    bus_mod.descartar(b, TS, W, "p1")
    despues = sit.situacion(k, r, b, cola, sus, W, "dep:atlas")
    assert despues["propuestas_propias"] == []
