# El abismo 1a -- paquete, contrato y porton de medicion: plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El paquete `calipso/abismo/` completo y probado en aislado (gramatica de la marca, anillos, tres fuentes, resolvedor, contrato/indice) mas el banco de medicion corrido sobre el 7b local. Entregable final: los numeros para Pedro. NO cablea nada al chat vivo (eso es el plan 1b).

**Architecture:** Piezas puras con dependencias inyectadas (el molde de `calipso/privacidad/`): `marca.py` es la gramatica unica, `anillos.py` la frontera determinista, `fuentes.py` tres funciones que devuelven sub-bloques `(texto, anillo)`, `consulta.py` el resolvedor con fallo cerrado, `contrato.py` el texto que ensenara la marca al modelo. El banco (`experimentos/consulta_abismo.py`) copia el molde de `juez_privacidad.py` y usa el contrato real para medir si el 7b sabe consultar.

**Tech Stack:** Python 3 + pytest (suite en la raiz del repo), Ollama local (qwen2.5:7b) via `dispatch._http_post_json`, sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-07-abismo-consulta-design.md`

## Global Constraints

- SIN EMOJIS en codigo, tests, docs y salidas.
- NUNCA importar modulos de `calipso` fuera de pytest sin exportar `CALIPSO_HOME` a un temporal ANTES del import: muchos modulos congelan la constante al importarse y `memory.Scope.__init__` escribe en el home REAL (`conftest.py` de la raiz cubre solo a pytest; el banco se cubre solo, como `experimentos/juez_privacidad.py:42`).
- Cada test aisla con `tmp_path` + `monkeypatch.setattr` sobre las constantes YA CONGELADAS del modulo (`chats.CHAT_FILE`, `chronology.CALIPSO_HOME`); `setenv` solo no alcanza.
- Suite completa antes de CADA commit: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py` debe dar 0 failed.
- `git add` con rutas explicitas, nunca `-A` ni `.`.
- Constantes del spec, verbatim: `ABISMO_BLOQUE_MAX = 2000`; indice del contrato `<= 600` chars; `MAX_PREGUNTA = 160`; recall dirigido `n=12`, top 8, umbral `0.20`; banco `N = 6` corridas a temperatura 0 con `num_ctx` fijado (4096, como `juez_privacidad.py:394`).
- **Este plan NO toca `server.py`, `prompt_compiler.py` ni nada del camino vivo.** El contrato vive como funcion pura y solo el banco lo usa. Si el contrato entrara al prompt del chat sin el filtro del 1b, las marcas aparecerian VISIBLES en la conversacion.
- Fuentes con dependencias INYECTADAS (el `mem`, el `obtener` del catastro, el `brief` del repo): `calipso/abismo/` no importa `calipso.server` jamas.

---

### Task 1: La gramatica de la marca (`marca.py`)

**Files:**
- Create: `calipso/abismo/__init__.py` (vacio)
- Create: `calipso/abismo/marca.py`
- Test: `test_abismo_marca.py`

**Interfaces:**
- Consumes: nada.
- Produces: `FUENTES: tuple[str,...] = ("memoria","chats","proyecto")`; `MAX_PREGUNTA = 160`; `ABRE = "⟦"`, `CIERRA = "⟧"`; `PATRON: re.Pattern` (la regex unica de la gramatica, compartida por el filtro del 1b y el banco); `Marca` (dataclass frozen con `fuente: str`, `resto: str`); `parsear(cuerpo: str) -> Marca | None`; `encontrar(texto: str) -> list[Marca | None]` (una entrada por marca hallada; `None` = ilegible).

- [ ] **Step 1: Write the failing test**

```python
# test_abismo_marca.py
"""La gramatica cerrada de la marca del abismo (spec seccion 5)."""
from calipso.abismo import marca


def test_marca_valida_por_fuente():
    m = marca.parsear("memoria que le gusta leer a Pedro")
    assert m == marca.Marca(fuente="memoria", resto="que le gusta leer a Pedro")
    m = marca.parsear("chats agosto libro desde:2026-08 hasta:2026-08")
    assert m.fuente == "chats"
    m = marca.parsear("proyecto calipso")
    assert m == marca.Marca(fuente="proyecto", resto="calipso")


def test_fuente_desconocida_es_ilegible():
    assert marca.parsear("memorai que dije ayer") is None      # typo: NO cae a memoria
    assert marca.parsear("fondo algo") is None                 # fuente de otra rebanada
    assert marca.parsear("") is None


def test_sin_resto_es_ilegible():
    assert marca.parsear("memoria") is None
    assert marca.parsear("proyecto   ") is None


def test_tope_de_pregunta():
    assert marca.parsear("memoria " + "x" * 152) is None       # cuerpo > 160
    assert marca.parsear("memoria " + "x" * 100) is not None


def test_encontrar_en_texto():
    texto = ("Dejame ver ⟦abismo:chats libro agosto⟧ y tambien "
             "⟦abismo:zzz nada⟧ al final.")
    marcas = marca.encontrar(texto)
    assert len(marcas) == 2
    assert marcas[0] == marca.Marca(fuente="chats", resto="libro agosto")
    assert marcas[1] is None                                   # ilegible, cuenta para aviso


def test_encontrar_sin_marcas():
    assert marca.encontrar("un texto cualquiera sin marcas") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test_abismo_marca.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'calipso.abismo'`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/abismo/marca.py
