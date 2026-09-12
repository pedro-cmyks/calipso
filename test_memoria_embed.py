"""La funcion de embeddings por Ollama y la Memory sin torch (spec memoria por
Ollama 2026-09-12, secciones 2 y 5): la request y la respuesta de
`_post_embed` con `urlopen` doblado (modelo, input, truncate, keep_alive y
num_thread por nivel, timeout, contador de uso), los errores como EmbedError,
la EF pura y registrada en chroma (una coleccion en un tmp que se reabre sin
pasar EF), el texto que se embebe, los lotes por tamano; y `Memory` con
`EmbedFalsa`: la coleccion `episodic-<tag>`, una sola embedding por recall
para los dos ambitos, ninguna sin episodios, el fail-open con fila y
`recall_ok`, y el remember con embeddings explicitos (ids y procedencia
intactos). Ningun test toca Ollama ni huggingface.co."""
from __future__ import annotations

import hashlib
import json
import os

import chromadb
import numpy as np
import pytest
from chromadb.utils.embedding_functions import known_embedding_functions

from calipso import carga
from calipso import config as calipso_config
from calipso import memoria_embed as me
from calipso import memory

PAR = "Pedro pregunto: /local que libro lei\nCalipso respondio: El nombre de la rosa, de Eco."


class _Resp:
    def __init__(self, cuerpo: bytes):
        self.cuerpo = cuerpo

    def read(self):
        return self.cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture(autouse=True)
def _carga_limpia():
    carga.olvidar()
    yield
    carga.olvidar()


def _urlopen_falso(monkeypatch, vectores=None, error=None, dims=1024):
    """Un urlopen que anota la request (url, payload, timeout, en_uso en ese
    instante) y contesta un vector de `dims` por input, o levanta `error`."""
    vistos = []

    def urlopen(req, timeout=None):
        payload = json.loads(req.data.decode())
        vistos.append({"url": req.full_url, "payload": payload, "timeout": timeout,
                       "en_uso": carga.en_uso, "content_type": req.get_header("Content-type")})
        if error is not None:
            raise error
        n = len(payload["input"])
        vs = vectores if vectores is not None else [[0.5] * dims for _ in range(n)]
        return _Resp(json.dumps({"model": "bge-m3:latest", "embeddings": vs}).encode())
    monkeypatch.setattr(me.urllib.request, "urlopen", urlopen)
    return vistos


# --- lo puro -------------------------------------------------------------------

def test_texto_para_embedding_es_la_pregunta_limpia_y_las_primeras_palabras_de_respuesta():
    """Con `palabras=150` EXPLICITO: el default lo prueba el test siguiente
    (el Step 10 de la Task 3 puede dejar PALABRAS_RESPUESTA en otro numero)."""
    respuesta = " ".join(f"p{i}" for i in range(400))
    doc = f"Pedro pregunto: /local /nube que libro lei\nCalipso respondio: {respuesta}"
    texto = me.texto_para_embedding(doc, palabras=150)
    pregunta, cabeza = texto.split("\n", 1)
    assert pregunta == "que libro lei"
    assert cabeza.split() == [f"p{i}" for i in range(150)]
    assert "Pedro pregunto" not in texto and "Calipso respondio" not in texto
    # con menos palabras entra todo; palabras=0 es la pregunta sola (variante del banco)
    assert me.texto_para_embedding(PAR, palabras=150) == "que libro lei\nEl nombre de la rosa, de Eco."
    assert me.texto_para_embedding(PAR, palabras=0) == "que libro lei"
    # el par entero (variante `par` del banco) es la pregunta limpia + la respuesta entera, sin etiquetas
    assert me.texto_para_embedding(doc, palabras=10_000).split("\n", 1)[1].split() == [f"p{i}" for i in range(400)]
    # el mojibake viejo tambien parsea (partir lo admite)
    assert me.texto_para_embedding("Pedro preguntÃ³: hola\nCalipso respondiÃ³: Hola Pedro.", palabras=150) == "hola\nHola Pedro."


