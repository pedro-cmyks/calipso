# Ronda adversaria -- lente EFICACIA -- rama feat/capa-de-sesion

**Fecha:** 2026-09-08
**Rama revisada:** feat/capa-de-sesion en `fa8fe89` (bifurcada de main en `c3a4d13`). Durante la revision entro `d3fc3ba` (docs: transcripcion del smoke), que no toca codigo: todo lo de abajo vale igual sobre HEAD.
**Metodo:** tests-sonda fuera del arbol (`scratchpad/sonda_eficacia*.py`, borrados al terminar), corridos con `.venv/bin/python -m pytest -p no:cacheprovider` y `CALIPSO_HOME` a un temporal fijado en el propio archivo antes del import. Loopback = `TestClient` ("testclient"); remoto http = `httpx.ASGITransport(client=(ip, 4321))`; remoto ws = `TestClient(srv.app, client=(ip, p))`; paths raros = scope ASGI crudo (httpx normaliza `..`); y para el corte del ws_chat, un driver ASGI crudo que registra cada `send` de la app, sin TestClient en el medio.
**Regla:** solo figura lo reproducido (salida citada) o lo que el codigo muestra sin ambiguedad. Lo no reproducido se dice como tal.
**Lectura, no mutacion:** el arbol, el indice y HEAD no se tocaron; `ls -lat ~/.calipso` no tiene ninguna entrada posterior al 2026-09-07 (el md5 del listado cambio por `..`, el home de Pedro, ajeno a esta revision).

---

## Hallazgos

### H1 (Important) -- Una sesion `navegador` remota se apropia de la credencial que Pedro aprobo para OTRO aparato

**Donde:** `calipso/server.py:908-913` (`aparatos_listar` devuelve `sesiones.listar()` tal cual a cualquier sesion con alcance `*`) + `calipso/sesiones.py:524-535` (`listar` incluye `id_pedido` en cada fila, tambien en las `viva` sin `hash_id`, o sea aprobadas y todavia no canjeadas).

**Ataque:** Pedro aprueba desde la Ally un golpe del lector (tipo `tablero`). Antes de que el lector canjee (sondea cada pocos segundos: la ventana es de segundos, y de minutos si el lector estaba dormido), una sesion `navegador` remota hace `GET /api/aparatos`, lee el `id_pedido` del registro aprobado y lo canjea. Se lleva la cookie con el tipo que Pedro eligio; el lector recibe 404; y la cookie robada SOBREVIVE a la revocacion del navegador ladron.

**Sonda (`test_inv4_HALLAZGO_navegador_remoto_*`), salida:**
```
LISTADO VISTO POR EL NAVEGADOR: {'hash_id': None, 'id_pedido': 's1Q-Q0nbz6_BMd8wpteil3JcU23riRUu4GJryowg2yk',
  'aparato': 'lector de Pedro', 'tipo': 'tablero', ..., 'estado': 'viva', 'efectivo': 'viva'}
CANJE DEL LADRON: 200 {"ok":true,"tipo":"tablero"} calipso_sesion=F_bDx5s6s4J-TiVvmytSstD6U_EWbi1nhv8qB9HeaKs;
CANJE DEL APARATO LEGITIMO: 404 {"detail":"pedido desconocido"}
LA SESION ROBADA DESPUES DE REVOCAR AL NAVEGADOR: 200
```

**Por que importa (severidad honesta):** el atacante ya tiene alcance `*` (necesito el TOTP de Pedro o una cookie navegador robada), asi que no es escalada de privilegios. Lo que gana es PERSISTENCIA: una segunda identidad, con el nombre del aparato de Pedro, que la revocacion del navegador no toca, y que en /fabrica se ve como el lector legitimo. El propio codigo trata al `id_pedido` como credencial ("El 404 no repite el id_pedido: es la credencial del canje", `server.py:881`) y despues lo publica en un listado que el navegador lee. De yapa: la UI (`aparatos.js:93-99`) no ofrece ningun boton para una aprobacion sin canjear ("aprobado, esperando al aparato"), asi que Pedro tampoco puede cancelarla desde /fabrica si sospecha.

