# El cableado del juez al camino vivo (Fase 2, parte 2a) -- plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cablear las librerias del juez de privacidad (Fase 2 parte 1, ya en main) al chat vivo, en la postura que eligio Pedro: **local por default, nube tapada a pedido**. Un gesto explicito (`/nube`) pide ayuda de la nube sobre un prompt privado; el juez decide, se redacta lo humano, se manda tapado y se repone la respuesta. Una credencial (o cualquier cosa que el juez no pueda tapar con seguridad) se mantiene local.

**Architecture:** Toda la logica nueva de decision vive en dos modulos chicos del paquete `calipso/privacidad/` (`conversacion.py`: el mapa de marcadores por conversacion; `nube.py`: la compuerta que corre el juez y arma la decision). `capabilities.parse_directives` gana el gesto `/nube`. `server.py` (el `ws_chat`) llama a la compuerta SOLO cuando el gesto esta presente, redacta el mensaje saliente, emite el degradado avisado, manda a la nube y repone la respuesta. La UI pulida del ofrecimiento y del degradado es el parte 2b; aca la senal viaja por WebSocket como un mensaje que el cliente ya puede mostrar crudo.

**Tech Stack:** Python 3.14, FastAPI, pytest. Reusa `calipso.privacidad` (detector, juez, redaccion) de la parte 1. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-02-ruteo-vivo-y-privacidad-design.md` (Fase 2, secciones 9 y 12). La UI del degradado avisado (seccion 9, la parte visual) y la normalizacion de tipos son el parte 2b, NO entran aca.

## Global Constraints

- **SIN EMOJIS.** Codigo, comentarios, texto que ve Pedro, mensajes de commit.
- **Nombres, comentarios y docstrings en ESPANOL.** Commits **sin tildes ni enie**.
- **NUNCA importar `calipso` fuera de pytest.** **HAY UN SERVIDOR CORRIENDO (pid ~357865): no pararlo, no reiniciarlo.**
- **`git add` con rutas explicitas.**
- **Postura (decision de Pedro 2026-09-02): local por default; la nube tapada es un acto explicito (`/nube`).** Un prompt privado sin `/nube` se comporta como en la Fase 1 (local o fallo cerrado). El juez LLM (~3.7s) corre SOLO en el camino `/nube`.
- **Una credencial nunca sale, ni tapada.** Si el juez devuelve `fallo_cerrado` (credencial, LLM caido, o tipo desconocido), el prompt NO va a la nube aunque haya `/nube`: se mantiene local y se avisa.
- **Ningun dato sensible viaja sin tapar.** Por eso este corte manda a la nube el mensaje redactado SIN historial (un turno privado anterior en el historial se filtraria). Redactar el historial es una refinacion posterior (ver "Lo que NO hace").
- **Los marcadores son estables por conversacion** (mismo valor real -> mismo marcador en todos los turnos de un `chat_id`).
- **Interprete:** `.venv/bin/python`. Tests: `.venv/bin/python -m pytest <archivo> -q` desde `/var/home/pedro/calipso`.

---

## Contexto verificado (leer antes de la Tarea 1)

1. **Las librerias del juez ya existen** (`calipso/privacidad/`): `juez.juzgar(texto) -> {"tramos": list, "fallo_cerrado": bool, "motivo": str}` (motivo en `credencial|juez_local_caido|tipo_desconocido|""`); `redaccion.MapaMarcadores`, `redaccion.redactar(texto, tramos, mapa) -> str`, `redaccion.reponer(texto, mapa) -> str`.
2. **`parse_directives`** (`capabilities.py:199`) devuelve un dict de overrides; ya maneja `/local`, `/api`, `/claude`, `/codex`, `/plan`, etc. El gesto `/nube` se agrega ahi.
3. **El bloque de envio del chat** vive en `ws_chat` (`server.py`, alrededor de `:2516-2565`): `if _should_orchestrate(...)` -> equipo; `elif route == "subscription"` -> `_run_subscription_text_live(..., chat_msg, ..., chat_id=chat_id)`; `else` -> `_chunks_for(route, system, chat_msg, ...)`. La respuesta se acumula en `full`; despues `full = await emisor.chunk(full)`.
4. **`chat_id`** identifica la conversacion; `_history_messages(chat_id)` arma el historial que las funciones de envio mandan a la nube. Pasar `chat_id=None` a la funcion de envio manda SIN historial (lo que este corte usa para `/nube`).
5. **`directives`** esta en scope en `ws_chat` (ya se usa `directives.get("force_team")`, `directives.get("force_route")`).

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `calipso/privacidad/conversacion.py` | el mapa de marcadores por `chat_id` (T1) |
| `calipso/privacidad/nube.py` | la compuerta: corre el juez y arma la decision (T2) |
| `calipso/capabilities.py` | el gesto `/nube` en `parse_directives` (T3) |
| `calipso/server.py` | el cableado en `ws_chat`: redactar, avisar, mandar, reponer (T4) |
| `test_privacidad_conversacion.py`, `test_privacidad_nube.py`, `test_capabilities.py` (existe), `test_chat_live.py` (existe) | tests |

## Los tipos que comparten las tareas

- **Decision** (lo que devuelve `nube.preparar_envio`): `dict` con
  `{"accion": str, "texto": str | None, "tapados": list[dict], "motivo": str}`.
  `accion` en `{"nube", "local"}`. Si `accion=="local"`, `texto` es `None` y
  `motivo` dice por que (credencial/juez_local_caido/tipo_desconocido). Si
  `accion=="nube"`, `texto` es el mensaje redactado (o el original si no habia
  nada sensible) y `tapados` es `[{"marcador": str, "tipo": str}]` para el aviso.

---

### Task 1: El mapa de marcadores por conversacion

**Files:**
- Create: `calipso/privacidad/conversacion.py`
- Test: `test_privacidad_conversacion.py`

**Interfaces:**
- Produces: `mapa_para(chat_id: str | None) -> MapaMarcadores` (el mismo `chat_id` devuelve SIEMPRE el mismo `MapaMarcadores`, para que los marcadores sean estables entre turnos; `chat_id=None` devuelve uno nuevo, sin cachear). `olvidar(chat_id: str) -> None` (limpia una conversacion).

- [ ] **Step 1: Escribir los tests que fallan**

```python
# test_privacidad_conversacion.py
from calipso.privacidad import conversacion
from calipso.privacidad.redaccion import MapaMarcadores


