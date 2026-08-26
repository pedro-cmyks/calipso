# El plantel — que los departamentos tengan a alguien adentro

Fecha: 2026-08-26
Estado: diseño acordado en conversación; pendiente de revisión de Pedro sobre este documento.

## 1. Propósito

Hoy la economía de Calipso es contabilidad sin fábrica. Un `Departamento` es nombre, zona, presupuesto y dos perillas que nadie lee: `explorar_explotar_pct` y `agresividad_pct` aparecen exactamente dos veces en todo el código, donde se declaran. Nadie crea propuestas en el bus fuera de los tests. El único gasto que existe es Pedro hablando por el chat.

Este spec pone a alguien adentro de cada departamento: **el jefe**, un agente persistente que mira su situación, decide y contrata. Con eso, la economía deja de ser un cinturón de seguridad sin auto: el sobregiro imposible, los techos y las compuertas existen precisamente para que un agente pueda trabajar solo sin que Pedro lo vigile.

## 2. Invariantes

1. **Decidir es gratis; actuar cuesta.** El bucle que corre seguido usa el escalón local. Un departamento que no tiene nada que hacer cuesta cero.
2. **El presupuesto es el freno, no la buena voluntad.** Ningún permiso del jefe puede pasar por encima del kernel: sin saldo no hay acción, y el chequeo vive en el libro, no en el prompt.
3. **La suscripción es costo hundido.** La unidad no usada no se ahorra: se pierde. La fábrica tiene que gastarla, y el precio es lo que lo hace racional para quien la compra.
4. **La API paga es costo marginal.** Ahí sí se minimiza, contra el techo declarado por Pedro.
5. **Un jefe no habla con el mundo.** Propone, trabaja y comenta hacia adentro. Toda salida al exterior sigue pasando por la frontera de salida, que este spec no construye.
6. **Todo lo que el jefe piensa se ve.** Cada decisión se publica al pulso, incluso la de no hacer nada. Un jefe que decide en silencio es indistinguible de uno colgado.
7. **Pedro puede parar todo en un toque**, sin reiniciar el servidor y sin abrir una terminal.

## 3. El jefe

Un agente persistente por departamento registrado. Su identidad **es** el departamento: no tiene nombre propio ni personalidad separada.

Tiene cuatro cosas, de las cuales tres ya existen:

| pata | estado hoy |
|---|---|
| **Billetera** | existe: su cuenta en el libro, con saldo derivado y escrows |
| **Perillas** | existen y están muertas: nadie las lee |
| **Memoria propia** | el mecanismo existe (`memory.Scope`: markdown núcleo + episódica Chroma); falta el espacio de nombres |
| **Bucle** | no existe |

La memoria del departamento vive en `CALIPSO_HOME/memoria/departamento/<nombre>/`, como un `Scope` más. El jefe lee su núcleo en cada tic (es markdown, es gratis) y escribe aprendizajes después de actuar.

**No tiene varios roles.** El spec de la economía dice "agentes persistentes con roles", en plural; este primer corte trae uno solo, porque el trabajo real lo hacen los equipos que contrata. La autoridad de escritura exclusiva que ese plural buscaba ya la cubre el sistema de propuestas, que exige la firma de Pedro para tocar un archivo. Si el jefe se queda corto, agregar roles es una extensión, no un rediseño.

## 4. El bucle: mirar, decidir, actuar

Corre sobre el ticker de `calipso/routines.py`, con una rutina por departamento (`kind: "departamento"`). Cada tic hace tres cosas, en orden de costo creciente.

### 4.1 Mirar — gratis, puro

Una función pura `situacion(asientos, registro, bus, cola, suscripciones, semana, nombre) -> dict` que pliega del libro todo lo que el jefe necesita:

- saldo disponible y escrows comprometidos;
- trabajos vivos de los que es dueño, con su gasto contra su criterio de muerte;
- propuestas del bus: las propias y las ajenas sobre las que todavía no opinó;
- compuertas suyas pendientes en la cola;
- capacidad de suscripción disponible, **su precio ahora mismo** y la fracción del ciclo transcurrida;
- qué cambió desde el tic anterior.

Cero llamadas a modelos. Es la misma clase de función que `mapa/ciudad.py`: determinística, testeable contra un libro sintético.

### 4.2 Decidir — barato, local

