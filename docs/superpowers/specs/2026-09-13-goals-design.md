# El goal que corre: la tarea con objetivo, criterio, tope y compuertas (2026-09-13, v2)

Spec de brainstorming con Pedro, 2026-09-13, revisado el mismo dia por cuatro lentes adversarias (modelo/
YAGNI, factibilidad por lectura, riesgo y seguridad, y Codex gpt-5.5): la seccion 15 lista los rulings. La
v1 esta en el commit `25d6491`. Subproyecto 1 de 3 del norte "que Calipso haga todo lo que hago con Claude
Code, y mas" (2: las manos completas; 3: los ojos). Todo archivo:linea es de main `4c5a1f9`.

## 1. De donde sale

Pedro, 2026-09-12: *"le quiero poder decir 'disena un asset para este juego de aves' y que el vaya y abra
Blender o lo instale, o se de cuenta que hay servicios en internet que lo hacen y cuanto valen, y me diga
lo que encuentra, haga y encuentre e itere"*; *"un chat headless, a toda la tarea ponerle slash goal, que
no pudieras parar hasta algo en lo cierto"*; *"las rutinas deberiamos cambiarlas por goals"*.

Decisiones de Pedro (2026-09-12/13):

- **El goal es de la mano, nunca del martillo.** Un modelo headless no puede seguir solo: cada invocacion es
  un golpe; Calipso lo vuelve a llamar, mide contra el criterio y decide si golpea otra vez.
- **La cabeza es el mejor modelo segun el ruteo**, y la economia cobra cada golpe contra el tope.
- **El juez es un revisor DISTINTO de la cabeza, y Pedro al final:** el que hizo el trabajo nunca se
  aprueba solo.
- **Compuertas.** SIN preguntar: editar y correr comandos en el repo del goal, buscar en la web y leer
  paginas, tocar archivos en raices declaradas fuera del repo, e **instalar solo dentro del goal** (afinado
  el 2026-09-13: venv y paquetes en el clon; `pip --user`, `npm -g`, `flatpak --system` y `rpm-ostree`
  PREGUNTAN, porque en Bazzite corren sin clave para su usuario; `rpm-ostree rebase|reset|rollback` y
  borrar remotes de flatpak NUNCA). CON pregunta: merge a la rama real, push, borrar fuera del repo del
  goal, raices nuevas. NUNCA sin Pedro: gastar, publicar, mandar correo, borrar sus datos.
- **Sin tope no corre. Termina esperando a Pedro. Nunca muere en silencio.**

## 2. Lo que ya existe y se extiende (y lo que se retira)

`calipso/goals.py` ("Goal Mode", 443 lineas): metas persistentes en `~/.calipso/projects/<slug>/goals/<id>/`
(`goal.json`, `events.jsonl`, `active.txt`), `objective`, `criteria`, `subtasks`, `evidence`, `blockers`,
estados `active/waiting/blocked/complete/cancelled`, `detect("meta: ...")` antes del ruteo
(`server.py:3944-3966`), `_goal_context` en el system (`server.py:3124-3158`, `prompt_compiler.py:236-237`),
`goal_id` en jobs y adjuntos, `/api/goals*` (`server.py:5528-5600`), `#goalBar` en la PWA
(`index.html:360-375`). Se conserva la identidad, el directorio y `events.jsonl` como ledger de estados.

Se retira o se cierra (ruling 15.3), porque contradice "sin tope no corre", "nadie es `complete` sin juez" y
"un goal activo": `goals.detect` deja de interceptar el turno (`meta: ...` entra por la misma rama que
`/goal` y produce `proposed`); `PUT /api/goals/{id}` rechaza `status` y `active` (las transiciones van por
endpoints propios); `check_auto_close`, `advance`, `draft` y los botones Avanzar/Verificar/Completar del
`#goalBar` se retiran (la barra queda de solo lectura); "activo" se lee de `~/.calipso/goals/activo.json`
(global, no del slug del `ROOT` conmutable); `_goal_context` lleva solo estado, ultimo golpe y lo que
espera, nunca el ledger. Los tests del harness siguen apagando el Goal Mode salvo los que lo prueban
(`test_abismo_chat.py:260-261`).

