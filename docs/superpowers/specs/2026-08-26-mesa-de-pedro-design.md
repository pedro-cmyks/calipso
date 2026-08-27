# La mesa de Pedro

**Fecha:** 2026-08-26
**Estado:** aprobado por Pedro, listo para plan

## 1. Por que existe

El plantel ya funciona: cada departamento tiene un jefe que despierta como
rutina, decide con un modelo local, y deja propuestas en el bus. Verificado
corriendo: tres tics produjeron tres altas sin que nadie le hablara al
departamento.

Pero nadie consume esas propuestas. `bus.financiar` no tiene ningun llamador
de produccion — solo tests. Y el jefe tiene un techo de tres propuestas sin
financiar (`jefe.py`, `TECHO_PROPUESTAS`). O sea que **cada departamento
propone tres veces y se frena para siempre**: con una rutina diaria, la
fabrica se apaga sola al cuarto dia.

La causa de fondo es mas chica de lo que parece. El bus solo conoce una
transicion desde `alta`:

    _TRANSICIONES = {"alta": frozenset({"financiada"}), ...}

No existe ninguna forma de descartar una propuesta. Una vez que tres se
acumulan, la unica salida es editar `bus.jsonl` a mano.

Esta pieza es la superficie donde Pedro ve lo que sus departamentos
propusieron y decide: financiar, descartar, o dejar para despues. Mas los
controles del plantel, para que apagarlo no exija una terminal.

## 2. Alcance

**Entra:**

- La transicion `alta -> descartada` en el bus.
- Tres endpoints: leer el bus, financiar, descartar.
- La mesa en `/fabrica`: una fila por propuesta, con sus dos acciones.
- La tira de controles del plantel: parar, reanudar, modo, y el formulario
  para crear la rutina de un departamento.
- Un enlace de `/` a `/fabrica`, que hoy no existe.

**No entra, a proposito:**

- **Matar una propuesta ya financiada.** Ahi hay plata en `trabajo:<id>` y el
  reparto proporcional correcto ya lo hace `evaluar_y_liquidar_muertos` en el
  cierre semanal. Duplicar esa logica en un boton es el doble de trabajo para
  algo que el sistema ya resuelve solo.
- **Cofinanciacion.** El libro la permite (financiar algo ya `financiada` es
  legal), pero la mesa no la expone. Ver seccion 6.2: es tambien lo que hace
  seguro el doble toque.
- **Que Pedro financie con su cuenta personal.** Tocaria la separacion entre
  la zona fabrica y la personal, que es una invariante deliberada.
- **Ejecutar el trabajo.** `trabajar` sigue siendo no-op. Es la frontera de
  salida, y es otro spec.

## 3. La transicion que falta

En `calipso/economia/bus.py`:

- `_TRANSICIONES["alta"]` pasa a ser `frozenset({"financiada", "descartada"})`.
- `"descartada"` **no** tiene entrada propia en `_TRANSICIONES`: es terminal,
  igual que `liquidada`.
- Una funcion nueva:

      def descartar(bus: Bus, ts: str, semana: str, id: str) -> None:
          """Pedro dice que no. No hay plata que devolver: nada se transfiere
          a trabajo:<id> hasta que alguien financia."""

  Su cuerpo es `bus.marcar(ts, semana, id, "descartada")` y nada mas.

**Por que no se reusa `muerta`:** mezclaria "nunca arranco" con "arranco y
fracaso", y el criterio de muerte lee `datos["semana_financiada"]`, una clave
que una propuesta en `alta` no tiene.

**Por que es terminal:** en un log append-only, "deshacer" es un estado mas y
una regla mas. Si hace falta una red, que la pida el boton, no el modelo de
estados.

**El plantel no se toca.** `situacion.py` ya filtra
`estado not in ("alta", "financiada")`, asi que una propuesta descartada
desaparece sola de `propuestas_propias` y el techo del jefe se destraba solo.
Esto hay que verificarlo con un test, no darlo por sentado.

## 4. Los endpoints

Convenciones del archivo que hay que respetar: bodies con Pydantic
`BaseModel` (es el 100% de los endpoints de economia), auth por el middleware
`auth_guard` (no hay decoradores por endpoint), y **el candado siempre sobre
`ruta_libro`**, nunca sobre `ruta_bus`, aunque el archivo que se escriba sea
`bus.jsonl`.

### 4.1 `GET /api/economia/bus`

Lector serializado: se toma `_eco_candado(p0.ruta_libro)` y se construye el
estado adentro. El libro se repara truncando, asi que leerlo a medio append
se come un asiento — esto ya destruyo el libro entero una vez en esta rama.
El patron bueno es `/api/economia/tablero`; `/api/economia/cola` es el unico
lector sin candado del archivo y **no se copia**.

Devuelve:

    {
      "activa": true,
      "semana": "2026-W35",
      "semana_abierta": true,
      "propuestas": [
        {"id": "atlas-6ef6e902",
         "estado": "alta",
         "departamento": "dep:atlas",
         "titulo": "...",
         "presupuesto_mm": 10000,
         "retorno_mm": 10000,
         "criterio": {"gasto_max_mm": 10000, "semanas_max": 4},
         "gastado_mm": 0,
         "aportes": {"dep:atlas": 10000}}
      ],
      "departamentos": [
        {"cuenta": "dep:atlas", "nombre": "atlas", "zona": "fabrica",
         "disponible_mm": 400000}
      ]
    }

