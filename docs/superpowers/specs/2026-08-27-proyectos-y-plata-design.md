# Proyectos, departamentos y las tres bolsas de plata

**Fecha:** 2026-08-27
**Estado:** diseño. Las decisiones de Pedro citadas en la sección 2 son autoridad
y no se reinterpretan. Todo lo demás es decisión de este documento y espera su
revisión.

---

## 1. Por qué existe este spec

Hoy la fábrica sabe **cuánta plata tiene cada billetera** y no sabe **para qué se
gastó**. Son dos huecos concretos, los dos verificados:

- Un `Departamento` es nombre, zona y cuatro perillas numéricas
  (`calipso/economia/departamentos.py:27-34`). Nada declara de qué es capaz.
  `legal` e `I&D` serían el mismo código con distinto nombre y distinta
  billetera.
- Cuando `legal` trabaja para Atlas, el asiento no puede decir las dos cosas a la
  vez. O el gasto sale de `trabajo:<id>` y no dice qué departamento lo hizo, o
  sale de `dep:legal` y no dice para qué proyecto fue. **El nexo no existe.**

Y Atlas, que es el ejemplo que Pedro usa para todo, hoy está modelado como
departamento (`test_mesa_server.py:32`, `test_plantel_situacion.py:39`,
`test_mapa_acoplamiento.py:87`). Pedro dice que no lo es.

Hay una ventana que se cierra: `~/.calipso/economia/` **no existe** (verificado:
`ls ~/.calipso` no lo tiene; `pagador.py:58-66` devuelve `None` sin sus tres
archivos). No hay libro que migrar, ni un asiento pasado que reinterpretar. Es la
última oportunidad para que el modelo nazca bien en vez de arreglarse después
contra un libro append-only que no se puede reescribir.

---

## 2. Lo que decidió Pedro

Estas líneas son la autoridad de este spec. Se citan textuales.

1. **Los departamentos son los de una fábrica de verdad, y son "para la
   autonomía":** uno de *"direcion o cerebro donde llega todo y ahi esta calipso
   como tal y su memoria centralizada"*, uno de *"markert resarh"*, uno *"de
   legal o algo asi"*, uno *"de I&D y asi"*.
2. **Atlas no es un departamento:** *"atlas donde iria, que es atlas? un proyecto
   con entregables y demas, que necesita de varios otros departamentos
   (publicar, testing, marketing, resarch, development)"*.
3. **Quién gasta y quién reporta:** *"yo creo que gastan los departamentos y
   reportan para que proyecto estan gastando"*.
4. **Quién tiene la plata:** *"y creo que el proyecto es el que tiene presupuesto
   y los departamentos gastan"*.
5. **Tres bolsas:** *"el tesoro, que es lo que va a las finanzas"*, *"lo que
   calipso ya tiene que es el presupuesto de gasto que son los de las
   suscripciones los apis y las otras cosas que quiera comprar"* y *"mis
   horas"*. Y: *"las monedas salen del tesoro, donde voy a llevar un banco con mi
   plata ingresos y egresos para hacer analisis financieros mios o que calipso
   tambien tenga ese contexto"*.
6. **Dos ideas de interfaz:** que la lista de chats de la izquierda esté separada
   en secciones por proyecto; y que al hacer click en un departamento del mapa
   la mesa muestre los proyectos que están usando ese departamento y qué
   recursos están usando. Dijo que podía ser una mezcla de las dos.

La sección 9 toma la sexta al pie de la letra: la mezcla no es un compromiso
estético, es lo que hace que el nexo de la sección 7 funcione solo.

---

## 3. Qué es un proyecto

### 3.1 La definición

Un proyecto es **una cuenta del libro con un objetivo y una fecha de cierre**.
Tiene plata propia, entregables, y una lista de departamentos que puede usar. No
tiene plantel, no tiene jefe, no despierta, no propone y no decide nada. Todo eso
lo hacen los departamentos.

La regla corta: **el proyecto tiene la plata y el objetivo; el departamento tiene
la gente y la capacidad.**

### 3.2 Dónde vive y qué campos tiene

Un archivo nuevo, `~/.calipso/economia/proyectos.json`, con la misma disciplina
exacta que `departamentos.json` (`departamentos.py:48-81`): **el registro guarda
configuración, nunca estado.** El saldo se pliega del libro
(`balances.py:18-27`), como todo lo demás.

```
"atlas": {
  "nombre": "Atlas",
  "zona": "fabrica",
  "repo_path": "/home/pedro/Observatory-Global",
  "departamentos": ["cerebro", "research", "development",
                    "testing", "marketing"],
  "abierto_en": "2026-W35"
}
```

- **`zona`**: `fabrica` o `personal`, mismo vocabulario que
  `departamentos.py:19-20`. En este spec todos los proyectos son de zona
  fábrica; ver sección 11.
- **`repo_path`**: el puente con los chats. Un chat cuyo `project_path`
  (`chats.py:81`) cae bajo este `repo_path` pertenece a este proyecto. Es lo que
  hace posible la vista A de la sección 9.1.
- **`departamentos`**: la lista de departamentos habilitados a gastarle. No es
  decoración: es la compuerta de la sección 7.1.
- **No hay campo `estado`.** El cierre de un proyecto es un apunte del libro,
  exactamente como la quiebra de un departamento
  (`departamentos.py:84-97` para el pliegue, `:100-102` para la escritura). Un
  registro que guardara "cerrado" sería estado guardado, y el modelo entero está
  construido sobre no guardar estado.

La cuenta del proyecto es **`proyecto:<slug>`**. `atlas` da `proyecto:atlas`.

### 3.3 Ciclo de vida

| paso | qué pasa en el libro | quién lo dispara |
|---|---|---|
| **alta** | nada. Solo entra la línea en `proyectos.json`. | Pedro, desde la mesa |
| **presupuesto** | transferencia `tesoro -> proyecto:<slug>`, motivo `presupuesto_proyecto` | Pedro, desde la mesa |
| **gasto** | el proyecto paga (sección 4) y el saldo baja | los departamentos |
| **venta** | acuñación subtipo `venta` con destino `proyecto:<slug>` (sección 8.5) | Pedro, en la frontera |
| **cierre** | apunte `{"nota": "cierre_proyecto", "proyecto": "proyecto:<slug>"}` más la liquidación | Pedro, desde la mesa |

Dos decisiones sobre esta tabla:

**El presupuesto de un proyecto no se recarga solo.** El de un departamento sí:
`presupuesto_semanal_mm` (`departamentos.py:31`) se paga entero cada cierre
semanal (`cierre.py:91-115`). El del proyecto no. Se carga por un acto explícito
y baja hasta cero. La razón es la razón entera de la sección 4: un presupuesto
que se rellena solo nunca llega a cero, y "cuánto le queda a Atlas" deja de ser
un número que signifique algo. El departamento tiene un sueldo; el proyecto tiene
una plata.

