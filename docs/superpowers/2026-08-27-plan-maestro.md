# Plan maestro: qué falta, en qué orden, y por qué ese orden

**Fecha:** 2026-08-27
**Entrada:** los dos specs del 27-08 (`specs/2026-08-27-proyectos-y-plata-design.md`,
`specs/2026-08-27-ojos-y-manos-design.md`) y cinco juicios cruzados sobre ellos.
**Qué es:** el plan de arriba. No es una lista de tareas: es qué se arregla en los
specs antes de tocar código, en qué etapas se construye, y qué queda vivo después.

---

## 1. El estado real

Funciona hoy de verdad: el servidor y el chat, los chats con `project_path`
persistido (`calipso/chats.py:74-82`), el mapa de la fábrica, el bus y la mesa,
adjuntos, jobs, el runner con allowlist (`calipso/tools/commands.py:23-283`),
las rutinas, y **toda la contabilidad como código** — kernel, mercado, balances,
PT, cierre, eficiencia, escritos y testeados. Está construido pero apagado el
sistema económico entero: `~/.calipso/economia/` **no existe** (verificado hoy),
así que `Pagador.desde_entorno` (`calipso/economia/pagador.py:59-66`) devuelve
`None` y los veintiún endpoints `/api/economia/*` contestan `{"activa": false}`;
`Kernel.acunar` (`calipso/economia/kernel.py:47-58`), `Kernel.liquidar`
(`:141-158`), `LibroPersonal.registrar` (`calipso/economia/personal.py:35-49`) y
`departamentos.Registro.alta` (`calipso/economia/departamentos.py:62-81`) no
tienen un solo llamador de producción, y `trabajar` es no-op declarado
(`calipso/server.py:3853-3857`). No existe: el nexo departamento↔proyecto en el
asiento, el registro de proyectos, el catastro de repos, la sección de economía
en el prompt, los modos de permiso, la bandeja, la memoria por departamento, los
entregables de un proyecto, y **el código que crea la economía por primera vez**.
Y hay una cosa viva y peligrosa: el token de Pedro está impreso en texto plano en
`calipso/server.py:207`, en una página que `auth_guard` deja pasar sin credencial
(`:241-242`), en un servidor que escucha en `0.0.0.0:8000` (`:4235`).

---

## 2. Lo que hay que arreglar en los specs antes de construir nada

### 2.1 Errores de hecho — un spec afirma algo falso del código

Todos verificados. Ninguno necesita a Pedro salvo donde se dice.

