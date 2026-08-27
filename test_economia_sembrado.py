"""Tests HTTP del sembrado de la economia, el banco de Pedro y la frontera
de acunacion (specs 8.4 y 8.5, y el sembrado que el plan maestro llama
Etapa 2 y que ningun spec escribio)."""
import json

import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso.economia import tipos as t
from calipso.economia.bus import Bus
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro

TS = "2026-08-27T09:00:00"
W = "2026-W35"

DEPARTAMENTOS = [
    {"nombre": "market_research", "zona": "fabrica",
     "presupuesto_semanal_mm": 25_000},
    {"nombre": "legal", "zona": "fabrica", "presupuesto_semanal_mm": 15_000},
]
# 1 moneda = 1000 mm = 1 USD: 200 USD y 20 USD, las dos suscripciones reales
# que Pedro ya paga.
SUSCRIPCIONES = {
    "claude_max": {"costo_mensual_mm": 200_000},
    "chatgpt_plus": {"costo_mensual_mm": 20_000},
}


@pytest.fixture
def crudo(tmp_path, monkeypatch):
    """HOME temporal SIN economia: el caso que sembrar tiene que manejar."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN}), tmp_path


@pytest.fixture
def cliente(crudo):
    """El mismo HOME, ya sembrado por la propia API (flujo real de Pedro)."""
    c, base = crudo
    r = c.post("/api/economia/sembrar",
              json={"departamentos": DEPARTAMENTOS,
                    "suscripciones": SUSCRIPCIONES})
    assert r.status_code == 200
    return c, base


# -- sembrar ---------------------------------------------------------------

def test_sembrar_crea_los_tres_archivos(crudo):
    c, base = crudo
    r = c.post("/api/economia/sembrar",
              json={"departamentos": DEPARTAMENTOS,
                    "suscripciones": SUSCRIPCIONES})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert set(body["departamentos"]) == {"market_research", "legal"}
    assert set(body["suscripciones"]) == {"claude_max", "chatgpt_plus"}
    eco = base / "economia"
    assert (eco / "libro.jsonl").exists()
    assert (eco / "libro.jsonl").read_text() == ""
    assert (eco / "departamentos.json").exists()
    assert (eco / "suscripciones.json").exists()
    # la economia activa: desde_entorno ya la encuentra
    assert c.get("/api/economia/tablero").json()["activa"] is True


def test_sembrar_de_nuevo_sobre_una_economia_existente_falla(cliente):
    c, base = cliente
    antes = (base / "economia" / "departamentos.json").read_text()
    r = c.post("/api/economia/sembrar",
              json={"departamentos": DEPARTAMENTOS,
                    "suscripciones": SUSCRIPCIONES})
    assert r.status_code == 400
    assert "ya esta sembrada" in r.json()["detail"]
    # append-only: sembrar de nuevo no toco nada de lo que ya habia
    assert (base / "economia" / "departamentos.json").read_text() == antes


def test_sembrar_exige_al_menos_un_departamento(crudo):
    c, base = crudo
    r = c.post("/api/economia/sembrar",
              json={"departamentos": [], "suscripciones": {}})
    assert r.status_code == 400
    assert "al menos un departamento" in r.json()["detail"]
    assert not (base / "economia").exists()


def test_sembrar_departamento_invalido_no_deja_archivos_parciales(crudo):
    c, base = crudo
    r = c.post("/api/economia/sembrar", json={
        "departamentos": [{"nombre": "ok", "zona": "fabrica"},
                          {"nombre": "malo", "zona": "invertida"}],
        "suscripciones": {}})
    assert r.status_code == 400
    eco = base / "economia"
    assert not (eco / "libro.jsonl").exists()
    assert not (eco / "departamentos.json").exists()
    assert not (eco / "suscripciones.json").exists()


def test_sembrar_departamentos_repetidos_falla(crudo):
    c, base = crudo
    r = c.post("/api/economia/sembrar", json={
        "departamentos": [{"nombre": "legal", "zona": "fabrica"},
                          {"nombre": "legal", "zona": "fabrica"}],
        "suscripciones": {}})
    assert r.status_code == 400
    assert "repetidos" in r.json()["detail"]


def test_sembrar_suscripcion_invalida(crudo):
    c, base = crudo
    r = c.post("/api/economia/sembrar", json={
        "departamentos": DEPARTAMENTOS,
        "suscripciones": {"claude_max": {"costo_mensual_mm": 0}}})
    assert r.status_code == 400


def test_sembrar_usa_los_defaults_comentados_si_no_vienen(crudo):
    c, base = crudo
    r = c.post("/api/economia/sembrar", json={
        "departamentos": DEPARTAMENTOS,
        "suscripciones": {"claude_max": {"costo_mensual_mm": 200_000}}})
    assert r.status_code == 200
    datos = json.loads((base / "economia" / "suscripciones.json").read_text())
    assert datos["claude_max"]["capacidad_ciclo"] == 1_000
    assert datos["claude_max"]["reserva_personal"] == 200
    assert datos["claude_max"]["costo_api_mm_por_unidad"] == 3_000


# -- el banco de Pedro (8.4) ------------------------------------------------

def test_personal_movimiento_ingreso_y_gasto(cliente):
    c, base = cliente
    r = c.post("/api/economia/personal/movimiento",
              json={"tipo": "ingreso", "monto_mm": 2_500_000,
                    "categoria": "sueldo"})
    assert r.status_code == 200 and r.json()["ok"] is True
    r = c.post("/api/economia/personal/movimiento",
              json={"tipo": "gasto", "monto_mm": 220_000,
                    "categoria": "suscripciones",
                    "nota": "claude max + chatgpt plus"})
    assert r.status_code == 200

    tab = c.get("/api/economia/tablero").json()["tablero"]
    assert tab["personal"] == {"ingresos_mm": 2_500_000,
                               "gastos_mm": 220_000,
                               "neto_mm": 2_280_000}
    # nunca toco el libro de la fabrica (invariante 11)
    k = Kernel(Libro(base / "economia" / "libro.jsonl"))
    assert k.libro.asientos() == []
    assert k.saldo(t.CUENTA_PEDRO) == 0
    assert k.saldo(t.TESORO) == 0


def test_personal_movimiento_acepta_egreso_como_sinonimo_de_gasto(cliente):
    # Pedro pidio el banco con estas palabras, textual: "ingresos y
    # egresos" -- pero personal.py (preexistente, no tocado) solo conoce
    # "ingreso"/"gasto". La normalizacion vive en el endpoint.
    c, base = cliente
    r = c.post("/api/economia/personal/movimiento",
              json={"tipo": "egreso", "monto_mm": 50_000,
                    "categoria": "comida"})
    assert r.status_code == 200 and r.json()["ok"] is True
    linea = json.loads(
        (base / "economia" / "personal.jsonl").read_text().splitlines()[-1])
    assert linea["tipo"] == "gasto"  # normalizado antes de llegar a registrar
    tab = c.get("/api/economia/tablero").json()["tablero"]
    assert tab["personal"]["gastos_mm"] == 50_000


def test_personal_movimiento_gasto_sigue_funcionando(cliente):
    c, base = cliente
    r = c.post("/api/economia/personal/movimiento",
              json={"tipo": "gasto", "monto_mm": 30_000,
                    "categoria": "transporte"})
    assert r.status_code == 200 and r.json()["ok"] is True
    linea = json.loads(
        (base / "economia" / "personal.jsonl").read_text().splitlines()[-1])
    assert linea["tipo"] == "gasto"


def test_personal_movimiento_tipo_invalido_falla(cliente):
    c, base = cliente
    r = c.post("/api/economia/personal/movimiento",
              json={"tipo": "prestamo", "monto_mm": 1, "categoria": "x"})
    assert r.status_code == 400


def test_personal_movimiento_sin_economia_activa_falla(crudo):
    c, base = crudo  # sin sembrar
    r = c.post("/api/economia/personal/movimiento",
              json={"tipo": "ingreso", "monto_mm": 1, "categoria": "x"})
    assert r.status_code == 400


# -- la frontera de acunacion (8.5) -----------------------------------------

def test_acunar_capital_al_tesoro(cliente):
    c, base = cliente
    r = c.post("/api/economia/frontera/acunar",
              json={"subtipo": "capital", "destino": "tesoro",
                    "monto_mm": 1_200_000,
                    "evidencia": {"tipo": "firma_pedro"}})
    assert r.status_code == 200
    asiento = r.json()["asiento"]
    assert asiento["destino"] == "tesoro"
    assert asiento["monto"] == 1_200_000
    assert asiento["subtipo"] == "capital"
    k = Kernel(Libro(base / "economia" / "libro.jsonl"))
    assert k.saldo(t.TESORO) == 1_200_000


def test_acunar_capital_a_departamento_falla(cliente):
    c, base = cliente
    r = c.post("/api/economia/frontera/acunar",
              json={"subtipo": "capital", "destino": "dep:legal",
                    "monto_mm": 1_000, "evidencia": {"tipo": "firma_pedro"}})
    assert r.status_code == 400
    assert "tesoro" in r.json()["detail"]
    k = Kernel(Libro(base / "economia" / "libro.jsonl"))
    assert k.libro.asientos() == []


def test_acunar_venta_al_tesoro_falla(cliente):
    c, base = cliente
    r = c.post("/api/economia/frontera/acunar",
              json={"subtipo": "venta", "destino": "tesoro",
                    "monto_mm": 1_000, "evidencia": {"comprobante": "x"},
                    "proyecto": "atlas"})
    assert r.status_code == 400


def test_acunar_venta_a_departamento_falla(cliente):
    c, base = cliente
    r = c.post("/api/economia/frontera/acunar",
              json={"subtipo": "venta", "destino": "dep:legal",
                    "monto_mm": 1_000, "evidencia": {"comprobante": "x"},
                    "proyecto": "atlas"})
    assert r.status_code == 400


def test_acunar_venta_a_direccion_y_cuenta_pedro_falla(cliente):
    c, base = cliente
    for destino in ("direccion", "cuenta_pedro"):
        r = c.post("/api/economia/frontera/acunar",
                  json={"subtipo": "venta", "destino": destino,
                        "monto_mm": 1_000, "evidencia": {"comprobante": "x"},
                        "proyecto": "atlas"})
        assert r.status_code == 400, destino


def test_acunar_venta_sin_proyecto_falla(cliente):
    c, base = cliente
    r = c.post("/api/economia/frontera/acunar",
              json={"subtipo": "venta", "destino": "proyecto:atlas",
                    "monto_mm": 1_000, "evidencia": {"comprobante": "x"}})
    assert r.status_code == 400
    assert "proyecto" in r.json()["detail"]


def test_acunar_venta_proyecto_no_coincide_con_destino_falla(cliente):
    c, base = cliente
    r = c.post("/api/economia/frontera/acunar",
              json={"subtipo": "venta", "destino": "proyecto:atlas",
                    "monto_mm": 1_000, "evidencia": {"comprobante": "x"},
                    "proyecto": "otro"})
    assert r.status_code == 400


def test_acunar_venta_a_proyecto_ok(cliente):
    c, base = cliente
    r = c.post("/api/economia/frontera/acunar",
              json={"subtipo": "venta", "destino": "proyecto:atlas",
                    "monto_mm": 50_000,
                    "evidencia": {"comprobante": "cobro-1"},
                    "proyecto": "atlas"})
    assert r.status_code == 200
    asiento = r.json()["asiento"]
    assert asiento["detalle"]["proyecto"] == "atlas"
    assert "trabajo" not in asiento["detalle"]
    k = Kernel(Libro(base / "economia" / "libro.jsonl"))
    assert k.saldo("proyecto:atlas") == 50_000


def test_acunar_venta_a_trabajo_vivo_lleva_proyecto_y_trabajo(cliente):
    c, base = cliente
    b = Bus(base / "economia" / "bus.jsonl")
    b.alta(TS, W, "p1", "dep:legal", "radar", 10_000, 30_000,
          {"gasto_max_mm": 10_000})
    b.marcar(TS, W, "p1", "financiada")  # vivo
    r = c.post("/api/economia/frontera/acunar",
              json={"subtipo": "venta", "destino": "trabajo:p1",
                    "monto_mm": 30_000,
                    "evidencia": {"comprobante": "cobro-2"},
                    "proyecto": "atlas"})
    assert r.status_code == 200
    asiento = r.json()["asiento"]
    assert asiento["detalle"] == {"evidencia": {"comprobante": "cobro-2"},
                                  "proyecto": "atlas", "trabajo": "p1"}
    k = Kernel(Libro(base / "economia" / "libro.jsonl"))
    assert k.saldo("trabajo:p1") == 30_000


def test_acunar_venta_a_trabajo_no_vivo_falla(cliente):
    c, base = cliente
    b = Bus(base / "economia" / "bus.jsonl")
    b.alta(TS, W, "p2", "dep:legal", "radar", 10_000, 30_000,
          {"gasto_max_mm": 10_000})
    # nunca se financia: sigue en "alta", no en "financiada" (no vivo)
    r = c.post("/api/economia/frontera/acunar",
              json={"subtipo": "venta", "destino": "trabajo:p2",
                    "monto_mm": 1_000, "evidencia": {"comprobante": "x"},
                    "proyecto": "atlas"})
    assert r.status_code == 400
    assert "no vivo" in r.json()["detail"]


def test_acunar_subtipo_invalido_falla(cliente):
    c, base = cliente
    r = c.post("/api/economia/frontera/acunar",
              json={"subtipo": "regalo", "destino": "tesoro",
                    "monto_mm": 1_000, "evidencia": {"x": 1}})
    assert r.status_code == 400


def test_acunar_sin_economia_activa_falla(crudo):
    c, base = crudo  # sin sembrar
    r = c.post("/api/economia/frontera/acunar",
              json={"subtipo": "capital", "destino": "tesoro",
                    "monto_mm": 1_000, "evidencia": {"tipo": "firma_pedro"}})
    assert r.status_code == 400
