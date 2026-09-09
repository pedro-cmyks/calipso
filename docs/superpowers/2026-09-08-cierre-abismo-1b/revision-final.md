# Revision final de merge -- feat/abismo-1b (c645ccd..745a7d8)

Revisor: lente de merge (rama entera contra spec, calidad, arquitectura, tests, produccion).
Fecha: 2026-09-08. Rama `feat/abismo-1b` (HEAD 745a7d8) sobre main c645ccd. 21 commits, 38 archivos,
+2978/-105.

## Veredicto: With fixes

Una ola corta cierra lo que frena el merge: un bug real de truncado silencioso en la ruta one-shot
(Important, confirmado con sonda) y tres minors del ledger que son baratos y guardan justamente el
codigo que esa ola va a tocar. Todo lo demas es pulido o queda condicionado al smoke, como ya lo
dejo el ruling 1 del controlador.

## Metodo

- Leido: contexto-13.md, global-constraints.md, progress.md (ledger completo), el spec entero
  (autoridad, 206 lineas), contexto-comun.md, task-13-brief.md, y el paquete entero
  (`review-c645ccd..745a7d8.diff`, 4709 lineas, en ocho pasadas: paquete puro, server.py en tres,
  UIs en dos, tests en dos).
- Verificado en el checkout lo que el diff no muestra: la compuerta /nube (`mensaje_saliente`),
  los tres `apagada = True`, los dos fallbacks completos, el cierre del turno (cobro, telemetry,
  `mem.remember`, `chats.append`, `done`), el `Filtro` de foco, `_subscription_invocation` y su
  cleanup, `_history_messages`, `_should_orchestrate`, los llamadores de `internal_contract` /
  `_build_context`, el borrador (`emisor_b`), `addDetail`/`addMsg` de la PWA, `.oculto` de la
  fabrica, `catastro._cargar_json`, y `num_ctx` en los otros llamadores de Ollama.
- Corrido: los 16 archivos de test del abismo + mapa (131 passed, EXIT 0); node desde
  `calipso/web/fabrica/` (412 pass). Dos sondas propias FUERA del arbol (borradas al terminar):
  `sonda_filtro.py` (propiedades del filtro bajo TODAS las particiones en 1..3 trozos de 14
  textos: 4 passed) y `sonda_cableado.py` sobre el harness (A one-shot con empalme anidado: FALLA,
  es el hallazgo 1; B orquestador con marca valida: pasa; C /api con reentrada que revienta y
  fallback local que emite marca: pasa).
- Nada mutado: ni arbol, ni indice, ni ramas; sin tocar el server desechable del otro agente.

## Alineacion con el spec (promesa por promesa, resumido)

| Seccion | Promesa | Estado |
|---|---|---|
| 4 filtro | lista ordenada de filtros (foco, abismo); retencion decide con `parsear`; inconclusa se retira con aviso; el bucle cierra el generador tras cada chunk | Hecho: `Emisor.filtros` (server.py:7404-7496), `FiltroAbismo` (filtro.py), corte en `marca_abismo()` (server.py:3762). Retencion 409 y no 168: desvio declarado en las constraints. |
| 4 reentrada | estado del turno junto al de conexion; solo un mensaje real resetea; salteos por enumeracion; prompt con bloques post-compile + "venias diciendo" por una sola via; un solo par persistido; `num_ctx` explicito | Hecho: `estado_abismo` (:3258, reset :3285), `CHAT_NUM_CTX` (:2819/:2887), `prompt_reentrada` (turno.py:55). Los salteos estan MEDIDOS (`test_la_pasada_sintetica_no_repite_nada_del_turno`). |
| 4 flujo/rutas | local/api en vivo; suscripcion one-shot con preview congelado y reinvocacion declarada; orquestador fuera con retiro y aviso; tope 3 con dos regimenes | Hecho: bucle exterior (:3705-3800), one-shot (:3620-3697), `congelar` (:3066), `_retirar_con_aviso` (:7391), `puede_cortar`. Tests de tope en las dos rutas. |
| 5 contrato | sintaxis + indice en el contrato interno, techo 600 | Hecho: `internal_contract` con `catastro.nombres()` (sin escaneo); `bloque_contrato` nunca rebana el cierre (T12). |
| 6 zona | consolidado personal solo en zona personal | Hecho: `_zona_del_chat` / `_consolidado_personal` (:7523-7546), test con tres departamentos. |
| 8 /nube | contrato sin nombres; UNA excepcion a la compuerta (el bloque del viaje); degradado avisado con `viaje`; sin bloque la nube sigue; suscripcion en /nube; venias diciendo crudo | Hecho: `_sistema_nube` (:2736), `preparar_viaje`, `mensaje_saliente` tapado en la reentrada (verificado en :3451/:3484), `tramos_crudos`. 8.4 por ruta: desvio declarado y escrito en el spec (ruling). |
| 9 senal | tres fases con cierre; UIs con renglon hermano; pulso `EVENTOS`+`CONOCIDOS` | Hecho, con test que acopla las dos listas y test de que el pulso cierra en `fallo`. |
| 10 steer | gana siempre; con el corte, durante la pesca, durante la reentrada; sin usar `pending` | Hecho y testeado en los cuatro momentos, con pausas deterministas (`_pausar_el_modelo`). |
| 11 bordes | abierta al fin; chats.json limpio; modos con pipeline propio afuera; goals no | Hecho: el borrador usa `preparar_borrador` (sin contrato) y `Emisor(ws)` (sin filtro): verificado (:3383-3386). `_build_context` solo entra por `_sistema_del_turno` (:2758). |
| 13 invariantes | 1-9 | Sin fuga encontrada. Ver "Privacidad" abajo. |
| 15 verificacion | harness de ws_chat, viaje en aislado, /nube con modelo falso, canario de crudos, done unico, preview congelado | Hecho. El done unico se afirma de verdad solo en test_abismo_nube (`_turno_con_un_solo_done`); en test_abismo_chat sigue vacuo (ledger T8). |

