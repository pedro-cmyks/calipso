# La carga: que Calipso ocupe cuando puede ocupar y se aligere cuando la maquina esta cargada (2026-09-11, v2)

Spec de brainstorming con Pedro, 2026-09-11 (tarde), revisado la misma noche por tres lentes adversarias
(dos de Claude: modelo/YAGNI y factibilidad por lectura; y Codex gpt-5.5 headless). La v1 esta en el
commit `0fe7527`; la seccion 9 lista lo que cambio y por que, como rulings revertibles para Pedro. Todo
archivo:linea es de main `9077a8e` mas la rama `feat/canarios`.

## 1. De donde sale

Pedro, textual: *"que todos los procesos que corran sean mindful de los recursos y que ocupen cuando puedan
ocupar y que sean mas ligeros cuando hay mucha carga; aplica para Calipso, tambien para ti"*. El disparador:
mientras Pedro jugaba en la Ally (11,4 GiB de RAM), Ollama murio por OOM a las 17:07:59 (journal: `Killed
process llama-server anon-rss:5873568kB oom_score_adj:200`, `Free swap = 232kB`) y a las 17:50 el 7b seguia
CARGADO ocupando 5,4 GB con 500 MB disponibles. Calipso hoy no mira la maquina de forma coherente: carga el
7b al primer turno sin preguntar si hay lugar y lo mantiene 5 minutos (`keep_alive` por defecto de
Ollama), las rutinas tickean cuando les toca (`_routines_ticker`, cada 60 s, `server.py:5388`), y los
smokes y portones del agente lanzan el 7b y Chromium sin mirar la RAM. Existe un medio sensor viejo
(`calipso/resource_dispatcher.py`: `/proc/meminfo`, `/api/ps`, `gate` con umbrales propios y un
`downgrade` al 3b) que solo usa el orquestador (`orchestrator.py:84-96`), en silencio.

**Decision de Pedro (2026-09-11):** cuando la maquina esta cargada y Pedro escribe en el chat, Calipso
**avisa y va por suscripcion**, visible en el mensaje; el local vuelve solo cuando hay lugar. Coherente con
"los modelos ven todo" y con "nunca escalar en silencio". Las otras tres opciones (esperar, el 3b,
preguntar cada vez) quedaron descartadas para esta tanda.

## 2. El sensor

`calipso/carga.py`, puro (lee `/proc` y `/api/ps`, no escribe). Absorbe lo que sirve de
`resource_dispatcher.py` (`ollama_loaded_models`, `ollama_evict`) y el resto de ese modulo se retira (9.7).

- **Senales:** `MemAvailable`, `MemTotal`, `SwapTotal`, `SwapFree` de `/proc/meminfo`; la presion de
  memoria y de CPU de `/proc/pressure/memory` y `/proc/pressure/cpu` (PSI `some avg10`, `full avg10`);
  `load1` de `/proc/loadavg` y `ncpu`; y lo que Ollama tiene cargado (`GET /api/ps`: nombre, `size`,
  `expires_at`; loopback, timeout 0,5 s). Alcance **global** (la pregunta es "la Ally esta cargada", no
  "mi cgroup"); sin cgroups en esta tanda.
- **Cuanto necesita el modelo local (`necesidad_mb`):** una sola fuente: el tamano del blob del GGUF del
  modelo configurado en `~/.ollama` (ya lo resuelve `calipso/tokenizador.py:48-67`; 4,68 GB para el 7b)
  mas `MARGEN_MODELO_MB` (1280, calibrado al RSS anonimo real medido en el OOM: 5,87 GB con `-c 8192` y
  `--no-mmap`). Si el blob no se encuentra, `NECESIDAD_DEFAULT_MB` (6000). El modelo ya cargado NO cuenta
  como disponible: `MemAvailable` ya lo descuenta, y con zram "cargado" no quiere decir "residente".
