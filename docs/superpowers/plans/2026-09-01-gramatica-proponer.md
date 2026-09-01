# La gramatica de `proponer` — plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que una propuesta del jefe tenga una forma tipada y comparable -- `sobre`, `promete`, `tarda` -- en vez de identificarse por un renglon de prosa cortado a 120 caracteres.

**Architecture:** La gramatica pura vive en un modulo nuevo sin I/O
(`calipso/plantel/ficha.py`): tablas, normalizacion y parseo. `parsear()` NO
cambia de forma -- la ficha se lee con una funcion aparte que solo se llama
cuando la accion es `proponer`, porque cambiar la aridad de `parsear` romperia
seis tests que no hablan de proponer. La forma viaja al bus como un campo
`forma` opcional, y una ficha que no se entiende se desvia a un archivo
append-only que la bandeja de la fabrica muestra como aviso.

**Tech Stack:** Python 3.14, pytest. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-01-gramatica-proponer-design.md`

## Global Constraints

- **SIN EMOJIS.** En ningun lado: codigo, comentarios, texto que ve Pedro,
  mensajes de commit.
- **Nombres, comentarios y docstrings en ESPANOL.** Mensajes de commit **sin
  tildes ni enie**.
- **NUNCA importar `calipso` fuera de pytest.** El paquete escribe en el
  `~/.calipso` real.
- **`git add` con rutas explicitas**, nunca `-A` ni `.`: hay agentes en
  paralelo compartiendo el indice de git.
- **El libro es append-only.** Nada de este plan reescribe un asiento.
- **`bus.alta` es una escritura** y sigue yendo bajo `_eco_candado`, con un
  `Bus` fresco construido adentro.
- **Los numeros los declara la perilla del jefe, no el modelo.**
- **Interprete:** `.venv/bin/python`. Tests: `.venv/bin/python -m pytest <archivo> -q`
  desde `/var/home/pedro/calipso`.

---

## Contexto verificado (leer antes de la Tarea 1)

Ocho hechos que salieron de leer el codigo. Si alguno resulta falso al
implementar, es un defecto del plan: se arregla el plan, no se compensa en el
codigo.

1. **`parsear` devuelve una 3-upla y no puede cambiar de aridad.** Se
   desestructura en `jefe.py:351` y en `test_plantel_decision.py` hay **dos
   asserts de igualdad de tupla completa** (`:254` y `:256`,
   `== ("nada", None, "motivo")`) mas cuatro desempaquetados de tres nombres.
   Ninguno habla de `proponer`.

2. **Inventar un valor de accion nuevo es peligroso.** `_puede`
   (`jefe.py:230-292`) **no tiene rama por defecto**: una accion desconocida
   pasa de largo las ramas de `nada`/`trabajar`/`comentar`, no entra al bloque
   de proponer/pedir, y cae al tramo final que devuelve `True` con saldo. Y el
   `contratar` de produccion **no tiene guarda de accion**: `comentar` en
   `server.py:5442`, `trabajar` en `:5446`, `pedir` en `:5452`, y todo lo demas
   cae en el camino de `proponer` que llama a `bus_fresco.alta`. Una accion
   nueva sin rama en `_puede` **escribe una propuesta de verdad en el bus, con
   el texto ilegible de titulo**.

3. **`bus.datos()` copia el evento de alta entero** (`bus.py:110-121`,
   `d = dict(eventos[0])`). En cuanto `alta` escriba `forma`,
   `datos.get("forma")` la devuelve sin tocar nada mas del lector.

4. **`decision.prompt` indexa con corchetes** (`p['titulo']`, `t['gastado_mm']`)
   y los doce dicts que los tests del prompt arman a mano **nunca traen
   `forma`**. Un render nuevo que haga `p['forma']` los revienta con KeyError.
   Con `.get()`, esos doce tests pasan a ser la suite de regresion del camino
   de compatibilidad, gratis.

5. **Dos tests assertan por substring sobre el prompt entero:**
   `test_el_prompt_no_ofrece_trabajar_sin_trabajos_vivos` afirma
   `"trabajar" not in p` y `test_el_prompt_no_ofrece_comentar_sin_nada_que_comentar`
   afirma `"comentar" not in p`. **Ningun texto nuevo del prompt puede contener
   esas subcadenas.** Las seis promesas no colisionan;
   `"Pedro DESCARTO" not in p` es en mayusculas y tampoco.

6. **`test_plantel_jefe.py:596-597` compara un dict por igualdad exacta:**
   `s["descartadas_semana"] == [{"id": "p0", "titulo": "radar de precios"}]`.
   Agregarle `forma` lo rompe. Es el unico assert de igualdad exacta sobre esas
   listas.

7. **Tres tests fijan las claves de la salida de `tic`:**
   `set(out) == CLAVES` en `test_plantel_jefe.py:79`, `:99` y `:116`, con
   `CLAVES = {cuenta, accion, ref, motivo, sesgo_pct, actuo, freno, resultado}`.
   **La salida de `tic` no gana ninguna clave en este plan.**

8. **El arnes de los tests del jefe no toca el bus.** `armar()` inyecta
   `contratar=lambda s, a, ref, m="": ...`. El guarda que pide la seccion 8 del
   spec ("un test que fija que el camino de produccion siempre manda `forma`")
   **no se puede escribir con `armar`**: va en `test_plantel_server.py`, que
   tiene `_contratar_real` -- el contratista de produccion contra un bus de
   verdad en disco.

## Las cinco decisiones que este plan toma

- **P1 -- `parsear` no cambia. La ficha se lee aparte.** Una funcion nueva
  `ficha.parsear_ficha(texto)` devuelve el dict o `None`, y `jefe.tic` la llama
  **solo** cuando `accion == "proponer"`. Motivo: el hecho 1. La ficha existe
  para un solo verbo; que su parseo viva en un solo verbo es ademas mas
  honesto.

- **P2 -- una ficha ilegible NO es una accion nueva.** Por el hecho 2. `tic`
  detecta `accion == "proponer" and ficha is None`, escribe el aviso, escribe
  la memoria, y fija `permiso = False` con un `freno` propio **sin llamar a
  `_puede`**. La accion reportada sigue siendo `"proponer"` -- el modelo si
  dijo proponer -- y `actuo` sale `False`.

- **P3 -- la ficha llega a `contratar` como argumento con nombre y default.**
  `contratar(situacion, accion, ref, motivo="", ficha=None)`. Las 44 llamadas
  del arnes siguen siendo de cuatro posicionales; lo unico que se toca es el
  `lambda` de `armar()`, que gana `ficha=None` y lo ignora. La verificacion de
  que la forma llega al bus vive donde el bus es real (hecho 8).

- **P4 -- `trabajos` sigue mostrando su titulo.** La seccion 6 del spec nombra
  solo `propuestas_propias`, `propuestas_ajenas` y `descartadas_semana`, pero
  las cuatro listas salen del mismo dict `base` de `situacion`. Los trabajos se
  renderean como hoy. Motivo: `test_el_prompt_lleva_los_numeros_que_hacen_falta`
  afirma `"radar" in p` sobre el titulo de un TRABAJO, y un trabajo vivo ya no
  es una propuesta esperando -- su identidad ya no esta en disputa.

- **P5 -- el render de las listas usa `.get()`, nunca corchetes, para `forma`.**
  Por el hecho 4. Sin `forma`, se muestra el titulo. Eso ES el camino de
  compatibilidad de la seccion 6, y los doce tests del prompt lo cubren sin
  escribir uno nuevo.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `calipso/plantel/ficha.py` (**nuevo**) | La gramatica pura: tablas, `normalizar`, `parsear_ficha`, `titulo_de`. Sin I/O, sin estado, sin imports del proyecto |
| `calipso/plantel/ilegibles.py` (**nuevo**) | El archivo append-only de fichas que no se entendieron, y su lectura colapsada |
| `calipso/economia/bus.py` | `alta` gana `forma` opcional y su validacion; `como_items` emite el aviso |
| `calipso/plantel/situacion.py` | `base` gana `forma`; el dict gana `catalogo` |
| `calipso/plantel/decision.py` | `prompt` gana la plantilla de la ficha y el catalogo; las listas muestran la forma |
| `calipso/plantel/jefe.py` | `tic` llama a `parsear_ficha`, corta el camino de la valvula y pasa `ficha=` |
| `calipso/server.py` | La rama de `proponer` arma la forma, el titulo y `semanas_max`; el endpoint de la mesa suma los ilegibles |

---

### Task 1: La gramatica pura

**Files:**
- Create: `calipso/plantel/ficha.py`
- Test: `test_plantel_ficha.py` (nuevo, en la raiz, como los demas)

**Interfaces:**
- Consumes: nada. El modulo no importa nada del proyecto a proposito.
- Produces, y lo usan las Tareas 4, 5 y 6:
  - `PROMESAS: tuple[str, ...]`, `PLAZOS: tuple[str, ...]`
  - `METRICA: dict[str, str]`, `SEMANAS_MAX: dict[str, int]`
  - `normalizar(texto: str) -> str`
  - `parsear_ficha(texto: str) -> dict | None` -- el dict tiene exactamente
    `{"sobre", "clave", "promete", "tarda", "porque"}`
  - `titulo_de(ficha: dict) -> str`

- [ ] **Step 1: Escribir los tests que fallan**

Crear `test_plantel_ficha.py`:

```python
#!/usr/bin/env python3
"""
test_plantel_ficha.py — La gramatica de `proponer` (spec del 2026-09-01).

Modulo puro: no toca disco, no importa nada del proyecto, no necesita
fixture de home.
"""
from calipso.plantel import ficha