| # | Dónde | Qué afirma | Qué pasa de verdad | Resuelve |
|---|---|---|---|---|
| **E1** | B §2 y §12.2 | *"Prender la economía. La puerta ya está escrita: `POST /api/economia/abrir`"* | Ese endpoint arranca con `desde_entorno` y devuelve `{"activa": False}` (`server.py:3681-3684`). `abrir_semana` abre una **semana** sobre un libro que ya existe; no crea ningún archivo. **Es un no-op exacto en el único estado en que haría falta.** | implementador borra la frase; la consecuencia es la Etapa 2 |
| **E2** | A §4 | *"el sistema se frena solo: `Kernel._exigir` rechaza el gasto cuando el saldo se agota"* | `SinSaldo` hereda de `OperacionInvalida` (`kernel.py:16,20`), `Pagador._cobrar` la atrapa y apila en `cargos_pendientes.jsonl` (`pagador.py:143-146`), y `_cobrar_turno` traga **toda** excepción y devuelve 0 (`server.py:4170-4175`). El cobro es el paso 4 del turno (`server.py:2495-2506`): la llamada al modelo ya ocurrió y la plata real ya salió. **La invariante 7 protege el libro, no la tarjeta.** | **Pedro** decide la política (pregunta 1); el implementador escribe el mecanismo |
| **E3** | A §3.3 | *"El presupuesto de proyecto pasa por el mandato de dirección. Mismo umbral que ya existe (`direccion.asignado_semana`)"* | `direccion.py:29` filtra `detalle["motivo"] == "presupuesto"` y la tabla de A fija el motivo en `presupuesto_proyecto`: el acumulado da siempre 0 y el umbral de 100.000 nunca dispara. Además `asignar_presupuesto` arranca con `dep_por_cuenta` (`direccion.py:36`), que revienta con `proyecto:*` (`mercado.py:44-48`). El proyecto queda siendo exactamente la puerta trasera al tesoro que A dice que no es. | implementador |
| **E4** | A §7.3.1 | *"Sin esto el mapa pinta todos los edificios iguales, `ciudad.py:177-180` toma su color de esa función"* | La clave de dibujo es `` `${e.id}|${e.zona}|${e.estado}|${e.tamano}|${e.actividad}|${esc}` `` (`web/fabrica/mapa.js:97`): `eficiencia_pormil` no aparece. Se usa en el texto de la ficha (`web/fabrica/ciudad.js:41-49`). El arreglo sigue haciendo falta, por `ficha.bloque` (`mapa/ficha.py:78-79`) y por el informe de cierre (`economia/cierre.py:213`); la urgencia está mal argumentada. | implementador |
| **E5** | A §9.2 | *"Tocar un edificio hoy solo mueve la cámara y pinta una tarjeta"* | Eso es el hover (`app.js:359-387`). El click hace `enFoco = resaltado` (`app.js:149`), y `app.js:180` dice literal *"el edificio tocado: contexto y pagador"*. `_cuenta_en_foco` (`server.py:4091-4101`) y `_ficha_y_cuenta` (`:4104-4135`) **ya separan quién paga de qué sabe Calipso**. §9.3 es un cambio de una línea sobre maquinaria terminada, no una vista nueva. A se subestima y presupuesta mal. | implementador |
| **E6** | A §10 | *"ningún pliegue puede exigir una clave nueva: todos leen con `.get()`"* | Falso como descripción: `cierre.py:120` hace `bus.datos(id)["departamento"]`, `bus.py:187,193` indexan `datos["criterio"]` y `datos["semana_financiada"]`. La regla se puede cumplir para la clave `proyecto`; la afirmación de que el repo ya la aplica no es cierta. | implementador |
| **E7** | B §3.5 | *"`pintarChats` agrupa por `project_path`, como ya hace la vieja"* | Hoy pinta lista plana (`web/fabrica/app.js:470-476`); la vieja sí agrupa (`web/index.html:2139-2148`). Escrito en presente lo que no pasa. Se cae de todos modos: la agrupación se la queda A §9.1. | implementador |
| **E8** | B §5.2 | *"los comandos de solo lectura del allowlist (`git_status`, `git_diff`, `git_log`, las suites de tests)"* | **Ninguno de esos tres ids existe** en `tools/commands.py:23`. Y "las suites de tests" en el modo `mirar` es ejecutar código del repo abierto, tres renglones después de *"nada de comando arbitrario"*. | implementador, y arrastra la decisión D9 |
| **E9** | B §1 | *"el agente corre con `cwd=str(ROOT)`... fue a leer archivos y chocó"* | `cwd` no confina nada. La invocación no lleva `--allowedTools` ni `--add-dir` ni modo de permisos (`server.py:1944-1947`) y hereda `os.environ.copy()` (`:1959`): podía leer `~/.calipso` perfectamente. La causa real es la tercera que el propio spec nombra — el directorio no existe. **§1 se contradice con S5 del mismo documento.** | implementador |
| **E10** | B §8.3.1 | *"el campo ya existe: `attachments.create` recibe `source` y el body lo acepta (`server.py:487-490`)"* | El body sí lo acepta, pero en `server.py:354-360` y `464-466`; `:487-490` es `goals.add_evidence`. Y `source` tiene claves `type`/`path` (`attachments.py:93-94`): **ningún adjunto tiene `origen`**. Sin un default, todo adjunto existente cae en "no confiable" y todo chat con un adjunto se degrada a `mirar` para siempre. | implementador (D8) |

### 2.2 Decisiones que faltan — las decide quien implemente