**Arreglo:** `listar()` no devuelve `id_pedido` para registros que ya no estan `golpeando` (una vez aprobado, el unico que lo necesita es el aparato que golpeo y ya lo tiene); y el endpoint solo incluye `id_pedido` cuando el pedido viene de loopback (la UI aprueba desde la Ally; el navegador no aprueba ni rechaza, no le sirve para nada). Opcional: un boton "cancelar aprobacion" (= `rechazar`) en la tarjeta de "esperando al aparato".

### H2 (Minor, contrato del spec roto) -- ws_chat: un mensaje de la sesion revocada se procesa y se persiste antes del corte, y en ese camino el 1008 se pierde

**Donde:** `calipso/server.py:682-684` (`_SocketVigilado.receive_text`: `await self._vigilar()` y DESPUES `await self._ws.receive_text()`), `server.py:3048` (`_receiver`: `await inbox.put(await ws.receive_text())`), `server.py:650-668` (`cerrar_revocado` no es idempotente; el segundo `close` levanta `RuntimeError` suprimido), `server.py:3655` (`finally: rtask.cancel()`).

**Mecanismo (sin ambiguedad en el codigo):** el receptor ya esta bloqueado en el receive CRUDO cuando llega la revocacion; el chequeo de la generacion corre antes de esperar, no al recibir. El mensaje que entra despues de revocar se entrega al handler entero. Con un chat activo (el caso normal de Pedro), `chats.append(chat_id, "user", ...)` (`server.py:3099`) lo persiste ANTES de la primera emision (`send_json({"type": "thinking"})`, `server.py:3105`), que es la que corta. Ademas, el receptor y el bucle principal corren a cerrar a la vez: el receptor llama `close(1008)`, cuyo `send` suspende en el checkpoint del transporte (anyio/uvicorn); el bucle principal llama `close` -> `RuntimeError` (estado ya DISCONNECTED) -> `WebSocketDisconnect` -> `finally: rtask.cancel()` cancela al receptor con el frame de cierre sin encolar. El handler retorna sin ningun `websocket.close`; uvicorn cierra el transporte a secas (`run_asgi` -> `transport.close()`): el cliente ve un cierre anormal, no el 1008 que el spec promete ("el cliente ve una sola razon de cierre").

**Sonda D (driver ASGI crudo, `test_ws_chat_crudo_sesion_revocada_manda_un_mensaje`), salida (8 combinaciones):**
```
texto='' chat_activo=True  send_suspende=False: emitidos=[accept, close 1008]; persistido=[]
texto='hola desde la revocada' chat_activo=True  send_suspende=False: emitidos=[accept, close 1008]; persistido=[('user', 'hola desde la revocada')]
texto='hola desde la revocada' chat_activo=False send_suspende=True:  emitidos=[accept]; persistido=[('user', 'hola desde la revocada')]
texto='hola desde la revocada' chat_activo=True  send_suspende=True:  emitidos=[accept]; persistido=[('user', 'hola desde la revocada')]
```
(en las combinaciones con `chat_activo=False` posteriores, el chat activo lo dejo el propio handler del caso anterior: `chats.create`.)
**Con el TestClient de Starlette (sonda B):** mensaje vacio -> `WebSocketDisconnect` a los 0.01 s; mensaje "hola" -> el cliente no recibe NADA en 40 s y termina en `EndOfStream()`.

**Alcance real:** un solo mensaje por socket que estuviera abierto al revocar (el handshake nuevo ya rebota); no llega a `_decide` ni al modelo (la emision `thinking` corta antes). Es contaminacion del historial de chat de Pedro y perdida del codigo de cierre, no ejecucion. Por eso Minor -- pero contradice el spec letra por letra ("re-chequea la generacion al recibir un mensaje").

