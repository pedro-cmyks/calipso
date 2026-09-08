# Revision final de merge: rama `feat/capa-de-sesion`

**Rango:** `c3a4d13` (main) .. `fa8fe89`, 21 commits, 19 archivos, +3156/-57. (Durante la revision aparecio `d3fc3ba` "docs(sesiones): smoke en vivo": agrega solo `docs/superpowers/2026-09-08-smoke-capa-de-sesion.md`, sin tocar codigo; este reporte cubre el codigo hasta `fa8fe89`, que es el mismo.)
**Autoridad:** spec `docs/superpowers/specs/2026-09-07-capa-de-sesion-design.md`; plan `docs/superpowers/plans/2026-09-07-capa-de-sesion.md`; restricciones y ledger en `.superpowers/sdd/2026-09-07-capa-de-sesion/`.
**Metodo:** lectura completa del paquete `review-c3a4d13..fa8fe89.diff` (4158 lineas, en cinco pasadas), lectura del spec/plan/constraints/ledger, lectura dirigida de `server.py` fuera del diff (`_verify_totp`, `_get_totp_secret`, `setup_page`, `login_submit`, `Emisor`, cierre de `ws_chat`, rutas reales bajo los prefijos del `tablero`, `candado()`), corrida de la suite y de node, y dos sondas propias fuera del arbol (borradas al terminar). Ninguna mutacion del arbol, indice, HEAD ni ramas.

**Verificacion corrida por el revisor:**
- `.venv/bin/python -m pytest -q -p no:cacheprovider --ignore=test_chat_live.py` -> **1356 passed, 4 warnings (preexistentes), EXIT=0** (linea base en main: 1183).
- `node --test` desde `calipso/web/fabrica/` -> **396 pass, 0 fail, EXIT=0**.
- Sonda 1 (confirmada): `POST /login` remoto con el secreto TOTP ausente lo CREA, y despues `/setup?token=` desde loopback muestra "TOTP ya esta configurado" sin QR.
- Sonda 2 (confirmada): remoto con cookie `calipso_token` INVALIDA recibe 401 sin `Set-Cookie`; con la VALIDA recibe 401 con `Set-Cookie` vencida.

## Veredicto: **With fixes**

No hay Critical (ningun hueco que entregue el token, una sesion, o el secreto a un remoto; ninguna perdida de datos). Hay dos Important con arreglos de pocas lineas y tres minors del ledger que deben cerrarse en la misma ola antes del merge. Todo lo prometido por el spec para las fases 1-3 esta implementado y probado; las desviaciones son las del ledger y estan justificadas.

---

## 1. Alineacion con el spec

| Promesa del spec | Estado | Donde |
|---|---|---|
| Almacen con hashes, `id` en claro jamas en disco | Hecho (ruling: el id nace en el CANJE) | `sesiones.py:408-436`, test "el archivo jamas contiene el id en claro" |
| 0600 de nacimiento, sin ventana | Hecho, mejor que el spec (O_EXCL en `candado.py:66-69`) | `sesiones.py:216-221` |
| Ilegible = renombrado y avisado, jamas pisado | Hecho | `sesiones.py:202-213` |
| TTL golpe 10 min, tope 5, sueno 30 d, vida 180 d, histeresis 1 h | Hecho, constantes verbatim | `sesiones.py:55-66` |
| `estado efectivo` en `listar()` sin escribir | Hecho, con test de mtime | `sesiones.py:524-535` |
| Alcances fail-closed, aplican a TODA ruta | Hecho; `tablero` refinado contra rutas reales | `sesiones.py:81-101, 295-327` |
| Guard puntos 1-5 en ese orden | Hecho; `/setup` endurecido mas alla del spec (Critical cazado en T4) | `server.py:456-546` |
| Punto 6: ws con token solo-loopback o sesion en alcance | Hecho, canario 1008 | `server.py:551-583`, tests ws |
| Freno propio `aparatos:*`, sondeo valido gratis | Hecho, con canario de separacion | `server.py:340-370` |
| id_pedido por BODY, nunca path | Hecho (aprobar/rechazar por body; el hash si va en path) | `server.py:808-815, 917` |
| `/login` remoto crea sesion `navegador`, no planta token | Hecho | `server.py:755-769` |
| Cookie-token remota: 401 que EXPIRA | Hecho solo para la cookie VALIDA (ver I2) | `server.py:534-538, 440-452` |
| Cookie 30 d re-plantada con la renovacion | Hecho (ruling `renovada`) | `server.py:510-515` |
| UI de /fabrica: tarjetas, alcance en palabras, aprobar con selector, lista, revocar | Hecho | `aparatos.js`, `app.js:614-735` |
| Corte de ws vivos, ociosos incluidos | Hecho (generaciones + proxy + latido 30 s) | `server.py:589-716, 3008-3025` |
| `sesiones.json` fuera del backup y bajo el NUNCA | Hecho, con tests | `backup.py`, `permisos/acciones.py` |
| Nota de despliegue con rotacion del token | Hecho (duplicada, ver M6) | spec:73-82 |
| BRIEF del lector, smoke en vivo | Task 9, fuera de este diff (en curso) | -- |

