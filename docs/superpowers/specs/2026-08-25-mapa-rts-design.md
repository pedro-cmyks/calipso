# El mapa RTS — la consola de la fábrica

Fecha: 2026-08-25
Estado: diseño aprobado en conversación (con companion visual); pendiente de revisión de Pedro sobre este documento.

## 1. Propósito

Darle a Calipso una consola donde Pedro vea y opere la fábrica: una ciudad en pixel art con perspectiva forzada, generada por código desde el libro contable, con la conversación siempre al lado. Se le habla a Calipso —nunca a un departamento suelto— y lo que se dice mueve la cámara; lo que se toca en el mapa contextualiza a Calipso. Desde ahí se hace oversight de la operación: quién gasta, quién vende, quién quebró, qué agentes están trabajando ahora mismo y en qué están pensando.

El mapa no es una vista más de la UI existente: es la superficie principal de uso diario, en el escritorio y en el teléfono. La UI actual (`calipso/web/index.html`, un IDE con editor Monaco) queda como está y no se toca.

## 2. Invariantes

Reglas que viven en código, no en la intención.

1. **La ciudad se deriva, nunca se guarda.** No existe un archivo con posiciones ni tamaños de edificios. Todo sale de plegar el libro y los archivos de estado que ya existen. Borrar el mapa y regenerarlo da el mismo mapa.
2. **Mismo libro, misma ciudad.** La derivación y el urbanismo son funciones puras y determinísticas: sin reloj del sistema, sin RNG sin semilla, sin orden de diccionario. El Ally, el Mac y el iPhone ven exactamente la misma ciudad.
3. **El servidor manda un modelo, no un dibujo.** El servidor dice "atlas es un edificio de tamaño 7, sano, en (140, 45), con una calle de peso 3 hacia mercado". Cómo se pinta eso es decisión exclusiva del cliente. Cambiar toda la estética no toca una línea de Python.
4. **El mapa nunca escribe en el libro por su cuenta.** Es un lector. Las únicas escrituras que origina son las acciones explícitas de Pedro (mover una perilla, firmar o rechazar una compuerta, fichar), y todas pasan por los endpoints de economía que ya existen, con su candado.
5. **La capa viva es efímera y no es fuente de verdad.** El pulso vive en memoria, se pierde al reiniciar y jamás contradice al libro: si el pulso dice que un agente gastó y el libro no lo tiene asentado, manda el libro.
6. **Cero archivos de imagen.** Los sprites se dibujan por código desde una paleta. Un departamento nuevo aparece dibujado sin que nadie haya hecho arte.
7. **La conversación es siempre con Calipso.** El departamento es un objetivo del cerebro (contexto y pagador), no otro interlocutor. Tocar un empleado abre su razonamiento en modo lectura, no un chat con él.
8. **Un departamento no tiene plantel fijo.** Decide qué agente necesita para cada cosa, lo asigna y lo libera. El mapa muestra esa decisión; no la impone.

## 3. El modelo de ciudad

Una función pura `ciudad(asientos, registro, bus, cola, semana, minutos_empleo=0, suscripciones=None) -> dict`. `suscripciones` es opcional porque el mapa tiene que poder derivarse sin ese estado: sin él no hay costo API equivalente y entonces `eficiencia_pormil` va en `null` — un campo nulo declarado, nunca ausente. El endpoint sí lo alcanza (`mercado_fresco().suscripciones`) y lo pasa. Estructura:

```
{
  "semana": "2026-W35",
  "tesoro_mm": 1148000,
  "cuenta_pedro_mm": 5000,
  "direccion_mm": 0,
  "tipo_cambio_mm": 5000,
  "linea_empleo_mm": 14450,
  "edificios": [ ... ],
  "calles":    [ ... ],
  "unidades":  [ ... ],
  "avisos":    [ ... ]
}
```

**Edificio** (uno por departamento registrado, más la casa de Pedro):

