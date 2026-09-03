# El jefe aprende de mis reacciones — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la mesa capture las palabras de Pedro al reaccionar (descartar / no mas / financiar), las guarde en un registro durable por departamento, el jefe las lea en cada decision, y un "no mas" frene de verdad el tema via un chequeo determinista por `clave`.

**Architecture:** Un almacen puro nuevo (`calipso/plantel/reacciones.py`) guarda las reacciones al lado de la carta (`memoria/departamento/<clave>/reacciones.json`), con escritura atomica y lectura que falla cerrado ante corrupto. Los endpoints de la mesa anotan al reaccionar. `jefe.tic` lee el registro (falla cerrado), se lo pasa a `decision.prompt` (que reemplaza la linea semanal `descartadas_semana`) y lo usa para el piso: si la `clave` de una propuesta fue vetada con "no mas" en ese departamento, se cae antes del bus. La UI de `/fabrica` gana un campo de texto y el boton "no mas".

**Tech Stack:** Python 3.14, pytest, FastAPI/pydantic; cliente ES modules (`node --test`). Escritor atomico compartido `calipso/economia/candado.py`.

**Spec:** `docs/superpowers/specs/2026-09-03-el-jefe-aprende-de-mis-reacciones-design.md`

## Global Constraints

- **`reacciones.py` NO importa `calipso.memory`.** `memory.py` importa `chromadb` en el tope (`memory.py:36`) y `jefe.py` se cuida de no arrastrarlo (`jefe.py:38`). El layout `memoria/departamento/<clave>/` se replica; `_slug` tiene que quedar **identico** a `memory._slug` (`memory.py:47`): `re.sub(r"[^a-z0-9]+", "-", str(nombre).lower()).strip("-")[:80] or "root"`.
- **Escritura atomica siempre.** Nunca `write_text` pelado para el registro: usar `calipso.economia.candado.escribir_json_atomico(ruta, datos)`.
- **Lectura fallo cerrado.** `leer` distingue AUSENTE (`[]`) de PRESENTE-pero-ilegible (**levanta**), como `permisos._leer_solicitudes`, no como `permisos.config()`. Nunca cae a `[]` sobre corrupto (perderia un "no mas" y lo reescribiria con vacio).
- **La identidad del "no mas" es la `clave`** (`ficha.normalizar(sobre)`), ignorando `promete`/`tarda`. El piso compara por igualdad de `clave`.
- **El veto es por el departamento que reacciono**, no global. El `nombre` del departamento se deriva SIN el prefijo `dep:` (el bus guarda `departamento` sin prefijo; la carta usa `cuenta.split(":",1)[1]`).
- **SIN EMOJIS** en codigo, tests ni mensajes. Comentarios y docstrings en espanol.
- **Mensajes de commit sin tildes ni ene**, sin emojis.
- **NUNCA importar `calipso` fuera de pytest.** Tests que tocan el almacen: `monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))`.
- **No reiniciar el servidor.** El smoke en vivo queda anotado como seguimiento.
- Retirar `descartadas_semana` es SOLO la lista del prompt (`situacion.py` deja de armarla, `decision.py` deja de leerla). NO tocar el `continue` de `situacion.py` que libera el techo al descartar — es logica aparte (el techo se libera por el estado del bus, no por esa lista).

---

### Task 1: El registro de reacciones (`calipso/plantel/reacciones.py`)

Almacen puro: guarda, lee (fallo cerrado) y expone el predicado del piso. No toca el chat ni el jefe todavia.

**Files:**
- Create: `calipso/plantel/reacciones.py`
- Test: `test_plantel_reacciones.py`

**Interfaces:**
- Consumes: `calipso.economia.candado.escribir_json_atomico(ruta, datos)`.
- Produces:
  - `anotar(nombre: str, reaccion: str, forma: dict | None, palabras: str, propuesta_id: str) -> None` — appendea; `reaccion` en `{"descarto","no_mas","financio"}`; escritura atomica.
  - `leer(nombre: str) -> list[dict]` — reacciones del depto, mas viejas primero; `[]` si ausente; **levanta `ErrorReacciones`** si corrupto.
  - `esta_vetada(reacciones: list, clave: str) -> bool` — PURA: True si hay un `no_mas` con esa `clave` en la lista dada.
  - `ErrorReacciones(Exception)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `test_plantel_reacciones.py`:

```python
# test_plantel_reacciones.py
import json

import pytest


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    return tmp_path


def _forma(sobre="el radar de precios", promete="medir", tarda="corto"):
    from calipso.plantel import ficha
    return {"sobre": sobre, "clave": ficha.normalizar(sobre),
            "promete": promete, "tarda": tarda}


def test_anotar_y_leer(home):
    from calipso.plantel import reacciones
    reacciones.anotar("taller", "descarto", _forma(), "muy caro", "taller-1")
    got = reacciones.leer("taller")
    assert len(got) == 1
    assert got[0]["reaccion"] == "descarto"
    assert got[0]["palabras"] == "muy caro"
    assert got[0]["forma"]["clave"] == _forma()["clave"]
    assert got[0]["ts"]


