# Smoke de la carga (2026-09-11, noche)

Spec: `docs/superpowers/specs/2026-09-11-carga-design.md` (seccion 6, ultimo punto). Plan:
`docs/superpowers/plans/2026-09-11-carga.md` (Task 6). Rama `feat/carga` @ `d3ba84e` (el script) mas el
commit de este informe (la fila de `CALIBRACION` y los dos arreglos del script).
Script: `experimentos/carga_smoke.py` (`nice -n 19 .venv/bin/python -m experimentos.carga_smoke` desde la
raiz del repo). Server desechable: `uvicorn calipso.server:app` en 127.0.0.1:8778, `CALIPSO_HOME` temporal
restaurado desde `experimentos/fixtures/memoria_smoke_home/` (copia; el fixture no se toca), token
aleatorio, `CALIPSO_NO_TOTP=1`. Ollama REAL en 11434 con `qwen2.5:7b`. La CLI `claude` de suscripcion
estaba disponible (el turno B lo contesto Socrates por haiku). Sin Chromium: las marcas de las dos UIs las
cubren los 13 tests de node de la Task 5 (3+5+3+2); el smoke verifico que `carga.js` sirve y que `index.html` lo importa.

Tres corridas, todas del controlador del plan (no de un implementador), con el server REAL de Pedro
(8000) APAGADO durante cada una y relanzado al terminar (login 200, `/api/ps` vacio, ningun turno enviado).
`~/.calipso` no se toco. Logs y telemetrias de cada corrida en
`.superpowers/sdd/2026-09-11-carga/smoke-corrida{1,2,3}.log` y `smoke-telemetria-{wj5k3pbr,xtxofgn9,oypgpdtz}.jsonl`
(el directorio esta en `.gitignore`: son copias de los homes desechables `/tmp/carga-smoke-<id>`).
**La corrida 3 (22:45-22:51) es la que vale: 0 fallos.** Las dos anteriores fallaron en 3 pasos cada una,
y en las tres el producto hizo lo que dice el spec: los fallos eran de las suposiciones del smoke.

## Por que tres corridas (y que fallo en cada una)

**El bloqueo previo.** El implementador de la Task 6 dejo el script escrito y probado en seco y devolvio
BLOCKED (`.superpowers/sdd/2026-09-11-carga/task-6-report.md`): con el server real arriba (1,57 GB de RSS)
la Ally en reposo daba 5920-5998 MB = `justa`, y como el server desechable pesa otros ~1,5 GB (`calipso.server`
construye la `Memory` al importar y `memory.py:163` levanta el `SentenceTransformer`), el smoke con su
server arriba mediria ~4450 MB = `cargada` antes de cargar ningun modelo. Bajo `cargada` el `keep_alive` es 0,
el 7b no queda cargado tras `/local`, y A, N y V no son medibles. Ruling del controlador: apagar el server real
(sin conexiones desde las 15:31) y correr el smoke el mismo; los agentes no tocan el server real.

**Corrida 1 (22:27-22:34, home `wj5k3pbr`, EXIT=1, 3 fallos).** Paso 0: `holgada` 7174 MB; con el server
desechable arriba: `justa` 5945.
- FALLO `V el vigia descargo el 7b (fila descarga)`: sin fila en 90 s. El 7b que cargo A dejo la maquina en
  `cargada` (1840-2150 MB), asi que N (`/nube /local`) corrio bajo `cargada` con su propio `keep_alive: 0`
  (spec 2, sin excepcion por "ya cargado", ruling 9.1) y el 7b se fue solo al terminar N. El tick siguiente
  del vigia no encontro nada que descargar: no hay fila `descarga` porque no hubo descarga que hacer. Era el
  smoke el que esperaba que el vigia descargara algo que el producto ya habia descargado por su cuenta.
  El paso `V /api/ps vacio` dio ok (por eso mismo).
