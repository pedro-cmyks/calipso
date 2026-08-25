# Mercado y Departamentos (Plan 2 de 3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir la capa de juego económico sobre el kernel del Plan 1: suscripciones como capacidad revendida con precio por escasez, departamentos con estado de quiebra derivado del libro, el mercado como frontera de políticas, dirección con mandato acumulado y cartas de sistema, el bus de propuestas con criterios de muerte y liquidación, la eficiencia con atribución prorrateada, y el cierre semanal/mensual orquestado.

**Architecture:** Módulos nuevos dentro de `calipso/economia/` que CONSUMEN el kernel del Plan 1 y nunca lo puentean: toda escritura monetaria pasa por `Kernel`/`pt` (jamás `libro.append` directo desde la capa de políticas). Todo estado (congelado, consumo de cuota, gasto por ciclo, rojos de renovación) se DERIVA plegando el libro — la única persistencia nueva son dos archivos chicos: el registro de departamentos (JSON) y los eventos del bus (JSONL). `Mercado` es la única puerta por la que los departamentos gastan.

**Tech Stack:** Python 3.14, solo stdlib. Tests pytest en la raíz, patrón del Plan 1.

**Spec:** `docs/superpowers/specs/2026-08-24-cerebro-central-economia-monedas-design.md` (secciones 4.2, 4.4, 5, 6, 7, 8 y el cierre de 4.0). Fuera de alcance (Plan 3): cola de compuertas de dos carriles, reloj clock-in, departamento personal de finanzas con libros privados, cuenta pagadora en `dispatch.py`, endpoints en `server.py`, simulación completa de spec 13.

## Global Constraints

- Todo lo del Plan 1 sigue vigente: Python 3.14 stdlib only; montos `int` (milimonedas/mili-PT/unidades); determinismo (ts y semana son parámetros, nada de reloj/RNG); español sin emojis; `from __future__ import annotations`; libro append-only.
- **La capa de políticas nunca llama `libro.append` directo**: escribe solo vía `Kernel` (que valida y unifica excepciones) y vía `pt`. Los apuntes informativos de esta capa (quiebra, consumo personal de capacidad) se apilan vía `kernel._append`… no: vía un helper público nuevo `Kernel.apuntar(ts, semana, monto, detalle)` (Task 2 lo agrega) para no depender de un método privado.
- **Contratos de excepción**: `Kernel` lanza `OperacionInvalida`/`SinSaldo`; cada módulo nuevo lanza su propia excepción de dominio (`ErrorCapacidad`, `ErrorDepartamento`, `ErrorMercado`, `ErrorDireccion`, `ErrorBus`); ninguna deja escapar `AsientoInvalido`.
- **Prefijos de cuenta**: departamentos de fábrica `dep:<slug>`, zona personal `personal:<slug>`, trabajos `trabajo:<id>`. La atribución de gastos a un trabajo usa `ref="trabajo:<id>"`.
- **Ciclo mensual = 4 semanas operativas** (`SEMANAS_POR_CICLO = 4`): el ciclo n cubre las semanas operativas con índice `[4n, 4n+4)`; la fracción transcurrida de la semana con índice i dentro de su ciclo es `(i % 4 + 1) * 25` por ciento.
- Estados y métricas SIEMPRE derivados del libro; los dos archivos nuevos (departamentos.json, bus.jsonl) guardan solo configuración y eventos de propuestas, nunca saldos.
- Tests: pytest real dirigido — `pytest test_economia_<modulo>.py -v` con `/var/home/pedro/calipso/.venv/bin/python -m pytest`; jamás `pytest` a secas. Regresión final por tarea: los tests del Plan 1 (`test_economia_libro.py test_economia_kernel.py test_economia_pt.py`) más `test_resource_dispatcher.py` deben seguir verdes.
- Las "cartas" que produce esta capa son ESTRUCTURAS DE DATOS devueltas (dicts en listas) — la cola que las presenta y el registro de "atendida" son del Plan 3; el ciclo mensual recibe `cartas_atendidas`/`firmas` como parámetros.

## File Structure

- Create: `calipso/economia/capacidad.py` — Suscripcion (config + prorrateo + equivalencias) y funciones puras de ciclo, consumo, precio por escasez y recaudación.
- Create: `calipso/economia/departamentos.py` — Departamento (perillas), Registro persistente (JSON), estado congelado derivado, declaración de quiebra.
- Create: `calipso/economia/mercado.py` — `Mercado`: la única puerta de gasto de los departamentos (capacidad, API con techo, servicios, reglas de zona y congelado).
- Create: `calipso/economia/direccion.py` — mandato acumulado por departamento/semana, cartas de sistema pagadas en PT por dirección, adelanto de obligatorias como crédito prioritario.
- Create: `calipso/economia/bus.py` — eventos de propuestas (JSONL), financiación, criterios de muerte, liquidación proporcional.
- Create: `calipso/economia/eficiencia.py` — atribución de ventas a consumos por costo API equivalente; eficiencia por suscripción y por departamento.
- Create: `calipso/economia/cierre.py` — cierre semanal orquestado y cierre de ciclo mensual (renovaciones con dos ejes y circuit breaker).
- Modify: `calipso/economia/kernel.py` — agregar `Kernel.apuntar(...)` (Task 2) y `detalle_extra` en `acunar` (Task 7). Nada más.
- Modify: `calipso/economia/__init__.py` — exportar los módulos nuevos (Task 8).
- Test: `test_economia_capacidad.py` (T1), `test_economia_mercado.py` (T2-T4), `test_economia_bus.py` (T5-T6), `test_economia_eficiencia.py` (T7), `test_economia_cierre.py` (T8).

---

### Task 1: Suscripciones y funciones puras de capacidad

**Files:**
- Create: `calipso/economia/capacidad.py`
- Test: `test_economia_capacidad.py`

**Interfaces:**
- Consumes: `tipos` (Asiento, TipoAsiento, Divisa, DIRECCION), nada más.
- Produces: `SEMANAS_POR_CICLO = 4`; `ErrorCapacidad(Exception)`; dataclass congelada `Suscripcion(nombre: str, costo_mensual_mm: int, capacidad_ciclo: int, reserva_personal: int, costo_api_mm_por_unidad: int)` con `__post_init__` que valida (`capacidad_ciclo > 0`, `0 <= reserva_personal < capacidad_ciclo`, `costo_api_mm_por_unidad > 0`, montos int) y propiedades `capacidad_fabrica`, `costo_fabrica_mm` (prorrateo `costo_mensual_mm * capacidad_fabrica // capacidad_ciclo`), `precio_base_mm` (`max(1, costo_fabrica_mm // capacidad_fabrica)`), `tope_mm` (`costo_api_mm_por_unidad * 9 // 10`). Funciones puras: `semanas_operativas(asientos) -> list[str]` (semanas con EMISION_PT, ordenadas); `posicion_ciclo(semana, semanas_ops) -> tuple[int, int]` ((ciclo, fraccion_pct); `ErrorCapacidad` si la semana no es operativa); `semanas_del_ciclo(ciclo, semanas_ops) -> list[str]`; `consumo_fabrica(asientos, nombre, semanas) -> int` (suma `detalle["unidades"]` de TRANSFERENCIA con destino DIRECCION, `detalle["suscripcion"] == nombre` y semana en la lista); `consumo_personal(asientos, nombre, semanas) -> int` (suma `monto` de APUNTE con `detalle["nota"] == "consumo_personal_capacidad"` y misma suscripción); `precio_unidad_mm(sus, consumido, fraccion_pct) -> int` (`r_pct = consumido * 100 * 100 // (sus.capacidad_fabrica * fraccion_pct)`; `min(sus.precio_base_mm * max(100, r_pct) // 100, sus.tope_mm)`); `recaudacion(asientos, nombre, semanas) -> int` (suma `monto` de esas mismas transferencias de capacidad).

- [ ] **Step 1: Write the failing tests**

```python
# test_economia_capacidad.py
"""Tests de suscripciones como capacidad: prorrateo, ciclo, precio por escasez."""
import pytest

from calipso.economia import capacidad as cap
from calipso.economia import tipos as t
from calipso.economia import pt
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"

SUS = cap.Suscripcion(nombre="claude_max", costo_mensual_mm=100_000,
                      capacidad_ciclo=1_000, reserva_personal=200,
                      costo_api_mm_por_unidad=500)


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


def _emitir(k, semanas):
    for s in semanas:
        pt.emitir_semana(k, TS, s, 4_000, 0)
        pt.expirar_pools(k, TS, s)


def test_prorrateo_y_precios_derivados():
    assert SUS.capacidad_fabrica == 800
    assert SUS.costo_fabrica_mm == 80_000   # 100k * 800/1000
    assert SUS.precio_base_mm == 100        # 80k / 800
    assert SUS.tope_mm == 450               # 500 * 0.9


def test_configuracion_invalida_se_rechaza():
    with pytest.raises(cap.ErrorCapacidad):
        cap.Suscripcion("x", 1_000, 0, 0, 500)          # capacidad 0
    with pytest.raises(cap.ErrorCapacidad):
        cap.Suscripcion("x", 1_000, 100, 100, 500)      # reserva == capacidad
    with pytest.raises(cap.ErrorCapacidad):
        cap.Suscripcion("x", 1_000, 100, 10, 0)         # api equiv 0


def test_posicion_y_semanas_de_ciclo(k):
    semanas = [f"2026-W{n}" for n in range(30, 36)]     # 6 semanas operativas
    _emitir(k, semanas)
    ops = cap.semanas_operativas(k.libro.asientos())
    assert ops == semanas
    assert cap.posicion_ciclo("2026-W30", ops) == (0, 25)
    assert cap.posicion_ciclo("2026-W33", ops) == (0, 100)
    assert cap.posicion_ciclo("2026-W34", ops) == (1, 25)
    assert cap.semanas_del_ciclo(0, ops) == semanas[:4]
    assert cap.semanas_del_ciclo(1, ops) == semanas[4:]
    with pytest.raises(cap.ErrorCapacidad):
        cap.posicion_ciclo("2026-W99", ops)


def test_precio_por_escasez_y_tope():
    # a ritmo (25% de ciclo, 25% de cuota consumida = 200): factor 100
    assert cap.precio_unidad_mm(SUS, 200, 25) == 100
    # sobre-ritmo: 50% consumido en 25% de ciclo -> factor 200
    assert cap.precio_unidad_mm(SUS, 400, 25) == 200
    # tope duro: 100% consumido en 25% de ciclo -> factor 400 -> 400 < 450
    assert cap.precio_unidad_mm(SUS, 800, 25) == 400
    # mas alla del tope: factor 500 -> clavado en 450
    assert cap.precio_unidad_mm(SUS, 1_000, 25) == 450
    # sub-ritmo nunca abarata bajo el precio base
    assert cap.precio_unidad_mm(SUS, 0, 100) == 100


def test_consumo_y_recaudacion_se_derivan_del_libro(k):
    _emitir(k, ["2026-W30", "2026-W31"])
    k.acunar(TS, "2026-W30", "dep:a", 50_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    k.transferir(TS, "2026-W30", "dep:a", t.DIRECCION, 1_000,
                 motivo="capacidad",
                 detalle_extra={"suscripcion": "claude_max", "unidades": 10})
    k.transferir(TS, "2026-W31", "dep:a", t.DIRECCION, 2_400,
                 motivo="capacidad",
                 detalle_extra={"suscripcion": "claude_max", "unidades": 12})
    k.transferir(TS, "2026-W31", "dep:a", t.DIRECCION, 500,
                 motivo="capacidad",
                 detalle_extra={"suscripcion": "otra", "unidades": 99})
    asientos = k.libro.asientos()
    assert cap.consumo_fabrica(asientos, "claude_max",
                               ["2026-W30", "2026-W31"]) == 22
    assert cap.consumo_fabrica(asientos, "claude_max", ["2026-W31"]) == 12
    assert cap.recaudacion(asientos, "claude_max",
                           ["2026-W30", "2026-W31"]) == 3_400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_capacidad.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.capacidad`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/capacidad.py