"""La gramatica de la marca del abismo -- spec 2026-09-07, seccion 5.

Gramatica CERRADA y en un solo lugar: esta regex la comparten el filtro de
streaming (plan 1b) y el detector one-shot del banco. No hay fallback "sin
fuente cae a memoria": lo que no matchea la lista es ilegible, se retira con
aviso y se mide como tal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ABRE = "⟦"    # los mismos corchetes que la marca de foco (mapa/foco.py)
CIERRA = "⟧"
FUENTES = ("memoria", "chats", "proyecto")
MAX_PREGUNTA = 160  # chars del cuerpo entre "abismo:" y el cierre

# El cuerpo no puede contener el corchete de cierre; el tope de la regex va
# holgado (el exacto lo valida parsear) para que una marca larga se detecte
# como marca ilegible y no se escape entera al texto.
PATRON = re.compile(
    re.escape(ABRE) + r"abismo:([^" + CIERRA + r"]{1,400})" + re.escape(CIERRA))


@dataclass(frozen=True)
class Marca:
    fuente: str
    resto: str


def parsear(cuerpo: str) -> Marca | None:
    """El cuerpo es lo que va entre 'abismo:' y el cierre. None = ilegible."""
    cuerpo = cuerpo.strip()
    if not cuerpo or len(cuerpo) > MAX_PREGUNTA:
        return None
    partes = cuerpo.split(None, 1)
    fuente = partes[0].lower()
    if fuente not in FUENTES:
        return None
    resto = partes[1].strip() if len(partes) > 1 else ""
    if not resto:
        return None  # toda fuente exige contenido (proyecto: al menos el nombre)
    return Marca(fuente=fuente, resto=resto)


def encontrar(texto: str) -> list[Marca | None]:
    """Todas las marcas de un texto, en orden. None por cada ilegible."""
    return [parsear(m.group(1)) for m in PATRON.finditer(texto)]
```

Y `calipso/abismo/__init__.py` vacio.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest test_abismo_marca.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Full suite + commit**

```bash
.venv/bin/python -m pytest -q --ignore=test_chat_live.py
git add calipso/abismo/__init__.py calipso/abismo/marca.py test_abismo_marca.py
git commit -m "feat(abismo): la gramatica cerrada de la marca (fuentes tipadas, sin fallback)"
```

---

### Task 2: Los anillos (`anillos.py`)

**Files:**
- Create: `calipso/abismo/anillos.py`
- Test: `test_abismo_anillos.py`

**Interfaces:**
- Consumes: nada.
- Produces: `ORILLA = 1`, `MEDIA_AGUA = 2`, `HONDO = 3`; `PISO_FUENTE: dict[str, int]`; `piso(fuente: str) -> int`; `puede_preguntar(anillo: int, consumidor: str) -> bool`; `puede_viajar(anillo: int, destino: str) -> bool`.

- [ ] **Step 1: Write the failing test**

```python
# test_abismo_anillos.py
"""La frontera determinista por profundidad (spec seccion 6)."""
from calipso.abismo import anillos


def test_pisos_por_fuente():
    assert anillos.piso("proyecto") == anillos.ORILLA
    assert anillos.piso("chats") == anillos.MEDIA_AGUA
    assert anillos.piso("memoria") == anillos.MEDIA_AGUA


def test_fuente_desconocida_cae_a_lo_hondo():
    # Fallo cerrado: lo que no se conoce se trata como lo mas delicado.
    assert anillos.piso("fondo") == anillos.HONDO


def test_solo_el_chat_pregunta_en_esta_rebanada():
    for a in (anillos.ORILLA, anillos.MEDIA_AGUA, anillos.HONDO):
        assert anillos.puede_preguntar(a, "chat") is True
        assert anillos.puede_preguntar(a, "jefe") is False
        assert anillos.puede_preguntar(a, "lector") is False


def test_a_la_nube_no_viaja_nada_en_esta_rebanada():
    # La politica (anillo 3 jamas, 1-2 redactados) es de rebanadas futuras;
    # aca la consulta no corre en /nube, asi que el viaje a nube es False
    # para TODO anillo (spec seccion 8).
    for a in (anillos.ORILLA, anillos.MEDIA_AGUA, anillos.HONDO):
        assert anillos.puede_viajar(a, "local") is True
        assert anillos.puede_viajar(a, "nube") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test_abismo_anillos.py -v`
Expected: FAIL con `ImportError: cannot import name 'anillos'` (o ModuleNotFoundError)

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/abismo/anillos.py
"""Los anillos: la frontera determinista por profundidad (spec seccion 6).

El piso es de la FUENTE; el juez de calipso/privacidad solo puede hundir un
sub-bloque concreto (nunca subirlo), y se aplica ANTES de puede_viajar. La
clase credencial no es un anillo: corta el envio entero (regla del ruteo).
"""
from __future__ import annotations

ORILLA = 1      # detalle de proyectos/repos
MEDIA_AGUA = 2  # historial de chats, memoria episodica
HONDO = 3       # core curado, cronologia, lo humano-sensible

PISO_FUENTE = {"proyecto": ORILLA, "chats": MEDIA_AGUA, "memoria": MEDIA_AGUA}


def piso(fuente: str) -> int:
    """Fallo cerrado: fuente desconocida se trata como lo mas hondo."""
    return PISO_FUENTE.get(fuente, HONDO)


def puede_preguntar(anillo: int, consumidor: str) -> bool:
    """Rebanada 1: el unico consumidor cableado es el chat de Pedro."""
    return consumidor == "chat"


def puede_viajar(anillo: int, destino: str) -> bool:
    """Rebanada 1: la consulta no corre en turnos /nube (spec seccion 8),
    asi que a "nube" no viaja nada. La firma completa queda para que las
    rebanadas 2 y 4 implementen la politica (3 jamas; 1-2 redactados)."""
    return destino == "local"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest test_abismo_anillos.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Full suite + commit**

```bash
.venv/bin/python -m pytest -q --ignore=test_chat_live.py
git add calipso/abismo/anillos.py test_abismo_anillos.py
git commit -m "feat(abismo): anillos -- piso por fuente, frontera determinista de rebanada 1"
```

---

### Task 3: `chats.todos()` y la fuente `chats` (busqueda lexica)

**Files:**
- Modify: `calipso/chats.py` (agregar `todos()` al final, junto a `list_chats`)
- Create: `calipso/abismo/fuentes.py`
- Test: `test_abismo_fuentes.py`

**Interfaces:**
- Consumes: `calipso.chats._load()` (via la nueva `todos()`), `anillos.MEDIA_AGUA`.
- Produces: `chats.todos() -> list[dict]` (los chats completos, con `messages`); `fuentes.chats_viejos(resto: str) -> list[tuple[str, int]]` (fragmentos `[titulo fecha] texto`, mas reciente primero, tope 8 fragmentos, anillo MEDIA_AGUA); helpers privados `fuentes._rango(resto) -> tuple[str|None, str|None, str]` y `fuentes._palabras(texto) -> set[str]` que las Tasks 5 y 6 reusan.

- [ ] **Step 1: Write the failing test**

```python
# test_abismo_fuentes.py
"""Las fuentes del abismo devuelven sub-bloques (texto, anillo) -- spec 6-7."""
import json

from calipso import chats
from calipso.abismo import anillos, fuentes


def _sembrar_chats(tmp_path, monkeypatch):
    data = {"active": "c1", "chats": {
        "c1": {"id": "c1", "title": "lecturas", "messages": [
            {"role": "user", "text": "empece El nombre de la rosa", "meta": {},
             "ts": "2026-08-03T10:00:00"},
            {"role": "assistant", "text": "buen libro", "meta": {},
             "ts": "2026-08-03T10:00:05"},
            {"role": "user", "text": "/redacta hola", "meta": {},
             "ts": "2026-08-04T10:00:00"},
        ]},
        "c2": {"id": "c2", "title": "compras", "messages": [
            {"role": "user", "text": "el libro de cocina llego roto", "meta": {},
             "ts": "2026-09-01T09:00:00"},
        ]},
    }}
    f = tmp_path / "chats.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(chats, "CHAT_FILE", f)


def test_todos_devuelve_chats_completos(tmp_path, monkeypatch):
    _sembrar_chats(tmp_path, monkeypatch)
    todos = chats.todos()
    assert {c["id"] for c in todos} == {"c1", "c2"}
    assert todos[0]["messages"]  # completos, no el conteo de list_chats


def test_chats_viejos_busca_por_palabra(tmp_path, monkeypatch):
    _sembrar_chats(tmp_path, monkeypatch)
    bloques = fuentes.chats_viejos("libro")
    assert bloques and all(a == anillos.MEDIA_AGUA for _, a in bloques)
    textos = "\n".join(t for t, _ in bloques)
    assert "El nombre de la rosa" in textos
    assert "cocina" in textos
    assert "[lecturas 2026-08-03]" in textos  # titulo y fecha del fragmento


def test_chats_viejos_respeta_rango(tmp_path, monkeypatch):
    _sembrar_chats(tmp_path, monkeypatch)
    bloques = fuentes.chats_viejos("libro desde:2026-09")
    textos = "\n".join(t for t, _ in bloques)
    assert "cocina" in textos
    assert "rosa" not in textos


def test_chats_viejos_ignora_gestos(tmp_path, monkeypatch):
    _sembrar_chats(tmp_path, monkeypatch)
    bloques = fuentes.chats_viejos("redacta")
    assert bloques == []  # los mensajes que empiezan con "/" no se pescan


def test_rango_parsea_y_limpia():
    desde, hasta, palabras = fuentes._rango("libro desde:2026-08 hasta:2026-09 rosa")
    assert (desde, hasta) == ("2026-08", "2026-09")
    assert "desde:" not in palabras and "libro" in palabras and "rosa" in palabras
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test_abismo_fuentes.py -v`
Expected: FAIL con `AttributeError: module 'calipso.chats' has no attribute 'todos'`

- [ ] **Step 3: Write minimal implementation**

En `calipso/chats.py`, al final:

```python
def todos() -> list[dict]:
    """Todos los chats completos (con mensajes). Para la fuente `chats` del
    abismo: la busqueda lexica necesita el texto, no el conteo de list_chats."""
    return list(_load()["chats"].values())
```

Y `calipso/abismo/fuentes.py`:

```python
# calipso/abismo/fuentes.py
"""Las fuentes del abismo -- spec 2026-09-07, secciones 6-7.