def test_mismo_chat_id_mismo_mapa():
    m1 = conversacion.mapa_para("chat-1")
    m2 = conversacion.mapa_para("chat-1")
    assert m1 is m2
    assert isinstance(m1, MapaMarcadores)


def test_chat_ids_distintos_mapas_distintos():
    assert conversacion.mapa_para("chat-a") is not conversacion.mapa_para("chat-b")


def test_none_no_cachea():
    assert conversacion.mapa_para(None) is not conversacion.mapa_para(None)


def test_olvidar_libera():
    m1 = conversacion.mapa_para("chat-x")
    conversacion.olvidar("chat-x")
    assert conversacion.mapa_para("chat-x") is not m1
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `.venv/bin/python -m pytest test_privacidad_conversacion.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Escribir el modulo**

`calipso/privacidad/conversacion.py`:
```python
"""El mapa de marcadores de una conversacion. Los marcadores de redaccion
tienen que ser estables entre turnos (el mismo valor real -> el mismo
marcador) para que la nube no pierda el hilo. Este modulo guarda un
MapaMarcadores por chat_id, vivo lo que dura el proceso del servidor.

No persiste a disco: un marcador tapa un valor solo en el trafico de salida;
no hay razon para guardarlo entre reinicios.
"""
from calipso.privacidad.redaccion import MapaMarcadores

_por_chat: dict[str, MapaMarcadores] = {}


def mapa_para(chat_id: str | None) -> MapaMarcadores:
    """El MapaMarcadores de una conversacion. Mismo chat_id -> mismo mapa.
    chat_id None (sin conversacion) devuelve uno nuevo, sin cachear."""
    if chat_id is None:
        return MapaMarcadores()
    if chat_id not in _por_chat:
        _por_chat[chat_id] = MapaMarcadores()
    return _por_chat[chat_id]


def olvidar(chat_id: str) -> None:
    """Descarta el mapa de una conversacion (p.ej. al borrarla)."""
    _por_chat.pop(chat_id, None)
