# El goal que corre: la tarea con objetivo, criterio, tope y compuertas (2026-09-13)

Spec de brainstorming con Pedro, 2026-09-13. Subproyecto 1 de 3 del norte "que Calipso haga todo lo que
hago con Claude Code, y mas" (2: las manos; 3: los ojos). Pendiente de revision adversaria. Todo
archivo:linea es de main `4c5a1f9`.

## 1. De donde sale

Pedro, 2026-09-12: *"le quiero poder decir 'disena un asset para este juego de aves' y que el vaya y abra
Blender o lo instale, o se de cuenta que hay servicios en internet que lo hacen y cuanto valen, y me diga
lo que encuentra, haga y encuentre e itere"*; *"un chat headless, a toda la tarea ponerle slash goal, que
no pudieras parar hasta algo en lo cierto"*; *"las rutinas deberiamos cambiarlas por goals"*.

Lo que se acordo en el brainstorm (2026-09-12/13):

- **El goal es de la mano, nunca del martillo.** Un modelo headless no puede seguir solo: cada invocacion es
  un golpe; Calipso lo vuelve a llamar, mide contra el criterio y decide si golpea otra vez. El bucle vive
  en Calipso.
- **La cabeza del bucle es el mejor modelo segun el ruteo** (decision de Pedro): `capabilities.choose` elige
  como en un turno (suscripcion para lo complejo, el 7b para lo trivial o privado); la economia cobra cada
  golpe contra el tope del goal.
- **El juez es un revisor DISTINTO de la cabeza, y Pedro al final** (decision de Pedro): el que hizo el
  trabajo nunca se aprueba solo; antes de darlo por hecho, el goal queda esperando a Pedro.
- **Compuertas** (decision de Pedro, las cuatro): SIN preguntar puede editar y correr comandos en su
  worktree, buscar en la web y leer paginas, instalar software y paquetes, y tocar archivos fuera del
  worktree. CON pregunta: merge a la rama real, push, borrar fuera del worktree, raices nuevas. NUNCA sin
  Pedro: gastar, publicar, mandar correo, borrar sus datos. Advertencia escrita: instalar y tocar afuera
  son las dos puertas por donde un goal puede romper algo; las mitigaciones son el ledger antes del hecho,
  las raices declaradas en la propuesta, y el NUNCA.
- **Sin tope no corre. Termina esperando a Pedro. Nunca muere en silencio.**

## 2. Lo que ya existe y se extiende (no se duplica)

`calipso/goals.py` (443 lineas, "Goal Mode"): metas persistentes en
`~/.calipso/projects/<slug>/goals/<id>/` (`goal.json`, `events.jsonl`, `active.txt`), con `objective`,
`criteria` (con `done`), `subtasks`, `evidence`, `blockers`, estados `active/waiting/blocked/complete/
cancelled`, `detect("meta: ...")` que intercepta el mensaje antes del ruteo (`server.py:3944-3966`),
`_goal_context` en el system, `goal_id` en los jobs y adjuntos, `/api/goals*` (`server.py:5528-5600`) y
`#goalBar` en la PWA. Es la identidad y la persistencia; le falta todo lo que corre: criterio medible,
tope, compuertas, worktree, el bucle, el juez, la carga, la aduana y la economia. Se extiende el mismo
objeto y el mismo directorio; `events.jsonl` es el ledger. Los tests del harness lo apagan
(`test_abismo_chat.py:260-261`): siguen apagandolo salvo los que prueban el goal.

## 3. El goal

`goal.json` suma estos campos (los viejos siguen):

- `criterio`: `{"tipo": "comando" | "archivo" | "numero" | "revisor", ...}`. `comando` = un comando en el
  worktree que debe salir 0 (`pytest -q`); `archivo` = una ruta que debe existir (y opcionalmente contener
  algo); `numero` = una metrica del ledger contra un umbral; `revisor` = no hay criterio medible: juzga
  otro modelo (seccion 6). Si Pedro no da criterio, Calipso propone uno y lo muestra.
- `tope`: `{"golpes": 20, "minutos": 120, "mm": 0}` (milimonedas de la economia). Los tres cuentan; el
  primero que se alcanza para. Sin tope no corre: Calipso propone uno segun el tamano del goal.
