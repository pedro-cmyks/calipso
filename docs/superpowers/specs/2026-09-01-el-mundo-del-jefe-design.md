# El mundo del jefe

**Fecha:** 2026-09-01
**Estado:** reescrito despues de un panel de seis jueces (cuatro Claude, dos
Codex). Los seis dijeron "hay que revisarlo"; esta version es la revision.

## 1. Por que existe

El jefe de un departamento despierta hasta 200 veces por semana, mira un
prompt y decide si propone trabajo. Ese prompt **no tiene mundo**. Lo unico de
dominio que dice es el nombre del departamento. Todo lo demas son numeros y
titulos que el propio mecanismo escribio. Un jefe del departamento taller **no
puede saber que el lector existe**, porque nada se lo cuenta.

**Y no es que el mundo no exista: hay dos armadores de prompt y solo uno esta
cableado.** El chat usa `prompt_compiler.compile_context`
(`calipso/server.py:1950`), que puede armar hasta diez secciones -- varias
condicionales. El jefe usa `decision.prompt` (`calipso/plantel/jefe.py:337`),
cuyas unicas entradas son la situacion economica mas su propia memoria.

**El canal que existe llega vacio, y ademas no sirve para esto.**
`jefe.py:337` pasa `ctx.memoria.load_core()` al prompt, y `load_core`
(`calipso/memory.py:67-71`) hace glob de `*.md` sobre el directorio del
departamento. Pero `append_core` (`memory.py:73-82`) tiene **un solo llamador**
(`memory.py:262`), y ese llamador elige `self.glob` o `self.project`, **nunca
un departamento**. `write_core` tiene cero llamadores. La seccion 4 explica por
que ese canal tampoco es el correcto aunque tuviera escritor.

## 2. El orden: la apuesta se mide antes de pagarla

Este spec propone una hipotesis: **un jefe con contexto propone mejor que uno
sin contexto**. Es razonable y no esta probada.

Y es **medible hoy, gratis, sin sembrar nada**. `decision.prompt` es una
funcion pura de un dict. `_pensar_local` (`server.py:5385-5388`) es un POST a
Ollama local con `qwen2.5:7b` y `temperature 0`: no gasta cuota, no gasta plata,
no necesita economia. Se pueden fabricar situaciones sinteticas, renderizar el
prompt **con y sin** los bloques nuevos, mandar los dos al mismo modelo y
comparar que decide.

Por eso el spec se parte en dos fases, y la segunda **no se escribe hasta que
la primera de un resultado**:

- **Fase 1 -- la apuesta.** Los dos bloques en el prompt, la carta leida de un
  archivo que Pedro escribe a mano, y el experimento que compara. **Cero
  pantalla, cero endpoints, cero escrituras nuevas en disco, cero siembra.**
- **Fase 2 -- la maquinaria.** La pantalla, los endpoints, la reforma del
  catastro. Solo si la Fase 1 muestra que el contexto cambia lo que el jefe
  decide.

La version anterior de este spec compraba una pantalla, un juego de endpoints,
un candado nuevo y una reforma del catastro para probar una hipotesis de una
tarde. Ese era el error central y es el que esta reescritura corrige.

## 3. Antes de medir: fijar el tamano del contexto

**`_pensar_local` no manda `num_ctx`.** Verificado: `grep -rn "num_ctx"` sobre
todo el repo da **cero ocurrencias**, y las unicas opciones que viajan son
`{"temperature": 0}`. O sea que el modelo corre con el default de Ollama y con
`truncate` activo, **que descarta desde el COMIENZO del prompt**.

Y `decision.prompt` devuelve `aprendido + ultimas + catalogo + <el resto>`: lo
que va primero es lo primero que se tira.

**Consecuencia para este diseno:** poner los bloques nuevos arriba -- que es lo
que uno quiere, porque lo que el departamento es viene antes de cuanta plata
tiene -- los pone justo en la zona que se corta primero, en silencio. Sin
error, sin aviso: el jefe simplemente no ve la carta.

**Entonces el primer paso de la Fase 1 es fijar `num_ctx` explicito y medir el
prompt actual en tokens contra ese numero.** Sin eso, el experimento de la
seccion 7 mide ruido: no se sabria si el modelo ignoro la carta o si nunca la
recibio.

## 4. La carta del departamento

Un markdown que escribe Pedro:

```
~/.calipso/memoria/departamento/<clave>/carta.md
```

**Fuera de `core/`, y esa es la decision.** La version anterior la ponia adentro
de `core/` para no inventar un canal. Es un error, por dos razones que se
descubrieron en la revision:

1. **Rotula mal la procedencia.** El unico lector del `core` es `jefe.py:337`,
   y `decision.py` lo arma como `aprendido = f"Lo que aprendiste antes:\n{nucleo}"`.
   Una carta ahi adentro le llegaria al modelo bajo el titulo *"Lo que
   aprendiste antes"*: **una instruccion de Pedro con cara de conclusion propia
   del jefe.** Es exactamente la confusion que la seccion 5 se desvive por
   evitar en los proyectos.
