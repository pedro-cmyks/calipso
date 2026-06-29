# Calipso - spec completo de conversacion natural y modo desarrollador

## 0. Resumen ejecutivo

Calipso debe convertirse en el taller personal de Pedro: una conversacion natural
capaz de entender contexto, adjuntar archivos, investigar, modificar proyectos,
verificar, recordar y recomendar proximos pasos. La experiencia debe parecerse a
trabajar con un agente de codigo en una conversacion viva, pero con identidad
propia, memoria local, control de costos, herramientas reales y continuidad entre
sesiones.

La meta no es que Pedro aprenda comandos. La meta es que Pedro pueda escribir:

```text
Calipso, mira este proyecto, arregla lo del login, prueba que funcione y dejame
un resumen para seguir manana.
```

Y que Calipso haga lo correcto:

```text
entiende intencion -> reune contexto -> decide si planear -> usa skills/agentes
-> propone/aplica cambios con permisos -> verifica -> responde -> guarda memoria
```

## 1. Vision

Pedro debe poder usar Calipso como usa esta conversacion: con lenguaje natural,
ida y vuelta, archivos, investigacion, iteracion, criterio y acompanamiento.

Calipso no es un wrapper de modelos. Es el sistema que coordina modelos,
herramientas, memoria, permisos, verificacion y aprendizaje. Claude, Codex,
Ollama, LiteLLM, navegador, terminal y memoria son organos internos; Pedro habla
con Calipso.

## 2. Principios de producto

- **Natural antes que ceremonial:** slash commands existen, pero no deben ser el
  camino normal. Calipso decide cuando planear, investigar o usar equipo.
- **Una sola voz:** agentes internos y modelos no fragmentan la conversacion.
- **Autonomia con consentimiento:** Calipso puede leer, buscar, planear y probar;
  pide aprobacion para escribir, gastar, publicar, borrar o tocar fuera del repo.
- **Verificacion sobre confianza:** todo cambio importante termina con evidencia.
- **Memoria con bibliotecario:** no todo se guarda; se clasifica antes de promover.
- **Local-first:** Pedro conserva control de archivos, secretos y memoria.
- **Costo consciente:** suscripciones y local primero; API paga solo por politica o
  aprobacion explicita.
- **Continuidad:** otro agente o Calipso manana debe poder seguir sin adivinar.

## 3. Personas y modos de uso

### Pedro creador

Quiere hablar rapido, mezclar ideas, pedir cambios, recibir criterio y avanzar sin
administrar herramientas.

Necesita:

- conversacion natural;
- memoria de preferencias;
- adjuntar archivos;
- continuidad;
- recomendaciones claras.

### Pedro operador

Quiere que Calipso funcione en PC, iPhone y red privada.

Necesita:

- arranque simple;
- login seguro;
- Tailscale/PWA;
- runbook;
- recuperacion.

### Agente de codigo externo

Codex, Claude Code u otro agente entra al repo.

Necesita:

- `AGENTS.md`;
- `SPEC.md`;
- `LIBRARY.md`;
- pruebas;
- decisiones no relitigables.

## 4. Experiencia objetivo

### 4.1 Conversacion normal

Pedro escribe:

```text
arregla el login y dejame un resumen de que cambiaste
```

Calipso:

1. Clasifica la intencion como repo/codigo.
2. Detecta complejidad suficiente para auto-plan.
3. Busca archivos relevantes.
4. Crea equipo interno si suma valor.
5. Asigna skills: planner/coder/verifier/writer.
6. Propone diff si requiere escritura.
7. Aplica solo con permiso.
8. Corre pruebas.
9. Si toca UI, captura screenshot.
10. Responde con estado: implementado, verificado, pendiente.

### 4.2 Investigacion natural

Pedro escribe:

```text
investiga como lo hacen los mejores y dime que adoptamos
```

Calipso:

1. Detecta necesidad web si el tema es actual o externo.
2. Busca fuentes.
3. Lee y renderiza paginas cuando haga falta.
4. Muestra screenshots en panel Web.
5. Separa hechos, inferencias y opinion.
6. Convierte hallazgos en adopciones concretas.
7. Pregunta antes de promover conclusiones importantes a memoria estable.

### 4.3 Iteracion

Pedro escribe:

```text
no, eso no, hazlo mas natural y menos manual
```

Calipso:

- entiende que es una correccion del rumbo;
- conserva el objetivo;
- revisa plan si aun no ejecuto;
- propone ajuste incremental si ya ejecuto;
- registra feedback como senal de aprendizaje.

### 4.4 Adjuntos

Pedro puede:

- adjuntar archivo;
- adjuntar carpeta;
- adjuntar imagen;
- adjuntar seleccion del editor;
- decir "usa este archivo como contexto, no lo edites";
- decir "este archivo si puedes modificarlo".

Calipso debe mostrar chips claros:

```text
Contexto: auth.py (editable), screenshot.png (solo lectura), carpeta docs/
```

### 4.6 GitHub y proyectos remotos

Pedro debe poder preguntarle a Calipso:

```text
conectate a GitHub y muestrame mis proyectos
```

Calipso debe distinguir tres cosas:

- **Git local:** el repo abierto en el PC (`git status`, branch, diff, remotes).
- **GitHub remoto:** repos, issues, PRs, forks, permisos y actividad de la cuenta.
- **Flujo de contribucion:** branch, commit, push, fork o PR.

Estado objetivo:

1. Si el repo local tiene remoto GitHub, Calipso muestra repo, branch, remote,
   estado local y PRs relacionados.
