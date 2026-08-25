"""Tests de departamentos, mercado y direccion: la capa de juego economico."""
import pytest

from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import cuenta_pedro as cp
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"
W = "2026-W35"


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


@pytest.fixture
def registro(tmp_path):
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("mercadeo", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=20_000,
                             techo_api_ciclo_mm=10_000))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    return r


def _capital(k, monto, destino=t.TESORO):
    return k.acunar(TS, W, destino, monto, t.SubtipoAcunacion.CAPITAL,
                    {"tipo": "firma_pedro"})


def test_cuentas_por_zona(registro):
    assert registro.obtener("mercadeo").cuenta == "dep:mercadeo"
    assert registro.obtener("finanzas").cuenta == "personal:finanzas"


def test_registro_persiste_y_ajusta(tmp_path, registro):
    registro.ajustar("mercadeo", presupuesto_semanal_mm=30_000)
    r2 = deps.Registro(tmp_path / "departamentos.json")
    assert r2.obtener("mercadeo").presupuesto_semanal_mm == 30_000
    assert len(r2.todos()) == 2
    with pytest.raises(deps.ErrorDepartamento):
        r2.alta(deps.Departamento("mercadeo", deps.ZONA_FABRICA))  # repetido
    with pytest.raises(deps.ErrorDepartamento):
        r2.obtener("fantasma")


def test_quiebra_congela_y_rescate_descongela(k):
    _capital(k, 10_000, destino="dep:a")
    assert not deps.es_congelado(k.libro.asientos(), "dep:a")
    deps.declarar_quiebra(k, TS, W, "dep:a")
    assert deps.es_congelado(k.libro.asientos(), "dep:a")
    _capital(k, 5_000, destino=t.CUENTA_PEDRO)
    cp.rescatar(k, TS, W, "dep:a", 5_000, firma={"tipo": "firma_pedro"})
    assert not deps.es_congelado(k.libro.asientos(), "dep:a")


def test_venta_propia_tambien_descongela(k):
    deps.declarar_quiebra(k, TS, W, "dep:a")
    k.acunar(TS, W, "dep:a", 1_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"})
    assert not deps.es_congelado(k.libro.asientos(), "dep:a")


def test_capital_no_descongela(k):
    """Solo rescate firmado o venta propia sacan del congelamiento (spec 5)."""
    deps.declarar_quiebra(k, TS, W, "dep:a")
    _capital(k, 1_000, destino="dep:a")  # capital directo, sin marca de rescate
    assert deps.es_congelado(k.libro.asientos(), "dep:a")