"""
calipso/economia/capacidad.py — Suscripciones como capacidad revendida.

Las monedas miden plata; la cuota mide capacidad (spec 4.2). Este modulo
es pura derivacion: la configuracion de cada suscripcion (con la reserva
personal de Pedro prorrateada fuera de la economia de la fabrica) y las
funciones que pliegan consumo, precio por escasez y recaudacion desde el
libro. Quien ESCRIBE compras es el Mercado.
"""
from __future__ import annotations

from dataclasses import dataclass

from .tipos import Asiento, TipoAsiento, DIRECCION

SEMANAS_POR_CICLO = 4


class ErrorCapacidad(Exception):
    pass


def _entero_positivo(valor: int, nombre: str) -> None:
    if not isinstance(valor, int) or isinstance(valor, bool) or valor <= 0:
        raise ErrorCapacidad(f"{nombre} debe ser entero positivo: {valor!r}")


@dataclass(frozen=True)
class Suscripcion:
    nombre: str
    costo_mensual_mm: int
    capacidad_ciclo: int
    reserva_personal: int
    costo_api_mm_por_unidad: int

    def __post_init__(self):
        _entero_positivo(self.costo_mensual_mm, "costo_mensual_mm")
        _entero_positivo(self.capacidad_ciclo, "capacidad_ciclo")
        _entero_positivo(self.costo_api_mm_por_unidad, "costo_api_mm_por_unidad")
        if (not isinstance(self.reserva_personal, int)
                or isinstance(self.reserva_personal, bool)
                or not 0 <= self.reserva_personal < self.capacidad_ciclo):
            raise ErrorCapacidad(
                f"reserva_personal fuera de [0, capacidad): {self.reserva_personal!r}")

    @property
    def capacidad_fabrica(self) -> int:
        return self.capacidad_ciclo - self.reserva_personal

    @property
    def costo_fabrica_mm(self) -> int:
        return self.costo_mensual_mm * self.capacidad_fabrica // self.capacidad_ciclo

    @property
    def precio_base_mm(self) -> int:
        return max(1, self.costo_fabrica_mm // self.capacidad_fabrica)

    @property
    def tope_mm(self) -> int:
        return self.costo_api_mm_por_unidad * 9 // 10


def semanas_operativas(asientos: list[Asiento]) -> list[str]:
    return sorted({a.semana for a in asientos
                   if a.tipo is TipoAsiento.EMISION_PT})


def posicion_ciclo(semana: str, semanas_ops: list[str]) -> tuple[int, int]:
    """(indice de ciclo, fraccion transcurrida en %) de una semana operativa."""
    try:
        i = semanas_ops.index(semana)
    except ValueError:
        raise ErrorCapacidad(f"semana no operativa: {semana}") from None
    return i // SEMANAS_POR_CICLO, (i % SEMANAS_POR_CICLO + 1) * 100 // SEMANAS_POR_CICLO


def semanas_del_ciclo(ciclo: int, semanas_ops: list[str]) -> list[str]:
    return semanas_ops[ciclo * SEMANAS_POR_CICLO:(ciclo + 1) * SEMANAS_POR_CICLO]


def _compras(asientos: list[Asiento], nombre: str, semanas: list[str]):
    for a in asientos:
        if (a.tipo is TipoAsiento.TRANSFERENCIA and a.destino == DIRECCION
                and a.detalle.get("suscripcion") == nombre
                and a.semana in semanas):
            yield a


def consumo_fabrica(asientos: list[Asiento], nombre: str,
                    semanas: list[str]) -> int:
    return sum(a.detalle["unidades"] for a in _compras(asientos, nombre, semanas))


def consumo_personal(asientos: list[Asiento], nombre: str,
                     semanas: list[str]) -> int:
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.APUNTE
               and a.detalle.get("nota") == "consumo_personal_capacidad"
               and a.detalle.get("suscripcion") == nombre
               and a.semana in semanas)


def precio_unidad_mm(sus: Suscripcion, consumido: int, fraccion_pct: int) -> int:
    """Precio por escasez (spec 4.2): base x factor, tope en 0,9 x API."""
    r_pct = consumido * 100 * 100 // (sus.capacidad_fabrica * fraccion_pct)
    return min(sus.precio_base_mm * max(100, r_pct) // 100, sus.tope_mm)


def recaudacion(asientos: list[Asiento], nombre: str,
                semanas: list[str]) -> int:
    return sum(a.monto for a in _compras(asientos, nombre, semanas))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_capacidad.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/capacidad.py test_economia_capacidad.py
git commit -m "feat(economia): suscripciones como capacidad — prorrateo, ciclo y precio por escasez"
```

---

### Task 2: Departamentos, registro y estado congelado

**Files:**
- Create: `calipso/economia/departamentos.py`
- Modify: `calipso/economia/kernel.py` (agregar `Kernel.apuntar`)
- Test: `test_economia_mercado.py`

**Interfaces:**
- Consumes: `Kernel`, tipos.
- Produces: en `kernel.py`: `Kernel.apuntar(ts, semana, monto, detalle: dict) -> Asiento` (APUNTE en MONEDA vía `_append`), y `Kernel.destruir` gana `detalle_extra: dict | None = None` (mismo patrón que `transferir`: `detalle={"motivo": motivo} | (detalle_extra or {})`) — lo usan el techo de API con firma y la renovación (las autorizaciones quedan auditables en el libro, como ya pasa con la compuerta d). En `departamentos.py`: `ZONA_FABRICA = "fabrica"`, `ZONA_PERSONAL = "personal"`, `ErrorDepartamento(Exception)`; dataclass congelada `Departamento(nombre, zona, presupuesto_semanal_mm=0, techo_api_ciclo_mm=0, explorar_explotar_pct=50, agresividad_pct=30)` con propiedad `cuenta` (`dep:<nombre>` en fábrica, `personal:<nombre>` en zona personal) y validación de zona/nombre; `Registro(ruta: Path)` con `alta(dep)`, `obtener(nombre) -> Departamento`, `todos() -> list[Departamento]`, `ajustar(nombre, **perillas) -> Departamento` (persiste JSON `{nombre: campos}`); `es_congelado(asientos, cuenta) -> bool` (pliegue: apunte `{"nota": "quiebra", "departamento": cuenta}` congela; TRANSFERENCIA entrante con `detalle["rescate"]` o ACUNACION subtipo venta con destino la cuenta descongelan); `declarar_quiebra(k, ts, semana, cuenta) -> Asiento` (apunte monto=1).

- [ ] **Step 1: Write the failing tests**

```python
# test_economia_mercado.py
"""Tests de departamentos, mercado y direccion: la capa de juego economico."""
import pytest

from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import cuenta_pedro as cp
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"
W = "2026-W35"


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


@pytest.fixture
def registro(tmp_path):
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("mercadeo", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=20_000,
                             techo_api_ciclo_mm=10_000))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    return r


def _capital(k, monto, destino=t.TESORO):
    return k.acunar(TS, W, destino, monto, t.SubtipoAcunacion.CAPITAL,
                    {"tipo": "firma_pedro"})


def test_cuentas_por_zona(registro):
    assert registro.obtener("mercadeo").cuenta == "dep:mercadeo"
    assert registro.obtener("finanzas").cuenta == "personal:finanzas"


def test_registro_persiste_y_ajusta(tmp_path, registro):
    registro.ajustar("mercadeo", presupuesto_semanal_mm=30_000)
    r2 = deps.Registro(tmp_path / "departamentos.json")
    assert r2.obtener("mercadeo").presupuesto_semanal_mm == 30_000
    assert len(r2.todos()) == 2
    with pytest.raises(deps.ErrorDepartamento):
        r2.alta(deps.Departamento("mercadeo", deps.ZONA_FABRICA))  # repetido
    with pytest.raises(deps.ErrorDepartamento):
        r2.obtener("fantasma")


def test_quiebra_congela_y_rescate_descongela(k):
    _capital(k, 10_000, destino="dep:a")
    assert not deps.es_congelado(k.libro.asientos(), "dep:a")
    deps.declarar_quiebra(k, TS, W, "dep:a")
    assert deps.es_congelado(k.libro.asientos(), "dep:a")
    _capital(k, 5_000, destino=t.CUENTA_PEDRO)
    cp.rescatar(k, TS, W, "dep:a", 5_000, firma={"tipo": "firma_pedro"})
    assert not deps.es_congelado(k.libro.asientos(), "dep:a")


