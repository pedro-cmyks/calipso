# La mesa de Pedro — Plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que Pedro vea las propuestas que sus departamentos dejaron en el bus y pueda financiarlas o descartarlas desde el telefono, para que la fabrica deje de apagarse sola al cuarto dia.

**Architecture:** Una transicion nueva en el bus (`alta -> descartada`, terminal, sin plata que devolver), tres endpoints en `server.py` que siguen las convenciones de economia (Pydantic, candado sobre `ruta_libro`, errores traducidos a 400), y un panel nuevo en `/fabrica` con su modulo puro y sus tests de `node --test`. Nada de esto llama a un modelo.

**Tech Stack:** Python 3.14, FastAPI, pytest. JavaScript de modulos ES sin build, probado con `node --test`.

**Spec:** `docs/superpowers/specs/2026-08-26-mesa-de-pedro-design.md`

## Global Constraints

- Cero dependencias nuevas: solo la biblioteca estandar y lo que el repo ya importa.
- Cero emojis, en codigo, comentarios, tests, mensajes de commit y salida.
- Nombres, comentarios y tests en espanol. Los mensajes de commit van sin tildes ni enie.
- El interprete es `/var/home/pedro/calipso/.venv/bin/python`. Node se invoca como `node --test`.
- **Toda lectura y toda escritura del bus van bajo `_eco_candado(p0.ruta_libro)`** — el candado se toma siempre sobre la ruta del LIBRO, nunca sobre `ruta_bus`, aunque el archivo que se escriba sea `bus.jsonl`. El estado (`_economia()`, `mercado_fresco()`, `Bus(...)`) se construye SIEMPRE adentro del candado.
- **Nunca usar `bus.marcar(..., "financiada")` en produccion.** Deja la propuesta financiada con `trabajo:<id>` en cero. Los tests del repo lo usan crudo; no son un ejemplo a copiar.
- Todo lo que entre por `innerHTML` pasa por `escapar()`. El titulo de una propuesta lo escribe un modelo local: es entrada no confiable.
- Todo `fetch` chequea `r.ok` y, si falla, lee `{"detail": ...}` y lo muestra. El molde bueno es `loadSubscriptions` de `calipso/web/index.html`; `loadRoutines` NO, que no mira `r.ok` y hace que un 500 se vea igual que "no hay nada".

---

### Task 1: La transicion que falta

Es la pieza mas chica y la que destraba el problema entero: hoy `_TRANSICIONES["alta"]` solo admite `financiada`, asi que una propuesta que Pedro no quiere no tiene salida, y a las tres el jefe se frena para siempre.

**Files:**
- Modify: `calipso/economia/bus.py`
- Test: `test_economia_bus.py`, `test_plantel_situacion.py`

**Interfaces:**
- Consumes: `Bus.marcar(ts, semana, id, evento)` y `Bus.estado(id)`, que ya existen.
- Produces: `bus.descartar(bus: Bus, ts: str, semana: str, id: str) -> None`, y el estado `"descartada"` como terminal.

- [ ] **Step 1: Escribir los tests del bus**

Agregar al final de `test_economia_bus.py`:

```python
def test_una_propuesta_en_alta_se_puede_descartar(entorno):
    """Sin esto, una propuesta que Pedro no quiere no tiene salida, y el jefe
    se frena para siempre al llegar a su techo de propuestas."""
    k, m, b = entorno
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.descartar(b, TS, "2026-W30", "p1")
    assert b.estado("p1") == "descartada"


def test_descartada_es_terminal(entorno):
    k, m, b = entorno
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.descartar(b, TS, "2026-W30", "p1")
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.descartar(b, TS, "2026-W30", "p1")
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 1_000)


def test_una_financiada_no_se_puede_descartar(entorno):
    """Ahi ya hay plata en trabajo:<id>, y devolverla prorrateada es trabajo
    de evaluar_y_liquidar_muertos, no de una marca cruda."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 50_000)
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.descartar(b, TS, "2026-W30", "p1")


def test_descartar_no_mueve_el_libro(entorno):
    """Nada se transfiere a trabajo:<id> hasta que alguien financia, asi que
    descartar no tiene plata que devolver."""
    k, m, b = entorno
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    antes = len(k.libro.asientos())
    bus_mod.descartar(b, TS, "2026-W30", "p1")
    assert len(k.libro.asientos()) == antes
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_bus.py -q -k descart`
Expected: FAIL con `AttributeError: module 'calipso.economia.bus' has no attribute 'descartar'`

- [ ] **Step 3: Escribir la transicion y la funcion**

En `calipso/economia/bus.py`, cambiar `_TRANSICIONES` para que `"alta"` admita el estado nuevo. Queda asi:

```python
_TRANSICIONES = {
    "alta": frozenset({"financiada", "descartada"}),
    "financiada": frozenset({"muerta"}),
    "muerta": frozenset({"liquidada"}),
}
```

`"descartada"` NO lleva entrada propia: sin entrada, es terminal, igual que `liquidada`.

Y agregar la funcion, al lado de `financiar`:

```python
def descartar(bus: Bus, ts: str, semana: str, id: str) -> None:
    """Pedro dice que no.

    No hay plata que devolver: nada se transfiere a `trabajo:<id>` hasta que
    alguien financia, asi que descartar es solo la marca. Es terminal a
    proposito — en un log append-only, "deshacer" es un estado mas y una regla
    mas; si hace falta una red, que la pida el boton y no el modelo de
    estados. Y no se reusa `muerta` porque mezclaria "nunca arranco" con
    "arranco y fracaso", y el criterio de muerte lee `semana_financiada`, una
    clave que una propuesta en `alta` no tiene.
    """
    bus.marcar(ts, semana, id, "descartada")
```

- [ ] **Step 4: Escribir el test que prueba que el jefe se destraba**

Este es el que justifica la tarea. Agregar al final de `test_plantel_situacion.py`:

```python
def test_una_propuesta_descartada_desaparece_de_las_propias(tmp_path):
    """El jefe tiene un techo de propuestas sin financiar. Descartar una tiene
    que devolverle lugar, o la fabrica se apaga sola al cuarto dia."""
    from calipso.economia import bus as bus_mod
    eco = _entorno(tmp_path)
    b = eco["bus"]
    b.alta(TS, W, "p1", "dep:atlas", "una", 10_000, 10_000,
           {"gasto_max_mm": 10_000})
    antes = sit.situacion(eco["kernel"], eco["registro"], b, eco["cola"],
                          eco["suscripciones"], W, "dep:atlas")
    assert len(antes["propuestas_propias"]) == 1
    bus_mod.descartar(b, TS, W, "p1")
    despues = sit.situacion(eco["kernel"], eco["registro"], b, eco["cola"],
                            eco["suscripciones"], W, "dep:atlas")
    assert despues["propuestas_propias"] == []
```

**Importante:** `test_plantel_situacion.py` ya tiene su propia forma de armar el entorno. Leelo primero y adapta el test a los helpers y nombres que ese archivo ya usa (`TS`, `W`, y como construye kernel/registro/bus/cola/suscripciones). No inventes un `_entorno` si el archivo ya tiene otro nombre para lo mismo; si no existe ninguno, extraelo de los tests que ya estan ahi. Lo que no puede cambiar es lo que el test afirma.

- [ ] **Step 5: Correr y ver que pasan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_bus.py test_plantel_situacion.py -q`
Expected: PASS, sin regresiones en los tests que ya estaban.

- [ ] **Step 6: Commit**

```bash
git add calipso/economia/bus.py test_economia_bus.py test_plantel_situacion.py
git commit -m "feat(bus): descartar una propuesta que Pedro no quiere"
```

---

### Task 2: El lector del bus por HTTP

**Files:**
- Modify: `calipso/server.py`
- Test: `test_mesa_server.py` (crear)

**Interfaces:**
- Consumes: `bus.ids()`, `bus.estado(id)`, `bus.datos(id)`, `bus.gastado(asientos, id)`, `bus.aportes(asientos, id)`, `registro.todos()`, `capacidad.semanas_operativas(asientos)`, y los helpers de `server.py`: `_EcoPagador`, `_ECO_BASE`, `_economia()`, `_eco_ahora()`, `_eco_candado`, `_eco_bus`, `_eco_op`.
- Produces: `GET /api/economia/bus`, con la forma que fija el test de abajo.

Firmas verificadas contra el repo, usalas tal cual:

```
bus.gastado(asientos: list[Asiento], id: str) -> int
bus.aportes(asientos: list[Asiento], id: str) -> dict[str, int]
Registro.todos(self) -> list[Departamento]
capacidad.semanas_operativas(asientos: list[Asiento]) -> list[str]
deps.ZONA_FABRICA == "fabrica"
```

- [ ] **Step 1: Escribir el test**

Crear `test_mesa_server.py`:

```python
"""La mesa de Pedro por HTTP: leer el bus, financiar y descartar."""
import json

import pytest
from fastapi.testclient import TestClient

from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.bus import Bus
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
import calipso.server as srv

TS = "2026-08-26T10:00:00"
W = "2026-W35"


