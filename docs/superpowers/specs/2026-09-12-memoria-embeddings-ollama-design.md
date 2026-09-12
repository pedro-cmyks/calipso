# La memoria embebe por Ollama: el server sin torch (2026-09-12, v2)

Spec de brainstorming con Pedro, 2026-09-12 (madrugada), revisado por tres lentes adversarias (modelo/YAGNI,
factibilidad por lectura, Codex gpt-5.5): la seccion 8 lista los rulings. Todo archivo:linea es de main
`6780bec`. Nota: `AGENTS.md:430` ya declaraba "embeddings obligatorios: bge-m3 via Ollama" desde junio; este
spec lo cumple.

## 1. De donde sale

Pedro, tras ver que el server pesa 1,5 GB antes de servir nada: *"pesado si es, intentemos optimizar siempre"*,
y la regla suya de siempre: **no poner techos, entender la causa**. Se midio (dos lectores, scripts en el
scratchpad de la sesion; el resumen en la seccion 2 del cierre de la carga). Del `VmRSS` de 1571 MB del
server real (pid 974148, 9 h de vida):

| causa | MB | detalle |
|---|---|---|
| `import torch` (build CUDA 13 en una APU AMD sin CUDA) | ~475 | libcublasLt 61, libnvrtc 27, libnvJitLink 25, libtriton 67 mapeados sin servir |
| `import sentence_transformers` (transformers, scipy, sklearn, triton) | ~270 | 4.500 modulos en `sys.modules` |
| el tokenizer del modelo (vocabulario de 250.002, backend Rust) | ~295 vivos + ~316 de heap que glibc no devuelve | `malloc_trim(0)` recupera 315 |
| los pesos (`model.safetensors`, 470 MB en disco) | ~82 | mmapeados; solo se paginan las capas y las filas tocadas |
| chromadb (import, dos `PersistentClient`, colecciones) | ~25-70 | los datos en disco no llegan a 1 MB |
| python, fastapi, uvicorn, calipso, runtime | ~150 | |

La causa de fondo: el server corre un segundo runtime de ML entero (torch, en su version con CUDA) para un
solo modelo chico (`paraphrase-multilingual-MiniLM-L12-v2`, 118M parametros, `calipso/memory.py:45`), que
ademas trunca a 128 tokens (solo la pregunta y el arranque de la respuesta entran al vector) y sale a
huggingface.co en cada construccion (`server.py:2174-2177`). Chroma y la memoria en si son marginales.

**Decision de Pedro (2026-09-12): los embeddings pasan a Ollama con `bge-m3`** (ya descargado desde junio:
566,7M parametros, F16, 1024 dimensiones, contexto 8192, multilingue; 1157 MB en disco, 1219 MB en RAM
mientras esta cargado, 0,17 s por embedding caliente, 2 s de carga fria, se descarga solo). El server se
queda sin torch: todo modelo vive en Ollama, gobernado por el sensor de carga.

## 2. La forma

- **`calipso/memoria_embed.py`** (puro salvo el POST a loopback): `OllamaEmbed(EmbeddingFunction)` para
  chroma, `__call__(self, input: list[str]) -> list[list[float]]` con la firma exacta que chroma valida,
  `name() = "calipso_ollama"`, `get_config() = {url, model, dims}`, `build_from_config`, registrada con
  `register_embedding_function` (asi el esquema persistido se reconstruye sin torch). Llama a
  `POST {base}/api/embed` con `urllib` (el canario de la aduana lo ve: entrada en `EXCEPCIONES`, como
  `carga.py:_ollama_get`) con `{"model": EMBED_MODEL, "input": [...], "truncate": true}` pasado por
  `carga.payload_local(payload, carga.nivel_reciente(), keep_alive=carga.keep_alive_embed(nivel))` (el mismo
  helper que los otros seis sitios para `num_thread`, pero con una tabla de `keep_alive` PROPIA del embedder,
  ruling 8.4: `holgada` `"5m"`, `justa` y `cargada` `0`: embebe y suelta, 2 s por uso, sin convivir con el 7b
  cuando la memoria esta justa) y dentro de `carga.usando()` (uso suelto: el vigia no descarga a mitad de un
  embed). El POST vive en una funcion de modulo `_post_embed(url, payload, timeout)` (la clave de
  `EXCEPCIONES` del canario se arma con nombres de funcion, no de clase). Timeouts distintos por uso (ruling
  8.7): recall 10 s (el turno sigue sin recuerdos), remember y reindex 120 s por lote. Lotes por tamano
  (<= 8.000 chars por request; un documento largo va solo), no por cantidad.