Desviaciones aceptadas (todas en el ledger, todas con razon): id de sesion generado en el canje; `crear_viva` para el login remoto (fuera del tope de pendientes); `Lleno` -> 429; `/api/permisos/responder` no existe -> `/api/permisos/solicitudes/`; `GET /api/aparatos` no en el `tablero` (coherente con "los aparatos los administra el navegador o el loopback").

---

## 2. Hallazgos

### Important

**I1. `POST /login` da a luz el secreto TOTP fuera de la ventana del punto 1 (primer arranque brickeable por cualquiera que alcance el puerto).**
`server.py:239-243` (`_verify_totp`) llama a `_get_totp_secret()` (`server.py:219-226`), que si el archivo no existe **lo genera y lo escribe**. `/login` esta exenta del guard y `_verify_totp` corre con cualquier codigo de 6 digitos. Secuencia (reproducida con la sonda): server recien instalado sin `totp_secret`; un host de la LAN/Tailscale (o un flatpak/otro uid local) hace `POST /login code=123456` -> 401, pero el secreto ya nacio sin que nadie lo viera; la condicion `not _TOTP_SECRET_FILE.exists()` del punto 1 (`server.py:462-470`) deja de cumplirse; Pedro abre `/setup?token=` desde su maquina y recibe `SETUP_DONE_HTML` ("ya esta configurado") sin QR. Unico remedio: borrar `~/.calipso/totp_secret` a mano. La causa raiz es anterior a la rama, pero la rama redisenio el primer arranque alrededor de "el secreto nace SOLO en la ventana" (el comentario de `server.py:472-483` lo dice textual: "servirlo es CREARLO") y este camino la contradice. Ningun test de la rama lo ve porque todos parchean `_verify_totp`. Impacto para la instalacion actual de Pedro: nulo (su secreto existe); impacto para un primer arranque o una reinstalacion: DoS del enrolamiento.
**Arreglo (2 lineas + 1 test):** en `_verify_totp`, `if not _TOTP_SECRET_FILE.exists(): return False` antes de leer el secreto (o partir `_get_totp_secret` en un lector puro y un creador que solo llame `setup_page`). Test en `test_sesiones_server.py`: `POST /login` sin secreto -> 401 y el archivo sigue sin existir.

**I2. Oraculo remoto de validez del token por `Set-Cookie` (regresion contra C8).**
`server.py:534-538`: un remoto con `calipso_token` VALIDA recibe `401 {"detail":"no autorizado"}` + `Set-Cookie: calipso_token=""; Max-Age=0`; con una INVALIDA recibe el mismo 401 y el mismo body **sin** `Set-Cookie` (sonda confirmada). El status y el body son iguales a proposito (el comentario de `_sin_credencial`, `server.py:430-438`, lo explica) pero la cabecera es el bit que C8 quiso negar ("distinguirlos era un oraculo remoto de validez del token": el codigo previo a la rama lo cumplia). El token es `token_urlsafe(12)` = 96 bits y esta rama no pasa por ningun freno; la fuerza bruta sigue siendo inviable, asi que el uso practico del oraculo es confirmar desde afuera que un token fugado por otra via (el access log con `?token=` de C4, el historial de un navegador) **sigue siendo el vigente**, o sea si la rotacion que el spec manda ya paso. Lo mismo en `_expirar_token_viajero` (`server.py:440-452`) para quien ya trae sesion, con menos peso.
**Arreglo (1 linea en cada lugar + 1 test):** borrar la cookie cuando el remoto la PRESENTA, valga o no (`if galleta_token is not None: resp.delete_cookie(COOKIE)`). El remoto solo aprende que mando una cookie, cosa que ya sabe. De yapa cierra el minor diferido de T4 ("un `calipso_token` INVALIDO desde afuera nunca se limpia"): tras rotar el token, las cookies viejas de un anio pasan a ser invalidas y hoy no se limpian nunca, asi que la nota de despliegue del spec ("las cookies-token remotas viejas mueren solas") es falsa justo despues del paso 2 que ella misma exige. `test_el_token_por_url_remoto_no_expira_ninguna_cookie` sigue valiendo (no presenta cookie). Agregar: cookie invalida remota -> `Set-Cookie` vencida igual que la valida.