- FALLO `P la rutina se pospuso` y `P last_run sigue None` (`last_run` 22:32:59): el reservador apartaba un
  `bytearray` de ceros tocando un byte por pagina. Hipotesis (los logs no la aislan): una reserva de ceros es
  compresible y al cargar el 7b en C pudo irse a zram (el swap subio 1 GB, 4047 -> 5059 MB); lo demostrado
  es que `MemAvailable` volvio a quedar por encima de 5746, la maquina dejo de estar `cargada` y la rutina
  corrio en el tick. La corrida 2, ya con bytes aleatorios, mostro la otra mitad de la causa (lo frio de
  OTROS procesos se comprime): de ahi los dos arreglos.
- El resto (1, A, N, M, R, B, C, L, D): ok, con numeros parecidos a los de la corrida 3 (M 2702 / R 5506
  contra 2709 / 5555).

**Arreglo 1 (del controlador, en `experimentos/carga_smoke.py`):** el reservador aparta `os.urandom(PASO)`
(bytes aleatorios no se comprimen: mandarlos a zram no libera nada y el kernel no gana con eso); y en V, si
`/api/ps` esta vacio, se recarga el 7b desde afuera con `keep_alive: "5m"` (lo que dejaria un turno bajo
`holgada`) para que sea el VIGIA quien lo descargue. Tras la corrida 3, `1c2685b` cambio el reservador a
`readinto` desde /dev/urandom (sin copia transitoria); probado en seco, no corrido en vivo.

**Corrida 2 (22:37-22:44, home `xtxofgn9`, EXIT=1, 3 fallos).** Paso 0: `holgada` 8314 MB; con el server
desechable arriba: `holgada` 7165.
- FALLO `V` otra vez, sin fila en 90 s: Ollama tarda unos segundos en soltar el runner tras un `keep_alive: 0`,
  el `ps()` unico de la recarga todavia listaba al 7b, no se recargo, y el 7b se fue solo igual que en la
  corrida 1 (el tick de las 22:38:18 lo vio en uso durante N: `descarga_diferida`, `en_uso: 1`; el siguiente
  ya no tenia nada).
- FALLO `P` otra vez (`last_run` 22:42:21): la reserva ya era incompresible, pero cargar el 7b en C mando
  ~1,2 GB de paginas frias de OTROS procesos a zram (swap 4150 -> 5367 MB durante C) y, al descargarse el 7b,
  quedo mas memoria libre que antes de C: `justa` en vez de `cargada`, y la rutina corrio.
- El resto ok. Durante C el vigia midio el pico de PSI de las tres corridas: `some avg10` 16,04 con 1166 MB
  libres y 451 MB de zram libre (22:41:21, `descarga_diferida`, `en_uso: 1`): no descargo, como manda el
  invariante 6.

**Arreglo 2 (del controlador):** en V se espera `/api/ps` vacio hasta 30 s antes de recargar; antes de P el
reservador vuelve a apartar hasta `cargada` (una escena mas en la calibracion: "reservador tras C, para P");
y el `finally` descarga el 7b que deja D (bajo `holgada` sale con `keep_alive: 5m` y nadie lo usa).

**Corrida 3 (22:45-22:51, home `oypgpdtz`, EXIT=0, 0 fallos).** La que se detalla abajo.

## La maquina

Todas las escenas son de la corrida 3, con el server REAL apagado y el desechable arriba (salvo el paso 0).
`mem` es MemAvailable en MiB; los PSI son `avg10` en %; la necesidad del 7b es 5746 (4466 + 1280).

