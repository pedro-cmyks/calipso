# Ronda adversaria de rama -- lente COMPLETITUD

Rama `feat/capa-de-sesion`, HEAD `fa8fe89`, base `c3a4d13`. Revision de lectura sobre el checkout (sin mutar arbol, indice ni ramas). Fecha: 2026-09-08.

Fuentes: spec `docs/superpowers/specs/2026-09-07-capa-de-sesion-design.md` (secciones 3, 4, 6, 7), plan `docs/superpowers/plans/2026-09-07-capa-de-sesion.md` (Tasks 1-9), ledger `.superpowers/sdd/2026-09-07-capa-de-sesion/progress.md`, diff de la rama (`rama-completitud.diff`, 21 commits, 19 archivos), y el codigo real de `calipso/sesiones.py`, `calipso/server.py`, `calipso/web/fabrica/*.js`, `test_sesiones.py`, `test_sesiones_server.py`.

Estado de la suite en este checkout (corrida en esta revision):
- `.venv/bin/python -m pytest -q --ignore=test_chat_live.py -p no:cacheprovider` -> `1356 passed, 4 warnings in 30.72s`, `EXIT=0` (los 4 warnings son los preexistentes).
- `node --test` desde `calipso/web/fabrica/` -> `# pass 396 / # fail 0`.

Convencion de la columna "Estado": VIVE (codigo y test la afirman), A MEDIAS (lo que falta se dice), FALTA. `srv:` = `calipso/server.py`, `ses:` = `calipso/sesiones.py`, `ts:` = `test_sesiones.py`, `tss:` = `test_sesiones_server.py`.

---

## A. Spec seccion 3 -- Arquitectura

### A.1 El almacen (`calipso/sesiones.py`)

| # | Promesa | Codigo | Test | Estado |
|---|---|---|---|---|
| 1 | `~/.calipso/sesiones.json` escrito con el escritor atomico de `candado.py` | ses:220 (`escribir_json_atomico(_ruta(), datos, modo=0o600)`); `candado.py:26-72` (parametro `modo`, `O_CREAT\|O_EXCL`) | ts:479-499 | VIVE |
| 2 | El archivo guarda `sha256(id)`, jamas el id en claro | ses:138-139, 432, 450 | ts:261-268; tss:312 | VIVE |
| 3 | Nace 0600 | ses:216-221; candado.py:69 | ts:271-273; ts:479-487 | VIVE |
| 4 | Entra a `SKIP_FILES_RAIZ` del backup | `calipso/backup.py:37` | `test_seguridad_backup.py:75-86` | VIVE |
| 5 | `es_credencial_del_servidor` lo cubre (NUNCA del motor de permisos) | `calipso/permisos/acciones.py:179, 208` | `test_seguridad_backup.py:89-99` | VIVE |
| 6 | Registro: `hash_id`, `id_pedido` = `token_urlsafe(32)`, `aparato` <= 60 sin control chars, `tipo`, `creada`, `ultima_vez`, `estado` | ses:352-358 (registro), ses:66 (`APARATO_MAX`), ses:272-288 (`_validar`, `isprintable`) | ts:224-235 | VIVE |
| 7 | `golpear` valida tipo en ALCANCES y limites de `aparato`; si no, 422 y NO estaciona | ses:339 -> ValueError; srv:827-843 -> 422 | ts:232-235 (`not ruta.exists()`); tss:147-156 | VIVE |
| 8 | Tope de 5 golpes pendientes | ses:58, 348-351 (`Lleno`), srv:841-843 -> 429 | ts:150-158; tss:159-167 | VIVE |
| 9 | TTL de `golpeando` = 10 min; los vencidos se podan | ses:57, 228-229, 345-347 | ts:141-147, 155-158 | VIVE |
| 10 | `aprobar(id_pedido, tipo)`: el tipo lo pone Pedro; "genera el id, guarda su hash, deja la cookie lista para UN canje" | ses:364-380. Ruling del ledger (T1 spec-vs-constraint): el id nace en el CANJE (ses:431-432), aprobar deja `viva` con `hash_id=None` | ts:61-72, 93-103; tss:257-267, 349-360 | VIVE (con ruling documentado en ses:12-19) |
| 11 | `rechazar` | ses:383-392 | ts:113-122; tss:270-274 | VIVE |
| 12 | `revocar` | ses:395-405 | ts:125-134; tss:372-382 | VIVE |
| 13 | `canjear` entrega el id UNA vez y quema `id_pedido`; segundo canje = 404 | ses:408-436; srv:858-877 | ts:75-82; tss:295-316 | VIVE |
| 14 | `resolver(id_en_claro)` | ses:482-521 | ts:61-72, 161-166, 184-192 | VIVE |
| 15 | `listar()` estado EFECTIVO (dormida >30 o pasada de 180 se reporta caduca aunque diga viva) | ses:241-255, 524-535 | ts:206-217 | VIVE |
| 16 | Lectura sin candado, cache recargada por stat/mtime | ses:150-153, 179-199 | ts:311-319 (recarga cuando otro proceso escribe) | VIVE |
| 17 | Renovacion de `ultima_vez` con histeresis de 1 h, via `asyncio.to_thread` desde el guard | ses:63, 510-521; srv:499 (`to_thread(sesiones.resolver, ...)`) | ts:195-203; tss:629-646 | VIVE |
| 18 | El flock JAMAS en el event loop | Todas las mutaciones desde `server.py` van por `to_thread`: srv:499, 583, 763, 836, 871, 879, 894, 903, 930; `aparatos_listar` es `def` sincrono (threadpool, srv:908); `aparatos_estado` llama `sesiones.estado` que no toma candado (ses:465-479) | Sin test que lo afirme (no hay forma barata de probar "no se tomo flock en el loop"); revisado a mano | VIVE (por lectura) |
| 19 | Archivo ilegible: renombrado a `sesiones.json.corrupto-<ts>` ANTES de la primera escritura; avisado y preservado; en lectura no se pisa | ses:202-213 (`_leer_para_mutar`), ses:179-199 (`_leer` no muta) | ts:276-297 | VIVE |
| 20 | Molde `_leer_solicitudes`, NO `config()` | ses:21-26 (docstring) | -- | VIVE |