**El presupuesto de proyecto pasa por el mandato de dirección.** Mismo umbral
acumulado por semana que ya existe para departamentos
(`direccion.asignado_semana`, `direccion.py:25-30`, contra
`UMBRAL_MANDATO_MM = 100_000`, `direccion.py:18`), y por encima exige firma
(compuerta d de la invariante 5). Un proyecto no es una puerta trasera al tesoro.

**El cierre de un proyecto es el primer llamador de `Kernel.liquidar`.** Esa
función está escrita, testeada y no la llama nadie (`kernel.py:141-157`). Hace
exactamente lo que hace falta y en el orden correcto: libera las reservas
activas de la cuenta, paga las acreencias pendientes por prelación, y barre el
resto al tesoro con motivo `liquidacion_remanente`. Cerrar un proyecto es
llamarla con `proyecto:<slug>` y apilar el apunte.

### 3.4 Proyecto y trabajo del bus: agrupa, no reemplaza

**Decidido: el proyecto agrupa trabajos. No los reemplaza.** Un proyecto tiene
muchos trabajos; un trabajo tiene exactamente cero o un proyecto.

Tres razones, todas verificables:

1. La cuenta `trabajo:<id>` es lo que hace funcionar el criterio de muerte y la
   liquidación proporcional entre financiadores (`bus.py:180-232`). Es el único
   mecanismo del sistema que **cierra una exploración sola**. Disolverlo dentro
   del proyecto lo mata.
2. El bus es donde Pedro decide (spec de la mesa,
   `docs/superpowers/specs/2026-08-26-mesa-de-pedro-design.md`). Un proyecto no
   es una decisión, es un contenedor: no tiene sentido "financiar o descartar"
   un proyecto propuesta por propuesta.
3. Tienen vidas distintas. Un trabajo muere por `semanas_max` o `gasto_max_mm`
   (`bus.py:19`, `:189-193`); un proyecto dura lo que dura el objetivo. Dos
   vidas distintas son dos objetos distintos.

Lo que cambia en el bus: el evento `alta` (`bus.py:70-73`) gana una clave
`proyecto`. Los eventos viejos sin ella se leen con `.get()` y default vacío,
que es la disciplina que el server ya usa contra el bus real de Pedro
(`server.py:3516-3528`). Un trabajo sin proyecto es legítimo: es trabajo interno
del departamento.

Y el financiador de un trabajo pasa a poder ser un proyecto. Hoy
`bus.financiar` exige un departamento de fábrica registrado
(`bus.py:116-123`). Es la segunda de las dos compuertas que este spec abre; la
otra está en la sección 4.

---

## 4. La cuenta que paga es `proyecto:atlas`, y qué cuesta

**Decidido: cuando un departamento gasta para un proyecto, quien paga es
`proyecto:<slug>` directo.**

La alternativa era que el proyecto le transfiriera al departamento y el
departamento gastara de lo suyo con una etiqueta de proyecto en el detalle. Esa
alternativa **no rompe ninguna invariante**: el pagador sigue siendo un
departamento registrado y `mercado._politica` (`mercado.py:70-88`) no se toca.

Se descarta igual, por una razón sola: mezcla la plata de varios proyectos en una
misma billetera. Si `dep:development` tiene 400 monedas y trabaja para Atlas,
para OpenMontage y para Calipso, "cuánto le queda a Atlas" deja de ser un saldo y
pasa a ser una resta hecha a mano sobre etiquetas — un número derivado, que puede
discrepar del libro, que nadie puede mirar bajar, y que no frena nada cuando se
acaba.

Con la cuenta directa, en cambio, "cuánto le queda a Atlas" es
`disponible(asientos, "proyecto:atlas", MONEDA)` (`balances.py:41-46`): un
número real y propio del proyecto, no una resta hecha a mano sobre etiquetas.

**Lo que ese número NO hace es frenar nada en el momento, y hay que decirlo
así de directo porque este spec lo afirmó y es falso.** `Kernel._exigir`
(`kernel.py:35-38`) protege el libro —ninguna cuenta queda en negativo,
invariante 7— pero el cobro de un turno de chat es posterior a la respuesta,
no previo a ella: es el paso 4 del turno, después de que el modelo ya
contestó (`server.py:2496`, `:2507`). Cuando `_exigir` rechaza el gasto y
levanta `SinSaldo` (`kernel.py:20`, hereda de `OperacionInvalida`,
`kernel.py:16`), esa excepción no llega a Pedro: la atrapa
`Pagador._cobrar` (`pagador.py:141-146`) y la apila en
`cargos_pendientes.jsonl`, y `_cobrar_turno` (`server.py:4169-4188`) se traga
cualquier excepción —de esa familia o de cualquier otra— y devuelve 0, con un
comentario que dice que el cobro es contabilidad y no puede dejar a Pedro sin
respuesta. La invariante 7 protege el libro, no la tarjeta de Pedro. Qué pasa
de verdad cuando la plata se acaba es una política aparte, y la cierra Pedro
más abajo.

### El costo, explícito

Hay que abrir **dos compuertas**, no una. Las dos preguntan lo mismo escrito en
dos lugares distintos:

1. **`mercado._politica`** (`mercado.py:70-88`). Hoy resuelve el departamento
   contra el que se evalúan las políticas así: si el pagador empieza con
   `trabajo:` exige un `dueno` explícito y lo resuelve con `dep_por_cuenta`
   (`mercado.py:77-81`); si no, exige que **el pagador mismo** sea un
   departamento registrado (`mercado.py:82`), vía `dep_por_cuenta`
   (`mercado.py:44-48`), que revienta con cualquier cuenta que no esté en el
   Registro. Pasa a tratar a `proyecto:<slug>` igual que a `trabajo:<id>`: pagador
   que no es departamento, `dueno` explícito y obligatorio, políticas del dueño.
2. **`bus.financiar`** (`bus.py:116-123`). Mismo cambio, misma razón: un proyecto
   puede financiar una propuesta de un departamento habilitado.

### Lo que la apertura NO significa

La invariante 12 dice *"la zona personal no compite en el mercado interno"*. Ese
contenido **no cambia**. Lo que cambia es su implementación, que hoy confunde dos
preguntas en una: `mercado.py:83-86` chequea `dep.zona != ZONA_FABRICA` sobre el
departamento que resolvió, y para llegar ahí `_politica` obligó al pagador a ser
un departamento. Separadas, quedan así:

- **quién puede pagar**: un departamento de fábrica registrado, un `trabajo:<id>`
  del bus, o un `proyecto:<slug>` **de zona fábrica y activo**;
