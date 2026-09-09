# Adversaria: COMPLETITUD -- rama feat/abismo-1b (c645ccd..745a7d8)

Lente: cada promesa del spec (`docs/superpowers/specs/2026-09-07-abismo-consulta-design.md`, secciones 3-11, 13, 15)
y del plan (Tasks 1-13) contra el codigo y los tests de 745a7d8. Revision de LECTURA sobre el checkout mas una
sonda propia fuera del arbol (`scratchpad/sonda_completitud.py`, borrada al terminar; su salida se transcribe abajo).
Estado del arbol al revisar: `git status` limpio, HEAD 745a7d8, rama feat/abismo-1b. Los 15 archivos de test del
abismo y vecinos: `117 passed, 4 warnings` (EXIT=0). Node en `calipso/web/fabrica/`: `# tests 412 / # pass 412 / # fail 0`.

Las lineas de `calipso/server.py` son las del checkout (se corren entre merges; el simbolo manda).

## 0. Hallazgos (solo lo que falta o esta a medias, y los minors que deben cerrarse)

| # | Severidad | Que | Evidencia |
|---|---|---|---|
| H1 | Important | **El filtro del stream no llega a punto fijo en un empalme y deja salir una marca VALIDA completa, visible y persistida, por las DOS rutas.** `⟦abismo:chats ⟦abismo:zzz nada⟧ libro⟧` sale de `FiltroAbismo.comer` como `⟦abismo:chats  libro⟧`: la ilegible de adentro se retira y los dos costados se pegan en una marca valida que ya nadie vuelve a mirar. Llega a Pedro como chunk y queda en `chats.json` (la fuente `chats` la pescaria despues). Viola "la marca JAMAS se persiste" (spec 4, constraint global) y la seccion 11 ("la marca no existe para la historia"). La rama YA cerro esta familia en las otras dos rutas de retiro (`_retirar_abismo` hasta punto fijo, T2 fix round 1) con el argumento del mapa del filtro 7.4 ("las dos rutas juzgan igual"); el filtro del stream quedo afuera y el review r1 de la T2 lo dejo flaggeado para esta ronda. | Sonda I (dos rutas), abajo. Codigo: `calipso/abismo/filtro.py:62-104` (`comer`: tras `if m is None: ... continue` el escaneo sigue desde `buf = buf[j+1:]`, sin releer el empalme). Contraste: `server.py:7364` `_retirar_abismo` itera `subn` hasta punto fijo. |
| H2 | Important | **Ruta one-shot: un prefijo `⟦abismo:` sin cerrar antes de la marca valida traga en silencio TODA la continuacion de la reentrada.** `cortar_en_marca` corta en `m.start()` de la primera valida y `tramo_crudo` ("x ⟦abismo:zzz ") entra al Emisor por `emisor.chunk` (`server.py:3657`); `FiltroAbismo` retiene el prefijo abierto (`filtro.py:85`), el texto de la SEGUNDA invocacion ("y sigo") se pega al buffer retenido en el mismo `emisor.chunk`, y `emisor.cerrar()` (`server.py:3913` -> `filtro.py:114`) descarta todo con aviso `abierta`. Pedro ve "x ", se persiste "x", y la respuesta con contexto (la que costo la segunda invocacion real) se pierde: exactamente el modo de falla que el ledger pidio mirar ("una marca valida trunca la respuesta en silencio"). En streaming el mismo texto da "x ⟦abismo:zzz y sigo" (el filtro ve el `⟧` y juzga el cuerpo). Viola "continuar, no regenerar" (spec 3) y la regla de las rutas (spec 4: misma gramatica, mismo juicio). | Sonda D (one-shot vs streaming), abajo. |
| H3 | Minor (DEBE cerrarse: ruling 5) | **`stderr.txt` de jobs es el unico artefacto que se escribe crudo.** `server.py:3110`, `:3146`, `:3161`: `jobs.write_artifact(..., "stderr.txt", stderr)` sin `_limpiar_marcas`, mientras `output.txt`, `partial-output.txt` y el `msg` del error si pasan. Ruling 5 del plan: "`_limpiar_marcas` ... limpia los artefactos de jobs". Solo muerde si el CLI real escribe texto del modelo a stderr (no verificable sin el CLI); el costo del cierre es una linea por sitio. | Sonda F: un CLI que escribe la marca a stderr deja `artifacts/stderr.txt = 'aviso ⟦abismo:chats libro⟧ del cli'`. |
| H4 | Minor | **Fallback entre suscripciones tras una reinvocacion fallida: lo persistido no es lo que Pedro leyo.** `server.py:3837` (`full, queued = await _run_subscription_text_live(...)`) y `:3846` (`full = await emisor.chunk(full)`) REASIGNAN `full`: la UI muestra "a fallback" (el tramo previo a la marca ya salio como chunk) y `chats.json`/`mem.remember` guardan "fallback". T7 lo declara "conducta preexistente del fallback", pero antes del abismo `full` estaba vacio al entrar a ese fallback (una sola invocacion), asi que la divergencia visible/persistido es NUEVA y alcanzable (spec 4, "UN solo par ... el texto visible fusionado": A MEDIAS). El fallback local, en cambio, hace `full +=` (`:3889-3903`). Puede esperar con nombre en el ledger; el cierre es `full +=` en los dos sitios. | Sonda C, abajo. |
| H5 | Minor | **El filtro de foco cosecha focos del texto DESCARTADO tras el corte** (la camara vuela a algo que Pedro no leyo). `Emisor.chunk` (`server.py:7458-7466`) corre `foco.comer` sobre el chunk ENTERO antes de que `FiltroAbismo` corte, y `_cosechar` (`:7444`) publica el foco. No es letra del spec (la invariante 7 habla de la marca del abismo); puede esperar. | Sonda E: `em.focos == ['dep:atlas']` con visible "Dejame ver ". |

No reproducidos / sin evidencia mas alla del codigo (no son hallazgos): el `EL_PULSO.publicar` de `_pescar_abismo` corre FUERA del `try` (`server.py:7576`; el `try` arranca en `:7581`); si reventara (evento desconocido) el pondering quedaria sin cierre server-side, pero "abismo" esta en `EVENTOS` y la UI cierra en `done`/`error` igual. Anotado, no reportado.

## 1. Spec seccion 3 (que decidio Pedro)

