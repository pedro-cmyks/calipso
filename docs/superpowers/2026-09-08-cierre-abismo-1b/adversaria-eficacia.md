# Adversaria EFICACIA -- feat/abismo-1b (HEAD 745a7d8 sobre main c645ccd)

Lente: las nueve invariantes de la seccion 13 del spec, atacadas con sondas ejecutadas contra el codigo de la
rama. Arma: el harness de `test_abismo_chat.py` (fixture `chat`, `ModeloEspia` con guiones), el CLI falso de
`test_abismo_suscripcion.py` (y una variante propia que puede fallar con `exit 1` y escribir a stderr), el juez
doble de `test_abismo_nube.py`. Cuatro archivos de sonda en el scratchpad, fuera del arbol de tests, con
`CALIPSO_HOME` a un temporal antes del import; corridos con `.venv/bin/python -m pytest -q -p no:cacheprovider -s`.
Borrados al terminar; el codigo relevante de cada sonda va condensado abajo, con su salida textual.

Regla de oro respetada: solo se reporta lo reproducido (salida citada) o lo que el codigo muestra sin ambiguedad
(file:line + razonamiento). Lo no reproducido se dice como tal en el resumen final.

Resultado de las corridas: tanda 1, 24/25 (la unica falla es una asercion mia, ver S5); tanda 2, 4/6 (las dos
fallas son de mi sonda y llevaron a la tanda 3); tanda 3, 3/3; tanda 4, 1/1.

## Hallazgos

### [I1] Important -- ruta one-shot (suscripcion): el filtro del Emisor corta o retiene por su cuenta y nadie lo consume: el resto del turno se traga EN SILENCIO (S11a, S11b, S3b)

`calipso/server.py:3648-3657`: la rama de suscripcion decide el corte con `abismo_turno.cortar_en_marca(texto)`
(PATRON + `parsear` sobre el texto crudo) y despues pasa `visible` por `emisor.chunk(visible)`, que es la tuberia
foco -> `FiltroAbismo` con estado y `puede_cortar=estado_abismo.puede_cortar`. El bucle one-shot **nunca llama a
`emisor.marca_abismo()`** ni cierra la retencion entre invocaciones. Cuando el filtro juzga distinto que PATRON, el
filtro corta (`_marca` pendiente, `comer` devuelve "" para siempre en ese turno) o retiene un prefijo a traves de
la pesca. Tres disparadores reproducidos, los tres sin senal `abismo`, sin fila `retirada`, sin nada en telemetry:

- **S11a** (foco anidado dentro de la marca): PATRON no admite corchetes en el cuerpo, asi que `cortar_en_marca` no ve
  marca; el filtro de foco (que corre ANTES en la tuberia) saca `⟦foco:atlas⟧`, y el del abismo ve una marca VALIDA y
  corta. El test `test_las_dos_rutas_de_retiro_juzgan_igual_el_empalme` usa exactamente este texto (`EMPALMES[1]`) y
  su asercion (`marca.encontrar(visible) == []`) pasa porque `visible` es solo lo anterior al corte: no ve que la
  tuberia corto.
- **S11b** (/nube /claude): `visible = redaccion.reponer(tramo_crudo, mapa)` corre ANTES del filtro (`:3655-3657`):
  una marca ilegible en crudo por largo (161 chars con cinco `[ID_1]`) queda en 156 tras reponer `Marta` y el filtro
  la toma por valida.
- **S3b** (doble apertura `⟦abismo:⟦abismo:chats libro⟧`): `tramo_crudo` termina en `⟦abismo:` (prefijo retenible),
  el filtro lo retiene durante la pesca y la reinvocacion; la reentrada ENTERA ("y sigo con contexto") cae en
  `cerrar()` como `abierta` y se descarta. Dos invocaciones reales del CLI pagadas para no mostrar nada.

Sonda (condensada):