### A.2 Los alcances

| # | Promesa | Codigo | Test | Estado |
|---|---|---|---|---|
| 21 | Reglas `(prefijo, metodos)` por tipo; fail-closed; 403 "fuera del alcance del aparato" | ses:81-97, 295-324; srv:505-510 | ts:326-472; tss:408-431 | VIVE |
| 22 | El alcance aplica a TODAS las rutas, no solo `/api` | srv:505 (sin filtro por prefijo) | tss:425-431 (`/fabrica` html -> 403) | VIVE |
| 23 | `navegador` = `*`; `lector` = `/api/lectura/` | ses:82-83 | ts:326-329, 427-448 | VIVE |
| 24 | `tablero`: `/fabrica`, `/static`, `/ws/mapa`, `/api/mapa/`, `/api/economia/`, `/api/permisos`, `/api/inbox` GET; `/api/economia/bus/` POST; `/api/permisos/responder` POST | ses:84-96. Refinada contra rutas reales (ruling T2): `/api/permisos/solicitudes/` POST en vez de `/api/permisos/responder` (que no existe); GET += `/api/plantel`, `/api/routines` | ts:344-373 | VIVE (refinamiento previsto por el spec: "la lista exacta se refina en el plan") |
| 25 | NADA de `/api/file`, `/api/commands`, `/api/config`, `/api/project` para el tablero | ses:84-96 (ausentes) | ts:376-424 (unidad, 40 rutas vedadas); tss:408-414 (endpoint, solo `/api/file`) | VIVE en codigo; A MEDIAS en tests de endpoint (ver seccion C, item 6.12) |
| 26 | La sesion resuelta viaja en `request.state.sesion` | srv:511 | tss:395-403 (revocar por navegador la usa) | VIVE |

### A.3 El guard

| # | Promesa | Codigo | Test | Estado |
|---|---|---|---|---|
| 27 | `/login` exenta | srv:459 | tss:192-209 (`/login` contesta 401 con el balde de aparatos lleno) | VIVE |
| 28 | `/setup` exenta SOLO si loopback Y no existe `totp_secret` Y `?token=` valido | srv:461-470 | tss:566-592 | VIVE |
| 29 | (fix T4) `/setup` no se sirve a NADIE sin secreto fuera de esa ventana | srv:472-483 | tss:595-624 | VIVE |
| 30 | `POST golpear/estado/canjear` exentas, freno propio con claves `aparatos:{host}` / `aparatos:*` | srv:348-369, 484-490 | tss:192-229 (host), 363-369 (solo POST). El balde `aparatos:*` (umbral 20) no se dispara en la suite; lo dispara la sonda S1 | VIVE (S1 lo confirma) |
| 31 | Cuenta fallo: golpe nuevo, estado/canje con id desconocido. NO cuenta: sondear un id valido | srv:836 (golpear siempre), 851-853, 866-868 | tss:172-188 | VIVE |
| 32 | El id viaja en el BODY, nunca en el path | srv:810-815; aprobar/rechazar tambien por body (ruling T1/T3) | tss:241-243, 262-263, 300 | VIVE |
| 33 | Cookie `calipso_sesion` httponly, samesite=lax, max_age 30 dias; viva pasa con su alcance | srv:135-136, 491-519, 874-876, 766-767 | tss:303-308, 534-539, 642-646 | VIVE |
| 34 | Cookie o `?token=` que valen el TOKEN: solo loopback | srv:520-546 | tss:444-480; `test_seguridad_portones.py:213-227` (ajustado de 200 a 401) | VIVE |
| 35 | Un 401 remoto con cookie-token ademas la EXPIRA (limpieza de las cookies de un anio) | srv:536-538 y srv:450-451 (`_expirar_token_viajero`): SOLO si `_valid(cookie)` | tss:444-456, 490-510 (solo con el token vigente) | A MEDIAS: tras rotar el token (paso obligatorio del despliegue, spec:77-83) la cookie vieja ya no es valida y NUNCA se expira. Sonda S3. Ver hallazgo H1 |
| 36 | `/login`+TOTP: local planta el token; remoto crea sesion `navegador` YA VIVA | srv:754-768 | tss:526-561 | VIVE |
| 37 | Websockets: token valido DESDE LOOPBACK o sesion viva cuyo alcance cubra ese ws | srv:551-587 (`_ws_autorizado`); srv:3030-3038 (ws_chat), 6915-6920 (ws_mapa) | tss:690-745 | VIVE |

### A.4 Alta, revocacion y corte en `/fabrica`

