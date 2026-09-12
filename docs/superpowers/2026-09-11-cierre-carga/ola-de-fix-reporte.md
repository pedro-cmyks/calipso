# Ola de fix del cierre de feat/carga: reporte del implementador (2026-09-12)

Worktree `/var/home/pedro/calipso/.claude/worktrees/carga`, rama `feat/carga`. Base `1c2685b`
(verificado con `git rev-parse HEAD` antes de tocar nada), HEAD `c33663f`. Once commits (uno por punto
mas un refactor del self-review), todos con rutas explicitas y el trailer. Suite base al arrancar:
1850 passed, EXIT=0 (142 s). No se corrio el smoke ni se llamo a Ollama; ~/.calipso y el checkout
principal no se tocaron; no se hizo push.

Un directorio sin trackear aparecio en el worktree durante la ola (`docs/superpowers/2026-09-11-cierre-carga/
revision-final-y-lentes.md`, 23:31): no es mio, no lo toque ni lo agregue a ningun commit.

## Los commits (en orden)

| punto | sha | mensaje |
|---|---|---|
| 1 | `fabe271` | fix(carga): el nivel se mide contra la memoria efectiva (el modelo cargado cuenta) |
| 2 | `091fbfb` | fix(carga): keep_alive bajo cargada es "30s", no 0 |
| 3 | `77920fa` | feat(carga): interruptor CALIPSO_CARGA=off, el rollback en caliente |
| 4 | `bcb8ade` | fix(carga): fail-open de verdad en necesidad_mb y en el tick del vigia |
| 5 | `5db6afa` | fix(rutinas): bajo justa no se pospone ninguna rutina |
| 6 | `ae7840d` | fix(carga): el vigia bajo Ollama lento, suspender antes del evict y PSI por archivo |
| 7 | `1769665` | fix(carga): el fallback local del equipo dinamico avisa bajo cargada |
| 8 | `0eea663` | fix(carga): el turno local toma el contador apenas _decide dice local |
| 9 | `c9b80b6` | fix(carga): /model <local> cerrado como /local |
| 10 | `eaeb0dc` | fix(carga): menores del cierre: DOM falso, informe del smoke y paso V del smoke |
| sr | `c33663f` | refactor(carga): el aviso del fallback del equipo lleva su estado explicito |

## Por punto

### 1. [CRITICO] La memoria efectiva

Que cambio (`calipso/carga.py`):
- docstring del modulo: la regla nueva y el ruling con fecha (lineas 30-52).
- `Carga` suma `mem_efectiva_mb: int` y `modelo_cargado_mb: int` (206-207); `fila()` los arrastra
  (telemetria, `verdict["carga_medicion"]`, `/api/carga`).
- `nivel(..., ncpu, modelo_cargado_mb=0)` (286-323): decide con `mem_disponible + modelo_cargado`;
  el motivo dice `mem efectiva 5703 < 5746` cuando hay modelo cargado y `mem 5506 < 5746` si no (la
  forma elegida; aplicada en todos los tests). Justa: `mem efectiva 6681 < 5746+1024`.
- `medir(..., modelos_propios=None)` (344-428): suma el `size_mb` de los modelos de `/api/ps` cuyo
  nombre esta en `modelos_propios`; sin la lista cuenta solo `modelo` (conservador: nunca suma un
  modelo ajeno). `ps` caido -> `modelo_cargado = 0`, efectiva = disponible (fail-open).
- `CALIBRACION`: cada fila lleva `modelo_cargado_mb` (5203 en las cinco con el 7b adentro, 0 en el
  resto) y el nivel recalculado: M (2709 + 5203 = 7912) holgada, V (2469 + 5203 = 7672) holgada, OOM
  (500 + 5203 = 5703) cargada. Comentario del bloque con el ruling y la fecha.
- `_linea` (CLI) imprime `efectiva=... (modelo ...MB)` cuando hay modelo; `main` mide con
  `modelos_propios={local, classifier}` de config (`_modelos_configurados`).
- `calipso/server.py:2434`: `_medir_carga` pasa `modelos_propios=_modelos_de_calipso()` (chat +
  clasificador + vision). Comentario del `_decide` (2583-2588) reescrito: el 7b cargado ya no es una
  excepcion, entra en la medicion.

