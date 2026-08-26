"""Tests del WS del pulso (spec seccion 6). Patron TestClient del repo."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import calipso.server as srv
from calipso.mapa import pulso as p


@pytest.fixture
def cliente(monkeypatch):
    # un pulso limpio por test: EL_PULSO es del proceso y dos tests que
    # comparten anillo se contaminan segun el orden en que corran
    monkeypatch.setattr(srv, "EL_PULSO", p.Pulso())
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_el_que_llega_tarde_recibe_lo_que_el_anillo_todavia_guarda(cliente):
    """Un agente arranco antes de que Pedro abriera el mapa. Si el WS
    mandara solo lo que pase de ahora en adelante, el escritorio quedaria
    vacio hasta el proximo evento, que puede tardar minutos."""
    srv.EL_PULSO.publicar("a1", "inicio", departamento="dep:atlas",
                          rol="scout", modelo="sonnet")
    with cliente.websocket_connect("/ws/mapa") as ws:
        ev = ws.receive_json()
    assert ev["agente_id"] == "a1" and ev["evento"] == "inicio"
    assert ev["departamento"] == "dep:atlas"


def test_lo_que_se_publica_despues_tambien_llega(cliente):
    with cliente.websocket_connect("/ws/mapa") as ws:
        srv.EL_PULSO.publicar("a1", "inicio", departamento="dep:atlas")
        assert ws.receive_json()["evento"] == "inicio"
        srv.EL_PULSO.publicar("a1", "razonando", texto="mirando el libro")
        segundo = ws.receive_json()
    assert segundo["evento"] == "razonando"
    assert segundo["texto"] == "mirando el libro"
    assert segundo["seq"] > 1


def test_el_foco_sale_por_el_mismo_socket(cliente):
    with cliente.websocket_connect("/ws/mapa") as ws:
        srv.EL_PULSO.enfocar("dep:atlas")
        ev = ws.receive_json()
    assert ev == {"seq": 1, "ts": ev["ts"], "agente_id": None,
                  "evento": "foco", "departamento": "dep:atlas",
                  "trabajo": None, "rol": None, "modelo": None}


def test_sin_auth_no_deja_entrar():
    """El auth_guard es middleware HTTP y NO corre para websockets: la
    guarda del socket es la del handler, y este test es lo unico que la
    sostiene."""
    c = TestClient(srv.app)
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws/mapa") as ws:
            ws.receive_json()


def test_el_ws_no_depende_de_la_economia(cliente, tmp_path, monkeypatch):
    """La ciudad puede estar inactiva y el pulso seguir latiendo: son dos
    canales distintos (spec seccion 6, degradacion limpia)."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / "vacio")
    assert cliente.get("/api/mapa/ciudad").json() == {"activa": False}
    srv.EL_PULSO.publicar("a1", "inicio", departamento="dep:atlas")
    with cliente.websocket_connect("/ws/mapa") as ws:
        assert ws.receive_json()["evento"] == "inicio"
