# El compositor aprende de lo que Pedro edita — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que Calipso aprenda la voz real de Pedro de los borradores que el edita: un gesto `/mia <texto>` guarda su version final como ejemplo fuerte, y el compositor la prioriza al redactar.

**Architecture:** Un almacen local propio (`calipso/compositor/ejemplos.py`, JSON en `CALIPSO_HOME`) guarda lo que Pedro trae con `/mia`. `voz.ejemplos_de_voz` gana un parametro `guardados` y los pone PRIMERO, rellenando con los mensajes de chat solo si faltan. `parse_directives` reconoce `/mia`, y una compuerta en `ws_chat` guarda y confirma sin correr un turno de chat.

**Tech Stack:** Python 3.14, pytest. El cliente no cambia. El almacen es JSON plano (como `chats.py`).

**Spec:** `docs/superpowers/specs/2026-09-03-compositor-aprende-de-mis-ediciones-design.md`

## Global Constraints

- **Calipso REDACTA, no manda.** `/mia` solo GUARDA texto que Pedro trae; Calipso no manda nada por el.
- **Los ejemplos de voz son de Pedro y locales.** El almacen vive en `CALIPSO_HOME`, no sale de la maquina, no se comparte entre proyectos. Ninguna llamada de red al guardar.
- **Sin `/mia` ni `/redacta`, el chat es identico a hoy.** La directiva nueva no cambia ningun turno normal.
- **El almacen no se corrompe.** `guardar` es append con dedup; un texto vacio no se guarda; un archivo ausente o corrupto se lee como lista vacia.
- **SIN EMOJIS** en codigo, tests ni mensajes al usuario. Comentarios y docstrings en espanol.
- **Mensajes de commit sin tildes ni ene**, sin emojis.
- **NUNCA importar `calipso` fuera de pytest.** Los tests que importan `calipso` corren bajo pytest (el `conftest.py` de la raiz fija `CALIPSO_HOME` a un temp antes de cualquier import). Los tests de este plan que tocan el almacen ademas hacen `monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))` para no pisarse entre si.
- **No reiniciar el servidor** (corre codigo viejo; el smoke en vivo queda anotado como seguimiento).
- La firma nueva de `ejemplos_de_voz` debe ser **compatible hacia atras**: las 5 pruebas actuales la llaman sin `guardados` y deben seguir verdes.

---

### Task 1: El almacen de ejemplos de voz

Crea el modulo que guarda y lee lo que Pedro trae con `/mia`, mas el helper puro que saca el texto del gesto (maneja el quirk de `parse_directives`). Todo puro y testeable, sin tocar el chat todavia.

**Files:**
- Create: `calipso/compositor/ejemplos.py`
- Test: `test_compositor_ejemplos.py`

**Interfaces:**
- Consumes: nada de tareas anteriores. Resuelve la ruta desde `CALIPSO_HOME` en tiempo de llamada (no al importar), igual que el patron de aislamiento de la suite.
- Produces:
  - `guardar(texto: str) -> None` — appendea `{"texto": <str>, "ts": <str>}` al JSON; dedup por texto; un texto vacio/espacios no se guarda.
  - `cargar() -> list[dict]` — la lista guardada (`[]` si el archivo no existe o esta corrupto).
  - `texto_del_gesto(clean: str) -> str` — el texto a guardar de un mensaje `/mia`; `""` si no hay nada real (mensaje vacio, o el quirk que deja `clean == "/mia"`).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `test_compositor_ejemplos.py`:

```python
# test_compositor_ejemplos.py
import json

import pytest


@pytest.fixture
def home(monkeypatch, tmp_path):
    # cada prueba con su propio CALIPSO_HOME: el almacen resuelve la ruta en
    # tiempo de llamada, asi que setear el env aca lo redirige al temp.
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    return tmp_path


def test_guardar_y_cargar(home):
    from calipso.compositor import ejemplos
    ejemplos.guardar("Hola Ana, nos vemos manana a las 10 entonces")
    got = ejemplos.cargar()
    assert len(got) == 1
    assert got[0]["texto"] == "Hola Ana, nos vemos manana a las 10 entonces"
    assert got[0]["ts"]                       # quedo estampado


def test_cargar_sin_archivo_es_lista_vacia(home):
    from calipso.compositor import ejemplos
    assert ejemplos.cargar() == []


def test_cargar_corrupto_es_lista_vacia(home):
    from calipso.compositor import ejemplos
    (home / "voz_ejemplos.json").write_text("{no es json", encoding="utf-8")
    assert ejemplos.cargar() == []


def test_dedup_no_duplica(home):
    from calipso.compositor import ejemplos
    ejemplos.guardar("cuento largo que Pedro escribio de verdad")
    ejemplos.guardar("cuento largo que Pedro escribio de verdad")
    assert len(ejemplos.cargar()) == 1


def test_texto_vacio_no_se_guarda(home):
    from calipso.compositor import ejemplos
    ejemplos.guardar("   ")
    assert ejemplos.cargar() == []


def test_no_hay_llamada_de_red_en_guardar(home):
    # el almacen es un archivo local: guardar escribe el JSON y nada mas.
    from calipso.compositor import ejemplos
    ejemplos.guardar("texto local que no debe salir a ningun lado nunca")
    data = json.loads((home / "voz_ejemplos.json").read_text(encoding="utf-8"))
    assert data[0]["texto"].startswith("texto local")


def test_texto_del_gesto_saca_el_texto():
    from calipso.compositor import ejemplos
    # parse_directives limpia el slash: "/mia hola" -> clean "hola"
    assert ejemplos.texto_del_gesto("respondele a ana que si") == "respondele a ana que si"


def test_texto_del_gesto_vacio_cuando_solo_slash():
    from calipso.compositor import ejemplos
    # quirk: si el mensaje era solo "/mia", clean cae al fallback "/mia"
    assert ejemplos.texto_del_gesto("/mia") == ""
    assert ejemplos.texto_del_gesto("   ") == ""
    assert ejemplos.texto_del_gesto("") == ""
```

- [ ] **Step 2: Correr las pruebas y verificar que fallan**

Run: `python -m pytest test_compositor_ejemplos.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'calipso.compositor.ejemplos'`

- [ ] **Step 3: Escribir la implementacion minima**

Crear `calipso/compositor/ejemplos.py`:

```python
"""Almacen local de ejemplos de la voz de Pedro: lo que el trae con /mia
(su version final editada de un borrador). Es su voz de verdad -- texto
escrito para una persona, no una orden a Calipso -- asi que el compositor
lo prioriza (ver voz.ejemplos_de_voz).

Local y del usuario: vive en CALIPSO_HOME, no sale de la maquina, no se
comparte entre proyectos. JSON plano, como chats.py.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib


def _archivo() -> pathlib.Path:
    # la ruta se resuelve en cada llamada (no al importar) para que los tests
    # puedan redirigir CALIPSO_HOME a un temp sin pelear con el orden de import.
    home = pathlib.Path(os.environ.get(
        "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
    return home / "voz_ejemplos.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def cargar() -> list[dict]:
    """La lista de ejemplos guardados. `[]` si no hay archivo o esta corrupto
    (el almacen no puede tumbar el chat por un JSON roto)."""
    ruta = _archivo()
    if not ruta.exists():
        return []
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def guardar(texto: str) -> None:
    """Appendea `texto` como ejemplo de la voz de Pedro. Un texto vacio no se
    guarda; un texto ya presente no se duplica (dedup por contenido)."""
    t = (texto or "").strip()
    if not t:
        return
    data = cargar()
    if any(e.get("texto") == t for e in data):
        return
    data.append({"texto": t, "ts": _now()})
    ruta = _archivo()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")


def texto_del_gesto(clean: str) -> str:
    """El texto a guardar de un mensaje /mia. Vacio si no hay nada real: el
    mensaje vacio, o el quirk de parse_directives que deja `clean` == "/mia"
    cuando el mensaje era solo el slash (el fallback `" ".join(keep) or
    message`)."""
    t = (clean or "").strip()
    if not t or t.lower() == "/mia":
        return ""
    return t
```

- [ ] **Step 4: Correr las pruebas y verificar que pasan**

Run: `python -m pytest test_compositor_ejemplos.py -v`
Expected: PASS (8 pruebas)

- [ ] **Step 5: Commit**

```bash
git add calipso/compositor/ejemplos.py test_compositor_ejemplos.py
git commit -m "feat(compositor): almacen local de ejemplos de voz (/mia) con dedup"
```

---

### Task 2: `voz` prioriza los guardados y `preparar_borrador` los recibe

`ejemplos_de_voz` gana el parametro `guardados` (los `/mia`) y los pone PRIMERO, rellenando con los mensajes de chat solo hasta `n`. `preparar_borrador` gana el mismo parametro y se lo pasa. Ambos cambios son la misma feature (la prioridad) y se revisan juntos.