- **`EMBED_MODEL`** pasa a ser el nombre en Ollama tal como lo devuelve `/api/ps`: default
  **`bge-m3:latest`** (ruling 8.1: `bge-m3` a secas no matchea y la carga no lo veria); vive en
  `calipso/config.py` (sin chromadb, para que `carga` lo lea sin arrastrar nada) como `CALIPSO_EMBED_MODEL`.
  `EMBED_DIMS = 1024` fijo por config (no se consulta `/api/show`: `__init__`, `get_config` y
  `build_from_config` de la EF son puros, chroma los llama al crear y dos veces por `upsert`). El tag de
  coleccion es el nombre saneado (`bge-m3`: sin `:latest`, sin caracteres invalidos). El modelo se suma a
  `_modelos_de_calipso()` (`server.py`) y a `carga._modelos_configurados()`, con la comparacion de nombres
  normalizando `:latest` a ambos lados: su `size` cuenta en la memoria efectiva y el vigia puede descargarlo
  bajo `cargada` (`ollama_evict` aprende a descargar un modelo de solo embedding por `/api/embed` con
  `keep_alive: 0`, porque `/api/generate` puede rechazarlo: se verifica en el smoke).
- **Las colecciones llevan el embedder en el nombre:** `Scope` abre `episodic-<EMBED_TAG>` (tag = nombre del
  modelo saneado, `bge-m3`) en el mismo `chroma.sqlite3`. La coleccion vieja `episodic` (EF
  `sentence_transformer` persistida, 384 dims) queda intacta hasta que el reindex la copie: chroma prohibe
  cambiar la clase de EF de una coleccion existente y las dimensiones no coinciden (medido). `reflect`,
  `recent` y los conteos miran la coleccion viva: los episodios viejos vuelven al reindexar. La vuelta a
  MiniLM NO es por env (`CALIPSO_EMBED_MODEL` abriria otra coleccion vacia): es checkout de main mas
  reinstalar torch; la coleccion vieja sigue ahi.
- **Que se embebe (ruling 8.5):** el documento guardado sigue siendo el par entero, pero el vector se calcula
  sobre `texto_para_embedding(doc)` = la pregunta de Pedro mas las primeras 150 palabras de la respuesta
  (MiniLM veia 128 tokens: pregunta y arranque de la respuesta; el par entero de 2-6k chars queda dominado
  por la respuesta y cuesta 2-5 s). `remember` y el reindex embeben por afuera y hacen `upsert(...,
  embeddings=[...])`; `recall` consulta con `query_embeddings`. El banco (seccion 3) mide las tres variantes
  (pregunta sola, pregunta + 150 palabras, par entero) y si otra separa mejor se cambia el numero, no la
  forma.
- **El reindex a otro embedder** es un modo nuevo de `calipso/memoria_reindex.py`: `--embeddings` lee
  `episodic` (`COLECCION_VIEJA`, solo como origen) con `embedding_function=None` (`get` no reconstruye la EF:
  sin torch), y hace `upsert` de documentos y metadatos con los MISMOS ids en `episodic-<tag>` embebiendo por
  Ollama en lotes por tamano; idempotente: para un id que ya esta hace `update(ids, metadatas)` sin
  documents (los metadatos convergen sin re-embeber). SOLO con el server apagado: en este modo `--forzar` no
  existe (un corte no atomico entre la vieja y la nueva no tiene arreglo despues); ademas toma la lista de
  ids antes y despues y, si aparecieron ids durante la corrida, lo dice y no declara `sin_reindexar = 0`.
  `--vista` cuenta sin embeber e imprime `sin_reindexar` por ambito (el mismo calculo que el server).
  `--vista/--aplicar` (procedencia) pasan a operar sobre la coleccion VIVA (`episodic-<tag>`); el orden
  `--embeddings` y luego `--aplicar` (o al reves) converge. Cubre global y proyectos (los departamentos no
  existen hoy: quedan fuera, ruling 8.9). Al terminar imprime cuantos copio y cuantos quedan; NO borra la
  vieja.
