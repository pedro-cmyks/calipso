# Los canarios: anclaje, degeneracion y ventana -- que Calipso se de cuenta cuando adivina, cuando se enloquece y cuando se quedo sin contexto (2026-09-11)

Spec de brainstorming con Pedro, 2026-09-11 (mediodia). Revisado por dos lentes de Claude (modelo,
factibilidad con sondas: prototipos corridos sobre 1120 salidas reales del 7b y el tokenizador real de
qwen2.5 armado desde el GGUF) y Codex headless; los rulings estan incorporados y marcados. Todo
archivo:linea es de main `9077a8e`.

## 1. De donde sale

Pedro, textual: *"como hacemos que sea honesto? que si no sabe que no diga? y tambien que tenga un canario
para que se de cuenta cuando se esta enloqueciendo o quedando sin contexto por ventana"*.

Lo que ya se vio en las mediciones de estos dos dias, que es el material de este spec:
- **Inventa cuando le falta el dato:** "Recuerdo que te conte sobre una trilogia de ciencia ficcion
  ambientada en un futuro distopico" (nunca existio), "en la ultima conversacion quedamos en revisar los
  costos actuales" (nunca se dijo). Porton de la memoria, `experimentos/porton_memoria_resultados.jsonl`.
  **Ojo: ninguna de las ocho confabulaciones reales trae un nombre propio, una fecha, un numero ni una
  cita.** Son narrativa blanda con una afirmacion de recuerdo adelante. Un detector de "hechos duros" solo
  no las ve; eso lo probaron las lentes y define el diseno del anclaje (seccion 2.1).
- **Afirma acciones que no hizo:** "Consultando los recuerdos de Pedro...", "Anotado:", "busque en tus
  chats" en turnos donde no hubo consulta ni escritura.
- **Se degenera:** en la medicion del system de produccion el 7b arranco en castellano, siguio en chino y
  abrio un JSON con `"tipoDeTarea"` cortado a mitad; en el porton de la memoria una respuesta fue
  literalmente la instruccion de reentrada ("Segui exactamente desde ahi, sin repetir."); en varias copio el
  molde de la fuente `chats` (`[Charla con Mariana 2026-08-20] ...`) adentro de la respuesta.
- **Se queda sin ventana en silencio.** El 7b corre con `CHAT_NUM_CTX = 8192` (`server.py`). Como corta
  Ollama, medido por endpoint: en `/api/generate` (el jefe, `_pensar_local`) trunca el prompt plano desde el
  principio; en `/api/chat` (el chat) descarta primero los mensajes MAS VIEJOS que no son system y conserva
  siempre el system y el ultimo mensaje, y solo corta por tokens desde el principio cuando system + ultimo
  mensaje solos no caben. El peligro real del chat es un system gordo (adjuntos de hasta 12.000 chars,
  brief del repo, bloques del abismo en la reentrada), no el historial. Nadie mide el tamano del prompt
  antes de mandarlo ni compara despues con lo que Ollama evaluo.

**Decision de Pedro (2026-09-11): en esta primera tanda, los canarios MARCAN Y MIDEN, sin frenar, sin
reintentar y sin reescribir la respuesta.** Con los numeros se decide que frenar despues, como con la aduana.

Y el brainstorm cerro el modelo: son dos cosas distintas. La **honestidad** ("si no sabe, que no diga") es
no afirmar lo que no esta anclado; los **canarios** son darse cuenta de que algo anda mal. Los modelos
chicos no se calibran solos: lo que funciona es externo y determinista.

## 2. Tres canarios, un modulo

`calipso/canarios.py`, puro salvo por la telemetria. Corre al cierre de cada turno del chat, en hilo
(`await asyncio.to_thread(canarios.veredicto, ...)` despues de `emisor.cerrar()` y antes de la fila
`chat_turn`; try/except ancho: fail-open; tope de tiempo declarado en el modulo), sobre lo que el turno ya
tiene: las secciones del system, el historial que viajo, el mensaje, los bloques pescados del abismo, los
tramos crudos y el texto visible final, `usage` por pasada, `features`, `estado_abismo`. Devuelve un
`Veredicto` con tres partes; el server lo persiste en la fila `chat_turn` de `telemetry.jsonl`, lo guarda en
el `meta` del mensaje assistant en `chats.json` (un dict propio, distinto del que va a `mem.remember`, que
recibe solo dos numeros: `degeneracion` y `sin_anclaje`), y lo manda por el ws como senal `{type: "canario",
...}` ANTES de `done`, para que las dos UIs la apliquen sobre el mensaje que se esta cerrando.