```

- [ ] **Step 4: Correr y ver verde**

Run: `.venv/bin/python -m pytest test_privacidad_conversacion.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/privacidad/conversacion.py test_privacidad_conversacion.py
git commit -m "feat(privacidad): mapa de marcadores estable por conversacion"
```

---

### Task 2: La compuerta de envio a la nube

**Files:**
- Create: `calipso/privacidad/nube.py`
- Test: `test_privacidad_nube.py`

**Interfaces:**
- Consumes: `juez.juzgar`, `redaccion.redactar`, `redaccion.MapaMarcadores`.
- Produces: `preparar_envio(texto: str, mapa: MapaMarcadores) -> dict` = la `Decision` (ver "Los tipos"). Corre el juez; si `fallo_cerrado` -> `accion="local"`; si no -> redacta los tramos humanos y devuelve `accion="nube"` con el texto tapado y la lista de tapados.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# test_privacidad_nube.py
from calipso.privacidad import nube
from calipso.privacidad.redaccion import MapaMarcadores


def _mock_juez(monkeypatch, veredicto):
    monkeypatch.setattr(nube.juez, "juzgar", lambda t: veredicto)


def test_fallo_cerrado_se_queda_local(monkeypatch):
    _mock_juez(monkeypatch, {"tramos": [], "fallo_cerrado": True, "motivo": "credencial"})
    d = nube.preparar_envio("subo esta clave?", MapaMarcadores())
    assert d["accion"] == "local"
    assert d["motivo"] == "credencial"
    assert d["texto"] is None


def test_humano_se_redacta_para_la_nube(monkeypatch):
    _mock_juez(monkeypatch, {"tramos": [{"texto": "3865-4421", "tipo": "contacto"}],
                             "fallo_cerrado": False, "motivo": ""})
    d = nube.preparar_envio("mi numero es 3865-4421, buscame vuelos", MapaMarcadores())
    assert d["accion"] == "nube"
    assert "3865-4421" not in d["texto"]           # el valor real no viaja
    assert "[CONTACTO_1]" in d["texto"]
    assert d["tapados"] == [{"marcador": "[CONTACTO_1]", "tipo": "contacto"}]


def test_nada_sensible_viaja_igual(monkeypatch):
    _mock_juez(monkeypatch, {"tramos": [], "fallo_cerrado": False, "motivo": ""})
    d = nube.preparar_envio("me explicas las tuplas?", MapaMarcadores())
    assert d["accion"] == "nube"
    assert d["texto"] == "me explicas las tuplas?"
    assert d["tapados"] == []
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `.venv/bin/python -m pytest test_privacidad_nube.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Escribir el modulo**

`calipso/privacidad/nube.py`:
```python
"""La compuerta entre un prompt y la nube, cuando Pedro pide ayuda de la nube
sobre un prompt privado (el gesto `/nube`). Corre el juez de dos capas y decide:

- Si el juez falla cerrado (credencial, LLM local caido, o un tipo que no puede
  categorizar con seguridad): el prompt NO va a la nube -- se queda local. Una
  credencial nunca sale, ni tapada.
- Si hay tramos de lenguaje humano: los tapa con marcadores estables y devuelve
  el texto redactado para mandar, mas la lista de que se tapo (para el aviso).
- Si no hay nada sensible: el texto viaja igual.

El juez corre SOLO aca (camino `/nube`), no en cada prompt: local es el default.
"""
from calipso.privacidad import juez
from calipso.privacidad import redaccion
from calipso.privacidad.redaccion import MapaMarcadores


def preparar_envio(texto: str, mapa: MapaMarcadores) -> dict:
    """Decide como (y si) mandar `texto` a la nube. Devuelve
    {"accion": "nube"|"local", "texto": str|None, "tapados": list, "motivo": str}."""
    veredicto = juez.juzgar(texto)
    if veredicto["fallo_cerrado"]:
        return {"accion": "local", "texto": None, "tapados": [],
                "motivo": veredicto["motivo"]}
    tramos = veredicto["tramos"]
    tapado = redaccion.redactar(texto, tramos, mapa)
    tapados = [{"marcador": mapa.marcador_para(t["texto"], t["tipo"]),
                "tipo": t["tipo"]} for t in tramos]
    return {"accion": "nube", "texto": tapado, "tapados": tapados, "motivo": ""}
```

Nota: `redactar` ya llamo a `marcador_para` para cada tramo, asi que el
`marcador_para` de la lista `tapados` devuelve el marcador ya asignado (es
estable), no crea uno nuevo. Es el mismo marcador que quedo en `tapado`.

- [ ] **Step 4: Correr y ver verde**

Run: `.venv/bin/python -m pytest test_privacidad_nube.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/privacidad/nube.py test_privacidad_nube.py
git commit -m "feat(privacidad): la compuerta de envio a la nube (juez + redaccion)"
```

---

### Task 3: El gesto `/nube` en las directivas

**Files:**
- Modify: `calipso/capabilities.py`, `parse_directives` (`:199`)
- Test: `test_capabilities.py` (existe)

