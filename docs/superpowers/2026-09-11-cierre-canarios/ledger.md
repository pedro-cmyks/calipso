# SDD ledger — plan: docs/superpowers/plans/2026-09-11-canarios.md

Rama: feat/canarios desde main d1fcb63. Spec: docs/superpowers/specs/2026-09-11-canarios-design.md.
Metodo: workflow sdd por task (implementador opus -> revisor opus -> hasta 3 rondas fix + re-review sonnet); cierre con revision final + lente + Codex.

## Preflight (2026-09-11 16:20)

Los dos criticos del plan hicieron el barrido cruzado; el corrector aplico 18 correcciones (seccion final del plan). Firmas cruzadas verificadas por el critico de cobertura (veredicto, anclaje, degeneracion, presupuesto, recortar, truncado, _chunks_for con history y messages, prompt_reentrada por secciones, la forma de canarios en chat_turn/meta/senal ws). Todo el codigo de las tasks 1-7 corrio sobre una copia (234 passed + 27; node 439; bancos: anclaje recall/precision 100% en 3 clases sobre 22 filas reales con contexto armado; degeneracion 19/19 rotas 0/32 falsas; memoria 32/33 0/25).

Ruling (ruling 2 del plan, pedido antes de la Task 7): la letra de la reentrada ATERRIZA si `sin_anclaje` no sube y `sin_dato FALSO` (no-saber con la verdad en el bloque) no sube; un `sin_dato` GENUINO que sube (el 7b deja de inventar y dice que no lo tiene cuando el bloque no lo trae) es la conducta que Pedro pidio ("que si no sabe que no diga"), no un empeoramiento. La letra del spec ("no empeora en ninguna de las tres") se corrige al cerrar. Costo si esta mal: mas "no lo tengo" honestos en turnos donde antes inventaba; reversible con CALIPSO_REENTRADA.
Ruling (ruling 3): "anotado" se coteja contra el remember episodico (como esta): un "anotado" nunca sale sin anclaje en produccion; la clase mide consulto/repo/web. Se anota como limite para Pedro.
Ruling (ruling 13): el piso del banco de la memoria NO se sube en esta rama.
Ruling (ruling 14): la marca visible sigue solo en turnos sobre Pedro; las confabulaciones tecnicas van a la fila y al resumen. Para Pedro con los numeros.

## Ejecucion (workflow wf_c7ebb7ff-d3f, 2026-09-11 16:30-17:40)

Task 1: complete -- d1fcb63..d0493b3 (anclaje + banco + unitarios); rev aprobada, 7 menores.
Task 2: complete -- d0493b3..44dd47c (degeneracion + done_reason en dispatch + banco); rev aprobada, 6 menores.
Task 3: complete -- 44dd47c..51adaa2 (estructura del turno, byte a byte); rev aprobada, 3 menores.
Task 4: complete -- 51adaa2..d5211ed + fix 1 ..4490580 (ventana); rev con 1 importante, resuelto en re-review.
Task 5: complete -- 4490580..c9311fd + fix 1 ..6f46a76 (cableado); rev con 1 importante, resuelto en re-review.
Task 6: complete -- 6f46a76..c1e61ea (marcas en las dos UIs); rev aprobada, 3 menores.
Task 7: complete -- c1e61ea..e415a28 + fix 1 ..90b999c (letra de la reentrada + porton N=3; DONE_WITH_CONCERNS: dos filas de nueva contaminadas por un OOM de Ollama, excluidas por `valida`); rev con 1 importante (el porton contaba filas que no contesto el 7b), resuelto en re-review.
Task 8: interrumpida a las 17:4x (impl:8 recargo el 7b con 776 MB libres mientras Pedro jugaba: TaskStop, 7b descargado, parcial de experimentos/canarios_smoke.py movido al scratchpad task8_parcial/). Se relanza con la maquina holgada (MemAvailable ~7 GB, PSI 0, Ollama sin modelos).
Ruling (recursos, pedido de Pedro 2026-09-11 tarde): cualquier paso que cargue el 7b o Chromium mide MemAvailable antes; si hay menos de 6,4 GB libres (5,4 del 7b + 1 de margen) espera o se declara BLOCKED, no arranca a ciegas. Costo si esta mal: un smoke que espera de mas; reversible.
Task 8: complete -- 90b999c..a746072 (smoke en vivo: 6 turnos con Ollama real + 2 con el falso, capturas, informe; el implementador devolvio BLOCKED solo por las capturas de la fase B) + 2a6c580 (fix del controlador: umbral propio para Chromium y corrida 3 de la fase B con las cuatro capturas). Suite 1773 passed; node 439. La revision de la Task 8 corre junto con la revision final del cierre.
Ruling (recursos, Chromium): el umbral de recursos se mide contra lo que el paso pide (Chromium headless ~0,4 GB -> LUGAR_CHROMIUM_MB 1500), no contra el 7b siempre. Costo si esta mal: una captura que compite con un juego; reversible.
Hallazgo del smoke para la ola de fix del cierre: carrera de la PWA al arranque (loadChats() pinta el historial antes de que el modulo cuelgue window.Canarios; las marcas guardadas en meta.canarios no se ven hasta re-abrir el chat). Candidata a la ola de fix (una linea).

## Cierre (2026-09-11 noche)

Revision final en paralelo (6 revisores: Task 8, tres areas, lente del spec, lente de riesgo) + Codex gpt-5.5 headless: 0 criticos, 12 importantes (7 distintos), 34 menores. Consolidado en `cierre-hallazgos.json` y en la carpeta del cierre.
Ola de fix (unica): brief `ola-de-fix-brief.md` (8 puntos) -> 2a6c580..4cdd1e9 (9 commits, DONE_WITH_CONCERNS: la negacion pegada DESPUES de una senal de marco tambien cuenta, ratificada) -> re-review 8/8 resueltos, 1 importante nuevo (el patron fuerte anulaba la oracion entera: una confabulacion con hedge en la cola dejaba de marcarse) + 1 menor (SKIP_DIRS -> SKIP_DIRS_RAIZ) -> arreglados por el controlador en 0e7cbc0 (banco 27 filas 100/100; suite 1788 passed).
Ruling (ola de fix, punto 1): el no-saber honesto con senal de memoria no sale "sin verificar" (negacion antes de la senal en la misma clausula, pegada despues de una senal de marco, o patron fuerte de no-saber que EMPIEZA antes de la senal). Es un cambio de umbral medido por el banco (100/100 antes y despues). Costo si esta mal: 'Aunque no estoy seguro te conte sobre X' sin coma no se marca; reversible.
Ruling (CALIPSO_CANARIOS=off): interruptor por llamada como rollback en caliente; la ventana sigue estimando (carga el tokenizador) pero no recorta. Costo: nada si no se usa.
Ruling (aviso de Ollama caido): no es una respuesta: sin remember, sin veredicto, sin senal; chats.json lo guarda porque Pedro lo leyo. Preexistente en main.
Residuos declarados (no se tocan en esta rama): recordo cotejado contra el remember episodico (ruling 3); el porton aterrizo la letra nueva por default (0/0/0 con dos contadores ciegos; reversible con CALIPSO_REENTRADA=vieja); reserva_respuesta en el presupuesto; titulos con cola y 'y/o' como archivo; sin_dato por turno en telemetria; 'lo anoto' en presente no es accion afirmada; el smoke no se re-corrio tras la ola (la captura de la PWA como prueba del primer pintado queda para la proxima corrida); server.py:2450 (/local al ranking entero) va al frente de la carga.
Merge --no-ff a main: pendiente del controlador (siguiente paso).
