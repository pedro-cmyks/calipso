"""Lo que el server hace con la memoria por Ollama (spec 2026-09-12, secciones
2 y 5): `GET /api/memory` con `sin_reindexar`, `recall_ok` y
`ultimo_recall_fallo`; el arranque que anuncia los pendientes (una linea y una
fila); el turno con la memoria muerta, por el harness: contesta sin recuerdos,
con `done`, la fila `recall_fallo` y la fila `remember_fallo`; el remember del
turno DESPUES del `done` como tarea de fondo que el harness espera; y la
fuente `memoria` del abismo que cierra con `memoria_no_disponible`. La Memory
es real (EmbedFalsa) sobre un home temporal; Ollama no se toca."""
from __future__ import annotations

import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso import chats
from calipso import memoria_embed as me
from calipso import memory
from calipso.abismo import consulta, fuentes, marca
from calipso.abismo import turno as abismo_turno
from test_abismo_chat import MemoriaFalsa, chat, de_tipo, texto_visible  # noqa: F401

_BUILD_CONTEXT_REAL = srv._build_context     # antes de que el fixture `chat` lo doble

PAR = "Pedro pregunto: que libro lei\nCalipso respondio: El nombre de la rosa."


class _EmbedCaida(me.EmbedFalsa):
    def embed(self, textos, timeout=None):
        raise me.EmbedError("connection refused")


def _matar(m: memory.Memory) -> None:
    """La EF caida en la fachada Y en cada ambito: `Memory.recall` embebe con
    `Memory._embed`, pero `Scope.remember` (el remember de fondo del turno)
    embebe con el `_embed` que el Scope recibio en `__init__`; rebindear solo
    `m._embed` dejaria al remember con la EmbedFalsa sana. Es lo que pasa de
    verdad con Ollama caido: los dos comparten el objeto con la misma url."""
    caida = _EmbedCaida()
    m._embed = caida
    for s in m._scopes:
        s._embed = caida


def _sembrar_vieja(m: memory.Memory, n: int) -> None:
    """`n` episodios en la coleccion VIEJA `episodic` del ambito global (3
    dims, EF default de chroma persistida): lo que un home de MiniLM deja."""
    vieja = m.glob._client.get_or_create_collection("episodic", metadata={"hnsw:space": "cosine"})
    vieja.add(ids=[f"v{i}" for i in range(n)], documents=[PAR] * n,
              metadatas=[{"ts": f"2026-09-0{i + 1}T10:00:00", "kind": "chat"} for i in range(n)],
              embeddings=[[0.1 * (i + 1), 0.2, 0.3] for i in range(n)])


@pytest.fixture
def memoria_real(tmp_path, monkeypatch):
    """Una Memory real con EmbedFalsa sobre un home temporal, con un episodio
    en global, puesta como `srv.mem`. Va DESPUES de `chat` en la firma de los
    tests que usan el harness: pisa la MemoriaFalsa del fixture."""
    monkeypatch.setattr(memory, "CALIPSO_HOME", tmp_path / "home")
    m = memory.Memory(project_root=str(tmp_path / "repo"))
    m.remember(PAR, scope="global", kind="chat", procedencia=1)
    monkeypatch.setattr(srv, "mem", m)
    return m


# --- GET /api/memory y el arranque ------------------------------------------------

def test_api_memory_trae_sin_reindexar_recall_ok_y_el_ultimo_fallo(memoria_real):
    _sembrar_vieja(memoria_real, 2)
    assert memoria_real.sin_reindexar() == {"global": 2, "project": 0}
    assert memoria_real.glob.sin_reindexar() == 2
    cliente = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})
    r = cliente.get("/api/memory").json()
    assert r["global_episodes"] == 1 and r["project_episodes"] == 0
    assert r["sin_reindexar"] == {"global": 2, "project": 0}
    assert r["recall_ok"] is True and r["ultimo_recall_fallo"] is None
    _matar(memoria_real)
    assert memoria_real.recall("q") == []
    r = cliente.get("/api/memory").json()
    assert r["recall_ok"] is False
    assert r["ultimo_recall_fallo"]["error"] == "connection refused" and r["ultimo_recall_fallo"]["ts"]


