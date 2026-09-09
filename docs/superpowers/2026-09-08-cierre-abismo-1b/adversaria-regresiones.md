# Adversaria: regresiones (rama feat/abismo-1b, HEAD 745a7d8 sobre main c645ccd)

Lente: que cambio para lo que YA funcionaba antes de la rama. Revision de lectura sobre el
checkout (sin mutar arbol, indice ni HEAD) + sondas propias corridas fuera del arbol de tests
(`scratchpad/sonda_regresiones.py`, borrada al terminar) que reusan el harness de
`test_abismo_chat.py` (ModeloEspia + TestClient), el `cli_falso` de `test_abismo_suscripcion.py`
y el juez doble de `test_abismo_nube.py`. Solo se reporta lo reproducido o lo que el codigo
muestra sin ambiguedad.

## Veredicto corto

No encontre ninguna regresion Critical ni Important. Lo que existia antes de la rama se comporta
igual en todas las rutas atacadas (steer, fallbacks, /redacta, /team, goals, /nube sin marcas,
adjuntos, /stop, persistencia, cobro). Quedan tres Minor: el `stderr.txt` de jobs persiste la marca
(ya declarado en el ledger), el `output` crudo de los agentes del orquestador entra con marca al
prompt de sintesis (en memoria, no a disco), y la ventana de `telemetry.recent(2000)` que lee
`learning.learn` se diluye con las filas `abismo`.

## Linea base y suite

- `.venv/bin/python -m pytest -q --ignore=test_chat_live.py` -> **1453 passed, 4 warnings in 67.61s, EXIT=0**
  (main era 1374; +79 de la rama; las 4 warnings son las preexistentes: chromadb/opentelemetry,
  `on_event` x2, starlette testclient).
- `node --test` en `calipso/web/fabrica/` -> **412 pass, 0 fail, EXIT=0** (main era 401).

## Tests preexistentes: ninguno debilitado

`git diff c645ccd..745a7d8 -- 'test_*.py' 'calipso/web/fabrica/*.test.js'` sobre archivos que ya
existian en main:

| Archivo | Cambio | Debilita? |
|---|---|---|
| `test_privacidad_nube_system.py` | `assert resultado == _SISTEMA_NUBE_MINIMO` pasa a `== _sistema_nube()` + `startswith(_SISTEMA_NUBE_MINIMO)`; sigue afirmando `_build_context` no llamado | No: es la letra del spec 8.1 |
| `test_abismo_anillos.py` (1a) | `puede_viajar` a nube: de "False para todo" a "1 y 2 True, 3 False, destino desconocido False" | No: enmienda 2026-09-08, y suma el caso fallo cerrado |
| `test_abismo_contrato.py` (1a) | suma `assert b.endswith("CONSULTA.")` | No: mas estricto |
| `test_abismo_consulta.py` / `test_abismo_marca.py` (1a) | solo agregan tests | No |
| `arranque.test.js` | el mock `nodo` pasa `textContent` de campo a propiedad contada (`escriturasDeTexto`) | No: mismo valor leido, suma medicion |
| `chat.test.js`, `pulso.test.js` | solo agregan tests | No |

## Sondas corridas (salidas citadas)

Comando: `cd /var/home/pedro/calipso && .venv/bin/python -m pytest -q -p no:cacheprovider -s --durations=0 <scratchpad>/sonda_regresiones.py`
Resultado final: **10 passed, 4 warnings in 18.04s, EXIT=0**. Duraciones: stop_durante 4.53 s,
fallback_entre 3.02 s, nube_sin_marcas 2.01 s, steer 0.52 s, el resto < 0.01 s.

1. **Steer sin marcas, byte a byte** (`test_steer_sin_marcas_byte_a_byte`): modelo pausado antes
   del trozo 2; steer "otra cosa" con el stream abierto. Chunks antes del `steered`:
   `['hola ', 'Pedro']` (el trozo ya en vuelo se entrega, como en main: el inbox se mira ENTRE
   chunks), `steered`, dos `done`, persistido `("assistant", "hola Pedro …(interrumpido)")` y el
   steer como turno siguiente con `messages[-1] == "otra cosa"`. Cero eventos `abismo`, cero filas
   `abismo` en telemetry. PASA.
2. **Fallback local con marca** (`/api` con `_sse_text_chunks` que revienta; el local emite
   `x ⟦abismo:chats libro⟧ y`): meta `note == "fallback a local"`, visible `"x  y"`, sin `abismo`,
   un `done`, telemetry `retirada` con `clase == "sin_corte"`, `chat_turn.fallbacks[0].to == "local"`,
   `chats.json` sin `⟦`. PASA: `estado_abismo.apagada = True` del fallback local funciona.
