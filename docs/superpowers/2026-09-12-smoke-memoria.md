# Smoke de la memoria por Ollama (2026-09-12)

Rama `feat/memoria-ollama` @ `2623443` (el fixture con las dos colecciones) mas el commit de este informe
(el script y el informe), `experimentos/memoria_smoke.py` (`CALIPSO_HOME=$(mktemp -d) nice -n 19
.venv/bin/python experimentos/memoria_smoke.py` desde la raiz del repo), server desechable `uvicorn
calipso.server:app` en 127.0.0.1:8779 sobre un `CALIPSO_HOME` temporal restaurado del fixture con las dos
colecciones (`experimentos/fixtures/memoria_smoke_home`, copia; el fixture no se toca), token aleatorio,
`CALIPSO_NO_TOTP=1`. Ollama 0.30.10 con `bge-m3:latest` (1219 MB en `/api/ps`) y `qwen2.5:7b` (5203 MB).
El embedder del server desechable va por el proxy TCP 127.0.0.1:11435 -> 11434 (`CALIPSO_EMBED_URL`):
cortar el proxy es "Ollama caido" para el embedder sin tocar el Ollama real; el sensor de carga y el 7b van
directo. El server real (8000, `~/.calipso`) siguio arriba y no recibio nada.

Dos corridas del implementador de la Task 4, las dos con `SMOKE=0` (19 pasos, 0 fallos). **La corrida 2
(13:42-13:45, home `invj68cz`) es la que vale**: en la corrida 1 (13:31-13:35, home `idbq9jff`) el corte del
proxy dejaba pasar la PRIMERA conexion (abajo), asi que el recall del turno C llego a Ollama y el paso C se
sostuvo solo por las consultas del abismo; el arreglo (`shutdown` antes de `close` en `Proxy.cortar`) esta
en el script commiteado. La corrida 1 sirve igual: midio la maquina en `justa` (la 2 en `holgada`), y los dos
niveles cuentan cosas distintas. Salidas, `server.log`, telemetrias y `resultados.json` de las dos en
`.superpowers/sdd/2026-09-12-memoria-ollama/smoke-memoria-*` (directorio ignorado por git). Tras cada corrida:
server desechable apagado, proxy cerrado, el 7b y bge-m3 descargados con `keep_alive 0`, `/api/ps`
`{"models":[]}`. OJO: en las dos corridas esa descarga la hizo el implementador A MANO (el `finally` del
script solo apagaba el server y cortaba el proxy); desde la ola de fix del cierre (punto 4) el script la
hace solo: `descargar_modelos` evicta bge-m3 por `/api/embed` y el 7b, directo a 11434, espera `/api/ps`
vacio hasta 30 s y deja la linea `[nota] Z descarga de los dos modelos`.

Umbrales vigentes (Task 3, provisorios): `RECALL_MIN_SCORE = 0.476` (el turno) y `RECALL_UMBRAL = 0.44` (la
consulta del abismo).

## Por que dos corridas

**Corrida 1.** `Proxy.cortar()` cerraba el listener con `close()` mientras otro hilo estaba bloqueado en
`accept()`. En Linux ese `close()` no despierta el `accept()`: el socket de escucha sigue vivo hasta que el
accept devuelve, y la primera conexion que llega despues del "corte" PASA (sondeado en puro: intento 1 tras
cortar `PASO`, intentos 2 y 3 `ConnectionRefusedError`). En la telemetria de la corrida 1 se ve: el turno C
tiene TRES filas `recall_fallo` (13:33:51, :53, :54), pareadas una a una con las tres consultas del abismo, y
ninguna al arrancar el turno (13:33:37): el recall de `_build_context` entro por la conexion zombi y trajo
recuerdos; los que se rechazaron fueron las consultas del abismo y el remember. El `[ok]` del paso C era
verdadero por la letra (`bool(fallos_recall)`) y falso por el espiritu ("el turno entero con recall_fallo").
Arreglo: `l.shutdown(socket.SHUT_RDWR)` antes de `l.close()` (saca al accept con EINVAL; sondeado: tras
cortar, rechazado desde la primera; reanudar/cortar/reanudar en ciclo, ok).

