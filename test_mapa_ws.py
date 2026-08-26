"""Tests del WS del pulso (spec seccion 6). Patron TestClient del repo."""
import asyncio

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


def test_el_envoltorio_anda_igual_sin_pulso(monkeypatch):
    """La instrumentacion no puede ser una fuente de errores nueva: si el
    pulso no se pudo importar, el equipo dinamico tiene que correr igual."""
    monkeypatch.setattr(srv, "EL_PULSO", None)
    with srv._pulso_agente("a1", departamento="dep:atlas") as mango:
        mango.razonando("no se publica en ningun lado")
        mango.tokens(1, 2, 3)
        mango.diff("a.py", "- x\n+ y")


def test_el_envoltorio_publica_cuando_hay_pulso(monkeypatch):
    pu = p.Pulso()
    monkeypatch.setattr(srv, "EL_PULSO", pu)
    with srv._pulso_agente("a1", departamento="dep:atlas", rol="scout") as mango:
        mango.razonando("mirando")
    assert [e["evento"] for e in pu.eventos("a1")] == [
        "inicio", "razonando", "fin"]
    assert pu.empleados("dep:atlas")[0]["rol"] == "scout"


def test_el_borrador_es_su_propio_agente_y_cierra_con_su_fin(tmp_path,
                                                            monkeypatch):
    """El borrador se lanza con `ensure_future` y llama a otro modelo: si
    publicara sobre el agente del turno, su `diff` caeria despues del `fin`
    de ese turno, `estado_de` diria "esperando" en vez de "liberado" y a los
    diez minutos el escritorio quedaria "inactivo" — el fantasma que el
    `fin` existe para evitar. El orden de sus eventos es lo que lo prueba."""
    pu = p.Pulso()
    monkeypatch.setattr(srv, "EL_PULSO", pu)
    # el borrador cobra su unidad de suscripcion: sin esto el test le escribe
    # al libro de VERDAD de quien lo corra
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "PENDING_CHANGES", {})
    monkeypatch.setattr(srv.goals, "active", lambda raiz: None)
    monkeypatch.setattr(srv.developer, "chat_draft_brief",
                        lambda *a, **k: {"job": {"id": "j1"}, "system": "s",
                                         "user_msg": "u"})
    monkeypatch.setattr(srv, "_run_subscription_text",
                        lambda *a, **k: "linea nueva\n")
    monkeypatch.setattr(srv.jobs, "write_artifact", lambda *a, **k: None)
    monkeypatch.setattr(srv.jobs, "update", lambda *a, **k: None)

    class _WSFalso:
        def __init__(self):
            self.enviados = []

        async def send_json(self, payload):
            self.enviados.append(payload)

    ws = _WSFalso()
    asyncio.run(srv._run_chat_draft(ws, "cambia algo", "no-existe.py",
                                    "chat:abc:borrador", "dep:atlas"))

    assert [e["evento"] for e in pu.eventos("chat:abc:borrador")] == [
        "inicio", "diff", "fin"]
    # y el agente del turno no se queda con un diff colgado despues de su fin
    assert pu.eventos("chat:abc") == []
    diff = pu.eventos("chat:abc:borrador")[1]
    assert diff["ruta"] == "no-existe.py"
    # el mismo texto que Pedro ve como propuesta
    assert diff["diff"] == ws.enviados[-1]["proposal"]["diff"]


def test_el_borrador_sin_agente_corre_igual(monkeypatch):
    """`_pulso_agente` degrada tambien cuando no hay id: el borrador tiene
    que poder correr sin que nadie le haya dado un agente."""
    pu = p.Pulso()
    monkeypatch.setattr(srv, "EL_PULSO", pu)
    with srv._pulso_agente(None, departamento="dep:atlas") as mango:
        mango.diff("a.py", "- x\n+ y")
    assert pu.recientes() == []
