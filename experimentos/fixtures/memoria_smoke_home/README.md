# Fixture: el home del smoke del abismo (2026-09-10), con las dos colecciones (2026-09-12)

Copia del `CALIPSO_HOME` temporal del smoke `docs/superpowers/2026-09-10-smoke-abismo-system-podado.md`
(sin token): `global/` (core + chroma con los episodios reales del 7b, contaminados a proposito con
no-saber y confabulaciones), `chats.json` (tres charlas viejas sembradas + los turnos del smoke) y
`projects/`. Es el fixture del porton de la memoria con procedencia
(`docs/superpowers/specs/2026-09-11-memoria-con-procedencia-design.md`, seccion 5): el porton lo RESTAURA
antes de cada condicion. No editar a mano.

Desde la memoria por Ollama (`docs/superpowers/specs/2026-09-12-memoria-embeddings-ollama-design.md`,
ruling 8.12) `global/chroma/chroma.sqlite3` trae DOS colecciones: `episodic` (MiniLM, 384 dims, la EF
`sentence_transformer` persistida, 16 episodios, sin `procedencia`) y `episodic-bge-m3` (bge-m3 por
Ollama, 1024 dims, la EF `calipso_ollama` persistida, los MISMOS 16 ids, documentos y metadatos).
`projects/var-home-pedro-calipso/chroma` trae las dos vacias. Un server de main (MiniLM) abre la vieja y
uno de esta rama abre la viva: el porton puede medir "antes" y "despues" sobre el mismo home mientras
sentence-transformers siga instalado (la condicion "antes" muere con el uninstall).

Receta (se genero UNA vez, con Ollama real y `bge-m3:latest`, el 2026-09-12; `test_memoria_fixture.py`
fija que las dos colecciones coinciden y que los vectores no son los de `EmbedFalsa`):

    CALIPSO_HOME=$(mktemp -d) .venv/bin/python -m calipso.carga --esperar
    COPIA=$(mktemp -d)/home && cp -r experimentos/fixtures/memoria_smoke_home "$COPIA"
    env -u CALIPSO_EMBED_FALSA CALIPSO_HOME="$COPIA" CALIPSO_PORT=1 .venv/bin/python -m calipso.memoria_reindex --embeddings
    rm -rf experimentos/fixtures/memoria_smoke_home/{global,projects/var-home-pedro-calipso}/chroma
    cp -r "$COPIA/global/chroma" experimentos/fixtures/memoria_smoke_home/global/chroma
    cp -r "$COPIA/projects/var-home-pedro-calipso/chroma" experimentos/fixtures/memoria_smoke_home/projects/var-home-pedro-calipso/chroma

Solo `--embeddings`, nunca `--aplicar`: `test_memoria_reindex.py` mide la procedencia sobre la viva
("16 por reindexar"). Si cambia el texto embebido (`memoria_embed.PALABRAS_RESPUESTA`) o el modelo, se
regenera con la misma receta.