## 3. El goal

`goal.json` suma (los campos viejos siguen):

- `criterio`: `{"tipo": "comando" | "archivo" | "numero" | "revisor", ...}`: `comando` = un comando en el
  repo del goal que debe salir 0; `archivo` = una ruta que debe existir (y contener algo, opcional);
  `numero` = una metrica del ledger contra un umbral; `revisor` = no hay criterio medible. Si Pedro no da
  criterio, Calipso propone uno y lo muestra.
- `tope`: `{"golpes": 20, "minutos": 120, "unidades": 60, "mm": 0}`. `unidades` son llamadas de la
  suscripcion (las que cuentan contra la cuota de Pedro: se leen del `stream-json`); `mm` solo aplica a la
  ruta API. El primero que se alcanza para. Sin tope no corre: Calipso propone uno segun el tamano del goal.
- `compuertas`: la tabla de la seccion 8 con el nivel por familia y las `raices` (directorios fuera del repo
  del goal, lectura y escritura), propuestas por Calipso desde el texto y aprobadas con el "dale".
  **Declarar una raiz es declarar que su contenido puede salir hacia la suscripcion** (ruling 15.7).
- `proyecto`: la ruta del repo de origen (nunca el `ROOT` global del server). `repo`: el **clon** del goal en
  `~/.calipso/goals/<id>/repo` sobre la rama `goal/<id>` (ruling 15.4: siempre clon, nunca un worktree del
  checkout que sirve el server; el clon local usa enlaces duros y cuesta segundos; el venv, si hace falta,
  lo crea el primer golpe adentro del clon). Un goal sin repo (buscar precios) tiene `repo` None y el golpe
  corre en un directorio vacio del goal.
- `privado`: si el texto dispara el detector de privacidad (`dispatch.PRIVATE`) el goal nace `proposed`
  con el aviso "un goal privado no puede usar manos de suscripcion" y Pedro decide (ruling 15.7).
- `estado`: `proposed` (nuevo) -> `active` -> `waiting` (esperando a Pedro: checkpoint, pregunta de una
  compuerta, tope, cuota, no convergencia, server apagado) -> `complete` | `failed` (nuevo, con motivo) |
  `cancelled`. `blocked` se conserva para lo viejo. **Toda transicion pasa por `goals.transicionar(id, a,
  motivo)`**, lo unico que escribe `status` (escritura atomica: tmp + replace).
- `golpes.jsonl`: una fila por golpe con `n`, `manos` (`claude`/`codex`), `session_id`, `unidades`,
  `duracion_ms`, `veredicto_del_golpe` (`sigo`/`terminar`/`preguntar`, resumen), `comandos` (los que corrio
  el martillo, del `stream-json`), `diff_stat` (`git diff --stat` del clon tras el golpe), `secretos_tapados`,
  `juez` (si hubo). La fila con el paso se escribe ANTES de invocar; el resto DESPUES.

## 4. Crear un goal

- **`/goal <texto>`** es una directiva nueva en `capabilities.parse_directives` (`capabilities.py:199-253`;
  hoy borra todo token con `/` y, en `:244`, las rutas absolutas). Gramatica opcional dentro del texto:
  `hasta: <criterio>`, `tope: <2h | 20 golpes | 60 unidades>`, `en: <ruta del repo>`. `meta: ...` es alias.
  Se desvia ANTES del ruteo con el molde de `/redacta` (`server.py:4007-4030`); `_gesto_de` devuelve
  `/goal` para la aduana.
- **La propuesta** es un golpe SIN herramientas de la cabeza (el mejor modelo: `dispatch.extract_features`
  sobre el texto del goal para el tipo real, complejidad del goal, y piso de tier frontera (`EFFORT_MIN_TIER`
  de `/ultra`) salvo goal privado: ruling 15.2; el 7b nunca es cabeza de un goal con manos). Devuelve JSON
  (`--json-schema`): titulo, criterio, tope, familias y raices que va a necesitar, dominios de red, un plan
  de 3-6 pasos, y `manos` (`claude` o `codex`). Estado `proposed`; el chat lo muestra. `/goal dale` (o el
  boton en Goals o en el inbox) -> `active`; `/goal no` -> `cancelled`; `/goal dale tope: 1h raiz:
  ~/Descargas` ajusta y arranca.