| campo | derivación |
|---|---|
| `id`, `nombre`, `zona` | del registro (`dep:*` / `personal:*`; la casa es `cuenta_pedro`) |
| `tamano` (1-9) | escala logarítmica del saldo (fórmula abajo) |
| `estado` | `activo` \| `congelado` (quiebra declarada sin rescate). No existe `cerrado`: liquidar no deja marca distinguible en el libro, asi que no es derivable |
| `saldo_mm` | de `balances.saldos` |
| `gasto_ciclo_mm` | todo lo que SALIÓ de la cuenta en las semanas operativas del ciclo en curso (destrucción, transferencia y ejecución de reserva). Mismo criterio de salida que `bus.gastado`, para que dos lecturas del mismo libro no discrepen sobre qué es gasto |
| `ventas_ventana_mm` | acuñaciones de subtipo `venta` con destino el departamento, dentro del lapso de la ventana. El capital no es venta: no lo firma el mercado |
| `eficiencia_pormil` | `eficiencia.eficiencia_departamento` sobre las ocho semanas operativas de la ventana, o `null` si no se pasó el estado de suscripciones |
| `actividad` (0-3) | señal de vida barata, derivada del libro: cuántos de los últimos 3 días tuvieron gasto de ese departamento |
| `trabajos` | ids de los trabajos vivos cuyo dueño es el departamento (del bus) |
| `compuertas` | cuántas compuertas suyas están pendientes (de la cola) |

**Fórmula del tamaño**, explícita para que sea reproducible y monótona:
`tamano = min(9, 1 + digitos(max(0, saldo_mm) // 1000))`, con `digitos(0) = 0`. Saldo cero da 1; una moneda da 2; cincuenta monedas dan 3; mil monedas dan 5; un millón dan 8. Crece rápido al principio y lento después, que es como se lee bien en pantalla y evita que un departamento rico tape a los demás.

**Calle** (una por par de departamentos con comercio en la ventana de 8 semanas):

| campo | derivación |
|---|---|
| `a`, `b` | los dos extremos, ordenados alfabéticamente para que el par sea estable |
| `peso_mm` | suma de las transferencias internas directas entre ambos en la ventana: servicios vendidos y financiación de propuestas. La compra de capacidad no cuenta, porque su destino es dirección y no el otro departamento. La ventana es el **lapso** entre la primera y la última de las ocho semanas operativas, no la pertenencia al conjunto de sus etiquetas: una venta no desaparece de la ventana solo porque su semana no tuvo emisión de PT, igual que en `pt.tipo_de_cambio` |
| `ancho` (1-4) | bucket del peso: `<10k`→1, `<100k`→2, `<1M`→3, resto→4 |
| `tipo` | `cable` si los extremos están en zonas distintas (fábrica ↔ personal), `calle` si comparten zona |

**Unidad**: un trabajo vivo, con `id`, `dueno`, `gastado_mm` y `hacia` — el departamento que más cofinanció el trabajo sin ser su dueño, o `null` si no hay ninguno. La unidad camina por esa calle, así que **`hacia` solo puede nombrar a un cofinanciador que tenga calle en el modelo**: los aportes se leen del libro entero pero las calles son de la ventana, y un trabajo de larga vida puede tener toda su financiación ya fuera de ventana. Sin `hacia`, la unidad orbita el edificio de su dueño.

**Aviso**: una compuerta o carta pendiente, con `id`, `sobre` (el edificio), `tipo` y `monedas_en_juego_mm` para que el cliente ordene por importancia.

## 4. Urbanismo: la física de afinidad

Función pura `urbanizar(edificios, calles) -> dict[id, (x, y)]`, por **colocación incremental por antigüedad**. No es una relajación global: una relajación global no tiene memoria, resuelve la ciudad entera desde cero en cada request, y cuando nace un departamento encuentra un mínimo distinto y se corren todos. El anclaje por inercia según la antigüedad era un proxy débil de "la ciudad no se reacomoda" — empuja en la dirección correcta pero no lo garantiza, y ninguna constante lo logra.

El algoritmo:

- Los edificios se ordenan por `orden` (primera aparición en el libro), desempatando por `id`. El primero va al origen y no se mueve nunca.
- El edificio k se coloca relajando **solo a él** contra los k−1 anteriores, que quedan **congelados** en las posiciones ya calculadas. Cuando termina, se congela también y sigue el k+1.
- Nace justo afuera del borde de la ciudad de ese momento (`borde + RADIO_INICIAL`), en el ángulo que le da el SHA-256 de su nombre.

Sobre el que se coloca actúan tres fuerzas, todas par a par contra los ya colocados:

- **Repulsión**: inversamente proporcional al cuadrado de la distancia, para que nadie se encime.
- **Pertenencia y separación de zona**: un resorte hacia cada edificio de su misma zona, con reposo corto (`REPOSO_ZONA`), y un resorte contra cada uno de las otras zonas, con reposo largo (`SEPARACION_ZONAS`). Son las dos caras de la misma regla y no hay ningún cálculo de centroide: el barrio personal emerge de las fuerzas entre pares. Ya **no** hay compuerta `multizona`: el resorte de pertenencia actúa siempre, porque es lo único que ata a la ciudad cuando hay una sola zona.
- **Resortes de calle**: cada calle que toca al edificio tira de él, con longitud de reposo inversamente proporcional al peso — cuanto más comercian, más cerca quedan.

Todos los resortes son atractivos más allá de su reposo, así que un edificio suelto siempre tiene equilibrio y la relajación converge: no hay un mínimo global inestable del que depender.

Lo que esto compra: cuando nace un departamento se agrega al final del orden y las posiciones de todos los que ya estaban salen **bit a bit idénticas**. El corrimiento es cero **por construcción**, no por tuneo, y la ciudad crece hacia afuera de verdad.

Lo que esto cuesta, aceptado a propósito: **un edificio viejo ya no se acerca a un socio comercial nuevo**, porque no se mueve más. Una calle nueva entre un edificio viejo y uno nuevo tira solo del nuevo. Es exactamente lo que significa crecimiento anclado.

- **Determinismo**: ángulo inicial del SHA-256 del nombre (nunca `hash()` de Python, que varía entre procesos), número fijo de iteraciones por edificio, paso fijo, todo recorrido ordenado. Coordenadas redondeadas a enteros al final.
- **Costo**: O(N²) relajaciones con N en decenas. Medido: 8 ms con 16 edificios, 42 ms con 36, 162 ms con 71.

Constantes reales del módulo (`calipso/mapa/urbanismo.py`): `K_REPULSION=150_000.0`, `K_RESORTE=0.030`, `PASO=0.55`, `AMORTIGUACION=0.6`, `SEPARACION_ZONAS=900.0` (retunada desde 9.000, que dejaba el barrio personal a nueve o diez veces el diámetro de toda la fábrica: una isla, no un barrio), `K_SEPARACION=0.15`, `K_ZONA=0.15`, `REPOSO_ZONA=150.0`, `RADIO_INICIAL=120.0` (ahora es cuánto más afuera del borde nace un edificio, no un radio absoluto que crecía con el índice), `ITERACIONES=300` **por edificio**, `REPOSO=(0.0, 260.0, 190.0, 130.0, 80.0)` indexado por ancho de calle 1-4. La masa es `1 + tamano`: el bono de inercia por antigüedad desapareció porque el anclaje ya no depende de él.

El cliente **anima la transición** entre dos layouts consecutivos: la ciudad se reacomoda a la vista en vez de teletransportarse.

## 5. El pulso: la capa viva

Un anillo de eventos en memoria (`pulso`) donde cada agente que corre publica lo que hace. Ningún dato del pulso se persiste. Nada que ver con `bus.py` de la economía, que lleva las propuestas: para evitar confusión, este módulo se llama siempre "el pulso" y nunca "el bus".

**Evento**: `{ts, agente_id, departamento, trabajo, rol, modelo, evento, ...}` con `evento` en:

- `inicio` — el departamento asignó este agente (incluye `rol` y `modelo`)
- `razonando` — un trozo del razonamiento en curso (texto incremental)
- `herramienta` — usó una herramienta (`nombre`, `resumen`)
- `tokens` — acumulado (`tokens_in`, `tokens_out`, `costo_mm`)
- `diff` — dejó un cambio (`ruta`, `diff` unificado)
- `fin` — terminó o fue liberado (`runtime_ms`, `resultado`)

