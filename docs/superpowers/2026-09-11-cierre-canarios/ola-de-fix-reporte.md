# Ola de fix del cierre de feat/canarios -- reporte (2026-09-11 noche)

Rama `feat/canarios`. Base `2a6c580`, HEAD `4cdd1e9`. Nueve commits (uno por punto, mas un retoque del
self-review), todos con rutas explicitas y el trailer. Nada tocado fuera de la rama; sin push; sin Ollama; sin
server real; `~/.ollama` solo leido (el header del GGUF en el test real del tokenizador, que ya existia).

Suite completa antes de CADA commit: `nice -n 19 .venv/bin/python -m pytest -q --ignore=test_chat_live.py`,
0 failed siempre; la ultima: **1787 passed, 4 warnings, EXIT=0** (2a6c580 daba 1773). Node
(`calipso/web/fabrica`, tras tocar `calipso/web/index.html`): **439 pass, 0 fail**.

## Commits

| sha | punto | mensaje |
|---|---|---|
| `1a16435` | 1 | fix(canarios): el no-saber honesto con senal de memoria no sale sin verificar |
| `960c540` | 2 | fix(canarios): la ventana de antes es fail-open y no frena el turno |
| `e69b795` | 3 | fix(web): la PWA pinta el historial recien con el DOM listo |
| `39976cd` | 4 | feat(canarios): interruptor CALIPSO_CANARIOS=off como rollback en caliente |
| `1dc4271` | 5 | fix(server): el aviso de Ollama caido no es una respuesta |
| `dccbf6d` | 6 | fix(canarios): la ventana en suscripcion mide el historial que el CLI recibe |
| `c76e274` | 7 | fix(porton): con 0 filas validas no se decide y el sin_dato genuino no decide |
| `127da9c` | 8 | fix(canarios): menores del cierre: cache atomico, backup, deps, smoke, docs |
| `4cdd1e9` | sr | refactor(server): la fila de error de la ventana tambien lleva `apagado` |

## Punto 1. El no-saber honesto con senal de memoria (`1a16435`)

Reproducido primero con el modulo real: los 7 textos del brief daban `aplica=True, sin_anclaje=[recuerdo]`.

Cambios (`calipso/canarios.py`):
- `:33` importa `PATRONES_FUERTES` de `calipso.memoria_procedencia` (verificado: ese modulo importa solo
  `os`, `re`, `unicodedata`; no arrastra disco ni `server`; no hubo que copiar la tupla).
- `:388` `_NEGACION_ANTES = re.compile(r"(?<![a-z])(no|nunca|jamas|tampoco)(?![a-z])[^,:;]*$")`, la regex del
  brief, aplicada en `_senal_en` (`:392-413`) sobre `oracion_norm[:m.start()]`.
- `:416` `_es_no_saber`: `afirmaciones_de_recuerdo` salta la oracion que matchea un patron fuerte.
- **Desvio anotado:** ademas de la negacion ANTES (el brief) se trata como negada la senal con la negacion
  PEGADA DESPUES (`senal + " no|nunca|jamas|tampoco"`). Sin eso el texto 5 del brief, "En la ultima
  conversacion no quedo definido el monto; no lo tengo", seguia marcado: la senal es un marco al inicio de
  la oracion (nada antes) y "no lo tengo" no es un patron fuerte. Es el espejo exacto del `(no )?` pegado
  que ya existia, no un umbral nuevo; con la negacion en cualquier lugar DESPUES (no pegada) se perdia
  `presu-acuerdo` del banco ("...se refiere a que aun no hemos llegado..."), asi que quedo solo pegada. El
  banco lo mide: 100/100 con las 26 filas.

Banco (`experimentos/anclaje_banco.py:185-203`): 4 filas nuevas de no-saber honesto con senal, esperado `{}`
y `aplica=True`: `nosabe-hermana`, `nosabe-bar`, `nosabe-recuerdos` (sinteticas, contexto del banco) y
`presu-nosabe-real` (la respuesta real del porton nueva/3/presupuesto, con `BLOQUE_MEMORIA_PRESU`, consulto 3).

`CALIPSO_HOME=$(mktemp -d) PYTHONPATH=. nice -n 19 .venv/bin/python experimentos/anclaje_banco.py`:

| | codigo de 2a6c580 (26 filas) | con el fix (26 filas) |
|---|---|---|
| hecho | tp=1 fp=0 fn=0 recall 100% precision 100% | tp=1 fp=0 fn=0 100% / 100% |
| recuerdo | tp=5 **fp=4** fn=0 recall 100% **precision 56%** | tp=5 fp=0 fn=0 **100% / 100%** |
| accion | tp=2 fp=0 fn=0 100% / 100% | tp=2 fp=0 fn=0 100% / 100% |
| aplica mal / solo_calipso mal | [] / [] | [] / [] |

