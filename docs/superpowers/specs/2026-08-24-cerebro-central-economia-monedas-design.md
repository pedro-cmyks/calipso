# Cerebro central y economía de monedas ("la fábrica")

Fecha: 2026-08-24
Estado: diseño aprobado en conversación; revisión adversarial 1 aplicada (27 hallazgos); revisión adversarial 2 aplicada (19 hallazgos sobre pedro-token, eficiencia y zona personal); pendiente de revisión final de Pedro sobre este documento.

## 1. Propósito

Convertir a Calipso en una organización que corre sola: departamentos permanentes de agentes que investigan, proponen, producen y compiten por recursos, con Pedro arriba moviendo parámetros como en un RTS. El sistema se mide con dos divisas — la **moneda** (anclada al dólar) para todo lo que es plata, y el **pedro-token (PT)** para el tiempo firmable de Pedro — y tiene dos zonas en el mismo mapa: la **fábrica** (departamentos que compiten por el tesoro) y la **zona personal** (departamentos de Pedro, financiados por su cuenta, que no compiten).

Este spec cubre el **cerebro central**: kernel de economía, modelo de departamento, bus de propuestas, dirección y cola de compuertas, probado con dos departamentos que compiten más el departamento personal de finanzas. Todo lo demás (mapa RTS, mezcla multi-proveedor, capa de estilo, puentes a Atlas y research-court, conectores automáticos de señales externas y bancarios) queda explícitamente fuera de alcance y tendrá specs propios (sección 12).

## 2. Invariantes

Estas reglas viven en código, no en prompts. Ningún agente puede opinar en contra de ellas.

1. **Solo el mundo exterior acuña y destruye monedas.** La acuñación tiene dos subtipos asentados distinto en el libro: **venta externa** (plata real cobrada por algo que la fábrica vendió) y **capital** (plata nueva que inyecta Pedro, incluidos rescates fondeados con plata nueva). Destrucción: recursos reales que salen (renovar suscripciones, uso de API paga, retiros de Pedro desde su cuenta). Todo movimiento interno — incluidos los pagos por horas de Pedro, que van a su cuenta — es transferencia con suma cero.
2. **Solo las horas firmables de Pedro emiten PT.** La emisión semanal es fija e igual a su cuota firmable declarada — las horas de compuerta (sesión más goteo), sin las horas de tuning, que no emiten PT. De la emisión, la **reserva personal de PT** (perilla semanal) se aparta para la zona personal antes de ofrecer el resto a la fábrica. Ningún saldo de monedas puede crear PT; ningún agente puede emitirlos.
3. **El tipo de cambio del PT es una función determinística del rendimiento realizado.** Lo calcula código sobre el libro con la fórmula de la sección 3.2; ni Pedro a mano en caliente ni ningún agente lo fijan. La perilla de Pedro es la fórmula, no el número del día.
4. **Toda acuñación entra por el módulo de frontera.** Un cobro externo acuña solo con evidencia verificable (webhook de cobro, conciliación) o con firma de Pedro. En el primer corte, toda acuñación por venta la confirma Pedro en sesión. Ningún departamento ni dirección puede autodeclarar un ingreso.
5. **Compuertas obligatorias de Pedro.** Cuatro tipos, taxativos: (a) contacto con una persona; (b) publicación; (c) compromisos de gasto real nuevos o cambiados — contratar, cancelar o cambiar de plan una suscripción, firmar un compromiso con un cliente, ampliar la reserva personal, cualquier gasto puntual fuera de presupuesto asignado; (d) disposición de capital del tesoro por encima del mandato de dirección (sección 8). El gasto de API por uso **dentro de un presupuesto ya asignado no requiere firma**: el control de Pedro vive en la asignación del presupuesto, no en cada llamada.
6. **Las compuertas obligatorias no se esquivan pagando, ni se bloquean por falta de caja.** El recargo de goteo compra la posición temporal, nunca la compuerta en sí. Y una compuerta obligatoria de un departamento sin monedas no se cae: dirección adelanta su costo en PT como crédito prioritario (secciones 5 y 9). Lo que sí se precia y sí puede rechazarse por precio es lo opcional: comprar una opinión o revisión de Pedro.
7. **Sin sobregiro, en ninguna divisa.** Toda compra o transferencia se autoriza atómicamente contra el saldo disponible de quien paga, con reserva previa (escrow) antes de ejecutar el gasto. Lo que excede el saldo se rechaza. Ningún balance puede volverse negativo por compra ni transferencia.
8. **Lo determinístico lo resuelve código, no criterio de modelo.** El libro, los balances, los precios internos, el tipo de cambio del PT, la eficiencia, los estados de quiebra y los cierres de período son funciones puras auditables.
9. **Autoridad de escritura exclusiva por rol.** Cada rol de agente es dueño único de sus archivos; dos agentes nunca escriben el mismo artefacto. Todas las billeteras — de la fábrica y de la zona personal — viven en el libro general y las escribe solo el kernel.
10. **Solo el libro exterior vota.** "Funcionando" se mide con señales de afuera (ventas, consultas calificadas, clics, impresiones). Las opiniones internas y las ventas entre departamentos no cuentan como señal de éxito.
11. **Los libros personales de Pedro son privados.** Cubren sus finanzas del mundo real (ingresos propios, gastos propios). Solo el departamento personal de finanzas (sección 10.1) los lee y escribe. Las billeteras internas — incluida la cuenta de Pedro — no son libros personales: viven en el libro general (invariante 9) y el departamento personal las consolida en su tablero como lector.
12. **La zona personal no compite en el mercado interno.** Un departamento personal no puede comprar capacidad de suscripción de la fábrica, API de la fábrica, PT de la emisión de fábrica ni goteo. Su cómputo va por la cuenta pagadora `personal` contra la reserva personal declarada; sus horas de Pedro salen de la reserva personal de PT. Sí puede comprar **servicios** a departamentos de la fábrica (transferencia interna normal).
13. **Copiar método sí, artefacto nunca.** Los copiadores replican formatos y procesos propios que rinden; jamás replican artefactos ajenos (riesgo de infracción y cierre de cuentas).
14. **Umbral de evidencia antes de copiar.** Nada se declara "copiable" con n=1; hace falta mediana sobre al menos 3 resultados aceptados (disciplina heredada del spec de research-court).
15. **Nunca escalar en silencio.** La escalada de suscripción a API paga cuesta monedas reales del presupuesto del departamento y queda registrada por dirección en el libro. El presupuesto asignado es el permiso; el asiento es la trazabilidad.
16. **El precio interno de la suscripción es siempre menor que el precio de la API equivalente.** Si se invierte, los departamentos escalan "porque sale más barato" y la capacidad ya pagada se desperdicia.

