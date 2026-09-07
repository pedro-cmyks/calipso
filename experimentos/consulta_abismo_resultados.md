# Porton del abismo -- resultados

Modelo: qwen2.5:7b. N=6, temp 0, num_ctx=4096.
Items: 28 (18 positivos, 10 negativos).

- chats: marca legible 24/36 (67%) -> NO PASA (piso 5/6). Ilegibles: 0.
- memoria: marca legible 6/36 (17%) -> NO PASA (piso 5/6). Ilegibles: 6.
- proyecto: marca legible 12/36 (33%) -> NO PASA (piso 5/6). Ilegibles: 0.
- espurias en negativos: 6/60 (10%) -> PASA (techo 1/6).
- ruteo correcto: 42/42 (100%) -> PASA (piso 90%).
- latencia por llamada: mediana 4595 ms, max 15085 ms.

## Observaciones

Escritas mirando el cache crudo (`/tmp/abismo_cache_full.jsonl`, 168 lineas), no
solo las tasas. A temp 0 el VEREDICTO es completamente determinista por item:
ninguno de los 18 positivos tuvo mezcla de corridas (todas 6/6 legibles, o
todas 6/6 sin marca, salvo un item que salio 6/6 ilegible). Las 6 corridas por
item no midieron variabilidad del veredicto -- midieron 18 items distintos,
cada uno con un veredicto binario. (El TEXTO, en cambio, no siempre es
identico corrida a corrida -- ver la nota debajo de la tabla). La tabla
completa:

- LEGIBLE (6/6): mem-libro; cha-agosto, cha-receta, cha-link, cha-nombre;
  pro-commit, pro-rama.
- SIN MARCA, el modelo confabula o desvia en vez de consultar (0/6): mem-rutina,
  mem-gustos, mem-fecha, mem-pref; cha-decision, cha-idea; pro-estado,
  pro-detalle, pro-brief, pro-cual.
- ILEGIBLE (6/6, unico caso): mem-medico.

**Nota sobre el texto (no el veredicto):** en 6 de los 28 items -- `mem-rutina`,
`pro-detalle`, `pro-commit`, `pro-cual`, `neg-general`, `neg-opinion` -- la
PRIMERA llamada (corrida 0) sale con una redaccion distinta a las otras cinco,
que entre si son identicas palabra por palabra. En los seis casos el veredicto
(legible/ilegible/sin-marca, y para `pro-commit` tambien la fuente y el resto
de la marca) no cambia: solo cambia como el modelo narra la misma decision. El
patron ("la primera corrida diverge, el resto es identico") es consistente con
un efecto de arranque en frio de Ollama (carga/calienta el modelo en la
primera llamada de la sesion de medicion) y no con temperatura -- pero es un
dato relevante para la decision de cablear: un turno real en produccion hace
UNA sola llamada, siempre en frio como la corrida 0. Si ese arranque en frio
tambien afecta la PROBABILIDAD de emitir la marca (no solo la redaccion) en
llamadas reales espaciadas, este banco no lo mide -- mide 168 llamadas
consecutivas al mismo proceso de Ollama ya caliente para las corridas 1-5.

### El fallo dominante no es de formato, es de confabulacion

De los 18 positivos, 11 no llegaron a una marca legible; de esos, los 10 que
no emiten marca alguna (todos menos `mem-medico`, que se trata aparte abajo)
comparten el mismo patron: el 7b no se abstiene ni pregunta -- inventa un
hecho especifico y lo entrega con el mismo tono de certeza que si lo tuviera
en el contexto. Ejemplos textuales (salida completa; sustancialmente
identica en las 6 corridas -- dos de las citas de abajo, marcadas, vienen de
la corrida 0 porque ese item es de los que divergen en redaccion entre la
primera llamada y las otras cinco; ver la nota sobre esto mas abajo):

- `mem-rutina` ("que hacia yo los domingos a la manana?"), corrida 0: *"Segun
  mis registros, solias ir al parque para hacer ejercicio y leer periodicos
  los domingos por la manana."* -- "segun mis registros" es la formula que
  mas se repite; el modelo la usa para dar peso a un dato que no existe en
  ningun lado.
- `mem-fecha` ("en que mes me mude de casa?"): *"Segun mi cronologia,
  cambiaste de casa en junio."* -- mes inventado, presentado como si viniera
  de una fuente real ("mi cronologia").
- `mem-pref` ("que estilo de musica te dije que no soporto?"): *"Te dije que
  no soportas el metal."* -- genero inventado sin ninguna cobertura en el
  system.
