# La memoria con procedencia: lo que dijo Calipso es contexto, no evidencia (2026-09-11)

Spec de brainstorming con Pedro, 2026-09-11 (madrugada), a partir del hallazgo h06 del smoke del abismo
(`docs/superpowers/2026-09-10-smoke-abismo-system-podado.md`). Revisado por dos lentes de Claude (modelo,
factibilidad con sondas) y Codex headless; los rulings estan incorporados y marcados. Todo archivo:linea es
de main `401f8ad`.

## 1. De donde sale

El smoke del system podado mostro que la fuente `memoria` del abismo, y los "Recuerdos relevantes" del
system de cada turno, le devuelven al 7b SUS PROPIAS RESPUESTAS anteriores como recuerdos: cada turno se
guarda como un episodio `"Pedro pregunto: <user_msg>\nCalipso respondio: <full>"` (`server.py`, el
`mem.remember` del final de `ws_chat`, `scope="global"`, `route=verdict["route"]`, `kind="chat"`) y el
recall trae el par entero, sin decir quien dijo que (`memory.py` `Scope.recall`; `prompt_compiler.py`
"Recuerdos relevantes"; `abismo/fuentes.py` `memoria()`). Con la consulta hecha, el 7b recibio "Calipso
respondio: No tengo registros de quien te presto..." y lo repitio; en otro turno construyo una
confabulacion sobre su propia respuesta previa. Cuanto mas falla, mas fallos recuerda.

La primera propuesta ("las respuestas de Calipso no son memoria") Pedro la corrigio: *"las respuestas de
Calipso son contexto"*. Lo que sigue es como lo manejan los laboratorios de frontera, adaptado: el
transcript con roles es contexto; la memoria a largo plazo son hechos destilados; lo recuperado de charlas
pasadas viaja con procedencia; y un no-saber no es un recuerdo.

**Decisiones de Pedro (2026-09-11):**
1. **Quien decide que una respuesta NO es un recuerdo: nadie al escribir.** *"Guardar todo, decidir al
   leer."* Nada se filtra ni se pierde en disco.
2. **Al leer: procedencia + degradar el no-saber.** Siempre "Pedro dijo: ..."; la respuesta de Calipso va
   etiquetada con ruta y fecha, y si es un no-saber (patrones fijos, aplicados AL LEER) se reemplaza por
   "Calipso no tenia el dato entonces".
3. **Lo viejo: reindexar todo con el formato nuevo.** Un script de un solo tiro sobre el home real que agrega
   los metadatos de procedencia a cada episodio existente, conservando id y texto (el embedding no cambia).
   Lo corre Pedro, con el server apagado.

## 2. Que cambia y que no

**Cambia el metadato del episodio, no su texto.** El `remember` del chat sigue guardando el par como
documento (asi el embedding no cambia; el id es hash de texto + metadatos + ts, o sea distinto para cada
episodio nuevo, como hoy) y suma metadatos: `ruta` = **la ruta USADA** (`used_route`: la que contesto de
verdad, `local` tras un fallback, `orchestrator` con equipo, `subscription` con el alterno; `route` sigue
siendo la decidida, como hoy), `modelo` (el que contesto), `chat` (id) y `procedencia=1` (marca explicita:
sirve para contar e idempotencia). **La pregunta que se guarda es la LIMPIA** (`chat_msg`, sin el `/local`
de adelante; hoy va `user_msg` crudo y todos los episodios del home del smoke arrancan con "/local").
*(Rulings: `titulo` del chat, `modelo` duplicado en el documento y `rol_pregunta` quedan afuera por YAGNI;
no se guardan `pregunta`/`respuesta` separadas: el parser hace falta igual para lo viejo, asi que hay un
solo camino de lectura.)* Los episodios que no son de chat (metas, fichas del jefe) no cambian de forma.

**Cambia la presentacion al leer.** Una funcion pura, `memoria_procedencia.presentar(texto, meta) -> str`,
que produce lo que ve el modelo:

```
- Pedro dijo (2026-08-14): empece El nombre de la rosa, me esta encantando
  Calipso contesto (local, 2026-08-14): Buena eleccion. Anotado...
```

o, si la respuesta es un no-saber: `Calipso no tenia el dato entonces.` Fecha = `ts[:10]` (como la fuente
`chats`). Tope por tramo, en el mismo modulo: pregunta 200 chars, respuesta 400 chars, con `...` (hoy no hay
ningun tope y hay episodios de 5000 chars del orquestador; el 7b corre con 8192 tokens). La usan los dos
lectores: el recall del system (`_build_context` -> `context_sections(recalled=...)`, que hoy pega
`- (score) texto`: pasa a una vineta con las dos lineas, sin score) y `abismo/fuentes.memoria`. **`presentar`
se aplica ANTES del corte a `RECALL_MAX` / `RECALL_TOP`** (se pide n=8, se presenta, se saltan los vacios y
recien ahi se corta), para que un salto no achique el bloque. `Memory.recall` conserva su contrato
`{text, meta, score, scope}`; `reflect`/`recent()` no cambian.

**El parser es tolerante y vive en un solo lugar.** Lo viejo NO dice siempre "Pedro pregunto:": de junio a
agosto se guardo con acentos rotos (`Pedro preguntÃ³:` / `Pedro preguntÃƒÂ³:` y `Calipso respondiÃ³:`,
en los ambitos de PROYECTO por `scope="auto"`). `memoria_procedencia.partir(texto)` usa
`^Pedro pregunt\S*:\s*(.*?)\nCalipso respondi\S*:\s*(.*)\Z` (DOTALL); `presentar` y el reindex lo comparten.
Para lo viejo, la pregunta se limpia de los gestos iniciales (`/local ...`) al mostrarla, y la ruta sale de
`meta["ruta"]` si existe o de `meta["route"]` (la decidida; puede no ser la que contesto: se acepta, no hay
forma de recuperar la usada).

**Lo que no es un par de chat tambien lleva procedencia.** Las metas (`kind="goal"`, en el ambito de
proyecto) SI entran al recall: `presentar` las muestra como `Registro (goal, 2026-08-14): <texto>`; lo
mismo para cualquier episodio que no parsee como par (`Registro (<kind o episodio>, <fecha>): ...`). Nunca
el crudo sin etiqueta. El reindex los cuenta como "no chat" y no los toca.

**La clasificacion es determinista, pura y al leer:** `memoria_procedencia.clasificar(respuesta) ->
"dato" | "sin_dato"`, sobre la respuesta en minusculas y sin acentos. Dos familias de patrones *(ruling:
fuertes y debiles, para no degradar una respuesta con dato que termina pidiendo precision)*:
- **Fuertes** (degradan solos): "no tengo registro(s)", "no tengo (esa|esta|la|ninguna) informacion",
  "no tengo informacion", "no tengo (ese|el|ningun) dato", "no tengo acceso", "no me consta", "no
  recuerdo", "no encuentro (registro|informacion|nada)", "no puedo (acceder|confirmar|verificar|recordar)",
  "no esta (registrad|en mi memoria|en mi cronologia)", "no hay (registro|informacion) (de|sobre)".
- **Debiles** (degradan solo si NO hay una oracion afirmativa con contenido antes, o si van con un fuerte):
  "podrias (darme|proporcionar|recordarme|decirme)", "me podrias (recordar|decir|dar)", "puedes
  (darme|proporcionar|recordarme|decirme)", "necesito mas (contexto|detalles)", "dame mas detalles".
- **Regla de posicion** *(ruling; reemplaza la regla "respuesta larga > 400" que no se podia medir)*: un
  patron fuerte degrada si empieza dentro de los primeros 250 chars (medido: en 148 no-saber reales el
  patron arranca en la posicion 0 de mediana, p90 116, maximo 202); mas tarde, la respuesta ya tiene
  contenido y no se degrada.