Tests rojo -> verde (`test_carga.py`): `test_el_modelo_cargado_cuenta_como_memoria_efectiva` (nivel puro:
a, b, justa, d), `test_medir_con_el_7b_cargado_en_reposo_es_holgada_y_sin_ps_es_cargada` (a, b, c, d con
/proc y ps falsos), `test_solo_los_modelos_propios_suman_a_la_memoria_efectiva` (ajeno no suma; con la
lista suma el 3b; el aviso sigue con los MB libres), `test_la_calibracion_con_el_7b_cargado_cae_donde_dice_el_ruling`;
la calibracion ejecutable pasa `modelo_cargado_mb` por fila. `test_carga_vigia.py`:
`test_con_el_7b_cargado_en_reposo_no_descarga_y_en_el_oom_si` (e) y
`test_medir_carga_del_server_pasa_los_modelos_de_calipso_como_propios`. El molde `medida()` gana
`modelo_cargado_mb=0` y deriva `mem_efectiva_mb`.
`test_carga_decide.py`/`test_carga_chat.py` verificados: usan `medida("cargada")` por hook (480 MB, sin
modelo), no dependen de que el modelo listado no cuente; no cambiaron. 21 rojos -> 0.

Desvio anotado: las filas del terreno 18:22:32 y 18:25:38 (1478/1578 + 5203) NO dan holgada como
sugiere el "idem" del brief: dan `justa` (load1 8,54 y 9,96 >= 8; y 18:22 tambien por 6681 < 6770).
Las anote asi, con la razon en la escena; el test las fija en justa. Suite: 1856 passed, EXIT=0.

### 2. `keep_alive` bajo cargada = "30s"

`calipso/carga.py:448` `_KEEP_ALIVE["cargada"] = "30s"`; docstring de `keep_alive()` (451-463) con los
numeros (N 48-56 s contra A 36-42 s, ps vacio a mitad de N, ~90 s de vida maxima tras el turno).
Tests: `test_keep_alive_y_num_thread_por_nivel` (asserta "30s" y que el docstring lleva los numeros),
`test_payload_local_agrega_las_perillas_sin_pisar_options_ni_mutar`, y en `test_carga_sitios.py`
`test_bajo_cargada_los_seis_llevan_keep_alive_30s_y_la_mitad_de_los_hilos` (renombrado). Suite: 1856, EXIT=0.

### 3. `CALIPSO_CARGA=off`

`calipso/carga.py`: `carga_activa()` (325-329, por llamada, patron de `canarios_activos`), `_apagada()`
(332-341) y el corte al principio de `medir` (358-361, antes de la cache y de cualquier lectura);
`Carga.apagado: bool = False` (222, ultimo campo, con default: el molde `medida()` no cambia).
Docstring del modulo. Adenda del estado del proyecto, seccion 9, junto a `CALIPSO_CANARIOS=off`
(`docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md:299-303`).
Test: `test_calipso_carga_off_apaga_el_sensor_por_llamada` (`monkeypatch.setenv`; con `OFF` no lee /proc
ni hace GET, ni inyectado ni sin inyectar; `""`, `on`, `0`, `false` y ausente son prendido). Suite: 1857, EXIT=0.

### 4. Fail-open de verdad

`calipso/carga.py:267-284` `necesidad_mb` atrapa `Exception`. `calipso/server.py:5781-5806`
`_tick_con_carga`: la medicion adentro del try; si levanta, fila `vigia_error` con el error (sin fila de
medicion) y `run_due(now, handlers)` sin nivel. Tests: `test_un_manifiesto_que_no_es_dict_no_revienta_la_necesidad_ni_medir`
(manifiesto `[1]` -> default, `medir` no levanta) y en el vigia
`test_una_medicion_que_revienta_no_se_lleva_las_rutinas_y_deja_vigia_error` (las rutinas corren, `ran`
con ok, la fila queda). Suite: 1859, EXIT=0.

### 5. Bajo justa no se pospone nada

`calipso/routines.py:46-52` `se_pospone` = `nivel == "cargada"`; `PESADAS` quitada (sin efecto);
docstrings de `se_pospone` y `run_due` y el comentario del bloque. `test_carga_rutinas.py`:
`test_bajo_justa_no_se_pospone_ninguna_ni_departamento` (reemplaza al de "solo departamento"),
`test_se_pospone_es_la_regla_del_ruling` (asserta que `PESADAS` no existe). `test_routines.py` (script)
sigue "OK". Suite: 1859, EXIT=0.

### 6. El vigia bajo Ollama lento, suspender antes, PSI por archivo