- **El nivel (contra la necesidad del modelo del chat, `CONFIG["local"]["model"]`):**
  - `cargada` si `MemAvailable < necesidad` **o** `psi_mem_some10 >= 20` **o** `psi_mem_full10 >= 5`;
  - `holgada` si `MemAvailable >= necesidad + MARGEN_LIBRE_MB` (1024) **y** `psi_mem_some10 < 5` **y**
    `psi_cpu_some10 < 25` **y** `load1 < ncpu / 2`;
  - `justa` en el medio (incluida la CPU ocupada con RAM de sobra: el decode del 7b usa los 16 hilos y le
    pega a un juego aunque sobre memoria).
  - **El swap NO entra en el nivel.** En esta maquina es zram (RAM comprimida, 5,7 GiB, zstd) con
    `swappiness` 180: el kernel lo llena proactivamente con paginas frias; el 2026-09-11 a las 18:05, con
    7,4 GB disponibles, PSI 0 y nada corriendo, el swap estaba al 95% (5,2 GB de paginas frias de dos
    python, plasma y steam comprimidas en 1,2 GB reales). Se mide y se anota en la fila; no decide.
- **Umbrales en un solo lugar** (`carga.UMBRALES`), con la calibracion anotada en el modulo: los numeros
  del OOM (17:07, MemAvailable ~500 MB, swap 232 kB), los de "jugando con el juego quieto" (17:55:
  MemAvailable 6897 MB, PSI mem/cpu avg10 0,00, load1 4,65/16, swap usado 5150 MB, `/api/ps` vacio) y los
  de reposo (18:05: 7377 MB, PSI 0). Los de "jugando de verdad" los anota el smoke (seccion 6).
- `carga.medir(modelo=None) -> Carga(nivel, mem_disponible_mb, mem_total_mb, swap_usado_mb,
  swap_libre_mb, psi_mem_some10, psi_mem_full10, psi_cpu_some10, load1, ncpu, modelos_cargados:
  list[str], necesidad_mb, medido: dict[str, bool], medido_en)`. Cuesta microsegundos mas el `ps`; se
  mide por decision (en el hilo de `_decide`, en el `to_thread` del ticker), nunca en el event loop, y
  no se cachea mas de 2 s. **Fail-open por senal:** si `/proc/pressure` no existe, esas senales se
  toman como 0 y `medido["psi"] = False`; si el `ps` no responde, `modelos_cargados = []` y
  `medido["ollama"] = False`; el nivel se calcula con lo que si se midio. Si NADA se pudo medir,
  `holgada` con `medido` todo en falso: Calipso se comporta como hoy.
- **Por nivel, dos perillas para las llamadas locales:** `carga.keep_alive(nivel)` (`holgada`: el
  default de Ollama, 5 min; `justa`: `"2m"`; `cargada`: `0`) y `carga.num_thread(nivel)` (`holgada`:
  ninguno, Ollama decide; `justa`/`cargada`: `ncpu // 2`). Van en el payload de Ollama (`keep_alive` es
  campo de primer nivel; `num_thread` va en `options`).
- **Sin nombres de apps:** no detecta Steam ni nada por nombre. Mide recursos.
- **Limite conocido (9.3):** un juego pausado con sus paginas en zram no se ve como demanda pendiente. Si
  vuelve mientras el 7b esta cargado, el OOM mata al 7b (`oom_score_adj` 200) y el turno local termina en
  `error` con lo parcial guardado, como hoy. El juego sobrevive.

## 3. Las politicas

En orden de impacto, todas con telemetria (`kind: carga`, con la `Carga` y la decision):

