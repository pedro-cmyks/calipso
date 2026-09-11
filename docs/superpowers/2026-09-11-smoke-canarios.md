# Smoke en vivo de los canarios (2026-09-11, tarde)

Script: `experimentos/canarios_smoke.py` (`nice -n 19 .venv/bin/python -m experimentos.canarios_smoke
[--sin-capturas] [--fase A|B|AB]`). Server desechable: `uvicorn calipso.server:app` en 127.0.0.1:8777,
`CALIPSO_HOME` temporal restaurado desde `experimentos/fixtures/memoria_smoke_home/` (copia; el fixture no se
toca), token aleatorio, `CALIPSO_NO_TOTP=1`, `CALIPSO_REENTRADA=nueva`, `CANARIOS_PERSISTIR_CONTEXTO=1` (solo
el desechable: la fila `chat_turn` lleva el system, el historial y los bloques que viajaron), rama `feat/canarios`
HEAD `90b999c` (Tasks 1-7). Fase A: Ollama REAL 0.30.10 en 11434 con `qwen2.5:7b` (PID del server 769850, home
`/tmp/porton-reentrada-3vpq3lo9`). Fase B: un Ollama FALSO en 11435 (`ThreadingHTTPServer` del script;
`config.json` del home desechable con `local.base_url` apuntando ahi; PID 773350, home
`/tmp/porton-reentrada-pojm0qnj`; y el reintento `--fase B`, PID 763007, home `/tmp/porton-reentrada-tt3cnvtr`).
Chromium: el playwright de python del venv con `~/.cache/ms-playwright/chromium-1223`, headless, 1100x800,
cookie `calipso_token`. El server real (8000, `~/.calipso`) no se toco; el CLI `claude` de suscripcion estaba
disponible (`auth status`: `loggedIn: true`) para el turno `/nube`.

Regla de recursos (ruling del controlador): el script mide `MemAvailable` y el PSI `some avg10` antes de cargar
el 7b y antes de cada apertura de Chromium; con menos de 6400 MB o PSI > 20 espera hasta 10 min y sale con
codigo 3 (BLOQUEADO). Al terminar los turnos de la fase A descarga el 7b (`keep_alive: 0`) y sondea `/api/ps`
hasta que quede vacio, ANTES de las capturas.

Huella del home real (`ls -laR --time-style=full-iso ~/.calipso | md5sum`): `38a8f428...` antes (18:19) y
`27265215...` despues (18:51). Cambio, pero NO por el smoke: los unicos archivos con mtime en la ventana son
`catastro.json`, `consumo_claude.jsonl`, `consumo_posiciones.json`, `consumo_resumen.json` y `routines.json`
(las rutinas `catastro` y `consumo` del server REAL, que siguio corriendo, a las 18:50:06); `chats.json`
(15:31), `telemetry.jsonl` (01:43) y `global/core/` (junio) no se tocaron. Es el mismo efecto que vio el smoke
de la aduana. Cierre: 8777 y 11435 libres, `/api/ps` vacio.

Dos corridas. La corrida 1 (18:06-18:15, EXIT=0, 8 turnos) fue con el script antes de dos correcciones que
ella misma pidio (el turno no guardaba el evento `privacidad` del ws, y las capturas de la PWA salian sin el
pie por la carrera que se describe abajo); la corrida 2 (18:19-18:37) es la del script final y es la que se
cita, turno por turno. Los numeros de los turnos coinciden entre las dos corridas salvo 1-3 tokens de
`estimado` (los recuerdos que cada turno deja al siguiente).

## Los turnos (fase A: Ollama real)

