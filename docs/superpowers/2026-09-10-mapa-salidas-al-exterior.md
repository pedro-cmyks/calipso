# Por donde sale Calipso al exterior hoy, y con que compuerta (2026-09-10)

Mapa del terreno para el brainstorm de la aduana (la idea de Pedro del 2026-09-10: "un departamento que
sea como una aduana, la unica puerta al internet"; despues afinada: "los modelos por suscripcion y por API
si deben poder ver todos los archivos; los queries al internet si medirlos"). Levantado por cinco lectores
en paralelo sobre main `446d1be`, un critico de completitud, y DIEZ afirmaciones clave refutadas por dos
lentes independientes: Claude (lectura literal) y Codex headless `gpt-5.5` (caminos alternativos), veinte
veredictos. Ninguna afirmacion cayo; todas las precisiones que dejaron estan incorporadas abajo. Todo es
lectura de codigo (archivo:linea de hoy); nada se ejecuto; `~/.calipso` no se leyo salvo lo que ya se sabia.

## 1. Lo que hay que saber en diez lineas

1. **No hay aduana.** Hay UNA compuerta de contenido buena, el juez de privacidad de dos capas, y corre en un
   solo camino: el gesto `/nube` (server.py:3462-3467; privacidad/nube.py:11; y sobre el bloque del abismo
   en viaje.py:59, tambien solo con /nube). Todo lo demas sale por donde cada modulo quiso.
2. **Los modelos de nube ya ven todo (con una asimetria).** En cualquier turno que el router mande a
   suscripcion (por puntaje, sin gesto: capabilities.choose, config.py:18 `subscription_first`) o con
   `/claude` `/codex`, viaja hasta 12 mensajes de historial + el mensaje crudo, y a `claude` ademas el
   system entero de `_build_context` (CALIPSO.md, memoria nucleo, hasta 4 recuerdos, economia, catastro,
   adjuntos, material web) por `--append-system-prompt-file` (server.py:2749-2803, 2890-2938, 3573,
   3597-3603). **A `codex` el system NO viaja:** la plantilla de config.py:33 solo tiene `{prompt}` y
   `{output}`, y `system_prompt` se escribe unicamente en la rama de claude (2929-2938 vs 2939-2949). Codex
   recibe historial + "Pedro: <msg>" y, como corre con cwd=ROOT, lee AGENTS.md del repo por su cuenta
   (inferido del CLI). Coincide con la decision de Pedro de hoy ("los modelos ven todo"), salvo esa asimetria.
3. **El bloque del abismo sube a ese CLI sin anillos ni juez** cuando el turno es suscripcion sin /nube:
   `destino` se deriva del gesto y no de la ruta real (server.py:3573, 3650, 3737) y viaje.py:51-53 deja
   pasar todo con destino='local', anillo 3 incluido (core, cronologia, consolidado personal; fuentes.py:120-133).
   **Contradice la invariante escrita del spec del abismo (:96-110, "anillo 3 jamas, ni tapado").** Las dos
   lentes lo confirman tal cual. Es una decision de Pedro: o vale "los modelos ven todo" o vale el anillo 3.
4. **La fabrica no tiene manos ni boca.** El jefe piensa contra Ollama localhost (server.py:6965-7003;
   `base_url` es configurable por `~/.calipso/config.json` y `PUT /api/config`, y nadie exige loopback),
   `trabajar` es un no-op declarado (7090-7094), `proponer`/`pedir` escriben una linea en bus.jsonl, y
   financiar (unico llamador: server.py:5624, un POST de Pedro) mueve monedas a `trabajo:<id>` que ningun
   ejecutor consume (solo contabilidad: cargos y liquidacion por gasto/plazo, bus.py:754-827). No hay
   frontera de ejecucion (confirmado en codigo 7017-7034 y en docs). No hay nada que sandboxear porque no
   ejecuta nada.
5. **Lo unico que ejecuta de verdad son los CLIs de suscripcion**, sin sandbox, contenedor, usuario aparte
   ni lista de herramientas de parte de Calipso: heredan `os.environ` menos 4 variables, corren como Pedro
   con cwd=ROOT (2955-2963, 2988-2990, 3026-3028). Lo que pueden hacer lo decide `~/.claude/settings.local.json`
   (85 reglas Bash, incluidas `Bash(bash)` y `Bash(ssh *)`, y dos entradas curl con el token de Calipso en
   claro) y la config de Codex. `memory.reflect` y `plugins.install` tambien lanzan `claude -p`, sin el
   escudo de git (memory.py:246-259; plugins.py:88-99).
6. **Salidas a internet que no son modelos, y ninguna pasa por ninguna compuerta de contenido:** busqueda
   en DuckDuckGo con el mensaje crudo por heuristica (regex `hoy`, `precio`, URL...; server.py:3554-3559,
   web.py:25-30) + GET a 2 paginas + Chromium si falta texto (browser.py:159-181, que ademas puede instalar
   Chromium solo: deps.py:88-95); `gh` para fork/pr/clone con `confirm:true` en el body (server.py:1688-1716);
   `npm install -g` desde el modal de updates (4404-4422); pip + playwright por catalogo (4337-4346);
   screenshot con Chromium a URL publica (4360-4370).
7. **Canales laterales a la nube que se disparan solos en un turno normal** (unico interruptor: /nube):
   borrador `claude -p` sonnet con el ARCHIVO ENTERO por regex de intencion de edicion (3545-3548,
   1344-1386, developer.py:225-245); vision por SDK de Anthropic con la imagen si hay `ANTHROPIC_API_KEY`
   (3580-3583, attachments.py:246-283); equipo dinamico por complejidad, sin aprobacion del plan, con el
   system completo por agente (2299-2320, orchestrator.py:154-166; se frena tambien por `private`, /fast y
   `/plan` `/team` lo hacen revisable).
8. **Un proceso desatendido que sale a la nube:** la rutina `reflect` manda a `claude -p` los 20 episodios
   mas recientes del ambito de memoria del PROYECTO activo (memory.py:238), sin juez. Detalle que importa:
   los turnos del chat de hoy se guardan en el ambito GLOBAL (server.py:4024-4026), que reflect NO lee
   mientras haya proyecto (siempre lo hay); lo que manda son los episodios de metas y los turnos archivados
   bajo el proyecto antes del 2026-08-31. Aun asi, sin juez, y con el texto crudo de los /nube guardado en
   global (`user_msg`, no `chat_msg`) para el dia que alguien cambie el ambito.
   Nace apagada (routines.py:81, 115); se dispara por boton, `POST /api/reflect`, `POST /api/routines/{id}/run`
   o el ticker si se enciende. La rutina `departamento` es Ollama local y no existe hasta sembrar.
9. **Salidas pasivas, sin datos de Pedro pero sin declarar:** huggingface.co en CADA arranque (`Memory()` a
   nivel de modulo, server.py:2004 -> memory.py:161, `SentenceTransformer` sin `local_files_only`: 1 GET
   de metadatos + 1 HEAD por archivo aunque el cache este completo; interruptor `HF_HUB_OFFLINE=1`, hoy no
   puesto) y lo mismo con whisper en el primer `/api/transcribe`; `registry.npmjs.org` en cada carga de la
   PWA `/` (index.html:2680 -> discovery.py:92-124, solo si `claude`/`codex` estan instalados); Google
   Fonts y Monaco entero desde cdn.jsdelivr.net sin CSP (index.html:13-15, 577, 665); probes `claude/codex
   --version` y `auth status` al arrancar. `/fabrica` no carga nada externo. Ollama y LiteLLM son locales
   por CONFIG, no por codigo: nadie exige loopback en `base_url`.
10. **La economia no frena salidas:** `techo_api_ciclo_mm` y el cristal se aplican POST-HOC en `_cobrar_turno`
    (mercado.py:232-235; pagador.py:126-155); lo unico pre-llamada es el presupuesto USD mensual que apaga
    el backend `api` (connectors.py:16-24). El motor de permisos tiene un solo consumidor, plata
    (server.py:6106; 6764/6786/6866); archivos, comandos y CLIs se protegen por auth + allowlist + `_safe`.

## 2. Tabla salida x compuerta

| salida | que viaja | quien dispara | compuerta de contenido | quien la mide hoy |
|---|---|---|---|---|
| chat -> CLI suscripcion (claude/codex) | system entero + 12 msgs + mensaje | router por puntaje, `/claude` `/codex`, reentrada del abismo, fallback claude<->codex | regex `private` (dispatch.py:124-126) apaga la nube; nada mas | telemetria + `_cobrar_turno` (cristal) |
| chat `/nube` -> CLI suscripcion | system minimo + mensaje TAPADO, sin historial; bloque del abismo tapado por anillos+juez | gesto de Pedro | juez de dos capas, fallo cerrado | idem |
| chat `/api` -> LiteLLM -> proveedor | system entero + historial (crudo salvo /nube) | gesto `/api` | presupuesto USD mensual (pre); techo API (post) | costs.jsonl + economia |
| borrador de codigo `claude -p` sonnet | archivo entero + pedido + meta activa | regex de intencion de edicion, automatico | saltado solo con /nube | nada |
| vision SDK Anthropic | imagen + mensaje | adjunto con imagen si hay ANTHROPIC_API_KEY | saltado solo con /nube | nada |
| equipo dinamico | system completo por agente | complejidad, `/plan` `/team` | `private`, /fast; API solo con `/api` | telemetria |
| busqueda web DuckDuckGo + GET paginas + Chromium | mensaje crudo (la query) | regex `needs_web`, `/web`, automatico | saltado solo con /nube; `exigir_url_publica` en screenshot, NO en render | nada |
| rutina `reflect` -> `claude -p` | 20 episodios del proyecto | rutina (nace apagada), boton, endpoint | ninguna | nada |
| `gh` fork/pr/clone, `gh api` | nombres de repo, ramas, el PR | POST con `confirm:true`; pantallas de github | argv fijo + escudo git; sin motor | nada |
| `npm install -g`, pip, `playwright install` | nada de Pedro | modal de updates; catalogo; auto-install de Chromium | auth_guard | nada |
| HF Hub, npm registry, CDNs, probes | nada de Pedro (UA, nombres de paquete) | arranque, cada carga de `/` | ninguna | nada |
| Ollama, LiteLLM | todo el turno | cada turno | n/a (local por config) | telemetria |

## 3. Lo que ya esta decidido y escrito (para no redescubrirlo)

- **Frontera de salida UNICA, decidida y NO construida:** "toda salida al mundo exterior (correo,
  publicacion, plataforma, gasto real) pasa por un unico modulo de frontera; no existen rutas de salida por
  fuera de el" (spec economia 2026-08-24 :19-20, :155). El inventario del 08-26 (:30-33) y lo-que-falta del
  08-27 (:424-428) la listan como faltante: "no hay un solo lugar donde auditar que sale".
