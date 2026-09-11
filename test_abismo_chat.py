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
import threading
import time

import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso import chats
from calipso.mapa import pulso as p


class MemoriaFalsa:
    """Doble de `Memory`: lo que el turno usa (recall, load_core, remember).
    `recordado` son los textos (lo que los tests viejos asertan);
    `guardados` es cada llamada entera: (texto, scope, meta), para mirar la
    procedencia que el turno escribe (spec 2026-09-11)."""

    def __init__(self, core: str = ""):
        self.core = core
        self.recordado: list[str] = []
        self.guardados: list[tuple[str, str, dict]] = []

    def recall(self, query, n=5, ambitos=None):
        return []

    def load_core(self):
        return self.core

    def remember(self, text, scope="auto", **meta):
        self.recordado.append(text)
        self.guardados.append((text, scope, dict(meta)))
        return "id-falso"


class ModeloEspia:
    """El modelo falso de las rutas local (`_ollama_chat_chunks(url, payload,
    usage)`) y api (`_sse_text_chunks(url, payload, headers, usage)`): en las
    dos, el ultimo posicional es el `usage` mutable. `guiones[i]` es la lista
    de trozos de la invocacion numero i (la ultima se repite si hay mas
    invocaciones que guiones). Anota cada payload en `llamadas`: ahi se lee
    el system, los messages y las options de cada pasada."""

    def __init__(self, guiones, usages=None):
        self.guiones = [list(g) for g in guiones]
        # `usages[i]`: lo que la invocacion i escribe en su usage ademas de
        # prompt_tokens=10 / completion_tokens (la ultima se repite); sirve
        # para simular done_reason="length" o un prompt_eval_count real
        self.usages = [dict(u) for u in (usages or [])]
        self.llamadas: list[dict] = []

    def __call__(self, url, payload, *resto):
        usage = resto[-1] if resto else None
        self.llamadas.append(payload)
        i = len(self.llamadas) - 1
        trozos = self.guiones[min(i, len(self.guiones) - 1)]
        extra = self.usages[min(i, len(self.usages) - 1)] if self.usages else {}

        def _gen():
            for t in trozos:
                yield t
            if isinstance(usage, dict):
                usage["prompt_tokens"] = 10
                usage["completion_tokens"] = len(trozos)
                usage.update(extra)
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


PLAZO = 60       # segundos que un turno del harness puede tardar en dar sus `done`
DRENAJE = 0.25   # segundos que se sigue escuchando tras el ultimo `done`


