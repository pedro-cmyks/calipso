# Kernel de Economía (Plan 1 de 3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir el kernel de economía de Calipso: libro contable append-only de dos divisas (moneda y pedro-token), balances derivados, escrow sin sobregiro, acuñación verificada con subtipos, acreencias, emisión/consumo/expiración de PT, tipo de cambio determinístico y cierre semanal.

**Architecture:** Paquete nuevo `calipso/economia/` con módulos chicos y puros: los montos son enteros (milimonedas / mili-PT), el estado se deriva siempre plegando el libro (nunca se edita un balance), y ninguna función lee el reloj del sistema — `ts` y `semana` son siempre parámetros. Persistencia JSONL en `~/.calipso/economia/` siguiendo el patrón de `calipso/costs.py`.

**Tech Stack:** Python 3.14, solo stdlib (dataclasses, enum, json, pathlib). Tests con pytest en la raíz del repo, patrón de `test_resource_dispatcher.py`.

**Spec:** `docs/superpowers/specs/2026-08-24-cerebro-central-economia-monedas-design.md` (secciones 2, 3, 4.0, 4.1, 4.4 parcial y 5 parcial). Este plan cubre el kernel; el Plan 2 (mercado y departamentos: suscripciones/capacidad, precio por escasez, eficiencia, departamentos, quiebra/congelado, bus, dirección) y el Plan 3 (frontera y operación: cola de compuertas, reloj clock-in, departamento personal, integración server/dispatch, simulación completa) se escriben cuando este ejecute.

## Global Constraints

- Python 3.14, sin dependencias nuevas: solo stdlib.
- Montos SIEMPRE `int`: milimonedas (1 moneda = 1.000 milimonedas = 1 USD) y mili-PT (1 PT = 1.000 mili-PT = 1 hora firmable). Nunca `float` en montos. Conversiones desde USD redondean al alza en destrucciones (`math.ceil`).
- Determinismo (spec invariantes 3 y 8): ningún módulo de `calipso/economia/` llama `datetime.now()`, `time.time()` ni RNG. `ts` (ISO 8601) y `semana` (formato `"YYYY-Www"` con cero a la izquierda, p. ej. `"2026-W05"`) son parámetros del llamador.
- El libro es append-only: nunca se edita ni borra una línea. Todo estado (saldos, reservas, pools PT, tipo de cambio) se deriva plegando los asientos.
- Sin sobregiro (spec invariante 7): toda salida de una cuenta valida `disponible >= monto` y se rechaza con excepción si no alcanza.
- Acuñación (spec invariantes 1 y 4): requiere subtipo (`venta` | `capital`) y evidencia no vacía en `detalle["evidencia"]`.
- Código, docstrings y nombres de tests en español, sin emojis (preferencia de Pedro). Estilo del repo: `from __future__ import annotations`, dataclasses, módulos con docstring de cabecera explicando el porqué.
- Tests: pytest REAL en la raíz del repo. Correr siempre dirigido: `pytest test_economia_*.py -v` — jamás `pytest` a secas (los otros `test_*.py` del repo son scripts con `main()` que rompen la colección). Los tests usan `tmp_path`; nunca tocan `~/.calipso`.
- Ruta de datos por defecto (solo para uso real, no tests): `CALIPSO_HOME / "economia" / "libro.jsonl"` con `CALIPSO_HOME = ~/.calipso` (mismo patrón que `calipso/costs.py`).

## File Structure

- Create: `calipso/economia/__init__.py` — exporta la API pública del paquete.
- Create: `calipso/economia/tipos.py` — constantes, enums (`Divisa`, `TipoAsiento`, `SubtipoAcunacion`), dataclass `Asiento` con validación y serialización JSON.
- Create: `calipso/economia/libro.py` — `Libro`: persistencia JSONL append-only, numeración correlativa, carga tolerante a última línea truncada.
- Create: `calipso/economia/balances.py` — funciones puras de derivación: `saldos()`, `reservas_activas()`, `disponible()`.
- Create: `calipso/economia/kernel.py` — `Kernel`: operaciones validadas (acuñar, destruir, transferir, escrow, acreencias, liquidación).
- Create: `calipso/economia/pt.py` — emisión/consumo/expiración de PT, apunte de costo de oportunidad, `tipo_de_cambio()`, `cerrar_semana()`.
- Create: `calipso/economia/cuenta_pedro.py` — las cuatro salidas tipadas de la cuenta de Pedro.
- Test: `test_economia_libro.py` (tareas 1-3), `test_economia_kernel.py` (tareas 4-6 y 9), `test_economia_pt.py` (tareas 7-8 y 10).

---

### Task 1: Tipos y asientos

**Files:**
- Create: `calipso/economia/__init__.py`
- Create: `calipso/economia/tipos.py`
- Test: `test_economia_libro.py`

**Interfaces:**
- Consumes: nada (primer módulo).
- Produces: `MILIS: int`; enums `Divisa` (`MONEDA`, `PT`), `TipoAsiento` (`ACUNACION`, `DESTRUCCION`, `TRANSFERENCIA`, `RESERVA`, `LIBERACION`, `EJECUCION_RESERVA`, `EMISION_PT`, `CONSUMO_PT`, `EXPIRACION_PT`, `APUNTE`, `ACREENCIA`), `SubtipoAcunacion` (`VENTA`, `CAPITAL`); constantes de cuenta `TESORO`, `CUENTA_PEDRO`, `DIRECCION`, `POOL_PT_FABRICA`, `POOL_PT_PERSONAL`; excepción `AsientoInvalido`; dataclass congelada `Asiento(seq, ts, semana, tipo, divisa, monto, origen=None, destino=None, subtipo=None, ref=None, detalle={})` con métodos `validar() -> None`, `a_json() -> str` y estática `Asiento.de_json(linea: str) -> Asiento`.

- [ ] **Step 1: Write the failing test**

```python
# test_economia_libro.py
"""Tests del kernel de economia: tipos, libro y balances."""
import pytest

from calipso.economia import tipos as t


def test_asiento_roundtrip_json():
    """Un asiento sobrevive el viaje a JSON y de vuelta, campo por campo."""
    a = t.Asiento(
        seq=1, ts="2026-08-24T10:00:00", semana="2026-W35",
        tipo=t.TipoAsiento.TRANSFERENCIA, divisa=t.Divisa.MONEDA,
        monto=2_500, origen="dep:mercado", destino=t.DIRECCION,
        ref="cap-001", detalle={"motivo": "capacidad"},
    )
    b = t.Asiento.de_json(a.a_json())
    assert b == a


def test_acunacion_exige_subtipo_y_evidencia():
    """Invariantes 1 y 4: acunar sin subtipo o sin evidencia es invalido."""
    base = dict(seq=1, ts="2026-08-24T10:00:00", semana="2026-W35",
                tipo=t.TipoAsiento.ACUNACION, divisa=t.Divisa.MONEDA,
                monto=25_000, destino=t.TESORO)
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base).validar()  # sin subtipo
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base, subtipo="venta").validar()  # sin evidencia
    ok = t.Asiento(**base, subtipo="capital",
                   detalle={"evidencia": {"tipo": "firma_pedro"}})
    ok.validar()  # no levanta


def test_monto_debe_ser_entero_positivo():
    base = dict(seq=1, ts="2026-08-24T10:00:00", semana="2026-W35",
                tipo=t.TipoAsiento.DESTRUCCION, divisa=t.Divisa.MONEDA,
                origen=t.TESORO)
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base, monto=0).validar()
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base, monto=-5).validar()
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base, monto=1.5).validar()


def test_transferencia_exige_origen_y_destino_distintos():
    base = dict(seq=1, ts="2026-08-24T10:00:00", semana="2026-W35",
                tipo=t.TipoAsiento.TRANSFERENCIA, divisa=t.Divisa.MONEDA,
                monto=100)
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base, origen="a").validar()  # sin destino
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(**base, origen="a", destino="a").validar()  # iguales


def test_semana_exige_formato_iso_con_cero():
    """El orden lexicografico de semanas solo funciona con cero a la izquierda."""
    with pytest.raises(t.AsientoInvalido):
        t.Asiento(seq=1, ts="2026-08-24T10:00:00", semana="2026-W5",
                  tipo=t.TipoAsiento.APUNTE, divisa=t.Divisa.MONEDA,
                  monto=1, detalle={"nota": "x"}).validar()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest test_economia_libro.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'calipso.economia'`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/__init__.py
