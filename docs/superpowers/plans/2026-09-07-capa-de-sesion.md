# La capa de sesion: plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identidad de aparato para Calipso: sesiones con alcance por tipo (lector/tablero/navegador), alta por "golpear la puerta" con aprobacion desde la Ally, renovacion por uso, revocacion desde /fabrica. Al final, el token queda relegado a loopback y un remoto solo entra por sesion.

**Architecture:** Modulo puro `calipso/sesiones.py` (almacen con HASHES + cache por mtime + reloj inyectable) probado en aislado; el cableado toca `auth_guard`, `/login`, los dos websockets y tres endpoints nuevos exentos-con-freno; la UI de /fabrica reusa el molde del inbox. Tres fases del spec seccion 7: la 1 es atomica (almacen+guard+login+ws), la 2 es UI, la 3 el corte activo de ws.

**Tech Stack:** Python/FastAPI + el escritor atomico de `candado.py`; tests pytest en la raiz + httpx.ASGITransport para simular IPs remotas (el molde de `test_seguridad_portones.py`).

**Spec:** `docs/superpowers/specs/2026-09-07-capa-de-sesion-design.md` — el spec es la autoridad; este plan lo argumenta. Leerlo ENTERO antes de la primera tarea.

## Global Constraints

- SIN EMOJIS en codigo, tests, docs y salidas.
- NUNCA importar modulos de calipso fuera de pytest sin `CALIPSO_HOME` a un temporal ANTES del import; tests con `tmp_path` + `monkeypatch.setattr` sobre constantes congeladas.
- Suite completa antes de CADA commit: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py` con 0 failed **verificando el exit code, no el tail** (ya se colo un commit con 1 failed por piparlo a tail). Si se toca `calipso/web/`, tambien `node --test` desde `calipso/web/fabrica/` (Node en `~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node`, cwd, no argumento).
- `git add` con rutas explicitas.
- Constantes del spec, verbatim: `SESION_SUENO_DIAS = 30`, `SESION_VIDA_MAX_DIAS = 180`, `GOLPE_TTL_MIN = 10`, `GOLPES_PENDIENTES_MAX = 5`, histeresis de renovacion 1 hora, `aparato` <= 60 chars sin caracteres de control, cookie `calipso_sesion` httponly samesite=lax max_age 30 dias, freno con claves `aparatos:{host}` / `aparatos:*` (JAMAS las del login), id_pedido e id de sesion = `secrets.token_urlsafe(32)`.
- El almacen guarda `sha256(id)` hex — el id en claro JAMAS toca el disco. `sesiones.json` nace 0600 (`os.open` con modo, como `_escribir_secreto` en server.py), entra a `SKIP_FILES_RAIZ` de `backup.py` y a `es_credencial_del_servidor` de `permisos/acciones.py`.
- El flock jamas en el event loop: lecturas por cache de mtime; escrituras via `asyncio.to_thread` desde el middleware.
- Reloj inyectable en TODO `sesiones.py` (el molde de `_login_reloj`).
- Anclas por SIMBOLO (auth_guard, login_submit, ws_chat, ws_mapa): las lineas de server.py se corren entre merges.
- Ritual de cierre de rama: ronda adversaria (eficacia/regresiones/completitud) antes del merge — es lo que cazo los bugs reales en los puntos 1, 2 y 3a. Un asiento que devuelva placeholder se re-corre: no dar por verificado lo vacio.

---

## FASE 1 — atomica: almacen + guard + login + ws

### Task 1: El almacen (`calipso/sesiones.py`) — estado y ciclo de vida

**Files:**
- Create: `calipso/sesiones.py`
- Test: `test_sesiones.py`

**Interfaces (Produces):**
- `golpear(aparato: str, tipo_sugerido: str) -> dict` (valida `tipo_sugerido in ALCANCES` y limites de `aparato`; levanta `ValueError` si no — el endpoint lo vuelve 422; aplica TTL de pendientes y tope 5; devuelve `{"id_pedido": ...}`)
- `aprobar(id_pedido: str, tipo: str) -> None` (el tipo lo fija Pedro; genera id de sesion, guarda `hash_id`, deja `cookie_pendiente` para UN canje) / `rechazar(id_pedido)` / `revocar(hash_id)`
- `canjear(id_pedido: str) -> str | None` (el id de sesion EN CLARO, una sola vez; quema `id_pedido` y borra `cookie_pendiente`; segunda vez o desconocido = None)
- `estado(id_pedido: str) -> str | None` ("golpeando"/"viva"/"rechazada"/None)
- `resolver(id_en_claro: str) -> dict | None` (hashea, busca, aplica sueno 30d y vida max 180d — vencida la marca revocada y devuelve None; renueva `ultima_vez` con histeresis 1h)
- `listar() -> list[dict]` (estado EFECTIVO derivado del reloj, sin escribir)
- `ALCANCES: dict[str, tuple]` (la tabla del spec; Task 2 la consume)
- Modulo: `_reloj` inyectable, cache por mtime, escritor de `candado.escribir_json_atomico` + chmod 0600, ilegible -> renombrar `.corrupto-<ts>` antes de escribir.

- [ ] Escribir `test_sesiones.py` con los casos del spec seccion 6 (ciclo completo; canje unico -> None la segunda; TTL 10 min de golpeando con reloj; tope 5 pendientes; caducidad 30/180; histeresis de renovacion; listar efectivo; el archivo NUNCA contiene el id en claro — grep del json por el id devuelto por canjear; modo 0600; corrupto renombrado). Correr en rojo.
- [ ] Implementar `sesiones.py` hasta verde. La estructura del registro y las funciones son las del spec seccion 3 al pie de la letra.
- [ ] Suite completa (exit code) y commit: `feat(sesiones): el almacen -- hashes, canje unico, ciclo de vida con reloj inyectable`.

### Task 2: Los alcances y su aplicacion

**Files:**
- Modify: `calipso/sesiones.py` (agregar `permite(tipo, path, metodo) -> bool`)
- Test: `test_sesiones.py` (ampliar)

`permite` evalua la tabla `ALCANCES` fail-closed; `"*"` es el unico comodin. La lista del `tablero` se REFINA aca contra las rutas reales de la UI de /fabrica (leer `calipso/web/fabrica/app.js` y los `@app.get/post` que consume): criterio fijo del spec — ver todo, firmar mesa (`/api/economia/bus/*` POST) y permisos (`/api/permisos/responder` POST), jamas `/api/file`, `/api/commands`, `/api/config`, `/api/project`, `/api/updates`, `/api/plugins`, `/api/backup`. Tests: canarios por tipo (lector contra ruta de la PWA = False; tablero contra file/commands/config/project = False; tablero mesa POST = True; navegador todo = True).

- [ ] Test rojo, implementar, verde, suite, commit: `feat(sesiones): alcances por tipo, fail-closed`.

### Task 3: Endpoints del alta con freno propio

**Files:**
- Modify: `calipso/server.py` (tres endpoints + exenciones en `auth_guard`)
- Test: `test_sesiones_server.py`

`POST /api/aparatos/golpear {aparato, tipo}` / `POST /api/aparatos/estado {id_pedido}` / `POST /api/aparatos/canjear {id_pedido}` — exentos de credencial en `auth_guard` (por path exacto y metodo POST), con el freno reutilizado con claves PROPIAS: `_login_espera/_login_fallo` con `f"aparatos:{host}"` y `"aparatos:*"`. Cuenta fallo: golpe nuevo, estado/canje con id desconocido. Gratis: estado/canje con id valido. El canje setea la cookie `calipso_sesion` en la respuesta. Aprobacion todavia sin UI: `POST /api/aparatos/{id_pedido}/aprobar {tipo}` y `/rechazar` DETRAS del guard y ademas exigiendo loopback (invariante 4); `GET /api/aparatos` (listar) detras del guard. Tests con ASGITransport: golpear remoto estacIona; aprobar desde remoto = 403 aunque tenga sesion; sondeo N veces gratis; martillar golpear frena `aparatos:*` SIN tocar el balde del login (canario de separacion); canje entrega cookie una vez.

- [ ] Test rojo, implementar, verde, suite, commit: `feat(sesiones): golpear/estado/canjear con freno propio, aprobar solo loopback`.

### Task 4: El guard resuelve sesiones y el token queda solo-loopback

**Files:**
- Modify: `calipso/server.py` (`auth_guard`, `_session_response` NO cambia; rama nueva de sesion; expiracion de cookie-token remota; exencion de `/setup` endurecida)
- Test: `test_sesiones_server.py` (ampliar)

Orden final del guard = spec seccion 3 "El guard" puntos 1-5, tal cual. La rama de sesion: `ses = await asyncio.to_thread(sesiones.resolver, request.cookies.get("calipso_sesion"))` (resolver puede escribir con histeresis: por eso to_thread); si viva y `sesiones.permite(ses["tipo"], path, request.method)` pasa con `request.state.sesion = ses`, si viva y no permite = 403 "fuera del alcance del aparato". Cookie-token remota: 401 que ADEMAS expira la cookie (`resp.delete_cookie(COOKIE)`). `/setup`: exenta solo si loopback Y sin `totp_secret` Y `?token=` valido (el porque esta en el spec — la ventana regalaba el secreto TOTP). `/login` remoto exitoso: en vez de `_session_response`, crear sesion `navegador` viva y setear `calipso_sesion` (el local sigue igual). Tests: alcance 403; cookie-token remota 401 + Set-Cookie vencida (canario); login remoto -> sesion sin token; /setup sin token = redirect aunque falte totp_secret.

- [ ] Test rojo, implementar, verde, suite, commit: `feat(sesiones): el guard resuelve sesiones; token solo-loopback tambien en cookie; setup endurecido`.

### Task 5: Los websockets aceptan sesion (y cierran el hueco del token)

**Files:**
- Modify: `calipso/server.py` (`ws_chat`, `ws_mapa`: el chequeo del handshake)
- Test: `test_sesiones_server.py` (ampliar)

Chequeo nuevo en ambos handshakes: `(_valid(cookie_token) and _es_loopback(ws.client.host)) or (sesion viva cuyo alcance cubra ese ws)` — ws_chat exige tipo `navegador`; `/ws/mapa` lo cubren `navegador` y `tablero`. **Canario del invariante 2: ws_chat con cookie-token desde host no-loopback = close 1008** (hoy entraria: es el hueco que la revision del spec cazo como bloqueante).

- [ ] Test rojo (el canario primero), implementar, verde, suite, commit: `feat(sesiones): los ws aceptan sesion y el token-cookie remoto ya no los abre`.

### Task 6: Blindaje del almacen en backup y permisos + migracion

**Files:**
- Modify: `calipso/backup.py` (SKIP_FILES_RAIZ += "sesiones.json"), `calipso/permisos/acciones.py` (es_credencial_del_servidor cubre sesiones.json)
- Test: `test_seguridad_backup.py` (ampliar)
- Doc: nota de despliegue en el spec o RUNBOOK: **rotar el TOKEN al desplegar la fase 1** (las cookies-token viejas de un anio).

- [ ] Test rojo, implementar, verde, suite, commit: `fix(seguridad): sesiones.json fuera del backup y bajo el NUNCA; nota de rotacion`.

## FASE 2 — la UI de /fabrica

### Task 7: Tarjetas de golpes y lista de aparatos

**Files:**
- Modify: `calipso/web/fabrica/inbox.js` (o el modulo de la superficie de solicitudes que muestre el molde actual — verificar contra `GET /api/permisos` y `data-inbox="responder"`), `calipso/web/fabrica/app.js`
- Test: cliente con `node --test` (reducer puro si el archivo lo permite) + `test_sesiones_server.py` para los endpoints que la UI consume

La tarjeta muestra: aparato (escapado con el esc()/textContent del molde — es input no autenticado), tipo SUGERIDO y el alcance en grande; botones aprobar (con selector de tipo, preseleccionado en la sugerencia) y rechazar. Lista de aparatos con estado efectivo y boton revocar (el POST exige loopback o sesion navegador). Todo por los endpoints de la Task 3.

- [ ] Implementar con el molde visual del inbox, tests, suite + node, commit.

## FASE 3 — el corte activo

### Task 8: Generaciones en memoria y el latido

**Files:**
- Modify: `calipso/server.py` (registro `_ws_generaciones: dict[hash_id, int]`; `revocar` lo incrementa via un hook; ws_chat chequea al recibir, antes de cada emision y en un latido con timeout alrededor de su espera; ws_mapa en su tick)
- Test: `test_sesiones_server.py` (ws de sesion revocada se corta aunque este ocioso)

- [ ] Test rojo, implementar, verde, suite, commit: `feat(sesiones): revocar corta los ws vivos, ociosos incluidos`.

### Task 9: Smoke en vivo + ronda adversaria + BRIEF

- [ ] Smoke con server desechable (home temporal): golpear con curl "remoto" (ASGI no alcanza aca: usar la IP real de la interfaz o simular), aprobar en /fabrica, usar con alcance, revocar, ver el corte. Documentar la transcripcion.
- [ ] Ronda adversaria de rama (eficacia/regresiones/completitud) ANTES del merge; fix round si hay hallazgos.
- [ ] Actualizar el BRIEF del lector: plugin = golpear->sesion `lector`; APK = tipo `tablero`. Merge a main + push. Rotar el TOKEN (paso de despliegue).

---

## La ruta: todo lo abierto al 2026-09-07 (para no perder el hilo)

**Specs con plan pendiente o en ejecucion:**

1. **Capa de sesion** — spec `2026-09-07-capa-de-sesion-design.md` (revisado adversarialmente, PENDIENTE de la lectura de Pedro; dos rulings a confirmar: tope 180 dias, tablero/lector no revocan). Plan: ESTE. Es el desbloqueante gordo del lector.
2. **El abismo, rebanada 1b** — el cableado de la consulta al chat vivo (spec `2026-09-07-abismo-consulta-design.md` secciones 4-10; el porton v2 esta EN VERDE con el contrato "dura" aterrizado). Plan pendiente de escribir. Piezas: filtro compuesto en el Emisor, estado del turno, reentrada sintetica (la seccion 4 ya enumera que saltea), senal de pondering, ramas de UI, pulso.
3. **El abismo, rebanadas 2-4** — sin spec todavia, decisiones madre tomadas (spec del abismo seccion 2): el fondo OneDrive (2: subida cifrada rclone, indice local, pesca, ojos sobre lo existente con anillos), la escena del mapa (3: la boca en el centro, cambio de escena, profundidad=anillos), los otros habitantes (4: jefes en su tic con corte seguro, el lector -- DEPENDE de la capa de sesion y trae los endpoints /api/lectura/*).

**Seguridad, lo que queda del informe (`2026-09-07-revision-seguridad.md`):**

4. **La escalada PUT /api/file + commands/run** — el ultimo bloqueante real de abrir el host tras la capa de sesion. Fix propio (motor de permisos sobre escrituras al repo de Calipso o verificacion del runner). Sin spec: la adenda p2 tiene el analisis.
5. **Raices explicitas del catastro** (hoy la raiz por defecto es el home entero) — chico, estructural.
6. **Tauri** (`src-tauri/src/lib.rs:118` navega con ?token=; es Rust) y el **bind solo-Tailscale operacional** al abrir.

**Fuera de seguridad/abismo:**

7. **La siembra de la economia** — TODO listo desde el 2026-09-03 (helper guiado ensayado, decisiones cerradas); falta solo el acto de Pedro: levantar el server un rato (probe de capacidad), elegir montos, disparar con la frase-token. El ticker solo late con el server prendido.
8. **La cara de terminal** (`calipso` en la consola, REPL contra /ws/chat) — en cola con mini-brainstorm de UX pendiente; limitacion conocida un-cliente-a-la-vez; systemd de usuario le daria cadencia a las rutinas de paso.
9. **Compositor** — refinamientos anotados: `/redacta /nube` (tapar solo el hilo), hilos multilinea (parse_directives aplana), panel en /fabrica, `/mias`, embeddings por registro.
10. **Ruteo Fase 2b** — la UI del ofrecimiento ("lo tengo local, queres la nube tapada?") y el degradado avisado; la senal ya viaja por WS sin pantalla.
11. **Lector** — el plugin Lua y la APK (BRIEF en calipso-lector/, actualizado hoy dos veces); bloqueado por: capa de sesion (1) + endpoints de lectura (rebanada 4, punto 3 de esta lista) + Tailscale operativo.
12. **Menores con nombre:** la rama `wip/sobre-obligatorio` (un commit sin verificar del 2026-09-02); los minors diferidos del 1a (armado fuera del try en resolver, PATRON con ⟦ anidado, re-corrida del banco pisa Observaciones, int() de env sin fallback, trim del contrato); el residual del balde global (DoS de disponibilidad compartido, revisitar cuando la capa de sesion reparta el login).
