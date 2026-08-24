# Cerebro central y economía de monedas ("la fábrica")

Fecha: 2026-08-24
Estado: diseño aprobado en conversación; revisado adversarialmente (27 hallazgos corregidos); pendiente de revisión final de Pedro sobre este documento.

## 1. Propósito

Convertir a Calipso en una organización que corre sola: departamentos permanentes de agentes que investigan, proponen, producen y compiten por recursos, con Pedro arriba moviendo parámetros como en un RTS. El sistema completo se mide con una sola unidad de cuenta — la moneda — y la autoridad de Pedro vive en la frontera con el mundo exterior y en la disposición de su propio capital.

Este spec cubre el **cerebro central**: kernel de economía, modelo de departamento, bus de propuestas, dirección y cola de compuertas, probado con exactamente dos departamentos. Todo lo demás (mapa RTS, mezcla multi-proveedor, capa de estilo, puentes a Atlas y research-court, conectores automáticos de señales externas) queda explícitamente fuera de alcance y tendrá specs propios (sección 12).

## 2. Invariantes

Estas reglas viven en código, no en prompts. Ningún agente puede opinar en contra de ellas.

1. **Solo el mundo exterior acuña y destruye monedas.** Acuñación: plata real que entra (ventas externas cobradas) o capital que inyecta Pedro. Destrucción: recursos reales que salen (renovar suscripciones, uso de API paga, horas de Pedro). Todo movimiento interno es transferencia con suma cero.
2. **Toda acuñación entra por el módulo de frontera.** Un cobro externo acuña solo con evidencia verificable (webhook de cobro, conciliación) o con firma de Pedro. En el primer corte, toda acuñación por venta la confirma Pedro en sesión. Ningún departamento ni dirección puede autodeclarar un ingreso.
3. **Compuertas obligatorias de Pedro.** Cuatro tipos, taxativos: (a) contacto con una persona; (b) publicación; (c) compromisos de gasto real nuevos o cambiados — contratar, cancelar o cambiar de plan una suscripción, firmar un compromiso con un cliente, cualquier gasto puntual fuera de presupuesto asignado; (d) disposición de capital del tesoro por encima del mandato de dirección (sección 8). El gasto de API por uso **dentro de un presupuesto ya asignado no requiere firma**: el control de Pedro vive en la asignación del presupuesto, no en cada llamada.
4. **Las compuertas obligatorias no se esquivan pagando.** El recargo de goteo compra la posición temporal (interrumpir entre semana), nunca la compuerta en sí. Lo que sí se precia es lo opcional: comprar una opinión o revisión de Pedro.
5. **Sin sobregiro.** Toda compra se autoriza atómicamente contra el saldo disponible, con reserva previa (escrow) antes de ejecutar el gasto. Una compra que excede el saldo se rechaza. Los balances no pueden volverse negativos por vía de compra.
6. **Lo determinístico lo resuelve código, no criterio de modelo.** El libro, los balances, los precios internos, los estados de quiebra y los cierres de período son funciones puras auditables.
7. **Autoridad de escritura exclusiva por rol.** Cada rol de agente es dueño único de sus archivos; dos agentes nunca escriben el mismo artefacto.
8. **Solo el libro exterior vota.** "Funcionando" se mide con señales de afuera (ventas, consultas calificadas, clics, impresiones). Las opiniones internas y las ventas entre departamentos no cuentan como señal de éxito.
9. **Copiar método sí, artefacto nunca.** Los copiadores replican formatos y procesos propios que rinden; jamás replican artefactos ajenos (riesgo de infracción y cierre de cuentas).
10. **Umbral de evidencia antes de copiar.** Nada se declara "copiable" con n=1; hace falta mediana sobre al menos 3 resultados aceptados (disciplina heredada del spec de research-court).
11. **Nunca escalar en silencio.** La escalada de suscripción a API paga cuesta monedas reales del presupuesto del departamento y queda registrada por dirección en el libro. El presupuesto asignado es el permiso; el asiento es la trazabilidad.
12. **El precio interno de la suscripción es siempre menor que el precio de la API equivalente.** Si se invierte, los departamentos escalan "porque sale más barato" y la capacidad ya pagada se desperdicia.

## 3. La moneda