## Privacidad (lo que mire con intencion)

- Nada sale a la nube sin viaje: `estado.bloques` se llena SOLO en `_pescar_abismo` (:7613) despues
  de `preparar_viaje`, y entra al envio SOLO por `prompt_reentrada`. El mensaje de la reentrada es
  `mensaje_saliente` (tapado, :3484); el system base de /nube es `_sistema_nube()` sin nombres.
- Nada se persiste: `full` es lo visible ya filtrado; `chats.append` y `mem.remember` lo usan tal
  cual (:3985-3994); `output.txt`/`partial-output.txt`/`msg` de jobs pasan por `_limpiar_marcas`
  (:3107, :3135, :3143, :3159). El pulso lleva `tamano`, nunca el bloque (afirmado por conjunto
  exacto de claves). Telemetry lleva clase/largo/cantidad/chars, jamas el cuerpo. Los temporales
  del CLI (system con el bloque) se borran en las dos invocaciones (test con espia de
  `NamedTemporaryFile`). Queda `stderr.txt` crudo (ledger T7; ver triage).
- Steer: no se pierde en ningun momento; la sonda C confirma ademas que una reentrada que revienta
  cae al fallback local sin truncar, con un solo `done`, y que el fallback no consulta.
- `done` unico por construccion (esta fuera del bucle exterior); la sonda B y C lo confirman en
  orquestador y fallback.

## Hallazgos

### Important

**1. One-shot: un `⟦abismo:` abierto antes de la primera marca valida traga la reentrada entera
(y el turno no persiste ningun `assistant`).** server.py:3648-3657 con filtro.py:85.

`cortar_en_marca` (turno.py:97) corta en la primera marca que `PATRON` acepta. Como `PATRON` no
admite `⟦` en el cuerpo (T2, a proposito), en un empalme anidado -`⟦abismo:⟦abismo:chats libro⟧ ...`,
el mismo texto que `test_las_dos_rutas_de_retiro_juzgan_igual_el_empalme` trata como caso real- la
primera valida es la INTERNA y `tramo_crudo` queda en `⟦abismo:` (abierto, sin cierre). Ese tramo
pasa por `emisor.chunk` (:3657) y el `FiltroAbismo` lo RETIENE (filtro.py:85, hasta 409 chars)
esperando un cierre que en la ruta one-shot nunca va a llegar dentro de esa invocacion. La retencion
es estado del filtro y sobrevive a la vuelta del bucle: la pesca corre, el CLI se reinvoca (dos
invocaciones reales, cobradas), y el texto de la reentrada se pega DETRAS de `⟦abismo:` retenido ->
`comer` lo retiene entero -> `emisor.cerrar()` al final lo descarta con aviso `abierta`.

