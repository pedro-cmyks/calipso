# Ola de fix del cierre de feat/memoria-ollama: reporte del implementador (2026-09-12)

Worktree `/var/home/pedro/calipso/.claude/worktrees/memoria-ollama`, rama `feat/memoria-ollama`.
Base `9c32f72` (verificado con `git rev-parse HEAD` antes de tocar nada). HEAD final `13384f5`.
Nueve commits (los 8 puntos mas un ajuste del self-review), cada uno con la suite completa en verde
antes (`nice -n 19 .venv/bin/python -m pytest -q --ignore=test_chat_live.py -p no:cacheprovider`) y
con el trailer. No se corrio el smoke ni se llamo a Ollama; ningun test lo hace (la suite lo verifica
con `urlopen` doblado y `CALIPSO_EMBED_FALSA=1`). No se toco `/var/home/pedro/calipso`, `main`,
`~/.calipso` ni el server real; ningun push.

## Commits

| # | sha | punto | mensaje |
|---|---|---|---|
| 1 | `bae9e64` | 1 | fix(memoria): el EmbedError conserva el cuerpo del error de Ollama |
| 2 | `3640f6e` | 2 | fix(carga): keep_alive_embed mira la memoria disponible fresca y si el 7b esta residente |
| 3 | `3c14ce9` | 3 | fix(memoria_reindex): --embeddings legible y sin vectores falsos |
| 4 | `788ba5f` | 4 | fix(smoke): el finally del smoke de la memoria descarga los dos modelos |
| 5 | `a7d49e8` | 5 | fix(server): el remember de fondo con tope de dos en vuelo y cierre ordenado |
| 6 | `3415c06` | 6 | docs(memoria): el despliegue en orden, la vuelta atras corregida y la rapida |
| 7 | `7ad6843` | 7 | feat(banco): el banco de recall anota el ruido intra-corpus |
| 8 | `a4bc79e` | 8 | fix(memoria): ids_de calla el aviso de chroma por la EF vieja que no reconstruye |
| 9 | `13384f5` | self-review | fix(memoria_reindex): el nombre para ollama pull es el del modelo sin :latest |

## Suite

Base (`9c32f72`, antes de tocar nada): EXIT=0. Antes de cada commit:

| antes del commit | resultado |
|---|---|
| 1 y 2 (una corrida sobre el arbol con los dos puntos; el commit 1 se hizo con `test_memoria_embed.py` sin las piezas del punto 2 y el 2 con el archivo completo, los dos arboles consistentes) | 1935 passed, EXIT=0 (125 s) |
| 3 | 1938 passed, EXIT=0 |
| 4 | 1938 passed, EXIT=0 |
| 5 | 1940 passed, EXIT=0 |
| 6 | 1940 passed, EXIT=0 |
| 7 | 1942 passed, EXIT=0 |
| 8 | 1943 passed, EXIT=0 |
| 9 | 1943 passed, EXIT=0 (127 s) |

0 failed en todas; 4-6 warnings (las de siempre: `asyncio.iscoroutinefunction` de chroma y el
`on_event` deprecado de FastAPI, que es el estilo que ya usaba el server para el startup).

## Por punto

### 1. `_post_embed` conserva el cuerpo del error de Ollama (`bae9e64`)

- `calipso/memoria_embed.py:119` `CUERPO_ERROR_CHARS = 300`; `:136-142` atrapa `urllib.error.HTTPError`
  ANTES del `except Exception`, lee `e.read()[:300]` (decode `errors="replace"`, y si el read falla,
  cuerpo vacio) y levanta `EmbedError(f"POST {url}: {e} {cuerpo}")`. `:177-180`: un 200 con
  `{"error": ...}` sin `embeddings` suma `(Ollama: <error>)` al mensaje "esperaba N vectores".
  `import urllib.error` agregado.