**Estructura**: un anillo por agente con los últimos N eventos (N = 200) y un anillo global de agentes recientes (M = 50). Un agente sin eventos por más de 10 minutos se marca inactivo y su escritorio queda vacío en el mapa.

**Vista derivada** `empleados(departamento)`: para cada agente vivo o recién liberado — rol, modelo, estado (razonando / esperando / liberado), runtime acumulado, tokens y costo, y el último diff. Es exactamente lo que llena el popup del empleado.

**Instrumentación**: los puntos donde hoy se lanzan agentes (`calipso/orchestrator.py`, el chat de `server.py`, `dispatch.py`) publican al bus. Se hace con un envoltorio (`with pulso.agente(...) as p:` y `p.razonando(...)`) para que agregar un punto nuevo sea una línea, no una refactorización.

## 6. Los dos canales

- **`GET /api/mapa/ciudad`** — la foto: el modelo completo con coordenadas ya calculadas. Se pide al abrir y después de cada cierre semanal o acción que mueva plata. Lector, bajo el candado del libro (invariante del Plan 3).
- **`WS /ws/mapa`** — el pulso: eventos de agentes en vivo, más un `foco` cuando Calipso decide mirar a un departamento. Reconecta solo; si se cae, el mapa sigue mostrando la foto (degradación limpia).

Ambos detrás del `auth_guard` que ya existe. Si la economía no está activa, `ciudad` responde `{"activa": false}` y el cliente muestra una pantalla de "todavía no hay fábrica".

## 7. El cliente

Vive en **`calipso/web/fabrica/`**, servido en **`/fabrica`**, como app propia — *no* dentro de `index.html`, que ya tiene 2.635 líneas y es un IDE con Monaco que no sirve en el teléfono. Archivos separados por responsabilidad (`ciudad.js` el modelo, `sprites.js` el dibujo, `camara.js` la navegación, `paneles.js` el layout, `pulso.js` el WebSocket), nunca un archivo único.

**Render.** Canvas 2D, pixel art con perspectiva forzada: cada edificio se dibuja con cara frontal, cara lateral oscurecida y techo aclarado, con el volumen horneado en el sprite (no tiles isométricos). El sprite se compone por código a partir del modelo: la altura sale del `tamano`, las ventanas prendidas de la `actividad`, las grietas y el apagado del `estado`, el color de la `zona`. Escala entera para que el pixel no se deforme.

**Cámara.** Paneo libre en los dos ejes (arrastre con mouse o dedo), zoom (rueda o pinza), y `volarA(edificio)` con easing para el foco. Tres niveles: ciudad (todo), barrio (un departamento y sus vecinos), interior (adentro del edificio). El "entrar" es un acercamiento continuo, no un cambio de pantalla: al pasar el umbral el techo se desvanece y aparece el interior.

**Paneles.** Tres columnas: chats, conversación, mapa (un tercio). El mapa se expande a pantalla completa con un botón para sobrevolar. Las compuertas pendientes se muestran siempre, sobre el mapa y en una barra fija.

**Teléfono.** Dos pestañas (chat y mapa) con la barra de compuertas visible en ambas. Misma app, mismo código; lo que cambia es cuántos paneles entran. Se instala como PWA con el `manifest.json` y el `sw.js` que ya existen.

**Hover / toque sobre un edificio**: tarjeta con saldo, gasto del ciclo, ventas de la ventana, eficiencia, trabajos vivos y compuertas pendientes — sin entrar.

## 8. El acoplamiento

Las tres direcciones, todas obligatorias:

- **Chat → mapa.** Cuando la conversación pasa a tratar de un departamento, Calipso emite una marca de control `⟦foco:atlas⟧` que el servidor **retira del texto visible** y reenvía como evento `foco` por `/ws/mapa`. La cámara vuela. La instrucción de emitirla vive en el compilador de prompts que ya existe.
- **Mapa → chat.** Tocar un edificio fija el departamento como contexto de la conversación: Calipso recibe su ficha (misión, saldo, trabajos, gasto, compuertas) y **su billetera pasa a pagar** lo que se consuma, vía la cuenta pagadora que el pagador del Plan 3 ya sabe cobrar.
- **Mapa → panel central.** Tocar un empleado convierte el panel del medio en su razonamiento en vivo: el stream del pulso, con runtime, tokens y el diff que dejó. Es lectura, no conversación; un botón vuelve al chat con Calipso.

## 9. Entrar a un departamento

Al cruzar el umbral de zoom, el techo se desvanece y se ve el interior: un escritorio por empleado que el departamento tiene asignado ahora. Cada uno muestra su rol y su estado (razonando, esperando, liberado). El escritorio de un agente liberado queda vacío con su rastro, porque ver que el departamento *soltó* gente es tan informativo como verlo contratar.

El popup de un empleado trae: rol, modelo que está usando, runtime acumulado, tokens de entrada y salida con su costo en monedas, y el diff de lo que tocó. Tocarlo lleva su razonamiento al panel central.

## 10. Integración con lo existente

- `calipso/server.py`: se suman los dos endpoints y la ruta `/fabrica`, en su propia sección, con el patrón de los endpoints de economía (estado fresco por request, candado en lo que escribe).
- `calipso/orchestrator.py` y el chat: se instrumentan para publicar al pulso. Sin cambio de comportamiento.
- `calipso/economia/*`: se consume tal cual, sin tocarlo. La ciudad es un lector más.
- `dispatch.py`: ya cobra por cuenta pagadora; el mapa solo elige qué cuenta según el departamento en foco.
- La UI vieja (`/`) sigue existiendo sin cambios.

## 11. Fuera de alcance

Sonido; edición manual del mapa (mover edificios a mano contradice la invariante 1); multi-usuario o espectadores; animación de agentes caminando dentro del interior; historial reproducible del mapa ("ver la ciudad de hace tres semanas"); y todo lo que la sección 12 del spec de la economía ya difiere (mezcla multi-proveedor, capa de estilo, conectores externos).

## 12. Verificación

- **Determinismo**, la propiedad central: el mismo libro produce el mismo modelo y las mismas coordenadas, en el mismo proceso y en procesos distintos. Test con dos derivaciones independientes y comparación exacta.
- **Estabilidad del urbanismo**: agregar un departamento nuevo deja a todos los existentes en **exactamente** las mismas coordenadas; el más viejo no se mueve nunca. Se verifica sobre modelos que `ciudad()` emite de verdad, no sobre diccionarios escritos a mano.
- **Barrio legible**: la separación mínima entre zonas supera la distancia media entre edificios de la misma zona, los personales están más cerca entre sí que de la fábrica, y ningún par de edificios queda a menos de 20.
- **Derivación**: cada campo del modelo se testea contra un libro sintético (tamaño por saldo, estado congelado, calles por comercio real, avisos por compuertas pendientes, actividad por gasto reciente).
- **Pulso**: los anillos no crecen sin límite; un agente inactivo se marca; los eventos salen en orden; el bus no persiste nada.
- **Frontera**: los endpoints responden `{"activa": false}` sin economía; el WS reconecta; el mapa sobrevive a que el pulso se caiga.
- **Cliente**: test del generador de sprites (mismo modelo, mismo bitmap) y de la cámara (volarA converge). El render fino se valida a ojo, no con tests.

## 13. Criterios de éxito

- Pedro abre `/fabrica` en el teléfono y en treinta segundos sabe si la fábrica está bien o mal, sin leer un número.
- Decir "miremos a Atlas" mueve la cámara y contextualiza a Calipso, y lo que se gaste ahí lo paga Atlas.
- Se puede ver a un agente razonando mientras razona, con su costo corriendo.
- Ninguna compuerta pendiente pasa desapercibida.
- La forma de la ciudad cuenta algo que los números sueltos no contaban: quién trabaja con quién.
