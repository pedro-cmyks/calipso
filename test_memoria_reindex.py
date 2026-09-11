"""El reindexado sobre un home temporal (spec 2026-09-11, secciones 3 y 5):
`--vista` no escribe; `--aplicar` conserva ids, documentos, embeddings y
cantidad, preserva las claves viejas y agrega `procedencia` y `ruta`; es
idempotente; cuenta lo que no parsea; se niega con el puerto ocupado y
sigue con `--forzar`. Al final, sobre una copia del fixture real del porton.

Los chromas de prueba se arman SIN modelo (embeddings explicitos): asi el
test tarda medio segundo y no depende del cache de HuggingFace. El del
fixture real trae la funcion de embeddings persistida y `update` la carga
(offline, del cache; ~5 s la primera vez en el proceso)."""
from __future__ import annotations

import io
import pathlib
import shutil
import socket

import chromadb
import pytest

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


def _leer(chroma_dir: pathlib.Path) -> dict:
    col = chromadb.PersistentClient(path=str(chroma_dir)).get_collection("episodic")
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
    """El fixture del porton tal cual (funcion de embeddings persistida): la
    vista da los numeros del spec y aplicar deja 16/16 con procedencia."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CALIPSO_PORT", "1")
    shutil.copytree(FIXTURE, tmp_path / "home")
    antes = _leer(tmp_path / "home" / "global" / "chroma")
    codigo, texto = _correr("--vista")
    assert codigo == 0
    assert ("global: 16 episodios, 0 con procedencia, 16 parsean como chat, "
            "0 kind=chat que NO parsean, 0 no chat, 5 sin_dato, 0 basura, 0 raros "
            "-> 16 por reindexar") in texto
    assert "projects/var-home-pedro-calipso: 0 episodios" in texto
    codigo, texto = _correr("--aplicar")
    assert codigo == 0 and "global: 16 episodios reindexados; count 16 -> 16" in texto
    despues = _leer(tmp_path / "home" / "global" / "chroma")
    assert (despues["ids"], despues["docs"], despues["emb"]) == (antes["ids"], antes["docs"], antes["emb"])
    assert all(m["procedencia"] == 1 and m["ruta"] == "local" and m["route"] == "local"
               for m in despues["metas"])
    assert "global: nada que escribir" in _correr("--aplicar")[1]
