# Modelo de Ciudad (Plan 1 de 3) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir la derivación del libro contable a modelo de ciudad y el urbanismo por física de afinidad, expuestos en `GET /api/mapa/ciudad` — el servidor entrega un modelo con coordenadas ya calculadas, sin dibujar nada.

**Architecture:** Paquete nuevo `calipso/mapa/`, LECTOR puro sobre `calipso/economia/`: no escribe en el libro, no importa nada que escriba. `ciudad.py` pliega asientos y estado a un modelo; `urbanismo.py` le pone coordenadas con resortes y repulsión, determinístico y anclado por antigüedad. El endpoint arma ambos y devuelve JSON. Cero dibujo, cero pixeles: eso es del Plan 2.

**Tech Stack:** Python 3.14, solo stdlib (`hashlib` para el hash estable, `math`, `datetime` solo para aritmética de fechas sobre strings dados). Tests pytest en la raíz, patrón de `test_economia_*.py`.

**Spec:** `docs/superpowers/specs/2026-08-25-mapa-rts-design.md` (secciones 2, 3, 4 y la parte de `GET /api/mapa/ciudad` de la 6). El Plan 2 (cliente: render pixel, cámara, paneles, acoplamiento) y el Plan 3 (pulso: instrumentación, WS, interior, reasoning) se escriben cuando este ejecute.

## Global Constraints

