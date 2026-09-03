# Siembra guiada de la economia — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un helper guiado de un solo tiro que corre los 7 pasos que prenden la economia (sembrar padron -> abrir semana -> acuñar al tesoro -> perillas -> rutina por depto -> vivo), re-entrante, con preview/confirmacion antes del acto irreversible.

**Architecture:** Un orquestador `calipso/siembra.py` (arriba de economia: importa routines + plantel.interruptor) que reusa los primitivos existentes y corre los pasos guardados por "ya esta hecho?". Un endpoint `POST /api/economia/sembrar-guiado` que, sin token, devuelve el PLAN (preview, no escribe), y con el token exacto ejecuta. Se ensaya en un home desechable antes de que Pedro toque su economia real.

**Tech Stack:** Python 3.14, pytest, FastAPI/pydantic. Escritor atomico + candado reentrante (`calipso/economia/candado.py`).

**Spec:** `docs/superpowers/specs/2026-09-03-siembra-guiada-design.md`

## Global Constraints

- **La siembra es un acto de Pedro.** El helper sin el token exacto `"sembrar la economia"` SOLO hace preview (no escribe). NUNCA correr `sembrar-guiado` en modo ejecutar contra el home real de Pedro; el ensayo es en un home desechable.
- **Re-entrante:** cada paso se guarda por "ya esta hecho?" (padron existe, semana en `semanas_operativas`, tesoro con saldo, rutina presente, modo). Re-llamar completa lo que falte sin romper ni duplicar.
- **Reusa los primitivos, no los reimplementa.** Firmas EXACTAS (del mapa):
  - Pagador crudo: `Pagador(base / "economia")` con `.ruta_libro/.ruta_registro/.ruta_sus/.ruta_bus`, `.leer_kernel() -> Kernel`, `.mercado_fresco() -> Mercado(.k,.registro,.suscripciones)`. `desde_entorno(base)` da `None` hasta sembrar.
  - Padron (paso 2): `Registro(p.ruta_registro)` + `registro.alta(Departamento(**d))` por depto; `p.ruta_sus.write_text(json...)`; `p.ruta_libro.touch()`. Todo bajo `candado(p.ruta_libro)`.
  - Abrir (paso 3): guardar `semana in capacidad.semanas_operativas(asientos)` ANTES de `operacion.abrir_semana(k, ts, semana, cuota_firmable_mpt, reserva_personal_mpt, suscripciones=)` — **levanta `ErrorPT` si la semana ya esta abierta**.
  - Acuñar (paso 4): `saldo = p.leer_kernel().saldo(tipos.TESORO)`; si `saldo < capital` -> `p.leer_kernel().acunar(ts, semana, "tesoro", capital - saldo, tipos.SubtipoAcunacion.CAPITAL, {"tipo": "genesis"})` bajo `candado(p.ruta_libro)`. `acunar` exige `evidencia` no vacia.
  - Perillas (paso 5): `Registro(p.ruta_registro).ajustar(nombre, **perillas)` bajo candado (persiste; solo perillas numericas).
  - Rutina (paso 6): `routines.add("departamento", label, interval, enabled=True, cuenta=f"dep:{nombre}")`; idempotente = escanear `routines.load()` por `kind=="departamento"` y `cuenta` igual.
  - Vivo (paso 7): `interruptor.poner_modo(base, "vivo")` (base = el HOME, no el dir economia; `ruta()` le agrega `economia/` solo). Idempotente.
- **`calipso/siembra.py` NO importa `calipso.server` ni `calipso.memory`** (chromadb). Importa `calipso.routines`, `calipso.economia.*`, `calipso.plantel.interruptor`.
- **SIN EMOJIS.** Comentarios/docstrings en espanol. Commits sin tildes ni ene, sin emojis.
- **NUNCA importar `calipso` fuera de pytest.** Tests aislan `CALIPSO_HOME` con `monkeypatch.setenv(..., str(tmp_path))` y el server con `monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)` + `monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))`.
- **No reiniciar el server.** El ensayo en vivo queda para el smoke de cierre.
- **Correr la SUITE COMPLETA antes de cada commit** (`.venv/bin/python -m pytest -q --ignore=test_chat_live.py`).

---

### Task 1: El orquestador (`calipso/siembra.py`)

Corre los 7 pasos re-entrante y arma el reporte. Puro respecto del server (testeable con un home temporal, sin HTTP).

