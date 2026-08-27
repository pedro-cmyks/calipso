# Inventario de lo que quedó abierto

Fecha: 2026-08-26

Auditoría de los dos specs, los seis planes, el research multi-modelo y AGENTS.md,
con **cada candidato verificado contra el código**, no contra el papel. 187 candidatos
del barrido; 162 abiertos, 22 parciales, 3 ya cerrados.

## El titular

`explorar_explotar_pct` y `agresividad_pct` aparecen dos veces en todo el código:
donde se declaran. Nadie crea propuestas en el bus fuera de los tests. Un
`Departamento` es nombre, zona, presupuesto, techo y dos perillas muertas.

**La economía está construida; la fábrica no.** Los departamentos son billeteras sin
plantel, sin roles y sin memoria propia. Nada propone y nada produce, así que el
único gasto que existe hoy es el de Pedro hablando por el chat.

## Tamaño del pendiente

| tamaño | cuántos | qué significa |
|---|---|---|
| spec | 34 | hay que diseñarlo antes de poder planificarlo |
| plan | 27 | diseño claro, necesita su propio plan |
| tarea | 94 | entra como tarea de un plan existente |
| línea | 29 | un cambio puntual |

## economia (64)

### [spec] 1. Frontera de salida al mundo exterior (correo, publicacion, plataforma)

**Por qué importa:** Servir una compuerta tipo contacto/publicacion cobra el PT y no manda nada: la firma de Pedro no produce ningun efecto en el mundo, y no hay un solo lugar donde auditar que sale.
**Evidencia:** /home/pedro/calipso/calipso/economia/cola.py:26 (_TIPOS incluye contacto/publicacion) y :252 (servir solo apila 'servida'); no existe /home/pedro/calipso/calipso/economia/frontera_salida.py

### [spec] 16. Departamentos sin plantel, roles ni autoridad de escritura exclusiva

**Por qué importa:** Sin plantel la economia es contabilidad sin fabrica: nadie propone ni produce, y las propuestas del bus las escribe quien llame la funcion.
**Evidencia:** /home/pedro/calipso/calipso/economia/departamentos.py:27-34 (solo billetera y perillas); /home/pedro/calipso/calipso/orchestrator.py:50-138 (plan/build_team arma equipos efimeros)

### [spec] 29. Copiadores y curiosos: invariantes 13 (copiar metodo, artefacto nunca) y 14 (umbral n>=3)

**Por qué importa:** Dos invariantes que el spec 2 dice que 'viven en codigo, no en prompts' hoy no viven en ningun lado; dependen del plantel de agentes.
**Evidencia:** no existe modulo alguno; grep 'copiador|copiar_metodo' en calipso/ devuelve 0

### [spec] 43. El `plantel` prometido por el Plan 2

**Por qué importa:** El plan del kernel prometio billetera+plantel+perillas y entrego dos de tres; sin agentes persistentes no hay quien produzca dentro de un departamento.
**Evidencia:** /home/pedro/calipso/calipso/economia/departamentos.py:28 (llegaron billetera y perillas); grep 'plantel' en calipso/ solo pega en web/fabrica/app.js:67 y pulso.js:5, donde significa escritorios efimeros (duplicado del item 16)

### [spec] 44. Memoria propia por departamento con espacio de nombres

**Por qué importa:** Es la cuarta pata del modelo de departamento y la condicion de todo archivado; el aislamiento de los libros personales es por archivo, no por control de acceso sobre la memoria hibrida.
**Evidencia:** /home/pedro/calipso/calipso/memory.py (0 lineas con departamento/namespace/espacio) — duplicado del item 17

### [spec] 50. Conectores de senales externas (ventas, metricas, cobros)

**Por qué importa:** Declarado fuera de alcance a proposito, pero hoy ni el fallback manual existe, asi que el numerador de todo depende de nada.
**Evidencia:** spec economia:206 lo declara spec futuro; la frontera de acunacion (/home/pedro/calipso/calipso/economia/kernel.py:47) no tiene ni siquiera la ingesta manual (ver item 26)

### [spec] 51. Conectores bancarios personales

**Por qué importa:** Declarado spec futuro; es lo que decide si los libros personales se mantienen al dia o se abandonan a la tercera semana.
**Evidencia:** spec economia:207; /home/pedro/calipso/calipso/economia/personal.py:35-49 solo acepta asientos cargados a mano

### [spec] 52. Puentes Atlas/Observatory-Global y research-court como departamentos

**Por qué importa:** Declarado spec futuro, pero la 'verificacion a ojo' del plan de acoplamiento usa a atlas como ejemplo de todo sobre un departamento que no existe en ningun registro.
**Evidencia:** spec economia:208; grep 'research-court' en calipso/ devuelve 0; 'atlas' solo aparece como ejemplo en comentarios (server.py:2524) y en fixtures de test

### [spec] 56. Umbral de escalado como perilla presupuestaria por departamento

**Por qué importa:** 'Departamento pobre, umbral agresivo hacia lo local' no se puede expresar: el router no sabe quien paga, asi que el presupuesto no puede aprender contra el ruteo.
**Evidencia:** /home/pedro/calipso/calipso/capabilities.py:275-282 (choose recibe features, effort, available, quota_low, project_root — nunca cuenta ni saldo); /home/pedro/calipso/calipso/connectors.py:16-44 es el unico acoplamiento economia->ruteo y es binario y global

### [spec] 60. Tarifas diferenciadas (off-peak, batch, cache hit) como producto interno

**Por qué importa:** Vender latencia a mitad de precio dentro de la economia interna es un producto nuevo del Mercado, no un parametro de la tabla de precios.
**Evidencia:** /home/pedro/calipso/calipso/costs.py:30 y /home/pedro/calipso/calipso/economia/pagador.py:28 (par fijo entrada/salida por modelo, sin eje temporal ni modo)

### [plan] 15. Perillas explorar/explotar y agresividad no las lee nadie

**Por qué importa:** Config muerta: Pedro puede mover la agresividad de un departamento y no cambia absolutamente nada en su comportamiento de gasto.
**Evidencia:** /home/pedro/calipso/calipso/economia/departamentos.py:33-34 es la unica aparicion en todo calipso/; /home/pedro/calipso/calipso/economia/mercado.py:140 (gastar_api) y cola.py:67 (encolar) no las consultan

### [plan] 17. Memoria por departamento con espacio de nombres propio

**Por qué importa:** Tres de las cuatro patas del departamento del spec 6 faltan o estan a medias; sin memoria propia el archivado de aprendizajes al cerrar o al morir un trabajo no tiene donde ir.
**Evidencia:** /home/pedro/calipso/calipso/memory.py — grep 'departamento|namespace|espacio' devuelve 0 en sus 224 lineas

### [plan] 2. Frontera de entrada de senales externas (consultas, clics, impresiones)

**Por qué importa:** Sin senales tipadas el criterio de muerte de una propuesta solo puede ser 'gaste mucho' o 'tarde mucho', nunca 'no funciono', que es lo unico que mata bien una exploracion.
**Evidencia:** /home/pedro/calipso/calipso/economia/tipos.py:31-43 (TipoAsiento no tiene evento exterior) y /home/pedro/calipso/calipso/economia/bus.py:19 (_CLAVES_CRITERIO = gasto_max_mm, semanas_max)

### [plan] 3. Escrow al firmar un compromiso exterior, reserva de horas de Pedro y exposicion comprometida

**Por qué importa:** Un departamento puede firmar una entrega y despues quebrar sin plata reservada: 'quebrar no libera de cumplir' no tiene respaldo contable.
**Evidencia:** /home/pedro/calipso/calipso/economia/cola.py:117 (la reserva es del costo en PT de la firma, no del compromiso) — grep 'compromiso' en calipso/ devuelve 0 lineas

### [plan] 33. El criterio de aceptacion del primer corte no se puede demostrar hoy

**Por qué importa:** Es el criterio que declara terminado el primer corte; lo demostrable hoy es la mitad contable (abrir, fichar, atender, cerrar) con test_economia_server.py verde.
**Evidencia:** falla en cuatro puntos independientes: sin departamentos (~/.calipso/economia inexistente), sin plantel que proponga (orchestrator.py:50), sin conciliacion (operacion.py:46), sin ingesta de ventas ni rescate (server.py:3429-3552)

### [plan] 35. El mapa no origina ninguna escritura (firmar, rechazar, mover perilla, fichar)

**Por qué importa:** La consola es 100% lectura: para firmar una compuerta hay que volver a la UI vieja, y la invariante 4 del spec del mapa enumera esas escrituras como las que el mapa SI origina.
**Evidencia:** /home/pedro/calipso/calipso/web/fabrica/app.js:219-228 (pintarAvisos pinta spans sin data-id ni handler) y paneles.js:53-62 (el id se descarta al pintar); el unico POST del cliente es app.js:354 /api/chats/{id}/activate

### [plan] 37. La economia nunca se encendio: no existe ~/.calipso/economia/

