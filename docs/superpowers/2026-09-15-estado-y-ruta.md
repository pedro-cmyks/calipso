# Calipso: donde estamos, que hay, adonde vamos (2026-09-15)

Este es el documento para volver. Reemplaza como punto de entrada al del 2026-09-09 (que sigue valiendo
como historia detallada de esas semanas). Escrito al cerrar la tanda de los goals y los probes en
produccion, con Pedro parando por su limite de la semana.

## 1. Que es Calipso, en una pagina

Calipso es el asistente personal de Pedro: corre en su ROG Ally (Bazzite, 11,4 GiB de RAM), es un server
Python (`calipso/server.py`, FastAPI) con una PWA de chat, un tablero (`/fabrica`) y una API. Pedro le
habla siempre a Calipso; Claude, Codex, DeepSeek y los modelos locales de Ollama (`qwen2.5:7b`,
`qwen2.5:3b`, `bge-m3`) son herramientas internas suyas. Lo que la distingue de un chat:

- **Rutea** cada pedido al modelo que conviene (local, suscripcion, API) segun la tarea, la intensidad,
  la privacidad y la carga de la maquina; Pedro puede forzar con `/fast`, `/think`, `/ultrathink`,
  `/local`, `/claude`, `/codex`, `/web`, `/plan`, `/nube`.
- **Recuerda** con procedencia: cada recuerdo dice de donde salio y cuando; los embeddings los hace Ollama
  (`bge-m3`), el server no carga torch.
- **Es honesta a proposito**: los canarios miden cada turno (anclaje, degeneracion, ventana) y la aduana
  registra todo lo que sale de la maquina (a quien, que, cuanto).
- **Tiene una economia** de agentes y departamentos con una moneda interna, permisos con compuertas (lo que
  se hace solo, lo que pregunta, lo que NUNCA) y un inbox donde Pedro decide.
- **Corre goals** (desde el 2026-09-14): una tarea con objetivo, criterio medible, tope y compuertas que
  corre sola en un clon del repo con Claude Code como martillo dentro de un sandbox, con un hook
  fail-closed, un juez de otra familia y Pedro al final.
- **Cuida la maquina**: mide la carga y bajo presion posterga, avisa o va por suscripcion; nunca escala
  en silencio.

Codigo: 45 modulos en `calipso/` (server.py de 10.000 lineas es el centro), 143 archivos de tests
(suite: 2888 en ~3,5 min; 463 tests node del tablero), 776 commits, todo en `github.com/pedro-cmyks/calipso`
(privado). El e-reader como pantalla de Calipso vive aparte (`~/calipso-lector`).

## 2. El objetivo general

Que Calipso haga todo lo que Pedro hace con Claude Code, y mas: que se le pueda decir "disena un asset
para AvesCO" y que vaya, abra o instale Blender, lo haga, o encuentre quien lo hace y cuanto vale, le
muestre lo que salio, e itere. Y que sea de Pedro: con su voz, su criterio, su memoria, en sus
dispositivos, sin que nada salga de su maquina sin que el lo sepa.

## 3. Los objetivos especificos (los subproyectos) y su estado

| # | Subproyecto | Que es | Estado |
|---|---|---|---|
| 0 | La cabeza y la confianza | ruteo, memoria con procedencia, abismo, aduana, canarios, carga, economia, permisos, inbox | **HECHO** y desplegado (agosto-septiembre) |
| 1 | El goal que corre | `/goal` con propuesta, dale, golpes en sandbox + hook, juez, Pedro; pestana Goals y goalBar | **HECHO** (merge `e17743a` 09-14) y probado en produccion (4 rondas + 4 vueltas de capacidades, 09-15) |
| 2 | Las manos | MCP `calipso` desde el golpe, `correr_app`, imagenes del goal, propuesta automatica desde el chat; caso guia: un asset para AvesCO en Blender | **BRAINSTORM HECHO, spec borrador** (`specs/2026-09-15-manos-design.md`): falta el ok de Pedro, las lentes, el spec v2 y el plan |
| 3 | Los ojos | ver documentos y fotos, la pantalla, clicks (ultimo recurso) | pendiente (las imagenes del goal en el 2 son la version 0) |
| S-A | El modelo propio (la voz) | LoRA sobre Qwen con los chats de Pedro; primero `/redacta`; paso 0: exportar el historial de Claude | **PLANTEADO** como proyecto de sesion (`2026-09-15-proyectos-de-sesion.md`) |
| S-B | Calipso en varios dispositivos | red entre lo de Pedro (tailnet), la Ally como raiz de confianza, modelo de amenaza; consultado con tres IAs | **PLANTEADO** como proyecto de sesion (mismo doc) |
| R | Rutinas -> goals | lo periodico (reflect, catastro...) como goals con criterio y tope; `reflect` primero | pospuesto (ruling 15.13 del spec de goals) |