def test_el_default_es_palabras_respuesta_leido_por_llamada(monkeypatch):
    """Sin `palabras=` manda `PALABRAS_RESPUESTA`, leido en cada llamada: el
    banco (Task 3, Step 10) puede dejarlo en 0 (pregunta sola) o en 10_000
    (par) sin tocar este test; cambia el numero, no la forma (ruling 2)."""
    respuesta = " ".join(f"p{i}" for i in range(400))
    doc = f"Pedro pregunto: que libro lei\nCalipso respondio: {respuesta}"
    assert isinstance(me.PALABRAS_RESPUESTA, int) and me.PALABRAS_RESPUESTA >= 0
    assert me.texto_para_embedding(doc) == me.texto_para_embedding(doc, palabras=me.PALABRAS_RESPUESTA)
    monkeypatch.setattr(me, "PALABRAS_RESPUESTA", 0)
    assert me.texto_para_embedding(doc) == "que libro lei"
    monkeypatch.setattr(me, "PALABRAS_RESPUESTA", 10_000)
    assert me.texto_para_embedding(doc).split("\n", 1)[1].split() == [f"p{i}" for i in range(400)]


def test_texto_para_embedding_tolera_otros_formatos():
    meta = "Pedro definio una meta: terminar el taller\nCalipso creo Goal Mode: g-1"
    assert me.texto_para_embedding(meta) == meta
    # lo que no es un par NO depende de `palabras`: con la variante pregunta sola (0) una meta no queda vacia
    assert me.texto_para_embedding(meta, palabras=0) == meta
    largo = " ".join(f"w{i}" for i in range(500))
    assert me.PALABRAS_OTRO == 300
    assert me.texto_para_embedding(largo, palabras=150).split() == [f"w{i}" for i in range(300)]
    assert me.texto_para_embedding(largo, palabras=0).split() == [f"w{i}" for i in range(300)]
    assert me.texto_para_embedding("") == ""
    # una pregunta que era SOLO gestos conserva el gesto antes que quedar vacia
    assert me.texto_para_embedding("Pedro pregunto: /local\nCalipso respondio: hola", palabras=150) == "/local\nhola"


def test_lotes_por_tamano_y_un_documento_largo_va_solo():
    assert me.lotes([]) == []
    assert me.lotes(["a", "b", "c"], max_chars=2) == [["a", "b"], ["c"]]
    largo = "x" * 10
    assert me.lotes(["aa", largo, "bb", "cc"], max_chars=5) == [["aa"], [largo], ["bb", "cc"]]
    assert me.lotes([largo], max_chars=5) == [[largo]]
    assert me.LOTE_CHARS == 8000 and me.TIMEOUT_RECALL_S == 10.0 and me.TIMEOUT_REMEMBER_S == 120.0


def test_embed_tag_y_los_nombres_de_coleccion():
    assert me.embed_tag("bge-m3:latest") == "bge-m3"
    assert me.embed_tag("bge-m3") == "bge-m3"
    assert me.embed_tag("nomic-embed-text:v1.5") == "nomic-embed-text-v1.5"
    assert me.embed_tag("raro/modelo:latest") == "raro-modelo"
    assert me.embed_tag(":latest") == "sin-modelo"
    assert me.COLECCION_VIEJA == "episodic"
    assert me.COLECCION_VIVA == f"episodic-{me.embed_tag(calipso_config.EMBED_MODEL)}"
    assert calipso_config.EMBED_MODEL == "bge-m3:latest" and calipso_config.EMBED_DIMS == 1024


