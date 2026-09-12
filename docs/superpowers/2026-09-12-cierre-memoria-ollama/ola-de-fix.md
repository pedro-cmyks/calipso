# Ola de fix del cierre de feat/memoria-ollama (unica; 2026-09-12)

Rama `feat/memoria-ollama` en el WORKTREE `/var/home/pedro/calipso/.claude/worktrees/memoria-ollama`, HEAD
`9c32f72`. Cinco revisores (memoria, server, experimentos, lente del spec, lente de riesgo) mas Codex. Sin
criticos. Todo se arregla en ESTA ola, en orden, con TDD donde hay test, suite completa antes de cada
commit (`cd <worktree> && nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q
--ignore=test_chat_live.py -p no:cacheprovider; echo EXIT=$?`, 0 failed), commits con rutas explicitas y el
trailer. NO se corre el smoke ni se llama a Ollama (lo corre el controlador). Las lineas citadas son de
`9c32f72`: verifica con `grep -n`. Los rulings son del controlador; no se rediscuten.

## 1. [IMPORTANTE] `_post_embed` conserva el cuerpo del error de Ollama

`calipso/memoria_embed.py:117-128`: `str(HTTPError)` es solo "HTTP Error 404: Not Found" y el cuerpo
`{"error": "model 'bge-m3:latest' not found, try pulling it first"}` se pierde: la fila `recall_fallo`,
`ultimo_recall_fallo` y `remember_fallo` no dicen por que. Arreglo: atrapar `urllib.error.HTTPError`
ANTES del `except Exception`, leer `e.read()[:300]` (decode `errors="replace"`) y levantar
`EmbedError(f"POST {url}: {e} {cuerpo}")`. Idem con un 200 con `{"error": ...}` sin `embeddings`: el
mensaje incluye `datos["error"]`. Tests en `test_memoria_embed.py` con `_urlopen_falso` que levante
`HTTPError(url, 404, "Not Found", {}, io.BytesIO(b'{"error":"model not found"}'))` (`match="model not
found"`) y con un 200 `{"error": "x"}`.

## 2. [IMPORTANTE] `keep_alive_embed` mira la memoria DISPONIBLE fresca y si el 7b esta residente

Ruling del ledger: con el 7b residente la medicion sale `holgada` por la memoria EFECTIVA y el embedder se
queda 5 min al lado del 7b (el smoke lo midio: 327 MB libres, `psi_mem_full10` 5,19). Y leer
`carga._ultima` no alcanza: la ultima medicion puede ser la de `_decide` ANTES de que el 7b cargara. Arreglo
en `calipso/carga.py`: `UMBRALES["EMBED_RESIDENTE_MB"] = 2500` (el embedder de 1219 MB mas 1 GB de margen);
`keep_alive_embed(nivel, disponible_mb=None, modelos_cargados=None)`: si `disponible_mb` es None lee
`MemAvailable` FRESCO y barato de `/proc/meminfo` (el lector `_leer_proc`/`_meminfo` que ya existe;
microsegundos, sin `/api/ps`); si `modelos_cargados` es None toma `_ultima.modelos_cargados` (o `[]`);
devuelve `0` si `disponible_mb < EMBED_RESIDENTE_MB` o si el modelo del chat (`CONFIG["local"]["model"]`,
comparado con `mismo_modelo`) esta en `modelos_cargados`; si no, la tabla por nivel de hoy (`holgada`
`"5m"`, `justa`/`cargada` `0`). Si la lectura de `/proc` falla, la tabla por nivel (fail-open). En
`OllamaEmbed.embed` no cambia la llamada si la firma toma defaults. Docstring con el porque y los numeros.
Tests en `test_carga.py` (con `leer` inyectado): holgada + 1800 disponibles -> 0; holgada + 4000 -> "5m";
holgada + 7000 + el 7b listado -> 0; sin lectura -> tabla. Test en `test_memoria_embed.py`: el payload lleva
`keep_alive: 0` con esa lectura sembrada.

## 3. [IMPORTANTE] `memoria_reindex --embeddings` legible y sin vectores falsos

`calipso/memoria_reindex.py:295-299`: (a) `EmbedError` sale sin atrapar (traceback); envolver
`reindexar_embeddings` en `except memoria_embed.EmbedError as e` que imprima `<ambito>: no se pudo embeber
por Ollama ({e}); si el modelo no esta: ollama pull bge-m3; la coleccion vieja queda intacta, volver a
correr --embeddings` y devuelva 3. (b) `embedder_por_env()` obedece un `CALIPSO_EMBED_FALSA=1` heredado de
la shell y llenaria la viva con vectores de hash sin decirlo: con `--embeddings`, si la EF es `EmbedFalsa`
imprimir `CALIPSO_EMBED_FALSA=1: --embeddings no escribe vectores falsos en un home (usar env -u
CALIPSO_EMBED_FALSA, o --falsa a proposito)` y devolver 2; un flag explicito `--falsa` lo permite (los
tests que reindexan con la falsa lo pasan). (c) Imprimir antes del bucle la linea `embedder: OllamaEmbed
bge-m3:latest 1024 dims @ <url>` (o `EmbedFalsa (--falsa)`). (d) Los conteos: "ya estaban" = ids
presentes en la viva (`presentes & ids_antes`), aparte "metadatos actualizados"; los documentos sin texto
se cuentan y la linea dice `sin_reindexar K (J sin documento: no se copian)`. Tests en
`test_memoria_reindex.py` para (a) con una EF que levanta EmbedError, (b) con la falsa sin `--falsa` ->
2 y con `--falsa` -> corre, (d) los conteos.

