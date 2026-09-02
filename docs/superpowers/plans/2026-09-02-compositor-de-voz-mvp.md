# El compositor de voz (MVP local) -- plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que Calipso escriba en la voz de Pedro con el gesto `/redacta` en el chat -- respondiendo un hilo pegado o redactando desde cero -- usando el modelo LOCAL (privado), con `/otra` para otra version. Es el MVP: local-only; `/redacta /nube` (mejor calidad por la nube) es un slice posterior.

**Architecture:** Un paquete `calipso/compositor/` con dos modulos de responsabilidad unica: `voz.py` (junta ejemplos de como escribe Pedro, de sus mensajes) y `redactor.py` (arma el prompt de redaccion, puro). `capabilities.parse_directives` gana `/redacta` y `/otra`. `server.py` (`ws_chat`) intercepta el gesto: junta ejemplos, arma el prompt, corre el modelo local, y muestra el borrador. Nada sale de la maquina (local-only).

**Tech Stack:** Python 3.14, FastAPI, pytest. Reusa la ruta local del chat (`_chunks_for("local", ...)`, ya arreglada en Fase 1) y `chats.py` (los mensajes de Pedro). Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-02-compositor-de-voz-design.md`.

## Global Constraints

- **SIN EMOJIS.** Codigo, comentarios, texto que ve Pedro, mensajes de commit.
- **Nombres, comentarios y docstrings en ESPANOL.** Commits **sin tildes ni enie**.
- **NUNCA importar `calipso` fuera de pytest.** **HAY UN SERVIDOR CORRIENDO: no pararlo, no reiniciarlo.**
- **`git add` con rutas explicitas.**
- **Calipso REDACTA, no manda.** El compositor solo produce un borrador; Pedro copia y manda por su cuenta. Nunca se conecta a mail/chat/nada.
- **MVP local-only.** El borrador se escribe con el modelo LOCAL. Nada sale de la maquina. `/redacta /nube` NO entra en este plan.
- **Sin `/redacta`, el chat es identico a hoy.** Todo el codigo nuevo detras de `directives.get("redacta")`.
- **Interprete:** `.venv/bin/python`. Tests: `.venv/bin/python -m pytest <archivo> -q` desde `/var/home/pedro/calipso`.

---

## Contexto verificado (leer antes de la Tarea 1)

1. **Los mensajes de Pedro** viven en `chats.py`: `chats._load()` devuelve `{"active":..., "chats": {id: chat}}`; cada `chat` tiene `"messages": [{"role","text",...}]`. Los de Pedro son `role == "user"`.
2. **`parse_directives`** (`capabilities.py:199`) ya maneja `/nube`, `/api`, etc. Agregar `/redacta` y `/otra` es el mismo patron.
3. **La ruta local del chat**: `_chunks_for("local", system, user_msg, usage, model, effort, chat_id=...)` (`server.py`) transmite desde Ollama. El compositor la reusa para que el borrador salga en streaming como una respuesta.
4. **El gate de directivas en `ws_chat`** esta cerca de donde ya se lee `directives.get("nube")` (~`server.py:2458`).

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `calipso/compositor/__init__.py` | marca el paquete |
| `calipso/compositor/voz.py` | junta ejemplos de como escribe Pedro (T1) |
| `calipso/compositor/redactor.py` | arma el prompt de redaccion, puro (T2) |
| `calipso/capabilities.py` | `/redacta` y `/otra` en parse_directives (T3) |
| `calipso/server.py` | el gate en `ws_chat`: junta, arma, corre local, muestra (T4) |
| `test_compositor_voz.py`, `test_compositor_redactor.py`, `test_capabilities.py` (existe) | tests |

---

### Task 1: Los ejemplos de voz de Pedro

**Files:**
- Create: `calipso/compositor/__init__.py` (docstring de una linea)
- Create: `calipso/compositor/voz.py`
- Test: `test_compositor_voz.py`

**Interfaces:**
- Produces: `ejemplos_de_voz(chats_data: dict, n: int = 6) -> list[str]`. Devuelve hasta `n` mensajes REALES de Pedro (`role=="user"`) sacados de `chats_data`, para usar como ejemplos de su estilo: los mas recientes primero, sin duplicados, salteando los triviales (muy cortos, o que son solo una directiva `/...`).

- [ ] **Step 1: Escribir los tests que fallan**

```python
# test_compositor_voz.py
from calipso.compositor.voz import ejemplos_de_voz


