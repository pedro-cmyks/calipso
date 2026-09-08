# La capa de sesion -- identidad de aparato para Calipso

**Fecha:** 2026-09-07
**Estado:** brainstorming cerrado con Pedro; corregido tras revision adversaria de cuatro lentes (41 hallazgos); listo para su revision
**Origen:** el resto del punto 3 de la revision de seguridad (`docs/superpowers/2026-09-07-revision-seguridad.md`, adenda 3a) + la decision D3 del 2026-08-31 ("el dispositivo se autentica una vez y cada tanto se le vuelve a pedir; Pedro puede revocar desde otro dispositivo; la Ally es la raiz de confianza"). Dossier: [[project_calipso_abismo]], [[project_calipso_lector]].
**Alcance honesto:** es NECESARIO pero NO SUFICIENTE para abrir CALIPSO_HOST. Despues de esta capa siguen bloqueando: la escalada PUT `/api/file` + `commands/run` (critica para una sesion `navegador` remota), las raices explicitas del catastro, el shell Tauri, y el bind operacional solo-Tailscale.

## 1. Por que existe

La credencial es UNA y es total: la cookie vale el TOKEN literal (`_session_response`, `auth_guard`) y quien la tiene puede todo. No hay identidad de aparato. El 3a corto las fugas y los portones de red; esta capa corta la enfermedad: sesiones por aparato, con alcance, revocables.

## 2. Que decidio Pedro (brainstorming 2026-09-07)

1. **El alta es "golpear la puerta": la Ally aprueba.** El aparato toca el server y queda estacionado; en `/fabrica` aparece "el lector pide entrar" y Pedro aprueba **desde la Ally (solo loopback aprueba)**. El gesto vive donde vive la raiz de confianza.
2. **Alcance por aparato, y el TIPO lo fija Pedro al aprobar** (el golpe solo lo sugiere): `lector` = sus endpoints de lectura; `tablero` = ver toda `/fabrica` y FIRMAR la mesa y los permisos, jamas archivos/comandos/config (decision de hoy para la pieza 2 del BRIEF del lector: "ver y firmar la mesa"); `navegador` = la PWA completa. La Ally (loopback) sigue siendo todo.
3. **La sesion se renueva usando y caduca si duerme** (30 dias sin aparecer). Y un tope absoluto laxo de 180 dias desde la creacion honra el "cada tanto se le vuelve a pedir" de D3: re-alta dos veces al anio, friccion casi nula. (El tope es ruling del diseno, revisable por Pedro.)

## 3. Arquitectura

### El almacen: `calipso/sesiones.py`

`~/.calipso/sesiones.json`, escrito por el escritor atomico de `calipso/economia/candado.py`. **El archivo guarda HASHES, no credenciales:** de cada sesion se persiste `sha256(id)`; el id en claro solo existe en la cookie del aparato. Con eso `sesiones.json` deja de ser una credencial robable -- y de yapa, defensa en profundidad: nace 0600, entra a `SKIP_FILES_RAIZ` del backup y `es_credencial_del_servidor` se extiende a cubrirlo (las tres, lecciones de C6).

```
{ "hash_id": sha256_hex,            # jamas el id en claro
  "id_pedido": token_urlsafe(32),   # el del golpe; se quema al canjear
  "aparato": str (<= 60 chars, sin control chars: es input NO autenticado
             que llega a la UI de /fabrica),
  "tipo": "lector" | "tablero" | "navegador",
  "creada": iso, "ultima_vez": iso,
  "estado": "golpeando" | "viva" | "revocada" | "rechazada" }
```

API del modulo (todas con reloj inyectable): `golpear(aparato, tipo_sugerido)` (valida tipo en ALCANCES y limites de `aparato`: si no, 422 y NO estaciona; tope de 5 golpes pendientes simultaneos; TTL de `golpeando` = 10 minutos -- el aparato esta ahi sondeando en vivo), `aprobar(id_pedido, tipo)` (el tipo lo pone Pedro; genera el id de sesion, guarda su hash, deja la cookie lista para UN canje), `rechazar`, `revocar`, `canjear(id_pedido)` (entrega el id de sesion UNA vez y quema `id_pedido`; un segundo canje = 404), `resolver(id_en_claro)`, `listar()` (estado EFECTIVO: una dormida >30 dias o pasada de 180 se reporta caduca aunque el archivo diga viva -- /fabrica no miente).

**Lectura sin candado, escritura poco frecuente:** `resolver()` lee de una cache en memoria recargada por mtime (os.replace garantiza viejo-o-nuevo, documentado en `candado.py`); la renovacion de `ultima_vez` se escribe con histeresis (solo si tiene mas de 1 hora) y via `asyncio.to_thread` -- el flock JAMAS se toma en el event loop (la trampa que ya obligo a `to_thread` en `economia_brief`).

**Archivo ilegible:** se renombra a `sesiones.json.corrupto-<ts>` ANTES de la primera escritura nueva -- avisado Y preservado, nunca pisado con vacio (el molde es `_leer_solicitudes` de permisos, NO `config()`, que pisa en silencio -- corregido de la primera version de este spec).