- **D1. Una sola sección `Economia`.** A §6 la pone entre "Meta activa" y "Estado operativo" con tesoro, tipo de cambio del PT y por-proyecto; B §4.1 entre `Repo` y `Meta activa` con saldo por departamento y `direccion`. Misma función (`prompt_compiler.py:47-72`, un solo llamador: `server.py:1829`). **Reparto: el slot, la caché por `(mtime,size)` y el texto de "apagada" son de B; el contenido es de A.** Y el número de B —"saldo por departamento"— es el que A §5.4 declara sin significado, porque un departamento de apoyo vive legítimamente en cero. Nota: `personal.tablero` **no es puro** (firma `tablero(k, registro, suscripciones, reloj, libro_personal, semana)`, `personal.py:69-70`): usar `libro_personal.resumen()` (`:51-60`).
- **D2. La agrupación de chats se la queda A §9.1** (secciones por proyecto de la fábrica, con el disponible al lado). B §3.5 se reduce a una línea que remite a A.
- **D3. `proyectos.json` y `catastro.json` no se fusionan: se parten por autoridad.** B se queda el **descubrimiento** (qué repos hay en disco, rama, último commit); A se queda el **registro** (cuál de esos tiene cuenta, presupuesto y departamentos habilitados). **El catastro nunca inventa una cuenta de proyecto.** Y el campo `departamento` del catastro se renombra: en B, `atlas` es un departamento y `Observatory-Global` el proyecto, exactamente al revés de lo que dijo Pedro. Se borra `dep:atlas` de la prueba de aceptación de B §12.2. Nota de campo: dos de los tres slugs de `~/.calipso/projects/` son worktrees del mismo repo y su `.git` es **un archivo, no un directorio**, así que el criterio *"una carpeta con `.git`"* y la lectura de `.git/HEAD` fallan ahí.
- **D4. `personal.jsonl` entra en la denylist de B S4.** Hoy no está, y vive dentro de `~/.calipso`, que B declara raíz de lectura en `mirar` (`server.py:3420,3427`). A cierra la puerta del prompt por invariante 11 y B abre la de al lado.
- **D5. `_id_carta` necesita clave de proyecto.** `operacion.py:41-43` hace `carta.get("departamento") or carta.get("suscripcion") or "general"`: sin eso, **todas** las cartas de proyecto comparten el id `cierre_proyecto:general:<semana>` y `cola.encolar_carta` es idempotente por id (`cola.py:121-122`) — entra la primera y las demás se pierden en silencio. Río abajo, `ciudad.py:184-185,256` y `situacion.py:105-106` leen `p["departamento"]`: una carta indexada por proyecto no es de nadie en los tres.
- **D6. La ruta del `dueno` por el pagador es un cambio de esquema, no un parámetro.** Para un trabajo el dueño se deriva del bus (`pagador.py:119-128`); para un proyecto viene del foco del mapa, en el momento del turno. Hay que bajarlo por `_cobrar_turno` (`server.py:4138`) → `cargar_api`/`cargar_suscripcion` (`pagador.py:148,162`) → **el dict persistido en `cargos_pendientes.jsonl`** (`:158-159,164-166`), porque `reintentar_pendientes` (`:98-116`) lo reaplica horas después, cuando el foco ya no existe. Seis firmas, tres archivos, un formato en disco. A no nombra `pagador.py` en toda su sección 9.
- **D7. `capacidades` es una etiqueta, no una compuerta.** El tipo tiene que ser tupla (`Departamento` es `frozen=True`, `departamentos.py:27-34`, y `_guardar` usa `asdict`). Y **la regla de A §5.2 —"un departamento sin capacidades declaradas no puede ser `dueno` de un gasto"— se cae**: rompe 39 construcciones de `Departamento(` en 16 archivos de test, es un candado que nadie pidió, y deja congelado a todo departamento hasta que alguien llene un campo.
- **D8. El default de `origen` en adjuntos** (ver E10), decidido antes de la mano cerrada o el sistema se autobloquea el primer día. Y **`repo` sale de la lista de orígenes confiables**: `_repo_brief` (`server.py:1746-1757`) mete 1400 caracteres de `AGENTS.md`, `CALIPSO.md`, `SPEC.md` y `README.md` de ROOT **en el system prompt**, y `AGENTS.md` es por convención el archivo que le da órdenes a un agente. Un repo recién bajado es `origen: bandeja`, no `origen: repo`.
- **D9. El piso de ejecución se blinda antes de que exista un modo que lo use.** `git` con `-c core.fsmonitor= -c diff.external= -c core.pager=cat` y `GIT_CONFIG_GLOBAL=/dev/null` — verificado en esta máquina: un `.git/config` con `fsmonitor = "touch X; false"` ejecuta al correr `git status --porcelain=v1`. Y el allowlist de `tools/commands.py` con **rutas absolutas ancladas al repo de Calipso**: 24 de sus 28 entradas son relativas (`[sys.executable, "test_ui.py"]`) y corren con `cwd=project_root` (`:280-283`), así que cualquier repo abierto con un `test_ui.py` propio convierte el comando de solo lectura en ejecución de ese archivo. `commands.run` además no pasa `env`.
- **D10. El techo de `ROOT` va en `_switch_project` (`server.py:971`), no en `project/open`.** B pone el tope en el endpoint que menos se usa de los cuatro: `ROOT` también se reasigna desde `POST /api/chats` con un `project_path` del body sin validar (`:1001-1003`), desde `activate` (`:1022`) y **en cada turno del WebSocket** (`:2228`). Un `POST /api/chats {"project_path": "/"}` envenena `chats.json` y sobrevive al reinicio.
- **D11. La allowlist de env de S6 hay que escribirla probando.** `PATH, HOME, LANG, TERM` sueltas rompen `claude` y `codex` en la práctica (`XDG_*`, `SHELL`, `TMPDIR`, `NODE_*`, proxies). Y `~/.calipso/tmp/` **no** entra como raíz de lectura de todos los modos: contiene el historial completo y los adjuntos de otros chats (`server.py:1923-1933`), con borrado best-effort. Va un subdirectorio por chat.
- **D12. Bloqueantes chicos que ningún spec toma:** el `Mercado` necesita el registro de proyectos como cuarta dependencia (`Mercado.__init__(kernel, registro, suscripciones)`) o §7.1, §7.3.2 y §7.3.3 no se pueden escribir; `situacion` (`situacion.py:55-59`) hace `registro.obtener(cuenta.split(":",1)[1])`, firma de departamento; `jefe._puede` tiene **cuatro** frenos, no tres — el cuarto es `tope = presupuesto_semanal_mm * agresividad_pct // 100` y `0 >= 0` congela igual al departamento de apoyo (`jefe.py:73-76`); y `routines.DEFAULTS` (`routines.py:39-44`) no incluye `catastro` ni `bandeja`, así que nacen deshabilitadas.