def _chats(*mensajes_por_chat):
    # cada arg es una lista de (role, text); arma la forma de chats._load()
    chats = {}
    for i, msgs in enumerate(mensajes_por_chat):
        chats[f"c{i}"] = {"messages": [{"role": r, "text": t} for r, t in msgs]}
    return {"active": None, "chats": chats}


def test_solo_mensajes_de_pedro():
    data = _chats([("user", "che como andas"), ("assistant", "bien vos?"),
                   ("user", "todo piola")])
    ej = ejemplos_de_voz(data)
    assert "che como andas" in ej and "todo piola" in ej
    assert "bien vos?" not in ej   # eso lo dijo calipso, no Pedro


def test_saltea_triviales_y_directivas():
    data = _chats([("user", "1"), ("user", "dale"), ("user", "/nube"),
                   ("user", "armame un plan largo para el finde con detalle")])
    ej = ejemplos_de_voz(data)
    assert ej == ["armame un plan largo para el finde con detalle"]


def test_sin_duplicados_y_tope_n():
    data = _chats([("user", "hola")] * 10 + [("user", f"mensaje {i} distinto y largo") for i in range(10)])
    ej = ejemplos_de_voz(data, n=3)
    assert len(ej) == 3
    assert len(set(ej)) == 3      # sin duplicados


def test_los_mas_recientes_primero():
    data = _chats([("user", "el primero de todos largo"),
                   ("user", "el ultimo que escribio pedro largo")])
    ej = ejemplos_de_voz(data)
    assert ej[0] == "el ultimo que escribio pedro largo"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `.venv/bin/python -m pytest test_compositor_voz.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Escribir el modulo**

`calipso/compositor/__init__.py`:
```python
"""El compositor de voz: Calipso escribe en la voz de Pedro (gesto /redacta)."""
```

`calipso/compositor/voz.py`:
```python
"""Junta ejemplos de COMO ESCRIBE Pedro, de sus mensajes reales, para darselos
al que redacta como muestra de su estilo. No es un modelo entrenado: son los
mensajes de Pedro tal cual, elegidos para que el que redacta imite su voz.

En el MVP la seleccion es simple -- los mas recientes, sin triviales -- que
alcanza para capturar sus habitos de superficie (sin tildes, muletillas, largo
de frase). La recuperacion semantica por registro es un refinamiento posterior.
"""

# Mensajes demasiado cortos o que son solo una orden no muestran su estilo.
_MIN_LARGO = 12


def _es_util(texto: str) -> bool:
    t = (texto or "").strip()
    if len(t) < _MIN_LARGO:
        return False
    if t.startswith("/"):        # una directiva (/nube, /redacta...) no es voz
        return False
    return True


def ejemplos_de_voz(chats_data: dict, n: int = 6) -> list[str]:
    """Hasta `n` mensajes reales de Pedro (role=="user") como ejemplos de su
    voz: los mas recientes primero, sin duplicados, sin triviales ni ordenes."""
    # recorrer todos los chats juntando los mensajes de Pedro en orden.
    mensajes: list[str] = []
    for chat in (chats_data or {}).get("chats", {}).values():
        for m in chat.get("messages", []):
            if m.get("role") == "user" and _es_util(m.get("text", "")):
                mensajes.append(m["text"].strip())
    # los mas recientes primero, sin duplicados, tope n.
    vistos: set[str] = set()
    ej: list[str] = []
    for texto in reversed(mensajes):
        if texto not in vistos:
            vistos.add(texto)
            ej.append(texto)
            if len(ej) >= n:
                break
    return ej