Cada fuente devuelve una LISTA de sub-bloques (texto, anillo): una misma
fuente puede pescar profundidades distintas. Dependencias INYECTADAS (mem,
obtener, brief): este modulo no importa calipso.server jamas.
"""
from __future__ import annotations

import re

from calipso import chats
from calipso.abismo import anillos

CHATS_MAX_FRAGMENTOS = 8
CHATS_FRAGMENTO_CHARS = 200

_RANGO = re.compile(r"\b(desde|hasta):(\d{4}-\d{2})\b")


def _rango(resto: str) -> tuple[str | None, str | None, str]:
    """Extrae la mini-sintaxis desde:/hasta: (spec seccion 5). Lo que no
    parsea queda como palabras: sin interpretacion de fechas en lenguaje
    natural ("agosto" es una palabra, no un rango)."""
    desde = hasta = None
    for m in _RANGO.finditer(resto):
        if m.group(1) == "desde":
            desde = m.group(2)
        else:
            hasta = m.group(2)
    palabras = _RANGO.sub(" ", resto)
    return desde, hasta, " ".join(palabras.split())


def _palabras(texto: str) -> set[str]:
    """Claves de busqueda: palabras de 4+ letras, en minusculas."""
    return set(re.findall(r"[0-9a-za-ÿ]{4,}", texto.lower()))


def chats_viejos(resto: str) -> list[tuple[str, int]]:
    """Busqueda lexica sobre chats.json, mas alla del historial del turno."""
    desde, hasta, palabras = _rango(resto)
    claves = _palabras(palabras)
    if not claves:
        return []
    hallados = []  # (ts, fragmento)
    for chat in chats.todos():
        titulo = (chat.get("title") or "?").strip()
        for msg in chat.get("messages", []):
            texto = (msg.get("text") or "").strip()
            if not texto or texto.startswith("/"):
                continue  # los gestos no se pescan (la leccion de voz._es_util)
            ts = msg.get("ts") or ""
            mes = ts[:7]
            if desde and mes and mes < desde:
                continue
            if hasta and mes and mes > hasta:
                continue
            if not (_palabras(texto) & claves):
                continue
            frag = f"[{titulo} {ts[:10]}] {texto[:CHATS_FRAGMENTO_CHARS]}"
            hallados.append((ts, frag))
    hallados.sort(reverse=True)  # mas reciente primero
    return [(frag, anillos.MEDIA_AGUA)
            for _, frag in hallados[:CHATS_MAX_FRAGMENTOS]]
```

Nota sobre la regex de `_palabras`: el rango `a-ÿ` cubre las vocales
acentuadas y la enie sin depender del modulo `unicodedata`; verificar en el
test que "cocina" y "rosa" matchean.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest test_abismo_fuentes.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Full suite + commit**

```bash
.venv/bin/python -m pytest -q --ignore=test_chat_live.py
git add calipso/chats.py calipso/abismo/fuentes.py test_abismo_fuentes.py
git commit -m "feat(abismo): fuente chats -- busqueda lexica con desde:/hasta: sobre chats.json"
```

---

### Task 4: Recall por ambito en `memory.py`

**Files:**
- Modify: `calipso/memory.py:201-206` (la firma de `Memory.recall`)
- Test: `test_abismo_memoria_recall.py`

**Interfaces:**
- Consumes: `Memory._scopes` (existente).
- Produces: `Memory.recall(query: str, n: int = 5, ambitos: tuple[str, ...] | None = None) -> list[dict]` -- con `ambitos=None` la conducta es EXACTAMENTE la de hoy (fusiona todos los scopes); con `ambitos=("global",)` consulta solo esos scopes por su `name`. Es el unico cambio en `memory.py` que el spec autoriza (seccion 7).

- [ ] **Step 1: Write the failing test**

```python
# test_abismo_memoria_recall.py
"""Memory.recall abierto a consultas por ambito (spec seccion 7).