## 4. Que compone el proyecto (por donde entrar)

| Pieza | Archivos | Doc |
|---|---|---|
| Ruteo y modelos | `dispatch.py` (raiz), `calipso/capabilities.py`, `orchestrator.py` | `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md` seccion 1 |
| Chat y server | `calipso/server.py` (ws `/ws/chat`, `_decide`, `_subscription_invocation`, HELP_TEXT), `calipso/web/index.html` (PWA), `calipso/web/fabrica/` (tablero) | idem |
| Memoria | `memory.py`, `memoria_embed.py`, `memoria_procedencia.py`, `memoria_reindex.py` | `specs/2026-09-11-memoria-con-procedencia-design.md`, `specs/2026-09-12-memoria-embeddings-ollama-design.md` |
| Abismo (consulta honda) | `calipso/abismo/` | `specs/2026-09-07-abismo-consulta-design.md` |
| Aduana (lo que sale) | `aduana.py`, `web.py`, canario AST `test_aduana_canario.py` | `specs/2026-09-10-aduana-design.md` |
| Canarios (honestidad) | `canarios.py` | `specs/2026-09-11-canarios-design.md` |
| Carga (recursos) | `carga.py` (`python -m calipso.carga --esperar`) | `specs/2026-09-11-carga-design.md` |
| Economia y permisos | `calipso/economia/`, `calipso/permisos/`, `inbox.py`, `plantel/` | specs de agosto-septiembre (economia, motor de permisos, siembra) |
| Goals | `goals.py` (almacen), `goals_hook.py` (segunda capa), `goals_manos.py` (el golpe: sandbox, argv, parser, confinado), `goals_runner.py` (el bucle), `permisos/goal.py`, `github.py` (clon) | `specs/2026-09-13-goals-design.md` (v2 + adenda con 38 rulings), `plans/2026-09-13-goals.md`, `2026-09-13-cierre-goals/` (ledger, revision, probes) |
| Sesiones y aparatos | `sesiones.py`, `/api/aparatos` (el lector) | `specs/2026-09-07-capa-de-sesion-design.md` |

## 5. Lo que se trabajo (la cronologia corta)

- **Agosto**: la base (chat, ruteo, memoria, PWA, tablero), la economia de agentes, el motor de permisos,
  la revision de seguridad (el server solo en localhost, el token fuera de la URL, el escudo git), la capa
  de sesion y los aparatos.
- **09-07 a 09-10**: el abismo (consulta honda con contrato y letra medida), la memoria con procedencia,
  la aduana. Metodo asentado: brainstorm -> spec -> lentes adversarias (Claude + Codex) -> spec v2 con
  rulings -> plan -> SDD por task en un worktree -> cierre (revision final, una ola de fix) -> smoke real ->
  merge -> despliegue.
- **09-11 a 09-12**: los canarios, la carga (la Ally como maquina compartida con los juegos de Pedro), la
  memoria por Ollama (el server de 1,5 GB a 161 MB, torch fuera del venv).
- **09-12 a 09-14**: el norte de Pedro (manos y ojos), el brainstorm de la tarea con goal, el spec (v2 con
  14 rulings), el plan (7 tasks), el SDD, la revision final (4 areas + 2 lentes + Codex: el criterio corria
  fuera del sandbox como Pedro; se confino bajo bwrap), la ola de fix de 5 carriles (43 commits), el smoke
  con Claude Code real (6 escenarios), el merge `e17743a` y el despliegue.
- **09-15**: push a GitHub (72 commits) y probes en produccion con la suscripcion de Pedro: cuatro rondas
  de goals reales (ronda 4: 16/0, un goal cuesta ~40 s, 0,23 USD, 3 % de la ventana de 5 h) y cuatro
  vueltas del probe de capacidades del chat (un turno por capacidad + un goal que instala torch). Cada
  vuelta encontro algo real que se arreglo, mergeo y desplego antes de la siguiente (rulings 32-38 de la
  adenda). Lo mas importante: la RAM en cero de la Ally era `/tmp` (tmpfs = RAM) con 4,6 GB de temporales
  de tests filtrados, y cada turno de chat por suscripcion lanzaba `claude -p` con todos los MCP y
  herramientas de Pedro; las dos causas quedaron cerradas.

