# Las manos (subproyecto 2): el goal que instala, corre una app y muestra lo que hizo

**Estado: SPEC v2 del 2026-09-16. El borrador del brainstorm del 2026-09-15 queda SUPERADO** (git lo
guarda: `git log -p -- docs/superpowers/specs/2026-09-15-manos-design.md`). Las ocho decisiones de Pedro
estan tomadas y aca se escriben como decisiones, cada una con su razon medida.

La autoridad sobre el estado del codigo es `docs/superpowers/2026-09-16-terreno-manos.md` (1.046 lineas,
ocho lectores sobre el codigo real mas un probe empirico sobre la maquina). Donde el borrador y el terreno
se contradecian, mando el terreno: esta version ya viene corregida, y cada afirmacion fuerte lleva su
`archivo:linea`. Todas las lineas citadas se releyeron al escribir esto (dos del terreno estaban corridas
en uno y aca van con el numero real: `goals_hook.py:1397` "familia sin nivel", `goals_hook.py:1364` el
DENEGAR de flatpak).

**Las seis lentes adversarias (cinco de Claude, una externa de Codex) ya corrieron: sus rulings estan en la
§12, y lo que quedo para Pedro en la §13.** El cuerpo de arriba ya viene corregido por esa adenda y cada
correccion lleva su numero de ruling; donde el cuerpo y la §12 se contradigan, manda la §12. Despues de
esto: el plan y el SDD, que citan este spec **por sha**, no por linea del working tree.

La numeracion se corrio en uno: entra la seccion 2 (las premisas falsas). Mapa contra el borrador: §2 caso
guia -> §3; §3 MCP -> §4; §4 `correr_app` -> §5; §5 imagenes -> §6; §6 propuesta -> §7; §7 compuertas ->
§8; §8 verificacion -> §10; §9 lo que no hace -> §9; §10 corte -> §11.

## 1. De donde sale, y las ocho decisiones

El norte de Pedro (2026-09-12): "decirle a Calipso 'disena un asset para este juego de aves' y que vaya y
abra Blender o lo instale, o se de cuenta de que hay servicios en internet que lo hacen y cuanto valen, y
me diga lo que encuentra, haga y encuentre e itere". El subproyecto 1 (los goals, mergeado y desplegado el
2026-09-14) dio la cabeza y el bucle: un goal corre solo en un clon con Claude Code como martillo dentro de
un sandbox, con un hook fail-closed, un juez y Pedro al final. Lo que falta para el ejemplo del norte son
las MANOS: instalar y correr una aplicacion, dejar el resultado donde Pedro lo quiere, hablar con Calipso
desde adentro de un golpe, y que Pedro VEA lo que salio.

Las cuatro decisiones del brainstorm del 09-15 siguen en pie: el caso guia es un asset para AvesCO en
Blender; el martillo habla con Calipso por un MCP `calipso` de solo lectura mas `preguntar`; el chat propone
el `/goal` y Pedro dice dale; el modelo propio va aparte
(`docs/superpowers/2026-09-15-proyectos-de-sesion.md`).

Sobre eso, las OCHO del 09-16, tomadas contra el terreno:

**D1. `correr_app` corre AFUERA del sandbox del CLI, por `correr_confinado` (el bwrap propio, el del
criterio) mas DOS mounts escribibles: `--tmpfs /run/user/<uid>` y `--tmpfs ~/.var/app`** (R2 de la adenda
corrige aca "UNA linea": con una app RECIEN instalada -- que es Blender en el caso guia -- el primero solo
no alcanza). Medido en esta maquina: con el `argv_bwrap` real del repo (`goals_manos.py:1046-1073`),
`flatpak run` da rc=1 `Unable to allocate instance id`; con `--tmpfs /run/user/1000` da rc=0 para una app
que YA tiene su `~/.var/app/<id>` (`org.kde.kcalc`) y rc=1 `mkdirat(org.kde.filelight): Read-only file
system` para una que no; sumando `--tmpfs ~/.var/app` da rc=0 tambien para esa. El argv sigue con
`--unshare-net` (`:1072`) y sigue tapando `~/.calipso` y `~/.ssh` (`:1067-1071`). La alternativa (meter la app en el sandbox del CLI sumando `/tmp` y `$XDG_RUNTIME_DIR` a
`escritura`, `goals_manos.py:449`) es peor y mas cara: el CLI traduce `allowWrite` a `--bind` de las rutas
REALES, y `/run/user/1000` en esta maquina tiene `ssh-agent.socket`, el bus de sesion, `wayland-0`, `gnupg`
y `pipewire-0`. Queda DESCARTADO `sandbox.enableWeakerNestedSandbox`: el propio binario dice que "exposes
the host /proc". **El costo que esta decision paga, y que esta seccion 5 escribe:** ese paso no lo lanza el
CLI sino el runner, asi que NO pasa por el hook `PreToolUse`; hay que validar a mano llamando a
`goals_hook.familia_de_argv` antes de lanzar, mas la fila de ledger, el scope systemd y el cruce de aduana.

**D2. El nivel de correr una app es MIXTO POR APP.** Directo para las que solo transforman datos (ffmpeg,
pandoc); pregunta para las que ejecutan codigo ajeno (`blender -P`, `gimp -b`, `libreoffice macro:///`).
Razon: con nivel directo para todas, `flatpak run org.blender.Blender -b -P assets/colibri.py` es ejecucion
arbitraria aprobada de antemano -- el hook lee el argv, no el script: es `python -c` con otro nombre, justo
lo que `_codigo_inline` (`goals_hook.py:1153-1175`) existe para negar. Y el nivel viene con gramatica por
app: bandera headless obligatoria, banderas prohibidas explicitas (`--command=`, `--filesystem=`,
`--share=`, `--socket=`, `--talk-name=`, `--env=`, `--devel` y los inline de cada app) y el argumento de
script dentro del clon. **Ojo:** `correr_app` NO EXISTE hoy en el repo (grep sobre `calipso/` y `test_*.py`:
cero coincidencias) y una familia sin nivel en la tabla DENIEGA, no cae en directo
(`goals_hook.py:1397`). Son tres tablas que un test obliga a mantener identicas (`goals.py:63-70`,
`permisos/goal.py:44-50`, `test_goals_permisos.py:61`) mas la copia que cada goal ya creado guarda en su
`goal.json` (`goals.py:650` la escribe, `goals.py:1011` la lee): hay que FUSIONAR, no usar la copia tal cual.

**D3. El token del goal viaja en el bloque `env` del propio `mcpServers`, en un archivo 0600 bajo
`~/.calipso/goals/<id>/`, pasado como `--mcp-config <archivo>`.** Nunca en el env del proceso CLI: todo
comando Bash del martillo lo heredaria (el bwrap que construye el CLI no lleva `--clearenv`: el unico
`--setenv` de su argv es el del proxy, asi que el entorno del padre se hereda entero), `curl` esta en
`ALLOW_EXES` (`goals_hook.py:133`) y los comandos del golpe se guardan en la fila del ledger
(`goals_runner.py:947`), o sea que un `curl` con el token quedaria escrito en `golpes.jsonl`. Nunca inline
en la argv: `ps` lo veria, que es exactamente la trampa que el diseno ya evito para el prompt (va por stdin)
y para el contrato (va por archivo). Y nunca el TOKEN maestro: `env_saneado` BORRA `CALIPSO_TOKEN`,
`LITELLM_MASTER_KEY` y las claves Anthropic a proposito (`goals_manos.py:88-90`). Queda por resolver, y §4
lo resuelve, donde vive entre relanzamientos del bucle y donde se revoca: la unica puerta sin agujeros es
`goals.transicionar` al entrar en `FINAL_STATES` (`goals.py:48`, `:719`).

**D4. `preguntar` NO BLOQUEA.** El MCP estaciona la solicitud en el inbox y el golpe termina en estado
`preguntar`, como hoy. Razon medida: el inbox de /fabrica se repinta cada 60 s y no hay push
(`web/fabrica/app.js:1505`; los goals, `:1517`), asi que una espera de 90 s deja casi cero segundos reales
para contestar. La tool existe igual, pero devuelve `estacionada` y no espera.

**D5. El hook NO juzga las llamadas `mcp__calipso__*`, pero SI quedan registradas.** El motivo, corregido
por R14 de la adenda (el borrador decia "el CLI compara esos matchers como strings exactos", que es falso):
el matcher se evalua como **RegExp de JS SIN anclar** sobre `tool_name` (bundle 2.1.273, la funcion que
decide si un hook aplica hace `if(!n||n==="*")return!0; ... let O=new RegExp(n); if(O.test(e))return!0`), y
`MATCHER_HOOK` (`goals_manos.py:277`) es una alternancia -- por eso UNA sola string dispara el hook para
cuatro herramientas distintas (medido sobre `~/.calipso/goals/*/hook.jsonl`: Bash 148, Write 34, Read 8,
Glob 1). Ninguna de las diez alternativas, todas con mayuscula, aparece dentro de un
`mcp__calipso__<minusculas>`: no casa. Eso se deja como esta, y se compensa con registro: campo nuevo en el
Parser y clave nueva en la fila de `golpes.jsonl` (hoy `_assistant` solo junta los `tool_use` de nombre
"Bash", `goals_manos.py:679-684`). Lo que rompe al sumar `mcp__calipso__.*` NO es "convertir los diez
nombres en regex sin anclar" (ya lo son): es la rama que falta en `decidir` (`goals_hook.py:1470`, que cae
en "herramienta fuera del contrato del goal") mas el desbalanceo de `CON_HOOK`; cualquier descuido mata toda
llamada MCP por fail-closed.

**D6. La propuesta automatica desde el chat se dispara SIEMPRE que haya manos, pero ANTES hay que arreglar
la deteccion.** Pedro: "la deteccion tiene que ser perfecta, arreglemosla". La seccion 7 la escribe como
compuerta de medicion contra el banco, no como opinion.

**D7. El terreno del smoke se precrea a mano.** El remote flathub `--user` lo crea Pedro una vez, fuera de
todo goal (`flatpak remotes --user -d` sale vacio y `flatpak --installations` devuelve solo
`/var/lib/flatpak`: sin eso, la linea del paso 3 falla antes de tocar la red con `Remote "flathub" not found
in the user installation`, y ademas el hook clasifica cualquier `remote-add` como `instalar_sistema` aunque
lleve `--user`, `goals_hook.py:1356`). El repo puede ser AvesCO real: ya existe local en
`/var/home/pedro/repos/AvesCO` (clonado el 09-16; rama `master`, cuatro archivos: `README.md`, `DOSSIER.md`,
`docs/GDD.md`, `.gitignore`), asi que el `en:` del caso guia es `~/repos/AvesCO` y no `~/AvesCO`.

**D8. Para Blender el martillo NO escribe `bpy` libre.** Emite un SPEC JSON validado; el script que corre
dentro de Blender es del repo, fijo y revisado. Convierte "ejecutar codigo arbitrario" en "validar un JSON"
y deja el spec como artefacto con procedencia. Ademas, una sonda barata por app antes de gastar el golpe:
el patron doctor -- correr la app con un marcador literal en stdout y timeout corto, y decidir por el
marcador, no por el returncode. (El patron viene de OpenMontage, que es AGPL-3.0 con clausula de red: se
mira la forma, NO se copia una linea de su codigo.)

