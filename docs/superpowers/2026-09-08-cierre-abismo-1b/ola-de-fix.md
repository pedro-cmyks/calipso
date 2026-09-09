# Ola de fix del cierre de feat/abismo-1b -- reporte

Implementador de la unica ola de fix. Rama `feat/abismo-1b`; base `82b2ede1b2e818fa1e76b6ddf54a08d87a234268`,
head `7011b9b4bbfa3cbf1bc61594762eafa44e793a03` (ocho commits, 16 archivos, +993/-95). Arbol limpio al cerrar.
Nada pusheado, main intacto, nada dentro de `.superpowers/` entro al repo (este reporte vive ahi, ignorado por git).

Regla de trabajo: TDD para todo lo que cambia conducta (el test rojo primero, focalizado, sobre el harness de
`test_abismo_chat.py`), suite completa con `EXIT=0` antes de cada commit, `node --test` cuando toque `calipso/web/`,
`git add` con rutas explicitas, commits por tema. Ningun import de calipso fuera de pytest sin `CALIPSO_HOME` a un
temporal (la medicion de h05 corrio sobre una COPIA del home del smoke).

## Resumen

| Hallazgo | Estado | Commit |
|---|---|---|
| h01 one-shot: prefijo abierto / foco anidado / reponer tragan la reentrada | cerrado (3 tests) | `eeb098c` |
| h02 el filtro del stream no llega a punto fijo en el empalme | cerrado (2 tests + 1 de integracion) | `35ef0d4` |
| h03 reinvocacion del CLI que falla cierra el turno mudo | cerrado (3 tests; + H4 del fallback que pisaba `full`) | `8833163` |
| h04 la fuente `chats` pesca el chat activo y la pregunta | cerrado (4 tests; decision documentada) | `6d4dc0e` |
| h05 el 7b local no emite la marca por su cuenta | MEDIDO, NO aplicado: la posicion no lo resuelve; decision de Pedro (spec 12) | `7011b9b` (evidencia) |
| m1 los `apagada = True` sin test | cerrado (3 tests guardia) | `b3d4d74`, `4245b4b` |
| m2 `stderr.txt` de jobs crudo | cerrado (3 sitios + 1 test) | `4245b4b` |
| m3 `Harness.recibir` sin plazo | cerrado (plazo + drenaje + 1 test) | `c8644d2` |

Suite al cerrar: `cd /var/home/pedro/calipso && .venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
-> `1470 passed, 4 warnings in 98.18s` `EXIT=0` (linea base 1453; +17 tests). Node desde `calipso/web/fabrica/`:
`# tests 412 / # pass 412 / # fail 0` `NODE_EXIT=0`. Los tests del abismo focalizados: `109 passed`.

## h01 -- ruta one-shot: el filtro cortaba o retenia por su cuenta y nadie lo consumia

**Causa.** En suscripcion el corte lo decide `cortar_en_marca` (PATRON sobre el texto CRUDO), pero el tramo pasa
despues por la tuberia del Emisor (foco -> `FiltroAbismo` con estado y `puede_cortar=estado_abismo.puede_cortar`).
Tres formas de divergir: (S3b) el tramo termina en un `⟦abismo:` abierto que el filtro RETIENE a traves de la pesca
y la reinvocacion, la continuacion se pega detras y `cerrar()` la descarta entera como `abierta`; (S11a) PATRON no
admite corchetes en el cuerpo, foco saca el `⟦foco:atlas⟧` de adentro y el filtro ve una VALIDA y corta solo, con
una marca pendiente que nadie consume; (S11b) en /nube `reponer` corre antes del filtro y acorta una ilegible de
161 a 156 chars: valida para el filtro, invisible para el detector.