### 2.3 Decisiones que faltan — las tiene que contestar Pedro

Van completas en la sección 6. En una línea cada una: si un chat sin saldo se
corta o sigue; si "full acceso a la terminal" es de verdad los tres modos de B;
la lista de departamentos y el capital inicial; qué es un entregable; y si los
skills de terceros entran ahora. Las dos primeras cambian la arquitectura, no la
prioridad.

---

## 3. Las etapas

### Etapa 0 — La cerradura. Hoy, sin discutir con nadie.

Borrar `server.py:207` y rotar el token; redirigir siempre sin query en el camino
`?token=` (hoy solo se hace para GET de páginas, `server.py:252`); filtrar
`token=` del access log; el banner imprime el token en su propia línea, no dentro
de una URL. Cerrar `POST /api/deps/install` (`server.py:2801-2812`), que hoy hace
`pip install <arbitrario>` para cualquiera con el token — RCE directa, y B §9
dice *"instalar dependencias es un pase, siempre"* mientras el endpoint sigue
ahí sin pase. Cerrar o autenticar `GET /api/browser/screenshot` (`:2815-2822`),
que es SSRF por GET con la cookie en `SameSite=lax` (`:185-187`).

**Termina en:** Pedro puede dejar el puerto abierto sin regalar la casa.
**Trampa:** `_load_token()` prefiere `CALIPSO_TOKEN` del entorno
(`server.py:114-115`). Reescribir el archivo no rota nada si la variable está
puesta — y S6 quiere dejar de pasarla a los subprocesos, o sea que está puesta.
Y el test de regresión de B §12.7 (`curl /login | grep -f ~/.calipso/token`) pasa
trivialmente después de rotar aunque el literal viejo siga en el HTML: busca el
token nuevo. Hay que fijar el literal viejo en el test.
**Desbloquea:** nada técnicamente. Es la precondición de todo lo que sigue.

### Etapa 1 — "La economía está apagada". El primer día que Pedro ve algo.

B §4.2: un kwarg en `context_sections` (`prompt_compiler.py:47-72`), tres líneas
en `_build_context` (`server.py:1811-1834`), una `economia_brief()` de unas
cuarenta líneas con los dos caminos, y `test_economia_brief.py`.

**Por qué primero:** es el síntoma exacto que originó los dos specs —Calipso
dijo que no podía ver su economía estando adentro del proceso que la tiene— y es
**la única pieza que no depende del bootstrap que no existe**, porque su trabajo
es justamente describir esa ausencia. No toca permisos, no toca plata, no toca el
mapa.
**Termina en:** Pedro pregunta por la economía de Atlas y Calipso contesta "está
apagada, faltan `libro.jsonl`, `departamentos.json` y `suscripciones.json`" en
vez de inventar una limitación de sandbox.
**Desbloquea:** el slot `Economia` queda hecho; el contenido se llena en la 2.
**Precondición:** D1, que es una conversación de diez minutos.
**Cuidado:** `_build_context` se llama **cuatro veces por turno**
(`server.py:2325, 2355, 2422, 2463`) y **sin `asyncio.to_thread`**. Si
`economia_brief` lee bajo `_eco_candado` —un `flock(LOCK_EX)` bloqueante,
`candado.py:37-53`— cuelga el event loop detrás de un cierre semanal. El repo ya
sabe esto: `_ficha_y_cuenta` se despacha con `to_thread` (`server.py:2277`) y su
docstring dice *"se llama SIEMPRE desde un hilo"*. La caché `(mtime,size)` no
salva: el miss ocurre justo cuando alguien está escribiendo.

### Etapa 2 — El sembrado. La pieza que ningún spec escribió.

`POST /api/economia/sembrar`: crea `~/.calipso/economia/` con `libro.jsonl`
vacío, `departamentos.json` con la lista de Pedro, `suscripciones.json` con lo
que paga de verdad; y recién después admite la primera acuñación al tesoro por la
frontera de A §8.5.

