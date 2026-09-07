# El abismo, rebanada 1 -- la consulta y las fuentes locales

**Fecha:** 2026-09-07
**Estado:** brainstorming cerrado con Pedro; corregido tras revision adversaria de cuatro lentes (citas, contradicciones, factibilidad, claridad); listo para su revision
**Origen:** sesion de brainstorming del 2026-09-07. Dossier de memoria: [[project_calipso_abismo]]. Precursor escrito: la observacion abierta del contexto selectivo en `docs/superpowers/2026-08-30-estado-y-que-sigue.md:140` ("falta el regimen del medio: que Calipso pueda pedir el detalle en vez de tenerlo todo encima") y la reserva explicita en `calipso/memory.py:218-220` ("enrutar de verdad... es trabajo del abismo, no de aca").

## 1. Por que existe

El contexto de Calipso tiene hoy dos regimenes y falta el del medio. Los briefs siempre-encendidos entran truncados a lo bruto (core a 3000 chars, economia a 2000, proyectos a 1200 -- `calipso/server.py:1842-1846`, `calipso/prompt_compiler.py:27-29,45-46`) y el recall automatico trae 4 recuerdos por turno con umbral fijo (`calipso/server.py:1985-1986`) -- push, no pull. Calipso sabe muchas cosas que no alcanza: el core entero, la cronologia completa, todo el historial de chats mas alla de los 12 mensajes de `_HISTORY_TURNS` (`calipso/server.py:2018`; `chats.json` guarda todo, `calipso/chats.py:11`), el detalle de cualquier repo (que hoy solo la UI puede pedir por `GET /api/catastro/{nombre}`, `calipso/server.py:1069-1079`).

La consulta al abismo es el regimen del medio: Calipso, a mitad de respuesta, se da cuenta de que necesita algo y lo pide. Pedro lo describio asi: "cuando Calipso le consulta al abismo es como cuando aca en Claude me sale ese asterisco con palabras como 'pondering'".

## 2. La cosmologia que cerro Pedro (2026-09-07)

Decisiones madre de la sesion. Las primeras cinco rigen mas alla de esta rebanada; el resto de este spec construye solo la rebanada 1.

1. **El corazon del abismo es la consulta.** Las otras dos caras (los datos de su casa, la escena del mapa) se construyen alrededor.
2. **Toda cara de Calipso podra consultar** (chat, jefes de la fabrica, el lector). El abismo es LA fuente de contexto del sistema. En esta rebanada solo se cablea el chat.
3. **La frontera es hibrida: anillos + juez.** Estructura determinista primero (profundidad por fuente y por consumidor), el juez local de privacidad despues, y solo sobre lo que los anillos dejan pasar. El mismo patron que gano en la Fase 2 del ruteo.
4. **El rol de dep:cerebro pasa al abismo y dep:cerebro muere.** `docs/superpowers/specs/2026-08-27-proyectos-y-plata-design.md:474,482-484` decidio un departamento nuevo dep:cerebro donde vive Calipso y donde vive la memoria centralizada; el padron cerrado de la siembra (`docs/superpowers/specs/2026-09-03-siembra-guiada-design.md:19`) no lo incluye y no hay camino de alta en produccion despues de la siembra (`Registro.alta` existe, `calipso/economia/departamentos.py:141`, pero su unico llamador es el sembrar de escritura unica). La decision no muere por imposibilidad tecnica: muere porque Pedro decide que ese rol ES el abismo -- sin billetera, sin jefe, otra capa del sistema.
   **Ripple resuelto:** proyectos-y-plata (seccion 9.3, `:768-770`) apoyaba sobre dep:cerebro el dueno-por-defecto de un chat sin edificio en foco. Ese rol NO puede pasar al abismo (no toca el libro). Queda lo que el codigo ya hace hoy: sin foco, la cuenta pagadora es la personal y el turno no se cobra (`calipso/mapa/ficha.py:24-52`, `calipso/server.py:6464-6465`). La decision 9.3 queda formalmente reemplazada por esta.