- **Anclaje:** 1 moneda = 1 USD. El libro es legible en plata real: 80 monedas quemadas son 80 dólares de recursos.
- **Precisión:** los asientos se registran en milimonedas enteras (1 moneda = 1.000 milimonedas), con redondeo al alza para destrucciones (conservador contra el tesoro). Necesario porque el costo de API por llamada es fracción de centavo.
- **Precio inicial de la hora de Pedro: 25 monedas/hora.** Es el piso de margen de contribución que Pedro declaró en el spec de research-court (USD 25 por hora activa). Es la perilla maestra: subirlo hace la fábrica más autónoma y más riesgosa; bajarlo la hace más cuidadosa y más lenta.
- **Las horas de Pedro son también capacidad, no solo precio.** Mismo patrón que la cuota de suscripción: cuota semanal declarada (sección 9), tope duro de interrupciones de goteo, y precio de goteo creciente por escasez dentro de la semana. Un departamento con caja no puede comprar más horas de las que existen.
- **Pago de horas de Pedro = destrucción.** Su tiempo es un recurso real externo al sistema, igual que un dólar de API.

## 4. El libro (kernel de economía)

### 4.0 Períodos

- **Período contable base: semanal.** Al cierre semanal corren: balances, evaluación de criterios de muerte, estados de quiebra, asignación de presupuestos, armado de la cola de sesión.
- **Ciclo mensual: renovaciones de suscripción**, alineado al ciclo de facturación de cada proveedor. Son dos cadencias anidadas y el código las trata como tales.

### 4.1 Asientos

Registro append-only de asientos tipados. Tres clases, más un registro auxiliar:

| Clase | Ejemplos | Efecto |
|---|---|---|
| Fijos periódicos | renovación de suscripciones | destrucción programada, cargada a dirección |
| Variables | API por uso, horas de Pedro, compra de capacidad interna, servicios entre departamentos | destrucción (recursos externos) o transferencia (movimientos internos) |
| Ingresos | venta externa cobrada y confirmada en frontera, capital de Pedro | acuñación |

- **Registro de acreencias:** deudas internas con orden de prelación (hoy, solo el crédito prioritario de dirección, sección 5). Una acreencia nace junto con su transferencia, se cobra con prelación en rescate o liquidación, y si no alcanza, dirección absorbe la pérdida en su rojo visible.

Propiedades que el código garantiza y los tests verifican (sección 13): transferencias internas suman cero; ninguna acuñación sin evento de frontera con evidencia o firma; ningún balance editable — solo derivable del libro; ninguna compra sin reserva previa suficiente.

### 4.2 Suscripciones: capacidad revendida

- **Dirección es dueña de todas las suscripciones.** Paga su renovación (destrucción periódica) y revende la capacidad adentro.
- **Reserva personal:** la parte de cada suscripción reservada al uso personal de Pedro queda fuera de la economía, y su costo se prorratea: la justificación de renovación compara la recaudación interna contra el **costo prorrateado a la fábrica**, no contra el costo total. Los departamentos no subsidian el uso personal.
- **Equivalencias declaradas:** cada suscripción declara su capacidad esperada por período (mensajes, tokens o unidades que el proveedor mida) y su tabla de conversión a costo API equivalente (qué costaría en dólares comprar esa unidad por API). Esa tabla hace comparable el precio interno con el precio API (invariante 12) y es dato de configuración, no opinión.
- **Precio interno:** `precio = precio_base × factor_escasez`, donde `precio_base = costo prorrateado del período / capacidad esperada de la fábrica`, y `factor_escasez` es una función monótona creciente de la razón entre fracción de cuota consumida y fracción de período transcurrido, con valor 1 cuando el consumo va a ritmo, y tope duro en `precio_API_equivalente × 0,9`. La forma exacta de la curva es decisión de implementación; la monotonía, el valor neutro y el tope son contrato.
- **Justificación de renovación (mensual):** recaudación < costo prorrateado → downgrade o cancelar; cuota agotada todos los períodos con demanda sobrante → upgrade. Renovar es un número, no una opinión. Todo cambio de plan es compuerta tipo (c): un cambio de compromiso contractual con el exterior, en cualquier dirección.
- **Circuit breaker de renovación:** la renovación automática es fail-open (sigue quemando plata real sin que nadie actúe), así que se le pone freno: si la recaudación no cubre el costo prorrateado durante 2 ciclos mensuales consecutivos y la carta de renovación no fue atendida en sesión, la siguiente renovación deja de ser automática y pasa a requerir confirmación explícita de Pedro, como ítem forzado al tope de la cola.
- La cuota se administra como **capacidad**, con el mismo patrón con que `resource_dispatcher` administra la RAM: las monedas miden plata, la cuota mide capacidad, y son cosas distintas.

### 4.3 API paga y cómputo local

