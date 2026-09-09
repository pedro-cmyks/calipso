# Calipso - guia para agentes (handoff)

> **Que es Calipso:** el asistente personal multi-modelo de Pedro (tipo "Jarvis"),
> con interfaz web (editor de codigo + chat), memoria que evoluciona, navegador real,
> modo de planificacion, agentes dinamicos y un orquestador que enruta cada peticion
> a la boca/modelo mas adecuado.
>
> **Idioma:** Pedro escribe en espanol. Responde en espanol.
> **Estado:** funcional de punta a punta. **El estado VIVO del proyecto (que hace, que esta apagado,
> que falta, decisiones pendientes de Pedro y como seguir) esta en
> `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md`; leerlo antes que esta guia,
> que quedo desactualizada (no cubre economia, plantel, mapa, abismo, privacidad, compositor ni sesiones).**

## Estado actual, en corto

- Git estaba limpio en el ultimo handoff revisado, pero el checkout actual ya
  contiene cambios sin commit. No asumir que `git status` esta limpio; revisar
  antes de editar, commitear o comparar.
- Ultimo checkpoint conocido: `0577e70 Apply Tech Innovation theme to the UI`.
- TOTP, agentes dinamicos, Planning Mode, navegador real y preview web visual ya
  existen. No los trates como "proxima tarea".
- Calipso ahora distingue plan automatico vs plan revisable: si la tarea lo
  amerita, planifica y ejecuta; si Pedro usa `/plan`/`/team`, muestra el plan y
  espera aprobacion o ajustes.
- Los agentes dinamicos tienen skills internos (`calipso/skills.py`): planner,
  researcher, coder, reviewer, writer, librarian, verifier y synthesizer.
- `LIBRARY.md` define la biblioteca/memoria: que vive en `CALIPSO.md`, que vive
  en `AGENTS.md`, que va al core global/proyecto y que queda como episodio.
- `SPEC.md` define la experiencia objetivo: usar Calipso como conversacion
  natural de desarrollo, con archivos, investigacion, iteracion, verificacion y
  recomendaciones de lanzamiento. Incluye Goal Mode: metas persistentes con
  criterios de listo, subtareas, evidencia, bloqueos y Goal Bar.
- `RUNBOOK.md` explica como prender Calipso si `localhost` esta caido. El objetivo
  de producto es que Pedro use un lanzador/app, no que recuerde comandos.
- La siguiente prioridad recomendada es endurecer/verificar producto real y luego
  elegir el siguiente bloque grande: rutinas/timers/inbox, multi-PC federado,
  PWA/Tailscale o quota-aware real.

## Estado operativo de esta sesion

- Repo local: `C:\Users\Pedro\Desktop\proycto`, rama `main`.
- Remoto Git local: no hay `origin` configurado en este checkout.
- `gh` no esta instalado o no esta en `PATH` en esta sesion.
- Conector GitHub de Codex: conectado a la cuenta `pedro-cmyks`, instalacion
  `131780634`.
- Repos visibles por el conector GitHub:
  - `pedro-cmyks/noaa-proyecto` (privado, `main`)
  - `pedro-cmyks/Observatory-Global` (publico, `v3-intel-layer`)
  - `pedro-cmyks/AvesCO` (privado, `master`)
  - `pedro-cmyks/cam-crm-vincere-demo` (privado, `main`)
- En esta sesion `python` si esta disponible en `PATH` y se uso para validar
  pruebas locales.

## Lo construido

- **Ruteo a nivel de MODELO** (`calipso/capabilities.py`): cada modelo declara tier
  (small/mid/frontier/apex), persona, costo y afinidad por tarea. `choose(features,
  effort)` puntua afinidad, costo, tier, cuota e intensidad. Suscripcion > API paga.
  No es un gate que prueba en orden.
- **Intensidad ("ultrathink")**: fast/balanced/think/ultra. Slash soportados:
  `/fast`, `/think`, `/ultrathink`, `/model`, `/local`, `/claude`, `/codex`,
  `/plan`, `/team`, `/web`, `/help`.
- **Features** (`dispatch.extract_features`): `{type, complexity, private,
  needs_repo}`.
- **Memoria** (`calipso/memory.py`): hibrida, markdown core + Chroma episodica,
  jerarquica global/proyecto, embeddings multilingues `bge-m3`, `reflect()`.
