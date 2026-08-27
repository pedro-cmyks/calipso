"""La mesa de Pedro por HTTP: leer el bus, financiar y descartar."""
import json

import pytest
from fastapi.testclient import TestClient

from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.bus import Bus
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
import calipso.server as srv

TS = "2026-08-26T10:00:00"
W = "2026-W35"


def _economia_de_prueba(base, abrir=True):
    """Una economia minima en disco, como la que arma el bootstrap real."""
    eco = base / "economia"
    eco.mkdir(parents=True, exist_ok=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=25_000))
    r.alta(deps.Departamento("mercado", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=25_000))
    if abrir:
        pt.emitir_semana(k, TS, W, 4_000, 1_000)
    k.acunar(TS, W, "dep:atlas", 400_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 200_000,
                       "capacidad_ciclo": 2_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    return eco


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    _economia_de_prueba(tmp_path)
    return TestClient(srv.app), tmp_path


def _propuesta(base, id="p1", cuenta="dep:atlas", titulo="radar de precios"):
    b = Bus(base / "economia" / "bus.jsonl")
    b.alta(TS, W, id, cuenta, titulo, 10_000, 10_000,
           {"gasto_max_mm": 10_000, "semanas_max": 4})
    return b


def test_el_bus_vacio_devuelve_una_lista_vacia(cliente):
    c, base = cliente
    r = c.get("/api/economia/bus", params={"token": srv.TOKEN})
    assert r.status_code == 200
    d = r.json()
    assert d["activa"] is True
    assert d["propuestas"] == []


def test_una_propuesta_llega_con_lo_que_la_mesa_necesita(cliente):
    c, base = cliente
    _propuesta(base)
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert len(d["propuestas"]) == 1
    p = d["propuestas"][0]
    assert p["id"] == "p1"
    assert p["estado"] == "alta"
    assert p["departamento"] == "dep:atlas"
    assert p["titulo"] == "radar de precios"
    assert p["presupuesto_mm"] == 10_000
    assert p["gastado_mm"] == 0
    assert p["aportes"] == {}


def test_los_departamentos_son_solo_los_de_la_fabrica(cliente):
    """El libro rechaza cualquier financiador fuera de la zona fabrica, asi
    que ofrecer otro en el selector seria ofrecer un boton que falla."""
    c, base = cliente
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    cuentas = {x["cuenta"] for x in d["departamentos"]}
    assert cuentas == {"dep:atlas", "dep:mercado"}
    assert all(x["zona"] == deps.ZONA_FABRICA for x in d["departamentos"])
    atlas = next(x for x in d["departamentos"] if x["cuenta"] == "dep:atlas")
    assert atlas["disponible_mm"] == 400_000


def test_dice_si_la_semana_esta_abierta(tmp_path, monkeypatch):
    """Sin emision de PT esa semana, TODA financiacion falla. Que la mesa lo
    diga antes es la diferencia entre un aviso y un error incomprensible."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    _economia_de_prueba(tmp_path, abrir=False)
    c = TestClient(srv.app)
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["semana_abierta"] is False


def test_sin_economia_no_esta_activa(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    c = TestClient(srv.app)
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["activa"] is False


def test_sin_token_no_se_lee_el_bus(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    c = TestClient(srv.app)
    assert c.get("/api/economia/bus").status_code == 401