5. **La geografia:** la ciudad esta construida alrededor de la boca del abismo. Entrar es cambiar de escena (no un zoom). Lo mas hondo es lo mas delicado -- la profundidad ES la frontera. Y el universo entero esta en el abismo: la fabrica produce en la superficie con lo que sube de el.
6. **OneDrive es el fondo del abismo** (rebanada 2): local-primero, la nube como capa profunda cifrada del lado de la Ally antes de subir; indice local de lo hundido; la consulta pesca. Calipso deposita SU territorio y ademas indexa lo que ya vive en el drive de Pedro, con asignacion de anillos. La base viva (Chroma, JSONL, chats.json) NUNCA corre sobre un mount de nube.
7. **El corte en rebanadas, aprobado en este orden:** (1) la consulta y las fuentes locales -- este spec; (2) el fondo (OneDrive); (3) la escena del mapa; (4) los otros habitantes (jefes en su tic, el lector).

## 3. Que decidio Pedro para esta rebanada

- **Mecanismo: la marca in-band con reentrada** (enfoque A, elegido contra pre-pasada clasificadora y tool-calling nativo). Reusa el patron de `⟦foco:...⟧` para el filtrado in-band; la reentrada es construccion nueva sobre el bucle (seccion 4), no un reuso gratis de `pending`.
- **Continuar, no regenerar:** el texto ya visto queda; tras pescar, el modelo recibe lo que venia diciendo y sigue. Precedente conceptual: el steering.
- **Marca tipada por fuente** con gramatica cerrada (seccion 5). Ruteo determinista, medible y explicable (la leccion de la gramatica de proponer).
- **Fuentes del dia uno:** memoria profunda, historial viejo de chats, detalle de proyectos. (Pedro tambien eligio el fondo para el dia uno del abismo; por tamano va en la rebanada 2, primera en la cola.)
- **/nube -- la politica de Pedro:** consulta local siempre; Calipso decide por anillo que viaja (anillo 3 jamas, ni tapado; anillos 1-2 solo redactados por el juez). **El cableado de esa politica se ETAPA:** en esta rebanada la consulta NO corre en turnos /nube (seccion 8 explica por que: ensenarle la marca al modelo de nube exige mandarle el contrato, y eso se disena junto con la UI del ofrecimiento de la Fase 2b del ruteo, no de contrabando aca). La politica queda escrita como la regla que ese trabajo futuro implementa.
- **El pondering es visible:** senal WS con fuente y verbo corto, en las dos UIs y en el pulso del mapa.
- **Porton de medicion antes de cablear** (tercera vez del metodo: el mundo del jefe, el juez de privacidad), con corte explicito del trabajo en dos planes (seccion 12).
- **La consulta no toca la economia interna:** no mueve el libro ni cobra turnos extra (seccion 4 dice como). El consumo real extra de una reentrada en suscripcion existe y lo ve el probe pasivo de consumo; se declara, no se esconde.

## 4. Arquitectura

Paquete nuevo **`calipso/abismo/`**, hermano de `privacidad/` y `compositor/`: piezas puras probadas en aislado, cableado al final (y recien tras el porton de medicion).

- **`fuentes.py`** -- una funcion por fuente. Firma: cada fuente devuelve una **lista de sub-bloques** `(texto, anillo)`, porque una misma fuente puede pescar profundidades distintas (la memoria: episodica anillo 2, core/cronologia anillo 3). Techos: `ABISMO_BLOQUE_MAX = 2000` chars por consulta (constante global, override por env; provisorio).
- **`anillos.py`** -- la frontera: constantes de profundidad, el piso por fuente, `puede_viajar(anillo, destino)` y `puede_preguntar(anillo, consumidor)`, deterministas. El juez de `calipso/privacidad/` se aplica DESPUES y solo puede hundir un sub-bloque concreto (nunca subirlo). En esta rebanada `puede_viajar` es trivial (la consulta no corre en /nube) pero nace con la firma completa para las rebanadas 2 y 4.
- **`consulta.py`** -- el resolvedor: recibe la marca ya validada, rutea a la fuente, arma el bloque etiquetado (fuente, anillo, techo).
- **El filtro de la marca** -- hermano del `Filtro` de foco (`calipso/mapa/foco.py:30-78`), que ya resuelve marcas cortadas entre chunks. Cambios que este spec declara y foco no cubre:
  - El `Emisor` (`calipso/server.py:6299-6345`) hoy recibe UN filtro; pasa a componer una **lista ordenada de filtros** (foco primero, abismo despues).
  - Tope de la pregunta: **160 chars** dentro de la marca (contra el `MAX_NOMBRE = 60` de foco, `calipso/mapa/foco.py:19`); el costo declarado es que el filtro puede retener hasta `⟦abismo:` + 160 chars del stream visible mientras decide.
  - **Marca inconclusa al fin del stream: se retira con aviso, no se vuelca cruda** (divergencia deliberada del `cerrar()` de foco, que vuelca).
  - El bucle de streaming hoy solo mira el inbox entre chunks (`calipso/server.py:2752-2767`); se agrega el paso: **tras cada chunk, el bucle consulta el estado del filtro abismo y si hay marca valida cierra el generador**.