- **Biblioteca** (`LIBRARY.md`): mapa de memoria y literatura. Define el rol del
  bibliotecario: clasificar, promover y evitar mezclar identidad, handoff, core,
  episodios y telemetria.
- **Perfil global de Pedro** (`~/.calipso/global/core/pedro-perfil.md`): seed
  importado desde memorias previas. Es contexto evolutivo para estilo, proyectos
  e identidad, no regla rigida ni cronologia completa.
- **Cronologia personal de Pedro** (`~/.calipso/global/core/pedro-cronologia.md`):
  linea de tiempo curada para cambios fechados, etapas actuales y proyectos en
  primer plano. La UI la muestra desde `/api/memory/chronology`; nuevas entradas
  entran como propuestas al bibliotecario, no como escritura directa.
- **Contexto presupuestado**: cache-friendly, just-in-time, alrededor de 5 KB por
  turno.
- **Lenguaje interno / Prompt Compiler** (`calipso/prompt_compiler.py`): compila
  sistema, constitucion, memoria nucleo, contrato interno, recuerdos relevantes,
  repo, meta activa y estado operativo antes de llamar modelos. Tambien genera
  `agent_brief()` para que cada agente dinamico reciba pedido original, subtarea,
  permisos y evidencia esperada. Regla clave: la memoria de Pedro es contexto
  editable, no verdad absoluta.
- **Aprendizaje** (`calipso/learning.py`): telemetria ajusta pesos por modelo,
  global y por repo. Endpoint `POST /api/learn`.
- **Sesiones** (`calipso/sessions.py`): cada sesion tiene su elenco de agentes
  configurable. Por agente: nombre, intensidad y enabled. Panel en la UI.
- **Descubrimiento + updates** (`calipso/discovery.py`): detecta modelos vivos
  (Ollama/LiteLLM), avisa updates de CLIs/npm/modelos. Endpoints `/api/discover`,
  `/api/updates`.
- **Steering**: el WebSocket escucha mientras responde; escribir mientras responde
  interrumpe o redirige el turno. `/stop` detiene. UI: boton Detener + frases de
  pensando.
- **Navegacion web** (`calipso/web.py`): busca con DuckDuckGo HTML, fetch legible,
  grounding en chat y eventos al panel Web.
- **Navegador real** (`calipso/browser.py`): Playwright/Chromium para screenshot y
  render de paginas con JS. Si el paquete existe pero falta el binario de Chromium,
  instala el navegador y reintenta una vez. `calipso/deps.py` instala dependencias
  bajo demanda y `/api/deps` verifica tambien el binario real.
- **Preview Web visual**: el panel Web muestra screenshots reales servidos por
  `/api/browser/screenshot`, no solo texto.
- **Agentes dinamicos** (`calipso/orchestrator.py`): Calipso descompone peticiones
  complejas, crea equipo de 1 a 3 agentes por subtarea, asigna modelo/persona/
  intensidad, ejecuta y sintetiza.
- **Skills internos** (`calipso/skills.py`): rutinas especializadas que se pegan
  a cada agente como musculos de trabajo: planificar, investigar, editar codigo,
  revisar, verificar, redactar, bibliotecario y sintetizar. Endpoint
  `/api/skills`; visibles en el panel de Sesion.
- **Planning Mode**: con `/plan` o `/team`, Calipso propone un plan/todo-list
  visible, espera aprobacion o ajustes y despues ejecuta.
- **Auto-plan**: sin slash, si `_should_orchestrate()` detecta complejidad, repo,
  codigo, analisis o subtareas multiples, Calipso muestra el plan como telemetria
  y ejecuta sin pedir `ok`.
- **UI** (`calipso/web/index.html`): explorador, Monaco, chat, paneles
  redimensionables, historial de chats por proyecto, proyecto activo, Git/work
  sidebar, sesiones, web preview, planning cards y tema Tech Innovation.
- **Jobs persistentes v0** (`calipso/jobs.py`): procesos largos registran job,
  eventos, estado y artifacts en `~/.calipso/projects/<slug>/jobs`. Endpoints
  `/api/jobs`, `/api/jobs/{job_id}` y
  `/api/jobs/{job_id}/artifacts/{name}`; el panel Trabajo puede listar jobs
  recientes y abrir su detalle/evidencia.
