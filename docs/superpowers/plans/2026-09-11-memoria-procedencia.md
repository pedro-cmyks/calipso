# La memoria con procedencia -- lo que dijo Calipso es contexto, no evidencia: plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que ningun lector de la memoria episodica le muestre al modelo un par `Pedro pregunto: ... / Calipso respondio: ...` crudo: cada episodio se presenta con procedencia (quien dijo que, cuando, por que ruta), un no-saber de Calipso se reemplaza al leer por la frase fija "Calipso no tenia el dato entonces", el gesto sin texto se salta ANTES del corte, y lo que no es un par lleva `Registro (<kind>, <fecha>)`; que el `remember` del chat guarde la pregunta LIMPIA y los metadatos de quien contesto de verdad (`ruta` usada, `modelo`, `chat`, `procedencia=1`); que lo viejo se pueda reindexar con un script de un solo tiro (metadatos por merge, id/documento/embedding/cantidad intactos, idempotente, con el server apagado); y que el porton en vivo (antes / A / B sobre el fixture restaurado) diga si el 7b deja de repetir sus propios no-saber y cual variante se aterriza.

**Architecture:** Un modulo puro, `calipso/memoria_procedencia.py`, sin modelo ni disco ni red y sin importar `server`: `PATRONES_FUERTES` / `PATRONES_DEBILES` (la lista vive SOLO ahi), `quitar_acentos`, `clasificar(respuesta) -> "dato" | "sin_dato"` (regla de posicion a 250 chars, regla de los debiles, respuesta que es solo una pregunta), `partir(texto)` (el regex tolerante que comparten los lectores y el reindex), `limpiar_gestos(pregunta)`, `presentar(texto, meta, *, tope_pregunta=200, tope_respuesta=400, score=None, variante=None)` (las tres formas y `""` para la basura) y `presentar_recuerdos(hits, tope, *, variante=None, con_score=True)` (presentar, saltar vacios, recien ahi cortar: el UNICO camino de los dos lectores; `con_score=False` en el abismo, cuyo `off` es `- texto` sin score). El escritor del chat (`server.py`, el `remember` del final de `ws_chat`) cambia el texto a `chat_msg` y suma cuatro kwargs. Los dos lectores (`server._build_context` -> `prompt_compiler.context_sections`, y `abismo/fuentes.memoria`) llaman a `presentar_recuerdos` antes de `RECALL_MAX` / `RECALL_TOP`; `context_sections` pega el `text` ya presentado, sin score. `calipso/memoria_reindex.py` abre cada ambito POR DIRECTORIO (`PersistentClient` + `get_collection("episodic", embedding_function=None)`, no via `Scope`), lee con `get(include=[...])`, arma `{**meta, procedencia: 1, ruta: route}` sin None y escribe con `update(ids, metadatas)` sin `documents`; `--vista` no escribe; se niega con el puerto del server ocupado salvo `--forzar`. El porton (`experimentos/porton_memoria.py`) corre sobre ESTA rama con la variable `MEMORIA_PRESENTAR=off|A|B` (decision 8), server desechable en 8776 y el fixture restaurado por condicion y por pasada. El banco (`experimentos/no_saber_banco.py`) son 51 respuestas reales etiquetadas a mano; el test fija el piso.