def test_la_ef_es_pura_al_construirse_y_se_reconstruye_por_config(monkeypatch):
    vistos = _urlopen_falso(monkeypatch)
    ef = me.OllamaEmbed()
    assert (ef.url, ef.model, ef.dims) == (calipso_config.EMBED_URL, "bge-m3:latest", 1024)
    assert me.OllamaEmbed.name() == "calipso_ollama"
    assert ef.get_config() == {"url": calipso_config.EMBED_URL, "model": "bge-m3:latest", "dims": 1024}
    otra = me.OllamaEmbed.build_from_config({"url": "http://127.0.0.1:1/", "model": "m:latest", "dims": 8})
    assert isinstance(otra, me.OllamaEmbed) and (otra.url, otra.model, otra.dims) == ("http://127.0.0.1:1", "m:latest", 8)
    assert me.OllamaEmbed.validate_config({}) is None and ef.validate_config_update({}, {}) is None
    assert ef.default_space() == "cosine"
    assert isinstance(me.EmbedFalsa.build_from_config(ef.get_config()), me.EmbedFalsa)
    assert vistos == [], "construir o reconstruir la EF hizo red"


# --- el POST -------------------------------------------------------------------

def test_embed_manda_modelo_input_truncate_y_las_perillas_del_nivel(monkeypatch):
    vistos = _urlopen_falso(monkeypatch)
    ef = me.OllamaEmbed(url="http://127.0.0.1:11434/")
    assert ef.embed(["hola", "chau"]) == [[0.5] * 1024, [0.5] * 1024]
    v, = vistos
    assert v["url"] == "http://127.0.0.1:11434/api/embed" and v["content_type"] == "application/json"
    assert v["payload"] == {"model": "bge-m3:latest", "input": ["hola", "chau"], "truncate": True,
                            "keep_alive": carga.keep_alive("holgada")}
    assert v["timeout"] == me.TIMEOUT_REMEMBER_S
    monkeypatch.setattr(carga, "nivel_reciente", lambda: "cargada")
    ef.embed(["x"])
    assert vistos[-1]["payload"]["keep_alive"] == carga.keep_alive("cargada")
    assert vistos[-1]["payload"]["options"] == {"num_thread": carga.num_thread("cargada")}


def test_embed_usa_el_timeout_del_llamador_y_toma_el_contador_de_uso(monkeypatch):
    vistos = _urlopen_falso(monkeypatch)
    ef = me.OllamaEmbed()
    ef.embed(["q"], timeout=me.TIMEOUT_RECALL_S)
    assert vistos[-1]["timeout"] == 10.0
    assert vistos[-1]["en_uso"] == 1 and carga.en_uso == 0    # usando(): tomado durante el POST, suelto despues


def test_embed_parte_en_lotes_por_tamano_y_concatena_en_orden(monkeypatch):
    vistos = _urlopen_falso(monkeypatch)
    monkeypatch.setattr(me, "LOTE_CHARS", 6)
    ef = me.OllamaEmbed()
    salida = ef.embed(["aaa", "bbb", "cccccccc", "d"])
    assert [v["payload"]["input"] for v in vistos] == [["aaa", "bbb"], ["cccccccc"], ["d"]]
    assert len(salida) == 4
    assert vistos[0]["en_uso"] == 1 and vistos[-1]["en_uso"] == 1 and carga.en_uso == 0


def test_embed_vacio_no_postea(monkeypatch):
    vistos = _urlopen_falso(monkeypatch)
    assert me.OllamaEmbed().embed([]) == []
    assert vistos == []


def test_un_error_de_red_o_timeout_es_embed_error(monkeypatch):
    _urlopen_falso(monkeypatch, error=OSError("connection refused"))
    with pytest.raises(me.EmbedError, match="connection refused"):
        me.OllamaEmbed().embed(["q"])
    _urlopen_falso(monkeypatch, error=TimeoutError("timed out"))
    with pytest.raises(me.EmbedError, match="timed out"):
        me.OllamaEmbed().embed(["q"], timeout=0.01)
    assert carga.en_uso == 0
    monkeypatch.setattr(me.urllib.request, "urlopen", lambda req, timeout=None: _Resp(b"no es json"))
    with pytest.raises(me.EmbedError):
        me._post_embed("http://127.0.0.1:1/api/embed", {}, 1.0)


