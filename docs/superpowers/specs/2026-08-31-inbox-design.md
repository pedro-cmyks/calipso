# El inbox

**Fecha:** 2026-08-31
**Estado:** aprobado por Pedro, listo para plan

## 1. Por que existe

Calipso ya tiene **cuatro** superficies donde algo le pide atencion a Pedro, y
ninguna se habla con las otras:

| | dónde | qué pide |
|---|---|---|
| **La mesa** | `calipso/web/fabrica/mesa.js` | financiar o descartar una propuesta |
| **Permisos** | `calipso/web/fabrica/permisos.js` | autorizar algo que no se deshace |
| **El bibliotecario** | `calipso/librarian.py`, UI vieja | curar una propuesta de memoria |
| **Las cartas** | `calipso/economia/cola.py` | atender un aviso del cierre semanal |

Las dos primeras viven en `/fabrica`, la tercera en `/`, la cuarta es una linea
de texto en `#avisos` que **no se refresca nunca**.

Y vienen mas. Pedro pidio un agente que le ayude a aplicar a trabajos (una
herramienta: la prende el) y otro que tenga su correo y su agenda (un empleado:
bucle propio, se despierta solo, aparece sin que lo llamen). El empleado es,
por definicion, algo que ocurre cuando Pedro no esta mirando.

**Pero el motivo de fondo no es el orden.** La atencion de Pedro es la divisa
mas escasa del sistema y esta contada de verdad: el pedro-token es una hora
firmable suya, se emite por semana y expira (`calipso/economia/pt.py`). El
analisis de la fabrica concluyo que el cuello de botella de toda la economia no
es la plata ni la capacidad: es **el despeje semanal de la bandeja**. El inbox
es el instrumento del recurso mas escaso que hay.

**Y hoy ese instrumento esta construido al reves.** Verificado, bandeja por
bandeja:

- **El "no" de la mesa dura una semana.** `calipso/plantel/situacion.py:107`:
  `if mio and datos.get("semana_descartada") == semana`. Al cambiar la semana el
  jefe deja de ver el descarte. El propio comentario (`situacion.py:99-106`)
  cuenta que sin ese recuerdo *"el mismo pedido volvia al tic siguiente -- a 200
  tics por semana, 200 veces"*.
- **El "si" permanente existe; el "no" permanente no.** `RESPUESTAS = ("si",
  "si_siempre", "no")` (`calipso/permisos/almacen.py:73`). El `si_siempre`
  escribe una regla (`almacen.conceder:204-235`); el `no` solo marca el item, no
  deja nada, y la proxima vez que aparezca esa forma vuelve a preguntar.
- **El `discard_reason` del bibliotecario se escribe y nadie lo lee.**
  `calipso/librarian.py:187`; grep en todo el repo: un solo hit, la escritura.

Consecuencia: **despejar la bandeja reabre al productor.** El techo de tres
propuestas (`calipso/plantel/jefe.py:20`) es lo unico que frena a un jefe;
financiar o descartar le libera el cupo; y la memoria del "no" caduca el lunes.
El despeje semanal **no reduce el flujo futuro: lo reinicia.** La unica palanca
que reduce items futuros en todo el sistema es `si_siempre`, y existe en una
sola de las cuatro bandejas y solo en la direccion del si.

Esta pieza es **una sola superficie con dos mitades**: la cinta (una lista, un
badge, un lugar donde contestar) y el aprendiz (toda respuesta puede dejar
regla, para que el inbox de la semana que viene sea mas chico).

## 2. Alcance

**Entra:**

- Una pestaña global de inbox en `/fabrica`, que lee las cuatro bandejas.
- El item unificado de ocho campos, con la accion **tipada por origen**.
- Las dos clases de item: **decision** y **aviso**.
- El alcance de la respuesta (`una vez` / `siempre`), incluido el `no_siempre`,
  que hoy no existe en ninguna bandeja.
- El almacen de reglas visible y revocable.
- El vencimiento del item como funcion pura, con reloj por origen.
- El badge sumando las cuatro fuentes.

**No entra:**