| # | Promesa | Codigo | Test | Estado |
|---|---|---|---|---|
| 38 | El aparato: golpear -> sondea estado -> al ver viva, canjear UNA vez -> cookie | srv:827-877 | tss:137-188, 295-321 | VIVE |
| 39 | `/fabrica` muestra los que golpean con el tipo SUGERIDO y su alcance EN GRANDE | `aparatos.js:31-45` (tabla en castellano), `aparatos.js:78-93` (tarjeta: `.sugerido`, `.alcance`, selector preseleccionado); `estilo.css:500-502` `.alcance` = 13px en `--acento` -- el mismo tamano que `.nombre` (estilo.css:498) | `aparatos.test.js` (tarjeta, escape, selector); `arranque.test.js:614-625` (el cartel se reescribe al cambiar el select) | A MEDIAS: "en grande" es solo color; tipograficamente no es mas grande que el nombre. Hallazgo H6 (minor) |
| 40 | Aprobar exige loopback; rechazar idem | srv:818-823, 880-905 | tss:234-274 | VIVE |
| 41 | `GET /api/aparatos` lista (estado efectivo) | srv:907-913 | tss:326-360 | VIVE |
| 42 | `POST /api/aparatos/{hash}/revocar` desde loopback o sesion `navegador`; `tablero` y `lector` NO revocan | srv:916-935 (loopback o `ses.tipo == navegador`); el tablero muere antes, en el alcance (ses:84-96 no tiene `/api/aparatos`) | tss:372-403 (loopback, lector, navegador). Tablero: sin test en la suite; sonda S2 -> 403 | VIVE (S2) |
| 43 | El token no se revoca por esta capa | srv:691-697 (el socket con token no se envuelve), docstring | tss:831-841 | VIVE |
| 44 | Corte de WS vivos: registro EN MEMORIA sesion->generacion que `revocar()` incrementa | srv:595-616 (`_ws_generaciones`, `_revocar_en_vivo`); el hook vive en el ENDPOINT `aparatos_revocar` (srv:934), no en `sesiones.revocar` | tss:773-787 (por la ruta http) | VIVE (por la ruta http; una revocacion hecha por otro proceso o por `sesiones.revocar` directo no incrementa -- fuera del spec, que dice "desde /fabrica") |
| 45 | Cada ws guarda su sesion del handshake y re-chequea la generacion al recibir, antes de cada emision y en el latido | srv:619-688 (`_SocketVigilado`: send_json/send_text/send_bytes/receive_text/receive_json), srv:642 (foto), srv:3008-3025 (`LATIDO_CHAT_S`=30 s, `_proximo_del_chat`), srv:3068, srv:6932 (tick del mapa) | tss:773-841 | VIVE, con la ventana TOCTOU reproducida en la sonda S7 (hallazgo H3, minor) |
| 46 | Un ws ocioso no sobrevive a la revocacion mas alla del proximo latido | srv:3011-3025 (chat, `wait_for` con timeout), srv:6932 (mapa, cada tick) | tss:773-798 | VIVE |
| 47 | `ws_mapa` itera por tick; `ws_chat` agrega el chequeo en sus puntos de emision | srv:6932; srv:3037 (proxy que cubre los 46 puntos) | tss:800-828 | VIVE |

### A.5 Migracion y despliegue

| # | Promesa | Codigo / doc | Estado |
|---|---|---|---|
| 48 | (1) Las cookies-token remotas viejas mueren solas (paso 4 las expira) | srv:536-538 / 450-451 condicionado a `_valid` | A MEDIAS: solo mientras el token NO haya rotado. En el orden que el propio spec manda (rotar en el paso 2), las cookies viejas nunca se expiran. Sonda S3. Hallazgo H1 |
| 49 | (2) Rotar el TOKEN es parte del despliegue, documentado | spec:77-83 ("Despliegue de la fase 1", pasos 1-4; commit c63e35f) | VIVE (doc). Paso de Pedro, no de esta sesion |
| 50 | (3) La PWA remota hace `/login`+TOTP una vez y queda `navegador` | srv:754-768 | VIVE |
| 51 | (4) Tauri y la Ally no cambian | srv:540-546 (`?token=` y cookie-token desde loopback siguen); tss:474-480, 710-714 | VIVE |

---

## B. Spec seccion 4 -- Invariantes

| Inv | Promesa | Donde | Estado |
|---|---|---|---|
| 1 | El TOKEN jamas viaja a un aparato remoto | srv:754-768 (login remoto no planta `calipso_token`), srv:461-470 y 586-592 (`/setup?token=` remoto -> 303), srv:540-546 (`_session_response` solo tras `_es_loopback`) | tss:526-543, 586-592 | VIVE |
| 2 | Remoto = solo sesiones; token (cookie o query) solo loopback, tambien en ws | srv:520-546; srv:581-585 | tss:444-480, 690-714; `test_seguridad_portones.py:213-227` | VIVE |
| 3 | Alcance fail-closed en http y ws | ses:295-324; srv:505; srv:579 | ts:451-472; tss:408-431, 725-736, 649-663 (registro sin tipo -> 403) | VIVE |
| 4 | Aprobar solo-loopback; excepcion `/login`+TOTP remoto; revocar loopback o `navegador` | srv:818-823; srv:754-768; srv:922-927 | tss:234-267, 526-543, 384-403; S2 | VIVE |
| 5 | Dormida 30 / vieja 180 = muerta; la mata la resolucion; `listar()` reporta efectivo | ses:232-238, 502-509, 524-535 | ts:161-192, 206-217 | VIVE (con el limite parked: una sesion caduca con ws abierto sigue emitiendo hasta la reconexion -- sonda S8) |
| 6 | Golpear/estado/canjear con freno propio, separado del login; el sondeo legitimo es gratis | srv:348-369, 484-490 | tss:178-229; S1 (balde global) | VIVE. Residual conocido (plan, punto 12): bajo el balde GLOBAL lleno, el sondeo legitimo tambien recibe 429 (S1: `sondeo legitimo bajo balde global lleno: 429`) |
| 7 | `sesiones.json` guarda hashes, nace 0600, no se respalda, bajo el NUNCA; ilegible = renombrado y avisado | ses:220, 202-213; backup.py:37; acciones.py:179 | ts:261-297; `test_seguridad_backup.py:75-99` | VIVE |
| 8 | La cookie se entrega UNA vez; `golpeando` caduca en minutos y tiene tope | ses:408-436, 228-229, 348-351 | ts:75-82, 141-158; tss:295-321 | VIVE |
| 9 | Sin marcha atras: revocada/rechazada no reviven | ses:374-377 (aprobar exige `golpeando`), 402 (revocar exige viva), 426-430 (canjear exige viva sin hash) | ts:113-134, 161-166 | VIVE |
| 10 | El flock jamas en el event loop | ver A.1 #18 | -- | VIVE (por lectura) |

