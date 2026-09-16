---
nombre: calipso
tipo: proyecto
anillo: 1
familia: personal
estado: vivo
remoto: github.com/pedro-cmyks/calipso
visibilidad: privado
trabajo_vivo_en: main
actualizado: 2026-09-16
tags: [asistente-personal, agentes-autonomos, python-fastapi, ruteo-de-modelos, sandbox-bwrap]
---

# calipso

El asistente personal de Pedro corriendo en su propia maquina: un server Python (FastAPI) con una PWA de
chat y un tablero web. Pedro le habla siempre a Calipso y ella decide por dentro a que modelo manda cada
pedido -- Claude, Codex, DeepSeek o los Qwen locales por Ollama -- segun el tipo de tarea, la privacidad,
el costo y cuanta RAM queda libre en la Ally. Recuerda con procedencia (cada recuerdo dice de donde salio),
se autoaudita turno a turno, y desde septiembre corre "goals": tareas con criterio medible que se ejecutan
solas en un clon del repo dentro de un sandbox, con Pedro aprobando al final. No es un producto ni una
libreria: es de un usuario, en una maquina.

## Estado

Vivo, y no hay ambiguedad sobre donde. El ultimo commit de trabajo es `9ea10e8`, del 2026-09-15 10:32
("docs: el documento para volver..."); `main` es la rama por defecto, y no diverge de `origin/main`: no
esta ningun commit atras, y lo unico que tiene adelante son los commits de este dossier, todavia sin
push. El arbol esta limpio salvo tres documentos sin trackear de hoy (2026-09-16) en
`docs/superpowers/`. El server real esta arriba ahora mismo, escuchando en 127.0.0.1:8000,
y sirve desde este mismo checkout: por eso main se queda quieto aca y las ramas se trabajan en worktrees.

777 commits hasta ahi desde el primero (`b6f8fdb`, 2026-06-14), un solo autor. 21 ramas locales, de las
cuales la unica que no esta mergeada en main es `wip/sobre-obligatorio`: todas las demas son restos de
tandas ya cerradas con merge --no-ff. Lo detenido esta detenido por decision de Pedro (su limite semanal
de suscripcion), no por un problema del proyecto.

## Por donde entrar

- `docs/superpowers/2026-09-15-estado-y-ruta.md` -- **EMPEZAR ACA, es EL documento.** Nueve secciones: que
  es Calipso en una pagina, el objetivo, la tabla de subproyectos con su estado, que pieza vive en que
  archivo, la cronologia, el estado del despliegue, hacia donde va, "como retomar en diez minutos" con
  comandos copiables, y el metodo con sus trampas. Si se lee un solo archivo, es este.
- `dispatch.py` (raiz, 619 lineas) -- el cerebro de ruteo: `extract_features` saca el tipo, la complejidad,
  si es privado y si toca el repo, y de ahi sale a que boca va el pedido. Es el archivo mas rentable de
  leer por linea.
- `calipso/server.py` (10.057 lineas) -- el centro y el monolito: FastAPI, el websocket `/ws/chat`, la API
  entera. Entrar por `_decide` para seguir el flujo de un turno; no leerlo de corrido.

**No entrar por `AGENTS.md` ni por `CALIPSO.md`.** Los dos son lo primero que encuentra quien abre el repo
y los dos mienten. AGENTS.md sigue describiendo un checkout de Windows (`C:\Users\Pedro\Desktop\proycto`,
"no hay `origin` configurado en este checkout", "OS: Windows 11, PowerShell") y apunta como estado vivo al
documento del 09-09, que ya fue reemplazado; CALIPSO.md, LIBRARY.md, RUNBOOK.md, SETUP.md, SPEC.md y
DESIGN.md son de junio, anteriores a la migracion a Linux. Son historia, no referencia.

## Como se corre

El server real ya corre desde este checkout, asi que lo normal no es levantarlo sino no pisarlo. Para una
instalacion desde cero, `./calipso.sh` crea el venv si falta, instala las dependencias y llama a
`launch_calipso.py`, que levanta el server y abre el navegador. No lo verifique en esta sesion: no levante
nada ni corri la suite; los comandos salen de leer `calipso.sh` y la seccion 8 del documento de estado.

    ./calipso.sh                                                          # crea el venv si falta y arranca
    ss -ltn | grep ':8000 '                                               # ver si el server real ya esta arriba
    nice -n 19 .venv/bin/python -m pytest -q --ignore=test_chat_live.py -p no:cacheprovider

La suite son 143 archivos `test_*.py` en la raiz mas 22 suites `node --test` del tablero; el documento de
estado la mide en unos 2.888 tests y ~3,5 minutos (no lo verifique). Para reiniciar el server real y para
trabajar una rama en worktree, los comandos exactos estan en la seccion 8 de
`docs/superpowers/2026-09-15-estado-y-ruta.md`.

## Lo que le falta

