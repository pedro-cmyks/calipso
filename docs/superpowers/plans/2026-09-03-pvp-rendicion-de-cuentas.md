# El PvP — rendicion de cuentas de las promesas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cuando el plazo de una promesa financiada vence, Pedro juzga si el departamento cumplio; el veredicto arma un standing por departamento (reputacion, sin mover plata) que el jefe ve en su prompt y Pedro ve en la mesa.

**Architecture:** Un almacen puro nuevo (`calipso/plantel/promesas.py`) guarda los veredictos al lado de la carta. Un helper puro `bus.vencida` decide que trabajo llego a su plazo sin juzgar. Los endpoints de la mesa capturan el veredicto (`cumplio`/`no-cumplio`) y la mesa surface la seccion "por juzgar" + el standing por propuesta. El jefe lee su standing en `decision.prompt`. La UI de `/fabrica` agrega la seccion y el standing.

**Tech Stack:** Python 3.14, pytest, FastAPI/pydantic; cliente ES modules (`node --test`). Escritor atomico compartido `calipso/economia/candado.py`.

**Spec:** `docs/superpowers/specs/2026-09-03-pvp-rendicion-de-cuentas-design.md`

## Global Constraints

- **`promesas.py` NO importa `calipso.memory`** (memory.py importa chromadb; jefe.py lo evita). El `_slug` se replica IDENTICO a `memory._slug` (`re.sub(r"[^a-z0-9]+", "-", str(pathlib.Path(nombre)).lower()).strip("-")[:80] or "root"`). Es el mismo patron ya usado por `calipso/plantel/reacciones.py` -- leer ese archivo como molde.
- **Escritura atomica siempre:** `calipso.economia.candado.escribir_json_atomico`. Nunca `write_text` para el almacen.
- **Lectura fallo cerrado:** `leer` distingue AUSENTE (`[]`) de PRESENTE-pero-ilegible (**levanta `ErrorPromesas`**). Nunca `[]` sobre corrupto.
- **El nombre del departamento se deriva SIN el prefijo `dep:`** en TODA escritura y lectura: `nombre = dep.split(":",1)[1] if ":" in dep else dep`. El bus guarda `departamento` CON prefijo; la carta/registros van pelados. (Esta trampa ya mordio en reacciones; el `_anotar_reaccion` de `server.py:4407` es el molde exacto.)
- **El veredicto NO mueve plata ni toca el bus/libro.** Es reputacion; la liquidacion queda intacta.
- **Un trabajo se juzga UNA vez** (dedup por `propuesta_id`) y solo si su plazo vencio (`bus.vencida`). Los preseed no se juzgan (sin `forma`, sin `criterio.semanas_max`).
- **Fail-closed vs degradar:** el ENDPOINT de juicio y la lectura del JEFE fallan cerrado (400 / el jefe no propone) ante un registro corrupto. La MESA (superficie de lectura) DEGRADA: envuelve el acceso a promesas por fila y muestra standing vacio / `por_juzgar` vacio en vez de tumbar toda la mesa con un 500.
- **SIN EMOJIS** en codigo, tests ni mensajes. Comentarios y docstrings en espanol.
- **Mensajes de commit sin tildes ni ene**, sin emojis.
- **NUNCA importar `calipso` fuera de pytest.** Tests que tocan el almacen o corren `jefe.tic`/endpoints: `monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))` (leccion dura del feature anterior: sin aislar, el registro se cuela al home compartido de la suite y rompe tests no relacionados).
- **No reiniciar el servidor.** El smoke en vivo queda anotado como seguimiento.
- **Antes de commitear cada tarea, correr la SUITE COMPLETA** (`.venv/bin/python -m pytest -q --ignore=test_chat_live.py`), no solo el archivo tocado: el feature anterior escondio una regresion que solo la suite entera atrapo.

---

### Task 1: El almacen de veredictos (`calipso/plantel/promesas.py`)

Almacen puro, hermano de `reacciones.py`: guarda veredictos, lee (fallo cerrado), y deriva el standing.

**Files:**
- Create: `calipso/plantel/promesas.py`
- Test: `test_plantel_promesas.py`

**Interfaces:**
- Consumes: `calipso.economia.candado.escribir_json_atomico`.
- Produces:
  - `anotar(nombre: str, propuesta_id: str, forma: dict | None, cumplio: bool, palabras: str) -> None` — appendea un veredicto; **dedup por `propuesta_id`** (si ya hay veredicto para ese id, no agrega otro); atomico.
  - `leer(nombre: str) -> list[dict]` — veredictos del depto, mas viejos primero; `[]` si ausente; **levanta `ErrorPromesas`** si corrupto.
  - `juzgada(nombre: str, propuesta_id: str) -> bool` — True si ese trabajo ya tiene veredicto.
  - `standing(nombre: str) -> dict` — `{"cumplidas": int, "total": int}` derivado.
  - `ErrorPromesas(Exception)`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `test_plantel_promesas.py`:

```python
# test_plantel_promesas.py
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
    from calipso.plantel import promesas
    promesas.anotar("atlas", "atlas-1", _forma(), True, "tarde pero cumplio")
    got = promesas.leer("atlas")
    assert len(got) == 1
    assert got[0]["propuesta_id"] == "atlas-1"
    assert got[0]["cumplio"] is True
    assert got[0]["palabras"] == "tarde pero cumplio"
    assert got[0]["ts"]


def test_leer_sin_archivo_es_lista_vacia(home):
    from calipso.plantel import promesas
    assert promesas.leer("atlas") == []


def test_leer_corrupto_levanta(home):
    from calipso.plantel import promesas
    ruta = home / "memoria" / "departamento" / "atlas" / "promesas.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("{no es json", encoding="utf-8")
    with pytest.raises(promesas.ErrorPromesas):
        promesas.leer("atlas")


def test_dedup_por_propuesta_un_trabajo_se_juzga_una_vez(home):
    from calipso.plantel import promesas
    promesas.anotar("atlas", "atlas-1", _forma(), True, "")
    promesas.anotar("atlas", "atlas-1", _forma(), False, "cambio de opinion")
    got = promesas.leer("atlas")
    assert len(got) == 1                 # gana el primero, no se duplica
    assert got[0]["cumplio"] is True


def test_juzgada(home):
    from calipso.plantel import promesas
    assert promesas.juzgada("atlas", "atlas-1") is False
    promesas.anotar("atlas", "atlas-1", _forma(), True, "")
    assert promesas.juzgada("atlas", "atlas-1") is True
    assert promesas.juzgada("atlas", "atlas-2") is False


def test_standing_cuenta_cumplidas_y_total(home):
    from calipso.plantel import promesas
    assert promesas.standing("atlas") == {"cumplidas": 0, "total": 0}
    promesas.anotar("atlas", "atlas-1", _forma(), True, "")
    promesas.anotar("atlas", "atlas-2", _forma(), False, "")
    promesas.anotar("atlas", "atlas-3", _forma(), True, "")
    assert promesas.standing("atlas") == {"cumplidas": 2, "total": 3}


def test_no_usa_write_text_pelado(home):
    from calipso.plantel import promesas
    promesas.anotar("atlas", "atlas-1", _forma(), True, "")
    dir_dep = home / "memoria" / "departamento" / "atlas"
    nombres = [p.name for p in dir_dep.iterdir()]
    assert "promesas.json" in nombres
    assert not any(n.startswith("promesas.json.tmp") for n in nombres)


def test_no_importa_memory():
    import ast
    import pathlib
    src = pathlib.Path("calipso/plantel/promesas.py").read_text(encoding="utf-8")
    arbol = ast.parse(src)
    mods = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            mods += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            mods.append(n.module or "")
    assert not any("memory" in m for m in mods)
    assert not any("chromadb" in m for m in mods)
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/bin/python -m pytest test_plantel_promesas.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'calipso.plantel.promesas'`

- [ ] **Step 3: Escribir la implementacion**

Crear `calipso/plantel/promesas.py`:

```python
"""Registro durable de los VEREDICTOS de Pedro sobre las promesas de un
departamento: cuando un trabajo financiado llega a su plazo, Pedro marca si
cumplio o no. De esos veredictos sale el STANDING (cumplio N de M), que el
jefe ve en su prompt (aprende a prometer lo que puede cumplir) y Pedro ve en
la mesa (financia con el historial a la vista). Es el PvP: reputacion, no
plata.

Vive al lado de la carta y de las reacciones, en
memoria/departamento/<clave>/promesas.json. NO importa calipso.memory A
PROPOSITO (memory.py importa chromadb; jefe.py lo evita). Mismo molde que
reacciones.py; `_slug` identico a memory._slug.
"""
from __future__ import annotations

import datetime
import json
import os
import pathlib
import re

from calipso.economia import candado


class ErrorPromesas(Exception):
    pass


def _home() -> pathlib.Path:
    return pathlib.Path(os.environ.get(
        "CALIPSO_HOME", os.path.expanduser("~/.calipso")))


def _slug(nombre: str) -> str:
    # identico a calipso.memory._slug: la carta, las reacciones y las
    # promesas caen en el MISMO directorio del departamento.
    return re.sub(r"[^a-z0-9]+", "-",
                  str(pathlib.Path(nombre)).lower()).strip("-")[:80] or "root"


def _ruta(nombre: str) -> pathlib.Path:
    return _home() / "memoria" / "departamento" / _slug(nombre) / "promesas.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def leer(nombre: str) -> list[dict]:
    """Los veredictos del departamento, mas viejos primero. `[]` si no hay
    archivo. PRESENTE pero ilegible levanta (fallo cerrado): no se pierde un
    veredicto ni se reescribe con vacio."""
    ruta = _ruta(nombre)
    if not ruta.exists():
        return []
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ErrorPromesas(
            f"no se pueden leer las promesas ({ruta}): {exc}") from None
    if not isinstance(data, list):
        raise ErrorPromesas(f"promesas ilegibles: {ruta}")
    return data


def juzgada(nombre: str, propuesta_id: str) -> bool:
    """True si ese trabajo ya tiene veredicto (para no traerlo de nuevo a
    'por juzgar' ni juzgarlo dos veces)."""
    return any(v.get("propuesta_id") == propuesta_id for v in leer(nombre))


def anotar(nombre: str, propuesta_id: str, forma: dict | None,
           cumplio: bool, palabras: str) -> None:
    """Appendea un veredicto. Un trabajo se juzga UNA vez: si ya hay
    veredicto para `propuesta_id`, no se agrega otro (gana el primero).
    Escritura atomica."""
    data = leer(nombre)
    if any(v.get("propuesta_id") == propuesta_id for v in data):
        return
    data.append({"ts": _now(), "propuesta_id": propuesta_id,
                 "forma": forma or None, "cumplio": bool(cumplio),
                 "palabras": (palabras or "").strip()})
    candado.escribir_json_atomico(_ruta(nombre), data)


def standing(nombre: str) -> dict:
    """El historial de promesas del departamento: `{"cumplidas", "total"}`.
    Derivado de los veredictos."""
    vs = leer(nombre)
    return {"cumplidas": sum(1 for v in vs if v.get("cumplio")),
            "total": len(vs)}
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `.venv/bin/python -m pytest test_plantel_promesas.py -v`
Expected: PASS (8 pruebas)

- [ ] **Step 5: Commit**

```bash
git add calipso/plantel/promesas.py test_plantel_promesas.py
git commit -m "feat(fabrica): almacen de veredictos de promesas (cumplio/no) con standing derivado"
```

---

### Task 2: `bus.vencida` — que trabajo llego a su plazo

Un helper puro en el bus que decide si un trabajo financiado con promesa llego a su plazo. Lo consumen los endpoints (Task 3) y la mesa (Task 3/UI).

**Files:**
- Modify: `calipso/economia/bus.py` (agregar `vencida`, junto a `semanas_transcurridas`/`preseed_vencido`, ~611-729)
- Test: `test_economia_bus.py` (agregar)

**Interfaces:**
- Consumes: `bus.semanas_transcurridas(semanas_ops, desde, hasta)` (ya existe).
- Produces: `vencida(datos: dict, semanas_ops: list[str], semana: str) -> bool` — True si `datos` es un trabajo con promesa cuyo plazo vencio. Puro; no toca disco ni promesas.

- [ ] **Step 1: Escribir las pruebas que fallan**

Agregar a `test_economia_bus.py` (usar el patron de `semanas_ops` que ya usan los tests de `preseed_vencido`/`evaluar_y_liquidar_muertos` en ese archivo):

```python
def test_vencida_true_cuando_paso_el_plazo():
    from calipso.economia import bus as bus_mod
    ops = ["2026-W30", "2026-W31", "2026-W32"]
    datos = {"tipo": "trabajo", "semana_financiada": "2026-W30",
             "criterio": {"gasto_max_mm": 100, "semanas_max": 1},
             "forma": {"sobre": "x", "clave": "x", "promete": "medir", "tarda": "corto"}}
    # W31 = 1 semana despues, semanas_max=1 -> vencida
    assert bus_mod.vencida(datos, ops, "2026-W31") is True


def test_vencida_false_si_todavia_no_paso():
    from calipso.economia import bus as bus_mod
    ops = ["2026-W30", "2026-W31"]
    datos = {"tipo": "trabajo", "semana_financiada": "2026-W30",
             "criterio": {"gasto_max_mm": 100, "semanas_max": 4},
             "forma": {"sobre": "x", "clave": "x", "promete": "medir", "tarda": "medio"}}
    assert bus_mod.vencida(datos, ops, "2026-W31") is False