- Test rojo -> verde: `test_memoria_embed.py:251` `test_un_http_error_conserva_el_cuerpo_del_error_de_ollama`
  (HTTPError 404 con `io.BytesIO(b'{"error":"model not found, try pulling it first"}')`, `match="model not
  found"`, mas "HTTP Error 404" y "POST http://" en el mensaje, `en_uso` en 0; y un 500 con cuerpo de 1000
  bytes no decodificable -> mensaje < 400 chars). El test viejo del 200 con `{"error": "model not found"}`
  ahora exige `match="model not found"` (antes solo `raises`). Rojo verificado: el mensaje era
  `POST http://localhost:11434/api/embed: HTTP Error 404: Not Found`.

### 2. `keep_alive_embed` mira la memoria DISPONIBLE fresca y si el 7b esta residente (`3640f6e`)

- `calipso/carga.py:138` `UMBRALES["EMBED_RESIDENTE_MB"] = 2500` (comentario con el porque).
  `:473-518` `keep_alive_embed(nivel, disponible_mb=None, modelos_cargados=None, *, leer=None,
  modelo_chat=None)`: si `disponible_mb` es None lee `MemAvailable` fresco con `_meminfo(_leer_proc(
  "/proc/meminfo"))` (sin `/api/ps`); si `modelos_cargados` es None toma `_ultima.modelos_cargados`
  (o `[]`); `modelo_chat` sale de `_modelo_configurado()` (`config.json` del CALIPSO_HOME,
  `local.model`); devuelve 0 si `disponible_mb < 2500` o si el modelo del chat esta en la lista
  (`mismo_modelo`, normaliza `:latest`); si no, la tabla por nivel de hoy. Si `/proc` no se lee,
  `disponible_mb` queda None y decide la tabla (fail-open). Docstring con el ruling, los numeros del
  smoke (327 MB de swap libres, psi_mem_full10 5,19; 1219 + 1 GB) y por que la lectura es fresca (la
  ultima medicion puede ser la de `_decide`, anterior a la carga del 7b). `OllamaEmbed.embed` no cambia.
- Tests: `test_carga.py:702` `test_keep_alive_embed_mira_la_memoria_disponible_fresca_y_si_el_7b_esta_residente`
  (con `leer` inyectado: holgada + 1800 -> 0; + 4000 -> "5m"; `disponible_mb=2500` -> "5m"; 7000 con
  `qwen2.5:7b` o `qwen2.5:7b:latest` listado -> 0, con `bge-m3:latest` listado -> "5m"; sin lista
  explicita toma la de `carga.medir(...)` con el 7b en `/api/ps` -> 0 y tras `olvidar()` -> "5m"; sin
  lectura de /proc -> tabla: holgada "5m", justa 0). El test viejo `:686` pasa `disponible_mb=7000,
  modelos_cargados=[]` para seguir siendo la tabla pura. `test_memoria_embed.py:183`
  `test_embed_suelta_el_modelo_si_la_memoria_disponible_no_alcanza_o_el_7b_esta_cargado`: el payload
  lleva `keep_alive: 0` con 1800 MB sembrados en `/proc/meminfo`, "5m" con 7000, y 0 de nuevo tras una
  medicion con el 7b listado. Rojo verificado (TypeError por la firma y "5m" con 1800).
- Nota: el fixture autouse de `test_memoria_embed.py` (`:47` `_sembrar_meminfo`) ahora siembra
  `carga._leer_proc` con 7377 MB disponibles para todo el archivo: sin eso, las aserciones de
  `keep_alive "5m"` dependerian de la RAM libre de la maquina que corre la suite.

### 3. `memoria_reindex --embeddings` legible y sin vectores falsos (`3c14ce9`, `13384f5`)