## 3. Las divisas

### 3.1 La moneda

- **Anclaje:** 1 moneda = 1 USD. El libro es legible en plata real: 80 monedas quemadas son 80 dólares de recursos.
- **Precisión:** los asientos se registran en milimonedas enteras (1 moneda = 1.000 milimonedas), con redondeo al alza para destrucciones (conservador contra el tesoro). Necesario porque el costo de API por llamada es fracción de centavo.

### 3.2 El pedro-token (PT)

El tiempo de Pedro no cotiza en monedas: cotiza en su propia divisa, para que sus horas no se mezclen con la plata y su valor siga a sus resultados.

- **Unidad:** 1 PT = 1 hora firmable de Pedro; divisible en mili-PT (una compuerta de 30 minutos consume 500 mili-PT).
- **Emisión (invariante 2):** semanal y fija, igual a la cuota firmable — sesión más goteo, **4-6 PT** con el reparto declarado de la sección 9. Las horas de tuning no emiten PT. La reserva personal de PT se aparta primero; el resto se ofrece a la fábrica. Los PT no consumidos al cierre expiran sin efecto monetario — el tiempo no se acumula.
- **Cobro en el servicio, no por adelantado:** al encolar una compuerta, el departamento reserva en escrow las monedas necesarias al tipo de cambio vigente; cuando la firma efectivamente se sirve, se ejecutan la transferencia a la cuenta de Pedro y el consumo del PT; si la semana cierra sin servirse, la reserva se libera íntegra. Nadie paga horas no trabajadas, dirección no puede confiscar por vía de no atender la cola, y no existe incentivo de quemar PT ya pagados a fin de semana.
- **Tipo de cambio, contrato completo:** `tipo = total de monedas acuñadas por venta externa en la ventana / total de PT consumidos por la fábrica en la ventana`, con ventana móvil de 8 semanas (perilla; si el ciclo de venta del negocio la supera, se agranda) y estas reglas de borde: (a) solo acuñaciones subtipo **venta externa** — el capital que inyecta Pedro y los rescates no entran al numerador; (b) solo PT consumidos por la fábrica — el consumo personal queda fuera de numerador y denominador; los PT expirados no cuentan como consumidos; (c) ventana sin PT consumidos → el tipo se mantiene; (d) mientras la ventana tenga menos de 4 semanas con consumo, rige el valor de arranque; (e) la variación por cierre semanal está acotada a una banda máxima (perilla; sugerido ±25%), que amortigua la realimentación precio→consumo→precio; (f) mínimo 1 moneda/PT.
- **Arranque: 5 monedas/PT.** Barato mientras nada vende — la fábrica no se desangra pagando a Pedro cuando todo lo requiere — y caro cuando sus horas demuestran convertirse en ingreso, que es cuando conviene economizarlas.
- **Líneas de referencia (no son pisos ni topes; el flotante puro se mantiene):** el tablero dibuja dos líneas para leer el tipo de cambio. **La línea del empleo: ≈14,5 monedas/hora** — el precio que el mercado le paga hoy al tiempo de Pedro: 2.500 USD/mes por disponibilidad L-V 8:00-16:00 más desbordes ≈ 40 h/semana ≈ 173 h/mes (perilla: se recalcula si cambian sueldo u horario). Es conservadora, porque el empleo compra *disponibilidad* y la fábrica compra *horas activas marginales*, que valen más. **La línea de research-court: 25 monedas/hora** — el piso de margen de contribución que Pedro declaró para su trabajo por fuera del empleo. PT sostenido sobre 14,5: la fábrica paga la hora de Pedro mejor que su empleador. Sobre 25: cumple su margen objetivo de horas marginales.
- **La cuenta de Pedro:** billetera de Pedro en la frontera, **dentro del libro general** (la escribe solo el kernel; el departamento personal la lee y consolida). Recibe los pagos por PT: es su sueldo visible. Salidas del saldo, taxativas y con chequeo de saldo (invariante 7): (1) **retiro** — destrucción, plata que se lleva; (2) **reinyección al tesoro** — transferencia, no acuña; (3) **financiación de departamentos personales** — transferencia; (4) **rescate dirigido a un departamento congelado** — transferencia, la única que un congelado puede recibir (sección 5).
- Usar el tiempo de Pedro ya no achica la masa monetaria de la fábrica: la recicla a través de su cuenta. Lo que sí consume es PT, que expira semana a semana.