def _economia_de_prueba(base, abrir=True):
    """Una economia minima en disco, como la que arma el bootstrap real."""
    eco = base / "economia"
    eco.mkdir(parents=True, exist_ok=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=25_000))
    r.alta(deps.Departamento("mercado", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=25_000))
    if abrir:
        pt.emitir_semana(k, TS, W, 4_000, 1_000)
    k.acunar(TS, W, "dep:atlas", 400_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 200_000,
                       "capacidad_ciclo": 2_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    return eco


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    _economia_de_prueba(tmp_path)
    return TestClient(srv.app), tmp_path


def _propuesta(base, id="p1", cuenta="dep:atlas", titulo="radar de precios"):
    b = Bus(base / "economia" / "bus.jsonl")
    b.alta(TS, W, id, cuenta, titulo, 10_000, 10_000,
           {"gasto_max_mm": 10_000, "semanas_max": 4})
    return b


def test_el_bus_vacio_devuelve_una_lista_vacia(cliente):
    c, base = cliente
    r = c.get("/api/economia/bus", params={"token": srv.TOKEN})
    assert r.status_code == 200
    d = r.json()
    assert d["activa"] is True
    assert d["propuestas"] == []


def test_una_propuesta_llega_con_lo_que_la_mesa_necesita(cliente):
    c, base = cliente
    _propuesta(base)
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert len(d["propuestas"]) == 1
    p = d["propuestas"][0]
    assert p["id"] == "p1"
    assert p["estado"] == "alta"
    assert p["departamento"] == "dep:atlas"
    assert p["titulo"] == "radar de precios"
    assert p["presupuesto_mm"] == 10_000
    assert p["gastado_mm"] == 0
    assert p["aportes"] == {}


def test_los_departamentos_son_solo_los_de_la_fabrica(cliente):
    """El libro rechaza cualquier financiador fuera de la zona fabrica, asi
    que ofrecer otro en el selector seria ofrecer un boton que falla."""
    c, base = cliente
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    cuentas = {x["cuenta"] for x in d["departamentos"]}
    assert cuentas == {"dep:atlas", "dep:mercado"}
    assert all(x["zona"] == deps.ZONA_FABRICA for x in d["departamentos"])
    atlas = next(x for x in d["departamentos"] if x["cuenta"] == "dep:atlas")
    assert atlas["disponible_mm"] == 400_000


def test_dice_si_la_semana_esta_abierta(tmp_path, monkeypatch):
    """Sin emision de PT esa semana, TODA financiacion falla. Que la mesa lo
    diga antes es la diferencia entre un aviso y un error incomprensible."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    _economia_de_prueba(tmp_path, abrir=False)
    c = TestClient(srv.app)
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["semana_abierta"] is False


def test_sin_economia_no_esta_activa(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    c = TestClient(srv.app)
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["activa"] is False


def test_sin_token_no_se_lee_el_bus(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    c = TestClient(srv.app)
    assert c.get("/api/economia/bus").status_code == 401
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mesa_server.py -q`
Expected: FAIL con 404, porque el endpoint no existe.

- [ ] **Step 3: Escribir el endpoint**

En `calipso/server.py`, justo despues de `api_eco_cola` (el bloque de endpoints de economia), agregar:

```python
@app.get("/api/economia/bus")
def api_eco_bus() -> dict:
    """Lo que Pedro necesita para decidir sobre cada propuesta.

    Lector serializado, como el resto de economia: el libro se repara
    truncando, asi que leerlo a medio append se come un asiento. El unico
    lector sin candado del archivo es `api_eco_cola`, y no es un ejemplo.
    """
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    _, semana = _eco_ahora()
    with _eco_candado(p0.ruta_libro):
        eco = _economia()
        m = eco["pagador"].mercado_fresco()
        bus = _eco_bus.Bus(p0.ruta_bus)
        asientos = m.k.libro.asientos()
        propuestas = []
        for id_ in bus.ids():
            estado = bus.estado(id_)
            # la mesa es para decidir, no un historial: lo descartado, muerto
            # y liquidado no vuelve a aparecer
            if estado not in ("alta", "financiada"):
                continue
            d = bus.datos(id_)
            propuestas.append({
                "id": id_, "estado": estado,
                "departamento": d["departamento_cuenta"],
                "titulo": d["titulo"],
                "presupuesto_mm": d["presupuesto_mm"],
                "retorno_mm": d["retorno_mm"],
                "criterio": d["criterio"],
                "gastado_mm": _eco_bus.gastado(asientos, id_),
                "aportes": _eco_bus.aportes(asientos, id_),
            })
        deps_fabrica = [
            {"cuenta": f"dep:{x.nombre}", "nombre": x.nombre, "zona": x.zona,
             "disponible_mm": m.k.saldo(f"dep:{x.nombre}")}
            for x in m.registro.todos() if x.zona == _eco_deps.ZONA_FABRICA]
        abierta = semana in _eco_cap.semanas_operativas(asientos)
    return {"activa": True, "semana": semana, "semana_abierta": abierta,
            "propuestas": propuestas, "departamentos": deps_fabrica}
```

**Antes de escribirlo, verifica tres cosas leyendo el codigo, y adapta si no coinciden:**

1. Que `bus.datos(id)` devuelva las claves `departamento_cuenta`, `titulo`, `presupuesto_mm`, `retorno_mm` y `criterio`. Si alguna se llama distinto, usa el nombre real.
2. Como se llaman en `server.py` los alias de `calipso.economia.departamentos` y `calipso.economia.capacidad`. Arriba escribi `_eco_deps` y `_eco_cap`, pero **puede que no existan**: mira el bloque de imports de economia (cerca de la linea 3376) y usa los alias que de verdad estan; si el modulo no esta importado, agregalo a ese mismo bloque siguiendo el patron.
3. Como se pide el saldo de una cuenta. Arriba escribi `m.k.saldo(cuenta)`; verifica el nombre real del metodo en `calipso/economia/kernel.py` y usa ese.

- [ ] **Step 4: Correr y ver que pasan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mesa_server.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py test_mesa_server.py
git commit -m "feat(mesa): el lector del bus, serializado bajo el candado"
```

---

### Task 3: Financiar y descartar por HTTP

**Files:**
- Modify: `calipso/server.py`
- Test: `test_mesa_server.py`

**Interfaces:**
- Consumes: lo mismo que la Tarea 2, mas `bus.financiar(mercado, bus, ts, semana, id, financiador_cuenta, mm) -> Asiento` y `bus.descartar(bus, ts, semana, id) -> None` de la Tarea 1.
- Produces: `POST /api/economia/bus/{id}/financiar` con body `{"cuenta": str, "mm": int}`, y `POST /api/economia/bus/{id}/descartar` sin body.

- [ ] **Step 1: Escribir los tests**

Agregar a `test_mesa_server.py`:

```python
def test_financiar_mueve_la_plata_y_marca(cliente):
    c, base = cliente
    _propuesta(base)
    r = c.post("/api/economia/bus/p1/financiar", params={"token": srv.TOKEN},
               json={"cuenta": "dep:atlas", "mm": 10_000})
    assert r.status_code == 200, r.text
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    p = d["propuestas"][0]
    assert p["estado"] == "financiada"
    assert p["aportes"] == {"dep:atlas": 10_000}
    atlas = next(x for x in d["departamentos"] if x["cuenta"] == "dep:atlas")
    assert atlas["disponible_mm"] == 390_000


def test_el_segundo_toque_no_paga_dos_veces(cliente):
    """`financiar` acepta financiar algo ya financiada (es cofinanciacion),
    asi que dos toques en un telefono lento pagarian dos veces. Se cierra por
    construccion: el endpoint solo acepta propuestas en `alta`."""
    c, base = cliente
    _propuesta(base)
    ok = c.post("/api/economia/bus/p1/financiar", params={"token": srv.TOKEN},
                json={"cuenta": "dep:atlas", "mm": 10_000})
    assert ok.status_code == 200
    otra = c.post("/api/economia/bus/p1/financiar", params={"token": srv.TOKEN},
                  json={"cuenta": "dep:atlas", "mm": 10_000})
    assert otra.status_code == 400
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["propuestas"][0]["aportes"] == {"dep:atlas": 10_000}


def test_un_error_del_bus_es_400_con_su_mensaje(tmp_path, monkeypatch):
    """Esta es la primera pantalla de economia cuyos errores los lee un
    humano: "semana no operativa" tiene que llegar como texto, no como un 500
    opaco."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    _economia_de_prueba(tmp_path, abrir=False)
    c = TestClient(srv.app)
    _propuesta(tmp_path)
    r = c.post("/api/economia/bus/p1/financiar", params={"token": srv.TOKEN},
               json={"cuenta": "dep:atlas", "mm": 10_000})
    assert r.status_code == 400
    assert r.json()["detail"]


def test_financiar_una_propuesta_que_no_existe_es_400(cliente):
    c, base = cliente
    r = c.post("/api/economia/bus/fantasma/financiar",
               params={"token": srv.TOKEN},
               json={"cuenta": "dep:atlas", "mm": 1_000})
    assert r.status_code == 400


def test_descartar_libera_el_lugar(cliente):
    c, base = cliente
    _propuesta(base)
    r = c.post("/api/economia/bus/p1/descartar", params={"token": srv.TOKEN})
    assert r.status_code == 200, r.text
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["propuestas"] == []


def test_no_se_descarta_una_ya_financiada(cliente):
    c, base = cliente
    _propuesta(base)
    c.post("/api/economia/bus/p1/financiar", params={"token": srv.TOKEN},
           json={"cuenta": "dep:atlas", "mm": 10_000})
    r = c.post("/api/economia/bus/p1/descartar", params={"token": srv.TOKEN})
    assert r.status_code == 400


def test_sin_token_no_se_financia(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    c = TestClient(srv.app)
    r = c.post("/api/economia/bus/p1/financiar",
               json={"cuenta": "dep:atlas", "mm": 1})
    assert r.status_code == 401
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mesa_server.py -q -k "financiar or descartar"`
Expected: FAIL con 404.

- [ ] **Step 3: Escribir el body y los dos endpoints**

Agregar el body Pydantic junto a los otros de economia (cerca de `EcoAbrirBody`):

```python
class MesaFinanciarBody(BaseModel):
    cuenta: str
    mm: int
```

Y los dos endpoints, despues de `api_eco_bus`:

```python
@app.post("/api/economia/bus/{id}/financiar")
def api_eco_bus_financiar(id: str, body: MesaFinanciarBody) -> dict:
    """Pedro dice que si.

    SOLO acepta propuestas en `alta`. `financiar` permite cofinanciar una ya
    financiada, asi que sin este corte dos toques en un telefono lento
    pagarian dos veces. Deshabilitar el boton en la UI es la segunda linea de
    defensa, no la primera.
    """
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    ts, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            eco = _economia()
            m = eco["pagador"].mercado_fresco()
            bus = _eco_bus.Bus(p0.ruta_bus)
            if bus.estado(id) != "alta":
                raise HTTPException(
                    status_code=400,
                    detail=f"la propuesta {id} ya no esta esperando plata")
            _eco_bus.financiar(m, bus, ts, semana, id, body.cuenta, body.mm)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"ok": True}


@app.post("/api/economia/bus/{id}/descartar")
def api_eco_bus_descartar(id: str) -> dict:
    """Pedro dice que no. Sin esto el jefe se frena al llegar a su techo."""
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    ts, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            bus = _eco_bus.Bus(p0.ruta_bus)
            if bus.estado(id) != "alta":
                raise HTTPException(
                    status_code=400,
                    detail=f"la propuesta {id} ya no se puede descartar")
            _eco_bus.descartar(bus, ts, semana, id)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"ok": True}