**Arreglo:** en `receive_text`/`receive_json`, vigilar DESPUES de que el receive crudo devuelva (ademas de antes, si se quiere); y hacer `cerrar_revocado` idempotente (una bandera `_cerrado`: el primero cierra, los demas solo levantan `WebSocketDisconnect`), para que el `rtask.cancel()` no se coma el frame.

### H3 (Minor, interleaving forzado) -- TOCTOU en el handshake: una revocacion entre `resolver` y la foto de la generacion deja el ws vigente para siempre

**Donde:** `calipso/server.py:573` (`_ws_autorizado` resuelve en `to_thread`), `server.py:3030/3037` y `6916/6920` (el handler toma `sesion` y recien despues `_vigilar_socket`), `server.py:642` (`_SocketVigilado.__init__` saca la foto `_generacion_de(hash_id)` en ese momento).

**Mecanismo:** si `_revocar_en_vivo` corre entre el retorno del hilo de `resolver` (registro viva) y la construccion del vigilado, la foto toma la generacion YA incrementada (1) y `vigente()` compara 1 == 1 de ahi en adelante. La ventana real es la reanudacion del coroutine tras `to_thread` (milisegundos); requiere que Pedro revoque justo mientras el aparato hace el handshake. NO lo reproduje en carrera libre: lo reproduje forzando el interleaving (un `resolver` que revoca en el almacen y en `_ws_generaciones` antes de devolver el registro viva).

**Sonda (`test_inv9_HALLAZGO_toctou_revocar_entre_resolver_y_la_foto`), salida:**
```
generacion tras el handshake: {'f9c8d78d...': 1}
(almacen: estado == "revocada")
Failed: ws de sesion REVOCADA sigue abierto y emitiendo: el ws seguia abierto 1.5 s despues
```

**Arreglo:** sacar la foto ANTES de resolver (`gen = _generacion_de(sesiones._hash(galleta))` en `_ws_autorizado`, o un contador global de revocaciones leido antes del `to_thread`) y pasarsela a `_SocketVigilado`; o, mas simple, tras construir el vigilado volver a resolver la cookie (barato: un stat y un sha256) y rebotar si ya no esta viva.

### H4 (Minor) -- `tipo` que no es hashable => 500 en `golpear` (anonimo, remoto) y en `aprobar`

**Donde:** `calipso/sesiones.py:277` (`_validar`: `if tipo not in ALCANCES`) y `sesiones.py:369` (`aprobar`, idem). Con `tipo` = lista o dict (JSON valido), `x in dict` levanta `TypeError`, que ni `ValueError` ni `Lleno` atrapan (`server.py:837-841`, `888-891`). Contradice `_cuerpo_json` ("un cuerpo basura tiene que morir en la validacion del almacen -422 y un fallo contado- y no en un 500", `server.py:806-809`).

**Sonda, salida:**
```
golpear tipo ['lector'] -> 500 Internal Server Error
golpear tipo {'a': 1}   -> 500 Internal Server Error
aprobar tipo ['navegador'] -> 500 Internal Server Error
aprobar tipo {'a': 1}      -> 500 Internal Server Error
(1, None, True -> 422, bien)
```
Sin consecuencia de seguridad (el fallo del freno ya se conto antes en `golpear`); es un 500 con traceback en el log a disposicion de cualquiera sin credencial. **Arreglo:** `if not isinstance(tipo, str) or tipo not in ALCANCES` en los dos lugares.

### H5 (Minor, diseno heredado del login) -- El balde global `aparatos:*` deja que terceros anonimos frenen al sondeo legitimo y al alta de aparatos nuevos

**Donde:** `calipso/server.py:352-355` (`_aparatos_espera` = max(host, global)) y `server.py:486-490` (el guard lo aplica ANTES del endpoint, sin saber si el `id_pedido` que viene es valido). El spec dice "el sondeo legitimo es gratis": es gratis para CONTAR, no para ser atendido.

