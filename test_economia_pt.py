# test_economia_pt.py
"""Tests de la divisa PT: emision, consumo y expiracion."""
import pytest

from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-24T10:00:00"


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


def test_emitir_semana_parte_fabrica_y_personal(k):
    pt.emitir_semana(k, TS, "2026-W35", cuota_firmable_mpt=5_000,
                     reserva_personal_mpt=2_000)
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 3_000
    assert k.saldo(t.POOL_PT_PERSONAL, t.Divisa.PT) == 2_000


def test_no_se_emite_dos_veces_la_misma_semana(k):
    pt.emitir_semana(k, TS, "2026-W35", 5_000, 0)
    with pytest.raises(pt.ErrorPT):
        pt.emitir_semana(k, TS, "2026-W35", 5_000, 0)


def test_no_se_emite_sobre_pools_sin_cerrar(k):
    """Cierre previo obligatorio: los pools deben estar en cero (spec 3.2)."""
    pt.emitir_semana(k, TS, "2026-W35", 5_000, 0)
    with pytest.raises(pt.ErrorPT):
        pt.emitir_semana(k, TS, "2026-W36", 5_000, 0)


def test_reserva_personal_no_puede_exceder_cuota(k):
    with pytest.raises(pt.ErrorPT):
        pt.emitir_semana(k, TS, "2026-W35", 4_000, 4_001)


def test_consumir_fabrica_valida_pool(k):
    pt.emitir_semana(k, TS, "2026-W35", 4_000, 1_000)
    pt.consumir_fabrica(k, TS, "2026-W35", 500, ref="firma-1", pagador="dep:a")
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 2_500
    with pytest.raises(pt.ErrorPT):
        pt.consumir_fabrica(k, TS, "2026-W35", 2_501, ref="firma-2",
                            pagador="dep:a")


def test_consumir_personal_genera_apunte_de_oportunidad(k):
    pt.emitir_semana(k, TS, "2026-W35", 4_000, 2_000)
    asientos = pt.consumir_personal(k, TS, "2026-W35", 1_500,
                                    departamento="personal:atlas",
                                    tipo_vigente_mm=5_000)
    assert k.saldo(t.POOL_PT_PERSONAL, t.Divisa.PT) == 500
    apunte = asientos[-1]
    assert apunte.tipo is t.TipoAsiento.APUNTE
    assert apunte.monto == 7_500  # 1.5 PT a 5 monedas/PT
    assert apunte.detalle["departamento"] == "personal:atlas"


def test_expirar_deja_pools_en_cero_y_registra(k):
    pt.emitir_semana(k, TS, "2026-W35", 4_000, 1_000)
    pt.consumir_fabrica(k, TS, "2026-W35", 1_000, ref="f-1", pagador="dep:a")
    expirados = pt.expirar_pools(k, TS, "2026-W35")
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 0
    assert k.saldo(t.POOL_PT_PERSONAL, t.Divisa.PT) == 0
    montos = {a.origen: a.monto for a in expirados}
    assert montos == {t.POOL_PT_FABRICA: 2_000, t.POOL_PT_PERSONAL: 1_000}


def _venta(k, monto_mm, semana):
    k.acunar(TS, semana, "dep:a", monto_mm, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"})


def _semana_operativa(k, semana, consumo_mpt):
    """Emision estandar de 4 PT fabrica y consumo dado, con cierre."""
    pt.emitir_semana(k, TS, semana, cuota_firmable_mpt=4_000,
                     reserva_personal_mpt=0)
    if consumo_mpt:
        pt.consumir_fabrica(k, TS, semana, consumo_mpt, ref=f"f-{semana}",
                            pagador="dep:a")
    pt.expirar_pools(k, TS, semana)


def test_arranque_rige_hasta_cuatro_semanas_con_consumo(k):
    k.acunar(TS, "2026-W30", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    for i, sem in enumerate(["2026-W30", "2026-W31", "2026-W32"]):
        _semana_operativa(k, sem, 2_000)
    got = pt.tipo_de_cambio(k.libro.asientos(), "2026-W32")
    assert got == 5_000  # solo 3 semanas con consumo: sigue el arranque


def test_capital_no_mueve_el_tipo_de_cambio(k):
    """Spec 3.2 regla (a): inyectar pista no sube el sueldo de Pedro."""
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"]:
        _semana_operativa(k, sem, 2_000)
    k.acunar(TS, "2026-W34", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    got = pt.tipo_de_cambio(k.libro.asientos(), "2026-W34")
    # 5 semanas con consumo y CERO ventas: cociente 0 -> banda y piso mandan
    assert got < 5_000  # bajo desde el arranque, no subio por el capital
    assert got >= 1_000


def test_ventas_suben_el_tipo_dentro_de_la_banda(k):
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]:
        _semana_operativa(k, sem, 2_000)
    _venta(k, 100_000, "2026-W34")  # 100 monedas de venta real
    _semana_operativa(k, "2026-W34", 2_000)
    antes = pt.tipo_de_cambio(k.libro.asientos(), "2026-W33")
    despues = pt.tipo_de_cambio(k.libro.asientos(), "2026-W34")
    assert despues > antes
    assert despues <= antes * 125 // 100  # banda de +25% por cierre


def test_ventana_sin_consumo_mantiene_el_tipo(k):
    """Spec 3.2 regla (c): con la ventana entera sin consumo, el tipo no
    se mueve. (Mientras la ventana todavia contiene semanas con consumo y
    cero ventas, bajar es legitimo: eso no es esta regla.)"""
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"]:
        _semana_operativa(k, sem, 2_000)
    for sem in ["2026-W35", "2026-W36", "2026-W37", "2026-W38", "2026-W39",
                "2026-W40", "2026-W41", "2026-W42", "2026-W43"]:
        _semana_operativa(k, sem, 0)  # nueve semanas sin consumo
    # en W42 y W43 la ventana de 8 ya es toda sin consumo: se mantiene
    a = pt.tipo_de_cambio(k.libro.asientos(), "2026-W42")
    b = pt.tipo_de_cambio(k.libro.asientos(), "2026-W43")
    assert a == b
    assert a >= 1_000  # y nunca por debajo del piso


def test_reproducible_misma_historia_mismo_numero(k):
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"]:
        _venta(k, 20_000, sem)
        _semana_operativa(k, sem, 2_000)
    a = pt.tipo_de_cambio(k.libro.asientos(), "2026-W34")
    b = pt.tipo_de_cambio(list(k.libro.asientos()), "2026-W34")
    assert a == b
    # y reconstruyendo el libro desde disco
    from calipso.economia.libro import Libro
    k2 = Kernel(Libro(k.libro.ruta))
    assert pt.tipo_de_cambio(k2.libro.asientos(), "2026-W34") == a