```

- [ ] **Step 4: Correr y ver verde**

Run: `.venv/bin/python -m pytest test_compositor_voz.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/compositor/__init__.py calipso/compositor/voz.py test_compositor_voz.py
git commit -m "feat(compositor): juntar ejemplos de la voz de Pedro de sus mensajes"
```

---

### Task 2: El prompt de redaccion

**Files:**
- Create: `calipso/compositor/redactor.py`
- Test: `test_compositor_redactor.py`

**Interfaces:**
- Produces: `construir_prompt(pedido: str, ejemplos: list[str]) -> tuple[str, str]`. Devuelve `(system, user_msg)` para la llamada al modelo. El `system` instruye: escribir EN LA VOZ de Pedro (con los ejemplos como muestra), inferir si `pedido` es un hilo a responder o una intencion a redactar, adaptar el registro, y devolver SOLO el borrador (sin preambulo). El `user_msg` es el `pedido`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# test_compositor_redactor.py
from calipso.compositor.redactor import construir_prompt


def test_el_system_lleva_los_ejemplos_y_la_instruccion():
    system, user = construir_prompt("respondele esto", ["che como va", "todo piola"])
    assert "che como va" in system and "todo piola" in system   # los ejemplos
    assert "voz" in system.lower()                              # la instruccion de voz
    # infiere responder-vs-desde-cero e instruye SOLO el borrador
    assert "solo" in system.lower() or "sin preambulo" in system.lower()
    assert user == "respondele esto"


def test_sin_ejemplos_igual_arma_prompt():
    system, user = construir_prompt("decile a ana que no llego", [])
    assert isinstance(system, str) and system
    assert user == "decile a ana que no llego"
    # sin ejemplos, el system lo dice (no inventa una voz falsa)
    assert "sin ejemplos" in system.lower() or "no hay ejemplos" in system.lower()
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `.venv/bin/python -m pytest test_compositor_redactor.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Escribir el modulo**

`calipso/compositor/redactor.py`:
```python
"""Arma el prompt que hace que el modelo escriba EN LA VOZ de Pedro. Puro: no
llama a ningun modelo, solo construye (system, user). Quien lo corre es el
chat (con el modelo local por default).
"""

_BASE = """\
Sos el compositor de voz de Calipso. Tu tarea NO es responderle a Pedro: es
escribir un texto COMO LO ESCRIBIRIA PEDRO, para que el lo mande como suyo.

El mensaje de Pedro es una de dos cosas, y tenes que inferir cual:
- un mensaje que a Pedro le llego y quiere responder -> escribi SU respuesta;
- una intencion ("decile a X que...") -> escribi ese texto desde cero.

Reglas:
- Escribi en la VOZ de Pedro: su registro, sus muletillas, su puntuacion, su
  largo de frase. Adapta el registro al contexto (a un amigo distinto que a un
  cliente), pero siempre suena a el.
- Devolve SOLO el texto listo para mandar, sin preambulo, sin comillas, sin
  explicar. Nada de "aca va tu respuesta:".
"""

_CON_EJEMPLOS = """
Asi escribe Pedro (ejemplos reales de sus mensajes, imita este estilo):
{ejemplos}
"""

_SIN_EJEMPLOS = """
No hay ejemplos de la voz de Pedro disponibles: escribi natural y directo,
sin inventar un estilo que no conoces.
"""


def construir_prompt(pedido: str, ejemplos: list[str]) -> tuple[str, str]:
    """(system, user) para redactar en la voz de Pedro."""
    if ejemplos:
        bloque = "\n".join(f"- {e}" for e in ejemplos)
        system = _BASE + _CON_EJEMPLOS.format(ejemplos=bloque)
    else:
        system = _BASE + _SIN_EJEMPLOS
    return system, pedido
```

- [ ] **Step 4: Correr y ver verde**

Run: `.venv/bin/python -m pytest test_compositor_redactor.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/compositor/redactor.py test_compositor_redactor.py
git commit -m "feat(compositor): el prompt que redacta en la voz de Pedro"
```

---

### Task 3: Los gestos `/redacta` y `/otra`

**Files:**
- Modify: `calipso/capabilities.py`, `parse_directives`
- Test: `test_capabilities.py` (existe -- es un SCRIPT con `main()`/`check()`, NO pytest; se corre `.venv/bin/python test_capabilities.py`)