- **Goal Mode minimo** (`calipso/goals.py`): detecta lenguaje natural tipo
  `meta: ...`, crea meta persistente con criterios/subtareas/evidencia, mantiene
  meta activa por proyecto y la muestra en Goal Bar. Endpoints `/api/goals`,
  `/api/goals/{goal_id}`, `/api/goals/{goal_id}/evidence`,
  `/api/goals/{goal_id}/criteria/{criterion_id}` y
  `/api/goals/{goal_id}/subtasks/{subtask_id}`. La Goal Bar permite registrar
  evidencia, bloquear, completar o cancelar; el detalle permite marcar criterios.
  Los jobs de suscripcion se asocian a la meta activa como evidencia.
- **Developer Loop minimo** (`calipso/developer.py`): endpoint
  `/api/goals/{goal_id}/advance` convierte la siguiente subtarea pendiente en un
  job persistente `goal_step`, genera artifact `next-action.md`, marca subtarea
  como `doing` y agrega evidencia `next_action` a la meta. La Goal Bar tiene
  boton `Avanzar` y el panel Trabajo muestra el job.
- **Runner allowlist** (`calipso/tools/commands.py`): endpoints `/api/commands`
  y `/api/commands/run` ejecutan solo comandos registrados, sin shell libre. Cada
  ejecucion crea job `command`, artifacts `stdout.txt`, `stderr.txt`,
  `result.json` y evidencia `command` en la meta activa. La Goal Bar tiene boton
  `Verificar` que corre una verificacion segura.
- **Verificacion fuerte v0** (`calipso/verification.py`): endpoints
  `/api/verify/recommend` y `/api/verify/run` clasifican archivos cambiados o
  propuestas, recomiendan comandos allowlist y ejecutan un job
  `verification_plan` con artifacts `verification-report.json` y
  `verification-report.md`. La Goal Bar usa este plan automatico. Cambios en docs
  suman el comando `docs_links` (`calipso/doclinks.py` + `check_doc_links.py`) que
  valida que las referencias internas citadas existan. Falta screenshot browser
  automatico por tipo de cambio visual.
- **Bibliotecario activo v0** (`calipso/librarian.py`): endpoints
  `/api/memory/inbox`, `/api/memory/inbox/proposals`,
  `/api/memory/inbox/proposals/{id}/accept|discard` guardan propuestas editables
  de memoria, registran eventos aceptar/descartar y promueven al core markdown
  global/proyecto solo al aceptar. `/api/memory/core` expone una lectura segura
  del core global/proyecto y la UI muestra `pedro-perfil.md` en el panel
  `Memoria`, con boton para preparar propuestas al target correcto.
  `/api/memory/chronology` expone `pedro-cronologia.md` y la UI permite preparar
  eventos fechados hacia ese archivo. Falta sugerencias automaticas desde
  sesiones completas.
- **Conectores/cuotas v0** (`calipso/connectors.py`): normaliza health de
  Claude/Codex/Ollama/LiteLLM, presupuesto mensual de API, bloqueo automatico de
  API al agotar budget y bloqueo manual de suscripciones. Endpoints
  `/api/harness/status` y `/api/connectors/health` exponen estado y resumen de
  ruteo. La UI permite editar budget API y bloquear Claude/Codex. La cuota exacta
  de suscripciones queda como desconocida si el proveedor no la expone.
- **GitHub remoto v0** (`calipso/github.py`): envuelve `gh` con runner inyectable
  y expone usuario autenticado, repos recientes, issues/PRs asignados y overview
  del repo actual (remoto + branch + PRs abiertos). Endpoints `/api/github/overview`,
  `/api/github/repos`, `/api/github/assigned`, `/api/github/contribute/plan` (planifica
  sin ejecutar) y `/api/github/contribute/run` (ejecuta solo con `confirm:true`).
  Calipso nunca pushea/forkea/abre PR solo: `run` sin `confirm` da 403. La UI tiene
  bloque GitHub en el panel Config y degrada si `gh` falta o no hay login.
- **Propuestas supervisadas** (`/api/proposals`): aplicar una propuesta crea job
  `proposal_apply`, artifacts `proposal.diff` y `applied-content.txt`, y
  evidencia `proposal` en la meta activa. La UI tiene `Aplicar` y
  `Aplicar + verificar` en el panel Cambios.
