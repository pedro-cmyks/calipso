# Smoke en vivo de la capa de sesion (8 de septiembre de 2026)

Rama `feat/capa-de-sesion`, HEAD `fa8fe89` (bifurcada de main en `c3a4d13`). Guion:
`.superpowers/sdd/2026-09-07-capa-de-sesion/task-9-context.md`, seccion "Guion del smoke".

## Entorno

Server DESECHABLE, jamas el real y jamas el puerto 8000. Nada de `CALIPSO_NO_TOTP`.

```
export CALIPSO_HOME=/tmp/claude-1000/-var-home-pedro/7ea3cff5-.../scratchpad/smoke-home   # vacio, nuevo
export CALIPSO_TOKEN=<32 chars aleatorios de secrets.token_urlsafe>
cd /var/home/pedro/calipso
.venv/bin/python -m uvicorn calipso.server:app --host 0.0.0.0 --port 8771 > $CALIPSO_HOME/server.log 2>&1 &
```

- LOOPBACK = `http://127.0.0.1:8771` (la Ally).
- REMOTO = `http://192.168.1.42:8771` (wlan0 de la misma maquina; el server la ve como host remoto).
- Huella del `~/.calipso` REAL antes de arrancar: `ls -laR --time-style=full-iso ~/.calipso | md5sum`
  -> `8644473ff26f088edab3d7b2f89e0471`. La verificacion esta en el paso 11.

---

## Paso 1 -- el server desechable arranca. PASA

```
$ for i in $(seq 1 40); do curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8771/login; ... done
login=200 tras 17 intentos

$ tail -3 $CALIPSO_HOME/server.log
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8771 (Press CTRL+C to quit)
INFO:     127.0.0.1:46520 - "GET /login HTTP/1.1" 200 OK
```

El `CALIPSO_HOME` nuevo arranca sin `sesiones.json` y sin `totp_secret`: los crea la capa cuando los
necesita.

## Paso 2 -- golpear desde el remoto y sondear. PASA

```
$ curl -s -i -X POST http://192.168.1.42:8771/api/aparatos/golpear \
    -H 'Content-Type: application/json' -d '{"aparato":"lector de prueba","tipo":"lector"}'
HTTP/1.1 200 OK
{"id_pedido":"RKcqsWUJJI1V4LxfY5Y2Rs75biuS7tndNLSMg4EjhfY"}

$ for i in $(seq 1 12); do curl -s -X POST http://192.168.1.42:8771/api/aparatos/estado \
    -H 'Content-Type: application/json' -d "{\"id_pedido\":\"$ID\"}"; done
sondeo 1..12: {"estado":"golpeando"} | HTTP 200
```

Doce sondeos seguidos con un `id_pedido` VALIDO: doce 200 y ningun 429. El sondeo legitimo no se
cobra (invariante 6). El id viaja en el body, nunca en el path.

## Paso 3 -- la cookie-token desde afuera no vale (invariante 2). PASA

```
$ curl -s -i -b "calipso_token=$CALIPSO_TOKEN" http://192.168.1.42:8771/api/tree
HTTP/1.1 401 Unauthorized
set-cookie: calipso_token=""; expires=Tue, 08 Sep 2026 14:29:46 GMT; Max-Age=0; Path=/; SameSite=lax
{"detail":"no autorizado"}

$ curl -s -i -X POST http://192.168.1.42:8771/api/aparatos/aprobar \
    -b "calipso_token=$CALIPSO_TOKEN" -d '{"id_pedido":"...","tipo":"tablero"}'
HTTP/1.1 401 Unauthorized
set-cookie: calipso_token=""; ... Max-Age=0; ...
{"detail":"no autorizado"}

$ curl -s -i -X POST "http://192.168.1.42:8771/api/aparatos/aprobar?token=$CALIPSO_TOKEN" -d '...'
HTTP/1.1 401 Unauthorized
```

El canario del invariante 2 canta: 401 y ademas la cookie-token vieja se EXPIRA sola (`Max-Age=0`).
La variante `?token=` en la query tambien rebota (401, sin cookie que expirar). Aprobar ni siquiera
llega al endpoint: muere en el guard.

## Paso 4 -- aprobar desde la Ally, con el tipo que elige Pedro. PASA

