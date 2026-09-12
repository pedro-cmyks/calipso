"""El reindexado sobre un home temporal (spec 2026-09-11, secciones 3 y 5):
`--vista` no escribe; `--aplicar` conserva ids, documentos, embeddings y
cantidad, preserva las claves viejas y agrega `procedencia` y `ruta`; es
idempotente; cuenta lo que no parsea; se niega con el puerto ocupado y
sigue con `--forzar`. Al final, sobre una copia del fixture real del porton.

Y el reindex a otro embedder (spec memoria por Ollama 2026-09-12):
`--embeddings` copia `episodic` a `episodic-<tag>` con los MISMOS ids,
documentos y metadatos, embebiendo por lotes (aca con EmbedFalsa: la suite
no toca Ollama); es idempotente (un id que ya esta solo converge sus
metadatos); no admite `--forzar`; toma la lista de ids antes y despues;
`--vista` imprime `sin_reindexar` sin embeber; y `--vista/--aplicar` operan
sobre la viva si existe (si no, sobre la vieja: los dos ordenes convergen).

Los chromas de prueba se arman SIN modelo (embeddings explicitos de 3 dims
en la vieja): asi el test tarda medio segundo y no depende de nada."""
from __future__ import annotations

import io
import pathlib
import shutil
import socket

import chromadb
import pytest

from calipso import memoria_embed as me
from calipso import memoria_reindex as mr

FIXTURE = pathlib.Path(__file__).resolve().parent / "experimentos" / "fixtures" / "memoria_smoke_home"

CHAT_DATO = "Pedro pregunto: /local que libro lei\nCalipso respondio: El nombre de la rosa."
CHAT_SIN_DATO = "Pedro pregunto: quien me presto el libro?\nCalipso respondio: No tengo registros de eso."
CHAT_BASURA = "Pedro pregunto: /nube\nCalipso respondio: Hola, en que te ayudo?"
CHAT_VIEJO = "Pedro preguntÃ³: hola\nCalipso respondiÃ³: Hola Pedro."
META_GOAL = "Pedro definio una meta: terminar\nCalipso creo Goal Mode: g-1"


def _sembrar(chroma_dir: pathlib.Path, filas: list[tuple[str, str, dict]]):
    cli = chromadb.PersistentClient(path=str(chroma_dir))
    col = cli.get_or_create_collection("episodic", metadata={"hnsw:space": "cosine"})
    if filas:
        col.add(ids=[f[0] for f in filas], documents=[f[1] for f in filas],
                metadatas=[f[2] for f in filas],
                embeddings=[[0.1 * (i + 1), 0.2, 0.3] for i in range(len(filas))])
    return col


def _leer(chroma_dir: pathlib.Path, nombre: str = "episodic") -> dict:
    col = chromadb.PersistentClient(path=str(chroma_dir)).get_collection(nombre, embedding_function=None)
    g = col.get(include=["documents", "metadatas", "embeddings"])
    return {"count": col.count(), "ids": list(g["ids"]), "docs": list(g["documents"]),
            "metas": list(g["metadatas"]),
            "emb": [list(map(float, e)) for e in g["embeddings"]]}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    monkeypatch.setenv("CALIPSO_PORT", "1")     # nada escucha en el 1
    g = tmp_path / "global" / "chroma"
    _sembrar(g, [
        ("m1", CHAT_DATO, {"ts": "2026-09-10T20:58:05", "route": "local", "kind": "chat"}),
        ("m2", CHAT_SIN_DATO, {"ts": "2026-09-10T21:00:00", "route": "api", "kind": "chat"}),
        ("m3", CHAT_BASURA, {"ts": "2026-09-10T21:01:00", "route": "local", "kind": "chat"}),
        ("m4", "un episodio roto sin forma de par", {"ts": "2026-09-10T21:02:00", "kind": "chat"}),
        ("m5", CHAT_DATO, {"ts": "2026-09-10T21:03:00"}),                  # sin kind: es chat
        ("m6", "Pedro pregunto: ya\nCalipso respondio: reindexado",
         {"ts": "2026-09-11T08:00:00", "route": "local", "ruta": "local",
          "kind": "chat", "chat": "c1", "modelo": "q", "procedencia": 1}),  # lo nuevo
    ])
    p = tmp_path / "projects" / "var-home-pedro-calipso" / "chroma"
    _sembrar(p, [
        ("p1", CHAT_VIEJO, {"ts": "2026-07-01T10:00:00", "route": "local", "kind": "chat"}),
        ("p2", META_GOAL, {"ts": "2026-08-14T09:00:00", "route": "goal", "kind": "goal"}),
    ])
    (tmp_path / "projects" / "sin-chroma").mkdir(parents=True)          # se ignora
    (tmp_path / "memoria" / "departamento" / "atlas" / "chroma").mkdir(parents=True)
    return tmp_path


