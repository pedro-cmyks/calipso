# Calipso: estado del proyecto y como seguimos (2026-09-09)

Escrito al cerrar la sesion del 2026-09-08 (la mas larga del proyecto: la capa de sesion y el abismo 1b
aterrizaron en main el mismo dia), para que Pedro pueda parar semanas y retomar sin releer nada mas.
Todo lo que dice esta verificado contra el codigo de main `c38dadb` y contra la maquina de Pedro (la Ally).
Cuando este documento y AGENTS.md discrepen, manda este: AGENTS.md esta desactualizado (habla de Windows y
no nombra la economia, el plantel, el mapa, el abismo, la privacidad, el compositor ni las sesiones).

## 0. Lo primero al volver (diez minutos)

1. Leer este documento entero. Despues, si vas a tocar un frente, su spec y su plan (seccion 8).
2. ~~Reiniciar el server real con main~~ **HECHO el 2026-09-10** (corre main `446d1be`+; log en
   `~/.calipso/logs/server.out.log`). Si esta apagado: `cd ~/calipso && .venv/bin/python calipso/server.py`.
3. ~~Rotar el token~~ **HECHO el 2026-09-10** (borrado y regenerado en 0600; el navegador y la PWA piden TOTP una vez).
4. ~~Decidir h05~~ **DECIDIDO el 2026-09-10: opcion (a), medido y aterrizado** (seccion 5.1). Lo que sigue es
   la aduana (seccion 6, item 3) y su plan.
5. Decir "sigamos con calipso" a una sesion nueva: la memoria del agente apunta aca. Adenda del 2026-09-10 al
   final de este documento (seccion 9).

## 1. Que es Calipso hoy, en una pagina

Calipso es el asistente personal de Pedro: un server local en la Ally (FastAPI, Python) que coordina modelos
(Ollama local con qwen2.5:7b, las suscripciones de Claude y Codex por sus CLIs, la API paga solo con gesto
explicito) sin exponer que backend contesta, con memoria persistente, verificacion real, y una economia de
agentes que todavia no se sembro. Pedro le habla en espanol; Calipso habla como Calipso.

**Las caras.** La PWA vieja en `/` (editor Monaco + chat + drawers de proyecto, memoria, git, plugins); la
consola `/fabrica` (tres pestanas: Chat, Mapa, Inbox; la mesa con cinco sub-pestanas: Todo, Decidir, Plata,
Permisos, Aparatos); un shell Tauri que levanta uvicorn y abre la PWA (compila; navega con el token). No hay
cara de terminal todavia (esta en la cola).

**El chat.** Un WebSocket (`/ws/chat`) con ruteo por turno (`_decide`): local por defecto, suscripcion si
conviene, API paga jamas sin `/api`. Gestos: `/nube` (manda un prompt privado a la nube TAPADO por el juez de
privacidad), `/local`, `/api`, `/claude`, `/codex`, `/model`, `/redacta` `/otra` `/mia` (el compositor escribe
como Pedro y aprende de sus ediciones), `/plan` `/team` (orquestador de agentes dinamicos), `/web`, `/fast`
`/think` `/ultrathink`, `/stop`. Steering: un mensaje a mitad de respuesta la interrumpe o la redirige. Goals:
metas con evidencia automatica. Dos marcas in-band que el modelo emite y Pedro nunca ve: `⟦foco:edificio⟧`
(mueve la camara del mapa) y `⟦abismo:fuente pregunta⟧` (la consulta al abismo, nueva).

**Los subsistemas y su estado real:**

