# La carga: que Calipso ocupe cuando puede ocupar y se aligere cuando la maquina esta cargada (2026-09-11)

Spec de brainstorming con Pedro, 2026-09-11 (tarde). Pendiente de revision adversaria y de la lectura de
Pedro. Todo archivo:linea es de main `9077a8e` mas la rama `feat/canarios` (que no toca estos sitios).

## 1. De donde sale

Pedro, textual: *"que todos los procesos que corran sean mindful de los recursos y que ocupen cuando puedan
ocupar y que sean mas ligeros cuando hay mucha carga; aplica para Calipso, tambien para ti"*. El disparador:
mientras Pedro jugaba en la Ally (11,6 GB de RAM), Ollama murio por OOM a las 17:08 con el swap lleno, y a
las 17:50 el 7b seguia CARGADO en Ollama ocupando 5,4 GB con 500 MB disponibles y 95 MB de swap libre.
Calipso hoy no mira la maquina: carga el 7b al primer turno sin preguntar si hay lugar y lo mantiene 5
minutos (`keep_alive` por defecto de Ollama), las rutinas tickean cuando les toca (`_routines_ticker`,
cada 60 s, `server.py`), el arranque precalienta probes y modelo de embeddings, y los smokes y portones del
agente lanzan el 7b y Chromium sin mirar la RAM.

**Decision de Pedro (2026-09-11):** cuando la maquina esta cargada y Pedro escribe en el chat, Calipso
**avisa y va por suscripcion** ("maquina cargada: contesto por Claude"), visible en el mensaje; el local
vuelve solo cuando hay lugar. Coherente con "los modelos ven todo" y con "nunca escalar en silencio": se
ve. Las otras tres opciones (esperar, el 3b, preguntar cada vez) quedaron descartadas para esta tanda.

## 2. El sensor

`calipso/carga.py`, puro (lee `/proc`, no escribe):

- **Senales:** `MemAvailable` y swap de `/proc/meminfo`; la presion de memoria y de CPU de
  `/proc/pressure/memory` y `/proc/pressure/cpu` (PSI: `some avg10`, `full avg10`; hoy en la Ally
  jugando: memoria `some avg10=0.21`, CPU `some avg10=0.79`); el load de `/proc/loadavg`; y lo que Ollama
  tiene cargado (`GET /api/ps`: modelo, `size`, `expires_at`; loopback, gratis).
- **Cuanto necesita el modelo local:** el `size` que Ollama reporta para el modelo configurado la ultima
  vez que estuvo cargado (cacheado en memoria del proceso; si nunca se cargo, el tamano del blob del GGUF
  en `~/.ollama`, que ya se lee para el tokenizador), mas un margen fijo (`MARGEN_MB`, 1024).
- **El nivel:** `holgada` si `MemAvailable >= necesidad + margen` y `psi_mem_some10 < 5%`; `cargada` si
  `MemAvailable < necesidad` (contando el modelo ya cargado como disponible: si el 7b esta en RAM, su
  memoria no hace falta pedirla dos veces) o `psi_mem_some10 >= 20%` o `full avg10 >= 5%` o el swap libre
  cayo por debajo de `SWAP_MIN_MB` (256); `justa` en el medio. Umbrales en un solo lugar, con la
  calibracion anotada (los numeros de hoy jugando y los de la maquina en reposo).
- `carga.medir() -> Carga(nivel, mem_disponible_mb, swap_libre_mb, psi_mem_some10, psi_mem_full10,
  psi_cpu_some10, load1, modelo_cargado: bool, necesidad_mb, medido_en)`. Cuesta microsegundos: se mide en
  cada decision, no se cachea mas de 2 s.
- **Sin nombres de apps:** no detecta Steam ni nada por nombre. Mide recursos.

## 3. Las politicas

En orden de impacto, todas con telemetria (`kind: carga`, con la `Carga` y la decision):

1. **El turno de chat bajo `cargada`, ruta local decidida:** `_decide` mira la carga ANTES de elegir; si
   esta cargada y el modelo local no esta ya en RAM, la ruta pasa a suscripcion (la que `capabilities`
   rankee entre las disponibles; si no hay ninguna, se queda local y avisa que va a tardar), y el turno
   arranca con el aviso visible **al principio del mensaje**: "maquina cargada (N MB libres): contesto por
   Claude". El aviso es texto del mensaje (queda en `chats.json` como parte de lo que Pedro leyo) y
   ademas viaja como senal `{type: "carga", ...}` para que las UIs lo pinten aparte. Si el 7b YA esta
   cargado, el turno sigue local (no hace falta pedir memoria) y no avisa. **`/local` explicito no se
   salta:** avisa "maquina cargada, /local va a tardar o fallar" y sigue local (fallo cerrado, como hoy
   promete `_chunks_for`), sin caer a suscripcion (esto ademas arregla de paso el bug encontrado en el
   porton de la reentrada: con Ollama caido `/local` caia a Opus por `server.py:2450`).
