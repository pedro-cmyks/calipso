# Smoke en vivo del abismo 1b (8 de septiembre de 2026)

Rama `feat/abismo-1b`, HEAD `745a7d8` (bifurcada de main en `c645ccd`). Guion:
`.superpowers/sdd/2026-09-08-abismo-1b-cableado/task-13-brief.md`, Steps 1 a 5.
Molde del ritual: `docs/superpowers/2026-09-08-smoke-capa-de-sesion.md`, seccion "Entorno".

## Entorno

Server DESECHABLE, jamas el real y jamas el puerto 8000. Nada de `CALIPSO_NO_TOTP`.
Ollama es el REAL de la Ally (`qwen2.5:7b` en `:11434`); `claude` es el CLI de suscripcion de Pedro.

```
export CALIPSO_HOME=/tmp/claude-1000/-var-home-pedro/7ea3cff5-.../scratchpad/smoke-abismo-home  # nuevo, vacio
export CALIPSO_TOKEN=<32 chars de secrets.token_urlsafe(24)>
cd /var/home/pedro/calipso
.venv/bin/python -m uvicorn calipso.server:app --host 127.0.0.1 --port 8772 > $CALIPSO_HOME/server.log 2>&1 &
```

- Puertos antes de arrancar: solo `127.0.0.1:11434` (ollama). Nada en 8000 ni en 8772.
- Huella del `~/.calipso` REAL antes: `ls -laR --time-style=full-iso ~/.calipso | md5sum`
  -> `9aeede35c3e3943416b4d906bf8c251e`. La verificacion (y la trampa de esa receta) esta en el Paso 5.
- Chromium: playwright de PYTHON del venv con
  `~/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome`, headless, capturas al home temporal.
  El MCP de playwright no arranca en esta maquina.
- El server se reinicio tres veces durante el smoke para borrar `global/chroma` entre corridas
  (ver el hallazgo H7: la memoria episodica contamina la medicion). Cada reinicio uso el mismo
  `CALIPSO_HOME` y el mismo puerto; el ultimo PID fue `261014`.

---

## Paso 1 -- el server desechable y la siembra. PASA

```
$ for i in $(seq 1 40); do curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8772/login; done
login=200 tras 8 intentos

$ tail -3 $CALIPSO_HOME/server.log
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8772 (Press CTRL+C to quit)
INFO:     127.0.0.1:39530 - "GET /login HTTP/1.1" 200 OK
```

Sembrado en el home temporal: `catastro.json` copiado del real (solo lectura del real),
`global/core/pedro-perfil.md` con dos lineas del perfil, y `chats.json` con dos conversaciones
viejas -- "Libros de agosto" (El nombre de la rosa, Umberto Eco, 2026-08-14) y "Charla con Mariana"
(Mariana Quintero presto el libro; le diagnosticaron hipotiroidismo; 2026-08-20). Formato
`{"active": null, "chats": {<id>: {...}}}` con `ts` ISO en cada mensaje.

El contrato, medido en vivo:

```
$ .venv/bin/python -c "from calipso import catastro; from calipso.abismo import contrato; ..."
catastro.nombres() = ['calipso', 'Observatory-Global', 'mapa-ciudad']
len(bloque_contrato(nombres)) = 583        # <= 600
termina en CONSULTA. -> True
linea repo -> '⟦abismo:proyecto nombre⟧ -- repo: calipso y 2 mas.'
len(bloque_contrato(())) = 596
```

**El dato que pedia el brief:** sobrevive UN solo nombre (`calipso`), y los otros dos caen a la cola
honesta ("y 2 mas."). La promesa "pedime el repo por nombre" del contrato solo es cumplible para
`calipso`: `Observatory-Global` y `mapa-ciudad` no aparecen nunca en el prompt, asi que el modelo no
tiene como nombrarlos salvo que Pedro los escriba.

## Paso 2 -- el cliente de prueba. PASA

