# La gramatica de `proponer`

**Fecha:** 2026-09-01
**Estado:** aprobado por Pedro seccion por seccion, listo para plan

## 1. Por que existe

Hoy un jefe propone escribiendo dos renglones de prosa. El segundo, cortado a
120 caracteres, se convierte en el titulo de la propuesta
(`calipso/server.py:5605`), y ese titulo es **lo unico que la identifica**: el
id es un uuid nuevo en cada alta (`server.py:5602`), y `bus.alta` valida la
forma del resto pero no mira el titulo (`calipso/economia/bus.py:70-99`).

De ahi salen tres agujeros, los tres verificados:

**El "no" de Pedro no frena nada.** `descartadas_semana` se escribe en
`calipso/plantel/situacion.py` y se lee en un solo lugar,
`calipso/plantel/decision.py`, para armar un renglon del prompt. `jefe._puede`
(`calipso/plantel/jefe.py:230-292`) no la nombra nunca: su unico contador es
`len(s["propuestas_propias"])` contra `TECHO_PROPUESTAS`. El "no" es un pedido
de buena voluntad a un modelo local, y caduca a la semana.

**Y no se puede arreglar donde corresponde.** El freno tiene que vivir en
`_puede`, pero `_puede` no tiene con que comparar. `proponer` ni siquiera trae
referencia: `decision.py:129` devuelve `("proponer", None, motivo)`. Comparar
titulos por igualdad no atrapa nada -- el mismo modelo escribe "radar de
precios" y "un radar de precios de la competencia" en dos tics -- y por
substring atrapa de mas y es imposible de explicar el dia que Pedro vaya a
revocar.

**La propuesta no declara como se sabe si salio bien.** `criterio` en el bus es
el criterio de MUERTE (`_CLAVES_CRITERIO = {"gasto_max_mm", "semanas_max"}`,
`bus.py:30`), no una metrica de exito. Y su `semanas_max` es hoy un `4`
literal escrito a mano (`server.py:5619`), igual para una propuesta de una
semana que para una de un trimestre.

**El precedente que este diseno copia** es el motor de permisos, que resolvio
el mismo problema y esta en `main`: separa la `forma` -- lo unico que se
compara -- del titulo y el detalle, que Pedro lee y que no participan de
ninguna comparacion (`calipso/permisos/acciones.py`). Este documento le da a
una propuesta su `forma`.

## 2. Alcance

**Entra:** la ficha de cuatro renglones, su parseo con reparacion
deterministica, la normalizacion que le da identidad, el catalogo de objetos
en el prompt, los campos que el codigo deriva de la ficha, la forma tipada
guardada en el bus, y la valvula para lo que no parsea.

**No entra, y cada uno es su propio spec despues:**

- **El `no_siempre` de la mesa.** Es lo que esta gramatica desbloquea, pero
  necesita su propio almacen de reglas, un punto de captura del alcance en
  `api_eco_bus_descartar` (que hoy no recibe cuerpo) y el corte en `_puede`.
- **El PvP.** Necesita la vara que sale de `promete` y `tarda`, mas el colapso
  por familia, el piso por departamento y las reglas de desempate.

La gramatica sola ya entrega: las propuestas pasan a tener forma comparable,
la metrica de exito deja de no existir, `semanas_max` deja de ser un literal, y
se arregla la semana congelada de la seccion 9.

**Lo que este documento NO arregla y conviene tener escrito:** el prompt del
jefe no tiene mundo. `situacion()` le devuelve plata y titulos que el propio
mecanismo escribio; el unico canal de texto sobre el dominio es el `core` del
departamento, y **nadie lo escribe en el codigo** -- el unico llamador de
`append_core` apunta a `glob` o `project` (`calipso/memory.py`). Un jefe de
taller no puede saber que el lector existe salvo que Pedro le deje un archivo a
mano. Achicar el vocabulario de salida no le da nada nuevo que decir. Es el
cuello de botella real y es otra decision.

## 3. La ficha

Cuatro renglones. Reemplazan al segundo renglon libre, solo para `proponer`:
`nada`, `pedir <monto>`, `trabajar <id>` y `comentar <id>` no cambian.

```
proponer
sobre:   el radar de precios
promete: descartar
tarda:   corto
porque:  no rindio y sigue gastando capacidad todas las semanas
```

| campo | quien lo pone | obligatorio |
|---|---|---|
| `sobre` | el modelo, texto libre sin tope de palabras | si |
| `promete` | el modelo, una de seis | si |
| `tarda` | el modelo, una de cuatro | si |
| `porque` | el modelo, hasta 120 caracteres | no |

**Las seis promesas**, y son el vocabulario entero: lo que no esta aca, un
departamento no lo puede pedir.