| Subsistema | Que hace | Estado |
|---|---|---|
| memoria (`memory.py`, `chronology.py`, `librarian.py`) | core markdown + Chroma por ambito global/proyecto/departamento; recall en cada turno; cronologia; inbox de propuestas | cableado y corriendo |
| abismo (`calipso/abismo/`) | el regimen del medio del contexto: Calipso pide un dato a mitad de respuesta (memoria, chats viejos, detalle de un repo), pesca local, en /nube viaja tapado por anillos + juez, y sigue en la misma burbuja | cableado al chat vivo (1b, 2026-09-08); con salvedad h05 (seccion 5) |
| privacidad (`calipso/privacidad/`) | juez de dos capas (detector determinista de credenciales + 7b local para lenguaje humano), redaccion con marcadores estables por conversacion, compuerta `/nube` | cableado; el juez corre solo en el camino /nube |
| compositor (`calipso/compositor/`) | escribe COMO Pedro (`/redacta`), aprende de lo que Pedro entrega con `/mia`; empieza neutro | cableado (MVP local) |
| sesiones (`calipso/sesiones.py`) | identidad de aparato: golpear la puerta, aprobar desde la Ally, canjear una cookie con alcance (lector / tablero / navegador), renovacion por uso, revocacion que corta ws vivos | cableado (2026-09-08); el tipo `lector` apunta a `/api/lectura/`, que no existe todavia |
| economia (`calipso/economia/`) | libro append-only, tres divisas (moneda, PT, cristal), departamentos con billetera, bus/mesa, cierre semanal, siembra guiada de 7 pasos | construido y probado, APAGADO: `~/.calipso/economia` no existe |
| plantel (`calipso/plantel/`) | el jefe de cada departamento (mirar, decidir, actuar), gramatica de proponer, reacciones de Pedro, standing de promesas | cableado; sin libro que mirar hasta sembrar |
| permisos (`calipso/permisos/`) | el motor que pregunta antes de lo que no se deshace; NUNCA sobre credenciales; inbox de solicitudes | cableado a acunar y a la UI; terminal/archivos/apps son consumidores futuros |
| mapa (`calipso/mapa/`, `web/fabrica/`) | la ciudad derivada del libro, el pulso efimero, el foco | cableado; muestra "todavia no hay fabrica" hasta sembrar |
| catastro, routines, consumo, telemetry, jobs, backup, github, web, attachments | indice de proyectos; ticker de rutinas (solo `catastro` y `consumo` nacen encendidas); probe pasivo del consumo de suscripciones; ledger; procesos largos; zip local sin credenciales; `gh`; busqueda y navegador real; adjuntos | cableados |
| lector (repo aparte `~/calipso-lector`) | el e-reader Musnap Neo C como cara de Calipso: plugin de KOReader + APK tablero | disenado (BRIEF), sin codigo; bloqueado por `/api/lectura/*` y Tailscale |

**Numeros:** 139 rutas HTTP/WS en `server.py` (7.7k lineas; `ws_chat` ~650); 113 archivos `test_*.py` (91 pytest,
22 scripts con `main()`), 18 archivos de tests de cliente; ultima corrida completa: 1470 passed en pytest,
412 en node. Suite en ~95 s.

## 2. Como se corre y como se entra

- Server: `python calipso/server.py` (puerto 8000 fijo; `CALIPSO_HOST` default `127.0.0.1`; abrirlo hay que
  pedirlo y solo a la IP de Tailscale) o `uvicorn calipso.server:app --host 127.0.0.1 --port 8000`.
  `launch_calipso.py` levanta el server si no corre y abre el navegador; `calipso.sh` prepara el venv.
- Entrar: `/login` con el codigo TOTP (Microsoft/Google Authenticator). Desde la Ally planta la cookie
  `calipso_token`; desde otro aparato crea una sesion `navegador`. `/setup` (el QR) solo desde loopback, con
  `?token=` y mientras no exista `~/.calipso/totp_secret`. Los aparatos (lector, APK) entran golpeando la
  puerta: `POST /api/aparatos/golpear` -> vos aprobas en /fabrica > Aparatos -> `canjear` -> cookie `calipso_sesion`.
- Variables: `CALIPSO_HOME` (todo el estado; default `~/.calipso`), `CALIPSO_TOKEN`, `CALIPSO_HOST`,
  `CALIPSO_ROOT` (raiz de archivos servidos), `CALIPSO_NO_TOTP` (solo loopback, solo desarrollo),
  `ABISMO_BLOQUE_MAX` (2000).