**Cambio** (`calipso/server.py`, `calipso/abismo/filtro.py` docstring):
- En la construccion del Emisor del turno, si `route == "subscription"` el `FiltroAbismo` recibe
  `puede_cortar=lambda: False`: en one-shot el corte lo decide SOLO el detector; el filtro retira con aviso
  (`sin_corte`) y el texto posterior vale. El tope de tres sigue pasando por `estado_abismo.puede_cortar()` en el
  bucle one-shot, como antes (el test del tope `test_en_suscripcion_la_cuarta_marca_no_corta` sigue verde con el
  mismo aviso).
- Tras `visible = await emisor.chunk(visible)` en el bucle one-shot: `visible += await emisor.cerrar()`. El texto
  llego entero, nada retenido puede completarse en otra invocacion: un corchete suelto se ve, un `⟦abismo:` abierto se
  descarta con aviso `abierta` ahi mismo (spec 11), como ya hacia el final del turno.
- `tramos_crudos.append(recortar_abierta(retirar_marcas(tramo_crudo)))`: el "venias diciendo" no lleva la marca a
  medias (antes viajaba `Venias diciendo: ⟦abismo:`).

**Tests** (rojos antes del fix con exactamente los visibles del hallazgo: `'x '`, `'Dejame ver '`, `'Le dije '`):
- `test_abismo_suscripcion.py::test_en_suscripcion_un_prefijo_abierto_antes_de_la_marca_no_traga_la_reentrada`
  (guion de la sonda: `x ⟦abismo:zzz ⟦abismo:chats libro⟧ fin` + `y sigo` -> visible y persistido `x y sigo`, dos
  invocaciones, `Venias diciendo: x \n` sin `⟦`, fases pondering/pescado, un done, fila `retirada/abierta` con
  `largo == len("⟦abismo:zzz ")`).
- `test_abismo_suscripcion.py::test_en_suscripcion_una_marca_que_solo_ve_la_tuberia_se_retira_sin_cortar` (S11a:
  visible `Dejame ver  y esto sigue`, sin senal, una invocacion, fila `sin_corte`).
- `test_abismo_nube.py::test_en_nube_por_suscripcion_reponer_no_le_da_al_filtro_una_marca_que_el_detector_no_vio`
  (S11b: cuerpo de 161 crudo / 156 repuesto; visible `Le dije  y esto sigue`, una invocacion, fila `sin_corte`).

Salida del rojo: `3 failed, 12 deselected` con `assert 'x ' == 'x y sigo'`, `assert 'Dejame ver ' == 'Dejame ver  y
esto sigue'`, `assert 'Le dije ' == 'Le dije  y esto sigue'`. Verde tras el fix: `52 passed` (los cuatro archivos).

**Divergencia que queda, declarada:** con el foco anidado en el cuerpo, streaming CONSULTA (la tuberia viva ve la
marca) y one-shot la retira con aviso (el detector no la ve). Antes one-shot perdia el resto del turno; ahora no
pierde nada. Igualar del todo exigiria correr el detector sobre el texto post-foco/post-reponer y mapear el corte al
crudo; no es de una ola de fix.

## h02 -- el filtro del stream dejaba salir una marca valida armada por empalme

**Causa.** `FiltroAbismo.comer` juzgaba el `⟦abismo:` de afuera como texto (su cuerpo tenia otro corchete), lo
emitia, retiraba la ilegible de adentro y seguia desde ahi: `a ⟦abismo:chats ⟦abismo:zzz nada⟧ libro⟧ b` salia
como `a ⟦abismo:chats  libro⟧ b`, valida, visible y persistida, por las dos rutas.

**Cambio** (`calipso/abismo/filtro.py`): tras cada retiro (ilegible o `sin_corte`) el bucle relee desde lo que el
trozo ya daba por visible (`buf = "".join(visible) + resto; visible = []`), hasta punto fijo, como `_retirar_abismo`.
Termina siempre (cada vuelta acorta el texto en una marca al menos). La marca armada se juzga como cualquiera: corta
si puede, se retira con aviso si no. Partido en trozos, el prefijo de afuera se RETIENE en vez de mostrarse a medias.