- **Adjuntos v0** (`calipso/attachments.py`): endpoints `/api/attachments` y
  `/api/attachments/{id}` guardan archivos de texto por proyecto, crean job
  `attachment`, artifact con el contenido y evidencia `attachment` en la meta
  activa. El boton `+` del chat sube archivos y los manda como contexto del
  siguiente mensaje. La UI tambien puede adjuntar la seleccion del editor o el
  archivo abierto como `editable`, guardando `source.path` y rango de seleccion.
  Las imagenes suben como base64/binario, quedan como artifact y se referencian
  como no textuales en el contexto. Carpeta/proyecto v0 usa
  `/api/attachments/folder`: crea un bundle textual presupuestado con manifiesto,
  archivos incluidos y omitidos. Falta vision multimodal real y que el agente use
  permisos editables completos.
- **Artifacts de respuesta v0** (`calipso/web/index.html`): las respuestas de
  Calipso tienen boton de copiar y, si son largas o contienen bloque de codigo,
  muestran una tarjeta `Artifact` con abrir/cerrar y copiar. Falta persistir esos
  artifacts conversacionales como recursos descargables/URL propia.
- **Seguridad** (`calipso/server.py`): token de recuperacion + TOTP compatible con
  autenticadores.
- **Arranque tipo app**: `launch_calipso.py`, `Calipso.bat` y `Calipso.ps1`
  prenden el servidor local y abren el navegador. PWA basica con manifest/service
  worker en `calipso/web/`.
- **Launch personal v0** (`/api/launch/checklist`): checklist humano de salud para
  uso diario: servidor, proyecto activo, token, TOTP, PWA, navegador real,
  lanzadores, modelos disponibles y budget API. Visible en el panel Config.
- **Rutinas/timers v0** (`calipso/routines.py` + `calipso/backup.py`): rutinas
  programables (reflect/learn/backup) persistidas en `CALIPSO_HOME/routines.json`.
  Un ticker en el startup del server corre las vencidas mientras este vivo (no
  abre red ni escala a API). Endpoints `/api/routines` (CRUD), `/api/routines/{id}/run`
  y `/api/backup`. Panel `Rutinas` en Config con encender/apagar, correr ahora y
  `Backup ahora`. Backup zipea el runtime curado y excluye caches pesados.

## Seguridad actual

La autoridad es el spec de la capa de sesion,
`docs/superpowers/specs/2026-09-07-capa-de-sesion-design.md`; esto es el resumen.

- **Hay DOS credenciales, no una.** La cookie `calipso_token` (httponly,
  `samesite=lax`) vale el TOKEN y vale SOLO desde loopback: la Ally y el shell
  Tauri. Un remoto que la presente cobra 401 y ademas se le expira la cookie.
  Lo mismo `?token=`: desde afuera no entra a ningun lado.
- **Desde afuera se entra por una sesion de aparato:** cookie `calipso_sesion`
  (httponly, `samesite=lax`, 30 dias) con un `tipo` -- `lector`, `tablero` o
  `navegador` -- y alcance FAIL-CLOSED (`calipso/sesiones.py`, tabla `ALCANCES`):
  lo que no matchea es 403, en http y en websockets. El `tablero` ve `/fabrica` y
  firma mesa y permisos, jamas archivos, comandos ni config.
- **El alta es "golpear la puerta":** `POST /api/aparatos/golpear`, `.../estado` y
  `.../canjear` entran sin credencial (un aparato que todavia no existe no tiene
  ninguna) y pagan con freno propio, con baldes separados de los del login. Quien
  aprueba es Pedro y SOLO desde loopback, en la sub-pestana `Aparatos` de
  `/fabrica`; el tipo lo elige el que aprueba, el golpe solo lo sugiere. La cookie
  se entrega una unica vez, al canjear.
- **Revocar** desde `/fabrica` (loopback o sesion `navegador`) corta ademas los
  websockets vivos de ese aparato, sin esperar a que hable.
- `/login`: pide codigo TOTP de 6 digitos. Desde loopback planta el token como
  siempre; desde afuera crea una sesion `navegador` viva -- el token JAMAS viaja a
  un aparato remoto. Es la unica excepcion a "el aparato no se aprueba solo",
  porque un codigo del autenticador es Pedro en persona.