def lo_que_siga(ws, plazo):
    """Lo que el server mande en los proximos `plazo` segundos, o nada.

    En un hilo demonio con `join(plazo)` (el molde de `_cierre_del_ws`,
    test_sesiones_server.py) porque `receive_json` del TestClient no acepta
    timeout: esperar de frente un evento que NO tiene que llegar colgaria la
    suite entera en vez de dejar pasar al test. El hilo muere cuando el
    socket cierra al salir del `with`."""
    extra: list[dict] = []

    def _leer():
        try:
            while True:
                extra.append(ws.receive_json())
        except BaseException:
            pass

    hilo = threading.Thread(target=_leer, daemon=True)
    hilo.start()
    hilo.join(plazo)
    return list(extra)


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
        `done` numero `hasta_dones` (2 cuando un steer encola otro turno), mas
        lo que siga durante `DRENAJE`: asi "un solo done" es una asercion de
        verdad y no una que solo podria fallar colgandose (un duplicado
        saldria del mismo camino microsegundos despues del primero)."""
        with self.cliente.websocket_connect("/ws/chat") as ws:
            ws.send_text(self.paquete(texto, departamento))
            eventos = self.recibir(ws, hasta_dones)
            eventos.extend(lo_que_siga(ws, DRENAJE))
            return eventos

    @staticmethod
    def recibir(ws, hasta_dones=1, plazo=PLAZO):
        """Todo lo que llega hasta el `done` numero `hasta_dones`. Con plazo:
        un `done` que no llega es un rojo con lo que SI llego, no un cuelgue
        de la suite (hilo demonio + join, como `lo_que_siga`)."""
        eventos, dones, error = [], 0, []

        def _leer():
            nonlocal dones
            try:
                while dones < hasta_dones:
                    ev = ws.receive_json()
                    eventos.append(ev)
                    if ev.get("type") == "done":
                        dones += 1
            except BaseException as e:      # el socket cerro: que lo vea el test
                error.append(e)

        hilo = threading.Thread(target=_leer, daemon=True)
        hilo.start()
        hilo.join(plazo)
        if hilo.is_alive():
            raise AssertionError(
                f"en {plazo} s llegaron {dones} de {hasta_dones} done: "
                f"{[e.get('type') for e in eventos]}")
        if error:
            raise error[0]
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
                        lambda user_msg, runtime, features=None: [("Sistema", "SISTEMA BASE")])
    monkeypatch.setattr(srv, "_harness_context", lambda *a, **k: "estado")
    monkeypatch.setattr(srv, "_extract_edit_target", lambda *a, **k: None)
    # el tokenizador del modelo local NO se carga en el harness: el fallback
    # local del turno (`model = _route_model_name("local")` = qwen2.5:7b)
    # leeria el header del GGUF real de ~/.ollama y escribiria 11 MB bajo el
    # home temporal; con `cargar` -> None el contador es el fallback de 3.3
    # en todas las rutas y los numeros de ventana son deterministas
    monkeypatch.setattr(srv.tokenizador, "cargar", lambda nombre: None)
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


class _SocketMudo:
    """Manda de todo menos el `done`, hasta que se lo para."""

    def __init__(self):
        self.parar = threading.Event()

    def receive_json(self):
        if self.parar.wait(0.02):
            raise RuntimeError("cerrado")
        return {"type": "chunk", "text": "..."}


def test_el_harness_no_se_cuelga_si_falta_el_done():
    """Un `done` de menos tiene que ser un rojo con mensaje (que dice que
    llego), no un cuelgue del ritual de merge."""
    ws = _SocketMudo()
    try:
        with pytest.raises(AssertionError, match="0 de 1 done"):
            Harness.recibir(ws, hasta_dones=1, plazo=0.3)
    finally:
        ws.parar.set()


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


def _sembrar_chat_viejo(textos):
    """Otra conversacion, mas vieja, que la fuente `chats` puede pescar."""
    viejo = chats.create(str(srv.ROOT), "lecturas")
    for t in textos:
        chats.append(viejo["id"], "user", t)
    return viejo["id"]


def test_una_marca_valida_corta_pesca_y_la_continuacion_sigue_en_la_misma_burbuja(chat):
    _sembrar_chat_viejo(["empece El nombre de la rosa, es un libro alucinante"])
    # historial previo del MISMO chat: la reentrada tiene que llevarlo, y
    # sin el parcial (que todavia no se persistio); con un chat vacio la
    # asercion del historial seria vacua
    chats.append(chat.chat_id, "user", "hola")
    chats.append(chat.chat_id, "assistant", "hola Pedro")
    chat.modelo.guiones = [["Dejame ver ", "⟦abismo:chats libro⟧", " esto no se ve"],
                           ["y sigo ", "con contexto"]]
    eventos = chat.turno("que libro lei")
    tipos = [e["type"] for e in eventos]
    # la senal, con cierre
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "pescado"]
    assert abismo[0]["fuente"] == "chats" and abismo[0]["verbo"] == "buscando en tus chats"
    assert abismo[1]["tamano"] > 0 and abismo[1]["viaje"] == {"destino": "local"}
    # la marca no llega a Pedro, lo posterior a la marca se descarta y la
    # continuacion sigue sin cerrar la burbuja: un solo thinking, un solo done
    assert texto_visible(eventos) == "Dejame ver y sigo con contexto"
    assert tipos.count("done") == 1 and tipos.count("thinking") == 1
    assert tipos.index("abismo") > tipos.index("thinking")
    # dos invocaciones al modelo: la reentrada lleva el bloque como append del
    # system base, el "venias diciendo" en el mensaje, num_ctx fijado y el
    # historial SIN el parcial (que todavia no se persistio)
    assert len(chat.modelo.llamadas) == 2
    primera, segunda = chat.modelo.llamadas
    assert segunda["options"]["num_ctx"] == srv.CHAT_NUM_CTX
    system2 = segunda["messages"][0]["content"]
    assert system2.startswith(primera["messages"][0]["content"])
    assert "=== Lo que subio del abismo (fuente: chats) ===" in system2
    assert "El nombre de la rosa" in system2
    usuario2 = segunda["messages"][-1]["content"]
    assert usuario2.startswith("que libro lei")
    assert "Venias diciendo: Dejame ver " in usuario2
    # el historial normal viaja (`_history_messages` descarta solo el ultimo
    # mensaje, el de Pedro) y el parcial NO va como mensaje assistant: su
    # unica via es el "venias diciendo"
    assert segunda["messages"][1:3] == [{"role": "user", "content": "hola"},
                                        {"role": "assistant", "content": "hola Pedro"}]
    assert "Dejame ver" not in json.dumps(segunda["messages"][:-1])
    # persistencia fusionada: un solo par user/assistant nuevo, ya filtrado,
    # sin marca ni bloque; la memoria recuerda una sola vez
    assert [(m["role"], m["text"]) for m in chat.mensajes()] == [
        ("user", "hola"), ("assistant", "hola Pedro"),
        ("user", "que libro lei"), ("assistant", "Dejame ver y sigo con contexto")]
    crudo = (chat.tmp / "chats.json").read_text(encoding="utf-8")
    assert "⟦" not in crudo and "Lo que subio" not in crudo
    assert len(chat.memoria.recordado) == 1 and "⟦" not in chat.memoria.recordado[0]
    filas = chat.telemetria("abismo")
    assert [f["evento"] for f in filas] == ["consulta"]
    assert filas[0]["resultado"] == "pescado" and filas[0]["destino"] == "local"


def test_la_fuente_chats_no_pesca_la_pregunta_ni_lo_que_el_modelo_ya_tiene(chat):
    """La sonda T1 del cierre (h04): con un chat activo largo que comparte la
    palabra buscada, el bloque eran la propia pregunta mas los mensajes
    recientes que el modelo YA tiene en `messages`, y el chat viejo quedaba
    afuera del tope de 8. Lo que esta en la ventana del historial no se
    pesca; lo anterior a la ventana del MISMO chat, si."""
    _sembrar_chat_viejo(["empece El nombre de la rosa, un libro alucinante"])
    for i in range(3):
        chats.append(chat.chat_id, "user", f"mensaje viejo {i} del libro de siempre")
    for i in range(12):
        chats.append(chat.chat_id, "user" if i % 2 == 0 else "assistant",
                     f"mensaje reciente {i} sobre el libro de siempre")
    chat.modelo.guiones = [["a ⟦abismo:chats libro⟧"], ["b"]]
    eventos = chat.turno("que libro lei")
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "pescado"]
    system2 = chat.modelo.llamadas[1]["messages"][0]["content"]
    bloque = system2[system2.index("=== Lo que subio del abismo"):]
    assert "El nombre de la rosa" in bloque
    assert "mensaje viejo" in bloque
    assert "que libro lei" not in bloque and "reciente" not in bloque
    # la ventana del historial es exactamente la que viaja en messages
    historial = [m["content"] for m in chat.modelo.llamadas[1]["messages"][1:-1]]
    assert len(historial) == srv._HISTORY_TURNS and all("reciente" in h for h in historial)


def test_la_pasada_sintetica_no_repite_nada_del_turno(chat, monkeypatch):
    """Los catorce salteos del spec, medidos: meta, cost, chat/updated,
    thinking y done salen una vez; el pulso abre y cierra un solo escritorio;
    chat_turn se escribe una vez y cuenta la consulta; y los cuatro que el
    fixture patchea sin contar (_decide, goals.detect, _sistema_del_turno,
    _cobrar_turno) corren UNA vez: si una regresion los moviera adentro del
    bucle exterior, esto lo ve (todos se resuelven como globales del modulo
    en el momento de la llamada, asi que el monkeypatch alcanza)."""
    llamadas = {"decide": 0, "goals": 0, "system": 0, "cobro": 0}

    def decide(*a, **k):
        llamadas["decide"] += 1
        return _decide_local(*a, **k)
    monkeypatch.setattr(srv, "_decide", decide)
    monkeypatch.setattr(srv.goals, "detect",
                        lambda texto: llamadas.__setitem__("goals", llamadas["goals"] + 1))
    sistema_real = srv._sistema_del_turno

    def sistema(*a, **k):
        llamadas["system"] += 1
        return sistema_real(*a, **k)
    monkeypatch.setattr(srv, "_sistema_del_turno", sistema)
    cobrar_real = srv._cobrar_turno

    def cobrar(*a, **k):
        llamadas["cobro"] += 1
        return cobrar_real(*a, **k)
    monkeypatch.setattr(srv, "_cobrar_turno", cobrar)
    _sembrar_chat_viejo(["un libro"])
    chat.modelo.guiones = [["a ⟦abismo:chats libro⟧"], ["b"]]
    eventos = chat.turno("libro")
    tipos = [e["type"] for e in eventos]
    for tipo in ("thinking", "meta", "cost", "done"):
        assert tipos.count(tipo) == 1, tipo
    assert len([e for e in eventos if e["type"] == "chat" and e.get("action") == "updated"]) == 1
    pulso = [e["evento"] for e in chat.pulso.desde(0)[1]]
    assert pulso.count("inicio") == 1 and pulso.count("fin") == 1
    turnos = chat.telemetria("chat_turn")
    assert len(turnos) == 1 and turnos[0]["abismo_consultas"] == 1
    assert llamadas == {"decide": 1, "goals": 1, "system": 1, "cobro": 1}


def test_el_tope_de_tres_consultas_por_turno(chat):
    _sembrar_chat_viejo(["un libro"])
    chat.modelo.guiones = [["a ⟦abismo:chats libro⟧"], ["b ⟦abismo:chats libro⟧"],
                           ["c ⟦abismo:chats libro⟧"], ["d ⟦abismo:chats libro⟧ e"]]
    eventos = chat.turno("libros")
    fases = [a["fase"] for a in de_tipo(eventos, "abismo")]
    assert fases == ["pondering", "pescado"] * 3
    # la cuarta marca no corta: se retira con aviso y el texto posterior vale
    assert texto_visible(eventos) == "a b c d  e"
    assert len(chat.modelo.llamadas) == 4
    retiradas = [f for f in chat.telemetria("abismo") if f["evento"] == "retirada"]
    assert [f["clase"] for f in retiradas] == ["sin_corte"]
    assert chat.telemetria("chat_turn")[0]["abismo_consultas"] == 3
    # invariante 8: un mensaje real de Pedro resetea el contador, y el turno
    # siguiente vuelve a poder consultar
    chat.modelo.guiones = [["z ⟦abismo:chats libro⟧"], ["w"]]
    chat.modelo.llamadas.clear()      # el espia elige el guion por el indice global
    eventos = chat.turno("otra vez")
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "pescado"]
    assert texto_visible(eventos) == "z w"
    assert chat.telemetria("chat_turn")[-1]["abismo_consultas"] == 1


def test_la_pesca_vacia_es_fallo_y_la_reentrada_sigue_sin_bloque(chat):
    chat.modelo.guiones = [["Dejame ver ", "⟦abismo:chats zzzz⟧ nada"], ["y sigo"]]
    eventos = chat.turno("hola")
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "fallo"]
    assert abismo[1]["motivo"] == "vacio"
    assert texto_visible(eventos) == "Dejame ver y sigo"
    assert len(chat.modelo.llamadas) == 2
    assert "Lo que subio" not in chat.modelo.llamadas[1]["messages"][0]["content"]
    assert "Venias diciendo: Dejame ver " in chat.modelo.llamadas[1]["messages"][-1]["content"]


def test_una_consulta_que_revienta_degrada_a_seguir_sin_contexto(chat, monkeypatch):
    def bomba(m, **kw):
        raise RuntimeError("chroma caido")
    monkeypatch.setattr(srv.abismo_consulta, "resolver", bomba)
    chat.modelo.guiones = [["a ⟦abismo:memoria que leo⟧"], ["b"]]
    eventos = chat.turno("hola")
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "fallo"]
    assert abismo[1]["motivo"] == "error"
    assert texto_visible(eventos) == "a b"
    assert [e["type"] for e in eventos].count("done") == 1
    assert chat.telemetria("abismo")[0]["motivo"] == "error"


def test_una_marca_ilegible_se_retira_sin_cortar(chat):
    chat.modelo.guiones = [["hola ⟦abismo:memorai que dije⟧ sigo"]]
    eventos = chat.turno("hola")
    assert texto_visible(eventos) == "hola  sigo"
    assert de_tipo(eventos, "abismo") == [] and len(chat.modelo.llamadas) == 1
    assert [f["clase"] for f in chat.telemetria("abismo")] == ["ilegible"]


def test_un_empalme_que_arma_una_marca_valida_no_llega_a_pedro_ni_a_disco(chat):
    """La sonda I del cierre: el filtro retiraba la ilegible de adentro y
    dejaba salir la marca valida que el empalme armaba, visible y persistida
    en chats.json. Ahora el filtro relee hasta punto fijo: la marca armada
    corta y consulta como cualquiera."""
    _sembrar_chat_viejo(["un libro"])
    chat.modelo.guiones = [["a ⟦abismo:chats ⟦abismo:zzz nada⟧ libro⟧ b"], ["z"]]
    eventos = chat.turno("libro")
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "pescado"]
    assert texto_visible(eventos) == "a z"
    assert "⟦" not in (chat.tmp / "chats.json").read_text(encoding="utf-8")
    assert [f["clase"] for f in chat.telemetria("abismo") if f["evento"] == "retirada"] == ["ilegible"]


def test_una_marca_abierta_al_fin_del_stream_no_se_vuelca(chat):
    chat.modelo.guiones = [["termino asi ", "⟦abismo:chats sin cie"]]
    eventos = chat.turno("hola")
    assert texto_visible(eventos) == "termino asi "
    assert chat.mensajes()[-1]["text"] == "termino asi"
    assert [f["clase"] for f in chat.telemetria("abismo")] == ["abierta"]


def test_la_zona_y_el_consolidado_los_pone_el_server(chat, monkeypatch):
    """La frontera del consolidado del libro personal (spec seccion 6): solo
    llega a la fuente en un chat de zona personal, y la zona sale del prefijo
    de la cuenta del edificio tocado. Sin edificio: fabrica."""
    eco = chat.tmp / ".calipso" / "economia"
    eco.mkdir(parents=True)
    (eco / "personal.jsonl").write_text(json.dumps({
        "ts": "2026-09-01T10:00:00", "semana": "2026-W36", "tipo": "ingreso",
        "monto_mm": 1000, "categoria": "sueldo", "nota": ""}) + "\n", encoding="utf-8")
    visto = []

    def espia(m, **kw):
        visto.append((kw["zona_chat"], kw["consolidado"]))
        return {"estado": "fallo", "fuente": m.fuente, "texto": "", "bloques": [],
                "aviso": "la consulta no trajo nada"}
    monkeypatch.setattr(srv.abismo_consulta, "resolver", espia)
    for dep in ("personal:finanzas", "dep:atlas", None):
        chat.modelo.guiones = [["a ⟦abismo:memoria plata⟧"], ["b"]]
        chat.modelo.llamadas.clear()      # el espia elige el guion por el indice global
        chat.turno("hola", departamento=dep)
    assert visto == [("personal", "ingresos 1000 mm, gastos 0 mm, neto 1000 mm"),
                     ("fabrica", None), ("fabrica", None)]


def test_el_steer_de_pedro_gana_durante_la_pesca(chat, monkeypatch):
    """La carrera del spec (seccion 10): un steer que llega mientras se pesca
    aborta la consulta (sin reentrada, aviso en telemetry) y se procesa como
    hoy: es el turno siguiente. El steer viaja como texto crudo, como lo manda
    `planSend` de la PWA (el steer JSON de `send()` es una rareza previa que
    este plan no toca)."""
    visto, liberar = threading.Event(), threading.Event()

    def pesca_lenta(m, **kw):
        visto.set()
        liberar.wait(10)
        return {"estado": "pescado", "fuente": m.fuente, "texto": "=== bloque ===",
                "bloques": [("un bloque", 2)], "aviso": ""}
    monkeypatch.setattr(srv.abismo_consulta, "resolver", pesca_lenta)
    chat.modelo.guiones = [["Dejame ver ", "⟦abismo:chats libro⟧"], ["respuesta al steer"]]
    with chat.cliente.websocket_connect("/ws/chat") as ws:
        ws.send_text(chat.paquete("que libro lei"))
        assert visto.wait(10), "la pesca no arranco"
        ws.send_text("otra cosa")
        time.sleep(0.5)          # que el receptor lo deje en el inbox antes de soltar la pesca
        liberar.set()
        eventos = chat.recibir(ws, hasta_dones=2)
    tipos = [e["type"] for e in eventos]
    assert "steered" in tipos and tipos.count("done") == 2
    # la senal cerro en `fallo` (spec seccion 10: bloque descartado, fase
    # fallo, aviso): la pesca termino en su hilo, `_pescar_abismo` vio el
    # steer en el inbox y no dio `pescado`; MOTIVOS es cerrada, el motivo
    # de la senal es `error` y el de telemetry, `abortada_por_steer`
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "fallo"]
    assert de_tipo(eventos, "abismo")[1]["motivo"] == "error"
    assert tipos.index("steered") > tipos.index("abismo")
    # la consulta se aborto: sin reentrada; el steer fue el turno siguiente
    assert len(chat.modelo.llamadas) == 2
    assert chat.modelo.llamadas[1]["messages"][-1]["content"] == "otra cosa"
    assert "Venias diciendo" not in json.dumps(chat.modelo.llamadas)
    filas = chat.telemetria("abismo")
    assert [f["evento"] for f in filas] == ["consulta", "abortada_por_steer"]
    assert filas[0]["motivo"] == "abortada_por_steer" and filas[1]["momento"] == "pesca"
    roles = [(m["role"], m["text"].split(" ")[0]) for m in chat.mensajes()]
    assert roles == [("user", "que"), ("assistant", "Dejame"), ("user", "otra"), ("assistant", "respuesta")]


def _pausar_el_modelo(chat, monkeypatch, invocacion, trozo):
    """Frena al modelo espia justo ANTES de entregar el trozo numero `trozo`
    de la invocacion numero `invocacion` (los dos 1-based). Asi el test mete
    un steer con el stream abierto y en un momento elegido, sin carreras: se
    espera `arranco`, se manda el steer, se suelta `liberar`. Devuelve
    (arranco, liberar)."""
    arranco, liberar = threading.Event(), threading.Event()
    espia = chat.modelo

    def pausado(url, payload, *resto):
        gen = espia(url, payload, *resto)
        if len(espia.llamadas) != invocacion:
            return gen

        def _pausado():
            for i, t in enumerate(gen):
                if i == trozo - 1:
                    arranco.set()
                    liberar.wait(10)
                yield t
        return _pausado()
    monkeypatch.setattr(srv.dispatch, "_ollama_chat_chunks", pausado)
    return arranco, liberar


def test_el_steer_que_llega_con_el_corte_no_llega_a_pescar(chat, monkeypatch):
    """El steer de Pedro gana ANTES del pondering (spec seccion 10): si ya
    estaba en la cola cuando la marca corto el stream, no hay consulta, no
    hay senal que cerrar y no se abre un stream nuevo para cerrarlo
    enseguida. Queda la fila de aviso, con el contador todavia en cero."""
    _sembrar_chat_viejo(["un libro"])
    chat.modelo.guiones = [["a ", "⟦abismo:chats libro⟧"], ["no deberia correr"]]
    arranco, liberar = _pausar_el_modelo(chat, monkeypatch, invocacion=1, trozo=2)
    with chat.cliente.websocket_connect("/ws/chat") as ws:
        ws.send_text(chat.paquete("que libro lei"))
        assert arranco.wait(10), "el modelo no arranco"
        ws.send_text("otra cosa")
        time.sleep(0.5)      # que el receptor lo deje en el inbox antes de soltar
        liberar.set()
        eventos = chat.recibir(ws, hasta_dones=2)
    assert de_tipo(eventos, "abismo") == []      # ni pondering ni cierre
    assert "steered" in [e["type"] for e in eventos]
    # dos invocaciones: la cortada y la del steer, ninguna reentrada
    assert len(chat.modelo.llamadas) == 2
    assert chat.modelo.llamadas[1]["messages"][-1]["content"] == "otra cosa"
    filas = chat.telemetria("abismo")
    assert [(f["evento"], f["momento"], f["consultas"]) for f in filas] == [
        ("abortada_por_steer", "pesca", 0)]
    assert chat.telemetria("chat_turn")[0]["abismo_consultas"] == 0


def test_el_steer_durante_el_stream_de_la_reentrada_deja_su_aviso(chat, monkeypatch):
    """El cuarto momento del steer (spec seccion 10, "idem"): la consulta ya
    se pesco y la pasada sintetica esta streameando. Corta como cualquier
    barge-in -mismo `steered`, mismo "(interrumpido)"- y suma la fila de
    aviso con `momento="reentrada"`, que es lo que la distingue del steer de
    un turno normal."""
    _sembrar_chat_viejo(["un libro"])
    chat.modelo.guiones = [["a ⟦abismo:chats libro⟧"], ["sigo ", "y termino"]]
    arranco, liberar = _pausar_el_modelo(chat, monkeypatch, invocacion=2, trozo=2)
    with chat.cliente.websocket_connect("/ws/chat") as ws:
        ws.send_text(chat.paquete("que libro lei"))
        assert arranco.wait(10), "la reentrada no arranco"
        ws.send_text("otra cosa")
        time.sleep(0.5)
        liberar.set()
        eventos = chat.recibir(ws, hasta_dones=2)
    # la consulta si se hizo y cerro bien: el steer llego despues
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "pescado"]
    assert "steered" in [e["type"] for e in eventos]
    avisos = [f for f in chat.telemetria("abismo") if f["evento"] == "abortada_por_steer"]
    assert [(f["momento"], f["consultas"]) for f in avisos] == [("reentrada", 1)]
    # el turno se persiste fusionado hasta donde llego, con el aviso del steer
    assert chat.mensajes()[1]["text"].startswith("a sigo y termino")
    assert chat.telemetria("chat_turn")[0]["abismo_consultas"] == 1


def test_la_ruta_orquestador_retira_la_marca_sin_cortar_y_emite_el_texto_entero(chat, monkeypatch):
    """Guarda del `apagada = True` del orquestador (ledger T6, must-fix del
    cierre): si faltara, una marca valida en la sintesis dejaria el filtro
    cortado con una marca que nadie consume y el resto se truncaria mudo."""
    monkeypatch.setattr(srv, "_should_orchestrate", lambda *a, **k: True)

    async def equipo(ws, inbox, chat_msg, features, system, verdict, **kw):
        return "sintesis ⟦abismo:chats libro⟧ entera", None, None
    monkeypatch.setattr(srv, "_run_dynamic_team", equipo)
    _sembrar_chat_viejo(["un libro"])
    eventos = chat.turno("libro")
    assert texto_visible(eventos) == "sintesis  entera"
    assert de_tipo(eventos, "abismo") == [] and chat.modelo.llamadas == []
    assert [e["type"] for e in eventos].count("done") == 1
    assert de_tipo(eventos, "cost")[0]["route"] == "orchestrator"
    assert [f["clase"] for f in chat.telemetria("abismo")] == ["sin_corte"]
    assert chat.mensajes()[-1]["text"] == "sintesis  entera"
    assert "⟦" not in (chat.tmp / "chats.json").read_text(encoding="utf-8")


def test_el_fallback_local_tras_un_corte_retira_la_marca_sin_cortar(chat, monkeypatch):
    """Guarda del `apagada = True` del fallback local: la api corta en una
    marca, pesca, y la reentrada por api revienta; el local que la reemplaza
    emite otra marca valida, que se retira sin cortar y sin consultar (un
    turno que cayo al fallback no consulta). Texto entero, un done, un cobro."""
    _sembrar_chat_viejo(["un libro"])
    api = ModeloEspia([["a ⟦abismo:chats libro⟧"]])

    def api_que_revienta_en_la_reentrada(url, payload, *resto):
        if api.llamadas:
            raise RuntimeError("litellm se cayo")
        return api(url, payload, *resto)
    monkeypatch.setattr(srv.dispatch, "_sse_text_chunks", api_que_revienta_en_la_reentrada)
    chat.modelo.guiones = [["fallback ⟦abismo:chats libro⟧ entero"]]
    eventos = chat.turno("/api libro")
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "pescado"]
    assert texto_visible(eventos) == "a fallback  entero"
    assert [m.get("note") for m in de_tipo(eventos, "meta")] == [None, "fallback a local"]
    assert [e["type"] for e in eventos].count("done") == 1
    assert len(api.llamadas) == 1 and len(chat.modelo.llamadas) == 1
    retiradas = [f["clase"] for f in chat.telemetria("abismo") if f["evento"] == "retirada"]
    assert retiradas == ["sin_corte"]
    turno = chat.telemetria("chat_turn")[0]
    assert [(f["from"], f["to"]) for f in turno["fallbacks"]] == [("api", "local")]
    assert chat.mensajes()[-1]["text"] == "a fallback  entero"


def test_la_senal_del_abismo_se_publica_al_pulso(chat):
    _sembrar_chat_viejo(["un libro"])
    chat.modelo.guiones = [["a ⟦abismo:chats libro⟧"], ["b"]]
    chat.turno("libro", departamento="dep:atlas")
    cursor, flujo = chat.pulso.desde(0)
    eventos = [e for e in flujo if e["evento"] == "abismo"]
    assert [(e["fase"], e["fuente"]) for e in eventos] == [("pondering", "chats"), ("pescado", "chats")]
    assert all(e["agente_id"].startswith("chat:") and e["departamento"] == "dep:atlas" for e in eventos)
    # al pulso va el tamano, jamas el bloque (invariante 2): el flujo se
    # replica a todo cliente del mapa
    assert eventos[1]["tamano"] > 0
    assert set(eventos[1]) == {"seq", "ts", "agente_id", "evento", "departamento",
                               "trabajo", "rol", "modelo", "fase", "fuente", "tamano"}
    # y el pondering del pulso tambien CIERRA cuando la pesca falla
    # (invariante 4): el escritorio del mapa no se queda pescando para siempre
    chat.modelo.guiones = [["a ⟦abismo:chats zzzz⟧"], ["b"]]
    chat.modelo.llamadas.clear()      # el espia elige el guion por el indice global
    chat.turno("otra vez", departamento="dep:atlas")
    fallidos = [e for e in chat.pulso.desde(cursor)[1] if e["evento"] == "abismo"]
    assert [(e["fase"], e.get("motivo")) for e in fallidos] == [
        ("pondering", None), ("fallo", "vacio")]


# --- la procedencia del episodio (spec 2026-09-11, seccion 2) ---------------

def test_el_episodio_del_chat_lleva_la_pregunta_limpia_y_la_procedencia(chat):
    """Lo que se guarda: el par con `chat_msg` (sin el gesto) y los metadatos
    de quien contesto de verdad."""
    chat.turno("/local hola")
    assert len(chat.memoria.guardados) == 1
    texto, scope, meta = chat.memoria.guardados[0]
    assert texto == "Pedro pregunto: hola\nCalipso respondio: hola Pedro"
    assert scope == "global"
    assert meta == {"route": "local", "kind": "chat", "ruta": "local",
                    "modelo": "modelo-falso", "chat": chat.chat_id, "procedencia": 1,
                    "degeneracion": 0, "sin_anclaje": 0}


def test_tras_un_fallback_la_ruta_guardada_es_la_usada_y_route_la_decidida(chat, monkeypatch):
    def api_que_revienta(url, payload, *resto):
        raise RuntimeError("litellm se cayo")
    monkeypatch.setattr(srv.dispatch, "_sse_text_chunks", api_que_revienta)
    chat.modelo.guiones = [["desde local"]]
    eventos = chat.turno("/api libro")
    assert [m.get("note") for m in de_tipo(eventos, "meta")] == [None, "fallback a local"]
    texto, scope, meta = chat.memoria.guardados[0]
    assert texto.startswith("Pedro pregunto: libro\n")
    assert (meta["route"], meta["ruta"]) == ("api", "local")
    assert meta["modelo"] == srv._route_model_name("local")
    assert meta["chat"] == chat.chat_id and meta["procedencia"] == 1


def test_con_el_orquestador_la_ruta_guardada_es_orchestrator(chat, monkeypatch):
    monkeypatch.setattr(srv, "_should_orchestrate", lambda *a, **k: True)

    async def equipo(ws, inbox, chat_msg, features, system, verdict, **kw):
        return "sintesis entera", None, None
    monkeypatch.setattr(srv, "_run_dynamic_team", equipo)
    chat.turno("libro")
    texto, scope, meta = chat.memoria.guardados[0]
    assert texto == "Pedro pregunto: libro\nCalipso respondio: sintesis entera"
    assert (meta["route"], meta["ruta"]) == ("local", "orchestrator")


# --- los canarios (spec 2026-09-11): el cableado del turno ------------------

def test_la_senal_canario_llega_antes_del_done_y_el_veredicto_va_a_meta_fila_y_remember(chat):
    eventos = chat.turno("que libro te conte que empece?")
    tipos = [e["type"] for e in eventos]
    canario = de_tipo(eventos, "canario")
    assert len(canario) == 1 and tipos.index("canario") < tipos.index("done")
    assert tipos.index("canario") > tipos.index("cost")
    v = canario[0]
    assert v["anclaje"]["aplica"] is True and v["anclaje"]["aplica_por"] == ["senal:te conte"]
    assert v["anclaje"]["sin_anclaje"] == [] and v["anclaje"]["tapado"] is False
    assert v["degeneracion"] == []
    assert [f["pasada"] for f in v["ventana"]] == [1]
    # el mismo dict en la fila chat_turn y en el meta del mensaje
    fila = chat.telemetria("chat_turn")[0]["canarios"]
    assert fila["anclaje"] == v["anclaje"] and fila["ventana"] == v["ventana"]
    meta = chat.mensajes()[-1]["meta"]
    assert meta["canarios"]["anclaje"]["aplica_por"] == ["senal:te conte"]
    assert meta["route"] == "local"       # lo de antes sigue
    # y los dos numeros en el remember
    _, _, meta_mem = chat.memoria.guardados[0]
    assert (meta_mem["degeneracion"], meta_mem["sin_anclaje"]) == (0, 0)


def test_un_invento_con_senal_en_la_pregunta_sale_sin_anclaje_y_una_accion_sin_accion_tambien(chat):
    chat.modelo.guiones = [["Recuerdo que te conte sobre una trilogia de ciencia ficcion ",
                            "ambientada en un futuro distopico. Consultando los recuerdos de Pedro..."]]
    eventos = chat.turno("que libro te conte que empece?")
    a = de_tipo(eventos, "canario")[0]["anclaje"]
    assert [s["tipo"] for s in a["sin_anclaje"]] == ["recuerdo", "accion"]
    assert a["sin_anclaje"][1]["accion"] == "consulto"
    _, _, meta_mem = chat.memoria.guardados[0]
    assert meta_mem["sin_anclaje"] == 2 and meta_mem["degeneracion"] == 0
    # en un turno sin senal ni consulta la medicion corre igual pero no
    # aplica; y la misma trilogia ahora ANCLA en el historial de Calipso
    # (el turno anterior la dijo): eso es `anclado_solo_en_calipso`, h07
    chat.modelo.llamadas.clear()
    eventos = chat.turno("explicame que es un websocket")
    a = de_tipo(eventos, "canario")[0]["anclaje"]
    assert a["aplica"] is False and a["aplica_por"] == []
    assert [s["tipo"] for s in a["sin_anclaje"]] == ["accion"]
    assert a["anclado_solo_en_calipso"] == 1
    assert [h["fuentes"] for h in a["hechos"] if h["tipo"] == "recuerdo"] == [["historial_calipso"]]


def test_una_salida_rota_reinyectada_da_senales_de_degeneracion(chat):
    chat.modelo.guiones = [["Segui exactamente desde ahi, sin repetir."]]
    eventos = chat.turno("hola")
    senales = [s["senal"] for s in de_tipo(eventos, "canario")[0]["degeneracion"]]
    assert senales == ["fuga_de_reentrada"]
    _, _, meta_mem = chat.memoria.guardados[0]
    assert meta_mem["degeneracion"] == 1
    assert chat.telemetria("chat_turn")[0]["canarios"]["degeneracion"][0]["senal"] == "fuga_de_reentrada"


def test_la_ventana_se_mide_por_pasada_con_evaluado_y_truncado(chat):
    """Dos pasadas: la primera se corta en la marca ANTES del done (el
    generador se cierra: usage_pasada queda vacio, `evaluado` None y
    `sin medicion`, no 0); la segunda llega al done con un
    prompt_eval_count al borde del techo y done_reason=length."""
    _sembrar_chat_viejo(["un libro"])
    chat.modelo.guiones = [["a ⟦abismo:chats libro⟧"], ["b"]]
    chat.modelo.usages = [{}, {"prompt_tokens": 7900, "done_reason": "length"}]
    eventos = chat.turno("libro")
    v = de_tipo(eventos, "canario")[0]
    assert [f["pasada"] for f in v["ventana"]] == [1, 2]
    p1, p2 = v["ventana"]
    assert p1["ruta"] == "local" and p1["num_ctx"] == srv.CHAT_NUM_CTX and p1["tokenizador"] == "fallback"
    assert p1["evaluado"] is None and p1["truncado"] == "sin medicion"
    assert p1["recorte"] == [] and p1["cabe"] is True
    assert p2["evaluado"] == 7900 and p2["truncado"] is True        # >= 0.95 * 8192
    assert p2["done_reason"] == "length" and p2["estimado"] > p1["estimado"]
    assert [s["senal"] for s in v["degeneracion"]] == ["cortada"]
    assert chat.telemetria("chat_turn")[0]["canarios"]["ventana"] == v["ventana"]


def test_un_evaluado_parecido_al_estimado_no_es_truncado(chat):
    chat.modelo.usages = [{"prompt_tokens": 700}]
    eventos = chat.turno("hola")
    fila = de_tipo(eventos, "canario")[0]["ventana"][0]
    assert fila["evaluado"] == 700 and fila["estimado"] < 700
    assert fila["truncado"] is False         # ni > num_ctx, ni >= 0.95 del techo, ni < 0.85 del estimado
    assert fila["done_reason"] is None       # el espia no lo escribe: None, nunca una cadena


def test_en_local_el_prompt_que_no_cabe_se_recorta_lo_volatil_y_se_anota(chat, monkeypatch):
    chats.append(chat.chat_id, "user", "hola")
    chats.append(chat.chat_id, "assistant", "hola Pedro")
    # con el fallback de 3.3: system 9 + 5, historial (2+5) + (4+5), mensaje 2 + 5, cierre 3 = 40
    monkeypatch.setattr(srv, "CHAT_NUM_CTX", 30)
    eventos = chat.turno("hola")
    fila = de_tipo(eventos, "canario")[0]["ventana"][0]
    assert fila["recorte"] == ["historial:2"] and fila["cabe"] is True and fila["no_cabe"] is False
    assert fila["estimado_sin_recorte"] > 30 >= fila["estimado"]
    # y el modelo NO vio el historial: lo que viajo es lo recortado
    assert [m["role"] for m in chat.modelo.llamadas[0]["messages"]] == ["system", "user"]
    assert chat.modelo.llamadas[0]["options"]["num_ctx"] == 30
    # el system base no se toco (invariante 8)
    assert chat.modelo.llamadas[0]["messages"][0]["content"] == "=== Sistema ===\nSISTEMA BASE"


def test_si_no_cabe_ni_recortando_se_manda_igual_y_se_marca(chat, monkeypatch):
    monkeypatch.setattr(srv, "CHAT_NUM_CTX", 5)
    eventos = chat.turno("hola")
    fila = de_tipo(eventos, "canario")[0]["ventana"][0]
    assert fila["no_cabe"] is True and fila["cabe"] is False and fila["recorte"] == []
    assert texto_visible(eventos) == "hola Pedro"          # se mando igual


def test_un_turno_steereado_no_es_cortada(chat, monkeypatch):
    arranco, liberar = _pausar_el_modelo(chat, monkeypatch, invocacion=1, trozo=2)
    chat.modelo.usages = [{"done_reason": "length"}]
    with chat.cliente.websocket_connect("/ws/chat") as ws:
        ws.send_text(chat.paquete("hola"))
        assert arranco.wait(5)
        ws.send_text(chat.paquete("otra"))
        liberar.set()
        eventos = chat.recibir(ws, hasta_dones=2)
    canarios = de_tipo(eventos, "canario")
    assert len(canarios) == 2
    assert "cortada" not in [s["senal"] for s in canarios[0]["degeneracion"]]
    assert canarios[0]["ventana"][0]["truncado"] == "sin medicion"


def test_fail_open_si_el_canario_revienta_el_turno_termina_y_la_fila_lo_dice(chat, monkeypatch):
    def bomba(**k):
        raise RuntimeError("canario roto")
    monkeypatch.setattr(srv.canarios, "veredicto", bomba)
    eventos = chat.turno("hola")
    tipos = [e["type"] for e in eventos]
    assert tipos.count("done") == 1 and tipos[-1] == "done"
    assert texto_visible(eventos) == "hola Pedro"
    v = de_tipo(eventos, "canario")[0]
    assert v["error"] == "RuntimeError" and v["anclaje"] is None
    assert chat.telemetria("chat_turn")[0]["canarios"]["error"] == "RuntimeError"
    # sin veredicto no hay numeros en el remember (None se descarta), y el
    # meta del mensaje lleva el fallo
    _, _, meta_mem = chat.memoria.guardados[0]
    assert meta_mem["degeneracion"] is None and meta_mem["sin_anclaje"] is None
    assert chat.mensajes()[-1]["meta"]["canarios"]["error"] == "RuntimeError"


def test_el_tope_de_tiempo_del_canario_no_frena_el_turno(chat, monkeypatch):
    monkeypatch.setattr(srv.canarios, "TOPE_SEGUNDOS", 0.05)

    def lento(**k):
        time.sleep(0.5)
        return {"anclaje": {}, "degeneracion": [], "ventana": []}
    monkeypatch.setattr(srv.canarios, "veredicto", lento)
    eventos = chat.turno("hola")
    assert [e["type"] for e in eventos][-1] == "done"
    assert de_tipo(eventos, "canario")[0]["error"] == "TimeoutError"


def test_el_canario_nunca_corre_en_el_event_loop(chat, monkeypatch):
    import asyncio
    visto = []

    def espia(**k):
        try:
            asyncio.get_running_loop()
            visto.append("loop")
        except RuntimeError:
            visto.append("hilo")
        return {"anclaje": {"sin_anclaje": []}, "degeneracion": [], "ventana": []}
    monkeypatch.setattr(srv.canarios, "veredicto", espia)
    chat.turno("hola")
    assert visto == ["hilo"]


def test_la_fila_lleva_el_contexto_solo_en_el_server_desechable(chat, monkeypatch):
    """CANARIOS_PERSISTIR_CONTEXTO=1 (el porton y el smoke): la fila chat_turn
    lleva el system, el historial y los bloques que viajaron; sin la
    variable (produccion), no (invariante 7)."""
    _sembrar_chat_viejo(["empece un libro: El nombre de la rosa"])
    chats.append(chat.chat_id, "user", "hola")
    chats.append(chat.chat_id, "assistant", "hola Pedro")
    chat.modelo.guiones = [["a ⟦abismo:chats libro⟧"], ["b"]]
    chat.turno("libro")
    assert "contexto" not in chat.telemetria("chat_turn")[0]
    monkeypatch.setenv("CANARIOS_PERSISTIR_CONTEXTO", "1")
    chat.modelo.llamadas.clear()
    chat.turno("libro otra vez")
    ctx = chat.telemetria("chat_turn")[1]["contexto"]
    assert ctx["secciones"][0] == ["Sistema", "SISTEMA BASE"]
    assert ctx["secciones"][-1][0] == "Lo que subio del abismo (fuente: chats)"
    assert "El nombre de la rosa" in ctx["bloques"][0]
    assert ctx["historial"][0] == {"role": "user", "content": "hola"}