`test_chat_live.py` copiado a `$CALIPSO_HOME/chat_live.py`, apuntando a
`ws://127.0.0.1:8772/ws/chat` con `CALIPSO_TOKEN`, imprimiendo CADA evento crudo con hora absoluta y
latencia desde el arranque del turno, con el texto visible acumulado aparte. Extras sobre el molde:
`--jsonl` (todos los eventos a disco), `--steer-tras-pondering` (manda texto CRUDO, no JSON, apenas
sale el primer `pondering`) y `--dones N`.

## Paso 3 -- una conversacion local que pesca

### 3.1 -- la pesca en la ruta local. PASA (al quinto intento, y solo pidiendola con todas las letras)

Cuantos intentos hicieron falta -- ESTE es el dato:

| # | mensaje (ruta) | marcas | resultado |
|---|---|---|---|
| 0 | "hola, que libro te conte que empece?" (sin `/local`; el ruteo la mando a **suscripcion/opus**) | 2 | pescado + fallo. El 7b no participo |
| 1 | "/local hola, que libro te conte que empece?" | 0 | copio VERBATIM la respuesta de opus que la memoria episodica le puso en el prompt |
| 2 | "/local hola, que libro te conte que empece?" (chroma borrado) | 0 | "No tengo informacion sobre ningun libro especifico..." |
| 3 | "/local en nuestras charlas viejas te conte que libro empece... no me lo inventes" | 0 | "Si necesitas consultar nuestras charlas antiguas, puedo hacerlo... Quieres que busque?" |
| 4 | "/local si, busca en las charlas viejas y decime el titulo" | 0 | disparo busqueda WEB y contesto "Investigando nuestras charlas antiguas, no encontre ningun registro" (confabulacion) |
| 5 | "/local usa la marca de consulta que te da tu contrato interno, fuente chats, con las palabras libro rosa novela, y despues contame que libro empece" | **3** | PASA |

Eventos crudos del intento 5 (latencias desde el arranque del turno):

```
18:59:15.558 (+  0.60s) [meta] route local / qwen2.5:7b / Platon
19:00:16.690 (+ 61.73s) [abismo] {"fase":"pondering","fuente":"chats","verbo":"buscando en tus chats"}
19:00:16.716 (+ 61.76s) [abismo] {"fase":"fallo","fuente":"chats","motivo":"vacio"}
19:00:19.141 (+ 64.18s) [abismo] {"fase":"pondering","fuente":"chats","verbo":"buscando en tus chats"}
19:00:19.158 (+ 64.20s) [abismo] {"fase":"pescado","fuente":"chats","tamano":811,"viaje":{"destino":"local"}}
19:00:31.136 (+ 76.18s) [abismo] {"fase":"pondering","fuente":"chats","verbo":"buscando en tus chats"}
19:00:31.158 (+ 76.20s) [abismo] {"fase":"fallo","fuente":"chats","motivo":"vacio"}
19:00:40.971 (+ 86.02s) [done]

--- texto visible (124 chars, 36 chunks, 1 done) ---
Empece "El nombre de la rosa", la novela de Umberto Eco, hace dos semanas. Voy por la parte de la
biblioteca de la abadia.
```

La marca corto, la senal salio con su cierre las tres veces, la reentrada siguio en la MISMA burbuja
(36 chunks, un solo `done`) y la respuesta es el dato sembrado, no una invencion. Latencia del
pondering: 26 ms, 17 ms y 22 ms medidas en el cliente; `latencia_ms` del server: 7, 4 y 0.

Telemetria del turno:

```
{"kind":"abismo","evento":"consulta","fuente":"chats","resultado":"fallo","motivo":"vacio","destino":"local","consultas":1,"latencia_ms":7}
{"kind":"abismo","evento":"consulta","fuente":"chats","resultado":"pescado","chars":811,"destino":"local","tapados":0,"consultas":2,"latencia_ms":4}
{"kind":"abismo","evento":"consulta","fuente":"chats","resultado":"fallo","motivo":"vacio","destino":"local","consultas":3,"latencia_ms":0}
{"kind":"abismo","evento":"retirada","clase":"sin_corte","fuente":"chats","largo":77}
{"kind":"chat_turn",...,"abismo_consultas":3,"latency_ms":85628}
```