**Files:**
- Create: `calipso/siembra.py`
- Test: `test_siembra.py`

**Interfaces:**
- Consumes: los primitivos de las Global Constraints.
- Produces:
  - `CONFIRMACION = "sembrar la economia"`.
  - `estado(base, semana) -> dict` — que pasos ya estan hechos: `{"sembrada": bool, "tesoro_mm": int, "semana_abierta": bool, "rutinas": [cuenta...], "modo": str}`.
  - `sembrar_guiado(base, config: dict, ts: str, semana: str, ejecutar: bool) -> dict` — sin `ejecutar` devuelve `{"plan": config, "estado": estado(...)}`; con `ejecutar` corre los pasos y devuelve `{"ok": True, "pasos": [{"paso","accion"}...], "estado": estado(...)}`.
- Config shape: `{"departamentos": [{nombre, zona, presupuesto_semanal_mm, techo_api_ciclo_mm, explorar_explotar_pct, agresividad_pct, techo_preseed_mm, techo_preseed_ciclo_mm}...], "suscripciones": {nombre: {capacidad_ciclo, ...}}, "capital_tesoro_mm": int, "cuota_firmable_mpt": int, "reserva_personal_mpt": int, "rutina_interval_min": int}`.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `test_siembra.py`:

```python
# test_siembra.py -- el orquestador de la siembra guiada, sin HTTP.
import pytest

from calipso.economia import capacidad as cap
from calipso.economia import tipos as t
from calipso.economia.pagador import Pagador
from calipso.plantel import interruptor as it
from calipso import routines

TS = "2026-08-26T10:00:00"
W = "2026-W35"


def _config():
    return {
        "departamentos": [
            {"nombre": "taller", "zona": "fabrica"},
            {"nombre": "development", "zona": "fabrica"},
            {"nombre": "research", "zona": "fabrica"},
            {"nombre": "finanzas", "zona": "personal"},
        ],
        "suscripciones": {"claude_max": {"costo_mensual_mm": 200_000,
                                         "capacidad_ciclo": 2_000,
                                         "reserva_personal": 200,
                                         "costo_api_mm_por_unidad": 500}},
        "capital_tesoro_mm": 100_000,
        "cuota_firmable_mpt": 4_000,
        "reserva_personal_mpt": 1_000,
        "rutina_interval_min": 60,
        "perillas_fabrica": {"presupuesto_semanal_mm": 25_000,
                             "techo_preseed_mm": 50_000,
                             "techo_preseed_ciclo_mm": 150_000,
                             "techo_api_ciclo_mm": 0},
    }


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    # routines.py resuelve su archivo desde CALIPSO_HOME en tiempo de llamada;
    # si no, revisar como fija su ruta y aislarla igual.
    return tmp_path


def test_preview_no_escribe_nada(home):
    from calipso import siembra
    r = siembra.sembrar_guiado(str(home), _config(), TS, W, ejecutar=False)
    assert "plan" in r and "estado" in r
    assert r["estado"]["sembrada"] is False
    assert not (home / "economia").exists()   # NADA se escribio


def test_ejecutar_corre_los_siete_pasos(home):
    from calipso import siembra
    r = siembra.sembrar_guiado(str(home), _config(), TS, W, ejecutar=True)
    assert r["ok"] is True
    p = Pagador(home / "economia")
    # padron
    assert p.ruta_registro.exists() and p.ruta_sus.exists() and p.ruta_libro.exists()
    reg = __import__("calipso.economia.departamentos", fromlist=["Registro"]).Registro(p.ruta_registro)
    assert {d.nombre for d in reg.todos()} == {"taller", "development", "research", "finanzas"}
    # semana abierta
    asientos = p.leer_kernel().libro.asientos()
    assert W in cap.semanas_operativas(asientos)
    # tesoro con capital
    assert p.leer_kernel().saldo(t.TESORO) == 100_000
    # perillas puestas en los de fabrica (pre-seed > 0, api_ciclo = 0)
    taller = reg.obtener("taller")
    assert taller.techo_preseed_mm == 50_000 and taller.techo_preseed_ciclo_mm == 150_000
    assert taller.techo_api_ciclo_mm == 0
    # una rutina departamento por depto de fabrica
    deptos_rutina = {r_.get("cuenta") for r_ in routines.load() if r_.get("kind") == "departamento"}
    assert deptos_rutina == {"dep:taller", "dep:development", "dep:research"}
    # modo vivo
    assert it.leer(str(home)).modo == "vivo"


def test_re_entrante_no_duplica_ni_rompe(home):
    from calipso import siembra
    siembra.sembrar_guiado(str(home), _config(), TS, W, ejecutar=True)
    # segunda corrida: saltea todo lo hecho, no duplica, no levanta
    r2 = siembra.sembrar_guiado(str(home), _config(), TS, W, ejecutar=True)
    assert r2["ok"] is True
    p = Pagador(home / "economia")
    assert p.leer_kernel().saldo(t.TESORO) == 100_000   # NO re-acuño
    deptos = [r_ for r_ in routines.load() if r_.get("kind") == "departamento"]
    assert len(deptos) == 3                              # NO duplico rutinas


def test_finanzas_no_lleva_rutina_ni_perillas_de_fabrica(home):
    from calipso import siembra
    siembra.sembrar_guiado(str(home), _config(), TS, W, ejecutar=True)
    cuentas = {r_.get("cuenta") for r_ in routines.load() if r_.get("kind") == "departamento"}
    assert "personal:finanzas" not in cuentas and "dep:finanzas" not in cuentas
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/bin/python -m pytest test_siembra.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'calipso.siembra'`