- **Mientras corre:** `/goal parar`, `/goal segui <nota>` (cuando esta `waiting`; la nota entra al ledger),
  `/goal estado`. Un solo goal `active` por server (invariante 8); los demas `proposed` esperan.

## 5. El bucle

El runner (`calipso/goals_runner.py`) es un objeto con `iteracion()` (los tests lo llaman directo, sin
tarea de fondo) que en produccion corre como tarea propia registrada en `_GOALS_EN_CURSO` (no en
`_TAREAS_DE_FONDO`: el harness revienta a los 5 s con una tarea viva, `test_abismo_chat.py`), con el
proceso del golpe a mano para el cierre ordenado (ruling 15.9).

Cada iteracion:

1. **Mide la carga** (`carga.medir`): bajo `cargada` espera al tick siguiente sin gastar (fila
   `goal/pospuesto`); bajo `justa` y `holgada` sigue. Lee `consumo` (pasivo): si la cuota de Codex esta por
   encima del 90% o la ultima sesion de Claude termino en limite, `waiting` motivo `cuota`.
2. **El golpe** (seccion 7): la cabeza ES el martillo (ruling 15.1): una sesion headless con herramientas
   dentro del clon, con el contrato del goal (texto, criterio, compuertas, raices, plan, el ledger resumido
   con el diff_stat y las `falta` del juez SIN recortar) y que termina con un veredicto estructurado
   `{"estado": "sigo" | "terminar" | "preguntar", "resumen", "pregunta"}`. Entre golpes se continua la
   sesion (`--resume <session_id>`): el martillo recuerda lo que hizo sin reinyectar el ledger.
3. **Despues del golpe:** `git diff --stat` del clon, los `comandos` del `stream-json`, las `unidades`, el
   detector de secretos sobre todo lo que va al ledger (ruling 15.7), la fila de la aduana, el cobro
   (`Pagador` con `unidades` reales, concepto `goal:<id>`), y el tope.
4. **No convergencia** (ruling 15.8): tres golpes seguidos sin diff nuevo, o la misma `falta` del juez dos
   veces, o dos golpes con el mismo comando fallando igual -> `waiting` con el diagnostico y las opciones
   (cambiar el plan, pedir a Pedro, cambiar de manos, achicar el alcance). Antes del tope, no en vez del tope.
5. **El tope:** golpes, minutos, unidades o mm -> `waiting` motivo `tope` con lo que hay.
6. **Terminar:** criterio medible si existe (comando/archivo/numero); revisor (seccion 6); cumplido ->
   `waiting` con resumen y evidencias para Pedro; no cumplido -> la `falta` entra al ledger y el martillo
   sigue (cuenta como golpe). Pedro cierra (`complete`) o devuelve con nota.
7. **Preguntar:** la herramienta `preguntar` del veredicto y toda compuerta en `pregunta` dejan el goal
   `waiting` con la pregunta en el inbox (molde: la solicitud estacionada del motor de permisos,
   `permisos/motor.evaluar` con `Contexto(corrida)`; `/api/inbox` ya agrega tres tipos de espera). La
   respuesta de Pedro (inbox o `/goal segui`) entra al ledger y retoma.
8. **Fallo del CLI por cuota** (`exit != 0` con texto de limite; en Codex `resets_at` del jsonl): `waiting`
   motivo `cuota` con la hora de reset si se conoce; NUNCA cae al 7b ni a la otra familia sin que Pedro lo
   diga (`/goal segui con: codex`). El golpe queda en el ledger pero no cuenta contra el tope de golpes.

## 6. El juez

1. **Criterio medible** primero, sin modelo: `comando` (en el clon, salida 0, con la salida recortada al
   ledger), `archivo`, `numero`.