3. **Fallback local DESPUES de un corte** (api emite marca, la reentrada api revienta, el local
   emite otra marca): fases `pondering, pescado`, luego fallback; visible `"a local  sigue"`
   (tramo + fallback, marca del fallback retirada sin corte); `cost` x1, `_cobrar_turno` x1,
   `done` x1; 2 llamadas api + 1 local; `chats.json` sin `⟦`. PASA: el filtro no queda cortado
   colgado tras el corte + excepcion (la marca ya fue consumida por `emisor.marca_abismo()`).
4. **/redacta** (`test_redacta_no_ensena_el_contrato_y_no_engancha_el_filtro`): el system del
   borrador NO contiene `=== El abismo ===` ni `abismo:` (`compositor/redactor.preparar_borrador`
   arma su propio prompt, sin `internal_contract`; verificado con grep: cero referencias a
   `prompt_compiler`/`abismo` en `calipso/compositor/`). Una marca emitida por el modelo sale
   VISIBLE: `VISIBLE_BORRADOR: 'borrador ⟦abismo:chats x⟧ fin'` (ruling 2 / spec 11: `Emisor(ws)`
   sin filtro del abismo). Sin `abismo`, un `done`, el borrador no se persiste como assistant.
   Mismo comportamiento que main salvo que en main la marca no existia; el borrador no puede
   aprenderla de los ejemplos de voz porque salen de `chats.json`, donde jamas se persiste. PASA.
5. **/team** (`_should_orchestrate` forzado; agente que devuelve `vamos a ⟦abismo:chats x⟧ mirar`,
   sintesis `sintesis ⟦abismo:chats y⟧ final`): visible `"sintesis  final"` (retiro SIN corte, el
   texto posterior no se pierde), sin `abismo`, un `done`, retiradas
   `[("agente", 1), ("sin_corte", None)]`, `meta.route == "orchestrator"`, `chats.json` sin `⟦`.
   Los agentes heredan `base_system` (el system del turno, con el contrato): `agent_system`
   recibio `"SISTEMA BASE"`. PASA.
6. **Goals** (`goals.detect` -> objetivo): `chunk "meta creada"`, `done`, sin `abismo`, modelo no
   llamado, `meta.route == "goal"`. PASA (el camino esta fuera del bucle exterior; el diff no lo toca).
7. **Adjuntos en la reentrada** (`attachments.context_block` -> `=== ADJUNTO ===`): el system de
   la primera pasada lo lleva y el de la segunda `startswith` el primero + bloque del abismo. PASA
   (vision y web se agregan en el mismo bloque, antes de la rama: `system_base = system`).
8. **/nube sin marcas por suscripcion** (`/nube /claude que hablamos con Marta`, juez doble):
   `privacidad/tapado` x1, visible `"Le dije a Marta hola"` (reponer), sin `abismo`, una sola
   invocacion, `sistema.startswith(_sistema_nube())` y `"Marta" not in llamadas`.
   `COLA_DEL_SYSTEM_NUBE: '\n\nResponde como Calipso. No digas que eres el backend usado.'` y el
   prompt `Pedro: ...\nCalipso:` son de main (`c645ccd:calipso/server.py:2855` y `:2866`). PASA.
9. **Fallback entre suscripciones con marca** (CLI propio: la 1a invocacion sale con exit 1 y
   stderr `boom ⟦abismo:chats libro⟧`; la 2a escribe `fallback ⟦abismo:chats libro⟧ sigue`;
   `_best_subscription_client` -> codex): meta "fallback entre suscripciones", visible
   `"fallback  sigue"`, sin `abismo`, un `done`, 2 invocaciones, retirada `sin_corte`,
   `chats.json` sin `⟦`, `MARCA_EN_TELEMETRY: False`, el JSON del job fallido sin `⟦` (el `msg`
   limpio). Pero: `ARTEFACTO stderr.txt 'boom ⟦abismo:chats libro⟧'` (ver Minor 1). PASA salvo eso.
10. **/stop durante el fallback entre suscripciones** (la 2a invocacion tarda 4 s; `/stop` tras
    su `process/start`; luego `/claude hola de nuevo` por el mismo socket): un `done`,
    `(proceso interrumpido)` visible, y el turno siguiente contesta `"tercera respuesta"` en
    `SEGUNDO_TURNO_S: 1.5` sin turno fantasma (el `"/stop"` que ahora devuelve
    `_run_subscription_text_live` queda en `pending` y el tope del bucle lo saltea con
    `continue`). Persistido: 4 mensajes en orden. PASA.

Nota de metodo: una corrida intermedia con dos de estas sondas FALLANDO por aserciones mias
(en el mismo proceso) tardo 306 s; los pares `steer+nube` (14.8 s) y `fallback_entre+stop` (23.5 s)
y la corrida final de las diez (18 s) son rapidos. Es un artefacto del harness en la ruta de
fallo, no una regresion del server: no reproducido como tal.