```python
# S11a
cli_falso.guion([{"partes": ["Dejame ver ⟦abismo:chats libro ⟦foco:atlas⟧ x⟧ y esto sigue"], "pausa": 0},
                 {"partes": ["NO deberia reinvocar"], "pausa": 0}])
ev = chat.turno("/claude libro")
# S11b
_juez_que_tapa_nombres(monkeypatch); _sembrar_chat_viejo(["con Marta hablamos del libro"])
cuerpo_crudo = "chats " + "x" * 120 + " [ID_1]" * 5       # 161 chars: ilegible en crudo
cli_falso.guion([{"partes": ["Le dije ⟦abismo:" + cuerpo_crudo + "⟧ y esto sigue"], "pausa": 0}])
ev = chat.turno("/nube /claude que hablamos con Marta del libro")
# S3b
cli_falso.guion([{"partes": ["Dejame ver ⟦abismo:⟦abismo:chats libro⟧"], "pausa": 0},
                 {"partes": ["y sigo con contexto"], "pausa": 0}])
ev = chat.turno("/claude libro")
```

Salida:

```
S11a visible: 'Dejame ver ' fases: [] cli: 1 avisos: [] persistido: 'Dejame ver'
S11b visible: 'Le dije ' fases: [] cli: 1 avisos: []
S3b fases: [('pondering', None), ('pescado', None)] visible: 'Dejame ver ' cli: 2 avisos: ['abierta'] persistido: 'Dejame ver'
```

Contraste en streaming (T3, misma marca con foco anidado): ahi el bucle si consume `marca_abismo()` y la consulta
corre (`fases: [pondering, pescado]`, visible `'Dejame ver z'`), o sea que la tuberia viva actua sobre una marca que
PATRON (el detector one-shot y el banco) rechaza: las dos gramaticas divergen y la ruta one-shot es la que paga.

Probabilidad baja (el modelo tiene que anidar marcas o escribir una de mas de 160 chars con marcadores); consecuencia
alta (perdida silenciosa del resto de la respuesta, sin rastro). Direccion de arreglo: en la ruta one-shot el
filtro no debe poder cortar (un `puede_cortar` que devuelva False mientras el corte lo decide `cortar_en_marca`, con
la marca retirada con aviso), y consumir/cerrar el estado del filtro entre invocaciones; o bien consumir
`emisor.marca_abismo()` tras cada `chunk` y tratarla.

### [I2] Important -- la reinvocacion del CLI que falla termina el turno en silencio con el tramo a medias: ni fallback, ni `error`, ni `meta` (U1, U2)

`calipso/server.py:3856-3858`:

```python
                        if full:
                            pass
                    if full and used_route == "subscription":
                        pass
                    else:
                        ... fallback a local ...
```

En main esa rama era el camino de EXITO del alterno (con `full` recien asignado por `full, queued = await
_run_subscription_text_live(...)`, que solo asigna si la llamada vuelve; si reventaba, `full` seguia en `""` y caia
al fallback local). Con el bucle one-shot del 1b, `full` ya lleva el tramo visible cuando la REINVOCACION revienta,
asi que la rama la alcanza un fallo: sin alterno (U1) o con alterno que tambien falla (U2) no pasa nada: el turno
sigue a `emisor.cerrar()`, `cost`, persiste "Dejame ver" y manda `done`. Pedro ve "Dejame ver " y la burbuja se
cierra; en telemetry `chat_turn.fallbacks` queda `[]` (U1) y `route_used: subscription`. El modelo local nunca se
llama. La pesca fue exitosa (`pescado`) y el bloque se tiro. Viola el espiritu de "fallo cerrado: seguir sin
contexto extra, nunca romper el turno": el turno no rompe, se amputa sin aviso.

Sonda (CLI propio: llamada 0 escribe la marca; llamadas siguientes `exit 1`):

```python
_cli_a_medida(tmp_path, monkeypatch, '''
    if n == 0: sys.stdout.write("Dejame ver ⟦abismo:chats libro⟧")
    else: sys.stderr.write("boom en la reinvocacion"); sys.exit(1)
''')
monkeypatch.setattr(srv, "_best_subscription_client", lambda p: None)   # U1; U2: lambda p: "codex"
chat.modelo.guiones = [["respuesta local desde cero"]]
ev = _turno_con_un_solo_done(chat, "/claude libro")
```

