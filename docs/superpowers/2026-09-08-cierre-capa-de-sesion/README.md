# Cierre de la rama feat/capa-de-sesion (2026-09-08)

El ritual de cierre de rama que el plan (`docs/superpowers/plans/2026-09-07-capa-de-sesion.md`,
Task 9) exige antes del merge, con sus informes tal cual los produjeron los agentes:

- `revision-final.md`: la revision de merge de la rama entera contra el spec, con el triage de los
  minors diferidos por tarea (cinco "deben cerrarse antes del merge", veinticinco "pueden esperar").
- `adversaria-eficacia.md`: ataque a los diez invariantes del spec con unas 160 sondas corridas de
  verdad (fuera del arbol de tests). Cedio H1: un navegador remoto leia el `id_pedido` de una
  aprobacion sin canjear y podia secuestrarla. Cerrado en `4588965`.
- `adversaria-regresiones.md`: que cambio para lo que ya funcionaba (Ally, Tauri, PWA local, primer
  arranque, freno, backups, tests). Cedio el boton "Abrir" del checklist a `/setup` a secas.
  Cerrado en `82638f9`.
- `adversaria-completitud.md`: tabla promesa por promesa del spec y del plan contra el codigo y los
  tests. Ninguna promesa falta; dos a medias (limpieza de la cookie-token remota, repintado que
  deshacia la eleccion del tipo). Cerradas en `27b4fe9` y `2e7bfe3`.

Los 30 hallazgos crudos de las cuatro fuentes mas el smoke se unificaron en 21; los Critical e
Important pasaron por tres refutadores independientes cada uno (ninguno cayo) y se cerraron en una
sola ola de fix (`416c70f..cfc1faa`) mas un fix acotado por la regresion que esa ola introdujo
(`0f20743..c21619f`). El smoke en vivo esta en `../2026-09-08-smoke-capa-de-sesion.md`.

Residuales que NO bloquean y quedan para Pedro: el primer arranque no tiene camino desde la UI (solo
`/setup?token=` leyendo el token a mano; la alternativa del spec es aceptar tambien la cookie-token
valida desde loopback en la regla 1 del guard); una aprobacion sin canjear vive 30 dias y no se puede
cancelar desde /fabrica; un host bajo castigo del freno recibe 429 tambien sondeando un id valido;
la pregunta de si el `tablero` deberia poder parar la fabrica (hoy no); y el paso de despliegue:
rotar el token y reiniciar el server (spec, seccion 3, "Despliegue de la fase 1").
