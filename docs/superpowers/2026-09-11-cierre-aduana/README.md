# Cierre de la rama feat/aduana (2026-09-11)

- `ledger.md`: la ejecucion entera (preflight, 9 tasks, rondas de fix, rulings del controlador, minors diferidos, cierre).
- `revision-final-y-lentes.md`: la revision final de merge, las tres lentes adversarias con sondas (eficacia, regresiones, completitud) y la lente de Codex headless.
- `ola-de-fix.md` y `ola-de-fix-reporte.md`: los 12 puntos de la unica ola de fix y el reporte del implementador (9 commits `cd4ee5d..db88602`), re-review 12/12.
- El smoke en vivo: `../2026-09-10-smoke-aduana.md`.

## Lo que queda para Pedro

1. **Rulings tomados en su nombre (todos en `ledger.md`, revertibles):** la lista negra de git extendida (spec 7); el detector completo en destino `afuera` (un SHA de 40 hex corta la consulta, como en /nube; afinar el detector es otra tanda); `GET /api/browser/screenshot` = `ui` y `PUT /api/config` = `gesto`; el tablero ve mas metadatos que la enumeracion literal del spec (nunca carga, chat ni URL); `pr` guarda titulo + 2 lineas del body; el umbral de 12 caracteres para un segmento de query sin `=`.
2. **Un efecto lateral sobre el home real:** un turno basura ("-q" / "Nada.", 01:42:55 del 2026-09-11) en el chat "que proyectos tengo? nombralos con su rama", escrito por `test_chat_live.py` al ser importado por un agente de la revision. El script ya no se ejecuta al importar. Borrar ese chat es de Pedro.
3. **Tanda B (no construida, decidida con los numeros de la aduana):** `HF_HUB_OFFLINE` tras la primera descarga, el chequeo de npm a pedido, Monaco y las fuentes servidas desde el repo. Y la familia `red` del motor de permisos (frenar), si se quiere.
4. **Minors diferidos** con nombre en `ledger.md` (24), ninguno bloquea.