- `compuertas`: la tabla de la seccion 8 con el estado por familia (`directo` / `pregunta` / `nunca`) y las
  `raices` (directorios fuera del worktree que el goal puede tocar), propuestas por Calipso desde el texto
  y aprobadas con el "dale".
- `proyecto` y `worktree`: la raiz del repo del goal (nunca el `ROOT` global del server, que es conmutable:
  `_switch_project`, `server.py:1906-1948`) y el worktree propio `<repo>/.claude/worktrees/goal-<id>`
  sobre una rama `goal/<id>` (helper nuevo en `calipso/github.py`: `worktree_add/remove`; identidad de
  commit "Calipso <calipso@local>"). Un goal sin repo (buscar precios de un servicio) tiene `worktree`
  None y solo la herramienta `web`.
- `estado`: `proposed` (nuevo) -> `active` -> `waiting` (esperando a Pedro: por checkpoint, por pregunta
  de una compuerta, por tope) -> `complete` | `failed` (nuevo, con motivo) | `cancelled` (parado por
  Pedro). `blocked` se conserva para lo viejo.
- `golpes`: contador, y `golpes.jsonl` en el directorio del goal: una fila por golpe con `n`, `paso`
  (herramienta y argumentos), `ruta` y `modelo` de la cabeza, `costo_mm`, `duracion_ms`, `observacion`
  (recortada), `comandos` (los del martillo si vinieron por `stream-json`), `veredicto` si hubo revisor.
  `events.jsonl` sigue siendo el ledger de estados (creado, propuesto, dale, golpe, pregunta, tope,
  cumplido, parado).
- `permanente` y `disparador` (seccion 9): para los goals que antes eran rutinas.

## 4. Crear un goal

- **`/goal <texto>`** es una directiva nueva en `capabilities.parse_directives` (`capabilities.py:199-253`;
  hoy borra todo token con `/` y, en `:244`, las rutas absolutas: `/goal` se traga en silencio). Gramatica
  opcional dentro del texto: `hasta: <criterio>`, `tope: <2h | 20 golpes | 500 mm>`, `en: <ruta del repo>`.
  `meta: ...` (el `detect` viejo) queda como alias. Se desvia ANTES del ruteo, con el molde de `/redacta`
  (`server.py:4007-4030`); `_gesto_de` devuelve `/goal` para la aduana.
- **La propuesta:** Calipso (la cabeza por ruteo, un golpe que cuenta) responde en el chat con el goal
  armado: titulo, criterio, tope, compuertas y raices, worktree, y un plan de 3-6 pasos. Estado `proposed`.
  Pedro contesta `/goal dale` (o el boton en la pestana Goals o en el inbox) y pasa a `active`; `/goal no`
  lo cancela; `/goal dale tope: 1h` ajusta y arranca.
- **Mientras corre:** `/goal parar` (cancelled), `/goal segui <nota>` (cuando esta `waiting`, la nota entra
  al ledger y sigue), `/goal estado`. Un solo goal `active` a la vez por server (invariante 8); los demas
  `proposed` esperan turno.

## 5. El bucle

El runner (`calipso/goals_runner.py`) es una tarea de fondo del server, una por goal activo, con el molde de
`_en_fondo`/`_esperar_fondo_al_apagar` (`server.py`) mas cancelacion ordenada: al apagar el server el goal
queda `waiting` con motivo `server apagado` y retoma al arrancar si Pedro lo pide (`/goal segui`).

Cada iteracion:

1. **Mide la carga** (`carga.medir`): bajo `cargada` espera al tick siguiente sin gastar (fila
   `goal/pospuesto`); bajo `justa` y `holgada` sigue.
2. **La cabeza decide el paso.** Prompt: el goal (texto, criterio, compuertas, raices), el plan, el ledger
   resumido (ultimos N golpes con sus observaciones recortadas) y el catalogo de herramientas de este goal.
   La cabeza se elige con `capabilities.choose` con `features.type = "goal"` (complejidad del goal, no del
   paso) y contesta UN paso en JSON: `{"herramienta": ..., "args": ..., "porque": ...}` o
   `{"herramienta": "terminar", "resumen": ...}` o `{"herramienta": "preguntar", "pregunta": ...}`. Un JSON
   invalido cuenta como golpe fallido; tres seguidos -> `failed`.