**Corrida 2.** Con el corte real: CUATRO filas `recall_fallo` en C (13:43:23, la del recall del turno, un
segundo despues de arrancar; y 13:43:31, :33, :34, las tres consultas del abismo con
`motivo: memoria_no_disponible`), la `retirada sin_corte` y el `remember_fallo` (13:43:38). Es la corrida
de la tabla.

## La maquina

- Corrida 1: `--esperar` abrio en el primer tick con `justa` 6164 MB (necesidad 5746 + 1024), swap usada 3442
  MB de 5818. Paso 0 (el sensor del smoke, sin cache): `justa` (mem 6216 < 5746+1024), efectiva 6216,
  `/api/ps []`. Con el server desechable arriba (sin torch: no levanta ningun modelo al importar) el nivel no
  cambio; en el smoke de la carga (2026-09-11) el server desechable pesaba 1,5 GB y bajaba la maquina a
  `cargada` antes de cargar nada.
- Corrida 2: `--esperar` abrio con `holgada` 7782 MB (swap usada 5300 MB: lo que se fue a swap en la corrida
  1 no volvio, y por eso habia MAS RAM disponible). Paso 0: `holgada`, 7786 MB, `/api/ps []`.
- La unica fila `kind: carga` de las dos corridas es la del paso C de la corrida 1 (13:33:37): `cargada` por
  `psi_mem_full10 5.19 >= 5`, mem_disponible 984 MB, efectiva 7349 (los dos modelos propios cargados, 6365 MB),
  swap usada 5491 MB y LIBRE 327 MB, load1 5.23, `/api/ps ['bge-m3:latest', 'qwen2.5:7b']` -> el turno salio
  igual por el gesto (`local_con_aviso`). En la corrida 2 ningun turno dejo fila de carga (nunca `cargada`).
- Paso J (el sensor del smoke): corrida 1 `holgada` con mem_disponible 2540 y efectiva 7743; corrida 2
  `holgada` con 2114 y efectiva 7317. La memoria efectiva (ruling 13 del addendum de la carga) suma los ~6365
  MB de los dos modelos propios cargados, y por eso `keep_alive_embed` fue `"5m"` en J en las dos.

## Los pasos (corrida 2; entre parentesis la corrida 1 cuando difiere)

| paso | resultado | numeros |
|---|---|---|
| A /api/memory | ok | `global_episodes 16, project_episodes 0, sin_reindexar {"global": 0, "project": 0}, recall_ok true, ultimo_recall_fallo null` |
| R1 recall real frio | ok | 1.76 s (carga fria de bge-m3 incluida; igual en la 1); top-4 sobre "hola, que libro te conte que empece?": 0.784 y 0.672 (las dos pasadas del episodio del libro), 0.498 y 0.497 (las dos pasadas de "retoma lo que dejamos sobre mariana, la charla de agosto") |
| R1 recall caliente | ok | 0.18 s con `keep_alive "5m"` (corrida 1, bajo `justa` con `keep_alive 0`: 1.76 s, otra carga fria); top-1 0.815 el episodio "quien me presto el libro rosa"; `/api/ps` `['bge-m3:latest']` |
| R2 turno con recall | ok | 45226 ms (carga fria del 7b desde disco + respuesta de 299 chars), ruta `local/qwen2.5:7b`, sin `recall_fallo` (corrida 1: 61061 ms, 358 chars) |
| D done antes del remember | ok | 111 ms entre el ultimo chunk y `done` (corrida 1: 209 ms); `global_episodes` 16 -> 17 en 0.42 s tras el `done` (corrida 1, bajo `justa`: 4.41 s, con la carga fria de bge-m3 adentro); `/api/ps` tras el turno `['bge-m3:latest', 'qwen2.5:7b']` |
| C Ollama caido | ok (x4) | proxy cortado: turno de 15645 ms con respuesta (135 chars), CUATRO `recall_fallo` (`POST http://127.0.0.1:11435/api/embed: <urlopen error [Errno 111] Connection refused>`: el del turno + tres consultas del abismo con `memoria_no_disponible`, `retirada sin_corte`), `remember_fallo` con el mismo error; `/api/memory` con `recall_ok false` y `ultimo_recall_fallo {ts 13:43:34, error ...}`; proxy reanudado: el turno siguiente (16048 ms) deja `recall_ok true` y guarda su episodio (18) |
| X reindex | ok (x2) | idempotente sobre la copia del fixture: 0.8 s (`0 copiados, 16 ya estaban, sin_reindexar 0`); desde cero (la viva borrada EN LA COPIA): 6.3 s para 16 documentos, `16 copiados`, ids iguales a la vieja, `sin_reindexar 0` (corrida 1: 1.0 s y 6.2 s) |
| V evict por /api/embed | ok | bge-m3 calentado con `keep_alive 5m` y visto en `/api/ps` (residente True); nivel `holgada` (`keep_alive_embed "5m"`); `carga.ollama_evict("bge-m3:latest", embedding=True)` True; `/api/ps` despues `['qwen2.5:7b']` (bge-m3 fuera en < 20 s) |
| J convivencia | ok (sin PARADA) | nivel `holgada` (2114 disponibles, efectiva 7317, `keep_alive_embed "5m"`); turno 1: antes `['qwen2.5:7b']`, tras done los dos, tras remember los dos, 17557 ms; turno 2: los dos antes, tras done y tras remember, 14831 ms, remember 0.42 s. Ollama NO desalojo al 7b ni a bge-m3 en ningun paso (tampoco en la corrida 1: 16960 / 14412 ms, remember 0.42 s) |