"""calipso/economia — kernel de la economia de la fabrica (spec 2026-08-24)."""
```

```python
# calipso/economia/tipos.py
"""
calipso/economia/tipos.py — Tipos base del libro contable.

Dos divisas: la moneda (1 moneda = 1.000 milimonedas = 1 USD) y el
pedro-token (1 PT = 1.000 mili-PT = 1 hora firmable de Pedro). Todos los
montos son enteros; el estado se deriva del libro, nunca se edita.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from enum import Enum

MILIS = 1000

TESORO = "tesoro"
CUENTA_PEDRO = "cuenta_pedro"
DIRECCION = "direccion"
POOL_PT_FABRICA = "pt:fabrica"
POOL_PT_PERSONAL = "pt:personal"

_RE_SEMANA = re.compile(r"^\d{4}-W\d{2}$")


class Divisa(str, Enum):
    MONEDA = "moneda"
    PT = "pt"


class TipoAsiento(str, Enum):
    ACUNACION = "acunacion"
    DESTRUCCION = "destruccion"
    TRANSFERENCIA = "transferencia"
    RESERVA = "reserva"
    LIBERACION = "liberacion"
    EJECUCION_RESERVA = "ejecucion_reserva"
    EMISION_PT = "emision_pt"
    CONSUMO_PT = "consumo_pt"
    EXPIRACION_PT = "expiracion_pt"
    APUNTE = "apunte"
    ACREENCIA = "acreencia"


class SubtipoAcunacion(str, Enum):
    VENTA = "venta"
    CAPITAL = "capital"


class AsientoInvalido(Exception):
    pass


_POOLS_PT = {POOL_PT_FABRICA, POOL_PT_PERSONAL}


@dataclass(frozen=True)
class Asiento:
    seq: int
    ts: str
    semana: str
    tipo: TipoAsiento
    divisa: Divisa
    monto: int
    origen: str | None = None
    destino: str | None = None
    subtipo: str | None = None
    ref: str | None = None
    detalle: dict = field(default_factory=dict, compare=True)

    def validar(self) -> None:
        if not isinstance(self.monto, int) or isinstance(self.monto, bool) \
                or self.monto <= 0:
            raise AsientoInvalido(f"monto debe ser entero positivo: {self.monto!r}")
        if not _RE_SEMANA.match(self.semana):
            raise AsientoInvalido(f"semana debe ser YYYY-Www: {self.semana!r}")
        t = self.tipo
        if t is TipoAsiento.ACUNACION:
            if self.divisa is not Divisa.MONEDA or not self.destino or self.origen:
                raise AsientoInvalido("acunacion: divisa moneda, destino si, origen no")
            if self.subtipo not in {s.value for s in SubtipoAcunacion}:
                raise AsientoInvalido(f"acunacion exige subtipo venta|capital: {self.subtipo!r}")
            if not self.detalle.get("evidencia"):
                raise AsientoInvalido("acunacion exige detalle['evidencia'] (invariante 4)")
        elif t is TipoAsiento.DESTRUCCION:
            if not self.origen or self.destino:
                raise AsientoInvalido("destruccion: origen si, destino no")
        elif t in (TipoAsiento.TRANSFERENCIA, TipoAsiento.EJECUCION_RESERVA):
            if not self.origen or not self.destino or self.origen == self.destino:
                raise AsientoInvalido(f"{t.value}: origen y destino distintos requeridos")
            if t is TipoAsiento.EJECUCION_RESERVA and not self.ref:
                raise AsientoInvalido("ejecucion_reserva exige ref de la reserva")
        elif t is TipoAsiento.RESERVA:
            if not self.origen or not self.ref:
                raise AsientoInvalido("reserva exige origen y ref")
        elif t is TipoAsiento.LIBERACION:
            if not self.ref:
                raise AsientoInvalido("liberacion exige ref")
        elif t is TipoAsiento.EMISION_PT:
            if self.divisa is not Divisa.PT or self.destino not in _POOLS_PT:
                raise AsientoInvalido("emision_pt: divisa pt y destino un pool pt:*")
        elif t in (TipoAsiento.CONSUMO_PT, TipoAsiento.EXPIRACION_PT):
            if self.divisa is not Divisa.PT or self.origen not in _POOLS_PT:
                raise AsientoInvalido(f"{t.value}: divisa pt y origen un pool pt:*")
        elif t is TipoAsiento.ACREENCIA:
            d = self.detalle
            if not d.get("acreedor") or not d.get("deudor"):
                raise AsientoInvalido("acreencia exige detalle acreedor y deudor")

    def a_json(self) -> str:
        d = asdict(self)
        d["tipo"] = self.tipo.value
        d["divisa"] = self.divisa.value
        return json.dumps(d, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def de_json(linea: str) -> "Asiento":
        d = json.loads(linea)
        d["tipo"] = TipoAsiento(d["tipo"])
        d["divisa"] = Divisa(d["divisa"])
        return Asiento(**d)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest test_economia_libro.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/__init__.py calipso/economia/tipos.py test_economia_libro.py
git commit -m "feat(economia): tipos base del libro — asientos, divisas, validacion"
```

---

### Task 2: Libro append-only con persistencia JSONL

**Files:**
- Create: `calipso/economia/libro.py`
- Test: `test_economia_libro.py` (agregar tests)

**Interfaces:**
- Consumes: `Asiento`, `AsientoInvalido`, enums de `tipos.py`.
- Produces: clase `Libro(ruta: pathlib.Path)` con `append(**campos) -> Asiento` (asigna `seq` correlativo desde 1, valida, persiste una línea JSON con flush) y `asientos() -> list[Asiento]` (lista en memoria, cargada al abrir). Excepción `ErrorLibro(Exception)`; `AsientoInvalido` pasa a heredar de `ErrorLibro` o se reexporta — mantener `AsientoInvalido` en `tipos.py` y `ErrorLibro` en `libro.py` como base de errores de persistencia (`LibroCorrupto`).

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_libro.py
from calipso.economia.libro import Libro, LibroCorrupto


def _libro(tmp_path):
    return Libro(tmp_path / "libro.jsonl")


def test_append_asigna_seq_correlativo_y_persiste(tmp_path):
    lb = _libro(tmp_path)
    a1 = lb.append(ts="2026-08-24T10:00:00", semana="2026-W35",
                   tipo=t.TipoAsiento.ACUNACION, divisa=t.Divisa.MONEDA,
                   monto=1_200_000, destino=t.TESORO, subtipo="capital",
                   detalle={"evidencia": {"tipo": "firma_pedro"}})
    a2 = lb.append(ts="2026-08-24T10:01:00", semana="2026-W35",
                   tipo=t.TipoAsiento.TRANSFERENCIA, divisa=t.Divisa.MONEDA,
                   monto=100_000, origen=t.TESORO, destino="dep:mercado")
    assert (a1.seq, a2.seq) == (1, 2)
    # reabrir desde disco reproduce exactamente lo mismo
    lb2 = _libro(tmp_path)
    assert lb2.asientos() == [a1, a2]


def test_append_invalido_no_persiste(tmp_path):
    lb = _libro(tmp_path)
    with pytest.raises(t.AsientoInvalido):
        lb.append(ts="2026-08-24T10:00:00", semana="2026-W35",
                  tipo=t.TipoAsiento.ACUNACION, divisa=t.Divisa.MONEDA,
                  monto=5, destino=t.TESORO)  # sin subtipo ni evidencia
    assert lb.asientos() == []
    assert _libro(tmp_path).asientos() == []


def test_ultima_linea_truncada_se_ignora_con_aviso(tmp_path):
    """Un corte de luz a mitad de un append no puede tumbar el libro entero."""
    lb = _libro(tmp_path)
    a1 = lb.append(ts="2026-08-24T10:00:00", semana="2026-W35",
                   tipo=t.TipoAsiento.ACUNACION, divisa=t.Divisa.MONEDA,
                   monto=1_000, destino=t.TESORO, subtipo="capital",
                   detalle={"evidencia": {"tipo": "firma_pedro"}})
    ruta = tmp_path / "libro.jsonl"
    with ruta.open("a", encoding="utf-8") as f:
        f.write('{"seq": 2, "ts": "2026-08-2')  # linea cortada
    lb2 = _libro(tmp_path)
    assert lb2.asientos() == [a1]
    # y el proximo append sigue la numeracion sana
    a2 = lb2.append(ts="2026-08-24T11:00:00", semana="2026-W35",
                    tipo=t.TipoAsiento.DESTRUCCION, divisa=t.Divisa.MONEDA,
                    monto=100, origen=t.TESORO)
    assert a2.seq == 2


def test_linea_corrupta_en_el_medio_es_error(tmp_path):
    """Corrupcion que NO es la ultima linea no se tolera: hay que mirar."""
    ruta = tmp_path / "libro.jsonl"
    ruta.write_text('esto no es json\n{"tampoco": 1}\n', encoding="utf-8")
    with pytest.raises(LibroCorrupto):
        Libro(ruta)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_economia_libro.py -v`
Expected: FAIL con `ModuleNotFoundError` / `ImportError` sobre `calipso.economia.libro`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/libro.py
"""
calipso/economia/libro.py — Persistencia append-only del libro contable.

