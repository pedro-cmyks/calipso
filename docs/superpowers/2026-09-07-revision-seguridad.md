# Revision de seguridad de Calipso

**Fecha:** 2026-09-07
**Metodo:** cinco auditores en paralelo (auth, filesystem, red, subprocesos, secretos) sobre el codigo actual de main+rama, mas un refutador adversario por cada hallazgo critico/alto (11 verificaciones). Todo hallazgo de abajo sobrevivio a un intento serio de tumbarlo; las gravedades son las AJUSTADAS por los refutadores, no las de los auditores. 26 hallazgos brutos -> 8 confirmados (consolidados), 1 refutado, ~9 medios/bajos deduplicados.

**Modelo de amenaza:** (1) otro proceso/usuario local; (2) un aparato en la LAN/tailnet cuando se abra el bind (el plan del lector); (3) contenido malicioso que entra por canal legitimo (un repo clonado, un nombre de archivo, un mensaje) y escala; (4) fuga hacia logs/nube/subprocesos.

**La lectura de conjunto:** hoy el bind en 127.0.0.1 y el home en 0700 (Bazzite) tapan mucho. Varios hallazgos "altos" son criticos EN CUANTO se abra `CALIPSO_HOST` para el lector — la lista de abajo es, en la practica, el precio de entrada de la rebanada 4 del abismo y del lector. Y hay UNA critica que no depende de abrir nada.

## Confirmados

### C1 (CRITICA) — RCE al abrir un repo ajeno: `server._git` corre sin el blindaje que el propio repo documenta

El helper `_git` de server.py (`calipso/server.py:844-847`) invoca git con `cwd=ROOT` SIN las banderas que `catastro._git` (`calipso/catastro.py:123-138`) y `tools/commands.py` (`:20-31`) aplican y documentan como no negociables: `-c core.fsmonitor= -c diff.external= -c core.pager=cat` + `GIT_CONFIG_GLOBAL=/dev/null`. Un `.git/config` con `core.fsmonitor="comando; false"` ejecuta ese comando en un `git status` comun — vector verificado empiricamente por el propio repo. Lo usan `/api/git/status` (`:854-859`), `/api/git/diff` (`:882-890`) y el flujo de verify (`:3737-3742`). **El disparo es automatico:** la UI llama `loadGitStatus()` al abrir cualquier proyecto (`calipso/web/index.html:719`). Ataque (canal 3): un repo que llega a Pedro por via legitima trae el payload en su config; Pedro lo abre en Calipso; el comando corre como Pedro sin un clic mas. Bindear 127.0.0.1 no mitiga nada: el payload viaja adentro del repo.
**Arreglo:** un solo helper git blindado compartido (borrar el duplicado de server.py y usar el de catastro, o copiar las banderas + env). Mismo criterio para el runner de gh.

### C2 (ALTA) — El techo de `_switch_project` deja abrir `~` y `~/.calipso` como proyecto: el caso conocido SIGUE VIVO, y escala a ejecucion

`_switch_project` (`calipso/server.py:1035-1056`) solo exige carpeta existente + `catastro.dentro_de_alguna_raiz()`; la raiz por defecto es el HOME ENTERO (`calipso/catastro.py:184-186`) y el chequeo acepta la raiz misma (`p == r`, `:242`). Con el token: `POST /api/project/open {"path":"~"}` -> `GET /api/file?path=.ssh/id_ed25519` (la llave), `PUT /api/file {"path":".ssh/authorized_keys"}` (persistencia y ejecucion como Pedro — el PUT hace mkdir de padres, `:517-524`). El refutador intento cuatro vias de tumbarlo y ninguna prospero; noto ademas que /api/commands/run es allowlist estricta, o sea que ESTA es la escalada real de "usar el asistente" a "ser Pedro". Cuatro puertas comparten el techo (project/open, POST /api/chats, activate, el turno del ws).
**Arreglo:** exigir `_es_repo`, rechazar `p == raiz` y todo lo que resuelva dentro de CALIPSO_HOME; denylist de `~/.ssh`, `~/.aws`, `~/.gnupg` en `_safe`; mejor aun, raices de proyectos explicitas en vez del home entero.