### La reentrada sintetica -- construccion nueva, no "pending gratis"

La revision adversaria demostro que consumir `pending` dispara el pipeline entero de un turno nuevo, con efectos que romperian las invariantes (re-parse de directivas sin `/nube`, `goals.detect` que puede secuestrar la continuacion, `chats.append` del mensaje sintetico como si fuera de Pedro, `mem.remember` fragmentado, `_cobrar_turno` de nuevo, `done` que cierra la burbuja). Por lo tanto la reentrada se define asi:

**Estado del turno** (vive junto al estado de conexion de `ws_chat`, atraviesa reentradas, y solo un paquete real de Pedro lo resetea): el mensaje original y sus `directives`/`route`/`verdict` ya decididos, el contador de consultas, los sub-bloques pescados acumulados, los tramos de parcial acumulados, y el flag de sinteticidad.

**La pasada sintetica saltea, por enumeracion:** `_decide` (hereda directivas y ruta del turno original, `calipso/server.py:1471,2462`), `goals.detect` (`:2435`), `chats.append("user", ...)` (`:2427`), `mem.remember` (`:2949-2954`), `chats.append("assistant", parcial)` intermedio (`:2958`), `_cobrar_turno`/costs/jobs de turno nuevo (`:2890-2892`), y el `done` (`:2979`) -- la burbuja de la UI se cierra con el UNICO `done` del final del turno.

**El prompt de la pasada sintetica:** el system del turno original (construido una vez, sin re-correr recall) + los sub-bloques pescados acumulados como append post-compile (el lugar canonico de los bloques por-necesidad, `calipso/server.py:2690-2708`) + el historial normal SIN el parcial + "venias diciendo: <concatenacion de los tramos>" + la instruccion de continuar. El parcial viaja por UNA sola via (el "venias diciendo"), nunca duplicado como mensaje assistant.

**Persistencia:** al final del turno se escribe UN solo par user/assistant: el mensaje real de Pedro y el texto visible fusionado (tramos + continuacion), ya filtrado. **La marca jamas se persiste** -- ni en `chats.json` (que la propia fuente `chats` pescaria despues) ni en el `output.txt` de jobs, que se limpia.

**Presupuesto de contexto:** hasta 3 consultas acumulan `3 x ABISMO_BLOQUE_MAX = 6000` chars + parcial; `num_ctx` se fija explicito en la llamada local (la leccion de la medicion del jefe: Ollama trunca desde el comienzo).

### El flujo, corregido

1. Calipso responde en streaming; emite `⟦abismo:chats agosto libro⟧`.
2. El filtro valida PRE-corte: sintaxis bien formada, fuente de la lista cerrada, tope no superado. **Solo una marca valida corta.** Una marca ilegible o de fuente desconocida se retira del texto con aviso y el stream sigue sin corte.
3. Marca valida: se retira, sale `{type:"abismo", fase:"pondering", fuente, verbo}`, el bucle cierra el generador.
4. `consulta.py` resuelve local. Fallos POST-corte (fuente rota, error interno): reentrada sin bloque, con aviso y fase `fallo`.
5. Los sub-bloques entran al estado del turno; la pasada sintetica corre como quedo definido arriba.
6. Sale `{type:"abismo", fase:"pescado", fuente, tamano}` y la continuacion streamea en la misma burbuja.