```
ahorrar     acelerar     arreglar     medir     construir     descartar
```

**Los cuatro plazos:**

```
corto     medio     largo     no se
```

`no se` existe a proposito: sin el, un modelo que no sabe elige uno al azar y
la mentira entra al criterio de muerte. Declararlo es informacion; adivinarlo
es ruido.

## 4. El parseo, y la reparacion antes de rendirse

El parseo de hoy (`decision.py:112-142`) toma `lineas[1]` tal cual como motivo.
Pasa a leer los cuatro renglones, y **repara antes de rendirse**:

1. Cada renglon se parte en el primer `:`.
2. La clave se normaliza (minusculas, sin tildes) y se matchea por **prefijo
   unico** contra `{sobre, promete, tarda, porque}`. `Sobre:`, `SOBRE :` y
   `sob:` son la misma clave. Un prefijo ambiguo no matchea.
3. **El orden no importa.** Los cuatro renglones pueden venir en cualquier
   orden.
4. `promete` y `tarda` se matchean tambien por prefijo unico contra sus listas.
   `desc` es `descartar`; `a` es ambiguo entre `ahorrar` y `acelerar` y no
   matchea.
5. `porque` puede faltar. Si falta, el titulo se arma sin el (seccion 7).
6. Renglones con claves que no matchean se ignoran, no rompen.

**Cae en la valvula (seccion 9), no en `nada`,** si despues de reparar falta
`sobre`, falta `promete`, falta `tarda`, o si `promete`/`tarda` no matchean
ninguna opcion.

La tolerancia de hoy se conserva donde ya existe: la primera linea sigue
aceptando `Proponer:` porque `lineas[0].replace(":", " ").lower().split()`
(`decision.py:121`) no cambia.

## 5. La identidad: como se normaliza `sobre`

Es la funcion de identidad de una propuesta. Por la leccion de permisos tiene
que ser **explicable el dia que Pedro revoque**: "dijiste que no a este
objeto, escrito asi".

```
normalizar("El Radar de Precios!")  ->  "precios+radar"
normalizar("el radar de precios")   ->  "precios+radar"
normalizar("radar de precio")       ->  "precio+radar"     (otra familia)
normalizar("el modelo 7b")          ->  "7b+modelo"
normalizar("el modelo 3b")          ->  "3b+modelo"        (otra familia)
```

El algoritmo, en orden:

1. Minusculas.
2. Sin tildes ni diacriticos (NFKD y descarte de combinantes).
3. Todo lo que no sea letra o digito pasa a separador.
4. Se descartan los funcionales: `el la los las un una unos unas de del al a en
   para por con y o que su sus mi mis lo`.
5. Se descartan los tokens vacios.
6. Se ordenan y se unen con `+`.

**Se ordena** porque el orden de las palabras es lo que un modelo mas varia, y
en una frase nominal casi nunca carga significado.

**Los digitos se quedan.** Descartarlos haria que `el modelo 7b` y `el modelo
3b` fueran la misma familia, y son cosas distintas.

**Singular y plural son dos familias.** `precio` no es `precios`. No se usa
stemming: seria difuso y no se podria explicar cuando Pedro revoque. El
paliativo es el catalogo (seccion 6).

**Si despues de normalizar no queda ningun token** -- `sobre: el` -- la ficha
cae en la valvula. Un objeto sin contenido no es un objeto.

## 6. El catalogo de objetos

Un bloque nuevo en el prompt con los objetos que **ese** departamento ya
nombro, el mas nuevo primero:

```
Objetos que ya nombraste (si hablas de uno, escribilo igual):
  - el radar de precios
  - el banco del lector
```

Sale del bus: las propuestas cuyo `departamento` es la cuenta de ese jefe, por
su `forma.sobre` crudo, deduplicadas por `forma.clave`. Es el paliativo del
problema de los sinonimos: sin el, "radar de precios" y "monitor de precios"
son dos familias, ocupan dos lugares y un "nunca mas" sobre una no tapa la
otra.

Lleva un tope de renglones. **Ese tope es de espacio del prompt, no una regla
sobre lo que un departamento puede hacer**: nombrar un objeto que no esta en la
lista es correcto y esperado.

Y las listas que ya existen en el prompt (`propuestas_propias`,
`propuestas_ajenas`, `descartadas_semana`) dejan de mostrar el titulo libre y
muestran la forma:

```
Propuestas tuyas todavia sin financiar:
  - p4: construir el banco del lector (medio)
```

Asi lo que el modelo lee y lo que tiene que escribir tienen la misma forma.

## 7. Lo que el codigo deriva, y lo que no

El principio: **se guarda lo que el modelo dijo y se deriva el resto.** Nada
derivable se persiste, para que no pueda quedar desincronizado.