- API paga entra al libro a costo real, sin margen: monedas por uso = dólares que salieron. Cada departamento tiene un techo de gasto API por período (perilla); superarlo requiere compuerta tipo (c).
- **Cómputo local cuesta exactamente 0 monedas.** Su límite es capacidad física: cuota de cómputo local por departamento (colas y RAM vía `resource_dispatcher`), con cuota reducida explícita para departamentos congelados. Así el bus no es un vector de saturación gratuita.

### 4.4 Tesoro y dirección

- El **tesoro** es la cuenta raíz: lo fondean las inyecciones de capital de Pedro. De ahí salen los presupuestos periódicos de los departamentos.
- **Pista de arranque sugerida: 3 meses de costos fijos** (~1.200 monedas con ~400/mes de suscripciones). Con cero ingresos al inicio, la pregunta honesta del proyecto es si algo acuña antes de que la pista se acabe; la pista la hace medible.
- **Dirección no quiebra**, pero su déficit es visible: si la reventa de capacidad no cubre las renovaciones prorrateadas, ese rojo es la señal contable de cancelar o achicar suscripciones. Dirección opera a costo; no acumula ganancia.

## 5. Quiebra: gracia y rescate

- Con la invariante 5 (sin sobregiro), un departamento quiebra cuando su saldo disponible se agota: entra en **estado congelado**.
- **El congelado:** conserva agentes y memoria; puede seguir proponiendo por el bus con su cuota reducida de cómputo local; no puede comprar capacidad, API ni horas de Pedro; **no recibe presupuesto periódico, ni transferencias internas entrantes, ni financiación de propuestas.** Sin esta triple prohibición, el congelamiento se escapa por rescate automático de ciclo, por rescate colusivo entre departamentos, o por financiación de propuestas — y la decisión de Pedro queda vacía.
- **Salidas del congelamiento, taxativas:** (a) rescate firmado por Pedro — acuñación de capital dirigida, decidida como una carta más en la cola de sesión, sin interrupciones; (b) acuñación externa propia — un cobro real de una venta del propio departamento, confirmado en frontera, que lo deja con saldo positivo.
- **Compromisos exteriores:** al firmar un compromiso con el exterior (compuerta tipo c), el costo estimado de cumplimiento se reserva en escrow en ese momento, y la compuerta muestra la exposición comprometida total del departamento contra su balance. Así, quebrar no libera de cumplir: lo comprometido ya está reservado. Solo el desvío sobre lo estimado lo adelanta dirección como **crédito prioritario** (acreencia con prelación, sección 4.1), porque un compromiso con el mundo exterior no se abandona por quiebra interna.
- **Cierre:** si Pedro cierra el departamento, se liquida — el saldo y las reservas pagan acreencias por prelación y el remanente vuelve al tesoro; los aprendizajes, documentos y datos quedan archivados y otro departamento puede absorberlos. El conocimiento no quiebra con la caja.

## 6. Modelo de departamento

Un departamento es cuatro cosas:

1. **Billetera:** saldo derivado del libro, con reservas (escrow) por gastos autorizados y compromisos firmados.
2. **Plantel:** agentes persistentes con roles; cada rol con autoridad de escritura exclusiva sobre sus archivos.
3. **Memoria propia:** estado, aprendizajes y artefactos, en espacio de nombres propio.
4. **Perillas de Pedro:** presupuesto por período, proporción explorar/explotar, techo de gasto API, y **agresividad** — la fracción del presupuesto del período que el departamento puede comprometer en apuestas no validadas y recursos caros (API, goteo, horas de Pedro). Cambiar perillas es gratis para Pedro: es el juego RTS. (La compuerta de mandato de la sección 8 aplica a asignaciones que **dirección** origina, no a movimientos de perillas de Pedro.)

Gastos: capacidad de suscripción (transferencia a dirección), API paga (destrucción), horas de Pedro (destrucción), servicios comprados a otros departamentos (transferencia). Ingresos: acuñación dirigida cuando algo suyo cobra afuera (vía frontera), y ventas internas de servicios.

Las ventas internas son transferencias: no acuñan y no cuentan como señal de "funcionando" (invariantes 1 y 8). Sirven para asignar costos reales a quien consume el trabajo, no para medir éxito.

**Criterio de muerte departamental:** un departamento no puede vivir para siempre reciclando presupuesto como proveedor interno de otro. Tras N períodos (perilla; sugerido 8 semanas) sin contribución trazable a acuñación externa — ni cobros propios, ni servicios vendidos a trabajos que acuñaron en ese horizonte — se dispara automáticamente una **carta de cierre** en la cola de sesión. La decisión sigue siendo de Pedro; el disparo es de código.