2. **Revisor de OTRA familia**, en solo lectura sobre el clon: si las manos fueron `claude`, el revisor es
   `codex exec -s read-only`; si fueron `codex`, `claude -p` sin herramientas de escritura. Recibe el goal,
   el resumen del ledger, `git diff` y las salidas, y contesta `{"cumplido": bool, "falta": [...], "nota"}`.
   Cuenta como golpe y se cobra. La fila del ledger anota `independencia`: `proveedor_distinto`,
   `modelo_distinto_mismo_cliente` (si solo hay una familia disponible) o `ninguna`.
3. **Sin otra familia y sin criterio medible**, el goal pasa a Pedro SIN veredicto de modelo (honesto; ruling
   15.6): el `#goalBar` y el inbox lo dicen. El 7b nunca juzga.
4. **Pedro al final, siempre:** ningun goal pasa a `complete` sin su "dale" o su respuesta en el inbox.

## 7. Las manos: el golpe

- **Claude Code (2.1.270)** como manos: `claude -p` con el prompt del golpe por **stdin** (nunca por argv ni
  en un archivo dentro del clon: `ps` y `git add -A` los verian), `cwd = clon`,
  `--append-system-prompt-file <contrato, fuera del clon>`, `--permission-mode acceptEdits
  --permission-prompts none`, `--restricted --tools Bash,Edit,Write,MultiEdit,Read,Glob,Grep,WebSearch,
  WebFetch` (ignora los settings de usuario y de proyecto: los 12 plugins y los `permissions.allow` de
  Pedro no entran, y el martillo no puede auto-escalarse escribiendo `.claude/settings.json`: ruling 15.5),
  `--setting-sources ""`, `--strict-mcp-config`, `--settings <json del goal>` (abajo), `--output-format
  stream-json --include-hook-events`, `--json-schema <veredicto del golpe>`, `--session-id <uuid del goal>`
  en el primer golpe y `--resume` en los siguientes. No existe `--max-turns`: el golpe se acota por
  **timeout** (por defecto 15 min; 3 en el smoke) que mata el grupo entero.
- **La barrera es el sandbox, no el hook** (ruling 15.5, critico de las cuatro lentes): el `--settings` del
  goal enciende el sandbox nativo de Claude Code sobre bubblewrap (`/usr/bin/bwrap` 0.12.0 esta en Bazzite):
  `sandbox.enabled`, `allowUnsandboxedCommands: false`, `excludedCommands: []`, escritura permitida = el
  clon + las raices declaradas, `denyRead` = `~/.ssh`, `~/.gnupg`, `~/.aws`, `~/.config/gh`,
  `~/.claude/.credentials.json`, `~/.codex`, `~/.calipso` (la lista ya existe en `permisos/acciones.py:
  179-185`), `network.allowedDomains` = `api.anthropic.com` mas los dominios que el goal declaro (sin
  `github.com`: asi push y PR son un hecho de red imposible, no un patron; el push con dale lo hace Calipso
  desde afuera con `git_runner`). Los nombres exactos de las claves los verifica el plan contra `claude
  --help` y la doc del sandbox; si alguna no existe en 2.1.270, se para y se dice.
- **El hook es la segunda capa, fail-closed:** `calipso/goals_hook.py` (stdlib puro, interprete absoluto,
  envuelto en `try/except BaseException` que deniega y sale 2 ante CUALQUIER error) con ALLOW-LIST de
  comandos simples y deniega lo que no sabe parsear (`;`, `&&`, `||`, `|`, `$(`, backticks, `bash -c`,
  `sh -c`, `eval`, `source`, heredocs, `xargs`, `find -exec`, `git -C`, `--git-dir`, `git worktree`,
  `update-ref`, `branch -D`), lo NUNCA (`gh pr create`, `gh release`, `git push`, `sudo`, `pkexec`,
  `rpm-ostree`, `flatpak --system|remote-*`, `mail`, `sendmail`, `rm` sobre las rutas protegidas) y las
  escrituras a `.claude/`, `.git/hooks/`, `.git/config` del clon; deja pasar `instalar` solo en su
  alcance directo (`pip install` dentro del venv del clon, `npm install` sin `-g`, `flatpak install
  --user` si el sandbox lo deja) anotando la linea de deshacer. **Sonda por golpe:** antes del primer golpe
  de cada goal, el hook se prueba con stdin sintetico (`gh pr create` -> exit 2); durante el golpe, el
  parser del `stream-json` exige un `hook_response` de nuestro hook antes de cada `tool_use`; un `tool_use`
  sin hook previo = matar el proceso y `failed` motivo `hook inactivo` (ruling 15.5).