1. **El turno de chat bajo `cargada` va por suscripcion, con aviso.** `_decide` (`server.py:2421`) mide
   la carga en su hilo y, si esta `cargada` y no hay un gesto local por construccion, apaga los backends
   con `route == "local"` en `avail` ANTES de `capabilities.choose` (el mismo gesto que la sesion en
   `server.py:2442-2444`); `choose` rankea entre lo que queda y el turno sale por la suscripcion mejor
   rankeada. **La API paga jamas entra por carga** (el filtro de `server.py:2455-2456` sigue). El veredicto
   lleva `carga: {nivel, mem_disponible_mb, motivo}` y el `why` lo dice (el modelo lo ve por
   `_harness_context`, `server.py:2767`). Sin excepciones por "el 7b ya esta cargado" (9.1).
   - **Los gestos locales por construccion no se saltan** (invariante 2 amplio): `/local`
     (`force_route`), `force_model` que nombre un modelo local, el prompt privado (`dispatch.PRIVATE`,
     `features.private`: `capabilities.score_model` descarta todo backend no `private_ok` y el ranking
     queda vacio), `/redacta` y `/otra` (siempre `_chunks_for("local")`, `server.py:3665-3703`), el fallo
     cerrado del juez de `/nube` (`nube_local`), y "no hay ninguna suscripcion disponible". Todos van
     local con el aviso `puede tardar o fallar`, sin caer a la nube, y con `keep_alive`/`num_thread` del
     nivel. Si Ollama muere a mitad del turno: `error` al ws y lo parcial guardado, como hoy
     (`server.py:4331-4333`).
   - **`/local` cerrado de verdad:** hoy `server.py:2450` (`ranked = [... force_route] or ranked`) cae al
     ranking ENTERO cuando local no esta en el ranking, y eso pasa con Ollama caido, con complejidad 4-5
     (`max_complexity` 3 del 7b, `capabilities.py:52`), con `/think`/`/ultra` (`EFFORT_MIN_TIER`,
     `capabilities.py:35`) y con la sonda de salud lenta (`_http_up` 1,5 s cacheada 20 s,
     `server.py:2386-2401`). El arreglo: con `force_route == "local"`, `_decide` construye el veredicto
     local directamente (el molde de la rama `else`, `server.py:2481-2488`) sin pasar por ese filtro;
     `_chunks_for` sigue siendo quien para con Ollama caido (`server.py:3112-3120`). Tests para los cuatro
     caminos.
   - **El fallback suscripcion -> local** (`server.py:4284-4290`, cuando claude y codex fallan) bajo
     `cargada` lleva el mismo aviso `puede tardar o fallar`.
   - **Privacidad del reroute (9.10):** no se agrega un detector nuevo sobre el prompt principal: hoy un
     prompt de complejidad 4 sale a suscripcion sin detector, y el pase por carga solo mueve los que
     habrian ido local por capacidad; lo privado por regex cae al veredicto local. Se anota como limite.
2. **El aviso es una marca, no texto de la respuesta (9.2).** Viaja como senal ws `{type: "carga",
   nivel, mem_disponible_mb, motivo, ruta}` ANTES del primer chunk, y se persiste en `meta.carga` del
   mensaje del assistant en `chats.json` (molde de `meta.canarios`, `server.py:4460-4466`). NO se
   concatena a `full`: `full` alimenta el historial que vuelve al modelo (`_history_messages`,
   `server.py:3054`), la memoria episodica (`Calipso respondio: {full}`, `server.py:4453`) y los canarios
   (`_veredicto_del_turno(respuesta=full)`, `server.py:4346`), y "N MB libres" es un hecho duro sin
   anclaje (`canarios.py:231-234`). Los textos, en un solo lugar (`carga.AVISOS`):
   `maquina cargada (N MB libres): contesto por <persona de la suscripcion>` y
   `maquina cargada (N MB libres): <gesto> es local, puede tardar o fallar`.