**Por qué acá:** los dos specs se terminan y el sistema sigue sin poder escribir
su primer asiento. B lo declara fuera de alcance apoyándose en E1; A lo da por
hecho en §3.3, §4, §7 y §8 y esconde el hueco en su pregunta abierta 2, que
pregunta el **número** y no el mecanismo. Ningún archivo de producción escribe
esos tres archivos: los únicos que los crean son fixtures de test.
**Termina en:** `GET /api/economia/tablero` (`server.py:3464-3479`) devuelve
números, el mapa pinta edificios con saldo, y la sección de la Etapa 1 deja de
decir "apagada".
**Desbloquea: el spec A entero**, y el paso 2 de la prueba de aceptación de B.
**Depende de:** la respuesta de Pedro a la pregunta 3.
**Decisión de borde:** si `proyectos.json` entra en la lista obligatoria de
`desde_entorno` (`pagador.py:62-65`), rompe los ~20 fixtures de test que crean la
economía con tres archivos. Si no entra, `_politica` necesita un camino nulo.

### Etapa 3 — El freno. Antes de que exista un presupuesto de proyecto.

Que el saldo agotado **corte el turno** en vez de archivarlo. Hoy `SinSaldo` se
atrapa dos veces (`pagador.py:143-146`, `server.py:4170-4175`) y el cargo se
apila en `cargos_pendientes.jsonl` "para siempre: una línea por turno y sin
techo" (comentario del propio repo). Y `reintentar_pendientes`
(`pagador.py:99-116`) drena esa cola contra el siguiente saldo: la primera
recarga que haga Pedro se evapora de golpe contra semanas de gasto acumulado.

**Por qué antes de la 5 y no después:** A §3.3 decide que *"el presupuesto de un
proyecto no se recarga solo"* —el departamento tenía un goteo semanal que ponía
un piso al desastre, el proyecto no— y A §7.3.3 **saca** el freno
`disponible_mm <= 0` de `jefe._puede` (`jefe.py:61-62`) para que los
departamentos de apoyo no queden congelados. Las dos cosas juntas, sobre un cobro
que ya demostró que atrapa y sigue, convierten "un agente automático tiene
presupuesto" en "un agente automático tiene mi tarjeta". Construir la Etapa 5
antes que ésta es entregar presupuestos que no son presupuestos.
**Termina en:** Pedro abre un chat en un proyecto sin plata y ve que no responde,
con el motivo escrito.
**Depende de:** Etapa 2. Sin libro no hay saldo que agotar.
**Necesita:** la respuesta de Pedro a la pregunta 1.

### Etapa 4 — El catastro y el techo de rutas.

B §3 completo, con D3, D9 y D10. Es la mejor pieza de los dos documentos:
formato explícito, criterio de descubrimiento explícito, techo numérico
(`CATASTRO_MAX = 1200`, 20 proyectos), la trampa del symlink `/home → var/home`
nombrada, y los tests uno por uno. Un implementador arranca hoy. Le faltan dos
renglones: `routines.DEFAULTS` y el refactor de `_repo_brief`, que lee `ROOT`,
`IGNORE_DIRS` y `REPO_BRIEF_MAX` como globales — treinta líneas, no un cambio de
firma.

**Termina en:** Pedro pregunta "qué proyectos tengo" desde un chat en `calipso` y
Calipso nombra `Observatory-Global` con su rama, sin que nadie haya movido `ROOT`.
**Desbloquea:** el `repo_path` del registro de proyectos tiene contra qué
resolverse, y con eso la vista A de la Etapa 5.
**Depende de:** nada del resto. Puede correr en paralelo con la 2 y la 3.

### Etapa 5 — Proyectos: el registro, la cuenta, el nexo, las dos vistas.

A §3, §4, §7, §8.4, §8.5 y §9, con D5, D6, D7 y D12.