| Promesa | Codigo | Test | Estado |
|---|---|---|---|
| Marca in-band con reentrada, no `pending` | `server.py:3698-3800` (bucle exterior local/api; `pending` solo lo toca el steer) | `test_abismo_chat.py::test_una_marca_valida_corta_pesca_y_la_continuacion_sigue_en_la_misma_burbuja` | OK |
| Continuar, no regenerar (venias diciendo) | `calipso/abismo/turno.py:prompt_reentrada`; `server.py:3797-3799`, `:3691-3693` | idem; `test_abismo_turno.py::test_el_prompt_de_reentrada_lleva_bloques_mensaje_y_venias_diciendo` | OK en streaming; **A MEDIAS en one-shot: H2** |
| Marca tipada, gramatica cerrada | `calipso/abismo/marca.py` (1a) + `PATRON` sin corchete anidado | `test_abismo_marca.py`, `test_abismo_filtro.py::test_un_corchete_anidado_no_secuestra_la_marca_siguiente` | OK |
| Fuentes del dia uno (memoria, chats, proyecto) | `calipso/abismo/fuentes.py` (1a); `_pescar_abismo` inyecta `mem`, `catastro.obtener`, `_repo_brief` (`server.py:7586-7588`) | `test_abismo_chat.py::test_la_zona_y_el_consolidado_los_pone_el_server` (inyeccion) | OK |
| /nube: consulta local + viaje por anillo; contrato sin nombres; viaja solo y se muestra; sin viaje la nube sigue | `viaje.py`; `_sistema_nube` (`server.py:2736`); `_pescar_abismo` con `destino`/`mapa` | `test_abismo_nube.py` (5), `test_abismo_viaje.py` (10) | OK |
| Pondering visible en las dos UIs y en el pulso | `index.html:2360-2368`, `fabrica/chat.js:80-95`, `pulso.py:23` | `arranque.test.js` (3), `chat.test.js` (7), `test_abismo_pulso.py`, `test_abismo_chat.py::test_la_senal_del_abismo_se_publica_al_pulso` | OK |
| No toca la economia; consumo extra de suscripcion declarado | cobro fuera del bucle (`server.py:3926`); `reinvocacion_suscripcion` en telemetry (`:3695-3697`); label "(reentrada del abismo N)" (`:3640`) | `test_la_pasada_sintetica_no_repite_nada_del_turno` (cobro==1); `test_en_suscripcion_la_marca_corta...` (eventos telemetry) | OK; subfacturacion api de la pasada cortada declarada (`:3728-3733`) |

## 2. Spec seccion 4 (arquitectura)

### 2.1 Piezas y filtro

| Promesa | Codigo | Test | Estado |
|---|---|---|---|
| `ABISMO_BLOQUE_MAX = 2000`, override por env, fallo suave | `consulta.py:_entero_env` | `test_abismo_minors.py::test_el_env_mal_tipeado_no_impide_arrancar` | OK |
| `puede_viajar`: local todo; nube 1-2, jamas 3 | `anillos.py:puede_viajar` | `test_abismo_anillos.py` | OK |
| `viaje.py` puro, tres pasos en orden, `{estado,texto,tapados,motivo}`, local transparente sin juez | `viaje.py:preparar_viaje` | `test_abismo_viaje.py` (los 10) | OK |
| `consulta.py` etiqueta un solo formato compartido | `consulta.py:etiquetar`, `viaje.etiquetar` delega | `test_abismo_viaje.py::test_el_etiquetado_del_viaje_es_el_mismo_que_el_del_resolvedor[3]` | OK |
| Emisor con LISTA ordenada de filtros (foco, abismo) | `server.py:7404-7495` (`filtros=`, `chunk`, `cerrar`, `marca_abismo`) | `test_abismo_filtro.py::test_el_emisor_compuesto_retira_las_dos_marcas_y_entrega_la_del_abismo` | OK |
| Tope 160 de pregunta; retencion declarada (ruling: 409) | `filtro.py:RETENCION_MAX`; `marca.MAX_PREGUNTA` | `test_una_marca_de_200_chars_no_se_escapa_cruda`, `test_el_tope_del_cuerpo_es_el_mismo_que_el_de_patron` | OK |
| Marca inconclusa al fin del stream: se retira con aviso, no se vuelca | `filtro.py:106-118` | `test_una_marca_abierta_al_cerrar_se_descarta_con_aviso`; `test_abismo_chat.py::test_una_marca_abierta_al_fin_del_stream_no_se_vuelca`; `test_abismo_suscripcion.py::test_en_suscripcion_una_marca_abierta_al_final_no_se_vuelca` | OK (y es el mecanismo de H2) |
| Tras cada chunk el bucle mira el filtro y cierra el generador | `server.py:3762-3771` | `test_una_marca_valida_corta...` (dos llamadas, "esto no se ve" descartado) | OK |
| Filtro y `PATRON` juzgan igual QUE es una marca (mapa 7.4) | `filtro.py:_es_cuerpo_de_marca`; `_limpiar_marcas` foco-primero y punto fijo (`server.py:7498`) | `test_las_dos_rutas_de_retiro_juzgan_igual_el_empalme` (dos textos) | **A MEDIAS: H1** (un tercer texto diverge: el filtro deja armada una valida) |

### 2.2 La reentrada sintetica

| Promesa | Codigo | Test | Estado |
|---|---|---|---|
| Estado del turno junto al estado de conexion; atraviesa reentradas; solo un paquete real lo resetea | `server.py:3258` (`estado_abismo`), `:3285` (`reset()` tras `user_msg.strip()`, cubre paquete y steer) | `test_el_tope_de_tres_consultas_por_turno` (cuarto turno reseteado) | OK |
| Prompt: system base (una vez) + bloques post-compile + historial SIN parcial + venias diciendo + instruccion | `turno.py:prompt_reentrada`; `system_base = system` (`:3708`, `:3630`) | `test_una_marca_valida_corta...` (system2 startswith system1; historial `[1:3]`; "Dejame ver" no en messages[:-1]) | OK |
| /nube: system minimo + contrato; bloques del viaje ya tapados; sin historial; venias CRUDO | `_sistema_nube`; `chat_id_nube=None` (`:3485`); `tramos_crudos` (`:3666`, `:3779`) | `test_abismo_nube.py::test_en_nube_el_bloque_viaja_tapado...` (api) y `::test_en_nube_por_suscripcion_los_tramos_vuelven_crudos` (canario) | OK |
| Persistencia: UN par user/assistant, texto visible fusionado, ya filtrado; la marca jamas en chats.json ni output.txt | `server.py:3994` (`full.strip()`), `:3159` (`output.txt` limpio) | `test_una_marca_valida_corta...` (4 mensajes, crudo sin `⟦`), `test_en_suscripcion_la_marca_corta...` (output.txt sin `⟦`) | OK en el camino feliz; **H1** (empalme persiste una valida), **H4** (fallback pierde el tramo) |
| Presupuesto: `num_ctx` explicito en la llamada local | `server.py:CHAT_NUM_CTX`, `_chunks_for` payload `options` | `test_la_llamada_local_del_chat_fija_num_ctx` (y `segunda["options"]["num_ctx"]`) | OK |

### 2.3 Los catorce salteos de la pasada sintetica, uno por uno

Todo lo que esta fuera del `while True` exterior (`server.py:3711`) corre una vez por turno. Verificado sitio por sitio:

