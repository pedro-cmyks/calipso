"""Los endpoints del interruptor y la rutina del departamento."""
import pytest
from fastapi.testclient import TestClient

import calipso.routines as routines
import calipso.server as srv
from calipso.plantel import interruptor as it


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_el_tablero_del_plantel_arranca_en_ensayo(cliente):
    d = cliente.get("/api/plantel").json()
    assert d["encendido"] is True and d["modo"] == "ensayo"


def test_parar_y_reanudar_por_http(cliente, tmp_path):
    assert cliente.post("/api/plantel/parar").json()["encendido"] is False
    assert it.leer(tmp_path).encendido is False
    assert cliente.post("/api/plantel/reanudar").json()["encendido"] is True


def test_poner_el_modo_por_http(cliente, tmp_path):
    assert cliente.put("/api/plantel/modo", json={"modo": "vivo"}).json()["modo"] == "vivo"
    assert it.leer(tmp_path).modo == "vivo"


def test_un_modo_inventado_se_rechaza_con_400(cliente, tmp_path):
    """El endpoint es la superficie por la que se suelta a la fabrica a
    gastar: no puede aceptar cualquier cosa."""
    assert cliente.put("/api/plantel/modo", json={"modo": "turbo"}).status_code == 400
    assert it.leer(tmp_path).modo == "ensayo"


def test_sin_auth_no_se_puede_parar_ni_soltar():
    c = TestClient(srv.app)
    assert c.post("/api/plantel/parar", follow_redirects=False).status_code in (401, 403, 302)


def test_la_rutina_de_departamento_es_un_kind_valido():
    assert "departamento" in routines.KINDS


def test_la_rutina_guarda_a_que_departamento_pertenece(tmp_path, monkeypatch):
    """El ticker le pasa la rutina al handler: si no lleva la cuenta, el
    handler no sabe a quien despertar."""
    monkeypatch.setattr(routines, "CALIPSO_HOME", tmp_path)
    r = routines.add("departamento", "atlas", 60, cuenta="dep:atlas")
    assert r["cuenta"] == "dep:atlas"
    assert routines.get(r["id"])["cuenta"] == "dep:atlas"


def test_las_rutinas_viejas_sin_cuenta_no_revientan(tmp_path, monkeypatch):
    """El archivo de rutinas de Pedro ya existe y sus entradas NO tienen el
    campo. Usar `add` no probaria eso, porque `add` siempre lo escribe: hay
    que escribir el archivo a mano, como quedo en disco antes del cambio."""
    import json
    monkeypatch.setattr(routines, "CALIPSO_HOME", tmp_path)
    (tmp_path / "routines.json").write_text(json.dumps([
        {"id": "rt_viejo", "kind": "reflect", "label": "reflexionar",
         "interval_minutes": 1440, "enabled": False,
         "last_run": None, "last_status": None}]), encoding="utf-8")
    viejas = routines.load()
    assert viejas and viejas[0].get("cuenta") is None
    assert routines.get("rt_viejo")["kind"] == "reflect"
