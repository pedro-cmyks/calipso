"""Tests de suscripciones como capacidad: prorrateo, ciclo, precio por escasez."""
import pytest

from calipso.economia import capacidad as cap
from calipso.economia import tipos as t
from calipso.economia import pt
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"

SUS = cap.Suscripcion(nombre="claude_max", costo_mensual_mm=100_000,
                      capacidad_ciclo=1_000, reserva_personal=200,
                      costo_api_mm_por_unidad=500)


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


def _emitir(k, semanas):
    for s in semanas:
        pt.emitir_semana(k, TS, s, 4_000, 0)
        pt.expirar_pools(k, TS, s)


def test_prorrateo_y_precios_derivados():
    assert SUS.capacidad_fabrica == 800
    assert SUS.costo_fabrica_mm == 80_000   # 100k * 800/1000
    assert SUS.precio_base_mm == 100        # 80k / 800
    assert SUS.tope_mm == 450               # 500 * 0.9


def test_configuracion_invalida_se_rechaza():
    with pytest.raises(cap.ErrorCapacidad):
        cap.Suscripcion("x", 1_000, 0, 0, 500)          # capacidad 0
    with pytest.raises(cap.ErrorCapacidad):
        cap.Suscripcion("x", 1_000, 100, 100, 500)      # reserva == capacidad
    with pytest.raises(cap.ErrorCapacidad):
        cap.Suscripcion("x", 1_000, 100, 10, 0)         # api equiv 0


def test_posicion_y_semanas_de_ciclo(k):
    semanas = [f"2026-W{n}" for n in range(30, 36)]     # 6 semanas operativas
    _emitir(k, semanas)
    ops = cap.semanas_operativas(k.libro.asientos())
    assert ops == semanas
    assert cap.posicion_ciclo("2026-W30", ops) == (0, 25)
    assert cap.posicion_ciclo("2026-W33", ops) == (0, 100)
    assert cap.posicion_ciclo("2026-W34", ops) == (1, 25)
    assert cap.semanas_del_ciclo(0, ops) == semanas[:4]
    assert cap.semanas_del_ciclo(1, ops) == semanas[4:]
    with pytest.raises(cap.ErrorCapacidad):
        cap.posicion_ciclo("2026-W99", ops)


def test_precio_por_escasez_y_tope():
    # a ritmo (25% de ciclo, 25% de cuota consumida = 200): factor 100
    assert cap.precio_unidad_mm(SUS, 200, 25) == 100
    # sobre-ritmo: 50% consumido en 25% de ciclo -> factor 200
    assert cap.precio_unidad_mm(SUS, 400, 25) == 200
    # tope duro: 100% consumido en 25% de ciclo -> factor 400 -> 400 < 450
    assert cap.precio_unidad_mm(SUS, 800, 25) == 400
    # mas alla del tope: factor 500 -> clavado en 450
    assert cap.precio_unidad_mm(SUS, 1_000, 25) == 450
    # sub-ritmo nunca abarata bajo el precio base
    assert cap.precio_unidad_mm(SUS, 0, 100) == 100


def test_consumo_y_recaudacion_se_derivan_del_libro(k):
    _emitir(k, ["2026-W30", "2026-W31"])
    k.acunar(TS, "2026-W30", "dep:a", 50_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    k.transferir(TS, "2026-W30", "dep:a", t.DIRECCION, 1_000,
                 motivo="capacidad",
                 detalle_extra={"suscripcion": "claude_max", "unidades": 10})
    k.transferir(TS, "2026-W31", "dep:a", t.DIRECCION, 2_400,
                 motivo="capacidad",
                 detalle_extra={"suscripcion": "claude_max", "unidades": 12})
    k.transferir(TS, "2026-W31", "dep:a", t.DIRECCION, 500,
                 motivo="capacidad",
                 detalle_extra={"suscripcion": "otra", "unidades": 99})
    asientos = k.libro.asientos()
    assert cap.consumo_fabrica(asientos, "claude_max",
                               ["2026-W30", "2026-W31"]) == 22
    assert cap.consumo_fabrica(asientos, "claude_max", ["2026-W31"]) == 12
    assert cap.recaudacion(asientos, "claude_max",
                           ["2026-W30", "2026-W31"]) == 3_400


def test_el_ciclo_de_hoy_no_espera_al_boton_de_abrir_la_semana():
    """`posicion_ciclo` solo sabe de semanas ya emitidas, y una semana se
    vuelve operativa recien cuando alguien aprieta el boton de abrir: toda
    semana empieza afuera. Preguntando con `if semana in ops`, el ciclo da
    vacio esa ventana entera -- y un techo acumulado por ciclo que se
    resetea solo porque Pedro tardo en abrir el lunes no es un techo."""
    ops = ["2026-W31", "2026-W32", "2026-W33"]
    # la semana de hoy todavia no emitio su PT: igual cae en el ciclo 0
    assert cap.semanas_del_ciclo_de_hoy(ops, "2026-W34") == ops
    # y ya emitida, la misma respuesta
    assert cap.semanas_del_ciclo_de_hoy(ops + ["2026-W34"],
                                        "2026-W34") == ops + ["2026-W34"]


def test_el_ciclo_de_hoy_solo_devuelve_semanas_que_existen():
    """La semana de hoy se inserta para hacer la cuenta, no para volver: si
    saliera en la lista, cualquier pliegue por semana la miraria y contaria
    asientos de una semana que todavia no emitio nada."""
    ops = ["2026-W31", "2026-W32", "2026-W33", "2026-W34"]
    # W35 abre el ciclo 1, que todavia no tiene ninguna semana real
    assert cap.semanas_del_ciclo_de_hoy(ops, "2026-W35") == []
    # y sin ninguna semana operativa, tampoco revienta
    assert cap.semanas_del_ciclo_de_hoy([], "2026-W31") == []
