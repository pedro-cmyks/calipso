# Plan 3 del mapa RTS — el pulso, el acoplamiento y el interior

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que la fábrica se vea viva y se pueda operar hablando: los agentes que corren publican lo que hacen y aparecen trabajando en el mapa, decir "miremos a Atlas" mueve la cámara, tocar un edificio contextualiza a Calipso y hace que esa billetera pague, y acercarse a un departamento deja ver adentro quién está pensando qué.

**Architecture:** Tres piezas nuevas del lado del servidor, todas chicas y puras salvo la frontera: **el pulso** (un anillo de eventos en memoria, efímero, que no es fuente de verdad), **el filtro de foco** (saca la marca de control del stream antes de que Pedro la lea) y **la ficha** (convierte un edificio del modelo de ciudad en un bloque de contexto y en una cuenta pagadora). Un `WS /ws/mapa` los publica sondeando el anillo con un cursor. Del lado del cliente, un módulo de pulso con reductor puro, un módulo de interior con la aritmética del umbral y los escritorios, y cableado en `app.js`. El modelo de ciudad, la economía y la UI vieja no cambian de comportamiento.

**Tech Stack:** Python 3.14 (biblioteca estándar + FastAPI/Starlette ya instalados), pytest para el servidor, JavaScript ES2022 sin dependencias, Canvas 2D, `node --test` de Node 22.

**Spec:** `docs/superpowers/specs/2026-08-25-mapa-rts-design.md` — este plan implementa las secciones **5** (el pulso), **6** (el canal `WS /ws/mapa`), **8** (el acoplamiento) y **9** (entrar a un departamento), más los dos residuales que la sección 12 ter dejó explícitamente para acá.

## Global Constraints

- **La capa viva es efímera y no es fuente de verdad** (invariante 5). El pulso vive en memoria, se pierde al reiniciar y jamás contradice al libro. Ninguna tarea de este plan escribe el pulso a disco.
- **El mapa nunca escribe en el libro por su cuenta** (invariante 4). La única escritura que este plan agrega es el cobro del turno de chat a la cuenta pagadora, que es una acción explícita de Pedro (eligió el departamento) y pasa por el `Pagador` que ya existe, con su candado.
- **La conversación es siempre con Calipso** (invariante 7). El departamento es contexto y pagador, no otro interlocutor. Tocar un empleado abre su razonamiento en modo lectura.
- **El pulso no es el bus.** `calipso/economia/bus.py` lleva las propuestas y se persiste; el pulso no. En código, comentarios y commits se lo llama siempre "el pulso".
- **Cero dependencias nuevas.** Ni npm, ni bundler, ni framework, ni paquete de Python. Todo con lo que ya está instalado.
- **Cero archivos de imagen.** El interior se dibuja por código desde la paleta, igual que el exterior.
- **Nada de emojis** en código, tests, commits, documentos ni en la interfaz. Texto plano o símbolos tipográficos.
- **Español** en nombres, comentarios, mensajes de test y de commit. Sin tildes en los mensajes de commit (el repo ya viene así).
- **Determinismo del dibujo**: el mismo modelo produce el mismo bitmap. Nada de `Math.random()` ni de `Date.now()` dentro de la generación de sprites. El pulso sí tiene reloj, pero **inyectado** (`ahora=time.time` por parámetro) para que los tests envejezcan un agente sin dormir diez minutos.
- **Nunca bloquear el event loop.** Todo lo que toma el candado del libro (cobrar, derivar la ciudad) va en `asyncio.to_thread`.
- Correr los tests siempre con `/var/home/pedro/calipso/.venv/bin/python -m pytest` (nunca `pytest` a secas). Los tests del cliente los corre `test_fabrica_js.py` a través de `node --test`.
- La UI vieja (`/`, `calipso/web/index.html`) **no se toca**. Sí se beneficia del filtro de foco, porque vive en el `/ws/chat` que las dos comparten.
- `calipso/server.py` tiene comentarios viejos con mojibake (`ÃƒÂ¡`). **No arreglarlos en este plan**: ensucia los diffs. El código nuevo va en UTF-8 limpio.

---

## Estructura de archivos

| archivo | responsabilidad |
|---|---|
| `calipso/mapa/pulso.py` | **NUEVO**. El anillo de eventos en memoria: publicar, el envoltorio `agente()`, la vista `empleados()` y el cursor `desde()` que alimenta el WebSocket. Reloj inyectado. |
| `calipso/mapa/foco.py` | **NUEVO**. El filtro que saca `⟦foco:atlas⟧` de un stream partido en trozos arbitrarios. Puro, sin estado global. |
| `calipso/mapa/ficha.py` | **NUEVO**. De un edificio del modelo de ciudad a un bloque de contexto para el prompt, y de un id de edificio a una cuenta pagadora. Puro. |
| `calipso/economia/pagador.py` | **MODIFICAR**. Se le suma `suscripcion_de_cliente()`, que hoy está copiada a mano en `dispatch.py`. |
| `dispatch.py` | **MODIFICAR**. Usa ese helper en vez de su copia. |
| `calipso/prompt_compiler.py` | **MODIFICAR**. Una línea en el contrato interno: cómo y cuándo emitir la marca de foco. |
| `calipso/server.py` | **MODIFICAR**. `WS /ws/mapa`; `_ciudad_modelo()` extraído del endpoint; el departamento en foco en `/ws/chat`; el filtro de foco sobre los chunks; el cobro del turno; la instrumentación del pulso. |
| `calipso/web/fabrica/pulso.js` | **NUEVO**. Cliente del `/ws/mapa`: reductor puro de eventos más el socket que lo alimenta, con reconexión. |
| `calipso/web/fabrica/interior.js` | **NUEVO**. La aritmética de entrar: umbral de zoom, opacidad del techo, grilla de escritorios, qué escritorio hay bajo un punto. |
| `calipso/web/fabrica/sprites.js` | **MODIFICAR**. `interiorSprite()`: el mismo edificio sin techo y con escritorios. |
| `calipso/web/fabrica/paleta.js` | **MODIFICAR**. Los índices del interior (piso, escritorio, ocupado). |
| `calipso/web/fabrica/mapa.js` | **MODIFICAR**. El cruce de fundido entre exterior e interior. |
| `calipso/web/fabrica/paneles.js` | **MODIFICAR**. El texto del popup del empleado, la barra de costo corriendo y la etiqueta del departamento en foco. |
| `calipso/web/fabrica/chat.js` | **MODIFICAR**. Mandar el departamento en el paquete, cargar el historial de otro chat, exponer el costo del turno. |
| `calipso/web/fabrica/app.js` | **MODIFICAR**. El cableado de todo lo anterior. |
| `calipso/web/fabrica/index.html` | **MODIFICAR**. Los nodos nuevos: etiqueta de foco, barra de costo, panel de razonamiento, popup del empleado. |
| `calipso/web/fabrica/estilo.css` | **MODIFICAR**. Los estilos de esos nodos. |
| `calipso/web/sw.js` | **MODIFICAR**. Los dos módulos nuevos entran en el SHELL. `test_mapa_server.py` deriva la lista esperada de los archivos reales del directorio: un `.js` nuevo que no esté en el SHELL pone la suite en rojo. |
| `test_mapa_pulso.py` | **NUEVO**. Tests del anillo, la vista y el envoltorio. |
| `test_mapa_ws.py` | **NUEVO**. Tests del `WS /ws/mapa` con `TestClient`. |
| `test_mapa_foco.py` | **NUEVO**. Tests del filtro de la marca. |
| `test_mapa_acoplamiento.py` | **NUEVO**. Tests de la ficha, la cuenta pagadora y el cobro del turno contra una economía de verdad. |
| `calipso/web/fabrica/pulso.test.js`, `interior.test.js` | **NUEVO**. |
| `calipso/web/fabrica/arranque.test.js`, `chat.test.js`, `paneles.test.js`, `lienzo.test.js` | **MODIFICAR**. |

**Contrato de un evento del pulso** (lo que el servidor manda por el WS y lo que el cliente reduce):

```
{seq, ts, agente_id, departamento, trabajo, rol, modelo, evento, ...extras}
```

`evento` es uno de `inicio | razonando | herramienta | tokens | diff | fin | foco`. Los extras por tipo: `razonando` lleva `texto`; `herramienta` lleva `nombre` y `resumen`; `tokens` lleva `tokens_in`, `tokens_out` y `costo_mm` **acumulados** (no incrementales); `diff` lleva `ruta` y `diff`; `fin` lleva `runtime_ms` y `resultado`. El `foco` no tiene agente: va con `agente_id: null` y el `departamento` al que hay que volar. El WS manda además un frame `{"evento": "latido", "seq": N}` cada diez segundos, que el cliente ignora salvo para saber que el socket sigue vivo.

**Contrato de un empleado** (lo que llena el escritorio y el popup):

```
{agente_id, rol, modelo, trabajo, estado, runtime_ms, tokens_in, tokens_out, costo_mm, diff, texto}
```

`estado` es `razonando | esperando | liberado | inactivo`. `diff` es `{ruta, diff}` o `null`.

---

### Task 1: El pulso

El anillo de eventos en memoria, con su vista derivada y su envoltorio. Nada de red y nada de disco: este es el módulo entero que la sección 5 del spec describe, y se puede testear sin levantar el servidor.

**Files:**
- Create: `calipso/mapa/pulso.py`
- Test: `test_mapa_pulso.py`

**Interfaces:**
- Consumes: nada. El módulo no importa economía ni FastAPI.
- Produces:
  - `Pulso(ahora=time.time, por_agente=200, recientes=50, flujo=500, inactivo_s=600)`
  - `Pulso.publicar(agente_id: str | None, evento: str, **campos) -> dict`
  - `Pulso.agente(agente_id, departamento=None, trabajo=None, rol=None, modelo=None)` — context manager que da un mango con `.razonando(texto)`, `.herramienta(nombre, resumen)`, `.tokens(tokens_in, tokens_out, costo_mm)`, `.diff(ruta, diff)` y el atributo `.resultado`
  - `Pulso.enfocar(departamento: str) -> dict`
  - `Pulso.eventos(agente_id) -> list[dict]`
  - `Pulso.desde(seq: int) -> tuple[int, list[dict]]`
  - `Pulso.empleados(departamento: str) -> list[dict]`
  - `estado_de(eventos, ahora, inactivo_s=600) -> str`
  - `resumen(eventos, ahora, inactivo_s=600) -> dict`
  - `EL_PULSO` — la instancia del proceso.

- [ ] **Step 1: Escribir el test de las dos funciones puras**

En `test_mapa_pulso.py`:

```python
"""Tests del pulso: la capa viva del mapa (spec seccion 5)."""
from calipso.mapa import pulso as p


def ev(evento, ts, **campos):
    """Un evento como el que arma `publicar`, para probar las derivadas."""
    return {"seq": 0, "ts": ts, "agente_id": "a1", "departamento": "dep:atlas",
            "trabajo": None, "rol": "scout", "modelo": "sonnet",
            "evento": evento, **campos}


def test_el_estado_se_deriva_del_ultimo_evento():
    """Un agente no declara su estado: se lo lee de lo que hizo."""
    assert p.estado_de([], 100.0) == "esperando"
    assert p.estado_de([ev("inicio", 100.0)], 101.0) == "esperando"
    assert p.estado_de([ev("razonando", 100.0, texto="hola")], 101.0) == "razonando"
    assert p.estado_de([ev("herramienta", 100.0, nombre="grep",
                           resumen="3 hits")], 101.0) == "razonando"
    assert p.estado_de([ev("fin", 100.0, runtime_ms=5, resultado="ok")],
                       101.0) == "liberado"


def test_el_que_dejo_de_publicar_se_marca_inactivo():
    """Spec: diez minutos sin eventos y el escritorio queda vacio. El corte
    es contra el reloj que se le pasa, no contra el del sistema."""
    eventos = [ev("razonando", 100.0, texto="pensando")]
    assert p.estado_de(eventos, 100.0 + 599, inactivo_s=600) == "razonando"
    assert p.estado_de(eventos, 100.0 + 601, inactivo_s=600) == "inactivo"
    # pero un agente ya liberado no se vuelve inactivo con el tiempo: se
    # solto, que es una cosa distinta de haberse colgado
    fin = [ev("fin", 100.0, runtime_ms=5, resultado="ok")]
    assert p.estado_de(fin, 100.0 + 9_999, inactivo_s=600) == "liberado"


def test_los_tokens_son_acumulados_no_incrementales():
    """El evento `tokens` trae el TOTAL. Sumar los eventos contaria dos
    veces el mismo consumo y el popup mostraria el doble de lo gastado."""
    eventos = [ev("inicio", 100.0),
               ev("tokens", 101.0, tokens_in=100, tokens_out=10, costo_mm=5),
               ev("tokens", 102.0, tokens_in=300, tokens_out=40, costo_mm=17)]
    r = p.resumen(eventos, 103.0)
    assert (r["tokens_in"], r["tokens_out"], r["costo_mm"]) == (300, 40, 17)


def test_el_resumen_junta_el_razonamiento_y_el_ultimo_diff():
    eventos = [ev("inicio", 100.0),
               ev("razonando", 100.5, texto="mirando "),
               ev("razonando", 100.9, texto="el libro"),
               ev("diff", 101.0, ruta="a.py", diff="- viejo\n+ nuevo"),
               ev("diff", 102.0, ruta="b.py", diff="- otro\n+ nuevo")]
    r = p.resumen(eventos, 103.0)
    assert r["texto"] == "mirando el libro"
    assert r["diff"] == {"ruta": "b.py", "diff": "- otro\n+ nuevo"}
    # sin evento `fin`, el runtime se mide de punta a punta de lo publicado
    assert r["runtime_ms"] == 2000
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_pulso.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'calipso.mapa.pulso'`

- [ ] **Step 3: Escribir el módulo con las funciones puras**

Crear `calipso/mapa/pulso.py`:

```python
"""
calipso/mapa/pulso.py — La capa viva.

Un anillo de eventos en memoria donde cada agente que corre publica lo que
hace. Nada de esto se persiste y nada de esto es fuente de verdad: si el
pulso dice que un departamento gasto y el libro no lo tiene asentado, manda
el libro (invariante 5 del spec).

Este modulo NO es el bus de la economia (`calipso/economia/bus.py`, que
lleva las propuestas y si se persiste). Se lo llama siempre "el pulso".

El reloj entra inyectado para que un test pueda envejecer un agente diez
minutos sin dormir diez minutos.
"""
from __future__ import annotations

import contextlib
import threading
import time
from collections import deque

EVENTOS = ("inicio", "razonando", "herramienta", "tokens", "diff", "fin",
           "foco")
IDENTIDAD = ("departamento", "trabajo", "rol", "modelo")

POR_AGENTE = 200      # eventos que guarda cada agente
RECIENTES = 50        # agentes que se recuerdan
FLUJO = 500           # eventos que alcanza a recibir un cliente que llega tarde
INACTIVO_S = 600      # diez minutos sin publicar: el escritorio queda vacio


def _ultimo(eventos: list[dict], evento: str) -> dict | None:
    for e in reversed(eventos):
        if e["evento"] == evento:
            return e
    return None


def estado_de(eventos: list[dict], ahora: float,
              inactivo_s: float = INACTIVO_S) -> str:
    """razonando | esperando | liberado | inactivo.

    Un agente liberado se queda liberado por mas que pase el tiempo: que lo
    hayan soltado es una cosa distinta de que se haya colgado, y en el mapa
    se ven distinto (escritorio vacio con rastro contra escritorio mudo)."""
    if not eventos:
        return "esperando"
    ultimo = eventos[-1]
    if ultimo["evento"] == "fin":
        return "liberado"
    if ahora - ultimo["ts"] > inactivo_s:
        return "inactivo"
    if ultimo["evento"] in ("razonando", "herramienta"):
        return "razonando"
    return "esperando"


def _runtime_ms(eventos: list[dict]) -> int:
    fin = _ultimo(eventos, "fin")
    if fin is not None and fin.get("runtime_ms") is not None:
        return int(fin["runtime_ms"])
    if not eventos:
        return 0
    return round((eventos[-1]["ts"] - eventos[0]["ts"]) * 1000)


def resumen(eventos: list[dict], ahora: float,
            inactivo_s: float = INACTIVO_S) -> dict:
    """Lo que llena el popup del empleado."""
    tok = _ultimo(eventos, "tokens") or {}
    dif = _ultimo(eventos, "diff")
    return {
        "estado": estado_de(eventos, ahora, inactivo_s),
        "runtime_ms": _runtime_ms(eventos),
        # el evento `tokens` trae el acumulado, no el incremento: se toma el
        # ultimo, nunca la suma
        "tokens_in": tok.get("tokens_in", 0),
        "tokens_out": tok.get("tokens_out", 0),
        "costo_mm": tok.get("costo_mm", 0),
        "diff": {"ruta": dif["ruta"], "diff": dif["diff"]} if dif else None,
        "texto": "".join(e.get("texto", "") for e in eventos
                         if e["evento"] == "razonando"),
    }
```

- [ ] **Step 4: Correr el test y ver que pasa**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_pulso.py -q`
Expected: PASS (4 tests)

- [ ] **Step 5: Escribir el test del anillo**

Agregar a `test_mapa_pulso.py`:

```python
class Reloj:
    """Un reloj que avanza cuando se lo dice el test, no cuando pasa el
    tiempo de verdad."""

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def avanzar(self, s):
        self.t += s


def test_la_identidad_se_hereda_del_inicio():
    """Cada evento sale con departamento, rol y modelo aunque el que
    publica solo mande el texto: el cliente indexa por departamento y un
    evento sin departamento no tiene escritorio donde caer."""
    reloj = Reloj()
    pu = p.Pulso(ahora=reloj)
    pu.publicar("a1", "inicio", departamento="dep:atlas", rol="scout",
                modelo="sonnet")
    ev = pu.publicar("a1", "razonando", texto="mirando")
    assert ev["departamento"] == "dep:atlas"
    assert ev["rol"] == "scout" and ev["modelo"] == "sonnet"
    assert ev["seq"] == 2 and ev["ts"] == 1000.0


def test_los_anillos_no_crecen_sin_limite():
    """Spec: los anillos son de tamano fijo. Un proceso que corre una semana
    no puede quedarse con todo lo que paso en la semana."""
    pu = p.Pulso(ahora=Reloj(), por_agente=3, recientes=2, flujo=4)
    pu.publicar("a1", "inicio", departamento="dep:atlas")
    for i in range(10):
        pu.publicar("a1", "razonando", texto=str(i))
    assert len(pu.eventos("a1")) == 3
    assert [e["texto"] for e in pu.eventos("a1")] == ["7", "8", "9"]
    # y el anillo de agentes tambien: al entrar el tercero, el primero se va
    # ENTERO (sus eventos tambien, o el diccionario crece igual)
    pu.publicar("a2", "inicio", departamento="dep:atlas")
    pu.publicar("a3", "inicio", departamento="dep:atlas")
    assert pu.recientes() == ["a3", "a2"]
    assert pu.eventos("a1") == []


def test_el_cursor_entrega_lo_nuevo_en_orden():
    """Es el contrato del WebSocket: el cliente guarda un numero y pregunta
    que paso despues de ese numero."""
    pu = p.Pulso(ahora=Reloj())
    pu.publicar("a1", "inicio", departamento="dep:atlas")
    pu.publicar("a1", "razonando", texto="uno")
    cursor, nuevos = pu.desde(0)
    assert [e["evento"] for e in nuevos] == ["inicio", "razonando"]
    assert cursor == 2
    cursor, nuevos = pu.desde(cursor)
    assert nuevos == [] and cursor == 2
    pu.publicar("a1", "razonando", texto="dos")
    _, nuevos = pu.desde(cursor)
    assert [e["texto"] for e in nuevos] == ["dos"]


