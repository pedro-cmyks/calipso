# Cierre de la rama feat/memoria-ollama (2026-09-12)

- `ledger.md`: la ejecucion entera (preflight, 4 tasks en un worktree, los rulings, el cierre).
- `revision-final-y-lentes.md`: la revision final por tres areas, la lente de fidelidad al spec, la lente de riesgo del despliegue y Codex gpt-5.5 headless. Sin criticos.
- `ola-de-fix.md` y `ola-de-fix-reporte.md`: los 8 puntos de la unica ola de fix y el reporte del implementador (9 commits `9c32f72..13384f5`), re-review 8/8; el residuo lo cerro el controlador en `cfa0885`.
- El smoke en vivo: `../2026-09-12-smoke-memoria.md` (tres corridas; la 3 con el codigo final: 35 ok). El banco de recall: `experimentos/recall_banco_resultados.md`. El spec quedo con el addendum (seccion 9, rulings 16-22).

## Lo que queda para Pedro

1. **El server ya no carga torch:** la memoria embebe por Ollama con `bge-m3` (pregunta mas 150 palabras de respuesta). Con el 7b residente el embedder embebe y suelta (ruling 16); sin el 7b se queda 5 minutos.
2. **Umbrales provisorios** (0,476 en el turno, 0,44 en el abismo; antes 0,30 y 0,20) medidos con un banco de 21 documentos: mismos aciertos, la mitad de recuerdos fuera de tema, pero el corte queda cerca del ruido (ruling 17). Vuelta atras por env: `CALIPSO_RECALL_MIN_SCORE`, `CALIPSO_RECALL_UMBRAL`. Se re-miden cuando el corpus crezca.
3. **Vuelta atras rapida** si bge-m3 falla: `CALIPSO_EMBED_URL=http://127.0.0.1:1` en el entorno del server (memoria en fail-open, el turno sale entero). Vuelta completa: checkout de main mas `pip install torch --index-url https://download.pytorch.org/whl/cpu && pip install sentence-transformers`; la coleccion vieja `episodic` no se borra.
4. **El `pip uninstall`** (~5 GB: torch con CUDA, nvidia, triton, transformers, sentence-transformers y huerfanos) lo hace el controlador DESPUES de ver a bge-m3 funcionando sobre el home real; `~/.cache/huggingface` no se toca.
5. **Nada se empujo a GitHub.** El merge a main es local; el push es de Pedro.