Una linea JSON por asiento. Nunca se edita ni borra una linea; todo estado
se deriva plegando los asientos. La carga tolera exactamente un defecto:
la ultima linea truncada (corte a mitad de un append). Cualquier otra
corrupcion levanta LibroCorrupto: eso se mira, no se ignora.
"""
from __future__ import annotations

import logging
import pathlib

from .tipos import Asiento

log = logging.getLogger("calipso.economia.libro")


class ErrorLibro(Exception):
    pass


class LibroCorrupto(ErrorLibro):
    pass


class Libro:
    def __init__(self, ruta: pathlib.Path):
        self.ruta = pathlib.Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._asientos: list[Asiento] = []
        self._cargar()

    def _cargar(self) -> None:
        if not self.ruta.exists():
            return
        lineas = self.ruta.read_text(encoding="utf-8").splitlines()
        for i, linea in enumerate(lineas):
            if not linea.strip():
                continue
            try:
                a = Asiento.de_json(linea)
            except Exception as exc:
                if i == len(lineas) - 1:
                    log.warning("libro: ultima linea truncada ignorada (%s)", exc)
                    return
                raise LibroCorrupto(f"linea {i + 1} ilegible: {exc}") from exc
            esperado = len(self._asientos) + 1
            if a.seq != esperado:
                raise LibroCorrupto(f"seq {a.seq} en linea {i + 1}, esperaba {esperado}")
            self._asientos.append(a)

    def asientos(self) -> list[Asiento]:
        return list(self._asientos)

    def append(self, **campos) -> Asiento:
        a = Asiento(seq=len(self._asientos) + 1, **campos)
        a.validar()
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(a.a_json() + "\n")
            f.flush()
        self._asientos.append(a)
        return a
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_economia_libro.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/libro.py test_economia_libro.py
git commit -m "feat(economia): libro JSONL append-only con carga tolerante a truncado"
```

---

### Task 3: Balances derivados

**Files:**
- Create: `calipso/economia/balances.py`
- Test: `test_economia_libro.py` (agregar tests)

**Interfaces:**
- Consumes: `Asiento`, `TipoAsiento`, `Divisa` de `tipos.py`.
- Produces: funciones puras `saldos(asientos: list[Asiento]) -> dict[tuple[str, Divisa], int]`, `reservas_activas(asientos) -> dict[str, tuple[str, int]]` (ref → (cuenta, monto)), `disponible(asientos, cuenta: str, divisa: Divisa) -> int` (saldo menos reservas activas de esa cuenta en esa divisa).

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_libro.py
from calipso.economia import balances as bal


def _acuna(lb, monto, destino=t.TESORO):
    return lb.append(ts="2026-08-24T09:00:00", semana="2026-W35",
                     tipo=t.TipoAsiento.ACUNACION, divisa=t.Divisa.MONEDA,
                     monto=monto, destino=destino, subtipo="capital",
                     detalle={"evidencia": {"tipo": "firma_pedro"}})


def test_saldos_pliegan_acunacion_transferencia_destruccion(tmp_path):
    lb = _libro(tmp_path)
    _acuna(lb, 1_000_000)
    lb.append(ts="2026-08-24T09:01:00", semana="2026-W35",
              tipo=t.TipoAsiento.TRANSFERENCIA, divisa=t.Divisa.MONEDA,
              monto=300_000, origen=t.TESORO, destino="dep:mercado")
    lb.append(ts="2026-08-24T09:02:00", semana="2026-W35",
              tipo=t.TipoAsiento.DESTRUCCION, divisa=t.Divisa.MONEDA,
              monto=50_000, origen="dep:mercado", detalle={"motivo": "api"})
    s = bal.saldos(lb.asientos())
    assert s[(t.TESORO, t.Divisa.MONEDA)] == 700_000
    assert s[("dep:mercado", t.Divisa.MONEDA)] == 250_000


def test_suma_cero_las_transferencias_no_crean_ni_destruyen(tmp_path):
    """Propiedad del spec 4.1: lo interno mueve, nunca crea."""
    lb = _libro(tmp_path)
    _acuna(lb, 500_000)
    lb.append(ts="2026-08-24T09:01:00", semana="2026-W35",
              tipo=t.TipoAsiento.TRANSFERENCIA, divisa=t.Divisa.MONEDA,
              monto=200_000, origen=t.TESORO, destino="dep:a")
    lb.append(ts="2026-08-24T09:02:00", semana="2026-W35",
              tipo=t.TipoAsiento.TRANSFERENCIA, divisa=t.Divisa.MONEDA,
              monto=80_000, origen="dep:a", destino="dep:b")
    s = bal.saldos(lb.asientos())
    total = sum(v for (cta, div), v in s.items() if div is t.Divisa.MONEDA)
    assert total == 500_000  # exactamente lo acunado


def test_reserva_no_mueve_saldo_pero_baja_disponible(tmp_path):
    lb = _libro(tmp_path)
    _acuna(lb, 100_000, destino="dep:a")
    lb.append(ts="2026-08-24T09:01:00", semana="2026-W35",
              tipo=t.TipoAsiento.RESERVA, divisa=t.Divisa.MONEDA,
              monto=60_000, origen="dep:a", ref="res-1")
    s = bal.saldos(lb.asientos())
    assert s[("dep:a", t.Divisa.MONEDA)] == 100_000
    assert bal.disponible(lb.asientos(), "dep:a", t.Divisa.MONEDA) == 40_000
    assert bal.reservas_activas(lb.asientos()) == {"res-1": ("dep:a", 60_000)}


def test_liberacion_devuelve_disponible(tmp_path):
    lb = _libro(tmp_path)
    _acuna(lb, 100_000, destino="dep:a")
    lb.append(ts="2026-08-24T09:01:00", semana="2026-W35",
              tipo=t.TipoAsiento.RESERVA, divisa=t.Divisa.MONEDA,
              monto=60_000, origen="dep:a", ref="res-1")
    lb.append(ts="2026-08-24T09:02:00", semana="2026-W35",
              tipo=t.TipoAsiento.LIBERACION, divisa=t.Divisa.MONEDA,
              monto=60_000, ref="res-1")
    assert bal.disponible(lb.asientos(), "dep:a", t.Divisa.MONEDA) == 100_000
    assert bal.reservas_activas(lb.asientos()) == {}


def test_ejecucion_de_reserva_transfiere_y_cancela(tmp_path):
    lb = _libro(tmp_path)
    _acuna(lb, 100_000, destino="dep:a")
    lb.append(ts="2026-08-24T09:01:00", semana="2026-W35",
              tipo=t.TipoAsiento.RESERVA, divisa=t.Divisa.MONEDA,
              monto=60_000, origen="dep:a", ref="res-1")
    lb.append(ts="2026-08-24T09:02:00", semana="2026-W35",
              tipo=t.TipoAsiento.EJECUCION_RESERVA, divisa=t.Divisa.MONEDA,
              monto=60_000, origen="dep:a", destino=t.CUENTA_PEDRO, ref="res-1")
    s = bal.saldos(lb.asientos())
    assert s[("dep:a", t.Divisa.MONEDA)] == 40_000
    assert s[(t.CUENTA_PEDRO, t.Divisa.MONEDA)] == 60_000
    assert bal.reservas_activas(lb.asientos()) == {}


def test_apunte_y_acreencia_no_mueven_saldos(tmp_path):
    lb = _libro(tmp_path)
    _acuna(lb, 10_000)
    lb.append(ts="2026-08-24T09:01:00", semana="2026-W35",
              tipo=t.TipoAsiento.APUNTE, divisa=t.Divisa.MONEDA,
              monto=5_000, detalle={"nota": "costo de oportunidad atlas"})
    lb.append(ts="2026-08-24T09:02:00", semana="2026-W35",
              tipo=t.TipoAsiento.ACREENCIA, divisa=t.Divisa.MONEDA,
              monto=3_000, ref="acr-1",
              detalle={"acreedor": t.DIRECCION, "deudor": "dep:a"})
    s = bal.saldos(lb.asientos())
    assert s[(t.TESORO, t.Divisa.MONEDA)] == 10_000
    assert ("dep:a", t.Divisa.MONEDA) not in s
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_economia_libro.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.balances`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/balances.py
"""
calipso/economia/balances.py — Derivacion pura de estado desde el libro.