## 4. El libro (kernel de economía)

### 4.0 Períodos

- **Período contable base: semanal.** Al cierre semanal corren: balances, evaluación de criterios de muerte, estados de quiebra, asignación de presupuestos, emisión y expiración de PT, liberación de reservas no servidas, recálculo del tipo de cambio, armado de la cola de sesión.
- **Ciclo mensual: renovaciones de suscripción**, alineado al ciclo de facturación de cada proveedor. Son dos cadencias anidadas y el código las trata como tales.

### 4.1 Asientos

Registro append-only de asientos tipados, en dos divisas. Clases:

| Clase | Ejemplos | Efecto |
|---|---|---|
| Fijos periódicos | renovación de suscripciones | destrucción programada de monedas, cargada a dirección |
| Variables | API por uso, compra de capacidad interna, servicios entre departamentos, pago de PT al servirse una firma | destrucción (recursos externos), transferencia (movimientos internos; los pagos por PT van a la cuenta de Pedro) |
| Ingresos | venta externa cobrada y confirmada en frontera (subtipo venta), capital nuevo de Pedro (subtipo capital) | acuñación de monedas, con subtipo obligatorio |
| PT | emisión semanal, consumo al servirse, expiración al cierre, apunte de costo de oportunidad del consumo personal | emisión, consumo y expiración de PT; el apunte personal es informativo, no mueve monedas |

- **Registro de acreencias:** deudas internas con orden de prelación (el crédito prioritario de dirección, secciones 5 y 9). Una acreencia nace junto con su transferencia o adelanto, se cobra con prelación en rescate o liquidación, y si no alcanza, dirección absorbe la pérdida en su rojo visible.

Propiedades que el código garantiza y los tests verifican (sección 13): transferencias internas suman cero por divisa; ninguna acuñación sin evento de frontera con evidencia o firma, y siempre con subtipo; ninguna emisión de PT fuera de la cuota firmable; ningún balance editable — solo derivable del libro; ninguna compra ni transferencia sin saldo y reserva previa suficientes.

### 4.2 Suscripciones: capacidad revendida

