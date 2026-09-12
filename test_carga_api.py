"""GET /api/carga (spec 2026-09-11, seccion 4): la medicion actual (por el
hook: nada mide) y las cuentas del dia derivadas de telemetria; loopback con
el token y un navegador ven todo, el tablero tambien (fila en ALCANCES: sin
ella, 403 fail-closed), el lector 403, sin credencial 401. Reemplaza a
GET /api/resources."""
from __future__ import annotations

import datetime
import json

import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso import carga
from test_aduana_api import _almacen_aislado, _pedir, _sesion, REMOTO  # noqa: F401
from test_carga import medida


@pytest.fixture
def api(monkeypatch, tmp_path):
    carga.olvidar()
    monkeypatch.setattr(srv, "_medir_carga", lambda: medida("cargada", mem=480, modelos=["qwen2.5:7b"]))
    monkeypatch.setattr(srv.telemetry, "LEDGER", tmp_path / "telemetry.jsonl")
    hoy = datetime.date.today().isoformat()
    filas = [{"ts": f"{hoy}T10:00:00", "kind": "carga", "accion": "suscripcion"},
             {"ts": f"{hoy}T10:01:00", "kind": "carga", "accion": "descarga"},
             {"ts": f"{hoy}T10:02:00", "kind": "carga", "accion": "pospone"},
             {"ts": "2026-01-01T10:00:00", "kind": "carga", "accion": "suscripcion"},
             {"ts": f"{hoy}T10:03:00", "kind": "chat_turn"}]
    (tmp_path / "telemetry.jsonl").write_text(
        "\n".join(json.dumps(f) for f in filas) + "\n", encoding="utf-8")
    yield
    carga.olvidar()


def test_loopback_ve_la_medicion_y_las_cuentas_del_dia(api):
    r = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN}).get("/api/carga")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["medicion"]["nivel"] == "cargada" and d["medicion"]["mem_disponible_mb"] == 480
    assert d["medicion"]["modelos_cargados"] == ["qwen2.5:7b"] and d["medicion"]["medido"]["ollama"] is True
    assert d["hoy"] == {"suscripcion": 1, "local_con_aviso": 0, "descarga": 1,
                        "pospone": 1, "sin_3b": 0, "sin_vision": 0}


def test_navegador_y_tablero_lo_ven_el_lector_no(api):
    nav = _pedir(REMOTO, "GET", "/api/carga", cookies={srv.COOKIE_SESION: _sesion("navegador", "Celular")})
    assert nav.status_code == 200, nav.text
    assert nav.json()["medicion"]["nivel"] == "cargada"
    tab = _pedir(REMOTO, "GET", "/api/carga", cookies={srv.COOKIE_SESION: _sesion("tablero", "Musnap")})
    assert tab.status_code == 200, tab.text
    assert tab.json()["hoy"]["descarga"] == 1
    lec = _pedir(REMOTO, "GET", "/api/carga", cookies={srv.COOKIE_SESION: _sesion("lector", "Musnap")})
    assert lec.status_code == 403 and lec.json() == {"detail": "fuera del alcance del aparato"}


def test_sin_credencial_es_401(api):
    assert TestClient(srv.app).get("/api/carga").status_code == 401