(a) `UMBRALES["PS_TIMEOUT_TICK_S"] = 2.0` (`carga.py:118`); `medir(..., ps_timeout=None)` (el lector
default es `ollama_loaded_models(timeout=ps_timeout)`); `_medir_carga(ps_timeout=None)` (`server.py:2434`);
el tick mide con `PS_TIMEOUT_TICK_S` y deja `ps_no_medido` si `cargada` y `medido["ollama"]` False
(`server.py:5791-5795`); anotada entre las acciones que no se cuentan (`carga.py:181-183`).
(b) `_vigia_del_modelo` (`server.py:5762-5776`): `suspendido_antes`, `suspender()` ANTES del evict, `try/finally`
que libera si el evict fallo o revento y no habia suspension previa.
(c) `medir`: `medido["psi_mem"]` y `medido["psi_cpu"]` por archivo; `nivel` recibe `None` solo por el
que fallo. La clave `medido["psi"]` desaparece (solo la usaban el sensor y sus tests; `aduana.js` y el
endpoint no la leen).
Tests: `test_medir_con_ps_timeout_propio_lo_pasa_al_lector_de_api_ps`,
`test_el_psi_se_mide_por_archivo_y_solo_el_que_fallo_no_decide` (mixto en los dos sentidos), y en el
vigia `test_el_tick_mide_con_el_timeout_propio_del_ps_y_anota_si_no_respondio` (con el `_medir_carga`
real y `carga.medir` doblado; bajo holgada sin ps no hay fila) y
`test_suspende_antes_del_evict_y_libera_si_fallo_sin_pisar_una_suspension_previa` (el espia del evict ve
`local_suspendido` True; falla sin previa -> liberado; con previa -> sigue; revienta -> liberado). El
fixture `tick` dobla `_medir_carga` con `lambda **k`. Suite: 1863, EXIT=0.

### 7. Los fallbacks locales del equipo dinamico

`server.py:2785-2802` `_fallback_local_del_equipo(ws, verdict, system, user_msg, chat_id, avisado)`: si
`_nivel_del(verdict) == "cargada"` o el local esta suspendido, `_senal_de_carga(ws, verdict, "local",
"fallback", chat_id)` (senal ws + fila `local_con_aviso`) una vez por turno, y `_run_backend_text(local)`
en to_thread (que ya corre dentro de `carga.usando()`). Los dos sitios (agente 2886, sintesis 2948) pasan
por ahi; `_run_dynamic_team` gana `chat_id=None` (2810) y el turno lo pasa (4256). Tras el self-review
(`c33663f`) el "una vez por turno" es un dict `avisado_fallback` del equipo, no una llave en el veredicto.
Tests (`test_carga_chat.py`, harness real con `_should_orchestrate` True, planner fijo y un agente que
revienta): `test_el_fallback_local_de_un_agente_del_equipo_bajo_cargada_avisa_y_suelta_el_contador`
(una senal con gesto `fallback` y el aviso, antes del primer chunk; fila `local_con_aviso` con el chat;
los dos POST locales con `en_uso >= 1`; 0 al final; `fallback_route` local en el evento `agent done`) y
`test_el_fallback_local_del_equipo_bajo_holgada_no_avisa`. Suite: 1865, EXIT=0.
Duda anotada: la marca del fallback del equipo no pisa `meta.carga` del turno (esa variable vive en
`ws_chat`); queda como senal + fila, que es lo que pide el brief ("al menos la fila").

### 8. La ventana entre `_decide` local y el primer request

`server.py:3897-3905`: `uso_local.tomar()` justo despues del `to_thread(_decide)` si `route == "local"`;
`/help` y `/mia` sueltan antes de su `continue` (3907, 3919); en la ruta final (4104-4108) local toma
(idempotente) y cualquier otra suelta. Comentario del tenedor actualizado (3813-3816). El cableado cerro
limpio en una pasada. Tests: `test_el_turno_local_toma_el_contador_apenas_decide_y_lo_suelta_en_done`
(`en_uso == 1` dentro de `_ficha_y_cuenta`, el primer await tras `_decide`; 0 en done),
`test_un_turno_que_nube_sube_a_suscripcion_suelta_el_contador_durante_el_stream` (1 en la ficha, 0
cuando corre `_harness_context` post-ruteo, 0 al final, ningun POST local),
`test_help_suelta_el_contador_tomado_tras_decide`. Suite: 1868, EXIT=0.

### 9. `/model <local>` cerrado como `/local`

`server.py:2597`: el veredicto directo tambien cuando `gesto` empieza por `/model `; `_veredicto_local`
(2486-2504) reconoce X ademas por el nombre del agente en la sesion (como `_gesto_local`). Solo `/local`
sigue rompiendo la suspension. Tests (`test_carga_decide.py`): Ollama caido, complejidad 5 (con el 3b
forzado), `/think`, y `test_model_local_no_rompe_la_suspension_ni_cambia_el_camino_de_suscripcion`
(`/model sonnet` sigue por el ranking). Suite: 1872, EXIT=0.

