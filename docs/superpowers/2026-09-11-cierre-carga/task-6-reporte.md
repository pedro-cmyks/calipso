# Task 6 -- reporte del implementador (2026-09-11, 22:00-22:30)

Rama `feat/carga` en el worktree `.claude/worktrees/carga`. base_sha `b2c7faa` -> head_sha `d3ba84e` (un commit).
Estado: **BLOCKED** para la corrida en vivo del smoke (y con ella la fila "cargada de verdad" de `CALIBRACION`
y `docs/superpowers/2026-09-11-smoke-carga.md`). Todo lo seco esta hecho, verde y commiteado.

## Que implemente

1. **`--esperar` abre con `justa` o `holgada`; `--holgada` exige `holgada`** (primer paso, ruling del
   controlador del ledger; TDD). `calipso/carga.py`: `abre = ("holgada",) if args.holgada else ("holgada",
   "justa")`, `if c.nivel in abre: return 0`; el mensaje de vencimiento dice `sin holgada ni justa` (default)
   o `sin holgada` (`--holgada`); `--tope` y el codigo 3 no cambian. Ayuda de argparse y docstring del
   modulo lo dicen (el docstring cita el ruling: por que `justa` abre, y el costo si esta mal).
2. **`experimentos/carga_smoke.py`** completo, el del brief con tres ajustes (abajo, "Desvios").
3. **La regla de recursos** en `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md`,
   seccion 7, tras "Lecciones que ya mordieron" (bloque ANTES: 1 match con `grep -nF`, linea 204).
4. NO hecho (bloqueado): la corrida en vivo, la fila `CALIBRACION[-1]` (sigue con `None`: el test la saltea)
   y `docs/superpowers/2026-09-11-smoke-carga.md`.

## Evidencia TDD

- Rojo: `test_esperar_vuelve_0_en_cuanto_no_esta_cargada` (esperaba `dormidos == [15]`: fallaba con
  `[15, 15]`), `test_esperar_con_holgada_exige_holgada` (`SystemExit: 2`, flag inexistente),
  `test_esperar_con_holgada_vence_con_3_si_solo_hay_justa`, `test_la_ayuda_y_el_docstring_dicen_lo_que_espera_cada_flag`
  -> `4 failed, 26 passed`.
- Verde tras el cambio: `test_carga.py` `30 passed`. `test_esperar_que_vence_sale_con_3_y_no_duerme_de_mas`
  (siempre cargada -> 3) sigue tal cual.
- Step 2 del brief (piezas secas): `ast.parse` ok; `antes_del_primer_chunk` las dos aserciones; el
  reservador aparto 512 MB de verdad (`MemAvailable` 5926 -> 5400 -> 5882 al soltar); `medir` leyo la
  maquina una vez (`justa mem=5882`); `python -m experimentos.carga_smoke --help` sale 0; sin procesos
  colgados despues.

## Archivos

- `calipso/carga.py` (docstring de uso, `main`: `--holgada`, `abre`, mensaje de vencimiento)
- `test_carga.py` (+3 tests netos: uno renombrado y reescrito, tres nuevos; `import contextlib`)
- `experimentos/carga_smoke.py` (nuevo)
- `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md` (seccion 7, la regla)

## Suite

Orden usado (alternativa valida del Step 6): suite completa ANTES de cualquier smoke, con el porton
`--esperar` (default nuevo) abierto en `justa` (5920 MB): `nice -n 19 ... pytest -q --ignore=test_chat_live.py
-p no:cacheprovider` -> **`1849 passed, 4 warnings in 136.51s`, EXIT=0** (Task 5 dejo 1846: +3).
`test_routines.py` -> `OK: rutinas/timers verificable`; `test_prompt_compiler.py` -> `OK`. Node desde
`calipso/web/fabrica` -> `# pass 452 / # fail 0` (no toque `calipso/web/`).

## Self-review (leyendo el diff)

- `--esperar` sin `--holgada` devuelve 0 en `justa` y `holgada`; con `--holgada` solo en `holgada`; el tope y
  el 3 intactos; `--json` y sin flag intactos. Sin acentos ni emojis en lo nuevo (grep sobre el script y el
  tramo nuevo del doc: 0).
- El smoke: paso 0 con el default (`--esperar --tope 600`, subproceso, `sys.exit(3)` si no abre, antes de
  levantar nada); `finally` libera y cierra el reservador y apaga el server aunque falle un paso; el
  reservador para en el primero de `cargada` / `MemAvailable < 1500 + 512` / 9000 MB; `esperar_fila(...,
  rutina_id=rt_id)` para no tomar la `pospone` de la catastro sembrada; el `meta` que se guarda es el
  PRIMERO del turno (`used` = ruta inicial; el fallback manda otro `meta` que no se captura: la ruta final
  la da `senales[-1]["ruta"]`, que es lo que el paso B mira).
