# Ola de fix del cierre de feat/canarios (unica; 2026-09-11 noche)

Rama `feat/canarios`, HEAD `2a6c580`. Seis revisores (Task 8, tres areas, dos lentes) mas Codex gpt-5.5
coincidieron en estos hallazgos. Sin criticos. Todos los puntos de abajo se arreglan en ESTA ola, en el
orden dado, con TDD (test rojo primero donde hay test), suite completa una vez antes de cada commit
(`nice -n 19 .venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`, ~140 s, 0 failed),
node (`cd calipso/web/fabrica && ~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test`)
si se toca `calipso/web/`, commits con rutas explicitas y el trailer. Un commit por punto (o por pareja de
puntos chicos afines). Las lineas citadas son de `2a6c580`: verifica con `grep -n` antes de editar.

## 1. El no-saber honesto con una senal de memoria no puede salir "sin verificar" (importante; dos revisores)

`calipso/canarios.py:367-378` (`_senal_en`) y `:402-416` (`afirmaciones_de_recuerdo`). Hoy la negacion solo
se reconoce PEGADA a la senal (`no hablamos de`). Verificado con el modulo real (contexto del banco
`_ctx(M_PRESU)` o el system podado): pregunta "te dije lo de mi hermana?" + respuesta "No encontre nada de lo
que me dijiste sobre tu hermana. Contame y lo anoto." -> `aplica=True`, `sin_anclaje=[recuerdo]`, marca
visible sobre una respuesta honesta. Idem "No tengo guardado el link que me dijiste del bar.", "No hay nada en
mis recuerdos sobre la ultima vez que hablamos de tu hermana.", "No tengo ese dato: la ultima vez no quedo
nada anotado sobre el presupuesto del taller", "En la ultima conversacion no quedo definido el monto; no lo
tengo", "No me consta que en la ultima conversacion hayamos cerrado una cifra", y la respuesta REAL del porton
(nueva/3/presupuesto) "Segun los recuerdos que tengo, no encontramos el presupuesto exacto del taller la
ultima vez". Es exactamente la clase que Pedro pidio proteger ("que si no sabe que no diga").

Arreglo (ruling del controlador, revertible, medido por el banco):
- En `_senal_en`, ademas del `(no )?` pegado, tratar como NEGADA la oracion cuyo tramo ANTES de la senal, sin
  `,` `:` `;` en el medio, contiene una palabra entera de negacion:
  `re.search(r"(?<![a-z])(no|nunca|jamas|tampoco)(?![a-z])[^,:;]*$", oracion_norm[:m.start()])`.
- En `afirmaciones_de_recuerdo`, saltar la oracion si la matchea un patron fuerte de no-saber:
  importar `memoria_procedencia.PATRONES_FUERTES` (es puro, sin disco; verifica que importar
  `calipso.memoria_procedencia` desde `canarios` no arrastre disco ni `server`; si arrastra, copia la tupla
  a `canarios` con un test de igualdad contra la original).
- Banco: sumar a `experimentos/anclaje_banco.py` 4 filas de no-saber honesto con senal (las tres sinteticas
  de arriba con contexto del banco y la real de nueva/3/presupuesto), esperado `{}` y `aplica=True`;
  re-correr `CALIPSO_HOME=$(mktemp -d) nice -n 19 .venv/bin/python experimentos/anclaje_banco.py` y pegar
  los numeros en el reporte (piso: recall/precision >= 90% por clase se mantienen; hoy 100/100; la trilogia
  y presu-* no pueden bajar).
- Test en `test_canarios_anclaje.py`: los 7 textos de arriba con contexto que no los contenga ->
  `sin_anclaje == []` y la fila `sin_anclaje` de `veredicto` vacia; y un caso de control que SIGUE marcando:
  "La ultima vez hablamos de la trilogia de Mariana" sin la trilogia en el contexto -> `[recuerdo]`.

## 2. `_ventana_antes` fail-open (importante; tres revisores)