La situación se compila a un prompt corto y va al escalón local (`qwen2.5:3b`, ya instalado y ya usado como clasificador). El jefe devuelve **una** decisión estructurada:

```
nada | proponer | trabajar <id> | comentar <id>
```

más un renglón de motivo. La respuesta se valida contra ese conjunto: lo que no parsea es `nada`. Un modelo que alucina no puede gastar.

La decisión se publica al pulso siempre, incluida `nada`.

### 4.3 Actuar — caro, y solo si hace falta

Si la decisión no es `nada` y los frenos de la sección 7 lo permiten, el jefe **contrata un equipo efímero** por el orquestador que ya existe (`orchestrator.plan` / `build_team` / `agent_system`) y lo paga de su billetera con cuenta pagadora `dep:<nombre>`.

El orquestador no cambia: se lo usa como biblioteca. Lo que cambia es quién lo llama y quién paga.

## 5. Las perillas dejan de ser decoración

- **`agresividad_pct`** — la fracción del presupuesto del período que el departamento puede comprometer en apuestas no validadas. Es un tope duro que se chequea **antes** de actuar, contra lo ya comprometido en el período. Un departamento con agresividad 0 solo trabaja lo ya financiado.
- **`explorar_explotar_pct`** — el sesgo entre `proponer` (explorar) y `trabajar` (explotar). **La modulación por precio se calcula en código, no en el prompt**: una función pura toma la perilla y el precio actual de la capacidad (sección 6) y devuelve el sesgo efectivo, que entra al prompt ya resuelto como una preferencia en palabras. Pedirle aritmética de precios a un modelo de 3b es pedirle lo único que no sabe hacer. Capacidad barata a fin de ciclo empuja a explorar; capacidad cara empuja a terminar lo empezado.

Mover una perilla tiene que cambiar el comportamiento observable en el próximo tic. Ese es el criterio de que dejaron de ser decoración.

## 6. El precio de la capacidad: usar la suscripción del todo

`capacidad.precio_unidad_mm` ya calcula el número correcto y después lo tira:

```python
r_pct = consumido * 100 * 100 // (capacidad_fabrica * fraccion_pct)
return min(precio_base_mm * max(100, r_pct) // 100, tope_mm)
```

`r_pct` compara lo consumido contra lo transcurrido del ciclo. Ir rápido lo sube por encima de 100 y la unidad se encarece, que es correcto. Ir atrasado lo baja por debajo de 100 — y el `max(100, ...)` lo pisa. **Ir atrasado no tiene descuento**, así que la capacidad se evapora a precio de lista.

Eso importa porque comprar capacidad **sí le cuesta plata al departamento**, aunque para la fábrica el costo esté hundido. Un departamento racional sub-usa la suscripción que la fábrica ya pagó.

**El cambio:** el piso pasa de 100 a una perilla, `PISO_FACTOR_PCT`, sugerida en 40. Con `claude_max` a 200 monedas y 1.800 unidades de fábrica por ciclo (base 100 mm):

| consumido | ciclo transcurrido | precio hoy | con piso 40 |
|---|---|---|---|
| 1.440 | 50% | 160 mm | 160 mm |
| 900 | 50% | 100 mm | 100 mm |
| 360 | 50% | 100 mm | **40 mm** |
| 90 | 100% | 100 mm | **40 mm** |

**Consecuencia en la renovación.** Unidades baratas significan que dirección recauda menos por unidad, así que la decisión de renovar no puede seguir siendo rojo contra negro: una suscripción usada al 100% con descuento se leería como fracaso. La renovación pasa a mirar **dos ejes**: recaudación y utilización. Rojo con utilización alta dice "está bien usada y sale cara: negociá o achicá". Rojo con utilización baja dice "nadie la usa: cancelá".

## 7. Los frenos

Ninguno es opcional: esto gasta plata mientras Pedro duerme.

