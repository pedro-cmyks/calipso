# El ruteo vivo, Fase 1 -- plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar la fuga de privacidad del chat: que la ruta "local" ejecute en el Ollama que ya corre, que lo privado sin local falle cerrado, que no se escale a API paga en silencio, y que los tres libros (ruteo, UI, costos) dejen de mentir.

**Architecture:** Todo el arreglo vive en las costuras que la corte identifico, sin tocar el jefe de un departamento (que ya usa Ollama). El streaming desde Ollama ya existe (`dispatch._ollama_chat_chunks`); la Fase 1 lo cablea al chat, saca dos `local_up = False` hardcodeados, agrega un filtro de API forzada en `_decide`, un corte de privacidad en `_should_orchestrate`, y corrige el cobro y los metadatos de la ruta local.

**Tech Stack:** Python 3.14, FastAPI, pytest. Ollama local (`qwen2.5:7b`). Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-02-ruteo-vivo-y-privacidad-design.md` (Fase 1; la Fase 2 -- juez + redaccion -- NO entra en este plan).

## Global Constraints

- **SIN EMOJIS.** Codigo, comentarios, texto que ve Pedro, mensajes de commit.
- **Nombres, comentarios y docstrings en ESPANOL.** Commits **sin tildes ni enie**.
- **NUNCA importar `calipso` fuera de pytest.** **HAY UN SERVIDOR CORRIENDO: no pararlo, no reiniciarlo.**
- **`git add` con rutas explicitas.**
- **Ningun dato marcado privado sale de la maquina.** Es la regla que todo el plan sirve: en la Fase 1 significa local-o-nada.
- **Ninguna ruta a API paga se toma sin gesto explicito de Pedro.**
- **El jefe de un departamento no se toca** (`_pensar_local`, `_run_backend_text` route local ya usan Ollama).
- **Antes de escribir un test, ABRIR el archivo de tests y verificar sus convenciones.** Si el brief no calza con el archivo real, **el brief esta mal**.
- **Interprete:** `.venv/bin/python`. Tests: `.venv/bin/python -m pytest <archivo> -q` desde `/var/home/pedro/calipso`.

---

## Contexto verificado (leer antes de la Tarea 1)

Nueve hechos, cada uno leido del codigo esta sesion:

1. **La fuga central.** `_local_via_sub` (`server.py:2006-2019`), la ejecucion de la ruta "local" en el chat streaming, corre `subprocess.run(["claude", "-p", user_msg])`. Tira el `system` (el closure solo usa `user_msg`) y no pasa `--model`. Devuelve el nombre `"claude"`.
2. **`local_up` esta hardcodeado en dos lugares:** `server.py:1435` y `:1782`, los dos `local_up = False  # sin Ollama`.
3. **El streamer de Ollama ya existe:** `dispatch._ollama_chat_chunks(url, payload, usage)` (`dispatch.py:450`), generador que transmite NDJSON. Y `_ollama_text_chunks` (`:426`).
4. **El patron de payload de Ollama** ya esta en `_chunks_for` para la rama `api` (`server.py:1993-2003`): `messages = [{"role":"system",...}] + history + [{"role":"user",...}]`. El de Ollama chat es el mismo formato de `messages`.
5. **`_http_up(url)`** (`server.py:1122`) es el probe HTTP que ya se usa para la API. Sirve para Ollama contra `dispatch.CONFIG["local"]["base_url"]`.
6. **`_decide` filtra por `force_route`** (`server.py:1483-1484`): `ranked = [r for r in ranked if r["route"] == d["force_route"]] or ranked`. Pero si NO hay `force_route`, un `route:"api"` puede ganar igual. Y el else de ranking vacio (`:1511`) fuerza `route:"local"`.
7. **`_should_orchestrate`** (`server.py:1520`, llamado en `:2475`) no mira `features.get("private")`.
8. **`_cobrar_turno`** (`server.py:5925`) cobra la local como una unidad de suscripcion claude: `cliente = "claude" if route == "local" else client` (`:5954`), con el comentario "la local, que es una suscripcion disfrazada". Tras el arreglo, la local es Ollama de verdad -- gratis -- y esa linea pasa a ser falsa.
9. **El CLI muerto** `dispatch.py` tiene `decide_by_rules`/`route`/`decide_by_model` que el chat NO usa (grep confirmado: nada fuera de `dispatch.py` importa `dispatch.route`). Su docstring y la rama PRIVATE prometen "privado -> local" y "suscripcion local sin API", falso. `SAFE_FALLBACK = "subscription"` definido y sin usar.

