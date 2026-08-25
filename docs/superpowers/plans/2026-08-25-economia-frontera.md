# Frontera y Operación (Plan 3 de 3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cerrar el primer corte del spec: la cola de compuertas de dos carriles con cobro al servicio, el reloj clock-in que dispara los cobros con tiempo real, los libros personales y el tablero consolidado, el candado de escritor único, los dos fixes parkeados (liquidación multi-financiador y emisión por pool), el pagador que conecta `dispatch.py` a la economía, los endpoints del server, y la simulación de ciclo completo de spec sección 13.

**Architecture:** Los módulos nuevos del núcleo (`cola.py`, `reloj.py`, `personal.py`, `candado.py`, `operacion.py`, `pagador.py`) siguen las reglas de los Planes 1-2: deterministas (ts/semana como parámetros), estados derivados de archivos append-only, escrituras monetarias solo vía Kernel/Mercado/pt/direccion. La ÚNICA excepción documentada: `operacion.py`, `pagador.py` y los endpoints del server son LA FRONTERA — pueden leer el reloj real del sistema, pero solo para estampar `ts`/`semana` que pasan HACIA el núcleo.

**Tech Stack:** Python 3.14, stdlib (fcntl para el candado). Tests pytest en la raíz, patrón de los planes anteriores; el server se testea con `TestClient(app, cookies={srv.COOKIE: srv.TOKEN})` (patrón documentado del repo).

**Spec:** `docs/superpowers/specs/2026-08-24-cerebro-central-economia-monedas-design.md` (secciones 3.2 cobro al servicio, 9 cola y reloj, 10.1 departamento personal, 11 integración, 13 verificación). Contratos heredados de los Planes 1-2 que este plan DEBE respetar: dueño de trabajos resuelto solo vía `bus.datos` (nunca input de agente); `acunar`/`detalle_extra` jamás passthrough; semana monótona y escritor único; `cerrar_ciclo` con la semana final exacta; `refs_no_servidas` solo con reservas activas.

## Global Constraints

- Todo lo de los Planes 1-2 sigue vigente: stdlib only; montos `int`; español sin emojis; `from __future__ import annotations`; libro append-only; capa de políticas escribe solo vía Kernel/Mercado/pt/direccion.
- **Determinismo del núcleo:** `cola.py`, `reloj.py`, `personal.py`, `candado.py` no leen reloj del sistema ni RNG. `operacion.py`, `pagador.py` y `server.py` son la frontera: estampan `ts` ISO y `semana` reales y los pasan al núcleo.
- **Excepciones por módulo:** `ErrorCola`, `ErrorReloj`, `ErrorPersonal`, `ErrorOperacion` (el pagador degrada a cargo pendiente, nunca revienta el dispatch).
- **Fracción mínima de firma:** 30 minutos = 500 mili-PT; el cobro redondea AL ALZA a múltiplos de 500 mpt (`max(500, ((mpt + 499) // 500) * 500)`).
- **Cobro al servicio (spec 3.2):** al encolar se reserva el estimado al tipo vigente; al servir se LIBERA la reserva y se transfiere el cobro real (tiempo medido, tipo DEL ENCOLADO guardado en el evento, recargo 2x si goteo) + `pt.consumir_fabrica`. Nadie paga horas no trabajadas.
- **Los archivos de eventos nuevos** (`cola.jsonl`, `reloj.jsonl`, `personal.jsonl`, `cargos_pendientes.jsonl`) siguen el patrón del bus: JSONL append-only, estado derivado por replay, flush en cada append.
- Tests: pytest dirigido con `/var/home/pedro/calipso/.venv/bin/python -m pytest ...` — jamás `pytest` a secas. Regresión completa por tarea: los 9 archivos de test existentes más los nuevos.
- `dispatch.py` y `calipso/server.py` son código EXISTENTE: cambios quirúrgicos, siguiendo sus patrones (imports con try/except tolerante, endpoints planos `@app.get/post`, telemetría best-effort). Nada de restructuras.

## File Structure

- Create: `calipso/economia/candado.py` — flock de escritor único (context manager).
- Modify: `calipso/economia/bus.py` — liquidación multi-financiador crash-segura (fix parkeado).
- Modify: `calipso/economia/pt.py` — emisión recuperable por pool (fix parkeado).
- Create: `calipso/economia/cola.py` — compuertas y cartas: encolar/servir/rechazar/atender/expirar, carriles, tope de goteo, registro de atención para el cierre.
- Create: `calipso/economia/reloj.py` — clock in/out por categorías, cobro vía cola, conciliación de huérfanos.
- Create: `calipso/economia/personal.py` — libros personales (ingresos/gastos reales) y tablero consolidado.
- Create: `calipso/economia/operacion.py` — la rutina de frontera: cierre semanal completo con candado, replay de cargos pendientes, `semana_iso()`.
- Create: `calipso/economia/pagador.py` — adaptador de cobro para dispatch (API por tokens, suscripción por unidad, degradación a pendientes).
- Modify: `dispatch.py` — argumento `--cuenta`, captura de usage en `run_api`, cargo best-effort vía pagador.
- Modify: `calipso/server.py` — endpoints `/api/economia/*` (tablero, cola, reloj, cierre).
- Modify: `calipso/economia/__init__.py` — exportar los módulos nuevos.
- Test: `test_economia_frontera.py` (T1-T6), `test_economia_pagador.py` (T7), `test_economia_server.py` (T8), `test_economia_simulacion.py` (T9).

---

### Task 1: Candado de escritor único y fixes parkeados

**Files:**
- Create: `calipso/economia/candado.py`
- Modify: `calipso/economia/bus.py` (liquidación crash-segura)
- Modify: `calipso/economia/pt.py` (emisión recuperable por pool)
- Test: `test_economia_frontera.py`

**Interfaces:**
- Produces: `candado.candado(ruta: Path)` — context manager que toma `flock` exclusivo sobre `<ruta>.lock` (crea el archivo si falta); `ErrorCandado(Exception)` si `no_bloquear=True` y está tomado. En `bus.py`: `evaluar_y_liquidar_muertos` calcula cada devolución contra el SALDO ORIGINAL al morir (saldo actual + ya devuelto, plegando transferencias motivo `liquidacion_trabajo` desde la cuenta trabajo) y descuenta lo ya pagado a cada financiador — un reintento tras crash a mitad de las devoluciones paga solo lo pendiente, con suma exacta. En `pt.py`: `emitir_semana` pasa a recuperación por pool — un pool está pendiente si su monto objetivo es > 0 y no existe EMISION_PT para ese pool y semana; se emiten solo los pendientes; si no hay ninguno pendiente se lanza `ErrorPT` ("semana ya emitida", preserva el contrato existente); la guarda de pools-en-cero aplica por pool pendiente.

- [ ] **Step 1: Write the failing tests**

```python
# test_economia_frontera.py
"""Tests de la frontera: candado, fixes parkeados, cola, reloj, personal, operacion."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import candado as cnd
from calipso.economia import capacidad as cap
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
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA, techo_api_ciclo_mm=500_000))
    r.alta(deps.Departamento("b", deps.ZONA_FABRICA, techo_api_ciclo_mm=500_000))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    m = mkt.Mercado(k, r, SUS)
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    return k, m, b, tmp_path


def _capital(k, monto, destino):
    k.acunar(TS, "2026-W30", destino, monto, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})


def _semana_op(k, semana, cuota=4_000, reserva=0):
    pt.emitir_semana(k, TS, semana, cuota, reserva)


def test_candado_reentrante_y_exclusivo_entre_procesos(tmp_path):
    import subprocess
    import sys
    ruta = tmp_path / "libro.jsonl"
    sonda = ("import fcntl,sys\n"
             "f=open(sys.argv[1],'a')\n"
             "try:\n"
             "    fcntl.flock(f.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
             "    print('LIBRE')\n"
             "except BlockingIOError:\n"
             "    print('TOMADO')\n")
    lock = str(ruta) + ".lock"
    with cnd.candado(ruta):
        with cnd.candado(ruta):  # reentrante: no se bloquea a si mismo
            r = subprocess.run([sys.executable, "-c", sonda, lock],
                               capture_output=True, text=True)
            assert r.stdout.strip() == "TOMADO"  # otro proceso lo ve tomado
    r = subprocess.run([sys.executable, "-c", sonda, lock],
                       capture_output=True, text=True)
    assert r.stdout.strip() == "LIBRE"  # liberado al salir del todo


def test_liquidacion_reanuda_sin_duplicar_pagos(entorno):
    """Fix parkeado del Plan 2: crash entre devoluciones no duplica pagos."""
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    _capital(k, 100_000, "dep:b")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000,
           {"gasto_max_mm": 25_000})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 60_000)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:b", 40_000)
    m.gastar_api(TS, "2026-W30", "trabajo:p1", 30_000, dueno="dep:a")  # muerto
    # simula un crash previo: la parte de dep:a (42_000 de 70_000) YA se pago
    k.transferir(TS, "2026-W30", "trabajo:p1", "dep:a", 42_000,
                 motivo="liquidacion_trabajo")
    muertos = bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W30")
    assert muertos == ["p1"]
    assert k.saldo("trabajo:p1") == 0
    assert k.saldo("dep:a") == 100_000 - 60_000 + 42_000  # sin doble pago
    assert k.saldo("dep:b") == 100_000 - 40_000 + 28_000


def test_emision_se_recupera_por_pool(entorno):
    """Fix parkeado: un crash entre las dos emisiones se completa re-llamando."""
    k, m, b, _ = entorno
    # simula el crash: solo el pool de fabrica quedo emitido (3000 de 4000/1000)
    k.libro.append(ts=TS, semana="2026-W30", tipo=t.TipoAsiento.EMISION_PT,
                   divisa=t.Divisa.PT, monto=3_000, destino=t.POOL_PT_FABRICA)
    emitidos = pt.emitir_semana(k, TS, "2026-W30", 4_000, 1_000)
    assert len(emitidos) == 1 and emitidos[0].destino == t.POOL_PT_PERSONAL
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 3_000
    assert k.saldo(t.POOL_PT_PERSONAL, t.Divisa.PT) == 1_000
    with pytest.raises(pt.ErrorPT):
        pt.emitir_semana(k, TS, "2026-W30", 4_000, 1_000)  # nada pendiente


def test_recuperacion_exige_mismo_split(entorno):
    k, m, b, _ = entorno
    pt.emitir_semana(k, TS, "2026-W30", 4_000, 0)
    with pytest.raises(pt.ErrorPT):
        pt.emitir_semana(k, TS, "2026-W30", 5_000, 1_000)  # otro split
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_frontera.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.candado`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/candado.py
"""
calipso/economia/candado.py — Escritor unico por archivo de libro.

Un flock exclusivo sobre <ruta>.lock protege entre PROCESOS (dispatch y
server escriben el mismo libro); un RLock por ruta protege entre HILOS
del mismo proceso (FastAPI sirve endpoints en threadpool) y hace el
candado REENTRANTE: la operacion puede tomarlo y llamar funciones que
tambien lo toman. Regla de uso: quien escribe toma el candado y
construye su estado (Kernel/Libro/Cola/...) DESPUES de adquirirlo —
nunca cachear escritores entre adquisiciones.
"""
from __future__ import annotations

import contextlib
import fcntl
import pathlib
import threading


class ErrorCandado(Exception):
    pass


_guardia = threading.Lock()
_por_ruta: dict[str, dict] = {}


def _entrada(lock_path: str) -> dict:
    with _guardia:
        if lock_path not in _por_ruta:
            _por_ruta[lock_path] = {"rlock": threading.RLock(),
                                    "fd": None, "profundidad": 0}
        return _por_ruta[lock_path]


@contextlib.contextmanager
def candado(ruta: pathlib.Path, no_bloquear: bool = False):
    lock_path = str(pathlib.Path(str(ruta) + ".lock"))
    ent = _entrada(lock_path)
    if not ent["rlock"].acquire(blocking=not no_bloquear):
        raise ErrorCandado(f"candado tomado por otro hilo: {lock_path}")
    try:
        ent["profundidad"] += 1
        if ent["profundidad"] == 1:
            pathlib.Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
            f = open(lock_path, "a")
            flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if no_bloquear else 0)
            try:
                fcntl.flock(f.fileno(), flags)
            except BlockingIOError:
                f.close()
                ent["profundidad"] -= 1
                raise ErrorCandado(
                    f"candado tomado por otro proceso: {lock_path}") from None
            ent["fd"] = f
        yield
    finally:
        ent["profundidad"] -= 1
        if ent["profundidad"] == 0 and ent["fd"] is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(ent["fd"].fileno(), fcntl.LOCK_UN)
            ent["fd"].close()
            ent["fd"] = None
        ent["rlock"].release()