**Por qué importa:** Todos los /api/economia/* responden {'activa': false}, _cobrar_turno (server.py:3833) sale por el early return y /api/mapa/ciudad no tiene un solo edificio.
**Evidencia:** verificado: ls ~/.calipso/ no tiene 'economia' y find ~/.calipso -name libro.jsonl no devuelve nada; /home/pedro/calipso/calipso/economia/pagador.py:62-66 devuelve None sin los tres archivos

### [plan] 39. Los sub-agentes del equipo dinamico gastan sin pasar por el Mercado

**Por qué importa:** Un turno de equipo consume planner + hasta 3 agentes + sintesis y el libro registra un solo cobro: la contabilidad subestima el gasto por un factor ~5.
**Evidencia:** /home/pedro/calipso/calipso/server.py:1612-1660 (hasta 3 agentes via _run_agent_text/_run_backend_text sin Pagador) y :1680-1695 (sintesis); el unico cobro es server.py:2528

### [plan] 54. No hay forma de crear el libro, dar de alta un departamento ni mover una perilla

**Por qué importa:** Es el bloqueo raiz de los items 28, 33, 37, 47, 48, 49 y 55: sin bootstrap, doce mil lineas de plan implementadas nunca corrieron contra datos reales.
**Evidencia:** Registro.alta (/home/pedro/calipso/calipso/economia/departamentos.py:62) y Registro.ajustar (:77) sin llamadores fuera de tests; /home/pedro/calipso/calipso/server.py:3662 solo instancia Registro para leer

### [plan] 55. Endpoint y UI para las perillas de Pedro

**Por qué importa:** 'Cambiar perillas es gratis para Pedro: es el juego RTS' — el juego no tiene mandos, y dos de esas cuatro perillas ademas no las lee nadie (item 15).
**Evidencia:** /home/pedro/calipso/calipso/economia/departamentos.py:29-34 declara y persiste los cuatro campos; /home/pedro/calipso/calipso/server.py no expone /api/economia/departamentos ni /perilla (endpoints existentes: 3429-3552)

### [plan] 57. Tres tablas de precio desincronizadas y ninguna importada de fuente mantenida

**Por qué importa:** Tres fuentes de verdad editadas a mano y ninguna derivada de otra: dos libros del mismo turno pueden contradecirse y nadie se entera.
**Evidencia:** /home/pedro/calipso/calipso/capabilities.py:39 (cost es ordinal 0/1/3), /home/pedro/calipso/calipso/costs.py:30-34 (3 modelos, USD/token), /home/pedro/calipso/calipso/economia/pagador.py:28 (1 modelo, mm/Mtok)

### [tarea] 10. Equivalencias declaradas como tabla de conversion por unidad

**Por qué importa:** No distingue mensajes de tokens, asi que la normalizacion entre proveedores de la que depende comparar eficiencia se apoya en que alguien cargue bien un solo numero a mano.
**Evidencia:** /home/pedro/calipso/calipso/economia/capacidad.py:32-34 (capacidad_ciclo + un solo costo_api_mm_por_unidad)

### [tarea] 11. Pista de arranque medible y ventas acumuladas en el tablero

**Por qué importa:** La metrica que el spec 14 usa para decidir si el proyecto vive — ventas externas antes de agotar la pista — no es observable en ninguna pantalla.
**Evidencia:** /home/pedro/calipso/calipso/economia/personal.py:81-94 y /home/pedro/calipso/calipso/mapa/ciudad.py:277-289 (no hay campo de pista); grep 'pista' en calipso/ devuelve 0

### [tarea] 13. Perillas del tipo de cambio (ventana 8, banda 25%, arranque) como configuracion

**Por qué importa:** La invariante 3 dice que la perilla de Pedro es la formula; hoy mover la ventana o la banda exige editar codigo y no queda auditado en ningun lado.
**Evidencia:** /home/pedro/calipso/calipso/economia/pt.py:109-112 (defaults) y los seis llamadores sin argumentos: cola.py:90, direccion.py:56, pt.py:195, reloj.py:97, personal.py:85, mapa/ciudad.py:282

### [tarea] 14. Perillas de umbral de mandato, recargo y tope de goteo, ventana del criterio de muerte

**Por qué importa:** Son constantes de modulo sin superficie: el 'juego RTS' de la seccion 6 no tiene mandos y cada ajuste es un commit.
**Evidencia:** /home/pedro/calipso/calipso/economia/direccion.py:18, /home/pedro/calipso/calipso/economia/cola.py:24-25, /home/pedro/calipso/calipso/economia/cierre.py:55

### [tarea] 18. Ejecutar el cierre de un departamento (liquidacion, archivo, baja del registro)

**Por qué importa:** Pedro firma el cierre de un departamento y no pasa nada: el departamento sigue vivo, cobrando presupuesto y apareciendo en el mapa.
**Evidencia:** /home/pedro/calipso/calipso/economia/cola.py:152-159 (atender_carta solo apila el evento); /home/pedro/calipso/calipso/economia/kernel.py:141 liquidar() sin ningun llamador de produccion; /home/pedro/calipso/calipso/economia/departamentos.py:62-81 sin metodo de baja

### [tarea] 20. Comentar o contraproponer sobre una propuesta ajena

**Por qué importa:** Falta la mitad deliberativa del bus: no hay forma de que un departamento discuta la propuesta de otro ni de ligar una contrapropuesta a la que responde.
**Evidencia:** /home/pedro/calipso/calipso/economia/bus.py:105-109 (_TRANSICIONES: alta -> financiada -> muerta -> liquidada)

### [tarea] 22. Items de cola con contexto y recomendacion de direccion, y la accion 'editar'

**Por qué importa:** 'Cada item llega masticado, firma de un toque' no se cumple: Pedro firma un titulo sin contexto y no puede aprobar con cambios.
**Evidencia:** /home/pedro/calipso/calipso/economia/cola.py:109-115 (el evento encolada no tiene contexto ni recomendacion) y :145,:152,:182 mas /home/pedro/calipso/calipso/server.py:3455,:3469 (solo atender y rechazar)

### [tarea] 23. Compuertas de Pedro por unidad de resultado (lo unico que direccion optimiza)

**Por qué importa:** Los datos ya estan en el libro (CONSUMO_PT con pagador, ventas con detalle trabajo) pero nadie los pliega: el objetivo declarado de direccion no se mide.
**Evidencia:** /home/pedro/calipso/calipso/economia/eficiencia.py:104-115 (mide ventas sobre costo API, no firmas sobre ventas) y /home/pedro/calipso/calipso/economia/cierre.py:205-214 (no lo informa)

### [tarea] 24. Goteo: recargo creciente por escasez y franjas de disponibilidad *(parcial)*

**Por qué importa:** El goteo puede interrumpir dentro de la franja del empleo (L-V 8-16), que segun el spec tiene prioridad sobre la fabrica; y el segundo goteo de la semana cuesta lo mismo que el primero.
**Evidencia:** hechos: /home/pedro/calipso/calipso/economia/cola.py:24 (2x), :25 y :81-88 (tope), :33-34 (fraccion minima). Faltan: recargo constante en :93 y :198; grep 'franja' en calipso/ devuelve 0

### [tarea] 26. Acunacion por venta con firma de Pedro y superficie de ingesta

**Por qué importa:** El numerador del tipo de cambio y de toda la eficiencia no tiene por donde entrar: la ingesta manual del spec 9 no existe como operacion.
**Evidencia:** /home/pedro/calipso/calipso/economia/kernel.py:47-58 (acunar solo exige evidencia no vacia, sin distinguir venta de capital) — acunar() no tiene NINGUN llamador fuera de tests; /home/pedro/calipso/calipso/server.py:3429-3552 no expone POST de venta

### [tarea] 27. Superficie para las cuatro salidas de la cuenta de Pedro y el rescate firmado

**Por qué importa:** La unica forma de rescatar un departamento congelado, retirar o reinyectar es abrir un interprete de Python: la decision de Pedro no tiene camino desde la cola.
**Evidencia:** /home/pedro/calipso/calipso/economia/cuenta_pedro.py:13-37 sin ningun llamador fuera de tests; /home/pedro/calipso/calipso/economia/cola.py:152 (atender_carta no dispara rescatar)

### [tarea] 28. El primer corte (dos competidores + finanzas personales) no esta instanciado

**Por qué importa:** Sin departamentos reales la economia entera responde 'activa: false' y todo el codigo solo corrio contra libros sinteticos.
**Evidencia:** ~/.calipso/economia/ no existe (verificado); los nombres 'Inteligencia de mercado' / 'Market research interno' solo aparecen como fixtures en test_economia_*.py

### [tarea] 30. Estado 'pausado' para un departamento personal sin fondos

**Por qué importa:** Un departamento personal sin fondos es indistinguible de uno activo: la zona personal esta bien exceptuada de la quiebra (cierre.py:66-67,:93) pero no tiene contraparte.
**Evidencia:** /home/pedro/calipso/calipso/economia/departamentos.py:84-97 (solo es_congelado) y /home/pedro/calipso/calipso/economia/personal.py:88-91 (tablero solo saldo y congelado)

### [tarea] 31. El empleo como habitante de la zona personal: franja laboral y sueldo en los libros personales *(parcial)*

**Por qué importa:** El sueldo que de hecho financia las suscripciones no esta en ningun libro, y la franja que el empleo compro primero no protege nada contra el goteo.
**Evidencia:** hechos: /home/pedro/calipso/calipso/economia/reloj.py:20 (categoria empleo) y personal.py:63-66 (linea medida). Faltan: grep 'franja' = 0; SUELDO_MENSUAL_MM (personal.py:19) solo se usa en :87 y ciudad.py:284, nunca se registra en LibroPersonal

### [tarea] 32. La simulacion de ciclo completo no cubre cuatro de los ocho elementos del spec 13 *(parcial)*

**Por qué importa:** El spec pide esos elementos encadenados en una corrida sin intervencion manual: probados de a uno no demuestran que interactuen.
**Evidencia:** /home/pedro/calipso/test_economia_simulacion.py:102-103 asserta tipo_final == 5_000 (nunca sale del bootstrap); los otros tres viven sueltos en test_economia_cierre.py:145, test_economia_mercado.py:254 y test_economia_kernel.py:146,:170

### [tarea] 34. Serie de crecimiento de la cola y deficit acumulado de direccion

**Por qué importa:** Dos criterios de exito del spec 14 no tienen instrumento: no se puede ver si la cola crece semana a semana ni si el rojo de direccion es sostenido.
**Evidencia:** /home/pedro/calipso/calipso/economia/cola.py:129-135 (pendientes devuelve el estado actual, no una serie) y /home/pedro/calipso/calipso/economia/personal.py:83 (direccion_mm es un saldo puntual)

### [tarea] 36. cola.pendientes() sigue siendo O(E^2) bajo el candado del libro

**Por qué importa:** Medio segundo de candado tomado por refresco del mapa bloquea toda escritura de la economia; se paga adentro de server.py:3744.
**Evidencia:** /home/pedro/calipso/calipso/economia/cola.py:129-135 (for e in self._eventos con self.estado(e['id']) adentro, que reitera los eventos)

### [tarea] 4. Un departamento personal puede consumir PT y goteo de la fabrica (la cola no chequea zona) *(parcial)*

**Por qué importa:** 'personal:finanzas' puede encolar una firma y consumir POOL_PT_FABRICA en servir(): la invariante 12 se cumple en la mitad de las puertas.
**Evidencia:** cerrado en /home/pedro/calipso/calipso/economia/mercado.py:83-86 (+ test_economia_mercado.py:119); abierto en /home/pedro/calipso/calipso/economia/cola.py:67-117 (encolar nunca consulta el Registro ni la zona)

### [tarea] 40. La suscripcion no se traduce a monedas en la barra de costo *(parcial)*

**Por qué importa:** CORRECCION al barrido: la decision de reflejar la suscripcion en milimonedas YA esta tomada en el codigo (precio por escasez, minimo 1 mm). Lo unico roto es el plomeria del retorno, asi que esto no es un spec sino un cambio de firma en _aplicar/cargar_suscripcion/_cobrar_turno.
**Evidencia:** el libro SI la traduce: pagador.cargar_suscripcion -> _aplicar (pagador.py:137) -> mercado.comprar_capacidad (mercado.py:107-117) transfiere `precio` en mm. Lo que falta: /home/pedro/calipso/calipso/economia/pagador.py:162-166 y /home/pedro/calipso/calipso/server.py:3845-3852 descartan el monto y devuelven 0

### [tarea] 41. cola.pendientes() O(E^2) disparado tambien por cada derivacion de la ciudad

**Por qué importa:** Mismo defecto que el 36, ahora en el camino caliente del chat con foco: un turno de chat paga el pliegue cuadratico de la cola.
**Evidencia:** /home/pedro/calipso/calipso/economia/cola.py:129-135; llamado desde /home/pedro/calipso/calipso/mapa/ciudad.py:268 bajo el candado de server.py:3744 (duplicado del item 36)

### [tarea] 42. El campo `mision` de la ficha del departamento

**Por qué importa:** Calipso recibe saldo, gasto y compuertas de un departamento sin saber para que existe: el contexto del foco esta mutilado. Necesita migracion de departamentos.json.
**Evidencia:** /home/pedro/calipso/calipso/economia/departamentos.py:28-34 (nombre, zona, cuatro perillas) y /home/pedro/calipso/calipso/mapa/ficha.py:71-86 (el bloque no menciona mision)

### [tarea] 45. La tabla de precios de API tiene un solo modelo cargado

**Por qué importa:** Cualquier turno por API con otro modelo destruye monedas calculadas con un precio de relleno 11x mas caro en entrada y 14x en salida, y el libro es append-only: esos asientos quedan.
**Evidencia:** /home/pedro/calipso/calipso/economia/pagador.py:28-29 (PRECIOS_API_MM_POR_MTOK = {'deepseek-chat': (270, 1100)}; PRECIO_DESCONOCIDO = (3000, 15000))

### [tarea] 46. Las excepciones de dominio de la economia suben como 500 crudos

**Por qué importa:** Aceptado explicitamente 'para el primer corte', pero firmar una carta ya resuelta devuelve un 500 opaco en vez de un mensaje que diga que paso.
**Evidencia:** /home/pedro/calipso/calipso/server.py:3455-3552 — ninguno de los ocho endpoints /api/economia/* tiene try/except sobre ErrorCola/ErrorReloj/ErrorMercado/SinSaldo

### [tarea] 47. El ciclo semanal completo REAL nunca se corrio

**Por qué importa:** Es el criterio que declara terminado el primer corte y no se puede ni empezar hasta que exista el libro.
**Evidencia:** ~/.calipso/economia/ inexistente; /home/pedro/calipso/test_economia_simulacion.py cubre la version sintetica con tmp_path (duplicado del item 33)

### [tarea] 48. Los dos departamentos competidores no estan registrados

**Por qué importa:** El caso de prueba honesto del spec — uno que acuna y otro que solo gasta — es lo que valida eficiencia, criterios de muerte, quiebras y tipo de cambio contra la realidad.
**Evidencia:** ~/.calipso/economia/departamentos.json no existe; Registro.alta (/home/pedro/calipso/calipso/economia/departamentos.py:62) solo tiene llamadores en test_economia_*.py

### [tarea] 49. El departamento de finanzas personales del primer corte tampoco existe

**Por qué importa:** El segundo libro independiente que ejercita el mismo kernel nunca corrio, y el tablero no puede mostrar 'hoy el empleo financia la fabrica'.
**Evidencia:** /home/pedro/calipso/calipso/economia/pagador.py:132-135 rutea 'personal' a usar_reserva_personal(..., 'personal:finanzas'), destino no registrado; /home/pedro/calipso/calipso/economia/personal.py implementado y sin usar

### [tarea] 5. Control de acceso de los libros personales (invariante 11) *(parcial)*

**Por qué importa:** Cualquier codigo con la ruta lee y escribe las finanzas reales de Pedro; el test que el spec 13 declara no existe en test_economia_frontera.py.
**Evidencia:** aislamiento por archivo en /home/pedro/calipso/calipso/economia/personal.py:27; sin identidad de llamador en :35-49; /home/pedro/calipso/calipso/memory.py sin ninguna nocion de departamento

### [tarea] 53. AGENTS.md no menciona la economia

**Por qué importa:** Un agente nuevo que lea AGENTS.md no sabe que existen 20 modulos, 13 suites y 8 endpoints de un libro contable, ni que dispatch.py cobra por cuenta pagadora.
**Evidencia:** /home/pedro/calipso/AGENTS.md — grep -i 'economia|moneda|departamento|api/economia' sobre sus 537 lineas devuelve CERO coincidencias

### [tarea] 59. Revision periodica de precios

**Por qué importa:** El gancho ya esta construido y el research avisa que el lider cambia cada 4-6 semanas: sin recordatorio las tres tablas del item 57 envejecen en silencio.
**Evidencia:** /home/pedro/calipso/calipso/routines.py:25 (KINDS = reflect, learn, backup) y :29-31 — el ticker de server.py existe y nadie colgo ahi la revision

### [tarea] 6. Conciliacion plan-contra-hecho en el cierre y clock-in huerfanos

**Por qué importa:** La cuota emitida nunca se compara contra los minutos fichados: el sistema no puede decir si Pedro trabajo mas o menos de lo que planeo, y un tramo abierto se arrastra en silencio.
**Evidencia:** /home/pedro/calipso/calipso/economia/operacion.py:46-48 (cerrar_semana_operativa no recibe Reloj); /home/pedro/calipso/calipso/economia/reloj.py:119 huerfanos() no tiene ningun llamador fuera de tests

### [tarea] 61. cost_tier como banda presupuestaria: el router no sabe quien paga el turno

**Por qué importa:** Un departamento sin fondos igual elige apex y el cargo termina en cargos_pendientes.jsonl (pagador.py:141-146) en vez de haber ruteado mas barato: el freno actua despues del gasto.
**Evidencia:** /home/pedro/calipso/calipso/capabilities.py:275 (choose sin cuenta ni saldo) mientras la cuenta ya llega al cobro en /home/pedro/calipso/calipso/server.py:2528 y dispatch.py:521

### [tarea] 62. Contador de pasos y limite de handoffs con descuento del presupuesto

**Por qué importa:** Atrapa casi la mitad de los fallos catalogados por MAST sin usar un LLM, y hoy nada frena un bucle de agentes antes de que gaste.
**Evidencia:** /home/pedro/calipso/calipso/orchestrator.py:61 (agents[:3] es el unico corte, y es duro); no hay contador de pasos ni rebotes en calipso/economia/

### [tarea] 63. El turno de EQUIPO cobra una sola unidad aunque corran planner, N agentes y sintesis

**Por qué importa:** El patron de cobro por sub-llamada YA existe (el borrador se cobra aparte en server.py:632-636) y no se aplico aca: es el mismo agujero del item 39 visto desde el cobro.
**Evidencia:** /home/pedro/calipso/calipso/server.py:2521-2530 (normaliza used_route 'orchestrator' y cobra UNA vez) contra :1500-1512 (planner), :1612-1660 (agentes) y :1680-1695 (sintesis)

### [tarea] 64. El plan/tier de cada proveedor es declarable pero no hay donde declararlo

**Por qué importa:** Cambiar de plan es compuerta tipo (c) y hoy no hay ni archivo ni endpoint donde vivan los planes reales: capacidad_ciclo, que ES 'en que plan estoy', solo lo escriben los tests.
**Evidencia:** el modelo existe en /home/pedro/calipso/calipso/economia/capacidad.py:29-44; /home/pedro/calipso/calipso/economia/pagador.py:62-66 devuelve None sin suscripciones.json y los unicos escritores son test_economia_pagador.py:27, test_mapa_server.py:22, test_economia_server.py:24; /home/pedro/calipso/calipso/costs.py:37-40 declara los mismos planes en USD sin relacion

### [tarea] 7. Justificacion de renovacion con dos ejes: upgrade por cuota agotada y reasignacion por eficiencia con cortes por departamento *(parcial)*

**Por qué importa:** Renovar solo sabe decir rojo/no rojo: no propone ampliar cuando se agota, ni reasignar cuota entre departamentos, ni cancelar — que son tres de las cuatro decisiones del spec 4.2.
**Evidencia:** /home/pedro/calipso/calipso/economia/cierre.py:205-214 (utilizacion + eficiencia agregada; el comentario ':211-212 cortes por departamento llegan con Plan 3' sigue vigente); /home/pedro/calipso/calipso/economia/eficiencia.py:104 sin cruzar por suscripcion

### [tarea] 8. Ciclo mensual alineado al ciclo de facturacion de cada proveedor

**Por qué importa:** Una suscripcion que factura el 3 y otra el 21 se renuevan juntas y su recaudacion se compara contra un ciclo que no es el suyo: el numero que decide renovar esta corrido.
**Evidencia:** /home/pedro/calipso/calipso/economia/capacidad.py:16 (SEMANAS_POR_CICLO = 4 global) y /home/pedro/calipso/calipso/economia/cierre.py:169 (todas las suscripciones se cierran en la misma semana)

### [tarea] 9. Ampliar la reserva personal como operacion y compuerta tipo (c)

**Por qué importa:** Cambiar la reserva personal cambia el prorrateo que justifica cada renovacion, y hoy se hace editando un JSON a mano: sin firma, sin asiento y sin carta.
**Evidencia:** /home/pedro/calipso/calipso/economia/capacidad.py:28-44 (Suscripcion frozen) y /home/pedro/calipso/calipso/economia/pagador.py:70-71 (se lee de suscripciones.json, sin escritor)

### [linea] 12. Linea de research-court (25 monedas/hora) en el tablero

**Por qué importa:** El hito de largo plazo del tablero tiene dos lineas y solo se dibuja una: cruzar 25 no se puede ver.
**Evidencia:** /home/pedro/calipso/calipso/economia/personal.py:19 y :86 (solo SUELDO_MENSUAL_MM y linea_empleo_mm); /home/pedro/calipso/calipso/mapa/ciudad.py:283

### [linea] 19. La propuesta del bus no lleva horas de firma estimadas ni compuertas previstas

**Por qué importa:** Direccion no puede ordenar la cola por costo en PT ni medir compuertas por resultado porque la propuesta nunca declara cuantas firmas va a necesitar.
**Evidencia:** /home/pedro/calipso/calipso/economia/bus.py:47-49 (alta recibe titulo, presupuesto_mm, retorno_mm, criterio)

### [linea] 21. Archivar los artefactos al liquidar un trabajo muerto

**Por qué importa:** Lo aprendido en una exploracion que murio se pierde entero; depende de que exista antes la memoria por departamento.
**Evidencia:** /home/pedro/calipso/calipso/economia/bus.py:210-217 (devuelve la plata y marca muerta/liquidada, nada mas)

### [linea] 25. Cuota firmable y reserva personal de PT como perillas declaradas

**Por qué importa:** No hay valor declarado en ningun archivo: si Pedro escribe otro numero una semana el libro lo acepta y la emision de PT queda sin ancla.
**Evidencia:** /home/pedro/calipso/calipso/economia/operacion.py:34-35 y /home/pedro/calipso/calipso/server.py:3419-3421 (EcoAbrirBody exige cuota_firmable_mpt en cada request)

### [linea] 38. La cuenta pagadora no es obligatoria: --cuenta tiene default 'personal'

**Por qué importa:** Un request sin cuenta no se rechaza como manda el spec 11: se le cobra silenciosamente a la reserva personal de Pedro.
**Evidencia:** /home/pedro/calipso/dispatch.py:521 (ap.add_argument('--cuenta', default='personal'))

### [linea] 58. api:claude-fable-5 esta en el registro y no en costs.PRICING

**Por qué importa:** El modelo mas caro del catalogo se registra como gratis en costs y nunca empuja connectors.limits_status, mientras la economia lo cobra al conservador (3000,15000): los dos libros se contradicen.
**Evidencia:** /home/pedro/calipso/calipso/capabilities.py:95 (tier apex) vs /home/pedro/calipso/calipso/costs.py:30-34 y :61 (PRICING.get(model, (0.0, 0.0))); el override ~/.calipso/pricing.json (costs.py:44-58) tampoco existe

## modelos (42)

### [spec] Cascada verificada sobre el escalon barato (AutoMix + FrugalGPT): hoy solo hay fallback por ERROR, nunca escalado por baja confianza

**Por qué importa:** Es la recomendacion #1 del research (:158), la de mayor ahorro reportado (>50%), y esta en cero: no hay prompt de auto-verificacion, ni extraccion de confianza, ni umbral, ni segundo intento. Necesita spec porque el CLI de suscripcion no da logprobs.
**Evidencia:** dispatch.py:263-278 + :543-553 (elige ruta y ejecuta una vez); calipso/server.py:2423-2505 (el unico camino de re-ruteo es el except: 'ruta {route} fallo; fallback local')

### [spec] El flag 'sensible' como dimension de JURISDICCION (cambia de host, no de modelo) *(parcial)*

**Por qué importa:** Media pieza real (deteccion + filtro duro en el scoring) y media rota: private_ok solo es True para modelos que no corren, y la regla de dispatch manda el dato sensible a la nube con un why que dice 'suscripcion local sin API'. La dimension jurisdiccion (mismo peso, host US/EU vs primera parte china) no se puede ni expresar sin el campo host.
**Evidencia:** dispatch.py:121-123 PRIVATE detecta; calipso/capabilities.py:45,52 private_ok; capabilities.py:255-256 score_model descarta los que no cumplen; pero dispatch.py:215-217 rutea el prompt privado a la SUSCRIPCION

### [spec] El router sigue siendo 'suscripcion primero' por regla fija, no por precio + aptitud + eficiencia medida (duplicado del item 2)

**Por qué importa:** Mismo pendiente que el item 2 con otro tamano estimado; el medidor (economia/eficiencia.py) esta construido y ningun llamador de routing lo consulta. Recomiendo fusionarlos en un solo spec.
**Evidencia:** dispatch.py:197-238 (decide_by_rules, precedencia hardcodeada), dispatch.py:256-260 (decide_by_model devuelve suscripcion), calipso/config.py:19 'policy: subscription_first'

### [spec] El scoring es un vector plano por tipo de tarea, no una matriz funcion x dominio (X-MAS)

**Por qué importa:** Sin el eje FUNCION (responder/juzgar/agregar/planificar) no se puede expresar 'buen juez aunque no sea buen generador', que es lo que habilita el jurado y el verificador. Correccion menor: VALID_TYPES ya sumo 'exec' (orchestrator.py:47), pero sigue sin 'juzgar' ni 'verificar'.
**Evidencia:** calipso/capabilities.py:41-102 (strengths mezcla dominio 'code'/'writing'/'analysis' con modo 'summarize'/'translate'); calipso/orchestrator.py:46-47 VALID_TYPES

### [spec] El verificador como rol con linea de presupuesto propia

**Por qué importa:** El planner no puede crear un verificador aunque quiera, y el turno de equipo se cobra como uno solo (server.py:2526-2530 cobra ruta_cobrable una vez), asi que no hay partida separada que presupuestar.
**Evidencia:** calipso/orchestrator.py:27-42 PLANNER_SYSTEM y :46-47 VALID_TYPES (sin 'verificar' ni 'juzgar'); calipso/verification.py:29-60 recomienda comandos de test por tipo de archivo, no verifica salidas de modelos

### [spec] Ensembles / MoA-Lite reservados a queries de alto valor y SOLO entre modelos por encima del umbral de aptitud

**Por qué importa:** El umbral que el guardarrail Self-MoA necesita es hoy implicito y blando: un modelo sin la strength declarada entra igual con 0.4*0.7. Sin umbral duro, cualquier ensemble futuro puede degradar por debajo del mejor modelo solo.
**Evidencia:** no hay camino de ensemble en el codigo; calipso/capabilities.py:262-263 (cap por defecto 0.4 y cap *= 0.7 si cap < 0.6 — penaliza, no descarta)

### [spec] Mezcla multi-proveedor: presupuesto y cuota por proveedor (duplicado del item 3)

**Por qué importa:** Duplica el item 3. Correccion menor al barrido: capacidad.py no modela 'una suscripcion por vez' — Mercado toma un dict de suscripciones y capacidad.py opera por nombre; lo que falta es comparar/presupuestar entre ellas.
**Evidencia:** calipso/economia/capacidad.py:28-60 (Suscripcion aislada, sin cuota cruzada), calipso/economia/pagador.py:31

### [spec] Mezcla multi-proveedor: presupuesto y cuota por proveedor con la eficiencia como criterio de comparacion

**Por qué importa:** Declarado spec futuro en el propio spec (:205) y sigue en cero: no se puede poner techo a Claude sin poner el mismo techo a todo lo demas. Matiz: capacidad.py SI modela N suscripciones (Mercado recibe un dict), lo que falta es presupuesto/cuota por PROVEEDOR de API.
**Evidencia:** calipso/economia/pagador.py:28 (un solo modelo en PRECIOS_API_MM_POR_MTOK), :31 (dos entradas cliente->suscripcion); calipso/config.py:22-30 (un unico api_monthly_usd, sin desglose por proveedor)

### [spec] No existe la dimension HOST/PROVEEDOR separada del modelo: la clave del registro es ruta:modelo

**Por qué importa:** El mismo peso servido por dos hosts a precio distinto es inexpresable, y tampoco se puede separar 'pesos abiertos' de 'ejecutable localmente' (research :146). Agregar o sacar proveedores hoy es editar el proxy LiteLLM, no Calipso.
**Evidencia:** calipso/capabilities.py:41 ('api:deepseek-chat', 'local:qwen2.5:7b'); calipso/config.py:35-40 (un unico base_url/api_key/model); calipso/server.py:1894-1905 manda cualquier modelo api a ese mismo proxy

### [spec] Regla anti-auto-juicio: ningun modelo (ni su familia) verifica salidas propias — no hay campo 'familia' en el registro

**Por qué importa:** La regla es hoy inexpresable y ademas se viola de fabrica: normalmente Claude juzga y fusiona salidas de Claude. El research (:111) precisa que el eje no es la empresa sino la distribucion de entrenamiento.
**Evidencia:** calipso/capabilities.py:41-102 (route/client/tier/persona/cost/speed/strengths, sin familia ni esfera); calipso/orchestrator.py:107-136 build_team; calipso/server.py:1695-1700 la sintesis usa verdict.get('route')/('client'), la misma ruta base del veredicto

### [spec] capabilities.py puntua aptitud ABSOLUTA en vez de brecha esperada contra el mejor modelo disponible

**Por qué importa:** Con score absoluto la decision economica es indirecta: nunca se pregunta '¿cuanto pierdo por no usar el caro aqui?'. Cambia la semantica del registro entero y del bucle de aprendizaje.
**Evidencia:** calipso/capabilities.py:262-272 (cap*1.0 - cost*0.25 + speed*0.2 - quota*0.6, con cost como constante de preferencia 0/1/3), WEIGHTS en :120

### [plan] El mini-RouterBench propio: un unico log de dispatch con (query, candidatos, elegido, costo, resultado) que permita replay offline *(parcial)*

**Por qué importa:** Existe la mitad cara (costo, modelo, latencia por turno) y falta la mitad que habilita el replay: los contrafactuales. Correccion al barrido: `ranked` no se tira del todo — server.py:2305 lo convierte en un `note` con los top-3 y sus scores que va al WebSocket y al harness context, pero nunca se persiste (telemetry.log_event no lo incluye). Capturar ese `note` en el evento es media tarea; unificar los dos logs es el plan.
**Evidencia:** dispatch.py:354-371 log_decision (~/.dispatch/decisions.jsonl: prompt truncado, ruta, cliente, why — sin costo ni modelo ni resultado); calipso/server.py:2544-2564 chat_turn (model_id, tier, effort, latency_ms, cost_usd, fallbacks — sin query, sin respuesta, sin candidatos)

### [plan] El router no elige por precio y aptitud con desempate por eficiencia (sigue el clasificador con prioridad fija suscripcion > API > local)

**Por qué importa:** Sin esto, cada moneda que gasta la fabrica la decide un regex, no el precio: capabilities.py:264-269 penaliza el costo como constante de preferencia (0/1/3) y nunca mira precio real ni eficiencia medida.
**Evidencia:** dispatch.py:528 llama route(prompt, args.route); dispatch.py:213 subscription_first; calipso/capabilities.py:8 docstring 'prefiere suscripciones sobre APIs pagas'; grep 'eficiencia' en dispatch.py/capabilities.py/server.py/connectors.py = 0 hits

### [plan] Escalon intermedio 'qwen x N con votacion por mayoria', con precio en latencia y no en dolares

**Por qué importa:** No hay camino de N muestras ni forma de que el router 'ofrezca' una opcion cara en latencia y barata en dolares. Depende del escalon local, que no corre.
**Evidencia:** calipso/server.py:1888-1921 _chunks_for hace exactamente una llamada; dispatch.py:317-347 run_api/run_local igual; calipso/capabilities.py:120 WEIGHTS tiene speed como bonificacion fija (+0.2), no como moneda negociable

### [plan] Jurado PoLL de 3 familias disjuntas baratas para el scoring

**Por qué importa:** El bucle de aprendizaje no tiene juez de ninguna clase: premia al backend que no revienta. Agravante verificado: como casi todo va por la misma ruta (items 6 y 15), la senal es degenerada — el ganador suele ser el unico candidato con muestras.
**Evidencia:** calipso/learning.py:54-72 propose elige ganador por (1 - tasa_de_fallback, -latencia_media) y mueve la afinidad ±0.05 (learning.py:22, :92)

### [plan] La promesa de privacidad esta rota: los prompts marcados como privados van a un CLI de suscripcion

**Por qué importa:** score_model (capabilities.py:255-256) descarta correctamente los no-private_ok, pero como la unica ruta private_ok no corre, el prompt sensible termina en la nube con un motivo que dice lo contrario. Es el caso que CALIPSO.md:23-24 prohibe expresamente.
**Evidencia:** dispatch.py:215-217 (PRIVATE -> route subscription, why 'suscripcion local sin API'); calipso/capabilities.py:183 private_ok = route == 'local'; capabilities.py:45,52 unicos private_ok True son los local, que estan caidos (connectors.py:89-90 + server.py:1363)

### [plan] La ruta 'local' del chat no corre local: ejecuta el CLI de suscripcion claude por subprocess

**Por qué importa:** Todo lo que el router manda a 'local' — incluido /local explicito — factura cuota Claude. El codigo ya es honesto consigo mismo (server.py:3850-3855 lo dice en un comentario y cobra suscripcion), pero AGENTS.md:336 sigue prometiendo Ollama.
**Evidencia:** calipso/server.py:1907 (# local no disponible (sin Ollama) -> suscripcion claude), :1909-1920 _local_via_sub lanza [claude, -p, user_msg]; dispatch.py:342-347 run_local redirige; calipso/server.py:1363 y :1710 local_up = False

### [tarea] Cooldowns por proveedor (allowed_fails / cooldown_time)

**Por qué importa:** Cuando Claude devuelve rate-limit, el router lo vuelve a elegir el turno siguiente; lo unico que pasa es un fallback que ademas termina otra vez en claude (server.py:1907). El research lo marca critico justamente con cuotas de suscripcion (:90).
**Evidencia:** calipso/connectors.py:16-44 limits_status solo lee el bloqueo manual (config.py:26-29) y el gasto del mes; no hay timestamp de ultimo error ni contador de fallos en ningun modulo (grep cooldown/allowed_fails/last_error = 0 hits en calipso/)

### [tarea] Criterio de admision de Anthropic antes de ir a multi-agente (frontera de contexto, paralelismo real, o 20+ herramientas) *(parcial)*

**Por qué importa:** Correccion al barrido: SI existe un gate de admision y no es trivial. Lo que falta es que sus criterios sean los del research — hoy decide por complejidad estimada y palabras conectoras (' y ', ' tambien '), no por frontera de contexto ni paralelismo real, y /plan|/team lo saltea entero (server.py:1450). Con la economia encendida, un equipo de 3 donde bastaba uno es plata destruida.
**Evidencia:** calipso/server.py:1448-1465 _should_orchestrate ('Activa equipo dinamico solo cuando suma valor real'): filtra por /fast, longitud del mensaje, tipo y complejidad

### [tarea] Detector de refusal que reenruta a un proveedor de otra esfera politica

**Por qué importa:** El research lo llama senal barata y accionable, pero depende del campo de esfera/jurisdiccion (item del host) y hoy seria inutil: el catalogo tiene una sola esfera viva.
**Evidencia:** grep refusal/rehus/refuse en calipso/ = 0 hits; calipso/server.py:2423-2505 solo distingue excepcion vs no excepcion

### [tarea] El baseline Zero Router (interpolacion aleatoria barato/caro) como prueba de honestidad

**Por qué importa:** Hoy nadie sabe si el scoring de capabilities.py aporta algo sobre elegir al azar al mismo costo; el research (:52) advierte que si no lo supera, no aporta.
**Evidencia:** nada en el repo compara capabilities.choose contra un baseline; test_capabilities.py no tiene noción de costo promedio

### [tarea] El clasificador local (segunda capa del router) fue borrado; decide_by_model devuelve suscripcion fija

**Por qué importa:** AGENTS.md:328 y SETUP.md:11 documentan una capa 2 que no existe. Correccion al barrido: config.py:45-48 ['classifier'] NO es codigo muerto — server.py:1502 lo usa para el planner del equipo dinamico (_plan_dynamic_team), que cae a _heuristic_plan porque Ollama no esta.
**Evidencia:** dispatch.py:256-260 (decide_by_model no llama a nadie); dispatch.py:245-253 CLASSIFIER_SYSTEM y :143-150 FEATURES_SYSTEM sin ningun referenciador

### [tarea] El descubrimiento de modelos de suscripcion sigue siendo un registry estatico

**Por qué importa:** Declarado en AGENTS.md:518. Nadie le pregunta al CLI que modelos tiene hoy, asi que un modelo nuevo de Anthropic/OpenAI no existe para Calipso hasta que alguien edite capabilities.py.
**Evidencia:** calipso/discovery.py:79-89 _cli_version solo hace shutil.which + --version; los modelos de suscripcion salen del dict duro capabilities.py:57-87; discover() (discovery.py:60-76) solo pregunta a Ollama y LiteLLM

### [tarea] El descubrimiento pregunta a dos endpoints fijos y adivina el tier con string-match a mano

**Por qué importa:** Los modelos del cuadro del research (minimax-m3, glm-5.2, kimi-k2.7, deepseek-v4-flash) caen todos en 'mid', y lo descubierto no trae precio, ni contexto, ni host — los tres datos que el research pide para decidir. Ademas discovery ignora la config que el propio repo ya tiene.
**Evidencia:** calipso/discovery.py:48 y :55 (localhost:11434 y localhost:4000 hardcodeados, sin leer config.py:36-43); discovery.py:36-45 guess_tier por substring

### [tarea] El effort real no llega a las bocas de suscripcion: solo viaja en el payload de API

**Por qué importa:** Declarado en AGENTS.md:517. Matiz al barrido: /ultrathink SI cambia algo — EFFORT_MIN_TIER (capabilities.py:35) fuerza tier frontier y server.py:1971-1972 pasa --model haiku|sonnet|opus. Lo que no llega es el parametro effort dentro del modelo elegido.
**Evidencia:** grep EFFORT_PARAM: solo calipso/capabilities.py:37, server.py:1530 y server.py:1903 (payloads LiteLLM); calipso/server.py:1922-1980 _subscription_invocation arma el cmd sin ninguna nocion de intensidad

### [tarea] El escalon 'API china barata' no se agrego: un solo modelo chino y es la generacion vieja

**Por qué importa:** Es la recomendacion 3 del research (:162). Agregar entradas es tarea, pero hacerlo bien depende del campo host y de precios reales (items siguientes), que hoy no existen.
**Evidencia:** calipso/capabilities.py:88 api:deepseek-chat (tier mid) y :95 api:claude-fable-5; no hay MiniMax M3, GLM-5.2, DeepSeek V4-Flash, Kimi ni Gemini

### [tarea] El escalon local sobre el que se apoya toda la palanca de ahorro no esta cableado

**Por qué importa:** Es el mismo hallazgo que el item 6 visto desde el research: prerrequisito de las recomendaciones 1, 4 y 7. Mientras el primer escalon cueste una unidad de suscripcion, la cascada no ahorra nada.
**Evidencia:** dispatch.py:342-347; calipso/server.py:1363 y :1710 local_up = False; server.py:1907-1921; capabilities.py:42-56 declara local:qwen2.5:3b/7b que connectors.py:89-90 marca no disponibles siempre

### [tarea] El eval de routing_accuracy que el research pide escribir ANTES de complejizar el router

**Por qué importa:** Sin conjunto etiquetado no hay forma de saber si un cambio al router mejora o empeora, y el research lo marca como precondicion (:97, :160), no como nice-to-have.
**Evidencia:** no existe /home/pedro/calipso/test_routing_accuracy.py; lo mas cercano es test_capabilities.py:30-46 (tres asserts a mano sobre el REGISTRY con available={todo True})

### [tarea] Hay DOS routers distintos: el CLI dispatch.py nunca llama a capabilities.choose()

**Por qué importa:** Confirmado. Matiz: comparten dispatch.extract_features (server.py:1388), asi que la extraccion de features SI es una sola. Lo que diverge es la decision: cualquier mejora del research aplicada a capabilities.py no toca el camino del CLI, y las dos superficies pueden rutear la misma consulta distinto.
**Evidencia:** dispatch.py:263-278 route() solo usa decide_by_rules/decide_by_model y devuelve una RUTA (sin modelo, tier ni intensidad); calipso/server.py:1409 es el unico llamador de capabilities.choose fuera de tests

### [tarea] Health-check de 'sin fallos en los ultimos 30 segundos' por proveedor

**Por qué importa:** La disponibilidad que alimenta el router (connectors.backend_availability, connectors.py:84-98) nunca se entera de que un proveedor acaba de fallar tres veces seguidas.
**Evidencia:** calipso/server.py:1339-1356 _ttl_cached cachea 20s 'claude --version' y GET /health (mide instalado+contesta, no 'viene fallando'); los fallbacks reales se acumulan en server.py:2436-2439 y :2480-2483 y solo van a telemetria

### [tarea] La senal '¿Pedro reintento?' como etiqueta de calidad gratis

**Por qué importa:** El bucle de aprendizaje premia al backend que no revienta y responde rapido, no al que responde bien. Un reintento o un /model forzado inmediatamente despues ya pasan por el WebSocket del chat y se descartan.
**Evidencia:** calipso/learning.py:46-50 (unico proxy: fails = hubo fallbacks, y latencia acumulada); grep reintent/retry en learning.py y server.py solo da los reintentos de cargos economicos (server.py:3520)

### [tarea] Lo que se descubre solo no se persiste: un modelo descubierto vive en memoria de un proceso

**Por qué importa:** El server funciona porque descubre en cada arranque; dispatch.py como CLI arranca con el REGISTRY pelado, asi que las dos superficies ven catalogos distintos. Ojo: CAP_FILE es tambien donde escribe el bucle de aprendizaje (learning.py:113-115), asi que escribir ahi no es una linea inocente — hay que decidir la fusion.
**Evidencia:** calipso/capabilities.py:170-185 discover muta el dict global REGISTRY; calipso/discovery.py:99-114 solo persiste la lista de NOMBRES en ~/.calipso/discovered.json; nada escribe CAP_FILE (capabilities.py:28), que es lo que load_backends fusiona (:161-167); server.py:3869 descubre al arrancar

### [tarea] Los strengths del registro son numeros a mano sin procedencia; el research pide calibrarlos con SWE-bench Pro

**Por qué importa:** El research (:142) avisa que el lider precio/aptitud cambia cada 4-6 semanas; sin procedencia no hay forma de saber que numero esta vencido. El bucle de aprendizaje (learning.py:88-96) los mueve ±0.05 encima, mezclando juicio a mano con senal medida sin distinguirlos.
**Evidencia:** calipso/capabilities.py:41-102 (opus code 0.95, codex code 1.0, deepseek reasoning 0.9) y :123-138 tier_prior, sin ningun campo de fuente ni fecha de revision

### [tarea] Pre-call check de ventana de contexto (no mandar 40k tokens a un modelo de 32k)

**Por qué importa:** score_model no puede descartar por contexto insuficiente, asi que un modelo chico puede ganar un prompt que no le entra. Agregar el campo es linea; usarlo como filtro duro en capabilities.py:251 es la tarea.
**Evidencia:** calipso/capabilities.py:41-102 no tiene campo de context window ni max output (grep context_window/max_input/max_output en calipso/ = 0 hits); lo unico parecido son umbrales de caracteres: server.py:1947 (>7000 chars vuelca a archivo) y dispatch.py:210 (>800 chars = 'largo')

### [tarea] dispatch.py no exige cuenta pagadora (default 'personal') y el cargo economico muere en un except silencioso

**Por qué importa:** Verificado: nada rechaza un request sin cuenta y un fallo NO economico (bug, disco lleno, import roto) pierde el cargo sin dejar pendiente, contra el criterio 'la fabrica registra CADA moneda'. Ojo: el default 'personal' lo pidio explicitamente el plan (docs/superpowers/plans/2026-08-25-economia-frontera.md:1379 y :1658), y docs/superpowers/plans/2026-08-25-economia-mercado.md:2007 dejo 'cuenta pagadora obligatoria en dispatch.py' fuera de alcance a proposito. El camino economico si esta bien (pagador.py:141-146). El servidor tiene el mismo default via _cuenta_en_foco (server.py:3785-3789).
**Evidencia:** dispatch.py:521 (--cuenta default='personal'), dispatch.py:579-580 (except Exception: pass)

### [tarea] quota_known hardcodeado en False y nunca medido, aunque el CLI puede reportarlo

**Por qué importa:** Correccion al barrido: costs.log_usage NO registra ceros dobles — server.py:2400 y :2392 setean completion_tokens = len(full.split()) (conteo de palabras), pero prompt_tokens si queda en 0 y el costo real de la ruta DOMINANTE nunca se mide. Un turno de 2k y uno de 200k cuestan lo mismo en el libro. Esto es lo medible que no se mide.
**Evidencia:** calipso/connectors.py:41 'quota_known': False fijo; calipso/server.py:1971-1974 arma [claude, --model X, --append-system-prompt-file, -p, prompt] sin --output-format json; calipso/economia/pagador.py:162-166 cargar_suscripcion cobra una unidad por turno

### [linea] AGENTS.md declara embeddings bge-m3 via Ollama como obligatorios; el codigo usa sentence-transformers

**Por qué importa:** El argumento (multilingue, no el default ingles de Chroma) se cumple; el mecanismo documentado no existe. Arrastra SPEC.md:396 y LINUX_MIGRATION.md:120: quien siga la doc instala Ollama+bge-m3 para nada.
**Evidencia:** calipso/memory.py:42 EMBED_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2', :139 SentenceTransformerEmbeddingFunction; AGENTS.md:63, :373-375, :462

### [linea] Degradacion elegante a un default fijo: SAFE_FALLBACK declarado, contradictorio y sin uso (duplicado del item 9)

**Por qué importa:** Duplica el item 9 desde el research. El default del servidor es peor que el del CLI: cae a un modelo local declarado en el registro que connectors marca no disponible siempre, o sea a _local_via_sub -> claude.
**Evidencia:** dispatch.py:82-84; defaults hardcodeados en dispatch.py:259, dispatch.py:276 y calipso/server.py:1438-1444 (else -> local:qwen2.5:7b, que no corre)

### [linea] El clasificador local que la docstring de dispatch.py promete es codigo muerto (duplicado del item 8)

**Por qué importa:** Duplica el item 8. Correccion importante al barrido: son TRES piezas muertas, no cuatro — config.py:45-48 ['classifier'] si lo lee codigo vivo, server.py:1502 lo usa como planner del equipo dinamico (y server.py:1068 lo expone en /api/harness/status).
**Evidencia:** dispatch.py:12-15 (docstring promete clasificador local Ollama con JSON) vs dispatch.py:256-260; CLASSIFIER_SYSTEM (:245-253) y FEATURES_SYSTEM (:143-150) sin referenciadores

### [linea] La descripcion del comando de verificacion dice que test_memory.py requiere Ollama con bge-m3

**Por qué importa:** Es texto que Pedro lee en el panel de Verificar y que ya no es cierto (memory.py:139 no toca Ollama).
**Evidencia:** calipso/tools/commands.py:159 "description": "Ejecuta test_memory.py (requiere Ollama con bge-m3)."

### [linea] Ponderacion cuadrado-inverso del precio en vez de argmax determinista

**Por qué importa:** Para un mismo (tipo, complejidad, intensidad) sale siempre el mismo modelo — perdida de diversidad de proveedores. La sugerencia de OpenRouter es muestrear el ranking con peso 1/precio^2, y ahora mismo ni siquiera hay precio real que muestrear (ver item del host).
**Evidencia:** calipso/capabilities.py:292 ranked.sort por score; calipso/server.py:1422 top = ranked[0]

### [linea] SAFE_FALLBACK vale 'subscription' pero su comentario y dos documentos dicen 'local'; ademas nadie la lee

**Por qué importa:** Es la unica salvaguarda de facturacion que SETUP.md:94-96 le promete a Pedro, y hoy es una constante huerfana que se contradice a si misma. El default real vive hardcodeado en tres sitios (dispatch.py:259, :276, server.py:1438).
**Evidencia:** dispatch.py:82-84 (comentario dice "local" para no escalar a una API de pago, valor = "subscription"); grep SAFE_FALLBACK: solo dispatch.py:84 y SETUP.md:95

## mapa (20)

### [spec] El pulso se pierde en cada reinicio: escritorios vacios con agentes que siguen corriendo

**Por qué importa:** Deliberado por la invariante 5, pero deja un desajuste real: subprocesos vivos y un mapa que afirma que no hay nadie trabajando.
**Evidencia:** calipso/mapa/pulso.py:126 (anillos en memoria, nada persiste) y calipso/server.py:3866 `_startup_warm` — no hay reconciliacion contra el bus al arranque

### [spec] Historial reproducible del mapa: 'ver la ciudad de hace tres semanas'

**Por qué importa:** Sin esto no se puede mirar como estaba la fabrica antes de una decision, que es la unica ventaja de tener un libro append-only.
**Evidencia:** calipso/server.py:3757 — `def api_mapa_ciudad() -> dict:` sin parametro de semana; calipso/mapa/ciudad.py:262 `ciudad(...)` si recibe `semana`

### [spec] Persistir el pulso o reproducir la ciudad de hace tres semanas

**Por qué importa:** Solapa con los items 9 y 16: la ciudad pasada si es derivable del libro y falta el control; la capa viva no lo es y falta decidir que significa 'pasado' para ella.
**Evidencia:** calipso/server.py:3757 (endpoint sin parametro de semana) y calipso/mapa/pulso.py:126 (anillos en memoria)

### [plan] El campo `trabajo` del evento del pulso nunca se llena: ningun agente vivo se ata a un trabajo del bus

**Por qué importa:** La capa viva queda desconectada de las `unidades` de la ciudad: no se puede saber que agente ejecuta que trabajo, que es el puente entre la seccion 3 y la 5.
**Evidencia:** calipso/server.py:614, :1620, :2322 pasan departamento/rol/modelo y omiten trabajo; `grep 'trabajo=' --include=*.py` fuera de tests solo da calipso/mapa/pulso.py:185

### [plan] Mapa RTS: la vista existe pero sin las perillas que el spec le pide mostrar y mover

**Por qué importa:** Sin perillas el mapa es solo un tablero de lectura: no hay forma de jugar el RTS (mover presupuesto, explorar/explotar, techo de API, agresividad) sin editar el JSON del registro a mano.
**Evidencia:** calipso/web/fabrica/paneles.js:30 (textoDeTarjeta solo pinta saldo/gasto/ventas/eficiencia/trabajos/compuertas) + calipso/mapa/ciudad.py:277-286

### [plan] `calipso/orchestrator.py` y `dispatch.py` no publican al pulso, contra lo que dice el spec

**Por qué importa:** Cualquier agente lanzado fuera del WebSocket de /fabrica (routines, jobs, verificacion, resource_dispatcher) no aparece en ningun escritorio: el interior de un departamento va a estar vacio justo mientras la fabrica trabaja.
**Evidencia:** calipso/orchestrator.py y dispatch.py: cero ocurrencias de `pulso`/`PULSO`; toda la instrumentacion vive en calipso/server.py:1620

### [plan] `dispatch.py` corrido como CLI no publica al pulso: los agentes de terminal no aparecen en ningun escritorio

**Por qué importa:** Descartado a proposito (pedia un POST autenticado entre procesos), pero el plan de la ciudad lo habia prometido para el Plan 3: el trabajo hecho desde la terminal es invisible en el mapa.
**Evidencia:** dispatch.py: cero ocurrencias de `pulso`; declarado en docs/superpowers/plans/2026-08-25-mapa-acoplamiento.md:3519 y :3529

### [tarea] AGENTS.md no menciona el mapa RTS ni la fabrica: un cliente entero (24 archivos JS/CSS) y su servidor

**Por qué importa:** Es peor de lo que dijo el barrido: AGENTS.md tampoco menciona `calipso/economia/` (19 modulos) ni /api/economia/*; un agente que lea AGENTS.md como fuente de verdad va a creer que la mitad del sistema no existe.
**Evidencia:** AGENTS.md:112 ('UI (calipso/web/index.html)'), :303 (arquitectura, solo index.html) y :377-444 (mapa del repo, sin calipso/mapa/ ni calipso/web/fabrica/)

### [tarea] El agente del turno de chat se abre y se cierra a mano: un turno que revienta fuera del `except` queda razonando diez minutos

**Por qué importa:** Diez minutos de escritorio mintiendo cada vez que un turno muere por una via que no pasa por el except; el envoltorio `_pulso_agente` (server.py:3599) ya existe y solo falta la re-indentacion que se evito.
**Evidencia:** calipso/server.py:2317-2323 (inicio, con el comentario que lo admite) y :2535-2543 (tokens+fin), sin `try/finally` que los ate; el colchon es INACTIVO_S = 600 en calipso/mapa/pulso.py:32

### [tarea] El anclaje del urbanismo tiene una excepcion viva: un departamento que nunca aparecio en el libro se mueve cuando nace otro

**Por qué importa:** Contradice la seccion 4 ('el corrimiento es cero por construccion') justo para los departamentos recien abiertos, que es cuando Pedro los esta mirando.
**Evidencia:** calipso/mapa/ciudad.py:155 `nunca = len(aparicion)` y :167 `"orden": aparicion.get(cuenta, nunca)`

### [tarea] El anclaje exacto del urbanismo tiene una excepcion: un departamento que nunca transo se mueve al nacer otro

**Por qué importa:** Duplicado del item 7: rompe 'ningun edificio existente se mueve' para los departamentos recien abiertos. El arreglo necesita un desempate determinista para las cuentas sin historia sin romper la invariante 2.
**Evidencia:** calipso/mapa/ciudad.py:155 y :167 (mismo defecto que el item 7; sin cambios respecto de lo que midio el spec)

### [tarea] El costo en monedas de un agente de equipo siempre es 0 y los tokens son una estimacion de caracteres/4

**Por qué importa:** Rompe el criterio de exito 'ver a un agente razonando con su costo corriendo': el popup miente en tokens y muestra costo cero para todo agente de equipo.
**Evidencia:** calipso/server.py:1651 — `mango.tokens(len(agent_system) // 4, len(output) // 4, 0)`

### [tarea] El escritorio del empleado de equipo muestra tokens inventados y costo cero

**Por qué importa:** Es el mismo defecto del item 6: el contrato del evento dice 'tokens_in, tokens_out y costo_mm acumulados' y lo que viaja son caracteres/4 y un literal cero.
**Evidencia:** calipso/server.py:1651 — `mango.tokens(len(agent_system) // 4, len(output) // 4, 0)`

### [tarea] El evento `herramienta` del contrato del pulso no tiene ningun productor en todo el codigo

**Por qué importa:** De los seis eventos de agente del spec este es el unico muerto de punta a punta: el popup del empleado nunca va a decir que herramienta esta usando.
**Evidencia:** calipso/mapa/pulso.py:105 (unica definicion) y calipso/server.py:3590 (el stub nulo) — no hay otro `.herramienta(` en .py ni .js fuera de tests

### [tarea] El evento `herramienta` del pulso no lo publica nadie ni lo pinta nadie

**Por qué importa:** Duplica el item 2 y agrega el otro extremo: aunque manana alguien publicara el evento, el popup no lo mostraria — falta productor Y pintor.
**Evidencia:** productor: ninguno (calipso/mapa/pulso.py:105 es la unica definicion); consumidor: calipso/web/fabrica/paneles.js:88-100 `textoDeEmpleado` no menciona `herramienta`

### [tarea] La "Verificacion a ojo" del plan de acoplamiento — ocho comprobaciones humanas que nadie pudo haber hecho

**Por qué importa:** Las ocho empiezan 'con la semana abierta' y la semana nunca se abrio: todo el acoplamiento (vuelo de camara, cobro al departamento en foco, techo que se desvanece, popup, reconexion, pinza en el telefono) esta sin verificar en vivo.
**Evidencia:** docs/superpowers/plans/2026-08-25-mapa-acoplamiento.md:3503-3514; `~/.calipso/economia/` no existe (ls: No such file or directory)

### [tarea] Las cartas pendientes no cuelgan de ningun edificio y solo existen en la barra *(parcial)*

**Por qué importa:** La mitad de lo que el spec llama 'aviso' no tiene representacion espacial, y el criterio 'ninguna compuerta pasa desapercibida' depende de una barra que ademas solo se pinta al arrancar (calipso/web/fabrica/app.js:371, unica llamada a traer()).
**Evidencia:** calipso/mapa/ciudad.py:252 (`sobre = None` para toda carta) y calipso/web/fabrica/ciudad.js:26 (`if (!a.sobre) continue`)

### [tarea] `Pulso.empleados()` es codigo muerto en el servidor: la vista derivada de la seccion 5 se reimplemento en JavaScript *(parcial)*

**Por qué importa:** Hay dos definiciones de 'quien esta sentado en un departamento' (Python con estado_de/resumen, JS con estadoVisible) que pueden divergir sin que nada lo agarre, y solo una se usa.
**Evidencia:** calipso/mapa/pulso.py:212 (solo la llaman test_mapa_pulso.py:178 y test_mapa_ws.py:89); lo que llena el popup es calipso/web/fabrica/pulso.js:110 `empleadosDe`

### [linea] La colocacion del urbanismo no converge a 300 iteraciones

**Por qué importa:** Duplicado del item 8: decision no tomada, no bug; el determinismo se mantiene porque la constante es fija.
**Evidencia:** calipso/mapa/urbanismo.py:48 — `ITERACIONES = 300` (tambien usado como default en :99)

### [linea] La colocacion del urbanismo no converge del todo a 300 iteraciones

**Por qué importa:** No rompe ninguna garantia declarada ni el determinismo; es una perilla de calidad visual con costo ya medido (medio segundo a 4.000 iteraciones con 36 edificios).
**Evidencia:** calipso/mapa/urbanismo.py:48 — `ITERACIONES = 300`

## cliente (17)

### [spec] Clientes multiplataforma: PWA a medias y sensores nativos de medicion pasiva sin empezar *(parcial)*

**Por qué importa:** La mitad PWA esta mas cerrada de lo que dice el barrido (manifest, registro del sw y shell que cachea los 12 modulos de fabrica); lo abierto es todo lo demas: sin sensores pasivos el reloj y los libros personales dependen de que Pedro fiche a mano, que es lo que la economia no puede auditar. src-tauri/ (sin commitear) es un webview que levanta el server, sin un solo sensor.
**Evidencia:** calipso/web/sw.js:1-19 + calipso/web/fabrica/index.html:56-62 (PWA completa); cero hits de knowledgeC/Screen Time/Atajos/wmctrl en todo el repo

### [plan] Sonido en el mapa

**Por qué importa:** Antes del codigo hay que decidir si un .wav en el repo viola la invariante 6 ('cero archivos de imagen', spec:21) llevada a su espiritu, o si solo vale sintetizar por WebAudio como se sintetizan los sprites.
**Evidencia:** grep de 'audio|sonido|oscillator|.wav|.mp3' sobre calipso/web/fabrica/: cero resultados

### [tarea] Animacion de agentes caminando dentro del interior de un departamento

**Por qué importa:** No rompe nada hoy, pero el cache del interior esta cerrado por construccion: meter movimiento obliga a sacar a los caminantes del raster o a meter `fase` en la clave y hacer explotar el cache.
**Evidencia:** calipso/web/fabrica/sprites.js:135 interiorSprite(edificio, estados) no recibe `fase`; calipso/web/fabrica/mapa.js:110-112 cachea el interior con clave `i|id|zona|estado|tamano|esc|estados`

### [tarea] Animar a los agentes caminando dentro del interior (duplicado del item 9)

**Por qué importa:** Mismo pendiente que el item 9, pero la ubicacion que da el barrido esta mal: interior.js es aritmetica de hit-testing, el dibujo esta en sprites.js:135 y el cache que lo bloquea en mapa.js:110.
**Evidencia:** calipso/web/fabrica/sprites.js:135-165 (escritorios estaticos con tres estados) y calipso/web/fabrica/interior.js:24 escritorioEnPunto, que asume posiciones fijas de plazasDe()

### [tarea] El cliente nunca vuelve a pedir /api/mapa/ciudad: la foto queda congelada toda la sesion

**Por qué importa:** Saldos, tamanos, gasto del ciclo y compuertas quedan viejos apenas se abre la pagina: una compuerta nueva no aparece nunca, y eso rompe el criterio de exito del spec:202 ('ninguna compuerta pendiente pasa desapercibida').
**Evidencia:** calipso/web/fabrica/app.js:371 y app.js:47 son las dos unicas llamadas a traer(); calipso/server.py:3607-3636 (/ws/mapa) solo reenvia eventos del pulso

### [tarea] El dpr se redondea a entero (duplicado del item 10)

**Por qué importa:** Mismo pendiente que el item 10; el plan y el codigo dicen exactamente lo mismo, no son dos deudas distintas.
**Evidencia:** calipso/web/fabrica/mapa.js:79-81; el comentario del plan en docs/superpowers/plans/2026-08-25-mapa-cliente.md:1206-1214 quedo copiado literal en mapa.js:71-78

### [tarea] El dpr se redondea a entero: en pantallas con dpr fraccionario el pixel art pierde nitidez

**Por qué importa:** En un aparato que no sea de Pedro (Windows al 150%) el navegador reescala el lienzo entero y el pixel art —que es toda la identidad visual de la fabrica— se ve borroso.
**Evidencia:** calipso/web/fabrica/mapa.js:79-80 `Math.max(1, Math.min(3, Math.round(window.devicePixelRatio || 1)))`, con la DEUDA DECLARADA en el comentario de mapa.js:71-78

### [tarea] El nivel de camara 'barrio' no existe: solo hay ciudad e interior

**Por qué importa:** Decir 'miremos a Atlas' aterriza en un zoom arbitrario (un 2 suelto, ni ciudad ni interior) en vez de encuadrar el departamento con sus socios comerciales, que es lo unico que hace legible con quien trabaja.
**Evidencia:** calipso/web/fabrica/camara.js:90 encuadrar() (toda la ciudad) e interior.js:12 UMBRAL=3; calipso/web/fabrica/app.js:434 volarA(cam, {..., escala: Math.max(cam.escala, 2)})

### [tarea] La 'Verificacion a ojo' del plan del cliente: siete comprobaciones de render que nadie miro, y la lista esta mal numerada

**Por qué importa:** El spec:178 delega el render fino a la verificacion a ojo, asi que estas siete comprobaciones son la unica cobertura que tiene el dibujo, y estan bloqueadas hasta que exista un libro con datos.
**Evidencia:** docs/superpowers/plans/2026-08-25-mapa-cliente.md:2390-2397 numera 1,2,3,4,3,4,5,6 (4 y 3 repetidos en :2393-2394); no existe ~/.calipso/economia/, asi que /api/mapa/ciudad responde {'activa': false} y no hay ciudad que mirar. Los 45 checkboxes del plan siguen todos en `- [ ]`, asi que el estado de los checkboxes no prueba nada en ningun sentido

### [tarea] La animacion de transicion entre dos layouts consecutivos no existe

**Por qué importa:** Hoy es latente porque el modelo nunca se recarga (item 2); en cuanto se arregle la recarga la ciudad se teletransporta, que es exactamente lo que el spec:102 dice que no debe pasar.
**Evidencia:** calipso/web/fabrica/mapa.js:151 dibuja aPantalla(cam, centroDe(e), v) directo del modelo; calipso/web/fabrica/app.js:33 reemplaza `ciudad` de un saque sin guardar el anterior

### [tarea] La cascada del CSS de /fabrica sigue sin ningun test

**Por qué importa:** Si alguien toca el complemento exacto del media query, por debajo de 820px queda una trampa sin salida (tres columnas sobre grilla de una, sin #pestanas, con #expandir en display:none) y nada la agarra.
**Evidencia:** grep de 'estilo.css|mapa-entero|sin-fabrica|820' sobre todos los *.py del repo: cero resultados. Las dos reglas viven solas en calipso/web/fabrica/estilo.css:173 y :142

### [tarea] La cascada del CSS del cliente no tiene test y dos arreglos viven solo en el archivo (duplicado del item 5)

**Por qué importa:** Es el mismo pendiente que el item 5, y le bajo el tamano de plan a tarea: el navegador ya esta en el repo (calipso/browser.py:33 `screenshot(url, path, full_page, width, height)`, Playwright con viewport parametrizable), asi que testear la cascada a 800px es una tarea con skip limpio como el que test_fabrica_js.py ya hace con node, no un plan para meter un navegador nuevo.
**Evidencia:** calipso/web/fabrica/estilo.css:173 (`@media not all and (max-width: 820px)` con `#app.mapa-entero` adentro) y :142/:148 (`.sin-fabrica` con `background: var(--fondo)`); ningun *.py los menciona

### [tarea] Los artifacts conversacionales no se persisten como recursos descargables con URL propia

**Por qué importa:** Un artifact largo se pierde al recargar la pagina o al cambiar de chat, y no hay forma de linkearlo ni bajarlo: la unica salida es el portapapeles.
**Evidencia:** calipso/web/index.html:1678-1707 maybeRenderArtifact solo crea un .artifact-card en el DOM con Abrir/Copiar; el unico endpoint de artifacts es calipso/server.py:3220 `/api/jobs/{job_id}/artifacts/{name}`, atado a jobs

### [tarea] arranque.test.js importa app.js una sola vez y sus tests comparten estado en orden

**Por qué importa:** Meter un test en el medio del archivo puede romper los de abajo por estado compartido, y el que lo rompa no va a entender por que.
**Evidencia:** calipso/web/fabrica/arranque.test.js:190 `import("./app.js").then(m => { modulo = m; ... })`, unica importacion para 441 lineas (18.419 bytes) de tests

### [tarea] arranque.test.js importa app.js una sola vez y sus tests comparten estado en orden (duplicado del item 7)

**Por qué importa:** Mismo pendiente que el item 7: el spec lo declara inevitable sin jsdom, asi que lo unico accionable es partir el archivo o meter jsdom, no 'arreglarlo'.
**Evidencia:** calipso/web/fabrica/arranque.test.js:190, unica importacion de app.js en las 441 lineas del archivo

### [linea] /fabrica no esta enlazado desde ningun lado: hay que saber la URL de memoria

**Por qué importa:** Rompe la regla de producto de RUNBOOK.md:83 aplicada a URLs: la mitad nueva de Calipso es invisible salvo que Pedro se acuerde de tipear /fabrica.
**Evidencia:** grep de 'fabrica' sobre calipso/web/index.html: cero resultados. El endpoint existe (calipso/server.py:3896) y el shell del service worker ya cachea '/fabrica' (calipso/web/sw.js:4), pero nada lo linkea

### [linea] El piso de tests de JavaScript sigue en 90 y el comentario que lo justifica quedo desactualizado

**Por qué importa:** El comentario esta peor de lo que dice el barrido: discrepa 52 tests con la realidad y 45 con el spec. arranque.test.js entero (45 casos) puede desaparecer sin que la suite se entere.
**Evidencia:** test_fabrica_js.py:20 PISO_DE_TESTS = 90; test_fabrica_js.py:18-19 dice '(hoy 111)'; corri `node --test` en calipso/web/fabrica y hoy imprime '# pass 163'

## infraestructura (20)

### [spec] Conectores automaticos de senales externas (webhooks, conciliacion) y conectores bancarios personales; mas la superficie de ingesta manual que hace de fallback *(parcial)*

**Por qué importa:** La invariante 10 (solo la senal exterior acuna) no tiene por donde entrar desde la UI: hoy acunar una venta o cargar el sueldo exige abrir un REPL de Python contra el libro, y sin eso el tipo de cambio y los criterios de muerte nunca ven un ingreso real.
**Evidencia:** calipso/connectors.py:16-118 (solo health/limites de Claude/Codex/Ollama/LiteLLM; ni un webhook ni una senal externa). Las primitivas de ingesta SI existen — calipso/economia/kernel.py:47 acunar() y calipso/economia/personal.py:35 LibroPersonal.registrar() — pero no tienen superficie: los endpoints de calipso/server.py:3429-3552 son tablero, cola, reloj in/out/conciliar, cierre y abrir; ninguno acuna ni registra. server.py:3396 instancia LibroPersonal solo para leerlo en el tablero.

### [spec] Multi-PC federado: cero codigo

**Por qué importa:** Sin esto un segundo PC no puede leer nada de este: no hay indice de ubicacion, ni selector de maquina, ni /api/file remoto — y la decision de arquitectura ya tomada no basta para planificar.
**Evidencia:** `grep -rEi 'federa|multi-pc|multipc|peer'` sobre todo calipso/ no devuelve un solo resultado. Las decisiones estan fijadas en AGENTS.md:478-479 (cada PC dueno de sus archivos, nada de Syncthing) y el bloque grande en AGENTS.md:504-505 pide indice de ubicacion + selector de maquina en la UI.

### [spec] Multi-usuario o espectadores del mapa

**Por qué importa:** No se puede mostrarle el mapa a nadie mas que a Pedro: cualquiera con el token ve razonamientos, diffs y costos de todos los departamentos, porque no hay sujeto al que filtrarle nada.
**Evidencia:** calipso/server.py:152-153 (_valid es un hmac.compare_digest contra un unico TOKEN global), :264-277 (auth_guard: cookie valida o token en query, sin identidad), :3616-3634 (ws_mapa acepta con _valid y manda TODO el anillo del pulso desde cursor 0 a quien pase)

### [plan] Clientes multiplataforma: ROG Ally como servidor via Tailscale y sensores nativos para el reloj *(parcial)*

**Por qué importa:** El reloj de la seccion 9 depende de que Pedro fiche a mano para siempre: sin sensores no hay medicion pasiva, y sin Tailscale automatizado el servidor solo existe dentro de la LAN.
**Evidencia:** La PWA existe por duplicado y esta cerrada: calipso/web/manifest.json + calipso/web/sw.js y calipso/web/fabrica/manifest.json. Lo demas es cero: `grep -ri 'knowledgeC|screen time|atajos|shortcuts|sensor'` sobre calipso/ no devuelve nada, y Tailscale aparece solo como texto en calipso/goals.py:94 y en los comentarios calipso/server.py:9 y :106 — ninguna linea de codigo lo detecta, configura ni mide.

### [plan] Cuota de computo local por departamento y cuota reducida para congelados (el bus como vector de saturacion gratuita)

**Por qué importa:** Un departamento congelado puede dar de alta propuestas infinitas y encolar trabajo local sin pagar nada: bus.py solo bloquea al congelado en financiar() (:128) y direccion.py:38, asi que el congelamiento no le cuesta computo y la quiebra deja de ser un limite real.
**Evidencia:** calipso/resource_dispatcher.py:44-58 (MODEL_RAM_MB y umbrales globales; grep de 'departamento|congelado|cuota' en el archivo: cero resultados) y calipso/economia/bus.py:47-73 (Bus.alta valida id, criterio, presupuesto y retorno — nunca consulta deps.es_congelado)

### [plan] `pytest` a secas y los test_*.py legacy con main()

**Por qué importa:** Es peor que lo que decia el doc: `pytest` a secas no rompe, pasa en verde saltandose 24 suites enteras (memoria, sesiones, orchestrator, github, streaming) — nadie se entera de que no corrieron, y de paso la coleccion ensucia CALIPSO_HOME para los tests que si corren.
**Evidencia:** 24 archivos (no 23: falta contar test_chat_live.py) tienen `def main(`. PERO la premisa del barrido es falsa: `.venv/bin/python -m pytest --collect-only -q` sale con codigo 0 y colecta 288 tests en 37s, sin un solo error de coleccion. El conteo por archivo muestra que los 288 salen de test_economia_*, test_mapa_*, test_resource_dispatcher.py, test_seguridad_secretos.py y test_fabrica_js.py: los 24 legacy aportan CERO. Ademas test_memory.py:14-18 setea os.environ['CALIPSO_HOME'] a nivel de modulo, o sea que la sola coleccion contamina el entorno del resto.

### [tarea] 'Estado operativo de esta sesion' de AGENTS.md describe Windows, sin origin y sin gh

**Por qué importa:** Las tres afirmaciones son falsas y AGENTS.md:532-533 declara que este archivo debe ser autocontenido porque Codex no lee la memoria de Claude: un agente que lo crea busca el repo en una ruta inexistente y descarta gh y el push.
**Evidencia:** AGENTS.md:38 dice `C:\Users\Pedro\Desktop\proycto`, rama `main` — el repo esta en /var/home/pedro/calipso y el checkout esta en la rama fix/secretos-en-0600 con calipso/web/index.html modificado sin commitear. AGENTS.md:39 'no hay origin configurado' — `git remote -v` da origin git@github.com:pedro-cmyks/calipso.git. AGENTS.md:40 'gh no esta instalado' — esta en /home/linuxbrew/.linuxbrew/bin/gh.

### [tarea] El config real apunta a claude.cmd/codex.cmd: la CLI dispatch.py no puede despachar en Linux

**Por qué importa:** Cualquier uso de Calipso por CLI (el alias `ai` de SETUP.md) muere con exit 127 en la ruta de suscripcion, que es la ruta por defecto de la politica subscription_first.
**Evidencia:** calipso/config.py:32-34 hardcodea ['claude.cmd', ...] y ['codex.cmd', ...] en DEFAULT_CONFIG; los guardas de :84-87 son `if os.name == 'nt' and subscription.get('claude')[0] == 'claude'` — nunca disparan porque el default YA es .cmd. ~/.calipso/config.json tiene 'claude.cmd'. dispatch.py:299 `if shutil.which(template[0]) is None: return 127`. En esta maquina hay /home/pedro/.local/bin/claude y .../codex; `which claude.cmd` no encuentra nada. El servidor se salva por calipso/server.py:1206-1209 (_subscription_command resuelve el exe aparte segun os.name).

### [tarea] PWA + Tailscale: la PWA existe, el acceso remoto nunca se automatizo *(parcial)*

**Por qué importa:** Pedro no tiene forma de saber desde Calipso si el acceso remoto esta arriba ni por que IP entrar desde el iPhone: la unica direccion que el runbook le da es una IP de LAN escrita a mano.
**Evidencia:** PWA cerrada: el checklist ya la chequea en calipso/server.py:2720 (manifest_ok = manifest.json y sw.js existen) y ambos estan. Tailscale abierto: solo texto en calipso/goals.py:94 ('Acceso seguro definido (Tailscale/token/TOTP)') y los comentarios calipso/server.py:9 y :106. El checklist de calipso/server.py:2711-2760 no tiene ningun item de tailscaled ni de IP de tailnet. RUNBOOK.md:58 sigue hardcodeando http://192.168.1.10:8000.

### [tarea] RUNBOOK.md es integramente de Windows y AGENTS.md lo cita como la guia para prender Calipso

**Por qué importa:** Es el documento de emergencia y en la unica maquina que existe hoy ninguno de sus tres caminos funciona; el que si funciona (./calipso.sh) no esta escrito en ningun lado salvo LINUX_MIGRATION.md.
**Evidencia:** RUNBOOK.md:8-32: 'En Windows, doble clic: Calipso.bat', 'O desde PowerShell: .\Calipso.ps1', y :26-32 son siete lineas diagnosticando el PATH de Python en PowerShell. `grep calipso.sh RUNBOOK.md` no da nada. AGENTS.md:30-31 lo declara la guia para cuando localhost esta caido.

### [tarea] Subir el escalon Ollama de qwen2.5 a qwen3:14b (o 8b)

**Por qué importa:** Subo el tamano de 'linea' a 'tarea': no son solo constantes — hay que pullear el modelo (~9 GB, hoy no esta), agregar su RAM a MODEL_RAM_MB para que el dispatcher no lo mande a REROUTE por desconocido, y revisar los umbrales max_complexity/strengths de capabilities.py, que estan calibrados para un 7b.
**Evidencia:** `grep -rn qwen3` sobre todo el repo (.py y .json): cero resultados. Los tres lugares siguen en qwen2.5: calipso/config.py:41-48 (local.model='qwen2.5:7b', classifier.model='qwen2.5:3b'), calipso/capabilities.py:42-56 (REGISTRY con 'local:qwen2.5:3b' y 'local:qwen2.5:7b') y calipso/resource_dispatcher.py:44-54 (MODEL_RAM_MB sin ninguna entrada qwen3, o sea que un qwen3:14b caeria al default de estimacion). `ollama list` en la maquina: solo bge-m3, qwen2.5:7b y qwen2.5:3b.

### [tarea] Tres endpoints de conectores/suscripciones rotos en Linux por subprocess.CREATE_NEW_CONSOLE

**Por qué importa:** Los botones de instalar y autenticar claude/codex existen en la UI y devuelven 500 en toda maquina Linux — la superficie muerta que CALIPSO.md:73 prohibe; y el arreglo no es solo borrar el flag, porque `claude login` necesita un TTY que en POSIX hay que decidir de donde sale.
**Evidencia:** calipso/server.py:1117 (/api/connectors/{name}/{action}), :1134 (/api/subscriptions/{client}/install) y :1154 (/api/subscriptions/{client}/login) pasan creationflags=subprocess.CREATE_NEW_CONSOLE. El atributo no existe en POSIX; se evalua dentro del try, cae en `except Exception as e` y sale como HTTPException 500 con el texto del AttributeError.

### [tarea] src-tauri/ y Cargo.toml sin commitear: la app nativa fuera de Git *(parcial)*

**Por qué importa:** Hay una app nativa que compila y corre y que un `git clean -fd` borra sin recuperacion; ademas ningun doc, lanzador ni checklist la conoce, asi que existe solo en esta maquina.
**Evidencia:** `git status`: `?? Cargo.lock`, `?? Cargo.toml`, `?? src-tauri/`; `git log --all -- src-tauri Cargo.toml` no devuelve nada (nunca estuvo versionado). Pero NO esta a medias: src-tauri/tauri.conf.json apunta a http://127.0.0.1:8000 con CSP completo y bundle targets appimage+rpm (Linux, no Windows/macOS), y target/release/calipso es un binario de 12,5 MB ya compilado (19 jun 18:17), con target/release/bundle/. .gitignore ignora target/ y src-tauri/target/ pero no src-tauri/ — la intencion era versionarlo. RUNBOOK.md:86 sigue describiendolo como objetivo futuro 'app nativa en Windows/macOS'.

### [linea] 'Entorno y dependencias' de AGENTS.md dice Windows 11 / PowerShell y que python no esta en PATH

**Por qué importa:** La seccion que un agente lee para saber como correr algo describe otra maquina y otro interprete, y su mapa de archivos omite los cuatro modulos mas nuevos del repo.
**Evidencia:** AGENTS.md:456-458 ('OS: Windows 11, PowerShell', 'Python: 3.12 esperado. En esta sesion el ejecutable no esta disponible en PATH'). La maquina es Bazzite/Fedora con .venv en el repo corriendo Python 3.14 (.venv/lib64/python3.14/). El gotcha de CPU de :467-469 sigue vigente pero hoy lo modela calipso/resource_dispatcher.py, que AGENTS.md no menciona nunca — su listado de estructura (AGENTS.md:412-445) tampoco lista resource_dispatcher.py, plugins.py, economia/, mapa/ ni web/fabrica/.

### [linea] El checklist de arranque solo busca los lanzadores de Windows; ignora calipso.sh

**Por qué importa:** Corregi el barrido: los tres archivos .bat/.ps1/.py EXISTEN en el repo, asi que en Linux el checklist da 'Lanzadores: ok' en verde contando dos scripts que no pueden ejecutarse — es peor que reportar faltantes, porque miente en verde sobre el unico item que dice si Calipso se puede prender.
**Evidencia:** calipso/server.py:2721-2724: launchers = {'windows_bat': Calipso.bat, 'windows_ps1': Calipso.ps1, 'python': launch_calipso.py}; el item se arma en :2753-2755 con all(launchers.values()). calipso.sh esta versionado (`git ls-files` lo lista) y es el lanzador real de esta maquina, y no figura.

### [linea] El piso de tests de JavaScript es una red, no un trinquete

**Por qué importa:** Con 163 pasando y piso 90 pueden desaparecer setenta y tres tests del cliente — arranque.test.js, chat.test.js y mapa.test.js enteros — sin que la suite parpadee.
**Evidencia:** test_fabrica_js.py:20-22 — el comentario dice 'hoy 111' y PISO_DE_TESTS = 90. Corri `node --test` en calipso/web/fabrica: '# pass 163, # fail 0'. El piso ya quedo desactualizado tres veces (spec decia 118, el comentario 111, la realidad 163).

### [linea] LINUX_MIGRATION.md manda clonar en ~/projects/calipso y a instalar tres modelos de Ollama *(parcial)*

**Por qué importa:** La ruta de clone lleva a un segundo checkout paralelo al real, y el pull de bge-m3 baja 1,2 GB que ya nada usa para embeddings; el resto de la seccion de Ollama sigue siendo correcta.
**Evidencia:** LINUX_MIGRATION.md:66-70 (`mkdir -p ~/projects; cd ~/projects; git clone ...`) contra el repo real en /var/home/pedro/calipso. LINUX_MIGRATION.md:117-121 pide pull de qwen2.5:3b, qwen2.5:7b y bge-m3. Corrijo al barrido en dos puntos: bge-m3 SI quedo obsoleto para embeddings (calipso/memory.py:42 usa 'paraphrase-multilingual-MiniLM-L12-v2' via sentence-transformers) pero sigue vivo como entrada en calipso/resource_dispatcher.py:46 y descargado en ollama; y qwen2.5:3b NO es de un clasificador borrado — el clasificador esta vivo y se usa en calipso/server.py:1502-1506 (_plan_dynamic_team lee dispatch.CONFIG['classifier']) y declarado en calipso/config.py:45-48.

### [linea] La receta de instalacion documentada produce un Calipso roto: faltan sentence-transformers y faster-whisper

**Por qué importa:** Un reclone siguiendo el doc revienta al importar calipso/memory.py — el import es de nivel de modulo, no lazy — o sea que el chat no arranca, no es que degrada; el dictado (faster_whisper, import diferido) falla mas silenciosamente.
**Evidencia:** calipso.sh:14 y LINUX_MIGRATION.md:89 instalan `chromadb ollama playwright litellm fastapi uvicorn[standard] pyotp qrcode pillow`. calipso/memory.py:36 importa SentenceTransformerEmbeddingFunction a nivel de modulo (:139 y :42 con EMBED_MODEL='paraphrase-multilingual-MiniLM-L12-v2') y calipso/server.py:3310 importa faster_whisper. Los dos estan en el .venv actual pero ninguno figura en la lista, y no existe requirements.txt en el repo.

### [linea] Las rutas de datos runtime de AGENTS.md apuntan al perfil de Windows

**Por qué importa:** Es la ruta que AGENTS.md:531-533 senala como la memoria que Codex no lee automaticamente: si esta mal, el unico puntero a la memoria persistente apunta a un directorio que no existe.
**Evidencia:** AGENTS.md:451 y AGENTS.md:529 citan `~/.claude/projects/C--Users-Pedro-Desktop-proycto/memory/`. La real es `~/.claude/projects/-var-home-pedro/memory/`.

### [linea] Los mojibake de calipso/server.py

**Por qué importa:** El docstring de cabecera del archivo mas grande del repo esta ilegible, y el plan que lo parkeo (2026-08-25-mapa-acoplamiento.md:29) ya esta mergeado, asi que la razon para diferirlo caduco.
**Evidencia:** calipso/server.py:3, 5, 6, 53, 88, 92, 103, 105, 328, 1166, 1169, 2192, 2566, 2568, 2601, 3909, 3915 — 17 lineas con doble mojeo UTF-8 (ÃƒÂ³, ÃƒÂ­, Ã¢â‚¬â€). Es el unico archivo del paquete afectado: `grep -rln 'Ã' calipso/**/*.py` devuelve solo server.py.

## servidor (1)

### [tarea] Falta el screenshot automatico del navegador por tipo de cambio visual en la verificacion fuerte *(parcial)*

**Por qué importa:** La mitad que existe (captura automatica) corre solo en el camino de propuestas; un cambio visual verificado por /api/verify/run pasa en verde sin que nadie haya mirado un pixel.
**Evidencia:** calipso/verification.py:44 clasifica frontend y solo agrega el comando `ui_syntax`, sin browser; pero calipso/server.py:721-731 SI dispara calipso_browser.before_after_capture automaticamente al aplicar una propuesta de UI (calipso/browser.py:66 is_ui_file)

## otro (18)

### [spec] CALIPSO.md promete conectores MCP y skills descargables

**Por qué importa:** La identidad promete una superficie de extension que no existe; y lo que si se construyo (plugins de Claude Code) no esta documentado en ningun handoff.
**Evidencia:** CALIPSO.md:178-179 ('MCP servers', 'Skills: paquetes descargables'). `grep -rniE '\bmcp\b'` sobre calipso/ y dispatch.py: cero. Lo que si existe es calipso/plugins.py (lee ~/.claude/plugins/installed_plugins.json y el catalogo) con server.py:2806,2813,2820 (/api/plugins, /catalog, /install), que AGENTS.md no menciona. CALIPSO.md:172 ademas sigue diciendo 'claude.cmd en Windows'.

### [spec] Capa de estilo (ASD-STE100 y anti-look-IA) que consume las horas de tuning reservadas

**Por qué importa:** Sin ella la fabrica puede producir texto que se lee como IA y no hay ninguna partida que lo controle, aunque el reloj ya reserve horas para calibrarlo.
**Evidencia:** docs/superpowers/specs/2026-08-24-cerebro-central-economia-monedas-design.md:206 lo declara fuera de alcance; grep -rniE 'ASD-STE|STE100|anti-look' sobre .py/.js/.html no devuelve una sola linea. El gancho economico si existe: calipso/economia/reloj.py:20 CATEGORIAS incluye 'tuning' y reloj.py:92-98 solo mueve PT para 'personal', nunca para 'tuning'.

### [spec] Capa de estilo (ASD-STE100 y anti-look-IA) — duplicado del item 1

**Por qué importa:** Es la unica partida de gasto de PT declarada sin contraparte en el libro: el presupuesto de tuning no tiene a quien cobrarle.
**Evidencia:** Mismo hallazgo que el item 1: spec :206 y docs/superpowers/plans/2026-08-25-economia-frontera.md:2084 la listan fuera de alcance; no hay modulo ni cuenta en calipso/economia/ (ls: 20 .py, ninguno de estilo).

### [spec] Hooks deterministas (post-save, pre-run, fallo CI, resumen diario)

**Por qué importa:** Nada puede reaccionar a un evento del sistema sin que Pedro lo pida a mano; y el diseno choca de frente con el runner allowlist de calipso/tools/commands.py, asi que necesita decidirse antes de codearse.
**Evidencia:** AGENTS.md:519-520. `grep -rniE '\bhook' --include=*.py` sobre el repo (excluyendo .venv) devuelve cero lineas: no hay calipso/hooks.py ni esqueleto en jobs.py.

### [spec] Puentes: Atlas/Observatory-Global en la zona personal y research-court como invitado de la fabrica

**Por qué importa:** Atlas y research-court son los dos consumidores reales que justifican la economia; sin billetera propia siguen gastando fuera del libro y el balance no refleja nada.
**Evidencia:** spec :209 y :181. El mecanismo esta: calipso/economia/departamentos.py:20 ZONA_PERSONAL y :49-52 cuenta 'personal:<nombre>'; calipso/economia/reloj.py:71-72 exige ref 'personal:<departamento>'. Lo concreto no: no hay ningun departamento sembrado (grep 'semilla|seed|inteligencia|market research' en calipso/economia/ y server.py: vacio), 'dep:atlas' solo aparece como fixture en test_mapa_pulso.py:7 y test_mapa_acoplamiento.py:20, y la nocion de 'invitado' no existe (grep invitado en calipso/: cero).

### [plan] Artifacts verificables (screenshots + walkthrough + resumen de pruebas unidos al plan ejecutado)

**Por qué importa:** No hay un solo entregable que pruebe que un plan se cumplio: las piezas (reporte, screenshots, artifacts, evidencia de meta) viven en cuatro lugares que nadie cose.
**Evidencia:** AGENTS.md:521-522 y LIBRARY.md:315. calipso/verification.py:104-157 run_plan() arma verification-report.{json,md} solo con command_id/status/returncode; grep 'browser|screenshot' sobre calipso/verification.py y calipso/jobs.py devuelve cero. El unico enlace hacia arriba es goals.add_evidence(..., goal_id) en verification.py:155, no el plan ejecutado.

### [plan] Bloque 'Rutinas/timers/inbox': hay rutinas y timers, no hay bandeja *(parcial)*

**Por qué importa:** Una rutina que corre y no deja nada revisable equivale a no correr: Pedro no tiene donde ver que produjo el reflect de anoche.
**Evidencia:** calipso/routines.py corre reflect/learn/backup con ticker (KINDS en :25), pero grep 'inbox|archiv|result' sobre calipso/routines.py devuelve cero: no hay bandeja de resultados ni auto-archivado (el /api/memory/inbox de calipso/librarian.py es la bandeja de propuestas de memoria, otra cosa). El doc se contradice: AGENTS.md:32-33 lo lista como bloque grande no empezado y AGENTS.md:196-201 como v0 hecho.

### [tarea] El 'Mapa del repo' omite todo lo construido desde junio

**Por qué importa:** El mapa es lo primero que lee un agente para ubicarse; hoy lo manda a un repo que no incluye ni la economia ni la fabrica.
**Evidencia:** AGENTS.md:379-444 (bloque text). Faltan calipso/economia/ (20 .py), calipso/mapa/ (6 .py), calipso/web/fabrica/ (24 archivos), calipso/plugins.py, calipso/resource_dispatcher.py, calipso/chats.py, calipso/attachments.py, calipso/backup.py, calipso/browser.py, DESIGN.md, LINUX_MIGRATION.md, docs/superpowers/{plans,specs}/, docs/research/, calipso.sh, Cargo.toml, src-tauri/.

### [tarea] La lista 'Verificado' omite 23 archivos de test que existen

**Por qué importa:** Un agente que corre 'lo verificado' de AGENTS.md deja sin ejecutar los tests de los dos subsistemas mas grandes del repo.
**Evidencia:** AGENTS.md:216-267 lista 17 comandos. Diff contra `ls test_*.py`: 23 archivos no se nombran en NINGUNA parte de AGENTS.md — test_economia_{kernel,libro,bus,pt,mercado,cierre,frontera,capacidad,eficiencia,pagador,server,simulacion}, test_mapa_{ciudad,urbanismo,acoplamiento,foco,pulso,server,ws}, test_fabrica_js, test_resource_dispatcher, test_seguridad_secretos, test_chat_live. Ninguno de los listados fue borrado.

### [tarea] Los cinco chequeos manuales de 'Endurecer lo ya construido' nunca se marcaron como hechos

**Por qué importa:** Tres botones de la UI de conectores fallan siempre en la maquina actual y nadie lo detecto porque el chequeo manual que lo habria visto nunca se corrio.
**Evidencia:** AGENTS.md:487-495, sin marca de hecho; AGENTS.md:216-267 solo reporta verificacion por test y mocks. El cuarto punto ('revisar que los controles visibles no sean placeholders') tiene tres incumplimientos concretos y verificados: calipso/server.py:1117 (/api/connectors/{name}/{action}), :1134 (/api/subscriptions/{client}/install) y :1154 (/api/subscriptions/{client}/login) pasan creationflags=subprocess.CREATE_NEW_CONSOLE, atributo que no existe en Linux — el except lo convierte en HTTP 500. El unico e2e real, test_chat_live.py, exige el server prendido y no esta en ninguna lista.

### [tarea] Sugerencias automaticas del bibliotecario desde sesiones completas *(parcial)*

**Por qué importa:** La memoria nunca aprende sola de una sesion completa: el endpoint existe pero nadie lo toca, asi que la promocion sigue siendo 100% manual.
**Evidencia:** Existe la mitad de abajo: calipso/librarian.py:195 suggest_from_text() y calipso/server.py:3024 POST /api/memory/inbox/suggest. Falta la de arriba: el unico llamador en todo el repo es test_librarian.py:44 — grep 'suggest' sobre calipso/web/ devuelve cero, y no hay disparador al cerrar sesion en calipso/sessions.py ni en el ticker de routines.py.

### [tarea] Vision multimodal (declarada faltante, ya hecha) vs permisos editables del agente (siguen faltando) *(parcial)*

**Por qué importa:** El agente ve el rango seleccionado como prosa, no como destino: no puede proponer una edicion dirigida a esas lineas, y AGENTS.md:182-183 sigue reportando mal cual de las dos mitades falta.
**Evidencia:** HECHO: calipso/attachments.py:23 _ANTHROPIC_VISION_MIMES, :224 has_images(), :232 ollama_vision_model(), :236 vision_describe(), enganchado en calipso/server.py:2351-2362. FALTA: el adjunto editable guarda source.path y selection (attachments.py:93-94, :156-164) pero solo se emiten como texto de cabecera en attachments.py:326-330; grep 'editable|selection' sobre calipso/orchestrator.py: cero, y calipso/developer.py solo usa 'editable' en :177,:230 para descartar binarios.

### [tarea] check_doc_links solo valida en una direccion (docs -> archivos), nunca archivos -> docs

**Por qué importa:** Es la razon mecanica de que el mapa quedara 129 commits atras con el verificador en verde; sin auditoria inversa el drift se repite solo.
**Evidencia:** calipso/doclinks.py:53 audit() recorre DOCS, extrae tokens entre backticks y solo comprueba `(root / token).exists()`; no hay recorrido inverso del repo. `.venv/bin/python check_doc_links.py` imprime 'refs internas revisadas: 81 / OK'. Ademas doclinks.py:19 DOCS = [SPEC, AGENTS, LIBRARY, RUNBOOK, CALIPSO] no incluye DESIGN.md ni docs/superpowers/.

### [linea] AGENTS.md se declara 'fuente de verdad del repo' y 'funcional de punta a punta'

**Por qué importa:** El proximo agente lee esa linea y asume Windows, sin economia y sin mapa; toma decisiones sobre un repo que ya no existe.
**Evidencia:** AGENTS.md:9. Contradicho por AGENTS.md:456 ('OS: Windows 11, PowerShell') contra LINUX_MIGRATION.md y calipso.sh; por AGENTS.md:379-444 (mapa sin economia/mapa/fabrica); y por calipso/server.py:1117,1134,1154 usando subprocess.CREATE_NEW_CONSOLE, atributo que no existe en Linux.

### [linea] El backlog declara pendientes dos cosas ya hechas (log de propuestas y rutina de /api/learn)

**Por qué importa:** Un agente que ataque el backlog reimplementa dos cosas que ya funcionan; es trabajo duplicado garantizado.
**Evidencia:** Las dos features estan hechas: calipso/librarian.py:174 _event(..., 'accepted', ...) y :190 _event(..., 'discarded', ...); calipso/routines.py:25 KINDS = ('reflect','learn','backup') con calipso/routines.py:30 interval_minutes 1440. Lo que sigue abierto es el texto: AGENTS.md:515-516 y LIBRARY.md:307-315 ('logging claro de aceptar/descartar propuestas', 'una rutina periodica de reflexion') siguen listandolas como falta.

### [linea] El checkpoint 'ultimo conocido' de AGENTS.md esta ~100 commits atras

**Por qué importa:** Cualquier comparacion 'contra el ultimo checkpoint' arranca 129 commits antes de la economia, el mapa y la fabrica.
**Evidencia:** AGENTS.md:16 dice '0577e70 Apply Tech Innovation theme to the UI'. El commit existe, pero `git rev-list --count 0577e70..HEAD` = 129 (no ~100), HEAD = 118d1fd, 158 commits totales.

### [linea] Las capas de memoria de AGENTS.md no incluyen DESIGN.md ni docs/superpowers/

**Por qué importa:** Ningun documento dice donde vive el diseno real de economia y mapa, asi que un agente nuevo no los encuentra y disena de nuevo lo ya decidido.
**Evidencia:** AGENTS.md:353-367 lista CALIPSO.md, AGENTS.md, LIBRARY.md, SPEC.md, core markdown, chroma y telemetria. `grep -rn 'DESIGN.md|superpowers' AGENTS.md LIBRARY.md CALIPSO.md SPEC.md` devuelve CERO resultados, pese a que DESIGN.md:3-4 se autodeclara autoridad visual y docs/superpowers/ tiene 2 specs + 6 planes. calipso/doclinks.py:19 tampoco los incluye en DOCS.

### [linea] Trabajo sin cerrar en el checkout: rama fix/secretos-en-0600 con index.html modificado sin commitear

**Por qué importa:** 51 lineas de UI sin commitear pueden ser trabajo en curso o basura de una prueba de Tauri; hasta que Pedro decida, cualquier merge o comparacion arrastra el ruido.
**Evidencia:** git branch --show-current = fix/secretos-en-0600, HEAD = 118d1fd. `git status --short`: ' M calipso/web/index.html' (+51/-4 lineas) y untracked Cargo.toml, Cargo.lock, src-tauri/. El aviso de AGENTS.md:13-15 sigue vigente y sigue siendo cierto. Nota lateral encontrada al verificar el item 17: test_chat_live.py:12 tiene un token de sesion hardcodeado en el repo.

## documentacion (1)

### [linea] AGENTS.md llama al tema de la UI 'Tech Innovation' pero index.html implementa la paleta ambar de DESIGN.md

**Por qué importa:** AGENTS.md es lo primero que lee una sesion nueva: nombrar un tema que ya no existe manda a inventar contra la paleta equivocada.
**Evidencia:** AGENTS.md:114 dice 'tema Tech Innovation'; calipso/web/index.html:19-38 define --void:#08090B, --amber:#F0A030, --frost:#5B8FA8 y Plus Jakarta Sans (index.html:15), exactamente DESIGN.md:23-43 y :58

## diseno (1)

### [spec] La fabrica ignora DESIGN.md: usa acento cyan, que el documento prohibe explicitamente

**Por qué importa:** DESIGN.md:4 se declara la unica fuente de toda decision visual y DESIGN.md:51 dice que los fondos son solo --void/--surface/--elevated: hoy Calipso tiene dos identidades visuales y ninguna esta declarada como excepcion, asi que la proxima sesion que toque UI no sabe cual respetar.
**Evidencia:** calipso/web/fabrica/estilo.css:3 `--fondo: #0b0f14` y :8 `--acento: #66d9ff`; calipso/web/fabrica/paleta.js:24 'la fabrica es acero frio'; DESIGN.md no menciona fabrica, mapa ni pixel art en sus 255 lineas


