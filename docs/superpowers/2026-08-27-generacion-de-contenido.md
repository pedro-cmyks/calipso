# Generación de contenido: qué instalar, qué pagar, en qué orden

**Fecha:** 2026-08-27
**Entrada:** cinco investigaciones (imágenes, vectores, 3D, video, sonido) más un
relevamiento del código de Calipso.
**Qué es:** la recomendación. Qué se hace esta semana, qué se difiere, y qué
todavía no está verificado.

---

## 1. La respuesta corta

Esta semana Pedro no instala nada que se pague y no contrata ninguna suscripción
nueva. Instala herramientas gratis y locales — `whisper.cpp` o `faster-whisper`
para transcribir, `Piper` o `Kokoro` para que Calipso hable, `mermaidx` +
`graphviz` + `d2` para diagramas, `vtracer` + `scour` para trazado y limpieza de
SVG — y prende dos capacidades que **ya tiene pagadas y no está usando**: el CLI
de Codex genera imágenes de forma nativa contra el plan de ChatGPT Plus, sin API
key y sin costo marginal, y el CLI de Claude escribe SVG a nivel de producción
para íconos, logos y diagramas. Total a pagar: **0 USD adicionales sobre los 220
que ya salen**. Lo único que conviene abrir con tarjeta, y no esta semana, es una
cuenta pay-as-you-go en **fal.ai** (sin cuota fija) como escape para volumen de
imágenes a ~0,003-0,005 USD cada una y para los clips de video que hagan falta,
con tope de gasto duro. Pero antes que cualquier modalidad hay un arreglo previo:
`~/.calipso/economia/` no existe, así que **hoy el libro contable no está
cobrando nada de nada** (`calipso/economia/pagador.py:58-66` devuelve `None`).
Generar contenido antes de prender el libro es gastar a ciegas.

---

## 2. Una tabla por modalidad

| Modalidad | Recomendada | Cómo se paga | Local o nube | Integrarla a Calipso |
|---|---|---|---|---|
| **Vectores (SVG)** | LLM escribe el SVG por CLI + loop de render; Iconify para íconos que ya existen; mermaidx / D2 / Graphviz para diagramas | SUSCRIPCIÓN (ya pagada) + HERRAMIENTA | nube ya pagada / local | **chico** — una función en el frontend |
| **Sonido: voz y transcripción** | `whisper.cpp`+Vulkan o `faster-whisper` para STT; `Piper` o `Kokoro` para TTS | HERRAMIENTA, gratis | local, CPU/iGPU | **chico** — ya funciona, falta registrarlo |
| **Imágenes** | Codex CLI (`$imagegen`, gpt-image-2) por defecto; fal.ai (FLUX schnell / Z-Image Turbo) como escape de volumen | SUSCRIPCIÓN; API 0,003-0,067 USD/img | nube | **mediano** — 5 cambios en 5 capas, uno en economía |
| **Sonido: música y efectos** | Freesound CC0 primero; Stable Audio Open Small local; ElevenLabs solo con entregable esperando | HERRAMIENTA; API/suscripción | local / nube | **mediano** — mismo problema de salida binaria |
| **3D** | Blender headless (`blender -b --python`) y CadQuery, con el script como artefacto primario; generación por modelo diferida | HERRAMIENTA + tokens de suscripción | local, CPU | **mediano**, o **chico** si se degrada a herramienta que escribe archivos |
| **Video** | Edición programática con ffmpeg (ya instalado) + MoviePy 2.x; generación por IA detrás de un tope de presupuesto | HERRAMIENTA; API 0,05-0,40 USD/s | local la edición, nube la generación | **rediseño** |

Precios de referencia por unidad, para tener la escala en la cabeza: una imagen
sale entre 0,003 (fal.ai FLUX schnell) y 0,21 USD (gpt-image-2 high); un SVG
vectorial de Recraft 0,08; un modelo 3D texturizado 0,20-0,40; una hora de
narración por API 0,75-5,00 y por local 0; una hora de transcripción 0,18-0,36
por API y 0 local; **un video de 90 segundos entre 4,50 y 36 USD**. Ese último
número es el 16% del gasto mensual de Pedro por minuto y medio de video.