Las 4 filas nuevas eran los 4 falsos; la trilogia (3 + eco) y presu-acuerdo / presu-costos siguen tp.
(El script se corre con `PYTHONPATH=.` o `-m experimentos.anclaje_banco`, como dice su docstring.)

Tests (`test_canarios_anclaje.py:245` y `:280`): los 7 textos con `_ctx()` vacio (nada que ancle por
casualidad) -> `aplica True`, `sin_anclaje == []` y `veredicto(...)["anclaje"]["sin_anclaje"] == []`; el
control "La ultima vez hablamos de la trilogia de Mariana" -> `[recuerdo]`; y `c.PATRONES_FUERTES is
memoria_procedencia.PATRONES_FUERTES`. Rojo (2 failed) -> verde.

## Punto 2. `_ventana_antes` fail-open (`960c540`)

`calipso/server.py:3131-3171`: el cuerpo (contador + `recortar`) en `try/except Exception`; en el fallo se
devuelven `secciones`/`historial` INTACTOS y la fila `{pasada, ruta, estimado: None, estimado_sin_recorte:
None, num_ctx, cabe: None, recorte: [], no_cabe: False, tokenizador: "fallback", evaluado: None, truncado:
None, done_reason: None, error: type(e).__name__}` (las mismas claves que la fila sana, mas `error`), con
`print(f"[canarios] ventana fallo: {e!r}", file=sys.stderr)`. `canarios.truncado` (`canarios.py:752`) devuelve
`None` con `estimado None` (y sigue "sin medicion" con `evaluado None`).

Tests: `test_abismo_chat.py:889` (bomba en `srv.canarios.recortar`: el turno contesta "hola Pedro", un solo
`done` al final, sin `error`, fila de ventana con `error == "RuntimeError"`, `tokenizador == "fallback"`,
`estimado None`, `evaluado 10`, el modelo vio el historial entero, la fila va a `chat_turn`) y
`test_canarios_ventana.py::test_truncado_por_pasada` (`truncado(None, 100, 8192) is None`). Rojo (el turno
terminaba en `['thinking','meta','error','cost','canario','done']` sin respuesta; `TypeError` en truncado)
-> verde.

## Punto 3. La carrera de la PWA (`e69b795`)

`calipso/web/index.html:800`: `document.addEventListener("DOMContentLoaded", () => loadChats());` en vez de
`loadChats();` suelto, con el comentario del porque (`:794-799`). Verificado con `grep -n "loadChats\|chats\["`
que nada depende de que corra en el parseo: `loadChats` es async (fetch) y `currentChatId` solo se usa al
mandar (`ws.send`), que es despues de que Pedro escriba; los otros llamadores (`chatsBtn`, `setSideView`,
`activateChat`, `createChat`, la senal `chat`) son posteriores.

`experimentos/canarios_smoke.py:289-300` y `:317-320`: la esquiva (`wait_for_function` + `activateChat`)
se quito y el docstring dice que la captura de la PWA es la prueba del primer pintado (si la carrera vuelve,
sale sin pie y lo dice). Sintaxis verificada; no se corrio (Chromium).

Test: `test_ui.py:25-38` (`carga_los_chats_tras_el_dom`: no existe `^loadChats();$` suelto y si la linea de
`DOMContentLoaded`; tambien como `check` en `main()`). Ojo: `test_ui.py` era un script sin funciones
`test_*` y pytest lo importaba sin correr nada; ahora tiene un test recolectado. Rojo -> verde; `python
test_ui.py` sigue OK (node --check del JS inline pasa). Node: 439/439.

## Punto 4. Interruptor `CALIPSO_CANARIOS=off` (`39976cd`)

- `calipso/canarios.py:39` `canarios_activos()`: `os.environ.get("CALIPSO_CANARIOS", "on").strip().lower()
  != "off"`, por llamada (patron de `abismo/turno.py:44-48`); el docstring del modulo (`:14-18`) explica que
  leer un env no es disco ni red.
- `server.py:3145-3146`: con off `_ventana_antes` mide con `num_ctx None` (no recorta) y la fila lleva
  `apagado: True` (`:3167-3168`; tras el self-review tambien en la fila de error).
- `server.py:3193-3200`: `_veredicto_del_turno` devuelve `None` sin correr el hilo.
- `server.py:4449-4450`: la senal `canario` solo con veredicto; `:4503`: `meta.canarios` solo con veredicto.
  `chat_turn` lleva `canarios: None` (el resumen `canarios_resumen.py:32` ya filtra `isinstance(dict)`).
  `resumen_de_remember(None)` ya daba dos None.
- Doc: `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md`, adenda seccion 9, bullet de los
  canarios: "**Rollback en caliente:** `CALIPSO_CANARIOS=off` ...".