| cuando | escena | mem | psi_mem some/full | psi_cpu | load1/16 | swap usado | nivel |
|---|---|---|---|---|---|---|---|
| antes de 22:45:40 | paso 0 (`--esperar`), sin el desechable | 8364 | 0,0/0,0 | 0,0 | 2,11 | 4156 | holgada (a los 0 s) |
| 22:45:40 | con el server desechable arriba (-1185 MB) | 7179 | 0,0/0,0 | 0,0 | 2,02 | 4156 | holgada |
| 22:47:15 | M: con el 7b cargado por A (`num_ctx` 8192) | 2709 | 0,28/0,28 | 0,0 | 6,46 | 4194 | cargada |
| 22:47:24 | V: el 7b recien recargado (`keep_alive` 5m) | 2469 | 1,39/1,39 | 0,0 | 5,70 | 4191 | cargada |
| 22:47:52 | **R: reservador sin modelo, 1536 MB** | **5555** | 0,11/0,11 | 0,0 | 4,14 | 4191 | **cargada** |
| 22:49:08 | P: reservador otra vez tras C, 2048 MB | 5513 | 0,03/0,03 | 0,0 | 5,94 | 4887 | cargada |
| ~22:50 | L: tras liberar | 7082 | 0,0/0,0 | 0,0 | 3,66 | 4883 | holgada |

Las cinco filas del bloque `=== calibracion ===` del log (22:45:40 a 22:49:08) son las que se anotaron en
`carga.CALIBRACION`, con el `medido_en` de cada una como `cuando`; `test_carga.py` las recorre todas (ya no
queda ninguna fila sin numeros) y una asercion fija que la fila "cargada de verdad" es la del paso R. **La
fila "cargada de verdad": 22:47:52, 5555 MB libres contra 5746, PSI 0,11, load1 4,14, swap 4191, sin modelo
cargado, con 1536 MB de bytes aleatorios apartados.** Cae en `cargada` por memoria y por nada mas.

El reservador, paso a paso (corrida 3, R): 0 MB -> `holgada` 7177; 512 -> `justa` 6596; 1024 -> `justa` 6074;
1536 -> `cargada` 5555. Cada 512 MB apartados bajaron MemAvailable ~520-580 MB. Tras C (P): 1536 -> `justa`
6106 (no `cargada`: C mando ~700 MB frios a zram, swap 4191 -> 4887); 2048 -> `cargada` 5513.

Con el 7b cargado la maquina es `cargada` sin ayuda (2709 MB): en esta Ally cargar el 7b YA es `cargada` para
el sensor (MemAvailable no cuenta al modelo: ruling 9.1), y por eso el vigia lo descarga al tick siguiente y
todo lo que sigue necesita carga que no sea el modelo.

## Los pasos de la corrida 3

27 filas en el resumen: 23 aserciones y 4 notas (las notas no cuentan como pasos); 0 fallos; EXIT=0.
Los tiempos de A y C son los ms del propio smoke (entre el envio y `done`: 38650 y 60311; en la telemetria
`latency_ms` da 38612 y 60205); los de N, B y D son `latency_ms` de la fila `chat_turn`.