3. **El 7b se descarga bajo `cargada`, sin cortar nada.** Un vigia dentro del ticker (cada 60 s, en el
   `to_thread`) mide; si esta `cargada` y `/api/ps` de ESA medicion lista un modelo de Calipso
   (`CONFIG["local"]["model"]`, `CONFIG["classifier"]["model"]`, el de vision) y `carga.en_uso() == 0`,
   lo descarga con `ollama_evict` (`keep_alive: 0` a `/api/generate`, timeout 10 s) y anota
   `accion: descarga`. Jamas evicta un nombre que no vio cargado (un `prompt: ""` a un modelo no cargado
   lo CARGA). **Contador de uso:** `carga.en_uso` es un entero con lock en el modulo; `carga.usando()` es
   un context manager que lo incrementa; el turno local entero (de `_decide` a `done`, incluidas las
   pasadas del abismo, `server.py:4110-4210`) y cada uso suelto del modelo local (juez, clasificador,
   jefe, agentes, vision) corren adentro. Ollama por si mismo no corta una request viva con
   `keep_alive: 0` (se verifica en el smoke), pero el contador evita que el evict se encole detras de un
   turno y venza su timeout.
4. **Histeresis (9.6):** despues de una descarga por carga o de un turno mandado a suscripcion por carga,
   `carga.local_suspendido = True`; con ese flag, el chat vuelve a local solo cuando una medicion da
   `holgada` (no `justa`), y ahi el flag se apaga. `/local` explicito rompe la suspension (con el aviso).
   Evita el ping-pong: descargar 5,4 GB sube `MemAvailable` justo por encima de la necesidad y el turno
   siguiente recargaria.
5. **Un solo `avail` por turno.** El mismo `avail` filtrado por carga llega a `choose` y a
   `orchestrator.build_team`/`pick_model` (`server.py:3933-3946`, `orchestrator.py:84-96`, que hoy toma
   su propio snapshot con `resource_dispatcher.gate` y descarta locales en silencio: se retira, 9.7). El
   planner del equipo dinamico (`_plan_dynamic_team`, `server.py:2551`, POST al 3b) solo corre bajo
   `holgada`; en `justa` y `cargada` usa `_heuristic_plan` (`server.py:2519`). Vision por Ollama
   (`attachments.py:297-317`, un SEGUNDO modelo en RAM) solo bajo `holgada`; si no, `aviso_imagen`
   (`server.py:3904`). `/nube` bajo carga: el juez (7b, `juez_llm.py:53-68`) corre local igual (la
   privacidad manda) y el aviso lo dice; el juez unifica `num_ctx` con `CHAT_NUM_CTX` (hoy 4096 contra
   8192: Ollama recrea el runner al cambiar `num_ctx`, o sea `/nube` recargaba el 7b; se verifica en el
   smoke).
6. **Un solo helper para hablar con Ollama:** `carga.payload_local(payload, nivel)` agrega `keep_alive`
   y `options.num_thread` del nivel, y los seis sitios lo usan: el chat (`server.py:3121-3123`), los
   agentes locales del equipo (`:2585-2591`), el clasificador (`:2555-2558`), el jefe (`_pensar_local`,
   `:7438`), el juez (`juez_llm.py:59-66`) y la vision (`attachments.py:307-312`). En Ollama gana el
   `keep_alive` de la ULTIMA request: por eso los seis tienen que coincidir. Un test recorre los seis.
7. **Las rutinas pesadas esperan, sin saltarse.** `run_due(now, handlers, nivel=None)`
   (`routines.py:281`): bajo `cargada` toda rutina vencida se pospone; bajo `justa` solo `departamento`
   (la unica que carga el modelo local: el jefe via `_pensar_local`; `reflect` corre `claude -p`,
   `consumo` lee JSONL, `catastro` escanea el disco, `backup` escribe). Una pospuesta **NO pasa por
   `mark_run`** (`routines.py:265-278` escribe `last_run`, y `next_due_at` vence desde ahi: pasarla por
   `mark_run` la empujaria un intervalo entero, 24 h para las diarias); sigue vencida al tick siguiente.
   Se anota en `ran` con `status: "pospuesta por carga"` (el ticker lo imprime) y en telemetria
   (`accion: pospone`). Nunca se saltan: se posponen.
8. **El arranque no cambia.** `_startup_warm` (`server.py:8356`) no carga ningun modelo local:
   `discover` son dos GET y los probes son subprocesos CLI de pocos segundos. Se saca la politica de la v1
   (9.8). El vigia arranca con el ticker, como todo.