**La metrica de exito** sale de `promete`, por tabla pura. Hoy no existe:

```
ahorrar     -> milimonedas por semana que dejan de salir de esa cuenta
acelerar    -> semanas hasta cerrar
arreglar    -> veces que vuelve a fallar
medir       -> existe el numero: si o no
construir   -> usos en cuatro semanas
descartar   -> milimonedas por semana que dejan de salir
```

No se guarda: se deriva al mostrarla. Es la unica manera de que cambiar la
tabla arregle tambien las propuestas viejas.

**`semanas_max`** sale de `tarda`, y reemplaza el `4` literal de
`server.py:5619`:

```
corto 1     medio 4     largo 12     no se 4
```

`no se` toma el valor de hoy a proposito: es el unico que no empeora nada.

**El titulo** se arma con la ficha, en vez de ser el motivo crudo:

```
con porque:  "descartar: el radar de precios (corto) -- no rindio y sigue gastando"
sin porque:  "descartar: el radar de precios (corto)"
```

Sigue cortado a 120 caracteres, igual que hoy.

**Lo que NO cambia:** `presupuesto_mm` lo sigue poniendo la perilla del jefe y
el libro, no el modelo (`server.py:5583-5601`). `retorno_mm` sigue siendo una
copia de `presupuesto_mm`. `gasto_max_mm` sigue siendo el presupuesto.

## 8. Lo que queda escrito en el bus

`bus.alta` (`bus.py:70-99`) gana un parametro `forma`, obligatorio para
`tipo="trabajo"`:

```python
forma = {
    "sobre": "el radar de precios",     # crudo, lo que el modelo escribio
    "clave": "precios+radar",           # normalizado, lo unico que se compara
    "promete": "descartar",
    "tarda": "corto",
}
```

Se valida como se valida `criterio`: claves conocidas, `promete` y `tarda` en
sus listas, `sobre` y `clave` strings no vacios. Un `alta` sin `forma` valida
levanta `ErrorBus`, igual que hoy un `criterio` invalido.

**`clave` se guarda ademas de derivarse** -- es la unica excepcion al principio
de la seccion 7, y a proposito: el libro es append-only, y si la funcion de
normalizacion cambia manana, una propuesta vieja tiene que seguir comparandose
como se comparaba el dia que se escribio. Es la misma razon por la que el
permiso guarda su `forma` y no la recalcula.

**El pre-seed (`tipo="preseed"`) no lleva `forma`.** No sale de una ficha: sale
de `pedir <monto>`, que es otro verbo, y su titulo ya tiene su propio armado
(`server.py:5488`). Que `forma` sea obligatoria solo para `tipo="trabajo"` es
lo que evita inventarle una ficha a algo que no la tiene.

**Compatibilidad:** una propuesta escrita antes de este cambio no tiene
`forma`. Todo lector la trata como una propuesta sin identidad comparable: no
entra al catalogo, no colapsa con nadie y ninguna regla la tapa. Se lee, se
financia y se descarta como siempre. No hay migracion.

## 9. La valvula, y los tres casos que hoy estan fundidos en dos

**Una ficha ilegible no cae en `nada`.** La prosa cruda se escribe en
`<base>/economia/ilegibles.jsonl` -- append-only, al lado del bus, con
`{ts, semana, departamento, crudo}` -- y aparece en la bandeja de la fabrica
como un item de clase `aviso` con esa prosa adentro.

**No va al bus.** El libro es contable y un aviso no es un objeto economico: no
ocupa lugar, no compite, no se puede financiar y no cuenta para el badge. Se
colapsa por texto identico -- a temperatura 0 (`server.py`, config del modelo
local) la repeticion es byte a byte -- asi que doscientos tics dan una fila con
un contador.

**Y aca esta el arreglo de la semana congelada.** Hoy hay tres situaciones y el
codigo las trata como dos:

| caso | que paso | memoria hoy | memoria despues |
|---|---|---|---|
| `nada` | el modelo eligio no hacer nada | no escribe | **no escribe** (igual) |
| freno | el modelo decidio bien, la maquina lo paro | no escribe | **no escribe** (igual) |
| ficha ilegible | el modelo intento y fallo | no escribe | **escribe** |