**Interfaces:**
- Produces: `parse_directives(message)` gana `"redacta": bool` y `"otra": bool` en su dict, y saca los tokens del `clean`.

- [ ] **Step 1: Escribir los checks que fallan**

ABRI `test_capabilities.py` y mira el estilo (`check()` dentro de `main()`, no pytest). Agrega, con ese estilo:

```python
    d = parse_directives("/redacta respondele que si a este mensaje")
    check(d["redacta"] is True, "redacta detectado")
    check("/redacta" not in d["clean"], "redacta sacado del clean")
    check("respondele" in d["clean"], "resto preservado")
    check(parse_directives("hola")["redacta"] is False, "sin redacta es false")
    check(parse_directives("/otra")["otra"] is True, "otra detectado")
    check(parse_directives("hola")["otra"] is False, "sin otra es false")
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python test_capabilities.py`
Expected: los checks nuevos fallan (`KeyError: 'redacta'`)

- [ ] **Step 3: Agregar los gestos**

En `parse_directives`: agrega `"redacta": False` y `"otra": False` al dict `out` inicial, y en el loop de tokens:
```python
        elif tl == "/redacta":
            out["redacta"] = True
        elif tl == "/otra":
            out["otra"] = True
```
(No se agregan a `keep`, asi salen del `clean`.)

- [ ] **Step 4: Correr y ver verde**

Run: `.venv/bin/python test_capabilities.py`
Expected: todos los checks OK, exit 0

- [ ] **Step 5: Commit**

```bash
git add calipso/capabilities.py test_capabilities.py
git commit -m "feat(compositor): gestos /redacta y /otra en las directivas"
```

---

### Task 4: Cablear el compositor al chat

**Files:**
- Modify: `calipso/server.py`, `ws_chat`
- Test: (no hay test unitario del ws en vivo -- ver abajo; se testea la logica pura extraida)

**Interfaces:**
- Consumes: `voz.ejemplos_de_voz`, `redactor.construir_prompt`, `chats._load`, `_chunks_for("local", ...)`, `directives["redacta"]`, `directives["otra"]`.

**El flujo a cablear (leer el bloque de `ws_chat` antes de tocar; adaptar):**
Cuando `directives.get("redacta")` o `directives.get("otra")`, el turno NO es una respuesta normal: es un borrador. ANTES del ruteo normal:
1. Determinar el `pedido`:
   - `/redacta`: el `pedido` es el mensaje limpio (`chat_msg`). Guardarlo por conversacion: `_ultimo_pedido[chat_id] = chat_msg` (un dict de modulo, como `conversacion._por_chat`).
   - `/otra`: el `pedido` es `_ultimo_pedido.get(chat_id)`. Si no hay (no hubo `/redacta` antes), avisar por WS (`{"type":"error","text":"deci /redacta primero"}`) y cortar el turno.
2. `ejemplos = voz.ejemplos_de_voz(chats._load())`.
3. `system, user_msg = redactor.construir_prompt(pedido, ejemplos)`.
4. Correr el modelo LOCAL con ese prompt: `gen, model = _chunks_for("local", system, user_msg, usage, _route_model_name("local"), chat_id=None)` y transmitir los chunks como hoy (el mismo loop de streaming del `else` de la rama local). El borrador sale en streaming. `chat_id=None`: el borrador no arrastra el historial del chat (es un texto aparte, no una respuesta en la conversacion).
5. Emitir un aviso de que es un borrador: antes de los chunks, `await ws.send_json({"type":"borrador","action":"inicio"})` (el cliente puede marcarlo; si no lo maneja, se ve como una respuesta normal -- inocuo).
6. Terminar el turno del borrador (cost/done) como un turno local normal, SIN cobrar suscripcion (es local, ya es gratis por Fase 1) y sin guardar el borrador como un turno de la conversacion si eso ensucia el historial -- decidilo leyendo como se guarda hoy; lo minimo: que el borrador no quede como "respuesta de Calipso" en un chat que despues se relee. Si guardarlo/no es complejo, dejalo como turno normal y anotalo.