def test_venta_propia_tambien_descongela(k):
    deps.declarar_quiebra(k, TS, W, "dep:a")
    k.acunar(TS, W, "dep:a", 1_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"})
    assert not deps.es_congelado(k.libro.asientos(), "dep:a")


def test_capital_no_descongela(k):
    """Solo rescate firmado o venta propia sacan del congelamiento (spec 5)."""
    deps.declarar_quiebra(k, TS, W, "dep:a")
    _capital(k, 1_000, destino="dep:a")  # capital directo, sin marca de rescate
    assert deps.es_congelado(k.libro.asientos(), "dep:a")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_mercado.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.departamentos`

- [ ] **Step 3: Write minimal implementation**

```python
# agregar a calipso/economia/kernel.py, dentro de class Kernel
    def apuntar(self, ts: str, semana: str, monto: int,
                detalle: dict) -> Asiento:
        """Apunte informativo: no mueve saldos (los pliegues lo ignoran)."""
        return self._append(
            ts=ts, semana=semana, tipo=TipoAsiento.APUNTE,
            divisa=Divisa.MONEDA, monto=monto, detalle=detalle)
```

Y REEMPLAZAR el método `destruir` existente para que acepte `detalle_extra` (retro-compatible):

```python
    def destruir(self, ts: str, semana: str, origen: str, monto: int,
                 motivo: str, ref: str | None = None,
                 detalle_extra: dict | None = None) -> Asiento:
        self._exigir(origen, monto)
        return self._append(
            ts=ts, semana=semana, tipo=TipoAsiento.DESTRUCCION,
            divisa=Divisa.MONEDA, monto=monto, origen=origen, ref=ref,
            detalle={"motivo": motivo} | (detalle_extra or {}))
```

```python
# calipso/economia/departamentos.py
"""
calipso/economia/departamentos.py — Departamentos y su estado.

El registro guarda CONFIGURACION (zona y perillas de Pedro); el estado
congelado se deriva del libro, nunca se guarda: quiebra declarada en un
cierre congela, y solo un rescate firmado o una venta propia descongelan
(spec 5). El capital sin marca de rescate NO descongela: esa es la
decision de Pedro que el codigo protege.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, asdict, replace

from .kernel import Kernel
from .tipos import Asiento, SubtipoAcunacion, TipoAsiento

ZONA_FABRICA = "fabrica"
ZONA_PERSONAL = "personal"


class ErrorDepartamento(Exception):
    pass


@dataclass(frozen=True)
class Departamento:
    nombre: str
    zona: str
    presupuesto_semanal_mm: int = 0
    techo_api_ciclo_mm: int = 0
    explorar_explotar_pct: int = 50
    agresividad_pct: int = 30

    def __post_init__(self):
        if self.zona not in (ZONA_FABRICA, ZONA_PERSONAL):
            raise ErrorDepartamento(f"zona invalida: {self.zona!r}")
        if not self.nombre or ":" in self.nombre:
            raise ErrorDepartamento(f"nombre invalido: {self.nombre!r}")

    @property
    def cuenta(self) -> str:
        prefijo = "dep" if self.zona == ZONA_FABRICA else "personal"
        return f"{prefijo}:{self.nombre}"


class Registro:
    def __init__(self, ruta: pathlib.Path):
        self.ruta = pathlib.Path(ruta)
        self._deps: dict[str, Departamento] = {}
        if self.ruta.exists():
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
            self._deps = {n: Departamento(**campos) for n, campos in datos.items()}

    def _guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = {n: asdict(d) for n, d in self._deps.items()}
        self.ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1),
                             encoding="utf-8")

    def alta(self, dep: Departamento) -> None:
        if dep.nombre in self._deps:
            raise ErrorDepartamento(f"departamento repetido: {dep.nombre}")
        self._deps[dep.nombre] = dep
        self._guardar()

    def obtener(self, nombre: str) -> Departamento:
        try:
            return self._deps[nombre]
        except KeyError:
            raise ErrorDepartamento(f"departamento inexistente: {nombre}") from None

    def todos(self) -> list[Departamento]:
        return list(self._deps.values())

    def ajustar(self, nombre: str, **perillas) -> Departamento:
        nuevo = replace(self.obtener(nombre), **perillas)
        self._deps[nombre] = nuevo
        self._guardar()
        return nuevo


def es_congelado(asientos: list[Asiento], cuenta: str) -> bool:
    congelado = False
    for a in asientos:
        if (a.tipo is TipoAsiento.APUNTE
                and a.detalle.get("nota") == "quiebra"
                and a.detalle.get("departamento") == cuenta):
            congelado = True
        elif (a.tipo is TipoAsiento.TRANSFERENCIA and a.destino == cuenta
                and a.detalle.get("rescate")):
            congelado = False
        elif (a.tipo is TipoAsiento.ACUNACION and a.destino == cuenta
                and a.subtipo == SubtipoAcunacion.VENTA.value):
            congelado = False
    return congelado


def declarar_quiebra(k: Kernel, ts: str, semana: str, cuenta: str) -> Asiento:
    return k.apuntar(ts, semana, 1,
                     {"nota": "quiebra", "departamento": cuenta})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_mercado.py -v`
Expected: PASS (5 tests). Regresión: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_kernel.py -v` sigue verde.

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/departamentos.py calipso/economia/kernel.py test_economia_mercado.py
git commit -m "feat(economia): departamentos — registro, perillas y congelado derivado del libro"
```

---

### Task 3: El Mercado — la puerta de gasto

**Files:**
- Create: `calipso/economia/mercado.py`
- Test: `test_economia_mercado.py` (agregar tests)

**Interfaces:**
- Consumes: `Kernel`, `capacidad`, `departamentos`, `pt`.
- Produces: `ErrorMercado(Exception)`; clase `Mercado(kernel: Kernel, registro: Registro, suscripciones: dict[str, Suscripcion])` con: `dep_por_cuenta(cuenta) -> Departamento` (ErrorMercado si no existe); `comprar_capacidad(ts, semana, pagador, sus_nombre, unidades, ref=None, dueno=None) -> Asiento` y `gastar_api(ts, semana, pagador, mm, ref=None, firma=None, dueno=None) -> Asiento`. **Pagadores `trabajo:<id>`:** exigen `dueno` (la cuenta del departamento dueño, la resuelve el llamador vía bus); las políticas — zona fábrica, no congelado, techo — se evalúan contra el DUEÑO, y el asiento lleva `detalle["dueno"]` para que el techo del dueño cuente también el gasto de sus trabajos. Para pagadores `dep:`/`personal:`, `dueno` se omite. Reglas: solo zona fábrica; ni el pagador-departamento ni el dueño congelados; cuota del ciclo validada; precio = `precio_unidad_mm(...) * unidades`; techo de API por ciclo del dueño (dep más sus trabajos): superarlo exige `firma` no vacía (compuerta tipo c) y la firma queda en el detalle del asiento. `usar_reserva_personal(ts, semana, sus_nombre, unidades, departamento_cuenta) -> Asiento` (apunte `consumo_personal_capacidad`; valida reserva restante del ciclo); `vender_servicio(ts, semana, origen, destino, mm, ref=None) -> Asiento` (origen activo; destino no congelado); `gasto_api_ciclo(asientos, dep_cuenta, semanas) -> int` como función de módulo (destrucciones motivo "api" en esas semanas con `origen == dep_cuenta` O `detalle["dueno"] == dep_cuenta`).

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_mercado.py
from calipso.economia import mercado as mkt

SUS = cap.Suscripcion(nombre="claude_max", costo_mensual_mm=100_000,
                      capacidad_ciclo=1_000, reserva_personal=200,
                      costo_api_mm_por_unidad=500)


@pytest.fixture
def mercado(k, registro):
    return mkt.Mercado(k, registro, {"claude_max": SUS})


def _semana_op(k, semana):
    pt.emitir_semana(k, TS, semana, 4_000, 0)
    pt.expirar_pools(k, TS, semana)


def test_comprar_capacidad_cobra_precio_por_escasez(k, mercado):
    _semana_op(k, "2026-W35")
    _capital(k, 100_000, destino="dep:mercadeo")
    a = mercado.comprar_capacidad(TS, "2026-W35", "dep:mercadeo",
                                  "claude_max", 10)
    assert a.monto == 1_000            # 10 unidades a precio base 100
    assert k.saldo(t.DIRECCION) == 1_000
    # tras consumir 400 en el 25% del ciclo, el precio dobla (factor 200)
    mercado.comprar_capacidad(TS, "2026-W35", "dep:mercadeo",
                              "claude_max", 390)
    b = mercado.comprar_capacidad(TS, "2026-W35", "dep:mercadeo",
                                  "claude_max", 10)
    assert b.monto == 2_000            # 10 unidades a 200


def test_cuota_agotada_rechaza(k, mercado):
    _semana_op(k, "2026-W35")
    _capital(k, 1_000_000, destino="dep:mercadeo")
    with pytest.raises(mkt.ErrorMercado):
        mercado.comprar_capacidad(TS, "2026-W35", "dep:mercadeo",
                                  "claude_max", 801)  # fabrica = 800


def test_zona_personal_no_compra_capacidad_de_fabrica(k, mercado):
    _semana_op(k, "2026-W35")
    with pytest.raises(mkt.ErrorMercado):
        mercado.comprar_capacidad(TS, "2026-W35", "personal:finanzas",
                                  "claude_max", 1)


def test_reserva_personal_se_consume_y_agota(k, mercado):
    _semana_op(k, "2026-W35")
    a = mercado.usar_reserva_personal(TS, "2026-W35", "claude_max", 150,
                                      "personal:finanzas")
    assert a.tipo is t.TipoAsiento.APUNTE and a.monto == 150
    with pytest.raises(mkt.ErrorMercado):
        mercado.usar_reserva_personal(TS, "2026-W35", "claude_max", 51,
                                      "personal:finanzas")  # reserva 200


def test_congelado_no_compra_ni_recibe(k, mercado):
    _semana_op(k, "2026-W35")
    _capital(k, 50_000, destino="dep:mercadeo")
    _capital(k, 50_000, destino="dep:otro")
    deps.declarar_quiebra(k, TS, "2026-W35", "dep:mercadeo")
    with pytest.raises(mkt.ErrorMercado):
        mercado.comprar_capacidad(TS, "2026-W35", "dep:mercadeo",
                                  "claude_max", 1)
    with pytest.raises(mkt.ErrorMercado):
        mercado.gastar_api(TS, "2026-W35", "dep:mercadeo", 100)
    with pytest.raises(mkt.ErrorMercado):
        mercado.vender_servicio(TS, "2026-W35", "dep:otro",
                                "dep:mercadeo", 100)


def test_techo_api_exige_firma_para_superarse(k, mercado):
    _semana_op(k, "2026-W35")
    _capital(k, 100_000, destino="dep:mercadeo")
    mercado.gastar_api(TS, "2026-W35", "dep:mercadeo", 9_000)
    with pytest.raises(mkt.ErrorMercado):
        mercado.gastar_api(TS, "2026-W35", "dep:mercadeo", 2_000)  # 11k > techo 10k
    a = mercado.gastar_api(TS, "2026-W35", "dep:mercadeo", 2_000,
                           firma={"tipo": "firma_pedro"})
    assert a.monto == 2_000


def test_trabajo_gasta_con_dueno_y_cuenta_contra_su_techo(k, mercado):
    """La puerta de gasto de los trabajos: politicas y techo del dueno."""
    _semana_op(k, "2026-W35")
    _capital(k, 50_000, destino="trabajo:p1")
    _capital(k, 50_000, destino="dep:mercadeo")
    with pytest.raises(mkt.ErrorMercado):
        mercado.gastar_api(TS, "2026-W35", "trabajo:p1", 1_000)  # sin dueno
    mercado.gastar_api(TS, "2026-W35", "trabajo:p1", 6_000, dueno="dep:mercadeo")
    # el gasto del trabajo cuenta contra el techo del dueno (10_000)
    with pytest.raises(mkt.ErrorMercado):
        mercado.gastar_api(TS, "2026-W35", "dep:mercadeo", 5_000)  # 6k+5k > 10k
    a = mercado.gastar_api(TS, "2026-W35", "dep:mercadeo", 5_000,
                           firma={"tipo": "firma_pedro"})
    assert a.detalle["firma"] == {"tipo": "firma_pedro"}  # auditable
    # dueno congelado: sus trabajos tampoco gastan
    deps.declarar_quiebra(k, TS, "2026-W35", "dep:mercadeo")
    with pytest.raises(mkt.ErrorMercado):
        mercado.gastar_api(TS, "2026-W35", "trabajo:p1", 100,
                           dueno="dep:mercadeo")


def test_vender_servicio_entre_departamentos(k, mercado, registro):
    registro.alta(deps.Departamento("produccion", deps.ZONA_FABRICA))
    _semana_op(k, "2026-W35")
    _capital(k, 10_000, destino="dep:produccion")
    mercado.vender_servicio(TS, "2026-W35", "dep:produccion",
                            "dep:mercadeo", 4_000)
    assert k.saldo("dep:mercadeo") == 4_000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_mercado.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.mercado`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/mercado.py
"""
calipso/economia/mercado.py — La unica puerta de gasto de los departamentos.

El Kernel garantiza que la plata no se invente; el Mercado garantiza que
las POLITICAS se cumplan: congelados no compran ni reciben, la zona
personal no toca capacidad ni API de la fabrica (invariante 12), el techo
de API exige firma (compuerta c) y la cuota de suscripcion es finita.
"""
from __future__ import annotations

from . import capacidad as cap
from . import departamentos as deps
from .kernel import Kernel
from .tipos import Asiento, DIRECCION


class ErrorMercado(Exception):
    pass


def gasto_api_ciclo(asientos, dep_cuenta: str, semanas: list[str]) -> int:
    """Gasto de API del departamento MAS el de sus trabajos (detalle dueno)."""
    from .tipos import TipoAsiento
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.DESTRUCCION
               and a.detalle.get("motivo") == "api" and a.semana in semanas
               and (a.origen == dep_cuenta
                    or a.detalle.get("dueno") == dep_cuenta))


class Mercado:
    def __init__(self, kernel: Kernel, registro: deps.Registro,
                 suscripciones: dict[str, cap.Suscripcion]):
        self.k = kernel
        self.registro = registro
        self.suscripciones = dict(suscripciones)

    # -- helpers -----------------------------------------------------------
    def dep_por_cuenta(self, cuenta: str) -> deps.Departamento:
        for d in self.registro.todos():
            if d.cuenta == cuenta:
                return d
        raise ErrorMercado(f"cuenta sin departamento registrado: {cuenta}")

    def _sus(self, nombre: str) -> cap.Suscripcion:
        try:
            return self.suscripciones[nombre]
        except KeyError:
            raise ErrorMercado(f"suscripcion desconocida: {nombre}") from None

    def _exigir_activo(self, cuenta: str) -> None:
        if deps.es_congelado(self.k.libro.asientos(), cuenta):
            raise ErrorMercado(f"departamento congelado: {cuenta}")

    def _ciclo(self, semana: str) -> tuple[list[str], int]:
        asientos = self.k.libro.asientos()
        ops = cap.semanas_operativas(asientos)
        ciclo, fraccion = cap.posicion_ciclo(semana, ops)
        return cap.semanas_del_ciclo(ciclo, ops), fraccion

    def _politica(self, pagador: str, dueno: str | None) -> deps.Departamento:
        """Resuelve el departamento contra el que se evaluan las politicas.

        Un trabajo gasta con dueno explicito (el llamador lo resuelve via
        bus); las reglas de zona, congelado y techo son del dueno.
        """
        if pagador.startswith("trabajo:"):
            if not dueno:
                raise ErrorMercado(
                    f"un trabajo gasta con dueno explicito: {pagador}")
            dep = self.dep_por_cuenta(dueno)
        else:
            dep = self.dep_por_cuenta(pagador)
        if dep.zona != deps.ZONA_FABRICA:
            raise ErrorMercado(
                "la zona personal no compra capacidad ni API de la fabrica "
                "(invariante 12)")
        self._exigir_activo(dep.cuenta)
        return dep

    # -- operaciones -------------------------------------------------------
    def comprar_capacidad(self, ts: str, semana: str, pagador: str,
                          sus_nombre: str, unidades: int,
                          ref: str | None = None,
                          dueno: str | None = None) -> Asiento:
        dep = self._politica(pagador, dueno)
        sus = self._sus(sus_nombre)
        semanas, fraccion = self._ciclo(semana)
        consumido = cap.consumo_fabrica(self.k.libro.asientos(),
                                        sus_nombre, semanas)
        if consumido + unidades > sus.capacidad_fabrica:
            raise ErrorMercado(
                f"cuota agotada: {consumido}+{unidades} > {sus.capacidad_fabrica}")
        precio = cap.precio_unidad_mm(sus, consumido, fraccion) * unidades
        detalle = {"suscripcion": sus_nombre, "unidades": unidades}
        if pagador.startswith("trabajo:"):
            detalle["dueno"] = dep.cuenta
        return self.k.transferir(
            ts, semana, pagador, DIRECCION, precio, motivo="capacidad",
            ref=ref, detalle_extra=detalle)

    def usar_reserva_personal(self, ts: str, semana: str, sus_nombre: str,
                              unidades: int, departamento_cuenta: str) -> Asiento:
        sus = self._sus(sus_nombre)
        semanas, _ = self._ciclo(semana)
        usado = cap.consumo_personal(self.k.libro.asientos(),
                                     sus_nombre, semanas)
        if usado + unidades > sus.reserva_personal:
            raise ErrorMercado(
                f"reserva personal agotada: {usado}+{unidades} > {sus.reserva_personal}")
        return self.k.apuntar(ts, semana, unidades,
                              {"nota": "consumo_personal_capacidad",
                               "suscripcion": sus_nombre,
                               "departamento": departamento_cuenta})

    def gastar_api(self, ts: str, semana: str, pagador: str, mm: int,
                   ref: str | None = None, firma: dict | None = None,
                   dueno: str | None = None) -> Asiento:
        dep = self._politica(pagador, dueno)
        semanas, _ = self._ciclo(semana)
        gastado = gasto_api_ciclo(self.k.libro.asientos(), dep.cuenta, semanas)
        if gastado + mm > dep.techo_api_ciclo_mm and not firma:
            raise ErrorMercado(
                f"techo de API del ciclo superado sin firma: "
                f"{gastado}+{mm} > {dep.techo_api_ciclo_mm} (compuerta c)")
        detalle = {}
        if pagador.startswith("trabajo:"):
            detalle["dueno"] = dep.cuenta
        if firma:
            detalle["firma"] = firma
        return self.k.destruir(ts, semana, pagador, mm, motivo="api", ref=ref,
                               detalle_extra=detalle or None)

    def vender_servicio(self, ts: str, semana: str, origen: str,
                        destino: str, mm: int,
                        ref: str | None = None) -> Asiento:
        self._exigir_activo(origen)
        if deps.es_congelado(self.k.libro.asientos(), destino):
            raise ErrorMercado(
                f"un congelado no recibe transferencias internas: {destino}")
        return self.k.transferir(ts, semana, origen, destino, mm,
                                 motivo="servicio", ref=ref)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_mercado.py -v`
Expected: PASS (13 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/mercado.py test_economia_mercado.py
git commit -m "feat(economia): mercado — capacidad, API con techo, servicios y reglas de zona"
```

---

### Task 4: Dirección — mandato, cartas de sistema y adelantos

**Files:**
- Create: `calipso/economia/direccion.py`
- Test: `test_economia_mercado.py` (agregar tests)

**Interfaces:**
- Consumes: `Mercado`, `Kernel`, `pt`, `departamentos`.
- Produces: `UMBRAL_MANDATO_MM = 100_000`; `ErrorDireccion(Exception)`; `asignado_semana(asientos, dep_cuenta, semana) -> int` (transferencias TESORO→cuenta con motivo "presupuesto" en esa semana); `asignar_presupuesto(mercado, ts, semana, dep_cuenta, mm, firma=None, umbral_mm=UMBRAL_MANDATO_MM) -> Asiento` (departamento registrado, no congelado — un congelado no recibe presupuesto —; si el ACUMULADO semanal + mm supera el umbral, exige firma no vacía — compuerta tipo d); `pagar_carta_sistema(mercado, ts, semana, mpt, ref) -> list[Asiento]` (tipo vigente = `pt.tipo_de_cambio(...)`; transferencia DIRECCION→CUENTA_PEDRO por `mpt * tipo // 1000` con motivo "carta_sistema" + `pt.consumir_fabrica(pagador=DIRECCION)`); `adelantar_obligatoria(mercado, ts, semana, dep_cuenta, mpt, ref) -> list[Asiento]` (igual que carta de sistema + `registrar_acreencia(acreedor=DIRECCION, deudor=dep_cuenta, monto=mm, ref=f"adelanto:{ref}")` — el crédito prioritario del spec 5/9).

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_mercado.py
from calipso.economia import direccion as dir_


def test_mandato_acumulado_por_semana(k, mercado):
    _semana_op(k, "2026-W35")
    _capital(k, 500_000)
    dir_.asignar_presupuesto(mercado, TS, "2026-W35", "dep:mercadeo", 60_000)
    with pytest.raises(dir_.ErrorDireccion):
        dir_.asignar_presupuesto(mercado, TS, "2026-W35", "dep:mercadeo",
                                 50_000)  # acumulado 110k > 100k sin firma
    a = dir_.asignar_presupuesto(mercado, TS, "2026-W35", "dep:mercadeo",
                                 50_000, firma={"tipo": "firma_pedro"})
    assert a.monto == 50_000
    assert k.saldo("dep:mercadeo") == 110_000


def test_presupuesto_a_congelado_se_rechaza(k, mercado):
    _semana_op(k, "2026-W35")
    _capital(k, 100_000)
    deps.declarar_quiebra(k, TS, "2026-W35", "dep:mercadeo")
    with pytest.raises(dir_.ErrorDireccion):
        dir_.asignar_presupuesto(mercado, TS, "2026-W35", "dep:mercadeo",
                                 10_000)


def test_carta_de_sistema_paga_en_pt_de_direccion(k, mercado):
    _semana_op(k, "2026-W35")
    _capital(k, 100_000, destino=t.DIRECCION)
    pt.emitir_semana(k, TS, "2026-W36", 4_000, 0)
    asientos = dir_.pagar_carta_sistema(mercado, TS, "2026-W36", 500,
                                        ref="carta:renovacion")
    # tipo vigente de arranque: 5000 mm/PT -> 500 mpt = 2500 mm
    assert k.saldo(t.CUENTA_PEDRO) == 2_500
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 3_500
    assert len(asientos) == 2


def test_adelanto_deja_acreencia_prioritaria(k, mercado):
    _semana_op(k, "2026-W35")
    _capital(k, 100_000, destino=t.DIRECCION)
    pt.emitir_semana(k, TS, "2026-W36", 4_000, 0)
    dir_.adelantar_obligatoria(mercado, TS, "2026-W36", "dep:mercadeo",
                               1_000, ref="firma-99")
    assert k.saldo(t.CUENTA_PEDRO) == 5_000  # 1 PT a 5000
    assert k.acreencias_pendientes("dep:mercadeo") == \
        [("adelanto:firma-99", t.DIRECCION, 5_000)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_mercado.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.direccion`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/direccion.py
"""
calipso/economia/direccion.py — El mandato de direccion.

Direccion asigna presupuestos desde el tesoro dentro de un mandato con
umbral ACUMULADO por departamento y semana (un umbral por asiento se
evade fraccionando — spec 8), paga las cartas de sistema con su propio
presupuesto de PT, y adelanta compuertas obligatorias de departamentos
sin caja como credito prioritario (invariante 6).
"""
from __future__ import annotations

from . import departamentos as deps
from . import pt
from .mercado import Mercado
from .tipos import (Asiento, CUENTA_PEDRO, DIRECCION, Divisa,
                    POOL_PT_FABRICA, TESORO, TipoAsiento)

UMBRAL_MANDATO_MM = 100_000


class ErrorDireccion(Exception):
    pass


def asignado_semana(asientos, dep_cuenta: str, semana: str) -> int:
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.TRANSFERENCIA
               and a.origen == TESORO and a.destino == dep_cuenta
               and a.detalle.get("motivo") == "presupuesto"
               and a.semana == semana)


def asignar_presupuesto(mercado: Mercado, ts: str, semana: str,
                        dep_cuenta: str, mm: int, firma: dict | None = None,
                        umbral_mm: int = UMBRAL_MANDATO_MM) -> Asiento:
    mercado.dep_por_cuenta(dep_cuenta)  # debe existir
    asientos = mercado.k.libro.asientos()
    if deps.es_congelado(asientos, dep_cuenta):
        raise ErrorDireccion(f"un congelado no recibe presupuesto: {dep_cuenta}")
    acumulado = asignado_semana(asientos, dep_cuenta, semana)
    if acumulado + mm > umbral_mm and not firma:
        raise ErrorDireccion(
            f"mandato excedido sin firma: {acumulado}+{mm} > {umbral_mm} "
            f"(compuerta d)")
    detalle = {"firma": firma} if firma else None
    return mercado.k.transferir(ts, semana, TESORO, dep_cuenta, mm,
                                motivo="presupuesto", detalle_extra=detalle)


def _pagar_pt(mercado: Mercado, ts: str, semana: str, mpt: int,
              ref: str) -> tuple[list[Asiento], int]:
    """Pre-valida AMBOS recursos antes del primer append: un libro
    append-only no tiene rollback, asi que el orden es validar todo,
    despues escribir."""
    k = mercado.k
    tipo = pt.tipo_de_cambio(k.libro.asientos(), semana)
    mm = mpt * tipo // 1000
    if mpt > k.saldo(POOL_PT_FABRICA, Divisa.PT):
        raise ErrorDireccion(
            f"pool de PT insuficiente para la carta: pide {mpt}, "
            f"hay {k.saldo(POOL_PT_FABRICA, Divisa.PT)}")
    if mm > k.disponible(DIRECCION):
        raise ErrorDireccion(
            f"direccion sin caja para la carta: pide {mm}, "
            f"disponible {k.disponible(DIRECCION)}")
    transfer = k.transferir(ts, semana, DIRECCION, CUENTA_PEDRO, mm,
                            motivo="carta_sistema", ref=ref)
    consumo = pt.consumir_fabrica(k, ts, semana, mpt, ref=ref,
                                  pagador=DIRECCION)
    return [transfer, consumo], mm


def pagar_carta_sistema(mercado: Mercado, ts: str, semana: str, mpt: int,
                        ref: str) -> list[Asiento]:
    asientos, _ = _pagar_pt(mercado, ts, semana, mpt, ref)
    return asientos


def adelantar_obligatoria(mercado: Mercado, ts: str, semana: str,
                          dep_cuenta: str, mpt: int, ref: str) -> list[Asiento]:
    asientos, mm = _pagar_pt(mercado, ts, semana, mpt, ref)
    acr = mercado.k.registrar_acreencia(ts, semana, DIRECCION, dep_cuenta,
                                        mm, ref=f"adelanto:{ref}")
    return asientos + [acr]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_mercado.py -v`
Expected: PASS (17 tests). Regresión Plan 1: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_libro.py test_economia_kernel.py test_economia_pt.py test_resource_dispatcher.py -v` verde.

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/direccion.py test_economia_mercado.py
git commit -m "feat(economia): direccion — mandato acumulado, cartas de sistema y adelantos"
```

---

### Task 5: Bus de propuestas — eventos y financiación

**Files:**
- Create: `calipso/economia/bus.py`
- Test: `test_economia_bus.py`

**Interfaces:**
- Consumes: `Mercado`, `Kernel`, `departamentos`.
- Produces: `ErrorBus(Exception)`; `cuenta_trabajo(id) -> str` (`trabajo:<id>`); clase `Bus(ruta: Path)` — JSONL append-only de eventos `{"ts", "semana", "evento", "id", ...}` con: `alta(ts, semana, id, departamento_cuenta, titulo, presupuesto_mm, retorno_mm, criterio: dict)` (id único; `criterio` admite claves `gasto_max_mm` y/o `semanas_max`, al menos una); `estado(id) -> str` (`alta`→`financiada`→`muerta`→`liquidada`; ErrorBus si no existe); `datos(id) -> dict` (los del alta + `semana_financiada` si aplica); `ids() -> list[str]`; `activas() -> list[str]` (financiadas no muertas); `marcar(ts, semana, id, evento)`. Funciones: `financiar(mercado, bus, ts, semana, id, financiador_cuenta, mm) -> Asiento` (propuesta en estado alta o financiada; el departamento DUEÑO no congelado — financiar la propuesta de un congelado es rescatarlo por la ventana, spec 5 —; el financiador tampoco congelado; transferencia financiador→trabajo con motivo "financiacion"; marca `financiada` la primera vez); `aportes(asientos, id) -> dict[str, int]`; `gastado(asientos, id) -> int` (toda salida de la cuenta trabajo: TRANSFERENCIA, DESTRUCCION, EJECUCION_RESERVA con ese origen).

- [ ] **Step 1: Write the failing tests**

```python
# test_economia_bus.py
"""Tests del bus de propuestas: eventos, financiacion, muerte y liquidacion."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import mercado as mkt
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"

SUS = cap.Suscripcion(nombre="claude_max", costo_mensual_mm=100_000,
                      capacidad_ciclo=1_000, reserva_personal=200,
                      costo_api_mm_por_unidad=500)


@pytest.fixture
def entorno(tmp_path):
    k = Kernel(Libro(tmp_path / "libro.jsonl"))
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA, techo_api_ciclo_mm=500_000))
    r.alta(deps.Departamento("b", deps.ZONA_FABRICA, techo_api_ciclo_mm=500_000))
    m = mkt.Mercado(k, r, {"claude_max": SUS})
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    return k, m, b