def test_el_foco_viaja_por_el_mismo_canal_sin_agente():
    pu = p.Pulso(ahora=Reloj())
    ev = pu.enfocar("dep:atlas")
    assert ev["evento"] == "foco" and ev["agente_id"] is None
    assert ev["departamento"] == "dep:atlas"
    assert pu.desde(0)[1] == [ev]


def test_el_envoltorio_abre_y_cierra_solo():
    reloj = Reloj()
    pu = p.Pulso(ahora=reloj)
    with pu.agente("a1", departamento="dep:atlas", rol="scout",
                   modelo="sonnet") as mango:
        reloj.avanzar(1.5)
        mango.razonando("pensando")
        mango.tokens(100, 20, 7)
    tipos = [e["evento"] for e in pu.eventos("a1")]
    assert tipos == ["inicio", "razonando", "tokens", "fin"]
    fin = pu.eventos("a1")[-1]
    assert fin["runtime_ms"] == 1500 and fin["resultado"] == "ok"


def test_un_agente_que_revienta_igual_se_cierra_y_lo_dice():
    """Sin esto, un agente que falla queda razonando para siempre en el
    mapa y el escritorio nunca se libera."""
    pu = p.Pulso(ahora=Reloj())
    try:
        with pu.agente("a1", departamento="dep:atlas"):
            raise RuntimeError("se cayo el backend")
    except RuntimeError:
        pass
    fin = pu.eventos("a1")[-1]
    assert fin["evento"] == "fin" and fin["resultado"] == "error"


def test_los_empleados_son_los_del_departamento_y_traen_su_resumen():
    reloj = Reloj()
    pu = p.Pulso(ahora=reloj)
    with pu.agente("a1", departamento="dep:atlas", rol="scout") as m:
        m.tokens(100, 20, 7)
    pu.publicar("b1", "inicio", departamento="dep:mercado", rol="vendedor")
    reloj.avanzar(1)
    pu.publicar("a2", "inicio", departamento="dep:atlas", rol="copista")
    empleados = pu.empleados("dep:atlas")
    assert [e["agente_id"] for e in empleados] == ["a2", "a1"]  # el nuevo primero
    assert empleados[0]["estado"] == "esperando"
    assert empleados[1]["estado"] == "liberado"
    assert empleados[1]["tokens_in"] == 100 and empleados[1]["rol"] == "scout"
    assert [e["agente_id"] for e in pu.empleados("dep:mercado")] == ["b1"]
    assert pu.empleados("dep:nadie") == []


def test_un_evento_desconocido_no_entra():
    """El cliente hace un switch sobre el tipo: un tipo inventado se le
    escurre entero y no hay forma de notarlo desde el navegador."""
    pu = p.Pulso(ahora=Reloj())
    try:
        pu.publicar("a1", "pensando_mucho")
    except ValueError as e:
        assert "pensando_mucho" in str(e)
    else:
        raise AssertionError("publicar acepto un evento que no existe")
```

- [ ] **Step 6: Correr los tests y ver que fallan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_pulso.py -q`
Expected: FAIL con `AttributeError: module 'calipso.mapa.pulso' has no attribute 'Pulso'`

- [ ] **Step 7: Escribir el anillo**

Agregar a `calipso/mapa/pulso.py`:

```python
class _Mango:
    """Lo que ve el codigo instrumentado. Agregar un punto nuevo al pulso
    tiene que ser una linea, no una refactorizacion."""

    def __init__(self, pulso: "Pulso", agente_id: str):
        self._pulso = pulso
        self._id = agente_id
        self.resultado = "ok"

    def razonando(self, texto: str) -> None:
        if texto:
            self._pulso.publicar(self._id, "razonando", texto=texto)

    def herramienta(self, nombre: str, resumen: str = "") -> None:
        self._pulso.publicar(self._id, "herramienta", nombre=nombre,
                             resumen=resumen)

    def tokens(self, tokens_in: int, tokens_out: int, costo_mm: int = 0) -> None:
        self._pulso.publicar(self._id, "tokens", tokens_in=tokens_in,
                             tokens_out=tokens_out, costo_mm=costo_mm)

    def diff(self, ruta: str, diff: str) -> None:
        self._pulso.publicar(self._id, "diff", ruta=ruta, diff=diff)


class Pulso:
    """Tres estructuras: los eventos de cada agente (para el popup), el
    orden de los agentes recientes (para saber a quien olvidar) y el flujo
    global (para el que se conecta y quiere ver lo que ya paso).

    Todo bajo un lock: los agentes publican desde hilos de trabajo
    (`asyncio.to_thread`) y el WebSocket lee desde el event loop."""

    def __init__(self, ahora=time.time, por_agente: int = POR_AGENTE,
                 recientes: int = RECIENTES, flujo: int = FLUJO,
                 inactivo_s: float = INACTIVO_S):
        self._ahora = ahora
        self._n = por_agente
        self._inactivo_s = inactivo_s
        self._por_agente: dict[str, deque] = {}
        self._orden: deque = deque(maxlen=recientes)
        self._flujo: deque = deque(maxlen=flujo)
        self._fichas: dict[str, dict] = {}
        self._seq = 0
        self._lock = threading.Lock()

    # -- publicar ----------------------------------------------------------
    def publicar(self, agente_id: str | None, evento: str, **campos) -> dict:
        if evento not in EVENTOS:
            raise ValueError(f"evento desconocido: {evento!r}")
        with self._lock:
            self._seq += 1
            ident = dict(self._fichas.get(agente_id, {})) if agente_id else {}
            for k in IDENTIDAD:
                valor = campos.pop(k, None)
                if valor is not None:
                    ident[k] = valor
            if agente_id:
                self._fichas[agente_id] = ident
            ev = {"seq": self._seq, "ts": round(self._ahora(), 3),
                  "agente_id": agente_id, "evento": evento,
                  "departamento": ident.get("departamento"),
                  "trabajo": ident.get("trabajo"),
                  "rol": ident.get("rol"), "modelo": ident.get("modelo"),
                  **campos}
            self._flujo.append(ev)
            if agente_id:
                anillo = self._por_agente.get(agente_id)
                if anillo is None:
                    # el agente entra: si el anillo de agentes esta lleno, el
                    # mas viejo se va con TODO lo suyo. Si no, los dos
                    # diccionarios crecen para siempre y el anillo no sirve
                    # de nada
                    if len(self._orden) == self._orden.maxlen:
                        viejo = self._orden[0]
                        self._por_agente.pop(viejo, None)
                        self._fichas.pop(viejo, None)
                    anillo = self._por_agente[agente_id] = deque(maxlen=self._n)
                    self._orden.append(agente_id)
                anillo.append(ev)
            return ev

    def enfocar(self, departamento: str) -> dict:
        """La camara mira para alla. Viaja por el mismo canal que el resto
        para que el cliente tenga un solo cursor y un solo reductor."""
        return self.publicar(None, "foco", departamento=departamento)

    @contextlib.contextmanager
    def agente(self, agente_id: str, departamento: str | None = None,
               trabajo: str | None = None, rol: str | None = None,
               modelo: str | None = None):
        arranque = self._ahora()
        self.publicar(agente_id, "inicio", departamento=departamento,
                      trabajo=trabajo, rol=rol, modelo=modelo)
        mango = _Mango(self, agente_id)
        try:
            yield mango
        except BaseException:
            mango.resultado = "error"
            raise
        finally:
            # el `fin` sale SIEMPRE: un agente que revienta y queda
            # razonando para siempre deja el escritorio ocupado por un
            # fantasma
            self.publicar(agente_id, "fin",
                          runtime_ms=round((self._ahora() - arranque) * 1000),
                          resultado=mango.resultado)

    # -- leer --------------------------------------------------------------
    def eventos(self, agente_id: str) -> list[dict]:
        with self._lock:
            return list(self._por_agente.get(agente_id, ()))

    def recientes(self) -> list[str]:
        """Del mas nuevo al mas viejo."""
        with self._lock:
            return list(reversed(self._orden))

    def desde(self, seq: int = 0) -> tuple[int, list[dict]]:
        """Lo que paso despues de `seq`, y el cursor nuevo.

        Si entre dos consultas pasaron mas eventos de los que el flujo
        guarda, los del medio se pierden: el pulso es efimero y el cliente
        se entera del estado igual por el proximo evento de cada agente."""
        with self._lock:
            return self._seq, [e for e in self._flujo if e["seq"] > seq]

    def empleados(self, departamento: str) -> list[dict]:
        """La vista derivada de la seccion 5: un escritorio por agente que el
        departamento tiene asignado ahora, el mas nuevo primero."""
        ahora = self._ahora()
        with self._lock:
            ids = [i for i in reversed(self._orden)
                   if self._fichas.get(i, {}).get("departamento") == departamento]
            datos = [(i, dict(self._fichas[i]), list(self._por_agente[i]))
                     for i in ids]
        salida = []
        for agente_id, ficha, eventos in datos:
            salida.append({"agente_id": agente_id, "rol": ficha.get("rol"),
                           "modelo": ficha.get("modelo"),
                           "trabajo": ficha.get("trabajo"),
                           **resumen(eventos, ahora, self._inactivo_s)})
        return salida


EL_PULSO = Pulso()
"""La instancia del proceso. El server publica y lee de esta; los tests se
arman la suya."""
```

- [ ] **Step 8: Correr los tests y ver que pasan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_pulso.py -q`
Expected: PASS (12 tests)

- [ ] **Step 9: Correr la suite entera para confirmar que no se rompió nada**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_*.py test_mapa_*.py test_fabrica_js.py test_resource_dispatcher.py -q`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add calipso/mapa/pulso.py test_mapa_pulso.py
git commit -m "feat(pulso): el anillo de la capa viva — efimero, con reloj inyectado"
```

---

### Task 2: El canal en vivo — `WS /ws/mapa`

El pulso sale del proceso. El endpoint sondea el anillo con un cursor en vez de que el publicador empuje: los agentes publican desde hilos de trabajo, y meter mano en el event loop desde otro hilo es la clase de cosa que anda hasta que no. El precio es un cuarto de segundo de latencia para mirar pensar a un agente, que no se nota.

**Files:**
- Modify: `calipso/server.py` (sección nueva, junto a la del mapa)
- Test: `test_mapa_ws.py`

**Interfaces:**
- Consumes: `calipso.mapa.pulso.Pulso` y `EL_PULSO` de la Task 1; `_valid` y `COOKIE`, que ya existen en `server.py`.
- Produces: `WS /ws/mapa`, que emite los eventos del pulso tal cual y un `{"evento": "latido", "seq": N}` cada diez segundos. `srv.EL_PULSO` queda como atributo de módulo para que los tests lo puedan reemplazar.

- [ ] **Step 1: Escribir el test**

Crear `test_mapa_ws.py`:

```python
"""Tests del WS del pulso (spec seccion 6). Patron TestClient del repo."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import calipso.server as srv
from calipso.mapa import pulso as p


@pytest.fixture
def cliente(monkeypatch):
    # un pulso limpio por test: EL_PULSO es del proceso y dos tests que
    # comparten anillo se contaminan segun el orden en que corran
    monkeypatch.setattr(srv, "EL_PULSO", p.Pulso())
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_el_que_llega_tarde_recibe_lo_que_el_anillo_todavia_guarda(cliente):
    """Un agente arranco antes de que Pedro abriera el mapa. Si el WS
    mandara solo lo que pase de ahora en adelante, el escritorio quedaria
    vacio hasta el proximo evento, que puede tardar minutos."""
    srv.EL_PULSO.publicar("a1", "inicio", departamento="dep:atlas",
                          rol="scout", modelo="sonnet")
    with cliente.websocket_connect("/ws/mapa") as ws:
        ev = ws.receive_json()
    assert ev["agente_id"] == "a1" and ev["evento"] == "inicio"
    assert ev["departamento"] == "dep:atlas"


def test_lo_que_se_publica_despues_tambien_llega(cliente):
    with cliente.websocket_connect("/ws/mapa") as ws:
        srv.EL_PULSO.publicar("a1", "inicio", departamento="dep:atlas")
        assert ws.receive_json()["evento"] == "inicio"
        srv.EL_PULSO.publicar("a1", "razonando", texto="mirando el libro")
        segundo = ws.receive_json()
    assert segundo["evento"] == "razonando"
    assert segundo["texto"] == "mirando el libro"
    assert segundo["seq"] > 1


def test_el_foco_sale_por_el_mismo_socket(cliente):
    with cliente.websocket_connect("/ws/mapa") as ws:
        srv.EL_PULSO.enfocar("dep:atlas")
        ev = ws.receive_json()
    assert ev == {"seq": 1, "ts": ev["ts"], "agente_id": None,
                  "evento": "foco", "departamento": "dep:atlas",
                  "trabajo": None, "rol": None, "modelo": None}


def test_sin_auth_no_deja_entrar():
    """El auth_guard es middleware HTTP y NO corre para websockets: la
    guarda del socket es la del handler, y este test es lo unico que la
    sostiene."""
    c = TestClient(srv.app)
    with pytest.raises(WebSocketDisconnect):
        with c.websocket_connect("/ws/mapa") as ws:
            ws.receive_json()


def test_el_ws_no_depende_de_la_economia(cliente, tmp_path, monkeypatch):
    """La ciudad puede estar inactiva y el pulso seguir latiendo: son dos
    canales distintos (spec seccion 6, degradacion limpia)."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / "vacio")
    assert cliente.get("/api/mapa/ciudad").json() == {"activa": False}
    srv.EL_PULSO.publicar("a1", "inicio", departamento="dep:atlas")
    with cliente.websocket_connect("/ws/mapa") as ws:
        assert ws.receive_json()["evento"] == "inicio"
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_ws.py -q`
Expected: FAIL — `test_sin_auth_no_deja_entrar` no encuentra la ruta y los demás fallan al conectar.

- [ ] **Step 3: Escribir el endpoint**

En `calipso/server.py`, justo **después** del bloque `try/except` que importa el mapa (el que define `_mapa_ciudad`, `_mapa_urbanismo` y `_mapa_cap`) y **antes** de `@app.get("/api/mapa/ciudad")`:

```python
# --------------------------------------------------------------------------
# EL PULSO (spec 2026-08-25 secciones 5 y 6): la capa viva
# --------------------------------------------------------------------------
try:
    from calipso.mapa import pulso as _pulso_mod
    EL_PULSO = _pulso_mod.EL_PULSO
except Exception:  # sin pulso el mapa sigue mostrando la foto
    _pulso_mod = None
    EL_PULSO = None

SONDEO_S = 0.25
LATIDO_CADA = 40          # sondeos: un latido cada diez segundos


@app.websocket("/ws/mapa")
async def ws_mapa(ws: WebSocket) -> None:
    """El pulso, en vivo.

    Se sondea el anillo con un cursor en vez de que el publicador empuje:
    los agentes publican desde hilos de trabajo (`asyncio.to_thread`) y
    tocar el event loop desde otro hilo es la clase de cosa que anda hasta
    que no. El costo es un cuarto de segundo de latencia para ver pensar a
    un agente."""
    if not _valid(ws.cookies.get(COOKIE)):
        await ws.close(code=1008)   # politica violada: sin token valido
        return
    await ws.accept()
    if EL_PULSO is None:
        await ws.send_json({"evento": "sin-pulso"})
        await ws.close()
        return
    cursor = 0            # cero, no el presente: el que llega tarde recibe
    vueltas = 0           # lo que el anillo todavia guarda
    try:
        while True:
            cursor, nuevos = EL_PULSO.desde(cursor)
            for ev in nuevos:
                await ws.send_json(ev)
            vueltas += 1
            if vueltas % LATIDO_CADA == 0:
                # sin trafico, un socket muerto no se nota hasta el proximo
                # evento, que puede no llegar nunca
                await ws.send_json({"evento": "latido", "seq": cursor})
            await asyncio.sleep(SONDEO_S)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass              # el cliente reconecta solo; el mapa sigue con la foto
```

- [ ] **Step 4: Correr el test y ver que pasa**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_ws.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py test_mapa_ws.py
git commit -m "feat(pulso): el canal en vivo — /ws/mapa con cursor y latido"
```

---

### Task 3: La marca de foco — chat → mapa

Calipso emite `⟦foco:atlas⟧` cuando la conversación pasa a tratar de un departamento. Pedro no la ve: el servidor la retira del stream y la convierte en un vuelo de cámara. El stream llega partido en trozos arbitrarios, así que la marca puede quedar cortada en cualquier lado; el filtro retiene la cola sospechosa hasta poder decidir.

Todo el texto que Pedro lee pasa a salir por un solo objeto, el `Emisor`. Hoy los `{"type": "chunk"}` se mandan desde **siete** lugares de `ws_chat`, de los que cinco llevan texto de un modelo; filtrar en cinco lugares es filtrar en cuatro.

**Files:**
- Create: `calipso/mapa/foco.py`
- Modify: `calipso/prompt_compiler.py` (una línea en el contrato interno)
- Modify: `calipso/server.py` (el `Emisor`, el resolvedor de nombres, y los cinco puntos de envío de `ws_chat`)
- Test: `test_mapa_foco.py`

**Interfaces:**
- Consumes: `Pulso.enfocar()` y `EL_PULSO` (Task 1).
- Produces:
  - `foco.Filtro()` con `.comer(trozo) -> str`, `.cerrar() -> str`, `.tomar_focos() -> list[str]`
  - `foco.ABRE`, `foco.CIERRA`, `foco.MAX_NOMBRE`
  - `server.Emisor(ws, agente_id=None, resolver=None, pulso=None, filtro=None)` con `await .chunk(texto) -> str`, `await .cerrar() -> str` y `.focos`
  - `server._edificios_livianos() -> list[dict]` — `{id, nombre}` de cada departamento, sin tocar el libro
  - `ficha.id_de_nombre(nombre, edificios) -> str | None` (se crea acá porque el resolvedor lo necesita; el resto de `ficha.py` es de la Task 5)

- [ ] **Step 1: Escribir el test del filtro**

Crear `test_mapa_foco.py`:

```python
"""Tests de la marca de foco (spec seccion 8, chat -> mapa)."""
from calipso.mapa import foco


def test_una_marca_entera_desaparece_del_texto():
    f = foco.Filtro()
    assert f.comer("miremos ⟦foco:atlas⟧ un rato") == "miremos  un rato"
    assert f.tomar_focos() == ["atlas"]
    # y tomarlos los consume: la camara no vuela dos veces por lo mismo
    assert f.tomar_focos() == []


def test_la_marca_partida_en_tres_trozos_igual_se_arma():
    """Es el caso real: el stream corta donde se le da la gana, y una marca
    de trece caracteres cae partida a menudo."""
    f = foco.Filtro()
    assert f.comer("vamos a ⟦fo") == "vamos a "
    assert f.comer("co:atl") == ""
    assert f.comer("as⟧ ahora") == " ahora"
    assert f.tomar_focos() == ["atlas"]
    assert f.cerrar() == ""


def test_lo_retenido_que_no_era_marca_se_devuelve_al_cerrar():
    """Un texto que empieza como la marca y no lo es no se puede tragar: si
    la respuesta termina con un corchete raro, Pedro tiene que verlo."""
    f = foco.Filtro()
    assert f.comer("mira este simbolo: ⟦") == "mira este simbolo: "
    assert f.cerrar() == "⟦"
    assert f.tomar_focos() == []


def test_una_marca_que_nunca_cierra_es_texto():
    """Sin tope, un `⟦foco:` sin cierre se come el resto de la respuesta."""
    f = foco.Filtro()
    largo = "x" * (foco.MAX_NOMBRE + 5)
    salida = f.comer("hola ⟦foco:" + largo)
    assert salida == "hola ⟦foco:" + largo
    assert f.tomar_focos() == []


def test_dos_marcas_en_el_mismo_trozo():
    f = foco.Filtro()
    assert f.comer("⟦foco:atlas⟧ y ⟦foco:mercado⟧") == " y "
    assert f.tomar_focos() == ["atlas", "mercado"]


def test_una_marca_vacia_no_enfoca_nada():
    f = foco.Filtro()
    assert f.comer("nada ⟦foco:⟧ aca") == "nada  aca"
    assert f.tomar_focos() == []


def test_el_texto_sin_marcas_pasa_intacto_y_sin_retener_nada():
    f = foco.Filtro()
    assert f.comer("una respuesta comun y corriente") == (
        "una respuesta comun y corriente")
    assert f.cerrar() == ""


def test_limpiar_saca_las_marcas_de_un_texto_entero():
    """Para el acumulado de la ruta de suscripcion, que no es incremental."""
    assert foco.limpiar("hola ⟦foco:atlas⟧ y ⟦foco:mercado⟧ chau") == (
        "hola  y  chau")
    # una marca a medio llegar se deja: el proximo envio trae el texto entero
    assert foco.limpiar("cortada ⟦foco:atl") == "cortada ⟦foco:atl"
    assert foco.limpiar("") == "" and foco.limpiar(None) == ""
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_foco.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'calipso.mapa.foco'`