| paso | resultado | detalle |
|---|---|---|
| 1 medicion con el server desechable arriba | nota | `holgada mem=7179` (8364 sin el desechable) |
| 1 carga.js sirve | ok | `GET /static/fabrica/carga.js` con `textosDeCarga` |
| 1 index importa carga.js | ok | `/static/fabrica/carga.js` en `GET /` |
| A `/local` bajo holgada, sin senal de carga | ok | 38650 ms (carga del 7b desde disco incluida), texto "Hola Pedro.", sin evento `carga`, sin `error` |
| A el 7b cargado con context_length 8192 | ok | `/api/ps`: `qwen2.5:7b`, 8192, `expires_at` 22:51:19 = 5 min despues (keep_alive "5m" de holgada) |
| N `/nube /local` no recreo el runner | ok | `/api/ps` sigue `context_length` 8192; 55967 ms; `error=None`. N corrio bajo `cargada` (1925 MB con el 7b adentro): `local_con_aviso`, keep_alive 0 |
| M medicion con el 7b cargado | nota | `cargada mem=2709 psi 0,28 load1 6,46 swap 4194` |
| M cargada | ok | idem |
| V el 7b recargado desde afuera (keep_alive 5m) | nota | tras esperar `/api/ps` vacio (N lo descargo con su keep_alive 0): `cargada mem=2469 psi 1,39` |
| V el vigia descargo el 7b (fila `descarga`) | ok | 22:47:40, 16 s despues de la recarga: `{"modelo": "qwen2.5:7b", "ok": true, "nivel": "cargada", "mem_disponible_mb": 2468}` |
| V `/api/ps` vacio tras la descarga | ok | `[]` |
| R cargada con carga real | ok | 1536 MB apartados: `cargada mem=5555 psi 0,11 load1 4,14` |
| R `GET /api/carga` coincide | ok | `{"nivel": "cargada", "mem_disponible_mb": 5555, "motivo": "mem 5555 < 5746"}`; cuentas de hoy: suscripcion 0, local_con_aviso 1, descarga 1, pospone 2, sin_3b 0, sin_vision 0 |
| B senal `carga` antes del primer chunk | ok | eventos: `carga` antes de `chunk`; aviso "maquina cargada (5555 MB libres): contesto por Socrates" |
| B por suscripcion con "contesto por" | ok | ruta `subscription`, haiku por la CLI `claude`, 10956 ms |
| B el aviso no entra en el texto | ok | texto visible "Hello again." |
| B `meta.carga` en el chat | ok | `GET /api/chats/{id}`: `{"nivel": "cargada", "mem_disponible_mb": 5555, "motivo": "mem 5555 < 5746", "ruta": "subscription", "gesto": null, "aviso": "..."}` |
| B fila `kind: carga` (`suscripcion`) | ok | 22:47:53, con el `chat` del turno |
| C `/local` avisa "es local, puede tardar o fallar" | ok | senal `{"ruta": "local", "gesto": "/local", "aviso": "maquina cargada (5497 MB libres): /local es local, puede tardar o fallar"}` |
| C keep_alive 0 desde afuera NO corto la request viva | ok | el evict a mitad del stream (tras 20 chars): 60311 ms, 479 chars, `done`, `error=None` |
| C `/api/ps` vacio tras el turno (keep_alive 0 del propio turno) | ok | `[]` en menos de 30 s |
| P cargada antes de la rutina | ok | el reservador otra vez: 2048 MB, `cargada mem=5513` |
| P la rutina se pospuso (fila `pospone`) | ok | 22:49:40, `{"rutina": "catastro", "nivel": "cargada"}` con el `rutina_id` del smoke (`rt_ee3efc10e4`; las sembradas `catastro` y `consumo` del fixture se posponen en cada tick tambien) |
| P `last_run` sigue None | ok | `null` |
| L nivel tras liberar | nota | `holgada mem=7082 psi 0/0 load1 3,66 swap 4883` |
| L la rutina pospuesta corrio al liberar | ok | `last_run` 22:50:40 (el tick siguiente a la liberacion) |
| D holgada: el turno local volvio solo, sin senal | ok | "traduce al ingles: hola": ruta `local` (Platon), sin evento `carga`, 39640 ms (recargo el 7b) |

Al final el `finally` libero la reserva, apago el server y descargo el 7b que dejo D (bajo `holgada`, keep_alive
5m); el ledger del controlador: `/api/ps` vacio antes de relanzar el server real.

## Lo que se vio y no estaba escrito (hallazgos para Pedro)

1. **Un server de Calipso pesa ~1,5 GB antes de servir nada.** El desechable: 1,48 GB de RSS
   (`VmRSS 1514748 kB`) por el solo `import calipso.server`; el real: 1,57 GB. La causa: `server.py`
   construye `Memory(project_root=...)` al importar y `memory.py` levanta el `SentenceTransformer` del modelo
   de embeddings ahi mismo. En una maquina de 11,4 GiB donde el 7b necesita 5746 MB es el 13 % de la RAM
   ocupado por un modelo que solo se usa al indexar y al buscar. Candidato a "entender la causa" (regla de
   Pedro: no poner techos): cargarlo perezoso, o en un proceso aparte, o medir que parte del RSS es el modelo
   y que parte el resto. En el smoke el delta medido al levantar el desechable fue 1149-1229 MB de MemAvailable.