**Tests:**
- `test_abismo_filtro.py::test_el_filtro_relee_el_empalme_hasta_punto_fijo` (entero con corte, entero sin corte,
  en dos trozos, y el empalme de dos vueltas con el tope alcanzado).
- `test_abismo_filtro.py::test_las_dos_rutas_de_retiro_juzgan_igual_el_empalme` (EMPALMES gana el tercer texto).
- `test_abismo_chat.py::test_un_empalme_que_arma_una_marca_valida_no_llega_a_pedro_ni_a_disco` (la sonda I por el
  WS: pondering/pescado, visible `a z`, chats.json sin `⟦`, fila `ilegible`).

Rojo: `2 failed, 19 passed` (los dos primeros). Verde: `47 passed` (filtro+chat+suscripcion+nube). Suite: `1455 passed`.

## h03 -- la reinvocacion del CLI que falla cerraba el turno mudo

**Causa.** `if full and used_route == "subscription": pass` era en main el camino de exito del alterno (`full`
llegaba vacio si la suscripcion reventaba). Con el bucle one-shot `full` ya lleva el tramo pescado, y el fallo de
la SEGUNDA invocacion caia ahi como exito.

**Cambio** (`calipso/server.py`, `calipso/web/index.html`):
- `alterno_ok = False` al entrar al `except`; `alterno_ok = True` justo antes del `raise StopIteration` del alterno;
  la rama pasa a `if not alterno_ok:` (mismo cuerpo del fallback local; el `if full: pass` muerto se fue).
- H4 de completitud, pegado al mismo bloque: el alterno ya no REASIGNA `full` (`texto_alterno` + `full +=`) y el
  `completion_tokens` se acumula. Lo persistido es lo que Pedro leyo.
- `_run_subscription_text_live` manda `{"type":"process","action":"failed", job_id, label, client, model, error}`
  (el `msg` ya limpio de marcas) cuando el CLI sale con `returncode != 0`; la PWA lo pinta (`updateDetail` +
  meta "<label> fallo"); la fabrica no pinta `process` (nunca lo hizo) y lo ignora.
- `cli_falso` gana `stderr` y `exit` por paso (compatible hacia atras; sirve como codex tambien).

**Tests** (`test_abismo_suscripcion.py`):
- `test_una_reinvocacion_que_falla_cae_al_fallback_local_con_aviso` (U1: sin alterno; visible `Dejame ver respuesta
  local`, metas `[None, "fallback a local"]`, 2 CLI + 1 local, `process/failed` con la etiqueta "(reentrada del
  abismo N)" y sin `⟦`, `chat_turn.fallbacks == [(subscription, local)]`, `route_used == local`, un done).
- `test_una_reinvocacion_que_falla_prueba_el_alterno_y_despues_el_local` (U2: 3 CLI, metas
  `[None, "fallback entre suscripciones", "fallback a local"]`, dos filas de fallback).
- `test_el_alterno_que_si_responde_se_suma_al_tramo_y_no_lo_pisa` (H4: visible y persistido `Dejame ver desde el
  alterno`, memoria con las dos partes).

Rojo: `3 failed` con `assert 'Dejame ver ' == 'Dejame ver respuesta local'` (x2) y `assert 'desde el alterno' ==
'Dejame ver desde el alterno'`. Verde: `18 passed`. Suite `1462 passed`; node `412 pass`.

## h04 -- la fuente `chats` pescaba el chat activo y la propia pregunta

**Decision tomada (no estaba en el spec), documentada en los docstrings:** dos regimenes.
- Local: el chat activo se pesca solo por FUERA de lo que el modelo ya tiene: sus ultimos `_HISTORY_TURNS + 1`
  mensajes (la ventana exacta de `_history_messages` mas la pregunta, ya persistida cuando la consulta corre) no
  entran al bloque; lo anterior a esa ventana en el MISMO chat si (spec seccion 1: "mas alla de los 12 mensajes").
