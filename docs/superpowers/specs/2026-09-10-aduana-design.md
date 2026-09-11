# La aduana: el unico punto por el que Calipso sale a internet, y lo que anota (2026-09-10)

Spec de brainstorming con Pedro, 2026-09-10 (tarde). Mapa del terreno que lo sostiene, verificado por dos
lentes (Claude y Codex headless): `docs/superpowers/2026-09-10-mapa-salidas-al-exterior.md`. Revisado por
cuatro lentes adversarias de Claude (codigo, seguridad, factibilidad con sondas, modelo) mas Codex headless
`gpt-5.5`; los rulings del controlador estan incorporados y marcados; lo que es de Pedro esta en la seccion
15. Todo archivo:linea es de main `446d1be`.

## 1. De donde sale

Pedro, textual: *"poner un departamento que sea como una aduana y que esa sea la unica puerta como al
internet, y los de fabrica como en un sandbox"*. Y despues, afinado: *"seria mas bien como call al
internet, porque los modelos por suscripcion si son mejores que el local, lo mismo los por API; entonces
ellos deberian si poder ver todos los archivos y cosas, pero los queries al internet si medirlos"*.

Preguntado que le importa de esa medicion, eligio dos cosas y descarto otras dos:
- **SI: cuantos cruces hay y quien los dispara** (que departamento, proyecto, turno o rutina).
- **SI: que datos se van** (poder auditar despues que salio).
- NO (por ahora): frenar por encima de un techo. NO: una sola puerta tecnica como pared.

Y sobre la contradiccion que el mapa dejo a la vista (el spec del abismo dice que el anillo 3 jamas viaja a
la nube; el codigo lo manda entero a Claude en cualquier turno de suscripcion sin /nube), Pedro decidio:
**"los modelos ven todo, incluido el anillo 3"**. Los anillos gobiernan solo el gesto /nube (y, mas
adelante, el lector). El codigo queda como esta; el spec del abismo se enmienda (seccion 13), con una
pregunta pendiente sobre la regla de credencial (seccion 15.1).

## 2. Que ES la aduana y que NO es