### 2.1 Anclaje (la honestidad medible)

`anclaje(respuesta, contexto, turno) -> {"hechos": [...], "sin_anclaje": [...], "aplica": bool,
"aplica_por": [...], "anclado_solo_en_calipso": N, "tapado": bool}`.

Tres clases de cosas que el modelo afirma, y como se anclan:

1. **Hechos duros**, por regex: nombres propios de dos o mas palabras con mayuscula ("Mariana Quintero"), y
   tambien "Mayuscula + de/del/la/el + minusculas" cuando van entre comillas o backticks o precedidos de
   libro/novela/pelicula/serie ("El nombre de la rosa"); fechas (`2026-08-14`, "14 de agosto",
   "el 12 de octubre": las sin ano anclan contra dia-mes en cualquier ano y se anotan `parcial`); numeros
   con unidad o moneda ("120 dolares", "3.101 COP", "30 dias": anclan por el numeral normalizado, la
   unidad no se coteja en esta tanda); titulos entre comillas; URLs y emails (se enmascaran antes de correr
   las demas regex, para no contarlos doble); rutas de archivo (con `/` o con extension de una lista corta:
   py, md, json, jsonl, txt, csv, js, html) e identificadores tecnicos (`goal_ff4b...`, `feat/aduana`,
   `qwen2.5:7b`). NO son hechos: "Calipso", "Pedro", los dias de la semana, numeros sueltos sin unidad,
   los nombres de librerias y tecnologias con punto (`Node.js`, `socket.io`: quedan fuera de la clase
   archivo), y lo que Pedro dijo en el mismo mensaje.
2. **Afirmaciones de recuerdo** *(ruling: la clase que caza las confabulaciones reales)*: una oracion con
   una senal de memoria ("recuerdo que", "te conte", "me dijiste", "quedamos en", "hablamos de", "la
   ultima vez", "en la ultima conversacion", "segun mi recuerdo", "de acuerdo con los recuerdos",
   "anotado"). De esa oracion se toman las palabras de contenido (sin stopwords ni la senal, 4+ letras,
   normalizadas: minusculas, sin acentos), y la afirmacion queda anclada si al menos la mitad de ellas, o
   un bigrama entero, aparece en el contexto (umbral calibrado en el banco). "trilogia ciencia ficcion
   futuro distopico redes inteligencia artificial" no aparece en nada: `sin_anclaje`; "Mariana Quintero
   presto libro rosa" aparece entera en el bloque: anclada.
3. **Acciones afirmadas** *(ruling: la mitad de la honestidad que el regex no ve y el server SI sabe)*:
   "anote", "anotado", "lo guardo", "lo guarde", "consulte", "busque en tus (chats|recuerdos)",
   "consultando los recuerdos", "revise el repo": se cotejan contra lo que el turno hizo de verdad
   (`estado_abismo.consultas > 0`, herramientas ejecutadas, `remember` hecho, `web` corrido). Una accion
   afirmada que no ocurrio es `sin_anclaje` con tipo `accion`.

**Contexto de anclaje y su fuente.** Se busca en el mensaje de Pedro, en las secciones estables del system,
en los recuerdos presentados (separando la parte de Pedro y la de Calipso), en el historial (separando
usuario y assistant) y en los bloques que subieron del abismo. **Cada hecho anclado lleva su fuente**
(`mensaje_pedro`, `system_estable`, `recuerdo_pedro`, `recuerdo_calipso`, `historial_pedro`,
`historial_calipso`, `bloque`), y el veredicto cuenta `anclado_solo_en_calipso`: hechos cuya unica fuente
es lo que Calipso misma dijo antes. Ese numero es el que le dice a Pedro si el 7b se cita a si mismo (el
hallazgo h07 de la memoria con procedencia); `sin_anclaje` mide el invento de ESTE turno. *(Ruling: sin
esto el canario contradecia el modelo que la memoria acaba de fijar, "lo que dijo Calipso es contexto, no
evidencia".)* El contexto se normaliza (minusculas, sin acentos, mojibake `latin-1 -> utf-8` intentado por
linea, espacios colapsados).

