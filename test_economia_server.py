# test_economia_server.py
"""Tests de los endpoints de economia (patron TestClient + cookie del repo)."""
import json
import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    # economia activa en un HOME temporal
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    k.acunar("2026-08-25T09:00:00", "2026-W35", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    # sin cache: cada request reconstruye desde los archivos
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_tablero_responde(cliente):
    r = cliente.get("/api/economia/tablero")
    assert r.status_code == 200
    body = r.json()
    assert body["activa"] is True
    assert body["tablero"]["tesoro_mm"] == 1_200_000


def test_cola_atender_carta(cliente):
    # sembrar una carta via los modulos (el server comparte la carpeta)
    r = cliente.get("/api/economia/cola")
    assert r.json()["pendientes"] == []


def test_sin_auth_rechaza(tmp_path):
    c = TestClient(srv.app)
    assert c.get("/api/economia/tablero",
                 follow_redirects=False).status_code in (302, 401, 403)