Evidencia (sonda A sobre el harness, CLI falso con guion
`["⟦abismo:⟦abismo:chats libro⟧ chats y⟧ resto"]` y luego `["y sigo con contexto"]`):
`visible=''`, `fases=['pondering','pescado']`, `llamadas=2`, `avisos=[('abierta', 27)]`
(27 = `⟦abismo:` + "y sigo con contexto"), `persistido=['/claude libro']` (sin `assistant`).
Ademas `tramos_crudos` guardo `⟦abismo:` (:3666, `retirar_marcas` no toca una abierta), asi que el
"Venias diciendo" que volvio al modelo fue `Venias diciendo: ⟦abismo:`.

Por que Important y no Critical: exige que el modelo abra una marca y, sin cerrarla, emita otra
valida (un empalme que el 7b/CLI produce raramente); pero cuando ocurre la perdida es total y muda,
cuesta una reinvocacion de suscripcion, y rompe la promesa del par persistido. Es exactamente la
clase de falla que el ledger pedia mirar ("el bucle one-shot nunca consume `emisor.marca_abismo()`":
la causa real no es una marca pendiente sino la retencion de un prefijo abierto).

Fix propuesto (chico, en la ola): en la ruta one-shot el texto llega ENTERO, asi que no hay nada que
retener entre iteraciones: despues de `visible = await emisor.chunk(visible)` (:3657) volcar la
tuberia con `visible += await emisor.cerrar()` (es lo que ya hace el final del turno en :3913:
prefijo suelto se ve, marca abierta se descarta con aviso `abierta`, spec seccion 11). Y aplicar
`abismo_turno.recortar_abierta(tramo_crudo)` antes de `tramos_crudos.append` (:3666) para que el
modelo no reciba `⟦abismo:` en el "venias diciendo". Hacer lo mismo con `resto_crudo` (:3686) no
hace falta: ahi `emisor.cerrar()` del final ya lo cubre. Test: el guion de la sonda A, afirmando
`"y sigo con contexto" in texto_visible`, el `assistant` persistido y el aviso `abierta` de la fila
de telemetry con `largo == len("⟦abismo:")`.

### Minor (nuevos de esta revision)

**2. Streaming muestra crudo un `⟦abismo:zzz ` abierto seguido de una valida.**
`test_un_corchete_anidado_no_secuestra_la_marca_siguiente` afirma `"x ⟦abismo:zzz "` como visible.
Es coherente con `PATRON` (fallo cerrado: no es marca) y con foco, pero tras el fix 1 las dos rutas
volverian a juzgar distinto el mismo empalme (one-shot lo descarta con aviso, streaming lo muestra).
Cosmetico; dejarlo escrito en el ledger, no tocar en la ola.

**3. El fallback entre suscripciones REASIGNA `full` en vez de acumular** (server.py:3837
`full, queued = await _run_subscription_text_live(...)`; el fallback local si acumula, :3905).
Linea preexistente, pero con el abismo el estado "full no vacio + excepcion en la ruta de
suscripcion" pasa a ser alcanzable: primera invocacion OK (tramo ya en `full` y en pantalla),
la REINVOCACION falla (exit != 0, por ejemplo cuota del CLI: dos invocaciones por consulta duplican
la chance), hay cliente alterno -> `full` queda solo con el texto del alterno. Pedro vio tramo +
respuesta del alterno; `chats.json` guarda solo la del alterno. Dos lineas
(`texto_fb, queued = ...; full += ...`); recomendado en la ola si se toca ese bloque, no frena.

**4. `_pescar_abismo` imprime `exc` a stderr** (server.py:7597): el mensaje de una excepcion de
fuente puede llevar la pregunta de la marca. stderr del proceso no es un sumidero de Calipso
(server.log / journal, local), pero es el unico lugar donde el cuerpo puede terminar escrito. Al
ledger; alternativa: `type(exc).__name__`.

**5. `usage["completion_tokens"]` del one-shot cuenta el texto descartado tras la marca** (:3644,
`len(texto.split())` sobre `texto` entero). Subfacturacion inversa a la declarada de api. Al ledger.

**6. `num_ctx`: juez 4096 (juez_llm.py:65) contra 8192 del chat y de `_pensar_local`.** Si Ollama
recarga el runner cuando cambia `num_ctx` (lo hace en las versiones que comparan opciones), cada
turno /nube (juez del mensaje + juez del bloque) alterna con los turnos locales y paga recargas del
7b en la Ally. Preexistente en clase (main tenia default vs 4096), pero el smoke ya mide latencias
reales: anotar el numero. Puede esperar.

