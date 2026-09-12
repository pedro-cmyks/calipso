# La memoria embebe por Ollama (bge-m3) y el server se queda sin torch: plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la memoria episodica de Calipso calcule sus vectores con `bge-m3` en Ollama (`POST /api/embed`, loopback) y el server deje de cargar torch, transformers y sentence-transformers (1,5 GB de RSS antes de servir nada; decision de Pedro del 2026-09-12): funcion de embeddings propia y pura al construirse, colecciones nuevas `episodic-bge-m3` al lado de la vieja `episodic` (que no se borra), `remember` con embeddings explicitos sobre la pregunta mas 150 palabras de respuesta y DESPUES del `done`, `recall` fail-open de una sola embedding por turno y visible en `/api/memory` y en el abismo, un reindex `--embeddings` idempotente con el server apagado, `sin_reindexar` a la vista, el embedder gobernado por la carga (nombre normalizado, `keep_alive` propio, vigia por `/api/embed`), los umbrales re-medidos con un banco de recall, y un smoke en vivo con Ollama real que mide la convivencia con el 7b.

**Architecture:** Un modulo nuevo `calipso/memoria_embed.py` (puro salvo el POST a loopback en `_post_embed`): `OllamaEmbed(EmbeddingFunction)` registrada en chroma como `calipso_ollama` (`name/get_config/build_from_config` puros, dims fijas por config), `EmbedFalsa` (hash determinista a 1024 dims, sin red, hija de la anterior) para la suite, `texto_para_embedding(doc, palabras=None)` (el default es `PALABRAS_RESPUESTA`, leido por llamada), `lotes()` por tamano, `embeber()` (una sola costura para embeber con timeout), `embed_tag()`, `COLECCION_VIVA`, `sin_reindexar(cliente)`. `calipso/config.py` gana `EMBED_MODEL` (`bge-m3:latest`, lo que devuelve `/api/ps`), `EMBED_DIMS` (1024) y `EMBED_URL`. `calipso/memory.py` deja de importar `SentenceTransformerEmbeddingFunction`: `Memory(project_root, embed=None)` elige `EmbedFalsa` con `CALIPSO_EMBED_FALSA=1` (que `conftest.py` fija antes de importar), `Scope` abre `episodic-<tag>`, `Scope.remember` embebe por afuera y hace `upsert(..., embeddings=)`, `Scope.recall(query, n, embedding=None)` conserva la costura vieja, `Memory.recall` mira `count() > 0` por ambito, embebe UNA vez, consulta con `query_embeddings` y atrapa cualquier excepcion (`[]` + fila `kind: memoria, accion: recall_fallo` + `recall_ok`/`ultimo_recall_fallo`). `calipso/memoria_reindex.py` gana `--embeddings` (copia `episodic` a `episodic-<tag>` por ids, lotes por tamano, doble lista de ids, sin `--forzar`) y `--vista/--aplicar` pasan a operar sobre la viva (o la vieja si la viva no existe: el orden `--embeddings`/`--aplicar` converge). En `server.py`: el `remember` del turno va DESPUES del `done` como tarea de fondo (conjunto `_TAREAS_DE_FONDO` que el harness espera), `GET /api/memory` devuelve `sin_reindexar`, `recall_ok` y `ultimo_recall_fallo`, el arranque anuncia `sin_reindexar` (una linea + fila), `_declarar_arranque` ya no declara la memoria, `_modelos_de_calipso()` suma el embedder y el vigia lo descarga por `/api/embed` sin histeresis. En `carga.py`: `keep_alive_embed(nivel)` (holgada 5m, justa/cargada 0), `payload_local(..., keep_alive=)`, `mismo_modelo()` normalizando `:latest`, `ollama_evict(..., embedding=True)`, `_modelos_configurados()` con el embedder. El abismo cierra la fuente `memoria` con motivo `memoria_no_disponible`. Un banco de recall (`experimentos/recall_banco.py`) mide MiniLM contra bge-m3 en tres variantes de texto embebido y fija los umbrales PROVISORIOS con vuelta atras por env. El fixture del smoke se regenera UNA vez con `--embeddings` (las dos colecciones commiteadas) y el smoke `experimentos/memoria_smoke.py` (server desechable 8779, Ollama real, un proxy local para "cortar" Ollama a mitad) mide el recall real, el `done` antes del remember, el fail-open, el reindex, la descarga por `/api/embed` y la convivencia con el 7b.

**Tech Stack:** Python 3.14 + FastAPI + pytest en la raiz (harness `chat` de `test_abismo_chat.py` con `MemoriaFalsa`/`ModeloEspia`; `medida()` y `_Resp` de `test_carga.py`); chromadb 1.5.9 (`register_embedding_function`, `upsert(..., embeddings=)`, `query(query_embeddings=)`, `get(include=[])`); stdlib para el POST (`urllib`) y el proxy del smoke (`socket`, `threading`); Ollama 0.30.10 con `bge-m3:latest` (566,7M, F16, 1024 dims, 1157 MB en disco, 1219 MB en RAM cargado) y `qwen2.5:7b`; `numpy` para los vectores; `sentence_transformers` SOLO en la condicion MiniLM del banco (importado adentro de un `try`, antes del uninstall); `websockets` 16.0 del venv para el smoke.

**Spec:** `docs/superpowers/specs/2026-09-12-memoria-embeddings-ollama-design.md` (autoridad: la decision de Pedro de la seccion 1, la forma de la 2, el banco de la 3, las 6 invariantes de la 4, la verificacion de la 5, lo que NO hace de la 6, el corte en 4 tasks de la 7 y los 14 rulings de la 8, ya tomados: este plan no los rediscute). Todo `archivo:linea` de este plan es del worktree `/var/home/pedro/calipso/.claude/worktrees/memoria-ollama` (rama `feat/memoria-ollama` @ `2276fcf`, arbol = main `6780bec` mas los dos commits del spec), verificado con `grep -n`/`sed -n` el 2026-09-12. Las anclas validas son los bloques ANTES y los simbolos, no los numeros. El terreno que precedio a este plan (con las sondas de chroma y los numeros del spike) esta en `.superpowers/sdd/2026-09-12-memoria-ollama/terreno-plan.md` y `terreno-spike.md`.

## Global Constraints

Invariantes del spec (seccion 4), textuales:

1. **El server no importa torch** ni ningun runtime de ML: los modelos viven en Ollama.
2. **La memoria es fail-open:** sin Ollama, el turno sale sin recuerdos y lo dice en telemetria; nunca tumba el websocket ni el arranque.
3. **Nada se pierde:** la coleccion vieja no se borra; el reindex es idempotente y por ids; `sin_reindexar` se ve hasta que sea 0.
4. **Los umbrales se re-miden con el banco** antes de aterrizar; los vectores viejos y nuevos no se mezclan (colecciones distintas).
5. **Un solo camino a Ollama:** el embedder usa `carga.payload_local` y `carga.usando()`, y su modelo esta en la lista de modelos de Calipso (memoria efectiva, vigia).
6. **Ningun test llama a Ollama ni a huggingface.co.**

Reglas del repo:

