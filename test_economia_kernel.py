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