- Python 3.14, stdlib only. Español sin emojis. `from __future__ import annotations`. Montos en milimonedas (`int`), como toda la economía.
- **`calipso/mapa/` es LECTOR** (invariante 4 del spec): no llama a `Kernel.transferir/destruir/acunar/reservar/liberar`, no importa `mercado`, `direccion`, `operacion` ni `pagador`. Solo lee `libro`, `balances`, `tipos`, `capacidad`, `departamentos`, `bus`, `cola`, `eficiencia`, `pt`, `personal`.
- **Determinismo absoluto** (invariante 2): ninguna función lee el reloj del sistema ni usa RNG. La "actividad reciente" se calcula contra el último `ts` del propio libro, no contra la hora actual. El hash de posición inicial es SHA-256 truncado, jamás `hash()` de Python (que varía entre procesos). Todo recorrido de colecciones va ordenado.
- **El modelo es datos, no dibujo** (invariante 3): ningún campo del modelo habla de píxeles, colores ni sprites. Tamaños en escala 1-9, anchos en 1-4, coordenadas en unidades abstractas.
- `estado` de un edificio es `activo` o `congelado`. **Corrección al spec:** el estado `cerrado` que la sección 3 menciona no es derivable del libro (liquidar no deja marca distinguible), así que no existe. El spec se corrige en la Task 1.
- Pytest dirigido: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_*.py -v` — jamás `pytest` a secas. Regresión completa por tarea: los 13 archivos de test existentes siguen verdes.
- `calipso/server.py` es código EXISTENTE de 3.400+ líneas: cambio quirúrgico, en su propia sección, siguiendo el patrón de los endpoints de economía (estado fresco por request, candado para leer).

## File Structure

- Create: `calipso/mapa/__init__.py` — expone `ciudad` y `urbanizar`.
- Create: `calipso/mapa/ciudad.py` — derivación: edificios, calles, unidades, avisos, cabecera.
- Create: `calipso/mapa/urbanismo.py` — física de afinidad determinística.
- Modify: `calipso/server.py` — sección `MAPA` con `GET /api/mapa/ciudad`.
- Modify: `docs/superpowers/specs/2026-08-25-mapa-rts-design.md` — corrección del estado `cerrado`.
- Test: `test_mapa_ciudad.py` (Tasks 1-2), `test_mapa_urbanismo.py` (Task 3), `test_mapa_server.py` (Task 4).

---

### Task 1: Edificios — la derivación de cada departamento

**Files:**
- Create: `calipso/mapa/__init__.py`
- Create: `calipso/mapa/ciudad.py`
- Modify: `docs/superpowers/specs/2026-08-25-mapa-rts-design.md`
- Test: `test_mapa_ciudad.py`

**Interfaces:**
- Consumes: de la economía, `tipos` (`Asiento`, `TipoAsiento`, `Divisa`, `TESORO`, `CUENTA_PEDRO`), `balances.saldos`, `departamentos` (`Registro`, `Departamento` con `.nombre/.zona/.cuenta`, `ZONA_FABRICA`, `ZONA_PERSONAL`, `es_congelado`), `bus.Bus` (`ids()`, `activas()`, `datos(id) -> dict` con clave `"departamento"`), `cola.Cola` (`pendientes() -> list[dict]` con claves `"id"`, `"departamento"`, `"tipo"`, `"monedas_en_juego"`, `"es_carta"`).
- Produces: `tamano_de(saldo_mm: int) -> int`; `actividad_de(asientos, cuenta, dias=3) -> int`; `duenos_de(bus) -> dict[str, str]`; `edificios(asientos, registro, bus, cola) -> list[dict]` — cada edificio con las claves `id, nombre, zona, orden, tamano, estado, saldo_mm, actividad, trabajos, compuertas`.

- [ ] **Step 1: Write the failing test**

```python
# test_mapa_ciudad.py
"""Tests de la derivacion del libro al modelo de ciudad."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import cola as cola_mod
from calipso.economia import departamentos as deps
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.mapa import ciudad as ciu

TS = "2026-08-25T10:00:00"
W = "2026-W35"


@pytest.fixture
def mundo(tmp_path):
    """Libro sintetico con dos departamentos de fabrica y uno personal."""
    k = Kernel(Libro(tmp_path / "libro.jsonl"))
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("mercado", deps.ZONA_FABRICA))
    r.alta(deps.Departamento("curiosos", deps.ZONA_FABRICA))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    c = cola_mod.Cola(tmp_path / "cola.jsonl")
    return k, r, b, c


def _capital(k, monto, destino, ts=TS, semana=W):
    k.acunar(ts, semana, destino, monto, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})


def test_tamano_crece_con_el_saldo_y_tiene_techo():
    assert ciu.tamano_de(0) == 1
    assert ciu.tamano_de(-500) == 1
    assert ciu.tamano_de(1_000) == 2
    assert ciu.tamano_de(50_000) == 3
    assert ciu.tamano_de(1_000_000) == 5
    assert ciu.tamano_de(10 ** 15) == 9  # techo


def test_edificios_salen_del_registro_con_su_saldo(mundo):
    k, r, b, c = mundo
    _capital(k, 50_000, "dep:mercado")
    _capital(k, 1_000, "personal:finanzas")
    _capital(k, 4_000, t.CUENTA_PEDRO)
    edis = {e["id"]: e for e in ciu.edificios(k.libro.asientos(), r, b, c)}
    assert set(edis) == {"dep:mercado", "dep:curiosos", "personal:finanzas",
                         "cuenta_pedro"}
    assert edis["dep:mercado"]["saldo_mm"] == 50_000
    assert edis["dep:mercado"]["tamano"] == 3
    assert edis["dep:mercado"]["zona"] == deps.ZONA_FABRICA
    assert edis["dep:curiosos"]["tamano"] == 1  # sin plata, sigue existiendo
    assert edis["cuenta_pedro"]["zona"] == deps.ZONA_PERSONAL
    assert edis["cuenta_pedro"]["nombre"] == "pedro"


def test_orden_es_por_primera_aparicion_en_el_libro(mundo):
    k, r, b, c = mundo
    _capital(k, 1_000, "dep:curiosos")   # aparece primero
    _capital(k, 1_000, "dep:mercado")
    edis = {e["id"]: e for e in ciu.edificios(k.libro.asientos(), r, b, c)}
    assert edis["dep:curiosos"]["orden"] < edis["dep:mercado"]["orden"]
    # uno que nunca aparecio queda al final, no rompe
    assert edis["personal:finanzas"]["orden"] > edis["dep:mercado"]["orden"]


def test_congelado_se_ve_en_el_estado(mundo):
    k, r, b, c = mundo
    _capital(k, 1_000, "dep:curiosos")
    assert ciu.edificios(k.libro.asientos(), r, b, c)
    deps.declarar_quiebra(k, TS, W, "dep:curiosos")
    edis = {e["id"]: e for e in ciu.edificios(k.libro.asientos(), r, b, c)}
    assert edis["dep:curiosos"]["estado"] == "congelado"
    assert edis["dep:mercado"]["estado"] == "activo"


def test_actividad_cuenta_dias_con_gasto_contra_el_ultimo_ts(mundo):
    """Determinismo: la ventana se mide contra el libro, no contra el reloj."""
    k, r, b, c = mundo
    _capital(k, 100_000, "dep:mercado", ts="2026-08-19T09:00:00")
    # cuatro dias con gasto, pero solo tres entran en la ventana
    for dia in ("2026-08-20", "2026-08-23", "2026-08-24", "2026-08-25"):
        k.destruir(f"{dia}T10:00:00", W, "dep:mercado", 100, motivo="api")
    asientos = k.libro.asientos()
    assert ciu.actividad_de(asientos, "dep:mercado") == 3  # techo y ventana
    assert ciu.actividad_de(asientos, "dep:curiosos") == 0
    # con dos dias de ventana, solo cuentan los dos ultimos
    assert ciu.actividad_de(asientos, "dep:mercado", dias=2) == 2
    # y no depende del reloj: reconstruido desde disco da lo mismo
    k2 = Kernel(Libro(k.libro.ruta))
    assert ciu.actividad_de(k2.libro.asientos(), "dep:mercado") == 3


def test_trabajos_y_compuertas_se_cuelgan_de_su_dueno(mundo):
    k, r, b, c = mundo
    _capital(k, 100_000, "dep:mercado")
    b.alta(TS, W, "radar", "dep:mercado", "radar vertical", 10_000, 30_000,
           {"gasto_max_mm": 5_000})
    b.marcar(TS, W, "radar", "financiada")
    c.encolar(k, TS, W, "c1", "dep:mercado", "llamar cliente", tipo="contacto",
              obligatoria=True, mpt_estimado=500, monedas_en_juego=90_000)
    edis = {e["id"]: e for e in ciu.edificios(k.libro.asientos(), r, b, c)}
    assert edis["dep:mercado"]["trabajos"] == ["radar"]
    assert edis["dep:mercado"]["compuertas"] == 1
    assert edis["dep:curiosos"]["trabajos"] == []
    assert edis["dep:curiosos"]["compuertas"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_ciudad.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'calipso.mapa'`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/mapa/__init__.py
"""
calipso/mapa — El modelo de ciudad (spec 2026-08-25).