```
$ curl -s -i -X POST http://127.0.0.1:8771/api/aparatos/aprobar \
    -b "calipso_token=$CALIPSO_TOKEN" -d '{"id_pedido":"RKcq...","tipo":"tablero"}'
HTTP/1.1 200 OK
{"ok":true}

$ curl -s -b "calipso_token=$CALIPSO_TOKEN" http://127.0.0.1:8771/api/aparatos
{"aparatos": [{"hash_id": null,
               "id_pedido": "RKcqsWUJJI1V4LxfY5Y2Rs75biuS7tndNLSMg4EjhfY",
               "aparato": "lector de prueba", "tipo": "tablero",
               "estado": "viva", "efectivo": "viva"}]}
```

**Nota posterior:** salida anterior al fix `4588965`; hoy la fila aprobada sale con `id_pedido` null.

El golpe sugirio `lector` y Pedro dio `tablero`: manda Pedro. `hash_id` sigue en null hasta el canje
(el hash nace ahi). En disco, `sesiones.json` guarda el `id_pedido` en claro -- es lo que dice el
spec (seccion "el registro", `"id_pedido": token_urlsafe(32),  # el del golpe; se quema al canjear`);
lo que jamas toca el disco es el id de SESION, verificado en el paso 11.

## Paso 5 -- canje unico. PASA

```
$ curl -s -X POST http://192.168.1.42:8771/api/aparatos/estado -d '{"id_pedido":"RKcq..."}'
{"estado":"viva"}   HTTP 200

$ curl -s -i -X POST http://192.168.1.42:8771/api/aparatos/canjear -d '{"id_pedido":"RKcq..."}'
HTTP/1.1 200 OK
set-cookie: calipso_sesion=OMDKHpKe...; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax
{"ok":true,"tipo":"tablero"}

$ curl -s -i -X POST http://192.168.1.42:8771/api/aparatos/canjear -d '{"id_pedido":"RKcq..."}'
HTTP/1.1 404 Not Found
{"detail":"pedido desconocido"}
```

Cookie con `HttpOnly`, `SameSite=lax` y `Max-Age=2592000` (30 dias exactos). El segundo canje
encuentra el pedido quemado: 404 (invariante 8).

## Paso 6 -- el alcance del `tablero`, desde afuera y con la cookie de sesion. PASA

```
$ curl -b "calipso_sesion=$SES" http://192.168.1.42:8771<ruta>
/fabrica                  -> HTTP 200   <!doctype html> ... (la PWA entera)
/api/economia/tablero     -> HTTP 200   {"activa":false}
/api/file?path=README.md  -> HTTP 403   {"detail":"fuera del alcance del aparato"}
/api/aparatos             -> HTTP 403   {"detail":"fuera del alcance del aparato"}
POST /api/aparatos/aprobar-> HTTP 403   {"detail":"fuera del alcance del aparato"}
```

Websockets (cliente `websockets` 16 con header `Cookie`):

```
$ .venv/bin/python ws_probe.py ws://192.168.1.42:8771/ws/mapa "calipso_sesion=$SES" 14
CONECTADO
MENSAJE: {"evento":"latido","seq":0}

$ .venv/bin/python ws_probe.py ws://192.168.1.42:8771/ws/chat "calipso_sesion=$SES" 6
HANDSHAKE RECHAZADO: HTTP 403

$ .venv/bin/python ws_probe.py ws://192.168.1.42:8771/ws/mapa "calipso_token=$CALIPSO_TOKEN" 4
HANDSHAKE RECHAZADO: HTTP 403
```

`/ws/mapa` abre y habla (el latido sale cada 10 s: `LATIDO_CADA = 40` sondeos de `SONDEO_S = 0.25`,
server.py:6878-6879; con una espera de 6 s el socket se ve mudo y no es un error). `/ws/chat` no abre
para un tablero, y la cookie-token desde afuera tampoco abre nada (invariante 2 tambien en ws).

Nota sobre la FORMA del rechazo: el handler hace `await ws.close(code=1008)` ANTES del `accept`
(server.py:3032 y 6918), y eso Starlette lo traduce a una respuesta HTTP 403 del handshake. El
cliente NO ve un cierre 1008: ve un 403. El efecto de seguridad es el mismo; lo que cambia es lo que
tiene que esperar quien escriba el plugin. Queda como hallazgo Minor.

