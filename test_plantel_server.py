"""Los endpoints del interruptor y la rutina del departamento."""
import json

import dispatch
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
    gastar: no puede aceptar cualquier cosa.

    La asercion mira el archivo crudo, no `it.leer`: `leer` normaliza
    cualquier modo desconocido a "ensayo", asi que pasaria igual aunque
    `poner_modo` hubiera llegado a escribir "turbo" en disco."""
    assert cliente.put("/api/plantel/modo", json={"modo": "turbo"}).status_code == 400
    ruta = it.ruta(tmp_path)
    crudo = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    assert crudo.get("modo") != "turbo"


def test_sin_auth_no_se_puede_parar_ni_soltar(tmp_path, monkeypatch):
    """Si el auth_guard alguna vez se rompe, este test no puede terminar
    escribiendo en el ~/.calipso real y parando la fabrica de Pedro."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    c = TestClient(srv.app)
    assert c.post("/api/plantel/parar", follow_redirects=False).status_code in (401, 403, 302)


def test_pensar_local_no_corre_claude_por_subscripcion(monkeypatch):
    """La trampa cara del brief: decidir por el escalon barato no puede
    terminar ejecutando `claude -p`, que gastaria una unidad de suscripcion
    por tic y por departamento. `_pensar_local` tiene que pegarle al
    clasificador (Ollama) y nunca abrir un subproceso."""
    llamadas = []

    def falso_post(url, payload, headers=None):
        llamadas.append(url)
        return {"response": "nada -- sin plata"}

    def spia_subprocess(*args, **kwargs):
        raise AssertionError("_pensar_local no puede correr un subproceso")

    monkeypatch.setattr(dispatch, "_http_post_json", falso_post)
    monkeypatch.setattr(srv.subprocess, "run", spia_subprocess)

    resultado = srv._pensar_local("hola")

    assert llamadas == [dispatch.CONFIG["classifier"]["base_url"]]
    assert resultado == "nada -- sin plata"


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