**Turnos tapados (/nube):** el anclaje corre sobre los tramos CRUDOS (con marcadores `[CONTACTO_1]`) contra
el contexto tapado que viajo; los marcadores no son hechos; el veredicto lleva `tapado: true`. Si no, cada
nombre repuesto saldria "sin verificar" justo cuando el sistema hizo bien su trabajo.

**Cuando APLICA la marca visible:** el chequeo corre en todos los turnos y va a telemetria, pero la marca
"sin verificar" sale solo en los turnos que son sobre Pedro: el abismo consulto en el turno, o la pregunta
lleva una senal de memoria ("te conte", "lo tenes", "acordate", "me dijiste", "la otra vez", "que dejamos",
"te dije", "te pase", "no me acuerdo", "me acuerdo", "retoma"). *(Ruling: la tercera clausula de la primera
version, "hubo recuerdos en el system", era siempre cierta en local -el recall trae algo con score 0.38 hasta
para "hola"- y marcaba websockets y traducciones.)* La fila lleva `aplica_por` para que los numeros muevan
la regla. Sin listas de exclusion de palabras: la regla de aplicacion es la que protege del ruido.

### 2.2 Degeneracion

`degeneracion(respuesta, secciones_estables, features, usage, turno) -> {"senales": [...]}`, cada senal con
nombre y evidencia (el fragmento). Umbrales en un solo lugar, calibrados contra el banco:

- `repeticion`: un n-grama de 6 palabras que aparece 3 o mas veces, o la misma linea 3 veces seguidas.
- `alfabeto`: una corrida de 15 o mas letras no latinas consecutivas (caza el chino de la medicion, que era
  el 10% del texto y no pasaba un umbral global), o mas del 20% del total.
- `fuga_del_contrato`: una frase de 8+ palabras de las **secciones de instruccion** del system (Sistema,
  Constitucion si la hubiera, Contrato interno: "Lenguaje interno" y "El abismo") aparece literal en la
  respuesta. **Nunca contra recuerdos, bloques ni historial**: citar el bloque es la conducta deseada
  ("Mariana Quintero me presto el libro rosa, recordame..." repite 11 palabras del bloque y es correcta).
  Medido: 0 falsos sobre 1120 salidas sanas con esta restriccion.
- `fuga_de_reentrada`: la respuesta contiene `INSTRUCCION_CONTINUAR` o "Venias diciendo:"
  (`abismo/turno.py:21, :66`).
- `eco_de_episodio`: en cualquier posicion, el molde de la memoria ("Pedro dijo (", "Calipso contesto (",
  "Pedro pregunto:", "Calipso respondio:") o el de la fuente chats (`[<titulo> AAAA-MM-DD]` al inicio de una
  oracion, "[anillo", "=== Lo que subio"). *(Ruling: copiar el molde adentro de una respuesta correcta SI se
  marca -es rara aunque acierte- y la fila lo dice; la UI muestra "respuesta rara: eco del molde".)*