`calipso/server.py:3126-3143`, llamadores `:3992-3995`, `:4136-4138`, `:4307-4309`. Corre en hilo (bien)
pero sin try: una excepcion en `tokenizador.contador` / `canarios.recortar` / `render_context` cae al
`except` general del turno y en ruta local termina en `{type: error}` sin respuesta: el canario frenaria el
turno (invariantes 1 y 3). Arreglo: envolver el cuerpo de `_ventana_antes` en `try/except Exception as e`:
devolver `(secciones, historial)` INTACTOS y la fila `{pasada, ruta, estimado: None, evaluado: None,
num_ctx, recorte: [], no_cabe: False, cabe: None, truncado: None, tokenizador: "fallback", error:
type(e).__name__}` (respeta las claves que hoy lleva la fila: mira `:3139-3143` y `_ventana_despues`), y un
`print(f"[canarios] ventana fallo: {e!r}", file=sys.stderr)` como hace `_veredicto_del_turno`.
`canarios.truncado(estimado=None, evaluado=<n>, num_ctx)` debe devolver `None` (hoy tolera evaluado None;
cubrir estimado None). Test en `test_abismo_chat.py` con el harness `chat`: `monkeypatch.setattr(srv.canarios,
"recortar", bomba)` -> el turno contesta, `done` al final, la fila de ventana con `error == "RuntimeError"`;
y un unitario de `truncado(None, 100, 8192) is None` en `test_canarios_ventana.py`.

## 3. La carrera de la PWA al arrancar (importante; smoke hallazgo 3, confirmado por el revisor de UIs)

`calipso/web/index.html:794` (`loadChats()` en el script clasico, corre en el parseo), `:584-595` (el
`<script type="module">` que cuelga `window.Canarios`, diferido), `:1694` (guarda de `aplicarCanario`),
`:2212` (`renderHistory` llama `aplicarCanario` desde `meta.canarios`). Si el historial llega antes que el
modulo, las marcas guardadas no se ven hasta re-abrir el chat. Arreglo minimo (una linea): en `:794`
reemplazar `loadChats();` por `document.addEventListener("DOMContentLoaded", () => loadChats());` (los
module scripts sin async corren antes de DOMContentLoaded; si el modulo falla, DOMContentLoaded dispara
igual: fail-open con la guarda de `:1694`). Verifica que ningun otro camino dependa de que `loadChats` haya
corrido en el parseo (`grep -n "loadChats\|chats\[" index.html`). Quitar la esquiva del smoke en
`experimentos/canarios_smoke.py:319-320` (el `wait_for_function` + `activateChat`): la captura de la PWA
pasa a ser la prueba del primer pintado; deja un comentario de por que. Check estatico en `test_ui.py` (o el
test que hoy fije `index.html`; buscalo con `grep -ln "index.html" test_*.py`): la linea `loadChats()`
suelta en el parseo no existe y la de `DOMContentLoaded` si.

## 4. Interruptor `CALIPSO_CANARIOS=off` (importante; lente de riesgo)

No hay rollback en caliente: el recorte, el veredicto, la senal ws, `meta.canarios` y los dos numeros del
remember corren siempre. Arreglo: un env leido POR LLAMADA con el patron de `abismo/turno.py:44-48`
(`letra_activa()`): `canarios_activos() -> bool` en `calipso/canarios.py` (`os.environ.get("CALIPSO_CANARIOS",
"on").lower() != "off"`; el modulo sigue puro: leer un env no es disco ni red, documentalo en el docstring).
Con `off`: `_ventana_antes` mide con `num_ctx=None` (no recorta) y la fila lleva `apagado: True`;
`_veredicto_del_turno` devuelve `None` sin correr el hilo; el server no manda la senal `canario` ni escribe
`meta.canarios`; `resumen_de_remember` ya tolera `None`. Tests por el harness: con `monkeypatch.setenv
("CALIPSO_CANARIOS", "off")` el turno no trae senal `canario`, `meta` sin `canarios`, y el recorte no
corre aunque no quepa. Documentar el interruptor en `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-
seguimos.md` (adenda seccion 9, como "rollback en caliente").

## 5. El aviso "[Calipso] no puedo contestar... Ollama no esta disponible" no es una respuesta (importante; lente de riesgo; preexistente en main, agravado por la rama)

`calipso/server.py:3117-3120` (`_local_caido`), `:4449-4456` (remember), `:4459-4466` (`chats.append`),
`:4346-4359` (veredicto con `hizo.recordo = bool(full)`). Con Ollama caido el aviso es `full`: entra a la
memoria episodica como "Calipso contesto: [Calipso] no puedo...", el canario lo mide limpio (0/0,
`recordo=True`) y esos ceros van al remember. Arreglo minimo: en `_chunks_for`, en la rama `_local_caido`,
marcar `usage["aviso_local_caido"] = True` (el `usage` que ya recibe); en el cierre del turno, con ese flag:
saltar `mem.remember` (no es una respuesta), veredicto `None` (sin senal, sin `meta.canarios`), y la fila
`chat_turn` con `aviso_local_caido: True`. `chats.append` SI guarda el mensaje (Pedro lo leyo). Test por el
harness (`test_turno_secciones.py:119-122` ya tiene el molde de Ollama caido en `_chunks_for`): el turno con
Ollama caido no llama a `remember` (espia) y no manda senal `canario`.