2. Si Pedro pide ver otros proyectos, Calipso usa conector GitHub o `gh` si esta
   autenticado.
3. Si Pedro pide trabajar en un repo remoto, Calipso pregunta/decide:
   - clonar localmente;
   - abrir carpeta existente;
   - crear branch;
   - crear fork si no tiene permisos;
   - abrir PR solo con aprobacion.
4. Calipso nunca hace push, fork o PR sin permiso explicito.

UX deseada:

```text
GitHub
  - repos recientes
  - issues/PRs asignados
  - repo actual y remoto
  - acciones: clonar, abrir, crear branch, preparar PR
```

Estado v0 (hecho):

- `calipso/github.py` envuelve `gh` con un runner inyectable (testeable sin red ni
  login) y expone: usuario autenticado, `list_repos`, `assigned_items` (issues/PRs),
  `repo_overview` (remoto + branch + PRs abiertos detectados desde el git local) y
  `plan_contribution`/`_build_command` para clone/branch/fork/PR.
- Endpoints: `GET /api/github/overview`, `GET /api/github/repos`,
  `GET /api/github/assigned`, `POST /api/github/contribute/plan` (planifica sin
  ejecutar) y `POST /api/github/contribute/run` (ejecuta solo con `confirm:true`).
- La política se aplica por código: `run` sin `confirm` responde 403; `plan`
  siempre devuelve `requires_approval`. Calipso nunca pushea/forkea/abre PR solo.
- UI: bloque GitHub en el panel Config con usuario, repo+remoto, PRs abiertos,
  repos recientes y asignados; degrada con gracia si `gh` no esta instalado o sin
  login.
- `test_github.py` verifica parsing, overview, gating de contribucion y
  comando-builder; `test_ui.py` cubre el panel. Falta v0+: clone/branch/PR
  guiados desde chat en lenguaje natural y permisos de escritura sobre repos
  ajenos (fork-first).

### 4.5 Metas

Pedro puede darle a Calipso una meta persistente:

```text
Meta: dejame Calipso listo para usarlo desde el iPhone en mi red privada.
```

Una meta no es un mensaje suelto. Es un objetivo vivo que Calipso persigue entre
turnos hasta cerrarlo como completado, bloqueado o cancelado.

Calipso debe entender:

- objetivo;
- criterios de listo;
- subtareas;
- estado actual;
- riesgos;
- siguiente accion;
- evidencia de avance;
- que falta para declarar la meta cumplida.

Ejemplo de estado visible:

```text
Persiguiendo meta: Calipso listo en iPhone
Estado: en progreso
Ahora: configurar Tailscale/PWA
Siguiente: verificar login desde dispositivo externo
Bloqueos: falta instalar Tailscale en iPhone
```

Si Pedro escribe durante una meta:

```text
espera, antes arregla el login
```

Calipso debe decidir si eso es subtarea de la meta, interrupcion temporal, cambio
de objetivo o nueva meta. Solo debe preguntar si no puede inferirlo con seguridad.

## 5. Lenguaje de interaccion

### Natural

El camino principal:

```text
hazlo mas simple
mira este archivo
busca como se hace hoy
prueba si funciona
guardalo como memoria del proyecto
preparame para lanzarlo en mi iPhone
```

### Slash commands

Son controles manuales, no requisitos:

- `/plan`: fuerza plan revisable.
- `/team`: fuerza equipo/agentes.
- `/web`: fuerza investigacion web.
- `/fast`: prioriza velocidad.
- `/think`: sube intensidad.
- `/ultrathink`: maxima intensidad.
- `/local`, `/claude`, `/codex`, `/api`: fuerza ruta si esta disponible.
- `/stop`: detiene.

### Metas explicitas

Formas naturales que deben activar Goal Mode:

```text
meta: ...
mi objetivo es ...
persigue esto hasta dejarlo listo: ...
quiero que sigas con esto hasta completarlo: ...
dejame listo ...
```

No debe requerir sintaxis perfecta. Calipso debe detectar intencion de meta por
lenguaje natural y convertirla en objetivo con criterios de listo.

### Lenguaje interno / Prompt Compiler

Pedro habla natural; Calipso no debe reenviar esa frase cruda a todos los
modelos como si fueran una caja magica. Debe compilar el turno a un brief interno
con instrucciones, memoria, contexto, herramientas y evidencia esperada.

La literatura actual empuja en esta direccion:

- OpenAI describe el prompting como escribir instrucciones efectivas para que un
  modelo produzca resultados consistentes; tambien separa herramientas,
  contexto, agentes, evaluacion y estado conversacional como piezas del sistema.
- Anthropic plantea el context engineering como evolucion del prompt
  engineering: no solo redactar instrucciones, sino decidir que conocimiento,
  historial, herramientas y estado entran al contexto del agente.
- La documentacion de Claude recomienda definir criterios de exito y formas de
  evaluar antes de optimizar prompts; no todo problema se arregla con palabras.
- MCP define un estandar para conectar aplicaciones de IA con datos,
  herramientas y workflows externos: el modelo no vive aislado, opera con
  contexto y capacidades.
- 12-factor agents resume patrones utiles para produccion: aduenarse de prompts,
  ventana de contexto, flujo de control, estado, herramientas y agentes pequenos.

Referencias base:

- OpenAI Prompt Engineering:
  `https://developers.openai.com/api/docs/guides/prompt-engineering`
- Anthropic Effective Context Engineering for AI Agents:
  `https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents`
- Claude Prompt Engineering Overview:
  `https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview`