Salida:

```
U1 tipos: ['thinking', 'meta', 'process', 'process', 'chunk', 'abismo', 'abismo', 'process', 'cost', 'chat', 'done']
U1 visible: 'Dejame ver ' fases: [('pondering', None), ('pescado', None)] cli llamadas: 2 llamadas al modelo local: 0 error events: [] meta notes: [None] chat_turn.fallbacks: [] route_used: subscription persistido: 'Dejame ver'
U2 tipos: ['thinking', 'meta', 'process', 'process', 'chunk', 'abismo', 'abismo', 'process', 'meta', 'process', 'cost', 'chat', 'done']
U2 visible: 'Dejame ver ' cli llamadas: 3 llamadas al modelo local: 0 error events: [] meta notes: [None, 'fallback entre suscripciones'] chat_turn.fallbacks: [{'from': 'claude', 'to': 'codex', 'error': 'boom'}] route_used: subscription
```

Nota: el `process` del job fallido tampoco manda `process/failed` por el WS (la rama `returncode != 0` de
`_run_subscription_text_live` solo escribe en jobs), asi que la UI no tiene ni ese indicio.

### [I3] Important -- la fuente `chats` pesca el chat ACTIVO y la propia pregunta: desplaza a los chats viejos y, en /nube, manda a la nube turnos previos locales de la misma conversacion (T1, T1b, V1)

`calipso/abismo/fuentes.py:59-75`: `for chat in chats.todos()` sin excluir el chat activo; `hallados.sort(reverse=True)`
(mas reciente primero) y `CHATS_MAX_FRAGMENTOS = 8`. `_pescar_abismo` no pasa `chat_id`. Y el cableado del 1b pesca
DESPUES de `chats.append(chat_id, "user", user_msg)` (`server.py`, arriba del `thinking`), asi que el mensaje actual
de Pedro es siempre el hallado mas reciente. Dos consecuencias:

1. **Eficacia**: la fuente existe para llegar "mas alla de los 12 mensajes de `_HISTORY_TURNS`" (spec seccion 1); con
   un chat activo de nueve mensajes que comparten la palabra clave, el bloque (624 chars) son la propia pregunta mas
   siete mensajes recientes que el modelo YA tiene en `messages`, y el unico chat viejo queda fuera del tope de 8. El
   smoke no lo ve porque su `chats.json` sembrado es chico.