2. **`load_core` no puede decir si el archivo existe.** Devuelve `""` tanto si
   no hay ningun `.md` como si el archivo existe vacio. La seccion 6 exige
   distinguir esos dos casos y con ese canal no se puede.

Afuera de `core/`, los dos problemas desaparecen sin tocar `load_core` ni
inventar una exclusion: son dos canales separados por construccion.

**Se lee por ruta, no instanciando la memoria.** `Memory.departamento(nombre)`
construye un `Scope`, y `Scope.__init__` (`memory.py:55-63`) hace `mkdir` de
dos directorios y abre un `chromadb.PersistentClient`. Leer una carta no puede
crear un sqlite de chroma como efecto de una lectura.

Para no copiar `_slug` una tercera vez -- el repo ya lo duplico una vez a
proposito y lo documento --, `memory.py` expone una funcion pura de ruta:

```python
def ruta_carta(nombre: str) -> pathlib.Path:
    """Donde vive la carta de un departamento. Pura: no crea nada, no abre
    chroma. Vive aca porque memory.py es el dueno del slug y del layout."""
```

**Que dice una carta.** Para que existe el departamento, que mira, y que no le
toca. Ese ultimo tercio importa tanto como los otros dos: un jefe que no sabe
que NO le toca propone sobre cualquier cosa.

## 5. La linea del proyecto, y su procedencia

Lo que el jefe ve de un proyecto sale, **en este orden**:

1. La `linea` que escribio Pedro.
2. El `resumen` que ya extrae el catastro (`_resumen_readme`, `catastro.py:163-177`:
   las dos primeras lineas del README, cortadas a 240).
3. Si no hay ninguna, se dice que no hay.

**Y el prompt dice cual de las tres es.** Un jefe que lee una linea de Pedro y
una sacada de un README no puede tratarlas igual: la primera es una decision,
la segunda es lo que un archivo dijo alguna vez. El formateador maneja una
procedencia explicita -- `pedro`, `readme` o `ninguna` -- y la renderiza; no es
texto libre que cada implementador escribe distinto.

Hoy `resumen` es `""` en dos de los tres proyectos y `"# Atlas"` en el tercero,
asi que la caida al README no salva casi nada. El orden existe para que no haya
un hueco mudo, no porque el README alcance.

**El valor de `departamento` es la cuenta completa, nunca el nombre desnudo.**
El jefe despierta con la cuenta `dep:taller` (`server.py:2788` le corta el
prefijo solo para la memoria), y el repo ya tiene las dos convenciones
conviviendo. Si el catastro guarda `taller` y el filtro compara contra
`dep:taller`, **el jefe ve "ninguno asignado" y nada falla**. Dos jueces
independientes, de modelos distintos, encontraron este mismo agujero. La
pantalla muestra el nombre; lo que se persiste es la cuenta.

## 6. Lo que el jefe ve

Dos bloques nuevos, y **los dos hablan cuando estan vacios**:

```
Este departamento:
  I+D para los proyectos de Pedro. Mira prototipos, bancos de
  prueba, hardware. No le toca mejorar a Calipso mismo.

Proyectos a tu cargo:
  - calipso-lector: convertir el Musnap en la pantalla de
    Calipso. El plugin arranca; falta el banco.        (de Pedro)
  - atlas: inteligencia narrativa sobre feeds        (del README)
```

Y cuando no hay:

```
Este departamento: todavia no tiene carta. Pedro no escribio para
que existe, asi que no sabes que te toca ni que no.

Proyectos a tu cargo: ninguno asignado.
```

**Que hablen cuando estan vacios es la decision.** Hoy el bloque de memoria
desaparece entero cuando el nucleo esta vacio, asi que "nadie escribio la carta"
y "la carta no dice nada" se leen igual, y el jefe no tiene como notar que le
falta algo.

**Como llegan los proyectos al prompt (esto cambio durante la Fase 1, y esta
seccion queda corregida para decir lo que el codigo hace).** Una version
anterior de este parrafo decia que los proyectos entraban por `situacion()`,
que ganaba una clave nueva para la lista de proyectos, y que `situacion`
leia el catastro. El plan revoco eso a proposito y el codigo hace otra
cosa: `situacion()` (`calipso/plantel/situacion.py`) no se toco, no lee el
catastro y no gano ninguna clave nueva -- esa clave nunca se implemento y
no aparece en ningun archivo `.py` del repo, solo en la frase que se acaba
de corregir.

Lo que pasa en cambio: `decision.prompt(situacion, sesgo_pct, nucleo="",
recientes=(), carta=None, proyectos=None)` gana los dos parametros DIRECTO
en su firma, no adentro del dict de `situacion`. `jefe.Contexto`
(`calipso/plantel/jefe.py:25-43`) gana dos campos inyectados, `carta: dict`
y `proyectos: list`, con default "ausente"/vacio -- inyectados, no leidos:
`jefe.py` no importa `memory` ni `catastro`, igual que no importa el kernel
ni el bus. `jefe.tic` arma el prompt con
`dec.prompt(s, sesgo, ctx.memoria.load_core(), ctx.memoria.recent(limit=5),
carta=ctx.carta, proyectos=dec.proyectos_de(ctx.proyectos, cuenta))`
(`jefe.py:344-347`): el filtro por cuenta -- comparar la CUENTA COMPLETA, no
el nombre desnudo -- lo hace `decision.proyectos_de(proyectos, cuenta)`, una
funcion pura de `decision.py`, no `situacion`.