Sin chroma ni embeddings: se prueba el ruteo de scopes con dobles, porque
construir Memory real descarga el modelo de embeddings y abre clientes.
"""
from calipso import memory


class _FalsoScope:
    def __init__(self, name, hits):
        self.name = name
        self._hits = hits

    def recall(self, query, n):
        return [dict(h, scope=self.name) for h in self._hits]


def _mem_doble():
    m = memory.Memory.__new__(memory.Memory)
    m.glob = _FalsoScope("global", [{"text": "g1", "score": 0.9},
                                    {"text": "g2", "score": 0.5}])
    m.project = _FalsoScope("project", [{"text": "p1", "score": 0.7}])
    m._deps = {}
    return m


def test_sin_ambitos_es_la_conducta_de_hoy():
    hits = _mem_doble().recall("q", n=3)
    assert [h["text"] for h in hits] == ["g1", "p1", "g2"]  # fusion por score


def test_ambitos_filtra_por_nombre():
    hits = _mem_doble().recall("q", n=5, ambitos=("global",))
    assert {h["scope"] for h in hits} == {"global"}


def test_ambito_inexistente_devuelve_vacio():
    assert _mem_doble().recall("q", n=5, ambitos=("departamento:taller",)) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test_abismo_memoria_recall.py -v`
Expected: FAIL con `TypeError: recall() got an unexpected keyword argument 'ambitos'`

- [ ] **Step 3: Write minimal implementation**

Reemplazar `Memory.recall` (`calipso/memory.py:201-206`) por:

```python
    def recall(self, query: str, n: int = 5,
               ambitos: tuple[str, ...] | None = None) -> list[dict]:
        """ambitos=None: la fusion de siempre (global+proyecto). Con ambitos,
        solo los scopes nombrados -- la consulta dirigida del abismo. El
        umbral sigue viviendo en el llamador (server.py para el turno,
        abismo/fuentes.py para la consulta)."""
        scopes = [s for s in self._scopes
                  if ambitos is None or s.name in ambitos]
        hits = []
        for s in scopes:
            hits += s.recall(query, n)
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:n]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest test_abismo_memoria_recall.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Full suite + commit**

La suite completa es OBLIGATORIA aca: `recall` lo llama `_build_context` en el camino vivo y el default tiene que seguir identico.

```bash
.venv/bin/python -m pytest -q --ignore=test_chat_live.py
git add calipso/memory.py test_abismo_memoria_recall.py
git commit -m "feat(memoria): recall acepta ambitos -- la consulta dirigida del abismo, default intacto"
```

---

### Task 5: La fuente `memoria`

**Files:**
- Modify: `calipso/abismo/fuentes.py` (agregar la fuente memoria y `_extracto`)
- Test: `test_abismo_fuentes.py` (ampliar)

**Interfaces:**
- Consumes: `Memory.recall(query, n, ambitos)` de la Task 4; `_palabras` de la Task 3; `calipso.chronology.load`.
- Produces: `fuentes.memoria(pregunta: str, mem, consolidado: str | None = None, zona_chat: str = "fabrica") -> list[tuple[str, int]]` -- recall dirigido (anillo MEDIA_AGUA) + extractos del core y la cronologia (anillo HONDO) + el consolidado personal SOLO en zona personal (anillo HONDO); `fuentes._extracto(texto: str, pregunta: str, max_lineas: int = 12) -> str`. Constantes: `RECALL_N = 12`, `RECALL_TOP = 8`, `RECALL_UMBRAL = 0.20`.

- [ ] **Step 1: Write the failing test** (agregar a `test_abismo_fuentes.py`)

```python
from calipso import chronology


class _FalsaMemoria:
    """Doble de Memory: solo lo que la fuente usa (recall + load_core)."""

    def __init__(self, hits, core=""):
        self._hits, self._core = hits, core
        self.pedido = None

    def recall(self, query, n=5, ambitos=None):
        self.pedido = {"query": query, "n": n, "ambitos": ambitos}
        return self._hits

    def load_core(self):
        return self._core


def test_memoria_recall_dirigido_sin_techos_del_turno(tmp_path, monkeypatch):
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    hits = [{"text": f"hecho {i}", "score": 0.9 - i * 0.1, "scope": "global"}
            for i in range(10)]  # los dos ultimos quedan bajo el umbral 0.20
    mem = _FalsaMemoria(hits)
    bloques = fuentes.memoria("que hago los domingos", mem)
    assert mem.pedido["n"] == fuentes.RECALL_N          # 12, no los 8 del turno
    episodico = [t for t, a in bloques if a == anillos.MEDIA_AGUA]
    assert len(episodico) == 1
    assert "hecho 0" in episodico[0]
    assert "hecho 8" not in episodico[0]                 # score 0.1 < 0.20
    assert "hecho 9" not in episodico[0]


def test_memoria_extractos_del_core_van_al_anillo_hondo(tmp_path, monkeypatch):
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    core = ("### perfil\n- A Pedro le gusta leer novela historica\n"
            "- Toma cafe sin azucar\n")
    mem = _FalsaMemoria([], core=core)
    bloques = fuentes.memoria("que novela le gusta", mem)
    hondos = [t for t, a in bloques if a == anillos.HONDO]
    assert any("novela historica" in t for t in hondos)
    assert not any("cafe" in t for t in hondos)          # linea sin clave no entra


def test_memoria_consolidado_solo_en_zona_personal(tmp_path, monkeypatch):
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    mem = _FalsaMemoria([])
    con = fuentes.memoria("plata", mem, consolidado="neto: 100",
                          zona_chat="personal")
    sin = fuentes.memoria("plata", mem, consolidado="neto: 100",
                          zona_chat="fabrica")
    assert any("neto: 100" in t and a == anillos.HONDO for t, a in con)
    assert not any("neto" in t for t, _ in sin)


def test_extracto_sin_claves_devuelve_vacio():
    assert fuentes._extracto("linea uno\nlinea dos", "a el de") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test_abismo_fuentes.py -v`
Expected: FAIL con `AttributeError: module ... has no attribute 'memoria'`

- [ ] **Step 3: Write minimal implementation** (agregar a `calipso/abismo/fuentes.py`)

```python
from calipso import chronology

RECALL_N = 12       # spec seccion 7: sin los techos del turno (turno: n=8/top4)
RECALL_TOP = 8
RECALL_UMBRAL = 0.20  # el del turno es RECALL_MIN_SCORE=0.30


def _extracto(texto: str, pregunta: str, max_lineas: int = 12) -> str:
    """Lineas del texto que comparten alguna clave con la pregunta. La fuente
    puede LEER el core entero (sin el truncado a 3000 del turno); lo que entra
    al bloque son los renglones relevantes, no el archivo."""
    claves = _palabras(pregunta)
    if not claves:
        return ""
    lineas = [ln for ln in texto.splitlines()
              if not ln.startswith("#") and (_palabras(ln) & claves)]
    return "\n".join(lineas[:max_lineas])


def memoria(pregunta: str, mem, consolidado: str | None = None,
            zona_chat: str = "fabrica") -> list[tuple[str, int]]:
    """Recall dirigido + extractos de core/cronologia. El consolidado del
    libro personal conserva su frontera de zona (spec seccion 6 e invariante
    del spec de proyectos): solo en chats de zona personal."""
    bloques: list[tuple[str, int]] = []
    hits = [h for h in mem.recall(pregunta, n=RECALL_N)
            if h.get("score", 0) >= RECALL_UMBRAL][:RECALL_TOP]
    if hits:
        lineas = "\n".join(f"- {h['text']}" for h in hits)
        bloques.append((f"recuerdos:\n{lineas}", anillos.MEDIA_AGUA))
    if (core := _extracto(mem.load_core(), pregunta)):
        bloques.append((f"del core:\n{core}", anillos.HONDO))
    crono = chronology.load(limit=200)
    lineas_crono = "\n".join(
        e["raw"] for e in crono["entries"]
        if _palabras(e.get("text", "")) & _palabras(pregunta))
    if lineas_crono:
        bloques.append((f"cronologia:\n{lineas_crono}", anillos.HONDO))
    if consolidado and zona_chat == "personal":
        bloques.append((f"libro personal (consolidado):\n{consolidado}",
                        anillos.HONDO))
    return bloques
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest test_abismo_fuentes.py -v`
Expected: PASS (los 5 de la Task 3 + estos 4)

- [ ] **Step 5: Full suite + commit**

```bash
.venv/bin/python -m pytest -q --ignore=test_chat_live.py
git add calipso/abismo/fuentes.py test_abismo_fuentes.py
git commit -m "feat(abismo): fuente memoria -- recall dirigido, extractos hondos, frontera de zona del consolidado"
```

---

### Task 6: La fuente `proyecto`

**Files:**
- Modify: `calipso/abismo/fuentes.py` (agregar la fuente proyecto)
- Test: `test_abismo_fuentes.py` (ampliar)

**Interfaces:**
- Consumes: `anillos.ORILLA`; los callables inyectados con la forma de `catastro.obtener(nombre) -> dict | None` (el dict trae `"ruta"`) y `server._repo_brief(raiz: pathlib.Path) -> str` (inyectado en el 1b; en tests, un fake).
- Produces: `fuentes.proyecto(resto: str, obtener, brief) -> list[tuple[str, int]]` -- el nombre es el primer token del resto, la pregunta extra se IGNORA en v1 (el brief entero va; spec seccion 5); nombre desconocido levanta `ValueError` (el resolvedor lo convierte en fallo suave).

- [ ] **Step 1: Write the failing test** (agregar a `test_abismo_fuentes.py`)

```python
import pathlib

import pytest


def test_proyecto_devuelve_brief_en_la_orilla():
    obtener = lambda nombre: ({"nombre": "calipso", "ruta": "/tmp/x"}
                              if nombre == "calipso" else None)
    brief = lambda raiz: f"brief de {raiz}"
    bloques = fuentes.proyecto("calipso que rutas tiene", obtener, brief)
    assert bloques == [("proyecto calipso:\nbrief de /tmp/x", anillos.ORILLA)]


def test_proyecto_desconocido_levanta():
    with pytest.raises(ValueError):
        fuentes.proyecto("inexistente", lambda n: None, lambda r: "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test_abismo_fuentes.py -v`
Expected: FAIL con `AttributeError: module ... has no attribute 'proyecto'`

- [ ] **Step 3: Write minimal implementation** (agregar a `calipso/abismo/fuentes.py`; `import pathlib` arriba)

```python
def proyecto(resto: str, obtener, brief) -> list[tuple[str, int]]:
    """El detalle de un repo del catastro, sin mover ROOT (la logica de
    api_catastro_detalle, con el brief inyectado). v1: el primer token es el
    nombre; la pregunta extra se ignora y va el brief entero."""
    nombre = resto.split()[0]
    p = obtener(nombre)
    if p is None:
        raise ValueError(f"el proyecto {nombre!r} no esta en el catastro")
    texto = brief(pathlib.Path(p["ruta"]))
    return [(f"proyecto {nombre}:\n{texto}", anillos.ORILLA)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest test_abismo_fuentes.py -v`
Expected: PASS (11 tests acumulados)

- [ ] **Step 5: Full suite + commit**

```bash
.venv/bin/python -m pytest -q --ignore=test_chat_live.py
git add calipso/abismo/fuentes.py test_abismo_fuentes.py
git commit -m "feat(abismo): fuente proyecto -- el brief del catastro con dependencias inyectadas"
```

---

### Task 7: El resolvedor (`consulta.py`)

**Files:**
- Create: `calipso/abismo/consulta.py`
- Test: `test_abismo_consulta.py`

**Interfaces:**
- Consumes: `marca.Marca`, las tres fuentes de `fuentes.py`.
- Produces: `ABISMO_BLOQUE_MAX = 2000` (env-overridable `ABISMO_BLOQUE_MAX`); `resolver(m: marca.Marca, *, mem=None, obtener=None, brief=None, consolidado=None, zona_chat="fabrica") -> dict` con claves `estado` ("pescado" | "fallo"), `fuente`, `texto` (el bloque armado y etiquetado, `<= ABISMO_BLOQUE_MAX`), `bloques` (los sub-bloques crudos `(texto, anillo)`), `aviso` (vacio si pescado). NUNCA levanta: cualquier excepcion de una fuente degrada a `estado="fallo"` (invariante 4 del spec).

- [ ] **Step 1: Write the failing test**

```python
# test_abismo_consulta.py
"""El resolvedor: ruteo por fuente, armado bajo techo, fallo cerrado."""
from calipso.abismo import anillos, consulta, fuentes, marca


def test_pescado_arma_bloque_etiquetado(monkeypatch):
    monkeypatch.setattr(fuentes, "chats_viejos",
                        lambda resto: [("[t 2026-08-01] hola", anillos.MEDIA_AGUA)])
    r = consulta.resolver(marca.Marca("chats", "hola"))
    assert r["estado"] == "pescado" and r["fuente"] == "chats"
    assert "=== Lo que subio del abismo (fuente: chats) ===" in r["texto"]
    assert "[anillo 2]" in r["texto"]
    assert r["aviso"] == ""


def test_techo_de_caracteres(monkeypatch):
    monkeypatch.setattr(fuentes, "chats_viejos",
                        lambda resto: [("x" * 5000, anillos.MEDIA_AGUA)])
    r = consulta.resolver(marca.Marca("chats", "x"))
    assert len(r["texto"]) <= consulta.ABISMO_BLOQUE_MAX


def test_fuente_que_revienta_es_fallo_suave(monkeypatch):
    def bomba(resto):
        raise RuntimeError("chats.json roto")
    monkeypatch.setattr(fuentes, "chats_viejos", bomba)
    r = consulta.resolver(marca.Marca("chats", "x"))
    assert r["estado"] == "fallo" and "roto" in r["aviso"]
    assert r["texto"] == "" and r["bloques"] == []


def test_pesca_vacia_es_fallo_con_aviso(monkeypatch):
    monkeypatch.setattr(fuentes, "chats_viejos", lambda resto: [])
    r = consulta.resolver(marca.Marca("chats", "zzz"))
    assert r["estado"] == "fallo"
    assert "no trajo nada" in r["aviso"]


def test_memoria_recibe_las_dependencias(monkeypatch):
    visto = {}

    def falsa(pregunta, mem, consolidado=None, zona_chat="fabrica"):
        visto.update(mem=mem, zona=zona_chat)
        return [("algo", anillos.MEDIA_AGUA)]
    monkeypatch.setattr(fuentes, "memoria", falsa)
    consulta.resolver(marca.Marca("memoria", "q"), mem="MEM", zona_chat="personal")
    assert visto == {"mem": "MEM", "zona": "personal"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test_abismo_consulta.py -v`
Expected: FAIL con `ImportError: cannot import name 'consulta'`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/abismo/consulta.py
"""El resolvedor de la consulta -- spec 2026-09-07, seccion 4.