Ningun balance se guarda: todo se pliega desde los asientos, siempre.
Eso hace los numeros reproducibles (misma historia, mismo numero) y
elimina la clase entera de bugs de "el cache dice otra cosa".
"""
from __future__ import annotations

from collections import defaultdict

from .tipos import Asiento, Divisa, TipoAsiento

_SIN_EFECTO = {TipoAsiento.APUNTE, TipoAsiento.ACREENCIA,
               TipoAsiento.RESERVA, TipoAsiento.LIBERACION}


def saldos(asientos: list[Asiento]) -> dict[tuple[str, Divisa], int]:
    s: dict[tuple[str, Divisa], int] = defaultdict(int)
    for a in asientos:
        if a.tipo in _SIN_EFECTO:
            continue
        if a.origen:
            s[(a.origen, a.divisa)] -= a.monto
        if a.destino:
            s[(a.destino, a.divisa)] += a.monto
    return dict(s)


def reservas_activas(asientos: list[Asiento]) -> dict[str, tuple[str, int]]:
    r: dict[str, tuple[str, int]] = {}
    for a in asientos:
        if a.tipo is TipoAsiento.RESERVA:
            r[a.ref] = (a.origen, a.monto)
        elif a.tipo in (TipoAsiento.LIBERACION, TipoAsiento.EJECUCION_RESERVA):
            r.pop(a.ref, None)
    return r


def disponible(asientos: list[Asiento], cuenta: str, divisa: Divisa) -> int:
    base = saldos(asientos).get((cuenta, divisa), 0)
    if divisa is Divisa.MONEDA:
        base -= sum(m for (cta, m) in reservas_activas(asientos).values()
                    if cta == cuenta)
    return base
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_economia_libro.py -v`
Expected: PASS (15 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/balances.py test_economia_libro.py
git commit -m "feat(economia): balances derivados — saldos, reservas, disponible"
```

---

### Task 4: Kernel — acuñar y destruir

**Files:**
- Create: `calipso/economia/kernel.py`
- Test: `test_economia_kernel.py`

**Interfaces:**
- Consumes: `Libro`, `balances`, tipos.
- Produces: clase `Kernel(libro: Libro)` con `acunar(ts, semana, destino, monto, subtipo: SubtipoAcunacion, evidencia: dict) -> Asiento`, `destruir(ts, semana, origen, monto, motivo: str, ref: str | None = None) -> Asiento`, `saldo(cuenta, divisa=Divisa.MONEDA) -> int`, `disponible(cuenta, divisa=Divisa.MONEDA) -> int`. Excepciones `SinSaldo(Exception)` y `OperacionInvalida(Exception)`.

- [ ] **Step 1: Write the failing tests**

```python
# test_economia_kernel.py
"""Tests del Kernel: operaciones validadas sobre el libro."""
import pytest

from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel, SinSaldo, OperacionInvalida

TS = "2026-08-24T10:00:00"
W = "2026-W35"


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


def _capital(k, monto=1_000_000, destino=t.TESORO):
    return k.acunar(TS, W, destino, monto, t.SubtipoAcunacion.CAPITAL,
                    {"tipo": "firma_pedro"})


def test_acunar_registra_subtipo_y_evidencia(k):
    a = _capital(k)
    assert a.subtipo == "capital"
    assert a.detalle["evidencia"] == {"tipo": "firma_pedro"}
    assert k.saldo(t.TESORO) == 1_000_000


def test_acunar_sin_evidencia_es_invalido(k):
    with pytest.raises(OperacionInvalida):
        k.acunar(TS, W, t.TESORO, 1_000, t.SubtipoAcunacion.VENTA, {})


def test_destruir_valida_disponible(k):
    _capital(k, 10_000)
    k.destruir(TS, W, t.TESORO, 4_000, motivo="renovacion")
    assert k.saldo(t.TESORO) == 6_000
    with pytest.raises(SinSaldo):
        k.destruir(TS, W, t.TESORO, 6_001, motivo="renovacion")


def test_destruir_de_cuenta_vacia_falla(k):
    with pytest.raises(SinSaldo):
        k.destruir(TS, W, "dep:fantasma", 1, motivo="api")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_economia_kernel.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.kernel`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/kernel.py
"""
calipso/economia/kernel.py — Operaciones validadas sobre el libro.