def test_vencida_false_para_preseed_sin_forma():
    from calipso.economia import bus as bus_mod
    ops = ["2026-W30", "2026-W31"]
    datos = {"tipo": "preseed", "semana_financiada": "2026-W30",
             "criterio": {"gasto_max_mm": 100}}   # sin semanas_max, sin forma
    assert bus_mod.vencida(datos, ops, "2026-W31") is False


def test_vencida_false_si_nunca_se_financio():
    from calipso.economia import bus as bus_mod
    ops = ["2026-W30", "2026-W31"]
    datos = {"tipo": "trabajo",
             "criterio": {"gasto_max_mm": 100, "semanas_max": 1},
             "forma": {"sobre": "x", "clave": "x", "promete": "medir", "tarda": "corto"}}
    # sin semana_financiada -> no fue elegida en la mesa -> no se juzga
    assert bus_mod.vencida(datos, ops, "2026-W31") is False
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/bin/python -m pytest test_economia_bus.py -k vencida -v`
Expected: FAIL — `AttributeError: module 'calipso.economia.bus' has no attribute 'vencida'`

- [ ] **Step 3: Escribir la implementacion**

En `calipso/economia/bus.py`, junto a `preseed_vencido`/`semanas_transcurridas`:

```python
def vencida(datos: dict, semanas_ops: list[str], semana: str) -> bool:
    """True si `datos` es un TRABAJO con promesa cuyo plazo ya llego -- lo
    que lo hace juzgable en el PvP. NO mira el estado actual: pregunta por
    `semana_financiada` (que `datos` conserva aun liquidado), asi juzgar es
    independiente de la liquidacion. El plazo es el `semanas_max` que el
    propio trabajo lleva en su `criterio` (== ficha.SEMANAS_MAX[tarda] al
    darse de alta), el mismo numero que usa `evaluar_y_liquidar_muertos`.
    Un preseed no entra: no tiene `forma` ni `semanas_max`."""
    if datos.get("tipo") != "trabajo":
        return False
    if not datos.get("forma"):
        return False
    fin = datos.get("semana_financiada")
    smax = (datos.get("criterio") or {}).get("semanas_max")
    if fin is None or smax is None:
        return False
    try:
        return semanas_transcurridas(semanas_ops, fin, semana) >= smax
    except ErrorBus:
        # una semana fuera del calendario operativo no es juzgable todavia
        return False
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `.venv/bin/python -m pytest test_economia_bus.py -k vencida -v`
Expected: PASS (4 pruebas)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/bus.py test_economia_bus.py
git commit -m "feat(fabrica): bus.vencida -- un trabajo con promesa llego a su plazo (independiente de la liquidacion)"
```

---

### Task 3: La superficie de juicio (endpoints + mesa)

Los endpoints `cumplio`/`no-cumplio` anotan el veredicto; la mesa surface la lista `por_juzgar` y el `standing` por propuesta.

**Files:**
- Modify: `calipso/server.py` — un body `MesaVeredictoBody`; un helper `_juzgar`; los endpoints `api_eco_bus_cumplio`/`api_eco_bus_no_cumplio`; y en `api_eco_bus` la lista `por_juzgar` + `standing` por fila. Import `from calipso.plantel import promesas as _plantel_promesas`.
- Test: `test_mesa_promesas_server.py`

**Interfaces:**
- Consumes: `promesas.anotar/leer/juzgada/standing` (Task 1); `bus.vencida` (Task 2); `bus.datos(id)`.
- Produces: `POST /api/economia/bus/{id}/cumplio` y `.../no-cumplio` (body `{palabras?}`); `api_eco_bus()` devuelve ademas `por_juzgar: list` y cada propuesta lleva `standing: {"cumplidas","total"}`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `test_mesa_promesas_server.py`. Reusar el helper de sembrado de `test_mesa_reacciones_server.py` (economia + una propuesta con forma), pero con el trabajo FINANCIADO y el reloj adelantado mas alla del plazo. Leer `test_mesa_reacciones_server.py` y `test_mesa_server.py` para el helper exacto (sembrado, `TestClient(app=srv.app, cookies={srv.COOKIE: srv.TOKEN})`, `monkeypatch.setattr(srv, "_ECO_BASE", ...)`, `monkeypatch.setenv("CALIPSO_HOME", ...)`, y como se financia un trabajo y como se adelantan las semanas operativas).

```python
# test_mesa_promesas_server.py -- el implementador completa los helpers de
# sembrado/financiacion/adelanto de semanas reusando test_mesa_reacciones_server.py
# y test_mesa_server.py. Lo esencial de cada test:

def test_cumplio_anota_el_veredicto(cliente, tmp_path, monkeypatch):
    id_, dep, _ = _sembrar_trabajo_vencido(tmp_path, monkeypatch)
    r = cliente.post(f"/api/economia/bus/{id_}/cumplio", json={"palabras": "listo"})
    assert r.status_code == 200
    from calipso.plantel import promesas
    assert promesas.leer(dep)[-1]["cumplio"] is True
    assert promesas.standing(dep) == {"cumplidas": 1, "total": 1}


def test_no_cumplio_anota_false(cliente, tmp_path, monkeypatch):
    id_, dep, _ = _sembrar_trabajo_vencido(tmp_path, monkeypatch)
    r = cliente.post(f"/api/economia/bus/{id_}/no-cumplio", json={})
    assert r.status_code == 200
    from calipso.plantel import promesas
    assert promesas.leer(dep)[-1]["cumplio"] is False


def test_juzgar_dos_veces_da_400(cliente, tmp_path, monkeypatch):
    id_, dep, _ = _sembrar_trabajo_vencido(tmp_path, monkeypatch)
    assert cliente.post(f"/api/economia/bus/{id_}/cumplio", json={}).status_code == 200
    assert cliente.post(f"/api/economia/bus/{id_}/cumplio", json={}).status_code == 400


def test_juzgar_un_no_vencido_da_400(cliente, tmp_path, monkeypatch):
    id_, dep, _ = _sembrar_trabajo_reciente(tmp_path, monkeypatch)  # financiado, sin vencer
    assert cliente.post(f"/api/economia/bus/{id_}/cumplio", json={}).status_code == 400


def test_la_mesa_trae_por_juzgar_y_standing(cliente, tmp_path, monkeypatch):
    id_, dep, _ = _sembrar_trabajo_vencido(tmp_path, monkeypatch)
    data = cliente.get("/api/economia/bus").json()
    assert any(p["id"] == id_ for p in data["por_juzgar"])
    # tras juzgarlo, sale de por_juzgar y el standing sube
    cliente.post(f"/api/economia/bus/{id_}/cumplio", json={})
    data2 = cliente.get("/api/economia/bus").json()
    assert not any(p["id"] == id_ for p in data2["por_juzgar"])
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/bin/python -m pytest test_mesa_promesas_server.py -v`
Expected: FAIL — `/cumplio` da 404 (no existe) y `api_eco_bus` no trae `por_juzgar`.

- [ ] **Step 3: Body + helper de juicio**

Junto a `MesaNoMasBody` en `server.py`:

```python
class MesaVeredictoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    palabras: str = ""
```

Import junto a los otros del plantel: `from calipso.plantel import promesas as _plantel_promesas  # noqa: E402`.

Helper compartido (arriba de los endpoints de la mesa):

```python
def _juzgar(id: str, cumplio: bool, palabras: str) -> dict:
    """Pedro juzga si un trabajo cumplio su promesa. Reputacion, no plata:
    no toca el bus ni el libro. Falla 400 si el trabajo no esta vencido o ya
    fue juzgado. El nombre del depto va pelado del prefijo dep: (mismo motivo
    que _anotar_reaccion)."""
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    _, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            m = p0.mercado_fresco()
            bus = _eco_bus.Bus(p0.ruta_bus)
            d = bus.datos(id)
            ops = _eco_cap.semanas_operativas(m.k.libro.asientos())
            dep = d.get("departamento", "")
            nombre = dep.split(":", 1)[1] if ":" in dep else dep
            if not nombre or not _eco_bus.vencida(d, ops, semana):
                raise HTTPException(
                    status_code=400,
                    detail=f"la propuesta {id} no esta lista para juzgar")
            if _plantel_promesas.juzgada(nombre, id):
                raise HTTPException(
                    status_code=400,
                    detail=f"la propuesta {id} ya fue juzgada")
        _plantel_promesas.anotar(nombre, id, d.get("forma"), cumplio, palabras)
    except HTTPException:
        raise
    except _eco_errores_economicos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except _plantel_promesas.ErrorPromesas as exc:
        raise HTTPException(
            status_code=400,
            detail=f"no se pudo registrar el veredicto: {exc}") from None
    return {"ok": True}


@app.post("/api/economia/bus/{id}/cumplio")
def api_eco_bus_cumplio(id: str, body: MesaVeredictoBody) -> dict:
    return _juzgar(id, True, body.palabras)


@app.post("/api/economia/bus/{id}/no-cumplio")
def api_eco_bus_no_cumplio(id: str, body: MesaVeredictoBody) -> dict:
    return _juzgar(id, False, body.palabras)
```

- [ ] **Step 4: `por_juzgar` + `standing` en `api_eco_bus`**

En `api_eco_bus` (`server.py:4215`), dentro del `with _eco_candado(...)`, ya estan `bus`, `semana`, `ops_mesa`, `asientos`. Agregar:

1. Un helper local que degrada (la mesa NO puede tumbarse por un registro de promesas corrupto):

```python
            def _standing_de(dep_crudo: str) -> dict:
                nombre = dep_crudo.split(":", 1)[1] if ":" in dep_crudo else dep_crudo
                try:
                    return _plantel_promesas.standing(nombre) if nombre else {"cumplidas": 0, "total": 0}
                except _plantel_promesas.ErrorPromesas:
                    return {"cumplidas": 0, "total": 0}   # degrada, no 500
```

2. En el armado de cada `fila` de `propuestas` (donde hoy se pone `metrica`), agregar `fila["standing"] = _standing_de(d.get("departamento", ""))`.

3. Una lista nueva `por_juzgar` recorriendo TODOS los ids (independiente del `continue` de alta/financiada), degradando ante corrupto:

```python
            por_juzgar = []
            for id_ in bus.ids():
                d = bus.datos(id_)
                if not _eco_bus.vencida(d, ops_mesa, semana):
                    continue
                dep_crudo = d.get("departamento", "")
                nombre = dep_crudo.split(":", 1)[1] if ":" in dep_crudo else dep_crudo
                try:
                    if not nombre or _plantel_promesas.juzgada(nombre, id_):
                        continue
                except _plantel_promesas.ErrorPromesas:
                    continue   # registro corrupto: la mesa degrada, no 500
                f = d.get("forma") or {}
                por_juzgar.append({
                    "id": id_, "departamento": dep_crudo,
                    "titulo": d.get("titulo", ""),
                    "promete": f.get("promete", ""),
                    "metrica": (_plantel_ficha.METRICA.get(f.get("promete"), "")
                                if _plantel_ficha is not None else ""),
                    "sobre": f.get("sobre", "")})
```

4. Sumar `por_juzgar` al dict de retorno de `api_eco_bus` (junto a `propuestas`, `vencidas`, `departamentos`, etc.).

- [ ] **Step 5: Correr y verificar que pasan**

Run: `.venv/bin/python -m pytest test_mesa_promesas_server.py test_mesa_server.py -v`
Expected: PASS (los nuevos + la mesa existente intacta; si algun test viejo de `api_eco_bus` asertaba las claves exactas del dict, sumar `por_juzgar`/`standing` no deberia romperlo salvo que compare el dict entero -- ajustar y anotar).

- [ ] **Step 6: Commit**

```bash
git add calipso/server.py test_mesa_promesas_server.py
git commit -m "feat(fabrica): endpoints cumplio/no-cumplio y la mesa surface por_juzgar + standing"
```

---

### Task 4: El jefe ve su standing en el prompt

El jefe lee su standing y lo pone en el prompt, para aprender a prometer lo que puede cumplir.

**Files:**
- Modify: `calipso/plantel/jefe.py` — en `tic`, leer `promesas.standing(nombre)` (fallo cerrado) y pasarlo a `dec.prompt`.
- Modify: `calipso/plantel/decision.py` — `prompt(...)` gana `standing: dict | None = None` y rinde un renglon "Tu historial de promesas".
- Test: `test_plantel_decision.py` (agregar), `test_plantel_jefe.py` (agregar).

**Interfaces:**
- Consumes: `promesas.standing(nombre) -> {"cumplidas","total"}` (Task 1).
- Produces: `decision.prompt(..., standing=None)` incluye el renglon cuando `standing["total"] > 0`.

- [ ] **Step 1: Escribir la prueba que falla (decision)**

Agregar a `test_plantel_decision.py`:

```python
def test_el_prompt_rinde_el_standing_de_promesas():
    from calipso.plantel import decision as dec
    s = _situacion_minima()   # helper existente
    p = dec.prompt(s, 50, "", (), standing={"cumplidas": 3, "total": 5})
    assert "promesas" in p.lower()
    assert "3" in p and "5" in p


def test_sin_standing_no_rompe_ni_muestra_renglon():
    from calipso.plantel import decision as dec
    s = _situacion_minima()
    p1 = dec.prompt(s, 50, "", ())                                  # sin standing
    p2 = dec.prompt(s, 50, "", (), standing={"cumplidas": 0, "total": 0})
    assert isinstance(p1, str) and p1
    assert "historial de promesas" not in p2.lower()               # total 0 -> se omite
```

- [ ] **Step 2: Correr y verificar que falla**

Run: `.venv/bin/python -m pytest test_plantel_decision.py::test_el_prompt_rinde_el_standing_de_promesas -v`
Expected: FAIL — `prompt()` no acepta `standing`.