# --------------------------------------------------------------------------
# normalizar: la funcion de identidad
# --------------------------------------------------------------------------

def test_la_misma_cosa_escrita_distinto_da_la_misma_clave():
    assert ficha.normalizar("El Radar de Precios!") == "precios+radar"
    assert ficha.normalizar("el radar de precios") == "precios+radar"
    assert ficha.normalizar("  radar   precios ") == "precios+radar"


def test_el_orden_de_las_palabras_no_importa():
    # es lo que un modelo mas varia, y en una frase nominal casi nunca
    # carga significado
    assert ficha.normalizar("precios radar") == ficha.normalizar("radar precios")


def test_los_digitos_se_quedan():
    # descartarlos haria que dos modelos distintos fueran la misma familia
    assert ficha.normalizar("el modelo 7b") == "7b+modelo"
    assert ficha.normalizar("el modelo 3b") == "3b+modelo"
    assert ficha.normalizar("el modelo 7b") != ficha.normalizar("el modelo 3b")


def test_singular_y_plural_son_dos_familias():
    # no se usa stemming: seria difuso y no se podria explicar el dia que
    # Pedro revoque
    assert ficha.normalizar("radar de precio") != ficha.normalizar("radar de precios")


def test_solo_funcionales_no_es_un_objeto():
    # un objeto sin contenido no es un objeto
    assert ficha.normalizar("el") == ""
    assert ficha.normalizar("de la") == ""


# --------------------------------------------------------------------------
# parsear_ficha: la reparacion antes de rendirse
# --------------------------------------------------------------------------

FICHA_OK = """proponer
sobre: el radar de precios
promete: descartar
tarda: corto
porque: no rindio y sigue gastando"""


def test_una_ficha_completa_se_lee_entera():
    f = ficha.parsear_ficha(FICHA_OK)
    assert f == {"sobre": "el radar de precios", "clave": "precios+radar",
                 "promete": "descartar", "tarda": "corto",
                 "porque": "no rindio y sigue gastando"}


def test_el_orden_de_los_renglones_no_importa():
    f = ficha.parsear_ficha(
        "proponer\ntarda: corto\nporque: da igual\npromete: medir\n"
        "sobre: el clasificador")
    assert f["promete"] == "medir" and f["tarda"] == "corto"


def test_las_claves_se_matchean_por_prefijo_unico_y_sin_mayusculas():
    f = ficha.parsear_ficha(
        "proponer\nSOBRE : el radar\nProm: medir\nTARDA: corto")
    assert f["sobre"] == "el radar" and f["promete"] == "medir"


def test_los_valores_tambien_se_matchean_por_prefijo():
    f = ficha.parsear_ficha("proponer\nsobre: el radar\npromete: desc\ntarda: cor")
    assert f["promete"] == "descartar" and f["tarda"] == "corto"


def test_un_prefijo_ambiguo_no_matchea():
    # `a` esta entre ahorrar y acelerar: adivinar seria peor que no entender
    assert ficha.parsear_ficha(
        "proponer\nsobre: el radar\npromete: a\ntarda: corto") is None


def test_porque_puede_faltar():
    f = ficha.parsear_ficha("proponer\nsobre: el radar\npromete: medir\ntarda: corto")
    assert f is not None and f["porque"] == ""


def test_un_renglon_que_no_matchea_se_ignora_y_no_rompe():
    f = ficha.parsear_ficha(
        "proponer\nsobre: el radar\nfulano: cualquier cosa\n"
        "promete: medir\ntarda: corto")
    assert f is not None and f["sobre"] == "el radar"


def test_no_se_es_un_plazo_valido():
    f = ficha.parsear_ficha("proponer\nsobre: el radar\npromete: medir\ntarda: no se")
    assert f is not None and f["tarda"] == "no se"


def test_lo_que_falta_deja_la_ficha_ilegible():
    sin_sobre = "proponer\npromete: medir\ntarda: corto"
    sin_promete = "proponer\nsobre: el radar\ntarda: corto"
    sin_tarda = "proponer\nsobre: el radar\npromete: medir"
    promete_invalido = "proponer\nsobre: el radar\npromete: bailar\ntarda: corto"
    for texto in (sin_sobre, sin_promete, sin_tarda, promete_invalido):
        assert ficha.parsear_ficha(texto) is None, texto


def test_un_sobre_sin_contenido_deja_la_ficha_ilegible():
    assert ficha.parsear_ficha(
        "proponer\nsobre: el\npromete: medir\ntarda: corto") is None


def test_la_prosa_libre_de_hoy_ya_no_es_una_ficha():
    # este es el cambio: lo que hoy pasa como propuesta, ahora es ilegible
    # y va a la valvula
    assert ficha.parsear_ficha("proponer\nhay hueco en precios") is None


# --------------------------------------------------------------------------
# las tablas y el titulo
# --------------------------------------------------------------------------

def test_cada_promesa_trae_su_metrica_y_cada_plazo_su_semana():
    assert set(ficha.METRICA) == set(ficha.PROMESAS)
    assert set(ficha.SEMANAS_MAX) == set(ficha.PLAZOS)
    assert ficha.SEMANAS_MAX["corto"] == 1
    assert ficha.SEMANAS_MAX["largo"] == 12
    # `no se` toma el valor de hoy a proposito: es el unico que no empeora
    # nada respecto del 4 literal que habia
    assert ficha.SEMANAS_MAX["no se"] == 4


def test_el_titulo_se_arma_con_la_ficha():
    f = ficha.parsear_ficha(FICHA_OK)
    assert ficha.titulo_de(f) == (
        "descartar: el radar de precios (corto) -- no rindio y sigue gastando")


def test_sin_porque_el_titulo_no_arrastra_el_separador():
    f = ficha.parsear_ficha("proponer\nsobre: el radar\npromete: medir\ntarda: corto")
    assert ficha.titulo_de(f) == "medir: el radar (corto)"


def test_el_titulo_no_pasa_de_120():
    f = ficha.parsear_ficha(
        "proponer\nsobre: " + "x" * 200 + "\npromete: medir\ntarda: corto")
    assert len(ficha.titulo_de(f)) <= 120
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_plantel_ficha.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'calipso.plantel.ficha'`

- [ ] **Step 3: Escribir el modulo**

Crear `calipso/plantel/ficha.py`:

```python
#!/usr/bin/env python3
"""
calipso/plantel/ficha.py — la gramatica de `proponer`.

Una propuesta se identificaba por un renglon de prosa cortado a 120
caracteres, y eso hacia imposible el "nunca mas" de la mesa: comparar
titulos por igualdad no atrapa nada -- el mismo modelo escribe "radar de
precios" y "un radar de precios de la competencia" en dos tics -- y por
substring atrapa de mas y no se le puede explicar a Pedro el dia que
revoque.

Este modulo es la forma que faltaba, y copia el molde del motor de
permisos: separa la FORMA -- lo unico que se compara -- del titulo y la
prosa, que Pedro lee y que no participan de ninguna comparacion.

Puro a proposito: no toca disco, no importa nada del proyecto y no tiene
estado. Todo lo que decide se decide con el texto que recibe.
"""
from __future__ import annotations

import unicodedata

# Las seis promesas son el vocabulario entero: lo que no esta aca, un
# departamento no lo puede pedir. Cada una trae su unidad de medida, asi
# que la propuesta nace con un criterio de exito que no inventa el modelo.
PROMESAS = ("ahorrar", "acelerar", "arreglar", "medir", "construir",
            "descartar")

METRICA = {
    "ahorrar": "milimonedas por semana que dejan de salir de esa cuenta",
    "acelerar": "semanas hasta cerrar",
    "arreglar": "veces que vuelve a fallar",
    "medir": "existe el numero: si o no",
    "construir": "usos en cuatro semanas",
    "descartar": "milimonedas por semana que dejan de salir",
}

# `no se` existe a proposito: sin el, un modelo que no sabe elige uno al
# azar y la mentira entra al criterio de muerte. Declararlo es informacion;
# adivinarlo es ruido.
PLAZOS = ("corto", "medio", "largo", "no se")

# `no se` toma el valor que el codigo usaba escrito a mano antes de que
# existiera esta tabla: es el unico de los cuatro que no empeora nada.
SEMANAS_MAX = {"corto": 1, "medio": 4, "largo": 12, "no se": 4}

CAMPOS = ("sobre", "promete", "tarda", "porque")

# Se descartan al normalizar para que "el radar de precios" y "radar
# precios" sean el mismo objeto.
FUNCIONALES = frozenset(
    "el la los las un una unos unas de del al a en para por con y o que "
    "su sus mi mis lo".split())

