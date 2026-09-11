# SDD ledger — plan: docs/superpowers/plans/2026-09-10-aduana.md

Rama: feat/aduana desde main 4aff94f (BASE inicial 4aff94f45dff714c9dfebf9bde0a865314c6cde1). Spec: docs/superpowers/specs/2026-09-10-aduana-design.md.
Metodo: cada task = implementador (opus) -> revisor (opus) -> hasta 3 rondas de fix (fixer opus + re-review sonnet), orquestado por Workflow; el controlador adjudica lo que queda abierto.

## Preflight (2026-09-10 22:40)

Los tres criticos del plan (cobertura, placeholders/firmas, factibilidad con sondas) ya hicieron el barrido cruzado; el corrector aplico 18 correcciones (seccion "Correcciones tras la critica" del plan). Tabla del controlador:

| par / task | produce vs consume | hallazgo |
|---|---|---|
| T1 -> T2..T7 | aduana.Quien(kw_only: origen, proyecto, desde obligatorios), cruzar(quien, proposito, destino, carga=None), Cuerpo, declarar, declarar_una_vez(clave,...), leer, recortar_para_tablero; harness libro/quien_de_prueba/cruces_del_libro/EspiaTelemetria | firmas identicas en T3-T7 (self-review 3 del plan) |
| T2 -> T3..T6 | EXCEPCIONES con pendiente: Task N; cada task borra las suyas; test_no_quedan_pendientes en T6 | consistente (correccion 3) |
| T3 -> T4..T7 | _desde_de_sesion(sesion), _quien_http(request, origen, endpoint, **campos) | usados igual en T4-T6 |
| T4 -> T5/T6 | _gesto_de(directives); quien_turno en ws_chat; firmas web/browser/deps con quien | test_seguridad_git_blindado se actualiza en T5, no en T4: ok |
| T6 -> T7 | declarados no cambian la forma del libro | ok |
| T7 -> T8 | GET /api/aduana {cruces, totales{por_origen,por_destino,por_proyecto,por_desde,declarados}, sin_libro, ilegibles} = lo que consume textoDeAduana | ok |
| T9 | destino 'afuera' (server 2 lineas + viaje.py + viaje_info); no toca anillos.py | ok; ruling 11 del plan (fallar cerrado tambien en Ollama es de Pedro: NO) |
| server.py lineas | el plan cita e924ed9 -> hoy con corrimientos; anclas por simbolo | ok |

Ruling: T9 se parte: el CODIGO (viaje.py, server destino afuera, tests) lo hace el workflow; el SMOKE en vivo y el cierre los hace el controlador (necesitan Ollama y un server desechable) — el smoke no se delega para no exponer a un agente a la red con datos reales.

## Ejecucion (workflow sdd-aduana, 2026-09-10 22:45 -> 2026-09-11 01:23; 24 agentes)

Task 1: fix round 1/5 (1 addressed, 0 open -- _destino/sanear_url reventaba con URL malformada: fail-open [SECRETO]; commits 4c26779..b8185f1)
Task 1: complete (commits 4aff94f..b8185f1, review clean tras fix; 9 minors deferred: ts no-str en leer, ruta del disco en ultimo_error, entro() sin proteccion, motivo sin saneo, leer sin guard de loop, saneo del cuerpo entero, copia de _endurecer, dos detalles de tests, contadores sin lock)
Task 2: fix round 1/5 (2 addressed, 0 open -- salida pasada por referencia; guardia de la decision 13 con controles positivos; commits faef4e3..fcbd05e)
Task 2: complete (commits b8185f1..fcbd05e, review clean tras fix; 6 minors deferred: helper: verifica Call generico, sobrantes salta helper:, exclusion /web/ profunda, alias por archivo, doble parseo, regla envolvente sin test)
Task 3: complete (commits fcbd05e..799fa3b, review clean; 3 minors deferred: proyecto vacio con ROOT=/, carga cableada al molde de npm, imports sin uso)
Task 4: complete (commits 799fa3b..9d2c562, review clean; 5 minors deferred: proposito heuristica por gesto, TypeError de Quien antes del yield, before_after_capture sin verificar loopback, /model <token> en gesto sin saneo, docstrings viejos)
Task 5: fix round 1/5 (1 addressed, 0 open -- GIT_DE_RED con falsos negativos: parser de opciones globales + lista de porcelana de red; commits 8833c1a..af81819)
Task 5: Ruling: el fix extendio GIT_DE_RED mas alla de la tupla literal del ruling 7 del plan (fetch, push, pull, clone, ls-remote) sumando submodule, svn, lfs, p4, request-pull, send-email, imap-send, fetch-pack, send-pack, http-fetch, http-push, remote update/prune/show/set-head y archive --remote -- RATIFICADO: el spec seccion 7 dice "git cruza SOLO con subcomando de red" y la tupla era una enumeracion, no una politica; la lista negra honesta cumple la letra y el espiritu; la inversion a lista blanca NO se aplico (haria cruzar stash/checkout). Costo si esta mal: una linea de mas en el libro por un subcomando local mal clasificado. Se anota en el spec seccion 7 al cerrar.
Task 5: complete (commits 9d2c562..af81819, review clean tras fix; 3 minors deferred: URL scp-like como nombre nominal, git inicial tolerado solo en el clasificador, quien mal tipado detectado recien en el with)
Task 6: complete (commits af81819..9ed4f57, review clean; 5 minors deferred: urlsplit sin fail-open en _declarar_modelos_fuera, loopback por tres literales, quien sin anotacion en reflect, test de reflect sin afirmar orden, POST /api/transcribe sin test de cableado)
Task 7: complete (commits 9ed4f57..7da7eb2, review clean; 3 minors deferred: desde/hasta/origen sin validar, test de navegador no separa sesion de host, .json() sin afirmar 200)
Task 8: complete (commits 7da7eb2..38f3a60, review clean; 2 minors deferred: especificidad CSS de .hora, filtro recordado con clave ausente)
Task 9 (codigo): complete (commits 38f3a60..cd4ee5d, review clean; 3 minors deferred: derivacion de destino duplicada en dos ramas, 'afuera' no documentado en el spec del abismo, rama api->afuera sin test end-to-end)
Task 9: Ruling: el detector completo (con _HEX y _TOKEN por entropia) sobre el bloque en destino `afuera` sobre-tapa (un SHA de 40 hex, una ruta larga con fecha o una URL de GitHub cortan el envio entero con motivo credencial) -- SE MANTIENE tal cual: es la misma conducta que /nube tiene hoy con el mismo detector (regla del 09-02: credencial = fallo cerrado del envio entero), fallar cerrado de mas no fuga nada (el turno sigue sin el bloque, con senal `fallo`), y afinar el detector afecta a /nube tambien: otra tanda, con banco. Costo si esta mal: menos consultas utiles al abismo en turnos de suscripcion/API sin /nube. El smoke lo ejercita y lo documenta.
Task 9 (smoke + cierre): pendiente, del controlador.

