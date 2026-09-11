# Cierre de la rama feat/memoria-procedencia (2026-09-11)

- `ledger.md`: preflight con los rulings previos (--vista permitida; antes = main exacto; presupuesto del abismo sin tocar), las 5 tasks, el ruling 6 con los datos del porton, las dos olas de fix y los minors diferidos.
- `revision-final-y-lente.md`: la revision final de merge y la lente de eficacia con sondas sobre el fixture real.
- `ola-de-fix-1.md` y `ola-de-fix-2.md`: los puntos de las dos olas (re-review 4/4 y 4/4).
- El informe del cierre de la Task 5 (porton antes/A/B, smoke de escritura y reindex): `../2026-09-11-cierre-memoria-procedencia.md`; los numeros crudos: `experimentos/porton_memoria_resultados.md` y `.jsonl`.

## Lo que queda para Pedro

1. **Ratificar o cambiar el ruling 6:** variante aterrizada A (la frase fija 'Calipso no tenia el dato entonces (ruta, fecha)'). Con los textos: B inventa en `presupuesto`, A dice que no tenia el dato. Cambiar a B es `VARIANTE_DEFAULT` y una linea de test.
2. **El reindex del home real** (tu acto): `.venv/bin/python -m calipso.memoria_reindex --vista` (se puede con el server prendido) y `--aplicar` con el server apagado (o `--forzar`).
3. **h07 (fuera de esta rama):** el 7b se cree sus propias respuestas viejas aunque lleven la etiqueta 'Calipso contesto (local, fecha)'; la trilogia inventada vuelve 2/2 en todas las condiciones. La procedencia que falta es si esa respuesta salio con el abismo consultado o sin consultar (guardar `consultas` en el episodio y mostrarlo).
4. **El sub-bloque `recuerdos` del abismo satura los 2000 chars** (13 de 13 pescados de memoria al techo): core y cronologia no entran cuando hay 8 hits. Presupuesto por sub-bloque, otra tanda.
5. Minors diferidos con nombre en `ledger.md` (hedges, catastro+fuerte, coletilla, reflect con presentar).