**Regla de las rutas.** Local y API streamean: el corte es en vivo. Suscripcion (CLI one-shot): el detector comparte gramatica con el filtro (una sola constante/regex); el preview de `{type:"process", partial}` (`calipso/server.py:2245-2254`) **se congela en la primera marca** (Pedro no lee texto que despues se descarta); el proceso corre a termino igual y la reentrada re-invoca el CLI completo -- **una consulta en suscripcion cuesta dos invocaciones reales**, se declara y el probe de consumo lo ve. La ruta orquestador (equipo dinamico) queda FUERA: las marcas que emitan agentes se retiran via `_limpiar_marcas` (que suma la marca abismo a la de foco, `calipso/server.py:6348-6353`) y se ignoran con aviso.

**Tope: 3 consultas por turno**, contador en el estado del turno. Bajo el tope: corte + pesca + reentrada. Alcanzado el tope: las marcas se retiran del texto y se ignoran con aviso, SIN corte -- el stream continua y el texto posterior vale (regimenes distintos, a proposito).

**Fallo cerrado en todo:** cualquier error degrada a "seguir sin contexto extra", nunca a romper el turno ni a fugar. Sin marca en el stream, el filtro es transparente byte a byte.

## 5. La gramatica de la marca y el contrato

Gramatica cerrada (regex unica compartida por filtro y detector one-shot):

```
⟦abismo:FUENTE RESTO⟧
FUENTE := memoria | chats | proyecto        (lista cerrada; token hasta el primer espacio)
RESTO  := memoria  -> pregunta libre (<= 160 chars)
          chats    -> palabras clave, con mini-sintaxis opcional desde:AAAA-MM hasta:AAAA-MM
          proyecto -> nombre (obligatorio) + pregunta opcional
```

Token que no matchea la lista (typo incluido): marca ilegible, se retira con aviso, sin corte. **No hay fallback "sin fuente cae a memoria"**: la gramatica cerrada es lo que el porton de medicion puede medir.

El contrato interno (`calipso/prompt_compiler.py:62-191`, unico lugar donde se ensenan marcas) suma la sintaxis y el **indice de lo consultable** -- la generalizacion del "preguntame por nombre" del catastro (`calipso/prompt_compiler.py:456-457`): un renglon por fuente diciendo que sabe contestar, techo total 600 chars. Esto cambia el system de TODOS los turnos (ver invariante 3, reformulada).

## 6. Los anillos

| Anillo | Nombre | Que vive ahi (piso por fuente) | Quien pregunta (futuro) | Viaje a la nube (politica) |
|---|---|---|---|---|
| 1 | La orilla | Detalle de proyectos/repos (catastro) | Toda cara | Redactado por el juez |
| 2 | Media agua | Historial de chats; memoria episodica (Chroma) | Chat; jefes con frontera (rebanada 4) | Redactado por el juez |
| 3 | Lo hondo | Core curado, cronologia completa, consolidado del libro personal, todo lo humano-sensible que el juez marque | Solo el chat | NUNCA, ni tapado |
| -- | Credencial | No es un anillo: es la clase que corta | Nadie | El envio ENTERO falla cerrado |

- **El piso es de la fuente; el juez solo hunde.** Un sub-bloque de chats (anillo 2) con salud adentro se hunde a 3.
- **Credencial mantiene la regla aprobada del ruteo** (`docs/superpowers/specs/2026-09-02-ruteo-vivo-y-privacidad-design.md:247-253`, "falla cerrado el prompt entero. Sin condicion"): una credencial detectada en material pescado que fuera a viajar hace fallar cerrado el envio entero, no se "hunde y sigue". En esta rebanada la regla no se ejercita (nada pescado viaja) pero queda declarada para las rebanadas que la ejerciten.
- **El consolidado del libro personal conserva su frontera de zona** (`docs/superpowers/specs/2026-08-27-proyectos-y-plata-design.md:508-511`): la fuente memoria solo lo devuelve a consultas nacidas en un chat de zona personal. La consulta del abismo no anula esa decision.
- En local, para Pedro, el resto esta disponible siempre: los anillos muerden cuando algo quiere salir de la maquina o cuando pregunta alguien que no es Pedro (rebanada 4).
- **Vida util del bloque pescado: efimera.** Vive en el estado del turno y muere con el turno; jamas se persiste en `chats.json` ni en memoria. Lo que Calipso cite en su texto VISIBLE es respuesta local que Pedro ya vio: entra al historial como cualquier texto y, si un turno futuro va a la nube, viaja bajo las reglas de la Fase 2 como todo el historial. La invariante 2 protege el bloque como tal, no cada frase que Calipso eligio decir en voz alta.