Tests: `test_abismo_chat.py:915` (con `setenv off` y `CHAT_NUM_CTX=30` que en on saca el historial: sin senal
`canario`, `meta` sin `canarios`, `chat_turn.canarios is None`, remember con dos None, el modelo vio
`[system, user, assistant, user]` entero, `options.num_ctx == 30` sigue), `test_canarios_ventana.py:144`
(el env por llamada: ausente/on/""/otro -> True, off/OFF -> False) y `:159` (`_ventana_antes` con off:
`apagado True`, `num_ctx None`, `recorte []`, historial intacto; sin la variable recorta). Rojo (el server
reventaba con `**None`) -> verde.

## Punto 5. El aviso de Ollama caido no es una respuesta (`1dc4271`)

- `server.py:3117-3120`: en la rama `_local_caido` de `_chunks_for`, `usage["aviso_local_caido"] = True`.
- `server.py:4211-4212`: la pasada propaga el flag de `usage_pasada` al `usage` del turno (el fallback local
  ya pasa `usage` directo).
- `server.py:4380-4381`: `aviso_local_caido = bool(usage.get(...))`; veredicto `None` sin correr el hilo.
- `server.py:4442`: la fila `chat_turn` lleva `aviso_local_caido: True`.
- `server.py:4487`: `mem.remember` se salta. `chats.append` SI guarda el mensaje. Sin senal ni
  `meta.canarios` (los mismos `if veredicto is not None` del punto 4).

Test: `test_abismo_chat.py:941` (`_http_up -> False`, espia sobre `canarios.veredicto`: el aviso llega como
texto visible, `done` al final, sin `canario`, `veredicto` no se llamo, `memoria.guardados == []`, el ultimo
mensaje del chat es el aviso sin `meta.canarios`, `chat_turn.aviso_local_caido is True` y `canarios None`).
Rojo (la senal `canario` salia y el remember corria) -> verde. El molde de `test_turno_secciones.py:119-122`
sigue verde.

## Punto 6. La ventana en suscripcion mide el historial que el CLI recibe (`dccbf6d`)

`server.py:4022`: `_ventana_antes(secciones, historial_sub, mensaje_turno, ...)` (antes `[]`). En suscripcion
`num_ctx` es None: verificado en `recortar` (`while num_ctx and ...` no entra) y en el test (`recorte == []`,
`cabe None`, `truncado "sin medicion"`).

Test: `test_abismo_suscripcion.py:447`: el mismo `/claude hola` sin historial y con 6 mensajes largos en el
chat -> `estimado` sube mas de 500 tokens (rojo: `24 > 24 + 500` fallaba: la ventana no veia el historial)
-> verde. Que el CLI recibe ese historial ya lo fija `test_en_suscripcion_sin_tapar_el_canario_ancla_...`.

## Punto 7. El porton con 0 filas validas no decide (`c76e274`)

`experimentos/porton_reentrada.py:339` `CLAVES_QUE_DECIDEN = ("sin_anclaje", "sin_dato_falso")` con el
ruling 2 del ledger citado en el comentario y en el docstring de `aterriza_nueva` (`:342-353`), que devuelve
`None` si `v["turnos"] == 0 or n["turnos"] == 0`. `resumen()` (`:402-404`) dice "sin filas validas en
<condicion>: no se decide"; la letra del aterrizaje ahora nombra las dos que deciden. Docstring del modulo
actualizado (`:21-26`).