## Medicion: latencia y tamano que el contrato le suma al system

Script propio con `CALIPSO_HOME` a un temporal y el `catastro.json` REAL copiado (solo lectura,
936 bytes, 3 proyectos), con una bomba sobre `catastro.escanear`:

```
catastro.json bytes: 936 proyectos: 3
len(bloque_contrato(nombres)): 583 termina en CONSULTA.: True
linea repo: ⟦abismo:proyecto nombre⟧ -- repo: calipso y 2 mas.
len(bloque_contrato(())): 596
internal_contract: 0.099 ms por llamada; len=2660 chars
catastro.nombres(): 0.050 ms por llamada (lee catastro.json cada vez)
len(_SISTEMA_NUBE_MINIMO): 363 len(_sistema_nube()): 1149 delta: 786
```

- La bomba no salto: `catastro.nombres()` no escanea disco (lee el JSON, 0.05 ms). `internal_contract`
  se llama UNA vez por `_build_context` (`prompt_compiler.py:224`, unico llamador), o sea una por
  turno (dos si hay fallback). Latencia despreciable.
- Local: +583 chars al system (el bloque "Contrato interno" pasa de ~2076 a 2660 chars). Con el
  catastro real sobrevive UN nombre ("calipso y 2 mas"): el dato para la promesa "preguntame por
  nombre" del brief, no una regresion.
- /nube: +786 chars sobre el minimo de 363 (contrato sin nombres 596 + linea de marcadores).

## Lo que revise por lectura (sin sonda), con evidencia

- **Emisor**: `Emisor(ws, filtro=...)` sigue aceptando `filtro` (test_mapa_foco.py:134 pasa);
  `Emisor(ws)` = solo foco (`server.py:7428-7432`); con `_mapa_foco is None` la lista queda vacia y
  `chunk` cae en `_soltar(texto)` como antes. `cerrar()` ahora ademas `_cosechar()`: foco no deja
  focos nuevos al cerrar (solo vuelca un prefijo incompleto), asi que no cambia nada.
- **Usage**: `dispatch.py:431-432, :458-459, :486-487` solo ASIGNAN `prompt_tokens` y
  `completion_tokens`, que son exactamente las dos claves que el bucle exterior acumula
  (`server.py:3773-3774`); no se pierde ninguna otra clave. En suscripcion `completion_tokens`
  es la suma por invocacion (= main con una sola).
- **Costs / cobro**: `costs.log_usage` (`:3916`), `_cobrar_turno` (`:3925`), `cost` (`:3928`),
  `chat_turn` (`:3941`), `mem.remember` (`:3987`), `chats.append` (`:3994`) y `done` (`:4015`)
  estan fuera de los dos `while` interiores: una vez por turno (la sonda 3 lo mide).
- **`/stop` como segundo valor de `_run_subscription_text_live`**: los cinco llamadores
  (`:2405` agente, `:2544` sintesis, `:3635` turno, `:3837` fallback) o filtran `"/stop"`
  (`_run_dynamic_team`, `:2763` y `:2814`) o lo dejan en `pending` donde `:3286` lo saltea.
- **`/mia`, `/help`, `/plan`**: el diff no toca sus ramas (solo `estado_abismo.reset()` antes).
- **Pulso**: `EVENTOS` suma `"abismo"` (`pulso.py:22-23`); `publicar` de los eventos viejos no
  cambia; `pulso.js` `CONOCIDOS` acoplado (test_abismo_pulso.py + pulso.test.js). Un cliente viejo
  (pulso.js v3 cacheado) ignora `abismo` por la whitelist: fallo cerrado.
- **PWA offline**: `sw.js` CACHE `calipso-shell-v4` (install re-corre `addAll(SHELL)`, activate
  borra v3, `skipWaiting`+`claim`); no hay modulo JS nuevo; `test_mapa_server` afirma que todo
  `calipso/web/fabrica/*.js` esta en el SHELL (pasa en la suite). `fetch` es network-first, asi
  que online no hay ventana de index.html viejo con app.js nuevo.
- **Fabrica cargando otro chat a mitad de un pondering**: `cargar` pone `abismo: null` y
  `streamViejo` (`chat.js:250-256`); `"abismo"` esta en `EVENTOS_DEL_STREAM`, asi que el resto del
  stream viejo se descarta; `pintarAbismo` con `abismo` null limpia el `setInterval` y oculta la
  caja (`app.js:1846-1852`). Tests: chat.test.js "un abismo que llega despues de cargar otro chat
  se descarta" y "cargar apagan".
