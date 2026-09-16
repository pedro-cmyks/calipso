# Calipso: donde estamos y adonde vamos (2026-09-16)

Reemplaza como punto de entrada al documento del 2026-09-15, que sigue valiendo como estado del despliegue
y de los subproyectos. Este cuenta una sola sesion, pero fue larga y movio cosas de fondo: el proposito
declarado de Calipso, la cosmologia de la fabrica, el archivista, y siete de las ocho decisiones de las
manos.

## 1. Lo que Pedro dijo, y que cambia el orden de las cosas

Tres frases suyas, en orden de aparicion, que valen mas que cualquier tarea de esta sesion:

1. **"Calipso es un Obsidian en esteroides"**: la red documental usa las convenciones de un vault
   (frontmatter, `[[wikilinks]]`, tags) para TODO lo que Calipso escribe, no solo para los repos.
2. **"En el abismo... todo vive ahi, los departamentos, las tools, todo esta indexado"**: el vault no es un
   modulo al costado, es el contenido del abismo. Cada nodo declara su anillo, y con eso la red hereda la
   frontera de privacidad que ya esta construida y probada.
3. **"Ese es el proposito de Calipso tambien: es un ojo sobre todos los proyectos... conoce los nortes,
   conoce los planes... se me pierde el norte muy facil porque soy una persona creativa"**. Sostener el
   rumbo entre proyectos vale tanto como ejecutar. Lo disparo el caso Atlas (seccion 4).