## Lo que se vio y no estaba escrito

- **`keep_alive` del embedder por nivel, medido en las dos puntas.** Bajo `justa` (corrida 1) el embedder va con
  `keep_alive 0` y bge-m3 se descarga tras CADA request: los dos recalls de R1 tardaron lo mismo (1.76 s) y el
  remember de D 4.41 s (carga fria mas el embedding de 358 chars mas el upsert). Bajo `holgada` (corrida 2)
  el recall caliente tardo 0.18 s y el remember 0.42 s. La carga fria cuesta ~1.6-2 s por uso, dos veces
  por turno (recall y remember). Sondeado aparte: con `keep_alive 0` el modelo queda en `/api/ps` con
  `expires_at` = ahora durante ~0.5 s y desaparece; por eso las notas de R1 y D de la corrida 1 lo muestran
  cargado.
- **La memoria efectiva convierte el `justa` de la letra del ruling 8.4 en `holgada` apenas el 7b esta
  cargado.** El ruling quiere que bajo `justa` bge-m3 no conviva con el 7b (keep_alive 0). Pero con el 7b
  cargado el sensor suma sus 5203 MB como propios: en la corrida 1, 2540 disponibles + 6365 de modelos = 7743
  efectivos = `holgada`, y el embedder pasa a `"5m"`. Resultado en J (las dos corridas): los dos modelos
  residentes juntos durante todo el turno y despues. La condicion "justa con el 7b cargado" del ruling casi
  no puede darse con el sensor de hoy: o no hay 7b (justa por memoria) o esta cargado y la efectiva dice
  holgada.
- **La convivencia no fue por desalojo sino por swap.** Ollama no desalojo a nadie (no hubo PARADA por la
  regla del spec), pero en la corrida 1 los dos modelos juntos (6365 MB) sobre 6216 MB disponibles llevaron la
  maquina a swap: la usada paso de 3442 MB al arrancar a 5491 MB en el paso C (327 MB de swap LIBRE), con
  `psi_mem_full10 5.19` y `cargada` para el sensor del server, que aviso y siguio por el gesto `/local`. Lo
  que se fue a swap no volvio (5300-5433 MB usados desde entonces; 385-440 libres): la corrida 2 arranco con
  mas RAM (7786 MB) justamente porque el resto del escritorio y el server real con torch (1,5 GB de RSS)
  quedaron paginados, y en ella los dos modelos convivieron con 2114 MB disponibles y sin `cargada`. Tras el
  `pip uninstall` y el reinicio del server real (del controlador) la cuenta cambia en ~1,3 GB a favor.
- **`done` sale 111-209 ms despues del ultimo chunk**, no < 50 ms como esperaba el brief. El remember no esta
  en ese tramo (se programa con `_en_fondo` antes del send y corre en un hilo; con `keep_alive 5m` el
  episodio 17 aparecio 0.42 s despues del done): son los pasos del cierre del turno (chats.json de 35 KB,
  canarios, telemetria, meta). No se investigo mas; queda medido.