2. **Con el server real arriba, la Ally en reposo mide `justa`, no `holgada`.** Antes de apagarlo: 5920-5998
   MB (22:12-22:25, el server real 1568 MB de RSS, krunner 497, dos `claude` 444 + 381, plasmashell 424, kwin
   149, playwright-mcp 232). Con el real apagado: 7174-8364 en el paso 0 (holgada). `holgada` pide 6770 (5746 +
   1024). Es el diseno del spec y el ruling 1 del plan: con la histeresis (3.4), tras una descarga del vigia el
   chat local no vuelve hasta `holgada`; con el server real corriendo y un agente trabajando, eso puede ser
   "no vuelve solo". Pero no es una constante: a las 23:01, con el server real relanzado y este agente
   corriendo, `/proc/meminfo` dio 7074 MB (holgada) con 4042 MB en zram, porque el frio que las tres corridas
   mandaron a zram sigue ahi (hallazgo 3c). La misma maquina, el mismo server: 5946 antes del smoke, 7074
   despues. El dato para el ruling de umbrales de Pedro (abajo).
3. **zram comprime lo frio y mueve MemAvailable cuando el 7b entra y sale.** Tres formas distintas de verlo:
   (a) una reserva de paginas casi vacias se comprime a nada cuando el 7b la aprieta (corrida 1, +1 GB de swap);
   (b) cargar el 7b manda ~700-1200 MB de paginas frias de OTROS procesos a zram (swap 4191 -> 4887 en la
   corrida 3, 4150 -> 5367 en la 2) y al descargarse el 7b sobra mas memoria que antes (corrida 2: `justa`
   en vez de `cargada`); (c) el reposo entre corridas subio de 7174 a 8314-8364 MB porque lo frio se quedo en
   zram (swap 2732 -> 4111-4156). El sensor mide MemAvailable, que es lo correcto (es lo que ve el OOM), pero
   el numero depende de cuanto frio ya esta comprimido: dos mediciones "en reposo" pueden diferir 1 GB.
   El swap sigue sin decidir (ruling 9.3): en las tres corridas el swap usado fue de 2732 a 5388 MB (el
   maximo, corrida 1, `descarga_diferida` 22:31:59) sin que eso dijera nada del nivel.
4. **`keep_alive: 0` desde afuera NO corta una request viva; medido 60 s.** En C el smoke mando el evict
   (`prompt: ""`, `keep_alive: 0` a `/api/generate`, lo mismo que hace el vigia) a mitad del stream: el turno
   termino con `done`, sin `error`, 479 chars, 60311 ms (corridas 1 y 2: 53762 ms / 374 chars y 60643 ms / 565
   chars). Ollama aplica el keep_alive nuevo al terminar la request en curso. El contador `en_uso` sigue
   valiendo (el vigia no encola un evict detras de un turno de un minuto: `descarga_diferida` con `en_uso: 1`
   en las tres corridas), pero el peor caso (que el vigia se le adelante al contador) no corta nada.
5. **El `num_ctx` unificado ya no recrea el runner, pero bajo `cargada` el `keep_alive: 0` de cada pasada lo
   descarga y recarga igual entre el juez y el chat.** N: `/api/ps` sigue con `context_length` 8192 despues de
   `/nube /local` (el juez corre con `num_ctx = CHAT_NUM_CTX`; antes de la Task 3 cada `/nube` recargaba el 7b
   por 4096 contra 8192). Pero la asercion solo distingue el `num_ctx`, no "runner conservado" de "runner
   recreado con el mismo `num_ctx`", y la telemetria muestra lo segundo: en las tres corridas N corrio bajo
   `cargada` (el 7b de A ya estaba en RAM), cada pasada llevo `keep_alive: 0`, y a mitad de N el 7b se
   descargo tras el juez y se recargo para el turno (corrida 3: 22:46:39, 20 s despues de arrancar N,
   `modelos_cargados: []` y 4212 MB libres contra 1925 tres segundos antes, PSI 1,51 leyendo el blob; corrida 1:
   22:28:55, `modelos: []` a mitad de N). N tardo 48-56 s contra 36-42 s de A, que incluye la carga desde
   disco. Es el costo del ruling 13 del plan (`keep_alive` 0 bajo `cargada`), pendiente de Pedro: la
   alternativa es un `keep_alive` corto no cero bajo `cargada` (p. ej. `"30s"`) para que las pasadas de un
   mismo turno compartan el runner.