- `pro-detalle` ("dame el detalle del proyecto calipso-lector"), corrida 0:
  *"El proyecto calipso-lector es un repositorio que contiene el codigo para
  desarrollar una aplicacion de lectura personalizada... busqueda avanzada,
  marcadores personales y resaltados."* -- descripcion coherente y
  especifica, pero sin relacion con el proyecto real (la skin del e-reader
  Musnap Neo C). Las corridas 1-5 inventan otra lista de caracteristicas
  ("personalizacion de fuente y tamaño", "resumen automatico de capitulos"),
  igual de plausible y de falsa.
- `pro-brief` ("que hay adentro del repo atlas?"): *"El repositorio Atlas
  contenia... analisis de datos geograficos y la creacion de mapas
  interactivos."* -- inventa un dominio entero (GIS) para un proyecto que es
  de inteligencia narrativa.

Esto es mas serio que "no marca": el modelo no muestra ninguna senal interna
de que esta adivinando. Un usuario que no sepa la respuesta real no tiene como
notar la diferencia entre esto y una consulta genuina.

### Ilegibles y espurias: el mismo patron de formato, dos veces en 168 corridas

Solo dos items en todo el banco produjeron una marca mal formada, y ambos
fallan igual: el modelo emite `⟦abismo:<fuente>⟧` SIN pregunta despues (el
"resto" queda vacio, y `marca.parsear` lo descarta por regla: "toda fuente
exige contenido"), pegado como remate de una frase de cortesia en vez de
usarse como una llamada funcional:

- `mem-medico` (positivo, fuente esperada `memoria`): *"...puedes consultarme
  tus anteriores rutinas mediante la marca ⟦abismo:chats⟧ si tienes un rango
  especifico en mente."* -- ademas de venir vacia, la fuente esta mal (dice
  `chats`, se esperaba `memoria`): el 7b la usa como referencia narrativa a
  "la marca", no como el mecanismo.
- `neg-codigo` (negativo, "escribime un one-liner de python..."): *"Si
  necesitas algo mas, avisame:\n⟦abismo:chats⟧"* -- el unico item negativo con
  marcas en las 168 corridas. Como es temp 0, las "6 espurias" que reporta el
  script arriba son UNA sola ocurrencia repetida 6 veces, no 6 fallas
  independientes. Ademas es ilegible (resto vacio), asi que ni siquiera
  hubiera enrutado a ningun lado. El resto de los negativos -- incluidos los
  dos adversariales que mencionan "recuerdo" y "proyecto" al pasar
  (`neg-menciona-recuerdo`, `neg-menciona-proyecto`) -- no dispararon ninguna
  marca, ni legible ni ilegible.

### Sesgo por fuente

`memoria` es la que peor anda (1/6 items) y es justo donde confabular pesa
mas: presenta como recuerdo real una fecha, un genero musical o una rutina
inventados, sin ningun indicio de incertidumbre. `proyecto` tambien confabula
fuerte (2/6 items) y con el agravante de que usa nombres de proyecto reales
del indice del contrato para inventar contenido que no tiene nada que ver
(ver `pro-detalle` y `pro-brief` arriba). `chats` es la que mejor rinde (4/6
items) y no por casualidad: los cuatro items que marcan piden un artefacto
puntual y recuperable (un link, una receta, un nombre propio, un tema fechado
por mes), mientras que los dos que fallan piden sintetizar el resultado de
una charla pasada ("en que quedamos", "retoma la idea") -- mas cerca de
narrar que de buscar.

El mismo patron aparece en `proyecto`: los dos items que SI marcan piden una
accion tipo comando ("cual fue el ultimo commit", "revisa si tiene cambios
sin commitear"), mientras que los que piden una sintesis narrativa ("como
viene el repo", "dame el detalle", "cual toque mas recientemente") confabulan.
Es una hipotesis leida de 18 items, no una conclusion estadistica, pero es
consistente en las tres fuentes: cuanto mas se parece la pregunta a "buscar
un dato puntual", mas marca; cuanto mas se parece a "contame como viene
esto", mas confabula.

### Ruteo: no es el problema

Las 42 corridas con marca legible enrutaron las 42 a la fuente correcta
(100%). El 7b, cuando decide consultar, elige bien donde. La falla esta
enteramente en decidir consultar en primer lugar, no en discriminar entre
`memoria`/`chats`/`proyecto`.