## 6. La ventana en suscripcion mide el historial que el CLI recibe (importante segun Codex; menor segun la lente)

`calipso/server.py:3992-3995`: `_ventana_antes(secciones, [], mensaje_turno, ...)` con historial vacio,
pero `mensajes_pasada` (`:4003-4005`) incluye `historial_sub` y `_subscription_invocation` (`:3197-3205`)
inyecta `=== Conversacion anterior ===` desde `_history_messages`. El estimado subestima justo en charlas
largas. Arreglo: pasar `historial_sub` a `_ventana_antes` en `:3993` (en suscripcion `num_ctx` es None: solo
estima, no recorta: verifica que con `num_ctx None` `recortar` no toque nada). Test en `test_abismo_suscripcion.py`
o el harness que cubra suscripcion: la fila de ventana de una charla con historial da `estimado` mayor que la
misma sin historial.

## 7. El porton con 0 filas validas no decide (importante; revisor de UIs)

`experimentos/porton_reentrada.py:329-335` (`aterriza_nueva`), `:310-327` (`totales`). Con 0 filas validas en
una condicion, `totales` da 0/0/0 y `aterriza_nueva` devuelve True (vacuo). Arreglo: `if v["turnos"] == 0 or
n["turnos"] == 0: return None` antes del `all()`; `resumen()` dice "sin filas validas en <condicion>: no se
decide". Ademas, `aterriza_nueva` compara solo `sin_anclaje` y `sin_dato_falso` (ruling 2 del ledger: un
`sin_dato` genuino que sube no es empeorar), con el docstring citando el ruling. Tests en
`test_porton_reentrada.py`: todas las filas de nueva invalidas -> `None` y el MD sin "queda LETRA_DEFAULT";
`sin_dato` sube y las otras dos no -> True. Regenerar `experimentos/porton_reentrada_resultados.md` con
`--informe` (sin Ollama) y confirmar que sigue diciendo lo mismo con la letra nueva del veredicto.

## 8. Menores baratos (un commit)

- `calipso/tokenizador.py:133-140`: escribir el cache a `cache.with_suffix(".json.tmp")` y `os.replace`; si
  `Tokenizer.from_file` falla con el cache presente, borrarlo y regenerar UNA vez antes de caer al fallback.
  Test con un json truncado en un `CALIPSO_HOME` temporal -> `tokenizador == "real"` tras regenerar.
- `calipso/backup.py:21`: sumar `"tokenizador"` a `SKIP_DIRS` (11-23 MB regenerables). Test si `SKIP_DIRS`
  tiene uno.
- `requirements.txt` (o donde esten las dependencias): declarar `tokenizers` con la version del venv
  (`.venv/bin/pip show tokenizers`).
- `experimentos/canarios_smoke.py:152-171`: si tras el sondeo el 7b sigue listado, imprimir
  `[recursos] ATENCION: sigue cargado ...` (no "descargado").
- `docs/superpowers/2026-09-11-smoke-canarios.md:28` ("Dos corridas") y `:128-132` (restos en presente que
  hoy son falsos: "NO estan", "se retoman") -> pasado explicito con el conteo real (corridas 1, 2, reintento
  `--fase B`, corrida 3). `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md:298`: el item
  "umbral de recursos para Chromium" ya no esta pendiente (1500 MB, corrida 3).

## Lo que NO se toca en esta ola (rulings del controlador, para el addendum del spec)

- `recordo = bool(full)` (Codex): ruling 3 del ledger, declarado; cotejar contra una escritura explicita es
  otra tanda.
- El porton aterrizo la letra nueva sobre 0/0/0 con dos contadores ciegos (lente del spec): ruling en el
  addendum (queda por default, reversible con `CALIPSO_REENTRADA=vieja`); re-medir es otra tanda.
- `reserva_respuesta` en el presupuesto, el titulo tras `novela|libro` que arrastra cola, `y/o`/`km/h` como
  archivo, el secciones_pasada del orquestador, `sin_dato` por turno en telemetria: al addendum y a la
  siguiente calibracion con telemetria real.
- `server.py:2450` (`/local` cae al ranking entero): frente de la carga (spec v2, task 2).

## Reporte

Escribi `/var/home/pedro/calipso/.superpowers/sdd/2026-09-11-canarios/ola-de-fix-report.md` con: por
punto, que cambiaste (archivo:linea nuevas), el test rojo->verde, los numeros del banco (punto 1) y del
porton regenerado (punto 7); la suite con conteo y EXIT; node; desvios y dudas. Salida estructurada: status,
base_sha (2a6c580), head_sha, commits, tests, concerns, report_file.