### Los alcances

Reglas por tipo: lista de `(prefijo, metodos)`; fail-closed (nada matchea = 403 "fuera del alcance del aparato"). El alcance aplica a TODAS las rutas, no solo `/api`.

```
"navegador": todo ("*")
"lector":    ("/api/lectura/", todos)          # pregunta, respuesta, presencia
"tablero":   ("/fabrica", GET) ("/static", GET) ("/ws/mapa", GET)
             ("/api/mapa/", GET) ("/api/economia/", GET) ("/api/permisos", GET)
             ("/api/inbox", GET)
             ("/api/economia/bus/", POST)      # financiar/descartar: la mesa
             ("/api/permisos/responder", POST) # aceptar requests
             y NADA de /api/file, /api/commands, /api/config, /api/project
```

La lista exacta del `tablero` se refina en el plan contra las rutas reales de `/fabrica`; el criterio es fijo: **ver todo, firmar mesa y permisos, jamas tocar la maquina.** La sesion resuelta viaja en `request.state.sesion`: el consumidor de anillos del abismo (rebanada 4) ES el tipo de sesion -- transporte y profundidad se componen, la costura queda declarada.

### El guard

Orden en `auth_guard` (anclas por simbolo; las lineas se corren):
1. `/login` exenta. `/setup` exenta SOLO si: loopback Y no existe `totp_secret` Y el request trae `?token=` valido -- loopback no es Pedro (flatpaks, otros uid); el token si, porque solo el uid de Pedro lee `~/.calipso/token`. Sin esa prueba, la ventana de primer arranque regalaba el secreto TOTP al primer proceso local que pasara.
2. `POST /api/aparatos/golpear`, `POST /api/aparatos/estado` y `POST /api/aparatos/canjear` exentas de credencial, con freno propio: **claves `aparatos:{host}` y balde `aparatos:*`, separados de los del login** (compartir el balde del login regalaria a un martillador sin credencial la palanca del DoS del TOTP). Cuenta como fallo: un golpe nuevo, o un estado/canje con `id_pedido` desconocido. NO cuenta: sondear un `id_pedido` valido (es el flujo feliz esperando a Pedro). El id viaja en el BODY (nunca en el path: el access log no lo ve).
3. Cookie de sesion (`calipso_sesion`, httponly, samesite=lax, max_age 30 dias) que resuelve viva: pasa con su alcance.
4. Cookie o `?token=` que valen el TOKEN: **solo loopback** (la Ally y Tauri intactos). Un 401 remoto con cookie-token ademas la EXPIRA (Set-Cookie vencida): limpieza de las cookies-token viejas de un anio.
5. `/login` + TOTP: local planta el token como hoy; **remoto crea una sesion `navegador` YA VIVA** -- la excepcion explicita del invariante 4: el TOTP es Pedro en persona, no un aparato aprobandose solo. (Y como aprobar es solo-loopback, ninguna sesion aprueba jamas a otra.)
6. Websockets (no pasan por el middleware; su chequeo vive en cada handshake): **token valido DESDE LOOPBACK o sesion viva cuyo alcance cubra ese ws.**

### Alta, revocacion y corte en `/fabrica`

- El aparato: `golpear` -> sondea `estado` -> al ver `viva`, `canjear` UNA vez -> cookie.
- `/fabrica`: la superficie de solicitudes existente (el molde de `/api/permisos` + inbox) muestra los que golpean con el tipo SUGERIDO y su alcance en grande; **aprobar exige loopback** (la Ally); rechazar idem. `GET /api/aparatos` lista (estado efectivo); `POST /api/aparatos/{hash}/revocar` desde loopback o sesion `navegador` (D3: "revocar desde otro dispositivo"; el `tablero` y el `lector` NO revocan). El token no se revoca por esta capa: su unica revocacion es rotarlo en la Ally.
- **Corte de WS vivos:** registro EN MEMORIA sesion->generacion que `revocar()` incrementa; cada ws guarda su sesion del handshake y re-chequea la generacion al recibir un mensaje, antes de cada emision al cliente, y en el latido periodico -- un ws ocioso no sobrevive a la revocacion mas alla del proximo latido. `ws_mapa` ya itera por tick; `ws_chat` agrega el chequeo en sus puntos de emision.

### Migracion y despliegue

Al aterrizar la capa: (1) las cookies-token remotas viejas mueren solas (paso 4 las expira); (2) **rotar el TOKEN es parte del despliegue** (las viejas quedaron un anio en navegadores); (3) la PWA remota existente hace `/login`+TOTP una vez y queda como sesion `navegador`.

**Despliegue de la fase 1** (el orden importa: el paso 2 corta a los remotos, el 3 los vuelve a dar de alta):