- **El server con memoria sin migrar:** `GET /api/memory` devuelve `sin_reindexar: N` por ambito (docs en
  `episodic` que no estan en `episodic-<tag>`), el arranque lo imprime una vez, y la fila
  `kind: memoria, accion: sin_reindexar` va a telemetria. No se niega a arrancar: fail-open.
- **`recall` fail-open de verdad, y visible:** `Scope.recall` y `Memory.recall` atrapan cualquier excepcion
  (Ollama caido, timeout, coleccion rota) y devuelven `[]` con una fila `kind: memoria, accion:
  recall_fallo, error`. Hoy el recall del turno corre fuera del `try` del turno (`server.py:4195` contra
  `:4244`) y una excepcion tumba el websocket: bug preexistente que este cambio arregla de paso. Para que
  una memoria muerta no quede escondida (ruling 8.8): `GET /api/memory` devuelve `recall_ok` y
  `ultimo_recall_fallo` (hora y error), y la fuente `memoria` del abismo cierra con motivo
  `memoria_no_disponible` (no `sin_hits`). `remember` ya es fail-open en el server (`:4784-4790`) y en la
  fuente del abismo (`:8535-8537`).
- **Una sola embedding por turno, y ninguna si no hay que buscar:** `Memory.recall` mira primero que ambitos
  tienen episodios (`count() > 0`, la guardia que hoy vive en `Scope.recall`); si ninguno, devuelve `[]` sin
  embeber (asi la suite y un home nuevo no tocan Ollama); si alguno, embebe la pregunta UNA vez y consulta
  con `query_embeddings` (hoy embebe una vez por ambito). `Scope.recall(query, n, embedding=None)` conserva
  la costura vieja (si no viene el vector, embebe): los dobles de `test_abismo_memoria_recall.py` siguen.
- **El `remember` del turno pasa a despues del `done` (ruling 8.3):** hoy corre ANTES de `chats.append` y
  del `done` (`server.py:4784-4790` contra `:4820-4821`) y cuesta 10-40 ms; con bge-m3 costaria 0,4-4 s
  visibles en `pensando`. Se manda `done` primero y el remember queda como tarea de fondo (`asyncio.to_thread`
  adentro, mismo `try/except`, fila `remember_fallo` si falla), como ya hace el remember de la meta
  (`:3883-3891`); las tareas de fondo se guardan en un conjunto del server que el harness puede esperar.
- **Adios torch:** `memory.py` deja de importar `SentenceTransformerEmbeddingFunction`; nada del repo
  importa `torch`, `transformers` ni `sentence_transformers` (test que lo fija por AST, como el canario).
  `calipso.sh` y `LINUX_MIGRATION.md` dejan de instalarlos; el `pip uninstall` del venv real es un paso del
  despliegue (del controlador, reversible con `pip install`). `faster-whisper` (ctranslate2) no depende de
  torch y sigue igual.
- **La aduana:** la memoria deja de salir a huggingface.co; `_declarar_arranque` (`server.py:2171-2189`) ya
  no declara "modelo de embeddings" (whisper sigue declarando lo suyo al primer uso). El POST a Ollama es
  loopback: no cruza la aduana.
- **`_switch_project`** (`server.py:1906-1948`) sigue reconstruyendo `Memory` en el loop: ahora es barato
  (la EF no abre nada al construirse). No se toca.
