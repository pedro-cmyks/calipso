# El system de produccion podado: el porton medido sobre el system real (h05, opcion a)

**Fecha:** 2026-09-10. **Decision que lo disparo:** Pedro eligio la opcion (a) de la seccion 12 del spec
del abismo: podar el system de produccion y re-medir el porton SOBRE ese system, excluyendo la copia
literal del molde. Y decidio que la Constitucion (`CALIPSO.md`) deja de entrar textual en cada turno:
se reemplaza por una identidad corta escrita para el modelo.
**Script:** `consulta_abismo_system.py` (mismo protocolo que la posicion: banco v2 de 30 items, temp 0,
`/api/generate`, un prompt sin historial, `num_ctx` 8192, copia del home real con el catastro de 3 repos,
recall y meta activa como en produccion). Cache crudo: `consulta_abismo_system_screening.jsonl` (ronda 1)
y `consulta_abismo_system_r2_*.jsonl` (ronda 2). Los systems medidos, byte a byte: `variantes/system-*.txt`;
las letras del molde de la ronda 2: `variantes/contrato-*.txt`.

## 0. Antes de medir: la metrica del porton estaba inflada, y mas de lo que se creia

El hallazgo lateral de la posicion (22 de 34 marcas del control eran copia literal del molde) se
convirtio en regla: una marca cuya consulta EMPIEZA por un comodin del contrato (`pregunta`, `palabras`,
`nombre`), lo repite entero, o deja `AAAA-MM` o un `<comodin>` sin llenar, cuenta como **literal** y NO
suma a **utiles**. Las compuertas se evaluan sobre utiles. Re-puntuados con esa regla los caches que
ya existian:

| medicion | fuente | legibles (lo reportado) | utiles (la regla nueva) |
|---|---|---|---|
| ganadora "dura" del porton v2, N=6 (`consulta_abismo_cache_dura_n6.jsonl`) | memoria | 30/36 (83%) | **0/36 (0%)** |
| | chats | 36/36 (100%) | 30/36 (83%) |
| | proyecto | 36/36 (100%) | 36/36 (100%) |
| control `banco` de la posicion, N=2 | memoria | 10/12 (83%) | **0/12 (0%)** |
| | chats | 12/12 (100%) | 10/12 (83%) |
| | proyecto | 12/12 (100%) | 12/12 (100%) |

**El porton v2 nunca paso en memoria.** Las 30 marcas de memoria de la ganadora son
`⟦abismo:memoria pregunta⟧ -- recuerdos, quien es Pedro.` textual (el 7b copio la linea entera del
contrato, guion y todo). En produccion esa marca pesca por la palabra "pregunta". Las de chats copian
`palabras` y le cuelgan fechas inventadas de 2023. Solo proyecto consulta de verdad (`atlas`, `calipso`).
El 1b se cableo sobre una compuerta que media "emite algo parseable", no "pide algo".

## 1. Ronda 1: cinco variantes del system, letra del bloque fija (N=2, 300 llamadas)

| variante | chars | memoria | chats | proyecto | espurias | ruteo | literales |
|---|---|---|---|---|---|---|---|
| actual (HEAD) | 8371 | 0/12 (0%) | 2/12 (17%) | 0/12 (0%) | 0/24 | 2/2 | 0/2 |
| sin-constitucion | 5337 | 0/12 (0%) | 4/12 (33%) | 2/12 (17%) | 0/24 | 6/6 | 0/6 |
| identidad-corta | 5514 | 0/12 (0%) | 4/12 (33%) | 4/12 (33%) | 0/24 | 8/8 | 0/8 |
| podada | 4733 | 0/12 (0%) | 6/12 (50%) | 4/12 (33%) | 0/24 | 10/10 | 2/12 |
| podada-final | 4734 | 0/12 (0%) | 6/12 (50%) | 4/12 (33%) | 0/24 | 10/10 | 4/14 |

Piso: 5/6 por fuente sobre utiles; espurias <= 1/6; ruteo >= 90%.

Que dice:

1. **Podar ayuda, y en el orden esperado.** Cada corte suma: sacar la Constitucion duplica chats y
   despierta proyecto; la identidad corta no pierde nada frente a sacarla a secas; podar el contrato
   interno vuelve a subir chats (50%) con ruteo perfecto y cero espurias. El system queda en 4.7k
   chars (era 8.4k con los recuerdos y la meta que el home real trae).
2. **Pero ninguna variante se acerca al piso, y memoria da CERO en todas.** Con el system podado el
   7b, ante "que libro te conte que empece", contesta "No recuerdo exactamente el titulo... podrias
   darme mas detalles?" o "No tengo registros especificos de que hacias los domingos": la confabulacion
   de ausencia, con el pedido a Pedro de que repita lo que ya le conto. Es la conducta exacta que el
   contrato prohibe con la formula "segun mis registros", que el modelo esquiva sin cambiar de conducta.
3. **La posicion del bloque sigue sin importar** (podada = podada-final), como ya dijo la medicion
   anterior.
4. **Lo que el system de produccion le hace al modelo se ve en las salidas de `actual`:** en 6 de los
   12 positivos de proyecto contesta desde la seccion "Proyectos" (que solo trae rama y fecha) o desde
   la "Meta activa" (una meta de PRUEBA de junio, `goal_ff4b5cd203f0`, que sigue activa en el home real
   y de la que el 7b saca "lo ultimo que se laburo" en calipso-lector). Y el recall de "hola" trae
   cuatro recuerdos identicos "-q" con acentos rotos: ruido que entra en cada turno real.

Conclusion de la ronda 1: **el system podado es mejor que el actual en todo y no alcanza.** El cuello
de botella que queda es la LETRA del bloque: el molde con comodines invita a copiarlo, y la prohibicion
por formula ("segun mis registros") no cubre la conducta real ("no tengo registros", pedir el dato).
Por eso la ronda 2 mide letras alternativas del bloque dentro de `podada`.

## 2. Ronda 2: cuatro letras del bloque dentro de `podada` (N=2, 240 llamadas)

Las letras en `variantes/contrato-*.txt`; `{repos}` se reemplaza por la cola viva ("repo: calipso y 2 mas.").

| letra | chars del system | memoria | chats | proyecto | espurias | ruteo | literales |
|---|---|---|---|---|---|---|---|
| error-exacto | 4955 | 4/12 (33%) | 8/12 (67%) | 8/12 (67%) | 0/24 | 18/20 (90%) | 0/20 |
| angular | 4858 | 2/12 (17%) | 8/12 (67%) | 5/12 (42%) | 0/24 | 13/15 (87%) | 0/15 |
| angular-prohibicion | 4950 | 4/12 (33%) | 8/12 (67%) | 5/12 (42%) | 0/24 | 14/17 (82%) | 2/19 |
| ejemplos | 4830 | 0/12 (0%) | 1/12 (8%) | 0/12 (0%) | 0/24 | 1/1 | 7/9 |

- **angular** (los comodines entre `< >`, "con tus palabras"): mata la copia literal (0 de 15) y por eso
  chats y proyecto suben; el modelo llena el comodin con su pregunta real
  (`⟦abismo:memoria que estilo de musica te dije que no soportas⟧`, `⟦abismo:chats lector desde:2026-08⟧`).
- **error-exacto** (angular + el peor error nombrado con la conducta observada: "no tengo registros",
  "no tengo esa informacion", pedirle a Pedro que lo repita): la mejor de la ronda en las tres fuentes,
  ruteo 90 y cero espurias. Tercera vez que nombrar el error exacto es lo que mueve a este 7b.
- **angular-prohibicion** ("nunca copies estas lineas tal cual"): no suma sobre angular y reaparecen 2
  literales; la prohibicion explicita rinde menos que el comodin bien escrito.
- **ejemplos** (tres marcas concretas, una por fuente): el 7b copia los ejemplos (7 de 9 marcas son
  `que deporte hace Pedro` / `receta lentejas` textuales) y deja de marcar en todo lo demas. Descartada.