2. **/nube**: la Fase 2a dejo la conversacion fuera de todo envio a la nube (`chat_id_nube = None`, "para no filtrar un
   turno privado anterior de la misma conversacion"); la fuente `chats` la vuelve a meter por el bloque. Va tapada por
   el juez (V1: `Marta` -> `[ID_1]`), pero un turno previo LOCAL, que nunca fue /nube, viaja: el canal "sin historial"
   que el spec 8.2 declara cerrado queda perforado por la fuente. Es una decision que el spec no toma explicitamente
   (seccion 6 dice que el historial de chats es anillo 2 y viaja redactado); conviene tomarla a proposito.

Sonda:

```python
# T1
_sembrar_chat_viejo(["empece El nombre de la rosa, un libro alucinante"])
for i in range(9):
    chats.append(chat.chat_id, "user" if i % 2 == 0 else "assistant", f"mensaje reciente {i} sobre el libro de siempre")
chat.modelo.guiones = [["a ⟦abismo:chats libro⟧"], ["b"]]
ev = chat.turno("que libro lei")
# V1
_juez_que_tapa_nombres(monkeypatch)
chats.append(chat.chat_id, "user", "el libro que me presto Marta es de cocina")
chats.append(chat.chat_id, "assistant", "que bueno ese libro de Marta")
chat.modelo.guiones = [["Dejame ver ", "⟦abismo:chats libro⟧"], ["y seguimos"]]
ev = _turno_con_un_solo_done(chat, "/nube /api que libro era")
```

Salida:

```
T1 fragmentos del bloque (mas reciente primero):
    [prueba 2026-09-08] que libro lei
    [prueba 2026-09-08] mensaje reciente 8 sobre el libro de siempre
    ... (7 del chat activo) ...
T1 el chat viejo entro: False | la propia pregunta entro: True | fragmentos del chat activo: 7 | tamano: 624
T1b chats_viejos('libro') -> ['[prueba 2026-09-08] que libro lei', '[lecturas 2026-09-08] empece El nombre de la ']
V1 viaje: {"destino": "nube", "tapados": [{"marcador": "[ID_1]", "tipo": "identidad"}], "texto_tapado": "=== Lo que subio del abismo (fuente: chats) ===\n[anillo 2]\n[prueba 2026-09-08] que bueno ese libro de [ID_1]\n[anillo 2]\n[prueba 2026-09-08] el libro que me presto [ID_1] es de cocina"}
V1 'presto' (turno previo local) en el system a la nube: True | 'cocina': True | Marta cruda: False | historial (messages) de la reentrada: ['system', 'user']
```

Arreglo barato: `chats_viejos` recibe el `chat_id` activo y lo excluye (o excluye el ultimo mensaje y los
`_HISTORY_TURNS` del activo). La fuente es del 1a, pero el cableado del 1b es quien la hace morder.

### [M1] Minor -- la camara vuela a un foco cosechado del texto DESCARTADO tras el corte (S2)

`calipso/server.py:7444-7452` (`Emisor._cosechar`) publica `tomar_focos()` de todos los filtros despues de `comer`;
el filtro de foco proceso el chunk ENTERO antes de que el del abismo cortara, y `marca_abismo()` (`:7479`,
`previo.cerrar()`) descarta la cola retenida pero no los focos ya cosechados. Pedro nunca leyo "atlas" y el pulso
publica `foco dep:atlas`.

```python
monkeypatch.setattr(srv, "_resolver_foco", lambda n: "dep:" + n)
chat.modelo.guiones = [["a ⟦abismo:chats libro⟧ luego ⟦foco:atlas⟧ nada"], ["z"]]
ev = chat.turno("libro")
```

```
S2 visible: 'a z' focos en el pulso: ['dep:atlas']
```

### [M2] Minor -- `stderr.txt` de jobs es el unico sumidero de disco sin `_limpiar_marcas` (S17)

`calipso/server.py:3110, :3146, :3161`: `jobs.write_artifact(..., "stderr.txt", stderr)` crudo, mientras `output.txt`,
`partial-output.txt` y el `msg` del error pasan por `_limpiar_marcas`. Reproducido el MECANISMO con un CLI falso que
escribe a stderr; no se demostro que el CLI real vuelque el system (contrato con marcas de ejemplo, o el bloque de la
reinvocacion) a stderr. Si lo hace en algun error, el bloque pescado queda en disco.

```
S17 stderr.txt: 'log: el system decia ⟦abismo:chats libro⟧ y === Lo que subio del abismo (fuente: chats) === bloque'
```

### [M3] Minor -- steer durante la pesca en one-shot: sin `steered`, sin fila `abortada_por_steer` con `momento`, y el texto posterior sin contexto se muestra igual (S5b)

`calipso/server.py:3675-3690`: si `_pescar_abismo` devuelve False por el steer (que solo MIRA el inbox), el bucle
one-shot entra en `if not hubo_bloque:` como si fuera una pesca vacia: emite el posterior y sale; el steer queda en el
inbox y es el turno siguiente, sin `steered` (en streaming el tope del bucle lo manda) y sin la fila con `momento`
que la ruta en vivo escribe. La senal cierra en `fallo`, asi que no cuelga; la asimetria es de UI y telemetry, y de
"lo que ve Pedro" (lee un posterior que el modelo escribio sin contexto y encima ya habia steereado).

```
S5b oneshot fases: [('pondering', None), ('fallo', 'error')] steered: False visible: 'Dejame ver  posterior sin contexto...' cli: 1 telemetria: [('consulta', None, 'abortada_por_steer'), ('retirada', None, None)] roles: [('user', '/claude que '), ('assistant', 'Dejame ver  '), ('user', 'otra cosa'), ('assistant', 'hola Pedro')]
```

### [M4] Minor -- una "marca" con cuerpo de 401+ chars escapa cruda a Pedro y se PERSISTE en chats.json y en memoria (S4)

`calipso/abismo/filtro.py:47-49, :90` y `marca.PATRON` (`{1,400}`): coherentes entre si a proposito (el test
`test_el_tope_del_cuerpo_es_el_mismo_que_el_de_patron` lo afirma), pero el resultado es que `⟦abismo:` + 401 chars +
`⟧` es texto: sale entero al WS, a `chats.json` (donde la propia fuente `chats` la pescaria) y a `mem.remember`.
Contra la letra "la marca JAMAS se persiste". `_limpiar_marcas` tampoco la saca. Con 400 se retira como `ilegible`.

```
S4 400 visible: 'a  b' avisos: ['ilegible']
S4 401 visible len: 414 empieza: 'a ⟦abismo:zzzzzzzzzz' chats.json tiene ⟦abismo:: True memoria recordado tiene ⟦abismo:: True
```

### [M5] Minor -- `ABISMO_BLOQUE_MAX` por env sin validacion: `0` da bloque vacio con `pescado`, negativo recorta la cola, sin tope superior (S8)

`calipso/abismo/consulta.py:23` (`_entero_env`) acepta cualquier entero; `:36` hace `[:ABISMO_BLOQUE_MAX]`. Con `0`,
`etiquetar` devuelve `''`, `resolver` sigue en `pescado`, `estado.bloques.append('')` y la senal dice `pescado` con
tamano 0 (la reentrada va sin bloque). Con `-5` se pierde la cola del bloque. `abc` y vacio caen bien a 2000.

```
S8 ABISMO_BLOQUE_MAX='999999': stdout="999999\n'=== Lo que subio del abismo (fuente: chats) ===\\n[anillo 2]\\nxxxxx...'"
S8 ABISMO_BLOQUE_MAX='abc': stdout="2000\n..."
S8 ABISMO_BLOQUE_MAX='0': stdout="0\n''"
S8 ABISMO_BLOQUE_MAX='-5': stdout="-5\n'=== Lo que subio del abismo (fuente: chats) ===\\n[anillo 2]\\nxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'"   (45 x en vez de 50)
S8 ABISMO_BLOQUE_MAX='': stdout="2000\n..."
```

### [M6] Minor -- los fallbacks a mitad de reentrada ignoran el estado del turno: el local reempieza desde cero pegado al tramo; el de suscripcion PISA `full` y persiste solo lo nuevo (S16b, T2)

- `calipso/server.py:3888-3910` (fallback local): `_chunks_for("local", system, chat_msg, ...)` con el mensaje
  ORIGINAL (sin bloques ni "venias diciendo") y `full +=`: Pedro lee el tramo, un pedazo de reentrada y despues una
  respuesta entera desde cero, en la misma burbuja.
- `calipso/server.py:3846` (fallback entre suscripciones): `full = await emisor.chunk(full)` reemplaza el tramo ya
  emitido; `chats.json` y la memoria guardan solo lo del alterno ("desde cero"), Pedro vio "Dejame ver desde cero".
  Un solo par user/assistant, pero no es lo que se leyo.

```
S16b tipos: [..., 'abismo', 'abismo', 'chunk', 'meta', 'chunk', 'cost', 'chat', 'done'] visible: 'a sigo respuesta local desde cero  fin' user del fallback: 'libro' persistido: 'a sigo respuesta local desde cero  fin'
T2 visible: 'Dejame ver desde cero' fases: [('pondering', None), ('pescado', None)] cli llamadas: 3 persistido: 'desde cero' recordado: '...Calipso respondio: desde cero'
```

### [M7] Minor -- dos consultas iguales duplican el bloque en el system (S14)

`estado.bloques.append(v["texto"])` sin dedup (`_pescar_abismo`); `prompt_reentrada` los concatena. Con tres consultas
identicas (el propio `test_el_tope_de_tres_consultas_por_turno` lo hace) van 3 x hasta 2000 chars del mismo texto al
`num_ctx` de 8192.

```
S14 bloques en el system de la 3a pasada: 2 len system: 268
```

### [M8] Minor -- respuesta que es SOLO la marca: "Venias diciendo: " vacio + "Segui exactamente desde ahi" (S13)

`prompt_reentrada` no distingue tramo vacio; la instruccion le pide al modelo seguir desde la nada. Funciona (S13
visible `'respuesta'`, un `done`), pero el prompt es contradictorio para el 7b.

```
S13 cola del usuario2: 'libro\n\nVenias diciendo: \nSegui exactamente desde ahi, sin repetir.'
```

## Observaciones sin severidad (registradas, no son hallazgos)

- **S9 / `posterior`**: `_retirar_con_aviso(texto[len(tramo_crudo):], "posterior")` (`:3686`) cuenta tambien la marca
  que corto (con cuatro marcas y pesca vacia, `cantidad: 4`), que ya se conto como `consulta`. Doble conteo trivial.
- **S12**: marca dentro de backticks o de un fence: visible `'mira `sigo'` y `'```\nsigo'` -- queda el fence abierto
  al frente de la continuacion. Cosmetico; el contrato pide la marca "a mitad de frase".
- **S18**: `tramos_crudos` en one-shot retira las marcas del abismo (la ilegible `memorai` no vuelve a la nube) pero
  deja `⟦foco:atlas⟧` en el "venias diciendo" (en streaming los tramos ya salieron filtrados de foco). Asimetria
  inocua: es texto que la nube escribio.
- **S7**: una marca vieja dentro de `chats.json` (sembrada a mano) viaja adentro del bloque al system local, a
  `texto_tapado` y a la nube en /nube. No actua (nada interpreta marcas fuera del filtro); el modelo de nube ve un
  ejemplo de marca, que a lo sumo dispararia una consulta.
- **T3**: en streaming la marca con foco anidado ACTUA (`pescado`, resto `libro  x`) aunque `marca.encontrar` (banco,
  detector one-shot) diga que ahi no hay marca: divergencia entre la tuberia viva y PATRON, raiz de [I1].
- **`estado.consultas += 1`** antes del chequeo de steer en `_pescar_abismo`: una consulta abortada cuenta contra el tope
  hasta el proximo mensaje (que resetea). Sin efecto practico.

## Lo que AGUANTO (sondas corridas, invariante por invariante)

| Sonda | Ataque | Salida | Invariante |
|---|---|---|---|
| S1 / S1b | dos marcas validas en un chunk (streaming y one-shot) | `fases [pondering, pescado]`, visible `'a z'`, 2 llamadas / 2 CLI | 4, 7 |
| S3 | `⟦` retenido por foco + `abi` + `smo:chats libro⟧ fin` en tres trozos | `[pondering, pescado]`, visible `'hola z'` | 3, 4 |
| S4 (400) | marca de 400 chars partida por el stream | `'a  b'`, aviso `ilegible` | 3 |
| S5 | steer mientras corre el JUEZ del viaje en `/nube /api` | `[pondering, fallo error]`, `steered`, 2 dones, ultimo user `'otra cosa'`, telemetry `consulta/abortada_por_steer` + `abortada_por_steer/pesca`; el bloque no llego a la nube (mi asercion fallo por la frase de `_NUBE_ABISMO_MARCADORES`, no por conducta) | 8, 2 |
| S6 | `/nube /api` con `ghp_` en el mensaje Y en el bloque | `privacidad local/credencial`, `meta.used local`, viaje `{destino: local}`, las dos llamadas con forma local (`options.num_ctx`), ninguna api | 1, 2, 6 |
| S9 | cuatro marcas en una respuesta (streaming y one-shot) | 1 consulta, `'a z'`, `abismo_consultas 1`; con pesca vacia el posterior vale `'a  b  c  d  e'` con `retirada posterior` | 4, 7 |
| S10a | orquestador (`apagada`) con marca valida en la sintesis | `'sintesis  entera'`, `sin_corte`, 0 llamadas al modelo, sin senal | 7 |
| S10b | fallback local (`apagada`) con marca valida | `'fallback  entero'`, `sin_corte`, `meta.note 'fallback a local'` | 7 |
| S10c | fallback entre suscripciones (`apagada`) con marca valida | `'hola  entero'`, `sin_corte`, 2 CLI, `'fallback entre suscripciones'` | 7 |
| S16a | el modelo local se cae a mitad de la reentrada | `error 'ollama se cayo'`, UN `done`, visible `'a sigo '`, persistido `'a sigo'` | 4 |
| T4 | `/stop` durante la reinvocacion | `'Dejame ver sigo\n\n...(proceso interrumpido)'`, 1 done, 2 CLI | 8 |
| U3 | barrido de disco tras una consulta por suscripcion (home de la sonda, tmp del fixture, `tmp*.md` del sistema, `*.prompt.md` en ROOT) | ningun archivo con el bloque ni la marca; 0 `.md` nuevos; 0 `.prompt.md` | 2 |
| S15 | tres bloques llenos (1722/1919/1919) y `num_ctx` | system de la 4a pasada 5578 chars sobre base mock de 12; usuario 72; `num_ctx 8192` | -- |

Los `estado_abismo.apagada = True` que quedan en la rama son TRES (orquestador `:3618`, fallback suscripcion `:3836`,
fallback local `:3888`); el de suscripcion "hasta T7" ya no existe: la rama one-shot no lo pone y no lo necesita
mientras el filtro no corte por su cuenta (que es justamente [I1]). Los tres sacan el texto ENTERO.

## No reproducido (dicho como tal)

- (15) Overflow de `num_ctx` 8192 con bloques de 2000+: con el modelo falso solo hay numeros de chars (5578 de system
  con base mock); con el `_build_context` real (core 3000 + eco 2000 + proyectos 1200 + contrato 600 + recall) y
  un historial de 12 mensajes SIN techo por mensaje el total puede pasar los ~28k chars; no se midio con tokenizador.
- (17) Que el CLI real (`claude`) vuelque el system o el bloque a stderr en algun error: solo se reprodujo el
  mecanismo con el CLI falso ([M2]).
- (11) Un filtro cortado colgado en la ruta one-shot por el camino "normal" (marca valida segun PATRON): no se da,
  porque `cortar_en_marca` deja fuera de `visible` justamente la marca que cortaria; los tres caminos que SI lo
  provocan estan en [I1].

## Sondas (archivos, borrados al terminar)

- `scratchpad/sonda_eficacia.py`: S1-S18 (25 tests; 24 pasan, 1 falla de asercion propia en S5).
- `scratchpad/sonda_eficacia2.py`: T1-T5 (T2b y T5 fallan por la propia sonda: T2b indexaba llamadas que NO
  existieron -- eso es [I2]; T5 barria el tmp del fixture y no el home de la sonda -- rehecho en U3).
- `scratchpad/sonda_eficacia3.py`: U1-U3.
- `scratchpad/sonda_eficacia4.py`: V1.

Comando: `cd /var/home/pedro/calipso && .venv/bin/python -m pytest -q -p no:cacheprovider -s -v <ruta>`; cada
archivo exporta `CALIPSO_HOME` a un `mkdtemp` antes de importar calipso y mete la raiz del repo en `sys.path` para
reusar `chat`, `cli_falso`, `_sembrar_chat_viejo`, `_turno_con_un_solo_done` y `_juez_que_tapa_nombres`.