- **El aviso fuera de la pantalla.** No existe ningun camino: cero resultados de
  `Notification`, `webpush`, `showNotification`, `setAppBadge` en todo el repo, y
  `calipso/web/sw.js` tiene tres listeners (`install`, `activate`, `fetch`),
  ninguno es `push`. Es de cero a uno y se decide su forma en este spec, pero se
  construye despues. Ver seccion 9.
- **Los dos agentes nuevos** (trabajos, correo y agenda). El inbox es su
  superficie; ellos son piezas propias.
- **Jubilar la UI vieja.** Ver seccion 8.
- **Un almacen unico.** Cada bandeja sigue siendo dueña de sus datos.

## 3. El item unificado, y lo que NO se aplana

Ocho campos, y las cuatro bandejas ya los tienen hoy:

```
{id, origen, clase, ts, titulo, cuerpo, estado, respuesta}
```

- `origen`: `mesa` | `permisos` | `biblioteca` | `carta` (y despues `correo`,
  `agenda`, `trabajos`).
- `clase`: `decision` | `aviso`. Ver seccion 5.
- `cuerpo`: opaco, tipado por origen. El inbox no lo interpreta.
- `respuesta`: `{ts, verbo, alcance}` o `null`.

**Los ids ya son opacos, con prefijo propio y sin colision**: `<dep>-<hex8>`
(`calipso/server.py:5483`), `sol_<hex12>` (`calipso/permisos/almacen.py:111`),
`mem_<hex12>` (`calipso/librarian.py:119`). Una lista mezclada rutea la accion
por el prefijo, sin tabla de traduccion ni campo extra.

**Como lector no hace falta ningun endpoint nuevo.** Los tres GET ya devuelven
la bandeja entera en un objeto: `/api/economia/bus` (`server.py:3889`),
`/api/permisos` (`server.py:4469`), `/api/memory/inbox` (`server.py:3220`). El
unico que hoy no tiene lector es la cola de cartas (`/api/economia/cola`,
`server.py:3881`), sin ningun consumidor en `calipso/web`.

### Las tres cosas que no se aplanan

Aplanarlas seria el error del diseño:

1. **Financiar no es un "si": es un si-con-cuenta-pagadora.** Para un trabajo
   Pedro elige de que billetera sale (`mesa.js:11-26`); para un pre-seed no hay
   eleccion y el selector se reemplaza a proposito por "paga el tesoro"
   (`mesa.js:32-41`), porque ahi un selector seria un menu donde todas las
   opciones fallan.
2. **En permisos, "despues" no aplaza: prolonga un bloqueo global.** Mientras la
   solicitud este abierta, esa forma exacta no pasa por ningun chat, ningun
   departamento ni ningun techo nuevo (`calipso/permisos/motor.py:141-153`), y el
   chequeo va *antes* de clasificar justo para que subir el techo no sea un
   rodeo. Un boton generico de "recordamelo mañana" sobre un permiso es una
   trampa.
3. **En el bibliotecario el texto se edita antes de aceptar.** `update`
   (`librarian.py:136-150`): la respuesta no es si/no, es "si, pero asi". Y
   `scope` + `target` no son metadatos, eligen a que archivo va a parar.

### El reparto de responsabilidad

**El inbox es dueño de la lista**: que hay, en que orden, cuantos son, y que ya
contestaste. **Cada origen es dueño de sus verbos.** El inbox nunca dibuja un
boton que el origen no declaro.

Cada origen expone un descriptor:

```
{origen, verbos: [{nombre, etiqueta, alcances, parametros}], reloj, clase_por_defecto}
```

**El descriptor vive del lado del servidor, al lado de cada origen, y viaja con
la lista.** Si viviera en el cliente, el cliente tendria que saber que verbos
tiene cada bandeja -- o sea que volveriamos a centralizar en el inbox lo que
esta seccion acaba de repartir, y agregar un origen nuevo (correo, agenda,
trabajos) obligaria a tocar el inbox. Con el descriptor del lado del origen, el
inbox dibuja lo que le mandan y un origen nuevo no lo toca.