def _capital(k, monto, destino):
    k.acunar(TS, "2026-W30", destino, monto, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})


def _semana_op(k, semana):
    pt.emitir_semana(k, TS, semana, 4_000, 0)
    pt.expirar_pools(k, TS, semana)


CRITERIO = {"gasto_max_mm": 50_000}


def test_alta_estado_y_persistencia(tmp_path, entorno):
    k, m, b = entorno
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar vertical x",
           presupuesto_mm=100_000, retorno_mm=300_000, criterio=CRITERIO)
    assert b.estado("p1") == "alta"
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "p1", "dep:a", "repetida", 1, 1, CRITERIO)
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "p2", "dep:a", "sin criterio", 1, 1, {})
    b2 = bus_mod.Bus(tmp_path / "bus.jsonl")
    assert b2.estado("p1") == "alta"
    with pytest.raises(bus_mod.ErrorBus):
        b2.estado("fantasma")


def test_financiar_transfiere_y_marca(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    _capital(k, 100_000, "dep:b")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 60_000)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:b", 40_000)  # cofinancia
    assert b.estado("p1") == "financiada"
    assert b.datos("p1")["semana_financiada"] == "2026-W30"
    asientos = k.libro.asientos()
    assert k.saldo("trabajo:p1") == 100_000
    assert bus_mod.aportes(asientos, "p1") == {"dep:a": 60_000, "dep:b": 40_000}


