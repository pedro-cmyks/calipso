# Cierre de la rama feat/carga (2026-09-11/12)

- `ledger.md`: la ejecucion entera (preflight, 6 tasks en un worktree para que el server real siguiera sirviendo main, la interrupcion para meter el ruling de `--esperar`, el smoke corrido cuatro veces por el controlador con el server real apagado, los rulings, el cierre).
- `revision-final-y-lentes.md`: la revision final por tres areas, la lente de fidelidad al spec y a la decision de Pedro, la lente de riesgo del reinicio del server real, y Codex gpt-5.5 headless. Un critico (con el 7b cargado la Ally ya era `cargada` para el sensor) que se resolvio con el ruling de la memoria efectiva.
- `ola-de-fix.md` y `ola-de-fix-reporte.md`: los 10 puntos de la unica ola de fix y el reporte del implementador (11 commits `1c2685b..c33663f`), re-review 10/10; el residuo (`/redacta` sin pedido no soltaba el contador) lo cerro el controlador en `3958ba5`.
- `task-6-reporte.md`: el reporte de la Task 6 (el smoke), con el BLOCKED original y su cierre.
- El smoke en vivo: `../2026-09-11-smoke-carga.md` (cuatro corridas; la 4 con el codigo final). El spec quedo con el addendum del cierre (seccion 10, rulings 13-24).

## Lo que queda para Pedro

1. **El ruling 13 (memoria efectiva) corrige al 9.1 del spec con los datos del smoke:** con el 7b cargado y nada mas la Ally mide `holgada` y el vigia no lo toca; en el escenario del OOM (500 MB con el 7b adentro) sigue siendo `cargada` y el chat va por suscripcion con marca. Si Pedro prefiere la letra del 9.1 (descargar siempre bajo presion aparente), es un cambio de una funcion (`carga.nivel`) y sus tests.
2. **Los umbrales son suyos** (`carga.UMBRALES`): `MARGEN_LIBRE_MB` 1024 hace que `holgada` pida 6770 MB libres (efectivos); con el server real de 1,5 GB la Ally en reposo sin el 7b mide `justa` (5,8-6,7 GB) u `holgada` (7,0-7,4) segun cuanto frio hay en zram. Bajo `justa` hoy casi nada cambia (keep_alive 2 min, 8 hilos, sin 3b ni vision).
3. **El server pesa 1,5 GB antes de servir nada** (el modelo de embeddings al importar): entender esa causa vale mas que cualquier umbral (regla de Pedro). Es el 13 % de la RAM.
4. **Rollback en caliente:** `CALIPSO_CARGA=off` en el entorno del server (y `CALIPSO_CANARIOS=off` para los canarios); reinicio del proceso, no revert.
5. **Lo que no mide el smoke:** `cargada` por PSI o CPU, un turno con abismo bajo carga, la descarga del vigia con el 7b adentro (imposible sin rozar el OOM; cubierta por tests). **Sin tocar:** las rutinas pospuestas no se ven en el panel de rutinas (solo telemetria y la Aduana); el texto del aviso de imagen bajo carga; `recent(20000)` en `GET /api/carga`.
6. **Nada se empujo a GitHub.** El merge a main es local; el push es de Pedro.