- `propuestas` sale de plegar `bus.ids()` con `estado()`, `datos()`,
  `gastado(asientos, id)` y `aportes(asientos, id)`.
- Se devuelven las propuestas en `alta` y en `financiada`. Las `descartada`,
  `muerta` y `liquidada` no: la mesa es para decidir, no un historial.
- `departamentos` sale de `registro.todos()`, **filtrado a
  `zona == ZONA_FABRICA`**, porque el libro rechaza cualquier otro
  financiador. Su `disponible_mm` es lo que decide si el boton puede pagar.
- `activa: false` cuando no hay pagador, igual que el resto de economia.

### 4.2 `POST /api/economia/bus/{id}/financiar`

Body: `{"cuenta": "dep:atlas", "mm": 10000}`.

Llama, bajo el candado y con el estado construido adentro:

    bus.financiar(mercado, bus, ts, semana, id, cuenta, mm)

**Solo acepta propuestas en estado `alta`.** Si el estado es otro, 400. Esto
es deliberado y hace dos cosas: cierra la duplicacion por doble toque
(seccion 6.2) y mantiene la cofinanciacion fuera del alcance.

### 4.3 `POST /api/economia/bus/{id}/descartar`

Sin body. Llama `bus.descartar(bus, ts, semana, id)` bajo el candado. Solo
acepta propuestas en `alta`; si no, 400.

### 4.4 Los errores

`ErrorBus` y `OperacionInvalida` se traducen a **400 con el mensaje del
error**. Hoy ningun endpoint de economia tiene try/except y todo propaga como
500 opaco, lo cual esta bien mientras el unico lector es un test — pero esta
es la primera pantalla de economia cuyos errores los lee un humano, y los va
a leer seguido: "semana no operativa" y "sin saldo" son mensajes utiles.

`SinSaldo` tambien se traduce a 400.

Las validaciones que puede levantar `financiar`, en el orden en que las
evalua: id inexistente o estado no financiable, financiador no registrado,
financiador fuera de la zona fabrica, semana no operativa, dueno congelado,
financiador congelado.

## 5. La mesa

Vive en `/fabrica`, que es donde ya vive la economia, es la unica UI
responsive del proyecto, y tiene su PWA y su suite de tests con `node --test`.

### 5.1 Estructura

Un modulo nuevo `calipso/web/fabrica/mesa.js`, siguiendo el patron de
`paneles.js`:

- Una funcion pura `textoDeMesa(datos)` que devuelve un string de HTML, con su
  `mesa.test.js` al lado. La logica de armado se prueba sin browser.
- `escapar()` en **todo** lo que entre por `innerHTML`. El titulo de una
  propuesta lo escribe un modelo local: es entrada no confiable.
- Delegacion por `data-accion` con un solo listener en el contenedor.
- Conversion de milimonedas a monedas como ya lo hace `ciudad.js`.
- Una `grid-area` en `estilo.css` y su rama en el media query de 820px.
- **El archivo nuevo entra al array `SHELL` de `sw.js`**, o no existe offline.

### 5.2 Una fila de propuesta

    atlas · radar de precios de la competencia
    10 monedas · sin gastar
    paga: [atlas ▾]   [financiar]  [descartar]

- El selector lista los departamentos de la zona fabrica, con el dueno
  seleccionado por default.
- Un departamento cuyo `disponible_mm` es menor al presupuesto se muestra
  igual pero anotado, para que se entienda por que va a fallar.
- Las propuestas en `financiada` se muestran sin botones, con lo gastado.

### 5.3 Los botones

- Se deshabilitan mientras la peticion esta en vuelo y se rehabilitan al
  terminar.
- Todo `fetch` chequea `r.ok` y, en el error, lee `{"detail": ...}` y lo
  muestra. El loader canonico a imitar es `loadSubscriptions` de
  `index.html`; **`loadRoutines` no**, que no mira `r.ok` ni lee la respuesta
  del PUT, y hace que un 500 se vea igual que "no hay nada".
- Despues de una accion exitosa se refresca la lista.

### 5.4 La tira del plantel

Arriba de la mesa:

- Estado actual (encendido/apagado, modo) leido de `GET /api/plantel`.
- Botones parar / reanudar.
- Un selector de modo: ensayo / vivo. Con una advertencia visible al pasar a
  vivo, porque es el momento en que la fabrica empieza a gastar sola.
- Un formulario chico para crear la rutina de un departamento: cuenta,
  etiqueta, intervalo en minutos. Manda `POST /api/routines` con
  `kind: "departamento"`.

### 5.5 El enlace que falta

Hoy no hay un solo enlace entre `/` y `/fabrica`. Se agrega **una linea** en
`index.html`: un enlace a `/fabrica`. Es la unica modificacion permitida a la
UI vieja.