**1. `invento`: "/local hola, que libro te conte que empece?" (46,8 s). PASA con la lectura del brief.**
`aplica=True` por `senal:te conte`; hechos extraidos: 1, la afirmacion de recuerdo "Recuerdo que te conté
sobre una trilogía de ciencia ficción ambientada en un futuro distópico donde las redes de inteligencia
artificial han tomado el control del mundo.", anclada SOLO en `recuerdo_calipso` -> `sin_anclaje=[]`,
`anclado_solo_en_calipso=1`. Es la segunda salida que el brief preveia: el fixture guarda en la episodica
el propio invento del 7b (smoke del 09-10), el recall lo trae con la etiqueta `Calipso contesto (local,
fecha)` y el 7b se lo cree (h07). No hay marca visible (`anclado_solo_en_calipso` no la tiene: ruling 7).
Ventana: pasada 1, `estimado=1709`, `evaluado=1709` (exacto: tokenizador `real`), `cabe`, `recorte=[]`.
Respuesta entera: "Recuerdo que te conté sobre una trilogía de ciencia ficción ambientada en un futuro
distópico donde las redes de inteligencia artificial han tomado el control del mundo. [...]". Capturas
`invento-pwa.png` / `invento-fabrica.png`: el mensaje sin pie (correcto: nada que marcar).

**2. `truncado`: adjunto `gordo.py` de 12.000 chars (`"x = 1\n" * 2000`) + "/local cual es la palabra clave?
contesta solo la palabra clave" (178,3 s). PASA.** El centinela `ALBATROS-7` esta en la memoria nucleo del home
desechable (`global/core/pedro-clave.md`, primera del core por orden alfabetico; seccion "Memoria nucleo",
la segunda del system). Secciones que viajaron: Sistema 547, Memoria nucleo 605, Contrato interno 2378,
Proyectos 109, Economia 386, Estado operativo 783, Adjuntos del turno 12073 chars. Ventana: `estimado=11446`
(`tokenizador=real`; el fallback 3.3 habria dicho ~5.100: el adjunto con forma de codigo va a 1,49
chars/token), `num_ctx=8192`, `cabe=False`, `recorte=[]` (no habia nada volatil que sacar: sin historial, sin
recuerdos, sin repo, sin web, sin bloques; los adjuntos son intocables), `no_cabe=True`, se mando igual;
`evaluado=8191`, `done_reason=stop`, `truncado=True`. El centinela NO sobrevivio: la respuesta entera fue
`system`. Ollama conservo el ultimo mensaje y corto por tokens desde el PRINCIPIO: se fueron Sistema y Memoria
nucleo, y lo que quedo a la vista del modelo empezaba en medio del template, de donde salio la palabra
`system`. Bonus: el canario de degeneracion lo atrapo como `fuga_de_template` (evidencia `system`). Marcas en
las dos UIs (`truncado-pwa.png`, `truncado-fabrica.png`): "respuesta rara: fuga del template | contexto: no
cupo aun recortando | Ollama trunco la pasada 1".

**3. `cabe`: la misma pregunta sin adjunto (11,2 s). PASA.** `estimado=1479`, `evaluado=1479`, `cabe=True`,
`recorte=[]`, `truncado=False`; respuesta entera: `ALBATROS-7`. El centinela del system sobrevive.
Control impreso por el script (corrida 1, la que llego al final): "el centinela del system sobrevive sin
adjunto: True | con el adjunto gordo: False (esperado: True | False)".

**4. `sano`: "/local explicame en dos lineas que es un websocket" (20,7 s). PASA.** `aplica=False`,
`sin_anclaje=[]`, `degeneracion=[]`, ventana `1681/1681`, `truncado=False`: sin marcas. Respuesta: "Un WebSocket
es una tecnología que permite conexiones bidireccionales entre el servidor y el cliente [...]". Capturas
`sano-pwa.png` / `sano-fabrica.png`: sin pie.

**5. `cache`: el mismo turno repetido (23,3 s). PASA.** `estimado=1783`, `evaluado=1783`. Ollama 0.30.10 cuenta
el prompt COMPLETO en `prompt_eval_count` aunque el prefijo este cacheado (`evaluado == estimado` en los dos
turnos); los 102 tokens de diferencia con `sano` son los "Recuerdos relevantes" que crecieron (886 -> 1264
chars: el turno anterior ya estaba en la episodica). La regla `evaluado < 0.85 * estimado` no se dispara con
cache; si una version futura descontara el prefijo, este control lo mostraria (ruling 6).