- [ ] **Step 3: Rendir el standing en `decision.prompt`**

En `decision.py`: la firma de `prompt` gana `standing: dict | None = None` (al final, tras `reacciones`). Y se arma un bloque, insertado en el texto del prompt junto a los otros bloques del departamento:

```python
    # El historial de promesas del departamento (el PvP): cuantas cumplio de
    # las que Pedro juzgo. Es para que aprenda a prometer lo que puede
    # cumplir. Se omite si todavia no se juzgo ninguna (total 0).
    bloque_standing = ""
    if standing and standing.get("total", 0) > 0:
        bloque_standing = (f"Tu historial de promesas: cumpliste "
                           f"{standing['cumplidas']} de {standing['total']} "
                           "que Pedro juzgo.\n\n")
```

e insertar `bloque_standing` donde se concatena el prompt (al lado de `bloque_carta`/las reacciones).

- [ ] **Step 4: Correr y verificar que pasan (decision)**

Run: `.venv/bin/python -m pytest test_plantel_decision.py -v`
Expected: PASS (nuevas + viejas).

- [ ] **Step 5: Cablear `jefe.tic`**

En `jefe.py`, en `tic`, junto a la lectura de reacciones (que ya existe, Task 3 del feature anterior), agregar la lectura del standing DENTRO del mismo `try` (fallo cerrado), y pasarlo:

```python
        reacs = reacciones.leer(nombre)
        pvp = promesas.standing(nombre)   # fallo cerrado: corrupto -> el try
                                          # lo vuelve "no armo el prompt"
        p = dec.prompt(s, sesgo, ctx.memoria.load_core(),
                       ctx.memoria.recent(limit=5),
                       carta=ctx.carta,
                       proyectos=dec.proyectos_de(ctx.proyectos, cuenta),
                       reacciones=reacs, standing=pvp)
```

Import `from calipso.plantel import promesas` arriba en `jefe.py` (junto a `reacciones`). Confirmar que `promesas` no importa memory (Task 1) para no arrastrar chromadb.

- [ ] **Step 6: Prueba de jefe + correr el plantel**

Agregar a `test_plantel_jefe.py` una prueba que anota dos veredictos (uno cumplido) para "atlas" con `monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))`, corre `j.tic(ctx, "dep:atlas", W)` con `ctx.pensar` capturando el prompt, y verifica que el prompt contiene "historial de promesas" y los numeros. (Mismo patron que los tests de reacciones via `j.tic`.)

Run: `.venv/bin/python -m pytest test_plantel_decision.py test_plantel_jefe.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add calipso/plantel/jefe.py calipso/plantel/decision.py test_plantel_decision.py test_plantel_jefe.py
git commit -m "feat(fabrica): el jefe ve su historial de promesas en el prompt"
```

---

### Task 5: La UI de la mesa (`calipso/web/fabrica/`)

La mesa muestra la seccion "por juzgar" con los botones cumplio/no cumplio, y el standing al lado de cada propuesta.

**Files:**
- Modify: `calipso/web/fabrica/mesa.js` — renderizar la seccion `por_juzgar` y el `standing` por fila.
- Modify: `calipso/web/fabrica/app.js` — postear `cumplio`/`no-cumplio` con `palabras`.
- Test: `calipso/web/fabrica/mesa.test.js` (agregar).

**Interfaces:**
- Consumes: `por_juzgar` y `standing` del `GET /api/economia/bus` (Task 3); los endpoints `cumplio`/`no-cumplio`.
- Produces: los `fetch` con `{palabras}` y los `data-accion="cumplio"`/`"no-cumplio"`.

- [ ] **Step 1: Escribir la prueba de cliente que falla**

Leer `mesa.test.js` y `mesa.js` para el entry point real de render (el feature anterior uso `textoDeMesa`). Agregar a `mesa.test.js` un test que, con un `data` que incluye `por_juzgar` y `standing`, verifique que el HTML muestra la seccion "por juzgar", los botones `data-accion="cumplio"`/`"no-cumplio"`, y el standing ("3/5" o similar) en una fila.

```javascript
test("la mesa muestra por juzgar y el standing", () => {
  const html = textoDeMesa({ /* propuestas con standing + por_juzgar */ });
  assert.match(html, /data-accion="cumplio"/);
  assert.match(html, /data-accion="no-cumplio"/);
  assert.match(html, /por juzgar/i);
});
```

- [ ] **Step 2: Correr y verificar que falla**

Run (desde `calipso/web/fabrica/`): `node --test mesa.test.js`
Expected: FAIL.

- [ ] **Step 3: Render en `mesa.js`**