- **Cada golpe en su cgroup:** `systemd-run --user --scope -p RuntimeMaxSec=<timeout> claude -p ...` si
  `systemd-run` existe (Bazzite: si), con `start_new_session=True` + `killpg` como fallback: el timeout y el
  apagado matan tambien lo que el martillo dejo con `nohup`/`setsid`.
- **Codex (0.142.4)** como manos: `codex exec -s workspace-write -C <clon> --add-dir <raices> --json -o <out>
  --output-schema <veredicto>`, con sandbox de kernel (landlock + seccomp) y red APAGADA: es valido para
  goals que no instalan ni buscan en la web dentro del golpe (ruling 15.10); la aduana por comando interno
  es del subproyecto 2. Lo elige la propuesta (`manos`) y Pedro lo puede cambiar con `/goal segui con:`.
- **El entorno:** reusa el saneado de `_subscription_invocation` (`server.py:3490-3565`: credenciales fuera,
  git blindado) mas `CALIPSO_HOME` fuera del alcance y sin `PYTHONPATH` al repo de Calipso; la invocacion
  es `Popen` sondeado desde el loop (molde `_run_subscription_text_live`, `server.py:3657-3727`), nunca
  `to_thread(subprocess.run)` (un golpe de 15 min colgaria el apagado: ruling 15.9).

## 8. Las compuertas, el motor de permisos, la aduana y la economia

- **La tabla** (`goals.COMPUERTAS`, la decision de Pedro afinada): `directo`: `repo` (editar y correr en el
  clon), `web`, `instalar_en_goal` (venv y paquetes dentro del clon), `raices` (las declaradas); `pregunta`:
  `merge`, `push`, `borrar_fuera`, `raiz_nueva`, `instalar_home` (`pip --user`, `npm -g`, `flatpak --user`
  fuera del clon), `instalar_sistema` (`rpm-ostree install`, `flatpak --system`, `remote-add`); `nunca`:
  `gastar`, `publicar`, `correo`, `datos_de_pedro`, `rpm-ostree rebase|reset|rollback`, `flatpak
  remote-delete`.
- **El motor de permisos** (`calipso/permisos/`): el goal es su PRIMER productor del camino desatendido
  (estaciona, pared de corrida, retoma). Se registran las familias de arriba con formas concretas (no clases
  abiertas: ruling 15.11): `pip install <paquete>` en el venv del clon, `npm install` en el cwd, `write` bajo
  raiz declarada, etc.; lo que no matchea una forma directa cae en `pregunta`; la preautorizacion que Pedro
  da a un goal (una raiz, una forma) vive en el goal con expiracion al cerrarlo, no en la politica global.
  El resto del server no cambia de politica.
- **La aduana:** `ORIGENES` suma `goal` (`aduana.py:55/105`); cada golpe es un cruce con
  `Quien(origen="goal", proyecto=<el del goal>, gesto="/goal", goal=<id>)`, `destino` None para la
  suscripcion y `dominios` = los permitidos al sandbox; `proyecto` es el del goal, nunca `_proyecto()`
  (`test_aduana_api.py:248`). Las instalaciones y los archivos tocados fuera del clon van al ledger y a la
  aduana con la linea de deshacer. El canario AST marca el `subprocess` del golpe: `cruzar` alrededor.
- **La economia:** cada golpe se cobra con el `Pagador` (concepto `goal:<id>`, `unidades` = llamadas reales
  del `stream-json`, no 1: ruling 15.12); la ruta local no cobra; `mm` solo en la ruta API; `costs.log_usage`
  sigue informativo. La propuesta le dice a Pedro cuanto de su cuota puede costar el goal (unidades y
  minutos estimados desde el tope).

