# Siembra guiada de la economia

**Fecha:** 2026-09-03
**Estado:** brainstorming cerrado con Pedro; listo para su revision
**Origen:** la economia de la fabrica esta toda construida y probada pero **nunca se sembro** (`~/.calipso/economia/` no existe). Sembrar es un acto de Pedro, irreversible (escritura unica; `Registro` no tiene baja). Ver [[project_calipso]] y [[project_calipso_abismo]].

## 1. Por que existe, y que descubrio la medicion

`sembrar` (`POST /api/economia/sembrar`) NO prende la fabrica: crea el **padron** (`departamentos.json`), `suscripciones.json`, y un **libro vacio** — nada mas (verificado: `server.py:4796-4833`, y `test_economia_sembrado.py:89` asserta el libro vacio). Prender la fabrica es una **secuencia de 7 pasos** sobre endpoints/primitivos que YA existen; no falta codigo de feature, falta orquestar la secuencia en el orden correcto, con los valores correctos, una sola vez y sin equivocarse — porque el padron se congela para siempre.

Ademas la medicion cerro dos cosas que se creian abiertas:
- **El color del ciclo (D1) ya esta en el codigo:** `cierre._rojo_de_ciclo` mide **aprovechamiento de la cuota**, no recaudacion (`cierre.py:287-291`, testeado). Solo el numero del piso (`PISO_APROVECHAMIENTO_PCT = 40`) es una propuesta ajustable, y el arranque en frio no da rojo (`cierre.py:284-286`). No bloquea la siembra.
- **Los "4 huecos" no son codigo que falte:** acuñar al tesoro (`kernel.acunar`), abrir la semana (`operacion.abrir_semana`), las perillas (`Registro.ajustar`), la rutina del jefe (`POST /api/routines` kind=departamento) y el switch `ensayo->vivo` (`interruptor.poner_modo`) ya existen. Son PASOS de la secuencia.

Este spec construye **un helper guiado de un solo tiro** que corre la secuencia con los valores confirmados, con una compuerta de confirmacion antes del acto irreversible, re-entrante (se puede volver a llamar para completar lo que falte), y ensayado en un home desechable antes de que Pedro toque su economia real.

## 2. Que decidio Pedro (brainstorming, 2026-09-03)

1. **El padron (irreversible), cerrado:** `taller`, `development`, `research` en fabrica (con jefe); `finanzas` en personal (sin jefe, obligatorio — el backend hardcodea `personal:finanzas` en `pagador.py:133-136`; sin el, los cargos personales se apilan en `cargos_pendientes.jsonl` para siempre).
2. **Leer NO es departamento — es el abismo.** No entra al padron. El lector consulta a Calipso pero no tiene billetera ni jefe; el "departamento con mis libros" del BRIEF pasa a ser un lugar del abismo, que se construye aparte. Sostiene la decision del abismo (la fabrica solo produce). Ver [[project_calipso_abismo]].
3. **Postura de seguridad para la primera corrida** (todo ajustable despues por perillas): montos conservadores; `techo_api_ciclo_mm = 0` a proposito (cada gasto de API por token pide firma de Pedro; la capacidad de suscripcion/cristal no se frena); `PISO_APROVECHAMIENTO_PCT` se queda en 40 (ajustable con un ciclo de datos reales).
4. **Ejecucion: un helper guiado de un solo tiro**, con confirmacion antes del paso irreversible. (Descartado: runbook manual — el orden importa y es irreversible, un helper testeado quita el riesgo de equivocarlo.)

## 3. Arquitectura

- **El endpoint guiado** (`POST /api/economia/sembrar-guiado`, nuevo en `server.py`): toma la config (padron fijo + montos + capital + la semana a abrir), corre los 7 pasos en orden, re-entrante. Sin token de confirmacion -> PREVIEW (no escribe nada, devuelve el plan). Con el token -> EJECUTA.
- **El orquestador** (`calipso/economia/siembra.py`, nuevo): funcion pura-de-efectos que, dado un pagador y la config, ejecuta/saltea cada paso segun el estado actual (idempotente/resumable) y devuelve un reporte paso-a-paso. Reusa los primitivos existentes (`Registro`, `kernel.acunar`, `operacion.abrir_semana`, `routines`, `interruptor`), no los reimplementa.
- **La UI minima** en `/fabrica`: una pantalla de siembra que muestra el PREVIEW (que se va a crear) y un boton de confirmar que manda el token. Es la parte fina; el nucleo es el endpoint.