- `calipso/memoria_reindex.py:303` flag `--falsa`. `:329-338`: con `--embeddings`, si
  `embedder_por_env()` es `EmbedFalsa` y no vino `--falsa`, imprime `CALIPSO_EMBED_FALSA=1: --embeddings
  no escribe vectores falsos en un home (usar env -u CALIPSO_EMBED_FALSA, o --falsa a proposito)` y
  devuelve 2 (despues del chequeo del puerto y de `--forzar`, para no tapar esos mensajes); si pasa,
  imprime antes del bucle `embedder: OllamaEmbed bge-m3:latest 1024 dims @ <url>` o `embedder:
  EmbedFalsa (--falsa)` (`_describir_embedder`, `:275`). `:343-351`: `reindexar_embeddings` envuelto en
  `except memoria_embed.EmbedError as e` que imprime `<ambito>: no se pudo embeber por Ollama ({e}); si
  el modelo no esta: ollama pull bge-m3; la coleccion vieja queda intacta, volver a correr --embeddings`
  y devuelve 3 (corta en el primer ambito que falla). `:185,203`: `ya_estaban = len(presentes &
  ids_antes)`, `actualizados` aparte, `sin_documento` contado; `_linea_embeddings` (`:261`) imprime
  `N copiados a <viva>, M ya estaban (K metadatos actualizados), sin_reindexar J (I sin documento: no
  se copian)` + el OJO de los aparecidos. Docstring del modulo: los usos nuevos y el parrafo viejo de
  `get_collection("episodic")`/`HF_HUB_OFFLINE` reescrito (ya no habla de la suite con el hub online ni
  del modelo cargado en el proceso).
- Tests (`test_memoria_reindex.py`): `:386` la falsa sin `--falsa` -> 2 con el mensaje y sin crear la
  viva; con `--falsa` -> 0 y la linea `embedder: EmbedFalsa (--falsa)` antes del primer ambito; `:409`
  la linea del embedder real (una `OllamaEmbed` doblada que no postea); `:418` una EF que levanta
  `EmbedError` -> 3, la linea con el motivo, `ollama pull bge-m3`, la vieja intacta y sin seguir al
  segundo ambito; `:366` los conteos (`sin_reindexar 1 (1 sin documento: no se copian)` y en la
  segunda corrida `1 ya estaban (0 metadatos actualizados)`). Todas las corridas de la suite con
  `--embeddings` pasan `--falsa`; los textos esperados dicen `0 ya estaban (0 metadatos actualizados)`
  y `6 ya estaban (6 metadatos actualizados)`. Rojo verificado (13 fallos: el flag no existia).
- `13384f5` (self-review): la sugerencia `ollama pull` usaba `embed_tag(ef.model)`, que sanea el nombre
  para la coleccion (un `nomic-embed-text:v1.5` daria un nombre inexistente); pasa al nombre del modelo
  sin `:latest`.
- El smoke (`reindex_sobre_copia`) y la receta del README del fixture ya corrian sin
  `CALIPSO_EMBED_FALSA` en el entorno: no cambian.

### 4. El `finally` del smoke descarga los dos modelos (`788ba5f`)

- `experimentos/memoria_smoke.py:415` `descargar_modelos(R)`: `carga.ollama_evict(EMBED,
  embedding=True)`, `carga.ollama_evict(MODELO)` (directo a `carga.OLLAMA` = 11434, no por el proxy),
  `esperar_ps(lambda l: not l, 30)` y `R.nota("Z descarga de los dos modelos", ...)` con `/api/ps`; una
  excepcion ahi deja una nota y no tapa el resultado. Llamado en `:543` tras `server.apagar()` y
  `proxy.cortar()`. Paso `Z` en el docstring.
- Piezas secas: `ast.parse` ok, `--help` ok (con CALIPSO_HOME temporal), y `descargar_modelos` con
  `carga.ollama_evict` y `ps` doblados: `[('bge-m3:latest', True), ('qwen2.5:7b', False)]` y la nota.
  No hay test en la suite para el smoke (no lo habia): sin rojo/verde en este punto.
- `docs/superpowers/2026-09-12-smoke-memoria.md:21-24`: en las dos corridas la descarga fue a mano; el
  script lo hace desde este commit.

### 5. El remember de fondo con tope y cierre ordenado (`a7d49e8`)