100% local siempre (invariante 1). Fallo cerrado: una consulta jamas rompe
una respuesta (invariante 4) -- toda excepcion degrada a estado "fallo" y el
turno sigue sin contexto extra.
"""
from __future__ import annotations

import os

from calipso.abismo import fuentes, marca

ABISMO_BLOQUE_MAX = int(os.environ.get("ABISMO_BLOQUE_MAX", "2000"))


def _fallo(fuente: str, aviso: str) -> dict:
    return {"estado": "fallo", "fuente": fuente, "texto": "",
            "bloques": [], "aviso": aviso[:200]}


def resolver(m: marca.Marca, *, mem=None, obtener=None, brief=None,
             consolidado=None, zona_chat: str = "fabrica") -> dict:
    try:
        if m.fuente == "memoria":
            bloques = fuentes.memoria(m.resto, mem, consolidado=consolidado,
                                      zona_chat=zona_chat)
        elif m.fuente == "chats":
            bloques = fuentes.chats_viejos(m.resto)
        elif m.fuente == "proyecto":
            bloques = fuentes.proyecto(m.resto, obtener, brief)
        else:  # la gramatica cerrada no deberia dejar llegar esto
            return _fallo(m.fuente, f"fuente desconocida: {m.fuente}")
    except Exception as e:
        return _fallo(m.fuente, str(e))
    bloques = [(t, a) for t, a in bloques if t.strip()]
    if not bloques:
        return _fallo(m.fuente, "la consulta no trajo nada")
    partes = [f"=== Lo que subio del abismo (fuente: {m.fuente}) ==="]
    for texto, anillo in bloques:
        partes.append(f"[anillo {anillo}]\n{texto.strip()}")
    return {"estado": "pescado", "fuente": m.fuente,
            "texto": "\n".join(partes)[:ABISMO_BLOQUE_MAX],
            "bloques": bloques, "aviso": ""}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest test_abismo_consulta.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Full suite + commit**

```bash
.venv/bin/python -m pytest -q --ignore=test_chat_live.py
git add calipso/abismo/consulta.py test_abismo_consulta.py
git commit -m "feat(abismo): el resolvedor -- ruteo por fuente, techo, fallo cerrado"
```

---

### Task 8: El contrato y el indice (`contrato.py`)

**Files:**
- Create: `calipso/abismo/contrato.py`
- Test: `test_abismo_contrato.py`

**Interfaces:**
- Consumes: `marca.ABRE/CIERRA/FUENTES`.
- Produces: `INDICE_MAX = 600`; `bloque_contrato(nombres_proyectos: tuple[str, ...] | list[str] = ()) -> str` -- el texto que en el 1b entrara a `internal_contract` y que el banco usa YA. Recorta nombres de proyectos enteros hasta entrar en el techo (el gesto de `proyectos_brief`, `calipso/prompt_compiler.py:452-464`).

- [ ] **Step 1: Write the failing test**

```python
# test_abismo_contrato.py
"""El contrato de la marca + el indice de lo consultable (spec seccion 5/7)."""
from calipso.abismo import contrato, marca


def test_ensena_la_sintaxis_de_las_tres_fuentes():
    b = contrato.bloque_contrato(("calipso", "atlas"))
    for fuente in marca.FUENTES:
        assert f"{marca.ABRE}abismo:{fuente}" in b
    assert "calipso" in b and "atlas" in b
    assert "Maximo 3" in b


def test_respeta_el_techo_con_muchos_proyectos():
    nombres = tuple(f"proyecto-con-nombre-largo-{i:03d}" for i in range(60))
    b = contrato.bloque_contrato(nombres)
    assert len(b) <= contrato.INDICE_MAX
    assert "mas" in b  # la cola "y N mas" en vez de un corte a la mitad


def test_sin_proyectos_sigue_siendo_valido():
    b = contrato.bloque_contrato(())
    assert len(b) <= contrato.INDICE_MAX
    assert f"{marca.ABRE}abismo:memoria" in b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest test_abismo_contrato.py -v`
Expected: FAIL con `ImportError: cannot import name 'contrato'`

- [ ] **Step 3: Write minimal implementation**

```python
# calipso/abismo/contrato.py
"""El contrato de la marca y el indice de lo consultable -- spec seccion 7.