**Termina en:** Pedro carga presupuesto en Atlas desde la mesa, abre un chat en
la sección Atlas, toca `legal` en el mapa, y el asiento dice
`origen: proyecto:atlas`, `dueno: dep:legal`. Es literal *"gastan los
departamentos y reportan para qué proyecto están gastando"*. Y el disponible de
Atlas baja a la vista, en la lista de chats donde él ya está mirando.
**Desbloquea:** la eficiencia por departamento, la carta de cierre de proyecto,
la vista B de la mesa.
**Depende de:** 2 (el libro), 3 (el freno), 4 (el `repo_path`).
**Es la etapa grande, y A la subestima en dos lugares.** El `dueno` tiene que
bajar hasta el archivo persistido (D6). Y la eficiencia no se arregla con
plegar el denominador por `dueno`: el numerador sigue en cero, porque
`eficiencia_departamento` (`eficiencia.py:104-115`) cuenta ventas vía
`ventas_por_trabajo`, que exige `a.detalle.get("trabajo")` (`:15-24`), y A §8.5
hace esa clave opcional. Una venta de proyecto sin trabajo no le atribuye
eficiencia a nadie, que es exactamente el síntoma que §7.3.1 dice arreglar.
Falta el pliegue venta→proyecto→departamentos **y la regla de reparto**: si Atlas
vende y tiene cinco departamentos habilitados, ¿cómo se divide? Eso no es una
línea, es una decisión de atribución. Y hay un doble conteo esperando: si
`costo_api_directo` pliega por `dueno` sin excluir `origen` que empieza con
`trabajo:`, el mismo asiento se cuenta dos veces.
**Y una cosa que la tabla de ciclo de vida no cubre:** `Kernel.liquidar`
(`kernel.py:141-158`) no ve la plata que el proyecto puso en un `trabajo:<id>`
vivo — está en la cuenta del trabajo (`bus.py:133-134`) — y
`evaluar_y_liquidar_muertos` (`bus.py:224-228`) la va a devolver semanas después
a una cuenta ya cerrada. Cerrar un proyecto exige matar o reasignar sus trabajos
primero.

### Etapa 6 — Las manos.

B §5 y §6, en la versión que Pedro elija (pregunta 2), con D8, D9, D11.

**Depende de:** Etapa 0, y de una prueba en la máquina. `--allowedTools`
**agrega** a la allowlist, no la reemplaza; los settings files siguen aplicando
además de las banderas; una regla `deny` sobre `Read` no cubre `Bash` (`cat
~/.ssh/id_rsa` es Bash); y el repo que se abre trae su propio
`.claude/settings.json`, que está en la jerarquía que el CLI lee. **No aceptar la
bandera por su nombre:** el criterio de salida de esta etapa es un test que
intente leer `~/.ssh/id_rsa` desde el agente contratado y falle. Si ese test no
se puede escribir, la sección 5 de B es una UI y hay que decirlo.
**Y una decisión de producto antes de tocar nada:** `_subscription_invocation`
no es "el agente contratado", es el chat de Pedro — llamadores en `server.py:597,
1497, 1523, 1654, 2372, 2427, 3163`. Poner `--allowedTools` ahí cambia lo que
Calipso puede hacer contestándole a Pedro. (Y existe `_run_subscription_text_live`
en `:2001-2006`, la versión streaming, que B nunca nombra.)
**Termina en:** Pedro dice "corré los tests de Atlas" y pasa.

### Etapa 7 — Lo diferido, en este orden

Memoria por departamento (`inventario-abierto.md`, items 17 y 44); entregables y
objetivo del proyecto; la frontera de salida (publicar); skills de terceros; el
navegador. Ninguno bloquea nada de lo anterior.

---

## 4. Lo primero que haría mañana

Un día. Tres cosas, en este orden.

1. **Etapa 0, la parte de veinte minutos:** borrar `calipso/server.py:207`, rotar
   `~/.calipso/token`, y **antes** chequear que `CALIPSO_TOKEN` no esté en el
   entorno del proceso (`server.py:114-115`) o la rotación no rota nada.
2. **Cerrar `POST /api/deps/install`** (`server.py:2801-2812`). Diez minutos, y
   es `pip install` arbitrario para cualquiera con el token.
3. **`economia_brief()` con el camino "apagada"** y el slot en
   `context_sections`, despachado con `asyncio.to_thread`, más
   `test_economia_brief.py`. Medio día.

Al final del día Pedro le pregunta a Calipso por la economía y Calipso contesta
la verdad. Eso es lo que motivó los dos specs.

---

## 5. Riesgos que quedan vivos después de todo el plan

- **El aprobador y el atacante son el mismo principal.** `_valid` es un
  `compare_digest` contra un único token global (`server.py:128-129`): no hay
  sujeto, no hay segundo canal, no hay diferencia criptográfica entre "Pedro
  aprueba un pase" y "cualquier cosa que tenga el token aprueba un pase". B §5.3
  dice *"la escalada es de Pedro, siempre"* y eso es falso en la implementación.
  **Mientras no exista un canal de aprobación fuera de banda, todo el modelo de
  permisos es una UI.** Y la Etapa 5 agrega encima el endpoint que acuña plata de
  la nada, cuya evidencia es esa misma firma.
- **La denylist no tiene jurisdicción sobre lo que necesita frenar.** `_safe`
  (`server.py:295-300`) es una función Python del servidor; el agente es `claude
  -p` corriendo como Pedro. Ninguna bandera del CLI acepta una denylist de rutas.
  Es un blocklist donde hacía falta un allowlist, con el default invertido —la
  raíz por defecto es el home entero a profundidad 3— y su lista de siete rutas
  no incluye `~/.claude.json`, `~/.codex/`, `~/.netrc`, `~/.npmrc`,
  `~/.git-credentials`, `~/.docker/config.json`, `~/.config/gcloud`,
  `~/.kube/config`, los perfiles del navegador, ni `~/.calipso/economia/personal.jsonl`.