- Model Context Protocol:
  `https://modelcontextprotocol.io/docs/getting-started/intro`
- 12-Factor Agents:
  `https://github.com/humanlayer/12-factor-agents`

Para Calipso, eso se traduce en:

```text
mensaje de Pedro
-> intent frame
-> perfil de Pedro + memoria relevante
-> project lens
-> goal lens
-> tool/permission frame
-> verification frame
-> brief por agente/modelo
-> sintesis en una sola voz
```

Contrato interno:

- El perfil de Pedro es contexto editable, no verdad inmutable.
- Las referencias comprimidas ("Atlas", "Observatory", "mi biblioteca") deben
  expandirse desde memoria curada cuando exista, o convertirse en pregunta/tarjeta
  de memoria cuando falte.
- El prompt visible de Pedro se conserva como fuente de intencion; el prompt de
  trabajo puede ser reescrito para cada modelo/agente.
- Cada agente recibe objetivo, contexto minimo, limites, herramientas permitidas y
  evidencia esperada.
- Calipso no revela cadena de pensamiento; si muestra proceso, muestra estado,
  decisiones, fuentes, pruebas y pendientes.
- La memoria nueva entra como propuesta del bibliotecario salvo datos triviales o
  explicitamente pedidos.

Implementacion v0:

- `calipso/prompt_compiler.py` centraliza el contrato y ordena contexto estable
  -> volatil -> estado operativo.
- `~/.calipso/global/core/pedro-perfil.md` guarda el perfil base importado por
  Pedro como memoria global evolutiva.
- `~/.calipso/global/core/pedro-cronologia.md` guarda actualizaciones fechadas
  sobre Pedro, sus etapas y proyectos. Es linea de tiempo, no identidad fija.
- `_build_context()` usa el prompt compiler para incluir memoria, contrato,
  recuerdos, repo, meta activa y health/runtime antes de llamar modelos.

### Respuesta esperada

Calipso responde breve, con estado operativo cuando importa:

```text
Listo. Cambie X y Y. Verifique con test_z y captura del login. Queda pendiente
probarlo desde el iPhone.
```

## 6. Capacidades existentes

- Chat web con WebSocket.
- Editor Monaco y explorador.
- Cambio de proyecto.
- Historial de chats por proyecto.
- Ruteo por modelo/capacidad/intensidad con scoring calibrado.
- Multilingüismo: Calipso detecta el idioma de cada turno y responde en ese idioma;
  entiende oraciones mixtas y usa bge-m3 (multilingual) para embeddings de memoria.
- Narración local: botón "Narrar" en cada respuesta + toggle auto-narrar;
  Web Speech API (cero deps, usa voces del sistema, detecta idioma automáticamente).
- Memoria hibrida global/proyecto.
- Perfil global de Pedro y cronologia personal curada.
- Bibliotecario activo con inbox, propuestas, aceptar/descartar y core visible.
- Telemetria y costos.
- TOTP/token.
- Navegacion web con preview visual.
- Browser real con Playwright/Chromium.
- `deps.py` con instalacion bajo demanda.
- Agentes dinamicos.
- Skills internos.
- Auto-plan vs `/plan` revisable.
- Goal Mode persistente con Goal Bar, criterios, subtareas y evidencia.
- Developer Loop: `advance_goal` + `draft_brief` + propuesta de diff aplicable.
- Jobs persistentes y panel Trabajo.
- Runner allowlist para verificaciones seguras.
- Verificacion fuerte v0 por tipo de cambio.
- Propuestas/diffs, aplicar y aplicar + verificar.
- Adjuntos reales: archivo, carpeta, seleccion del editor, archivo abierto e
  imagen como artifact no textual.
- Artifacts de respuesta v0 con copiar/abrir.
- GitHub remoto v0 en modo seguro, sin push/fork/PR sin confirmacion.
- Rutinas/timers/backup v0.
- Launch personal v0 con PWA basica y lanzadores.
- Conectores/cuotas v0.
- Panel de sesiones y skills.
- `CALIPSO.md`, `AGENTS.md`, `LIBRARY.md`, `SPEC.md`.

## 7. Capacidades faltantes

### Criticas

- Generacion autonoma robusta de diffs desde chat, con permisos editables claros
  desde adjuntos y seleccion del editor.
- Screenshot/browser check automatico para cambios visuales.
- Artifacts conversacionales persistentes como recursos descargables/URL propia.
- Cierre automatico robusto de metas contra criterios con evidencia suficiente.
- Sugerencias automaticas de memoria desde sesiones completas, no solo manuales.
- Vision multimodal real para imagenes adjuntas.
- Jobs persistentes v0 existe: `calipso/jobs.py`, endpoints `/api/jobs` y
  `/api/jobs/{job_id}`. Tambien expone artifacts por
  `/api/jobs/{job_id}/artifacts/{name}` y el panel Trabajo permite abrir detalle
  de jobs recientes. Falta convertirlo en runner completo; hoy registra procesos
  largos, salida, errores y eventos para reconstruir actividad.
- Developer Loop minimo v0 existe: `calipso/developer.py` y
  `/api/goals/{goal_id}/advance` convierten la siguiente subtarea de una meta en
  job persistente con artifact `next-action.md`, evidencia y panel Trabajo.
  `calipso/tools/commands.py`, `/api/commands` y `/api/commands/run` agregan
  runner allowlist de verificaciones seguras como jobs con stdout/stderr/result.
  `/api/proposals/{id}/apply` crea job/evidencia/artifacts al aplicar cambios y
  la UI soporta `Aplicar + verificar`. Falta generacion autonoma robusta de diffs
  desde chat.