9. **Los procesos del agente (yo):** los portones y smokes que usan el 7b o Chromium empiezan por
   `python -m calipso.carga --esperar` (bloquea hasta `holgada`, midiendo cada 15 s; con `--tope`
   segundos, default 600; **al vencer sale con codigo 3 y no corre nada**), y la suite corre con
   `nice -n 19`. Sin flag, `python -m calipso.carga` imprime la medicion. Es una regla de trabajo del
   agente (memoria del proyecto y REGLAS de los workflows), no codigo del producto salvo el helper.

## 4. Donde se ve

- **En el mensaje:** la marca `carga` como cabecera de la burbuja en las dos UIs (molde de las marcas de
  los canarios: `msg-foot` en la PWA, el pie del turno en `/fabrica`; en vivo por la senal, al cargar
  desde `meta.carga`). Sin colores de alarma.
- **En `/fabrica`, pestana Aduana:** una linea "la maquina" con la medicion actual (nivel y sus numeros,
  de `GET /api/carga`) y las cuentas del dia derivadas de telemetria: turnos a suscripcion por carga,
  descargas del modelo, rutinas pospuestas. Sin barra de estado, sin contadores en proceso.
- **En telemetria:** `kind: carga` por decision, con `accion` en {`suscripcion`, `local_con_aviso`,
  `descarga`, `pospone`, `sin_3b`, `sin_vision`}.
- **`GET /api/carga`** reemplaza a `GET /api/resources` (`server.py:5231-5236`, sin uso en las UIs).

## 5. Invariantes

1. **Nunca escala en silencio:** toda ida a suscripcion por carga lleva la marca en el mensaje y la fila.
2. **Ningun gesto o deteccion que hoy fija local cae a la nube por carga:** `/local`, `force_model`
   local, prompt privado, `/redacta`, `/otra`, fallo cerrado del juez, sin suscripcion. Ni por carga ni
   por Ollama caido. La API paga jamas entra por carga.
3. **Nada se salta:** una rutina pospuesta corre cuando hay lugar; un turno bajo carga se contesta (por
   suscripcion) o se avisa que va a tardar.
4. **Un solo sensor, puro y barato**, que mide recursos y no nombres de programas; umbrales en un solo
   lugar, calibrados y anotados; `resource_dispatcher.gate` y sus umbrales desaparecen.
5. **Fail-open por senal:** lo que no se puede medir no decide; si nada se puede medir, Calipso se
   comporta como hoy.
6. **La descarga del modelo jamas corta un turno en curso** (contador `en_uso`).
7. **El aviso no contamina:** `full`, la memoria episodica y los canarios reciben solo la respuesta del
   modelo; el aviso vive en `meta.carga` y en la senal.

## 6. Verificacion

- Unitarios de `carga.py` con `/proc` y `/api/ps` falsos: los tres niveles y los bordes (swap lleno con
  memoria libre -> no decide; PSI alto con memoria libre -> cargada; CPU alta con RAM libre -> justa;
  `/proc/pressure` ausente -> medido["psi"] False y el resto decide; `ps` caido -> sin modelos, el resto
  decide; nada medible -> holgada con medido todo False); `keep_alive`/`num_thread` por nivel;
  `payload_local`; `usando()` con hilos; `local_suspendido` se apaga solo en `holgada`; `--esperar` que
  vence sale con 3.
- `_decide` con carga falsa (hook `server._medir_carga`, fixture `holgada` para los tests existentes):
  cargada + local decidido -> suscripcion con `verdict["carga"]`; cargada + `/local` -> local con aviso,
  sin nube; cargada + privado -> local con aviso; cargada + sin suscripcion -> local con aviso; cargada +
  `force_model` local -> local; `local_suspendido` + justa -> suscripcion, + holgada -> local y flag
  apagado; holgada -> byte a byte como hoy. `/local` con Ollama caido, con complejidad 5, con `/think` y
  con salud cacheada en False -> veredicto local las cuatro veces.