Limitacion honesta del paso: `/api/economia/tablero` contesta `{"activa":false}` porque el
`CALIPSO_HOME` desechable no tiene economia; lo verificado es que el alcance DEJA pasar (200), no la
forma del tablero cargado.

## Paso 7 -- la UI de Aparatos, en un navegador de verdad. PASA

```
$ curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8771/static/fabrica/aparatos.js
303          # sin credencial redirige a /login: el estatico tambien vive detras del guard
$ curl -s -b "calipso_token=$CALIPSO_TOKEN" ... /static/fabrica/aparatos.js
HTTP 200  bytes=6395
$ curl -s -b "calipso_token=$CALIPSO_TOKEN" http://127.0.0.1:8771/fabrica | grep -n aparatos
56:      <button data-vista="aparatos" type="button">Aparatos
57:        <span id="badge-aparatos" class="badge oculto"></span></button>
64:    <div id="aparatos" class="aparatos-panel oculto"></div>
```

El MCP de playwright configurado en la sesion no arranca (`Chromium distribution 'chrome' is not
found at /opt/google/chrome/chrome`), asi que el navegador se manejo con el playwright de python del
propio venv (1.60.0) sobre el chromium de `~/.cache/ms-playwright/chromium-1223`. Es un navegador
real; lo que sigue es lo que se vio en pantalla, con capturas en el scratchpad.

```
$ .venv/bin/python ui_aprobar.py
URL final: http://127.0.0.1:8771/fabrica      # el ?token= se consume y deja la cookie
titulo: Calipso - la fabrica
--- panel Aparatos (texto) ---
PIDIENDO ENTRAR
celular de la UI
sugiere: tablero
Ve toda la fabrica y firma la mesa y los permisos. Jamas archivos, comandos ni configuracion
que le doy | lector tablero navegador | aprobar rechazar
APARATOS
lector de prueba | tablero | VIVA | ultima vez 2026-09-08 09:30 | revocar
--- panel tras APROBAR (clic en el boton) ---
listo: el aparato quedo aprobado, falta que entre
PIDIENDO ENTRAR: Ningun aparato esta pidiendo entrar.
APARATOS
lector de prueba | tablero | VIVA | revocar
celular de la UI | tablero | VIVA | aprobado, esperando al aparato
errores de consola: []
```

Visto en la captura `ui-2-aparatos.png`: la pestana "Aparatos" con badge amarillo "1", la tarjeta del
golpe con el nombre, el "sugiere: tablero", el alcance en palabras, el selector de tipo y los botones
aprobar/rechazar; abajo la lista con "lector de prueba" en VIVA y su boton revocar. Cero errores de
consola. El boton Aprobar se clickeo de verdad y la lista se rehizo sola con la nota "aprobado,
esperando al aparato" (viva sin hash, sin boton de revocar: un boton que daria 404 no se dibuja).

## Paso 8 -- el CORTE: revocar mata el ws vivo. PASA

Primera pasada, con el boton Revocar de la UI mientras un ws remoto escuchaba:

```
ws remoto (cookie de sesion del tablero): [09:33:26] CONECTADO, escuchando
UI (loopback):                            [09:33:29] CLIC EN REVOCAR
ws remoto:                                [+2.50s] CERRADO code=1008
panel tras revocar: "listo: la sesion quedo cortada" / lector de prueba ... REVOCADA
```

Los relojes de los dos procesos son de segundo entero, asi que esa pasada no mide bien el retardo.
Segunda pasada instrumentada en un solo proceso (canje remoto, ws remoto, revocar por curl desde
loopback, todo con el mismo `time.monotonic`):

```
$ .venv/bin/python corte_preciso.py
canje remoto: 200 {"ok":true,"tipo":"tablero"} [calipso_sesion=EIxzVOe...; HttpOnly; Max-Age=2592000...]
ws remoto conectado
hash_id del aparato: 94f1075b55fd2841 ...
[+0.001s] REVOCAR loopback -> 200 {"ok":true}
[+0.249s] ws CERRADO code=1008
tras el corte, GET remoto /api/economia/tablero -> 401
```

249 ms, muy por debajo de los 2 s del guion. Y despues del corte la misma cookie ya no sirve para
nada:

```
$ curl -s -i -b "calipso_sesion=$SES" http://192.168.1.42:8771/api/economia/tablero
HTTP/1.1 401 Unauthorized
$ .venv/bin/python ws_probe.py ws://192.168.1.42:8771/ws/mapa "calipso_sesion=$SES" 3
HANDSHAKE RECHAZADO: HTTP 403
```

## Paso 9 -- login remoto con TOTP: sesion `navegador`, jamas el token. PASA

```
$ CODE=$(.venv/bin/python -c "import time,calipso.server as s; print(s._totp_code(s._get_totp_secret(), int(time.time()//30)))")
codigo TOTP vigente: 124208
$ ls -la $CALIPSO_HOME/totp_secret
-rw------- 32 ...        # el secreto nace 0600 en el HOME DESECHABLE

$ curl -s -i -X POST http://192.168.1.42:8771/login -d "code=$CODE"
HTTP/1.1 303 See Other
location: /
set-cookie: calipso_sesion=V-lidsuvsi...; HttpOnly; Max-Age=2592000; Path=/; SameSite=lax
# ocurrencias de "calipso_token" en la respuesta: 0
```

Con esa sesion `navegador`, desde el remoto:

```
GET  /api/aparatos                  -> HTTP 200, lista completa (los tres aparatos y sus estados)
POST /api/aparatos/aprobar          -> HTTP 403 {"detail":"aprobar es solo desde la Ally"}
POST /api/aparatos/<hash>/revocar   -> HTTP 200 {"ok":true}      # D3: revocar desde otro dispositivo
   y la victima queda muerta: GET remoto con su cookie -> HTTP 401
```

El navegador remoto ve y revoca, pero NO aprueba: ninguna sesion consagra a otra (invariante 4).

Freno del login, seis codigos malos seguidos desde el remoto:

```
intento 1..5 (code=00000N) -> HTTP 401
intento 6                  -> HTTP 429
```

Y con /login frenado, el alta sigue viva (baldes separados, invariante 6):

```
$ curl -s -i -X POST http://192.168.1.42:8771/api/aparatos/golpear -d '{"aparato":"prueba de separacion",...}'
HTTP/1.1 200 OK
```

## Paso 10 -- freno propio del alta. PASA

```
$ for i in $(seq 1 25); do curl -D - -o /dev/null -X POST .../api/aparatos/golpear -d "{\"aparato\":\"martillo $i\",...}"; done
golpe 1:  HTTP/1.1 200 OK
golpe 2:  HTTP/1.1 429 Too Many Requests | retry-after: 16
golpe 3..25: idem, retry-after: 16

$ curl -s -o /dev/null -w '%{http_code}' -X POST http://192.168.1.42:8771/login -d "code=999999"
401          # el login NO se contagia del freno del alta

$ curl -s -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8771/api/aparatos/golpear -d '...'
200          # y la clave es por host: la Ally no paga el martilleo del remoto
```

El 429 trae `Retry-After` y no cuenta como fallo (martillar el 429 no escala el castigo). La cuenta
del remoto ya venia cargada de los pasos anteriores, por eso el freno cae en el segundo golpe y no en
el sexto.

Contra-observacion del mismo paso (ver hallazgo 1): con el castigo activo, un sondeo con un
`id_pedido` VALIDO tambien se lleva 429.

```
$ for i in $(seq 1 10); do curl -X POST .../api/aparatos/estado -d "{\"id_pedido\":\"<valido>\"}"; done
sondeo 1..10 -> {"detail":"demasiados intentos"} HTTP 429
```

## Paso 11 -- apagar y auditar. PASA