```

Fijate en dos detalles que importan: el `except HTTPException: raise` va **antes** del `except Exception`, o el 400 con mensaje bueno se convierte en otro 400 con el mensaje de la excepcion de FastAPI; y `bus.estado(id)` levanta `ErrorBus` para un id inexistente, que el `except Exception` traduce a 400 — que es lo que el test de la propuesta fantasma espera.

- [ ] **Step 4: Correr y ver que pasan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mesa_server.py -q`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py test_mesa_server.py
git commit -m "feat(mesa): financiar y descartar, con los errores traducidos"
```

---

### Task 4: El modulo puro de la mesa

Todo lo que decide QUE se muestra vive aca y es puro; el DOM lo toca `app.js`. Es el mismo reparto que ya usa `paneles.js`.

**Files:**
- Create: `calipso/web/fabrica/mesa.js`
- Test: `calipso/web/fabrica/mesa.test.js`

**Interfaces:**
- Consumes: `escapar` de `./paneles.js` y `monedas` de `./ciudad.js`, que ya existen.
- Produces: `textoDeMesa(datos) -> string` y `hayQueAvisarDeLaSemana(datos) -> boolean`.

- [ ] **Step 1: Escribir el test**

Crear `calipso/web/fabrica/mesa.test.js`:

```js
import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDeMesa, hayQueAvisarDeLaSemana} from "./mesa.js";