def test_no_se_financia_propuesta_de_congelado(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:b")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    deps.declarar_quiebra(k, TS, "2026-W30", "dep:a")
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:b", 10_000)


def test_gastado_pliega_todas_las_salidas(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 80_000)
    # el trabajo gasta por la puerta del Mercado, con dueno explicito
    m.gastar_api(TS, "2026-W30", "trabajo:p1", 20_000, ref="trabajo:p1",
                 dueno="dep:a")
    m.comprar_capacidad(TS, "2026-W30", "trabajo:p1", "claude_max", 50,
                        ref="trabajo:p1", dueno="dep:a")  # 50 u a 100 = 5_000
    assert bus_mod.gastado(k.libro.asientos(), "p1") == 25_000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_bus.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.bus`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/bus.py
"""
calipso/economia/bus.py — El bus de propuestas.

Una propuesta declara que quiere hacer, cuanto pide y su criterio de
muerte ANTES de empezar (spec 7). Los eventos van a un JSONL propio
(no son asientos monetarios); la plata del trabajo vive en la cuenta
trabajo:<id> del libro, movida siempre via Kernel.
"""
from __future__ import annotations

import json
import pathlib

from . import departamentos as deps
from .mercado import Mercado
from .tipos import Asiento, TipoAsiento

_CLAVES_CRITERIO = {"gasto_max_mm", "semanas_max"}


class ErrorBus(Exception):
    pass


def cuenta_trabajo(id: str) -> str:
    return f"trabajo:{id}"


class Bus:
    def __init__(self, ruta: pathlib.Path):
        self.ruta = pathlib.Path(ruta)
        self._eventos: list[dict] = []
        if self.ruta.exists():
            for linea in self.ruta.read_text(encoding="utf-8").splitlines():
                if linea.strip():
                    self._eventos.append(json.loads(linea))

    def _apilar(self, evento: dict) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False,
                               separators=(",", ":")) + "\n")
            f.flush()
        self._eventos.append(evento)

    def alta(self, ts: str, semana: str, id: str, departamento_cuenta: str,
             titulo: str, presupuesto_mm: int, retorno_mm: int,
             criterio: dict) -> None:
        if any(e["id"] == id for e in self._eventos):
            raise ErrorBus(f"propuesta repetida: {id}")
        if not criterio or not set(criterio) <= _CLAVES_CRITERIO:
            raise ErrorBus(
                f"criterio de muerte invalido (claves {_CLAVES_CRITERIO}): "
                f"{criterio!r}")
        self._apilar({"ts": ts, "semana": semana, "evento": "alta", "id": id,
                      "departamento": departamento_cuenta, "titulo": titulo,
                      "presupuesto_mm": presupuesto_mm,
                      "retorno_mm": retorno_mm, "criterio": criterio})

    def _eventos_de(self, id: str) -> list[dict]:
        eventos = [e for e in self._eventos if e["id"] == id]
        if not eventos:
            raise ErrorBus(f"propuesta inexistente: {id}")
        return eventos

    def estado(self, id: str) -> str:
        return self._eventos_de(id)[-1]["evento"]

    def datos(self, id: str) -> dict:
        eventos = self._eventos_de(id)
        d = dict(eventos[0])
        for e in eventos[1:]:
            if e["evento"] == "financiada" and "semana_financiada" not in d:
                d["semana_financiada"] = e["semana"]
        return d

    def ids(self) -> list[str]:
        return sorted({e["id"] for e in self._eventos})

    def activas(self) -> list[str]:
        return [i for i in self.ids() if self.estado(i) == "financiada"]

    def marcar(self, ts: str, semana: str, id: str, evento: str) -> None:
        self._eventos_de(id)  # debe existir
        self._apilar({"ts": ts, "semana": semana, "evento": evento, "id": id})


def financiar(mercado: Mercado, bus: Bus, ts: str, semana: str, id: str,
              financiador_cuenta: str, mm: int) -> Asiento:
    if bus.estado(id) not in ("alta", "financiada"):
        raise ErrorBus(f"propuesta no financiable en estado {bus.estado(id)}")
    asientos = mercado.k.libro.asientos()
    dueno = bus.datos(id)["departamento"]
    if deps.es_congelado(asientos, dueno):
        raise ErrorBus(
            f"financiar la propuesta de un congelado es rescatarlo: {dueno}")
    if deps.es_congelado(asientos, financiador_cuenta):
        raise ErrorBus(f"un congelado no financia: {financiador_cuenta}")
    a = mercado.k.transferir(ts, semana, financiador_cuenta,
                             cuenta_trabajo(id), mm, motivo="financiacion")
    if bus.estado(id) == "alta":
        bus.marcar(ts, semana, id, "financiada")
    return a


def aportes(asientos: list[Asiento], id: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in asientos:
        if (a.tipo is TipoAsiento.TRANSFERENCIA
                and a.destino == cuenta_trabajo(id)
                and a.detalle.get("motivo") == "financiacion"):
            out[a.origen] = out.get(a.origen, 0) + a.monto
    return out


def gastado(asientos: list[Asiento], id: str) -> int:
    cuenta = cuenta_trabajo(id)
    salidas = (TipoAsiento.TRANSFERENCIA, TipoAsiento.DESTRUCCION,
               TipoAsiento.EJECUCION_RESERVA)
    return sum(a.monto for a in asientos
               if a.tipo in salidas and a.origen == cuenta)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_bus.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/bus.py test_economia_bus.py
git commit -m "feat(economia): bus de propuestas — eventos, financiacion y aportes"
```

---

### Task 6: Criterios de muerte y liquidación de trabajos

**Files:**
- Modify: `calipso/economia/bus.py`
- Test: `test_economia_bus.py` (agregar tests)

**Interfaces:**
- Consumes: lo anterior + `capacidad.semanas_operativas`.
- Produces: en `bus.py`: `evaluar_y_liquidar_muertos(mercado, bus, ts, semana) -> list[str]` — para cada propuesta activa: muere si `gastado > criterio["gasto_max_mm"]` o si `semanas_transcurridas(ops, semana_financiada, semana) > criterio["semanas_max"]` (transcurridas = diferencia de índices en semanas operativas); al morir: `marcar muerta`, devolver el saldo del trabajo a los financiadores en proporción a sus aportes (el último se lleva el resto de la división entera para que la suma sea exacta), `marcar liquidada`. Devuelve los ids muertos. Función auxiliar `semanas_transcurridas(semanas_ops, desde, hasta) -> int`.

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_bus.py
def test_muere_por_gasto_y_liquida_proporcional(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    _capital(k, 100_000, "dep:b")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000,
           {"gasto_max_mm": 25_000})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 60_000)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:b", 40_000)
    k.destruir(TS, "2026-W30", "trabajo:p1", 30_000, motivo="api",
               ref="trabajo:p1")  # 30k > 25k: muerto
    muertos = bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W30")
    assert muertos == ["p1"]
    assert b.estado("p1") == "liquidada"
    assert k.saldo("trabajo:p1") == 0
    # saldo 70k proporcional a aportes 60/40: a 42k, b 28k
    assert k.saldo("dep:a") == 100_000 - 60_000 + 42_000
    assert k.saldo("dep:b") == 100_000 - 40_000 + 28_000