- [ ] **Step 3: Escribir el filtro**

Crear `calipso/mapa/foco.py`:

```python
"""
calipso/mapa/foco.py — La marca de control, sacada del texto que Pedro lee.

Calipso emite `⟦foco:atlas⟧` cuando la conversacion pasa a tratar de un
departamento. La marca no se ve: este filtro la retira del stream y la
convierte en un foco para la camara (spec seccion 8).

El stream llega partido en trozos arbitrarios y la marca puede quedar
cortada en cualquier lado, asi que el filtro RETIENE la cola sospechosa
hasta poder decidir. `cerrar()` devuelve lo retenido: una marca que nunca
cierra es texto, y tragarsela seria comerse el final de la respuesta.
"""
from __future__ import annotations

import re

ABRE = "⟦foco:"
CIERRA = "⟧"
MAX_NOMBRE = 60      # mas largo que esto no es un departamento, es texto


def _retenible(texto: str) -> int:
    """Cuantos caracteres del final pueden ser el principio de la marca."""
    for k in range(min(len(texto), len(ABRE) - 1), 0, -1):
        if ABRE.startswith(texto[-k:]):
            return k
    return 0


class Filtro:
    """Uno por turno. No es reentrante y no se comparte entre conexiones."""

    def __init__(self):
        self._resto = ""
        self._focos: list[str] = []

    def comer(self, trozo: str) -> str:
        """Devuelve el texto visible del trozo; guarda los focos que vio."""
        buf = self._resto + trozo
        self._resto = ""
        visible = []
        while buf:
            i = buf.find(ABRE)
            if i < 0:
                k = _retenible(buf)
                visible.append(buf[:len(buf) - k] if k else buf)
                self._resto = buf[len(buf) - k:] if k else ""
                break
            visible.append(buf[:i])
            j = buf.find(CIERRA, i + len(ABRE))
            if j < 0:
                if len(buf) - i > len(ABRE) + MAX_NOMBRE:
                    # abrio y no cerro en un nombre plausible: era texto
                    visible.append(buf[i:i + len(ABRE)])
                    buf = buf[i + len(ABRE):]
                    continue
                self._resto = buf[i:]
                break
            nombre = buf[i + len(ABRE):j].strip()
            if nombre:
                self._focos.append(nombre)
            buf = buf[j + len(CIERRA):]
        return "".join(visible)

    def cerrar(self) -> str:
        resto, self._resto = self._resto, ""
        return resto

    def tomar_focos(self) -> list[str]:
        """Los consume: la camara no tiene que volar dos veces por lo mismo."""
        focos, self._focos = self._focos, []
        return focos


_MARCA = re.compile(re.escape(ABRE) + "[^" + re.escape(CIERRA) + "]*"
                    + re.escape(CIERRA))


def limpiar(texto: str) -> str:
    """Saca las marcas COMPLETAS de un texto que ya llego entero.

    El `Filtro` es para un stream partido en trozos; esto es para un
    acumulado que se remanda entero cada tanto (el `partial` de la ruta de
    suscripcion). Sin estado y sin retencion: una marca a medio llegar se
    limpia sola en el envio siguiente."""
    return _MARCA.sub("", texto or "")
```

- [ ] **Step 4: Correr el test y ver que pasa**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_foco.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Escribir el test del emisor y del resolvedor**

Agregar a `test_mapa_foco.py`:

```python
import asyncio

import calipso.server as srv
from calipso import prompt_compiler
from calipso.economia import departamentos as deps
from calipso.mapa import ficha
from calipso.mapa import pulso as p


class WSFalso:
    """Anota lo que se manda, en vez de mandarlo."""

    def __init__(self):
        self.enviados = []

    async def send_json(self, dato):
        self.enviados.append(dato)


def textos(ws):
    return [e["text"] for e in ws.enviados if e.get("type") == "chunk"]


def test_el_nombre_se_resuelve_contra_los_departamentos_que_existen():
    edificios = [{"id": "dep:atlas", "nombre": "atlas"},
                 {"id": "personal:finanzas", "nombre": "finanzas"}]
    assert ficha.id_de_nombre("atlas", edificios) == "dep:atlas"
    assert ficha.id_de_nombre("Atlas", edificios) == "dep:atlas"   # sin caso
    assert ficha.id_de_nombre("dep:atlas", edificios) == "dep:atlas"
    assert ficha.id_de_nombre("finanzas", edificios) == "personal:finanzas"
    # el modelo se puede inventar un departamento: eso no vuela a ningun lado
    assert ficha.id_de_nombre("ministerio", edificios) is None


def test_el_emisor_retira_la_marca_publica_el_foco_y_alimenta_al_pulso():
    ws, pu = WSFalso(), p.Pulso()
    edificios = [{"id": "dep:atlas", "nombre": "atlas"}]
    em = srv.Emisor(ws, agente_id="a1",
                    resolver=lambda n: ficha.id_de_nombre(n, edificios),
                    pulso=pu, filtro=foco.Filtro())

    async def turno():
        salida = ""
        salida += await em.chunk("vamos a ⟦fo")
        salida += await em.chunk("co:atlas⟧ mirar")
        salida += await em.cerrar()
        return salida

    assert asyncio.run(turno()) == "vamos a  mirar"
    # lo que salio por el socket es lo mismo que se devolvio, sin la marca
    assert "".join(textos(ws)) == "vamos a  mirar"
    assert em.focos == ["dep:atlas"]
    # el foco viaja por el pulso, que es lo que el mapa esta escuchando
    eventos = pu.desde(0)[1]
    assert [e["evento"] for e in eventos if e["evento"] == "foco"] == ["foco"]
    assert [e for e in eventos if e["evento"] == "foco"][0]["departamento"] == "dep:atlas"
    # y el razonamiento del turno queda en el anillo del agente
    assert "".join(e.get("texto", "") for e in pu.eventos("a1")) == "vamos a  mirar"


def test_el_emisor_no_manda_chunks_vacios():
    """Un trozo que era pura marca no puede salir como un chunk vacio: la UI
    vieja lo pinta igual y queda un turno con un salto de linea de mas."""
    import asyncio

    ws = WSFalso()
    em = srv.Emisor(ws, filtro=foco.Filtro())
    asyncio.run(em.chunk("⟦foco:atlas⟧"))
    assert textos(ws) == []


def test_el_contrato_interno_le_dice_al_modelo_como_emitir_la_marca():
    """La instruccion vive en el compilador de prompts (spec seccion 8), no
    suelta en un f-string del server. `test_prompt_compiler.py` no lo cubre:
    es de los que pytest no colecta (tiene main(), no tests)."""
    texto = prompt_compiler.internal_contract({})
    assert foco.ABRE in texto and foco.CIERRA in texto
    assert "no la ve" in texto or "no se muestra" in texto


def test_el_parcial_de_la_suscripcion_tampoco_muestra_la_marca():
    """El otro camino por el que el texto del modelo llega a Pedro: el
    acumulado que la ruta de suscripcion remanda cada dos segundos."""
    assert srv._limpiar_marcas("corriendo ⟦foco:atlas⟧ todavia") == (
        "corriendo  todavia")
    assert srv._limpiar_marcas("") == ""


def test_los_edificios_livianos_no_tocan_el_libro(tmp_path, monkeypatch):
    """Se lee el registro, que es un JSON chico, no el libro entero: esto
    corre en cada turno de chat para resolver el nombre del foco."""
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    (eco / "libro.jsonl").write_text("", encoding="utf-8")
    (eco / "suscripciones.json").write_text("{}", encoding="utf-8")
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    assert srv._edificios_livianos() == [{"id": "dep:atlas", "nombre": "atlas"},
                                         {"id": "personal:finanzas",
                                          "nombre": "finanzas"}]


def test_sin_economia_no_hay_a_quien_enfocar(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / "vacio")
    assert srv._edificios_livianos() == []
```

**Nada de plugins de pytest**: no hay `pytest-asyncio` en el repo y no se agrega. Lo asíncrono se corre con `asyncio.run` adentro de un test sincrónico, que es lo que ya se puede hacer sin instalar nada.

- [ ] **Step 6: Correr los tests y ver que fallan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_foco.py -q`
Expected: FAIL — no existen `srv.Emisor`, `srv._edificios_livianos` ni `ficha.id_de_nombre`, y el contrato interno todavía no menciona la marca.

- [ ] **Step 7: Escribir `id_de_nombre`**

Crear `calipso/mapa/ficha.py` con lo que hace falta ahora (el resto lo agrega la Task 5):

```python
"""
calipso/mapa/ficha.py — De un edificio a contexto y a una cuenta que paga.

El departamento no es otro interlocutor (invariante 7): es un objetivo del
cerebro. Este modulo hace las dos traducciones que eso necesita — el bloque
de texto que Calipso recibe, y la cuenta que va a pagar el turno — y las
hace puras, sobre el modelo de ciudad que el mapa ya deriva.
"""
from __future__ import annotations


def id_de_nombre(nombre: str, edificios: list[dict]) -> str | None:
    """`atlas` -> `dep:atlas`. None si ese departamento no existe: el modelo
    se puede inventar un nombre y la camara no vuela a la nada."""
    if not nombre:
        return None
    buscado = nombre.strip().lower()
    for e in edificios:
        if e["id"].lower() == buscado or (e.get("nombre") or "").lower() == buscado:
            return e["id"]
    return None
```

- [ ] **Step 8: Escribir el emisor y el resolvedor en el server**

En `calipso/server.py`, agregar `import contextlib` al bloque de imports de la biblioteca estándar (va entre `import base64` y `import datetime`, en orden alfabético).

En el bloque de imports de la economía, sumar `departamentos as _eco_deps`:

```python
    from calipso.economia import (bus as _eco_bus, cola as _eco_cola,
                                  departamentos as _eco_deps,
                                  operacion as _eco_op,
                                  personal as _eco_personal,
                                  reloj as _eco_reloj)
```

y en el `except` de ese mismo bloque agregar `_eco_deps = None` a la lista de nombres que se apagan.

En el bloque `try/except` que importa el mapa, sumar el filtro y la ficha:

```python
try:
    from calipso.economia import capacidad as _mapa_cap
    from calipso.mapa import ciudad as _mapa_ciudad
    from calipso.mapa import ficha as _mapa_ficha
    from calipso.mapa import foco as _mapa_foco
    from calipso.mapa import urbanismo as _mapa_urbanismo
except Exception:  # el mapa no esta disponible: el endpoint responde inactivo
    _mapa_ciudad = None
    _mapa_urbanismo = None
    _mapa_cap = None
    _mapa_ficha = None
    _mapa_foco = None
```

Y después de la sección del pulso (Task 2), antes de `@app.get("/api/mapa/ciudad")`:

```python
def _edificios_livianos() -> list[dict]:
    """`{id, nombre}` de cada departamento registrado, sin abrir el libro.

    Resolver el nombre de un foco corre en cada turno de chat; el registro
    es un JSON de unas lineas y el libro puede ser de megabytes."""
    if _eco_deps is None or _EcoPagador is None:
        return []
    p0 = _EcoPagador.desde_entorno(_ECO_BASE)
    if p0 is None:
        return []
    try:
        registro = _eco_deps.Registro(p0.ruta_registro)
    except Exception:
        return []
    return [{"id": d.cuenta, "nombre": d.nombre} for d in registro.todos()]


def _resolver_foco(nombre: str) -> str | None:
    if _mapa_ficha is None:
        return None
    return _mapa_ficha.id_de_nombre(nombre, _edificios_livianos())


class Emisor:
    """Todo lo que Pedro lee sale por aca.

    Tres cosas en un solo lugar: retirar la marca de foco del texto visible,
    publicar el foco apenas aparece (la camara vuela mientras Calipso sigue
    escribiendo) y darle al pulso lo que se va diciendo. Antes los chunks
    salian desde cinco puntos de `ws_chat`, y filtrar en cinco lugares es
    filtrar en cuatro."""

    def __init__(self, ws, agente_id: str | None = None, resolver=None,
                 pulso=None, filtro=None):
        self.ws = ws
        self.agente_id = agente_id
        self._resolver = resolver or _resolver_foco
        self._pulso = pulso if pulso is not None else EL_PULSO
        self._filtro = filtro if filtro is not None else (
            _mapa_foco.Filtro() if _mapa_foco is not None else None)
        self.focos: list[str] = []

    async def _soltar(self, visible: str) -> str:
        if not visible:
            return ""      # un chunk vacio la UI vieja lo pinta igual
        await self.ws.send_json({"type": "chunk", "text": visible})
        if self._pulso is not None and self.agente_id:
            self._pulso.publicar(self.agente_id, "razonando", texto=visible)
        return visible

    async def chunk(self, texto: str) -> str:
        """Manda lo visible y devuelve exactamente eso, para que el que
        acumula la respuesta acumule lo mismo que Pedro leyo."""
        if self._filtro is None:
            return await self._soltar(texto)
        visible = await self._soltar(self._filtro.comer(texto))
        for nombre in self._filtro.tomar_focos():
            destino = self._resolver(nombre)
            if destino is None:
                continue          # el modelo se invento un departamento
            self.focos.append(destino)
            if self._pulso is not None:
                self._pulso.enfocar(destino)
        return visible

    async def cerrar(self) -> str:
        """Una marca que nunca cerro es texto y Pedro tiene que verlo."""
        if self._filtro is None:
            return ""
        return await self._soltar(self._filtro.cerrar())
```

- [ ] **Step 9: Poner la instrucción en el compilador de prompts**

En `calipso/prompt_compiler.py`, dentro de la lista que devuelve `internal_contract`, después de la línea que empieza con `"Manten una sola voz visible:"`:

```python
        "Cuando la conversacion pase a tratar de un departamento de la fabrica, "
        "emiti una vez la marca ⟦foco:<nombre>⟧ con el nombre exacto del "
        "departamento (atlas, mercado, finanzas). Pedro no la ve: el servidor la "
        "retira del texto y con ella mueve la camara del mapa. Nunca inventes un "
        "nombre y no la repitas mientras el tema no cambie.",
```

- [ ] **Step 10: Correr los tests y ver que pasan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_foco.py -q`
Expected: PASS

- [ ] **Step 11: Pasar los cinco puntos de envío de `ws_chat` por el emisor**

En `calipso/server.py`, adentro de `ws_chat`, **después** del `await ws.send_json({"type": "meta", ...})` que sigue a `_decide` (el que manda `route`, `used`, `model`, `why`, `note`), crear el emisor del turno:

```python
            agente_id = "chat:" + uuid.uuid4().hex[:8]
            emisor = Emisor(ws, agente_id=agente_id)
```

Después, reemplazar los cinco envíos de chunk:

1. En el bucle de la ruta normal (`server.py:2329-2330`, a **24** espacios):
```python
                        full += chunk
                        await ws.send_json({"type": "chunk", "text": chunk})
```
pasa a
```python
                        full += await emisor.chunk(chunk)
```

2. En el bucle del fallback local (`server.py:2412-2413`, adentro del `except`), la misma sustitución **pero a 28 espacios**: ese bucle está un nivel más adentro, así que el texto no es el mismo y un `old_string` copiado del item 1 no lo encuentra. La ventaja colateral es que, al diferir la indentación, cada uno es un anclaje único.
```python
                            full += chunk
                            await ws.send_json({"type": "chunk", "text": chunk})
```
pasa a
```python
                            full += await emisor.chunk(chunk)
```

3. El par de la rama del orquestador (`server.py:2300-2301`) y el de la rama de suscripción (`server.py:2309-2310`) son **byte a byte idénticos**, los dos a 20 espacios: un reemplazo por texto falla por ambigüedad. La sustitución va a las **tres** apariciones —esas dos, más la del fallback entre suscripciones (`server.py:2363-2364`, a 32 espacios)— con `replace_all`, o desambiguando cada una con su línea anterior:
```python
                    usage["completion_tokens"] = len(full.split())
                    await ws.send_json({"type": "chunk", "text": full})
```
pasa a
```python
                    usage["completion_tokens"] = len(full.split())
                    full = await emisor.chunk(full)
```
En las tres, `usage["completion_tokens"]` se calcula **antes** de filtrar, que es lo correcto: los tokens los gastó el modelo escribiendo la marca.

4. Los dos envíos que **no** se tocan son los que escribe el server, no un modelo: el de `goal_objective` (`await ws.send_json({"type": "chunk", "text": reply})`) y el de `HELP_TEXT`. No llevan marcas.

5. La ruta de suscripción manda el texto crudo del modelo por **otro** camino, que no es un chunk: `_run_subscription_text_live` reenvía el acumulado cada dos segundos como `{"type": "process", "action": "running", "partial": ...}` (`server.py:2019-2026`), y la UI vieja lo pinta en su panel de proceso (`calipso/web/index.html`). Ahí la marca se vería. En ese `send_json`, cambiar

```python
                    "partial": partial[-3000:] if partial else "",
```

por

```python
                    "partial": _limpiar_marcas(partial[-3000:]) if partial else "",
```

y poner el helper junto al `Emisor`:

```python
def _limpiar_marcas(texto: str) -> str:
    """El parcial de la suscripcion se remanda ENTERO cada dos segundos, asi
    que no necesita la maquinaria de retencion del Filtro: alcanza con sacar
    las marcas completas. Una marca a medio llegar se limpia sola en el envio
    siguiente, porque el texto se relee desde cero."""
    return _mapa_foco.limpiar(texto) if _mapa_foco is not None else texto
```

Y justo antes del bloque `# 4) registrar costo/uso y avisar`:

```python
            # lo que el filtro venia reteniendo por si era una marca: si la
            # respuesta termino en un corchete suelto, Pedro tiene que verlo
            full += await emisor.cerrar()
```

- [ ] **Step 12: Correr la suite entera**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_*.py test_mapa_*.py test_fabrica_js.py test_resource_dispatcher.py -q`
Expected: PASS

- [ ] **Step 13: Commit**

```bash
git add calipso/mapa/foco.py calipso/mapa/ficha.py calipso/prompt_compiler.py \
        calipso/server.py test_mapa_foco.py