TOPE_TITULO = 120


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """La clave de identidad de un objeto.

    Explicable el dia que Pedro revoque, que es el requisito que descarta
    cualquier comparacion difusa: "dijiste que no a este objeto, escrito
    asi".

    Se ORDENA porque el orden de las palabras es lo que un modelo mas
    varia y en una frase nominal casi nunca carga significado. Los DIGITOS
    se quedan: sin ellos "el modelo 7b" y "el modelo 3b" serian la misma
    familia, y son cosas distintas.
    """
    limpio = _sin_tildes(texto or "").lower()
    tokens = []
    actual = []
    for c in limpio:
        if c.isalnum():
            actual.append(c)
        elif actual:
            tokens.append("".join(actual))
            actual = []
    if actual:
        tokens.append("".join(actual))
    return "+".join(sorted(t for t in tokens if t and t not in FUNCIONALES))


def _por_prefijo(dado: str, opciones) -> str | None:
    """El valor de `opciones` que `dado` prefija, si es UNO solo.

    Un prefijo ambiguo no matchea: `a` esta entre `ahorrar` y `acelerar`, y
    adivinar cual quiso decir seria peor que no entender -- la ficha caeria
    en el bus con una promesa que el jefe no eligio.
    """
    dado = _sin_tildes((dado or "").strip()).lower()
    if not dado:
        return None
    calzan = [o for o in opciones if o.startswith(dado)]
    return calzan[0] if len(calzan) == 1 else None


def parsear_ficha(texto: str) -> dict | None:
    """Los cuatro renglones de una propuesta, o `None` si no se entienden.

    Repara antes de rendirse: el orden no importa, las claves se matchean
    por prefijo unico y sin mayusculas ni tildes, los valores tambien, y un
    renglon con una clave que no matchea se ignora en vez de romper.

    `None` NO es un error: es la valvula. El llamador la desvia a un aviso
    con la prosa cruda adentro, que es lo que evita que la gramatica
    amordace al departamento.
    """
    crudo: dict[str, str] = {}
    for linea in (texto or "").splitlines():
        if ":" not in linea:
            continue
        clave, _, valor = linea.partition(":")
        campo = _por_prefijo(clave.strip(), CAMPOS)
        if campo is None or campo in crudo:
            continue        # el primero gana: un renglon repetido no pisa
        crudo[campo] = valor.strip()

    sobre = crudo.get("sobre", "")
    clave = normalizar(sobre)
    if not clave:
        return None         # sin objeto, o un objeto de puros funcionales
    promete = _por_prefijo(crudo.get("promete", ""), PROMESAS)
    tarda = _por_prefijo(crudo.get("tarda", ""), PLAZOS)
    if promete is None or tarda is None:
        return None
    return {"sobre": sobre, "clave": clave, "promete": promete,
            "tarda": tarda, "porque": crudo.get("porque", "")}


def titulo_de(f: dict) -> str:
    """Lo que Pedro lee en la mesa. No participa de ninguna comparacion.

    Sigue cortado a 120 como el titulo de hoy, asi que `bus.alta` recibe
    exactamente el largo que ya recibia.
    """
    base = f"{f['promete']}: {f['sobre']} ({f['tarda']})"
    if f.get("porque"):
        base = f"{base} -- {f['porque']}"
    return base[:TOPE_TITULO]
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_ficha.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/plantel/ficha.py test_plantel_ficha.py
git commit -m "feat(plantel): la gramatica de proponer, pura y sin disco"
```

---

### Task 2: El bus guarda la forma

**Files:**
- Modify: `calipso/economia/bus.py` (la constante junto a `_CLAVES_CRITERIO`
  cerca de la linea 30, y `alta` en `:70-99`)
- Test: `test_economia_bus.py`

**Interfaces:**
- Consumes: `ficha.PROMESAS` y `ficha.PLAZOS` de la Tarea 1 -- **pero NO se
  importan**: ver el Step 3, el bus valida contra sus propias constantes.
- Produces, y lo usan las Tareas 3 y 6:
  `Bus.alta(ts, semana, id, departamento_cuenta, titulo, presupuesto_mm,
  retorno_mm, criterio, tipo="trabajo", forma=None)`.

- [ ] **Step 1: Escribir los tests que fallan**

En `test_economia_bus.py`, al final. **Ojo con el alias**: ese archivo importa
`from calipso.economia import bus as bus_mod`, no `bus` -- verificado. Usar
`bus` a secas da `NameError`.

```python
FORMA_OK = {"sobre": "el radar de precios", "clave": "precios+radar",
            "promete": "descartar", "tarda": "corto"}


def test_una_propuesta_puede_llevar_su_forma(tmp_path):
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    b.alta(TS, W, "p1", "dep:a", "descartar: el radar (corto)", 10_000,
           10_000, {"gasto_max_mm": 10_000, "semanas_max": 1},
           forma=FORMA_OK)
    assert b.datos("p1")["forma"] == FORMA_OK


def test_una_propuesta_sin_forma_sigue_siendo_valida(tmp_path):
    """Compatibilidad: las que se escribieron antes de que la forma
    existiera se leen, se financian y se descartan igual. No hay
    migracion."""
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    b.alta(TS, W, "p1", "dep:a", "radar", 10_000, 10_000,
           {"gasto_max_mm": 10_000})
    assert b.datos("p1").get("forma") is None
    assert b.estado("p1") == "alta"


def test_una_forma_invalida_no_entra_al_libro(tmp_path):
    """El libro es append-only: una forma mal escrita no se puede borrar
    despues, asi que se corta antes de escribirla."""
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    casos = [
        {"sobre": "x", "clave": "x", "promete": "bailar", "tarda": "corto"},
        {"sobre": "x", "clave": "x", "promete": "medir", "tarda": "ya"},
        {"sobre": "x", "clave": "x", "promete": "medir"},
        {"sobre": "", "clave": "x", "promete": "medir", "tarda": "corto"},
        {"sobre": "x", "clave": "", "promete": "medir", "tarda": "corto"},
        {"sobre": "x", "clave": "x", "promete": "medir", "tarda": "corto",
         "de_mas": 1},
    ]
    for i, forma in enumerate(casos):
        with pytest.raises(bus_mod.ErrorBus):
            b.alta(TS, W, f"p{i}", "dep:a", "t", 1000, 1000,
                   {"gasto_max_mm": 1000}, forma=forma)


