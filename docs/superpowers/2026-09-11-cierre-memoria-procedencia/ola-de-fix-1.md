# Ola de fix del cierre de feat/memoria-procedencia (una sola)

Rama feat/memoria-procedencia, HEAD c31e8dd. TDD, suite completa antes de cada commit, rutas explicitas, trailer.

1. **Aterrizaje A (ruling del controlador, ledger):** VARIANTE_DEFAULT queda "A" (no tocar codigo). Corregir los docs que decian que no se aterrizo nada: docs/superpowers/2026-09-11-cierre-memoria-procedencia*.md (o como se llame el informe del cierre de la Task 5) y la adenda de la seccion 9 de docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md: 'Variante aterrizada: A (ruling del controlador con los datos: B inventa en presupuesto, A dice que no tenia el dato)'; la nota del dossier de memoria del agente NO se toca (es del controlador). experimentos/porton_memoria_resultados.md queda como esta (dice 'se aterriza A', ahora es verdad).
2. **Patron fuerte nuevo:** `no teniamos (el|ese|este|ningun|la) (dato|informacion)` (con la regla de posicion como los demas) en calipso/memoria_procedencia.py, y en experimentos/no_saber_banco.py la fila sin_dato con la respuesta REAL del porton: "No teníamos el dato del presupuesto del taller registrado en ese momento. ¿Necesitas que busque más información sobre este tema?". Verificar el piso del banco (0 falsos sin_dato, >= 90%). Si el patron degrada algun dato del banco, NO lo sumes: devolve DONE_WITH_CONCERNS con el caso.
3. **Minors de la Task 1 que conviene cerrar** (calipso/memoria_procedencia.py): (a) presentar_recuerdos con tope <= 0 devuelve [] (guard antes del append) + aserto; (b) presentar() de un texto vacio devuelve '' tambien en off (como main saltaba) + test; (c) una variante explicita invalida cae a variante_activa() (o levanta ValueError; elegi caer al default y documentalo) + test; (d) test del enganche env -> presentar (MEMORIA_PRESENTAR=off/B/ausente) sin pasar variante explicita.
4. **Minors de la Task 5 (docs):** en el informe del cierre, '5 de 5' pasa a '13 eventos pescado en 6 turnos, los 13 al techo de 2000'; el informe no remite a .superpowers/ (pega el conteo de la suite y el EXIT en el propio informe); y en experimentos/porton_memoria.py, antes de `git worktree add`, correr `git worktree prune` para tolerar un worktree huerfano.

## Lo que NO se toca (rulings del controlador, en el ledger)
- La confabulacion de 'libro' (episodio inventado que vuelve etiquetado) y la subida de confabula en 'presupuesto' (ruteo memoria/chats): hallazgo h07 para Pedro, otra tanda.
- El presupuesto por sub-bloque del abismo (ruling 2).
- La letra de las vinetas y los topes (rulings 8 y 9).