| # | Salteo | Donde corre (una vez) | Test que lo cuenta | Estado |
|---|---|---|---|---|
| 1 | `_decide` (directivas/ruta heredadas) | `server.py:3333` (antes del `try` del envio) | `test_la_pasada_sintetica_no_repite_nada_del_turno` (`decide==1`) | OK |
| 2 | `goals.detect` | `:3306` | idem (`goals==1`); spec 11 "goals no corren en la sintetica" | OK |
| 3 | `chats.append("user")` | `:3298` | `test_una_marca_valida_corta...` (un solo user nuevo) | OK |
| 4 | `mem.remember` | `:3988` (post-bucle, `full` fusionado) | idem (`recordado` len 1, sin `⟦`) | OK |
| 5 | `chats.append("assistant", parcial)` intermedio | no existe dentro del bucle; unico append `:3994` | idem (un assistant fusionado) | OK |
| 6 | `_cobrar_turno` | `:3926` | `test_la_pasada_sintetica...` (`cobro==1`) | OK |
| 7 | `costs.log_usage` + evento `cost` | `:3916`, `:3928` | idem (`cost` count 1) | OK; `usage` acumulado por pasada (`:3773-3774`) |
| 8 | `done` | `:4015` | idem (`done==1`); `test_abismo_nube.py::_turno_con_un_solo_done` (escucha tras el done) | OK |
| 9 | `thinking` | `:3304` | idem (`thinking==1`) | OK |
| 10 | `meta` | `:3497` | idem (`meta==1`) | OK |
| 11 | `chat/updated` | `:4002` | idem | OK |
| 12 | pulso `inicio`/`fin` (un solo escritorio) | `:3517`, `:3938` | idem (`inicio==1`, `fin==1`) | OK |
| 13 | `chat_turn` en telemetry (con `abismo_consultas`) | `:3942-3963` | idem (`len==1`, `abismo_consultas==1`) | OK |
| 14 | `_sistema_del_turno` (recall, economia bajo candado) | `:3557`; la reentrada usa `system_base` | idem (`system==1`) | OK |
| + | compuerta /nube del MENSAJE (`preparar_envio`) | `:3458` | `test_en_nube_solo_hondo...` (`privacidad` count 1) | OK |
| + | `emisor.cerrar()` | `:3913` | (por construccion; sin conteo directo) | OK |
| + | jobs "de turno nuevo" | no hay en local/api; en suscripcion la reinvocacion es un SEGUNDO job de proceso, declarado con etiqueta propia (`:3640`) | `test_en_suscripcion_la_marca_corta...` (dos `process/start`, output.txt de ambos limpio) | OK, declarado |

### 2.4 El flujo, corregido (pasos 1-6)

| Paso | Codigo | Test | Estado |
|---|---|---|---|
| 2. Validacion PRE-corte: solo la valida corta; ilegible/desconocida se retira con aviso sin corte | `filtro.py:95-101` | `test_una_marca_ilegible_se_retira_con_aviso_y_sin_corte`; `test_abismo_chat.py::test_una_marca_ilegible_se_retira_sin_cortar` | OK |
| 3. Valida: retiro, senal `pondering`, cierre del generador | `server.py:3762-3771`; `_pescar_abismo` `:7571` | `test_una_marca_valida_corta...` | OK |
| 4. Fallos POST-corte: reentrada sin bloque, aviso, `fallo` | `_pescar_abismo` (`try` `:7581-7597`, `motivo`), `server.py:3793-3800` | `test_la_pesca_vacia_es_fallo...`, `test_una_consulta_que_revienta...` | OK |
| 5. Sub-bloques al estado; pasada sintetica | `:7613` (`estado.bloques.append`), `:3796` | idem | OK |
| 6. `pescado` con `tamano` (+ `viaje`); continuacion en la misma burbuja | `:7617-7621`; UIs | idem; `arranque.test.js` ("la continuacion abrio otra burbuja") | OK |

### 2.5 Regla de las rutas