Lector puro sobre calipso/economia: pliega el libro y devuelve un MODELO
con coordenadas, nunca un dibujo. Ninguna funcion de este paquete escribe
en el libro ni lee el reloj del sistema.
"""
from __future__ import annotations

from . import ciudad  # noqa: F401
```

```python
# calipso/mapa/ciudad.py
"""
calipso/mapa/ciudad.py — Del libro al modelo.

Cada departamento es un edificio cuyo tamano sale de su saldo, cuyo estado
sale de su quiebra y cuya actividad sale de si gasto en los ultimos dias
del propio libro (nunca del reloj del sistema: eso romperia el
determinismo del mapa).
"""
from __future__ import annotations

import datetime

from calipso.economia import departamentos as deps
from calipso.economia import balances as bal
from calipso.economia.tipos import (Asiento, CUENTA_PEDRO, Divisa,
                                    TipoAsiento)

DIAS_ACTIVIDAD = 3
ACTIVIDAD_MAX = 3


def _digitos(n: int) -> int:
    return len(str(n)) if n > 0 else 0


def tamano_de(saldo_mm: int) -> int:
    """Escala 1-9: crece rapido al principio y lento despues, para que un
    departamento rico no tape a los demas."""
    return min(9, 1 + _digitos(max(0, saldo_mm) // 1000))


def actividad_de(asientos: list[Asiento], cuenta: str,
                 dias: int = DIAS_ACTIVIDAD) -> int:
    """Senal de vida barata: cuantos de los ultimos dias tuvieron gasto.
    La ventana se mide contra el ultimo asiento DEL LIBRO."""
    if not asientos:
        return 0
    fin = datetime.date.fromisoformat(max(a.ts for a in asientos)[:10])
    ventana = {(fin - datetime.timedelta(days=i)).isoformat()
               for i in range(dias)}
    salidas = (TipoAsiento.DESTRUCCION, TipoAsiento.TRANSFERENCIA)
    con_gasto = {a.ts[:10] for a in asientos
                 if a.origen == cuenta and a.tipo in salidas
                 and a.ts[:10] in ventana}
    return min(ACTIVIDAD_MAX, len(con_gasto))


def duenos_de(bus) -> dict[str, str]:
    """id de trabajo -> cuenta del departamento dueno."""
    return {id: bus.datos(id)["departamento"] for id in bus.ids()}


def _orden_de_aparicion(asientos: list[Asiento]) -> dict[str, int]:
    """Antiguedad: en que posicion aparecio cada cuenta por primera vez."""
    visto: dict[str, int] = {}
    for a in asientos:
        for cuenta in (a.destino, a.origen):
            if cuenta and cuenta not in visto:
                visto[cuenta] = len(visto)
    return visto


def edificios(asientos: list[Asiento], registro, bus, cola) -> list[dict]:
    saldos = bal.saldos(asientos)
    aparicion = _orden_de_aparicion(asientos)
    nunca = len(aparicion)
    duenos = duenos_de(bus)
    vivos = set(bus.activas())
    pendientes = [p for p in cola.pendientes() if not p.get("es_carta")]

    filas = [(d.cuenta, d.nombre, d.zona) for d in registro.todos()]
    filas.append((CUENTA_PEDRO, "pedro", deps.ZONA_PERSONAL))

    out = []
    for cuenta, nombre, zona in sorted(filas):
        saldo = saldos.get((cuenta, Divisa.MONEDA), 0)
        out.append({
            "id": cuenta,
            "nombre": nombre,
            "zona": zona,
            "orden": aparicion.get(cuenta, nunca),
            "tamano": tamano_de(saldo),
            "estado": ("congelado" if deps.es_congelado(asientos, cuenta)
                       else "activo"),
            "saldo_mm": saldo,
            "actividad": actividad_de(asientos, cuenta),
            "trabajos": sorted(id for id in vivos
                               if duenos.get(id) == cuenta),
            "compuertas": sum(1 for p in pendientes
                              if p.get("departamento") == cuenta),
        })
    return out
```

Y corregir el spec, `docs/superpowers/specs/2026-08-25-mapa-rts-design.md`, reemplazando la fila de estado de la tabla de edificios:

```
| `estado` | `activo` \| `congelado` (quiebra declarada sin rescate). No existe `cerrado`: liquidar no deja marca distinguible en el libro, asi que no es derivable |
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_ciudad.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/mapa/__init__.py calipso/mapa/ciudad.py test_mapa_ciudad.py docs/superpowers/specs/2026-08-25-mapa-rts-design.md
git commit -m "feat(mapa): edificios — tamano por saldo, estado, actividad y carga"
```

---

### Task 2: Calles, unidades, avisos y el modelo completo

**Files:**
- Modify: `calipso/mapa/ciudad.py`
- Test: `test_mapa_ciudad.py` (agregar tests)

**Interfaces:**
- Consumes: lo de la Task 1, más `capacidad.semanas_operativas`, `bus.gastado`, `bus.aportes`, `pt.tipo_de_cambio`, `personal.linea_empleo_mm_por_hora` y `personal.SUELDO_MENSUAL_MM`, `tipos.TESORO`/`DIRECCION`.
- Produces: `VENTANA_SEMANAS = 8`; `ancho_de(peso_mm: int) -> int`; `calles(asientos, edificios_, duenos, semanas) -> list[dict]` con `a, b, peso_mm, ancho, tipo`; `unidades(asientos, bus, duenos) -> list[dict]` con `id, dueno, gastado_mm, hacia`; `avisos(cola) -> list[dict]` con `id, tipo, sobre, monedas_en_juego_mm`; `ciudad(asientos, registro, bus, cola, semana, minutos_empleo=0) -> dict` con la cabecera completa (`semana, tesoro_mm, cuenta_pedro_mm, direccion_mm, tipo_cambio_mm, linea_empleo_mm, edificios, calles, unidades, avisos`).

- [ ] **Step 1: Write the failing tests**

```python
# agregar a test_mapa_ciudad.py
from calipso.economia import pt


def _semana_op(k, semana):
    pt.emitir_semana(k, TS, semana, 4_000, 0)
    pt.expirar_pools(k, TS, semana)


def test_ancho_por_buckets_de_comercio():
    assert ciu.ancho_de(0) == 1
    assert ciu.ancho_de(9_999) == 1
    assert ciu.ancho_de(10_000) == 2
    assert ciu.ancho_de(100_000) == 3
    assert ciu.ancho_de(1_000_000) == 4


def test_calle_por_servicio_directo_y_cable_entre_zonas(mundo):
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 200_000, "dep:mercado")
    _capital(k, 200_000, "personal:finanzas")
    k.transferir(TS, W, "dep:mercado", "dep:curiosos", 120_000,
                 motivo="servicio")
    k.transferir(TS, W, "personal:finanzas", "dep:mercado", 5_000,
                 motivo="servicio")
    asientos = k.libro.asientos()
    edis = ciu.edificios(asientos, r, b, c)
    cs = {(x["a"], x["b"]): x for x in ciu.calles(
        asientos, edis, ciu.duenos_de(b), [W])}
    assert cs[("dep:curiosos", "dep:mercado")]["peso_mm"] == 120_000
    assert cs[("dep:curiosos", "dep:mercado")]["ancho"] == 3
    assert cs[("dep:curiosos", "dep:mercado")]["tipo"] == "calle"
    # cruza zonas: es cable
    assert cs[("dep:mercado", "personal:finanzas")]["tipo"] == "cable"


def test_financiar_el_trabajo_de_otro_tambien_es_comercio(mundo):
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 200_000, "dep:curiosos")
    b.alta(TS, W, "radar", "dep:mercado", "radar", 10_000, 30_000,
           {"gasto_max_mm": 5_000})
    b.marcar(TS, W, "radar", "financiada")
    k.transferir(TS, W, "dep:curiosos", "trabajo:radar", 40_000,
                 motivo="financiacion")
    asientos = k.libro.asientos()
    edis = ciu.edificios(asientos, r, b, c)
    cs = {(x["a"], x["b"]): x for x in ciu.calles(
        asientos, edis, ciu.duenos_de(b), [W])}
    assert cs[("dep:curiosos", "dep:mercado")]["peso_mm"] == 40_000


def test_la_capacidad_no_crea_calles_entre_departamentos(mundo):
    """Comprar capacidad va a direccion, no al otro departamento."""
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 200_000, "dep:mercado")
    k.transferir(TS, W, "dep:mercado", t.DIRECCION, 30_000, motivo="capacidad",
                 detalle_extra={"suscripcion": "claude_max", "unidades": 10})
    asientos = k.libro.asientos()
    edis = ciu.edificios(asientos, r, b, c)
    assert ciu.calles(asientos, edis, ciu.duenos_de(b), [W]) == []


def test_unidades_son_los_trabajos_vivos(mundo):
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 200_000, "dep:mercado")
    _capital(k, 200_000, "dep:curiosos")
    b.alta(TS, W, "radar", "dep:mercado", "radar", 10_000, 30_000,
           {"gasto_max_mm": 50_000})
    b.marcar(TS, W, "radar", "financiada")
    k.transferir(TS, W, "dep:mercado", "trabajo:radar", 20_000,
                 motivo="financiacion")
    k.transferir(TS, W, "dep:curiosos", "trabajo:radar", 60_000,
                 motivo="financiacion")
    k.destruir(TS, W, "trabajo:radar", 7_000, motivo="api", ref="trabajo:radar")
    us = ciu.unidades(k.libro.asientos(), b, ciu.duenos_de(b))
    assert len(us) == 1
    assert us[0]["id"] == "radar"
    assert us[0]["dueno"] == "dep:mercado"
    assert us[0]["gastado_mm"] == 7_000
    # camina hacia el mayor cofinanciador que no es el dueno
    assert us[0]["hacia"] == "dep:curiosos"


def test_avisos_traen_lo_que_espera_tu_firma(mundo):
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 200_000, "dep:mercado")
    c.encolar(k, TS, W, "c1", "dep:mercado", "llamar", tipo="contacto",
              obligatoria=True, mpt_estimado=500, monedas_en_juego=90_000)
    c.encolar_carta(TS, W, "renovacion:claude_max:0",
                    {"tipo": "renovacion", "suscripcion": "claude_max"})
    avs = {a["id"]: a for a in ciu.avisos(c)}
    assert avs["c1"]["sobre"] == "dep:mercado"
    assert avs["c1"]["monedas_en_juego_mm"] == 90_000
    assert avs["c1"]["tipo"] == "contacto"
    assert avs["renovacion:claude_max:0"]["sobre"] is None


def test_ciudad_arma_la_cabecera_completa(mundo):
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 1_200_000, t.TESORO)
    _capital(k, 5_000, t.CUENTA_PEDRO)
    m = ciu.ciudad(k.libro.asientos(), r, b, c, W, minutos_empleo=9_600)
    assert m["semana"] == W
    assert m["tesoro_mm"] == 1_200_000
    assert m["cuenta_pedro_mm"] == 5_000
    assert m["direccion_mm"] == 0
    assert m["tipo_cambio_mm"] == 5_000     # arranque, sin historia
    assert m["linea_empleo_mm"] == 15_625   # 2.500.000 * 60 // 9600
    assert len(m["edificios"]) == 4
    assert m["calles"] == [] and m["unidades"] == [] and m["avisos"] == []


def test_ciudad_es_reproducible(mundo):
    """Invariante 2: mismo libro, mismo modelo — tambien desde disco."""
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 50_000, "dep:mercado")
    a = ciu.ciudad(k.libro.asientos(), r, b, c, W)
    k2 = Kernel(Libro(k.libro.ruta))
    dos = ciu.ciudad(k2.libro.asientos(), r, b, c, W)
    assert a == dos
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_ciudad.py -v`
Expected: FAIL con `AttributeError: module ... has no attribute 'ancho_de'`

- [ ] **Step 3: Write minimal implementation**

```python
# agregar a calipso/mapa/ciudad.py — sumar al bloque de imports:
from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import personal as per_mod
from calipso.economia import pt
from calipso.economia.tipos import DIRECCION, TESORO

VENTANA_SEMANAS = 8
_ANCHOS = ((10_000, 1), (100_000, 2), (1_000_000, 3))


def ancho_de(peso_mm: int) -> int:
    for tope, ancho in _ANCHOS:
        if peso_mm < tope:
            return ancho
    return 4


def calles(asientos: list[Asiento], edificios_: list[dict],
           duenos: dict[str, str], semanas: list[str]) -> list[dict]:
    """Comercio directo entre departamentos: servicios vendidos y
    financiacion del trabajo de otro. La compra de capacidad no cuenta:
    su destino es direccion, no el otro departamento."""
    zona = {e["id"]: e["zona"] for e in edificios_}
    pesos: dict[tuple[str, str], int] = {}
    for a in asientos:
        if a.tipo is not TipoAsiento.TRANSFERENCIA or a.semana not in semanas:
            continue
        motivo = a.detalle.get("motivo")
        if motivo == "servicio":
            otro = a.destino
        elif motivo == "financiacion" and a.destino.startswith("trabajo:"):
            otro = duenos.get(a.destino.split(":", 1)[1])
        else:
            continue
        if not otro or otro == a.origen:
            continue
        if a.origen not in zona or otro not in zona:
            continue
        par = tuple(sorted((a.origen, otro)))
        pesos[par] = pesos.get(par, 0) + a.monto
    return [{"a": x, "b": y, "peso_mm": p, "ancho": ancho_de(p),
             "tipo": "calle" if zona[x] == zona[y] else "cable"}
            for (x, y), p in sorted(pesos.items())]


def unidades(asientos: list[Asiento], bus, duenos: dict[str, str]) -> list[dict]:
    out = []
    for id in bus.activas():
        dueno = duenos.get(id, "")
        aportes = bus_mod.aportes(asientos, id)
        ajenos = sorted(((monto, quien) for quien, monto in aportes.items()
                         if quien != dueno), reverse=True)
        out.append({"id": id, "dueno": dueno,
                    "gastado_mm": bus_mod.gastado(asientos, id),
                    "hacia": ajenos[0][1] if ajenos else None})
    return out


def avisos(cola) -> list[dict]:
    out = []
    for p in cola.pendientes():
        if p.get("es_carta"):
            tipo = (p.get("carta") or {}).get("tipo", "carta")
            sobre = None
        else:
            tipo = p.get("tipo", "compuerta")
            sobre = p.get("departamento")
        out.append({"id": p["id"], "tipo": tipo, "sobre": sobre,
                    "monedas_en_juego_mm": p.get("monedas_en_juego", 0)})
    return out


def ciudad(asientos: list[Asiento], registro, bus, cola, semana: str,
           minutos_empleo: int = 0) -> dict:
    saldos = bal.saldos(asientos)
    ops = cap.semanas_operativas(asientos)
    ventana = ops[-VENTANA_SEMANAS:]
    edis = edificios(asientos, registro, bus, cola)
    duenos = duenos_de(bus)
    return {
        "semana": semana,
        "tesoro_mm": saldos.get((TESORO, Divisa.MONEDA), 0),
        "cuenta_pedro_mm": saldos.get((CUENTA_PEDRO, Divisa.MONEDA), 0),
        "direccion_mm": saldos.get((DIRECCION, Divisa.MONEDA), 0),
        "tipo_cambio_mm": pt.tipo_de_cambio(asientos, semana) if ops else 5_000,
        "linea_empleo_mm": per_mod.linea_empleo_mm_por_hora(
            per_mod.SUELDO_MENSUAL_MM, minutos_empleo),
        "edificios": edis,
        "calles": calles(asientos, edis, duenos, ventana),
        "unidades": unidades(asientos, bus, duenos),
        "avisos": avisos(cola),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_ciudad.py -v`
Expected: PASS (14 tests). Regresión: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_libro.py test_economia_kernel.py test_economia_pt.py test_economia_capacidad.py test_economia_mercado.py test_economia_bus.py test_economia_eficiencia.py test_economia_cierre.py test_economia_frontera.py test_economia_pagador.py test_economia_server.py test_economia_simulacion.py test_resource_dispatcher.py -q` sigue en 172.

- [ ] **Step 5: Commit**

```bash
git add calipso/mapa/ciudad.py test_mapa_ciudad.py
git commit -m "feat(mapa): calles por comercio real, unidades, avisos y el modelo completo"
```

---

### Task 3: Urbanismo — la física de afinidad

**Files:**
- Create: `calipso/mapa/urbanismo.py`
- Modify: `calipso/mapa/__init__.py`
- Test: `test_mapa_urbanismo.py`

**Interfaces:**
- Consumes: los dicts de edificio (`id`, `zona`, `tamano`, `orden`) y de calle (`a`, `b`, `ancho`) de las Tasks 1-2. No importa nada de la economía.
- Produces: `urbanizar(edificios, calles, iteraciones=300) -> dict[str, tuple[int, int]]`; constantes `K_REPULSION`, `K_RESORTE`, `PASO`, `AMORTIGUACION`, `REPOSO` (tupla indexada por ancho), `SEPARACION_ZONAS`.

- [ ] **Step 1: Write the failing tests**

```python
# test_mapa_urbanismo.py
"""Tests del urbanismo: fisica de afinidad determinista y estable."""
import math

from calipso.mapa import urbanismo as urb


def _edi(id, orden, tamano=3, zona="fabrica"):
    return {"id": id, "orden": orden, "tamano": tamano, "zona": zona}


def _dist(pos, a, b):
    return math.dist(pos[a], pos[b])


def test_el_mas_viejo_queda_clavado_en_el_origen():
    edis = [_edi("dep:a", 0), _edi("dep:b", 1), _edi("dep:c", 2)]
    pos = urb.urbanizar(edis, [])
    assert pos["dep:a"] == (0, 0)
    assert pos["dep:b"] != (0, 0)


def test_mismo_insumo_mismas_coordenadas():
    edis = [_edi("dep:a", 0), _edi("dep:b", 1), _edi("dep:c", 2)]
    calles = [{"a": "dep:a", "b": "dep:b", "ancho": 4}]
    assert urb.urbanizar(edis, calles) == urb.urbanizar(edis, calles)
    # y no depende del orden en que vengan las listas
    assert urb.urbanizar(edis, calles) == urb.urbanizar(
        list(reversed(edis)), calles)


def test_los_que_comercian_quedan_mas_cerca():
    edis = [_edi("dep:a", 0), _edi("dep:b", 1), _edi("dep:c", 2)]
    juntos = urb.urbanizar(edis, [{"a": "dep:a", "b": "dep:b", "ancho": 4}])
    sueltos = urb.urbanizar(edis, [])
    assert _dist(juntos, "dep:a", "dep:b") < _dist(sueltos, "dep:a", "dep:b")


def test_mas_comercio_es_menos_distancia():
    edis = [_edi("dep:a", 0), _edi("dep:b", 1)]
    fuerte = urb.urbanizar(edis, [{"a": "dep:a", "b": "dep:b", "ancho": 4}])
    debil = urb.urbanizar(edis, [{"a": "dep:a", "b": "dep:b", "ancho": 1}])
    assert _dist(fuerte, "dep:a", "dep:b") < _dist(debil, "dep:a", "dep:b")


def test_nadie_queda_encimado():
    edis = [_edi(f"dep:{n}", i) for i, n in enumerate("abcdef")]
    pos = urb.urbanizar(edis, [])
    ids = sorted(pos)
    for i, x in enumerate(ids):
        for y in ids[i + 1:]:
            assert _dist(pos, x, y) > 20


def test_la_zona_personal_queda_agrupada_y_aparte():
    edis = [_edi("dep:a", 0), _edi("dep:b", 1),
            _edi("personal:x", 2, zona="personal"),
            _edi("personal:y", 3, zona="personal")]
    pos = urb.urbanizar(edis, [])
    entre_personales = _dist(pos, "personal:x", "personal:y")
    cruzada = min(_dist(pos, p, f) for p in ("personal:x", "personal:y")
                  for f in ("dep:a", "dep:b"))
    assert entre_personales < cruzada


def test_un_departamento_nuevo_no_reacomoda_la_ciudad():
    """Anclaje por antiguedad: la ciudad crece hacia afuera."""
    viejos = [_edi("dep:a", 0), _edi("dep:b", 1), _edi("dep:c", 2)]
    antes = urb.urbanizar(viejos, [])
    despues = urb.urbanizar(viejos + [_edi("dep:nuevo", 3)], [])
    assert despues["dep:a"] == antes["dep:a"] == (0, 0)
    corrimiento = max(math.dist(antes[i], despues[i]) for i in antes)
    assert corrimiento < 60


def test_ciudad_vacia_y_de_uno_no_rompen():
    assert urb.urbanizar([], []) == {}
    assert urb.urbanizar([_edi("dep:solo", 0)], []) == {"dep:solo": (0, 0)}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_urbanismo.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'calipso.mapa.urbanismo'`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/mapa/urbanismo.py
"""
calipso/mapa/urbanismo.py — Donde nace y crece cada departamento.

