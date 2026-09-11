# Los canarios: anclaje, degeneracion y ventana -- que Calipso se de cuenta cuando adivina, cuando se enloquece y cuando se quedo sin contexto (2026-09-11)

Spec de brainstorming con Pedro, 2026-09-11 (mediodia). Pendiente de revision adversaria y de la lectura de
Pedro. Todo archivo:linea es de main `401f8ad` + la rama `feat/memoria-procedencia` (que no toca estos
sitios).

## 1. De donde sale

Pedro, textual: *"como hacemos que sea honesto? que si no sabe que no diga? y tambien que tenga un canario
para que se de cuenta cuando se esta enloqueciendo o quedando sin contexto por ventana"*.

Lo que ya se vio en las mediciones de estos dos dias, que es el material de este spec:
- **Inventa cuando le falta el dato:** "una trilogia de ciencia ficcion ambientada en un futuro distopico"
  (nunca existio), "quedamos en revisar los costos actuales" (nunca se dijo). Porton de la memoria,
  `experimentos/porton_memoria_resultados.md`.
- **Se degenera:** en la medicion del system de produccion el 7b arranco un JSON con `"tipoDeTarea"` y se
  paso al chino; en el porton de la memoria una respuesta fue literalmente la instruccion de reentrada
  ("Segui exactamente desde ahi, sin repetir."); en el smoke del abismo copio "Pedro pregunto:" del bloque.
- **Se queda sin ventana en silencio:** el 7b corre con `CHAT_NUM_CTX = 8192` (`server.py:3004`) y Ollama,
  cuando el prompt se pasa, trunca DESDE EL PRINCIPIO sin avisar (donde va el system y el contrato; nota
  del 2026-09-01 en la memoria del proyecto). Hoy nadie mide el tamano del prompt antes de mandarlo ni
  compara despues con lo que Ollama evaluo.

**Decision de Pedro (2026-09-11): en esta primera tanda, los canarios MARCAN Y MIDEN, sin frenar, sin
reintentar y sin reescribir la respuesta.** Con los numeros se decide que frenar despues, como con la aduana.

Y el brainstorm cerro el modelo: son dos cosas distintas. La **honestidad** ("si no sabe, que no diga") es
no afirmar lo que no esta anclado; los **canarios** son darse cuenta de que algo anda mal. Los modelos
chicos no se calibran solos: lo que funciona es externo y determinista.

## 2. Tres canarios, un modulo

`calipso/canarios.py`, puro salvo por la telemetria. Corre DESPUES de cada turno del chat, en hilo (nunca en
el event loop), sobre lo que el turno ya tiene: el system armado, el historial que viajo, el mensaje, los
bloques del abismo que subieron, el texto visible final y `usage` de Ollama. Devuelve un `Veredicto` con
tres partes; el server lo persiste en la fila `chat_turn` de `telemetry.jsonl`, lo guarda en el `meta` del
mensaje assistant en `chats.json` y lo manda por el ws como senal `{type: "canario", ...}` para que la UI
marque el mensaje.

### 2.1 Anclaje (la honestidad medible)

`anclaje(respuesta, contexto) -> {"hechos": [...], "sin_anclaje": [...], "aplica": bool}`.

- **Hechos duros** que se extraen de la respuesta, por regex, sin modelo: nombres propios de dos o mas
  palabras con mayuscula ("Mariana Quintero", "El nombre de la rosa"), fechas (`2026-08-14`, "14 de agosto",
  "el 12 de octubre"), numeros con unidad o moneda ("120 dolares", "3.101 COP", "30 dias"), titulos entre
  comillas, URLs, emails, nombres de archivo con extension, identificadores con guiones (`goal_ff4b...`,
  `feat/aduana`).
- **Contexto del turno** donde se buscan: el system (con los recuerdos presentados), el historial que
  viajo, el mensaje de Pedro, y los bloques que subieron del abismo. Un hecho se considera anclado si
  aparece (normalizado: minusculas, sin acentos, espacios colapsados) en alguno; una fecha ademas si
  aparece con otro formato equivalente (`2026-08-14` ~ "14 de agosto de 2026").