- Token de recuperacion: `~/.calipso/token`, o `CALIPSO_TOKEN`.
- TOTP: secreto en `~/.calipso/totp_secret`.
- `/setup`: muestra QR/URI la primera vez, y SOLO desde loopback con `?token=`
  valido y mientras el secreto no exista (servirlo es CREARLO, y una sesion remota
  se llevaba el segundo factor). Con el secreto ya escrito no muestra nada.
- `sesiones.json` guarda HASHES del id (el id en claro solo vive en la cookie del
  aparato), nace 0600, no se respalda y esta bajo el NUNCA del motor de permisos
  (`calipso/permisos/acciones.py`, `es_credencial_del_servidor`). Ilegible = se
  renombra y se avisa, jamas se pisa.
- El servidor se ata a `127.0.0.1` por defecto (`_host()` en `calipso/server.py`;
  el default se cerro el 2026-08-31). Abrirlo hay que pedirlo con `CALIPSO_HOST`,
  y para remoto seguro solo a la IP de Tailscale. Nunca abrir el puerto a internet.

## Verificado

Pruebas locales verdes en el ultimo chequeo historico:

```bash
python test_streaming.py
python test_capabilities.py
python test_orchestrator.py
python test_skills.py
python test_jobs.py
python test_goals.py
python test_developer.py
python test_commands.py
python test_verification.py
python test_librarian.py
python test_connectors.py
python test_launch.py
python test_prompt_compiler.py
python test_proposals.py
python test_attachments.py
python test_sessions.py
python test_learning.py
```

Notas de verificacion historica:

- Streaming SSE/NDJSON verificado con mocks.
- Ruteo por modelo + intensidad verificado en `test_capabilities.py`.
- Orquestador dinamico verificado en `test_orchestrator.py`.
- Skills internos verificados en `test_skills.py`.
- Jobs persistentes verificados en `test_jobs.py`.
- Goal Mode minimo verificado en `test_goals.py`.
- Developer Loop minimo verificado en `test_developer.py`.
- Runner allowlist verificado en `test_commands.py`.
- Verificacion fuerte v0 verificada en `test_verification.py`.
- Bibliotecario activo v0 verificado en `test_librarian.py`.
- Conectores/cuotas v0 verificados en `test_connectors.py`.
- Launch personal v0 verificado en `test_launch.py`.
- Lenguaje interno/prompt compiler verificado en `test_prompt_compiler.py`.
- GitHub remoto v0 verificado en `test_github.py`.
- Rutinas/timers v0 y backup verificados en `test_routines.py`.
- Validador de links/rutas de docs verificado en `test_doclinks.py`.
- Propuestas supervisadas verificadas en `test_proposals.py`.
- Adjuntos v0 verificados en `test_attachments.py`.
- Sesiones/rosters verificados en `test_sessions.py`.
- Aprendizaje/overrides por repo verificados en `test_learning.py`.
- Playwright/Chromium fue instalado y probado con screenshots reales.
- El estado de `/api/deps` fue endurecido: browser solo aparece ready si Chromium
  existe, no solo si el paquete Python importa.
- El panel Web fue probado mostrando un screenshot real de `example.com`.
- Planning Mode fue probado por WebSocket: propone plan, espera `ok`, aprueba,
  arranca equipo y marca tareas.

La linea `[error] test fallo: kaboom` al final de `test_streaming.py` es esperada:
ese test simula una excepcion y aun asi termina con exit code 0.

Nota de sesion: `python` estuvo disponible y se usó para repetir pruebas locales
del incremento actual.

## Arranque rapido

```bash
python calipso/server.py
```

Abrir (SIN token en la URL -- revision de seguridad 2026-09-07: con
?token= la credencial quedaba en historial del navegador y logs):

```text
http://localhost:8000/
```

La primera vez en un navegador se entra por /login con el codigo TOTP y la
cookie queda. El ?token= sigue existiendo SOLO como recuperacion manual
(p.ej. TOTP roto), a sabiendas de que deja rastro.

Luego, para TOTP:

1. Entrar con el token de recuperacion.
2. Abrir `/setup?token=<el token>` desde la propia maquina: mientras el secreto
   no exista, esa ventana es la unica puerta (la cookie sola no alcanza, porque
   loopback no prueba que sea Pedro).
3. Escanear el QR con Microsoft Authenticator, Google Authenticator o similar.
4. Desde entonces usar `/login` con el codigo de 6 digitos.

## Arquitectura