```

En `calipso/economia/bus.py`, dentro de `evaluar_y_liquidar_muertos`, REEMPLAZAR el bloque de devoluciones (desde `saldo = mercado.k.saldo(cuenta)` hasta el final del loop de financiadores) por:

```python
        asientos = mercado.k.libro.asientos()  # frescos: incluyen el gasto del loop
        aportado = aportes(asientos, id)
        saldo = mercado.k.saldo(cuenta)
        ya_devuelto = {
            fin: sum(a.monto for a in asientos
                     if a.tipo is TipoAsiento.TRANSFERENCIA
                     and a.origen == cuenta and a.destino == fin
                     and a.detalle.get("motivo") == "liquidacion_trabajo")
            for fin in aportado}
        saldo_original = saldo + sum(ya_devuelto.values())
        total = sum(aportado.values())
        financiadores = sorted(aportado)
        # partes teoricas sobre el saldo ORIGINAL (suma exacta: el ultimo cierra)
        partes = {}
        repartido = 0
        for i, fin in enumerate(financiadores):
            if i < len(financiadores) - 1:
                partes[fin] = saldo_original * aportado[fin] // total
            else:
                partes[fin] = saldo_original - repartido
            repartido += partes[fin]
        for fin in financiadores:
            pendiente = partes[fin] - ya_devuelto.get(fin, 0)
            if pendiente > 0:
                mercado.k.transferir(ts, semana, cuenta, fin, pendiente,
                                     motivo="liquidacion_trabajo")
```

(OJO: el rango reemplazado INCLUYE la línea original `aportado = aportes(asientos, id)` — por eso el bloque nuevo la re-define explícitamente al inicio, contra los asientos frescos. No queda ninguna referencia sin definir.)

En `calipso/economia/pt.py`, REEMPLAZAR `_ya_emitida` y la validación de `emitir_semana` por recuperación por pool:

```python
def _pool_emitido(k: Kernel, semana: str, pool: str) -> bool:
    return any(a.tipo is TipoAsiento.EMISION_PT and a.semana == semana
               and a.destino == pool for a in k.libro.asientos())


def emitir_semana(k: Kernel, ts: str, semana: str, cuota_firmable_mpt: int,
                  reserva_personal_mpt: int) -> list[Asiento]:
    if not isinstance(cuota_firmable_mpt, int) or isinstance(cuota_firmable_mpt, bool) \
            or cuota_firmable_mpt <= 0:
        raise ErrorPT("una semana sin horas firmables no se emite: "
                      "cuota_firmable_mpt debe ser > 0")
    if not 0 <= reserva_personal_mpt <= cuota_firmable_mpt:
        raise ErrorPT("reserva personal fuera de rango [0, cuota]")
    # una re-llamada de recuperacion debe usar el MISMO split: si algun pool
    # ya emitido de esta semana declara otra cuota/reserva, es un error del
    # llamador, no una recuperacion
    for a in k.libro.asientos():
        if (a.tipo is TipoAsiento.EMISION_PT and a.semana == semana
                and a.detalle.get("cuota") is not None
                and (a.detalle["cuota"] != cuota_firmable_mpt
                     or a.detalle["reserva"] != reserva_personal_mpt)):
            raise ErrorPT(
                f"emision de {semana} ya iniciada con otro split: "
                f"({a.detalle['cuota']}, {a.detalle['reserva']})")
    objetivos = [(POOL_PT_FABRICA, cuota_firmable_mpt - reserva_personal_mpt),
                 (POOL_PT_PERSONAL, reserva_personal_mpt)]
    pendientes = [(pool, monto) for pool, monto in objetivos
                  if monto > 0 and not _pool_emitido(k, semana, pool)]
    if not pendientes:
        raise ErrorPT(f"semana ya emitida: {semana}")
    out = []
    for pool, monto in pendientes:
        if k.saldo(pool, Divisa.PT) != 0:
            raise ErrorPT(f"pool {pool} sin cerrar: expirar antes de emitir")
        out.append(k.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.EMISION_PT,
            divisa=Divisa.PT, monto=monto, destino=pool,
            detalle={"cuota": cuota_firmable_mpt,
                     "reserva": reserva_personal_mpt}))
    return out
```

(Los asientos EMISION_PT ganan `detalle={"cuota", "reserva"}`; un asiento viejo o plantado sin detalle no participa de la validación de split — por eso el test de recuperación, que planta la emisión parcial a mano sin detalle, pasa. Un segundo llamado con split DISTINTO sobre una emisión nueva lanza ErrorPT: agregar el test `test_recuperacion_exige_mismo_split` — emitir (4_000, 0) completo y llamar (5_000, 1_000) → ErrorPT por split distinto, no "ya emitida".)

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_frontera.py -v` (3 tests PASS). Regresión completa: los 9 archivos existentes siguen verdes (el contrato "ya emitida" y la liquidación de un solo financiador no cambian).

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/candado.py calipso/economia/bus.py calipso/economia/pt.py test_economia_frontera.py
git commit -m "feat(economia): candado de escritor unico; liquidacion y emision crash-seguras"
```

---

### Task 2: La cola — encolar, cartas y registro de atención

**Files:**
- Create: `calipso/economia/cola.py`
- Test: `test_economia_frontera.py` (agregar tests)

**Interfaces:**
- Consumes: `Kernel` (reservar/liberar/transferir), `pt.tipo_de_cambio`, `departamentos.es_congelado`.
- Produces: `ErrorCola(Exception)`; `CARRIL_SESION = "sesion"`, `CARRIL_GOTEO = "goteo"`; `RECARGO_GOTEO_PCT = 200`; `TOPE_GOTEO_SEMANAL = 2`; clase `Cola(ruta: Path)` (JSONL de eventos, patrón del bus) con: `encolar(k, ts, semana, id, departamento, titulo, tipo: str, obligatoria: bool, mpt_estimado: int, monedas_en_juego: int, carril=CARRIL_SESION)` — tipos válidos `{"contacto", "publicacion", "gasto", "opinion"}`; valida id único, mpt_estimado múltiplo de 500 y > 0, carril válido; goteo: cuenta las ENCOLADAS de carril goteo en la semana y rechaza sobre el tope; guarda `tipo_mm = pt.tipo_de_cambio(...)` del momento; reserva escrow `mpt_estimado * tipo_mm // 1000 * (RECARGO_GOTEO_PCT // 100 si goteo)` con `ref=f"cola:{id}"` — si el departamento no tiene disponible: `obligatoria=True` → encola SIN reserva marcando `adelanto=True` (dirección la adelantará al servir, invariante 6), `obligatoria=False` → `ErrorCola` (lo opcional sí se rechaza por precio); `encolar_carta(ts, semana, id, carta: dict)` — cartas del cierre, sin escrow; `pendientes() -> list[dict]` ordenadas por `monedas_en_juego` desc (cartas primero); `estado(id)`; `rechazar(k, ts, semana, id)` (libera reserva si existe); `atender_carta(ts, semana, id, firma: dict | None)` — registra atención; `cartas_atendidas() -> frozenset[str]` (ids de carta atendidos, para `cerrar_ciclo`); `firmas() -> dict[str, dict]`; `expirar_semana(k, ts, semana) -> list[str]` — libera las reservas de compuertas encoladas en ESA semana aún pendientes y las marca expiradas (devuelve ids; las reservas liberadas son el insumo `refs_no_servidas` ya resuelto — `pt.cerrar_semana` recibe entonces `[]`).

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_frontera.py
from calipso.economia import cola as cola_mod


@pytest.fixture
def cola(entorno):
    k, m, b, tmp = entorno
    return cola_mod.Cola(tmp / "cola.jsonl")


def test_encolar_reserva_al_tipo_vigente(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "llamar cliente",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=90_000)
    # 500 mpt a tipo 5000 = 2500 mm reservados
    assert k.disponible("dep:a") == 47_500
    assert cola.estado("c1") == "encolada"
    with pytest.raises(cola_mod.ErrorCola):
        cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "repetida",
                     tipo="contacto", obligatoria=True, mpt_estimado=500,
                     monedas_en_juego=1)


def test_goteo_recarga_y_tiene_tope(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "g1", "dep:a", "urgente 1",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=10_000, carril=cola_mod.CARRIL_GOTEO)
    assert k.disponible("dep:a") == 45_000  # 2500 * 2 de recargo
    cola.encolar(k, TS, "2026-W30", "g2", "dep:a", "urgente 2",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=9_000, carril=cola_mod.CARRIL_GOTEO)
    with pytest.raises(cola_mod.ErrorCola):
        cola.encolar(k, TS, "2026-W30", "g3", "dep:a", "urgente 3",
                     tipo="contacto", obligatoria=True, mpt_estimado=500,
                     monedas_en_juego=8_000, carril=cola_mod.CARRIL_GOTEO)


