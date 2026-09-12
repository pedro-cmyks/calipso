"""Los seis sitios que hablan con Ollama pasan por `carga.payload_local`
(spec 2026-09-11, 3.6): el chat, los agentes del equipo, el clasificador del
planner, el jefe, el juez de /nube y la vision. En Ollama gana el keep_alive
de la ULTIMA request: por eso los seis tienen que coincidir. Mas: el juez con
CHAT_NUM_CTX, el planner sin 3b fuera de holgada, build_team con el avail del
turno, pick_model sin snapshot, y resource_dispatcher retirado.
"""
from __future__ import annotations

import asyncio
import importlib.util
import json
import urllib.request

import pytest

import calipso.server as srv
import dispatch
from calipso import attachments, carga, orchestrator
from calipso.privacidad import juez_llm


@pytest.fixture(autouse=True)
def _limpio():
    carga.olvidar()
    yield
    carga.olvidar()


class _Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def read(self):
        return self.cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _seis_payloads(monkeypatch, nivel):
    """Recorre los seis sitios con `nivel` como nivel reciente (y explicito en
    el chat) y devuelve {sitio: payload}. El clasificador solo aparece bajo
    holgada: fuera de ahi no hay POST (es lo que se prueba aparte)."""
    monkeypatch.setattr(carga, "nivel_reciente", lambda: nivel)
    vistos: dict = {"post": []}

    def post(url, payload, headers=None):
        vistos["post"].append(payload)
        return {"response": json.dumps({"tramos": [], "agents": []})}
    monkeypatch.setattr(dispatch, "_http_post_json", post)
    # 1. el chat
    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: True)

    def chunks(url, payload, usage=None):
        vistos["chat"] = payload
        return iter(())
    monkeypatch.setattr(srv.dispatch, "_ollama_chat_chunks", chunks)
    srv._chunks_for("local", "s", "u", {}, history=[], nivel=nivel)
    # 2. los agentes del equipo (y la sintesis y sus fallbacks: el mismo helper)
    srv._run_backend_text("local", None, None, "s", "u")
    vistos["agentes"] = vistos["post"][-1]
    # 3. el clasificador del planner
    if nivel == "holgada":
        srv._plan_dynamic_team("hace algo", {"type": "code", "complexity": 3}, nivel)
        vistos["clasificador"] = vistos["post"][-1]
    # 4. el jefe
    srv._pensar_local("p")
    vistos["jefe"] = vistos["post"][-1]
    # 5. el juez
    juez_llm.juzgar_llm("texto")
    vistos["juez"] = vistos["post"][-1]
    # 6. la vision (urllib propio, no pasa por dispatch)

    def urlopen(req, timeout=None):
        vistos["vision"] = json.loads(req.data.decode())
        return _Resp(b'{"response": "una foto"}')
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr(attachments, "image_bytes_b64", lambda root, aid: ("YWJj", "image/png"))
    assert attachments._vision_ollama(None, ["a1"], "que es?", "moondream") == "una foto"
    return vistos


def test_bajo_cargada_los_seis_llevan_keep_alive_0_y_la_mitad_de_los_hilos(monkeypatch):
    vistos = _seis_payloads(monkeypatch, "cargada")
    sitios = ["chat", "agentes", "jefe", "juez", "vision"]
    for s in sitios:
        assert vistos[s]["keep_alive"] == 0, s
        assert vistos[s]["options"]["num_thread"] == carga.num_thread("cargada"), s
    assert vistos["chat"]["options"]["num_ctx"] == srv.CHAT_NUM_CTX
    assert vistos["jefe"]["options"] == {"temperature": 0, "num_ctx": carga.CHAT_NUM_CTX,
                                         "num_thread": carga.num_thread("cargada")}
    assert vistos["juez"]["options"]["num_ctx"] == carga.CHAT_NUM_CTX     # unificado con el chat
    assert vistos["juez"]["format"] == "json" and vistos["juez"]["options"]["temperature"] == 0
    assert vistos["vision"]["images"] == ["YWJj"] and vistos["vision"]["model"] == "moondream"
    assert carga.en_uso == 0


def test_bajo_holgada_los_seis_llevan_5m_y_ningun_num_thread(monkeypatch):
    vistos = _seis_payloads(monkeypatch, "holgada")
    for s in ["chat", "agentes", "clasificador", "jefe", "juez", "vision"]:
        assert vistos[s]["keep_alive"] == "5m", s
        assert "num_thread" not in (vistos[s].get("options") or {}), s
    assert vistos["chat"]["options"] == {"num_ctx": srv.CHAT_NUM_CTX}     # byte a byte (test_turno_secciones)
    assert "options" not in vistos["agentes"]
    assert vistos["clasificador"]["options"] == {"temperature": 0} and vistos["clasificador"]["format"] == "json"
    assert srv.CHAT_NUM_CTX == carga.CHAT_NUM_CTX == 8192