- **Tests:** `Memory(embed=...)` acepta una EF inyectada, y ademas `memory.py` elige `EmbedFalsa` (hash
  determinista a 1024 dims, sin red, en `calipso/memoria_embed.py`) cuando `CALIPSO_EMBED_FALSA=1`, que
  `conftest.py` fija ANTES de importar `calipso` (como `CALIPSO_HOME`: varios tests importan
  `calipso.server` a nivel de modulo y eso construye `Memory()` antes de cualquier fixture). Ningun test
  llama a Ollama. `test_memory.py` (script manual) queda para correr a mano con Ollama. Tests que cambian de
  letra (enumerados para que la task no los descubra corriendo la suite): `test_aduana_api.py:440-449, :515,
  :596` (el cruce "modelo de embeddings" a huggingface.co desaparece), `test_carga_vigia.py:143-145` (el set
  de `_modelos_de_calipso()` suma el embedder), `test_abismo_memoria_recall.py` (dobles con `recall(query,
  n)`), `test_memoria_reindex.py:183-201` (el fixture con las dos colecciones), docstrings de
  `test_memoria_carta.py:69-71`, `test_abismo_memoria_recall.py:3-4`, `test_aduana_canario.py:58`,
  `test_memoria_ambito.py:15`.

## 3. Los umbrales se re-miden, no se heredan

`RECALL_MIN_SCORE = 0.30` (`server.py:3005`) y `RECALL_UMBRAL = 0.20` (`abismo/fuentes.py:21`) estan
calibrados sobre MiniLM (score = 1 - distancia coseno). `bge-m3` tiene otra distribucion (similitudes mas
altas y mas apretadas) y embebe otro texto. Regla h05: no tocar la letra sin re-medir. **Banco de recall**
(`experimentos/recall_banco.py`, seco salvo Ollama y, para la condicion MiniLM, el venv con torch: corre
ANTES de desinstalarlo). Lo que hay hoy no mide nada (ruling 8.6): los 16 episodios del fixture son 8
preguntas por 2 pasadas (duplicados) y las 4 consultas existentes son la pregunta literal del documento, asi
que `hit@4` da ~100% con cualquier embedder. El banco se arma asi: por cada uno de los 8 topicos del fixture,
la pregunta literal mas dos parafrasis escritas a mano (una sobre la pregunta, otra sobre el CONTENIDO de la
respuesta) y 6-8 consultas negativas (temas ausentes); los duplicados cuentan como UN acierto (hit@1 por
topico); las 5 filas reales del home entran con consultas escritas a partir de su contenido (es local: no
sale nada). Se mide para MiniLM y para `bge-m3` en sus tres variantes de texto embebido: `hit@1`, `hit@4`, la
distribucion de scores y el **margen** `min(score aciertos) - max(score negativas)`. Los umbrales nuevos se
eligen por el margen (con los aciertos de MiniLM como piso), se anotan en el modulo con los numeros y se
marcan PROVISORIOS (N chico; se re-miden cuando el corpus crezca), con `CALIPSO_RECALL_MIN_SCORE` y
`CALIPSO_RECALL_UMBRAL` como vuelta atras por env. Regla de parada: si `bge-m3` no iguala el `hit@1` por
topico de MiniLM o su margen es negativo, se para y se le dice a Pedro (no se aterriza a ciegas).

## 4. Invariantes

1. **El server no importa torch** ni ningun runtime de ML: los modelos viven en Ollama.
2. **La memoria es fail-open:** sin Ollama, el turno sale sin recuerdos y lo dice en telemetria; nunca tumba
   el websocket ni el arranque.
3. **Nada se pierde:** la coleccion vieja no se borra; el reindex es idempotente y por ids; `sin_reindexar`
   se ve hasta que sea 0.
4. **Los umbrales se re-miden con el banco** antes de aterrizar; los vectores viejos y nuevos no se mezclan
   (colecciones distintas).
5. **Un solo camino a Ollama:** el embedder usa `carga.payload_local` y `carga.usando()`, y su modelo esta
   en la lista de modelos de Calipso (memoria efectiva, vigia).
6. **Ningun test llama a Ollama ni a huggingface.co.**

## 5. Verificacion

- Unitarios de `memoria_embed.py` con `urlopen` doblado: la request (modelo, input, truncate, keep_alive y
  num_thread por nivel), la respuesta (lista de vectores, dims), timeout y error -> excepcion propia;
  `name/get_config/build_from_config` y el registro en chroma (una coleccion en un tmp que se reabre sin
  pasar EF y reconstruye `calipso_ollama` sin torch).
