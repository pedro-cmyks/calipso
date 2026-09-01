# El mundo del jefe

**Fecha:** 2026-09-01
**Estado:** aprobado por Pedro seccion por seccion, listo para plan

## 1. Por que existe

El jefe de un departamento despierta hasta 200 veces por semana, mira un
prompt y decide si propone trabajo. Ese prompt **no tiene mundo**. Lo unico
de dominio que dice es el nombre del departamento:

> `Sos el jefe del departamento atlas de una fabrica de agentes.`

Todo lo demas son numeros y titulos que el propio mecanismo escribio: saldos,
techos, precios de capacidad, y las propuestas que el mismo jefe genero antes.
Un jefe del departamento taller **no puede saber que el lector existe**, porque
nada se lo cuenta.

**Y no es que el mundo no exista: hay dos armadores de prompt y solo uno esta
cableado.** El chat usa `prompt_compiler.compile_context`
(`calipso/server.py:1950`), que arma diez secciones -- constitucion, memoria
nucleo, recuerdos, repo, proyectos, meta activa, economia, estado operativo.
El jefe usa `decision.prompt` (`calipso/plantel/jefe.py:337`), cuyas unicas
entradas son la situacion economica mas su propia memoria.

**El canal ya existe y llega vacio.** `jefe.py:337` pasa
`ctx.memoria.load_core()` al prompt, y `load_core`
(`calipso/memory.py:67-71`) hace glob de `*.md` sobre el directorio del
departamento. Pero `append_core` (`memory.py:73-82`) tiene **un solo llamador
en todo el repo** (`memory.py:262`, dentro de `reflect`), y ese llamador elige
su destino en la linea anterior: `self.glob` o `self.project`, **nunca un
departamento**. `write_core` (`memory.py:84-87`) tiene cero llamadores.

El resultado esta escrito en el propio docstring de `decision.prompt`: sin el
nucleo, *"el jefe escribiria en su memoria y no la leeria nunca -- seria
memoria de solo escritura, y la tercera pata del departamento no serviria de
nada"*. Hoy esa pata esta exactamente asi.

**Y el campo del catastro se diseno para esto y lleva esperando.** El docstring
de `catastro.escanear` dice literalmente: *"Preserva `departamento` (lo escribe
Pedro, no el escaneo)"*. El campo existe, vale `null` en los tres proyectos, y
**no hay un solo camino en el codigo para que Pedro lo escriba**.

## 2. Alcance

**Entra:** la carta del departamento (un texto que escribe Pedro), la linea del
proyecto y su asignacion a un departamento, los dos bloques nuevos del prompt
del jefe, la pantalla de `/fabrica` donde se escriben las tres cosas, y poder
declarar a mano un proyecto que el catastro no ve.

**No entra, y cada uno es su propio spec:**

- **Limpiar las fuentes rotas.** Verificado sobre el disco real de Pedro: el
  chroma global tiene 0 documentos y el del proyecto tiene 36 en mojibake
  (`Pedro preguntÃƒÂ³`), la cronologia devuelve 0 entradas sobre 341 bytes
  porque `_parse_entry` exige un prefijo `- ` que el ejemplo del propio archivo
  no lleva, el bibliotecario tiene 0 propuestas en toda la vida de la
  instalacion, y la meta activa es `Test draft final` del 18 de junio.
- **La ventana de lo que Pedro anda haciendo.** Depende de la limpieza de
  arriba. Sin ella, cablear el jefe al compilador del chat le entrega diez
  encabezados con nada debajo, una meta de prueba y 36 recuerdos corruptos:
  ruido con forma de mundo, que es peor que el silencio.
- **Sembrar la economia.** Es un acto de Pedro y es irreversible.

## 3. La dependencia dura: esto se enciende cuando Pedro siembre

`~/.calipso/economia/` **no existe**, asi que el padron -- `departamentos.json`
-- tampoco. La lista de que departamentos hay sale de ahi y **no se duplica en
ningun otro lado**: dos fuentes de verdad sobre que departamentos existen es
justo lo que despues nadie sabe cual manda, y el padron es ademas irreversible
por diseno (no tiene alta ni baja fuera de la siembra).

Consecuencia: **la pantalla no tiene departamentos que mostrar hasta que Pedro
siembre.** Antes de eso dice que no se sembro, en vez de mostrar casillas
vacias que se leen como un error.

No es un accidente desafortunado: escribir la carta de un departamento es
exactamente lo que se quiere hacer *en el momento de sembrar*. La carta dice
para que existe; la siembra lo crea.

La mitad de proyectos de la pantalla -- la linea, la asignacion, declarar uno a
mano -- **si funciona sin siembra**, porque el catastro existe y tiene tres
proyectos. Lo unico que no se puede hacer antes es asignar un proyecto a un
departamento que todavia no existe.

## 4. La carta del departamento

Un markdown que escribe Pedro, en el `core` que ya existe:

```
~/.calipso/memoria/departamento/<clave>/core/que-es.md
```

La `<clave>` sale de `Memory.departamento(nombre)` (`memory.py:184-189`), que
hace `_slug` sobre el nombre que le pasa `server.py:2788`
(`cuenta.split(":", 1)[1]`). O sea que la cuenta `dep:taller` da la clave
`taller`.

**No se inventa ningun canal.** `load_core` ya hace glob de `*.md` sobre ese
directorio y el jefe ya lo lee en cada tic. Lo unico que falta es un escritor.

**Que dice una carta.** Para que existe el departamento, que mira, y que no le
toca. Ese ultimo tercio importa tanto como los otros dos: un jefe que no sabe
que NO le toca propone sobre cualquier cosa.

**`finanzas` no lleva carta.** Es del padron y no tiene jefe nunca (decision de
Pedro, por la invariante 12 de la economia), asi que su carta no la leeria
nadie. La pantalla lo dice; no lo deja en blanco, porque un blanco se lee como
un hueco que Pedro tiene que llenar.

**Un `core` con varios `.md` funciona igual.** `load_core` los concatena
ordenados por nombre, con `### <stem>` de encabezado. El spec propone un solo
archivo, `que-es.md`, pero no hay nada que impida que Pedro agregue otros y el
mecanismo no cambia.

## 5. La linea del proyecto, y a quien pertenece

Dos campos en la entrada del catastro:

- **`departamento`** -- ya existe, vale `null` en los tres, y su docstring dice
  que lo escribe Pedro. Solo falta el camino.
- **`linea`** -- nuevo. Una frase de Pedro: que es el proyecto y en que etapa
  esta.

**De donde sale el resumen que ve el jefe, en este orden:**

1. La `linea` que escribio Pedro, si la escribio.
2. Si no, el `resumen` que ya extrae el catastro (`_resumen_readme`: las dos
   primeras lineas del README, cortadas a 240 caracteres).
3. Si tampoco, se dice que no hay.

**Y el prompt dice cual de las tres es.** Un jefe que lee una linea escrita por
Pedro y una sacada de un README no puede tratarlas igual: la primera es una
decision, la segunda es lo que un archivo dijo alguna vez. Confundirlas es
darle a un texto de junio el peso de una instruccion de hoy.

Hoy, con el extractor actual: `resumen` es `""` en dos de los tres proyectos y
`"# Atlas"` en el tercero. O sea que la caida al README no salva casi nada, y
la linea de Pedro es la que hace el trabajo. El orden existe para que no haya
un hueco mudo, no porque el README alcance.

## 6. Lo que el jefe ve

Dos bloques nuevos en `decision.prompt`, y **los dos hablan cuando estan
vacios**:

```
Este departamento:
  I+D para los proyectos de Pedro. Mira prototipos, bancos de
  prueba, hardware. No le toca mejorar a Calipso mismo.

Proyectos a tu cargo:
  - calipso-lector: convertir el Musnap en la pantalla de
    Calipso. El plugin arranca; falta el banco.        (de Pedro)
  - atlas: inteligencia narrativa sobre feeds        (de sus docs)
```

Y cuando no hay:

```
Este departamento: todavia no tiene carta. Pedro no escribio para
que existe, asi que no sabes que te toca ni que no.

Proyectos a tu cargo: ninguno asignado.
```

**Que hablen cuando estan vacios es la decision, no un detalle de redaccion.**
Hoy el bloque de memoria desaparece entero cuando el nucleo esta vacio
(`decision.py`: `aprendido = ... if nucleo.strip() else ""`), asi que "nadie
escribio la carta" y "la carta no dice nada" se leen igual, y el jefe no tiene
como notar que le falta algo. Un jefe que sabe que le falta la carta puede
decirlo; uno que ve un prompt sin el bloque, no.

Los bloques nuevos van **arriba** de los numeros de la economia. Lo que el
departamento es viene antes de cuanta plata tiene.

## 7. La pantalla

Una pestana en `/fabrica`. Dos listas y nada mas:

**Departamentos** -- salen del padron. Cada uno con su carta, editable ahi
mismo, y el hueco visible cuando no la tiene. `finanzas` aparece dicho: no
lleva carta porque no tiene jefe.

**Proyectos** -- salen del catastro. Cada uno con su linea, editable, y a que
departamento pertenece.

**Escribe exactamente tres cosas**, y ninguna mas: la carta de un departamento,
la linea de un proyecto, y la asignacion de un proyecto a un departamento.

**No da de alta departamentos.** Eso es la siembra, es irreversible, y darle
un boton a algo que no se deshace en la misma pantalla donde se editan textos
es invitar al accidente.

**Sin siembra, la mitad de departamentos dice que no se sembro** y la de
proyectos funciona igual, salvo el desplegable de asignacion, que no tiene a
quien asignar.

## 8. Declarar un proyecto que el catastro no ve