- Un manifiesto de dependencias de Python (minutos). No hay `requirements.txt` ni `pyproject.toml`
  (verificado): la unica lista real es una linea de `pip install` dentro de `calipso.sh`, sin versiones
  salvo `tokenizers==0.22.2`, y sin registrar que torch NO debe entrar al venv. Hoy funciona solo porque
  el `.venv` existe en este disco.
- Commitear o descartar los tres documentos sin trackear de hoy (minutos). `2026-09-16-terreno-manos.md`
  es el insumo del proximo paso del subproyecto 2 y existe en un solo disco.
- Mover a `docs/historia/` los .md de junio de la raiz y borrar `Calipso.bat` / `Calipso.ps1` (minutos).
  Describen un producto que ya no es este: el "Goal Mode" de SPEC.md no es el goal que se implemento.
- Podar las ~19 ramas locales ya mergeadas (minutos), y decidir que pasa con `wip/sobre-obligatorio`, la
  unica con contenido no mergeado.
- Decidir que hacer con `experimentos/fixtures/memoria_smoke_home/` (horas). Ver "Cuidado con".
- Alguna forma de correr la suite sola, aunque sea un hook local (horas). No hay `.github/` (verificado).
- Un mapa de `server.py`, o empezar a partirlo (dias). 10.057 lineas concentran el chat, el ruteo y la API.
- Cerrar los pendientes chicos que dejaron los probes del 09-15, anotados en la seccion 6 del documento de
  estado (dias). Estan escritos pero fuera del codigo: son los que se pierden primero.

## Relaciones

- [[AvesCO]] es el caso guia del subproyecto 2 de Calipso, "las manos": el objetivo declarado es pedirle a
  Calipso un asset 3D para AvesCO y que ella abra Blender y lo haga. Todavia no hay una linea de codigo que
  los conecte; el vinculo vive en `docs/superpowers/specs/2026-09-15-manos-design.md` y en el documento de
  estado.
- [[Observatory-Global]], [[noaa-proyecto]] y [[cam-crm-vincere-demo]] aparecen nombrados en `AGENTS.md`
  como los repos de la cuenta de GitHub que Calipso ve por su conector, y alguno se usa como repo de
  ejemplo en los tests. Es relacion de inventario, no dependencia de codigo.
- [[CAM-CRM-Vincere]], [[CAM-CRM-Vincere-collector-build]] y [[research-court]] no tienen ninguna relacion
  tecnica con este repo: son proyectos de Pedro que Calipso, hoy, ni conoce.
- Fuera de los ocho repos, la relacion mas fuerte es con `~/calipso-lector` (el e-reader Musnap Neo C como
  pantalla de Calipso, que se conecta por `/api/aparatos` y la capa de sesion) y con Claude Code y Codex
  CLI, que no son repos de Pedro pero son dependencia dura: Calipso los invoca como subprocesos y el propio
  repo se desarrolla con ellos.

## Cuidado con

- **Datos personales reales versionados.** `experimentos/fixtures/memoria_smoke_home/` es la copia de un
  CALIPSO_HOME real: incluye `global/core/pedro-perfil.md`, `global/core/pedro-cronologia.md` y bases
  `chroma.sqlite3` con turnos de chat reales que se leen en claro. Mientras el repo sea privado es
  aceptable; es la pieza que lo vuelve no-publicable sin una limpieza previa.
- **Este repo ejecuta comandos arbitrarios en la maquina de Pedro.** Esta tratado en serio (bwrap, hook
  fail-closed, permisos con compuertas, aduana, el freno `CALIPSO_GOALS=off`, el server solo en localhost,
  tests de seguridad dedicados), pero quien toque `calipso/goals_hook.py` o `calipso/goals_manos.py` tiene
  que entender esas capas antes de mover una linea.
- **AGENTS.md es informacion activamente falsa** sobre el estado operativo, y es el primer archivo que un
  lector nuevo abre porque no hay README. Ver "Por donde entrar".
- **Secretos: no hay ninguno versionado**, verificado. Las coincidencias de patrones que aparecen en el
  arbol son placeholders de los tests de redaccion y de la aduana -- fixtures que prueban que Calipso TAPA
  credenciales, no credenciales. Las de verdad viven en `~/.calipso`, fuera del repo, y hay un test que
  fija que nacen y se re-cierran en 0600.
- **El server real sirve desde este checkout.** Cambiar de rama aca le cambia el codigo al asistente que
  esta corriendo. Las ramas se trabajan en worktrees; main se queda en la raiz.
- **Dependencias sin pinear** (ver "Lo que le falta"): chromadb y litellm rompen compatibilidad seguido, y
  no hay archivo que diga con que versiones funciono.
- **Lastre en el arbol**: los planes de `docs/superpowers/plans/` son transcripciones de trabajo de
  agentes, no documentos para leer -- el de goals pesa 526 KB. Inflan las busquedas.
- **`src-tauri/` (cascara de escritorio en Rust) esta versionada desde el 2026-08-31 y sin tocar desde
  entonces**, y ningun documento de estado la menciona. Es la pieza mas cercana a muerta del repo.