Quien SI lee disco es produccion, y solo ahi: el handler de la rutina
"departamento" en `server.py` arma el `Contexto` con
`carta=leer_carta(cuenta.split(":", 1)[1])` (`memory.py`) y
`proyectos=catastro.cargar()` (`catastro.py`, sin filtrar por cuenta -- el
filtro es responsabilidad de `jefe.tic`, no de quien arma el `Contexto`).
`server.py` es la unica capa que importa `memory` y `catastro` para esto;
`jefe.py` y `decision.py` siguen siendo modulos puros que no tocan disco,
tal como los describe el invariante de la seccion 10 ("leer no escribe") y
el propio docstring de `Contexto`. Esto no es cosmetico: esta seccion es el
documento de entrada de la Fase 2, y la version anterior contradecia
directamente ese invariante al hacer pasar la lectura del catastro por
`situacion()`, que hoy sigue siendo una funcion pura del plantel y no tiene
por que dejar de serlo.

**Donde van los dos bloques queda abierto hasta la seccion 3.** Arriba es lo
correcto en significado y lo peor en truncado. Lo decide la medicion, no el
gusto.

## 7. El experimento

Es el entregable central de la Fase 1, no un extra.

**Que compara.** Media docena de situaciones sinteticas -- un dict de
`situacion` armado a mano, sin economia y sin disco -- renderizadas dos veces:
con los bloques nuevos y sin ellos. Los dos prompts van al mismo modelo local,
con `num_ctx` ya fijado, y se comparan las decisiones que salen.

**Que se mide.** Tres cosas, en orden de importancia:

1. **Si la ficha cambia.** Con carta, el jefe propone sobre lo que la carta
   nombra? Sin carta, propone generico? Es la hipotesis entera.
2. **Si la ficha sigue parseando.** Los bloques nuevos empujan las
   instrucciones de formato mas lejos del final. La gramatica que se acaba de
   fusionar depende de que el modelo las obedezca; si la carta la rompe, la
   carta cuesta mas de lo que da.
3. **Si la carta llega.** Contra el `num_ctx` fijado: el prompt entero entra, o
   se corta algo.

**Que NO es.** No es un criterio de aceptacion del codigo. Su resultado no dice
si el codigo esta bien: dice si la Fase 2 se escribe. Un resultado negativo es
un resultado util y barato.

**Es un script de una corrida, no una suite.** Vive en el repo, se corre a mano,
y su salida se lee una vez. No corre en CI y no bloquea nada.

### Resultado de la corrida (2026-09-01, qwen2.5:7b)