- `calipso/server.py:2443` `REMEMBER_EN_VUELO_MAX = 2`; `:2456` `_semaforo_remember()` devuelve un
  `asyncio.Semaphore(2)` atado al loop que corre (se recrea si el loop cambia: la suite levanta un loop
  por TestClient y un Semaphore se ata al loop en la primera espera; en produccion hay uno solo).
  `:4901`: `_recordar` hace `async with _semaforo_remember():` antes del `to_thread` (el `done` ya
  salio). `:2467` `_esperar_fondo_al_apagar(plazo=10)`: `asyncio.wait(vivas, timeout=plazo)` y la fila
  `kind: memoria, accion: remember_pendiente, n` si vencio. `:8927` `@app.on_event("shutdown")
  _shutdown_fondo` (el mismo estilo que el `startup` que ya habia; verificado que queda registrado en
  `app.router.on_shutdown`).
- Tests (`test_memoria_server.py`): `:186` tres turnos seguidos en la misma conexion con un doble cuyo
  `remember` cuenta en vuelo y se retiene por una puerta; tras el tercer `done` y 0,3 s: 2 entradas y
  max 2 en vuelo, `recordado == []`; se abre la puerta, `esperar_fondo`, los tres `guardados` en orden,
  max 2, 3 entradas. Rojo verificado: `(3, 3)` sin el semaforo. `:231` el shutdown: una tarea rapida
  -> sin fila; dos eternas con plazo 0,05 -> fila `remember_pendiente` con `n: 2`.
- Desvio menor: el brief decia "embedder lento (0,3 s)"; el doble espera una puerta (determinista) y el
  test espera 0,3 s antes de mirar el contador, que es lo mismo sin depender de cuanto tarda un turno del
  harness.

### 6. Docs del despliegue (`3415c06`)

- `docs/superpowers/2026-09-12-smoke-memoria.md:154-193` "Pendiente del controlador: el despliegue, en
  este orden": merge -> reindex del home real (`--vista`, `env -u CALIPSO_EMBED_FALSA ... --embeddings`,
  evict de bge-m3) -> reinicio -> verificar `GET /api/memory` (`sin_reindexar` 0, `recall_ok` true tras
  un turno de Pedro) -> recien entonces `pip uninstall` (lista del spec, chequeo post-uninstall, VmRSS);
  `~/.cache/huggingface` (533 MB, MiniLM adentro) no se borra. Vueltas atras: la RAPIDA
  (`CALIPSO_EMBED_URL=http://127.0.0.1:1` -> fail-open, `recall_fallo` inmediato) y la completa con el
  comando corregido (`pip install torch --index-url .../whl/cpu && pip install sentence-transformers`,
  con la explicacion de por que el de antes reemplazaba PyPI). Nota de que el ruling de la convivencia
  quedo implementado y que los numeros de J y del R1 caliente son del codigo anterior.
- `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md:358-376`: la entrada de la ola de
  fix, el orden, las dos vueltas atras (comando corregido) y el cache.
- `AGENTS.md:246-248` (la aduana: whisper al primer uso; la memoria ya no sale), `calipso/server.py`
  `_calentar_probes` (`:8882`) y el comentario de `_startup_warm` (`:8900-8902`), `calipso/aduana.py:11-13`
  (el ejemplo de `declarar` pasa a `declarar_una_vez("whisper", ...)`, el que existe). Sin test (docs y
  docstrings); la suite entera verde.

### 7. El banco anota el ruido intra-corpus (`7ad6843`)

- `experimentos/recall_banco.py:262` `ruido_intra_corpus(filas)`: por condicion, los scores de OTRO
  topico en el top-4 de las consultas positivas (literal, parafrasis y reales; las negativas quedan
  afuera), `n`, `max` y `pasan` contra `UMBRALES_REFERENCIA` (`:85`: 0.476 turno, 0.44 abismo, 0.30 el
  viejo de MiniLM); `resumen` suma `r["ruido"]` con `pasan_sugerido` (contra el umbral sugerido de la
  condicion); `informe` tiene la seccion `## Ruido intra-corpus` (`:387`) con la tabla; `--informe`
  imprime una linea por condicion y ahora CONSERVA del MD anterior la fecha de la corrida y la seccion
  "Umbrales elegidos" escrita a mano (`conservar_del_md`, `:342`): antes regenerar el MD las pisaba.