## Las cinco decisiones que este plan toma

- **P1 -- la ruta local ejecuta Ollama, y si Ollama no responde FALLA CERRADO, nunca claude.** El unico modo de llegar a `_chunks_for("local")` con Ollama caido es el fallback de ranking vacio (todo lo demas tambien esta caido), asi que degradar a claude ahi no tiene sentido ni siquiera para lo no-privado. Falla cerrado con un mensaje claro.

- **P2 -- `local_up` lee la salud real de Ollama.** Deja de ser una constante. Un Ollama vivo se ve vivo; el scorer vuelve a poder elegir local con fundamento.

- **P3 -- API paga se cae del ranking salvo `force_route == "api"`.** El freno deja de depender de la penalizacion blanda de costo. Si no queda candidato no-API y el usuario no forzo, el sistema lo dice en vez de gastar.

- **P4 -- un prompt privado no orquesta.** `_should_orchestrate` devuelve False si `features.get("private")`. Un privado tiene un solo camino: local o fallo cerrado.

- **P5 -- la local es gratis y honesta.** `_cobrar_turno` deja de cobrar la local como claude; el meta y los costos reportan el modelo que de verdad contesto.

---

## Estructura de archivos

| Archivo | Responsabilidad en Fase 1 |
|---|---|
| `calipso/server.py` | `_chunks_for` local (T1), `local_up` (T2), `_decide` API (T3), `_should_orchestrate` (T4), `_cobrar_turno` (T5) |
| `dispatch.py` | los comentarios falsos del CLI muerto (T6) |
| `test_plantel_server.py` (o el archivo de tests del server que corresponda) | los tests de cada tarea |

---

### Task 1: La ruta local ejecuta en Ollama, o falla cerrado

**Files:**
- Modify: `calipso/server.py`, `_chunks_for` (la rama local, `:2005-2019`)
- Test: `test_plantel_server.py`

**Interfaces:**
- Consumes: `dispatch._ollama_chat_chunks`, `dispatch.CONFIG["local"]`, `_http_up`.
- Produces: `_chunks_for("local", ...)` devuelve `(generador_ollama, modelo_local)` cuando Ollama responde, y un generador de un solo mensaje de fallo cerrado -- **nunca claude** -- cuando no.

- [ ] **Step 1: Escribir los tests que fallan**

En `test_plantel_server.py`. **Abri el archivo y usa su convencion** (ya monkeypatchea `dispatch` y `subprocess`).

```python
def test_la_ruta_local_del_chat_ejecuta_en_ollama_no_en_claude(monkeypatch):
    """La fuga central: la ruta 'local' corria `claude -p`, mandando el dato
    a Anthropic bajo la etiqueta 'local'. Tiene que transmitir desde el
    Ollama que ya corre."""
    llamado = {}

    def ollama_espia(url, payload, usage=None):
        llamado["url"] = url
        llamado["messages"] = payload.get("messages")
        yield "respuesta de ollama"

    def subprocess_prohibido(*a, **k):
        raise AssertionError("la ruta local NO puede llamar a subprocess (claude)")

    monkeypatch.setattr(srv.dispatch, "_ollama_chat_chunks", ollama_espia)
    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: True)
    monkeypatch.setattr(srv.subprocess, "run", subprocess_prohibido)

    gen, modelo = srv._chunks_for("local", "SOY EL SISTEMA", "hola", {},
                                  chat_id=None)
    salida = "".join(gen)
    assert "respuesta de ollama" in salida
    assert modelo == srv.dispatch.CONFIG["local"]["model"]
    # el system viaja: el bug viejo lo tiraba
    assert any(m.get("role") == "system" and "SOY EL SISTEMA" in m.get("content", "")
               for m in llamado["messages"])


def test_la_ruta_local_con_ollama_caido_falla_cerrado_y_no_llama_claude(monkeypatch):
    """Fallo cerrado: si Ollama no responde, la ruta local NO degrada a
    claude. Da un mensaje claro y no ejecuta nada remoto."""
    def subprocess_prohibido(*a, **k):
        raise AssertionError("Ollama caido no puede caer a claude")

    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: False)
    monkeypatch.setattr(srv.subprocess, "run", subprocess_prohibido)

    gen, modelo = srv._chunks_for("local", "sys", "hola", {}, chat_id=None)
    salida = "".join(gen)
    assert "no" in salida.lower() and "local" in salida.lower()
    assert modelo != "claude"
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_plantel_server.py -q -k "ejecuta_en_ollama or falla_cerrado"`
Expected: FAIL -- el primero por el AssertionError de subprocess (hoy llama claude); el segundo igual.