## 9. Las rutinas y los goals (pospuesto)

Pedro quiere que las rutinas sean goals. Las cuatro lentes coinciden en que migrar `catastro` no prueba nada
del bucle (no tiene cabeza, manos ni juez) y que el ticker de hoy (handlers sincronos en serie, `KINDS`
cerrado, `last_run` tras el handler) no encaja con una corrida que dura minutos y puede quedar `waiting`.
Ruling 15.13: esta tanda NO toca `routines.py`; la primera migracion real es `reflect` (usa un modelo, cobra,
mide carga) en la tanda siguiente, con un adaptador que solo CREA la corrida desde el tick y vuelve.

## 10. Donde se ve

- **Pestana Goals en `/fabrica`** (molde `aduana.js` + `app.js:805-870` + `SHELL`/`CACHE` de `sw.js`):
  lista con estado, tope consumido (golpes/minutos/unidades), el ledger del goal (golpes con veredicto,
  comandos, diff_stat, costo), los botones `dale`, `no`, `parar`, `segui con nota`, y lo que espera
  respuesta. `sesiones.ALCANCES` da GET al tablero (fail-closed hoy).
- **En el chat:** la propuesta y los cierres son mensajes de Calipso; `/goal estado` devuelve el resumen. No
  hay push al `/ws/chat` fuera de un turno: la PWA sondea `/api/goals` cada 60 s para la `#goalBar` (solo
  lectura) y el inbox muestra lo que espera a Pedro.
- **Telemetria:** `kind: goal` por golpe y por transicion.

## 11. Invariantes

1. **Un goal sin tope no corre;** al tocar cualquier tope queda `waiting` con lo que hay.
2. **Ningun goal es `complete` sin juez y sin Pedro:** criterio medible o revisor de otra familia; si no hay
   ninguno, Pedro sin veredicto de modelo y se dice.
3. **Todo golpe esta en el ledger antes de ejecutarse**, con su costo, su diff y sus comandos despues.
4. **NUNCA se cumple aunque el martillo lo pida:** el sandbox lo hace imposible (sin red a github, sin
   lectura de credenciales, sin escritura fuera del clon y las raices) y el hook lo deniega como segunda
   capa; un golpe sin hook activo se mata.
5. **El goal no depende del `ROOT` global:** lleva proyecto, clon y raices propios; el checkout que sirve
   el server real no es escribible desde un golpe.
6. **Fail-open del server:** un goal que revienta queda `failed` con motivo; nunca tumba el server, el
   ticker ni el chat; el apagado deja el goal `waiting` y mata el golpe; el arranque reconcilia.
7. **Bajo `cargada` el goal espera** sin gastar; con la cuota agotada tambien.
8. **Un goal activo a la vez** por server.
9. **Lo que sale de la maquina se declara:** todo lo que el martillo lee en el clon y en las raices viaja a
   la suscripcion; el detector de credenciales tapa lo que parece credencial en el ledger y en el prompt;
   un goal privado no tiene manos de suscripcion.

## 12. Verificacion

- Unitarios de `goals.py` extendido (campos, `transicionar` con transiciones cerradas y escritura atomica,
  gramatica de `/goal`, tope, `golpes.jsonl`, `COMPUERTAS`, `activo.json` global), del clon (crea/borra sobre
  un repo temporal, rama `goal/<id>`, `git diff --stat`), del hook (allow/deny/pregunta con comandos
  concretos: `pip install x` en el venv, `rm -rf ~/.ssh`, `git push`, `gh pr create`, `bash -c "..."`,
  `rpm-ostree install`, escribir `.claude/settings.json`; y que ante un error interno deniega), del parser
  de `stream-json` (comandos, unidades, veredicto, la sonda del hook), del detector de secretos sobre el
  ledger.