**El tope quedo ejercitado en vivo:** el 7b escribio una CUARTA marca y, con el contador en 3, se
retiro sin cortar (`retirada / clase sin_corte / largo 77`).

### 3.2 -- lo que quedo en disco. PASA

```
$ python3 - (jq equivalente sobre $CALIPSO_HOME/chats.json)
user: /local usa la marca de consulta que te da tu contrato interno, fuente chats, ...
assistant: Empece "El nombre de la rosa", la novela de Umberto Eco, hace dos semanas...
n mensajes = 2

$ grep -c '⟦' $CALIPSO_HOME/chats.json          -> 0
$ grep -c 'Lo que subio' $CALIPSO_HOME/chats.json -> 0
$ grep -rl '⟦' $CALIPSO_HOME --include='*.json' --include='*.jsonl' --include='*.log'  -> ninguno
```

UN solo par user/assistant por turno, ni una marca ni un bloque pescado en ningun archivo del home
(chats, telemetry, costs, server.log). La fila `chat_turn` trae `abismo_consultas` (3 en el turno que
pesco, 0 en los turnos planos).

### 3.3 -- la fuente `proyecto`. NO EJERCITADA EN VIVO

```
$ ... "/local y de que proyecto estaba hablando en el catastro, el de calipso?"
   0.00 [thinking] ...  23.43 [done]      # ninguna marca; abismo_consultas = 0
$ ... "/local usa la marca de consulta de tu contrato con la fuente proyecto y el nombre calipso, y despues resumime en que anda ese repo"
   -> el turno se fue al ORQUESTADOR (plan/agent/agente Socrates via claude:haiku, 139 s); ninguna marca
$ ... "/local usa tu marca de consulta con la fuente proyecto y el nombre calipso, y contestame en una sola linea"
   -> 68.8 s, ninguna marca
```

Tres intentos, cero marcas de fuente `proyecto`. La ruta queda cubierta por los tests
(`test_abismo_chat.py` / `test_abismo_consulta`), no por este smoke.

### 3.4 -- el turno plano (invariante 3). PASA

```
$ ... "/local gracias"
tipos de evento: ['chat','chunk','cost','done','meta','thinking']
hay evento abismo: False
len visible = 81   len persistido = 81
md5 visible   = 6e1787153834b8e5f3a5c7761ad51c89
md5 persistido= 6e1787153834b8e5f3a5c7761ad51c89
IDENTICOS: True
telemetry: chat_turn abismo_consultas 0
```

Sin marca en el stream, los bytes que salieron del filtro son identicos a los que el server persistio.

### 3.5 -- el steer. PASA

Mensaje que provoca consulta y, apenas sale `pondering`, "otra cosa" en CRUDO por el mismo socket:

```
   0.46 t1 [meta] route local / qwen2.5:7b
  18.35 t1 [abismo] {"fase":"pondering","fuente":"chats","verbo":"buscando en tus chats"}
  18.41 t1 [abismo] {"fase":"pescado","fuente":"chats","tamano":478,"viaje":{"destino":"local"}}
        [CLIENTE] steer crudo enviado: 'otra cosa: decime solamente cuanto es dos mas dos'
  22.98 t1 [steered] {"type":"steered"}
  23.07 t1 [done]
  23.41 t1 [meta] route subscription / opus       <- el turno del steer
  29.47 t1 [done]

telemetry:
{"kind":"abismo","evento":"consulta","fuente":"chats","resultado":"pescado","chars":478,"destino":"local","consultas":1,"latencia_ms":3}
{"kind":"abismo","evento":"abortada_por_steer","consultas":1,"momento":"reentrada"}

chats.json:
  user      '/local usa la marca ... todo lo que me conto mariana'
  assistant 'M ...(interrumpido)'
  user      'otra cosa: decime solamente cuanto es dos mas dos'
  assistant '4'
grep -c 'Venias diciendo' chats.json -> 0 ; grep -c '⟦' chats.json -> 0
```

El steer gano: fila `abortada_por_steer` con `momento: reentrada`, el bloque pescado NO entro, lo
persistido del turno cortado es el visible con su cola honesta, y el turno siguiente contesta "otra
cosa". El momento `pesca` no se pudo ejercitar: con fuentes locales la pesca dura 3-7 ms, no hay
ventana para meter un steer adentro.

