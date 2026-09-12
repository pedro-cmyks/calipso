# Ola de fix del cierre de feat/carga (unica; 2026-09-11 noche)

Rama `feat/carga` en el WORKTREE `/var/home/pedro/calipso/.claude/worktrees/carga`, HEAD `1c2685b`. Cinco
revisores (sensor, server, UIs+smoke, lente del spec, lente de riesgo) mas Codex gpt-5.5 coincidieron en lo
de abajo. Un critico (punto 1). Todo se arregla en ESTA ola, en orden, con TDD donde hay test, suite completa
antes de cada commit (`cd <worktree> && nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q
--ignore=test_chat_live.py -p no:cacheprovider; echo EXIT=$?`, 0 failed), node si se toca `calipso/web/`
(`cd <worktree>/calipso/web/fabrica && ~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node
--test`), commits con rutas explicitas y el trailer. Un commit por punto (o por pareja afin). NO se corre el
smoke ni se llama a Ollama: el smoke lo corre el controlador despues (apaga el server real). Las lineas
citadas son de `1c2685b`: verifica con `grep -n` antes de editar. Los rulings de abajo son del controlador;
no se rediscuten, se anotan en el reporte si algo no cierra.

## 1. [CRITICO] La memoria efectiva: el modelo cargado cuenta (ruling que revierte en parte el 9.1 del spec)

Medido en el smoke: con el 7b cargado y NADA mas, `MemAvailable` baja de 7179 a 2709 MB (< 5746) y el sensor
dice `cargada`; el vigia descargaria el 7b a los <= 60 s de todo turno local en holgada, suspenderia el local
y el chat quedaria en suscripcion hasta la proxima `holgada` (que con el server real de 1,5 GB puede no
llegar). Es lo contrario de "ocupen cuando puedan ocupar" en el caso mas comun. Ruling: el nivel se mide
contra la memoria EFECTIVA para el modelo:

`mem_efectiva_mb = mem_disponible_mb + sum(size_mb de los modelos de Calipso que /api/ps de ESA medicion lista)`

(es exactamente lo que devuelve un evict). `cargada` si `mem_efectiva < necesidad` (o PSI); `holgada` si
`mem_efectiva >= necesidad + MARGEN_LIBRE_MB` (y PSI/CPU/load1 como hoy); `justa` en el medio. Si el `ps`
no responde (`medido["ollama"] False`), `mem_efectiva = mem_disponible` (fail-open). El escenario del OOM
(17:07: ~500 MB libres con el 7b adentro: 500 + 5203 = 5703 < 5746) sigue dando `cargada` -> el vigia
descarga y el chat va a suscripcion con marca. El ping-pong desaparece por construccion: antes y despues de
un evict la memoria efectiva es la misma. "Modelos de Calipso" = `_modelos_de_calipso()` del server; en
`carga.medir` recibe la lista por parametro (`modelos_propios=`) o la deriva de `dispatch.CONFIG` como hoy
hace el server (elegi lo que menos acople; `carga.py` sigue puro).

- `Carga` suma `mem_efectiva_mb: int` y `modelo_cargado_mb: int` (la suma de los `size` propios listados;
  0 si nada). `nivel(...)` recibe `mem_efectiva` (o lo calcula); el `motivo` dice `mem efectiva 5703 < 5746`
  (o `mem 5506 < 5746` cuando no hay modelo cargado: elegi una forma y aplicala en todos los tests). Los
  avisos siguen diciendo "N MB libres" con `mem_disponible_mb` (lo que Pedro entiende).
- `CALIBRACION`: recalcular `nivel` de las filas con modelo cargado con la regla nueva (M 2709 + 5203 =
  7912 -> holgada; V 2469 + 5203 -> holgada; la fila del terreno 18:22-18:25 con el 7b cargado idem) y anotar
  en el comentario del modulo el ruling y la fecha. El test que fija las filas se ajusta.
- Tests nuevos en `test_carga.py`: (a) 7b cargado en reposo (2709 libres, ps lista el 7b con size 5203) ->
  holgada; (b) el OOM (500 libres, 7b listado) -> cargada; (c) ps caido con 2709 libres -> cargada (fail-open:
  sin ps la memoria efectiva es la disponible); (d) 5506 libres sin modelo -> cargada (como hoy); (e) el
  vigia con (a) NO evicta (test_carga_vigia.py), con (b) SI.
- `test_carga_decide.py`/`test_carga_chat.py`: revisar que ninguna fixture de "cargada" dependa de que el
  modelo listado no cuente (usan `medida("cargada")` por hook: no deberian cambiar; verifica).
- Spec y plan NO se tocan aca (el controlador escribe el addendum). `docs/superpowers/2026-09-11-smoke-carga.md`
  NO se toca aca (el controlador re-corre el smoke).

## 2. [IMPORTANTE] `keep_alive` bajo `cargada` = `"30s"`, no 0