- "Un jefe no habla con el mundo" (plantel :18, :141); `trabajar` es no-op "es la frontera de salida, y es
  otro spec" (mesa :53-54); no hay frontera de ejecucion, Pedro juzga (PvP :102).
- "publicar" quedo como pregunta explicita a Pedro en tres documentos y de facto fuera del padron cerrado
  (proyectos-y-plata :891-896). La aduana NO la contesta: publicar, correo, contacto y gasto real son la
  mitad de la frontera que FIRMA (invariante 5 del 08-24, compuertas obligatorias), del lado del motor de
  permisos; la aduana es la mitad que MIDE.
- Nube: local por default, `/nube` tapada, credencial jamas, API paga jamas sin gesto (ruteo 09-02 :247-253).
- Abismo: anillos 1-2 tapados a la nube, anillo 3 jamas (abismo :96-110). Contradicho por el codigo en
  suscripcion sin /nube (punto 3 de arriba).
- Contenido de internet: procedencia marcada (`origen` en {pedro, repo, bandeja, web}; sin origen = no
  confiable); con documento no confiable adentro no hay permisos guardados (ojos-y-manos :957-1046).
- Red: bind 127.0.0.1; remoto solo Tailscale; nunca internet (AGENTS :241-243). Bloqueante vigente de abrir
  el host: la escalada PUT `/api/file` + `commands/run` (revision 09-07 :82; estado 09-09 :129-141).