const DEPS = [
  {cuenta: "dep:atlas", nombre: "atlas", zona: "fabrica", disponible_mm: 400000},
  {cuenta: "dep:mercado", nombre: "mercado", zona: "fabrica", disponible_mm: 5000},
];

function datos(propuestas, extra = {}) {
  return {activa: true, semana: "2026-W35", semana_abierta: true,
          propuestas, departamentos: DEPS, ...extra};
}

const P1 = {id: "p1", estado: "alta", departamento: "dep:atlas",
            titulo: "radar de precios", presupuesto_mm: 10000,
            retorno_mm: 10000, criterio: {}, gastado_mm: 0, aportes: {}};

test("sin propuestas lo dice, no queda en blanco", () => {
  const html = textoDeMesa(datos([]));
  assert.match(html, /ninguna propuesta|nada que decidir/i);
});

test("una propuesta trae su departamento, su titulo y sus dos botones", () => {
  const html = textoDeMesa(datos([P1]));
  assert.match(html, /atlas/);
  assert.match(html, /radar de precios/);
  assert.match(html, /data-accion="financiar"/);
  assert.match(html, /data-accion="descartar"/);
  assert.match(html, /data-id="p1"/);
});

test("el titulo se escapa: lo escribe un modelo, no es de confianza", () => {
  const malo = {...P1, titulo: '<img src=x onerror="alert(1)">'};
  const html = textoDeMesa(datos([malo]));
  assert.ok(!html.includes("<img"), "se colo una etiqueta del modelo");
  assert.match(html, /&lt;img/);
});

test("el selector ofrece los departamentos y preselecciona al dueno", () => {
  const html = textoDeMesa(datos([P1]));
  assert.match(html, /<option value="dep:atlas" selected/);
  assert.match(html, /<option value="dep:mercado"/);
});

test("un departamento sin plata suficiente queda anotado", () => {
  const html = textoDeMesa(datos([{...P1, departamento: "dep:mercado"}]));
  assert.match(html, /sin saldo|no alcanza/i);
});

test("una financiada muestra lo gastado y no ofrece botones", () => {
  const fin = {...P1, estado: "financiada", gastado_mm: 3000,
               aportes: {"dep:atlas": 10000}};
  const html = textoDeMesa(datos([fin]));
  assert.ok(!html.includes('data-accion="financiar"'));
  assert.ok(!html.includes('data-accion="descartar"'));
  assert.match(html, /financiada/i);
});

test("con la semana cerrada hay que avisar", () => {
  assert.equal(hayQueAvisarDeLaSemana(datos([P1], {semana_abierta: false})), true);
  assert.equal(hayQueAvisarDeLaSemana(datos([P1])), false);
});

test("sin economia activa no se avisa de la semana", () => {
  assert.equal(hayQueAvisarDeLaSemana({activa: false}), false);
});

test("sin economia activa la mesa lo dice", () => {
  assert.match(textoDeMesa({activa: false}), /economia no esta activa/i);
});
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd /var/home/pedro/calipso/calipso/web/fabrica && node --test mesa.test.js`
Expected: FAIL, no existe `mesa.js`.

- [ ] **Step 3: Escribir el modulo**

Crear `calipso/web/fabrica/mesa.js`:

```js
/**
 * calipso/web/fabrica/mesa.js — La mesa de Pedro.
 *
 * Lo que decide QUE se muestra vive aca y es puro; el DOM lo toca app.js.
 * El titulo de una propuesta lo escribe un modelo local, asi que TODO lo que
 * sale por innerHTML pasa por escapar().
 */
import {escapar} from "./paneles.js";
import {monedas} from "./ciudad.js";

function selector(propuesta, departamentos) {
  const opciones = departamentos.map(d => {
    const elegido = d.cuenta === propuesta.departamento ? " selected" : "";
    return `<option value="${escapar(d.cuenta)}"${elegido}>` +
           `${escapar(d.nombre)}</option>`;
  }).join("");
  return `<select class="paga" data-id="${escapar(propuesta.id)}">` +
         `${opciones}</select>`;
}

function alcanza(propuesta, departamentos) {
  const dueno = departamentos.find(d => d.cuenta === propuesta.departamento);
  return !dueno || dueno.disponible_mm >= propuesta.presupuesto_mm;
}