def test_el_arranque_anuncia_sin_reindexar_una_linea_y_una_fila_por_ambito(memoria_real, monkeypatch, capsys):
    filas = []
    monkeypatch.setattr(srv.telemetry, "log_event", lambda kind, **k: filas.append({"kind": kind, **k}))
    srv._anunciar_memoria()
    assert capsys.readouterr().out == "" and filas == []          # nada pendiente: silencio
    _sembrar_vieja(memoria_real, 3)
    srv._anunciar_memoria()
    salida = capsys.readouterr().out
    assert "[calipso] memoria: 3 episodios sin reindexar en global" in salida
    assert "memoria_reindex --embeddings" in salida and "project" not in salida
    assert filas == [{"kind": "memoria", "accion": "sin_reindexar", "ambito": "global", "n": 3}]


def test_startup_warm_anuncia_la_memoria_en_hilo_sin_romper_el_orden(monkeypatch):
    llamadas = []
    monkeypatch.setattr(srv.discovery, "discover", lambda register=True: {"added": [], "local": [], "api": []})
    monkeypatch.setattr(srv, "_calentar_probes", lambda: llamadas.append("_calentar_probes") or {})

    def anunciar():
        try:
            asyncio.get_running_loop()
            llamadas.append("_anunciar_memoria EN EL LOOP")
        except RuntimeError:
            llamadas.append("_anunciar_memoria")
    monkeypatch.setattr(srv, "_anunciar_memoria", anunciar)
    for nombre in ("_asegurar_rutina_catastro", "_asegurar_rutina_cierre", "_asegurar_rutina_consumo"):
        monkeypatch.setattr(srv, nombre, lambda n=nombre: llamadas.append(n))

    async def _nada():
        return None
    monkeypatch.setattr(srv, "_routines_ticker", lambda: llamadas.append("_routines_ticker") or _nada())
    asyncio.run(srv._startup_warm())
    assert llamadas == ["_calentar_probes", "_anunciar_memoria", "_asegurar_rutina_catastro",
                        "_asegurar_rutina_cierre", "_asegurar_rutina_consumo", "_routines_ticker"]
    # un chroma roto al anunciar no se lleva el arranque (fail-open)
    llamadas.clear()
    monkeypatch.setattr(srv, "_anunciar_memoria", lambda: (_ for _ in ()).throw(RuntimeError("sqlite roto")))
    asyncio.run(srv._startup_warm())
    assert llamadas[-1] == "_routines_ticker"


# --- el turno por el harness -----------------------------------------------------

def test_un_turno_con_la_memoria_muerta_contesta_sin_recuerdos_con_done_y_filas(chat, memoria_real, monkeypatch):
    """La memoria real, el `_build_context` REAL (el fixture lo dobla) y el
    embedder caido en la fachada y en los ambitos (`_matar`): el recall del
    turno corre fuera del try del turno, asi que antes esto tumbaba el
    websocket. Ahora: la respuesta entera, un `done`, `recall_fallo` en
    telemetria y, como el remember de fondo embebe con el `_embed` del Scope
    (tambien caido), `remember_fallo` y ningun upsert."""
    monkeypatch.setattr(srv, "_build_context", _BUILD_CONTEXT_REAL)
    monkeypatch.setattr(srv.prompt_compiler, "economia_brief", lambda base: "")
    monkeypatch.setattr(srv.prompt_compiler, "proyectos_brief", lambda root: "")
    _matar(memoria_real)
    eventos = chat.turno("/local que libro lei")
    assert len(de_tipo(eventos, "done")) == 1 and de_tipo(eventos, "error") == []
    assert texto_visible(eventos) == "hola Pedro"
    acciones = [f["accion"] for f in chat.telemetria("memoria")]
    assert acciones == ["recall_fallo", "remember_fallo"]
    assert all(f["error"] == "connection refused" for f in chat.telemetria("memoria"))
    assert memoria_real.recall_ok is False
    assert memoria_real.glob.count() == 1                       # el remember no llego a escribir
    assert "Recuerdos relevantes" not in chat.modelo.llamadas[0]["messages"][0]["content"]