**Tech Stack:** Python 3.14 + FastAPI + pytest en la raiz del repo (el harness `chat` de `test_abismo_chat.py` para `ws_chat`; `chromadb` 1.5.9 con colecciones SIN modelo -embeddings explicitos- para los tests del reindex; `websockets` 16.0 del .venv para el porton, como `test_chat_live.py`). Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-11-memoria-con-procedencia-design.md` (autoridad: las tres decisiones de Pedro de la seccion 1, los rulings marcados en la 2 y la 3, las invariantes de la 4, el porton y la verificacion de la 5, lo que NO hace de la 6, el corte en 5 tasks de la 7). Todo `archivo:linea` de este plan es de main `8fff6c1` (el spec y el fixture ya estan commiteados), verificado leyendo el disco el 2026-09-11.

## Global Constraints

Invariantes del spec (seccion 4), textuales:

1. **Nada se borra ni se reescribe en disco al leer.** La degradacion y el salto viven en `presentar`.
2. **Todo lo que el modelo ve de un episodio lleva procedencia:** quien lo dijo, cuando, y por que ruta si fue Calipso; lo que no es un par de chat lleva `Registro (<kind>, <fecha>)`. No existe mas el par crudo en ningun prompt.
3. **Un no-saber jamas se presenta como dato.** Se reemplaza por la frase fija; la respuesta cruda sigue en disco.
4. **La clasificacion es pura y determinista,** sin modelo, medida contra el banco; los patrones estan en un solo lugar.
5. **El reindexado conserva id, documento y cantidad;** solo agrega metadatos por merge; es idempotente y se niega con el server prendido (salvo `--forzar`).
6. **Lo viejo y lo nuevo se leen con la misma funcion** (`partir` + `presentar`).
7. **`Memory.recall`, `recent` y `reflect` no cambian de contrato.**

Reglas del repo:

- SIN EMOJIS en codigo, tests, docs, commits y salidas. Comentarios, docstrings y docs en espanol SIN acentos (los TEXTOS del banco y de los tests son respuestas reales del 7b y llevan los acentos que traen: son datos, no prosa nuestra).
- `CALIPSO_HOME` a un temporal en TODO test: `conftest.py:46-47` lo fija ANTES de importar `calipso`. NUNCA importar `calipso` fuera de pytest sin `export CALIPSO_HOME=<temporal>` antes del import (`memory.py:41-42` y `chronology` congelan la constante al importar). `memoria_procedencia` no toca el home (puro) y `memoria_reindex` lo resuelve POR LLAMADA (`home()`), nunca en una constante de modulo: `test_aislacion_home.py:35-47` recorre los modulos `calipso.*` con un atributo `CALIPSO_HOME` y ninguno de los dos debe tenerlo.
- **El server REAL (puerto 8000, `~/.calipso`) NO se toca.** El porton corre con un server desechable en el puerto 8776 y un `CALIPSO_HOME` temporal restaurado desde el fixture. **El reindex sobre el home real es acto de Pedro** (decision 3 del spec): el plan deja los comandos en el cierre y NADIE los corre por el.
- El fixture `experimentos/fixtures/memoria_smoke_home/` NO se abre en sitio con `PersistentClient` (chroma escribe sqlite/WAL al abrir): siempre `shutil.copytree` a `tmp_path` primero. No se edita a mano (README del fixture).
- No se llama a Ollama ni a huggingface.co desde los tests: los chromas de prueba se arman con embeddings explicitos (sin funcion de embeddings); el unico test que abre el fixture real carga el SentenceTransformer del cache local. El `setdefault` de `HF_HUB_OFFLINE` / `TRANSFORMERS_OFFLINE` de `memoria_reindex` protege la corrida por CLI (el acto de Pedro: proceso limpio, 0 conexiones fuera de loopback) y el archivo `test_memoria_reindex.py` corrido en aislado (~5 s la primera vez en el proceso). En la SUITE llega tarde: `calipso.server` (importado antes, por orden alfabetico) construye `Memory()` -> `SentenceTransformerEmbeddingFunction` con el hub online (una conexion a huggingface.co:443 al importar, conducta de main, no de este plan) y `huggingface_hub.constants` queda congelado; ahi el test del fixture real igual no sale a la red, pero porque la funcion de embeddings reutiliza el modelo ya cargado en el proceso, no por el `setdefault`. Medido con un espia de `socket.connect`: los dos archivos juntos -> una sola conexion en fase import, ninguna durante los tests.
- **Excepciones declaradas a las invariantes 2 y 3:** (a) la variante `MEMORIA_PRESENTAR=off` vuelve a pegar el par crudo y el no-saber tal cual; existe SOLO para medir la condicion `antes` del porton y para re-medir; en produccion la variable no se pone (decision 8); (b) `reflect` (`memory.py:238-245`, lee `source.recent(limit)` y manda los episodios crudos a `claude -p`), `recent` y el jefe (`plantel/jefe.py:359`, `ctx.memoria.recent(limit=5)`) siguen leyendo el documento crudo: fuera del alcance por la seccion 6 del spec y la invariante 7.
- Los tests nuevos son pytest de verdad (`def test_...` con fixtures). `test_prompt_compiler.py` es un script con `main()` que se corre a mano (`.venv/bin/python test_prompt_compiler.py`) y NO se toca: sigue pasando porque `context_sections` sigue pegando `item["text"]`.
- `test_memoria_ambito.py:82-121` lee del FUENTE el bloque de `server.py` entre el comentario `recordar el intercambio` y `chats.append(chat_id, "assistant"` y exige: `scope="global"` literal, `asyncio.to_thread`, `except Exception`, las palabras `pregunto` y `respondio`, y NINGUNA `Ã` (mojibake) en ese tramo. El comentario nuevo del bloque (Task 2) respeta las cinco cosas; las variantes rotas (`preguntÃ³`) se citan SOLO en `memoria_procedencia.py` y en `test_memoria_procedencia.py`.
- Suite completa antes de CADA commit verificando el EXIT CODE: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?` (tarda ~100 s). Anotar la linea base en main al arrancar (Task 1, Step 1) y exigir `0 failed`, `EXIT=0` en cada task; el numero esperado es "base + los nuevos" (tabla del Self-review). No se toca `calipso/web/`: los tests de node no cambian (428).
- `git add` con rutas explicitas (dos agentes en paralelo comparten el indice). Anclas por SIMBOLO en `server.py` (`grep -n '^def <nombre>'`), las lineas de este plan son de hoy.
- Ritual de cierre de rama: el porton en vivo + el smoke con server desechable antes del merge; merge `--no-ff`.

## Decisiones tomadas por este plan (visibles; el spec las dejaba al plan)

1. **Un solo camino para los dos lectores: `memoria_procedencia.presentar_recuerdos(hits, tope, *, variante=None, con_score=True)`.** Presenta cada hit, salta los `""` y recien ahi corta a `tope`; devuelve los hits con `text` ya presentado (score, meta y scope viajan intactos). `_build_context` lo llama con `RECALL_MAX` tras el filtro por `RECALL_MIN_SCORE` (n=8 como hoy) y `fuentes.memoria` con `RECALL_TOP, con_score=False` tras `RECALL_UMBRAL` (n=12 como hoy; `con_score` solo importa en la variante `off`, donde el abismo de main pega `- texto` sin score). **`context_sections` NO llama a `presentar`**: pega `item["text"]` tal cual, sin `(score)`. Presentar en el compilador obligaria a presentar dos veces (una para saltar antes del corte en `_build_context`, otra al pegar) o a mover el corte del server al compilador; `context_sections` es un renderer y su unico llamador de produccion es `_build_context`. `test_prompt_compiler.py:22` sigue pasando un hit crudo y sigue pasando.
2. **Los dos parciales del orquestador del fixture (`[4]`, `[12]`, 5000+ chars, "No pude completar la sintesis automatica. Resultado parcial del equipo: ...") son `dato`** en el banco: informan rama y commits reales. El spec (seccion 5) dice "7 no-saber, 4 confabulaciones" sobre los 16; medido hoy con sus propios patrones da **5 no-saber** (`[0] [1] [2] [9] [10]`), **5 confabulaciones** (`[5] [6] [8] [13] [14]`, todas `dato` por el ruling del spec), 4 datos genuinos y los 2 parciales. El `--vista` sobre el fixture reporta `5 sin_dato`; los tests lo fijan. Contarlos como no-saber sin un patron que los atrape rompia el piso del 90% (5/7).
3. **Patrones que el banco sumo a la lista del spec** (el spec lo permite: "se mide contra el banco; afinarla no toca el disco"): un fuerte, `no hay informacion disponible` (atrapa "No hay informacion disponible sobre su estado" y NO atrapa "No hay informacion adicional disponible sobre este commit", que viene despues de un dato); y en los debiles `recordar` sin `-me` (cubre las dos formas), `contarme`, `compartir` y `cuentame (un poco )?mas`. Ningun otro. `no tenemos (un )?registro` NO entra a proposito: degradaria la confabulacion "La ultima discusion sobre el presupuesto se centro en ... Sin embargo, no tenemos un registro detallado" que el spec manda etiquetar `dato`.
4. **"Oracion afirmativa con contenido"** (la regla de los debiles y la de "solo una pregunta"): una oracion COMPLETA (cerrada por `.`, `!`, `?` o salto de linea; el fragmento final sin cierre no cuenta) que no termina en `?` ni empieza con `¿`, y que despues de pelar los abridores de relleno (`claro`, `por supuesto`, `entendido`, `entiendo`, `de acuerdo`, `perfecto`, `vale`, `ok`, `si`, `hola`, `buen dia`, `buenas`, `gracias`, `pedro`) conserva 3+ palabras. Con 4 palabras "Estoy bien, gracias" (un saludo) caia en `sin_dato`; con 3 no. Para el debil cuentan solo las oraciones completas ANTES del patron. **La segunda clausula de los debiles del spec ("o si van con un fuerte") queda subsumida por la regla de posicion y NO se implementa aparte:** un fuerte que arranca antes de `POSICION_MAX` ya degrada solo (el debil no agrega nada); un fuerte que arranca despues de 250 es, por el ruling de la posicion, una respuesta que ya tiene contenido, y un debil al lado no la vuelve no-saber (el banco lo mide: 0 falsos, 26/27 atrapados).
5. **La vineta colapsa el espacio de cada tramo** (`" ".join(texto.split())`): dos lineas exactas por par, los topes se miden sobre el texto colapsado y el recorte agrega `...`. Sin esto una respuesta con lista markdown rompe la sangria de la segunda linea y el tope no acota nada.
6. **La frase fija lleva ruta y fecha:** `  Calipso no tenia el dato entonces (local, 2026-09-10).` La invariante 2 pide "por que ruta si fue Calipso" tambien para el no-saber; el flag `eco` del porton busca `no tenia el dato`, que es el prefijo intacto.
7. **Lo que no parsea:** `- Registro (<kind o episodio>, <ts[:10] o ?>): <texto colapsado, tope 400>`. Con `meta=None` o sin `ts`: `?`. Los dobles de los tests pasan hits sin `meta` (`test_abismo_fuentes.py:139`, `test_prompt_compiler.py:22`): `presentar` tolera `meta` ausente o `None`.
8. **La variable del porton: `MEMORIA_PRESENTAR=off|A|B`**, leida POR LLAMADA por `memoria_procedencia.variante_activa()` (nunca congelada), con `VARIANTE_DEFAULT = "A"` cuando no esta o vale otra cosa. `off` reproduce los dos LECTORES de main byte a byte: `- (score) texto` en el system (`prompt_compiler.py:224`) y `- texto` SIN score en el abismo (`fuentes.py:118`); por eso `presentar` recibe `score` y `presentar_recuerdos` recibe `con_score` (`True` en `_build_context`, `False` en `fuentes.memoria`: la fuente del abismo nunca pasa el score). Asi las tres condiciones corren sobre ESTA rama con el mismo server, sin worktree ni stash. **Desviacion declarada respecto de "`antes` (main)" del spec:** el ESCRITOR de la condicion `antes` es el de la Task 2 (pregunta limpia, metadatos nuevos), no el de main; el efecto queda acotado a los turnos 2-4 de una misma pasada (chat nuevo por turno; el home se restaura por pasada), que pueden recuperar el episodio del turno 1 con un embedding distinto del que main habria guardado (`Pedro pregunto: /local ...`). Se acepta; si Pedro quiere el baseline exacto, `antes` se mide con el server desde main en un worktree (ruling 11). En produccion la variable no esta puesta. Tras el porton (Task 5) la constante aterriza en `A` o `B` segun la regla del spec, y el interruptor QUEDA (documentado en el modulo) para re-medir.
9. **El reindex abre por directorio y va offline por construccion.** `chromadb.PersistentClient(path)` + `get_collection("episodic", embedding_function=None)` (no `get_or_create`: no crea colecciones vacias; solo directorios que YA tienen `chroma.sqlite3`: un `PersistentClient` sobre un directorio vacio lo crea). Verificado en 1.5.9: `update(ids, metadatas)` sin `documents` reconstruye la funcion de embeddings persistida en el schema (SentenceTransformer) aunque no embeba nada, y eso sale a huggingface.co salvo `HF_HUB_OFFLINE=1`; el modulo fija `HF_HUB_OFFLINE` y `TRANSFORMERS_OFFLINE` con `setdefault` ANTES de `import chromadb` (un `HF_HUB_OFFLINE=0` explicito de Pedro manda). Sin red no hay nada que declarar en la aduana, y el reindex no es el proceso del server. `--vista` solo hace `get`/`count` y no carga nada.
10. **El chequeo del puerto es solo para `--aplicar` (PROPUESTA del plan, pendiente del ruling 7).** `--vista` es de solo lectura y sirve justamente para mirar con el server prendido; el spec (seccion 3 e invariante 5) dice "se niega si responde, salvo `--forzar`" sin distinguir modos, asi que la letra del spec es que la vista TAMBIEN se niega. Se le pregunta a Pedro ANTES de arrancar la Task 4 (ruling 7); hasta entonces el test `test_se_niega_con_el_puerto_ocupado_y_sigue_con_forzar` NO fija la conducta de `--vista` con el puerto ocupado (solo `--aplicar` y `--forzar`). El mensaje del rechazo dice que es por completitud del recorrido, no por integridad (ruling del spec). `CALIPSO_PORT` con default 8000, como `launch_calipso.py:29`. La llamada `socket.create_connection` de `_server_prendido` entra a `EXCEPCIONES` del canario de la aduana con motivo `loopback` (Task 4), como `launch_calipso.py:_port_open`.
11. **Conteos del reindex:** sin `kind` y con forma de par = chat (se reindexa); sin `kind` y sin forma = "no chat"; `kind="chat"` sin forma = "kind=chat que NO parsean" (se cuenta, no se toca); la basura (`/algo` solo) TAMBIEN recibe `procedencia` (el reindex marca, el lector salta); `raros` = meta que no es dict o documento que no es str (se saltan y se cuentan); `ruta` solo si `route` existe (jamas un None en el merge); un episodio que ya tiene `procedencia=1` no se toca (idempotencia). Lotes de 100.
12. **El porton:** `experimentos/porton_memoria.py`, sin importar `calipso` salvo `memoria_procedencia.clasificar` (puro); server desechable `uvicorn calipso.server:app` en 127.0.0.1:8776 con `CALIPSO_HOME` temporal, `CALIPSO_TOKEN` aleatorio, `CALIPSO_NO_TOTP=1` y `MEMORIA_PRESENTAR` por condicion; el home se restaura por condicion Y por pasada (`copytree` del fixture + un `catastro.json` minimo `{"raices": [], "proyectos": []}` para que el server no escanee el disco de la maquina en el primer turno; el fixture no trae catastro); chat nuevo por turno (`POST /api/chats` + `activate`, ws con `chat_id`); N=2; texto COMPLETO en el JSONL (el cliente del smoke lo cortaba a 400 y eso rompia la clasificacion). Verdades: `libro` -> "nombre de la rosa"; `libro_rosa` -> "mariana quintero"; `presupuesto` -> "120" o "octubre"; `mariana` -> "mariana" y "libro". Regla de aterrizaje = la del spec (B solo si A muestra eco y B no); cualquier otro resultado aterriza A y lo dice.
13. **`MemoriaFalsa` del harness suma `guardados: list[(text, scope, meta)]`** y conserva `recordado: list[str]` intacto (`test_abismo_chat.py:254` y `:323` lo asertan como lista de str).
14. **`_build_context` no cambia de firma** (`user_msg` sigue siendo el nombre del parametro aunque llegue `chat_msg`) ni de umbral ni de n: solo el orden presentar -> saltar -> cortar.

## Mapa de archivos

**Se crean:**

| Archivo | Que es | Task |
|---|---|---|
| `calipso/memoria_procedencia.py` | el modulo puro: patrones, `quitar_acentos`, `clasificar`, `partir`, `limpiar_gestos`, `presentar`, `presentar_recuerdos`, `variante_activa`, `VARIANTE_DEFAULT`, `TOPE_PREGUNTA`, `TOPE_RESPUESTA`, `SIN_DATO` | 1 |
| `experimentos/no_saber_banco.py` | el banco: 51 respuestas reales etiquetadas (27 `sin_dato`, 24 `dato`) y `medir(clasificar)`; corre solo con `python -m experimentos.no_saber_banco` | 1 |
| `test_memoria_procedencia.py` | 24 unitarios: banco, posicion, acentos, debiles, solo-pregunta, `partir` (nuevo, dos variantes rotas, saltos), `limpiar_gestos`, `presentar` (A, B, off, ruta, meta None, viejo, basura, Registro, topes, colapso), `presentar_recuerdos` | 1 |
| `test_memoria_lectores.py` | 9 tests: `context_sections`, `_build_context` (presenta, salta, corta despues; umbral; variante), `fuentes.memoria` (presenta y corta a `RECALL_TOP`; bajo el techo de `etiquetar`; hits sin meta; `off` es el bloque crudo de main sin score) | 3 |
| `calipso/memoria_reindex.py` | el script: `home()`, `puerto()`, `ambitos()`, `_server_prendido()`, `abrir()`, `revisar()`, `aplicar()`, `main()` con `--vista` / `--aplicar` / `--forzar` | 4 |
| `test_memoria_reindex.py` | 8 tests sobre homes temporales sin modelo + uno sobre la copia del fixture real (9) | 4 |
| `experimentos/porton_memoria.py` | el porton en vivo: restaura el fixture, levanta el desechable, manda las 4 preguntas con chat nuevo por turno, clasifica, escribe el JSONL y el informe | 5 |
| `experimentos/porton_memoria_resultados.md` + `.jsonl` | lo que dio el porton (los textos completos en el JSONL) | 5 |
| `docs/superpowers/2026-09-11-cierre-memoria-procedencia.md` | el informe del cierre: porton, aterrizaje, smoke, lo que queda para Pedro (el reindex del home real) | 5 |

**Se modifican (lineas de main `8fff6c1`):**

| Archivo | Donde | Que | Task |
|---|---|---|---|
| `test_abismo_chat.py` | `:28-43` (`MemoriaFalsa`), al final (tras `:685`) | `guardados` en el doble; 3 tests: turno plano, fallback api->local, orquestador | 2 |
| `calipso/server.py` | `:4234-4243` (el `remember` del chat, dentro de `ws_chat` `:3407`; ancla: el comentario `# 3. Corria sobre el event loop`) | `chat_msg` en el texto; `ruta=used_route, modelo=model, chat=chat_id, procedencia=1`; comentario de la procedencia (sin `Ã`) | 2 |
| `calipso/server.py` | `:101` (import, debajo de `from calipso import aduana`), `:2955-2957` (`_build_context` `:2941`, el recall) | import de `memoria_procedencia`; `presentar_recuerdos(..., RECALL_MAX)` | 3 |
| `calipso/prompt_compiler.py` | `:222-228` (`context_sections` `:198`) | pega `item["text"]` sin `(score)` | 3 |
| `calipso/abismo/fuentes.py` | `:13` (import), `:114-119` (`memoria` `:109`) | `presentar_recuerdos(..., RECALL_TOP)` | 3 |
| `test_aduana_canario.py` | `:53` (tras `launch_calipso.py:main`) | la excepcion `calipso/memoria_reindex.py:_server_prendido` con motivo loopback | 4 |
| `calipso/memoria_procedencia.py` | `VARIANTE_DEFAULT` | `"A"` o `"B"` segun el porton (y la linea del test que lo fija) | 5 |
| `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md` | adenda (seccion 9, `:229-257`) | el estado: memoria con procedencia en main; el reindex del home real pendiente de Pedro | 5 |

**Lo que NO se toca (spec seccion 6):** `memory.py` (`Scope.remember :92-118` ya descarta los kwargs `None` y ya hashea texto+meta+ts; `recall :120-130`, `recent :132-136`, `reflect :238-283` intactos), `chats.json`, el bibliotecario, el core, la cronologia, el escritor de metas (`server.py:3509-3515`, `kind="goal"`, ambito de proyecto por `scope="auto"`), `consulta.etiquetar` y `ABISMO_BLOQUE_MAX` (`consulta.py:23-36`), `capabilities.parse_directives` (`:199-256`; `:255` cae al crudo si el mensaje era solo gestos: por eso la basura se detecta en `presentar`).

## Orden de tasks

El corte de la seccion 7 del spec, con un solo desvio: el fixture durable ya esta en main (`8fff6c1`), asi que la Task 1 no lo copia. Cada task termina en un commit con la suite verde; la Task 5 aterriza la variante, corre el smoke y mergea con `--no-ff`.

Rama de trabajo: `feat/memoria-procedencia` desde main, en la raiz del repo.

---

### Task 1: `calipso/memoria_procedencia.py` (patrones, `clasificar`, `partir`, `limpiar_gestos`, `presentar`, `presentar_recuerdos`) + el banco + los unitarios

**Files:**
- Create: `calipso/memoria_procedencia.py`
- Create: `experimentos/no_saber_banco.py`
- Create: `test_memoria_procedencia.py`
- Test: `test_memoria_procedencia.py`

**Interfaces:**
- Consumes: nada del paquete (modulo puro: `os`, `re`, `unicodedata`). Los datos del banco salen del fixture (`experimentos/fixtures/memoria_smoke_home/global/chroma`, 16 episodios; volcados tal cual, con strip) y de `experimentos/consulta_abismo_*.jsonl` (campo `salida`, solo las de menos de 400 chars -las que no tocan el corte de `consulta_abismo_system.py:196` / `consulta_abismo_posicion.py:97`- y sin marca `⟦`; el campo `item` es la pregunta del experimento).
- Produces: `PATRONES_FUERTES`, `PATRONES_DEBILES`, `POSICION_MAX = 250`, `quitar_acentos(texto) -> str`, `clasificar(respuesta) -> "dato" | "sin_dato"`, `partir(texto) -> (pregunta, respuesta) | None`, `limpiar_gestos(pregunta) -> str`, `TOPE_PREGUNTA = 200`, `TOPE_RESPUESTA = 400`, `SIN_DATO = "Calipso no tenia el dato entonces"`, `VARIANTE_DEFAULT = "A"`, `VARIANTES = ("A", "B", "off")`, `variante_activa() -> str`, `presentar(texto, meta=None, *, tope_pregunta=200, tope_respuesta=400, score=None, variante=None) -> str`, `presentar_recuerdos(hits, tope, *, variante=None, con_score=True) -> list[dict]`. En el banco: `BANCO: list[tuple[etiqueta, respuesta, nota]]`, `SIN_DATO`, `DATO`, `medir(clasificar) -> {no_saber, atrapados, datos, falsos, fallas, recall}`.

- [ ] **Step 1: Crear la rama, commitear el plan y anotar la linea base**

```bash
cd /var/home/pedro/calipso && git checkout main
# sin `git pull`: main esta 34 commits por delante de origin/main (`git status -sb` -> `[ahead 34]`) y la red
# no es condicion de nada; un pull que falla no puede dejar los commits de abajo sobre main
git checkout -b feat/memoria-procedencia
test "$(git branch --show-current)" = "feat/memoria-procedencia" || { echo "NO estoy en la rama"; false; }
# el plan mismo se commitea ANTES de ejecutarlo (convencion del repo: 4aff94f plan(aduana), c645ccd plan(abismo))
git add docs/superpowers/plans/2026-09-11-memoria-procedencia.md
git commit -m "plan(memoria): la memoria con procedencia -- 5 tasks (modulo puro con patrones fuertes/debiles y regla de posicion + banco de 51 respuestas reales, el remember del chat con la pregunta limpia y la ruta usada, los dos lectores presentan antes del corte, el reindex por directorio y offline, el porton antes/A/B sobre la misma rama con MEMORIA_PRESENTAR), escrito sobre el spec y verificado corriendo sobre copias"
.venv/bin/python -m pytest -q --ignore=test_chat_live.py 2>&1 | tail -1; echo EXIT=$?     # anotar: N passed (linea base; el merge de la aduana dejo 1645)
```

- [ ] **Step 2: Los unitarios (en rojo)**

`test_memoria_procedencia.py`, completo:

```python
"""La memoria con procedencia, en aislado (spec 2026-09-11, seccion 5):
`clasificar` contra el banco, `partir` y `presentar` con lo nuevo, lo viejo
(las dos variantes rotas), meta ausente, basura, sin ruta y topes; y
`presentar_recuerdos`, el corte DESPUES de presentar que usan los dos
lectores."""
from __future__ import annotations

from calipso import memoria_procedencia as mp
from experimentos import no_saber_banco as banco


# --- clasificar -------------------------------------------------------------

def test_el_banco_atrapa_los_no_saber_y_no_degrada_ningun_dato():
    """El piso del spec: 0 falsos `sin_dato` sobre respuestas con dato y
    >= 90% de los no-saber atrapados. Si un patron nuevo rompe esto, el
    rojo lista las filas."""
    r = banco.medir(mp.clasificar)
    assert r["falsos"] == 0, r["fallas"]
    assert r["recall"] >= 0.90, (r["atrapados"], r["no_saber"], r["fallas"])
    assert r["no_saber"] >= 20 and r["datos"] >= 20   # el banco no se vacio


def test_un_fuerte_degrada_solo_si_arranca_antes_de_los_250_chars():
    relleno = "Hay contenido de verdad en esta respuesta. " * 7   # 301 chars
    assert mp.clasificar("No tengo registros de eso.") == "sin_dato"
    assert mp.clasificar(relleno + "No tengo registros de eso.") == "dato"
    assert mp.clasificar("Bueno. " * 10 + "No tengo registros de eso.") == "sin_dato"


def test_los_acentos_y_las_mayusculas_no_esconden_un_patron():
    assert mp.clasificar("NO TENGO INFORMACIÓN sobre eso.") == "sin_dato"
    assert mp.clasificar("No está registrado en mi memoria.") == "sin_dato"
    assert mp.quitar_acentos("información año") == "informacion ano"


def test_un_debil_no_degrada_si_antes_hay_una_afirmativa_con_contenido():
    assert mp.clasificar("Claro, Pedro. ¿Podrías darme más detalles?") == "sin_dato"
    assert mp.clasificar(
        "El commit fue el 2026-09-09 en main. ¿Podrías darme más detalles?") == "dato"


def test_una_respuesta_que_es_solo_una_pregunta_es_sin_dato():
    assert mp.clasificar("¿A cuál idea te refieres?") == "sin_dato"
    assert mp.clasificar("Anoté el 12 de octubre. ¿Algo más?") == "dato"


def test_la_respuesta_vacia_es_sin_dato():
    assert mp.clasificar("") == "sin_dato"
    assert mp.clasificar("   \n") == "sin_dato"


# --- partir y limpiar_gestos ------------------------------------------------

NUEVO = "Pedro pregunto: que libro lei\nCalipso respondio: El nombre de la rosa."
VIEJO_1 = "Pedro preguntÃ³: -q\nCalipso respondiÃ³: Nada. Sigo esperando."
VIEJO_2 = "Pedro preguntÃƒÂ³: hola\nCalipso respondiÃƒÂ³: Hola Pedro."


def test_partir_lo_nuevo_y_las_dos_variantes_rotas():
    assert mp.partir(NUEVO) == ("que libro lei", "El nombre de la rosa.")
    assert mp.partir(VIEJO_1) == ("-q", "Nada. Sigo esperando.")
    assert mp.partir(VIEJO_2) == ("hola", "Hola Pedro.")


def test_partir_tolera_saltos_en_la_pregunta_y_en_la_respuesta():
    texto = "Pedro pregunto: linea 1\nlinea 2\nCalipso respondio: a\n\nb"
    assert mp.partir(texto) == ("linea 1\nlinea 2", "a\n\nb")


def test_partir_devuelve_none_para_lo_que_no_es_un_par():
    assert mp.partir("Pedro definio una meta: X\nCalipso creo Goal Mode: g1") is None
    assert mp.partir("hecho 0") is None
    assert mp.partir("") is None
    assert mp.partir("Calipso respondio: solo\nPedro pregunto: al reves") is None


def test_limpiar_gestos_saca_los_gestos_iniciales_y_solo_esos():
    assert mp.limpiar_gestos("/local hola, que libro?") == "hola, que libro?"
    assert mp.limpiar_gestos("/local /think hola") == "hola"
    assert mp.limpiar_gestos("hola /web algo") == "hola /web algo"
    assert mp.limpiar_gestos("/local") == ""
    assert mp.limpiar_gestos("/nube") == ""
    assert mp.limpiar_gestos("-q") == "-q"
    assert mp.limpiar_gestos("  hola   mundo\n") == "hola mundo"


# --- presentar --------------------------------------------------------------

META = {"ts": "2026-09-10T20:58:05", "route": "local", "kind": "chat"}


def test_presentar_un_par_con_dato_da_la_vineta_de_dos_lineas():
    assert mp.presentar(NUEVO, META, variante="A") == (
        "- Pedro dijo (2026-09-10): que libro lei\n"
        "  Calipso contesto (local, 2026-09-10): El nombre de la rosa.")


def test_presentar_un_no_saber_lo_reemplaza_por_la_frase_fija():
    texto = ("Pedro pregunto: /local quien me presto el libro rosa?\n"
             "Calipso respondio: Entiendo. No tengo registros de quien te presto un libro.")
    assert mp.presentar(texto, META, variante="A") == (
        "- Pedro dijo (2026-09-10): quien me presto el libro rosa?\n"
        "  Calipso no tenia el dato entonces (local, 2026-09-10).")
    assert "No tengo registros" not in mp.presentar(texto, META, variante="A")


def test_la_variante_b_omite_el_renglon_de_calipso_en_el_no_saber():
    texto = ("Pedro pregunto: quien me presto el libro?\n"
             "Calipso respondio: No tengo registros de eso.")
    assert mp.presentar(texto, META, variante="B") == (
        "- Pedro dijo (2026-09-10): quien me presto el libro?")
    # con dato, B es igual a A
    assert mp.presentar(NUEVO, META, variante="B") == mp.presentar(NUEVO, META, variante="A")


def test_la_variante_off_es_el_par_crudo_de_antes():
    assert mp.presentar(NUEVO, META, variante="off") == f"- {NUEVO}"
    assert mp.presentar(NUEVO, META, score=0.91, variante="off") == f"- (0.91) {NUEVO}"
    # por presentar_recuerdos: el system de main pegaba el score, el abismo no
    hit = {"text": NUEVO, "meta": META, "score": 0.91, "scope": "global"}
    assert mp.presentar_recuerdos([hit], 8, variante="off")[0]["text"] == f"- (0.91) {NUEVO}"
    assert mp.presentar_recuerdos([hit], 8, variante="off", con_score=False)[0]["text"] == f"- {NUEVO}"


def test_la_variante_activa_sale_del_entorno_y_sin_variable_es_la_default(monkeypatch):
    monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)
    assert mp.variante_activa() == mp.VARIANTE_DEFAULT == "A"
    monkeypatch.setenv("MEMORIA_PRESENTAR", "B")
    assert mp.variante_activa() == "B"
    monkeypatch.setenv("MEMORIA_PRESENTAR", "cualquiera")
    assert mp.variante_activa() == mp.VARIANTE_DEFAULT


def test_la_ruta_usada_manda_sobre_la_decidida_y_sin_ninguna_es_interrogante():
    meta = {"ts": "2026-09-11T10:00:00", "route": "api", "ruta": "local"}
    assert "Calipso contesto (local, 2026-09-11)" in mp.presentar(NUEVO, meta, variante="A")
    assert "Calipso contesto (api, 2026-09-11)" in mp.presentar(
        NUEVO, {"ts": "2026-09-11T10:00:00", "route": "api"}, variante="A")
    assert "Calipso contesto (?, 2026-09-11)" in mp.presentar(
        NUEVO, {"ts": "2026-09-11T10:00:00"}, variante="A")


def test_meta_ausente_o_none_da_fecha_y_ruta_interrogante():
    assert mp.presentar(NUEVO, None, variante="A") == (
        "- Pedro dijo (?): que libro lei\n"
        "  Calipso contesto (?, ?): El nombre de la rosa.")
    assert mp.presentar(NUEVO, {}, variante="A") == mp.presentar(NUEVO, None, variante="A")


def test_lo_viejo_se_presenta_igual_que_lo_nuevo_y_sin_el_gesto():
    viejo = ("Pedro pregunto: /local hola, que libro te conte que empece?\n"
             "Calipso respondio: Estare encantado. Actualmente no tengo ese dato en mi memoria.")
    assert mp.presentar(viejo, META, variante="A") == (
        "- Pedro dijo (2026-09-10): hola, que libro te conte que empece?\n"
        "  Calipso no tenia el dato entonces (local, 2026-09-10).")
    assert mp.presentar(VIEJO_2, META, variante="A") == (
        "- Pedro dijo (2026-09-10): hola\n"
        "  Calipso contesto (local, 2026-09-10): Hola Pedro.")


def test_el_gesto_sin_texto_es_la_unica_basura_y_da_vacio():
    solo_gesto = "Pedro pregunto: /local\nCalipso respondio: Hola, en que te ayudo?"
    assert mp.presentar(solo_gesto, META, variante="A") == ""
    assert mp.presentar(solo_gesto, META, variante="B") == ""
    # "-q" no es basura: se presenta como lo que es
    assert mp.presentar(VIEJO_1, META, variante="A").startswith("- Pedro dijo (2026-09-10): -q")


def test_lo_que_no_parsea_lleva_registro_con_kind_y_fecha():
    meta = {"ts": "2026-08-14T09:00:00", "route": "goal", "kind": "goal"}
    texto = "Pedro definio una meta: terminar el lector\nCalipso creo Goal Mode: g-1"
    assert mp.presentar(texto, meta, variante="A") == (
        "- Registro (goal, 2026-08-14): Pedro definio una meta: terminar el lector "
        "Calipso creo Goal Mode: g-1")
    assert mp.presentar("hecho 0", None, variante="A") == "- Registro (episodio, ?): hecho 0"
    assert mp.presentar("hecho 0", {"score": 1}, variante="A") == "- Registro (episodio, ?): hecho 0"


def test_los_topes_recortan_cada_tramo_con_puntos_suspensivos():
    pregunta = "p" * 300
    respuesta = "r" * 5000
    texto = f"Pedro pregunto: {pregunta}\nCalipso respondio: {respuesta}"
    salida = mp.presentar(texto, META, variante="A")
    l1, l2 = salida.split("\n")
    assert l1 == "- Pedro dijo (2026-09-10): " + "p" * 200 + "..."
    assert l2 == "  Calipso contesto (local, 2026-09-10): " + "r" * 400 + "..."
    corto = mp.presentar(texto, META, tope_pregunta=10, tope_respuesta=20, variante="A")
    assert "p" * 10 + "..." in corto and "r" * 20 + "..." in corto
    assert mp.presentar("x" * 900, None, variante="A") == "- Registro (episodio, ?): " + "x" * 400 + "..."


def test_los_saltos_de_linea_se_colapsan_para_que_la_vineta_sea_de_dos_lineas():
    texto = ("Pedro pregunto: dame el detalle\nCalipso respondio: Entendido.\n\n"
             "1. **Objetivo:** un mapa.\n2. **Backend:** una API.")
    salida = mp.presentar(texto, META, variante="A")
    assert salida.count("\n") == 1
    assert "Entendido. 1. **Objetivo:** un mapa. 2. **Backend:** una API." in salida


# --- presentar_recuerdos: presentar ANTES del corte --------------------------

def _hit(texto, score, meta=META):
    return {"text": texto, "meta": meta, "score": score, "scope": "global"}


def test_presentar_recuerdos_salta_los_vacios_antes_de_cortar():
    basura = "Pedro pregunto: /local\nCalipso respondio: hola"
    hits = [_hit(basura, 0.9), _hit(basura, 0.8)] + [
        _hit(f"Pedro pregunto: q{i}\nCalipso respondio: r{i}", round(0.7 - i * 0.01, 2))
        for i in range(6)]
    salida = mp.presentar_recuerdos(hits, 4, variante="A")
    assert len(salida) == 4
    assert [h["score"] for h in salida] == [0.7, 0.69, 0.68, 0.67]
    assert all(h["text"].startswith("- Pedro dijo (2026-09-10): q") for h in salida)
    assert salida[0]["scope"] == "global" and salida[0]["meta"] is META


def test_presentar_recuerdos_tolera_hits_sin_meta_y_conserva_el_texto():
    hits = [{"text": "hecho 0", "score": 0.9, "scope": "global"}]
    salida = mp.presentar_recuerdos(hits, 8, variante="A")
    assert salida == [{"text": "- Registro (episodio, ?): hecho 0", "score": 0.9, "scope": "global"}]
    assert mp.presentar_recuerdos([], 8) == []
```

- [ ] **Step 3: Verlos fallar**

Run: `.venv/bin/python -m pytest -q test_memoria_procedencia.py 2>&1 | tail -3`
Expected: error de coleccion, `ModuleNotFoundError: No module named 'calipso.memoria_procedencia'` (el import de la linea 9; `experimentos.no_saber_banco` tampoco existe todavia).

- [ ] **Step 4: `calipso/memoria_procedencia.py` completo**

```python
"""La memoria con procedencia: lo que dijo Calipso es contexto, no evidencia
(spec 2026-09-11, secciones 2 y 4).

Un episodio del chat se guarda como el par `Pedro pregunto: ...\\nCalipso
respondio: ...` (server.py, el `remember` del final de `ws_chat`). Al leer,
ese par NO se le muestra crudo al modelo: se parte (`partir`), se limpia la
pregunta de los gestos (`limpiar_gestos`), se clasifica la respuesta
(`clasificar`) y se presenta con quien dijo que, cuando y por que ruta
(`presentar`). Un no-saber de Calipso se reemplaza por la frase fija: un
"no tengo registros" de ayer no es un recuerdo, y devolverselo al 7b como
recuerdo era lo que lo hacia repetirlo (h06 del smoke del abismo).

Todo es PURO y determinista: sin modelo, sin disco, sin red. Decidir al leer
es lo que permite afinar los patrones sin tocar lo guardado. Este modulo no
importa calipso.server (lo usan `abismo/fuentes.py`, que tiene la misma
regla, y `server._build_context`).
"""
from __future__ import annotations

import os
import re
import unicodedata

# --- la clasificacion (spec seccion 2, "la clasificacion es determinista") ---
#
# Sobre la respuesta en minusculas y sin acentos. Dos familias (ruling):
# los FUERTES degradan solos si arrancan dentro de los primeros
# POSICION_MAX chars (medido en 148 no-saber reales: mediana 0, p90 116,
# maximo 202); mas tarde la respuesta ya tiene contenido. Los DEBILES solo
# degradan si antes no hay ninguna oracion afirmativa con contenido. La
# otra clausula del spec para los debiles ("o si van con un fuerte") queda
# subsumida por la regla de posicion: un fuerte antes de POSICION_MAX ya
# degrada solo, y uno despues es, por ese mismo ruling, una respuesta con
# contenido que un debil al lado no vuelve no-saber (decision 4 del plan).
#
# La lista vive SOLO aca y se mide contra experimentos/no_saber_banco.py:
# afinarla es tocar estas tuplas y correr el banco, nunca el disco.

PATRONES_FUERTES = (
    r"no tengo registros?",
    r"no tengo (esa|esta|la|ninguna) informacion",
    r"no tengo informacion",
    r"no tengo (ese|el|ningun) dato",
    r"no tengo acceso",
    r"no me consta",
    r"no recuerdo",
    r"no encuentro (registro|informacion|nada)",
    r"no puedo (acceder|confirmar|verificar|recordar)",
    r"no esta (registrad|en mi memoria|en mi cronologia)",
    r"no hay (registro|informacion) (de|sobre)",
    # sumado por el banco (decision 3 del plan): "no hay informacion
    # disponible sobre su estado"; NO atrapa "no hay informacion adicional
    # disponible sobre este commit", que viene despues de un dato
    r"no hay informacion disponible",
)

PATRONES_DEBILES = (
    # `recordar` cubre `recordarme`; `proporcionar` cubre `proporcionarme`
    r"podrias (darme|proporcionar|recordar|decirme|contarme|compartir)",
    r"me podrias (recordar|decir|dar)",
    r"puedes (darme|proporcionar|recordar|decirme|contarme|compartir)",
    r"necesito mas (contexto|detalles)",
    r"dame mas detalles",
    r"cuentame (un poco )?mas",
)

POSICION_MAX = 250

# lo que abre una oracion sin decir nada: se pela antes de contar palabras
_RELLENO = re.compile(
    r"^(?:(?:claro|por supuesto|entendido|entiendo|de acuerdo|perfecto|vale|"
    r"ok|si|hola|buen dia|buenas|gracias|pedro)[,.!:;\s]*)+")
_MIN_PALABRAS = 3

_FUERTES = tuple(re.compile(p) for p in PATRONES_FUERTES)
_DEBILES = tuple(re.compile(p) for p in PATRONES_DEBILES)


def quitar_acentos(texto: str) -> str:
    """'informacion' con tilde y sin tilde son la misma palabra para los patrones."""
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


def _normalizar(respuesta: str) -> str:
    return quitar_acentos(respuesta).lower()


def _oraciones(texto: str) -> list[str]:
    """Oraciones COMPLETAS: cerradas por . ! ? o por un salto de linea. Un
    fragmento final sin cierre no cuenta (es lo que precede a un debil que
    esta en medio de la oracion: 'Claro, para poder ayudarte mejor, me
    podrias...')."""
    piezas = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", texto)]
    piezas = [p for p in piezas if p]
    if piezas and not re.search(r"[.!?]$", piezas[-1]) and not texto.endswith("\n"):
        piezas = piezas[:-1]
    return piezas


def _afirmativa_con_contenido(oracion: str) -> bool:
    """Ni pregunta ni relleno: por lo menos _MIN_PALABRAS palabras despues
    de pelar 'Claro, Pedro.' y parientes."""
    o = oracion.strip()
    if o.endswith("?") or o.startswith("¿") or o.startswith("?"):
        return False
    pelada = _RELLENO.sub("", o)
    return len(pelada.split()) >= _MIN_PALABRAS


def clasificar(respuesta: str) -> str:
    """'sin_dato' si la respuesta es un no-saber; 'dato' si informa algo
    (aunque sea una confabulacion: eso no se detecta sin modelo, lo ataca la
    procedencia + la consulta al abismo)."""
    low = _normalizar(respuesta or "")
    if not low.strip():
        return "sin_dato"
    for patron in _FUERTES:
        m = patron.search(low)
        if m and m.start() < POSICION_MAX:
            return "sin_dato"
    for patron in _DEBILES:
        m = patron.search(low)
        if m and not any(_afirmativa_con_contenido(o)
                         for o in _oraciones(low[:m.start()])):
            return "sin_dato"
    if low.rstrip().endswith("?") and not any(
            _afirmativa_con_contenido(o) for o in _oraciones(low)):
        return "sin_dato"
    return "dato"


# --- el parser, tolerante y en un solo lugar (spec seccion 2) --------------
#
# Lo viejo no siempre dice "Pedro pregunto:": de junio a agosto se guardo con
# acentos rotos (una A con tilde donde iba la o; en el ambito de proyecto por
# scope="auto"). `\S*` se come cualquier cola hasta los dos puntos.

_PAR = re.compile(
    r"^Pedro pregunt\S*:\s*(.*?)\nCalipso respondi\S*:\s*(.*)\Z", re.DOTALL)


def partir(texto: str) -> tuple[str, str] | None:
    """(pregunta, respuesta) si el texto es un par de chat; None si no."""
    m = _PAR.match(texto or "")
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def limpiar_gestos(pregunta: str) -> str:
    """Saca los gestos iniciales ('/local hola' -> 'hola') y colapsa el
    espacio. Lo viejo se guardo con `user_msg` crudo; lo nuevo con
    `chat_msg`, que ya viene limpio salvo cuando el mensaje era SOLO gestos
    (`parse_directives` cae al crudo: '/local' llega tal cual). Devuelve ''
    para ese caso: la basura del spec."""
    tokens = (pregunta or "").split()
    while tokens and tokens[0].startswith("/"):
        tokens.pop(0)
    return " ".join(tokens)


# --- la presentacion (spec seccion 2, invariantes 1-3) ----------------------

TOPE_PREGUNTA = 200
TOPE_RESPUESTA = 400
SIN_DATO = "Calipso no tenia el dato entonces"

# La variante la fija el porton (spec seccion 5): A = frase fija; B = se
# omite el renglon de Calipso cuando es sin_dato; off = el par crudo de antes
# (solo para medir el 'antes' sobre la misma rama). En produccion la variable
# no esta puesta y vale VARIANTE_DEFAULT.
VARIANTE_DEFAULT = "A"
VARIANTES = ("A", "B", "off")


def variante_activa() -> str:
    v = (os.environ.get("MEMORIA_PRESENTAR") or "").strip()
    return v if v in VARIANTES else VARIANTE_DEFAULT


def _recortar(texto: str, tope: int) -> str:
    plano = " ".join((texto or "").split())
    if len(plano) <= tope:
        return plano
    return plano[:tope].rstrip() + "..."


def presentar(texto: str, meta: dict | None = None, *,
              tope_pregunta: int = TOPE_PREGUNTA,
              tope_respuesta: int = TOPE_RESPUESTA,
              score: float | None = None,
              variante: str | None = None) -> str:
    """Lo que el modelo ve de un episodio: una vineta con procedencia.

    Par de chat:
        - Pedro dijo (2026-08-14): empece El nombre de la rosa
          Calipso contesto (local, 2026-08-14): Buena eleccion. Anotado...
    Par con un no-saber (variante A):
        - Pedro dijo (2026-09-10): quien me presto el libro rosa?
          Calipso no tenia el dato entonces (local, 2026-09-10).
    Lo que no parsea como par (metas, fichas): nunca el crudo sin etiqueta:
        - Registro (goal, 2026-08-14): Pedro definio una meta: ...
    Pregunta que era solo un gesto ('/local'): '' -- el lector la salta.

    `meta` tolera None y claves ausentes (los dobles de los tests pasan hits
    sin meta): fecha '?' y ruta '?'. La ruta sale de `ruta` (la usada, lo
    nuevo) o de `route` (la decidida, lo viejo).

    Variante `off` (solo para medir el 'antes' del porton): el crudo de
    main, `- (score) texto` si llega `score` (el system: prompt_compiler
    pegaba el score) y `- texto` si no (el abismo: fuentes.memoria nunca lo
    pego). Quien decide si viaja el score es `presentar_recuerdos`."""
    meta = meta or {}
    variante = variante or variante_activa()
    if variante == "off":
        return f"- ({score}) {texto}" if score is not None else f"- {texto}"
    fecha = str(meta.get("ts") or "")[:10] or "?"
    par = partir(texto)
    if par is None:
        kind = meta.get("kind") or "episodio"
        return f"- Registro ({kind}, {fecha}): {_recortar(texto, tope_respuesta)}"
    pregunta, respuesta = par
    pregunta = limpiar_gestos(pregunta)
    if not pregunta:
        return ""
    ruta = meta.get("ruta") or meta.get("route") or "?"
    lineas = [f"- Pedro dijo ({fecha}): {_recortar(pregunta, tope_pregunta)}"]
    if clasificar(respuesta) == "sin_dato":
        if variante == "A":
            lineas.append(f"  {SIN_DATO} ({ruta}, {fecha}).")
    else:
        lineas.append(f"  Calipso contesto ({ruta}, {fecha}): "
                      f"{_recortar(respuesta, tope_respuesta)}")
    return "\n".join(lineas)


def presentar_recuerdos(hits: list[dict], tope: int, *,
                        variante: str | None = None,
                        con_score: bool = True) -> list[dict]:
    """Los dos lectores (el system del turno y la fuente `memoria` del
    abismo) pasan por aca: presentar cada hit, SALTAR los vacios y recien
    ahi cortar a `tope` (spec: presentar ANTES del corte, para que un salto
    no achique el bloque). Devuelve los hits con `text` ya presentado (el
    resto del hit -score, meta, scope- viaja intacto).

    `con_score` solo importa en la variante `off`: el system de main pegaba
    `- (score) texto` (con_score=True, `_build_context`) y el abismo `- texto`
    (con_score=False, `fuentes.memoria`). En A y B el score nunca se ve."""
    salida = []
    for h in hits:
        texto = presentar(h.get("text") or "", h.get("meta"),
                          score=h.get("score") if con_score else None,
                          variante=variante)
        if not texto:
            continue
        salida.append({**h, "text": texto})
        if len(salida) >= tope:
            break
    return salida
```

- [ ] **Step 5: `experimentos/no_saber_banco.py` completo**

Las 51 respuestas son REALES (12 del fixture, 39 de los JSONL): se pegan tal cual, con sus acentos, porque son los datos contra los que se mide. `experimentos/` no tiene `__init__.py`: es un paquete de espacio de nombres, importable desde la raiz del repo (pytest inserta la raiz en `sys.path` por el `conftest.py`) y ejecutable con `python -m experimentos.no_saber_banco`.

```python
"""El banco de la clasificacion (spec de la memoria con procedencia, seccion
5): respuestas REALES y COMPLETAS del 7b, etiquetadas a mano, contra las que
se mide `memoria_procedencia.clasificar`. La UNICA fila recortada es
fixture[12] (la salida parcial del orquestador, 5085 chars de respuesta:
se pegan los primeros ~300): sobre el texto entero `clasificar` tambien da
`dato` y ningun patron fuerte aparece en ninguna posicion (verificado sobre
la copia del fixture), asi que el recorte no cambia lo que la fila mide; el
resto son commits y diffs que no aportan al banco.

Piso (test_memoria_procedencia.py): 0 falsos `sin_dato` sobre respuestas
con dato, y >= 90% de los no-saber atrapados. Un patron nuevo se afina ACA
primero: si atrapa un `dato`, no entra.

De donde sale cada respuesta:
  fixture[i]  experimentos/fixtures/memoria_smoke_home (chroma global, los 16
              episodios reales del smoke del abismo del 2026-09-10; el texto
              es la respuesta entera, con strip)
  <item>      experimentos/consulta_abismo_*.jsonl (campo `salida`, solo
              las que no tocan el corte de 400 chars y no llevan marca);
              `item` es la pregunta del experimento: mem-libro, cha-idea...

Las etiquetas siguen el spec: la confabulacion es `dato` (lo unico que se
detecta sin modelo es el no-saber); "El proyecto X no esta en la lista"
es `dato` (informa algo); una respuesta con dato que termina pidiendo
precision es `dato`.
"""
from __future__ import annotations

SIN_DATO = "sin_dato"
DATO = "dato"

# (etiqueta, respuesta, de donde / por que)
BANCO: list[tuple[str, str, str]] = [
    # --- el fixture del porton: los 5 no-saber ---
    (SIN_DATO,
     "Estaré encantado de ayudarte una vez que tenga acceso a esa información. "
     "Actualmente no tengo ese dato en mi memoria actual. ¿Puedes darme más "
     "detalles para que pueda buscarlo?",
     "fixture[0] mem-libro: el fuerte arranca en la posicion 85"),
    (SIN_DATO,
     "Entiendo. No tengo registros de quién te prestó un libro rosa anteriormente. "
     "Podrías revisar tus recuerdos o libretas personales para ver si encuentras "
     "algún detalle adicional que pueda ayudarme a recordarlo. ¿Tienes alguna otra "
     "información que pudiera ser relevante?",
     "fixture[1] libro rosa: 'Entiendo.' es relleno"),
    (SIN_DATO,
     ">No tengo registros de una conversación específica sobre el presupuesto para "
     "el taller. Podrías revisar tus notas o los chats antiguos para ver si "
     "encontramos alguna referencia al respecto. ¿Recuerdas algún detalle adicional "
     "que pueda ayudarme a localizar esa información?",
     "fixture[2] presupuesto: arranca con '>'"),
    (SIN_DATO,
     "Entiendo. No tengo registros de quién te prestó el libro rosa anteriormente. "
     "Podrías revisar tus recuerdos o libretas personales para ver si encuentras "
     "algún detalle adicional que pueda ayudarte a recordarlo. ¿Tienes alguna otra "
     "información que pudiera ser relevante?",
     "fixture[9] libro rosa, segunda pasada"),
    (SIN_DATO,
     "No tengo registros específicos de una conversación sobre el presupuesto para "
     "el taller en particular. ¿Podrías proporcionar más detalles o contextos que "
     "puedan ayudarme a localizar la información? Si recuerdas algún punto "
     "específico o contexto adicional, eso sería muy útil.",
     "fixture[10] presupuesto, segunda pasada"),
    # --- el fixture: los datos (dos verdades pescadas, dos generales) ---
    (DATO,
     "Entendido. Continuemos desde donde nos quedamos con Mariana en la "
     "conversación de agosto.\n\n[Charla con Mariana 2026-08-20] Entendido, lo "
     "anoto: Mariana te presto el libro y te lo recuerdo al terminar.\n[Charla con "
     "Mariana 2026-08-20] Mariana Quintero me presto el libro rosa, recordame "
     "devolverselo cuando lo termine.",
     "fixture[3] mariana: verdad sembrada, pescada de chats"),
    (DATO,
     "Entendido. Continuemos desde donde nos quedamos con Mariana en la "
     "conversación de agosto.\n\n[Charla con Mariana 2026-08-20] Entendido, lo "
     "anoto: Mariana te presto el libro y te lo recuerdo al terminar.\n[Charla con "
     "Mariana 2026-08-20] Mariana Quintero me presto el libro rosa, recordame "
     "devolverselo cuando lo termine.\n\n¿Necesitas que haga algo más relacionado "
     "con esta charla o tienes alguna otra información adicional sobre Mariana?",
     "fixture[11] mariana con pregunta final: termina en ? pero tiene contenido"),
    (DATO,
     "Un WebSocket es una tecnología que permite conexiones bidireccionales entre "
     "el servidor y el cliente, manteniendo abierta una sola conexión TCP para "
     "enviar datos en tiempo real. Esto facilita la comunicación continua sin "
     "necesidad de abrir múltiples peticiones HTTP.",
     "fixture[7] websocket"),
    (DATO,
     "¡Buen día, Pedro!\n\nEstamos avanzando bien en varios frentes:\n\n1. "
     "**Proyecto `mapa-ciudad`:** El backend está casi listo y la integración con "
     "la interfaz frontend avanza significativamente. Esperamos tener un prototipo "
     "funcional para finales de este mes.\n\n2. **Repo Calipso:** La rama "
     "`feat/abismo-system-podado` continúa su progreso, con ajustes en el sistema "
     "de aduana y las pruebas correspondientes. El trabajo está en WIP pero se "
     "espera tener una versión más estabilizada pronto.\n\n3. **Economía del "
     "proyecto:** Aún no tenemos los archivos necesarios para sembrar la economía, "
     "por lo que seguimos sin esta funcionalidad. Estamos trabajando en recuperar "
     "estos archivos desde los registros de Pedro.\n\n¿Hay algo específico sobre "
     "estos proyectos o tareas en las que te pueda ayudar hoy?",
     "fixture[14] buen dia: confabulacion de avances -> dato"),
    # --- el fixture: las confabulaciones son dato ---
    (DATO,
     "Entendido. Vamos a continuar exactamente donde lo dejamos.\n\nRecuerdo que te "
     "conté sobre un libro de ciencia ficción que comenzamos a leer juntos. Parece "
     "ser una trilogía ambientada en un futuro distópico donde las redes de "
     "inteligencia artificial han tomado el control del mundo. ¿Necesitas más "
     "detalles o quieres hablar de algún aspecto específico del libro?",
     "fixture[8] la confabulacion del spec: dato"),
    (DATO,
     "Entendido. Vamos a revisar los detalles del proyecto `mapa-ciudad`:\n\n1. "
     "**Objetivo:** Crear un mapa interactivo de la ciudad que integre información "
     "relevante para los usuarios locales.\n2. **Desarrollo Backend:**\n   - "
     "Implementación de una API geolocalización.\n   - Desarrollo de un backend "
     "local para manejar datos de localización y almacenamiento en base de datos."
     "\n3. **Integración Frontend:**\n   - Desarrollo frontend utilizando React.js."
     "\n   - Diseño intuitivo y funcional para usuarios finales.\n4. "
     "**Características:**\n   - Anotaciones y recursos relevantes que los usuarios "
     "pueden agregar directamente.\n   - Capas de información adicionales como "
     "servicios públicos, puntos de interés turístico y áreas verdes.\n5. "
     "**Progreso Actual:**\n   - Backend casi listo con pruebas en progreso.\n   - "
     "Interfaz frontend está integrando con el backend para un prototipo funcional "
     "a fines de este mes.\n\n¿Hay algún aspecto específico del proyecto "
     "`mapa-ciudad` en el que te gustaría más detalles o ayuda?",
     "fixture[13] mapa-ciudad inventado en lista: dato"),
    (DATO,
     "No pude completar la sintesis automatica. Resultado parcial del equipo:\n\n"
     "[Heraclito - analista]\n**Rama:** `feat/abismo-system-podado` — working tree "
     "**limpio** ahora (los cambios que estaban sueltos ya se commitearon).\n\n"
     "**Último commit:** `1b2d734` (hoy, 21:03) — *\"el system local podado, "
     "aterrizado byte a byte como se midió (h05, opción a de Pedro)\"*.",
     "fixture[12] (la unica fila RECORTADA: ~300 de 5085 chars; el texto entero "
     "tambien da dato y no tiene ningun fuerte) la salida parcial del "
     "orquestador: informa rama y commit reales -> dato (decision 2 del plan)"),
    # --- JSONL: no-saber fuertes ---
    (SIN_DATO,
     "No tengo registros específicos de qué hacías los domingos por la mañana, "
     "Pedro. ¿Podrías darme más detalles o alguna pista para ayudarte a recordar?",
     "mem-rutina"),
    (SIN_DATO,
     "No tengo esa información en la cronología de Pedro. Podría ser útil saber "
     "más sobre el contexto o si hay algún evento específico relacionado con "
     "mudarse de casa que puedas compartir.",
     "mem-fecha"),
    (SIN_DATO,
     "No tengo información sobre el mes en que te mudaste de casa en mi cronología "
     "actual. Podría ser porque ese evento no ha sido registrado aún o no está "
     "incluido en los datos disponibles para mí.\n\nSi tienes alguna otra pregunta "
     "o necesitas ayuda con algo más, estaré encantado de asistirte. ¿Hay algún "
     "otro detalle sobre el que quieras que busque?",
     "mem-fecha, largo"),
    (SIN_DATO,
     "Esa novela en particular no está registrada en mi memoria actualmente. "
     "¿Podrías darme más detalles sobre ella? Por ejemplo, el género, la autora o "
     "algún fragmento del título podría ayudarme a recordarlo.",
     "mem-libro: 'no esta registrada'"),
    (SIN_DATO,
     "No recuerdo exactamente el nombre de la novela que me contaste. ¿Podrías "
     "darme más detalles sobre ella? Por ejemplo, el género, algún personaje o una "
     "frase que te haya gustado. Eso podría ayudarme a recordarla.",
     "mem-libro: 'no recuerdo'"),
    (SIN_DATO,
     "No tengo registro de ningún link relacionado con Bazzite en chats anteriores. "
     "¿Podrías proporcionarme más detalles para poder ayudarte mejor?",
     "cha-link: singular 'registro'"),
    (SIN_DATO,
     "No tengo registros de ninguna receta que hayas compartido conmigo en otras "
     "conversaciones. ¿Podrías proporcionarme más detalles sobre la receta o el "
     "contexto en el que se discutió? Esto ayudará a localizarla si realmente "
     "existe en nuestras conversaciones pasadas.",
     "cha-receta"),
    (SIN_DATO,
     "No tengo información actualizada sobre el repositorio Atlas ni su rama "
     "actualmente. ¿Podrías proporcionarme más detalles o confirmar si estás "
     "interesado en un proyecto específico relacionado con Atlas?",
     "pro-estado"),
    (SIN_DATO,
     "No tengo registros específicos de lo último que se trabajó en "
     "`calipso-lector`. ¿Podrías proporcionar más detalles o fechas para "
     "orientarme mejor? Si necesitas revisar el historial del repositorio, puedo "
     "ayudarte a hacerlo.",
     "pro-ultimo"),
    (SIN_DATO,
     "Pedro, actualmente no hay una economía sembrada en el sistema, por lo que no "
     "puedo acceder a información sobre presupuestos o departamentos específicos. "
     "¿Podrías proporcionarme más detalles para que podamos continuar nuestra "
     "conversación?",
     "cha-decision: 'no puedo acceder' en la posicion 73"),
    (SIN_DATO,
     "No tengo registros específicos de estilos de música que hayas mencionado "
     "anteriormente, Pedro. ¿Podrías darme más detalles o contextos sobre esto?",
     "mem-pref"),
    (SIN_DATO,
     "No tengo información específica sobre el contenido actual del repositorio "
     "`atlas`. Podría haber sido un proyecto temporal o una carpeta con archivos "
     "que ya no son relevantes para tu trabajo actual. ¿Te interesaría que "
     "verificara qué archivos contiene el repositorio `atlas` localmente?",
     "pro-brief"),
    (SIN_DATO,
     "Verificando el estado del proyecto Calipso...\n\n```\ncalipso (~/calipso) "
     "rama main, ult. 2026-09-09, en foco\n```\n\nNo hay información sobre cambios "
     "sin commitear en el registro actual. Sin embargo, para obtener un reporte "
     "preciso, necesito verificar directamente el estado del repositorio.\n\n"
     "¿Deseas que verifique el estado actual del proyecto Calipso?",
     "pro-rama: la pregunta era por los cambios sin commitear y no los tiene; "
     "el fuerte arranca en la posicion 97"),
    (SIN_DATO,
     "El repositorio Atlas no tiene ninguna rama activa o cambios recientes "
     "registrados en mi memoria actual. No hay información disponible sobre su "
     "estado o ramas actuales. ¿Podrías proporcionar más detalles o especificar si "
     "estás interesado en un aspecto particular del repo de Atlas?",
     "pro-estado: 'no hay informacion disponible' (fuerte sumado por el banco)"),
    # --- JSONL: no-saber debiles (solo relleno antes) ---
    (SIN_DATO,
     "Claro, Pedro. ¿Podrías recordarme cuál era el punto exacto al que llegamos "
     "ayer? Esto me ayudará a retomar la idea de manera precisa.",
     "cha-idea: 'Claro, Pedro.' es relleno; el debil degrada"),
    (SIN_DATO,
     "Por supuesto, Pedro. ¿Puedes proporcionarme más detalles sobre la receta? "
     "¿De qué tipo de comida se trata y cuáles son los ingredientes principales? "
     "Esto me ayudará a encontrarla más rápidamente.",
     "cha-receta: debil tras relleno"),
    (SIN_DATO,
     "Claro, para poder ayudarte mejor, ¿me podrías recordar algunas cosas sobre tu "
     "hermana? Por ejemplo, ¿le gusta algún tipo de actividad en particular, tiene "
     "alguna pasión o preferencia especial? Esto me ayudará a sugerir un regalo "
     "adecuado.",
     "mem-gustos: el debil esta en medio de la primera oracion (fragmento, no "
     "cuenta como afirmativa)"),
    (SIN_DATO,
     "Claro, cuéntame más sobre tu hermana. ¿Qué le gusta? ¿Tiene algún hobby o "
     "interes en particular? Esto me ayudará a sugerir algo que le encantaría.",
     "mem-gustos: 'cuentame mas' (debil sumado por el banco)"),
    (SIN_DATO,
     "Claro, Pedro. ¿Podrías recordar un poco más sobre qué idea dejamos a medias "
     "ayer? Así podré ayudarte a retomarla de manera efectiva.",
     "cha-idea: 'podrias recordar' sin -me"),
    # --- JSONL: solo una pregunta ---
    (SIN_DATO,
     "Claro, Pedro. ¿Puedes recordar un poco más sobre la receta? Tenía algo "
     "específico o era de algún tipo de comida en particular?",
     "cha-receta: termina en ? y no afirma nada"),
    (SIN_DATO,
     "Claro, para poder ayudarte mejor, cuéntame más sobre tu hermana. ¿Qué le "
     "gusta? ¿Tiene alguna preferencia o tipo de regalo en particular?",
     "mem-gustos: termina en ?; 'cuentame mas' ademas"),
    # --- JSONL: el que se escapa (medido, se acepta dentro del 10%) ---
    (SIN_DATO,
     "Hablemos un poco más sobre el contexto para asegurarnos de que estemos en "
     "línea con lo que acordamos anteriormente. ¿Podrías recordar brevemente qué "
     "aspectos del presupuesto discutimos la última vez? Esto me ayudará a "
     "responder de manera más precisa y relevante.",
     "cha-decision: la primera oracion es relleno largo y protege al debil; "
     "un no-saber que NO se atrapa hoy"),
    # --- JSONL: datos que un patron torpe degradaria ---
    (DATO,
     "¡Recuerdo! Te contaste una novela llamada \"Cien años de soledad\" de Gabriel "
     "García Márquez. Es una obra maestra del realismo mágico y ha sido muy "
     "influyente en la literatura latinoamericana. ¿Te gustaría que te resumiera "
     "algunos de sus elementos más destacados?",
     "mem-libro: confabulacion (el libro sembrado era otro): dato; 'Recuerdo' no "
     "es 'no recuerdo'"),
    (DATO,
     "El proyecto `calipso-lector` no está en la lista de proyectos que tengo "
     "actualmente. Sin embargo, puedo consultar el abismo para obtener más "
     "información si deseas. ¿Te interesa que busque?\n\nSi es así, ¿podrías "
     "proporcionar alguna palabra clave o contexto adicional sobre este proyecto?",
     "pro-detalle: el caso del catastro (informa que no esta); el debil viene "
     "despues de una afirmativa con contenido"),
    (DATO,
     "No hay ningún proyecto llamado \"atlas\" en los registros actuales. Los "
     "proyectos listados son \"calipso\", \"Observatory-Global\" y \"mapa-ciudad\". "
     "¿Podrías proporcionar más detalles sobre el repositorio de atlas o confirmar "
     "si existe algún error en el nombre?",
     "pro-estado: catastro; 'no hay ningun proyecto' no es 'no hay registro de'"),
    (DATO,
     "El último commit en la rama `feat/abismo-1b` de Calipso se realizó el 8 de "
     "septiembre de 2026. No hay información adicional disponible sobre este "
     "commit en el contexto actual. ¿Necesitas más detalles sobre ese commit "
     "específico?",
     "pro-commit: dato y despues una duda; 'no hay informacion adicional "
     "disponible' NO debe atraparse"),
    (DATO,
     "El último commit de Calipso se realizó el 2026-09-09 en la rama main.",
     "pro-commit"),
    (DATO,
     "De acuerdo con mi memoria, Pedro, te dije que no soportas el metal pesado.",
     "mem-pref: dato ('de acuerdo' es relleno pero no hay debil ni ?)"),
    (DATO,
     "He anotado la fecha de tu hermana en mi memoria. Cumpleaños: 12 de octubre. "
     "¿Hay algo más que necesites recordar?",
     "neg-inline: termina en ? con contenido antes"),
    (DATO,
     "Me gustan los cafés sin azúcar. ¿Hay algo más en lo que te pueda ayudar?",
     "neg-menciona-recuerdo"),
    (DATO,
     "¡Buen día, Pedro! Estoy bien, gracias por preguntar. ¿Cómo estás tú? ¿Hay "
     "algo en particular de lo que quieras hablar hoy?",
     "neg-charla: un saludo no es un no-saber"),
    (DATO,
     "Claro, aquí tienes un one-liner de Python para invertir una cadena:\n\n"
     "```python\nprint(input()[::-1])\n```",
     "neg-codigo"),
    (DATO,
     "15% de 84000 es 12600.",
     "neg-matematica"),
    (DATO,
     "\"Estantería\" se dice \"shelf\" en inglés.",
     "neg-traduccion"),
    (DATO,
     "Sí, \"Calipso\" tiene un sonido elegante y misterioso. ¿Te gusta cómo se "
     "adapta a tu personalidad o estilo de trabajo?",
     "neg-menciona-proyecto"),
    (DATO,
     "Verificando...\n\n```\ncd ~/calipso\ngit status\n```\n\n```bash\nOn branch "
     "feat/abismo-1b\nYour branch is up to date with 'origin/feat/abismo-1b'.\n\n"
     "nothing to commit, working tree clean\n```\n\nNo hay cambios sin commitear "
     "en el proyecto Calipso.",
     "pro-rama: 'no hay cambios' informa"),
    (DATO,
     "La última discusión sobre el presupuesto se centró en revisar los gastos "
     "actuales y planificar una estrategia para optimizarlos. Sin embargo, no "
     "tenemos un registro detallado de esa conversación en nuestra memoria actual. "
     "¿Podrías darme más contexto o detalles para que pueda ayudarte mejor?",
     "cha-decision: confabula y despues duda: dato (la confabulacion la ataca "
     "la procedencia); 'no tenemos un registro' no es fuerte a proposito"),
    (DATO,
     "Has solicitado resumir un texto anteriormente en una línea, pero no has "
     "proporcionado el texto específico. ¿Podrías compartir el texto que deseas "
     "resumir?",
     "neg-este-chat: informa lo que paso en el chat; el debil viene despues"),
    (DATO,
     "Depende del público al que estés dirigiéndote y el contexto en el que se "
     "usarán las funciones. En español es más natural para usuarios locales, "
     "mientras que en inglés puede facilitar la comprensión entre desarrolladores "
     "internacionales. ¿Para qué proyecto sería mejor elegir uno u otro?",
     "neg-opinion"),
]