- /nube (`destino == "nube"`, que coincide con `chat_id_nube=None`): el chat activo ENTERO queda fuera. La Fase 2a
  cerro el canal "sin historial"; el bloque no puede ser su puerta de atras.

**Cambio:** `fuentes.chats_viejos(resto, *, chat_activo=None, en_contexto=0)` (`None` = el activo entero afuera;
sin `chat_activo`, todo es viejo: los tests del 1a siguen tal cual); `consulta.resolver(..., chat_activo, en_contexto)`;
`_pescar_abismo(..., chat_id)` calcula `en_contexto = None if destino == "nube" else _HISTORY_TURNS + 1` y los dos
llamadores le pasan `chat_id`. Los dobles `lambda resto:` de los tests del 1a (consulta, minors, turno) pasan a
`lambda resto, **kw:` (eran dobles de la firma vieja).

**Tests:**
- `test_abismo_fuentes.py::test_chats_viejos_no_pesca_lo_que_el_chat_activo_ya_tiene_en_contexto` y
  `::test_chats_viejos_deja_fuera_el_chat_activo_entero_si_se_lo_pide`.
- `test_abismo_chat.py::test_la_fuente_chats_no_pesca_la_pregunta_ni_lo_que_el_modelo_ya_tiene` (la sonda T1: 3
  mensajes viejos + 12 recientes + la pregunta en el activo, un chat viejo sembrado; el bloque trae el chat viejo y
  los 3 viejos del activo, ni la pregunta ni los recientes; el historial de la reentrada son exactamente los 12
  recientes).
- `test_abismo_nube.py::test_en_nube_un_turno_local_previo_de_la_misma_conversacion_no_viaja_por_el_bloque` (la
  sonda V1: "presto"/"cocina"/"Marta" en ningun envio ni en `texto_tapado`; el chat viejo con Ana si viaja tapado).

Rojo: `TypeError: chats_viejos() got an unexpected keyword argument 'chat_activo'` (x2), el bloque con `que libro
lei` y siete `mensaje reciente`, y `'cocina' in ... texto_tapado`. Verde: `74 passed` (nueve archivos). Suite `1470`.

## h05 -- el 7b local no emite la marca por su cuenta: MEDIDO, NO APLICADO

La hipotesis del hallazgo era la posicion (cuarta de diez secciones y no al final, como en el banco). Antes de
mover algo medido, se midio: el protocolo del porton (banco v2, 30 items, temp 0, `/api/generate`, N=2 de
screening) sobre el system de PRODUCCION armado por `_build_context` con una copia del home del smoke (catastro
real, core y chats sembrados, `num_ctx` 8192), en tres posiciones con la letra byte-identica, mas el control del
banco. 240 llamadas al 7b real (corre en CPU en la Ally; el primer intento murio por el timeout de 120 s de
`dispatch` cuando la suite corria en paralelo, y se relanzo con timeout largo; el JSONL es reanudable).

| Variante | memoria | chats | proyecto | espurias | copia literal del molde |
|---|---|---|---|---|---|
| banco (control, 687 chars) | 10/12 (83%) PASA | 12/12 PASA | 12/12 PASA | 2/24 (8%) | 22/34 |
| actual (produccion, 7420 chars) | 2/12 (17%) | 6/12 (50%) | 2/12 (17%) | 0/24 | 5/10 |
| final (el bloque al final) | 5/12 (42%) | 5/12 (42%) | 2/12 (17%) | 0/24 | 6/12 |
| primero (el bloque antes de todo) | 4/12 (33%) | 8/12 (67%) | 4/12 (33%) | 0/24 | 12/16 |