### 10. Menores

- `calipso/web/fabrica/arranque.test.js:95-104`: el setter de `textContent` vacia `hijos`. Verificado
  con una mutacion transitoria en `app.js` (sin el `insertBefore` de la cabecera): `not ok 76` ("la carga
  antes del primer chunk sale como cabecera..."), 451/452; `app.js` restaurado byte a byte.
- `docs/superpowers/2026-09-11-smoke-carga.md`: "12 tests de node" -> 13 (3+5+3+2) en las dos lineas
  (11 y 223); linea del `readinto` junto al Arreglo 1 (51-52).
- `experimentos/carga_smoke.py`: docstring de L con los numeros de las tres corridas (holgada 7082-7352
  tras liberar, server real apagado); M afirma `nivel != "cargada"` y `mem_efectiva_mb >= necesidad_mb`
  con el 7b listado (ya no aparta memoria "hasta cargada" ahi); V reescrito: espera 130 s (dos ticks),
  afirma que NO hay fila `descarga` nueva y que `/api/ps` sigue listando el 7b (ok si M dio holgada;
  si M dio justa el keep_alive fue "2m" y una expiracion de Ollama no es una descarga: nota, no fallo);
  despues el smoke descarga el 7b desde afuera (`evict_desde_afuera`, sin request viva) porque R, B, C,
  P necesitan el 7b afuera y carga real. `cargar_desde_afuera` borrado; `esperar_ps_vacio` se queda
  (lo usan V-evict y C). Docstring: el camino de la descarga queda en `test_carga_vigia.py` y no se
  provoca en vivo (500 + 5203 < 5746 seria pasar el tope duro de 1500 MB). `linea()` y la impresion de
  la calibracion muestran `mem_efectiva_mb`/`modelo_cargado_mb`. Piezas secas: `ast.parse` ok, `--help`
  ok (sin tocar Ollama). Test nuevo `test_el_smoke_parsea_y_su_paso_v_es_el_del_ruling`.
- Desvio menor en C: el brief dice que C no cambia de sentido; el sentido se mantiene (el ps queda vacio
  tras el turno) pero con `keep_alive "30s"` (punto 2) el 7b vive hasta 30 s tras el turno y el vigia lo
  descarga al tick: `esperar_ps_vacio(ESPERA_TICK_S)` (90 s) en vez de 30 s, y la etiqueta lo dice.
- Node: 452/452. Suite: 1873, EXIT=0.

## La suite

Antes de CADA commit: `cd <worktree> && nice -n 19 /var/home/pedro/calipso/.venv/bin/python -m pytest -q
--ignore=test_chat_live.py -p no:cacheprovider`. Conteos: base 1850 -> 1856 (p1) -> 1856 (p2) -> 1857 (p3)
-> 1859 (p4) -> 1859 (p5) -> 1863 (p6) -> 1865 (p7) -> 1868 (p8) -> 1872 (p9) -> 1873 (p10) -> 1873 (sr);
siempre 0 failed, EXIT=0, ~132-136 s. `test_routines.py` (script): "OK: rutinas/timers verificable".
Node (`calipso/web/fabrica`, `node --test`): 452 pass, 0 fail (corrido en el punto 10 y en el self-review).

## Desvios y dudas (resumen)

1. Calibracion 18:22/18:25 con el 7b: `justa`, no holgada (load1 >= 8; 18:22 tambien por memoria).
2. `medido["psi"]` reemplazada por `psi_mem`/`psi_cpu` (nadie mas la leia).
3. La marca del fallback del equipo no llega a `meta.carga` del turno (solo senal + fila).
4. C del smoke espera hasta 90 s el ps vacio (keep_alive "30s" + vigia), no 30.
5. V del smoke: si M mide `justa` (keep_alive "2m"), la presencia del 7b a los 130 s es nota, no fallo;
   la ausencia de fila `descarga` si es fallo.
6. `_apagada` (CALIPSO_CARGA=off) reporta `necesidad_mb = NECESIDAD_DEFAULT_MB` y ceros: no se calcula
   nada (ni el blob) con el interruptor en off.
7. No se toco: spec, plan, ni el resto de `docs/superpowers/2026-09-11-smoke-carga.md` (el controlador
   re-corre el smoke); no se corrio el smoke ni Ollama.