def test_obligatoria_sin_caja_encola_con_adelanto(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    cola.encolar(k, TS, "2026-W30", "c2", "dep:b", "responder cliente",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=5_000)  # dep:b sin un peso
    p = [x for x in cola.pendientes() if x["id"] == "c2"][0]
    assert p["adelanto"] is True
    with pytest.raises(cola_mod.ErrorCola):
        cola.encolar(k, TS, "2026-W30", "c3", "dep:b", "opinion cara",
                     tipo="opinion", obligatoria=False, mpt_estimado=500,
                     monedas_en_juego=1_000)  # lo opcional si se rechaza


def test_orden_cartas_primero_y_monedas_en_juego(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "chica", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=1_000)
    cola.encolar(k, TS, "2026-W30", "c2", "dep:a", "grande", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=50_000)
    cola.encolar_carta(TS, "2026-W30", "k1", {"tipo": "mandato",
                                              "departamento": "dep:a"})
    orden = [x["id"] for x in cola.pendientes()]
    assert orden == ["k1", "c2", "c1"]


def test_atender_carta_y_registro_para_el_cierre(entorno, cola):
    k, m, b, _ = entorno
    cola.encolar_carta(TS, "2026-W30", "renovacion:claude_max",
                       {"tipo": "renovacion", "suscripcion": "claude_max"})
    cola.atender_carta(TS, "2026-W30", "renovacion:claude_max",
                       firma={"tipo": "firma_pedro"})
    assert "renovacion:claude_max" in cola.cartas_atendidas()
    assert cola.firmas()["renovacion:claude_max"] == {"tipo": "firma_pedro"}


def test_expirar_semana_libera_reservas(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "no atendida",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=1_000)
    expirados = cola.expirar_semana(k, TS, "2026-W30")
    assert expirados == ["c1"]
    assert k.disponible("dep:a") == 50_000
    assert cola.estado("c1") == "expirada"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_frontera.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.cola`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/cola.py
"""
calipso/economia/cola.py — La cola de compuertas (spec 9).

Dos carriles: sesion acumula la semana y se ordena por monedas en juego;
goteo interrumpe con recargo y tope. El escrow se toma al encolar al tipo
vigente y el cobro real ocurre al servir (reloj). Una obligatoria sin
caja no se cae: se encola marcada para adelanto de direccion.
Las cartas del cierre entran sin escrow y su atencion queda registrada
para el cerrar_ciclo (cartas_atendidas / firmas).
"""
from __future__ import annotations

import json
import pathlib

from . import pt
from .kernel import Kernel

CARRIL_SESION = "sesion"
CARRIL_GOTEO = "goteo"
RECARGO_GOTEO_PCT = 200
TOPE_GOTEO_SEMANAL = 2
_TIPOS = {"contacto", "publicacion", "gasto", "opinion"}


class ErrorCola(Exception):
    pass


class Cola:
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

    def _de(self, id: str) -> list[dict]:
        ev = [e for e in self._eventos if e["id"] == id]
        if not ev:
            raise ErrorCola(f"item inexistente: {id}")
        return ev

    def estado(self, id: str) -> str:
        return self._de(id)[-1]["evento"]

    def datos(self, id: str) -> dict:
        return dict(self._de(id)[0])

    # -- encolado ----------------------------------------------------------
    def encolar(self, k: Kernel, ts: str, semana: str, id: str,
                departamento: str, titulo: str, tipo: str, obligatoria: bool,
                mpt_estimado: int, monedas_en_juego: int,
                carril: str = CARRIL_SESION) -> None:
        if any(e["id"] == id for e in self._eventos):
            raise ErrorCola(f"id repetido: {id}")
        if tipo not in _TIPOS:
            raise ErrorCola(f"tipo de compuerta invalido: {tipo!r}")
        if carril not in (CARRIL_SESION, CARRIL_GOTEO):
            raise ErrorCola(f"carril invalido: {carril!r}")
        if (not isinstance(mpt_estimado, int) or isinstance(mpt_estimado, bool)
                or mpt_estimado <= 0 or mpt_estimado % 500 != 0):
            raise ErrorCola(
                f"mpt_estimado debe ser multiplo positivo de 500: {mpt_estimado!r}")
        if carril == CARRIL_GOTEO:
            goteos = sum(1 for e in self._eventos
                         if e["evento"] == "encolada"
                         and e["carril"] == CARRIL_GOTEO
                         and e["semana"] == semana)
            if goteos >= TOPE_GOTEO_SEMANAL:
                raise ErrorCola(
                    f"tope de goteo semanal alcanzado ({TOPE_GOTEO_SEMANAL})")
        asientos = k.libro.asientos()
        tipo_mm = pt.tipo_de_cambio(asientos, semana)
        costo = mpt_estimado * tipo_mm // 1000
        if carril == CARRIL_GOTEO:
            costo = costo * RECARGO_GOTEO_PCT // 100
        congelado = deps.es_congelado(asientos, departamento)
        if congelado and not obligatoria:
            raise ErrorCola(
                f"un congelado no compra firmas opcionales: {departamento}")
        adelanto = False
        if congelado or k.disponible(departamento) < costo:
            if obligatoria:
                adelanto = True  # invariante 6: las obligatorias no se caen
            else:
                raise ErrorCola(
                    f"sin caja para la opcional: pide {costo}, "
                    f"disponible {k.disponible(departamento)}")
        # el evento se apila ANTES de la reserva: un crash entre ambos deja
        # una compuerta sin escrow (servir/expirar lo toleran), nunca una
        # reserva fantasma sin evento que la libere
        self._apilar({"ts": ts, "semana": semana, "evento": "encolada",
                      "id": id, "departamento": departamento,
                      "titulo": titulo, "tipo": tipo,
                      "obligatoria": obligatoria, "carril": carril,
                      "mpt_estimado": mpt_estimado, "tipo_mm": tipo_mm,
                      "monedas_en_juego": monedas_en_juego,
                      "adelanto": adelanto, "es_carta": False})
        if not adelanto:
            k.reservar(ts, semana, departamento, costo, ref=f"cola:{id}")

    def encolar_carta(self, ts: str, semana: str, id: str,
                      carta: dict) -> None:
        if any(e["id"] == id for e in self._eventos):
            return  # las cartas del cierre pueden re-emitirse: idempotente
        self._apilar({"ts": ts, "semana": semana, "evento": "encolada",
                      "id": id, "carta": carta, "es_carta": True,
                      "carril": CARRIL_SESION,
                      "monedas_en_juego": carta.get("monto", 0)})

    # -- lectura -----------------------------------------------------------
    def pendientes(self) -> list[dict]:
        out = []
        for e in self._eventos:
            if e["evento"] == "encolada" and self.estado(e["id"]) == "encolada":
                out.append(dict(e))
        return sorted(out, key=lambda e: (not e.get("es_carta", False),
                                          -e.get("monedas_en_juego", 0)))

    # -- resolucion --------------------------------------------------------
    def _liberar_si_reservada(self, k: Kernel, ts: str, semana: str,
                              id: str) -> None:
        # tolerante: libera solo si la reserva existe de verdad (un crash
        # entre el evento y la reserva, o un reintento, la dejan ausente)
        from . import balances as bal
        if f"cola:{id}" in bal.reservas_activas(k.libro.asientos()):
            k.liberar(ts, semana, ref=f"cola:{id}")

    def rechazar(self, k: Kernel, ts: str, semana: str, id: str) -> None:
        if self.estado(id) != "encolada":
            raise ErrorCola(f"no esta pendiente: {id}")
        self._liberar_si_reservada(k, ts, semana, id)
        self._apilar({"ts": ts, "semana": semana, "evento": "rechazada",
                      "id": id})

    def atender_carta(self, ts: str, semana: str, id: str,
                      firma: dict | None = None) -> None:
        if not self.datos(id).get("es_carta"):
            raise ErrorCola(f"no es una carta: {id}")
        if self.estado(id) != "encolada":
            raise ErrorCola(f"carta ya resuelta: {id}")
        self._apilar({"ts": ts, "semana": semana, "evento": "atendida",
                      "id": id, "firma": firma})

    def cartas_atendidas(self) -> frozenset:
        return frozenset(e["id"] for e in self._eventos
                         if e["evento"] == "atendida")

    def firmas(self) -> dict:
        return {e["id"]: e["firma"] for e in self._eventos
                if e["evento"] == "atendida" and e.get("firma")}

    def expirar_semana(self, k: Kernel, ts: str, semana: str) -> list[str]:
        out = []
        for e in list(self._eventos):
            if (e["evento"] == "encolada" and not e.get("es_carta")
                    and e["semana"] == semana
                    and self.estado(e["id"]) == "encolada"):
                self._liberar_si_reservada(k, ts, semana, e["id"])
                self._apilar({"ts": ts, "semana": semana,
                              "evento": "expirada", "id": e["id"]})
                out.append(e["id"])
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_frontera.py -v` (9 tests PASS)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/cola.py test_economia_frontera.py
git commit -m "feat(economia): cola de compuertas — carriles, escrow, cartas y atencion"
```

---

### Task 3: Servir — el cobro al servicio

**Files:**
- Modify: `calipso/economia/cola.py`
- Test: `test_economia_frontera.py` (agregar tests)

**Interfaces:**
- Consumes: `Kernel` (liberar/transferir/registrar_acreencia/disponible/saldo), `balances.reservas_activas`, `pt.consumir_fabrica`. La cola NO usa `direccion.adelantar_obligatoria`: el adelanto se hace acá con el tipo DEL ENCOLADO y el recargo de goteo incluido (dirección paga el precio completo de la interrupción y la acreencia es por ese total).
- Produces: `Cola.servir(mercado, ts, semana, id, mpt_real: int) -> dict` — UN solo flujo, pre-validado y reanudable: el item debe estar `encolada` y no ser carta; `mpt_cobrado = max(500, ((mpt_real + 499) // 500) * 500)`; `cobro = mpt_cobrado * tipo_mm_del_encolado // 1000` (× recargo si goteo). Se calcula: `ya_pagado` (transferencias previas a CUENTA_PEDRO con `ref=f"cola:{id}"` — reintento tras crash), `pendiente = cobro - ya_pagado`, `disponible_total` (disponible del dep más su reserva activa si existe), `del_dep = min(pendiente, disponible_total)`, `faltante = pendiente - del_dep`. PRE-VALIDACIÓN antes del primer append (patrón `_pagar_pt`): pool de fábrica `>= mpt_cobrado` (salvo que el consumo ya esté hecho de un intento previo) y, si es obligatoria con faltante, `disponible(DIRECCION) >= faltante` (`ErrorCola` limpia si no — nada escrito); una opcional con faltante cobra hasta donde alcanza (`cobro_efectivo = ya_pagado + del_dep`). Escrituras en orden, todas tolerantes a reintento: liberar la reserva (si existe), transferir `del_dep` del dep, transferir `faltante` desde DIRECCION + `registrar_acreencia(DIRECCION, dep, faltante, ref=f"adelanto:{id}")`, `pt.consumir_fabrica(mpt_cobrado, ref=f"cola:{id}", pagador=dep)` (si no está hecho), y al final el evento `servida {id, mpt_real, mpt_cobrado, cobro_mm}`. Devuelve `{"mpt_cobrado", "cobro_mm", "adelantado_mm"}` con los montos REALMENTE movidos.

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_frontera.py
from calipso.economia import direccion as dir_


def test_servir_cobra_tiempo_real_y_libera_reserva(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "llamar", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=9_000)
    # 42 minutos reales -> 700 mpt -> redondeo a 1000 mpt -> 5000 mm
    res = cola.servir(m, TS, "2026-W30", "c1", mpt_real=700)
    assert res["mpt_cobrado"] == 1_000 and res["cobro_mm"] == 5_000
    assert k.saldo(t.CUENTA_PEDRO) == 5_000
    assert k.saldo("dep:a") == 45_000
    assert k.disponible("dep:a") == 45_000  # la reserva de 2500 se libero
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 3_000
    assert cola.estado("c1") == "servida"
    with pytest.raises(cola_mod.ErrorCola):
        cola.servir(m, TS, "2026-W30", "c1", mpt_real=500)  # ya servida


def test_servir_goteo_cobra_recargo(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "g1", "dep:a", "urgente", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=9_000,
                 carril=cola_mod.CARRIL_GOTEO)
    res = cola.servir(m, TS, "2026-W30", "g1", mpt_real=500)
    assert res["cobro_mm"] == 5_000  # 500 mpt a 5000 x2 de recargo
    assert k.saldo(t.CUENTA_PEDRO) == 5_000


def test_servir_con_adelanto_de_direccion(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, t.DIRECCION)
    cola.encolar(k, TS, "2026-W30", "c2", "dep:b", "responder",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=5_000)  # dep:b sin caja -> adelanto
    res = cola.servir(m, TS, "2026-W30", "c2", mpt_real=500)
    assert res["adelantado_mm"] == 2_500
    assert k.saldo(t.CUENTA_PEDRO) == 2_500
    assert k.acreencias_pendientes("dep:b") == \
        [("adelanto:c2", t.DIRECCION, 2_500)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_frontera.py -v`
Expected: FAIL con `AttributeError: ... 'servir'`

- [ ] **Step 3: Write minimal implementation**

```python
# agregar a calipso/economia/cola.py — sumar al bloque de imports del modulo:
from . import balances as bal
from .tipos import CUENTA_PEDRO, DIRECCION, Divisa, POOL_PT_FABRICA, TipoAsiento
# (y quitar el import local de balances dentro de _liberar_si_reservada,
#  que ahora usa el del modulo)


def _redondear_mpt(mpt_real: int) -> int:
    return max(500, ((mpt_real + 499) // 500) * 500)


# dentro de class Cola:
    def servir(self, mercado, ts: str, semana: str, id: str,
               mpt_real: int) -> dict:
        datos = self.datos(id)
        if datos.get("es_carta"):
            raise ErrorCola(f"las cartas se atienden, no se sirven: {id}")
        if self.estado(id) != "encolada":
            raise ErrorCola(f"no esta pendiente: {id}")
        if not isinstance(mpt_real, int) or isinstance(mpt_real, bool) \
                or mpt_real <= 0:
            raise ErrorCola(f"mpt_real debe ser entero positivo: {mpt_real!r}")
        k = mercado.k
        dep = datos["departamento"]
        ref = f"cola:{id}"
        mpt_cobrado = _redondear_mpt(mpt_real)
        cobro = mpt_cobrado * datos["tipo_mm"] // 1000
        if datos["carril"] == CARRIL_GOTEO:
            cobro = cobro * RECARGO_GOTEO_PCT // 100

        # estado real previo (reanudable tras crash a mitad de un intento)
        asientos = k.libro.asientos()
        ya_pagado = sum(a.monto for a in asientos
                        if a.tipo is TipoAsiento.TRANSFERENCIA
                        and a.destino == CUENTA_PEDRO and a.ref == ref)
        consumo_hecho = any(a.tipo is TipoAsiento.CONSUMO_PT and a.ref == ref
                            for a in asientos)
        reservas = bal.reservas_activas(asientos)
        monto_reservado = reservas[ref][1] if ref in reservas else 0
        pendiente = max(0, cobro - ya_pagado)
        disponible_total = k.disponible(dep) + monto_reservado
        del_dep = min(pendiente, disponible_total)
        faltante = pendiente - del_dep

        # PRE-VALIDACION antes del primer append (patron _pagar_pt):
        if not consumo_hecho and \
                k.saldo(POOL_PT_FABRICA, Divisa.PT) < mpt_cobrado:
            raise ErrorCola(
                f"pool de fabrica insuficiente: pide {mpt_cobrado}, "
                f"hay {k.saldo(POOL_PT_FABRICA, Divisa.PT)}")
        if faltante > 0 and datos["obligatoria"]:
            if k.disponible(DIRECCION) < faltante:
                raise ErrorCola(
                    f"direccion sin caja para el adelanto: {faltante}")
        elif faltante > 0:
            faltante = 0  # la opcional cobra hasta donde alcanza

        # escrituras, todas tolerantes a reintento
        self._liberar_si_reservada(k, ts, semana, id)
        if del_dep > 0:
            k.transferir(ts, semana, dep, CUENTA_PEDRO, del_dep,
                         motivo="firma_servida", ref=ref)
        if faltante > 0:
            k.transferir(ts, semana, DIRECCION, CUENTA_PEDRO, faltante,
                         motivo="carta_sistema", ref=ref)
            k.registrar_acreencia(ts, semana, DIRECCION, dep, faltante,
                                  ref=f"adelanto:{id}")
        if not consumo_hecho:
            pt.consumir_fabrica(k, ts, semana, mpt_cobrado, ref=ref,
                                pagador=dep)
        cobro_efectivo = ya_pagado + del_dep + faltante
        self._apilar({"ts": ts, "semana": semana, "evento": "servida",
                      "id": id, "mpt_real": mpt_real,
                      "mpt_cobrado": mpt_cobrado, "cobro_mm": cobro_efectivo})
        return {"mpt_cobrado": mpt_cobrado, "cobro_mm": cobro_efectivo,
                "adelantado_mm": faltante}
```

NOTA para el implementador: no hay rama especial de `adelanto` — una compuerta encolada sin escrow simplemente llega acá con `monto_reservado = 0` y el flujo cubre el faltante desde DIRECCION con su acreencia (invariante 6), con el tipo DEL ENCOLADO y el recargo de goteo incluidos: lo reportado es exactamente lo movido. El tipo de cambio SÍ puede moverse dentro de la semana post-bootstrap (el pliegue incluye el consumo de la semana corriente) — por eso el precio de una firma queda CLAVADO al del encolado, nunca al vigente al servir.

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_frontera.py -v` (12 tests PASS). Regresión completa verde.

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/cola.py test_economia_frontera.py
git commit -m "feat(economia): cobro al servicio — tiempo real, recargo de goteo y adelantos"
```

---

### Task 4: El reloj — clock in/out

**Files:**
- Create: `calipso/economia/reloj.py`
- Test: `test_economia_frontera.py` (agregar tests)

**Interfaces:**
- Consumes: `Cola.servir`, `pt.consumir_personal`, `pt.tipo_de_cambio`.
- Produces: `ErrorReloj(Exception)`; `Reloj(ruta: Path)` (JSONL) con: `clock_in(ts, semana, categoria: str, ref: str | None = None, cola: Cola | None = None)` — categorías `fabrica` (exige `ref` = id de compuerta y VALIDA contra la `cola` — obligatoria como parámetro para fabrica — que exista, no sea carta y esté "encolada": un typo se rechaza al fichar, no al salir), `personal` (exige `ref` = cuenta `personal:<dep>`), `empleo`, `tuning`; rechaza si hay un tramo abierto; `clock_out(mercado, cola, ts, semana) -> dict` — cierra el tramo abierto, `minutos = _minutos(ts_in, ts_out)` (parse ISO, diferencia entera en minutos; `ErrorReloj` si <= 0), `mpt_real = minutos * 1000 // 60`; efectos por categoría: `fabrica` → `cola.servir(...)`; `personal` → `pt.consumir_personal(..., mpt_real directo — la fracción mínima es de las firmas —, tipo_vigente_mm=pt.tipo_de_cambio(...))`; `empleo`/`tuning` → solo el evento. **El cobro que falla no atasca el reloj**: si `cola.servir`/`consumir_personal` lanzan un error de dominio (`ErrorCola`/`ErrorPT` — p. ej. la compuerta expiró entre el in y el out, o la reserva personal se agotó), el tramo se CIERRA igual con el evento `out` anotando `{"sin_cobro": True, "error": str(e)}` y `clock_out` devuelve esa info — el tiempo queda registrado, el cobro no ocurre, y el reloj sigue operable; `abierto() -> dict | None`; `huerfanos(semana_actual: str) -> list[dict]` (el tramo abierto si su semana es anterior a la actual); `conciliar(ts, semana, ts_in, minutos: int)` — cierra un huérfano con duración declarada por Pedro (nunca inventada) SOLO como registro (sin cobro — la compuerta asociada ya expiró en su cierre); `minutos_por_categoria(semanas: list[str]) -> dict[str, int]`.

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_frontera.py
from calipso.economia import reloj as reloj_mod


@pytest.fixture
def reloj(entorno):
    k, m, b, tmp = entorno
    return reloj_mod.Reloj(tmp / "reloj.jsonl")


def test_reloj_fabrica_sirve_la_compuerta(entorno, cola, reloj):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "llamar", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=9_000)
    with pytest.raises(reloj_mod.ErrorReloj):
        reloj.clock_in(TS, "2026-W30", "fabrica", ref="typo", cola=cola)
    reloj.clock_in("2026-08-25T10:00:00", "2026-W30", "fabrica", ref="c1",
                   cola=cola)
    with pytest.raises(reloj_mod.ErrorReloj):
        reloj.clock_in("2026-08-25T10:05:00", "2026-W30", "tuning")  # abierto
    res = reloj.clock_out(m, cola, "2026-08-25T10:42:00", "2026-W30")
    assert res["minutos"] == 42 and res["mpt_real"] == 700
    assert res["sin_cobro"] is False
    assert cola.estado("c1") == "servida"
    assert k.saldo(t.CUENTA_PEDRO) == 5_000  # 1000 mpt redondeados a 5000mm


def test_cobro_fallido_no_atasca_el_reloj(entorno, cola, reloj):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c9", "dep:a", "se expira", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=1_000)
    reloj.clock_in("2026-08-25T10:00:00", "2026-W30", "fabrica", ref="c9",
                   cola=cola)
    cola.expirar_semana(k, TS, "2026-W30")  # el cierre corrio con el tramo abierto
    res = reloj.clock_out(m, cola, "2026-08-25T10:30:00", "2026-W30")
    assert res["sin_cobro"] is True
    assert reloj.abierto() is None  # el reloj sigue operable
    assert k.saldo(t.CUENTA_PEDRO) == 0  # y no se cobro nada


def test_reloj_personal_consume_reserva(entorno, cola, reloj):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30", cuota=4_000, reserva=1_000)
    reloj.clock_in("2026-08-25T09:00:00", "2026-W30", "personal",
                   ref="personal:finanzas")
    res = reloj.clock_out(m, cola, "2026-08-25T09:30:00", "2026-W30")
    assert res["mpt_real"] == 500
    assert k.saldo(t.POOL_PT_PERSONAL, t.Divisa.PT) == 500


def test_reloj_empleo_solo_registra(entorno, cola, reloj):
    k, m, b, _ = entorno
    reloj.clock_in("2026-08-25T08:00:00", "2026-W30", "empleo")
    reloj.clock_out(m, cola, "2026-08-25T16:00:00", "2026-W30")
    assert reloj.minutos_por_categoria(["2026-W30"]) == {"empleo": 480}


def test_huerfano_se_concilia_sin_inventar(entorno, cola, reloj):
    k, m, b, _ = entorno
    reloj.clock_in("2026-08-25T08:00:00", "2026-W30", "tuning")
    assert reloj.abierto() is not None
    huerfanos = reloj.huerfanos("2026-W31")
    assert len(huerfanos) == 1
    reloj.conciliar(TS, "2026-W31", huerfanos[0]["ts"], minutos=60)
    assert reloj.abierto() is None
    assert reloj.minutos_por_categoria(["2026-W30"]) == {"tuning": 60}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_frontera.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.reloj`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/reloj.py
"""
calipso/economia/reloj.py — La frontera de entrada del tiempo (spec 9).

El clock-out es el evento que dispara el cobro: fabrica sirve la compuerta
con el tiempo real medido, personal consume la reserva de PT, empleo y
tuning solo registran. Un tramo huerfano jamas inventa duracion: se
concilia con minutos declarados por Pedro y sin cobro.
Determinista: los ts son parametros; los minutos salen de restar ISO.
"""
from __future__ import annotations

import datetime
import json
import pathlib

from . import pt
from .cola import Cola, ErrorCola

CATEGORIAS = {"fabrica", "personal", "empleo", "tuning"}


class ErrorReloj(Exception):
    pass


def _minutos(ts_in: str, ts_out: str) -> int:
    a = datetime.datetime.fromisoformat(ts_in)
    b = datetime.datetime.fromisoformat(ts_out)
    return int((b - a).total_seconds()) // 60


class Reloj:
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

    def abierto(self) -> dict | None:
        abiertos = [e for e in self._eventos if e["evento"] == "in"]
        cerrados = {e["ts_in"] for e in self._eventos
                    if e["evento"] in ("out", "conciliado")}
        pend = [e for e in abiertos if e["ts"] not in cerrados]
        return dict(pend[-1]) if pend else None

    def clock_in(self, ts: str, semana: str, categoria: str,
                 ref: str | None = None, cola: Cola | None = None) -> None:
        if categoria not in CATEGORIAS:
            raise ErrorReloj(f"categoria invalida: {categoria!r}")
        if categoria == "fabrica":
            if not ref or cola is None:
                raise ErrorReloj(
                    "fabrica exige ref (id de compuerta) y la cola para validarlo")
            try:
                datos = cola.datos(ref)
            except ErrorCola:
                raise ErrorReloj(f"compuerta inexistente: {ref}") from None
            if datos.get("es_carta") or cola.estado(ref) != "encolada":
                raise ErrorReloj(f"la compuerta no esta pendiente: {ref}")
        if categoria == "personal" and not (ref or "").startswith("personal:"):
            raise ErrorReloj("personal exige ref personal:<departamento>")
        if self.abierto():
            raise ErrorReloj("ya hay un tramo abierto: clock_out primero")
        self._apilar({"ts": ts, "semana": semana, "evento": "in",
                      "categoria": categoria, "ref": ref})

    def clock_out(self, mercado, cola: Cola, ts: str, semana: str) -> dict:
        tramo = self.abierto()
        if not tramo:
            raise ErrorReloj("no hay tramo abierto")
        minutos = _minutos(tramo["ts"], ts)
        if minutos <= 0:
            raise ErrorReloj(f"duracion invalida: {minutos} minutos")
        mpt_real = minutos * 1000 // 60
        categoria = tramo["categoria"]
        error_cobro = None
        try:
            if categoria == "fabrica":
                cola.servir(mercado, ts, semana, tramo["ref"], mpt_real)
            elif categoria == "personal":
                tipo = pt.tipo_de_cambio(mercado.k.libro.asientos(), semana)
                pt.consumir_personal(mercado.k, ts, semana, mpt_real,
                                     departamento=tramo["ref"],
                                     tipo_vigente_mm=tipo)
        except (ErrorCola, pt.ErrorPT) as exc:
            # el tiempo queda registrado; el cobro fallido no atasca el reloj
            error_cobro = str(exc)
        evento = {"ts": ts, "semana": semana, "evento": "out",
                  "ts_in": tramo["ts"], "categoria": categoria,
                  "minutos": minutos}
        if error_cobro:
            evento["sin_cobro"] = True
            evento["error"] = error_cobro
        self._apilar(evento)
        return {"minutos": minutos, "mpt_real": mpt_real,
                "categoria": categoria, "sin_cobro": bool(error_cobro)}

    def huerfanos(self, semana_actual: str) -> list[dict]:
        tramo = self.abierto()
        if tramo and tramo["semana"] < semana_actual:
            return [dict(tramo)]
        return []

    def conciliar(self, ts: str, semana: str, ts_in: str,
                  minutos: int) -> None:
        if not isinstance(minutos, int) or isinstance(minutos, bool) \
                or minutos <= 0:
            raise ErrorReloj(f"minutos debe ser entero positivo: {minutos!r}")
        tramo = self.abierto()
        if not tramo or tramo["ts"] != ts_in:
            raise ErrorReloj(f"no hay tramo abierto con ts {ts_in}")
        self._apilar({"ts": ts, "semana": semana, "evento": "conciliado",
                      "ts_in": ts_in, "categoria": tramo["categoria"],
                      "minutos": minutos})

    def minutos_por_categoria(self, semanas: list[str]) -> dict[str, int]:
        out: dict[str, int] = {}
        ins = {e["ts"]: e for e in self._eventos if e["evento"] == "in"}
        for e in self._eventos:
            if e["evento"] in ("out", "conciliado"):
                origen = ins.get(e["ts_in"])
                if origen and origen["semana"] in semanas:
                    cat = e["categoria"]
                    out[cat] = out.get(cat, 0) + e["minutos"]
        return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_frontera.py -v` (16 tests PASS)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/reloj.py test_economia_frontera.py
git commit -m "feat(economia): reloj clock-in — el tiempo real dispara los cobros"
```

---

### Task 5: Libros personales y tablero consolidado

**Files:**
- Create: `calipso/economia/personal.py`
- Test: `test_economia_frontera.py` (agregar tests)

**Interfaces:**
- Produces: `ErrorPersonal(Exception)`; `SUELDO_MENSUAL_MM = 2_500_000`; `LibroPersonal(ruta: Path)` (JSONL privado, spec inv. 11) con `registrar(ts, semana, tipo: "ingreso"|"gasto", monto_mm: int, categoria: str, nota: str = "")` (montos int > 0) y `resumen(semanas: list[str] | None = None) -> dict` (`{"ingresos_mm", "gastos_mm", "neto_mm"}`); `linea_empleo_mm_por_hora(sueldo_mm: int, minutos_empleo: int) -> int` — con minutos reales `sueldo_mm * 60 // minutos`, sin datos (`minutos <= 0`) la teórica `sueldo_mm // 173`; `tablero(kernel, registro, suscripciones, reloj, libro_personal, semana) -> dict` — la vista consolidada (solo LECTURA, spec 10.1): `{"tesoro_mm", "cuenta_pedro_mm", "tipo_cambio_mm", "linea_empleo_mm", "departamentos": {cuenta: {"saldo_mm", "congelado"}}, "reserva_personal_usada": {sus: unidades}, "costo_oportunidad_mm" (suma de apuntes), "personal": resumen}`.

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_frontera.py
from calipso.economia import personal as per_mod


def test_libro_personal_registra_y_resume(entorno):
    k, m, b, tmp = entorno
    lp = per_mod.LibroPersonal(tmp / "personal.jsonl")
    lp.registrar(TS, "2026-W30", "ingreso", 2_500_000, "sueldo")
    lp.registrar(TS, "2026-W30", "gasto", 400_000, "suscripciones")
    lp.registrar(TS, "2026-W31", "gasto", 100_000, "comida")
    assert lp.resumen(["2026-W30"]) == {"ingresos_mm": 2_500_000,
                                        "gastos_mm": 400_000,
                                        "neto_mm": 2_100_000}
    assert lp.resumen()["neto_mm"] == 2_000_000
    with pytest.raises(per_mod.ErrorPersonal):
        lp.registrar(TS, "2026-W30", "prestamo", 1, "x")


def test_linea_empleo_medida_y_teorica():
    # 160 horas reales en el mes: 2.5M/160h = 15_625 mm/h
    assert per_mod.linea_empleo_mm_por_hora(2_500_000, 160 * 60) == 15_625
    assert per_mod.linea_empleo_mm_por_hora(2_500_000, 0) == 14_450  # /173


def test_tablero_consolida(entorno, reloj):
    k, m, b, tmp = entorno
    lp = per_mod.LibroPersonal(tmp / "personal.jsonl")
    _semana_op(k, "2026-W30", cuota=4_000, reserva=1_000)
    _capital(k, 1_200_000, t.TESORO)
    _capital(k, 5_000, t.CUENTA_PEDRO)
    tab = per_mod.tablero(k, m.registro, SUS, reloj, lp, "2026-W30")
    assert tab["tesoro_mm"] == 1_200_000
    assert tab["cuenta_pedro_mm"] == 5_000
    assert tab["tipo_cambio_mm"] == 5_000
    assert tab["departamentos"]["dep:a"] == {"saldo_mm": 0,
                                             "congelado": False}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_frontera.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.personal`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/personal.py
"""
calipso/economia/personal.py — Los libros personales y el tablero.

Los libros personales son PRIVADOS (invariante 11): finanzas del mundo
real de Pedro, en su propio JSONL, fuera del libro de la fabrica. El
tablero es un LECTOR que consolida — jamas escribe.
"""
from __future__ import annotations

import json
import pathlib

from . import capacidad as cap
from . import departamentos as deps
from . import pt
from .kernel import Kernel
from .tipos import CUENTA_PEDRO, TESORO, TipoAsiento

SUELDO_MENSUAL_MM = 2_500_000


class ErrorPersonal(Exception):
    pass


class LibroPersonal:
    def __init__(self, ruta: pathlib.Path):
        self.ruta = pathlib.Path(ruta)
        self._eventos: list[dict] = []
        if self.ruta.exists():
            for linea in self.ruta.read_text(encoding="utf-8").splitlines():
                if linea.strip():
                    self._eventos.append(json.loads(linea))

    def registrar(self, ts: str, semana: str, tipo: str, monto_mm: int,
                  categoria: str, nota: str = "") -> None:
        if tipo not in ("ingreso", "gasto"):
            raise ErrorPersonal(f"tipo invalido: {tipo!r}")
        if not isinstance(monto_mm, int) or isinstance(monto_mm, bool) \
                or monto_mm <= 0:
            raise ErrorPersonal(f"monto_mm debe ser entero positivo: {monto_mm!r}")
        evento = {"ts": ts, "semana": semana, "tipo": tipo,
                  "monto_mm": monto_mm, "categoria": categoria, "nota": nota}
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False,
                               separators=(",", ":")) + "\n")
            f.flush()
        self._eventos.append(evento)

    def resumen(self, semanas: list[str] | None = None) -> dict:
        ing = gas = 0
        for e in self._eventos:
            if semanas is not None and e["semana"] not in semanas:
                continue
            if e["tipo"] == "ingreso":
                ing += e["monto_mm"]
            else:
                gas += e["monto_mm"]
        return {"ingresos_mm": ing, "gastos_mm": gas, "neto_mm": ing - gas}


def linea_empleo_mm_por_hora(sueldo_mm: int, minutos_empleo: int) -> int:
    if minutos_empleo <= 0:
        return sueldo_mm // 173  # teorica: ~40 h/semana
    return sueldo_mm * 60 // minutos_empleo


def tablero(k: Kernel, registro: deps.Registro, suscripciones: dict,
            reloj, libro_personal: LibroPersonal, semana: str) -> dict:
    asientos = k.libro.asientos()
    ops = cap.semanas_operativas(asientos)
    minutos = reloj.minutos_por_categoria(ops[-4:]) if ops else {}
    reserva_usada = {nombre: cap.consumo_personal(asientos, nombre, ops[-4:])
                     for nombre in suscripciones} if ops else {}
    costo_op = sum(a.monto for a in asientos
                   if a.tipo is TipoAsiento.APUNTE
                   and a.detalle.get("nota") == "costo_oportunidad")
    return {
        "tesoro_mm": k.saldo(TESORO),
        "cuenta_pedro_mm": k.saldo(CUENTA_PEDRO),
        "tipo_cambio_mm": pt.tipo_de_cambio(asientos, semana) if ops else 5_000,
        "linea_empleo_mm": linea_empleo_mm_por_hora(
            SUELDO_MENSUAL_MM, minutos.get("empleo", 0)),
        "departamentos": {
            d.cuenta: {"saldo_mm": k.saldo(d.cuenta),
                       "congelado": deps.es_congelado(asientos, d.cuenta)}
            for d in registro.todos()},
        "reserva_personal_usada": reserva_usada,
        "costo_oportunidad_mm": costo_op,
        "personal": libro_personal.resumen(),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_frontera.py -v` (19 tests PASS)

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/personal.py test_economia_frontera.py
git commit -m "feat(economia): libros personales privados y tablero consolidado"
```

---

### Task 6: Operación — la rutina de frontera

**Files:**
- Create: `calipso/economia/operacion.py`
- Modify: `calipso/economia/__init__.py` (exportar módulos nuevos)
- Test: `test_economia_frontera.py` (agregar tests)

**Interfaces:**
- Produces: `ErrorOperacion(Exception)`; `semana_iso(fecha: str) -> str`; `abrir_semana(k, ts, semana, cuota, reserva)` = `pt.emitir_semana` bajo candado; `cerrar_semana_operativa(mercado, bus, cola, ts, semana, presupuesto_direccion_mm=0) -> dict` — LA rutina, bajo `candado(mercado.k.libro.ruta)` (reentrante: las funciones internas pueden re-tomarlo): (1) `cola.expirar_semana` (libera reservas → `refs_no_servidas=[]` para pt); (2) `cierre.cerrar_semana_economia(...)` — si la semana no es operativa, `ErrorOperacion` limpia (envuelve `ErrorCapacidad`); (3) las cartas del cierre → `cola.encolar_carta` con id `f"{tipo}:{quien}:{semana}"`; (4) si la semana cierra ciclo (fracción 100): las cartas de renovación llevan el CICLO en el id (`f"renovacion:{sus}:{ciclo}"`) para que el breaker se rearme cada ciclo y la carta se re-presente en cada ciclo rojo; la atención y las firmas de la cola se TRADUCEN a las claves que `cerrar_ciclo` espera — `cartas_atendidas = {f"renovacion:{sus}" ...}` solo de los ids del ciclo CORRIENTE, y `firmas = {sus: firma}` idem; los informes con `requiere_firma` o `rojo` → `cola.encolar_carta`. Devuelve `{"cierre": CierreEconomia, "informes_ciclo": list, "expiradas": list}`. Nota determinismo: `semana_iso` es función pura; los llamadores de frontera estampan la fecha real.

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_economia_frontera.py
from calipso.economia import operacion as op_mod


def test_semana_iso():
    assert op_mod.semana_iso("2026-08-25") == "2026-W35"
    assert op_mod.semana_iso("2026-01-01") == "2026-W01"


def test_cerrar_semana_operativa_orquesta_todo(entorno, cola):
    k, m, b, _ = entorno
    m.registro.ajustar("a", presupuesto_semanal_mm=10_000)
    _capital(k, 1_200_000, t.TESORO)
    op_mod.abrir_semana(k, TS, "2026-W30", 4_000, 0)
    _capital(k, 20_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "sin atender",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=1_000)
    res = op_mod.cerrar_semana_operativa(m, b, cola, TS, "2026-W30")
    assert res["expiradas"] == ["c1"]
    assert cola.estado("c1") == "expirada"
    assert k.saldo("dep:a") == 30_000  # presupuesto asignado
    assert res["informes_ciclo"] == []  # fraccion 25, no cierra ciclo
    # la emision de W30 expiro en el cierre de pt
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 0


def test_ciclo_completo_encola_carta_de_renovacion(entorno, cola):
    k, m, b, _ = entorno
    _capital(k, 1_200_000, t.TESORO)
    semanas = ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]
    for sem in semanas:
        op_mod.abrir_semana(k, TS, sem, 4_000, 0)
        res = op_mod.cerrar_semana_operativa(m, b, cola, TS, sem)
    # W33 cierra el ciclo 0: sin recaudacion -> rojo 1, renueva automatico
    assert len(res["informes_ciclo"]) == 1
    assert res["informes_ciclo"][0]["renovada"] is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_frontera.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.operacion`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/operacion.py
"""
calipso/economia/operacion.py — La rutina de frontera.

Abrir la semana (emitir PT) y cerrarla (expirar cola, cierre economico,
cartas a la cola, ciclo mensual con la atencion registrada) — todo bajo
el candado de escritor unico. Este modulo ES la frontera: sus llamadores
estampan fechas reales; el nucleo recibe ts y semana como datos.
"""
from __future__ import annotations

import datetime

from . import bus as bus_mod
from . import capacidad as cap
from . import cierre
from . import cola as cola_mod
from . import pt
from .candado import candado
from .capacidad import ErrorCapacidad
from .kernel import Kernel
from .mercado import Mercado


class ErrorOperacion(Exception):
    pass


def semana_iso(fecha: str) -> str:
    d = datetime.date.fromisoformat(fecha)
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def abrir_semana(k: Kernel, ts: str, semana: str, cuota_firmable_mpt: int,
                 reserva_personal_mpt: int):
    with candado(k.libro.ruta):
        return pt.emitir_semana(k, ts, semana, cuota_firmable_mpt,
                                reserva_personal_mpt)


def _id_carta(carta: dict, semana: str) -> str:
    quien = carta.get("departamento") or carta.get("suscripcion") or "general"
    return f"{carta['tipo']}:{quien}:{semana}"


def cerrar_semana_operativa(mercado: Mercado, bus: bus_mod.Bus,
                            cola: cola_mod.Cola, ts: str, semana: str,
                            presupuesto_direccion_mm: int = 0) -> dict:
    k = mercado.k
    with candado(k.libro.ruta):
        try:
            ops = cap.semanas_operativas(k.libro.asientos())
            ciclo, fraccion = cap.posicion_ciclo(semana, ops)
        except ErrorCapacidad as exc:
            raise ErrorOperacion(
                f"la semana no esta abierta (emitir primero): {exc}") from exc
        expiradas = cola.expirar_semana(k, ts, semana)
        res = cierre.cerrar_semana_economia(
            mercado, bus, ts, semana, refs_no_servidas=[],
            presupuesto_direccion_mm=presupuesto_direccion_mm)
        for carta in res.cartas:
            cola.encolar_carta(ts, semana, _id_carta(carta, semana), carta)
        informes = []
        if fraccion == 100:
            # traduccion cola -> cierre: solo la atencion del ciclo CORRIENTE
            # desarma el breaker, y las firmas se indexan por suscripcion
            sufijo = f":{ciclo}"
            atendidas = frozenset(
                "renovacion:" + id.split(":")[1]
                for id in cola.cartas_atendidas()
                if id.startswith("renovacion:") and id.endswith(sufijo))
            firmas = {id.split(":")[1]: f for id, f in cola.firmas().items()
                      if id.startswith("renovacion:") and id.endswith(sufijo)}
            informes = cierre.cerrar_ciclo(mercado, ts, semana,
                                           cartas_atendidas=atendidas,
                                           firmas=firmas)
            for inf in informes:
                if inf["requiere_firma"] or inf["rojo"]:
                    cola.encolar_carta(
                        ts, semana,
                        f"renovacion:{inf['suscripcion']}:{ciclo}",
                        {"tipo": "renovacion", **inf})
        return {"cierre": res, "informes_ciclo": informes,
                "expiradas": expiradas}
```

En `calipso/economia/__init__.py`, sumar al bloque de imports existente:

```python
from . import candado, cola, operacion, pagador, personal, reloj  # noqa: F401
```

(NOTA: `pagador` se crea en la Task 7 — en esta tarea importar solo `candado, cola, operacion, personal, reloj` y la Task 7 suma `pagador`.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_frontera.py -v` (22 tests PASS). Regresión completa verde.

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/operacion.py calipso/economia/__init__.py test_economia_frontera.py
git commit -m "feat(economia): operacion — abrir y cerrar la semana bajo candado"
```

---

### Task 7: El pagador y el cableado de dispatch.py

**Files:**
- Create: `calipso/economia/pagador.py`
- Modify: `dispatch.py` (argumento `--cuenta`, usage en `run_api`, cargo best-effort)
- Test: `test_economia_pagador.py`

**Interfaces:**
- Produces: `PRECIOS_API_MM_POR_MTOK = {"deepseek-chat": (270, 1100)}` (mm por millón de tokens entrada/salida; desconocido → `(3000, 15000)` conservador); `Pagador` — **sin estado cacheado**: guarda solo las RUTAS de `<base|~/.calipso>/economia/`; cada operación de cobro toma `candado(libro)` y construye un `Mercado` FRESCO dentro del lock (contrato de escritor único: dispatch y el server pueden cobrar el mismo libro sin corromper la cadena de seq). `desde_entorno(base=None) -> Pagador | None` (si falta `libro.jsonl`, `departamentos.json` o `suscripciones.json`, la economía no está activa → `None`); `leer_kernel() -> Kernel` (lector fresco, para consultas y tests); `cargar_api(ts, semana, cuenta, modelo, prompt_tokens, completion_tokens) -> int | None` — mm = ceil((pt·in + ct·out)/1M); cuenta `personal*` → `None` sin cargo (el uso personal de API queda fuera del libro — lo lleva `costs.py`); `cargar_suscripcion(ts, semana, cuenta, suscripcion, unidades=1)` — `personal` → `usar_reserva_personal(..., "personal:finanzas")`, resto → `comprar_capacidad`; **cuentas `trabajo:<id>`**: el dueño se resuelve DENTRO de `_aplicar` vía `Bus(eco/"bus.jsonl").datos(id)["departamento"]` y se pasa como `dueno=` — sin bus o sin propuesta, el cargo degrada a pendiente (nunca un pendiente eterno estructural: el reintento re-resuelve); **degradación**: excepciones económicas (`ErrorMercado`/`ErrorCapacidad`/`ErrorBus`/`OperacionInvalida` incl. `SinSaldo`) → el cargo va a `cargos_pendientes.jsonl` (escrito bajo el mismo candado) con aviso a stderr; `pendientes() -> list[dict]`; `reintentar_pendientes() -> int` — bajo candado, re-aplica cargo por cargo REESCRIBIENDO el archivo tras CADA aplicado (un crash a mitad no duplica cobros) y las excepciones no-económicas (cargo malformado) se conservan con aviso en vez de abortar. En `dispatch.py`: (1) argparse gana `--cuenta` (default `"personal"`); (2) `run_api` gana parámetro `usage: dict | None = None` — en stream pasa `usage` a `_sse_text_chunks` y agrega `"stream_options": {"include_usage": True}` al payload; en no-stream copia `data.get("usage", {})`; (3) en `main`, tras ejecutar la ruta, un bloque best-effort (patrón del archivo: try/except ancho) llama `pagador` si `Pagador.desde_entorno()` no es `None`: ruta `api` → `cargar_api(...)` con el usage capturado; ruta `subscription` → `cargar_suscripcion(cuenta, "claude_max" si client claude, "chatgpt_plus" si codex)`; ruta `local` → nada; `ts`/`semana` estampados con `datetime.datetime.now().isoformat(timespec="seconds")` y `operacion.semana_iso(date.today().isoformat())` (dispatch ES frontera).

- [ ] **Step 1: Write the failing tests**

```python
# test_economia_pagador.py
"""Tests del pagador: el adaptador entre dispatch y la economia."""
import json
import pytest

from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import pagador as pag
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"
W = "2026-W35"


@pytest.fixture
def base(tmp_path):
    eco = tmp_path / "economia"
    eco.mkdir()
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("mercadeo", deps.ZONA_FABRICA,
                             techo_api_ciclo_mm=500_000))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    k.acunar(TS, W, "dep:mercadeo", 100_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    return tmp_path


def test_desde_entorno_inactivo_sin_archivos(tmp_path):
    assert pag.Pagador.desde_entorno(tmp_path) is None


def test_cargar_api_por_tokens(base):
    p = pag.Pagador.desde_entorno(base)
    mm = p.cargar_api(TS, W, "dep:mercadeo", "deepseek-chat",
                      prompt_tokens=100_000, completion_tokens=50_000)
    assert mm == 82  # ceil((100k*270 + 50k*1100) / 1M)
    assert p.leer_kernel().saldo("dep:mercadeo") == 100_000 - 82


def test_cargar_api_de_trabajo_resuelve_dueno(base):
    from calipso.economia import bus as bus_mod
    b = bus_mod.Bus(base / "economia" / "bus.jsonl")
    b.alta(TS, W, "p1", "dep:mercadeo", "radar", 10_000, 20_000,
           {"gasto_max_mm": 50_000})
    Kernel(Libro(base / "economia" / "libro.jsonl")).transferir(
        TS, W, "dep:mercadeo", "trabajo:p1", 1_000, motivo="financiacion")
    p = pag.Pagador.desde_entorno(base)
    p.cargar_api(TS, W, "trabajo:p1", "deepseek-chat", 1_000_000, 0)  # 270 mm
    assert p.pendientes() == []
    assert p.leer_kernel().saldo("trabajo:p1") == 1_000 - 270


def test_cuenta_personal_no_carga_api(base):
    p = pag.Pagador.desde_entorno(base)
    assert p.cargar_api(TS, W, "personal", "deepseek-chat", 1000, 1000) is None
    assert p.leer_kernel().saldo("dep:mercadeo") == 100_000


def test_cargar_suscripcion_por_unidad(base):
    p = pag.Pagador.desde_entorno(base)
    p.cargar_suscripcion(TS, W, "dep:mercadeo", "claude_max")
    # 1 unidad a precio base 100
    assert p.leer_kernel().saldo(t.DIRECCION) == 100
    p.cargar_suscripcion(TS, W, "personal", "claude_max")
    asientos = p.leer_kernel().libro.asientos()
    assert cap.consumo_personal(asientos, "claude_max", [W]) == 1


def test_fallo_economico_degrada_a_pendiente(base):
    p = pag.Pagador.desde_entorno(base)
    # semana no operativa: el cargo no puede aplicarse -> pendiente
    p.cargar_suscripcion(TS, "2026-W99", "dep:mercadeo", "claude_max")
    assert len(p.pendientes()) == 1
    assert p.leer_kernel().saldo(t.DIRECCION) == 0
    # el reintento re-aplica con la semana ORIGINAL del cargo, que sigue
    # sin ser operativa: queda pendiente
    assert p.reintentar_pendientes() == 0
    assert len(p.pendientes()) == 1


def test_reintento_aplica_cuando_puede(base):
    p = pag.Pagador.desde_entorno(base)
    # techo agotado -> pendiente; al reintentar con techo ampliado, pasa
    registro = deps.Registro(base / "economia" / "departamentos.json")
    registro.ajustar("mercadeo", techo_api_ciclo_mm=10)
    p.cargar_api(TS, W, "dep:mercadeo", "deepseek-chat", 100_000, 50_000)
    assert len(p.pendientes()) == 1
    registro.ajustar("mercadeo", techo_api_ciclo_mm=500_000)
    assert p.reintentar_pendientes() == 1  # el mercado fresco ve el ajuste
    assert p.pendientes() == []
    assert p.leer_kernel().saldo("dep:mercadeo") == 100_000 - 82
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_pagador.py -v`
Expected: FAIL con `ImportError` sobre `calipso.economia.pagador`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/economia/pagador.py
"""
calipso/economia/pagador.py — El adaptador de cobro para dispatch.

Todo request lleva cuenta pagadora (spec 11). El pagador convierte uso
real (tokens de API, requests de suscripcion) en asientos via Mercado.
Nunca rompe el flujo del dispatch: un cargo que no puede aplicarse queda
en cargos_pendientes.jsonl y se reintenta desde la operacion.
El uso personal de API queda fuera del libro de la fabrica (lo lleva
calipso/costs.py); la cuenta personal de suscripcion va contra la
reserva personal. Este modulo es FRONTERA: sus llamadores estampan
ts/semana reales.
"""
from __future__ import annotations

import json
import pathlib
import sys

from . import departamentos as deps
from .bus import Bus, ErrorBus
from .candado import candado
from .capacidad import ErrorCapacidad, Suscripcion
from .kernel import Kernel, OperacionInvalida
from .libro import Libro
from .mercado import ErrorMercado, Mercado

PRECIOS_API_MM_POR_MTOK = {"deepseek-chat": (270, 1100)}
PRECIO_DESCONOCIDO = (3000, 15000)  # conservador

_ERRORES_ECONOMICOS = (ErrorMercado, ErrorCapacidad, ErrorBus,
                       OperacionInvalida)


class Pagador:
    """Sin estado cacheado: solo rutas. Cada cobro toma el candado y
    construye un Mercado fresco adentro — escritor unico de verdad."""

    def __init__(self, eco: pathlib.Path):
        self.eco = pathlib.Path(eco)
        self.ruta_libro = self.eco / "libro.jsonl"
        self.ruta_registro = self.eco / "departamentos.json"
        self.ruta_sus = self.eco / "suscripciones.json"
        self.ruta_bus = self.eco / "bus.jsonl"
        self.ruta_pendientes = self.eco / "cargos_pendientes.jsonl"

    @staticmethod
    def desde_entorno(base: pathlib.Path | None = None) -> "Pagador | None":
        raiz = pathlib.Path(base) if base else \
            pathlib.Path(pathlib.Path.home() / ".calipso")
        p = Pagador(raiz / "economia")
        if not (p.ruta_libro.exists() and p.ruta_registro.exists()
                and p.ruta_sus.exists()):
            return None
        return p

    # -- construccion fresca (llamar BAJO candado para escribir) -----------
    def mercado_fresco(self) -> Mercado:
        datos = json.loads(self.ruta_sus.read_text(encoding="utf-8"))
        suscripciones = {n: Suscripcion(**c) for n, c in datos.items()}
        return Mercado(Kernel(Libro(self.ruta_libro)),
                       deps.Registro(self.ruta_registro), suscripciones)

    def leer_kernel(self) -> Kernel:
        return Kernel(Libro(self.ruta_libro))

    # -- pendientes --------------------------------------------------------
    def _reescribir_pendientes(self, cargos: list[dict]) -> None:
        contenido = "".join(json.dumps(c, ensure_ascii=False,
                                       separators=(",", ":")) + "\n"
                            for c in cargos)
        self.ruta_pendientes.parent.mkdir(parents=True, exist_ok=True)
        self.ruta_pendientes.write_text(contenido, encoding="utf-8")

    def _apilar_pendiente(self, cargo: dict) -> None:
        self._reescribir_pendientes(self.pendientes() + [cargo])
        print(f"[pagador] cargo pendiente: {cargo.get('tipo')} "
              f"{cargo.get('cuenta')}", file=sys.stderr)

    def pendientes(self) -> list[dict]:
        if not self.ruta_pendientes.exists():
            return []
        return [json.loads(l) for l in
                self.ruta_pendientes.read_text(encoding="utf-8").splitlines()
                if l.strip()]

    def reintentar_pendientes(self) -> int:
        aplicados = 0
        with candado(self.ruta_libro):
            quedan = self.pendientes()
            i = 0
            while i < len(quedan):
                try:
                    self._aplicar(quedan[i])
                except _ERRORES_ECONOMICOS:
                    i += 1
                    continue
                except Exception as exc:  # cargo malformado: conservar
                    print(f"[pagador] cargo ilegible: {exc}", file=sys.stderr)
                    i += 1
                    continue
                del quedan[i]
                self._reescribir_pendientes(quedan)  # tras CADA aplicado
                aplicados += 1
        return aplicados

    # -- cargos ------------------------------------------------------------
    def _dueno_de(self, cuenta: str) -> str:
        if not self.ruta_bus.exists():
            raise ErrorBus(f"sin bus para resolver el dueno de {cuenta}")
        id_trabajo = cuenta.split(":", 1)[1]
        return Bus(self.ruta_bus).datos(id_trabajo)["departamento"]

    def _aplicar(self, cargo: dict) -> None:
        m = self.mercado_fresco()  # relee el libro bajo el candado
        cuenta = cargo["cuenta"]
        dueno = self._dueno_de(cuenta) if cuenta.startswith("trabajo:") else None
        if cargo["tipo"] == "api":
            m.gastar_api(cargo["ts"], cargo["semana"], cuenta, cargo["mm"],
                         dueno=dueno)
        elif cuenta == "personal":
            m.usar_reserva_personal(cargo["ts"], cargo["semana"],
                                    cargo["suscripcion"], cargo["unidades"],
                                    "personal:finanzas")
        else:
            m.comprar_capacidad(cargo["ts"], cargo["semana"], cuenta,
                                cargo["suscripcion"], cargo["unidades"],
                                dueno=dueno)

    def _cobrar(self, cargo: dict) -> None:
        with candado(self.ruta_libro):
            try:
                self._aplicar(cargo)
            except _ERRORES_ECONOMICOS:
                self._apilar_pendiente(cargo)

    def cargar_api(self, ts: str, semana: str, cuenta: str, modelo: str,
                   prompt_tokens: int, completion_tokens: int) -> int | None:
        if cuenta == "personal" or cuenta.startswith("personal:"):
            return None  # fuera del libro de la fabrica (costs.py lo lleva)
        pin, pout = PRECIOS_API_MM_POR_MTOK.get(modelo, PRECIO_DESCONOCIDO)
        mm = -(-(prompt_tokens * pin + completion_tokens * pout) // 1_000_000)
        self._cobrar({"ts": ts, "semana": semana, "tipo": "api",
                      "cuenta": cuenta, "mm": mm, "modelo": modelo})
        return mm

    def cargar_suscripcion(self, ts: str, semana: str, cuenta: str,
                           suscripcion: str, unidades: int = 1) -> None:
        self._cobrar({"ts": ts, "semana": semana, "tipo": "suscripcion",
                      "cuenta": cuenta, "suscripcion": suscripcion,
                      "unidades": unidades})
```

En `dispatch.py` (cambios quirúrgicos, siguiendo los patrones del archivo):

1. Junto a los imports tolerantes existentes:
```python
try:
    from calipso.economia.pagador import Pagador as _Pagador
    from calipso.economia.operacion import semana_iso as _semana_iso
except Exception:
    _Pagador = None
    _semana_iso = None
```
2. En el argparse de `main`: `parser.add_argument("--cuenta", default="personal", help="cuenta pagadora de la economia (dep:<x>, trabajo:<id>, personal)")`.
3. `run_api` gana `usage: dict | None = None`: en la rama stream, `payload["stream_options"] = {"include_usage": True}` y pasar `usage` a `_sse_text_chunks(cfg["base_url"], payload, headers, usage)`; en la rama no-stream, tras obtener `data`, si `usage is not None: usage.update(data.get("usage") or {})`.
4. En `main`, la ejecución de rutas HOY termina en returns directos (`return run_subscription(...)` / `return run_api(...)` / `return run_local(...)`) — el bloque de cobro necesita una reestructura mínima y explícita: capturar el código de retorno, cobrar, devolver. Patrón exacto (adaptando los nombres reales de las variables de `main`, que el implementador lee antes de tocar):
```python
    usage: dict = {}
    if ruta == "api":
        rc = run_api(prompt, stream, usage=usage)
    elif ruta == "subscription":
        rc = run_subscription(prompt, cliente, cwd=...)
    else:  # local — OJO: run_local REAL redirige a run_subscription
        rc = run_local(prompt, stream)

    # Cargo economico best-effort (nunca rompe el flujo, patron log_decision)
    try:
        if _Pagador and _semana_iso:
            pagador = _Pagador.desde_entorno()
            if pagador:
                ahora = datetime.datetime.now()
                ts_eco = ahora.isoformat(timespec="seconds")
                sem = _semana_iso(ahora.date().isoformat())
                if ruta == "api":
                    pagador.cargar_api(ts_eco, sem, args.cuenta,
                                       CONFIG["api"]["model"],
                                       usage.get("prompt_tokens", 0),
                                       usage.get("completion_tokens", 0))
                else:
                    # subscription Y local: run_local redirige a la
                    # suscripcion, asi que tambien consume una unidad
                    sus = "claude_max" if cliente == "claude" else "chatgpt_plus"
                    pagador.cargar_suscripcion(ts_eco, sem, args.cuenta, sus)
    except Exception:
        pass  # telemetria economica best-effort

    return rc
```
(Para la ruta local, `cliente` es el `subscription_client` de la config al que `run_local` redirige — el mismo default que usa `run_local` internamente.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_pagador.py -v` (6 tests PASS). Verificación de dispatch: `/var/home/pedro/calipso/.venv/bin/python dispatch.py --dry-run "resume este texto"` sigue funcionando (sin economía activa → no-op). Regresión completa verde.

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/pagador.py calipso/economia/__init__.py dispatch.py test_economia_pagador.py
git commit -m "feat(economia): pagador — dispatch cobra por cuenta pagadora con degradacion"
```

---

### Task 8: Endpoints del server

**Files:**
- Modify: `calipso/server.py`
- Test: `test_economia_server.py`

**Interfaces:**
- Produces: en `server.py`, tras los endpoints existentes, una sección `# --- ECONOMIA ---`. **Nada de singletons ni cache**: cada request construye el estado FRESCO desde los archivos (`Pagador.desde_entorno(_ECO_BASE)` más `Cola/Reloj/Bus/LibroPersonal` nuevos sobre `_ECO_BASE/"economia"`), y TODO endpoint que escribe toma `candado(ruta del libro)` alrededor de construir+operar — es el contrato de escritor único: dispatch (otro proceso) y el server (threadpool de FastAPI) comparten el libro sin corromper la cadena de seq; el candado reentrante permite que `cerrar_semana_operativa` lo re-tome adentro. Los endpoints de lectura construyen fresco sin candado. Si la economía no está activa → `{"activa": False}`. Endpoints (detrás del `auth_guard` existente, funciones planas): `GET /api/economia/tablero`; `GET /api/economia/cola`; `POST /api/economia/cola/{id}/atender` (body `{"firma"}`) y `.../rechazar`; `POST /api/economia/reloj/in` (body `{"categoria", "ref"}`) y `.../out`; `POST /api/economia/cierre` (→ `cerrar_semana_operativa` + `abrir_semana` de la siguiente NO: solo el cierre + `reintentar_pendientes()`); ts/semana estampados con el reloj real (el server ES frontera). Modelos pydantic mínimos patrón `SaveBody`. Las excepciones de dominio suben como 500 visibles (aceptable para el primer corte).

- [ ] **Step 1: Write the failing tests**

```python
# test_economia_server.py
"""Tests de los endpoints de economia (patron TestClient + cookie del repo)."""
import json
import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    # economia activa en un HOME temporal
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    k.acunar("2026-08-25T09:00:00", "2026-W35", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    # sin cache: cada request reconstruye desde los archivos
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_tablero_responde(cliente):
    r = cliente.get("/api/economia/tablero")
    assert r.status_code == 200
    body = r.json()
    assert body["activa"] is True
    assert body["tablero"]["tesoro_mm"] == 1_200_000


def test_cola_atender_carta(cliente):
    # sembrar una carta via los modulos (el server comparte la carpeta)
    r = cliente.get("/api/economia/cola")
    assert r.json()["pendientes"] == []


def test_sin_auth_rechaza(tmp_path):
    c = TestClient(srv.app)
    assert c.get("/api/economia/tablero",
                 follow_redirects=False).status_code in (302, 401, 403)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_server.py -v`
Expected: FAIL (404 en los endpoints nuevos / AttributeError `_ECO_BASE`)

- [ ] **Step 3: Write minimal implementation**

Agregar a `calipso/server.py` (al final, antes del arranque, siguiendo el estilo del archivo):

```python
# --------------------------------------------------------------------------
# ECONOMIA (spec 2026-08-24): tablero, cola, reloj y cierre
# --------------------------------------------------------------------------
try:
    from calipso.economia import (bus as _eco_bus, cola as _eco_cola,
                                  operacion as _eco_op,
                                  personal as _eco_personal,
                                  reloj as _eco_reloj)
    from calipso.economia.candado import candado as _eco_candado
    from calipso.economia.pagador import Pagador as _EcoPagador
except Exception:  # economia no disponible: los endpoints responden inactivo
    _EcoPagador = None

_ECO_BASE = pathlib.Path(os.path.expanduser("~/.calipso"))


def _economia():
    """Estado FRESCO por request: el estado vive en los archivos, no en el
    proceso — asi dispatch (otro proceso) y este server no se pisan. Los
    endpoints que ESCRIBEN envuelven esta construccion en el candado."""
    if _EcoPagador is None:
        return None
    pagador = _EcoPagador.desde_entorno(_ECO_BASE)
    if pagador is None:
        return None
    eco = _ECO_BASE / "economia"
    return {
        "pagador": pagador,
        "cola": _eco_cola.Cola(eco / "cola.jsonl"),
        "reloj": _eco_reloj.Reloj(eco / "reloj.jsonl"),
        "bus": _eco_bus.Bus(eco / "bus.jsonl"),
        "personal": _eco_personal.LibroPersonal(eco / "personal.jsonl"),
    }


def _eco_ahora() -> tuple[str, str]:
    ahora = _dt.datetime.now()
    return (ahora.isoformat(timespec="seconds"),
            _eco_op.semana_iso(ahora.date().isoformat()))


class EcoAtenderBody(BaseModel):
    firma: dict | None = None


class EcoRelojInBody(BaseModel):
    categoria: str
    ref: str | None = None


@app.get("/api/economia/tablero")
def api_eco_tablero() -> dict:
    eco = _economia()
    if not eco:
        return {"activa": False}
    m = eco["pagador"].mercado_fresco()  # lector fresco, sin candado
    _, semana = _eco_ahora()
    tab = _eco_personal.tablero(m.k, m.registro, m.suscripciones,
                                eco["reloj"], eco["personal"], semana)
    return {"activa": True, "tablero": tab}


@app.get("/api/economia/cola")
def api_eco_cola() -> dict:
    eco = _economia()
    if not eco:
        return {"activa": False}
    return {"activa": True, "pendientes": eco["cola"].pendientes()}


@app.post("/api/economia/cola/{item_id}/atender")
def api_eco_atender(item_id: str, body: EcoAtenderBody) -> dict:
    eco = _economia()
    if not eco:
        return {"activa": False}
    ts, semana = _eco_ahora()
    # atender solo toca cola.jsonl, pero mantiene la disciplina de candado
    with _eco_candado(eco["pagador"].ruta_libro):
        eco["cola"].atender_carta(ts, semana, item_id, firma=body.firma)
    return {"ok": True}


@app.post("/api/economia/cola/{item_id}/rechazar")
def api_eco_rechazar(item_id: str) -> dict:
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    ts, semana = _eco_ahora()
    with _eco_candado(p0.ruta_libro):
        eco = _economia()  # fresco BAJO el candado: ve el libro actual
        eco["cola"].rechazar(eco["pagador"].mercado_fresco().k, ts, semana,
                             item_id)
    return {"ok": True}


@app.post("/api/economia/reloj/in")
def api_eco_reloj_in(body: EcoRelojInBody) -> dict:
    eco = _economia()
    if not eco:
        return {"activa": False}
    ts, semana = _eco_ahora()
    eco["reloj"].clock_in(ts, semana, body.categoria, ref=body.ref,
                          cola=eco["cola"])
    return {"ok": True}


@app.post("/api/economia/reloj/out")
def api_eco_reloj_out() -> dict:
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    ts, semana = _eco_ahora()
    with _eco_candado(p0.ruta_libro):
        eco = _economia()  # fresco BAJO el candado
        res = eco["reloj"].clock_out(eco["pagador"].mercado_fresco(),
                                     eco["cola"], ts, semana)
    return {"ok": True, **res}


@app.post("/api/economia/cierre")
def api_eco_cierre() -> dict:
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    ts, semana = _eco_ahora()
    with _eco_candado(p0.ruta_libro):
        eco = _economia()  # fresco BAJO el candado (reentrante adentro)
        res = _eco_op.cerrar_semana_operativa(
            eco["pagador"].mercado_fresco(), eco["bus"], eco["cola"],
            ts, semana)
        aplicados = eco["pagador"].reintentar_pendientes()
    return {"ok": True, "expiradas": res["expiradas"],
            "informes_ciclo": res["informes_ciclo"],
            "pendientes_aplicados": aplicados}
```

(El implementador verifica los imports reales del archivo: `pathlib`, `os`, `BaseModel` ya existen; agregar `import datetime as _dt` si el archivo no lo tiene con ese alias. Las excepciones de dominio de la economía se dejan subir: FastAPI las convierte en 500, que para el primer corte operado por Pedro es aceptable y visible.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_server.py -v` (3 tests PASS). Regresión completa verde (incluye `test_resource_dispatcher.py` y todo lo de economía).

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py test_economia_server.py
git commit -m "feat(economia): endpoints del server — tablero, cola, reloj y cierre"
```

---

### Task 9: La simulación de ciclo completo (spec 13)

**Files:**
- Create: `test_economia_simulacion.py`

**Interfaces:**
- Consumes: todo el paquete. Es UN test integrador largo (más asserts de invariantes), sin reloj real: semanas y ts sintéticos.

- [ ] **Step 1: Write the simulation test (es el deliverable — no hay RED clásico: debe pasar contra lo ya construido; si falla, el bug está en el paquete y se reporta, no se ajusta el assert)**

```python
# test_economia_simulacion.py
"""Simulacion de ciclo completo (spec 13): la economia entera, sin manos.

Cuatro semanas operativas con dos departamentos que compiten, una
propuesta financiada que gasta y muere, compuertas servidas por el reloj,
una venta real confirmada que mueve el tipo de cambio, una quiebra con
intento de rescate colusivo (debe fallar) y rescate firmado (debe pasar),
y el cierre de ciclo con renovacion — verificando al final las
invariantes globales del libro.
"""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import cola as cola_mod
from calipso.economia import cuenta_pedro as cp
from calipso.economia import departamentos as deps
from calipso.economia import mercado as mkt
from calipso.economia import operacion as op
from calipso.economia import pt
from calipso.economia import reloj as reloj_mod
from calipso.economia import tipos as t
from calipso.economia.balances import saldos
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"
SUS = {"claude_max": cap.Suscripcion("claude_max", 100_000, 1_000, 200, 500)}


def test_simulacion_ciclo_completo(tmp_path):
    k = Kernel(Libro(tmp_path / "libro.jsonl"))
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("mercado", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=50_000,
                             techo_api_ciclo_mm=100_000))
    r.alta(deps.Departamento("curiosos", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=20_000,
                             techo_api_ciclo_mm=50_000))
    m = mkt.Mercado(k, r, SUS)
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    cola = cola_mod.Cola(tmp_path / "cola.jsonl")
    reloj = reloj_mod.Reloj(tmp_path / "reloj.jsonl")

    # --- arranque: la pista del spec 4.4
    k.acunar(TS, "2026-W30", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})

    # --- W30: abrir, presupuestos, propuesta financiada, compuerta servida
    op.abrir_semana(k, TS, "2026-W30", 4_000, 500)
    op.cerrar_semana_operativa(m, b, cola, TS, "2026-W30")
    assert k.saldo("dep:mercado") == 50_000
    assert k.saldo("dep:curiosos") == 20_000

    op.abrir_semana(k, TS, "2026-W31", 4_000, 500)
    b.alta(TS, "2026-W31", "radar", "dep:mercado", "radar vertical",
           60_000, 200_000, {"gasto_max_mm": 20_000})
    bus_mod.financiar(m, b, TS, "2026-W31", "radar", "dep:mercado", 30_000)
    m.gastar_api(TS, "2026-W31", "trabajo:radar", 10_000, dueno="dep:mercado")
    cola.encolar(k, TS, "2026-W31", "entrega", "dep:mercado",
                 "entregar radar al cliente", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=150_000)
    reloj.clock_in("2026-08-26T10:00:00", "2026-W31", "fabrica",
                   ref="entrega", cola=cola)
    reloj.clock_out(m, cola, "2026-08-26T10:25:00", "2026-W31")
    assert cola.estado("entrega") == "servida"
    assert k.saldo(t.CUENTA_PEDRO) == 2_500  # 25 min -> 500 mpt a 5000
    op.cerrar_semana_operativa(m, b, cola, TS, "2026-W31")

    # --- W32: la venta real, atribuida al trabajo; el colusivo debe fallar
    op.abrir_semana(k, TS, "2026-W32", 4_000, 500)
    k.acunar(TS, "2026-W32", "dep:mercado", 150_000,
             t.SubtipoAcunacion.VENTA, {"tipo": "firma_pedro"},
             detalle_extra={"trabajo": "radar"})
    # curiosos quema todo su presupuesto en API y quiebra al cierre
    m.gastar_api(TS, "2026-W32", "dep:curiosos", 40_000)
    res32 = op.cerrar_semana_operativa(m, b, cola, TS, "2026-W32")
    assert "dep:curiosos" in res32["cierre"].quiebras
    # rescate colusivo: transferencia interna normal a un congelado -> falla
    with pytest.raises(mkt.ErrorMercado):
        m.vender_servicio(TS, "2026-W32", "dep:mercado", "dep:curiosos", 1_000)
    # rescate firmado desde la cuenta de Pedro -> pasa y descongela
    cp.rescatar(k, TS, "2026-W32", "dep:curiosos", 2_000,
                firma={"tipo": "firma_pedro"})
    assert not deps.es_congelado(k.libro.asientos(), "dep:curiosos")

    # --- W33: cierra el ciclo; el trabajo radar muere por gasto en el cierre
    op.abrir_semana(k, TS, "2026-W33", 4_000, 500)
    m.gastar_api(TS, "2026-W33", "trabajo:radar", 15_000, dueno="dep:mercado")
    saldo_mercado_antes = k.saldo("dep:mercado")
    res33 = op.cerrar_semana_operativa(m, b, cola, TS, "2026-W33")
    assert "radar" in res33["cierre"].trabajos_muertos
    assert b.estado("radar") == "liquidada"
    # el remanente del trabajo (30k - 10k - 15k = 5k) volvio al financiador
    assert k.saldo("trabajo:radar") == 0
    assert k.saldo("dep:mercado") == saldo_mercado_antes + 5_000 + 50_000
    assert len(res33["informes_ciclo"]) == 1  # el ciclo 0 cerro

    # --- el tipo de cambio sigue en el arranque: la regla de bootstrap rige
    # hasta 4 semanas con consumo (spec 3.2d); la venta ya esta en el lapso
    # y empujara el tipo cuando el bootstrap termine
    tipo_final = pt.tipo_de_cambio(k.libro.asientos(), "2026-W33")
    assert tipo_final == 5_000

    # --- invariantes globales del libro (spec 13)
    asientos = k.libro.asientos()
    acunado = sum(a.monto for a in asientos
                  if a.tipo is t.TipoAsiento.ACUNACION)
    destruido = sum(a.monto for a in asientos
                    if a.tipo is t.TipoAsiento.DESTRUCCION)
    total = sum(v for (cta, div), v in saldos(asientos).items()
                if div is t.Divisa.MONEDA)
    assert total == acunado - destruido  # ni una milimoneda inventada
    # reproducibilidad: reconstruir desde disco da lo mismo
    k2 = Kernel(Libro(tmp_path / "libro.jsonl"))
    assert saldos(k2.libro.asientos()) == saldos(asientos)
```

- [ ] **Step 2: Run the simulation**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_simulacion.py -v`
Expected: PASS. Si falla, NO ajustar asserts: reportar el fallo con la traza (es un bug del paquete o una traza mal calculada del plan — el controlador decide).

- [ ] **Step 3: Run the whole world**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_libro.py test_economia_kernel.py test_economia_pt.py test_economia_capacidad.py test_economia_mercado.py test_economia_bus.py test_economia_eficiencia.py test_economia_cierre.py test_economia_frontera.py test_economia_pagador.py test_economia_server.py test_economia_simulacion.py test_resource_dispatcher.py -v`
Expected: todo verde.

- [ ] **Step 4: Commit**

```bash
git add test_economia_simulacion.py
git commit -m "test(economia): simulacion de ciclo completo — spec seccion 13"
```

---

## Qué queda fuera (specs futuros, sección 12 del spec)

Mapa RTS (la vista), mezcla multi-proveedor, capa de estilo, conectores automáticos (señales externas y bancarios), puentes Atlas/research-court, y la PWA/clientes multiplataforma. El primer corte queda operable por API y archivos: abrir semana, fichar con el reloj, atender la cola, cerrar semana — todo desde los endpoints o los módulos.