- **Dirección es dueña de todas las suscripciones.** Paga su renovación (destrucción periódica) y revende la capacidad adentro.
- **Reserva personal:** la parte de cada suscripción reservada al uso personal de Pedro y su zona personal queda fuera de la economía de la fábrica, y su costo se prorratea: la justificación de renovación compara la recaudación interna contra el **costo prorrateado a la fábrica**, no contra el costo total. Los departamentos no subsidian el uso personal — ni por prorrateo ni por precio: el consumo personal no toca la cuota de la fábrica ni su factor de escasez. Ampliar la reserva personal cambia el prorrateo y es compuerta tipo (c).
- **Equivalencias declaradas:** cada suscripción declara su capacidad esperada por período (mensajes, tokens o unidades que el proveedor mida) y su tabla de conversión a costo API equivalente (qué costaría en dólares comprar esa unidad por API). Esa tabla hace comparable el precio interno con el precio API (invariante 16), normaliza la eficiencia entre proveedores, y es dato de configuración, no opinión.
- **Precio interno:** `precio = precio_base × factor_escasez`, donde `precio_base = costo prorrateado del período / capacidad esperada de la fábrica`, y `factor_escasez` es una función monótona creciente de la razón entre fracción de cuota consumida y fracción de período transcurrido, con valor 1 cuando el consumo va a ritmo, y tope duro en `precio_API_equivalente × 0,9`. La forma exacta de la curva es decisión de implementación; la monotonía, el valor neutro y el tope son contrato.
- **Eficiencia, contrato completo:** `eficiencia = monedas acuñadas por venta externa atribuidas / costo API equivalente de la capacidad consumida`, un número adimensional comparable entre suscripciones, departamentos y trabajos. Atribución: cada acuñación por venta se prorratea entre los consumos del trabajo que la originó, **proporcional al costo interno pagado por cada consumo** (para capacidad de suscripción, su costo API equivalente). Ventana: las mismas 8 semanas del tipo de cambio. Los entregables aceptados se llevan aparte como serie de conteo informativa — no se mezclan en el número. El numerador es siempre señal exterior (invariante 10).
- **Justificación de renovación (mensual), con dos ejes:** utilización (recaudación vs costo prorrateado) y eficiencia. Recaudación < costo prorrateado → downgrade o cancelar; cuota agotada todos los períodos con demanda sobrante → upgrade; utilización alta con eficiencia baja sostenida — 2 ciclos mensuales consecutivos, y **en todos sus cortes por departamento**, para que un departamento explorador no arrastre a la suscripción que otro convierte bien — → candidata a reasignar cuota entre departamentos antes que a ampliar. La eficiencia es señal de reasignación, no de muerte: la exploración madura con rezago y su disciplina es el criterio de muerte por propuesta, no esta métrica. Renovar es un número, no una opinión. Todo cambio de plan es compuerta tipo (c).
- **Circuit breaker de renovación:** si la recaudación no cubre el costo prorrateado durante 2 ciclos mensuales consecutivos y la carta de renovación no fue atendida en sesión, la siguiente renovación deja de ser automática y pasa a requerir confirmación explícita de Pedro, como ítem forzado al tope de la cola.
- La cuota se administra como **capacidad**, con el mismo patrón con que `resource_dispatcher` administra la RAM: las monedas miden plata, la cuota mide capacidad, y son cosas distintas.

### 4.3 API paga y cómputo local

- API paga entra al libro a costo real, sin margen: monedas por uso = dólares que salieron. Cada departamento tiene un techo de gasto API por período (perilla); superarlo requiere compuerta tipo (c).
- **Cómputo local cuesta exactamente 0 monedas.** Su límite es capacidad física: cuota de cómputo local por departamento (colas y RAM vía `resource_dispatcher`), con cuota reducida explícita para departamentos congelados. Así el bus no es un vector de saturación gratuita.

### 4.4 Tesoro y dirección

- El **tesoro** es la cuenta raíz de la fábrica: lo fondean las inyecciones de capital de Pedro (acuñación subtipo capital si es plata nueva; transferencia si reinyecta desde su cuenta). De ahí salen los presupuestos periódicos de los departamentos y el presupuesto de PT de dirección (sección 9).
- **Pista de arranque sugerida: 3 meses de costos fijos** (~1.200 monedas con ~400/mes de suscripciones). Con cero ingresos al inicio, la pregunta honesta del proyecto es si algo acuña ventas antes de que la pista se acabe; la pista la hace medible.
- **Dirección no quiebra**, pero su déficit es visible: si la reventa de capacidad no cubre las renovaciones prorrateadas, ese rojo es la señal contable de cancelar o achicar suscripciones. Dirección opera a costo; no acumula ganancia.

## 5. Quiebra: gracia y rescate