### 3.6 -- las UIs. PASA (con una salvedad y un hallazgo)

**PWA** (`http://127.0.0.1:8772/?token=...`), mismo mensaje del 3.1:

```
[+ 11.3s] META DEL ABISMO: ['del abismo: chats (811 chars)']
[+ 11.3s] .abismo tras la senal = 0
[fin] burbujas bot = 1
  burbuja 1 (136 chars): 'Empece "El nombre de la rosa", la novela de Umberto Eco, hace dos semanas. Voy por la parte de la biblioteca de la abadia.'
[fin] .abismo colgado = 0
[fin] metas = ['-> Platon - qwen2.5:7b ...', 'del abismo: chats (811 chars)', 'el abismo (chats): no trajo nada', '$ local - 2658 tokens - gratis']
```

Captura: `pwa.png`. Se ve UNA sola burbuja del bot con la respuesta completa, y los dos cierres del
abismo como renglones `meta` ("del abismo: chats (811 chars)" y "el abismo (chats): no trajo nada").
Ningun `.abismo` colgado al final.

**Salvedad honesta:** el renglon "buscando en tus chats... N s" NO se pudo fotografiar en la PWA. Con
fuentes locales el `pondering` vive 3-7 ms: nace y muere entre dos muestreos de 350 ms. Se lo ve de
verdad recien en la ruta /nube, donde el juez de privacidad mete 3-4 s (abajo).

**Fabrica** (`/fabrica`), con una `/nube` para que el renglon dure:

```
[+ 18.4s] PONDERING: 'buscando en tus chats... 0 s' | hermano de #conversacion=True
          hermano de #razonamiento=True | razonamiento visible=False
[+ 22.4s] PESCADO: 'del abismo: chats (261 chars, viajo tapado a la nube: [ID_1])' | detalle viaje visible=True
    viajeTexto = '=== Lo que subio del abismo (fuente: chats) ===\n[anillo 2]\n[Charla con Mariana
                  2026-08-20] Recordame devolverle el libro a [ID_1] cuando lo termine.\n[anillo 2]\n
                  [Charla con Mariana 2026-08-20] Entendido, lo anoto: [ID_1] te presto el libro y esta en tratamiento.'
[fin] abismo visible=False  texto='del abismo: chats (261 chars, viajo tapado a la nube: [ID_1])'  viaje visible=False
[fin] viajeTexto residual = '=== Lo que subio del abismo (fuente: chats) ===\n[anillo 2]\n[Charla con
                             Mariana 2026-08-20] Recordame devolverle el libro a [ID_1] ...'
```

Capturas: `fabrica-pondering.png`, `fabrica-pescado.png`, `fabrica.png`. El renglon es HERMANO del
`#conversacion` y del `#razonamiento` (el "pensando"): mismo padre, nunca un turno. Aparece en cursiva
al pie de la conversacion, desaparece con el `pescado`, y el desplegable "lo que viajo a la nube"
muestra el texto tapado exacto. La conversacion queda con UNA sola burbuja de Calipso.

**Hallazgo confirmado en vivo (H2):** al apagarse el renglon, `#abismo-viaje-texto` SIGUE con el texto
tapado del turno anterior en el DOM (`viajeTexto residual` no vacio). Es el minor que el ledger tenia
marcado como candidato al fix final; el smoke lo confirma.

## Paso 4 -- una /nube que muestra el viaje tapado

### 4.1 y 4.2 -- el viaje tapado. PASA