- Respuesta que es solo una pregunta (termina en `?` y no tiene ninguna oracion afirmativa): `sin_dato`.
La lista vive en un solo lugar y se mide contra el banco (seccion 5); como corre al leer, afinarla no toca
el disco.

**Un solo caso de basura, y no achica el bloque:** una pregunta que es solo un gesto sin texto (`/algo`)
no se presenta (`presentar` devuelve `""`, el lector la salta antes del corte). *(Ruling: "respuesta vacia"
no puede existir por el guard de `remember`, y "una o dos letras" era un filtro que Pedro no pidio: fuera.)*
Los turnos "-q" quedan en disco y en el bloque si el recall los trae; la procedencia los muestra como lo
que son.

**El ranking no cambia** (el recall embebe el par entero). Que las palabras de Pedro pesen mas es un
refinamiento a medir despues.

## 3. El reindexado (acto de Pedro)

`calipso/memoria_reindex.py`, con `python -m calipso.memoria_reindex --vista` y `--aplicar`. Recorre cada
ambito (`global` y cada `projects/*/chroma` bajo `CALIPSO_HOME`), lee todos los documentos con sus
metadatos (`get(include=["documents", "metadatas"])`) y para cada episodio que parsea como par de chat
(`partir`), con `kind="chat"` o sin `kind`, escribe los metadatos nuevos con `collection.update(ids=...,
metadatas=...)` **sin tocar `documents`** (verificado en chromadb 1.5.9: conserva documento, id, embedding y
`count`; `update` MERGEA metadatos, un `None` BORRA la clave: el reindex arma `{**meta_actual, **nuevos}`
sin `None`). Lo que agrega a lo viejo: `procedencia=1` y `ruta` (= `route` decidida, unica disponible);
`chat` y `modelo` no se pueden recuperar (quedan ausentes). `--vista` imprime por ambito: episodios,
cuantos ya tienen `procedencia`, cuantos parsean como chat, **cuantos `kind="chat"` NO parsean** (esperado
0; si no, Pedro lo ve antes de aplicar), cuantos quedarian como `sin_dato` y cuantos como basura; no escribe
nada. Idempotente por el merge (la segunda corrida no cambia nada y lo dice). Exige que el server este
apagado: chequea `CALIPSO_PORT` (default 8000) y se niega si responde, salvo `--forzar`; *(ruling: dos
`PersistentClient` sobre el mismo directorio no corrompen nada, sondeado; el chequeo es por completitud
del recorrido, no por integridad, y el mensaje lo dice)*. Al terminar vuelve a contar y avisa si `count`
cambio durante la corrida. Un episodio con metadatos raros se salta y se cuenta, jamas se pisa.

## 4. Invariantes

1. **Nada se borra ni se reescribe en disco al leer.** La degradacion y el salto viven en `presentar`.
2. **Todo lo que el modelo ve de un episodio lleva procedencia:** quien lo dijo, cuando, y por que ruta si
   fue Calipso; lo que no es un par de chat lleva `Registro (<kind>, <fecha>)`. No existe mas el par crudo
   en ningun prompt.
3. **Un no-saber jamas se presenta como dato.** Se reemplaza por la frase fija; la respuesta cruda sigue en
   disco.
4. **La clasificacion es pura y determinista,** sin modelo, medida contra el banco; los patrones estan en un
   solo lugar.
5. **El reindexado conserva id, documento y cantidad;** solo agrega metadatos por merge; es idempotente y
   se niega con el server prendido (salvo `--forzar`).
6. **Lo viejo y lo nuevo se leen con la misma funcion** (`partir` + `presentar`).
7. **`Memory.recall`, `recent` y `reflect` no cambian de contrato.**

## 5. El porton y la verificacion