### C3 (ALTA) — Fuerza bruta sin limite contra /login entrega el token maestro

`/login` es la unica ruta exenta del auth_guard (`calipso/server.py:312-313,338-348`); TOTP con ventana ±1 = 3 codigos validos por instante (`:220-229`); CERO rate limiting/lockout/backoff en todo el repo; y el exito setea la cookie con el TOKEN LITERAL (`:253-257`) — no una sesion: LA credencial permanente. Esperanza ~333k intentos; a velocidad de loopback, minutos u horas, sin ninguna senal. Hoy exige pie local (el vector real: flatpaks con red y sin home, otros uid); **pasa a critica sin cambiar una linea el dia que se abra CALIPSO_HOST**.
**Arreglo:** contador de intentos con backoff exponencial y lockout en login_submit. Y que la cookie no sea el token (ver M2).

### C4 (ALTA) — La credencial se multiplica: query string, access log, consola, navegador, y un server.log en disco con 38 copias

Familia consolidada de cinco reportes. `auth_guard` acepta `?token=` (`calipso/server.py:316`); `uvicorn.run` va sin `log_config` ni `access_log=False` (`:6605`) y el default loguea la request CON query (verificado en el uvicorn instalado); el filtro de log que el spec de ojos-y-manos DECIDIO agregar no existe (cero configuracion de logging en el paquete); el banner imprime el token (`:6599`); `launch_calipso.py` abre el navegador con `?token=` en cada arranque (`:56-60,76-79`) — historial del navegador (sync = nube, modelo 4) y argv de xdg-open visible en `/proc/*/cmdline`. Evidencia en disco: `~/.calipso/logs/server.log` (0644) contiene HOY 38 lineas con el token. Atenuante verificado: el home 0700 corta el acceso de otros uid hoy; el mismo-uid ya lee el token 0600 igual. La gravedad la sostienen el historial-del-navegador-a-la-nube y el dia que algo se abra.
**Arreglo:** filtro de logging que enmascare `token=` (decision ya tomada, sin implementar); no imprimir el token; navegador y sondeo sin `?token=` (cookie o POST de un solo uso); rotar el token actual (ya esta multiplicado).

### C5 (ALTA) — XSS almacenado en la UI vieja por nombres de archivo y rutas de git sin escapar

`nodeRow` mete `${name}` crudo por innerHTML (`calipso/web/index.html:743`), y las filas de git `${f.path}`/`${f.status}` (`:832,839,872`); `esc()` existe (`:1264`) y se usa en otros lados, aca no. Un archivo llamado `<img src=x onerror=...>` dentro de un repo abierto corre JS en la sesion autenticada: fetch mismo-origen con la cookie automatica -> `/api/file`, comandos del allowlist, financiar en la economia. La cookie httponly no protege: el XSS no necesita leerla.
**Arreglo:** esc() o textContent/createElement en arbol, cambios de git y catalogo de plugins (`:1080,1096`).

### C6 (ALTA) — El backup zipea token + totp_secret y esquiva el unico NUNCA del motor de permisos

`create_backup` camina TODO CALIPSO_HOME (`calipso/backup.py:38-53`); SKIP_DIRS solo excluye caches; el zip nace 0644. Y `es_credencial_del_servidor` (`calipso/permisos/acciones.py:200-205`) matchea SOLO las dos rutas exactas: **un agente al que el motor le niega leer `token` puede disparar `POST /api/backup` y leer el zip** — la credencial del servidor con la que el motor se gobierna, por la puerta de al lado. Hoy el home 0700 tapa a otros uid; el bypass del motor de permisos no lo tapa nadie.
**Arreglo:** excluir token/totp_secret/logs del backup (la credencial no se respalda: se regenera); zip 0600; extender la regla de credencial a backups/.