- `Memory` con `EmbedFalsa`: `episodic-<tag>` como nombre, `recall` con una sola embedding y ambos ambitos,
  fail-open (embedder que revienta -> `[]` + fila), `remember` intacto (ids, procedencia).
- `memoria_reindex --embeddings` sobre una copia del fixture: 16 copiados, ids iguales, metadatos iguales,
  idempotente, `--vista` sin embeber, `sin_reindexar` 16 -> 0.
- El server: `GET /api/memory` con `sin_reindexar`; el turno con Ollama caido (harness) contesta sin
  recuerdos, con la fila `recall_fallo` y `done`; `_modelos_de_calipso()` incluye el embedder; el AST del
  repo sin `torch`/`transformers`/`sentence_transformers`; la aduana ya no declara embeddings al arranque.
- El banco de recall con los dos embedders y los umbrales nuevos anotados.
- El smoke en vivo (server desechable sobre el fixture con las dos colecciones, Ollama real): recall real por
  bge-m3, `done` antes del remember (medir el tiempo entre el ultimo chunk y `done`), Ollama caido a mitad
  (recall_fallo + turno entero), reindex sobre una copia, el vigia descargando bge-m3 (por `/api/embed`), y la
  **convivencia con el 7b bajo `justa`** (ruling 8.4): con el 7b cargado, un turno completo (recall, generacion,
  remember) midiendo `/api/ps` en cada paso: si Ollama desaloja al 7b para cargar bge-m3, se para y se le dice
  a Pedro con los numeros (candidatas: saltar el recall bajo justa con el 7b cargado, con fila; cola de
  remember diferido que el tick drena en holgada).
- Despliegue (controlador): merge; `pip uninstall` con la lista explicita (~5 GB: sentence-transformers, torch,
  transformers, triton, nvidia-*, cuda-bindings, cuda-toolkit, cuda-pathfinder, sympy, mpmath, networkx, scipy,
  scikit-learn, joblib, threadpoolctl, safetensors; se QUEDAN onnxruntime, tokenizers, huggingface_hub,
  ctranslate2, faster-whisper); chequeo post-uninstall (`import chromadb, ollama, faster_whisper,
  calipso.server` con home temporal); vuelta atras documentada (`pip install sentence-transformers` con el
  indice CPU de torch, ~200 MB, y la coleccion vieja intacta); reindex del home real con el server apagado;
  reinicio; `VmRSS` del server real antes y despues (esperado: de 1571 MB a ~200); un turno de humo NO (el
  server real no recibe turnos del agente).

## 6. Lo que NO hace

- No cambia chroma ni la forma de los episodios ni la procedencia.
- No pre-calienta el embedder al arrancar (el primer recall tras inactividad paga ~2 s de carga fria; se
  anota y se mide; pre-calentar bajo holgada es YAGNI hasta que moleste).
- No toca el juez de privacidad ni el abismo mas alla del recall.
- No borra la coleccion vieja (otra tanda, cuando `sin_reindexar` sea 0 en todos los homes).

## 7. Corte

Una rama `feat/memoria-ollama`, 4 tasks: (1) `memoria_embed.py` (EF, `EmbedFalsa`, `texto_para_embedding`,
`_post_embed`) + `Memory(embed=)` y `CALIPSO_EMBED_FALSA` + colecciones por tag + recall fail-open, de una
sola embedding y con guardia + `remember` con embeddings explicitos + tests; (2) `memoria_reindex
--embeddings` (sin `--forzar`, lotes por tamano, doble lista de ids) + `--vista/--aplicar` sobre la viva +
`sin_reindexar`, `recall_ok` y `ultimo_recall_fallo` en `/api/memory` y el arranque + el `done` antes del
remember + tests sobre una copia del fixture; (3) el banco de recall con los dos embedders y las tres
variantes, los umbrales provisorios con env, la carga (nombre normalizado, `keep_alive_embed`, `ollama_evict`
para embedding, `_modelos_de_calipso`), la aduana (`_declarar_arranque`, EXCEPCIONES), el guardia
`sys.modules`/AST anti-torch, docs + tests; (4) el fixture con las dos colecciones (generado UNA vez con
`--embeddings`, commiteado, README con la receta, test de ids iguales), el smoke en vivo con Ollama (incluida
la convivencia con el 7b bajo `justa`) y el cierre.

