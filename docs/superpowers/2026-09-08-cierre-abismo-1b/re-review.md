# Re-revision de la ola de fix del cierre de `feat/abismo-1b`

Revision de LECTURA sobre el checkout (arbol, indice, HEAD y ramas intactos: `git status --porcelain` vacio al
entrar y al salir; ninguna sonda dentro del arbol de tests). Rango revisado: `82b2ede..7011b9b`, ocho commits,
16 archivos, +993/-95. HEAD de la rama al momento de esta revision: `7011b9b` (el `745a7d8` del brief era el HEAD
previo a la ola). Paquete: `.superpowers/sdd/2026-09-08-abismo-1b-cableado/review-82b2ede..7011b9b.diff`.
No se re-corrio la suite (el reporte trae la evidencia); una sola sonda focalizada, sobre funciones puras, ya
borrada.

## Veredicto por hallazgo

| Hallazgo | Veredicto | Donde se cierra |
|---|---|---|
| h01 one-shot traga la reentrada | ADDRESSED | server.py:3524-3529, :3682, :3690-3691 (+3 tests) |
| h02 el filtro del stream no llega a punto fijo | ADDRESSED | filtro.py:96-111 (+3 tests) |
| h03 la reinvocacion que falla cierra el turno mudo | ADDRESSED | server.py:3835/:3888/:3896, :3143 (+3 tests) |
| h04 la fuente `chats` pesca el chat activo y la pregunta | ADDRESSED | fuentes.py:52-81, consulta.py:45-60, server.py:3628 (+4 tests) |
| h05 el 7b local no emite la marca por su cuenta | NO ADDRESSED (medido y diferido a Pedro, spec 12) | `experimentos/consulta_abismo_posicion_produccion.md` |
| m1 los `apagada = True` sin test | ADDRESSED (con una salvedad) | 3 tests guardia; ver "nuevo" #2 |
| m2 `stderr.txt` de jobs crudo | ADDRESSED | server.py:3113, :3155, :3170 (+1 test) |
| m3 `Harness.recibir` sin plazo | ADDRESSED | test_abismo_chat.py:88-89, :143-171 (+1 test) |

### h01 -- ADDRESSED

Dos cambios, los dos verificados en el arbol:

1. `calipso/server.py:3528-3529`: `corta_el_filtro = (estado_abismo.puede_cortar if route != "subscription" else
   (lambda: False))`. En one-shot el `FiltroAbismo` ya no puede dejar una marca pendiente que nadie consuma
   (`emisor.marca_abismo()` no se llama en ese bucle): retira con aviso y el texto posterior vale. Esto cierra
   S11a (foco anidado en el cuerpo) y S11b (`reponer` que acorta una ilegible a valida).
2. `calipso/server.py:3682`: `visible += await emisor.cerrar()` justo despues del `emisor.chunk(visible)` del
   bucle. La retencion ya no sobrevive a la pesca ni a la reinvocacion: el `⟦abismo:` abierto se descarta ahi
   mismo con aviso `abierta` (spec 11) y la continuacion de la reentrada sale limpia. Esto cierra S3b.
   Ademas `estado_abismo.tramos_crudos.append(recortar_abierta(retirar_marcas(tramo_crudo)))` (:3690-3691): el
   "Venias diciendo" ya no lleva la marca a medias.

Traza del caso original (`x ⟦abismo:zzz ⟦abismo:chats libro⟧ fin` + `y sigo`) sobre el codigo actual:
`cortar_en_marca` corta en la valida, `tramo_crudo = "x ⟦abismo:zzz "`, `chunk` deja `"x "` y retiene el prefijo,
`cerrar()` lo descarta con `abierta/12`, `tramos_crudos = ["x "]`, la reinvocacion arranca con el filtro limpio y
`full == "x y sigo"`. Coincide con el test
`test_abismo_suscripcion.py::test_en_suscripcion_un_prefijo_abierto_antes_de_la_marca_no_traga_la_reentrada`,
que ademas afirma `"⟦" not in llamadas[1]["prompt"]`, el persistido, el done unico y la fila `("abierta", 12)`.

El tope de tres sigue decidiendose donde debe (`server.py:3665`, `estado_abismo.puede_cortar()` sobre el texto
crudo), asi que `test_en_suscripcion_la_cuarta_marca_no_corta` no se debilita.