**I3. El repintado de 60 s deshace el tipo que eligio Pedro y aprueba lo que sugirio el aparato** (minor del ledger T7, recalibrado).
`app.js:1212` `setInterval(pintarAparatos, 60_000)` -> `app.js:650` reemplaza `innerHTML` con `textoDeAparatos`, que reconstruye cada tarjeta con `selected` en el tipo SUGERIDO (`aparatos.js`, `opcionesDeTipo(golpe.tipo)`). El `click` de aprobar (`app.js:695-699`) manda `select.value` EN ESE MOMENTO, que es lo correcto, pero si Pedro bajo "navegador" -> "lector", leyo el alcance, verifico el aparato y tardo mas de un minuto en tocar aprobar, el selector ya volvio solo a "navegador" y el POST aprueba la casa entera. La sugerencia es input NO autenticado (la escribe quien golpea), asi que en la practica es "el aparato fija el tipo si Pedro se demora": exactamente lo que el invariante 4 y el canario de T3 ("aprobar ignora el tipo del golpe") venian a evitar. Pedro lo veria despues en la lista y podria revocar, pero el alta ya se hizo con un alcance que no eligio.
**Arreglo (~10 lineas + 1 test de node):** en `pintarAparatos`, antes de reemplazar el HTML, leer `{id: select.value}` de cada `select[data-tipo-de]` y re-aplicarlos despues (y re-escribir el `.alcance` con `alcanceDe`); o no repintar el bloque de golpes mientras alguno de sus selectores tenga foco o difiera de la sugerencia. Test: repintar con un selector cambiado lo conserva.

### Minor

**M1. TOCTOU entre resolver la sesion y la foto de la generacion** (ledger T8; debe cerrarse antes del merge).
`_ws_autorizado` (`server.py:551-583`) resuelve en `to_thread`; recien despues `ws_chat`/`ws_mapa` (`server.py:3037`, `6920`) envuelven y `_SocketVigilado.__init__` (`server.py:626-630`) fotografia `_generacion_de(hash)`. Una revocacion que aterrice entre ambos (el almacen ya dice revocada y el contador ya subio) deja un socket cuya foto es la generacion NUEVA: `vigente()` da True para siempre y ese ws sobrevive a la revocacion hasta que el cliente se vaya. Ventana de microsegundos; probabilidad despreciable con Pedro revocando a mano; pero es el invariante entero de la fase 3 y el arreglo es trivial: calcular el hash de la cookie ANTES de resolver (exponer `sesiones.hash_de(id)`), fotografiar la generacion ahi, resolver, y envolver con esa foto. Como `aparatos_revocar` escribe el disco (`server.py:929`) ANTES de incrementar (`934`), cualquier intercalado queda cubierto: o `resolver` devuelve None, o la foto es la vieja y el primer chequeo cierra. En la misma pasada, `_vigilar_socket` (`server.py:691-697`) falla ABIERTO si el registro no trae `hash_id` (devuelve el socket crudo): hoy es inalcanzable porque `resolver` busca por hash, pero es una capa de autenticacion y debe fallar cerrado (cerrar 1008).

