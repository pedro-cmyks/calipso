# Re-smoke en vivo abreviado del abismo 1b, tras la ola de fix (8 de septiembre de 2026)

Rama `feat/abismo-1b`, HEAD `7011b9b4bbfa3cbf1bc61594762eafa44e793a03` (bifurcada de main en
`c645ccd`). Arbol limpio al arrancar y al cerrar; nada commiteado en esta ronda.
Guion: `task-13-brief.md` Steps 1-3 y 5, abreviado por encargo del controlador a
**arranque + siembra, 3.1, 3.2, 3.4 y 3.5**. El smoke completo previo (sobre `745a7d8`, pre-fix)
vive en `docs/superpowers/2026-09-08-smoke-abismo-1b.md`; este informe es el diferencial.

## Entorno

Server DESECHABLE en `127.0.0.1:8772`, jamas el real ni el 8000. Sin `CALIPSO_NO_TOTP`.
Ollama REAL de la Ally (`qwen2.5:7b` en `:11434`).

```
export CALIPSO_HOME=/tmp/claude-1000/-var-home-pedro/7ea3cff5-be99-4946-a05c-6203e4bc2f84/scratchpad/re-smoke-home-kwGd     # temporal NUEVO y vacio (mktemp -d), distinto al del smoke previo
export CALIPSO_TOKEN=<32 chars de secrets.token_urlsafe(24)>
cd /var/home/pedro/calipso
.venv/bin/python -m uvicorn calipso.server:app --host 127.0.0.1 --port 8772 > $CALIPSO_HOME/server.log 2>&1 &
```

- Puertos antes de arrancar: solo `127.0.0.1:11434` (ollama). Nada en 8000 ni en 8772.
  Ningun proceso `uvicorn`/`calipso.server` corriendo.
- Huella del `~/.calipso` REAL antes (receta honesta del smoke previo: `ls -laR` sin la linea de
  `..`, que arrastra el mtime de `/home/pedro` y se mueve solo):
  `5d45458b84ee05a442b64a41ef9e5165`. Ademas un inventario `find ~/.calipso -printf "%y %s %T@ %p"`
  de 755 lineas (`re-home-antes.inv`), que es el que decide de verdad.
- Home temporal sembrado igual que la vez pasada: `catastro.json` COPIADO del real (solo lectura del
  real), `global/core/pedro-perfil.md` con dos lineas del perfil, y `chats.json` con las dos
  conversaciones viejas -- "Libros de agosto" (El nombre de la rosa, Umberto Eco, 2026-08-14) y
  "Charla con Mariana" (Mariana Quintero presto el libro; le diagnosticaron hipotiroidismo; 2026-08-20),
  formato `{"active": null, "chats": {<id>: {...}}}` con `ts` ISO.
- Cliente: `chat_live.py` del smoke previo copiado al home nuevo (WS a `127.0.0.1:8772`, cada evento
  crudo con hora y latencia, `--jsonl`, `--steer-tras-pondering`, `--dones`).
- `chroma` arranca VACIO (home nuevo): la contaminacion episodica del H7 previo no juega en 3.1.

---

## Paso 1 -- server desechable y siembra. PASA

```
login=200 tras 10 intentos
PID=429379
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8772 (Press CTRL+C to quit)
ss -ltn -> LISTEN 127.0.0.1:8772        (y nada en 8000)
```

El contrato medido en vivo con el home del smoke (identico al de la ronda previa: la ola de fix no
toco `contrato.py`):

```
catastro.nombres() = ['calipso', 'Observatory-Global', 'mapa-ciudad']
len(bloque_contrato(nombres)) = 583        # <= 600
termina en CONSULTA. -> True
linea repo -> '⟦abismo:proyecto nombre⟧ -- repo: calipso y 2 mas.'
len(bloque_contrato(())) = 596
nombres que sobreviven en el bloque: ['calipso'] -> 1
```

Sigue sobreviviendo UN solo nombre; `Observatory-Global` y `mapa-ciudad` caen a la cola honesta.

## Paso 3.1 -- la conversacion local que pesca. PASA (al PRIMER intento)

Mismo mensaje que la vez pasada necesito cinco intentos para conseguir (el 7b no emite la marca
sola: H1). Con el chroma vacio y el pedido explicito, salio a la primera:

```
[turno 1] -> '/local usa la marca de consulta que te da tu contrato interno, fuente chats,
              con las palabras libro rosa novela, y despues contame que libro empece'

21:11:51.050 (+  0.00s) [chat]     {"action":"active","chat":{"id":"b23da050882e", ... "messages":[]}}
21:11:51.052 (+  0.00s) [meta]     route local / qwen2.5:7b / Platon
21:12:36.434 (+ 45.39s) [abismo]   {"fase":"pondering","fuente":"chats","verbo":"buscando en tus chats"}
21:12:36.442 (+ 45.39s) [abismo]   {"fase":"pescado","fuente":"chats","tamano":811,"viaje":{"destino":"local"}}
21:12:47.620 (+ 56.57s) [abismo]   {"fase":"pondering","fuente":"chats","verbo":"buscando en tus chats"}
21:12:47.626 (+ 56.58s) [abismo]   {"fase":"fallo","fuente":"chats","motivo":"vacio"}
21:12:53.317 (+ 62.27s) [cost]     qwen2.5:7b / local / 2716 tokens / 0.0
21:12:53.452 (+ 62.40s) [done]

--- texto visible (167 chars, 48 chunks, 1 done) ---
Mariana Quintero me prestó el libro "El nombre de la rosa" de Umberto Eco. Llegué a la parte donde
se introduce Guillermo de Baskerville en la biblioteca de la abadía.
```

`pondering` con fuente `chats` y verbo, `pescado` con `viaje.destino == "local"` y `tamano 811 > 0`,
la continuacion en la MISMA burbuja (48 chunks, UN solo `done`), y las dos senales con su cierre.
Latencia del pondering medida en el cliente: 8 ms y 6 ms; `latencia_ms` del server: 3 y 0.
La respuesta es el dato sembrado, no una invencion.

Visible vs persistido del mismo turno (la reentrada no duplica ni recorta):

```
3.1 visible len 167 | persistido len 167 | iguales: True
md5 125416691ff1f5e36e9ac45d00a0260f == 125416691ff1f5e36e9ac45d00a0260f
```

## Paso 3.2 -- lo que quedo en disco. PASA

```
chat activo: b23da050882e
n mensajes = 2
  user      : /local usa la marca de consulta que te da tu contrato interno, fuente chats, ...
  assistant : Mariana Quintero me prestó el libro "El nombre de la rosa" de Umberto Eco. ...

grep -c '⟦' chats.json           -> 0
grep -c 'Lo que subio' chats.json -> 0
grep -rl '⟦' $CALIPSO_HOME (json/jsonl/log/txt)   -> ninguno
grep -rl 'Lo que subio' $CALIPSO_HOME             -> ninguno

telemetry.jsonl:
{"kind":"abismo","evento":"consulta","fuente":"chats","resultado":"pescado","chars":811,"destino":"local","tapados":0,"consultas":1,"latencia_ms":3}
{"kind":"abismo","evento":"consulta","fuente":"chats","resultado":"fallo","motivo":"vacio","destino":"local","consultas":2,"latencia_ms":0}
{"kind":"chat_turn",...,"route_used":"local","abismo_consultas":2,"latency_ms":62268}
```

UN solo par user/assistant, ni una marca ni un bloque pescado en ningun archivo del home
(chats, telemetry, costs, server.log). `abismo_consultas` es 2 y no 1 porque el 7b escribio dos
marcas (la segunda no pesco nada): el contador cuenta consultas, no marcas exitosas.

### Verificacion extra de esta ronda: el fix h04 en vivo

El unico fix de la ola que cambia lo que el smoke MIDE es h04 (la fuente `chats` deja fuera lo que el
modelo ya tiene del chat activo). Sonda en proceso contra el home del smoke, con el chat `b23da050882e`
ya cargado (6 mensajes), reproduciendo los tres regimenes:

```
_HISTORY_TURNS = 12
sin chat_activo (regimen pre-fix): pescado, 1368 chars
local (ventana del historial fuera, en_contexto=13): pescado, 811 chars
nube (chat activo entero fuera, en_contexto=None):   pescado, 811 chars

la PREGUNTA de Pedro esta en el bloque?  pre-fix: True  | local: False | nube: False
la RESPUESTA del turno previo esta?      pre-fix: True  | local: False | nube: False
el chat VIEJO sembrado esta?                           | local: True  | nube: True
```

Los 811 chars de la senal en vivo son exactamente los del regimen local: el server pasa la ventana
correcta. Pre-fix ese mismo bloque habria devuelto 1368 chars con la pregunta de Pedro y la respuesta
del turno anterior adentro.

## Paso 3.4 -- el turno plano (invariante 3). PASA

```
[turno 1] -> '/local gracias'
tipos de evento: ['chat','chunk','cost','done','meta','thinking']
hay evento abismo: False
len visible = 63   len persistido = 63
md5 visible    = 0594cc53f1aaef5992c8888dc9081f42
md5 persistido = 0594cc53f1aaef5992c8888dc9081f42
IDENTICOS: True
telemetry chat_turn: abismo_consultas = 0 | route_used = local
filas 'kind:abismo' en telemetry tras el turno plano: 2  (las dos del 3.1; el turno plano no sumo)
```