- **Sin sobregiro** — lo garantiza el kernel. Un departamento sin saldo no puede actuar, y no hay prompt que lo evite.
- **Interruptor general** — `POST /api/plantel/parar` y `/reanudar`, respaldados por un archivo en `CALIPSO_HOME/economia/plantel.json`. Se chequea al principio de cada tic. Sobrevive al reinicio del servidor y se puede tocar desde el teléfono.
- **Modo ensayo** — `plantel.json` lleva `modo: ensayo | vivo`. En ensayo el jefe mira, decide y publica al pulso, pero no contrata ni gasta. **Arranca en ensayo.** Se pasa a vivo cuando Pedro miró un par de días qué decide.
- **Techo de tics por período** — vive en `plantel.json`, no en el registro de departamentos: agregarle un campo al dataclass obligaría a migrar el JSON del registro por una perilla operativa. Un bug no puede girar.
- **Decidir no toca el libro** — el escalón de decisión es local y gratis, así que un departamento sin nada que hacer no consume nada.

## 8. La zona personal

`personal:trabajo` y `personal:finanzas` llevan el mismo jefe, con tres diferencias que ya declara el spec de la economía: no quiebran, no compiten, y pagan con la reserva personal en vez de comprar capacidad de fábrica.

La memoria de `personal:trabajo` es donde vive el contexto de los proyectos que Pedro corre para su empleo: es el `Scope` del departamento, y el jefe lo lee en cada tic.

## 9. Qué ve el mapa

Nada nuevo que construir. El jefe publica al pulso con `departamento=<cuenta>` y `rol="jefe"`; los equipos que contrata publican los suyos. Los escritorios del interior se llenan solos — que es para lo que se construyeron y nunca mostraron a nadie más que un turno de chat.

## 10. Integración con lo existente

- `calipso/routines.py` — un `kind` nuevo. El motor, el ticker y los endpoints ya existen.
- `calipso/orchestrator.py` — **no se toca**: se usa como biblioteca.
- `calipso/memory.py` — un `Scope` por departamento; el resto no cambia.
- `calipso/economia/capacidad.py` — el piso del factor.
- `calipso/economia/cierre.py` — la renovación de dos ejes.
- `calipso/economia/departamentos.py` — sin cambios de forma: las perillas ya están, lo que falta es que alguien las lea.
- El pulso y el mapa se consumen tal cual.

## 11. Fuera de alcance

- **Varios roles por departamento.** Uno alcanza para probar que el bucle sirve.
- **Que los departamentos se hablen directo.** Ya se hablan por el bus.
- **Elegir modelo por proveedor.** Es el spec de mezcla multi-proveedor, que este spec no necesita: alcanza con el escalón local para decidir y el orquestador para actuar.
- **El protocolo de inventario de specs por departamento.** Spec propio, y necesita éste primero: sin memoria de departamento no tiene dónde vivir.
- **La frontera de salida.** Un jefe no puede mandar un correo ni publicar nada, así que **después de este spec la fábrica todavía no puede vender**. Trabaja hacia adentro. Acuñar la primera venta sigue exigiendo la frontera de salida, que es otro spec.

## 11 bis. Nota de alcance

El diseño es uno solo, pero la implementación se puede partir en dos planes sin romper nada: el bucle con sus frenos (secciones 3, 4, 7, 8) es independiente del precio y la renovación (secciones 5 y 6). Si se parte, el bucle va primero: el precio sin nadie que compre capacidad no cambia ningún comportamiento.

## 12. Verificación

- **Mirar** es puro: se testea contra un libro sintético, comparando la situación derivada campo por campo. Sin modelos.
- **Decidir** se testea con un doble del modelo local: se le hace devolver cada una de las cuatro decisiones, más basura, y se verifica que la basura cae en `nada`.
- **Los frenos**, uno por uno: sin saldo no actúa; el interruptor apagado no corre un tic; en ensayo no se escribe un solo asiento; pasado el techo de tics no despierta.
- **Las perillas**: dos corridas con la misma situación y distinta `agresividad_pct` producen decisiones distintas. Si no, la perilla sigue muerta.
- **El precio**: la tabla de la sección 6, como test de valores exactos.
- **El ciclo completo**: una simulación donde un departamento con presupuesto propone, financia, trabaja y ve bajar su saldo, sin que nadie le hable.

## 13. Criterios de éxito

- Un departamento propone algo sin que Pedro le hable.
- Pedro mueve `agresividad_pct` y el departamento cambia lo que se anima a hacer en el próximo tic.
- Al cerrar el ciclo, la capacidad de suscripción está usada y no evaporada.
- El mapa muestra escritorios ocupados por alguien que no es el chat de Pedro.
- El interruptor para todo en un toque, y `plantel.json` lo recuerda después de reiniciar.