- El turno por el harness de ws: la senal `carga` antes del primer chunk; `meta.carga` en `chats.json`;
  `full`, el episodio de memoria y `respuesta` del canario sin el aviso (test que falla si el aviso entra
  en `full`).
- El helper en los seis sitios: un test que recorre los seis payloads y verifica `keep_alive` de primer
  nivel y `options.num_thread` por nivel; el juez con `num_ctx == CHAT_NUM_CTX`.
- El vigia: cargada + modelo listado + `en_uso == 0` -> un `ollama_evict` de ese nombre; con `en_uso > 0`
  -> ninguno; modelo NO listado -> ninguno (jamas carga para descargar).
- `run_due` con nivel: cargada -> todas pospuestas con `status` y `last_run` intacto y siguen `is_due`
  al tick siguiente; justa -> solo `departamento`; holgada -> como hoy (test_routines.py sigue).
- El orquestador: cargada/justa -> `_heuristic_plan` sin POST al 3b; `pick_model` sin snapshot propio;
  test_resource_dispatcher.py reemplazado por test_carga.py.
- Smoke en vivo con server desechable y **carga real**: un proceso que reserve memoria hasta dejar la
  maquina en `cargada` (`python -c` con un bytearray, reservando de a 512 MB midiendo, con cuidado del
  OOM), un turno de chat -> marca + suscripcion (o local con aviso si no hay CLI), `/local` -> aviso +
  local, el vigia descarga el 7b (verificar con `/api/ps` que `keep_alive: 0` no corto una request viva),
  una rutina pospuesta y corrida al liberar; liberar la memoria -> `holgada` -> el siguiente turno local
  vuelve solo (histeresis). Registrar PSI y MemAvailable en el momento de `cargada`: esos son los numeros
  de calibracion "cargada de verdad" que se anotan en `carga.py`. El server real no se toca. El smoke
  mismo empieza por `--esperar`.

## 7. Lo que NO hace

- No espera ni encola turnos (opcion descartada). No usa el 3b como reemplazo del 7b. No pregunta cada vez.
- No limita procesos ajenos ni mata nada. No mira nombres de programas. No mira cgroups.
- No toca el ruteo cuando la maquina esta holgada (byte a byte).
- No mueve el modelo a GPU ni cambia `num_ctx` del chat (unifica el del juez con el del chat).
- No agrega un detector de credenciales al prompt principal (9.10).
- No arregla la sonda de salud lenta que hoy manda el chat normal a suscripcion en silencio cuando
  `/api/tags` tarda mas de 1,5 s con Ollama vivo (`server.py:2005-2010`, `:2386-2401`); queda anotada
  como deuda: bajo `cargada` el aviso sale igual por el sensor.

## 8. Corte

Una rama `feat/carga`, 6 tasks: (1) `carga.py` (sensor, niveles, perillas, `usando()`, histeresis,
`ollama_loaded_models`/`ollama_evict` traidos de `resource_dispatcher`, `__main__` con `--esperar`) +
tests; (2) `_decide`: carga sobre `avail`, `/local` cerrado de verdad, gestos locales con aviso,
histeresis, `verdict["carga"]`, la senal y `meta.carga` en el turno, `full` limpio + tests por harness;
(3) el helper en los seis sitios, el juez con `CHAT_NUM_CTX`, el orquestador sin 3b ni snapshot bajo
carga, vision solo en holgada, retiro de `resource_dispatcher` sobrante y de `/api/resources` + tests;
(4) el vigia en el ticker y `run_due(nivel)` + tests; (5) la marca en las dos UIs, `GET /api/carga`, la
linea en Aduana + tests node; (6) el smoke con carga real, la calibracion anotada, la regla en las REGLAS
de los workflows y el cierre. Corre despues del cierre de los canarios.

## 9. Rulings de la revision adversaria (2026-09-11 noche; todos revertibles)

