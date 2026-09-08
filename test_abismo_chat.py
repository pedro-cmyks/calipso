"""El molde que faltaba: `ws_chat` de punta a punta con un modelo local FALSO
y el socket real del TestClient (spec seccion 15).

Nada de esto toca la red ni el home real: el home lo aisla conftest.py y cada
test ademas monkeypatchea las constantes YA CONGELADAS (chats.CHAT_FILE,
telemetry.LEDGER, _ECO_BASE) hacia tmp_path. El modelo es un generador espia
que sigue un guion por invocacion y anota cada payload; el ruteo se fuerza a
local con un `_decide` falso que conserva el parseo REAL de las directivas,
asi `/nube`, `/api` y `/claude` siguen significando lo mismo que en
produccion. El system compilado se reemplaza por una constante (recall,
economia bajo candado y catastro no son lo que se prueba aca), pero
`_sistema_del_turno` sigue siendo el real: la compuerta /nube se ejercita.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso import chats
from calipso.mapa import pulso as p


class MemoriaFalsa:
    """Doble de `Memory`: lo que el turno usa (recall, load_core, remember)."""

    def __init__(self, core: str = ""):
        self.core = core
        self.recordado: list[str] = []

    def recall(self, query, n=5, ambitos=None):
        return []

    def load_core(self):
        return self.core

    def remember(self, text, scope="auto", **meta):
        self.recordado.append(text)
        return "id-falso"


class ModeloEspia:
    """El modelo falso de las rutas local (`_ollama_chat_chunks(url, payload,
    usage)`) y api (`_sse_text_chunks(url, payload, headers, usage)`): en las
    dos, el ultimo posicional es el `usage` mutable. `guiones[i]` es la lista
    de trozos de la invocacion numero i (la ultima se repite si hay mas
    invocaciones que guiones). Anota cada payload en `llamadas`: ahi se lee
    el system, los messages y las options de cada pasada."""

    def __init__(self, guiones):
        self.guiones = [list(g) for g in guiones]
        self.llamadas: list[dict] = []

    def __call__(self, url, payload, *resto):
        usage = resto[-1] if resto else None
        self.llamadas.append(payload)
        trozos = self.guiones[min(len(self.llamadas) - 1, len(self.guiones) - 1)]

        def _gen():
            for t in trozos:
                yield t
            if isinstance(usage, dict):
                usage["prompt_tokens"] = 10
                usage["completion_tokens"] = len(trozos)
        return _gen()


def _decide_local(user_msg, last_features=None, last_verdict=None):
    """`_decide` sin probes ni ranking: ruta local salvo que Pedro fuerce otra
    con un slash (`/api`, `/claude`). Las directivas se parsean con el parser
    REAL, que es lo que hace que `/nube` siga siendo `/nube`."""
    d = srv.capabilities.parse_directives(user_msg)
    route = d.get("force_route") or "local"
    client = d.get("force_model") if route == "subscription" else None
    verdict = {"route": route, "client": client, "model": "modelo-falso",
               "model_id": f"{route}:modelo-falso", "persona": "Epicteto",
               "tier": "small", "effort": 1, "effort_name": "balanced",
               "session": "s", "source": "harness", "why": "harness"}
    features = {"type": "chat", "complexity": 1, "needs_repo": False,
                "needs_web": False, "private": False}
    return verdict, features, [], d


class Harness:
    def __init__(self, cliente, chat_id, modelo, memoria, pulso, tmp):
        self.cliente = cliente
        self.chat_id = chat_id
        self.modelo = modelo
        self.memoria = memoria
        self.pulso = pulso
        self.tmp = tmp

    def paquete(self, texto, departamento=None):
        paquete = {"text": texto, "chat_id": self.chat_id}
        if departamento:
            paquete["departamento"] = departamento
        return json.dumps(paquete)

    def turno(self, texto, departamento=None, hasta_dones=1):
        """Manda un paquete real y junta todo lo que el server emite hasta el
        `done` numero `hasta_dones` (2 cuando un steer encola otro turno)."""
        with self.cliente.websocket_connect("/ws/chat") as ws:
            ws.send_text(self.paquete(texto, departamento))
            return self.recibir(ws, hasta_dones)

    @staticmethod
    def recibir(ws, hasta_dones=1):
        eventos, dones = [], 0
        while dones < hasta_dones:
            ev = ws.receive_json()
            eventos.append(ev)
            if ev.get("type") == "done":
                dones += 1
        return eventos

    def mensajes(self):
        return chats.get(self.chat_id)["messages"]

    def telemetria(self, kind=None):
        ruta = self.tmp / "telemetry.jsonl"
        if not ruta.exists():
            return []
        filas = [json.loads(linea) for linea in
                 ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]
        return [f for f in filas if kind is None or f.get("kind") == kind]


def de_tipo(eventos, tipo):
    return [e for e in eventos if e.get("type") == tipo]


def texto_visible(eventos):
    return "".join(e["text"] for e in de_tipo(eventos, "chunk"))


@pytest.fixture
def chat(tmp_path, monkeypatch):
    monkeypatch.setattr(chats, "CHAT_FILE", tmp_path / "chats.json")
    monkeypatch.setattr(srv.telemetry, "LEDGER", tmp_path / "telemetry.jsonl")
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    memoria = MemoriaFalsa()
    monkeypatch.setattr(srv, "mem", memoria)
    pu = p.Pulso()
    monkeypatch.setattr(srv, "EL_PULSO", pu)
    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: True)
    monkeypatch.setattr(srv, "_decide", _decide_local)
    monkeypatch.setattr(srv, "_build_context",
                        lambda user_msg, runtime, features=None: "SISTEMA BASE")
    monkeypatch.setattr(srv, "_harness_context", lambda *a, **k: "estado")
    monkeypatch.setattr(srv, "_extract_edit_target", lambda *a, **k: None)
    # la fuente `proyecto` recibe `catastro.obtener`, que sin catastro.json
    # en el home de la suite ESCANEA el home real de Pedro (`cargar()` ->
    # `escanear()` sobre `Path.home()`): cerrado aca para todo el harness;
    # los tests de esa fuente inyectan el suyo
    monkeypatch.setattr(srv.catastro, "obtener", lambda nombre: None)
    monkeypatch.setattr(srv.goals, "active", lambda raiz: None)
    monkeypatch.setattr(srv.goals, "detect", lambda texto: None)
    modelo = ModeloEspia([["hola ", "Pedro"]])
    monkeypatch.setattr(srv.dispatch, "_ollama_chat_chunks", modelo)
    monkeypatch.setattr(srv.dispatch, "_sse_text_chunks", modelo)
    creado = chats.create(str(srv.ROOT), "prueba")
    cliente = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})
    return Harness(cliente, creado["id"], modelo, memoria, pu, tmp_path)


def test_un_turno_plano_da_thinking_chunks_y_un_solo_done(chat):
    eventos = chat.turno("hola")
    tipos = [e["type"] for e in eventos]
    assert tipos[0] == "thinking"
    assert texto_visible(eventos) == "hola Pedro"
    assert tipos.count("done") == 1 and tipos[-1] == "done"
    assert len(chat.modelo.llamadas) == 1
    # el par user/assistant queda escrito una sola vez, y la memoria tambien
    assert [(m["role"], m["text"]) for m in chat.mensajes()] == [
        ("user", "hola"), ("assistant", "hola Pedro")]
    assert len(chat.memoria.recordado) == 1


def test_la_llamada_local_del_chat_fija_num_ctx(chat):
    """La leccion de la medicion del jefe (spec seccion 4): Ollama trunca
    desde el COMIENZO y sin `num_ctx` explicito la reentrada con 6000 chars
    de bloques se comeria el system con el contrato, en silencio."""
    chat.turno("hola")
    payload = chat.modelo.llamadas[0]
    assert payload["options"]["num_ctx"] == srv.CHAT_NUM_CTX == 8192
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][-1] == {"role": "user", "content": "hola"}