- **contra quién se evalúan las políticas** (zona, congelado, techo de API): el
  `dueno`, que sigue siendo siempre un departamento de fábrica registrado.

Un proyecto de zona personal no paga desde el libro de la fábrica: colapsa a la
cuenta `personal` igual que hoy hace `ficha.cuenta_pagadora`
(`mapa/ficha.py:41-52`), y su uso queda fuera del libro de la fábrica, en
`calipso/costs.py`.

### Una validación nueva que hoy no existe

Las cuentas nacen al ser nombradas (`balances.py:18-27`) y `Asiento.validar` no
valida nombres de cuenta (`tipos.py:71-121`). Con eso, un typo del tipo
`proyecto:atals` en un **gasto** lo frena `_exigir` (saldo 0), pero un typo en un
**presupuesto** entierra plata en una cuenta fantasma para siempre.

Por eso el destino de un `presupuesto_proyecto` se valida contra el registro de
proyectos antes del append, exactamente como `direccion.asignar_presupuesto` ya
valida el departamento con `mercado.dep_por_cuenta(dep_cuenta)`
(`direccion.py:36`). La validación vive en la compuerta, no en el tipo — ver
sección 10.

### Qué pasa cuando el saldo se agota

Pedro contestó esto el 2026-08-27, distinguiendo por tipo de saldo, palabra
por palabra: *"pues para la 1 depende de que tipo de saldo, si es una
suscripcion y usa mas de lo que pensao pues si, ok, pero si es plata que esta
gastando y la perido ahi si lanza una alerta y lo reviso yo a ver que paso
entonces entro a habalr con calipso sobre el caso"*. No pidió un corte duro.
Pidió que no se pierda en silencio.

La distinción que traza es la que la economía ya tiene escrita en el código,
aunque hoy los dos casos se comporten exactamente igual cuando fallan.
`_cobrar_turno` (`server.py:4151-4188`) ya separa las dos rutas por nombre:
`route == "api"` llama a `pagador.cargar_api`, que cobra en monedas reales;
`route in ("subscription", "local")` llama a `pagador.cargar_suscripcion`, que
consume unidades de capacidad prepaga (`server.py:4169-4182`). Es exactamente
la frontera hundido/marginal:

- **suscripción = costo hundido.** Ya está pagada; una unidad de más no le
  cuesta un peso extra a Pedro.
- **API = costo marginal.** Es plata que sale de verdad y se pierde si el
  cargo no se aplica.

Pero cuando cualquiera de las dos falla, hoy caen en el mismo lugar sin
distinción: las dos pasan por `Pagador._cobrar` (`pagador.py:141-146`), las
dos se atrapan como `_ERRORES_ECONOMICOS` (`pagador.py:42-43`) y las dos se
apilan en `cargos_pendientes.jsonl` (`pagador.py:86-89`) sin que nadie se
entere.

**Capacidad de suscripción agotada: sigue, sin alerta — pero no porque se
recupere sola.** `comprar_capacidad` (`mercado.py:91-117`) rechaza con "cuota
agotada" (`mercado.py:101-103`) cuando el consumo del ciclo supera
`sus.capacidad_fabrica`, y el cargo queda en `cargos_pendientes.jsonl`. Hasta
acá es igual al caso de API. La diferencia está en qué pasa después, y ahí hay
que corregir algo: `reintentar_pendientes` (`pagador.py:98-116`) tiene un
único llamador de producción, `api_eco_cierre` (`server.py:3676-3687`), y ese
endpoint **no tiene un solo llamador de producción propio** — ver el hallazgo
en la sección 11. Hoy un cargo de suscripción pendiente no "se reintenta
solo": queda muerto en `cargos_pendientes.jsonl` para siempre, igual que
cualquier otro pendiente.

Con eso, la conclusión de que no amerita alerta se sostiene igual, pero por
otra razón. Lo que hay detrás de un cargo de capacidad es una transferencia
interna, del pagador a `DIRECCION` (`mercado.py:115-117`), que reparte un
costo ya hundido —la suscripción, que Pedro ya pagó afuera del libro,
independientemente de si este asiento se aplica—. Que ese cargo quede sin
aplicarse no le saca un peso a Pedro: le desalinea la atribución interna del
gasto a ese departamento (eficiencia, gasto del ciclo), que es un problema de
métrica, no de plata perdida. Es real y no se resuelve con una alerta por
cargo: se resuelve arreglando el latido semanal (sección 11), que es lo que
efectivamente vuelve a intentar los pendientes.

**Cargo de API sin saldo: no corta el chat, pero deja de perderse en
silencio.** El turno ya contestó cuando se cobra (paso 4, `server.py:2496`,
`:2507`); cortarlo retroactivamente no tiene sentido y Pedro no lo pidió.
**Decidido: cuando `Pagador._apilar_pendiente` (`pagador.py:86-89`) recibe un
cargo `tipo == "api"`, además de apilarlo en `cargos_pendientes.jsonl` encola
una carta** con `Cola.encolar_carta` (`cola.py:119-126`) — el mismo mecanismo
sin escrow que ya usan las cartas de cierre departamental (sección 7.3, punto
2), idempotente por `id` (`cola.py:121-122`): reintentos del mismo cargo no
duplican la carta. Los cargos de suscripción/capacidad no encolan carta —
son el caso "ok" de arriba.

**Dónde la ve Pedro: la cola, no el pulso.** El sistema ya tiene tres lugares
donde algo puede aparecerle: el pulso, la cola y la barra de avisos de
`/fabrica`. El pulso (`mapa/pulso.py:4-6`) es "un anillo de eventos en
memoria" donde, textual, "nada de esto se persiste": si Pedro no está mirando
el mapa en ese instante, el aviso se pierde para siempre, y eso es
precisamente lo que no puede pasarle a un cargo de plata real. La cola, en
cambio, es la superficie donde ya vive lo que Pedro tiene que revisar y
firmar (invariante 5), y una carta encolada **ya se pinta sola**:
`mapa/ciudad.py:avisos` (`:248-259`), plegando `cola.pendientes()`
(`:268`, `:288`), alimenta la barra `#avisos` de `/fabrica`
(`web/fabrica/app.js:177`, `:224-232`; el texto lo arma
`resumenDeAvisos`, `web/fabrica/paneles.js:53-61`, que ya es genérico sobre
`tipo`/`sobre`/`monedas_en_juego_mm`) sin que haga falta tocar una línea de
UI nueva. No se elige la barra de avisos como mecanismo: se elige la cola, y
la barra de avisos es donde esa elección ya aparece.