- Tests: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py` (el conftest de la raiz aisla el home REAL:
  solo para pytest; cualquier script suelto que importe calipso tiene que exportar `CALIPSO_HOME` a un temporal
  ANTES). Cliente: `node --test` desde `calipso/web/fabrica/` (Node en
  `~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node`, el directorio como cwd).
  `test_chat_live.py` es una sonda manual contra un server vivo.
- Smokes en vivo: siempre con server desechable (home temporal + token aleatorio + puerto 877x), nunca el real.
  Recetas en `docs/superpowers/2026-09-08-smoke-capa-de-sesion.md` y `2026-09-08-smoke-abismo-1b.md`.

## 3. Lo que aterrizo en las ultimas sesiones (todo en main, pusheado)

| Fecha | Que | Commit | Verificado por |
|---|---|---|---|
| 2026-09-03 | siembra guiada, `no_siempre` de la mesa (el jefe aprende), PvP (Pedro juzga entregas), compositor que aprende de `/mia` | varios | suites + smoke del compositor |
| 2026-09-07 | abismo 1a (paquete puro + banco + porton) y porton v2 PASA con el contrato "dura" | `0617dc9`, `8437b07` | 168 llamadas reales al 7b; N=6 |
| 2026-09-07 | revision de seguridad (5 lentes) y remediacion puntos 1, 2 y 3a (git blindado, techo de proyectos, filtro de token en logs, freno de fuerza bruta en /login, `?token=` solo local) | `977a824`, `13b1bd7`, `5e825b3` | canarios reales + rondas adversarias |
| 2026-09-08 | **capa de sesion** (identidad de aparato) | `b671ba8` | 1374 tests, smoke 11/11 con UI en Chromium, 200 sondas adversarias |
| 2026-09-08 | **abismo 1b** (la consulta cableada al chat vivo, incluido /nube con viaje) | `c38dadb` | 1470 tests, smoke con Ollama real y `claude` de suscripcion, 45 sondas adversarias, ola de fix de 8 commits |

Cada cierre de rama dejo su carpeta con la revision final, las tres lentes adversarias, la ola de fix y el
ledger con TODOS los rulings que el agente tomo en nombre de Pedro: `docs/superpowers/2026-09-08-cierre-capa-de-sesion/`
y `docs/superpowers/2026-09-08-cierre-abismo-1b/`. Los README de ambas empiezan por "lo que queda para Pedro".

## 4. El estado real del despliegue (la Ally, 2026-09-09)

- El server real esta APAGADO. La ultima vez que corrio fue con codigo anterior a las dos ramas de ayer.
- `~/.calipso/token` es del 7 de septiembre: NO se roto tras la capa de sesion (paso de despliegue pendiente).
  `totp_secret` es de junio y sigue valiendo.
- `~/.calipso/economia` NO existe: la economia no esta sembrada; el mapa dice "todavia no hay fabrica"; los
  jefes no tienen libro. Sembrar es un acto de Pedro (irreversible: el padron no tiene alta ni baja despues).
- Rutinas: solo `catastro` y `consumo` nacen encendidas; `reflect`, `learn`, `backup` y `cierre` estan apagadas.
  El ticker late solo con el server prendido.
- El probe de consumo viene leyendo los JSONL de `claude`/`codex` (10 MB en `consumo_claude.jsonl`).
- El BRIEF del lector (`~/calipso-lector/BRIEF.md`, fuera de git) esta al dia con la capa de sesion.

## 5. Decisiones que solo Pedro puede tomar

1. **h05, la decision de la seccion 12 del spec del abismo (la que manda).** El 7b local no emite la marca
   del abismo por su cuenta con el system de PRODUCCION: cero marcas en seis turnos naturales del smoke, y en
   uno confabulo. El porton v2 del dia 7 midio el contrato SOLO (junto a una identidad de dos renglones);
   dentro del system real de ocho secciones no pasa en ninguna posicion (240 llamadas reales, N=2; evidencia en
   `experimentos/consulta_abismo_posicion*.{py,md,jsonl}`). Ademas la metrica del porton contaba como legible
   la copia literal del molde (22 de 34 marcas del control). Con marca explicita en el mensaje la pesca
   funciona de punta a punta; en /nube por suscripcion el modelo de nube consulta solo. Nada se rompe mientras
   tanto (sin marca el filtro es transparente), pero el contrato suma ~600 chars al system de cada turno local.
   Opciones: (a) podar el system de produccion y re-medir el porton SOBRE ese system, excluyendo la copia
   literal; (b) cablear la consulta solo en rutas grandes (suscripcion/API) y sacar el contrato del system
   local; (c) aceptar el regimen actual hasta la rebanada 2 (el fondo: el disco del Mac), que cambia las fuentes.
2. **h04, una politica que el fix del cierre decidio y el spec no escribe:** en local, la fuente `chats` no
   pesca la ventana de 12 mensajes que el modelo ya tiene ni la pregunta actual, pero SI los mensajes mas
   viejos del mismo chat; en /nube el chat activo queda fuera ENTERO (para que un turno local previo no viaje
   tapado por la puerta de atras). Confirmar o cambiar.
3. **Capa de sesion:** el tope absoluto de 180 dias y que tablero/lector no revoquen van con los defaults del
   spec; y la pregunta abierta: el tablero (la APK del lector) ve la fabrica y firma la mesa, pero hoy NO
   puede PARAR la fabrica. Es una linea en la tabla `ALCANCES` si lo queres.
4. **La siembra de la economia:** todo listo desde el 3 de septiembre (helper guiado ensayado); faltan los
   montos y disparar `POST /api/economia/sembrar-guiado` con la frase-token, con el server prendido un rato
   antes para que el probe mida la capacidad real. Ver `docs/superpowers/specs/2026-09-03-siembra-guiada-design.md`.
5. **Abrir CALIPSO_HOST** (Tailscale) sigue bloqueado por la escalada PUT `/api/file` + `commands/run` para
   una sesion navegador remota (seccion 6, item 2).

## 6. Lo que falta, en orden (la ruta actualizada)

Los items 1 y 2 de la ruta del 2026-09-07 (capa de sesion, abismo 1b) estan hechos. Lo abierto:

1. **Despliegue de lo que ya esta en main:** reiniciar el server con main; rotar el token. (Pedro, diez minutos.)
2. **Seguridad, lo que queda del informe del 7:** la escalada PUT `/api/file` + `commands/run` (una sesion
   navegador remota puede escribir en el repo de Calipso y correr comandos: es el ultimo bloqueante real de
   abrir el host; fix propio con el motor de permisos sobre escrituras o verificacion del runner; analisis en
   la adenda del punto 2 de `2026-09-07-revision-seguridad.md`); raices explicitas del catastro (hoy la raiz por
   defecto es el home); Tauri navega con `?token=` (Rust); el bind operacional solo-Tailscale. Sin spec.
3. **El abismo segun h05:** si (a), un ciclo corto de medicion sobre el system real (banco v2 con la
   exclusion de la copia literal, 4-6 variantes del system podado); si (b), un plan chico que apague el contrato
   en local y lo deje en suscripcion/API; si (c), nada.
4. **Abismo, rebanadas 2-4** (decisiones madre tomadas, sin spec): (2) el fondo: **el disco de 2 TB conectado al
   Mac de Pedro, no OneDrive** (decision del 2026-09-09: "mejor eso que una cosa de Microsoft"). El Mac va a ser un
   nodo de la red de Calipso, y esa red no esta disenada: el brainstorm de la rebanada 2 empieza por ahi (como llega
   la Ally al disco: nodo de Calipso en el Mac por Tailscale, mount o rclone contra el Mac; si hace falta cifrado en un
   disco propio; que tipo de aparato es un nodo). Siguen valiendo: local-primero, indice local de lo hundido, la
   consulta pesca, anillos sobre lo existente, la base viva jamas sobre un mount;
   (3) la escena del mapa (la boca en el centro de la ciudad, cambio de escena, profundidad = anillos); (4) los
   otros habitantes: los jefes consultan en su tic con corte seguro, y el lector, que trae los endpoints
   `/api/lectura/*` (pregunta, respuesta, presencia). Cada una: brainstorm -> spec -> plan.
5. **Sembrar la economia** (item 5 de arriba). Es lo que prende la fabrica, el mapa y los jefes.
6. **La cara de terminal:** `calipso` en la consola, REPL contra el mismo `/ws/chat` con el token; mini
   brainstorm de UX pendiente; el WS es un-cliente-a-la-vez (la capa de sesion ya da identidad; falta que el
   chat acepte dos clientes). Bonus: que el comando levante el server y una unidad systemd de usuario para el
   ticker.
7. **Ruteo Fase 2b:** la UI del ofrecimiento ("lo tengo local, queres la nube tapada?") y el degradado avisado
   para el MENSAJE (el bloque del abismo ya se muestra con el mismo molde de senal); vision local en /nube;
   contexto redactado en vez de minimo; normalizacion de tipos del juez.
8. **Compositor:** `/redacta /nube` (tapar solo el hilo), hilos multilinea (`parse_directives` aplana), panel en
   /fabrica, `/mias`, embeddings por registro.
9. **Lector:** el plugin de KOReader (golpear -> sesion `lector`) y la APK (tipo `tablero`); bloqueado por
   `/api/lectura/*` (rebanada 4) y Tailscale.
10. **Residuales con nombre** (los README de los dos cierres los listan con dueno): capa de sesion: el primer
    arranque solo entra por `/setup?token=`, una aprobacion sin canjear vive 30 dias sin poder cancelarse
    desde /fabrica, un host bajo castigo del freno recibe 429 tambien sondeando un id valido; abismo:
    divergencia streaming/one-shot ante un foco anidado en la marca, `turno.retirar_marcas` de una sola
    pasada, el fallback local tras una reinvocacion fallida reempieza pegado al tramo, el foco cosecha focos
    del texto descartado, `/nube /api` streamea marcadores sin reponer, hueco visual en la PWA entre `pescado`
    y el primer chunk, `pintarAbismo` no limpia el texto tapado anterior, `memoria` sin ambito.
11. **Deuda de forma:** AGENTS.md desactualizado (reescribirlo a partir de este documento); `server.py` en 7.7k
    lineas con `ws_chat` de ~650 y tres bucles de streaming; `app.js` en 1.3k con el cuarteto
    pintarX/avisarEnX/click/interval repetido por bandeja; 22 tests que siguen siendo scripts con `main()`;
    `Harness.recibir` ya tiene plazo pero el resto de tests de ws siguen sin el.

## 7. Como seguimos: el metodo que funciono

Lo que produjo las dos ramas de ayer sin regresiones, y conviene repetir tal cual:

1. **Brainstorm con Pedro antes de tocar el modelo** (una pregunta por vez; si Pedro dice "dale" sobre algo
   cuyo modelo no esta cerrado, pensar juntos, no pedir parametros). Salida: un spec en
   `docs/superpowers/specs/` con decisiones de Pedro citadas, invariantes, y "lo que NO hace".
2. **Revision adversaria del spec** (4 lentes) antes del plan.
3. **Plan con codigo completo por task** (`docs/superpowers/plans/`), escrito sobre mapas del terreno con
   lineas reales de hoy (5 lectores en paralelo), y corregido por 3 criticos (cobertura, placeholders y
   firmas, factibilidad con sonda corrida). Task 1 = el harness que todo lo demas reusa.
4. **Ejecucion SDD por workflows:** un implementador por task (lee brief + contexto comun + mapa), un revisor
   de spec y calidad, hasta 5 rondas de fix con re-review acotado. Un workflow por fase (5-7 tasks), el
   controlador lee resultados y escribe un addendum de "seams" para la fase siguiente. Ledger en
   `.superpowers/sdd/<plan>/progress.md` (git-ignored; se archiva en docs al cerrar).
5. **Cierre de rama:** revision final + 3 lentes adversarias con sondas EJECUTADAS + smoke en vivo con server
   desechable (Ollama real, Chromium con el playwright de python), dedup, 3 refutadores por hallazgo, UNA ola de
   fix, re-review, re-smoke si toco el flujo. Los README de los cierres son el molde.
6. **Merge con `--no-ff` tras correr suite + node el propio controlador.** Rotar/reiniciar es de Pedro.

Costos reales del 8 de septiembre, para dimensionar: capa de sesion 9 tareas, 47 agentes, ~5 h; abismo 1b
13 tareas (plan de 3.8k lineas), 61 agentes, ~7 h. Los cierres cazaron 2 y 3 hallazgos Important que las
revisiones por task no vieron: no saltear el ritual.

**Lecciones que ya mordieron:** medir un porton SOBRE el system de produccion, no el contrato solo; excluir
de "legible" la copia literal del molde; dos agentes en paralelo en el mismo checkout comparten el indice de
git (rutas explicitas o worktree); `write_text` trunca en el lugar (usar el escritor atomico); muchos modulos
congelan `CALIPSO_HOME` al importar; el MCP de playwright no arranca en la Ally (usar el de python del venv);
un server que escuche en 0.0.0.0 ve como remoto lo que entra por la IP de wlan0 desde la misma maquina.

**Propuesta para la proxima sesion:** (1) desplegar (reiniciar + rotar); (2) decidir h05 y, si es (a), correr
el ciclo de medicion sobre el system real (un dia); (3) la escalada PUT+commands (brainstorm corto + spec +
plan: es lo que destraba abrir el host y, con eso, el lector); (4) sembrar la economia cuando quieras ver la
fabrica viva.

## 8. Donde esta todo

- **Specs** (`docs/superpowers/specs/`): economia y monedas (08-24), mapa RTS (08-25), mesa de Pedro y plantel
  (08-26), ojos y manos, proyectos y plata (08-27), inbox (08-31), el mundo del jefe y la gramatica de proponer
  (09-01), compositor y ruteo vivo + privacidad (09-02), compositor aprende, el jefe aprende, PvP, siembra
  guiada (09-03), abismo consulta (09-07, enmendado 09-08 con /nube) y capa de sesion (09-07).
- **Planes** (`docs/superpowers/plans/`): uno por spec; el ultimo es `2026-09-08-abismo-1b-cableado.md`. La
  seccion final de `2026-09-07-capa-de-sesion.md` tiene la ruta del 7 (superada por la seccion 6 de aca).
- **Informes:** `2026-09-07-revision-seguridad.md` (con adendas por punto), los dos smokes y los dos cierres del
  09-08, `2026-08-30-estado-y-que-sigue.md` y `2026-08-27-lo-que-falta.md` (historia).
- **Experimentos** (`experimentos/`): el banco del juez de privacidad, los bancos del abismo (contrato v1/v2 y
  la medicion sobre el system de produccion), carta vs sin carta.
- **Memoria del agente** (fuera del repo, `~/.claude/projects/-var-home-pedro/memory/`): `project_calipso.md`,
  `project_calipso_abismo.md` (el dossier vivo), `project_calipso_lector.md`, `project_calipso_compositor.md`,
  `project_calipso_ruteo_fase2.md`, `project_calipso_worktrees.md`, mas los feedbacks (sin emojis, modelo antes
  que parametros, no poner techos). Apuntan a este documento.
- **El lector:** `~/calipso-lector/BRIEF.md` (fuera de git; respaldo del 09-08 en el scratchpad de esa sesion).

## 9. Adenda 2026-09-10: lo que paso en la sesion siguiente

- **Despliegue hecho:** server real con main, token rotado (seccion 0).
- **h05 cerrado, opcion (a):** el porton se re-midio SOBRE el system de produccion con la metrica corregida
  (la copia literal del molde no cuenta) y descubrio que el porton v2 nunca habia pasado en memoria. Se podo
  el system local (identidad corta en vez de CALIPSO.md; contrato interno de 7 renglones) y se re-escribio
  la letra del bloque con las SENALES de Pedro ("te conte", "lo tenes", "acordate", "la otra vez", "que
  dejamos"). A N=6: memoria 83%, chats 100%, proyecto 83%, espurias 0, cero copias literales; ruteo 88% (dos
  items deterministas; Pedro acepto la excepcion). Evidencia: `experimentos/consulta_abismo_system_resultados.md`;
  la letra de produccion esta atada a lo medido por `test_abismo_system_medido.py`. Rama `feat/abismo-system-podado`.
- **Dos decisiones de Pedro sobre el abismo:** los anillos gobiernan solo /nube ("los modelos ven todo,
  incluido el anillo 3"); la credencial jamas sale, en ningun destino no local (hueco conocido en
  `viaje.py:51-53` sin /nube; lo cierra la tarea 9 del plan de la aduana).
- **La aduana (nueva, spec en main):** `docs/superpowers/specs/2026-09-10-aduana-design.md`, sobre el mapa
  verificado `docs/superpowers/2026-09-10-mapa-salidas-al-exterior.md`. Idea de Pedro: "la unica puerta al
  internet", afinada a "los modelos ven todo; los queries a internet se miden" (cuantos, quien, que se va; sin
  frenar). Es la mitad que MIDE de la frontera de salida del 08-24; publicar/correo/gasto real siguen siendo
  compuertas obligatorias del motor de permisos. Siguiente paso: el plan (writing-plans) y su ejecucion SDD.
- **Metodo nuevo que funciono:** Codex headless (`codex exec -m gpt-5.5 -s read-only --output-schema`) como
  lente adversaria independiente, a pedido de Pedro, en la refutacion del mapa (10 veredictos) y en la revision
  del spec. El modelo `astra` no esta disponible con cuenta ChatGPT.
- **Ruido del home real visto de paso (de Pedro):** la meta de prueba `goal_ff4b5cd203f0` (junio) sigue activa y
  entra en cada turno; el recall trae recuerdos "-q" con acentos rotos. Y `.claude/launch.json:7` arranca
  uvicorn en `0.0.0.0` (el default loopback solo rige bajo `__main__`).
