# La memoria embebe por Ollama: el server sin torch (2026-09-12)

Spec de brainstorming con Pedro, 2026-09-12 (madrugada). Pendiente de revision adversaria. Todo
archivo:linea es de main `6780bec`.

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
  `carga.payload_local(payload, carga.nivel_reciente())` (`keep_alive` y `num_thread` por nivel: el mismo
  helper que los otros seis sitios) y dentro de `carga.usando()` (uso suelto: el vigia no descarga a mitad
  de un embed). Timeout 60 s. Batch nativo: una request por lista.
- **`EMBED_MODEL`** pasa a ser el nombre en Ollama (`CALIPSO_EMBED_MODEL`, default `bge-m3`), y
  `EMBED_DIMS` (1024) se lee del `/api/show` una vez o se fija por config. El modelo se suma a
  `_modelos_de_calipso()` (`server.py`) y a `carga._modelos_configurados()`: su `size` cuenta en la memoria
  efectiva y el vigia puede descargarlo bajo `cargada`.
- **Las colecciones llevan el embedder en el nombre:** `Scope` abre `episodic-<EMBED_TAG>` (tag = nombre del
  modelo saneado, `bge-m3`) en el mismo `chroma.sqlite3`. La coleccion vieja `episodic` (EF
  `sentence_transformer` persistida, 384 dims) queda intacta hasta que el reindex la copie: chroma prohibe
  cambiar la clase de EF de una coleccion existente y las dimensiones no coinciden (medido).
- **El reindex a otro embedder** es un modo nuevo de `calipso/memoria_reindex.py`: `--embeddings` lee
  `episodic` con `embedding_function=None` (`get` no reconstruye la EF: sin torch), y hace `upsert` de
  documentos y metadatos con los MISMOS ids en `episodic-<tag>` embebiendo por Ollama en lotes de 16;
  idempotente (los ids que ya estan se saltan salvo `--forzar`); con el server apagado (o `--forzar`, como
  hoy); `--vista` cuenta sin embeber. Cubre global, proyectos y departamentos (hoy `ambitos` deja los
  departamentos afuera: se suman). Al terminar imprime cuantos copio y cuantos quedan; NO borra la vieja.
- **El server con memoria sin migrar:** `GET /api/memory` devuelve `sin_reindexar: N` por ambito (docs en
  `episodic` que no estan en `episodic-<tag>`), el arranque lo imprime una vez, y la fila
  `kind: memoria, accion: sin_reindexar` va a telemetria. No se niega a arrancar: fail-open.
- **`recall` fail-open de verdad:** `Scope.recall` y `Memory.recall` atrapan cualquier excepcion (Ollama
  caido, timeout, coleccion rota) y devuelven `[]` con una fila `kind: memoria, accion: recall_fallo,
  error`. Hoy el recall del turno corre fuera del `try` del turno (`server.py:4195` contra `:4244`) y una
  excepcion tumba el websocket: bug preexistente que este cambio arregla de paso. `remember` ya es
  fail-open en el server (`:4784-4790`) y en la fuente del abismo (`:8535-8537`).
- **Una sola embedding por turno:** `Memory.recall` embebe la pregunta una vez y consulta ambos ambitos con
  `query_embeddings` (hoy embebe una vez por ambito: `memory.py:212-213`). Resultados identicos, mitad de
  costo.
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
- **Tests:** `Memory(embed=...)` acepta una EF inyectada; `conftest.py` provee `EmbedFalsa` (hash
  determinista a 1024 dims, sin red) para todo test que construya `Memory` real (`test_plantel_memoria.py`,
  `test_memoria_*`); ningun test llama a Ollama. `test_memory.py` (script manual) queda para correr a mano
  con Ollama.

## 3. Los umbrales se re-miden, no se heredan

`RECALL_MIN_SCORE = 0.30` (`server.py:3005`) y `RECALL_UMBRAL = 0.20` (`abismo/fuentes.py:21`) estan
calibrados sobre MiniLM (score = 1 - distancia coseno). `bge-m3` tiene otra distribucion (similitudes mas
altas y mas apretadas) y embebe otro texto (el par entero, no 128 tokens). Regla h05: no tocar la letra sin
re-medir. **Banco de recall** (`experimentos/recall_banco.py`, seco salvo Ollama): sobre el fixture
`experimentos/fixtures/memoria_smoke_home` (16 episodios) y las 5 filas reales del home, 20-30 consultas con
el episodio esperado (las del porton de la memoria y las del smoke de los canarios sirven de base), mide
`hit@1`, `hit@4` y la distribucion de scores de aciertos y de no-aciertos, para MiniLM (con el venv de hoy,
ANTES de desinstalar torch) y para `bge-m3`. Los umbrales nuevos se eligen para que los aciertos de MiniLM
sigan pasando y los no-aciertos sigan quedando afuera; se anotan en el modulo con los numeros. Si `bge-m3`
no iguala el `hit@4` de MiniLM en el banco, se para y se le dice a Pedro (no se aterriza a ciegas).

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
- Despliegue (controlador): merge, `pip uninstall` de torch/nvidia-*/transformers/sentence-transformers (anotar
  cuanto disco libera), reindex del home real con el server apagado, reinicio, `VmRSS` del server real antes
  y despues (esperado: de 1571 MB a ~200), un turno de humo NO (el server real no recibe turnos del agente).

## 6. Lo que NO hace

- No cambia chroma ni la forma de los episodios ni la procedencia.
- No pre-calienta el embedder al arrancar (el primer recall tras inactividad paga ~2 s de carga fria; se
  anota y se mide; pre-calentar bajo holgada es YAGNI hasta que moleste).
- No toca el juez de privacidad ni el abismo mas alla del recall.
- No borra la coleccion vieja (otra tanda, cuando `sin_reindexar` sea 0 en todos los homes).

## 7. Corte

Una rama `feat/memoria-ollama`, 4 tasks: (1) `memoria_embed.py` + `Memory(embed=)` + `EmbedFalsa` +
colecciones por tag + recall fail-open y de una sola embedding + tests; (2) `memoria_reindex --embeddings`
+ `sin_reindexar` en `/api/memory` y el arranque + tests sobre el fixture; (3) el banco de recall con los dos
embedders y los umbrales nuevos (corre ANTES de sacar torch del venv), la aduana y la carga (modelo en las
listas, `_declarar_arranque`), el guardia AST anti-torch, `calipso.sh` y docs + tests; (4) el fixture
regenerado, el smoke en vivo con Ollama (server desechable: recall real, Ollama caido, reindex) y el cierre.
