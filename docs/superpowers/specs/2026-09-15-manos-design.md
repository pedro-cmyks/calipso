# Las manos (subproyecto 2): el goal que instala, corre una app y muestra lo que hizo

**Estado: BORRADOR del brainstorm del 2026-09-15 (decisiones de Pedro tomadas; el diseño en secciones
esta presentado y pendiente de su ok final; sin lentes ni plan todavia).** Lo revisamos y lo cerramos la
proxima sesion; despues van las lentes (Claude + Codex adversario), el spec v2 y el plan.

## 1. De donde sale

El norte de Pedro (2026-09-12): "decirle a Calipso 'disena un asset para este juego de aves' y que vaya y
abra Blender o lo instale, o se de cuenta de que hay servicios en internet que lo hacen y cuanto valen, y
me diga lo que encuentra, haga y encuentre e itere". El subproyecto 1 (los goals, mergeado y desplegado el
2026-09-14) dio la cabeza y el bucle: un goal corre solo en un clon con Claude Code como martillo dentro de
un sandbox, con un hook fail-closed, un juez y Pedro al final. Lo que falta para el ejemplo del norte son
las MANOS: instalar y correr una aplicacion, dejar el resultado donde Pedro lo quiere, hablar con Calipso
desde adentro de un golpe, y que Pedro VEA lo que salio.

Decisiones de Pedro en el brainstorm (2026-09-15):

1. **El caso guia es un asset para AvesCO en Blender**: el goal instala Blender (pregunta), genera un modelo
   con `bpy` headless, lo exporta al repo AvesCO y le muestra a Pedro un render.
2. **El martillo habla con Calipso por un MCP `calipso` de solo lectura mas `preguntar`**: consulta la
   memoria, el estado del goal y la aduana, y pide una compuerta al vuelo sin terminar el golpe; nunca
   escribe en `~/.calipso`.
3. **El chat propone el `/goal` y Pedro dice dale**: un pedido con manos en el chat se vuelve una propuesta
   automatica (titulo, criterio, tope) que aparece en el inbox; no cambia el modelo de goals.
4. (Modelo propio, proyecto de sesion aparte) **primero la voz**: ver `docs/superpowers/2026-09-15-proyectos-de-sesion.md`.

## 2. El caso guia, paso a paso (lo que tiene que pasar de punta a punta)

Pedro, en el chat: "disena un asset de un colibri low-poly para AvesCO y dejalo en el repo con un render".

1. El chat detecta manos (`needs_hands`), arma la propuesta con la cabeza frontera y la estaciona en el
   inbox: titulo, criterio (`existe assets/colibri.glb` + revisor mira el render), tope (8 golpes, 40 min),
   familias (`repo`, `instalar_home`, `correr_app`), `en: ~/AvesCO` (o el clon de GitHub si no esta local).
2. Pedro: dale (inbox o `/goal dale`).
3. Golpe 1: el martillo ve que no hay Blender (`flatpak list`, `which blender`) y pide la compuerta
   `instalar_home` con la forma exacta (`flatpak install --user flathub org.blender.Blender`) **por el MCP,
   sin terminar el golpe**; la solicitud aparece en el inbox; Pedro dice si; el martillo sigue en el mismo
   golpe (o, si Pedro tarda mas que el plazo del MCP, el golpe termina `preguntar` como hoy).
4. Instala (la linea de deshacer va al ledger: `flatpak uninstall --user org.blender.Blender`).
5. Escribe `assets/colibri.py` (bpy: malla low-poly, material, export a glTF) y lo corre headless:
   `flatpak run org.blender.Blender -b -P assets/colibri.py` (familia `correr_app`: correr una app que el
   goal instalo o que ya estaba, dentro del sandbox, directo).
6. Renderiza un PNG (Cycles CPU o Workbench; sin GPU en el sandbox) y lo deja en el clon.
7. Termina `terminar`. Juez: el criterio archivo pasa; el revisor de otra familia LEE el render (Claude Code
   lee imagenes con `Read`; Codex `-s read-only` tambien) y dice si parece un colibri low-poly; Pedro ve
   el render en la tarjeta del goal (/fabrica y la PWA) y dice dale.
8. `complete`: la rama `goal/<id>` queda en AvesCO; el merge es de Pedro.

Lo que hoy NO existe y este subproyecto construye: el MCP (3), `correr_app` (5), las imagenes en el goal
(7), la propuesta automatica desde el chat (1). Lo que ya existe y se reusa: el sandbox, el hook, el clon,
`instalar_home` (pregunta), el juez, el inbox, la rama traida.

## 3. El MCP `calipso` (solo lectura + preguntar)

Un servidor MCP por stdio, `calipso/mcp_calipso.py`, que el martillo recibe en el `--mcp-config` del golpe
(el unico MCP: sigue `--strict-mcp-config`). Corre DENTRO del sandbox como hijo del CLI, asi que no puede
leer `~/.calipso` (denyRead): habla con el server por HTTP en `127.0.0.1:8000` con un **token del goal**
(capability: solo ese goal, solo lectura mas `preguntar`, vence con el goal; nace en `_lanzar_bucle` y va
en el env del golpe). La red del sandbox suma `127.0.0.1` solo para ese puerto.

Herramientas:

| tool | que hace | escribe? |
|---|---|---|
| `memoria_buscar(q, k)` | recall en la memoria de Pedro (lo que la aduana declara: sale a la suscripcion como el resto del prompt) | no |
| `goal_estado()` | el goal, el consumo contra el tope, las notas de Pedro, las `falta` del juez | no |
| `aduana_resumen()` | cruces de este goal | no |
| `preguntar(pregunta, compuerta?, plazo_s=120)` | estaciona la solicitud en el inbox y ESPERA hasta `plazo_s`; devuelve `si`/`no`/`sin respuesta`; con `si` aplica (`aplicar_respuesta`: preautorizada, host, raiz) y el hook lo ve en el mismo golpe | crea la solicitud (es lo unico que crea) |
| `nota(texto)` | una nota al ledger del goal (lo que el martillo quiere que Pedro lea) | ledger del goal |

Invariantes: el MCP no tiene ninguna tool que escriba en la memoria, la aduana o los permisos; todo lo
que devuelve pasa por `tapar`; cada llamada es un cruce de aduana con origen `goal` y `via: mcp`; sin token
valido el server contesta 401 y el hook no interviene (el MCP no es Bash). La sonda de hook inactivo no
cuenta los `mcp__calipso__*` (son in-process del CLI: se registran aparte en `golpes.jsonl`).

## 4. `correr_app`: correr una aplicacion instalada, headless

Familia nueva `correr_app` (directo por defecto, en la tabla de Pedro entre `repo` e `instalar_en_goal`):
`flatpak run <app> ...`, `<app>` de `~/.local/bin`, o un binario del clon/venv, SIN interfaz (`-b`,
`--headless`, `--background`, o el equivalente que el hook conozca por app). El hook: allow-list de apps
por nombre (`org.blender.Blender`, `org.inkscape.Inkscape`, `org.gimp.GIMP`, `ffmpeg`, `pandoc`,
`libreoffice --headless`...), args de salida dentro del clon o las raices (los `-o`/`--output`/`--export`
van a `_tokens_destino`), sin red propia (el sandbox ya la corta). Una app fuera de la lista: `pregunta`.

No confirmado (para el smoke): flatpak DENTRO del sandbox nativo (bwrap dentro de bwrap: puede fallar por
namespaces anidados; alternativa: correr la app fuera del sandbox pero bajo `correr_confinado`, el bwrap del
criterio, con `--share-net` apagado); bpy sin GPU; el tiempo de un render.

## 5. Las imagenes del goal (los ojos, version 0)

Un golpe que deja un PNG/JPG/SVG en `<clon>/goal-imagenes/` (o lo nombra en el veredicto: `imagenes:
[...]`) hace que el runner lo copie a `~/.calipso/goals/<id>/imagenes/` (tapado: nada de rutas ni texto
sensible en el nombre) y lo exponga en `GET /api/goals/<id>/imagenes/<n>`; la tarjeta de /fabrica y la
`#goalBar` de la PWA los muestran; el revisor los recibe (Claude Code lee imagenes; Codex tambien). Es lo
mas cerca de "ojos" sin captura de pantalla; la captura y los clicks son el subproyecto 3.

## 6. La propuesta automatica desde el chat

Cuando `needs_hands` es verdadero y el pedido no es un `/goal` explicito, el turno de chat contesta como
hoy (honesto, sin manos) Y ademas propone el goal: `_proponer_goal(texto, en=<repo activo o el que
nombre>)` en hilo, con la cabeza frontera; la respuesta termina con "propuse el goal <id>: <titulo>
(criterio, tope); dale en el inbox o `/goal dale`". Costo: una llamada frontera mas por pedido con manos;
si la maquina esta `cargada` o la cuota al limite, solo sugiere el comando. Un goal en curso: no se propone
otro, se dice.

## 7. Compuertas y seguridad (lo que no cambia)

La tabla de Pedro sigue: directo = repo, web, instalar_en_goal, raices, `correr_app`; pregunta = merge,
push, borrar fuera, raiz nueva, instalar home/sistema; NUNCA = gastar, publicar, correo, datos de Pedro,
rpm-ostree rebase/reset/rollback, borrar remotes flatpak. El MCP no abre ninguna: `preguntar` pasa por el
motor como una solicitud mas. Blender instalado por el goal vive en `~/.local/share/flatpak` (home:
pregunta, con su linea de deshacer). Servicios en internet (el otro ejemplo del norte) quedan para despues
de este spec: navegar y comparar precios es `web`; contratar es `gastar` (NUNCA).

## 8. Verificacion

Unitarios con `cli_falso_stream` (el MCP con un server falso; `correr_app` en el hook con stdin sintetico;
las imagenes en el runner con Falsas; la propuesta automatica por harness). Smoke real: Blender flatpak
`--user` de verdad (~300 MB), un clon de AvesCO (o un repo temporal con la misma forma), el asset y el
render, el MCP preguntando en vivo con el si por el inbox, y el desinstalar al final. No confirmado 1-3 de
la seccion 4.

## 9. Lo que NO hace

Captura de pantalla ni clicks (subproyecto 3); merge/push automaticos; Codex como manos con red; instalar
en el sistema (rpm-ostree, flatpak --system: pregunta, y no se prueba en el smoke); servicios pagos.

## 10. Corte tentativo

1. El MCP `calipso` con el token del goal y `preguntar` con espera (server + `goals_manos` + hook).
2. `correr_app` en el hook y el motor + las apps de la allow-list.
3. Las imagenes del goal (runner, endpoints, /fabrica, PWA, revisor).
4. La propuesta automatica desde el chat.
5. El smoke con Blender y AvesCO + informe.