Tests (`test_porton_reentrada.py:83` y `:107`): todas las filas de `nueva` invalidas -> `None`, MD sin "queda
`LETRA_DEFAULT" ni "pasa a vieja" y con la frase nueva (tambien al reves, sin validas en `vieja`); `sin_dato`
genuino que sube y las otras dos no -> `True`; un `sin_dato` FALSO que sube -> `False`. Rojo (True vacuo;
False por sin_dato) -> verde. Los tests viejos siguen (el `t_sucio` de Opus sigue dando False: es sin_dato
falso).

Porton regenerado con `CALIPSO_HOME=$(mktemp -d) .venv/bin/python -m experimentos.porton_reentrada --informe`
(sin Ollama): `experimentos/porton_reentrada_resultados.md` cambia solo las dos lineas del aterrizaje; los
totales son los mismos (**vieja 12 turnos, nueva 10 (2 excluidas), `sin_anclaje` 0/0, `sin_dato` 0/0,
`sin_dato falso` 0/0**) y sigue diciendo: queda `LETRA_DEFAULT = "nueva"`, ahora con la letra "no sube en
`sin_anclaje` ni en `sin_dato falso` (un `sin_dato` genuino que sube no es empeorar, ruling 2)".

## Punto 8. Menores (`127da9c`)

- `calipso/tokenizador.py:120-128` `_generar_cache`: escribe a `cache.with_suffix(".json.tmp")` y
  `os.replace`; `cargar` (`:146-154`): si `Tokenizer.from_file` falla con el cache presente, lo borra y
  regenera UNA vez antes del fallback. Tests `test_canarios_ventana.py:257` (json truncado en un
  `CALIPSO_HOME` temporal -> `"real"`, el GGUF se lee una vez, sin `.tmp` colgado, el cache sano no vuelve a
  leerlo) y `:280` (espia sobre `os.replace`: `sha256-abc.json.tmp -> sha256-abc.json`). Los dos con un
  Ollama de mentira y un BPE de 4 tokens con la forma de qwen2 (sin el GGUF real; el test real que ya existia
  sigue verde y sigue leyendo el header de `~/.ollama`). Rojo (fallback; `[] == [...]`) -> verde.
- `calipso/backup.py:23`: `"tokenizador"` en `SKIP_DIRS`. Test `test_seguridad_backup.py:42`. Rojo -> verde.
- Dependencias: no hay `requirements.txt` ni `pyproject`; las deps viven en `calipso.sh:14` y
  `LINUX_MIGRATION.md:89` (el mismo `pip install`): sumado `tokenizers==0.22.2` (`.venv/bin/pip show`:
  0.22.2). Sin test (no hay uno para esa linea).
- `experimentos/canarios_smoke.py:170-173`: si el 7b sigue listado tras el sondeo imprime `[recursos]
  ATENCION: sigue cargado tras el sondeo; /api/ps: [...]`; solo dice "descargado" con `/api/ps` vacio.
- `docs/superpowers/2026-09-11-smoke-canarios.md:28-34` ("Cuatro corridas en total": 1, 2, el reintento
  `--fase B` y la 3), `:128-133` (pasado: las capturas de `accion`/`degenerado` se retomaron en la corrida 3
  con `LUGAR_CHROMIUM_MB = 1500` y estan en la carpeta) y el hallazgo 3 (`:177-181`: ARREGLADO en esta ola).
  `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md` (fin de la adenda): la carrera de la
  PWA y el umbral de Chromium ya no estan pendientes.

## Self-review (`git diff 2a6c580..HEAD`)

Leido entero. Un retoque (`4cdd1e9`): con `off` y la ventana reventada, la fila de error no llevaba
`apagado`; un solo camino de salida para las dos filas. Lo demas: los `if veredicto is not None` cubren los
puntos 4 y 5 a la vez; `usages.append(dict(usage))` en el fallback local arrastra el flag
`aviso_local_caido` (inofensivo: `degeneracion` solo lee `done_reason`); `_cobrar_turno` y `costs.log_usage`
leen claves fijas del `usage`.

## Desvios y dudas

1. **Punto 1, la negacion pegada DESPUES de la senal** (ver arriba): sin ella el texto 5 del brief no cerraba
   con la regla dada. Es la version simetrica del `(no )?` que ya existia; medida por el banco (100/100,
   26 filas). Si el controlador prefiere ceñirse a la letra del brief, se saca esa alternativa del patron y
   el texto 5 vuelve a marcar (y su fila del test hay que quitarla).
2. **Punto 3, `test_ui.py`** era un script (`main()`), no un test de pytest; el check quedo en los dos
   lados (funcion `test_*` recolectada y `check` en `main`). Es el archivo que el brief nombro; ningun otro
   test fijaba `index.html` de la PWA.
3. **Punto 8, dependencias:** no existe `requirements.txt`; la version quedo en `calipso.sh` y
   `LINUX_MIGRATION.md`, que son los dos `pip install` del repo (`SETUP.md` solo instala litellm).
4. **Punto 8, la clase del cache:** el test del cache roto NO usa el GGUF real (BPE chico inyectado por
   `leer_metadata`): asi corre en cualquier maquina y no escribe 11 MB. El test real preexistente sigue
   cubriendo el camino con el GGUF.
5. **Porton:** `--informe` relee el `sin_anclaje` guardado por fila en la corrida (no re-corre el canario),
   asi que el fix del punto 1 no cambia los totales del porton. La fila real nueva/3/presupuesto ("Pedro,
   segun los recuerdos que tengo, no encontramos el presupuesto exacto del taller la ultima vez") ya tenia
   `sin_anclaje 0` en la corrida (anclo de casualidad contra el contexto real que viajo); con el contexto
   ARMADO del banco el codigo viejo la marcaba (era uno de los 4 falsos), por eso entro como fila real con
   esperado `{}`. Los contextos del porton persistidos (`CANARIOS_PERSISTIR_CONTEXTO=1`) siguen pendientes
   de reemplazar a los armados (pendiente de Pedro ya anotado en el estado del proyecto).
6. Los dos archivos sin trackear `docs/superpowers/plans/2026-09-11-carga.md` y
   `docs/superpowers/specs/2026-09-11-carga-design.md` estaban antes de la ola (frente de la carga) y no se
   tocaron ni se agregaron.