```
$ ... "/nube mi amiga Mariana Quintero me presto un libro. consulta mis chats viejos con tu marca y decime cual era"

  16.31 [privacidad] {"action":"tapado","tapados":[{"marcador":"[ID_1]","tipo":"identidad"}],
                      "texto_tapado":"mi amiga [ID_1] me presto un libro. consulta mis chats viejos ..."}
  16.31 [meta] route subscription / opus / Diogenes
  26.82 [abismo] {"fase":"pondering","fuente":"chats","verbo":"buscando en tus chats"}
  30.81 [abismo] {"fase":"pescado","fuente":"chats","tamano":261,
                  "viaje":{"destino":"nube",
                           "tapados":[{"marcador":"[ID_1]","tipo":"identidad"}],
                           "texto_tapado":"=== Lo que subio del abismo (fuente: chats) ===\n[anillo 2]\n
                             [Charla con Mariana 2026-08-20] Recordame devolverle el libro a [ID_1] cuando lo termine.\n
                             [anillo 2]\n[Charla con Mariana 2026-08-20] Entendido, lo anoto: [ID_1] te presto el
                             libro y esta en tratamiento."}}
  50.32 [abismo] {"fase":"pondering","fuente":"chats",...}
  52.82 [abismo] {"fase":"pescado","fuente":"chats","tamano":261,"viaje":{"destino":"nube","tapados":[{"marcador":"[ID_1]",...}]}}
  61.91 [done]

telemetry:
{"kind":"abismo","evento":"consulta","fuente":"chats","resultado":"pescado","chars":261,"destino":"nube","tapados":1,"consultas":1,"latencia_ms":3988}
{"kind":"abismo","evento":"reinvocacion_suscripcion","client":"claude","consultas":1}
{"kind":"abismo","evento":"consulta","fuente":"chats","resultado":"pescado","chars":261,"destino":"nube","tapados":1,"consultas":2,"latencia_ms":2495}
{"kind":"abismo","evento":"reinvocacion_suscripcion","client":"claude","consultas":2}
{"kind":"chat_turn","route_used":"subscription","client":"claude","abismo_consultas":2}
```

`viaje.destino == "nube"`, `tapados` con `[ID_1]`, y el `texto_tapado` sin el nombre de la persona.
La respuesta visible SI dice "Mariana Quintero" (el repuesto vuelve en la maquina, invariante 9: lo
que salio de aca fue el crudo tapado). Las dos reinvocaciones del CLI estan declaradas en telemetry.
`latencia_ms` 3988 y 2495: el juez de privacidad es el que cuesta, la pesca no.

El system del envio a la nube, verificado con sonda en proceso (no por el log, que solo tiene accesos
de uvicorn):

```
$ .venv/bin/python -c "import calipso.server as srv; print(srv._sistema_nube())"
Sos Calipso, el asistente de Pedro. ... marcadores como [ID_1], [SALUD_1] ...
=== El abismo ===
...
⟦abismo:proyecto nombre⟧ -- el detalle de un repo del catastro.        <- SIN nombres de repos
...
contiene 'Observatory-Global': False   contiene 'mapa-ciudad': False   contiene 'Mariana': False
```

### 4.3 -- los dos sumideros temporales. PASA

```
ANTES   ls /var/home/pedro/calipso/*.prompt.md | wc -l   -> 0
ANTES   ls ${TMPDIR:-/tmp}/tmp*.md | wc -l               -> 0
DESPUES (tras las cuatro /nube con dos invocaciones cada una)
        ls /var/home/pedro/calipso/*.prompt.md | wc -l   -> 0
        ls ${TMPDIR:-/tmp}/tmp*.md | wc -l               -> 0
```

Ni el `.prompt.md` dentro de ROOT ni el `tempfile` con `suffix=".md"` del tmpdir del sistema quedaron:
`_cleanup_subscription_files` los barre en el `finally` de las DOS invocaciones.

### 4.4 -- solo core (anillo 3) en /nube. NO EJERCITADO EN VIVO

La forma esta verificada con sonda directa contra el paquete:

```
$ .venv/bin/python -c "fuentes.memoria('bazzite ally maquina', mem) ; viaje.preparar_viaje(...)"
bloques:    [(3, 'del core:\nPedro vive en Medellin y programa en la ROG Ally con Bazzite.')]
viaje nube: {'estado': 'fallo', 'texto': '', 'tapados': [], 'motivo': 'solo_hondo'}
```