1. Reiniciar el server con el codigo nuevo.
2. **Rotar el TOKEN:** borrar `~/.calipso/token` y reiniciar -- `_load_token` (server.py) genera y guarda uno nuevo cuando el archivo no existe. Es obligatorio y no opcional: el paso 4 del guard expira la cookie-token vieja recien cuando ese navegador VUELVE, y las que se repartieron duraron un anio. (Si `CALIPSO_TOKEN` esta exportado en el entorno del server, gana sobre el archivo: rotar ahi tambien, o borrarla.)
3. La PWA remota hace `/login` + TOTP una vez y queda como sesion `navegador` (paso 5 del guard). No hay que golpear ni aprobar nada para eso.
4. Tauri y la Ally no cambian: son loopback y siguen con el token (rotado) como hasta hoy.

## 4. Invariantes

1. **El TOKEN jamas viaja a un aparato remoto**; una sesion no contiene ni deriva el token.
2. **Remoto = solo sesiones.** Token (cookie o query) vale unicamente desde loopback -- tambien en los websockets.
3. **Alcance fail-closed**, en http y en ws.
4. **Aprobar es solo-loopback** (la Ally). Unica excepcion de auto-consagracion: `/login`+TOTP remoto, porque el TOTP es Pedro en persona. Revocar: loopback o sesion `navegador`.
5. **Dormida 30 dias o mas vieja que 180 = muerta**; la mata la resolucion (no un cron) y `listar()` reporta el estado efectivo sin esperar a eso.
6. **Golpear/estado/canjear llevan freno propio** (claves `aparatos:*`), separado del login; el sondeo legitimo es gratis.
7. **`sesiones.json` guarda hashes**, nace 0600, no se respalda, y esta bajo el NUNCA del motor de permisos. Ilegible = renombrado y avisado, jamas pisado.
8. **La cookie de sesion se entrega UNA vez** (canje que quema el id_pedido); `golpeando` caduca en minutos y tiene tope de pendientes.
9. **Sin marcha atras:** revocada/rechazada no reviven; el aparato vuelve a golpear.
10. **El flock jamas corre en el event loop.**

## 5. Lo que NO hace (fuera de este spec)

- La escalada PUT `/api/file` + `commands/run` (su propio fix con el motor de permisos; hasta entonces, una sesion `navegador` remota carga ese riesgo -- por eso el `tablero` existe).
- Raices explicitas del catastro; el shell Tauri (Rust); TLS (el transporte remoto es Tailscale).
- El "accept-once" de `?token=` de las adendas MUERE aca con nombre: ya no hace falta -- el token es solo-loopback y un remoto jamas lo presenta.
- Endpoints `/api/lectura/*` (rebanada 4 del abismo): aca solo queda definido su alcance.
- Scopes mas finos que el tipo; tipos nuevos se agregan a la tabla cuando exista el aparato.
- Riesgo aceptado y nombrado: una cookie de sesion robada EN USO vive hasta el tope de 180 dias o la revocacion manual -- el precio del "cero friccion diaria" que Pedro eligio.

## 6. Como se verifica que funciona

- `sesiones.py` en aislado con reloj inyectable: ciclo completo, TTL de golpes (10 min), tope de pendientes, canje unico (el segundo = 404), caducidad 30/180, estado efectivo en listar, hash (el archivo jamas contiene el id de la cookie), corrupcion renombrada, 0600.
- Endpoint: golpear estacionado con tipo validado (basura = 422); aprobar desde remoto = 403 y desde loopback = viva CON EL TIPO DE PEDRO (aprobar ignora el tipo del golpe: canario); alcance `lector` y `tablero` contra rutas vedadas = 403 (canarios: file/commands/config para tablero); renovacion con histeresis; login remoto crea sesion y NO planta token; cookie-token remota = 401 QUE EXPIRA la cookie (canario); **ws_chat con cookie-token desde host no-loopback = close 1008 (canario nuevo del invariante 2)**; ws de sesion revocada se corta aunque este ocioso (latido).
- Freno propio: martillar golpear frena SIN tocar el balde del login (canario de separacion); sondear id valido N veces = gratis.
- Suite completa + node; smoke en vivo con server desechable (golpear con curl, aprobar, usar, revocar, ver el corte); ronda adversaria de rama antes del merge.

## 7. El corte en fases (para el plan)

- **Fase 1 (atomica):** almacen + guard + login + los ws aceptan sesion. Inseparables: si el login remoto planta sesion pero ws_chat sigue exigiendo cookie==TOKEN, la PWA remota pierde el chat.
- **Fase 2:** la UI de `/fabrica` (tarjetas de golpes, lista de aparatos, revocar).
- **Fase 3:** el corte activo de ws revocados (generaciones + latido).
- Ripple documental al aterrizar: el BRIEF del lector (su plugin pasa de "login+TOTP" a "golpear -> sesion lector"; su APK es tipo `tablero`).

## 8. Vocabulario

"Sesion" y "aparato". `id_pedido` (del golpe) != id de sesion (el de la cookie); el aparato no conoce el segundo hasta canjear. La cookie nueva es `calipso_sesion`; `calipso_token` sigue siendo la del token, solo-loopback. No confundir esta capa con el motor de `permisos` (gobierna ACCIONES de agentes; esta gobierna QUIEN entra) ni el tipo `lector` con el consumidor `lector` de los anillos del abismo (se componen via `request.state.sesion`).
