"""Tests de la divisa PT: emision, consumo, expiracion y tipo de cambio."""
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


def test_consumir_monto_no_positivo_es_error_pt(k):
    pt.emitir_semana(k, TS, "2026-W35", 4_000, 0)
    with pytest.raises(pt.ErrorPT):
        pt.consumir_fabrica(k, TS, "2026-W35", 0, ref="f-1", pagador="dep:a")
    with pytest.raises(pt.ErrorPT):
        pt.consumir_fabrica(k, TS, "2026-W35", -5, ref="f-1", pagador="dep:a")


def test_emitir_cuota_cero_es_error_pt(k):
    with pytest.raises(pt.ErrorPT):
        pt.emitir_semana(k, TS, "2026-W35", 0, 0)


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


def test_venta_en_semana_no_operativa_cuenta_en_el_lapso(k):
    """Enmienda (a): una venta nunca desaparece del indice — cuenta en el
    numerador aunque su semana no tenga emision de PT."""
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"]:
        _semana_operativa(k, sem, 2_000)
    got_w34 = pt.tipo_de_cambio(k.libro.asientos(), "2026-W34")
    assert got_w34 == 2_812

    # W35 NO se emite (semana no operativa), pero si se acuna una venta
    _venta(k, 100_000, "2026-W35")
    _semana_operativa(k, "2026-W36", 2_000)
    got_w36 = pt.tipo_de_cambio(k.libro.asientos(), "2026-W36")
    assert got_w36 == 3_515


def test_arranque_es_solo_bootstrap_sin_salto(k):
    """Enmienda (d): superado el bootstrap (4 semanas con consumo en
    alguna ventana), el cociente con banda gobierna siempre; no hay
    salto de vuelta al valor de arranque aunque la ventana vuelva a
    tener pocas semanas con consumo."""
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"]:
        _semana_operativa(k, sem, 2_000)
    assert pt.tipo_de_cambio(k.libro.asientos(), "2026-W34") == 2_812

    for sem in ["2026-W35", "2026-W36", "2026-W37", "2026-W38", "2026-W39",
                "2026-W40", "2026-W41", "2026-W42"]:
        _semana_operativa(k, sem, 0)  # decae, luego se mantiene en el piso

    _semana_operativa(k, "2026-W43", 2_000)  # la ventana ya solo tiene 1
    got = pt.tipo_de_cambio(k.libro.asientos(), "2026-W43")
    assert got == 1_000  # cociente 0 clamped al piso, NO 5_000


def test_expirados_no_cuentan_como_consumidos(k):
    """Spec 3.2(b): los PT expirados no cuentan como consumidos — el
    denominador solo suma CONSUMO_PT de la fabrica."""
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]:
        _semana_operativa(k, sem, 2_000)  # cada semana expira 2_000 tambien
    _venta(k, 30_000, "2026-W34")
    _semana_operativa(k, "2026-W34", 2_000)
    got = pt.tipo_de_cambio(k.libro.asientos(), "2026-W34")
    assert got == 3_000  # objetivo = 30_000*1000//10_000, dentro de banda


def test_consumo_personal_no_mueve_el_tipo(k):
    """Spec 3.2(b): el consumo personal de PT queda fuera de numerador y
    denominador del tipo de cambio."""
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"]:
        pt.emitir_semana(k, TS, sem, 5_000, 1_000)
        if sem == "2026-W34":
            _venta(k, 30_000, sem)
        pt.consumir_fabrica(k, TS, sem, 2_000, ref=f"f-{sem}", pagador="dep:a")
        pt.consumir_personal(k, TS, sem, 1_000, departamento="personal:atlas",
                             tipo_vigente_mm=5_000)
        pt.expirar_pools(k, TS, sem)
    got = pt.tipo_de_cambio(k.libro.asientos(), "2026-W34")
    assert got == 3_000  # si el consumo personal contara, denominador 15_000


def test_cierre_semanal_libera_expira_y_recalcula(k):
    k.acunar(TS, "2026-W35", "dep:a", 100_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    pt.emitir_semana(k, TS, "2026-W35", 4_000, 1_000)
    k.reservar(TS, "2026-W35", "dep:a", 10_000, ref="firma-99")  # encolada, no servida
    pt.consumir_fabrica(k, TS, "2026-W35", 500, ref="firma-1", pagador="dep:a")
    cierre = pt.cerrar_semana(k, TS, "2026-W35",
                              refs_reservas_no_servidas=["firma-99"])
    assert cierre.semana == "2026-W35"
    assert cierre.expirado_fabrica_mpt == 2_500
    assert cierre.expirado_personal_mpt == 1_000
    assert cierre.reservas_liberadas == 1
    assert cierre.tipo_mm == 5_000  # sin historia suficiente: arranque
    assert k.disponible("dep:a") == 100_000  # la reserva no servida volvio
    # y la semana siguiente ya puede emitir
    pt.emitir_semana(k, TS, "2026-W36", 4_000, 0)


def test_api_publica_del_paquete():
    import calipso.economia as eco
    assert eco.Kernel and eco.Libro and eco.pt and eco.cuenta_pedro
    assert eco.RUTA_LIBRO_DEFECTO.name == "libro.jsonl"