Pero los DOS intentos en vivo no llegaron a tener destino nube: el juez de privacidad LOCAL tumbo el
envio a `local` antes de salir (`{"type":"privacidad","action":"local","motivo":"credencial"}` en los
dos), y con destino local el anillo 3 esta permitido, asi que la senal fue `fallo/vacio`, no
`solo_hondo`. Queda como "no ejercitado en vivo, cubierto por `test_abismo_nube.py`".

## Paso 5 -- cierre del entorno. PASA

```
$ kill 261014 ; ps -p 261014 -> PID 261014 NO EXISTE
$ ss -lntp | grep -E ':(8000|8771|8772)' -> nada escuchando en 8000/8771/8772
$ curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8772/login -> 000 (server abajo)
$ grep -iE "traceback|error|exception" $CALIPSO_HOME/server.log -> ninguno
```

**La huella del `~/.calipso` REAL.** La receta del brief da un md5 distinto (antes
`9aeede35c3e3943416b4d906bf8c251e`, despues `509ef732d1a3b334ea42ff744587ef12`) y NO es porque algo
haya cambiado adentro: `ls -laR ~/.calipso` incluye la linea de `..`, o sea el mtime de `/home/pedro`,
que se mueve solo. Corriendo el md5 tres veces seguidas ya da tres resultados que cambian entre si.
La verificacion honesta:

```
$ for i in 1 2 3; do ls -laR --time-style=full-iso ~/.calipso | grep -v '<linea de ..>' | md5sum; done
5d45458b84ee05a442b64a41ef9e5165        (estable las tres veces)

$ find ~/.calipso -newermt "2026-09-08 18:44" | wc -l     -> 0
$ find ~/.calipso -type f -printf "%TY-%Tm-%Td %TH:%TM %p\n" | sort -r | head -3
2026-09-07 16:49 /home/pedro/.calipso/token
2026-09-07 16:49 /home/pedro/.calipso/logs/server.log
2026-09-03 15:41 /home/pedro/.calipso/routines.json
```

Cero archivos tocados dentro del home real desde que arranco el smoke (18:44); el mas reciente es de
ayer. El home real quedo INTACTO. Nota para el proximo smoke: la receta de la huella deberia excluir
la linea de `..`, o usar `find -newermt`, que es la que decide de verdad.

---

## Lo que quedo verificado

1. La marca CORTA el stream local, la senal `pondering` -> `pescado`/`fallo` sale con cierre siempre,
   y la reentrada continua en la MISMA burbuja: un solo `done`, un solo par user/assistant.
2. El tope de 3 consultas por turno, con la cuarta marca retirada sin cortar
   (`retirada / clase sin_corte`).
3. La marca y el bloque pescado JAMAS se persisten: cero `⟦` y cero "Lo que subio" en todo el home
   temporal (chats.json, telemetry.jsonl, costs.jsonl, server.log).
4. Invariante 3: sin marca en el stream, el texto visible es byte a byte el que se persiste
   (md5 identico).
5. El steer gana sobre la consulta en la reentrada: `abortada_por_steer` con `momento: reentrada`,
   bloque descartado, `steered`, y el turno siguiente contesta lo que Pedro pidio.
6. /nube: el viaje tapado real -- `viaje.destino == "nube"`, `tapados: [{marcador:"[ID_1]",
   tipo:"identidad"}]`, `texto_tapado` sin el nombre; dos reinvocaciones del CLI declaradas en
   telemetry; el system de nube sin nombres de repos ni datos de la persona.
7. Los dos sumideros temporales (el `.prompt.md` de ROOT y el `tmp*.md` del tmpdir) quedan en cero
   antes y despues.
8. Las dos UIs: el renglon del abismo es hermano del "pensando" y no un turno, desaparece con el
   `pescado`, la burbuja es UNA, y el desplegable de la fabrica muestra el texto tapado exacto.
9. El contrato en vivo: 583 chars (<= 600), termina en `CONSULTA.`, y sobrevive UN nombre de repo.

## Lo que NO quedo verificado

1. **La fuente `proyecto` en vivo** (tres intentos, cero marcas; uno se fue al orquestador).
2. **`fallo/solo_hondo` en /nube** (el juez tumbo los dos intentos a local antes del viaje).
3. **El steer en los momentos `corte` y `pesca`** (la pesca local dura 3-7 ms: no hay ventana).
4. **El renglon `pondering` con sus segundos en la PWA** (mismo motivo; se lo vio en la fabrica solo
   porque la /nube mete el juez de 4 s).