**Ataque:** cada direccion tiene 5 fallos sin castigo. 4 direcciones x 5 `estado` con id basura = 20 en una rafaga, y desde ahi el balde global castiga a TODOS. Se sostiene con UN request cada 901 s (el decaimiento resta uno por ventana de calma y el fallo lo repone). Con 6 direcciones y ~35 min de reloj (esperando los Retry-After) el global llega a 28-30 y el castigo al tope de 900 s.

**Sonda C (`test_1_rafaga_de_30_fallos_desde_6_direcciones`) y B (`test_b_freno_global_con_hosts_multiples_sostenido`), salida:**
```
30 requests anonimos: [404 x19, 429 x11]; balde global=20; sondeo legitimo -> 429 Retry-After=3
  +901 s: hostil 404, legitimo 429 Retry-After=3 global=20   (x3, sostenido)
---
baldes={'aparatos:*': 29, ...}; ... +901 s: hostil 404, legitimo 429 (Retry-After 513), global=28  (x4)
login remoto durante todo esto: 401        <- el balde del login queda intacto (separacion OK)
golpear de un aparato nuevo: 429
```
Un solo host NO alcanza (medido: se estanca en ~14 por el decaimiento; la primera version de mi sonda se colgo justo por eso). En Tailscale/LAN, 4-6 direcciones son un solo atacante con IPv4+IPv6 o un par de nodos. **Arreglo barato:** en `aparatos_estado` y `aparatos_canjear`, no aplicar el balde GLOBAL cuando el `id_pedido` del body es valido (mover el chequeo del freno al endpoint, despues de `sesiones.estado`), o aplicar solo el balde por host al sondeo. El login ya acepta este mismo riesgo a sabiendas; aca lo nuevo es que ademas bloquea a un aparato que YA fue aprobado y solo quiere canjear.

### H6 (Minor) -- Un 403 "fuera del alcance" renueva `ultima_vez` en el almacen y NO re-planta la cookie

**Donde:** `calipso/server.py:499-511`: `resolver` (que renueva con histeresis, `sesiones.py:510-521`) corre ANTES de `permite`; si el alcance rebota, el almacen ya quedo renovado y la respuesta 403 sale sin `Set-Cookie`.

**Sonda (`test_HALLAZGO_una_sesion_fuera_de_alcance_se_renueva_igual`), salida:**
```
ultima_vez antes: 2026-09-08T14:53:00.248711+00:00  despues del 403: 2026-09-08T16:53:00.248880+00:00
set-cookie en el 403: None
```
Efecto: un aparato que solo pide cosas vedadas mantiene su sesion viva hasta los 180 dias ("la sesion se renueva usando": un 403 no es usar), y el almacen y la cookie se desfasan (la cookie vence a los 30 dias mientras /fabrica sigue diciendo viva). Sin agujero de acceso. **Arreglo:** renovar solo si `permite` pasa (o pasar el path/metodo a `resolver`, o mover la renovacion a despues del `call_next`).

### H7 (Minor, PREEXISTENTE en main) -- Un remoto anonimo quema la ventana del primer arranque: `POST /login` con 6 digitos crea `totp_secret`

**Donde:** `calipso/server.py:239-243` (`_verify_totp` -> `_get_totp_secret()`, que en `server.py:219-226` genera y ESCRIBE el secreto si no existe). Ya estaba asi en main (`c3a4d13`, mismas lineas 234/243); lo que cambio en la rama es que `/setup` ahora exige las tres condiciones (`server.py:461-486`) y el spec habla de esa ventana como cosa protegida.

**Sonda (`test_setup_HALLAZGO_un_remoto_anonimo_quema_el_primer_arranque`), salida:**
```
login remoto anonimo: 401 secreto creado: True
/setup?token= de Pedro despues: 303 qr: False done: False   (-> /setup -> "TOTP ya esta configurado")
```
Pedro nunca ve el QR: el secreto lo genero un desconocido (no lo vio; no es confidencialidad), y el login remoto queda inutilizable hasta que Pedro borre `~/.calipso/totp_secret` a mano. **Arreglo:** `_verify_totp` devuelve False si el archivo no existe (crearlo es cosa de `setup_page`, y solo ahi).

