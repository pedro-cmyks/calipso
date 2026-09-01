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

**Como llegan los proyectos al prompt.** `decision.prompt(s, sesgo, nucleo,
recientes)` no recibe el catastro y `jefe.tic` no se lo pasa. Los proyectos
entran por `situacion()`, que es quien ya arma el dict que el prompt consume:
gana una clave `proyectos_a_cargo`, y `situacion` es quien lee el catastro. La
firma de `prompt` gana un parametro para el estado de la carta, que no sale de
`situacion` porque no es economico.

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
catalogo poblado -- cada una con **dos sesgos** (50, "mantener el equilibrio",
y 75, "explorar cosas nuevas") y renderizada con la carta y los proyectos y
sin ellos: **12 comparaciones**, 24 llamadas al modelo local por corrida. Se
corrio dos veces completas. Diferencia entre las dos: **una sola linea de
las 78 que imprime el script**, el campo `tarda` de una ficha (ver
"Reproducibilidad" mas abajo) -- todo lo demas, incluido el conteo final,
salio identico.

**Por que hacian falta los dos sesgos.** La primera corrida (un solo sesgo,
50) dejo 5 de las 6 situaciones empatadas en `nada` de los dos lados: el jefe
no estaba de animo de proponer en ninguna rama, y un empate en `nada` no dice
nada sobre la hipotesis. El sesgo 75 fuerza al jefe a la zona de "explorar",
y ahi propuso (con o sin carta, o ambas) en las 6 situaciones.

**El conteo pedido, sobre las 7 de 12 comparaciones donde AL MENOS UNA rama
propuso** (las otras 5, todas con sesgo 50, empataron en `nada` y no
cuentan):
- Mismo objeto (misma clave en las dos fichas): **0**
- Objetos distintos: **6**
- Propone SOLO la rama CON carta: **1**
- Propone SOLO la rama SIN carta: **0**

**Ese "6" no se puede leer como "seis comparaciones reales de un objeto
contra otro".** De las 6 marcadas "distintos": en **4** las DOS ramas
devolvieron una ficha **ilegible** -- `parsear_ficha` no pudo leer ningun
objeto de ningun lado, asi que no hay nada que comparar, son dos fallas de
formato que la regla del script (no se puede confirmar que sean iguales)
cuenta como "distinto" a falta de otra categoria. En las otras 2, una rama
(siempre CON carta) devolvio una ficha legible y la otra (siempre SIN carta)
salio ilegible -- tampoco hay un segundo objeto real contra el cual
comparar. **Ninguna de las 6 es un caso de "las dos propusieron un objeto
legible y eran distintos".**

**El numero que si se lee solo, y que importa mas que el pedido: cuantas
fichas *legibles* salieron de cada lado.** En las 12 comparaciones de cada
corrida (24 llamadas), el modelo escribio una ficha que `parsear_ficha` pudo
leer **3 veces, y las 3 del lado CON carta** ("sin nada" a sesgo 75,
"catalogo poblado" a sesgo 50, "catalogo poblado" a sesgo 75) -- y en 2 de
esas 3 nombro el objeto exacto que `PROYECTOS` le paso (`calipso-lector`,
"falta el banco de pruebas"). **El lado SIN carta no produjo NINGUNA ficha
legible en ninguna de las 12 llamadas de ninguna corrida** (0 de 6 intentos
por corrida, en las dos corridas). Apunta en la misma direccion que la
hipotesis, y con mas fuerza que el conteo de mismo/distinto: tener un objeto
concreto que nombrar no solo cambia QUE nombra, tambien parece ayudarlo a
llenar el resto de la ficha sin romper el formato.