```
$ kill $PID
$ ps -p $PID -o pid=            -> (no existe)
$ ss -ltnp | grep 8771          -> nadie escucha en 8771
$ pgrep -af "uvicorn calipso.server"  -> ningun uvicorn de calipso vivo

$ stat -c '%a %U:%G %n' $CALIPSO_HOME/sesiones.json
600 pedro:pedro .../smoke-home/sesiones.json

# las cuatro cookies de sesion que entrego el server, buscadas en el archivo:
sesion_tablero  (OMDKHpKe4e...): no aparece
sesion_celular  (EIxzVOe...)   : no aparece
sesion_victima  (iEswqAPj9s...): no aparece
sesion_navegador(V-lidsuvsi...): no aparece

# y el hash guardado ES el sha256 de la cookie:
sha256 esperado: 4bc974726037a4d27fa86a72e44555ec2ce5ca55f3e9fbb905a17bc2770889c4
hash guardado  : 4bc974726037a4d27fa86a72e44555ec2ce5ca55f3e9fbb905a17bc2770889c4

$ python3 -c "claves por registro"
['aparato', 'creada', 'estado', 'hash_id', 'id_pedido', 'tipo', 'ultima_vez']   # 9 registros
```

Estado final del almacen (por loopback, antes de apagar):

```
lector de prueba         tipo=tablero    efectivo=revocada   hash=si
celular de la UI         tipo=tablero    efectivo=revocada   hash=si
tablero victima          tipo=tablero    efectivo=revocada   hash=si
navegador 192.168.1.42   tipo=navegador  efectivo=viva       hash=si
prueba de separacion     tipo=lector     efectivo=golpeando  hash=no
sonda de espera          tipo=lector     efectivo=golpeando  hash=no
sonda gratis             tipo=lector     efectivo=golpeando  hash=no
martillo 1               tipo=lector     efectivo=golpeando  hash=no
desde la ally            tipo=lector     efectivo=golpeando  hash=no
```

### El `~/.calipso` REAL de Pedro

La huella recursiva cambio (`8644473f...` antes, `fb3c8974...` despues) y NO por Calipso: `ls -laR`
imprime tambien la linea de `..`, que es `/home/pedro`, y ese directorio cambio de mtime 09:27 a
09:37 por algo ajeno a esta sesion. Las tres pruebas directas dicen que el home real quedo intacto:

```
$ find ~/.calipso -newermt '2026-09-08 00:00'
(vacio: ningun archivo del home real se toco hoy)

$ stat -c '%y %a %n' ~/.calipso ~/.calipso/token ~/.calipso/totp_secret
2026-09-07 16:49:54 755 /home/pedro/.calipso        # el mtime del directorio es de AYER:
2026-09-07 16:49:54 600 /home/pedro/.calipso/token  # no nacio ni murio ninguna entrada
2026-06-19 13:57:55 600 /home/pedro/.calipso/totp_secret

$ ls -la ~/.calipso/sesiones.json
No such file or directory                            # la capa escribio solo en el temporal

$ ls -laR --time-style=full-iso ~/.calipso | grep -v ' \.\.$' | md5sum
5d45458b84ee05a442b64a41ef9e5165                     # estable en corridas repetidas
```

Leccion de instrumento: `ls -laR ... | md5sum` sobre un directorio incluye la linea del PADRE, asi
que es una huella ruidosa. La proxima vez, `grep -v ' \.\.$'` o `find -printf`.

---

## Que quedo verificado

- Invariante 1 y 2: el token no sale de la Ally. Cookie-token y `?token=` desde el remoto -> 401, y
  la cookie vieja se expira sola; en ws, handshake rechazado. El login remoto con TOTP entrega
  SESION, nunca token (cero ocurrencias de `calipso_token` en la respuesta).
- Invariante 3: alcance fail-closed en http (403 "fuera del alcance del aparato" para archivos,
  aparatos y aprobar) y en ws (`/ws/chat` cerrado para un tablero, `/ws/mapa` abierto).
- Invariante 4: aprobar solo desde loopback -- 401 al remoto con cookie-token, 403 a la sesion
  `navegador`; revocar si desde la sesion `navegador` (200) y desde la Ally.
- Invariante 6: baldes separados. Seis TOTP malos frenan `/login` y NO frenan el alta; 25 golpes
  frenan el alta con `Retry-After` y NO frenan `/login`; la clave es por host (la Ally no paga).
- Invariante 7: `sesiones.json` 0600, con `sha256(id)` verificado contra la cookie, y ninguno de los
  cuatro ids de sesion entregados aparece en claro en el disco.
- Invariante 8: canje unico (el segundo, 404); cookie `HttpOnly; SameSite=lax; Max-Age=2592000`.
- Invariante 9: revocada no revive -- 401 en http y 403 en el handshake nuevo del ws.
- El corte en vivo: 249 ms desde el `revocar` hasta el cierre 1008 del ws remoto que ya estaba
  adentro.