3. **El golpe.** Se ejecuta la herramienta (seccion 7), se cobra (`_cobrar_turno`/`Pagador` con concepto
   `goal:<id>`, molde `_run_chat_draft._cobrar_borrador`), se anota en `golpes.jsonl` ANTES de ejecutar (el
   paso) y DESPUES (la observacion, el costo, la duracion). La aduana lo ve (seccion 8).
4. **El tope.** Si golpes, minutos o mm superan el tope: `waiting` con motivo `tope` y el resumen de lo que
   hay. Nunca muere en silencio.
5. **Terminar.** Cuando la cabeza dice `terminar`: si el criterio es medible se corre (comando/archivo/
   numero); si no, o ademas, el revisor juzga (seccion 6). Cumplido -> `waiting` con el resumen y la
   evidencia para Pedro; no cumplido -> la nota del revisor entra al ledger y la cabeza sigue (cuenta como
   golpe). Pedro cierra (`complete`) o devuelve con nota (sigue).
6. **Preguntar.** La herramienta `preguntar` y toda compuerta en `pregunta` dejan el goal `waiting` con la
   pregunta en el inbox (molde: la solicitud estacionada del motor de permisos, `permisos/motor.evaluar`
   con `Contexto(corrida)` y `estacionada`; `/api/inbox` ya agrega tres tipos de espera). La respuesta de
   Pedro (inbox o `/goal segui`) entra al ledger y el bucle retoma.

## 6. El juez

- **Criterio medible** primero: `comando` (en el worktree, salida 0, con la salida recortada al ledger),
  `archivo`, `numero`. Sin modelo.
- **Revisor:** otro modelo, DISTINTO de la cabeza: si la cabeza fue `claude`, el revisor es `codex`
  (o al reves); si solo hay uno disponible, el mismo cliente con otro modelo del registro; el 7b como
  ultimo recurso (y se dice). Recibe el goal, el resumen del ledger y las evidencias (archivos tocados,
  diff del worktree, salidas) y contesta `{"cumplido": bool, "falta": [...], "nota": ...}`. Cuenta como
  golpe y se cobra.
- **Pedro al final**, siempre: ningun goal pasa a `complete` sin su "dale" (o su respuesta en el inbox).
  Excepcion: los goals permanentes de la seccion 9 con criterio medible cierran solos (son las rutinas).

## 7. Las manos minimas (lo que este subproyecto necesita; el subproyecto 2 las completa)

Catalogo de herramientas del goal (un dict en `goals_runner.py`, con costo estimado y familia de compuerta):

- **`manos`**: una invocacion headless con herramientas dentro del worktree. Claude Code 2.1.270:
  `claude -p <paso> --permission-mode acceptEdits --permission-prompts none --allowedTools <lista>
  --add-dir <raices> --output-format stream-json --append-system-prompt-file <contrato del goal>` con
  `cwd = worktree` (`subprocess`, no hay `--cwd`); las compuertas se aplican con un **hook `PreToolUse`**
  (`--settings <json>`) que corre `calipso/goals_hook.py`: deniega lo NUNCA (pagos, `gh pr create`,
  `gh release`, correo, `rm` sobre `~/.calipso`/`~/.ssh`/datos de Pedro), deniega y estaciona lo
  `pregunta` (`git push`, `git merge` a la rama real, `rm` fuera del worktree, escribir fuera de las
  raices), y deja pasar lo `directo` anotandolo (instalar: `pip`, `npm`, `flatpak`, `dnf`, con el tamano
  si se puede saber). Codex 0.142.4: `codex exec -s workspace-write -C <worktree> --add-dir <raices>
  --json <paso>` (la red la habilita la config del sandbox); sin hooks, asi que las compuertas se aplican
  leyendo el `--json` a posteriori y el NUNCA se cumple negandole a Codex las raices sensibles (para lo
  irreversible, Codex no se usa como manos hasta el subproyecto 2: ruling). La salida `stream-json`/`--json`
  se parsea: cada comando del martillo va a `comandos` del golpe (visible en el ledger), y el texto final es
  la observacion. Reusa `_subscription_invocation` (`server.py:3490-3565`: entorno saneado, credenciales
  fuera) con `cwd` y flags nuevos por parametro; hoy no hay timeout: el golpe lleva uno (por defecto 15
  min) y al vencer mata el proceso y anota.
