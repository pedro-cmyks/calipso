# Cierre de la rama feat/canarios (2026-09-11)

- `ledger.md`: la ejecucion entera (preflight, 8 tasks, rondas de fix, rulings del controlador, la interrupcion por RAM y la regla de recursos, el cierre).
- `revision-final-y-lentes.md`: la revision de la Task 8, la revision final por tres areas, la lente de fidelidad al spec, la lente de riesgo del reinicio del server real, y Codex gpt-5.5 headless como lente externa. Sin criticos.
- `ola-de-fix.md` y `ola-de-fix-reporte.md`: los 8 puntos de la unica ola de fix y el reporte del implementador (9 commits `2a6c580..4cdd1e9`), re-review 8/8; los dos residuos de la re-review (el hedge en la cola y `SKIP_DIRS_RAIZ`) los cerro el controlador en `0e7cbc0`.
- El smoke en vivo: `../2026-09-11-smoke-canarios.md` (cuatro corridas; las capturas de la fase B con el umbral propio de Chromium). El porton de la reentrada: `experimentos/porton_reentrada_resultados.md`.
- El spec quedo con un addendum (seccion 9) con los 15 rulings tomados al construir, para que Pedro los vete por numero.

## Lo que queda para Pedro

1. **Rulings tomados en su nombre** (spec seccion 9; todos revertibles): los tres que mas pesan son (a) la letra de la reentrada quedo por default, no por evidencia (el porton dio 0/0/0 con dos contadores ciegos; `CALIPSO_REENTRADA=vieja` la revierte); (b) el no-saber honesto con senal de memoria ya no sale "sin verificar" (umbral medido, banco 27 filas 100/100); (c) `anclado_solo_en_calipso` (h07: el 7b se cree sus propias respuestas viejas) se cuenta en la fila y el resumen pero NO se muestra en la UI.
2. **Rollback en caliente:** `CALIPSO_CANARIOS=off` en el entorno del server apaga recorte, veredicto, senal y `meta.canarios` sin reiniciar el codigo (si reiniciar el proceso).
3. **Lo que la primera tanda no mide:** `sin_dato` por turno en telemetria; `reserva_respuesta` en el presupuesto; titulos con cola y `y/o` como archivo; `lo anoto` en presente. Siguiente calibracion con telemetria real del home de Pedro.
4. **`server.py:2450`** (`/local` cae al ranking entero con Ollama caido, complejidad 4-5, `/think` o la sonda de salud lenta): va al frente de la carga (spec v2, task 2), no se toco aca.
5. **Nada se empujo a GitHub.** El merge a main es local; el push es de Pedro.