git commit -m "feat(foco): la marca sale del texto y mueve la camara"
```

---

### Task 4: La instrumentación — los agentes publican lo que hacen

Los puntos donde hoy se lanzan agentes empiezan a publicar al pulso. Sin cambio de comportamiento: si el pulso no está, todo sigue igual.

El turno de chat abre y cierra el agente **a mano** en vez de con el envoltorio: envolver el cuerpo del turno significaría re-indentar doscientas cincuenta líneas de `ws_chat` y ensuciar el diff entero. El riesgo de que un turno que revienta deje un agente razonando para siempre lo cubre la regla de inactividad de diez minutos. El equipo dinámico sí usa el envoltorio, que ahí entra justo.

**Files:**
- Modify: `calipso/server.py` (`ws_chat`, `_run_dynamic_team`)
- Test: `test_mapa_ws.py` (se le suman los tests del envoltorio nulo)

**Interfaces:**
- Consumes: `EL_PULSO` (Task 1), `Emisor` (Task 3).
- Produces: `server._pulso_agente(agente_id, **campos)` — context manager que funciona con o sin pulso; `_run_dynamic_team(..., departamento=None)`.

- [ ] **Step 1: Escribir el test del envoltorio nulo**

Agregar a `test_mapa_ws.py`:

```python
def test_el_envoltorio_anda_igual_sin_pulso(monkeypatch):
    """La instrumentacion no puede ser una fuente de errores nueva: si el
    pulso no se pudo importar, el equipo dinamico tiene que correr igual."""
    monkeypatch.setattr(srv, "EL_PULSO", None)
    with srv._pulso_agente("a1", departamento="dep:atlas") as mango:
        mango.razonando("no se publica en ningun lado")
        mango.tokens(1, 2, 3)
        mango.diff("a.py", "- x\n+ y")


def test_el_envoltorio_publica_cuando_hay_pulso(monkeypatch):
    pu = p.Pulso()
    monkeypatch.setattr(srv, "EL_PULSO", pu)
    with srv._pulso_agente("a1", departamento="dep:atlas", rol="scout") as mango:
        mango.razonando("mirando")
    assert [e["evento"] for e in pu.eventos("a1")] == [
        "inicio", "razonando", "fin"]
    assert pu.empleados("dep:atlas")[0]["rol"] == "scout"
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_ws.py -q`
Expected: FAIL con `AttributeError: module 'calipso.server' has no attribute '_pulso_agente'`

- [ ] **Step 3: Escribir el envoltorio**

En `calipso/server.py`, en la sección del pulso (justo después de `LATIDO_CADA`):

```python
class _MangoNulo:
    """Cuando el pulso no se pudo importar, el codigo instrumentado corre
    igual y no se llena de `if EL_PULSO is not None`."""

    resultado = "ok"

    def razonando(self, texto): pass
    def herramienta(self, nombre, resumen=""): pass
    def tokens(self, tokens_in, tokens_out, costo_mm=0): pass
    def diff(self, ruta, diff): pass


_MANGO_NULO = _MangoNulo()


@contextlib.contextmanager
def _pulso_agente(agente_id: str, **campos):
    if EL_PULSO is None:
        yield _MANGO_NULO
        return
    with EL_PULSO.agente(agente_id, **campos) as mango:
        yield mango
```

- [ ] **Step 4: Correr el test y ver que pasa**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_ws.py -q`
Expected: PASS (7 tests)

- [ ] **Step 5: Instrumentar el turno de chat**

En `ws_chat`, donde la Task 3 dejó `agente_id = "chat:" + uuid.uuid4().hex[:8]`, agregar debajo:

```python
            if EL_PULSO is not None:
                # abierto y cerrado a mano: envolver el cuerpo del turno
                # re-indentaria doscientas cincuenta lineas. Si el turno
                # revienta sin cerrar, la regla de inactividad libera el
                # escritorio a los diez minutos
                EL_PULSO.publicar(agente_id, "inicio",
                                  departamento=departamento, rol="calipso",
                                  modelo=model)
```

**Ojo:** `departamento` lo define la Task 5. En esta tarea va literalmente `departamento=None` en el snippet de arriba; la Task 5 lo reemplaza por la variable. La misma advertencia vale para el paso 6.

Y justo después del `await ws.send_json({"type": "cost", ...})`:

```python
            if EL_PULSO is not None:
                EL_PULSO.publicar(agente_id, "tokens",
                                  tokens_in=entry["prompt_tokens"],
                                  tokens_out=entry["completion_tokens"],
                                  costo_mm=0)
                EL_PULSO.publicar(
                    agente_id, "fin",
                    runtime_ms=round((time.perf_counter() - turn_started) * 1000),
                    resultado="ok")
```

(El `costo_mm` real lo llena la Task 5, que es la que sabe cuánto se cobró.)

- [ ] **Step 6: Instrumentar el equipo dinámico**

En `_run_dynamic_team`, agregar el parámetro al final de la firma:

```python
async def _run_dynamic_team(ws: WebSocket, inbox: asyncio.Queue, chat_msg: str,
                            features: dict, base_system: str,
                            verdict: dict,
                            approval_required: bool = False,
                            departamento: str | None = None) -> tuple[str, dict, str | None]:
```

Adentro del `for idx, agent in enumerate(agents, start=1):`, envolver desde el `agent_system = orchestrator.agent_system(...)` hasta el `results.append(result)` con el envoltorio, y publicar lo que el agente produjo:

```python
        agent_system = orchestrator.agent_system(agent, base_system, chat_msg)
        with _pulso_agente(f"{ws_agente_base}:{idx}", departamento=departamento,
                           rol=agent.get("role"),
                           modelo=agent.get("model")) as mango:
            try:
                output, queued = await _run_agent_text(
                    ws, inbox, agent, agent_system, agent["task"])
                queued_msg = queued_msg or queued
            except Exception as e:
                agent["fallback_error"] = str(e)
                try:
                    output = await asyncio.to_thread(
                        _run_backend_text, "local", None, _route_model_name("local"),
                        agent_system, agent["task"], None)
                    agent["fallback_route"] = "local"
                except Exception as e2:
                    output = (
                        f"No pude ejecutar esta subtarea. Ruta original: "
                        f"{agent.get('route')} {agent.get('model') or ''}. "
                        f"Error: {e}. Fallback local: {e2}."
                    )
                    agent["fallback_route"] = "failed"
            # el agente de un equipo no streamea: `_run_backend_text` devuelve
            # el texto entero. Su razonamiento se publica una vez, al final.
            # El incremental existe solo donde existe el stream, que es el
            # turno principal del chat
            mango.razonando(output)
            mango.tokens(len(agent_system) // 4, len(output) // 4, 0)
        result = {**agent, "output": output}
        results.append(result)
```

`ws_agente_base` es un id nuevo al principio de la función, junto a `results: list[dict] = []`:

```python
    ws_agente_base = "equipo:" + uuid.uuid4().hex[:8]
```

Y en la llamada desde `ws_chat`, pasarle el departamento — **con la misma salvedad del paso 5**: en esta tarea la variable `departamento` todavía no existe, así que la llamada se deja como está y el argumento lo agrega la Task 5. El parámetro nuevo tiene default `None`, así que la firma vieja sigue siendo válida:

```python
                    # la Task 5 le agrega aca `departamento=departamento`
                    full, agent_team, queued = await _run_dynamic_team(
                        ws, inbox, chat_msg, features, system, verdict,
                        approval_required=bool(directives.get("force_team")))
```

- [ ] **Step 6b: Publicar el `diff` que deja el borrador**

El spec pide un evento `diff` (sección 5) y que el popup del empleado muestre "el diff de lo que tocó" (sección 9). El único punto del server que hoy produce un diff de verdad es `_run_chat_draft`, que ya lo calcula para mandarlo como `proposal`. Sin este paso, el evento `diff` queda declarado y sin productor, y el campo `toco` del popup nunca se llena.

En `calipso/server.py`, la firma (`server.py:580`):

```python
async def _run_chat_draft(ws, chat_msg: str, file_path: str,
                          agente_id: str | None = None) -> None:
```

y justo después de `diff = _proposal_diff(file_path, new_content)`:

```python
    if EL_PULSO is not None and agente_id:
        # el rastro del agente: es lo que el popup del empleado muestra como
        # "toco" y lo que el panel de razonamiento pinta abajo del texto
        EL_PULSO.publicar(agente_id, "diff", ruta=file_path, diff=diff)
```

En la llamada (`server.py:2244`), pasarle el agente del turno:

```python
                asyncio.ensure_future(_run_chat_draft(ws, chat_msg, _edit_target,
                                                      agente_id))
```

`_run_chat_draft` se define mil líneas antes que `EL_PULSO`, y eso está bien: el nombre se resuelve cuando la función corre, no cuando se define.

Y el test, en `test_mapa_ws.py`:

```python
def test_el_borrador_deja_su_diff_en_el_anillo_del_agente(monkeypatch):
    """El evento `diff` tenia consumidores (el popup, el panel) y ningun
    productor: el unico diff real del server es el del borrador."""
    pu = p.Pulso()
    monkeypatch.setattr(srv, "EL_PULSO", pu)
    pu.publicar("chat:abc", "inicio", departamento="dep:atlas", rol="calipso")
    pu.publicar("chat:abc", "diff", ruta="a.py", diff="- viejo\n+ nuevo")
    empleado = pu.empleados("dep:atlas")[0]
    assert empleado["diff"] == {"ruta": "a.py", "diff": "- viejo\n+ nuevo"}
```

- [ ] **Step 7: Correr la suite entera**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_*.py test_mapa_*.py test_fabrica_js.py test_resource_dispatcher.py test_orchestrator.py -q`
Expected: PASS. `test_orchestrator.py` es de los que pytest no colecta; correrlo aparte con `/var/home/pedro/calipso/.venv/bin/python test_orchestrator.py` y ver que sigue diciendo lo mismo que antes del cambio.

- [ ] **Step 8: Commit**

```bash
git add calipso/server.py test_mapa_ws.py
git commit -m "feat(pulso): el chat y el equipo dinamico publican lo que hacen"
```

---

### Task 5: La ficha y la billetera — mapa → chat

Tocar un edificio fija el departamento como contexto de la conversación, y su billetera pasa a pagar lo que se consuma. Es la única escritura que este plan agrega al libro, y es una acción explícita de Pedro: eligió el departamento.

Dos cosas declaradas de entrada, porque salen del comportamiento que la economía ya tiene y este plan no lo cambia:

- **La ruta local no cuesta plata.** Ollama corre en la máquina de Pedro; el libro no tiene dónde asentarlo. Se cobra API y suscripción.
- **Un departamento personal no paga API pero sí consume capacidad de suscripción.** `Pagador.cargar_api` devuelve `None` para cualquier cuenta que empiece con `personal:` (el uso personal lo lleva `calipso/costs.py`), mientras que `cargar_suscripcion` sí le compra capacidad. Es asimétrico y es lo que hay hoy.

**Files:**
- Modify: `calipso/mapa/ficha.py`
- Modify: `calipso/economia/pagador.py`
- Modify: `dispatch.py`
- Modify: `calipso/server.py`
- Test: `test_mapa_acoplamiento.py` (nuevo), `test_economia_pagador.py` (se le suma un test)

**Interfaces:**
- Consumes: `Emisor` y `_edificios_livianos` (Task 3), `EL_PULSO` (Task 1), `Pagador` (ya existe).
- Produces:
  - `ficha.CUENTA_PERSONAL`, `ficha.cuenta_pagadora(id) -> str`, `ficha.edificio_de(modelo, id) -> dict | None`, `ficha.bloque(edificio) -> str`
  - `pagador.suscripcion_de_cliente(cliente) -> str`
  - `server._ciudad_modelo() -> dict | None` (extraído del endpoint, que pasa a usarlo)
  - `server._cobrar_turno(cuenta, route, client, model, usage) -> int`
  - `/ws/chat` acepta `departamento` en el paquete y devuelve `cuenta` y `mm` en el evento `cost`

- [ ] **Step 1: Escribir el test de la ficha y del cobro**

Crear `test_mapa_acoplamiento.py`:

```python
"""Tests del acoplamiento mapa <-> chat (spec seccion 8)."""
import json

import pytest

import calipso.server as srv
from calipso.economia import departamentos as deps
from calipso.economia import pagador as pag
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.mapa import ficha

TS = "2026-08-25T10:00:00"
W = "2026-W35"


EDIFICIO = {"id": "dep:atlas", "nombre": "atlas", "zona": "fabrica",
            "estado": "activo", "saldo_mm": 1_148_000,
            "gasto_ciclo_mm": 320_000, "ventas_ventana_mm": 900_500,
            "eficiencia_pormil": 124, "actividad": 2,
            "trabajos": ["t1", "t2"], "compuertas": 1}


def test_la_cuenta_pagadora_sale_del_id_del_edificio():
    assert ficha.cuenta_pagadora("dep:atlas") == "dep:atlas"
    assert ficha.cuenta_pagadora("personal:finanzas") == "personal:finanzas"
    # la casa de Pedro no es un departamento: su gasto queda fuera del libro
    # de la fabrica, que es donde lo lleva calipso/costs.py
    assert ficha.cuenta_pagadora("cuenta_pedro") == ficha.CUENTA_PERSONAL
    assert ficha.cuenta_pagadora(None) == ficha.CUENTA_PERSONAL
    assert ficha.cuenta_pagadora("") == ficha.CUENTA_PERSONAL
    # y nada de cuentas inventadas desde el cliente: el paquete del chat
    # llega de afuera y "tesoro" no puede pagar un chat
    assert ficha.cuenta_pagadora("tesoro") == ficha.CUENTA_PERSONAL


def test_el_edificio_se_busca_por_id_en_el_modelo():
    modelo = {"edificios": [EDIFICIO, {**EDIFICIO, "id": "dep:mercado"}]}
    assert ficha.edificio_de(modelo, "dep:mercado")["id"] == "dep:mercado"
    assert ficha.edificio_de(modelo, "dep:nada") is None
    assert ficha.edificio_de(None, "dep:atlas") is None


def test_el_bloque_lleva_los_numeros_en_monedas_y_dice_quien_paga():
    """El libro guarda milimonedas; el que lee el prompt lee monedas. Un
    bloque que dijera 1148000 haria que Calipso hable de millones."""
    texto = ficha.bloque(EDIFICIO)
    assert "atlas" in texto
    assert "1148.00" in texto and "320.00" in texto and "900.50" in texto
    assert "12.4%" in texto
    assert "dep:atlas" in texto.split("paga la cuenta")[1]
    assert "1148000" not in texto


def test_el_bloque_no_miente_cuando_no_hay_eficiencia():
    texto = ficha.bloque({**EDIFICIO, "eficiencia_pormil": None})
    assert "sin dato" in texto
    assert "0.0%" not in texto


@pytest.fixture
def economia(tmp_path, monkeypatch):
    """Una fabrica chica con un departamento con techo de API y plata.

    El `emitir_semana` no es decorativo: sin PT emitido, la semana no es
    operativa y `gastar_api` no encuentra el ciclo. Mismo armado que usa
    `test_economia_pagador.py`."""
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             techo_api_ciclo_mm=1_000_000))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    k.acunar(TS, W, "dep:atlas", 50_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    return eco


def saldo(eco, cuenta):
    return pag.Pagador(eco).leer_kernel().saldo(cuenta)


def test_el_turno_de_api_lo_paga_el_departamento_en_foco(economia):
    """Un millon de tokens de entrada de deepseek son 270 milimonedas: el
    precio esta en PRECIOS_API_MM_POR_MTOK y no se redondea a cero."""
    antes = saldo(economia, "dep:atlas")
    cobrado = srv._cobrar_turno("dep:atlas", "api", None, "deepseek-chat",
                                {"prompt_tokens": 1_000_000,
                                 "completion_tokens": 0})
    assert cobrado == 270
    assert saldo(economia, "dep:atlas") == antes - 270


def test_sin_departamento_no_se_toca_el_libro(economia):
    antes = saldo(economia, "dep:atlas")
    assert srv._cobrar_turno(ficha.CUENTA_PERSONAL, "api", None,
                             "deepseek-chat",
                             {"prompt_tokens": 1_000_000}) == 0
    assert saldo(economia, "dep:atlas") == antes


def test_la_ruta_local_no_cuesta_plata(economia):
    antes = saldo(economia, "dep:atlas")
    assert srv._cobrar_turno("dep:atlas", "local", None, "qwen2.5:7b",
                             {"prompt_tokens": 9_000_000}) == 0
    assert saldo(economia, "dep:atlas") == antes


def test_un_cobro_que_no_entra_queda_pendiente_y_no_voltea_el_chat(tmp_path,
                                                                  monkeypatch):
    """Techo de API en cero: el mercado rechaza el gasto. El turno tiene que
    terminar igual y el cargo esperar en cargos_pendientes.jsonl."""
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             techo_api_ciclo_mm=0))
    (eco / "suscripciones.json").write_text("{}", encoding="utf-8")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    k.acunar(TS, W, "dep:atlas", 50_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    srv._cobrar_turno("dep:atlas", "api", None, "deepseek-chat",
                      {"prompt_tokens": 1_000_000, "completion_tokens": 0})
    pendientes = pag.Pagador(eco).pendientes()
    assert len(pendientes) == 1 and pendientes[0]["cuenta"] == "dep:atlas"


def test_el_turno_de_equipo_dinamico_tambien_le_cobra_al_departamento(economia):
    """`used_route` vale "orchestrator" cuando corre el equipo dinamico. Si
    eso llega crudo a `_cobrar_turno`, los agentes gastan y el departamento
    no paga nada — que es justo lo contrario del criterio de exito del spec."""
    antes = saldo(economia, "dep:atlas")
    # lo que el llamador normaliza: orchestrator no es una ruta cobrable
    ruta = "api"      # verdict["route"] del turno
    cobrado = srv._cobrar_turno("dep:atlas", ruta, None, "deepseek-chat",
                                {"prompt_tokens": 1_000_000,
                                 "completion_tokens": 0})
    assert cobrado == 270 and saldo(economia, "dep:atlas") == antes - 270
    # y la ruta cruda no cobra nada, que es el bug que la normalizacion evita
    assert srv._cobrar_turno("dep:atlas", "orchestrator", None,
                             "deepseek-chat",
                             {"prompt_tokens": 1_000_000}) == 0


def test_el_modelo_de_ciudad_se_deriva_una_sola_vez_y_sin_coordenadas(economia):
    """El chat necesita la ficha, no el dibujo: el urbanismo, que es la
    mitad cara, no corre cuando no hay mapa que pintar."""
    modelo = srv._ciudad_modelo()
    assert modelo is not None
    edificio = ficha.edificio_de(modelo, "dep:atlas")
    assert edificio["saldo_mm"] == 50_000
    assert "x" not in edificio and "y" not in edificio
    # y el endpoint sigue entregando las coordenadas
    from fastapi.testclient import TestClient
    c = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})
    cuerpo = c.get("/api/mapa/ciudad").json()
    assert cuerpo["activa"] is True
    assert all("x" in e for e in cuerpo["ciudad"]["edificios"])
```

Y en `test_economia_pagador.py`:

```python
def test_el_cliente_se_traduce_a_la_suscripcion_que_existe():
    """dispatch.py tenia esta traduccion copiada a mano; dos verdades para
    un solo dato es como se desincronizan."""
    from calipso.economia.pagador import suscripcion_de_cliente
    assert suscripcion_de_cliente("claude") == "claude_max"
    assert suscripcion_de_cliente("codex") == "chatgpt_plus"
    assert suscripcion_de_cliente("CLAUDE") == "claude_max"
    assert suscripcion_de_cliente(None) == "claude_max"
```

- [ ] **Step 2: Correr los tests y ver que fallan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_acoplamiento.py test_economia_pagador.py -q`
Expected: FAIL — no existen `ficha.cuenta_pagadora`, `srv._cobrar_turno`, `srv._ciudad_modelo` ni `suscripcion_de_cliente`.

- [ ] **Step 3: Completar `ficha.py`**

Agregar a `calipso/mapa/ficha.py`:

```python
CUENTA_PERSONAL = "personal"
PREFIJOS = ("dep:", "personal:")


def _monedas(mm: int) -> str:
    """El libro guarda milimonedas; el que lee el prompt lee monedas."""
    return f"{(mm or 0) / 1000:.2f}"


def cuenta_pagadora(id_edificio: str | None) -> str:
    """La cuenta que paga el turno.

    La casa de Pedro (`cuenta_pedro`) y cualquier cosa que no sea un
    departamento caen en `personal`, que queda FUERA del libro de la
    fabrica. El id llega del cliente, asi que esto es tambien la validacion:
    `tesoro` no puede pagar un chat."""
    if not id_edificio:
        return CUENTA_PERSONAL
    if any(id_edificio.startswith(p) for p in PREFIJOS):
        return id_edificio
    return CUENTA_PERSONAL


def edificio_de(modelo: dict | None, id_edificio: str) -> dict | None:
    if not modelo:
        return None
    for e in modelo.get("edificios", ()):
        if e["id"] == id_edificio:
            return e
    return None


def bloque(edificio: dict) -> str:
    """El contexto que recibe Calipso cuando Pedro toca un edificio.

    No lo convierte en el departamento: lo pone a hablar CON Pedro SOBRE el
    departamento (invariante 7)."""
    efi = edificio.get("eficiencia_pormil")
    trabajos = edificio.get("trabajos") or []
    return "\n".join([
        "=== Departamento en foco ===",
        f"Pedro esta mirando {edificio['nombre']} (id {edificio['id']}, "
        f"zona {edificio['zona']}, estado {edificio['estado']}).",
        f"Saldo: {_monedas(edificio['saldo_mm'])} monedas. "
        f"Gasto del ciclo: {_monedas(edificio['gasto_ciclo_mm'])}. "
        f"Ventas de la ventana: {_monedas(edificio['ventas_ventana_mm'])}. "
        + ("Eficiencia: sin dato." if efi is None
           else f"Eficiencia: {efi / 10:.1f}%."),
        f"Trabajos vivos: {', '.join(trabajos) if trabajos else 'ninguno'}. "
        f"Compuertas pendientes: {edificio.get('compuertas', 0)}.",
        f"Lo que se gaste en este turno lo paga la cuenta "
        f"{cuenta_pagadora(edificio['id'])}.",
        "Hablas con Pedro SOBRE este departamento. No hablas en su nombre ni "
        "le hablas a el: la conversacion es siempre con Calipso.",
    ])
```

- [ ] **Step 4: Sacar la traducción de cliente a suscripción de `dispatch.py`**

En `calipso/economia/pagador.py`, después de `PRECIO_DESCONOCIDO`:

```python
SUSCRIPCION_POR_CLIENTE = {"claude": "claude_max", "codex": "chatgpt_plus"}


def suscripcion_de_cliente(cliente: str | None) -> str:
    """`claude` -> `claude_max`. El nombre del cliente y el de la suscripcion
    no son el mismo dato; la traduccion estaba escrita a mano en dispatch.py
    y ahora la usan los dos."""
    return SUSCRIPCION_POR_CLIENTE.get((cliente or "").strip().lower(),
                                       "claude_max")
```

En `dispatch.py`, en el bloque de cargo económico, reemplazar

```python
                    sus = "claude_max" if cliente == "claude" else "chatgpt_plus"
```

por

```python
                    sus = _suscripcion_de_cliente(cliente)
```

y en el import de arriba (`from calipso.economia.pagador import Pagador as _Pagador`) sumar el nombre:

```python
    from calipso.economia.pagador import (Pagador as _Pagador,
                                          suscripcion_de_cliente as
                                          _suscripcion_de_cliente)
```

En el `except` de ese import, agregar `_suscripcion_de_cliente = None` junto a `_Pagador = None`, y en la guarda del bloque de cargo (`if _Pagador and _semana_iso:`) no hace falta tocar nada: si el import falló, `_Pagador` ya es `None`.

- [ ] **Step 5: Extraer `_ciudad_modelo` y escribir `_cobrar_turno`**

En `calipso/server.py`, reemplazar el cuerpo de `api_mapa_ciudad` por esto (la derivación sale a su propia función, que es lo que el chat necesita sin las coordenadas):

```python
def _ciudad_modelo() -> dict | None:
    """El modelo derivado del libro, SIN coordenadas.

    El endpoint le agrega el urbanismo; el chat, que solo quiere la ficha de
    un departamento, se ahorra esa mitad. None si la economia no esta."""
    if _mapa_ciudad is None or _EcoPagador is None:
        return None
    p0 = _EcoPagador.desde_entorno(_ECO_BASE)
    if not p0:
        return None
    _, semana = _eco_ahora()
    # lector serializado: el libro se repara truncando, no se lee a medio
    # escribir
    with _eco_candado(p0.ruta_libro):
        eco = _economia()
        m = eco["pagador"].mercado_fresco()
        asientos = m.k.libro.asientos()
        ops = _mapa_cap.semanas_operativas(asientos)
        minutos = eco["reloj"].minutos_por_categoria(ops[-4:]) if ops else {}
        return _mapa_ciudad.ciudad(
            asientos, m.registro, eco["bus"], eco["cola"], semana,
            minutos_empleo=minutos.get("empleo", 0),
            suscripciones=m.suscripciones)


@app.get("/api/mapa/ciudad")
def api_mapa_ciudad() -> dict:
    modelo = _ciudad_modelo()
    if modelo is None:
        return {"activa": False}
    posiciones = _mapa_urbanismo.urbanizar(modelo["edificios"],
                                           modelo["calles"])
    for e in modelo["edificios"]:
        x, y = posiciones.get(e["id"], (0, 0))
        e["x"], e["y"] = x, y
    return {"activa": True, "ciudad": modelo}


def _cobrar_turno(cuenta: str, route: str, client: str | None,
                  model: str | None, usage: dict) -> int:
    """La billetera del departamento en foco paga el turno.

    Nunca voltea el chat: lo que el mercado rechaza queda en
    cargos_pendientes.jsonl y la operacion lo reintenta. Toma el candado del
    libro, asi que se llama SIEMPRE desde un hilo. Devuelve las milimonedas
    cobradas: la ruta local no cuesta plata y la suscripcion se cobra en
    unidades de capacidad, no en monedas, asi que las dos devuelven cero."""
    if _EcoPagador is None or _mapa_ficha is None:
        return 0
    if not cuenta or cuenta == _mapa_ficha.CUENTA_PERSONAL:
        return 0
    pagador = _EcoPagador.desde_entorno(_ECO_BASE)
    if pagador is None:
        return 0
    ts, semana = _eco_ahora()
    try:
        if route == "api":
            return pagador.cargar_api(ts, semana, cuenta, model or "",
                                      usage.get("prompt_tokens", 0),
                                      usage.get("completion_tokens", 0)) or 0
        if route == "subscription":
            pagador.cargar_suscripcion(ts, semana, cuenta,
                                       _eco_suscripcion(client))
    except Exception as exc:
        # el cobro es contabilidad, no la conversacion: que falle no puede
        # dejar a Pedro sin respuesta
        print(f"[calipso] no se pudo cobrar el turno a {cuenta}: {exc}",
              file=sys.stderr)
    return 0
```

Y en el import de la economía de `server.py`, sumar el traductor:

```python
    from calipso.economia.pagador import (Pagador as _EcoPagador,
                                          suscripcion_de_cliente as
                                          _eco_suscripcion)
```

con `_eco_suscripcion = None` en el `except` correspondiente.

- [ ] **Step 6: Cablear el departamento en `ws_chat`**

1. Al principio del turno, junto a `attachment_ids: list[str] = []`:

```python
            departamento = None      # el edificio que Pedro tiene tocado
```

2. En el parseo del paquete, junto a `chat_id = packet.get("chat_id") or chat_id`:

```python
                        departamento = packet.get("departamento") or None
```

3. Después de `chat_msg = directives["clean"]`, resolver la cuenta y la ficha:

```python
            cuenta = (_mapa_ficha.cuenta_pagadora(departamento)
                      if _mapa_ficha else "personal")
            bloque_dep = ""
            if departamento and _mapa_ficha is not None:
                # derivar la ciudad toma el candado del libro: va en un hilo
                modelo = await asyncio.to_thread(_ciudad_modelo)
                edificio = _mapa_ficha.edificio_de(modelo, departamento)
                if edificio:
                    bloque_dep = _mapa_ficha.bloque(edificio)
```

4. **Cada vez** que aparece el par de líneas

```python
                if attachment_context:
                    system += "\n\n" + attachment_context
```

(hay cuatro apariciones, con distinta indentación: la principal, la del orquestador, la del fallback entre suscripciones y la del fallback local), agregar debajo, con la misma indentación:

```python
                if bloque_dep:
                    system += "\n\n" + bloque_dep
```

La aparición principal está justo después de `attachment_context = attachments.context_block(...)` (`server.py:2275-2277`) y tiene su `if` como las otras tres; el bloque del departamento va debajo, igual que en el resto.

5. Reemplazar el `agente_id`/`inicio` que dejó la Task 4 para que lleve el departamento de verdad:

```python
                EL_PULSO.publicar(agente_id, "inicio",
                                  departamento=departamento, rol="calipso",
                                  modelo=model)
```

6. Cobrar y contarlo. Reemplazar el bloque `# 4) registrar costo/uso y avisar` por:

```python
            # 4) registrar costo/uso, cobrarle al departamento en foco y avisar
            entry = costs.log_usage(
                used_route, model, usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0), client=verdict.get("client"))
            # `used_route` vale "orchestrator" cuando corrio el equipo dinamico,
            # y esa no es una ruta que se pueda cobrar: los agentes gastaron
            # por la ruta base del verdict. Sin esta normalizacion, un turno
            # de equipo con atlas en foco no le cobra un peso a atlas.
            ruta_cobrable = (verdict["route"] if used_route == "orchestrator"
                             else used_route)
            cobrado = await asyncio.to_thread(
                _cobrar_turno, cuenta, ruta_cobrable, verdict.get("client"),
                model, usage)
            await ws.send_json({"type": "cost", "model": model, "route": used_route,
                                "tokens": entry["prompt_tokens"] + entry["completion_tokens"],
                                "cost_usd": entry["cost_usd"],
                                "cuenta": cuenta, "mm": cobrado})
```

y en el `tokens` del pulso que dejó la Task 4, pasar `costo_mm=cobrado`.

- [ ] **Step 7: Correr los tests y ver que pasan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_mapa_acoplamiento.py test_economia_pagador.py -q`
Expected: PASS

- [ ] **Step 8: Correr la suite entera**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_*.py test_mapa_*.py test_fabrica_js.py test_resource_dispatcher.py -q`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add calipso/mapa/ficha.py calipso/economia/pagador.py dispatch.py \
        calipso/server.py test_mapa_acoplamiento.py test_economia_pagador.py
git commit -m "feat(acoplamiento): el departamento en foco contextualiza y paga"
```

---

### Task 6: El cliente del pulso y el vuelo de la cámara

El mapa se entera de lo que pasa. Un reductor puro que reconstruye los empleados de cada departamento a partir del flujo de eventos, un socket que lo alimenta y reconecta, y la cámara volando cuando llega un foco.

**Files:**
- Create: `calipso/web/fabrica/pulso.js`, `calipso/web/fabrica/pulso.test.js`
- Modify: `calipso/web/fabrica/app.js`, `calipso/web/fabrica/arranque.test.js`

**Interfaces:**
- Consumes: el contrato de evento del `WS /ws/mapa` (Task 2); `volarA` de `camara.js`.
- Produces:
  - `estadoInicial() -> {conectado, empleados, foco, seq}`
  - `aplicarEvento(estado, ev, ahora) -> estado` (puro, no muta)
  - `empleadosDe(estado, departamento) -> array` ordenado, el más nuevo primero
  - `estadoVisible(empleado, ahora, inactivoMs = 600000) -> string`
  - `crearPulso(alCambiar, ConstructorWS = WebSocket, ahora = () => Date.now())`

- [ ] **Step 1: Escribir el test del reductor**

Crear `calipso/web/fabrica/pulso.test.js`:

```js
/**
 * pulso.test.js — El reductor de la capa viva.
 *
 * El servidor manda eventos sueltos; el cliente arma con eso el plantel de
 * cada departamento. Se testea el reductor entero sin abrir un socket,
 * igual que chat.test.js hace con el protocolo del chat.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {aplicarEvento, crearPulso, empleadosDe, estadoInicial,
        estadoVisible} from "./pulso.js";

function ev(evento, campos = {}, seq = 1, ts = 1000) {
  return {seq, ts, agente_id: "a1", departamento: "dep:atlas", trabajo: null,
          rol: "scout", modelo: "sonnet", evento, ...campos};
}

test("el inicio abre un escritorio en su departamento", () => {
  const e = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  const empleados = empleadosDe(e, "dep:atlas");
  assert.equal(empleados.length, 1);
  assert.equal(empleados[0].rol, "scout");
  assert.equal(empleados[0].modelo, "sonnet");
  assert.equal(empleados[0].estado, "esperando");
  assert.deepEqual(empleadosDe(e, "dep:mercado"), []);
});

test("el reductor no muta lo que recibe", () => {
  const antes = estadoInicial();
  const despues = aplicarEvento(antes, ev("inicio"), 5000);
  assert.notEqual(antes, despues);
  assert.deepEqual(empleadosDe(antes, "dep:atlas"), []);
});

test("el razonamiento se acumula, no se reemplaza", () => {
  let e = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  e = aplicarEvento(e, ev("razonando", {texto: "mirando "}, 2), 5001);
  e = aplicarEvento(e, ev("razonando", {texto: "el libro"}, 3), 5002);
  const empleado = empleadosDe(e, "dep:atlas")[0];
  assert.equal(empleado.texto, "mirando el libro");
  assert.equal(empleado.estado, "razonando");
});

test("los tokens son el ultimo acumulado, no la suma", () => {
  let e = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  e = aplicarEvento(e, ev("tokens", {tokens_in: 100, tokens_out: 10,
                                     costo_mm: 5}, 2), 5001);
  e = aplicarEvento(e, ev("tokens", {tokens_in: 300, tokens_out: 40,
                                     costo_mm: 17}, 3), 5002);
  const empleado = empleadosDe(e, "dep:atlas")[0];
  assert.equal(empleado.tokens_in, 300);
  assert.equal(empleado.costo_mm, 17);
});

test("el fin libera el escritorio y guarda el rastro", () => {
  let e = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  e = aplicarEvento(e, ev("diff", {ruta: "a.py", diff: "- x\n+ y"}, 2), 5001);
  e = aplicarEvento(e, ev("fin", {runtime_ms: 1500, resultado: "ok"}, 3), 5002);
  const empleado = empleadosDe(e, "dep:atlas")[0];
  assert.equal(empleado.estado, "liberado");
  assert.equal(empleado.runtime_ms, 1500);
  // ver que el departamento SOLTO gente es tan informativo como verlo
  // contratar: el rastro del que se fue no se borra
  assert.deepEqual(empleado.diff, {ruta: "a.py", diff: "- x\n+ y"});
});

test("el que dejo de publicar se ve inactivo, el liberado no", () => {
  let e = aplicarEvento(estadoInicial(), ev("razonando", {texto: "x"}), 5000);
  const vivo = empleadosDe(e, "dep:atlas")[0];
  assert.equal(estadoVisible(vivo, 5000 + 599_000), "razonando");
  assert.equal(estadoVisible(vivo, 5000 + 601_000), "inactivo");
  e = aplicarEvento(e, ev("fin", {runtime_ms: 1, resultado: "ok"}, 2), 5001);
  const suelto = empleadosDe(e, "dep:atlas")[0];
  assert.equal(estadoVisible(suelto, 5000 + 9_999_000), "liberado");
});

test("dos agentes del mismo departamento son dos escritorios", () => {
  let e = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  e = aplicarEvento(e, ev("inicio", {agente_id: "a2", rol: "copista"}, 2),
                    5001);
  const empleados = empleadosDe(e, "dep:atlas");
  assert.deepEqual(empleados.map(x => x.agente_id), ["a2", "a1"]);
});

test("el foco se guarda con su seq para que no vuele dos veces", () => {
  let e = aplicarEvento(estadoInicial(),
                        {seq: 7, ts: 1, agente_id: null, evento: "foco",
                         departamento: "dep:atlas"}, 5000);
  assert.deepEqual(e.foco, {departamento: "dep:atlas", seq: 7});
  // un evento cualquiera despues no borra el foco ni le cambia el seq
  e = aplicarEvento(e, ev("inicio", {}, 8), 5001);
  assert.deepEqual(e.foco, {departamento: "dep:atlas", seq: 7});
});

test("el latido y lo desconocido no rompen ni ensucian el estado", () => {
  const base = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  assert.equal(aplicarEvento(base, {evento: "latido", seq: 9}, 5001), base);
  assert.equal(aplicarEvento(base, {evento: "bailando", seq: 9}, 5001), base);
  assert.equal(aplicarEvento(base, null, 5001), base);
});

test("un evento sin departamento no cuelga de ningun escritorio", () => {
  // el turno de chat sin edificio tocado publica igual: se ve en el flujo
  // pero no tiene donde sentarse
  const e = aplicarEvento(estadoInicial(),
                          ev("inicio", {departamento: null}), 5000);
  assert.deepEqual(Object.keys(e.empleados), []);
});

test("el socket se engancha a /ws/mapa y reconecta cuando se cae", () => {
  const abiertos = [];
  class WSFalso {
    static OPEN = 1;
    constructor(url) {
      this.url = url;
      this.oyentes = new Map();
      abiertos.push(this);
    }
    addEventListener(tipo, f) {
      if (!this.oyentes.has(tipo)) this.oyentes.set(tipo, []);
      this.oyentes.get(tipo).push(f);
    }
    emitir(tipo, ev) { for (const f of this.oyentes.get(tipo) || []) f(ev); }
    dice(dato) { this.emitir("message", {data: JSON.stringify(dato)}); }
    close() {}
  }
  globalThis.location = {protocol: "http:", host: "127.0.0.1:8137"};
  const vistos = [];
  const reintentos = [];
  globalThis.setTimeout = f => { reintentos.push(f); return 0; };

  crearPulso(e => vistos.push(e), WSFalso, () => 5000);
  assert.ok(abiertos[0].url.endsWith("/ws/mapa"), abiertos[0].url);
  // el estado inicial se pinta ANTES de conectar: si no, la interfaz se ve
  // conectada hasta el primer evento
  assert.equal(vistos[0].conectado, false);

  abiertos[0].emitir("open", {});
  assert.equal(vistos.at(-1).conectado, true);
  abiertos[0].dice(ev("inicio"));
  assert.equal(empleadosDe(vistos.at(-1), "dep:atlas").length, 1);

  abiertos[0].emitir("close", {});
  assert.equal(vistos.at(-1).conectado, false);
  assert.equal(reintentos.length, 1, "no se programo la reconexion");
  reintentos[0]();
  assert.equal(abiertos.length, 2);
  // y lo que ya sabia no se pierde: el mapa no se vacia porque se corto el
  // socket (el pulso es efimero, pero no amnesico)
  assert.equal(empleadosDe(vistos.at(-1), "dep:atlas").length, 1);
});
```

- [ ] **Step 2: Correr los tests del cliente y ver que fallan**

Run: `cd /var/home/pedro/calipso/calipso/web/fabrica && ~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test`
Expected: FAIL — `Cannot find module ./pulso.js`

- [ ] **Step 3: Escribir el módulo**

Crear `calipso/web/fabrica/pulso.js`:

```js
/**
 * calipso/web/fabrica/pulso.js — La capa viva, del lado del cliente.
 *
 * El servidor manda eventos sueltos por /ws/mapa y este reductor arma con
 * ellos el plantel de cada departamento. Es puro y no muta lo que recibe:
 * por eso se puede testear el protocolo entero sin abrir un socket.
 *
 * El reloj entra por parametro (`ahora`) y se guarda en cada empleado como
 * `visto`: el `ts` del evento es del reloj DEL SERVIDOR y compararlo contra
 * el del navegador es comparar dos relojes distintos. Para saber si alguien
 * dejo de publicar alcanza con cuando lo vimos nosotros.
 */
export const INACTIVO_MS = 600_000;    // diez minutos, igual que el servidor