def medir(clasificar) -> dict:
    """Corre el clasificador sobre el banco: cuantos no-saber atrapa y cuantos
    datos degrada (los falsos). Devuelve tambien las filas que fallan, para
    leerlas en el rojo."""
    atrapados = falsos = 0
    no_saber = datos = 0
    fallas = []
    for etiqueta, respuesta, nota in BANCO:
        clase = clasificar(respuesta)
        if etiqueta == SIN_DATO:
            no_saber += 1
            if clase == SIN_DATO:
                atrapados += 1
            else:
                fallas.append(("se escapa", nota, respuesta[:80]))
        else:
            datos += 1
            if clase == SIN_DATO:
                falsos += 1
                fallas.append(("falso sin_dato", nota, respuesta[:80]))
    return {"no_saber": no_saber, "atrapados": atrapados, "datos": datos,
            "falsos": falsos, "fallas": fallas,
            "recall": atrapados / no_saber if no_saber else 0.0}


if __name__ == "__main__":
    from calipso import memoria_procedencia
    r = medir(memoria_procedencia.clasificar)
    print(f"no-saber: {r['atrapados']}/{r['no_saber']} atrapados "
          f"({r['recall']:.0%}); datos: {r['falsos']}/{r['datos']} falsos")
    for f in r["fallas"]:
        print("  ", *f)
