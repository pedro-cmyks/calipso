# test_siembra_server.py -- el endpoint HTTP del helper guiado de siembra:
# preview sin token, ejecuta con el token exacto.
import pytest

import calipso.routines as calipso_routines
import calipso.server as srv
from fastapi.testclient import TestClient

TS = "2026-08-26T10:00:00"
W = "2026-W35"


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    # routines.py congela CALIPSO_HOME en una constante de modulo al
    # importarse y su helper de ruta la usa directo, asi que el setenv de
    # abajo no alcanza solo: hay que pisar tambien el atributo del modulo
    # ya importado -- si no, el test que ejecuta (agrega rutinas de
    # departamento) contamina el home compartido de la suite y rompe otros
    # tests.
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    monkeypatch.setattr(calipso_routines, "CALIPSO_HOME", tmp_path)
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def _body(confirmacion=""):
    return {
        "confirmacion": confirmacion,
        "departamentos": [
            {"nombre": "taller", "zona": "fabrica"},
            {"nombre": "development", "zona": "fabrica"},
            {"nombre": "research", "zona": "fabrica"},
            {"nombre": "finanzas", "zona": "personal"}],
        "suscripciones": {"claude_max": {"costo_mensual_mm": 200_000,
                                         "capacidad_ciclo": 2_000,
                                         "reserva_personal": 200,
                                         "costo_api_mm_por_unidad": 500}},
        "capital_tesoro_mm": 100_000,
        "cuota_firmable_mpt": 4_000, "reserva_personal_mpt": 1_000,
        "rutina_interval_min": 60,
        "perillas_fabrica": {"presupuesto_semanal_mm": 25_000,
                             "techo_preseed_mm": 50_000,
                             "techo_preseed_ciclo_mm": 150_000,
                             "techo_api_ciclo_mm": 0}}


def test_preview_sin_token_no_escribe(cliente, tmp_path):
    r = cliente.post("/api/economia/sembrar-guiado", json=_body())
    assert r.status_code == 200
    assert r.json()["estado"]["sembrada"] is False
    assert not (tmp_path / "economia").exists()


def test_token_incorrecto_no_ejecuta(cliente, tmp_path):
    r = cliente.post("/api/economia/sembrar-guiado", json=_body("dale"))
    assert r.status_code == 400
    assert not (tmp_path / "economia").exists()


def test_token_exacto_ejecuta(cliente, tmp_path):
    r = cliente.post("/api/economia/sembrar-guiado",
                     json=_body("sembrar la economia"))
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["estado"]["sembrada"] is True and j["estado"]["modo"] == "vivo"
    assert (tmp_path / "economia" / "departamentos.json").exists()