**Files:**
- Modify: `calipso/compositor/voz.py:23-48` (la funcion `ejemplos_de_voz`)
- Modify: `calipso/compositor/redactor.py:52-56` (la funcion `preparar_borrador`)
- Test: `test_compositor_voz.py` (agregar pruebas; las 5 existentes quedan intactas)
- Test: `test_compositor_redactor.py` (agregar una prueba; las 4 existentes quedan intactas)

**Interfaces:**
- Consumes: `ejemplos.cargar()` de la Task 1 devuelve `list[dict]` con claves `"texto"` y `"ts"` — ese es el tipo que llega como `guardados`.
- Produces:
  - `ejemplos_de_voz(chats_data: dict, guardados: list = (), n: int = 6) -> list[str]` — los textos de `guardados` (mas recientes por `ts`) primero, luego los mensajes de chat, sin duplicados, tope `n`.
  - `preparar_borrador(pedido: str, chats_data: dict, guardados: list = ()) -> tuple[str, str]`.

- [ ] **Step 1: Escribir las pruebas que fallan (voz)**

Agregar al final de `test_compositor_voz.py`:

```python
def test_los_guardados_van_primero():
    # con /mia guardados, esos ejemplos van ANTES que los mensajes de chat.
    data = _chats([("user", "un mensaje de chat largo cualquiera")])
    guardados = [{"texto": "Hola Ana, confirmo la reunion del jueves", "ts": "2026-09-03T10:00:00"}]
    ej = ejemplos_de_voz(data, guardados)
    assert ej[0] == "Hola Ana, confirmo la reunion del jueves"
    assert "un mensaje de chat largo cualquiera" in ej   # rellena con el chat


def test_guardados_llenos_desplazan_al_chat():
    # con n o mas guardados, los mensajes de chat ya no entran.
    data = _chats([("user", "orden vieja de chat que no deberia entrar")])
    guardados = [{"texto": f"ejemplo real de voz numero {i} escrito por pedro", "ts": f"2026-09-03T10:0{i}:00"}
                 for i in range(3)]
    ej = ejemplos_de_voz(data, guardados, n=3)
    assert len(ej) == 3
    assert "orden vieja de chat que no deberia entrar" not in ej


def test_guardados_ordenados_por_ts():
    data = _chats()
    guardados = [
        {"texto": "el mas viejo de los guardados largo", "ts": "2026-01-01T10:00:00"},
        {"texto": "el mas nuevo de los guardados largo", "ts": "2026-09-03T10:00:00"}]
    ej = ejemplos_de_voz(data, guardados)
    assert ej[0] == "el mas nuevo de los guardados largo"


def test_sin_guardados_identico_a_hoy():
    data = _chats([("user", "che como andas todo bien por aca")])
    assert ejemplos_de_voz(data) == ejemplos_de_voz(data, [])
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `python -m pytest test_compositor_voz.py -v`
Expected: FAIL — `test_los_guardados_van_primero` y las nuevas fallan con `TypeError` (la firma actual no acepta `guardados`).

- [ ] **Step 3: Reescribir `ejemplos_de_voz` en `calipso/compositor/voz.py`**

Reemplazar la funcion `ejemplos_de_voz` (lineas 23-48) por:

```python
def ejemplos_de_voz(chats_data: dict, guardados: list = (), n: int = 6) -> list[str]:
    """Hasta `n` ejemplos de la voz de Pedro. Los `guardados` (lo que trajo
    con /mia -- su voz de verdad) van PRIMERO, mas recientes por `ts`; el
    resto se rellena con sus mensajes de chat (role=="user", recientes, sin
    triviales ni ordenes). Sin duplicados. Sin `guardados` se comporta igual
    que antes: solo mensajes de chat."""
    ej: list[str] = []
    vistos: set[str] = set()

    # 1) los /mia primero, mas recientes por ts (sort estable: los empates
    #    mantienen su orden de aparicion).
    priori = sorted(
        (g for g in (guardados or []) if _es_util(g.get("texto", ""))),
        key=lambda g: g.get("ts", ""), reverse=True)
    for g in priori:
        t = g["texto"].strip()
        if t not in vistos:
            vistos.add(t)
            ej.append(t)
            if len(ej) >= n:
                return ej

    # 2) rellenar con los mensajes reales de Pedro de los chats, por recencia
    #    real (ts descendente). un mensaje sin ts (dato viejo) usa "" y queda
    #    al final.
    mensajes: list[tuple[str, str]] = []
    for chat in (chats_data or {}).get("chats", {}).values():
        for m in chat.get("messages", []):
            if m.get("role") == "user" and _es_util(m.get("text", "")):
                mensajes.append((m.get("ts", ""), m["text"].strip()))
    mensajes.sort(key=lambda par: par[0], reverse=True)
    for _, texto in mensajes:
        if texto not in vistos:
            vistos.add(texto)
            ej.append(texto)
            if len(ej) >= n:
                break
    return ej