Y una decision de proceso que precede a todo: **antes de escribir el plan corre una SONDA DE TERRENO contra
Claude Code 2.1.273** (`claude --version`; el terreno del cierre esta medido sobre 2.1.270 y
`goals_manos.py:431-432` todavia lo dice). Contesta lo unico que puede tirar abajo el MCP entero: si una tool
`mcp__calipso__*` se ejecuta sola bajo `--restricted --permission-prompts none` o si el CLI la niega
automaticamente (el texto del binario: `--permission-prompts none` = "nobody: anything that would prompt is
denied automatically"). Y si el schema de `sandbox` se movio: `failIfUnavailable` podria no existir y el
sandbox fallaria ABIERTO. Detalle en §10.S1.

## 2. Las tres premisas falsas del borrador, y que cambia en el diseno

### 2.1. "El MCP corre DENTRO del sandbox como hijo del CLI, asi que no puede leer `~/.calipso` (denyRead)"

**Falso.** El sandbox se aplica POR COMANDO Bash, no a la sesion: el CLI construye un bwrap por comando. Un
servidor MCP por stdio es hijo del CLI y corre como Pedro, sin `denyRead`, sin hook, con `~/.calipso`,
`~/.ssh` y la red enteras. La prueba esta en la maquina: el hook `PreToolUse` -- otro hijo del CLI --
escribe HOY en `/var/home/pedro/.calipso/goals/*/hook.jsonl`, y esa ruta esta en `DENY_READ`
(`goals_manos.py:280-281`). El propio schema del binario 2.1.273 lo dice: "Enforced for sandboxed commands
only - in-process tools such as WebFetch are not gated".

**Que cambia.** (a) El MCP deja de ser un adaptador y pasa a ser codigo de seguridad: es la unica pieza del
golpe que no pasa ni por el hook ni por `denyRead` ni deja fila en `hook.jsonl`. Todo el peso se muda al
token, al 401 del server y a `tapar` (`goals_manos.py:1186`). (b) Se cae la necesidad de abrir `127.0.0.1`
en la red del goal: el MCP llega al 8000 sin tocar nada. Esa frase del borrador se borra, y ademas era
inexpresable: `_host()` hace `split(':')[0]` (`goals_hook.py:561-563`), o sea que el puerto no se compara, y
`web` es DIRECTO en la tabla (`goals.py:64`); un `127.0.0.1` en `dominios` habilitaria cualquier
`curl http://127.0.0.1:<puerto>` de TODO comando Bash del golpe -- Ollama en 11434 incluido.

### 2.2. "bwrap dentro de bwrap puede fallar por namespaces anidados"

**Falso, y el sintoma real es otro.** El anidamiento anda: `bwrap --dev-bind / / --unshare-user
--unshare-pid bwrap ... /bin/true` -> rc=0, y tambien dentro de la forma exacta del martillo. Lo que faltan
son DOS mounts escribibles. Medido en orden: forma exacta del martillo + `flatpak run` ->
`open(O_TMPFILE): Read-only file system` rc=1; `+ --tmpfs /tmp` -> `Unable to allocate instance id` rc=1;
`+ --tmpfs /run/user/1000` -> rc=0.

**Que cambia.** El eje de la seccion 5 entera. La alternativa que el borrador mencionaba de pasada
(`correr_confinado`) es la que se arregla con UNA linea y sin aflojar nada, y el camino que daba por
principal (Bash del martillo bajo el sandbox del CLI) es el que exige bindear rutas reales sensibles. D1.

### 2.3. "El martillo recibe el MCP en el `--mcp-config` del golpe" (implicito: alcanza con sumar una flag)

**Bloqueante que el borrador no menciona.** Hoy CUALQUIER tool que empiece con `mcp__` en el `system/init`
es violacion y mata el golpe en el acto: `raras = [t for t in self.tools if str(t).startswith("mcp__")]` ->
`self._violar(f"mcp inesperado en la sesion: {raras[:3]}")` (`goals_manos.py:647-649`), y el runner lo
convierte en `failed` (`goals_runner.py:981-983`). Sin invertir esa regla, TODO golpe con el MCP muere en el
primer init, y el sintoma se lee como "mcp inesperado", no como "falta permitir el MCP". Ademas `argv_claude`
pasa `--strict-mcp-config` pero nunca `--mcp-config`.

**Que cambia.** La primera tarea del MCP no es "agregar una flag" sino invertir un invariante por una lista
blanca de NOMBRES EXACTOS, y arrastra `test_goals_manos.py:328-329` (la guarda) y
`test_goals_manos.py:226` (**el unico test de la argv del GOLPE**). Los otros tres que el borrador contaba
como arrastrados no lo son y no se rompen (R32): `test_seguridad_techo.py:206-210` es la argv del chat,
`test_goals_chat.py:514` la de la cabeza y `test_goals_manos.py:1078-1088` la del revisor, y sus asserts son
de pertenencia o por indice, nunca igualdad de lista. Esos tres se reusan para fijar el invariante contrario:
que esas tres argv **no** ganan `--mcp-config`. Se dimensiona como tal en el corte.

### 2.4. Lo demas que el borrador daba por cierto y no lo es

- **`correr_app` "no cambia la tabla de Pedro" (§7 del borrador).** Si la cambia: la familia no existe
  (grep: cero) y una familia sin nivel DENIEGA (`goals_hook.py:1397`). Es un ruling de Pedro, tomado en D2.
- **`flatpak run` es clasificable hoy.** No: cae en el `DENEGAR` final de la rama flatpak
  (`goals_hook.py:1364`). Una app de `~/.local/bin` por ruta absoluta muere como `ruta_fuera`
  (`goals_hook.py:1116-1135` -> `:1276`); por nombre suelto muere en el fallback (`:1375`).
- **Blender pesa ~300 MB.** Pesa 477,4 MB de descarga y 1,1 GB instalado (`flatpak remote-info flathub
  org.blender.Blender`, version 5.2). El runtime que pide (`org.freedesktop.Platform 25.08`) ya esta en el
  system. Y esos 477,4 MB tienen que caber en `GOLPE_TIMEOUT_S` = 900 s: 4,24 Mbit/s sostenidos (R28).
- **Los tmpfs del confinado son gratis.** No: `--tmpfs` sin `--size` da la mitad de la RAM -- medido, 5,7 G
  cada uno adentro del bwrap, sobre 11,4 GiB totales (R4).
- **`flatpak run` alcanza con `--tmpfs /run/user/<uid>`.** Solo para una app que YA tiene su
  `~/.var/app/<id>`. Para una recien instalada hacen falta DOS mounts (R2).
- **El `si` mid-golpe siempre entra en el mismo golpe.** Solo para compuertas: el hook relee
  `compuertas.json` en cada invocacion (`goals_hook.py:1477-1487`). Para `web` y `raiz_nueva` NO:
  `allowedDomains`, `allowWrite` y `--add-dir` se serializan al lanzar (`goals_manos.py:462` allowWrite,
  `:466-468` allowedDomains y strictAllowlist, `:503-504` `--add-dir`;
  armados una vez en `goals_runner.py:474-488`). Y la preautorizada se compara por igualdad EXACTA de dict
  (`goals_hook.py:1391-1393`).
- **Los frenos de la propuesta automatica.** "Un goal en curso, no se propone otro" no existe: `goals.crear`
  nace en `PROPOSED` sin consultar `activo()` (`goals.py:621-650`); el unico chequeo esta al transicionar a
  `ACTIVE` (`goals.py:709-713`). Y la firma real es `_proponer_goal(d, texto_crudo, departamento)`
  (`server.py:4286`).

## 3. El caso guia, paso a paso

Pedro, en el chat: "disena un asset de un colibri low-poly para AvesCO y dejalo en el repo con un render".

**Paso 0 (fuera de todo goal, una vez, a mano; D7).** El remote de usuario:
`flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo`. El repo
ya esta: `/var/home/pedro/repos/AvesCO`.

1. El chat detecta manos (§7: mensaje + contexto, con la compuerta de medicion cumplida), arma la propuesta
   con la cabeza frontera y la estaciona en el inbox: titulo, criterio (`existe assets/colibri.glb` + el
   revisor mira el render), tope (8 golpes, 40 min -- **no cierra, P6 de §13**), familias (`repo`,
   `instalar_home`, `correr_app`, `correr_datos`, `raiz_nueva`), `en: ~/repos/AvesCO`, y **`dominios:
   ["dl.flathub.org"]`** (R27). Lo ultimo no es opcional: sin eso el golpe 2 no llega a flathub. La red del
   golpe es `api.anthropic.com` + los indices de paquetes + `compuertas["dominios"]`, con
   `strictAllowlist: true` (`goals_manos.py:415-425`, `:466-468`), y flathub no esta en ninguno de los tres;
   es el mismo golpe que las adendas 32 (pypi) y 36 (la CDN de pytorch) del spec de goals ya pagaron dos
   veces. `web` es directo en la tabla, asi que declararlo no cuesta compuerta. Medido: `dl.flathub.org` es
   un solo host sin redireccion (`curl -L .../repo/config` -> 200, 0 redirects); **lo que NO esta medido es
   si `flatpak`/`libostree` respeta el proxy socks/http del sandbox del CLI** (§10.3), y esa es la primera
   pregunta de S2.
2. Pedro: dale (inbox o `/goal dale`).
3. Golpe 1: el martillo ve que no hay Blender (`flatpak list` pasa libre por el hook,
   `goals_hook.py:1362`; `which blender` da 1) y pide DOS cosas por el MCP (`preguntar`, que estaciona y no
   espera, D4): la compuerta `instalar_home` con la forma exacta
   `flatpak install --user flathub org.blender.Blender`, y la raiz `~/.local/share/flatpak`. El golpe
   termina en `preguntar`, como hoy. Pedro dice si a las dos en el inbox.
4. Golpe 2: instala. **La raiz recien vale en este golpe**, no en el anterior: `allowWrite` y `--add-dir` se
   congelan al lanzar el proceso (`goals_runner.py:474-488`); esto hay que decirlo porque el modo de falla
   -- el hook dice que si y el CLI dice que no -- ya mordio en el smoke G3. La linea de deshacer va al
   ledger: `flatpak uninstall --user org.blender.Blender` -- **pero nadie la ejecuta hoy** (P4 de §13:
   `linea_de_deshacer` produce un string y no hay ejecutor; si el goal muere en el golpe 3, 1,1 GB de
   Blender quedan instalados). El install tiene que caber en `GOLPE_TIMEOUT_S` = 900 s (R28): 477,4 MB en
   900 s exige 4,24 Mbit/s sostenidos, y 10,1 Mbit/s si la instalacion `--user` no reusa el runtime del
   system (+659,9 MB, no confirmado). Si vence, el golpe se mata, la fila CUENTA para el tope (no es
   `cuota_fallo` ni `cancelado`) y se llevo 1 de 8 golpes y 15 de 40 minutos sin instalar nada: S5 mide el
   enlace ANTES, y este golpe va con `CALIPSO_GOAL_TIMEOUT_S` subido. (Compuerta de medicion S2: no esta
   confirmado que `flatpak install --user` funcione dentro del sandbox del CLI, que no tiene `/tmp`
   escribible ni `$XDG_RUNTIME_DIR`.)
5. **El asset, sin `bpy` libre (D8).** El martillo escribe `assets/colibri.spec.json`: un SPEC declarativo
   (primitivas, modificadores permitidos, material, escala, export) validado contra un esquema del repo. El
   script que corre dentro de Blender es del repo, fijo y revisado:
   `calipso/manos/blender_spec.py`, que lee el spec, lo valida otra vez adentro y exporta. El runner lo
   lanza por `correr_confinado` (D1):
   `flatpak run org.blender.Blender -b -P <repo>/calipso/manos/blender_spec.py -- --spec <clon>/assets/colibri.spec.json --out <clon>/assets/colibri.glb`.
   **Este paso cuesta una vuelta por el inbox que el guion omitia (R29):** `correr_app` es PREGUNTA (D2), y
   §5 dice que con decision negativa no se lanza nada y el goal pide la compuerta. O sea que antes de correr
   hay un golpe que pide `correr_app` y un si de Pedro. Es parte de por que el tope de 8 no cierra (P6).
   Y el SPEC JSON tiene que topear el presupuesto del render, no solo la forma (R30): motor, samples y
   resolucion con numeros escritos (Workbench por defecto; Cycles solo hasta N samples; resolucion <=
   1280x720). Sin eso, un `engine: cycles, samples: 4096, resolution: 4096x4096` valida el esquema y quema
   el timeout entero a 16 hilos -- y el costo del revisor, que lee el PNG, tambien lo elige el martillo.
   Antes de gastar el golpe corre la **sonda de la app**: el mismo `flatpak run` con
   `calipso/manos/sonda_blender.py`, timeout 60 s, y se decide por el marcador literal
   `CALIPSO_SONDA org.blender.Blender ok` en stdout, no por el returncode (Blender vuelve 0 habiendo hecho
   nada, y vuelve distinto de 0 por ruidos de audio/GPU que no importan). Si el marcador no aparece, el goal
   no gasta golpe: va a `preguntar` con la cola de la salida.
6. El render: el mismo camino, con el spec declarando camara y luces, Workbench o Cycles CPU (no hay GPU:
   dentro del bwrap `/dev` no tiene `dri`). El PNG queda en `<clon>/goal-imagenes/`.
7. `terminar`. El juez: el criterio archivo pasa; el revisor de otra familia LEE el render y dice si parece
   un colibri low-poly. **Al revisor se le pasan las rutas DEL CLON, no las copias de `~/.calipso`**: el
   revisor corre con `denyRead` sobre `~/.calipso` (`goals_manos.py:280-281`) y no podria abrirlas. Pedro ve
   el render en la tarjeta del goal en /fabrica y en el detalle de la PWA, y dice dale.
8. `complete`: la rama `goal/<id>` queda en AvesCO; el merge es de Pedro. Al entrar en `FINAL_STATES` se
   revoca el token del MCP y se borra su archivo (§4).

Lo que este subproyecto construye: el MCP (3, 5), `correr_app` por `correr_confinado` (5, 6), las imagenes
del goal (7), la propuesta automatica desde el chat (1). Lo que ya existe y se reusa: el sandbox, el hook,
el clon, `instalar_home` (pregunta), el juez, el inbox, la rama traida.

## 4. El MCP `calipso` (lectura del goal, mas `preguntar` y `nota`, que no bloquean)

**Donde corre, y por que eso cambia todo.** `calipso/mcp_calipso.py`, stdio, hijo del CLI, **fuera del
sandbox**: como Pedro, con `~/.calipso`, `~/.ssh` y la red enteras (§2.1). Es la unica pieza del golpe que
no pasa por ninguna de las dos capas. Por eso:

- El MCP **no valida nada que importe**: corre del lado del martillo, y lo que el valide no cuenta. El
  alcance vive en el SERVER.
- El MCP **no lee ni escribe fuera del namespace del goal**, y tiene exactamente DOS escrituras, las de la
  tabla de abajo: `preguntar` (una solicitud del motor de permisos) y `nota` (un evento del ledger del
  goal), las dos con tope por golpe. No hay tool que escriba en la memoria, en la aduana ni en
  `preautorizadas` (R16 corrige el "solo lectura" del borrador de esta seccion, que la tabla ya desmentia).
- Toda salida pasa por `tapar` (`goals_manos.py:1186`) del lado del server, antes de salir. **`tapar` tapa
  CREDENCIALES DE MAQUINA, no privacidad** (R6): `detector.detectar_secretos` tiene un solo tipo,
  `"credencial"`, y barre prefijos, JWT, PEM, cadenas de conexion, hex y base32; el vocabulario humano
  (`identidad`, `salud`, `ubicacion`, `financiero`, `contacto`) vive en otro lado
  (`privacidad/juez.py:15`) y NO participa.
- El limite del goal es el token + el 401 + el alcance de un solo goal + que el goal no tiene ruta de red a
  `127.0.0.1`; `tapar` suma solo contra credenciales. La enumeracion "ni en el env ni en la argv ni en el
  ledger" **no es completa**: el token vive en el env del proceso MCP y la tool `Read` es in-process (no
  sandboxeada) y el hook la deja pasar sobre `/proc` (R9). Hay que decirlo asi, explicito, en el codigo.

**Como llega al server: un namespace propio, no una credencial mas sobre lo existente.** El server expone
`/api/goals/<id>/mcp/<tool>` -- y nada mas. El alcance no se declara en una tabla: se construye. La
credencial del goal solo abre esa ruta, y el `<id>` de la ruta tiene que ser el del token; cualquier otra
ruta es 401 aunque el token sea valido. Se prefiere esto a un tipo nuevo en `sesiones.ALCANCES`
(`sesiones.py:81-103`) porque ese molde es por prefijo y metodo, y el tipo mas parecido (`tablero`) ya
lleva `POST /api/permisos/solicitudes/` (`sesiones.py:102`), que es justo lo que un goal no debe poder
firmar. La rama nueva va en `auth_guard` (`server.py:571`), que hoy entiende tres credenciales y ninguna
mas (cookie de sesion, cookie-token y `?token=`, las dos ultimas solo desde loopback) y contesta 401 incluso
desde loopback (medido: `curl -s -i http://127.0.0.1:8000/api/goals` -> 401 `{"detail":"no autorizado"}`).

**El token (D3).** Nace al crear la sesion del bucle, no en `_lanzar_bucle` (`server.py:2728`, que lo llaman
seis sitios y hace early-return si ya hay tarea viva). Vive en `~/.calipso/goals/<id>/mcp.json`, 0600, con
esta forma, que es la que el CLI acepta (`--mcp-config` toma archivos o JSON inline; el objeto completo, no
un nombre):

```json
{"mcpServers": {"calipso": {"type": "stdio",
  "command": "/var/home/pedro/calipso/.venv/bin/python",
  "args": ["-P", "-m", "calipso.mcp_calipso"],
  "cwd": "/var/home/pedro/calipso",
  "env": {"CALIPSO_GOAL": "<id>", "CALIPSO_GOAL_TOKEN": "<token>",
          "PYTHONPATH": "/var/home/pedro/calipso"},
  "alwaysLoad": true}}}
```

**El `-P`, el `cwd` y el `PYTHONPATH` no son adorno: sin ellos el bloque es ejecucion de codigo arbitrario
como Pedro** (R1 de la adenda, medido). El CLI spawnea el MCP heredando SU cwd, que es el clon, y `-m` pone
ese cwd primero en `sys.path`; `calipso` no esta instalado en el venv, asi que el unico
`calipso/mcp_calipso.py` capaz de satisfacer el import seria el que escriba el martillo -- y escribir ahi es
familia `repo`, directo. Medido en la maquina: `PYTHONPATH=<repo>` SOLO no alcanza (el cwd gana); `-P` +
`PYTHONPATH` si, y `cwd` explicito tambien. Van los tres.

En `goal.json` NO va el token: va su sha256. El server compara hashes. Entre relanzamientos del bucle el
archivo sobrevive y el token es el mismo; **la revocacion es una sola puerta**: `goals.transicionar` al
entrar en `FINAL_STATES` (`goals.py:719`) borra el archivo y limpia el hash. No se copia el patron de
`_limpiar_preautorizadas`, que solo corre desde el runner y deja agujeros cuando el cierre viene del server.
Cada llamada revalida el estado del goal: un goal que no esta `ACTIVE` da 401.

`alwaysLoad: true` para que las tools no queden diferidas detras de tool search (el martillo tiene que saber
que tiene `preguntar` justo cuando lo necesita), y `memoria_buscar` con tope de salida propio (existe
`MAX_MCP_OUTPUT_TOKENS`: un recall sin tope le inunda el contexto).

**Las tools.**

| tool | que hace | escribe? |
|---|---|---|
| `memoria_buscar(q, k<=5)` | recall en la memoria de Pedro. **PENDIENTE DE PEDRO (P1): satisface la familia `datos_de_pedro`, que es NUNCA en su tabla.** No se implementa hasta que Pedro elija entre las tres opciones de §13 | no |
| `goal_estado()` | el goal, el consumo contra el tope, las notas de Pedro, las `falta` del juez | no |
| `aduana_resumen()` | los cruces de ESTE goal | no |
| `preguntar(pregunta, compuerta?)` | llama del lado del server al MISMO camino que `_preguntar` (`goals_runner.py:1092-1132`, con sus tres frenos: NUNCA no se pregunta, `raiz_nueva` se valida antes de estacionar, y una que el motor concede por directo no estaciona nada) y devuelve lo que ese camino decidio: `estacionada` \| `concedida_directo` \| `no_se_pregunta_es_nunca` \| `raiz_invalida`. **No espera** (D4). **Nunca escribe `preautorizadas`** (R8) | crea la solicitud, por el motor |
| `nota(texto)` | un evento propio del ledger del goal | ledger, evento propio |

**`preguntar` no bloquea (D4), y ademas tiene dos trampas que hay que esquivar.** (1) La pared de corrida
del motor devuelve la solicitud ANTERIOR ante la misma corrida y no filtra por estado
(`permisos/almacen.py:401-412`), y la corrida actual es `f'{goal}:{op}:{n}'` (`server.py:4203`): la segunda
`preguntar` del mismo golpe recibiria la respuesta que Pedro ya dio a OTRA pregunta. Se suma un contador
`vez` a la corrida y a la forma, como ya hizo `estacionar_retomar` para el mismo pozo
(`goals_runner.py:580-583`). El `vez` va en la CORRIDA (`f"{goal}:{op}:{n}:{vez}"`) y, si hace falta para la
idempotencia por forma de `almacen.crear`, en el nivel de ARRIBA de la forma de la solicitud (junto a `goal`
y `familia`) -- **nunca dentro de `forma["forma"]`**: `_aplicar_tabla` compara la preautorizada por igualdad
EXACTA de dict contra lo que devuelve `familia_de_argv`, que jamas lleva `vez`, y el si de Pedro no taparia
nada (R12). (2) Un solo consumidor de la aprobada: hoy `_evaluar_solicitud` la consume
(`server.py:2515-2521`) y el bucle del goal la sondea; el camino del MCP **no consume nunca**.

**Quien aplica el si, y por que hace falta escribirlo (R8).** Hoy lo unico que convierte un si en
preautorizada es `aplicar_respuesta` leyendo `goal["espera"]["compuerta"]` (`goals.py:790-797`), y el goal
tiene UNA sola `espera` -- pero el caso guia pide DOS compuertas en el golpe 1. Modo de falla silencioso:
Pedro dice si a las dos en el inbox y el golpe 2 sigue denegado. El camino completo: el MCP SOLO estaciona
(no toca `goal.json` ni `compuertas.json`, que son last-writer-wins) y, al cerrar el golpe, el runner junta
TODAS las solicitudes abiertas de este goal -- `_solicitud_abierta_del_goal` ya existe
(`server.py:4218-4228`) -- y las aplica en orden. Eso exige `espera` con lista, o un `aplicar_respuesta` por
solicitud: se dimensiona en la tarea 4 del corte. Y la regla de composicion: si el golpe ya estaciono por el
MCP, el veredicto `preguntar` del mismo golpe NO vuelve a estacionar (reusa la solicitud viva por `corrida`
+ `vez`).

**`nota` no usa `nota_de_pedro`.** `goals.nota_de_pedro` (`goals.py:738-745`) escribe `goal['ultima_nota']`,
que el runner reinyecta al prompt del golpe siguiente rotulada como `NOTA DE PEDRO:`
(`goals_runner.py:209`). El martillo se estaria pasando instrucciones a si mismo con la firma de Pedro: el
patron de h06 del abismo, pero con autoridad. `nota` va por un evento propio (`goals.event` con `action`
distinto) y el prompt del golpe siguiente distingue la fuente.

**La guarda del Parser: lista blanca de nombres EXACTOS.** `goals_manos.py:647-649` pasa de "ningun `mcp__`"
a "exactamente estos cinco": `mcp__calipso__memoria_buscar`, `mcp__calipso__goal_estado`,
`mcp__calipso__aduana_resumen`, `mcp__calipso__preguntar`, `mcp__calipso__nota`. Cualquier otro `mcp__*`
sigue siendo violacion que mata el golpe -- incluido `mcp__calipso__lo_que_sea` no listado y
`mcp__calipso_evil__x` (el nombre del server se normaliza: todo caracter fuera de `[a-zA-Z0-9_-]` se vuelve
`_`). La guarda es la ultima defensa si `--strict-mcp-config` se cae de la argv por un refactor: no debe
depender de la flag. **Y por eso va en DOS lugares, no en uno (R7):** el anuncio del `system/init` (lo que
hoy hay, invertido, `goals_manos.py:641-649`) **y** el nombre de cada `tool_use` en `_assistant`
(`goals_manos.py:669-684`), que es exactamente donde D5 ya pone el registro de las llamadas MCP -- no cuesta
una pieza nueva. Una tool que no aparece en el anuncio (diferida detras de tool search, que es justo lo que
`alwaysLoad` intenta evitar, o agregada despues) se llama igual y el init no la ve: un `mcp__*` fuera de los
cinco es violacion aunque el init no lo hubiera anunciado.

**El hook no las juzga; el ledger si las ve (D5).** `MATCHER_HOOK` queda como esta. A cambio, el Parser
guarda las llamadas MCP (nombre y argumentos tapados) y el runner las escribe en una clave nueva de la fila
de `golpes.jsonl` (hoy `_assistant` solo junta los `tool_use` de nombre "Bash",
`goals_manos.py:679-684`). La sonda de "hook inactivo" no las cuenta y no debe: `CON_HOOK`
(`goals_manos.py:276`, usado en `:702`) no las incluye.

**La aduana.** Cada llamada es un cruce asentado **por el server**, con `origen="goal"` (ya existe,
`aduana.py:55`) y `rutina={"kind": "goal", "id": "<id>", "via": "mcp"}` -- `Quien` exige `kind` e `id` en
`rutina` y admite claves extra (`aduana.py:88-118`), asi que no hay que tocar el dataclass congelado.
`desde.credencial` solo admite `"maquina"` o `"sesion"` (`aduana.py:57`): se declara `"maquina"` (es cierto:
loopback, mismo uid) y la distincion queda en `rutina.via` y en `endpoint`. Entrada nueva en las
EXCEPCIONES del canario.