Funcion PURA: el 1b la insertara en internal_contract (prompt_compiler); en
el 1a solo la consume el banco de medicion. Techo propio para no pagar en
cada turno lo que se ahorra consultando.
"""
from __future__ import annotations

from calipso.abismo import marca

INDICE_MAX = 600


def bloque_contrato(nombres_proyectos=()) -> str:
    a, c = marca.ABRE, marca.CIERRA

    def _armar(nombres, extra):
        lineas = [
            "=== El abismo (contexto a demanda) ===",
            ("Si te falta un dato que Calipso deberia saber, pedilo a mitad "
             "de la respuesta con UNA marca:"),
            f"{a}abismo:memoria <pregunta>{c} -- recuerdos, quien es Pedro, su cronologia.",
            f"{a}abismo:chats <palabras, opcional desde:AAAA-MM hasta:AAAA-MM>{c} -- conversaciones viejas.",
            f"{a}abismo:proyecto <nombre>{c} -- el detalle de un repo del catastro.",
        ]
        if nombres:
            cola = f" y {extra} mas" if extra else ""
            lineas.append("Proyectos consultables: " + ", ".join(nombres) + cola + ".")
        lineas.append(("La marca se retira del texto: segui la frase como si "
                       "nada. Maximo 3 por respuesta. Si no te falta nada, "
                       "no consultes."))
        return "\n".join(lineas)

    nombres = list(nombres_proyectos)
    total = len(nombres)
    texto = _armar(nombres, 0)
    while len(texto) > INDICE_MAX and nombres:
        nombres = nombres[:-1]
        texto = _armar(nombres, total - len(nombres))
    return texto[:INDICE_MAX]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest test_abismo_contrato.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Full suite + commit**

```bash
.venv/bin/python -m pytest -q --ignore=test_chat_live.py
git add calipso/abismo/contrato.py test_abismo_contrato.py
git commit -m "feat(abismo): el contrato de la marca y el indice de lo consultable, bajo techo"
```

---

### Task 9: El banco de medicion (`experimentos/consulta_abismo.py`)

**Files:**
- Create: `experimentos/consulta_abismo.py`

**Interfaces:**
- Consumes: `calipso.abismo.marca.encontrar` (el detector es LA gramatica, no una copia), `calipso.abismo.contrato.bloque_contrato`, `dispatch._http_post_json(dispatch.CONFIG["local"]["base_url"], payload)` (el molde exacto de `experimentos/juez_privacidad.py:384-407`).
- Produces: script manual (no pytest) que imprime las tres metricas del porton (spec seccion 12) y escribe `experimentos/consulta_abismo_resultados.md`. Cache resumible via env `ABISMO_CACHE` (el molde de `JUEZ_CACHE`); recorte para pruebas rapidas via `ABISMO_LIMIT`.

- [ ] **Step 1: Write the script**

No hay test de pytest para el script (igual que `juez_privacidad.py`): sus piezas con logica (gramatica, contrato) YA estan testeadas en el paquete. El criterio de "anda" es el Step 2.

```python
#!/usr/bin/env python3
"""
experimentos/consulta_abismo.py -- el porton de la rebanada 1a del abismo
(spec 2026-09-07, seccion 12).

La apuesta: que el 7b local, con el contrato y el indice puestos, sepa emitir
la marca ⟦abismo:fuente pregunta⟧ cuando le falta contexto -- y abstenerse
cuando no. Antes de cablear el filtro al chat vivo (plan 1b), esto lo mide.

QUE MIDE, sobre N corridas a temperatura 0 (el modelo no es determinista):
  1. MARCA CUANDO DEBE: en los positivos (la respuesta correcta EXIGE
     consultar), tasa de corridas con marca legible. Piso: >= 5/6 por fuente.
  2. ABSTENERSE CUANDO NO DEBE: en los negativos, tasa de corridas con alguna
     marca (espurias). Techo: <= 1/6.
  3. RUTEO: entre las marcas legibles de los positivos, cuantas eligen la
     fuente esperada. Piso: >= 90%.
Tambien reporta latencia y marcas ilegibles (emitio pero mal formada).

Los umbrales son los del spec; si al armar items nuevos hay razon para
moverlos, el cambio queda escrito ACA con su razon.

No decide nada solo: imprime los numeros y los lee Pedro (plan 1b arranca
solo despues de esa lectura).