Medido: bajo cargada cada pasada lleva keep_alive 0 y Ollama descarga el 7b al terminar CADA pasada: `/nube`
(juez + turno) y las reentradas del abismo pagan una carga desde disco por pasada (N 48-56 s contra A 36-42 s;
a mitad de N `/api/ps` vacio y 4212 MB libres contra 1925 tres segundos antes). Ruling: `_KEEP_ALIVE
["cargada"] = "30s"`: las pasadas de un mismo turno comparten el runner y el vigia descarga en el tick
siguiente cuando `en_uso` llega a 0 (el 7b no sobrevive mas de ~90 s despues del turno). Ajustar
`test_carga.py::test_keep_alive_y_num_thread_por_nivel` y `test_carga_sitios.py::test_bajo_cargada_los_seis_llevan_keep_alive_0_y_la_mitad_de_los_hilos`
(renombrar). El docstring de `keep_alive()` explica el porque con los numeros.

## 3. [IMPORTANTE] Interruptor `CALIPSO_CARGA=off`

Leido POR LLAMADA en `carga.medir` (patron de `canarios.canarios_activos`, `calipso/canarios.py:39-43`): con
`off` devuelve una `Carga` holgada con `medido` todo en False y `apagado: True` (la rama del invariante 5:
Calipso se comporta como hoy): sin vigia, sin pospuestas, sin marca, sin histeresis, perillas de holgada.
Test en `test_carga.py` (`monkeypatch.setenv`). Documentar en la adenda del estado del proyecto como
"rollback en caliente" junto a `CALIPSO_CANARIOS=off` (`docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md`, seccion 9).

## 4. [IMPORTANTE] Fail-open de verdad en el sensor y en el tick

`calipso/carga.py:230-242` (`necesidad_mb`) solo atrapa `OSError`; un manifiesto de Ollama que sea JSON
valido pero no dict (verificado: `[1]`) levanta `AttributeError` en `tokenizador.blob_del_modelo`, `_decide`
revienta en cada turno y `_tick_con_carga` (`server.py:5728`, `_medir_carga()` fuera del try) se lo traga y
NINGUNA rutina corre, en silencio. Arreglo: `except Exception` en `necesidad_mb` (devuelve
`NECESIDAD_DEFAULT_MB`); en `_tick_con_carga` la medicion adentro de un try: si levanta, fila
`accion: vigia_error` con el error y `run_due(now, handlers)` sin nivel (como hoy). Tests: manifiesto `[1]`
-> `necesidad_mb == NECESIDAD_DEFAULT_MB` y `medir` no levanta; `_medir_carga` que revienta -> las rutinas
corren y queda la fila.

## 5. [IMPORTANTE] Bajo `justa` no se pospone nada

Con el server real corriendo, `justa` es el estado de reposo de la Ally. `justa` quiere decir que el modelo
entra (ruling de `--esperar`). Ruling: `se_pospone`: `cargada` pospone todas; `justa` no pospone ninguna
(`PESADAS` deja de tener efecto bajo justa; dejala como constante documentada o quitala). Ajustar
`test_carga_rutinas.py` (o donde este) y el docstring de `run_due`.

## 6. [IMPORTANTE] El vigia bajo Ollama lento, y suspender antes de evictar

(a) `/api/ps` con 0,5 s bajo carga puede no responder: el vigia no descarga y no deja rastro. Arreglo: el
tick mide con un timeout propio `UMBRALES["PS_TIMEOUT_TICK_S"] = 2.0` (`medir(..., ps_timeout=)` o el
lector inyectado con ese timeout), y si `nivel == "cargada"` y `medido["ollama"]` es False deja una fila
`accion: ps_no_medido`. Test en `test_carga_vigia.py`. (b) `server.py:5714-5716`: `suspender()` se fija
DESPUES del evict; en esa ventana un `_decide` ve holgada y recarga. Arreglo: `carga.suspender()` ANTES del
evict y `carga.liberar()` si el evict fallo (sin pisar una suspension previa: guarda el estado anterior).
Test. (c) `calipso/carga.py:303-309`: el PSI se descarta en bloque si falla uno de los dos archivos; medir
por archivo (`medido["psi_mem"]`, `medido["psi_cpu"]`) y pasar `None` solo por el que fallo. Test mixto.

## 7. [IMPORTANTE] Los fallbacks locales del equipo dinamico bajo `cargada`

`server.py:2854-2857` y `:2916-2919`: si falla un agente o la sintesis, `_run_backend_text(..., "local")`
sin mirar `verdict["avail"]` ni el nivel, sin marca y sin `en_uso`. Arreglo minimo y coherente con el
fallback suscripcion->local del chat (`:4565-4566`): si `_nivel_del(verdict) == "cargada"` (o local
suspendido), el fallback local lleva la senal `carga` con gesto `fallback` y aviso "puede tardar o fallar"
(reusa `_senal_de_carga` si el ws esta a mano; si no, al menos la fila `local_con_aviso`) y corre dentro de
`carga.usando()`. Test por el harness con el planner y un agente que revienta bajo cargada: fila
`local_con_aviso` y `en_uso` de vuelta en 0.