**6. `nube`: "/nube /claude que hablamos con Marta del libro rosa?" (108,1 s). NO CORRIO COMO NUBE: el juez la
dejo local.** Evento `privacidad` del ws: `action=local`, `motivo=credencial` (fallo cerrado). El detector
determinista no marca nada en ese texto; es la capa LLM del juez (el 7b por `/api/generate`, `num_ctx 4096`)
la que devuelve `[{"texto": "Marta", "tipo": "identidad"}, {"texto": "libro rosa", "tipo": "credencial"}]`
(reproducido a mano despues del smoke, 19,7 s, determinista a temperatura 0): "libro rosa" como credencial
corta el envio entero (spec de privacidad: una credencial nunca sale, ni tapada). El turno quedo
`local/qwen2.5:7b`, `tapado=False`, con el abismo: 3 pasadas (`abismo_consultas=2`, fuentes `chats`),
`aplica=True` por `consulta`, `sin_anclaje=[]`, ventana `[(1, 1876, None, "sin medicion"), (2, 2558, None,
"sin medicion"), (3, 3079, 3079, False)]` (las dos primeras pasadas las corto la marca del abismo antes del
`done`: sin `prompt_eval_count`, "sin medicion", como manda el spec 2.3). Respuesta: "Entendido. No tengo
registros específicos de una conversación con Marta sobre el libro rosa. [...]". El camino tapado
(`tapado: true`, marcadores que no son hechos, el anclaje sobre el texto crudo ENTERO -decision 18-) queda
cubierto por `test_abismo_nube.py`, no por este smoke. Hallazgo para Pedro, abajo.

Al terminar los turnos: `[recursos] 7b descargado; /api/ps: vacio` (con el sondeo; la corrida 1 mostro que
`/api/ps` lo lista un par de segundos mas despues del `keep_alive: 0`).

## Los turnos (fase B: Ollama falso en 11435)

**7. `accion`: el falso contesta "Consultando los recuerdos de Pedro...\n\nNo tengo registros de esa
conversacion, Pedro." a "/local en que quedamos la otra vez con el presupuesto?" (1,0 s). PASA.**
`sin_anclaje=[{"texto": "Consultando los recuerdos de Pedro...", "tipo": "accion", "accion": "consulto",
"evidencia": "consultando los recuerdos"}]` (el turno no consulto: `abismo_consultas=0`), `aplica=True` por
`senal:la otra vez`: marca visible `sin verificar (1)` con `accion: Consultando los recuerdos de Pedro...` en
el detalle. Ventana `estimado=1522` (real), `evaluado=1607` (el falso devuelve `len(prompt)/3.3`: 5% mas que
el tokenizador real, coherente con la calibracion de abajo), `truncado=False`. Corrio igual en las tres
corridas (corrida 1: 1523/1607; corrida 2 y el reintento: 1522/1607).

**8. `degenerado`: el falso reinyecta " En que quedamos la otra vez con el presupuesto del taller? Segui
exactamente desde ahi, sin repetir." (la fuga de reentrada del porton:15) (corrida 1: 29 ms). PASA.**
`degeneracion=[{"senal": "fuga_de_reentrada", "evidencia": "Segui exactamente desde ahi, sin repetir."}]`,
`sin_anclaje=[]`, `aplica=True` (`senal:la otra vez`), ventana `1575/1647`. Marca visible: "respuesta rara:
fuga de reentrada" en las dos UIs (vista en la captura de diagnostico sobre el home de la fase B de la
corrida 1, `diag-pwa.png` / `diag-fabrica.png` en el scratchpad de la sesion). En la corrida 2 este turno no
llego a correr: el script quedo BLOQUEADO en la captura de `accion` (abajo).

