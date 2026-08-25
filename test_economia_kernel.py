"""Tests del Kernel: operaciones validadas sobre el libro."""
import pytest

from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel, SinSaldo, OperacionInvalida

TS = "2026-08-24T10:00:00"
W = "2026-W35"


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


def _capital(k, monto=1_000_000, destino=t.TESORO):
    return k.acunar(TS, W, destino, monto, t.SubtipoAcunacion.CAPITAL,
                    {"tipo": "firma_pedro"})


def test_acunar_registra_subtipo_y_evidencia(k):
    a = _capital(k)
    assert a.subtipo == "capital"
    assert a.detalle["evidencia"] == {"tipo": "firma_pedro"}
    assert k.saldo(t.TESORO) == 1_000_000


def test_acunar_sin_evidencia_es_invalido(k):
    with pytest.raises(OperacionInvalida):
        k.acunar(TS, W, t.TESORO, 1_000, t.SubtipoAcunacion.VENTA, {})


def test_destruir_valida_disponible(k):
    _capital(k, 10_000)
    k.destruir(TS, W, t.TESORO, 4_000, motivo="renovacion")
    assert k.saldo(t.TESORO) == 6_000
    with pytest.raises(SinSaldo):
        k.destruir(TS, W, t.TESORO, 6_001, motivo="renovacion")


def test_destruir_de_cuenta_vacia_falla(k):
    with pytest.raises(SinSaldo):
        k.destruir(TS, W, "dep:fantasma", 1, motivo="api")


def test_transferir_mueve_y_valida_disponible(k):
    _capital(k, 100_000)
    k.transferir(TS, W, t.TESORO, "dep:mercado", 40_000, motivo="presupuesto")
    assert k.saldo(t.TESORO) == 60_000
    assert k.saldo("dep:mercado") == 40_000
    with pytest.raises(SinSaldo):
        k.transferir(TS, W, t.TESORO, "dep:mercado", 60_001, motivo="presupuesto")


@pytest.mark.skip(reason="reservar llega en task 6")
def test_transferir_respeta_reservas(k):
    """Sin sobregiro es contra DISPONIBLE, no contra saldo (invariante 7)."""
    _capital(k, 100_000, destino="dep:a")
    k.reservar(TS, W, "dep:a", 70_000, ref="res-1")
    with pytest.raises(SinSaldo):
        k.transferir(TS, W, "dep:a", "dep:b", 40_000, motivo="servicio")
    k.transferir(TS, W, "dep:a", "dep:b", 30_000, motivo="servicio")
    assert k.saldo("dep:b") == 30_000