---

## 3. Lo que Pedro ya paga y no está usando

De las cinco modalidades, **dos y media están cubiertas por los 220 USD que ya
salen**. El resto no está cubierto por nada.

**Imágenes, cubierto y desaprovechado.** El CLI de Codex trae generación de
imágenes nativa con gpt-image-2. La documentación oficial del repo de OpenAI
distingue explícitamente dos modos: el built-in `image_gen` que *"does not
require `OPENAI_API_KEY`"* y un fallback por script que sí la requiere. O sea:
mientras `OPENAI_API_KEY` **no** esté en el entorno del proceso de Codex, cada
imagen se paga contra el ChatGPT Plus que Pedro ya tiene. Costo marginal cero,
hasta 2K de resolución, hasta 10 imágenes por llamada, invocable sin interacción
con `codex exec -s workspace-write`. Calipso ya sabe hacer exactamente este
truco: limpia `ANTHROPIC_API_KEY` antes de invocar a Claude
(`calipso/server.py:2018-2021`, `dispatch.py:308-310`, `plugins.py:88-90`) para
forzar el cobro a la suscripción. Hay que hacer lo mismo con `OPENAI_API_KEY`
para Codex, y hacerlo antes de la primera llamada, no después.

**Vectores, cubierto y desaprovechado.** SVGBench mide hoy claude-opus-4.6 en
75,6% y gpt-5.2 en 74,4%: Pedro tiene la capacidad por partida doble, arriba de
todo, y ya pagada. La intuición vieja de que "los LLM dibujan mal" está muerta:
gpt-4o sacaba 31,8%. Para íconos, logos, badges, ilustración geométrica plana y
cualquier cosa con estructura, esto ya sirve para producción. El multiplicador
gratis es el loop de render: el modelo escribe SVG, Calipso lo rasteriza con el
Chromium de Playwright que ya instala como HERRAMIENTA, le devuelve el PNG, el
modelo corrige. Es el error típico (texto cortado por el viewBox) arreglado en
una iteración y en segundos.

**La media modalidad: orquestación.** En 3D y en video, la parte cara en tokens
—planificar, escribir el script de Blender o de CadQuery, mirar el render,
corregir— sale del Max de 200 y **no suma un peso**. Blender headless es
HERRAMIENTA, ffmpeg es HERRAMIENTA. El costo marginal de "video editado
programáticamente" y de "geometría por código" es cero. Ese es el mejor
arbitraje que aparece en toda la investigación, y es el argumento entero para
tratar la edición como el camino principal y la generación como condimento.

**Lo que las dos suscripciones NO dan, y hay que decirlo sin vueltas.** Video:
cero. Sora 2 y la Videos API entera se apagan el **24 de septiembre de 2026**
según la página oficial de deprecaciones de OpenAI, sin reemplazo listado; los
20 USD/mes de ChatGPT Plus no compran nada de video. Audio: cero, ni Claude ni
ChatGPT dan generación de audio programática. 3D generativo: cero, y no es un
descuido — **ninguna lab frontier vende generación 3D**, ni Anthropic, ni
OpenAI, ni Google. Música: cero. Toda esa columna es plata nueva o es local.

---

## 4. Gemini, contestado

**¿El CLI de Gemini genera imágenes?** No de fábrica. El paquete base da I/O de
archivos, shell, búsqueda web y código; no trae síntesis de imagen. Existe la
extensión oficial `gemini-cli-extensions/nanobanana`, que agrega `/generate`,
`/edit`, `/icon`, `/diagram` y demás, **pero exige la variable
`NANOBANANA_API_KEY` con una key de Google AI Studio**. La extensión es una
fachada de CLI sobre la API paga, no un canal de suscripción.