- [ ] **Step 3: Reescribir la rama local de `_chunks_for`**

Reemplazar el bloque desde el comentario `# local no disponible (sin Ollama)` hasta el `return _local_via_sub(), "claude"`:

```python
    # LA RUTA LOCAL ES LOCAL: transmite desde el Ollama que ya corre, con el
    # mismo `messages` que la rama api de arriba. El bug viejo corria
    # `claude -p` -- mandaba el dato privado a Anthropic bajo la etiqueta
    # 'local', tiraba el system y no pasaba el modelo. Ver la fuga central en
    # el spec del 2026-09-02.
    cfg = dispatch.CONFIG["local"]
    mdl = model or cfg["model"]
    if not _http_up(cfg["base_url"]):
        # FALLO CERRADO: lo unico que llega aca con Ollama caido es el
        # fallback de ranking vacio (todo lo demas tambien esta caido), asi
        # que degradar a claude no protege a nadie y rompe la promesa de que
        # lo privado no sale de la maquina. Se para y se dice.
        def _local_caido():
            yield ("[Calipso] no puedo contestar esto con el modelo local: "
                   "Ollama no esta disponible. No lo mando a la nube.")
        return _local_caido(), mdl
    messages = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_msg})
    payload = {"model": mdl, "messages": messages, "stream": True}
    return dispatch._ollama_chat_chunks(cfg["base_url"], payload, usage), mdl
```

**Verifica antes de escribir** que `dispatch._ollama_chat_chunks` acepta ese
payload (modelo, messages, stream) y esa firma `(url, payload, usage)`. Si la
url que espera es distinta de `base_url` (por ejemplo un endpoint `/api/chat`),
usa la que el generador espera -- el brief no adivina el sufijo exacto.

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_server.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py test_plantel_server.py
git commit -m "fix(ruteo): la ruta local del chat ejecuta en Ollama, o falla cerrado"
```

---

### Task 2: `local_up` lee la salud real de Ollama

**Files:**
- Modify: `calipso/server.py:1435` y `:1782` (los dos `local_up = False`)
- Test: `test_plantel_server.py`

**Interfaces:**
- Consumes: `_http_up`, `dispatch.CONFIG["local"]`.
- Produces: `local_up` refleja si Ollama responde. La disponibilidad de los backends `local:*` en el scorer pasa a ser real.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_local_up_refleja_la_salud_real_de_ollama(monkeypatch):
    """Estaba hardcodeado en False 'sin Ollama', pero Ollama corre. Con la
    salud real, un Ollama vivo se ve vivo y el scorer puede elegir local."""
    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: True)
    monkeypatch.setattr(srv, "_http_up_cached", lambda url: True)
    h = srv._connector_health(use_cache=False)
    assert h["local"]["ready"] is True

    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: False)
    h2 = srv._connector_health(use_cache=False)
    assert h2["local"]["ready"] is False
```

**Verifica** como `_connector_health` arma la clave `local` a partir de
`local_up` -- el assert de arriba asume `h["local"]["ready"]`; si la forma real
es otra, ajusta el assert al shape verdadero (leelo, no lo adivines).

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python -m pytest test_plantel_server.py -q -k local_up`
Expected: FAIL (hoy `ready` es siempre False)

- [ ] **Step 3: Los dos `local_up`**

En `server.py:1435` y `:1782`, reemplazar `local_up = False  # sin Ollama` por:

```python
    # la salud REAL de Ollama, no una constante: el chat ya puede ejecutar
    # local (ver la ruta local de `_chunks_for`), asi que apagarlo a mano
    # dejaba muerta la unica boca que mantiene lo privado en la maquina.
    local_up = (_http_up_cached if use_cache else _http_up)(
        dispatch.CONFIG["local"]["base_url"])
```

**Ojo:** el de `:1782` puede estar en una funcion sin el parametro `use_cache`.
Verifica el contexto de cada uno y usa el probe que corresponda a cada sitio
(el `:1435` esta en `_connector_health(use_cache=...)`; el otro puede ser un
diagnostico distinto -- leelo y adapta, sin inventar un `use_cache` que no
exista ahi).

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_server.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py test_plantel_server.py
git commit -m "fix(ruteo): local_up lee la salud real de Ollama, no una constante"
```

---

### Task 3: No escalar a API paga en silencio

**Files:**
- Modify: `calipso/server.py`, `_decide` (despues del bloque de `force_route`, cerca de `:1484`)
- Test: `test_plantel_server.py`

**Interfaces:**
- Consumes: `capabilities.choose`, las directivas (`d.get("force_route")`).
- Produces: un `route:"api"` no puede ser el veredicto salvo que `d["force_route"] == "api"`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
def test_la_api_paga_no_gana_sin_gesto_explicito(monkeypatch):
    """El freno de API forzada solo vivia en el CLI muerto. En el chat vivo,
    si las suscripciones caen y el proxy esta arriba, la API paga ganaba en
    silencio."""
    # un ranking donde la API queda primera (suscripciones no disponibles)
    ranking = [{"key": "api:deepseek-chat", "route": "api", "client": None,
                "model": "deepseek-chat", "persona": "Confucio", "tier": "mid",
                "score": 0.5}]
    monkeypatch.setattr(srv.capabilities, "choose", lambda *a, **k: list(ranking))
    verdict, *_ = srv._decide("analiza esto", ...)  # completa la firma real
    assert verdict["route"] != "api"


def test_la_api_paga_si_gana_cuando_pedro_la_fuerza(monkeypatch):
    ranking = [{"key": "api:deepseek-chat", "route": "api", "client": None,
                "model": "deepseek-chat", "persona": "Confucio", "tier": "mid",
                "score": 0.5}]
    monkeypatch.setattr(srv.capabilities, "choose", lambda *a, **k: list(ranking))
    # con /api o el equivalente en directivas: force_route == "api"
    verdict, *_ = srv._decide("/api analiza esto", ...)
    assert verdict["route"] == "api"
```

**Los `...` son deliberados:** la firma real de `_decide` y como se arma
`force_route` desde una directiva `/api` salen de leer `_decide` y el parser de
directivas en `server.py`. Completa el test con la forma real; lo que fija son
los dos asserts.

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_plantel_server.py -q -k "api_paga"`
Expected: FAIL el primero (hoy la API gana), PASS el segundo si ya se fuerza bien.

- [ ] **Step 3: El filtro en `_decide`**

Justo despues del bloque de `force_route` (`server.py:1483-1484`), antes del de
`force_model`:

```python
    # No escalar a API paga en silencio: un veredicto de API solo vale si
    # Pedro lo forzo. El freno viejo (`api_only_when_forced`) solo vivia en
    # el CLI muerto `dispatch.py` y nunca corria en el chat, asi que si las
    # suscripciones caian y el proxy pago estaba arriba, la API ganaba sola.
    if d.get("force_route") != "api":
        ranked = [r for r in ranked if r["route"] != "api"]
```

Con esto, si solo quedaban candidatos de API y Pedro no forzo, `ranked` queda
vacio y el else de `:1511` fuerza `route:"local"` -- que intenta Ollama y, si
esta caido, falla cerrado (Tarea 1). Nunca API sin gesto.

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_server.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py test_plantel_server.py
git commit -m "fix(ruteo): la API paga no gana sin que Pedro la fuerce"
```

---

### Task 4: Un prompt privado no orquesta

**Files:**
- Modify: `calipso/server.py`, `_should_orchestrate` (`:1520`)
- Test: `test_plantel_server.py`