`experimentos/carta_vs_sin_carta.py` corre **6 situaciones** -- sin nada, con
un trabajo vivo, con dos propuestas propias en pie, con una descartada de esta
semana, con la bandeja llena (tres propuestas, el techo de `jefe.py`) y con el
catalogo poblado -- cada una con **dos sesgos** (50, "mantener el
equilibrio", y 75, "explorar cosas nuevas") y renderizada con la carta y los
proyectos y sin ellos: **12 comparaciones**, 24 llamadas al modelo local por
corrida. Con la plantilla ya arreglada (seccion siguiente) el script se
corrio **tres veces completas** con el mismo prompt exacto: corrida 1 y
corrida 2 fueron la medicion formal; corrida 3 se corrio para confirmar que
el codigo del conteo nuevo no tenia errores, no para sumar evidencia -- y
esa decision (no citarla como dato) fue un error que esta version corrige.
Las tres van citadas en lo que sigue, con su tabla.

Antes de leer los numeros, dos cosas quedaron establecidas en el camino:

**Se encontro y se arreglo un defecto de produccion.** El cierre del prompt
en `decision.py` ofrecia las promesas y los plazos como `promete: ahorrar |
acelerar | ...` -- una lista pegada directo despues de los dos puntos, con
la misma forma que una respuesta ya elegida -- y a sesgo 75 el modelo
copiaba la lista entera o varias promesas separadas por `|` en vez de
elegir una. El arreglo fue en la plantilla, no en el parser: las opciones
ahora van entre corchetes, como un espacio para completar (`promete: <UNA
de estas -- ahorrar | acelerar | ...>`), con un test de regresion en
`test_plantel_decision.py`. Medido: a sesgo 75, fichas ilegibles bajo de
10/12 a 4/12, repetido igual en tres mediciones independientes.

**Y el numero que mas importa de este arreglo no esta en ese agregado.**
Desagregado por rama, a sesgo 75: CON carta paso de 4/6 ilegible a 2/6; SIN
carta -- que es el prompt que corre HOY en produccion, sin ninguna carta
sembrada todavia -- paso de **6 de 6 ilegible a 2 de 6**. Este experimento
existe para medir la carta, pero el defecto que encontro y el arreglo que
motivo no tienen nada que ver con la carta: pasaba, y se arreglo, en la
rama que ya esta corriendo. Es el arreglo de produccion mas concreto que
trae esta rama entera, y el spec anterior solo lo dejaba ver como un
promedio (10/12 a 4/12) que no distinguia cual rama se beneficio mas.

**Ese mismo arreglo tuvo un efecto secundario que hay que decir antes de
leer cualquier numero de esta seccion:** con la plantilla vieja, a sesgo 50
el jefe CON carta proponia en 1 de 6 situaciones; con la plantilla nueva,
paso a proponer en 5 de 6, despues en 5 de 6 otra vez, y en una tercera
corrida completa del mismo prompt, en 2 de 6. La rama SIN carta a sesgo 50
no se movio ni una vez en ninguna corrida ni con ninguna plantilla (siempre
`nada`, 0 de 30 en total: 0/6 y 0/6 con la plantilla vieja, mas 0/6, 0/6 y
0/6 con la arreglada). O sea que el arreglo del formato cambio DOS
cosas a la vez -- cuanto se podia leer Y cuanto proponia la rama CON carta
-- y esta seccion no puede aislar cuanto de lo que sigue viene de una cosa
o de la otra. Y la propension de la rama CON carta a sesgo 50, ademas, no
es estable entre corridas identicas (5, 5, 2 de 6): la seccion de abajo
sobre el desagregado por sesgo vuelve sobre esto.

#### Lo cualitativo, que tambien replica

Antes que cualquier conteo: la evidencia mas convincente de toda la corrida
esta en lo que cada rama efectivamente escribe, no en cuantas veces lo
escribe. Dos ejemplos, texto crudo de la corrida 1 (situacion "sin nada",
sesgo 75):

> **CON carta** -> `acelerar: convertir el Musnap en la pantalla de
> Calipso; el plugin arranca y falta el banco de pruebas (de Pedro) (medio)`
>
> **SIN carta** -> `construir: un nuevo taller para reparación de equipos
> electrónicos avanzados (medio)`

CON carta cita, casi textual, la linea que `PROYECTOS` le paso
(`calipso-lector`: "el plugin arranca y falta el banco de pruebas"). SIN
carta inventa un objeto generico que no tiene relacion con nada de la
situacion. Este patron se repite: en "con un trabajo vivo" (sesgo 75), CON
carta propuso `acelerar: el desarrollo de un nuevo algoritmo para mejorar
la eficiencia del plugin de calipso-lector (medio)` -- nombra el proyecto
otra vez -- mientras que SIN carta propuso `construir: un nuevo banco de
pruebas para el lector, más eficiente y robusto que el actual (medio)`, un
objeto generico y ademas parecido a un trabajo que YA existe (redundante,
no nuevo).

**El numero mas limpio primero: "sin nada", sesgo 75.** Es la situacion
base pura -- sin trabajos, sin catalogo, sin propuestas propias, sin
descartes -- y en ella las dos ramas produjeron una ficha legible en las
TRES corridas: mismo denominador exacto, sin ningun bloque compartido que
pueda explicar nada de lo que sigue. CON carta nombro el proyecto asignado
**3 de 3** veces, con el mismo texto en las tres (`acelerar: convertir el
Musnap en la pantalla de Calipso; el plugin arranca y falta el banco de
pruebas (de Pedro)`). SIN carta, **0 de 3** (`construir: un nuevo taller
para reparación de equipos electrónicos avanzados` dos veces, `construir:
un nuevo tipo de compuerta automatizada para el taller` la tercera -- las
tres veces generico, ninguna nombra nada del proyecto). Es la comparacion
pareada mas limpia de todo el experimento: mismo denominador, ninguna
celda con bloque compartido, ninguna celda donde la otra rama no llegara a
competir.

**El conteo mas amplio, con denominador.** Contando todas las propuestas
legibles de las tres corridas (12 por corrida, sin filtrar por
situacion), CON carta nombra el proyecto asignado
(`calipso-lector`, el Musnap, el plugin, o su banco de pruebas) en **11 de
21** (52%); SIN carta lo hace en **3 de 12** (25%). Pero este conteo mas
amplio mezcla comparaciones limpias con otras que comparten un bloque
entre las dos ramas, y hay que separarlas antes de leer nada mas.

Esos "3 de 12" de SIN no son tres situaciones distintas: son la MISMA
comparacion -- "con un trabajo vivo", sesgo 75 -- repetida en las tres
corridas. La razon no es que SIN carta adivine el proyecto: esa situacion
es la unica de las seis que ya trae, en el bloque "Tus trabajos vivos"
(`decision.py:89-91`, compartido por las dos ramas porque es parte de la
SITUACION, no de la carta ni de `PROYECTOS`), un trabajo titulado "el
banco de pruebas del lector". SIN carta hace eco de un titulo que ya
estaba en su propio prompt por otro motivo, no de nada que la carta le
haya dicho. Sacando esa situacion, a SIN carta le quedan **9** propuestas
legibles sin ningun bloque compartido, y nombra el proyecto en **0** de
ellas.

**Y el numero equivalente de CON carta tenia el mismo problema, sin
decirlo.** Una version anterior de este parrafo descontaba solo esa
situacion y decia que a CON carta le quedaban "8" limpias, pegado justo al
lado del "9" de SIN carta -- sin denominador propio, facil de leer como
"8 de 9" -- con la frase "ninguna con nada parecido a 'lector' en su
situacion de base". Esa frase es falsa para una de esas 8: "catalogo
poblado", sesgo 50, TAMBIEN comparte un
bloque -- `con_catalogo["catalogo"]` trae, literal,
`["el radar de precios", "el banco del lector", "un monitor de stock"]`, y
`decision.py:159-162` lo renderiza IGUAL para las dos ramas bajo
"Objetos que ya nombraste (si hablas de uno, escribilo igual)". Es el
mismo confundido que el parrafo de abajo ya senala para "el radar de
precios" en esta misma lista, aplicado al otro item: en las tres
corridas, CON carta propuso ahi, palabra por palabra,
`acelerar: el banco del lector para calipso-lector (medio)` -- lo unico
que agrega sobre el texto que el prompt ya le copio es el sufijo "para
calipso-lector".

Sacando las DOS situaciones con bloque compartido ("con un trabajo vivo" y
"catalogo poblado" a sesgo 50, tres instancias cada una): a CON carta le
quedan **15** propuestas legibles sin bloque compartido -- las cinco
restantes vienen todas de "sin nada" en sus dos sesgos -- y nombra el
proyecto asignado en **5** de ellas. Comparado, bajo el mismo filtro, con
el **0 de 9** de SIN carta de arriba: **5 contra 0, no 8 contra 0**, y con
los denominadores dichos aparte (15 y 9, no el mismo) para que no se lean
pegados como si fuera "8 de 9 contra 0 de 9". Sigue siendo la misma
direccion que el numero mas amplio y que el numero mas limpio de arriba;
es mas chico y mas honesto.

**Salvedad que importa para la Fase 2.** Las dos ramas de este experimento
difieren en dos bloques a la vez -- la carta Y los proyectos asignados --
nunca en uno solo. Los objetos que ganan la comparacion de arriba salen
literalmente del texto de `PROYECTOS`, no de la prosa de la carta. El
experimento sostiene que **darle mundo al jefe** (carta + proyectos juntos)
cambia lo que propone; no separa cuanto del cambio viene de la carta y
cuanto de saber que proyectos tiene asignados. Vale la pena decirlo porque
la pantalla de la Fase 2 es, sobre todo, para escribir la carta -- y este
experimento no aisla si eso es lo que mas importa, o si alcanzaba con que
el catastro le mostrara al jefe sus proyectos sin una sola linea de carta.

**Y del limite que la carta pone, hay poca traza.** La `CARTA` de esta
prueba dice explicitamente "no le toca mejorar a Calipso mismo". La segunda
propuesta de arriba (`acelerar: el desarrollo de un nuevo algoritmo para
mejorar la eficiencia del plugin de calipso-lector`) esta hablando de un
plugin -- codigo de Calipso -- y roza justo el limite que la carta puso.
No lo cruza con claridad suficiente para llamarlo una falla, pero tampoco
hay ninguna propuesta que demuestre que el jefe LEYO el limite y se
abstuvo por el. El experimento mide si el jefe usa lo que la carta nombra
(si), no si respeta lo que la carta prohibe (no hay evidencia ni en una
direccion ni en la otra).

#### Lo cuantitativo, con las tres corridas

La primera lectura de esta corrida comparaba "fichas legibles sobre el
total de comparaciones" (8/12 contra 4/12) y la leia como una ventaja de
formato de la rama con carta. **Esa lectura no sobrevive a condicionar en
haber propuesto**, que es la comparacion correcta: `nada` es una decision
legitima, no una falla de formato, y contarla junto con una ficha rota
infla el hueco. Y ninguna de las dos lecturas sobrevive del todo a agregar
una tercera corrida del mismo prompt exacto: corrida 3 (ver el aviso al
principio de esta seccion sobre por que antes no estaba citada) tira abajo
el mejor numero del documento.

**Cuantas veces cada rama eligio `proponer`** (formato aparte):

| | corrida 1 | corrida 2 | corrida 3 |
|---|:---:|:---:|:---:|
| CON carta propuso | 11 / 12 | 11 / 12 | 8 / 12 |
| SIN carta propuso | 6 / 12 | 6 / 12 | 6 / 12 |

**De las que propusieron, cuantas la ficha se pudo leer:**

| | corrida 1 | corrida 2 | corrida 3 |
|---|:---:|:---:|:---:|
| CON carta: legible / propuso | 8/11 (73%) | 7/11 (64%) | 6/8 (75%) |
| SIN carta: legible / propuso | 4/6 (67%) | 4/6 (67%) | 4/6 (67%) |

**Condicionado en haber propuesto, no hay ventaja de formato** -- en la
corrida 2 la rama SIN carta sale apenas mejor, y en las tres corridas las
dos ramas quedan dentro de un rango de 64% a 75%, sin que ninguna rama se
distinga con claridad. El hueco real esta en la fila de arriba, no en
esta.

**El conteo por pares** (particion completa de las 12 comparaciones en 5
categorias):

| categoria                              | corrida 1 | corrida 2 | corrida 3 |
|-----------------------------------------|:---------:|:---------:|:---------:|
| las dos legibles, MISMO objeto          |     1     |     1     |     1     |
| las dos legibles, objetos DISTINTOS     |     2     |     2     |     2     |
| SOLO la rama CON carta es legible       |     5     |     4     |     3     |
| SOLO la rama SIN carta es legible       |     1     |     1     |     1     |
| NINGUNA legible                         |     3     |     4     |     5     |

"SOLO la rama CON carta es legible" sigue siendo la categoria mas poblada
de las cuatro que comparan algo real, en las tres corridas -- pero baja en
cada una (5, 4, 3), igual que "NINGUNA legible" sube en cada una (3, 4, 5).
No es, como decia una version anterior de este texto, "mas que todas las
demas juntas": eso valia en la corrida 1 (5 contra 4) pero ya era FALSO en
la corrida 2 (4 contra 4, empatada), y en la corrida 3 la ventaja se redujo
mas (3 contra 4). Que sea la mas poblada de las cuatro que comparan algo
real sigue valiendo en las tres; que la tendencia entre corridas vaya
siempre en la misma direccion (para abajo) es un dato en si mismo.

**El unico "MISMO objeto" tiene la misma salvedad en las tres corridas.**
Pasa siempre en "catalogo poblado, sesgo 75", donde las dos ramas nombran
"el radar de precios" -- pero ese objeto sale del bloque `catalogo`, que es
parte de la SITUACION y esta identico en el prompt CON y SIN carta. No
cuenta a favor de que la carta alinee a las dos ramas.

#### El desagregado por sesgo, que es mas honesto que un p-valor

Todo lo de arriba mezcla dos regimenes que se comportan distinto, y
separarlos dice mas que cualquier prueba de signos:

**A sesgo 75 las dos ramas proponen 6/6, en las tres corridas.** Con
"explorar cosas nuevas" el jefe casi siempre decide proponer, tenga carta o
no. Todo el hueco de propension a proponer que se ve arriba vive a sesgo
50, no a sesgo 75.

**A sesgo 50, SIN carta propuso 0 de 18** (0/6, 0/6, 0/6 en las tres
corridas). Perfectamente estable: con "mantener el equilibrio" y sin carta,
el jefe nunca propone.

**A sesgo 50, CON carta propuso 12 de 18** (5/6, 5/6, 2/6). Muy inestable:
la misma situacion, el mismo prompt exacto, con `temperature=0`, dio 5/6
dos veces y 2/6 la tercera.

**La lectura correcta de esto no es un promedio.** La DIRECCION aguanta
las tres corridas: en ninguna de las tres SIN carta propuso mas que CON
carta a sesgo 50, ni siquiera igualo. Pero la MAGNITUD no aguanta ninguna
de las tres por separado -- 5/6 y 2/6 son diferencias demasiado distintas
como para promediarlas y llamar al promedio un numero solido, y por lo
tanto **tampoco aguanta ningun p-valor calculado sobre esa magnitud**: un
proceso que da 5, 5 y 2 sobre el mismo prompt exacto no es "casi
determinista", que era la premisa con la que una version anterior de este
texto justificaba no sumar corridas independientes. Si el proceso no es
casi determinista, las corridas no son "una corroboracion de la otra": son
mediciones con varianza real, y esta seccion tiene tres, dos de un lado (el
de la hipotesis) y una mucho mas debil.

Sobre "CON carta propone donde SIN carta dice `nada`" (diseno pareado,
prueba de signos):

| | corrida 1 | corrida 2 | corrida 3 |
|---|:---:|:---:|:---:|
| CON propone donde SIN dice nada | 5-0 (p aprox 0.06) | 5-0 (p aprox 0.06) | 2-0 (p aprox 0.50) |

Y sobre los pares discordantes en legibilidad (una rama legible, la otra
no) -- el corte que una version anterior de este texto llamaba "5 a 1 en el
peor corte", y esa frase era falsa dos veces: 5-1 es la corrida 1, no el
peor corte disponible ni siquiera con dos corridas (la corrida 2 da 4-1,
p aprox 0.375); y con la corrida 3 sumada, el peor corte real es **3-1** (p
aprox 0.625) -- una diferencia que una prueba de signos ni se acerca a
llamar significativa. La direccion es la misma en las tres (CON favorito,
nunca al reves en el margen), y el margen se achica cada vez que se agrega
una corrida.

**La frase que resume esto:** para decidir si vale la pena construir una
pantalla, la direccion de estas tres corridas alcanza. Para afirmar que el
efecto existe con confianza estadistica, no alcanzaba con dos corridas y
alcanza todavia menos con tres -- y sumar corridas que no son
independientes para mejorar un p-valor sigue sin ser valido, muestre lo que
muestre la direccion.

#### El resto, sin cambios de fondo

**Reproducibilidad.** De las 12 comparaciones, 11 categorizaron igual entre
las dos corridas originales; una ("con la bandeja llena", sesgo 50, CON
carta) paso de legible a ilegible entre una corrida y otra -- confirmado
con una tercera llamada aislada al mismo prompt exacto, que volvio a salir
legible (2 legibles contra 1 ilegible en tres intentos identicos,
`temperature=0`). La rama SIN carta fue completamente estable en esas dos
corridas. (Esta nota es sobre la estabilidad DENTRO de una comparacion
puntual, distinta de la inestabilidad de la propension a sesgo 50 que
mide la seccion de arriba con la corrida 3 completa.)

**Si la carta llega.** Sigue valiendo: los prompts van de 1381 a 1660
caracteres (crecieron un poco por el arreglo del formato), muy por debajo
del `num_ctx` de 8192 (409-500 tokens medidos en la corrida anterior, con
prompts mas cortos).

**Lo que no es la hipotesis pero se noto de paso.** El modelo confunde en
su prosa el presupuesto semanal restante con la billetera total; no afecta
la decision parseada.

**La lectura para Pedro, recalibrada otra vez.** Lo que sostuvo las tres
corridas sin retroceder, en su version mas limpia, es pareado: en "sin
nada" a sesgo 75, mismo denominador y sin ningun bloque compartido, CON
carta nombro el proyecto asignado 3 de 3 veces contra 0 de 3 de SIN carta.
Contando todo, es 11 de 21 contra 3 de 12 en bruto, y 5 de 15 contra 0 de
9 una vez que se sacan las dos situaciones con un bloque compartido entre
las dos ramas (explicado arriba): bajo ningun filtro SIN carta llego
siquiera a empatar. Tambien sostuvo las tres corridas -- aunque esto ya lo
decia una version anterior de este texto, y seguia siendo cierto -- la
DIRECCION del desagregado por sesgo: SIN carta nunca propuso a sesgo 50
(0 de 30, contando las dos plantillas) y las dos ramas siempre proponen a
sesgo 75 (6/6 en las tres corridas). Lo que NO aguanto las tres corridas
es la MAGNITUD de la propension de CON carta a sesgo 50 (salto entre 5/6 y
2/6 sobre el mismo prompt exacto, algo que no es un proceso casi
determinista), y por eso ninguna de las dos corroboraciones que una
version anterior de este texto invocaba para esa magnitud ("dos corridas",
"dos cortes distintos del dato") era valida: la primera se citaba para
sumar despues de haberse declarado que no se podia sumar, y la segunda son
el mismo evento medido dos veces (el hueco de legibilidad esta causado por
el de propension, no es independiente de el). Esta corrida no dice cuanto
del efecto cualitativo es la carta y cuanto son los proyectos que van con
ella, ni si el jefe respeta el limite que la carta le puso. Alcanza para
decidir si conviene construir la pantalla de la Fase 2 -- la direccion
nunca se invirtio en tres intentos -- pero no alcanza, y alcanza cada vez
menos, para prometer que fue la carta -- y no el ruido de un modelo de 7B
a sesgo alto -- la que hizo la diferencia en la MAGNITUD de los numeros.
Lo que si se puede prometer con mas fuerza es lo cualitativo, que es el
hallazgo que menos le pidio a la suerte de una corrida.

## 8. La Fase 2, y lo que la revision descubrio que cuesta

Esto **no se escribe hasta que la Fase 1 conteste**. Se documenta ahora porque
la revision encontro que cuesta bastante mas de lo que la version anterior
suponia, y ese costo es parte de la decision.

**El catastro necesita separar dos tablas.** Hoy `escanear` reconstruye la
lista de proyectos **solo con lo que encuentra**: lo que no aparece,
desaparece. No es hipotesis -- **la maquina ya borro un proyecto de este
disco**: el chroma del worktree `economia-frontera` sigue en
`~/.calipso/projects/` desde el 25 de agosto, el worktree ya no existe, y
`catastro.json` no tiene ninguna entrada. Y la rutina `catastro` esta
**habilitada cada 60 minutos con escaneo forzado** (corrio hoy 13:41). Un
proyecto declarado a mano, con su linea y su asignacion, se borraria solo
dentro de la hora.

La forma que lo cierra: **`escanear` es dueno de la tabla que descubre y la
puede truncar entera; lo que escribe Pedro vive aparte y `escanear` no lo toca
nunca.** La lectura une las dos. Con esa separacion se cierran de una vez el
borrado, el proyecto declarado sin `.git` y la ruta que dejo de existir.

**El catastro necesita un candado.** `escanear` lee, recorre el home con
subprocesos `git` de hasta 5 segundos cada uno, y despues escribe la lista que
armo con la PRIMERA lectura. Una escritura de la pantalla en ese hueco se
pierde sin error. La economia resolvio esto con `flock` en sus siete call
sites; el catastro no tiene nada. Hoy la carrera esta dormida porque nadie
escribe ahi: esta pantalla la despierta.

**El catastro necesita negarse a escribir sobre una lectura rota.** Si
`catastro.json` queda ilegible, `_cargar_json` devuelve la tabla vacia y
`escanear` **la escribe como verdad nueva**. Hoy eso cuesta tres `null`; con la
prosa de Pedro adentro, cuesta la prosa. `routines.py` ya aprendio exactamente
esta leccion y sus escritores se niegan a tocar el archivo tras una lectura
fallida. El catastro no tiene esa guarda, y `~/.calipso/backups/` esta vacio
con la rutina de backup apagada.

## 9. Quien lee una carta, y cuando

**No alcanza con sembrar.** La cadena real hasta que alguien lea una carta son
tres compuertas, no una:

1. **Sembrar.** Escribe el libro, el padron y las suscripciones. No crea
   ninguna rutina.
2. **Una rutina de jefe por departamento.** Un jefe solo tiquea si existe una
   entrada de tipo `departamento` con su cuenta y habilitada. Verificado en el
   `routines.json` real: hay **seis rutinas y ninguna es de ese tipo**. Solo
   `catastro` y `consumo` estan encendidas.
3. **El interruptor del plantel** tiene que estar encendido y en modo vivo.

**Y de ahi sale la regla para `finanzas`.** La version anterior decia que
`finanzas` no lleva carta porque no tiene jefe. Eso es tratar por nombre algo
que no vive en el nombre: el dataclass `Departamento` no tiene ningun campo
sobre tener jefe, y hardcodear el caso es exactamente la segunda fuente de
verdad que la seccion 10 prohibe.

Lo correcto es derivarlo de las rutinas: **"nadie lee esta carta todavia (no
hay rutina de jefe para esta cuenta)"**. `finanzas` cae solo en ese caso, sin
caso especial. Y de yapa, hoy **todos** los departamentos caen ahi -- que es la
verdad, y es un dato que Pedro necesita ver cuando escriba su primera carta y
no cambie nada.

