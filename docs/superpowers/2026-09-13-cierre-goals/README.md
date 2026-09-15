# Cierre de los goals (feat/goals, 2026-09-13/14)

El goal que corre: `/goal <texto>` -> propuesta de la cabeza -> `dale` -> golpes de Claude Code en un clon
bajo el sandbox nativo + hook fail-closed -> juez (criterio confinado + revisor de otra familia) -> Pedro.
Spec: `docs/superpowers/specs/2026-09-13-goals-design.md` (v2 + adenda seccion 16, rulings 15-31). Plan:
`docs/superpowers/plans/2026-09-13-goals.md` (7 tasks). Smoke: `docs/superpowers/2026-09-13-smoke-goals.md`.

Lo que hay en esta carpeta (copias de `.superpowers/sdd/2026-09-13-goals/`, que git ignora):

- `ledger.md`: el ledger del SDD con todos los rulings del controlador (preflight, ejecucion, cierre).
- `terreno-plan.md`: el CLI de Claude Code y Codex verificado antes del plan (sandbox, hooks, stream-json).
- `reportes-de-tasks.md`: los reportes de los implementadores de las 7 tasks (el 7 con las 4 corridas).
- `revision-final.md` / `revision-codex.json`: la revision final (4 areas, 2 lentes) y Codex adversario.
- `ola-de-fix-briefs.md` / `ola-de-fix-reportes.md`: los cinco carriles de la ola de fix.

## Lo que queda para Pedro

1. El primer goal real, chico, con la pestana Goals abierta: `/goal <algo concreto de un repo tuyo> hasta:
   <criterio medible> tope: 6 golpes 30m`. Mirar en `~/.calipso/goals/<id>/golpes.jsonl` las columnas
   `unidades` y `rate_limit` y contarnos cuanto gasta un golpe real de la ventana de 5 h.
2. Si algo sale mal: `CALIPSO_GOALS=off` en el entorno del server y reiniciarlo (los goals quedan en su
   estado en disco; nada mas cambia).
3. Decisiones tuyas pendientes (adenda): las unidades (iteraciones del CLI vs turnos de modelo); una raiz de
   solo lectura para aprobar lecturas sueltas del home; el revisor codex envuelto en bwrap; las compuertas
   `merge`/`push` (hoy el merge de la rama `goal/<id>` es tuyo, a mano).
4. Tandas siguientes: subproyecto 2 (las manos: MCP hacia Calipso, aduana por comando, herramientas
   propias, Codex con red por dominios), subproyecto 3 (los ojos), y las rutinas -> goals (`reflect`).