**IMPORTANTE de alcance:** sin `/redacta` ni `/otra`, NADA cambia. Todo detras de ese `if`. El borrador NUNCA sale a la nube (siempre `_chunks_for("local")`). `/redacta /nube` no se implementa en este plan.

**Testabilidad:** el `ws_chat` en vivo no tiene test unitario (habla por WebSocket). Extrae la logica testeable a una funcion pura y testeala:
- En `calipso/compositor/redactor.py` (o un modulo nuevo del paquete), agrega:
  `def preparar_borrador(pedido: str, chats_data: dict) -> tuple[str, str]` que junta ejemplos (`voz.ejemplos_de_voz`) y arma el prompt (`construir_prompt`), devolviendo `(system, user)`. Unit-testeala en `test_compositor_redactor.py`: con un `chats_data` con mensajes de Pedro, el `system` lleva esos ejemplos y el `user` es el pedido.
- El pegamento en `ws_chat` (elegir el pedido, `/otra`, correr local, streaming) se verifica por lectura + la suite entera verde.

- [ ] **Step 1: El test de `preparar_borrador`**

```python
# agregar a test_compositor_redactor.py
from calipso.compositor.redactor import preparar_borrador


def test_preparar_borrador_junta_ejemplos_y_pedido():
    data = {"active": None, "chats": {"c0": {"messages": [
        {"role": "user", "text": "che todo piola por aca"},
        {"role": "assistant", "text": "que bueno"}]}}}
    system, user = preparar_borrador("decile que si", data)
    assert "che todo piola por aca" in system
    assert user == "decile que si"
```

- [ ] **Step 2: Correr y ver que falla**

Run: `.venv/bin/python -m pytest test_compositor_redactor.py -q -k preparar`
Expected: FAIL

- [ ] **Step 3: Escribir `preparar_borrador` y cablear `ws_chat`**

`preparar_borrador` en `redactor.py`:
```python
from calipso.compositor import voz


def preparar_borrador(pedido: str, chats_data: dict) -> tuple[str, str]:
    """Junta los ejemplos de voz de Pedro y arma el (system, user) para el
    borrador. La cara testeable de lo que hace el chat en /redacta."""
    ejemplos = voz.ejemplos_de_voz(chats_data)
    return construir_prompt(pedido, ejemplos)
```

Y el cableado en `ws_chat` segun el flujo de arriba (con el dict `_ultimo_pedido` a nivel de modulo en server.py, o importado del paquete). Leé el bloque de envio y el gate de `/nube` para ubicar donde va el `if directives.get("redacta") or directives.get("otra")`.

- [ ] **Step 4: Verde + suite entera**

Run: `.venv/bin/python -m pytest test_compositor_redactor.py -q` (el test nuevo)
Run: `.venv/bin/python -m pytest -q` (la suite entera -- no romper el chat)
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py calipso/compositor/redactor.py test_compositor_redactor.py
git commit -m "feat(compositor): /redacta corre el compositor local y muestra el borrador"
```

---

## Lo que este plan NO hace (slices posteriores)

- **`/redacta /nube`** (mejor borrador por la nube): necesita tapar SOLO el hilo y NO los ejemplos de estilo -- mas wiring que reusar el `/nube` del chat. Proximo slice.
- **Recuperacion semantica por registro** (embeddings): el MVP usa una muestra de mensajes recientes. Refinamiento.
- **La ficha de voz explicita y editable** (seccion 6 del spec).
- **Sembrar ejemplos** (`/voz <ejemplo>` etiquetado por registro) para mejorar el rango. Refinamiento; la feature funciona sin el.
- **Un panel en `/fabrica`** y **mandar el mensaje por Pedro** (fuera del spec del MVP).

## Nota de verificacion final

Al terminar: la suite entera verde. Sin `/redacta`/`/otra`, el chat es identico. Con `/redacta <hilo o intencion>`, sale un borrador en la voz de Pedro (verificado leyendo un borrador real, con el servidor y Ollama vivos -- que sea una respuesta al hilo o el texto pedido, con los habitos de Pedro presentes), corrido 100% local (nada a la nube). `/otra` da otra version del ultimo pedido.