**¿Se paga por suscripción o por token?** Por token, y la suscripción no sirve.
La documentación de Google es explícita: los beneficios de los planes Google AI
*"apply only within the Google AI Studio web interface. Direct use of the Gemini
API […] is billed and managed separately."* Google AI Pro cuesta 19,99 USD/mes y
da Nano Banana dentro de AI Studio y de la app, no por API; no incluye créditos
de API, y la tabla de precios marca **"Not available"** en el free tier para
todos los modelos de imagen. La salida de imagen se factura a 60 USD por millón
de tokens en `gemini-3.1-flash-image`; una imagen de 1024×1024 son ~1120 tokens,
o sea **0,067 USD**.

**Qué significa para el libro de Calipso.** Tres cosas concretas. Primero: Gemini
para imágenes entra como forma **API**, no como SUSCRIPCIÓN — la creencia estaba
invertida, y estaba invertida en la dirección que le conviene a Pedro, porque la
opción por suscripción que sí existe (Codex) es la que no estaba usando.
Segundo, y es la buena noticia técnica: como Gemini factura **tokens**,
`cargar_api()` (`calipso/economia/pagador.py:148-160`) lo cobra tal cual, sin
cambiar el esquema; el único cambio es una entrada más en
`PRECIOS_API_MM_POR_MTOK` (`pagador.py:28`) **con la tarifa del modelo de
imagen, que es distinta de la de texto** — sin esa entrada, el fallback
`PRECIO_DESCONOCIDO` (`pagador.py:29`) cobra un número inventado. Gemini es la
única opción de imagen que no necesita el cargo por unidad. Tercero: no
construir nada sobre Imagen, que se apagó el 17 de agosto de 2026, hace diez
días, y facturaba plano por imagen; Nano Banana es tokens.

---

## 5. El orden que recomiendo

**Paso cero, antes de cualquier modalidad: prender el libro y agregarle una boca
por unidad.** `~/.calipso/economia/` no existe (verificado hoy), así que
`Pagador.desde_entorno()` devuelve `None` y `_cobrar_turno()`
(`server.py:4216-4253`) sale por la puerta de atrás. Hoy Calipso no cobra nada.
Y aunque estuviera prendido, `cargar_api()` solo habla tokens: si le pasás `0,
0` porque el proveedor no reportó usage, devuelve `0` sin generar cargo
(`pagador.py:154-157`). Traducido: **una imagen de cuatro centavos queda gratis
en el libro**. Casi ningún proveedor de imagen, 3D o video factura por token —
facturan por imagen, por megapíxel o por segundo. El arreglo es una sola
función: `cargar_api_por_unidad(ts, semana, cuenta, modelo, unidades,
mm_por_unidad)` que arme el mismo cargo `{"tipo":"api","mm":N}` que `_aplicar()`
ya consume (`pagador.py:129-131`) y que `Mercado.gastar_api()` ya sabe recibir en
milimonedas (`mercado.py:140`). Es la única pieza que las cuatro modalidades no
textuales necesitan por igual.

**Primera modalidad: vectores.** Por cuatro razones. Es la única que atraviesa
intacta toda la tubería existente, porque un SVG es texto: lo escribe `claude
-p`, lo lee `_run_subscription_text_live` (`server.py:2098-2106`), lo pasa
`_emit` (`dispatch.py:478`), lo guarda `chats.append` (`chats.py:101-106`) y se
cobra hoy como suscripción sin tocar el pagador. No necesita entrada nueva en el
REGISTRY: los modelos que ya están ruteados por `writing` y `code` dibujan SVG
bien. El cambio es **uno solo y es cosmético** — que `maybeRenderArtifact()`
(`web/index.html:1679-1708`) detecte `<svg` y lo renderice en vez de volcarlo en
un `<pre>` con `textContent`. Y es la modalidad cuyo producto Calipso más va a
consumir: íconos, diagramas y badges para su propia interfaz y para
Observatory-Global. Una tarde de trabajo, un archivo, cero dólares.