- Con la invariante 7 (sin sobregiro), un departamento quiebra cuando su saldo disponible se agota: entra en **estado congelado**.
- **El congelado:** conserva agentes y memoria; puede seguir proponiendo por el bus con su cuota reducida de cómputo local; no puede comprar capacidad, API ni firmas; **no recibe presupuesto periódico, ni transferencias internas entrantes, ni financiación de propuestas** — con una única excepción: el asiento de rescate firmado por Pedro. Sin esta prohibición, el congelamiento se escapa por rescate automático de ciclo, por rescate colusivo entre departamentos, o por financiación de propuestas — y la decisión de Pedro queda vacía.
- **Salidas del congelamiento, taxativas:** (a) rescate firmado por Pedro — desde su cuenta (transferencia exceptuada) o con plata nueva (acuñación subtipo capital), decidido como una carta más en la cola de sesión; (b) acuñación por venta externa propia, confirmada en frontera, que lo deja con saldo positivo. Las compuertas obligatorias que la salida (b) exija (contactar, publicar, confirmar el cobro) no requieren caja: las adelanta dirección como crédito prioritario (invariante 6, sección 9), así la salida (b) no es letra muerta.
- **Compromisos exteriores:** al firmar un compromiso con el exterior (compuerta tipo c), el costo estimado de cumplimiento en monedas se reserva en escrow en ese momento, y las horas de Pedro que requiera se reservan como capacidad en las cuotas semanales correspondientes; la compuerta muestra la exposición comprometida total del departamento contra su balance. Así, quebrar no libera de cumplir: lo comprometido ya está reservado. Solo el desvío sobre lo estimado lo adelanta dirección como **crédito prioritario** (acreencia con prelación, sección 4.1), porque un compromiso con el mundo exterior no se abandona por quiebra interna.
- **Cierre:** si Pedro cierra el departamento, se liquida — el saldo y las reservas pagan acreencias por prelación y el remanente vuelve al tesoro; los aprendizajes, documentos y datos quedan archivados y otro departamento puede absorberlos. El conocimiento no quiebra con la caja.

## 6. Modelo de departamento

Un departamento es cuatro cosas:

1. **Billetera:** saldo de monedas derivado del libro, con reservas (escrow) por gastos autorizados, compuertas encoladas y compromisos firmados.
2. **Plantel:** agentes persistentes con roles; cada rol con autoridad de escritura exclusiva sobre sus archivos.
3. **Memoria propia:** estado, aprendizajes y artefactos, en espacio de nombres propio.
4. **Perillas de Pedro:** presupuesto por período, proporción explorar/explotar, techo de gasto API, y **agresividad** — la fracción del presupuesto del período que el departamento puede comprometer en apuestas no validadas y recursos caros (API, goteo, firmas). Cambiar perillas es gratis para Pedro: es el juego RTS. (La compuerta de mandato de la sección 8 aplica a asignaciones que **dirección** origina, no a movimientos de perillas de Pedro.)

Gastos: capacidad de suscripción (transferencia a dirección), API paga (destrucción), firmas en PT (transferencia a la cuenta de Pedro al servirse), servicios comprados a otros departamentos (transferencia). Ingresos: acuñación subtipo venta cuando algo suyo cobra afuera (vía frontera), y ventas internas de servicios — incluidas las ventas de servicios a la zona personal.

Las ventas internas son transferencias: no acuñan y no cuentan como señal de "funcionando" (invariantes 1 y 10). Sirven para asignar costos reales a quien consume el trabajo, no para medir éxito.

**Criterio de muerte departamental:** un departamento no puede vivir para siempre reciclando presupuesto como proveedor interno de otro. Tras N períodos (perilla; sugerido 8 semanas) sin contribución trazable a acuñación por venta externa — ni cobros propios, ni servicios vendidos a trabajos que acuñaron en ese horizonte — se dispara automáticamente una **carta de cierre** en la cola de sesión. La decisión sigue siendo de Pedro; el disparo es de código.

## 7. Bus de propuestas

- Una **propuesta** es un documento estructurado: qué se quiere hacer, presupuesto pedido en monedas (y horas de firma estimadas), retorno esperado, compuertas de Pedro que va a necesitar, y **criterio de muerte declarado antes de empezar** (qué resultado en cuánto tiempo o gasto la mata).
- Cualquier departamento lee las propuestas de los demás y puede comentar o contraproponer dentro de su cuota de cómputo local. **Opinar es barato; ejecutar cuesta.**
- **Financiación:** la propuesta la financia el propio departamento desde su billetera si le cabe en el presupuesto; si pide más, dirección asigna del tesoro (sujeto al mandato de la sección 8); otros departamentos pueden cofinanciar con transferencias — nunca a un departamento congelado.
- Una propuesta financiada se convierte en trabajo con presupuesto propio (reservado en la billetera del financiador o transferido con destino marcado). Su criterio de muerte se evalúa por código en cada cierre semanal. **Liquidación de un trabajo muerto:** el remanente vuelve a quien lo financió, en proporción; los artefactos se archivan en la memoria del departamento.

## 8. Dirección (el cerebro)

Responsabilidades, todas dentro de las invariantes:

- Dueña de suscripciones y capacidad (sección 4.2).
- Asigna presupuestos por período desde el tesoro, dentro de un mandato con umbral. **El umbral aplica al acumulado de asignaciones por departamento por período** (perilla; sugerido 100 monedas), no a la asignación individual — un umbral por asiento se evade fraccionando, y dirección tiene el incentivo explícito de minimizar compuertas. Por encima del acumulado, toda asignación adicional a ese departamento en el período es compuerta tipo (d).
- Administra su **presupuesto de PT** (sección 9) para las cartas de sistema y los adelantos de crédito prioritario.
- Arma y ordena la cola de compuertas (sección 9); llega a cada compuerta con la decisión masticada.
- Ejecuta el cierre semanal (balances, criterios de muerte, quiebras, PT, cola de sesión) y el ciclo mensual de renovaciones (justificación de dos ejes, circuit breaker).
- Optimiza una sola cosa: **la menor cantidad de compuertas de Pedro por unidad de resultado.** Un departamento que consume tres firmas para producir lo que otro resuelve con una está perdiendo, aunque su trabajo sea bueno.

## 9. Cola de compuertas (frontera)

Capacidad declarada de Pedro: **8-10 horas/semana, reparto mixto** — una sesión larga de 3-4 horas, goteo en bloques cortos (1-2 horas en total), y 2-3 horas reservadas a tuning de estilo. Las horas de tuning no emiten PT: son trabajo de calibración fuera del mercado.

**Cuota firmable = sesión más goteo = 4-6 horas = 4-6 PT semanales.** De ahí se aparta primero la reserva personal de PT (perilla semanal; sección 10.1) y el resto se ofrece a la fábrica. La aritmética honesta, a ~30 minutos por firma: **8-12 firmas semanales como techo, antes de descontar la reserva personal.** Agotados los PT ofrecidos, no se sirven más firmas de fábrica esa semana y la cola espera.

**Quién paga cada firma:**

- **Compuertas originadas por un departamento solvente:** las paga el departamento — reserva al encolar, cobro al servirse (sección 3.2).
- **Cartas de sistema** — rescate o cierre de un congelado, justificación de renovación, circuit breaker, compuertas tipo (d) por exceso de mandato: las paga **dirección desde su presupuesto de PT**, fondeado por el tesoro y visible en su rojo.
- **Compuerta obligatoria de un departamento sin caja** (incluido un congelado ejecutando su salida b): dirección adelanta el costo como **crédito prioritario** (invariante 6). Las obligatorias nunca se caen por precio.

Dos carriles:

- **Carril de sesión:** acumula todo lo que puede esperar. La fábrica trabaja la semana entera y arma una cola ordenada por **monedas en juego** — el máximo entre lo que la decisión compromete (gasto) y lo que declara desbloquear (retorno esperado). Cada ítem llega masticado: contexto, recomendación de dirección, y firma de un toque — aprobar, rechazar o editar.
- **Carril de goteo:** interrumpe entre semana. Se cobra en PT por tiempo consumido con recargo de interrupción (2x, perilla), fracción mínima de 30 minutos (500 mili-PT), tope duro de interrupciones por semana (perilla; sugerido 2), y recargo creciente por escasez dentro de la semana. **El goteo respeta las franjas de disponibilidad declaradas** (perilla): por defecto queda fuera de la franja del empleo (L-V 8:00-16:00), que tiene prioridad sobre la fábrica — el empleo compró esa disponibilidad primero. Para una **compuerta obligatoria urgente**, el recargo compra la posición temporal, no la compuerta (invariante 6); si el departamento no puede pagarlo, aplica la regla de adelanto de dirección.

**Frontera de salida:** toda salida al mundo exterior (correo, publicación, plataforma, gasto real) pasa por un único módulo de frontera. No existen rutas de salida por fuera de él.

**Frontera de entrada:** las señales externas que alimentan la invariante 10 y los criterios de muerte (ventas, consultas, clics, impresiones) entran como eventos tipados del libro exterior. En el primer corte la ingesta es manual: Pedro las carga o confirma en la sesión semanal — igual que las acuñaciones (invariante 4). Conectores automáticos son spec futuro (sección 12).

## 10. Las dos zonas del mapa

### 10.0 Primer corte de la fábrica: dos competidores

El cerebro central se prueba con dos departamentos que compiten de verdad por el mismo presupuesto y los mismos PT:

1. **Inteligencia de mercado** — el negocio real (Radar/research-court como cliente del método, no como molde). Es el camino más corto a acuñar la primera venta.
2. **Market research interno** — curiosos y copiadores como hermanos dentro del mismo departamento, con la perilla explorar/explotar entre ellos. Los curiosos se proponen problemas nuevos; los copiadores replican métodos propios que ya rinden (invariantes 13 y 14). Es puro gasto especulativo al arranque.

Uno tiene ingreso a la vista, el otro no: la competencia entre ambos es el caso de prueba honesto de toda la economía.