## 6. Donde estamos hoy (el estado del despliegue)

- `main` = GitHub = el server real de la Ally (puerto 8000, `~/.calipso`), reiniciado con `main` el 09-15.
- Los goals funcionan de punta a punta en produccion: propuesta (~12 s) -> inbox -> dale -> golpes bajo
  sandbox + hook -> criterio confinado -> revisor Codex -> `waiting cumplido` -> dale -> `complete` con la
  rama `goal/<id>` en el repo de origen; parar -> `retomar` por el inbox con nota; instalar en el venv del
  clon (pypi/npm en la red del sandbox); un host nuevo se pide y, si la tabla lo permite, se abre solo.
- El chat sabe que no tiene manos y propone el `/goal`; lo que pide manos no va al 7b ni arma equipo.
- Freno de emergencia: `CALIPSO_GOALS=off` en el entorno del server (y `CALIPSO_CARGA=off`,
  `CALIPSO_CANARIOS=off` para las otras piezas), reiniciando el proceso.
- Pendientes chicos que dejaron los probes: la identidad de Calipso no llega por la ruta Codex ("soy
  Codex"); el modelo local no sabe la fecha ni la hora; `/plan` tarda mas de 7 minutos; la carga no mira el
  swap lleno (zram) al decidir si carga el 7b; un goal que instale una app de sistema no se probo.
- Decisiones de Pedro pendientes (adenda del spec de goals): las unidades (iteraciones del CLI o turnos de
  modelo), una raiz de solo lectura, el revisor Codex envuelto en bwrap, las compuertas merge/push.

## 7. Hacia donde vamos ahora

1. **Subproyecto 2, las manos**: Pedro decidio el caso guia (un asset para AvesCO en Blender), el MCP
   `calipso` de solo lectura + preguntar, y que el chat proponga el `/goal` solo. El spec borrador esta en
   `specs/2026-09-15-manos-design.md`; la proxima sesion: su ok, las lentes (Claude + Codex), el spec v2, el
   plan y el SDD como siempre.
2. **Proyectos de sesion** (uno por sesion, con tiempo): (A) el modelo propio, empezando por exportar el
   historial de Claude y los chats como dataset y un LoRA de juguete medido con el banco del compositor;
   (B) la red de Calipso entre dispositivos, con el modelo de amenaza escrito y consultado con tres IAs.
   `2026-09-15-proyectos-de-sesion.md`.
3. Despues: los ojos (subproyecto 3) y las rutinas como goals.

## 8. Como retomar en diez minutos

```
cd /var/home/pedro/calipso && git status --short && git log --oneline -3      # main limpio y al dia
ss -ltn | grep ':8000 '                                                     # el server real arriba
CALIPSO_HOME=$(mktemp -d) .venv/bin/python -m calipso.carga                 # la carga de la maquina
du -sh /tmp; swapon --show                                                  # si la RAM anda corta: /tmp es RAM
nice -n 19 .venv/bin/python -m pytest -q --ignore=test_chat_live.py -p no:cacheprovider   # ~3,5 min, 2888
```

Para reiniciar el server real: `kill -TERM <pid>`, esperar que el 8000 cierre, y desde una shell con fnm
en el PATH (claude, codex, node): `setsid nohup .venv/bin/python calipso/server.py >> ~/.calipso/logs/server.out.log 2>&1 < /dev/null & disown`.
Para trabajar una rama: en un worktree (`.claude/worktrees/<rama>`) con `/var/home/pedro/calipso/.venv/bin/python`;
`main` se queda en el checkout principal porque el server real sirve desde ahi.

## 9. El metodo que funciono (y sus trampas)

Brainstorm con Pedro (una pregunta por vez, opciones) -> spec -> lentes adversarias (un workflow de
revisores Claude por lente + `codex exec -m gpt-5.5 -s read-only` con esquema) -> rulings numerados en el
spec v2 -> plan por un workflow (terreno verificado, escritor, dos criticos, corrector) -> SDD por task en
un worktree (implementador, revisor, hasta tres rondas de fix) -> cierre (revision final por areas, una ola
de fix, residuos por el controlador) -> smoke real -> merge --no-ff -> despliegue -> probes en produccion
con Pedro mirando. Trampas: seis revisores en paralelo tumban el limite de 5 h de la sesion (de a tres);
un agente puede quedar mudo horas (pararlo y retomar desde cache); `pkill -f` con un patron que matchea
la propia shell la mata (exit 144); `/tmp` es RAM; el server real nunca recibe turnos de un agente, solo de
Pedro o de un probe que Pedro pidio.