**Es la mitad que MIDE de la frontera de salida** que el spec de la economia decidio el 2026-08-24 (:155:
"toda salida al mundo exterior pasa por un unico modulo de frontera; no existen rutas de salida por fuera
de el") y que nunca se construyo (inventario 08-26 :30-33: "no hay un solo lugar donde auditar que sale").
La aduana cubre el egreso HTTP y por CLI del proceso del server. **La otra mitad, la que firma, no es
esta:** correo, publicacion, contacto con una persona y gasto real siguen sin construir, y cuando existan
llevan la compuerta OBLIGATORIA de Pedro (invariante 5 del 08-24 :20) del lado del motor de permisos, no
de la aduana. La aduana no es la compuerta de publicar. *(Ruling: la primera version de este spec decia
que la aduana contestaba "publicar"; eso tocaba una invariante de Pedro y se retiro.)*

**No es un departamento.** Un departamento tiene billetera, jefe, propone y puede quebrar; la aduana no
propone nada ni gasta nada. Es un modulo del kernel, como el candado o el motor de permisos.

**No mide el CONTENIDO que ven los modelos** (decision de Pedro). Las llamadas a modelos que ya miden la
telemetria y la economia (los CLIs del turno, LiteLLM, el borrador) no cruzan. Las dos llamadas a modelos
que hoy no mide NADIE se **declaran** (una linea, sin bytes, sin tocar lo que el modelo ve): la vision por
SDK de Anthropic y la rutina `reflect` (seccion 7). *(Ruling; Pedro puede vetar: la version anterior las
dejaba afuera con la justificacion, falsa, de que "ya las mide la telemetria".)*

**No frena.** Mide. Si un dia Pedro quiere frenar, la aduana ya tiene el quien y el que para que el motor
de permisos estrene una familia `red`; eso es otra tanda (seccion 11).

## 3. La forma

Un modulo `calipso/aduana.py`, puro salvo por el libro, con dos entradas:

```python
with aduana.cruzar(quien, proposito="buscar en la web", destino=url, carga=consulta) as cruce:
    pagina = urllib.request.urlopen(req, timeout=10).read()
    cruce.entro(len(pagina))
```

- `cruzar(...)` es un context manager SINCRONO. Al entrar no escribe nada; al salir escribe UNA linea
  con el resultado: `ok` si el bloque termino, `fallo` con el nombre de la excepcion si levanto (la
  excepcion se re-lanza intacta: la aduana jamas se traga un error, y un fallo de escritura del libro
  jamas reemplaza la excepcion del bloque), y los milisegundos. `cruce.entro(n)` anota los bytes que
  volvieron; es opcional.
- **El `with` vive en la funcion que hace la llamada de red** (`web._get`, `deps._run`, el closure `run`
  de los runners de github, `discovery._npm_latest`), no en el llamador. Es lo que el canario verifica
  (seccion 8); el Quien llega hasta ahi por parametro (seccion 4).
- `declarar(quien, proposito, destino, motivo)` para lo que sale dentro de una libreria y no se puede
  envolver por byte, o para lo que Pedro decidio no medir por contenido pero si contar. Escribe una linea
  con `declarado: true`: la aduana sabe que ahi hay una puerta y quien la abre, pero no cuenta bytes ni
  resultado. Un `declarar` "una vez por proceso" evalua su bandera ANTES de tocar el candado: un no-op
  nunca toma el flock.

**Nunca desde el event loop.** El libro toma el candado (invariante 10 de la capa de sesion: el flock
jamas corre en el loop). Casi todos los sitios de hoy ya corren en `asyncio.to_thread` o en endpoints
sincronos; **dos NO**: `contribute/run` (server.py:1689 -> `subprocess.run` en :1713) y `updates/run`
(:4405 -> :4416) son `async def` con el subproceso inline y hoy ya bloquean el loop hasta 120 s. **El
plan los pasa a `asyncio.to_thread` ANTES de enchufarlos.** Los declarados tambien tienen su lugar fijo
(seccion 7): la memoria se declara en el arranque (server.py:2004), no en `Memory.__init__` (que
`_switch_project` reconstruye en el loop); los probes en `_startup_warm` (ya en hilo), no en
`_subscription_probe` (que se alcanza desde `_harness_context` en el loop); whisper adentro de su
`to_thread`. **Conducta defensiva:** si igual la llaman desde el loop, la aduana lo detecta
(`asyncio.get_running_loop()`), NO toma el candado, anota `aduana_en_loop` en telemetria y sigue
(fail-open). El test lo ejercita contra los dos endpoints con el cliente de pruebas, no solo contra el
modulo aislado.

## 4. Quien

Obligatorio y tipado. Un `Quien` con:

| campo | valores | de donde sale |
|---|---|---|
| `origen` | `turno`, `gesto`, `rutina`, `jefe`, `arranque`, `ui` | el sitio de llamada lo sabe siempre |
| `chat` | id del chat | `ws_chat` |
| `proyecto` | nombre (slug) de ROOT en el momento del cruce | el sitio lo pasa (Pedro lo nombro: "que departamento, proyecto, turno o rutina") |
| `gesto` | el slash reconstruido desde `directives` (`force_web` -> `/web`, `nube` -> `/nube`, `force_route`+`force_model` -> `/claude`...); si no hubo slash, `null` y el proposito lo dice ("busqueda por heuristica") | `directives` |
| `ruta` | `local`, `subscription`, `api`, `orchestrator`: la ruta DECIDIDA al momento del cruce (`verdict.route`, post-/nube); la real queda en telemetria, correlable por chat y ts | `ws_chat` |
| `rutina` | `kind` e `id`; se rellena ademas cuando al origen lo desperto el ticker (`origen` es quien decide; `rutina` quien lo desperto) | el ticker y `POST /api/routines/{id}/run` |
| `departamento` | la clave PELADA (sin `dep:`) | el contexto del jefe |
| `endpoint` | la ruta HTTP | `ui` y `gesto` por HTTP |
| `desde` | `{credencial: maquina}` o `{credencial: sesion, tipo: navegador|tablero, aparato, hash: 8 hex}`; el ticker -> `maquina` | `request.state.sesion` (HTTP) o `_ws_autorizado` (ws) |

Criterio escrito para HTTP: **`ui`** = lo dispara la pagina sola (un GET al cargar); **`gesto`** = un
click, un POST o un slash de Pedro. Ambos llevan `endpoint`.

`desde` existe porque "quien los dispara" en una auditoria post-incidente es tambien DESDE DONDE: un
`/web` desde la Ally y uno desde una sesion `navegador` en el celular (o una cookie robada) no pueden
quedar identicos cuando el proceso ya tiene el dato.

**El Quien viaja por PARAMETRO explicito, sin default, hasta la funcion que hace la llamada.** Sin
contextvars. Firmas nuevas (el plan las escribe con codigo): `web.research(query, n, read, quien)` ->
`search(query, n, quien)` / `fetch(url, max_chars, quien)` -> `_get(url, quien, proposito, ...)`;
`browser.screenshot/render/before_after_capture(..., quien)` -> `deps.ensure(tool, quien, run_post)` ->
`_run(cmd, log, quien, ...)`; `github.default_runner(cwd, timeout, quien)` / `git_runner(cwd, timeout,
quien)` (el cruce vive en el closure `run`); `discovery.updates(quien)` -> `_npm_latest(pkg, quien)`.
`ws_chat` construye el Quien en 3554-3559 antes del `to_thread`; cada endpoint en su cuerpo. Un cruce sin
Quien no compila: no hay valor por defecto, porque un `desconocido` por defecto se vuelve el valor mas
frecuente en un mes. *(Plan: `test_seguridad_git_blindado.py:54/:56` fija la firma vieja de los runners;
se actualiza.)*

## 5. Que se fue (la carga)

Acotada a proposito. La aduana registra QUE salio, no es una segunda copia de lo que salio:

- **consulta** (una busqueda, una URL, un argv, un nombre de paquete): texto, tope 500 caracteres.
- **cuerpo** (un PR, un POST con datos): `tamano` en bytes, `sha256` (12 hex) y las **tres primeras
  lineas** (tope 200 caracteres). Nunca el cuerpo entero.
- **nada** (`carga=None`): la salida no lleva nada de Pedro (un `--version`, el registry de npm). Se dice
  explicitamente; no es lo mismo "no se" que "nada".

El recorte y el saneo (invariante 9) los hace la aduana, no el sitio de llamada: un sitio nuevo no puede
olvidarse.

## 6. El libro

`aduana.jsonl` bajo `CALIPSO_HOME`, append-only, una linea por cruce:

```json
{"ts": "...", "id": "cr_...", "quien": {"origen": "turno", "chat": "...", "proyecto": "calipso", "gesto": "/web",
 "ruta": "local", "desde": {"credencial": "maquina"}},
 "proposito": "buscar en la web", "destino": {"host": "html.duckduckgo.com", "url": "https://html.duckduckgo.com/html/"},
 "carga": {"tipo": "consulta", "texto": "precio del dolar hoy"},
 "resultado": {"estado": "ok", "ms": 812, "bytes": 48213}, "declarado": false}
```

Letra del escritor *(ruling, sondeado contra `candado.py` y `sesiones.py`)*:
- La ruta se resuelve **en CADA escritura** via `calipso_home()` (molde `sesiones._ruta`), nunca al
  importar (la trampa documentada del proyecto, que `telemetry.py` tiene).
- Se abre con `os.open(O_WRONLY | O_CREAT | O_APPEND, 0o600)` + `os.fdopen`, una `write` por linea. Si
  el archivo ya existe con otro modo, `_endurecer` (server.py:211). `open(..., "a")` no sirve: nace con
  el umask (0644 en la Ally).
- Bajo `candado(ruta_libro)` (`candado.py:93`; el `.lock` nace 0644 vacio, esta bien), tomado con
  `no_bloquear=True` y reintento acotado (3 x 50 ms). Un candado bloqueante sin timeout convertiria un
  `.lock` tomado por otro proceso en un cuelgue del hilo del turno DESPUES de la salida a internet:
  fail-hang, no fail-open.
- **Fail-open con aviso, y el `try` envuelve la toma del candado Y la escritura:** `ErrorCandado`,
  `OSError` (el `mkdir`/`open` del lock, `ENOSPC`, permisos) o cualquier fallo -> el cruce SIGUE (medir
  jamas rompe el producto) y se cuenta en `sin_libro`, un contador **en memoria** `{n, desde,
  ultimo_error}` que `GET /api/aduana` devuelve sin tocar el disco (con el disco lleno, un aviso que
  dependa del disco no se veria justo cuando importa). `telemetry.log_event("aduana_sin_libro", error=,
  n=)` es el segundo canal, best-effort, SIN destino ni carga (`telemetry.jsonl` es 0644 y se sirve
  entera).
- Nunca se edita ni se borra una linea. **Append-only es convencion del server, no propiedad del
  archivo:** cualquier proceso de Pedro puede tocarlo; el 0600 separa usuarios, no procesos (limite
  conocido, seccion 11). Rotacion: fuera de este spec.
- `_safe` ya veda `CALIPSO_HOME` a `/api/file`; el backup local lo incluye (zip 0600, como el resto).

## 7. Los enchufes: lo que pasa por la aduana el dia uno

La columna "sitio" apunta a la funcion que hace la llamada (donde vive el `with`); el Quien le llega por
parametro desde el llamador nombrado.

| sitio (archivo:linea hoy) | llamador que arma el Quien | quien | carga |
|---|---|---|---|
| `calipso/web.py:19-23` `_get` (urlopen: POST a html.duckduckgo.com desde `search`, GET a cada pagina desde `fetch`) | `ws_chat` 3554-3559 via `research` | `turno` + gesto `/web` o heuristica, ruta, chat, proyecto, desde | consulta: la query (`search`) o la URL (`fetch`) |
| `calipso/browser.py:87-89, :169-171` `page.goto` en `screenshot` y `render` (Chromium) | `ws_chat` via `web.research` (render); `POST /api/browser/screenshot` 4361-4364 (screenshot, `gesto`) | `turno` o `gesto` + endpoint | consulta: la URL |
| `calipso/deps.py:68-70` `_run` (pip install, `playwright install chromium`) | `POST /api/deps/install` 4346 (`gesto`, catalogo); los cuatro caminos de `browser.py` a `deps.ensure` (:64, :99, :155, :181) heredan el Quien de su operacion | `gesto` o `turno` | consulta: el comando |
| `calipso/github.py:71-79` closure `run` de `default_runner` (gh) y `:90-100` de `git_runner` (git) | endpoints de github 1645-1673 (`ui`/`gesto` + endpoint) | `ui` o `gesto` | consulta: el argv saneado. **git cruza SOLO con subcomando de red** (`fetch`, `push`, `pull`, `clone`, `ls-remote`); `rev-parse`, `log`, `status`, `remote get-url`, `branch` son locales y no cruzan *(ruling; cierra la pregunta 15.2 de la version anterior)* |
| `calipso/server.py:1713-1716` `contribute/run` (gh/git con `confirm:true`), **pasado a `to_thread` primero** | el propio endpoint | `gesto` + endpoint + desde | por accion: `pr` -> cuerpo (titulo + 3 lineas del body); `clone`/`fork` -> consulta (argv); `branch` -> no cruza (`git checkout -b`, local) |
| `calipso/discovery.py:92-96` `_npm_latest` (registry.npmjs.org; `_get_json` es helper) | `GET /api/updates` 4373-4376 (carga de `/`) | `ui` + endpoint | nada |
| `calipso/server.py:4416` `updates/run` (`npm install -g`), **pasado a `to_thread` primero** | el propio endpoint | `gesto` + endpoint | consulta: el paquete |

**Declarados** (una linea al ocurrir, sin bytes; los "una vez por proceso" chequean su bandera antes del
candado):
- La memoria (huggingface.co por `SentenceTransformer`): en `server.py:2004`, `arranque`, una vez.
  `_switch_project` (que reconstruye `Memory` en el loop) NO declara: chromadb cachea el modelo por
  clase y no vuelve a salir.
- Whisper (Systran/faster-whisper-tiny): adentro del `to_thread` de `_get_whisper` (4879-4884), `gesto`
  + `/api/transcribe`, una vez.
- Probes `claude/codex --version`, `auth status`, `login status`: en `_startup_warm` (7866-7874, ya en
  hilo), `arranque`, una vez. `_subscription_probe` queda sin llamada a la aduana.
- `_cli_probe` (`gh --version` + `gh auth status` -> api.github.com; server.py:2134-2158) desde
  `GET /api/connectors` (que dispara `index.html`): `ui` + endpoint, una vez por proceso.
- **Modelo fuera de la maquina:** al cargar la config (`dispatch.load_config` en el arranque) y en
  `PUT /api/config`, si el host de `local`/`api`/`classifier` no es loopback, UN `declarar(origen=
  arranque|ui, proposito="modelo fuera de la maquina", destino=host)` por proceso y por cambio de config.
  *(Ruling: la version anterior cruzaba por turno dentro de `dispatch._http_post_*`; eso choca con 18
  fakes que fijan esas firmas, con el stream lazy que cerraria el `with` antes de leer nada, y con la
  carga `nada` para un turno entero. El dia uno el caso es cero.)*
- La vision por SDK de Anthropic (`attachments.py:257-283`): `turno` + chat, proposito "vision por SDK",
  destino api.anthropic.com, por llamada. *(Nota aparte: es API paga sin gesto, contra el ruteo del 09-02;
  no es de este spec.)*
- `memory.reflect` (`memory.py:246-259`, `claude -p` con 20 episodios): `rutina` o `gesto` (boton /
  `POST /api/reflect`), proposito "reflect", por llamada.

**Lo que NO pasa por la aduana, con nombre** (son la lista de excepciones del canario, seccion 8):
- **Modelos:** los CLIs de suscripcion (`server.py:2988`, `:3026`) y sus reinvocaciones; `plugins.py:96`;
  `dispatch.py:329/:395/:406` (LiteLLM y Ollama; el CLI suelto de `dispatch.py` no mide).
- **Loopback por config o por construccion:** `server._http_up` (1885-1890; salud, corre en el LOOP);
  `discovery._get_json` via `discover_ollama`/`discover_litellm` (:48/:53) y `_cli_version` (:79-89);
  `resource_dispatcher.py:104/:138`; `attachments._vision_ollama` (:302-305); `launch_calipso.py:34/:44/:62`;
  `before_after_capture` (`server.py:1493` la llama con `http://localhost:8000`, unica llamada: lo que
  Chromium cargue al renderizar `/` es la tanda B).
- **git local:** `catastro.py:134`, `server.py:1573`, `tools/commands.py:398`, y `git_runner` con
  subcomando local.
- **Muertos en Linux:** `install`/`login` de conectores y suscripciones (`server.py:1951/:1968/:1988`,
  `Popen` con `CREATE_NEW_CONSOLE`, solo Windows; en la Ally dan 500 antes de ejecutar). Cuando se
  arreglen, cruzan como `gesto` con endpoint y carga nada.
- **Lo que carga el navegador de Pedro** (Google Fonts, Monaco desde jsdelivr): el server no lo ve. Tanda B.
- **Lo que hace un CLI agente por su cuenta** (un `gh` adentro de `claude -p`): fuera del proceso.

El dia uno cruzan los turnos de Pedro, sus gestos y la UI; el origen `rutina` no tiene enchufe (reflect es
un declarado; `departamento` es Ollama loopback) y `jefe` tampoco. Estan en el enum para que el dia que
la fabrica tenga manos no haya que redisenar el Quien.

## 8. El canario

*(Ruling: la regla de la version anterior, "primer argumento literal gh/npm/pip", matcheaba CERO sitios del
repo: todo argv es una variable, y pip/playwright van detras de `sys.executable`. La regla se invierte.)*

`test_aduana_canario.py` recorre el arbol de sintaxis de `calipso/**/*.py`, `dispatch.py` y
`launch_calipso.py` y **marca TODA** llamada a `urlopen`, `urlretrieve`, `socket.create_connection`,
`requests.*`, `httpx.*`, `websockets.connect`, `aiohttp.*` (resolviendo alias de import, incluidos los
locales como `_ur` en `attachments.py:290`) y **TODO** `subprocess.run/Popen/check_output/check_call/call`,
sin mirar argv ni host (por AST son indecidibles). Un hallazgo se salva si:

- (a) la funcion que lo contiene (o un closure anidado) contiene una llamada a `aduana.cruzar` o
  `aduana.declarar` (un `Call` en el AST, no texto: permite `contextlib.nullcontext` para cruces
  condicionales como el de git local); o
- (b) `archivo:funcion` esta en la lista de excepciones del test, **con motivo, una por linea**, para que
  sumar una excepcion sea un diff visible. Una excepcion puede decir `helper: el cruce esta en <llamador>`
  y el canario verifica que ese llamador tenga el `Call`.

Si no, la suite falla con `archivo:linea` y el texto de la llamada. Lista inicial de excepciones: el bloque
"lo que NO pasa" de la seccion 7, mas los probes declarados en otro lugar (`server.py:2056/:2062/:2071`,
`discovery.py:85`) y `memory.py:256` (reflect: el `declarar` vive en la misma funcion, asi que no hace
falta excepcion; se lista por claridad si el plan lo pone en el llamador).

Control positivo (seccion 12): un archivo temporal con un `urlopen` Y otro con un `subprocess.run(cmd)`
con `cmd` variable, ambos sin aduana, tienen que hacerlo fallar.

Limite honesto: el canario no ve lo que sale desde una libreria (chromadb, sentence_transformers, el SDK)
ni `page.goto` de Chromium. Para eso estan `declarar` y la tabla de la seccion 7 como inventario humano;
`page.goto` entra en ese inventario.

## 9. `GET /api/aduana` y la pestana Aduana en /fabrica

- `GET /api/aduana?desde=<iso>&hasta=<iso>&origen=<...>` devuelve `{cruces: [...], totales: {por_origen,
  por_destino, por_proyecto, por_desde, declarados: N}, sin_libro: {n, desde, ultimo_error}, ilegibles: N}`.
  Por defecto: hoy. Lee el libro bajo el candado, tolera lineas rotas (las cuenta, no las esconde).
- **Alcance por sesion** *(ruling con default seguro; pregunta 15.3)*: para `request.state.sesion` de tipo
  `tablero`, la respuesta lleva totales + `quien.origen` + `destino.host` + `proposito` + `estado`, **SIN
  `carga` ni `quien.chat`** (la carga de un `/web` es el mensaje crudo de Pedro, y el tablero por decision
  previa no ve chats). La respuesta completa solo a loopback (token) y a `navegador`. `lector`: 403.
  *(Plan: sumar `('/api/aduana', ('GET',))` a `tablero` en `sesiones.ALCANCES` y la fila al parametrize
  de `test_sesiones.py:405-445`.)*
- Pestana **Aduana** en `/fabrica`, molde `aparatos.js`: arriba los totales por origen, proyecto y desde,
  y el aviso de `sin_libro` si hay; abajo la lista del dia: hora, quien (con el chat o la rutina), destino,
  proposito, carga (recortada, en monoespacio), estado; los declarados con su marca. Filtros por origen,
  proyecto y desde. Sin badge: la aduana no le pide nada a Pedro.
- **Todo texto del libro se escapa; nada del libro es de confianza:** las URLs de `fetch` salen del href
  que devolvio DuckDuckGo. `aparatos.js` ya escapa siempre; aca se exige y se prueba (seccion 12).

## 10. Invariantes

1. **Toda salida a internet del proceso del server que no sea un modelo cruza o se declara.** El canario
   lo exige en la suite.
2. **La aduana no frena, no altera, no reintenta.** Una excepcion adentro del `with` se re-lanza intacta;
   un fallo del libro jamas la reemplaza.
3. **Fail-open con aviso:** sin libro (candado, disco, permisos) el cruce sigue y el hueco se ve
   (contador en memoria + telemetria + pestana). Desde el loop: no toma el candado, avisa, sigue.
4. **Append-only** por convencion del server. Ninguna linea se edita ni se borra.
5. **Carga acotada, recortada por la aduana:** consulta <= 500 chars; cuerpo = tamano + hash + 3 lineas.
6. **Quien es obligatorio, tipado y viaja por parametro.** No hay `desconocido` por defecto.
7. **La aduana no conoce a los modelos.** Un `base_url` no loopback se DECLARA al cargar la config, no se
   cruza por turno. Vision-SDK y reflect se declaran porque nadie mas los cuenta.
8. **Nunca en el event loop.**
9. **Sin secretos de MAQUINA en el libro** *(ruling; la version anterior pasaba "cada texto" por el
   detector y sobre-tapaba URLs enteras por entropia mientras dejaba pasar `?pwd=`)*. La aduana sanea antes
   de escribir: (1) `destino.url`: userinfo -> `[SECRETO]`; los VALORES de la query y del fragmento ->
   `[SECRETO]` siempre (se conservan los nombres de parametro); sobre host y path solo `_PREFIJOS`, `_JWT`,
   `_PEM`, `_CONN` del detector, nunca `_HEX` ni `_TOKEN` (un SHA de commit o una ruta de GitHub no son
   secretos). (2) argv de gh/git: solo `_PREFIJOS`/`_JWT`/`_PEM`/`_CONN`. (3) `carga.texto` que viene del
   mensaje de Pedro (consulta, 3 lineas de cuerpo): detector completo. (4) **La aduana jamas anota env,
   headers ni stdin** (ahi viven el Bearer de LiteLLM y las credenciales de git). Limite honesto: una
   contrasena humana tipeada en un `/web` queda en el libro; el libro es tan sensible como los chats, y por
   eso nace 0600.

## 11. Lo que NO hace (fuera de este spec, con nombre)

- **No pregunta ni frena.** Una familia `red` en el motor de permisos (con techos por origen y por
  ventana) es la tanda siguiente si Pedro la quiere; la aduana le deja el quien y el que listos.
- **No es la compuerta de publicar** ni de correo, contacto o gasto real (invariante 5 del 08-24): esa
  mitad de la frontera va del lado del motor de permisos, cuando exista.
- **No cobra peaje.** Tiene sentido el dia que la fabrica tenga manos; hoy cruzan Pedro, sus gestos y la UI.
- **No cierra puertas.** `HF_HUB_OFFLINE`, el chequeo de npm a pedido, Monaco y las fuentes servidas
  desde el repo: tanda B, decidida con los numeros de la aduana.
- **No mide el contenido que ven los modelos** ni intercepta a los CLIs. No es proxy. No es sandbox.
- **No protege el libro de otros procesos de Pedro:** 0600 separa usuarios, no procesos.
- **No dibuja la aduana en el mapa** (la ciudad se deriva del libro de la economia; un edificio Aduana en
  la boca del camino es de la escena, rebanada 3 del abismo).
- **No rota el libro.**
- **Lateral con nombre, otra tanda:** `~/.dispatch/decisions.jsonl` (`dispatch.py:91-93`, `:372-386`)
  guarda cada prompt del CLI suelto (500 chars) en claro y 0644, fuera de `CALIPSO_HOME`, del `_safe` y del
  backup. Moverlo bajo `CALIPSO_HOME` 0600 o apagarlo por defecto.

## 12. Verificacion

- Unitarios de `aduana.py`: una linea por cruce con la forma de la seccion 6; `fallo` re-lanza y un fallo
  del libro no la reemplaza; recorte de carga (500 / 3 lineas); `declarar` y su bandera antes del candado;
  fail-open con `sin_libro` en memoria y `aduana_sin_libro` en telemetria (candado tomado por otro proceso,
  `ENOSPC` simulado, sin permisos); desde el loop: `aduana_en_loop` y sin candado; ruta resuelta en cada
  escritura (una linea en `test_aislacion_home.py` que importe `calipso.aduana` y verifique que cae fuera
  de `~/.calipso`); creado con `umask 022` y `stat & 0o777 == 0o600` en la primera escritura.
- **Banco del saneo:** falsos positivos que deben quedar intactos
  (`https://github.com/pedro-cmyks/Observatory-Global/pull/12`, una URL de lanacion con fecha,
  `docs.google.com/document/d/...`, `git fetch origin <sha40>`) y positivos tapados (`user:pass@`,
  `?token=<hex32>` -> nombre de parametro conservado y valor tapado, `ghp_...`, `eyJ...`).
- El canario (seccion 8), con los dos controles positivos.
- Un test por enchufe con la red falsa (`monkeypatch` de `urlopen` / `subprocess.run` / `page.goto`): el
  sitio produce UN cruce con el `Quien` correcto (incluidos `proyecto` y `desde`) y la carga recortada; sin
  la aduana escribible, el sitio sigue funcionando igual. `git_runner` con `log` no cruza, con `fetch` si.
- `contribute/run` y `updates/run`: el test "nunca desde el loop" con `TestClient` (el `subprocess.run`
  falso registra el hilo en que corre).
- `GET /api/aduana`: filtros, totales, lineas rotas contadas, `sin_libro`; alcances: `tablero` recibe
  cruces sin `carga` ni `chat`, `lector` 403, `navegador` completo.
- Cliente: `aduana.test.js` con `node --test` (totales, lista, filtros, aviso de `sin_libro`, y un caso con
  `<img src=x onerror=...>` en `carga.texto` y en `destino.url` que salga escapado).
- Smoke en vivo con server desechable: un turno con `/web` real, un `gh api user`, abrir `/`; los tres
  cruces en la pestana con su quien, proyecto y desde; `aduana.jsonl` en 0600; cero `⟦` ni secretos de
  maquina en el libro; el server real no se toca.

## 13. Enmienda al spec del abismo (decision de Pedro de hoy)

En `docs/superpowers/specs/2026-09-07-abismo-consulta-design.md`, seccion de anillos (:96-110): los anillos
y el juez gobiernan el viaje del bloque **solo cuando el destino es /nube** (el gesto de privacidad de
Pedro) y, cuando exista, el lector. En un turno de suscripcion o API sin /nube el bloque viaja entero,
anillo 3 incluido, porque **"los modelos ven todo"** (Pedro, 2026-09-10). El codigo de hoy ya hace eso
(`server.py:3573, 3650, 3737`; `viaje.py:51-53`); lo que cambia es la letra del spec y un test que fije la
politica para que un fix futuro no la "arregle" al reves.

**Lo que esta enmienda NO decide sola:** la misma seccion del spec del abismo tiene la fila "Credencial:
el envio ENTERO falla cerrado, sin condicion", anclada a la decision de Pedro del 2026-09-02 (ruteo
:247-253: "la credencial jamas sale"). La decision de hoy fue sobre el anillo 3, no sobre credenciales.
Tal como esta el codigo (`viaje.py:51-53`, destino `local` = transparente), una credencial pescada por el
abismo viaja en un turno de suscripcion sin /nube. Es la pregunta 15.1; el test de la ultima tarea fija la
opcion que Pedro elija. No bloquea el resto del plan.