export function estadoInicial() {
  return {conectado: false, empleados: {}, foco: null, seq: 0};
}

function vacio(ev, ahora) {
  return {agente_id: ev.agente_id, departamento: ev.departamento,
          rol: ev.rol, modelo: ev.modelo, trabajo: ev.trabajo,
          estado: "esperando", texto: "", tokens_in: 0, tokens_out: 0,
          costo_mm: 0, runtime_ms: 0, diff: null, herramienta: null,
          visto: ahora};
}

const CONOCIDOS = ["inicio", "razonando", "herramienta", "tokens", "diff",
                   "fin", "foco"];

export function aplicarEvento(estado, ev, ahora) {
  if (!ev || !CONOCIDOS.includes(ev.evento)) return estado;   // latido incluido
  if (ev.evento === "foco") {
    if (!ev.departamento) return estado;
    return {...estado, seq: ev.seq || estado.seq,
            foco: {departamento: ev.departamento, seq: ev.seq}};
  }
  if (!ev.departamento || !ev.agente_id) return estado;
  const dep = estado.empleados[ev.departamento] || {};
  const previo = dep[ev.agente_id];
  // el `inicio` de un agente que ya estaba lo reinicia: un id repetido es un
  // trabajo nuevo, no la continuacion del anterior
  const base = (previo && ev.evento !== "inicio") ? previo : vacio(ev, ahora);
  const e = {...base, visto: ahora,
             rol: ev.rol || base.rol, modelo: ev.modelo || base.modelo,
             trabajo: ev.trabajo || base.trabajo};
  switch (ev.evento) {
    case "razonando":
      e.texto = base.texto + (ev.texto || "");
      e.estado = "razonando";
      break;
    case "herramienta":
      e.herramienta = {nombre: ev.nombre, resumen: ev.resumen || ""};
      e.estado = "razonando";
      break;
    case "tokens":
      // acumulados: se reemplazan, no se suman
      e.tokens_in = ev.tokens_in || 0;
      e.tokens_out = ev.tokens_out || 0;
      e.costo_mm = ev.costo_mm || 0;
      break;
    case "diff":
      e.diff = {ruta: ev.ruta, diff: ev.diff};
      break;
    case "fin":
      e.estado = "liberado";
      e.runtime_ms = ev.runtime_ms || 0;
      e.resultado = ev.resultado || "ok";
      break;
    default:
      break;
  }
  return {...estado, seq: ev.seq || estado.seq,
          empleados: {...estado.empleados,
                      [ev.departamento]: {...dep, [ev.agente_id]: e}}};
}

/** El mas nuevo primero, que es como se llenan los escritorios. */
export function empleadosDe(estado, departamento) {
  const dep = estado.empleados[departamento];
  if (!dep) return [];
  return Object.values(dep).sort((a, b) => (b.visto - a.visto) ||
                                           (a.agente_id < b.agente_id ? 1 : -1));
}

/** Un liberado se queda liberado; el que se colgo se marca inactivo. */
export function estadoVisible(empleado, ahora, inactivoMs = INACTIVO_MS) {
  if (!empleado) return "esperando";
  if (empleado.estado === "liberado") return "liberado";
  return (ahora - empleado.visto > inactivoMs) ? "inactivo" : empleado.estado;
}

export function crearPulso(alCambiar, ConstructorWS = WebSocket,
                           ahora = () => Date.now()) {
  let estado = estadoInicial();
  const proto = location.protocol === "https:" ? "wss" : "ws";
  let ws = null;

  function conectar() {
    try {
      ws = new ConstructorWS(`${proto}://${location.host}/ws/mapa`);
    } catch (e) {
      // el constructor puede tirar sincronicamente, y adentro del setTimeout
      // del reintento no hay nadie que agarre esa excepcion: la cadena de
      // reconexion moriria en silencio (mismo motivo que en chat.js)
      ws = null;
      estado = {...estado, conectado: false};
      alCambiar(estado);
      setTimeout(conectar, 2000);
      return;
    }
    ws.addEventListener("open", () => {
      estado = {...estado, conectado: true};
      alCambiar(estado);
    });
    ws.addEventListener("message", ev => {
      let dato;
      try { dato = JSON.parse(ev.data); } catch { return; }
      estado = aplicarEvento(estado, dato, ahora());
      alCambiar(estado);
    });
    // si se cae, el mapa sigue mostrando la foto: el pulso es una capa
    // encima, no el mapa
    ws.addEventListener("close", () => {
      estado = {...estado, conectado: false};
      alCambiar(estado);
      setTimeout(conectar, 2000);
    });
  }
  alCambiar(estado);        // el estado inicial dice "sin conexion" y se pinta
  conectar();

  return {estado: () => estado};
}
```

- [ ] **Step 4: Correr los tests y ver que pasan**

Run: `cd /var/home/pedro/calipso/calipso/web/fabrica && ~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test`
Expected: PASS

- [ ] **Step 5: Cablear el vuelo de la cámara en `app.js`**

Agregar el import junto a los otros:

```js
import {crearPulso, empleadosDe, estadoVisible} from "./pulso.js";
```

Y al final del archivo, junto al arranque del mapa:

```js
let pulso = {conectado: false, empleados: {}, foco: null, seq: 0};
let ultimoFoco = 0;

const conexionPulso = crearPulso(estado => {
  pulso = estado;
  if (pulso.foco && pulso.foco.seq !== ultimoFoco) {
    ultimoFoco = pulso.foco.seq;
    volarAEdificio(pulso.foco.departamento);
  }
});

/** El foco de la conversacion mueve la camara (spec seccion 8). */
function volarAEdificio(id) {
  if (!ciudad) return;
  const e = ciudad.edificios.find(x => x.id === id);
  if (!e) return;              // la ciudad puede no tenerlo todavia
  volarA(cam, {x: e.x, y: e.y, escala: Math.max(cam.escala, 2)});
}
```

y sumar `volarA` al import de `camara.js`.

- [ ] **Step 6: Arreglar la elección de socket en `arranque.test.js`**

`app.js` abre ahora dos sockets, y el del pulso puede salir primero. Reemplazar

```js
const socket = nav.sockets[0];
```

por

```js
// dos sockets vivos: el del chat y el del pulso. Elegirlos por INDICE ata el
// test al orden de los imports de app.js
const socket = nav.sockets.find(s => s.url.endsWith("/ws/chat"));
const socketMapa = nav.sockets.find(s => s.url.endsWith("/ws/mapa"));
```

Para poder afirmar que la cámara se movió hace falta poder verla. El archivo importa `app.js` descartando el módulo (`import("./app.js").then(() => "cargado")`, línea 183): cambiarlo para quedárselo, con un `let modulo = null;` arriba del `Promise.race`:

```js
let modulo = null;
const cargado = await Promise.race([
  import("./app.js").then(m => { modulo = m; return "cargado"; }),
  new Promise(r => { plazo = setTimeout(() => r("colgado"), PLAZO); }),
]);
```

y en `app.js`, junto a `volarAEdificio`, un lector de una línea:

```js
// Solo para arranque.test.js: la camara es interna y sin esto el test del
// foco no puede afirmar nada mas que "el chat no se entero", que es la
// mitad que no importa. Es de lectura y no la deja tocar.
export const camaraDePrueba = () => cam;
```

Ahora sí, los dos tests, **al final del archivo** (comparten el `app.js` ya evaluado y el orden importa):

```js
test("el mapa se engancha a /ws/mapa", () => {
  assert.ok(socketMapa, "crearPulso no abrio ningun socket");
});

test("un foco por el pulso hace volar la camara, sin tocar el chat", async () => {
  await new Promise(r => setTimeout(r, 0));   // la ciudad ya contesto
  const conversacionAntes = nav.nodos.get("conversacion").hijos.length;
  socketMapa.dice({seq: 1, ts: 1, agente_id: null, evento: "foco",
                   departamento: "dep:b"});
  const cam = modulo.camaraDePrueba();
  // la ciudad de prueba pone a dep:b en (60, 30): la camara arranca un VUELO
  // hacia ahi, no se teletransporta
  assert.ok(cam.vuelo, "el foco no disparo ningun vuelo");
  assert.deepEqual({x: cam.vuelo.hasta.x, y: cam.vuelo.hasta.y},
                   {x: 60, y: 30});
  assert.equal(nav.nodos.get("conversacion").hijos.length, conversacionAntes,
               "el foco toco la conversacion");
});
```

- [ ] **Step 7: El módulo nuevo entra en el SHELL del service worker**

`test_mapa_server.py::test_el_shell_no_se_olvida_de_ningun_archivo_de_la_fabrica` deriva la lista esperada de los archivos **reales** del directorio: cualquier `.js` nuevo que no esté en el SHELL pone la suite en rojo, y la fábrica queda inservible sin conexión. En `calipso/web/sw.js`, dentro del array `SHELL`, junto a las otras rutas de la fábrica:

```js
  "/static/fabrica/chat.js",
  "/static/fabrica/pulso.js"
```

(la línea de `chat.js` es hoy la última del array y no lleva coma: se le agrega).

- [ ] **Step 8: Correr los tests del cliente y la suite del mapa**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py test_mapa_server.py -q`
Expected: PASS. `test_mapa_server.py` va explícito porque es el que vigila el SHELL.

- [ ] **Step 9: Commit**

```bash
git add calipso/web/fabrica/pulso.js calipso/web/fabrica/pulso.test.js \
        calipso/web/fabrica/app.js calipso/web/fabrica/arranque.test.js \
        calipso/web/sw.js
git commit -m "feat(fabrica): el cliente del pulso y la camara que vuela al foco"
```

---

### Task 7: Tocar un edificio, cambiar de chat, ver el costo corriendo

Las tres superficies que el Plan 2 dejó cableadas a medias a propósito (sección 12 ter del spec) más el lado cliente del acoplamiento: tocar un edificio fija el contexto y se **ve** que lo fijó, la lista de chats responde al click, y el costo del turno deja de acumularse en silencio.

**Files:**
- Modify: `calipso/web/fabrica/chat.js`, `paneles.js`, `app.js`, `index.html`, `estilo.css`
- Modify: `calipso/web/fabrica/chat.test.js`, `paneles.test.js`, `arranque.test.js`

**Interfaces:**
- Consumes: `/api/chats` y `POST /api/chats/{id}/activate` (ya existen); el evento `cost` con `cuenta` y `mm` (Task 5).
- Produces:
  - `chat.paquete(texto, chatId, departamento) -> objeto`
  - `chat.turnosDeHistorial(mensajes) -> array`
  - `crearChat(...).enviar(texto, departamento) -> bool`
  - `crearChat(...).cargar(chat)` — reemplaza los turnos por el historial y sube `epoca`
  - `paneles.textoDeCosto(estadoDelChat) -> string`
  - `paneles.textoDeFoco(ficha) -> string`

- [ ] **Step 1: Escribir los tests del chat**

En `calipso/web/fabrica/chat.test.js`, primero la cabecera: la línea 4 importa hoy `{estadoInicial, aplicarEvento, paquete, crearChat}` y hay que sumarle `turnosDeHistorial`. Sin eso el test nuevo falla con `turnosDeHistorial is not defined` para siempre, aun con `chat.js` bien implementado. Después, los tests:

```js
test("el paquete lleva el departamento tocado, y solo si hay uno", () => {
  assert.deepEqual(paquete("hola", "c1", "dep:atlas"),
                   {text: "hola", chat_id: "c1", departamento: "dep:atlas"});
  assert.deepEqual(paquete("hola", "c1", null),
                   {text: "hola", chat_id: "c1"});
});

test("el evento cost dice quien pago", () => {
  let e = estadoInicial();
  e = aplicarEvento(e, {type: "cost", cost_usd: 0.004, tokens: 1200,
                        cuenta: "dep:atlas", mm: 270});
  assert.equal(e.cuenta, "dep:atlas");
  assert.equal(e.costo_mm, 270);
  assert.equal(e.tokens, 1200);
  // dos turnos seguidos acumulan las milimonedas, igual que los tokens
  e = aplicarEvento(e, {type: "cost", cost_usd: 0.001, tokens: 300,
                        cuenta: "dep:atlas", mm: 30});
  assert.equal(e.costo_mm, 300);
});

test("el historial de otro chat se convierte en turnos", () => {
  const turnos = turnosDeHistorial([
    {role: "user", text: "hola", ts: "x"},
    {role: "assistant", text: "que tal", meta: {route: "api"}},
  ]);
  assert.deepEqual(turnos, [{quien: "pedro", texto: "hola", abierto: false},
                            {quien: "calipso", texto: "que tal",
                             abierto: false}]);
  assert.deepEqual(turnosDeHistorial(null), []);
});

test("cargar otro chat reemplaza los turnos y sube la epoca", () => {
  // la epoca es lo que le dice a app.js que tiene que rehacer los nodos:
  // sin eso, los turnos del chat viejo quedan arriba de los del nuevo
  const vistos = [];
  const chat = crearChat(e => vistos.push(e), WSFalso);
  chat.cargar({id: "c9", messages: [{role: "user", text: "viejo"}]});
  const estado = vistos.at(-1);
  assert.equal(estado.chatId, "c9");
  assert.equal(estado.turnos.length, 1);
  assert.ok(estado.epoca > estadoInicial().epoca);
});
```

(`WSFalso` es el doble que `chat.test.js` ya declara en su cabecera, con `WSFalso.OPEN = 1`.)

- [ ] **Step 2: Escribir los tests de los paneles**

En `calipso/web/fabrica/paneles.test.js`, primero la cabecera: el import de `./paneles.js` (líneas 4-5) trae hoy `{disposicion, textoDeTarjeta, posicionDeTarjeta, resumenDeAvisos, ANCHO_TELEFONO}` y hay que sumarle `textoDeCosto, textoDeFoco`. Después, los tests:

```js
test("el costo corriendo dice ruta, modelo, tokens y quien paga", () => {
  const texto = textoDeCosto({ruta: "api", modelo: "sonnet", tokens: 1234,
                              costo_usd: 0.0042, cuenta: "dep:atlas",
                              costo_mm: 270});
  assert.match(texto, /api/);
  assert.match(texto, /sonnet/);
  assert.match(texto, /1\.234/);        // separador de miles en es
  assert.match(texto, /atlas/);
  assert.match(texto, /0,27/);          // 270 milimonedas son 0,27 monedas
});

test("sin turno todavia, la barra de costo esta vacia y no dice cero", () => {
  assert.equal(textoDeCosto({ruta: null, modelo: null, tokens: 0,
                             costo_usd: 0}), "");
});

test("el costo no inventa una cuenta cuando paga Pedro", () => {
  const texto = textoDeCosto({ruta: "local", modelo: "qwen2.5:7b",
                              tokens: 40, costo_usd: 0});
  assert.ok(!texto.includes("paga"), texto);
});

test("la etiqueta de foco nombra al departamento y ofrece soltarlo", () => {
  const texto = textoDeFoco({id: "dep:atlas", nombre: "atlas",
                             saldo: "1.148"});
  assert.match(texto, /atlas/);
  assert.match(texto, /data-accion="quitar"/);
  // el nombre lo escribe Pedro: va escapado, como en la tarjeta
  const feo = textoDeFoco({id: "dep:x", nombre: '<img src=x>', saldo: "0"});
  assert.ok(!feo.includes("<img"), feo);
});
```

- [ ] **Step 3: Correr los tests del cliente y ver que fallan**

Run: `cd /var/home/pedro/calipso/calipso/web/fabrica && ~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test`
Expected: FAIL — `textoDeCosto is not defined`, `turnosDeHistorial is not defined`, `chat.cargar is not a function`.

- [ ] **Step 4: Implementar en `chat.js`**

```js
export function estadoInicial() {
  return {turnos: [], pensando: false, chatId: null, ruta: null,
          modelo: null, costo_usd: 0, tokens: 0, costo_mm: 0, cuenta: null,
          conectado: false, epoca: 0};
}

export function paquete(texto, chatId, departamento = null) {
  const p = {text: texto, chat_id: chatId};
  // el departamento va SOLO si hay uno: mandar null en cada turno haria que
  // el server tenga que distinguir "sin foco" de "foco borrado"
  if (departamento) p.departamento = departamento;
  return p;
}

export function turnosDeHistorial(mensajes) {
  return (mensajes || []).map(m => ({
    quien: m.role === "user" ? "pedro" : "calipso",
    texto: m.text || "", abierto: false}));
}
```

En `aplicarEvento`, el caso `cost`:

```js
    case "cost":
      // campos reales del /ws/chat: cost_usd y tokens (server.py), mas la
      // cuenta que pago y las milimonedas que se le cobraron
      e.costo_usd = e.costo_usd + (ev.cost_usd || 0);
      e.tokens = e.tokens + (ev.tokens || 0);
      e.costo_mm = e.costo_mm + (ev.mm || 0);
      if (ev.cuenta && ev.cuenta !== "personal") e.cuenta = ev.cuenta;
      break;
```

En `crearChat`, cambiar `enviar` y sumar `cargar`:

```js
    enviar(texto, departamento = null) {
      if (!texto.trim() || !ws || ws.readyState !== ConstructorWS.OPEN) {
        return false;
      }
      estado = {...estado,
                turnos: [...estado.turnos,
                         {quien: "pedro", texto, abierto: false}]};
      alCambiar(estado);
      ws.send(JSON.stringify(paquete(texto, estado.chatId, departamento)));
      return true;
    },
    /** Otro chat: los turnos se reemplazan enteros y la epoca sube para que
     *  quien pinta sepa que tiene que rehacer los nodos, no agregarles. */
    cargar(chat) {
      estado = {...estado, chatId: chat.id,
                turnos: turnosDeHistorial(chat.messages),
                epoca: estado.epoca + 1};
      alCambiar(estado);
    },
```

- [ ] **Step 5: Implementar en `paneles.js`**

```js
/** El costo del turno, corriendo. Vacio antes del primer turno: una barra
 *  que dice "0 tokens" ocupa lugar para no decir nada. */
export function textoDeCosto(estado) {
  if (!estado || (!estado.ruta && !estado.tokens)) return "";
  const partes = [estado.ruta, estado.modelo,
                  `${NUMERO.format(estado.tokens || 0)} tokens`];
  if (estado.costo_usd) partes.push(`${estado.costo_usd.toFixed(4)} USD`);
  if (estado.cuenta) {
    partes.push(`paga ${estado.cuenta.split(":").pop()}` +
                (estado.costo_mm ? ` ${monedas(estado.costo_mm)}` : ""));
  }
  return partes.filter(Boolean).join(" · ");
}

/** La etiqueta de que departamento esta fijado como contexto. */
export function textoDeFoco(ficha) {
  if (!ficha) return "";
  return `<span>hablando sobre <b>${escapar(ficha.nombre)}</b>` +
         ` — saldo ${escapar(ficha.saldo)}</span>` +
         `<button type="button" data-accion="quitar">quitar</button>`;
}
```

con `NUMERO` arriba del archivo, junto al import de `monedas`:

```js
const NUMERO = new Intl.NumberFormat("es", {maximumFractionDigits: 0,
                                            useGrouping: "always"});
```

- [ ] **Step 6: Los nodos nuevos en `index.html` y su estilo**

En `index.html`, el panel del centro pasa a:

```html
  <main id="panel-centro" class="panel">
    <div class="titulo">
      <span>Calipso</span>
      <span id="costo" class="costo"></span>
    </div>
    <div id="foco" class="foco oculto"></div>
    <div id="conversacion" class="conversacion"></div>
    <div id="razonamiento" class="razonamiento oculto"></div>
    <form id="entrada" autocomplete="off">
      <input id="texto" type="text" placeholder="Escribi a Calipso">
      <button type="submit">Enviar</button>
    </form>
  </main>
```

y adentro de `.lienzo`, junto a la tarjeta:

```html
      <div id="empleado" class="tarjeta oculto"></div>
```