## 4. [IMPORTANTE] El `finally` del smoke descarga los dos modelos

`experimentos/memoria_smoke.py:520-522`: solo `server.apagar()` y `proxy.cortar()`; en las dos corridas la
descarga de bge-m3 y del 7b la hizo el implementador a mano y el informe lo presenta como parte del smoke.
Arreglo: tras `server.apagar()`, `carga.ollama_evict(EMBED, embedding=True)` y `carga.ollama_evict(MODELO)`
(directo a 11434, no por el proxy), `esperar_ps(lambda l: not l, 30)` y una linea `[nota]` con `/api/ps`.
En `docs/superpowers/2026-09-12-smoke-memoria.md` decir que en las dos corridas la descarga fue a mano y
que el script lo hace desde este commit. Piezas secas del smoke verificadas (`--help`, `ast.parse`).

## 5. [IMPORTANTE, Codex] El remember de fondo con tope y cierre ordenado

`calipso/server.py:2440-2444` (`_en_fondo`) y `:4856-4868`: cada turno crea una tarea de fondo sin limite
(un embed puede esperar 120 s): dos turnos seguidos acumulan POSTs concurrentes. Arreglo: un
`asyncio.Semaphore(2)` a nivel de modulo que la corrutina de `_recordar` adquiere antes del `to_thread`
(el `done` ya salio: no afecta la latencia visible); en el shutdown del app (el hook de lifespan/shutdown
que ya exista, o `@app.on_event("shutdown")` si es lo que usa el server) esperar `_TAREAS_DE_FONDO` con
`asyncio.wait(..., timeout=10)` y anotar `remember_pendiente: N` si vencio. Test por el harness: tres
turnos seguidos en la misma conexion con un embedder lento (0,3 s) -> los tres `guardados` al final y
nunca mas de 2 en vuelo (contador en el doble).

## 6. [IMPORTANTE] Docs del despliegue: la vuelta atras y el orden

`docs/superpowers/2026-09-12-smoke-memoria.md:161-163` y el estado del proyecto: (a) el comando de vuelta
atras esta roto (`pip install sentence-transformers --index-url https://download.pytorch.org/whl/cpu`
reemplaza PyPI): corregir a `pip install torch --index-url https://download.pytorch.org/whl/cpu && pip
install sentence-transformers`; (b) el orden del despliegue pasa a: merge -> reindex del home real
(`--vista`, `--embeddings`, evict) -> reinicio -> verificar `GET /api/memory` (`sin_reindexar` en 0,
`recall_ok` true tras un turno de Pedro) -> recien entonces `pip uninstall`; (c) documentar el rollback
RAPIDO sin checkout ni pip: `CALIPSO_EMBED_URL=http://127.0.0.1:1` en el entorno del server deja la
memoria en fail-open (recall_fallo inmediato, el turno sale entero) mientras se decide; y que
`~/.cache/huggingface` (533 MB, MiniLM adentro) no se borre. Tambien en `AGENTS.md:246`, el comentario de
`_startup_warm` (`server.py:8863`) y el docstring de `calipso/aduana.py:11-12` (el ejemplo cita el cruce de
embeddings que ya no existe: usar el de whisper).

## 7. [IMPORTANTE, lente del spec] El banco anota el ruido intra-corpus

`experimentos/recall_banco.py:279-280`: el margen se mide contra temas AUSENTES; el ruido de siempre es
otro episodio del mismo corpus (63 hits de otro topico en el top-4 de las positivas; con 0,476 pasan
22/63, con MiniLM a 0,30 pasaban 45/63). Arreglo: sumar la metrica `max score de otro topico en el top-4
de las positivas` (y cuantos pasan el umbral sugerido) por condicion, calculada del JSONL en `--informe`
(sin Ollama), y regenerar el MD con `--informe` sobre el JSONL commiteado. Anotarla junto a los umbrales
en `server.py`/`fuentes.py` (siguen PROVISORIOS). Test seco del calculo.

## 8. [MENOR] Menores baratos (un commit)

- `calipso/memoria_embed.py:237-243` (`ids_de`): `warnings.catch_warnings()` ignorando el `UserWarning`
  "Could not reconstruct embedding function" (aparecera en cada arranque cuando torch ya no este).
- Docstrings viejos que citan MiniLM/huggingface: `test_memoria_carta.py`, `test_abismo_memoria_recall.py`,
  `test_memoria_ambito.py:15` si quedaron; `memoria_reindex.py` (el parrafo de `get_collection("episodic")`
  y `HF_HUB_OFFLINE`).

## Lo que NO se toca (para el addendum del spec, lo escribe el controlador)

- El fixture con episodios sinteticos (Codex lo leyo como datos personales: son los personajes de los smokes,
  y las consultas de los episodios reales van por `--reales` fuera del repo).
- Los umbrales 0,476 / 0,44 siguen provisorios con env; se re-miden cuando el corpus crezca.

## Reporte

Escribi `<worktree>/.superpowers/sdd/2026-09-12-memoria-ollama/ola-de-fix-report.md`: por punto, que
cambiaste (archivo:linea nuevas), el test rojo->verde, la suite con conteo y EXIT, desvios y dudas. Salida
estructurada: status, base_sha (9c32f72), head_sha, commits, tests, concerns, report_file.