## 7. Las fuentes

- **`memoria`** -- recall dirigido sin los techos del turno: ambito elegible, `n=12`/top 8, umbral propio 0.20 (provisorios; el del turno es `RECALL_MIN_SCORE=0.30`, top 4), mas el core sin truncar y la cronologia entera como sub-bloques anillo 3. Requiere abrir `Memory.recall` a consultas por ambito -- hoy fusiona global+proyecto sin opcion (`calipso/memory.py:201-206`). Es el unico cambio real en `memory.py`. No construir Scopes nuevos por consulta (el `__init__` de Scope hace mkdir + cliente Chroma).
- **`chats`** -- busqueda lexica: palabras clave sobre `chats.json`, con la mini-sintaxis opcional `desde:`/`hasta:` de la gramatica (si no parsea, solo-palabras; sin interpretacion de lenguaje natural de fechas en v1 -- "agosto" es una palabra, no un rango). Devuelve fragmentos con titulo y fecha, anillo 2.
- **`proyecto`** -- el brief por nombre reusando la logica de `api_catastro_detalle` (`calipso/server.py:1069-1079`), sin mover `ROOT` ni tocar la memoria. Anillo 1.

## 8. /nube: por que la consulta no corre ahi (en esta rebanada)

En un turno /nube el system es `_SISTEMA_NUBE_MINIMO` a proposito (`calipso/server.py:1960-1966`, decision de la Fase 2a: los canales paralelos se cierran, el envio va sin recuerdos). Para que el modelo DE NUBE emita `⟦abismo:...⟧` habria que mandarle el contrato y el indice de lo consultable -- texto derivado de datos de Pedro (nombres de proyectos, que sabe cada fuente) viajando crudo en cada turno /nube. Eso es exactamente el patron de fuga que la Fase 2a cerro, y ademas perfora la compuerta binaria `a_la_nube_tapado` en sus cuatro sitios de append (`calipso/server.py:2703-2706,2718-2725,2796-2802,2845-2853`) y pierde el momento del "degradado avisado" que la Fase 2 prometio ("muestra que se tapo y que viajo, antes de mandar", `2026-09-02-ruteo-vivo-y-privacidad-design.md:268-272`).

**Decision de esta rebanada:** en turnos /nube la consulta esta apagada -- el contrato no viaja, el modelo de nube no sabe pescar, la respuesta de nube va con menos contexto (el costo que la Fase 2a ya acepto). **La politica de Pedro (anillos deciden que viaja redactado) queda declarada en la seccion 6 como la regla que implementara el trabajo que junte: el contrato minimo auditado que si puede viajar, la fusion del mapa del juez, la excepcion explicita a la compuerta en los cuatro sitios, y la version redactada real mostrada a Pedro (con la UI del ofrecimiento de la Fase 2b).** Ese trabajo es una extension futura con nombre, no un hueco.

## 9. La senal de pondering

`{type:"abismo"}` por el WS del chat, TRES fases con cierre garantizado: `pondering` (fuente + verbo corto: "buscando en tus chats..."), `pescado` (fuente + tamano del bloque) y `fallo` (la consulta no trajo nada; la UI nunca queda con un pondering colgado). "Queda aviso" en este spec significa: fila en `telemetry.jsonl` + la fase `fallo` de esta senal.