| Promesa | Codigo | Test | Estado |
|---|---|---|---|
| Local y API: corte en vivo (en /nube /api tambien, con viaje) | bucle `:3698-3800`; `destino` (`:3710`) | `test_una_marca_valida...`; `test_abismo_nube.py` (`/nube /api`, 3 tests) | OK |
| Suscripcion: detector con la MISMA regex; primera valida corta; preview congelado; proceso a termino; reinvocacion completa; dos invocaciones declaradas | `turno.py:cortar_en_marca/prefijo_congelado` (PATRON); `_run_subscription_text_live(congelar=)` `:3066-3078`; bucle one-shot `:3630-3697` | `test_en_suscripcion_la_marca_corta_congela_el_preview_y_reinvoca` (parciales, 2 llamadas, telemetry) | OK; **H2** (el juicio del Emisor sobre `tramo_crudo` diverge del streaming) |
| `/stop` durante el CLI ni pesca ni reinvoca | `:3117-3120` ("/stop" como segundo valor), `:3667-3673` | `test_un_stop_durante_el_cli_no_pesca_ni_reinvoca` | OK |
| Orquestador FUERA: marcas de agentes retiradas via `_limpiar_marcas` CON aviso | `server.py:2516` (`_retirar_con_aviso` + `_limpiar_marcas`); sintesis con `apagada` (`:3618`) | `test_el_agente_de_equipo_no_publica_la_marca_del_abismo_al_pulso`; sonda B (sintesis via ws_chat) | OK; minor: con `⟦abismo:chats ⟦foco:x⟧ p⟧` el aviso se pierde (T7 r0 #2), puede esperar |
| Tope 3 por turno; bajo el tope corta; alcanzado retira sin corte y el texto posterior vale | `turno.py:puede_cortar`; `filtro.py:98-101` (`sin_corte`); one-shot `:3649-3651` | `test_el_tope_de_tres_consultas_por_turno`; `test_en_suscripcion_la_cuarta_marca_no_corta` | OK |
| Fallo cerrado en todo; sin marca el filtro es transparente byte a byte | `_pescar_abismo` try/except; `filtro.py` | `test_sin_marca_es_transparente_byte_a_byte`; `test_un_turno_plano_da_thinking_chunks_y_un_solo_done` | OK |

## 3. Spec seccion 5 (gramatica y contrato)

| Promesa | Codigo | Test | Estado |
|---|---|---|---|
| Regex unica compartida por filtro y detector; sin fallback de fuente | `marca.PATRON`; `turno.cortar_en_marca` usa `PATRON`+`parsear`; filtro decide con `parsear` | `test_abismo_marca.py`, `test_abismo_turno.py::test_cortar_en_marca_corta_en_la_primera_valida` | OK |
| Contrato interno suma sintaxis + indice (<= 600) y cambia el system de TODOS los turnos | `prompt_compiler.py:internal_contract` (ultimo bloque); `catastro.nombres()` sin escaneo | `test_abismo_contrato_vivo.py` (3), `test_abismo_minors.py::test_el_trim_del_contrato_nunca_corta_el_cierre` | OK |

## 4. Spec seccion 6 (anillos)

| Promesa | Codigo | Test | Estado |
|---|---|---|---|
| 1-2 viajan redactados; 3 nunca ni tapado; credencial corta el envio entero | `viaje.py` pasos 1-2 | `test_a_la_nube_lo_hondo_se_descarta_antes_del_juez`, `test_credencial_en_cualquier_sub_bloque_falla_cerrado_el_envio_entero`, `test_solo_hondo_falla_cerrado_sin_juez` | OK |
| El juez solo hunde ("se hunde a 3") | superado por la enmienda: tapa o corta, no cambia anillo (docstring de `preparar_viaje`) | idem | OK, declarado |
| Consolidado del libro personal solo en zona personal | `_zona_del_chat`, `_consolidado_personal` (`server.py:7523-7546`) | `test_la_zona_y_el_consolidado_los_pone_el_server` | OK |
| Bloque efimero: jamas en chats.json ni memoria | `estado_abismo.reset()`; nada lo escribe | `test_en_nube_el_bloque_viaja_tapado...` ("Lo que subio" no en chats.json/recordado/telemetry) | OK |

## 5. Spec seccion 7 (fuentes)

| Promesa | Codigo | Test | Estado |
|---|---|---|---|
| `memoria`: recall dirigido, ambito ELEGIBLE, core y cronologia anillo 3 | `fuentes.memoria` (1a) llama `mem.recall(pregunta, n=...)` SIN `ambitos` | -- | **A MEDIAS, declarado** (plan "Huecos declarados": "ambito elegible" queda para cuando la marca traiga senal de ambito). Puede esperar: residual de Pedro |
| `chats`: lexica + desde/hasta, anillo 2 | `fuentes.chats_viejos` (1a) | tests del 1a; `_sembrar_chat_viejo` en todo el harness | OK |
| `proyecto`: brief por nombre, anillo 1 | `fuentes.proyecto` (1a); inyeccion de `obtener`/`brief` | fixture `chat` cierra `catastro.obtener` | OK |

## 6. Spec seccion 8 (/nube)

| Promesa | Codigo | Test | Estado |
|---|---|---|---|
| 8.1 Contrato sin nombres + linea de marcadores en el system minimo; contrato segundo | `_NUBE_ABISMO_MARCADORES`, `_sistema_nube` (`server.py:2729-2746`); `_sistema_del_turno` | `test_el_system_de_nube_lleva_el_contrato_sin_nombres`; `test_privacidad_nube_system.py`; `test_en_nube...` (system2), `test_en_nube_por_suscripcion_los_tramos_vuelven_crudos` (`llamadas[0]["sistema"]`) | OK (los dos fallbacks recompilan con `_sistema_del_turno(..., a_la_nube_tapado)`: tambien sin nombres) |
| 8.2 La excepcion a la compuerta es UNA: el bloque entra por `prompt_reentrada` y nada mas | los cuatro `if ... and not a_la_nube_tapado` intactos (`:3580-3583`, `:3597-3600`, `:3832-3835`, `:3884-3887`); bloques solo en `prompt_reentrada` | `test_en_nube_el_bloque_viaja_tapado...` (system2 = minimo + contrato + bloque; roles `[system, user]`) | OK |
| 8.3 Degradado avisado: `pescado` con `viaje` (destino, tapados, texto_tapado) | `_pescar_abismo` `:7617-7621` | `test_en_nube_el_bloque_viaja_tapado...` (api). Suscripcion /nube: `viaje` NO afirmado (ledger T8) | OK; la asercion faltante en suscripcion puede esperar (mismo `_pescar_abismo`) |
| 8.4 Sin viaje la nube sigue: reentrada sin bloque (streaming) / texto posterior vale sin reinvocar (one-shot) | `:3784-3800` (comentario y reentrada); `:3679-3689` (`hubo_bloque False`) | `test_en_nube_una_credencial...` y `::test_en_nube_solo_hondo...` (api: 2 llamadas, segunda sin encabezado); `::test_en_nube_por_suscripcion_un_bloque_que_no_viaja_no_reinvoca` (1 llamada) | OK, con la aclaracion escrita en el spec (diff del spec, punto 4) |
| Suscripcion en /nube: detector sobre el texto entero; preview congelado; reinvocacion; dos invocaciones declaradas | bucle one-shot | `test_en_nube_por_suscripcion_los_tramos_vuelven_crudos` | OK |
| Venias diciendo CRUDO por las DOS rutas | suscripcion: `tramos_crudos.append(retirar_marcas(tramo_crudo))` (`:3666`), `visible = reponer(...)` (`:3655`); api: `tramos_crudos.append(tramo)` (`:3779`), sin reponer en vivo (preexistente) | suscripcion: canario (`"Venias diciendo: Le dije a [ID_1] que "` en `llamadas[1]["prompt"]`, "Marta" en ningun envio); api: `test_en_nube_el_bloque_viaja_tapado...` (`"Venias diciendo: Le dije a [ID_1] que "` en el segundo mensaje) | OK en las dos (en api crudo==visible porque la rama no repone: preexistente, declarado). Minor: en one-shot el crudo conserva marcas de foco (asimetria con streaming), puede esperar |
| Latencia sin techo; el pondering la hace visible | juez en hilo (`:7591`), sin timeout | -- (por diseno) | OK |

## 7. Spec seccion 9 (la senal)

| Promesa | Codigo | Test | Estado |
|---|---|---|---|
| Tres fases con cierre garantizado; motivos de la lista cerrada | `turno.py:senal/MOTIVOS`; `_pescar_abismo` (todo camino termina en `fallo` o `pescado`) | `test_la_senal_lleva_los_campos_fijos_de_cada_fase`; `test_los_motivos_reales_del_viaje_sobreviven_a_la_senal`; cierre por salida: excepcion (`test_una_consulta_que_revienta...`), steer durante pesca (`test_el_steer_de_pedro_gana_durante_la_pesca`), tope (sin pondering: `test_el_tope...`), EOF (sin pondering: `..._abierta_al_fin_del_stream...`), juez caido/credencial/solo hondo (`test_abismo_nube.py`, `test_abismo_viaje.py`), modelo caido en la reentrada (sonda G: `pescado` y luego `error` + un `done`), steer con el corte (sin pondering: `test_el_steer_que_llega_con_el_corte_no_llega_a_pescar`), /stop en CLI (sin pondering: `test_un_stop_durante_el_cli...`), texto encolado en CLI (sonda H) | OK en todas las salidas ejercitadas |
| Renglon HERMANO del pensando en las dos UIs, nunca un mensaje ni un turno; segundos en el cliente; detalle desplegable con destino nube | PWA: `index.html:2475-2512` (`abismoEl` div en `messages`, `botEl` intacto; `addDetalleViaje` via `addDetail`); fabrica: `chat.js:80-95` (campo `abismo`, no turno), `app.js:pintarAbismo` (nodo `#abismo` fuera de `#conversacion`, `<details>`) | `chat.test.js` (7: no agrega turnos, n, apagados), `arranque.test.js` (3: sin nodos nuevos, detalle nube, sin reescrituras); PWA sin test de DOM (test_ui.py substrings; smoke) | OK. Nota: la PWA agrega un `addMsg("meta", ...)` en pescado/fallo (una linea meta como las de ruta, no burbuja ni turno; no se persiste): lectura del plan, T10/T13 |
| "Queda aviso" = fila en telemetry + fase `fallo` | `_avisar_abismo`, `_pescar_abismo` log_event | `test_el_aviso_por_defecto_deja_fila_en_telemetry_sin_el_texto` | OK |
| Pulso: `EVENTOS` y `CONOCIDOS` juntos; `case "abismo"` | `pulso.py:23`, `pulso.js:36`, `:94` | `test_abismo_pulso.py` (acople), `pulso.test.js` | OK |

## 8. Spec seccion 10 (steering)

| Momento | Codigo | Test | Estado |
|---|---|---|---|
| Con el corte (ya en cola) | `server.py:3780-3783` (`sintetica=True; continue` -> tope del bucle `:3712-3725`, fila `momento="pesca"`) | `test_el_steer_que_llega_con_el_corte_no_llega_a_pescar` | OK (minor: la etiqueta `pesca` cubre dos situaciones, ledger T6) |
| Durante la pesca: bloque descartado, `fallo`, aviso | `_pescar_abismo` `:7598-7601` (mira `inbox` al volver) | `test_el_steer_de_pedro_gana_durante_la_pesca` (fases, orden con `steered`, sin reentrada, `abortada_por_steer`) | OK |
| Durante la reentrada | `:3746-3752` (fila `momento="reentrada"`) | `test_el_steer_durante_el_stream_de_la_reentrada_deja_su_aviso` | OK |
| One-shot: texto encolado / `/stop` | `:3667-3673` (`momento="cli"`) | `test_un_stop_durante_el_cli...`; sonda H (texto) | OK |
| No usa `pending` | solo el steer asigna `pending` | por construccion | OK |

## 9. Spec seccion 11 (casos borde)

| Caso | Codigo | Test | Estado |
|---|---|---|---|
| Marca abierta al EOF | `filtro.py:cerrar` | tres tests (2.1) | OK |
| chats.json: texto visible fusionado, filtrado | `:3994` | `test_una_marca_valida...` | OK salvo **H1** (empalme) y **H4** (fallback) |
| Modos con pipeline propio afuera (`/redacta`, `/otra`, `/mia`, `/plan`, `/team`, orquestador) | `/redacta`/`/otra`: `Emisor(ws)` sin abismo y system propio (`:3386`); `/mia` sin modelo; orquestador `apagada` (`:3618`); solo `_build_context` ensena el contrato (`prompt_compiler.py:224`) | `test_el_emisor_con_solo_foco_sigue_volcando_lo_retenido`; sonda B | OK; declarado: los agentes del orquestador heredan el contrato por `base_system` (T7 riesgos) -> consultan al vacio y se retira con aviso |
| Turno /nube | seccion 8 | `test_abismo_nube.py` | OK |
| Goals no corren en la sintetica | `goals.detect` `:3306` fuera del bucle | `test_la_pasada_sintetica...` | OK |

## 10. Spec seccion 13 (invariantes)

| # | Invariante | Codigo | Test | Estado |
|---|---|---|---|---|
| 1 | Resolvedor 100% local | `_pescar_abismo` -> `abismo_consulta.resolver` en hilo; juez local | `test_en_nube_solo_hondo...` ("Cordoba" en ningun envio) | OK |
| 2 | Bloque jamas a la nube sin viaje; jamas se persiste | `preparar_viaje` antes de `bloques.append`; solo `prompt_reentrada` | `test_abismo_nube.py` (5); `test_la_senal_del_abismo_se_publica_al_pulso` (al pulso solo `tamano`) | OK |
| 3 | Sin marca, bytes identicos | `filtro.py` | `test_sin_marca_es_transparente_byte_a_byte`; `test_un_turno_plano...` | OK |
| 4 | Fallo cerrado; todo pondering cierra | `_pescar_abismo`; `consulta.resolver` armado dentro del try | 2.4, seccion 7 de esta tabla; `test_una_fuente_que_devuelve_basura_es_fallo_suave` | OK |
| 5 | No toca la economia; cobro una vez; extra de suscripcion declarado | `:3926` fuera del bucle; `reinvocacion_suscripcion` | `test_la_pasada_sintetica...` | OK |
| 6 | El juez solo hunde; credencial corta el envio entero | `viaje.py` | `test_credencial_en_cualquier_sub_bloque...`, `test_en_nube_una_credencial...` (api y one-shot) | OK |
| 7 | La marca que no salio del filtro no actua; las de agentes se retiran con aviso | solo el bucle consume `marca_abismo()`; orquestador `_retirar_con_aviso` | `test_el_agente_de_equipo...` | OK como "no actua"; **H1** deja una marca VISIBLE (no actua, pero existe para Pedro y para la historia) |
| 8 | Solo un mensaje real resetea; el steer gana | `:3285`; seccion 8 de esta tabla | `test_el_tope...` (cuarto turno) | OK |
| 9 | Lo que vuelve a la nube es crudo; contrato sin nombres | seccion 6 de esta tabla | canario + `test_el_system_de_nube...` | OK |

## 11. Spec seccion 15 (verificacion)

| Promesa | Donde | Estado |
|---|---|---|
| Paquete en aislado con `CALIPSO_HOME` tmp | conftest raiz + `tmp_path` en cada fixture | OK |
| Tests: gramatica, transparencia, tope, fallo cerrado con cierre, carrera steering, no-persistencia, salteos, zona | enumerados arriba (test_abismo_marca/filtro/chat) | OK |
| `viaje.py` en aislado (5 casos) + turno /nube por TestClient (7 afirmaciones) | `test_abismo_viaje.py`, `test_abismo_nube.py` | OK; "preview de suscripcion congelado en la primera marca" se afirma en `/claude` (no en `/nube /claude`): puede esperar |
| El molde que faltaba: `ws_chat` con modelo falso | `test_abismo_chat.py` (Harness, ModeloEspia) | OK (minor: `Harness.recibir` sin plazo, `test_abismo_chat.py:111-118`) |
| Suite + node antes de cada commit | ledger por task; verificado hoy: 117 passed (abismo), node 412/412 | OK |
| Porton corrido antes del 1b | 1a (v2 PASA) | OK |
| Smoke en vivo con server desechable; review final cazando fugas | Task 13 (en curso, otro agente) | pendiente por diseno |

## 12. Los sumideros, uno por uno (la marca y el bloque)

| Sumidero | Codigo | Limpio | Test | Estado |
|---|---|---|---|---|
| `chats.json` (assistant) | `server.py:3994` `full.strip()` (visible filtrado) | si | `test_una_marca_valida...`, `test_en_nube...` (`⟦` y "Lo que subio" ausentes) | OK salvo H1/H4 |
| `mem.remember` | `:3988` (`full.strip()`) | si | `recordado` sin `⟦`/"Lo que subio" | OK |
| `telemetry.jsonl` `chat_turn` | `:3942` (sin texto: `response_chars`) | si | "cocina"/"Ana"/"ghp_" ausentes en el jsonl | OK |
| `telemetry.jsonl` `abismo` | `_pescar_abismo` (fuente, chars, tapados=len) / `_avisar_abismo` (clase, largo, sin cuerpo) | si | `test_el_aviso_por_defecto_deja_fila...` ("memorai" ausente); nube: "ghp_" ausente | OK |
| `output.txt` | `:3159` | si | `test_en_suscripcion_la_marca_corta...` (ambos jobs) | OK |
| `partial-output.txt` | `:3107`, `:3143` | si | sin test (ledger T7) | OK por codigo |
| `stderr.txt` | `:3110`, `:3146`, `:3161` | **NO** | sonda F | **H3** |
| `jobs.update(error=)`, `jobs.event(error=)`, `fallbacks[].error` | `:3135-3137` (`msg` limpio) | si | sin test (ledger T7) | OK por codigo |
| preview `process/running.partial` | `:3066-3078` (congelado, `recortar_abierta`, `_limpiar_marcas`) | si | parciales en `test_en_suscripcion_la_marca_corta...` | OK |
| `jobs.event("running")` | `:3080-3083` (solo elapsed/tokens) | n/a | -- | OK |
| pulso `razonando` | `Emisor._soltar` (`:7439`, `texto=visible`); orquestador `:2516` | si | `test_el_agente_de_equipo...`; `test_la_senal_del_abismo...` (claves del evento) | OK |
| system `.md` (`--append-system-prompt-file`, lleva el BLOQUE) y `.prompt.md` de ROOT | `finally` `:3180` (`_cleanup_subscription_files`) | borrados | `test_los_archivos_temporales_de_las_dos_invocaciones_se_borran` | OK |
| `.stdout`/`.stderr` temporales del CLI | `finally` `:3174-3177` (`unlink`) | borrados | -- (codigo) | OK |
| stderr del server | `:7597` (`print(... {exc})`: solo la excepcion) | n/a | -- | OK |
| DOM de las UIs | PWA `addDetalleViaje` (texto tapado, escapado); fabrica `<pre>` por `textContent` | tapado | `arranque.test.js` | OK (minor: la fabrica no vacia el `<pre>` al apagarse; queda oculto, ya tapado y ya visto) |

## 13. Las dos UIs, promesa por promesa

| Promesa | PWA (`calipso/web/index.html`) | Fabrica (`calipso/web/fabrica/`) | Estado |
|---|---|---|---|
| Renglon hermano del pensando, nunca un turno | `startAbismo` (`:2475`): div `.abismo` en `messages`, `stopThinking()`; `botEl` no se toca | `chat.js:80-95` campo `abismo`; `app.js:pintarAbismo` sobre `#abismo` fuera de `#conversacion` | OK |
| Misma burbuja | `chunk`: `if (!botEl) botEl = addMsg(...)` (botEl vive) | `case "chunk"` intacto (ultimo turno abierto) | OK (`arranque.test.js` lo custodia en la fabrica; PWA por smoke) |
| Segundos en el cliente | `tick` cada 1 s (`:2484-2489`) | `abismoTimer` en `app.js` (`n` distingue consulta nueva de repintado) | OK |
| Detalle desplegable del viaje (destino nube) | `addDetalleViaje` (`:2508`) via `addDetail` (escapa) | `#abismo-viaje` `<details>` + `<pre>` por `textContent` | OK |
| Cierre: `done`/`error`/`steered`/`onclose`/cargar historial | `:2420`/`:2418`/`:2359`/`:2429`/`renderHistory :2178` | `chat.js:73` (done), `:112` (error), `cargar` `:202`, `thinking` `:59`; `steered` cae en default y lo cierra el `done` del turno interrumpido | OK |
| Fase desconocida: fallo cerrado | `else` -> `stopAbismo` + meta (una fase inventada cerraria el renglon: aceptable) | `case "abismo"` no toca nada | OK |
| `sw.js` a v4 | `CACHE = "calipso-shell-v4"` | -- | OK |

## 14. El plan, Task por Task (Produces contra el codigo)

| Task | Produce | Estado |
|---|---|---|
| 1 | Harness (`chat`, `ModeloEspia`, `Harness.turno/recibir/paquete/mensajes/telemetria`, `de_tipo`, `texto_visible`); `CHAT_NUM_CTX`; payload `options` | OK (`test_abismo_chat.py`, `server.py:_chunks_for`) |
| 2 | `filtro.py` (`comer/cerrar/tomar_marca/tomar_avisos`, `RETENCION_MAX`); `Emisor(filtros=, avisar=)`, `marca_abismo`; `_avisar_abismo`, `_retirar_con_aviso`; `_limpiar_marcas` dos gramaticas; `PATRON` sin corchete anidado | OK (+ `_retirar_abismo` punto fijo del fix round 1); **H1** es el hueco de la misma familia en el filtro |
| 3 | `puede_viajar` real; `viaje.py` (`etiquetar`, `preparar_viaje`) | OK |
| 4 | `turno.py` (`EstadoTurno` con `apagada`, `prompt_reentrada` con `mensaje`, `senal`, `motivo_de_consulta`, `cortar_en_marca`, `prefijo_congelado`, `retirar_marcas`, `recortar_abierta`) | OK (desvios declarados en el brief) |
| 5 | `catastro.nombres()`; contrato al final de `internal_contract`; `_NUBE_ABISMO_MARCADORES`, `_sistema_nube`; `test_privacidad_nube_system.py` reescrito | OK |
| 6 | `estado_abismo` + reset; Emisor con tuberia; `_zona_del_chat`, `_consolidado_personal`, `_pescar_abismo`; bucle exterior; `apagada` en orquestador y dos fallbacks; `chat_turn.abismo_consultas`; telemetry `consulta`/`abortada_por_steer` | OK; los tres `apagada` sin test en el arbol: sondas A y B los confirman en verde |
| 7 | `congelar`; preview congelado + `recortar_abierta`; "/stop" como segundo valor; `queued_msg` sin "/stop"; `msg` limpio; artefactos limpios; bucle one-shot; `reinvocacion_suscripcion`; `momento="cli"`; label de reentrada; `cli_falso` | OK salvo `stderr.txt` (**H3**) y el juicio del `tramo_crudo` (**H2**) |
| 8 | `test_abismo_nube.py` (5) + aclaracion del 8.4 en el spec | OK (spec diff presente) |
| 9 | `EVENTOS`/`CONOCIDOS` + `abismo` en `vacio`; tres `publicar`; tests | OK |
| 10 | PWA: CSS, `startAbismo/stopAbismo/textoDeAbismo/addDetalleViaje`, ramas, `onclose`, `renderHistory`; `sw.js` v4; `test_ui.py` | OK |
| 11 | `estado.abismo`, `EVENTOS_DEL_STREAM`, `textoDeAbismo`, `#abismo` + `<details>`, `pintarAbismo`, CSS (con `max-height` declarado) | OK |
| 12 | `_entero_env`; armado dentro del try; cola honesta corta + variante sin nombres; `_ruta_de_salida`; tests | OK |
| 13 | smoke + ronda + merge | en curso (este informe es parte) |

## 15. Sondas corridas y sus salidas

Archivo: `/tmp/claude-1000/.../scratchpad/sonda_completitud.py` (fuera del arbol; `CALIPSO_HOME` a un temporal antes del import; reusa `chat`, `de_tipo`, `texto_visible`, `_sembrar_chat_viejo` de `test_abismo_chat.py` y `cli_falso` de `test_abismo_suscripcion.py`; un CLI propio `_cli_a_medida` para C y F). Comando: `cd /var/home/pedro/calipso && .venv/bin/python -m pytest -q -p no:cacheprovider -s <sonda>`. Resultado: `6 failed, 5 passed` (A, B, D-streaming, G, H en verde; C, D-one-shot, E, F, I-streaming, I-one-shot en rojo = reproducciones). Cada test afirma lo que el spec promete.

- **A** (fallback local con marca, ruta `/api` con `_sse_text_chunks` reventando; local devuelve `a ⟦abismo:chats libro⟧ b`) -- PASA:
  `A tipos: ['thinking', 'meta', 'meta', 'chunk', 'cost', 'chat', 'done']`, `A visible: 'a  b'`, telemetria `[{'kind': 'abismo', 'evento': 'retirada', 'clase': 'sin_corte', 'fuente': 'chats', 'largo': 11}]`. El `apagada` del fallback local (`:3888`) hace lo que promete.
- **B** (orquestador via ws_chat, sintesis `a ⟦abismo:chats libro⟧ b`) -- PASA: `B tipos: ['thinking', 'meta', 'chunk', 'cost', 'chat', 'done']`, `B visible: 'a  b'`. El `apagada` del orquestador (`:3618`) hace lo que promete.
- **C** (reinvocacion que sale con exit 1; `_best_subscription_client` -> codex; codex devuelve "fallback") -- FALLA (H4):
  `C tipos: ['thinking', 'meta', 'process', 'process', 'chunk', 'abismo', 'abismo', 'process', 'meta', 'process', 'process', 'chunk', 'cost', 'chat', 'done']`, `C visible: 'a fallback'`, `C persistido: 'fallback'`, `C fases: ['pondering', 'pescado']`, `C metas: [None, 'fallback entre suscripciones']`. `AssertionError: assert 'fallback' == 'a fallback'`.
- **D-streaming** (`x ⟦abismo:zzz ⟦abismo:chats libro⟧ fin` + reentrada "y sigo") -- PASA: `D-stream visible: 'x ⟦abismo:zzz y sigo'`, fases `['pondering', 'pescado']`.
- **D-one-shot** (mismo texto por `/claude`) -- FALLA (H2): `D-oneshot visible: 'x '`, fases `['pondering', 'pescado']`, `llamadas: 2`, telemetria `[('consulta', None), ('reinvocacion_suscripcion', None), ('retirada', 'abierta')]`, `persistido: 'x'`. `assert 'x '.endswith('y sigo')` -> False.
- **E** (Emisor compuesto, chunk `Dejame ver ⟦abismo:chats libro⟧ y ⟦foco:atlas⟧ miro`) -- FALLA (H5): `E visible: 'Dejame ver ' marca: Marca(fuente='chats', resto='libro') focos: ['dep:atlas']`.
- **F** (CLI que escribe `aviso ⟦abismo:chats libro⟧ del cli` a stderr, exit 0) -- FALLA (H3): `F stderr.txt: <home>/projects/var-home-pedro-calipso/jobs/job_626de2ab8db4/artifacts/stderr.txt True 'aviso ⟦abismo:chats libro⟧ del cli'`.
- **G** (modelo local revienta en la SEGUNDA llamada, la reentrada) -- PASA: `G tipos: ['thinking', 'meta', 'chunk', 'abismo', 'abismo', 'error', 'cost', 'chat', 'done']`, `G visible: 'a ' persistido: 'a'`. La senal cerro en `pescado` antes del `error`; un solo `done`.
- **H** (texto de Pedro encolado durante un CLI cuya salida trae marca valida + " tarde") -- PASA: `H visible: 'Dejame ver  tardehola Pedro'` (el segundo turno es el steer, por local), telemetria `[('abortada_por_steer', 'cli', None), ('retirada', None, 'posterior')]`, `llamadas: 1`, `done` x2, sin eventos `abismo`.
- **I-filtro / I-streaming / I-one-shot** (`a ⟦abismo:chats ⟦abismo:zzz nada⟧ libro⟧ b`) -- FALLA (H1):
  `I filtro solo: 'a ⟦abismo:chats  libro⟧ b' marca: None avisos: [{'clase': 'ilegible', 'largo': 8}]`;
  `I-stream visible: 'a ⟦abismo:chats  libro⟧ b'`, `fases: []`, `marcas en lo visible: [Marca(fuente='chats', resto='libro')]`, `chats.json tiene ⟦: True | persistido: 'a ⟦abismo:chats  libro⟧ b'`;
  `I-oneshot chats.json tiene ⟦: True` (mismo visible: `cortar_en_marca` tampoco la ve y el texto entero pasa por el mismo filtro).

## 16. El ledger: "minor (deferred)" y rulings, clasificados

DEBE = cerrar antes del merge; ESPERA = puede esperar (con nombre en `ledger.md`).

### Lo que contexto-13 pidio mirar con intencion

| Item | Veredicto | Razon |
|---|---|---|
| Los `estado_abismo.apagada = True` (hoy tres: `:3618`, `:3836`, `:3888`; el cuarto lo reemplazo el one-shot) sin test | ESPERA | Sondas A y B en verde: el codigo hace lo prometido; el hueco es de regresion. Las dos sondas son tests listos (cero costo si la ola toca `server.py`) |
| El bucle one-shot nunca consume `emisor.marca_abismo()` | ESPERA | Verificado: `tramo_crudo` nunca trae una valida (corta en `m.start()`), el tope va por `puede_cortar()` antes del Emisor (`:3649`), el resto posterior por `_retirar_con_aviso` (`:3686`). No queda filtro cortado colgado. Lo que SI queda colgado es el prefijo abierto: **H2 (DEBE)** |
| `FiltroAbismo.comer` caso de empalme fail-closed | **DEBE** | No es fail-closed: **H1** deja salir una marca valida completa (visible y persistida) |
| Foco cosechado del texto descartado | ESPERA | H5, reproducido; no es letra del spec; efecto: la camara vuela una vez de mas |
| `stderr.txt` sin `_limpiar_marcas` | **DEBE** | H3; ruling 5; tres lineas |
| `tramos_crudos` en suscripcion sin filtrar (foco) | ESPERA | El "venias diciendo" one-shot conserva `⟦foco:...⟧`; el modelo relee su propia marca de foco; inocuo (el filtro la retira otra vez) |
| Senal `pescado` con `viaje` no afirmada en suscripcion /nube | ESPERA | Mismo `_pescar_abismo` que la ruta api (afirmada); una asercion en `test_en_nube_por_suscripcion_los_tramos_vuelven_crudos` |
| `pintarAbismo` no limpia `viajeAbismoTexto` al apagarse | ESPERA salvo smoke (ruling 1) | `app.js:1118-1124`: queda texto YA tapado y ya visto en un `<details>` oculto; el proximo `pescado` lo pisa o lo vacia |
| PWA: hueco visual entre `pescado` y el primer chunk | ESPERA salvo smoke (ruling 1) | `index.html:2363-2366`: `stopAbismo` sin `startThinking`; el spec no promete un "pensando" durante la reentrada |
| `Harness.recibir` sin plazo | ESPERA | `test_abismo_chat.py:111-118`; un `done` de menos cuelga la suite; molde con plazo ya escrito en `test_abismo_nube.py::_lo_que_siga` |
| Subfacturacion api de la pasada cortada | ESPERA | Declarada en `:3728-3733`; invariante 5 la admite |
| `/nube /api` streamea marcadores sin reponer | ESPERA | Preexistente y fuera del plan |
| Steer JSON de la PWA crudo a `pending` | ESPERA | Preexistente y fuera del plan |
| `memoria` sin ambito | ESPERA | Spec 7 A MEDIAS, declarado como hueco; residual de Pedro |

### Minors por task (progress.md)

| Task | Minor | Veredicto | Razon |
|---|---|---|---|
| T1 | 8192 dos veces (`CHAT_NUM_CTX` y el literal de `_pensar_local`) | ESPERA | duplicacion; sin efecto |
| T1 | `_decide_local` con `ranked=[]` (`meta.note` siempre None) | ESPERA | harness |
| T2 | `_retirar_con_aviso` pone `largo: 0` | ESPERA | campo informativo |
| T2 | `abismo_filtro` importado sin uso hasta T6 | ESPERA | ya usado |
| T2 | `_cosechar` decide por `hasattr` | ESPERA | estilo |
| T2 | docstring de `_avisar_abismo` con cuatro comillas | ESPERA | cosmetico |
| T2 | empalme del filtro | **DEBE** | H1 |
| T2 | `marca.encontrar` de una sola pasada (fail-closed a proposito) | ESPERA | usado por el banco y `cortar_en_marca`; con H1 cerrado en el filtro, revisar si el detector one-shot deberia releer el empalme (hoy lo cubre el Emisor... que es justo H1) |
| T3 | destino desconocido reporta `solo_hondo` | ESPERA | typo del cableado; hoy `destino` sale de dos literales |
| T3 | `except` sin detalle en `preparar_viaje` | ESPERA | fallo cerrado |
| T3 | `fuente=""` por defecto | ESPERA | T6 pasa `fuente` (`:7592`) |
| T4 | `_ABIERTA_AL_FINAL` re-declara la clase de `PATRON` sin acople | ESPERA | un test de acople barato |
| T4 | `recortar_abierta` no recorta prefijos mas cortos que `⟦abismo:` | ESPERA | se ve un tic, como foco |
| T4 | passthrough de `senal` sin test | ESPERA | -- |
| T5 | docstring de `_sistema_nube` vs comentario ("tercero de ocho" / "cuarta seccion") | ESPERA | texto |
| T5 | `===` anidado dentro de "Contrato interno" | ESPERA | letra medida |
| T5 | `internal_contract` resuelve dos homes | ESPERA | -- |
| T5 | `test_privacidad_nube_system.py` se compara contra si mismo | ESPERA | el contenido lo afirma `test_abismo_contrato_vivo.py`; la asercion `startswith(_SISTEMA_NUBE_MINIMO)` ya no es vacua |
| T6 | `momento="pesca"` etiqueta dos situaciones | ESPERA | telemetry; `consultas=0` distingue el caso |
| T6 | los `apagada` sin test | ESPERA | sondas A/B verdes |
| T6 | barge-in triplicado | ESPERA | estructura |
| T6 | `_pescar_abismo` devuelve bool que nadie lee | ESPERA | el one-shot si lo lee (`:3675`) |
| T6 | fila `pescado` con campos sin test | ESPERA | -- |
| T7 | `stderr.txt` crudo | **DEBE** | H3 |
| T7 | aviso del retiro del orquestador se pierde con foco anidada | ESPERA | misma familia que H1; "se ignoran con aviso" A MEDIAS solo en ese texto |
| T7 | `tramos_crudos` sin filtrar | ESPERA | ver arriba |
| T7 | bucle one-shot no consume `marca_abismo()` | ESPERA | ver arriba (lo que muerde es H2) |
| T7 | huecos de test `partial-output.txt` y `msg` del CLI | ESPERA | codigo limpio por lectura |
| T7 | comentario duplicado `:2547`; primer test acoplado al reloj | ESPERA | -- |
| T8 | par unico sin afirmar en /nube; "dos llamadas" en desempaque | ESPERA | `len==4`/desempaque ya lo implican |
| T8 | `viaje` no afirmado en suscripcion | ESPERA | ver arriba |
| T8 | `/nube /api` sin reponer; mapa sin barrido | ESPERA | preexistentes |
| T9 | guardia repetida x3; test con dos escenarios; chat sin edificio no cuelga de escritorio | ESPERA | aceptados (rebanada 3) |
| T10 | hueco visual; `test_ui.py` substrings; `ABISMO_VERBOS` duplicado; `chunk` no apaga el pondering; tick fuerza scroll | ESPERA (hueco: salvo smoke) | el `chunk` de la reentrada llega DESPUES de `pescado`/`fallo`, que ya apagaron; la asimetria no muerde |
| T11 | pondering sobrevive a la caida del socket hasta el `thinking` siguiente; test de fase inventada; reloj sin test; `textContent` getter global; DOM sucio | ESPERA (DOM sucio: salvo smoke) | decisiones del brief |
| T12 | tmp huerfano por corrida; test del banco una env; test del env no ejerce la linea; fallback del trim inalcanzable | ESPERA | -- |

### Rulings (scan previo y (B))

Todos se cumplen en 745a7d8 y no hay nada que cerrar por ellos: desvio de orden del `PATRON` (T2, hecho); `test_privacidad_nube_system.py` reescrito (T5); desvio 8.4 aceptado y ESCRITO en el spec (diff presente); "/stop" como segundo valor con `_run_dynamic_team` filtrando (`:2489`, `:2549`); T12 con la letra medida intacta (solo la cola del `elif extra:` cambio; `test_el_trim_del_contrato_nunca_corta_el_cierre`); imports del abismo sin try/except (`server.py:83-88`); `sw.js` v4 en T10 sin re-bump; huecos declarados como residuales; (B) tests extra del steer, `max-height`, `etiquetar` compartido, asercion por encabezado real. El ruling 5 ("limpia los artefactos de jobs") es el que H3 deja a medias.

## Resumen

Ataque: cada promesa de las secciones 3-11, 13 y 15 del spec y de las Tasks 1-13, con foco en los catorce salteos, el cierre de la senal en todas las salidas, los sumideros, el "venias diciendo" crudo por las dos rutas, el contrato sin nombres y las dos UIs; mas nueve sondas fuera del arbol sobre el harness real.
Aguanto: los 14 salteos (todos fuera del bucle, cada uno con su conteo), el cierre de la senal en excepcion/steer (4 momentos)/tope/EOF/juez caido/modelo caido en la reentrada, el contrato sin nombres por las dos rutas y los fallbacks, el crudo a la nube por las dos rutas, los tres `apagada` (sondas A y B), y las dos UIs (renglon hermano, una burbuja, detalle, cierre en done/error/steered/onclose/cargar).
Cedio: (H1) el filtro del stream deja salir y persistir una marca valida armada por empalme, por las dos rutas; (H2) en one-shot un prefijo `⟦abismo:` abierto antes de la marca traga toda la continuacion de la reentrada en silencio; (H3) `stderr.txt` es el unico artefacto de jobs crudo (ruling 5); (H4) el fallback entre suscripciones tras una reinvocacion fallida persiste menos de lo que Pedro leyo (declarado, pero la divergencia es nueva); (H5) el foco se cosecha del texto descartado (no es letra del spec).