## 6. Las trampas, y como se resuelven

### 6.1 La semana cerrada

Si la semana no tiene una emision de PT, `financiar` falla **siempre**, y
nadie llama `POST /api/economia/abrir` automaticamente. Probado a mano, esto
es lo primero que revienta, y hoy con un 500 opaco.

`GET /api/economia/bus` devuelve `semana_abierta`. Cuando es falso, la mesa lo
dice y ofrece el boton para abrir la semana, en vez de dejar a Pedro contra un
error incomprensible.

### 6.2 El doble toque duplica la plata

`financiar` escribe la transferencia y despues la marca. Bajo el candado no
hay carrera entre procesos, pero **financiar algo ya `financiada` es legal**
(es cofinanciacion), asi que dos toques en un telefono con conexion lenta
pagan dos veces.

Se cierra por construccion: el endpoint solo acepta propuestas en `alta`. El
segundo toque encuentra `financiada` y recibe un 400. La deshabilitacion del
boton en la UI es la segunda linea de defensa, no la primera.

### 6.3 `marcar` es publica y no pide plata

Si el endpoint llamara `marcar(..., "financiada")` en vez de `financiar`, la
propuesta quedaria financiada con `trabajo:<id>` en cero, y despues el cierre
la mataria con `aportes={}` dejando cualquier saldo posterior varado. Los
tests del repo usan `marcar` crudo; **no son un ejemplo de produccion**.

### 6.4 `liquidar` no es lo que parece

La unica `def liquidar` es `Kernel.liquidar`, que liquida una **cuenta** de
departamento y manda el remanente al tesoro. Llamada con `trabajo:<id>`
funciona y le roba la plata a los financiadores — lo contrario de
`evaluar_y_liquidar_muertos`, que la devuelve prorrateada. Nada de esta pieza
la llama.

### 6.5 `gastado()` despues de liquidar

`gastado()` suma todo lo que sale de `trabajo:<id>`, incluidas las
devoluciones de liquidacion. Sirve mientras la propuesta esta viva; despues de
liquidar, el numero miente. La mesa solo muestra propuestas vivas, asi que no
la toca — pero no hay que reusar ese numero en otro contexto sin saberlo.

## 7. Invariantes que no se tocan

1. **Decidir es gratis.** Nada de esta pieza llama a un modelo.
2. **La zona fabrica y la personal siguen separadas.** El financiador tiene
   que ser un departamento registrado en `ZONA_FABRICA`. Pedro no financia
   directo.
3. **El libro es append-only y con escritor unico.** Toda lectura y toda
   escritura del bus pasan por el candado sobre `ruta_libro`.
4. **El reparto proporcional al morir sigue siendo del cierre semanal.** Esta
   pieza no mata propuestas financiadas.

## 8. Tests

- **`bus.descartar`**: `alta -> descartada` es legal; desde `financiada` o
  desde `descartada` no lo es; el libro no se mueve al descartar.
- **El techo del jefe se destraba**: con tres propuestas en `alta` el jefe
  esta frenado; al descartar una, vuelve a poder proponer. Es la razon de ser
  de todo esto y necesita su propio test.
- **Los endpoints**: el 400 traducido de `ErrorBus`; financiar solo desde
  `alta`; el segundo financiar rechazado; descartar solo desde `alta`; el
  lector bajo candado (hay un test espia del candado en
  `test_plantel_server.py` que sirve de molde).
- **`mesa.js`**: la funcion pura, incluido el escapado de un titulo con HTML
  adentro, y el caso de la lista vacia.
- **El `SHELL` de `sw.js`** incluye el archivo nuevo — el test existente se
  deriva de los archivos reales del directorio, asi que hay que sumarlo.
- La suite de `/fabrica` corre con `node --test` y tiene un piso de tests que
  no puede bajar.

## 9. Como se verifica que funciona

No alcanza con los tests. Al terminar, con el server real y Ollama real:

1. Abrir `/fabrica` en un browser y ver la mesa con las propuestas que el
   jefe dejo.
2. Poner el plantel en vivo desde la tira, correr la rutina de un
   departamento, y ver aparecer una propuesta nueva en la mesa sin recargar a
   mano.
3. Apretar **financiar** y verificar en el libro que se movio plata: la
   cuenta del financiador baja y `trabajo:<id>` sube, con los asientos
   correspondientes.
4. Apretar **descartar** en otra, y verificar que el jefe vuelve a poder
   proponer — que es el problema que motivo la pieza.
5. Apretar **parar** y confirmar que el siguiente tic no hace nada.

## 10. Lo que sigue despues

En orden, y fuera de este spec:

1. **Ejecutar el trabajo** (seccion 4.3 del spec del plantel): que `trabajar`
   contrate un equipo efimero y lo pague. Es lo que cierra el ciclo completo
   y lo que hace que la agresividad tenga algo que medir.
2. **La identidad del departamento**: nadie escribe el `core/` de un
   departamento, asi que su memoria curada esta vacia para siempre y las
   propuestas salen genericas y parecidas entre si.
3. **Matar una financiada a mano**, con el reparto proporcional.