- **El repo es el WORKTREE** `/var/home/pedro/calipso/.claude/worktrees/memoria-ollama` (rama `feat/memoria-ollama`). El checkout principal `/var/home/pedro/calipso` esta en `main` y lo sirve el server real (puerto 8000, `~/.calipso`): NO se toca, no se reinicia, no recibe turnos del agente. El interprete es el del venv compartido: `/var/home/pedro/calipso/.venv/bin/python` (el paquete `calipso` no esta instalado en el venv: se importa desde el cwd, por eso todo comando corre desde la raiz del worktree).
- SIN EMOJIS en codigo, tests, docs, commits y salidas. Todo texto NUEVO (comentarios, docstrings, docs, mensajes) en espanol SIN acentos. Los bloques ANTES copian el texto viejo TAL CUAL (con sus acentos y su mojibake): son el ancla de un reemplazo textual, nunca se retocan.
- `CALIPSO_HOME` a un temporal en TODO test: `conftest.py:46-47` lo fija ANTES de importar `calipso`; la Task 1 suma `CALIPSO_EMBED_FALSA=1` al lado (ruling 8.10). NUNCA importar `calipso` fuera de pytest sin `export CALIPSO_HOME=<temporal>` antes (`memory.Scope.__init__` hace `mkdir` y abre chroma en el acto). Todo comando suelto de este plan va con `CALIPSO_HOME=$(mktemp -d)`.
- **Ningun test llama a Ollama** (invariante 6): en la suite `Memory()` construye `EmbedFalsa` por `CALIPSO_EMBED_FALSA=1`; los unitarios de `memoria_embed.py` doblan `urlopen`; el harness usa `MemoriaFalsa` o una `Memory` real con `EmbedFalsa`. Los UNICOS pasos que hablan con Ollama real son el banco (Task 3, Step de la corrida), la regeneracion del fixture (Task 4) y el smoke (Task 4), siempre precedidos por `CALIPSO_HOME=$(mktemp -d) /var/home/pedro/calipso/.venv/bin/python -m calipso.carga --esperar` (la regla de recursos: abre con `justa` u `holgada`; codigo 3 = BLOQUEADO, no se corre nada).
- **La maquina es una ROG Ally con 11,4 GiB y Pedro a veces juega en ella.** La suite SIEMPRE con `nice -n 19`. Antes de la suite y de cualquier cosa que cargue un modelo, mirar la RAM libre (`--esperar`). El 7b pesa 5203 MB en `/api/ps` y `bge-m3` 1162-1219: los dos juntos ~6,4 GB.
- **La suite entera tarda ~120-150 s: no se corre por reflejo.** Cada task corre SUS archivos sueltos (listados en cada Step de verde) y la suite completa UNA vez antes de su commit, verificando el EXIT CODE: `cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama && nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q --ignore=test_chat_live.py -p no:cacheprovider 2>&1 | tail -1; echo EXIT=$?` -> `0 failed`, `EXIT=0`. `test_chat_live.py` no se importa ni se corre. `test_routines.py` y `test_prompt_compiler.py` son scripts (no pytest) y no los toca este plan.
- `test_aduana_canario.py` es un guardia de dos filos: cada `urlopen` nuevo bajo `calipso/` exige su linea en `EXCEPCIONES` (`archivo:funcion` con motivo; la clave se arma con la pila de `FunctionDef`, una `ClassDef` NO entra: por eso el POST vive en la funcion de modulo `_post_embed`), y una excepcion sin hallazgo falla el otro test.
- `test_aislacion_home.py:35-47` recorre los modulos `calipso.*` con un atributo `CALIPSO_HOME` de tipo `Path`: `memoria_embed.py` NO tiene atributo `CALIPSO_HOME` (lee `calipso.config`).
- `test_plantel_promesas.py:77-89` y `test_plantel_reacciones.py:85-99` exigen por AST que `plantel/promesas.py` y `plantel/reacciones.py` NO importen `memory` ni `chromadb`: no se tocan.
- `test_memoria_ambito.py:82-96` acota el bloque del remember del turno por TEXTO del fuente de `server.py` (desde el comentario `recordar el intercambio`, PRIMERA aparicion: ningun comentario anterior de `ws_chat` puede repetir ese literal) y exige adentro `mem.remember`, `scope="global"`, `asyncio.to_thread`, `except Exception`, `pregunto`/`respondio` y ningun `Ã`: al pasar el remember a tarea de fondo (Task 2) el fixture se re-acota hasta `except WebSocketDisconnect` (el send del `done` queda adentro, despues de `_en_fondo(`) y la corutina queda INLINE en `ws_chat` (no en una funcion aparte).
- `test_turno_secciones.py:115` fija `options == {"num_ctx": CHAT_NUM_CTX}` con igualdad estricta bajo holgada: `payload_local` sigue sin agregar `num_thread` bajo holgada; el parametro nuevo `keep_alive=` no cambia nada cuando no viene.
- `git add` con rutas explicitas (dos agentes en paralelo comparten el indice). Anclas por SIMBOLO (`grep -n '^def <nombre>'`, `grep -n 'async def ws_chat'`); cada bloque ANTES es unico en su archivo (verificado con `grep -c` de su primera linea distintiva) y se aplica con un reemplazo textual, nunca a mano. **Un ANTES con 0 matches (o con mas de 1) detiene la task:** se re-deriva desde el arbol, se reescribe el par ANTES/DESPUES en el plan y se anota en el reporte de la task. Nunca se improvisa sobre un ANTES que no matchea.
- Cada commit lleva al final del mensaje estas dos lineas (trailer):
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01N3P8mZgfi31VYnG8sweiAa`
- Ritual de cierre: el banco (Task 3) y el smoke con Ollama real (Task 4) antes del merge; **el merge, el `pip uninstall` del venv real, el reindex del home real y el reinicio del server real son del controlador**, no del implementador (spec seccion 5, "Despliegue").

## Decisiones tomadas por este plan (visibles; el spec las dejaba al plan)

1. **`EmbedFalsa` es HIJA de `OllamaEmbed`** y comparte `name() = "calipso_ollama"` y `get_config()`: el esquema que chroma persiste en la suite es identico al de produccion, el fixture generado con la EF real se abre en la suite con la falsa sin conflicto de nombre (`validate_embedding_function_conflict_on_get` compara solo `name()`), y chroma auto-registra `type(ef)` al crear una coleccion (`collection_configuration.py:163`), asi que en la suite `known_embedding_functions["calipso_ollama"]` puede ser la hija: los tests afirman `issubclass(..., OllamaEmbed)`, no identidad. `build_from_config` es un `classmethod` que construye `cls(...)`.
2. **Una sola costura para embeber: `memoria_embed.embeber(ef, textos, timeout=None)`.** Si la EF tiene `embed(textos, timeout=)` (las dos de Calipso) lo usa; si es una EF ajena de chroma la llama con `__call__` y convierte a `list[list[float]]`. Asi los timeouts por uso (ruling 8.7: recall `TIMEOUT_RECALL_S = 10`, remember y reindex `TIMEOUT_REMEMBER_S = 120` por lote) viajan sin pasar por el `__call__` que chroma envuelve, y `Memory(embed=)` acepta cualquier EF.
3. **El fail-open del recall vive en `Memory.recall` (un solo `try`, una sola fila).** `Scope.recall(query, n, embedding=None)` NO atrapa: es la costura vieja (si no viene el vector, embebe) y nadie del server la llama directo (grep: `mem.recall` en `server.py:3201` y `abismo/fuentes.py:120`, los dos por `Memory`; el jefe usa `recent`/`remember`). El spec (seccion 2) dice "Scope.recall y Memory.recall atrapan": la conducta observable (ninguna excepcion sale de la memoria hacia el turno, fila `recall_fallo`, `[]`) se cumple en el unico punto de entrada; atrapar dos veces habria escondido el fallo del ambito al llamador que decide el motivo del abismo (y `recall_ok` quedaria en True con la memoria muerta: contra el ruling 8.8). Es un desvio de la LETRA del spec (seccion 2, "Scope.recall y Memory.recall atrapan"; verificado por grep que `.recall(` fuera de `memory.py` solo vive en `server.py:3201` y `abismo/fuentes.py:120`, los dos por `Memory`): queda a la vista aca y en el ledger de correcciones para que el controlador lo anote como ruling en la seccion 8 del spec al cierre; no cambia codigo.
4. **`recall_ok` y `ultimo_recall_fallo` son atributos de instancia de `Memory` con default de clase** (`recall_ok = True`, `ultimo_recall_fallo = None`): los dobles construidos con `Memory.__new__` los heredan, `_switch_project` (que reconstruye `Memory`) los resetea (aceptado: la memoria nueva no fallo todavia), y `fuentes.memoria` los lee con `getattr(mem, "recall_ok", True)` para que los dobles sin el atributo sigan valiendo.
5. **El motivo `memoria_no_disponible` llega al abismo por una excepcion con aviso fijo:** `fuentes.memoria` levanta `MemoriaNoDisponible("la memoria no esta disponible")` cuando el recall devolvio `[]` y `mem.recall_ok is False`; `consulta.resolver` ya la convierte en `_fallo(fuente, str(e))`; `turno.motivo_de_consulta` mapea ese aviso exacto (como hace con "la consulta no trajo nada") y `MOTIVOS` lo suma. Las UIs no cambian (ruling 8.8: una marca es YAGNI): `MOTIVOS[m.motivo] || m.motivo` en `chat.js:187` e `index.html:2594` imprime el motivo crudo.
6. **Las tareas de fondo del server son un conjunto de modulo `_TAREAS_DE_FONDO: set[asyncio.Task]` con `_en_fondo(coro)`** (crea la task, la guarda, la saca al terminar con `add_done_callback`). El remember del turno se PROGRAMA con `_en_fondo` justo antes de `await ws.send_json({"type": "done"})` y corre despues (create_task no ejecuta; el remember arranca en la siguiente vuelta del loop, en un hilo): asi el done sale sin esperar el embedding (ruling 8.3) y un corte del cliente justo en el send del done (que levanta y salta al `except WebSocketDisconnect`) no pierde el episodio, que antes de este cambio tambien se guardaba. El harness gana `Harness.esperar_fondo()` (poll sobre el conjunto desde el hilo del test, ADENTRO del `with websocket_connect`, antes de que el socket cierre) y `turno()` lo llama tras el drenaje: las aserciones sobre `memoria.recordado` dejan de ser una carrera. El remember de la meta (`server.py:3883-3891`) no se toca.
7. **`texto_para_embedding` embebe la pregunta LIMPIA (sin gestos) y las primeras 150 palabras de la respuesta, sin las etiquetas `Pedro pregunto:`/`Calipso respondio:`**, separadas por un salto de linea; un documento que no parsea como par (metas, fichas del jefe) embebe sus primeras `PALABRAS_OTRO = 300` palabras, fijo: NO depende de `palabras` (con la variante pregunta sola, `palabras=0`, una meta quedaria vacia). `palabras=None` lee `PALABRAS_RESPUESTA` por llamada: el Step de anotar los umbrales (Task 3, Step 10) puede cambiar el numero sin tocar los tests, que prueban 150 explicito y el default por separado. El documento guardado no cambia (ruling 8.5). El banco mide las tres variantes (`palabras=0` = pregunta sola; 150; el par entero) y si otra separa mejor se cambia el numero, no la forma.
8. **`--vista/--aplicar` abren la VIVA si existe y si no la VIEJA** (`abrir(cliente) -> (col, nombre)`): asi `--aplicar` antes de `--embeddings` marca la vieja y el reindex copia los metadatos ya marcados; `--embeddings` antes de `--aplicar` copia y despues se marca la viva. Los dos ordenes convergen (spec seccion 2). La linea de `sin_reindexar` se imprime en `--vista` y en `--aplicar` ANTES de la linea de procedencia, y dice sobre que coleccion opera la procedencia. `HF_HUB_OFFLINE`/`TRANSFORMERS_OFFLINE` quedan en `memoria_reindex.py` (protegen el `--aplicar` sobre la vieja mientras sentence-transformers siga instalado; tras el uninstall son inertes).
9. **`sin_reindexar(cliente)` vive en `memoria_embed.py`** (conoce `COLECCION_VIVA` y `COLECCION_VIEJA`): lo usan `Scope.sin_reindexar()`, `Memory.sin_reindexar()` (dict por ambito: `{"global": N, "project": N}`), `GET /api/memory`, el arranque (`_anunciar_memoria`) y el reindex. `memory.py` NO importa `memoria_reindex` (que fija `HF_HUB_OFFLINE` al importarse: un efecto que no tiene por que entrar al server).
10. **`OllamaEmbed.embed` con lista vacia devuelve `[]` sin POST** (chroma revienta con `ef([])`; los llamadores nunca llegan con vacio: `Memory.recall` corta en `count() == 0`, el reindex en `nuevos == []`), valida `len(embeddings) == len(lote)` y `len(v) == dims` (una respuesta rara es `EmbedError`, no un `InvalidArgumentError` de chroma dos capas mas abajo), y envuelve TODO el recorrido de lotes en `carga.usando()` (un uso suelto: el vigia no descarga a mitad).
11. **Los umbrales se leen por `memoria_procedencia.umbral_por_env(nombre, default, alias=None)`:** `RECALL_MIN_SCORE` lee `CALIPSO_RECALL_MIN_SCORE` y, como alias, el viejo `CALIPSO_RECALL_MIN`; `RECALL_UMBRAL` lee `CALIPSO_RECALL_UMBRAL`; un valor roto cae al default (un env mal tipeado no puede impedir que arranque el server). El numero de cada default lo pone la corrida del banco (Task 3, Step "anotar"); hasta esa corrida quedan los de MiniLM (0.30 / 0.20) marcados PROVISORIOS.
12. **El embedder se descarga por `/api/embed` con `input: "x"` y `keep_alive: 0`** (`ollama_evict(nombre, embedding=True)`): un `input` vacio podria salir por la rama corta de Ollama sin tocar el runner (no se pudo POSTear hoy), y un caracter cuesta 0,1 s. **El vigia no suspende el local al descargar el embedder** (la histeresis es del modelo del chat: suspender el 7b por descargar bge-m3 seria castigar al chat por un modelo que no es el suyo); si el 7b tambien esta listado se descarga en el mismo tick con la suspension de siempre. Hook aparte: `_ollama_evict_embedding(nombre)`.
13. **`payload_local(payload, nivel=None, keep_alive=None)`:** el parametro nuevo pisa la tabla del 7b solo cuando viene; los seis sitios viejos no cambian (test_carga_sitios sigue byte a byte). Adentro, la tabla del 7b se lee por el alias `_keep_alive_del_nivel` (el parametro se llama igual que la funcion).
14. **`mismo_modelo(a, b)` normaliza `:latest` a los dos lados** y se usa en `carga.medir` (la memoria efectiva) y en `_vigia_del_modelo` (ruling 8.1); `_modelos_de_calipso()` y `_modelos_configurados()` suman `calipso_config.EMBED_MODEL` tal cual (`bge-m3:latest`), sin normalizar al guardar.
15. **`Memory.recall` con ningun ambito poblado devuelve `[]` sin tocar `recall_ok`** (no hubo intento). Con ambitos poblados: una embedding, y `recall_ok = True` al salir bien.
16. **El smoke corta "Ollama" con un proxy TCP local** (`127.0.0.1:11435 -> 11434`) al que el server desechable apunta por `CALIPSO_EMBED_URL`: cortar el proxy a mitad de la corrida es "Ollama caido" para el embedder sin matar el Ollama real (que sirve al 7b del mismo smoke y al server real). `carga.OLLAMA` (el `/api/ps` del sensor) y `dispatch` siguen yendo directo.
17. **La regeneracion del fixture corre SOLO `--embeddings`** (no `--aplicar`): la viva queda con los 16 ids, documentos y metadatos IGUALES a la vieja (sin `procedencia`), asi `test_sobre_una_copia_del_fixture_real` sigue midiendo "16 por reindexar" sobre la viva y `test_memoria_fixture.py` afirma la igualdad exacta.
18. **El banco corre sobre una COPIA temporal del fixture** (chroma sobre el directorio commiteado podria escribir su WAL), lee las filas reales con `--home <ruta> --reales <json>` (el JSON con las 5 consultas escritas a mano NO se commitea: vive en el scratchpad de la sesion; el MD muestra de las reales solo ids y numeros) y mezcla fixture + reales en un solo corpus por condicion (mas distractores = medicion mas honesta).

## Rulings que el implementador NO puede tomar solo

Si aparece una de estas dudas, se detiene y pregunta (a Pedro, o al controlador del plan); todo lo demas esta decidido arriba o en el spec:

1. **Los umbrales del recall** (`RECALL_MIN_SCORE`, `RECALL_UMBRAL`): los numeros salen del banco por el criterio del margen (spec seccion 3) con los aciertos de MiniLM como piso. Si `bge-m3` no iguala el `hit@1` por topico de MiniLM, o su margen es negativo, **se para** y se le dice a Pedro con la tabla; no se aterriza a ciegas ni se afloja un umbral para que el banco "salga".
2. **La forma del texto embebido** (decision 7): se puede cambiar el NUMERO (150 -> lo que el banco separe mejor, incluido 0 = pregunta sola o "par entero"), nunca la forma (agregar etiquetas, resumir, meter metadatos). Si ninguna de las tres variantes iguala a MiniLM, es ruling de Pedro.
3. **Borrar la coleccion vieja `episodic`** (spec seccion 6): NO, en ningun home, ni en el fixture, ni "para que el sqlite pese menos". Otra tanda, cuando `sin_reindexar` sea 0 en todos los homes.
4. **Tocar el server real** (puerto 8000, `~/.calipso`, el checkout `/var/home/pedro/calipso`): ni reiniciarlo, ni mandarle un turno, ni correr `memoria_reindex` sobre `~/.calipso`, ni escribir en su home. La UNICA lectura permitida de `~/.calipso` es la del banco (spec seccion 3: las 5 filas reales), que copia `projects/var-home-pedro-calipso/chroma` a un tmp y lee de la copia (`--home ~/.calipso`, `--listar-reales`, `--reales`). Con 3 en `--esperar`, se para y se dice.
5. **El `pip uninstall`** de torch/transformers/sentence-transformers/nvidia-* en el venv real (spec seccion 5, lista explicita): es del controlador, despues del banco (que necesita MiniLM instalado) y del merge. El implementador no desinstala nada.
6. **La convivencia con el 7b bajo `justa`** (ruling 8.4): si el smoke (Task 4, paso J) muestra que Ollama desaloja al 7b para cargar bge-m3 (o al reves) se para y se le dice a Pedro con los numeros de `/api/ps` por paso; las candidatas (saltar el recall bajo justa con el 7b cargado, con fila; cola de remember diferido que el tick drena en holgada) son de Pedro.
7. **Pre-calentar el embedder al arrancar** (spec seccion 6): no. El primer recall tras inactividad paga ~2 s de carga fria: se mide y se anota en el smoke.
8. **Tocar el juez de privacidad, el compositor, el lector o el abismo mas alla del recall** (ruling 8.14).
9. **Cambiar `EMBED_DIMS` o consultar `/api/show` al construir la EF** (ruling 8.2): la EF es pura; si Pedro cambia de modelo, cambia `CALIPSO_EMBED_MODEL` y `CALIPSO_EMBED_DIMS` juntos y reindexa.
10. **Volver a ESPERAR el remember antes del `done`** (un `await` del remember antes del send, como estaba) "porque el harness se pone raro" (ruling 8.3): el harness espera el conjunto de tareas de fondo; si una carrera aparece, se arregla la espera. Programar la tarea antes del send del done (decision 6) no es esto: el done sigue saliendo sin esperar el embedding.
11. **El merge** de `feat/memoria-ollama` (del controlador, tras suite + banco + smoke + informe), el reindex del home real y el reinicio del server real.

## Mapa de archivos

**Se crean:**

| Archivo | Que es | Task |
|---|---|---|
| `calipso/memoria_embed.py` | la EF `OllamaEmbed` (registrada), `EmbedFalsa`, `EmbedError`, `_post_embed`, `texto_para_embedding`, `lotes`, `embeber`, `embed_tag`, `EMBED_TAG`, `COLECCION_VIVA`, `COLECCION_VIEJA`, `embedder_por_env`, `ids_de`, `sin_reindexar`, los timeouts y `LOTE_CHARS` | 1 |
| `test_memoria_embed.py` | unitarios de la EF con `urlopen` doblado, el registro en chroma en un tmp, `texto_para_embedding`, `lotes`, y `Memory` con `EmbedFalsa` (nombre de coleccion, una embedding, fail-open, remember con embeddings explicitos) | 1 (3 suma el keep_alive propio) |
| `test_memoria_server.py` | `GET /api/memory` con `sin_reindexar`/`recall_ok`, el arranque que anuncia, el turno por el harness con la memoria muerta (`done` + fila), el remember despues del `done`, el abismo con `memoria_no_disponible` | 2 |
| `test_memoria_sin_torch.py` | el guardia anti-torch: AST del repo + `import calipso.server` en subproceso con home temporal | 3 |
| `test_recall_umbrales.py` | `umbral_por_env` y las constantes marcadas PROVISORIAS | 3 |
| `experimentos/recall_banco.py` | el banco de recall: consultas, condiciones, metricas, MD + JSONL, `--informe` | 3 |
| `experimentos/recall_banco_resultados.{jsonl,md}` | la corrida | 3 |
| `test_memoria_fixture.py` | el fixture trae las dos colecciones con los mismos ids/documentos/metadatos | 4 |
| `experimentos/memoria_smoke.py` | el smoke con Ollama real (server desechable 8779, proxy 11435) | 4 |
| `docs/superpowers/2026-09-12-smoke-memoria.md` | el informe del smoke | 4 |

**Se modifican (lineas de `feat/memoria-ollama` @ `2276fcf`):**

| Archivo | Donde | Que | Task |
|---|---|---|---|
| `calipso/config.py` | `:9-11` (tras `CONFIG_FILE`) | `EMBED_MODEL`, `EMBED_DIMS`, `EMBED_URL` | 1 |
| `calipso/memory.py` | `:36-46` (imports y `EMBED_MODEL`), `:56-66` (`Scope.__init__`), `:92-118` (`Scope.remember`), `:120-130` (`Scope.recall`), `:159-172` (`Memory.__init__`), `:203-215` (`Memory.recall`) | sin torch, `episodic-<tag>`, embeddings explicitos, una embedding, fail-open | 1 |
| `conftest.py` | `:46-47` | `CALIPSO_EMBED_FALSA=1` | 1 |
| `test_aduana_canario.py` | `:44-49` (`EXCEPCIONES`), `:58` | la entrada de `_post_embed`; la letra de `commands.py:run` | 1 |
| `test_abismo_memoria_recall.py` | entero (38 lineas) | dobles con `count()` y `recall(query, n, embedding=None)`, `_embed` falso; una embedding; fail-open | 1 |
| `test_memoria_ambito.py` | `:15-17`, `:40-46`, `:82-96` (fixture `turno`), `:130-153` (`_ColeccionFalsa`, `ambito`) | docstrings; `upsert(..., embeddings=None)`; `_embed`; el fixture re-acotado hasta `except WebSocketDisconnect` | 1 (docstrings, coleccion falsa) y 2 (fixture `turno`) |
| `test_memoria_carta.py` | `:69-72` | docstring | 1 |
| `calipso/memory.py` | `Scope` (tras `count`), `Memory` (tras `recall`) | `sin_reindexar()` | 2 |
| `calipso/memoria_reindex.py` | `:1-9` (docstring), `:36-54` (imports, constantes), `:103-109` (`abrir`), `:173-218` (`main`) | `--embeddings`, `abrir` viva-o-vieja, `reindexar_embeddings`, la linea de `sin_reindexar` | 2 |
| `calipso/server.py` | antes de `_medir_carga` (`:2434`), `_startup_warm` (`:8794-8798`), `api_memory` (`:5319-5326`), `ws_chat` `:4748-4795` y `:4818-4826` | `_TAREAS_DE_FONDO`, `_en_fondo`, `_anunciar_memoria`; `/api/memory`; el remember despues del `done` | 2 |
| `calipso/abismo/fuentes.py` | `:19-21`, `:119-122` | `MemoriaNoDisponible`, `AVISO_MEMORIA_NO_DISPONIBLE`, `RECALL_UMBRAL` por env (Task 3) | 2, 3 |
| `calipso/abismo/turno.py` | `:18-19`, `:131-135` | `memoria_no_disponible` en `MOTIVOS` y en `motivo_de_consulta` | 2 |
| `test_abismo_chat.py` | `:150-160` (`Harness.turno`) | `esperar_fondo()` | 2 |
| `test_memoria_reindex.py` | `:1-10` (docstring), `:165-169` (mensaje "se salta"), `:183-202` (fixture real) | la letra nueva; `_leer(nombre=)`; tests de `--embeddings` | 2 (y 4 para el fixture con las dos colecciones) |
| `calipso/carga.py` | `:396-406` (`medir`), `:448-484` (`keep_alive`/`payload_local`), `:587-601` (`ollama_evict`), `:652-662` (`_modelos_configurados`) | `mismo_modelo`, `keep_alive_embed`, `keep_alive=`, `embedding=True`, el embedder en los propios | 3 |
| `calipso/memoria_embed.py` | `OllamaEmbed.embed` | `keep_alive=carga.keep_alive_embed(nivel)` | 3 |
| `calipso/memoria_procedencia.py` | al final | `umbral_por_env` | 3 |
| `calipso/server.py` | `:104` (import), `:2171-2189` (`_declarar_arranque`), `:3005` (`RECALL_MIN_SCORE`), `:5720-5733` (`_modelos_de_calipso`, hook), `:5756-5762` (el vigia), `:8795` (comentario) | sin `EMBED_MODEL`, sin "modelo de embeddings", umbral por env, el embedder en la lista y en el vigia | 3 |
| `test_aduana_api.py` | `:434-449`, `:507-516`, `:587-600` | el cruce "modelo de embeddings" desaparece | 3 |
| `test_carga_vigia.py` | `:143-147` | el set suma el embedder; el vigia lo descarga por el hook nuevo sin suspender | 3 |
| `test_carga.py` | al final | `keep_alive_embed`, `payload_local(keep_alive=)`, `ollama_evict(embedding=True)`, `mismo_modelo`, `medir` normalizando, `_modelos_configurados` | 3 |
| `AGENTS.md` | `:430-431` | la memoria por Ollama, sin torch, la coleccion viva y el reindex | 3 |
| `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md` | seccion 9 (al final) | la entrada "La memoria por Ollama (2026-09-12)" | 3 |
| `experimentos/fixtures/memoria_smoke_home/` | `global/chroma/`, `projects/var-home-pedro-calipso/chroma/`, `README.md` | las dos colecciones (generadas con `--embeddings`), la receta | 4 |

**Lo que NO se toca (spec seccion 6 y ruling 8.14):** chroma y la forma de los episodios, la procedencia (`memoria_procedencia.presentar*`), el juez de privacidad, el compositor, el lector, el abismo mas alla de la fuente `memoria`, `_switch_project` (reconstruye `Memory`: ahora es barato), el remember de la meta, `reflect`/`recent`, los departamentos en el reindex (no existen), `calipso.sh`/`LINUX_MIGRATION.md` (nunca instalaron torch; ruling 8.13), las UIs.

## Orden de tasks

El corte de la seccion 7 del spec, en su orden: 1 la EF y `Memory`; 2 el reindex, `/api/memory`, el `done` antes del remember y el abismo; 3 el banco, los umbrales, la carga, la aduana, el guardia anti-torch y las docs; 4 el fixture, el smoke y el cierre. La 2 necesita la 1 (`memoria_embed`, `Memory(embed=)`, `recall_ok`), la 3 la 1 (`OllamaEmbed.embed`) y la 2 (`sin_reindexar`, el vigia), la 4 la 2 (`--embeddings`) y la 3 (`ollama_evict(embedding=True)`, los umbrales). Cada task termina en un commit con la suite verde.

Rama de trabajo: `feat/memoria-ollama` en el worktree `/var/home/pedro/calipso/.claude/worktrees/memoria-ollama` (ya existe, HEAD `2276fcf`). Antes de la Task 1: `cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama && git status --short` (limpio) y `git log --oneline -1` (anotar el commit desde el que se arranca en el reporte de la task).

---

### Task 1: `calipso/memoria_embed.py` (la EF por Ollama, `EmbedFalsa`, `texto_para_embedding`, `_post_embed`) + `Memory(embed=)`, `CALIPSO_EMBED_FALSA`, `episodic-<tag>`, recall fail-open de una sola embedding, `remember` con embeddings explicitos + tests

**Files:**
- Create: `calipso/memoria_embed.py`, `test_memoria_embed.py`
- Modify: `calipso/config.py:9-11`; `calipso/memory.py:36-46`, `:56-66`, `:92-118`, `:120-130`, `:159-172`, `:203-215`; `conftest.py:46-47`; `test_aduana_canario.py:44-49`, `:58`; `test_abismo_memoria_recall.py` (entero); `test_memoria_ambito.py:15-17`, `:40-46`, `:130-153`; `test_memoria_carta.py:69-72`
- Test: `test_memoria_embed.py`, `test_abismo_memoria_recall.py`, `test_memoria_ambito.py`, `test_memoria_carta.py`, `test_plantel_memoria.py`, `test_aduana_canario.py`, `test_aislacion_home.py`, `test_memoria_lectores.py`, `test_abismo_chat.py`

**Interfaces:**
- Consumes: `carga.payload_local(payload, nivel)`, `carga.nivel_reciente()`, `carga.usando()`, `carga.keep_alive(nivel)`, `carga.num_thread(nivel)` (existentes, `calipso/carga.py:448-511`); `memoria_procedencia.partir(texto) -> (pregunta, respuesta) | None` y `memoria_procedencia.limpiar_gestos(pregunta) -> str` (`calipso/memoria_procedencia.py:164-181`); `telemetry.log_event(kind, **data)`.
- Produces (lo que las Tasks 2-4 usan): en `calipso/config.py`: `EMBED_MODEL: str` (`"bge-m3:latest"`), `EMBED_DIMS: int` (1024), `EMBED_URL: str`. En `calipso/memoria_embed.py`: `TIMEOUT_RECALL_S = 10.0`, `TIMEOUT_REMEMBER_S = 120.0`, `LOTE_CHARS = 8000`, `PALABRAS_RESPUESTA = 150`, `PALABRAS_OTRO = 300`, `class EmbedError(RuntimeError)`, `embed_tag(nombre: str) -> str`, `EMBED_TAG: str` (`"bge-m3"`), `COLECCION_VIEJA = "episodic"`, `COLECCION_VIVA: str` (`"episodic-bge-m3"`), `texto_para_embedding(doc: str, palabras: int | None = None) -> str` (None = `PALABRAS_RESPUESTA` leido por llamada), `lotes(textos: list[str], max_chars: int | None = None) -> list[list[str]]`, `_post_embed(url: str, payload: dict, timeout: float) -> dict`, `class OllamaEmbed(EmbeddingFunction[Documents])` con `__init__(url=None, model=None, dims=None, timeout=TIMEOUT_REMEMBER_S)`, `embed(textos: list[str], timeout: float | None = None) -> list[list[float]]`, `__call__(input)`, `name() -> "calipso_ollama"`, `get_config() -> {url, model, dims}`, `build_from_config(config)` (classmethod), `class EmbedFalsa(OllamaEmbed)` con `.llamadas: list[list[str]]`, `embedder_por_env() -> OllamaEmbed`, `embeber(ef, textos, timeout=None) -> list[list[float]]`, `ids_de(cliente, nombre) -> set[str] | None`, `sin_reindexar(cliente) -> int`. En `calipso/memory.py`: `Memory(project_root=None, embed=None)`, `Memory.recall_ok: bool`, `Memory.ultimo_recall_fallo: dict | None` (`{"ts", "error"}`), `Memory.recall(query, n=5, ambitos=None) -> list[dict]` (fail-open), `Scope.recall(query, n=5, embedding=None)`, `Scope._embed` (la MISMA referencia que `Memory._embed` al construirse; un test que cambie la EF despues tiene que cambiarla en la Memory y en cada Scope, ver `_matar` en `test_memoria_server.py`), `Scope._client`, `memory.COLECCION` (= `COLECCION_VIVA`), `memory.EMBED_MODEL` (= `config.EMBED_MODEL`). Fila de telemetria: `kind: "memoria", accion: "recall_fallo", error: str`.

- [ ] **Step 1: `calipso/config.py` -- el modelo, las dims y la URL del embedder**

ANTES (`calipso/config.py:9-11`):

```python
CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
CONFIG_FILE = CALIPSO_HOME / "config.json"
```

DESPUES:

```python
CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
CONFIG_FILE = CALIPSO_HOME / "config.json"

# El embedder de la memoria episodica vive en Ollama (spec memoria por Ollama
# 2026-09-12). Vive ACA y no en memory.py (ruling 8.11) para que `carga` lo
# lea sin arrastrar chromadb. EMBED_MODEL es el nombre TAL COMO lo devuelve
# /api/ps (`bge-m3:latest`; `bge-m3` a secas no matchea, ruling 8.1); el tag
# de la coleccion (`bge-m3`) lo deriva memoria_embed.embed_tag. Las
# dimensiones son fijas por config (ruling 8.2: nada consulta /api/show al
# construir la funcion de embeddings; cambiar de modelo es cambiar las dos
# variables juntas y reindexar). La URL es la del Ollama local; el smoke la
# apunta a un proxy para cortarla a mitad.
EMBED_MODEL = os.environ.get("CALIPSO_EMBED_MODEL", "bge-m3:latest")
EMBED_DIMS = int(os.environ.get("CALIPSO_EMBED_DIMS", "1024"))
EMBED_URL = os.environ.get("CALIPSO_EMBED_URL", "http://localhost:11434")
```

- [ ] **Step 2: `calipso/memoria_embed.py`, completo**

```python
"""La funcion de embeddings de la memoria episodica: `bge-m3` en Ollama por
`POST /api/embed`, sin torch en el proceso (spec memoria por Ollama
2026-09-12, seccion 2).

Puro salvo el POST a loopback, que vive en la funcion de modulo
`_post_embed` (el canario de la aduana arma su clave con nombres de funcion,
no de clase: `calipso/memoria_embed.py:_post_embed` esta en EXCEPCIONES).

`OllamaEmbed` es la EF que chroma persiste en el esquema de la coleccion
(`name() = "calipso_ollama"`, `get_config() = {url, model, dims}`) y
reconstruye con `build_from_config` al crear la coleccion y DOS veces por
cada upsert/update (sondeado sobre chromadb 1.5.9): por eso es PURA al
construirse (ruling 8.2): sin red, sin disco, dims fijas por config. Nadie
deja que chroma la llame para embeber: `Scope.remember` y el reindex embeben
por afuera con `embeber(...)` y pasan `embeddings=` explicitos; `recall`
consulta con `query_embeddings`. Asi los timeouts van por uso (ruling 8.7):
recall 10 s (el turno sigue sin recuerdos), remember y reindex 120 s por
lote; y los lotes son por tamano (<= LOTE_CHARS por request; un documento
largo va solo), no por cantidad.

`EmbedFalsa` (hash determinista a EMBED_DIMS, sin red) es la de la suite:
`memory.Memory()` la elige con `CALIPSO_EMBED_FALSA=1`, que conftest.py fija
antes de importar calipso (ruling 8.10). Es HIJA de `OllamaEmbed` y comparte
nombre y config: el esquema persistido en la suite es el mismo que en
produccion, y el fixture generado con la EF real se abre con la falsa sin
conflicto (chroma compara solo `name()`).

Lo que se embebe (ruling 8.5): `texto_para_embedding(doc)` = la pregunta de
Pedro (limpia de gestos) y las primeras 150 palabras de la respuesta, sin las
etiquetas del par. MiniLM veia 128 tokens (la pregunta y el arranque de la
respuesta); el par entero de 2-6k chars queda dominado por la respuesta y
cuesta 2-5 s. El documento guardado no cambia.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request

import numpy as np
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.errors import NotFoundError
from chromadb.utils.embedding_functions import register_embedding_function

from calipso import carga
from calipso import config as calipso_config
from calipso import memoria_procedencia

TIMEOUT_RECALL_S = 10.0       # el turno sigue sin recuerdos (ruling 8.7)
TIMEOUT_REMEMBER_S = 120.0    # remember y reindex, por lote
LOTE_CHARS = 8000             # lotes por tamano, no por cantidad
PALABRAS_RESPUESTA = 150      # ruling 8.5; el banco mide 0 / 150 / par entero (10_000); lo fija el Step 10 de la Task 3
PALABRAS_OTRO = 300           # un documento que no es un par (meta, ficha del jefe): fijo, no depende del de arriba


class EmbedError(RuntimeError):
    """Ollama no contesto, contesto otra cosa o con otras dimensiones."""


def embed_tag(nombre: str) -> str:
    """El nombre del modelo saneado para el nombre de la coleccion: sin
    `:latest` y solo `[a-zA-Z0-9._-]` (chroma rechaza `episodic-bge-m3:latest`
    con InvalidArgumentError; sondeado). `bge-m3:latest` -> `bge-m3`."""
    base = nombre[:-len(":latest")] if nombre.endswith(":latest") else nombre
    tag = re.sub(r"[^a-zA-Z0-9._-]+", "-", base).strip("-._")
    return tag or "sin-modelo"


EMBED_TAG = embed_tag(calipso_config.EMBED_MODEL)
COLECCION_VIEJA = "episodic"                  # MiniLM, 384 dims: solo origen del reindex
COLECCION_VIVA = f"episodic-{EMBED_TAG}"      # la que abre Scope


def texto_para_embedding(doc: str, palabras: int | None = None) -> str:
    """Lo que se embebe de un episodio (ruling 8.5). Un par de chat: la
    pregunta limpia de gestos y las primeras `palabras` de la respuesta
    (PALABRAS_RESPUESTA si no viene, leido por llamada: el banco y sus tests
    pueden cambiar el numero), separadas por un salto de linea, sin las
    etiquetas. Otro formato (una meta, una ficha del jefe): sus primeras
    PALABRAS_OTRO palabras, sea cual sea `palabras` (con la variante
    pregunta sola, 0, una meta no puede quedar vacia)."""
    palabras = PALABRAS_RESPUESTA if palabras is None else palabras
    par = memoria_procedencia.partir(doc)
    if par is None:
        palabras_doc = (doc or "").split()
        if len(palabras_doc) <= PALABRAS_OTRO:
            return (doc or "").strip()          # entero, con sus saltos de linea
        return " ".join(palabras_doc[:PALABRAS_OTRO])
    pregunta, respuesta = par
    pregunta = memoria_procedencia.limpiar_gestos(pregunta) or pregunta
    cabeza = " ".join(respuesta.split()[:palabras])
    return f"{pregunta}\n{cabeza}".strip()


def lotes(textos: list[str], max_chars: int | None = None) -> list[list[str]]:
    """Parte `textos` en lotes contiguos de a lo sumo `max_chars` (suma de
    largos; LOTE_CHARS si no viene, leido por llamada para que un test lo
    pueda bajar); un texto mas largo que el tope va solo en su lote. Conserva
    el orden: el llamador alinea las respuestas por posicion."""
    max_chars = LOTE_CHARS if max_chars is None else max_chars
    salida: list[list[str]] = []
    actual: list[str] = []
    largo = 0
    for t in textos:
        if actual and largo + len(t) > max_chars:
            salida.append(actual)
            actual, largo = [], 0
        actual.append(t)
        largo += len(t)
    if actual:
        salida.append(actual)
    return salida


def _post_embed(url: str, payload: dict, timeout: float) -> dict:
    """El unico POST del modulo: `{base}/api/embed` por urllib, loopback (no
    cruza la aduana; entrada en EXCEPCIONES del canario). Cualquier fallo
    (conexion, timeout, HTTP, JSON) es EmbedError."""
    datos = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=datos, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise EmbedError(f"POST {url}: {e}") from e


@register_embedding_function
class OllamaEmbed(EmbeddingFunction[Documents]):
    """La EF de produccion. Pura al construirse (ruling 8.2)."""

    def __init__(self, url: str | None = None, model: str | None = None,
                 dims: int | None = None, timeout: float = TIMEOUT_REMEMBER_S) -> None:
        self.url = (url or calipso_config.EMBED_URL).rstrip("/")
        self.model = model or calipso_config.EMBED_MODEL
        self.dims = int(dims or calipso_config.EMBED_DIMS)
        self.timeout = timeout

    def embed(self, textos: list[str], timeout: float | None = None) -> list[list[float]]:
        """Los vectores de `textos`, en orden, por lotes de LOTE_CHARS, con el
        payload pasado por `carga.payload_local` (num_thread y keep_alive por
        nivel: un solo camino a Ollama, invariante 5) y dentro de
        `carga.usando()` (el vigia no descarga a mitad). Una lista vacia
        devuelve [] sin POST (chroma revienta con `ef([])`)."""
        textos = list(textos)
        if not textos:
            return []
        nivel = carga.nivel_reciente()
        salida: list[list[float]] = []
        with carga.usando():
            for lote in lotes(textos):
                payload = carga.payload_local(
                    {"model": self.model, "input": lote, "truncate": True}, nivel)
                datos = _post_embed(f"{self.url}/api/embed", payload, timeout or self.timeout)
                vectores = datos.get("embeddings") if isinstance(datos, dict) else None
                if not isinstance(vectores, list) or len(vectores) != len(lote):
                    cuantos = len(vectores) if isinstance(vectores, list) else "?"
                    raise EmbedError(f"{self.model}: esperaba {len(lote)} vectores y vinieron {cuantos}")
                for v in vectores:
                    if not isinstance(v, list) or len(v) != self.dims:
                        raise EmbedError(f"{self.model}: vector de {len(v) if isinstance(v, list) else '?'} "
                                         f"dimensiones; la config dice {self.dims}")
                    salida.append([float(x) for x in v])
        return salida

    def __call__(self, input: Documents) -> Embeddings:
        # la firma exacta que chroma valida (self, input); en produccion nadie
        # llega por aca (embeddings explicitos), pero queda para una EF pasada
        # a mano a chroma
        return [np.array(v, dtype=np.float32) for v in self.embed(list(input))]

    @staticmethod
    def name() -> str:
        return "calipso_ollama"

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def get_config(self) -> dict:
        return {"url": self.url, "model": self.model, "dims": self.dims}

    @classmethod
    def build_from_config(cls, config: dict) -> "OllamaEmbed":
        # puro: chroma lo llama al crear la coleccion y dos veces por upsert
        return cls(url=config.get("url"), model=config.get("model"), dims=config.get("dims"))

    @staticmethod
    def validate_config(config: dict) -> None:
        return None

    def validate_config_update(self, old_config: dict, new_config: dict) -> None:
        return None


class EmbedFalsa(OllamaEmbed):
    """La EF de la suite: un vector determinista por hash del texto (sha256
    repetido hasta EMBED_DIMS, normalizado), sin red. Mismo texto, mismo
    vector: consultar con el texto exacto de lo embebido da distancia 0.
    `llamadas` guarda cada lista de textos que se le pidio (los tests cuentan
    embeddings por recall)."""

    def __init__(self, url: str | None = None, model: str | None = None,
                 dims: int | None = None, timeout: float = TIMEOUT_REMEMBER_S) -> None:
        super().__init__(url=url, model=model, dims=dims, timeout=timeout)
        self.llamadas: list[list[str]] = []

    def embed(self, textos: list[str], timeout: float | None = None) -> list[list[float]]:
        textos = list(textos)
        self.llamadas.append(list(textos))
        salida = []
        for t in textos:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            crudo = np.frombuffer((h * (self.dims // len(h) + 1))[: self.dims],
                                  dtype=np.uint8).astype(np.float32)
            salida.append((crudo / np.linalg.norm(crudo)).tolist())
        return salida


def embedder_por_env() -> OllamaEmbed:
    """La EF que `Memory()` construye si no le inyectan una: la falsa con
    `CALIPSO_EMBED_FALSA=1` (la suite), la real si no."""
    if os.environ.get("CALIPSO_EMBED_FALSA") == "1":
        return EmbedFalsa()
    return OllamaEmbed()


def embeber(ef, textos: list[str], timeout: float | None = None) -> list[list[float]]:
    """La unica costura para pedir vectores con timeout por uso: las EFs de
    Calipso tienen `embed(textos, timeout=)`; una EF ajena de chroma (una
    inyectada en `Memory(embed=)`) se llama con `__call__` y se convierte."""
    if hasattr(ef, "embed"):
        return ef.embed(list(textos), timeout=timeout)
    return [[float(x) for x in v] for v in ef(list(textos))]


def ids_de(cliente, nombre: str) -> set[str] | None:
    """Los ids de la coleccion `nombre` del cliente, o None si no existe.
    `get(include=[])` no reconstruye la EF persistida ni importa nada."""
    try:
        col = cliente.get_collection(nombre, embedding_function=None)
    except NotFoundError:
        return None
    return set(col.get(include=[])["ids"])


def sin_reindexar(cliente) -> int:
    """Cuantos documentos de la vieja `episodic` no estan en `episodic-<tag>`
    (invariante 3: se ve hasta que sea 0). Es EL calculo: lo usan el server
    (`/api/memory`, el arranque) y el reindex (`--vista`, `--embeddings`)."""
    viejos = ids_de(cliente, COLECCION_VIEJA)
    if not viejos:
        return 0
    vivos = ids_de(cliente, COLECCION_VIVA) or set()
    return len(viejos - vivos)
```

- [ ] **Step 3: `conftest.py` -- `CALIPSO_EMBED_FALSA=1` antes de importar calipso**

ANTES (`conftest.py:46-47`):

```python
_HOME_SUITE = pathlib.Path(tempfile.mkdtemp(prefix="calipso_suite_home_"))
os.environ["CALIPSO_HOME"] = str(_HOME_SUITE)
```

DESPUES:

```python
_HOME_SUITE = pathlib.Path(tempfile.mkdtemp(prefix="calipso_suite_home_"))
os.environ["CALIPSO_HOME"] = str(_HOME_SUITE)
# La memoria embebe por Ollama (spec 2026-09-12, ruling 8.10): en la suite
# NADIE llama a Ollama. Con esta variable `memory.Memory()` construye
# `memoria_embed.EmbedFalsa` (hash determinista, 1024 dims, sin red), y tiene
# que estar puesta ANTES del primer import de calipso por la misma razon que
# CALIPSO_HOME: varios tests importan `calipso.server` a nivel de modulo y
# eso construye `Memory()` en el acto. Se pisa siempre: un `0` exportado en
# la shell convertiria la suite en 200 POSTs a Ollama.
os.environ["CALIPSO_EMBED_FALSA"] = "1"
```

- [ ] **Step 4: los tests nuevos de la EF y de `Memory` (en rojo)**

`test_memoria_embed.py`, completo:

```python
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
```

- [ ] **Step 5: verlos fallar**

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama && nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q test_memoria_embed.py -p no:cacheprovider 2>&1 | tail -3
# ModuleNotFoundError: No module named 'calipso.memoria_embed' (el archivo del Step 2 todavia no existe si se
# escribieron los tests primero; con el modulo ya escrito, fallan los de Memory: TypeError: Memory.__init__()
# got an unexpected keyword argument 'embed' y la coleccion sigue llamandose 'episodic')
```

- [ ] **Step 6: `calipso/memory.py` -- sin torch, `episodic-<tag>`, embeddings explicitos, una embedding, fail-open**

ANTES (`calipso/memory.py:36-46`):

```python
from calipso import aduana

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))

# Modelo multilingüe local; se descarga automáticamente en el primer uso (~470 MB).
EMBED_MODEL = os.environ.get("CALIPSO_EMBED_MODEL",
                             "paraphrase-multilingual-MiniLM-L12-v2")
```

DESPUES:

```python
from calipso import aduana, telemetry
from calipso import config as calipso_config
from calipso import memoria_embed

import chromadb

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))

# El embedder vive en Ollama (spec memoria por Ollama 2026-09-12): el nombre
# en calipso.config (EMBED_MODEL = "bge-m3:latest", ruling 8.11) y la
# coleccion viva lleva el tag (`episodic-bge-m3`). La vieja `episodic`
# (MiniLM, 384 dims, EF sentence_transformer persistida) queda intacta en el
# mismo sqlite hasta que `memoria_reindex --embeddings` la copie: chroma
# prohibe cambiar la clase de EF de una coleccion y las dims no coinciden.
# Este modulo ya no importa torch ni sentence_transformers.
EMBED_MODEL = calipso_config.EMBED_MODEL
COLECCION = memoria_embed.COLECCION_VIVA
```

ANTES (`calipso/memory.py:56-66`):

```python
    def __init__(self, name: str, core_dir: pathlib.Path,
                 chroma_dir: pathlib.Path, embed) -> None:
        self.name = name
        self.core_dir = pathlib.Path(core_dir)
        self.core_dir.mkdir(parents=True, exist_ok=True)
        chroma_dir = pathlib.Path(chroma_dir)
        chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._col = self._client.get_or_create_collection(
            "episodic", embedding_function=embed,
            metadata={"hnsw:space": "cosine"})
```

DESPUES:

```python
    def __init__(self, name: str, core_dir: pathlib.Path,
                 chroma_dir: pathlib.Path, embed) -> None:
        self.name = name
        self.core_dir = pathlib.Path(core_dir)
        self.core_dir.mkdir(parents=True, exist_ok=True)
        chroma_dir = pathlib.Path(chroma_dir)
        chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._embed = embed
        # la EF se pasa para que chroma persista su esquema (name + config) y
        # el hnsw sea coseno; los vectores llegan siempre explicitos
        self._col = self._client.get_or_create_collection(
            COLECCION, embedding_function=embed,
            metadata={"hnsw:space": "cosine"})
```

ANTES (`calipso/memory.py:113-118`, el cierre de `Scope.remember`; el docstring queda):

```python
        clean = {k: v for k, v in meta.items() if v is not None}
        clean["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
        huella = repr((text, sorted(clean.items())))
        mem_id = "m" + hashlib.sha256(huella.encode("utf-8")).hexdigest()[:24]
        self._col.upsert(documents=[text], metadatas=[clean], ids=[mem_id])
        return mem_id
```

DESPUES:

```python
        clean = {k: v for k, v in meta.items() if v is not None}
        clean["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
        huella = repr((text, sorted(clean.items())))
        mem_id = "m" + hashlib.sha256(huella.encode("utf-8")).hexdigest()[:24]
        # el vector se calcula por afuera sobre la pregunta + 150 palabras de
        # respuesta (memoria_embed.texto_para_embedding, ruling 8.5) y va
        # explicito: chroma no llama a la EF. El documento sigue siendo el par.
        vector = memoria_embed.embeber(
            self._embed, [memoria_embed.texto_para_embedding(text)],
            timeout=memoria_embed.TIMEOUT_REMEMBER_S)
        self._col.upsert(documents=[text], metadatas=[clean], ids=[mem_id],
                         embeddings=vector)
        return mem_id
```

ANTES (`calipso/memory.py:120-130`):

```python
    def recall(self, query: str, n: int = 5) -> list[dict]:
        total = self._col.count()
        if total == 0:
            return []
        res = self._col.query(query_texts=[query], n_results=min(n, total))
        out = []
```

DESPUES:

```python
    def recall(self, query: str, n: int = 5, embedding=None) -> list[dict]:
        """Los `n` episodios mas cercanos de ESTE ambito. Con `embedding`
        (el vector de `query`, que `Memory.recall` calcula UNA vez para todos
        los ambitos) no embebe nada; sin el, embebe: es la costura vieja. No
        atrapa: el fail-open vive en `Memory.recall`, el unico punto de
        entrada del server."""
        total = self._col.count()
        if total == 0:
            return []
        if embedding is None:
            embedding = memoria_embed.embeber(
                self._embed, [query], timeout=memoria_embed.TIMEOUT_RECALL_S)[0]
        res = self._col.query(query_embeddings=[embedding], n_results=min(n, total))
        out = []
```

ANTES (`calipso/memory.py:159-172`):

```python
class Memory:
    """Fachada: une los ámbitos global y de proyecto."""

    def __init__(self, project_root: str | None = None) -> None:
        self._embed = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
        g = CALIPSO_HOME / "global"
```

DESPUES:

```python
class Memory:
    """Fachada: une los ámbitos global y de proyecto."""

    # el estado del ultimo recall (spec memoria por Ollama, ruling 8.8: fail-open
    # VISIBLE): los lee `GET /api/memory` y la fuente `memoria` del abismo.
    # Defaults de clase para que los dobles construidos con `__new__` los tengan.
    recall_ok: bool = True
    ultimo_recall_fallo: dict | None = None

    def __init__(self, project_root: str | None = None, embed=None) -> None:
        # la EF es barata y pura (ruling 8.2): `_switch_project` la reconstruye
        # en el loop sin costo. `embed=` es para inyectar una en los tests;
        # sin ella, la real, o la falsa con CALIPSO_EMBED_FALSA=1 (conftest)
        self._embed = embed or memoria_embed.embedder_por_env()
        g = CALIPSO_HOME / "global"
```

ANTES (`calipso/memory.py:203-215`):

```python
    def recall(self, query: str, n: int = 5,
               ambitos: tuple[str, ...] | None = None) -> list[dict]:
        """ambitos=None: la fusion de siempre (global+proyecto). Con ambitos,
        solo los scopes nombrados -- la consulta dirigida del abismo. El
        umbral sigue viviendo en el llamador (server.py para el turno,
        abismo/fuentes.py para la consulta)."""
        scopes = [s for s in self._scopes
                  if ambitos is None or s.name in ambitos]
        hits = []
        for s in scopes:
            hits += s.recall(query, n)
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:n]
```

DESPUES:

```python
    def recall(self, query: str, n: int = 5,
               ambitos: tuple[str, ...] | None = None) -> list[dict]:
        """ambitos=None: la fusion de siempre (global+proyecto). Con ambitos,
        solo los scopes nombrados -- la consulta dirigida del abismo. El
        umbral sigue viviendo en el llamador (server.py para el turno,
        abismo/fuentes.py para la consulta).

        Una sola embedding por turno, y ninguna si no hay que buscar (spec
        memoria por Ollama, seccion 2): primero que ambitos tienen episodios;
        si ninguno, [] sin tocar Ollama (la suite y un home nuevo); si alguno,
        la pregunta se embebe UNA vez y cada ambito consulta con ese vector.

        FAIL-OPEN de verdad (invariante 2): cualquier excepcion (Ollama caido,
        timeout, coleccion rota) devuelve [] con la fila `kind: memoria,
        accion: recall_fallo` y deja `recall_ok`/`ultimo_recall_fallo` para
        que la memoria muerta no quede escondida (ruling 8.8). El recall del
        turno corre fuera del try del turno (server.py): antes una excepcion
        aca tumbaba el websocket."""
        scopes = [s for s in self._scopes
                  if ambitos is None or s.name in ambitos]
        try:
            poblados = [s for s in scopes if s.count() > 0]
            if not poblados:
                return []
            vector = memoria_embed.embeber(
                self._embed, [query], timeout=memoria_embed.TIMEOUT_RECALL_S)[0]
            hits = []
            for s in poblados:
                hits += s.recall(query, n, embedding=vector)
        except Exception as e:
            self.recall_ok = False
            self.ultimo_recall_fallo = {
                "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "error": str(e)[:300]}
            telemetry.log_event("memoria", accion="recall_fallo", error=str(e)[:300])
            return []
        self.recall_ok = True
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:n]
```

- [ ] **Step 7: los tests que cambian de letra**

`test_abismo_memoria_recall.py`, entero (reemplaza las 38 lineas):

```python
"""Memory.recall abierto a consultas por ambito (spec seccion 7), y de una
sola embedding con guardia de count (spec memoria por Ollama 2026-09-12).

Sin chroma: se prueba el ruteo de scopes con dobles que respetan la costura
nueva -- `count()` (la guardia) y `recall(query, n, embedding=None)` (el
vector viene calculado una vez desde Memory) -- y con `EmbedFalsa`, que no
toca la red y anota cada lista de textos que embebio.
"""
from calipso import memoria_embed, memory


class _FalsoScope:
    def __init__(self, name, hits):
        self.name = name
        self._hits = hits
        self.vectores = []

    def count(self):
        return len(self._hits)

    def recall(self, query, n, embedding=None):
        self.vectores.append(embedding)
        return [dict(h, scope=self.name) for h in self._hits]


def _mem_doble():
    m = memory.Memory.__new__(memory.Memory)
    m._embed = memoria_embed.EmbedFalsa()
    m.glob = _FalsoScope("global", [{"text": "g1", "score": 0.9},
                                    {"text": "g2", "score": 0.5}])
    m.project = _FalsoScope("project", [{"text": "p1", "score": 0.7}])
    m._deps = {}
    return m


def test_sin_ambitos_es_la_conducta_de_hoy():
    hits = _mem_doble().recall("q", n=3)
    assert [h["text"] for h in hits] == ["g1", "p1", "g2"]  # fusion por score


def test_ambitos_filtra_por_nombre():
    hits = _mem_doble().recall("q", n=5, ambitos=("global",))
    assert {h["scope"] for h in hits} == {"global"}


def test_ambito_inexistente_devuelve_vacio():
    assert _mem_doble().recall("q", n=5, ambitos=("departamento:taller",)) == []


def test_una_sola_embedding_para_todos_los_ambitos_y_ninguna_sin_episodios():
    m = _mem_doble()
    m.recall("q", n=3)
    assert m._embed.llamadas == [["q"]]
    assert m.glob.vectores == m.project.vectores and len(m.glob.vectores) == 1
    assert m.glob.vectores[0] == m._embed.embed(["q"])[0]
    vacia = _mem_doble()
    vacia.glob = _FalsoScope("global", [])
    vacia.project = _FalsoScope("project", [])
    assert vacia.recall("q", n=3) == [] and vacia._embed.llamadas == []


def test_un_embedder_caido_es_fail_open_con_fila(monkeypatch):
    filas = []
    monkeypatch.setattr(memory.telemetry, "log_event", lambda kind, **k: filas.append({"kind": kind, **k}))

    class _Caido(memoria_embed.EmbedFalsa):
        def embed(self, textos, timeout=None):
            raise memoria_embed.EmbedError("connection refused")
    m = _mem_doble()
    m._embed = _Caido()
    assert m.recall("q", n=3) == []
    assert m.recall_ok is False and m.ultimo_recall_fallo["error"] == "connection refused"
    assert filas == [{"kind": "memoria", "accion": "recall_fallo", "error": "connection refused"}]
    assert m.glob.vectores == []          # no llego a consultar ningun ambito
```

`test_memoria_ambito.py`: tres bloques.

ANTES (`test_memoria_ambito.py:15-17`):

```python
Los tres se comprueban sin cargar el modelo de embeddings: el ruteo se prueba
sobre `Memory.remember` con ambitos falsos, y el sitio de llamada se lee del
fuente, porque vive adentro de un handler de websocket.
```

DESPUES:

```python
Los tres se comprueban sin construir una Memory real (abre dos clientes de
chroma): el ruteo se prueba sobre `Memory.remember` con ambitos falsos, y el
sitio de llamada se lee del fuente, porque vive adentro de un handler de
websocket.
```

ANTES (`test_memoria_ambito.py:40-46`):

```python
def mem():
    """Una Memory sin construir: `__init__` carga los pesos del embebedor
    (unos siete segundos) y aca no hace falta ni uno."""
    m = memory.Memory.__new__(memory.Memory)
```

DESPUES:

```python
def mem():
    """Una Memory sin construir: `__init__` abre dos clientes de chroma y aca
    no hace falta ninguno."""
    m = memory.Memory.__new__(memory.Memory)
```

ANTES (`test_memoria_ambito.py:144-153`):

```python
    def upsert(self, documents, metadatas, ids):
        self.llamadas.append("upsert")
        self.docs[ids[0]] = documents[0]             # upsert SI pisa


@pytest.fixture
def ambito():
    s = memory.Scope.__new__(memory.Scope)
    s._col = _ColeccionFalsa()
    return s
```

DESPUES:

```python
    def upsert(self, documents, metadatas, ids, embeddings=None):
        self.llamadas.append("upsert")
        self.docs[ids[0]] = documents[0]             # upsert SI pisa
        self.vectores = embeddings                   # explicitos desde Scope.remember


@pytest.fixture
def ambito():
    s = memory.Scope.__new__(memory.Scope)
    s._col = _ColeccionFalsa()
    s._embed = memoria_embed.EmbedFalsa()            # remember embebe por afuera, sin red
    return s
```

Y el import del archivo: ANTES `from calipso import memory` (linea 24) -> DESPUES `from calipso import memoria_embed, memory`.

`test_memoria_carta.py`, ANTES (`:69-72`):

```python
    Y se prueba asi a proposito: `Memory.__init__` carga un modelo de
    embeddings (`SentenceTransformerEmbeddingFunction`), asi que construir
    una para comprobar una ruta seria un test lento y fragil por un motivo
    ajeno a lo que prueba.
```

DESPUES:

```python
    Y se prueba asi a proposito: `Memory.__init__` abre dos clientes de
    chroma y crea directorios, asi que construir una para comprobar una
    ruta seria un test con efectos por un motivo ajeno a lo que prueba.
```

`test_aduana_canario.py`: ANTES (`:49`):

```python
    "calipso/carga.py:ollama_evict": "loopback: Ollama (keep_alive 0 del vigia)",
```

DESPUES:

```python
    "calipso/carga.py:ollama_evict": "loopback: Ollama (keep_alive 0 del vigia)",
    "calipso/memoria_embed.py:_post_embed": "loopback: Ollama (/api/embed del embedder de la memoria, bge-m3; spec memoria por Ollama 2026-09-12). La memoria ya no sale a huggingface.co",
```

ANTES (`:58`):

```python
    "calipso/tools/commands.py:run": "subprocesos de la allowlist: git local y tests; `test_memory` sale a la red desde OTRO proceso (test_memory.py construye Memory() -> huggingface.co y llama reflect -> `claude -p`), fuera de la aduana: limite conocido, como los CLIs agentes",
```

DESPUES:

```python
    "calipso/tools/commands.py:run": "subprocesos de la allowlist: git local y tests; `test_memory` habla con Ollama en loopback desde OTRO proceso (test_memory.py construye Memory() -> POST /api/embed) y llama reflect -> `claude -p`, fuera de la aduana: limite conocido, como los CLIs agentes",
```

- [ ] **Step 8: verde, archivo por archivo y la suite entera**

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama
nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q -p no:cacheprovider test_memoria_embed.py test_abismo_memoria_recall.py test_memoria_ambito.py test_memoria_carta.py test_plantel_memoria.py test_aduana_canario.py test_aislacion_home.py test_memoria_lectores.py 2>&1 | tail -1
# 25 nuevos en test_memoria_embed + 5 en test_abismo_memoria_recall; 0 failed
nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q -p no:cacheprovider test_abismo_chat.py test_memoria_reindex.py 2>&1 | tail -1
# el harness sigue con MemoriaFalsa; el reindex sobre la vieja sigue igual (memoria_reindex no cambia en esta task)
CALIPSO_HOME=$(mktemp -d) nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m calipso.carga --esperar; echo ESPERA=$?
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama && nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q --ignore=test_chat_live.py -p no:cacheprovider 2>&1 | tail -1; echo EXIT=$?
# 0 failed, EXIT=0. Anotar en el reporte el total y el tiempo: es la linea base de la rama.
```

Si `test_aduana_api.py:434-449` falla: no deberia (el server sigue declarando "modelo de embeddings" con `motivo=EMBED_MODEL`, ahora `bge-m3:latest`; eso se corrige en la Task 3). Si un test viejo que construye `Memory()` real levanta `ValueError ... conflict: new: calipso_ollama vs persisted: sentence_transformer`, es que abrio `episodic` en vez de `episodic-<tag>`: revisar el DESPUES de `Scope.__init__`.

- [ ] **Step 9: Commit**

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama
git add calipso/memoria_embed.py calipso/config.py calipso/memory.py conftest.py test_memoria_embed.py test_abismo_memoria_recall.py test_memoria_ambito.py test_memoria_carta.py test_aduana_canario.py
git commit -m "feat(memoria): la memoria embebe por Ollama -- calipso/memoria_embed.py con OllamaEmbed (registrada en chroma como calipso_ollama, pura al construirse, dims fijas por config, POST /api/embed por urllib en _post_embed con carga.payload_local y carga.usando(), lotes por tamano, timeouts por uso), EmbedFalsa determinista para la suite (CALIPSO_EMBED_FALSA=1 en conftest antes de importar), texto_para_embedding = pregunta limpia + 150 palabras; EMBED_MODEL/EMBED_DIMS/EMBED_URL en config.py; memory.py sin torch: Memory(embed=), coleccion episodic-<tag>, remember con embeddings explicitos, Scope.recall(query, n, embedding=None), Memory.recall con guardia de count, una sola embedding y fail-open con fila recall_fallo + recall_ok/ultimo_recall_fallo; la entrada de _post_embed en el canario; 30 tests sin Ollama

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N3P8mZgfi31VYnG8sweiAa"
```

---

### Task 2: `memoria_reindex --embeddings` (sin `--forzar`, lotes por tamano, doble lista de ids) + `--vista/--aplicar` sobre la viva + `sin_reindexar`, `recall_ok` y `ultimo_recall_fallo` en `/api/memory` y en el arranque + el `done` antes del remember (tareas de fondo) + `memoria_no_disponible` en el abismo + tests

**Files:**
- Modify: `calipso/memory.py` (tras `Scope.count`, tras `Memory.recall`); `calipso/memoria_reindex.py:1-9`, `:48-54`, `:103-109`, `:173-218`; `calipso/server.py` (antes de `_medir_carga` `:2434`; `api_memory` `:5319-5326`; `_startup_warm` `:8794-8798`; `ws_chat` `:4748-4795` y `:4818-4826`); `calipso/abismo/fuentes.py:19-21`, `:119-122`; `calipso/abismo/turno.py:18-19`, `:131-135`; `test_abismo_chat.py:150-160`; `test_memoria_ambito.py:82-96`; `test_memoria_reindex.py:1-10`, `:42-47`, `:165-169`
- Create: `test_memoria_server.py`
- Test: `test_memoria_server.py`, `test_memoria_reindex.py`, `test_abismo_chat.py`, `test_carga_chat.py`, `test_memoria_ambito.py`, `test_abismo_turno.py`, `test_aduana_api.py`, `test_memoria_embed.py`

**Interfaces:**
- Consumes (Task 1): `memoria_embed.COLECCION_VIVA`, `COLECCION_VIEJA`, `ids_de(cliente, nombre)`, `sin_reindexar(cliente)`, `embeber(ef, textos, timeout)`, `texto_para_embedding(doc)`, `lotes(textos)`, `embedder_por_env()`, `TIMEOUT_REMEMBER_S`; `Memory.recall_ok`, `Memory.ultimo_recall_fallo`; `Scope._client`.
- Produces: `Scope.sin_reindexar() -> int`, `Memory.sin_reindexar() -> dict[str, int]`; en `memoria_reindex`: `COLECCION_VIEJA`, `COLECCION_VIVA`, `abrir(cliente) -> tuple[col | None, str | None]`, `reindexar_embeddings(cliente, ef) -> dict` (`{copiados, actualizados, aparecidos, sin_reindexar, sin_vieja}`), `_linea_estado(nombre, cliente, coleccion=None) -> str`, `main(argv, salida)` con `--embeddings`; en `server.py`: `_TAREAS_DE_FONDO: set[asyncio.Task]`, `_en_fondo(coro) -> asyncio.Task`, `_anunciar_memoria() -> None`, `GET /api/memory` con `sin_reindexar: {ambito: N}`, `recall_ok: bool`, `ultimo_recall_fallo: dict | None`; filas `kind: memoria` con `accion` `sin_reindexar` (`ambito`, `n`) y `remember_fallo` (`error`); en el abismo: `fuentes.MemoriaNoDisponible`, `fuentes.AVISO_MEMORIA_NO_DISPONIBLE = "la memoria no esta disponible"`, `"memoria_no_disponible"` en `turno.MOTIVOS` y en `turno.motivo_de_consulta`; en el harness: `Harness.esperar_fondo(plazo=5.0)`.

- [ ] **Step 1: los tests del reindex `--embeddings` y de `--vista/--aplicar` sobre la viva (en rojo)**

`test_memoria_reindex.py`: cambia el docstring, `_leer` gana `nombre`, y se agregan los tests al final.

ANTES (`test_memoria_reindex.py:1-10`):

```python
"""El reindexado sobre un home temporal (spec 2026-09-11, secciones 3 y 5):
`--vista` no escribe; `--aplicar` conserva ids, documentos, embeddings y
cantidad, preserva las claves viejas y agrega `procedencia` y `ruta`; es
idempotente; cuenta lo que no parsea; se niega con el puerto ocupado y
sigue con `--forzar`. Al final, sobre una copia del fixture real del porton.

Los chromas de prueba se arman SIN modelo (embeddings explicitos): asi el
test tarda medio segundo y no depende del cache de HuggingFace. El del
fixture real trae la funcion de embeddings persistida y `update` la carga
(offline, del cache; ~5 s la primera vez en el proceso)."""
```

DESPUES:

```python
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
```

ANTES (`test_memoria_reindex.py:42-47`):

```python
def _leer(chroma_dir: pathlib.Path) -> dict:
    col = chromadb.PersistentClient(path=str(chroma_dir)).get_collection("episodic")
    g = col.get(include=["documents", "metadatas", "embeddings"])
```

DESPUES:

```python
def _leer(chroma_dir: pathlib.Path, nombre: str = "episodic") -> dict:
    col = chromadb.PersistentClient(path=str(chroma_dir)).get_collection(nombre, embedding_function=None)
    g = col.get(include=["documents", "metadatas", "embeddings"])
```

ANTES (`test_memoria_reindex.py:165-169`):

```python
def test_un_directorio_chroma_sin_la_coleccion_se_salta(home):
    d = home / "projects" / "otro" / "chroma"
    chromadb.PersistentClient(path=str(d))          # crea el sqlite, sin coleccion
    codigo, texto = _correr("--vista")
    assert codigo == 0 and "projects/otro: sin coleccion episodic (se salta)" in texto
```

DESPUES:

```python
def test_un_directorio_chroma_sin_la_coleccion_se_salta(home):
    d = home / "projects" / "otro" / "chroma"
    chromadb.PersistentClient(path=str(d))          # crea el sqlite, sin coleccion
    codigo, texto = _correr("--vista")
    assert codigo == 0 and "projects/otro: sin coleccion episodic-bge-m3 ni episodic (se salta)" in texto
    codigo, texto = _correr("--embeddings")
    assert codigo == 0 and "projects/otro: sin coleccion episodic (se salta)" in texto
```

Al final del archivo (despues de `test_sobre_una_copia_del_fixture_real`), agregar; y arriba, el import `from calipso import memoria_embed as me` junto a `from calipso import memoria_reindex as mr`:

```python
# --- el reindex a otro embedder: --embeddings (spec memoria por Ollama 2026-09-12) ---

VIVA = me.COLECCION_VIVA


def _por_id(leido: dict) -> dict:
    return {i: (d, m) for i, d, m in zip(leido["ids"], leido["docs"], leido["metas"])}


def test_embeddings_copia_la_vieja_a_la_viva_con_los_mismos_ids_documentos_y_metadatos(home):
    g = home / "global" / "chroma"
    antes = _leer(g)
    codigo, texto = _correr("--embeddings")
    assert codigo == 0, texto
    assert f"global: 6 copiados a {VIVA}, 0 ya estaban (metadatos actualizados), sin_reindexar 0" in texto
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
    assert _correr("--embeddings")[0] == 0
    codigo, texto = _correr("--aplicar")
    assert codigo == 0 and "global: 4 episodios reindexados; count 6 -> 6" in texto
    assert f"(procedencia sobre {VIVA})" in texto
    despues_a = _leer(g, VIVA)
    assert _por_id(despues_a)["m1"][1]["procedencia"] == 1
    codigo, texto = _correr("--embeddings")
    assert codigo == 0 and f"global: 0 copiados a {VIVA}, 6 ya estaban (metadatos actualizados), sin_reindexar 0" in texto
    assert _leer(g, VIVA) == despues_a                         # update mergea: la procedencia queda
    assert _por_id(_leer(g))["m1"][1].get("procedencia") is None   # la vieja sigue sin marcar


def test_aplicar_antes_de_embeddings_tambien_converge(home):
    g = home / "global" / "chroma"
    codigo, texto = _correr("--aplicar")                       # no hay viva: cae a la vieja
    assert codigo == 0 and "global: 4 episodios reindexados" in texto
    assert "(procedencia sobre episodic)" in texto
    assert _por_id(_leer(g))["m1"][1]["procedencia"] == 1
    assert _correr("--embeddings")[0] == 0
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
    assert _correr("--embeddings")[0] == 0
    codigo, texto = _correr("--vista")
    assert f"global: 6 en episodic, 6 en {VIVA}, sin_reindexar 0 (procedencia sobre {VIVA})" in texto
    # un episodio nuevo en la vieja (un server viejo que siguio escribiendo) vuelve a contar
    chromadb.PersistentClient(path=str(g)).get_collection("episodic", embedding_function=None).add(
        ids=["m7"], documents=[CHAT_DATO], metadatas=[{"ts": "2026-09-12T10:00:00", "kind": "chat"}],
        embeddings=[[0.7, 0.2, 0.3]])
    assert "sin_reindexar 1" in _correr("--vista")[1]
    codigo, texto = _correr("--embeddings")
    assert f"global: 1 copiados a {VIVA}, 6 ya estaban" in texto and "sin_reindexar 0" in texto


def test_embeddings_se_niega_con_el_puerto_ocupado_y_no_admite_forzar(home, monkeypatch):
    # con el puerto LIBRE (el fixture deja CALIPSO_PORT=1) --forzar tambien se rechaza: no existe en este modo
    codigo, texto = _correr("--embeddings", "--forzar")
    assert codigo == 2 and "no admite --forzar" in texto
    assert me.ids_de(chromadb.PersistentClient(path=str(home / "global" / "chroma")), VIVA) is None
    escucha = socket.socket()
    escucha.bind(("127.0.0.1", 0))
    escucha.listen(1)
    monkeypatch.setenv("CALIPSO_PORT", str(escucha.getsockname()[1]))
    try:
        codigo, texto = _correr("--embeddings")
        assert codigo == 2 and "no admite --forzar" in texto
        codigo, texto = _correr("--embeddings", "--forzar")
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
    codigo, texto = _correr("--embeddings")
    assert codigo == 0
    assert "OJO: aparecieron 1 ids en episodic durante la corrida" in texto
    assert "global: 6 copiados" in texto and "sin_reindexar 1" in texto


def test_embeddings_copia_sin_metadatos_y_deja_sin_reindexar_lo_que_no_tiene_documento(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    monkeypatch.setenv("CALIPSO_PORT", "1")
    col = _sembrar(tmp_path / "global" / "chroma", [])
    col.add(ids=["r1"], documents=[CHAT_DATO], embeddings=[[0.1, 0.2, 0.3]])       # sin meta
    col.add(ids=["r2"], embeddings=[[0.2, 0.2, 0.3]])                              # sin documento
    codigo, texto = _correr("--embeddings")
    assert codigo == 0 and "global: 1 copiados" in texto and "sin_reindexar 1" in texto
    viva = _leer(tmp_path / "global" / "chroma", VIVA)
    assert viva["ids"] == ["r1"] and viva["metas"] == [None]
```

- [ ] **Step 2: los tests del server y del abismo (en rojo)**

`test_memoria_server.py`, completo:

```python
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
```

- [ ] **Step 3: verlos fallar**

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama && nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q -p no:cacheprovider test_memoria_reindex.py test_memoria_server.py 2>&1 | tail -3
# SystemExit: 2 (argparse: unrecognized arguments: --embeddings); AttributeError: 'Memory' object has no
# attribute 'sin_reindexar'; AttributeError: module 'calipso.server' has no attribute '_anunciar_memoria';
# KeyError: 'sin_reindexar'; AttributeError: module 'calipso.abismo.fuentes' has no attribute 'AVISO_MEMORIA_NO_DISPONIBLE'
```

- [ ] **Step 4: `calipso/memory.py` -- `sin_reindexar` por ambito**

ANTES (`calipso/memory.py`, el cierre de `Scope`):

```python
    def count(self) -> int:
        return self._col.count()
```

DESPUES:

```python
    def count(self) -> int:
        return self._col.count()

    def sin_reindexar(self) -> int:
        """Los episodios de la coleccion vieja `episodic` que todavia no estan
        en la viva (spec memoria por Ollama, invariante 3). Mismo calculo que
        el reindex (`memoria_embed.sin_reindexar`); solo ids, sin EF."""
        return memoria_embed.sin_reindexar(self._client)
```

ANTES (`calipso/memory.py`, el cierre de `Memory.recall`, ya con el DESPUES de la Task 1):

```python
        self.recall_ok = True
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:n]
```

DESPUES:

```python
        self.recall_ok = True
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:n]

    def sin_reindexar(self) -> dict[str, int]:
        """Por ambito de la lectura combinada (`{"global": N, "project": N}`):
        lo que `GET /api/memory` devuelve y el arranque anuncia."""
        return {s.name: s.sin_reindexar() for s in self._scopes}
```

- [ ] **Step 5: `calipso/memoria_reindex.py` -- `--embeddings`, `abrir` viva-o-vieja, la linea de estado**

ANTES (`calipso/memoria_reindex.py:1-9`):

```python
"""El reindexado de la memoria episodica con procedencia (spec 2026-09-11,
seccion 3): un solo tiro sobre el home, con el server apagado, que agrega a
cada episodio VIEJO que parsea como par de chat los metadatos que lo nuevo ya
trae (`procedencia=1`, `ruta` = la `route` decidida, unica disponible),
conservando id, documento, embedding y cantidad.

    python -m calipso.memoria_reindex --vista      # cuenta, no escribe
    python -m calipso.memoria_reindex --aplicar    # escribe (merge, idempotente)
    python -m calipso.memoria_reindex --aplicar --forzar   # con el server prendido
```

DESPUES:

```python
"""El reindexado de la memoria episodica: la procedencia (spec 2026-09-11,
seccion 3) y el cambio de embedder (spec memoria por Ollama 2026-09-12): un
solo tiro sobre el home, con el server apagado. `--aplicar` agrega a cada
episodio VIEJO que parsea como par de chat los metadatos que lo nuevo ya trae
(`procedencia=1`, `ruta` = la `route` decidida), conservando id, documento,
embedding y cantidad. `--embeddings` copia la coleccion vieja `episodic`
(MiniLM, 384 dims) a la viva `episodic-<tag>` (`episodic-bge-m3`) con los
MISMOS ids, documentos y metadatos, embebiendo por Ollama en lotes por
tamano; idempotente (un id que ya esta solo converge sus metadatos); NO borra
la vieja; imprime cuantos copio y cuantos quedan.

    python -m calipso.memoria_reindex --vista        # cuenta (procedencia y sin_reindexar), no escribe
    python -m calipso.memoria_reindex --aplicar      # la procedencia (merge, idempotente)
    python -m calipso.memoria_reindex --aplicar --forzar   # con el server prendido
    python -m calipso.memoria_reindex --embeddings   # episodic -> episodic-<tag>; SOLO con el server apagado

`--vista` y `--aplicar` operan sobre la VIVA si existe y sobre la vieja si
no: `--embeddings` y luego `--aplicar`, o al reves, convergen. `--embeddings`
no admite `--forzar` (ruling 8.9): un corte no atomico entre las dos
colecciones no tiene arreglo despues; ademas toma la lista de ids de la
vieja antes y despues y, si aparecieron ids durante la corrida, lo dice y no
declara `sin_reindexar = 0`.
```

ANTES (`calipso/memoria_reindex.py:50-54`):

```python
from calipso import memoria_procedencia as mp  # noqa: E402

COLECCION = "episodic"
LOTE = 100
```

DESPUES:

```python
from calipso import memoria_embed  # noqa: E402  (registra la EF calipso_ollama en chroma)
from calipso import memoria_procedencia as mp  # noqa: E402

COLECCION_VIEJA = memoria_embed.COLECCION_VIEJA      # "episodic": MiniLM, solo origen
COLECCION_VIVA = memoria_embed.COLECCION_VIVA        # "episodic-<tag>": la que abre el server
LOTE = 100
```

ANTES (`calipso/memoria_reindex.py:103-109`):

```python
def abrir(chroma_dir: pathlib.Path):
    """La coleccion, o None si el directorio no la tiene."""
    cliente = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        return cliente.get_collection(COLECCION, embedding_function=None)
    except NotFoundError:
        return None
```

DESPUES:

```python
def abrir(cliente):
    """(coleccion, nombre) para la procedencia: la VIVA si existe, si no la
    vieja; (None, None) si el directorio no tiene ninguna. Sin EF: `get`,
    `count` y `update(ids, metadatas)` no embeben (en la viva reconstruyen
    `calipso_ollama`, que es pura; en la vieja, la ST persistida, de ahi el
    hub offline de arriba)."""
    for nombre in (COLECCION_VIVA, COLECCION_VIEJA):
        try:
            return cliente.get_collection(nombre, embedding_function=None), nombre
        except NotFoundError:
            continue
    return None, None


def _linea_estado(nombre: str, cliente, coleccion: str | None = None) -> str:
    """`<ambito>: N en episodic, M en episodic-<tag>, sin_reindexar K`; lo que
    `--vista` y `--aplicar` imprimen antes de la linea de procedencia."""
    partes = []
    for col in (COLECCION_VIEJA, COLECCION_VIVA):
        ids = memoria_embed.ids_de(cliente, col)
        partes.append(f"{len(ids)} en {col}" if ids is not None else f"sin {col}")
    texto = f"{nombre}: {', '.join(partes)}, sin_reindexar {memoria_embed.sin_reindexar(cliente)}"
    if coleccion:
        texto += f" (procedencia sobre {coleccion})"
    return texto


def reindexar_embeddings(cliente, ef) -> dict:
    """Copia `episodic` a `episodic-<tag>` por ids (spec memoria por Ollama,
    seccion 2): lee la vieja con `get` (sin EF: no importa torch), crea la
    viva con la EF nueva (chroma persiste name + config; los vectores van
    explicitos), hace `update(ids, metadatas)` para los ids que ya estan
    (convergen sin re-embeber) y `upsert` con embeddings de
    `texto_para_embedding` para los que faltan, por lotes de LOTE_CHARS.
    Un documento sin texto no se copia (queda en `sin_reindexar`); un
    metadato vacio va como None (chroma rechaza `{}`). Devuelve copiados,
    actualizados, los ids que aparecieron en la vieja durante la corrida y
    `sin_reindexar` al final."""
    try:
        vieja = cliente.get_collection(COLECCION_VIEJA, embedding_function=None)
    except NotFoundError:
        return {"copiados": 0, "actualizados": 0, "aparecidos": 0, "sin_reindexar": 0, "sin_vieja": True}
    viva = cliente.get_or_create_collection(COLECCION_VIVA, embedding_function=ef,
                                            metadata={"hnsw:space": "cosine"})
    ids_antes = set(vieja.get(include=[])["ids"])
    datos = vieja.get(include=["documents", "metadatas"])
    presentes = set(viva.get(include=[])["ids"])
    nuevos: list[tuple[str, str, dict | None]] = []
    ya: list[tuple[str, dict]] = []
    for id_, doc, meta in zip(datos["ids"], datos["documents"], datos["metadatas"]):
        meta_ = meta if isinstance(meta, dict) and meta else None
        if id_ in presentes:
            if meta_:
                ya.append((id_, meta_))
            continue
        if not isinstance(doc, str) or not doc.strip():
            continue
        nuevos.append((id_, doc, meta_))
    for i in range(0, len(ya), LOTE):
        lote = ya[i:i + LOTE]
        viva.update(ids=[p[0] for p in lote], metadatas=[p[1] for p in lote])
    copiados = 0
    textos = [memoria_embed.texto_para_embedding(doc) for _, doc, _ in nuevos]
    pos = 0
    for lote in memoria_embed.lotes(textos):
        tramo = nuevos[pos:pos + len(lote)]
        pos += len(lote)
        vectores = memoria_embed.embeber(ef, lote, timeout=memoria_embed.TIMEOUT_REMEMBER_S)
        viva.upsert(ids=[t[0] for t in tramo], documents=[t[1] for t in tramo],
                    metadatas=[t[2] for t in tramo], embeddings=vectores)
        copiados += len(tramo)
    ids_despues = set(vieja.get(include=[])["ids"])
    vivos = set(viva.get(include=[])["ids"])
    return {"copiados": copiados, "actualizados": len(ya),
            "aparecidos": len(ids_despues - ids_antes),
            "sin_reindexar": len(ids_despues - vivos), "sin_vieja": False}
```

ANTES (`calipso/memoria_reindex.py:173-218`, `main` entero):

```python
def main(argv: list[str] | None = None, salida=None) -> int:
    salida = salida or sys.stdout
    ap = argparse.ArgumentParser(prog="python -m calipso.memoria_reindex",
                                 description=__doc__.split("\n\n")[0])
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--vista", action="store_true", help="contar, no escribir")
    modo.add_argument("--aplicar", action="store_true", help="escribir los metadatos")
    ap.add_argument("--forzar", action="store_true",
                    help="aplicar aunque el server responda en CALIPSO_PORT")
    args = ap.parse_args(argv)
    base = home()
    print(f"home: {base}", file=salida)
    if args.aplicar and _server_prendido(puerto()):
        if not args.forzar:
            print(f"el server responde en el puerto {puerto()}: apagalo (o --forzar). "
                  "No es por integridad -- dos clientes no corrompen el chroma -- "
                  "sino para que el recorrido sea completo: un server vivo sigue "
                  "escribiendo episodios.", file=salida)
            return 2
        print(f"el server responde en el puerto {puerto()}; --forzar: sigo", file=salida)
    lista = ambitos(base)
    if not lista:
        print("ningun ambito con chroma bajo el home", file=salida)
        return 1
    for nombre, chroma_dir in lista:
        col = abrir(chroma_dir)
        if col is None:
            print(f"{nombre}: sin coleccion {COLECCION} (se salta)", file=salida)
            continue
        r = revisar(col)
        print(_linea(nombre, r), file=salida)
        if not args.aplicar:
            continue
        if not r["pendientes"]:
            print(f"{nombre}: nada que escribir (ya reindexado o sin pares de chat)", file=salida)
            continue
        n = aplicar(col, r)
        despues = col.count()
        print(f"{nombre}: {n} episodios reindexados; count {r['episodios']} -> {despues}"
              + ("" if despues == r["episodios"] else "  OJO: la cantidad cambio durante la corrida"),
              file=salida)
    return 0
```

DESPUES:

```python
def main(argv: list[str] | None = None, salida=None) -> int:
    salida = salida or sys.stdout
    ap = argparse.ArgumentParser(prog="python -m calipso.memoria_reindex",
                                 description=__doc__.split("\n\n")[0])
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--vista", action="store_true", help="contar (procedencia y sin_reindexar), no escribir")
    modo.add_argument("--aplicar", action="store_true", help="escribir los metadatos de procedencia")
    modo.add_argument("--embeddings", action="store_true",
                      help=f"copiar {COLECCION_VIEJA} a {COLECCION_VIVA} embebiendo por Ollama "
                           "(solo con el server apagado; sin --forzar)")
    ap.add_argument("--forzar", action="store_true",
                    help="aplicar aunque el server responda en CALIPSO_PORT (no vale con --embeddings)")
    args = ap.parse_args(argv)
    if args.embeddings and args.forzar:
        # antes de mirar el puerto: con --embeddings, --forzar no existe (ruling 8.9),
        # tambien con el server apagado
        print("--embeddings no admite --forzar (ruling 8.9): corre siempre con el server apagado; "
              "un corte no atomico entre las dos colecciones no tiene arreglo despues.", file=salida)
        return 2
    base = home()
    print(f"home: {base}", file=salida)
    if args.embeddings and _server_prendido(puerto()):
        print(f"el server responde en el puerto {puerto()}: apagalo. --embeddings no admite --forzar "
              "(ruling 8.9): un corte no atomico entre las dos colecciones no tiene arreglo despues.",
              file=salida)
        return 2
    if args.aplicar and _server_prendido(puerto()):
        if not args.forzar:
            print(f"el server responde en el puerto {puerto()}: apagalo (o --forzar). "
                  "No es por integridad -- dos clientes no corrompen el chroma -- "
                  "sino para que el recorrido sea completo: un server vivo sigue "
                  "escribiendo episodios.", file=salida)
            return 2
        print(f"el server responde en el puerto {puerto()}; --forzar: sigo", file=salida)
    lista = ambitos(base)
    if not lista:
        print("ningun ambito con chroma bajo el home", file=salida)
        return 1
    ef = memoria_embed.embedder_por_env() if args.embeddings else None
    for nombre, chroma_dir in lista:
        cliente = chromadb.PersistentClient(path=str(chroma_dir))
        if args.embeddings:
            r = reindexar_embeddings(cliente, ef)
            if r["sin_vieja"]:
                print(f"{nombre}: sin coleccion {COLECCION_VIEJA} (se salta)", file=salida)
                continue
            print(f"{nombre}: {r['copiados']} copiados a {COLECCION_VIVA}, {r['actualizados']} ya estaban "
                  f"(metadatos actualizados), sin_reindexar {r['sin_reindexar']}"
                  + (f"  OJO: aparecieron {r['aparecidos']} ids en {COLECCION_VIEJA} durante la corrida"
                     if r["aparecidos"] else ""),
                  file=salida)
            continue
        col, coleccion = abrir(cliente)
        if col is None:
            print(f"{nombre}: sin coleccion {COLECCION_VIVA} ni {COLECCION_VIEJA} (se salta)", file=salida)
            continue
        print(_linea_estado(nombre, cliente, coleccion), file=salida)
        r = revisar(col)
        print(_linea(nombre, r), file=salida)
        if not args.aplicar:
            continue
        if not r["pendientes"]:
            print(f"{nombre}: nada que escribir (ya reindexado o sin pares de chat)", file=salida)
            continue
        n = aplicar(col, r)
        despues = col.count()
        print(f"{nombre}: {n} episodios reindexados; count {r['episodios']} -> {despues}"
              + ("" if despues == r["episodios"] else "  OJO: la cantidad cambio durante la corrida"),
              file=salida)
    return 0
```

- [ ] **Step 6: `calipso/server.py` -- las tareas de fondo, el anuncio, `/api/memory`, el arranque**

ANTES (`calipso/server.py:2434`, la firma de `_medir_carga`; el bloque nuevo va ANTES de ella):

```python
def _medir_carga(ps_timeout: float | None = None) -> carga.Carga:
```

DESPUES:

```python
# --- las tareas de fondo del server (spec memoria por Ollama 2026-09-12, ruling 8.3) ---
# El remember del turno corre DESPUES del `done` como tarea del loop; el
# conjunto las retiene (asyncio solo guarda referencias debiles) y el harness
# de los tests lo espera (`Harness.esperar_fondo`) para que las aserciones
# sobre la memoria no sean una carrera.
_TAREAS_DE_FONDO: set[asyncio.Task] = set()


def _en_fondo(coro) -> asyncio.Task:
    tarea = asyncio.create_task(coro)
    _TAREAS_DE_FONDO.add(tarea)
    tarea.add_done_callback(_TAREAS_DE_FONDO.discard)
    return tarea


def _anunciar_memoria() -> None:
    """En hilo desde `_startup_warm`: cuantos episodios de la coleccion vieja
    `episodic` faltan en `episodic-<tag>` por ambito (spec memoria por Ollama,
    invariante 3: se ve hasta que sea 0). Una linea por ambito con pendientes
    y la fila `kind: memoria, accion: sin_reindexar`. No se niega a arrancar
    (fail-open): si el chroma esta roto, el try del arranque se lo traga."""
    for ambito, n in mem.sin_reindexar().items():
        if n:
            print(f"[calipso] memoria: {n} episodios sin reindexar en {ambito} "
                  f"(python -m calipso.memoria_reindex --embeddings, con el server apagado)")
            telemetry.log_event("memoria", accion="sin_reindexar", ambito=ambito, n=n)


def _medir_carga(ps_timeout: float | None = None) -> carga.Carga:
```

ANTES (`calipso/server.py:5319-5326`):

```python
@app.get("/api/memory")
def api_memory() -> dict:
    """Estado de la memoria (para el panel / debugging)."""
    return {
        "core": mem.load_core(),
        "global_episodes": mem.glob.count(),
        "project_episodes": mem.project.count() if mem.project else 0,
    }
```

DESPUES:

```python
@app.get("/api/memory")
def api_memory() -> dict:
    """Estado de la memoria (para el panel / debugging), con lo que la memoria
    por Ollama deja a la vista (spec 2026-09-12, ruling 8.8): cuantos episodios
    viejos faltan en la coleccion viva por ambito, y si el ultimo recall salio
    (`recall_ok`) o cuando y por que fallo (`ultimo_recall_fallo`)."""
    return {
        "core": mem.load_core(),
        "global_episodes": mem.glob.count(),
        "project_episodes": mem.project.count() if mem.project else 0,
        "sin_reindexar": mem.sin_reindexar() if hasattr(mem, "sin_reindexar") else {},
        "recall_ok": bool(getattr(mem, "recall_ok", True)),
        "ultimo_recall_fallo": getattr(mem, "ultimo_recall_fallo", None),
    }
```

ANTES (`calipso/server.py:8794-8798`, en `_startup_warm`):

```python
    try:
        await asyncio.to_thread(_calentar_probes)  # declara la memoria y los probes, pre-calienta el cache
    except Exception:
        pass
    await asyncio.to_thread(_asegurar_rutina_catastro)
```

DESPUES:

```python
    try:
        await asyncio.to_thread(_calentar_probes)  # declara la memoria y los probes, pre-calienta el cache
    except Exception:
        pass
    try:
        await asyncio.to_thread(_anunciar_memoria)  # sin_reindexar por ambito: una linea y una fila (fail-open)
    except Exception:
        pass
    await asyncio.to_thread(_asegurar_rutina_catastro)
```

- [ ] **Step 7: `calipso/server.py` -- el remember del turno DESPUES del `done`, como tarea de fondo**

Dos bloques en `ws_chat`. Verificar la unicidad antes de tocar: `grep -c '# 5) recordar el intercambio (episodica)' calipso/server.py` -> 1; `grep -c '_last_features = features' calipso/server.py` -> 1.

ANTES (`calipso/server.py:4748-4795`; el bloque entero del paso 5 mas las dos lineas que siguen):

```python
            # 5) recordar el intercambio (episodica)
            #
            # Tres cosas se arreglaron aca el 2026-08-31, y las tres son la
            # misma clase de error: lo que se guarda mal se recupera mal, y
            # nadie se entera porque no levanta ninguna excepcion.
            #
            # 1. El literal tenia las dos vocales acentuadas doble-encodeadas
            #    (el mojibake clasico: una A con tilde donde va la vocal), asi
            #    que la cadena rota se EMBEBIA tal cual y cada intercambio
            #    degradaba su propia recuperacion. No se transcribe aca a
            #    proposito: escribirla para explicarla es como vuelve.
            # 2. Iba a `scope="auto"`, que es "el proyecto si hay proyecto"
            #    (memory.py:187-194) -- y el chat SIEMPRE tiene proyecto. O
            #    sea que la vida de Pedro se archivaba bajo el repo que
            #    tuviera abierto, y el ambito global termino con cero filas
            #    despues de dos meses. Va a global: en la conversacion la
            #    constante es Pedro, el repo es la variable. Lo que si es
            #    del proyecto lo escriben los que hablan del proyecto
            #    (reflect, el bibliotecario, el jefe de departamento).
            # 3. Corria sobre el event loop, a diferencia del `remember` de
            #    la meta ocho lineas mas arriba (:2377), que ya va por hilo.
            #
            # Y la procedencia (spec 2026-09-11, seccion 2): el par sigue
            # siendo el documento (el embedding no cambia), pero la pregunta
            # es la LIMPIA (`chat_msg`, sin el `/local` de adelante) y los
            # metadatos dicen quien contesto de verdad: `ruta` es la USADA
            # (`used_route`: local tras un fallback, orchestrator con equipo,
            # subscription con el alterno; `route` sigue siendo la decidida),
            # `modelo` el que contesto, `chat` el id y `procedencia=1` la
            # marca para contar y para la idempotencia del reindex. Lo que
            # sea None lo descarta `Scope.remember`. Se lee con
            # `memoria_procedencia.presentar`, nunca crudo.
            # Y los canarios (spec 2026-09-11): dos numeros del veredicto,
            # `degeneracion` y `sin_anclaje` (None si el canario fallo).
            # El aviso de Ollama caido no entra: no es una respuesta.
            if full.strip() and not aviso_local_caido:
                try:
                    await asyncio.to_thread(
                        mem.remember,
                        f"Pedro pregunto: {chat_msg}\nCalipso respondio: {full.strip()}",
                        scope="global", route=verdict["route"], kind="chat",
                        ruta=used_route, modelo=model, chat=chat_id, procedencia=1,
                        **canarios.resumen_de_remember(veredicto))
                except Exception:
                    pass    # recordar no puede voltear un turno ya contestado
            if full.strip():
                chats.append(chat_id, "assistant", full.strip(), {
```

DESPUES:

```python
            # 5) el mensaje al chat. El remember del intercambio (episodica)
            # corre como tarea de fondo que arranca cuando el `done` ya salio
            # (spec memoria por Ollama 2026-09-12, ruling 8.3): es el paso 6,
            # al final de este turno.
            if full.strip():
                chats.append(chat_id, "assistant", full.strip(), {
```

ANTES (`calipso/server.py:4818-4826`):

```python
            _last_features = features
            _last_verdict = verdict
            uso_local.soltar()
            await ws.send_json({"type": "done"})
    except WebSocketDisconnect:
        pass
    finally:
        uso_local.soltar()       # una desconexion a mitad de turno no deja el contador en 1
        rtask.cancel()
```

DESPUES:

```python
            _last_features = features
            _last_verdict = verdict
            uso_local.soltar()
            # 6) recordar el intercambio (episodica), como tarea de fondo que
            # corre DESPUES del `done` (spec memoria por Ollama 2026-09-12,
            # ruling 8.3): con bge-m3 el embedding cuesta 0,4-4 s y antes se
            # ESPERABA antes del done, visible en `pensando`; el molde es el
            # remember de la meta (mas arriba), que ya iba despues de su done.
            # La tarea se PROGRAMA justo antes del send del done (create_task
            # no ejecuta nada: el remember arranca en la siguiente vuelta del
            # loop y va a un hilo, asi que el done sale igual de rapido) y no
            # despues: si el cliente corta justo en ese send, `send_json`
            # levanta y salta al `except WebSocketDisconnect`; con la tarea ya
            # creada el episodio se guarda igual (antes de este cambio tambien
            # se guardaba: corria antes del done).
            #
            # Tres cosas se arreglaron aca el 2026-08-31, y las tres son la
            # misma clase de error: lo que se guarda mal se recupera mal, y
            # nadie se entera porque no levanta ninguna excepcion.
            # 1. El literal tenia las dos vocales acentuadas doble-encodeadas
            #    (el mojibake clasico: una A con tilde donde va la vocal), asi
            #    que la cadena rota se EMBEBIA tal cual. No se transcribe aca
            #    a proposito: escribirla para explicarla es como vuelve.
            # 2. Iba a `scope="auto"`, que es "el proyecto si hay proyecto" --
            #    y el chat SIEMPRE tiene proyecto: la vida de Pedro se
            #    archivaba bajo el repo que tuviera abierto. Va a global: en
            #    la conversacion la constante es Pedro, el repo es la variable.
            # 3. Corria sobre el event loop: va por hilo (`asyncio.to_thread`).
            #
            # Y la procedencia (spec 2026-09-11, seccion 2): el par sigue
            # siendo el documento, la pregunta es la LIMPIA (`chat_msg`, sin
            # el `/local` de adelante) y los metadatos dicen quien contesto
            # de verdad: `ruta` es la USADA (`used_route`), `modelo` el que
            # contesto, `chat` el id y `procedencia=1` la marca. Lo que sea
            # None lo descarta `Scope.remember`. Los canarios suman
            # `degeneracion` y `sin_anclaje`. El aviso de Ollama caido no
            # entra: no es una respuesta. Un fallo (Ollama caido al embeber,
            # chroma roto) deja la fila `kind: memoria, accion: remember_fallo`:
            # recordar no puede voltear un turno ya contestado, pero tampoco
            # puede fallar en silencio (fail-open visible, ruling 8.8).
            if full.strip() and not aviso_local_caido:
                episodio = f"Pedro pregunto: {chat_msg}\nCalipso respondio: {full.strip()}"
                meta_episodio = dict(
                    scope="global", route=verdict["route"], kind="chat",
                    ruta=used_route, modelo=model, chat=chat_id, procedencia=1,
                    **canarios.resumen_de_remember(veredicto))

                async def _recordar(texto=episodio, meta=meta_episodio):
                    try:
                        await asyncio.to_thread(mem.remember, texto, **meta)
                    except Exception as e:
                        telemetry.log_event("memoria", accion="remember_fallo", error=str(e)[:300])
                _en_fondo(_recordar())
            await ws.send_json({"type": "done"})
    except WebSocketDisconnect:
        pass
    finally:
        uso_local.soltar()       # una desconexion a mitad de turno no deja el contador en 1
        rtask.cancel()
```

El orden importa y lo fija el fixture `turno` de `test_memoria_ambito.py` (Step 9): `_en_fondo(` ANTES de `{"type": "done"}` en el bloque. El `done` sigue saliendo antes de que se embeba nada: `create_task` solo programa; `test_el_remember_del_turno_corre_despues_del_done_como_tarea_de_fondo` (Step 2) lo mide con la puerta.

- [ ] **Step 8: el abismo -- `memoria_no_disponible`**

ANTES (`calipso/abismo/fuentes.py:19-21`):

```python
RECALL_N = 12
RECALL_TOP = 8
RECALL_UMBRAL = 0.20
```

DESPUES:

```python
RECALL_N = 12
RECALL_TOP = 8
RECALL_UMBRAL = 0.20

# el fail-open visible de la memoria (spec memoria por Ollama 2026-09-12,
# ruling 8.8): si el recall devolvio [] porque la memoria no esta (Ollama
# caido, coleccion rota), la fuente no puede cerrar con `vacio`. Se levanta
# con este aviso EXACTO; `consulta.resolver` lo vuelve `_fallo(fuente, aviso)`
# y `turno.motivo_de_consulta` lo mapea a `memoria_no_disponible`.
AVISO_MEMORIA_NO_DISPONIBLE = "la memoria no esta disponible"


class MemoriaNoDisponible(RuntimeError):
    pass
```

ANTES (`calipso/abismo/fuentes.py:119-122`):

```python
    recuerdos = memoria_procedencia.presentar_recuerdos(
        [h for h in mem.recall(pregunta, n=RECALL_N)
         if h.get("score", 0) >= RECALL_UMBRAL],
        RECALL_TOP)
```

DESPUES:

```python
    hits = mem.recall(pregunta, n=RECALL_N)
    if not hits and getattr(mem, "recall_ok", True) is False:
        raise MemoriaNoDisponible(AVISO_MEMORIA_NO_DISPONIBLE)
    recuerdos = memoria_procedencia.presentar_recuerdos(
        [h for h in hits if h.get("score", 0) >= RECALL_UMBRAL],
        RECALL_TOP)
```

ANTES (`calipso/abismo/turno.py:18-19`):

```python
MOTIVOS = ("vacio", "credencial", "solo_hondo", "juez_local_caido",
           "tipo_desconocido", "error")
```

DESPUES:

```python
MOTIVOS = ("vacio", "credencial", "solo_hondo", "juez_local_caido",
           "tipo_desconocido", "memoria_no_disponible", "error")
```

ANTES (`calipso/abismo/turno.py:131-135`):

```python
def motivo_de_consulta(resultado: dict) -> str:
    """El motivo de la senal `fallo` a partir de lo que devolvio
    `consulta.resolver`: la pesca vacia es `vacio` (el aviso exacto de
    consulta._fallo, "la consulta no trajo nada"); todo lo demas, `error`."""
    return "vacio" if resultado.get("aviso") == "la consulta no trajo nada" else "error"
```

DESPUES:

```python
def motivo_de_consulta(resultado: dict) -> str:
    """El motivo de la senal `fallo` a partir de lo que devolvio
    `consulta.resolver`: la pesca vacia es `vacio` (el aviso exacto de
    consulta._fallo, "la consulta no trajo nada"); la memoria muerta es
    `memoria_no_disponible` (el aviso exacto de fuentes.MemoriaNoDisponible,
    spec memoria por Ollama, ruling 8.8); todo lo demas, `error`."""
    aviso = resultado.get("aviso")
    if aviso == "la consulta no trajo nada":
        return "vacio"
    if aviso == "la memoria no esta disponible":
        return "memoria_no_disponible"
    return "error"
```

- [ ] **Step 9: los dos harness que leen el turno**

`test_abismo_chat.py`, ANTES (`:150-160`):

```python
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
```

DESPUES:

```python
    def turno(self, texto, departamento=None, hasta_dones=1):
        """Manda un paquete real y junta todo lo que el server emite hasta el
        `done` numero `hasta_dones` (2 cuando un steer encola otro turno), mas
        lo que siga durante `DRENAJE`: asi "un solo done" es una asercion de
        verdad y no una que solo podria fallar colgandose (un duplicado
        saldria del mismo camino microsegundos despues del primero). Antes de
        cerrar el socket espera las tareas de fondo del server (el remember
        del turno corre DESPUES del done, spec memoria por Ollama 2026-09-12):
        las aserciones sobre `memoria.recordado` no son una carrera."""
        with self.cliente.websocket_connect("/ws/chat") as ws:
            ws.send_text(self.paquete(texto, departamento))
            eventos = self.recibir(ws, hasta_dones)
            eventos.extend(lo_que_siga(ws, DRENAJE))
            self.esperar_fondo()
            return eventos

    @staticmethod
    def esperar_fondo(plazo: float = 5.0) -> None:
        """Hasta que ninguna tarea de `srv._TAREAS_DE_FONDO` siga viva. Se
        llama con el socket ABIERTO: el loop de la app vive en el portal del
        TestClient y al cerrar el socket una tarea pendiente se cancelaria.
        Poll desde el hilo del test (el conjunto muta en el otro hilo: un
        `list()` a mitad de mutacion se reintenta)."""
        limite = time.monotonic() + plazo
        while time.monotonic() < limite:
            try:
                vivas = [t for t in list(srv._TAREAS_DE_FONDO) if not t.done()]
            except RuntimeError:
                continue
            if not vivas:
                return
            time.sleep(0.01)
        raise AssertionError("quedaron tareas de fondo vivas tras el turno")
```

`test_memoria_ambito.py`, ANTES (`:82-96`):

```python
@pytest.fixture
def turno():
    """El bloque que recuerda el intercambio, del fuente del servidor.

    Acotado por los DOS extremos y no por una cuenta de caracteres: el
    archivo tiene mojibake en otros comentarios, asi que una ventana que se
    pasa de largo da un falso positivo; y una que se queda corta se pierde
    el `except`. Empieza en el comentario del paso 5 y termina donde arranca
    el paso siguiente, que guarda el mensaje en el chat."""
    fuente = pathlib.Path(
        memory.__file__).with_name("server.py").read_text(encoding="utf-8")
    i = fuente.index("recordar el intercambio")
    j = fuente.index("chats.append(chat_id, \"assistant\"", i)
    bloque = fuente[i:j]
    assert "mem.remember" in bloque, "el bloque no es el que se cree"
    return bloque
```

DESPUES:

```python
@pytest.fixture
def turno():
    """El bloque que recuerda el intercambio, del fuente del servidor.

    Acotado por los DOS extremos y no por una cuenta de caracteres: el
    archivo tiene mojibake en otros comentarios, asi que una ventana que se
    pasa de largo da un falso positivo; y una que se queda corta se pierde
    el `except`. Empieza en el comentario del paso 6 (el remember corre
    DESPUES del `done` como tarea de fondo, programada justo antes del send
    del done: spec memoria por Ollama 2026-09-12, ruling 8.3) y termina donde
    el handler atrapa la desconexion del websocket; el `done` queda adentro."""
    fuente = pathlib.Path(
        memory.__file__).with_name("server.py").read_text(encoding="utf-8")
    i = fuente.index("recordar el intercambio")
    j = fuente.index("except WebSocketDisconnect", i)
    bloque = fuente[i:j]
    assert "mem.remember" in bloque, "el bloque no es el que se cree"
    assert "_en_fondo(" in bloque, "el remember volvio a esperarse antes del done"
    assert '{"type": "done"}' in bloque, "el done salio del bloque: el remember quedo despues del send"
    assert bloque.index("_en_fondo(") < bloque.index('{"type": "done"}'), \
        "la tarea se crea DESPUES del send del done: un corte en ese send pierde el episodio"
    return bloque
```

- [ ] **Step 10: verde, archivo por archivo y la suite entera**

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama
nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q -p no:cacheprovider test_memoria_reindex.py test_memoria_server.py test_memoria_ambito.py test_abismo_turno.py test_memoria_embed.py 2>&1 | tail -1
# 7 nuevos en test_memoria_reindex + 7 en test_memoria_server; 0 failed
nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q -p no:cacheprovider test_abismo_chat.py test_carga_chat.py test_aduana_api.py test_abismo_nube.py test_canarios_anclaje.py test_canarios_degeneracion.py test_canarios_ventana.py 2>&1 | tail -1
# los harness con esperar_fondo; 0 failed (si un test viejo aserta `memoria.recordado` y falla, es la carrera:
# revisar que `esperar_fondo` corre ADENTRO del with)
CALIPSO_HOME=$(mktemp -d) nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q -p no:cacheprovider test_memoria_reindex.py::test_sobre_una_copia_del_fixture_real 2>&1 | tail -1
# sigue verde sobre la vieja (el fixture todavia no tiene la viva: Task 4); carga la ST persistida como hoy
CALIPSO_HOME=$(mktemp -d) nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m calipso.carga --esperar; echo ESPERA=$?
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama && nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q --ignore=test_chat_live.py -p no:cacheprovider 2>&1 | tail -1; echo EXIT=$?
# 0 failed, EXIT=0
```

- [ ] **Step 11: Commit**

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama
git add calipso/memory.py calipso/memoria_reindex.py calipso/server.py calipso/abismo/fuentes.py calipso/abismo/turno.py test_memoria_reindex.py test_memoria_server.py test_abismo_chat.py test_memoria_ambito.py
git commit -m "feat(memoria): el reindex a otro embedder y el server con la memoria a la vista -- memoria_reindex --embeddings copia episodic a episodic-<tag> por ids (lotes por tamano, update de metadatos para los presentes, doble lista de ids, sin --forzar), --vista imprime sin_reindexar sin embeber y --vista/--aplicar operan sobre la viva (o la vieja si no existe: los dos ordenes convergen); Scope/Memory.sin_reindexar; GET /api/memory con sin_reindexar, recall_ok y ultimo_recall_fallo; el arranque anuncia los pendientes (una linea + fila kind: memoria); el remember del turno corre DESPUES del done como tarea de fondo (_TAREAS_DE_FONDO/_en_fondo, fila remember_fallo) y el harness lo espera; la fuente memoria del abismo cierra con memoria_no_disponible; 14 tests sin Ollama

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N3P8mZgfi31VYnG8sweiAa"
```

---

### Task 3: el banco de recall (MiniLM contra bge-m3 en tres variantes), los umbrales PROVISORIOS con vuelta atras por env, la carga (`mismo_modelo`, `keep_alive_embed`, `payload_local(keep_alive=)`, `ollama_evict(embedding=True)`, el embedder en los modelos propios y en el vigia), la aduana (`_declarar_arranque` sin embeddings), el guardia anti-torch, docs + tests

**Files:**
- Create: `experimentos/recall_banco.py`, `experimentos/recall_banco_resultados.jsonl`, `experimentos/recall_banco_resultados.md`, `test_recall_umbrales.py`, `test_memoria_sin_torch.py`
- Modify: `calipso/carga.py:81-82`, `:396-406`, `:448-484`, `:587-601`, `:652-662`; `calipso/memoria_embed.py` (`OllamaEmbed.embed`); `calipso/memoria_procedencia.py` (al final); `calipso/server.py:104`, `:2171-2189`, `:3005`, `:5720-5733`, `:5756-5762`, `:8795`; `calipso/abismo/fuentes.py:19-21`; `test_memoria_embed.py` (`test_embed_manda_modelo_input_truncate_y_las_perillas_del_nivel`); `test_carga.py` (al final); `test_carga_vigia.py:143-147`; `test_aduana_api.py:434-449`, `:507-516`, `:587-600`; `AGENTS.md:430-431`; `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md` (al final)
- Test: `test_carga.py`, `test_carga_vigia.py`, `test_carga_sitios.py`, `test_carga_chat.py`, `test_aduana_api.py`, `test_aduana_canario.py`, `test_memoria_embed.py`, `test_recall_umbrales.py`, `test_memoria_sin_torch.py`, `test_memoria_lectores.py`, `test_abismo_turno.py`

**Interfaces:**
- Consumes (Task 1): `memoria_embed.OllamaEmbed().embed(textos, timeout)`, `texto_para_embedding(doc, palabras)`, `COLECCION_VIEJA`; `calipso_config.EMBED_MODEL`; (Task 2): `_vigia_del_modelo`, `_modelos_de_calipso` (existentes: `server.py:5720-5780`); `test_carga.medida`, `test_carga._Resp`, `test_carga.lector`.
- Produces: en `carga.py`: `mismo_modelo(a, b) -> bool`, `keep_alive_embed(nivel) -> str | int` (`"5m"` / `0` / `0`), `payload_local(payload, nivel=None, keep_alive=None)`, `ollama_evict(model, base=OLLAMA, timeout=None, embedding=False)`, `_modelos_configurados()` con el embedder; en `memoria_procedencia.py`: `umbral_por_env(nombre, default, alias=None) -> float`; en `server.py`: `_ollama_evict_embedding(nombre) -> bool` (hook), `_modelos_de_calipso()` con `calipso_config.EMBED_MODEL`, `RECALL_MIN_SCORE` por `CALIPSO_RECALL_MIN_SCORE` (alias `CALIPSO_RECALL_MIN`); en `fuentes.py`: `RECALL_UMBRAL` por `CALIPSO_RECALL_UMBRAL`; el banco: `python experimentos/recall_banco.py [--condiciones ...] [--home RUTA --reales JSON] [--listar-reales] [--informe] [--sin-esperar]`.

- [ ] **Step 1: los tests de la carga, la aduana y el vigia (en rojo)**

`test_carga.py`, al final del archivo:

```python
# --- el embedder de la memoria (spec memoria por Ollama 2026-09-12, rulings 8.1 y 8.4) ---

def test_mismo_modelo_normaliza_latest_a_los_dos_lados():
    assert carga.mismo_modelo("bge-m3:latest", "bge-m3") and carga.mismo_modelo("bge-m3", "bge-m3:latest")
    assert carga.mismo_modelo("qwen2.5:7b", "qwen2.5:7b")
    assert not carga.mismo_modelo("qwen2.5:7b", "qwen2.5:3b")
    assert not carga.mismo_modelo("bge-m3:latest", "bge-m3:v2")
    assert not carga.mismo_modelo("", "bge-m3") and not carga.mismo_modelo(None, None)


def test_medir_cuenta_el_embedder_en_la_memoria_efectiva_aunque_ps_diga_latest():
    ps = lambda: [{"name": "bge-m3:latest", "size_mb": 1219, "expires_at": ""}]
    c = carga.medir("qwen2.5:7b", leer=lector(), ps=ps, ncpu=16,
                    modelos_propios={"qwen2.5:7b", "bge-m3"})
    assert c.modelo_cargado_mb == 1219 and c.mem_efectiva_mb == c.mem_disponible_mb + 1219
    assert c.modelos_cargados == ["bge-m3:latest"]
    ajeno = carga.medir("qwen2.5:7b", leer=lector(), ps=ps, ncpu=16, modelos_propios={"qwen2.5:7b"})
    assert ajeno.modelo_cargado_mb == 0


def test_keep_alive_embed_es_la_tabla_propia_del_embedder():
    """holgada 5m; justa y cargada 0: embebe y suelta (ruling 8.4), sin
    convivir con el 7b cuando la memoria esta justa. La tabla del 7b no cambia."""
    assert carga.keep_alive_embed("holgada") == "5m" and carga.keep_alive_embed(None) == "5m"
    assert carga.keep_alive_embed("justa") == 0 and carga.keep_alive_embed("cargada") == 0
    assert "8.4" in carga.keep_alive_embed.__doc__
    assert carga.keep_alive("justa") == "2m" and carga.keep_alive("cargada") == "30s"


def test_payload_local_acepta_un_keep_alive_propio_sin_tocar_los_seis_sitios():
    base = {"model": "bge-m3:latest", "input": ["x"], "truncate": True}
    p = carga.payload_local(base, "justa", keep_alive=carga.keep_alive_embed("justa"))
    assert p["keep_alive"] == 0 and p["options"] == {"num_thread": carga.num_thread("justa")}
    assert carga.payload_local(base, "justa")["keep_alive"] == "2m"
    assert carga.payload_local(base, "holgada", keep_alive="5m") == {**base, "keep_alive": "5m"}
    assert base == {"model": "bge-m3:latest", "input": ["x"], "truncate": True}    # no muta


def test_ollama_evict_de_un_modelo_de_embedding_va_por_api_embed(monkeypatch):
    """A un modelo de solo embedding /api/generate puede rechazarlo: el ramal
    nuevo manda un /api/embed con keep_alive 0 (un `input` de un caracter:
    el vacio podria salir por la rama corta de Ollama sin tocar el runner).
    El camino del 7b queda byte a byte."""
    vistos = []

    def urlopen(req, timeout=None):
        vistos.append((req.full_url, json.loads(req.data.decode()), timeout))
        return _Resp(b"{}")
    monkeypatch.setattr(carga.urllib.request, "urlopen", urlopen)
    assert carga.ollama_evict("bge-m3:latest", embedding=True) is True
    assert vistos == [("http://localhost:11434/api/embed",
                       {"model": "bge-m3:latest", "input": "x", "truncate": True, "keep_alive": 0},
                       carga.UMBRALES["EVICT_TIMEOUT_S"])]
    assert carga.ollama_evict("qwen2.5:7b") is True
    assert vistos[-1][0] == "http://localhost:11434/api/generate"
    monkeypatch.setattr(carga.urllib.request, "urlopen",
                        lambda req, timeout=None: (_ for _ in ()).throw(OSError("x")))
    assert carga.ollama_evict("bge-m3:latest", embedding=True) is False


def test_los_modelos_configurados_suman_el_embedder():
    from calipso import config as calipso_config
    assert carga._modelos_configurados() == {"qwen2.5:7b", "qwen2.5:3b", calipso_config.EMBED_MODEL}
    assert "bge-m3:latest" in carga._modelos_configurados()
```

`test_carga_vigia.py`, ANTES (`:143-147`):

```python
def test_los_tres_modelos_de_calipso_son_los_de_config_y_el_de_vision(monkeypatch):
    assert srv._modelos_de_calipso() == {srv.dispatch.CONFIG["local"]["model"],
                                         srv.dispatch.CONFIG["classifier"]["model"]}
    monkeypatch.setattr(srv.attachments, "ollama_vision_model", lambda: "moondream")
    assert "moondream" in srv._modelos_de_calipso()
```

DESPUES:

```python
def test_los_modelos_de_calipso_son_los_de_config_el_embedder_y_el_de_vision(monkeypatch):
    assert srv._modelos_de_calipso() == {srv.dispatch.CONFIG["local"]["model"],
                                         srv.dispatch.CONFIG["classifier"]["model"],
                                         srv.calipso_config.EMBED_MODEL}
    assert "bge-m3:latest" in srv._modelos_de_calipso()
    monkeypatch.setattr(srv.attachments, "ollama_vision_model", lambda: "moondream")
    assert "moondream" in srv._modelos_de_calipso()


def test_bajo_cargada_el_embedder_listado_se_descarga_por_api_embed_sin_suspender(tick, monkeypatch):
    """El embedder es de Calipso (memoria efectiva y vigia, ruling 8.1) pero no
    es el modelo del chat: se descarga por el ramal /api/embed y NO suspende
    el local (la histeresis es del 7b). Con el 7b al lado, los dos, y la
    suspension es por el 7b. `bge-m3` sin `:latest` en /api/ps tambien matchea."""
    evictados_embed = []
    monkeypatch.setattr(srv, "_ollama_evict_embedding", lambda modelo: evictados_embed.append(modelo) or True)
    tick["correr"](medida("cargada", modelos=["bge-m3:latest"]))
    assert evictados_embed == ["bge-m3:latest"] and tick["evictados"] == []
    assert carga.local_suspendido is False
    fila = _de(tick["filas"], "descarga")[0]
    assert fila["modelo"] == "bge-m3:latest" and fila["ok"] is True and fila["nivel"] == "cargada"
    tick["correr"](medida("cargada", modelos=["qwen2.5:7b", "bge-m3"]))
    assert tick["evictados"] == ["qwen2.5:7b"] and evictados_embed == ["bge-m3:latest", "bge-m3"]
    assert carga.local_suspendido is True
    monkeypatch.setattr(srv, "_ollama_evict_embedding", lambda modelo: False)
    carga.olvidar()
    tick["correr"](medida("cargada", modelos=["bge-m3:latest"]))
    assert _de(tick["filas"], "descarga_fallida")[-1]["modelo"] == "bge-m3:latest"
    assert carga.local_suspendido is False
```

`test_aduana_api.py`, tres bloques.

ANTES (`:434-450`):

```python
def test_el_arranque_declara_la_memoria_una_vez(libro, monkeypatch):
    """`_declarar_arranque()` NO corre al importar el server: la llama
    `_calentar_probes` en hilo desde `_startup_warm` (con `uvicorn
    calipso.server:app` el import del modulo corre ADENTRO del loop y la
    aduana no escribiria). Aca se la llama directo, dos veces, con el libro
    limpio: una sola linea."""
    srv._declarar_arranque()
    srv._declarar_arranque()
    c, = cruces_del_libro(libro)
    assert c["declarado"] is True and c["resultado"] is None
    assert c["quien"] == {"origen": "arranque", "chat": None, "proyecto": srv.ROOT.name,
                          "gesto": None, "ruta": None, "rutina": None, "departamento": None,
                          "endpoint": None, "desde": {"credencial": "maquina"}}
    assert c["proposito"] == "modelo de embeddings"
    assert c["destino"] == {"host": "huggingface.co", "url": None}
    assert c["motivo"] == srv.EMBED_MODEL
    assert libro.telemetria.de("aduana_en_loop") == []
```

DESPUES:

```python
def test_el_arranque_ya_no_declara_la_memoria(libro, monkeypatch):
    """`_declarar_arranque()` NO corre al importar el server: la llama
    `_calentar_probes` en hilo desde `_startup_warm` (con `uvicorn
    calipso.server:app` el import del modulo corre ADENTRO del loop y la
    aduana no escribiria). Y ya no declara la memoria (spec memoria por
    Ollama 2026-09-12): el embedder es Ollama en loopback, sin huggingface.co
    (la entrada `memoria_embed.py:_post_embed` del canario lo documenta). Con
    la config de la suite (todo loopback) dos llamadas dejan el libro vacio."""
    srv._declarar_arranque()
    srv._declarar_arranque()
    assert cruces_del_libro(libro) == []
    assert not hasattr(srv, "EMBED_MODEL")
    assert libro.telemetria.de("aduana_en_loop") == []
```

ANTES (`:507-516`):

```python
def test_calentar_probes_termina_con_un_base_url_malformado(libro, monkeypatch):
    monkeypatch.setattr(srv.dispatch, "CONFIG", {
        "local": {"base_url": "http://[::1:11434/x"},
        "api": {"base_url": "http://127.0.0.1:4000/v1"},
        "classifier": {"base_url": "http://localhost:11434/api/generate"}})
    monkeypatch.setattr(srv, "_backend_availability", lambda: {"ok": True})
    assert srv._calentar_probes() == {"ok": True}
    propositos = [c["proposito"] for c in cruces_del_libro(libro)]
    assert propositos == ["modelo de embeddings", "modelo fuera de la maquina",
                          "probes claude/codex: --version, auth status, login status"]
```

DESPUES:

```python
def test_calentar_probes_termina_con_un_base_url_malformado(libro, monkeypatch):
    monkeypatch.setattr(srv.dispatch, "CONFIG", {
        "local": {"base_url": "http://[::1:11434/x"},
        "api": {"base_url": "http://127.0.0.1:4000/v1"},
        "classifier": {"base_url": "http://localhost:11434/api/generate"}})
    monkeypatch.setattr(srv, "_backend_availability", lambda: {"ok": True})
    assert srv._calentar_probes() == {"ok": True}
    propositos = [c["proposito"] for c in cruces_del_libro(libro)]
    assert propositos == ["modelo fuera de la maquina",
                          "probes claude/codex: --version, auth status, login status"]
```

ANTES (`:587-600`):

```python
def test_los_probes_se_declaran_una_vez_al_calentar(libro, monkeypatch):
    """`_calentar_probes` es el unico lugar del arranque que escribe en el
    libro: primero `_declarar_arranque` (la memoria; los modelos fuera de la
    maquina, cero con la config de la suite), despues los probes. Dos
    llamadas, dos lineas: las banderas `una vez` valen por proceso."""
    monkeypatch.setattr(srv, "_backend_availability", lambda: {"ok": True})
    assert srv._calentar_probes() == {"ok": True}
    assert srv._calentar_probes() == {"ok": True}
    memoria, probes = cruces_del_libro(libro)
    assert memoria["proposito"] == "modelo de embeddings" and memoria["declarado"] is True
    c = probes
    assert c["declarado"] is True and c["quien"]["origen"] == "arranque"
    assert c["proposito"] == "probes claude/codex: --version, auth status, login status"
    assert c["destino"] == {"host": None, "url": None}
```

DESPUES:

```python
def test_los_probes_se_declaran_una_vez_al_calentar(libro, monkeypatch):
    """`_calentar_probes` es el unico lugar del arranque que escribe en el
    libro: primero `_declarar_arranque` (los modelos fuera de la maquina,
    cero con la config de la suite; la memoria ya no sale: embebe por Ollama
    en loopback), despues los probes. Dos llamadas, una linea: las banderas
    `una vez` valen por proceso."""
    monkeypatch.setattr(srv, "_backend_availability", lambda: {"ok": True})
    assert srv._calentar_probes() == {"ok": True}
    assert srv._calentar_probes() == {"ok": True}
    c, = cruces_del_libro(libro)
    assert c["declarado"] is True and c["quien"]["origen"] == "arranque"
    assert c["proposito"] == "probes claude/codex: --version, auth status, login status"
    assert c["destino"] == {"host": None, "url": None}
```

`test_memoria_embed.py`, ANTES (el test del Step 4 de la Task 1):

```python
    assert v["payload"] == {"model": "bge-m3:latest", "input": ["hola", "chau"], "truncate": True,
                            "keep_alive": carga.keep_alive("holgada")}
    assert v["timeout"] == me.TIMEOUT_REMEMBER_S
    monkeypatch.setattr(carga, "nivel_reciente", lambda: "cargada")
    ef.embed(["x"])
    assert vistos[-1]["payload"]["keep_alive"] == carga.keep_alive("cargada")
    assert vistos[-1]["payload"]["options"] == {"num_thread": carga.num_thread("cargada")}
```

DESPUES:

```python
    assert v["payload"] == {"model": "bge-m3:latest", "input": ["hola", "chau"], "truncate": True,
                            "keep_alive": "5m"}
    assert v["timeout"] == me.TIMEOUT_REMEMBER_S
    # la tabla PROPIA del embedder (ruling 8.4): justa y cargada 0 (embebe y suelta)
    for nivel in ("justa", "cargada"):
        monkeypatch.setattr(carga, "nivel_reciente", lambda n=nivel: n)
        ef.embed(["x"])
        assert vistos[-1]["payload"]["keep_alive"] == 0 == carga.keep_alive_embed(nivel)
        assert vistos[-1]["payload"]["options"] == {"num_thread": carga.num_thread(nivel)}
```

`test_recall_umbrales.py`, completo:

```python
"""Los umbrales del recall se re-miden, no se heredan (spec memoria por Ollama
2026-09-12, seccion 3): los dos numeros quedan PROVISORIOS y anotados con el
banco en el fuente, y tienen vuelta atras por env
(`CALIPSO_RECALL_MIN_SCORE`, con el viejo `CALIPSO_RECALL_MIN` como alias, y
`CALIPSO_RECALL_UMBRAL`); un env roto cae al default."""
from __future__ import annotations

import pathlib

from calipso import memoria_procedencia as mp

RAIZ = pathlib.Path(__file__).resolve().parent


def test_umbral_por_env_manda_el_nombre_luego_el_alias_luego_el_default(monkeypatch):
    monkeypatch.delenv("X_NUEVO", raising=False)
    monkeypatch.delenv("X_VIEJO", raising=False)
    assert mp.umbral_por_env("X_NUEVO", 0.3, alias="X_VIEJO") == 0.3
    monkeypatch.setenv("X_VIEJO", "0.25")
    assert mp.umbral_por_env("X_NUEVO", 0.3, alias="X_VIEJO") == 0.25
    monkeypatch.setenv("X_NUEVO", "0.55")
    assert mp.umbral_por_env("X_NUEVO", 0.3, alias="X_VIEJO") == 0.55
    monkeypatch.setenv("X_NUEVO", "no-es-numero")
    assert mp.umbral_por_env("X_NUEVO", 0.3, alias="X_VIEJO") == 0.3
    monkeypatch.setenv("X_NUEVO", "")
    assert mp.umbral_por_env("X_NUEVO", 0.3) == 0.3


def test_los_dos_umbrales_estan_marcados_provisorios_y_atados_al_banco():
    server = (RAIZ / "calipso" / "server.py").read_text(encoding="utf-8")
    fuentes = (RAIZ / "calipso" / "abismo" / "fuentes.py").read_text(encoding="utf-8")
    i = server.index("RECALL_MIN_SCORE = memoria_procedencia.umbral_por_env(")
    assert "PROVISORIO" in server[i - 900:i] and "recall_banco" in server[i - 900:i]
    assert '"CALIPSO_RECALL_MIN_SCORE"' in server[i:i + 200] and 'alias="CALIPSO_RECALL_MIN"' in server[i:i + 200]
    j = fuentes.index("RECALL_UMBRAL = memoria_procedencia.umbral_por_env(")
    assert "PROVISORIO" in fuentes[j - 900:j] and "recall_banco" in fuentes[j - 900:j]
    assert '"CALIPSO_RECALL_UMBRAL"' in fuentes[j:j + 120]


def test_los_umbrales_vigentes_son_numeros_en_rango():
    import calipso.server as srv
    from calipso.abismo import fuentes
    assert 0.0 < srv.RECALL_MIN_SCORE < 1.0 and 0.0 < fuentes.RECALL_UMBRAL < 1.0
```

`test_memoria_sin_torch.py`, completo:

```python
"""El server no importa torch (spec memoria por Ollama 2026-09-12, invariante
1): ningun modulo del repo importa torch, transformers ni
sentence_transformers (por AST, como el canario de la aduana), y un `import
calipso.server` en un proceso limpio con home temporal no los carga (por
`sys.modules`: lo que un import perezoso o una dependencia arrastraria).
Medido antes del cambio: `import calipso.server` = 1479 MB de RSS con torch
(1055 submodulos), scipy, transformers, sympy, sentence_transformers..."""
from __future__ import annotations

import ast
import json
import os
import pathlib
import subprocess
import sys

RAIZ = pathlib.Path(__file__).resolve().parent
PROHIBIDOS = ("torch", "transformers", "sentence_transformers")


def _archivos():
    for p in sorted((RAIZ / "calipso").rglob("*.py")):
        if "/web/" not in str(p):
            yield p
    yield RAIZ / "dispatch.py"
    yield RAIZ / "launch_calipso.py"


def test_ningun_modulo_del_repo_importa_torch_ni_transformers():
    malos = []
    for ruta in _archivos():
        tree = ast.parse(ruta.read_text(encoding="utf-8"))
        for n in ast.walk(tree):
            nombres = []
            if isinstance(n, ast.Import):
                nombres = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.module:
                nombres = [n.module]
            for nombre in nombres:
                if nombre.split(".")[0] in PROHIBIDOS:
                    malos.append(f"{ruta.relative_to(RAIZ)}:{n.lineno} {nombre}")
    assert malos == []


def test_importar_el_server_no_carga_torch(tmp_path):
    codigo = ("import json, sys\n"
              "import calipso.server\n"
              f"malos = sorted(m for m in sys.modules if m.split('.')[0] in {PROHIBIDOS!r})\n"
              "print('SYS_MODULES=' + json.dumps(malos))\n")
    env = {**os.environ, "CALIPSO_HOME": str(tmp_path), "CALIPSO_EMBED_FALSA": "1",
           "CALIPSO_ROOT": str(RAIZ)}
    r = subprocess.run([sys.executable, "-c", codigo], cwd=str(RAIZ), env=env,
                       capture_output=True, text=True, timeout=300)
    assert r.returncode == 0, r.stderr[-3000:]
    linea = [l for l in r.stdout.splitlines() if l.startswith("SYS_MODULES=")][-1]
    assert json.loads(linea[len("SYS_MODULES="):]) == []
```

- [ ] **Step 2: verlos fallar**

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama && nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q -p no:cacheprovider test_carga.py test_carga_vigia.py test_aduana_api.py test_recall_umbrales.py test_memoria_sin_torch.py 2>&1 | tail -3
# AttributeError: module 'calipso.carga' has no attribute 'mismo_modelo' / 'keep_alive_embed'; TypeError:
# payload_local() got an unexpected keyword argument 'keep_alive'; los tres de la aduana con el cruce viejo;
# AttributeError: 'memoria_procedencia' has no attribute 'umbral_por_env'; test_memoria_sin_torch: el AST ya
# esta verde (memory.py no importa ST desde la Task 1) y el subproceso tambien: se anota que ya pasan
```

- [ ] **Step 3: `calipso/carga.py` -- `mismo_modelo`, la memoria efectiva, `keep_alive_embed`, `payload_local(keep_alive=)`, `ollama_evict(embedding=)`, los modelos configurados**

ANTES (`calipso/carga.py:81-82`):

```python
OLLAMA = "http://localhost:11434"
NIVELES = ("holgada", "justa", "cargada")
```

DESPUES:

```python
OLLAMA = "http://localhost:11434"
NIVELES = ("holgada", "justa", "cargada")


def _sin_latest(nombre: str) -> str:
    return nombre[:-len(":latest")] if nombre.endswith(":latest") else nombre


def mismo_modelo(a, b) -> bool:
    """`bge-m3` y `bge-m3:latest` son el mismo modelo (spec memoria por Ollama
    2026-09-12, ruling 8.1): /api/ps devuelve el nombre con `:latest` y la
    config puede traerlo sin. Se normaliza a los DOS lados: sin esto la
    memoria efectiva no veia 1,2 GB y el vigia nunca descargaba el embedder."""
    a, b = str(a or ""), str(b or "")
    return bool(a) and bool(b) and _sin_latest(a) == _sin_latest(b)
```

ANTES (`calipso/carga.py:401-402`):

```python
            modelos = [str(m.get("name", "")) for m in lista if m.get("name")]
            modelo_cargado = sum(int(m.get("size_mb") or 0) for m in lista
                                 if m.get("name") and str(m.get("name")) in propios)
```

DESPUES:

```python
            modelos = [str(m.get("name", "")) for m in lista if m.get("name")]
            # `bge-m3:latest` en /api/ps contra `bge-m3` en config: mismo modelo
            modelo_cargado = sum(int(m.get("size_mb") or 0) for m in lista
                                 if m.get("name") and any(mismo_modelo(m.get("name"), p) for p in propios))
```

ANTES (`calipso/carga.py:448-484`):

```python
_KEEP_ALIVE = {"holgada": "5m", "justa": "2m", "cargada": "30s"}


def keep_alive(nivel: str | None):
```

DESPUES:

```python
_KEEP_ALIVE = {"holgada": "5m", "justa": "2m", "cargada": "30s"}
# la tabla PROPIA del embedder de la memoria (bge-m3), ver keep_alive_embed
_KEEP_ALIVE_EMBED = {"holgada": "5m", "justa": 0, "cargada": 0}


def keep_alive_embed(nivel: str | None):
    """El keep_alive del embedder de la memoria (spec memoria por Ollama
    2026-09-12, ruling 8.4), distinto del del 7b: la tabla del 7b esta
    calibrada para pasadas de un turno que comparten runner; un modelo que se
    usa al principio (recall) y al final (remember) del turno con 30 s
    garantiza dos cargas frias, y bajo `justa` no debe convivir con el 7b
    (los dos juntos ~6,4 GB en una Ally de 11,4 GiB). holgada: 5m (el default
    de Ollama, explicito porque gana el keep_alive de la ULTIMA request);
    justa y cargada: 0, embebe y suelta (2 s de carga fria por uso). La
    convivencia se MIDE en el smoke y, si Ollama desaloja al 7b, se para y se
    decide con Pedro."""
    return _KEEP_ALIVE_EMBED.get(nivel or "holgada", "5m")


def keep_alive(nivel: str | None):
```

ANTES (`calipso/carga.py:471-484`):

```python
def payload_local(payload: dict, nivel: str | None = None) -> dict:
    """Un solo helper para hablar con Ollama (spec 3.6): agrega `keep_alive` de
    primer nivel y `options.num_thread` segun el nivel (el reciente si no viene).
    Devuelve un dict NUEVO; no muta `payload` ni sus `options`."""
    nivel = nivel or nivel_reciente()
    nuevo = dict(payload)
    nuevo["keep_alive"] = keep_alive(nivel)
    hilos = num_thread(nivel)
    if hilos is not None:
        nuevo["options"] = {**(payload.get("options") or {}), "num_thread": hilos}
    return nuevo
```

DESPUES:

```python
_keep_alive_del_nivel = keep_alive     # alias: el parametro de payload_local se llama igual


def payload_local(payload: dict, nivel: str | None = None, keep_alive=None) -> dict:
    """Un solo helper para hablar con Ollama (spec 3.6): agrega `keep_alive` de
    primer nivel y `options.num_thread` segun el nivel (el reciente si no viene).
    `keep_alive=` explicito pisa la tabla del 7b: es para el embedder de la
    memoria, que tiene la suya (`keep_alive_embed`, ruling 8.4); los seis
    sitios del chat no lo pasan y quedan como estaban.
    Devuelve un dict NUEVO; no muta `payload` ni sus `options`."""
    nivel = nivel or nivel_reciente()
    nuevo = dict(payload)
    nuevo["keep_alive"] = _keep_alive_del_nivel(nivel) if keep_alive is None else keep_alive
    hilos = num_thread(nivel)
    if hilos is not None:
        nuevo["options"] = {**(payload.get("options") or {}), "num_thread": hilos}
    return nuevo
```

ANTES (`calipso/carga.py:587-601`):

```python
def ollama_evict(model: str, base: str = OLLAMA, timeout: float | None = None) -> bool:
    """Descarga `model` de la RAM de Ollama con una inferencia vacia y
    keep_alive 0. OJO: a un modelo NO cargado esto lo CARGA (ruling 9.12): el
    vigia solo evicta lo que vio en /api/ps en la misma medicion."""
    payload = json.dumps({"model": model, "prompt": "", "stream": False,
                          "keep_alive": 0}).encode()
    try:
        req = urllib.request.Request(f"{base}/api/generate", data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout or UMBRALES["EVICT_TIMEOUT_S"]):
            pass
        return True
    except Exception:
        return False
```

DESPUES:

```python
def ollama_evict(model: str, base: str = OLLAMA, timeout: float | None = None,
                 embedding: bool = False) -> bool:
    """Descarga `model` de la RAM de Ollama con una inferencia vacia y
    keep_alive 0. OJO: a un modelo NO cargado esto lo CARGA (ruling 9.12): el
    vigia solo evicta lo que vio en /api/ps en la misma medicion. Con
    `embedding=True` (spec memoria por Ollama 2026-09-12) va por /api/embed:
    a un modelo de solo embedding (bge-m3, capabilities ['embedding'])
    /api/generate puede rechazarlo. El `input` es un caracter y no vacio: el
    vacio podria salir por la rama corta de Ollama sin tocar el runner."""
    if embedding:
        ruta = "/api/embed"
        payload = json.dumps({"model": model, "input": "x", "truncate": True,
                              "keep_alive": 0}).encode()
    else:
        ruta = "/api/generate"
        payload = json.dumps({"model": model, "prompt": "", "stream": False,
                              "keep_alive": 0}).encode()
    try:
        req = urllib.request.Request(f"{base}{ruta}", data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout or UMBRALES["EVICT_TIMEOUT_S"]):
            pass
        return True
    except Exception:
        return False
```

ANTES (`calipso/carga.py:657-662`):

```python
def _modelos_configurados() -> set[str]:
    """Los modelos propios para la memoria efectiva desde la terminal: el del
    chat y el del clasificador (el server suma el de vision si hay)."""
    from calipso import config as calipso_config
    cfg = calipso_config.load_config()
    return {cfg["local"]["model"], (cfg.get("classifier") or {}).get("model") or cfg["local"]["model"]}
```

DESPUES:

```python
def _modelos_configurados() -> set[str]:
    """Los modelos propios para la memoria efectiva desde la terminal: el del
    chat, el del clasificador y el embedder de la memoria (spec memoria por
    Ollama 2026-09-12; el server suma el de vision si hay)."""
    from calipso import config as calipso_config
    cfg = calipso_config.load_config()
    return {cfg["local"]["model"], (cfg.get("classifier") or {}).get("model") or cfg["local"]["model"],
            calipso_config.EMBED_MODEL}
```

- [ ] **Step 4: `calipso/memoria_embed.py` -- la tabla propia del embedder**

ANTES (en `OllamaEmbed.embed`):

```python
                payload = carga.payload_local(
                    {"model": self.model, "input": lote, "truncate": True}, nivel)
```

DESPUES:

```python
                payload = carga.payload_local(
                    {"model": self.model, "input": lote, "truncate": True}, nivel,
                    keep_alive=carga.keep_alive_embed(nivel))
```

- [ ] **Step 5: los umbrales por env -- `memoria_procedencia.umbral_por_env`, `RECALL_MIN_SCORE`, `RECALL_UMBRAL`**

`calipso/memoria_procedencia.py`, al final del archivo (`os` ya esta importado):

```python
# --- los umbrales del recall (spec memoria por Ollama 2026-09-12, seccion 3) ----

def umbral_por_env(nombre: str, default: float, alias: str | None = None) -> float:
    """El umbral de recall por env: `nombre` manda, `alias` (el nombre viejo)
    sigue valiendo, y un valor roto o vacio cae al default (un env mal
    tipeado no puede impedir que arranque el server: server.py y
    abismo/fuentes.py lo leen al importarse). Es la vuelta atras de los
    umbrales PROVISORIOS calibrados con experimentos/recall_banco.py."""
    for clave in (nombre, alias):
        if clave and os.environ.get(clave, "") != "":
            try:
                return float(os.environ[clave])
            except ValueError:
                return default
    return default
```

`calipso/server.py`, ANTES (`:3005`):

```python
RECALL_MIN_SCORE = float(os.environ.get("CALIPSO_RECALL_MIN", "0.30"))
```

DESPUES:

```python
# El umbral del recall del turno (score = 1 - distancia coseno) sobre bge-m3
# (spec memoria por Ollama 2026-09-12, seccion 3). PROVISORIO: bge-m3 tiene
# otra distribucion que MiniLM (similitudes mas altas y mas apretadas) y
# embebe otro texto; el numero se elige por el MARGEN del banco
# `experimentos/recall_banco.py` (min(aciertos) - max(negativas)) con los
# aciertos de MiniLM como piso, sobre N chico (16 episodios del fixture + 5
# reales): se re-mide cuando el corpus crezca. Los numeros de la corrida
# estan en experimentos/recall_banco_resultados.md. Vuelta atras por env:
# CALIPSO_RECALL_MIN_SCORE (el viejo CALIPSO_RECALL_MIN sigue valiendo).
RECALL_MIN_SCORE = memoria_procedencia.umbral_por_env(
    "CALIPSO_RECALL_MIN_SCORE", 0.30, alias="CALIPSO_RECALL_MIN")
```

`calipso/abismo/fuentes.py`, ANTES (ya con el DESPUES de la Task 2):

```python
RECALL_N = 12
RECALL_TOP = 8
RECALL_UMBRAL = 0.20
```

DESPUES:

```python
RECALL_N = 12
RECALL_TOP = 8
# El umbral de la consulta dirigida del abismo sobre bge-m3 (spec memoria por
# Ollama 2026-09-12, seccion 3). PROVISORIO, como RECALL_MIN_SCORE del turno:
# calibrado con experimentos/recall_banco.py por el margen, N chico, se
# re-mide cuando el corpus crezca; mas bajo que el del turno a proposito (la
# consulta la escribe el modelo, con menos anclaje que la pregunta de Pedro;
# el techo del bloque lo pone consulta.etiquetar). Vuelta atras por env.
RECALL_UMBRAL = memoria_procedencia.umbral_por_env("CALIPSO_RECALL_UMBRAL", 0.20)
```

(`memoria_procedencia` ya esta importado en `fuentes.py:10`.)

- [ ] **Step 6: `calipso/server.py` -- sin `EMBED_MODEL`, la aduana sin embeddings, el embedder en los modelos propios y en el vigia**

ANTES (`calipso/server.py:104`):

```python
from calipso.memory import EMBED_MODEL, Memory, leer_carta  # noqa: E402
```

DESPUES:

```python
from calipso.memory import Memory, leer_carta  # noqa: E402
```

ANTES (`calipso/server.py:2171-2189`):

```python
def _declarar_arranque() -> None:
    """Lo que sale al arrancar el proceso, declarado UNA vez (spec seccion
    7). La memoria sale a huggingface.co al construirse (`SentenceTransformer`
    sin `local_files_only`: metadatos + un HEAD por archivo aunque el cache
    este completo): se declara ACA y no en `Memory.__init__`, porque
    `_switch_project` reconstruye la memoria en el loop y chromadb cachea
    el modelo por clase (no vuelve a salir). NO se llama a nivel de modulo:
    con `uvicorn calipso.server:app` (asi arranca el shell de escritorio,
    ver `_instalar_filtro_de_token`, y asi levanta el smoke) el import del
    modulo corre ADENTRO del loop (uvicorn 0.49: `Server._serve` ->
    `config.load()`), la aduana detectaria el loop y NO escribiria
    (`aduana_en_loop`), y la memoria quedaria sin declarar. Se llama desde
    `_calentar_probes`, en `to_thread` desde `_startup_warm`, donde el
    candado se puede tomar. Con `python calipso/server.py` daria igual."""
    quien = aduana.Quien(origen="arranque", proyecto=_proyecto(),
                         desde={"credencial": "maquina"})
    aduana.declarar_una_vez("memoria", quien, "modelo de embeddings",
                            destino="huggingface.co", motivo=EMBED_MODEL)
    _declarar_modelos_fuera(quien)
```

DESPUES:

```python
def _declarar_arranque() -> None:
    """Lo que sale al arrancar el proceso, declarado UNA vez (spec seccion
    7): hoy, solo los modelos fuera de la maquina. La memoria YA NO sale
    (spec memoria por Ollama 2026-09-12): embebe por `POST /api/embed` en
    loopback (`memoria_embed._post_embed`, entrada del canario) y
    `Memory.__init__` no abre red ni disco; whisper sigue declarando lo suyo
    al primer uso. NO se llama a nivel de modulo: con `uvicorn
    calipso.server:app` (asi arranca el shell de escritorio, ver
    `_instalar_filtro_de_token`, y asi levanta el smoke) el import del
    modulo corre ADENTRO del loop (uvicorn 0.49: `Server._serve` ->
    `config.load()`), la aduana detectaria el loop y NO escribiria
    (`aduana_en_loop`). Se llama desde `_calentar_probes`, en `to_thread`
    desde `_startup_warm`, donde el candado se puede tomar. Con `python
    calipso/server.py` daria igual."""
    quien = aduana.Quien(origen="arranque", proyecto=_proyecto(),
                         desde={"credencial": "maquina"})
    _declarar_modelos_fuera(quien)
```

ANTES (`calipso/server.py:5720-5733`):

```python
def _modelos_de_calipso() -> set[str]:
    """Los nombres que el vigia puede descargar (spec carga 3.3, ruling 9.12):
    el del chat, el del clasificador y el de vision si hay. Jamas otro: un
    `prompt: ""` con keep_alive 0 a un modelo NO cargado lo CARGA."""
    nombres = {dispatch.CONFIG["local"]["model"], dispatch.CONFIG["classifier"]["model"]}
    vm = attachments.ollama_vision_model()
    if vm:
        nombres.add(vm)
    return nombres


# el hook de la descarga: los tests lo reemplazan con un espia
_ollama_evict = carga.ollama_evict
```

DESPUES:

```python
def _modelos_de_calipso() -> set[str]:
    """Los nombres que el vigia puede descargar (spec carga 3.3, ruling 9.12):
    el del chat, el del clasificador, el embedder de la memoria (spec memoria
    por Ollama 2026-09-12, ruling 8.1: `bge-m3:latest`, que es lo que /api/ps
    devuelve; la comparacion normaliza `:latest` a los dos lados) y el de
    vision si hay. Jamas otro: un `prompt: ""` con keep_alive 0 a un modelo
    NO cargado lo CARGA."""
    nombres = {dispatch.CONFIG["local"]["model"], dispatch.CONFIG["classifier"]["model"],
               calipso_config.EMBED_MODEL}
    vm = attachments.ollama_vision_model()
    if vm:
        nombres.add(vm)
    return nombres


# el hook de la descarga: los tests lo reemplazan con un espia
_ollama_evict = carga.ollama_evict


def _ollama_evict_embedding(nombre: str) -> bool:
    """El hook de la descarga del embedder: por /api/embed (a un modelo de
    solo embedding /api/generate puede rechazarlo). Los tests lo reemplazan."""
    return carga.ollama_evict(nombre, embedding=True)
```

ANTES (`calipso/server.py:5756-5762`, en `_vigia_del_modelo`):

```python
    for nombre in medida.modelos_cargados:
        if nombre not in de_calipso:
            continue
        if carga.en_uso > 0:
            telemetry.log_event("carga", accion="descarga_diferida", modelo=nombre,
                                en_uso=carga.en_uso, **fila)
            continue
```

DESPUES:

```python
    for nombre in medida.modelos_cargados:
        if not any(carga.mismo_modelo(nombre, propio) for propio in de_calipso):
            continue
        if carga.en_uso > 0:
            telemetry.log_event("carga", accion="descarga_diferida", modelo=nombre,
                                en_uso=carga.en_uso, **fila)
            continue
        if carga.mismo_modelo(nombre, calipso_config.EMBED_MODEL):
            # el embedder de la memoria no es el modelo del chat: se descarga
            # por /api/embed y SIN histeresis (suspender el local por descargar
            # bge-m3 seria castigar al chat por un modelo que no es el suyo);
            # si el 7b tambien esta listado, cae en este mismo bucle con la
            # suspension de siempre
            ok = _ollama_evict_embedding(nombre)
            if ok:
                descargados.append(nombre)
            telemetry.log_event("carga", accion=("descarga" if ok else "descarga_fallida"),
                                modelo=nombre, ok=ok, **fila)
            continue
```

ANTES (`calipso/server.py:8795`, en `_startup_warm`):

```python
        await asyncio.to_thread(_calentar_probes)  # declara la memoria y los probes, pre-calienta el cache
```

DESPUES:

```python
        await asyncio.to_thread(_calentar_probes)  # declara los modelos fuera y los probes, pre-calienta el cache
```

- [ ] **Step 7: verde de la carga, la aduana, el vigia y el guardia**

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama
nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q -p no:cacheprovider test_carga.py test_carga_vigia.py test_carga_sitios.py test_carga_chat.py test_aduana_api.py test_aduana_canario.py test_memoria_embed.py test_recall_umbrales.py test_memoria_sin_torch.py test_memoria_lectores.py test_abismo_turno.py 2>&1 | tail -1
# 6 nuevos en test_carga + 1 en test_carga_vigia + 3 en test_recall_umbrales + 2 en test_memoria_sin_torch; 0 failed
```

- [ ] **Step 8: `experimentos/recall_banco.py`, completo**

```python
#!/usr/bin/env python3
"""El banco de recall (spec memoria por Ollama 2026-09-12, seccion 3; ruling
8.6): mide SEPARACION, no `hit@4` literal. Lo que habia no media nada: los 16
episodios del fixture son 8 preguntas por 2 pasadas (duplicados) y las
consultas eran la pregunta literal, asi que hit@4 daba ~100% con cualquier
embedder.

El banco: por cada uno de los 8 topicos del fixture, la pregunta literal mas
dos parafrasis escritas a mano (una sobre la pregunta, otra sobre el
CONTENIDO de la respuesta) y 8 consultas negativas (temas ausentes); los
duplicados cuentan como UN acierto (hit@1 por TOPICO); las filas reales del
home entran con consultas escritas a partir de su contenido (`--home` y
`--reales`; es local: no sale nada, y el MD solo muestra ids y numeros de las
reales). Condiciones: `minilm` (la ST en proceso, el par entero como en
produccion, truncado a 128 tokens; importa sentence_transformers solo si
esta: corre ANTES del uninstall) y `bge-m3` por Ollama en tres variantes del
texto embebido: `pregunta` (palabras=0), `pregunta+150` (la de produccion) y
`par` (palabras=10_000: la pregunta limpia + la respuesta ENTERA, sin las
etiquetas; es la forma que `PALABRAS_RESPUESTA = 10_000` aterriza, no el
documento crudo: lo que se mide es lo que se aterrizaria). Metricas por
condicion: hit@1 por topico, hit@4,
la distribucion de scores (aciertos contra negativas; score = coseno = 1 -
distancia de chroma) y el MARGEN = min(score de los aciertos top-1) -
max(score top-1 de las negativas); un umbral sugerido = el punto medio del
margen. Regla de parada: si bge-m3 no iguala el hit@1 por topico de MiniLM o
su margen es negativo, se para y se le dice a Pedro (no se aterriza a ciegas).

    python experimentos/recall_banco.py                       # todas las condiciones (Ollama + la ST)
    python experimentos/recall_banco.py --condiciones bge-m3:pregunta+150
    python experimentos/recall_banco.py --home ~/.calipso --listar-reales    # los docs reales, para escribir las consultas
    python experimentos/recall_banco.py --home ~/.calipso --reales /ruta/reales.json
    python experimentos/recall_banco.py --informe             # el MD desde el JSONL, sin Ollama

`reales.json`: `[{"id": "<id de chroma>", "consulta": "...", "tipo": "contenido"}, ...]`
(NO se commitea: vive en el scratchpad de la sesion). Salidas:
experimentos/recall_banco_resultados.jsonl (una fila por consulta y
condicion) y experimentos/recall_banco_resultados.md. Antes de tocar Ollama
corre `python -m calipso.carga --esperar` (la regla de recursos; `--sin-esperar`
la salta solo si ya se corrio a mano).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

RAIZ = pathlib.Path(__file__).resolve().parent.parent
os.environ.setdefault("CALIPSO_HOME", tempfile.mkdtemp(prefix="recall-banco-home-"))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.pop("CALIPSO_EMBED_FALSA", None)
sys.path.insert(0, str(RAIZ))

import chromadb  # noqa: E402
import numpy as np  # noqa: E402

from calipso import memoria_embed as me  # noqa: E402
from calipso import memoria_procedencia as mp  # noqa: E402

FIXTURE = RAIZ / "experimentos" / "fixtures" / "memoria_smoke_home"
SALIDA_JSONL = RAIZ / "experimentos" / "recall_banco_resultados.jsonl"
SALIDA_MD = RAIZ / "experimentos" / "recall_banco_resultados.md"
MINILM = "paraphrase-multilingual-MiniLM-L12-v2"
TOP = 4
CONDICIONES = ("minilm", "bge-m3:pregunta", "bge-m3:pregunta+150", "bge-m3:par")

# los 8 topicos del fixture: topico -> fragmento que identifica la pregunta del documento
TOPICOS = {
    "libro_empezado": "que libro te conte que empece",
    "libro_rosa": "quien me presto el libro rosa",
    "presupuesto_taller": "presupuesto del taller",
    "mariana_agosto": "retoma lo que dejamos sobre mariana",
    "repo_calipso": "como viene el repo de calipso",
    "mapa_ciudad": "detalle del proyecto mapa-ciudad",
    "buen_dia": "buen dia! como va todo",
    "websocket": "que es un websocket",
}

# (id, topico, tipo, texto). Literal = la pregunta del documento sin el gesto
# (asi llega `chat_msg` al recall); parafrasis escritas a mano.
CONSULTAS = [
    ("libro_empezado/literal", "libro_empezado", "literal", "hola, que libro te conte que empece?"),
    ("libro_empezado/pregunta", "libro_empezado", "parafrasis_pregunta", "que libro te dije que habia arrancado a leer?"),
    ("libro_empezado/contenido", "libro_empezado", "parafrasis_contenido", "el libro de ciencia ficcion que empezamos a leer juntos"),
    ("libro_rosa/literal", "libro_rosa", "literal", "che, quien me presto el libro rosa? no me acuerdo"),
    ("libro_rosa/pregunta", "libro_rosa", "parafrasis_pregunta", "no recuerdo quien me dio prestado el libro rosa"),
    ("libro_rosa/contenido", "libro_rosa", "parafrasis_contenido", "revisar mis libretas personales para ver quien me presto un libro"),
    ("presupuesto_taller/literal", "presupuesto_taller", "literal", "en que quedamos la otra vez con el presupuesto del taller?"),
    ("presupuesto_taller/pregunta", "presupuesto_taller", "parafrasis_pregunta", "cuanta plata habiamos acordado para el taller?"),
    ("presupuesto_taller/contenido", "presupuesto_taller", "parafrasis_contenido", "no hay registros de una conversacion sobre el presupuesto"),
    ("mariana_agosto/literal", "mariana_agosto", "literal", "retoma lo que dejamos sobre mariana, la charla de agosto"),
    ("mariana_agosto/pregunta", "mariana_agosto", "parafrasis_pregunta", "seguimos con lo de mariana que hablamos en agosto"),
    ("mariana_agosto/contenido", "mariana_agosto", "parafrasis_contenido", "la charla con Mariana del 20 de agosto de 2026"),
    ("repo_calipso/literal", "repo_calipso", "literal", "como viene el repo de calipso, en que rama esta y que se toco ultimo?"),
    ("repo_calipso/pregunta", "repo_calipso", "parafrasis_pregunta", "estado del repositorio calipso: rama actual y ultimos cambios"),
    ("repo_calipso/contenido", "repo_calipso", "parafrasis_contenido", "Heraclito el analista reviso la rama del repo y no pudo completar la sintesis"),
    ("mapa_ciudad/literal", "mapa_ciudad", "literal", "dame el detalle del proyecto mapa-ciudad"),
    ("mapa_ciudad/pregunta", "mapa_ciudad", "parafrasis_pregunta", "contame de que va mapa-ciudad"),
    ("mapa_ciudad/contenido", "mapa_ciudad", "parafrasis_contenido", "un mapa interactivo de la ciudad con el backend casi listo"),
    ("buen_dia/literal", "buen_dia", "literal", "buen dia! como va todo?"),
    ("buen_dia/pregunta", "buen_dia", "parafrasis_pregunta", "hola, como venimos con todo?"),
    ("buen_dia/contenido", "buen_dia", "parafrasis_contenido", "estamos avanzando bien en varios frentes"),
    ("websocket/literal", "websocket", "literal", "explicame en dos lineas que es un websocket"),
    ("websocket/pregunta", "websocket", "parafrasis_pregunta", "que es un websocket, en breve"),
    ("websocket/contenido", "websocket", "parafrasis_contenido", "conexiones bidireccionales entre servidor y cliente con una sola conexion abierta"),
]
NEGATIVAS = [
    ("neg/tokio", "que hora es en tokio ahora"),
    ("neg/pan", "receta de pan casero con masa madre"),
    ("neg/rueda", "como se cambia una rueda pinchada"),
    ("neg/waterloo", "cuando fue la batalla de waterloo"),
    ("neg/rodilla", "me duele la rodilla al correr"),
    ("neg/alquiler", "que dice el contrato de alquiler sobre las mascotas"),
    ("neg/mongolia", "cual es la capital de mongolia"),
    ("neg/wifi", "como configuro el wifi del router nuevo"),
]


# --- el corpus ------------------------------------------------------------------

def _leer_coleccion(chroma_dir: pathlib.Path, origen: str) -> list[dict]:
    """Los documentos de la vieja `episodic` (o de la viva si la vieja no esta)
    sobre una COPIA temporal del directorio: chroma escribe su WAL al abrir."""
    copia = pathlib.Path(tempfile.mkdtemp(prefix="recall-banco-chroma-"))
    shutil.copytree(chroma_dir, copia, dirs_exist_ok=True)
    cliente = chromadb.PersistentClient(path=str(copia))
    col = None
    for nombre in (me.COLECCION_VIEJA, me.COLECCION_VIVA):
        try:
            col = cliente.get_collection(nombre, embedding_function=None)
            break
        except Exception:
            continue
    if col is None:
        return []
    datos = col.get(include=["documents", "metadatas"])
    return [{"id": i, "texto": d, "origen": origen, "meta": m or {}}
            for i, d, m in zip(datos["ids"], datos["documents"], datos["metadatas"])
            if isinstance(d, str) and d.strip()]


def topico_de(doc: str) -> str | None:
    par = mp.partir(doc)
    pregunta = mp.limpiar_gestos(par[0]) if par else (doc or "")
    pregunta = pregunta.lower()
    for topico, fragmento in TOPICOS.items():
        if fragmento in pregunta:
            return topico
    return None


def corpus(home: pathlib.Path | None) -> list[dict]:
    docs = _leer_coleccion(FIXTURE / "global" / "chroma", "fixture")
    for d in docs:
        d["topico"] = topico_de(d["texto"])
    if home:
        reales = _leer_coleccion(home / "projects" / "var-home-pedro-calipso" / "chroma", "real")
        for d in reales:
            d["topico"] = f"real/{d['id']}"
        docs += reales
    return docs


def consultas_de(reales: list[dict] | None) -> list[dict]:
    salida = [{"id": i, "topico": t, "tipo": tipo, "texto": x} for i, t, tipo, x in CONSULTAS]
    salida += [{"id": i, "topico": None, "tipo": "negativa", "texto": x} for i, x in NEGATIVAS]
    for r in reales or []:
        salida.append({"id": f"real/{r['id']}/{r.get('tipo', 'contenido')}", "topico": f"real/{r['id']}",
                       "tipo": f"real_{r.get('tipo', 'contenido')}", "texto": r["consulta"]})
    return salida


# --- las condiciones ------------------------------------------------------------

def texto_doc(condicion: str, doc: str) -> str:
    """El texto que cada condicion embebe. Solo `minilm` embebe el documento
    CRUDO (con las etiquetas y los gestos: reproduce la produccion vieja);
    las tres de bge-m3 pasan por `texto_para_embedding` con el numero que
    el Step 10 aterrizaria (0 / 150 / 10_000): se mide la forma aterrizable."""
    if condicion == "minilm":
        return doc
    if condicion == "bge-m3:pregunta":
        return me.texto_para_embedding(doc, palabras=0)
    if condicion == "bge-m3:pregunta+150":
        return me.texto_para_embedding(doc, palabras=150)
    if condicion == "bge-m3:par":
        return me.texto_para_embedding(doc, palabras=10_000)
    raise ValueError(condicion)


def embedder_de(condicion: str):
    """(embed, nota) o (None, por que no) -- la ST solo si esta instalada."""
    if condicion == "minilm":
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            return None, f"sentence_transformers no importable: {e}"
        modelo = SentenceTransformer(MINILM, device="cpu")

        def embed(textos):
            return modelo.encode(list(textos), normalize_embeddings=True).tolist()
        return embed, f"{MINILM} en proceso, max_seq_length {modelo.max_seq_length}"
    ef = me.OllamaEmbed()

    def embed(textos):
        return ef.embed(list(textos), timeout=900)
    return embed, f"{ef.model} por {ef.url}/api/embed, {ef.dims} dims"


def _normalizar(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def correr_condicion(condicion: str, embed, docs: list[dict], consultas: list[dict]) -> list[dict]:
    t0 = time.monotonic()
    D = _normalizar(np.asarray(embed([texto_doc(condicion, d["texto"]) for d in docs]), dtype=np.float64))
    t_docs = time.monotonic() - t0
    t0 = time.monotonic()
    Q = _normalizar(np.asarray(embed([c["texto"] for c in consultas]), dtype=np.float64))
    t_cons = time.monotonic() - t0
    S = Q @ D.T
    filas = []
    for qi, c in enumerate(consultas):
        orden = [int(j) for j in np.argsort(-S[qi])[:TOP]]
        top = [{"id": docs[j]["id"], "topico": docs[j]["topico"], "origen": docs[j]["origen"],
                "score": round(float(S[qi, j]), 4)} for j in orden]
        propios = [j for j, d in enumerate(docs) if c["topico"] is not None and d["topico"] == c["topico"]]
        mejor = round(float(max(S[qi, j] for j in propios)), 4) if propios else None
        filas.append({
            "condicion": condicion, "consulta": c["id"], "topico": c["topico"], "tipo": c["tipo"],
            "top": top, "mejor_correcto": mejor,
            "acierto1": bool(propios) and top[0]["topico"] == c["topico"],
            "acierto4": bool(propios) and any(t["topico"] == c["topico"] for t in top),
            "s_docs": round(t_docs, 2), "s_consultas": round(t_cons, 2), "n_docs": len(docs)})
    return filas


# --- las metricas y el informe ---------------------------------------------------

def resumen(filas: list[dict]) -> dict:
    """Por condicion: hit@1 y hit@4 por topico y totales, la distribucion de
    scores, el margen y el umbral sugerido."""
    por_cond: dict[str, dict] = {}
    for f in filas:
        r = por_cond.setdefault(f["condicion"], {"topicos": {}, "aciertos": [], "negativas": [],
                                                  "reales": [0, 0], "n_docs": f["n_docs"],
                                                  "s_docs": f["s_docs"], "s_consultas": f["s_consultas"]})
        if f["tipo"] == "negativa":
            r["negativas"].append(f["top"][0]["score"])
            continue
        if f["tipo"].startswith("real_"):
            r["reales"][1] += 1
            r["reales"][0] += int(f["acierto1"])
            if f["acierto1"]:
                r["aciertos"].append(f["top"][0]["score"])
            continue
        t = r["topicos"].setdefault(f["topico"], {"hit1": 0, "hit4": 0, "n": 0})
        t["n"] += 1
        t["hit1"] += int(f["acierto1"])
        t["hit4"] += int(f["acierto4"])
        if f["acierto1"]:
            r["aciertos"].append(f["top"][0]["score"])
    for nombre, r in por_cond.items():
        r["hit1"] = sum(t["hit1"] for t in r["topicos"].values())
        r["hit4"] = sum(t["hit4"] for t in r["topicos"].values())
        r["n"] = sum(t["n"] for t in r["topicos"].values())
        ac, ne = r["aciertos"], r["negativas"]
        r["aciertos_min_med_max"] = (round(min(ac), 4), round(statistics.median(ac), 4), round(max(ac), 4)) if ac else None
        r["negativas_min_med_max"] = (round(min(ne), 4), round(statistics.median(ne), 4), round(max(ne), 4)) if ne else None
        r["margen"] = round(min(ac) - max(ne), 4) if ac and ne else None
        r["umbral_sugerido"] = round((min(ac) + max(ne)) / 2, 3) if ac and ne and min(ac) > max(ne) else None
    return por_cond


def regla_de_parada(res: dict) -> list[str]:
    """Para cada variante de bge-m3: iguala el hit@1 por topico de MiniLM y su
    margen es positivo. Si MiniLM no corrio, solo el margen."""
    avisos = []
    base = res.get("minilm")
    for nombre, r in res.items():
        if not nombre.startswith("bge-m3"):
            continue
        if r["margen"] is None or r["margen"] < 0:
            avisos.append(f"{nombre}: margen {r['margen']} (negativo o sin datos): PARAR y decirle a Pedro")
        if base:
            peores = [t for t, v in r["topicos"].items() if v["hit1"] < base["topicos"].get(t, {}).get("hit1", 0)]
            if peores:
                avisos.append(f"{nombre}: hit@1 por debajo de MiniLM en {peores}: PARAR y decirle a Pedro")
    return avisos


def informe(filas: list[dict]) -> str:
    res = resumen(filas)
    L = ["# Banco de recall: MiniLM contra bge-m3 en tres variantes (spec memoria por Ollama, seccion 3)", ""]
    L.append(f"Corrida: {time.strftime('%Y-%m-%d %H:%M')}. Consultas por condicion: {len({f['consulta'] for f in filas})} "
             f"({len(CONSULTAS)} positivas = 8 topicos x 3, {len(NEGATIVAS)} negativas"
             + (", mas las reales" if any(f["tipo"].startswith("real_") for f in filas) else "") + "). "
             "Score = coseno (= 1 - distancia de chroma). Los duplicados del fixture cuentan como UN acierto (por topico).")
    L += ["", "## Resumen por condicion", "",
          "| condicion | docs | hit@1 | hit@4 | reales hit@1 | aciertos min/med/max | negativas min/med/max | margen | umbral sugerido | s docs | s consultas |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for nombre in CONDICIONES:
        r = res.get(nombre)
        if not r:
            L.append(f"| {nombre} | - | no corrio | | | | | | | | |")
            continue
        L.append(f"| {nombre} | {r['n_docs']} | {r['hit1']}/{r['n']} | {r['hit4']}/{r['n']} | "
                 f"{r['reales'][0]}/{r['reales'][1]} | {r['aciertos_min_med_max']} | {r['negativas_min_med_max']} | "
                 f"{r['margen']} | {r['umbral_sugerido']} | {r['s_docs']} | {r['s_consultas']} |")
    L += ["", "## hit@1 por topico (de 3 consultas: literal, parafrasis de la pregunta, parafrasis del contenido)", "",
          "| topico | " + " | ".join(c for c in CONDICIONES if c in res) + " |",
          "|---|" + "---|" * len([c for c in CONDICIONES if c in res])]
    for topico in TOPICOS:
        L.append(f"| {topico} | " + " | ".join(
            f"{res[c]['topicos'].get(topico, {}).get('hit1', 0)}/3 (hit@4 {res[c]['topicos'].get(topico, {}).get('hit4', 0)}/3)"
            for c in CONDICIONES if c in res) + " |")
    L += ["", "## Regla de parada", ""]
    avisos = regla_de_parada(res)
    L += [f"- {a}" for a in avisos] or ["- ninguna variante de bge-m3 queda por debajo de MiniLM y todos los margenes son positivos"]
    L += ["", "## Umbrales elegidos (a completar a mano al anotar: ver el plan, Task 3, Step 10)", "",
          "- `RECALL_MIN_SCORE` (server.py): ", "- `RECALL_UMBRAL` (abismo/fuentes.py): ",
          "- variante aterrizada (`PALABRAS_RESPUESTA`): ", ""]
    L += ["## Detalle: top-1 por consulta", "", "| condicion | consulta | tipo | top-1 (topico, score) | mejor del topico | acierto@1 |", "|---|---|---|---|---|---|"]
    for f in filas:
        t = f["top"][0]
        quien = t["topico"] if t["origen"] == "fixture" else f"real:{t['id']}"
        L.append(f"| {f['condicion']} | {f['consulta']} | {f['tipo']} | {quien} ({t['score']}) | {f['mejor_correcto']} | {'si' if f['acierto1'] else 'no'} |")
    return "\n".join(L) + "\n"


# --- main --------------------------------------------------------------------------

def esperar_recursos() -> None:
    r = subprocess.run([sys.executable, "-m", "calipso.carga", "--esperar", "--tope", "600"],
                       cwd=str(RAIZ), env=os.environ)
    if r.returncode != 0:
        sys.exit(f"[recursos] --esperar salio con {r.returncode}: BLOQUEADO, no corro el banco (codigo 3)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--condiciones", default=",".join(CONDICIONES))
    ap.add_argument("--home", type=pathlib.Path, default=None, help="el CALIPSO_HOME real, solo lectura (copia a tmp)")
    ap.add_argument("--reales", type=pathlib.Path, default=None, help="JSON con las consultas de las filas reales")
    ap.add_argument("--listar-reales", action="store_true", help="imprimir los docs reales (id y texto) y salir")
    ap.add_argument("--informe", action="store_true", help="rehacer el MD desde el JSONL, sin Ollama")
    ap.add_argument("--sin-esperar", action="store_true")
    args = ap.parse_args(argv)
    if args.informe:
        filas = [json.loads(l) for l in SALIDA_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
        SALIDA_MD.write_text(informe(filas), encoding="utf-8")
        print(SALIDA_MD)
        return 0
    docs = corpus(args.home)
    if args.listar_reales:
        for d in docs:
            if d["origen"] == "real":
                print(f"--- {d['id']} ({len(d['texto'])} chars, {d['meta'].get('ts')})\n{d['texto'][:600]}\n")
        return 0
    sin_topico = [d["id"] for d in docs if d["topico"] is None]
    if sin_topico:
        print(f"[banco] OJO: {len(sin_topico)} documentos del fixture sin topico (distractores): {sin_topico}")
    reales = json.loads(args.reales.read_text(encoding="utf-8")) if args.reales else None
    consultas = consultas_de(reales)
    condiciones = [c.strip() for c in args.condiciones.split(",") if c.strip()]
    if any(c.startswith("bge-m3") for c in condiciones) and not args.sin_esperar:
        esperar_recursos()
    filas: list[dict] = []
    for condicion in condiciones:
        embed, nota = embedder_de(condicion)
        if embed is None:
            print(f"[banco] {condicion}: no corre ({nota})")
            continue
        print(f"[banco] {condicion}: {nota}; {len(docs)} docs, {len(consultas)} consultas", flush=True)
        filas += correr_condicion(condicion, embed, docs, consultas)
    with open(SALIDA_JSONL, "w", encoding="utf-8") as f:
        for fila in filas:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    SALIDA_MD.write_text(informe(filas), encoding="utf-8")
    res = resumen(filas)
    for nombre, r in res.items():
        print(f"[banco] {nombre}: hit@1 {r['hit1']}/{r['n']} hit@4 {r['hit4']}/{r['n']} reales {r['reales'][0]}/{r['reales'][1]} "
              f"margen {r['margen']} umbral sugerido {r['umbral_sugerido']}")
    for aviso in regla_de_parada(res):
        print(f"[banco] PARADA: {aviso}")
    print(f"[banco] {SALIDA_JSONL}\n[banco] {SALIDA_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 9: correr el banco (Ollama real y la ST instalada, ANTES del uninstall)**

Primero una corrida seca del informe sobre un JSONL vacio para ver que el MD se arma (sin Ollama):

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama
: > experimentos/recall_banco_resultados.jsonl
CALIPSO_HOME=$(mktemp -d) nice -n 19 /var/home/pedro/calipso/.venv/bin/python experimentos/recall_banco.py --informe && head -12 experimentos/recall_banco_resultados.md
```

Las consultas de las filas reales: listar los docs reales del home (SOLO LECTURA: el banco copia el chroma del proyecto a un tmp), escribir el JSON a mano en el scratchpad (una consulta por contenido por cada uno de los 5, `tipo: "contenido"`), no commitearlo:

```bash
REALES=$(mktemp -d)/recall_reales.json && echo "$REALES"
CALIPSO_HOME=$(mktemp -d) nice -n 19 /var/home/pedro/calipso/.venv/bin/python experimentos/recall_banco.py --home ~/.calipso --listar-reales
# escribir $REALES a mano: [{"id": "<id>", "consulta": "<una consulta por el contenido>", "tipo": "contenido"}, ...] con los 5 ids
```

La corrida (mide la RAM primero: la ST carga torch en el proceso del banco, ~1,5 GB, y bge-m3 en Ollama, 1,2 GB; con el 7b descargado entra en `justa`):

```bash
CALIPSO_HOME=$(mktemp -d) nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m calipso.carga --esperar; echo ESPERA=$?
CALIPSO_HOME=$(mktemp -d) nice -n 19 /var/home/pedro/calipso/.venv/bin/python experimentos/recall_banco.py --home ~/.calipso --reales "$REALES" 2>&1 | grep '^\[banco\]'
# esperado: cuatro lineas "[banco] <condicion>: hit@1 a/24 hit@4 b/24 reales r/5 margen m umbral sugerido u";
# ninguna linea PARADA. Si hay PARADA: se para aca y se le lleva la tabla a Pedro (ruling 1 de este plan).
```

Con Ollama caido o sin bge-m3 el banco levanta `EmbedError`: no se doblan los numeros. Anotar en el reporte de la task los tiempos (`s docs`, `s consultas`) de cada condicion: son el dato del costo del reindex y del recall.

- [ ] **Step 10: anotar los umbrales (el paso explicito del spec, seccion 3)**

Con el MD a la vista, elegir por el margen (con los aciertos de MiniLM como piso):

1. `RECALL_MIN_SCORE` (el turno): el `umbral sugerido` de la variante `bge-m3:pregunta+150` (o de la variante que mejor separe, ver 3). Reemplazar en `calipso/server.py` el default `0.30` de `memoria_procedencia.umbral_por_env("CALIPSO_RECALL_MIN_SCORE", 0.30, alias="CALIPSO_RECALL_MIN")` por ese numero y completar el comentario de arriba con una linea `# Corrida 2026-09-12: hit@1 a/24, hit@4 b/24, aciertos min X, negativas max Y, margen M.`
2. `RECALL_UMBRAL` (el abismo): mas bajo que el del turno, dentro del margen (la consulta la escribe el modelo): `max(negativas) + 0.25 * margen`, redondeado a dos decimales. Reemplazar el default `0.20` en `calipso/abismo/fuentes.py` y completar su comentario con la misma linea.
3. Si otra variante separa mejor que `pregunta+150` (mayor margen con hit@1 >= el de MiniLM en todos los topicos), cambiar `PALABRAS_RESPUESTA` en `calipso/memoria_embed.py` (0 = pregunta sola; para `par` usar `10_000`, que es EXACTAMENTE lo que el banco midio en `bge-m3:par`: `texto_para_embedding(doc, palabras=10_000)`) y anotarlo en el docstring del modulo: el NUMERO cambia, la forma no (ruling 2 de este plan). Los tests de `test_memoria_embed.py` no se tocan: prueban 150 explicito y el default por separado (`test_el_default_es_palabras_respuesta_leido_por_llamada`); sumar ahi un assert `assert me.PALABRAS_RESPUESTA == <el numero elegido>   # banco 2026-09-12: margen M contra M' de pregunta+150` para que la letra quede atada al banco. El fixture de la Task 4 se genera con la variante aterrizada.
4. Completar la seccion "Umbrales elegidos" de `experimentos/recall_banco_resultados.md` a mano con los tres valores y el motivo en una linea cada uno.
5. Verificar: `nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q -p no:cacheprovider test_recall_umbrales.py test_memoria_lectores.py test_memoria_embed.py 2>&1 | tail -1` -> `0 failed` (los tests de los lectores fijan `RECALL_MIN_SCORE` con monkeypatch: no dependen del numero).

- [ ] **Step 11: docs -- `AGENTS.md` y el estado del proyecto**

`AGENTS.md`, ANTES (`:430-431`):

```
Embeddings obligatorios: `bge-m3` via Ollama, por soporte multilingue. No usar el
default ingles de Chroma para ranking en espanol.
```

DESPUES:

```
Embeddings obligatorios: `bge-m3` via Ollama (`POST /api/embed`, `calipso/memoria_embed.py`;
`CALIPSO_EMBED_MODEL`, default `bge-m3:latest`, 1024 dims), por soporte multilingue. El server
NO importa torch ni sentence-transformers (`test_memoria_sin_torch.py` lo fija; spec
`docs/superpowers/specs/2026-09-12-memoria-embeddings-ollama-design.md`). La coleccion viva es
`episodic-<tag>` (`episodic-bge-m3`); la vieja `episodic` (MiniLM, 384 dims) queda intacta hasta
que `python -m calipso.memoria_reindex --embeddings` (server apagado) la copie; `GET /api/memory`
muestra `sin_reindexar`, `recall_ok` y `ultimo_recall_fallo`. El recall es fail-open (fila
`kind: memoria`). No usar el default ingles de Chroma para ranking en espanol.
```

`docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md`, ANTES (las dos ultimas lineas del archivo):

```
  Chromium, `CALIPSO_HOME=$(mktemp -d) .venv/bin/python -m calipso.carga --esperar` (abre con `justa`;
  `--holgada` exige holgada; 1500 MB para Chromium) y las suites con `nice -n 19`.
```

DESPUES:

```
  Chromium, `CALIPSO_HOME=$(mktemp -d) .venv/bin/python -m calipso.carga --esperar` (abre con `justa`;
  `--holgada` exige holgada; 1500 MB para Chromium) y las suites con `nice -n 19`.
- **La memoria embebe por Ollama (2026-09-12):** el server pesaba 1,5 GB antes de servir nada y se midio
  que era torch con build CUDA (475 MB), la cadena transformers/scipy/sklearn (270) y el tokenizer de
  MiniLM (295 vivos + 316 de heap que glibc no devuelve), no el modelo ni chroma. Decision de Pedro: los
  embeddings pasan a `bge-m3` en Ollama y el server se queda sin torch. Spec v2 (tres lentes, 14 rulings)
  `docs/superpowers/specs/2026-09-12-memoria-embeddings-ollama-design.md`; plan de 4 tasks
  `docs/superpowers/plans/2026-09-12-memoria-ollama.md`; rama `feat/memoria-ollama` en el worktree
  `.claude/worktrees/memoria-ollama`. `calipso/memoria_embed.py` (EF `calipso_ollama` pura, `EmbedFalsa`
  para la suite con `CALIPSO_EMBED_FALSA=1` en conftest), coleccion viva `episodic-bge-m3` al lado de la
  vieja (no se borra), `remember` con embeddings explicitos sobre la pregunta + 150 palabras y DESPUES del
  `done`, `recall` de una sola embedding y fail-open visible (`/api/memory`: `sin_reindexar`, `recall_ok`,
  `ultimo_recall_fallo`; el abismo cierra con `memoria_no_disponible`), `memoria_reindex --embeddings`
  (server apagado, idempotente), el embedder gobernado por la carga (`keep_alive` propio: justa/cargada 0;
  vigia por `/api/embed`), umbrales PROVISORIOS re-medidos con `experimentos/recall_banco.py` (vuelta
  atras: `CALIPSO_RECALL_MIN_SCORE`, `CALIPSO_RECALL_UMBRAL`). **Pendiente del controlador tras el
  merge:** `pip uninstall` con la lista explicita del spec (seccion 5, ~5 GB; se quedan onnxruntime,
  tokenizers, huggingface_hub, ctranslate2, faster-whisper), chequeo post-uninstall, el reindex del home
  real (`--embeddings` con el server apagado), reinicio, y el `VmRSS` antes/despues (esperado 1571 -> ~200).
  **Vuelta atras** (spec seccion 5): checkout de `main` + `pip install sentence-transformers --index-url
  https://download.pytorch.org/whl/cpu` (el indice CPU de torch, ~200 MB, no los 5 GB con CUDA); la
  coleccion vieja `episodic` sigue intacta en cada home y main la abre tal cual. NO vale
  `CALIPSO_EMBED_MODEL` como vuelta atras: abriria otra coleccion vacia.
```

- [ ] **Step 12: la suite entera y el commit**

```bash
CALIPSO_HOME=$(mktemp -d) nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m calipso.carga --esperar; echo ESPERA=$?
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama && nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q --ignore=test_chat_live.py -p no:cacheprovider 2>&1 | tail -1; echo EXIT=$?
# 0 failed, EXIT=0
git add calipso/carga.py calipso/memoria_embed.py calipso/memoria_procedencia.py calipso/server.py calipso/abismo/fuentes.py test_carga.py test_carga_vigia.py test_aduana_api.py test_memoria_embed.py test_recall_umbrales.py test_memoria_sin_torch.py experimentos/recall_banco.py experimentos/recall_banco_resultados.jsonl experimentos/recall_banco_resultados.md AGENTS.md docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md
git commit -m "feat(memoria): el banco de recall, los umbrales provisorios y el embedder bajo la carga -- experimentos/recall_banco.py mide MiniLM contra bge-m3 en tres variantes (pregunta, pregunta+150, par) con parafrasis y negativas por topico, hit@1 por topico, hit@4, distribucion y margen; RECALL_MIN_SCORE y RECALL_UMBRAL re-medidos, marcados PROVISORIOS y con vuelta atras por env (CALIPSO_RECALL_MIN_SCORE con alias CALIPSO_RECALL_MIN, CALIPSO_RECALL_UMBRAL); carga: mismo_modelo normaliza :latest en la memoria efectiva y el vigia, keep_alive_embed (holgada 5m, justa/cargada 0) por payload_local(keep_alive=), ollama_evict(embedding=True) por /api/embed, el embedder en _modelos_de_calipso y _modelos_configurados, el vigia lo descarga sin suspender el local; la aduana ya no declara la memoria; guardia anti-torch por AST y por sys.modules en subproceso; AGENTS.md y el estado del proyecto

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N3P8mZgfi31VYnG8sweiAa"
```

---

### Task 4: el fixture con las dos colecciones (generado UNA vez con `--embeddings`, README con la receta, test de ids iguales), el smoke en vivo con Ollama real (`experimentos/memoria_smoke.py`, incluida la convivencia con el 7b) y el informe

**Files:**
- Modify: `experimentos/fixtures/memoria_smoke_home/global/chroma/` (el sqlite y un directorio hnsw nuevo), `experimentos/fixtures/memoria_smoke_home/projects/var-home-pedro-calipso/chroma/`, `experimentos/fixtures/memoria_smoke_home/README.md`; `test_memoria_reindex.py:183-202` (`test_sobre_una_copia_del_fixture_real`)
- Create: `test_memoria_fixture.py`, `experimentos/memoria_smoke.py`, `docs/superpowers/2026-09-12-smoke-memoria.md`
- Test: `test_memoria_fixture.py`, `test_memoria_reindex.py`, `test_memoria_sin_torch.py`; el smoke (manual, con Ollama real)

**Interfaces:**
- Consumes (Task 1-3): `memoria_embed.COLECCION_VIVA`, `COLECCION_VIEJA`, `sin_reindexar(cliente)`, `EmbedFalsa`, `OllamaEmbed(url=)`, `texto_para_embedding`; `memoria_reindex --embeddings` (Task 2); `carga.ollama_evict(nombre, embedding=True)`, `carga.keep_alive_embed`, `carga.medir` (Task 3); `GET /api/memory` con `sin_reindexar`/`recall_ok`/`ultimo_recall_fallo`; las filas `kind: memoria` (`recall_fallo`, `remember_fallo`); `CALIPSO_EMBED_URL` (config, Task 1).
- Produces: el fixture con `episodic` (384 dims, 16) y `episodic-bge-m3` (1024 dims, 16, mismos ids/documentos/metadatos) en `global/chroma`, y `episodic-bge-m3` vacia en el proyecto; `experimentos/memoria_smoke.py` (codigos: 0 ok, 1 fallos, 3 bloqueado por recursos); el informe.

**En esta task SI se habla con Ollama real** (la regeneracion del fixture y el smoke), siempre tras `python -m calipso.carga --esperar` y nunca desde la suite. El server real no se toca (el smoke levanta el suyo en 8779 sobre un home temporal restaurado del fixture).

- [ ] **Step 1: regenerar el fixture con `--embeddings` (UNA vez, con Ollama real)**

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama
CALIPSO_HOME=$(mktemp -d) nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m calipso.carga --esperar; echo ESPERA=$?
# ESPERA=0 (justa u holgada). Con 3: BLOQUEADO, no se sigue.
COPIA=$(mktemp -d)/home && cp -r experimentos/fixtures/memoria_smoke_home "$COPIA" && echo "$COPIA"
env -u CALIPSO_EMBED_FALSA CALIPSO_HOME="$COPIA" CALIPSO_PORT=1 nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m calipso.memoria_reindex --embeddings
# esperado (10-45 s: las dos respuestas de 5,7k chars van truncadas a 150 palabras, asi que menos):
#   home: <copia>
#   global: 16 copiados a episodic-bge-m3, 0 ya estaban (metadatos actualizados), sin_reindexar 0
#   projects/var-home-pedro-calipso: 0 copiados a episodic-bge-m3, 0 ya estaban (metadatos actualizados), sin_reindexar 0
env -u CALIPSO_EMBED_FALSA CALIPSO_HOME="$COPIA" CALIPSO_PORT=1 nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m calipso.memoria_reindex --vista
# esperado: "global: 16 en episodic, 16 en episodic-bge-m3, sin_reindexar 0 (procedencia sobre episodic-bge-m3)"
#           y "global: 16 episodios, 0 con procedencia, ... -> 16 por reindexar" (NO se corre --aplicar: decision 17)
rm -rf experimentos/fixtures/memoria_smoke_home/global/chroma experimentos/fixtures/memoria_smoke_home/projects/var-home-pedro-calipso/chroma
cp -r "$COPIA/global/chroma" experimentos/fixtures/memoria_smoke_home/global/chroma
cp -r "$COPIA/projects/var-home-pedro-calipso/chroma" experimentos/fixtures/memoria_smoke_home/projects/var-home-pedro-calipso/chroma
git status --short experimentos/fixtures | cat
# esperado: M ...global/chroma/chroma.sqlite3, ?? ...global/chroma/<uuid nuevo>/ (el hnsw de la viva),
#           M ...projects/var-home-pedro-calipso/chroma/chroma.sqlite3; el directorio 771a6edf-... puede
#           cambiar de bytes (chroma compacta la cola al abrir): se commitea tal cual.
```

`CALIPSO_PORT=1` porque el server real escucha en 8000 y `--embeddings` se niega con el puerto ocupado (esta copia no es su home). `env -u CALIPSO_EMBED_FALSA` porque la variable exportada haria el fixture con vectores falsos (el test del Step 3 lo detecta).

- [ ] **Step 2: el README del fixture, entero**

`experimentos/fixtures/memoria_smoke_home/README.md`:

```
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
```

- [ ] **Step 3: los tests del fixture (en rojo hasta el Step 1; verdes con el fixture nuevo)**

`test_memoria_fixture.py`, completo:

```python
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
```

`test_memoria_reindex.py`, ANTES (`:183-202`, el test del fixture; con el DESPUES de la Task 2 el archivo ya importa `memoria_embed as me` y define `VIVA`):

```python
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
```

DESPUES:

```python
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
    codigo, texto = _correr("--embeddings")
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
    codigo, texto = _correr("--embeddings")
    assert codigo == 0, texto
    assert f"global: 16 copiados a {VIVA}, 0 ya estaban (metadatos actualizados), sin_reindexar 0" in texto
    viva = _leer(g, VIVA)
    assert viva["count"] == 16 and sorted(viva["ids"]) == sorted(vieja["ids"])
    assert _por_id(viva) == _por_id(vieja)
    assert {len(e) for e in viva["emb"]} == {1024}
    assert _leer(g) == vieja                                                # la vieja no se toca
    assert f"sin_reindexar 0 (procedencia sobre {VIVA})" in _correr("--vista")[1]
```

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama && nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q -p no:cacheprovider test_memoria_fixture.py test_memoria_reindex.py test_memoria_sin_torch.py 2>&1 | tail -1
# 5 nuevos (4 en test_memoria_fixture + el desde cero en test_memoria_reindex); 0 failed. Y torch ya no entra
# por el fixture: el --aplicar de test_sobre_una_copia_del_fixture_real corre sobre la viva
```

- [ ] **Step 4: commit del fixture**

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama
git add experimentos/fixtures/memoria_smoke_home test_memoria_fixture.py test_memoria_reindex.py
git commit -m "test(memoria): el fixture del smoke con las dos colecciones -- episodic (MiniLM, 384) y episodic-bge-m3 (1024, generada una vez con memoria_reindex --embeddings y Ollama real; mismos 16 ids, documentos y metadatos, sin procedencia), README con la receta, test_memoria_fixture.py (ids iguales, vectores de bge-m3 y no de la falsa, la suite lo abre con EmbedFalsa sin conflicto) y el test del reindex sobre la copia del fixture medido sobre la viva

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N3P8mZgfi31VYnG8sweiAa"
```

- [ ] **Step 5: `experimentos/memoria_smoke.py`, completo**

```python
#!/usr/bin/env python3
"""El smoke de la memoria por Ollama (spec 2026-09-12, seccion 5): un server
DESECHABLE en 8779 sobre un CALIPSO_HOME temporal restaurado del fixture (las
dos colecciones), Ollama REAL (bge-m3 y el 7b) y un proxy TCP local
(127.0.0.1:11435 -> 11434) al que el server apunta por CALIPSO_EMBED_URL:
cortar el proxy es "Ollama caido" para el embedder sin tocar el Ollama real.
El server real (8000, ~/.calipso) no se toca.

Pasos:
  0  la regla de recursos (`python -m calipso.carga --esperar`; 3 = BLOQUEADO), Ollama con los dos
     modelos, los puertos libres, el home restaurado, el proxy y el server arriba
  A  GET /api/memory: 16 episodios, sin_reindexar 0, recall_ok True
  R1 recall real por bge-m3 en ESTE proceso sobre otra copia del fixture: la pregunta del fixture
     trae su episodio arriba (score y tiempo, con la carga fria); un segundo recall caliente
  R2 un turno por el server con recall real: sin recall_fallo, texto, ruta
  D  `done` antes del remember: ms entre el ultimo chunk y done; segundos hasta que
     global_episodes pasa de 16 a 17 (el remember de fondo)
  C  Ollama caido a mitad (el proxy cortado): el turno entero con recall_fallo y remember_fallo,
     /api/memory con recall_ok False y ultimo_recall_fallo; el proxy vuelve y el turno siguiente
     deja recall_ok True
  X  el reindex sobre copias: idempotente sobre el fixture (0 copiados, 16 ya estaban) y desde cero
     (la viva borrada EN LA COPIA: 16 copiados, ids iguales), con los tiempos
  V  la descarga del embedder por /api/embed (carga.ollama_evict(..., embedding=True)): se calienta bge-m3
     con un POST propio con keep_alive 5m (bajo justa/cargada keep_alive_embed es 0 y el modelo se
     descargaria solo: el evict tiene que actuar sobre un modelo RESIDENTE), se espera verlo en /api/ps
     y recien ahi se evicta: /api/ps sin bge-m3
  J  la convivencia con el 7b (ruling 8.4): con el 7b cargado, un turno completo midiendo /api/ps
     antes, tras el done y tras el remember; si el 7b desaparece mientras bge-m3 esta, PARADA
     (se le dice a Pedro con los numeros; candidatas en el spec)

Salida: una linea [ok]/[FALLO]/[nota] por paso, el resumen y `resultados.json` en el home del smoke.
El informe se escribe a mano en docs/superpowers/2026-09-12-smoke-memoria.md. Codigos: 0 ok, 1 con
fallos (incluida la PARADA de J), 3 bloqueado por recursos.

    CALIPSO_HOME=$(mktemp -d) nice -n 19 .venv/bin/python experimentos/memoria_smoke.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
HOME_AGENTE = pathlib.Path(tempfile.mkdtemp(prefix="memoria-smoke-agente-"))
os.environ["CALIPSO_HOME"] = str(HOME_AGENTE)          # este proceso: jamas el home real
os.environ.pop("CALIPSO_EMBED_FALSA", None)             # el smoke embebe de verdad
os.environ.pop("CALIPSO_EMBED_URL", None)               # este proceso va directo a Ollama
sys.path.insert(0, str(RAIZ))

import chromadb  # noqa: E402

from calipso import carga  # noqa: E402
from calipso import config as calipso_config  # noqa: E402
from calipso import memoria_embed as me  # noqa: E402

FIXTURE = RAIZ / "experimentos" / "fixtures" / "memoria_smoke_home"
PUERTO = 8779
BASE = f"http://127.0.0.1:{PUERTO}"
WS = f"ws://127.0.0.1:{PUERTO}/ws/chat"
OLLAMA = "http://127.0.0.1:11434"
PUERTO_PROXY = 11435
EMBED_URL = f"http://127.0.0.1:{PUERTO_PROXY}"
MODELO = "qwen2.5:7b"
EMBED = calipso_config.EMBED_MODEL
SALIDA_BLOQUEADO = 3
PLAZO_TURNO_S = 900


# --- la regla de recursos --------------------------------------------------------

def esperar_no_cargada() -> None:
    r = subprocess.run([sys.executable, "-m", "calipso.carga", "--esperar", "--tope", "600"],
                       cwd=str(RAIZ), env=os.environ)
    if r.returncode != 0:
        print(f"[recursos] --esperar salio con {r.returncode}: BLOQUEADO, no arranco nada", flush=True)
        sys.exit(SALIDA_BLOQUEADO)


def medir() -> carga.Carga:
    return carga.medir(MODELO, ncpu=os.cpu_count(), modelos_propios={MODELO, EMBED})   # inyectado: sin cache


# --- Ollama ------------------------------------------------------------------------

def ps() -> list[dict]:
    with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=10) as r:
        return json.loads(r.read()).get("models", [])


def nombres(lista: list[dict]) -> list[str]:
    return [m.get("name", "") for m in lista]


def cargado(nombre: str, lista: list[dict] | None = None) -> bool:
    return any(carga.mismo_modelo(n, nombre) for n in nombres(ps() if lista is None else lista))


def esperar_ps(condicion, segundos: int = 30) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        try:
            if condicion(ps()):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def calentar_embed() -> None:
    """Carga bge-m3 con keep_alive 5m EXPLICITO, sin pasar por OllamaEmbed:
    bajo `justa`/`cargada` `keep_alive_embed` es 0 y el modelo se descargaria
    solo al terminar, y el evict del paso V actuaria sobre un modelo no
    residente (lo cargaria y descargaria: un [ok] vacuo)."""
    datos = json.dumps({"model": EMBED, "input": ["x"], "truncate": True, "keep_alive": "5m"}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/embed", data=datos, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120):
        pass


def _ollama_listo() -> None:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5) as r:
            tags = nombres(json.loads(r.read()).get("models", []))
    except Exception as e:
        sys.exit(f"Ollama no responde en {OLLAMA}: {e}")
    for modelo in (MODELO, EMBED):
        if not any(carga.mismo_modelo(t, modelo) for t in tags):
            sys.exit(f"Ollama no tiene {modelo}: {tags}")


def _puerto_libre(puerto: int) -> None:
    try:
        with socket.create_connection(("127.0.0.1", puerto), timeout=1):
            pass
    except OSError:
        return
    sys.exit(f"algo ya escucha en 127.0.0.1:{puerto}: no levanto nada ahi")


# --- el proxy ("Ollama caido" sin matar a Ollama) ---------------------------------

class Proxy:
    """Un reenvio TCP 127.0.0.1:PUERTO_PROXY -> 127.0.0.1:11434 que se corta
    (cierra el listener y las conexiones vivas) y se reanuda. El server
    desechable apunta su embedder aca (CALIPSO_EMBED_URL); el sensor de la
    carga y el 7b van directo (carga.OLLAMA, dispatch)."""

    def __init__(self, destino=("127.0.0.1", 11434)) -> None:
        self.destino = destino
        self.listener: socket.socket | None = None
        self.conexiones: set[socket.socket] = set()
        self.lock = threading.Lock()

    def reanudar(self) -> None:
        l = socket.socket()
        l.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        l.bind(("127.0.0.1", PUERTO_PROXY))
        l.listen(16)
        self.listener = l
        threading.Thread(target=self._aceptar, args=(l,), daemon=True).start()

    def cortar(self) -> None:
        l, self.listener = self.listener, None
        if l is not None:
            l.close()
        with self.lock:
            for s in list(self.conexiones):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    s.close()
                except OSError:
                    pass
            self.conexiones.clear()

    def _aceptar(self, l: socket.socket) -> None:
        while True:
            try:
                cliente, _ = l.accept()
            except OSError:
                return
            try:
                arriba = socket.create_connection(self.destino, timeout=10)
            except OSError:
                cliente.close()
                continue
            with self.lock:
                self.conexiones.update({cliente, arriba})
            for a, b in ((cliente, arriba), (arriba, cliente)):
                threading.Thread(target=self._bombear, args=(a, b), daemon=True).start()

    def _bombear(self, a: socket.socket, b: socket.socket) -> None:
        try:
            while True:
                datos = a.recv(65536)
                if not datos:
                    break
                b.sendall(datos)
        except OSError:
            pass
        finally:
            for s in (a, b):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    s.close()
                except OSError:
                    pass
            with self.lock:
                self.conexiones.discard(a)
                self.conexiones.discard(b)


# --- el server desechable ------------------------------------------------------------

def restaurar_home() -> pathlib.Path:
    home = pathlib.Path(tempfile.mkdtemp(prefix="memoria-smoke-"))
    shutil.copytree(FIXTURE, home, dirs_exist_ok=True)
    (home / "README.md").unlink(missing_ok=True)
    (home / "catastro.json").write_text(
        json.dumps({"raices": [{"ruta": str(RAIZ), "profundidad": 1}], "proyectos": []}),
        encoding="utf-8")
    return home


class Server:
    def __init__(self, home: pathlib.Path) -> None:
        self.home = home
        self.token = secrets.token_urlsafe(24)
        env = {**os.environ, "CALIPSO_HOME": str(home), "CALIPSO_ROOT": str(RAIZ),
               "CALIPSO_TOKEN": self.token, "CALIPSO_NO_TOTP": "1",
               "CALIPSO_EMBED_URL": EMBED_URL}
        env.pop("CALIPSO_EMBED_FALSA", None)
        self.log = open(home / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "calipso.server:app",
             "--host", "127.0.0.1", "--port", str(PUERTO)],
            cwd=str(RAIZ), env=env, stdout=self.log, stderr=subprocess.STDOUT)

    def esperar(self, segundos: int = 120) -> None:
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            if self.proc.poll() is not None:
                sys.exit(f"el server murio al arrancar: ver {self.home}/server.log")
            try:
                with urllib.request.urlopen(f"{BASE}/login", timeout=2) as r:
                    if r.status == 200:
                        return
            except Exception:
                pass
            time.sleep(1)
        sys.exit(f"el server no levanto en {segundos} s: ver {self.home}/server.log")

    def apagar(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.log.close()

    def http(self, metodo: str, ruta: str, cuerpo: dict | None = None, timeout: int = 30):
        req = urllib.request.Request(
            f"{BASE}{ruta}", data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
            headers={"Cookie": f"calipso_token={self.token}", "Content-Type": "application/json"},
            method=metodo)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")

    def telemetria(self, kind: str) -> list[dict]:
        ruta = self.home / "telemetry.jsonl"
        if not ruta.exists():
            return []
        filas = [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [f for f in filas if f.get("kind") == kind]

    def esperar_fila(self, kind: str, accion: str, segundos: int = 60) -> dict | None:
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            for f in self.telemetria(kind):
                if f.get("accion") == accion:
                    return f
            time.sleep(1)
        return None

    def esperar_episodios(self, n: int, segundos: int = 120) -> float | None:
        """Segundos hasta que /api/memory dice global_episodes >= n (el
        remember de fondo), o None."""
        t0 = time.monotonic()
        limite = t0 + segundos
        while time.monotonic() < limite:
            if self.http("GET", "/api/memory")["global_episodes"] >= n:
                return round(time.monotonic() - t0, 2)
            time.sleep(0.2)
        return None


# --- un turno ------------------------------------------------------------------------

def chat_nuevo(server: Server, titulo: str) -> str:
    cid = server.http("POST", "/api/chats", {"title": titulo})["id"]
    server.http("POST", f"/api/chats/{cid}/activate", {})
    return cid


async def _turno(server: Server, mensaje: str) -> dict:
    import websockets   # en el .venv (lo usa test_chat_live.py)
    cid = chat_nuevo(server, f"memoria {mensaje[:24]}")
    t0 = time.monotonic()
    texto, meta, error = [], None, None
    t_ultimo_chunk = t_done = None
    async with websockets.connect(WS, additional_headers={"Cookie": f"calipso_token={server.token}"},
                                  max_size=None) as ws:
        await ws.send(json.dumps({"text": mensaje, "chat_id": cid}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=PLAZO_TURNO_S)
            try:
                pkt = json.loads(raw)
            except Exception:
                continue
            t = pkt.get("type", "")
            if t == "chunk":
                texto.append(pkt.get("text", ""))
                t_ultimo_chunk = time.monotonic()
            elif t == "meta" and meta is None:
                meta = pkt
            elif t == "error":
                error = pkt.get("text")
            elif t == "done":
                t_done = time.monotonic()
                break
    return {"chat": cid, "texto": "".join(texto), "meta": meta, "error": error,
            "ms": int((time.monotonic() - t0) * 1000),
            "done_tras_ultimo_chunk_ms": (int((t_done - t_ultimo_chunk) * 1000)
                                          if t_done and t_ultimo_chunk else None)}


def turno(server: Server, mensaje: str) -> dict:
    return asyncio.run(_turno(server, mensaje))


# --- el reindex sobre copias ------------------------------------------------------------

def reindex_sobre_copia(borrar_viva: bool) -> dict:
    copia = pathlib.Path(tempfile.mkdtemp(prefix="memoria-smoke-reindex-"))
    shutil.copytree(FIXTURE, copia, dirs_exist_ok=True)
    if borrar_viva:                                  # EN LA COPIA, jamas en el fixture ni en un home
        for sub in ("global/chroma", "projects/var-home-pedro-calipso/chroma"):
            try:
                chromadb.PersistentClient(path=str(copia / sub)).delete_collection(me.COLECCION_VIVA)
            except Exception:
                pass                                     # la copia del proyecto puede no tener la viva
    env = {**os.environ, "CALIPSO_HOME": str(copia), "CALIPSO_PORT": "1"}
    env.pop("CALIPSO_EMBED_URL", None)
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, "-m", "calipso.memoria_reindex", "--embeddings"],
                       cwd=str(RAIZ), env=env, capture_output=True, text=True, timeout=900)
    cli = chromadb.PersistentClient(path=str(copia / "global" / "chroma"))
    return {"texto": r.stdout + r.stderr, "codigo": r.returncode, "s": time.monotonic() - t0,
            "ids_iguales": me.ids_de(cli, me.COLECCION_VIEJA) == me.ids_de(cli, me.COLECCION_VIVA),
            "sin_reindexar": me.sin_reindexar(cli)}


# --- los resultados ---------------------------------------------------------------------

class Resultados:
    def __init__(self) -> None:
        self.filas: list[tuple[str, bool, str]] = []

    def ok(self, paso: str, cond: bool, detalle: str = "") -> bool:
        self.filas.append((paso, bool(cond), detalle))
        print(f"[{'ok' if cond else 'FALLO'}] {paso}: {detalle}", flush=True)
        return bool(cond)

    def nota(self, paso: str, detalle: str) -> None:
        self.filas.append((paso, True, detalle))
        print(f"[nota] {paso}: {detalle}", flush=True)

    def fallos(self) -> int:
        return sum(1 for _, c, _ in self.filas if not c)


# --- el smoke ------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="el smoke de la memoria por Ollama")
    ap.add_argument("--sin-esperar", action="store_true", help="saltar --esperar (solo si ya se corrio a mano)")
    args = ap.parse_args(argv)
    R = Resultados()
    # 0
    if not args.sin_esperar:
        esperar_no_cargada()
    _ollama_listo()
    _puerto_libre(PUERTO)
    _puerto_libre(PUERTO_PROXY)
    c0 = medir()
    R.nota("0 la maquina", f"{c0.nivel} ({c0.motivo}) mem_disponible {c0.mem_disponible_mb} MB efectiva "
                           f"{c0.mem_efectiva_mb}; /api/ps {nombres(ps())}")
    proxy = Proxy()
    proxy.reanudar()
    home = restaurar_home()
    server = Server(home)
    server.esperar()
    R.nota("0 server", f"8779 arriba sobre {home}; embedder por el proxy {EMBED_URL}")
    try:
        # A
        m = server.http("GET", "/api/memory")
        R.ok("A /api/memory", m["global_episodes"] == 16 and m["sin_reindexar"] == {"global": 0, "project": 0}
             and m["recall_ok"] is True and m["ultimo_recall_fallo"] is None,
             json.dumps({k: m.get(k) for k in ("global_episodes", "project_episodes", "sin_reindexar",
                                                "recall_ok", "ultimo_recall_fallo")}))
        # R1: recall real en este proceso sobre otra copia
        from calipso import memory
        memory.CALIPSO_HOME = restaurar_home()
        mem = memory.Memory(project_root=str(RAIZ))
        assert type(mem._embed) is me.OllamaEmbed, "el smoke construyo la EF falsa"
        t0 = time.monotonic()
        hits = mem.recall("hola, que libro te conte que empece?", n=4)
        dt = time.monotonic() - t0
        R.ok("R1 recall real por bge-m3 (frio)", bool(hits) and mem.recall_ok and "libro" in hits[0]["text"].lower(),
             f"{dt:.2f} s; top-4: " + " | ".join(f"{h['score']} {h['text'][16:70]!r}" for h in hits))
        t0 = time.monotonic()
        hits = mem.recall("che, quien me presto el libro rosa? no me acuerdo", n=4)
        dt = time.monotonic() - t0
        R.ok("R1 recall caliente", bool(hits) and "rosa" in hits[0]["text"].lower(),
             f"{dt:.2f} s; top-1 {hits[0]['score']} {hits[0]['text'][16:70]!r}")
        R.nota("R1 /api/ps", str(nombres(ps())))
        # R2 + D
        t = turno(server, "/local hola, que libro te conte que empece?")
        fallos_recall = [f for f in server.telemetria("memoria") if f["accion"] == "recall_fallo"]
        R.ok("R2 turno con recall por el server", t["error"] is None and t["texto"].strip() != "" and not fallos_recall,
             f"{t['ms']} ms; ruta {(t['meta'] or {}).get('route')}/{(t['meta'] or {}).get('model')}; "
             f"texto {t['texto'][:80]!r}")
        R.ok("D done antes del remember", t["done_tras_ultimo_chunk_ms"] is not None and t["done_tras_ultimo_chunk_ms"] < 500,
             f"{t['done_tras_ultimo_chunk_ms']} ms entre el ultimo chunk y done")
        s_rem = server.esperar_episodios(17)
        R.ok("D el remember de fondo", s_rem is not None, f"global_episodes 16 -> 17 en {s_rem} s tras el done")
        R.nota("D /api/ps tras el turno", str(nombres(ps())))
        # C: Ollama caido a mitad (para el embedder)
        proxy.cortar()
        t = turno(server, "/local en que quedamos la otra vez con el presupuesto del taller?")
        fallos_recall = [f for f in server.telemetria("memoria") if f["accion"] == "recall_fallo"]
        R.ok("C turno con Ollama caido para el embedder", t["error"] is None and t["texto"].strip() != "" and bool(fallos_recall),
             f"{t['ms']} ms; recall_fallo: {(fallos_recall[-1]['error'][:90] if fallos_recall else None)!r}")
        rf = server.esperar_fila("memoria", "remember_fallo", 60)
        R.ok("C remember_fallo", rf is not None, (rf or {}).get("error", "")[:90])
        m = server.http("GET", "/api/memory")
        R.ok("C /api/memory con recall_ok False", m["recall_ok"] is False and bool(m["ultimo_recall_fallo"]),
             json.dumps(m["ultimo_recall_fallo"]))
        proxy.reanudar()
        t = turno(server, "/local hola de nuevo")
        m = server.http("GET", "/api/memory")
        R.ok("C se recupera solo", t["error"] is None and m["recall_ok"] is True, f"recall_ok {m['recall_ok']}")
        server.esperar_episodios(18)
        # X
        r1 = reindex_sobre_copia(borrar_viva=False)
        R.ok("X reindex idempotente sobre el fixture", r1["codigo"] == 0 and "0 copiados" in r1["texto"]
             and "16 ya estaban" in r1["texto"] and r1["sin_reindexar"] == 0, f"{r1['s']:.1f} s")
        r2 = reindex_sobre_copia(borrar_viva=True)
        R.ok("X reindex desde cero (la viva borrada en la copia)", r2["codigo"] == 0 and "16 copiados" in r2["texto"]
             and r2["ids_iguales"] and r2["sin_reindexar"] == 0, f"{r2['s']:.1f} s para 16 documentos")
        # V
        calentar_embed()                                   # keep_alive 5m explicito: residente pase lo que pase con el nivel
        residente = esperar_ps(lambda l: cargado(EMBED, l), 20)
        cv = medir()
        ok = carga.ollama_evict(EMBED, embedding=True)
        R.ok("V descarga del embedder por /api/embed", residente and ok and esperar_ps(lambda l: not cargado(EMBED, l), 20),
             f"residente antes del evict {residente}; nivel {cv.nivel} (keep_alive_embed {carga.keep_alive_embed(cv.nivel)!r}); "
             f"ollama_evict {ok}; /api/ps {nombres(ps())}")
        # J
        antes = ps()
        c1 = medir()
        t1 = turno(server, "/local decime en una linea que es un websocket")
        ps_done1 = ps()
        server.esperar_episodios(19)
        ps_rem1 = ps()
        R.nota("J nivel", f"{c1.nivel} ({c1.motivo}) mem_disponible {c1.mem_disponible_mb} efectiva {c1.mem_efectiva_mb}; "
                          f"keep_alive_embed {carga.keep_alive_embed(c1.nivel)!r}")
        R.nota("J turno 1 (carga el 7b)", f"antes {nombres(antes)}; tras done {nombres(ps_done1)}; tras remember "
                                          f"{nombres(ps_rem1)}; {t1['ms']} ms")
        antes2 = ps()
        c2 = medir()
        t2 = turno(server, "/local y en dos lineas, que es http?")
        ps_done2 = ps()
        s_rem2 = server.esperar_episodios(20)
        ps_rem2 = ps()
        desalojado = cargado(MODELO, antes2) and (not cargado(MODELO, ps_done2) or not cargado(MODELO, ps_rem2))
        R.ok("J convivencia con el 7b", not desalojado,
             f"nivel {c2.nivel}; antes {nombres(antes2)}; tras done {nombres(ps_done2)}; tras remember {nombres(ps_rem2)}; "
             f"turno {t2['ms']} ms, remember {s_rem2} s"
             + ("  PARADA: Ollama desalojo al 7b (ruling 8.4): decidir con Pedro" if desalojado else ""))
    finally:
        server.apagar()
        proxy.cortar()
    print("\n== resumen ==")
    for paso, cond, detalle in R.filas:
        print(f"  [{'ok' if cond else 'FALLO'}] {paso}: {detalle[:160]}")
    (HOME_AGENTE / "resultados.json").write_text(
        json.dumps([{"paso": p, "ok": c, "detalle": d} for p, c, d in R.filas], ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"resultados: {HOME_AGENTE / 'resultados.json'}; server.log: {home / 'server.log'}; fallos: {R.fallos()}")
    return 1 if R.fallos() else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: correr el smoke**

```bash
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama
CALIPSO_HOME=$(mktemp -d) nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m py_compile experimentos/memoria_smoke.py && echo COMPILA
SALIDA=$(mktemp -d)/memoria_smoke.out && echo "$SALIDA"
CALIPSO_HOME=$(mktemp -d) nice -n 19 /var/home/pedro/calipso/.venv/bin/python experimentos/memoria_smoke.py 2>&1 | tee "$SALIDA"; echo SMOKE=${PIPESTATUS[0]}
# esperado: [ok] en A, R1 (x2), R2, D (x2), C (x4), X (x2), V, J; SMOKE=0. Tiempos: R1 frio ~2-3 s
# (carga fria de bge-m3), caliente 0,2-0,5 s; D: done tras el ultimo chunk < 50 ms, remember 0,5-5 s;
# C: recall_fallo con "connection refused"; X: 10-45 s desde cero; V: ps sin bge-m3 en < 5 s.
# Con SMOKE=3: BLOQUEADO por recursos, se reintenta mas tarde. Con SMOKE=1: se lee el paso que fallo
# (server.log en el home del smoke) y, si es J con PARADA, se para y se le lleva a Pedro (ruling 6).
```

Si el turno de R2 no trae `chunk` (el 7b tarda mas de 900 s bajo carga) el smoke aborta con `TimeoutError`: se repite con la maquina mas libre, no se baja `PLAZO_TURNO_S`.

- [ ] **Step 7: el informe `docs/superpowers/2026-09-12-smoke-memoria.md`**

Escrito a mano desde la salida del smoke (los numeros reales, no los esperados), con estas secciones:

```
# Smoke de la memoria por Ollama (2026-09-12)

Rama `feat/memoria-ollama` @ <commit>, `experimentos/memoria_smoke.py`, server desechable 8779 sobre el
fixture con las dos colecciones, Ollama 0.30.10 con `bge-m3:latest` y `qwen2.5:7b`, embedder por el proxy
127.0.0.1:11435. El server real no recibio nada.

## La maquina

- nivel al arrancar, mem_disponible/efectiva, /api/ps (paso 0); si hubo --esperar y cuanto espero

## Los pasos

| paso | resultado | numeros |
|---|---|---|
| A /api/memory | ok/FALLO | sin_reindexar, recall_ok |
| R1 recall real frio / caliente | | segundos, top-1 score y texto |
| R2 turno con recall | | ms, ruta |
| D done antes del remember | | ms entre ultimo chunk y done; s hasta 17 episodios |
| C Ollama caido | | recall_fallo, remember_fallo, ultimo_recall_fallo, recuperacion |
| X reindex | | s idempotente, s desde cero, ids iguales |
| V evict por /api/embed | | ps despues |
| J convivencia | | nivel, ps antes/tras done/tras remember, ms |

## Lo que se vio y no estaba escrito

- (hallazgos: p. ej. la carga fria del embedder en el primer recall, si el 7b y bge-m3 convivieron o no
  y bajo que nivel, el keep_alive que rigio, cuanto tardo el remember con una respuesta larga)

## Lo que el smoke NO ejercito

- el vigia bajo `cargada` con bge-m3 listado (cubierto por test_carga_vigia con el hook; el evict real se
  probo desde afuera en V), los departamentos (no existen), el uninstall (del controlador)

## Veredicto

- ok / con fallos / PARADA (J), y que decide Pedro

## Pendiente del controlador

- merge; pip uninstall con la lista del spec (seccion 5); chequeo post-uninstall
  (`CALIPSO_HOME=$(mktemp -d) .venv/bin/python -c "import chromadb, ollama, faster_whisper, calipso.server"`);
  reindex del home real con el server apagado (`--vista` y luego `--embeddings`); reinicio; VmRSS antes y
  despues; la coleccion vieja queda (otra tanda cuando sin_reindexar sea 0 en todos los homes)
- vuelta atras (spec seccion 5): checkout de `main` + `pip install sentence-transformers --index-url
  https://download.pytorch.org/whl/cpu` (el indice CPU de torch, ~200 MB); la coleccion `episodic` sigue
  intacta y main la abre tal cual; NO vale `CALIPSO_EMBED_MODEL` (abriria otra coleccion vacia)
```

- [ ] **Step 8: la suite entera y el commit**

```bash
CALIPSO_HOME=$(mktemp -d) nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m calipso.carga --esperar; echo ESPERA=$?
cd /var/home/pedro/calipso/.claude/worktrees/memoria-ollama && nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q --ignore=test_chat_live.py -p no:cacheprovider 2>&1 | tail -1; echo EXIT=$?
# 0 failed, EXIT=0
git add experimentos/memoria_smoke.py docs/superpowers/2026-09-12-smoke-memoria.md
git commit -m "docs(memoria): el smoke en vivo de la memoria por Ollama -- experimentos/memoria_smoke.py (server desechable 8779 sobre el fixture con las dos colecciones, Ollama real, proxy local para cortar el embedder a mitad): /api/memory, recall real por bge-m3 frio y caliente, el turno con recall, done antes del remember con los tiempos, Ollama caido (recall_fallo, remember_fallo, recall_ok False y recuperacion), el reindex sobre copias (idempotente y desde cero), la descarga por /api/embed y la convivencia con el 7b midiendo /api/ps por paso (regla de parada del spec); el informe con los numeros

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01N3P8mZgfi31VYnG8sweiAa"
```

Con esto termina el corte del spec (seccion 7). El merge, el `pip uninstall`, el reindex del home real y el reinicio del server real son del controlador (spec seccion 5, "Despliegue"; rulings 5 y 11 de este plan).

---

## Self-review

### 1. Cobertura del spec, seccion por seccion -> task

- **Seccion 1 (de donde sale, la decision):** el goal y la arquitectura; el server sin torch se fija en la Task 3 (`test_memoria_sin_torch.py`, AST + `sys.modules` en subproceso).
- **Seccion 2, `memoria_embed.py`:** Task 1 entera (`OllamaEmbed` con la firma `(self, input)`, `name`, `get_config`, `build_from_config`, `register_embedding_function`, `urllib` en `_post_embed` con la entrada en `EXCEPCIONES`, `truncate: true`, `payload_local` + `usando()`, timeouts 10/120 por uso, lotes <= 8000 chars con el largo solo); la tabla `keep_alive_embed` en la Task 3 (Step 3-4).
- **Seccion 2, `EMBED_MODEL`/`EMBED_DIMS` en config, el tag, `_modelos_de_calipso`, `_modelos_configurados`, la normalizacion de `:latest`, `ollama_evict` por `/api/embed`:** config en la Task 1; la carga y el vigia en la Task 3.
- **Seccion 2, colecciones por tag, la vieja intacta, `reflect`/`recent` sobre la viva, la vuelta a MiniLM por checkout:** Task 1 (`Scope.__init__`); nada borra la vieja (ruling 3 de este plan).
- **Seccion 2, que se embebe (ruling 8.5):** `texto_para_embedding` + `remember` con `embeddings=` + `recall` con `query_embeddings` en la Task 1; las tres variantes en el banco (Task 3).
- **Seccion 2, el reindex `--embeddings`:** Task 2 (sin `--forzar`, lotes por tamano, `update` para los presentes, doble lista de ids, `--vista` con `sin_reindexar`, `--vista/--aplicar` sobre la viva, departamentos fuera, cuantos copio y cuantos quedan, no borra).
- **Seccion 2, el server con memoria sin migrar:** Task 2 (`/api/memory`, `_anunciar_memoria`, fila `sin_reindexar`, fail-open del arranque).
- **Seccion 2, recall fail-open visible y el bug del websocket:** Task 1 (`Memory.recall`) + Task 2 (`recall_ok`/`ultimo_recall_fallo` en `/api/memory`, `memoria_no_disponible` en el abismo, el test del harness con la memoria muerta).
- **Seccion 2, una sola embedding y ninguna sin episodios:** Task 1 (`Memory.recall`, `Scope.recall(embedding=)`, los dobles de `test_abismo_memoria_recall.py`).
- **Seccion 2, el remember despues del `done` (ruling 8.3):** Task 2 (`_TAREAS_DE_FONDO`, `_en_fondo`, la corutina inline, `remember_fallo`, `esperar_fondo` en el harness, el fixture `turno` re-acotado).
- **Seccion 2, adios torch:** Task 1 (`memory.py` sin `SentenceTransformerEmbeddingFunction`) + Task 3 (el guardia). `calipso.sh`/`LINUX_MIGRATION.md`: nada que sacar (ruling 8.13, verificado por grep en el terreno); el `pip uninstall` es del controlador.
- **Seccion 2, la aduana:** Task 3 (`_declarar_arranque` sin "modelo de embeddings", los tres tests de `test_aduana_api.py`; la entrada del canario en la Task 1).
- **Seccion 2, `_switch_project` no se toca:** no se toca.
- **Seccion 2, tests:** `Memory(embed=)`, `EmbedFalsa`, `CALIPSO_EMBED_FALSA` en `conftest.py` (Task 1); los que cambian de letra: `test_aduana_api.py:440-449, :515, :596` (Task 3), `test_carga_vigia.py:143-145` (Task 3), `test_abismo_memoria_recall.py` (Task 1), `test_memoria_reindex.py:183-201` (Task 2 y 4), los docstrings de `test_memoria_carta.py:69-71`, `test_abismo_memoria_recall.py:3-4`, `test_aduana_canario.py:58`, `test_memoria_ambito.py:15` (Task 1). Sumados por este plan: `test_memoria_ambito.py:82-96` y `:144-153` (el fixture del turno y la coleccion falsa: el terreno los marco).
- **Seccion 3 (los umbrales se re-miden):** Task 3 (`recall_banco.py` con parafrasis, negativas, hit@1 por topico, hit@4, distribucion, margen, las 5 reales por contenido, MiniLM contra tres variantes; `umbral_por_env` con `CALIPSO_RECALL_MIN_SCORE`/`CALIPSO_RECALL_UMBRAL`; el Step 10 de anotar; la regla de parada en el script y en el ruling 1 de este plan).
- **Seccion 4 (invariantes):** 1 Task 3 (guardia); 2 Task 1 + 2 (fail-open, el harness); 3 Task 2 + 4 (idempotente, por ids, `sin_reindexar` visible, nada se borra); 4 Task 3 (banco) + Task 1 (colecciones distintas); 5 Task 1 + 3 (`payload_local`, `usando()`, la lista de modelos); 6 conftest + todos los tests (dobles de `urlopen`, `EmbedFalsa`).
- **Seccion 5 (verificacion):** unitarios de la EF (Task 1, Step 4), `Memory` con `EmbedFalsa` (Task 1), el reindex sobre la copia (Task 2 y 4), el server (Task 2 y 3), el banco (Task 3), el smoke con los siete pasos incluida la convivencia (Task 4). El despliegue (uninstall, chequeo, reindex real, reinicio, VmRSS) y la vuelta atras (checkout de main + sentence-transformers con el indice CPU de torch; la vieja intacta; no por env) quedan enumerados como pendiente del controlador en el informe (Task 4, Step 7) y en el estado del proyecto (Task 3, Step 11). El "16 copiados, ids iguales, metadatos iguales, sin_reindexar 16 -> 0" sobre la copia del fixture se prueba en la suite con EmbedFalsa (`test_embeddings_desde_cero_sobre_una_copia_del_fixture`, Task 4, Step 3) y con bge-m3 real en el smoke (paso X).
- **Seccion 6 (lo que NO hace):** respetado; ruling 7 de este plan (no pre-calentar) lo fija.
- **Seccion 7 (el corte):** las 4 tasks en ese orden.
- **Seccion 8 (14 rulings):** 8.1 Task 3 (`mismo_modelo`, `EMBED_MODEL = "bge-m3:latest"`, tag `bge-m3`); 8.2 Task 1 (EF pura, dims por config); 8.3 Task 2; 8.4 Task 3 (`keep_alive_embed`) + Task 4 (paso J con parada); 8.5 Task 1; 8.6 Task 3; 8.7 Task 1 (timeouts, lotes); 8.8 Task 1 + 2; 8.9 Task 2; 8.10 Task 1 (conftest); 8.11 Task 1 (config); 8.12 Task 4; 8.13 Task 3 (AGENTS.md); 8.14 nada mas se toca.

### 2. Scan de placeholders

Sin "TBD", "TODO", "implementar despues", "similar a la Task N", "agregar manejo de errores". Cada modulo nuevo esta completo (`memoria_embed.py`, `recall_banco.py`, `memoria_smoke.py`, los cinco archivos de tests nuevos), cada cambio en un archivo existente tiene su par ANTES/DESPUES textual, y cada Step de rojo y verde tiene su comando con lo esperado. Lo que se llena con la corrida esta explicito como acto: los dos numeros de los umbrales (Task 3, Step 10: "reemplazar el default 0.30/0.20 por ..."), el JSON de las consultas reales (Task 3, Step 9: escrito a mano, no commiteado) y el informe del smoke (Task 4, Step 7: las secciones y que numero va en cada una). Los `<...>` que quedan son eso (un id de chroma, el commit del informe), no codigo.

### 3. Consistencia de nombres y firmas entre tasks

- `memoria_embed.embeber(ef, textos, timeout=None)`: definida en Task 1; usada en `Scope.remember`/`Scope.recall`/`Memory.recall` (Task 1), `reindexar_embeddings` (Task 2), doblada en `test_memoria_reindex.py` (Task 2). Misma firma.
- `Scope.recall(query, n=5, embedding=None)`: Task 1; los dobles de `test_abismo_memoria_recall.py` (Task 1) la respetan.
- `memoria_embed.sin_reindexar(cliente)` / `ids_de(cliente, nombre)`: Task 1; `Scope.sin_reindexar`, `Memory.sin_reindexar` (dict por ambito), `_linea_estado`, `_anunciar_memoria`, `api_memory` (Task 2), `test_memoria_fixture.py` y el smoke (Task 4).
- `Memory.recall_ok` / `ultimo_recall_fallo` (`{"ts", "error"}`): Task 1; `api_memory` y `fuentes.memoria` (Task 2) los leen con `getattr(..., True/None)`.
- `memoria_reindex.abrir(cliente) -> (col, nombre)`: Task 2; su unico llamador es `main` (Task 2).
- `carga.payload_local(payload, nivel=None, keep_alive=None)`, `carga.keep_alive_embed(nivel)`, `carga.mismo_modelo(a, b)`, `carga.ollama_evict(model, base, timeout, embedding=False)`: Task 3; `OllamaEmbed.embed` (Task 3, Step 4), `_vigia_del_modelo` y `_ollama_evict_embedding` (Task 3), el smoke (Task 4: `carga.ollama_evict(EMBED, embedding=True)`, `carga.mismo_modelo`, `carga.keep_alive_embed`).
- `srv._TAREAS_DE_FONDO` / `srv._en_fondo(coro)`: Task 2; `Harness.esperar_fondo` y `test_memoria_server.py` (Task 2) los miran; el fixture `turno` de `test_memoria_ambito.py` (Task 2) exige `_en_fondo(` en el bloque.
- `memoria_procedencia.umbral_por_env(nombre, default, alias=None)`: Task 3; `server.py` y `fuentes.py` (Task 3); `test_recall_umbrales.py` (Task 3).
- `me.COLECCION_VIVA` / `COLECCION_VIEJA`: Task 1; `memory.COLECCION` (Task 1), `memoria_reindex` (Task 2), `VIVA` en los tests (Task 2 y 4), el banco y el smoke (Task 3 y 4).
- El texto exacto de las lineas de salida del reindex (`"{n} copiados a {viva}, {m} ya estaban (metadatos actualizados), sin_reindexar {k}"`, `"{n} en episodic, {m} en episodic-bge-m3, sin_reindexar {k} (procedencia sobre {col})"`, `"sin coleccion episodic-bge-m3 ni episodic (se salta)"`, `"sin coleccion episodic (se salta)"` para `--embeddings`): Task 2 lo define en `main`/`_linea_estado` y lo asertan `test_memoria_reindex.py` (Task 2 y 4), la receta del fixture (Task 4, Step 1) y el smoke (paso X: `"0 copiados"`, `"16 ya estaban"`, `"16 copiados"`).
- Las filas `kind: memoria`: `recall_fallo` (`error`, Task 1), `remember_fallo` (`error`, Task 2), `sin_reindexar` (`ambito`, `n`, Task 2); las asertan `test_memoria_embed.py`, `test_abismo_memoria_recall.py`, `test_memoria_server.py` y las lee el smoke.
- `test_carga.medida(nivel, modelos=...)`, `test_carga._Resp`, `test_carga.lector()`: existentes, usadas tal cual en `test_carga_vigia.py` y `test_carga.py` (Task 3).

### 4. Lo que se verifico leyendo y sondeando antes de escribir el plan (2026-09-12)

- Todas las anclas (`archivo:linea`) con `grep -n`/`sed -n` sobre el worktree @ `2276fcf`; los bloques ANTES estan extraidos por rango (no transcriptos); `grep -c` de las primeras lineas distintivas: 1 cada uno (`# 5) recordar el intercambio (episodica)`, `_last_features = features`, `def _medir_carga`, `def _declarar_arranque`, `RECALL_MIN_SCORE = float(`, `_KEEP_ALIVE = {`, `def payload_local`, `def ollama_evict`, `def _modelos_configurados`, `def abrir(chroma_dir`, `COLECCION = "episodic"`, `MOTIVOS = (`, `def motivo_de_consulta`, `RECALL_UMBRAL = 0.20`).
- Sonda de chroma 1.5.9 en un tmp (scratchpad `plan2/sonda_plan.py`): una EF hija de la registrada abre la misma coleccion sin conflicto; chroma AUTO-registra `type(ef)` al crear (de ahi `issubclass` y no identidad en los tests); `upsert` con `metadatas=[None, {...}]` y embeddings explicitos no llama a la EF; `get(include=[])` devuelve solo ids; `update(ids, metadatas)` desde un cliente sin EF funciona; `get_collection` de un nombre ausente levanta `NotFoundError`; `ef([])` levanta `ValueError`; `__call__` envuelto devuelve `list[np.ndarray]`; torch no entra por nada de esto.
- El fixture (leido en `mode=ro&immutable=1`): 16 documentos, 8 preguntas x 2 pasadas; los 8 topicos del banco salen de ahi (`TOPICOS` en `recall_banco.py`, con el fragmento que identifica cada pregunta).
- `chromadb.utils.embedding_functions.sentence_transformer_embedding_function` importa `sentence_transformers` de forma perezosa (adentro de `__init__`): `import chromadb` no arrastra torch; el guardia por `sys.modules` es viable antes del uninstall.
- `test_aduana_api.py:603-636` fija el ORDEN de `_startup_warm` con dobles que registran; `_anunciar_memoria` entra entre `_calentar_probes` y las rutinas sin romperlo (corre real contra la Memory de la suite: 0 pendientes, silencio).
- `test_abismo_chat.py` importa `time`; `test_memoria_lectores.py` ya llama a `_build_context` REAL dentro de la suite (por eso el harness de la memoria muerta lo puede restaurar; `economia_brief`/`proyectos_brief` se doblan igual para no depender del catastro).
- Los `pytest.MonkeyPatch.context()` de los dos tests que parchean y despues siguen usando el home temporal: un `monkeypatch.undo()` ahi habria deshecho tambien el `CALIPSO_HOME` del fixture y el reindex habria caido al home real (corregido al releer).

---

## Correcciones de la critica (15 aplicadas, 3 descartadas)

Dos criticos (lentes cobertura y fidelidad) sobre el plan @ `2276fcf`; los hallazgos repetidos por los dos cuentan una vez. Cada linea dice que se toco; lo verificado contra el arbol lleva su `grep -n`.

Aplicadas:

1. **[critico] La EF caida no llegaba al remember de fondo** (`Scope._embed` se fija en `Scope.__init__` con la referencia que `Memory.__init__` le pasa, `calipso/memory.py:161-171`; rebindear `Memory._embed` no la cambia): `test_memoria_server.py` gana `_matar(m)` (la caida en la fachada Y en cada `_scopes`) y lo usan `test_un_turno_con_la_memoria_muerta...` (docstring corregido: el remember embebe con el `_embed` del Scope) y `test_api_memory_trae_sin_reindexar...`; la interfaz de la Task 1 lo deja escrito en `Scope._embed`. Se eligio la correccion de test (minima) y no redisenar `Scope` para resolver la EF por la Memory.
2. **[importante] `PALABRAS_RESPUESTA` podia cambiar en el Step 10 y dejar la suite en rojo:** `texto_para_embedding(doc, palabras=None)` lee `PALABRAS_RESPUESTA` por llamada; `test_texto_para_embedding_es_la_pregunta_limpia_y_las_primeras_palabras_de_respuesta` usa `palabras=150` explicito (y prueba `palabras=10_000` = par); nuevo `test_el_default_es_palabras_respuesta_leido_por_llamada` (default == constante, y con monkeypatch 0 / 10_000); el Step 10 punto 3 dice que sumar (`assert me.PALABRAS_RESPUESTA == <n>` con el motivo del banco). Interfaces y decision 7 actualizadas.
3. **[importante] La condicion `bge-m3:par` del banco embebia el documento crudo** (con etiquetas y gestos), que el Step 10 no puede aterrizar (ruling 2): `texto_doc` devuelve `me.texto_para_embedding(doc, palabras=10_000)` para `par` y `palabras=150` explicito para `pregunta+150`; solo `minilm` sigue crudo (reproduce la produccion vieja). Docstring del banco y Step 10 punto 3 alineados. Con esto la letra del spec ("par entero") es el par en la forma aterrizable: pregunta limpia + respuesta entera sin etiquetas.
4. **[menor] Invariante 6 sin guardia:** nuevo `test_la_suite_construye_la_falsa_por_el_conftest` en `test_memoria_embed.py` (`CALIPSO_EMBED_FALSA == "1"` y `srv.mem._embed` y el de cada Scope son `EmbedFalsa`), con `import os`.
5. **[menor] `Scope.recall` no atrapa (decision 3) contra la letra del spec (seccion 2):** anotado en la decision 3 con el motivo (atrapar en el Scope dejaria `recall_ok` en True con la memoria muerta, contra 8.8) y la verificacion (`grep -n 'recall('`: solo `calipso/server.py:3201` y `calipso/abismo/fuentes.py:120`, por `Memory`). El spec manda en la CONDUCTA (ninguna excepcion sale, fila, `[]`), que se cumple; la letra queda para que el controlador la anote como ruling en la seccion 8 del spec al cierre (este corrector no edita el spec).
6. **[menor] `--embeddings --forzar` corria en silencio con el puerto libre:** `main` lo rechaza con codigo 2 ANTES de mirar el puerto; `test_embeddings_se_niega_con_el_puerto_ocupado_y_no_admite_forzar` lo prueba tambien con `CALIPSO_PORT=1` (el fixture `home`) y comprueba que la viva no se creo.
7. **[menor] La vuelta atras (spec seccion 5) no estaba escrita:** sumada a la entrada del estado del proyecto (Task 3, Step 11) y al "Pendiente del controlador" del informe del smoke (Task 4, Step 7): checkout de main + `pip install sentence-transformers --index-url https://download.pytorch.org/whl/cpu` (~200 MB), la coleccion `episodic` intacta, NO por `CALIPSO_EMBED_MODEL`.
8. **[menor] El paso V del smoke calentaba con `keep_alive_embed(nivel)` (0 bajo justa/cargada):** nuevo `calentar_embed()` (POST propio a `/api/embed` con `keep_alive: "5m"`), `esperar_ps(cargado)` antes del evict, y la fila anota si estaba residente y el nivel.
9. **[menor] El "16 copiados desde cero" sobre la copia del fixture quedaba solo en el smoke:** nuevo `test_embeddings_desde_cero_sobre_una_copia_del_fixture` en `test_memoria_reindex.py` (Task 4, Step 3): borra la viva EN LA COPIA, `--vista` dice `sin_reindexar 16`, `--embeddings` copia 16 con ids y metadatos iguales, 1024 dims, la vieja intacta, `sin_reindexar 0`. El conteo del Step 3 pasa a 5 nuevos.
10. **[menor] Conteos del Step 8/9 de la Task 1 (23/28 contra 25/30):** con los dos tests que suma esta critica (puntos 2 y 4) `test_memoria_embed.py` tiene 25 `def test_` (verificado: `grep -c '^def test_'` sobre el bloque = 25) y 25 + 5 = 30: los numeros escritos quedan correctos sin tocarlos.
11. **[menor] `test_canarios_chat.py` no existe** (`ls test_canarios*.py`: anclaje, degeneracion, ventana): el comando del Step 10 de la Task 2 nombra los tres.
12. **[menor] Anclas de linea desviadas** (los bloques ANTES matcheaban; solo los numeros): `test_memoria_reindex.py:172-180` -> `:165-169` (`grep -n 'def test_un_directorio_chroma_sin_la_coleccion_se_salta'` = 165); `test_aduana_canario.py:48` -> `:49` y `:44-48` -> `:44-49` (`grep -n 'calipso/carga.py:ollama_evict'` = 49); `test_memoria_ambito.py:143-153` -> `:144-153`, `:131-153` -> `:130-153`, `:79-96` -> `:82-96` (`grep -n 'def upsert'` = 144, `class _ColeccionFalsa` = 130, `@pytest.fixture` del turno = 82); `calipso/server.py:8795-8799` -> `:8794-8798` (el `try:` esta en 8794); `:5757-5759` -> `:5756-5762` (`for nombre in medida.modelos_cargados` = 5756, el bloque ANTES termina en 5762); `test_turno_secciones.py:114` -> `:115` (`grep -n num_ctx` = 115).
13. **[menor] El remember quedaba DESPUES de `send_json(done)`: un corte del cliente en ese send saltaba al `except WebSocketDisconnect` y el episodio no se guardaba** (regresion contra hoy, que lo guardaba antes del done): `_en_fondo(_recordar())` se llama justo ANTES del `await ws.send_json({"type": "done"})` (create_task solo programa: el remember arranca en la siguiente vuelta del loop y va a un hilo; el done sale igual de rapido, ruling 8.3 se cumple y lo mide el test de la puerta). El fixture `turno` de `test_memoria_ambito.py` exige ahora `{"type": "done"}` dentro del bloque y `_en_fondo(` antes que el done. Decision 6 y ruling 10 reescritos para distinguir "programar antes del send" (lo que se hace) de "esperar antes del done" (lo prohibido).
14. **[hallado por el corrector] `texto_para_embedding` con `palabras=0` dejaba VACIO un documento que no es un par** (`palabras_doc[:0]`): una meta o una ficha del jefe se habria embebido como `""` si el banco aterrizaba la variante pregunta sola. Nuevo `PALABRAS_OTRO = 300`, fijo, para lo que no parsea como par; `test_texto_para_embedding_tolera_otros_formatos` lo fija (`palabras=0` sobre una meta devuelve la meta). Sondeado en puro (`memoria_procedencia` + la funcion del plan): todos los asserts nuevos de los puntos 2 y 14 pasan.
15. **[hallado por el corrector] El comentario nuevo del paso 5 decia "buscarlo por 'recordar el intercambio'":** ese literal ANTES del bloque 6 hacia que `fuente.index("recordar el intercambio")` del fixture `turno` anclara en el paso 5 (el bloque medido habria sido otro). Reescrito sin el literal; la regla queda anotada en Global Constraints (primera aparicion).

Descartadas (con motivo):

- **Redisenar `Scope` para que resuelva la EF por la Memory** (alternativa del punto 1): tocaria `Scope.remember`, `Scope.recall`, el fixture `ambito` de `test_memoria_ambito.py` y `test_memory_acepta_una_ef_inyectada` para arreglar un rebindeo que solo hacen los tests; la correccion de test es la minima y deja escrito el porque.
- **Una cuarta condicion `bge-m3:crudo` en el banco** (alternativa del punto 3): mediria una forma que el ruling 2 prohibe aterrizar (etiquetas + gestos); sumarla solo confundiria la eleccion del Step 10. Si Pedro la quiere como referencia, es una linea en `CONDICIONES` y `texto_doc`.
- **Anotar el ruling de `Scope.recall` en la seccion 8 del spec** (punto 5): el corrector no edita el spec; queda en la decision 3 y en este ledger para el controlador.

Verificacion de este corrector (2026-09-12, sin server, sin pytest, sin Ollama): `py_compile` de los bloques completos extraidos del plan (`memoria_embed.py`, `test_memoria_embed.py`, `test_memoria_server.py`, `recall_banco.py`, `memoria_smoke.py`, `test_memoria_fixture.py`, el `main` nuevo de `memoria_reindex.py`): compilan; la sonda pura de `texto_para_embedding`: OK; conteos de `def test_` por bloque: 25 (embed) + 5 (abismo recall) en la Task 1, 7 + 7 en la Task 2, 4 + 1 en la Task 4.