def test_una_respuesta_con_otras_dims_o_menos_vectores_es_embed_error(monkeypatch):
    _urlopen_falso(monkeypatch, vectores=[[0.1, 0.2, 0.3]])
    with pytest.raises(me.EmbedError, match="3 dimensiones"):
        me.OllamaEmbed().embed(["q"])
    _urlopen_falso(monkeypatch, vectores=[[0.5] * 1024])
    with pytest.raises(me.EmbedError, match="esperaba 2 vectores"):
        me.OllamaEmbed().embed(["q", "r"])
    monkeypatch.setattr(me.urllib.request, "urlopen", lambda req, timeout=None: _Resp(b'{"error": "model not found"}'))
    with pytest.raises(me.EmbedError):
        me.OllamaEmbed().embed(["q"])


# --- el registro en chroma -----------------------------------------------------

def test_la_ef_registrada_se_reabre_sin_pasarla_y_chroma_nunca_la_llama(tmp_path, monkeypatch):
    vistos = _urlopen_falso(monkeypatch)
    falsa = me.EmbedFalsa()
    cli = chromadb.PersistentClient(path=str(tmp_path))
    col = cli.get_or_create_collection(me.COLECCION_VIVA, embedding_function=me.OllamaEmbed(),
                                       metadata={"hnsw:space": "cosine"})
    vec = falsa.embed(["uno", "dos"])
    col.upsert(ids=["a", "b"], documents=["uno", "dos"], metadatas=[{"k": 1}, None], embeddings=vec)
    assert vistos == [], "chroma llamo a la EF real aunque los embeddings vinieron explicitos"
    reabierta = chromadb.PersistentClient(path=str(tmp_path)).get_collection(me.COLECCION_VIVA)
    assert reabierta.count() == 2
    r = reabierta.query(query_embeddings=[vec[0]], n_results=2)
    assert r["ids"][0][0] == "a" and abs(r["distances"][0][0]) < 1e-5
    assert reabierta.get(include=[])["ids"] == ["a", "b"]
    assert issubclass(known_embedding_functions["calipso_ollama"], me.OllamaEmbed)
    assert reabierta.configuration_json["embedding_function"]["name"] == "calipso_ollama"
    # la falsa abre la misma coleccion sin conflicto: mismo name()
    otra = chromadb.PersistentClient(path=str(tmp_path)).get_or_create_collection(
        me.COLECCION_VIVA, embedding_function=falsa, metadata={"hnsw:space": "cosine"})
    assert otra.count() == 2 and vistos == []


def test_embed_falsa_es_determinista_de_1024_dims_y_sin_red(monkeypatch):
    vistos = _urlopen_falso(monkeypatch)
    ef = me.EmbedFalsa()
    a, b = ef.embed(["hola", "hola"])
    c, = ef.embed(["chau"])
    assert a == b and a != c and len(a) == 1024
    assert abs(sum(x * x for x in a) - 1.0) < 1e-4
    assert ef.llamadas == [["hola", "hola"], ["chau"]]
    assert vistos == []
    assert me.EmbedFalsa.name() == "calipso_ollama" and ef.get_config()["dims"] == 1024
    assert isinstance(ef(["z"])[0], np.ndarray)      # el __call__ envuelto por chroma sigue andando


def test_embedder_por_env(monkeypatch):
    monkeypatch.setenv("CALIPSO_EMBED_FALSA", "1")
    assert isinstance(me.embedder_por_env(), me.EmbedFalsa)
    monkeypatch.delenv("CALIPSO_EMBED_FALSA")
    ef = me.embedder_por_env()
    assert type(ef) is me.OllamaEmbed


def test_la_suite_construye_la_falsa_por_el_conftest():
    """Invariante 6 (ningun test llama a Ollama), como guardia y no solo por
    construccion: conftest.py fija CALIPSO_EMBED_FALSA=1 antes de importar
    calipso, y la Memory que `import calipso.server` construye a nivel de
    modulo tiene que ser la falsa. Si alguien borra esa linea del conftest,
    la suite construiria OllamaEmbed real y cada recall con count > 0
    POSTearia a localhost:11434: este test lo marca."""
    import calipso.server as srv
    assert os.environ.get("CALIPSO_EMBED_FALSA") == "1", "conftest.py dejo de fijar CALIPSO_EMBED_FALSA"
    assert isinstance(srv.mem._embed, me.EmbedFalsa)
    assert all(isinstance(s._embed, me.EmbedFalsa) for s in srv.mem._scopes)