- **`web`**: `/web` de hoy (busqueda + leer paginas), medido por la aduana.
- **`leer`**: leer un archivo del worktree o de las raices (sin modelo).
- **`preguntar`** y **`terminar`** (seccion 5).

Lo que NO esta en este subproyecto: el MCP para que el martillo le pregunte a Calipso, la aduana por cada
comando interno del martillo (hoy: un golpe = un cruce), herramientas propias mas finas, los ojos.

## 8. Las compuertas, la aduana y la economia

- **La tabla** (`goals.COMPUERTAS`, con lo que decidio Pedro): `directo`: `worktree` (editar y correr),
  `web`, `instalar`, `raices` (los directorios declarados en la propuesta); `pregunta`: `merge`, `push`,
  `borrar_fuera`, `raiz_nueva`; `nunca`: `gastar`, `publicar`, `correo`, `datos_de_pedro`. Se registran
  como familias del motor de permisos (`calipso/permisos/`: hoy "instalar" y "escribir fuera de raices"
  son nivel `pregunta` y `gastar/publicar/correo` existen solo como tipos de la cola sin llamador): el goal
  es el PRIMER productor del camino desatendido del motor (estaciona, pared de corrida, retoma). Ruling
  explicito: para `origen == "goal"` la politica es la tabla de Pedro; el resto del server no cambia.
- **La aduana:** `ORIGENES` suma `goal` (`aduana.py:55/105`); cada golpe es un cruce con `Quien(origen=
  "goal", proyecto=<el del goal>, gesto="/goal", goal=<id>)`, `destino` None para las manos (el modelo de
  suscripcion) y el host para `web`; `proyecto` es el del goal, nunca `_proyecto()` (que lee el ROOT
  conmutable, `test_aduana_api.py:248`). La pestana Aduana cuenta los cruces por goal.
- **La economia:** cada golpe se cobra con el `Pagador` (concepto `goal:<id>`, ruta y modelo de la cabeza
  o de las manos); la ruta local no cobra (como hoy); el tope en `mm` se compara contra la suma cobrada
  en `golpes.jsonl` (no contra el libro: el cobro nunca frena, lo rechazado va a `cargos_pendientes`).
  `costs.log_usage` sigue informativo.

## 9. Las rutinas pasan a ser goals

- Un goal `permanente` tiene `disparador` (`{"cada_minutos": 60}` o `{"evento": ...}`, por ahora solo el
  reloj), criterio medible y tope chico, y no espera a Pedro al terminar (cierra su corrida y vuelve a
  esperar el disparador). El ticker (`_tick_con_carga` -> `run_due`, `routines.py`) suma el kind `goal`
  (`KINDS` es una tupla cerrada, `routines.py:33`): cuando vence, crea una corrida del goal (una serie
  acotada de golpes) en vez de llamar a un handler; bajo `cargada` se pospone como todo.
- **En esta tanda se migra UNA rutina** como prueba (`catastro`: criterio medible = el catastro escrito y
  reciente; tope 2 golpes; sin modelo) y las otras cinco (`reflect`, `consumo`, `backup`, `cierre`,
  `departamento`) siguen como handlers hasta la tanda siguiente. Ruling: la migracion entera es otra
  tanda porque cada handler tiene su propio contrato (el jefe, el cierre de la economia).

## 10. Donde se ve

- **Pestana Goals en `/fabrica`** (molde `aduana.js` + `app.js:805-870` + `SHELL`/`CACHE` de `sw.js`):
  lista con estado, tope consumido (golpes/minutos/mm), el ledger del goal seleccionado (golpes con paso,
  observacion, comandos, costo), los botones `dale`, `parar`, `segui con nota`, y lo que espera respuesta.
  `sesiones.ALCANCES` da GET al tablero (fail-closed hoy).
- **En el chat:** la propuesta y los cierres son mensajes de Calipso; mientras corre, `/goal estado`
  devuelve el resumen. No hay push al `/ws/chat` fuera de un turno (limite de hoy): la PWA sondea
  `/api/goals` cada 60 s para la `#goalBar` (que ya existe) y el inbox muestra lo que espera a Pedro.
- **Telemetria:** `kind: goal` por golpe y por cambio de estado.

## 11. Invariantes