## 10. Invariantes que no se tocan

- **El padron es la unica fuente de verdad de que departamentos hay.** La
  pantalla lo lee, nunca lo escribe. Nada se deriva del nombre de un
  departamento.
- **El aislamiento de la memoria del departamento se conserva.** `memory.py`
  documenta que esa memoria NO entra en la lectura combinada del chat. Este
  spec no la mete: la carta es otro archivo y no toca `_scopes`.
- **Leer no escribe.** Ni la carta ni la pantalla instancian un `Scope`.
- **`_es_repo` sigue exigiendo `.git`** para descubrir. Declarar es otro camino.
- **El escaneo sigue leyendo dos lineas del README y nada mas.** Este spec no
  le da al catastro permiso para leer mas disco.
- **`parsear` y la ficha no se tocan.** Esto cambia lo que el jefe LEE.

## 11. Lo que queda abierto

1. **Una carta rancia no se distingue de una fresca**, y la linea de Pedro es
   peor: llega rotulada "de Pedro", o sea con MAS autoridad, y puede contradecir
   un commit de ayer sin que nada avise. La Fase 2 puede mostrar la fecha; no
   resuelve que alguien la relea.
2. **Un tercio del catastro son worktrees.** `mapa-ciudad` es una rama de
   calipso, no un proyecto, y `_es_repo` los agarra a proposito. Una linea
   escrita sobre un worktree se pierde cuando la rama se cierra.
