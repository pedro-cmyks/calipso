# Ronda adversaria: lente REGRESIONES (feat/capa-de-sesion, HEAD fa8fe89)

Base: main en c3a4d1382db6de62bb6b387f29732b2d66203086. Diff de la rama en
`.superpowers/sdd/2026-09-07-capa-de-sesion/rama-regresiones.diff` (21 commits, 19 archivos).
Revision de LECTURA sobre el checkout (sin mutar arbol, indice ni ramas). Sonda propia fuera del
arbol de tests, corrida y borrada al terminar (su contenido relevante esta al final).

## Corridas de referencia

- `.venv/bin/python -m pytest -q --ignore=test_chat_live.py` -> **1356 passed, 4 warnings in 30.41s, EXIT=0**
  (linea base de main: 1183 passed, 4 warnings; los 4 warnings son los preexistentes).
- `node --test` en `calipso/web/fabrica/` -> **396 pass, 0 fail, EXIT=0**.
- Sonda `sonda_regresiones.py` (25 casos) -> **25 passed, EXIT=0** (la primera corrida tuvo 1 fallo
  por una asercion MIA equivocada en P5c, corregida; ver abajo).

## Hallazgos

### H1 (Important): el boton "Abrir" del checklist de launch para el TOTP lleva a `/setup` a secas, que ya no entra desde la Ally

- Donde: `calipso/server.py` `api_launch_checklist`, item `"totp"`: el detail dice
  `"Abre /setup?token=<el token> en la propia maquina."` pero el `action` sigue siendo `"/setup"`
  (lineas ~3893-3900). `calipso/web/index.html` ~1483 lo pinta como `<a class="toolbtn" href="${esc(item.action)}">Abrir</a>`.
- Antes de la rama: Pedro en la Ally (cookie-token, 127.0.0.1) tocaba "Abrir" y `/setup` servia el QR
  (el guard viejo dejaba pasar la cookie valida antes de mirar nada). Con la rama, la regla 1 del guard
  exige `?token=` en la query y la regla 2 rebota a `/login` mientras el secreto falte.
- Reproducido (sonda P5b):
  ```
  P5b {'key': 'totp', 'label': 'Login TOTP', 'ok': False,
       'detail': 'Abre /setup?token=<el token> en la propia maquina.', 'action': '/setup'}
  P5b click 303 /login        <- GET /setup con calipso_token valido desde 127.0.0.1, sin ?token=
  ```
- Es justo el flujo de primer arranque: `launch_calipso.py` abre `/` sin token (C4), Pedro entra por
  `?token=` (la unica pista del LOGIN_HTML), mira el checklist y el unico boton que le ofrece el server
  para enrolar el autenticador lo manda a la pantalla de login que no puede funcionar sin secreto.
- Arreglo minimo: mientras `_TOTP_SECRET_FILE` no exista, el item no debe ofrecer `action="/setup"`
  (`action=None`, dejando el detail como instruccion) -- o el checklist arma la URL con el token que la
  Ally ya tiene (pero eso vuelve a poner `?token=` en el historial, lo que C4 quiso evitar).
  Alternativa de spec, a decidir por el controlador: aceptar en la regla 1 la cookie-token valida desde
  loopback ademas de `?token=`: la cookie ES el token (`_valid(cookies[COOKIE])`), prueba la misma
  posesion, y otro uid no lee el jar de cookies del navegador de Pedro. El spec argumenta "loopback no es
  Pedro", pero la cookie-token no es "loopback a secas".

### H2 (Minor, PREEXISTENTE, agravado por la doc de la rama): cualquier `POST /login` con 6 digitos crea `totp_secret` y cierra para siempre la "unica ventana" de `/setup`

- Donde: `login_submit` -> `_verify_totp` -> `_get_totp_secret()` (`calipso/server.py` ~219-247 y ~750):
  si el archivo no existe, lo GENERA y lo escribe. Esas lineas no estan en el diff de la rama: el
  comportamiento es de main. Pero la rama documenta `/setup?token=` como "la unica puerta"
  (AGENTS.md 208 y 297; checklist "Abre /setup?token=..."; spec seccion 3 punto 1) y endurecio
  `/setup`, asi que ahora ES la forma en que Pedro se queda sin poder enrolar: `launch_calipso.py`
  aterriza en `/login`; un codigo tecleado ahi (o un remoto probando `000000`) escribe el secreto sin
  que nadie haya visto el QR, `/setup` pasa a "ya esta configurado" y el checklist dice
  "Autenticador configurado.".