- **El fail-open se vio entero.** Con el proxy cortado, el turno de C hizo su recall (fila, 1 s despues de
  arrancar), el 7b contesto igual, el abismo consulto la memoria tres veces (`consultas 1, 2, 3`, cada una
  con `recall_fallo` y `motivo: memoria_no_disponible`, 8-10 ms cada una) y se retiro `sin_corte`, y el
  remember de fondo dejo su `remember_fallo`: cinco POSTs rechazados en un turno, ninguno tumbo nada.
  `ultimo_recall_fallo` en `/api/memory` es el ULTIMO (13:43:34, el de la tercera consulta). El turno
  siguiente, con el proxy de vuelta, recupero `recall_ok` y guardo su episodio sin reiniciar nada.
- **El recall trae lo que hay, y lo que hay son las confabulaciones del fixture.** El top-1 de R2 (0.784) fue
  la respuesta que el 7b dio a la misma pregunta en el smoke del 2026-09-10 (contaminada a proposito), y el 7b
  de hoy la retomo en las dos corridas ("un libro de ciencia ficcion ... una trilogia"); la verdad sembrada en
  `chats.json` ("El nombre de la rosa") no esta en la coleccion. Es el h06 conocido (la memoria le devuelve
  al modelo sus propias respuestas), no un problema del embedder: bge-m3 ordeno bien (las dos pasadas del
  episodio del libro arriba, 0.784 y 0.672; las de mariana en 0.498; el resto abajo).
- **Tiempos del reindex con bge-m3 real:** 16 documentos desde cero en 6.2-6.3 s (incluida la carga fria; ~0.3
  s por documento con la variante pregunta+150); idempotente 0.8-1.0 s (solo `update` de metadatos, sin
  embeber). El home real tiene 5 episodios vivos: < 5 s.
- **`--embeddings` desde la CLI embebe con `keep_alive "5m"`:** el proceso del reindex no mide la carga
  (`nivel_reciente()` = "holgada"), asi que bge-m3 quedo residente 5 min tras regenerar el fixture; se descargo a
  mano. Para el reindex del home real (del controlador): al terminar, un POST a `/api/embed` con `keep_alive
  0` (o `carga.ollama_evict(..., embedding=True)`).
- Los umbrales nuevos separaron en vivo: en R1 los aciertos (0.784, 0.815) quedaron bien arriba de 0.476 y
  las pasadas de mariana (0.497-0.498) apenas lo cruzan; en R2 el recall entrego contexto (la respuesta
  "retomo" el libro) sin `recall_fallo`.

## Lo que el smoke NO ejercito

- El vigia bajo `cargada` con bge-m3 listado (cubierto por `test_carga_vigia.py` con el hook
  `_ollama_evict_embedding`; el evict real se probo desde afuera en V). El server midio `cargada` solo en el C
  de la corrida 1 y no hubo fila de descarga del vigia.
- La convivencia bajo un `justa` LITERAL con el 7b cargado: con la memoria efectiva ese estado no aparece
  (ver arriba); lo que se midio es `holgada`-por-efectiva con los dos residentes.
- Los departamentos (no existen), el `pip uninstall` y el reindex del home real (del controlador), el server
  real (no recibio nada), las UIs (sin Chromium), el recall por la nube (todos los turnos fueron `/local`).

## Veredicto

- **ok: 19/19 pasos, 0 fallos, sin PARADA** en la corrida que vale (y en la 1). El producto hizo lo que dice
  el spec: `/api/memory` a la vista, recall real por bge-m3 con los umbrales nuevos, `done` antes del
  remember, fail-open de verdad (turno entero con la memoria muerta, cinco POSTs rechazados, recuperacion
  sola), reindex idempotente y desde cero, evict por `/api/embed`, y Ollama no desalojo al 7b ni a bge-m3.
- **Lo que decide Pedro (ruling 6 del plan, con los numeros de arriba):** la convivencia del 7b con bge-m3
  se sostuvo por swap (327 MB de swap libres en el C de la corrida 1, `psi_mem_full10 5.19`), y la memoria
  efectiva deja al embedder en `"5m"` justo cuando el 7b esta cargado. Candidatas del spec: saltar el recall
  bajo `justa` con el 7b cargado (con fila), o la cola de remember diferido que el tick drena en `holgada`;
  una tercera que sale de esta corrida: que `keep_alive_embed` mire la memoria DISPONIBLE (no la efectiva) o
  el nivel sin contar al 7b, para que con el 7b residente bge-m3 embeba y suelte. Ninguna se toco: es un
  cambio del modelo. Tambien vale decidir "nada": el turno con los dos modelos residentes tardo 14-17 s bajo
  `holgada`-por-efectiva, y despues del uninstall la Ally tendra ~1,3 GB mas.