**Después, en este orden:** (2) **voz y transcripción**, que ya funcionan y solo
falta formalizarlas — `faster-whisper` se usa en `server.py:3405-3437` y **no
está en `deps.TOOLS`** (`deps.py:23-32`, que tiene una sola entrada), así que
hoy Calipso le tira a Pedro un mensaje de error pidiéndole que corra un `pip
install` a mano, que es exactamente el roadblock que `deps.py` existe para
evitar; el patrón a copiar es el `is_ready` especial de `browser`
(`deps.py:43-59`), porque para modelos con pesos el import no alcanza como
prueba. (3) **Imágenes por Codex**, que es el primer cambio estructural real
pero con todas las piezas ya en la casa: entrada de imagen resuelta
(`attachments.py:200-254`), almacenamiento de bytes resuelto
(`attachments.py:74-78`, `jobs.py:126-129`), servir un PNG por HTTP resuelto
(`server.py:2890-2900`). Falta un `type="image"` en `VALID_TYPES`
(`dispatch.py:140-141`) sin el cual `score_model` nunca puede elegir un backend
de imagen, un GET que sirva bytes de adjunto (hoy `server.py:524-532` devuelve
`content` vacío), el `content_type` correcto en artifacts (`server.py:3333-3338`
sirve PNGs como `text/plain`), un campo de adjunto en el mensaje de chat, y el
cargo por unidad. Cinco cambios chicos en cinco capas: semanas, no tardes. (4)
**música y efectos**, cuando aparezca un entregable. (5) **3D**, como
herramienta que escribe archivos. (6) **video**, cuando exista el productor
asincrónico.

---

## 6. Lo que no recomiendo hacer todavía

**3D generativo: no está maduro, y no es una cuestión de esperar la próxima
versión.** El survey de 2026 sobre assets 3D listos para producción lo dice sin
vueltas: *"a persistent gap separates the outputs of current methods from the
production-ready standard"*, y enumera topología, UV, materiales PBR, rigging y
layout. Lo que sale son 40.000-80.000 triángulos sin edge flow, con caras
superpuestas: se ve bien girando en pantalla y se rompe apenas lo tocás. Cinco
razones para no entrar: es la única modalidad donde el hardware de Pedro no
participa en absoluto (es CUDA o nada, y no es "instalá torch para ROCm" sino
portar kernels custom); es la única cuyo output no es consumible tal cual —una
imagen se mira, un audio se escucha, una malla necesita retopo antes de servir
para algo; es la única sin proveedor frontier, o sea otra cuenta y otra tarjeta
sin aprovechar nada de lo ya pagado; y **no está claro quién consume el
output** — Pedro no tiene un juego ni un motor ni un pipeline 3D, y un GLB
precioso sin destino es un archivo en una carpeta. Lo que sí salvo es el
sub-camino **código → geometría**: Blender headless y CadQuery son maduros,
deterministas y de costo hundido, pero eso no es "generación 3D por IA", es
automatización 3D por agente, y ahí Calipso está bien parado.

**Generación de video como base: no.** La economía es brutalmente asimétrica:
editar cuesta cero marginal y permite cuarenta iteraciones a las tres de la
mañana; 90 segundos con Veo Standard son 36 USD, y si no te gustó son 36 otra
vez. Además los modelos no producen videos, producen **clips** de 5 a 10
segundos: aunque generes todo con IA, igual tenés que editar. La edición no es
un camino alternativo, es la etapa final obligatoria de los dos caminos.

**Ninguna suscripción nueva.** Ni ElevenLabs Creator (22 USD), ni Meshy Pro (20),
ni Recraft Basic (12). Cada una es capacidad fija sin demanda demostrada, que es
exactamente el tipo de gasto que el libro de Calipso existe para evitar.
ElevenLabs es la única que defendería, porque un solo plan cubre voz expresiva,
clonado, música con licencia comercial defendible y efectos por un mismo SDK —
pero **solo cuando haya un entregable concreto esperándola**, no antes.

**Generación de imágenes local en la Ally: no todavía.** Verifiqué el hardware
hoy: **11 GB de RAM totales, 6 disponibles**, compartidos entre CPU e iGPU.
ROCm no soporta oficialmente gfx1103 (el workaround `HSA_OVERRIDE_GFX_VERSION`
es terreno no soportado), Bazzite es inmutable así que hay que contenerizar, y
Ollama agregó generación de imágenes en enero de 2026 pero **solo en macOS**.
Aun funcionando: 1 a 3 minutos por imagen, comiendo 6-8 GB que compiten
directamente con qwen2.5-7b y bge-m3. Con Codex generando gratis y fal.ai a
medio centavo, esto no se justifica. Si algún día se hace, el camino de menor
fricción es `stable-diffusion.cpp` con backend **Vulkan**, que evita ROCm entero.