function fila(propuesta, departamentos) {
  const dep = escapar(propuesta.departamento.replace(/^dep:/, ""));
  const plata = escapar(monedas(propuesta.presupuesto_mm));
  if (propuesta.estado === "financiada") {
    const gastado = escapar(monedas(propuesta.gastado_mm));
    return `<div class="propuesta financiada">` +
      `<div class="cabeza"><b>${dep}</b> · ${escapar(propuesta.titulo)}</div>` +
      `<div class="datos">financiada · ${plata} · gastado ${gastado}</div>` +
      `</div>`;
  }
  const aviso = alcanza(propuesta, departamentos)
    ? "" : `<div class="aviso">sin saldo suficiente</div>`;
  return `<div class="propuesta">` +
    `<div class="cabeza"><b>${dep}</b> · ${escapar(propuesta.titulo)}</div>` +
    `<div class="datos">${plata}</div>` + aviso +
    `<div class="acciones">paga ${selector(propuesta, departamentos)}` +
    `<button data-accion="financiar" data-id="${escapar(propuesta.id)}">` +
    `financiar</button>` +
    `<button data-accion="descartar" data-id="${escapar(propuesta.id)}">` +
    `descartar</button></div></div>`;
}

export function hayQueAvisarDeLaSemana(datos) {
  return Boolean(datos && datos.activa && datos.semana_abierta === false);
}

export function textoDeMesa(datos) {
  if (!datos || !datos.activa) {
    return `<div class="vacio">La economia no esta activa.</div>`;
  }
  const deps = datos.departamentos || [];
  const props = datos.propuestas || [];
  const semana = hayQueAvisarDeLaSemana(datos)
    ? `<div class="aviso semana">La semana ${escapar(datos.semana)} no esta ` +
      `abierta: financiar va a fallar hasta que la abras.` +
      `<button data-accion="abrir-semana">abrir la semana</button></div>`
    : "";
  if (!props.length) {
    return semana + `<div class="vacio">Ninguna propuesta esperando.</div>`;
  }
  return semana + props.map(p => fila(p, deps)).join("");
}
```

**Antes de escribirlo, verifica** que `ciudad.js` exporte `monedas` y que reciba milimonedas y devuelva un texto. Si la firma es otra, adapta las llamadas — lo que no puede cambiar es lo que afirman los tests.

- [ ] **Step 4: Correr y ver que pasa**

Run: `cd /var/home/pedro/calipso/calipso/web/fabrica && node --test mesa.test.js`
Expected: PASS (9 tests)

- [ ] **Step 5: Correr la suite entera de /fabrica**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -q`
Expected: PASS, con el piso de tests mas alto que antes.

- [ ] **Step 6: Commit**

```bash
git add calipso/web/fabrica/mesa.js calipso/web/fabrica/mesa.test.js
git commit -m "feat(mesa): el modulo puro que arma la mesa"
```

---

### Task 5: La mesa en la pantalla

**Files:**
- Modify: `calipso/web/fabrica/index.html`
- Modify: `calipso/web/fabrica/estilo.css`
- Modify: `calipso/web/fabrica/app.js`
- Modify: `calipso/web/sw.js`

**Interfaces:**
- Consumes: `textoDeMesa(datos)` y `hayQueAvisarDeLaSemana(datos)` de la Tarea 4; `GET /api/economia/bus`, `POST /api/economia/bus/{id}/financiar` y `POST /api/economia/bus/{id}/descartar` de las Tareas 2 y 3; y `POST /api/economia/abrir`, que ya existe.
- Produces: el panel `#panel-mesa` y la pestana `mesa`.

- [ ] **Step 1: El HTML**

En `calipso/web/fabrica/index.html`, agregar el panel despues de `#panel-mapa` y antes de `<nav id="pestanas">`:

```html
  <section id="panel-mesa" class="panel">
    <div class="titulo"><span>La mesa</span></div>
    <div id="mesa" class="mesa"></div>
  </section>
```

y sumar la pestana dentro de `<nav id="pestanas">`, despues del boton de mapa:

```html
    <button data-pestana="mesa" type="button">Mesa</button>
```

- [ ] **Step 2: El CSS**

En `calipso/web/fabrica/estilo.css`, en la regla de `#app`, la grilla pasa a tener una columna mas:

```css
#app {
  display: grid; height: 100%;
  grid-template-columns: 220px minmax(0, 1fr) minmax(0, 1fr) minmax(0, 320px);
  grid-template-rows: minmax(0, 1fr) var(--barra);
  grid-template-areas: "chats centro mapa mesa" "avisos avisos avisos avisos";
}
```

y al lado de las otras areas:

```css
#panel-mesa { grid-area: mesa; border-right: 0; overflow-y: auto; }
#panel-mapa { grid-area: mapa; }
```

(ojo: `#panel-mapa` hoy tiene `border-right: 0` porque era el ultimo; ahora el ultimo es la mesa, asi que ese `border-right: 0` se mueve.)

Estilos de la mesa, al final del archivo:

```css
.mesa { padding: 8px; display: flex; flex-direction: column; gap: 8px; }
.mesa .propuesta {
  border: 1px solid var(--linea); border-radius: 6px; padding: 8px;
  background: var(--panel);
}
.mesa .propuesta.financiada { opacity: .7; }
.mesa .cabeza { margin-bottom: 4px; }
.mesa .datos { color: var(--tenue); font-size: 12px; }
.mesa .aviso { color: var(--acento); font-size: 12px; margin-top: 4px; }
.mesa .acciones {
  display: flex; align-items: center; gap: 6px; margin-top: 8px;
  flex-wrap: wrap;
}
.mesa .acciones button { cursor: pointer; }
.mesa .vacio { color: var(--tenue); padding: 8px; }
```