```

- [ ] **Step 6: Verde, el banco a mano y la suite**

```bash
.venv/bin/python -m pytest -q test_memoria_procedencia.py 2>&1 | tail -1            # 24 passed
.venv/bin/python -m experimentos.no_saber_banco
# no-saber: 26/27 atrapados (96%); datos: 0/24 falsos
#    se escapa cha-decision: la primera oracion es relleno largo y protege al debil; ...
.venv/bin/python -m pytest -q --ignore=test_chat_live.py 2>&1 | tail -1; echo EXIT=$?  # base + 24, 0 failed
```

El que se escapa es el unico no-saber conocido que la regla de los debiles no atrapa ("Hablemos un poco mas sobre el contexto para asegurarnos de que estemos en linea con lo que acordamos anteriormente. ¿Podrias recordar brevemente...?": la primera oracion es relleno pero tiene 15 palabras). Esta en el banco a proposito, etiquetado `sin_dato`, para que el numero sea honesto y para que quien afine los patrones lo vea; el piso es 90% y esta en 96%.

- [ ] **Step 7: Commit**

```bash
git add calipso/memoria_procedencia.py experimentos/no_saber_banco.py test_memoria_procedencia.py
git commit -m "feat(memoria): memoria_procedencia -- el modulo puro que decide al leer: patrones fuertes (regla de posicion a 250 chars) y debiles (solo sin una afirmativa con contenido antes), clasificar/partir/limpiar_gestos/presentar (Pedro dijo / Calipso contesto con ruta y fecha, la frase fija para el no-saber, Registro para lo que no es un par, vacio para el gesto solo, topes 200/400) y presentar_recuerdos (saltar antes de cortar); el banco de 51 respuestas reales del 7b etiquetadas a mano con el piso (0 falsos sin_dato, 26/27 atrapados)"
```

---

### Task 2: El `remember` del chat con la pregunta limpia y los metadatos de procedencia + el doble y los tests del harness

**Files:**
- Modify: `test_abismo_chat.py:28-43` (`MemoriaFalsa`), y tres tests al final (tras `:685`)
- Modify: `calipso/server.py:4234-4243` (el bloque `# 5) recordar el intercambio` dentro de `ws_chat`, ancla `# 3. Corria sobre el event loop`)
- Test: `test_abismo_chat.py`, `test_memoria_ambito.py`

**Interfaces:**
- Consumes (todo local de `ws_chat`, `server.py:3407`): `chat_msg = directives["clean"]` (`:3527`, la pregunta limpia; `parse_directives` cae al crudo si el mensaje era solo gestos, `capabilities.py:255`), `chat_id` (`:3449` / `:3461` / `:3478`), `used_route` (`:3808` `= route`; `:3831` `"orchestrator"`; `:4101` `"subscription"` tras el alterno; `:4123` `"local"` tras el fallback), `model` (`:3629` `verdict.get("model")`; reasignado en `:3658`, `:3680`, `:4069`, `:4124` por `_route_model_name`, `:2213`), `verdict["route"]` (la decidida; pisada por /nube en `:3650`), `full`. `Scope.remember` (`memory.py:113`) descarta los kwargs con valor `None` (un `model` desconocido no rompe) y solo acepta str/int/float/bool (`procedencia=1` es int). El `chats.append` de `:4245-4250` ya usa `used_route` y `model`: el episodio y el chat dicen lo mismo.
- Produces: el episodio `Pedro pregunto: {chat_msg}\nCalipso respondio: {full.strip()}` con `scope="global"`, `route=<decidida>`, `kind="chat"`, `ruta=<usada>`, `modelo=<el que contesto>`, `chat=<id>`, `procedencia=1`. En el harness: `MemoriaFalsa.guardados: list[tuple[str, str, dict]]`.

- [ ] **Step 1: El doble y los tests (en rojo)**

`test_abismo_chat.py:28-43`, ANTES:

```python
class MemoriaFalsa:
    """Doble de `Memory`: lo que el turno usa (recall, load_core, remember)."""

    def __init__(self, core: str = ""):
        self.core = core
        self.recordado: list[str] = []

    def recall(self, query, n=5, ambitos=None):
        return []

    def load_core(self):
        return self.core

    def remember(self, text, scope="auto", **meta):
        self.recordado.append(text)
        return "id-falso"
```

DESPUES:

```python
class MemoriaFalsa:
    """Doble de `Memory`: lo que el turno usa (recall, load_core, remember).
    `recordado` son los textos (lo que los tests viejos asertan);
    `guardados` es cada llamada entera: (texto, scope, meta), para mirar la
    procedencia que el turno escribe (spec 2026-09-11)."""

    def __init__(self, core: str = ""):
        self.core = core
        self.recordado: list[str] = []
        self.guardados: list[tuple[str, str, dict]] = []

    def recall(self, query, n=5, ambitos=None):
        return []

    def load_core(self):
        return self.core

    def remember(self, text, scope="auto", **meta):
        self.recordado.append(text)
        self.guardados.append((text, scope, dict(meta)))
        return "id-falso"
```

Al final de `test_abismo_chat.py` (tras `test_la_senal_del_abismo_se_publica_al_pulso`, `:665-685`):

```python


# --- la procedencia del episodio (spec 2026-09-11, seccion 2) ---------------

def test_el_episodio_del_chat_lleva_la_pregunta_limpia_y_la_procedencia(chat):
    """Lo que se guarda: el par con `chat_msg` (sin el gesto) y los metadatos
    de quien contesto de verdad."""
    chat.turno("/local hola")
    assert len(chat.memoria.guardados) == 1
    texto, scope, meta = chat.memoria.guardados[0]
    assert texto == "Pedro pregunto: hola\nCalipso respondio: hola Pedro"
    assert scope == "global"
    assert meta == {"route": "local", "kind": "chat", "ruta": "local",
                    "modelo": "modelo-falso", "chat": chat.chat_id, "procedencia": 1}


def test_tras_un_fallback_la_ruta_guardada_es_la_usada_y_route_la_decidida(chat, monkeypatch):
    def api_que_revienta(url, payload, *resto):
        raise RuntimeError("litellm se cayo")
    monkeypatch.setattr(srv.dispatch, "_sse_text_chunks", api_que_revienta)
    chat.modelo.guiones = [["desde local"]]
    eventos = chat.turno("/api libro")
    assert [m.get("note") for m in de_tipo(eventos, "meta")] == [None, "fallback a local"]
    texto, scope, meta = chat.memoria.guardados[0]
    assert texto.startswith("Pedro pregunto: libro\n")
    assert (meta["route"], meta["ruta"]) == ("api", "local")
    assert meta["modelo"] == srv._route_model_name("local")
    assert meta["chat"] == chat.chat_id and meta["procedencia"] == 1


def test_con_el_orquestador_la_ruta_guardada_es_orchestrator(chat, monkeypatch):
    monkeypatch.setattr(srv, "_should_orchestrate", lambda *a, **k: True)

    async def equipo(ws, inbox, chat_msg, features, system, verdict, **kw):
        return "sintesis entera", None, None
    monkeypatch.setattr(srv, "_run_dynamic_team", equipo)
    chat.turno("libro")
    texto, scope, meta = chat.memoria.guardados[0]
    assert texto == "Pedro pregunto: libro\nCalipso respondio: sintesis entera"
    assert (meta["route"], meta["ruta"]) == ("local", "orchestrator")
```

- [ ] **Step 2: Verlos fallar**

Run: `.venv/bin/python -m pytest -q test_abismo_chat.py -k "procedencia or fallback_la_ruta or orquestador_la_ruta" 2>&1 | grep -E "^(E  |FAILED|[0-9]+ (passed|failed))"`
Expected: `3 failed, 19 deselected`: el plano con `- Pedro pregunto: hola / + Pedro pregunto: /local hola` (hoy se guarda `user_msg` crudo); el del fallback con `'Pedro pregunto: /api libro\nCalipso respondio: desde local'.startswith('Pedro pregunto: libro\n')` -> `False`; el del orquestador con `KeyError: 'ruta'`.

- [ ] **Step 3: El `remember` del chat**

`calipso/server.py:4234-4243` (dentro del bloque `# 5) recordar el intercambio`, `:4215-4243`; las lineas de arriba del comentario no cambian), ANTES:

```python
            # 3. Corria sobre el event loop, a diferencia del `remember` de
            #    la meta ocho lineas mas arriba (:2377), que ya va por hilo.
            if full.strip():
                try:
                    await asyncio.to_thread(
                        mem.remember,
                        f"Pedro pregunto: {user_msg}\nCalipso respondio: {full.strip()}",
                        scope="global", route=verdict["route"], kind="chat")
                except Exception:
                    pass    # recordar no puede voltear un turno ya contestado
```

DESPUES:

```python
            # 3. Corria sobre el event loop, a diferencia del `remember` de
            #    la meta ocho lineas mas arriba (:2377), que ya va por hilo.
            #
            # Y la procedencia (spec 2026-09-11, seccion 2): el par sigue
            # siendo el documento (el embedding no cambia), pero la pregunta
            # es la LIMPIA (`chat_msg`, sin el `/local` de adelante) y los
            # metadatos dicen quien contesto de verdad: `ruta` es la USADA
            # (`used_route`: local tras un fallback, orchestrator con equipo,
            # subscription con el alterno; `route` sigue siendo la decidida),
            # `modelo` el que contesto, `chat` el id y `procedencia=1` la
            # marca para contar y para la idempotencia del reindex. Lo que
            # sea None lo descarta `Scope.remember`. Se lee con
            # `memoria_procedencia.presentar`, nunca crudo.
            if full.strip():
                try:
                    await asyncio.to_thread(
                        mem.remember,
                        f"Pedro pregunto: {chat_msg}\nCalipso respondio: {full.strip()}",
                        scope="global", route=verdict["route"], kind="chat",
                        ruta=used_route, modelo=model, chat=chat_id, procedencia=1)
                except Exception:
                    pass    # recordar no puede voltear un turno ya contestado
```

Lo que `test_memoria_ambito.py:82-121` exige en este tramo sigue ahi: `scope="global"` literal, `asyncio.to_thread`, `except Exception`, `pregunto` y `respondio`, y ninguna `Ã` (el comentario nuevo no cita las variantes rotas).

- [ ] **Step 4: Verde y suite**

```bash
.venv/bin/python -m pytest -q test_abismo_chat.py test_memoria_ambito.py 2>&1 | tail -1     # 22 + 11 passed
.venv/bin/python -m pytest -q --ignore=test_chat_live.py 2>&1 | tail -1; echo EXIT=$?         # base + 27, 0 failed
```

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py test_abismo_chat.py
git commit -m "feat(memoria): el episodio del chat con procedencia -- la pregunta guardada es la limpia (chat_msg, sin el /local de adelante) y los metadatos dicen quien contesto de verdad: ruta usada (local tras un fallback, orchestrator con equipo, subscription con el alterno; route sigue siendo la decidida), modelo, chat y procedencia=1; MemoriaFalsa captura (texto, scope, meta) y tres tests por harness lo fijan"
```

---

### Task 3: Los dos lectores presentan ANTES del corte -- `_build_context` + `context_sections` y `fuentes.memoria` bajo el techo del bloque

**Files:**
- Create: `test_memoria_lectores.py`
- Modify: `calipso/server.py:101` (import), `:2955-2957` (el recall de `_build_context`, `:2941`)
- Modify: `calipso/prompt_compiler.py:222-228` (`context_sections`, `:198`)
- Modify: `calipso/abismo/fuentes.py:13` (import), `:114-119` (`memoria`, `:109`)
- Test: `test_memoria_lectores.py`, `test_abismo_fuentes.py`, `test_abismo_system_medido.py`, `test_abismo_memoria_recall.py`, `test_economia_brief.py`; a mano `test_prompt_compiler.py`

**Interfaces:**
- Consumes: `memoria_procedencia.presentar_recuerdos(hits, tope, *, variante=None, con_score=True)` (Task 1); `Memory.recall(query, n, ambitos=None) -> [{text, meta, score, scope}]` (`memory.py:203-215`, corta a n ANTES del filtro por score: por eso se pide n=8 / 12 y se corta despues); `RECALL_MIN_SCORE = 0.30`, `RECALL_MAX = 4` (`server.py:2802-2803`); `RECALL_N = 12`, `RECALL_TOP = 8`, `RECALL_UMBRAL = 0.20` (`fuentes.py:19-21`); `consulta.etiquetar` y `ABISMO_BLOQUE_MAX = 2000` (`consulta.py:23-36`, corte duro por chars sobre el bloque ENTERO: no cambia); `render_context` (`prompt_compiler.py:242-243`, `=== {title} ===\n{body}`).
- Produces: `_build_context` pasa a `compile_context` un `recalled` cuyos `text` son vinetas presentadas (score/meta/scope intactos); `context_sections` pega `text` sin `(score)`; `fuentes.memoria` arma `recuerdos:\n<vinetas>` en `MEDIA_AGUA`. El titulo `Recuerdos relevantes` no cambia (`test_prompt_compiler.py:37` lo indexa). `fuentes` sigue sin importar `server` (deps inyectadas) y `memoria_procedencia` tampoco.

- [ ] **Step 1: Los tests (en rojo)**

`test_memoria_lectores.py`, completo:

```python
"""Los dos lectores de la memoria episodica presentan con procedencia y
cortan DESPUES de presentar (spec 2026-09-11, seccion 2 y 5): el system del
turno (`_build_context` -> `context_sections`) y la fuente `memoria` del
abismo (`fuentes.memoria`), esta bajo el techo del bloque (`etiquetar`)."""
from __future__ import annotations

import calipso.server as srv
from calipso import chronology, memoria_procedencia as mp, prompt_compiler
from calipso.abismo import anillos, consulta, fuentes

META = {"ts": "2026-09-10T20:58:05", "route": "local", "kind": "chat"}
BASURA = "Pedro pregunto: /local\nCalipso respondio: hola"
NO_SABER = ("Pedro pregunto: /local quien me presto el libro rosa?\n"
            "Calipso respondio: Entiendo. No tengo registros de quien te presto un libro.")


def _par(i: int) -> str:
    return f"Pedro pregunto: pregunta {i}\nCalipso respondio: respuesta {i}"


class _MemoriaConHits:
    def __init__(self, hits, core=""):
        self._hits, self._core = hits, core
        self.pedido = None

    def recall(self, query, n=5, ambitos=None):
        self.pedido = {"query": query, "n": n}
        return self._hits[:n]

    def load_core(self):
        return self._core


