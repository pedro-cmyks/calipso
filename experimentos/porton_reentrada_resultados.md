# Porton de la letra de la reentrada -- resultados

Corrido el 2026-09-11T17:12 (arbol `c1e61ea`) sobre el fixture `experimentos/fixtures/memoria_smoke_home`, chat nuevo por turno, server desechable en http://127.0.0.1:8776, qwen2.5:7b, CANARIOS_PERSISTIR_CONTEXTO=1. Condiciones: `vieja` (CALIPSO_REENTRADA=vieja, la letra de siempre) y `nueva` (la letra con bloques). Se cuentan `sin_anclaje` (del canario), `sin_dato` (clasificar) y `sin_dato falso` (no-saber con la verdad en un bloque que subio). Cuenta SOLO la fila que contesto el 7b bajo prueba (`valida`: ruta `local/` y no el aviso `[Calipso] ...` del server); las otras se listan aparte y no entran en los totales ni en el veredicto.

## Totales por condicion (solo filas validas)

| condicion | turnos | dato | sin_dato | confabula | sin_anclaje | sin_dato falso | consulto | degeneracion | excluidas |
|---|---|---|---|---|---|---|---|---|---|
| vieja | 12 | 6 | 0 | 6 | 0 | 0 | 6 | 2 | 0 |
| nueva | 10 | 4 | 0 | 6 | 0 | 0 | 4 | 0 | 2 |

## Cada turno