Sin marca en el stream el filtro es transparente: los bytes que salieron son los que se persistieron.

## Paso 3.5 -- el steer. PASA (con un intento previo fallido que dejo un dato)

**Intento A (descartado, dato util).** Mismo chat que el 3.1, mensaje pidiendo la marca sobre
"mariana libro prestado": el 7b **no emitio ninguna marca** (0 eventos `abismo`), asi que el cliente
nunca tuvo un `pondering` sobre el cual disparar el steer y el turno murio esperando el segundo
`done` (TimeoutError del cliente a los 300 s; el server cerro su turno bien a los 21.3 s).
Lo que contesto, sin consultar:

```
"Mariana Quintero me prestó el libro El nombre de la rosa ... Mariana no mencionó otros detalles
 específicos sobre el libro o la entrega, solo este pasaje inicial que me ha relatado."
```

El chat activo YA tenia la respuesta del 3.1 en su historial, asi que el modelo la reciclo y ademas
afirmo una AUSENCIA falsa ("no mencionó otros detalles"): el chat sembrado si tiene mas (el
hipotiroidismo y el tratamiento). Es el H1 del smoke previo reconfirmado en su forma mas fea
(confabulacion de ausencia), no una regresion de la ola de fix.

**Intento B (el que cuenta).** Chat NUEVO (`POST /api/chats`, id `529311c52012`) y una pregunta cuya
respuesta no estaba en el historial. Steer en CRUDO por el mismo socket 50 ms despues del `pondering`:

```
21:20:07.215 (+  0.24s) [meta]     route local / qwen2.5:7b
21:20:55.898 (+ 48.92s) [abismo]   {"fase":"pondering","fuente":"chats","verbo":"buscando en tus chats"}
21:20:55.950 (+ 48.97s) [CLIENTE]  steer crudo enviado: '/local otra cosa: decime solamente cuanto es dos mas dos'
21:20:55.950 (+ 48.97s) [abismo]   {"fase":"pescado","fuente":"chats","tamano":367,"viaje":{"destino":"local"}}
21:20:59.770 (+ 52.79s) [steered]  {"type":"steered"}
21:20:59.857 (+ 52.88s) [done]                       <- cierre del turno cortado
21:20:59.857 (+ 52.88s) [thinking]                   <- el turno del steer
21:21:11.882 (+ 64.90s) [done]

telemetry:
{"kind":"abismo","evento":"consulta","fuente":"chats","resultado":"pescado","chars":367,"destino":"local","tapados":0,"consultas":1,"latencia_ms":0}
{"kind":"abismo","evento":"abortada_por_steer","consultas":1,"momento":"reentrada"}
chat_turn 1: abismo_consultas 1 | route local | response_chars 18
chat_turn 2: abismo_consultas 0 | route local | response_chars 43

chats.json (chat 529311c52012, 4 mensajes = dos pares limpios):
  user      '/local usa la marca ... contame que me conto mariana de su salud'
  assistant 'M …(interrumpido)'
  user      '/local otra cosa: decime solamente cuanto es dos mas dos'
  assistant 'Dos más dos es cuatro. ¿Necesitas algo más?'

grep -c 'Venias diciendo' chats.json -> 0
grep -c 'Venias diciendo' server.log -> 0
grep -c '⟦' chats.json               -> 0
grep -rl 'Lo que subio' $CALIPSO_HOME -> ninguno
```

El steer gano: fila `abortada_por_steer` con `momento: reentrada`, el bloque pescado (367 chars) NO
entro, lo persistido del turno cortado es el visible con su cola honesta, y el turno siguiente
contesta "otra cosa". El momento `pesca` sigue sin ventana en vivo (la pesca local tarda 0-3 ms).

Nota: el steer se mando con prefijo `/local` para que el turno del steer no gastara una invocacion de
suscripcion (en el smoke previo ese turno se fue a opus). No cambia lo que el paso mide.

## Paso 5 -- cierre del entorno. PASA

```
grep -iE "traceback|exception|error" $CALIPSO_HOME/server.log -> ninguno
kill 429379 ; ps -p 429379 -> PID 429379 NO EXISTE
ss -ltn | grep -E ':(8000|8771|8772)' -> nada escuchando
curl -m 3 http://127.0.0.1:8772/login -> 000
pgrep -af "uvicorn calipso|calipso.server" -> ninguno
ls /var/home/pedro/calipso/*.prompt.md | wc -l -> 0
git status --porcelain -> vacio ; HEAD 7011b9b
```

Huella del `~/.calipso` REAL despues:

```
for i in 1 2 3; do ls -laR --time-style=full-iso ~/.calipso | grep -v '<linea de ..>' | md5sum; done
5d45458b84ee05a442b64a41ef9e5165   (las tres veces, IDENTICO al de antes)

diff re-home-antes.inv re-home-despues.inv -> sin diferencias (755 lineas, path/size/mtime)
find ~/.calipso -newermt "2026-09-08 21:10:00" | wc -l -> 0
mas reciente del home real: 2026-09-07 16:49 /home/pedro/.calipso/token
```

El home real quedo INTACTO: mismo md5 estable, inventario identico linea por linea, cero archivos
tocados desde que arranco el re-smoke.

---

## Resultado por paso

| Paso | Resultado | Nota |
|---|---|---|
| 1 arranque + siembra | PASA | login 200; contrato 583 chars, termina en CONSULTA., 1 nombre sobrevive |
| 3.1 conversacion local que pesca | PASA | pondering/pescado(811, destino local)/pondering/fallo(vacio), 1 done, 1 burbuja; al primer intento |
| 3.2 lo que quedo en disco | PASA | 1 par user/assistant, cero `⟦` y cero "Lo que subio" en todo el home; telemetry con `abismo_consultas` |
| 3.4 turno plano | PASA | sin evento abismo, md5 visible == md5 persistido |
| 3.5 steer | PASA | `abortada_por_steer` momento `reentrada`, bloque descartado, sin "Venias diciendo" en disco, el turno siguiente contesta el steer |
| 5 cierre | PASA | server muerto, puertos libres, home real identico (md5 + inventario + `find -newermt`) |

## Lo que la ola de fix cambio para este smoke

- **h04 confirmado en vivo:** el bloque de la fuente `chats` ya no trae la pregunta de Pedro ni la
  respuesta del turno anterior del chat activo (1368 -> 811 chars en la sonda de los tres regimenes).
- Los otros fixes de la ola (h01, h02, h03, m1, m2, m3) viven en la ruta one-shot / suscripcion / el
  harness, que esta ronda abreviada NO ejercita: quedan cubiertos por sus tests y por el smoke previo.
- **Nada de lo que el smoke previo daba por PASA se rompio:** las cuatro pruebas repetidas dieron el
  mismo resultado, con los mismos numeros donde son comparables (contrato 583/596/1 nombre, bloque de
  811 chars, un solo par, cero marcas en disco, md5 identicos, `momento: reentrada`).

## Lo que NO se ejercito en esta ronda (por encargo)

Paso 2 (el cliente, reusado tal cual), 3.3 (fuente `proyecto`), 3.6 (las dos UIs y las capturas),
y el Paso 4 entero (/nube, viaje tapado, sumideros temporales, `solo_hondo`). El estado de esos pasos
es el del informe previo, `docs/superpowers/2026-09-08-smoke-abismo-1b.md`.

## Hallazgos

- **F1 (Important, H1 reconfirmado, no es regresion).** `qwen2.5:7b` sigue sin emitir la marca por su
  cuenta y ahora se lo vio confabular una AUSENCIA: con la respuesta del turno previo en el historial
  contesto "Mariana no mencionó otros detalles específicos" cuando el chat sembrado si los tiene
  (hipotiroidismo, tratamiento), sin consultar. Es exactamente lo que el contrato prohibe
  ("prohibido 'segun mis registros' sin consultar"). Coincide con lo medido en h05 (el system de
  produccion le borra al contrato la mejora entera): la bifurcacion sigue siendo de Pedro (spec 12).
- **F2 (Minor, metodologico).** El H7 del smoke previo (contaminacion episodica) tiene un hermano mas
  barato: el HISTORIAL del chat activo. Repetir una pregunta parecida en el mismo chat hace que el
  modelo recicle su respuesta anterior y no consulte -- y eso ahora es CORRECTO por diseno (h04: lo
  que el modelo ya tiene no se vuelve a pescar). Para medir la pesca hay que abrir un chat nuevo
  (`POST /api/chats`) por prueba. Anotado para el proximo smoke.
- **F3 (Minor, del cliente del smoke, no del producto).** `chat_live.py --steer-tras-pondering` solo
  dispara el steer si sale un `pondering`; si el modelo no emite marca, el cliente espera el segundo
  `done` hasta el timeout de 300 s. Conviene un plazo por turno o un steer por tiempo ademas de por
  fase. No afecta al server (cerro su turno en 21 s, limpio).

## Veredicto

Los cuatro pasos ejercitados PASAN sobre `7011b9b`, con los mismos numeros que la ronda previa donde
son comparables, mas la confirmacion en vivo del fix h04. El server desechable quedo apagado y el
`~/.calipso` real intacto. Nada de esta ronda se commiteo.