def _correr(*args) -> tuple[int, str]:
    out = io.StringIO()
    codigo = mr.main(list(args), salida=out)
    return codigo, out.getvalue()


def test_ambitos_solo_los_que_existen_con_sqlite(home):
    nombres = [n for n, _ in mr.ambitos(home)]
    assert nombres == ["global", "projects/var-home-pedro-calipso"]


def test_vista_cuenta_y_no_escribe(home):
    antes = _leer(home / "global" / "chroma")
    codigo, texto = _correr("--vista")
    assert codigo == 0
    assert ("global: 6 episodios, 1 con procedencia, 5 parsean como chat, "
            "1 kind=chat que NO parsean, 0 no chat, 1 sin_dato, 1 basura, 0 raros "
            "-> 4 por reindexar") in texto
    assert ("projects/var-home-pedro-calipso: 2 episodios, 0 con procedencia, "
            "1 parsean como chat, 0 kind=chat que NO parsean, 1 no chat, 0 sin_dato, "
            "0 basura, 0 raros -> 1 por reindexar") in texto
    assert _leer(home / "global" / "chroma") == antes


def test_aplicar_conserva_ids_documentos_embeddings_y_cantidad_y_mergea(home):
    antes = _leer(home / "global" / "chroma")
    codigo, texto = _correr("--aplicar")
    assert codigo == 0, texto
    assert "global: 4 episodios reindexados; count 6 -> 6" in texto
    assert "OJO" not in texto
    despues = _leer(home / "global" / "chroma")
    assert (despues["count"], despues["ids"], despues["docs"], despues["emb"]) == (
        antes["count"], antes["ids"], antes["docs"], antes["emb"])
    por_id = dict(zip(despues["ids"], despues["metas"]))
    # las claves viejas quedan, las nuevas se suman, sin None
    assert por_id["m1"] == {"ts": "2026-09-10T20:58:05", "route": "local", "kind": "chat",
                            "procedencia": 1, "ruta": "local"}
    assert por_id["m2"]["ruta"] == "api" and por_id["m2"]["procedencia"] == 1
    assert por_id["m3"]["procedencia"] == 1            # la basura tambien se marca
    assert por_id["m5"] == {"ts": "2026-09-10T21:03:00", "procedencia": 1}   # sin route: sin ruta
    # lo que no parsea y lo ya reindexado no se tocan
    assert por_id["m4"] == {"ts": "2026-09-10T21:02:00", "kind": "chat"}
    assert por_id["m6"]["chat"] == "c1" and por_id["m6"]["modelo"] == "q"
    # el proyecto: lo viejo con acentos rotos entra, la meta no
    proyecto = dict(zip(*[_leer(home / "projects" / "var-home-pedro-calipso" / "chroma")[k]
                          for k in ("ids", "metas")]))
    assert proyecto["p1"] == {"ts": "2026-07-01T10:00:00", "route": "local", "kind": "chat",
                              "procedencia": 1, "ruta": "local"}
    assert proyecto["p2"] == {"ts": "2026-08-14T09:00:00", "route": "goal", "kind": "goal"}


def test_la_segunda_corrida_no_cambia_nada_y_lo_dice(home):
    _correr("--aplicar")
    despues_1 = _leer(home / "global" / "chroma")
    codigo, texto = _correr("--aplicar")
    assert codigo == 0
    assert "global: 6 episodios, 5 con procedencia" in texto
    assert "-> 0 por reindexar" in texto
    assert "global: nada que escribir (ya reindexado o sin pares de chat)" in texto
    assert _leer(home / "global" / "chroma") == despues_1


