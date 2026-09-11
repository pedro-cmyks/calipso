# SDD ledger — plan: docs/superpowers/plans/2026-09-11-memoria-procedencia.md

Rama: feat/memoria-procedencia desde main 279dfb0. Spec: docs/superpowers/specs/2026-09-11-memoria-con-procedencia-design.md.
Metodo: workflow sdd por task (implementador opus -> revisor opus -> hasta 3 rondas fix + re-review sonnet); cierre con revision final + lentes + Codex.

## Preflight (2026-09-11 04:05)

Los dos criticos del plan (cobertura+firmas, factibilidad con sondas) hicieron el barrido cruzado; el corrector aplico 10 correcciones. Pares: T1 -> T2..T5 (presentar_recuerdos(hits, tope, *, variante, con_score), partir, clasificar, VARIANTE_DEFAULT) consistentes; T2 -> T5 (el escritor con procedencia); T3 -> T5 (MEMORIA_PRESENTAR=off|A|B en los dos lectores, off sin score en fuentes); T4 (reindex) independiente; T5 consume todo.

Ruling (ruling 7 del plan, pedido ANTES de la Task 4): '--vista' con el server prendido SE PERMITE (solo '--aplicar' se niega, salvo --forzar). Razon: la vista es de solo lectura, dos clientes sobre el mismo directorio no corrompen (sondeado por la lente de factibilidad del spec), y Pedro necesita ver los conteos sin apagar el server. Costo si esta mal: un conteo de la vista que no incluya un episodio que el server escribe en ese instante; la letra del spec (seccion 3) se ajusta al cerrar: 'exige el server apagado para APLICAR'.
Ruling (ruling 11 del plan): la condicion 'antes' del porton se mide contra MAIN EXACTO (server desechable levantado desde un worktree de main, 'git worktree add <tmp>/calipso-main main', que se borra al terminar), no contra la rama con MEMORIA_PRESENTAR=off; A y B contra la rama. Costo: unos minutos mas de porton; a cambio el baseline es honesto.
Ruling (ruling 2 del plan): el presupuesto por sub-bloque del abismo NO se toca en esta rama (el corte en etiquetar queda como esta el spec); si el porton muestra que el sub-bloque recuerdos desborda y deja afuera core/cronologia, se anota como hallazgo para Pedro.

## Ejecucion (workflow sdd-memoria, 2026-09-11 04:10 -> 10:59; 10 agentes)

Task 1: complete (commits 279dfb0..bd4b35c, review clean; 6 minors deferred: tope<=0 devuelve 1 hit, texto vacio no se salta, variante invalida se comporta como B, enganche env->presentar sin test, _RELLENO sin \b, hedges fuera del banco)
Task 2: complete (commits bd4b35c..8f49266, review clean)
Task 3: complete (commits 8f49266..8eb001f, review clean)
Task 4: complete (commits 8eb001f..74c88f6, review clean)
Task 5: complete (commits 74c88f6..c31e8dd, review clean; DONE_WITH_CONCERNS: ruling 6 escalado; 5 minors: '5 de 5' vs 13 pescados, la adenda dice mergeada antes del merge, el cierre remite a .superpowers, resultados.md dice 'se aterriza A' vs cierre 'nada', worktree huerfano tras SIGKILL)
Task 5: Ruling (ruling 6 del plan): SE ATERRIZA A (VARIANTE_DEFAULT="A", como esta el codigo). Razon con los datos: el sintoma original (libro_rosa: repetir 'no tengo registros') pasa de 2/2 a 0/2 en A y B; la subida de confabula (2 -> 4) es ENTERA del caso presupuesto, donde la verdad vive solo en chats.json y el 7b consulta memoria (el desvio de ruteo conocido cha-decision, ruteo 88 del abismo); ahi B inventa ('quedamos en revisar los costos') y A parafrasea la frase fija ('no teniamos el dato del presupuesto registrado en ese momento, necesitas que busque?'), que es la respuesta mas honesta del porton aunque la metrica la clase como confabula. A gana en honestidad; el eco parafraseado NO es un dano (dice la verdad) pero hay que clasificarlo: se suma 'no teniamos (el|ese|ningun) dato' a los patrones fuertes con fila en el banco (ruling 1: se verifica 0 falsos). Costo si esta mal: un no-saber parafraseado mas que se presenta como 'Calipso contesto' hasta que el banco lo atrape.
Task 5: hallazgo para Pedro (h07, fuera de esta rama): el 7b se cree sus propias respuestas viejas aunque lleven la etiqueta 'Calipso contesto (local, fecha)' (la trilogia inventada de 'libro' vuelve 2/2 en todas las condiciones). La procedencia que falta es si esa respuesta salio CON el abismo consultado o SIN consultar (guardar `consultas` en el episodio y presentarlo: 'Calipso contesto (local, 2026-08-14, sin consultar)'). Y el ruling 2 del plan: los 13 pescados de memoria de A/B llegaron al techo de 2000 del bloque (el sub-bloque recuerdos desborda y deja afuera core/cronologia).

## Cierre (2026-09-11 11:05 -> 12:40)

Ola de fix 1 (4 puntos, commits c31e8dd..6bfff5e): 4/4 resueltos (re-review sonnet), sin roturas.
Revision final (opus) + lente eficacia con sondas sobre el fixture real: 0 criticos, 2 importantes (la variante off como interruptor muerto; el no-saber en pasado no atrapado), 9 menores.
Ruling: se saca la variante `off` (sobra desde el ruling 11; contradice la invariante 2). Costo si esta mal: ninguno en produccion; el porton ya no la usa.
Ruling: los fuertes NO reciben la clausula 'afirmativa con contenido antes' (rompe fixture[0]: 'Estare encantado de ayudarte... Actualmente no tengo ese dato'); queda parkeado con el caso catastro+fuerte, la coletilla y los hedges para una tanda post-merge con filas en el banco. Costo: un dato real seguido de un no-saber sobre OTRA cosa se presenta degradado; no se vio en 638 salidas reales.
Ruling: `reflect` sigue mandando episodios crudos (fuera del spec); la invariante 2 se acota en el spec.
Ola de fix 2 (4 puntos): ver cierre-fix-wave-2.md.
Ola de fix 2 (4 puntos, commits 6bfff5e..baeb1fc): 4/4 resueltos (re-review sonnet), sin roturas. Banco 30/31 (97%), 0/24 falsos. Suite 1700.
Minors diferidos post-merge (con dueno: otra tanda, con filas en el banco primero): hedges ("no recuerdo si te lo dije, pero X", "en ese momento no tenia el dato, pero ahora si"), catastro+fuerte, coletilla "¿correcto?", _RELLENO sin \b, la clausula afirmativa para fuertes; presupuesto por sub-bloque del abismo (ruling 2); h07 (consultas en el episodio); reflect con presentar.
Para Pedro: ratificar (o cambiar a B) el ruling 6 -- variante aterrizada A; correr el reindex del home real (--vista con el server prendido; --aplicar con el server apagado).
Merge --no-ff a main.