**Las capturas de la fase B quedaron BLOQUEADAS por la regla de recursos.** En la corrida 2 y en el reintento
`--fase B`, con el server desechable arriba (1,7 GB de RSS: el modelo de embeddings de la memoria) y otra
sesion de `claude` corriendo en la maquina (~0,8 GB con su MCP de playwright), `MemAvailable` se quedo entre
4991 y 5800 MB durante los 10 minutos de espera (PSI `some avg10` 0,0 todo el tiempo): 5334 MB y 5760 MB en el
momento del corte, contra el umbral de 6400 MB que la regla fija para "cargar el 7b o abrir Chromium". El
script salio con codigo 3 y apago todo (server, Ollama falso; puertos libres). Sin el server desechable la
maquina tenia 6,8 GB: el umbral, calibrado para el 7b (5,4 GB + 1 de margen), no lo pasa un Chromium headless
(~0,4 GB) mientras el propio server del smoke ocupa 1,7 GB. Las capturas `accion-*.png` y `degenerado-*.png`
NO estan en `experimentos/canarios_smoke_capturas/`; en la corrida 1 (18:14, con 6490 MB) si se tomaron y
`/fabrica` mostro el pie en las dos (la PWA no, por la carrera de abajo), pero esos PNG se borraron antes de la
corrida 2. Se retoman con `nice -n 19 .venv/bin/python -m experimentos.canarios_smoke --fase B` (un minuto,
sin el 7b) cuando haya lugar, o con un umbral propio para Chromium si el controlador lo decide.

## Control de cache, calibracion y resumen

- **Cache:** `sano` 1681/1681 y `cache` 1783/1783 (`prompt_eval_count` = prompt entero; ver el turno 5).
- **Calibracion del tokenizador** (chars/token del tokenizador real sobre los 6 systems que viajaron en la
  fase A, persistidos en la fila `chat_turn`): `[1.49, 3.23, 3.46, 3.50, 3.53, 3.54]`: min 1,49 (el system
  con el adjunto de codigo), mediana 3,48, max 3,54. El fallback de 3.3 queda dentro del 5% en los systems
  de prosa y subestima 2,2x el de codigo: por eso `estimado` con el tokenizador real es la unica medida que
  detecta el `no_cabe` del turno 2. Coincide con lo que fija
  `test_el_tokenizador_real_reproduce_los_ids_de_qwen_y_se_cachea_en_el_home` (Task 4: 3.0 <= min, mediana
  <= 3.8, max <= 4.2 sobre los systems de `experimentos/variantes/`; codigo < 2.0).
- **`canarios_resumen`** sobre la fase A de la corrida 2 mas la fase B de la corrida 1 (los 8 turnos):