- **Fixture durable:** el home del smoke del abismo (`smoke_home` del scratchpad de la sesion: 16 episodios
  reales del 7b, 7 de ellos no-saber, 4 confabulaciones) se copia a `experimentos/fixtures/memoria_smoke_home/`
  (chroma + chats.json + core, sin token) y el porton lo RESTAURA desde ahi antes de cada condicion y de
  cada pasada (cada turno muta el home). *(Ruling: sin fixture durable el porton no era reproducible.)*
- **Banco de la clasificacion:** `experimentos/no_saber_banco.py`: respuestas COMPLETAS del 7b (los
  documentos del chroma y `chats.json` del fixture, mas las salidas de los JSONL de `experimentos/` que no
  toquen el corte de 400 chars), unas 40 etiquetadas a mano (`sin_dato` / `dato`), con los casos borde:
  confabulaciones ("Recuerdo que te conte sobre un libro de ciencia ficcion..." es `dato`: el no-saber es lo
  unico detectable sin modelo; la confabulacion la ataca la procedencia + la consulta), respuestas con dato
  que terminan en "necesitas mas detalles?" (`dato`), y el caso del catastro ("El proyecto X no esta en la
  lista..." es `dato`: informa algo). Piso: **0 falsos `sin_dato`** sobre respuestas con dato y **>= 90%** de
  los no-saber atrapados.
- **Porton en vivo (el que importa):** sobre el fixture restaurado, las 4 preguntas de memoria/chats del
  smoke, chat nuevo por turno, N=2, tres condiciones: `antes` (main), `A` (frase fija) y `B` *(ruling: variante
  escrita por si el 7b copia el eco: se omite el renglon de Calipso cuando es `sin_dato` y queda solo "Pedro
  dijo (fecha): ...")*. Cada turno se clasifica con UNA clase determinista: `dato` (la respuesta contiene la
  verdad sembrada: "nombre de la rosa" / "Mariana Quintero" / "120" u "octubre" / Mariana + libro),
  `sin_dato` (`clasificar()` lo dice), `confabula` (ni una ni otra); mas dos flags: `consulto` (evento
  `abismo` en el ws) y `eco` (la respuesta contiene "no tenia el dato"). Se espera que `sin_dato` caiga a
  cero y que `eco` sea cero; si A muestra eco y B no, se aterriza B (sigue siendo "decidir al leer").
- Unitarios: `clasificar` (banco), `partir` y `presentar` (nuevo, viejo con las dos variantes rotas, meta,
  basura, sin ruta, topes), el `remember` del chat con los metadatos nuevos (harness de `test_abismo_chat.py`,
  cuyo `MemoriaFalsa.remember` tiene que capturar `meta` y `scope`), `context_sections` y `_build_context`
  con la presentacion y el corte despues de presentar, `fuentes.memoria` con la presentacion bajo el techo
  del bloque, el reindexado sobre un home temporal (vista no escribe; aplicar conserva ids, documentos y
  cantidad y preserva las claves viejas; idempotente; cuenta los que no parsean; se niega con el puerto
  ocupado; `--forzar`).

## 6. Lo que NO hace

- No filtra al escribir (decision 1). No borra basura (decision 3: se reindexa, no se limpia).
- No cambia el embedding ni el ranking. No toca `reflect`, `recent`, el bibliotecario, el core ni la
  cronologia. No toca `chats.json`.
- No usa un modelo para clasificar. No detecta confabulaciones: eso lo hace la consulta al abismo con la
  fuente etiquetada, y es lo que el porton mide.
- No recupera `chat` ni `modelo` de lo viejo (no existen en los metadatos viejos).

## 7. Corte

Una rama `feat/memoria-procedencia`, 5 tasks: (1) `calipso/memoria_procedencia.py` (patrones, `clasificar`,
`partir`, `presentar`) + el fixture durable + el banco + tests; (2) el `remember` del chat con los metadatos
nuevos y la pregunta limpia (server) + test por harness; (3) los dos lectores usan `presentar` antes del
corte + tests; (4) `memoria_reindex` + tests; (5) el porton en vivo (antes / A / B), aterrizaje de A o B, smoke
y cierre.