6. **El paso C es el borde de la Ally.** `/local` bajo `cargada` con ~5,4 GB "libres" carga el 7b igual (el
   spec lo pide: los gestos locales no se saltan) y la maquina queda en 860-1166 MB de MemAvailable con
   430-944 MB de zram libre (corridas 1, 2 y 3; el 18:25 del terreno tenia 68 kB de zram libre cuando Ollama
   murio). El vigia lo vio (`descarga_diferida`, `en_uso: 1`) y no toco nada. El aviso "puede tardar o fallar"
   es literal; el tope duro del reservador (1500 MB) protege de la reserva, no del 7b que se carga encima.
7. **El canario de degeneracion atrapo a C.** En la corrida 3 la respuesta del 7b bajo esa presion tuvo un
   tramo en chino (senal `alfabeto`, fraccion 0,366) y el canario lo marco; en las corridas 1 y 2 no paso. No
   se puede atribuir a la memoria (qwen2.5 cambia de alfabeto solo a veces), pero es el tipo de dato que los
   canarios existen para juntar.
8. **Tiempos.** Cargar el 7b y contestar una linea: 36-42,5 s (A y D, en las tres corridas);
   `/nube /local` (juez + turno): 48-56 s; el turno por suscripcion (haiku): 9,3-34,8 s; C (cinco lineas bajo
   carga): 53,7-60,6 s. El vigia descargo a los 16 s de la recarga (el tick cae donde cae: hasta 60 s).
9. **El PSI nunca decidio.** Maximo `some avg10` 16,04 (corrida 2, C, 1166 MB libres) contra 20 de `cargada`;
   en la corrida 3 el maximo fue 1,51 (durante la carga del 7b). En todas las escenas decidio MemAvailable.
   Coincide con la fila del 18:25 del terreno ("el PSI no ve el OOM que viene").
10. **Las rutinas sembradas y el ritmo de la telemetria.** El fixture no trae `routines.json`, el server
    siembra `catastro` y `consumo` habilitadas y vencidas, y bajo `cargada` se posponen en cada tick: una fila
    `pospone` por rutina vencida por minuto (a las 22:47:52 ya habia 4 filas de dos rutinas). Las cuentas del
    dia cuentan RUTINAS distintas (`pospone: 2` en R), asi que la Aduana no infla; la telemetria si crece: bajo
    `cargada` sostenida con N rutinas vencidas son N filas por minuto en `telemetry.jsonl`.

## Lo que el smoke NO ejercito

- `justa` como nivel de un turno: el smoke la cruzo solo mientras apartaba (512 y 1024 MB). Ningun turno
  corrio bajo `justa`; ni el `keep_alive "2m"`, ni `departamento` pospuesta bajo `justa` (las demas corren),
  ni el aviso "maquina justa (...): contesto por X" del local suspendido.