```text
Navegador (PC / iPhone futuro)
   |
   | HTTP + WebSocket + cookie
   v
calipso/server.py
   |- UI web: calipso/web/index.html
   |- API archivos: /api/tree, /api/file, /api/proposal*
   |- chat: /ws/chat
   |- memoria: /api/memory, /api/reflect
   |- costos: /api/costs
   |- sesiones: /api/session*
   |- discovery/updates: /api/discover, /api/updates
   |- deps/browser: /api/deps*, /api/browser/screenshot
   |- launch: /api/launch/checklist
   |- seguridad: /setup, /login, token + TOTP
   |
   |- dispatch.py              router multi-modelo
   |- calipso/capabilities.py  registro y scoring de modelos
   |- calipso/connectors.py    health, limites y disponibilidad de backends
   |- calipso/orchestrator.py  agentes dinamicos
   |- calipso/memory.py        memoria hibrida
   |- calipso/costs.py         tracker de gastos
   |- calipso/telemetry.py     ledger operativo
   |- calipso/learning.py      ajuste de pesos
   |- calipso/web.py           busqueda/fetch/grounding
   |- calipso/browser.py       Playwright real
   `- calipso/deps.py          instalacion bajo demanda
```

## El cerebro: `dispatch.py`

Router hibrido: reglas + clasificador local si las reglas no deciden.

Rutas:

- **subscription**: lanza `claude`/`codex` como subprocess. Critico: borra
  `ANTHROPIC_API_KEY` y `ANTHROPIC_AUTH_TOKEN` del entorno para usar suscripcion
  y no facturar API. Preserva `CLAUDE_CODE_OAUTH_TOKEN`.
- **api**: LiteLLM local (`http://localhost:4000`, formato OpenAI).
- **local**: Ollama (`http://localhost:11434`).

Streaming:

- `_sse_text_chunks` para LiteLLM.
- `_ollama_text_chunks` para Ollama.
- Ambas rutas aceptan `usage` para tokens.

Log de decisiones:

```text
~/.dispatch/decisions.jsonl
```

Fallback seguro: `local`. No escalar silenciosamente a API paga si algo falla.

## Memoria

Capas:

- `CALIPSO.md`: identidad, reglas del harness y principios.
- `AGENTS.md`: handoff tecnico del proyecto.
- `LIBRARY.md`: mapa de biblioteca/memoria y reglas de promocion.
- `SPEC.md`: contrato de producto y plan de ejecucion del modo conversacion
  natural/desarrollador.
- Core markdown global/proyecto.
- `~/.calipso/global/core/pedro-perfil.md` y
  `~/.calipso/global/core/pedro-cronologia.md` como perfil + linea de tiempo de
  Pedro.
- Chroma episodica global/proyecto.
- Telemetria operativa.

Rutas:

- Global: `~/.calipso/global/{core,chroma}`.
- Proyecto: `<repo>/.calipso/core` + `~/.calipso/projects/<slug>/chroma`.

Embeddings obligatorios: `bge-m3` via Ollama, por soporte multilingue. No usar el
default ingles de Chroma para ranking en espanol.

## Mapa del repo

```text
dispatch.py
CALIPSO.md
AGENTS.md
LIBRARY.md
SPEC.md
RUNBOOK.md
SETUP.md
test_streaming.py
test_memory.py
test_capabilities.py
test_learning.py
test_orchestrator.py
test_skills.py
test_jobs.py
test_goals.py
test_developer.py
test_commands.py
test_verification.py
test_librarian.py
test_connectors.py
test_launch.py
test_prompt_compiler.py
test_proposals.py
test_attachments.py
test_sessions.py
test_github.py
test_routines.py
test_doclinks.py
test_ui.py
test_docs.py
check_doc_links.py
calipso/
  __init__.py
  attachments.py
  backup.py
  browser.py
  capabilities.py
  chats.py
  chronology.py
  config.py
  connectors.py
  costs.py
  developer.py
  deps.py
  discovery.py
  doclinks.py
  github.py
  learning.py
  goals.py
  jobs.py
  librarian.py
  memory.py
  orchestrator.py
  prompt_compiler.py
  routines.py
  server.py
  sessions.py
  skills.py
  telemetry.py
  verification.py
  web.py
  tools/commands.py
  web/index.html
.claude/launch.json
```

Datos runtime fuera del repo:

```text
~/.calipso/
~/.dispatch/decisions.jsonl
~/.claude/projects/C--Users-Pedro-Desktop-proycto/memory/
```