(`#razonamiento` y `#empleado` los usa la Task 9 y la Task 8; se declaran acá para no tocar el esqueleto tres veces.)

En `estilo.css`:

```css
.costo {
  color: var(--tenue); font-size: 11px; text-transform: none;
  letter-spacing: 0; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; max-width: 60%;
}

.foco {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; padding: 6px 10px; border-bottom: 1px solid var(--linea);
  background: #12161c; color: var(--tenue); font-size: 12px;
}
.foco b { color: var(--acento); font-weight: 600; }
.foco button {
  background: transparent; border: 1px solid var(--linea); color: var(--tenue);
  border-radius: 4px; padding: 2px 7px; font-size: 11px; cursor: pointer;
}
```

- [ ] **Step 7: Cablear `app.js`**

Sumar a los imports de `paneles.js`: `textoDeCosto, textoDeFoco`.

```js
const barraCosto = document.getElementById("costo");
const barraFoco = document.getElementById("foco");
let enFoco = null;            // el edificio tocado: contexto y pagador
let ultimaEpoca = 0;

function pintarFoco() {
  const ficha = (ciudad && enFoco) ? fichaDe(ciudad, enFoco) : null;
  barraFoco.classList.toggle("oculto", !ficha);
  barraFoco.innerHTML = ficha ? textoDeFoco(ficha) : "";
}

barraFoco.addEventListener("click", ev => {
  if (ev.target && ev.target.dataset.accion === "quitar") {
    enFoco = null;
    pintarFoco();
  }
});
```

En `soltar()`, donde el toque fija el resaltado, fijar también el foco:

```js
  if (tocado && !tocado.movio && punteros.size === 1 && ciudad) {
    resaltado = enPunto(ciudad, cam, mapa.vista(), tocado.x, tocado.y);
    pintarTarjeta(tocado.x, tocado.y);
    if (resaltado) {           // tocar un edificio lo fija como contexto
      enFoco = resaltado;      // y su billetera pasa a pagar (spec 8)
      pintarFoco();
    }
  }
```

En el callback de `crearChat`, pintar el costo y respetar la época:

```js
const chat = crearChat(estado => {
  if (estado.epoca !== ultimaEpoca) {
    // se cargo otro chat: los nodos del anterior no se reciclan
    ultimaEpoca = estado.epoca;
    nodosDeTurno.length = 0;
    avisoPasajero = null;
    conversacion.innerHTML = "";
  }
  pintarConversacion(estado.turnos);
  conversacion.scrollTop = conversacion.scrollHeight;
  formulario.classList.toggle("sin-conexion", !estado.conectado);
  campo.placeholder = estado.conectado
    ? "Escribi a Calipso" : "Sin conexion con Calipso";
  barraCosto.textContent = textoDeCosto(estado);
});
```

En el `submit`, mandar el foco: `if (chat.enviar(campo.value, enFoco)) {`.

Y la lista de chats, que ya se ve clickeable y ahora responde:

```js
listaChats.addEventListener("click", async ev => {
  const fila = ev.target && ev.target.dataset && ev.target.dataset.id
    ? ev.target : null;
  if (!fila) return;
  try {
    const r = await fetch(`/api/chats/${encodeURIComponent(fila.dataset.id)}/activate`,
                          {method: "POST"});
    if (!r.ok) return;
    chat.cargar(await r.json());
    fetch("/api/chats").then(x => (x.ok ? x.json() : null))
      .then(d => { if (d) pintarChats(d); });
  } catch (e) {
    // sin conexion no se cambia de chat; el que estaba sigue entero
  }
});
```

- [ ] **Step 8: Ajustar el doble de `fetch` en `arranque.test.js`**

El doble hoy cuelga **cualquier** URL que contenga `/api/chats`, y eso incluye el `activate`. Cambiar a la coincidencia exacta y agregar la respuesta del activate:

```js
  globalThis.fetch = (url, opciones) => {
    pedidos.push(String(url));
    // solo la lista cuelga: es el caso que este archivo fija (el mapa
    // arranca sin esperarla). El activate tiene que poder resolver
    if (String(url).endsWith("/api/chats")) return new Promise(() => {});
    if (String(url).includes("/activate")) {
      return Promise.resolve({ok: true, json: async () => (
        {id: "c9", title: "otro", messages: [{role: "user", text: "viejo"}]})});
    }
    return Promise.resolve({ok: true,
                            json: async () => ({activa: true,
                                                ciudad: ciudadDePrueba()})});
  };
```

Y sumar los ids nuevos a la lista de nodos del DOM de mentira: `"costo"`, `"foco"`, `"razonamiento"`, `"empleado"`. Sin esto, `document.getElementById` devuelve `null`, `app.js` explota al evaluar el módulo y **todos** los tests de `arranque.test.js` fallan de golpe.

- [ ] **Step 9: Correr los tests y ver que pasan**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py -q`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add calipso/web/fabrica/
git commit -m "feat(fabrica): el edificio tocado contextualiza, los chats se abren y el costo se ve"
```

---

### Task 8: Entrar a un departamento

Al cruzar el umbral de zoom el techo se desvanece y se ve el interior: un escritorio por empleado, con su estado. El "entrar" es un acercamiento continuo, no un cambio de pantalla.

El escritorio de un agente liberado queda vacío con su rastro, porque ver que el departamento **soltó** gente es tan informativo como verlo contratar.

**Files:**
- Create: `calipso/web/fabrica/interior.js`, `calipso/web/fabrica/interior.test.js`
- Modify: `calipso/web/fabrica/paleta.js`, `sprites.js`, `mapa.js`, `app.js`, `paneles.js`, `estilo.css`, `calipso/web/sw.js`
- Modify: `calipso/web/fabrica/sprites.test.js`, `lienzo.test.js`, `paneles.test.js`

**Interfaces:**
- Consumes: `empleadosDe`, `estadoVisible` (Task 6); `medidas`, `alturaDe`, `ANCHO`, `PROF`, `ALTO_PISO` de `sprites.js`; `aPantalla`, `escalaEntera` de `camara.js`.
- Produces:
  - `interior.UMBRAL`, `interior.opacidadDeTecho(escala) -> 0..1`
  - `interior.plazas(edificio) -> [{x, y}]` (en píxeles del sprite, de arriba hacia abajo y de izquierda a derecha)
  - `interior.escritorioEnPunto(edificio, cam, vista, px, py) -> indice | null`
  - `sprites.interiorSprite(edificio, estados) -> {ancho, alto, pix}`
  - `sprites.plazasDe(edificio) -> [{x, y}]`
  - `paleta.PISO`, `paleta.ESCRITORIO`, `paleta.OCUPADO`, `paleta.ESPERA`
  - `paneles.textoDeEmpleado(empleado) -> string` (se adelanta desde la Task 9: `app.js` lo importa acá)

- [ ] **Step 1: Escribir los tests del interior**

Crear `calipso/web/fabrica/interior.test.js`:

```js
/**
 * interior.test.js — La aritmetica de entrar a un departamento.
 *
 * El fundido y las plazas son numeros puros: lo unico que el navegador
 * agrega es pintarlos.
 */
import test from "node:test";
import assert from "node:assert/strict";

import {crearCamara} from "./camara.js";
import {UMBRAL, escritorioEnPunto, opacidadDeTecho, plazas} from "./interior.js";
import {ALTO_PISO, PROF, medidas} from "./sprites.js";

const EDIFICIO = {id: "dep:atlas", nombre: "atlas", zona: "fabrica",
                  estado: "activo", tamano: 3, actividad: 2, x: 0, y: 0};

test("el techo se desvanece cruzando el umbral, no de golpe", () => {
  assert.equal(opacidadDeTecho(UMBRAL - 1.5), 1);     // lejos: techo entero
  assert.equal(opacidadDeTecho(UMBRAL + 1), 0);       // adentro: sin techo
  const medio = opacidadDeTecho(UMBRAL - 0.4);
  assert.ok(medio > 0 && medio < 1, `fundido roto: ${medio}`);
  // y es monotono: acercarse nunca vuelve a tapar el interior
  assert.ok(opacidadDeTecho(UMBRAL - 0.2) < opacidadDeTecho(UMBRAL - 0.6));
});

test("hay una plaza por ventana y estan adentro del sprite", () => {
  const m = medidas(EDIFICIO);
  const p = plazas(EDIFICIO);
  assert.equal(p.length, 3 * 3);        // tres pisos, tres columnas
  for (const {x, y} of p) {
    assert.ok(x >= 0 && x < m.ancho, `x fuera del sprite: ${x}`);
    assert.ok(y >= PROF && y < m.alto, `y fuera del sprite: ${y}`);
  }
  // de arriba hacia abajo: el primer escritorio es el del piso mas alto
  assert.ok(p[0].y < p.at(-1).y);
  // y no hay dos en el mismo lugar
  assert.equal(new Set(p.map(q => `${q.x},${q.y}`)).size, p.length);
});

test("un edificio mas alto tiene mas plazas", () => {
  assert.ok(plazas({...EDIFICIO, tamano: 6}).length >
            plazas({...EDIFICIO, tamano: 2}).length);
});

test("el escritorio bajo el dedo es el que se toco", () => {
  const cam = crearCamara(0, 0, 4);
  const vista = {ancho: 400, alto: 300};
  const p = plazas(EDIFICIO);
  // el centro de la plaza 4, llevado a pantalla con la misma cuenta que
  // usa el dibujo, tiene que devolver 4 y no su vecina
  const m = medidas(EDIFICIO);
  const esc = Math.round(cam.escala);
  const x0 = vista.ancho / 2 - (m.ancho * esc) / 2;
  const y0 = vista.alto / 2 - m.alto * esc;
  const px = x0 + (p[4].x + 1.5) * esc;
  const py = y0 + (p[4].y + 1) * esc;
  assert.equal(escritorioEnPunto(EDIFICIO, cam, vista, px, py), 4);
  // afuera del edificio no hay escritorio
  assert.equal(escritorioEnPunto(EDIFICIO, cam, vista, 5, 5), null);
});
```

Y agregar a `sprites.test.js`, sumando primero a sus imports `OCUPADO, ESCRITORIO, ESPERA, PISO` de `./paleta.js` y `interiorSprite, plazasDe` de `./sprites.js`:

```js
test("el interior es el mismo edificio sin techo y con escritorios", () => {
  const edificio = {id: "dep:atlas", zona: "fabrica", estado: "activo",
                    tamano: 2, actividad: 3};
  const fuera = edificioSprite(edificio);
  const dentro = interiorSprite(edificio, ["razonando", "liberado"]);
  assert.equal(dentro.ancho, fuera.ancho);
  assert.equal(dentro.alto, fuera.alto);
  // el techo se fue: la fila de arriba del sprite queda transparente
  assert.ok(dentro.pix.slice(0, dentro.ancho).every(v => v === TRANSPARENTE));
  assert.ok(fuera.pix.slice(0, fuera.ancho).some(v => v !== TRANSPARENTE));
  // hay al menos un escritorio ocupado y uno vacio, que es lo que se pidio
  assert.ok(dentro.pix.includes(OCUPADO));
  assert.ok(dentro.pix.includes(ESCRITORIO));
});

test("los tres estados del spec se dibujan distintos", () => {
  const edificio = {id: "dep:atlas", zona: "fabrica", estado: "activo",
                    tamano: 2, actividad: 0};
  const s = interiorSprite(edificio, ["razonando", "esperando", "liberado"]);
  // razonando prendido, esperando ocupado pero apagado, liberado vacio: si
  // dos de los tres comparten indice, el mapa no distingue "esta pensando"
  // de "esta esperando", que es la mitad de para que sirve entrar
  assert.ok(s.pix.includes(OCUPADO), "falta el que razona");
  assert.ok(s.pix.includes(ESPERA), "falta el que espera");
  assert.ok(s.pix.includes(ESCRITORIO), "falta el escritorio vacio");
});

test("el mismo interior da siempre el mismo bitmap", () => {
  const edificio = {id: "dep:atlas", zona: "fabrica", estado: "activo",
                    tamano: 4, actividad: 1};
  assert.deepEqual(interiorSprite(edificio, ["razonando"]).pix,
                   interiorSprite(edificio, ["razonando"]).pix);
});

test("mas empleados que escritorios no desborda el sprite", () => {
  const edificio = {id: "dep:atlas", zona: "fabrica", estado: "activo",
                    tamano: 1, actividad: 0};
  const estados = new Array(50).fill("razonando");
  const dentro = interiorSprite(edificio, estados);
  assert.equal(dentro.pix.length, dentro.ancho * dentro.alto);
});
```

- [ ] **Step 2: Correr los tests y ver que fallan**

Run: `cd /var/home/pedro/calipso/calipso/web/fabrica && ~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test`
Expected: FAIL — `Cannot find module ./interior.js`

- [ ] **Step 3: Los índices nuevos de la paleta**

En `calipso/web/fabrica/paleta.js`:

```js
export const PISO = 8;
export const ESCRITORIO = 9;
export const OCUPADO = 10;
export const ESPERA = 11;
```

Son tres estados dibujables, no dos, porque la sección 9 del spec los enumera: `razonando`, `esperando` y `liberado`. Un escritorio ocupado por alguien que espera no se ve igual que uno donde alguien está pensando.

y en cada rampa, los tres colores (en `fabrica`, `personal` y `congelado`):

```js
  fabrica: {
    ...,
    [PISO]: "#141a21", [ESCRITORIO]: "#33414f", [OCUPADO]: "#ffd75f",
    [ESPERA]: "#6d7f92",
  },
  personal: {
    ...,
    [PISO]: "#1a1420", [ESCRITORIO]: "#4a3a58", [OCUPADO]: "#c9a3e0",
    [ESPERA]: "#8b74a0",
  },
  congelado: {
    ...,
    [PISO]: "#151515", [ESCRITORIO]: "#2b2b2b", [OCUPADO]: "#2b2b2b",
    [ESPERA]: "#2b2b2b",
  },
```

- [ ] **Step 4: `interiorSprite` en `sprites.js`**

```js
export const ESC_ANCHO = 3;
export const ESC_ALTO = 2;
export const ESC_COLS = 3;

/**
 * Donde va cada escritorio, en pixeles del sprite. Misma grilla que las
 * ventanas: una ventana prendida ES un escritorio ocupado, y que las dos
 * cosas coincidan es lo que hace que acercarse se lea como entrar.
 * De arriba hacia abajo, para que el que llego primero se siente arriba.
 */
export function plazasDe(edificio) {
  const pisos = pisosDe(edificio.tamano);
  const arriba = PROF;
  const salida = [];
  // p = 0 es el piso de mas arriba (la y mas chica), igual que en las
  // ventanas de `edificioSprite`. Recorrerlo al reves dejaria a p[0] abajo y
  // el contrato dice "de arriba hacia abajo"
  for (let p = 0; p < pisos; p++) {
    for (let c = 0; c < ESC_COLS; c++) {
      salida.push({x: 2 + c * 5, y: arriba + 2 + p * ALTO_PISO});
    }
  }
  return salida;
}

/**
 * El mismo edificio, sin techo y con la gente adentro. `estados` es la lista
 * de estados de los empleados, en el orden en que se sientan; los que no
 * entran no se dibujan (el popup igual los lista).
 */
export function interiorSprite(edificio, estados = []) {
  const {ancho, alto, altoFrente} = medidas(edificio);
  const pix = new Uint8Array(ancho * alto);
  const en = (x, y, v) => {
    if (x >= 0 && x < ancho && y >= 0 && y < alto) pix[y * ancho + x] = v;
  };
  const arriba = PROF;
  // el hueco: donde estaba la cara frontal ahora se ve el piso
  for (let y = arriba; y < arriba + altoFrente; y++)
    for (let x = 0; x < ANCHO; x++) en(x, y, PISO);
  // el contorno se queda: sin el, el edificio se funde con el de al lado
  for (let x = 0; x < ANCHO; x++) {
    en(x, arriba, BORDE);
    en(x, arriba + altoFrente - 1, BORDE);
  }
  for (let y = arriba; y < arriba + altoFrente; y++) {
    en(0, y, BORDE);
    en(ANCHO - 1, y, BORDE);
  }
  const plazas = plazasDe(edificio);
  for (let i = 0; i < plazas.length; i++) {
    const estado = estados[i];
    // tres estados, que son los que enumera el spec: el que piensa se ve
    // prendido, el que espera ocupado pero apagado, y el que se fue deja el
    // escritorio vacio — ver que el departamento SOLTO gente es tan
    // informativo como verlo contratar
    const v = estado === "razonando" ? OCUPADO
      : estado === "esperando" ? ESPERA : ESCRITORIO;
    for (let dy = 0; dy < ESC_ALTO; dy++)
      for (let dx = 0; dx < ESC_ANCHO; dx++)
        en(plazas[i].x + dx, plazas[i].y + dy, v);
  }
  return {ancho, alto, pix};
}
```

con `PISO`, `ESCRITORIO` y `OCUPADO` agregados al import de `paleta.js`.

- [ ] **Step 5: `interior.js`**

```js
/**
 * calipso/web/fabrica/interior.js — Entrar a un departamento.
 *
 * El "entrar" es un acercamiento continuo, no un cambio de pantalla: al
 * pasar el umbral el techo se desvanece y aparece el interior. Todo lo de
 * aca es aritmetica pura; el dibujo lo hace mapa.js.
 */
import {aPantalla, escalaEntera} from "./camara.js";
import {centroDe} from "./ciudad.js";
import {ESC_ALTO, ESC_ANCHO, medidas, plazasDe} from "./sprites.js";

export const UMBRAL = 3;        // escala a partir de la cual se esta adentro
export const FUNDIDO = 0.8;     // cuanto dura el desvanecido, en escala

/** 1 = techo entero, 0 = adentro. Monotona: acercarse nunca vuelve a tapar. */
export function opacidadDeTecho(escala) {
  if (escala >= UMBRAL) return 0;
  if (escala <= UMBRAL - FUNDIDO) return 1;
  return (UMBRAL - escala) / FUNDIDO;
}

export const plazas = plazasDe;

/** El indice del escritorio bajo el punto, o null. */
export function escritorioEnPunto(edificio, cam, vista, px, py) {
  const esc = escalaEntera(cam);
  const m = medidas(edificio);
  const p = aPantalla(cam, centroDe(edificio), vista);
  const x0 = p.x - (m.ancho * esc) / 2;
  const y0 = p.y - m.alto * esc;
  const lugares = plazasDe(edificio);
  for (let i = 0; i < lugares.length; i++) {
    const ex = x0 + lugares[i].x * esc, ey = y0 + lugares[i].y * esc;
    if (px >= ex && px < ex + ESC_ANCHO * esc &&
        py >= ey && py < ey + ESC_ALTO * esc) return i;
  }
  return null;
}
```

- [ ] **Step 6: El fundido en `mapa.js`**

`dibujar` recibe un argumento más: los empleados por departamento. Firma nueva:

```js
  function dibujar(ciudad, cam, resaltado = null, fase = 0, empleados = {}) {
```

y, adentro del bucle de edificios, después del `ctx.drawImage(r.lienzo, x, y)`:

```js
      // el interior: se pinta encima con la opacidad complementaria a la del
      // techo, asi entrar es un acercamiento y no un salto de pantalla
      const tapa = opacidadDeTecho(cam.escala);
      if (tapa < 1) {
        const dentro = rasterizarInterior(e, esc, empleados[e.id] || []);
        ctx.globalAlpha = 1 - tapa;
        ctx.drawImage(dentro.lienzo, x, y);
        ctx.globalAlpha = 1;
      }
```

`rasterizarInterior` es gemela de `rasterizar`, con la clave del cache incluyendo los estados (si no, el escritorio nunca se apaga):