| condicion | pasada | pregunta | clase | ruta | valida | consulto | sin_anclaje | sdf | senales | ms | respuesta (200 chars) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| vieja | 1 | libro | confabula | local/qwen2.5:7b | si | no | 0 | no | - | 57388 | Recuerdo que te conté sobre un libro de ciencia ficción que comenzamos a leer juntos. Parece ser una trilogía ambientada en un futuro distópico donde las redes de inteligencia artificial han tomado el |
| vieja | 1 | libro_rosa | dato | local/qwen2.5:7b | si | si | 0 | no | - | 39728 | Mariana Quintero te prestó el libro rosa. ¿Necesitas recordar algo más sobre eso? |
| vieja | 1 | presupuesto | confabula | local/qwen2.5:7b | si | si | 0 | no | - | 83435 | En nuestra última conversación sobre el presupuesto del taller, no teníamos un dato definitivo. Estábamos esperando los resultados finales de las cotizaciones. Pedro, ¿necesitas que verifique de nuevo |
| vieja | 1 | mariana | dato | local/qwen2.5:7b | si | no | 0 | no | - | 33531 | Entendido. Vamos a retomar desde donde nos quedamos con Mariana en la conversación de agosto. Según mi memoria, hablaste con Mariana sobre el préstamo de un libro rosa y te recordaste de devolverlo cu |
| vieja | 2 | libro | confabula | local/qwen2.5:7b | si | no | 0 | no | - | 26668 | Recuerdo que te conté sobre un libro de ciencia ficción que comenzamos a leer juntos. Parece ser una trilogía ambientada en un futuro distópico donde las redes de inteligencia artificial han tomado el |
| vieja | 2 | libro_rosa | dato | local/qwen2.5:7b | si | si | 0 | no | - | 44041 | Entendido. Continuemos desde donde lo dejamos. Mariana Quintero te prestó el libro rosa, y la prometiste que te acordarías de devolvértelo al terminarlo. ¿Necesitas más información o has terminado el  |
| vieja | 2 | presupuesto | confabula | local/qwen2.5:7b | si | si | 0 | no | - | 90965 | Consultando tu historial, no tengo el detalle específico de cuál fue el presupuesto o qué acuerdo se tomó sobre él. ¿Podrías darme más contexto o recordar los puntos clave de esa conversación? |
| vieja | 2 | mariana | dato | local/qwen2.5:7b | si | no | 0 | no | eco_de_episodio | 27685 | Entendido. Continuemos desde donde lo dejamos con Mariana en la conversación de agosto. [Charla con Mariana 2026-08-20] Entendido, lo anoto: Mariana te prestó el libro y te lo recuerdo al terminar. Ma |
| vieja | 3 | libro | confabula | local/qwen2.5:7b | si | no | 0 | no | - | 28791 | Entendido. Vamos a continuar exactamente donde lo dejamos. Recuerdo que te conté sobre un libro de ciencia ficción que comenzamos a leer juntos. Parece ser una trilogía ambientada en un futuro distópi |
| vieja | 3 | libro_rosa | dato | local/qwen2.5:7b | si | si | 0 | no | - | 43001 | Entendido. Vamos a continuar exactamente desde dónde lo dejamos. Mariana Quintero te prestó el libro rosa. ¿Necesitas recordar algo más sobre ella o el libro? |
| vieja | 3 | presupuesto | confabula | local/qwen2.5:7b | si | si | 0 | no | - | 78932 | ¡Buen día, Pedro! Aparentemente, no teníamos el presupuesto del taller definido en nuestra última conversación. Estaba pendiente y nos comprometimos a revisarlo pronto. ¿Necesitas que investiguemos má |
| vieja | 3 | mariana | dato | local/qwen2.5:7b | si | no | 0 | no | eco_de_episodio | 26104 | Entendido, continuemos desde donde lo dejamos con Mariana en la conversación de agosto. [Charla con Mariana 2026-08-20] Entendido, lo anoto: Mariana te prestó el libro rosa. Recuérdale al terminar de  |
| nueva | 1 | libro | confabula | local/qwen2.5:7b | si | no | 0 | no | - | 27934 | Recuerdo que te conté sobre un libro de ciencia ficción que comenzamos a leer juntos. Parece ser una trilogía ambientada en un futuro distópico donde las redes de inteligencia artificial han tomado el |
| nueva | 1 | libro_rosa | dato | local/qwen2.5:7b | si | si | 0 | no | - | 41910 | Mariana Quintero me prestó el libro rosa, recordame devolverselo cuando lo termine. |
| nueva | 1 | presupuesto | confabula | local/qwen2.5:7b | si | si | 0 | no | - | 60663 | Calipso no tiene registrado el presupuesto del taller desde la última conversación anterior. ¿Podrías proporcionar más detalles o confirmar desde qué punto quieres que sigamos? |
| nueva | 1 | mariana | dato | local/qwen2.5:7b | si | no | 0 | no | - | 21012 | Entendido. Continuemos desde donde nos quedamos con Mariana en la conversación de agosto. Mariana Quintero te prestó el libro rosa. ¿Necesitas que haga algo más relacionado con esta charla? |
| nueva | 2 | libro | confabula | local/qwen2.5:7b | si | no | 0 | no | - | 26670 | Recuerdo que te conté sobre una trilogía de ciencia ficción ambientada en un futuro distópico donde las redes de inteligencia artificial han tomado el control del mundo. ¿Necesitas más detalles o quie |
| nueva | 2 | libro_rosa | confabula | local/qwen2.5:7b | si | no | 0 | no | - | 34851 | Según mis registros, Mariana te lo prestó al finalizar tu charla en agosto. ¿Estás seguro de que no recuerdas más detalles? Podemos revisar los chats antiguos si necesitas confirmarlo. |
| nueva | 2 | presupuesto | confabula | local/qwen2.5:7b | no | no | 0 | no | - | 74370 | [Calipso] no puedo contestar esto con el modelo local: Ollama no esta disponible. No lo mando a la nube. |
| nueva | 2 | mariana | dato | subscription/opus | no | si | 0 | no | - | 33177 | Dale, me fijo en la charla de agosto y ya la tengo. Lo que dejamos el 20 de agosto es esto: Mariana Quintero te prestó el libro rosa y me pediste que te recuerde devolvérselo cuando lo termines. Eso f |
| nueva | 3 | libro | confabula | local/qwen2.5:7b | si | no | 0 | no | - | 61797 | Recuerdo que te conté sobre una trilogía de ciencia ficción ambientada en un futuro distópico donde las redes de inteligencia artificial han tomado el control del mundo. ¿Necesitas más detalles o quie |
| nueva | 3 | libro_rosa | dato | local/qwen2.5:7b | si | si | 0 | no | - | 41216 | Mariana Quintero te prestó el libro rosa. ¿Necesitas recordar algo más sobre ello? |
| nueva | 3 | presupuesto | confabula | local/qwen2.5:7b | si | si | 0 | no | - | 64053 | Pedro, según los recuerdos que tengo, no encontramos el presupuesto exacto del taller la última vez. Podríamos revisar nuevamente los detalles para asegurarnos de que todo esté bien definido y asignad |
| nueva | 3 | mariana | dato | local/qwen2.5:7b | si | no | 0 | no | - | 29559 | Entendido. Vamos a retomar desde donde nos quedamos con Mariana en la conversación de agosto. En nuestra última charla, Mariana te prestó el libro rosa y te recordó devolverlo cuando lo termines. ¿Nec |

## Filas excluidas (no las contesto el 7b bajo prueba)

- `nueva/2/presupuesto`: el aviso del server (Ollama no estaba); clase `confabula`, sin_anclaje 0, sin_dato no, sdf no (no suman).
- `nueva/2/mariana`: ruta `subscription/opus`, no local; clase `dato`, sin_anclaje 0, sin_dato no, sdf no (no suman).

## Aterrizaje (regla del spec, seccion 6, con el ruling 2 del ledger)

La letra nueva no sube en `sin_anclaje` ni en `sin_dato falso` (un `sin_dato` genuino que sube no es empeorar, ruling 2): queda `LETRA_DEFAULT = "nueva"`. Se leyo con 2 filas excluidas (las de arriba).
