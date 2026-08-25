"""Tests del endpoint del mapa (patron TestClient + cookie del repo)."""
import json
import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso.economia import departamentos as deps
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("mercado", deps.ZONA_FABRICA))
    r.alta(deps.Departamento("curiosos", deps.ZONA_FABRICA))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    k.acunar("2026-08-25T09:00:00", "2026-W35", "dep:mercado", 50_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_ciudad_responde_con_coordenadas(cliente):
    r = cliente.get("/api/mapa/ciudad")
    assert r.status_code == 200
    body = r.json()
    assert body["activa"] is True
    edis = {e["id"]: e for e in body["ciudad"]["edificios"]}
    assert edis["dep:mercado"]["saldo_mm"] == 50_000
    assert edis["dep:mercado"]["tamano"] == 3
    for e in edis.values():
        assert isinstance(e["x"], int) and isinstance(e["y"], int)


def test_ciudad_es_estable_entre_llamadas(cliente):
    """Invariante 2: el mapa no se mueve solo entre dos requests."""
    uno = cliente.get("/api/mapa/ciudad").json()
    dos = cliente.get("/api/mapa/ciudad").json()
    assert uno["ciudad"]["edificios"] == dos["ciudad"]["edificios"]


def test_sin_economia_responde_inactiva(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / "vacio")
    c = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})
    assert c.get("/api/mapa/ciudad").json() == {"activa": False}


def test_sin_auth_rechaza(cliente):
    c = TestClient(srv.app)
    assert c.get("/api/mapa/ciudad",
                 follow_redirects=False).status_code in (302, 401, 403)