def test_muere_por_semanas(entorno):
    k, m, b = entorno
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]:
        _semana_op(k, sem)
    _capital(k, 50_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 50_000, 100_000,
           {"semanas_max": 2})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 30_000)
    assert bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W32") == []
    assert bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W33") == ["p1"]
    assert k.saldo("dep:a") == 50_000  # todo devuelto: no gasto nada


def test_vivo_no_se_liquida(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 50_000, 100_000,
           {"gasto_max_mm": 25_000})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 30_000)
    k.destruir(TS, "2026-W30", "trabajo:p1", 10_000, motivo="api",
               ref="trabajo:p1")
    assert bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W30") == []
    assert b.estado("p1") == "financiada"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_bus.py -v`
Expected: FAIL con `AttributeError: ... 'evaluar_y_liquidar_muertos'`

- [ ] **Step 3: Write minimal implementation**

```python
# agregar a calipso/economia/bus.py
from . import capacidad as cap  # sumar al bloque de imports


def semanas_transcurridas(semanas_ops: list[str], desde: str,
                          hasta: str) -> int:
    try:
        return semanas_ops.index(hasta) - semanas_ops.index(desde)
    except ValueError:
        raise ErrorBus(f"semana no operativa: {desde!r} o {hasta!r}") from None


def evaluar_y_liquidar_muertos(mercado: Mercado, bus: Bus, ts: str,
                               semana: str) -> list[str]:
    asientos = mercado.k.libro.asientos()
    ops = cap.semanas_operativas(asientos)
    muertos: list[str] = []
    for id in bus.activas():
        datos = bus.datos(id)
        criterio = datos["criterio"]
        gasto = gastado(asientos, id)
        muere = ("gasto_max_mm" in criterio
                 and gasto > criterio["gasto_max_mm"])
        if not muere and "semanas_max" in criterio:
            muere = semanas_transcurridas(
                ops, datos["semana_financiada"], semana) > criterio["semanas_max"]
        if not muere:
            continue
        bus.marcar(ts, semana, id, "muerta")
        cuenta = cuenta_trabajo(id)
        saldo = mercado.k.saldo(cuenta)
        aportado = aportes(asientos, id)
        total = sum(aportado.values())
        financiadores = sorted(aportado)
        devuelto = 0
        for i, fin in enumerate(financiadores):
            if i < len(financiadores) - 1:
                parte = saldo * aportado[fin] // total
            else:
                parte = saldo - devuelto  # el ultimo cierra la cuenta exacta
            if parte > 0:
                mercado.k.transferir(ts, semana, cuenta, fin, parte,
                                     motivo="liquidacion_trabajo")
                devuelto += parte
        bus.marcar(ts, semana, id, "liquidada")
        muertos.append(id)
    return muertos
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_bus.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/bus.py test_economia_bus.py
git commit -m "feat(economia): criterios de muerte y liquidacion proporcional de trabajos"
```

---

### Task 7: Eficiencia — atribución prorrateada

**Files:**
- Create: `calipso/economia/eficiencia.py`
- Modify: `calipso/economia/kernel.py` (`acunar` gana `detalle_extra`)
- Test: `test_economia_eficiencia.py`

**Interfaces:**
- Consumes: tipos, `capacidad` (equivalencias).
- Produces: en `kernel.py`: `acunar(..., detalle_extra: dict | None = None)` — `detalle={"evidencia": evidencia} | (detalle_extra or {})`; una venta atribuible a un trabajo lleva `detalle_extra={"trabajo": "<id>"}`. En `eficiencia.py`: `ventas_por_trabajo(asientos, semanas) -> dict[str, int]` (ACUNACION subtipo venta con `detalle["trabajo"]`); `costos_de_trabajo(asientos, id, suscripciones, semanas=None) -> dict[str, int]` (claves `"api"` y `"sus:<nombre>"`, en costo API equivalente: API = mm con `ref == "trabajo:<id>"` y motivo "api"; capacidad = `unidades * costo_api_mm_por_unidad` de compras con ese ref; con `semanas` filtra por `a.semana in semanas`, sin `semanas` pliega toda la historia); `atribucion_por_suscripcion(asientos, semanas, suscripciones) -> dict[str, int]` (cada venta ventaneada se prorratea entre los costos HISTÓRICOS de su trabajo, proporcional al costo API equivalente; floor por componente — el resto de la división entera se descarta: es métrica, no plata); `eficiencia_pormil(atribuido_mm, consumido_api_mm) -> int` (`atribuido * 1000 // consumido`; 0 si consumido == 0); `eficiencia_suscripcion(asientos, sus, semanas, suscripciones) -> int`; `costo_api_directo(asientos, dep_cuenta, semanas, suscripciones) -> int` (gasto directo del departamento en la ventana, en costo API equivalente: destrucciones motivo "api" con `origen == dep_cuenta` más compras de capacidad con `origen == dep_cuenta` a `unidades * equivalencia` — disjunto de los costos de trabajos, que tienen origen `trabajo:*`); `eficiencia_departamento(asientos, dep_cuenta, semanas, suscripciones, duenos: dict[str, str]) -> int` (ventas ventaneadas de los trabajos del departamento / costo API equivalente EN LA VENTANA: el directo del dep más el de sus trabajos, ambos filtrados por `semanas`).

- [ ] **Step 1: Write the failing tests**

```python
# test_economia_eficiencia.py
"""Tests de eficiencia: atribucion prorrateada por costo API equivalente."""
import pytest

from calipso.economia import capacidad as cap
from calipso.economia import eficiencia as ef
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"
W = "2026-W35"
SEMANAS = [W]

SUS = {"claude_max": cap.Suscripcion("claude_max", 100_000, 1_000, 200, 500)}


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


def _montar_trabajo(k, id, api_mm, unidades):
    """Trabajo con gasto de API y de capacidad, etiquetado por ref."""
    ref = f"trabajo:{id}"
    k.acunar(TS, W, f"trabajo:{id}", api_mm + 100_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    k.destruir(TS, W, f"trabajo:{id}", api_mm, motivo="api", ref=ref)
    k.transferir(TS, W, f"trabajo:{id}", t.DIRECCION, unidades * 100,
                 motivo="capacidad", ref=ref,
                 detalle_extra={"suscripcion": "claude_max",
                                "unidades": unidades})


def test_costos_de_trabajo_en_api_equivalente(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    costos = ef.costos_de_trabajo(k.libro.asientos(), "p1", SUS)
    # capacidad: 100 unidades * 500 mm api-equiv = 50_000
    assert costos == {"api": 50_000, "sus:claude_max": 50_000}


def test_atribucion_prorratea_por_costo(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"}, detalle_extra={"trabajo": "p1"})
    atribuida = ef.atribucion_por_suscripcion(k.libro.asientos(), SEMANAS, SUS)
    assert atribuida == {"claude_max": 15_000}  # 30k * 50k/100k


def test_eficiencia_por_suscripcion(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"}, detalle_extra={"trabajo": "p1"})
    got = ef.eficiencia_suscripcion(k.libro.asientos(), SUS["claude_max"],
                                    SEMANAS, SUS)
    assert got == 300  # 15_000 * 1000 // 50_000


def test_eficiencia_departamento(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"}, detalle_extra={"trabajo": "p1"})
    got = ef.eficiencia_departamento(k.libro.asientos(), "dep:a", SEMANAS,
                                     SUS, duenos={"p1": "dep:a"})
    assert got == 300  # 30_000 * 1000 // 100_000


def test_eficiencia_departamento_ventana_y_gasto_directo(k):
    """El denominador respeta la ventana y suma el gasto directo del dep."""
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)  # 100k equiv en W35
    # gasto del trabajo FUERA de la ventana: excluido
    k.destruir(TS, "2026-W34", "trabajo:p1", 10_000, motivo="api",
               ref="trabajo:p1")
    # gasto directo del departamento EN la ventana: 20k
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    k.destruir(TS, W, "dep:a", 20_000, motivo="api")
    k.acunar(TS, W, "dep:a", 30_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"}, detalle_extra={"trabajo": "p1"})
    got = ef.eficiencia_departamento(k.libro.asientos(), "dep:a", SEMANAS,
                                     SUS, duenos={"p1": "dep:a"})
    assert got == 250  # 30_000 * 1000 // (100_000 + 20_000)


def test_capital_y_ventas_sin_trabajo_no_atribuyen(k):
    _montar_trabajo(k, "p1", api_mm=50_000, unidades=100)
    k.acunar(TS, W, t.TESORO, 1_000_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    k.acunar(TS, W, "dep:a", 99_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"})  # venta sin trabajo: no atribuible
    atribuida = ef.atribucion_por_suscripcion(k.libro.asientos(), SEMANAS, SUS)
    assert atribuida == {}


def test_eficiencia_sin_consumo_es_cero():
    assert ef.eficiencia_pormil(0, 0) == 0
    assert ef.eficiencia_pormil(5_000, 0) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_eficiencia.py -v`
Expected: FAIL (ImportError `eficiencia`; y `acunar` aún sin `detalle_extra`)

- [ ] **Step 3: Write minimal implementation**

En `kernel.py`, cambiar la firma de `acunar`:

```python
    def acunar(self, ts: str, semana: str, destino: str, monto: int,
               subtipo: SubtipoAcunacion, evidencia: dict,
               detalle_extra: dict | None = None) -> Asiento:
        if not isinstance(subtipo, SubtipoAcunacion):
            raise OperacionInvalida(f"subtipo debe ser SubtipoAcunacion: {subtipo!r}")
        if not evidencia:
            raise OperacionInvalida("acunar exige evidencia (invariante 4)")
        return self._append(
            ts=ts, semana=semana, tipo=TipoAsiento.ACUNACION,
            divisa=Divisa.MONEDA, monto=monto, destino=destino,
            subtipo=subtipo.value,
            detalle={"evidencia": evidencia} | (detalle_extra or {}))
```