- El control reproduce el porton v2 hoy: el entorno no cambio.
- El system de produccion (no lo trunca `num_ctx`: 7.4k chars) le borra al contrato la mejora entera, en CUALQUIER
  posicion: `actual` son los numeros de la linea base v1 que NO PASO. Lo que compite no es el lugar sino el resto
  del system (Constitucion de 3000, memoria nucleo, las otras diez instrucciones del "Contrato interno", proyectos,
  economia): el 7b pide detalles, contesta "no tengo registros" (la confabulacion de ausencia) o sigue OTRA
  instruccion al pie de la letra (en `final`/mem-medico arranca un JSON `"tipoDeTarea": "chat"` y se pasa al chino).
- Hallazgo lateral sobre la metrica del porton: 22 de las 34 marcas legibles del control son la COPIA LITERAL del
  molde (`⟦abismo:memoria pregunta⟧`, `⟦abismo:chats palabras...⟧`, `⟦abismo:proyecto nombre⟧`): validas para
  `parsear`, inutiles en produccion (pescarian por "pregunta"). El 83/100/100 del v2 esta inflado por el loro.

**Por que no se aplico:** mover el bloque no lo resuelve (chats empeora al final; nada llega al piso) y seria churn
sobre algo medido. El cableado del 1b esta bien; la promesa "ante la duda, CONSULTA" no se sostiene en la ruta
local con el system de produccion, y esa es la bifurcacion que el spec (seccion 12) reserva para Pedro con los
numeros en la mano: refinar el indice o podar el system y re-medir el porton SOBRE el system de produccion, cablear
la consulta solo en rutas grandes (Opus la emitio sola en el smoke), o aceptar el regimen actual hasta la rebanada
2. Y contar como legible solo la marca que no copia el molde.

**Evidencia archivada (commit `7011b9b`):** `experimentos/consulta_abismo_posicion.py` (reusable, home por
parametro, JSONL reanudable), `experimentos/consulta_abismo_posicion_produccion.jsonl` (cache crudo, 240 filas con
`salida[:400]`), `experimentos/consulta_abismo_posicion_produccion.md` (tablas por variante y por item, lectura).

## m1 -- guardias de los `apagada = True`

Tests guardia (verdes de entrada, moldes de las sondas B/C del revisor final y S10c de la adversaria):
- `test_abismo_chat.py::test_la_ruta_orquestador_retira_la_marca_sin_cortar_y_emite_el_texto_entero`
  (`_should_orchestrate -> True`, `_run_dynamic_team` falso con marca: visible `sintesis  entera`, sin senal, 0
  llamadas al modelo, `cost.route == orchestrator`, fila `sin_corte`, chats.json sin `⟦`).
- `test_abismo_chat.py::test_el_fallback_local_tras_un_corte_retira_la_marca_sin_cortar` (`/api` corta y pesca, la
  reentrada api revienta, el local emite marca: visible `a fallback  entero`, un done, fallbacks `[(api, local)]`).
- `test_abismo_suscripcion.py::test_el_fallback_entre_suscripciones_retira_la_marca_sin_cortar` (el alterno emite
  marca: `hola  entero`, sin senal, fila `sin_corte`, el error del fallback sin `⟦` en telemetry).

## m2 -- `stderr.txt` de jobs

`jobs.write_artifact(..., "stderr.txt", _limpiar_marcas(stderr))` en los tres sitios (/stop, fallo, exito) de
`_run_subscription_text_live`. Test `test_abismo_suscripcion.py::test_el_stderr_de_los_jobs_no_lleva_la_marca`
(un CLI que escribe la marca a stderr en un job que falla y en el alterno que termina: los dos `stderr.txt` existen,
sin `⟦`, con el resto del texto). Rojo: `assert '⟦' not in 'aviso ⟦abis...bro⟧ del cli'`. Suite `1466 passed`.

## m3 -- `Harness.recibir` con plazo