- **El modo `mirar`, que es el default, ejecuta código.** `git status` sobre un
  repo bajado dispara `core.fsmonitor` del `.git/config` que vino en el zip
  (confirmado en esta máquina, git 2.53), y el allowlist de comandos son rutas
  relativas corridas con `cwd=ROOT`. La mano cerrada de B §8.3.2 degrada a un
  modo que corre binarios del repo hostil.
- **La rutina `departamento` corre cada 60 segundos sin chat**
  (`server.py:3367-3382` → `:2605-2638`), despierta al jefe, y el jefe llama a un
  modelo. Los modos de B viven por chat y los pases mueren con el chat: **el
  único camino de gasto desatendido que existe queda fuera del modelo de
  permisos entero.** Sus frenos son otros —`interruptor.Estado(modo="ensayo")`,
  `techo_tics=200`, `TECHO_PROPUESTAS=3`— y ningún spec los nombra.
- **El canal web inyecta al system prompt y ninguna mitigación lo toca.**
  `web.context_block` (`web.py:88-98`) arma texto de un tercero sin marca de
  procedencia y lo cierra con *"Usa esta información para responder"*; se
  concatena al system en `server.py:2345` y `:2361`, y se dispara solo con pegar
  una URL (`dispatch.py:172`). La mitigación de B vive en `attachments.py`, por
  donde el camino web nunca pasa: `test_no_confiable.py` va a pasar y el canal
  que ya lee internet sigue igual.
- **Los títulos del bus son inyección modelo-a-modelo persistente.**
  `_contratar_para` (`server.py:3878-3888`) escribe como `titulo` la salida de un
  modelo; `situacion` lo lee (`situacion.py:77`) y `dec.prompt` lo interpola
  verbatim en el prompt de **todos** los demás jefes (`decision.py:41-48`).
  Sobrevive al reinicio, y es lo mismo que Pedro lee en la mesa para decidir si
  financia. Ningún marco de "no confiable" lo cubre.
- **El control presupuestario es opt-in del que llama.** El pagador sale de
  `chats.project_path`, que el cliente elige libremente en `POST /api/chats`
  (`server.py:1001`), y `_cobrar_turno` devuelve 0 para `personal`
  (`server.py:4150-4151`). Un chat con un `project_path` que no cae bajo ningún
  `repo_path` gasta invisible para el libro de la fábrica.
- **El neto bancario de Pedro viaja a Anthropic / DeepSeek / OpenAI** en cada
  turno de un chat de zona personal (A §6), y la zona la determina el
  `departamento` del paquete del WebSocket (`server.py:4091-4101`): **el cliente
  elige si ese dato viaja.** La invariante 11 queda respetada en la letra.
- **El marco `<<< >>>` es rompible y el header de adjunto es falsificable.** Sin
  nonce por turno, un documento que contenga una línea `>>>` sale del marco; y
  `safe_name` (`attachments.py:72`) saca directorios pero no saltos de línea, y
  el nombre se interpola en el header (`:322-325`).
- **TOTP sin límite de intentos** (`server.py:152-161`, `valid_window=1`): tres
  códigos válidos por ventana de 30s, sin lockout ni backoff.
- **Todo número de gasto por modelo que no sea `deepseek-chat` es inventado.**
  `PRECIOS_API_MM_POR_MTOK` tiene un solo modelo (`pagador.py:28`); el resto cae
  en `PRECIO_DESCONOCIDO`. A §8.2 lo menciona y no lo resuelve.
- **`timeout=None`** en `_run_subscription_text` (`server.py:1990`): un agente
  colgado se queda para siempre.

---

## 6. Preguntas abiertas, ordenadas por cuánto cambian el trabajo

1. **Cuando un proyecto se queda sin plata, ¿el chat se corta o sigue?** Si se
   corta, el cobro tiene que pasar a ser una **reserva antes** de llamar al
   modelo, no un asiento después (`server.py:2495-2506`), y eso es un rediseño
   del turno. Si sigue, "presupuesto" es una etiqueta y hay que sacar la frase
   *"el sistema se frena solo"* de A §4. No hay tercera opción: hoy sigue, gasta
   dólares reales, y acumula cargos sin techo.
2. **"Full acceso a mi terminal": ¿es de verdad los tres modos de B?** B entrega
   lo contrario de lo que dice esa frase —default solo lectura, pase de quince
   minutos, mano cerrada— movido por una revisión de seguridad que vos pediste
   **aparte**. Lo natural era: darte la terminal, y proponerte el candado en la
   nota aparte para que decidas. Si querés la llave por default, la Etapa 6
   cambia de forma; si querés los modos, se queda como está.