**La `clase` la declara el origen por item**, no el inbox: es el origen el unico
que sabe si algo esta detenido esperando o es solo una noticia. El
`clase_por_defecto` del descriptor es para los origenes que son siempre de una
clase -- las cuatro bandejas de hoy son todas `decision` y no necesitan
decidirlo item por item.

## 4. El aprendiz: toda respuesta puede dejar regla

Tres reglas:

1. **Toda respuesta se guarda con su alcance declarado**, `una vez` o `siempre`.
   No es un boton nuevo por bandeja: es un campo del item, y el origen declara
   que alcances acepta cada verbo.
2. **`no_siempre` existe.** Hoy no existe en ninguna de las cuatro, y es la
   unica mitad que le falta al sistema para poder encoger.
3. **Las reglas viven en un lugar visible y se pueden revocar.** Si no,
   "siempre" es una trampa: se dice que no una vez con sueño y se pierde algo
   para siempre sin saber donde apagarlo.

### Donde vive una regla

**Cada origen guarda sus propias reglas; el inbox guarda la vista.** No es un
reparto arbitrario: se sigue de que la regla tiene que filtrar en el productor.
El que sabe comparar "esta propuesta es la misma que Pedro ya rechazo" es el
jefe, no el inbox; el que sabe que dos solicitudes de permiso son la misma forma
es `permisos/motor.py`. Un almacen central de reglas obligaria al inbox a
entender el cuerpo de cada origen, que es exactamente lo que la seccion 3 le
prohibe.

Lo que si es unico es **la pantalla de reglas**: una lista de todo lo que hay
vigente, de cualquier origen, con su fecha y un boton de revocar. El inbox la
arma pidiendole a cada origen sus reglas, igual que arma la lista de items.

Consecuencia para el plan: `permisos` ya tiene su almacen y no se toca. La mesa
y el bibliotecario necesitan uno, y el molde a copiar es
`almacen.conceder:204-235`.

### La regla filtra en el productor, no en la pantalla

Es el detalle mecanico que hace que esto valga. Si la regla solo esconde el
item, el jefe igual quemo su cupo del techo de tres y la presion sigue puesta:
seria cambiar un inbox lleno por un inbox vacio con la misma fabrica pidiendo.
El `no_siempre` tiene que llegar hasta el que propone.

**La maquinaria ya existe en una de las cuatro.** `permisos` guarda reglas, las
compara por forma y las aplica **antes** de preguntar (`almacen.conceder:204-235`,
`motor.py:141-153`). No hay que inventar el mecanismo: hay que extenderlo a las
otras tres y darle la direccion del "no".

### El silencio no es una respuesta

**Vencer no es contestar.** Un item que vencio sale de la lista pero **no cuenta
como un "no"** y no deja regla. Si el silencio dejara regla, el aprendiz
aprenderia del cansancio de Pedro en vez de su criterio, y una semana ocupada le
enseñaria a decir que no a cosas que nunca miro.

Esto ya es la semantica de la mesa y hay que conservarla: vencer un pre-seed le
quita la reserva de cupo, pero el evento sigue en `alta` en el bus para siempre
(`calipso/economia/bus.py:583-591`). **Lo que vence es la presion, no el item.**

## 5. Decision y aviso

Las cuatro bandejas de hoy son todas decisiones: algo se detuvo y espera un
verbo. El empleado de correo rompe eso — muchas veces no hay nada esperando, hay
algo que conviene saber.

- **`decision`**: algo esta detenido. Cuenta para el badge.
- **`aviso`**: nada espera. No cuenta para el badge.

Sin esta distincion, con un empleado que mira la bandeja todo el dia el numero
no baja nunca y Pedro deja de mirarlo, **que es la unica forma real en que este
diseño fracasa.**

Nota verificada: **no existe ninguna nocion de "leido" o "visto" en todo el
repo.** El unico estado que baja un contador es *decidir*. Con las dos clases,
el badge deja de mentir sin necesidad de inventar "visto".

## 6. El alcance: el inbox es del sistema