def test_se_niega_con_el_puerto_ocupado_y_sigue_con_forzar(home, monkeypatch):
    escucha = socket.socket()
    escucha.bind(("127.0.0.1", 0))
    escucha.listen(1)
    monkeypatch.setenv("CALIPSO_PORT", str(escucha.getsockname()[1]))
    try:
        antes = _leer(home / "global" / "chroma")
        codigo, texto = _correr("--aplicar")
        assert codigo == 2 and "apagalo (o --forzar)" in texto
        assert _leer(home / "global" / "chroma") == antes
        # ruling 7 (ledger, 2026-09-11): `--vista` SE PERMITE con el server
        # prendido -- es de solo lectura y Pedro necesita ver los conteos
        # sin apagarlo; solo `--aplicar` se niega.
        assert _correr("--vista")[0] == 0
        assert _leer(home / "global" / "chroma") == antes
        codigo, texto = _correr("--aplicar", "--forzar")
        assert codigo == 0 and "--forzar: sigo" in texto
        assert "global: 4 episodios reindexados" in texto
    finally:
        escucha.close()


def test_un_home_sin_ambitos_lo_dice(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    codigo, texto = _correr("--vista")
    assert codigo == 1 and "ningun ambito" in texto


def test_un_directorio_chroma_sin_la_coleccion_se_salta(home):
    d = home / "projects" / "otro" / "chroma"
    chromadb.PersistentClient(path=str(d))          # crea el sqlite, sin coleccion
    codigo, texto = _correr("--vista")
    assert codigo == 0 and "projects/otro: sin coleccion episodic-bge-m3 ni episodic (se salta)" in texto
    codigo, texto = _correr("--embeddings", "--falsa")
    assert codigo == 0 and "projects/otro: sin coleccion episodic (se salta)" in texto


def test_un_episodio_con_metadatos_raros_se_salta_y_se_cuenta(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    monkeypatch.setenv("CALIPSO_PORT", "1")
    col = _sembrar(tmp_path / "global" / "chroma", [])
    col.add(ids=["r1"], documents=[CHAT_DATO], embeddings=[[0.1, 0.2, 0.3]])   # sin meta
    r = mr.revisar(col)
    assert (r["episodios"], r["raros"], r["pendientes"]) == (1, 1, [])
    codigo, texto = _correr("--aplicar")
    assert codigo == 0 and "1 raros -> 0 por reindexar" in texto


def test_sobre_una_copia_del_fixture_real(tmp_path, monkeypatch):
    """El fixture del porton tal cual, con las DOS colecciones (spec memoria
    por Ollama, ruling 8.12): la vista da los numeros del spec de procedencia
    SOBRE LA VIVA (`episodic-bge-m3`, EF `calipso_ollama` pura: sin torch),
    sin_reindexar 0; aplicar deja 16/16 con procedencia en la viva y la vieja
    intacta; y `--embeddings` es idempotente sobre el fixture."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CALIPSO_PORT", "1")
    shutil.copytree(FIXTURE, tmp_path / "home")
    g = tmp_path / "home" / "global" / "chroma"
    vieja_antes = _leer(g)
    antes = _leer(g, VIVA)
    codigo, texto = _correr("--vista")
    assert codigo == 0
    assert f"global: 16 en episodic, 16 en {VIVA}, sin_reindexar 0 (procedencia sobre {VIVA})" in texto
    assert ("global: 16 episodios, 0 con procedencia, 16 parsean como chat, "
            "0 kind=chat que NO parsean, 0 no chat, 5 sin_dato, 0 basura, 0 raros "
            "-> 16 por reindexar") in texto
    assert "projects/var-home-pedro-calipso: 0 episodios" in texto
    codigo, texto = _correr("--aplicar")
    assert codigo == 0 and "global: 16 episodios reindexados; count 16 -> 16" in texto
    despues = _leer(g, VIVA)
    assert (despues["ids"], despues["docs"], despues["emb"]) == (antes["ids"], antes["docs"], antes["emb"])
    assert all(m["procedencia"] == 1 and m["ruta"] == "local" and m["route"] == "local"
               for m in despues["metas"])
    assert _leer(g) == vieja_antes                                # la vieja no se toca
    assert "global: nada que escribir" in _correr("--aplicar")[1]
    codigo, texto = _correr("--embeddings", "--falsa")
    assert codigo == 0 and f"global: 0 copiados a {VIVA}, 16 ya estaban" in texto and "sin_reindexar 0" in texto
    assert _leer(g, VIVA) == despues                              # el merge de metadatos no pisa la procedencia


def test_embeddings_desde_cero_sobre_una_copia_del_fixture(tmp_path, monkeypatch):
    """Spec seccion 5, en la suite y sin Ollama (EmbedFalsa): sobre una copia
    del fixture con la viva borrada EN LA COPIA, `--embeddings` copia los 16
    con ids y metadatos iguales a la vieja y `sin_reindexar` pasa de 16 a 0.
    El smoke (paso X) repite lo mismo con bge-m3 real."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CALIPSO_PORT", "1")
    shutil.copytree(FIXTURE, tmp_path / "home")
    g = tmp_path / "home" / "global" / "chroma"
    chromadb.PersistentClient(path=str(g)).delete_collection(VIVA)       # en la copia, jamas en el fixture
    vieja = _leer(g)
    codigo, texto = _correr("--vista")
    assert codigo == 0 and f"global: 16 en episodic, sin {VIVA}, sin_reindexar 16 (procedencia sobre episodic)" in texto
    codigo, texto = _correr("--embeddings", "--falsa")
    assert codigo == 0, texto
    assert f"global: 16 copiados a {VIVA}, 0 ya estaban (0 metadatos actualizados), sin_reindexar 0" in texto
    viva = _leer(g, VIVA)
    assert viva["count"] == 16 and sorted(viva["ids"]) == sorted(vieja["ids"])
    assert _por_id(viva) == _por_id(vieja)
    assert {len(e) for e in viva["emb"]} == {1024}
    assert _leer(g) == vieja                                                # la vieja no se toca
    assert f"sin_reindexar 0 (procedencia sobre {VIVA})" in _correr("--vista")[1]


# --- el reindex a otro embedder: --embeddings (spec memoria por Ollama 2026-09-12) ---

VIVA = me.COLECCION_VIVA


def _por_id(leido: dict) -> dict:
    return {i: (d, m) for i, d, m in zip(leido["ids"], leido["docs"], leido["metas"])}


def test_embeddings_copia_la_vieja_a_la_viva_con_los_mismos_ids_documentos_y_metadatos(home):
    g = home / "global" / "chroma"
    antes = _leer(g)
    codigo, texto = _correr("--embeddings", "--falsa")
    assert codigo == 0, texto
    assert f"global: 6 copiados a {VIVA}, 0 ya estaban (0 metadatos actualizados), sin_reindexar 0" in texto
    assert f"projects/var-home-pedro-calipso: 2 copiados a {VIVA}" in texto
    assert "OJO" not in texto
    assert _leer(g) == antes                                   # la vieja no se toca
    viva = _leer(g, VIVA)
    assert sorted(viva["ids"]) == sorted(antes["ids"]) and viva["count"] == 6
    assert _por_id(viva) == _por_id(antes)
    assert all(len(e) == 1024 for e in viva["emb"])
    falsa = me.EmbedFalsa()
    for i, d, e in zip(viva["ids"], viva["docs"], viva["emb"]):
        esperado = falsa.embed([me.texto_para_embedding(d)])[0]
        assert max(abs(a - b) for a, b in zip(e, esperado)) < 1e-6, i
    # la viva quedo con la EF calipso_ollama persistida: el server la abre sin conflicto
    col = chromadb.PersistentClient(path=str(g)).get_collection(VIVA)
    assert col.configuration_json["embedding_function"]["name"] == "calipso_ollama"


def test_embeddings_es_idempotente_y_converge_los_metadatos_en_los_dos_ordenes(home):
    g = home / "global" / "chroma"
    # orden A: --embeddings, luego --aplicar (sobre la viva), luego --embeddings otra vez
    assert _correr("--embeddings", "--falsa")[0] == 0
    codigo, texto = _correr("--aplicar")
    assert codigo == 0 and "global: 4 episodios reindexados; count 6 -> 6" in texto
    assert f"(procedencia sobre {VIVA})" in texto
    despues_a = _leer(g, VIVA)
    assert _por_id(despues_a)["m1"][1]["procedencia"] == 1
    codigo, texto = _correr("--embeddings", "--falsa")
    assert codigo == 0 and f"global: 0 copiados a {VIVA}, 6 ya estaban (6 metadatos actualizados), sin_reindexar 0" in texto
    assert _leer(g, VIVA) == despues_a                         # update mergea: la procedencia queda
    assert _por_id(_leer(g))["m1"][1].get("procedencia") is None   # la vieja sigue sin marcar


def test_aplicar_antes_de_embeddings_tambien_converge(home):
    g = home / "global" / "chroma"
    codigo, texto = _correr("--aplicar")                       # no hay viva: cae a la vieja
    assert codigo == 0 and "global: 4 episodios reindexados" in texto
    assert "(procedencia sobre episodic)" in texto
    assert _por_id(_leer(g))["m1"][1]["procedencia"] == 1
    assert _correr("--embeddings", "--falsa")[0] == 0
    viva = _por_id(_leer(g, VIVA))
    assert viva["m1"][1] == {"ts": "2026-09-10T20:58:05", "route": "local", "kind": "chat",
                             "procedencia": 1, "ruta": "local"}
    assert "global: nada que escribir" in _correr("--aplicar")[1]


def test_vista_imprime_sin_reindexar_sin_embeber_ni_crear_la_viva(home):
    g = home / "global" / "chroma"
    # el parche vive en su propio contexto: un `monkeypatch.undo()` desharia
    # tambien el CALIPSO_HOME del fixture `home` y el reindex caeria al home real
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(me, "embeber", lambda *a, **k: (_ for _ in ()).throw(AssertionError("--vista embebio")))
        codigo, texto = _correr("--vista")
    assert codigo == 0
    assert f"global: 6 en episodic, sin {VIVA}, sin_reindexar 6 (procedencia sobre episodic)" in texto
    assert f"projects/var-home-pedro-calipso: 2 en episodic, sin {VIVA}, sin_reindexar 2" in texto
    assert me.ids_de(chromadb.PersistentClient(path=str(g)), VIVA) is None
    assert _correr("--embeddings", "--falsa")[0] == 0
    codigo, texto = _correr("--vista")
    assert f"global: 6 en episodic, 6 en {VIVA}, sin_reindexar 0 (procedencia sobre {VIVA})" in texto
    # un episodio nuevo en la vieja (un server viejo que siguio escribiendo) vuelve a contar
    chromadb.PersistentClient(path=str(g)).get_collection("episodic", embedding_function=None).add(
        ids=["m7"], documents=[CHAT_DATO], metadatas=[{"ts": "2026-09-12T10:00:00", "kind": "chat"}],
        embeddings=[[0.7, 0.2, 0.3]])
    assert "sin_reindexar 1" in _correr("--vista")[1]
    codigo, texto = _correr("--embeddings", "--falsa")
    assert f"global: 1 copiados a {VIVA}, 6 ya estaban" in texto and "sin_reindexar 0" in texto


def test_embeddings_se_niega_con_el_puerto_ocupado_y_no_admite_forzar(home, monkeypatch):
    # con el puerto LIBRE (el fixture deja CALIPSO_PORT=1) --forzar tambien se rechaza: no existe en este modo
    codigo, texto = _correr("--embeddings", "--falsa", "--forzar")
    assert codigo == 2 and "no admite --forzar" in texto
    assert me.ids_de(chromadb.PersistentClient(path=str(home / "global" / "chroma")), VIVA) is None
    escucha = socket.socket()
    escucha.bind(("127.0.0.1", 0))
    escucha.listen(1)
    monkeypatch.setenv("CALIPSO_PORT", str(escucha.getsockname()[1]))
    try:
        codigo, texto = _correr("--embeddings", "--falsa")
        assert codigo == 2 and "no admite --forzar" in texto
        codigo, texto = _correr("--embeddings", "--falsa", "--forzar")
        assert codigo == 2 and "no admite --forzar" in texto
        assert me.ids_de(chromadb.PersistentClient(path=str(home / "global" / "chroma")), VIVA) is None
    finally:
        escucha.close()


def test_embeddings_detecta_ids_aparecidos_durante_la_corrida(home, monkeypatch):
    g = home / "global" / "chroma"
    real = me.embeber

    def embeber_y_escribir_en_la_vieja(ef, textos, timeout=None):
        chromadb.PersistentClient(path=str(g)).get_collection("episodic", embedding_function=None).add(
            ids=["tarde"], documents=[CHAT_DATO], metadatas=[{"ts": "2026-09-12T10:00:00"}],
            embeddings=[[0.9, 0.2, 0.3]])
        monkeypatch.setattr(me, "embeber", real)        # una sola vez
        return real(ef, textos, timeout=timeout)
    monkeypatch.setattr(me, "embeber", embeber_y_escribir_en_la_vieja)
    codigo, texto = _correr("--embeddings", "--falsa")
    assert codigo == 0
    assert "OJO: aparecieron 1 ids en episodic durante la corrida" in texto
    assert "global: 6 copiados" in texto and "sin_reindexar 1" in texto


def test_embeddings_copia_sin_metadatos_y_deja_sin_reindexar_lo_que_no_tiene_documento(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    monkeypatch.setenv("CALIPSO_PORT", "1")
    col = _sembrar(tmp_path / "global" / "chroma", [])
    col.add(ids=["r1"], documents=[CHAT_DATO], embeddings=[[0.1, 0.2, 0.3]])       # sin meta
    col.add(ids=["r2"], embeddings=[[0.2, 0.2, 0.3]])                              # sin documento
    codigo, texto = _correr("--embeddings", "--falsa")
    assert codigo == 0 and "global: 1 copiados" in texto
    assert "sin_reindexar 1 (1 sin documento: no se copian)" in texto      # el que queda para siempre, dicho
    viva = _leer(tmp_path / "global" / "chroma", VIVA)
    assert viva["ids"] == ["r1"] and viva["metas"] == [None]
    # la segunda corrida: "ya estaban" son los ids presentes en la viva, aparte los metadatos actualizados
    codigo, texto = _correr("--embeddings", "--falsa")
    assert codigo == 0
    assert "global: 0 copiados" in texto and "1 ya estaban (0 metadatos actualizados)" in texto
    assert "sin_reindexar 1 (1 sin documento: no se copian)" in texto


# --- la ola de fix del cierre (punto 3): legible y sin vectores falsos ------------------

def test_embeddings_con_la_ef_falsa_exige_el_flag_falsa(home):
    """`embedder_por_env()` obedece un CALIPSO_EMBED_FALSA=1 heredado de la
    shell (la suite lo fija en conftest) y llenaria la viva de un home con
    vectores de hash sin decirlo: sin `--falsa` se niega con 2 y no escribe;
    `--falsa` lo permite a proposito y lo anuncia."""
    g = home / "global" / "chroma"
    codigo, texto = _correr("--embeddings")
    assert codigo == 2
    assert "CALIPSO_EMBED_FALSA=1: --embeddings no escribe vectores falsos en un home" in texto
    assert "env -u CALIPSO_EMBED_FALSA" in texto and "--falsa" in texto
    assert me.ids_de(chromadb.PersistentClient(path=str(g)), VIVA) is None
    codigo, texto = _correr("--embeddings", "--falsa")
    assert codigo == 0
    assert texto.index("embedder: EmbedFalsa (--falsa)") < texto.index("global: 6 copiados")


class _OllamaDoblada(me.OllamaEmbed):
    """Una EF real por firma (no es EmbedFalsa) que no postea: vectores fijos."""

    def embed(self, textos, timeout=None):
        return [[0.5] * self.dims for _ in textos]


def test_embeddings_anuncia_el_embedder_real_antes_del_bucle(home, monkeypatch):
    monkeypatch.setattr(me, "embedder_por_env",
                        lambda: _OllamaDoblada(url="http://127.0.0.1:11434", model="bge-m3:latest", dims=1024))
    codigo, texto = _correr("--embeddings")
    assert codigo == 0, texto
    assert "embedder: OllamaEmbed bge-m3:latest 1024 dims @ http://127.0.0.1:11434" in texto
    assert texto.index("embedder: OllamaEmbed") < texto.index("global: 6 copiados")


def test_embeddings_con_ollama_caido_lo_dice_sin_traceback_y_devuelve_3(home, monkeypatch):
    """Un EmbedError (Ollama caido, el modelo sin bajar) no sale como
    traceback: una linea con el motivo, que hacer (`ollama pull bge-m3`), que
    la vieja queda intacta y que se vuelve a correr; codigo 3."""
    class _Caida(me.OllamaEmbed):
        def embed(self, textos, timeout=None):
            raise me.EmbedError("POST http://127.0.0.1:11434/api/embed: HTTP Error 404: Not Found "
                                "{\"error\":\"model 'bge-m3:latest' not found, try pulling it first\"}")
    monkeypatch.setattr(me, "embedder_por_env", lambda: _Caida())
    g = home / "global" / "chroma"
    antes = _leer(g)
    codigo, texto = _correr("--embeddings")
    assert codigo == 3, texto
    assert "global: no se pudo embeber por Ollama (POST http://127.0.0.1:11434/api/embed: HTTP Error 404" in texto
    assert "try pulling it first" in texto
    assert "si el modelo no esta: ollama pull bge-m3" in texto
    assert "la coleccion vieja queda intacta, volver a correr --embeddings" in texto
    assert _leer(g) == antes
    assert "projects/var-home-pedro-calipso" not in texto        # corta en el primer ambito que falla