def test_el_remember_del_turno_corre_despues_del_done_como_tarea_de_fondo(chat, monkeypatch):
    """`done` sale ANTES de que el remember termine (ruling 8.3): la memoria
    falsa se queda esperando una puerta que el test abre recien cuando ya
    recibio el `done`; despues, `esperar_fondo` drena la tarea y el episodio
    esta guardado con la procedencia de siempre."""
    class _Lenta(MemoriaFalsa):
        def __init__(self):
            super().__init__()
            self.entro = threading.Event()
            self.puerta = threading.Event()

        def remember(self, text, scope="auto", **meta):
            self.entro.set()
            assert self.puerta.wait(5), "el remember nunca recibio la puerta"
            return super().remember(text, scope, **meta)
    lenta = _Lenta()
    monkeypatch.setattr(srv, "mem", lenta)
    with chat.cliente.websocket_connect("/ws/chat") as ws:
        ws.send_text(chat.paquete("hola"))
        eventos = chat.recibir(ws, 1)
        assert de_tipo(eventos, "done")
        assert lenta.entro.wait(2), "el remember no arranco tras el done"
        assert lenta.recordado == []                    # done llego y el remember sigue vivo
        vivas = [t for t in list(srv._TAREAS_DE_FONDO) if not t.done()]
        assert len(vivas) == 1
        lenta.puerta.set()
        chat.esperar_fondo()
    texto, scope, meta = lenta.guardados[0]
    assert texto == "Pedro pregunto: hola\nCalipso respondio: hola Pedro"
    assert scope == "global" and meta["kind"] == "chat" and meta["procedencia"] == 1
    assert meta["ruta"] == "local" and meta["chat"] == chat.chat_id
    assert not [t for t in list(srv._TAREAS_DE_FONDO) if not t.done()]


def test_el_remember_de_fondo_tiene_tope_de_dos_en_vuelo_y_ninguno_se_pierde(chat, monkeypatch):
    """Ola de fix del cierre, punto 5 (Codex): cada turno creaba una tarea
    de fondo sin limite (un embed puede esperar 120 s), y dos turnos seguidos
    acumulaban POSTs concurrentes a Ollama. Tres turnos seguidos en la misma
    conexion con un embedder LENTO (0,3 s, retenido por una puerta): los tres
    `guardados` al final y nunca mas de 2 en vuelo (contador en el doble).
    El `done` no espera al semaforo: ya salio."""
    class _Lenta(MemoriaFalsa):
        def __init__(self):
            super().__init__()
            self.puerta = threading.Event()
            self.candado = threading.Lock()
            self.en_vuelo = 0
            self.max_en_vuelo = 0
            self.entradas = 0

        def remember(self, text, scope="auto", **meta):
            with self.candado:
                self.en_vuelo += 1
                self.entradas += 1
                self.max_en_vuelo = max(self.max_en_vuelo, self.en_vuelo)
            try:
                assert self.puerta.wait(5), "el remember nunca recibio la puerta"
                return super().remember(text, scope, **meta)
            finally:
                with self.candado:
                    self.en_vuelo -= 1
    lenta = _Lenta()
    monkeypatch.setattr(srv, "mem", lenta)
    with chat.cliente.websocket_connect("/ws/chat") as ws:
        for texto in ("uno", "dos", "tres"):
            ws.send_text(chat.paquete(texto))
            eventos = chat.recibir(ws, 1)
            assert len(de_tipo(eventos, "done")) == 1
        time.sleep(0.3)                                  # el embedder lento: los tres ya pidieron entrar
        assert lenta.entradas == 2 and lenta.max_en_vuelo == 2, (lenta.entradas, lenta.max_en_vuelo)
        assert lenta.recordado == []                     # los done salieron con los remember vivos
        lenta.puerta.set()
        chat.esperar_fondo()
    # ninguno se pierde: los tres textos, en cualquier orden. Dos remember
    # concurrentes (el tope es 2 en vuelo) terminan en el orden en que el
    # scheduler los despierta, no en el de los turnos: afirmar [uno, dos,
    # tres] fallaba 1 de 3 bajo carga (cierre 2026-09-14, flaky ajeno)
    esperados = [f"Pedro pregunto: {t}\nCalipso respondio: hola Pedro" for t in ("uno", "dos", "tres")]
    assert sorted(g[0] for g in lenta.guardados) == sorted(esperados)
    assert len(lenta.guardados) == 3
    assert lenta.max_en_vuelo == 2 and lenta.entradas == 3
    assert not [t for t in list(srv._TAREAS_DE_FONDO) if not t.done()]


