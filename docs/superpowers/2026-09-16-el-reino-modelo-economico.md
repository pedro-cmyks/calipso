# El reino: la cosmologia y el modelo economico de los departamentos (2026-09-16)

Documento base para **la sesion del padron**, que Pedro pidio aparte: *"hay que hacer una sesion para
definir los departamentos y el alcance de cada uno y lo que se espera, en su propia sesion"*. El padron es
el unico paso irreversible de la siembra, asi que esa sesion arranca con esto escrito y no desde cero.

Todo lo que sigue salio de la conversacion del 2026-09-16, y lo tecnico esta medido contra el codigo en
`2026-09-16-cosmologia-y-departamentos.md` (1.196 lineas, ocho lectores sobre `calipso/economia/`,
`calipso/plantel/`, `calipso/permisos/`, la aduana, el mapa y los goals).

## 1. La cosmologia, en palabras de Pedro

*"El abismo es una BOVEDA, una boveda con NIVELES. La fabrica es donde existe como el REINO del asistente,
que viene siendo Calipso, y todas las posibilidades de las cosas que hace y las cosas que requieren de
ella: los jefes, los proyectos, las metas, la economia."*

Y la pregunta que abrio: los departamentos TIENEN manos, o los departamentos SON manos?

**Ninguna de las dos: invocan.** Es la respuesta que estaba en su propia metafora anterior ("los
departamentos son unos magos que invocan a Calipso, y Calipso es la que tiene el conocimiento del abismo y
las herramientas"). Un mago no tiene manos: tiene voluntad y una formula. El cuerpo es de Calipso y es uno
solo. El mundo queda en cuatro lugares que no se mezclan:

| lugar | que es | que hace | estado |
|---|---|---|---|
| **La boveda** (el abismo) | lo que se SABE, por niveles de profundidad (los anillos) | se consulta; no actua | frontera construida; la geografia es la rebanada 3 |
| **El reino** (la fabrica) | los que QUIEREN (jefes, departamentos), lo que se quiere (proyectos, metas) y con que se paga (la economia) | proponen y deciden; no tocan nada | construido y NUNCA sembrado |
| **El cuerpo** (las manos, y despues los ojos) | uno solo, de Calipso: hoy el goal con su sandbox, su hook fail-closed y su juez | toca el mundo | los goals andan; las manos de verdad son el subproyecto 2 |
| **La isla** (la aduana) | lo que cruza hacia afuera | mide y registra; no frena | viva, 107 cruces reales |

**La simetria que cierra el modelo:** la boveda tiene NIVELES para lo que entra; la puerta tiene COMPUERTAS
para lo que sale. Anillos y familias son la misma idea aplicada a los dos ejes del sistema -- saber y
hacer, cada uno con su frontera.

**Tres consecuencias que no son poesia:**

1. Explica por que "departamento = goal" no cerraba y **"departamento LANZA goals" si**: un departamento es
   un *querer que dura*; un goal es un *hacer que termina*. Mezclarlos da un querer que se apaga solo o un
   hacer que no termina nunca.
2. **El cuerpo es uno, asi que las manos no se reparten: se turnan.** El carril unico de goals
   (`goals.py:708-713`, un solo `activo.json`) deja de ser una limitacion accidental y pasa a ser coherente
   con el modelo. Lo que hay que construir no es un segundo par de manos: es un orden de turnos.
3. **Simplifica el padron.** Si el *como* lo pone el cuerpo, un departamento no declara capacidades
   tecnicas. Declara tres cosas: **que quiere** (el norte), **hasta donde** (alcance y compuertas) y **con
   que** (el bolsillo).

## 2. El objetivo de fondo: que Calipso administre, y despues gane

Pedro: *"el objetivo final de ponerle a Calipso, ademas de delegarle tareas y trabajos y proyectos
personales, es que tambien pueda manejar su economia... que siempre quiera maximizar las ganancias, o
mantener, que utilice diferentes estrategias"*. Referencia elegida por el: **Anno** (city-builder con
cadenas de produccion).

**Lo que ya existe es el sistema de control de una economia que gana**, no el de un juguete: tres divisas
que no se confunden (MONEDA = plata real de Pedro; PT = su hora firmable; CRISTAL = un request de una
suscripcion YA PAGADA -- gastar un cristal no gasta una moneda, porque contarlos juntos cobraria dos veces
lo que se pago una), un libro append-only validado al escribir y al releer, presupuestos semanales, techos
por ciclo, escrow, quiebra, cartas de cierre, circuit breaker de suscripciones (rojo bajo 40% de
aprovechamiento) y un mandato de direccion que exige firma de Pedro arriba de 100 monedas.