- Verificacion fuerte v0 existe: `calipso/verification.py`,
  `/api/verify/recommend` y `/api/verify/run` mapean archivos cambiados o
  propuestas a comandos allowlist, ejecutan un plan secuencial y dejan job
  `verification_plan` con `verification-report.json` y `verification-report.md`.
  El boton `Verificar` de la Goal Bar usa este plan automatico. Falta screenshot
  browser automatico para cambios visuales y verificacion mas profunda de links.
- Bibliotecario activo v0 existe: `calipso/librarian.py` y endpoints
  `/api/memory/inbox*` crean propuestas editables de memoria, permiten aceptar o
  descartar con log y promueven al core markdown global/proyecto solo tras
  aceptacion. La UI tiene panel `Memoria`. Falta reflect/learn periodico y
  sugerencias automaticas mas inteligentes desde sesiones completas.
- Adjuntos v0 existe: `calipso/attachments.py`, `/api/attachments` y
  `/api/attachments/{id}` guardan archivos de texto como contexto de chat, crean
  job/evidencia/artifact y se inyectan al siguiente turno con presupuesto. La UI
  permite adjuntar archivo externo, seleccion del editor o archivo abierto, con
  metadata de origen y modo `editable` cuando viene del editor. Imagen v0 se
  guarda como binario/base64 y artifact, y se referencia en el contexto sin
  inyectarla como texto. Carpeta/proyecto v0 empaqueta archivos textuales
  pequeños con manifiesto, omitidos y presupuesto. Falta vision multimodal real
  y permisos editables completos.
- Artifacts de respuesta v0 existe en la UI: las respuestas de Calipso tienen
  copiar y, cuando son largas o contienen bloque de codigo, muestran una tarjeta
  `Artifact` con abrir/cerrar y copiar. Falta persistir artifacts conversacionales
  como entidades descargables con URL propia.
- Goal Mode persistente v0 existe: `calipso/goals.py`, endpoints `/api/goals`,
  `/api/goals/{goal_id}` y `/api/goals/{goal_id}/evidence`, deteccion natural
  tipo `meta: ...`, Goal Bar, controles minimos de evidencia/bloqueo/cierre,
  marcado de criterios desde el detalle y asociacion de jobs de suscripcion como
  evidencia. Falta cierre automatico robusto contra criterios y editor completo
  de criterios/subtareas.
- Politica de permisos aplicada por codigo, no solo documentada.

### Importantes

- Inbox de tareas/eventos no accionados. El inbox de memoria ya existe; falta una
  bandeja mas general para resultados de rutinas, hallazgos y pendientes.
- Rutinas/timers. (v0 hecho: `calipso/routines.py` + ticker + panel Config;
  rutinas reflect/learn/backup programables y ejecutables a mano)
- Health real de conectores. (hecho: `calipso/connectors.py`)
- GitHub remoto: repos, issues, PRs, clone/fork/branch/PR con permisos claros.
  (v0 hecho: `calipso/github.py` + endpoints `/api/github/*` + panel Config; ver 4.6)
- Cuota/budget-aware real. (hecho: budget mensual + bloqueo)
- PWA/Tailscale. PWA basica existe; falta configuracion guiada Tailscale/iPhone.
- Runbook de lanzamiento personal. (hecho: `RUNBOOK.md`; falta convertirlo en
  diagnostico guiado dentro de Calipso)

### Futuras

- Multi-PC federado.
- Voz de alta calidad local (Piper TTS — upgrade a Web Speech API ya implementado).
- Imagenes: decidir buscar vs generar.
- Transcripcion de audio/video local (Whisper).
- Workflows compartibles como skills instalables.
- Modo copiloto silencioso: watch del repo y sugerencias no invasivas.

## 8. Arquitectura objetivo

```text
UI conversacional
  |
  | texto / voz / adjuntos / seleccion
  v
Intent Router
  |
  |- responder
  |- investigar
  |- editar repo
  |- verificar
  |- recordar
  |- configurar
  |- lanzar
  v
Context Builder
  |
  |- CALIPSO.md
  |- core global/proyecto
  |- episodios relevantes
  |- adjuntos
  |- estado operativo
  v
Goal Manager
  |
  |- meta activa
  |- criterios de listo
  |- subtareas
  |- bloqueos
  |- evidencia
  v
Planner
  |
  |- directo si simple
  |- auto-plan si complejo
  |- plan revisable si /plan o riesgo alto
  v
Orchestrator
  |
  |- agentes dinamicos
  |- skills internos
  |- modelo/ruta por capacidad
  v
Tool Layer
  |
  |- filesystem seguro
  |- rg/search
  |- propuestas/diff/apply
  |- comandos allowlist
  |- navegador/screenshot
  |- web research
  |- git
  |- memoria
  v
Verifier
  |
  |- tests
  |- endpoints
  |- screenshot
  |- diff
  |- lint/compile
  v
Response + Artifacts + Memory
```

## 9. Componentes nuevos propuestos

### 9.1 Intent Router

Modulo sugerido:

```text
calipso/intent.py
```

Salida:

```json
{
  "intent": "edit_repo",
  "risk": "medium",
  "needs_plan": true,
  "needs_approval": true,
  "needs_web": false,
  "needs_files": true,
  "suggested_skills": ["planner", "coder", "verifier"],
  "reason": "pedido de cambio en repo con verificacion"
}
```

### 9.2 Tool Layer

Modulo sugerido:

```text
calipso/tools/
  files.py
  commands.py
  git.py
  artifacts.py
  attachments.py
```

Regla: cada herramienta declara permisos, entradas, salida y riesgos.

### 9.3 Developer Loop

Modulo sugerido:

```text
calipso/developer.py
```

Contrato:

```text
prepare_change(request) -> plan + proposed actions
apply_change(change_id) -> touched files + diff
verify_change(change_id) -> tests + screenshots + status
summarize_change(change_id) -> response + memory suggestions
```

### 9.4 Artifact Store

Ruta sugerida:

```text
~/.calipso/projects/<slug>/artifacts/<task_id>/
```

Contenido:

```text
plan.json
events.jsonl
diff.patch
tests.txt
screenshot.png
summary.md
memory_suggestions.json
```

### 9.4.1 Job Runner persistente

Los procesos largos deben vivir en el servidor, no en el WebSocket. Si Pedro
recarga, cambia de panel o abre otra pestana, Calipso debe poder reconectarse al
job y seguir mostrando progreso.

Modulo sugerido:

```text
calipso/jobs.py
```

Contrato:

```text
start_job(kind, payload) -> job_id
stream_job(job_id) -> eventos
cancel_job(job_id) -> estado cancelado
job_status(job_id) -> running/done/failed/cancelled
```

Cada job debe escribir eventos a:

```text
~/.calipso/projects/<slug>/jobs/<job_id>/events.jsonl
```

Esto evita que "me fui a hacer clic a otra cosa" rompa el trabajo.

### 9.5 Inbox

Tipos:

- memoria sugerida;
- prueba fallida;
- tarea pendiente;
- decision que requiere Pedro;
- actualizacion de conector;
- recomendacion de lanzamiento.

### 9.6 Goal Manager

Modulo sugerido:

```text
calipso/goals.py
```

Persistencia:

```text
~/.calipso/projects/<slug>/goals.jsonl
```

Modelo:

```json
{
  "id": "goal_...",
  "title": "Calipso listo en iPhone",
  "objective": "Dejar Calipso usable desde el iPhone por red privada",
  "status": "active",
  "done_criteria": [
    "Calipso abre desde iPhone",
    "Login TOTP funciona",
    "No hay puerto publico abierto"
  ],
  "tasks": [
    {"id": "t1", "text": "Configurar Tailscale", "status": "pending"},
    {"id": "t2", "text": "Crear PWA", "status": "pending"}
  ],
  "evidence": [],
  "blockers": [],
  "notes": []
}
```

Estados:

- `active`: Calipso esta persiguiendo la meta.
- `waiting`: espera accion de Pedro o recurso externo.
- `blocked`: no puede avanzar sin algo concreto.
- `complete`: criterios de listo cumplidos y verificados.
- `cancelled`: Pedro la cancelo.

Regla: Calipso no marca `complete` solo porque avanzo mucho; debe mapear contra
criterios de listo y evidencia.

## 10. Skills internos

Skills actuales:

- `planner`: descompone objetivo.
- `researcher`: busca hechos/fuentes.
- `coder`: edita codigo con cuidado.
- `reviewer`: detecta riesgos/regresiones.
- `writer`: redacta claro.
- `librarian`: clasifica memoria.
- `verifier`: prueba y separa estados.
- `synthesizer`: une resultados.

Skills creativos propuestos:

- `scout`: explora repo y crea mapa rapido.
- `surgeon`: cambio minimo de codigo con bajo blast radius.
- `qa_pilot`: maneja navegador, screenshots y flujos UI.
- `quartermaster`: instala/verifica dependencias y conectores.
- `historian`: revisa commits/memoria para no repetir decisiones.
- `launch_coach`: prepara runbook, PWA, Tailscale y checklist diaria.
- `critic`: contradice el plan y busca fallos antes de ejecutar.

Regla: un skill no es personalidad. Es tecnica de trabajo.

## 11. Politica de permisos

### Puede hacer solo

- Leer archivos dentro del proyecto activo.
- Buscar texto dentro del proyecto.
- Consultar memoria.
- Buscar web si el pedido lo necesita.
- Crear plan interno.
- Generar propuestas no aplicadas.
- Correr comandos allowlist no destructivos.
- Capturar screenshots.
- Crear artifacts de tarea.

### Debe pedir aprobacion

- Aplicar diffs.
- Escribir fuera del proyecto activo.
- Borrar archivos.
- Instalar dependencias nuevas o pesadas.
- Usar API paga fuera de politica.
- Publicar, pushear, abrir PR, desplegar.
- Cambiar seguridad/autenticacion.
- Promover memoria sensible.
- Reescribir `CALIPSO.md`.

### Nunca debe hacer

- Exponer secretos.
- Abrir puerto a internet.
- Escalar silenciosamente a API paga.
- Marcar como verificado sin evidencia.
- Revertir cambios de Pedro sin permiso.
- Duplicar archivos entre PCs como solucion multi-PC.

## 12. UX requerida

### Chat

- Entrada natural.
- Adjuntos.
- Chips de contexto.
- Estado visible de proceso.
- Boton detener.
- Mensajes de plan automatico sin bloquear.
- Plan revisable solo cuando se fuerza o el riesgo lo exige.

### Goal Bar

Cuando hay meta activa, la UI debe mostrar una barra compacta:

```text
Persiguiendo meta: <titulo> | estado | tiempo | controles
```

Controles:

- abrir detalle;
- pausar/cancelar;
- marcar bloqueo;
- ver evidencia;
- cambiar criterios.