- [ ] **Step 3: Escribir `calipso/siembra.py`**

```python
"""Siembra guiada: orquesta los 7 pasos que prenden la economia de la
fabrica, en orden, re-entrante (se puede re-llamar para completar lo que
falte). Reusa los primitivos existentes, no los reimplementa. Vive arriba
de economia (importa routines y plantel.interruptor), por eso NO esta en
calipso/economia/. NO importa calipso.server ni calipso.memory.

El paso 2 (el padron) es el unico irreversible; los demas son idempotentes.
"""
from __future__ import annotations

import json
import pathlib

from calipso import routines
from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import operacion as op
from calipso.economia import tipos as tipos
from calipso.economia.candado import candado
from calipso.economia.pagador import Pagador
from calipso.plantel import interruptor as it

CONFIRMACION = "sembrar la economia"


def _pagador(base) -> Pagador:
    return Pagador(pathlib.Path(base) / "economia")


def _fabrica(config: dict) -> list[dict]:
    return [d for d in config["departamentos"] if d.get("zona") == "fabrica"]


def estado(base, semana: str) -> dict:
    """Que pasos ya estan hechos. Sirve para el preview y para la
    re-entrancia."""
    p = _pagador(base)
    sembrada = (p.ruta_registro.exists() and p.ruta_libro.exists()
                and p.ruta_sus.exists())
    est = {"sembrada": sembrada, "tesoro_mm": 0, "semana_abierta": False,
           "rutinas": [], "modo": it.leer(str(base)).modo}
    if sembrada:
        k = p.leer_kernel()
        asientos = k.libro.asientos()
        est["tesoro_mm"] = k.saldo(tipos.TESORO)
        est["semana_abierta"] = semana in cap.semanas_operativas(asientos)
    est["rutinas"] = [r.get("cuenta") for r in routines.load()
                      if r.get("kind") == "departamento"]
    return est


def sembrar_guiado(base, config: dict, ts: str, semana: str,
                   ejecutar: bool) -> dict:
    """Corre (o previsualiza) los 7 pasos. Sin `ejecutar`: devuelve el plan
    y el estado, sin escribir NADA. Con `ejecutar`: corre los pasos que
    falten y devuelve el reporte paso a paso."""
    if not ejecutar:
        return {"plan": config, "estado": estado(base, semana)}

    p = _pagador(base)
    pasos: list[dict] = []
    perillas = config["perillas_fabrica"]

    with candado(p.ruta_libro):
        # PASO 2 -- el padron (irreversible). Reusa el camino de `sembrar`.
        if not (p.ruta_registro.exists() and p.ruta_libro.exists()
                and p.ruta_sus.exists()):
            p.eco.mkdir(parents=True, exist_ok=True)
            registro = deps.Registro(p.ruta_registro)
            for d in config["departamentos"]:
                registro.alta(deps.Departamento(**d))
            sus = {n: cap.Suscripcion(nombre=n, **s)
                   for n, s in config["suscripciones"].items()}
            import dataclasses
            p.ruta_sus.write_text(
                json.dumps({n: dataclasses.asdict(s) for n, s in sus.items()},
                           ensure_ascii=False, indent=1), encoding="utf-8")
            p.ruta_libro.touch()
            pasos.append({"paso": "padron", "accion": "sembrado"})
        else:
            pasos.append({"paso": "padron", "accion": "ya estaba (saltea)"})

        # PASO 3 -- abrir la primera semana (antes de acuñar). Idempotente:
        # abrir_semana LEVANTA si la semana ya esta abierta.
        m = p.mercado_fresco()
        if semana not in cap.semanas_operativas(m.k.libro.asientos()):
            op.abrir_semana(m.k, ts, semana, config["cuota_firmable_mpt"],
                            config["reserva_personal_mpt"],
                            suscripciones=m.suscripciones)
            pasos.append({"paso": "semana", "accion": "abierta"})
        else:
            pasos.append({"paso": "semana", "accion": "ya abierta (saltea)"})

        # PASO 4 -- acuñar el capital de genesis al tesoro. Idempotente:
        # solo el faltante.
        k = p.leer_kernel()
        saldo = k.saldo(tipos.TESORO)
        objetivo = int(config["capital_tesoro_mm"])
        if saldo < objetivo:
            k.acunar(ts, semana, tipos.TESORO, objetivo - saldo,
                     tipos.SubtipoAcunacion.CAPITAL, {"tipo": "genesis"})
            pasos.append({"paso": "tesoro", "accion": f"acuñado {objetivo - saldo} mm"})
        else:
            pasos.append({"paso": "tesoro", "accion": "ya tenia capital (saltea)"})

        # PASO 5 -- perillas de cada depto de FABRICA. Idempotente.
        registro = deps.Registro(p.ruta_registro)
        for d in _fabrica(config):
            registro.ajustar(d["nombre"], **perillas)
        pasos.append({"paso": "perillas", "accion": f"{len(_fabrica(config))} deptos"})

    # PASO 6 -- una rutina departamento por depto de fabrica (archivo aparte).
    existentes = {r.get("cuenta") for r in routines.load()
                  if r.get("kind") == "departamento"}
    nuevas = 0
    for d in _fabrica(config):
        cuenta = f"dep:{d['nombre']}"
        if cuenta not in existentes:
            routines.add("departamento", f"jefe {d['nombre']}",
                         config["rutina_interval_min"], enabled=True,
                         cuenta=cuenta)
            nuevas += 1
    pasos.append({"paso": "rutinas", "accion": f"{nuevas} nuevas"})

    # PASO 7 -- plantel a vivo (archivo aparte).
    it.poner_modo(str(base), "vivo")
    pasos.append({"paso": "modo", "accion": "vivo"})

    return {"ok": True, "pasos": pasos, "estado": estado(base, semana)}
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `.venv/bin/python -m pytest test_siembra.py -v`
Expected: PASS (5 pruebas). Si `routines.load()` no resuelve su archivo desde `CALIPSO_HOME` (revisar `routines.py`), aislar su ruta en el fixture del modo que corresponda y anotarlo.

- [ ] **Step 5: Suite completa + commit**

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py`
Expected: verde.