**Asimetria declarada con codex.** `codex exec` no tiene `--mcp-config`: los MCP salen de
`~/.codex/config.toml` o de `-c mcp_servers...`, y no hay equivalente a `--strict-mcp-config`
(`--ignore-user-config` apaga todo el config.toml). En esta tanda **el MCP es solo para claude**: un goal
con `con: codex` no tiene MCP ni `preguntar` mid-golpe, y el contrato del golpe lo dice. Paridad = diseno
nuevo, §9.

## 5. `correr_app`: correr una aplicacion instalada, headless, afuera del sandbox del CLI

**Quien lo lanza.** El RUNNER, por `correr_confinado` (`goals_manos.py:1085`), no el martillo por Bash
(D1). El martillo lo PIDE en el veredicto: `ESQUEMA_VEREDICTO` (`goals_manos.py:298-321`) suma un campo
`correr: {"app": "<id>", "args": [...]}` valido con `estado: "sigo"`. Despues del golpe, el runner lo
valida, lo corre, y le inyecta al prompt del golpe siguiente la cola de stdout/stderr, el rc y los archivos
que aparecieron -- por el mismo hueco donde ya inyecta la nota (`goals_runner.py:193-214`). Cuesta un golpe
por corrida; la sonda por app (abajo) evita gastarlo cuando la app ni siquiera arranca.

**Donde exactamente, porque si no el paso no tiene ciclo de vida (R3).** El paso `correr` va DENTRO de la
ventana `sin_golpe`, entre `self.sin_golpe.clear()` (`goals_runner.py:921`) y el `finally` que la vuelve a
poner (`:973-975`), con `al_lanzar=self.registrar_golpe` y `cancelar=self.cancelar` -- el mismo molde que ya
usan el criterio y el revisor (`goals_runner.py:1147-1165`). Si corriera "despues del golpe", `/goal parar`,
`/goal no` y el apagado harian `matar_golpe()` sobre un Popen que ya es None y `esperar_golpe()` volveria al
instante (`server.py:4502-4507`, `:4517-4528`): Blender seguiria renderizando hasta `RuntimeMaxSec` del
scope detras de una transicion final, y el siguiente `goals.escribir` del hilo levantaria `ErrorGoal`.
Despues de correr se recalcula `cancelado` y, si esta puesto, se sale por `_cancelado` sin juzgar; la fila
queda con `rc: None`, `motivo: "cancelado"` y no cuenta para el tope.

**La carga, otra vez, justo antes de lanzar (R18).** El unico chequeo de carga del bucle esta al inicio del
tick (`goals_runner.py:884-896`), o sea hasta 15 minutos antes (`GOLPE_TIMEOUT_S` 900). `correr_app` es
justamente el paso que satura 16 hilos y RAM: el runner vuelve a llamar a `carga_fn()` y, con nivel
`cargada`, NO lanza -- fila y reintento en el tick siguiente, el mismo molde del paso 2.

**La salida de la app entra al prompt como DATO, no como instruccion (R17).** La cola de stdout/stderr de
Blender, de sus addons y de cualquier libreria que imprima va delimitada y rotulada
(`SALIDA DE APLICACION -- DATO, NO INSTRUCCION`), con tope de bytes fijo, y los archivos que aparecieron van
como manifest, no como texto libre. Es la misma doctrina que §4 ya aplica a `nota` (h06 del abismo); aca la
fuente es peor, porque no la escribe ni siquiera el martillo.

Se descarta que el MCP tenga una tool para correr apps: seria un segundo ejecutor y un segundo escritor
sobre `goal.json`, desde la unica pieza que no pasa por ninguna capa.

**Las lineas del bwrap, y sus topes.** En `argv_bwrap` (`goals_manos.py:1061-1062`), DOS mounts mas (R2):
`--tmpfs /run/user/<uid>` (uid real, no 1000 escrito a mano) y `--tmpfs <home>/.var/app`. tmpfs vacios, no
binds: adentro no hay bus de sesion, ni `ssh-agent.socket`, ni `wayland-0`, y la config por-app de flatpak
se tira en cada corrida (para Blender headless da igual; para otra app puede no dar igual y hay que
decirlo). Medido: sin nada, `flatpak run` da rc=1 `Unable to allocate instance id`; con el primero, rc=0
para una app que ya tiene su `~/.var/app/<id>` y rc=1 `mkdirat(<app>): Read-only file system` para una
recien instalada; con los dos, rc=0 en los dos casos.