```python
# calipso/economia/eficiencia.py
"""
calipso/economia/eficiencia.py — Resultado por unidad consumida.

Cada venta con trabajo de origen se prorratea entre los consumos de ese
trabajo, proporcional al costo API equivalente de cada consumo (spec 4.2).
El numerador es siempre senal exterior (subtipo venta); el capital y las
ventas sin trabajo no atribuyen nada.
"""
from __future__ import annotations

from .capacidad import Suscripcion
from .tipos import Asiento, DIRECCION, SubtipoAcunacion, TipoAsiento


def ventas_por_trabajo(asientos: list[Asiento],
                       semanas: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in asientos:
        if (a.tipo is TipoAsiento.ACUNACION
                and a.subtipo == SubtipoAcunacion.VENTA.value
                and a.semana in semanas and a.detalle.get("trabajo")):
            id = a.detalle["trabajo"]
            out[id] = out.get(id, 0) + a.monto
    return out


def costos_de_trabajo(asientos: list[Asiento], id: str,
                      suscripciones: dict[str, Suscripcion],
                      semanas: list[str] | None = None) -> dict[str, int]:
    ref = f"trabajo:{id}"
    out: dict[str, int] = {}
    for a in asientos:
        if a.ref != ref:
            continue
        if semanas is not None and a.semana not in semanas:
            continue
        if (a.tipo is TipoAsiento.DESTRUCCION
                and a.detalle.get("motivo") == "api"):
            out["api"] = out.get("api", 0) + a.monto
        elif (a.tipo is TipoAsiento.TRANSFERENCIA and a.destino == DIRECCION
                and a.detalle.get("suscripcion") in suscripciones):
            nombre = a.detalle["suscripcion"]
            sus = suscripciones[nombre]
            clave = f"sus:{nombre}"
            out[clave] = out.get(clave, 0) + \
                a.detalle["unidades"] * sus.costo_api_mm_por_unidad
    return out


def atribucion_por_suscripcion(asientos: list[Asiento], semanas: list[str],
                               suscripciones: dict[str, Suscripcion]
                               ) -> dict[str, int]:
    out: dict[str, int] = {}
    for id, venta in ventas_por_trabajo(asientos, semanas).items():
        costos = costos_de_trabajo(asientos, id, suscripciones)
        total = sum(costos.values())
        if total == 0:
            continue
        for clave, costo in costos.items():
            if clave.startswith("sus:"):
                nombre = clave[4:]
                out[nombre] = out.get(nombre, 0) + venta * costo // total
    return out


def eficiencia_pormil(atribuido_mm: int, consumido_api_mm: int) -> int:
    if consumido_api_mm <= 0:
        return 0
    return atribuido_mm * 1000 // consumido_api_mm


def eficiencia_suscripcion(asientos: list[Asiento], sus: Suscripcion,
                           semanas: list[str],
                           suscripciones: dict[str, Suscripcion]) -> int:
    atribuida = atribucion_por_suscripcion(asientos, semanas,
                                           suscripciones).get(sus.nombre, 0)
    consumido = sum(a.detalle["unidades"] * sus.costo_api_mm_por_unidad
                    for a in asientos
                    if a.tipo is TipoAsiento.TRANSFERENCIA
                    and a.destino == DIRECCION
                    and a.detalle.get("suscripcion") == sus.nombre
                    and a.semana in semanas)
    return eficiencia_pormil(atribuida, consumido)


def costo_api_directo(asientos: list[Asiento], dep_cuenta: str,
                      semanas: list[str],
                      suscripciones: dict[str, Suscripcion]) -> int:
    """Gasto directo del departamento (sin trabajos) en API equivalente."""
    total = 0
    for a in asientos:
        if a.origen != dep_cuenta or a.semana not in semanas:
            continue
        if (a.tipo is TipoAsiento.DESTRUCCION
                and a.detalle.get("motivo") == "api"):
            total += a.monto
        elif (a.tipo is TipoAsiento.TRANSFERENCIA and a.destino == DIRECCION
                and a.detalle.get("suscripcion") in suscripciones):
            sus = suscripciones[a.detalle["suscripcion"]]
            total += a.detalle["unidades"] * sus.costo_api_mm_por_unidad
    return total


def eficiencia_departamento(asientos: list[Asiento], dep_cuenta: str,
                            semanas: list[str],
                            suscripciones: dict[str, Suscripcion],
                            duenos: dict[str, str]) -> int:
    ventas = sum(v for id, v in ventas_por_trabajo(asientos, semanas).items()
                 if duenos.get(id) == dep_cuenta)
    consumido = costo_api_directo(asientos, dep_cuenta, semanas, suscripciones)
    trabajos = {id for id, d in duenos.items() if d == dep_cuenta}
    for id in trabajos:
        consumido += sum(costos_de_trabajo(asientos, id, suscripciones,
                                           semanas).values())
    return eficiencia_pormil(ventas, consumido)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_eficiencia.py -v`
Expected: PASS (7 tests). Regresión: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_kernel.py -v` verde (la firma de `acunar` es retro-compatible).

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/eficiencia.py calipso/economia/kernel.py test_economia_eficiencia.py
git commit -m "feat(economia): eficiencia — atribucion de ventas prorrateada por costo API"
```

---

### Task 8: Cierre semanal y mensual orquestado

**Files:**
- Create: `calipso/economia/cierre.py`
- Modify: `calipso/economia/__init__.py` (exportar módulos nuevos)
- Test: `test_economia_cierre.py`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: `@dataclass CierreEconomia(semana, quiebras: list[str], trabajos_muertos: list[str], cartas: list[dict], cierre_pt: pt.CierreSemana)`; `cerrar_semana_economia(mercado, bus, ts, semana, refs_no_servidas=(), presupuesto_direccion_mm=0, ventana_carta_cierre=8, umbral_mandato_mm=direccion.UMBRAL_MANDATO_MM) -> CierreEconomia`. Orden: (1) `bus.evaluar_y_liquidar_muertos`; (2) quiebras: departamentos de fábrica activos con `disponible <= 0` → `declarar_quiebra` (los ya congelados no se re-declaran); (3) presupuesto de dirección (`transferir TESORO→DIRECCION` motivo "presupuesto_direccion") si `presupuesto_direccion_mm > 0`; (4) presupuestos semanales: cada dep de fábrica no congelado con `presupuesto_semanal_mm > 0` vía `direccion.asignar_presupuesto` sin firma — si el mandato lo rechaza, carta `{"tipo": "mandato", "departamento", "monto"}`; si el tesoro no alcanza (`SinSaldo`), carta `{"tipo": "tesoro_insuficiente", ...}`; (5) cartas de cierre departamental: dep de fábrica que lleva `>= ventana_carta_cierre` semanas operativas de existencia (contando su primera semana Y la actual) sin ACUNACION venta (a su cuenta o a un trabajo suyo — `duenos` derivado de `bus`) en la ventana → carta `{"tipo": "cierre_departamento", "departamento"}`; (6) `pt.cerrar_semana`. El cierre semanal es IDEMPOTENTE: un segundo llamado sobre la misma semana no re-asigna presupuestos (salta al dep que ya recibió su presupuesto semanal) ni re-declara quiebras. Y `cerrar_ciclo(mercado, ts, semana, cartas_atendidas=frozenset(), firmas=None) -> list[dict]` — al terminar un ciclo (la semana es la última del ciclo n): para cada suscripción, informe `{"suscripcion", "recaudacion_mm", "costo_fabrica_mm", "rojo": bool, "rojos_consecutivos": int, "renovada": bool, "requiere_firma": bool}`; renovación = `destruir(TESORO, costo_mensual_mm, motivo="renovacion", ref=f"renovacion:{nombre}")`; circuit breaker: si los DOS últimos ciclos fueron rojos y `f"renovacion:{nombre}"` no está en `cartas_atendidas`, la renovación exige `firmas[nombre]` — sin firma NO se renueva y `requiere_firma=True`.

- [ ] **Step 1: Write the failing tests**

```python
# test_economia_cierre.py
"""Tests del cierre semanal y mensual: el pulso de la economia."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import cierre
from calipso.economia import departamentos as deps
from calipso.economia import mercado as mkt
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"

SUS = {"claude_max": cap.Suscripcion("claude_max", 100_000, 1_000, 200, 500)}


@pytest.fixture
def entorno(tmp_path):
    k = Kernel(Libro(tmp_path / "libro.jsonl"))
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=10_000,
                             techo_api_ciclo_mm=500_000))
    r.alta(deps.Departamento("b", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=10_000,
                             techo_api_ciclo_mm=500_000))
    m = mkt.Mercado(k, r, SUS)
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    k.acunar(TS, "2026-W30", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    return k, m, b


def _semana(k, semana):
    pt.emitir_semana(k, TS, semana, 4_000, 0)


def test_cierre_semanal_asigna_declara_y_cierra(entorno):
    k, m, b = entorno
    _semana(k, "2026-W30")
    # dep:b gasta hasta quedar en cero para quebrar en el cierre
    cierre_0 = cierre.cerrar_semana_economia(m, b, TS, "2026-W30")
    assert k.saldo("dep:a") == 10_000 and k.saldo("dep:b") == 10_000
    assert cierre_0.quiebras == []
    # idempotencia: un reintento del mismo cierre no paga dos veces
    cierre.cerrar_semana_economia(m, b, TS, "2026-W30")
    assert k.saldo("dep:a") == 10_000 and k.saldo("dep:b") == 10_000
    m.gastar_api(TS, "2026-W30", "dep:b", 10_000)
    _semana(k, "2026-W31")
    c = cierre.cerrar_semana_economia(m, b, TS, "2026-W31")
    assert c.quiebras == ["dep:b"]
    assert deps.es_congelado(k.libro.asientos(), "dep:b")
    # el congelado no recibio presupuesto en ese cierre; el activo si
    assert k.saldo("dep:a") == 20_000
    assert k.saldo("dep:b") == 0
    # y el cierre siguiente no re-declara la quiebra
    _semana(k, "2026-W32")
    c2 = cierre.cerrar_semana_economia(m, b, TS, "2026-W32")
    assert c2.quiebras == []


def test_carta_de_mandato_cuando_presupuesto_excede(entorno):
    k, m, b = entorno
    m.registro.ajustar("a", presupuesto_semanal_mm=150_000)  # > umbral 100k
    _semana(k, "2026-W30")
    c = cierre.cerrar_semana_economia(m, b, TS, "2026-W30")
    assert any(carta["tipo"] == "mandato" and carta["departamento"] == "dep:a"
               for carta in c.cartas)
    assert k.saldo("dep:a") == 0  # no se asigno sin firma


def test_carta_de_cierre_departamental(entorno):
    k, m, b = entorno
    semanas = [f"2026-W{n}" for n in range(30, 34)]
    for sem in semanas:
        _semana(k, sem)
        c = cierre.cerrar_semana_economia(m, b, TS, sem,
                                          ventana_carta_cierre=3)
    # tras 4 semanas operativas sin ventas, ambos deps tienen carta
    tipos = [carta["tipo"] for carta in c.cartas]
    assert tipos.count("cierre_departamento") == 2
    # una venta al dep la evita la semana siguiente
    k.acunar(TS, "2026-W33", "dep:a", 1_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"})
    _semana(k, "2026-W34")
    c2 = cierre.cerrar_semana_economia(m, b, TS, "2026-W34",
                                       ventana_carta_cierre=3)
    afectados = [carta["departamento"] for carta in c2.cartas
                 if carta["tipo"] == "cierre_departamento"]
    assert afectados == ["dep:b"]


def _ciclo_completo(k, m, b, semanas, unidades_por_semana=0):
    for sem in semanas:
        _semana(k, sem)
        cierre.cerrar_semana_economia(m, b, TS, sem)  # asigna presupuestos
        if unidades_por_semana:
            m.comprar_capacidad(TS, sem, "dep:a", "claude_max",
                                unidades_por_semana)


def test_cierre_de_ciclo_renueva_automatico_si_no_es_rojo(entorno):
    k, m, b = entorno
    m.registro.ajustar("a", presupuesto_semanal_mm=100_000)
    # 4 semanas comprando a ritmo la cuota completa (800 unidades a precio
    # base 100): recaudacion 80_000 == costo prorrateado -> no es rojo
    semanas = ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]
    _ciclo_completo(k, m, b, semanas, unidades_por_semana=200)
    tesoro_antes = k.saldo(t.TESORO)
    informes = cierre.cerrar_ciclo(m, TS, "2026-W33")
    inf = informes[0]
    assert inf["rojo"] is False and inf["renovada"] is True
    assert k.saldo(t.TESORO) == tesoro_antes - 100_000
    # idempotencia: un reintento no destruye el tesoro dos veces
    informes_bis = cierre.cerrar_ciclo(m, TS, "2026-W33")
    assert informes_bis[0]["renovada"] is True
    assert k.saldo(t.TESORO) == tesoro_antes - 100_000


def test_circuit_breaker_tras_dos_ciclos_rojos_sin_atender(entorno):
    k, m, b = entorno
    semanas = [f"2026-W{n}" for n in range(30, 38)]  # 2 ciclos, sin compras
    _ciclo_completo(k, m, b, semanas)
    informes_1 = cierre.cerrar_ciclo(m, TS, "2026-W33")
    assert informes_1[0]["rojo"] is True and informes_1[0]["renovada"] is True
    informes_2 = cierre.cerrar_ciclo(m, TS, "2026-W37")
    inf = informes_2[0]
    assert inf["rojos_consecutivos"] == 2
    assert inf["requiere_firma"] is True and inf["renovada"] is False
    # con firma, renueva
    informes_3 = cierre.cerrar_ciclo(m, TS, "2026-W37",
                                     firmas={"claude_max": {"tipo": "firma_pedro"}})
    assert informes_3[0]["renovada"] is True


def test_ciclo_incompleto_no_renueva(entorno):
    k, m, b = entorno
    _semana(k, "2026-W30")
    cierre.cerrar_semana_economia(m, b, TS, "2026-W30")
    assert cierre.cerrar_ciclo(m, TS, "2026-W30") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_cierre.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.cierre`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/cierre.py