2. **El 7b se descarga bajo `cargada`:** un vigia liviano (dentro del ticker, cada 60 s) mide; si esta
   cargada y hay un modelo local en RAM sin turno en curso, lo descarga (`keep_alive: 0`, como
   `resource_dispatcher.ollama_evict`) y lo anota. No se vuelve a cargar hasta que un turno local lo pida
   con la maquina no cargada. Las llamadas locales de Calipso mandan `keep_alive` corto (2 min) cuando
   la carga es `justa`, el default cuando es `holgada`.
3. **Las rutinas pesadas esperan:** `run_due` recibe la carga; `reflect`, `consumo` (lee 10 MB de JSONL),
   `cierre`, `departamento` (el jefe: 7b) y `catastro` (escanea el disco) no corren bajo `cargada`: se
   reprograman al proximo tick y lo dicen (`status: "pospuesta por carga"`). `backup` tambien. Bajo
   `justa` corren las que no usan el modelo. Nunca se saltan: se posponen.
4. **El arranque no precalienta bajo carga:** `_startup_warm` mide; si esta cargada no corre los probes ni
   `discover` (los hace al primer turno) y lo anota. El modelo de embeddings (`Memory()`) se carga igual:
   es chico y el chat no funciona sin el.
5. **Los procesos del agente (yo):** los portones y smokes que usan el 7b o Chromium empiezan por
   `carga.medir()` y esperan (con un tope y un aviso) hasta `holgada`; la suite corre con `nice -n 19`.
   Es una regla de trabajo del agente (memoria del proyecto), no codigo del producto, salvo un helper
   `python -m calipso.carga --esperar` que bloquea hasta holgada o tope.

## 4. Donde se ve

- En el mensaje: el aviso al principio, y la marca `carga` en las dos UIs (molde de las marcas de los
  canarios: `msg-foot` en la PWA, el pie del turno en `/fabrica`).
- En `/fabrica`: el nivel actual y sus numeros (en la barra de estado o en la pestana Aduana, junto al
  resumen: "lo que sale, lo que entra, lo que la maquina aguanta"), y cuantas veces hoy se fue a
  suscripcion por carga, se descargo el modelo, se pospuso una rutina.
- En telemetria: `kind: carga` por decision.

## 5. Invariantes

1. **Nunca escala en silencio:** toda ida a suscripcion por carga lleva el aviso en el mensaje y la fila.
2. **`/local` explicito jamas cae a la nube.** Ni por carga ni por Ollama caido.
3. **Nada se salta:** una rutina pospuesta corre cuando hay lugar; un turno bajo carga se contesta (por
   suscripcion) o se avisa que va a tardar.
4. **El sensor es puro y barato**, mide recursos y no nombres de programas; umbrales en un solo lugar,
   calibrados y anotados.
5. **Fail-open:** si `/proc` no se puede leer (otro sistema) o Ollama no responde al `ps`, el nivel es
   `holgada` con `medido: false`: Calipso se comporta como hoy.
6. **La descarga del modelo jamas corta un turno en curso.**

## 6. Verificacion

- Unitarios de `carga.py` con `/proc` y `/api/ps` falsos para los tres niveles y los bordes (modelo ya
  cargado cuenta como disponible; swap bajo; PSI alto con memoria libre; `/proc` ausente).
- `_decide` con carga falsa: cargada + local decidido -> suscripcion con aviso; cargada + `/local` ->
  local con aviso, sin nube; cargada + modelo ya cargado -> local sin aviso; holgada -> como hoy (byte a
  byte: el test de `_decide` existente sigue).
- El vigia: cargada + modelo cargado + sin turno -> `keep_alive: 0` una vez; con turno en curso -> no.
- `run_due` con carga falsa: pesadas pospuestas con `status`, livianas corren; en holgada todo corre.
- `_startup_warm` bajo carga: sin probes ni discover, con fila.
- Smoke en vivo con server desechable y **carga real**: un proceso que reserve memoria hasta dejar la
  maquina en `cargada` (`python -c` con un bytearray, con cuidado del OOM: reservar de a 512 MB midiendo),
  un turno de chat -> aviso + suscripcion (o fila si no hay CLI), `/local` -> aviso + local, el vigia
  descarga el 7b (verificar con `/api/ps`), una rutina pospuesta; liberar la memoria -> el siguiente turno
  local vuelve solo. El server real no se toca.

## 7. Lo que NO hace

- No espera ni encola turnos (opcion descartada). No usa el 3b. No pregunta cada vez.
- No limita procesos ajenos ni mata nada. No mira nombres de programas.
- No toca el ruteo cuando la maquina esta holgada.
- No mueve el modelo a GPU ni cambia `num_ctx`.

## 8. Corte

Una rama `feat/carga`, ~5 tasks: (1) `carga.py` + tests; (2) `_decide` y el aviso en el turno + `/local`
cerrado de verdad (con el test del bug) + senal + tests por harness; (3) el vigia del modelo y el
`keep_alive` por nivel + tests; (4) rutinas que se posponen + arranque bajo carga + tests; (5) las marcas
en las UIs, `/fabrica`, el helper `--esperar`, el smoke y el cierre. Corre despues del cierre de los
canarios.