### 10.1 La zona personal de Pedro

El mismo mapa tiene una segunda zona: los **departamentos personales**, financiados por Pedro desde su cuenta (transferencia, salida 3 de la sección 3.2). Mismo kernel de libro, misma estructura (billetera, plantel, memoria, perillas), pero **no compiten** (invariante 12) — son el staff y los proyectos de Pedro: el departamento de finanzas personales (primer corte), y los que Pedro abra después para proyectos de su trabajo o proyectos propios como Atlas (que como departamento concreto sigue siendo el puente de la sección 12; lo que este spec deja listo es el mecanismo para abrirlo).

Reglas de la zona personal:

- **Cómputo:** siempre por la cuenta pagadora `personal`, contra la reserva personal declarada de las suscripciones. Agotada la reserva, espera al período siguiente — o Pedro la amplía, que recalcula el prorrateo y es compuerta tipo (c). Prohibido comprar capacidad de fábrica, API de fábrica, PT de fábrica o goteo (invariante 12).
- **Servicios:** un departamento personal sí puede contratar servicios de departamentos de la fábrica, pagando con su billetera (transferencia interna normal; para la fábrica es ingreso interno, no señal de éxito).
- **Tiempo de Pedro:** sale de la **reserva personal de PT** (perilla semanal, apartada de la cuota firmable antes de ofrecer a la fábrica). El consumo personal no paga monedas — sería pagarse a sí mismo — pero queda asentado como **apunte de costo de oportunidad** al tipo de cambio vigente: el mapa muestra cuántas monedas de capacidad de fábrica costó Atlas esta semana. Ese consumo queda **fuera del cálculo del tipo de cambio** (sección 3.2, regla b): si entrara, hundiría el precio sin acuñar en el libro de la fábrica y el indicador dejaría de ser honesto. El tiempo de sesión dedicado a los libros personales (ingesta, revisión) también sale de la reserva personal de PT.
- **Sin quiebra ni carta de cierre:** un departamento personal sin fondos o sin reserva simplemente se pausa hasta que Pedro transfiera más. No compite, no quiebra, no se le dispara cierre automático.
- **El empleo de Pedro es el primer habitante de la zona personal**, modelado mínimo (sin plantel LLM al arranque): reserva la franja laboral (L-V 8:00-16:00 más desbordes ocasionales, que tienen prioridad sobre la fábrica), y su ingreso — 2.500 USD/mes — entra a los libros personales del departamento de finanzas. Es además la fuente real de la pista de la fábrica: las suscripciones (~400/mes) y las inyecciones de capital salen de ese ingreso, y el tablero lo muestra: hoy el empleo financia la fábrica; el hito es que deje de hacer falta.
- **El departamento de finanzas personales** lleva los libros personales privados (invariante 11): ingresos propios (empezando por el sueldo), gastos propios, con ingesta manual o por extractos en el primer corte (conectores bancarios: sección 12). Consolida además, como lector, la vista unificada — pista de la fábrica, cuenta de Pedro, reserva personal, apuntes de costo de oportunidad — en un solo tablero.
- **Por qué entra en el primer corte:** ejercita el mismo kernel con un segundo libro independiente — la prueba de que el kernel generaliza — y arma la vista de la cuenta de Pedro, que el mecanismo del PT necesita desde el día uno.

## 11. Integración con Calipso existente

- **Módulo nuevo** (kernel de economía + dirección + bus + frontera) como paquete propio dentro de `calipso/`, sin reescribir lo existente.
- `dispatch.py` (router multi-modelo): **todo request lleva una cuenta pagadora obligatoria** — departamento, trabajo, o `personal` (contra la reserva personal declarada); sin cuenta pagadora, el router rechaza. El router elige **la opción más barata que cumpla el requisito de aptitud de la tarea** (el scoring de `calipso/capabilities.py`); ante opciones de precio y aptitud equivalentes, desempata la eficiencia medida (sección 4.2). Con eso, local gana cuando alcanza, suscripción cuando hace falta calidad, y API solo cuando no queda cuota o la asignación lo justifica. La política "suscripción > API paga > local" deja de ser regla recordada: emerge de precio más aptitud, no de prioridades fijas.
- `calipso/orchestrator.py`: hoy arma equipos ad hoc y los disuelve; el modelo de departamento generaliza su patrón hacia planteles persistentes con roles de autoridad exclusiva. Los equipos efímeros siguen existiendo para tareas sueltas.
- `calipso/resource_dispatcher.py`: sigue administrando capacidad física (RAM, colas de modelos locales); la economía administra plata. La cuota de suscripción, la cuota de cómputo local por departamento y la emisión semanal de PT se modelan con su mismo patrón de capacidad.
- `calipso/memory.py`: la memoria por departamento reutiliza la memoria híbrida existente con espacios de nombres por departamento; los libros personales usan un espacio aislado con control de acceso.
- La UI existente gana después una vista de tablero (el mapa RTS con sus dos zonas, spec futuro); el primer corte se opera por API y archivos.