Rama minima en las dos UIs -- un renglon con fuente y tiempo transcurrido, el molde visual de `process running` con partial (`calipso/web/index.html:2296-2314`) -- porque hoy ambas descartan tipos desconocidos en silencio (`calipso/web/index.html:2255-2417`, `calipso/web/fabrica/chat.js:37-99`). El evento se publica ademas al pulso del mapa para la rebanada 3, tocando `EVENTOS` (`calipso/mapa/pulso.py:22`, `publicar` revienta con evento desconocido) y la whitelist `CONOCIDOS` del cliente (`calipso/web/fabrica/pulso.js:35-39`) en el mismo cambio.

## 10. Colision con el steering

La consulta y el steering comparten mecanica (cierre de generador + estado de conexion), y `pending` es un slot unico (`calipso/server.py:2381,2753-2762`). Regla de precedencia: **el steer de Pedro gana siempre.** Un steer que llega durante la pesca cancela la consulta (bloque descartado, fase `fallo`, aviso) y se procesa como hoy; un steer durante la reentrada sintetica idem (la reentrada se aborta, el steer es el proximo turno). La reentrada sintetica NO usa el slot `pending` (usa el estado del turno de la seccion 4), asi que no compite por el. Test de la carrera incluido en la seccion 15.

## 11. Casos borde (decididos aca, no por el implementador)

- **Marca abierta al fin del stream:** se retira lo retenido con aviso; jamas se vuelca cruda.
- **Que persiste `chats.json`:** el texto visible fusionado, ya filtrado. La marca no existe para la historia (y por lo tanto tampoco para la propia fuente `chats`).
- **Modos con pipeline propio:** la consulta v1 vive SOLO en el turno conversacional plano. `/redacta`, `/otra`, `/mia`, `/plan`, `/team` y la ruta orquestador quedan explicitamente afuera (sus pipelines ni ensenan el contrato ni enganchan el filtro... salvo el retiro de marcas del orquestador, seccion 4).
- **Turno /nube:** seccion 8 -- apagada, contrato no viaja.
- **Goals:** la pasada sintetica no pasa por `goals.detect`; un goal solo puede nacer de un mensaje real de Pedro.

## 12. El porton de medicion (antes de cablear) y el corte en dos planes

Banco de situaciones hechas a mano en `experimentos/` (el molde de `experimentos/juez_privacidad.py`): positivos donde la respuesta correcta EXIGE consultar (por fuente) y negativos donde consultar seria ruido. Con el contrato y el indice puestos, sobre el 7b local, `temp 0`, `num_ctx` fijado, **N=6 corridas** (recordando que temp 0 no es determinismo):

1. Marca bien formada cuando debe: **>= 5/6 por fuente en positivos**.
2. Abstenerse cuando no debe: **espurias <= 1/6 en negativos**.
3. Ruteo a la fuente correcta: **>= 90% de las marcas legibles**.

Umbrales provisorios: se pueden revisar AL ARMAR el banco, pero cualquier cambio queda escrito en el experimento con su razon.

**El trabajo se corta en DOS planes** (la medicion bifurca el diseno con una decision humana en el medio, asi que no es un solo plan de punta a punta):

- **Plan 1a:** el paquete `calipso/abismo/` completo y probado en aislado + el contrato/indice + el banco + el porton corrido. Entregable: los numeros para Pedro.
- **Plan 1b:** el cableado a `ws_chat` (filtro compuesto, estado del turno, reentrada sintetica, senal, UIs, pulso). Arranca solo despues de que Pedro vea los numeros. Si el 7b no pasa el piso, las salidas son refinar el indice o cablear la consulta solo en rutas grandes (suscripcion/API) -- decision de Pedro con los numeros en la mano, y el costo de suscripcion (dos invocaciones por consulta) sobre la mesa.

## 13. Invariantes