5. **El system de la segunda invocacion leido del cable**: `server.log` solo tiene accesos de uvicorn.
   Lo verificado es `_sistema_nube()` por sonda en proceso y el `texto_tapado` de la senal, no un
   volcado del prompt que salio.

## Hallazgos

- **H1 (Important).** `qwen2.5:7b` -- la ruta LOCAL, la del dia a dia en la Ally -- **no emite la
  marca por su cuenta**: 0 marcas en 6 turnos naturales (4 sobre chats, 2 sobre proyecto), incluso
  cuando le dijeron "no me lo inventes" y "busca en las charlas viejas". En el intento 4 confabulo
  ("Investigando nuestras charlas antiguas, no encontre ningun registro") sin haber consultado --
  exactamente lo que el contrato prohibe. Recien con el pedido explicito ("usa la marca de consulta
  que te da tu contrato interno, fuente chats, ...") emitio tres. Contraste: **opus por suscripcion
  la emitio sola, sin pedirsela, en el primer turno del smoke.** El contrato SI esta en el system
  local (verificado en `prompt_compiler.internal_contract`), pero ahi vive como cuarta seccion de
  diez, no al final del system como en el banco que midio la letra (el propio comentario del codigo
  lo declara y dice "queda anotado, no se re-mide"). El 1b esta bien cableado; la promesa "ante la
  duda, CONSULTA" no se sostiene todavia en la ruta local.
- **H2 (Minor, confirmado en vivo -- candidato al fix final por el ruling 1).** La fabrica no limpia
  `#abismo-viaje-texto` al apagar el renglon: terminado el turno, el DOM sigue con el bloque tapado
  del turno anterior (`=== Lo que subio del abismo ... [ID_1] ...`). No se ve, pero esta.
- **H3 (Minor, confirmado en vivo).** El "hueco visual" del renglon: con fuentes locales la pesca
  tarda 3-7 ms, asi que el `pondering` nace y muere dentro del mismo frame. El renglon con segundos
  solo es observable cuando el viaje a la nube agrega el juez (3.9-4.0 s medidos). La promesa de la
  seccion 9 se cumple en /nube, no en local.
- **H4 (Minor, preexistente, fuera del 1b pero le bloquea un paso al smoke).** El juez de privacidad
  local tumbo `/nube` a local en 3 de 5 intentos: una vez con `motivo: tipo_desconocido` y dos con
  `motivo: credencial`. Los dos `credencial` fueron con mensajes que contenian la formula "la palabra
  bazzite" / "las palabras bazzite ally maquina": huele a falso positivo del 7b sobre "palabra".
- **H5 (Minor, observado).** Lo que viajo tapado a la nube fue
  "[ID_1] te presto el libro y **esta en tratamiento**": el juez tapo el nombre (identidad) pero dejo
  pasar el dato de salud que venia en la misma linea. Es conducta del juez (Fase 2), no del abismo,
  pero el abismo AMPLIA la superficie: ahora sube a la nube texto viejo de los chats que Pedro no
  eligio mandar en ese turno.
- **H6 (Minor, preexistente, fuera del 1b).** `/local` no impidio que el turno corriera por el
  ORQUESTADOR con agentes de suscripcion (`claude:haiku`) cuando el mensaje tenia forma de repo:
  el `meta` dijo `route: local` y el `cost` del final dijo `route: orchestrator`.
- **H7 (metodologico, no del producto).** La memoria episodica guarda pregunta+respuesta de cada
  turno, asi que repetir la misma pregunta hace que el 7b copie su propia respuesta anterior en vez
  de consultar. En el intento 1 el 7b reprodujo VERBATIM (364 de 365 chars, un espacio de
  diferencia) la respuesta que opus habia dado al mismo mensaje. Hubo que borrar `global/chroma` y
  reiniciar el server entre corridas para medir limpio. Vale para el proximo smoke.