- Reproducido (sonda P5c), con el secreto ausente al inicio:
  ```
  P5c login remoto 401          <- POST /login code=123456 desde 192.168.1.66
  P5c secreto existe: True      <- totp_secret aparecio
  P5c setup?token= 303 /setup   <- la ventana ya no aplica; cae a _session_response
  P5c /setup con cookie: 200 otpauth: False texto: <p class=m>Por seguridad, esta pantalla ya no muestra el QR ni el secreto...
  P5c checklist True Autenticador configurado.
  ```
- Arreglo: `_verify_totp` debe devolver False sin crear nada cuando `_TOTP_SECRET_FILE` no existe; el
  unico creador del secreto tiene que ser `setup_page` (que ya esta detras de la ventana). No es un
  cambio de la capa de sesion, pero conviene cerrarlo junto con H1 porque los dos viven en el mismo
  primer arranque.

### H3 (Minor): en la Ally, una cookie `calipso_sesion` de tipo restringido tapa a la cookie-token valida, y el 403 no la limpia

- Donde: `auth_guard` (`calipso/server.py` ~490-520): la rama de sesion corre antes que la del token
  (orden 3 antes que 4 del spec). Si la sesion resuelve viva y `permite` dice que no, devuelve 403 sin
  mirar que el mismo request trae el TOKEN valido desde loopback. El 403 no borra `calipso_sesion`
  (solo `_expirar_token_viajero` toca la cookie-token, y solo fuera de loopback), asi que el estado
  persiste hasta 30 dias.
- Antes de la rama: la cookie-token valida entraba siempre. Ahora, en loopback con las dos cookies:
  ```
  P4 403 {"detail":"fuera del alcance del aparato"} None   <- /api/tree con calipso_token=TOKEN + calipso_sesion=<tablero>
  P4 sin sesion 200                                          <- el mismo request sin la cookie de sesion
  P4r 200                                                    <- con una sesion REVOCADA cae al token (bien)
  ```
- Solo pasa con estado auto-infligido (un canje hecho desde el navegador de la Ally, por ejemplo
  probando el flujo del tablero en 127.0.0.1), y el orden es el del spec. Por eso Minor. Arreglo si se
  quiere: en loopback, cuando el alcance rechaza el path y `_valid(cookies[COOKIE])`, seguir de largo a
  la rama del token en vez de cortar en 403.

## Lo que se ataco y aguanto (verificado, sin hallazgo)