## Pedido de Pedro, 2026-08-27: revision de seguridad de Calipso

Pedro pidio "una nota aparte para hacer una revision de seguridad para calipso". Queda abierto como trabajo propio, no como parte del rediseno de proyectos/departamentos.

Lo que ya sabemos que entra en esa revision, para que no se pierda:
- El token en la URL: auth_guard acepta ?token= y uvicorn loguea el query string entero, asi que el token queda en texto plano en el log del server en cada request. Confirmado por observacion directa. La cascara Tauri (src-tauri/src/lib.rs, sin trackear) navega el webview a http://127.0.0.1:8000/?token={tok}, que es el mismo patron.
- El remedio conocido: POST del token a un endpoint que devuelva Set-Cookie, y navegar despues sin query string.
- La superficie nueva de la mesa (financiar y descartar) mueve plata y hereda el mismo auth_guard que el resto; conviene mirarla con ojos de seguridad ahora que existe.
- Los agentes contratados y sus herramientas: la unica ruta que hoy le da herramientas a un agente lo hace heredando el CLI entero sin restriccion (server.py:1944-1947), mientras que el repo YA tiene un runner con allowlist real en tools/commands.py:23 que no esta expuesto a ningun agente. O sea que un agente contratado por un departamento puede hacer lo mismo que la sesion que lo lanzo. Encontrado al mapear el modelo de skills el 2026-08-27.
- CSP debilitada en la cascara Tauri (src-tauri/tauri.conf.json): script-src lleva 'unsafe-inline' y 'unsafe-eval'. Marcado por revision automatica el 2026-08-27. El motivo probable de 'unsafe-eval' es el cargador AMD de Monaco; las versiones recientes ya no lo necesitan si se le configura trustedTypesPolicy. El arreglo recomendado: separar style-src (que si suele necesitar unsafe-inline) de script-src, y dejar script-src estricto en 'self' mas el origen local. No es explotable hoy porque la cascara nunca compilo, pero importa cuando compile: la UI ya renderiza SVG que escribe un modelo, y aunque la frontera de ese caso es un iframe con sandbox="" sin allow-scripts, una CSP con unsafe-eval le saca una capa a todo lo demas.
- Sobre el token en la URL de la cascara Tauri, que la misma revision volvio a marcar: el 2026-08-27 ya se roto el token y se saco el literal de la pagina de login (commit 4eba4eb), asi que el que quedo escrito en los access logs viejos esta muerto. Lo que sigue abierto es el patron: la cascara navega a http://127.0.0.1:8000/?token={tok}. Las tres salidas concretas son POSTear el token a un endpoint que devuelva Set-Cookie y navegar despues sin query, inyectar la cookie directo en el almacen del webview antes de la primera navegacion, o mandar el token en un header Authorization en un fetch de arranque desde about:blank. Y ademas configurar uvicorn para que no loguee query strings.