- Lo que verifique contra el server de hoy antes de confiar en el script: `POST /api/routines` devuelve la
  rutina con `id` (`routines.add`); `GET /api/routines` -> `{"routines": [...]}`; `GET /api/chats/{id}` devuelve
  los mensajes crudos (con `meta`); `telemetry.jsonl` en el home; la fila `pospone` lleva `rutina` y
  `rutina_id`; `GET /` sirve `index.html` y este importa `/static/fabrica/carga.js` (linea 604); el ticker
  duerme 60 s; `carga.ollama_evict` manda `{"model", "prompt": "", "stream": False, "keep_alive": 0}` a
  `/api/generate` (el `evict_desde_afuera` del smoke es el mismo payload).

## Desvios y por que

1. **Paso 0 del smoke con el default de `--esperar`** (no cargada), no `holgada`: ruling del controlador,
   por encima del brief. La funcion se llama `esperar_no_cargada()` (el brief: `esperar_holgada()`); el
   docstring del script lo dice en el paso 0 y en A ("bajo no cargada"; bajo `justa` el keep_alive es
   "2m", no "5m": la asercion de A solo mira `context_length`, y el vigia lo alcanza antes de los 2 min
   porque el tick es cada 60 s).
2. **Una medicion impresa con el server desechable arriba** (`res.nota("1 medicion con el server
   desechable arriba", ...)`, y una segunda nota si ahi ya es `cargada`): el server pesa ~1,5 GB (abajo) y
   A, N y V presuponen que la maquina siga NO cargada con el server arriba. Es un print mas en la
   calibracion (escena "con el server desechable arriba"), no cambia ninguna asercion ni el orden de los
   pasos.
3. **La regla de recursos escrita con la semantica nueva** (`justa` abre; `--holgada` exige holgada) y con
   dos datos que el brief no tenia: la regla de Pedro de los canarios (6400 MB antes del 7b/Chromium a mano)
   y la huella del server desechable.
4. **Commit parcial** (sin la fila de calibracion ni el informe del smoke): el brief los commitea juntos
   con la corrida; la corrida esta bloqueada y el trabajo seco queda verde y a mano para cuando se decida.
5. El ledger dice que el ruling de `--esperar` "se anota en el addendum del spec (3.9)": no existe addendum
   todavia (la seccion 9 termina en el ruling 12) y en los canarios lo escribio el cierre; no toque el spec.

## Por que BLOCKED (los numeros)