En el media query de escritorio ancho (el que tiene `grid-template-areas: "mapa mapa mapa"`), esa fila tiene que pasar a cuatro columnas: `"mapa mapa mapa mapa"` y `"avisos avisos avisos avisos"`. Y agregar `#panel-mesa` a la lista de paneles que se ocultan en `#app.mapa-entero`.

En el media query de telefono (max-width 820px):

```css
  #panel-chats { display: none; }
  #panel-centro, #panel-mapa, #panel-mesa { grid-area: centro; border-right: 0; }
  #app[data-pestana="chat"] #panel-mapa,
  #app[data-pestana="chat"] #panel-mesa { display: none; }
  #app[data-pestana="mapa"] #panel-centro,
  #app[data-pestana="mapa"] #panel-mesa { display: none; }
  #app[data-pestana="mesa"] #panel-centro,
  #app[data-pestana="mesa"] #panel-mapa { display: none; }
  #pestanas { grid-template-columns: 1fr 1fr 1fr; }
```

(la regla de `#pestanas` ya existe con `1fr 1fr`; hay que cambiarla, no duplicarla.)

- [ ] **Step 3: El cableado en app.js**

Importar arriba, junto a los otros imports:

```js
import {textoDeMesa} from "./mesa.js";
```

y agregar, cerca de donde vive el resto de la logica de paneles:

```js
const cajaMesa = document.getElementById("mesa");

async function pintarMesa() {
  try {
    const r = await fetch("/api/economia/bus");
    if (!r.ok) {
      cajaMesa.innerHTML = '<div class="vacio">No se pudo leer el bus.</div>';
      return;
    }
    cajaMesa.innerHTML = textoDeMesa(await r.json());
  } catch (_) {
    cajaMesa.innerHTML = '<div class="vacio">No se pudo leer el bus.</div>';
  }
}

async function accionDeMesa(boton) {
  const accion = boton.dataset.accion;
  const id = boton.dataset.id;
  boton.disabled = true;
  try {
    let r;
    if (accion === "abrir-semana") {
      r = await fetch("/api/economia/abrir", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({cuota_firmable_mpt: 4000,
                              reserva_personal_mpt: 1000})});
    } else if (accion === "financiar") {
      const sel = cajaMesa.querySelector(`select.paga[data-id="${id}"]`);
      const fila = boton.closest(".propuesta");
      const mm = Number(fila?.dataset.presupuesto || 0);
      r = await fetch(`/api/economia/bus/${encodeURIComponent(id)}/financiar`, {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({cuenta: sel ? sel.value : "", mm})});
    } else if (accion === "descartar") {
      r = await fetch(`/api/economia/bus/${encodeURIComponent(id)}/descartar`,
                      {method: "POST"});
    } else {
      return;
    }
    if (!r.ok) {
      let detalle = "no se pudo";
      try { detalle = (await r.json()).detail || detalle; } catch (_) {}
      alert(detalle);
    }
  } finally {
    boton.disabled = false;
    await pintarMesa();
  }
}

cajaMesa.addEventListener("click", evento => {
  const boton = evento.target.closest("button[data-accion]");
  if (boton) accionDeMesa(boton);
});
```

Llamar `pintarMesa()` una vez al arrancar, donde el archivo ya hace su carga inicial de datos.

**Ojo con el `mm`:** el codigo de arriba lo lee de `fila.dataset.presupuesto`, asi que `mesa.js` tiene que ponerlo. En la Tarea 4 el `<div class="propuesta">` no lo lleva. **Agregalo**: que el div de una propuesta financiable sea
`<div class="propuesta" data-presupuesto="${escapar(propuesta.presupuesto_mm)}">`
y sumale un test en `mesa.test.js` que lo afirme. Sin eso, financiar manda `mm: 0` y el libro lo rechaza.

- [ ] **Step 4: El service worker**

En `calipso/web/sw.js`, agregar al array `SHELL`:

```js
  "/static/fabrica/mesa.js",
```

Un archivo que no esta en `SHELL` no existe offline.

- [ ] **Step 5: Correr los tests**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py test_ui.py -q`
Expected: PASS. Si `test_ui.py` o el test del `SHELL` se derivan de los archivos reales del directorio, van a exigir que el archivo nuevo este listado; ese es el punto.

- [ ] **Step 6: Commit**

```bash
git add calipso/web/fabrica/index.html calipso/web/fabrica/estilo.css \
        calipso/web/fabrica/app.js calipso/web/fabrica/mesa.js \
        calipso/web/fabrica/mesa.test.js calipso/web/sw.js