## 14. Corte

Una sola rama, `feat/aduana`, en un plan de ~9 tareas: (1) `aduana.py` (cruzar, declarar, Quien, libro,
saneo) + tests + banco del saneo; (2) el canario con sus controles positivos y la lista de excepciones;
(3) `contribute/run` y `updates/run` a `to_thread` (con test de hilo) y enchufe; (4) enchufes de `web.py`,
`browser.py`, `deps.py` con el Quien por parametro desde `ws_chat` y los endpoints; (5) enchufes de
`github.py` (runners con regla de red/local), `discovery.py`, y `test_seguridad_git_blindado` al dia;
(6) declarados: memoria, whisper, probes, `_cli_probe`, config no loopback, vision-SDK, reflect;
(7) `GET /api/aduana` + `ALCANCES` + `test_sesiones`; (8) pestana + tests de cliente; (9) enmienda del spec
del abismo con su test (segun 15.1), smoke en vivo, cierre.

## 15. Lo que queda para Pedro

1. **Credencial en suscripcion sin /nube (bloquea solo la tarea 9).** (a) "los modelos ven todo" incluye
   una credencial detectada por el detector: se enmienda tambien el ruteo del 09-02 con nombre; o (b) la
   regla de credencial sobrevive en TODO destino que no sea local (suscripcion y API sin /nube incluidos):
   `viaje.py:51-53` queda anotado como hueco conocido y su arreglo (correr el detector determinista, que
   es gratis, sobre el bloque antes de cualquier destino no local) va en la tarea 9. **Recomendacion: (b).**
   Un token de maquina no es "sus archivos"; es la llave de la casa, y el detector cuesta nada.
2. **Vision-SDK y reflect declarados** (seccion 2): default si; Pedro puede vetar.
3. **¿El tablero (y la APK del lector, que es tipo tablero) deberia ver la carga de los cruces?** Default:
   no (ve totales, origen, host, proposito, estado).
4. Rotacion del libro: nada por ahora (como el libro de la economia). Confirmar.