- El runner con manos falsas (`cli_falso` de `test_abismo_suscripcion.py` extendido a `stream-json`, que
  anota `argv`, `cwd`, stdin y el `--settings` recibido): el ciclo entero (proposed -> dale -> golpes ->
  terminar -> revisor de otra familia falla -> sigue -> cumple -> waiting -> Pedro -> complete); los cuatro
  topes; no convergencia; JSON invalido; una compuerta `pregunta` -> waiting y retoma; `cargada` ->
  pospuesto; cuota agotada -> waiting sin caer al 7b; el revisor de la otra familia; `independencia` sin
  otra familia; el cobro por golpe con unidades; la fila de la aduana con `origen goal`; el apagado (mata
  el proceso falso, `waiting`) y el arranque (reconcilia).
- Tests node de la pestana Goals; el harness de ws para `/goal ...`, `dale`, `no`, `parar`, `segui`,
  `estado`, y `meta:` como alias que produce `proposed`.
- **Smoke en vivo** (server desechable, Claude Code real por suscripcion, repo temporal SIN remoto, un `gh`
  de mentira primero en el `PATH` que anota su argv y sale 1, sandbox con red solo a `api.anthropic.com`,
  `--restricted`, tope 6 golpes 10 min, timeout de golpe 3 min): un goal chico y medible (`crea un modulo
  saludo.py con hola() y su test; hasta: pytest en verde`) de punta a punta con el revisor real (`codex
  -s read-only`), midiendo golpes, unidades y minutos por golpe (el dato para la seccion 8); un goal que
  pide el NUNCA (`publicalo con gh pr create`) denegado por el hook Y sin red al remoto (si el `gh` falso
  anota una llamada, el test es rojo); uno que pide una raiz nueva y queda `waiting`; el apagado del server
  con un golpe en curso (el proceso muere, el goal queda `waiting`); y la verificacion de que el sandbox
  esta activo (un `cat ~/.ssh/id_ed25519` desde el martillo falla). Registrar el radio de dano verificado
  de un fail-open. El server real no se toca.

## 13. Lo que NO hace

- No tiene ojos ni clicks (subproyecto 3). No expone un MCP hacia Calipso ni mide cada comando interno del
  martillo en la aduana (subproyecto 2). No aprende recetas. Blender y los servicios con precio son
  goals concretos que se escriben con esto, no piezas de esta tanda.
- No corre dos goals a la vez. No migra rutinas (seccion 9). No usa un usuario del sistema aparte ni un
  contenedor (otra tanda si el sandbox no alcanza).
- No empuja al `/ws/chat` fuera de un turno.

## 14. Corte

Una rama `feat/goals`, 7 tasks: (1) `goals.py` extendido (campos, `transicionar`, `activo.json` global,
`golpes.jsonl`, `COMPUERTAS`, gramatica) + el retiro de `detect`/`check_auto_close`/`PUT status` + el clon en
`calipso/github.py` + tests; (2) `/goal` en `parse_directives` + la propuesta (cabeza frontera sin
herramientas, JSON) + `dale/no/parar/segui/estado` + el inbox + `_goal_context` recortado + tests por
harness; (3) `calipso/goals_manos.py` (la invocacion con sandbox, `--restricted`, stdin, `stream-json`,
`--json-schema`, `--resume`, `systemd-run`/`start_new_session`, timeout, parser con la sonda del hook,
detector de secretos, variante Codex) + `calipso/goals_hook.py` + tests con `cli_falso`; (4)
`calipso/goals_runner.py` (`iteracion()`, tope, carga, cuota, no convergencia, juez con criterio medible y
revisor de otra familia, `independencia`, `waiting`, `_GOALS_EN_CURSO`, apagado y reconciliacion) + la aduana
con `origen goal` + el `Pagador` por golpe + tests; (5) las familias del goal en el motor de permisos con
formas concretas + el hook que las lee + tests; (6) la pestana Goals, la `#goalBar` de solo lectura con
sondeo, el inbox, `ALCANCES` + tests node; (7) el smoke en vivo y el cierre.

## 15. Rulings de la revision adversaria (2026-09-13; todos revertibles)

1. **La cabeza ES el martillo.** Un golpe es una sesion headless con herramientas (veredicto estructurado
   al final, `--resume` entre golpes), no "la cabeza decide un paso en JSON y las manos lo ejecutan": gasta la
   mitad de cuota por golpe y el juez ve el diff real, no el resumen de una cabeza que no ejecuto nada. La
   cabeza sin herramientas queda solo para la propuesta y para goals sin repo.