def _hit(texto, score, meta=META):
    return {"text": texto, "meta": meta, "score": score, "scope": "global"}


# --- context_sections -------------------------------------------------------

def test_context_sections_pega_los_recuerdos_ya_presentados_sin_score():
    presentado = mp.presentar(_par(1), META, variante="A")
    secciones = prompt_compiler.context_sections(
        "Eres Calipso.", recalled=[{"text": presentado, "score": 0.91, "meta": META}])
    cuerpo = dict(secciones)["Recuerdos relevantes"]
    assert cuerpo == presentado
    assert "0.91" not in cuerpo and "Pedro pregunto:" not in cuerpo
    assert cuerpo.startswith("- Pedro dijo (2026-09-10): pregunta 1\n  Calipso contesto (local, 2026-09-10): respuesta 1")


def test_context_sections_sin_recuerdos_no_arma_la_seccion():
    secciones = prompt_compiler.context_sections("Eres Calipso.", recalled=[])
    assert "Recuerdos relevantes" not in dict(secciones)


# --- _build_context ---------------------------------------------------------

def test_build_context_presenta_salta_la_basura_y_corta_despues(monkeypatch):
    hits = [_hit(BASURA, 0.95), _hit(NO_SABER, 0.9)] + [
        _hit(_par(i), round(0.8 - i * 0.05, 2)) for i in range(7)]
    mem = _MemoriaConHits(hits)
    monkeypatch.setattr(srv, "mem", mem)
    monkeypatch.setattr(srv, "RECALL_MAX", 4)
    monkeypatch.setattr(srv, "RECALL_MIN_SCORE", 0.30)
    monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)
    system = srv._build_context("que libro lei", "runtime", {"type": "chat"})
    assert mem.pedido["n"] == 8
    bloque = system.split("=== Recuerdos relevantes ===\n")[1].split("\n\n===")[0]
    vinetas = [v for v in bloque.split("\n- ") if v]
    # 8 pedidos: la basura se salta, el no-saber degradado y 3 pares -> 4 vinetas
    assert len(vinetas) == 4
    assert "Pedro dijo (2026-09-10): quien me presto el libro rosa?" in bloque
    assert "Calipso no tenia el dato entonces (local, 2026-09-10)." in bloque
    assert "No tengo registros" not in bloque
    assert "pregunta 2" in bloque and "pregunta 3" not in bloque
    assert "Pedro pregunto:" not in system and "/local" not in bloque


def test_build_context_bajo_el_umbral_no_entra_y_sin_hits_no_hay_seccion(monkeypatch):
    mem = _MemoriaConHits([_hit(_par(1), 0.1)])
    monkeypatch.setattr(srv, "mem", mem)
    system = srv._build_context("hola", "runtime", {"type": "chat"})
    assert "Recuerdos relevantes" not in system


def test_build_context_honra_la_variante_del_porton(monkeypatch):
    mem = _MemoriaConHits([_hit(NO_SABER, 0.9)])
    monkeypatch.setattr(srv, "mem", mem)
    monkeypatch.setenv("MEMORIA_PRESENTAR", "B")
    system = srv._build_context("hola", "runtime", {"type": "chat"})
    assert "Pedro dijo (2026-09-10): quien me presto el libro rosa?" in system
    assert "no tenia el dato" not in system
    monkeypatch.setenv("MEMORIA_PRESENTAR", "off")
    system = srv._build_context("hola", "runtime", {"type": "chat"})
    assert f"- (0.9) {NO_SABER}" in system


# --- fuentes.memoria --------------------------------------------------------

def test_fuentes_memoria_presenta_y_corta_a_recall_top_despues(tmp_path, monkeypatch):
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)
    hits = [_hit(BASURA, 0.95)] + [_hit(_par(i), round(0.9 - i * 0.05, 2)) for i in range(11)]
    mem = _MemoriaConHits(hits)
    bloques = fuentes.memoria("que libro lei", mem)
    assert mem.pedido["n"] == fuentes.RECALL_N
    episodico = [t for t, a in bloques if a == anillos.MEDIA_AGUA]
    assert len(episodico) == 1
    texto = episodico[0]
    assert texto.startswith("recuerdos:\n- Pedro dijo (2026-09-10): pregunta 0\n  Calipso contesto (local, 2026-09-10): respuesta 0")
    assert texto.count("- Pedro dijo") == fuentes.RECALL_TOP == 8
    assert "pregunta 7" in texto and "pregunta 8" not in texto
    assert "/local" not in texto and "Pedro pregunto:" not in texto


def test_fuentes_memoria_bajo_el_techo_del_bloque(tmp_path, monkeypatch):
    """Ocho episodios del orquestador (5000+ chars cada uno) presentados con
    los topes: cada vineta queda acotada y el bloque etiquetado cae bajo
    ABISMO_BLOQUE_MAX con las primeras vinetas ENTERAS. El corte sigue
    siendo de `etiquetar`, no de la fuente."""
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)
    largo = "Pedro pregunto: como viene el repo?\nCalipso respondio: " + "x" * 5000
    hits = [_hit(largo, round(0.9 - i * 0.01, 2)) for i in range(8)]
    bloques = fuentes.memoria("como viene el repo", _MemoriaConHits(hits))
    texto = [t for t, a in bloques if a == anillos.MEDIA_AGUA][0]
    vinetas = texto.split("\n- ")[1:]
    assert len(vinetas) == 8
    assert all(len(v) <= mp.TOPE_PREGUNTA + mp.TOPE_RESPUESTA + 80 for v in vinetas)
    etiquetado = consulta.etiquetar("memoria", bloques)
    assert len(etiquetado) <= consulta.ABISMO_BLOQUE_MAX
    primera = "- Pedro dijo (2026-09-10): como viene el repo?\n  Calipso contesto (local, 2026-09-10): " + "x" * 400 + "..."
    assert etiquetado.count(primera) >= 2


def test_fuentes_memoria_tolera_hits_sin_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)
    bloques = fuentes.memoria("hecho", _MemoriaConHits([{"text": "hecho 0", "score": 0.9, "scope": "global"}]))
    texto = [t for t, a in bloques if a == anillos.MEDIA_AGUA][0]
    assert texto == "recuerdos:\n- Registro (episodio, ?): hecho 0"


def test_fuentes_memoria_off_es_el_bloque_crudo_de_main_sin_score(tmp_path, monkeypatch):
    """La condicion `antes` del porton: con MEMORIA_PRESENTAR=off la fuente
    del abismo pega `- texto` SIN score, como fuentes.py:118 de main (el
    score solo lo pegaba el system). Pasa en main y tiene que seguir
    pasando: es el control de que `off` reproduce el abismo byte a byte."""
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    monkeypatch.setenv("MEMORIA_PRESENTAR", "off")
    bloques = fuentes.memoria("que libro lei", _MemoriaConHits([_hit(_par(1), 0.9)]))
    texto = [t for t, a in bloques if a == anillos.MEDIA_AGUA][0]
    assert texto == "recuerdos:\n- " + _par(1)
    assert "0.9" not in texto
```

- [ ] **Step 2: Verlos fallar**

Run: `.venv/bin/python -m pytest -q test_memoria_lectores.py 2>&1 | grep -E "^(E   |FAILED|[0-9]+ (passed|failed))"`
Expected: `6 failed, 3 passed`: `context_sections` con `'- (0.91) - Pedro dijo...' == '- Pedro dijo...'` (hoy antepone el score); los dos de `_build_context` con `'Pedro dijo (2026-09-10): quien me presto el libro rosa?' in '- (0.95) Pedro pregunto: /local\nCalipso respondio: hola\n- (0.9) Pedro pregunto: ...'` (el par crudo, la basura adentro); `fuentes` con `startswith('recuerdos:\n- Pedro dijo ...')` -> `False` (`'recuerdos:\n- Pedro pregunto: /local\nCalipso respondio: hola\n- ...'`), `all(<genexpr>)` -> `False` (vinetas de 5000 chars) y `'recuerdos:\n- hecho 0' == 'recuerdos:\n- Registro (episodio, ?): hecho 0'`. Los tres que pasan son los controles: dos negativos (`sin_recuerdos_no_arma_la_seccion`, `bajo_el_umbral_no_entra`) y `fuentes_memoria_off_es_el_bloque_crudo_de_main_sin_score`, que en main pasa porque main YA pega `- texto` sin score (`fuentes.py:118`) y en la rama tiene que seguir pasando (es lo que hace `con_score=False`).

- [ ] **Step 3: `server.py` -- el import y `_build_context`**

En `calipso/server.py:101`, debajo de `from calipso import aduana  # noqa: E402`:

```python
from calipso import memoria_procedencia  # noqa: E402
```

`calipso/server.py:2955-2957` (dentro de `_build_context`, `:2941`; el resto de la funcion no cambia), ANTES:

```python
    # --- sufijo volátil ---
    recalled = [r for r in mem.recall(user_msg, n=8)
                if r["score"] >= RECALL_MIN_SCORE][:RECALL_MAX]
```

DESPUES:

```python
    # --- sufijo volátil ---
    # con procedencia (spec 2026-09-11): se pide n=8, se PRESENTA cada hit
    # (quien dijo que, cuando, por que ruta; el no-saber degradado; el
    # gesto sin texto saltado) y recien ahi se corta a RECALL_MAX, para que
    # un salto no achique el bloque. `text` de cada item ya es la vineta.
    recalled = memoria_procedencia.presentar_recuerdos(
        [r for r in mem.recall(user_msg, n=8) if r["score"] >= RECALL_MIN_SCORE],
        RECALL_MAX)
```

- [ ] **Step 4: `prompt_compiler.py`**

`calipso/prompt_compiler.py:222-228` (dentro de `context_sections`, `:198-239`), ANTES:

```python
    if recalled:
        lines = "\n".join(
            f"- ({item.get('score')}) {item.get('text')}"
            for item in recalled
            if item.get("text"))
        if lines:
            sections.append(("Recuerdos relevantes", lines))
```

DESPUES:

```python
    if recalled:
        # cada `text` ya viene presentado con procedencia (vineta de dos
        # lineas, sin score: `memoria_procedencia.presentar_recuerdos`, que
        # corre en `_build_context` ANTES del corte); aca solo se pegan
        lines = "\n".join(
            str(item.get("text"))
            for item in recalled
            if item.get("text"))
        if lines:
            sections.append(("Recuerdos relevantes", lines))
```

- [ ] **Step 5: `abismo/fuentes.py`**

`calipso/abismo/fuentes.py:13`, ANTES: `from calipso import chats, chronology` -> DESPUES: `from calipso import chats, chronology, memoria_procedencia`.

`calipso/abismo/fuentes.py:114-119` (dentro de `memoria`, `:109-134`; `del core`, `cronologia` y `libro personal` no cambian), ANTES:

```python
    bloques: list[tuple[str, int]] = []
    hits = [h for h in mem.recall(pregunta, n=RECALL_N)
            if h.get("score", 0) >= RECALL_UMBRAL][:RECALL_TOP]
    if hits:
        lineas = "\n".join(f"- {h['text']}" for h in hits)
        bloques.append((f"recuerdos:\n{lineas}", anillos.MEDIA_AGUA))
```

DESPUES:

```python
    bloques: list[tuple[str, int]] = []
    # con procedencia (spec 2026-09-11): presentar cada hit y recien ahi
    # cortar a RECALL_TOP, como en server._build_context. El techo del
    # bloque entero sigue siendo de `consulta.etiquetar`. `con_score=False`:
    # esta fuente nunca pego el score (solo cuenta en la variante off).
    recuerdos = memoria_procedencia.presentar_recuerdos(
        [h for h in mem.recall(pregunta, n=RECALL_N)
         if h.get("score", 0) >= RECALL_UMBRAL],
        RECALL_TOP, con_score=False)
    if recuerdos:
        lineas = "\n".join(r["text"] for r in recuerdos)
        bloques.append((f"recuerdos:\n{lineas}", anillos.MEDIA_AGUA))
```

- [ ] **Step 6: Verde y suite**

```bash
.venv/bin/python -m pytest -q test_memoria_lectores.py test_abismo_fuentes.py test_abismo_system_medido.py test_abismo_memoria_recall.py test_economia_brief.py 2>&1 | tail -1
.venv/bin/python test_prompt_compiler.py | tail -1                                     # OK: prompt compiler verificable
.venv/bin/python -m pytest -q --ignore=test_chat_live.py 2>&1 | tail -1; echo EXIT=$?  # base + 36, 0 failed
```

`test_abismo_fuentes.py:137-148` sigue verde porque `presentar` conserva el texto de un hit que no parsea (`Registro (episodio, ?): hecho 0`) y el umbral corre antes; `test_abismo_system_medido.py:81-87` llama a `_build_context` real con el `mem` de la suite (home vacio: sin recuerdos) y compara solo Sistema y Contrato interno.

- [ ] **Step 7: Commit**

```bash
git add calipso/server.py calipso/prompt_compiler.py calipso/abismo/fuentes.py test_memoria_lectores.py
git commit -m "feat(memoria): los dos lectores presentan con procedencia ANTES del corte -- _build_context pide n=8, presenta, salta el gesto solo y recien ahi corta a RECALL_MAX; context_sections pega la vineta de dos lineas sin score; fuentes.memoria igual con RECALL_TOP y el techo del bloque sigue en etiquetar; el par crudo no existe mas en ningun prompt; tests con el corte despues de presentar y bajo el techo"
```

---

### Task 4: `calipso/memoria_reindex.py` (`--vista` / `--aplicar` / `--forzar`) + los tests sobre homes temporales y la copia del fixture + la excepcion del canario

**Files:**
- Create: `calipso/memoria_reindex.py`
- Create: `test_memoria_reindex.py`
- Modify: `test_aduana_canario.py:51-53` (una linea nueva en `EXCEPCIONES`, tras `launch_calipso.py:main`)
- Test: `test_memoria_reindex.py`, `test_aduana_canario.py`, `test_aislacion_home.py`

**Interfaces:**
- Consumes: `memoria_procedencia.partir`, `limpiar_gestos`, `clasificar` (Task 1); `chromadb.PersistentClient(path)`, `Client.get_collection(name, embedding_function=None)` (levanta `chromadb.errors.NotFoundError` si no existe), `Collection.get(include=["documents", "metadatas"]) -> {ids, documents, metadatas}` alineados, `Collection.update(ids, metadatas)` (merge; `None` borra; sin `documents` no re-embebe; conserva id/documento/embedding/count; idempotente -- sondeado sobre una copia del fixture, chromadb 1.5.9), `Collection.count()`; `CALIPSO_HOME` (layout `global/chroma` y `projects/<slug>/chroma`, `memory.py:164-172`), `CALIPSO_PORT` (`launch_calipso.py:29`).
- Produces: `home() -> Path`, `puerto() -> int`, `ambitos(base) -> [(nombre, chroma_dir)]`, `_server_prendido(port, host="127.0.0.1") -> bool`, `abrir(chroma_dir) -> Collection | None`, `revisar(col) -> {episodios, con_procedencia, parsean, chat_no_parsean, no_chat, sin_dato, basura, raros, pendientes}`, `aplicar(col, revision) -> int`, `main(argv=None, salida=None) -> int` (0 ok, 1 sin ambitos, 2 server prendido), `COLECCION = "episodic"`, `LOTE = 100`. La linea por ambito: `<nombre>: N episodios, N con procedencia, N parsean como chat, N kind=chat que NO parsean, N no chat, N sin_dato, N basura, N raros -> N por reindexar`.

- [ ] **Step 1: Los tests (en rojo)**

`test_memoria_reindex.py`, completo:

```python
"""El reindexado sobre un home temporal (spec 2026-09-11, secciones 3 y 5):
`--vista` no escribe; `--aplicar` conserva ids, documentos, embeddings y
cantidad, preserva las claves viejas y agrega `procedencia` y `ruta`; es
idempotente; cuenta lo que no parsea; se niega con el puerto ocupado y
sigue con `--forzar`. Al final, sobre una copia del fixture real del porton.

Los chromas de prueba se arman SIN modelo (embeddings explicitos): asi el
test tarda medio segundo y no depende del cache de HuggingFace. El del
fixture real trae la funcion de embeddings persistida y `update` la carga
(offline, del cache; ~5 s la primera vez en el proceso)."""
from __future__ import annotations

import io
import pathlib
import shutil
import socket

import chromadb
import pytest

from calipso import memoria_reindex as mr

FIXTURE = pathlib.Path(__file__).resolve().parent / "experimentos" / "fixtures" / "memoria_smoke_home"

CHAT_DATO = "Pedro pregunto: /local que libro lei\nCalipso respondio: El nombre de la rosa."
CHAT_SIN_DATO = "Pedro pregunto: quien me presto el libro?\nCalipso respondio: No tengo registros de eso."
CHAT_BASURA = "Pedro pregunto: /nube\nCalipso respondio: Hola, en que te ayudo?"
CHAT_VIEJO = "Pedro preguntÃ³: hola\nCalipso respondiÃ³: Hola Pedro."
META_GOAL = "Pedro definio una meta: terminar\nCalipso creo Goal Mode: g-1"


def _sembrar(chroma_dir: pathlib.Path, filas: list[tuple[str, str, dict]]):
    cli = chromadb.PersistentClient(path=str(chroma_dir))
    col = cli.get_or_create_collection("episodic", metadata={"hnsw:space": "cosine"})
    if filas:
        col.add(ids=[f[0] for f in filas], documents=[f[1] for f in filas],
                metadatas=[f[2] for f in filas],
                embeddings=[[0.1 * (i + 1), 0.2, 0.3] for i in range(len(filas))])
    return col


def _leer(chroma_dir: pathlib.Path) -> dict:
    col = chromadb.PersistentClient(path=str(chroma_dir)).get_collection("episodic")
    g = col.get(include=["documents", "metadatas", "embeddings"])
    return {"count": col.count(), "ids": list(g["ids"]), "docs": list(g["documents"]),
            "metas": list(g["metadatas"]),
            "emb": [list(map(float, e)) for e in g["embeddings"]]}


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    monkeypatch.setenv("CALIPSO_PORT", "1")     # nada escucha en el 1
    g = tmp_path / "global" / "chroma"
    _sembrar(g, [
        ("m1", CHAT_DATO, {"ts": "2026-09-10T20:58:05", "route": "local", "kind": "chat"}),
        ("m2", CHAT_SIN_DATO, {"ts": "2026-09-10T21:00:00", "route": "api", "kind": "chat"}),
        ("m3", CHAT_BASURA, {"ts": "2026-09-10T21:01:00", "route": "local", "kind": "chat"}),
        ("m4", "un episodio roto sin forma de par", {"ts": "2026-09-10T21:02:00", "kind": "chat"}),
        ("m5", CHAT_DATO, {"ts": "2026-09-10T21:03:00"}),                  # sin kind: es chat
        ("m6", "Pedro pregunto: ya\nCalipso respondio: reindexado",
         {"ts": "2026-09-11T08:00:00", "route": "local", "ruta": "local",
          "kind": "chat", "chat": "c1", "modelo": "q", "procedencia": 1}),  # lo nuevo
    ])
    p = tmp_path / "projects" / "var-home-pedro-calipso" / "chroma"
    _sembrar(p, [
        ("p1", CHAT_VIEJO, {"ts": "2026-07-01T10:00:00", "route": "local", "kind": "chat"}),
        ("p2", META_GOAL, {"ts": "2026-08-14T09:00:00", "route": "goal", "kind": "goal"}),
    ])
    (tmp_path / "projects" / "sin-chroma").mkdir(parents=True)          # se ignora
    (tmp_path / "memoria" / "departamento" / "atlas" / "chroma").mkdir(parents=True)
    return tmp_path


def _correr(*args) -> tuple[int, str]:
    out = io.StringIO()
    codigo = mr.main(list(args), salida=out)
    return codigo, out.getvalue()


def test_ambitos_solo_los_que_existen_con_sqlite(home):
    nombres = [n for n, _ in mr.ambitos(home)]
    assert nombres == ["global", "projects/var-home-pedro-calipso"]


def test_vista_cuenta_y_no_escribe(home):
    antes = _leer(home / "global" / "chroma")
    codigo, texto = _correr("--vista")
    assert codigo == 0
    assert ("global: 6 episodios, 1 con procedencia, 5 parsean como chat, "
            "1 kind=chat que NO parsean, 0 no chat, 1 sin_dato, 1 basura, 0 raros "
            "-> 4 por reindexar") in texto
    assert ("projects/var-home-pedro-calipso: 2 episodios, 0 con procedencia, "
            "1 parsean como chat, 0 kind=chat que NO parsean, 1 no chat, 0 sin_dato, "
            "0 basura, 0 raros -> 1 por reindexar") in texto
    assert _leer(home / "global" / "chroma") == antes


def test_aplicar_conserva_ids_documentos_embeddings_y_cantidad_y_mergea(home):
    antes = _leer(home / "global" / "chroma")
    codigo, texto = _correr("--aplicar")
    assert codigo == 0, texto
    assert "global: 4 episodios reindexados; count 6 -> 6" in texto
    assert "OJO" not in texto
    despues = _leer(home / "global" / "chroma")
    assert (despues["count"], despues["ids"], despues["docs"], despues["emb"]) == (
        antes["count"], antes["ids"], antes["docs"], antes["emb"])
    por_id = dict(zip(despues["ids"], despues["metas"]))
    # las claves viejas quedan, las nuevas se suman, sin None
    assert por_id["m1"] == {"ts": "2026-09-10T20:58:05", "route": "local", "kind": "chat",
                            "procedencia": 1, "ruta": "local"}
    assert por_id["m2"]["ruta"] == "api" and por_id["m2"]["procedencia"] == 1
    assert por_id["m3"]["procedencia"] == 1            # la basura tambien se marca
    assert por_id["m5"] == {"ts": "2026-09-10T21:03:00", "procedencia": 1}   # sin route: sin ruta
    # lo que no parsea y lo ya reindexado no se tocan
    assert por_id["m4"] == {"ts": "2026-09-10T21:02:00", "kind": "chat"}
    assert por_id["m6"]["chat"] == "c1" and por_id["m6"]["modelo"] == "q"
    # el proyecto: lo viejo con acentos rotos entra, la meta no
    proyecto = dict(zip(*[_leer(home / "projects" / "var-home-pedro-calipso" / "chroma")[k]
                          for k in ("ids", "metas")]))
    assert proyecto["p1"] == {"ts": "2026-07-01T10:00:00", "route": "local", "kind": "chat",
                              "procedencia": 1, "ruta": "local"}
    assert proyecto["p2"] == {"ts": "2026-08-14T09:00:00", "route": "goal", "kind": "goal"}


def test_la_segunda_corrida_no_cambia_nada_y_lo_dice(home):
    _correr("--aplicar")
    despues_1 = _leer(home / "global" / "chroma")
    codigo, texto = _correr("--aplicar")
    assert codigo == 0
    assert "global: 6 episodios, 5 con procedencia" in texto
    assert "-> 0 por reindexar" in texto
    assert "global: nada que escribir (ya reindexado o sin pares de chat)" in texto
    assert _leer(home / "global" / "chroma") == despues_1


def test_se_niega_con_el_puerto_ocupado_y_sigue_con_forzar(home, monkeypatch):
    escucha = socket.socket()
    escucha.bind(("127.0.0.1", 0))
    escucha.listen(1)
    monkeypatch.setenv("CALIPSO_PORT", str(escucha.getsockname()[1]))
    try:
        antes = _leer(home / "global" / "chroma")
        codigo, texto = _correr("--aplicar")
        assert codigo == 2 and "apagalo (o --forzar)" in texto
        assert _leer(home / "global" / "chroma") == antes
        # `--vista` con el puerto ocupado NO se fija aca: es el ruling 7 de
        # Pedro (el plan propone que la vista no se niegue; el spec dice "se
        # niega" sin distinguir modos). Se agrega el aserto cuando lo decida.
        codigo, texto = _correr("--aplicar", "--forzar")
        assert codigo == 0 and "--forzar: sigo" in texto
        assert "global: 4 episodios reindexados" in texto
    finally:
        escucha.close()


def test_un_home_sin_ambitos_lo_dice(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    codigo, texto = _correr("--vista")
    assert codigo == 1 and "ningun ambito" in texto


def test_un_directorio_chroma_sin_la_coleccion_se_salta(home):
    d = home / "projects" / "otro" / "chroma"
    chromadb.PersistentClient(path=str(d))          # crea el sqlite, sin coleccion
    codigo, texto = _correr("--vista")
    assert codigo == 0 and "projects/otro: sin coleccion episodic (se salta)" in texto


def test_un_episodio_con_metadatos_raros_se_salta_y_se_cuenta(tmp_path, monkeypatch):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    monkeypatch.setenv("CALIPSO_PORT", "1")
    col = _sembrar(tmp_path / "global" / "chroma", [])
    col.add(ids=["r1"], documents=[CHAT_DATO], embeddings=[[0.1, 0.2, 0.3]])   # sin meta
    r = mr.revisar(col)
    assert (r["episodios"], r["raros"], r["pendientes"]) == (1, 1, [])
    codigo, texto = _correr("--aplicar")
    assert codigo == 0 and "1 raros -> 0 por reindexar" in texto


def test_sobre_una_copia_del_fixture_real(tmp_path, monkeypatch):
    """El fixture del porton tal cual (funcion de embeddings persistida): la
    vista da los numeros del spec y aplicar deja 16/16 con procedencia."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("CALIPSO_PORT", "1")
    shutil.copytree(FIXTURE, tmp_path / "home")
    antes = _leer(tmp_path / "home" / "global" / "chroma")
    codigo, texto = _correr("--vista")
    assert codigo == 0
    assert ("global: 16 episodios, 0 con procedencia, 16 parsean como chat, "
            "0 kind=chat que NO parsean, 0 no chat, 5 sin_dato, 0 basura, 0 raros "
            "-> 16 por reindexar") in texto
    assert "projects/var-home-pedro-calipso: 0 episodios" in texto
    codigo, texto = _correr("--aplicar")
    assert codigo == 0 and "global: 16 episodios reindexados; count 16 -> 16" in texto
    despues = _leer(tmp_path / "home" / "global" / "chroma")
    assert (despues["ids"], despues["docs"], despues["emb"]) == (antes["ids"], antes["docs"], antes["emb"])
    assert all(m["procedencia"] == 1 and m["ruta"] == "local" and m["route"] == "local"
               for m in despues["metas"])
    assert "global: nada que escribir" in _correr("--aplicar")[1]
```