## Pendiente del controlador: el despliegue, en este orden

El `pip uninstall` va AL FINAL (ola de fix del cierre, punto 6): hasta que `GET /api/memory` diga que la
memoria nueva anda, torch sigue en el venv y `main` sigue siendo una vuelta atras completa.

1. Merge de `feat/memoria-ollama` (el checkout principal esta en `main`, lo sirve el server real).
2. Reindex del home real con el server apagado, desde la raiz del repo, con Ollama arriba y `bge-m3` bajado
   (`ollama pull bge-m3`): `.venv/bin/python -m calipso.memoria_reindex --vista` (mira los conteos;
   `sin_reindexar` por ambito), `env -u CALIPSO_EMBED_FALSA .venv/bin/python -m calipso.memoria_reindex
   --embeddings` (imprime `embedder: OllamaEmbed bge-m3:latest 1024 dims @ ...`; si Ollama no contesta
   devuelve 3 con el motivo y se vuelve a correr), y descargar bge-m3 al terminar (la CLI lo deja con
   `keep_alive 5m`: `carga.ollama_evict("bge-m3:latest", embedding=True)` o un POST a `/api/embed` con
   `keep_alive 0`). El home real tiene 5 episodios vivos: < 5 s.
3. Reinicio del server real.
4. Verificar `GET /api/memory`: `sin_reindexar` en 0 en todos los ambitos y, tras un turno de Pedro,
   `recall_ok` true y `ultimo_recall_fallo` null. Si no cierra, la vuelta atras RAPIDA de abajo.
5. Recien entonces `pip uninstall` con la lista del spec (seccion 5: sentence-transformers, torch,
   transformers, triton, nvidia-*, cuda-bindings, cuda-toolkit, cuda-pathfinder, sympy, mpmath, networkx,
   scipy, scikit-learn, joblib, threadpoolctl, safetensors; se QUEDAN onnxruntime, tokenizers,
   huggingface_hub, ctranslate2, faster-whisper); chequeo post-uninstall (`CALIPSO_HOME=$(mktemp -d)
   .venv/bin/python -c "import chromadb, ollama, faster_whisper, calipso.server"`); `VmRSS` del server real
   antes y despues. `~/.cache/huggingface` (533 MB, MiniLM adentro) NO se borra: es lo que hace instantanea
   la vuelta atras completa. La coleccion vieja `episodic` queda (otra tanda cuando `sin_reindexar` sea 0 en
   todos los homes).

Vueltas atras:

- **Rapida, sin checkout ni pip** (mientras se decide): `CALIPSO_EMBED_URL=http://127.0.0.1:1` en el
  entorno del server deja la memoria en fail-open: `recall_fallo` inmediato (conexion rechazada, sin
  esperar el timeout), el turno sale entero sin recuerdos, `remember_fallo` en cada turno y `/api/memory`
  con `recall_ok` false. Se quita la variable y se reinicia para volver.
- **Completa** (spec seccion 5): checkout de `main` + `pip install torch --index-url
  https://download.pytorch.org/whl/cpu && pip install sentence-transformers` (torch del indice CPU, ~200
  MB, y recien despues sentence-transformers desde PyPI: un solo `pip install sentence-transformers
  --index-url .../whl/cpu` REEMPLAZA PyPI por el indice de torch y no encuentra el paquete); la coleccion
  `episodic` sigue intacta y main la abre tal cual, con MiniLM desde `~/.cache/huggingface`; NO vale
  `CALIPSO_EMBED_MODEL` (abriria otra coleccion vacia).
- El ruling de la convivencia (arriba) quedo implementado en la ola de fix del cierre (punto 2):
  `keep_alive_embed` mira la memoria DISPONIBLE fresca (< 2500 MB -> 0) y si el 7b esta residente (-> 0);
  los numeros de J y del R1 caliente de este informe son del codigo anterior.