La barra debe sentirse como una brujula, no como un modal. No debe tapar la
conversacion ni obligar a Pedro a trabajar de forma rigida.

### Panel Trabajo

Debe mostrar:

- plan actual;
- agentes/skills;
- archivos tocados;
- comandos ejecutados;
- pruebas;
- screenshots;
- estado final.

### Panel Biblioteca

Debe mostrar:

- memoria sugerida;
- destino sugerido: global/proyecto/AGENTS/CALIPSO/LIBRARY/SPEC;
- razon;
- botones aceptar/descartar/editar.

### Panel Metas

Debe mostrar:

- meta activa;
- metas anteriores;
- criterios de listo;
- subtareas;
- evidencia;
- bloqueos;
- historial de decisiones;
- boton "convertir esta conversacion en meta".

### Panel Launch

Debe mostrar:

- estado de TOTP;
- Tailscale;
- PWA;
- conectores;
- modelos vivos;
- backup;
- checklist diaria.

## 13. Plan de ejecucion

### Fase 0 - checkpoint estable

Objetivo: cerrar el paquete actual.

Tareas:

- Revisar diff.
- Correr pruebas base.
- Commit.

Validacion:

- Git limpio.
- Tests verdes.
- `AGENTS.md`, `LIBRARY.md`, `SPEC.md` coherentes.

### Fase 1 - Developer Loop minimo

Objetivo: Calipso puede hacer un cambio pequeno supervisado desde su UI.

Tareas:

- [x] Crear `calipso/tools/commands.py` con allowlist.
- Crear endpoint `/api/run` o `/api/tools/command`.
- Crear artifact store basico.
- Crear flujo developer:
  - plan;
  - propuesta;
  - aplicar con aprobacion;
  - test;
  - resumen.
- [x] Integrar con panel Trabajo.
- [x] Endpoint para correr pruebas allowlist como jobs con artifacts.
- [x] Aplicar propuestas como jobs con diff/contenido/evidencia.

Validacion:

```text
Pedido: agrega un test simple para skills.
Resultado: Calipso propone cambio, aplica con permiso, corre test_skills.py y resume.
```

### Fase 1.5 - Goal Mode minimo

Objetivo: Calipso entiende una meta persistente y la usa para organizar trabajo.

Tareas:

- [x] Crear `calipso/goals.py`.
- [x] Endpoint `GET /api/goals`, `POST /api/goals`, `PUT /api/goals/{id}`.
- [x] Detectar lenguaje natural de meta.
- [x] Mostrar Goal Bar en UI.
- [x] Asociar jobs/artifacts de procesos de suscripcion a meta activa.
- [x] Permitir completar, bloquear y cancelar desde UI.
- [~] Pausar/esperar y editar criterios/subtareas. Backend soporta estados y
  marcado minimo; falta editor completo.

Validacion:

```text
Pedro: meta: dejame listo Calipso para usarlo desde el iPhone.
Calipso: crea meta, propone criterios, genera subtareas y muestra Goal Bar.
```

### Fase 2 - Adjuntos reales

Objetivo: Pedro manda contexto sin copiar/pegar.

Tareas:

- [x] Upload de archivo de texto al chat.
- [x] Adjuntar seleccion del editor.
- [x] Adjuntar imagen como referencia binaria.
- [x] Adjuntar carpeta/proyecto como bundle textual presupuestado.
- [x] Guardar referencias en historial.
- [x] Presupuesto de contexto por adjunto.
- [~] Distinguir solo lectura vs editable. Ya se guarda `mode` y origen; falta
  que el agente use ese permiso para proponer/aplicar cambios sobre el adjunto.

Validacion:

```text
Pedro adjunta un archivo y pide "resumelo y dime si toca cambiarlo".
Calipso usa el archivo y distingue solo lectura vs editable.
```

### Fase 3 - Verificacion fuerte

Objetivo: cada cambio importante termina con prueba.

Tareas:

- [x] Mapeo tipo de cambio -> verificacion.
- [x] Backend: py_compile/tests/endpoints.
- [~] Frontend: screenshot/browser check. V0 revisa sintaxis JS inline; falta
  screenshot automatico por tipo de cambio visual.
- [x] Docs: links/rutas/coherencia. `calipso/doclinks.py` + `check_doc_links.py`
  validan que las referencias internas (calipso/..., test_*.py, scripts raiz)
  citadas en los docs existan; comando allowlist `docs_links` se suma al plan de
  verificacion cuando cambian docs. Conservador: omite URLs, runtime y placeholders.
- [x] Reporte final estructurado.

Validacion:

```text
Cambio UI -> screenshot.
Cambio Python -> py_compile + test relevante.
Cambio docs -> no rompe brief/referencias.
```

### Fase 4 - Bibliotecario activo

Objetivo: Calipso propone memoria en vez de escribir todo.

Tareas:

- [x] Inbox de memoria.
- [x] Propuestas editables.
- [x] Log aceptar/descartar.
- [x] Reflect periodico. `calipso/routines.py` permite una rutina `reflect` con
  intervalo; el ticker del server la corre cuando vence (mientras este vivo).
- [x] Learn periodico. Rutina `learn` (global + proyecto) via el mismo scheduler.

Validacion:

```text
Tras una sesion, Calipso propone aprendizajes y Pedro acepta/descarta.
```

### Fase 5 - Conectores vivos y cuotas

Objetivo: modelos como musculos reales.

Tareas:

- [x] Health real Claude/Codex/Ollama/LiteLLM. V0 prueba CLIs de suscripcion y
  endpoints HTTP de Ollama/LiteLLM.