- La UI de Aparatos existe y funciona en un navegador real: pestana, badge, tarjeta con el alcance en
  palabras, selector de tipo, y los botones Aprobar y Revocar hacen lo que dicen.
- El `~/.calipso` real no se toco.

## Que NO quedo verificado

- La caducidad por reloj (dormida 30 dias / vieja 180) -- no se puede correr en un smoke de minutos;
  vive en los tests de `sesiones.py` con reloj inyectable.
- El tope de 5 golpes pendientes (`sesiones.Lleno`) -- el freno del alta llega antes que el tope y
  tapa esa respuesta desde un solo host.
- El alcance `lector` de verdad: `/api/lectura/*` todavia no existe (rebanada 4 del abismo). Solo se
  verifico que el tipo se acepta y se guarda.
- `/api/economia/tablero` con economia cargada: el HOME desechable devuelve `{"activa":false}`. Lo
  verificado es que el guard deja pasar, no el contenido.
- `/setup` en primer arranque, Tauri, la PWA local y los CLIs: fuera del guion de este smoke (son la
  lente de la ronda de regresiones).
- El MCP de playwright del entorno: no arranca por falta de Chrome en `/opt/google/chrome/chrome`. El
  navegador se manejo con el playwright del venv y el chromium de `~/.cache/ms-playwright`.

## Hallazgos

### 1. (Minor) El freno del alta bloquea tambien al sondeo legitimo

`server.py:484-491`: el guard decide el freno con `_aparatos_espera(host)` ANTES de que el endpoint
pueda distinguir un `id_pedido` valido de uno desconocido. El spec dice "NO cuenta: sondear un
`id_pedido` valido (es el flujo feliz esperando a Pedro)", y la implementacion cumple la letra -- no
lo CUENTA (`_aparatos_fallo` solo se llama con id desconocido, server.py:852 y 865) -- pero mientras
hay castigo activo ese sondeo igual se lleva 429. Reproducido: con el balde cargado, diez sondeos
seguidos de un `id_pedido` valido devolvieron `{"detail":"demasiados intentos"} HTTP 429`.

Consecuencia de segundo orden, no reproducida en vivo pero visible en los numeros: el castigo escala
`2 * 2^(fallos-5)` hasta `_LOGIN_BACKOFF_TOPE = 900` s (server.py:287-288), y `GOLPE_TTL_MIN = 10`
minutos son 600 s. Un host que acumule ~13 fallos entra en un castigo mas largo que la vida del
golpe: cuando puede volver a sondear, el pedido ya caduco, y el golpe nuevo suma otro fallo. Se
sostiene solo hasta que el host pase 900 s callado (el decaimiento baja UNO por ventana). Le pasa a
un aparato que martilla, no al plugin bien portado que golpea una vez y sondea; por eso Minor y no
Important. Arreglo posible: cuando la ruta es `/api/aparatos/estado` y el `id_pedido` resuelve,
dejarlo pasar aunque el balde este cargado (mirar el id antes del freno solo para ese caso), o topear
el backoff del alta por debajo del TTL del golpe.

### 2. (Minor) El ws fuera de alcance rechaza con 403 en el handshake, no con cierre 1008

`server.py:3032` (`ws_chat`) y `server.py:6918` (`ws_mapa`) hacen `await ws.close(code=1008)` antes
del `accept`. Starlette traduce un close-antes-de-accept a una respuesta HTTP 403 del handshake, asi
que el cliente NUNCA ve el codigo 1008: ve `HANDSHAKE RECHAZADO: HTTP 403`. Verificado con
`websockets` 16 en los tres casos de rechazo (tablero en `/ws/chat`, cookie-token remota en
`/ws/mapa`, sesion revocada en `/ws/mapa`). El cierre 1008 SI se ve, y es el unico caso donde se ve,
cuando el corte llega con el socket ya aceptado (paso 8). Seguridad: identica. Lo que hay que
corregir es la expectativa escrita: el guion de la task 9 y lo que se documente para el plugin de
KOReader y la APK deben decir "403 en el handshake" para el rechazo y "cierre 1008" para el corte en
vivo, o el cliente va a esperar un evento que no llega.