**Lo que no puede pasar más: un cargo de API que solo vive en
`cargos_pendientes.jsonl`.** Hoy eso es exactamente lo que pasa —
`_cobrar_turno` (`server.py:4183-4188`) traga la excepción, la imprime a
`stderr` y devuelve 0, y un `print` a un log que nadie lee no es una alerta
que Pedro vea. Con la carta encolada, el cargo sigue viviendo en
`cargos_pendientes.jsonl` como registro —sigue siendo la fuente de verdad de
lo que falta cobrar, y si algún día algo vuelve a llamar
`reintentar_pendientes` (sección 11) lo intenta desde ahí— pero además, desde
ya y sin depender de que eso pase, existe visible y persistente en la barra
de avisos, hasta que Pedro la atienda con `Cola.atender_carta`
(`cola.py:152-159`), que es literalmente "lo reviso yo a ver que pasó", y
desde ahí entre a hablar con Calipso sobre el caso, como dijo.

---

## 5. Qué es un departamento después de esto

### 5.1 Sigue siendo la billetera, y gana lo que le falta

No se le saca nada. Un departamento sigue teniendo su cuenta `dep:<nombre>`
(`departamentos.py:42-45`), sus cuatro perillas (`:31-34`), su jefe
(`plantel/jefe.py`) y su memoria. Lo que gana es una declaración de **de qué es
capaz**, que hoy no existe en ninguna parte.

### 5.2 Las capacidades se declaran, no se infieren

Un campo nuevo en el registro de departamentos:

```
"legal": {
  "zona": "fabrica",
  "presupuesto_semanal_mm": 0,
  "techo_api_ciclo_mm": 20000,
  "explorar_explotar_pct": 20,
  "agresividad_pct": 15,
  "capacidades": ["revision-contratos", "licencias-oss", "politica-privacidad"]
}
```

Una capacidad es **un identificador estable que un skill puede reclamar**. No es
prosa y no es un prompt: es la clave que une "qué sabe hacer este departamento"
con "qué skill se le carga a un agente contratado por este departamento".

Tres reglas:

- **Un departamento sin capacidades declaradas no puede ser `dueno` de un
  gasto.** Es la respuesta directa al problema de la sección 1: si `legal` e
  `I&D` no declaran nada distinto, son el mismo departamento con dos billeteras,
  y la métrica por departamento no significa nada.
- **La lista de capacidades de un proyecto es la unión de las de sus
  departamentos habilitados.** Es la forma de contestar "¿Atlas puede hacer
  esto?" sin preguntarle a un modelo.
- **Las capacidades no se infieren del nombre.** `skills.infer`
  (`skills.py:72-90`) ya adivina un skill por palabras del rol y la tarea; sirve
  para un agente efímero del orquestador y no sirve para esto. Un departamento es
  permanente y su capacidad es configuración de Pedro, no una adivinanza por
  substring.

### 5.3 Los skills, y las bibliotecas de Pedro

Hoy `skills.REGISTRY` es un dict hardcodeado de 8 entradas sin ningún I/O
(`skills.py:12-69`), y `/api/skills` es GET solamente (`server.py:2887-2892`).
Pedro tiene marcadas en GitHub dos bibliotecas de agent skills con más de mil
skills entre las dos, más OpenCut y OpenMontage (producción de video agéntica) y
claude-obsidian.

**Decidido: los skills se cargan por archivo, con el molde que el repo ya
tiene.** `capabilities.py` resuelve exactamente este problema para los backends:
un `REGISTRY` hardcodeado que `load_backends` mergea con `~/.calipso/capabilities.json`
y, si hay proyecto, con `<repo>/.calipso/capabilities.json`
(`capabilities.py:161-167`, con `CAP_FILE` en `:28`). El registro de skills
copia esa forma:

- `skills.REGISTRY` queda como el piso hardcodeado (los 8 de hoy);
- se mergea `~/.calipso/skills.json` encima;
- cada skill declara qué capacidades reclama, para que la sección 5.2 tenga con
  qué unir.

Mil skills no entran a mano en un dict de Python, y no tienen por qué: el archivo
puede ser generado desde donde estén clonadas las bibliotecas. **Cuáles entran y
bajo qué licencia lo decide Pedro** (sección 12, pregunta 3); el mecanismo lo
decide este spec.

Lo que este spec **no** resuelve y hay que decir en voz alta: un agente
contratado hereda hoy **el CLI entero sin restricción**
(`server.py:1944-1947`: se arma `claude --append-system-prompt-file ... -p`, sin
allowlist de herramientas), mientras que `tools/commands.py:23` tiene un runner
con allowlist real que no está expuesto a ningún agente. O sea que un agente
contratado por `dep:legal` puede hacer lo mismo que la sesión que lo lanzó.
Declarar de qué es capaz un departamento sin acotar qué puede tocar es media
respuesta. Ver sección 11.

### 5.4 Qué NO se toca del departamento

- **La quiebra se acota.** Hoy el cierre declara quiebra a todo departamento de
  fábrica con `disponible <= 0` que ya haya aparecido en el libro
  (`cierre.py:64-76`). Con el presupuesto en el proyecto, un departamento de
  apoyo vive legítimamente en cero y sería declarado en quiebra todas las
  semanas. **Decidido: la quiebra solo aplica a departamentos con
  `presupuesto_semanal_mm > 0`**, es decir, a los que tienen billetera propia por
  diseño. Hoy eso casi funciona por accidente —`_primera_semana`
  (`cierre.py:37-42`) mira `origen`, `destino` y `detalle["departamento"]`, y un
  departamento que solo actúa como `dueno` nunca aparece— pero apoyarse en un
  accidente es apoyarse en nada.
- **El techo de API sigue siendo del departamento.** `techo_api_ciclo_mm`
  (`departamentos.py:32`) es una perilla de seguridad sobre el actor, no sobre la
  plata, y `gasto_api_ciclo` ya suma por dueño además de por origen
  (`mercado.py:26-33`), así que sigue funcionando sin tocarlo cuando el pagador
  pasa a ser un proyecto. Es el único pedazo del mercado que ya estaba escrito
  para este modelo.

---

## 6. El cerebro, y la cuenta `direccion` que no se toca

Pedro pidió *"direcion o cerebro donde llega todo y ahi esta calipso como tal y
su memoria centralizada"*. Hay una trampa de nombres, y hay que desarmarla antes
de construir nada.

**`direccion` ya existe y NO es un departamento.** Es una cuenta fija
(`tipos.py:19`) que hace tres trabajos:

- **recauda** lo que los departamentos pagan por capacidad: `comprar_capacidad`
  transfiere siempre a `DIRECCION` (`mercado.py:115-117`);
- **paga** la renovación mensual de las suscripciones, reponiéndose del tesoro si
  no le alcanza (`cierre.py:186-204`);
- **presta en última instancia**: adelanta compuertas obligatorias de
  departamentos sin caja como crédito prioritario (`direccion.py:79-84`,
  invariante 6).

