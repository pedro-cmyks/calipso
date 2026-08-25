"""Tests de eficiencia: atribucion prorrateada por costo API equivalente."""
import pytest

from calipso.economia import capacidad as cap
from calipso.economia import eficiencia as ef
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"
W = "2026-W35"
SEMANAS = [W]

SUS = {"claude_max": cap.Suscripcion("claude_max", 100_000, 1_000, 200, 500)}


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


def _montar_trabajo(k, id, api_mm, unidades):
    """Trabajo con gasto de API y de capacidad, etiquetado por ref."""
    ref = f"trabajo:{id}"
    k.acunar(TS, W, f"trabajo:{id}", api_mm + 100_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    k.destruir(TS, W, f"trabajo:{id}", api_mm, motivo="api", ref=ref)
    k.transferir(TS, W, f"trabajo:{id}", t.DIRECCION, unidades * 100,
                 motivo="capacidad", ref=ref,
                 detalle_extra={"suscripcion": "claude_max",
                                "unidades": unidades})


def test_costos_de_trabajo_en_api_equivalente(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    costos = ef.costos_de_trabajo(k.libro.asientos(), "p1", SUS)
    # capacidad: 100 unidades * 500 mm api-equiv = 50_000
    assert costos == {"api": 50_000, "sus:claude_max": 50_000}


def test_atribucion_prorratea_por_costo(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"}, detalle_extra={"trabajo": "p1"})
    atribuida = ef.atribucion_por_suscripcion(k.libro.asientos(), SEMANAS, SUS)
    assert atribuida == {"claude_max": 15_000}  # 30k * 50k/100k


def test_eficiencia_por_suscripcion(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"}, detalle_extra={"trabajo": "p1"})
    got = ef.eficiencia_suscripcion(k.libro.asientos(), SUS["claude_max"],
                                    SEMANAS, SUS)
    assert got == 300  # 15_000 * 1000 // 50_000


def test_eficiencia_departamento(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"}, detalle_extra={"trabajo": "p1"})
    got = ef.eficiencia_departamento(k.libro.asientos(), "dep:a", SEMANAS,
                                     SUS, duenos={"p1": "dep:a"})
    assert got == 300  # 30_000 * 1000 // 100_000


def test_eficiencia_departamento_ventana_y_gasto_directo(k):
    """El denominador respeta la ventana y suma el gasto directo del dep."""
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)  # 100k equiv en W35
    # gasto del trabajo FUERA de la ventana: excluido
    k.destruir(TS, "2026-W34", "trabajo:p1", 10_000, motivo="api",
               ref="trabajo:p1")
    # gasto directo del departamento EN la ventana: 20k
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    k.destruir(TS, W, "dep:a", 20_000, motivo="api")
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"}, detalle_extra={"trabajo": "p1"})
    got = ef.eficiencia_departamento(k.libro.asientos(), "dep:a", SEMANAS,
                                     SUS, duenos={"p1": "dep:a"})
    assert got == 250  # 30_000 * 1000 // (100_000 + 20_000)


def test_capital_y_ventas_sin_trabajo_no_atribuyen(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    k.acunar(TS, W, t.TESORO, 1_000_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    k.acunar(TS, W, "dep:a", 99_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"})  # venta sin trabajo: no atribuible
    atribuida = ef.atribucion_por_suscripcion(k.libro.asientos(), SEMANAS, SUS)
    assert atribuida == {}


def test_eficiencia_sin_consumo_es_cero():
    assert ef.eficiencia_pormil(0, 0) == 0
    assert ef.eficiencia_pormil(5_000, 0) == 0