## 8. Rulings de la revision adversaria (2026-09-12; todos revertibles)

1. **Nombre y tag son dos cosas:** `EMBED_MODEL = "bge-m3:latest"` (lo que devuelve `/api/ps`); tag de
   coleccion `bge-m3`. La carga y el vigia comparan normalizando `:latest`. Sin esto la memoria efectiva
   no ve 1,2 GB y el vigia nunca descarga el embedder.
2. **La EF es pura al construirse** (sin red ni disco): chroma la reconstruye al crear y dos veces por
   `upsert`; con Ollama caido el arranque seguiria siendo fail-open. Dims fijo por config.
3. **El `remember` va despues del `done`** como tarea de fondo: con bge-m3 costaria 0,4-4 s visibles.
4. **`keep_alive` propio del embedder** (`holgada` 5m; `justa`/`cargada` 0): la tabla del 7b esta calibrada
   para pasadas de un turno que comparten runner; un modelo que se usa al principio y al final del turno con
   30 s garantiza dos cargas frias, y bajo `justa` no debe convivir con el 7b. La convivencia se MIDE en el
   smoke y, si Ollama desaloja al 7b, se para y se decide con Pedro.
5. **Se embebe pregunta + 150 palabras de respuesta**, no el par entero (que queda dominado por respuestas
   de 2-6k chars y cuesta 2-5 s); el documento guardado no cambia. El banco mide las tres variantes.
6. **El banco de recall mide separacion, no `hit@4` literal:** parafrasis y negativas por topico, duplicados
   como un acierto, margen como criterio, umbrales provisorios con vuelta atras por env, regla de parada por
   `hit@1` y margen.
7. **Timeouts y lotes por uso:** recall 10 s; remember y reindex 120 s por lote; lotes por tamano (<= 8k
   chars) y un documento largo solo. El techo efectivo de contexto de bge-m3 en Ollama es 4096 tokens (no
   8192): con 150 palabras no importa.
8. **Fail-open visible:** `recall_ok`/`ultimo_recall_fallo` en `/api/memory`, motivo `memoria_no_disponible`
   en el abismo. Una marca en las UIs es YAGNI hasta que haga falta.
9. **`--embeddings` sin `--forzar`** (server apagado siempre) y con doble lista de ids; `--vista/--aplicar`
   sobre la viva; departamentos fuera (no existen).
10. **`CALIPSO_EMBED_FALSA` en `conftest.py`** antes de importar: `Memory(embed=)` solo no alcanza porque
    los tests importan `calipso.server` a nivel de modulo.
11. **`EMBED_MODEL` vive en `calipso/config.py`**, no en `memory.py`: `carga` lo lee sin importar chromadb.
12. **Fixture con las dos colecciones**, generado una vez y commiteado; la condicion "antes" del porton de la
    memoria (main con MiniLM) muere con el uninstall: se anota.
13. **La lista de desinstalacion es explicita** (~5 GB) y `calipso.sh`/`LINUX_MIGRATION.md` nunca instalaron
    torch (lo instalo una mano): no hay nada que sacar de ahi; AGENTS.md se corrige.
14. **Ni el lector ni el compositor ni el juez tocan la memoria vectorial** (verificado por las lentes): el
    cambio es de `memory.py`, el reindex, el recall del turno y el abismo.
15. **Solo `Memory.recall` atrapa** (decision 3 del plan): `Scope.recall(query, n, embedding=None)` no
    atrapa nada y ningun llamador del server lo usa directo (verificado: `server.py:3201` y
    `abismo/fuentes.py:120` van por `Memory`). El fail-open vive en la fachada, que es la unica puerta.


## 9. Addendum del cierre (2026-09-12): rulings tomados al construir, para Pedro

Todo esta en el codigo de `feat/memoria-ollama`, en el ledger (`docs/superpowers/2026-09-12-cierre-memoria-ollama/`)
y medido en el smoke (`docs/superpowers/2026-09-12-smoke-memoria.md`, tres corridas; la 3 con el codigo
final). Numerados para vetar por numero; todos revertibles.