- **`/api/chats` e historial**: la marca no aparece en `chats.json` en ninguna de las 8 sondas que
  lo greppean (`_sin_marca_en_disco`), incluidas fallback local, fallback entre suscripciones,
  orquestador y /nube.
- **Telemetry**: lectores de `telemetry.jsonl` = `learning.learn` (`learning.py:105`, filtra
  `kind == "chat_turn"`, ignora `abismo`) y `GET /api/telemetry` (`server.py:4595`, passthrough sin
  consumidor en `index.html`: cero hits de `api/telemetry`). `abismo_consultas` en `chat_turn` es
  un campo extra que nadie lee. Ver Minor 3.
- **Jobs**: `output.txt`, `partial-output.txt` y el `msg` de error pasan por `_limpiar_marcas`
  (`:3016-3017, :3044-3048, :3057, :3074`); `stderr.txt` no (`:3019, :3060, :3076`). Ver Minor 1.
- **`test_chat_live.py`**: sin cambios en la rama; ignora tipos desconocidos (`abismo`, `steered`,
  `process`) sin romper. Sigue siendo un script valido (no muestra el pondering).
- **Cadena de import**: `prompt_compiler` -> `calipso.abismo.contrato` -> solo `marca`
  (`contrato.py:21`); `calipso/abismo/__init__.py` vacio. Sin ciclo.

## Findings

### Minor 1 -- `stderr.txt` de jobs persiste la marca (reproducido; ya en el ledger)

Sonda 9: `ARTEFACTO stderr.txt 'boom ⟦abismo:chats libro⟧'`. `server.py:3019`, `:3060` y `:3076`
escriben `stderr` crudo mientras `output.txt`/`partial-output.txt`/`msg` pasan por
`_limpiar_marcas`. Angulo de regresion: en main no habia marca que persistir; ahora un CLI que
eco-ee su entrada a stderr deja la marca en disco, y en la REINVOCACION el system lleva el
bloque pescado, asi que un CLI que vuelque el system en el error dejaria el bloque en
`stderr.txt` (constraint global: el bloque jamas se persiste). No lo reproduje con el CLI real.
Fix de una linea por sitio: `jobs.write_artifact(..., "stderr.txt", _limpiar_marcas(stderr))`.
Ya figura en contexto-13 como sumidero declarado.

### Minor 2 -- el `output` crudo de los agentes del orquestador entra con marca al prompt de sintesis

`server.py:2789` retira la marca SOLO de lo que va al pulso (`mango.razonando(...)`); `:2791`
guarda `result = {**agent, "output": output}` con el texto crudo, y `:2542` lo pasa a
`orchestrator.synthesis_prompt(chat_msg, results)`; el fallback de sintesis (`:2559-2564`)
tambien concatena `r['output']` crudo. Consecuencia: el modelo de sintesis lee las marcas de los
agentes (que ademas heredan el contrato por `base_system`) y puede repetirlas; lo que repita se
retira al final con `apagada` (sonda 5 lo confirma: visible `"sintesis  final"`). No llega a
disco (`agent_team` persistido solo lleva metadatos, `:2565-2569`; `agent_turn` solo
`response_chars`). Es ruido en un prompt en memoria, no una fuga: por eso Minor. Si se quiere
cerrar, `_retirar_con_aviso(output, "agente")` una sola vez antes del `result`, y usar ese texto
para el pulso.

### Minor 3 -- la ventana de `learning.learn` se diluye

`learning.py:105` toma `telemetry.recent(2000)` (las ultimas 2000 LINEAS) y filtra
`kind == "chat_turn"`. Cada consulta suma 1 fila `abismo`/`consulta` (+1 `reinvocacion_suscripcion`
en suscripcion, +1 `retirada` por marca retirada, +1 `abortada_por_steer`), asi que la misma
ventana cubre menos turnos que en main. Sin cambio funcional en el aprendizaje mas alla de la
ventana efectiva; lo anoto porque es el unico lector preexistente de telemetry al que las filas
nuevas le cambian algo.

## No reproducido / sin hallazgo

- Filtro del abismo "cortado colgado" tras corte + excepcion (sonda 3) o en el bucle one-shot
  (lectura: el filtro solo ve `tramo_crudo` sin marca valida, o `texto` entero con
  `puede_cortar()` False, o `resto` ya sin marcas por `_retirar_con_aviso`): no ocurre.
- Perdida de texto en el orquestador: solo se retira la marca, el texto a los costados queda.
- Turno fantasma por el `"/stop"` en `pending`: no ocurre (sonda 10).
- El chunk en vuelo antes del `steered`: identico a main (el inbox se mira entre chunks).
- Los 306 s de una corrida con sondas fallidas: artefacto del harness, no del server.