- Dibujar la seccion **"por juzgar"** (si `data.por_juzgar` tiene items): por cada uno, el titulo/lo prometido (la `metrica`) + un `<input class="palabras">` opcional + `<button data-accion="cumplio" data-id="...">cumplio</button>` y `<button data-accion="no-cumplio" data-id="...">no cumplio</button>`.
- En cada fila de propuesta, mostrar el `standing` del departamento (`propuesta.standing.cumplidas`/`.total`, p.ej. "3/5") al lado del nombre. Manejar `standing` ausente (fila vieja) sin romper.

- [ ] **Step 4: Postear en `app.js`**

En el handler de la mesa (`app.js`, junto a financiar/descartar/no-mas): agregar ramas `accion === "cumplio"` y `accion === "no-cumplio"` que leen las palabras de la fila (`.querySelector("input.palabras, textarea.palabras")?.value || ""`) y `POST /api/economia/bus/${id}/cumplio` (o `/no-cumplio`) con `{palabras}` y `Content-Type: application/json`. El listener de click ya despacha por `data-accion`.

- [ ] **Step 5: Correr y verificar que pasan (cliente + puente)**

Run (desde `calipso/web/fabrica/`): `node --test`
Expected: PASS (todo el cliente).

Run (raiz): `.venv/bin/python -m pytest test_fabrica_js.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add calipso/web/fabrica/mesa.js calipso/web/fabrica/app.js calipso/web/fabrica/mesa.test.js
git commit -m "feat(fabrica): la mesa muestra por juzgar (cumplio/no cumplio) y el standing por departamento"
```

---

## Notas de verificacion (fuera de las tareas)

- **Suite completa antes de cerrar la rama:** `.venv/bin/python -m pytest -q --ignore=test_chat_live.py` verde + cliente (`node --test` en `calipso/web/fabrica/`). Sin juzgar nada, la fabrica corre como hoy (standing 0/0, sin renglon en el prompt, sin "por juzgar").
- **Smoke en vivo (seguimiento, NO en este plan porque no se reinicia el server):** con la economia sembrada, financiar un trabajo con plazo corto, adelantar la semana, y ver que aparece en "por juzgar"; marcar cumplio y ver el standing subir en la mesa y el renglon en el prompt del jefe.

## Self-Review

**1. Cobertura del spec:**
- Seccion 4 (almacen `promesas.py`: anotar/leer/juzgada/standing, dedup, atomico, fallo cerrado): Task 1. OK.
- Seccion 5 (detectar lo vencido, `bus.vencida`, independiente de liquidacion, por semana_financiada): Task 2. OK.
- Seccion 6 (superficie: por_juzgar + endpoints cumplio/no-cumplio, guardas 400, no toca bus/libro): Task 3. OK.
- Seccion 7 (standing: prompt del jefe + mesa por propuesta): Task 4 (prompt) + Task 3 (mesa). OK.
- Seccion 8 (UI: seccion por juzgar + standing en la fila): Task 5. OK.
- Seccion 9 (invariantes): no mueve plata (T3 no toca libro), juzga una vez (T1 dedup + T3 guarda), preseeds no (T2 vencida), standing afuera del core (T1/T4), no se corrompe (T1 atomico+fallo cerrado), independiente de liquidacion (T2 por semana_financiada), nombre sin prefijo (T3/T4). OK.
- Seccion 10 (lo que NO hace): ninguna tarea mueve plata, ordena la mesa, mide la metrica sola ni agrega panel de revocar. OK.
- Seccion 11 (verificacion): cada punto mapea a pruebas de T1-T5 + smoke anotado. OK.

**2. Placeholders:** el codigo de produccion (T1 modulo, T2 helper, T3 endpoints+mesa, T4 prompt+wiring) va completo. T3/T5 dejan al implementador COMPLETAR helpers de test reusando infraestructura EXISTENTE nombrada (`test_mesa_reacciones_server.py`/`test_mesa_server.py` para sembrar+financiar+adelantar semanas; `mesa.test.js` para el render) — adaptacion a test-harness que ya existe, no logica sin especificar.

**3. Consistencia de tipos:** el veredicto `{ts, propuesta_id, forma, cumplio, palabras}` es lo que escribe `anotar` (T1), lo que anota `_juzgar` (T3), y de lo que salen `juzgada`/`standing` (T1). `standing -> {"cumplidas","total"}` en T1, T3 (mesa), T4 (prompt). `bus.vencida(datos, ops, semana) -> bool` en T2 y sus consumidores T3. `nombre = dep.split(":",1)[1] if ":" in dep else dep` en T3 (endpoint + mesa) y T4 (jefe), igual que el `_anotar_reaccion` existente. Consistente.