1. **Un goal sin tope no corre;** al tocar cualquier tope queda `waiting` con lo que hay.
2. **Ningun goal es `complete` sin un juez distinto de la cabeza y sin Pedro** (salvo los permanentes
   con criterio medible).
3. **Todo golpe esta en el ledger antes de ejecutarse**, con su costo despues.
4. **NUNCA se cumple aunque la cabeza lo pida:** el hook deniega, el motor estaciona, la aduana lo anota.
5. **El goal no depende del `ROOT` global:** lleva proyecto, worktree y raices propios.
6. **Fail-open del server:** un goal que revienta queda `failed` con motivo; nunca tumba el server, el
   ticker ni el chat.
7. **Bajo `cargada` el goal espera** sin gastar.
8. **Un goal activo a la vez** por server; los demas esperan `proposed`.
9. **Lo que sale de la maquina pasa por la aduana** con `origen goal`; el juez de privacidad y el detector
   de credenciales siguen valiendo para `web` y para lo que viaja al modelo de suscripcion.

## 12. Verificacion

- Unitarios de `goals.py` extendido (campos, estados, gramatica de `/goal`, tope, `golpes.jsonl`,
  `COMPUERTAS`), del helper de worktree (crea/borra sobre un repo temporal), del hook (allow/deny/pregunta
  con comandos concretos: `pip install x`, `rm -rf ~/.ssh`, `git push`, `gh pr create`, escribir dentro y
  fuera de las raices), del parser de `stream-json`.
- El runner con manos falsas (`cli_falso` de `test_abismo_suscripcion.py` con salida `stream-json`), cabeza
  y revisor doblados: el ciclo entero (proposed -> dale -> golpes -> terminar -> revisor falla -> sigue ->
  revisor cumple -> waiting -> Pedro -> complete); el tope en golpes, minutos y mm; JSON invalido x3 ->
  failed; una compuerta `pregunta` -> waiting y retoma con la respuesta; `cargada` -> pospuesto sin golpe;
  el revisor distinto de la cabeza; cobro por golpe en el libro; la fila de la aduana con `origen goal`.
- El ticker con un goal permanente (`catastro` migrado): vence, corre, cierra solo, se pospone bajo carga.
- Tests node de la pestana Goals; el harness de ws para `/goal ...`, `dale`, `parar`, `estado`.
- **Smoke en vivo** (server desechable, Claude Code real por suscripcion, un repo de prueba en un tmp): un
  goal chico y medible (`crea un modulo saludo.py con una funcion hola() y su test; hasta: pytest en verde;
  tope: 6 golpes 10 min`) de punta a punta con el revisor real, midiendo golpes, costo y tiempo; un goal
  que toca el NUNCA (`publicalo con gh pr create`) y queda denegado; uno que pide una raiz nueva y queda
  `waiting`. El server real no se toca.

## 13. Lo que NO hace

- No tiene ojos ni clicks (subproyecto 3). No expone un MCP hacia Calipso ni mide cada comando del
  martillo en la aduana (subproyecto 2). No aprende recetas (el aprendiz, despues de las manos).
- No corre dos goals a la vez. No migra las seis rutinas (una, como prueba).
- No usa Codex como manos para lo irreversible hasta que tenga hook (ruling en la seccion 7).
- No empuja al `/ws/chat` fuera de un turno (sondeo de 60 s).

## 14. Corte

Una rama `feat/goals`, ~7 tasks: (1) `goals.py` extendido (campos, estados, gramatica, tope, `golpes.jsonl`,
`COMPUERTAS`) + el helper de worktree + tests; (2) `/goal` en `parse_directives` + la propuesta + `dale/no/
parar/segui/estado` en el chat + el inbox + tests por harness; (3) las manos: la invocacion headless con
herramientas y `cwd` + el hook de compuertas + `stream-json` al ledger + `web` y `leer` + la aduana con
`origen goal` + las familias del motor de permisos + tests; (4) el runner: cabeza por ruteo, pasos, golpes,
cobro, tope, carga, juez (criterio medible y revisor distinto), `waiting`, fail-open, cierre ordenado +
tests con dobles; (5) rutinas -> goals permanentes con disparador en el ticker y `catastro` migrado + tests;
(6) la pestana Goals, la `#goalBar` con sondeo, `ALCANCES` + tests node; (7) el smoke en vivo y el cierre.