git commit -m "feat(mesa): la mesa en la pantalla, con su pestana y su panel"
```

---

### Task 6: La tira del plantel y el enlace que falta

**Files:**
- Modify: `calipso/web/fabrica/index.html`
- Modify: `calipso/web/fabrica/estilo.css`
- Modify: `calipso/web/fabrica/app.js`
- Modify: `calipso/web/index.html`

**Interfaces:**
- Consumes: `GET /api/plantel`, `POST /api/plantel/parar`, `POST /api/plantel/reanudar`, `PUT /api/plantel/modo` con body `{"modo": "ensayo"|"vivo"}`, y `POST /api/routines` con `{"kind": "departamento", "label", "interval_minutes", "enabled", "cuenta"}`. Todos existen.
- Produces: la tira de controles arriba de la mesa, y un enlace de `/` a `/fabrica`.

- [ ] **Step 1: El HTML de la tira**

En `calipso/web/fabrica/index.html`, dentro de `#panel-mesa`, antes de `<div id="mesa">`:

```html
    <div id="plantel" class="plantel"></div>
```

- [ ] **Step 2: El CSS**

Al final de `calipso/web/fabrica/estilo.css`:

```css
.plantel {
  padding: 8px; border-bottom: 1px solid var(--linea);
  display: flex; flex-direction: column; gap: 6px;
}
.plantel .estado { color: var(--tenue); font-size: 12px; }
.plantel .botones { display: flex; gap: 6px; flex-wrap: wrap; }
.plantel button, .plantel select, .plantel input { cursor: pointer; }
.plantel .peligro { color: var(--acento); font-size: 12px; }
.plantel form { display: flex; gap: 6px; flex-wrap: wrap; }
.plantel input { min-width: 0; flex: 1 1 90px; }
```

- [ ] **Step 3: El cableado**

En `calipso/web/fabrica/app.js`:

```js
const cajaPlantel = document.getElementById("plantel");

function textoDePlantel(estado) {
  if (!estado || estado.activo === false) {
    return '<div class="estado">El plantel no esta disponible.</div>';
  }
  const prendido = estado.encendido ? "encendido" : "apagado";
  const peligro = estado.modo === "vivo"
    ? '<div class="peligro">En vivo: la fabrica gasta sola.</div>' : "";
  return `<div class="estado">${prendido} · modo ${escapar(estado.modo)} ` +
    `· techo ${escapar(String(estado.techo_tics))} tics</div>` + peligro +
    `<div class="botones">` +
    `<button data-plantel="parar">parar</button>` +
    `<button data-plantel="reanudar">reanudar</button>` +
    `<button data-plantel="modo" data-modo="${estado.modo === "vivo"
      ? "ensayo" : "vivo"}">pasar a ${estado.modo === "vivo"
      ? "ensayo" : "vivo"}</button>` +
    `</div>` +
    `<form data-plantel="rutina">` +
    `<input name="cuenta" placeholder="dep:atlas" required>` +
    `<input name="minutos" type="number" value="60" min="1" required>` +
    `<button type="submit">crear rutina</button></form>`;
}

async function pintarPlantel() {
  try {
    const r = await fetch("/api/plantel");
    cajaPlantel.innerHTML = textoDePlantel(r.ok ? await r.json() : null);
  } catch (_) {
    cajaPlantel.innerHTML = textoDePlantel(null);
  }
}

cajaPlantel.addEventListener("click", async evento => {
  const boton = evento.target.closest("button[data-plantel]");
  if (!boton || boton.type === "submit") return;
  const que = boton.dataset.plantel;
  boton.disabled = true;
  try {
    if (que === "modo") {
      await fetch("/api/plantel/modo", {
        method: "PUT", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({modo: boton.dataset.modo})});
    } else {
      await fetch(`/api/plantel/${que}`, {method: "POST"});
    }
  } finally {
    boton.disabled = false;
    await pintarPlantel();
  }
});

cajaPlantel.addEventListener("submit", async evento => {
  evento.preventDefault();
  const form = evento.target;
  const cuenta = form.cuenta.value.trim();
  const minutos = Number(form.minutos.value);
  const r = await fetch("/api/routines", {
    method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({kind: "departamento", label: `jefe de ${cuenta}`,
                          interval_minutes: minutos, enabled: true,
                          cuenta})});
  if (!r.ok) {
    let detalle = "no se pudo crear la rutina";
    try { detalle = (await r.json()).detail || detalle; } catch (_) {}
    alert(detalle);
  } else {
    form.reset();
  }
});
```

Importar `escapar` desde `./paneles.js` si `app.js` todavia no lo importa, y llamar `pintarPlantel()` en el arranque, al lado de `pintarMesa()`.

- [ ] **Step 4: El enlace que falta**

Hoy no hay un solo enlace entre `/` y `/fabrica`, asi que la mesa existe y no se encuentra. En `calipso/web/index.html`, agregar **una linea** en la barra de herramientas de arriba, al lado de los botones que ya estan:

```html
<a class="toolbtn" href="/fabrica" title="La fabrica y la mesa">Fabrica</a>
```

Es la unica modificacion permitida a la UI vieja. Buscá donde estan los otros `.toolbtn` y ponelo al lado, siguiendo el mismo estilo.

- [ ] **Step 5: Correr los tests**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py test_ui.py -q`
Expected: PASS

- [ ] **Step 6: La suite entera**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest -q --ignore=test_chat_live.py`
Expected: PASS (`test_chat_live.py` se ignora a proposito: se conecta a un server vivo al coleccionar y es preexistente).

- [ ] **Step 7: Commit**

```bash
git add calipso/web/fabrica/index.html calipso/web/fabrica/estilo.css \
        calipso/web/fabrica/app.js calipso/web/index.html
git commit -m "feat(mesa): la tira del plantel y el enlace desde la UI vieja"
```