**Por que se rompe la ficha -- hallazgo nuevo, que solo aparecio al agregar
el sesgo 75.** El texto crudo de las fichas ilegibles muestra el mismo
patron una y otra vez: el modelo escribe DOS O MAS promesas separadas por
"|" en el renglon `promete`, copiando literalmente el formato con el que el
prompt LISTA las opciones (`"promete: " + " | ".join(ficha.PROMESAS)`) en
vez de elegir una sola. Ejemplos reales, texto crudo: `promete: acelerar |
medir` y `promete: acelerar | arreglar | medir | construir`.
`ficha._por_prefijo` no matchea eso contra ninguna promesa de la lista y la
ficha entera cae con `parsear_ficha` -> `None`. Aparece CON carta y SIN
carta por igual (en 4 de las 6 situaciones a sesgo 75 rompio en las DOS
ramas) -- no es un efecto de la carta, es un efecto del sesgo alto: al
"explorar", el modelo hedgea entre varias promesas en vez de comprometerse a
una. Es la version real de la preocupacion que esta seccion nombraba antes
de correr nada ("si los bloques nuevos empujan la gramatica a romperse") --
salvo que lo que la rompe no es la carta, es el modo explorar, y le pasa
tanto con carta como sin ella.

**Si la carta llega.** Si, con margen amplio, sigue valiendo con las 12
situaciones nuevas: los prompts van de 1226 a 1505 caracteres. No se le pidio
`prompt_eval_count` a esta corrida (se le pregunto aparte a Ollama en la corrida
anterior, con las mismas seis situaciones y sesgo 50: 409 a 500 tokens
contra el `num_ctx` de 8192 -- sobra margen de sobra para lo que agregan las
situaciones con sesgo 75, que no cambian el tamano del prompt de forma
apreciable: la diferencia entre sesgo 50 y 75 de la misma situacion es de 1
caracter, el numero del sesgo mismo no entra al texto del prompt).

**Reproducibilidad entre las dos corridas.** Se corrio el script completo
DOS VECES. El `diff` de las dos salidas completas (78 lineas cada una,
incluido el conteo final) difiere en **una sola linea**: el campo `tarda` de
la ficha de "catalogo poblado, sesgo 50, CON carta" salio `medio` en la
primera corrida y `corto` en la segunda. La accion (`nada`/`proponer`), el
objeto nombrado y la legibilidad de la ficha fueron identicos en las 12
comparaciones de las dos corridas, y el conteo final (0 / 6 / 1 / 0) fue
identico en las dos. Con `temperature=0` uno esperaria mas estabilidad
todavia; el campo `tarda` es, hasta ahora, el unico que se vio moverse entre
corridas identicas -- la accion y el objeto no se movieron ni una vez en las
24 comparaciones de las dos corridas (contando la corrida anterior con un
solo sesgo).

**Lo que no es la hipotesis pero se noto de paso.** En varias respuestas
`nada` el modelo confunde en su prosa el presupuesto semanal restante
(`presupuesto_semanal_mm - salidas_semana_mm`) con la billetera total
(`disponible_mm`) -- llama "disponible" a un numero que es el otro. No afecta
la decision parseada, pero es una senal de que el modelo de 7b no lee los
numeros del prompt con precision.

**La lectura para Pedro.** El conteo pedido (0 mismo / 6 distinto / 1 solo-
CON / 0 solo-SIN) es real pero enganoso si se lee sin el detalle de arriba:
la mayoria del "6" son fichas ilegibles de los dos lados, no comparaciones
de un objeto contra otro. El dato que si aguanta la lectura sola es mas
chico y mas duro: en toda la corrida, **la unica rama que alguna vez
completo una ficha legible fue la que tenia carta**, tres veces sobre tres.
La rama sin carta, cuando propuso, nunca termino de escribir una ficha que
el parser pudiera leer. Sigue siendo poca evidencia -- tres exitos contra
cero, no treinta contra cero -- pero no hay ni un solo caso, en dos corridas
completas, donde la rama SIN carta haya producido algo que la carta no
produjera igual o mejor. Y aparecio un costo nuevo, aparte del que motivaba
esta pregunta: a sesgo alto el jefe hedgea el campo `promete` y rompe la
ficha con o sin carta, un problema de la gramatica en modo explorar que no
tiene nada que ver con esta fase y que convendria mirar aparte de la
decision de la Fase 2.

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