## 12. Fuera de alcance (specs futuros)

- **Mapa RTS:** la vista de tablero con las dos zonas, tesoro, tipo de cambio del PT, líneas y perillas. Es una vista del cerebro, no lógica nueva.
- **Mezcla multi-proveedor:** presupuesto y cuota por proveedor (Claude, Codex, otros), con la misma mecánica de capacidad y la eficiencia como criterio de comparación.
- **Capa de estilo:** ASD-STE100 y anti-look-IA; consume las horas de tuning reservadas.
- **Conectores de señales externas:** ingesta automática de ventas, métricas y cobros (webhooks, conciliación). Hasta entonces, ingesta manual en sesión (sección 9).
- **Conectores bancarios personales:** importación automática para el departamento de finanzas personales. Hasta entonces, carga manual o por extractos.
- **Puentes:** Atlas/Observatory-Global y research-court entran como departamentos con billetera propia — Atlas en la zona personal, research-court como invitado de la fábrica — no como fundamento del sistema.

## 13. Verificación

- El kernel de economía se desarrolla con **pytest de verdad** (como `test_resource_dispatcher.py`, no como los scripts `test_*.py` con `main()`).
- Tests de propiedades del libro: transferencias suman cero por divisa; ninguna acuñación sin evento de frontera con evidencia o firma, siempre con subtipo; el numerador del tipo de cambio y de la eficiencia solo toma subtipo venta; ninguna emisión de PT fuera de la cuota firmable; los PT expiran al cierre y los expirados no cuentan como consumidos; el cobro de una firma ocurre solo al servirse y las reservas no servidas se liberan al cierre; el tipo de cambio es reproducible desde el libro (misma historia, mismo número), respeta la banda de variación y se mantiene cuando la ventana no tiene consumo; el consumo personal de PT queda fuera del cálculo; los pagos por PT terminan en la cuenta de Pedro y sus cuatro salidas validan saldo; balances siempre derivables; ninguna compra ni transferencia sin reserva previa suficiente (sin sobregiro, en ambas divisas); congelado no puede comprar ni recibir transferencias internas, presupuesto ni financiación — **salvo el asiento de rescate firmado**; las cartas de sistema se pagan del presupuesto de PT de dirección; un departamento personal no puede comprar capacidad, API, PT ni goteo de la fábrica; el umbral de mandato se evalúa sobre el acumulado por departamento y período; los libros personales rechazan todo acceso que no sea del departamento de finanzas personales.
- **Simulación de ciclo completo** con departamentos sintéticos y reloj acelerado: N períodos con gastos, una venta externa simulada (y el tipo de cambio subiendo en respuesta, dentro de su banda), una inyección de capital que NO mueve el tipo de cambio, una quiebra con intento de rescate colusivo (debe fallar), un rescate firmado desde la cuenta de Pedro (debe pasar como única excepción), un congelado ejecutando su salida (b) con adelanto de dirección, un circuit breaker de renovación disparado y un cierre con liquidación por prelación — sin intervención manual.
- Criterio de aceptación del primer corte: un ciclo semanal completo real — propuestas, asignación, gasto medido, cola de sesión armada y firmada por Pedro, cierre de período con balances correctos en ambas divisas y libros personales al día — con los dos departamentos competidores vivos y el departamento de finanzas personales operando.

## 14. Criterios de éxito

- La fábrica registra **cada** moneda y cada PT que entra y sale; el tablero nunca muestra prosperidad que el mundo exterior no confirme.
- Pedro opera el sistema dentro de su cuota firmable (8-12 firmas menos su reserva personal, más tuning) sin que la cola de sesión crezca semana a semana.
- **El tipo de cambio del PT es un indicador honesto:** sube solo si la fábrica acuña ventas externas por PT consumido — el capital inyectado no lo mueve. Un PT caro es la fábrica vendiendo; un PT barato con mucha demanda es la señal de que Pedro trabaja mucho y el sistema vende poco.
- **El hito de largo plazo del tablero:** el tipo de cambio sosteniéndose por encima de la línea del empleo (≈14,5) — la fábrica comprando el tiempo de Pedro mejor que su empleador — y después de la línea de research-court (25).
- Las suscripciones quedan justificadas, achicadas o canceladas por números del libro (utilización y eficiencia), no por intuición.
- La métrica que decide si el proyecto vive: **monedas acuñadas por ventas externas antes de agotar la pista de arranque.**