`calipso-lector` es invisible para el catastro, y la razon es concreta:
`_es_repo` (`catastro.py:116-120`) devuelve `(path / ".git").exists()` y su
docstring dice que es *"el unico criterio"*. Esa carpeta tiene `BRIEF.md` y
`BRIEF.md.bak`, no tiene `.git`. Son 25 KB de las palabras de Pedro sobre el
lector -- justo lo que un jefe de taller necesitaria -- estructuralmente
invisibles.

**El criterio no cambia.** Es lo unico que hoy impide que el catastro se llene
de carpetas al azar del home, y aflojarlo afecta el descubrimiento de todo.

**Se suma declarar a mano**, desde la misma pantalla: una ruta y un nombre. La
entrada declarada vive en el catastro como cualquier otra, con una marca de que
fue declarada y no descubierta, y `escanear` la preserva igual que preserva
`departamento`.

Una ruta declarada que no existe en el disco se dice en la pantalla; no se
borra sola. Que Pedro mueva una carpeta no es razon para que Calipso olvide que
el proyecto existe.

## 9. Invariantes que no se tocan

- **El padron es la unica fuente de verdad de que departamentos hay**, y no se
  duplica. La pantalla lo lee, nunca lo escribe.
- **El aislamiento de la memoria del departamento se conserva.** `memory.py`
  dice que la memoria de un departamento NO entra en `_scopes` a proposito --
  esa es la lectura combinada del chat. Este spec abre el canal en la direccion
  Pedro -> departamento escribiendo un archivo en su `core`, **sin** volver
  `departamento()` parte de `_scopes`. Lo del departamento sigue sin filtrarse
  al chat de Pedro.
- **`_es_repo` sigue exigiendo `.git`** para descubrir. Declarar es otro camino,
  no una excepcion al criterio.
- **El catastro sigue preservando `departamento`** entre escaneos, y ahora
  tambien `linea` y la marca de declarado.
- **El escaneo sigue leyendo dos lineas del README y nada mas.** Este spec no
  le da al catastro permiso para leer mas del disco: la linea rica la escribe
  Pedro.
- **`parsear` y la ficha no se tocan.** Este spec cambia lo que el jefe LEE, no
  lo que escribe.

## 10. Lo que queda abierto

1. **Una carta rancia no se distingue de una fresca.** Si Pedro escribe la
   carta de taller en septiembre y en marzo el taller hace otra cosa, el jefe
   sigue leyendo septiembre con la misma confianza. No hay fecha, no hay aviso.
   Se podria mostrar cuando se escribio; no esta en este spec.
2. **Nada obliga a que la carta sea corta.** `load_core` concatena todo lo que
   haya. Un `core` de 20 KB entra entero al prompt de un modelo de 7b y desplaza
   al resto. El spec no pone techo porque no hay un numero defendible sin medir;
   la pantalla puede mostrar el largo.
3. **Un proyecto pertenece a un solo departamento.** El campo es un valor, no
   una lista. Es lo mas simple y coincide con como esta escrito hoy, pero un
   proyecto que toque a dos departamentos no se puede expresar.
4. **No esta verificado que esto cambie lo que el modelo local propone.** Todo
   el spec es una apuesta razonable: que un jefe con contexto propone mejor que
   uno sin contexto. Medir eso pide correr la fabrica sembrada un rato, que hoy
   no se puede.

## 11. Como se verifica que funciona

**Unitario, sin modelo y sin siembra:**

- La carta se lee del `core` del departamento: escribir el `.md`, construir la
  memoria de ese departamento, y confirmar que `load_core` lo devuelve.
- El prompt trae la carta cuando existe, y **trae la frase de "no tiene carta"
  cuando no existe**. Ese par es el que fija la decision de la seccion 6.
- El prompt lista los proyectos del departamento y **ninguno de otro**.
- La procedencia se dice: un proyecto con `linea` de Pedro y otro sin ella
  producen textos distinguibles en el prompt.
- El orden de caida: `linea` gana al `resumen`; sin ninguno de los dos, se dice
  que no hay.
- `finanzas` no recibe carta y la pantalla lo dice.
- Escribir la carta y la linea no toca ninguna otra clave del catastro, y un
  `escanear` posterior preserva las tres (`departamento`, `linea`, declarado).
- Un proyecto declarado a mano aparece en el catastro sin `.git`, y `_es_repo`
  sigue devolviendo False para esa ruta -- o sea que se declaro, no se aflojo
  el criterio.
- Sin siembra: la mitad de departamentos de la pantalla dice que no se sembro,
  y la de proyectos responde igual.

**Del lado del cliente**, con el runner de Node: la pantalla dibuja el hueco de
una carta ausente de forma distinguible de una carta vacia, y `finanzas` sale
dicho y no en blanco.

**Y un chequeo que ningun test hace:** despues de escribir una carta de verdad,
mirar el prompt que sale. Es el unico modo de ver si el bloque nuevo desplazo
algo que hacia falta.