La secuencia de 7 pasos (paso 1 es una precondicion, no lo corre el helper):

1. **(Precondicion, manual)** Levantar el server y dejar correr el probe de consumo, para que `capacidad_ciclo` de las suscripciones sea el numero medido y no la estimacion. El helper toma la `capacidad_ciclo` como dato de config (medido o provisto).
2. **Sembrar el padron** — `Registro.alta` por depto + `suscripciones.json` + libro vacio. **El acto irreversible.** Si `departamentos.json` ya existe, se saltea (ya sembrado).
3. **Abrir la primera semana** — `operacion.abrir_semana(k, ts, semana, cuota_firmable_mpt, reserva_personal_mpt, suscripciones)`: emite el `EMISION_PT` que hace la semana operativa. Si la semana ya esta abierta (hay `EMISION_PT` para ella), se saltea. Va ANTES de acuñar para que el capital caiga en una semana ya operativa (es el orden que usa el codigo de prueba que ya anda: `emitir_semana` y despues `acunar`).
4. **Acuñar capital al tesoro** — `kernel.acunar(ts, semana, "tesoro", capital_mm, SubtipoAcunacion.CAPITAL, {"tipo": "genesis"})`. Si el tesoro ya tiene saldo, se saltea. (Es el mint de genesis: lo autoriza la confirmacion de la siembra, no pasa por la frontera/permisos, que son para los mint ONGOING.)
5. **Poner las perillas** de cada depto de fabrica — `Registro.ajustar` con `presupuesto_semanal_mm`, `techo_preseed_mm`, `techo_preseed_ciclo_mm`, `techo_api_ciclo_mm=0`. Idempotente (se aplica a los valores objetivo).
6. **Una rutina `kind: departamento` por depto de fabrica** — via el mismo camino que `POST /api/routines`. Si ya existe la rutina de ese depto, se saltea.
7. **Pasar el plantel a `vivo`** — `interruptor.poner_modo(base, "vivo")`. Idempotente.

## 4. La compuerta de confirmacion (el acto irreversible)

El endpoint tiene dos modos, para que la siembra no se dispare por accidente:
- **PREVIEW** (sin `confirmacion` en el body): NO escribe nada. Devuelve el plan completo — el padron que se va a crear, los montos por depto, el capital al tesoro, la semana a abrir — y el estado actual (que pasos ya estan hechos, si los hay). Es lo que la UI muestra antes de confirmar.
- **EJECUTA** (`confirmacion` == la frase exacta `"sembrar la economia"`): corre los 7 pasos. Cualquier otro valor de `confirmacion` -> 400, sin escribir.

**Re-entrante y honesto ante fallas:** cada paso se guarda por "ya esta hecho?" (padron existe, tesoro con saldo, semana abierta, rutina presente, modo vivo). Si un paso falla a mitad, el helper PARA y devuelve un reporte preciso de que pasos completo y cual fallo, para que Pedro (o una segunda llamada) complete lo que quede. El unico paso irreversible (el padron, paso 2) es lo primero que se escribe; una falla despues deja una economia sembrada-pero-no-activada que una segunda llamada al helper termina de prender (saltea el paso 2 ya hecho).

## 5. Los montos (config del helper, con defaults conservadores)

El helper toma la config; los defaults son conservadores y **todo es ajustable despues por perillas** (los montos NO son irreversibles). Propuesta de arranque:
- **Capital al tesoro:** un monto modesto que alcance para unas rondas de pre-seed (Pedro pone el numero; default sugerido acotado). Es su plata; el helper no inventa un monto grande.
- **Por depto de fabrica:** `presupuesto_semanal_mm`, `techo_preseed_mm` (por pedido), `techo_preseed_ciclo_mm` (por ciclo) en valores chicos; `techo_api_ciclo_mm = 0` (firma por cada gasto de API por token).
- **La semana:** `cuota_firmable_mpt` (los pedro-tokens de la semana) y `reserva_personal_mpt`.
- **El piso del ciclo:** `PISO_APROVECHAMIENTO_PCT` se queda en 40 (no lo toca el helper; se ajusta aparte si Pedro quiere con datos reales).

