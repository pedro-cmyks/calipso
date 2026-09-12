"""El fixture del smoke trae las DOS colecciones (spec memoria por Ollama
2026-09-12, ruling 8.12): `episodic` (MiniLM, 384 dims) y `episodic-bge-m3`
(1024 dims, generada UNA vez con `memoria_reindex --embeddings` y Ollama real)
con los mismos ids, documentos y metadatos; `sin_reindexar` 0; los vectores
son de bge-m3 (no de EmbedFalsa); y la suite abre el fixture con EmbedFalsa
sin conflicto (mismo name()). Siempre sobre una COPIA: chroma escribe al abrir."""
from __future__ import annotations

import pathlib
import shutil

import chromadb

from calipso import memoria_embed as me
from calipso import memory

FIXTURE = pathlib.Path(__file__).resolve().parent / "experimentos" / "fixtures" / "memoria_smoke_home"


def _copia(tmp_path, sub: str):
    destino = tmp_path / sub.replace("/", "_")
    shutil.copytree(FIXTURE / sub, destino)
    return chromadb.PersistentClient(path=str(destino))


def _nombres(cli) -> list[str]:
    return sorted(c if isinstance(c, str) else c.name for c in cli.list_collections())


def test_global_trae_las_dos_colecciones_con_los_mismos_ids_documentos_y_metadatos(tmp_path):
    cli = _copia(tmp_path, "global/chroma")
    assert _nombres(cli) == sorted(["episodic", me.COLECCION_VIVA])
    vieja = cli.get_collection("episodic", embedding_function=None)
    viva = cli.get_collection(me.COLECCION_VIVA, embedding_function=None)
    a = vieja.get(include=["documents", "metadatas", "embeddings"])
    b = viva.get(include=["documents", "metadatas", "embeddings"])
    assert len(a["ids"]) == len(b["ids"]) == 16
    por_id_a = {i: (d, m) for i, d, m in zip(a["ids"], a["documents"], a["metadatas"])}
    por_id_b = {i: (d, m) for i, d, m in zip(b["ids"], b["documents"], b["metadatas"])}
    assert por_id_a == por_id_b
    assert all("procedencia" not in m for m in b["metadatas"])      # solo --embeddings (decision 17)
    assert {len(e) for e in a["embeddings"]} == {384} and {len(e) for e in b["embeddings"]} == {1024}
    assert me.sin_reindexar(cli) == 0
    ef = viva.configuration_json["embedding_function"]
    assert ef["name"] == "calipso_ollama" and ef["config"]["model"] == "bge-m3:latest" and ef["config"]["dims"] == 1024


def test_los_vectores_del_fixture_son_de_bge_m3_y_no_de_la_falsa(tmp_path):
    cli = _copia(tmp_path, "global/chroma")
    viva = cli.get_collection(me.COLECCION_VIVA, embedding_function=None)
    b = viva.get(limit=1, include=["documents", "embeddings"])
    real = [float(x) for x in b["embeddings"][0]]
    falso = me.EmbedFalsa().embed([me.texto_para_embedding(b["documents"][0])])[0]
    assert max(abs(x - y) for x, y in zip(real, falso)) > 0.01, "el fixture se genero con CALIPSO_EMBED_FALSA=1"
    assert abs(sum(x * x for x in real) - 1.0) < 0.01               # Ollama devuelve normalizados


def test_el_proyecto_trae_la_viva_vacia(tmp_path):
    cli = _copia(tmp_path, "projects/var-home-pedro-calipso/chroma")
    assert _nombres(cli) == sorted(["episodic", me.COLECCION_VIVA])
    assert cli.get_collection(me.COLECCION_VIVA, embedding_function=None).count() == 0
    assert me.sin_reindexar(cli) == 0


def test_la_suite_abre_el_fixture_con_la_falsa_sin_conflicto(tmp_path, monkeypatch):
    """Lo que hace la suite (EmbedFalsa) sobre lo que genero la EF real: mismo
    name(), sin `ValueError ... conflict`; count 16, sin_reindexar 0, y un
    recall que consulta (con la falsa el orden no significa nada)."""
    home = tmp_path / "home"
    shutil.copytree(FIXTURE, home)
    monkeypatch.setattr(memory, "CALIPSO_HOME", home)
    m = memory.Memory(project_root=str(tmp_path / "repo"))
    assert isinstance(m._embed, me.EmbedFalsa)
    assert m.glob.count() == 16 and m.sin_reindexar()["global"] == 0
    assert len(m.recall("hola, que libro te conte que empece?", n=4)) == 4 and m.recall_ok is True