```

- [ ] **Step 4: Correr y verificar que pasan (voz)**

Run: `python -m pytest test_compositor_voz.py -v`
Expected: PASS (las 5 viejas + las 4 nuevas = 9)

- [ ] **Step 5: Escribir la prueba que falla (redactor)**

Agregar al final de `test_compositor_redactor.py`:

```python
def test_preparar_borrador_prioriza_los_guardados():
    data = {"active": None, "chats": {"c0": {"messages": [
        {"role": "user", "text": "orden de chat cualquiera larga", "ts": "1"}]}}}
    guardados = [{"texto": "Hola Ana, quedamos el jueves a las 10", "ts": "2026-09-03T10:00:00"}]
    system, user = preparar_borrador("decile a luis que si", data, guardados)
    assert "Hola Ana, quedamos el jueves a las 10" in system   # el /mia entro
    assert user == "decile a luis que si"
```

- [ ] **Step 6: Correr y verificar que falla**

Run: `python -m pytest test_compositor_redactor.py -v`
Expected: FAIL con `TypeError` (la firma actual no acepta un tercer argumento).

- [ ] **Step 7: Actualizar `preparar_borrador` en `calipso/compositor/redactor.py`**

Reemplazar la funcion `preparar_borrador` (lineas 52-56) por:

```python
def preparar_borrador(pedido: str, chats_data: dict,
                      guardados: list = ()) -> tuple[str, str]:
    """Junta los ejemplos de voz de Pedro -- los que trajo con /mia
    (`guardados`) primero, luego sus mensajes de chat -- y arma el (system,
    user) para el borrador. La cara testeable de lo que hace el chat en
    /redacta."""
    ejemplos = voz.ejemplos_de_voz(chats_data, guardados)
    return construir_prompt(pedido, ejemplos)
```

- [ ] **Step 8: Correr y verificar que pasa (redactor)**

Run: `python -m pytest test_compositor_redactor.py test_compositor_voz.py -v`
Expected: PASS (5 redactor + 9 voz)

- [ ] **Step 9: Commit**

```bash
git add calipso/compositor/voz.py calipso/compositor/redactor.py test_compositor_voz.py test_compositor_redactor.py
git commit -m "feat(compositor): voz prioriza los ejemplos guardados con /mia"
```

---

### Task 3: El gesto `/mia` en `parse_directives`

`parse_directives` reconoce `/mia` como directiva booleana (como `/redacta`), lo saca de `clean` y deja el resto del mensaje.

**Files:**
- Modify: `calipso/capabilities.py:201-204` (el dict `out`) y `:218-224` (la cadena de `elif` de tokens)
- Test: `test_capabilities.py` (script; agregar checks en `main()`)

**Interfaces:**
- Consumes: nada.
- Produces: `parse_directives(msg)["mia"]` es `True` cuando el mensaje trae `/mia`, y `clean` queda sin el slash.

- [ ] **Step 1: Agregar los checks que fallan en `test_capabilities.py`**

En `main()`, despues del bloque de `/otra` (tras la linea `check("sin /otra -> otra False", ...)`), agregar:

```python
    d8 = cap.parse_directives("/mia respondele a ana que confirmo")
    check("parse /mia -> mia True", d8["mia"] is True)
    check("parse /mia limpia el slash", "/mia" not in d8["clean"])
    check("parse /mia conserva el resto", "respondele a ana" in d8["clean"])
    check("sin /mia -> mia False", cap.parse_directives("hola")["mia"] is False)
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `python test_capabilities.py`
Expected: sale con codigo 1 e imprime `FALLARON:` incluyendo `parse /mia -> mia True` (la clave `"mia"` todavia no existe -> `KeyError` o check en rojo).

- [ ] **Step 3: Agregar la directiva en `calipso/capabilities.py`**