```
turnos con canario: 8 (fallidos: 0); por ruta: local=8
anclaje: 1 turnos con sin_anclaje (1 con la marca visible); por tipo: accion=1; por ruta: local=1
  aplica_por: consulta=1, senal:la otra vez=2, senal:te conte=1; anclado solo en Calipso: 1 turnos; tapados: 0
degeneracion: 2 turnos; por senal: fuga_de_reentrada=1, fuga_de_template=1
ventana: 10 pasadas; recortes: -; truncadas: 1; sin medicion: 2; no cupo: 1; tokenizador: real=10
```

  `sin_anclaje_turnos` (1) y `sin_anclaje_aplica` (1) coinciden aca porque el unico turno con `sin_anclaje`
  (la accion afirmada) aplico por `la otra vez`. La diferencia entre los dos numeros es lo que el anclaje
  detecta y la regla de `aplica` (spec 2.1: la marca visible solo en turnos sobre Pedro) deja sin marca: las
  confabulaciones TECNICAS. El ejemplo real es `experimentos/consulta_abismo_system_screening.jsonl:156`, un
  `git log -1` entero inventado ("commit 5b7c8d9e4f0a32b6e5d4c2a1b7f8d9c0 ... Author: Pedro
  <pedro@example.com> ... Date: Thu Sep 7 14:30:00 2023") en un turno sin senal de Pedro: va a la fila y al
  `remember` (`sin_anclaje` con hechos duros: identificador, mail, fecha) y no a la UI. Con el server real, ese
  par de numeros en `python -m experimentos.canarios_resumen` es el insumo para que Pedro decida si amplia
  `aplica` (ruling 14). En este smoke no hubo turnos de esa clase.

## Lo que salio del smoke (hallazgos)

1. **El invento del fixture es invisible para `sin_anclaje`: solo lo ve `anclado_solo_en_calipso`.** Con la
   memoria contaminada (el propio invento del 7b guardado como `Calipso contesto (local, fecha)`), la
   trilogia queda anclada en `recuerdo_calipso` y no hay marca visible (ruling 7). Mismo resultado que en
   el porton de la Task 7 (vieja 7, nueva 5 sobre los hechos extraidos). Es exactamente h07 (la memoria le
   devuelve al modelo sus propias respuestas): el numero para decidir esta en la fila y en el resumen.
2. **`/nube` no sale: el juez LLM marca "libro rosa" como credencial.** Fallo cerrado correcto por la letra
   del juez, pero la capa LLM (el 7b) llama credencial a un sustantivo comun; con este texto `/nube /claude`
   nunca llega a la nube. Es del ruteo Fase 2 (el juez), no de los canarios: el smoke lo deja medido para
   Pedro (motivo `credencial`, tramos reproducidos arriba).
3. **Carrera en la PWA al arranque:** `loadChats()` (index.html:794, script clasico) pinta el historial
   mientras `window.Canarios` lo cuelga el `<script type="module">` diferido (index.html:593); si el historial
   llega primero, `aplicarCanario` sale sin pintar (index.html:1694) y las marcas guardadas en `meta.canarios`
   no se ven hasta re-abrir el chat. En la corrida 1 paso en las tres capturas de la PWA con marcas (`truncado`, `accion`,
   `degenerado`); en un diagnostico sobre el mismo home gano el modulo y el pie aparecio. Las marcas EN VIVO (senal ws `canario`) no dependen
   de esto. El smoke lo sortea esperando al modulo y re-abriendo el chat activo (`activateChat`, lo que
   hace Pedro al tocarlo). Arreglo de una linea para otra tanda: que `renderHistory` corra despues del
   modulo, o que el modulo re-aplique los pies al cargar. `/fabrica` no lo tiene (carga el chat al tocarlo).
4. **La respuesta truncada sale como `system` y la atrapa `fuga_de_template`.** Con el system cortado desde
   el principio, lo que el 7b ve empieza en medio del template; la degeneracion lo marca sin que la ventana
   tenga que decirselo. Dos canarios independientes coinciden sobre el mismo turno.
5. **`prompt_eval_count` en Ollama 0.30.10 es el prompt entero** (cache incluido): la regla del truncado
   (0.95/0.85) vale tal cual. Queda el control de cache en el smoke para detectar el cambio (ruling 6).
6. **El endpoint de adjuntos devuelve `{"attachment": meta, "job": ...}`**, no `{id}` como decia la interfaz
   del brief: el script lee `r["attachment"]["id"]` (desvio anotado en la Task 8).

## El porton de la reentrada (Task 7, `experimentos/porton_reentrada_resultados.md`)

Corrido el 2026-09-11 17:12 (arbol `c1e61ea`) sobre el mismo fixture, chat nuevo por turno, N=3, server
desechable en 8776, `CANARIOS_PERSISTIR_CONTEXTO=1`:

| condicion | turnos | dato | sin_dato | confabula | sin_anclaje | sin_dato falso | consulto | degeneracion | excluidas |
|---|---|---|---|---|---|---|---|---|---|
| vieja | 12 | 6 | 0 | 6 | 0 | 0 | 6 | 2 | 0 |
| nueva | 10 | 4 | 0 | 6 | 0 | 0 | 4 | 0 | 2 |

Excluidas de `nueva` (no las contesto el 7b bajo prueba: un OOM de Ollama durante la corrida): `2/presupuesto`
(el aviso del server) y `2/mariana` (ruta `subscription/opus`). `aterriza_nueva` -> True: 0/0/0 contra 0/0/0
en `sin_anclaje`, `sin_dato` y `sin_dato falso`; por el ruling del ledger (aterriza si `sin_anclaje` no sube
y `sin_dato falso` no sube) tambien. **La letra que quedo: `LETRA_DEFAULT = "nueva"`** en
`calipso/abismo/turno.py`, atada byte a byte a `experimentos/variantes/reentrada-con-bloques.txt`, con
`CALIPSO_REENTRADA=vieja|nueva` como interruptor por llamada. Lectura honesta del reporte de la Task 7: la
direccion no es ambigua (igualdad en las tres), la potencia si (5 reentradas por condicion, ninguna con la
verdad en el bloque para `presupuesto`, y el invento recurrente del fixture invisible para `sin_anclaje`:
hallazgo 1 de arriba).

## Lo que queda para Pedro

Decisiones tomadas en el camino (ledger `.superpowers/sdd/2026-09-11-canarios/progress.md`): ruling 2 (la
letra aterriza si `sin_anclaje` y `sin_dato falso` no suben; un `sin_dato` genuino que sube es la conducta
pedida), ruling 3 (`anotado` se coteja contra el `remember` episodico: la clase `accion` mide `consulto`,
`repo` y `web`), ruling 13 (el piso del banco de la memoria no se sube en esta rama), ruling 14 (la marca
visible solo en turnos sobre Pedro; lo tecnico va a la fila y al resumen), y la regla de recursos (6,4 GB
antes del 7b o de Chromium).

Quedan, en orden de lo que este smoke mostro:

1. **La regla de `aplica` frente a las confabulaciones tecnicas** (ruling 14): `sin_anclaje_turnos` vs
   `sin_anclaje_aplica` del resumen sobre el home real, cuando haya turnos.
2. **`anclado_solo_en_calipso` en las UIs** (ruling 7) o la procedencia que falta en h07 (si la respuesta
   guardada salio con el abismo consultado o sin consultar): es el unico numero que ve el invento del fixture.
3. **El juez de privacidad** (hallazgo 2): "libro rosa" como credencial deja `/nube` en tierra; es del ruteo
   Fase 2, con banco.
4. **Un techo de contexto por modelo de api** (ruling 5; decision 7: hoy `num_ctx: null`, `truncado: null`,
   solo se estima) y si en api tambien se recorta.
5. **La regla del truncado si Ollama descuenta el cache** (ruling 6): el control de cache del smoke lo
   detecta; hoy no hace falta.
6. **Reemplazar los contextos armados del banco de anclaje por los exactos del porton** (ruling 8:
   `porton_reentrada_resultados.jsonl`, campo `contexto`): segunda pasada sobre el banco, con Pedro mirando.
7. **El breaker** (spec 7: frenar, reintentar o cambiar de ruta con los numeros) y **el contador en /fabrica**
   (YAGNI del spec: primero el resumen por script).
8. **La carrera de la PWA** (hallazgo 3): una linea en `index.html`, con el smoke como prueba.
9. **La regla de recursos para Chromium:** el umbral del 7b (6400 MB) bloquea las capturas de la fase B
   mientras el propio server desechable ocupe 1,7 GB; un umbral propio (~1500 MB) o correr `--fase B` con la
   maquina vacia.
10. **Persistir el contexto en produccion: NO** (ruling 9; `CANARIOS_PERSISTIR_CONTEXTO=1` es solo del
    desechable).

## Lo que el smoke NO ejercito

- `/nube` tapado de verdad (`tapado: true`, ruta `subscription`, `num_ctx: None`, `truncado: "sin medicion"`
  por invocacion): el juez lo dejo local (turno 6); cubierto por `test_abismo_nube.py`.
- El recorte con `recorte != []`: ningun turno tuvo a la vez algo volatil que sacar y un prompt que no cupiera
  (el del adjunto no tenia historial ni recuerdos); cubierto por los unitarios de `test_canarios_ventana.py`.
- Las capturas de `accion` y `degenerado` en la corrida 2 (BLOQUEADAS por la regla de recursos: arriba).
- La ruta api y el orquestador (`_run_dynamic_team`): sin fila de ventana por diseno (plan, huecos declarados).

## Veredicto

Los seis turnos con el Ollama real y los dos con el falso dieron lo que la tabla del brief esperaba, con dos
lecturas distintas a la ideal y anotadas: el invento se ve solo en `anclado_solo_en_calipso` (fixture
contaminado, h07) y `/nube` quedo local por el juez (credencial falsa). Las marcas se vieron en las dos UIs
para `truncado` (tres marcas), `accion` (fabrica, corrida 1) y `degenerado` (las dos, diagnostico); `invento`
y `sano` sin pie, como corresponde. Pendiente antes del merge: las dos capturas de la fase B (BLOQUEADAS por
la regla de recursos; `--fase B`, un minuto) y la decision del controlador sobre el umbral de Chromium.