- [ ] **Step 2: Verlos fallar**

Run: `.venv/bin/python -m pytest -q test_memoria_reindex.py 2>&1 | tail -3`
Expected: error de coleccion, `ModuleNotFoundError: No module named 'calipso.memoria_reindex'`.

- [ ] **Step 3: `calipso/memoria_reindex.py` completo**

```python
"""El reindexado de la memoria episodica con procedencia (spec 2026-09-11,
seccion 3): un solo tiro sobre el home, con el server apagado, que agrega a
cada episodio VIEJO que parsea como par de chat los metadatos que lo nuevo ya
trae (`procedencia=1`, `ruta` = la `route` decidida, unica disponible),
conservando id, documento, embedding y cantidad.

    python -m calipso.memoria_reindex --vista      # cuenta, no escribe
    python -m calipso.memoria_reindex --aplicar    # escribe (merge, idempotente)
    python -m calipso.memoria_reindex --aplicar --forzar   # con el server prendido

Abre cada ambito por directorio (`global/chroma` y `projects/*/chroma` bajo
CALIPSO_HOME) con `chromadb.PersistentClient` + `get_collection("episodic",
embedding_function=None)`, NO via `memory.Scope` (exige la funcion de
embeddings y hace mkdir de un core_dir que aca no se conoce). Verificado en
chromadb 1.5.9: `update(ids, metadatas)` sin `documents` MERGEA metadatos,
un `None` BORRA la clave (por eso los nuevos se arman sin None), y no toca
documento, id ni embedding. PERO ese `update` reconstruye la funcion de
embeddings persistida en el schema de la coleccion (SentenceTransformer)
aunque no embeba nada, y cargarla sale a huggingface.co salvo que el hub
este en modo offline: por eso las dos variables de abajo se fijan ANTES de
importar chromadb (`setdefault`: un `HF_HUB_OFFLINE=0` explicito de Pedro
manda). Eso protege la corrida por CLI (proceso limpio: el acto de Pedro) y
el archivo de tests corrido en aislado; dentro de la suite entera llega
tarde (calipso.server ya construyo Memory() con el hub online al importar,
conducta de main) y el test del fixture real no sale a la red porque
reutiliza el modelo ya cargado en el proceso. Sin red, sin aduana: este
proceso no es el server.

`--vista` solo hace `get` y `count`: no carga el modelo. Que la vista se
niegue o no con el server prendido es el ruling 7 del plan (Pedro); hasta
entonces solo `--aplicar` chequea el puerto.
"""
from __future__ import annotations

import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import argparse  # noqa: E402
import pathlib  # noqa: E402
import socket  # noqa: E402
import sys  # noqa: E402

import chromadb  # noqa: E402
from chromadb.errors import NotFoundError  # noqa: E402

from calipso import memoria_procedencia as mp  # noqa: E402

COLECCION = "episodic"
LOTE = 100


def home() -> pathlib.Path:
    """Resuelto por llamada, no congelado al importar (test_aislacion_home):
    el script se corre con `export CALIPSO_HOME=...` o sobre el real."""
    return pathlib.Path(os.environ.get("CALIPSO_HOME",
                                       os.path.expanduser("~/.calipso")))


def puerto() -> int:
    """El del lanzador (launch_calipso.py): CALIPSO_PORT, default 8000."""
    try:
        return int(os.environ.get("CALIPSO_PORT", "8000"))
    except (TypeError, ValueError):
        return 8000


def ambitos(base: pathlib.Path) -> list[tuple[str, pathlib.Path]]:
    """(nombre, directorio chroma) de cada ambito que EXISTE: `global` y cada
    `projects/<slug>`. Solo los que ya tienen `chroma.sqlite3`: abrir un
    PersistentClient sobre un directorio vacio lo crea, y el reindex no
    crea nada. Los departamentos (memoria/departamento/*) no entran: el spec
    los deja afuera."""
    salida = []
    g = base / "global" / "chroma"
    if (g / "chroma.sqlite3").exists():
        salida.append(("global", g))
    proyectos = base / "projects"
    if proyectos.is_dir():
        for d in sorted(proyectos.iterdir()):
            c = d / "chroma"
            if (c / "chroma.sqlite3").exists():
                salida.append((f"projects/{d.name}", c))
    return salida


def _server_prendido(port: int, host: str = "127.0.0.1") -> bool:
    """Loopback: pregunta si algo escucha en el puerto del server. Es por
    completitud del recorrido (un server vivo sigue escribiendo episodios),
    no por integridad: dos PersistentClient sobre el mismo directorio no
    corrompen nada (sondeado)."""
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def abrir(chroma_dir: pathlib.Path):
    """La coleccion, o None si el directorio no la tiene."""
    cliente = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        return cliente.get_collection(COLECCION, embedding_function=None)
    except NotFoundError:
        return None


def revisar(col) -> dict:
    """Lee todo y clasifica sin escribir. `pendientes` son los (id, meta
    nueva) que `aplicar` escribiria: pares de chat (kind 'chat' o sin kind)
    sin `procedencia` todavia, con `{**meta, procedencia: 1, ruta: route}`
    sin ningun None."""
    datos = col.get(include=["documents", "metadatas"])
    r = {"episodios": 0, "con_procedencia": 0, "parsean": 0,
         "chat_no_parsean": 0, "no_chat": 0, "sin_dato": 0, "basura": 0,
         "raros": 0, "pendientes": []}
    for id_, doc, meta in zip(datos["ids"], datos["documents"], datos["metadatas"]):
        r["episodios"] += 1
        if not isinstance(meta, dict) or not isinstance(doc, str):
            r["raros"] += 1          # se salta y se cuenta, jamas se pisa
            continue
        kind = meta.get("kind")
        es_chat = kind in (None, "chat")
        par = mp.partir(doc)
        if meta.get("procedencia") == 1:
            r["con_procedencia"] += 1
        if not es_chat:
            r["no_chat"] += 1
            continue
        if par is None:
            if kind == "chat":
                r["chat_no_parsean"] += 1
            else:
                r["no_chat"] += 1    # sin kind y sin forma de par: no es un chat
            continue
        r["parsean"] += 1
        pregunta, respuesta = par
        if not mp.limpiar_gestos(pregunta):
            r["basura"] += 1
        elif mp.clasificar(respuesta) == "sin_dato":
            r["sin_dato"] += 1
        if meta.get("procedencia") == 1:
            continue                 # ya reindexado: idempotencia
        nuevos = {"procedencia": 1}
        if meta.get("route"):
            nuevos["ruta"] = meta["route"]
        r["pendientes"].append((id_, {**meta, **nuevos}))
    return r


def aplicar(col, revision: dict) -> int:
    """Escribe los pendientes por lotes con `update(ids, metadatas)` -- sin
    `documents`, para no re-embeber. Devuelve cuantos escribio."""
    pendientes = revision["pendientes"]
    for i in range(0, len(pendientes), LOTE):
        lote = pendientes[i:i + LOTE]
        col.update(ids=[p[0] for p in lote], metadatas=[p[1] for p in lote])
    return len(pendientes)


def _linea(nombre: str, r: dict) -> str:
    return (f"{nombre}: {r['episodios']} episodios, {r['con_procedencia']} con "
            f"procedencia, {r['parsean']} parsean como chat, "
            f"{r['chat_no_parsean']} kind=chat que NO parsean, {r['no_chat']} no chat, "
            f"{r['sin_dato']} sin_dato, {r['basura']} basura, {r['raros']} raros "
            f"-> {len(r['pendientes'])} por reindexar")


def main(argv: list[str] | None = None, salida=None) -> int:
    salida = salida or sys.stdout
    ap = argparse.ArgumentParser(prog="python -m calipso.memoria_reindex",
                                 description=__doc__.split("\n\n")[0])
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--vista", action="store_true", help="contar, no escribir")
    modo.add_argument("--aplicar", action="store_true", help="escribir los metadatos")
    ap.add_argument("--forzar", action="store_true",
                    help="aplicar aunque el server responda en CALIPSO_PORT")
    args = ap.parse_args(argv)
    base = home()
    print(f"home: {base}", file=salida)
    if args.aplicar and _server_prendido(puerto()):
        if not args.forzar:
            print(f"el server responde en el puerto {puerto()}: apagalo (o --forzar). "
                  "No es por integridad -- dos clientes no corrompen el chroma -- "
                  "sino para que el recorrido sea completo: un server vivo sigue "
                  "escribiendo episodios.", file=salida)
            return 2
        print(f"el server responde en el puerto {puerto()}; --forzar: sigo", file=salida)
    lista = ambitos(base)
    if not lista:
        print("ningun ambito con chroma bajo el home", file=salida)
        return 1
    for nombre, chroma_dir in lista:
        col = abrir(chroma_dir)
        if col is None:
            print(f"{nombre}: sin coleccion {COLECCION} (se salta)", file=salida)
            continue
        r = revisar(col)
        print(_linea(nombre, r), file=salida)
        if not args.aplicar:
            continue
        if not r["pendientes"]:
            print(f"{nombre}: nada que escribir (ya reindexado o sin pares de chat)", file=salida)
            continue
        n = aplicar(col, r)
        despues = col.count()
        print(f"{nombre}: {n} episodios reindexados; count {r['episodios']} -> {despues}"
              + ("" if despues == r["episodios"] else "  OJO: la cantidad cambio durante la corrida"),
              file=salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: La excepcion del canario**

`socket.create_connection` es una de las llamadas que `test_aduana_canario.py` marca en todo `calipso/**` (`_es_salida`, `:113`); sin la linea, `test_toda_salida_del_proceso_cruza_o_se_declara` cae con `calipso/memoria_reindex.py:87  _server_prendido  socket.create_connection((host, port), timeout=0.4)`. `test_aduana_canario.py:51-53`, ANTES:

```python
    "launch_calipso.py:_port_open": "loopback: el lanzador espera al propio server",
    "launch_calipso.py:_wait_ready": "loopback: idem",
    "launch_calipso.py:main": "local: lanza uvicorn/el navegador, no sale a internet",
```

DESPUES:

```python
    "launch_calipso.py:_port_open": "loopback: el lanzador espera al propio server",
    "launch_calipso.py:_wait_ready": "loopback: idem",
    "launch_calipso.py:main": "local: lanza uvicorn/el navegador, no sale a internet",
    "calipso/memoria_reindex.py:_server_prendido": "loopback: el reindex (acto de Pedro, fuera del server) pregunta si el server escucha en CALIPSO_PORT antes de recorrer el chroma; no sale de la maquina",
```

- [ ] **Step 5: Verde y suite**

```bash
.venv/bin/python -m pytest -q test_memoria_reindex.py test_aduana_canario.py test_aislacion_home.py 2>&1 | tail -1   # 9 + 12 + 4 passed (~6 s: la copia del fixture carga el modelo del cache)
export CALIPSO_HOME=$(mktemp -d) && .venv/bin/python -m calipso.memoria_reindex --vista; echo "exit=$?"   # "ningun ambito con chroma bajo el home", exit=1
.venv/bin/python -m pytest -q --ignore=test_chat_live.py 2>&1 | tail -1; echo EXIT=$?   # base + 45, 0 failed
```

OJO con el segundo comando: `python -m calipso.memoria_reindex` SIN `CALIPSO_HOME` exportado resuelve `~/.calipso`. Con `--vista` no escribe, pero la regla es no abrir el home real desde una sesion de agente: siempre con la variable.

- [ ] **Step 6: Commit**

```bash
git add calipso/memoria_reindex.py test_memoria_reindex.py test_aduana_canario.py
git commit -m "feat(memoria): memoria_reindex -- el acto de Pedro sobre lo viejo: abre cada ambito por directorio (global y projects/*), lee con get, y a cada par de chat sin procedencia le mergea procedencia=1 y ruta=route con update sin documents (id, documento, embedding y cantidad intactos; idempotente; sin None); --vista cuenta sin escribir (los kind=chat que no parsean, los sin_dato, la basura, los raros), --aplicar se niega con el server en CALIPSO_PORT salvo --forzar, offline por construccion (HF_HUB_OFFLINE antes de chromadb); tests sobre homes sin modelo y sobre la copia del fixture; excepcion loopback en el canario"
```

---

### Task 5: El porton en vivo (antes / A / B), el aterrizaje de la variante, el smoke y el cierre de rama

**Files:**
- Create: `experimentos/porton_memoria.py`
- Create: `experimentos/porton_memoria_resultados.md`, `experimentos/porton_memoria_resultados.jsonl` (los escribe el porton)
- Create: `docs/superpowers/2026-09-11-cierre-memoria-procedencia.md`
- Modify: `calipso/memoria_procedencia.py` (`VARIANTE_DEFAULT`) y `test_memoria_procedencia.py` (la linea que lo fija) SOLO si gana B
- Modify: `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md` (adenda, seccion 9)
- Test: la suite entera; el porton y el smoke son en vivo

**Interfaces:**
- Consumes: el server desechable (`uvicorn calipso.server:app`, `CALIPSO_NO_TOTP` en `server.py:858`, `CALIPSO_TOKEN` en `_load_token` `:208`), `POST /api/chats` (`:1974`) y `POST /api/chats/{chat_id}/activate` (`:1992`), el ws `/ws/chat` con cookie `calipso_token` y paquete `{"text", "chat_id"}` (eventos `chunk`, `meta` con `route`/`model`, `abismo` con `fase`/`fuente`/`tamano`/`motivo`, `done`, `error`); Ollama real en 11434 con `qwen2.5:7b`; `websockets` 16.0 del .venv; `memoria_procedencia.clasificar` y `variante_activa()` (leida por llamada en cada turno del server hijo, que hereda `MEMORIA_PRESENTAR`).
- Produces: `clasificar_turno(clave, texto, clasificar) -> "dato" | "sin_dato" | "confabula"`, `hay_eco(texto) -> bool`, `restaurar_home() -> Path`, `Server(home, variante)` con `esperar()` / `apagar()`, `chat_nuevo(token, titulo) -> id`, `turno(token, mensaje) -> {chat, ruta, abismo, ms, texto}`, `correr(condiciones, n, clasificar) -> filas`, `resumen(filas) -> str`, `main(argv)`; `PREGUNTAS`, `CONDICIONES = {"antes": "off", "A": "A", "B": "B"}`, `PUERTO = 8776`.

- [ ] **Step 1: `experimentos/porton_memoria.py` completo**

```python
"""El porton en vivo de la memoria con procedencia (spec 2026-09-11, seccion
5): sobre el fixture restaurado, las 4 preguntas de memoria/chats del smoke,
chat nuevo por turno, N pasadas, tres condiciones -- `antes` (los lectores
pegan el par crudo, MEMORIA_PRESENTAR=off), `A` (frase fija) y `B` (sin el
renglon de Calipso en el no-saber). Cada turno se clasifica con UNA clase
determinista (`dato` / `sin_dato` / `confabula`) y dos flags (`consulto`,
`eco`). Escribe experimentos/porton_memoria_resultados.{jsonl,md}.

    .venv/bin/python experimentos/porton_memoria.py            # N=2, las 3 condiciones
    .venv/bin/python experimentos/porton_memoria.py --n 1 --condiciones A,B

Levanta un server DESECHABLE por condicion y por pasada (uvicorn
calipso.server:app en 127.0.0.1:8776, CALIPSO_HOME temporal restaurado
desde experimentos/fixtures/memoria_smoke_home, token aleatorio,
CALIPSO_NO_TOTP=1), con Ollama real (qwen2.5:7b). Jamas el server real, el
puerto 8000 ni ~/.calipso: este script no importa calipso; solo habla HTTP
y ws con el desechable.

La condicion `antes` reproduce los dos LECTORES de main (MEMORIA_PRESENTAR=
off: `- (score) texto` en el system, `- texto` en el abismo), pero el
ESCRITOR es el de esta rama (pregunta limpia, metadatos con procedencia):
desviacion declarada (decision 8 del plan), acotada a los turnos 2-4 de
una misma pasada, que pueden recuperar el episodio del turno 1 con un
embedding distinto del que main habria guardado. El baseline exacto seria
un server desde main en un worktree (ruling 11, si Pedro lo pide).
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import pathlib
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = RAIZ / "experimentos" / "fixtures" / "memoria_smoke_home"
SALIDA_JSONL = RAIZ / "experimentos" / "porton_memoria_resultados.jsonl"
SALIDA_MD = RAIZ / "experimentos" / "porton_memoria_resultados.md"
PUERTO = 8776
BASE = f"http://127.0.0.1:{PUERTO}"
WS = f"ws://127.0.0.1:{PUERTO}/ws/chat"
OLLAMA = "http://127.0.0.1:11434"
MODELO = "qwen2.5:7b"

# las 4 preguntas de memoria/chats del smoke (lineas 1-4 de sus mensajes) y
# la verdad sembrada en chats.json del fixture que las contesta
PREGUNTAS = [
    ("libro", "/local hola, que libro te conte que empece?",
     ("nombre de la rosa",)),
    ("libro_rosa", "/local che, quien me presto el libro rosa? no me acuerdo",
     ("mariana quintero",)),
    ("presupuesto", "/local en que quedamos la otra vez con el presupuesto del taller?",
     ("120", "octubre")),
    ("mariana", "/local retoma lo que dejamos sobre mariana, la charla de agosto",
     ("mariana", "libro")),
]
CONDICIONES = {"antes": "off", "A": "A", "B": "B"}


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c)).lower()


def clasificar_turno(clave: str, texto: str, clasificar) -> str:
    """`dato` si la respuesta contiene la verdad sembrada (TODAS las palabras
    de la tupla: 'mariana' y 'libro'; para el presupuesto basta '120' u
    'octubre'), `sin_dato` si `clasificar` lo dice, `confabula` si ni una
    ni otra."""
    low = _sin_acentos(texto)
    verdades = dict((c, v) for c, _, v in PREGUNTAS)[clave]
    if clave == "presupuesto":
        tiene = any(v in low for v in verdades)
    else:
        tiene = all(v in low for v in verdades)
    if tiene:
        return "dato"
    if clasificar(texto) == "sin_dato":
        return "sin_dato"
    return "confabula"


def hay_eco(texto: str) -> bool:
    return "no tenia el dato" in _sin_acentos(texto)


# --- el server desechable ----------------------------------------------------

def _http(metodo: str, ruta: str, cuerpo: dict | None, token: str, timeout=30):
    req = urllib.request.Request(
        f"{BASE}{ruta}", data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
        headers={"Cookie": f"calipso_token={token}", "Content-Type": "application/json"},
        method=metodo)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _ollama_listo() -> None:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5) as r:
            nombres = [m.get("name") for m in json.loads(r.read()).get("models", [])]
    except Exception as e:
        sys.exit(f"Ollama no responde en {OLLAMA}: {e}")
    if MODELO not in nombres:
        sys.exit(f"Ollama no tiene {MODELO}: {nombres}")


def _puerto_libre() -> None:
    try:
        with socket.create_connection(("127.0.0.1", PUERTO), timeout=1):
            pass
    except OSError:
        return
    sys.exit(f"algo ya escucha en {BASE}: no levanto otro server ahi")


def restaurar_home() -> pathlib.Path:
    """Un CALIPSO_HOME nuevo con el fixture adentro (chroma + chats.json +
    core, sin token) y un catastro.json minimo para que el server no
    escanee el disco de la maquina en el primer turno."""
    home = pathlib.Path(tempfile.mkdtemp(prefix="porton-memoria-"))
    shutil.copytree(FIXTURE, home, dirs_exist_ok=True)
    (home / "README.md").unlink(missing_ok=True)
    (home / "catastro.json").write_text(
        json.dumps({"raices": [], "proyectos": []}), encoding="utf-8")
    return home


class Server:
    def __init__(self, home: pathlib.Path, variante: str):
        self.home = home
        self.token = secrets.token_urlsafe(24)
        env = {**os.environ, "CALIPSO_HOME": str(home), "CALIPSO_TOKEN": self.token,
               "CALIPSO_NO_TOTP": "1", "MEMORIA_PRESENTAR": variante}
        self.log = open(home / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "calipso.server:app",
             "--host", "127.0.0.1", "--port", str(PUERTO)],
            cwd=str(RAIZ), env=env, stdout=self.log, stderr=subprocess.STDOUT)

    def esperar(self, segundos: int = 120) -> None:
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            if self.proc.poll() is not None:
                sys.exit(f"el server murio al arrancar: ver {self.home}/server.log")
            try:
                with urllib.request.urlopen(f"{BASE}/login", timeout=2) as r:
                    if r.status == 200:
                        return
            except Exception:
                pass
            time.sleep(1)
        sys.exit(f"el server no levanto en {segundos} s: ver {self.home}/server.log")

    def apagar(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.log.close()


# --- un turno ----------------------------------------------------------------

def chat_nuevo(token: str, titulo: str) -> str:
    cid = _http("POST", "/api/chats", {"title": titulo}, token)["id"]
    _http("POST", f"/api/chats/{cid}/activate", {}, token)
    return cid


async def turno(token: str, mensaje: str) -> dict:
    import websockets   # en el .venv (lo usa test_chat_live.py)
    cid = chat_nuevo(token, f"porton {mensaje[:24]}")
    t0 = time.monotonic()
    eventos, texto, ruta = [], [], None
    async with websockets.connect(WS, additional_headers={"Cookie": f"calipso_token={token}"},
                                  max_size=None) as ws:
        await ws.send(json.dumps({"text": mensaje, "chat_id": cid}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=900)
            try:
                pkt = json.loads(raw)
            except Exception:
                continue
            t = pkt.get("type", "")
            if t == "chunk":
                texto.append(pkt.get("text", ""))
            elif t == "meta":
                ruta = f"{pkt.get('route')}/{pkt.get('model')}"
            elif t == "abismo":
                eventos.append({k: pkt.get(k) for k in ("fase", "fuente", "tamano", "motivo")})
            elif t == "done":
                break
            elif t == "error":
                eventos.append({"error": pkt.get("text")})
                break
    return {"chat": cid, "ruta": ruta, "abismo": eventos,
            "ms": int((time.monotonic() - t0) * 1000), "texto": "".join(texto)}


# --- el porton ---------------------------------------------------------------

def correr(condiciones: list[str], n: int, clasificar) -> list[dict]:
    filas = []
    for condicion in condiciones:
        for pasada in range(1, n + 1):
            home = restaurar_home()
            server = Server(home, CONDICIONES[condicion])
            print(f"[{condicion} pasada {pasada}] server en {BASE}, home {home}", flush=True)
            try:
                server.esperar()
                for clave, mensaje, _ in PREGUNTAS:
                    r = asyncio.run(turno(server.token, mensaje))
                    fila = {"condicion": condicion, "pasada": pasada, "pregunta": clave,
                            "mensaje": mensaje, "clase": clasificar_turno(clave, r["texto"], clasificar),
                            "consulto": any(e.get("fase") for e in r["abismo"]),
                            "eco": hay_eco(r["texto"]), **r,
                            "ts": datetime.datetime.now().isoformat(timespec="seconds")}
                    filas.append(fila)
                    with SALIDA_JSONL.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(fila, ensure_ascii=False) + "\n")
                    print(f"   {clave:12} {fila['clase']:9} consulto={fila['consulto']!s:5} "
                          f"eco={fila['eco']!s:5} {fila['ms']:6} ms :: {r['texto'][:90]!r}", flush=True)
            finally:
                server.apagar()
    return filas


def resumen(filas: list[dict]) -> str:
    """El informe: totales por condicion y la tabla de cada turno."""
    lineas = ["# Porton de la memoria con procedencia -- resultados",
              "",
              f"Corrido el {datetime.datetime.now().isoformat(timespec='minutes')} sobre el fixture "
              f"`experimentos/fixtures/memoria_smoke_home`, chat nuevo por turno, server desechable en "
              f"{BASE}, {MODELO}. Clases: `dato` (la respuesta trae la verdad sembrada), `sin_dato` "
              "(`clasificar` lo dice), `confabula` (ni una ni otra). Flags: `consulto` (evento "
              "`abismo` en el ws), `eco` (la respuesta contiene 'no tenia el dato').",
              "",
              "## Totales por condicion",
              "",
              "| condicion | turnos | dato | sin_dato | confabula | consulto | eco |",
              "|---|---|---|---|---|---|---|"]
    for condicion in dict.fromkeys(f["condicion"] for f in filas):
        de = [f for f in filas if f["condicion"] == condicion]
        cuenta = lambda k, v: sum(1 for f in de if f[k] == v)   # noqa: E731
        lineas.append(f"| {condicion} | {len(de)} | {cuenta('clase', 'dato')} | "
                      f"{cuenta('clase', 'sin_dato')} | {cuenta('clase', 'confabula')} | "
                      f"{cuenta('consulto', True)} | {cuenta('eco', True)} |")
    lineas += ["", "## Cada turno", "",
               "| condicion | pasada | pregunta | clase | consulto | eco | ms | respuesta (200 chars) |",
               "|---|---|---|---|---|---|---|---|"]
    for f in filas:
        resp = " ".join(f["texto"].split())[:200].replace("|", "/")
        lineas.append(f"| {f['condicion']} | {f['pasada']} | {f['pregunta']} | {f['clase']} | "
                      f"{'si' if f['consulto'] else 'no'} | {'si' if f['eco'] else 'no'} | "
                      f"{f['ms']} | {resp} |")
    eco_a = sum(1 for f in filas if f["condicion"] == "A" and f["eco"])
    eco_b = sum(1 for f in filas if f["condicion"] == "B" and f["eco"])
    hay_b = any(f["condicion"] == "B" for f in filas)
    lineas += ["", "## Aterrizaje (regla del spec, seccion 5)", ""]
    if hay_b and eco_a and not eco_b:
        lineas.append("A muestra eco y B no: se aterriza **B** (`VARIANTE_DEFAULT = \"B\"`).")
    else:
        lineas.append("Se aterriza **A** (la frase fija): "
                      + ("B no corrio." if not hay_b else f"eco en A = {eco_a}, en B = {eco_b}."))
    return "\n".join(lineas) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--n", type=int, default=2, help="pasadas por condicion (default 2)")
    ap.add_argument("--condiciones", default="antes,A,B",
                    help="lista separada por comas entre antes, A y B")
    args = ap.parse_args(argv)
    condiciones = [c.strip() for c in args.condiciones.split(",") if c.strip()]
    for c in condiciones:
        if c not in CONDICIONES:
            sys.exit(f"condicion desconocida: {c}")
    if not FIXTURE.is_dir():
        sys.exit(f"falta el fixture {FIXTURE}")
    # el clasificador es el del paquete, importado aca y no arriba: este
    # script no necesita CALIPSO_HOME (memoria_procedencia no toca el home)
    sys.path.insert(0, str(RAIZ))
    from calipso.memoria_procedencia import clasificar
    _ollama_listo()
    _puerto_libre()
    SALIDA_JSONL.unlink(missing_ok=True)
    filas = correr(condiciones, args.n, clasificar)
    SALIDA_MD.write_text(resumen(filas), encoding="utf-8")
    print(f"\ninforme: {SALIDA_MD}\n")
    print(resumen(filas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Chequeo sin server (las partes puras): `cd /var/home/pedro/calipso && .venv/bin/python -c "import sys; sys.path.insert(0, '.'); from experimentos import porton_memoria as pm; from calipso.memoria_procedencia import clasificar; print(pm.clasificar_turno('libro', 'Empezaste El Nombre de la Rosa.', clasificar), pm.clasificar_turno('libro', 'No tengo registros de eso.', clasificar), pm.clasificar_turno('libro', 'Recuerdo que te conte sobre 1984.', clasificar), pm.hay_eco('Calipso no tenía el dato entonces'))"` -> `dato sin_dato confabula True`.

- [ ] **Step 2: Correr el porton**

Jamas el server real ni el puerto 8000 ni `~/.calipso`. Antes: Ollama prendido con `qwen2.5:7b` (`curl -s http://127.0.0.1:11434/api/tags | jq '.models[].name'`), nada en el 8776, y la huella del home real para comparar al final:

```bash
cd /var/home/pedro/calipso
ls -laR --time-style=full-iso ~/.calipso | md5sum > /tmp/huella_antes_porton.txt
.venv/bin/python experimentos/porton_memoria.py                # N=2, antes,A,B: 6 servers, 24 turnos
```

Tarda lo que tarde el 7b (el smoke del 09-10 dio 10-60 s por turno de memoria; ninguna de las 4 preguntas es la del orquestador): del orden de 15-30 minutos. Cada turno imprime clase, `consulto`, `eco` y los primeros 90 chars; el JSONL crece turno a turno (si algo se cae a mitad, lo hecho queda). Al terminar imprime el informe y lo escribe en `experimentos/porton_memoria_resultados.md`. Despues: `ls -laR --time-style=full-iso ~/.calipso | md5sum` tiene que dar lo mismo que `/tmp/huella_antes_porton.txt`.

Lo que se lee del informe (spec seccion 5): por condicion, `sin_dato` y `eco`. Se espera que en A y en B `sin_dato` caiga (contra `antes`) y `eco` sea cero. Tres salidas posibles:

1. **A sin eco (y B tambien o B no mejor):** se aterriza A. `VARIANTE_DEFAULT` ya es `"A"`: no se toca codigo.
2. **A con eco y B sin eco:** se aterriza B (Step 3).
3. **Cualquier otra cosa** (eco en las dos; `sin_dato` que no baja; `confabula` que sube mucho en A/B contra `antes`): NO se aterriza nada por cuenta propia. Se escribe el informe con los numeros y se para: ruling 6.

- [ ] **Step 3: Aterrizar B (solo si gano B)**

`calipso/memoria_procedencia.py`, ANTES:

```python
VARIANTE_DEFAULT = "A"
```

DESPUES:

```python
VARIANTE_DEFAULT = "B"   # el porton del 2026-09-11: A mostro eco y B no (experimentos/porton_memoria_resultados.md)
```

Y en `test_memoria_procedencia.py`, `test_la_variante_activa_sale_del_entorno_y_sin_variable_es_la_default`, ANTES: `assert mp.variante_activa() == mp.VARIANTE_DEFAULT == "A"` -> DESPUES: `assert mp.variante_activa() == mp.VARIANTE_DEFAULT == "B"`. Nada mas cambia: `presentar` ya implementa B y `test_la_variante_b_omite_el_renglon_de_calipso_en_el_no_saber` la fija.

- [ ] **Step 4: El smoke -- la escritura real y el reindex sobre un home que un server real escribio**

El porton ya ejercito la LECTURA en vivo (las tres condiciones). Falta ver, con chroma y server reales, que lo que el turno ESCRIBE es lo del spec y que el reindex lo respeta. Con la variante aterrizada (sin `MEMORIA_PRESENTAR`), un server desechable nuevo sobre el fixture restaurado y un solo turno:

```bash
cd /var/home/pedro/calipso
export CALIPSO_HOME=$(mktemp -d /tmp/memoria-smoke-XXXX) && cp -r experimentos/fixtures/memoria_smoke_home/. $CALIPSO_HOME && rm $CALIPSO_HOME/README.md
echo '{"raices": [], "proyectos": []}' > $CALIPSO_HOME/catastro.json
export CALIPSO_TOKEN=$(.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(24))") CALIPSO_NO_TOTP=1
.venv/bin/python -m uvicorn calipso.server:app --host 127.0.0.1 --port 8776 > $CALIPSO_HOME/server.log 2>&1 &
for i in $(seq 1 60); do curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8776/login | grep -q 200 && break; sleep 1; done
CID=$(curl -s -b "calipso_token=$CALIPSO_TOKEN" -H 'Content-Type: application/json' -d '{"title":"smoke"}' http://127.0.0.1:8776/api/chats | jq -r .id)
curl -s -b "calipso_token=$CALIPSO_TOKEN" -X POST -d '{}' http://127.0.0.1:8776/api/chats/$CID/activate > /dev/null
.venv/bin/python - <<EOF2
import asyncio, json, os, websockets
async def main():
    async with websockets.connect("ws://127.0.0.1:8776/ws/chat", additional_headers={"Cookie": f"calipso_token={os.environ['CALIPSO_TOKEN']}"}, max_size=None) as ws:
        await ws.send(json.dumps({"text": "/local che, quien me presto el libro rosa? no me acuerdo", "chat_id": "$CID"}))
        while True:
            p = json.loads(await ws.recv())
            if p.get("type") in ("done", "error"): break
asyncio.run(main())
EOF2
kill %1; sleep 2
```

Pasa/no pasa, con salida en el informe:

1. **El episodio nuevo lleva la pregunta limpia y la procedencia.** `HF_HUB_OFFLINE=1 .venv/bin/python -c "import chromadb, os; c = chromadb.PersistentClient(path=os.environ['CALIPSO_HOME'] + '/global/chroma').get_collection('episodic', embedding_function=None); g = c.get(include=['documents', 'metadatas']); n = [(d, m) for d, m in zip(g['documents'], g['metadatas']) if m.get('procedencia') == 1]; print(c.count(), len(n)); print(n[0][1]); print(n[0][0][:120])"` -> `17 1`; el meta con `ruta: local`, `route: local`, `modelo: qwen2.5:7b`, `chat: <CID>`, `kind: chat`, `procedencia: 1`, `ts`; el documento arranca con `Pedro pregunto: che, quien me presto el libro rosa? no me acuerdo\nCalipso respondio:` (sin `/local`).
2. **El reindex sobre ese home.** `.venv/bin/python -m calipso.memoria_reindex --vista` -> `global: 17 episodios, 1 con procedencia, 17 parsean como chat, 0 kind=chat que NO parsean, 0 no chat, <5 o 6> sin_dato, 0 basura, 0 raros -> 16 por reindexar` y `projects/var-home-pedro-calipso: 0 episodios ... -> 0 por reindexar`. Con el server ya apagado, `.venv/bin/python -m calipso.memoria_reindex --aplicar` -> `global: 16 episodios reindexados; count 17 -> 17`; `--vista` de nuevo -> `17 con procedencia -> 0 por reindexar`; `--aplicar` de nuevo -> `global: nada que escribir`. Y con el server PRENDIDO (levantarlo otra vez en 8776 y `CALIPSO_PORT=8776`): `--aplicar` -> `el server responde en el puerto 8776: apagalo (o --forzar)`, exit 2; `--vista` con el server prendido hace lo que Pedro haya decidido en el ruling 7 (sin ruling: sigue contando, que es lo que el plan propone).
3. **Lo presentado en un turno real.** En `$CALIPSO_HOME/server.log` no se ve el system; se mira por el camino del codigo: `.venv/bin/python -c "import calipso.server as srv; print(srv._build_context('quien me presto el libro rosa?', 'runtime', {'type': 'chat'}).split('=== Recuerdos relevantes ===')[1].split('===')[0])"` (con `CALIPSO_HOME` apuntando a ese home y el server apagado; carga el modelo, ~7 s) -> vinetas `- Pedro dijo (2026-09-10): ...` / `  Calipso no tenia el dato entonces (local, 2026-09-10).` (o, si gano B, solo la linea de Pedro), ninguna `Pedro pregunto:`, ninguna `/local`.
4. **El home real intacto:** `ls -laR --time-style=full-iso ~/.calipso | md5sum` igual a `/tmp/huella_antes_porton.txt`.

- [ ] **Step 5: El informe del cierre y el estado**

`docs/superpowers/2026-09-11-cierre-memoria-procedencia.md`: la tabla del porton por condicion (turnos, dato, sin_dato, confabula, consulto, eco) copiada de `experimentos/porton_memoria_resultados.md`, la variante aterrizada y por que, los 4 pasos del smoke con su salida y PASA / NO PASA, el banco (26/27, 0 falsos) y lo que queda para Pedro:

- **El reindex del home real (decision 3 del spec, acto de Pedro):** con el server apagado, desde la raiz del repo, `.venv/bin/python -m calipso.memoria_reindex --vista` (mira los numeros: los `kind=chat que NO parsean` deberian ser 0; los ambitos de proyecto traen lo de junio-agosto con acentos rotos, que `partir` entiende), y si cierran, `.venv/bin/python -m calipso.memoria_reindex --aplicar`. Sin `CALIPSO_HOME` exportado va al `~/.calipso` real: es lo que se quiere ESA vez. Segunda corrida: `nada que escribir`. El server puede volver a arrancar en cualquier momento (dos clientes no corrompen nada; el chequeo del puerto es por completitud del recorrido).
- Los departamentos (`memoria/departamento/*/chroma`) no se reindexan (spec).
- `reflect`/`recent` siguen leyendo el documento crudo (fuera del alcance, spec seccion 6).

Adenda en `docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md` (seccion 9, `:229-257`: una lista de items con negrita; se agrega UN item al final, con este texto y solo lo que esta entre `<>` sale del porton y del smoke):

```markdown
- **Memoria con procedencia (2026-09-11):** lo que dijo Calipso es contexto, no evidencia. Rama
  `feat/memoria-procedencia` mergeada. Guardar todo, decidir al leer: los dos lectores (system del turno y
  fuente `memoria` del abismo) presentan cada episodio como `Pedro dijo (fecha): ...` / `Calipso contesto
  (ruta, fecha): ...`, el no-saber se degrada al leer con patrones fijos medidos contra un banco de 51
  respuestas reales (`experimentos/no_saber_banco.py`, 0 falsos, 26/27), el gesto solo se salta antes del
  corte; el `remember` del chat guarda la pregunta limpia y `ruta` usada / `modelo` / `chat` / `procedencia=1`.
  Variante aterrizada: <A|B> (porton `experimentos/porton_memoria_resultados.md`: antes / A / B sobre el fixture
  restaurado, N=2: sin_dato <antes -> A / B>, eco <A / B>). Spec
  `docs/superpowers/specs/2026-09-11-memoria-con-procedencia-design.md`; cierre
  `docs/superpowers/2026-09-11-cierre-memoria-procedencia.md`. **Pendiente de Pedro:** el reindex del home real,
  con el server apagado y desde la raiz del repo: `.venv/bin/python -m calipso.memoria_reindex --vista` y, si los
  numeros cierran, `--aplicar` (idempotente; `reflect`/`recent` y los departamentos quedan fuera, spec seccion 6).