**Suno por wrappers de terceros: no.** Suno no tiene API pública para
desarrolladores en 2026. Todo lo que se vende como "Suno API" son terceros que
mantienen pools de cuentas y las operan por detrás. Si Pedro publica algo
generado así, la cadena de derechos no existe. Igual con **MusicGen**: los pesos
son CC BY-NC 4.0, usar la salida comercialmente viola la licencia **aunque lo
corras en tu propia máquina**.

**OpenCut: al radar, no al stack.** Se está reescribiendo desde cero, no acepta
contribuciones externas, y lo que Calipso necesitaría —Editor API, MCP server,
headless mode— está prometido y no existe. La versión usable está archivada.
Revisar en seis meses.

**OpenMontage: sí, pero como proceso separado.** Es lo más accionable que
apareció en video —arquitectura agent-first, con `estimate_cost()` antes de
gastar y un `CostTracker` con reserva y reconciliación que calca la lógica del
libro de Calipso— pero es **AGPL-3.0**, y Calipso es un servidor FastAPI que
sirve por red. Importar sus módulos dentro del proceso de Calipso
(`from tools.tool_registry import registry`) mete a todo Calipso bajo el
copyleft. Invocarlo por subprocess como HERRAMIENTA, igual que se hace con
`browser`, mantiene el límite limpio. Es una decisión de arquitectura, no de
estilo.

**Y tres cosas sobre las que directamente no construir:** Imagen de Google
(apagado el 17-ago-2026), Sora y la Videos API (se apagan el 24-sep-2026), y
`ffmpeg-python` en Python — tiene 11k estrellas, es el resultado obvio de
googlear, y **no tiene release desde 2019**. Usar `subprocess` a ffmpeg
directo, MoviePy 2.x para timeline, PyAV para frames.

---

## 7. Lo que quedó sin verificar

Antes de gastar plata o de escribir el pipeline, confirmar esto:

**Bloqueantes de la recomendación principal.** (a) Los límites reales del
`$imagegen` de Codex: la fuente de que un turno con imagen consume el plan 3-5x
más rápido y de que hay un tope de ~250 img/min es de terceros, no de
documentación de OpenAI. Si el límite es agresivo, la opción por defecto cambia.
(b) Que el uso programático y por lotes de `image_gen` contra la suscripción sea
compatible con los términos de OpenAI — construir un pipeline de volumen sobre
una capacidad pensada para uso interactivo es un riesgo de cuenta, no solo de
cuota. (c) Comprobar en la máquina que `OPENAI_API_KEY` no esté exportada al
entorno de Codex, y forzar su limpieza en el código antes de la primera llamada;
si está seteada, cada imagen sale plata sin que nadie se entere.

**Hardware.** La RAM: dos investigadores dijeron 16 GB por specs, la máquina
reporta **11 GB totales**. Confirmar si es Ally o Ally X y cuánto reserva el
BIOS para la iGPU, porque de eso depende todo lo local. Y verificar que
`whisper.cpp` con Vulkan corra efectivamente en la 780M bajo Bazzite: los
reportes de la mejora de 12x son sobre una **680M**, la generación anterior.

**Precios de fuentes secundarias, no primarias.** Lyria 3 a 0,04-0,08 USD por
clip. El plan Basic de Recraft a 12 USD por 1000 créditos. El precio unitario de
Vectorizer.AI. Runway Gen-4 Turbo a ~0,05 USD/s con mínimo de carga de 10 USD.
Seedance 2.5 a ~0,14 USD/s, que además factura por tokens de completion y no por
segundo fijo. Y el retiro de gpt-image-1 el 23-oct-2026.