16. **El embedder queda residente solo con memoria DISPONIBLE de sobra.** Con la memoria efectiva (ruling
    13 de la carga) el 7b residente no vuelve `cargada` la maquina, y el embedder se quedaba 5 min al lado
    del 7b: el smoke midio 327 MB de swap libre y `psi_mem_full10` 5,19. Ahora `keep_alive_embed` lee
    `MemAvailable` FRESCO (no la ultima medicion, que puede ser de antes de cargar el 7b) y mira si el
    modelo del chat esta listado: con menos de `EMBED_RESIDENTE_MB` (2500) disponibles o con el 7b
    residente, `keep_alive 0` (embebe y suelta, ~2 s por uso); si no, la tabla por nivel (`holgada` 5m).
    Corrida 3: con el 7b residente y 2010 MB disponibles, bge-m3 no se quedo y el turno completo tardo
    16-18 s con el remember de fondo en 2,3 s. Costo si esta mal: 2 s mas por recall mientras el 7b esta
    cargado.
17. **El banco mide contra temas ausentes; el ruido de siempre es otro episodio del mismo corpus.** En el
    top-4 de las 29 consultas positivas hay 63 hits de otro topico: con 0,476 pasan 22/63 (con MiniLM a
    0,30 pasaban 45/63); en el abismo 32/63 (0,44) contra 60/63 (0,20). Es una mejora real (mismos
    aciertos, la mitad de recuerdos fuera de tema en el prompt) pero el umbral queda a 0,02 del ruido y a
    0,078 del peor acierto: no es un corte limpio. La metrica quedo en el banco (`--informe`) y los
    umbrales siguen PROVISORIOS con `CALIPSO_RECALL_MIN_SCORE` / `CALIPSO_RECALL_UMBRAL`; se re-miden
    cuando el corpus real crezca.
18. **El remember de fondo tiene tope** (dos en vuelo, `REMEMBER_EN_VUELO_MAX`) y el server espera hasta
    10 s las tareas pendientes al apagarse (fila `remember_pendiente` si vencio).
19. **`--embeddings` es legible y no escribe vectores falsos:** con Ollama caido o el modelo sin bajar dice
    el motivo y `ollama pull bge-m3` (codigo 3, la vieja intacta); con `CALIPSO_EMBED_FALSA=1` heredado
    del shell se niega (codigo 2) salvo `--falsa` explicito; anuncia el embedder; los conteos distinguen
    "ya estaban", "metadatos actualizados" y "sin documento".
20. **El orden del despliegue es: merge, reindex del home real (server apagado), reinicio, verificar
    `GET /api/memory`, y recien entonces `pip uninstall`.** La vuelta atras: `pip install torch
    --index-url https://download.pytorch.org/whl/cpu && pip install sentence-transformers` (~200 MB) mas
    checkout de main; la coleccion vieja no se borra; `~/.cache/huggingface` no se borra. Vuelta RAPIDA
    sin pip ni checkout: `CALIPSO_EMBED_URL=http://127.0.0.1:1` en el entorno del server deja la memoria
    en fail-open (turno entero sin recuerdos, `recall_fallo` inmediato).
21. **El fixture es sintetico** (los personajes de los smokes: Mariana, el libro rosa, el presupuesto del
    taller); las consultas de los episodios reales de Pedro entran por `--reales` fuera del repo y el JSONL
    commiteado no lleva su texto. Codex lo leyo como datos personales: no lo son.
22. **Lo que el smoke midio con el codigo final (corrida 3):** recall frio 2,0 s y caliente 0,19 s;
    `done` 111 ms tras el ultimo chunk y el episodio guardado 0,6 s despues; con el embedder caido el turno
    entero sale (18,9 s), `recall_fallo` y `remember_fallo` con el motivo, `recall_ok` false y vuelve a true
    solo; reindex idempotente 1,1 s y desde cero 10 s para 16 documentos; evict por `/api/embed`; y la
    convivencia del ruling 16. Lo que NO ejercito: `cargada` por PSI con el embedder, un turno con abismo
    (varias pasadas) bajo carga, y el `pip uninstall` (es del despliegue).