```

Y la nota del dossier de memoria del proyecto (`~/.claude/projects/-var-home-pedro/memory/`, la del proyecto Calipso): una linea con lo mismo (rama mergeada, variante aterrizada, el reindex del home real pendiente de Pedro con el comando).

- [ ] **Step 6: Cierre**

```bash
.venv/bin/python -m pytest -q --ignore=test_chat_live.py 2>&1 | tail -1; echo EXIT=$?     # 0 failed
git add experimentos/porton_memoria.py experimentos/porton_memoria_resultados.md experimentos/porton_memoria_resultados.jsonl docs/superpowers/2026-09-11-cierre-memoria-procedencia.md docs/superpowers/2026-09-09-estado-del-proyecto-y-como-seguimos.md
# si gano B, tambien: git add calipso/memoria_procedencia.py test_memoria_procedencia.py
git commit -m "docs(memoria): el porton en vivo (antes / A / B sobre el fixture restaurado, chat nuevo por turno, N=2) y el smoke con server desechable -- <sin_dato y eco por condicion>; se aterriza <A|B>; el reindex del home real queda para Pedro"
git checkout main && git merge --no-ff feat/memoria-procedencia -m "merge: la memoria con procedencia -- lo que dijo Calipso es contexto, no evidencia (guardar todo, decidir al leer: Pedro dijo / Calipso contesto con ruta y fecha, el no-saber degradado por patrones medidos contra un banco real, el gesto solo saltado antes del corte, la pregunta limpia y la ruta usada en el episodio nuevo, el reindex por directorio para lo viejo, porton antes/A/B en vivo). 5 tasks; suite <N> + node 428"
# el push NO es condicion del merge: solo si hay red (esta sesion no pudo conectar a servicios externos;
# main ya esta 34 commits por delante de origin/main). Si falla, se anota en el informe y queda para Pedro.
git push || echo "sin red: el push queda para Pedro"
```

Sin reiniciar el server real y sin correr el reindex sobre `~/.calipso`: los dos son actos de Pedro (el reindex, con el server apagado, con los comandos del informe). Actualizar el dossier de memoria del proyecto (la nota de Calipso en `~/.claude/projects/-var-home-pedro/memory/`) con el estado.

---

## Self-review

### 1. Cobertura del spec, seccion por seccion -> task

| Spec | Requisito | Task |
|---|---|---|
| 1, decision 1 | guardar todo, decidir al leer: nada se filtra al escribir | 2 (el `remember` solo suma metadatos y limpia la pregunta), 1 (todo el juicio en `presentar`) |
| 1, decision 2 | procedencia + degradar el no-saber al leer, patrones fijos | 1, 3 |
| 1, decision 3 | reindexar lo viejo con un script, id y texto intactos, server apagado, lo corre Pedro | 4 (el script y los tests), 5 (los comandos para Pedro; nadie lo corre por el) |
| 2, el metadato | `ruta` = usada, `modelo`, `chat`, `procedencia=1`; `route` sigue siendo la decidida; pregunta LIMPIA; el par sigue siendo el documento; los rulings (sin titulo, sin modelo en el documento, sin pregunta/respuesta separadas) | 2 |
| 2, la presentacion | `presentar(texto, meta)` con las dos lineas, fecha `ts[:10]`, topes 200/400 con `...`, la frase fija; la usan los dos lectores; ANTES del corte; `Memory.recall` conserva el contrato; `reflect`/`recent` no cambian | 1, 3 |
| 2, el parser | `partir` con `^Pedro pregunt\S*:\s*(.*?)\nCalipso respondi\S*:\s*(.*)\Z` DOTALL; compartido por `presentar` y el reindex; gestos iniciales limpiados al mostrar; `ruta` de `meta["ruta"]` o `meta["route"]` | 1, 4 |
| 2, lo que no es un par | metas y fichas: `Registro (<kind o episodio>, <fecha>)`; nunca el crudo; el reindex las cuenta como no chat y no las toca | 1, 4 |
| 2, la clasificacion | pura, minusculas sin acentos, fuertes (degradan solos, regla de posicion 250), debiles (solo sin afirmativa con contenido antes), solo-pregunta = `sin_dato`; la lista en un solo lugar, medida contra el banco | 1 (decisiones 3 y 4 del plan para lo que el spec dejaba abierto) |
| 2, la basura | solo el gesto sin texto; `presentar` da `""`, el lector salta antes del corte; "-q" se presenta | 1, 3 |
| 2, el ranking | no cambia (el recall embebe el par entero) | 2 (el documento no cambia), 3 (n y umbrales no cambian) |
| 3, el reindex | `--vista` / `--aplicar`, cada ambito bajo CALIPSO_HOME, `get(include=...)`, `update(ids, metadatas)` sin documents, merge sin None, `procedencia=1` y `ruta=route`, `chat`/`modelo` ausentes, la vista con los seis conteos (incluidos los `kind="chat"` que NO parsean), idempotente, `CALIPSO_PORT` salvo `--forzar` con el mensaje que dice por que, recuento final, raros saltados y contados | 4 |
| 4, invariantes 1-7 | 1 (T1: `presentar` puro; T3: los lectores no escriben), 2 (T1 las tres formas; T3 ningun crudo en ningun prompt; T5 smoke 3), 3 (T1 la frase fija; el banco), 4 (T1 patrones en un lugar + banco), 5 (T4: ids/docs/emb/count iguales, merge, idempotente, puerto), 6 (T1 `partir` + `presentar`; T4 usa `partir`), 7 (nada toca `memory.py`; `test_abismo_memoria_recall.py` sigue verde) | 1-5 |
| 5, fixture durable | ya en main (`8fff6c1`); el porton lo RESTAURA por condicion y por pasada | 5 (y T4 lo usa copiado) |
| 5, banco | respuestas completas del fixture + JSONL sin el corte de 400, ~40 etiquetadas a mano (51), los tres bordes del spec (confabulacion = dato, "necesitas mas detalles?" con dato = dato, catastro = dato); piso 0 falsos / >= 90% | 1 |
| 5, porton en vivo | fixture restaurado, las 4 preguntas de memoria/chats, chat nuevo por turno, N=2, antes / A / B, clase determinista con las verdades sembradas + `consulto` + `eco`; aterrizaje B solo si A muestra eco y B no | 5 |
| 5, unitarios | `clasificar` (banco), `partir` y `presentar` (nuevo, viejo con las dos variantes rotas, meta, basura, sin ruta, topes), el `remember` por harness con `MemoriaFalsa` capturando meta y scope, `context_sections` y `_build_context` con el corte despues de presentar, `fuentes.memoria` bajo el techo, el reindex (vista no escribe; aplicar conserva ids/docs/count y claves viejas; idempotente; cuenta los que no parsean; se niega con el puerto ocupado; `--forzar`) | 1, 2, 3, 4 |
| 6, lo que NO hace | ni filtra al escribir, ni borra, ni cambia embedding/ranking, ni toca reflect/recent/bibliotecario/core/cronologia/chats.json, ni usa modelo, ni detecta confabulaciones, ni recupera chat/modelo de lo viejo | -- (nada del plan lo hace; el Mapa lo lista como intocable) |
| 7, corte | una rama, 5 tasks en ese orden | todas |

Huecos declarados (no son tasks porque el spec los deja afuera con nombre): el sub-bloque `recuerdos` del abismo con 8 vinetas de hasta ~650 chars desborda `ABISMO_BLOQUE_MAX` (2000) y `etiquetar` corta el bloque entero, core y cronologia incluidos (ruling 2); las palabras de Pedro no pesan mas en el ranking (spec: "a medir despues"); los departamentos no se reindexan; los turnos "-q" con acentos rotos del home real se presentan como lo que son (`Pedro dijo (fecha): -q`).

### 2. Scan de placeholders

Buscado en el plan: "TBD", "TODO", "implement later", "similar a", "agregar validacion", "etc." en pasos de codigo. Ninguno. Cada bloque de codigo es el que se escribe y es el que se corrio (seccion 4). Los `...` en los bloques ANTES/DESPUES marcan SOLO lineas que no cambian y que el bloque nombra por rango; los `<5 o 6>`, `<sin_dato y eco por condicion>`, `<A|B>` y `<N>` del Step 4-6 de la Task 5 son valores que el porton y la suite dan en vivo, por diseno (como el smoke de todos los cierres).

### 3. Consistencia de nombres y firmas entre tasks

- `memoria_procedencia.presentar(texto, meta=None, *, tope_pregunta=200, tope_respuesta=400, score=None, variante=None) -> str` (T1) es lo que llama `presentar_recuerdos` (T1) y lo que los tests de T1 y T3 llaman con `variante="A"|"B"|"off"` explicita; `presentar_recuerdos(hits, tope, *, variante=None, con_score=True) -> list[dict]` (T1) es lo que llaman `_build_context` (`..., RECALL_MAX`, con score: el system de main lo pegaba) y `fuentes.memoria` (`..., RECALL_TOP, con_score=False`: el abismo de main no) en T3, siempre con `variante` por defecto (la del entorno) en produccion; `test_la_variante_off_es_el_par_crudo_de_antes` (T1) y `test_fuentes_memoria_off_es_el_bloque_crudo_de_main_sin_score` (T3) fijan las dos formas de `off`.
- Los hits son `{text, meta, score, scope}` (`memory.py:128-129`); los dobles de T3 (`_MemoriaConHits`) y de `test_abismo_fuentes._FalsaMemoria` (sin `meta`) los producen; `presentar_recuerdos` devuelve `{**hit, "text": presentado}`; `context_sections` lee `item.get("text")`; `fuentes.memoria` lee `r["text"]`.
- `clasificar(respuesta) -> "dato" | "sin_dato"` (T1) es lo que mide `no_saber_banco.medir(clasificar)` (T1), lo que usa `revisar` del reindex (T4) y lo que el porton importa (`from calipso.memoria_procedencia import clasificar`, T5) y pasa a `clasificar_turno(clave, texto, clasificar)`.
- `partir(texto) -> (pregunta, respuesta) | None` y `limpiar_gestos(pregunta) -> str` (T1): `presentar` y `revisar` (T4) los usan igual; la basura es `limpiar_gestos(pregunta) == ""` en los dos.
- Los metadatos: lo nuevo escribe `route, kind, ruta, modelo, chat, procedencia` (T2, y el test del harness lo fija como dict exacto); `presentar` lee `ts`, `ruta` o `route`, `kind` (T1); el reindex lee `kind`, `procedencia`, `route` y escribe `procedencia`, `ruta` (T4); el smoke (T5) lee los seis del episodio nuevo.
- `MEMORIA_PRESENTAR` / `variante_activa()` / `VARIANTE_DEFAULT` / `VARIANTES` (T1) es lo que `test_build_context_honra_la_variante_del_porton` (T3) setea con `monkeypatch.setenv`, lo que el porton pone en el env del server hijo por condicion (`CONDICIONES = {"antes": "off", "A": "A", "B": "B"}`, T5) y lo que el aterrizaje cambia (T5 Step 3).
- La frase fija `SIN_DATO = "Calipso no tenia el dato entonces"` (T1) es el prefijo que `hay_eco` busca (`"no tenia el dato"`, sin acentos, T5) y lo que los tests de T1 y T3 asertan con `(local, 2026-09-10).` detras.
- `memoria_reindex.main(argv=None, salida=None) -> int` (T4) es lo que `_correr(*args)` llama en los tests y lo que `python -m calipso.memoria_reindex --vista|--aplicar [--forzar]` ejecuta (`__main__`); `revisar(col)["pendientes"]` es `[(id, meta_nueva)]` y es lo unico que `aplicar` escribe; la linea de `_linea` es la que asertan los tests y la que el smoke espera.
- El canario: `EXCEPCIONES["calipso/memoria_reindex.py:_server_prendido"]` (T4) nombra la funcion exacta del modulo (`_server_prendido`); `test_las_excepciones_apuntan_a_sitios_que_existen_y_que_no_cruzan_ya` cae si el nombre no coincide.
- Harness: `MemoriaFalsa.guardados` (T2) es `[(text, scope, meta)]` y `recordado` sigue siendo `[text]`; `chat.chat_id`, `chat.memoria`, `chat.modelo.guiones`, `de_tipo`, `srv._route_model_name` son los de `test_abismo_chat.py` de hoy.
- Conteos esperados de la suite (pytest): base -> +24 (T1) -> +27 (T2) -> +36 (T3) -> +45 (T4) -> +45 (T5); por archivo al cierre: `test_memoria_procedencia.py` 24, `test_abismo_chat.py` +3 (22), `test_memoria_lectores.py` 9, `test_memoria_reindex.py` 9, `test_aduana_canario.py` 12 (sin cambio de cantidad). Node: 428 sin cambio (no se toca `calipso/web/`). Lo que manda es `0 failed`, `EXIT=0`.

### 4. Lo que se verifico corriendo antes de escribir el plan (2026-09-11)

- `calipso/memoria_procedencia.py`, `experimentos/no_saber_banco.py` y `test_memoria_procedencia.py` tal como estan en la Task 1: `24 passed`; el banco: `26/27 atrapados (96%); datos: 0/24 falsos`. Sobre las 374 salidas unicas de los 10 `experimentos/consulta_abismo_*.jsonl` (< 400 chars, sin marca; dedupe por `salida`, el primer `item` gana): `mem-*` 102 `sin_dato` / 7 `dato`, `cha-*` 49 / 12, `pro-*` 21 / 40, `neg-*` 1 / 142 (suman 374; el unico `neg` en `sin_dato` es "Me gustaria un cafe sin azucar, ¿correcto?", que es solo una pregunta). Sobre los 16 del fixture: `sin_dato` en `[0] [1] [2] [9] [10]`, `dato` en el resto (decision 2).
- Las Tasks 2, 3 y 4 aplicadas sobre una COPIA del repo (calipso/ + los tests tocados; el fixture y `experimentos/variantes` enlazados): `133 passed` en `test_abismo_system_medido.py test_memoria_lectores.py test_abismo_chat.py test_abismo_fuentes.py test_memoria_ambito.py test_memoria_procedencia.py test_memoria_reindex.py test_aislacion_home.py test_abismo_memoria_recall.py test_economia_brief.py test_aduana_canario.py` (17 s), y `test_prompt_compiler.py` a mano `OK`. Contra el codigo de main, los rojos de los Steps 2 de cada task son los transcriptos (3 del harness, 6 de los lectores, los dos `ModuleNotFoundError`), y el canario sin la excepcion cae con la linea de `_server_prendido`.
- chromadb 1.5.9 sobre una copia del fixture: `get_collection("episodic", embedding_function=None)` + `get` no cargan `sentence_transformers`; `update(ids, metadatas)` SI lo carga (4.5 s, del cache local con `HF_HUB_OFFLINE=1` fijado antes de importar chromadb; sin la variable, HEAD a huggingface.co); tras el update: ids, documentos y embeddings identicos, count 16, meta mergeado con `procedencia` y `ruta`; `PersistentClient` sobre un directorio vacio lo crea (por eso `ambitos` exige `chroma.sqlite3`); `get_collection` en un chroma sin la coleccion levanta `NotFoundError`. Un chroma de prueba con embeddings explicitos y sin funcion de embeddings acepta `add`, `get`, `update(metadatas)` y reabrir en medio segundo.
- `python -m experimentos.no_saber_banco` y `python -m calipso.memoria_reindex --vista` (con `CALIPSO_HOME` a un temporal vacio: `ningun ambito`, exit 1) corren desde la raiz.
- Del porton (T5) se corrieron SOLO las partes puras (`clasificar_turno`, `hay_eco`, `resumen`, `restaurar_home` sobre un temporal, `_puerto_libre`) y `ast.parse` del script; `websockets` 16.0 esta en el .venv. Lo que NO se corrio: el porton en vivo, el smoke y la suite entera (escrito sobre los moldes citados: `smoke_cliente_fresco.py` del smoke del 09-10 y `docs/superpowers/2026-09-10-smoke-abismo-system-podado.md`).

## Rulings que el implementador NO puede tomar solo

Si aparece una de estas dudas, se detiene y pregunta (a Pedro, o al controlador del plan); todo lo demas esta decidido arriba o en el spec:

1. **Un patron nuevo que degrade un `dato` del banco.** El piso es 0 falsos `sin_dato`: si para atrapar un no-saber nuevo hay que aceptar un falso, no entra; se anota el caso en el banco como "se escapa" y se pregunta. Tampoco se quita una fila del banco para que pase.
2. **Un presupuesto de chars por fuente en el abismo.** Con 8 vinetas de hasta ~650 chars el sub-bloque `recuerdos` desborda `ABISMO_BLOQUE_MAX` (2000) y `etiquetar` corta el bloque entero (core y cronologia quedan afuera cuando el recall trae mucho). El spec deja el corte en `etiquetar`; bajar `RECALL_TOP`, subir el techo o presupuestar por sub-bloque es de Pedro.
3. **Cambiar que se guarda** (pregunta y respuesta separadas, `titulo`, `modelo` en el documento, `rol_pregunta`): los rulings del spec lo cierran. Lo mismo recuperar `chat`/`modelo` de lo viejo cruzando `chats.json` por `ts` (spec seccion 6).
4. **Reindexar los departamentos** (`memoria/departamento/*/chroma`) o cualquier ambito que no sea `global` y `projects/*`.
5. **Correr el reindex sobre `~/.calipso`.** Es acto de Pedro con el server apagado (spec, decision 3). El plan deja los comandos; el implementador no los ejecuta ni "para probar".
6. **El aterrizaje cuando el porton no da la salida limpia** (eco en A y en B; `sin_dato` que no baja contra `antes`; `confabula` que sube claramente en A/B). Se escribe el informe con los numeros y se para. Tambien si el porton no puede correr (Ollama sin `qwen2.5:7b`, el 8776 ocupado): no se cambia de modelo ni de puerto por cuenta propia.
7. **`--vista` con el server prendido: se pregunta ANTES de arrancar la Task 4.** El plan propone permitirla (decision 10); el spec (seccion 3 e invariante 5) dice "se niega" sin distinguir modos. El test `test_se_niega_con_el_puerto_ocupado_y_sigue_con_forzar` NO fija la conducta de la vista hasta que Pedro decida: si la vista tambien se niega, es cambiar `if args.aplicar and _server_prendido(...)` por `if _server_prendido(...)` en `main` y sumar al test `codigo, texto = _correr("--vista"); assert codigo == 2`; si se permite, sumar `assert _correr("--vista")[0] == 0` y ajustar el item 2 del smoke (Task 5, Step 4).
8. **La letra de las vinetas** (`Pedro dijo`, `Calipso contesto`, `Calipso no tenia el dato entonces (ruta, fecha).`, `Registro (kind, fecha)`): la del spec con la ruta y la fecha sumadas a la frase fija (decision 6). Cambiarla es de Pedro; el flag `eco` del porton depende del prefijo `no tenia el dato`.
9. **Los topes 200/400 y `POSICION_MAX = 250`** son numeros del spec (rulings): no se afinan para que un test pase.
10. **Que `context_sections` presente por su cuenta** (en vez de recibir el `text` presentado, decision 1): mover el corte y la presentacion del server al compilador es un cambio de arquitectura que hay que preguntar, no un refactor.
11. **El baseline exacto de la condicion `antes`.** El plan la mide sobre esta rama con `MEMORIA_PRESENTAR=off` (los dos lectores de main byte a byte) pero con el ESCRITOR de la Task 2 (decision 8: desviacion declarada, acotada a los turnos 2-4 de cada pasada). Si Pedro quiere `antes` = main exacto, es levantar el server desechable de la condicion `antes` desde un worktree de main (`git worktree add ../calipso-main main`) y no una decision del implementador.

## Correcciones tras la critica (2026-09-11, dos criticos: cobertura-firmas y factibilidad)

Todo lo que sigue esta aplicado arriba; una linea por hallazgo, con el veredicto y donde quedo.

1. **[importante, x2] `off` no reproducia el abismo de main** (`presentar_recuerdos` pasaba `score` siempre y `fuentes.memoria` pegaba `- (0.9) ...` donde `fuentes.py:118` pega `- texto`; reproducido hoy con el modulo del plan: `'- (0.87) Pedro pregunto: /local q...'`). Aplicado: `presentar_recuerdos(hits, tope, *, variante=None, con_score=True)` pasa `score=h.get("score") if con_score else None`; `fuentes.memoria` llama con `con_score=False`; `test_la_variante_off_es_el_par_crudo_de_antes` (T1) fija las dos formas por `presentar_recuerdos`; `test_fuentes_memoria_off_es_el_bloque_crudo_de_main_sin_score` (T3, el 9no de `test_memoria_lectores.py`, pasa en main y debe seguir pasando); decision 1, decision 8, Architecture, Produces de T1 y T3, docstrings de `presentar` y `presentar_recuerdos`, Self-review 3 y los conteos (T3 `6 failed, 3 passed`; suite base +36 / +45; lectores 9).
2. **[importante] La cadena `git pull --ff-only && git checkout -b` de T1 Step 1 dependia de la red** (main esta `[ahead 34]` de origin; un pull fallido dejaba el commit del plan sobre main). Aplicado: sin pull, la rama en su propia linea y `git branch --show-current` verificado antes del `git add`; en T5 Step 6 el `git push` deja de ser condicion del merge (`|| echo`, queda para Pedro si no hay red).
3. **[menor, ruling] El test de T4 congelaba `--vista` con el puerto ocupado antes del ruling 7.** No se toma la decision (es de modelo, de Pedro): el aserto sale del test con un comentario, decision 10 queda como PROPUESTA pendiente del ruling 7 (con la letra del spec: "se niega" sin distinguir modos), el ruling 7 pide preguntarlo ANTES de la Task 4 y da las dos lineas de cada salida; el item 2 del smoke (T5 Step 4) y el docstring de `memoria_reindex` lo dicen.
4. **[menor] La clausula "o si van con un fuerte" de los debiles del spec no estaba implementada ni declarada.** Aplicado: declarada como subsumida por la regla de posicion (un fuerte antes de 250 degrada solo; despues de 250 el ruling de la posicion dice que hay contenido y el debil no lo vuelve no-saber) en la decision 4 y en el comentario de `PATRONES_DEBILES`; el banco la mide (0 falsos, 26/27). No se implemento aparte: hacerlo contradiria el ruling de la posicion.
5. **[menor] La condicion `antes` corre con el escritor de la Task 2, no el de main.** Aplicado: desviacion declarada en la decision 8 y en el docstring del porton (efecto acotado a los turnos 2-4 de una pasada, chat nuevo por turno, home restaurado por pasada); el baseline exacto por worktree es el ruling 11 (nuevo).
6. **[menor] El Mapa decia "9 tests sobre homes temporales + uno sobre el fixture".** Aplicado: "8 + uno (9)" (los 9 del archivo: ambitos, vista, aplicar, segunda, niega, sin_ambitos, sin_coleccion, raros, fixture_real).
7. **[menor] La fila `fixture[12]` del banco esta recortada y el docstring pedia COMPLETAS.** Aplicado: el docstring del banco y la nota de la fila declaran que es la UNICA recortada (~300 de 5085 chars de respuesta) y por que no cambia lo que mide (verificado hoy sobre la copia del fixture: `dato`, ningun fuerte en ninguna posicion). No se pego el texto entero: son commits y diffs del orquestador que no aportan al banco.
8. **[menor] `test_fuentes_memoria_tolera_hits_sin_meta` sin `delenv`** (con `MEMORIA_PRESENTAR=off` en la shell fallaba). Aplicado: `monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)`.
9. **[menor] Las invariantes 2 y 3 se copiaban textuales sin las dos excepciones del plan.** Aplicado: linea nueva en Global Constraints: `off` (solo para medir; no se pone en produccion) y `reflect`/`recent`/el jefe (`memory.py:238-245`, `plantel/jefe.py:359`), fuera del alcance por la seccion 6 del spec y la invariante 7.
10. **[menor] La adenda de la seccion 9 del estado del proyecto no tenia esqueleto.** Aplicado: el item entero en el formato de la seccion 9 (`- **Memoria con procedencia (2026-09-11):** ...`, con el comando del reindex para Pedro) dejando entre `<>` solo lo que sale del porton; la nota del dossier de memoria, una linea con lo mismo.
11. **[menor] Las cifras por grupo del Self-review 4 no sumaban 374** (`pro-*` 21/44, `neg-*` 1/153 -> 389). Re-medido hoy con el `clasificar` del plan sobre los 10 JSONL, dedupe por `salida`: `pro-*` 21/40, `neg-*` 1/142 (suma 374, mismo unico `neg` en `sin_dato`). Aplicado; ninguna conclusion cambia.
12. **[menor] `HF_HUB_OFFLINE` por `setdefault` "protege la suite" era impreciso**: en la suite `calipso.server` ya construyo `Memory()` con el hub online (conducta de main) y el test del fixture real no sale a la red porque reutiliza el modelo cargado en el proceso; el `setdefault` protege la corrida por CLI y el archivo en aislado. Aplicado en Global Constraints y en el docstring de `memoria_reindex`. Nada cambia en el codigo.