```bash
git add calipso/siembra.py test_siembra.py
git commit -m "feat(economia): orquestador de siembra guiada (7 pasos, re-entrante)"
```

---

### Task 2: El endpoint `POST /api/economia/sembrar-guiado`

Preview sin token; ejecuta con el token exacto. Auth por el middleware existente.

**Files:**
- Modify: `calipso/server.py` — un body `EcoSembrarGuiadoBody`; el endpoint; import `from calipso import siembra as _siembra`.
- Test: `test_siembra_server.py`

**Interfaces:**
- Consumes: `siembra.sembrar_guiado(base, config, ts, semana, ejecutar)` y `siembra.CONFIRMACION` (Task 1); `_ECO_BASE`, `_eco_ahora`, `_eco_errores_economicos` (server).
- Produces: `POST /api/economia/sembrar-guiado` — body con la config + `confirmacion: str = ""`. Sin/incorrecta confirmacion -> preview (200, no escribe). Con la exacta -> ejecuta (200). Un error economico -> 400.

- [ ] **Step 1: Escribir las pruebas que fallan**

Crear `test_siembra_server.py` (usar el patron de auth y aislamiento de `test_economia_sembrado.py` / `test_siembra.py`):

```python
# test_siembra_server.py
import pytest

import calipso.server as srv
from fastapi.testclient import TestClient

TS = "2026-08-26T10:00:00"
W = "2026-W35"


@pytest.fixture
def cliente(monkeypatch, tmp_path):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def _body(confirmacion=""):
    return {
        "confirmacion": confirmacion,
        "departamentos": [
            {"nombre": "taller", "zona": "fabrica"},
            {"nombre": "development", "zona": "fabrica"},
            {"nombre": "research", "zona": "fabrica"},
            {"nombre": "finanzas", "zona": "personal"}],
        "suscripciones": {"claude_max": {"costo_mensual_mm": 200_000,
                                         "capacidad_ciclo": 2_000,
                                         "reserva_personal": 200,
                                         "costo_api_mm_por_unidad": 500}},
        "capital_tesoro_mm": 100_000,
        "cuota_firmable_mpt": 4_000, "reserva_personal_mpt": 1_000,
        "rutina_interval_min": 60,
        "perillas_fabrica": {"presupuesto_semanal_mm": 25_000,
                             "techo_preseed_mm": 50_000,
                             "techo_preseed_ciclo_mm": 150_000,
                             "techo_api_ciclo_mm": 0}}


def test_preview_sin_token_no_escribe(cliente, tmp_path):
    r = cliente.post("/api/economia/sembrar-guiado", json=_body())
    assert r.status_code == 200
    assert r.json()["estado"]["sembrada"] is False
    assert not (tmp_path / "economia").exists()


def test_token_incorrecto_no_ejecuta(cliente, tmp_path):
    r = cliente.post("/api/economia/sembrar-guiado", json=_body("dale"))
    assert r.status_code == 400
    assert not (tmp_path / "economia").exists()


def test_token_exacto_ejecuta(cliente, tmp_path):
    r = cliente.post("/api/economia/sembrar-guiado",
                     json=_body("sembrar la economia"))
    assert r.status_code == 200
    j = r.json()
    assert j["ok"] is True
    assert j["estado"]["sembrada"] is True and j["estado"]["modo"] == "vivo"
    assert (tmp_path / "economia" / "departamentos.json").exists()
```