### C7 (MEDIA) — CALIPSO_NO_TOTP apaga el segundo factor para cualquier origen (decision S3, escrita y sin implementar)

`_TOTP_DISABLED` sale del entorno sin mirar origen (`calipso/server.py:335,343`) y la pantalla lo ANUNCIA. El spec de ojos-y-manos ya decidio atarlo a 127.0.0.1 (fila S3, "Abierto"). Atenuantes verificados: nada en el repo actual setea la variable (el shell Tauri que lo hacia fue corregido), y el ataque remoto exige ademas host abierto. Interruptor latente con fallo catastrofico.
**Arreglo:** implementar S3 tal como esta escrita.

### C8 (MEDIA) — HTTP en claro si algun dia se bindea 0.0.0.0

Sin TLS ni TrustedHost (`calipso/server.py:6605,139-155`). Atenuante fuerte que el refutador encontro: el BRIEF del lector ya recomienda Tailscale expresamente y 0.0.0.0 figura solo como atajo de prueba. Footgun latente, no exposicion vigente.
**Arreglo:** para el lector, bindear SOLO la IP de la interfaz Tailscale (cifrada); si el host no es loopback, rechazar `?token=` en claro.

## Refutado (y por que igual vale saberlo)

- **"Todo ~/.calipso nace world-readable (0644)"** — los hechos son ciertos (solo token/totp_secret van a 0600; ningun write pasa mode), pero `/var/home/pedro` esta en 0700 (default de Bazzite, verificado), asi que otro uid muere en el home antes de llegar. Gravedad real: BAJA, defensa en profundidad. Fix barato si se quiere: CALIPSO_HOME a 0700.

## Medios y bajos (deduplicados)

- **Websockets sin chequeo de Origin** (media): una pagina en OTRO puerto de 127.0.0.1 puede montar el WS de la sesion de Pedro desde el navegador. Chequear Origin en el handshake.
- **No hay capa de sesion** (media): la cookie ES el token eterno, sin rotacion, sin revocacion, sin identidad de dispositivo. Es LA pieza que el lector necesita de todos modos (D3 del brainstorming de agosto): sesiones derivadas + revocacion por aparato resuelven C3/C4 de paso.
- **PUT /api/config redefine los comandos de suscripcion** (media): segunda via de token-a-ejecucion; validar/allowlistear lo configurable.
- **Subprocesos de modelo heredan el entorno completo** (media): LITELLM_MASTER_KEY y CALIPSO_TOKEN (si esta exportado) llegan a claude/codex; el system-prompt ademas incrusta nombres/ramas de repos ajenos y va a `codex exec`. Sanitizar env al spawnear (el patron ya existe en memory.reflect, que popea las claves Anthropic).
- **Traversal en id de sesion** (`PUT /api/session/active`) y **attachment_ids sin sanitizar** en el ws (bajas): normalizar/validar los ids contra su directorio.
- **Llamada de suscripcion sin timeout** (baja): timeout=None en el camino bloqueante del chat.

## Orden de remediacion recomendado

1. **Ya, en cualquier momento (no depende de nada):** C1 (helper git blindado — es chico y es RCE hoy), C5 (esc() en los sumideros), C6 (backup sin secretos + zip 0600).
2. **Antes de sembrar mas confianza en el token:** C2 (el techo de _switch_project) y C4 (dejar de multiplicar la credencial + rotar el token).
3. **Portones de la puerta de red — bloqueantes de abrir CALIPSO_HOST para el lector:** C3 (rate limit en login), C7 (S3), C8 (bind solo Tailscale), capa de sesion + identidad de dispositivo (que el lector necesita igual: un solo trabajo, dos frutos).

Los tres primeros items del punto 1 son un dia de trabajo entre los tres y matan la unica critica vigente.
