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