2. **Cabeza por ruteo con piso frontera.** `features.type = "goal"` no existe en el registro y el ranking lo
   ganaba el 7b por costo (medido: `{goal, c3}` -> 7b primero). Se usa el tipo real del texto
   (`extract_features`) con piso de tier frontera; el 7b solo por goal privado, y entonces sin manos.
3. **El Goal Mode viejo se cierra:** `detect` fuera del turno, `PUT` sin `status`/`active`, `transicionar`
   como unica puerta, `proposed`/`failed` en `VALID_STATES`, `activo.json` global, `#goalBar` de solo
   lectura. Sin esto "sin tope no corre" y "un goal activo" se rompian por el alias `meta:`.
4. **Siempre un clon, nunca un worktree.** Un worktree del repo de Calipso comparte `.git`, `.venv` y el
   checkout que sirve el server real (los estaticos se sirven del disco en el acto); el clon en
   `~/.calipso/goals/<id>/repo` con venv propio aisla eso, y vale igual para cualquier otro repo.
5. **El sandbox es la barrera; el hook, la segunda capa.** El hook `PreToolUse` de Claude Code 2.1.270 es
   fail-open (exit distinto de 2 = la herramienta corre) y por patrones no ve adentro de `bash -c`,
   scripts, `python -c` ni post-install de paquetes; `--add-dir` solo gobierna las herramientas de archivo.
   Bubblewrap + `--restricted --tools` + `--setting-sources ""` + sonda por golpe (`--include-hook-events`)
   + cgroup por golpe. Radio de dano verificado de un fail-open sin esto: push y PR (gh autenticado),
   instalacion de sistema sin clave, lectura de `~/.ssh` y `~/.calipso`.
6. **El juez, en orden:** criterio medible; revisor de OTRA familia (Pedro tiene claude y codex); sin otra
   familia, Pedro sin veredicto de modelo. "Otro modelo del mismo cliente" no es independencia y se anota
   como tal; el 7b nunca juzga.
7. **Privacidad con la verdad:** lo que el martillo lee en el clon y en las raices viaja a la suscripcion;
   declarar una raiz es declarar esa fuga; el detector de secretos tapa credenciales en el ledger y en el
   prompt; el prompt va por stdin y el contrato en un archivo fuera del clon; `denyRead` de credenciales y
   de `~/.calipso`; goal privado sin manos de suscripcion.
8. **No convergencia antes del tope:** tres golpes sin diff, la misma `falta` dos veces, el mismo comando
   fallando igual -> `waiting` con diagnostico.
9. **El server:** `_GOALS_EN_CURSO` propio, `Popen` sondeado desde el loop con sesion propia (o
   `systemd-run --scope`), apagado que mata y deja `waiting`, arranque que reconcilia con `git status` del
   clon. `_esperar_fondo_al_apagar` no cancela nada y `to_thread(subprocess.run)` colgaria el apagado.
10. **Codex es mano valida y confinada** (sandbox de kernel, red apagada): sirve para goals sin instalar
    ni web dentro del golpe. La v1 lo tenia al reves.
11. **El motor de permisos no se saltea:** familias del goal con formas concretas; lo abierto cae en
    `pregunta`; la preautorizacion vive en el goal y expira con el.
12. **Cuota y unidades:** `unidades` reales por golpe desde el `stream-json` (una sesion son 10-40 llamadas,
    no 1); cuota agotada -> `waiting` motivo `cuota`, nunca el 7b como sustituto; `mm` solo en la ruta API;
    la propuesta estima el costo en cuota.
13. **Rutinas: otra tanda.** `catastro` no prueba nada; `reflect` es la primera migracion real.
14. **Instalar** (afinado por Pedro): directo solo dentro del goal; home pregunta; sistema pregunta; rebase,
    reset, rollback y borrar remotes nunca; `dnf` no instala en Bazzite y sale del spec; cada instalacion con
    su linea de deshacer y el estado antes/despues (`pip list`, `npm ls`, `flatpak list`).