**Interfaces:**
- Produces: `parse_directives(message)` devuelve la clave nueva `"nube": bool` en su dict de salida (True si el mensaje tiene el token `/nube`). El `/nube` se saca del mensaje limpio.

- [ ] **Step 1: Escribir el test que falla**

Abri `test_capabilities.py` y mira como se testea `parse_directives` (que estructura espera). Agrega, con el estilo del archivo:

```python
def test_nube_se_detecta_y_se_limpia():
    d = parse_directives("/nube mi numero es 3865-4421, buscame vuelos")
    assert d["nube"] is True
    assert "/nube" not in d["clean"]
    assert "buscame vuelos" in d["clean"]


def test_sin_nube_es_false():
    assert parse_directives("hola que tal")["nube"] is False
```

(Adapta el import y el nombre exacto a como el archivo ya llama a `parse_directives`.)

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest test_capabilities.py -q -k nube`
Expected: FAIL (`KeyError: 'nube'`)

- [ ] **Step 3: Agregar el gesto**

En `parse_directives` (`capabilities.py`): agrega `"nube": False` al dict `out` inicial, y una rama en el loop de tokens (junto a las otras directivas `elif`):
```python
        elif tl == "/nube":
            out["nube"] = True
```
(No agrega el token a `keep`, asi se saca del mensaje limpio, igual que las otras directivas.)

- [ ] **Step 4: Correr y ver verde**

Run: `.venv/bin/python -m pytest test_capabilities.py -q`
Expected: PASS (el nuevo test y los que ya estaban)

- [ ] **Step 5: Commit**

```bash
git add calipso/capabilities.py test_capabilities.py
git commit -m "feat(ruteo): el gesto /nube pide ayuda de la nube con redaccion"
```

---

### Task 4: Cablear la compuerta al chat vivo

**Files:**
- Modify: `calipso/server.py`, `ws_chat` (el bloque de envio, alrededor de `:2513-2565`)
- Test: `test_chat_live.py` (existe)

**Interfaces:**
- Consumes: `conversacion.mapa_para`, `nube.preparar_envio`, `redaccion.reponer`, `directives["nube"]`.
- Produces: comportamiento nuevo del chat cuando `directives.get("nube")` es True.

**El flujo a cablear (leer con cuidado; adaptar al codigo real del bloque):**
Cuando `directives.get("nube")` es True, ANTES del bloque `try` de envio (y despues de que `_decide` produjo `verdict`/`route`):
1. `mapa = conversacion.mapa_para(chat_id)`
2. `dec = await asyncio.to_thread(nube.preparar_envio, chat_msg, mapa)` (el juez es una llamada bloqueante a Ollama; va en un hilo, como el resto de las llamadas al modelo local).
3. **Si `dec["accion"] == "local"` (fallo cerrado):** el prompt NO va a la nube por NINGUN camino -- ni ruteo directo ni orquestacion. Emitir el aviso y forzar local de forma que el bloque tome la rama `_chunks_for("local", ...)`:
   ```python
   await ws.send_json({"type": "privacidad", "action": "local",
                       "motivo": dec["motivo"]})
   route = "local"
   verdict["route"] = "local"
   ```
   Y **saltear la orquestacion**: el `if _should_orchestrate(...)` del bloque se evalua independiente de `route`, asi que un prompt complejo orquestaria a la nube igual. Guarda el resultado del gate en una variable (p.ej. `nube_local = True`) y agregala a la condicion: `if _should_orchestrate(...) and not nube_local:`. Con `route == "local"` y la orquestacion salteada, el bloque cae en la rama local. (Ademas la orquestacion ya devuelve False para `features["private"]`, pero un `/nube` no siempre viene marcado privado por la regex debil, por eso el corte explicito.)
4. **Si `dec["accion"] == "nube"`:** el prompt SI va a la nube, tapado. Como el default es local, `/nube` tiene que EMPUJAR la ruta a la nube (salvo que Pedro ya haya forzado otra con `/api`/`/claude`/`/codex`): si `route == "local"` y no hay `force_route`, subilo a `"subscription"` (la nube gratis). Emitir el degradado y preparar el mensaje saliente redactado, SIN historial:
   ```python
   await ws.send_json({"type": "privacidad", "action": "tapado",
                       "tapados": dec["tapados"], "texto_tapado": dec["texto"]})
   if route == "local" and not directives.get("force_route"):
       route = "subscription"
       verdict["route"] = "subscription"
   mensaje_saliente = dec["texto"]
   ```
   En TODAS las llamadas de envio a la nube del bloque (`_run_dynamic_team`, `_run_subscription_text_live`, `_chunks_for` rama api) pasar `mensaje_saliente` en lugar de `chat_msg` y `chat_id=None` (sin historial, para no filtrar un turno privado anterior). Guardar `mapa` para reponer.
5. Despues de tener `full` (la respuesta de la nube) y ANTES de `full = await emisor.chunk(full)`: si fue camino nube con redaccion, `full = redaccion.reponer(full, mapa)` -- repone los valores reales localmente antes de mostrar. (Si hubo `_local`/fallo cerrado no hay nada que reponer, pero reponer un texto sin marcadores es inocuo -- `reponer` solo toca marcadores conocidos.)

**IMPORTANTE de alcance:** si `directives.get("nube")` NO esta, NADA cambia -- el chat se comporta exactamente como hoy. Todo el codigo nuevo esta detras de ese `if`. El corte de la orquestacion (`and not nube_local`) tambien: `nube_local` arranca en False.

- [ ] **Step 1: Escribir el test que falla**

Abri `test_chat_live.py` y mira como ejercita `ws_chat` (que fixture de WebSocket usa, como mockea el modelo). Escribi un test que, con `directives` de `/nube`:
- Con el juez mockeado devolviendo `fallo_cerrado` (credencial) -> el chat NO llama a la funcion de envio a la nube (`_run_subscription_text_live`) y emite `{"type":"privacidad","action":"local"}`.
- Con el juez mockeado devolviendo un tramo humano -> la funcion de envio a la nube recibe el texto REDACTADO (no el original) y `chat_id=None`; el WebSocket ve `{"type":"privacidad","action":"tapado"}`; y la respuesta mostrada tiene el valor REPUESTO.

Usa los mocks que el archivo ya tenga para el modelo/red; NO llames a Ollama ni a la nube de verdad. Si el archivo no tiene un camino limpio para interceptar la funcion de envio, monkeypatchea `server._run_subscription_text_live` para capturar con que texto y chat_id fue llamada.

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest test_chat_live.py -q -k nube`
Expected: FAIL