`Harness.recibir(ws, hasta_dones=1, plazo=PLAZO=60)`: hilo demonio + `join(plazo)`; si no llegaron los done es
`AssertionError("en 60 s llegaron N de M done: [tipos...]")`, y una excepcion del socket se re-lanza en el test.
`Harness.turno` ademas drena `DRENAJE=0.25` s tras el ultimo done (`lo_que_siga`, el molde de test_abismo_nube
movido al harness), asi `tipos.count("done") == 1` es una asercion de verdad en todo `test_abismo_chat.py` (T8);
`_turno_con_un_solo_done` de nube queda como la guarda sobre `chat.turno`. Test
`test_abismo_chat.py::test_el_harness_no_se_cuelga_si_falta_el_done` (socket mudo, plazo 0.3 s, `pytest.raises`
con `match="0 de 1 done"`). El rojo de este item ES el cuelgue: no se corrio en rojo a proposito. Costo: ~+12 s de
suite por el drenaje.

## Commits (base 82b2ede -> head 7011b9b)

```
35ef0d4 fix(abismo): el filtro del stream relee el empalme hasta punto fijo -- ...            suite 1455 passed
c8644d2 test(abismo): el harness tiene plazo ... y drena tras el ultimo done ...              suite 1456 passed
eeb098c fix(abismo): en la ruta one-shot el filtro no corta por su cuenta ...                 suite 1459 passed
8833163 fix(abismo): una reinvocacion del CLI que falla cae al fallback ... process/failed    suite 1462 passed, node 412
4245b4b fix(abismo): stderr.txt de los jobs pasa por _limpiar_marcas ...                      suite 1466 passed
b3d4d74 test(abismo): guardias de los apagada del orquestador y del fallback local ...        (misma corrida: 1466)
6d4dc0e fix(abismo): la fuente chats no pesca lo que el modelo ya tiene del chat activo ...   suite 1470 passed
7011b9b docs(abismo): el porton medido sobre el system de produccion ...                      suite 1470 passed
```

Nota sobre `4245b4b`/`b3d4d74`: una sola corrida de la suite para los dos (el arbol no cambio entre uno y otro; el
primero es un subconjunto del segundo que solo omite tests). Para que esos dos commits fueran de tema puro, los tests
de h04 (todavia sin implementacion) se apartaron del arbol durante esa corrida y se restauraron despues.

## Lo que toca el flujo (para el re-smoke)

`ws_chat` (construccion del Emisor, bucle one-shot, el `except` del fallback), `_run_subscription_text_live`
(`process/failed`, stderr limpio), `FiltroAbismo.comer`, `_pescar_abismo` (chat_id), `fuentes.chats_viejos`,
`consulta.resolver`, la PWA (`process/failed`). El re-smoke deberia mirar: una `/claude` con marca (dos invocaciones,
`Venias diciendo` sin `⟦`), una `/nube` con la conversacion activa nombrando a alguien (nada de esa conversacion en
`texto_tapado`), y el `process/failed` si el CLI llegara a fallar.

## Concerns (no bloquean el merge; para el ledger con nombre)

1. h05 queda como decision de Pedro (spec 12) con los numeros archivados; la ruta local sigue sin emitir la marca
   por su cuenta.
2. La metrica del porton cuenta como legible la copia literal del molde (22/34 en el control): re-medir con esa
   exclusion antes de decidir.
3. Divergencia declarada streaming/one-shot con foco anidado en el cuerpo (streaming consulta, one-shot retira).
4. M6 de la adversaria: tras una reinvocacion fallida el fallback local reempieza desde cero pegado al tramo (ahora
   avisado con meta y fila; "continuar, no regenerar" no se cumple en ese camino). El fallback no lleva bloques ni
   "venias diciendo"; hacerlo exige decidir que pasa con los bloques tapados de /nube en un modelo local.
5. h04 toma una decision de producto (dos regimenes) que Pedro deberia confirmar: en local, los mensajes del chat
   activo anteriores a la ventana de 12 SI se pescan.
6. `process/failed` es un evento nuevo del WS: la fabrica no pinta `process` y lo ignora; la PWA lo pinta.
