# La memoria con procedencia: lo que dijo Calipso es contexto, no evidencia (2026-09-11)

Spec de brainstorming con Pedro, 2026-09-11 (madrugada), a partir del hallazgo h06 del smoke del abismo
(`docs/superpowers/2026-09-10-smoke-abismo-system-podado.md`). Todo archivo:linea es de main `9b3168c`
(rama `feat/aduana` no toca la memoria).

## 1. De donde sale

El smoke del system podado mostro que la fuente `memoria` del abismo, y los "Recuerdos relevantes" del
system de cada turno, le devuelven al 7b SUS PROPIAS RESPUESTAS anteriores como recuerdos: cada turno se
guarda como un episodio `"Pedro pregunto: <msg>\nCalipso respondio: <full>"` (`server.py:4237-4241`,
`scope="global"`, `route`, `kind="chat"`) y el recall trae el par entero, sin decir quien dijo que
(`memory.py:120-130`; `prompt_compiler.py:222-228`; `abismo/fuentes.py:110-118`). Con la consulta hecha, el
7b recibio "Calipso respondio: No tengo registros de quien te presto..." y lo repitio; en otro turno
construyo una confabulacion sobre su propia respuesta previa. Cuanto mas falla, mas fallos recuerda.

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

- **Cambia el metadato del episodio, no su texto.** `remember` sigue guardando el par como documento (asi el
  embedding y el id por hash de contenido no cambian) y suma metadatos: `rol_pregunta="pedro"`, `pregunta`,
  `respuesta` (los dos tramos por separado, para no parsear texto al leer), `ruta`, `modelo`, `chat`,
  `titulo` del chat, `ts` (ya estaba), `kind="chat"` (ya estaba). Los episodios que no son de chat (metas,
  fichas ilegibles del jefe) no cambian.
- **Cambia la presentacion al leer.** Una funcion pura, `memoria_procedencia.presentar(episodio) -> str`,
  que a partir del documento y sus metadatos produce el texto que ve el modelo:
  `Pedro dijo (14 ago 2026, chat "Libros de agosto"): empece El nombre de la rosa` y
  `Calipso contesto (local, 14 ago 2026): Buena eleccion. Anotado...` o, si la respuesta es un no-saber,
  `Calipso no tenia el dato entonces.` La usan los dos lectores: el recall del system (`_build_context` ->
  `context_sections(recalled=...)`) y `abismo/fuentes.memoria`.
- **La clasificacion es determinista, pura y al leer:** `memoria_procedencia.clasificar(respuesta) ->
  "dato" | "sin_dato"`. Patrones (minusculas, sin acentos, como todo el repo): "no tengo registro(s)",
  "no tengo (esa|esta|la) informacion", "no tengo (ese|el) dato", "no tengo informacion", "no me consta",
  "no encuentro", "no puedo acceder", "no tengo acceso", "podrias (darme|proporcionar|recordarme|decirme)",
  "necesito mas (contexto|detalles)", "dame mas detalles"; ademas: respuesta vacia; respuesta que es solo
  una pregunta (termina en `?` y no tiene ninguna oracion afirmativa). Un patron que aparece en una
  respuesta LARGA con datos (mas de 400 chars y el patron despues del primer tercio) no la degrada: el
  no-saber es la respuesta, no una frase dentro de una respuesta con contenido. La lista vive en un solo
  lugar y se mide contra un banco (seccion 5); como corre al leer, afinarla no toca el disco.
- **Los episodios basura no entran al bloque** (siguen en disco): pregunta de una o dos letras, o que es
  solo un gesto (`/algo` sin texto), o respuesta vacia. `presentar` devuelve `""` y el lector los salta.
- **Lo viejo se lee igual:** para un episodio sin los metadatos nuevos, `presentar` parsea el formato
  `Pedro pregunto: ...\nCalipso respondio: ...` (y `Pedro pregunto:` a secas) y aplica las mismas reglas; la
  ruta sale de `meta["route"]`. Asi el cambio funciona el dia uno sin reindexar, y el reindexado solo
  completa metadatos.
- **El ranking no cambia** (el recall embebe el par entero, como hoy). Que las palabras de Pedro pesen mas
  es un refinamiento a medir despues.
- **`reflect` no cambia** (manda `recent()` como hoy; recibe los episodios crudos, un modelo grande sabe
  leer "Calipso respondio").

## 3. El reindexado (acto de Pedro)