def test_embeber_usa_embed_con_timeout_o_el_call_de_una_ef_ajena():
    ef = me.EmbedFalsa()
    assert me.embeber(ef, ["q"], timeout=3.0) == ef.embed(["q"])

    class _Ajena:
        def __call__(self, input):
            return [np.array([1.0, 2.0], dtype=np.float32) for _ in input]
    assert me.embeber(_Ajena(), ["q", "r"]) == [[1.0, 2.0], [1.0, 2.0]]


def test_sin_reindexar_cuenta_los_ids_de_la_vieja_que_no_estan_en_la_viva(tmp_path):
    cli = chromadb.PersistentClient(path=str(tmp_path))
    assert me.ids_de(cli, "episodic") is None and me.sin_reindexar(cli) == 0
    vieja = cli.get_or_create_collection("episodic", metadata={"hnsw:space": "cosine"})
    vieja.add(ids=["m1", "m2", "m3"], documents=["a", "b", "c"],
              embeddings=[[0.1, 0.2, 0.3], [0.2, 0.2, 0.3], [0.3, 0.2, 0.3]])
    assert me.sin_reindexar(cli) == 3
    viva = cli.get_or_create_collection(me.COLECCION_VIVA, embedding_function=me.EmbedFalsa(),
                                        metadata={"hnsw:space": "cosine"})
    viva.upsert(ids=["m1", "m3"], documents=["a", "c"], embeddings=me.EmbedFalsa().embed(["a", "c"]))
    assert me.ids_de(cli, me.COLECCION_VIVA) == {"m1", "m3"}
    assert me.sin_reindexar(cli) == 1


# --- Memory con EmbedFalsa -----------------------------------------------------

class _EmbedQueRevienta(me.EmbedFalsa):
    def embed(self, textos, timeout=None):
        raise me.EmbedError("ollama caido: connection refused")


@pytest.fixture
def mem(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "CALIPSO_HOME", tmp_path / "home")
    monkeypatch.setenv("CALIPSO_EMBED_FALSA", "1")
    m = memory.Memory(project_root=str(tmp_path / "repo"))
    assert isinstance(m._embed, me.EmbedFalsa)
    return m


def test_la_coleccion_viva_lleva_el_tag_del_embedder(mem):
    assert mem.glob._col.name == me.COLECCION_VIVA == "episodic-bge-m3"
    assert mem.project._col.name == me.COLECCION_VIVA
    assert mem.glob._col.metadata == {"hnsw:space": "cosine"}
    assert memory.COLECCION == me.COLECCION_VIVA and memory.EMBED_MODEL == calipso_config.EMBED_MODEL
    # la vieja no existe en un home nuevo: nada que reindexar
    assert me.ids_de(mem.glob._client, "episodic") is None


def test_memory_acepta_una_ef_inyectada(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, "CALIPSO_HOME", tmp_path)
    ef = me.EmbedFalsa()
    m = memory.Memory(embed=ef)
    assert m._embed is ef and m.glob._embed is ef
    assert m.departamento("atlas")._embed is ef