- **Cuando APLICA la marca visible:** solo en los turnos que son sobre Pedro: el abismo consulto en el
  turno, o la pregunta lleva una de las senales del contrato ("te conte", "lo tenes", "acordate", "me
  dijiste", "la otra vez", "que dejamos", "te dije", "te pase"), o la ruta fue local y hubo recuerdos en el
  system. En los demas turnos (conocimiento general: "que es un websocket") el chequeo corre igual y va a
  telemetria, pero NO marca: los nombres de protocolos no son inventos y marcarlos seria ruido. Esta regla
  es la primera que los numeros pueden mover.
- **Lo que NO es un hecho:** lo que Pedro dijo en el mismo mensaje (el eco no es invento), la palabra
  "Calipso", "Pedro", los dias de la semana, los numeros sueltos sin unidad.

### 2.2 Degeneracion

`degeneracion(respuesta, system, mensaje_reentrada) -> {"senales": [...]}`, cada senal con nombre y
evidencia (el fragmento):

- `repeticion`: un n-grama de 6 palabras que aparece 3 o mas veces, o la misma linea 3 veces seguidas.
- `alfabeto`: mas del 20% de los caracteres alfabeticos fuera del latino (el chino de la medicion).
- `fuga_del_contrato`: una frase de 8+ palabras del system aparece literal en la respuesta ("No sabes nada
  de Pedro fuera de este prompt", "Pide confirmacion antes de escribir", el molde de la marca con
  `<que queres saber de Pedro>`).
- `fuga_de_reentrada`: la respuesta contiene `INSTRUCCION_CONTINUAR` ("Segui exactamente desde ahi") o
  "Venias diciendo:" (`abismo/turno.py:21, :66`).
- `eco_de_episodio`: arranca con "Pedro pregunto:" / "Pedro dijo (" / "Calipso contesto (" / "Calipso
  respondio:" (el molde de la memoria copiado como respuesta).
- `formato_no_pedido`: la respuesta es un JSON o un bloque de codigo entero y la pregunta no pedia codigo
  (`features.type` no es `code`).
- `vacia_o_rota`: respuesta vacia, o que es solo signos de puntuacion, o que termina a mitad de palabra sin
  punto y con `eval_count` igual al tope de generacion (se corto por longitud).

### 2.3 Ventana

Dos mediciones alrededor de la llamada local (y de la API; las suscripciones no exponen el tamano):

- **Antes de mandar:** `presupuesto(system, historial, mensaje, num_ctx) -> {"estimado": tokens,
  "cabe": bool, "recorte": [...]}`. Estimacion barata (chars / 3.5 para espanol, calibrada contra
  `prompt_eval_count` real en el smoke y anotada en el modulo). Si no cabe, el server **recorta lo volatil
  antes que lo estable**, en este orden y una cosa por vez hasta que quepa: el historial mas viejo (de a
  dos mensajes), los recuerdos presentados (de a uno, los de menor score), el brief del repo, los bloques
  del abismo (el mas viejo). Jamas el system base ni el contrato. Lo recortado va a la fila del turno
  (`recorte: [...]`) y a la marca visible. *(Esto SI cambia lo que el modelo ve; es la unica accion no
  pasiva del spec, y es la que evita que Ollama corte por el principio en silencio. Pedro lo aprobo como
  "recortar lo volatil antes que lo estable".)*
- **Despues de recibir:** `truncado(estimado, prompt_eval_count) -> bool`: si Ollama evaluo bastante
  menos de lo estimado (por debajo del 85%, umbral calibrado en el smoke), el prompt se trunco y el turno
  se marca `cortado`. `prompt_eval_count` ya llega en `usage["prompt_tokens"]` (`dispatch.py:458, :486`).

## 3. Donde se ve

- **En el mensaje:** marcas chicas al pie del mensaje de Calipso, en la PWA (`index.html`, junto a la meta
  de ruta y modelo) y en el chat de `/fabrica` (`chat.js`): "sin verificar (2)" con los hechos al pasar el
  mouse o tocar; "respuesta rara: fuga de reentrada"; "contexto cortado: se recorto el historial viejo" o
  "Ollama trunco el prompt". Sin colores de alarma; es informacion, no una compuerta.
- **En telemetria:** la fila `chat_turn` suma `canarios: {anclaje: {aplica, hechos, sin_anclaje},
  degeneracion: [...], ventana: {estimado, evaluado, cabe, recorte, truncado}}`.
- **En `/fabrica`:** un contador del dia en la pestana Aduana ("lo que sale, lo que entra, lo que se dice"):
  turnos con hechos sin anclaje, con degeneracion, con recorte o truncamiento. Sin badge.

## 4. La honestidad en la reentrada (un cambio de letra, con porton)

Hoy la reentrada tras un bloque del abismo dice solo "Segui exactamente desde ahi, sin repetir"
(`abismo/turno.py:21`). Pasa a: "Segui exactamente desde ahi, sin repetir. Lo que sigue se basa SOLO en lo
que subio del abismo y en lo que ya tenias en este prompt; si lo que subio no trae el dato, decilo con esas
palabras en vez de completarlo." Es un cambio de letra que el 7b puede ignorar o sobre-obedecer: **va con
su porton** (seccion 6) y no se aterriza si empeora el anclaje o sube los no-saber falsos.

## 5. Invariantes

1. **Los canarios no frenan, no reintentan, no reescriben la respuesta.** La unica accion es el recorte de
   lo volatil ANTES de mandar cuando el prompt no cabe, y se anota.
2. **Todo canario es determinista y puro** (sin modelo), medido contra un banco, con los umbrales en un solo
   lugar y anotados con su calibracion.
3. **Fail-open:** si el modulo levanta, el turno se entrega igual y el fallo va a telemetria.
4. **Nunca en el event loop.**
5. **La marca visible de anclaje solo sale en turnos sobre Pedro**; la medicion corre en todos.
6. **Nada de lo que el canario extrae (hechos) sale de la maquina ni se guarda fuera de `telemetry.jsonl`
   y `chats.json`** (que ya guardan el texto entero).
7. **El recorte jamas toca el system base ni el contrato del abismo.**

## 6. Verificacion

- **Banco de anclaje** (`experimentos/anclaje_banco.py`): las respuestas reales del porton de la memoria
  con su contexto (fixture + system + bloque): "trilogia distopica" y "revisar los costos" caen como
  `sin_anclaje`; "Mariana Quintero te presto el libro rosa" no; "120 dolares" anclado solo si el bloque
  de chats subio. Piso: 0 falsos `sin_anclaje` sobre hechos que SI estaban en el contexto (normalizacion
  de fechas y acentos incluida); >= 90% de los inventos del banco atrapados.
- **Banco de degeneracion** (`experimentos/degeneracion_banco.py`): las salidas rotas reales de las
  mediciones (el JSON con `tipoDeTarea` y el chino de `consulta_abismo_posicion_produccion.jsonl`, la fuga
  de reentrada y los "Pedro pregunto:" del porton, mas 30 respuestas sanas). Piso: 0 falsas senales sobre
  respuestas sanas; todas las rotas atrapadas.
- **Ventana:** unitarios del presupuesto y del recorte (orden, nunca el system, lo recortado se anota) y un
  test del umbral de truncamiento; en el smoke, un prompt armado a proposito por encima de 8192 contra
  Ollama real: `prompt_eval_count` cae, el turno se marca `cortado`, y con el recorte puesto el mismo turno
  cabe y no se marca.
- **Porton de la reentrada** (seccion 4): las 4 preguntas del fixture de la memoria, antes y despues de la
  letra nueva, N=2, contando `sin_anclaje` por turno y `sin_dato` (el clasificador de la memoria): se
  aterriza solo si `sin_anclaje` baja y `sin_dato` falso no sube.
- Tests del cableado: la senal ws, el `meta` del mensaje, la fila de telemetria, fail-open (el modulo
  levanta y el turno termina), nunca en el loop; cliente: las marcas en la PWA y en `/fabrica` (node).
- Smoke en vivo con server desechable: un turno que invente (fixture contaminado), uno degenerado
  (forzado con un prompt que pida JSON al 7b sin pedirlo... o el propio JSON del banco reinyectado por un
  modelo falso), uno truncado, uno sano: las tres marcas en la UI y en telemetria; el server real no se toca.

## 7. Lo que NO hace

- No frena, no reintenta, no reescribe, no cambia de ruta (una tanda futura con los numeros: el breaker).
- No usa un modelo como juez (ni el 7b ni la nube).
- No compacta el historial (resumir turnos viejos): otra tanda; hoy solo recorta.
- No mide a las suscripciones por dentro (no exponen el tamano del prompt): solo estima antes.
- No toca el ruteo, el abismo (salvo la letra de la reentrada, con porton) ni la memoria.

## 8. Corte

Una rama `feat/canarios`, ~6 tasks: (1) `canarios.py` anclaje + banco + tests; (2) degeneracion + banco +
tests; (3) ventana: presupuesto, recorte en el server antes de mandar, truncado despues, tests; (4) el
cableado: fila de telemetria, meta del mensaje, senal ws, contador en /fabrica; (5) las marcas en las dos
UIs + tests de cliente; (6) la letra de la reentrada con su porton, smoke y cierre. Corre despues del merge
de la memoria con procedencia.