3. **La lista de departamentos del arranque y cuánto capital entra al tesoro.**
   Nombraste cerebro/dirección, market research, legal, I&D, y para Atlas
   publicar, testing, marketing, research, development. Dos cosas concretas: ¿
   "market research" y "research" son uno o dos? ¿"publicar" es un departamento
   o es la frontera de salida? Y el número del primer capital, más la regla: vos
   dijiste que el tesoro es donde va el banco con tus ingresos y egresos, así que
   la pregunta real es si el neto del banco acuña, si hay un tope semanal, o si
   es un acto manual cada vez. **Sin esto la Etapa 2 no corre.**
4. **¿Qué es un entregable de un proyecto?** Dijiste *"un proyecto con
   entregables y demás"*. A lo nombra una vez en la definición y su JSON no tiene
   ni `objetivo`, ni fecha de cierre, ni entregables: un proyecto en A es una
   billetera con nombre de carpeta. Y **no hay ninguna pantalla donde mirar un
   proyecto** — se lo ve como encabezado de una sección de chats y como fila
   adentro de la mesa de un departamento. Tu primera idea, "un departamento de
   proyectos", se cayó sin una línea. ¿"Cómo va Atlas?" tiene que tener pantalla?
5. **¿Los skills de terceros entran ahora?** A dice *"decidido: se cargan por
   archivo"*; B dice *"no se abre esa puerta hasta que la sección 8 esté
   construida y verificada"*. Un spec decide lo que el otro veta, en silencio.
   No lo pediste en esta conversación; la propuesta es sacarlo de los dos y que
   sea un tercer documento.

---

## Bitacora de ejecucion

**2026-08-27.**

- **Etapa 0, la parte urgente: hecha.** El token estaba hardcodeado en la pagina de /login, que es la unica ruta que auth_guard deja pasar sin autenticar: cualquiera que alcanzara el puerto se llevaba la credencial pidiendo /login. Verificado contra el server corriendo antes de tocar nada. Sacado, rotado, y el viejo da 401 (commit 4eba4eb). El mismo literal estaba en test_chat_live.py, que esta en git, y en un spec: los tres limpiados.
- **Etapa 0, las otras dos puertas: hechas.** POST /api/deps/install corria pip install de un paquete arbitrario — ejecucion de codigo remota para cualquiera con el token — y no tenia un solo llamador en la UI: la rama cerrada con 403, queda el catalogo cerrado de deps.TOOLS. GET /api/browser/screenshot visitaba cualquier URL por GET con la cookie en SameSite=lax: ahora browser.exigir_url_publica rechaza esquemas que no sean http/https y todo lo que resuelva a loopback, privada, link-local, reservada o multicast, incluido 169.254.169.254. La defensa vive en el modulo, no solo en el endpoint. Tests en test_seguridad_puertas.py (commit cd1f3dc).
- **Los dos specs corregidos con las respuestas de Pedro** (commits 8f07b41 y b1ebe2a). La politica de saldo agotado quedo decidida: la suscripcion es costo hundido y sigue, la API es plata que se pierde y encola una carta que Pedro ve en la barra de avisos. El modelo de permisos se dio vuelta: capaz por defecto con permiso pedido al momento, que es lo que Pedro habia pedido y el spec habia invertido.
- **Etapa 1: hecha** (commit 0df0d6f). Verificada de punta a punta con un turno de chat real: se le pregunto lo mismo que habia fallado y contesto que la economia no esta sembrada, nombrando los tres archivos que faltan, en vez de inventar una limitacion de sandbox. Los cuatro llamadores de _build_context pasaron a despacharse con asyncio.to_thread, que era la trampa que el plan marcaba.
- **Hallazgo nuevo, que no estaba en ningun spec: nadie dispara el cierre semanal.** cerrar_semana_operativa es el latido de toda la economia —expira los PT, manda las cartas de cierre, liquida los trabajos muertos, renueva la capacidad y reintenta los cargos pendientes— y solo corre detras de POST /api/economia/cierre, que no tiene llamador ni en la UI, ni en routines.KINDS, ni en cron, ni en un timer. Anotado en el spec A, seccion 11, sin resolver: quien lo dispara es una decision de diseno de Pedro.
- **Correccion de un error mio:** le pase al que corrigio el spec B, como error de hecho de la corte, que git_status, git_diff y git_log no existian en el allowlist de tools/commands.py. Existen, en las lineas 220, 226 y 238. La corte lo marco mal y yo lo repeti sin verificar; el implementador fue a mirar el archivo y no lo aplico.