- [ ] **Step 3: Cablear en `ws_chat`**

Segui el flujo de arriba. Lee el bloque `:2513-2565` entero antes de tocar. Agrega el `if directives.get("nube"):` con los cinco pasos, y asegurate de que:
- el camino sin `/nube` queda intacto (todo detras del `if`),
- la llamada al juez va en `asyncio.to_thread`,
- la reposicion pasa sobre `full` en TODAS las ramas de envio a la nube (equipo, subscription, api) cuando hubo redaccion.

- [ ] **Step 4: Correr y ver verde**

Run: `.venv/bin/python -m pytest test_chat_live.py -q`
Expected: PASS (el nuevo y los que ya estaban)

- [ ] **Step 5: Correr la suite entera (es el camino vivo; no romper nada)**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add calipso/server.py test_chat_live.py
git commit -m "feat(ruteo): /nube corre el juez, redacta el saliente y repone la respuesta"
```

---

## Lo que este plan NO hace (parte 2b o despues)

- **La UI pulida** del ofrecimiento ("lo tengo local, queres la nube tapada?") y del degradado avisado en `/fabrica`. Aca la senal viaja como `{"type":"privacidad",...}` por WebSocket; el cliente ya puede mostrarla cruda, pero el diseno visual es del parte 2b.
- **Redactar el HISTORIAL.** Este corte manda a la nube el turno actual redactado SIN historial (`chat_id=None`), para no filtrar un turno privado anterior. Incluir historial redactado (con el mismo mapa de conversacion, y juzgando los turnos que nunca se juzgaron) es una refinacion posterior.
- **Normalizacion de tipos** (mapear "medicamento recetado" -> "salud" para recuperar el ~8% de salud que hoy cae a fallo cerrado). Es del juez (parte 1) y se decide con datos; parte 2b o despues.
- **Mover el helper HTTP al paquete** (`import dispatch` pelado en juez_llm). Higiene, despues.

## Nota de verificacion final

Al terminar: la suite entera verde, y el par de invariantes que este parte agrega, verificado en test: (1) sin `/nube`, el chat se comporta identico a hoy; (2) con `/nube` y una credencial, el prompt se queda local y NO se llama a la nube; (3) con `/nube` y un dato humano, a la nube viaja el texto TAPADO (verificado mirando el argumento de la funcion de envio, no la pantalla) y la respuesta se muestra REPUESTA. Ese trio es la prueba de que "local por default, nube tapada a pedido" se cumple.