**7. El detalle del viaje en la PWA es un `details` con `esc()`, y en la fabrica un `pre` por
`textContent`: bien.** Lo unico: `addMsg("meta", textoDeAbismo(m))` deja un `meta` en el DOM entre
la burbuja y su continuacion (index.html:2364); es un meta, no un turno, y `botEl` no se toca: la
burbuja sigue siendo una. Conforme al ruling 11. Sin accion.

## Triage de los "minor (deferred)" del ledger marcados CANDIDATO AL FIX FINAL

### DEBEN cerrarse antes del merge

- **T6:** "los cuatro `estado_abismo.apagada = True` (:3587,:3599,:3739,:3791) SIN test y con modo
  de falla silencioso (una marca valida truncaria la respuesta en rutas que no reentran) --
  CANDIDATO AL FIX FINAL: test de suscripcion/orquestador con marca que igual emite el texto
  entero". Razon: hoy son tres (:3618 orquestador, :3836 y :3888 fallbacks; el de suscripcion lo
  reemplazo la T7) y estan bien, pero la ola de fix va a tocar el bucle one-shot (hallazgo 1) y sin
  guarda una regresion ahi es muda (el texto se trunca, ningun test se pone rojo). Las sondas B y C
  son el molde y pasan verdes hoy: ~40 lineas en test_abismo_chat.py (orquestador:
  `_should_orchestrate` -> True y `_run_dynamic_team` falso con marca valida; fallback:
  `_sse_text_chunks` que revienta en la segunda llamada y `_ollama_chat_chunks` con marca valida;
  afirmar texto entero, `abismo == []` o `[pondering, pescado]` segun el caso, `retirada`
  `sin_corte`, un `done`).
- **T7:** "stderr.txt de jobs sigue crudo (unico sumidero sin _limpiar_marcas; :3110,:3146,:3161)
  -- CANDIDATO AL FIX FINAL (una linea)". Razon: cierra la clase "la marca jamas se persiste" en el
  unico sumidero de disco que queda; un `_limpiar_marcas(stderr)` por sitio (tres lineas). Nota: el
  BLOQUE no lo cubre (un CLI que volcara el system en stderr lo dejaria ahi), pero ningun CLI real
  lo hace y el archivo es local a jobs; con la marca cerrada, alcanza.
- **T1:** "`Harness.recibir` sin plazo (un `done` perdido CUELGA la suite; molde de arreglo: hilo
  demonio + join(plazo) en test_sesiones_server.py ~1035)". Razon: el molde ya existe en el propio
  paquete (`_lo_que_siga`, test_abismo_nube.py:19), el harness lo importan tres archivos, y la ola
  agrega tests sobre el (T6 y el del hallazgo 1): un `done` de menos tiene que ser un rojo con
  mensaje, no un cuelgue del ritual de merge que el controlador corre a mano. ~10 lineas.

### Pueden esperar (al ledger.md con nombre y dueno)

- **T8:** "la senal `pescado` con `viaje` NO se afirma en la ruta de suscripcion (solo en /nube
  /api) -- CANDIDATO AL FIX FINAL". Razon: `viaje` lo arma `_pescar_abismo` (:7614-7618), la misma
  funcion para todas las rutas, y ya se afirma en /nube /api con el marcador exacto. Dos asserts en
  `test_en_nube_por_suscripcion_los_tramos_vuelven_crudos` (:171) son gratis si la ola toca ese
  archivo; no guardan nada nuevo.