---

## Lo que aguanto (todo reproducido con sondas; se lista para que conste que se intento)

**Invariante 2 (remoto = solo sesiones):** cookie-token remota en http -> 401 + `Max-Age=0`; `?token=` remoto -> 401 sin expirar nada; `::ffff:192.168.1.66` es remoto; `request.client = None` es remoto (401) y el freno lo clava en `aparatos:`; ws chat y mapa con cookie-token remota -> 1008; `?token=` en la URL del ws -> 1008 (remoto Y loopback: nunca lo acepto); ws remoto con cookie-token + sesion revocada -> 1008; loopback con token + sesion revocada entra como maquina. El TOKEN no aparece en ningun body (grep; `server.py:7279` lo enmascara en logs).

**Invariante 3 (alcance fail-closed):** tablero contra 23 paths raros por scope ASGI crudo (`/API/file`, `//api/file`, `/fabrica/../api/file`, `/fabrica/../../api/file`, `/static/../sesiones.json`, `/static/../../.calipso/token`, `/api/file ` (espacio), `/api/file;x`, `/fabrica;/api/file`, `/api//file`, `/api/file/`, `/api/file\n`, `/api/economia/../file`, `/api/economia/bus/../../file`, `/fabrica%2F..%2Fapi%2Ffile`, `/api%2Ffile`, `/`, `/manifest.json`, `/sw.js`, `/docs`, `/openapi.json`) -> 403/404, nunca contenido (`/setup` dio 303 por la regla del secreto ausente, que corre antes del alcance: sin QR, no es fuga); `?path=` no cambia el path; 27 combinaciones metodo/ruta vedadas (HEAD/OPTIONS `/fabrica`, PATCH/PUT/DELETE sobre la mesa, `permisos/concedidos/*/revocar`, `permisos/techo`, `economia/cierre|abrir|sembrar|frontera/acunar|cola/*/atender`, `plantel/modo|parar`, `routines` POST y `*/run`, `aparatos` GET/aprobar/revocar, `file` PUT, `commands/run`, `config` GET/PUT, `project/open`, `memory`, `backup`) -> 403; lector no llega a nada existente; ws tablero->chat y lector->mapa -> 1008. Razonamiento adicional sobre `%2F`: el router matchea sobre `scope["path"]` y el guard sobre `request.url.path` (un unquote mas); para que el router matchee una ruta exacta el path no puede llevar `%`, asi que la doble decodificacion no abre nada.

**Invariante 4:** aprobar desde loopback sin credencial -> 401; con sesion tablero -> 403; navegador remoto aprobar/rechazar -> 403; revocar por tablero/lector -> 403, anonimo -> 401, cookie-token remota -> 401; aprobar vencido (11 min), ya aprobado o rechazado -> 404.

**Invariante 6:** 25 golpes -> 5 x 200 y 20 x 429 con `Retry-After` >= 1; `/login` sigue 401 (no 429) y sus claves no aparecen; tope 5 desde hosts distintos -> "ya hay 5 golpes esperando"; ids raros en `estado`/`canjear` (int, lista, None, dict, body lista o string) -> 404, nunca 500.

**Invariante 7:** archivo 0600, sin el id ni el `id_pedido` en claro; 12 formas de almacen roto (json invalido, lista, `sesiones` dict, registros no-dict, `hash_id` null, sin tipo, tipo `dios`, fechas null/ilegibles, estado `zombi`, `hash_id` int, `id_pedido` int) con 9 cookies raras cada una (el id, el HASH, vacia, `null`, 5000 chars, `None`, `\x00`, `a;b`, `%00`) -> 401 siempre, y despues se sigue escribiendo; el corrupto queda en `sesiones.json.corrupto-<ts>` con el contenido original.

