"""Tests del bus de propuestas: eventos, financiacion, muerte y liquidacion."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import mercado as mkt
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"

SUS = cap.Suscripcion(nombre="claude_max", costo_mensual_mm=100_000,
                      capacidad_ciclo=1_000, reserva_personal=200,
                      costo_api_mm_por_unidad=500)


@pytest.fixture
def entorno(tmp_path):
    k = Kernel(Libro(tmp_path / "libro.jsonl"))
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA, techo_api_ciclo_mm=500_000))
    r.alta(deps.Departamento("b", deps.ZONA_FABRICA, techo_api_ciclo_mm=500_000))
    m = mkt.Mercado(k, r, {"claude_max": SUS})
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    return k, m, b


def _capital(k, monto, destino):
    k.acunar(TS, "2026-W30", destino, monto, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})


def _semana_op(k, semana):
    pt.emitir_semana(k, TS, semana, 4_000, 0)
    pt.expirar_pools(k, TS, semana)


CRITERIO = {"gasto_max_mm": 50_000}


def test_alta_estado_y_persistencia(tmp_path, entorno):
    k, m, b = entorno
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar vertical x",
           presupuesto_mm=100_000, retorno_mm=300_000, criterio=CRITERIO)
    assert b.estado("p1") == "alta"
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "p1", "dep:a", "repetida", 1, 1, CRITERIO)
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "p2", "dep:a", "sin criterio", 1, 1, {})
    b2 = bus_mod.Bus(tmp_path / "bus.jsonl")
    assert b2.estado("p1") == "alta"
    with pytest.raises(bus_mod.ErrorBus):
        b2.estado("fantasma")


def test_alta_valida_valores(entorno):
    k, m, b = entorno
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "v1", "dep:a", "malo", 100_000, 300_000,
               {"gasto_max_mm": "abc"})
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "v2", "dep:a", "malo", 100_000, 300_000,
               {"semanas_max": -5})
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "v3", "dep:a", "malo", 0, 300_000,
               {"gasto_max_mm": 50_000})


def test_financiar_transfiere_y_marca(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    _capital(k, 100_000, "dep:b")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 60_000)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:b", 40_000)  # cofinancia
    assert b.estado("p1") == "financiada"
    assert b.datos("p1")["semana_financiada"] == "2026-W30"
    asientos = k.libro.asientos()
    assert k.saldo("trabajo:p1") == 100_000
    assert bus_mod.aportes(asientos, "p1") == {"dep:a": 60_000, "dep:b": 40_000}


def test_no_se_financia_propuesta_de_congelado(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:b")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    deps.declarar_quiebra(k, TS, "2026-W30", "dep:a")
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:b", 10_000)


def test_gastado_pliega_todas_las_salidas(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 80_000)
    # el trabajo gasta por la puerta del Mercado, con dueno explicito
    m.gastar_api(TS, "2026-W30", "trabajo:p1", 20_000, ref="trabajo:p1",
                 dueno="dep:a")
    m.comprar_capacidad(TS, "2026-W30", "trabajo:p1", "claude_max", 50,
                        ref="trabajo:p1", dueno="dep:a")  # 50 u a 100 = 5_000
    assert bus_mod.gastado(k.libro.asientos(), "p1") == 25_000


def test_muere_por_gasto_y_liquida_proporcional(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    _capital(k, 100_000, "dep:b")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000,
           {"gasto_max_mm": 25_000})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 60_000)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:b", 40_000)
    k.destruir(TS, "2026-W30", "trabajo:p1", 30_000, motivo="api",
               ref="trabajo:p1")  # 30k > 25k: muerto
    muertos = bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W30")
    assert muertos == ["p1"]
    assert b.estado("p1") == "liquidada"
    assert k.saldo("trabajo:p1") == 0
    # saldo 70k proporcional a aportes 60/40: a 42k, b 28k
    assert k.saldo("dep:a") == 100_000 - 60_000 + 42_000
    assert k.saldo("dep:b") == 100_000 - 40_000 + 28_000


def test_muere_por_semanas(entorno):
    k, m, b = entorno
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]:
        _semana_op(k, sem)
    _capital(k, 50_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 50_000, 100_000,
           {"semanas_max": 2})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 30_000)
    assert bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W32") == []
    assert bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W33") == ["p1"]
    assert k.saldo("dep:a") == 50_000  # todo devuelto: no gasto nada


def test_vivo_no_se_liquida(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 50_000, 100_000,
           {"gasto_max_mm": 25_000})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 30_000)
    k.destruir(TS, "2026-W30", "trabajo:p1", 10_000, motivo="api",
               ref="trabajo:p1")
    assert bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W30") == []
    assert b.estado("p1") == "financiada"