- **T5:** "`test_privacidad_nube_system.py` se compara contra si mismo (`assert resultado ==
  srv._sistema_nube()`) -- candidato al fix final: afirmar sobre el contenido". Razon: el contenido
  ya se afirma en `test_abismo_contrato_vivo.py::test_el_system_de_nube_lleva_el_contrato_sin_nombres`
  (contrato sin nombres, sin "calipso"/"atlas", con "[TIPO_N]") y el test viejo suma
  `startswith(_SISTEMA_NUBE_MINIMO)`. Cerrado en la practica.
- **T10:** "hueco visual entre `pescado` y el primer chunk de la reentrada (no se re-emite
  `thinking`; arreglo barato: startThinking() al cerrar el renglon) -- CANDIDATO AL FIX FINAL si el
  smoke lo confirma". Razon: ruling 1 lo condiciona al smoke; es UX, no invariante.
- **T11:** "`pintarAbismo` no limpia `viajeAbismoTexto` al apagarse -- CANDIDATO AL FIX FINAL (texto
  tapado del turno anterior queda en el DOM)". Razon: `.oculto` es `display:none !important`
  (estilo.css:177): el texto viejo es invisible, se reemplaza en el proximo `pescado` y es DOM local
  de Pedro (no una fuga); ruling 1 lo condiciona al smoke. Si el smoke lo ve, es una linea
  (`viajeAbismoTexto.textContent = ""` en la rama `!a` de app.js:1116).
- El resto de los minors del ledger (momento="pesca" para dos situaciones, barge-in triplicado,
  bool de `_pescar_abismo` que el streaming no lee, fila `pescado` sin test de campos, guardia del
  pulso repetida, `ABISMO_VERBOS` duplicado, test_ui por substrings, tmp huerfano del banco, el
  primer test de suscripcion acoplado al reloj, `memoria` sin ambito, `/nube /api` sin reponer,
  steer JSON crudo a `pending`, el foco cosechado del texto descartado): al ledger, sin accion.

## Lo bien hecho

- **El harness (T1) es el molde que faltaba y esta bien construido:** socket real por TestClient,
  modelo espia por invocacion que anota payloads, ruteo forzado con el parser REAL de directivas
  (asi `/nube`, `/api`, `/claude` significan lo mismo que en produccion), y el steer en cuatro
  momentos con pausas deterministas (`_pausar_el_modelo`) en vez de dormir a ciegas.
- **El filtro es correcto bajo toda particion:** mi sonda corrio tres propiedades (transparencia
  byte a byte, corte identico, ningun empalme deja marca) contra TODAS las particiones en 1..3
  trozos de 14 textos; `PATRON` y filtro juzgan igual; `_retirar_abismo` va a punto fijo con un
  tope de seguridad razonado en el docstring.
- **La reentrada como bucle exterior:** los catorce salteos salen gratis por construccion, y hay un
  test que los MIDE (`_decide`, `goals.detect`, `_sistema_del_turno`, `_cobrar_turno` una vez;
  `thinking`/`meta`/`cost`/`done` una vez; un escritorio del pulso).
- **Privacidad cuidada hasta el detalle:** `mensaje_saliente` tapado en la reentrada; crudos con
  marcadores de vuelta a la nube (canario "Marta"/"[ID_1]" en suscripcion); el mapa compartido de la
  conversacion (`[ID_2]` para Ana, con el test que explica por que); el pulso con conjunto exacto de
  claves; la linea `_NUBE_ABISMO_MARCADORES`; los temporales de las dos invocaciones borrados; `msg`
  del CLI limpio porque va a tres sumideros.
- **Fallo cerrado de verdad:** `_pescar_abismo` envuelve TODO y corre el juez en hilo; la sonda C
  muestra que una reentrada que revienta cae al fallback local sin truncar, un `done`, y sin
  consultar.
- **`/stop` como segundo valor de `_run_subscription_text_live`** con los cuatro llamadores
  revisados y el orquestador filtrando.
- **UIs:** reductor puro de la fabrica con `n` para el reloj y sin turno; la guarda de `textContent`
  que protege la seleccion durante la reentrada, con un test que CUENTA escrituras; techo 30vh al
  detalle; la PWA cierra en done/error/steered/onclose/renderHistory; `sw.js` v4 y el test del SHELL
  acoplan la fabrica.
- **Los desvios estan declarados donde corresponde:** retencion 409, 8.4 por ruta escrito en el
  spec, subfacturacion api, dos invocaciones en suscripcion, cola honesta del contrato.

## Produccion (lo que el smoke tiene que mirar ademas de su guion)

- `num_ctx` 8192 en cada turno local (RAM de la Ally) y la alternancia con el juez a 4096 (hallazgo 6).
- El costo declarado en suscripcion: hasta 4 invocaciones por turno (3 consultas); el label
  "(reentrada del abismo N)" en el panel de jobs.
- La PWA offline con SHELL v4: todos los archivos tocados estan en el SHELL (test_mapa_server).

## Sondas (borradas)

- `scratchpad/sonda_filtro.py`: 4 passed.
- `scratchpad/sonda_cableado.py`: A FAILED (hallazgo 1), B y C passed.