- La rama "sin holgada" de la histeresis (D con `justa`: suscripcion con motivo "local suspendido hasta
  holgada"): con el server real apagado la Ally volvio a `holgada` al liberar, y el local volvio solo. Con el
  server real arriba, esa es la rama que se veria (hallazgo 2).
- `cargada` por PSI (some >= 20 o full >= 5): nunca paso (hallazgo 9).
- El fallback suscripcion -> local con aviso (la CLI estaba y contesto), el prompt privado, `/redacta`, `/otra`,
  `force_model` local, y `/local` con Ollama caido / complejidad 5 / `/think` / salud cacheada: solo por los
  tests de la Task 2.
- `sin_3b` (el planner del equipo dinamico fuera de `holgada`) y `sin_vision` (una imagen fuera de `holgada`):
  ningun turno con equipo ni con adjunto; las cuentas quedaron en 0. Solo tests (Task 3).
- `descarga_fallida` y `vigia_error`.
- Dos turnos locales a la vez (`en_uso > 1`).
- Las marcas en las UIs con un navegador (13 tests de node de la Task 5, 3+5+3+2; aca solo que `carga.js` sirve y que
  `index.html` lo importa).
- Pedro jugando de verdad: el reservador es memoria anonima incompresible sin CPU ni GPU; un juego ademas
  ocupa hilos (la CPU entra solo en `justa`: ruling 9.4) y VRAM compartida.
- La opcion `--holgada` de `--esperar` (el smoke usa el default, que abre con `justa`).
- El OOM: el tope duro del reservador esta para no llegar.

## Veredicto

El producto se comporto como el spec en las tres corridas: `/local` bajo `holgada` sin senal y con el 7b
en `keep_alive 5m`; el juez sin recrear el runner; con el 7b cargado la maquina es `cargada` y el vigia lo
descarga con fila `descarga` en el tick siguiente cuando nadie lo usa (y `descarga_diferida` cuando si); bajo
`cargada` el turno que iria local sale por suscripcion con la marca antes del primer chunk, en `meta.carga` y
fuera del texto; `/local` bajo `cargada` va local con el aviso y un `keep_alive 0` desde afuera no lo corta;
la rutina vencida se pospone sin tocar `last_run` y corre al tick siguiente de liberar; con `holgada` el
local vuelve solo. Los seis fallos de las corridas 1 y 2 fueron dos suposiciones del smoke (que el vigia
tendria algo que descargar cuando el propio turno ya lo habia descargado; que una reserva de memoria y el
nivel `cargada` sobrevivirian a que el 7b entrara y saliera con zram en el medio), corregidas en el script.
Corrida 3: 23 aserciones ok, 4 notas, 0 fallos, EXIT=0, `holgada` tras liberar.

La rama queda con la suite y node verdes y este informe escrito. El merge de `feat/carga` es del controlador
(`--no-ff`, ruling 12).

## Orden de la suite

La suite completa (`nice -n 19 .venv/bin/python -m pytest -q --ignore=test_chat_live.py -p no:cacheprovider`)
se corrio DESPUES del smoke, con el server real ya relanzado, para el commit de la fila de calibracion y de
este informe (ninguna prueba carga modelo; `test_carga.py` recorre `CALIBRACION` sin medir nada). Node
(`calipso/web/fabrica`, `node --test`) no cambio desde la Task 5 (`# pass 452 / # fail 0`).

## Pendiente de Pedro

- **Los umbrales (`carga.UMBRALES`), ruling 1 del plan.** Con `MARGEN_LIBRE_MB` 1024, `holgada` pide 6770 MB
  libres de 11638. Con el server real corriendo (1,5 GB) y un agente trabajando, la Ally en reposo da `justa`
  (5800-6500), y por la histeresis el chat local no vuelve solo tras una descarga. Con el server real apagado
  dio `holgada` (7174-8364) y todo el ciclo cerro. Opciones, todas reversibles: bajar el margen libre, bajar el
  margen del modelo (1280 esta calibrado al RSS real del OOM), o achicar el server (hallazgo 1).
- **El server que pesa 1,5 GB por el `SentenceTransformer` al importar** (hallazgo 1): entender la causa
  antes que cualquier umbral.
- **`keep_alive: 0` bajo `cargada` recarga el 7b entre las pasadas de un mismo turno** (hallazgo 5; ruling 13
  del plan): `/nube` y las reentradas del abismo pagan una carga desde disco por pasada. Alternativa: un
  `keep_alive` corto no cero bajo `cargada` (`"30s"`), o que el vigia sea el unico que descarga.
- **El merge de `feat/carga`** (del controlador, `--no-ff`, tras suite + node).