**Lo que falta es una sola cosa y es enorme: la mitad de la frontera que FIRMA.** Hoy `gastar`, `publicar`
y `correo` son **NUNCA** en la tabla de Pedro (`goals.py:66-69`), y la acuñacion por venta externa exige
evidencia y no tiene camino: nada en el sistema puede vender, cobrar ni contactar a nadie. Consecuencia
dura: la regla "solo el libro exterior vota" es hoy **un invariante sin numerador posible**, y por eso todo
departamento muere por la misma carta de cierre a las 8 semanas.

**Maximizar ganancias no es una perilla: es abrir la puerta que el sistema cierra por diseño**, y es justo
la puerta donde un agente autonomo hace mas daño. Orden natural propuesto: **primero administrar lo que
Pedro YA gasta** (suscripciones, APIs: decisiones reales de optimizacion, cero riesgo externo), y solo
despues poder ganar. Lo primero es una economia cerrada y medible desde hoy; lo segundo exige abrir la
frontera.

## 3. Las dos clases de departamento, y las dos varas

Pedro dijo dos cosas el mismo dia que estan en tension si se aplican a los mismos: que los de costo puro
viven de **un bolsillo apartado** ("de nuestro presupuesto general descontamos esa entrada y no esta para
gastar, porque el departamento ya tiene su gasto") y que **"viven los que producen, los que estan haciendo
cosas, los que sirven"**. No se resuelve eligiendo una: hay **dos clases y dos varas**.

| clase | ejemplos | de que vive | con que se mide |
|---|---|---|---|
| **Produce hacia afuera** | los que venden, entregan, generan | de lo que gana | el libro exterior (como ya esta escrito) |
| **Sirve al sistema** | validacion y pruebas, el vigia, equipo rojo / equipo azul | de una asignacion apartada del general | **utilidad demostrada**, nunca actividad |

**La asignacion, en detalle.** La perilla existe (`presupuesto_semanal_mm`) y el paso 4 del cierre semanal
ya se la paga a cada departamento de fabrica no congelado. El mecanismo de apartar tambien existe (el
escrow: `reserva` / `liberacion` / `ejecucion_reserva`, y `disponible()` ya resta las reservas activas). Y
para estimar el bolsillo sin adivinar hay 80.620 lineas de consumo real en `~/.calipso/consumo_claude.jsonl`.

**El hueco concreto:** el escrow es **solo en MONEDAS** (`tipos.py` lo prohibe para las demas divisas), y
el bolsillo que Pedro describe ("tantos tokens") no es dinero: son **CRISTALES**. Para apartar el bolsillo
de un departamento de costo puro hay que extender la reserva a cristales o darles su propio apartado.

**Y dos reglas que hoy el codigo no cumple y hay que arreglar:** la quiebra (`disponible <= 0`) y la carta
de cierre (8 semanas sin venta externa) le caen igual a un departamento de asignacion. El spec de
proyectos-y-plata YA decidio que la quiebra solo aplique a los que tienen presupuesto propio.

## 4. El ranking, y la trampa que lo arruina

*"Constantemente es un ranking de departamentos, y viven los que producen... los que sirven."* La seleccion
ya esta construida: quiebra, carta de cierre, standing de promesas cumplidas, veto permanente de Pedro,
circuit breaker. Lo que falta es **la vara**.

**El riesgo numero uno es de modelo, no de implementacion: la metrica se vuelve la meta.** En un sistema
donde los departamentos compiten por seguir vivos, la vara que se elija es literalmente lo que van a
maximizar:

- Al **vigia** medido por *alarmas emitidas* le conviene llenar el inbox de ruido. Medido por *alarmas que
  Pedro atendio*, le conviene callarse lo irrelevante. La diferencia es una palabra y lo cambia todo.
- A **validacion** medida por *tests escritos* le conviene escribir tests triviales. Medida por *fallos
  atrapados antes del merge*, le conviene ir donde duele.
- La **Direccion** ya optimiza un molde honesto: *menos compuertas a Pedro por unidad de resultado*.

**El caso que rompe cualquier ranking ingenuo:** el departamento cuyo exito es que NO PASE NADA. Un mes sin
hallazgos del vigia significa que los proyectos estan sanos, no que fallo. Medirlo por actividad lo empuja
a inventar problemas. O sale del ranking, o se le da una vara invertida.

**Dos propiedades que el ranking tiene que tener:**

1. **Procedencia por punto**: cada numero tiene que poder señalar el hecho que lo produjo. Un ranking sin
   evidencia por punto es una opinion disfrazada de medicion, y eso es lo unico que Calipso no se permite.
2. **La vara no la toca el departamento.** Quien puede reescribir con que se lo mide no esta siendo medido.
   Eso parte la carta en dos mitades con dueños distintos: lo que **fija Pedro** (vara, alcance, bolsillo) y
   lo que **escribe el departamento** (su estado, sus notas, lo que aprendio). Hoy la carta es un solo
   archivo de prosa libre y opcional, y hay **cero cartas escritas**.

## 5. Las relaciones del reino: que hay y que falta

| relacion | estado | nota |
|---|---|---|
| **Venderse servicios** | EXISTE (`mercado.vender_servicio`) | transferencia entre dos registrados, ninguno congelado |
| **Encargar trabajo** | NO EXISTE | I+D no puede pedirle un test a Validacion. Es el hueco mas notorio |
| **Comentar** | A MEDIAS | el verbo existe pero muere en la memoria propia: el bus no tiene superficie de comentarios. Abierto desde 2026-08-26 |
| **Verse las propuestas** | EXISTE | cada jefe ve las `propuestas_ajenas` en su prompt |

**La regla que hay que sostener al agregar el encargo: el ingreso por venta interna NO cuenta como exito.**
Si contara, dos departamentos podrian facturarse servicios mutuamente y los dos apareceerian "produciendo"
sin que pase nada real: lavado interno, el atajo que cualquier optimizador encuentra primero en una
economia cerrada donde vivir depende del ranking. La invariante ya escrita dice que esa transferencia
**asigna costo, no prueba logro**.

## 6. La vista: el reino se mira desde arriba

Pedro: *"hacer un UI donde se ve la fabrica y se ve el abismo, y son objetos fisicos interactuables, por eso
la vista desde arriba... es como un juego, pero con mi plata. Y cosas de verdad"*.

Ya esta diseñado: es la **rebanada 3 del abismo**, y la cosmologia del spec dice que la ciudad esta
construida alrededor de la BOCA del abismo y que entrar es **cambiar de escena, no hacer zoom**. El estado
real: el mapa existe (`ciudad`, `foco`, `pulso`, `urbanismo`) pero es **plano** -- fabrica y personal en una
sola lista separadas por un string y un resorte de 900 unidades; sin capas, sin escenas, sin eje vertical.
Y el pulso esta **vivo y mudo**: publica ocho tipos de evento y ningun jefe corrio jamas.

**Dos reglas de diseño que se siguen de la frase de Pedro:**

1. **"Un juego pero con mi plata" invierte la regla del genero.** En Anno equivocarse es barato y
   reversible; aca una accion puede gastar dinero real, escribirle a una persona o cambiar un repo. La
   vista tiene que hacer VISIBLE que es real y que es simulado, y donde esta el boton que cuesta.
2. **Nada decorativo: cada elemento se deriva de un dato real y verificable; si no hay dato, no hay
   elemento.** El pulso ya es la advertencia. Un mapa con relleno seria la primera vez que Calipso aparenta
   algo.

**Y el premio:** la vista desde arriba ES el ojo (`2026-09-16-estado-y-ruta.md` §4). Un edificio con la luz
apagada, una calle sin trafico, un almacen lleno cuyo camion nunca sale: la deriva se mira, no se lee.

## 7. Las cinco decisiones de la sesion del padron

Ninguna es tecnica, y todas hay que tomarlas antes de escribir el padron.

1. **Las dos clases** y que departamento es de cual.
2. **La vara de cada uno** -- lo que van a perseguir el resto de su vida. Esto importa mas que el nombre.
3. **Quien fija la vara** y donde vive (la carta partida en dos mitades), sabiendo que el padron es de
   escritura unica, `Registro.ajustar` solo acepta numeros y no hay `baja`.
4. **Que relaciones existen** entre departamentos (encargo, venta, comentario) y cuales cuentan como logro:
   ninguna interna.
5. **Que significa crecer**: mas departamentos que se SOSTIENEN, no mas departamentos. Un reino con cinco
   edificios apagados se ve grande y esta muerto.

Y las que ya estan decididas y no hay que volver a discutir: los departamentos **lanzan** goals (no son
goals); los de costo puro viven de una **asignacion apartada**; el bolsillo se mide en **cristales**, no en
monedas; y el norte de un departamento **caduca** (un norte sin fecha de revision ES una deriva, no un
norte vigente).