Hay una asimetria real y verificada: el bibliotecario es **por proyecto**
(`librarian.py:33-35`, `CALIPSO_HOME/projects/<slug>/librarian/`), mientras que
permisos (`calipso/permisos/almacen.py:91`) y la economia
(`calipso/economia/pagador.py:60-66`) son **globales**. Si Pedro cambia de
proyecto, dos bandejas quedan igual y una cambia entera.

**El inbox es global.** Dos razones, y la segunda manda:

1. Lo escaso es la atencion de Pedro, y tiene una sola, este abierto el repo que
   este.
2. **Las fuentes nuevas no tienen proyecto en absoluto.** El correo no es de un
   proyecto. La agenda tampoco. Una postulacion tampoco. Si el inbox fuera del
   proyecto abierto, las tres cosas que motivaron esta pieza no tendrian donde
   aparecer.

El proyecto pasa a ser **una faceta del item**, no el ambito del inbox: un item
puede declarar de que proyecto es y filtrarse por eso -- como la mesa ya filtra
por departamento cuando Pedro toca un edificio en el mapa (`mesa.js:162-197`) --
pero el inbox no cambia de contenido al cambiar de repo.

## 7. El vencimiento: se copia la forma, no el reloj

Hoy solo vencen los pre-seed. Una propuesta de *trabajo* no vence jamas y ocupa
cupo para siempre; permisos no vence (grep de `venc|caduc|expir` en
`calipso/permisos/`: **cero**); el bibliotecario no vence; las cartas estan
exceptuadas a mano (`calipso/economia/cola.py:169-175`).

**La forma que se copia** es la de `bus.preseed_vencido` (`bus.py:574-643`): el
vencimiento es una **funcion pura del libro, recalculada en cada lectura**. El
docstring lo dice textual: *"quien lo dispara: nadie"*. No hay barrendero, no hay
cron, no hay evento. **No hay nada que encender, y por lo tanto nada que pueda
quedarse apagado** -- que es como mueren la mitad de los mecanismos de este
sistema.

**El reloj no se copia.** La mesa vence por **semanas operativas** y se niega
explicitamente a vencer por calendario (`bus.py:635-640`): *"hacer vencer aca
seria expirar por el paso del tiempo, que es justo lo que este techo se niega a
hacer"*. Es correcto para un pedido de plata contra una ventana de capital, e
inutil para un correo.

**Cada origen declara su reloj; el inbox declara la forma.**

## 8. Donde vive: `/fabrica`, pestaña global

**El repo no decide esto y no hay documento al que apelar.** Verificado: no
existe ningun plan de reemplazo de la UI vieja, y lo escrito dice lo contrario
tres veces (`docs/superpowers/specs/2026-08-25-mapa-rts-design.md:10` y `:164`,
`2026-08-26-mesa-de-pedro-design.md:220`). Es una congelacion tactica del 25 de
agosto, tomada para poder construir el mapa sin romper el IDE, que nunca se
reviso. **Queda abierta y es de Pedro.** Ver seccion 11.

Dicho eso, tres hechos verificados deciden esta pieza aunque esa pregunta siga
abierta:

1. **La UI vieja no funciona en el telefono, y no es opinion.** Unico `@media`
   en las 2.690 lineas de `calipso/web/index.html` es la linea 222, y es
   `prefers-reduced-motion`: **cero media queries de layout**. Tres columnas
   fijas con splitters de mouse. Un empleado que se despierta cuando Pedro no
   esta sentado en la compu no puede vivir en un inbox de escritorio.
2. **El molde ya esta ahi y en ningun otro lado.** `#panel-mesa` ya es un
   contenedor de bandejas con sub-pestañas
   (`calipso/web/fabrica/index.html:47-59`), y su badge en dos niveles (`:53` y
   `:65`) es **el unico mecanismo de "enterarse sin buscarlo" que existe en todo
   el sistema**.
3. **La costura corre en la direccion correcta.** El mount `/static` sirve todo
   el arbol web (`server.py:5889`) y ya hay precedente vivo: `index.html:580-582`
   importa `/static/fabrica/svg.js` como modulo. Un modulo de inbox escrito al
   estilo fabrica **se puede consumir desde la vieja; lo inverso no**. Construirlo
   en `/fabrica` no cierra la puerta de `/`; construirlo en `/` si cierra la de
   `/fabrica`.