def test_un_preseed_no_lleva_forma(tmp_path):
    """No sale de una ficha: sale de `pedir <monto>`, que es otro verbo."""
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    b.alta(TS, W, "p1", "dep:a", "ronda pre-seed de a", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    assert b.datos("p1").get("forma") is None
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_economia_bus.py -q -k "forma or preseed_no_lleva"`
Expected: FAIL con `TypeError: alta() got an unexpected keyword argument 'forma'`

- [ ] **Step 3: Las constantes y la validacion**

En `calipso/economia/bus.py`, junto a `_CLAVES_CRITERIO` (cerca de `:30`):

```python
# La forma de una propuesta: lo UNICO que se compara. El titulo es prosa y
# no participa de ninguna comparacion, igual que en el motor de permisos.
#
# Se listan aca y NO se importan de `calipso.plantel.ficha` a proposito: el
# bus es el libro, y el libro no puede depender de quien lo escribe. Si el
# plantel cambia su vocabulario, el bus tiene que seguir leyendo lo que ya
# esta escrito -- y que las dos listas se separen tiene que romper un test,
# no una lectura del libro.
_CLAVES_FORMA = {"sobre", "clave", "promete", "tarda"}
_PROMESAS = {"ahorrar", "acelerar", "arreglar", "medir", "construir",
             "descartar"}
_PLAZOS = {"corto", "medio", "largo", "no se"}
```

- [ ] **Step 4: `alta` gana el parametro**

En `alta`, la firma pasa a:

```python
    def alta(self, ts: str, semana: str, id: str, departamento_cuenta: str,
             titulo: str, presupuesto_mm: int, retorno_mm: int,
             criterio: dict, tipo: str = "trabajo",
             forma: dict | None = None) -> None:
```

Y despues del bloque que valida `criterio`, antes del que valida
`presupuesto_mm`, va:

```python
        # OPCIONAL, no obligatoria para tipo="trabajo", que era lo natural:
        # `alta` tiene dos llamadores de produccion y 123 sitios de llamada
        # en los tests. Hacerla obligatoria convierte un cambio de dos
        # lineas en un barrido mecanico de 123 ediciones. Y seria
        # incoherente: si LEER tolera que no este -- una propuesta escrita
        # antes de que la forma existiera -- ESCRIBIR tambien.
        # El guarda de que el camino de produccion siempre la manda vive en
        # test_plantel_server.py, apuntado al unico lugar que importa.
        if forma is not None:
            if set(forma) != _CLAVES_FORMA:
                raise ErrorBus(
                    f"forma invalida (claves {_CLAVES_FORMA}): {forma!r}")
            if forma["promete"] not in _PROMESAS:
                raise ErrorBus(f"promesa invalida: {forma['promete']!r}")
            if forma["tarda"] not in _PLAZOS:
                raise ErrorBus(f"plazo invalido: {forma['tarda']!r}")
            for clave in ("sobre", "clave"):
                if not (isinstance(forma[clave], str) and forma[clave].strip()):
                    raise ErrorBus(
                        f"forma con {clave} vacio: {forma[clave]!r}")
```

Y en el `_apilar` del final, el evento gana la clave **solo cuando la forma
existe**, para que una propuesta sin forma no quede con un `"forma": null` que
despues haya que distinguir de la ausencia:

```python
        evento = {"ts": ts, "semana": semana, "evento": "alta", "id": id,
                  "departamento": departamento_cuenta, "titulo": titulo,
                  "presupuesto_mm": presupuesto_mm,
                  "retorno_mm": retorno_mm, "criterio": criterio,
                  "tipo": tipo}
        if forma is not None:
            evento["forma"] = dict(forma)
        self._apilar(evento)
```

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/python -m pytest test_economia_bus.py test_economia_pagador.py test_economia_cierre.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add calipso/economia/bus.py test_economia_bus.py
git commit -m "feat(bus): una propuesta puede llevar su forma, y se valida antes del libro"
```

---

### Task 3: La situacion lleva la forma y el catalogo

**Files:**
- Modify: `calipso/plantel/situacion.py` (el dict `base` cerca de `:126-127`,
  la rama de descartadas cerca de `:108-109`, y el dict de retorno)
- Test: `test_plantel_situacion.py`, y **arreglar** `test_plantel_jefe.py:596-597`

**Interfaces:**
- Consumes: `bus.datos(id)["forma"]`, que la Tarea 2 hace existir.
- Produces, y lo usa la Tarea 4:
  - cada dict de `trabajos`, `propuestas_propias`, `propuestas_ajenas` y
    `descartadas_semana` gana la clave `forma` (`dict` o `None`)
  - el dict de `situacion` gana la clave `catalogo`: `list[str]`, los `sobre`
    crudos distintos de ese departamento, el mas nuevo primero, hasta 12

- [ ] **Step 1: Escribir los tests que fallan**

En `test_plantel_situacion.py`:

```python
def test_las_propuestas_llevan_su_forma(tmp_path):
    """El prompt necesita la forma para mostrarla; sin esto solo tiene el
    titulo, que es prosa."""
    b, s = _situacion_con(tmp_path, forma={
        "sobre": "el radar de precios", "clave": "precios+radar",
        "promete": "descartar", "tarda": "corto"})
    assert s["propuestas_propias"][0]["forma"]["promete"] == "descartar"


def test_una_propuesta_vieja_sin_forma_no_rompe(tmp_path):
    b, s = _situacion_con(tmp_path, forma=None)
    assert s["propuestas_propias"][0]["forma"] is None
    assert s["propuestas_propias"][0]["titulo"]


def test_el_catalogo_trae_los_objetos_que_el_departamento_ya_nombro(tmp_path):
    """Es el paliativo de los sinonimos: sin el, "radar de precios" y
    "monitor de precios" son dos familias, ocupan dos lugares y un "nunca
    mas" sobre una no tapa la otra."""
    b, s = _situacion_con_varias(tmp_path)
    assert "el radar de precios" in s["catalogo"]


def test_el_catalogo_no_repite_el_mismo_objeto(tmp_path):
    """Deduplicado por clave, no por texto: dos redacciones que normalizan
    igual son un solo objeto."""
    b, s = _situacion_con_dos_redacciones(tmp_path)
    assert len(s["catalogo"]) == 1


def test_el_catalogo_es_solo_del_propio_departamento(tmp_path):
    """Copiar el objeto de otro departamento seria empujarlo a pisarle el
    lugar en la mesa."""
    b, s = _situacion_con_ajena(tmp_path)
    assert "la encuesta de mercado" not in s["catalogo"]


def test_el_catalogo_no_pasa_de_doce(tmp_path):
    """Tope de espacio del prompt, no una regla sobre lo que el
    departamento puede hacer."""
    b, s = _situacion_con_veinte(tmp_path)
    assert len(s["catalogo"]) == 12
```

Ese archivo YA tiene todo lo que hace falta y no hay que inventar helpers: el
fixture `fabrica` (linea 21) devuelve `(k, r, bus, cola, sus)` con dos
departamentos -- `dep:atlas` y `dep:mercado` -- la semana abierta y plata
acunada, y los tests llaman `sit.situacion(k, r, bus, cola, sus, W,
"dep:atlas")`. Los seis tests de arriba se escriben con ese fixture, dando de
alta las propuestas con `bus.alta(..., forma=...)` antes de llamar a
`situacion`. Este es el molde exacto, y los otros cinco salen de el cambiando
las altas:

```python
def _forma(sobre, clave, promete="medir", tarda="corto"):
    return {"sobre": sobre, "clave": clave, "promete": promete,
            "tarda": tarda}


def test_las_propuestas_llevan_su_forma(fabrica):
    k, r, bus, cola, sus = fabrica
    bus.alta(TS, W, "p1", "dep:atlas", "medir: el radar (corto)", 10_000,
             10_000, {"gasto_max_mm": 10_000},
             forma=_forma("el radar de precios", "precios+radar",
                          promete="descartar"))
    s = sit.situacion(k, r, bus, cola, sus, W, "dep:atlas")
    assert s["propuestas_propias"][0]["forma"]["promete"] == "descartar"
```

Para `test_el_catalogo_no_repite_el_mismo_objeto`, las dos altas llevan
**la misma `clave`** y distinto `sobre`. Para
`test_el_catalogo_es_solo_del_propio_departamento`, el alta va con
`"dep:mercado"`. Para `test_el_catalogo_no_pasa_de_doce`, veinte altas en un
`for` con `clave=f"obj{i}"`.

Y en `test_plantel_jefe.py`, la linea 596-597 pasa de comparar el dict entero
a comparar lo que el test dice probar:

```python
    assert [d["id"] for d in s["descartadas_semana"]] == ["p0"]
    assert s["descartadas_semana"][0]["titulo"] == "radar de precios"
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_plantel_situacion.py -q -k "forma or catalogo"`
Expected: FAIL con `KeyError: 'forma'` y `KeyError: 'catalogo'`

- [ ] **Step 3: `base` gana la forma**

En `calipso/plantel/situacion.py`, el dict `base` (cerca de `:126`) gana:

```python
        # la forma tipada, o None para las escritas antes de que existiera.
        # El prompt la lee con .get() y cae al titulo, asi que una vieja se
        # sigue mostrando como siempre.
        base = {"id": id_, "titulo": datos.get("titulo", ""),
                "presupuesto_mm": datos.get("presupuesto_mm", 0),
                "forma": datos.get("forma")}
```

Y el dict de las descartadas (cerca de `:108`):

```python
                descartadas.append({"id": id_,
                                    "titulo": datos.get("titulo", ""),
                                    "forma": datos.get("forma")})
```

- [ ] **Step 4: El catalogo**

En el mismo recorrido por `bus.ids()`, acumular:

```python
    catalogo: list[str] = []
    vistas: set[str] = set()
```

y dentro del bucle, para toda propuesta del propio departamento **sea cual sea
su estado** -- viva, financiada, descartada o muerta -- antes de cualquier
`continue`:

```python
        forma = datos.get("forma")
        if mio and forma and forma.get("clave") not in vistas:
            # el catalogo existe para que el modelo COPIE en vez de
            # reinventar, asi que incluye tambien lo muerto: el objeto que
            # nombro hace dos meses es justo el que va a redactar distinto.
            # Deduplicado por clave, no por texto.
            vistas.add(forma["clave"])
            catalogo.append(forma["sobre"])
```

Y en el dict de retorno:

```python
        # los objetos que este departamento ya nombro, el mas nuevo primero,
        # hasta doce. El tope es de espacio del prompt, no una regla sobre lo
        # que puede hacer: nombrar uno que no esta en la lista es correcto y
        # esperado.
        "catalogo": list(reversed(catalogo))[:12],
```

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_situacion.py test_plantel_jefe.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add calipso/plantel/situacion.py test_plantel_situacion.py test_plantel_jefe.py
git commit -m "feat(plantel): la situacion lleva la forma y el catalogo de objetos"
```

---

### Task 4: El prompt pide la ficha

**Files:**
- Modify: `calipso/plantel/decision.py` (`prompt`, `:27-109`)
- Test: `test_plantel_decision.py`

**Interfaces:**
- Consumes: `situacion["catalogo"]` y `p["forma"]` de la Tarea 3;
  `ficha.PROMESAS` y `ficha.PLAZOS` de la Tarea 1.
- Produces: nada que consuma otra tarea. `parsear()` **no se toca**.

**Restriccion dura, verificada:** dos tests afirman `"trabajar" not in p` y
`"comentar" not in p` sobre el prompt entero. **Ningun texto nuevo puede
contener esas subcadenas** -- ni en la plantilla, ni en los ejemplos, ni en el
catalogo. Por eso la plantilla usa un marcador generico y no un ejemplo
concreto.

- [ ] **Step 1: Escribir los tests que fallan**

En `test_plantel_decision.py`:

```python
def test_el_prompt_pide_la_ficha_con_sus_cuatro_renglones():
    p = dec.prompt(_situacion_minima(), 50)
    for campo in ("sobre:", "promete:", "tarda:", "porque:"):
        assert campo in p, campo


def test_el_prompt_nombra_las_seis_promesas_y_los_cuatro_plazos():
    p = dec.prompt(_situacion_minima(), 50)
    for palabra in ficha.PROMESAS:
        assert palabra in p, palabra
    for plazo in ficha.PLAZOS:
        assert plazo in p, plazo


def test_una_propuesta_con_forma_se_muestra_como_ficha():
    s = _situacion_minima()
    s["propuestas_propias"] = [{
        "id": "p4", "titulo": "lo viejo", "presupuesto_mm": 0,
        "forma": {"sobre": "el banco del lector", "clave": "banco+lector",
                  "promete": "construir", "tarda": "medio"}}]
    p = dec.prompt(s, 50)
    assert "construir: el banco del lector (medio)" in p
    assert "lo viejo" not in p


def test_una_propuesta_sin_forma_muestra_su_titulo():
    """Compatibilidad: no se le inventa una ficha a partir del titulo.
    Seria adivinar, y un objeto adivinado entraria al catalogo como si el
    departamento lo hubiera nombrado."""
    s = _situacion_minima()
    s["propuestas_propias"] = [{"id": "p4", "titulo": "algo viejo",
                                "presupuesto_mm": 0, "forma": None}]
    assert "algo viejo" in dec.prompt(s, 50)


def test_el_catalogo_aparece_cuando_hay_objetos():
    s = _situacion_minima()
    s["catalogo"] = ["el radar de precios"]
    p = dec.prompt(s, 50)
    assert "el radar de precios" in p


def test_sin_objetos_el_bloque_del_catalogo_no_aparece():
    """Un encabezado sobre una lista vacia le ensena al modelo que ese
    bloque no dice nada."""
    s = _situacion_minima()
    s["catalogo"] = []
    assert "que ya nombraste" not in dec.prompt(s, 50)


def test_los_trabajos_siguen_mostrando_su_titulo():
    """Un trabajo vivo ya no es una propuesta esperando: su identidad no
    esta en disputa, asi que no cambia de render."""
    s = _situacion_minima()
    s["trabajos"] = [{"id": "p1", "titulo": "radar de precios",
                      "gastado_mm": 1000, "presupuesto_mm": 10_000,
                      "forma": {"sobre": "x", "clave": "x",
                                "promete": "medir", "tarda": "corto"}}]
    assert "radar de precios" in dec.prompt(s, 50)
```

**`test_plantel_decision.py` no tiene helpers**: verificado, cada test arma su
dict `s` inline. Los tests de arriba hacen lo mismo, y `_situacion_minima()` es
esta funcion, que hay que agregar al archivo una sola vez:

```python
def _situacion_minima() -> dict:
    """Lo minimo que `prompt` indexa con corchetes. Las claves que lee con
    `.get()` -propuestas_propias, descartadas_semana, catalogo- se omiten a
    proposito: asi los tests que no hablan de ellas ejercitan el camino de
    una situacion que no las trae."""
    return {"nombre": "atlas", "disponible_mm": 400_000, "saldo_mm": 400_000,
            "presupuesto_semanal_mm": 25_000, "salidas_semana_mm": 7_000,
            "compuertas_pendientes": 2, "trabajos": [],
            "propuestas_ajenas": [], "capacidad": None}
```

Ojo con un test que ya existe y que no hay que romper: el de la linea 105
afirma `for accion in dec.ACCIONES: assert accion in p` -- las cinco acciones
aparecen en el prompt. La plantilla nueva no las toca.

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_plantel_decision.py -q -k "ficha or catalogo or promesas or forma or trabajos_siguen"`
Expected: FAIL

- [ ] **Step 3: El render de una propuesta**

En `calipso/plantel/decision.py`, arriba de `prompt`, con el import nuevo
`from . import ficha` junto a los que ya estan:

```python
def _como_se_ve(p: dict) -> str:
    """La ficha si la tiene, el titulo si no.

    Con `.get()` y no con corchetes a proposito: las propuestas escritas
    antes de que la forma existiera no traen la clave, y los tests del
    prompt arman sus dicts a mano sin ella. Un `p["forma"]` las reventaria
    con KeyError en vez de mostrar lo que hay.
    """
    f = p.get("forma")
    if not f:
        return p.get("titulo", "")
    return f"{f['promete']}: {f['sobre']} ({f['tarda']})"
```

Y las tres listas de `prompt` pasan a usarlo. `trabajos` **no** (ver la
decision P4 del plan):

```python
    propias = "\n".join(
        f"  - {p['id']}: {_como_se_ve(p)}"
        for p in s.get("propuestas_propias", [])) or "  (ninguna)"
    ajenas = "\n".join(
        f"  - {p['id']}: {_como_se_ve(p)} (de {p['dueno']})"
        for p in s["propuestas_ajenas"]) or "  (ninguna)"
    rechazadas = "\n".join(f"  - {_como_se_ve(p)}"
                           for p in s.get("descartadas_semana", []))
```

- [ ] **Step 4: El catalogo y la plantilla**

Junto a `aprendido` y `ultimas`, un bloque condicional mas:

```python
    # los objetos que este departamento ya nombro, para que COPIE en vez de
    # reinventar: sin esto "radar de precios" y "monitor de precios" son dos
    # familias, ocupan dos lugares en la mesa y un "nunca mas" sobre una no
    # tapa la otra. Condicional como los otros dos: un encabezado sobre una
    # lista vacia le ensena al modelo que ese bloque no dice nada.
    objetos = s.get("catalogo") or []
    catalogo = ("Objetos que ya nombraste (si hablas de uno, escribilo "
                "igual):\n" + "\n".join(f"  - {o}" for o in objetos) + "\n\n"
                ) if objetos else ""
```

`catalogo` se suma al `return` junto a `aprendido` y `ultimas`, en ese orden:

```python
    return (
        aprendido +
        ultimas +
        catalogo +
        f"Sos el jefe del departamento {s['nombre']} ...
```

Y el cierre del prompt, donde hoy dice `"Segunda linea: un renglon con el
motivo.\n"`, pasa a:

```python
        "Segunda linea: un renglon con el motivo.\n\n"
        "Si elegis proponer, en vez del motivo van CUATRO renglones:\n"
        "  sobre:   <el objeto, en tus palabras>\n"
        "  promete: " + " | ".join(ficha.PROMESAS) + "\n"
        "  tarda:   " + " | ".join(ficha.PLAZOS) + "\n"
        "  porque:  <un renglon, opcional>\n"
```

**No poner un ejemplo concreto de `sobre`.** Un ejemplo con las subcadenas
`trabaj` o `coment` rompe dos tests que afirman que esas palabras no aparecen
en el prompt cuando el menu no las ofrece, y el marcador generico dice lo
mismo sin el riesgo.

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_decision.py -q`
Expected: PASS, incluidos los doce tests viejos del prompt -- que ahora son la
suite de regresion del camino de compatibilidad.

- [ ] **Step 6: Commit**

```bash
git add calipso/plantel/decision.py test_plantel_decision.py
git commit -m "feat(plantel): el prompt pide la ficha y le muestra al jefe sus objetos"
```

---

### Task 5: La valvula

**Files:**
- Create: `calipso/plantel/ilegibles.py`
- Modify: `calipso/plantel/jefe.py` (`tic`, entre `:353` y `:355`; la anotacion
  `Callable` de `:33`)
- Test: `test_plantel_ilegibles.py` (nuevo), `test_plantel_jefe.py`

**Interfaces:**
- Consumes: `ficha.parsear_ficha(texto)` de la Tarea 1.
- Produces, y lo usan las Tareas 6 y 7:
  - `ilegibles.ruta(base) -> pathlib.Path` (`<base>/economia/ilegibles.jsonl`)
  - `ilegibles.anotar(base, semana, departamento, crudo) -> None` -- **sin
    `ts`**: `jefe.tic` no tiene ninguno. Verificado: su firma es
    `tic(ctx, cuenta, semana)` y en todo `jefe.py` no hay `ahora`, `_ahora`
    ni `isoformat`. Un rastro se pone su propia hora; un asiento del libro
    no, y por eso el libro si la recibe del llamador.
  - `ilegibles.colapsados(base) -> list[dict]` con
    `{departamento, crudo, veces, ts}`, el mas nuevo primero
  - `contratar(situacion, accion, ref, motivo="", ficha=None)`

**Lo que hace peligrosa esta tarea, y hay que respetarlo:** `_puede`
(`jefe.py:230-292`) **no tiene rama por defecto**, y el `contratar` de
produccion **no tiene guarda de accion** -- todo lo que no es
`comentar`/`trabajar`/`pedir` cae en el camino que escribe en el bus. Por eso
**una ficha ilegible no es una accion nueva**: el corte se hace en `tic` con la
accion `proponer` intacta, fijando `permiso = False` a mano y sin llamar a
`_puede`.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `test_plantel_ilegibles.py`:

```python
#!/usr/bin/env python3
"""
test_plantel_ilegibles.py — la valvula de la gramatica de proponer.
"""
from calipso.plantel import ilegibles

W = "2026-W36"


def test_lo_ilegible_queda_anotado(tmp_path):
    ilegibles.anotar(tmp_path, W, "dep:atlas", "una idea larga")
    filas = ilegibles.colapsados(tmp_path)
    assert len(filas) == 1
    assert filas[0]["crudo"] == "una idea larga"
    assert filas[0]["veces"] == 1


def test_el_mismo_texto_se_colapsa_con_su_contador(tmp_path):
    """A temperatura 0 la repeticion es byte a byte: 200 tics tienen que dar
    una fila con un contador, no 200 filas."""
    for _ in range(200):
        ilegibles.anotar(tmp_path, W, "dep:atlas", "la misma idea")
    filas = ilegibles.colapsados(tmp_path)
    assert len(filas) == 1 and filas[0]["veces"] == 200


def test_dos_departamentos_no_se_mezclan(tmp_path):
    ilegibles.anotar(tmp_path, W, "dep:atlas", "misma idea")
    ilegibles.anotar(tmp_path, W, "dep:taller", "misma idea")
    assert len(ilegibles.colapsados(tmp_path)) == 2


def test_sin_archivo_la_lista_es_vacia(tmp_path):
    assert ilegibles.colapsados(tmp_path) == []


def test_una_linea_rota_no_voltea_la_lectura(tmp_path):
    """Append-only escrito por un proceso que puede morir a la mitad: una
    linea cortada no puede esconder las demas."""
    ilegibles.anotar(tmp_path, W, "dep:atlas", "buena")
    ruta = ilegibles.ruta(tmp_path)
    with ruta.open("a", encoding="utf-8") as f:
        f.write("{esto no es json\n")
    assert len(ilegibles.colapsados(tmp_path)) == 1
```

Y en `test_plantel_jefe.py`:

```python
def test_una_ficha_ilegible_no_contrata_pero_deja_aviso(tmp_path):
    """La valvula: la prosa que no entra en la ficha no cae en `nada`, cae
    en un aviso con la prosa cruda adentro."""
    ctx, contratos, _ = armar(tmp_path, "proponer\nhay hueco en precios")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "proponer"
    assert out["actuo"] is False
    assert "ilegible" in out["freno"]
    assert contratos == []
    filas = ilg.colapsados(tmp_path)
    assert len(filas) == 1 and filas[0]["crudo"] == "hay hueco en precios"


def test_una_ficha_ilegible_SI_escribe_memoria(tmp_path):
    """El arreglo de la semana congelada. `nada` no anota -- el modelo
    eligio no hacer nada -- y un freno tampoco -- la maquina lo paro. Pero
    una ficha ilegible es el modelo intentando y fallando: sin anotarla, el
    prompt del tic siguiente es identico, y a temperatura 0 la respuesta
    tambien. El primer tic que no parsea le termina la semana al
    departamento."""
    ctx, _, _ = armar(tmp_path, "proponer\nhay hueco en precios")
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    assert ctx.memoria.recordado != []


def test_nada_sigue_sin_escribir_memoria(tmp_path):
    """El otro lado de la distincion: elegir no hacer nada no es fallar."""
    ctx, _, _ = armar(tmp_path, "nada\ntodo tranquilo")
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    assert ctx.memoria.recordado == []


def test_una_ficha_buena_contrata_y_le_llega_al_contratista(tmp_path):
    ctx, contratos, _ = armar(
        tmp_path,
        "proponer\nsobre: el radar de precios\npromete: descartar\n"
        "tarda: corto\nporque: no rindio")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "proponer" and out["actuo"] is True
    assert contratos and contratos[0][0] == "proponer"


def test_un_aviso_que_revienta_no_voltea_el_tic(tmp_path, monkeypatch):
    """Mismo trato que la memoria: el rastro no puede volverse una forma de
    tumbar el tic. Sin su propio try/except, el `except Exception` de `tic`
    lo reporta como 'reviento actuando'."""
    def explota(*a, **k):
        raise OSError("disco lleno")
    monkeypatch.setattr(ilg, "anotar", explota)
    ctx, contratos, _ = armar(tmp_path, "proponer\nhay hueco")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "proponer" and out["actuo"] is False
    assert "reviento" not in (out["motivo"] or "")
```

Con `from calipso.plantel import ilegibles as ilg` junto a los imports que ese
archivo ya tiene.

Y **actualizar los diez tests que hoy mandan `"proponer\n<prosa>"` y esperan
que contrate**, cambiando la respuesta por una ficha valida. Son, verificados:
`test_en_ensayo_decide_y_publica_pero_no_contrata` (L69),
`test_en_vivo_contrata` (L82), `test_sin_saldo_si_puede_proponer` (L135),
`test_la_agresividad_frena_proponer_pero_no_trabajar` (L275),
`test_presupuesto_semanal_cero_no_frena_proponer_por_agresividad` (L147),
`test_un_departamento_personal_corre_el_mismo_bucle` (L313),
`test_memoria_que_revienta_no_borra_la_contratacion` (L377),
`test_el_techo_de_propuestas_frena_proponer` (L427),
`test_descartar_una_propuesta_destraba_el_techo` (L442),
`test_con_menos_propuestas_que_el_techo_sigue_pudiendo_proponer` (L467),
`test_el_techo_de_propuestas_no_tapa_la_agresividad` (L480).

**`test_la_agresividad_frena_proponer_pero_no_trabajar` es el que importa:**
hoy manda `"proponer\notra apuesta"` y solo afirma `actuo is False`. Con la
valvula pasaria por accidente y dejaria de probar el freno de agresividad. Su
respuesta **tiene que** pasar a una ficha valida.

Y `test_el_motivo_del_parser_llega_al_contratista` (L395) **se reescribe, no
se re-inputea**: su docstring afirma que el titulo del bus es el motivo crudo,
que es exactamente lo que la seccion 7 del spec deroga. Pasa a afirmar que lo
que llega al contratista es la ficha.

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_plantel_ilegibles.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'calipso.plantel.ilegibles'`

- [ ] **Step 3: El almacen de lo ilegible**

Crear `calipso/plantel/ilegibles.py`:

```python
#!/usr/bin/env python3
"""
calipso/plantel/ilegibles.py — la valvula de la gramatica de `proponer`.

Una ficha que no se entiende NO cae en `nada`: cae aca, y de aca sale a la
bandeja de la fabrica como un aviso con la prosa cruda adentro.

Por que no va al bus: el libro es contable y un aviso no es un objeto
economico -- no ocupa lugar, no compite, no se puede financiar y no cuenta
para el badge. Y por que existe: sin esto, la gramatica amordazaria al
departamento, porque lo que no entra en cuatro renglones desapareceria sin
dejar rastro.

Append-only y sin candado, como `cola._apilar`: una linea corta abierta en
modo "a" no se entrelaza con la de otro proceso.
"""
from __future__ import annotations

import datetime
import json
import pathlib

ARCHIVO = "ilegibles.jsonl"


def _ahora() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def ruta(base) -> pathlib.Path:
    # al lado del bus, que es donde vive el resto del estado del plantel
    return pathlib.Path(base) / "economia" / ARCHIVO


def anotar(base, semana: str, departamento: str, crudo: str) -> None:
    """La hora se la pone esta funcion, no el llamador.

    Al reves que un asiento del libro, que la recibe de afuera para que dos
    escrituras del mismo tic queden con la misma: esto es un rastro, nadie
    lo concilia contra nada, y `jefe.tic` no tiene ningun timestamp a mano
    -- su firma es `(ctx, cuenta, semana)`.
    """
    p = ruta(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    linea = json.dumps({"ts": _ahora(), "semana": semana,
                        "departamento": departamento, "crudo": crudo},
                       ensure_ascii=False)
    with p.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")


def colapsados(base) -> list[dict]:
    """Una fila por texto distinto, con su contador y su ts mas nuevo.

    Se colapsa por igualdad EXACTA del texto, no por parecido: el modelo
    local corre a temperatura 0, asi que la repeticion dentro de una semana
    es byte a byte y doscientos tics dan una fila con `veces: 200`. Un
    colapso difuso no se podria explicar y no haria falta.

    Una linea rota no voltea la lectura: el archivo lo escribe un proceso
    que puede morir a la mitad, y una linea cortada no puede esconder las
    demas.
    """
    p = ruta(base)
    try:
        crudo_texto = p.read_text(encoding="utf-8")
    except OSError:
        return []
    filas: dict[tuple[str, str], dict] = {}
    for linea in crudo_texto.splitlines():
        if not linea.strip():
            continue
        try:
            d = json.loads(linea)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        clave = (d.get("departamento", ""), d.get("crudo", ""))
        fila = filas.get(clave)
        if fila is None:
            filas[clave] = {"departamento": clave[0], "crudo": clave[1],
                            "veces": 1, "ts": d.get("ts", "")}
        else:
            fila["veces"] += 1
            fila["ts"] = d.get("ts", "") or fila["ts"]
    return sorted(filas.values(), key=lambda f: f["ts"], reverse=True)
```

- [ ] **Step 4: El corte en `tic`**

En `calipso/plantel/jefe.py`, el import nuevo `from . import ficha, ilegibles`
junto a los que ya estan, y la anotacion de `:33` pasa a admitir el argumento
con nombre:

```python
    contratar: Callable[..., Any]
```

Y en `tic`, entre `ctx.publicar("razonando", ...)` (`:352-353`) y
`permiso, freno = _puede(...)` (`:355`):

```python
        # La ficha solo existe para `proponer`. Se lee aparte y no dentro de
        # `parsear` porque `parsear` devuelve una 3-upla que seis tests
        # desempaquetan o comparan entera, y ninguno de ellos habla de
        # proponer.
        f = ficha.parsear_ficha(crudo) if accion == "proponer" else None

        if accion == "proponer" and f is None:
            # LA VALVULA. Y ojo con el atajo que parece obvio: NO se le
            # puede dar a esto un valor de accion propio. `_puede` no tiene
            # rama por defecto -- una accion desconocida cae al tramo final
            # y devuelve True con saldo -- y el `contratar` de produccion no
            # tiene guarda de accion: todo lo que no es comentar, trabajar o
            # pedir termina en el camino que llama a `bus.alta`. O sea que
            # una accion nueva escribiria en el libro una propuesta de
            # verdad, con este texto ilegible de titulo. Por eso el corte se
            # hace aca, con la accion intacta y el permiso en False a mano,
            # sin pasar por `_puede`.
            try:
                ilegibles.anotar(ctx.base, semana, cuenta, motivo)
                # y ACA se rompe la semana congelada: `nada` no anota
                # -el modelo eligio no hacer nada- y un freno tampoco -la
                # maquina lo paro-, pero esto es el modelo intentando y
                # fallando. Sin la anotacion el prompt del tic siguiente es
                # identico, y a temperatura 0 la respuesta tambien: el
                # primer tic que no parsea le termina la semana al
                # departamento.
                ctx.memoria.remember(f"ficha ilegible: {motivo}",
                                     kind="jefe", departamento=cuenta)
            except Exception as exc:
                # mismo trato que el `remember` de mas abajo: que el rastro
                # falle no puede volverse una forma de tumbar el tic. Sin
                # este except lo caza el `except Exception` de afuera y el
                # tic entero sale como "reviento actuando".
                fin = "error"
                motivo = f"{motivo} (no pudo anotar el aviso: {exc})"
            return salida(accion, ref, motivo, False,
                          "ficha ilegible: no se entendio que proponia")

        permiso, freno = _puede(estado, s, accion, ref)
        resultado = None
        if permiso:
            resultado = ctx.contratar(s, accion, ref, motivo, ficha=f)
```

No hace falta ningun timestamp en `tic`: `ilegibles.anotar` se pone el suyo,
justamente porque `tic(ctx, cuenta, semana)` no tiene ninguno.

- [ ] **Step 5: El arnes admite el argumento**

En `test_plantel_jefe.py`, el `contratar` que inyecta `armar()`:

```python
        contratar=lambda s, a, ref, m="", ficha=None: (
            contratos.append((a, ref, m)) or {"ok": True}),
```

La tupla que captura **no cambia**: los 44 tests que comparan `contratos`
siguen valiendo. Lo que llega al bus se verifica en la Tarea 6, contra un bus
de verdad.

- [ ] **Step 6: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_ilegibles.py test_plantel_jefe.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add calipso/plantel/ilegibles.py calipso/plantel/jefe.py test_plantel_ilegibles.py test_plantel_jefe.py
git commit -m "feat(plantel): la valvula, y con ella el arreglo de la semana congelada"
```

---

### Task 6: El contratista escribe la forma

**Files:**
- Modify: `calipso/server.py` (`_contratar_para`: la firma cerca de `:5440` y
  la rama de `proponer`, `:5574-5619`)
- Test: `test_plantel_server.py`

**Interfaces:**
- Consumes: `ficha.titulo_de`, `ficha.SEMANAS_MAX` de la Tarea 1;
  `bus.alta(..., forma=...)` de la Tarea 2; el argumento `ficha=` de la Tarea 5.
- Produces: nada que consuma otra tarea.

- [ ] **Step 1: Escribir los tests que fallan**

En `test_plantel_server.py`, usando `_contratar_real`:

```python
FICHA = {"sobre": "el radar de precios", "clave": "precios+radar",
         "promete": "descartar", "tarda": "corto", "porque": "no rindio"}


def test_el_camino_de_produccion_siempre_manda_la_forma(tmp_path, monkeypatch):
    """El guarda de la seccion 8 del spec, apuntado al unico lugar que
    importa: `forma` es opcional en `bus.alta` para no barrer 123 sitios de
    test, asi que lo que hay que fijar es que produccion nunca se la
    olvide."""
    contratar, bus_real = _contratar_real(tmp_path, monkeypatch)
    r = contratar({"nombre": "atlas", "presupuesto_semanal_mm": 10_000,
                   "agresividad_pct": 100, "salidas_semana_mm": 0},
                  "proponer", None, "no rindio", ficha=FICHA)
    datos = bus_real.datos(r["propuesta"])
    assert datos["forma"] == {"sobre": "el radar de precios",
                              "clave": "precios+radar",
                              "promete": "descartar", "tarda": "corto"}


def test_el_titulo_sale_de_la_ficha_y_no_del_motivo_crudo(tmp_path, monkeypatch):
    contratar, bus_real = _contratar_real(tmp_path, monkeypatch)
    r = contratar({"nombre": "atlas", "presupuesto_semanal_mm": 10_000,
                   "agresividad_pct": 100, "salidas_semana_mm": 0},
                  "proponer", None, "no rindio", ficha=FICHA)
    assert bus_real.datos(r["propuesta"])["titulo"] == (
        "descartar: el radar de precios (corto) -- no rindio")


def test_el_plazo_de_la_ficha_manda_el_criterio_de_muerte(tmp_path, monkeypatch):
    """Antes eran cuatro semanas escritas a mano, iguales para una
    propuesta de una semana que para una de un trimestre."""
    contratar, bus_real = _contratar_real(tmp_path, monkeypatch)
    largo = {**FICHA, "tarda": "largo"}
    r = contratar({"nombre": "atlas", "presupuesto_semanal_mm": 10_000,
                   "agresividad_pct": 100, "salidas_semana_mm": 0},
                  "proponer", None, "x", ficha=largo)
    assert bus_real.datos(r["propuesta"])["criterio"]["semanas_max"] == 12


def test_sin_ficha_el_contratista_no_escribe_nada(tmp_path, monkeypatch):
    """No hay camino de produccion que llegue aca sin ficha -- el jefe la
    desvia antes -- pero si alguna vez lo hubiera, escribir una propuesta
    sin identidad en un libro append-only es peor que no escribir."""
    contratar, bus_real = _contratar_real(tmp_path, monkeypatch)
    r = contratar({"nombre": "atlas", "presupuesto_semanal_mm": 10_000,
                   "agresividad_pct": 100, "salidas_semana_mm": 0},
                  "proponer", None, "hay hueco")
    assert r["en"] == "nada"
    assert bus_real.ids() == []
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_plantel_server.py -q -k "forma or titulo_sale or plazo_de_la_ficha or sin_ficha"`
Expected: FAIL con `TypeError: contratar() got an unexpected keyword argument 'ficha'`

- [ ] **Step 3: La firma y la rama de proponer**

En `calipso/server.py`, la firma del `contratar` interno:

```python
    def contratar(situacion, accion, ref, motivo="", ficha=None):
```

Y en la rama de `proponer`, reemplazar el armado del titulo y el `alta`:

```python
        if ficha is None:
            # No hay camino de produccion que llegue aca sin ficha: `tic` la
            # desvia a la valvula antes de contratar. Pero el libro es
            # append-only, asi que una propuesta sin identidad escrita por
            # un llamador futuro no se podria borrar despues.
            return {"accion": accion, "ref": ref, "en": "nada",
                    "motivo": "una propuesta sin ficha no tiene identidad: "
                              "no se escribe"}
        propuesta = f"{situacion['nombre']}-{uuid.uuid4().hex[:8]}"
        # El titulo sale de la ficha, no del motivo crudo: es lo que Pedro
        # lee, y ahora lleva adentro lo mismo que la maquina compara.
        titulo = _plantel_ficha.titulo_de(ficha)
        # `semanas_max` sale del plazo que declaro el jefe. Antes eran
        # cuatro semanas escritas a mano, iguales para una propuesta de una
        # semana que para una de un trimestre.
        semanas = _plantel_ficha.SEMANAS_MAX[ficha["tarda"]]
        # al libro va la forma SIN `porque`: la prosa no se compara, y
        # guardarla adentro de la forma invitaria a compararla.
        forma = {c: ficha[c] for c in ("sobre", "clave", "promete", "tarda")}
        with _eco_candado(pagador.ruta_libro):
            bus_fresco = _eco_bus.Bus(pagador.ruta_bus)
            if _bandeja_llena(bus_fresco):   # segunda linea: ver arriba
                return {"accion": accion, "ref": ref, "en": "nada",
                        "motivo": "la bandeja se lleno mientras este tic "
                                  "decidia: que Pedro despeje antes de "
                                  "sumar otra"}
            bus_fresco.alta(ts, semana, propuesta, cuenta, titulo,
                            presupuesto, presupuesto,
                            {"gasto_max_mm": presupuesto,
                             "semanas_max": semanas},
                            forma=forma)
        return {"accion": accion, "ref": ref, "propuesta": propuesta}
```

El import va en el bloque del plantel que ya existe en `calipso/server.py`
(cerca de la linea 5256), que tiene su propio try/except a proposito. Queda
asi, con las dos lineas nuevas de esta tarea y la siguiente:

```python
try:
    from calipso.plantel import ficha as _plantel_ficha
    from calipso.plantel import ilegibles as _plantel_ilegibles
    from calipso.plantel import interruptor as _plantel_it
    from calipso.plantel import jefe as _plantel_jefe
except Exception:  # el plantel no esta disponible: el tablero responde inactivo
    _plantel_ficha = _plantel_ilegibles = None
    _plantel_it = _plantel_jefe = None
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_server.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py test_plantel_server.py
git commit -m "feat(server): la propuesta se escribe con su forma, su titulo y su plazo"
```

---

### Task 7: El aviso llega a la bandeja

**Files:**
- Modify: `calipso/economia/bus.py` (`como_items`, en el adaptador del inbox)
- Modify: `calipso/server.py` (el endpoint de la mesa)
- Test: `test_inbox.py`, `test_mesa_server.py`

**Interfaces:**
- Consumes: `ilegibles.colapsados(base)` de la Tarea 5.
- Produces: nada.

- [ ] **Step 1: Escribir los tests que fallan**

En `test_inbox.py`:

```python
def test_una_ficha_ilegible_es_un_aviso_y_no_una_decision():
    """No ocupa lugar, no compite, no se puede financiar y no cuenta para
    el badge -- pero se ve."""
    datos = {"activa": True, "propuestas": [], "ilegibles": [
        {"departamento": "dep:atlas", "crudo": "hay hueco en precios",
         "veces": 3, "ts": "2026-09-01T10:00:00"}]}
    items = eco_bus.como_items(datos)
    avisos = [i for i in items if i["clase"] == "aviso"]
    assert len(avisos) == 1
    assert avisos[0]["cuerpo"]["verbos_validos"] == []
    assert "hay hueco en precios" in avisos[0]["titulo"]


def test_el_contador_de_repeticiones_se_ve():
    """Doscientos tics dan una fila con un contador, no doscientas filas: si
    el numero no se muestra, la fila miente sobre cuanto se repitio."""
    datos = {"activa": True, "propuestas": [], "ilegibles": [
        {"departamento": "dep:atlas", "crudo": "la misma idea",
         "veces": 200, "ts": "2026-09-01T10:00:00"}]}
    aviso = [i for i in eco_bus.como_items(datos) if i["clase"] == "aviso"][0]
    assert "200" in aviso["titulo"]


def test_sin_ilegibles_no_hay_avisos():
    datos = {"activa": True, "propuestas": [], "ilegibles": []}
    assert [i for i in eco_bus.como_items(datos) if i["clase"] == "aviso"] == []


def test_una_respuesta_vieja_sin_la_clave_no_rompe():
    """El endpoint puede no traerla: el adaptador no puede reventar por
    eso."""
    datos = {"activa": True, "propuestas": []}
    assert eco_bus.como_items(datos) == []
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_inbox.py -q -k "ilegible or contador_de_repeticiones or sin_ilegibles"`
Expected: FAIL

- [ ] **Step 3: El adaptador emite el aviso**

En `calipso/economia/bus.py`, al final de `como_items`, antes del `return`:

```python
    # Las fichas que no se entendieron. Son AVISOS y no decisiones: nada
    # espera un verbo de Pedro, y contarlas para el badge lo haria mentir.
    # El molde es el aviso que emite el adaptador de permisos cuando no
    # puede leer su archivo: clase "aviso", `verbos_validos` vacio.
    for i, fila in enumerate(datos_endpoint.get("ilegibles") or []):
        veces = fila.get("veces", 1)
        repeticion = f" (x{veces})" if veces > 1 else ""
        items.append({
            "id": f"ilegible:{i}", "origen": ORIGEN_INBOX, "clase": "aviso",
            "ts": fila.get("ts", ""),
            "titulo": f"{fila.get('departamento', '?')} escribio algo que no "
                      f"entra en una ficha{repeticion}: {fila.get('crudo', '')}",
            "cuerpo": {"departamento": fila.get("departamento", ""),
                       "crudo": fila.get("crudo", ""),
                       "veces": veces, "verbos_validos": []},
            "estado": "aviso", "respuesta": None})
```

- [ ] **Step 4: La metrica llega al item**

La seccion 7 del spec dice que la metrica de exito **se deriva al mostrarla y
no se guarda**. Sin este paso, `ficha.METRICA` seria una tabla que nadie lee:
codigo muerto en el primer commit.

Se deriva en el ENDPOINT y no en el adaptador, para no meter un import de
`calipso.plantel` adentro de `calipso.economia`: el libro no puede depender de
quien lo escribe. En el endpoint de la mesa, cada propuesta que lleva forma
gana su metrica:

```python
        # la metrica de exito NO se guarda en el libro: se deriva de
        # `promete` cada vez que se muestra. Es la unica manera de que
        # cambiar la tabla arregle tambien las propuestas viejas.
        f = datos.get("forma")
        if f and _plantel_ficha is not None:
            fila["metrica"] = _plantel_ficha.METRICA.get(f["promete"], "")
```

sobre el dict que el endpoint ya arma por propuesta. Y en `como_items`, el
cuerpo del item de una propuesta gana la clave, con `.get()`:

```python
            "metrica": p.get("metrica", ""),
```

Con su test, en `test_inbox.py`:

```python
def test_la_propuesta_muestra_que_promete_medir():
    """La metrica no se guarda: se deriva. Si no llega al item, la tabla de
    METRICA es codigo muerto y Pedro no sabe contra que se juzga la
    propuesta."""
    datos = {"activa": True, "propuestas": [
        {"id": "p1", "titulo": "descartar: el radar (corto)",
         "estado": "alta", "metrica": "milimonedas por semana que dejan de "
                                      "salir", "presupuesto_mm": 1000}]}
    item = [i for i in eco_bus.como_items(datos) if i["clase"] == "decision"][0]
    assert "milimonedas por semana" in item["cuerpo"]["metrica"]
```

**Leer el endpoint de la mesa y `como_items` antes de escribir esto**: los
nombres exactos del dict por propuesta salen de ahi, y este paso solo agrega
una clave a cada uno.

- [ ] **Step 5: El endpoint suma la lista de ilegibles**

En el endpoint de la mesa de `calipso/server.py`, la respuesta gana:

```python
        # las fichas que no se entendieron viajan con la mesa y no por un
        # origen nuevo del inbox: son produccion de la fabrica que no llego
        # al bus, asi que pertenecen a la misma bandeja que las que si
        # llegaron -- y un origen nuevo obligaria a un descriptor entero
        # para algo que no tiene ni un verbo.
        "ilegibles": _plantel_ilegibles.colapsados(_ECO_BASE),
```

Con el import bajo la misma guarda que los demas del plantel. Si el modulo no
se pudo importar, la clave va `[]`: una bandeja que pierde sus avisos es mejor
que una que no carga.

- [ ] **Step 6: Correr los tests**

Run: `.venv/bin/python -m pytest test_inbox.py test_inbox_server.py test_mesa_server.py -q`
Expected: PASS

- [ ] **Step 7: La suite entera**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS. Es la primera corrida completa con las siete tareas juntas.

- [ ] **Step 8: Verificar que lo agregado es solo ascii**

Run: `git diff $(git merge-base main HEAD)..HEAD | grep -nP '^\+.*[^\x00-\x7F]' || echo "solo ascii"`
Expected: `solo ascii`

- [ ] **Step 9: Commit**

```bash
git add calipso/economia/bus.py calipso/server.py test_inbox.py test_mesa_server.py
git commit -m "feat(mesa): la ficha que no se entendio se ve como aviso en la bandeja"
```

---

## Lo que este plan NO hace

- **El `no_siempre` de la mesa.** Es lo que esta gramatica desbloquea, y es su
  propio spec: necesita un almacen de reglas, un punto de captura del alcance
  en `api_eco_bus_descartar` (que hoy no recibe cuerpo) y el corte en `_puede`.
- **El PvP.** Necesita la vara que sale de `promete` y `tarda`, mas el colapso
  por familia, el piso por departamento y el desempate.
- **Darle mundo al prompt.** Es el cuello de botella real y esta escrito en la
  seccion 2 del spec: `situacion()` le devuelve al jefe plata y titulos que el
  propio mecanismo escribio, y nadie escribe el `core` del departamento. Esto
  ordena lo que un departamento dice; no le da nada nuevo que decir.
- **Medir la ficha contra el modelo real.** La seccion 13 del spec pide correr
  el prompt nuevo contra el modelo local 50 veces y contar parseos. No es un
  criterio de aceptacion del codigo -- su resultado puede mandar a cambiar la
  plantilla, no el parser -- y se hace despues de que esto este verde.