**M2. Cuerpo sin tope en las tres rutas SIN credencial** (ledger T3; debe cerrarse antes del merge).
`_cuerpo_json` (`server.py:799-806`) hace `await request.json()` sobre lo que mande un anonimo; uvicorn no limita el body por defecto, y el freno se cobra recien despues de leerlo. Un host de la red puede mandar cuerpos de GB a `/api/aparatos/golpear|estado|canjear` y crecer la memoria del server. Arreglo (~6 lineas): en el guard, para `_APARATOS_EXENTAS`, rechazar con 413 si `Content-Length` > 4096 (y contar el fallo); sin `Content-Length` (chunked), leer por `request.stream()` con el mismo tope. `/login` tiene el mismo problema preexistente (`await request.body()`), se puede tapar con el mismo helper.

**M3. Carrera en la cache del almacen: `_leer` puede devolver `None` y el guard contesta 500.**
`sesiones.py:179-199`: `_leer` compara `_CACHE["clave"]` y en la linea 199 devuelve `_CACHE["datos"]`; `_escribir` (`221`) y `_leer_para_mutar` (`212`) hacen `_CACHE.update(_cache_vacia())` desde OTRO hilo (todas las mutaciones corren en `to_thread`, `resolver` incluida). Si el reset cae entre la comparacion y el `return`, `_leer` devuelve `None`, `_por_hash(None, ...)` levanta `TypeError` y ese request muere en 500. Ventana de pocos bytecodes y escrituras raras (histeresis 1 h, altas): transitorio, no de seguridad. Arreglo: leer la cache como una foto unica (rebindear `_CACHE` con `global` a un dict nuevo en vez de mutarlo, y en `_leer` hacer `cache = _CACHE` una sola vez), o simplemente no resetear en `_escribir` (el `os.replace` cambia el inodo y la clave por stat ya invalida sola). Los `monkeypatch.setattr(sesiones, "_CACHE", ...)` de los tests siguen funcionando con el rebind.

**M4. `AGENTS.md` "Seguridad actual" quedo desactualizado.**
`AGENTS.md:203-214` sigue diciendo que `/login` "setea la misma cookie de sesion" (hoy: local planta el token, remoto crea `calipso_sesion`), que "el token viejo sigue funcionando como recuperacion con `?token=`" (hoy: solo desde loopback), y no nombra `calipso_sesion`, los tipos `lector/tablero/navegador`, el alta por golpe ni que remoto = solo sesiones. Son 6-8 lineas; sin ellas el proximo agente que lea el archivo diseña contra un modelo de seguridad que ya no existe.

**M5. La subseccion "Migracion y despliegue" del spec dice lo mismo dos veces** (ledger T6). spec:75 y 77-82. Podar el parrafo 75.

**M6. `rechazada`/`revocada` no se podan y cada `/login` remoto agrega una sesion** (ledger T1 + ruling diferido de T4). `sesiones.py:439-460` (`crear_viva`) desde `server.py:763-764` sin dedup; `golpear` solo poda golpes vencidos. Con meses de uso `sesiones.json`, `/api/aparatos` y la lista de /fabrica crecen sin tope. Puede esperar; anotar: podar rechazada/revocada de mas de N dias en la proxima escritura.

**M7. Tres emisiones fuera de todo `try`** (ledger T8). `server.py:3040` (el `active_goal` antes del `try` de 3061), ~3323 y ~6923: un `WebSocketDisconnect(1008)` levantado por el proxy ahi escapa del handler y uvicorn imprime un traceback. Ruido, no comportamiento. Puede esperar.

**M8. `test_una_sesion_tablero_si_ve_el_tablero_de_economia` afirma `not in (401, 403)`** (ledger T4). Pasaria con 404 o 500. Cambiar a `== 200`. Trivial; puede ir en la ola o esperar.

**M9. El freno global `aparatos:*` bloquea tambien el sondeo VALIDO.** `server.py:485-490` contesta 429 antes de leer el body, asi que con el balde global caliente (20 fallos de quien sea) el aparato legitimo que sondea un id valido tambien rebota. El spec promete que no CUENTA (se cumple), no que no se bloquee; es el residual de disponibilidad que el ledger ya tiene anotado. Puede esperar; la opcion es mirar el id antes de aplicar el balde global en `estado`.

---

## 3. Triage de los "minor (deferred)" del ledger

### Deben cerrarse antes del merge