**Pestaña global, no cuarta sub-pestaña de la mesa.** En telefono `#panel-mesa`
es una de tres pestañas y en escritorio la columna es `minmax(0,320px)`: meterlo
adentro serian tres niveles de pestañas anidados en la columna mas angosta. Y el
codigo ya trata el aviso como cosa de nivel superior -- el badge se pinta sobre
la pestaña global (`app.js:458-465`).

**La trampa, dicha en voz alta:** el costo empuja al lado equivocado. La ultima
vista de la vieja (Plugins, `1f4debc`) costo **93 lineas, un archivo, cero
tests**; la ultima de la fabrica (permisos, `1793f79`) costo **745 lineas en 6
archivos**, 313 de ellas de test. La opcion barata y la correcta apuntan a lados
opuestos: si nadie decide a proposito, esto termina en la vieja por gravedad.

## 9. El aviso fuera de la pantalla: forma decidida, construccion despues

**No existe ningun camino.** Verificado por grep sobre `.py/.js/.html/.json`:
cero resultados de `Notification|webpush|pywebpush|showNotification|requestPermission|setAppBadge`.
`calipso/web/sw.js` tiene tres listeners: `install` (:28), `activate` (:33),
`fetch` (:40). **La PWA se instala y es muda.**

La forma que queda decidida, para que el inbox no haya que rehacerlo:

- El inbox publica su cuenta de decisiones pendientes por el **pulso**
  (`calipso/mapa/pulso.py`), que ya es el canal vivo del sistema.
- El aviso fuera de pantalla es un **consumidor mas** de esa cuenta, no una
  ruta paralela. Cuando se construya, no toca el inbox.
- Solo la clase `decision` genera aviso. Un `aviso` nunca despierta a Pedro.

## 10. Invariantes que no se tocan

- **Cada bandeja sigue siendo dueña de sus datos.** El inbox lee y despacha; no
  migra almacenes. El bus sigue append-only, permisos sigue con su escritura
  atomica y su candado, el bibliotecario sigue donde esta.
- **La pared de permisos no se afloja.** Mientras una solicitud este abierta, esa
  forma no pasa por ningun lado. El inbox no ofrece "despues" sobre permisos.
- **El item vencido no deja regla.**
- **El inbox no dibuja un verbo que el origen no declaro.**
- **`si_siempre` sigue siendo revocable**, y `no_siempre` nace revocable.

## 11. Lo que queda abierto, y es de Pedro

1. **Si `/fabrica` reemplaza a `/` o conviven.** No hay documento al que apelar y
   no lo puede contestar el repo. Esta pieza no depende de la respuesta -- se
   construye en `/fabrica` en los dos casos -- pero la respuesta cambia cuanto
   vale consolidar el resto.
2. **El freno del productor.** De las cuatro bandejas, **solo una tiene techo**
   (`TECHO_PROPUESTAS = 3`, por departamento). Permisos no tiene, el bibliotecario
   no tiene, las cartas no tienen, y el empleado de correo -- que es el que mas
   volumen va a traer -- tampoco. El vencimiento y el `no_siempre` ayudan, pero el
   dia que una fuente sin techo se desboque, el inbox no tiene con que frenarla.
   Hace falta decidir si el techo es por origen, global, o no existe.

## 12. Como se verifica que funciona

- Las cuatro bandejas aparecen en una lista y cada una conserva sus verbos
  exactos: financiar sigue pidiendo cuenta pagadora, el bibliotecario sigue
  dejando editar el texto, permisos sigue sin ofrecer "despues".
- Un `no_siempre` sobre una propuesta de la mesa hace que el jefe **no la vuelva
  a proponer al tic siguiente** -- y se comprueba en el productor, no en la
  pantalla.
- Un item vencido desaparece de la lista y **no** deja regla.
- El badge cuenta decisiones y no avisos.
- Cambiar de proyecto no cambia el contenido del inbox.
- Revocar una regla hace volver a aparecer lo que esa regla escondia.