- [x] Login guiado. Los conectores CLI exponen accion de instalar/login/health
  desde la configuracion.
- [~] Cuota/bloqueo. API tiene presupuesto mensual local y bloqueo automatico;
  Claude/Codex tienen bloqueo manual. La cuota exacta de suscripcion queda como
  desconocida si el proveedor no la expone.
- [x] `_backend_quota_low()` real. Usa el estado normalizado de conectores y
  limites para evitar rutas agotadas o bloqueadas.
- [x] Fallback transparente. El estado de harness muestra razon humana:
  apagado, bloqueado, presupuesto cerca/agotado o listo.

Validacion:

```text
Si un backend falla, Calipso cambia de ruta y explica sin perder el turno.
```

Implementacion v0:

- `calipso/connectors.py` normaliza health, limite y disponibilidad por backend.
- `/api/connectors/health` expone health + resumen de ruteo.
- La UI permite definir budget API mensual y bloquear Claude/Codex manualmente.
- `test_connectors.py` verifica warning, bloqueo, disponibilidad y cuota baja.

### Fase 6 - Launch personal

Objetivo: Pedro usa Calipso todos los dias.

Tareas:

- [x] `RUNBOOK.md`.
- [x] Lanzador Windows: `Calipso.bat` / `Calipso.ps1`.
- [x] Lanzador cross-platform: `launch_calipso.py`.
- [x] PWA basica: manifest + service worker + icono.
- [~] Tailscale. Decidido como ruta segura, falta configuracion guiada en maquina.
- [x] Arranque facil: el lanzador detecta si ya esta prendido, espera health y abre
  navegador con token.
- [x] Backup. `calipso/backup.py` zipea el runtime curado (memoria, metas,
  config, chats) a `CALIPSO_HOME/backups/`; rutina `backup` programable y boton
  `Backup ahora` + `POST /api/backup`. Excluye caches pesados; 100% local.
- [x] Checklist de salud visible: `/api/launch/checklist` y panel Config muestran
  seguridad, PWA, navegador real, lanzadores, modelos y budget.

Validacion:

```text
Pedro abre Calipso desde PC/iPhone, conversa, adjunta contexto, pide cambios y
recibe verificacion.
```

Implementacion v0:

- `launch_calipso.py` prende el servidor local y abre Calipso.
- `Calipso.bat` y `Calipso.ps1` son lanzadores de doble clic/PowerShell.
- `/api/launch/checklist` devuelve un semaforo humano de uso diario.
- `test_launch.py` verifica que el checklist exista y cubra seguridad, PWA,
  lanzadores y modelos.

### Fase 7 - Lenguaje interno / Prompt Compiler

Objetivo: Calipso traduce la conversacion natural de Pedro a briefs internos
con memoria, herramientas, permisos y evidencia, sin convertir el perfil de Pedro
en una regla rigida.

Tareas:

- [x] Importar perfil base de Pedro a memoria global curada:
  `~/.calipso/global/core/pedro-perfil.md`.
- [x] Documentar que el perfil es seed evolutivo, no biografia cerrada.
- [x] Crear `calipso/prompt_compiler.py` con contrato interno y orden de contexto.
- [x] Integrar `_build_context()` con el prompt compiler.
- [x] Agregar `test_prompt_compiler.py` y comando allowlist.
- [x] Usar el prompt compiler para briefs por agente individual. El orquestador
  agrega `agent_brief()` con pedido original, rol, subtarea, skill, permisos y
  evidencia esperada.
- [x] UI de memoria global v0. El panel Memoria muestra `/api/memory/core`,
  incluyendo `pedro-perfil.md`, y permite preparar propuestas globales al archivo
  correcto sin editar el core directo.
- [x] Cronologia personal v0. `/api/memory/chronology` expone
  `~/.calipso/global/core/pedro-cronologia.md`; la UI la muestra en Memoria y
  permite preparar entradas fechadas que se promueven por bibliotecario.

Validacion:

```text
Pedro menciona un proyecto/persona/preferencia comprimida.
Calipso usa memoria global como contexto, pregunta si falta algo, y si aprende
algo durable propone guardarlo con bibliotecario.
```

Implementacion v0:

- `test_prompt_compiler.py` verifica que sistema, memoria, contrato, recuerdos,
  repo, meta y runtime queden en orden y con reglas sobre perfil editable.
- `test_orchestrator.py` verifica que cada agente reciba brief interno formal.
- `calipso/tools/commands.py` incluye `test_prompt_compiler`.
- Cambios en memoria/contexto activan verificacion relacionada desde
  `calipso/verification.py`.
- `/api/memory/core` y el panel Memoria muestran core global/proyecto en modo
  lectura; los cambios siguen pasando por propuestas del bibliotecario.
- `calipso/chronology.py` asegura y parsea `pedro-cronologia.md`; el endpoint
  `/api/memory/chronology/proposals` crea propuestas globales al archivo correcto
  sin escribir directo al core.

## 14. Matriz de validacion