- `experimentos/recall_banco_resultados.md` regenerado con `--informe` sobre el JSONL commiteado (sin
  Ollama): solo se suma la seccion (11 lineas). Numeros: `bge-m3:pregunta+150` 63 hits, max 0.6961,
  22/63 pasan 0.476 (= el sugerido), 32/63 pasan 0.44, 63/63 pasan 0.30; `minilm` 63 hits, max 0.7011,
  26/63 pasan su sugerido 0.374, 45/63 pasan 0.30; `bge-m3:par` 63, 22/63 a 0.476; `bge-m3:pregunta`
  64, sin sugerido. Anotado junto a `RECALL_MIN_SCORE` (`server.py:3076-3078`) y `RECALL_UMBRAL`
  (`fuentes.py:30-32`), que siguen PROVISORIOS (el test `test_los_dos_umbrales_estan_marcados_
  provisorios_y_atados_al_banco` sigue verde: "PROVISORIO" y "recall_banco" dentro de la ventana).
- Test seco (`test_recall_umbrales.py:72,96`): con filas sinteticas (7 hits, max 0.7, pasan 3/3/4,
  el sugerido 0.85 con 0 que lo pasan, la seccion y la fila en el MD) y con el JSONL commiteado (63,
  0.6961, 22; MiniLM 45 a 0.30 y 26 al sugerido). El banco se importa por ruta y se restaura
  `CALIPSO_EMBED_FALSA` (el modulo lo quita al importar). Rojo verificado (`AttributeError`).

### 8. Menores (`a4bc79e`)

- `calipso/memoria_embed.py:261-274` `ids_de` con `warnings.catch_warnings()` +
  `filterwarnings("ignore", message="Could not reconstruct embedding function", category=UserWarning)`;
  cualquier otro aviso pasa. Test `test_memoria_embed.py:371` con un cliente que avisa ese
  `UserWarning` y un `DeprecationWarning`: solo el segundo se ve. Rojo verificado.
- Docstrings viejos: `test_memoria_carta.py`, `test_abismo_memoria_recall.py` y `test_memoria_ambito.py`
  ya no citan MiniLM/huggingface (grep vacio en `9c32f72`: nada que tocar); el parrafo de
  `memoria_reindex.py` se reescribio en el punto 3.

## Desvios y dudas

- Punto 2: el brief dice `CONFIG["local"]["model"]`; `carga.py` no tiene un `CONFIG` de modulo y el
  server tampoco (usa `_route_model_name`), asi que se usa `carga._modelo_configurado()` (lee
  `config.json` del CALIPSO_HOME por llamada; es un JSON chico, dos veces por turno) con `modelo_chat`
  inyectable. Si /proc no se lee, la tabla decide, pero el chequeo del 7b listado sigue valiendo
  (0 si esta): lo lei como parte del "devuelve 0 si ...".
- Punto 2: en el smoke `keep_alive_embed(cv.nivel)` (pasos V y J) ahora lee /proc fresco de la maquina
  del smoke: la nota de esos pasos deja de ser "la tabla" y pasa a ser la decision real. Es lo deseado.
- Punto 3: el rechazo de la falsa va DESPUES del chequeo del puerto y de `--forzar` (el test viejo del
  puerto ocupado espera esos mensajes); el orden no cambia lo que se escribe (nada en los tres casos).
- Punto 4: sin test en la suite (el smoke no tiene); verificado en seco con dobles.
- Punto 5: `@app.on_event` esta deprecado en FastAPI 0.137 (warning en la suite, ya estaba por el
  startup); se mantuvo por consistencia con el hook existente, como pedia el brief.
- Punto 7: el MD regenerado conserva "Corrida: 2026-09-12 13:06" y la seccion de umbrales a mano gracias
  a `conservar_del_md`; sin eso `--informe` habria pisado esa seccion con la plantilla vacia.
- La suite tarda ~2 min con nice; corrio 9 veces (una base + una por commit).
- Queda sin commitear (ya estaba, no es mio): `docs/superpowers/2026-09-12-cierre-memoria-ollama/`
  (la revision final y las lentes).