def test_remember_embebe_el_texto_para_embedding_y_conserva_id_y_procedencia(mem):
    ts_antes = len(mem._embed.llamadas)
    mid = mem.remember(PAR, scope="global", route="local", kind="chat", ruta="local",
                       modelo="qwen2.5:7b", chat="c1", procedencia=1, nada=None)
    assert mem._embed.llamadas[ts_antes:] == [[me.texto_para_embedding(PAR)]]
    datos = mem.glob._col.get(ids=[mid], include=["documents", "metadatas", "embeddings"])
    assert datos["documents"] == [PAR]
    meta = datos["metadatas"][0]
    assert meta["procedencia"] == 1 and meta["ruta"] == "local" and meta["chat"] == "c1" and "nada" not in meta
    esperado = me.EmbedFalsa().embed([me.texto_para_embedding(PAR)])[0]
    assert np.allclose(np.asarray(datos["embeddings"][0]), np.asarray(esperado), atol=1e-6)
    huella = repr((PAR, sorted(meta.items())))
    assert mid == "m" + hashlib.sha256(huella.encode("utf-8")).hexdigest()[:24]
    assert mem.glob.count() == 1 and mem.project.count() == 0


def test_recall_embebe_la_pregunta_una_sola_vez_para_los_dos_ambitos(mem):
    mem.remember(PAR, scope="global", kind="chat")
    mem.remember("Pedro pregunto: que es un websocket\nCalipso respondio: Una conexion bidireccional.",
                 scope="project", kind="chat")
    mem._embed.llamadas.clear()
    hits = mem.recall("que libro lei\nEl nombre de la rosa, de Eco.", n=5)
    assert mem._embed.llamadas == [["que libro lei\nEl nombre de la rosa, de Eco."]]
    assert {h["scope"] for h in hits} == {"global", "project"}
    assert hits[0]["text"] == PAR and hits[0]["score"] == 1.0      # el texto exacto de lo embebido: distancia 0
    assert hits[0]["meta"]["kind"] == "chat"
    assert mem.recall_ok is True and mem.ultimo_recall_fallo is None
    # ambitos= sigue filtrando, y sigue siendo una embedding
    mem._embed.llamadas.clear()
    assert {h["scope"] for h in mem.recall("q", n=5, ambitos=("project",))} == {"project"}
    assert len(mem._embed.llamadas) == 1


def test_recall_sin_episodios_no_embebe(mem):
    mem._embed.llamadas.clear()
    assert mem.recall("hola", n=5) == []
    assert mem._embed.llamadas == []
    assert mem.recall_ok is True


def test_recall_es_fail_open_y_visible(mem, monkeypatch):
    filas = []
    monkeypatch.setattr(memory.telemetry, "log_event", lambda kind, **k: filas.append({"kind": kind, **k}))
    mem.remember(PAR, scope="global", kind="chat")
    sana = mem._embed
    mem._embed = _EmbedQueRevienta()       # alcanza para el recall: Memory.recall embebe con Memory._embed
    assert mem.recall("que libro lei", n=5) == []
    assert mem.recall_ok is False
    assert "ollama caido" in mem.ultimo_recall_fallo["error"] and mem.ultimo_recall_fallo["ts"]
    assert filas == [{"kind": "memoria", "accion": "recall_fallo",
                      "error": "ollama caido: connection refused"}]
    # una coleccion rota tambien es fail-open (el parche vive en su propio
    # contexto: `monkeypatch.undo()` desharia tambien el CALIPSO_HOME del fixture)
    mem._embed = sana
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(type(mem.glob._col), "query",
                   lambda self, **k: (_ for _ in ()).throw(RuntimeError("hnsw roto")))
        assert mem.recall("que libro lei", n=5) == []
    assert filas[-1]["error"] == "hnsw roto" and mem.recall_ok is False
    # se recupera solo
    assert mem.recall("que libro lei", n=5) and mem.recall_ok is True


def test_scope_recall_conserva_la_costura_vieja(mem):
    mem.remember(PAR, scope="global", kind="chat")
    mem._embed.llamadas.clear()
    hits = mem.glob.recall("que libro lei", 3)          # sin vector: embebe solo
    assert len(hits) == 1 and mem._embed.llamadas == [["que libro lei"]]
    vector = mem._embed.embed(["que libro lei"])[0]
    mem._embed.llamadas.clear()
    assert mem.glob.recall("que libro lei", 3, embedding=vector) == hits
    assert mem._embed.llamadas == []
    assert mem.project.recall("q", 3) == []             # sin episodios: [] sin embeber