El Kernel es la unica puerta de escritura de la economia: valida
invariantes (sin sobregiro, acunacion con evidencia) antes de apilar
asientos. No conoce departamentos ni politicas: eso vive arriba.
"""
from __future__ import annotations

from . import balances as bal
from .libro import Libro
from .tipos import Asiento, Divisa, SubtipoAcunacion, TipoAsiento


class OperacionInvalida(Exception):
    pass


class SinSaldo(OperacionInvalida):
    pass


class Kernel:
    def __init__(self, libro: Libro):
        self.libro = libro

    # -- consultas ---------------------------------------------------------
    def saldo(self, cuenta: str, divisa: Divisa = Divisa.MONEDA) -> int:
        return bal.saldos(self.libro.asientos()).get((cuenta, divisa), 0)

    def disponible(self, cuenta: str, divisa: Divisa = Divisa.MONEDA) -> int:
        return bal.disponible(self.libro.asientos(), cuenta, divisa)

    def _exigir(self, cuenta: str, monto: int, divisa: Divisa = Divisa.MONEDA):
        disp = self.disponible(cuenta, divisa)
        if monto > disp:
            raise SinSaldo(f"{cuenta}: pide {monto}, disponible {disp}")

    # -- operaciones -------------------------------------------------------
    def acunar(self, ts: str, semana: str, destino: str, monto: int,
               subtipo: SubtipoAcunacion, evidencia: dict) -> Asiento:
        if not evidencia:
            raise OperacionInvalida("acunar exige evidencia (invariante 4)")
        return self.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.ACUNACION,
            divisa=Divisa.MONEDA, monto=monto, destino=destino,
            subtipo=subtipo.value, detalle={"evidencia": evidencia})

    def destruir(self, ts: str, semana: str, origen: str, monto: int,
                 motivo: str, ref: str | None = None) -> Asiento:
        self._exigir(origen, monto)
        return self.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.DESTRUCCION,
            divisa=Divisa.MONEDA, monto=monto, origen=origen, ref=ref,
            detalle={"motivo": motivo})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_economia_kernel.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/kernel.py test_economia_kernel.py
git commit -m "feat(economia): kernel — acunar con evidencia y destruir sin sobregiro"
```

---

### Task 5: Kernel — transferir sin sobregiro

**Files:**
- Modify: `calipso/economia/kernel.py`
- Test: `test_economia_kernel.py` (agregar tests)

**Interfaces:**
- Consumes: lo anterior.
- Produces: `Kernel.transferir(ts, semana, origen, destino, monto, motivo: str, ref: str | None = None, detalle_extra: dict | None = None) -> Asiento`.

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_kernel.py
def test_transferir_mueve_y_valida_disponible(k):
    _capital(k, 100_000)
    k.transferir(TS, W, t.TESORO, "dep:mercado", 40_000, motivo="presupuesto")
    assert k.saldo(t.TESORO) == 60_000
    assert k.saldo("dep:mercado") == 40_000
    with pytest.raises(SinSaldo):
        k.transferir(TS, W, t.TESORO, "dep:mercado", 60_001, motivo="presupuesto")


def test_transferir_respeta_reservas(k):
    """Sin sobregiro es contra DISPONIBLE, no contra saldo (invariante 7)."""
    _capital(k, 100_000, destino="dep:a")
    k.reservar(TS, W, "dep:a", 70_000, ref="res-1")
    with pytest.raises(SinSaldo):
        k.transferir(TS, W, "dep:a", "dep:b", 40_000, motivo="servicio")
    k.transferir(TS, W, "dep:a", "dep:b", 30_000, motivo="servicio")
    assert k.saldo("dep:b") == 30_000
```

(El segundo test usa `reservar`, que llega en la Task 6: escribirlo ya, marcarlo con `@pytest.mark.skip(reason="reservar llega en task 6")` y quitar el skip en la Task 6.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_economia_kernel.py -v`
Expected: FAIL `test_transferir_mueve_y_valida_disponible` con `AttributeError: 'Kernel' object has no attribute 'transferir'`; el otro SKIPPED.

- [ ] **Step 3: Write minimal implementation**

```python
# agregar a calipso/economia/kernel.py, dentro de class Kernel
    def transferir(self, ts: str, semana: str, origen: str, destino: str,
                   monto: int, motivo: str, ref: str | None = None,
                   detalle_extra: dict | None = None) -> Asiento:
        self._exigir(origen, monto)
        detalle = {"motivo": motivo} | (detalle_extra or {})
        return self.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.TRANSFERENCIA,
            divisa=Divisa.MONEDA, monto=monto, origen=origen,
            destino=destino, ref=ref, detalle=detalle)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_economia_kernel.py -v`
Expected: PASS (5 tests, 1 skipped)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/kernel.py test_economia_kernel.py
git commit -m "feat(economia): kernel — transferencias internas sin sobregiro"
```

---

### Task 6: Kernel — escrow (reservar, liberar, ejecutar)

**Files:**
- Modify: `calipso/economia/kernel.py`
- Test: `test_economia_kernel.py` (agregar tests, quitar el skip de la Task 5)

**Interfaces:**
- Consumes: `balances.reservas_activas`.
- Produces: `Kernel.reservar(ts, semana, cuenta, monto, ref: str) -> Asiento`, `Kernel.liberar(ts, semana, ref: str) -> Asiento`, `Kernel.ejecutar_reserva(ts, semana, ref: str, destino: str, detalle_extra: dict | None = None) -> Asiento` (transfiere el monto reservado desde la cuenta reservante y cancela la reserva en un solo asiento `EJECUCION_RESERVA`).

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_kernel.py  (y quitar el @pytest.mark.skip de task 5)
def test_reservar_exige_disponible_y_ref_unica(k):
    _capital(k, 50_000, destino="dep:a")
    k.reservar(TS, W, "dep:a", 30_000, ref="res-1")
    with pytest.raises(SinSaldo):
        k.reservar(TS, W, "dep:a", 30_000, ref="res-2")  # solo quedan 20k
    with pytest.raises(OperacionInvalida):
        k.reservar(TS, W, "dep:a", 1_000, ref="res-1")  # ref repetida


def test_liberar_devuelve_lo_reservado(k):
    _capital(k, 50_000, destino="dep:a")
    k.reservar(TS, W, "dep:a", 30_000, ref="res-1")
    k.liberar(TS, W, ref="res-1")
    assert k.disponible("dep:a") == 50_000
    with pytest.raises(OperacionInvalida):
        k.liberar(TS, W, ref="res-1")  # ya no existe


def test_ejecutar_reserva_paga_a_destino(k):
    """El cobro al servirse una firma (spec 3.2): reserva -> ejecucion."""
    _capital(k, 50_000, destino="dep:a")
    k.reservar(TS, W, "dep:a", 10_000, ref="firma-42")
    k.ejecutar_reserva(TS, W, ref="firma-42", destino=t.CUENTA_PEDRO)
    assert k.saldo(t.CUENTA_PEDRO) == 10_000
    assert k.saldo("dep:a") == 40_000
    assert k.disponible("dep:a") == 40_000
    with pytest.raises(OperacionInvalida):
        k.ejecutar_reserva(TS, W, ref="firma-42", destino=t.CUENTA_PEDRO)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_economia_kernel.py -v`
Expected: FAIL con `AttributeError: ... 'reservar'`

- [ ] **Step 3: Write minimal implementation**

```python
# agregar a calipso/economia/kernel.py, dentro de class Kernel
    def _reserva(self, ref: str) -> tuple[str, int]:
        r = bal.reservas_activas(self.libro.asientos())
        if ref not in r:
            raise OperacionInvalida(f"reserva inexistente o ya cerrada: {ref}")
        return r[ref]

    def reservar(self, ts: str, semana: str, cuenta: str, monto: int,
                 ref: str) -> Asiento:
        if ref in bal.reservas_activas(self.libro.asientos()):
            raise OperacionInvalida(f"ref de reserva repetida: {ref}")
        self._exigir(cuenta, monto)
        return self.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.RESERVA,
            divisa=Divisa.MONEDA, monto=monto, origen=cuenta, ref=ref)

    def liberar(self, ts: str, semana: str, ref: str) -> Asiento:
        cuenta, monto = self._reserva(ref)
        return self.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.LIBERACION,
            divisa=Divisa.MONEDA, monto=monto, ref=ref,
            detalle={"cuenta": cuenta})

    def ejecutar_reserva(self, ts: str, semana: str, ref: str, destino: str,
                         detalle_extra: dict | None = None) -> Asiento:
        cuenta, monto = self._reserva(ref)
        return self.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.EJECUCION_RESERVA,
            divisa=Divisa.MONEDA, monto=monto, origen=cuenta,
            destino=destino, ref=ref, detalle=(detalle_extra or {}))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_economia_kernel.py -v`
Expected: PASS (9 tests, 0 skipped — el skip de task 5 quitado)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/kernel.py test_economia_kernel.py
git commit -m "feat(economia): escrow — reservar, liberar y ejecutar reservas"
```

---

### Task 7: PT — emisión, consumo y expiración

**Files:**
- Create: `calipso/economia/pt.py`
- Test: `test_economia_pt.py`

**Interfaces:**
- Consumes: `Kernel` (y su `libro`), tipos, `balances`.
- Produces: en `pt.py`: `emitir_semana(k: Kernel, ts, semana, cuota_firmable_mpt: int, reserva_personal_mpt: int) -> list[Asiento]` (valida `0 <= reserva <= cuota`, que la semana no esté ya emitida y que los pools estén en cero — cierre previo hecho); `consumir_fabrica(k, ts, semana, monto_mpt, ref: str, pagador: str) -> Asiento`; `consumir_personal(k, ts, semana, monto_mpt, departamento: str, tipo_vigente_mm: int) -> list[Asiento]` (consumo del pool personal + `APUNTE` de costo de oportunidad en milimonedas = `monto_mpt * tipo_vigente_mm // 1000`); `expirar_pools(k, ts, semana) -> list[Asiento]`. Excepción `ErrorPT(Exception)`.

- [ ] **Step 1: Write the failing tests**

```python
# test_economia_pt.py
"""Tests de la divisa PT: emision, consumo, expiracion y tipo de cambio."""
import pytest

from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-24T10:00:00"


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


def test_emitir_semana_parte_fabrica_y_personal(k):
    pt.emitir_semana(k, TS, "2026-W35", cuota_firmable_mpt=5_000,
                     reserva_personal_mpt=2_000)
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 3_000
    assert k.saldo(t.POOL_PT_PERSONAL, t.Divisa.PT) == 2_000


def test_no_se_emite_dos_veces_la_misma_semana(k):
    pt.emitir_semana(k, TS, "2026-W35", 5_000, 0)
    with pytest.raises(pt.ErrorPT):
        pt.emitir_semana(k, TS, "2026-W35", 5_000, 0)


def test_no_se_emite_sobre_pools_sin_cerrar(k):
    """Cierre previo obligatorio: los pools deben estar en cero (spec 3.2)."""
    pt.emitir_semana(k, TS, "2026-W35", 5_000, 0)
    with pytest.raises(pt.ErrorPT):
        pt.emitir_semana(k, TS, "2026-W36", 5_000, 0)


def test_reserva_personal_no_puede_exceder_cuota(k):
    with pytest.raises(pt.ErrorPT):
        pt.emitir_semana(k, TS, "2026-W35", 4_000, 4_001)


def test_consumir_fabrica_valida_pool(k):
    pt.emitir_semana(k, TS, "2026-W35", 4_000, 1_000)
    pt.consumir_fabrica(k, TS, "2026-W35", 500, ref="firma-1", pagador="dep:a")
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 2_500
    with pytest.raises(pt.ErrorPT):
        pt.consumir_fabrica(k, TS, "2026-W35", 2_501, ref="firma-2",
                            pagador="dep:a")


def test_consumir_personal_genera_apunte_de_oportunidad(k):
    pt.emitir_semana(k, TS, "2026-W35", 4_000, 2_000)
    asientos = pt.consumir_personal(k, TS, "2026-W35", 1_500,
                                    departamento="personal:atlas",
                                    tipo_vigente_mm=5_000)
    assert k.saldo(t.POOL_PT_PERSONAL, t.Divisa.PT) == 500
    apunte = asientos[-1]
    assert apunte.tipo is t.TipoAsiento.APUNTE
    assert apunte.monto == 7_500  # 1.5 PT a 5 monedas/PT
    assert apunte.detalle["departamento"] == "personal:atlas"


def test_expirar_deja_pools_en_cero_y_registra(k):
    pt.emitir_semana(k, TS, "2026-W35", 4_000, 1_000)
    pt.consumir_fabrica(k, TS, "2026-W35", 1_000, ref="f-1", pagador="dep:a")
    expirados = pt.expirar_pools(k, TS, "2026-W35")
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 0
    assert k.saldo(t.POOL_PT_PERSONAL, t.Divisa.PT) == 0
    montos = {a.origen: a.monto for a in expirados}
    assert montos == {t.POOL_PT_FABRICA: 2_000, t.POOL_PT_PERSONAL: 1_000}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_economia_pt.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.pt`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/pt.py
"""
calipso/economia/pt.py — La divisa del tiempo de Pedro.