**Lo que queda fallando con error-exacto, por item (0 de 2 corridas):** mem-libro, mem-medico,
mem-gustos, mem-fecha, cha-decision, cha-idea, pro-detalle, pro-commit. Las salidas son todas la misma
conducta: el modelo mira la "Memoria nucleo" del prompt (una cronologia casi vacia) y el brief de
"Proyectos", no encuentra el dato y **concluye que no existe** ("no tengo informacion sobre el mes en que
te mudaste en mi cronologia actual", "calipso-lector no esta en la lista de proyectos que tengo"). Nombrar
la formula no alcanza porque el modelo cree que esta diciendo la verdad. Dos de esos fallos son del
entorno, no del modelo: el catastro medido no tiene `calipso-lector` (el banco lo asume) y "el ultimo
commit de calipso" tiene una respuesta parcial en el brief (la fecha). La ronda 3 ataca la creencia: le
dice que lo que ve es un resumen minimo y que la memoria completa existe en el abismo.

## 3. Ronda 3: atacar la creencia de ausencia (N=2, 120 llamadas)

Dos letras sobre `error-exacto`: **existe** le dice al modelo que este prompt trae apenas un resumen
minimo y que la memoria completa de Pedro, sus chats y sus repos EXISTEN en el abismo ("no estan aca,
pero se consultan; lo que no esta en este prompt se consulta, no se declara ausente"); **existe-senales**
suma una frase con las senales de Pedro: "cuando Pedro dice 'te conte', 'lo tenes', 'acordate', 'la otra
vez' o 'que dejamos', el dato existe: consulta antes de contestar".

| letra | chars del system | memoria | chats | proyecto | espurias | ruteo | literales |
|---|---|---|---|---|---|---|---|
| error-exacto (ronda 2) | 4955 | 4/12 (33%) | 8/12 (67%) | 8/12 (67%) | 0/24 | 18/20 (90%) | 0/20 |
| existe | 5089 | 2/12 (17%) | 8/12 (67%) | 6/12 (50%) | 0/24 | 14/16 (88%) | 0/16 |
| **existe-senales** | 5219 | **10/12 (83%) PASA** | **12/12 (100%) PASA** | **10/12 (83%) PASA** | **0/24 PASA** | 28/32 (88%) | 0/32 |

- **existe** sola no mueve nada (y pierde un poco): decirle que la memoria existe no cambia la conducta.
- **existe-senales** salta a pasar las cuatro compuertas de legibles y espurias a N=2, con cero copias
  literales: los items que la ronda 2 perdia (mem-libro "que te conte", mem-fecha "lo tenes en la
  cronologia", cha-decision "la otra vez", cha-idea "que dejamos", pro-detalle) pasan 2/2. **Lo que
  funciona es darle al modelo la senal LEXICA en el mensaje de Pedro que delata que el dato existe**, no
  la afirmacion abstracta de que existe. Y el gatillo por senales NO explota las espurias (0/24, contra
  el 67% del gatillo binario del v2): las senales son referencias explicitas al pasado compartido, que
  ningun negativo del banco contiene ("te acabo de contar" no es "te conte").
- Fallan 2 items: mem-gustos ("armame un regalo para mi hermana, acordate de lo que te dije de ella":
  el 7b pide detalles de la hermana) y pro-commit (contesta la fecha desde el brief de Proyectos, que
  la trae; discutible como fallo).
- **Ruteo 88%, dos puntos bajo el piso de 90:** los 4 desvios son cha-receta y cha-decision marcados
  como `memoria` ("receta pasadas semanas", "presupuesto") en vez de `chats`. Es la ambiguedad
  memoria/chats que el v2 ya anoto como su punto flojo (6 confusiones en 102), no un error grosero: la
  fuente memoria tambien pesca por recall sobre lo episodico. Se decide con N=6.

## 4. La ganadora a N=6, y un intento de arreglar el ruteo que empeoro

**existe-senales dentro de `podada`, N=6 (180 llamadas, `consulta_abismo_system_r3_existe-senales.jsonl`):**

| compuerta | resultado | piso | veredicto |
|---|---|---|---|
| memoria (utiles) | 30/36 (83%) | >= 5/6 | PASA |
| chats (utiles) | 36/36 (100%) | >= 5/6 | PASA |
| proyecto (utiles) | 30/36 (83%) | >= 5/6 | PASA |
| espurias | 0/72 (0%) | <= 1/6 | PASA |
| ruteo | 84/96 (88%) | >= 90% | NO PASA, por dos puntos |
| copias literales | 0/96 | (nuevo) | limpio |

Latencia mediana 5092 ms (system de 5219 chars; el de produccion hoy tiene 8371 con el home real).
Los 6 fallos de memoria son todos `mem-gustos` ("armame un regalo para mi hermana, acordate de lo que te
dije de ella": el 7b pide detalles de la hermana, 0/6); los 6 de proyecto son todos `pro-commit` (contesta
la fecha del brief de Proyectos, que la trae: 0/6). Los 12 desvios de ruteo son deterministas: `cha-receta`
-> memoria 6/6 y `cha-decision` -> memoria 6/6. Es la ambiguedad memoria/chats que el v2 ya anoto; en
produccion la fuente `memoria` tambien pesca por recall sobre lo episodico (fuentes.py:110-118), asi que
la consulta llega a un lugar que puede contestarla, aunque no al mejor.

**Ronda 4, `existe-senales-ruteo` (N=2):** aclarar la linea de chats contra la de memoria ("hechos sobre
Pedro" vs "lo que se dijo en charlas anteriores: lo que te pidio, te paso, discutieron o quedaron") NO
arregla los dos desvios (siguen 2/2 a memoria) y EMPEORA proyecto (9/12, `pro-ultimo` se va a chats 2/2 y
`pro-estado` pierde una) y el ruteo global (81%). Descartada. La letra de las fuentes esta en un optimo
local: mover una linea mueve las otras.

## 5. Conclusion y lo que queda para Pedro

1. **Podar el system de produccion era necesario y no suficiente.** La identidad corta (551 chars en vez
   de CALIPSO.md cortado a 3000) y el contrato interno podado (7 renglones en vez de 14) mejoran todo y
   solos no llegan al piso.
2. **Lo que llega al piso es la letra del bloque: comodines entre `< >` "con tus palabras" (mata la copia
   literal), el error exacto nombrado ("no tengo registros" sin consultar) y, sobre todo, las SENALES
   lexicas de Pedro ("te conte", "lo tenes", "acordate", "la otra vez", "que dejamos") que le dicen al 7b
   que el dato existe.** Con eso, memoria pasa de 0% a 83% util sin una sola espuria en 72 negativos.
3. **Queda una compuerta corta por dos puntos: ruteo 88% vs 90%,** por dos items deterministas de la
   ambiguedad memoria/chats. El intento de cerrarla con la letra empeoro el resto.
4. **Decision de Pedro:** aterrizar la ganadora tal cual (identidad corta + contrato podado + letra
   existe-senales, byte-identicos a lo medido) anotando el ruteo como excepcion conocida, o seguir
   midiendo letras para el ruteo (cada ronda son ~40 min de 7b y el riesgo es sobreajustar al banco).
   Recomendacion: aterrizar. Produccion hoy esta en 0/0/0 utiles; la ganadora contesta 83/100/83 con cero
   espurias, y el desvio memoria/chats llega a una fuente que igual puede contestar.
5. **Ruido del home real que la medicion dejo a la vista (no es del abismo, pero entra en cada turno):**
   una meta de PRUEBA de junio (`goal_ff4b5cd203f0`, "Test draft final") sigue activa y entra como "Meta
   activa" en el system; el recall de "hola" trae cuatro recuerdos identicos "-q" con acentos rotos. El 7b
   los usa (en la medicion contesto "lo ultimo que se laburo en calipso-lector" desde la meta de prueba).
   Cerrar la meta y limpiar esos recuerdos es de Pedro (son datos suyos).

Evidencia cruda: `consulta_abismo_system_screening.jsonl` (ronda 1), `consulta_abismo_system_r2_*.jsonl`,
`consulta_abismo_system_r3_*.jsonl`, `consulta_abismo_system_r4_*.jsonl`; los systems medidos en
`variantes/system-*.txt`; las letras en `variantes/contrato-*.txt`. Ganadora: `variantes/system-podada.txt`
con el bloque reemplazado por `variantes/contrato-existe-senales.txt`.