## 4. Hallazgos laterales del mapa (no son la aduana, pero quedaron a la vista)

- `.claude/launch.json:7` arranca uvicorn con `--host 0.0.0.0`: el default 127.0.0.1 solo rige bajo
  `__main__` (server.py:180, 7967). Esa configuracion abre el server a toda interfaz sin el aviso de arranque.
- El prompt > 7000 chars se vuelca a un `.prompt.md` DENTRO de ROOT (server.py:2916-2919), no en
  `~/.calipso/tmp` 0600 como decidio el spec de ojos-y-manos (:866-867). Se borra en `finally`, pero mientras
  vive el CLI con cwd=ROOT lo ve como untracked.
- `/api/connectors/{name}/{install,login}`, `/api/subscriptions/{client}/install` y `/login` usan
  `subprocess.CREATE_NEW_CONSOLE` (server.py:1952, 1969, 1989): solo existe en Windows; en la Ally dan 500
  antes de ejecutar nada (inferido por semantica de Python, no ejecutado).
- No existe ninguna ruta `/api/lectura/*`: el alcance `lector` de sesiones.py:83 apunta a nada (fail-closed).
- El handshake websocket no chequea `Origin` (server.py:615-660); que una pagina ajena pueda abrir
  `/ws/chat` desde el navegador de Pedro depende del SameSite de la cookie (no verificado).
- `browser.render` no exige URL publica y en su reintento instala Chromium solo (browser.py:159-181).
- Sin CSP en ninguna capa; el CSP de `src-tauri/tauri.conf.json` no gobierna la pagina remota que carga.
- La meta de prueba `goal_ff4b5cd203f0` (junio) sigue ACTIVA en el home real y entra en cada turno como
  "Meta activa"; el recall de "hola" trae cuatro recuerdos identicos "-q" con acentos rotos. Ruido en cada
  turno del 7b (visto en la medicion del abismo del mismo dia).

## 5. Metodo

Cinco lectores (salidas en operacion, que ejecuta la fabrica, compuertas, decisiones en specs, salidas
pasivas y del navegador) + critico de completitud + 10 afirmaciones clave x 2 refutadores (Claude lectura
literal; Codex `gpt-5.5` headless `codex exec -s read-only --output-schema`, ~85k tokens por veredicto).
Los 20 veredictos marcaron "impreciso" en 18 (siempre "correcta en lo central, falta un caso o una linea")
y "correcta tal cual" en 2 (la fuga del anillo 3, por ambas lentes). Crudo: `experimentos/` no; los
veredictos de Codex quedaron en el scratchpad de la sesion. Esta es la primera vez que el proyecto usa
Codex headless como lente adversaria en un cierre, a pedido de Pedro ("aqui y alla haz llamados a ChatGPT
con headless"): el modelo `astra` no esta disponible con cuenta ChatGPT (400), `gpt-5.5` si.