Emision semanal fija (cuota firmable), reserva personal apartada primero,
consumo por firma servida, expiracion al cierre: el tiempo no se acumula.
El tipo de cambio es un pliegue deterministico de la historia (task 8).
"""
from __future__ import annotations

from .kernel import Kernel
from .tipos import (Asiento, Divisa, TipoAsiento,
                    POOL_PT_FABRICA, POOL_PT_PERSONAL)


class ErrorPT(Exception):
    pass


def _ya_emitida(k: Kernel, semana: str) -> bool:
    return any(a.tipo is TipoAsiento.EMISION_PT and a.semana == semana
               for a in k.libro.asientos())


def emitir_semana(k: Kernel, ts: str, semana: str, cuota_firmable_mpt: int,
                  reserva_personal_mpt: int) -> list[Asiento]:
    if not 0 <= reserva_personal_mpt <= cuota_firmable_mpt:
        raise ErrorPT("reserva personal fuera de rango [0, cuota]")
    if _ya_emitida(k, semana):
        raise ErrorPT(f"semana ya emitida: {semana}")
    for pool in (POOL_PT_FABRICA, POOL_PT_PERSONAL):
        if k.saldo(pool, Divisa.PT) != 0:
            raise ErrorPT(f"pool {pool} sin cerrar: expirar antes de emitir")
    out = []
    fabrica = cuota_firmable_mpt - reserva_personal_mpt
    if fabrica:
        out.append(k.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.EMISION_PT,
            divisa=Divisa.PT, monto=fabrica, destino=POOL_PT_FABRICA))
    if reserva_personal_mpt:
        out.append(k.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.EMISION_PT,
            divisa=Divisa.PT, monto=reserva_personal_mpt,
            destino=POOL_PT_PERSONAL))
    return out


def _consumir(k: Kernel, ts: str, semana: str, pool: str, monto_mpt: int,
              ref: str | None, detalle: dict) -> Asiento:
    if monto_mpt > k.saldo(pool, Divisa.PT):
        raise ErrorPT(f"pool {pool}: pide {monto_mpt}, "
                      f"hay {k.saldo(pool, Divisa.PT)}")
    return k.libro.append(
        ts=ts, semana=semana, tipo=TipoAsiento.CONSUMO_PT,
        divisa=Divisa.PT, monto=monto_mpt, origen=pool, ref=ref,
        detalle=detalle)


def consumir_fabrica(k: Kernel, ts: str, semana: str, monto_mpt: int,
                     ref: str, pagador: str) -> Asiento:
    return _consumir(k, ts, semana, POOL_PT_FABRICA, monto_mpt, ref,
                     {"pagador": pagador})


def consumir_personal(k: Kernel, ts: str, semana: str, monto_mpt: int,
                      departamento: str, tipo_vigente_mm: int) -> list[Asiento]:
    consumo = _consumir(k, ts, semana, POOL_PT_PERSONAL, monto_mpt, None,
                        {"departamento": departamento})
    out = [consumo]
    costo = monto_mpt * tipo_vigente_mm // 1000
    if costo > 0:  # un apunte de monto 0 seria un asiento invalido
        out.append(k.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.APUNTE,
            divisa=Divisa.MONEDA, monto=costo,
            detalle={"nota": "costo_oportunidad", "departamento": departamento,
                     "tipo_mm": tipo_vigente_mm}))
    return out


def expirar_pools(k: Kernel, ts: str, semana: str) -> list[Asiento]:
    out = []
    for pool in (POOL_PT_FABRICA, POOL_PT_PERSONAL):
        resto = k.saldo(pool, Divisa.PT)
        if resto:
            out.append(k.libro.append(
                ts=ts, semana=semana, tipo=TipoAsiento.EXPIRACION_PT,
                divisa=Divisa.PT, monto=resto, origen=pool))
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_economia_pt.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/pt.py test_economia_pt.py
git commit -m "feat(economia): PT — emision semanal, reserva personal, consumo, expiracion"
```

---

### Task 8: PT — tipo de cambio determinístico

**Files:**
- Modify: `calipso/economia/pt.py`
- Test: `test_economia_pt.py` (agregar tests)

**Interfaces:**
- Consumes: asientos del libro (`EMISION_PT`, `CONSUMO_PT`, `ACUNACION`).
- Produces: `pt.tipo_de_cambio(asientos: list[Asiento], hasta_semana: str, ventana: int = 8, banda_pct: int = 25, arranque_mm: int = 5000, minimo_mm: int = 1000, min_semanas_consumo: int = 4) -> int` — pliegue determinístico semana a semana. Contrato (spec 3.2): cociente de totales `ventas externas (mm) * 1000 // PT fábrica consumidos (mpt)` sobre la ventana de las últimas `ventana` semanas operativas (semanas con `EMISION_PT`); solo acuñaciones subtipo `venta`; solo consumo del pool fábrica; ventana sin consumo → se mantiene el valor anterior; menos de `min_semanas_consumo` semanas con consumo en la ventana → rige `arranque_mm`; variación por cierre acotada a `±banda_pct%` del valor anterior; piso `minimo_mm`.

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_pt.py
def _venta(k, monto_mm, semana):
    k.acunar(TS, semana, "dep:a", monto_mm, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"})


def _semana_operativa(k, semana, consumo_mpt):
    """Emision estandar de 4 PT fabrica y consumo dado, con cierre."""
    pt.emitir_semana(k, TS, semana, cuota_firmable_mpt=4_000,
                     reserva_personal_mpt=0)
    if consumo_mpt:
        pt.consumir_fabrica(k, TS, semana, consumo_mpt, ref=f"f-{semana}",
                            pagador="dep:a")
    pt.expirar_pools(k, TS, semana)


def test_arranque_rige_hasta_cuatro_semanas_con_consumo(k):
    k.acunar(TS, "2026-W30", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    for i, sem in enumerate(["2026-W30", "2026-W31", "2026-W32"]):
        _semana_operativa(k, sem, 2_000)
    got = pt.tipo_de_cambio(k.libro.asientos(), "2026-W32")
    assert got == 5_000  # solo 3 semanas con consumo: sigue el arranque


def test_capital_no_mueve_el_tipo_de_cambio(k):
    """Spec 3.2 regla (a): inyectar pista no sube el sueldo de Pedro."""
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"]:
        _semana_operativa(k, sem, 2_000)
    k.acunar(TS, "2026-W34", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    got = pt.tipo_de_cambio(k.libro.asientos(), "2026-W34")
    # 5 semanas con consumo y CERO ventas: cociente 0 -> banda y piso mandan
    assert got < 5_000  # bajo desde el arranque, no subio por el capital
    assert got >= 1_000


def test_ventas_suben_el_tipo_dentro_de_la_banda(k):
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]:
        _semana_operativa(k, sem, 2_000)
    _venta(k, 100_000, "2026-W34")  # 100 monedas de venta real
    _semana_operativa(k, "2026-W34", 2_000)
    antes = pt.tipo_de_cambio(k.libro.asientos(), "2026-W33")
    despues = pt.tipo_de_cambio(k.libro.asientos(), "2026-W34")
    assert despues > antes
    assert despues <= antes * 125 // 100  # banda de +25% por cierre


def test_ventana_sin_consumo_mantiene_el_tipo(k):
    """Spec 3.2 regla (c): con la ventana entera sin consumo, el tipo no
    se mueve. (Mientras la ventana todavia contiene semanas con consumo y
    cero ventas, bajar es legitimo: eso no es esta regla.)"""
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"]:
        _semana_operativa(k, sem, 2_000)
    for sem in ["2026-W35", "2026-W36", "2026-W37", "2026-W38", "2026-W39",
                "2026-W40", "2026-W41", "2026-W42", "2026-W43"]:
        _semana_operativa(k, sem, 0)  # nueve semanas sin consumo
    # en W42 y W43 la ventana de 8 ya es toda sin consumo: se mantiene
    a = pt.tipo_de_cambio(k.libro.asientos(), "2026-W42")
    b = pt.tipo_de_cambio(k.libro.asientos(), "2026-W43")
    assert a == b
    assert a >= 1_000  # y nunca por debajo del piso


def test_reproducible_misma_historia_mismo_numero(k):
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"]:
        _venta(k, 20_000, sem)
        _semana_operativa(k, sem, 2_000)
    a = pt.tipo_de_cambio(k.libro.asientos(), "2026-W34")
    b = pt.tipo_de_cambio(list(k.libro.asientos()), "2026-W34")
    assert a == b
    # y reconstruyendo el libro desde disco
    from calipso.economia.libro import Libro
    k2 = Kernel(Libro(k.libro.ruta))
    assert pt.tipo_de_cambio(k2.libro.asientos(), "2026-W34") == a
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_economia_pt.py -v`
Expected: FAIL con `AttributeError: module ... has no attribute 'tipo_de_cambio'`

- [ ] **Step 3: Write minimal implementation**

```python
# agregar a calipso/economia/pt.py
from .tipos import SubtipoAcunacion  # sumar al import de cabecera


def tipo_de_cambio(asientos: list[Asiento], hasta_semana: str,
                   ventana: int = 8, banda_pct: int = 25,
                   arranque_mm: int = 5000, minimo_mm: int = 1000,
                   min_semanas_consumo: int = 4) -> int:
    """Pliegue deterministico del contrato de spec 3.2.

    Cociente de totales sobre las ultimas `ventana` semanas operativas
    (semanas con emision de PT), recalculado en orden semana a semana para
    que la banda encadene igual siempre: misma historia, mismo numero.
    """
    semanas = sorted({a.semana for a in asientos
                      if a.tipo is TipoAsiento.EMISION_PT
                      and a.semana <= hasta_semana})
    ventas_por_semana: dict[str, int] = {}
    consumo_por_semana: dict[str, int] = {}
    for a in asientos:
        if a.semana > hasta_semana:
            continue
        if (a.tipo is TipoAsiento.ACUNACION
                and a.subtipo == SubtipoAcunacion.VENTA.value):
            ventas_por_semana[a.semana] = \
                ventas_por_semana.get(a.semana, 0) + a.monto
        elif (a.tipo is TipoAsiento.CONSUMO_PT
                and a.origen == POOL_PT_FABRICA):
            consumo_por_semana[a.semana] = \
                consumo_por_semana.get(a.semana, 0) + a.monto

    tipo = arranque_mm
    for i, sem in enumerate(semanas):
        vent = semanas[max(0, i + 1 - ventana):i + 1]
        consumo = sum(consumo_por_semana.get(s, 0) for s in vent)
        con_consumo = sum(1 for s in vent if consumo_por_semana.get(s, 0) > 0)
        if consumo == 0:
            pass  # regla (c): se mantiene
        elif con_consumo < min_semanas_consumo:
            tipo = arranque_mm  # regla (d)
        else:
            ventas = sum(ventas_por_semana.get(s, 0) for s in vent)
            objetivo = ventas * 1000 // consumo
            piso_banda = tipo * (100 - banda_pct) // 100
            techo_banda = tipo * (100 + banda_pct) // 100
            tipo = min(max(objetivo, piso_banda), techo_banda)  # regla (e)
        tipo = max(tipo, minimo_mm)  # regla (f)
    return tipo
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_economia_pt.py -v`
Expected: PASS (12 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/pt.py test_economia_pt.py
git commit -m "feat(economia): tipo de cambio del PT — cociente con ventana, banda y bordes"
```

---

### Task 9: Cuenta de Pedro y acreencias

**Files:**
- Create: `calipso/economia/cuenta_pedro.py`
- Modify: `calipso/economia/kernel.py` (acreencias)
- Test: `test_economia_kernel.py` (agregar tests)

**Interfaces:**
- Consumes: `Kernel` completo.
- Produces: en `kernel.py`: `Kernel.registrar_acreencia(ts, semana, acreedor, deudor, monto, ref: str) -> Asiento`, `Kernel.acreencias_pendientes(deudor: str) -> list[tuple[str, str, int]]` (ref, acreedor, pendiente; un pago es una `TRANSFERENCIA` con esa `ref`), `Kernel.liquidar(ts, semana, cuenta: str) -> list[Asiento]` (paga acreencias en orden de `seq`, hasta donde alcanza; el remanente va al `TESORO`). En `cuenta_pedro.py`: `retirar(k, ts, semana, monto) -> Asiento`, `reinyectar(k, ts, semana, monto) -> Asiento`, `financiar_personal(k, ts, semana, departamento: str, monto) -> Asiento` (exige prefijo `personal:`), `rescatar(k, ts, semana, departamento: str, monto, firma: dict) -> Asiento` (exige `firma` no vacía; marca `detalle={"rescate": True, "firma": firma}`).

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_kernel.py
from calipso.economia import cuenta_pedro as cp


def _sueldo(k, monto=50_000):
    """Simula pagos por PT ya cobrados en la cuenta de Pedro."""
    _capital(k, monto, destino=t.CUENTA_PEDRO)


def test_cuatro_salidas_de_la_cuenta_validan_saldo(k):
    _sueldo(k, 50_000)
    cp.retirar(k, TS, W, 10_000)
    cp.reinyectar(k, TS, W, 10_000)
    cp.financiar_personal(k, TS, W, "personal:finanzas", 10_000)
    cp.rescatar(k, TS, W, "dep:mercado", 10_000, firma={"tipo": "firma_pedro"})
    assert k.saldo(t.CUENTA_PEDRO) == 10_000
    with pytest.raises(SinSaldo):
        cp.retirar(k, TS, W, 10_001)


def test_financiar_exige_departamento_personal(k):
    _sueldo(k)
    with pytest.raises(OperacionInvalida):
        cp.financiar_personal(k, TS, W, "dep:mercado", 1_000)


def test_rescate_exige_firma(k):
    _sueldo(k)
    with pytest.raises(OperacionInvalida):
        cp.rescatar(k, TS, W, "dep:mercado", 1_000, firma={})
    a = cp.rescatar(k, TS, W, "dep:mercado", 1_000,
                    firma={"tipo": "firma_pedro"})
    assert a.detalle["rescate"] is True


def test_acreencias_se_liquidan_por_prelacion(k):
    """Spec 4.1/5: en la liquidacion cobran primero los acreedores."""
    _capital(k, 30_000, destino="dep:quebrado")
    k.registrar_acreencia(TS, W, acreedor=t.DIRECCION, deudor="dep:quebrado",
                          monto=20_000, ref="acr-1")
    k.registrar_acreencia(TS, W, acreedor=t.DIRECCION, deudor="dep:quebrado",
                          monto=15_000, ref="acr-2")
    asientos = k.liquidar(TS, W, "dep:quebrado")
    assert k.saldo("dep:quebrado") == 0
    assert k.saldo(t.DIRECCION) == 30_000  # 20k de acr-1 + 10k de acr-2
    assert k.saldo(t.TESORO) == 0  # no sobro nada
    assert k.acreencias_pendientes("dep:quebrado") == \
        [("acr-2", t.DIRECCION, 5_000)]  # lo impago queda visible


def test_liquidar_con_sobrante_devuelve_al_tesoro(k):
    _capital(k, 30_000, destino="dep:quebrado")
    k.registrar_acreencia(TS, W, acreedor=t.DIRECCION, deudor="dep:quebrado",
                          monto=10_000, ref="acr-1")
    k.liquidar(TS, W, "dep:quebrado")
    assert k.saldo(t.DIRECCION) == 10_000
    assert k.saldo(t.TESORO) == 20_000
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_economia_kernel.py -v`
Expected: FAIL con `ImportError` sobre `cuenta_pedro`

- [ ] **Step 3: Write minimal implementation**

```python
# agregar a calipso/economia/kernel.py, dentro de class Kernel
    def registrar_acreencia(self, ts: str, semana: str, acreedor: str,
                            deudor: str, monto: int, ref: str) -> Asiento:
        return self.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.ACREENCIA,
            divisa=Divisa.MONEDA, monto=monto, ref=ref,
            detalle={"acreedor": acreedor, "deudor": deudor})

    def acreencias_pendientes(self, deudor: str) -> list[tuple[str, str, int]]:
        pagos: dict[str, int] = {}
        acre: list[tuple[str, str, int]] = []
        for a in self.libro.asientos():
            if (a.tipo is TipoAsiento.ACREENCIA
                    and a.detalle.get("deudor") == deudor):
                acre.append((a.ref, a.detalle["acreedor"], a.monto))
            elif a.tipo is TipoAsiento.TRANSFERENCIA and a.ref:
                pagos[a.ref] = pagos.get(a.ref, 0) + a.monto
        out = []
        for ref, acreedor, monto in acre:
            pend = monto - pagos.get(ref, 0)
            if pend > 0:
                out.append((ref, acreedor, pend))
        return out

    def liquidar(self, ts: str, semana: str, cuenta: str) -> list[Asiento]:
        out: list[Asiento] = []
        for ref, acreedor, pend in self.acreencias_pendientes(cuenta):
            pago = min(pend, self.disponible(cuenta))
            if pago > 0:
                out.append(self.transferir(ts, semana, cuenta, acreedor,
                                           pago, motivo="liquidacion",
                                           ref=ref))
        resto = self.disponible(cuenta)
        if resto > 0:
            out.append(self.transferir(ts, semana, cuenta, TESORO, resto,
                                       motivo="liquidacion_remanente"))
        return out
```

Sumar `TESORO` al import de `tipos` en `kernel.py`:
`from .tipos import (Asiento, Divisa, SubtipoAcunacion, TipoAsiento, TESORO)`

```python
# calipso/economia/cuenta_pedro.py
"""
calipso/economia/cuenta_pedro.py — Las cuatro salidas de la cuenta de Pedro.