def test_bajo_justa_las_perillas_son_2m_y_la_mitad(monkeypatch):
    vistos = _seis_payloads(monkeypatch, "justa")
    assert vistos["chat"]["keep_alive"] == "2m"
    assert vistos["jefe"]["options"]["num_thread"] == carga.num_thread("justa")


def test_el_planner_no_llama_al_3b_fuera_de_holgada_y_lo_anota(monkeypatch):
    filas = []
    monkeypatch.setattr(srv.telemetry, "log_event", lambda kind, **k: filas.append({"kind": kind, **k}))

    def nunca(url, payload, headers=None):
        raise AssertionError("POST al 3b bajo carga")
    monkeypatch.setattr(dispatch, "_http_post_json", nunca)
    for nivel in ("justa", "cargada"):
        plan = srv._plan_dynamic_team("arma un plan de la ciudad", {"type": "code", "complexity": 3}, nivel)
        assert plan["agents"] and plan["agents"][0]["role"] == "arquitecto"
    assert [f["accion"] for f in filas if f["kind"] == "carga"] == ["sin_3b", "sin_3b"]
    assert filas[0]["nivel"] == "justa"
    # sin nivel explicito toma el reciente
    monkeypatch.setattr(carga, "nivel_reciente", lambda: "cargada")
    srv._plan_dynamic_team("arma un plan", {"type": "code", "complexity": 3})
    assert len([f for f in filas if f.get("accion") == "sin_3b"]) == 3


def test_build_team_recibe_el_avail_del_turno_y_no_toma_otro(monkeypatch):
    """Un solo avail por turno (spec 3.5): el filtrado por carga en _decide
    es el que ve build_team. Molde de test_mapa_foco.py:139-176."""
    vistos = {}
    monkeypatch.setattr(srv, "_plan_dynamic_team", lambda *a, **k: {"plan": 1})

    def no(*a, **k):
        raise AssertionError("_backend_availability no se llama con avail en el veredicto")
    monkeypatch.setattr(srv, "_backend_availability", no)
    monkeypatch.setattr(srv.sessions, "active", lambda *a, **k: None)

    def build_team(plan_obj, available, **k):
        vistos["avail"] = available
        return {"agents": [{"role": "scout", "task": "mira", "model": "m",
                            "persona": "explorador", "route": "api"}], "synthesis": ""}
    monkeypatch.setattr(srv.orchestrator, "build_team", build_team)
    monkeypatch.setattr(srv.orchestrator, "agent_system", lambda *a, **k: "s")
    monkeypatch.setattr(srv.orchestrator, "synthesis_prompt", lambda *a, **k: "u")
    monkeypatch.setattr(srv.telemetry, "log_event", lambda *a, **k: None)
    monkeypatch.setattr(srv, "_run_backend_text", lambda *a, **k: "listo")

    async def _agente(ws, inbox, agent, system, task):
        return "hecho", None
    monkeypatch.setattr(srv, "_run_agent_text", _agente)

    class WSFalso:
        def __init__(self):
            self.enviados = []

        async def send_json(self, dato):
            self.enviados.append(dato)
    avail = {"local:qwen2.5:7b": False, "subscription:claude:sonnet": True}
    final, _, _ = asyncio.run(srv._run_dynamic_team(
        WSFalso(), asyncio.Queue(), "hace algo", {}, "base",
        {"route": "api", "client": None, "model": "m", "avail": avail,
         "carga_medicion": {"nivel": "cargada"}}))
    assert final == "listo" and vistos["avail"] == avail


def test_pick_model_no_mira_la_maquina_y_resource_dispatcher_se_fue(monkeypatch):
    assert not hasattr(orchestrator, "_rd") and not hasattr(dispatch, "_rd") and not hasattr(srv, "_rd")
    assert importlib.util.find_spec("calipso.resource_dispatcher") is None

    def nunca(*a, **k):
        raise AssertionError("pick_model salio a la red")
    monkeypatch.setattr(urllib.request, "urlopen", nunca)
    todo = {k: True for k in srv.capabilities.REGISTRY}
    picked = orchestrator.pick_model("small", "trivial", todo)
    assert picked is not None and picked[1].get("route") == "local"
    assert not [r for r in srv.app.routes if getattr(r, "path", "") == "/api/resources"]


def test_la_vision_por_ollama_solo_corre_con_permiso(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(attachments, "load", lambda root, aid: {"mime": "image/png"})
    monkeypatch.setattr(attachments, "ollama_vision_model", lambda: "moondream")
    llamadas = []
    monkeypatch.setattr(attachments, "_vision_ollama",
                        lambda root, ids, q, model: llamadas.append(model) or "una foto")
    assert attachments.vision_describe(None, ["a1"], "q", quien=None, permitir_ollama=False) is None
    assert llamadas == []
    assert attachments.vision_describe(None, ["a1"], "q", quien=None) == "una foto"
    assert llamadas == ["moondream"]