Resortes donde hay comercio, repulsion entre todos, y anclaje por
antiguedad: el mas viejo queda clavado y la inercia baja con el orden de
llegada, asi la ciudad CRECE HACIA AFUERA en vez de reacomodarse entera
cuando nace un departamento. Determinista de punta a punta: la posicion
inicial sale de un SHA-256 del nombre (nunca de hash(), que varia entre
procesos), el numero de iteraciones es fijo y todo recorrido va ordenado.
"""
from __future__ import annotations

import hashlib
import math

K_REPULSION = 900_000.0
K_RESORTE = 0.030
PASO = 0.55
AMORTIGUACION = 0.85
SEPARACION_ZONAS = 900.0
RADIO_INICIAL = 120.0
REPOSO = (0.0, 260.0, 190.0, 130.0, 80.0)  # indexado por ancho 1..4


def _angulo(nombre: str) -> float:
    h = hashlib.sha256(nombre.encode("utf-8")).digest()
    return (int.from_bytes(h[:4], "big") / 0xFFFFFFFF) * 2 * math.pi


def urbanizar(edificios: list[dict], calles: list[dict],
              iteraciones: int = 300) -> dict[str, tuple[int, int]]:
    if not edificios:
        return {}
    orden = sorted(edificios, key=lambda e: (e["orden"], e["id"]))
    ancla = orden[0]["id"]
    pos: dict[str, list[float]] = {}
    masa: dict[str, float] = {}
    zona: dict[str, str] = {}
    for i, e in enumerate(orden):
        ang = _angulo(e["id"])
        radio = RADIO_INICIAL * (1 + i)
        pos[e["id"]] = [radio * math.cos(ang), radio * math.sin(ang)]
        masa[e["id"]] = 1.0 + e["tamano"] + max(0.0, 6.0 - e["orden"])
        zona[e["id"]] = e["zona"]
    pos[ancla] = [0.0, 0.0]

    ids = sorted(pos)
    vel = {i: [0.0, 0.0] for i in ids}
    aristas = [(a["a"], a["b"], REPOSO[min(4, max(1, a["ancho"]))])
               for a in calles if a["a"] in pos and a["b"] in pos]

    for _ in range(iteraciones):
        fuerza = {i: [0.0, 0.0] for i in ids}
        for n, x in enumerate(ids):
            for y in ids[n + 1:]:
                dx = pos[y][0] - pos[x][0]
                dy = pos[y][1] - pos[x][1]
                d2 = max(dx * dx + dy * dy, 1.0)
                d = math.sqrt(d2)
                f = K_REPULSION / d2
                fuerza[x][0] -= f * dx / d
                fuerza[x][1] -= f * dy / d
                fuerza[y][0] += f * dx / d
                fuerza[y][1] += f * dy / d
                if zona[x] != zona[y]:
                    g = SEPARACION_ZONAS / d
                    fuerza[x][0] -= g * dx / d
                    fuerza[x][1] -= g * dy / d
                    fuerza[y][0] += g * dx / d
                    fuerza[y][1] += g * dy / d
        for x, y, reposo in aristas:
            dx = pos[y][0] - pos[x][0]
            dy = pos[y][1] - pos[x][1]
            d = max(math.sqrt(dx * dx + dy * dy), 1.0)
            f = K_RESORTE * (d - reposo)
            fuerza[x][0] += f * dx / d
            fuerza[x][1] += f * dy / d
            fuerza[y][0] -= f * dx / d
            fuerza[y][1] -= f * dy / d
        for i in ids:
            if i == ancla:
                continue
            vel[i][0] = (vel[i][0] + fuerza[i][0] * PASO / masa[i]) * AMORTIGUACION
            vel[i][1] = (vel[i][1] + fuerza[i][1] * PASO / masa[i]) * AMORTIGUACION
            pos[i][0] += vel[i][0]
            pos[i][1] += vel[i][1]

    return {i: (round(pos[i][0]), round(pos[i][1])) for i in ids}
```

Y en `calipso/mapa/__init__.py`, sumar al import: `from . import ciudad, urbanismo  # noqa: F401`

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_urbanismo.py -v`
Expected: PASS (8 tests).

Nota para el implementador: si `test_nadie_queda_encimado` o `test_un_departamento_nuevo_no_reacomoda_la_ciudad` fallan por poco, el problema son las constantes, no la forma. Ajustar `K_REPULSION` (más separación) o `AMORTIGUACION` (menos corrimiento) y dejar el valor que pase ambos, documentando el cambio en el reporte. NO relajar los asserts.

- [ ] **Step 5: Commit**

```bash
git add calipso/mapa/urbanismo.py calipso/mapa/__init__.py test_mapa_urbanismo.py
git commit -m "feat(mapa): urbanismo — afinidad, repulsion y anclaje por antiguedad"
```

---

### Task 4: El endpoint

**Files:**
- Modify: `calipso/server.py`
- Test: `test_mapa_server.py`

**Interfaces:**
- Consumes: `ciudad.ciudad(...)`, `urbanismo.urbanizar(...)`, y del server la infraestructura de economía que ya existe: `_ECO_BASE`, `_economia()`, `_eco_ahora()`, `_eco_candado`, `_EcoPagador`.
- Produces: `GET /api/mapa/ciudad` → `{"activa": false}` sin economía, o `{"activa": true, "ciudad": {...}}` donde cada edificio trae además `x` e `y`.

- [ ] **Step 1: Write the failing tests**

```python
# test_mapa_server.py
"""Tests del endpoint del mapa (patron TestClient + cookie del repo)."""
import json
import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso.economia import departamentos as deps
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("mercado", deps.ZONA_FABRICA))
    r.alta(deps.Departamento("curiosos", deps.ZONA_FABRICA))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    k.acunar("2026-08-25T09:00:00", "2026-W35", "dep:mercado", 50_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_ciudad_responde_con_coordenadas(cliente):
    r = cliente.get("/api/mapa/ciudad")
    assert r.status_code == 200
    body = r.json()
    assert body["activa"] is True
    edis = {e["id"]: e for e in body["ciudad"]["edificios"]}
    assert edis["dep:mercado"]["saldo_mm"] == 50_000
    assert edis["dep:mercado"]["tamano"] == 3
    for e in edis.values():
        assert isinstance(e["x"], int) and isinstance(e["y"], int)


def test_ciudad_es_estable_entre_llamadas(cliente):
    """Invariante 2: el mapa no se mueve solo entre dos requests."""
    uno = cliente.get("/api/mapa/ciudad").json()
    dos = cliente.get("/api/mapa/ciudad").json()
    assert uno["ciudad"]["edificios"] == dos["ciudad"]["edificios"]


def test_sin_economia_responde_inactiva(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / "vacio")
    c = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})
    assert c.get("/api/mapa/ciudad").json() == {"activa": False}


def test_sin_auth_rechaza(cliente):
    c = TestClient(srv.app)
    assert c.get("/api/mapa/ciudad",
                 follow_redirects=False).status_code in (302, 401, 403)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_server.py -v`
Expected: FAIL con 404 en `/api/mapa/ciudad`

- [ ] **Step 3: Write minimal implementation**

Agregar a `calipso/server.py`, después de la sección de economía (leer primero cómo están escritos `api_eco_tablero` y `_economia()` y seguir ese patrón exacto):

```python
# --------------------------------------------------------------------------
# MAPA (spec 2026-08-25): el modelo de ciudad
# --------------------------------------------------------------------------
try:
    from calipso.economia import capacidad as _mapa_cap
    from calipso.mapa import ciudad as _mapa_ciudad
    from calipso.mapa import urbanismo as _mapa_urbanismo
except Exception:  # el mapa no esta disponible: el endpoint responde inactivo
    _mapa_ciudad = None
    _mapa_urbanismo = None
    _mapa_cap = None


@app.get("/api/mapa/ciudad")
def api_mapa_ciudad() -> dict:
    if _mapa_ciudad is None:
        return {"activa": False}
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    _, semana = _eco_ahora()
    # lector serializado: el libro se repara truncando, no se lee a medio escribir
    with _eco_candado(p0.ruta_libro):
        eco = _economia()
        m = eco["pagador"].mercado_fresco()
        asientos = m.k.libro.asientos()
        ops = _mapa_cap.semanas_operativas(asientos)
        minutos = eco["reloj"].minutos_por_categoria(ops[-4:]) if ops else {}
        modelo = _mapa_ciudad.ciudad(
            asientos, m.registro, eco["bus"], eco["cola"], semana,
            minutos_empleo=minutos.get("empleo", 0))
    posiciones = _mapa_urbanismo.urbanizar(modelo["edificios"],
                                           modelo["calles"])
    for e in modelo["edificios"]:
        x, y = posiciones.get(e["id"], (0, 0))
        e["x"], e["y"] = x, y
    return {"activa": True, "ciudad": modelo}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_server.py -v`
Expected: PASS (4 tests).

Suite completa — los 13 de economía más los 3 nuevos:
`/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_libro.py test_economia_kernel.py test_economia_pt.py test_economia_capacidad.py test_economia_mercado.py test_economia_bus.py test_economia_eficiencia.py test_economia_cierre.py test_economia_frontera.py test_economia_pagador.py test_economia_server.py test_economia_simulacion.py test_mapa_ciudad.py test_mapa_urbanismo.py test_mapa_server.py test_resource_dispatcher.py -v` — todo verde.

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py test_mapa_server.py
git commit -m "feat(mapa): endpoint de ciudad — modelo con coordenadas ya calculadas"
```

---

## Qué queda para los planes siguientes (NO implementar acá)

- **Plan 2 — El cliente:** `/fabrica` con render pixel de perspectiva forzada, cámara de tres niveles con paneo libre y `volarA`, los tres paneles (dos pestañas en el teléfono), la barra de compuertas, el hover con la ficha económica, la PWA, y el acoplamiento chat↔mapa (la marca `⟦foco:x⟧` y el departamento como contexto y pagador).
- **Plan 3 — El pulso:** `calipso/mapa/pulso.py` con los anillos en memoria, la instrumentación de `orchestrator.py`, `dispatch.py` y el chat, el `WS /ws/mapa`, el interior del departamento con sus empleados, y el panel central convertido en el razonamiento de un agente (runtime, tokens, diff).