## 8. [IMPORTANTE, Codex] La ventana entre `_decide` local y el primer request

`server.py:3863` (`_decide` en to_thread) y `:4060-4061` (`Uso.tomar()` recien en la ruta final): entre
medio hay awaits; el vigia (que solo actua bajo `cargada`) podria descargar un modelo que el turno esta por
usar. Arreglo: tomar `Uso` apenas `_decide` devuelve `route == "local"` (justo despues del to_thread) y
soltarlo si `/nube` o el ruteo final lo saca de local (el tenedor es idempotente: `tomar` suma una vez). Test:
un turno local con un `_decide` doblado -> `en_uso == 1` antes del primer chunk y 0 en `done`; un turno que
`/nube` sube a suscripcion -> 0 durante el stream. Si el cableado no cierra limpio en una pasada, anota el
motivo en el reporte y deja el punto declarado (no lo fuerces).

## 9. [MENOR] `/model <local>` cerrado como `/local`

`server.py:2586-2593`: `/model <local>` con Ollama caido, complejidad 4-5 o `/think` cae al ranking entero
(verificado: `/model qwen2.5:7b traduce al ingles: hola` con salud local False -> `subscription:claude:haiku`
sin marca). Arreglo: cuando `_gesto_local` da `/model <X>` con X local, pasar por `_veredicto_local` como
`/local`. Tests para los tres caminos en `test_carga_decide.py`.

## 10. [MENOR] Menores baratos (un commit)

- `calipso/web/fabrica/arranque.test.js:97`: el setter de `textContent` del DOM falso vacia `hijos` (como
  el navegador): `set: v => { texto = v; escriturasDeTexto++; n.hijos.length = 0; }`; verificado por el
  revisor que con eso la mutacion de `app.js:1228` (la reinsercion de la cabecera) hace fallar el test 32.
- `docs/superpowers/2026-09-11-smoke-carga.md`: "los 12 tests de node" -> 13 (3+5+3+2) en las dos lineas;
  una linea junto al Arreglo 1: "tras la corrida 3, `1c2685b` cambio el reservador a `readinto` desde
  /dev/urandom (sin copia transitoria); probado en seco, no corrido en vivo". (El resto del informe lo toca el
  controlador tras la nueva corrida.)
- `experimentos/carga_smoke.py`: el docstring del paso L ("hoy en reposo la Ally dio justa, 5876") -> los
  numeros de las tres corridas (holgada 7082-7352 tras liberar, con el server real apagado). Y el paso V
  cambia de sentido con el punto 1: con el 7b cargado y nada mas la maquina es holgada efectiva y el vigia NO
  debe descargar. Reescribir V: (i) con el 7b cargado (tras A/N), medir: `nivel != "cargada"` y
  `mem_efectiva_mb >= necesidad`; esperar dos ticks (130 s) y afirmar que NO hay fila `descarga` y que
  `/api/ps` sigue listando el 7b; (ii) el camino de la descarga queda cubierto por `test_carga_vigia.py` (no
  se puede provocar `cargada` con el 7b adentro sin pasar el tope duro de 1500 MB: seria el OOM de verdad);
  anotar eso en el docstring. R, B, C, P, L, D no cambian de sentido (R: `reservar_hasta_cargada` sin modelo
  sigue dando cargada por memoria efectiva = disponible). El `esperar_ps_vacio` + `cargar_desde_afuera` de V
  se borran. Piezas secas del smoke verificadas (`--help`, `ast.parse`).

## Lo que NO se toca en esta ola (para el addendum del spec, lo escribe el controlador)

- `MARGEN_LIBRE_MB` 1024 y `MARGEN_MODELO_MB` 1280: quedan (umbrales: ruling de Pedro). Con el punto 1, en
  reposo con el 7b cargado la Ally es holgada; sin el 7b es justa (5,9 GB con el server real) u holgada (7,4).
- El server de 1,5 GB por el `SentenceTransformer` al importar: dato para Pedro.
- Las rutinas pospuestas no dejan rastro en `routines.json` ni en el panel (solo telemetria y la Aduana):
  para Pedro.
- Bajo `cargada` el juez de `/nube` corre local sin aviso propio cuando el turno ya iba por suscripcion.
- La marca no se re-emite en el fallback entre suscripciones; doble fila del fallback en las cuentas; el
  texto del aviso de imagen bajo carga; `recent(20000)` en `/api/carga`.

## Reporte

Escribi `/var/home/pedro/calipso/.claude/worktrees/carga/.superpowers/sdd/2026-09-11-carga/ola-de-fix-report.md`:
por punto, que cambiaste (archivo:linea nuevas), el test rojo->verde, la suite con conteo y EXIT, node, los
desvios y dudas. Salida estructurada: status, base_sha (1c2685b), head_sha, commits, tests, concerns,
report_file.