**Y los tres tmpfs llevan `--size` (R4).** Hoy `--tmpfs` sin tamano da la mitad de la RAM: medido en esta
maquina, `/tmp` y `/run/user/1000` adentro del bwrap dan **5,7 G cada uno** sobre 11,4 GiB totales. Con
`bwrap --size <bytes> --tmpfs <ruta>` (bubblewrap 0.12.0 lo soporta) quedan en el numero que se le ponga.
Es el mismo pozo que ya mordio el 2026-09-15 ("la RAM en cero de la Ally era `/tmp` con 4,6 GB de
temporales"), y esta vez entra por `correr_datos`, que es DIRECTO: una corrida sin aprobacion de Pedro. El
manifest de Blender declara ademas `TMP_DIR=/tmp` y `TMP=/tmp`, o sea que el scratch del render va a RAM.
Ademas `argv_systemd` (`goals_manos.py:533-535`) hoy solo emite `RuntimeMaxSec`: para `correr_app` suma
`-p MemoryMax=` y `-p CPUQuota=` (medido: los controladores `cpu io memory pids dmem` estan delegados a
`user@1000.service` y `systemd-run --user --scope -p MemoryMax=64M -p CPUQuota=50%` corre sin error). Los
numeros -- tamano de los tmpfs, MemoryMax, CPUQuota y el timeout -- los pone Pedro (P5 de §13): es su
maquina y su sesion.

Se conservan `--unshare-net` (`:1072`), los tmpfs sobre `~/.calipso`, `~/.ssh` y el resto de PROTEGIDAS
(`:1067-1071`) y el `--tmpfs /tmp` que ya estaba (`:1061`).

**La validacion, a mano, porque no hay hook.** Antes de lanzar, el runner llama a
`goals_hook.familia_de_argv(argv, compuertas)` (`goals_hook.py:1254`) y aplica la tabla por el mismo camino
que el hook. Para que sea UN solo camino y UN solo test, se expone
`goals_hook.decidir_argv(argv, compuertas) -> Decision`, que compone `familia_de_argv` con `_aplicar_tabla`
(`goals_hook.py:1378-1397`). Si la decision es negativa, no se lanza nada y el goal pide la compuerta. Si es
positiva: fila **en `hook.jsonl`** con la MISMA forma que `goals_hook.anotar` (`goals_hook.py:1489-1503`),
marcada `tool: "correr"` y ANTES de lanzar, con la misma regla fail-closed -- si no se puede escribir, no se
corre. El archivo importa y el borrador lo decia mal (R10): `compuertas_usadas` NO lee `golpes.jsonl`, lee
el `registro` del hook (`goals_runner.py:271-296`, y descarta toda fila sin `familia` en `:288-289`), que es
de donde salen el resumen de compuertas usadas y la carga del cruce de aduana. Ademas: scope systemd con
`unidad` (y sus topes, arriba), cruce de aduana, y un **timeout con numero** -- `CORRER_TIMEOUT_S`, no
"timeout propio" (R19): todos los demas caminos lo tienen escrito (`GOLPE_TIMEOUT_S` 900,
`CRITERIO_TIMEOUT_S` 600, `TIMEOUT_REVISOR_S` 300, `TIMEOUT_CABEZA_S` 180, `TIMEOUT_SONDA_S` 20); el valor
lo pone Pedro (P5). Lo bueno de D1 que conviene decir explicito para que nadie lo "arregle": como
`correr_app` corre AFUERA del golpe, `GOLPE_TIMEOUT_S` **no** lo alcanza.

**Los minutos contra el tope, con la clave nombrada (R11).** `consumo` suma `duracion_ms` de las filas
fundidas por `n` con last-wins (`goals.py:849-875`), asi que las dos opciones obvias estan mal: con el mismo
`n`, la fila de `correr` PISA la `duracion_ms` del golpe y se pierden los minutos del martillo; con un `n`
nuevo, cuenta como un GOLPE entero contra los 8. Va una clave propia, `duracion_correr_ms`, en la fila del
MISMO `n`, y `consumo` la suma aparte de `duracion_ms`. Un test lo fija.

**El ejecutable se resuelve por ruta absoluta, NO por `resolver_exe` (R13).** `correr_confinado` hoy resuelve
`argv[0]` con `resolver_exe`, que prefiere `<cwd>/.venv/bin/<exe>` (`goals_manos.py:1016`) y pone ese
directorio primero en el PATH (`:1102`, `:1105`) -- y el cwd es el clon, que el martillo escribe con nivel
directo. Medido: con un `<clon>/.venv/bin/flatpak` plantado, `resolver_exe("flatpak", clon, "/usr/bin:/bin")`
devuelve el plantado. Con eso, lo que valida `decidir_argv` no es lo que se ejecuta y la gramatica entera
queda decorativa. Por eso: la tabla `APPS` guarda la **ruta absoluta** del ejecutable (`/usr/bin/flatpak`,
`/usr/bin/ffmpeg`), resuelta sin symlinks y verificada fuera del clon y de las raices; `correr_confinado`
recibe un `resolver=False` (o `correr_app` usa una variante propia) y no toca el PATH del clon. Y entre
`decidir_argv` y el `Popen` no puede cambiar nada: el script y los destinos se resuelven a rutas reales UNA
vez y se lanza con esas, no con las que escribio el martillo.

**Las dos familias (D2).** El nivel es por app, y la maquinaria es por familia: se parten en dos, y las dos
van en las tres tablas.

| familia | nivel | apps | por que |
|---|---|---|---|
| `correr_datos` | directo | `ffmpeg` (instalado: `/usr/bin/ffmpeg`) | transforma datos; no acepta script ni macro |
| `correr_app` | pregunta | `org.blender.Blender` (se instala en el caso guia) | ejecuta codigo ajeno (`-P`) |

**`pandoc`, `org.gimp.GIMP` y `libreoffice` SALEN de la tabla en esta tanda (R23).** No estan en la maquina
(`which pandoc libreoffice gimp` -> los tres "no encontrado"; `flatpak list --app` -> 12 apps, ninguna es
GIMP ni Blender), asi que entraban a una tabla que se presenta como medida sin una sola medicion; y para
`pandoc` el argumento "no acepta script" ademas es falso: `--filter` corre un ejecutable y `--lua-filter` un
script. Quedan declaradas como futuras, cada una con su sonda. El smoke ejercita `ffmpeg` para
`correr_datos` y Blender para `correr_app`.

Una app que no este en la tabla de apps DENIEGA antes de llegar a la tabla de niveles. Una familia sin nivel
tambien deniega (`goals_hook.py:1397`): las dos puertas cierran para el mismo lado.

**La preautorizada es por app, no por argv.** Forma `{"app": "org.blender.Blender"}`. Motivo: el dict se
compara por igualdad EXACTA (`goals_hook.py:1391-1393`), y con las argv largas de una app un `si` taparia
una sola linea y Pedro contestaria diez veces lo mismo. Lo que hace segura a la preautorizada por app es que
**la gramatica no es negociable**: se valida siempre, antes de la tabla de niveles, como ya hace el chequeo
de familias NUNCA (`goals_hook.py:1382`).

**La gramatica por app.** Tabla `APPS` en `goals_hook.py`, una entrada por app:

- **headless obligatoria**: al menos una de las banderas declaradas (`-b`/`--background` en Blender,
  `--headless` en libreoffice). Sin ella, DENEGAR.
- **prohibidas del envoltorio flatpak**: `--command=`, `--filesystem=`, `--share=`, `--socket=`,
  `--talk-name=`, `--env=`, `--devel` (y sus formas con espacio).
- **prohibidas de la app**: los inline de cada una (`--python-expr`, `--python-console`, `--python-text`,
  `--enable-autoexec`, `--addons` en Blender; `-b`/`--batch-interpreter` con expresion en GIMP;
  `macro:///` en libreoffice).
- **script**: el valor de `-P`/`--python` tiene que resolver dentro del clon por la doctrina de
  `_script_del_clon` (`goals_hook.py:1178-1190`: sin variable, sin glob, fuera de la auto-escalada) **o**
  ser uno de los `SCRIPTS_DEL_REPO` -- rutas absolutas fijas bajo `calipso/manos/`, resueltas sin symlinks.
  Esa es la puerta por la que entra el script fijo de D8.
- **destinos por app**: funcion propia, no el default generico de `_tokens_destino`, que devuelve TODOS los
  posicionales como destino (`goals_hook.py:1101-1102`) y para `flatpak run <app> -b -P script.py` daria
  basura. Los destinos tienen que caer en el clon o en las raices.
- **fuentes** (vineta nueva, R15, y la mas facil de olvidar): toda ruta de la argv que NO sea destino se
  resuelve y pasa por `_protegida_para_leer` (`goals_hook.py:1305`), `_abarca_el_home` (`:1307`) y la regla
  `raiz_nueva` de `_bajo_home` (`:1334-1335`) -- los mismos tres chequeos que el hook aplica hoy a todo
  `EXES_CON_RUTAS`. Sin esto, como la rama `run` devuelve temprano, ninguno corre: adentro de
  `correr_confinado` el sistema entero esta montado de lectura (`--ro-bind / /`, `goals_manos.py:1061`) y
  solo DENY_READ + PROTEGIDAS se tapan, asi que `~/Documents`, `~/repos` y el resto del home son legibles, y
  `pandoc ~/lo-que-sea.md -o <clon>/out.md` con `correr_datos` en DIRECTO seria una primitiva de "copiar
  cualquier archivo del home al clon" sin preguntarle a Pedro -- de donde viaja al contexto y a la API. El
  ruling 22(c) del spec de goals ya clasifico eso como `raiz_nueva` (pregunta) para el hook.
  `decidir_argv` devuelve la familia **MAS restrictiva** de las dos (fuente y destino), no la de la app.

**Los tres caminos de invocacion, y el agujero que se cierra.** `flatpak run <app>` (rama nueva en
`goals_hook.py` ANTES del `DENEGAR` de `:1364`); un ejecutable de `~/.local/bin` (cuarta categoria en
`_exe_de`, `goals_hook.py:1116-1135`, sin relajar `ALLOW_EXES`); y un binario del clon o del venv. Este
ultimo es hoy una puerta trasera: `if exe in ALLOW_EXES or donde in ("venv", "clon")` devuelve familia
`None` -- allow silencioso, sin chequeo de destinos y sin fila con familia (`goals_hook.py:1373`) --, asi
que copiar el binario al clon saltea la compuerta entera. En esta tanda se cierra **para las apps de la
tabla**, y se cierra por **FORMA, no por nombre** (R20): cerrarlo por el nombre del ejecutable lo desarma
una linea, porque `_exe_de` toma el basename (`goals_hook.py:1116-1118`) y
`cp $(which flatpak) <clon>/zz && ./zz run org.blender.Blender -P x.py` da exe=`zz`, donde=`clon`, y cae en
el allow silencioso de `:1373` sin familia -- y sin familia la fila ni aparece en `compuertas_usadas`. El
comentario de `_exe_de` (`:1119-1123`) ya registra que el martillo hizo exactamente esa maniobra en el probe
del 2026-09-15. Entonces: si el argv TIENE LA FORMA de una app de la tabla (primer posicional `run` mas un
app-id de `APPS`, o un `-P`/`--python`/`-b`/`macro:///`), la gramatica corre se llame como se llame el
ejecutable. El caso general queda abierto y declarado (§9).

**Las tres tablas y la migracion.** `correr_app` y `correr_datos` entran en `goals.COMPUERTAS`
(`goals.py:63-69`), en `permisos/goal.py:_NIVELES_DEFECTO` (`:44-50`) y en el test que las compara
(`test_goals_permisos.py:61`). Y hay una migracion escondida: cada goal creado guarda su propia copia de
`niveles` (`goals.py:650`), y las seis lecturas usan esa copia (`goals.py:1011`, `goals_runner.py:125` y
`:1096`, `permisos/goal.py:82` y `:117`, `server.py:4201`), asi que un goal viejo denegaria con "familia sin
nivel en la tabla". Se agrega **un solo helper**, `goals.niveles_de(goal) -> {**NIVEL_DE, **copia}`, y las
seis lecturas pasan por el. Es seguro porque el unico escritor de esa copia es `crear` (grep de `"niveles"`:
seis lectores, un escritor): nadie baja un nivel a proposito, asi que fusionar no pisa ninguna decision de
Pedro.

**La sonda por app (D8).** Antes de la primera corrida real de una app en un goal, el runner la ejecuta con
un script del repo que imprime un marcador literal (`CALIPSO_SONDA <app> ok`), timeout corto, bajo el mismo
`correr_confinado`. Se decide **por el marcador en stdout**, no por el returncode. Resultado y salida van al
ledger. Si falla, el goal no gasta el golpe: `preguntar` con la cola de la salida. Esto atrapa barato las
tres cosas que mas probable rompan: la app no instalada, el mount que falta, y el flatpak que arranca pero
no puede escribir. **"Ya sondee esta app en este goal" vive en el LEDGER del goal, no en el Runner** (R23):
el molde parecido, `self.hook_sondeado` (`goals_runner.py:668`, `:872-876`), es por instancia y se pierde en
cada relanzamiento del bucle, asi que con retomar/apagado la sonda se repetiria en cada arranque. Un evento
propio del ledger, leido desde ahi, sobrevive. Y una regla de una linea: un campo `correr` que llega con
`estado` distinto de `sigo` **se ignora y deja fila**; no invalida el veredicto.

**Sin GPU.** Dentro del bwrap `/dev` no tiene `dri` (medido). Render por Workbench o Cycles CPU. Abrir la
GPU seria `--dev-bind-try /dev/dri /dev/dri` en `argv_bwrap`: no se hace en esta tanda (§9).

## 6. Las imagenes del goal (los ojos, version 0)

El veredicto suma `imagenes: [<rutas del clon>]` en `ESQUEMA_VEREDICTO` (`goals_manos.py:298-321`). El
runner las copia despues del golpe, en el hueco que ya existe (`goals_runner.py:932-950`), donde corre
**fuera** del sandbox y si puede escribir en `~/.calipso` (el martillo no).

Reglas, todas porque la entrada la escribe el martillo:

- **PRIMERA, y la que faltaba (R5): la ruta ORIGEN tiene que caer dentro del clon.** Cada ruta se resuelve
  con `Path.resolve()` (symlinks seguidos) contra el clon y tiene que dar `_en_alcance(p, compuertas) ==
  "repo"`; lo que no cae adentro no se copia y deja fila en el ledger diciendo por que. Sin esta regla,
  `imagenes: ["../../../.ssh/id_ed25519"]` o un symlink del clon a `~/.ssh/id_ed25519` deja el archivo
  copiado bajo `~/.calipso` con nombre canonico y servido por la API: el veredicto lo escribe el martillo y
  `StructuredOutput` es allow incondicional en el hook (`goals_hook.py:1462`), y el copiador corre fuera del
  sandbox como Pedro, sin `denyRead`. No hace falta ni symlink: basta una ruta relativa que salga del clon.
- **Renombrado canonico generado por el server**: `<n>-<k>.<ext>`. Nunca el nombre del martillo (es la unica
  forma robusta de cumplir el "tapado" que pedia el borrador). `<n>` es el numero de GOLPE y `<k>` el indice
  dentro del golpe; ese nombre es detalle interno y no es el `{n}` de la URL (abajo).
- **Topes antes de copiar**: cantidad por golpe, tamano por archivo, **dimensiones** (un PNG de colores
  planos es chico en disco y caro en contexto: los tokens de imagen escalan con el tamano, no con los
  bytes) y **firma de bytes, no extension** (R5): magic de PNG/JPEG/WebP verificado antes de copiar, y el
  renombrado usa la extension que dice el magic, no la que dijo el martillo. **SVG no**: servido inline es
  HTML ejecutable en el mismo origen que tiene la cookie de Pedro.
- **Se sirve por INDICE, nunca por nombre**: `GET /api/goals/{id}/imagenes/{n}`, con el molde de
  `api_job_artifact` (`server.py:6670`). Servir por nombre es traversal directo y el `_safe` de
  `server.py:1171` no sirve (es relativo al ROOT y ademas veda `~/.calipso`). El `{n}` de la URL es el
  indice 0-based en la lista publicada, ordenada por (golpe, k); esa lista es la fuente de verdad.
  Content-Type FIJO de la lista blanca y `X-Content-Type-Options: nosniff`.
- La lista va en `_goal_con_consumo` (`server.py:6473`) para que la vean los dos frentes.
- **`goal-imagenes/` no se commitea**: vive dentro del clon y al `complete` la rama del clon se trae al repo
  real (`goals_runner.py:598-610`), asi que un `git add -A` del martillo le metia a AvesCO los PNG de
  trabajo. O las imagenes viven en `dir_trabajo` (fuera del clon), o el runner escribe `goal-imagenes/` en
  el `.git/info/exclude` del clon al crearlo.

**Los dos frentes son dos trabajos, no uno.** En /fabrica: una tira en `tarjetaDeGoal`
(`calipso/web/fabrica/goals.js:128-143`) con el molde que ya existe para las capturas web -- `<img>` +
`loading="lazy"` + `onerror` (`calipso/web/index.html:1296-1302`) -- mas `Cache-Control` (los dos frentes
repintan cada 60 s, `calipso/web/fabrica/app.js:1517`). En la PWA: en el **detalle** (`showGoal`,
`calipso/web/index.html:2004`), NO en la `#goalBar`, que es una fila de 34 px donde `renderGoal` escribe
solo con `textContent` (`calipso/web/index.html:64-74`, `:357`, `:1982`). La barra queda como esta.
**"via `addDetail`" no alcanza (R24):** `addDetail` escapa todo y lo mete en un `<pre>`
(`calipso/web/index.html:1960-1971`), asi que un `<img>` pasado por `body` sale como texto literal -- que es
justo lo que el test del front verifica que pase. El camino concreto: `appendChild` de la tira sobre el nodo
`<details>` que `addDetail` DEVUELVE, o una funcion hermana (`addDetailConImagenes`). Hoy no hay ningun test
del detalle de la PWA: §10.1 le suma la fila.
(Las rutas del front en este spec llevan el prefijo del paquete: son `calipso/web/*`, no `web/*`.)

**Al revisor, las rutas del clon.** No las copias: el revisor corre con `denyRead` sobre `~/.calipso`
(`goals_manos.py:280-281`). Si se le pasan las copias, el paso 7 del caso guia se queda sin ojos justo donde
esta su unica verificacion de modelo.

## 7. La propuesta automatica desde el chat

**La decision (D6): se dispara siempre que haya manos. Y por eso la deteccion se arregla ANTES de cablear
nada.** Esta seccion es una compuerta de medicion, no una opinion: el banco existe y el numero esta medido.

**El numero de hoy.** La regex `dispatch.MANOS` (`dispatch.py:144-149`, usada en `:184` y `:206`), medida
con `experimentos/banco_manos.py` contra `~/.calipso/experimentos/banco_manos.jsonl` (449 mensajes reales de
Pedro sacados del historial de Claude Code, 0600, fuera del repo; rama `feat/historial-export`), sobre los
245 que son mensajes de CHAT: **aciertos 60%, precision 67%, recall 8%**, 4 falsos positivos y 95 falsos
negativos. No sobre-dispara: esta ciega.

**El hallazgo que cambia la forma de la pieza.** El **41%** de los pedidos con manos de Pedro son
continuaciones cortas: "dale, escribilo", "merge y push", "reinicia el servidor y sigamos", "arranca la Fase
2". Ningun detector que mire el mensaje AISLADO puede acertarlos ni en principio. **La pieza no es un
clasificador de mensajes: es mensaje + contexto del turno anterior.**

**La forma.** `dispatch.necesita_manos(texto, contexto) -> "si" | "dudoso" | "no"`, determinista y a cero
tokens, en dos capas:

1. **Mensaje aislado**: la regex de hoy, ampliada con lo que el banco muestra que se pierde. Atrapa los
   pedidos explicitos.
2. **Continuacion**: si el mensaje es corto y es una continuacion ("dale", "hacelo", "segui", "mergea y
   push"), hereda la etiqueta del turno anterior. Para eso el turno anterior tiene que dejar marca: el chat
   ya guarda meta en `chats.append` (`server.py:5781`), asi que se suma ahi `manos: true|false` y la capa 2
   la lee. Nada de re-clasificar texto con un modelo.

**Los tres caminos, y por que el intermedio es el que hace barata la equivocacion.** `si` -> propone el goal
(una llamada frontera, unidades cobradas, tarjeta en el inbox). `dudoso` -> el turno contesta como hoy y
termina con una linea: "esto tiene manos: `/goal <texto>`" (cero costo, cero tarjetas). `no` -> nada.

**La compuerta de medicion, con el piso explicito.** La asimetria esta medida en el codigo: un falso
positivo cuesta una llamada frontera, **unidades cobradas** (`server.py:4412-4422`: la propuesta escribe su
fila y llama `_cobrar_golpe`), un goal `proposed` y una tarjeta en el inbox de Pedro; un falso negativo solo
deja las cosas como hoy (el chat contesta honesto, sin manos). Por eso el piso es asimetrico, y se mide con
`experimentos.banco_manos.medir(detector)`, que ya devuelve `precision_pct`, `recall_pct`,
`falsos_positivos` y `falsos_negativos` separados justamente por esto:

**Antes de medir nada hay que arreglar el banco y `medir`, porque como estan el piso no es medible (R25).**
Tres incompatibilidades verificadas: (a) `medir(detector: Callable[[str], bool])` llama `detector(f["texto"])`
con UN argumento y el detector de §7 es `necesita_manos(texto, contexto)`; (b) hace `bool(detector(...))`, y
`bool("dudoso")` es True, asi que un detector de tres valores cuenta cada `dudoso` como positivo y hunde la
precision, que es la mitad del piso; (c) `cargar()` termina en
`[f for f in filas if f["etiqueta"] in ("manos","no_manos")]` y las continuaciones tienen etiqueta propia:
quedan AFUERA de los 245 (conteo real del banco: 449 filas totales; 326 de chat = 142 `no_manos` + 103
`manos` + 71 `continuacion` + 10 `para_pedro`; lo que `cargar()` devuelve = 245). O sea que el 41% que es la
razon de ser de la capa 2 **no puede mover ese numero ni en principio**. Y el banco no tiene id de
conversacion (claves: `texto`, `etiqueta`, `confianza`, `por_que`, `fuente`, `linea`, y `frontera` en 37
filas): no hay con que reconstruir "el turno anterior del MISMO chat".

Por eso el piso va **partido en dos**, y la tarea 5 presupuesta el trabajo de banco:

- **Capa 1, sobre los 245 con `medir` tal cual.** No se cablea el camino `si` hasta que: precision >= 95% (a
  lo sumo 1-2 falsos positivos) y recall >= 60% (pasar de 8 a 62 de 103 con la regex sola).
- **Capa 2, sobre las 71 continuaciones de chat.** Exige un banco NUEVO -- filas con el turno anterior y su
  etiqueta, re-exportadas con `historial_export.py` conservando el id de conversacion, que el banco de hoy
  no guarda -- y una funcion nueva, `medir_con_contexto(detector, filas)`, que pase `(texto, contexto)` y
  mapee explicitamente los tres valores a positivo/negativo (declarando si `dudoso` cuenta como positivo o
  se mide aparte). El piso de la capa 2 se fija cuando exista el banco; sin el, la capa 2 no se cablea.
- **Y el banco hay que TRAERLO**: `experimentos/banco_manos.py` (y `historial_export.py`) viven solo en la
  rama `feat/historial-export`, sin mergear. El test de regresion del detector ademas SALTA (skipif) si el
  jsonl no esta: vive en `~/.calipso/experimentos/`, que `correr_confinado` tapa con tmpfs
  (`goals_manos.py:1029-1043`), asi que un `hasta: pytest en verde` de cualquier goal futuro no lo ve.
- Mientras no se cumpla, la pieza entra igual pero **solo con el camino `dudoso`**: sugerir la linea no le
  cuesta a Pedro ni una unidad.
- **Ampliar la capa 1 es un cambio de RUTEO, no solo de propuesta (R26).** `dispatch.MANOS` ya tiene dos
  consumidores vivos: `dispatch.py:206` sube la complejidad a 4 (fuera del 7b y de haiku) y
  `server.py:3097` apaga el equipo. Con el recall de hoy eso toca ~8 de los 245 mensajes; con el piso,
  ~60: 7,5x mas turnos forzados a frontera, aunque el camino `si` no se cablee nunca. Antes de ampliarla se
  mide ese costo contra el mismo banco (cuantos pasan de local/haiku a frontera y que cuesta), o
  `necesita_manos` usa regex propia y `MANOS` queda como esta para el router. Como esta escrito, "el camino
  dudoso no le cuesta a Pedro ni una unidad" es falso.
- Los 12 casos que quedaron para Pedro se resuelven antes de medir el numero final.
- El test de regresion del detector vive con el banco y corre con cada cambio de la regex o de la capa 2.
- Si la capa determinista no llega al piso, la respuesta NO es cablear igual: es medir un clasificador chico
  contra el mismo banco, con el mismo piso, antes de tocar el chat.

**Los frenos que el borrador daba por hechos y NO existen.** (1) "Un goal en curso, no se propone otro":
`goals.crear` nace en `PROPOSED` sin consultar `activo()` (`goals.py:621-650`); el unico chequeo esta al
transicionar a `ACTIVE` (`goals.py:709-713`). Hay que escribirlo: si hay un goal activo, o si ya hay un
`proposed` abierto, no se propone -- se dice. (2) La firma real es
`_proponer_goal(d: dict, texto_crudo: str, departamento: str|None)` (`server.py:4286`), y el dict hay que
armarlo a mano: pasar el mensaje por `goals.parse_goal_texto` (`goals.py:947-960`) lo mutila -- se come la
primera palabra si es `dale/no/parar/segui/estado` y parte el texto en cualquier `hasta:`/`en:`/`con:` que
Pedro escriba en una frase normal. (3) "El repo que nombre" no existe como capacidad: `_proyecto_del_goal`
(`server.py:4273`) solo mira `en:` o cae al ROOT si es git. (4) Si la maquina esta cargada o la cuota al
limite, el camino `si` degrada a `dudoso`.

**Donde engancha.** Despues del `chats.append` (`server.py:5781`) y antes del `done` (`server.py:5851`), en
`asyncio.to_thread` (la propuesta es sincrona y hace una llamada frontera) y con su propio try/except: un
fallo proponiendo no puede romper el turno de chat.

## 8. Compuertas y seguridad: lo que cambia de verdad

**La tabla de Pedro CAMBIA** (el borrador lo presentaba bajo "lo que no cambia"): entran `correr_datos`
(directo) y `correr_app` (pregunta), D2. Lo demas queda: directo = `repo`, `web`, `instalar_en_goal`,
`raices`; pregunta = `merge`, `push`, `borrar_fuera`, `raiz_nueva`, `instalar_home`, `instalar_sistema`;
NUNCA = `gastar`, `publicar`, `correo`, `datos_de_pedro`, `rpm_ostree_rebase`, `flatpak_remote_delete`
(`goals.py:63-69`). `preguntar` pasa por el motor como una solicitud mas y no abre ninguna. **Pero
`memoria_buscar` SI abriria una, y es NUNCA: `datos_de_pedro`** (R6). Esta frase decia "El MCP no abre
ninguna" y contradecia a §4, que admite que el MCP corre como Pedro con `~/.calipso` entero. La memoria vive
bajo `~/.calipso` (`memory.py:42-43`, `:204`, `:212`, `:228`), que esta en PROTEGIDAS del hook
(`goals_hook.py:90-91`) y en DENY_READ del sandbox (`goals_manos.py:280-281`): hoy toda lectura del martillo
sobre esa ruta muere como `NUNCA: ... datos de Pedro` (`goals_hook.py:1306` por Bash, `:1420` por
Read/Grep/Glob), cortada por NOMBRE y ANTES de la tabla (`:1382-1384`), y ademas va tapada con tmpfs dentro
del confinado. `memoria_buscar` la entregaria por la unica puerta sin hook ni `denyRead`. **Queda como P1 de
§13 y no se implementa hasta que Pedro decida.**

Lo que esta version agrega como invariantes escritas:

- **El MCP es codigo de seguridad**, no un adaptador: corre como Pedro, fuera de las dos capas. Sin tools de
  escritura, `tapar` en toda salida, alcance en el server, token con vencimiento por estado del goal.
- **El token nunca en el env del golpe ni en la argv** (D3). Un test lo fija: `env_del_golpe` no contiene el
  token, y la argv tampoco. **Lo que esa enumeracion NO cubre, y hay que escribir (R9):** el token vive en
  el env del proceso MCP, que es un hermano del mismo uid. Por Bash no se llega -- medido: adentro del bwrap
  del CLI (`--unshare-user --cap-drop ALL`), leer `/proc/<pid>/environ` de un hermano da `Permission
  denied`, y con `enableWeakerNestedSandbox` (prohibido, abajo) si se llegaria. Pero la tool `Read` es
  **in-process y NO sandboxeada** (el mismo argumento que §2.1 usa para probar que el MCP no esta
  confinado: "Enforced for sandboxed commands only - in-process tools such as WebFetch are not gated") y el
  hook la deja pasar sobre `/proc`, que no es protegida ni esta bajo el home (`decidir_archivo`,
  `goals_hook.py:1415-1428`). O sea: el martillo puede leerse el token con una llamada `Read`. El limite
  real es el 401, el alcance de un solo goal y que el goal no tiene ruta de red a `127.0.0.1`.
- **El token tiene vencimiento propio** ademas del estado del goal (por ejemplo la ventana del tope de
  minutos): la revocacion por `transicionar` es puerta unica y buena, pero un goal colgado en `ACTIVE`
  (crash del bucle, reboot, tarea muerta) dejaria el archivo 0600 vivo indefinidamente.
- **No se abre `127.0.0.1` en la red del goal**: innecesario (§2.1) y, si se abriera, seria para todo
  comando Bash del golpe, no solo para el MCP.
- **No se usa `sandbox.enableWeakerNestedSandbox`** ("exposes the host /proc") ni se bindea el
  `$XDG_RUNTIME_DIR` real.
- **La gramatica por app manda sobre la preautorizada**: un `si` a una app no es un `si` a cualquier argv de
  esa app.
- **Modo de falla declarado**: el `si` mid-golpe vale para compuertas (el hook relee `compuertas.json`,
  `goals_hook.py:1477-1487`) pero NO para `web` ni `raiz_nueva`, que se congelan al lanzar
  (`goals_manos.py:462`, `:466-468`, `:503-504`, `goals_runner.py:474-488`). En el caso guia eso significa que la
  raiz `~/.local/share/flatpak` recien vale en el golpe siguiente al `si`.
- **Blender instalado por el goal vive en `~/.local/share/flatpak`** (home: pregunta, con su linea de
  deshacer). El `remote-add --user` no lo hace ningun goal (D7).
- **Servicios en internet**: navegar y comparar precios es `web`; contratar es `gastar` (NUNCA).

**Lo que esta tanda ENMIENDA del spec de goals (R31).** Hay que escribirlo como enmienda o el primer
implementador que lea el spec de goals va a creer que el MCP y `correr_app` estan cubiertos:

1. La **invariante 4** del spec de goals ("NUNCA se cumple aunque el martillo lo pida: el sandbox lo hace
   imposible y el hook lo deniega como segunda capa") pasa a: **las barreras son TRES, cada una con su
   alcance escrito** -- el sandbox del CLI para lo que lanza el CLI; `correr_confinado` + `decidir_argv`
   para lo que lanza el runner (D1: ese paso NO pasa por el hook `PreToolUse`); y token + 401 + alcance del
   server para el MCP (§2.1: la unica pieza que no pasa ni por el hook ni por `denyRead`).
2. El **ruling 15.5** ("la barrera es el sandbox, no el hook") queda acotado a los comandos que lanza el
   CLI.
3. El registro de esas dos piezas nuevas es inerte para la sonda de hook inactivo y debe seguir siendolo:
   `CON_HOOK` (`goals_manos.py:276`, usado en `:702`) no incluye ningun `mcp__*`.

## 9. Lo que NO se construye en esta tanda, y por que

- **Captura de pantalla y clicks**: es el subproyecto 3. Las imagenes del goal son lo mas cerca de "ojos"
  sin captura.
- **`preguntar` bloqueante**: D4. El inbox se repinta cada 60 s y no hay push; una espera larga clava un
  worker del threadpool, quema wall-clock del golpe y minutos del tope, y mete un segundo escritor sobre
  `goal.json` y `compuertas.json`, que son last-writer-wins.
- **El hook juzgando las llamadas MCP**: D5. Acopla `MATCHER_HOOK`, `CON_HOOK` y `decidir`; cualquier
  descuido mata toda llamada MCP por fail-closed (`goals_hook.py:1470`) o deja ciega la sonda de hook
  inactivo.
- **GPU dentro de `correr_confinado`** (`--dev-bind-try /dev/dri`): es un ensanche del sandbox por un render
  que Workbench hace en CPU. Primero se mide cuanto tarda el render sin GPU.
- **El caso general del agujero `goals_hook.py:1373`** (cualquier binario del clon o del venv es allow
  silencioso con familia `None`): se cierra solo para las apps de la tabla, y por FORMA, no por nombre
  (R20). Cerrarlo entero cambia el comportamiento de todos los goals y merece su propia tanda. **Residuo
  declarado:** un binario del clon que NO tenga la forma de una app de la tabla sigue siendo allow
  silencioso sin familia -- y sin familia la fila ni aparece en `compuertas_usadas`.
- **`pandoc`, `org.gimp.GIMP` y `libreoffice`** salen de la tabla `APPS` en esta tanda (R23): no estan en la
  maquina y no se pueden medir. Quedan declaradas como futuras, cada una con su sonda.
- **Deshacer lo instalado** no lo hace nadie hoy y esta tanda no lo construye sin el ruling de Pedro (P4).
- **`memoria_buscar`** no se implementa hasta que Pedro decida (P1). El MCP de la tarea 3 puede salir con
  `goal_estado` y `aduana_resumen` nada mas.
- **SVG en las imagenes del goal**: XSS en el mismo origen que la cookie de Pedro.
- **MCP para codex**: `codex exec` no tiene `--mcp-config` ni equivalente a `--strict-mcp-config`. La
  asimetria se declara en el contrato del golpe.
- **Reclasificar `flatpak remote-add --user` a `instalar_home`** (hoy cae en `instalar_sistema`,
  `goals_hook.py:1356`): el remote se precrea a mano (D7); tocar la clasificacion es un ruling aparte.
- **Instalar en el sistema** (rpm-ostree, `flatpak --system`): sigue siendo pregunta y no se prueba en el
  smoke.
- **merge/push automaticos, servicios pagos, codex como manos con red**: sin cambios.
- **`@anthropic-ai/sandbox-runtime`** (el `apply-seccomp` que bloquea sockets unix) no se instala. Queda
  escrito como supuesto del smoke: si alguien lo instala despues, `correr_app` puede empezar a fallar sin
  que nadie relacione la causa.

## 10. Verificacion

### 10.1 Unitarios, con el molde que ya existe en el repo

| que se prueba | molde |
|---|---|
| la gramatica por app: `flatpak run` con la forma exacta pasa; sin headless DENIEGA; con `--command=`/`--filesystem=`/`--share=`/`--socket=`/`--talk-name=`/`--env=`/`--devel` DENIEGA; `-P` fuera del clon y fuera de `SCRIPTS_DEL_REPO` DENIEGA; app fuera de `APPS` DENIEGA; destino fuera del clon DENIEGA; el binario de una app conocida copiado al clon pasa por la gramatica | `test_goals_hook.py`, fixture `goal_dir` y `familia_de_argv` pura (`test_goals_hook.py:562-565`) |
| las tres tablas identicas con las dos familias nuevas | `test_goals_permisos.py:61` |
| un goal viejo (copia de `niveles` sin las familias nuevas) NO deniega por "familia sin nivel" | test nuevo sobre `goals.niveles_de` |
| el Parser: los cinco nombres exactos pasan; `mcp__calipso__otra`, `mcp__calipso_evil__x` y `mcp__claude_ai_Google_Drive__copy_file` siguen matando el golpe | `test_goals_manos.py:328-329`, reescrito |
| la argv del GOLPE suma `--mcp-config <archivo>` y el token NO esta ni en la argv ni en `env_del_golpe` | `test_goals_manos.py:226` (el unico que toca `argv_claude`) |
| que la argv del CHAT, la de la CABEZA y la del REVISOR **no** ganan `--mcp-config` (invariante nuevo que conviene fijar ahora que el golpe si lo gana; R32: estos tres estaban citados como "arrastrados" y no lo son -- `test_seguridad_techo.py:208` es `_subscription_invocation`, `test_goals_chat.py:510` es `argv_cabeza_claude` y `test_goals_manos.py:1080` es el revisor, y ninguno se rompe: los asserts son de pertenencia o por indice, nunca igualdad de lista) | `test_seguridad_techo.py:206-210`, `test_goals_chat.py:514`, `test_goals_manos.py:1078-1088` |
| el MCP no se lanza con `-m` sobre el cwd heredado: el argv lleva `-P`, el bloque lleva `cwd` y `PYTHONPATH`, y un `calipso/mcp_calipso.py` plantado en el clon NO se ejecuta | test nuevo sobre el bloque de `mcp.json` |
| `correr_confinado` para `correr_app`/`correr_datos` no pasa por `resolver_exe`: un `<clon>/.venv/bin/flatpak` plantado no se ejecuta | `test_goals_manos.py`, molde `correr_confinado` |
| las imagenes: un symlink del clon a `~/.ssh/id_ed25519`, una ruta con `../` y un archivo de texto llamado `x.png` no producen NINGUNA copia | `test_goals_runner.py` (`Falsas`) |
| el paso `correr` corre con `sin_golpe` apagado, publica su Popen y su unidad por `al_lanzar`, y su fila queda en `hook.jsonl` (no en `golpes.jsonl`) y aparece en `compuertas_usadas` | `test_goals_runner.py` |
| el detalle de la PWA produce un `<img>` desde la URL por indice (hoy no hay ningun test de `showGoal`) | nuevo, molde `web/fabrica/goals.test.js` |
| el runner: el paso `correr` del veredicto (decision negativa no lanza nada; positiva deja fila CON familia, cruce de aduana e inyeccion de la salida en el prompt siguiente) y la copia de imagenes (renombrado canonico, topes, extensiones, SVG rechazado) | `Falsas` (`test_goals_runner.py:49`) |
| los endpoints `/api/goals/<id>/mcp/*`: 200 con el token del goal; 401 sin token; 401 con el token de OTRO goal; 401 con el goal en estado final; 401 en cualquier otra ruta con ese token | `test_sesiones_server.py` (TestClient + `_pedir`), estilo `test_inbox_server.py:86` |
| la revocacion: `transicionar` a un `FINAL_STATE` borra el archivo 0600 y limpia el hash | `test_goals.py` |
| `preguntar`: dos preguntas en el mismo golpe no se comen la respuesta de la otra (contador `vez`); el camino del MCP no consume la aprobada | `test_goals_runner.py` (molde `estacionar_retomar`) + `test_goals_permisos.py` |
| `nota` no escribe `ultima_nota` ni aparece rotulada como NOTA DE PEDRO en el prompt siguiente | `test_goals_runner.py` |
| el front: el payload `<img src=x onerror=alert(1)>` en id/title/espera sigue sin producir `<img>`, y la tira de imagenes SI produce uno desde la URL por indice | `web/fabrica/goals.test.js:89` y `:155`, reescritos (no borrados) |
| el detector contra el banco, con el piso de §7 | `experimentos/banco_manos.py` (`medir`) |

### 10.2 Lo que exige smoke real (ningun unitario lo ve)

- **S1. Sonda de terreno contra 2.1.273, ANTES del plan.** Uno o dos golpes reales, baratos, con un MCP
  trivial. Contesta: (a) bajo `--restricted --permission-mode acceptEdits --permission-prompts none`, ¿una
  tool `mcp__calipso__*` se ejecuta sola o la niega el CLI? Se mira `permission_denials` del result, no el
  exit code. (b) ¿hace falta `--allowedTools mcp__calipso__*` o `permissions.allow` en `--settings`? (c)
  ¿las cinco tools aparecen en el `system/init` sin tool search, o sea que `alwaysLoad` hace lo que promete?
  **S1 se achica: las otras dos preguntas ya estan contestadas por grep sobre el bundle, sin gastar un
  golpe** (R33). Medido en `/var/home/pedro/.local/share/claude/versions/2.1.273` (`claude --version` ->
  2.1.273): `failIfUnavailable` 20 apariciones y sigue en la lista de claves restrictivas del schema
  (literal `{path:["sandbox","failIfUnavailable"],restrictive:!0}`) -- **el bloqueante de "el sandbox falla
  ABIERTO" queda tachado antes de empezar**; `alwaysLoad` 42, `MAX_MCP_OUTPUT_TOKENS` 6,
  `strict-mcp-config` 19, `mcp-config` 83, `enableWeakerNestedSandbox` 14 con su texto "exposes the host
  /proc". Y el `hook_response` esta medido en vivo: el hook corre y deja fila. Salida: una nota de terreno y
  la version del CLI fijada.
- **S2. `flatpak install --user` dentro del sandbox del CLI**, con una app chica (`org.kde.kcalc`), con
  `~/.local/share/flatpak` declarado como raiz y `dl.flathub.org` en `dominios`. **Se adelanta a la tarea 0
  junto con S1** (R34): es igual de barato y puede invalidar el paso 4 del caso guia. Lo que se mide, **en
  este orden, porque la red falla primero**: (1) ¿`flatpak`/`libostree` usa el proxy socks/http que el
  sandbox del CLI monta, o ignora `HTTP_PROXY` y muere sin red? (2) ¿el install necesita `/tmp` escribible o
  `$XDG_RUNTIME_DIR`? (el terreno midio `flatpak run`, no `install`). **La salida de emergencia que este
  spec proponia -- "el install tambien se muda a `correr_confinado`" -- NO EXISTE** (R34): `argv_bwrap`
  lleva `--unshare-net` incondicional (`goals_manos.py:1072`) y un install sin red no baja 477 MB; es una
  invariante escrita del cierre 2026-09-14 (adenda 18). Si S2 sale mal, las opciones reales son (a) un
  tercer camino (bwrap propio CON red por allowlist, que es un parametro nuevo y una decision aparte), o (b)
  que el install lo haga Pedro a mano, extendiendo D7 a la instalacion de la app (P3 de §13).
- **S3. `correr_confinado` + `--tmpfs /run/user/<uid>` + Blender headless con el script fijo**: el `.glb` y
  el PNG, con el tiempo del render sin GPU medido.
- **S4. El MCP en vivo**: `memoria_buscar`, `goal_estado`, `preguntar` estacionada que aparece en el inbox,
  y la revocacion al cerrar el goal (la llamada siguiente da 401).
- **S5. El caso guia entero** contra `~/repos/AvesCO`, con el remote `--user` precreado, y el
  `flatpak uninstall --user` al final. Con la maquina medida **en el momento de correrlo, con la metrica
  correcta** (R35): el "~475 MiB libres" que este spec copio del terreno era MemFree y esta mal como criterio
  -- la doctrina de `carga.py` es MemAvailable ("los avisos siguen diciendo N MB libres con MemAvailable,
  que es lo que Pedro entiende"). Medido hoy: MemFree 557 MiB vs **MemAvailable 6,7 GiB**, y `/tmp` es tmpfs
  de 5,7 G con 5,0 G disponibles. El criterio de arranque se escribe como "MemAvailable >= X MiB", y el
  riesgo de RAM no es que falten 475 MiB sino que los tmpfs sin `--size` puedan pedir 11,4 GiB (R4).
  Blender son 477,4 MB de descarga y 1,1 GB instalado. Y la plata esperada: ~3 USD la pasada limpia (8 x
  0,32 USD de golpe + 0,23 de la cabeza + el revisor), ~9 USD con dos o tres pasadas de depuracion.

### 10.3 No confirmado, con el experimento exacto que lo confirmaria

| no confirmado | experimento |
|---|---|
| ¿una tool `mcp__calipso__*` se ejecuta sola bajo `--permission-prompts none`, o el CLI la niega? | S1(a): golpe real con MCP trivial, mirar `permission_denials` |
| ~~¿sigue existiendo `sandbox.failIfUnavailable` en 2.1.273?~~ **CONTESTADO por grep (R33)**: si, 20 apariciones, y sigue como clave restrictiva del schema (`{path:["sandbox","failIfUnavailable"],restrictive:!0}`). Idem `alwaysLoad` (42) y `MAX_MCP_OUTPUT_TOKENS` (6) | -- |
| ¿`flatpak`/`libostree` respeta el proxy socks/http del sandbox del CLI? | S2, PRIMERA pregunta: sin esto el paso 4 del caso guia no toca la red |
| ¿el martillo puede leerse el token del MCP con `Read` sobre `/proc/<pid>/environ`? (por Bash NO: medido, `Permission denied` adentro del bwrap del CLI) | S1/S4: un golpe de sonda que lo intente |
| ¿cuanto pide de red el enlace de Pedro? 477,4 MB en 900 s = 4,24 Mbit/s sostenidos | S5, medido ANTES de arrancar |
| ¿`flatpak install --user` necesita `/tmp` o `$XDG_RUNTIME_DIR` escribibles? | S2 con `org.kde.kcalc` |
| ¿que rutas escribe `flatpak install --user` ademas de `~/.local/share/flatpak` (¿`~/.cache`?) | S2, mirando que falla y agregando raices de a una |
| ¿una app `--user` usa el runtime que ya esta en el system, o baja 660 MB mas? | S2/S5: `flatpak install --user` y mirar lo que descarga |
| ¿cuanto tarda el render sin GPU en esta maquina? | S3, con el spec del colibri |
| ¿flatpak sobrevive si alguien instala `@anthropic-ai/sandbox-runtime` (seccomp sobre sockets unix)? | fuera de esta tanda; queda como supuesto del smoke |
| ¿el martillo entiende el SPEC JSON y no intenta escribir `bpy` igual? | S5: mirar el ledger del goal; si insiste, el contrato del golpe lo dice mas fuerte |

## 11. El corte: tareas en orden, cada una con lo que la bloquea

**0. Sonda de terreno contra 2.1.273 (S1) + la sonda del install (S2).** *Bloquea a*: la 3 y la 4 enteras
(S1) y el paso 4 del caso guia (S2). *La bloquea*: nada. Baratas, y son lo unico que puede tirar abajo el
MCP entero o el install. S1 ya viene achicada por el grep del bundle (R33); S2 se adelanta aca porque es
igual de barata y igual de invalidante (R34), y mide la RED primero. Salida: nota de terreno + version del
CLI fijada.

**1. `correr_app` / `correr_datos` por `correr_confinado`.** *La bloquea*: nada (no depende del MCP). Es la
tarea de mayor valor y menor riesgo. Partes: (a) `--tmpfs /run/user/<uid>` en `argv_bwrap`
(`goals_manos.py:1061`), mas `--tmpfs <home>/.var/app` y `--size` en los tres (R2, R4), mas `MemoryMax` y
`CPUQuota` en `argv_systemd`; (b) rama `run` en `goals_hook.py` antes del `DENEGAR` de `:1364`, con la tabla
`APPS` (rutas ABSOLUTAS del ejecutable, R13) y la gramatica, incluida la vineta de **fuentes** (R15) y el
cierre **por forma** (R20); (c) `decidir_argv` compartido por el hook y el runner; (d) las dos familias en
las tres tablas + `goals.niveles_de` **partido en dos caminos** (R36: `permisos/goal.py` NO importa `goals`,
es una invariante declarada y fijada por test, asi que ahi se fusiona contra su propia copia
`{**_NIVELES_DEFECTO, **(niveles or {})}`; y la fusion va en `goals.compuertas_del_goal`, `goals.py:1011`,
que arregla de una al hook `goals_hook.py:1387` y a `goals_manos.py:418`, el lector que faltaba en la lista)
+ el test de `test_goals_permisos.py:61`; (e) el campo `correr` del veredicto (nullable para codex, R37) y
el camino del runner: DENTRO de la ventana `sin_golpe` con `al_lanzar` y `cancelar` (R3), chequeo de carga
antes de lanzar (R18), fila en `hook.jsonl` ANTES de lanzar (R10), scope systemd, aduana,
`duracion_correr_ms` (R11), `CORRER_TIMEOUT_S` (R19) e inyeccion de la salida ROTULADA como dato (R17); (f)
la sonda por app, con su marca en el LEDGER (R23); (g) cerrar el agujero de `:1373` para las apps de la
tabla.

**2. Las imagenes del goal.** *La bloquea*: nada. Barata e independiente, y es lo que le da a Pedro el "ver"
del caso guia. Incluye reescribir `goals.test.js:89` y `:155`.

**3. El MCP `calipso` de SOLO LECTURA** (`memoria_buscar`, `goal_estado`, `aduana_resumen`). *La bloquea*:
la 0. Partido a proposito: esta mitad no necesita ninguna decision de espera ni toca el estado del goal.
Incluye lo caro: (a) invertir la guarda del Parser a lista blanca de nombres exactos
(`goals_manos.py:647-649` + `goals_runner.py:981-983` + los tests de argv); (b) `--mcp-config` con el token
en archivo 0600; (c) el namespace `/api/goals/<id>/mcp/*` y la rama nueva en `auth_guard`
(`server.py:571`); (d) revocacion en `goals.transicionar` al entrar en `FINAL_STATES`; (e) `tapar` en toda
salida, el cruce de aduana asentado por el server y la entrada en EXCEPCIONES del canario; (f) el registro
de las llamadas MCP en el Parser y en `golpes.jsonl` (D5).

**4. `preguntar` y `nota`.** *La bloquea*: la 3. Sin espera (D4): contador `vez` en la corrida y en la forma,
un solo consumidor de la aprobada, y `nota` por evento propio.

**5. El detector con contexto, medido.** *La bloquea*: nada tecnico; la bloquea el **piso de §7**. **Arranca
por traer `experimentos/banco_manos.py` y `experimentos/historial_export.py` desde `feat/historial-export`,
que NO estan en main** (R25), y por el trabajo de banco que el piso exige: re-exportar conservando el id de
conversacion, filas con el turno anterior, `medir_con_contexto(detector, filas)`, y el mapeo explicito de
los tres valores (hoy `bool("dudoso")` es True). Despues: capa 1 + capa 2 + la marca `manos` en el meta del
turno, con el costo de RUTEO medido antes de ampliar la regex (R26). Se cablea el camino `dudoso` desde el
principio; el camino `si` solo cuando el numero pasa el piso de la capa 1.

**6. La propuesta automatica.** *La bloquea*: la 5 (el piso). Los dos frenos que no existen (goal en curso,
dict armado a mano sin `parse_goal_texto`), el enganche entre `server.py:5781` y `:5851`, y el degradado a
`dudoso` por carga o cuota.

**7. El smoke real y el informe.** *La bloquea*: 1, 2, 3, 4. S3 -> S4 -> S5, en ese orden (S2 se adelanto a
la tarea 0, R34): cada uno mide lo que el siguiente da por hecho.

## 12. Rulings de la revision adversaria, 2026-09-16

Seis lentes adversarias (cinco de Claude, una externa de Codex gpt-5.5 en `-s read-only`) leyeron el spec v2
contra el codigo real, contra los specs que ya gobiernan (goals 2026-09-13 + adenda 16, aduana 2026-09-10,
canarios, carga, abismo) y contra la maquina. Devolvieron 73 hallazgos; **los que sobrevivieron a la verificacion
propia entran aca deduplicados como 41 rulings mas 9 decisiones de Pedro (§13); 2 se descartan** (al final,
con el por que). El cuerpo del spec ya quedo corregido donde contradecia esta adenda; cada correccion
lleva el numero del ruling.

Todo lo que dice "medido" aca se midio HOY en esta maquina, y esta adenda tiene que releerse con el spec ya
commiteado: el plan y el SDD citan el spec **por sha**, no por linea del working tree.

### Lo que la revision NO tumbo

Conviene decirlo primero porque es la mitad del documento: §2 (las tres premisas falsas) se sostiene entera,
D1 en su forma (sacar la app del sandbox del CLI por `correr_confinado`), D8 (SPEC JSON en vez de `bpy`
libre), D3 en su eleccion (token en archivo 0600, ni en el env del CLI ni en la argv), D4 (`preguntar` no
bloquea), D7 (el terreno del smoke a mano), el namespace propio en el server en vez de un tipo nuevo en
`sesiones.ALCANCES`, la revocacion por `goals.transicionar` como puerta unica, y el orden del corte. Las ~60
citas `archivo:linea` que se verificaron caen practicamente todas donde el spec dice, incluidas las dos
correcciones de off-by-one que el encabezado promete (`goals_hook.py:1397` y `:1364`, las dos correctas).

### A. La escalada por el MCP y por lo que lanza el runner

**R1 (critico). El bloque `mcp.json` de §4, tal como estaba escrito, era ejecucion de codigo arbitrario como
Pedro.** *Que se encontro:* `"args": ["-m", "calipso.mcp_calipso"]` sin `cwd` ni `-P`. El CLI spawnea el MCP
por stdio heredando SU cwd -- que es el clon -- y `-m` pone ese cwd primero en `sys.path`. *Evidencia:* el
bundle 2.1.273 spawnea literal `{...,shell:!1,windowsHide:...,cwd:this._serverParams.cwd}` (undefined si el
config no lo trae, y Node hereda el del padre); el cwd del CLI es el clon (`goals_runner.py:96-98` `_cwd_de`,
`:460`, `:486`); `calipso` NO esta instalado en el venv (`/var/home/pedro/calipso/.venv/bin/python -c "import
calipso"` desde otro directorio -> `ModuleNotFoundError`); escribir `calipso/mcp_calipso.py` en el clon es
familia `repo` = directo (`goals.py:64`) y NO es auto-escalada (`goals_hook.py:541-546`: solo `.claude/`,
`.git/hooks/`, `.git/config`). Reproducido: con un `calipso/mcp_calipso.py` plantado en el cwd, `python -m
calipso.mcp_calipso` ejecuta el del cwd. *Que se decidio:* el bloque pasa a llevar los TRES: `-P`, `cwd`
explicito al repo y `PYTHONPATH`. Medido: `PYTHONPATH=<repo>` SOLO no alcanza (el cwd gana el sys.path[0] de
`-m`); `-P` + `PYTHONPATH` si, y `cwd` explicito tambien. §4 corregido, y dice POR QUE, porque es
contraintuitivo. Test en §10.1.

**R2 (critico). D1 no es "una linea": son DOS mounts.** *Que se encontro:* el `--tmpfs /run/user/<uid>` se
midio contra `org.kde.kcalc`, que YA tenia su `~/.var/app/org.kde.kcalc` en el host (creado hoy 13:37, antes
del probe). Con una app recien instalada -- Blender en el caso guia -- `flatpak run` crea
`~/.var/app/<app-id>/{cache,config,data}` antes de arrancar, y dentro de `argv_bwrap` el home va `--ro-bind`.
*Evidencia:* medido hoy importando el modulo real, `flatpak run --command=/bin/true`: kcalc rc=0;
`org.kde.filelight` (sin dir por-app) rc=1 `error: mkdirat(org.kde.filelight): Read-only file system`;
filelight + `--tmpfs /var/home/pedro/.var/app` rc=0. `ls /var/home/pedro/.var/app` no tiene ni filelight ni
Blender. *Que se decidio:* D1 y §5 reescritos a dos mounts, con la consecuencia dicha (la config por-app se
tira en cada corrida). §10.3 suma la fila de que mas necesita `flatpak run` de una app `--user`.

**R3 (critico). El paso `correr` no tenia ciclo de vida.** *Que se encontro:* "despues del golpe" lo deja
fuera de la ventana que protege al golpe. *Evidencia:* `goals_runner.py:921` `self.sin_golpe.clear()`,
`:973-975` el `finally` que pone `golpe_en_curso = None` y `sin_golpe.set()`; `_cancelar_goal`
(`server.py:4502-4507`) y `_parar_goal` (`:4517-4528`) hacen `matar_golpe()` + `esperar_golpe()` ANTES de
transicionar; `matar_golpe` (`goals_runner.py:722-725`) solo conoce `golpe_en_curso`. Resultado: `/goal
parar` no mata nada, el render sigue hasta `RuntimeMaxSec` detras de una transicion final, y el hilo vivo
levanta `ErrorGoal` en su siguiente `escribir`. *Que se decidio:* `correr` va DENTRO de la ventana
`sin_golpe`, con `al_lanzar=self.registrar_golpe` y `cancelar=self.cancelar` -- el molde que el criterio y
el revisor ya usan (`goals_runner.py:1147-1165`) --; despues se recalcula `cancelado`. §5 corregido.

**R4 (critico). Los tmpfs del confinado no tienen tope, y el scope no tiene MemoryMax ni CPUQuota.** *Que se
encontro:* `--tmpfs` sin tamano da la mitad de la RAM; `correr_confinado` quedaba con DOS (tres, con R2) en
el unico camino que corre sin preguntarle a Pedro (`correr_datos`, directo). Es la reapertura del bug del
2026-09-15 ("la RAM en cero de la Ally era /tmp con 4,6 GB de temporales"). *Evidencia:* medido, `bwrap
--ro-bind / / --tmpfs /tmp --tmpfs /run/user/1000 ... df -h` -> ambos `5.7G` sobre 11,4 GiB totales; con
`--size 268435456` -> `256M` (bubblewrap 0.12.0 lo soporta). `argv_systemd` (`goals_manos.py:533-535`) solo
emite `RuntimeMaxSec`; los controladores estan delegados (`cgroup.controllers` -> `cpu io memory pids dmem`)
y `systemd-run --user --scope -p MemoryMax=64M -p CPUQuota=50%` corre sin error. El manifest de Blender
declara `TMP_DIR=/tmp` y `TMP=/tmp`: el scratch del render va a RAM. *Que se decidio:* `--size` en los tres
tmpfs y `MemoryMax`/`CPUQuota` en el scope de `correr_app`. Los numeros los pone Pedro (P5).

**R5 (critico). Las reglas de las imagenes no contenian la ruta ORIGEN, y validaban por extension.** *Que se
encontro:* §6 cubria nombre de destino, topes, extension y forma de servir, pero nada exigia que el origen
resolviera dentro del clon. La entrada la escribe el martillo y `StructuredOutput` es allow incondicional en
el hook (`goals_hook.py:1462`); la copia la hace el runner fuera del sandbox, como Pedro, sin `denyRead`.
*Evidencia:* `imagenes: ["../../../.ssh/id_ed25519"]` (sin symlink siquiera) dejaria el archivo bajo
`~/.calipso` con nombre canonico y servido por la API, que publica la lista entera (`_goal_con_consumo`,
`server.py:6473-6480`, en `/api/goals`). *Que se decidio:* regla nueva y PRIMERA de la lista (resolver con
symlinks seguidos, tiene que dar `_en_alcance == "repo"`, lo que no cae adentro no se copia y deja fila),
validacion por **magic bytes** con el renombrado usando la extension del magic, tope de **dimensiones**
ademas de bytes, y Content-Type fijo + `nosniff` al servir. §6 corregido; tests en §10.1.

### B. Lo que el MCP promete y no cumple

**R6 (critico). `memoria_buscar` abre una familia NUNCA, y §8 decia lo contrario que §4.** *Que se
encontro:* la memoria de Pedro es exactamente `datos_de_pedro`, NUNCA en la tabla, y §8 afirmaba "El MCP no
abre ninguna" mientras §4 admitia que el MCP corre como Pedro con `~/.calipso` entero. Ademas la frase "el
limite del goal ES el token + el 401 + `tapar`" sobrevende a `tapar`. *Evidencia:* la memoria vive bajo
`~/.calipso` (`memory.py:42-43`, `:204`, `:212`, `:228`), que esta en PROTEGIDAS (`goals_hook.py:90-91`) y en
DENY_READ (`goals_manos.py:280-281`); hoy toda lectura del martillo ahi muere como NUNCA
(`goals_hook.py:1306` por Bash, `:1420` por Read/Grep/Glob), cortada por NOMBRE y ANTES de la tabla
(`:1382-1384`). `tapar` (`goals_manos.py:1186-1203`) recorre `detector.detectar_secretos`, que tiene un solo
tipo -- `"credencial"` -- y barre `_PREFIJOS`, `_JWT`, `_PEM`, `_CONN`, hex y base32
(`privacidad/detector.py:41-58`); el vocabulario humano (`identidad`, `salud`, `ubicacion`, `financiero`,
`contacto`) esta en `privacidad/juez.py:15` y no participa. Y `aduana.cruzar` registra: no filtra. *Que se
decidio:* §4 y §8 corregidos para que digan lo mismo y digan el alcance real de `tapar`. **La eleccion sobre
`memoria_buscar` es de Pedro: P1.** Hasta entonces el MCP de la tarea 3 puede salir con `goal_estado` y
`aduana_resumen`.

**R7 (importante). La guarda del Parser solo miraba el anuncio del `init`.** *Que se encontro:* el spec le
asigna el rol de "ultima defensa si `--strict-mcp-config` se cae por un refactor", y para ese rol no sirve:
una tool que no aparece en el anuncio -- diferida detras de tool search (lo que `alwaysLoad` intenta evitar,
o sea que el spec ya sabe que puede pasar) o agregada despues -- se llama igual y la guarda no la ve.
*Evidencia:* `_system` solo inspecciona el anuncio (`goals_manos.py:641-649`); `_assistant` guarda el nombre
de cada `tool_use` (`self._tool_uses[tid] = {"name": nombre, ...}`, `:669-684`) pero no lo juzga: solo filtra
`if nombre == "Bash"`. *Que se decidio:* la lista blanca va en DOS lugares -- el anuncio y el nombre de cada
`tool_use` en `_assistant`, que es exactamente donde D5 ya pone el registro de las llamadas MCP. El test de
§10.1 ejercita el segundo camino, no solo el primero.

**R8 (importante). Nadie aplicaba el si de `preguntar`, y el atajo obvio le daba autoridad de permisos al
MCP.** *Que se encontro:* el spec dice que `preguntar` "estaciona" y que el camino del MCP "no consume
nunca", pero nunca dice QUIEN aplica el si. Y hay dos caminos que estacionan la misma solicitud (el MCP y el
veredicto `preguntar` del mismo golpe) sin regla de composicion, con el del MCP salteandose los tres frenos
que `_preguntar` tiene hoy. *Evidencia:* `aplicar_respuesta` solo actua sobre `goal["espera"]`
(`goals.py:790-797`), y el goal tiene UNA sola espera -- el caso guia pide DOS compuertas en el golpe 1;
`ESQUEMA_VEREDICTO` tambien tiene UN campo `compuerta` (`goals_manos.py:298-321`). Los tres frenos de
`_preguntar` (`goals_runner.py:1092-1132`): familia NUNCA -> nota y sigue; `raiz_nueva` -> `validar_raices`
ANTES de estacionar, porque un si sobre una raiz invalida clava el goal; nivel directo -> se concede sin
estacionar. *Que se decidio:* la tool del MCP no estaciona por su cuenta: llama del lado del server al MISMO
camino que `_preguntar` y devuelve lo que ese camino decidio. El MCP **nunca** escribe `preautorizadas` ni
`goal.json` ni `compuertas.json`. Al cerrar el golpe el runner junta TODAS las solicitudes abiertas del goal
(`_solicitud_abierta_del_goal`, `server.py:4218-4228`) y las aplica en orden: eso exige `espera` con lista o
un `aplicar_respuesta` por solicitud, y se dimensiona en la tarea 4. §4 corregido.

**R9 (importante). La invariante del token prometia mas de lo que da.** *Que se encontro:* el token SI vive
en el env de un proceso -- el del MCP, hijo del CLI, mismo uid -- y la enumeracion "ni en el env del golpe,
ni en la argv, ni en el ledger" no es completa. *Evidencia, con una correccion propia sobre lo que reporto
la lente:* por **Bash** NO se llega -- medido, adentro de un bwrap con `--unshare-user --cap-drop ALL` (la
forma que el terreno documenta para el CLI, `terreno-manos.md:986`) leer `/proc/<pid>/environ` de un hermano
del mismo uid da `Permission denied`, aunque el `/proc` fresco SI lista los 436 pids del host. Por **`Read`
si**: es in-process y NO sandboxeada (el mismo argumento que §2.1 usa para probar que el MCP no esta
confinado) y el hook la deja pasar sobre `/proc`, que no es protegida ni esta bajo el home
(`decidir_archivo`, `goals_hook.py:1415-1428`, termina en `Decision(True, "Read permitido")`). *Que se
decidio:* §8 dice la verdad completa, se suma la fila a §10.3 con su sonda, y el token lleva vencimiento
propio ademas del estado del goal (un goal colgado en `ACTIVE` dejaba el archivo vivo indefinidamente).

### C. Lo que el runner tiene que escribir y no estaba escrito

**R10 (importante). "Fila de ledger" mandaba al archivo equivocado.** *Evidencia:* `compuertas_usadas`
(`goals_runner.py:271-296`) abre el `registro` = `<carpeta>/hook.jsonl` (`goals.py:1014`,
`goals_runner.py:914`), no `golpes.jsonl`, y descarta toda fila sin `familia` (`:288-289`). Su unico escritor
es `goals_hook.anotar` (`goals_hook.py:1489-1503`), fail-closed. *Que se decidio:* el runner escribe en
`hook.jsonl` con la MISMA forma de `anotar`, marcada `tool: "correr"`, **ANTES** de lanzar (si escribe
despues, una corrida que mata al server no deja rastro de que se corrio) y con la misma regla fail-closed. Un
unitario verifica que la fila aparece en `compuertas_usadas` y en el cruce de aduana.

**R11 (importante). "Los minutos contra el tope" no era expresable.** *Evidencia:* `golpes()` funde las filas
por `n` con last-wins (`goals.py:849-863`) y `consumo()` suma `duracion_ms` de las fundidas (`:866-875`). Con
el mismo `n`, la fila de `correr` PISA la del golpe; con un `n` nuevo, cuenta como un GOLPE entero contra los
8. Las dos opciones obvias estan mal. *Que se decidio:* clave propia `duracion_correr_ms` en la fila del
MISMO `n`, y `consumo` la suma aparte. §10.1 lo prueba.

**R12 (menor). `vez` era ambiguo, y una de las dos lecturas rompia la preautorizada.** *Evidencia:* la
preautorizada se compara por igualdad EXACTA de dict contra lo que devuelve `familia_de_argv`
(`goals_hook.py:1391-1393`, y lo mismo en `permisos/goal.py:68-74`), que jamas lleva `vez`; el precedente que
el spec cita pone `vez` en la forma de `retomar` (`goals_runner.py:583`), pero `retomar` nunca se vuelve
preautorizada. *Que se decidio:* `vez` va en la CORRIDA (`f"{goal}:{op}:{n}:{vez}"`) y, si hace falta para la
idempotencia por forma de `almacen.crear`, en el nivel de ARRIBA de la forma de la solicitud -- nunca dentro
de `forma["forma"]`. Test: dos `preguntar` en el mismo golpe no se comen la respuesta de la otra, Y la
preautorizada que sale de la segunda si tapa el argv.

**R13 (critico). Lo que validaba `decidir_argv` no era lo que se ejecutaba.** *Que se encontro:*
`correr_confinado` resuelve `argv[0]` con `resolver_exe`, que prefiere `<cwd>/.venv/bin/<exe>` -- y el cwd es
el clon, que el martillo escribe con nivel directo. Toda la gramatica por app quedaba decorativa y D1 ("lo
lanza el RUNNER") dejaba de ser cierto. *Evidencia:* `goals_manos.py:1016` (`venv = os.path.join(cwd,
".venv", "bin", exe)` antes de `shutil.which` en `:1019`), `:1102` (PATH del clon primero), `:1105`
(`resolver_exe(str(argv[0]), cwd, env["PATH"])`). Reproducido: con un `<clon>/.venv/bin/flatpak` plantado,
`resolver_exe("flatpak", clon, "/usr/bin:/bin")` devuelve el plantado; con `ffmpeg` y nada plantado devuelve
`/usr/bin/ffmpeg`. *Que se decidio:* la tabla `APPS` guarda la ruta ABSOLUTA del ejecutable, verificada sin
symlinks y fuera del clon y de las raices; `correr_app`/`correr_datos` no pasan por `resolver_exe` ni por el
PATH del clon; y entre `decidir_argv` y el `Popen` no cambia nada (script y destinos resueltos UNA vez). §5
corregido; test en §10.1.

**R14 (importante). El motivo de D5 era falso, y el riesgo que declaraba no existe.** *Que se encontro:* el
spec decia que el CLI compara los matchers "como strings exactos". Si fuera asi, `MATCHER_HOOK` -- que es UNA
sola string -- no casaria con nada y el hook no se dispararia nunca. *Evidencia:* medido sobre
`~/.calipso/goals/*/hook.jsonl`, llegaron al hook Bash 148, Write 34, Read 8, Glob 1: cuatro herramientas
desde esa unica string. El bundle 2.1.273: la funcion que decide si un hook aplica (la que expande
`hookMatcherFamilyNames` para PreToolUse) hace `if(!n||n==="*")return!0; ... let O=new RegExp(n);
if(O.test(e))return!0` -- **regex NO anclada** sobre `tool_name`. El propio terreno ya lo decia
(`terreno-manos.md:423`) y el spec tomo la otra afirmacion, que venia de los docs. *Que se decidio:* D5
reescrito con el mecanismo real. La conclusion no cambia (ninguna de las diez alternativas, todas con
mayuscula, aparece en un `mcp__calipso__<minusculas>`), pero el riesgo declarado si: "meter un `.` o un `*`
convierte los diez nombres en regex sin anclar" es falso -- ya lo son. Lo que rompe al sumar
`mcp__calipso__.*` es la rama faltante en `decidir` (`goals_hook.py:1470`) mas el desbalanceo de `CON_HOOK`.

**R15 (critico). La gramatica por app normaba destinos y no fuentes.** *Que se encontro:* como la rama `run`
devuelve temprano con su familia, los tres chequeos de LECTURA que el hook aplica hoy a todo
`EXES_CON_RUTAS` no corren, y dentro de `correr_confinado` todo `/` esta montado de lectura salvo PROTEGIDAS.
`pandoc ~/Documents/loquesea.md -o <clon>/out.md` con `correr_datos` en DIRECTO seria "copiar cualquier
archivo del home al clon" sin aprobacion -- y de ahi al contexto y a la API. *Evidencia:* los tres chequeos
salteados son `_protegida_para_leer` (`goals_hook.py:1305`), `_abarca_el_home` (`:1307`) y la regla
`raiz_nueva` de `_bajo_home` (`:1334-1335`); `--ro-bind / /` en `goals_manos.py:1061` y solo DENY_READ +
PROTEGIDAS tapadas (`_tapadas_del_confinado`, `:1029-1043`, usado en `:1067-1071`); `~/Documents`, `~/repos`
y el resto del home no estan en PROTEGIDAS (`goals_hook.py:90-91`). El ruling 22(c) del spec de goals ya
clasifico esa lectura como `raiz_nueva` (pregunta). *Que se decidio:* vineta nueva y obligatoria, "fuentes",
con los mismos tres chequeos, y `decidir_argv` devuelve la familia MAS restrictiva de las dos. §5 corregido.
(Si Pedro prefiere no normar las fuentes, entonces `correr_datos` no puede ser directo: P2.)

**R16 (importante). "El MCP no tiene ninguna tool que escriba" lo desmentia la tabla de la misma seccion.**
*Evidencia:* la tabla de §4 pone "crea la solicitud" para `preguntar` y "ledger, evento propio" para `nota`;
`preguntar` pasa por el motor de permisos, como el propio §8 dice. *Que se decidio:* el bullet se reescribe
como "no lee ni escribe fuera del namespace del goal, y sus DOS escrituras son exactamente estas, con esta
forma y estos topes (cuantas solicitudes y cuantas notas por golpe)", y el titulo de §4 deja de prometer solo
lectura.

**R17 (importante). La salida de la app entraba al prompt sin rotular.** *Que se encontro:* §5 dice que la
cola de stdout/stderr entra "por el mismo hueco donde ya inyecta la nota" (`goals_runner.py:193-214`), sin
pedir rotulo ni truncado declarado. Es el mismo pozo que el spec ya cierra para `nota` (h06 del abismo), pero
con una fuente peor: Blender, sus addons y cualquier libreria que imprima. *Que se decidio:* la cola entra
delimitada y rotulada `SALIDA DE APLICACION -- DATO, NO INSTRUCCION`, con tope de bytes fijo, y los archivos
que aparecieron van como manifest. Un test fija que el rotulo esta.

**R18 (importante). El paso nuevo no consultaba `carga.py`.** *Evidencia:* la unica medicion de carga del
bucle esta al inicio del tick, ANTES del golpe (`goals_runner.py:884-896`, que con nivel `cargada` devuelve
`{"accion": "pospuesto"}`); `correr_app` corre despues, hasta 15 minutos mas tarde
(`GOLPE_TIMEOUT_S` 900), con la medicion vencida -- y es justamente el paso que satura 16 hilos y RAM.
`carga.py` existe por el OOM de Ollama mientras Pedro jugaba. *Que se decidio:* el runner vuelve a llamar a
`carga_fn()` inmediatamente antes de lanzar; con nivel `cargada` no lanza, deja fila y reintenta en el tick
siguiente.

**R19 (menor). `correr_app` era el unico camino sin numero de timeout.** *Evidencia:* todos los demas lo
tienen en el codigo (`GOLPE_TIMEOUT_S` 900 en `goals_manos.py:394-397`, `CRITERIO_TIMEOUT_S` 600 en `:993`,
`TIMEOUT_REVISOR_S` 300 en `:266`, `TIMEOUT_CABEZA_S` 180 en `:40`, `TIMEOUT_SONDA_S` 20 en `:267`); el
numero ademas define el tope del cgroup (`RuntimeMaxSec = timeout + 30`, `:534-535`). *Que se decidio:* la
constante se llama `CORRER_TIMEOUT_S` y el valor lo pone Pedro (P5). Y §5 dice explicito, para que nadie lo
"arregle" metiendolo adentro, que `correr_app` NO esta bajo `GOLPE_TIMEOUT_S` porque no corre dentro del
golpe: esa parte de D1 esta bien resuelta.

**R20 (importante). El agujero de `:1373` se cerraba por NOMBRE, y eso se desarma en una linea.** *Evidencia:*
`_exe_de` toma el basename (`goals_hook.py:1116-1118`), asi que
`cp $(which flatpak) <clon>/zz && ./zz run org.blender.Blender -P x.py` da exe=`zz`, donde=`clon`, no entra
en la rama `flatpak` (`:1353`) ni en la rama `run` nueva, y cae en `if exe in ALLOW_EXES or donde in ("venv",
"clon"): return None` (`:1373`): allow silencioso, sin familia -- y sin familia la fila ni aparece en
`compuertas_usadas` (`goals_runner.py:288-289`). El comentario de `_exe_de` (`:1119-1123`) ya registra que el
martillo hizo exactamente esa maniobra en el probe del 2026-09-15. *Que se decidio:* se cierra por FORMA: si
el argv tiene la forma de una app de la tabla (primer posicional `run` mas un app-id de `APPS`, o un
`-P`/`--python`/`-b`/`macro:///`), la gramatica corre se llame como se llame el ejecutable. El residuo del
caso general queda declarado en §9 con todas las letras.

### D. Correcciones de citas, numeros y piezas que no existen

**R21 (menor). "El sandbox hace `--setenv` del entorno del padre" no es lo que se midio.** *Evidencia:* el
argv real del bwrap que construye el CLI (`terreno-manos.md:986`, medido del bundle) lleva `--setenv` solo
para las variables de proxy, y no aparece `--clearenv` en ninguna parte: bwrap sin `--clearenv` hereda el
entorno del proceso que lo lanza. *Que se decidio:* D3 reescrita. La conclusion es la misma y de hecho mas
firme asi.

**R22 (menor). La cita `goals_manos.py:455-460` no contiene ni `allowWrite` ni `allowedDomains`.**
*Evidencia:* `:455-460` es el bloque de banderas del sandbox; `allowWrite` esta en `:462`, `allowedDomains`
en `:466`, `strictAllowlist` en `:468`, y `--add-dir` en `:503-504`. *Que se decidio:* corregida en los dos
lugares donde aparecia (§2.4 y §8). El encabezado del spec promete que todas las lineas citadas se
releyeron: esta se habia escapado.

**R23 (importante). La mitad de la tabla `APPS` no existe en la maquina.** *Evidencia:* `which pandoc
libreoffice gimp` -> los tres "no encontrado"; `which ffmpeg` -> `/usr/bin/ffmpeg`; `flatpak list --app` ->
12 apps, ninguna es GIMP ni Blender. Y para `pandoc` el argumento "no acepta script" es falso: `--filter`
corre un ejecutable y `--lua-filter` un script. Ademas "antes de la PRIMERA corrida de una app en un goal"
necesita estado y el molde parecido (`self.hook_sondeado`, `goals_runner.py:668`, `:872-876`) es por
instancia de Runner: se pierde en cada relanzamiento del bucle. *Que se decidio:* `pandoc`, `org.gimp.GIMP` y
`libreoffice` salen de la tabla en esta tanda y quedan declaradas como futuras (§9); el smoke usa `ffmpeg`
para `correr_datos` y Blender para `correr_app`. La marca "ya sondee esta app en este goal" vive en el LEDGER
del goal, no en el Runner. Y un `correr` que llega con `estado` distinto de `sigo` se ignora y deja fila.

**R24 (menor). El molde que §6 le asignaba a la PWA no admite una imagen.** *Evidencia:* `addDetail`
(`calipso/web/index.html:1960-1971`) hace `d.innerHTML = \`<summary>${esc(title)}</summary><pre>${esc(body ||
"")}</pre>\``: un `<img>` pasado por `body` sale como texto literal, que es exactamente lo que el test del
front verifica que pase. *Que se decidio:* se nombra el camino concreto (`appendChild` sobre el `<details>`
que `addDetail` devuelve, o una funcion hermana), se suma la fila de test del detalle de la PWA a §10.1 (hoy
solo hay tests de /fabrica), y se corrigen las rutas del front en todo el spec: son `calipso/web/*`, no
`web/*`.

**R25 (critico). El piso de §7 no era medible con el banco que el spec cita, y el banco no esta en main.**
*Evidencia, verificada linea por linea sobre `feat/historial-export`:* `medir(detector: Callable[[str],
bool], ...)` y `pred = bool(detector(f["texto"]))` (`banco_manos.py:42`, `:55`) -- UN argumento, y
`bool("dudoso")` es True; `cargar()` termina en `[f for f in filas if f["etiqueta"] in ("manos","no_manos")]`
(`:35-39`). Conteo real del jsonl (449 filas): totales `no_manos` 160, `manos` 145, `continuacion` 132,
`para_pedro` 12; de chat (326): 142 / 103 / 71 / 10; lo que `medir()` ve = 245, sin una sola continuacion. El
41% sale de 71/(103+71) = 40,8% y esas 71 estan AFUERA. Claves de una fila: `texto`, `etiqueta`, `confianza`,
`por_que`, `fuente`, `linea` (+ `frontera` en 37): no hay id de conversacion. `ls experimentos/banco_manos.py`
en main -> no existe; `git ls-tree feat/historial-export` -> si; `git branch --merged HEAD` -> la rama NO
esta mergeada. Y el jsonl vive bajo `~/.calipso`, que `correr_confinado` tapa con tmpfs. *Que se decidio:* el
piso va PARTIDO EN DOS (capa 1 sobre los 245 con `medir` tal cual; capa 2 sobre las 71, con banco nuevo y
`medir_con_contexto`), la tarea 5 arranca trayendo los dos archivos desde la rama, el mapeo de los tres
valores se declara explicito, y el test de regresion SALTA con skipif si el jsonl no esta. §7 y §11
corregidos.

**R26 (importante). Ampliar la regex `MANOS` es un cambio de RUTEO, no solo de propuesta.** *Evidencia:*
`MANOS` (`dispatch.py:144-149`) ya tiene dos consumidores vivos: `dispatch.py:184` la mete en
`needs_hands` y `:206` sube la complejidad a 4 ("fuera del 7b (max_complexity 3) y de haiku"), y
`server.py:3097` apaga el equipo con ella. Con el recall de hoy eso toca ~8 de los 245; con el piso de §7,
~60: 7,5x mas turnos forzados a frontera aunque el camino `si` no se cablee nunca. *Que se decidio:* §7 lo
dice y exige medir ese costo contra el mismo banco ANTES de ampliar, o que `necesita_manos` use regex propia
y `MANOS` quede como esta para el router. La frase "el camino dudoso no le cuesta a Pedro ni una unidad" se
corrige.

**R27 (critico). El caso guia no declaraba los dominios de flathub: el golpe 2 no llegaba a la red.**
*Evidencia:* `_dominios_permitidos` (`goals_manos.py:415-425`) = `api.anthropic.com` + `DOMINIOS_INDICES`
(`:291`: pypi, files.pythonhosted, npmjs, yarnpkg) si `instalar_en_goal` es directo + `compuertas["dominios"]`;
flathub no esta en ninguno, y los settings van con `"strictAllowlist": True` (`:468`). Es el mismo golpe que
las adendas 32 (pypi) y 36 (la CDN de pytorch) del spec de goals ya pagaron dos veces, y `dominios` se
congela al lanzar, asi que descubrirlo mid-golpe cuesta otro golpe. Medido: `dl.flathub.org` es un solo host
sin redireccion (`curl -L .../repo/config` -> 200, 0 redirects). *Que se decidio:* la propuesta del paso 1
declara `dominios: ["dl.flathub.org"]` desde el arranque (`web` es directo: no cuesta compuerta), y S2 mide
la RED primero, porque **no esta confirmado que flatpak/libostree respete el proxy socks/http del sandbox**:
esa es la pregunta que va antes que cualquier otra.

**R28 (importante). El install tiene que caber en `GOLPE_TIMEOUT_S`, y nadie lo dijo.** *Evidencia:*
`GOLPE_TIMEOUT_S()` default 900 (`goals_manos.py:394-397`); 477,4e6/900 = 530,4 kB/s = **4,24 Mbit/s**
sostenidos, y 10,1 Mbit/s si la instalacion `--user` no reusa el runtime del system (+659,9 MB, no
confirmado). Si vence, el golpe se mata y la fila CUENTA para el tope (`cuenta_para_tope` solo se pone False
con `cuota_fallo` o `cancelado`, `goals_runner.py:956`): dos vencimientos matan el goal habiendo gastado 0,64
USD y 30 minutos sin instalar nada. *Que se decidio:* el golpe del install va con
`CALIPSO_GOAL_TIMEOUT_S` subido, y S5 mide el enlace ANTES.

**R29 (importante). El guion del caso guia se comia la vuelta por la compuerta `correr_app`.** *Evidencia:*
D2 la pone en `pregunta` y §5 dice "si la decision es negativa, no se lanza nada y el goal pide la
compuerta", pero el paso 5 de §3 lanza `flatpak run` sin mencionarla. *Que se decidio:* el paso 5 lo escribe.
El efecto sobre el tope de 8 golpes es de Pedro (P6).

**R30 (importante). El presupuesto del render no estaba acotado en ningun lado.** *Evidencia:* D8 fija el
SCRIPT, pero el CONTENIDO del spec.json lo escribe el martillo, y lo que §5 dice que el esquema valida es
"primitivas, modificadores permitidos, material, escala, export": ni motor, ni samples, ni resolucion. Un
`engine: cycles, samples: 4096, resolution: 4096x4096` valida y quema el timeout entero a 16 hilos (nproc =
16). Del otro lado, los topes de §6 eran bytes y extension, no dimensiones, y el revisor lee el PNG con un
modelo. *Que se decidio:* el esquema topea motor, samples y resolucion con numeros escritos, y §6 suma el
tope de dimensiones (R5).

**R31 (importante). Esta tanda enmienda el spec de goals y no lo decia.** *Evidencia:* el spec de goals sigue
diciendo, en su invariante 4 (linea 237) y su ruling 15.5 (linea 155), que la barrera es total y que es el
sandbox; el spec v2 abre dos carriles que no pasan por ninguna de las dos capas -- el MCP (§2.1, §4) y el
paso `correr` lanzado por el runner (D1, §5) -- y lo reconoce en el cuerpo pero no lo escribe como enmienda.
*Que se decidio:* §8 suma el parrafo "lo que esta tanda enmienda del spec de goals", numerado, con la forma
de la adenda 16: la invariante 4 pasa a tres barreras con su alcance escrito, y el ruling 15.5 queda acotado
a los comandos del CLI.

**R32 (importante). Tres de los cinco tests citados como "arrastrados" no son de la argv del golpe.**
*Evidencia:* `test_seguridad_techo.py:208` llama `srv._subscription_invocation(...)` -- la argv del CHAT;
`test_goals_chat.py:510` llama `argv_cabeza_claude` -- la cabeza; `test_goals_manos.py:1080` assertea
`--tools Read,Glob,Grep` -- el REVISOR. El unico que toca `argv_claude` es `test_goals_manos.py:222-232`. Y
ninguno de los cuatro se rompe por agregar una flag: los asserts son de pertenencia o por indice, nunca
igualdad de lista. *Que se decidio:* §2.3 y §11.3(a) dejan como arrastrado solo `test_goals_manos.py:226`, y
§10.1 cita los otros tres por lo que de verdad valen: el invariante de que la argv del chat, la de la cabeza
y la del revisor **NO** ganan `--mcp-config` -- que conviene fijar explicito ahora que el golpe si lo gana, y
que es justo lo que `--strict-mcp-config` esta ahi para sostener.

**R33 (menor). Dos de las cuatro preguntas de S1 se contestan con un grep, sin gastar un golpe.**
*Evidencia:* sobre `/var/home/pedro/.local/share/claude/versions/2.1.273` (`claude --version` -> 2.1.273):
`failIfUnavailable` 20 apariciones, y sigue como clave restrictiva del schema, literal
`{path:["sandbox","failIfUnavailable"],restrictive:!0}` -- el bloqueante "el sandbox falla ABIERTO" queda
tachado antes de empezar; `alwaysLoad` 42, `MAX_MCP_OUTPUT_TOKENS` 6, `strict-mcp-config` 19, `mcp-config`
83, `enableWeakerNestedSandbox` 14 con su texto "exposes the host /proc". *Que se decidio:* la evidencia del
grep se fija en §10.3 y S1 queda con lo unico que el binario no contesta: si una tool `mcp__calipso__*` corre
sola bajo `--permission-prompts none`, si hace falta `--allowedTools`, y si `alwaysLoad` de verdad las pone
en el `system/init` sin tool search (pregunta que S1 no tenia).

**R34 (critico). La salida de emergencia de S2 es imposible, y S2 estaba al final.** *Evidencia:*
`correr_confinado` lleva `--unshare-net` incondicional (`goals_manos.py:1072`), sin bandera ni parametro que
lo apague, y el docstring de `lanzar_confinado` (`:1076-1078`) lo declara invariante ("canario: local, no
sale de la maquina"); es una invariante escrita del cierre 2026-09-14 (adenda 18). Un `flatpak install` sin
red no baja 477 MB. El propio spec citaba ese `--unshare-net` como virtud en §5 y lo ignoraba en §10.2. *Que
se decidio:* la frase se borra y se escriben las opciones reales; y S2 se adelanta a la tarea 0 junto con S1,
porque es igual de barata y puede invalidar el paso 4 del caso guia. La eleccion, si S2 sale mal, es de Pedro
(P3).

**R35 (menor). La unica linea de presupuesto de RAM del spec usaba la metrica equivocada.** *Evidencia:* "~475
MiB libres" viene del terreno (`terreno-manos.md:265`) y es MemFree, no MemAvailable, que es la metrica de
`carga.py` ("los avisos siguen diciendo N MB libres con MemAvailable, que es lo que Pedro entiende"). Medido
hoy: MemFree 557 MiB vs MemAvailable **6,7 GiB**; `df -h /tmp` -> 5,7 G de tamano con 5,0 G disponibles.
*Que se decidio:* S5 escribe el criterio como "MemAvailable >= X MiB al arrancar", medido en el momento, y
dice que el riesgo de RAM no es que falten 475 MiB sino los tmpfs sin `--size` (R4). De paso, S5 suma la
plata esperada, que el spec no tenia en ningun lado: ~3 USD la pasada limpia, ~9 con depuracion.

**R36 (importante). El helper `goals.niveles_de` no entra en dos de las lecturas, y faltaba un lector.**
*Evidencia:* `permisos/goal.py` NO importa `goals` A PROPOSITO -- invariante declarada en el codigo
(`:41-43`: "copiada para no importar `goals` desde el paquete permisos, que tiene que poder negar aunque el
resto del repo no importe") y fijada por `test_goals_permisos.py:56-61`; sus imports son solo `goals_hook` y
`.acciones`. Y esas dos lecturas (`:82`, `:117`) no reciben un `goal` sino un dict de compuertas o un detalle
de solicitud. Grep completo de `"niveles"`: escritor `goals.py:650`; lectores `goals.py:1011`,
`goals_runner.py:125` y `:1096`, `goals_manos.py:418`, `goals_hook.py:1387`, `server.py:4201`,
`permisos/goal.py:82` y `:117` -- el spec listaba seis y omitia `goals_manos.py:418` (`_dominios_permitidos`,
que decide por el nivel de `instalar_en_goal` si los indices de paquetes entran en la red). *Que se decidio:*
el arreglo se parte en dos y se escribe asi en §11.1(d): la fusion va en `goals.compuertas_del_goal`
(`goals.py:1011`), que es lo que se serializa a `compuertas.json` y arregla de una al hook y a
`goals_manos.py:418`; en `goals_runner.py:125`/`:1096` y `server.py:4201` se usa el helper; y en
`permisos/goal.py` NO se importa `goals`, se fusiona contra su propia copia (`{**_NIVELES_DEFECTO,
**(niveles or {})}`). El test del goal viejo cubre los dos caminos.

**R37 (menor). Los dos campos nuevos del veredicto arrastran a codex, y `compuerta.forma` no tiene `app`.**
*Evidencia:* `ESQUEMA_VEREDICTO.compuerta.forma.properties` = `{raiz, ruta, argv, host}`
(`goals_manos.py:298-321`): no hay `app`, asi que un goal no podria ni pedir la compuerta `correr_app` con la
forma que §5 le asigna. Y `esquema_para_codex` (`:324-346`) pone `additionalProperties: false` y TODAS las
claves en `required` en cada objeto, con lo opcional pasando a nullable (por el `invalid_json_schema` medido
en la corrida 3 del smoke, adenda 16). *Que se decidio:* `compuerta.forma` suma `app` (string); `correr` e
`imagenes` son nullable para codex y el runner trata `None` igual que ausente. `correr` SI vale para `con:
codex` -- el runner es quien lanza, y la asimetria declarada en §4 es solo por el MCP. Un renglon de §10.1 lo
fija con test.

**R38 (menor). El nacimiento del token estaba definido solo por negacion.** *Que se encontro:* "nace al
crear la sesion del bucle, no en `_lanzar_bucle`" no apunta a ningun sitio del codigo, y es el unico paso del
ciclo de vida del token sin direccion -- con una restriccion dura: el archivo tiene que existir ANTES de que
se arme la argv. Los candidatos tienen consecuencias distintas: `goals.crear` (todo `proposed` tendria token,
incluso los que Pedro nunca aprueba), la transicion a `ACTIVE`, o el arranque del Runner. *Evidencia:* lo
verificado a favor del spec: `_lanzar_bucle` esta en `server.py:2728` y lo llaman los seis sitios que dice
(`:2817`, `:2821`, `:4439`, `:4498`, `:4539`, `:4625`), y la revocacion en `goals.transicionar` al entrar en
`FINAL_STATES` (`goals.py:719`) es de verdad puerta unica -- `goals.update` levanta `ValueError` para
cualquier goal con tope (`goals.py:372-377`, "un goal que corre solo cambia de status por
goals.transicionar"). Lo que falta: la argv con `--mcp-config` se arma en `goals_runner.py:481-485`, dentro
de `_golpe`. *Que se decidio:* el token nace en `manos_con_cli` (`goals_runner.py`), donde ya se escribe
`contrato.md` y se relee `compuertas.json` antes de armar la argv, y con regla de ausencia explicita: si
`mcp.json` no existe al armar la argv, **se crea en ese momento**; nunca se pasa una ruta inexistente (el CLI
falla y el golpe muere por una causa que nadie va a relacionar). Hay 16 goals en disco, todos en estado
final, asi que hoy el riesgo es bajo -- la regla falta igual. §10.1 suma el test de que un relanzamiento del
bucle reusa el mismo token.

**R39 (importante). El spec declara que el MCP es codigo de seguridad y no disena el proceso.** *Que se
encontro:* no hay una sola linea sobre con que entorno arranca, que importa, ni que no puede lanzar
subprocesos -- y el bloque `mcpServers.env` AGREGA variables sobre el entorno heredado del CLI, asi que el
argumento de D3 ("todo comando Bash heredaria el token") se aplica tal cual a cualquier hijo del propio MCP.
*Evidencia:* el repo ya piensa asi para el golpe y no para el MCP: `env_saneado` BORRA `CALIPSO_TOKEN`,
`LITELLM_MASTER_KEY`, las claves Anthropic y `PYTHONPATH` (`goals_manos.py:88-90`). *Que se decidio:* §4 suma
un parrafo de proceso, que se escribe en el SDD junto con R1: env minimo y explicito (`CALIPSO_GOAL`,
`CALIPSO_GOAL_TOKEN`, `PATH`, `PYTHONPATH` del repo, HOME neutro y nada mas), `cwd` fuera del clon (R1),
prohibicion escrita de `subprocess` y de importar el server entero, y `tapar` sobre los tracebacks antes de
que salgan por stderr, que el CLI captura.

**R40 (menor). "`<n>-<k>`" y "`/imagenes/{n}`" eran dos `n` distintos, y `goal-imagenes/` se commiteaba.**
*Evidencia:* §6 usaba `n` para el numero de golpe en el nombre de disco y `n` para "el indice" en la URL, sin
decir cual era cual: un implementador no podia saber si `/imagenes/3` es la tercera imagen del goal o las del
golpe 3, ni como se ordena la lista que `_goal_con_consumo` publica. Y `goal-imagenes/` vive dentro del clon,
cuya rama se trae al repo real al `complete` (`goals_runner.py:598-610`): un `git add -A` del martillo le
metia a AvesCO los PNG de trabajo junto con el asset. *Que se decidio:* una sola numeracion -- la lista
publicada en `_goal_con_consumo`, ordenada por (golpe, k), es la fuente de verdad, y la URL toma el indice
0-based en esa lista; el nombre en disco queda como detalle interno. Y las imagenes viven fuera del clon (en
`dir_trabajo`) o el runner escribe `goal-imagenes/` en el `.git/info/exclude` del clon al crearlo. §6
corregido.

**R41 (menor). No estaba escrito que pasa con el `correr` pendiente cuando Pedro dice si.** *Que se
encontro:* el pedido venia en el veredicto del golpe anterior; cuando el goal retoma, o el runner lo
reejecuta con la preautorizada nueva, o el martillo tiene que volver a pedirlo gastando otro golpe. El spec
elegia implicitamente y no decia cual. *Evidencia:* §5 solo dice "no se lanza nada y el goal pide la
compuerta"; la adenda 24 del spec de goals define que un `waiting` estaciona una solicitud `retomar` y que el
si retoma el bucle, sin decir nada de un paso del runner pendiente; y la preautorizada se compara por
igualdad exacta de dict (`goals_hook.py:1391-1393`), asi que la forma guardada al estacionar y la recalculada
al retomar tienen que coincidir byte a byte. *Que se decidio:* el `correr` pendiente se guarda en la fila del
golpe y, al retomar, el runner lo **revalida** con `decidir_argv` y lo lanza antes de gastar el golpe
siguiente, con la forma `{"app": ...}` recalculada por el mismo camino que la que se estaciono. Un test del
molde `estacionar_retomar` lo fija.

### Los dos hallazgos que se descartan, y por que

**D-1. "Exponer `goals_hook.decidir_argv` crea un segundo motor de permisos con divergencia silenciosa"**
(Codex, marcado Alta). **Falso.** `decidir_bash` ya ES esa composicion: `def decidir_bash(comando,
compuertas): argv = partir(comando); ...; familia, motivo, forma = familia_de_argv(argv, compuertas); return
_aplicar_tabla(familia, motivo, forma, compuertas)` (`goals_hook.py:1400-1405`). Tres lineas. `decidir_argv`
es literalmente ese cuerpo sin el parseo del shell: no hay donde meterse una divergencia. La factorizacion
que el spec propone es la correcta y se deja como esta. Lo unico real del hallazgo -- que `familia_de_argv`
decide sobre TEXTO y no ve lo que pase entre la validacion y el `Popen` -- no es un segundo motor, es el
problema de resolucion de rutas, y ya entro por R13.

**D-2. "El spec no esta commiteado y se apoya en ~60 citas `archivo:linea`, que se corren solas"** (Codex,
marcado Baja). Cierto como observacion, pero no es un defecto del diseno y **este commit lo resuelve**: el
spec queda fijado y el plan y el SDD lo citan por sha, como el propio spec ya hace con el terreno. No entra
como ruling; queda como la regla de uso escrita al principio de esta seccion.

## 13. Decisiones pendientes de Pedro

Nueve. Ninguna se decide aca. Cada una con las opciones reales y una recomendacion.

**P1. `memoria_buscar`: ¿el goal puede leer la memoria de Pedro?** (R6.) Es la mas cara del lote: la familia
`datos_de_pedro` es NUNCA en tu tabla y el MCP la abriria por la unica puerta sin hook ni `denyRead`. Y
`tapar` no te cubre: tapa credenciales de maquina, no privacidad.
*Opciones:* **(a)** entra en la tabla como familia propia (p. ej. `memoria_goal`), nivel pregunta la primera
vez de cada goal y despues preautorizada, declarada en la propuesta como se declara una raiz y visible en la
tarjeta del inbox. **(b)** entra en directo pero con el alcance recortado EN EL SERVER: solo la coleccion del
proyecto del goal (nunca global ni departamento), k<=5, titulos y no cuerpos, y el juez de privacidad
(`privacidad/juez.py`) en el camino, con un test que fije que una memoria con `identidad`/`salud` no sale.
**(c)** no va en esta tanda: el MCP arranca con `goal_estado` y `aduana_resumen` nada mas.
*Recomendacion:* **(c) para esta tanda, (b) despues.** El caso guia no la necesita (el martillo disena un
colibri, no consulta tu historia), y sacarla del camino critico deja la tarea 3 sin ninguna decision de
privacidad pendiente. Si despues se quiere, (b) con el juez es lo unico que convierte "NUNCA" en algo
medible.

**P2. `correr_datos` en directo: ¿se norman las fuentes de lectura, o se declara la fuga?** (R15.) Adentro de
`correr_confinado` todo el home fuera de PROTEGIDAS es legible, y `correr_datos` es DIRECTO.
*Opciones:* **(a)** la gramatica norma las fuentes igual que los destinos (los tres chequeos del hook), y
`decidir_argv` devuelve la familia mas restrictiva -- que es lo que el cuerpo del spec ya escribe. **(b)**
`correr_datos` deja de ser directo y pasa a pregunta. **(c)** se declara la fuga en §8 y se deja directo.
*Recomendacion:* **(a).** Es codigo que ya existe (son tres llamadas), no cuesta una vuelta por el inbox, y
mantiene la coherencia con el ruling 22(c) que ya gobierna al hook. (c) contradice tu propia tabla.

**P3. Si `flatpak install --user` no anda bajo el sandbox del CLI (S2), ¿que se hace?** (R34.) La salida que
el spec proponia no existe: `correr_confinado` no tiene red.
*Opciones:* **(a)** un tercer camino: bwrap propio CON red por allowlist (parametro nuevo en `argv_bwrap`,
que hoy es `--unshare-net` incondicional por invariante escrita del cierre). **(b)** declarar
`~/.local/share/flatpak` raiz y sumar `/tmp` y `$XDG_RUNTIME_DIR` a `allowWrite` -- que D1 ya descarto porque
el CLI bindea las rutas REALES y ahi viven `ssh-agent.socket`, el bus de sesion y `wayland-0`. **(c)**
extender D7: el `flatpak install` lo hace Pedro a mano, como el `remote-add`, y el goal solo corre lo
instalado.
*Recomendacion:* **(c) para el smoke, y decidir (a) despues con datos.** (b) esta descartada por buenas
razones. (c) cuesta un comando tuyo y desbloquea S3/S4/S5 enteros; (a) es una decision de sandbox que merece
su propia tanda y no deberia tomarse a las apuradas para que corra un smoke.

**P4. Deshacer lo que el goal instalo: ¿que pasa al cerrar?** (§12 R28, completitud.) Hoy `linea_de_deshacer`
produce un STRING que va a la fila y a un mensaje; **no hay ningun ejecutor** (grep de "deshacer" sobre
`calipso/*.py`: solo esa funcion, su fila y un texto de `server.py:2589`). Si el goal muere en el golpe 3,
1,1 GB de Blender quedan instalados, con `filesystems=host` en su manifest, y nadie te lo recuerda salvo que
leas el ledger.
*Opciones:* **(a)** nada automatico, pero al cerrar el goal la tarjeta muestra las lineas de deshacer juntas,
en un solo bloque copiable. **(b)** al `failed`/`cancelled` se estaciona una solicitud "¿deshago lo que
instale?" con las lineas exactas. **(c)** se deshace solo lo `instalar_home` al cerrar, automatico.
*Recomendacion:* **(b).** (a) te deja acumulando instalaciones que nadie mira entre corrida y corrida del
caso guia; (c) es un ejecutor automatico de comandos de desinstalacion disparado por un estado final, que es
exactamente el tipo de cosa que este diseno evita en todos lados. (b) usa el inbox, que ya existe, y te deja
la decision.

**P5. Los numeros de `correr_app`: timeout, tamano de los tmpfs, MemoryMax y CPUQuota.** (R4, R19.) Es tu
maquina y tu sesion: 11.638 MiB compartidos con tus juegos, 16 hilos.
*Opciones:* un punto de partida para que tachees o cambies -- `CORRER_TIMEOUT_S = 600` (el mismo del
criterio, hasta que S3 mida el render), `--size 512 MiB` en `/tmp` y en `/run/user/<uid>`, `--size 64 MiB` en
`~/.var/app`, `MemoryMax=4G`, `CPUQuota=800%` (8 de 16 hilos).
*Recomendacion:* esos, y que S3 mida el render antes de fijar el timeout definitivo. El `CPUQuota` es el que
mas te toca mientras jugas: 800% deja media maquina libre.

**P6. El tope del caso guia (8 golpes, 40 min) no cierra con el guion.** (R29.) Conteo minimo con CERO
iteracion: (1) pedir `instalar_home` + raiz, (2) instalar, (3) escribir el spec.json y pedir la compuerta
`correr_app`, (4) pedir el `correr` del asset, (5) ver la salida y corregir, (6) pedir el render, (7)
terminar + juez + revisor. Siete golpes sin un solo error, sobre una tarea cuyo criterio de modelo es "parece
un colibri low-poly". Plata: ~3 USD la pasada limpia, ~9 con depuracion.
*Opciones:* **(a)** subir el tope a 12 golpes / 60 min. **(b)** preautorizar `correr_app` para Blender en el
MISMO `dale`, junto con `instalar_home`, y ahorrar el golpe 3. **(c)** las dos.
*Recomendacion:* **(c).** (b) sola no alcanza (quedan 6 golpes sin margen de error); (a) sola te hace pagar
una vuelta por el inbox que ya sabes que vas a aprobar. Con las dos, el smoke tiene margen real.

**P7. La preautorizada de `correr_app`: ¿por app, o por app + script?** (Codex.) Un `si` por app es un `si`
permanente en ese goal a cualquier argv que la gramatica deje pasar -- y la gramatica es codigo nuevo con
siete clases de banderas prohibidas y una funcion de destinos propia por app.
*Opciones:* **(a)** la forma suma lo que cambia entre corridas: `{"app": X, "script": <ruta resuelta>}`.
**(b)** se acepta el `si` por app y el spec escribe que el riesgo residual es un bug de gramatica, y que por
eso los tests de la gramatica en §10.1 son **bloqueantes del merge**, no opcionales.
*Recomendacion:* **(b), con los tests declarados bloqueantes.** Con D8 el script ya es fijo y del repo, asi
que (a) agregaria una vuelta por el inbox por cada script nuevo sin comprar mucho; y `SCRIPTS_DEL_REPO` es
una lista corta y revisada, que es donde de verdad vive la garantia.

**P8. La raiz `~/.local/share/flatpak` es escribible, y eso afloja D8.** (Seguridad.) El paso 3 del caso guia
la hace aprobar como RAIZ, y una raiz es escribible tanto en el sandbox del CLI (`allowWrite`,
`goals_manos.py:449`/`:462`) como en el confinado (`--bind`, `:1063-1066`). Quien puede escribir ahi puede
reescribir los archivos del propio `org.blender.Blender` y despues pedir `correr_app`: D8 convierte "ejecutar
codigo arbitrario" en "validar un JSON" **solo si el interprete es de confianza**.
*Opciones:* **(a)** el `flatpak install --user` lo lanza el runner (como `correr_app`) y la raiz del flatpak
nunca entra ni en `allowWrite` ni en `--add-dir`. **(b)** §8 declara el residuo tal cual, y entonces
`correr_app` sigue en pregunta cada vez y no se preautoriza por app (choca con P7(b)).
*Recomendacion:* **(a), y si P3 termina en (c) el problema se disuelve solo**: si el install lo hacen tus
manos fuera del goal, la raiz no hace falta en ningun momento y ni se declara. Vale la pena mirar P3 y P8
juntas.

**P9. La aduana: ¿cada llamada MCP `cruza` o se `declara`?** (Contradicciones.) Asentar cada llamada como un
CRUCE contradice el spec de la aduana en dos puntos y cuenta dos veces el mismo egreso: la llamada es
loopback, mismo uid, no sale de la maquina; lo que sale es su respuesta dentro del contexto del martillo, o
sea "el contenido que ven los modelos", que decidiste que la aduana NO mide (spec aduana §2, invariantes 1 y
7) -- y el golpe que lo lleva ya es un cruce (spec de goals §8).
*Opciones:* **(a)** `declarar(quien, proposito, destino, motivo)` (`aduana.py:453`), que es justo lo que la
aduana tiene para lo que se cuenta pero no se mide. **(b)** no tocar la aduana: el registro de las llamadas
MCP queda donde D5 ya lo pone, en `golpes.jsonl` y en el ledger del goal. **(c)** `cruzar` igual, y §4 lo
escribe como enmienda explicita a la invariante 1 y al §2 del spec de la aduana, con el motivo, para que no
lo herede el implementador como si fuera lo de siempre.
*Recomendacion:* **(b) con `aduana_resumen` intacta.** El golpe ya cruza y el ledger ya ve la llamada (D5):
sumar una fila de aduana por llamada MCP infla el registro sin decir nada nuevo y erosiona una invariante que
te costo escribir. Si despues querés contarlas, (a).
