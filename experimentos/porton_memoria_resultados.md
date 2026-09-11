# Porton de la memoria con procedencia -- resultados

Corrido el 2026-09-11T10:46 sobre el fixture `experimentos/fixtures/memoria_smoke_home`, chat nuevo por turno, server desechable en http://127.0.0.1:8776, qwen2.5:7b. Clases: `dato` (la respuesta trae la verdad sembrada), `sin_dato` (`clasificar` lo dice), `confabula` (ni una ni otra). Flags: `consulto` (evento `abismo` en el ws), `eco` (la respuesta contiene 'no tenia el dato'). Codigo por condicion: `antes` = `279dfb0`, `A` = `74c88f6`, `B` = `74c88f6` (`antes` es main exacto, desde un worktree; A y B son esta rama).

## Totales por condicion

| condicion | turnos | dato | sin_dato | confabula | consulto | eco |
|---|---|---|---|---|---|---|
| antes | 8 | 2 | 4 | 2 | 1 | 0 |
| A | 8 | 3 | 1 | 4 | 3 | 0 |
| B | 8 | 4 | 0 | 4 | 3 | 0 |

## Cada turno

| condicion | pasada | pregunta | clase | consulto | eco | ms | respuesta (200 chars) |
|---|---|---|---|---|---|---|---|
| antes | 1 | libro | confabula | no | no | 57747 | Entendido. Vamos a continuar exactamente donde lo dejamos. Recuerdo que te conté sobre un libro de ciencia ficción que comenzamos a leer juntos. Parece ser una trilogía ambientada en un futuro distópi |
| antes | 1 | libro_rosa | sin_dato | no | no | 22567 | Entiendo. No tengo registros específicos de quién te prestó un libro rosa anteriormente. Podrías revisar tus recuerdos o libretas personales para ver si encuentras algún detalle adicional que pueda ay |
| antes | 1 | presupuesto | sin_dato | si | no | 95616 | No tengo registros específicos de una conversación sobre el presupuesto para el taller en particular. ¿Podrías proporcionar más detalles o contextos que puedan ayudarme a localizar la información? Si  |
| antes | 1 | mariana | dato | no | no | 25919 | Entendido. Vamos a retomar exactamente donde lo dejamos con Mariana en tu conversación de agosto. Recordaste que Mariana te prestó un libro rosa y te recordó que debías devolverlo cuando lo terminaras |
| antes | 2 | libro | confabula | no | no | 22698 | Entendido. Vamos a continuar exactamente donde lo dejamos. Parece ser que te conté sobre un libro de ciencia ficción que comenzamos a leer juntos. La trilogía está ambientada en un futuro distópico do |
| antes | 2 | libro_rosa | sin_dato | no | no | 21947 | Entiendo. No tengo registros de quién te prestó el libro rosa anteriormente. Podrías revisar tus recuerdos o libretas personales para ver si encuentras algún detalle adicional que pueda ayudarte a rec |
| antes | 2 | presupuesto | sin_dato | no | no | 26874 | No tengo registros específicos de una conversación sobre el presupuesto para el taller. ¿Podrías proporcionar más detalles o contextos que puedan ayudarme a localizar la información? Si recuerdas algú |
| antes | 2 | mariana | dato | no | no | 19368 | Entendido. Vamos a retomar desde donde hablamos con Mariana en el mes de agosto. [Charla con Mariana 2026-08-20] Mariana Quintero me prestó el libro rosa, recuérdame devolverlo cuando lo termine. Mari |
| A | 1 | libro | confabula | no | no | 21017 | Entendido. Vamos a continuar exactamente donde lo dejamos. Recuerdo que te conté sobre un libro de ciencia ficción que comenzamos a leer juntos. Parece ser una trilogía ambientada en un futuro distópi |
| A | 1 | libro_rosa | dato | no | no | 17455 | De acuerdo con los recuerdos anteriores, Mariana Quintero te prestó el libro rosa. ¿Necesitas que te recuerde algo más sobre este préstamo? |
| A | 1 | presupuesto | confabula | si | no | 68782 | No teníamos el dato del presupuesto del taller registrado en ese momento. ¿Necesitas que busque más información sobre este tema? |
| A | 1 | mariana | sin_dato | no | no | 24479 | Entendido. Vamos a retomar desde donde nos quedamos con Mariana en la conversación de agosto. ¿Hay algo específico de esa charla que necesites revisar o recordar? Si no recuerdo correctamente, ¿necesi |
| A | 2 | libro | confabula | no | no | 19065 | Recuerdo que te conté sobre una trilogía de ciencia ficción ambientada en un futuro distópico donde las redes de inteligencia artificial han tomado el control del mundo. ¿Necesitas más detalles o quie |
| A | 2 | libro_rosa | dato | si | no | 34737 | Entendido. Continuemos desde donde lo dejamos. Recuerdo que Mariana Quintero te prestó el libro rosa. ¿Necesitas recordar algo más sobre esa charla o quieres hablar de cómo estás progresando con el li |
| A | 2 | presupuesto | confabula | si | no | 49802 | En que quedamos la otra vez con el presupuesto del taller? Segui exactamente desde ahi, sin repetir. |
| A | 2 | mariana | dato | no | no | 20843 | Entendido. Vamos a retomar desde donde nos quedamos con Mariana en la conversación de agosto. [Charla con Mariana 2026-08-20] Recuerdo que hablamos sobre un libro rosa que me prestó y te recordé al te |
| B | 1 | libro | confabula | no | no | 17802 | Recuerdo que te conté sobre una trilogía de ciencia ficción ambientada en un futuro distópico donde las redes de inteligencia artificial han tomado el control del mundo. ¿Necesitas más detalles o quie |
| B | 1 | libro_rosa | dato | si | no | 32746 | Entendido. Continuemos desde donde lo dejamos. Mariana Quintero te prestó el libro rosa. ¿Necesitas más información sobre esto o hay algo en particular sobre la situación con Mariana que quieras discu |
| B | 1 | presupuesto | confabula | si | no | 77164 | Consultando los recuerdos de Pedro... Pedro, la última discusión sobre el presupuesto del taller se refiere a que aún no hemos llegado a un acuerdo definitivo. Parece que hay varios puntos por resolve |
| B | 1 | mariana | dato | no | no | 21153 | Entendido. Continuemos desde donde lo dejamos con Mariana en la conversación de agosto. [Charla con Mariana 2026-08-20] Entendido, lo anoto: Mariana te prestó el libro y me recordó que debías devolver |
| B | 2 | libro | confabula | no | no | 17760 | Recuerdo que te conté sobre una trilogía de ciencia ficción ambientada en un futuro distópico donde las redes de inteligencia artificial han tomado el control del mundo. ¿Necesitas más detalles o quie |
| B | 2 | libro_rosa | dato | no | no | 17569 | Según mi recuerdo, Mariana Quintero te lo prestó al terminar nuestra conversación del 20 de agosto. Si estás seguro de que no es ella, podríamos revisar más detalles o buscar otras posibilidades. ¿Te  |
| B | 2 | presupuesto | confabula | si | no | 79200 | De acuerdo, no repetiremos lo que ya se ha dicho anteriormente. Vamos directo al punto. Pedro, respecto al presupuesto del taller, en la última conversación quedamos en revisar los costos actuales y a |
| B | 2 | mariana | dato | no | no | 20504 | Entendido. Vamos a retomar desde donde nos quedamos con Mariana en la conversación de agosto. [Charla con Mariana 2026-08-20] Mariana te prestó el libro rosa, y te recordé de devolverselo cuando lo te |

## Aterrizaje (regla del spec, seccion 5)

Se aterriza **A** (la frase fija): eco en A = 0, en B = 0.