**Interfaces:**
- Consumes: `features` (con la clave `private`).
- Produces: `_should_orchestrate` devuelve `False` si `features.get("private")`.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_un_prompt_privado_no_dispara_orquestacion():
    """La orquestacion reparte a backends de suscripcion/API sin pasar por el
    filtro `private_ok`. Un prompt privado no puede tomar ese camino."""
    features = {"type": "code", "complexity": 4, "private": True}
    assert srv._should_orchestrate(features, {}, "un mensaje largo y complejo "
                                    "con muchas palabras para pasar el umbral") is False
    # sin privado, el mismo prompt SI orquesta (no romper el caso normal)
    features2 = {"type": "code", "complexity": 4, "private": False}
    assert srv._should_orchestrate(features2, {}, "un mensaje largo y complejo "
                                   "con muchas palabras para pasar el umbral") is True
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python -m pytest test_plantel_server.py -q -k orquestacion`
Expected: FAIL (hoy el privado orquesta)

- [ ] **Step 3: El corte**

Al principio de `_should_orchestrate`, despues del `if directives.get("force_team")`:

```python
    if features.get("private"):
        # un prompt privado tiene un solo camino -- local o fallo cerrado --
        # y la orquestacion lo repartiria a backends que no son private_ok.
        # El filtro de privacidad no puede tener una puerta de atras.
        return False
```

**Ojo con el orden:** va despues de `force_team` a proposito? No. Un `/team`
explicito sobre un prompt privado tambien tiene que respetar la privacidad, asi
que este corte va **antes** que `force_team`. Ponelo como la primera linea del
cuerpo.

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_server.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py test_plantel_server.py
git commit -m "fix(ruteo): un prompt privado no dispara orquestacion"
```

---

### Task 5: La local es gratis y honesta

**Files:**
- Modify: `calipso/server.py`, `_cobrar_turno` (`:5925`, la linea `:5954`)
- Test: `test_plantel_server.py` o el archivo de tests de economia del server que corresponda

**Interfaces:**
- Consumes: nada nuevo.
- Produces: `_cobrar_turno(route="local", ...)` no debita una unidad de suscripcion claude, porque la local ahora es Ollama de verdad -- gratis.

- [ ] **Step 1: Escribir el test que falla**

**Abri el archivo y verifica** como se ejercita hoy `_cobrar_turno` (que fixture
de economia usa, si hay uno). El test tiene que fijar que un turno `route="local"`
no cobra una unidad de suscripcion:

```python
def test_un_turno_local_no_cobra_suscripcion_claude(...):
    """La local dejo de ser 'una suscripcion disfrazada': ahora es Ollama, y
    Ollama no cobra. Cobrarla como claude debita capacidad que no se uso."""
    # con la economia sembrada del fixture, cobrar un turno local y afirmar
    # que NO se debito una unidad de suscripcion de claude
    ...
```

Completa el cuerpo con el fixture real. Lo que fija es que la rama local no
termine cobrando `cliente = "claude"`.

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python -m pytest <archivo> -q -k local_no_cobra`
Expected: FAIL (hoy cobra como claude)

- [ ] **Step 3: El arreglo**

En `_cobrar_turno`, la linea `:5954` (`cliente = "claude" if route == "local" else client`)
y su docstring. La local deja de mapear a claude:

```python
            # la local ya no es "una suscripcion disfrazada": es Ollama, y
            # Ollama no cobra. Un turno local no debita ninguna unidad de
            # suscripcion. La rama de cobro de suscripcion es solo para
            # `route == "subscription"`.
            if route == "local":
                return 0
            cliente = client