En el dict `out` de `parse_directives` (dentro de la linea que arranca `out = {"clean": message, ...`), agregar `"mia": False` junto a `"redacta"` y `"otra"`:

```python
    out = {"clean": message, "effort": None, "force_model": None,
           "force_route": None, "help": False, "force_web": False,
           "force_team": False, "nube": False, "redacta": False,
           "otra": False, "mia": False}
```

Y en la cadena de `elif` que clasifica cada token, agregar el caso `/mia` junto a `/redacta` y `/otra`:

```python
        elif tl == "/redacta":
            out["redacta"] = True
        elif tl == "/otra":
            out["otra"] = True
        elif tl == "/mia":
            out["mia"] = True
```

- [ ] **Step 4: Correr y verificar que pasa**

Run: `python test_capabilities.py`
Expected: sale con codigo 0 e imprime `OK: ruteo a nivel de modelo + intensidad + descubrimiento`

- [ ] **Step 5: Commit**

```bash
git add calipso/capabilities.py test_capabilities.py
git commit -m "feat(compositor): parse_directives reconoce el gesto /mia"
```

---

### Task 4: Cablear `/mia` en `ws_chat` y pasar los guardados a `/redacta`

La compuerta `/mia` en `ws_chat` guarda el texto y confirma sin correr un turno (no responde, no rutea, no cobra, no toca historial ni memoria). Y la compuerta `/redacta` pasa a alimentarse tambien de los guardados. El nucleo del gesto (`texto_del_gesto` + `guardar` + `cargar` + `preparar_borrador`) se prueba a nivel de modulo; la compuerta de websocket se verifica leyendo, con el import del server y la suite completa, y un smoke en vivo anotado como seguimiento.

**Files:**
- Modify: `calipso/server.py:60` (imports del compositor)
- Modify: `calipso/server.py:2467-2493` (agregar la compuerta `/mia` antes de la de `/redacta`; actualizar la llamada a `preparar_borrador`)
- Test: `test_compositor_flujo.py` (nuevo; el flujo gesto -> almacen -> borrador, sin websocket)

**Interfaces:**
- Consumes: `compositor_ejemplos.texto_del_gesto`, `.guardar`, `.cargar` (Task 1); `compositor_redactor.preparar_borrador(pedido, chats_data, guardados)` (Task 2); `directives["mia"]` (Task 3).
- Produces: el comportamiento de `/mia` en el chat. Nada que consuma otra tarea.

- [ ] **Step 1: Escribir la prueba de flujo que falla**

Crear `test_compositor_flujo.py`:

```python
# test_compositor_flujo.py -- el lazo completo del gesto, sin el websocket:
# Pedro trae su version final con /mia, y un /redacta posterior la usa.
import pytest


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    return tmp_path


def test_mia_alimenta_el_borrador(home):
    from calipso.compositor import ejemplos, redactor
    # el chat sacaria el texto del gesto y lo guardaria:
    texto = ejemplos.texto_del_gesto("Hola Ana, quedamos manana a las 10 entonces")
    assert texto
    ejemplos.guardar(texto)
    # un /redacta posterior carga los guardados y los mete en el system:
    system, user = redactor.preparar_borrador(
        "decile a luis que confirmo", {"active": None, "chats": {}},
        ejemplos.cargar())
    assert "Hola Ana, quedamos manana a las 10 entonces" in system
    assert user == "decile a luis que confirmo"


def test_mia_solo_slash_no_guarda_nada(home):
    from calipso.compositor import ejemplos
    texto = ejemplos.texto_del_gesto("/mia")   # el quirk del fallback
    assert texto == ""
    # el chat, al ver texto vacio, no llama a guardar: el almacen sigue vacio.
    assert ejemplos.cargar() == []
```

- [ ] **Step 2: Correr y verificar que pasa**

Run: `python -m pytest test_compositor_flujo.py -v`
Expected: PASS (Tasks 1 y 2 ya dejaron todo lo que este flujo usa). Si falla, faltan esas tareas -- no avanzar.

- [ ] **Step 3: Importar el almacen en `calipso/server.py`**

Junto al import del redactor (linea 60, `from calipso.compositor import redactor as compositor_redactor  # noqa: E402`), agregar:

```python
from calipso.compositor import ejemplos as compositor_ejemplos  # noqa: E402
```

- [ ] **Step 4: Agregar la compuerta `/mia` en `ws_chat`**