| Punto de la lente | Evidencia | Veredicto |
|---|---|---|
| Tauri: `lib.rs` navega a `http://127.0.0.1:8000/?token=` | P1a: `303 /` + `Set-Cookie: calipso_token=<TOKEN>; HttpOnly`. P1b: `/api/launch/checklist?token=` -> 200 + Set-Cookie. P1c: cookie vieja invalida + `?token=` nuevo -> `303 /fabrica` + cookie replantada (rotacion). `_session_response` sin cambios en el diff. | Intacto |
| La Ally por cookie-token en loopback | P2: `/`, `/fabrica`, `/manifest.json`, `/sw.js`, `/fabrica/manifest.json`, `/static/fabrica/aparatos.js`, `/static/fabrica/app.js`, `/api/launch/checklist`, `/api/aparatos` -> 200 y sin Set-Cookie. | Intacto (salvo H3) |
| PWA local, ws locales | P3: `/ws/mapa` con cookie-token desde testclient entra y recibe `{'evento': 'latido', 'seq': 0}`; `/ws/chat` entra. `?token=` en la URL del ws -> 1008 (nunca se acepto; sin cambio). | Intacto |
| Rutas antes publicas/exentas | P2s sin credencial: `/`, `/static/...`, `/manifest.json`, `/sw.js` -> 303 `/login`; `/api/tree`, `/ws/chat` -> 401; `/login` -> 200. Igual que antes (`_sin_credencial` es el mismo par 401/303). | Intacto |
| Cookie-token remota | P9: 401 + `calipso_token=""; Max-Age=0`. Cambio deliberado (invariante 2), documentado en spec "Migracion y despliegue". | Cambio esperado |
| Primer arranque | P5a: `/setup` con cookie-token loopback y sin secreto -> 303 `/login` (documentado en AGENTS.md 208/297 y en el detail del checklist). Ningun texto de usuario apunta a `/setup` a secas... salvo el `action` del checklist (H1). LOGIN_HTML solo menciona `?token=` como recuperacion. RUNBOOK.md/SETUP.md no hablan de `/setup`. | H1, H2 |
| `launch_calipso.py` | Sin cambios en la rama; abre `/` sin token (C4) y lanza `python calipso/server.py` (`proxy_headers=False`, sin cambios). | Intacto |
| CLIs y `dispatch.py` | `grep calipso_token\|CALIPSO_TOKEN\|127.0.0.1:8000` fuera de tests: solo `server.py`, `lib.rs`, y `plugins.py`/`memory.py` que hacen `env.pop("CALIPSO_TOKEN")`. `dispatch.py` no llama a la API de Calipso. Nada que regresar. | N/A |
| Backups | P8: zip de un home con `sesiones.json`, `token` y `sesiones.json.corrupto-<ts>` -> `['sesiones.json.corrupto-1757000000']`. Los `.corrupto-*` SI se respaldan y NO son NUNCA: decision explicita en los comentarios de `backup.py:36` y `acciones.py:179` ("Solo el nombre exacto"). Su contenido son hashes e id_pedido de un almacen que ya fue reemplazado por uno vacio (nada de eso resuelve), y el zip nace 0600. | Sin hallazgo |
| Motor de permisos | P8: `es_credencial_del_servidor` True para `token`, `totp_secret`, `sesiones.json`; la tupla conserva los dos viejos. | Intacto |
| Freno del login | P7: tras 8 golpes remotos las claves son `['aparatos:*', 'aparatos:192.168.1.66']` y `/login` remoto sigue 401 (no 429); tras 6 logins malos aparecen `'*'` y `'192.168.1.66'` aparte. `_login_exito` solo borra la clave del host del login. El decaimiento de `_login_fallo` recorre todas las claves, pero es idempotente en el tiempo para los contadores (n1+n2 ventanas = total) y ya lo disparaba cualquier fallo de cualquier host antes de la rama: los golpes solo agregan disparadores, no regalan rafagas (el 429 del freno no cuenta fallo ni dispara el decaimiento). | Intacto |
| Latencia del guard | P6: 200 `resolver()` seguidos sobre una sesion viva = **1** lectura de disco (`_leer_disco`) y **0** candados; el resto es `os.stat` + sha256. P6b: la Ally (cookie-token, sin cookie de sesion) no llama a `resolver` (0 llamadas) -- ni hilo ni stat. `_TOTP_SECRET_FILE.exists()` solo corre para `path == "/setup"`. | Intacto |
| Tests preexistentes debilitados | `git diff main..HEAD -- 'test_*.py' '*.test.js' \| grep '^-'`: 5 lineas borradas: una lista de ids del DOM de mentira (arranque.test.js, ampliada), una linea de docstring, y `test_cookie_si_entra_desde_afuera` (200) reescrito como `test_la_cookie_token_ya_no_entra_desde_afuera` (401). Esa inversion es el invariante 2 del spec, documentada en el propio test. Ninguna asercion relajada. `test_seguridad_portones::test_token_por_url_no_entra_desde_afuera` sigue tal cual. | Sin hallazgo |
| Service worker | `SHELL` suma `/static/fabrica/aparatos.js`; `CACHE` sigue `"calipso-shell-v3"`. Los dos commits anteriores que sumaron modulos al SHELL (2e1680f, a83dd5d) tampoco lo subieron: es la convencion del repo, y la estrategia es red-primero con `addAll` en el install (un sw.js byte-distinto reinstala y re-baja el shell). | Sin hallazgo |
| `badge-submesa` -> `badge-permisos` | `grep badge-submesa calipso/` vacio: sin referencias colgadas en js/css/html. La unica linea de CSS borrada solo gana `flex-wrap: wrap` en `#submesa`. | Intacto |
| `ws_chat` con el socket envuelto | `_receiver` hace `await ws.receive_text()` dentro de `try/except Exception -> inbox.put(None)`: el `WebSocketDisconnect(1008)` del vigilado termina el bucle como una desconexion normal. `_proximo_del_chat` usa `asyncio.wait_for(inbox.get(), 30)` en Python 3.14.3: `Queue.get` es seguro ante cancelacion (el item queda en el deque y despierta al proximo getter), asi que un mensaje que llegue justo al vencer el plazo no se pierde. No hay `isinstance(ws, WebSocket)` ni `async for ... in ws` en server.py que el proxy `__getattr__` no cubra. El socket con token queda crudo (`_vigilar_socket`). | Intacto |
| `proxy_headers=False` | `__main__` no cambio; el guard sigue leyendo `request.client.host` como antes. Tauri lanza `uvicorn` por CLI (proxy_headers por defecto True, `forwarded_allow_ips` 127.0.0.1) bindeado a 127.0.0.1: sin cambio respecto de main. | Intacto |
| `escribir_json_atomico(modo=None)` | Camino sin `modo` byte por byte igual (solo movio el `json.dumps` antes del `try`: si falla la serializacion, antes lo atrapaba el `finally` con un tmp inexistente; ahora no llega a crear el tmp). | Intacto |