1. **T8:** "TOCTOU entre resolver la sesion en el handshake y la foto de la generacion (una revocacion en el medio deja un ws que nunca se entera) -- candidato a fix final: fotografiar la generacion ANTES de resolver". Razon: es el invariante de la fase 3; el arreglo es de 5 lineas y la escritura-antes-de-incrementar de `aparatos_revocar` lo hace correcto. (M1)
2. **T8:** "`_vigilar_socket` falla ABIERTO si el registro no trae hash_id -- candidato a fix final (fallar cerrado)". Razon: capa de autenticacion; se toca la misma funcion que el punto 1. (M1)
3. **T7:** "el repintado de 60 s DESHACE la eleccion del select (Pedro baja a lector, el intervalo repinta y el POST aprueba lo que sugirio el aparato) -- candidato a fix final". Razon: recalibrado a Important (I3): la sugerencia es input no autenticado y el bug le da al aparato el tipo que Pedro no eligio.
4. **T3:** "`await request.json()` sin tope de tamano en rutas SIN credencial (golpear/estado/canjear) -- candidato al fix final: rechazar Content-Length > 4 KB antes de leer". Razon: es la unica superficie NUEVA sin credencial de la rama; 6 lineas. (M2)
5. **T4:** "un calipso_token INVALIDO desde afuera nunca se limpia (tras rotar el token, las cookies viejas quedan un anio: la nota de despliegue promete limpieza que no ocurre) -- candidato al fix final: borrar la cookie remota este o no valida". Razon: es EL MISMO cambio que cierra el oraculo I2, y hace verdadera la nota de despliegue.

### Pueden esperar (con razon)

- **T1:** docstring de `resolver` como "lectura" aunque tome el flock en dos ramas (el docstring del modulo ya lo aclara: "salvo cuando resolver renueva o mata"); sufijo `.corrupto-<ts>` con resolucion de segundos (dos corrupciones en el mismo segundo es un borde teorico); validacion del tipo duplicada en `_validar` y `aprobar` (DRY menor); rechazada/revocada nunca se podan (M6: crecimiento lento, Pedro es el unico que loguea); `escribir_json_atomico` con modo levanta `FileExistsError` ante un temporal huerfano (el nombre lleva pid+thread; el `finally` lo limpia y el segundo intento pasa); `estado()` devuelve "viva" para aprobado-y-caduco (`canjear` ya devuelve None y el aparato vuelve a golpear).
- **T2:** `startswith` es prefijo crudo (`/fabricante` no existe; anotar para cuando exista); comodin comparado con `==` depende de tuplas (la tabla es de tuplas y el test la fija).
- **T3:** rama "revocar por sesion navegador" sin test directo -- **ya cerrado**: existe `test_revocar_desde_una_sesion_navegador_remota_corta_la_otra`; balde `aparatos:*` (umbral 20) nunca disparado en tests (la maquinaria es la del login, que si esta probada; el canario de separacion cubre lo que importa); `request.client.host if request.client else ""` repetido 7 veces (helper de una linea, estilo).
- **T4:** la renovacion de cookie se pierde si el request cae fuera de alcance (el siguiente request en alcance la renueva; un aparato que solo pide fuera de alcance no deberia conservarla); test del tablero con `not in (401,403)` (M8, trivial).
- **T5:** `_ws_autorizado` repite la rama de sesion del guard (dos copias de 6 lineas, aceptable); ningun test fija el orden sesion-primero (riesgo bajo: `test_una_revocacion_no_toca_el_ws_abierto_con_el_token` cubre la mitad que importa).
- **T6:** spec duplicado (M5, doc); test espejo de `projects/sesiones.json` en el zip (el de `projects/token` ya fija el patron).
- **T7:** `.alcance` a 13px no es "en grande" (esta en `--acento` y es la unica linea de color de la tarjeta: cumple la intencion); sin test de la suma del badge, del cartel ni del alert (el cartel y el badge tienen tests de arranque; el alert es `window.alert`); quinta copia del cuarteto pintarX (deuda de app.js, no de esta rama); el badge global no cuenta golpes (ruling 6, por diseno).
- **T8:** tres emisiones fuera de try (M7, ruido); `_run_chat_draft` con `ensure_future` puede dejar "Task exception was never retrieved" (preexistente en forma, ruido); falta el positivo en vivo del proxy (`test_el_socket_vigilado_no_deja_pasar_una_emision_de_una_revocada` cubre la logica y los tests de corte cubren la costura); peor caso del chat ocioso 30 s (`LATIDO_CHAT_S`, decision documentada).
- **Rulings parked que no reabro:** sesion gana sobre token tambien en loopback (orden del spec); una sesion fuera de alcance cae al token en `_ws_autorizado` (remoto no afloja nada porque el token exige loopback); el corte por EXPIRACION de reloj no pasa por generaciones (documentado en `_revocar_en_vivo`; muere en la proxima reconexion).