---

## C. Spec seccion 6 -- Como se verifica

| # | Verificacion prometida | Test | Estado |
|---|---|---|---|
| 6.1 | Ciclo completo con reloj inyectable | ts:61-72 | VIVE |
| 6.2 | TTL de golpes (10 min) | ts:141-147 | VIVE |
| 6.3 | Tope de pendientes | ts:150-158 | VIVE |
| 6.4 | Canje unico (segundo = 404) | ts:75-82; tss:295-316 | VIVE |
| 6.5 | Caducidad 30/180 | ts:161-192 | VIVE |
| 6.6 | Estado efectivo en listar | ts:206-217 | VIVE |
| 6.7 | Hash: el archivo jamas contiene el id | ts:261-268; tss:312 | VIVE |
| 6.8 | Corrupcion renombrada | ts:276-284 | VIVE |
| 6.9 | 0600 | ts:271-273 | VIVE |
| 6.10 | Golpear estacionado con tipo validado (basura = 422) | tss:137-156 | VIVE |
| 6.11 | Aprobar remoto = 403; loopback = viva CON EL TIPO DE PEDRO (canario) | tss:234-267 | VIVE |
| 6.12 | Alcance `lector` y `tablero` contra rutas vedadas = 403; canarios file/commands/config para tablero | tss:408-414 (`/api/file`), 425-431 (lector vs `/fabrica`), 336-346 (`/api/aparatos`). `commands` y `config` solo en la unidad (ts:376-390) | A MEDIAS en tests de endpoint (sonda S5 confirma que el guard los rebota). Hallazgo H5 (minor) |
| 6.13 | Renovacion con histeresis | ts:195-203; tss:629-646 | VIVE |
| 6.14 | Login remoto crea sesion y NO planta token | tss:526-543 | VIVE |
| 6.15 | Cookie-token remota = 401 QUE EXPIRA la cookie (canario) | tss:444-456 | VIVE para el token vigente; ver H1 para el rotado |
| 6.16 | ws_chat con cookie-token desde no-loopback = close 1008 (canario del invariante 2) | tss:690-694 | VIVE |
| 6.17 | ws de sesion revocada se corta aunque este ocioso (latido) | tss:773-798 | VIVE |
| 6.18 | Martillar golpear frena SIN tocar el balde del login | tss:192-209 | VIVE |
| 6.19 | Sondear id valido N veces = gratis | tss:178-188 | VIVE |
| 6.20 | Suite completa + node | corrida en esta revision: 1356 passed EXIT=0; node 396 pass | VIVE |
| 6.21 | Smoke en vivo con server desechable (golpear con curl, aprobar, usar, revocar, ver el corte) | `docs/superpowers/2026-09-08-smoke-capa-de-sesion.md` NO existe en HEAD fa8fe89 | FALTA en HEAD; en curso en esta misma ronda (Task 9, otro agente). No es hallazgo de esta lente: se cierra cuando aterrice la transcripcion |
| 6.22 | Ronda adversaria de rama antes del merge | esta ronda | en curso |

---

## D. Spec seccion 7 -- Fases y ripple documental

| # | Promesa | Donde | Estado |
|---|---|---|---|
| 7.1 | Fase 1 atomica: almacen + guard + login + ws | commits d39bc99..2de546b (Tasks 1-6) | VIVE |
| 7.2 | Fase 2: UI de `/fabrica` (tarjetas, lista, revocar) | commits e682d63..0da1926; `aparatos.js`, `app.js:614-727, 793-800, 1186, 1212`, `index.html:56, 64`, `sw.js:27`, `estilo.css:476-520` | VIVE |
| 7.3 | Fase 3: corte activo (generaciones + latido) | commit fa8fe89; srv:595-710, 3008-3025 | VIVE |
| 7.4 | Ripple documental: BRIEF del lector (plugin = golpear -> sesion `lector`; APK = `tablero`) | `/var/home/pedro/calipso-lector/BRIEF.md` (fuera de git), actualizado 2026-09-08 09:32: seccion "# Actualizacion del 8 de septiembre de 2026: la capa de sesion aterrizo" (l.547) con los 7 puntos del brief de la Task 9 (golpear/estado/canjear l.564-595; Pedro aprueba l.597-604; alcance lector l.606-614; APK tablero l.616-633; vida de la sesion l.635-652; token en la Ally l.654-666; lo que sigue bloqueando l.668-681) y las notas de "Actualizacion 2026-09-08" sobre los pasajes viejos (l.178, 242, 312, 364, 525, 536) | VIVE, con una salvedad: la seccion 6 del BRIEF (l.656-659) repite la promesa "se limpian solas la proxima vez que ese navegador vuelve", que S3 muestra falsa despues de rotar el token (H1). Si se cierra H1 en codigo, el texto queda cierto; si no, hay que corregir el BRIEF y el spec |

---

## E. Plan -- Tasks 1 a 9