- **La maquina, 22:12-22:25, sin juego** (load1 1,1-1,5/16, PSI mem y cpu 0,0, `/api/ps` vacio): `MemAvailable`
  **5920-5998 MB** = `justa` (`mem 5946 < 5746+1024`). Los que ocupan: el server real 1568 MB de RSS, krunner
  497, dos `claude` (444 + 381), plasmashell 424, kwin 149, playwright-mcp 232. El porton del producto
  (`--esperar`, default) ABRE; la regla del controlador para esta task ("MemAvailable < 6400 al empezar:
  BLOCKED, no compitas") y la de Pedro de los canarios ("menos de 6,4 GB libres: espera o BLOCKED") NO.
- **El server desechable pesa 1,48 GB de RSS por el solo import de `calipso.server`** (medido:
  `VmRSS 1514748 kB`; `server.py:2192` construye `Memory(project_root=...)` al importar y `memory.py:163`
  levanta el `SentenceTransformer` del modelo de embeddings; el server real muestra 1,57 GB). Consecuencia:
  con 5946 en reposo, el smoke con su server arriba mide **~4450 MB < 5746 = `cargada` antes de cargar
  ningun modelo**. Bajo `cargada` el keep_alive es 0 (spec 2), asi que el 7b no queda cargado tras `/local`:
  **A** (sin senal; `/api/ps` con el 7b), **N** (el runner no se recrea: con keep_alive 0 se recarga entre el
  juez y el turno, ruling 13) y **V** (el vigia descarga algo que ya no esta) fallan por la maquina, no por
  el producto; **R** apartaria 0 MB (ya cargada) y la fila "cargada de verdad" seria "dos servers de Calipso
  y PSI 0", no carga real; **C** cargaria el 7b con ~4450 MB (lo que la regla de Pedro prohibe). Precedente
  identico: la corrida 2 del smoke de los canarios (`docs/superpowers/2026-09-11-smoke-canarios.md`, "con el
  server desechable arriba (1,7 GB de RSS...) MemAvailable se quedo entre 4991 y 5800 MB ... codigo 3").
- Para que A, N y V sean medibles hace falta `MemAvailable >= ~7250 MB` en el paso 0 (5746 de necesidad +
  ~1500 del server desechable), y para C la regla de Pedro pide 6400 con el server arriba (~7900 en el paso
  0). En reposo con el server real la Ally da 5800-6500; sin el server real (1,57 GB) daria ~7400-8000. Es
  decir: **el smoke completo solo cierra con el server real apagado** (o con los umbrales cambiados), y las
  dos cosas son rulings que el implementador no toma (rulings 1, 6 y 12 del plan).

## Pregunta para el controlador / Pedro

Como se corre la corrida en vivo:
(a) con el server real apagado por Pedro ~15 min (el script queda como esta; `nice -n 19
    .venv/bin/python -m experimentos.carga_smoke` desde el worktree; despues la fila de `CALIBRACION`, el
    informe y el commit del Step 6); o
(b) aceptar una corrida con el server real arriba, sabiendo que A, N, V no son medibles (saldrian FALLO por
    la maquina), que R daria 0 MB apartados y que C viola la regla de los 6400 (habria que saltearlo); o
(c) cambiar umbrales (ruling 1: de Pedro).
Recomiendo (a).

## Dudas menores

- `test_la_ayuda_y_el_docstring...` lee la ayuda de argparse por `redirect_stdout` (argparse no usa
  `salida`); si molesta, se saca la asercion de la ayuda y queda la del docstring.
- La opcion `--sin-esperar` del smoke (del brief) saltea el paso 0: la deje con la ayuda "solo si YA mediste
  no cargada a mano"; no la use.

## Estado de la maquina al terminar

`/api/ps` vacio (nunca se cargo el 7b), puerto 8778 libre (nunca se abrio), sin procesos del smoke ni
reservador vivos, el checkout principal en `main` y limpio, `~/.calipso` intacto. Ultima medicion 22:25:22:
`justa mem=5998 swap_usado=2732 psi 0/0 load1 1.46`.

## Cierre por el controlador (2026-09-11, 22:27-23:05)

El bloqueo de arriba se resolvio con la opcion (a): el controlador apago el server real (sin conexiones desde
las 15:31), corrio el smoke tres veces el mismo y relanzo el server real tras cada corrida (login 200,
`/api/ps` vacio, ningun turno enviado). Logs y telemetrias en este directorio (`smoke-corrida{1,2,3}.log`,
`smoke-telemetria-{wj5k3pbr,xtxofgn9,oypgpdtz}.jsonl`). El cierre (fila de calibracion, informe, commit) lo
hizo un segundo implementador sin correr nada en vivo.

### Las tres corridas

- **Corrida 1 (22:27, EXIT=1, 3 fallos).** V: el 7b que cargo A puso la maquina en `cargada`, N corrio con
  `keep_alive 0` y el 7b se fue solo antes del tick: el vigia no tuvo nada que descargar (no hay fila
  `descarga`). P (dos aserciones): el reservador apartaba ceros tocando un byte por pagina; al cargar el 7b en
  C zram comprimio la reserva (swap +1 GB), la maquina dejo de estar `cargada` y la rutina corrio.
- **Corrida 2 (22:37, EXIT=1, 3 fallos).** V: la recarga con `keep_alive 5m` estaba guardada por un `ps()`
  unico y Ollama tarda segundos en soltar el runner: el ps aun listaba al 7b, no se recargo, y el 7b se fue
  solo otra vez. P: la reserva ya era incompresible (bytes aleatorios), pero cargar el 7b en C mando ~1,2 GB
  de paginas frias de OTROS procesos a zram y al descargarse quedo mas memoria libre: `justa`, la rutina corrio.
- **Corrida 3 (22:45-22:51, EXIT=0).** 27 filas en el resumen: 23 aserciones ok, 4 notas, 0 fallos.

En las tres corridas los pasos 1, A, N, M, R, B, C, L y D dieron ok con los mismos numeros: los seis fallos
fueron dos suposiciones del smoke, no del producto (ruling del controlador en el ledger).

### Los arreglos en `experimentos/carga_smoke.py` (del controlador; el diff estaba sin commitear)

1. El reservador aparta `os.urandom(PASO)` en vez de un `bytearray` tocado: zram no lo comprime.
2. En V, tras M, se espera `/api/ps` vacio (hasta 30 s) y se recarga el 7b desde afuera con `keep_alive "5m"`
   (lo que dejaria un turno bajo `holgada`) para que sea el VIGIA el que descargue; una escena mas en la
   calibracion ("con el 7b recargado para el vigia").
3. Antes de P el reservador vuelve a apartar hasta `cargada` ("reservador tras C, para P"): cargar el 7b en C
   manda frio de otros procesos a zram y al descargarse sobra memoria.
4. El `finally` descarga el 7b que deja D (bajo `holgada` sale con `keep_alive 5m` y nadie lo usa).

### La calibracion (corrida 3; `carga.CALIBRACION`)

Cinco filas nuevas, con el `medido_en` como `cuando`, verificadas campo por campo contra el bloque
`=== calibracion ===` del log con un script:

| cuando | escena | mem | psi_mem | psi_cpu | load1 | swap | nivel |
|---|---|---|---|---|---|---|---|
| 22:45:40 | con el server desechable arriba, el real APAGADO | 7179 | 0,0 | 0,0 | 2,02 | 4156 | holgada |
| 22:47:15 | M: con el 7b cargado | 2709 | 0,28 | 0,0 | 6,46 | 4194 | cargada |
| 22:47:24 | V: el 7b recargado para el vigia | 2469 | 1,39 | 0,0 | 5,70 | 4191 | cargada |
| 22:47:52 | **cargada de verdad: reservador sin modelo, 1536 MB** | **5555** | 0,11 | 0,0 | 4,14 | 4191 | cargada |
| 22:49:08 | P: reservador tras C, 2048 MB | 5513 | 0,03 | 0,0 | 5,94 | 4887 | cargada |

TDD en `test_carga.py`: `test_la_calibracion_anotada_cae_donde_dice` ya no saltea filas sin numeros (exige
`cuando` y `mem_disponible_mb` en todas) y `test_la_fila_cargada_de_verdad_es_la_del_reservador_del_smoke`
fija la fila del paso R (22:47:52, 5555 < 5746, motivo `mem 5555 < 5746`, PSI por debajo del umbral de
holgada, la escena cita el script y el informe). Rojo: `2 failed` (`cuando` None). Verde tras las filas:
`31 passed` (eran 30).

### El informe

`docs/superpowers/2026-09-11-smoke-carga.md`: las tres corridas con lo que fallo y por que era del smoke; la
tabla de las 27 filas de la corrida 3 con tiempos y numeros (de los logs y de las filas `chat_turn` y
`carga` de la telemetria); la calibracion; lo que el smoke NO ejercito (`justa` en un turno, la rama sin
holgada de la histeresis, cargada por PSI, el fallback a local, `sin_3b`/`sin_vision`, `descarga_fallida`,
dos turnos a la vez, las UIs con navegador, Pedro jugando, `--holgada`, el OOM); diez hallazgos para Pedro; el
veredicto; pendientes (umbrales, el server de 1,5 GB, el merge).

### Hallazgos para Pedro (resumen; el detalle en el informe)

1. Un server de Calipso pesa ~1,5 GB antes de servir nada (`SentenceTransformer` al importar `calipso.server`):
   candidato a "entender la causa" antes que a cualquier umbral.
2. Con el server real arriba la Ally en reposo midio `justa` (5920-5998) antes del smoke; con el real apagado,
   `holgada` (7174-8364). Pero a las 23:01, con el real relanzado y este agente corriendo, `/proc/meminfo` dio
   7074 MB (holgada) con 4042 MB en zram: el frio que las tres corridas mandaron a zram sigue ahi.
3. zram comprime lo frio y mueve MemAvailable cuando el 7b entra y sale (tres formas, en el informe); el
   sensor mide lo correcto pero dos "reposos" pueden diferir 1 GB.
4. `keep_alive 0` desde afuera NO corta una request viva: medido 60 s (60311 ms, 479 chars, `done`, sin error).
5. El runner no se recrea entre el juez y el chat (`context_length` sigue 8192 tras `/nube /local`).
6. El paso C es el borde: `/local` bajo `cargada` con 5,4 GB "libres" carga el 7b igual y deja 860-1166 MB de
   MemAvailable con 430-944 MB de zram libre; el vigia lo vio en uso (`descarga_diferida`) y no toco nada.
7. El canario de degeneracion atrapo a C en la corrida 3 (`alfabeto`, 0,366: un tramo en chino).
8. Tiempos: cargar el 7b y contestar una linea 36-42,5 s; `/nube /local` 48-56 s; haiku 9,3-34,8 s; C 54-61 s.
9. El PSI nunca decidio (maximo 16,04 en la corrida 2, contra 20): MemAvailable decidio en todas las escenas.
10. Las rutinas sembradas del fixture (`catastro`, `consumo`) se posponen en cada tick bajo `cargada`: una fila
    por rutina por minuto en la telemetria; las cuentas del dia cuentan rutinas distintas (2), no filas.

### Suite y commit

Orden: la suite completa DESPUES del smoke, con el server real ya relanzado y la maquina holgada por
`/proc/meminfo` (7074 MB a las 23:01; ninguna prueba carga modelo). Resultado y sha en la salida
estructurada del implementador del cierre. Un commit con rutas explicitas: `experimentos/carga_smoke.py`,
`calipso/carga.py`, `test_carga.py`, `docs/superpowers/2026-09-11-smoke-carga.md`. Node no cambio desde la
Task 5 (452 pass). El merge queda para el controlador (ruling 12).