```

**Verifica el flujo real** de la funcion: el objetivo es que un turno local
devuelva 0 sin tocar el libro de suscripcion. Adapta la forma exacta al codigo
de `_cobrar_turno` -- puede requerir mover el corte mas arriba. Y actualiza el
docstring, que hoy dice "la local, que es una suscripcion disfrazada".

- [ ] **Step 4: El meta y los costos ya dicen la verdad, verificarlo**

Con la Tarea 1, `_chunks_for("local")` devuelve el modelo real de Ollama (o el
fallo cerrado), asi que el meta que la UI ve (`server.py:1502`, `:1511`) ya no
puede reportar `qwen2.5:7b` sobre una respuesta de claude -- porque la ruta local
ya no ejecuta claude. Agrega un test que fije que un turno local reporta el
modelo local y registra costo cero, si el archivo tiene un camino para
inspeccionar el meta.

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/python -m pytest <archivos tocados> -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add calipso/server.py <archivo de test>
git commit -m "fix(economia): un turno local es gratis, no una suscripcion claude"
```

---

### Task 6: El CLI muerto deja de mentir

**Files:**
- Modify: `dispatch.py` (docstring del modulo `:1-18`, `decide_by_rules` docstring y la rama PRIVATE, `SAFE_FALLBACK` `:84`)
- Test: ninguno de comportamiento (el CLI no lo cubre la suite); es correccion de comentarios

**Interfaces:**
- Consumes/Produces: nada. Es limpieza de comentarios falsos.

**Por que entra en la Fase 1:** el CLI muerto no fuga porque nadie lo llama,
pero su comentario `why: "suscripcion local sin API"` sobre la rama PRIVATE y su
docstring "privado -> local" son la misma clase de mentira sobre privacidad que
la Fase 1 corrige en el chat. Un comentario falso engaña al proximo que lo lea.

- [ ] **Step 1: Corregir la docstring del modulo**

En `dispatch.py:1-18`, la docstring que promete "tres bocas" y un "clasificador
LOCAL (Ollama) que devuelve JSON": decir la verdad de hoy -- que `decide_by_model`
es un stub que siempre devuelve suscripcion, que no hay boca local viva en este
CLI, y que el ruteo del chat vivo NO pasa por aca (vive en `capabilities.choose`).

- [ ] **Step 2: Corregir `decide_by_rules`**

Su docstring declara una precedencia "trivial/privado -> local" que el codigo no
cumple (todo va a suscripcion). Reescribir la docstring para que describa el
orden real de los `if`. Y el `why` de la rama PRIVATE (`"datos privados/sensibles;
suscripcion local sin API"`) deja de decir "local": suscripcion manda a la nube.

- [ ] **Step 3: `SAFE_FALLBACK`**

`SAFE_FALLBACK = "subscription"` (`:84`) esta definido, sin usar, y con el valor
contrario a su comentario. Borralo (grep confirma cero usos) o, si algun dia se
cablea, dejalo en `"local"` con una nota de que no se usa todavia. Preferir
borrarlo.

- [ ] **Step 4: Verificar que no rompio imports**

Run: `.venv/bin/python -c "import ast; ast.parse(open('dispatch.py').read())" && echo "parsea"`
Y correr la suite entera para confirmar que nada importaba `SAFE_FALLBACK`:
`.venv/bin/python -m pytest -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dispatch.py
git commit -m "docs(dispatch): el CLI muerto deja de prometer privacidad que no cumple"
```

---

## Lo que esta Fase NO hace

- **El juez de privacidad y la redaccion** (Fase 2 del spec, secciones 8-10). Este plan cierra la fuga; la Fase 2 le agrega a un prompt privado la opcion de recibir ayuda de la nube con los datos tapados. No arranca hasta que la Fase 1 aterrice y hasta medir que un modelo local sabe marcar datos sensibles.
- **Ampliar la regex de privacidad.** Sigue siendo la de hoy (debil). La Fase 2 la reemplaza por el juez; la Fase 1 solo arregla que lo que SI se marca privado no se fugue.
- **La deteccion de privado en adjuntos.** Es de la Fase 2.
- **Tocar el jefe de un departamento.** Ya usa Ollama; no se toca.

## Nota de verificacion final

Al terminar las seis tareas, la suite entera tiene que quedar verde, y un
chequeo que ningun test unitario hace: con el servidor levantado y Ollama vivo,
un mensaje que dispare la regex de privacidad tiene que contestar **desde
Ollama** -- verificado espiando el subproceso o el trafico, no la pantalla -- y
con Ollama apagado, tiene que **fallar cerrado** sin tocar la nube. Ese par es
la prueba de que las tres reglas de Pedro se cumplen.