```js
  function rasterizarInterior(e, esc, estados) {
    const clave = `i|${e.id}|${e.zona}|${e.estado}|${e.tamano}|${esc}|` +
                  estados.join(",");
    const guardado = cache.get(clave);
    if (guardado) return guardado;
    const sprite = interiorSprite(e, estados);
    const fuera = document.createElement("canvas");
    fuera.width = sprite.ancho * esc;
    fuera.height = sprite.alto * esc;
    const octx = fuera.getContext("2d");
    octx.imageSmoothingEnabled = false;
    pintar(octx, sprite, rampaDe(e), 0, 0, esc);
    const listo = {lienzo: fuera, ancho: fuera.width, alto: fuera.height};
    if (cache.size > 300) cache.clear();
    cache.set(clave, listo);
    return listo;
  }
```

con los imports correspondientes (`interiorSprite` de `sprites.js`, `opacidadDeTecho` de `interior.js`).

En `lienzo.test.js`: el contexto falso anota `drawImage` pero **no** anota la opacidad, y sin eso el test no puede distinguir el interior del exterior. Sumarle `globalAlpha` igual que hace con `fillStyle` — inicializarlo en `1` junto a `fillStyle: null` y anotarlo en la operación:

```js
    drawImage: (img, x, y) => ops.push({op: "drawImage", x, y,
                                        ancho: img.width, alto: img.height,
                                        globalAlpha: ctx.globalAlpha}),
```

Y agregar el test del fundido, con los helpers que el archivo ya tiene (`montar`, `edi`):

```js
test("adentro del umbral se pinta el interior encima de cada edificio", () => {
  const {lienzo, ctx} = montar();
  const mapa = crearMapa(lienzo);
  // un solo edificio, en el origen: a escala 4 los de ciudadDePrueba se van
  // de la vista y el dibujo los saltea, que es justo lo que se quiere contar
  const ciudad = {edificios: [edi("dep:a")], calles: [], unidades: [],
                  avisos: []};
  mapa.dibujar(ciudad, crearCamara(0, 0, 1), null, 0, {});
  const lejos = ctx.ops.filter(o => o.op === "drawImage").length;
  assert.equal(lejos, 1, "lejos se pinta solo el exterior");
  ctx.ops.length = 0;
  mapa.dibujar(ciudad, crearCamara(0, 0, UMBRAL + 1), null, 0,
               {"dep:a": ["razonando"]});
  const cerca = ctx.ops.filter(o => o.op === "drawImage");
  assert.equal(cerca.length, 2, "el interior no se pinto encima");
  assert.equal(cerca[1].globalAlpha, 1,
               "pasado el umbral el interior va opaco, no a medio fundir");
});
```

Sumar `UMBRAL` al import de `./interior.js` en la cabecera de `lienzo.test.js`.

- [ ] **Step 6b: El popup del empleado**

`app.js` va a importar `textoDeEmpleado` en el paso que sigue, así que la función tiene que existir antes: un `import` con nombre de algo que el módulo no exporta es un error de enlace y `app.js` no llega a evaluarse — se lleva puesta la app entera y todo `arranque.test.js` con ella.

Primero el test, en `paneles.test.js` (sumando `textoDeEmpleado` al import de `./paneles.js` de la cabecera, que hoy trae `{disposicion, textoDeTarjeta, posicionDeTarjeta, resumenDeAvisos, ANCHO_TELEFONO}` más lo que le agregó la Task 7):

```js
const EMPLEADO = {agente_id: "a1", rol: "scout", modelo: "sonnet",
                  estado: "razonando", texto: "mirando el libro",
                  tokens_in: 1200, tokens_out: 340, costo_mm: 270,
                  runtime_ms: 4500,
                  diff: {ruta: "calipso/mapa/ciudad.py", diff: "- a\n+ b"}};

test("el popup del empleado trae rol, modelo, runtime, tokens y costo", () => {
  const texto = textoDeEmpleado(EMPLEADO);
  assert.match(texto, /scout/);
  assert.match(texto, /sonnet/);
  assert.match(texto, /4,5 s/);              // runtime en segundos, no en ms
  assert.match(texto, /1\.200/);
  assert.match(texto, /0,27/);               // 270 milimonedas
  assert.match(texto, /ciudad\.py/);
});

test("un empleado liberado se ve liberado, no vacio", () => {
  const texto = textoDeEmpleado({...EMPLEADO, estado: "liberado",
                                 texto: "", diff: null});
  assert.match(texto, /liberado/);
  assert.ok(!texto.includes("undefined"), texto);
  assert.ok(!texto.includes("null"), texto);
});
```

Correlo y mirá que falle con `textoDeEmpleado is not defined`. Después, en `paneles.js`:

```js
const SEGUNDOS = new Intl.NumberFormat("es", {maximumFractionDigits: 1});

function segundos(ms) {
  return SEGUNDOS.format((ms || 0) / 1000) + " s";
}

/** El popup: lo que se ve del empleado sin abandonar el mapa. */
export function textoDeEmpleado(empleado) {
  if (!empleado) return "";
  const e = empleado;
  return `<div class="nombre">${escapar(e.rol || "agente")}</div>` +
    `<div class="estado ${escapar(e.estado)}">${escapar(e.estado)}</div>` +
    fila("modelo", e.modelo || "sin dato") +
    fila("corriendo", segundos(e.runtime_ms)) +
    fila("tokens", `${NUMERO.format(e.tokens_in || 0)} / ` +
                   `${NUMERO.format(e.tokens_out || 0)}`) +
    fila("costo", monedas(e.costo_mm || 0)) +
    (e.diff ? fila("toco", e.diff.ruta) : "");
}
```

`NUMERO`, `fila`, `escapar` y `monedas` ya están en el archivo: los tres últimos de antes, `NUMERO` desde la Task 7.

- [ ] **Step 7: Cablear el interior en `app.js`**

Los imports que hacen falta arriba del archivo:

```js
import {escritorioEnPunto, opacidadDeTecho} from "./interior.js";
```

y sumar `textoDeEmpleado` al import de `./paneles.js`.

El bucle de dibujo pasa los empleados, y el toque adentro abre el popup:

```js
  if (ciudad) {
    mapa.dibujar(ciudad, cam, resaltado, (ahora / 4000) % 1, plantel());
  }
```

```js
/** Los estados de cada departamento, en el orden en que se sientan. */
function plantel() {
  const ahora = Date.now();
  const salida = {};
  for (const dep of Object.keys(pulso.empleados)) {
    salida[dep] = empleadosDe(pulso, dep).map(e => estadoVisible(e, ahora));
  }
  return salida;
}
```

En `soltar()`, antes de fijar el foco, probar si el toque cayó en un escritorio. **Nada de `return` acá**: la cola de `soltar()` es la que suelta el puntero (`punteros.delete`, `pinza = null`, `releasePointerCapture`), y saltearla deja el puntero capturado para siempre — con mouse, el `pointerId` se reusa y el mapa queda pegado al cursor. Una bandera, no un `return`:

```js
    let tocoEmpleado = false;
    if (resaltado && opacidadDeTecho(cam.escala) < 1) {
      const i = escritorioEnPunto(ciudad.edificios.find(e => e.id === resaltado),
                                  cam, mapa.vista(), tocado.x, tocado.y);
      const gente = empleadosDe(pulso, resaltado);
      if (i !== null && gente[i]) {
        mostrarEmpleado(gente[i]);
        tocoEmpleado = true;   // tocar un empleado no cambia el contexto
      }
    }
    if (!tocoEmpleado) {
      popupEmpleado.classList.add("oculto");   // el toque afuera lo cierra
      if (resaltado) { enFoco = resaltado; pintarFoco(); }
    }
```

y entonces el bloque que la Task 7 puso en `soltar()` para fijar el foco (`if (resaltado) { enFoco = resaltado; pintarFoco(); }`) se borra: quedó absorbido acá arriba.

`mostrarEmpleado` la escribe la Task 9; por ahora, que pinte el popup:

```js
const popupEmpleado = document.getElementById("empleado");

function mostrarEmpleado(empleado) {
  popupEmpleado.innerHTML = textoDeEmpleado(empleado);
  popupEmpleado.classList.remove("oculto");
}
```

- [ ] **Step 8: `interior.js` entra en el SHELL**

Igual que `pulso.js` en la Task 6: `test_mapa_server.py` compara el SHELL contra los archivos reales del directorio. En `calipso/web/sw.js`, dentro de `SHELL`:

```js
  "/static/fabrica/pulso.js",
  "/static/fabrica/interior.js"
```

- [ ] **Step 9: Correr todo**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_fabrica_js.py test_mapa_server.py -q`
Expected: PASS

- [ ] **Step 10: Commit**

```bash
git add calipso/web/fabrica/ calipso/web/sw.js
git commit -m "feat(fabrica): entrar a un departamento — el techo se desvanece y hay escritorios"
```

---

### Task 9: El razonamiento en el panel central

Tocar un empleado convierte el panel del medio en su razonamiento en vivo: el stream del pulso, con runtime, tokens y el diff que dejó. Es lectura, no conversación; un botón vuelve al chat con Calipso (invariante 7).

**Files:**
- Modify: `calipso/web/fabrica/paneles.js`, `app.js`, `index.html`, `estilo.css`
- Modify: `calipso/web/fabrica/paneles.test.js`

**Interfaces:**
- Consumes: el contrato de empleado (Task 6); `#razonamiento` y `#empleado` (Task 7).
- Produces: `paneles.textoDeEmpleado(empleado) -> string`, `paneles.textoDeRazonamiento(empleado) -> string`.

- [ ] **Step 1: Escribir los tests**

Agregar a `paneles.test.js`, sumando primero `textoDeRazonamiento` al import de `./paneles.js` de la cabecera (la Task 8 ya le agregó `textoDeEmpleado`, y la constante `EMPLEADO` ya está en el archivo desde esa tarea):

```js
test("el razonamiento va con el diff y con el boton de volver", () => {
  const texto = textoDeRazonamiento(EMPLEADO);
  assert.match(texto, /mirando el libro/);
  assert.match(texto, /- a/);
  assert.match(texto, /data-accion="volver"/);
});

test("el texto del agente se escapa: lo escribe un modelo", () => {
  const texto = textoDeRazonamiento({...EMPLEADO,
                                     texto: '<script>alert(1)</script>'});
  assert.ok(!texto.includes("<script>"), texto);
});
```

- [ ] **Step 2: Correr y ver que falla**

Run: `cd /var/home/pedro/calipso/calipso/web/fabrica && ~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test`
Expected: FAIL — `textoDeEmpleado is not defined`

- [ ] **Step 3: Implementar en `paneles.js`**

El `textoDeEmpleado` ya está: lo adelantó la Task 8, que es donde `app.js` lo importa. Acá se le suma su hermano:

```js
/** El panel del medio: lectura, no conversacion. */
export function textoDeRazonamiento(empleado) {
  if (!empleado) return "";
  const e = empleado;
  const diff = e.diff
    ? `<div class="ruta">${escapar(e.diff.ruta)}</div>` +
      `<pre class="diff">${escapar(e.diff.diff)}</pre>`
    : "";
  return `<div class="cabecera">` +
    `<span>${escapar(e.rol || "agente")} — ${escapar(e.estado)}` +
    ` — ${escapar(e.modelo || "sin dato")}</span>` +
    `<button type="button" data-accion="volver">volver al chat</button>` +
    `</div>` +
    `<pre class="pensando">${escapar(e.texto || "")}</pre>` + diff;
}
```

- [ ] **Step 4: El panel y su estilo**

En `estilo.css`:

```css
/* el popup del empleado reusa .tarjeta, que es position:absolute sin
   coordenadas: sin esta regla cae en el flujo y aparece en cualquier lado */
#empleado { left: 10px; bottom: 10px; top: auto; max-width: 260px; }

.razonamiento { flex: 1; overflow-y: auto; padding: 10px; }
.razonamiento .cabecera {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; color: var(--tenue); margin-bottom: 10px;
}
.razonamiento .cabecera button {
  background: transparent; border: 1px solid var(--linea); color: var(--texto);
  border-radius: 4px; padding: 3px 8px; font-size: 11px; cursor: pointer;
}
.razonamiento .pensando { white-space: pre-wrap; margin: 0 0 12px; }
.razonamiento .ruta { color: var(--acento); font-size: 12px; }
.razonamiento .diff {
  background: var(--fondo); border: 1px solid var(--linea); border-radius: 4px;
  padding: 8px; overflow-x: auto; font-size: 12px; margin: 6px 0 0;
}
.tarjeta .estado { color: var(--tenue); margin-bottom: 5px; }
.tarjeta .estado.razonando { color: var(--aviso); }
.tarjeta .estado.liberado { color: var(--tenue); }
.tarjeta .estado.inactivo { color: #ff7b72; }

/* con el razonamiento abierto, el chat se esconde y la entrada tambien: es
   lectura, no una conversacion con el agente */
#panel-centro[data-modo="razonamiento"] .conversacion,
#panel-centro[data-modo="razonamiento"] #entrada { display: none; }
#panel-centro[data-modo="razonamiento"] #razonamiento { display: block; }
```

- [ ] **Step 5: Cablear en `app.js`**

Sumar `textoDeRazonamiento` al import de `./paneles.js`, y reemplazar el `mostrarEmpleado` provisorio de la Task 8 por este.

**Dónde va:** arriba del bloque `crearPulso(...)` de la Task 6, porque su callback llama a `pintarRazonamiento()` y una `function` se iza pero una `const` no: `panelCentro`, `panelRazonamiento` y `mirando` tienen que estar inicializadas antes de que el primer evento del pulso entre.

**Y el `classList`:** `.oculto` es `display: none !important` (`estilo.css:115`). La regla `#panel-centro[data-modo="razonamiento"] #razonamiento { display: block; }` no le gana a un `!important`, así que cambiar el `data-modo` no alcanza: hay que sacarle la clase al nodo, igual que se hace con el popup.

```js
const panelCentro = document.getElementById("panel-centro");
const panelRazonamiento = document.getElementById("razonamiento");
let mirando = null;             // agente_id que se esta leyendo

function mostrarEmpleado(empleado) {
  popupEmpleado.innerHTML = textoDeEmpleado(empleado);
  popupEmpleado.classList.remove("oculto");
  mirando = empleado.agente_id;
  pintarRazonamiento();
  panelRazonamiento.classList.remove("oculto");   // gana al display:none
  panelCentro.dataset.modo = "razonamiento";
  app.dataset.pestana = "chat";     // en el telefono, el panel del medio
}

function pintarRazonamiento() {
  if (!mirando) return;
  const todos = Object.keys(pulso.empleados)
    .flatMap(dep => empleadosDe(pulso, dep));
  const empleado = todos.find(e => e.agente_id === mirando);
  if (!empleado) return;            // el anillo lo olvido: se deja lo ultimo
  panelRazonamiento.innerHTML = textoDeRazonamiento(empleado);
  panelRazonamiento.scrollTop = panelRazonamiento.scrollHeight;
}

panelRazonamiento.addEventListener("click", ev => {
  if (ev.target && ev.target.dataset.accion === "volver") {
    mirando = null;
    panelCentro.dataset.modo = "chat";
    panelRazonamiento.classList.add("oculto");
    popupEmpleado.classList.add("oculto");
  }
});
```

y en el callback de `crearPulso`, después de guardar el estado, `pintarRazonamiento()` — así el panel se actualiza con cada chunk que publica el agente, que es lo que quiere decir "en vivo".

- [ ] **Step 6: Correr todo**

Run: `/var/home/pedro/calipso/.venv/bin/python -m pytest test_economia_*.py test_mapa_*.py test_fabrica_js.py test_resource_dispatcher.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add calipso/web/fabrica/
git commit -m "feat(fabrica): el panel del medio muestra el razonamiento del empleado"
```

---

## Verificación a ojo (una vez, al cerrar el plan)

Los tests cubren la lógica; lo que se mira es que el conjunto se lea. Levantar el servidor (`/var/home/pedro/calipso/.venv/bin/python calipso/server.py`), abrir `/fabrica` y, con la semana abierta:

1. Decirle a Calipso "miremos a atlas": la cámara vuela sola y en el texto **no** aparece ninguna marca rara.
2. Tocar un edificio: aparece la etiqueta de foco arriba del chat, y el turno siguiente termina con "paga atlas" en la barra de costo. `cat ~/.calipso/economia/libro.jsonl | tail -3` muestra el asiento.
3. Tocar "quitar" en la etiqueta: el turno siguiente ya no cobra a nadie.
4. Acercar el zoom sobre un departamento con agentes corriendo: el techo se desvanece, aparecen los escritorios, los ocupados se ven prendidos.
5. Tocar un empleado: el panel del medio pasa a su razonamiento y se ve crecer mientras piensa. "volver al chat" vuelve.
6. Clickear otro chat en la lista: la conversación se reemplaza entera, sin turnos del anterior colgados arriba.
7. Cortar el server y volver a levantarlo: el mapa sigue mostrando la foto mientras el pulso está caído, y cuando vuelve reconecta solo.
8. En el teléfono: la pestaña del mapa deja entrar a un departamento con pinza, y la barra de compuertas sigue visible.

## Riesgos declarados

- **El pulso se pierde en cada reinicio.** Es la invariante 5 y es deliberado, pero significa que después de reiniciar el server los escritorios están vacíos aunque haya agentes que quedaron corriendo en subprocesos.
- **`dispatch.py` corrido como CLI (otro proceso) no publica al pulso.** El server lo importa en proceso y por ahí sí se ve; la invocación desde la terminal no. Meterlo pedía un POST autenticado al server y no vale la superficie.
- **El agente del turno de chat se abre y se cierra a mano.** Un turno que revienta de una forma que no pasa por el `except` deja el agente sin `fin`; a los diez minutos la regla de inactividad lo marca y el escritorio se libera.
- **Entre dos sondeos del WS pueden perderse eventos** si se publicaron más de 500. El cliente se entera del estado igual con el próximo evento de ese agente.
- **Cobrar cada turno al departamento cambia la economía de verdad.** Un chat largo sobre atlas le gasta plata a atlas. Es lo que pide el spec ("lo que se gaste ahí lo paga Atlas") y el freno es que Pedro tiene que tocar el edificio para que pase.
- **La suscripción no reporta monedas.** `_cobrar_turno` devuelve 0 en la ruta de suscripción a propósito: se cobra en unidades de capacidad, no en monedas, y este plan no traduce una cosa en la otra. Como la suscripción es la ruta dominante del chat, la barra de costo va a decir "paga atlas" con 0 monedas la mayor parte del tiempo. El equivalente en milimonedas existe (`costo_api_mm_por_unidad` en `suscripciones.json`); traducirlo es un cambio de la economía, no del mapa.
- **La ficha deriva la ciudad entera en cada turno con foco.** Medido en el Plan 1: 162 ms con 71 edificios, con el candado del libro tomado. Sin foco no cuesta nada. Si molesta, la corrección va en `cola.pendientes()`, que es el O(E²) que la sección 12 bis ya tiene anotado.

## Fuera de alcance de este plan

- Persistir el pulso o reproducir la ciudad de hace tres semanas.
- Instrumentar `dispatch.py` como proceso aparte.
- Animar a los agentes caminando dentro del interior.
- Que un empleado se pueda chatear (invariante 7: la conversación es siempre con Calipso).
- Los cuatro residuales del Plan 2 que no son de acoplamiento: la cascada del CSS sigue sin test y el piso de tests de JavaScript sigue siendo un piso.
- Traducir las unidades de capacidad de una suscripción a monedas para la barra de costo.
- El campo `mision` que la sección 8 del spec le pide a la ficha: `deps.Departamento` no lo tiene (solo nombre, zona y cuatro perillas), así que `ficha.bloque` arma el contexto con lo que existe. Agregarlo es un campo nuevo en el registro y una migración del JSON.
- Todo lo que la sección 12 del spec de la economía difiere: mezcla multi-proveedor, capa de estilo, conectores externos y bancarios, puentes Atlas/research-court, clientes PWA/iPhone vía Tailscale.