La cuenta vive en el libro general (la escribe solo el kernel); estas
funciones son las UNICAS formas tipadas de sacar plata de ella (spec 3.2).
"""
from __future__ import annotations

from .kernel import Kernel, OperacionInvalida
from .tipos import Asiento, CUENTA_PEDRO, TESORO


def retirar(k: Kernel, ts: str, semana: str, monto: int) -> Asiento:
    return k.destruir(ts, semana, CUENTA_PEDRO, monto, motivo="retiro_pedro")


def reinyectar(k: Kernel, ts: str, semana: str, monto: int) -> Asiento:
    return k.transferir(ts, semana, CUENTA_PEDRO, TESORO, monto,
                        motivo="reinyeccion")


def financiar_personal(k: Kernel, ts: str, semana: str, departamento: str,
                       monto: int) -> Asiento:
    if not departamento.startswith("personal:"):
        raise OperacionInvalida(
            f"solo se financian departamentos personal:* — {departamento!r}")
    return k.transferir(ts, semana, CUENTA_PEDRO, departamento, monto,
                        motivo="financiacion_personal")


def rescatar(k: Kernel, ts: str, semana: str, departamento: str, monto: int,
             firma: dict) -> Asiento:
    if not firma:
        raise OperacionInvalida("rescate exige firma de Pedro")
    return k.transferir(ts, semana, CUENTA_PEDRO, departamento, monto,
                        motivo="rescate",
                        detalle_extra={"rescate": True, "firma": firma})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest test_economia_kernel.py -v`
Expected: PASS (14 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/kernel.py calipso/economia/cuenta_pedro.py test_economia_kernel.py
git commit -m "feat(economia): cuenta de Pedro (4 salidas) y acreencias con prelacion"
```

---

### Task 10: Cierre semanal y exportación del paquete

**Files:**
- Modify: `calipso/economia/pt.py` (cerrar_semana)
- Modify: `calipso/economia/__init__.py` (API pública)
- Test: `test_economia_pt.py` (agregar tests)

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: `pt.cerrar_semana(k: Kernel, ts, semana, refs_reservas_no_servidas: list[str] = ()) -> CierreSemana` con `@dataclass CierreSemana(semana: str, expirado_fabrica_mpt: int, expirado_personal_mpt: int, reservas_liberadas: int, tipo_mm: int)` — libera las reservas de compuertas no servidas, expira los pools y devuelve el tipo de cambio recalculado. `calipso/economia/__init__.py` exporta: `Libro`, `Kernel`, `SinSaldo`, `OperacionInvalida`, `tipos`, `pt`, `cuenta_pedro`, `balances` y `RUTA_LIBRO_DEFECTO = CALIPSO_HOME / "economia" / "libro.jsonl"` (con `CALIPSO_HOME` leído de la variable de entorno como en `costs.py`).

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_pt.py
def test_cierre_semanal_libera_expira_y_recalcula(k):
    k.acunar(TS, "2026-W35", "dep:a", 100_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    pt.emitir_semana(k, TS, "2026-W35", 4_000, 1_000)
    k.reservar(TS, "2026-W35", "dep:a", 10_000, ref="firma-99")  # encolada, no servida
    pt.consumir_fabrica(k, TS, "2026-W35", 500, ref="firma-1", pagador="dep:a")
    cierre = pt.cerrar_semana(k, TS, "2026-W35",
                              refs_reservas_no_servidas=["firma-99"])
    assert cierre.semana == "2026-W35"
    assert cierre.expirado_fabrica_mpt == 2_500
    assert cierre.expirado_personal_mpt == 1_000
    assert cierre.reservas_liberadas == 1
    assert cierre.tipo_mm == 5_000  # sin historia suficiente: arranque
    assert k.disponible("dep:a") == 100_000  # la reserva no servida volvio
    # y la semana siguiente ya puede emitir
    pt.emitir_semana(k, TS, "2026-W36", 4_000, 0)


def test_api_publica_del_paquete():
    import calipso.economia as eco
    assert eco.Kernel and eco.Libro and eco.pt and eco.cuenta_pedro
    assert eco.RUTA_LIBRO_DEFECTO.name == "libro.jsonl"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest test_economia_pt.py -v`
Expected: FAIL con `AttributeError: ... 'cerrar_semana'`

- [ ] **Step 3: Write minimal implementation**

```python
# agregar a calipso/economia/pt.py
from dataclasses import dataclass  # sumar al import de cabecera


@dataclass(frozen=True)
class CierreSemana:
    semana: str
    expirado_fabrica_mpt: int
    expirado_personal_mpt: int
    reservas_liberadas: int
    tipo_mm: int


def cerrar_semana(k: Kernel, ts: str, semana: str,
                  refs_reservas_no_servidas: list[str] = ()) -> CierreSemana:
    liberadas = 0
    for ref in refs_reservas_no_servidas:
        k.liberar(ts, semana, ref)
        liberadas += 1
    expirados = expirar_pools(k, ts, semana)
    por_pool = {a.origen: a.monto for a in expirados}
    return CierreSemana(
        semana=semana,
        expirado_fabrica_mpt=por_pool.get(POOL_PT_FABRICA, 0),
        expirado_personal_mpt=por_pool.get(POOL_PT_PERSONAL, 0),
        reservas_liberadas=liberadas,
        tipo_mm=tipo_de_cambio(k.libro.asientos(), semana))
```

```python
# calipso/economia/__init__.py  (reemplazar contenido)
"""calipso/economia — kernel de la economia de la fabrica (spec 2026-08-24)."""
from __future__ import annotations

import os
import pathlib

from . import balances, cuenta_pedro, pt, tipos          # noqa: F401
from .kernel import Kernel, OperacionInvalida, SinSaldo  # noqa: F401
from .libro import Libro, LibroCorrupto                  # noqa: F401

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
RUTA_LIBRO_DEFECTO = CALIPSO_HOME / "economia" / "libro.jsonl"
```

- [ ] **Step 4: Run full suite to verify everything passes**

Run: `pytest test_economia_libro.py test_economia_kernel.py test_economia_pt.py -v`
Expected: PASS (todos, 0 skipped)

Y verificar que lo existente no se rompió: `pytest test_resource_dispatcher.py -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/pt.py calipso/economia/__init__.py test_economia_pt.py
git commit -m "feat(economia): cierre semanal y API publica del kernel"
```

---

## Qué queda para los planes siguientes (NO implementar acá)

- **Plan 2 — Mercado y departamentos:** suscripciones como capacidad (precio base × escasez, tope API), equivalencias, eficiencia, prorrateo de reserva personal, departamentos (billetera+plantel+perillas), presupuestos y mandato acumulado de dirección, estado congelado y sus prohibiciones (usa `acreencias` y `rescatar` de este plan), criterios de muerte, bus de propuestas, cartas de sistema con presupuesto de PT de dirección.
- **Plan 3 — Frontera y operación:** cola de compuertas de dos carriles (usa `reservar`/`ejecutar_reserva`/`consumir_fabrica`), reloj clock-in (dispara `ejecutar_reserva` + `consumir_fabrica` con tiempo real), departamento personal y libros privados, cuenta pagadora en `dispatch.py`, endpoints en `server.py`, simulación de ciclo completo del spec sección 13.