## Entorno y dependencias

- OS: Windows 11, PowerShell.
- Python: 3.12 esperado. En esta sesion el ejecutable no esta disponible en
  `PATH`; resolver antes de validar tests o arrancar por comando manual.
- pip: `litellm[proxy]`, `chromadb`, `ollama`, `playwright`.
- Playwright: Chromium instalado y usado para screenshots reales.
- Ollama: `qwen2.5:3b` (clasificador/planner), `qwen2.5:7b` (chat/reflect),
  `bge-m3` (embeddings).
- LiteLLM puede no estar arrancado todavia.
- Los CLIs `claude`/`codex` pueden no estar instalados/autenticados en todas las
  maquinas. Si no estan listos, Calipso degrada a local y debe explicarlo.

Gotcha importante: esta maquina puede correr Ollama 100% en CPU (`size_vram=0`).
`qwen2.5:7b` y el planner pueden tardar. No confundas latencia de CPU con bug sin
diagnosticar.

## Decisiones clave

- Pedro habla con Calipso, no con los backends. Los modelos son bocas internas.
- Calipso puede mostrar telemetria/proceso en la UI, pero la respuesta principal
  mantiene una sola voz.
- Memoria markdown-first para lo curado; vector para volumen.
- Multi-PC sera federado, sin duplicar archivos. Cada PC dueno de sus archivos;
  otros Calipsos leen bajo demanda via API del PC dueno.
- No usar Syncthing para este objetivo.
- Remoto seguro: Tailscale + token/TOTP. Nunca port-forwarding.
- Billing: nunca pasar `ANTHROPIC_API_KEY` al subprocess de la boca suscripcion.
- Si aparece un roadblock, diagnosticarlo y resolverlo. No saltarlo ni taparlo con
  una explicacion vaga.

## Proxima direccion recomendada

### 1. Endurecer lo ya construido

- Probar manualmente `/setup` y `/login` con un autenticador real.
- Probar Planning Mode desde la UI, no solo WebSocket directo.
- Verificar `/stop`, barge-in, historial de chats, panel Web y screenshots reales
  en navegador.
- Revisar que los controles visibles no sean placeholders.
- Hacer una prueba completa: pedido complejo -> plan -> aprobar -> agentes ->
  sintesis -> telemetria.

### 2. Elegir el siguiente bloque grande

Opciones recomendadas:

1. **Rutinas/timers/inbox:** workflows guardados que corren por horario o evento,
   dejan resultados en una bandeja y se auto-archivan si no hay nada.
2. **Multi-PC federado:** indice de ubicacion de archivos + selector de maquina en
   UI; Calipso-A lee archivos de Calipso-B via `/api/file` sin copiarlos.
3. **PWA + Tailscale:** instalar la web como app en iPhone y entrar por red privada.
4. **Quota-aware real:** no rutear a una API sin saldo ni a suscripcion con cuota
   agotada. `costs.py`, `telemetry.py` y `_backend_quota_low()` son la semilla.
5. **Bocas vivas:** instalar/autenticar `claude`/`codex` y arrancar LiteLLM para
   activar subscription/API de verdad.
6. **Perf CPU:** cache de veredictos, planner mas chico o por embeddings, modelo
   local mas liviano para chat.

## Backlog tecnico

- Loguear aceptar/descartar propuestas.
- Ejecutar `/api/learn` periodicamente o como rutina.
- Pasar effort real a sub-claude/sub-codex/local cuando el backend lo soporte.
- Descubrir modelos de suscripcion de forma mas real, no solo registry estatico.
- Hooks deterministas: acciones en eventos concretos (post-save, pre-run, fallo CI,
  resumen diario).
- Artifacts verificables: screenshots, walkthroughs y resumen de pruebas unidos al
  plan ejecutado.

## Contexto extra

La memoria persistente de sesiones Claude puede existir en:

```text
~/.claude/projects/C--Users-Pedro-Desktop-proycto/memory/
```

Codex no la lee automaticamente; por eso este `AGENTS.md` debe mantenerse
autocontenido.

Nota meta: una sesion anterior se cerro porque Pedro se quedo sin usage de Claude
y paso a Codex. Ese problema - repartir trabajo entre proveedores segun cuota
disponible - es exactamente parte del objetivo de Calipso.