Y una cuarta, sobre la economia: los departamentos de costo puro viven de una **asignacion presupuestaria
apartada** del general ("un bolsillo... de nuestro presupuesto general descontamos esa entrada y no esta
para gastar, porque el departamento ya tiene su gasto").

## 2. La cosmologia, y el estado real de la fabrica

Pedro describio el mundo: la planta donde los departamentos interactuan, la aduana como **isla**, el abismo
con sus clasificaciones de seguridad, y los departamentos como **magos que invocan a Calipso**. El
reconocimiento (`2026-09-16-cosmologia-y-departamentos.md`, 1.196 lineas) lo midio contra el codigo:

- **La aduana como isla: EXISTE**, y el spec ya la define igual ("no es un departamento, no propone ni
  gasta; es un modulo del kernel"). 107 cruces reales.
- **El abismo con anillos: EXISTE** la frontera logica; falta la geografia (rebanada 3).
- **Los magos que invocan: NO EXISTE.** `anillos.puede_preguntar` devuelve `consumidor == 'chat'` y ningun
  modulo del plantel importa el abismo. Es la rebanada 4, diseñada y sin construir.
- **La fabrica entera: CONSTRUIDA Y NUNCA SEMBRADA.** `~/.calipso/economia/` no existe. Cero
  departamentos, cero cartas, cero asientos. La rutina del cierre semanal esta `enabled: false`. Las ~2.500
  lineas del plantel nunca corrieron contra datos reales. `trabajar` devuelve literalmente
  `{'en': 'nada', 'motivo': 'ejecutar trabajo todavia no existe'}`.

**Decision de Pedro: los departamentos LANZAN goals, no SON goals.** El departamento sigue siendo la rutina
permanente (interruptor, modo ensayo, techo de 200 tics) y abre un goal acotado por ciclo. Asi el carril
unico pasa de bloqueo a cola y decidir sigue siendo gratis (el 7b piensa; solo el golpe cuesta, 0,32 USD).

**Decision de Pedro: el padron merece su propia sesion.** Es el unico paso irreversible de la siembra:
`Registro` no tiene `baja` y `ajustar` solo acepta numeros.

## 3. El archivista: los repos documentados

Pedro pidio una copia de sus repos de GitHub y documentarlos bien, con la mira puesta en que Calipso haga
el proceso documental sola cuando conecte **M1** -- que es **el Mac del disco de 2 TB**, o sea el fondo del
abismo (rebanada 2). Conectar M1 y la rebanada 2 son el mismo trabajo.

Lo hecho: los seis repos que faltaban clonados en `~/repos/`; el catastro completo
(`2026-09-16-catastro-de-repos.md`, 798 lineas); y **un `DOSSIER.md` en cada uno de los ocho repos**, en el
formato del vault (frontmatter con anillo, familia, estado y `trabajo_vivo_en`, mas `[[wikilinks]]` entre
ellos), cada uno escrito por un lector y **corregido por un verificador** que midio cada afirmacion contra
el repo. Los seis privados estan pusheados; **los dos publicos no**: su seccion "Cuidado con" es un mapa
preciso de sus propias debilidades y no se publica hasta arreglarlas.

Ademas, dos cosas que vivian en un solo disco quedaron bajo git y en GitHub (privados): `calipso-lector`
(36 KB de diseño aprobado que solo tenian un `.bak` al lado) y `ally-tools` (las cinco piezas de
`ally-screen-idle` y `kwin-dpms`, repartidas entre `~/.local/bin`, `~/.local/share` y `~/.config`).

La clasificacion la dio Pedro y no se deduce de ningun repo: **trabajo** (los tres `cam-crm-vincere*`),
**personales** (`AvesCO`, `Observatory-Global`, `calipso`), **legacy** (`research-court`, del que Calipso
es la evolucion, y `noaa-proyecto`).

## 4. El caso Atlas: por que el ojo hace falta

El checkout local de Atlas estaba **39 commits atras** del remoto, y por eso el catastro lo dio por
pausado. Sincronizado y vuelto a mirar, aparecio lo contrario y tres cosas que Pedro no sabia:

- Produccion esta **viva y sana** (verificado: `/api/v2/stats` 200, `degraded:false`, 63.971 señales en
  24 h, 5.422 fuentes, la poda corriendo). Los crons del Mac si corren.
- El **kit v2 se construyo el 08-24 y nunca se mergeo**: tres semanas de produccion sirviendo el v1 ya
  rechazado. Probado en git: fecha de autor 08-24, fecha de commit 09-11.
- El **paquete del post #1 esta listo desde el 09-15 y no se publico**; cero eventos de telemetria entre el
  08-26 y el 09-10.
- El **saldo de DeepSeek se acabo en silencio** el 09-13 y la nocturna corrio sin court ni relabel. Ya
  habia pasado con Anthropic en junio: es un patron.

De ahi sale la forma de la capacidad: una alarma util no es "hace N dias que no tocas esto" -- eso es falso
para un proyecto terminado a proposito. Es **la diferencia entre el norte declarado y el estado derivado**.
El norte lo pone Pedro una vez; el estado lo deriva Calipso sola y barato (git, HTTP, saldos); la deriva es
lo que se avisa. Las tres alarmas son del mismo tipo: **trabajo terminado sin integrar, trabajo listo sin
publicar, dependencia caida en silencio.**

## 5. Las manos (subproyecto 2): siete de ocho decisiones cerradas

El terreno (`2026-09-16-terreno-manos.md`, 1.046 lineas) desmintio tres premisas del spec borrador:
bwrap anidado SI anda (faltaban dos mounts); el MCP NO corre dentro del sandbox (este envuelve cada comando
Bash, no la sesion, asi que el MCP corre como Pedro y toda la contencion se muda al token); y hoy cualquier
tool `mcp__` mata el golpe (`goals_manos.py:647`). Ademas: Blender pesa 1,1 GB y no hay remote flathub
`--user`, asi que la linea del caso guia falla antes de tocar la red.

Las decisiones estan en la memoria del proyecto y en el documento del terreno. Las tres que mas mueven:
`correr_app` corre **afuera** del sandbox del CLI bajo `correr_confinado` con `--tmpfs /run/user/1000`; el
nivel es **mixto por app** (directo las que transforman datos, pregunta las que ejecutan codigo ajeno); y
para Blender el martillo **no escribe bpy libre**: emite un spec JSON validado y el script que corre es del
repo, fijo y revisado.

**La que queda abierta es la deteccion**, y es la mas interesante. Pedro eligio que la propuesta automatica
se dispare siempre que haya manos, con una condicion: *"la deteccion tiene que ser perfecta, arreglemosla"*.

## 6. El banco del detector de manos

Construido hoy, con el metodo de siempre: medir antes de cablear.

- `experimentos/historial_export.py` (rama `feat/historial-export`, 18 tests, TDD): saca del historial de
  Claude Code lo que escribio Pedro y solo eso. **449 mensajes.** Tres filtros, los tres medidos: las
  marcas XML del CLI, dos frases que no llevan marca (7 de 456), y la ruta -- lo que vive bajo `subagents/`
  es el prompt que recibio un agente, indistinguible de un mensaje de Pedro por su forma. Ese era el que
  envenenaba el dataset. Nada con secretos entra.
- El banco: `~/.calipso/experimentos/banco_manos.jsonl` (0600, fuera del repo porque son sus mensajes).
  Etiquetado por dos lectores independientes mas desempate: 412 por acuerdo, 37 por desempate, 12 quedaron
  para Pedro.
- **El numero: la regex de hoy tiene recall 8%.** Sobre 245 mensajes de chat (separando los prompts de los
  probes, que inflan la clase manos): aciertos 60%, precision 67%, 4 falsos positivos y 95 falsos
  negativos. No sobre-dispara: esta ciega.
- **El hallazgo que cambia la pieza: el 41% de los pedidos con manos son continuaciones cortas** -- "dale,
  escribilo", "merge y push", "reinicia el servidor y sigamos". Ningun detector que mire el mensaje AISLADO
  puede acertarlos ni en principio. **No es un clasificador de mensajes: es mensaje + contexto del turno
  anterior.** Eso va al spec antes de implementar nada.

## 7. El cruce con los repos que Pedro marco

`2026-09-16-cruce-repos-marcados.md`. De los cinco, **uno solo es ingenieria portable**: `claude-obsidian`
(15.006 estrellas) -- 23 modulos Python con cero dependencias, 34 archivos de test, y el reparto que
importa: el Python nunca llama a un LLM; el modelo redacta un bundle JSON y el Python lo valida, lo hashea
y lo aplica atomicamente. `OpenCut` (89.606 estrellas) promete MCP, headless y CLI con cero codigo detras.

Lo mas valioso para tomar: **procedencia por CAMPO, no por documento** (evidencia a favor y en contra,
caducidad declarada, e independencia de fuentes calculada para no auto-confirmarse leyendo el mismo chat
tres veces). Es exactamente lo que el catastro pidio por escrito y no tenia con que hacer.

Y el hueco que señalo, que es cierto: hoy hay ocho `DOSSIER.md` con frontmatter consistente y **cero lineas
de codigo que los declaren, validen o lean**. El vault nacio como artefactos, no como mecanismo.

Advertencia: OpenMontage es **AGPL-3.0 con clausula de red** y Calipso sirve una PWA por HTTP. Se miran los
patrones, no se copia una linea.

## 8. Lo que queda, en orden

1. **El spec v2 de las manos**, con las siete decisiones y el hallazgo del contexto en la deteccion; despues
   las lentes, el plan y el SDD.
2. **El detector con contexto**, medido contra el banco. Y los 12 casos que quedaron para Pedro.
3. **La sesion del padron**: definir cada departamento, su alcance y lo que se espera. Es irreversible.
4. **El esquema del nodo del vault** (`calipso/vault/esquema.py`), que es lo que le falta a los ocho
   dossieres para dejar de ser archivos sueltos. Horas, no dias.
5. La deriva (`calipso/deriva.py`), determinista y a cero tokens, cuando el norte este declarado.
6. Lo pospuesto: los ojos (subproyecto 3), la rebanada 2 del abismo (M1, el Mac), el modelo propio.

## 9. Pendientes que Pedro decidio postergar

- **Rotar el token de GitHub**: esta en texto plano en el historial de Claude Code y ese mismo token recibio
  hoy permiso de `Administration: write`. El sandbox tapa `~/.config/gh` pero NO `~/.claude/projects`.
  Pedro: "no importa el token, despues lo arreglamos".
- Los datos de terceros en los dos repos publicos (correos corporativos, una encuesta interna con respuestas
  de empleados) y el `.env` en la historia de `CAM-CRM-Vincere` con RLS sin endurecer.
- Once PDF en `~/Downloads` con nombre y apellido de once traders reales, y cuatro CSV de NinjaTrader en el
  escritorio.

## 10. Como retomar

```
cd /var/home/pedro/calipso && git status --short && git log --oneline -3
ss -ltn | grep ':8000 '                      # el server real
cat docs/superpowers/2026-09-16-estado-y-ruta.md   # este documento
git worktree list                            # la rama feat/historial-export vive en .claude/worktrees/historial
nice -n 19 .venv/bin/python experimentos/banco_manos.py   # el numero del detector, desde el worktree
```