**Licencias.** La ficha específica de cada modelo de Voxtral en Hugging Face
—los de comprensión salieron Apache 2.0 y el TTS sería CC BY-NC 4.0, y las
fuentes las mezclan. Que Potrace es GPL, si alguna vez se distribuye algo.

**Datos que cambian un caso de uso entero.** Si Pedro tiene acceso a una
impresora 3D: de eso depende el único caso 3D que se justifica por sí solo
(soportes, adaptadores, un dock para la Ally, por CadQuery a 3MF y STL, costo
cero). Si no la tiene, ese caso no existe y 3D se difiere entero. También: qué
versión de Blender hay en Bazzite, y si ya salieron los pesos abiertos de
Hunyuan3D 3.0.

**Una trampa concreta ya verificada, para que no cueste un día de debugging:**
`vtracer` 0.6.15 en **Python 3.14 hace segfault ante cualquier argumento por
palabra clave**. La máquina de Pedro corre 3.14.3. El adaptador debe usar solo
argumentos posicionales, o aislar la llamada en un subproceso.

**Y un dato de calidad que no es un bug pero se le parece:** en Text2CAD-Bench,
los modelos generan código CadQuery que corre sin error y produce la pieza
equivocada — *"models may generate executable code with poor geometric
fidelity"*. La tasa de código inválido en nivel 3 va del 12,8% al 70% según el
modelo. La conclusión de diseño vale para las cinco modalidades y es la más
importante del informe: **el benchmark mide one-shot, y un agente no tiene por
qué serlo**. Sin loop de verificación —generar, renderizar, mirar, corregir—
Calipso está esculpiendo a ciegas. Con el loop, la cosa cambia de naturaleza.
Vale igual para el SVG, para el script de Blender, para el render de video y
para el prompt de imagen.

---

## Verificado a mano el 2026-08-27, no repetido de la investigacion

**Codex genera imagenes contra la suscripcion que Pedro ya paga.** Probado tres veces con `codex exec` desde un subproceso, que es exactamente como Calipso lo invoca:
- Generar: PNG de 1254x1254 de un edificio isometrico en pixel art. 19.622 tokens del plan Plus, costo hundido.
- Transparencia: PNG RGBA con alfa 0 en las esquinas. Ojo con el detalle, que cambia el diseno: el modelo NO hace transparencia nativa — Codex la resolvio recortando el fondo despues. O sea que no es "un backend de imagen", es un agente con manos que ademas dibuja.
- Editar: le pedi una variacion de la imagen anterior y mantuvo la geometria, el equipo del techo y la escalera, cambiando solo las ventanas y sumando el neon. Dijo que uso la original como referencia visual y lo confirme mirando las dos.

**El SVG anda de punta a punta.** Le pedi un logo por el chat y lo dibujo: 747 caracteres, renderizado en la pantalla. La frontera de seguridad es un iframe con sandbox="" sin allow-scripts, verificada con Chromium probando el ataque CON y SIN el saneado — o sea que la frontera aguanta sola y el regex es higiene encima.

**Gemini: el camino de suscripcion esta cerrado.** Google apago el CLI de Gemini para individuos el 18 de junio de 2026, sin periodo de gracia; solo siguen las licencias Standard y Enterprise de organizaciones. El reemplazo es Antigravity CLI (agy), con tier gratis y modo headless `agy -p --output-format json`, pero el paquete npm que la documentacion sugiere da 404: falta encontrar la via real de instalacion.

**Los sprites del mapa NO se reemplazan ni se texturizan.** Me equivoque dos veces proponiendolo y lo corrijo aca. Son de 16 pixeles de ancho y un edificio de nueve pisos mide 42 de alto: no hay donde poner una textura. Y cada pixel es un INDICE A LA PALETA, no un color, por eso `pintar` recibe una rampa y el mismo sprite se pinta distinto segun zona y estado. Ademas la altura sale del saldo, las ventanas encendidas de la actividad, y el patron de ventanas de un FNV-1a del id, explicitamente estable entre corridas. Un PNG generado no puede hacer nada de eso, pesa 1,1 MB contra unas lineas de codigo, y rompe los tests que dibujan y comparan. Lo que al mapa le falta es composicion, no arte.