Los montos que DEBEN ser > 0 para que un depto de fabrica realmente proponga-y-se-financie: los dos techos de pre-seed (`techo_preseed_mm`, `techo_preseed_ciclo_mm`); en 0 frenan (`jefe._freno_preseed`, `bus.py:274-278/318-323`). `presupuesto_semanal_mm` en 0 no frena la existencia (solo saltea el freno de agresividad). `techo_api_ciclo_mm` se deja en 0 a proposito.

## 6. Invariantes

- **La siembra es un acto de Pedro.** El helper no se dispara solo: sin el token de confirmacion exacto, solo hace preview. Yo NO corro `sembrar-guiado` contra el home real de Pedro — lo ensayo en desechable; el disparo real es suyo.
- **El padron es irreversible y se escribe una sola vez.** El paso 2 respeta la escritura unica de `sembrar`; una segunda corrida lo saltea, no lo duplica.
- **Re-entrante:** llamar al helper de nuevo completa lo que falte sin romper lo hecho (guardas "ya esta hecho?" por paso).
- **Reusa los primitivos, no los reimplementa** — misma fuente de verdad que los endpoints sueltos (`Registro`, `kernel.acunar`, `operacion.abrir_semana`, `routines`, `interruptor`).
- **La postura segura del arranque:** `techo_api_ciclo = 0` (firma por gasto de API real); montos conservadores; PISO 40 sin tocar.
- **finanzas va siempre** en el padron (dependencia dura del backend).
- **Escritura serializada** bajo el candado del libro, como el resto de economia.

## 7. Lo que NO hace (fuera del MVP)

- **No corre el probe de consumo por Pedro** (paso 1): es una precondicion manual (levantar el server un rato). El helper toma la `capacidad_ciclo` como dato.
- **No decide los montos por Pedro:** propone defaults conservadores; el numero es suyo.
- **No construye el abismo** (leer, la casa, la memoria): es otra capa, aparte.
- **No agrega departamentos despues de sembrar:** eso sigue siendo editar el JSON a mano (no hay `baja`/alta post-siembra); el helper no lo resuelve.
- **No cambia `PISO_APROVECHAMIENTO_PCT`:** se queda en 40; ajustarlo es aparte.
- **Sin deshacer:** no hay "des-sembrar". El preview es la unica red antes del acto.

## 8. Como se verifica que funciona

- **Preview:** `POST /sembrar-guiado` sin `confirmacion` no escribe NADA (ni `departamentos.json`) y devuelve el plan + el estado actual.
- **Confirmacion:** un `confirmacion` incorrecto da 400 sin escribir; el exacto ejecuta.
- **Los 7 pasos, en un home desechable:** tras ejecutar, existen `departamentos.json` (con taller/development/research/finanzas), el tesoro tiene el capital, la semana esta abierta (`EMISION_PT`), las perillas estan puestas (pre-seed > 0, api_ciclo = 0), hay una rutina `departamento` por depto de fabrica, y el modo es `vivo`.
- **Re-entrancia:** una segunda llamada al helper sobre una economia ya sembrada saltea el padron (no duplica) y converge sin error; una llamada sobre una economia a-medio-sembrar completa lo que falta.
- **Idempotencia de los pasos:** acuñar no re-mint si el tesoro ya tiene saldo; abrir no re-abre una semana ya abierta; poner_modo("vivo") sobre vivo no rompe.
- **La fabrica cobra vida (ENSAYO en vivo, con server y Ollama):** tras la siembra guiada en un home desechable, un tick de la rutina `departamento` hace que un jefe (p.ej. taller) proponga trabajo, y la propuesta llega a la mesa (`api_eco_bus`). Esto prueba end-to-end que la secuencia prende la fabrica. Queda como el smoke de esta feature (aislado, no toca el setup real).
- **No regresion:** la suite completa (`.venv/bin/python -m pytest -q --ignore=test_chat_live.py`) verde; sin llamar al helper, la economia se comporta como hoy (sin sembrar).