## CALIPSO_HOME congelado al importar, en quince modulos

Encontrado el 2026-08-27 persiguiendo tres tests del catastro que pasaban solos y fallaban dentro de la suite. La causa era que `CALIPSO_HOME` se resuelve UNA SOLA VEZ al importar el modulo, asi que monkeypatch sobre esa constante no cambia adonde escribe la funcion — y los tests terminaban escribiendo en el ~/.calipso REAL de Pedro. El sintoma visible fue el rojo; el problema de fondo es que la suite escribe en su casa.

En catastro.py quedo arreglado (commit f4779b0): CALIPSO_HOME paso de constante a una funcion calipso_home() que lee el entorno en cada llamada, y test_catastro_server.py corre en un subproceso limpio porque necesita el server entero. Verificado con md5 y mtime del archivo real, identicos despues de dos corridas completas de la suite.

Pero el patron sigue igual en QUINCE modulos mas: backup.py, attachments.py, config.py, chronology.py, discovery.py, librarian.py, chats.py, routines.py, capabilities.py, costs.py, jobs.py, goals.py, memory.py, telemetry.py y sessions.py. Cada uno es una puerta por la que un test puede escribir en el home real sin que nadie se entere — este se descubrio de casualidad, porque ademas rompio tres tests.

No se arreglo en el momento a proposito: son quince archivos, el arreglo de cada uno es chico pero hay que revisar sus llamadores, y merece su propia pasada con su revision. Lo que si conviene decidir antes de tocarlos es si el arreglo es funcion-por-modulo (como catastro) o una sola fuente compartida que todos consulten, porque hacerlo quince veces distinto seria peor que no hacerlo.