Y está deliberadamente fuera del modelo de departamentos: no está en el Registro,
`dep_por_cuenta("direccion")` revienta (`mercado.py:44-48`), y no es edificio del
mapa (`mapa/ciudad.py:151-152` arma las filas desde el registro más
`CUENTA_PEDRO`, nada más).

**Decidido: el cerebro es un departamento nuevo, `dep:cerebro`. La cuenta
`direccion` no se toca ni se renombra.** Renombrar una cuenta fija en un libro
append-only dejaría huérfano todo asiento pasado; y aunque hoy no haya libro que
romper, la cuenta hace tres trabajos que el cerebro no hace y no debería hacer:
el cerebro no cobra peaje por capacidad, no paga suscripciones y no presta.

Lo que sí es el cerebro:

- **Es donde vive Calipso.** El chat de Pedro sin edificio en foco le habla al
  cerebro, y por lo tanto lo hace `dep:cerebro` (sección 9.3).
- **Es donde vive la memoria centralizada.** La memoria por departamento es la
  cuarta pata que todavía falta (`docs/superpowers/2026-08-26-inventario-abierto.md`,
  items 17 y 44); la del cerebro es la global.
- **Es un edificio del mapa como cualquier otro**, porque está en el Registro. A
  diferencia de `direccion`, que sigue sin serlo.
- **Es el `dueno` por defecto** de cualquier gasto que no tenga otro departamento
  en foco.

### El cerebro tiene que poder ver su propia economía

Hay un síntoma concreto que este spec cierra: el chat le dijo a Pedro que no
podía ver su economía **estando adentro del server que la tiene cargada**. La
causa está localizada: `prompt_compiler.context_sections`
(`prompt_compiler.py:47-72`) arma el contexto en ocho secciones —Sistema,
Constitución, Memoria núcleo, Contrato interno, Recuerdos, Repo, Meta activa,
Estado operativo— y **ninguna es de economía**.

**Decidido: una sección nueva, `Economia`, entre "Meta activa" y "Estado
operativo".** Contenido, todo plegado del libro y nada guardado:

- saldo del tesoro y tipo de cambio vigente del PT (`pt.tipo_de_cambio`,
  `pt.py:109-170`);
- por cada proyecto activo: presupuesto cargado, gastado, disponible;
- gasto del ciclo del departamento en foco, si hay uno;
- y **solo en un chat de zona personal**: el neto del banco de Pedro, tomado de
  `personal.tablero` (`personal.py:69`), que ya está declarado lector y jamás
  escribe. Los movimientos crudos nunca entran al prompt: la invariante 11 se
  respeta sirviendo el consolidado, no el libro.

---

## 7. El nexo: quién lo hizo y para qué proyecto

Este es el hueco de la sección 1 y se cierra con tres claves del asiento, dos de
las cuales ya existen.

### 7.1 Las tres claves

| clave | qué contesta | estado hoy |
|---|---|---|
| `origen` | **quién pagó**: `proyecto:<slug>`, `trabajo:<id>` o `dep:<nombre>` | existe |
| `detalle["dueno"]` | **qué departamento lo hizo** | existe, `mercado.py:110-111` y `:152-153` |
| `ref` | forzado a la cuenta pagadora cuando el pagador no es un departamento | existe, `mercado.py:112-114` y `:154-156` |

La regla se generaliza en una línea: **`dueno` se estampa siempre que el pagador
no sea, él mismo, una cuenta de departamento.** Hoy la condición está escrita
como `pagador.startswith("trabajo:")` (`mercado.py:110`, `:152`); pasa a ser
"el pagador no es `dep:*` ni `personal:*`".

Y la compuerta que le da sentido a la lista `departamentos` del proyecto
(sección 3.2): cuando el pagador es `proyecto:<slug>`, el `dueno` tiene que estar
en esa lista. Un departamento no habilitado no le gasta a un proyecto, aunque
sepa el nombre de la cuenta.

### 7.2 Cómo se lee, en dos pliegues puros

**El proyecto de un gasto:**
- `origen` empieza con `proyecto:` → ese proyecto, directo;
- `origen` empieza con `trabajo:` → el `proyecto` del evento `alta` de ese
  trabajo en el bus (`bus.datos`, `bus.py:84-90`);
- `origen` empieza con `dep:` → **ninguno**, y es una respuesta correcta, no un
  hueco: es gasto de estructura del departamento.

**El departamento de un gasto:**
- `detalle["dueno"]` si está;
- si no, `origen` cuando `origen` empieza con `dep:`.

Las dos son funciones puras sobre la lista de asientos, de la misma clase que
`mapa/ciudad.py` y `plantel/situacion.py`: sin red, sin reloj de sistema, se
testean contra un libro sintético campo por campo.

### 7.3 Lo que se rompe si esto se hace y no se acompaña

Tres cosas, las tres verificadas, las tres que **hay que arreglar en el mismo
movimiento** o quedan mintiendo:

1. **La eficiencia por departamento se va a cero para todos.**
   `eficiencia_departamento` (`eficiencia.py:104-115`) calcula el consumido con
   `costo_api_directo` (`:86-101`), que filtra por `a.origen != dep_cuenta`. Si
   el gasto sale por `proyecto:*`, ese filtro no pega nunca. Tiene que plegar por
   `detalle["dueno"]`, exactamente como `gasto_api_ciclo` ya hace
   (`mercado.py:29-33`). Sin esto, el mapa pinta todos los edificios iguales
   (`mapa/ciudad.py:177-180` toma su color de esa función).

2. **La carta de cierre departamental deja de tener sentido y se reapunta al
   proyecto.** Hoy el cierre le manda carta a todo departamento de fábrica que
   lleve 8 semanas operativas sin una sola venta, plegando sobre
   `{dep.cuenta} ∪ {trabajos del dep}` (`cierre.py:117-142`). Un departamento de
   `legal` o de `testing` **nunca** va a registrar una venta: no vende, sostiene.
   Lo que vende o no vende es el proyecto. **Decidido: la carta pasa a ser
   `cierre_proyecto`**, plegada sobre `{proyecto:<slug>} ∪ {trabajos del
   proyecto}`. La carta de departamento se retira, no se reapunta: la pregunta
   que hacía no tiene respuesta correcta para un departamento de apoyo.