Los dos primeros son correctos y estan fijados por tests que siguen valiendo
(`test_plantel_jefe.py:174-190` fija que un freno no anota, con el argumento de
que "el jefe quemaria un tic por semana en un no-op que igual se anotaria como
que actuo"). El tercero es el bug: `remember` esta adentro de `if permiso:`
(`jefe.py:357-361`) y `_puede` devuelve `False` para `nada`
(`jefe.py:232-233`), asi que una ficha ilegible no deja rastro, el prompt del
tic siguiente es identico, y a temperatura 0 la respuesta tambien.
**El primer tic que no parsea le termina la semana al departamento**: 200 tics
(`interruptor.py:27`) quemados en un punto fijo.

La valvula lo rompe: el aviso escribe la memoria episodica del departamento, y
el prompt del tic siguiente ya no es el mismo.

**Tres avisos del mismo departamento en una semana es la senal de que al menu
le falta una promesa.** La gramatica crece una vez por mano de Pedro, no
doscientas por mano del modelo.

## 10. Lo que un departamento deja de poder decir

Sin suavizar. Hoy taller podria escribir:

> "montar el banco de pruebas del lector con el Musnap conectado y, si el
> render e-ink aguanta, recien ahi portar la skin -- pero solo si Pedro
> consigue el segundo aparato"

Queda: `construir: el banco del lector (medio)`. Se pierden las dos etapas, la
condicion, la dependencia de hardware y el "si aguanta".

Ademas:

- **Ninguna magnitud, umbral ni meta.** "Bajarlo a 2 segundos" y "bajarlo un
  poco" son la misma propuesta con la misma vara.
- **Nada compuesto ni condicional.**
- **Ningun acto que no sea una de las seis promesas**: negociar con otro
  departamento, objetar una propuesta ajena, retirar la propia.
- **La propuesta sobre si mismo**: "este departamento esta mal planteado".

La prosa sigue existiendo en `porque` y en la valvula, pero **deja de dirigir**:
se degrada de rango. Ese es el precio, y se paga a cambio de que exista una
identidad que la mesa pueda comparar.

## 11. Invariantes que no se tocan

- **El libro es append-only.** Nada de esto reescribe un asiento.
- **`bus.alta` es una escritura** y sigue yendo bajo `_eco_candado`, con un
  `Bus` fresco construido adentro (`server.py:5607-5609`).
- **El techo de tres propuestas en pie** y su re-chequeo fresco bajo candado
  (`_bandeja_llena`) no cambian.
- **Descartar sigue liberando el cupo.** Es la salida cuando la bandeja esta
  llena; una gramatica que lo cambie rompe la valvula del techo.
- **`descartadas_semana` sigue caducando a la semana.** Lo que caduca es el
  recordatorio. La regla permanente es otro objeto y es otro spec.
- **El parser sigue siendo tolerante:** lo que no se entiende no gasta. Lo que
  cambia es que ademas deja rastro.
- **Los numeros los declara la perilla del jefe, no el modelo.**

## 12. Lo que queda abierto

1. **El prompt no tiene mundo** (seccion 2). Es el cuello de botella real.
2. **Sinonimos.** El catalogo es un paliativo, no una solucion. "Radar de
   precios" y "monitor de precios" siguen siendo dos familias si el modelo
   ignora el catalogo. **Sin verificar contra el modelo real.**
3. **`retorno_mm` sigue siendo copia de `presupuesto_mm`.** La vara que saldra
   de `promete` ordena por tipo de promesa, nunca por tamano.
4. **No esta verificado que el modelo local acierte cuatro renglones
   `clave: valor`.** Lo medido es el formato de dos renglones. Con la valvula
   puesta, fallar ya no es fatal, pero si es caro. La prueba minima esta en la
   seccion 13.

## 13. Como se verifica que funciona

**Unitario, sin modelo:**

- `normalizar` sobre la tabla de la seccion 5, incluidos los dos casos que
  fijan decisiones: los digitos se quedan (`7b` != `3b`), y `sobre: el` cae en
  la valvula.
- El parseo repara: orden cambiado, mayusculas, prefijos (`desc` ->
  `descartar`), `porque` ausente, renglon extra ignorado.
- El parseo NO repara lo ambiguo: `a` no matchea entre `ahorrar` y `acelerar`.
- Falta `sobre`, falta `promete`, `tarda` invalido -> valvula, no `nada`.
- La metrica y `semanas_max` derivan de la tabla, y `no se` da 4.
- `bus.alta` levanta con `forma` invalida y acepta un `preseed` sin `forma`.
- Una propuesta vieja sin `forma` se lee, se financia y se descarta.

**El bug de la semana congelada, con su propio test:** dos tics seguidos con la
misma respuesta ilegible tienen que producir dos entradas en `ilegibles.jsonl`
colapsadas en un aviso con contador 2, y **memoria escrita**, mientras que dos
tics de `nada` siguen sin escribir memoria. Ese par es el que fija la
distincion de la seccion 9.

**Con el modelo real, antes de encender una linea de produccion:** correr
`decision.prompt` con la plantilla nueva contra el modelo local 50 veces y
contar parseos, con la capa de reparacion puesta. No es un criterio de
aceptacion del codigo -- es la medicion que dice si la ficha es realista, y su
resultado puede mandar a cambiar la plantilla, no el parser.