## 7. Bus de propuestas

- Una **propuesta** es un documento estructurado: qué se quiere hacer, presupuesto pedido en monedas, retorno esperado, compuertas de Pedro que va a necesitar, y **criterio de muerte declarado antes de empezar** (qué resultado en cuánto tiempo o gasto la mata).
- Cualquier departamento lee las propuestas de los demás y puede comentar o contraproponer dentro de su cuota de cómputo local. **Opinar es barato; ejecutar cuesta.**
- **Financiación:** la propuesta la financia el propio departamento desde su billetera si le cabe en el presupuesto; si pide más, dirección asigna del tesoro (sujeto al mandato de la sección 8); otros departamentos pueden cofinanciar con transferencias — nunca a un departamento congelado.
- Una propuesta financiada se convierte en trabajo con presupuesto propio (reservado en la billetera del financiador o transferido con destino marcado). Su criterio de muerte se evalúa por código en cada cierre semanal. **Liquidación de un trabajo muerto:** el remanente vuelve a quien lo financió, en proporción; los artefactos se archivan en la memoria del departamento.

## 8. Dirección (el cerebro)

Responsabilidades, todas dentro de las invariantes:

- Dueña de suscripciones y capacidad (sección 4.2).
- Asigna presupuestos por período desde el tesoro, dentro de un mandato con umbral. **El umbral aplica al acumulado de asignaciones por departamento por período** (perilla; sugerido 100 monedas), no a la asignación individual — un umbral por asiento se evade fraccionando, y dirección tiene el incentivo explícito de minimizar compuertas. Por encima del acumulado, toda asignación adicional a ese departamento en el período es compuerta tipo (d).
- Arma y ordena la cola de compuertas (sección 9); llega a cada compuerta con la decisión masticada.
- Ejecuta el cierre semanal (balances, criterios de muerte, quiebras, cola de sesión) y el ciclo mensual de renovaciones (justificación, circuit breaker).
- Optimiza una sola cosa: **la menor cantidad de compuertas de Pedro por unidad de resultado.** Un departamento que consume tres firmas para producir lo que otro resuelve con una está perdiendo, aunque su trabajo sea bueno.

## 9. Cola de compuertas (frontera)

Capacidad declarada de Pedro: **8-10 horas/semana, reparto mixto** — una sesión larga de 3-4 horas, goteo en bloques cortos (1-2 horas en total), y 2-3 horas reservadas a tuning de estilo. Las horas de tuning no se subastan: son trabajo de calibración.

La aritmética honesta, a ~30 minutos por compuerta: **6-8 firmas en la sesión larga más 2-4 por goteo — techo operativo de 8-12 firmas semanales.** La cuota semanal de horas de Pedro es capacidad dura (sección 3): agotada la cuota, no se venden más firmas esa semana y la cola espera.

Dos carriles:

- **Carril de sesión:** acumula todo lo que puede esperar. La fábrica trabaja la semana entera y arma una cola ordenada por **monedas en juego** — el máximo entre lo que la decisión compromete (gasto) y lo que declara desbloquear (retorno esperado). Cada ítem llega masticado: contexto, recomendación de dirección, y firma de un toque — aprobar, rechazar o editar.
- **Carril de goteo:** interrumpe entre semana. Se cobra por hora consumida con recargo de interrupción (2x, perilla), fracción mínima de 30 minutos, tope duro de interrupciones por semana (perilla; sugerido 2), y precio creciente por escasez dentro de la semana. Para una **compuerta obligatoria urgente** (un cliente que no puede esperar), el recargo compra la posición temporal, no la compuerta (invariante 4); si el departamento no puede pagarlo y hay un compromiso ya firmado de por medio, el escrow del compromiso lo cubre.

**Frontera de salida:** toda salida al mundo exterior (correo, publicación, plataforma, gasto real) pasa por un único módulo de frontera. No existen rutas de salida por fuera de él.

**Frontera de entrada:** las señales externas que alimentan la invariante 8 y los criterios de muerte (ventas, consultas, clics, impresiones) entran como eventos tipados del libro exterior. En el primer corte la ingesta es manual: Pedro las carga o confirma en la sesión semanal — igual que las acuñaciones (invariante 2). Conectores automáticos son spec futuro (sección 12).

## 10. Primer corte: dos departamentos

El cerebro central se prueba con exactamente dos departamentos que compiten de verdad por el mismo presupuesto y las mismas horas:

1. **Inteligencia de mercado** — el negocio real (Radar/research-court como cliente del método, no como molde). Es el camino más corto a acuñar la primera moneda de afuera.
2. **Market research interno** — curiosos y copiadores como hermanos dentro del mismo departamento, con la perilla explorar/explotar entre ellos. Los curiosos se proponen problemas nuevos; los copiadores replican métodos propios que ya rinden (invariantes 9 y 10). Es puro gasto especulativo al arranque.

Uno tiene ingreso a la vista, el otro no: la competencia entre ambos es el caso de prueba honesto de toda la economía.

## 11. Integración con Calipso existente

- **Módulo nuevo** (kernel de economía + dirección + bus + frontera) como paquete propio dentro de `calipso/`, sin reescribir lo existente.
- `dispatch.py` (router multi-modelo): **todo request lleva una cuenta pagadora obligatoria** — departamento, trabajo, o `personal` (fuera de la economía, descuenta de la reserva personal declarada); sin cuenta pagadora, el router rechaza. El router elige **la opción más barata que cumpla el requisito de aptitud de la tarea** (el scoring de `calipso/capabilities.py`): con eso, local gana cuando alcanza, suscripción cuando hace falta calidad, y API solo cuando no queda cuota o la asignación lo justifica. La política "suscripción > API paga > local" deja de ser regla recordada: emerge de precio más aptitud, no de prioridades fijas.
- `calipso/orchestrator.py`: hoy arma equipos ad hoc y los disuelve; el modelo de departamento generaliza su patrón hacia planteles persistentes con roles de autoridad exclusiva. Los equipos efímeros siguen existiendo para tareas sueltas.
- `calipso/resource_dispatcher.py`: sigue administrando capacidad física (RAM, colas de modelos locales); la economía administra plata. La cuota de suscripción, la cuota de cómputo local por departamento y la cuota de horas de Pedro se modelan con su mismo patrón de capacidad.
- `calipso/memory.py`: la memoria por departamento reutiliza la memoria híbrida existente con espacios de nombres por departamento.
- La UI existente gana después una vista de tablero (el mapa RTS, spec futuro); el primer corte se opera por API y archivos.

## 12. Fuera de alcance (specs futuros)

- **Mapa RTS:** la vista de tablero con tesoro, líneas y perillas. Es una vista del cerebro, no lógica nueva.
- **Mezcla multi-proveedor:** presupuesto y cuota por proveedor (Claude, Codex, otros), con la misma mecánica de capacidad.
- **Capa de estilo:** ASD-STE100 y anti-look-IA; consume las horas de tuning reservadas.
- **Conectores de señales externas:** ingesta automática de ventas, métricas y cobros (webhooks, conciliación). Hasta entonces, ingesta manual en sesión (sección 9).
- **Puentes:** Atlas/Observatory-Global y research-court entran como departamentos invitados con billetera propia, no como fundamento del sistema.

## 13. Verificación

- El kernel de economía se desarrolla con **pytest de verdad** (como `test_resource_dispatcher.py`, no como los scripts `test_*.py` con `main()`).
- Tests de propiedades del libro: transferencias suman cero; ninguna acuñación sin evento de frontera con evidencia o firma; balances siempre derivables y reproducibles desde el libro; ninguna compra sin reserva previa suficiente (sin sobregiro); precio interno de suscripción < precio API equivalente en todo estado; congelado no puede comprar **ni recibir transferencias internas, presupuesto ni financiación**; el umbral de mandato se evalúa sobre el acumulado por departamento y período.
- **Simulación de ciclo completo** con departamentos sintéticos y reloj acelerado: N períodos con gastos, una venta externa simulada, una quiebra con intento de rescate colusivo (debe fallar), un rescate firmado, un circuit breaker de renovación disparado y un cierre con liquidación por prelación — sin intervención manual.
- Criterio de aceptación del primer corte: un ciclo semanal completo real — propuestas, asignación, gasto medido, cola de sesión armada y firmada por Pedro, cierre de período con balances correctos — con los dos departamentos vivos.

## 14. Criterios de éxito

- La fábrica registra **cada** moneda que entra y sale; el tablero nunca muestra prosperidad que el mundo exterior no confirme.
- Pedro opera el sistema dentro de su cuota semanal (8-12 firmas más tuning) sin que la cola de sesión crezca semana a semana.
- Las suscripciones quedan justificadas, achicadas o canceladas por números del libro, no por intuición.
- La métrica que decide si el proyecto vive: **monedas acuñadas de afuera antes de agotar la pista de arranque.**