3. **El jefe propone contra la billetera equivocada.** `_contratar_para`
   dimensiona el presupuesto de una propuesta con
   `situacion["presupuesto_semanal_mm"] * agresividad_pct // 100`
   (`server.py:3874-3876`), y `_puede` frena al jefe si
   `s["disponible_mm"] <= 0` (`jefe.py:61-62`). Con la plata en el proyecto, un
   departamento de apoyo tiene 0 en las dos y queda **congelado para siempre**:
   nunca propone nada. Hacen falta tres cambios chicos y acoplados:
   - `situacion` (`situacion.py:54`) gana la lista de proyectos activos que
     habilitan a este departamento, cada uno con su disponible;
   - `dec.prompt` (`decision.py:28`) los ofrece, y `_puede` valida la referencia
     al proyecto igual que hoy valida la de un trabajo (`jefe.py:47-49`);
   - el presupuesto de la propuesta es
     `min(tope de agresividad, disponible del proyecto)`, y el chequeo de saldo
     mira el disponible del proyecto elegido.

---

## 8. Las tres bolsas

### El titular

Las tres bolsas tienen **una sola causa raíz compartida**, y es la puerta de la
primera: `Kernel.acunar` (`kernel.py:47-58`) **no tiene un solo llamador fuera de
tests** (verificado: todos los hits de `acunar` en el repo son de `test_*.py`).
Nunca entró plata de afuera. Las consecuencias medidas de eso son tres, y son las
tres cosas que parecen bugs independientes:

- el tipo de cambio del PT queda pegado en el arranque de 5.000 mm
  (`pt.py:148`, regla (d): sin bootstrap superado, `tipo = arranque_mm`);
- toda la eficiencia da 0, porque el numerador es siempre señal exterior y no hay
  ninguna (`eficiencia.py:66-69`);
- la carta de cierre departamental dispara contra **todos** a las 8 semanas
  (`cierre.py:117-142`), porque nadie vendió nunca nada.

### 8.1 El tesoro — existe, está vacía, le falta la puerta

`TESORO` (`tipos.py:17`) es la cuenta de la que sale todo presupuesto:
`direccion.asignar_presupuesto` (`direccion.py:46`), el presupuesto de dirección
del cierre (`cierre.py:87-89`) y la reposición para la renovación
(`cierre.py:195-196`). La bolsa está construida entera. Lo que falta es la
puerta: la sección 8.5.

### 8.2 El presupuesto de gasto — está partida en cuatro

Pedro la describe como *"los de las suscripciones los apis y las otras cosas que
quiera comprar"*. Hoy vive en cuatro lugares que no se hablan:

- **`suscripciones.json`** (`pagador.py:55`, leído en `:70-71`): el costo mensual
  y la capacidad de cada suscripción. **El archivo no existe.**
- **`PRECIOS_API_MM_POR_MTOK`** (`pagador.py:28`): **un solo modelo**,
  `deepseek-chat`. Todo lo demás cae en `PRECIO_DESCONOCIDO` (`:29`), un par
  conservador inventado.
- **`calipso/costs.py`**: el uso personal, deliberadamente fuera del libro de la
  fábrica (`pagador.py:150-151`).
- **la caja de `direccion`**, que es la que efectivamente paga la renovación
  (`cierre.py:201-203`).

**Decidido: la bolsa 2 no es una cuenta nueva. Es `direccion`, y ya está
construida.** Recauda la capacidad (`mercado.py:115-117`), paga la renovación
(`cierre.py:201-203`) y se repone del tesoro cuando no le alcanza
(`cierre.py:192-198`). No hay que inventarla; hay que terminarla:

- que `suscripciones.json` exista con lo que Pedro paga de verdad;
- que `PRECIOS_API_MM_POR_MTOK` cubra los modelos que se usan;
- **"las otras cosas que quiera comprar"**: una compra puntual es una
  destrucción desde `direccion` con motivo `compra` y firma, entrando por la
  cola como compuerta tipo (c) de la invariante 5. La maquinaria existe: `_TIPOS`
  de la cola ya incluye `"gasto"` (`cola.py:26`).
- una vista que sume las cuatro fuentes en un número, porque hoy nadie puede
  contestar "cuánto gasto por mes".

### 8.3 Mis horas — existe entera, con el precio roto

Es la única de las tres que funciona sola. Emisión semanal (`pt.py:26-60`), dos
pools (`tipos.py:20-21`), consumo (`pt.py:63-95`), expiración al cierre
(`pt.py:98-106`), tipo de cambio como pliegue determinístico
(`pt.py:109-170`), y el reloj como frontera de entrada del tiempo
(`economia/reloj.py`).

No hay que construir nada. Su precio está pegado por la causa raíz del titular, y
se arregla con la sección 8.5, no acá.

### 8.4 El banco de Pedro — existe y nadie escribe en él

Pedro dijo: *"un banco con mi plata ingresos y egresos para hacer analisis
financieros mios o que calipso tambien tenga ese contexto"*.

Eso es `LibroPersonal` (`personal.py:26-60`), que ya existe, ya valida tipo y
monto (`personal.py:35-49`), ya resume por semana (`:51-60`) y es **privado por
invariante 11**. El server lo construye en cada request
(`server.py:3426`) y lo lee para el tablero (`server.py:3476`).

Y **no tiene un solo escritor de producción**: los únicos llamadores de
`registrar` en todo el repo son `test_economia_frontera.py:372-374`.

**Decidido: el banco es `LibroPersonal` y no se mueve al libro de la fábrica.** La
invariante 11 no se toca. Lo que falta son dos cosas y ninguna es contable:

1. **La escritura**: un endpoint `POST /api/economia/personal/movimiento` que
   llame a `registrar`, y su vista. Nunca acuña, nunca toca el libro de la
   fábrica.
2. **El contexto**: la sección `Economia` del prompt (sección 6), que le sirve a
   Calipso el **consolidado** de `personal.tablero`, no los movimientos crudos.

### 8.5 Cómo entra por primera vez plata de afuera

Un endpoint nuevo, `POST /api/economia/frontera/acunar`, con el mismo candado y
la misma forma que las escrituras que ya existen
(`server.py:3541-3573` sirve de molde: candado, mercado fresco adentro,
`_eco_errores_economicos` a 400).

Cuerpo: `{subtipo, destino, monto_mm, evidencia}`. Reglas, taxativas:

- **`subtipo: "capital"`** → destino **solo** `tesoro`. Es Pedro poniendo plata
  suya. La evidencia es su firma.
- **`subtipo: "venta"`** → destino **solo** `proyecto:<slug>` de un proyecto
  activo, o `trabajo:<id>` vivo. La evidencia es el comprobante (id de cobro,
  link, captura), que va en `detalle["evidencia"]` como `Asiento.validar` ya
  exige (`tipos.py:83-84`).
- **Nunca** `dep:*`, **nunca** `direccion`, **nunca** `cuenta_pedro`. El que vende
  es el proyecto; el departamento es el que trabaja. Una venta en `dep:legal` no
  significa nada.
- Una acuñación por venta lleva además **`detalle["proyecto"]` siempre**, y
  **`detalle["trabajo"]` cuando salió de un trabajo vivo**. La segunda no es
  opcional ni redundante: `eficiencia.ventas_por_trabajo` (`eficiencia.py:15-24`)
  atribuye leyendo exactamente esa clave, y sin ella la venta no le atribuye
  eficiencia a nadie.