| Area | Prueba | Evidencia |
| --- | --- | --- |
| Chat | enviar mensaje simple | respuesta visible |
| Auto-plan | tarea compleja sin `/plan` | plan visible y ejecucion sin `ok` |
| Plan revisable | tarea con `/plan` | espera aprobacion |
| Skills | abrir panel Sesion | 8+ skills visibles |
| Repo | pedir cambio pequeno | diff/propuesta |
| Aplicacion | aprobar cambio | archivo modificado |
| Tests | correr test relevante | salida capturada |
| UI | cambio frontend | screenshot |
| Web | pedir investigacion | fuentes + preview |
| Goal Mode | "meta: ..." | meta activa + criterios + Goal Bar |
| Goal continuidad | mensaje relacionado | asociado a meta activa |
| Goal cierre | criterios cumplidos | estado complete + evidencia |
| Memoria | proponer aprendizaje | inbox/promocion |
| Cronologia | abrir panel Memoria | `pedro-cronologia.md` visible + proponer evento |
| Seguridad | entrar sin cookie | 401/login |
| TOTP | login codigo valido | cookie sesion |
| Costos | ruta API bloqueada si no permitida | no escalamiento silencioso |

## 15. Riesgos y mitigaciones

- **Latencia CPU:** usar modelos chicos para planner, cache y fallback heuristic.
- **Falsa autonomia:** permisos por accion, no solo prompts.
- **Memoria ruidosa:** inbox y bibliotecario antes de promover.
- **Costo accidental:** policy + quota + confirmacion API paga.
- **UI con controles falsos:** todo control visible debe tener endpoint y prueba.
- **Fragilidad Playwright:** deps verifica paquete y binario; retry de instalacion.
- **Contexto excesivo:** adjuntos presupuestados y lectura bajo demanda.
- **Multi-PC confuso:** indice de ubicacion, no sincronizacion masiva.

## 16. Ideas creativas para que Calipso se sienta vivo

### Mesa de trabajo

Cada tarea crea una mesa:

```text
objetivo
contexto
plan
archivos
agentes
pruebas
resultado
memoria sugerida
```

Pedro puede volver a una mesa manana.

### Metas como brujula

Una meta activa se vuelve la brujula de Calipso. No reemplaza la conversacion:
la orienta. Cada respuesta puede preguntarse internamente:

```text
Esto acerca la meta?
Esto la cambia?
Esto es una interrupcion?
Esto revela un bloqueo?
```

La UI puede mostrar una linea viva:

```text
Meta: Lanzar Calipso personal | 3/7 criterios | siguiente: PWA
```

### Semaforo de confianza

Cada respuesta operativa tiene estado:

- verde: verificado;
- amarillo: implementado sin prueba completa;
- rojo: bloqueado;
- gris: idea/no ejecutado.

### Modo copiloto silencioso

Mientras Pedro edita, Calipso observa cambios del repo y puede decir:

```text
Vi que tocaste server.py. Puedo correr la prueba relacionada o revisar el diff.
```

Solo sugiere; no invade.

### Diario del taller

Al final del dia:

```text
Hoy avanzamos: X.
Quedo pendiente: Y.
Aprendizajes sugeridos: Z.
Riesgo principal: W.
```

### Launch Coach

Un skill dedicado revisa si Calipso esta listo para uso diario:

```text
auth OK
PWA pendiente
Tailscale pendiente
backup pendiente
conectores parcial
```

### Biblioteca con curaduria

Calipso no "recuerda todo"; propone tarjetas:

```text
Guardar como preferencia global?
Guardar como decision del proyecto?
Agregar al handoff?
Descartar como ruido?
```

## 17. Recomendacion de lanzamiento

No lanzar Calipso publico todavia. Lanzarlo como herramienta personal de Pedro en
tres anillos:

1. **Local PC:** taller principal con lanzador tipo app.
2. **PWA celular:** instalable desde navegador.
3. **Red privada:** iPhone por Tailscale/PWA.
4. **Multi-PC federado:** cada PC duena de sus archivos.

El primer lanzamiento exitoso es que Pedro lo use una semana para:

- conversar;
- adjuntar archivos;
- pedir investigacion;
- hacer cambios pequenos;
- verificar;
- continuar al dia siguiente.

## 18. Definition of Done final

Calipso esta listo para reemplazar una parte grande de esta conversacion cuando:

- entiende pedidos sin slash;
- adjunta y lee contexto sin friccion;
- decide plan/web/agentes por si mismo;
- usa skills internos de forma trazable;
- edita mediante propuestas;
- aplica con permiso;
- corre pruebas;
- verifica visualmente si toca UI;
- guarda artifacts;
- propone memoria con bibliotecario;
- usa modelos disponibles con fallback honesto;
- evita costos inesperados;
- puede continuar trabajo entre sesiones;
- Pedro siente que esta hablando con Calipso, no operando un panel tecnico.
- Pedro no necesita recordar como prender localhost.

## 19. Primeros bloques a construir despues de este spec

Primero construir Fase 1:

```text
Developer Loop minimo
```

Orden recomendado:

1. Commit del checkpoint actual.
2. `calipso/tools/commands.py` con allowlist.
3. Artifact store basico.
4. Endpoint para correr pruebas.
5. Integrar resultado en panel Trabajo.
6. Primer flujo completo desde chat.

Primer caso de prueba:

```text
Pedro: agrega una prueba pequena para comprobar que /api/skills devuelve el
skill Bibliotecario.

Calipso:
  - auto-planea;
  - propone diff;
  - aplica con permiso;
  - corre test;
  - verifica;
  - resume.
```

Luego construir Fase 1.5:

```text
Goal Mode minimo
```

Primer caso de prueba:

```text
Pedro: meta: dejame Calipso listo para usarlo desde el iPhone.

Calipso:
  - crea meta persistente;
  - propone criterios de listo;
  - crea subtareas;
  - muestra Goal Bar;
  - asocia acciones futuras a esa meta;
  - no la marca completa sin evidencia.
```