def test_leer_sin_archivo_es_lista_vacia(home):
    from calipso.plantel import reacciones
    assert reacciones.leer("taller") == []


def test_leer_corrupto_levanta(home):
    from calipso.plantel import reacciones
    ruta = home / "memoria" / "departamento" / "taller" / "reacciones.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("{no es json", encoding="utf-8")
    with pytest.raises(reacciones.ErrorReacciones):
        reacciones.leer("taller")


def test_leer_no_lista_levanta(home):
    from calipso.plantel import reacciones
    ruta = home / "memoria" / "departamento" / "taller" / "reacciones.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text('{"reaccion": "descarto"}', encoding="utf-8")
    with pytest.raises(reacciones.ErrorReacciones):
        reacciones.leer("taller")


def test_reaccion_desconocida_levanta(home):
    from calipso.plantel import reacciones
    with pytest.raises(reacciones.ErrorReacciones):
        reacciones.anotar("taller", "meh", _forma(), "", "taller-1")


def test_esta_vetada_solo_con_no_mas_y_misma_clave(home):
    from calipso.plantel import reacciones
    f = _forma()
    lista = [
        {"reaccion": "descarto", "forma": f, "palabras": "", "propuesta_id": "a"},
        {"reaccion": "no_mas", "forma": f, "palabras": "no", "propuesta_id": "b"},
    ]
    assert reacciones.esta_vetada(lista, f["clave"]) is True
    # una clave distinta no esta vetada
    assert reacciones.esta_vetada(lista, "otra+cosa") is False
    # un descarto (blando) NO es un veto
    solo_descarto = [{"reaccion": "descarto", "forma": f, "palabras": "", "propuesta_id": "a"}]
    assert reacciones.esta_vetada(solo_descarto, f["clave"]) is False


def test_no_usa_write_text_pelado(home):
    # el registro va por el escritor atomico compartido: tras anotar existe el
    # json final y NO queda ningun .tmp tirado.
    from calipso.plantel import reacciones
    reacciones.anotar("taller", "no_mas", _forma(), "no mas", "taller-1")
    dir_dep = home / "memoria" / "departamento" / "taller"
    nombres = [p.name for p in dir_dep.iterdir()]
    assert "reacciones.json" in nombres
    assert not any(n.startswith("reacciones.json.tmp") for n in nombres)


def test_no_importa_memory():
    # jefe.py lee este registro y se cuida de no arrastrar chromadb; el modulo
    # no puede importar calipso.memory (que importa chromadb en el tope).
    import ast
    import pathlib
    src = pathlib.Path("calipso/plantel/reacciones.py").read_text(encoding="utf-8")
    arbol = ast.parse(src)
    importados = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            importados += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            importados.append(n.module or "")
    assert not any("memory" in m for m in importados)
    assert not any("chromadb" in m for m in importados)
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/bin/python -m pytest test_plantel_reacciones.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'calipso.plantel.reacciones'`

- [ ] **Step 3: Escribir la implementacion**

Crear `calipso/plantel/reacciones.py`:

```python
"""Registro durable de las reacciones de Pedro a las propuestas de un
departamento: lo que descarto, lo que veto ("no mas") y lo que financio, con
SUS palabras. El jefe lo lee en cada decision y aprende (un modelo sin
memoria propia "aprende" teniendo el registro delante). El "no mas" ademas
arma un piso determinista: `esta_vetada`.

Vive al lado de la carta, en memoria/departamento/<clave>/reacciones.json.
NO importa calipso.memory A PROPOSITO: memory.py importa chromadb en el tope
(memory.py:36) y jefe.py -que lee este registro- se cuida de no arrastrar eso
(jefe.py:38). Por eso el layout se replica aca; `_slug` tiene que quedar
IDENTICO a memory._slug.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re

from calipso.economia import candado


class ErrorReacciones(Exception):
    pass


REACCIONES = ("descarto", "no_mas", "financio")


def _home() -> pathlib.Path:
    return pathlib.Path(os.environ.get(
        "CALIPSO_HOME", os.path.expanduser("~/.calipso")))


def _slug(nombre: str) -> str:
    # identico a calipso.memory._slug: la carta y las reacciones tienen que
    # caer en el MISMO directorio del departamento.
    return re.sub(r"[^a-z0-9]+", "-", str(nombre).lower()).strip("-")[:80] or "root"


def _ruta(nombre: str) -> pathlib.Path:
    return _home() / "memoria" / "departamento" / _slug(nombre) / "reacciones.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def leer(nombre: str) -> list[dict]:
    """Las reacciones del departamento, mas viejas primero. `[]` si no hay
    archivo. Un archivo PRESENTE pero ilegible NO es lista vacia: levanta,
    para no perder un "no mas" ni reescribirlo con vacio (espeja
    permisos._leer_solicitudes, no config())."""
    ruta = _ruta(nombre)
    if not ruta.exists():
        return []
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ErrorReacciones(
            f"no se pueden leer las reacciones ({ruta}): {exc}") from None
    if not isinstance(data, list):
        raise ErrorReacciones(f"reacciones ilegibles: {ruta}")
    return data


def anotar(nombre: str, reaccion: str, forma: dict | None,
           palabras: str, propuesta_id: str) -> None:
    """Appendea una reaccion al registro del departamento. Escritura
    atomica (nunca write_text pelado). Si el archivo esta corrupto, `leer`
    levanta y no se anota (no se lo lleva por delante)."""
    if reaccion not in REACCIONES:
        raise ErrorReacciones(f"reaccion desconocida: {reaccion}")
    data = leer(nombre)
    data.append({"ts": _now(), "reaccion": reaccion,
                 "forma": forma or None,
                 "palabras": (palabras or "").strip(),
                 "propuesta_id": propuesta_id})
    candado.escribir_json_atomico(_ruta(nombre), data)


def esta_vetada(reacciones: list, clave: str) -> bool:
    """El piso del "no mas": True si alguna reaccion es un `no_mas` sobre esa
    `clave`. PURA -- opera sobre una lista ya leida para que el jefe no relea
    disco. Ignora `promete`/`tarda`: la identidad es la `clave`."""
    return any(r.get("reaccion") == "no_mas"
               and (r.get("forma") or {}).get("clave") == clave
               for r in reacciones)
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `.venv/bin/python -m pytest test_plantel_reacciones.py -v`
Expected: PASS (8 pruebas)

- [ ] **Step 5: Commit**

```bash
git add calipso/plantel/reacciones.py test_plantel_reacciones.py
git commit -m "feat(fabrica): registro durable de reacciones del jefe (descarto/no_mas/financio)"
```

---

### Task 2: La captura en la mesa (`server.py`)

Los endpoints de la mesa pasan a llevar las palabras de Pedro y a anotar la reaccion. `descartar` gana un body opcional; nace `no-mas`; `financiar` gana palabras opcionales.

**Files:**
- Modify: `calipso/server.py` — modelos de body (junto a `MesaFinanciarBody`, ~430) y los endpoints `api_eco_bus_financiar` / `api_eco_bus_descartar` (~4388-4462); agregar `api_eco_bus_no_mas`.
- Test: `test_mesa_reacciones_server.py`

**Interfaces:**
- Consumes: `reacciones.anotar(nombre, reaccion, forma, palabras, id)` (Task 1); `bus.datos(id)` da `{"departamento","forma",...}`.
- Produces: `POST /api/economia/bus/{id}/descartar` (body `{palabras?}`), `POST /api/economia/bus/{id}/no-mas` (body `{palabras?}`), `POST /api/economia/bus/{id}/financiar` (body gana `palabras?`).

**Nota de orden y errores:** el marcado del bus (accion economica critica, dentro del candado del libro) va PRIMERO, como hoy. La anotacion de la reaccion va DESPUES, con su propio archivo. `reacciones.anotar` puede levantar solo si el registro esta corrupto (caso rarisimo con escritura atomica); si lo hace, se surfacea como 400 — el descartar/no-mas ya quedo asentado en el bus y no se revierte (es la accion economica terminal; la reaccion es el registro de aprendizaje).

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `test_mesa_reacciones_server.py`. Usa el patron de auth del proyecto (`TestClient` con la cookie del token). Reusa el armado de una propuesta con forma que ya tienen los tests de mesa (mira `test_mesa_server.py` para el helper de sembrar una propuesta en `alta` con `forma`).

```python
# test_mesa_reacciones_server.py
import os

import pytest

# el conftest de la raiz ya fija CALIPSO_HOME a un tmp de la suite.
import calipso.server as srv
from calipso.plantel import reacciones
from fastapi.testclient import TestClient


@pytest.fixture
def cliente():
    return TestClient(app=srv.app, cookies={srv.COOKIE: srv.TOKEN})


def _sembrar_propuesta_alta(...):
    # Reproducir el helper de test_mesa_server.py: economia sembrada + una
    # propuesta en `alta` con forma {"sobre","clave","promete","tarda"} y
    # departamento conocido. Devuelve (id, nombre_dep, clave).
    ...


def test_descartar_con_palabras_anota_la_reaccion(cliente):
    id_, dep, clave = _sembrar_propuesta_alta(...)
    r = cliente.post(f"/api/economia/bus/{id_}/descartar",
                     json={"palabras": "otro angulo"})
    assert r.status_code == 200
    regs = reacciones.leer(dep)
    assert regs and regs[-1]["reaccion"] == "descarto"
    assert regs[-1]["palabras"] == "otro angulo"
    assert regs[-1]["forma"]["clave"] == clave


def test_no_mas_anota_reaccion_no_mas(cliente):
    id_, dep, clave = _sembrar_propuesta_alta(...)
    r = cliente.post(f"/api/economia/bus/{id_}/no-mas",
                     json={"palabras": "no mas de esto"})
    assert r.status_code == 200
    regs = reacciones.leer(dep)
    assert regs[-1]["reaccion"] == "no_mas"
    assert reacciones.esta_vetada(regs, clave) is True


def test_descartar_sin_palabras_sigue_andando(cliente):
    id_, dep, _ = _sembrar_propuesta_alta(...)
    r = cliente.post(f"/api/economia/bus/{id_}/descartar", json={})
    assert r.status_code == 200
    assert reacciones.leer(dep)[-1]["palabras"] == ""


def test_financiar_con_palabras_anota_financio(cliente):
    id_, dep, _ = _sembrar_propuesta_alta(...)
    r = cliente.post(f"/api/economia/bus/{id_}/financiar",
                     json={"cuenta": "<cuenta_valida>", "mm": <presupuesto>,
                           "palabras": "esto si"})
    assert r.status_code == 200
    assert reacciones.leer(dep)[-1]["reaccion"] == "financio"
```

(El implementador completa `_sembrar_propuesta_alta` y los valores `<...>` reusando el helper existente en `test_mesa_server.py`; el nombre del depto sale de `srv._eco_bus.Bus(...).datos(id)["departamento"]`.)

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/bin/python -m pytest test_mesa_reacciones_server.py -v`
Expected: FAIL — `no-mas` da 404/405 (no existe), y descartar rechaza el body extra o no anota.

- [ ] **Step 3: Agregar los modelos de body**

Junto a `MesaFinanciarBody` en `server.py`, agregar dos cuerpos (con `extra="forbid"` como el resto):

```python
class MesaDescartarBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    palabras: str = ""


class MesaNoMasBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    palabras: str = ""
```

Y agregar `palabras: str = ""` a `MesaFinanciarBody` (despues de `mm`).

- [ ] **Step 4: Anotar la reaccion en los endpoints**

Importar el registro junto a los otros imports del plantel en `server.py`:

```python
from calipso.plantel import reacciones as _plantel_reacciones  # noqa: E402
```

Un helper local para no repetir la derivacion (arriba de los endpoints de la mesa):

```python
def _anotar_reaccion(p0, id: str, reaccion: str, palabras: str) -> None:
    """Anota la reaccion de Pedro sobre una propuesta. Deriva depto y forma
    del bus. No mueve plata ni toca el libro; su propio archivo, atomico."""
    bus = _eco_bus.Bus(p0.ruta_bus)
    d = bus.datos(id)
    dep = d.get("departamento", "")
    if dep:
        _plantel_reacciones.anotar(dep, reaccion, d.get("forma"),
                                   palabras, id)
```

En `api_eco_bus_descartar`: cambiar la firma a `def api_eco_bus_descartar(id: str, body: MesaDescartarBody) -> dict:` y, DESPUES del `with _eco_candado(...)` exitoso (fuera del candado del libro), agregar `_anotar_reaccion(p0, id, "descarto", body.palabras)`.

En `api_eco_bus_financiar`: agregar, tras el `financiar` exitoso, `_anotar_reaccion(p0, id, "financio", body.palabras)`.

Agregar el endpoint nuevo, clon de `descartar` (mismo guarda de estado, `bus.descartar` — la propuesta puntual muere igual; la diferencia es el tipo `no_mas`):

```python
@app.post("/api/economia/bus/{id}/no-mas")
def api_eco_bus_no_mas(id: str, body: MesaNoMasBody) -> dict:
    """Pedro dice NO MAS: descarta esta propuesta Y veta el tema. El piso lo
    lee el jefe (reacciones.esta_vetada) y no vuelve a proponer esa clave en
    este departamento. Mismo corte que descartar contra el LIBRO."""
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    ts, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            m = p0.mercado_fresco()
            bus = _eco_bus.Bus(p0.ruta_bus)
            if (bus.estado(id) != "alta"
                    or _eco_bus.aportes(m.k.libro.asientos(), id)
                    or _eco_bus.aporte_preseed(m.k.libro.asientos(), id)):
                raise HTTPException(
                    status_code=400,
                    detail=f"la propuesta {id} ya no se puede descartar")
            _eco_bus.descartar(bus, ts, semana, id)
        _anotar_reaccion(p0, id, "no_mas", body.palabras)
    except HTTPException:
        raise
    except _eco_errores_economicos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"ok": True}
```

(En `descartar`/`financiar`, poner el `_anotar_reaccion(...)` fuera del `with _eco_candado` pero dentro del `try`, para que un registro corrupto se surfacee como error y no quede mudo.)

- [ ] **Step 5: Correr y verificar que pasan**

Run: `.venv/bin/python -m pytest test_mesa_reacciones_server.py -v`
Expected: PASS

- [ ] **Step 6: No regresion de la mesa existente**

Run: `.venv/bin/python -m pytest test_mesa_server.py -v`
Expected: PASS — descartar/financiar siguen andando (el body nuevo de descartar es opcional: `{}` vale). Si algun test viejo posteaba a `descartar` SIN body JSON, ajustarlo a `json={}` (el endpoint ahora espera un body; un POST sin cuerpo da 422). Anotar el ajuste en el reporte.

- [ ] **Step 7: Commit**

```bash
git add calipso/server.py test_mesa_reacciones_server.py test_mesa_server.py
git commit -m "feat(fabrica): la mesa captura las palabras de Pedro y anota la reaccion (descartar/no-mas/financiar)"
```

---

### Task 3: El jefe lee sus reacciones (`jefe.py`, `decision.py`, `situacion.py`)

El jefe lee el registro durable (fallo cerrado) y lo pone en su prompt como "Pedro reacciono asi", reemplazando la linea semanal `descartadas_semana`.

**Files:**
- Modify: `calipso/plantel/jefe.py` — en `tic`, leer `reacciones.leer(nombre)` y pasarlo a `dec.prompt`.
- Modify: `calipso/plantel/decision.py` — `prompt(...)` gana un parametro `reacciones` y rinde el bloque nuevo en vez de `rechazadas` (la linea de `descartadas_semana`).
- Modify: `calipso/plantel/situacion.py` — dejar de armar `descartadas_semana`.
- Test: `test_plantel_decision.py` (agregar), `test_plantel_jefe.py` (migrar los de descartadas), `test_plantel_situacion.py` (migrar).

**Interfaces:**
- Consumes: `reacciones.leer(nombre) -> list[dict]` (Task 1).
- Produces: `decision.prompt(..., reacciones: list = ())` incluye el bloque "Pedro reacciono asi"; `situacion` ya no devuelve `descartadas_semana`.

- [ ] **Step 1: Escribir la prueba que falla (decision.prompt rinde las reacciones)**

Agregar a `test_plantel_decision.py`:

```python
def test_el_prompt_rinde_las_reacciones_de_pedro():
    from calipso.plantel import decision as dec
    s = _situacion_minima()   # helper existente en el archivo
    reacs = [
        {"reaccion": "no_mas", "forma": {"sobre": "el radar de precios", "clave": "precios+radar"}, "palabras": "no mas", "propuesta_id": "a"},
        {"reaccion": "descarto", "forma": {"sobre": "un dashboard", "clave": "dashboard"}, "palabras": "otro angulo", "propuesta_id": "b"},
    ]
    p = dec.prompt(s, 50, "", (), reacciones=reacs)
    assert "Pedro reacciono" in p
    assert "el radar de precios" in p and "NO MAS" in p
    assert "un dashboard" in p and "otro angulo" in p


def test_sin_reacciones_el_prompt_no_rompe():
    from calipso.plantel import decision as dec
    s = _situacion_minima()
    p = dec.prompt(s, 50, "", ())
    assert isinstance(p, str) and p
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `.venv/bin/python -m pytest test_plantel_decision.py::test_el_prompt_rinde_las_reacciones_de_pedro -v`
Expected: FAIL — `prompt()` no acepta `reacciones` (TypeError) y no rinde el bloque.

- [ ] **Step 3: Rendir las reacciones en `decision.prompt`**

En `calipso/plantel/decision.py`:

1. La firma de `prompt` gana `reacciones: list = ()` (al final, para no romper llamadas por posicion). La firma actual (`decision.py:76-78`) lista `recientes`, `carta`, etc.; agregar `reacciones` como keyword con default.
2. Reemplazar la construccion de `rechazadas` (que lee `s.get("descartadas_semana", [])`, `decision.py:105-106`) por un bloque que rinde `reacciones`:

```python
    # Las reacciones DURABLES de Pedro (descarto / no mas / financio), su
    # VOZ y no una conclusion del jefe (por eso viven afuera del core, como
    # la carta). Reemplaza al viejo `descartadas_semana`, que se evaporaba
    # cada semana. Un `no_mas` ademas lo frena el piso determinista (ver
    # jefe): mostrarlo aca es para que no gaste turnos.
    def _linea_reaccion(r):
        f = r.get("forma") or {}
        sobre = f.get("sobre", "(sin tema)")
        pal = f" ({r['palabras']})" if r.get("palabras") else ""
        if r.get("reaccion") == "no_mas":
            return f"  - NO MAS: {sobre}{pal}"
        if r.get("reaccion") == "financio":
            return f"  - financio: {sobre}{pal}"
        return f"  - descarto: {sobre}{pal} -- proba otro angulo o soltalo"
    rechazadas = "\n".join(_linea_reaccion(r) for r in reacciones)
```

3. Donde `rechazadas` se inserta en el texto del prompt (el titulo del bloque), cambiar el encabezado a algo como `"Pedro reacciono asi a tus propuestas (su voz, no tu conclusion):\n{rechazadas}"` cuando haya reacciones; si no hay, omitir el bloque (o "  (todavia no reacciono a nada)"). Mantener el resto del prompt igual.

- [ ] **Step 4: Correr y verificar que pasan (decision)**

Run: `.venv/bin/python -m pytest test_plantel_decision.py -v`
Expected: PASS (las nuevas + las viejas; si alguna vieja asertaba el texto de `descartadas_semana`, migrarla al bloque nuevo — anotar en el reporte cual).

- [ ] **Step 5: Retirar `descartadas_semana` de `situacion` y cablear `jefe.tic`**

En `calipso/plantel/situacion.py`: quitar la construccion de la lista `descartadas` y la clave `"descartadas_semana": descartadas` del dict de retorno (`situacion.py:112-123` y `:224`). **NO tocar** el `continue` de la rama `estado == "descartada"` que libera el techo — solo quitar el append a `descartadas` y el fold en el dict. El `catalogo` (que tambien recorre el bus) queda igual.

En `calipso/plantel/jefe.py`, en `tic`, leer el registro y pasarlo al prompt. El nombre del depto se deriva de `cuenta` sin el prefijo `dep:` (igual que la carta): `nombre = cuenta.split(":", 1)[1] if ":" in cuenta else cuenta`. Dentro del `try` que ya envuelve el armado del prompt (`jefe.py:344`), leer las reacciones ANTES de `dec.prompt` y pasarlas:

```python
        reacs = reacciones.leer(nombre)   # fallo cerrado: si esta corrupto,
                                          # levanta y el try lo convierte en
                                          # "no armo el prompt" -> el jefe no
                                          # propone este tic (lado seguro).
        p = dec.prompt(s, sesgo, ctx.memoria.load_core(),
                       ctx.memoria.recent(limit=5),
                       carta=ctx.carta,
                       proyectos=dec.proyectos_de(ctx.proyectos, cuenta),
                       reacciones=reacs)
```

Guardar `reacs` en una variable accesible mas abajo en `tic` (para el piso de la Task 4). Importar el modulo arriba en `jefe.py`: `from calipso.plantel import reacciones`. (Confirmar que `reacciones` no importa memory — Task 1 lo garantiza — asi `jefe` sigue sin arrastrar chromadb.)

- [ ] **Step 6: Migrar los tests de descartadas y correr todo el plantel**

Los tests que verificaban `descartadas_semana`:
- `test_plantel_situacion.py`: los que asertan `s["descartadas_semana"]` — migrar a verificar que la clave ya NO esta (o borrarlos si su intencion la cubre ahora el registro). `test_una_propuesta_descartada_desaparece_de_las_propias` (:185) NO se toca (es sobre `propuestas_propias`, no sobre la lista retirada).
- `test_plantel_jefe.py`: `test_lo_que_pedro_descarto_esta_semana_le_llega_al_jefe` (:757) y `test_una_descartada_de_otra_semana_ya_no_pesa` (:785) — reescribir contra el registro durable (una reaccion `descarto` anotada llega al prompt via `reacciones.leer`), o moverlas a `test_plantel_decision.py`/`test_plantel_reacciones.py` segun lo que prueben. `test_descartar_una_propuesta_destraba_el_techo` (:614) NO se toca (es sobre el techo, que sigue).

Run: `.venv/bin/python -m pytest test_plantel_situacion.py test_plantel_jefe.py test_plantel_decision.py -v`
Expected: PASS (con los tests migrados).

- [ ] **Step 7: Commit**

```bash
git add calipso/plantel/jefe.py calipso/plantel/decision.py calipso/plantel/situacion.py test_plantel_decision.py test_plantel_jefe.py test_plantel_situacion.py
git commit -m "feat(fabrica): el jefe lee sus reacciones durables en el prompt y retira descartadas_semana"
```

---

### Task 4: El piso del "no mas" (`jefe.py`)

Cuando el jefe propone y la `clave` de la ficha fue vetada con "no mas" en ese departamento, la propuesta se cae antes del bus.

**Files:**
- Modify: `calipso/plantel/jefe.py` — en `tic`, tras parsear la ficha de un `proponer` (donde hoy se desvia la ilegible, `jefe.py:371-...`), agregar el chequeo del piso.
- Test: `test_plantel_jefe.py` (agregar).

**Interfaces:**
- Consumes: `reacciones.esta_vetada(reacs, clave) -> bool` (Task 1); `reacs` ya leido en `tic` (Task 3); `f["clave"]` de `ficha.parsear_ficha`.
- Produces: una propuesta con `clave` vetada no llega al bus; el jefe recibe la razon "eso lo vetaste".

- [ ] **Step 1: Escribir la prueba que falla**

Agregar a `test_plantel_jefe.py` (usar el patron existente del archivo para correr un `tic` con una carta/registro puestos y un modelo que devuelve una ficha con `sobre` conocido):

```python
def test_un_tema_vetado_con_no_mas_no_llega_al_bus(...):
    # dado un no_mas anotado sobre la clave de "el radar de precios" en el
    # depto, cuando el jefe propone justamente ese tema (reencuadrado con
    # otra promesa), la propuesta se cae antes del bus y el jefe recibe la
    # razon del veto.
    from calipso.plantel import ficha, reacciones
    dep = "taller"
    f = {"sobre": "el radar de precios", "clave": ficha.normalizar("el radar de precios"),
         "promete": "medir", "tarda": "corto"}
    reacciones.anotar(dep, "no_mas", f, "no mas", "taller-viejo")
    # el modelo del jefe devuelve una ficha del MISMO tema pero reencuadrada
    # (promete acelerar en vez de medir): misma clave -> vetada.
    crudo = "proponer\nsobre: radar de precios\npromete: acelerar\ntarda: corto\nporque: x"
    res = _correr_tic(dep, modelo_devuelve=crudo, ...)
    assert res["accion"] != "proponer" or res["actuo"] is False
    assert "vetast" in (res.get("freno", "") + res.get("motivo", "")).lower()
    # y no quedo ninguna alta nueva en el bus para esa clave
    ...


def test_un_tema_no_vetado_si_llega(...):
    # el mismo camino, sin no_mas anotado (o con otra clave vetada), propone
    # normal.
    ...
```

(El implementador adapta al helper de `tic` que ya usa `test_plantel_jefe.py`; lo esencial: un `no_mas` sobre la clave, el modelo propone esa clave, la propuesta NO llega al bus y el jefe recibe una razon con "vetaste".)

- [ ] **Step 2: Correr y verificar que falla**

Run: `.venv/bin/python -m pytest test_plantel_jefe.py::test_un_tema_vetado_con_no_mas_no_llega_al_bus -v`
Expected: FAIL — hoy la propuesta vetada llega al bus (no hay piso).

- [ ] **Step 3: Agregar el chequeo del piso en `tic`**

En `calipso/plantel/jefe.py`, en `tic`, DESPUES de `f = ficha.parsear_ficha(crudo) if accion == "proponer" else None` y de la valvula de la ilegible (`if accion == "proponer" and f is None: ...`), y ANTES de llamar a `_puede`/`contratar`, agregar:

```python
        # EL PISO DEL "NO MAS". Determinista: si Pedro veto esta clave en
        # este departamento, la propuesta no llega al bus, pase lo que pase
        # con el modelo. Reencuadrar la promesa o el plazo no lo esquiva
        # porque la clave sale solo del `sobre`. Va aca, con la ficha ya
        # legible y ANTES de `_puede`/`contratar`, por el mismo motivo que
        # la valvula de la ilegible: `contratar` de produccion no tiene
        # guarda de accion y escribiria en el bus.
        if f is not None and reacciones.esta_vetada(reacs, f["clave"]):
            ctx.publicar("razonando",
                         texto=f"vetado: {f['sobre']} -- Pedro dijo no mas")
            return salida(accion="proponer", ref=None,
                          motivo="eso lo vetaste, proba otra cosa",
                          actuo=False, freno="vetado con no mas")
```

(Adaptar `salida(...)` a la firma real del helper local de `tic` — `jefe.py:333`. Lo importante: no llamar a `contratar`, devolver el dict con las ocho claves, `actuo=False`, y una razon que diga que se veto.)

- [ ] **Step 4: Correr y verificar que pasan**

Run: `.venv/bin/python -m pytest test_plantel_jefe.py -v`
Expected: PASS (las nuevas + las viejas).

- [ ] **Step 5: Commit**

```bash
git add calipso/plantel/jefe.py test_plantel_jefe.py
git commit -m "feat(fabrica): piso determinista del no mas -- una clave vetada no llega al bus"
```

---

### Task 5: La UI de la mesa (`calipso/web/fabrica/`)

La mesa gana un campo de texto para las palabras y el boton "no mas"; `app.js` manda las palabras y pega a `/no-mas`.

**Files:**
- Modify: `calipso/web/fabrica/mesa.js` — dibujar el campo de texto y el boton "no mas" en cada fila.
- Modify: `calipso/web/fabrica/app.js` — leer las palabras del campo y postear (descartar/no-mas con `palabras`, financiar con `palabras`).
- Test: `calipso/web/fabrica/mesa.test.js` (agregar).

**Interfaces:**
- Consumes: los endpoints de la Task 2.
- Produces: los `fetch` con `palabras` en el body y el nuevo `data-accion="no-mas"`.

- [ ] **Step 1: Escribir la prueba de cliente que falla**

Agregar a `calipso/web/fabrica/mesa.test.js` un test que verifique que el HTML de una fila incluye el campo de texto de palabras y un boton con `data-accion="no-mas"` (usando el mismo patron de render que ya testea `mesa.test.js`).

```javascript
test("la fila de la mesa tiene campo de palabras y boton no mas", () => {
  const html = filaPropuesta(/* una propuesta de ejemplo con forma */);
  assert.match(html, /data-accion="no-mas"/);
  assert.match(html, /class="[^"]*palabras/);   // el input/textarea de palabras
});
```

(El implementador usa el export real que arma la fila en `mesa.js` — mirar como `mesa.test.js` importa y llama hoy.)

- [ ] **Step 2: Correr y verificar que falla**

Run (desde `calipso/web/fabrica/`): `node --test mesa.test.js`
Expected: FAIL — no hay `data-accion="no-mas"` ni campo de palabras.

- [ ] **Step 3: Dibujar el campo y el boton en `mesa.js`**

En la funcion que arma la fila de una propuesta, agregar (junto a los botones de descartar/financiar) un `<textarea>`/`<input class="palabras" data-id="...">` opcional y un `<button data-accion="no-mas" data-id="...">no mas</button>`. Mantener el estilo de los botones existentes.

- [ ] **Step 4: Postear las palabras en `app.js`**

En el handler de la mesa (`app.js:283-297`):
- Para `financiar` y `descartar`, leer las palabras del campo de la fila: `const palabras = boton.closest(".propuesta")?.querySelector("input.palabras, textarea.palabras")?.value || "";` e incluirlas en el body (`descartar` pasa a mandar `{palabras}` con `Content-Type: application/json`; `financiar` agrega `palabras`).
- Agregar la rama `accion === "no-mas"`: `fetch('/api/economia/bus/${id}/no-mas', {method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({palabras})})`.
- El listener de click (`app.js:314`) ya despacha por `data-accion`; asegurar que `no-mas` entra.

- [ ] **Step 5: Correr y verificar que pasan (cliente + puente pytest)**

Run (desde `calipso/web/fabrica/`): `node --test mesa.test.js`
Expected: PASS

Run (desde la raiz): `.venv/bin/python -m pytest test_fabrica_js.py -q`
Expected: PASS (el puente que corre los tests del cliente sigue verde).

- [ ] **Step 6: Commit**

```bash
git add calipso/web/fabrica/mesa.js calipso/web/fabrica/app.js calipso/web/fabrica/mesa.test.js
git commit -m "feat(fabrica): la mesa gana campo de palabras y boton no mas"
```

---

## Notas de verificacion (fuera de las tareas)

- **Suite completa antes de cerrar la rama:** `.venv/bin/python -m pytest -q` verde, mas los tests del cliente via `test_fabrica_js.py`. Sin reaccionar con palabras ni "no mas", la fabrica corre como hoy (salvo que `descartadas_semana` es ahora el registro durable).
- **Smoke en vivo (seguimiento, NO en este plan porque no se reinicia el server):** con el server y la economia sembrada, descartar/no-mas con palabras desde `/fabrica`, y ver que (a) el jefe deja de proponer una clave vetada y (b) el prompt del jefe muestra "Pedro reacciono asi". Igual que otros smokes, queda anotado hasta poder reiniciar con codigo nuevo.

## Self-Review

**1. Cobertura del spec:**
- Seccion 4 (registro `reacciones.py`, atomico, fallo cerrado, `esta_vetada`): Task 1. OK.
- Seccion 5 (captura: descartar/no-mas/financiar con palabras, dep/forma del bus, guardas): Task 2. OK.
- Seccion 6 (uso: prompt "Pedro reacciono asi", retira descartadas_semana, tres clases distintas): Task 3. OK.
- Seccion 7 (piso determinista por clave en la costura de decision, fallo cerrado): Task 4 (piso) + Task 3 (la lectura fallo-cerrado en tic). OK.
- Seccion 8 (UI: campo + boton no mas): Task 5. OK.
- Seccion 9 (invariantes): no_mas determinista (T4), reencuadrar esquiva blando no duro (T4, identidad por clave), voz de Pedro afuera del core (T3), no se corrompe (T1 atomico+fallo cerrado), veto por depto (T1/T2 derivan el nombre sin prefijo). OK.
- Seccion 10 (lo que NO hace): ninguna tarea infiere intensidad, captura por chat, veta global, resume el registro ni agrega panel de revocar. OK.
- Seccion 11 (verificacion): cada punto mapea a pruebas de T1-T5 + smoke anotado. OK.

**2. Placeholders:** el codigo del modulo (T1), los endpoints (T2), el render del prompt (T3) y el piso (T4) van completos. T2/T4/T5 dejan al implementador COMPLETAR helpers de test reusando helpers EXISTENTES nombrados con archivo (`test_mesa_server.py` para sembrar una propuesta; el helper de `tic` de `test_plantel_jefe.py`; el render de `mesa.test.js`) — es adaptacion a infraestructura de test que ya existe, no logica sin especificar. Los pasos de codigo de produccion no tienen placeholders.

**3. Consistencia de tipos:** `reacciones.leer -> list[dict]` (T1) es lo que `jefe.tic` guarda en `reacs` (T3) y lo que `esta_vetada(reacs, clave)` consume (T4). El registro `{ts, reaccion, forma, palabras, propuesta_id}` es el que escribe `anotar` (T1), lo que anota el endpoint (T2) y lo que rinde el prompt (T3) y filtra el piso (T4). `reaccion` en `{"descarto","no_mas","financio"}` en los cuatro. `forma` = `{sobre,clave,promete,tarda}` de `ficha.parsear_ficha`/`bus.datos`. La `clave` = `ficha.normalizar(sobre)` en T1 (test), T4 (piso) y el bus. Consistente.