1. **El resolvedor de la consulta es 100% local siempre.** Y en esta rebanada, en turnos /nube ni corre (seccion 8).
2. **El bloque pescado jamas entra a un envio a la nube ni se persiste.** Es efimero al turno (seccion 6 define el alcance exacto: protege el bloque, no el texto visible que Pedro ya vio).
3. **Con el filtro puesto y sin marca en el stream, los bytes que salen del filtro son identicos a los que entraron**, y ningun otro punto del pipeline cambia su conducta. (El system prompt SI cambia para todos los turnos -- suma contrato e indice; la invariante es la transparencia del filtro, no "identico a main".)
4. **Fallo cerrado:** cualquier error de la consulta degrada a "seguir sin contexto extra", nunca a romper el turno ni a fugar. Toda senal de pondering tiene cierre (`pescado` o `fallo`).
5. **La consulta no toca la economia interna:** no mueve el libro, y la pasada sintetica no ejecuta `_cobrar_turno` ni escribe costs/jobs como turno nuevo. El consumo real extra en suscripcion existe, se declara, y lo mide el probe pasivo.
6. **El juez solo hunde, nunca sube.** Y la clase credencial conserva su regla del ruteo: corta el envio entero, no se hunde-y-sigue.
7. **La marca que no salio del filtro no actua.** Nada interpreta `⟦abismo:...⟧` fuera del camino filtro -> resolvedor (las de agentes del orquestador se retiran y se ignoran con aviso).
8. **Solo un mensaje real de Pedro resetea el estado del turno** (contador, bloques, tramos). El steer de Pedro gana siempre sobre la consulta.

## 14. Lo que NO hace (fuera de esta rebanada)

- El fondo de OneDrive (rebanada 2): subida cifrada, indice de lo hundido, pesca en el drive, ojos sobre lo existente.
- La escena del mapa (rebanada 3): la boca en el centro de la ciudad, el cambio de escena, el descenso por anillos.
- Jefes consultando en su tic y el lector (rebanada 4). NO se toca `ACCIONES` del plantel (`calipso/plantel/decision.py:12`): un verbo nuevo sin corte propio escribiria en el bus (`calipso/plantel/jefe.py:396-418`).
- La consulta en turnos /nube (seccion 8): extension futura con nombre, junto a la UI del ofrecimiento de la Fase 2b del ruteo.
- La pre-pasada clasificadora (`needs_abismo`): descartada como mecanismo principal; puede volver como precarga.
- Busqueda semantica sobre chats viejos e interpretacion de fechas en lenguaje natural (v1 es lexica + `desde:`/`hasta:`).
- Migracion de almacenes: la memoria global existente (`~/.calipso/global/`) YA es el abismo; no se muda nada.
- La cara de terminal (`calipso` como comando REPL): proyecto aparte, en cola despues del abismo.

## 15. Como se verifica que funciona

- Paquete probado en aislado: `CALIPSO_HOME` a tmp con `monkeypatch` (cuidando los modulos que congelan la variable al importar), sin tocar el home real.
- Tests de: la gramatica (incluidos typos y marca abierta al EOF), la transparencia del filtro (invariante 3 reformulada), el tope y sus dos regimenes, el fallo cerrado con cierre de senal, la carrera steering-vs-consulta, la no-persistencia de la marca, el salteo enumerado de la pasada sintetica (no user append, no goals, no remember, no cobro, no done intermedio), y la frontera de zona del consolidado personal.
- Suite completa de pytest + los tests de cliente con `node --test` antes de cada commit.
- El porton de medicion corrido y documentado ANTES del plan 1b.
- Smoke final en vivo con servidor desechable (home temporal, token conocido), el ritual del compositor y la siembra: una conversacion real donde Calipso consulta, el pondering se ve, y la respuesta continua en la misma burbuja.
- Review final de rama cazando fugas por los canales paralelos que ya mordieron en la Fase 2a (borrador de fondo, web research, vision, system con recall) mas los nuevos de este spec (output.txt de jobs, preview de suscripcion, historial).

## 16. Vocabulario y nombres

- **No usar "cerebro"**: tomado por `dispatch.py` (AGENTS.md), la seccion Direccion del spec de economia, y la decision anulada de dep:cerebro.
- **No llamar "capa" al abismo**: "capa" ya significa el pulso efimero del mapa (`docs/superpowers/specs/2026-08-25-mapa-rts-design.md:20`). La pila queda: **ciudad** (superficie alrededor de la boca), **pulso** (lo efimero encima), **abismo** (escena propia, hacia abajo).
- `docs/superpowers/` sigue fuera de la auditoria de `doclinks.py:18` (hueco ya anotado en `2026-08-27-lo-que-falta.md:508`); este spec no lo arregla.