**Invariante 8:** canje concurrente por http con 8 hilos y por el almacen con 8 hilos -> exactamente UNA cookie (`[404, 404, 404, 200, 404, 404, 404, 404]`); nombre del aparato: 60 -> 200, 61 -> 422, tab/salto/RTL override/zero-width/bidi -> 422, vacio/espacios/None/int/lista -> 422, `<script>` -> 200 pero `aparatos.js:74-105` lo pasa por `escapar()` (leido: `&<>"'`), emoji -> 200. (`nbsp` al final entra porque `strip()` lo quita: correcto.)

**Invariante 9:** rechazada no se aprueba ni se canjea; revocada no vuelve a entrar ni se re-canjea; revocar dos veces -> 404; ws ocioso revocado cortado por el latido (1008); ws_mapa cortado en el tick.

**Invariante 10:** grep de `sesiones.(golpear|aprobar|rechazar|revocar|canjear|crear_viva|resolver)(` en server.py: 0 llamadas fuera de `to_thread`; `estado` y `listar` (sin candado) van directo o en `def` sincrono, como dice el spec.

**/setup, 8 combinaciones:** solo loopback + sin secreto + `?token=` valido muestra el QR (y crea el secreto); las otras 7 -> 303 sin QR y sin crear el secreto (salvo H7, que entra por `/login`).

**Login remoto:** 303 con `calipso_sesion=...; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax`, sin `calipso_token` ni el TOKEN; crea una sesion `navegador`. `crear_viva` sin tope: 12 logins = 12 sesiones, pero solo con TOTP (Pedro), no es palanca anonima.

## No reproducido / fuera de la lente (para las otras)

- **Caducidad por reloj con el ws abierto:** medido (sonda `test_inv5_...`): un ws_mapa tablero sigue emitiendo con la sesion "caduca" en `listar()`. Es el LIMITE CONOCIDO que documenta `_revocar_en_vivo`; no lo cuento como hallazgo.
- **La cookie de sesion sombrea al token en loopback:** `TestClient` con token + sesion tablero -> `/api/tree` 403, y `?token=` tampoco lo destraba (`server.py:496-511`: la sesion se mira primero). Es un pie de Pedro en la Ally si alguna vez probo un tablero en su propio navegador; lente regresiones.
- **Un navegador desde loopback aprueba** (200): loopback es la raiz de confianza; consistente con el spec.
- **CSRF same-site en loopback** (otro puerto de localhost es same-site para `SameSite=lax` y `request.json()` no mira el content-type): afecta a TODOS los POST del server desde antes de la rama; no es de esta capa.
- **Timing de `==` sobre `id_pedido`** (`sesiones.py:_por_pedido`): teorico; con el freno contando cada fallo no es explotable. No reproducido, no es hallazgo.
- **`request.state.sesion` entre requests:** por construccion es por scope; no hay forma de que se filtre y no lo intente mas alla de leer el codigo.

## Sondas corridas (borradas al terminar)

- `sonda_eficacia.py` (145 tests: inv2 8/8 OK; inv3 62 OK + 1 esperado (`/setup` 303); inv4 -> H1 x2, H4 x2; inv5 xfail documentado; inv6 -> H5; inv7 OK x14; inv8 -> H4 x2, OK el resto; inv9 -> H2 (via TestClient), H3; inv10 OK; setup 8/8 + H7; otros -> H6). Dos fallos fueron errores de la sonda, no del codigo: el assert del balde del login tras un `/login` 401 (el propio login cuenta su fallo) y "combinando" de 120 code points (> 60, 422 correcto).
- `sonda_eficacia_b.py`: tiempo del corte del ws_chat que habla (40 s: nada) vs. vacio (0.01 s); freno con 6 hosts y reloj.
- `sonda_eficacia_c.py`: rafaga de 30 desde 6 direcciones; persistencia del mensaje de la revocada con chat activo.
- `sonda_eficacia_d.py`: driver ASGI crudo de `/ws/chat`, 8 combinaciones (texto x chat activo x send que suspende).