| Task | Promesa | Donde | Estado |
|---|---|---|---|
| T1 | Almacen con la interfaz declarada; `crear_viva` (ruling); `renovada` (ruling); commit con ese nombre | ses completo; `crear_viva` ses:439-458; `renovada` ses:511, 521; commit d39bc99 | VIVE |
| T1 | Tests: grep del json por el id de canjear; modo 0600; corrupto renombrado | ts:261-268, 271-273, 276-284 | VIVE |
| T2 | `permite` fail-closed; comodin `*`; tablero refinado contra rutas reales; vedadas file/commands/config/project/updates/plugins/backup | ses:295-324; ts:376-424 | VIVE |
| T3 | Tres endpoints exentos por path exacto y POST; freno con claves propias; canje setea la cookie; aprobar/rechazar detras del guard + loopback; `GET /api/aparatos` detras del guard | srv:484-490, 827-913 | tss:137-369 | VIVE |
| T3 | "martillar golpear frena `aparatos:*` SIN tocar el balde del login" | tss:192-209 afirma `aparatos:*` == 5 (el host se frena antes de que el global llegue a 20); el umbral global lo dispara la sonda S1 | VIVE (sin test del umbral global en la suite: minor del ledger, puede esperar) |
| T4 | Orden del guard = spec 1-5; `delete_cookie` en el 401 remoto; `/setup` endurecido; login remoto -> sesion | srv:456-548, 754-768 | tss:444-624 | VIVE (salvo A.3 #35) |
| T5 | Ambos handshakes: token+loopback o sesion con alcance; ws_chat solo `navegador`; `/ws/mapa` navegador y tablero; canario del invariante 2 primero | srv:551-587; ses:87 | tss:690-745 | VIVE |
| T6 | backup, acciones, test espejo, nota de rotacion en el spec | backup.py:37; acciones.py:179; `test_seguridad_backup.py:75-99`; spec:77-83 | VIVE |
| T7 | Tarjeta escapada; tipo sugerido y alcance en grande; aprobar con selector preseleccionado; rechazar; lista con estado efectivo y revocar; node tests + tests de endpoints | `aparatos.js`, `app.js`, `aparatos.test.js`, `arranque.test.js:522-625`, `test_mapa_server.py:171-195` | VIVE, con H2 (el repintado deshace el select) y H6 (en grande) |
| T8 | `_ws_generaciones`; revocar incrementa via hook; ws_chat chequea al recibir/emitir/latido; ws_mapa en su tick; test del ocioso | srv:595-710, 934, 3008-3025, 6932; tss:773-841 | VIVE (H3: TOCTOU) |
| T9 | Smoke en vivo con transcripcion | FALTA en HEAD fa8fe89 (en curso en esta ronda) | pendiente de la ronda |
| T9 | Ronda adversaria (eficacia/regresiones/completitud) | en curso | pendiente de la ronda |
| T9 | BRIEF del lector actualizado | hecho fuera de git (ver D 7.4) | VIVE |
| T9 | Merge a main + push | lo hace el controlador | pendiente |
| T9 | Rotar el TOKEN (paso de despliegue documentado) | spec:77-83; el acto es de Pedro | VIVE (doc) |

Rulings del plan/ledger que esperan a Pedro (no son bloqueantes, se implemento el default del spec): tope de 180 dias (ses:56), tablero/lector no revocan (srv:922-927), y "el tablero VE `/api/plantel` pero no puede PARAR la fabrica" (ses:92, ts:402-404; la confirmo el implementador, no Pedro).

---

## F. Minors diferidos y rulings parked del ledger: clasificacion

DEBE = cerrarse antes del merge. ESPERA = puede quedar para despues (con la razon).

| Origen | Minor / ruling | Clasificacion | Razon |
|---|---|---|---|
| T1 | Docstring de `sesiones.py` clasifica `resolver` como lectura pero toma el flock en dos ramas | ESPERA | El guard ya lo llama por `to_thread` (srv:499, 583); solo guia a un futuro llamador. El docstring ses:32-34 ya lo dice ("salvo cuando resolver renueva o mata") |
| T1 | Sufijo `.corrupto-<ts>` con resolucion de segundos pisa una segunda corrupcion en el mismo segundo | ESPERA | Requiere dos corrupciones distintas en el mismo segundo con una mutacion en el medio |
| T1 | Validacion de tipo duplicada en `_validar` y `aprobar` | ESPERA | Cosmetico |
| T1 | rechazada/revocada nunca se podan (listar crece sin limite) | ESPERA | Solo Pedro crea rechazadas/revocadas (aprobar/rechazar/revocar exigen Ally o navegador); los golpes vencidos SI se podan (ses:345-347). Sin palanca anonima |
| T1 | `escribir_json_atomico` con modo levanta `FileExistsError` ante un temporal huerfano | ESPERA | El nombre lleva pid y thread ident (candado.py:59-60) y el `finally` lo borra; queda solo tras un crash duro con reuso de pid |
| T1 | `estado()` devuelve "viva" para aprobado-y-caduco (asimetria con `canjear`) | ESPERA | Reproducido en la sonda S6 (estado 200 "viva", canjear 404 y un fallo cobrado). Requiere una aprobacion que nadie canjeo en 30 dias; el aparato sondea "cada pocos segundos" y canjea al primer "viva". Barato de alinear (devolver None cuando `_sesion_caduca`) pero no bloquea |
| T2 | `startswith` es prefijo crudo (`/fabricante` matchearia `/fabrica`) | ESPERA | No existe ninguna ruta asi hoy. Anotar como regla de convivencia: toda ruta nueva que empiece por `/fabrica`, `/api/permisos`, `/api/inbox`, `/api/plantel`, `/api/routines` queda abierta al tablero en GET |
| T2 | Comodin comparado con `==` depende de tuplas | ESPERA | `ALCANCES` es del modulo; ts:326-329 fija la forma |
| T3 | Rama "revocar por sesion navegador" sin test directo | CERRADO en la rama | tss:395-403 |
| T3 | Balde `aparatos:*` (umbral 20) nunca disparado en tests | ESPERA | La sonda S1 lo dispara y funciona (429 + Retry-After 3 para un host nuevo; `/login` sigue 401 y su balde `*` intacto). Agregar el test es trivial, no bloquea |
| T3 | `await request.json()` sin tope de tamano en rutas SIN credencial | ESPERA | Vector de memoria preexistente con el mismo perfil que `/login` (body de formulario sin tope); el freno limita a 5 por host / 20 globales por ventana de castigo; transporte solo-Tailscale. Cerrarlo es barato (rechazar `Content-Length` > 4 KB antes de leer) y conviene, pero no es una promesa del spec |
| T3 | `request.client.host if request.client else ""` repetido 7 veces | ESPERA | Cosmetico |
| T4 | La renovacion de cookie se pierde si el request cae fuera de alcance | ESPERA | El siguiente request dentro del alcance la re-planta (srv:513-517); costo: una hora |
| T4 | Un `calipso_token` INVALIDO desde afuera nunca se limpia (tras rotar, las cookies viejas quedan un anio; la nota de despliegue promete una limpieza que no ocurre) | DEBE | Es la promesa (1) de "Migracion y despliegue" (spec:74) y la 6.15 del spec, rota justo en el orden que el spec manda (rotar primero). Reproducido en S3. Y de yapa: condicionar el `Set-Cookie` vencido a `_valid` es un oraculo remoto de validez del token (el comentario srv:447-449 y 533-535 afirma lo contrario). Fix de una linea en dos lugares: borrar la cookie remota si VIENE, valga o no (srv:450, 536-538). Hallazgo H1 |
| T4 | Test del tablero contra `/api/economia/tablero` afirma `not in (401, 403)` y pasaria con 404 | ESPERA | Hoy contesta 200 (sonda S4); endurecer a `== 200` es una linea |
| T4 (ruling parked) | La sesion gana sobre el token tambien en loopback | ESPERA | Es el orden del spec (3 antes de 4). Reproducido en S9: loopback con cookie tablero + token -> 403 en `/api/tree`. Solo pasa si Pedro canjea un tablero desde el navegador de la propia Ally; la salida es revocarlo o borrar la cookie. Vale una linea en AGENTS.md |
| T4 (ruling deferred) | `/login` remoto crea una sesion viva por login, sin poda ni dedup | ESPERA | Solo con TOTP (Pedro); `/fabrica` > Aparatos ya lista y revoca |
| T5 (ruling parked) | En `_ws_autorizado` una sesion fuera de alcance cae al chequeo del token (OR literal); el guard http da 403 sin mirar el token | ESPERA | Reproducido en S10: loopback con cookie tablero + token abre `/ws/chat` (por el token, socket sin vigilar). Remoto no afloja nada (el token exige loopback). Alinear es de dos lineas pero es el mismo caso contrived de arriba |
| T5 | `_ws_autorizado` repite la rama de sesion del guard; ningun test fija el orden sesion-primero | ESPERA | tss:717-745 y S7 dependen de ese orden de hecho; refactor, no promesa |
| T6 | Parrafo duplicado en "Migracion y despliegue" del spec | ESPERA | Doc; si se cierra H1 conviene reescribir ese parrafo de una vez |
| T6 | Falta el test espejo de `projects/sesiones.json` en el zip | ESPERA | `test_seguridad_backup.py:96-99` ya cubre el espejo en `es_credencial_del_servidor`; el del zip es simetrico y barato |
| T7 | `.alcance` no es tipograficamente "en grande" | ESPERA (hallazgo H6, minor) | Promesa del spec:70 a medias; es UX, no seguridad. Una linea de CSS |
| T7 | Sin test de la suma del badge, del cartel "Solo desde la Ally o desde un navegador" ni del alert con detail | ESPERA | `arranque.test.js:545-566` ya fija el badge de aparatos; el resto es cableado de UI |
| T7 | El repintado de 60 s DESHACE la eleccion del select (Pedro baja a lector, el intervalo repinta y el POST aprueba lo que sugirio el aparato) | DEBE | Contradice "el TIPO lo fija Pedro al aprobar (el golpe solo lo sugiere)" (spec seccion 2.2 y 3) del lado del cliente. Codigo sin ambiguedad: `app.js:650` reescribe `innerHTML` sin mirar el DOM; `app.js:1212` lo dispara cada 60 s, `app.js:659-664` tras cada accion y 5 s despues, `app.js:724` en el `finally` del click; el POST manda `select.value` del momento (`app.js:696-698`), que tras un repintado vuelve a ser la sugerencia. La ventana de decision de Pedro es de hasta 10 min y un aparato anonimo puede sugerir `navegador`. Hallazgo H2 |
| T7 | Quinta copia del cuarteto pintar/avisar/click/interval en app.js | ESPERA | Deuda de estructura |
| T7 | El badge global de la pestana no cuenta golpes (ruling 6) | ESPERA | Decision de diseno registrada; el sub-badge de "Aparatos" (`app.js:623, 651`) cumple "en /fabrica aparece". Costo: Pedro en la pestana del chat no ve el golpe hasta entrar a la Mesa |
| T8 | TOCTOU entre resolver la sesion en el handshake y la foto de la generacion | ESPERA, pero cierre recomendado en la misma ola (hallazgo H3, minor) | Reproducido en S7 simulando el orden (revocacion + hook entre `resolver` y `_SocketVigilado.__init__`): el ws sigue recibiendo eventos con la sesion revocada en disco. Ventana de microsegundos, sin palanca del atacante (necesita que Pedro revoque justo ahi). Fix de dos lineas: leer `_generacion_de` ANTES de `_ws_autorizado` y pasarla al proxy |
| T8 | Tres emisiones fuera de todo `try` pueden levantar `WebSocketDisconnect` sin nadie que lo atrape (srv ~3041, ~3323, ~6923) | ESPERA | Ruido de log en el peor caso, no un hueco |
| T8 | `_vigilar_socket` falla ABIERTO si el registro no trae `hash_id` | ESPERA | Inalcanzable: `resolver` matchea POR `hash_id` (ses:497-498), asi que un registro resuelto siempre lo trae. Fallar cerrado es higiene, no promesa |
| T8 | `_run_chat_draft` con `ensure_future` puede dejar "Task exception was never retrieved" | ESPERA | Log |
| T8 | Falta el positivo en vivo del proxy | ESPERA | S7 y S8 lo muestran de paso: un tablero vigilado recibe eventos del pulso a traves de `_SocketVigilado` |
| T8 | Peor caso del chat ocioso 30 s | ESPERA | Documentado (srv:3005-3008); el spec dice "el proximo latido" |
| T8 (ruling parked) | El corte por EXPIRACION de reloj con ws abierto no se cubre | ESPERA | Reproducido en S8 (sesion "caduca" en listar, el ws sigue recibiendo). El spec promete el corte por REVOCACION; la expiracion la mata la resolucion (invariante 5) y un ws no resuelve. Documentado en srv:612-615. Nota para el BRIEF si se quiere ser exhaustivo: un tablero que solo mantenga `/ws/mapa` sin hacer HTTP no renueva `ultima_vez` |

---

## G. Sondas corridas

Archivo: `/tmp/claude-1000/-var-home-pedro/7ea3cff5-be99-4946-a05c-6203e4bc2f84/scratchpad/sonda_completitud.py` (fuera del arbol; `CALIPSO_HOME` a un temporal antes del import; borrado al terminar). Comando:

```
cd /var/home/pedro/calipso && .venv/bin/python -m pytest -q -p no:cacheprovider -s <sonda>
```

Resultado: `15 passed, 4 warnings in 8.37s`. Salidas:

```
S1 host nuevo tras 20 fallos globales: 429 Retry-After 3
S1 golpear desde host nuevo: 429
S1 sondeo legitimo bajo balde global lleno: 429
S1 /login con el balde de aparatos lleno: 401 | balde * del login despues: 1
S2 tablero revoca: 403 {"detail":"fuera del alcance del aparato"}
S3 cookie-token VIGENTE remota: 401 Set-Cookie: calipso_token=""; expires=Tue, 08 Sep 2026 14:37:34 GMT; Max-Age=0; Path=/; SameSite=lax
S3 cookie-token ROTADA remota: 401 Set-Cookie: None
S4 /api/economia/tablero para tablero: 200
S6 estado: 200 {"estado":"viva"} | canjear: 404 | fallos del host: 1 | listar: ['caduca']
S7 ws de sesion REVOCADA recibe: {'seq': 1, ..., 'evento': 'inicio', 'departamento': 'dep:atlas', ...}
S8 ws de sesion CADUCA recibe: {'seq': 1, ..., 'evento': 'inicio', 'departamento': 'dep:atlas', ...}
S9 loopback con token + cookie tablero, /api/tree: 403 {"detail":"fuera del alcance del aparato"}
S10 ws_chat loopback tablero+token entro: True
```

Que prueba cada una:
- S1: el balde global `aparatos:*` existe y frena (5 hosts x 4 fallos = 20; el sexto host recibe 429 con Retry-After; golpear tambien); el balde del login queda intacto (`/login` -> 401 y `*` solo con el fallo de ese intento). Y el residual nombrado en el plan: el sondeo legitimo tambien queda bajo el 429 global.
- S2: el tablero no revoca (403 por alcance). Promesa A.4 #42 sin test en la suite.
- S3: la limpieza de la cookie-token remota solo dispara con el token VIGENTE; con un valor rotado, 401 sin `Set-Cookie`. Evidencia de H1 (promesa de migracion a medias + oraculo).
- S4: `/api/economia/tablero` contesta 200 a un tablero (el test `not in (401, 403)` es laxo pero hoy no tapa un 404).
- S5 (6 casos, sin print): el guard rebota a un tablero en `/api/commands` GET, `/api/commands/run` POST, `/api/config` GET/PUT, `/api/project` GET, `/api/file` PUT con 403 "fuera del alcance del aparato". Los canarios de la seccion 6 SE CUMPLEN en el codigo; solo faltan como tests de endpoint.
- S6: la asimetria `estado`/`canjear` del ledger, a nivel endpoint.
- S7: la ventana TOCTOU del corte, simulando el orden real (revocacion en disco + hook entre `resolver` y la foto): el ws sobrevive y recibe eventos con la sesion revocada.
- S8: expiracion por reloj con ws abierto (ruling parked): el ws sigue recibiendo.
- S9 y S10: los dos rulings parked de T4/T5 en loopback, reproducidos tal cual estan descriptos.

---

## H. Hallazgos (solo promesas faltantes o a medias y minors que deben cerrarse)

### H1 -- Important -- La limpieza de la cookie-token remota no ocurre despues de rotar el token (promesa de migracion a medias) y la condicion es un oraculo
- `calipso/server.py:450-451` (`_expirar_token_viajero`) y `calipso/server.py:536-538` (rama del token en `auth_guard`): `delete_cookie(COOKIE)` solo si `_valid(cookie)`.
- Spec seccion 3 "Migracion y despliegue" (l.74): "(1) las cookies-token remotas viejas mueren solas (paso 4 las expira); (2) rotar el TOKEN es parte del despliegue". Paso 2 del despliegue (l.79-80): rotar ANTES de que los remotos vuelvan. Despues de rotar, la cookie vieja ya no es `_valid` y NUNCA recibe el `Set-Cookie` vencido: el navegador remoto sigue mandando el token viejo (muerto) un anio. La promesa (1) solo vale si NO se cumple la (2).
- Reproducido (S3): cookie `calipso_token=<vigente>` remota -> 401 + `Set-Cookie: calipso_token=""; Max-Age=0`; cookie `calipso_token=token-de-antes-de-rotar` -> 401 sin `Set-Cookie`. Esa diferencia es observable desde afuera: un remoto que presente un valor como cookie sabe si es EL token. El comentario del codigo (srv:447-449, 533-535) afirma "no abre oraculo".
- El BRIEF del lector (l.656-659) y el spec repiten la promesa tal cual.
- Fix: en las dos ramas, si el request remoto trae la cookie `calipso_token` (cualquier valor), expirarla; sin mirar `_valid`. Cierra el oraculo y hace verdadera la nota de despliegue. Ajustar tss:444-456 para cubrir el valor invalido.

### H2 -- Important -- El repintado de la pestana Aparatos deshace la eleccion de tipo de Pedro (el POST aprueba lo que sugirio el aparato)
- `calipso/web/fabrica/app.js:650`: `cajaAparatos.innerHTML = textoDeAparatos(datos, mensajeAparatos)` reescribe todas las tarjetas sin conservar el estado de los `select`.
- Disparadores: `app.js:1212` cada 60 s; `app.js:659-664` tras cada accion (rechazar un golpe repinta y resetea el select de los otros) y 5 s despues; `app.js:724` en el `finally` de cualquier click; `app.js:800` al entrar a la pestana.
- `app.js:696-698`: el POST de aprobar manda `select?.value` del momento del click. Tras un repintado ese valor volvio a `golpe.tipo` (`aparatos.js:62-67`, `selected` en el sugerido).
- Contradice el spec seccion 2.2 / seccion 3 ("el TIPO lo fija Pedro al aprobar; el golpe solo lo sugiere") del lado del cliente; `arranque.test.js:522-531` lo llama "el canario del invariante 4 del lado del cliente", pero solo fija que el POST lleve el valor del select, no que el select sobreviva al repintado. Escenario: el aparato sugiere `navegador`, Pedro lo baja a `lector`, se distrae dentro de los 10 minutos del golpe, el intervalo repinta, Pedro toca aprobar: sale `navegador`.
- No reproducido en runtime (no hay DOM real en la suite); el codigo lo muestra sin ambiguedad.
- Fix: al repintar, conservar por `id_pedido` el valor de cada `select` ya tocado (leerlo del DOM antes de `innerHTML` y re-aplicarlo), o no repintar las tarjetas de golpe mientras alguna tenga el select distinto de la sugerencia. Test en `arranque.test.js`: cambiar el select, forzar `pintarAparatos()`, y afirmar que el POST sigue llevando el tipo elegido.

### H3 -- Minor -- TOCTOU del corte en vivo: una revocacion entre `resolver` y la foto de la generacion deja un ws que nunca se entera
- `calipso/server.py:551-587` resuelve la sesion (con `to_thread`); `calipso/server.py:642` recien ahi fotografia `_generacion_de(hash_id)`. Si `aparatos_revocar` (srv:929-934) corre en el medio, la foto ya incluye el incremento y `vigente()` (srv:647-648) da True para siempre.
- Reproducido (S7) simulando ese orden: la sesion queda revocada en disco (`resolver` -> None, `_ws_generaciones[hash] == 1`) y el ws de mapa sigue recibiendo eventos del pulso.
- Ventana de microsegundos y sin palanca del atacante: puede esperar, pero el fix son dos lineas (leer la generacion ANTES de `_ws_autorizado` y pasarla a `_SocketVigilado`) y conviene cerrarlo en la misma ola.

### H4 -- Minor -- AGENTS.md "Seguridad actual" describe la autenticacion vieja
- `AGENTS.md:205-213`: "Cookie: `calipso_token`" (no nombra `calipso_sesion`), "`/login` ... si valida, setea la misma cookie de sesion" (falso desde afuera: srv:754-768 planta `calipso_sesion`), "El token viejo sigue funcionando como recuperacion con `?token=...`" (solo desde loopback desde C8 y esta capa). Solo se actualizo la linea de `/setup` (commit 7b967af).
- No es una promesa del spec (el ripple nombra solo al BRIEF), pero es la guia del repo para agentes y contradice la rama. Un parrafo.

### H5 -- Minor -- Los canarios de endpoint del tablero prometidos en la seccion 6 (file/commands/config) solo existen para `/api/file`
- Spec seccion 6: "alcance lector y tablero contra rutas vedadas = 403 (canarios: file/commands/config para tablero)". En la suite: `test_sesiones_server.py:408-414` (solo `/api/file`); `commands` y `config` viven en la unidad (`test_sesiones.py:376-390`), no atraviesan el guard.
- El codigo cumple (sonda S5: seis rutas -> 403 "fuera del alcance del aparato"). Falta el test que lo afirme en la costura; es una parametrizacion de tss:408.

### H6 -- Minor -- "Su alcance en grande" es solo color
- Spec l.70: "muestra los que golpean con el tipo SUGERIDO y su alcance en grande". `estilo.css:500-502`: `.alcance` 13px en `--acento`; `.nombre` tambien 13px (`estilo.css:498`). El alcance es lo que Pedro tiene que leer antes de aprobar (comentario en estilo.css:476-479 lo dice) y no se destaca por tamano. Una linea de CSS.

---

## I. No reproducido / fuera de esta lente

- El smoke en vivo (6.21) y su transcripcion: no existen en HEAD fa8fe89; los produce otro agente de esta misma ronda. No se cuenta como hallazgo.
- El repintado del select (H2) no se corrio con DOM real: se reporta por lectura de codigo, sin ambiguedad.
- `await request.json()` sin tope: no se midio el consumo de memoria; se clasifica ESPERA por ser preexistente en `/login` y por el freno.
- Nada de esta lente encontro una promesa del spec o del plan que FALTE del todo en el codigo: todo lo prometido vive; lo que hay es dos promesas a medias con consecuencia (H1, H2), una ventana reproducida (H3) y tres huecos de test/doc/UX (H4-H6).