Esto respeta la invariante 4 entera: toda acuñación entra por una frontera, con
evidencia, confirmada por Pedro. Ningún departamento, ningún proyecto y ningún
jefe puede autodeclarar un ingreso.

---

## 9. Las dos vistas

### 9.1 Vista A — la lista de chats en secciones por proyecto

Estado hoy: la UI vieja **ya agrupa**, por `project_path` del chat
(`web/index.html:2139-2148`). La UI de la fábrica lo ignora y pinta lista plana
(`web/fabrica/app.js:470-476`, dentro de `#lista-chats`,
`web/fabrica/index.html:15`).

**Decidido: las secciones son PROYECTOS de la fábrica, no `project_path`.** El
puente es el `repo_path` del proyecto (sección 3.2): un chat cuyo `project_path`
(`chats.py:81`) cae bajo el `repo_path` de un proyecto entra en esa sección. Los
demás van a una sección **"sin proyecto"**, que es explícita y no un cajón de
sastre: un chat sin proyecto no le cuesta nada al libro de la fábrica.

Cada sección muestra, junto al nombre del proyecto, su **disponible**. Es el
número que Pedro pidió poder mirar bajar, y está donde ya está mirando.

### 9.2 Vista B — la mesa del departamento en foco

Estado hoy: `#panel-mesa` (`web/fabrica/index.html:47-51`) tiene `#plantel` y
`#mesa`; `mesa.textoDeMesa` (`web/fabrica/mesa.js:60-80`) pinta una fila por
propuesta del bus. Tocar un edificio hoy solo mueve la cámara y pinta una tarjeta
(`web/fabrica/app.js:359-386`).

**Decidido: la mesa gana un segundo modo.** Al tocar un edificio, muestra el
departamento en foco: **una fila por proyecto que lo está usando**, con gasto del
ciclo, trabajos vivos y última actividad. Al soltar el foco, vuelve a propuestas.
El modo propuestas sigue siendo el default, porque es el que Pedro necesita todos
los días.

El dato es un pliegue puro, `proyectos_de_departamento(asientos, dep_cuenta,
semanas)`: agrupa por el proyecto derivado del `origen` (sección 7.2) los
asientos cuyo `detalle["dueno"]` es este departamento. Misma clase de función que
`mapa/ciudad.py` y `plantel/situacion.py`.

Endpoint: uno nuevo, `GET /api/economia/departamento/{cuenta}`, no una extensión
de `GET /api/economia/bus` (`server.py:3490-3538`). Razón: la mesa de propuestas
se pide en cada refresco y esto solo cuando hay foco; meterlo adentro le cobra a
todos el costo de lo que usa uno.

### 9.3 La mezcla, que es lo que hace funcionar el nexo

Pedro dijo que podía ser una mezcla de las dos. Lo es, y no por estética: **las
dos vistas contestan las dos mitades del nexo de la sección 7.**

Hoy la cuenta que paga un turno de chat sale del **edificio en foco del mapa**:
`_cuenta_en_foco` (`server.py:4090-4100`) valida el id contra el registro y lo
traduce con `ficha.cuenta_pagadora` (`mapa/ficha.py:33-52`); `_ficha_y_cuenta`
(`server.py:4103-4135`) separa a propósito "quién paga" de "qué sabe Calipso del
departamento".

**Decidido, y es la decisión más importante de la sección:**

- **quién paga** = el proyecto del chat (vista A). Sin proyecto, `personal`, que
  queda fuera del libro de la fábrica como hoy.
- **quién lo hizo** (`dueno`) = el departamento en foco del mapa (vista B). Sin
  foco, `dep:cerebro`, porque un chat sin edificio en foco le está hablando a
  Calipso y Calipso vive en el cerebro (sección 6).

O sea: Pedro abre un chat en la sección Atlas y toca el edificio de `legal`. El
turno lo paga `proyecto:atlas` y el asiento dice `dueno: dep:legal`. Es
exactamente *"gastan los departamentos y reportan para que proyecto estan
gastando"*, y sale gratis de las dos vistas que él ya pidió.

El foco **ya no cambia quién paga**. Cambia quién lo hizo. Es un cambio de
comportamiento respecto de `_cuenta_en_foco` hoy, y es deliberado.

---

## 10. Invariantes: qué se toca y qué no

### Se tocan dos, y son la misma compuerta escrita dos veces

1. **`mercado._politica`** (`mercado.py:70-88`) deja de exigir que el pagador sea
   un departamento registrado y pasa a aceptar `proyecto:<slug>` con `dueno`
   explícito, resolviendo las políticas contra el dueño.
2. **`bus.financiar`** (`bus.py:116-123`) hace lo mismo para el financiador.

**El contenido de la invariante 12 no cambia.** La zona personal sigue sin
comprar capacidad, API, PT ni goteo de la fábrica. Lo que se separa son dos
preguntas que hoy están confundidas en una: quién puede pagar, y contra quién se
evalúan las políticas. La segunda sigue siendo siempre un departamento de fábrica
registrado y activo.

### No se tocan, bajo ningún concepto

- **Invariante 1 — solo el exterior acuña y destruye.** Un proyecto **no acuña**.
  Su presupuesto es una transferencia del tesoro, suma cero. La única plata nueva
  entra por la frontera de la sección 8.5.
- **Invariante 4 — toda acuñación con evidencia.** El endpoint nuevo no la
  esquiva: la exige, y el tipo ya la exige antes que él (`tipos.py:83-84`).
- **Invariante 7 — sin sobregiro.** `proyecto:atlas` obedece `Kernel._exigir`
  (`kernel.py:35-38`) como cualquier cuenta: el libro nunca la deja en
  negativo. Eso es una garantía sobre el libro, no sobre el momento del
  gasto — el cobro de un turno es posterior y asincrónico, y qué pasa cuando
  falla es la política de saldo agotado de la sección 4.
- **Invariante 9 — solo el kernel escribe billeteras.** `proyectos.json` es
  configuración, no saldo. El saldo se pliega (`balances.py:18-27`).
- **Invariante 11 — los libros personales son privados.** El banco se queda en
  `personal.jsonl`. Al prompt llega el consolidado del tablero, nunca los
  movimientos.
- **Invariantes 2 y 3 — el PT.** Un proyecto nunca tiene PT.
  `tipos.py:110-115` prohíbe que una cuenta que no sea `pt:*` toque divisa PT, y
  eso queda igual.
- **El append-only.** Ningún asiento pasado se reescribe, y **ningún pliegue
  puede exigir una clave nueva**: todos leen con `.get()` y default, que es la
  disciplina que el server ya aplica contra el bus real (`server.py:3516-3528`).