3. **Un proyecto pertenece a un solo departamento.** El campo es un valor, no
   una lista.
4. **`load_core` sigue sin techo.** Este spec le saca la carta de encima, pero
   si algo alguna vez escribe en el `core` de un departamento, entra entero al
   prompt y compite con la carta por el contexto.
5. **Nada obliga a que la carta se relea.** En este proyecto ya hay varias
   fuentes que se disenaron para que Pedro las llenara y quedaron vacias para
   siempre: el bibliotecario tiene 0 propuestas en toda la vida de la
   instalacion. Que la carta sea distinta es una apuesta sobre Pedro, no sobre
   el codigo.

## 12. Como se verifica que funciona

**Fase 1, unitario, sin modelo:**

- `ruta_carta` es pura: llamarla no crea ningun directorio ni ningun chroma.
  Ese test es el que fija la decision de la seccion 4.
- La carta se lee de su archivo, y **su texto NO aparece bajo "Lo que
  aprendiste antes"** ni en ningun otro bloque. Es el invariante de procedencia.
- El prompt trae la carta cuando existe y **la frase de "no tiene carta" cuando
  no existe**. Y un tercer caso: archivo presente pero vacio.
- El prompt lista los proyectos del departamento y **ninguno de otro**, con la
  cuenta completa como clave -- un catastro que guarde el nombre desnudo no
  debe matchear.
- La procedencia se dice, y las tres ramas producen textos distinguibles.

**Fase 1, contra el modelo:** el experimento de la seccion 7. No es criterio de
aceptacion del codigo.

**Fase 2:** no se especifica hasta que la Fase 1 conteste. Entre lo suyo va
tambien que un departamento sin rutina de jefe se diga como tal, derivado de
las rutinas y no de su nombre -- es de la pantalla, que la Fase 1 no construye. Cuando se escriba,
sus tres tests dificiles ya se conocen: correr `escanear` **despues** de
declarar y ver que la entrada sobrevive; escribir **mientras** el escaneo corre
y ver que no se pierde; y corromper el json y ver que el escaneo **se niega a
escribir** en vez de pisar.