CALIPSO_HOME va a un temporal ANTES de importar nada del paquete.
"""
import json
import os
import pathlib
import statistics
import sys
import tempfile
import time

os.environ["CALIPSO_HOME"] = tempfile.mkdtemp(prefix="abismo-exp-")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import dispatch  # noqa: E402
from calipso.abismo import contrato, marca  # noqa: E402

N = int(os.environ.get("ABISMO_N", "6"))
NUM_CTX = 4096

# El system del banco: representativo del turno real -- identidad minima +
# el contrato REAL (la misma funcion que el 1b va a cablear) con nombres de
# proyectos plausibles.
PROYECTOS = ("calipso", "atlas", "calipso-lector")
SISTEMA = "\n".join([
    "Sos Calipso, el asistente personal de Pedro. Respondele en su idioma,",
    "directo y natural.",
    contrato.bloque_contrato(PROYECTOS),
])

# --- EL BANCO. Hecho a mano. -------------------------------------------------
# positivo: la respuesta correcta EXIGE consultar (fuente_esperada dice cual).
# negativo: consultar seria ruido (charla, conocimiento general, lo que ya
# esta en el mensaje). Adversariales incluidos: mensajes que MENCIONAN
# recuerdos o proyectos sin necesitar la consulta.
BANCO = [
    # -- positivos: memoria
    {"id": "mem-libro", "tipo": "positivo", "fuente": "memoria",
     "mensaje": "che, como se llamaba esa novela que te conte que me habia encantado?"},
    {"id": "mem-rutina", "tipo": "positivo", "fuente": "memoria",
     "mensaje": "que era lo que hacia yo los domingos a la manana?"},
    {"id": "mem-medico", "tipo": "positivo", "fuente": "memoria",
     "mensaje": "cuando fue la ultima vez que cambie de rutina de ejercicio?"},
    {"id": "mem-gustos", "tipo": "positivo", "fuente": "memoria",
     "mensaje": "armame un regalo para mi hermana, acordate de lo que te dije de ella"},
    {"id": "mem-fecha", "tipo": "positivo", "fuente": "memoria",
     "mensaje": "en que mes me mude de casa? lo tenes en la cronologia"},
    {"id": "mem-pref", "tipo": "positivo", "fuente": "memoria",
     "mensaje": "que estilo de musica te dije que no soporto?"},
    # -- positivos: chats
    {"id": "cha-agosto", "tipo": "positivo", "fuente": "chats",
     "mensaje": "que estuvimos hablando en agosto sobre el lector?"},
    {"id": "cha-receta", "tipo": "positivo", "fuente": "chats",
     "mensaje": "buscame la receta que te pase hace unas semanas en otra conversacion"},
    {"id": "cha-decision", "tipo": "positivo", "fuente": "chats",
     "mensaje": "en que quedamos la otra vez que discutimos lo del presupuesto?"},
    {"id": "cha-link", "tipo": "positivo", "fuente": "chats",
     "mensaje": "pasame de nuevo el link que te mande en un chat viejo sobre bazzite"},
    {"id": "cha-nombre", "tipo": "positivo", "fuente": "chats",
     "mensaje": "como se llamaba el bar que anotamos en una charla del mes pasado?"},
    {"id": "cha-idea", "tipo": "positivo", "fuente": "chats",
     "mensaje": "retoma la idea que dejamos a medias ayer en la otra conversacion"},
    # -- positivos: proyecto
    {"id": "pro-estado", "tipo": "positivo", "fuente": "proyecto",
     "mensaje": "como viene el repo de atlas? en que rama esta?"},
    {"id": "pro-detalle", "tipo": "positivo", "fuente": "proyecto",
     "mensaje": "dame el detalle del proyecto calipso-lector"},
    {"id": "pro-commit", "tipo": "positivo", "fuente": "proyecto",
     "mensaje": "cual fue el ultimo commit de calipso?"},
    {"id": "pro-brief", "tipo": "positivo", "fuente": "proyecto",
     "mensaje": "que hay adentro del repo atlas? no me acuerdo de que iba"},
    {"id": "pro-rama", "tipo": "positivo", "fuente": "proyecto",
     "mensaje": "revisa si el proyecto calipso tiene cambios sin commitear"},
    {"id": "pro-cual", "tipo": "positivo", "fuente": "proyecto",
     "mensaje": "de mis proyectos, cual toque mas recientemente? fijate en el catastro"},
    # -- negativos
    {"id": "neg-charla", "tipo": "negativo",
     "mensaje": "buen dia! como va todo?"},
    {"id": "neg-general", "tipo": "negativo",
     "mensaje": "explicame en dos lineas que es un websocket"},
    {"id": "neg-inline", "tipo": "negativo",
     "mensaje": "mi hermana cumple el 12 de octubre, anotalo"},
    {"id": "neg-codigo", "tipo": "negativo",
     "mensaje": "escribime un one-liner de python que invierta un string"},
    {"id": "neg-opinion", "tipo": "negativo",
     "mensaje": "que te parece mejor para nombres de funciones, espanol o ingles?"},
    {"id": "neg-menciona-recuerdo", "tipo": "negativo",
     "mensaje": "te acabo de contar que me gusta el cafe sin azucar, repetimelo"},
    {"id": "neg-menciona-proyecto", "tipo": "negativo",
     "mensaje": "calipso es el nombre de mi asistente, te gusta como suena?"},
    {"id": "neg-matematica", "tipo": "negativo",
     "mensaje": "cuanto es 15% de 84000?"},
    {"id": "neg-traduccion", "tipo": "negativo",
     "mensaje": "como se dice 'estanteria' en ingles?"},
    {"id": "neg-ahora", "tipo": "negativo",
     "mensaje": "resumime este parrafo: los patos migran en otono hacia el sur."},
]

# --- cache resumible (el molde de juez_privacidad.py:50-77) ------------------
CACHE_PATH = os.environ.get("ABISMO_CACHE", "")
_cache: dict = {}


def _cache_load():
    if CACHE_PATH and os.path.exists(CACHE_PATH):
        for linea in open(CACHE_PATH, encoding="utf-8"):
            try:
                r = json.loads(linea)
                _cache[(r["item"], r["corrida"])] = (r["salida"], r["ms"])
            except (json.JSONDecodeError, KeyError):
                pass
    if _cache:
        print(f"cache: {len(_cache)} respuestas guardadas, se retoman.", flush=True)


def _cache_put(item_id, corrida, salida, ms):
    _cache[(item_id, corrida)] = (salida, ms)
    if CACHE_PATH:
        with open(CACHE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"item": item_id, "corrida": corrida,
                                "salida": salida, "ms": ms}) + "\n")


def preguntar(mensaje: str) -> tuple[str, int]:
    """Una llamada al 7b con el system del banco. Devuelve (texto, ms)."""
    payload = {
        "model": dispatch.CONFIG["local"]["model"],
        "system": SISTEMA,
        "prompt": mensaje,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": NUM_CTX},
    }
    t0 = time.monotonic()
    data = dispatch._http_post_json(dispatch.CONFIG["local"]["base_url"], payload)
    ms = int((time.monotonic() - t0) * 1000)
    return data.get("response", ""), ms


def main():
    _cache_load()
    limite = int(os.environ.get("ABISMO_LIMIT", "0")) or len(BANCO)
    banco = BANCO[:limite]
    modelo = dispatch.CONFIG["local"]["model"]
    print(f"\n{'=' * 72}\nPORTON DEL ABISMO -- {modelo} (temp 0, {N} corridas x "
          f"{len(banco)} items)\n{'=' * 72}", flush=True)

    fuentes_pos = sorted({i["fuente"] for i in banco if i["tipo"] == "positivo"})
    stats = {f: {"corridas": 0, "legibles": 0, "ruteo_ok": 0, "ilegibles": 0}
             for f in fuentes_pos}
    neg_corridas = neg_con_marca = 0
    latencias = []

    for item in banco:
        for corrida in range(N):
            key = (item["id"], corrida)
            if key in _cache:
                salida, ms = _cache[key]
            else:
                salida, ms = preguntar(item["mensaje"])
                _cache_put(item["id"], corrida, salida, ms)
            latencias.append(ms)
            marcas = marca.encontrar(salida)
            legibles = [m for m in marcas if m is not None]
            if item["tipo"] == "negativo":
                neg_corridas += 1
                if marcas:
                    neg_con_marca += 1
                continue
            s = stats[item["fuente"]]
            s["corridas"] += 1
            s["ilegibles"] += sum(1 for m in marcas if m is None)
            if legibles:
                s["legibles"] += 1
                if legibles[0].fuente == item["fuente"]:
                    s["ruteo_ok"] += 1
        print(f"  {item['id']}: listo", flush=True)

    lineas = ["# Porton del abismo -- resultados", "",
              f"Modelo: {modelo}. N={N}, temp 0, num_ctx={NUM_CTX}.",
              f"Items: {len(banco)} ({sum(1 for i in banco if i['tipo'] == 'positivo')} "
              f"positivos, {neg_corridas // N if N else 0} negativos).", ""]
    total_leg = total_ruteo = 0
    for f in fuentes_pos:
        s = stats[f]
        tasa = s["legibles"] / s["corridas"] if s["corridas"] else 0
        veredicto = "PASA" if tasa >= 5 / 6 else "NO PASA"
        lineas.append(f"- {f}: marca legible {s['legibles']}/{s['corridas']} "
                      f"({tasa:.0%}) -> {veredicto} (piso 5/6). "
                      f"Ilegibles: {s['ilegibles']}.")
        total_leg += s["legibles"]
        total_ruteo += s["ruteo_ok"]
    esp = neg_con_marca / neg_corridas if neg_corridas else 0
    lineas.append(f"- espurias en negativos: {neg_con_marca}/{neg_corridas} "
                  f"({esp:.0%}) -> {'PASA' if esp <= 1 / 6 else 'NO PASA'} (techo 1/6).")
    rut = total_ruteo / total_leg if total_leg else 0
    lineas.append(f"- ruteo correcto: {total_ruteo}/{total_leg} ({rut:.0%}) -> "
                  f"{'PASA' if rut >= 0.9 else 'NO PASA'} (piso 90%).")
    lineas.append(f"- latencia por llamada: mediana "
                  f"{statistics.median(latencias):.0f} ms, "
                  f"max {max(latencias)} ms.")
    reporte = "\n".join(lineas) + "\n"
    print("\n" + reporte, flush=True)
    out = pathlib.Path(__file__).parent / "consulta_abismo_resultados.md"
    out.write_text(reporte, encoding="utf-8")
    print(f"reporte escrito en {out}", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Smoke del script sin quemar el banco entero**

Run: `ABISMO_LIMIT=2 ABISMO_N=1 .venv/bin/python experimentos/consulta_abismo.py`
(antes: `curl -s http://localhost:11434/api/tags >/dev/null || echo "OLLAMA CAIDO"` -- si esta caido, levantarlo o reportar el bloqueo, no seguir)
Expected: corre 2 items x 1 corrida, imprime el reporte y escribe `experimentos/consulta_abismo_resultados.md` sin traceback. (`ABISMO_N` se lee como override de N: agregarlo tal como aparece en el codigo de arriba.)

- [ ] **Step 3: Full suite + commit**

```bash
.venv/bin/python -m pytest -q --ignore=test_chat_live.py
git add experimentos/consulta_abismo.py
git commit -m "exp(abismo): el banco del porton -- positivos por fuente, negativos adversariales, cache resumible"
```

---

### Task 10: Correr el porton y dejar los numeros

**Files:**
- Modify: `experimentos/consulta_abismo_resultados.md` (lo escribe el script; se commitea)

**Interfaces:**
- Consumes: la Task 9 completa y Ollama vivo con el modelo local configurado.
- Produces: el reporte con las tres metricas y sus PASA/NO PASA -- los numeros que Pedro lee antes de autorizar el plan 1b.

- [ ] **Step 1: Verificar que Ollama esta vivo**

Run: `curl -s http://localhost:11434/api/tags | head -c 300`
Expected: JSON con la lista de modelos (debe incluir el de `dispatch.CONFIG["local"]["model"]`, qwen2.5:7b). Si Ollama no corre: `ollama serve` en segundo plano o reportar el bloqueo -- NO inventar numeros.

- [ ] **Step 2: Correr el banco completo con cache**

Run: `ABISMO_CACHE=/tmp/abismo_cache.jsonl .venv/bin/python experimentos/consulta_abismo.py`
Expected: 28 items x 6 corridas = 168 llamadas (menos las cacheadas si se retoma). A ~4 s por llamada son ~10-12 minutos: dejarlo terminar, no matarlo por lento ([[feedback_no_techos_entender_causa]]). El reporte final imprime las tres metricas con PASA/NO PASA.

- [ ] **Step 3: Leer el reporte y anotar lo cualitativo**

Abrir `experimentos/consulta_abismo_resultados.md` y agregarle a mano una seccion `## Observaciones` con: patrones de las ilegibles (que renglon omite el 7b, copia el separador?), ejemplos textuales de 2-3 marcas espurias si las hay, y cualquier sesgo por fuente. Es el mismo gesto que dejo utiles los portones anteriores (la plantilla del jefe salio de mirar los ilegibles, no las tasas).

- [ ] **Step 4: Full suite + commit**

```bash
.venv/bin/python -m pytest -q --ignore=test_chat_live.py
git add experimentos/consulta_abismo_resultados.md
git commit -m "exp(abismo): porton corrido -- los numeros del 7b para decidir el 1b"
```

- [ ] **Step 5: Reportar a Pedro**

El entregable del plan 1a: las tres metricas con su PASA/NO PASA, las observaciones cualitativas, y la pregunta que abre el 1b: cablear como esta, refinar el indice y re-medir, o cablear solo en rutas grandes (spec seccion 12).

---

## Self-review (hecho al escribir el plan)

1. **Cobertura del spec (secciones del 1a):** gramatica (Task 1), anillos con piso/hundir-preparado (Task 2), fuente chats + mini-sintaxis (Task 3), recall por ambito (Task 4), fuente memoria con frontera de zona (Task 5), fuente proyecto inyectada (Task 6), resolvedor con techo y fallo cerrado (Task 7), contrato/indice bajo techo (Task 8), banco con los tres umbrales del spec (Task 9), porton corrido y numeros (Task 10). El filtro de streaming, el estado del turno, la reentrada, la senal WS, las UIs y el pulso son plan 1b, como el spec manda.
2. **Sin placeholders:** todo el codigo esta escrito; el unico "a mano" es la seccion Observaciones del reporte, que es deliberadamente humana.
3. **Consistencia de tipos:** `fuentes.*` devuelven `list[tuple[str, int]]`; `resolver` las consume tal cual; `marca.Marca(fuente, resto)` es la que usan resolvedor y banco; `bloque_contrato` recibe tuplas o listas de nombres. El juez que hunde NO aparece en 1a (se aplica sobre viajes, y en 1a nada viaja): su enchufe es `anillos.puede_viajar`, documentado en el docstring.