## No reproducido / notas

- `request.client is None` (solo con un bind por unix socket, que Calipso no usa): antes la cookie-token
  entraba igual; ahora `host=""` no es loopback y rebota. No reproducido en un despliegue real; nota.
- Un `tablero` no puede bajar `/sw.js` ni `/` (fuera de su alcance), asi que su PWA no registra el
  service worker: no es regresion (el tipo es nuevo); le corresponde a la lente de completitud.

## Sonda (corrida y borrada)

`/tmp/claude-1000/-var-home-pedro/7ea3cff5-be99-4946-a05c-6203e4bc2f84/scratchpad/sonda_regresiones.py`,
invocada con `cd /var/home/pedro/calipso && .venv/bin/python -m pytest -q -p no:cacheprovider -s <ruta>`.
Fija `CALIPSO_HOME` a un `mkdtemp` ANTES de importar calipso; aisla `sesiones._ruta`, `sesiones._CACHE`,
`srv._TOTP_SECRET_FILE` (tmp_path), congela `srv._login_reloj` y limpia `_login_fallos`/`_ws_generaciones`
por test (mismo andamiaje que `test_sesiones_server.py`). Host remoto = `httpx.ASGITransport(client=("192.168.1.66", 4321))`,
loopback = `("127.0.0.1", 4321)`; websockets con `TestClient` (host "testclient").

Casos: P1 (3) Tauri/`?token=` loopback; P2 (9+1) Ally cookie-token y rutas sin credencial; P3 (2) ws
locales; P4 (2) orden sesion/token en loopback; P5 (3) primer arranque; P6 (2) lecturas de disco y
llamadas a `resolver`; P7 (1) claves del freno; P8 (1) backup + NUNCA; P9 (1) cookie-token remota.

Salida completa de la corrida final (25 passed, EXIT=0):
```
P1a 303 / calipso_token=X59XG7FvnCpgQSgm; HttpOnly
P1b 200 calipso_token=X59XG7FvnCpgQSgm; HttpOnly
P1c 303 /fabrica
P2 / 200 ... P2 /api/aparatos 200   (las 9 rutas en 200, sin Set-Cookie)
P2s / 303 /login | /static/fabrica/app.js 303 /login | /manifest.json 303 /login | /sw.js 303 /login | /api/tree 401 | /ws/chat 401
P3 mapa {'evento': 'latido', 'seq': 0} | P3 chat: entro | P3 url 1008
P4 403 {"detail":"fuera del alcance del aparato"} None | P4 sin sesion 200 | P4r 200
P5a 303 /login
P5b {'key': 'totp', ..., 'detail': 'Abre /setup?token=<el token> en la propia maquina.', 'action': '/setup'} | P5b click 303 /login
P5c login remoto 401 | P5c secreto existe: True | P5c setup?token= 303 /setup | P5c /setup con cookie: 200 otpauth: False | P5c checklist True Autenticador configurado.
P6 lecturas de disco en 200 resolver: 1 candados: 0 | P6b 200 resolver llamado: 0
P7 claves tras golpes: ['aparatos:*', 'aparatos:192.168.1.66'] | P7 login remoto tras golpes: 401 | P7 claves tras logins: ['*', '192.168.1.66', 'aparatos:*', 'aparatos:192.168.1.66']
P8 zip: ['sesiones.json.corrupto-1757000000'] | P8 nunca token: True totp: True sesiones: True corrupto: False
P9 401 calipso_token=""; expires=...; Max-Age=0; Path=/; SameSite=lax
```
(El token que aparece es el generado en el home temporal de la sonda, no el de Pedro.)
