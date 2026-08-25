# test_economia_simulacion.py
"""Simulacion de ciclo completo (spec 13): la economia entera, sin manos.

Cuatro semanas operativas con dos departamentos que compiten, una
propuesta financiada que gasta y muere, compuertas servidas por el reloj,
una venta real confirmada que mueve el tipo de cambio, una quiebra con
intento de rescate colusivo (debe fallar) y rescate firmado (debe pasar),
y el cierre de ciclo con renovacion — verificando al final las
invariantes globales del libro.
"""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import cola as cola_mod
from calipso.economia import cuenta_pedro as cp
from calipso.economia import departamentos as deps
from calipso.economia import mercado as mkt
from calipso.economia import operacion as op
from calipso.economia import pt
from calipso.economia import reloj as reloj_mod
from calipso.economia import tipos as t
from calipso.economia.balances import saldos
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"
SUS = {"claude_max": cap.Suscripcion("claude_max", 100_000, 1_000, 200, 500)}


def test_simulacion_ciclo_completo(tmp_path):
    k = Kernel(Libro(tmp_path / "libro.jsonl"))
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("mercado", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=50_000,
                             techo_api_ciclo_mm=100_000))
    r.alta(deps.Departamento("curiosos", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=20_000,
                             techo_api_ciclo_mm=50_000))
    m = mkt.Mercado(k, r, SUS)
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    cola = cola_mod.Cola(tmp_path / "cola.jsonl")
    reloj = reloj_mod.Reloj(tmp_path / "reloj.jsonl")

    # --- arranque: la pista del spec 4.4
    k.acunar(TS, "2026-W30", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})

    # --- W30: abrir, presupuestos, propuesta financiada, compuerta servida
    op.abrir_semana(k, TS, "2026-W30", 4_000, 500)
    op.cerrar_semana_operativa(m, b, cola, TS, "2026-W30")
    assert k.saldo("dep:mercado") == 50_000
    assert k.saldo("dep:curiosos") == 20_000

    op.abrir_semana(k, TS, "2026-W31", 4_000, 500)
    b.alta(TS, "2026-W31", "radar", "dep:mercado", "radar vertical",
           60_000, 200_000, {"gasto_max_mm": 20_000})
    bus_mod.financiar(m, b, TS, "2026-W31", "radar", "dep:mercado", 30_000)
    m.gastar_api(TS, "2026-W31", "trabajo:radar", 10_000, dueno="dep:mercado")
    cola.encolar(k, TS, "2026-W31", "entrega", "dep:mercado",
                 "entregar radar al cliente", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=150_000)
    reloj.clock_in("2026-08-26T10:00:00", "2026-W31", "fabrica",
                   ref="entrega", cola=cola)
    reloj.clock_out(m, cola, "2026-08-26T10:25:00", "2026-W31")
    assert cola.estado("entrega") == "servida"
    assert k.saldo(t.CUENTA_PEDRO) == 2_500  # 25 min -> 500 mpt a 5000
    op.cerrar_semana_operativa(m, b, cola, TS, "2026-W31")

    # --- W32: la venta real, atribuida al trabajo; el colusivo debe fallar
    op.abrir_semana(k, TS, "2026-W32", 4_000, 500)
    k.acunar(TS, "2026-W32", "dep:mercado", 150_000,
             t.SubtipoAcunacion.VENTA, {"tipo": "firma_pedro"},
             detalle_extra={"trabajo": "radar"})
    # curiosos quema todo su presupuesto en API y quiebra al cierre
    m.gastar_api(TS, "2026-W32", "dep:curiosos", 40_000)
    res32 = op.cerrar_semana_operativa(m, b, cola, TS, "2026-W32")
    assert "dep:curiosos" in res32["cierre"].quiebras
    # rescate colusivo: transferencia interna normal a un congelado -> falla
    with pytest.raises(mkt.ErrorMercado):
        m.vender_servicio(TS, "2026-W32", "dep:mercado", "dep:curiosos", 1_000)
    # rescate firmado desde la cuenta de Pedro -> pasa y descongela
    cp.rescatar(k, TS, "2026-W32", "dep:curiosos", 2_000,
                firma={"tipo": "firma_pedro"})
    assert not deps.es_congelado(k.libro.asientos(), "dep:curiosos")

    # --- W33: cierra el ciclo; el trabajo radar muere por gasto en el cierre
    op.abrir_semana(k, TS, "2026-W33", 4_000, 500)
    m.gastar_api(TS, "2026-W33", "trabajo:radar", 15_000, dueno="dep:mercado")
    saldo_mercado_antes = k.saldo("dep:mercado")
    res33 = op.cerrar_semana_operativa(m, b, cola, TS, "2026-W33")
    assert "radar" in res33["cierre"].trabajos_muertos
    assert b.estado("radar") == "liquidada"
    # el remanente del trabajo (30k - 10k - 15k = 5k) volvio al financiador
    assert k.saldo("trabajo:radar") == 0
    assert k.saldo("dep:mercado") == saldo_mercado_antes + 5_000 + 50_000
    assert len(res33["informes_ciclo"]) == 1  # el ciclo 0 cerro

    # --- el tipo de cambio sigue en el arranque: la regla de bootstrap rige
    # hasta 4 semanas con consumo (spec 3.2d); la venta ya esta en el lapso
    # y empujara el tipo cuando el bootstrap termine
    tipo_final = pt.tipo_de_cambio(k.libro.asientos(), "2026-W33")
    assert tipo_final == 5_000

    # --- invariantes globales del libro (spec 13)
    asientos = k.libro.asientos()
    acunado = sum(a.monto for a in asientos
                  if a.tipo is t.TipoAsiento.ACUNACION)
    destruido = sum(a.monto for a in asientos
                    if a.tipo is t.TipoAsiento.DESTRUCCION)
    total = sum(v for (cta, div), v in saldos(asientos).items()
                if div is t.Divisa.MONEDA)
    assert total == acunado - destruido  # ni una milimoneda inventada
    # reproducibilidad: reconstruir desde disco da lo mismo
    k2 = Kernel(Libro(tmp_path / "libro.jsonl"))
    assert saldos(k2.libro.asientos()) == saldos(asientos)