- [ ] **Step 2: Correr y verificar que fallan**

Run: `.venv/bin/python -m pytest test_siembra_server.py -v`
Expected: FAIL (404: el endpoint no existe).

- [ ] **Step 3: Body + endpoint en `server.py`**

Import junto a los otros del paquete (donde estan los aliases de economia): `from calipso import siembra as _siembra  # noqa: E402`.

Body (junto a `EcoSembrarBody`):

```python
class EcoSembrarGuiadoBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmacion: str = ""
    departamentos: list[EcoSembrarDepartamentoBody]
    suscripciones: dict[str, EcoSembrarSuscripcionBody] = {}
    capital_tesoro_mm: int = Field(ge=0, le=_MAX_MM)
    cuota_firmable_mpt: int = Field(gt=0, le=_MAX_MM)
    reserva_personal_mpt: int = Field(default=0, ge=0, le=_MAX_MM)
    rutina_interval_min: int = Field(default=60, ge=1)
    perillas_fabrica: EcoSembrarPerillasBody

    sin_booleanos = field_validator("*", mode="before")(_no_booleano)


class EcoSembrarPerillasBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    presupuesto_semanal_mm: int = Field(default=0, ge=0, le=_MAX_MM)
    techo_preseed_mm: int = Field(default=0, ge=0, le=_MAX_MM)
    techo_preseed_ciclo_mm: int = Field(default=0, ge=0, le=_MAX_MM)
    techo_api_ciclo_mm: int = Field(default=0, ge=0, le=_MAX_MM)
```

(Definir `EcoSembrarPerillasBody` ANTES de `EcoSembrarGuiadoBody`. Reusar `EcoSembrarDepartamentoBody`/`EcoSembrarSuscripcionBody` que ya existen.)

Endpoint:

```python
@app.post("/api/economia/sembrar-guiado")
def api_eco_sembrar_guiado(body: EcoSembrarGuiadoBody) -> dict:
    """Helper guiado de un solo tiro. Sin `confirmacion` -> PREVIEW (no
    escribe). Con la frase exacta -> ejecuta los 7 pasos, re-entrante. La
    siembra es un acto de Pedro; el preview es la red antes del acto
    irreversible (el padron)."""
    if _siembra is None:
        raise HTTPException(status_code=400,
                            detail="la economia no esta disponible")
    ts, semana = _eco_ahora()
    config = {
        "departamentos": [d.model_dump() for d in body.departamentos],
        "suscripciones": {n: s.model_dump()
                          for n, s in body.suscripciones.items()},
        "capital_tesoro_mm": body.capital_tesoro_mm,
        "cuota_firmable_mpt": body.cuota_firmable_mpt,
        "reserva_personal_mpt": body.reserva_personal_mpt,
        "rutina_interval_min": body.rutina_interval_min,
        "perillas_fabrica": body.perillas_fabrica.model_dump()}
    ejecutar = body.confirmacion == _siembra.CONFIRMACION
    if body.confirmacion and not ejecutar:
        raise HTTPException(
            status_code=400,
            detail=f"para ejecutar, confirmacion debe ser exactamente "
                   f"'{_siembra.CONFIRMACION}'")
    try:
        return _siembra.sembrar_guiado(str(_ECO_BASE), config, ts, semana,
                                       ejecutar=ejecutar)
    except (_eco_errores_economicos, _eco_deps.ErrorDepartamento,
            _eco_cap.ErrorCapacidad, _eco_pt.ErrorPT, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
```

- [ ] **Step 4: Correr y verificar que pasan**

Run: `.venv/bin/python -m pytest test_siembra_server.py -v`
Expected: PASS (3 pruebas).

- [ ] **Step 5: Suite completa + commit**

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py`
Expected: verde (sin llamar al endpoint, la economia se comporta como hoy).

```bash
git add calipso/server.py test_siembra_server.py
git commit -m "feat(economia): endpoint sembrar-guiado con preview y confirmacion"
```

---

## Notas de verificacion (fuera de las tareas)

- **Suite completa antes de cerrar la rama:** `.venv/bin/python -m pytest -q --ignore=test_chat_live.py` verde.
- **ENSAYO EN VIVO (el smoke de esta feature, aislado, NO toca el home real):** con un server desechable (home temporal, puerto propio) y Ollama vivo, `POST /api/economia/sembrar-guiado` con el token exacto y la config; despues disparar un tick de una rutina `departamento` (o `POST /api/routines/{id}/run` si existe) y verificar por `GET /api/economia/bus` que un jefe propuso y la propuesta llego a la mesa. Prueba end-to-end que la secuencia prende la fabrica. Es el equivalente al smoke del PvP; lo corro yo antes de darte el helper. La siembra real la ejecutas vos.
- **La UI de `/fabrica` (pantalla de siembra) queda como refinamiento** — el endpoint con preview/confirmacion ya es el helper guiado; se puede manejar desde la consola de economia o curl. Una pantalla dedicada es un slice posterior.

## Self-Review

**1. Cobertura del spec:**
- Seccion 3 (endpoint + orquestador, 7 pasos, re-entrante): Task 1 (orquestador) + Task 2 (endpoint). OK.
- Seccion 4 (preview/confirmacion, re-entrante, honesto ante fallas): Task 1 (el reporte paso a paso + guardas) + Task 2 (el gate de confirmacion). OK.
- Seccion 5 (montos como config con defaults): el body los toma; los defaults conservadores van en el body/config. OK.
- Seccion 6 (invariantes): acto de Pedro (token), padron irreversible (guarda "ya sembrada"), re-entrante (guardas por paso), reusa primitivos, api_ciclo 0 (perillas), finanzas en el padron (config), serializado (candado). OK.
- Seccion 7 (lo que NO hace): no corre el probe, no decide montos, no construye el abismo, no agrega deptos post-siembra, no cambia el PISO. Ninguna tarea hace esas cosas. OK.
- Seccion 8 (verificacion): cada punto mapea a pruebas de T1/T2 + el ensayo anotado. OK.

**2. Placeholders:** el codigo de produccion (siembra.py completo, el endpoint completo) va entero. Los tests dejan una nota condicional sobre el aislamiento de `routines.load()` (por si su ruta no sale de CALIPSO_HOME) — el implementador lo confirma leyendo `routines.py`; no es logica sin especificar.

**3. Consistencia de tipos:** `sembrar_guiado(base, config, ts, semana, ejecutar) -> dict` en T1 y su llamada en T2. `CONFIRMACION = "sembrar la economia"` en T1 y el gate en T2. El `config` que arma T2 (endpoint) tiene las mismas claves que consume T1 (`departamentos`, `suscripciones`, `capital_tesoro_mm`, `cuota_firmable_mpt`, `reserva_personal_mpt`, `rutina_interval_min`, `perillas_fabrica`). Los primitivos (Pagador, Registro, kernel.acunar, op.abrir_semana, routines.add, it.poner_modo) con las firmas exactas del mapa. Consistente.