Queda una divergencia declarada (ver "abierto" #1): con foco anidado en el cuerpo, streaming CONSULTA y one-shot
RETIRA. Es mejor que antes (antes one-shot perdia el resto del turno en silencio) pero sigue sin ser el mismo
juicio en las dos rutas (spec 4).

### h02 -- ADDRESSED

`calipso/abismo/filtro.py:96-111`: tras cada retiro (ilegible o `sin_corte`) el bucle rehace `buf` como
`"".join(visible) + resto` y vacia `visible`, releyendo hasta punto fijo. Termina siempre: cada vuelta saca al
menos una marca completa (>= `len(ABRE)+2` chars). Verificado en la sonda:
`a ⟦abismo:chats ⟦abismo:zzz nada⟧ libro⟧ b` con `puede_cortar=False` sale como `a  b` con avisos
`["ilegible", "sin_corte"]` y `marca.encontrar(visible) == []`; con `puede_cortar=True` corta en
`Marca(chats, libro)` y deja `a `.

Los tests correspondientes son reales, no cosmeticos: `EMPALMES` gana el tercer texto y
`test_las_dos_rutas_de_retiro_juzgan_igual_el_empalme` corre sobre los tres afirmando
`marca.encontrar(...) == []` por las dos rutas; `test_el_filtro_relee_el_empalme_hasta_punto_fijo` cubre entero
con corte, entero sin corte, partido en dos trozos y el empalme de dos vueltas; y
`test_abismo_chat.py::test_un_empalme_que_arma_una_marca_valida_no_llega_a_pedro_ni_a_disco` cierra el lazo por
el WS (`chats.json` sin `⟦`).

Residual verificado (abierto #2): `turno.retirar_marcas` (turno.py:117-120) sigue siendo una sola pasada de `sub`.

### h03 -- ADDRESSED

- `server.py:3835` `alterno_ok = False` al entrar al `except`; `:3888` `alterno_ok = True` justo antes del
  `raise StopIteration` del alterno; `:3896` `if not alterno_ok:` gobierna el fallback local. La rama
  `if full and used_route == "subscription": pass` ya no existe: un fallo de la SEGUNDA invocacion cae al
  fallback como cualquier suscripcion que revienta, con `meta`, fila en `fallbacks` y `route_used`.
- `server.py:3143-3148`: `{"type":"process","action":"failed", job_id, label, client, model, error}` con
  `error = _limpiar_marcas(stderr or partial or "")[:300]`. La PWA lo pinta (`index.html:2324-2326`); la
  fabrica no maneja `type:"process"` en absoluto (grep sobre `calipso/web/fabrica/*.js`: cero coincidencias), asi
  que lo ignora sin ruido.
- H4 pegado: el alterno ya no REASIGNA `full` (`texto_alterno` + `full += await emisor.chunk(...)`, :3868-3885) y
  `completion_tokens` acumula en vez de pisar. Lo persistido pasa a ser lo que Pedro leyo.

Los tres tests (U1 sin alterno, U2 con alterno que tambien falla, H4 con alterno que responde) afirman el visible,
el persistido, el done unico, la lista de `note` de las metas, la cuenta de invocaciones y las filas de fallback.
Verifique tambien que `full` sigue vacio cuando la PRIMERA invocacion falla (el `full +=` es equivalente al
`full =` de antes en ese camino), asi que el fallback clasico no cambia de conducta.

### h04 -- ADDRESSED

`fuentes.chats_viejos(resto, *, chat_activo=None, en_contexto=0)` (fuentes.py:52-81) recorta el chat activo:
`mensajes[:len(mensajes) - max(0, en_contexto)]` (verificado el borde `en_contexto > len(mensajes)` -> lista
vacia, no un `[:-N]` que devuelva de mas), y `en_contexto=None` lo saca entero. `consulta.resolver` reenvia
(consulta.py:45-60) y `_pescar_abismo` calcula `en_contexto = None if destino == "nube" else _HISTORY_TURNS + 1`
(server.py:3628) con `chat_activo=chat_id`, que los dos llamadores le pasan (:3702, :3820).

El `_HISTORY_TURNS + 1` es exacto contra `_history_messages` (server.py:2833-2834: `msgs[:-1][-12:]`, o sea 12
mensajes previos mas el actual = 13). El default `chat_activo=None` deja intactos los tests del 1a.

(b) del hallazgo: con `destino == "nube"` (que coincide con `chat_id_nube=None`) el chat activo queda fuera
ENTERO, asi que un turno LOCAL previo de la misma conversacion ya no viaja por el bloque.
`test_abismo_nube.py::test_en_nube_un_turno_local_previo_de_la_misma_conversacion_no_viaja_por_el_bloque` afirma
que "presto"/"cocina"/"Marta" no estan ni en los envios ni en `texto_tapado`, y que el chat viejo con Ana SI
viaja tapado (o sea que la fuente sigue sirviendo).

La conducta del juez que el smoke observo (tapa el nombre, deja pasar el dato de salud de la misma linea) es
Fase 2 y queda fuera: va a `out_of_scope`.

### h05 -- NO ADDRESSED (medido, diferido)

El defecto concreto sigue en pie: por la ruta local con el system de produccion el 7b no emite la marca. La ola
midio la hipotesis (posicion del bloque) con el protocolo del porton sobre el system REAL y la refuto: `actual`
2/12-6/12-2/12, `final` 5/12-5/12-2/12, `primero` 4/12-8/12-4/12, contra un control que reproduce el v2
(10/12-12/12-12/12). Ningun lugar llega al piso, y `chats` empeora al final. La evidencia esta archivada y es
reproducible (`experimentos/consulta_abismo_posicion.py`, con `CALIPSO_HOME` puesto ANTES del import y el home por
argv: cumple la restriccion global). El spec seccion 12 reserva explicitamente esta bifurcacion para Pedro, asi
que no aplicar es defendible -- pero el hallazgo no esta cerrado y va a `open`.

Hallazgo lateral de la propia medicion, que vale mas que la tabla: 22 de las 34 marcas legibles del CONTROL son la
copia literal del molde del contrato (`⟦abismo:memoria pregunta⟧`), validas para `parsear` e inutiles en
produccion. El 83/100/100 con el que el porton v2 desbloqueo el 1b esta inflado por el loro. Eso toca la premisa
del cierre, no solo el h05.

### m1 -- ADDRESSED (con salvedad)

Los tres `apagada = True` que quedan (server.py:3636 orquestador, :3870 fallback entre suscripciones, :3924
fallback local) tienen guardia. Dos son guardias de verdad:
`test_la_ruta_orquestador_retira_la_marca_sin_cortar_y_emite_el_texto_entero` (turno local, el filtro SI podria
cortar si faltara la linea) y `test_el_fallback_local_tras_un_corte_retira_la_marca_sin_cortar` (turno `/api`,
idem). La tercera (`test_el_fallback_entre_suscripciones_retira_la_marca_sin_cortar`) afirma la conducta correcta
pero ya no discrimina la linea 3870: ver "nuevo" #2.

### m2 -- ADDRESSED

Los tres sitios (`/stop` :3113, fallo :3155, exito :3170) escriben `_limpiar_marcas(stderr)`, y
`test_el_stderr_de_los_jobs_no_lleva_la_marca` los ejercita por dos caminos reales (el job que falla y el alterno
que termina) afirmando que el archivo existe, que no tiene `⟦` y que conserva el resto del texto. El `cli_falso`
gana `stderr`/`exit` por paso de forma compatible hacia atras.

### m3 -- ADDRESSED

`Harness.recibir(ws, hasta_dones=1, plazo=PLAZO=60)` corre en hilo demonio con `join(plazo)` y levanta
`AssertionError("en 60 s llegaron N de M done: [...]")`; una excepcion del socket se guarda y se re-lanza en el
test. `Harness.turno` drena `DRENAJE=0.25` s tras el ultimo done, con lo que `tipos.count("done") == 1` deja de
ser vacuo en TODO `test_abismo_chat.py` (cerraba de paso el T8). Revisado el riesgo de carrera: el hilo lector
termina antes de que `lo_que_siga` arranque el suyo (sale del `while` sin bloquear en un `receive_json` extra),
asi que no hay dos lectores sobre el mismo socket.

## Lo que la ola introdujo (new_breakage)

Ninguna regresion funcional. No se debilito ningun test: el `git diff` de los `test_*.py` no borra una sola linea
`assert`; lo unico que se toca de los viejos son los dobles `lambda resto:` -> `lambda resto, **kw:` (obligado por
la firma nueva) y el helper `_turno_con_un_solo_done` de nube, que pasa a apoyarse en el drenaje del harness. Sigue
habiendo un solo `done` por turno (afirmado explicitamente en los seis tests nuevos que lo tocan) y no sale nada
nuevo a la nube: h01 y h04 REDUCEN lo que viaja, y el alterno de h03 no lleva bloques (rearma el system con
`_sistema_del_turno` y manda `mensaje_saliente`, no `mensaje_turno`).

Dos cosas menores que la ola sí introdujo:

1. **Minor -- la fila `sin_corte` en one-shot pasa a significar dos cosas distintas.** Con
   `corta_el_filtro = lambda: False` para toda la ruta de suscripcion (server.py:3528), la telemetria ya no
   distingue "no corto porque el tope llego / la consulta esta apagada" de "no corto porque el detector no vio
   esta marca y el filtro si". Justo la clase de divergencia (foco anidado, `reponer`) que h01 pedia poder ver.
   Hay rastro, que es lo que faltaba, pero es ambiguo: una `clase` propia (p.ej. `solo_tuberia`) lo separaria en
   una linea.
2. **Minor -- una de las tres guardias de m1 quedo sin poder discriminar.** `apagada = True` en el fallback entre
   suscripciones (server.py:3870) ya no tiene efecto observable: en esa ruta el filtro no puede cortar de todos
   modos (`lambda: False` congelado en la construccion del Emisor) y ese fallback no pasa por el bucle one-shot,
   el unico otro lector de `estado_abismo.puede_cortar()`. Borrar la linea no pondria rojo
   `test_el_fallback_entre_suscripciones_retira_la_marca_sin_cortar`. La conducta visible sigue afirmada; lo que
   se perdio es el diente del test sobre esa linea.

## Abierto

1. **Divergencia declarada streaming/one-shot con foco anidado en el cuerpo** (spec 4 pide el mismo juicio en las
   dos rutas). Streaming consulta, one-shot retira con aviso. Ya no se pierde texto, que era lo grave, pero el
   juicio sigue sin coincidir. Igualarlo pide correr el detector sobre el texto post-foco/post-`reponer` y mapear
   el corte al crudo. Declarado en el reporte del fix (concern 3).
2. **`turno.retirar_marcas` es la unica ruta de retiro que no llega a punto fijo** (turno.py:117-120,
   `PATRON.sub` de una pasada), mientras `_retirar_abismo` (server.py:7400-7424) y ahora `FiltroAbismo.comer`
   si. Verificado con sonda: para `a ⟦abismo:chats ⟦abismo:zzz nada⟧ libro⟧ b` devuelve
   `a ⟦abismo:chats  libro⟧ b`, con la marca armada en pie. Alcance real: `tramos_crudos` del one-shot, o sea el
   "Venias diciendo" que se le manda de vuelta al CLI y, en `/nube`, a la nube. No se persiste en disco y nadie la
   interpreta (invariante 7 se sostiene), asi que es Minor -- pero es la misma familia que h02 y se cierra con la
   misma linea (`_retirar_abismo`-style).
3. **h05 sin resolver:** por la ruta local del dia a dia la promesa "ante la duda, CONSULTA" no se sostiene.
   Decision de Pedro (spec 12) con los numeros en la mano.
4. **La metrica del porton cuenta como legible la copia literal del molde** (22/34 en el control). El piso que
   desbloqueo el 1b esta inflado; re-medir con esa exclusion antes de decidir el punto 3.
5. **h04 toma una decision de producto que Pedro no confirmo:** en local, los mensajes del chat activo ANTERIORES
   a la ventana de 12 si se pescan; en `/nube` el activo queda fuera entero. Esta documentada en los docstrings y
   apoyada en la letra del spec 1, pero no estaba escrita en el spec.
6. **M6: tras una reinvocacion fallida el fallback local reempieza de cero** pegado al tramo que Pedro ya leyo
   (`mensaje_saliente`, sin bloques ni "venias diciendo"). Ahora esta avisado con meta y fila, pero "continuar, no
   regenerar" (spec 3) no se cumple en ese camino.
7. **La ventana excluida de `chats_viejos` es de mensajes CRUDOS, no de los que el modelo realmente ve.**
   `_history_messages` descarta los vacios y los de rol raro, y `chats_viejos` ademas saltea los que empiezan con
   `/`. Con gestos recientes en el chat, se excluyen de la pesca uno o dos mensajes reales que el modelo NO tiene.
   Es sobre-exclusion (nunca sub-), asi que es cosmetico.

## Fuera del alcance del fix

- **El juez de privacidad deja pasar el dato de salud tapando solo la identidad** (lo que el smoke vio en H5:
  `[ID_1] te presto el libro y esta en tratamiento`). Es conducta de la Fase 2, no del cableado del abismo; la ola
  cerro lo que era del abismo (la conversacion activa ya no viaja por el bloque). Va al ledger con dueno.
- `estado_abismo.tramos` (turno.py:43) se escribe en las dos rutas (server.py:3686, :3805) y no lo lee nadie:
  acumulador muerto, preexistente.
- La PWA no actualiza el `workItem` de la barra lateral en `process/failed` (queda "iniciado"), igual que ya pasa
  con `stopped`. Cosmetico y consistente con lo que habia.
- Los demas diferidos del ledger que la ola no toco: `pintarAbismo` que no limpia `viajeAbismoTexto`, el hueco
  visual entre `pescado` y el primer chunk de la reentrada, la subfacturacion api de la pasada cortada, el steer
  JSON crudo en `pending`, `memoria` sin ambito.

## Recomendacion

La ola cierra los cuatro Important accionables y los tres must-fix, con tests que fallan de verdad si se revierte
el codigo. Ninguna regresion. Mergeable como esta, con dos salvedades para el ledger antes de que el controlador
corra el ritual: el punto abierto 2 (`retirar_marcas` sin punto fijo, una linea) y el punto 4 (la metrica del
porton inflada), que es el que le cambia el peso a la decision del h05.