---

## 4. Lo bien hecho

- **El almacen** (`sesiones.py`) es el mejor archivo de la rama: hashes y nada mas en disco, el id nace en el canje (ruling que elimina el "id en claro esperando en disco" que el spec original tenia), 0600 sin ventana via `O_CREAT|O_EXCL` con modo (mejor que el "chmod despues" del plan), corrupcion preservada y avisada una sola vez por version, `permite` fail-closed hasta con un tipo que no es texto, y reloj inyectable en cada punto que mira la hora. Los 499 lineas de `test_sesiones.py` prueban comportamiento real (grep del json por el id devuelto, mtime intacto en `listar`, la aprobacion dormida que ya no se canjea).
- **El guard** sigue el orden del spec y lo endurece donde el spec se quedaba corto: `/setup` no se sirve a NADIE sin el secreto (el Critical del `("*","*")` cazado en T4), `_sin_credencial` unifica las dos ramas para no abrir oraculo por status/body, y `_expirar_token_viajero` cubre la poblacion que mas importa (el remoto que ya entro por `/login` y sigue mandando el token).
- **`_SocketVigilado`** es la decision de arquitectura correcta: envolver el socket una vez cubre los 60 puntos de emision (46 en `ws_chat` mas helpers, `Emisor` y el borrador suelto) sin tocar ninguno, reutiliza `WebSocketDisconnect` para que los `except` existentes limpien solos, y deja crudo el socket del token (la Ally no se revoca por esta capa). El latido de `_proximo_del_chat` con `wait_for` es la forma minima de despertar un chat ocioso sin enseñarle un evento nuevo a la PWA.
- **El freno propio** con claves `aparatos:*` y el canario de separacion (`test_martillar_golpear_frena_sin_tocar_el_balde_del_login`) cierran de verdad el DoS del TOTP que el spec temia.
- **Los tests de costura** usan `httpx.ASGITransport(client=(ip, ...))` para el remoto y `TestClient(client=...)` para los ws; los canarios del spec estan todos: aprobar ignora el tipo del golpe, tablero vs `/api/file`, lector vs `/fabrica`, cookie-token remota 401+vencida, `ws_chat` con token remoto = 1008, revocar corta el ws ocioso (con timeout en hilo para que un fallo no cuelgue la suite), el `tipo: null` editado a mano da 403 y no 500.
- **La UI**: nombre del aparato escapado siempre, `Object.hasOwn` para que "constructor" no se disfrace de tipo inofensivo, un badge por sub-pestana con un test a nivel HTML que ningun test de JS podia ver, el 403 del tablero convertido en cartel y no en alert, y el test de arranque que fija que el POST lleva lo que dice el selector en el momento del clic.
- **Trazabilidad**: cada desviacion del spec esta en el ledger con su ruling y su costo; los comentarios del codigo explican el POR QUE y citan el invariante; `test_seguridad_portones.py` cambia un solo assert y explica por que lo que afirmaba dejo de ser verdad.

---

## 5. La ola de fix sugerida (una sola, en este orden)

1. `_verify_totp` no crea el secreto (I1) + test.
2. Borrar la cookie-token remota presente, valida o no, en las dos ramas (I2 + minor T4) + test.
3. `pintarAparatos` conserva los selectores al repintar (I3) + test de node.
4. Foto de la generacion antes de `resolver` y `_vigilar_socket` fail-closed (M1) + test del orden.
5. Tope de 4 KB en las rutas exentas (M2) + test.
6. Si sobra: `_leer` con foto unica de la cache (M3), `AGENTS.md` seccion de seguridad (M4), podar el parrafo duplicado del spec (M5), `== 200` en el test del tablero (M8).

Despues: suite completa con exit code, node, y re-correr las dos sondas de esta revision (estan descritas arriba, ~40 lineas) antes del merge. Rotar el TOKEN sigue siendo paso obligatorio del despliegue.