1. **Fuera la excepcion "el 7b ya cargado sigue local sin aviso"** (v1, politica 1). Contradecia la
   decision de Pedro en el escenario exacto que motivo el spec (17:50: 7b cargado con 500 MB libres era
   `cargada` por el propio sensor, y el chat habria ido local y callado) y chocaba con el vigia, que
   descargaba ese mismo modelo al minuto. Con zram y `--no-mmap`, "cargado" no es "residente". Costo si
   esta mal: un turno mas por suscripcion cuando el 7b estaba justo cargado.
2. **El aviso es marca, no texto.** Pedro pidio que se vea: se ve, como cabecera de la burbuja, y queda
   en `chats.json` (`meta.carga`). Como texto contaminaba el historial (el system de suscripcion dice
   "no digas que backend sos" y el mensaje anterior diria "contesto por Claude"), la memoria episodica y
   el canario de anclaje ("N MB" es un hecho duro sin fuente). Costo: si Pedro lo queria como prosa, es
   un cambio de UI.
3. **El swap sale del nivel.** Es zram con `swappiness` 180: lleno es estado normal. Lo detectado en el
   incidente lo daba `MemAvailable` contra la necesidad. Una lente propuso restar el swap usado de
   `MemAvailable` (para ver un juego pausado): hoy con nada corriendo daria `cargada` durante horas
   (5,2 GB de paginas frias de todo). Se anota el limite (2, ultimo punto). Costo: un juego pausado en
   swap que vuelve mata al 7b, no al juego.
4. **La CPU entra en `justa`** (`psi_cpu_some10 >= 25` o `load1 >= ncpu/2`) y `num_thread = ncpu // 2`
   bajo `justa`/`cargada`: es la mitad de "mas ligeros bajo carga" que la v1 no cubria. No hay `cargada`
   por CPU: un juego en 16 cores no produce presion de CPU (17:55: PSI cpu 0, load1 4,65).
5. **Una sola fuente para la necesidad:** blob del GGUF + 1280 MB (el `size` de `/api/ps` solo existe
   cuando ya se cargo, que es cuando no hace falta; el RSS real medido fue 5,87 GB, 1,2 GB sobre el blob).
6. **Histeresis** tras una descarga o un pase por carga: local vuelve solo en `holgada`. Sin esto la
   descarga sube `MemAvailable` justo por encima de la necesidad y el turno siguiente recarga (Codex).
7. **`carga.py` absorbe `resource_dispatcher.py`:** quedan `ollama_loaded_models` y `ollama_evict`; se
   borran `gate`, `_smaller_model` (el `downgrade` al 3b que Pedro descarto seguia vivo por el camino del
   orquestador), `TaskQueue`, `evict_all_and_retry`, `MODEL_RAM_MB`, `resource_aware_pick_model`,
   `diagnose` y `GET /api/resources` (sin uso). Dos sensores con dos juegos de umbrales violaban el
   invariante 4.
8. **Se borra la politica del arranque** (v1, 4): no cargaba ningun modelo; saltear `discover` no
   ahorraba nada. YAGNI. Tambien la barra de estado y los contadores en proceso: telemetria alcanza.
9. **Rutinas pospuestas sin `mark_run`** y regla simple: `cargada` pospone todas, `justa` solo
   `departamento`.
10. **Sin detector nuevo para el prompt principal.** Codex pidio una compuerta "afuera por carga" con
    detector de credenciales fail-closed. Hoy el ruteo por capacidad manda prompts a suscripcion sin
    detector, y el pase por carga solo mueve los que habrian ido local por capacidad (trivial, c<=3); lo
    privado por regex se queda local. Agregar el detector solo en ese camino seria incoherente; agregarlo
    a todo el chat es otra tanda (afecta a /nube y al abismo, con banco). Para Pedro.
11. **`en_uso` cubre el turno local entero,** no solo la request: entre pasadas del abismo el modelo no
    se descarga.
12. **Vigia solo evicta lo que vio cargado en la misma medicion** y solo modelos de Calipso.