- **`Asiento.validar` sigue sin validar nombres de cuenta** (`tipos.py:71-121`) y
  las cuentas siguen naciendo al ser nombradas (`balances.py:18-27`). La
  disciplina de nombres vive en la compuerta del Mercado, no en el tipo. Meter
  una lista blanca de cuentas en `validar` obligaría a cada asiento viejo a
  revalidarse contra una regla más nueva que él: es exactamente lo que un libro
  append-only no puede hacer.

---

## 11. Fuera de alcance, y por qué

- **Ejecutar el trabajo.** `trabajar` sigue siendo no-op: `_contratar_para`
  devuelve el gancho sin cobrar nada (`server.py:3854-3858`), y la razón escrita
  ahí sigue siendo la correcta —cobrar sobre un plan que nunca corre mete
  asientos falsos que corrompen la señal de precio que realimenta al jefe. Un
  proyecto con presupuesto y sin ejecución sigue siendo un presupuesto que baja
  por el chat de Pedro, que es lo que ya pasa hoy.
- **La frontera de salida** (mandar el correo, publicar). Otro spec, ya
  identificado (`docs/superpowers/2026-08-26-inventario-abierto.md`, item 1).
- **Conectores automáticos**, de ventas y bancarios. La ingesta de este spec es
  manual y firmada a propósito (invariante 4).
- **La baja de un departamento.** `Kernel.liquidar` (`kernel.py:141-157`)
  consigue su primer llamador acá, pero para **cerrar un proyecto**, no para dar
  de baja un departamento: `departamentos.py:62-81` sigue teniendo `alta`,
  `obtener`, `todos` y `ajustar`, y ninguna baja. Razón: cerrar un departamento
  pregunta quién hereda sus proyectos y su memoria, y eso es una decisión de
  organización, no de contabilidad.
- **La allowlist de herramientas del agente contratado.** Nombrada en 5.3 y no
  resuelta acá: es un spec de seguridad, y mezclarlo con el modelo económico hace
  que ninguno de los dos se revise bien.
- **El cierre semanal no tiene quién lo dispare.** `cerrar_semana_operativa`
  (`operacion.py:46`) es el latido de toda la economía: liquida los trabajos
  muertos (`cierre.py:61-62`), expira los PT (`pt.py:98-106`), manda las
  cartas de cierre (`cierre.py:117-142`) y paga la renovación de suscripciones
  reponiéndose del tesoro si hace falta (`cierre.py:192-198`, `:201-203`). Y
  solo corre detrás de `POST /api/economia/cierre` (`server.py:3676-3687`),
  que **no tiene un solo llamador de producción verificado**: cero resultados
  para `economia/cierre` en `calipso/web/`; `routines.KINDS`
  (`routines.py:29`) es `("reflect", "learn", "backup", "departamento")` —sin
  un kind de cierre— y su mapa de handlers (`server.py:2656`) tampoco lo
  tiene; y no hay cron ni timer de systemd en esta máquina. Hoy el cierre
  semanal **no corre nunca**. Se nombra acá, y no se resuelve acá, porque
  quién lo dispara es una decisión de diseño (¿una rutina más en
  `routines.KINDS`? ¿un botón en la mesa? ¿un timer?) que excede esta
  corrección — pero la política de saldo agotado de la sección 4 depende de
  que corra: sin él, `Pagador.reintentar_pendientes` (`pagador.py:98-116`)
  nunca se llama y un cargo pendiente, de API o de suscripción, queda muerto
  en `cargos_pendientes.jsonl` para siempre.
- **El token en el query string.** `auth_guard` acepta `?token=`
  (`server.py:246`) y uvicorn loguea el query string entero, así que el token
  queda en texto plano en el log en cada request (verificado por observación
  directa). Se nombra acá porque **toda la superficie nueva de este spec mueve
  plata y hereda ese guard**, no porque se resuelva acá.
- **Multi-usuario o filtrado por sujeto.** `_valid` es un `compare_digest` contra
  un único token global (`server.py:128-129`): no hay sujeto al que filtrarle
  nada.
- **Proyectos de zona personal.** El modelo los admite (el campo `zona` está en
  3.2) pero este spec no los construye: un chat personal sigue colapsando a la
  cuenta `personal` y quedando fuera del libro de la fábrica
  (`mapa/ficha.py:41-52`). Meter la zona personal en el mismo movimiento
  duplicaría la superficie a revisar sin agregar una sola respuesta a las siete
  preguntas de arriba.
- **Migración del libro.** No hay nada que migrar: `~/.calipso/economia/` no
  existe.

---

## 12. Preguntas abiertas, con quién las contesta

Cinco. Ninguna bloquea empezar; las dos primeras bloquean **encender**.

1. **La lista exacta de departamentos del arranque.** Pedro nombró cuatro
   (cerebro, market research, legal, I&D) y describiendo Atlas nombró cinco más
   (publicar, testing, marketing, research, development). Dos cosas concretas:
   ¿"market research" y "research" son el mismo departamento o dos distintos?
   ¿"publicar" es un departamento o es la frontera de salida, que está fuera de
   alcance? **Contesta: Pedro.**

2. **Cuánto capital entra en la primera acuñación al tesoro.** Es su plata y no
   hay forma de deducirlo. Sin ese número el sistema no arranca: el presupuesto
   de todo proyecto sale del tesoro (`direccion.py:46`). **Contesta: Pedro.**

3. **Cuáles skills de las dos bibliotecas entran, y bajo qué licencia.** El
   mecanismo lo decide este spec (declaración por archivo, molde
   `capabilities.py:161-167`). Qué entra de más de mil skills, y si se leen desde
   donde están clonadas o se copian al repo, es decisión de licencia y de
   mantenimiento. **Contesta: Pedro.**

4. **El sueldo.** `SUELDO_MENSUAL_MM = 2_500_000` (`personal.py:19`) hoy se usa
   solo como línea base del costo de oportunidad
   (`linea_empleo_mm_por_hora`, `personal.py:63-66`). ¿Se carga además como
   ingreso recurrente del banco (8.4), o se queda como línea base y nada más?
   **Contesta: Pedro.**

5. **Qué pasa cuando un proyecto se queda sin plata con un trabajo vivo
   adentro.** Este spec decide que se emite una carta a la cola de compuertas
   (`cola.py`) en vez de matar el trabajo o dejar que el departamento adelante.
   Lo que queda abierto es en qué carril: sesión, que acumula y espera a la
   sesión semanal, o goteo, que interrumpe con recargo y tiene tope duro de dos
   por semana (`cola.py:22-25`). Es una decisión sobre cuánto quiere que lo
   interrumpan. **Contesta: Pedro.**