def test_el_shutdown_espera_las_tareas_de_fondo_y_anota_las_que_vencen(chat, monkeypatch):
    """Al apagar el app se esperan las tareas de fondo hasta 10 s; si vence,
    la fila `kind: memoria, accion: remember_pendiente, n: N` (nada se pierde
    en silencio). Sin tareas vivas, ninguna fila."""
    async def _rapida():
        await asyncio.sleep(0.01)

    async def _eterna(puerta: asyncio.Event):
        await puerta.wait()

    async def escenario():
        srv._en_fondo(_rapida())
        await srv._esperar_fondo_al_apagar(plazo=1.0)
        assert not [t for t in list(srv._TAREAS_DE_FONDO) if not t.done()]
        assert chat.telemetria("memoria") == []
        puerta = asyncio.Event()
        t1 = srv._en_fondo(_eterna(puerta))
        t2 = srv._en_fondo(_eterna(puerta))
        await srv._esperar_fondo_al_apagar(plazo=0.05)
        filas = chat.telemetria("memoria")
        assert [(f["accion"], f["n"]) for f in filas] == [("remember_pendiente", 2)]
        puerta.set()
        await asyncio.gather(t1, t2)
    asyncio.run(escenario())
    assert not [t for t in list(srv._TAREAS_DE_FONDO) if not t.done()]


def test_un_remember_de_fondo_que_revienta_deja_su_fila_y_no_toca_el_turno(chat, monkeypatch):
    class _Rota(MemoriaFalsa):
        def remember(self, text, scope="auto", **meta):
            raise RuntimeError("chroma roto")
    monkeypatch.setattr(srv, "mem", _Rota())
    eventos = chat.turno("hola")
    assert len(de_tipo(eventos, "done")) == 1 and texto_visible(eventos) == "hola Pedro"
    assert [f["accion"] for f in chat.telemetria("memoria")] == ["remember_fallo"]
    assert chat.telemetria("memoria")[0]["error"] == "chroma roto"
    assert chat.mensajes()[-1]["text"] == "hola Pedro"          # el mensaje se guardo igual


# --- el abismo -------------------------------------------------------------------

class _MemoriaMuerta:
    recall_ok = False

    def recall(self, pregunta, n=5, ambitos=None):
        return []

    def load_core(self):
        return ""


class _MemoriaVaciaPeroViva(_MemoriaMuerta):
    recall_ok = True


def test_la_fuente_memoria_cierra_con_memoria_no_disponible_y_no_con_vacio(tmp_path, monkeypatch):
    monkeypatch.setattr(fuentes.chronology, "CALIPSO_HOME", tmp_path)
    r = consulta.resolver(marca.Marca("memoria", "el libro"), mem=_MemoriaMuerta())
    assert r["estado"] == "fallo" and r["aviso"] == fuentes.AVISO_MEMORIA_NO_DISPONIBLE
    assert abismo_turno.motivo_de_consulta(r) == "memoria_no_disponible"
    assert "memoria_no_disponible" in abismo_turno.MOTIVOS
    assert abismo_turno.senal("fallo", "memoria", motivo="memoria_no_disponible")["motivo"] == "memoria_no_disponible"
    # una memoria viva sin hits sigue siendo la pesca vacia de siempre
    r = consulta.resolver(marca.Marca("memoria", "el libro"), mem=_MemoriaVaciaPeroViva())
    assert abismo_turno.motivo_de_consulta(r) == "vacio"
    # un doble sin el atributo (los tests viejos) vale como viva
    class _SinAtributo:
        def recall(self, pregunta, n=5, ambitos=None):
            return []

        def load_core(self):
            return ""
    assert abismo_turno.motivo_de_consulta(consulta.resolver(marca.Marca("memoria", "x"), mem=_SinAtributo())) == "vacio"