En `ws_chat`, JUSTO ANTES del bloque `if directives.get("redacta") or directives.get("otra"):` (linea ~2473), insertar:

```python
            # /mia: Pedro trae de vuelta su version FINAL editada de un
            # borrador. Calipso la GUARDA como ejemplo fuerte de su voz y no
            # hace nada mas: no responde, no rutea, no cobra, no toca historial
            # ni memoria. Asi el compositor aprende su voz real de lo que el
            # corrige (ver calipso/compositor/ejemplos.py y voz.ejemplos_de_voz).
            if directives.get("mia"):
                texto_mia = compositor_ejemplos.texto_del_gesto(chat_msg)
                if not texto_mia:
                    await ws.send_json({"type": "error",
                                        "text": "pega tu version despues de /mia"})
                    await ws.send_json({"type": "done"})
                    continue
                compositor_ejemplos.guardar(texto_mia)
                await ws.send_json({"type": "chunk",
                                    "text": "guardado como ejemplo de tu voz"})
                await ws.send_json({"type": "done"})
                continue
```

- [ ] **Step 5: Alimentar `/redacta` con los guardados**

En el mismo `ws_chat`, en la compuerta de `/redacta`, cambiar la llamada a `preparar_borrador` (linea ~2492) para pasar los guardados:

Antes:
```python
                system_b, user_b = compositor_redactor.preparar_borrador(
                    pedido, chats._load())
```
Despues:
```python
                system_b, user_b = compositor_redactor.preparar_borrador(
                    pedido, chats._load(), compositor_ejemplos.cargar())
```

- [ ] **Step 6: Verificar que el server importa y que la suite sigue verde**

Run: `python -c "import calipso.server"`
Expected: sin error (sin `SyntaxError` ni `ImportError`).

Run: `python -m pytest test_compositor_flujo.py test_compositor_ejemplos.py test_compositor_voz.py test_compositor_redactor.py -v && python test_capabilities.py`
Expected: PASS todo + `python test_capabilities.py` sale 0.

- [ ] **Step 7: Commit**

```bash
git add calipso/server.py test_compositor_flujo.py
git commit -m "feat(compositor): gesto /mia en el chat guarda la voz y /redacta la usa"
```

---

## Notas de verificacion (fuera de las tareas)

- **Suite completa antes de cerrar la rama:** `python -m pytest -q` (mas los scripts que la suite corra por su cuenta). Debe quedar todo verde; sin `/mia` ni `/redacta` el chat es identico a hoy.
- **Smoke en vivo (seguimiento, NO en este plan porque no se reinicia el server):** con el server y Ollama vivos, `/mia <texto real de Pedro>` un par de veces y luego `/redacta <hilo>` -> el borrador deberia sonar mas a Pedro que el neutro de arranque. Igual que el smoke de `/redacta`, queda anotado hasta que se pueda reiniciar con codigo nuevo.

## Self-Review

**1. Cobertura del spec:**
- Seccion 3 (gesto `/mia`): Task 3 (parse) + Task 4 (compuerta que guarda/confirma, `/mia` solo avisa). OK.
- Seccion 4 (almacen `voz_ejemplos.json`, `guardar`/`cargar`, dedup, no corrupto): Task 1. OK.
- Seccion 5 (voz prioriza, rellena, firma nueva; `preparar_borrador` recibe guardados): Task 2. OK.
- Seccion 6 (invariantes): local (Task 1, prueba de red), redacta-no-manda (Task 4 no manda nada), sin /mia identico (compat hacia atras, Task 2/3), no se corrompe (Task 1). OK.
- Seccion 7 (lo que NO hace): ninguna tarea agrega tag por registro, /mias, UI inline, captura automatica ni recuperacion semantica. OK.
- Seccion 8 (como se verifica): cada punto mapea a una prueba de las Tasks 1-4 + el smoke anotado. OK.

**2. Placeholders:** sin TBD/TODO; todo paso de codigo trae el codigo real.

**3. Consistencia de tipos:** `guardados` es `list[dict]` con `"texto"`/`"ts"` en Task 1 (`cargar`), Task 2 (`ejemplos_de_voz`, `preparar_borrador`) y Task 4 (la llamada del server). `texto_del_gesto(clean) -> str` igual en Task 1, la prueba de flujo (Task 4) y la compuerta (Task 4). La firma `ejemplos_de_voz(chats_data, guardados=(), n=6)` es compatible con las llamadas viejas (que usan `n=` por palabra). OK.