## Cierre de rama (2026-09-11, 01:30 -> 02:40)

Task 9 (smoke): complete -- docs/superpowers/2026-09-10-smoke-aduana.md, 8/8 PASA, mas dos sondas del destino afuera (URL de GitHub: viaja; SHA de 40 hex: fallo credencial = costo del ruling 9). Efecto lateral encontrado: test_chat_live.py se ejecutaba al importar y un agente de la revision le mando "-q" al server REAL (turno basura 01:42:55 en el chat "que proyectos tengo?..."); arreglado en la ola de fix (punto 12); los datos basura ya escritos son de Pedro.
Revision final (opus) + 3 lentes con sondas (eficacia, regresiones, completitud) + Codex gpt-5.5: 0 criticos, 7 importantes (3 de docs: lista de git en el spec, 'afuera' en el spec del abismo, informe del smoke; 4 de codigo: Lock entre hilos, proyecto vacio con ROOT=/, urlsplit sin fail-open, argv con URL sin sanear), 26 menores; los revisores pidieron cerrar antes del merge 8 menores (ts no-str, motivo/proposito/gesto sin saneo, ruta en ultimo_error, query sin =, before_after_capture loopback, motivos del canario x2, test_chat_live).
Ola de fix (una sola, 9 commits cd4ee5d..db88602) + re-review (sonnet): 12/12 resueltos, 1 menor nuevo parkeado (condicion muerta en leer(), aduana.py:515-519).
Ruling: el umbral de 'segmento corto' de la query sin '=' quedo en 1-12 caracteres alfanumericos (eleccion del implementador, ratificada: un token de 13+ sin '=' se tapa entero; costo si esta mal: un valor corto legitimo tapado de mas, que se ve y se afina).
Ruling: el motivo de la excepcion de discovery._get_json dice "loopback por default" (discover() usa el default hardcodeado, no CONFIG): honesto; si algun dia discover lee CONFIG, entra al declarado de arranque. 
Minors diferidos que quedan (con dueno: otra tanda): entro() sin try; leer() bajo candado bloqueante (a proposito); /web/ por substring en el canario; derivacion de destino duplicada en dos ramas de ws_chat; el canario es ciego a rebinding/os.system (documentado); recorte del tablero mas ancho que la enumeracion literal (decision 14, para Pedro); pr con titulo + 2 lineas (ruling 12, para Pedro); el detector completo en afuera (ruling 9); helper: del canario verifica un Call generico; alias por archivo; regla envolvente sin test; proposito heuristica por gesto; TypeError de Quien antes del yield; especificidad CSS de .hora; filtro recordado con clave ausente; test de reflect sin afirmar orden; POST /api/transcribe sin test de cableado; desde/hasta/origen sin validar; test de navegador no separa sesion de host; .json() sin afirmar 200; URL scp-like como nombre nominal; git inicial tolerado solo en el clasificador; quien mal tipado detectado en el with; condicion muerta en leer().
Suite al cierre: pytest 1645 passed (base 1476 en main + 169), node 428 (base 412 + 16). Merge --no-ff a main.