- `formato_no_pedido`: la respuesta es un JSON entero, o CONTIENE un fence ```json o un objeto `{` con 3+
  claves, y `features.type` no esta en el conjunto de tipos que legitimamente traen codigo (el mismo que
  usa el server: code, repo, refactor, exec, agentic). Un fence ``` sin json (el estado del repo) no cuenta.
- `cortada`: `done_reason == "length"` (dispatch guarda `usage["done_reason"]` del chunk final de Ollama:
  una linea) o respuesta vacia / solo puntuacion. Un turno con `steered` no cuenta (termina en
  "...(interrumpido)" a proposito).

### 2.3 Ventana

**Por pasada, no por turno** *(ruling)*: un turno con abismo hace hasta cuatro llamadas a Ollama con prompts
distintos y crecientes, y el server suma `prompt_tokens` de todas. La fila lleva `ventana: [{pasada,
estimado, evaluado, cabe, recorte, truncado}]` y la marca visible resume ("pasada 2 cortada").

- **Antes de cada pasada:** `presupuesto(secciones, historial, mensaje, bloques, num_ctx)` estima los
  tokens. Estimacion **exacta** con el tokenizador real: `tokenizers` esta en el venv y un `tokenizer.json`
  generado una vez desde el GGUF del modelo local (`~/.ollama`; se regenera si cambia el blob; fallback
  3.3 chars/token para lo que entra, medido: mediana 3.42 sobre systems y contratos reales; las respuestas
  dan 3.9). La senal primaria es determinista y previa: `estimado > num_ctx`, y cuanto.
- **El recorte, solo donde el techo es real y lo impone Calipso (ruta local, `CHAT_NUM_CTX`).** Si no cabe,
  se recorta lo volatil antes que lo estable, una cosa por vez hasta que quepa, en este orden: el historial
  mas viejo (de a dos mensajes), los recuerdos presentados (de a uno, los de menor score), el brief del repo,
  los resultados web, el bloque del abismo mas viejo (nunca el de esta pasada). **Intocables:** el system
  base (Sistema), el contrato interno con el contrato del abismo (`contrato_abismo`, distinto de los
  `bloques_pescados`), la memoria nucleo, el Estado real, el mensaje de Pedro, y **los adjuntos** *(ruling:
  Pedro los adjunto a proposito en este turno; si aun asi no cabe, se manda igual y se marca)*. Estado
  terminal `no_cabe`: se manda igual, se marca "no cupo aun recortando", va a la fila. Lo recortado va a la
  fila y a la marca visible. *(Esto SI cambia lo que el modelo ve; es la unica accion no pasiva del spec:
  reemplaza un corte silencioso de Ollama por uno visible y anotado.)* En la ruta api solo se estima y se
  anota contra el techo del modelo configurado, sin recortar; las suscripciones solo estiman.
- **Para poder recortar, el turno conserva la ESTRUCTURA** *(ruling; el system viaja hoy como un string
  plano)*: `_sistema_del_turno` / `_build_context` devuelven la lista de secciones (`context_sections` mas
  las que el server apendea: vision, adjuntos, departamento, resultados web) y se renderiza recien al armar
  el payload; `prompt_reentrada` agrega los bloques como secciones; `_chunks_for` recibe el historial
  prearmado y DEVUELVE los `messages` que mando, para que el canario compare exactamente lo que viajo.
- **Despues de cada pasada:** `truncado(estimado, evaluado, num_ctx)`: `evaluado` es `prompt_eval_count`
  de esa pasada (`usage_pasada["prompt_tokens"]`; `null` si la pasada se corto antes del `done`, y entonces
  `truncado = "sin medicion"`). Truncado si `estimado > num_ctx`, o `evaluado >= 0.95 * num_ctx`, o
  `evaluado < 0.85 * estimado`. Medido en el smoke del 09-10: Ollama 0.30.10 cuenta el prompt completo aun
  con cache de prefijo (1534, 1626, 1925...), asi que la comparacion vale; el smoke repite el control de cache
  (dos turnos seguidos con el mismo system tienen que reportar `prompt_eval_count` parecido) por si una
  version futura descuenta el cache.

## 3. Donde se ve

- **En el mensaje:** marcas chicas al pie del mensaje de Calipso, en la PWA (`index.html`: un `<div
  class="msg-foot">` dentro de `.msg.bot`, aplicado sobre el `botEl` al llegar la senal y desde
  `msg.meta.canarios` al pintar el historial) y en el chat de `/fabrica` (`chat.js`: `canario` entra en
  `EVENTOS_DEL_STREAM` y el reductor guarda la marca en el ultimo turno de Calipso, no como turno aparte):
  "sin verificar (2)" con los hechos al pasar el mouse o tocar; "respuesta rara: fuga de reentrada";
  "contexto: se recorto el historial viejo" / "Ollama trunco la pasada 2" / "no cupo". Sin colores de
  alarma; es informacion, no una compuerta.
- **En telemetria:** la fila `chat_turn` suma `canarios: {anclaje: {aplica, aplica_por, hechos,
  sin_anclaje, anclado_solo_en_calipso, tapado}, degeneracion: [...], ventana: [...]}`. Los tests de forma
  de `chat_turn` son tolerantes (presencia y contenido minimo), no igualdad exacta.
- **El resumen:** `experimentos/canarios_resumen.py` sobre `telemetry.jsonl` (turnos con `sin_anclaje`,
  degeneracion, recorte, truncado, por ruta y por `aplica_por`). *(Ruling YAGNI: el contador en la pestana
  de /fabrica se hace cuando los numeros digan cual conviene mirar; los portones se cierran con un `.md`.)*

## 4. La honestidad en la reentrada (un cambio de letra, con porton, en su propia task)

Hoy la reentrada tras un bloque dice solo "Segui exactamente desde ahi, sin repetir"
(`abismo/turno.py:21`). Pasa a, **solo cuando hay bloques** (tras un `fallo` la reentrada va sin bloque y
"se basa SOLO en lo que subio" con nada subido seria un no-saber inducido): "Segui exactamente desde ahi, sin
repetir. Lo que sigue se basa SOLO en lo que subio del abismo y en lo que ya tenias en este prompt; si lo
que subio no trae el dato, decilo con esas palabras en vez de completarlo." Es un cambio de letra que el 7b
puede ignorar o sobre-obedecer, asi que:
- la frase inducida entra al clasificador de la memoria por el camino de siempre: `no trae (el|ese|este)
  dato` a `PATRONES_FUERTES` via `experimentos/no_saber_banco.py` con el piso de 0 falsos;
- `sin_dato falso` se define y se computa: la respuesta es no-saber Y la verdad sembrada del fixture
  aparece en un bloque que subio en ese turno (la fila `chat_turn` del server desechable lleva los textos
  de los bloques; en produccion no);
- la letra que aterrice se ata a un archivo en `experimentos/variantes/` con un test byte a byte, como el
  contrato del abismo; el test de estructura de la reentrada (`test_abismo_turno.py`) actualiza solo el
  sufijo;
- va en su propia task, separada del recorte, para poder atribuir cualquier cambio del banco.

## 5. Invariantes

1. **Los canarios no frenan, no reintentan, no reescriben la respuesta.** La unica accion es el recorte de
   lo volatil ANTES de mandar cuando el prompt no cabe en local, y se anota; si aun asi no cabe, se manda
   igual y se marca.
2. **Todo canario es determinista y puro** (sin modelo), medido contra un banco, con los umbrales en un solo
   lugar y anotados con su calibracion.
3. **Fail-open:** si el modulo levanta o se pasa del tope de tiempo, el turno se entrega igual y el fallo va
   a telemetria.
4. **Nunca en el event loop.**
5. **La marca visible de anclaje solo sale en turnos sobre Pedro**; la medicion corre en todos y dice por
   que aplico.
6. **Cada hecho anclado dice donde anclo**, y lo anclado solo en lo que Calipso dijo se cuenta aparte.
7. **Nada de lo que el canario extrae sale de la maquina ni se guarda fuera de `telemetry.jsonl` y
   `chats.json`.**
8. **El recorte jamas toca el system base, el contrato del abismo, la memoria nucleo, el Estado real, el
   mensaje de Pedro ni los adjuntos.** Tests que fallan si lo toca.
9. **La ventana se mide por pasada.**

## 6. Verificacion

- **Banco de anclaje** (`experimentos/anclaje_banco.py`): las respuestas reales del porton de la memoria
  con su contexto exacto (el server desechable persiste por fila el system, el historial y los bloques que
  viajaron; el banco corre sobre `full` post-filtro), mas respuestas sanas tecnicas y creativas de los
  JSONL de `experimentos/`. Se mide **precision y recall por clase** (hechos duros, afirmaciones de
  recuerdo, acciones), no un cero global *(ruling)*: la trilogia y "revisar los costos" caen como
  afirmacion de recuerdo sin anclaje; "Mariana Quintero te presto el libro rosa" anclada en `bloque`;
  "Consultando los recuerdos de Pedro..." con `consultas == 0` cae como accion; "Un WebSocket es..." no
  produce marca (no aplica). Piso: recall >= 90% sobre los inventos del banco; precision >= 90% sobre
  los turnos que aplican.
- **Banco de degeneracion** (`experimentos/degeneracion_banco.py`): las salidas rotas reales (el JSON con
  `tipoDeTarea` y el chino, la fuga de reentrada, los ecos del molde de chats) mas 30 respuestas sanas,
  incluidas las que citan el bloque. Piso: 0 falsas senales sobre las sanas; todas las rotas atrapadas.
- **Ventana:** unitarios del presupuesto (tokenizador real y fallback), del recorte (orden, intocables
  con tests que fallan si se tocan, lo recortado se anota, `no_cabe`), del truncado por pasada (`null` sin
  `done`); y en el smoke, contra Ollama real: un prompt armado por encima de 8192 por system gordo
  (adjuntos) -> `truncado` y el contrato deja de sobrevivir (una frase-centinela del system que el modelo
  tenga que repetir); el mismo turno con el recorte puesto cabe; el control de cache (dos turnos iguales
  seguidos); calibracion del tokenizador sobre 3+ prompts reales (min, mediana, max de chars/token).
- **Porton de la reentrada** (seccion 4): las 4 preguntas del fixture de la memoria, antes y despues de la
  letra nueva, chat nuevo por turno, **N=3** (12 turnos por condicion; con N=2 el porton de la memoria
  vario 2-4 en el ruido), contando `sin_anclaje`, `sin_dato` y `sin_dato falso` por turno: se aterriza solo
  si **no empeora en ninguna** de las tres.
- Tests del cableado: la senal ws antes de `done`, el `meta` del mensaje, la fila de telemetria, el
  `remember` con los dos numeros, fail-open (el modulo levanta y el turno termina), tope de tiempo, nunca
  en el loop, `_chunks_for` devuelve lo que mando; cliente: las marcas en la PWA y en `/fabrica` (node),
  `canario` en `EVENTOS_DEL_STREAM`.
- Smoke en vivo con server desechable: un turno que invente (fixture contaminado), uno con accion afirmada
  sin accion, uno degenerado (una salida rota del banco reinyectada por un modelo falso), uno truncado, uno
  sano, uno /nube tapado: las marcas en las dos UIs y en telemetria; el server real no se toca.

## 7. Lo que NO hace

- No frena, no reintenta, no reescribe, no cambia de ruta (una tanda futura con los numeros: el breaker).
- No usa un modelo como juez (ni el 7b ni la nube).
- No compacta el historial (resumir turnos viejos): otra tanda; hoy solo recorta.
- No mide a las suscripciones por dentro (no exponen el tamano del prompt): solo estima antes.
- No toca el ruteo, el abismo (salvo la letra de la reentrada, con porton) ni la memoria (salvo el patron
  `no trae el dato` por el banco).
- No coteja unidades ni anos en fechas sin ano (se anotan `parcial`).
- No pone el contador en /fabrica (primero el resumen por script).

## 8. Corte

Una rama `feat/canarios`, ~8 tasks: (1) `canarios.py` anclaje (tres clases, fuentes, normalizacion,
tapados) + banco + tests; (2) degeneracion + `done_reason` en dispatch + banco + tests; (3) la estructura
del turno (secciones, `_chunks_for` con historial prearmado y `messages` devueltos, `prompt_reentrada` por
secciones) + tests de que nada cambia byte a byte sin recorte; (4) ventana: tokenizador desde el GGUF con
fallback, presupuesto, recorte con intocables, truncado por pasada, tests; (5) el cableado (veredicto en
hilo antes de `chat_turn`, `meta`, `remember`, senal ws) + `canarios_resumen.py` + tests; (6) las marcas en
las dos UIs + tests de cliente; (7) la letra de la reentrada con su porton (N=3) y el patron en el banco de
la memoria; (8) smoke en vivo y cierre. Corre despues del merge de la memoria con procedencia (hecho).
