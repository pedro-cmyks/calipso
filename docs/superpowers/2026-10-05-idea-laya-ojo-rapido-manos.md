# Idea: Laya como el "if" rapido de las manos (2026-10-05)

Nota de Pedro, dictada en la sesion del 2026-10-05, para que no se pierda. No es
spec ni plan: es una direccion para el subproyecto de las manos
(`specs/2026-09-15-manos-design.md`, terreno medido en
`2026-09-16-terreno-manos.md`).

## El problema

Calipso corre en el computador de Pedro (Linux). Para que actue sobre la
maquina -- hacer clic, ver cosas, entrar a paginas, mover programas -- no todo
se puede hacer desde el codigo. Hay programas con la puerta abierta (CLI, API,
MCP) y ahi se entra facil. Hay otros que no la tienen y toca navegarlos
directamente, como lo haria una persona: mirar la pantalla y decidir.

Eso obliga a un ciclo de muchas decisiones chiquitas y rapidas: tomar una foto
de la pantalla, decidir para donde moverse, volver a mirar, confirmar si el
movimiento fue el correcto o si ya aparecio lo que se buscaba. Pedirle cada una
de esas decisiones a un modelo grande es lento y caro; son, en palabras de
Pedro, "un if rapidisimo".

## La idea

Usar Laya (Convai, `laya` 0.3.22; el motor de decision "System 1" que ya se
probo en Atlas) como ese `if`: un clasificador no autorregresivo, con
probabilidades calibradas y abstencion por umbral, que responde en milisegundos
preguntas cerradas del tipo:

- "¿Lo que hay en pantalla es la ventana que esperaba?"
- "¿El movimiento que acabo de hacer me acerco a lo que busco?"
- "¿Ya aparecio el elemento que necesito para el siguiente paso?"

El modelo grande planea y decide que hacer; Laya vigila cada paso y dice
si/no/no-se. Solo cuando dice "no" o "no-se" se vuelve al modelo grande.

## Lo que hay que medir antes de construir

1. **Laya no ve.** Es un codificador de texto (ModernBERT + cabeza de decision),
   no un modelo de vision. "Tomar fotos" tiene que convertirse en texto antes de
   preguntarle: arbol de accesibilidad (AT-SPI en Linux), titulo y clase de la
   ventana activa, OCR de la region relevante, o la descripcion corta de un
   modelo de vision pequeno. El "ojo" y el "if" son dos piezas; Laya es el `if`.
2. **Precision en este dominio, con datos propios.** En el piloto de Atlas
   (`docs/research/jev/pilot1`, 2026-10-01) Laya quedo lejos del juez grande en
   una tarea de entailment de etiquetas (58% precision / 40% recall contra 84/88
   de DeepSeek). Esa tarea es mucho mas dificil que "¿esta ventana es la que
   esperaba?", pero hay que medirlo aqui, con capturas reales de esta maquina y
   un conjunto etiquetado a mano, antes de confiarle el volante.
3. **Abstencion como mecanismo central.** Lo util de Laya para este uso no es
   solo la velocidad sino `confidence.py`: umbrales calibrados y abstencion. El
   diseno deberia tratar "no-se" como la salida normal que escala al modelo
   grande, no como un error.
4. **Costo real del ciclo.** Captura + conversion a texto + Laya + accion.
   Medir el tiempo de cada pieza; si la conversion a texto tarda mas que la
   decision, el cuello esta en el ojo, no en el `if`.

## Donde encaja

Dentro del diseno de las manos, como el verificador por paso del runner, al
lado de los portones de permisos ya existentes. No reemplaza al modelo grande
ni toca el sandbox; reduce cuantas veces hay que llamarlo.