"""
calipso/economia/cierre.py — El pulso de la economia.

El cierre semanal ejecuta en orden: muertes de trabajos, quiebras,
presupuestos (direccion y departamentos, dentro del mandato), cartas de
cierre departamental, y el cierre de PT. El cierre de ciclo (cada 4
semanas operativas) decide renovaciones con numeros — recaudacion contra
costo prorrateado — y aplica el circuit breaker: dos ciclos rojos con la
carta sin atender vuelven la renovacion manual (spec 4.2).
Las cartas son datos devueltos; la cola que las presenta es del Plan 3.
"""
from __future__ import annotations

from dataclasses import dataclass

from . import bus as bus_mod
from . import capacidad as cap
from . import departamentos as deps
from . import direccion
from . import pt
from .kernel import SinSaldo
from .mercado import Mercado
from .tipos import DIRECCION, SubtipoAcunacion, TESORO, TipoAsiento


@dataclass(frozen=True)
class CierreEconomia:
    semana: str
    quiebras: list
    trabajos_muertos: list
    cartas: list
    cierre_pt: pt.CierreSemana


def _primera_semana(asientos, cuenta: str) -> str | None:
    for a in asientos:
        if cuenta in (a.origen, a.destino) or \
                a.detalle.get("departamento") == cuenta:
            return a.semana
    return None


def _ventas_en(asientos, cuentas: set[str], semanas: list[str]) -> int:
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.ACUNACION
               and a.subtipo == SubtipoAcunacion.VENTA.value
               and a.destino in cuentas and a.semana in semanas)


def cerrar_semana_economia(mercado: Mercado, bus: bus_mod.Bus, ts: str,
                           semana: str, refs_no_servidas: list[str] = (),
                           presupuesto_direccion_mm: int = 0,
                           ventana_carta_cierre: int = 8,
                           umbral_mandato_mm: int = direccion.UMBRAL_MANDATO_MM
                           ) -> CierreEconomia:
    k = mercado.k
    cartas: list[dict] = []

    # 1) trabajos muertos
    muertos = bus_mod.evaluar_y_liquidar_muertos(mercado, bus, ts, semana)

    # 2) quiebras nuevas (solo fabrica; los ya congelados no se re-declaran)
    quiebras: list[str] = []
    for dep in mercado.registro.todos():
        if dep.zona != deps.ZONA_FABRICA:
            continue
        asientos = k.libro.asientos()
        if (not deps.es_congelado(asientos, dep.cuenta)
                and k.disponible(dep.cuenta) <= 0
                and _primera_semana(asientos, dep.cuenta) is not None
                and _primera_semana(asientos, dep.cuenta) < semana):
            deps.declarar_quiebra(k, ts, semana, dep.cuenta)
            quiebras.append(dep.cuenta)

    # 3) presupuesto de direccion
    if presupuesto_direccion_mm > 0:
        k.transferir(ts, semana, TESORO, DIRECCION, presupuesto_direccion_mm,
                     motivo="presupuesto_direccion")

    # 4) presupuestos semanales de departamentos
    for dep in mercado.registro.todos():
        if dep.zona != deps.ZONA_FABRICA or dep.presupuesto_semanal_mm <= 0:
            continue
        if deps.es_congelado(k.libro.asientos(), dep.cuenta):
            continue
        ya = direccion.asignado_semana(k.libro.asientos(), dep.cuenta, semana)
        if ya >= dep.presupuesto_semanal_mm:
            continue  # idempotencia: un reintento del cierre no paga dos veces
        try:
            direccion.asignar_presupuesto(mercado, ts, semana, dep.cuenta,
                                          dep.presupuesto_semanal_mm - ya,
                                          umbral_mm=umbral_mandato_mm)
        except direccion.ErrorDireccion:
            cartas.append({"tipo": "mandato", "departamento": dep.cuenta,
                           "monto": dep.presupuesto_semanal_mm})
        except SinSaldo:
            cartas.append({"tipo": "tesoro_insuficiente",
                           "departamento": dep.cuenta,
                           "monto": dep.presupuesto_semanal_mm})

    # 5) cartas de cierre departamental
    asientos = k.libro.asientos()
    ops = cap.semanas_operativas(asientos)
    duenos = {id: bus.datos(id)["departamento"] for id in bus.ids()}
    ventana = ops[-ventana_carta_cierre:]
    for dep in mercado.registro.todos():
        if dep.zona != deps.ZONA_FABRICA:
            continue
        primera = _primera_semana(asientos, dep.cuenta)
        if primera is None or primera not in ops:
            continue
        if len(ops) - ops.index(primera) < ventana_carta_cierre:
            continue  # todavia no vivio la ventana completa
        cuentas = {dep.cuenta} | {bus_mod.cuenta_trabajo(id)
                                  for id, d in duenos.items()
                                  if d == dep.cuenta}
        if _ventas_en(asientos, cuentas, ventana) == 0:
            cartas.append({"tipo": "cierre_departamento",
                           "departamento": dep.cuenta})

    # 6) cierre de PT
    cierre_pt = pt.cerrar_semana(k, ts, semana,
                                 refs_reservas_no_servidas=list(refs_no_servidas))
    return CierreEconomia(semana=semana, quiebras=quiebras,
                          trabajos_muertos=muertos, cartas=cartas,
                          cierre_pt=cierre_pt)


def _rojo_de_ciclo(asientos, sus: cap.Suscripcion, ciclo: int,
                   ops: list[str]) -> bool:
    semanas = cap.semanas_del_ciclo(ciclo, ops)
    return cap.recaudacion(asientos, sus.nombre, semanas) < sus.costo_fabrica_mm


def cerrar_ciclo(mercado: Mercado, ts: str, semana: str,
                 cartas_atendidas: frozenset = frozenset(),
                 firmas: dict | None = None) -> list[dict]:
    firmas = firmas or {}
    k = mercado.k
    asientos = k.libro.asientos()
    ops = cap.semanas_operativas(asientos)
    ciclo, fraccion = cap.posicion_ciclo(semana, ops)
    if fraccion != 100:
        return []  # la semana no cierra un ciclo
    informes: list[dict] = []
    for nombre, sus in sorted(mercado.suscripciones.items()):
        semanas = cap.semanas_del_ciclo(ciclo, ops)
        recaudado = cap.recaudacion(asientos, nombre, semanas)
        rojo = recaudado < sus.costo_fabrica_mm
        rojos = 0
        c = ciclo
        while c >= 0 and _rojo_de_ciclo(asientos, sus, c, ops):
            rojos += 1
            c -= 1
        carta_id = f"renovacion:{nombre}"
        breaker = (rojos >= 2 and carta_id not in cartas_atendidas)
        requiere_firma = breaker and not firmas.get(nombre)
        ya_renovada = any(a.tipo is TipoAsiento.DESTRUCCION
                          and a.ref == carta_id and a.semana in semanas
                          for a in asientos)
        renovada = ya_renovada
        if not requiere_firma and not ya_renovada:
            detalle = {"firma": firmas[nombre]} if firmas.get(nombre) else None
            k.destruir(ts, semana, TESORO, sus.costo_mensual_mm,
                       motivo="renovacion", ref=carta_id,
                       detalle_extra=detalle)
            renovada = True
        informes.append({"suscripcion": nombre, "recaudacion_mm": recaudado,
                         "costo_fabrica_mm": sus.costo_fabrica_mm,
                         "rojo": rojo, "rojos_consecutivos": rojos,
                         "renovada": renovada,
                         "requiere_firma": requiere_firma})
    return informes
```

```python
# calipso/economia/__init__.py — sumar al bloque de imports existente
from . import bus, capacidad, cierre, departamentos, direccion, eficiencia, mercado  # noqa: F401
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_cierre.py -v`
Expected: PASS (6 tests). Suite completa: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_libro.py test_economia_kernel.py test_economia_pt.py test_economia_capacidad.py test_economia_mercado.py test_economia_bus.py test_economia_eficiencia.py test_economia_cierre.py -v` toda verde, y `test_resource_dispatcher.py` también.

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/cierre.py calipso/economia/__init__.py test_economia_cierre.py
git commit -m "feat(economia): cierre semanal y mensual — quiebras, presupuestos, cartas y breaker"
```

---

## Qué queda para el Plan 3 (NO implementar acá)

Cola de compuertas de dos carriles (usa `reservar`/`ejecutar_reserva` + las cartas de este plan), reloj clock-in (dispara los cobros con tiempo real), departamento personal de finanzas con libros privados, cuenta pagadora obligatoria en `dispatch.py` — que para pagadores `trabajo:<id>` resuelve el dueño vía bus y rutea SIEMPRE por `Mercado.gastar_api`/`comprar_capacidad` con `dueno=` (la puerta ya existe en este plan; ningún gasto real va por kernel directo) —, endpoints en `server.py`, atención de cartas (el registro de `cartas_atendidas` y `firmas` que acá son parámetros), locking de escritor único, y la simulación de ciclo completo de spec sección 13.