`experimentos/../` no: es codigo del producto, `calipso/memoria_reindex.py`, con `python -m
calipso.memoria_reindex --vista` y `--aplicar`. Recorre cada ambito (`global` y cada proyecto bajo
`CALIPSO_HOME/projects/*/chroma`), lee todos los documentos con sus metadatos, y para cada episodio
`kind="chat"` (o sin `kind` pero con el formato `Pedro pregunto:`) calcula los metadatos nuevos y los
escribe con `collection.update(ids=..., metadatas=...)` **sin tocar `documents`** (el id y el embedding
quedan). `--vista` imprime por ambito: episodios, cuantos ya tienen procedencia, cuantos quedarian como
`sin_dato` y cuantos como basura, y no escribe nada. Idempotente: correrlo dos veces no cambia nada la
segunda. Exige que el server este apagado (chequea el puerto 8000 y se niega si responde) porque Chroma es
un solo escritor por directorio. Un episodio con metadatos raros se salta y se cuenta, jamas se pisa.

## 4. Invariantes

1. **Nada se borra ni se reescribe en disco al leer.** La degradacion y el salto de basura viven en
   `presentar`, no en Chroma.
2. **Todo lo que el modelo ve de un episodio lleva procedencia:** quien lo dijo, cuando, y por que ruta si
   fue Calipso. No existe mas el par crudo en ningun prompt.
3. **Un no-saber jamas se presenta como dato.** Se reemplaza por la frase fija; la respuesta cruda sigue en
   disco.
4. **La clasificacion es pura y determinista,** sin modelo, medida contra el banco; la lista de patrones esta
   en un solo lugar.
5. **El reindexado conserva id, documento y cantidad;** solo agrega metadatos; es idempotente y se niega con
   el server prendido.
6. **Lo viejo y lo nuevo se leen con la misma funcion.**

## 5. El porton y la verificacion

- **Banco de la clasificacion:** `experimentos/no_saber_banco.py` con respuestas REALES del 7b tomadas de
  los JSONL de los smokes y las mediciones de hoy (`experimentos/consulta_abismo_system_*.jsonl`, el
  scratchpad del smoke): unas 40 respuestas etiquetadas a mano (`sin_dato` / `dato`), incluidas las
  confabulaciones ("Recuerdo que te conte sobre un libro de ciencia ficcion...": es `dato` para el
  clasificador, porque el no-saber es lo unico que se puede detectar sin modelo; la confabulacion la ataca
  la procedencia + la consulta al abismo, no este filtro). Piso: 0 falsos `sin_dato` sobre respuestas con
  dato (nunca degradar un dato real) y >= 90% de los no-saber atrapados.
- **Porton en vivo (el que importa):** sobre el home del smoke del abismo de hoy (ya contaminado con
  episodios "no tengo registros"), las mismas 4 preguntas de memoria/chats antes y despues del cambio, con
  chat nuevo por turno, N=2: contar cuantas veces el 7b repite el no-saber viejo, cuantas consulta al
  abismo, cuantas contesta con el dato. Se espera que "repite el no-saber" caiga a cero.
- Unitarios: `clasificar` (banco), `presentar` (nuevo, viejo, basura, sin ruta), `remember` del chat con los
  metadatos nuevos (server, por el harness de `test_abismo_chat.py`), `context_sections` con la
  presentacion, `fuentes.memoria` con la presentacion, el reindexado sobre un home temporal (vista no
  escribe; aplicar conserva ids y cantidad; idempotente; se niega con el puerto 8000 ocupado).

## 6. Lo que NO hace

- No filtra al escribir (decision 1). No borra basura (decision 3: se reindexa, no se limpia).
- No cambia el embedding ni el ranking. No toca `reflect`, el bibliotecario, el core ni la cronologia.
- No usa un modelo para clasificar. No intenta detectar confabulaciones: eso lo hace la consulta al abismo con
  la fuente etiquetada, y es lo que el porton mide.
- No toca `chats.json` (la conversacion visible sigue igual).

## 7. Corte

Una rama `feat/memoria-procedencia`, ~5 tasks: (1) `calipso/memoria_procedencia.py` (clasificar, presentar)
+ banco + tests; (2) `remember` del chat con metadatos (server) + test por harness; (3) los dos lectores
(`_build_context`/`context_sections` y `fuentes.memoria`) usan `presentar` + tests; (4) `memoria_reindex`
+ tests; (5) porton en vivo + smoke + cierre. Corre despues del merge de la aduana.
