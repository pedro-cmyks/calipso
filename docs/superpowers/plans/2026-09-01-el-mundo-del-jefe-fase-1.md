# El mundo del jefe, Fase 1 -- plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que el jefe de un departamento vea, en su prompt, para que existe su
departamento y que proyectos le tocan -- y medir si eso cambia lo que decide,
antes de construir nada mas.

**Architecture:** Todo se inyecta, nada se importa nuevo en el plantel. La
carta es un archivo que Pedro escribe, leido por una funcion pura de
`memory.py` que NO instancia un `Scope` (instanciarlo crearia directorios y un
chroma como efecto de una lectura). `server.py` lee la carta y los proyectos y
los pone en el `Contexto`; `jefe.tic` los pasa; `decision.prompt` los rendera.
El entregable central no es codigo: es la medicion que decide si la Fase 2 se
escribe.

**Tech Stack:** Python 3.14, pytest. Ollama local (`qwen2.5:7b`) para el
experimento. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-01-el-mundo-del-jefe-design.md`

## Global Constraints

- **SIN EMOJIS.** En ningun lado: codigo, comentarios, texto del prompt,
  mensajes de commit.
- **Nombres, comentarios y docstrings en ESPANOL.** Commits **sin tildes ni
  enie**.
- **NUNCA importar `calipso` fuera de pytest.** El paquete escribe en el
  `~/.calipso` real. **Hay un servidor de Calipso CORRIENDO en esta maquina**:
  no pararlo, no reiniciarlo.
- **`git add` con rutas explicitas**, nunca `-A` ni `.`.
- **Leer no escribe.** Ninguna funcion de este plan puede crear un directorio
  ni abrir un chroma como efecto de una lectura.
- **Los modulos del plantel son puros** (`situacion`, `decision`,
  `interruptor`): no tocan disco. Todo lo que necesiten llega por parametro.
- **Antes de escribir un test, ABRIR el archivo de tests y verificar sus
  convenciones**: alias de import, constantes de modulo, fixtures, helpers. Si
  el brief no calza con el archivo real, **el brief esta mal**.
- **Interprete:** `.venv/bin/python`. Tests: `.venv/bin/python -m pytest <archivo> -q`
  desde `/var/home/pedro/calipso`.

---

## Contexto verificado (leer antes de la Tarea 1)

Siete hechos que salieron de leer el codigo y el disco real. Si alguno resulta
falso al implementar, es un defecto del plan: se arregla el plan.

1. **`_pensar_local` no manda `num_ctx`.** Verificado: las unicas opciones que
   viajan son `{"temperature": 0}`, y `grep -rn "num_ctx"` sobre todo el repo
   da **cero ocurrencias**. Ollama corre con su default y trunca **desde el
   comienzo** del prompt.

2. **`decision.prompt` arma `aprendido + ultimas + catalogo + <el resto>`**, o
   sea que lo primero del prompt es lo primero que se tira.

3. **`Scope.__init__` (`memory.py:55-63`) hace `mkdir` de dos directorios y
   abre un `chromadb.PersistentClient`.** Por eso la carta NO se lee
   instanciando `Memory.departamento(...)`.

4. **`test_memory.py` no tiene un solo `def test_`**: es de los archivos con
   `main()` que pytest no colecta. Un test de la carta ahi **no corre nunca**.
   El archivo hermano que si colecta es `test_memoria_ambito.py` (11 tests).

5. **`Contexto` (`jefe.py:25-36`) es un dataclass** cuyo ultimo campo
   (`publicar`) tiene default. Cualquier campo nuevo tiene que tener default
   tambien, o el dataclass no compila.

6. **`armar()` (`test_plantel_jefe.py:40-69`) construye el `Contexto` con
   keywords**, asi que campos nuevos con default no rompen sus 44 llamadas.

7. **La cuenta del jefe lleva prefijo.** `situacion` hace
   `registro.obtener(cuenta.split(":", 1)[1])` y `server.py:2788` hace el mismo
   corte para la memoria. El catastro guardaria `departamento` **con la cuenta
   completa** (`dep:taller`), y el filtro compara contra la cuenta completa. Si
   se comparan formatos distintos, el jefe ve "ninguno asignado" y **nada
   falla**.

## Las cuatro decisiones que este plan toma

- **P1 -- todo se inyecta por el `Contexto`.** Ni `jefe.py` ni `decision.py`
  ganan un import nuevo. `server.py` lee la carta y los proyectos y los pone en
  el `Contexto`, igual que ya hace con la memoria, el kernel y el bus. Motivo:
  es el patron que el modulo ya tiene, y es lo que permite que los tests
  inyecten una carta sin tocar disco.

- **P2 -- la carta la lee `memory.py`, no el plantel.** `memory.py` es el dueno
  del slug y del layout del directorio de un departamento; copiar `_slug` una
  tercera vez seria la tercera copia de algo que el repo ya duplico una vez a
  proposito. Pero la funcion nueva es **pura**: no instancia `Scope`.

- **P3 -- `situacion` no cambia.** Los proyectos no son economicos y `situacion`
  es "lo plegado del libro". El filtro por cuenta y el render viven en
  `decision.py`, que es el armador del prompt. Motivo: una sola ruta de datos
  por bloque, y `situacion` sigue siendo pura sin ganar un parametro que no le
  corresponde.

- **P4 -- el orden de los bloques lo decide la medicion, no el gusto.** El plan
  los pone arriba (que es lo correcto en significado) y la Tarea 6 mide si
  sobreviven al truncado. Si no sobreviven, el orden se cambia con dato, no
  antes.

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `calipso/server.py` | `num_ctx` explicito; lee la carta y los proyectos y los inyecta al `Contexto` |
| `calipso/memory.py` | `ruta_carta` y `leer_carta`: puras, sin instanciar `Scope` |
| `calipso/plantel/decision.py` | `proyectos_de` (filtro por cuenta + procedencia) y los dos bloques del prompt |
| `calipso/plantel/jefe.py` | `Contexto` gana dos campos; `tic` los pasa a `prompt` |
| `test_memoria_carta.py` (**nuevo**) | los tests de la carta |
| `calipso/verification.py` | que tocar la carta dispare sus tests |
| `experimentos/carta_vs_sin_carta.py` (**nuevo**) | el experimento |

---

### Task 1: El tamano del contexto, explicito

**Files:**
- Modify: `calipso/server.py`, dentro de `_pensar_local` (cerca de la linea 5385)
- Test: `test_plantel_server.py`

**Interfaces:**
- Consumes: nada.
- Produces: nada que consuma otra tarea. Pero **la Tarea 6 no significa nada sin
  esto**: sin `num_ctx` fijo, no se sabe si el modelo ignoro la carta o si
  nunca la recibio.

- [ ] **Step 1: Escribir el test que falla**

En `test_plantel_server.py`. Ese archivo **ya importa `dispatch` directo**
(linea 5) y ya tiene un test que hace `monkeypatch.setattr(dispatch,
"_http_post_json", ...)` (linea 84): usa ese mismo camino, no `srv.dispatch`.

```python
def test_el_modelo_local_recibe_un_contexto_explicito(monkeypatch):
    """Ollama trunca desde el COMIENZO del prompt cuando no entra, y
    `decision.prompt` pone lo mas importante primero. Sin `num_ctx` fijo,
    el jefe puede dejar de ver su carta sin que nada avise -- y la medicion
    de la Tarea 6 no podria distinguir "el modelo la ignoro" de "nunca le
    llego"."""
    visto = {}

    def post_espia(url, cuerpo):
        visto.update(cuerpo)
        return {"response": "nada\nno hay nada"}

    monkeypatch.setattr(dispatch, "_http_post_json", post_espia)
    srv._pensar_local("un prompt cualquiera")
    assert visto["options"]["num_ctx"] == 8192
    assert visto["options"]["temperature"] == 0
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python -m pytest test_plantel_server.py -q -k contexto_explicito`
Expected: FAIL con `KeyError: 'num_ctx'`

- [ ] **Step 3: Fijar el contexto**

En `_pensar_local`, el cuerpo del POST pasa a:

```python
        {"model": cfg["model"], "prompt": prompt, "stream": False,
         # `num_ctx` explicito y no el default de Ollama, por dos razones que
         # se descubrieron midiendo: Ollama trunca desde el COMIENZO del
         # prompt, y `decision.prompt` pone primero lo que mas importa (lo
         # aprendido, y ahora la carta del departamento). Con el default,
         # crecer el prompt hace que el jefe deje de ver justo lo que se le
         # agrego, en silencio: sin error y sin aviso.
         # 8192 y no mas: `qwen2.5:7b` soporta bastante mas, pero cada token
         # de contexto cuesta RAM en la maquina de Pedro y el prompt entero
         # de un tic hoy no llega ni cerca. Es holgura, no capacidad.
         "options": {"temperature": 0, "num_ctx": 8192}})
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_server.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/server.py test_plantel_server.py
git commit -m "fix(server): el modelo local recibe un num_ctx explicito"
```

---

### Task 2: La carta, leida sin crear nada

**Files:**
- Modify: `calipso/memory.py`
- Test: `test_memoria_carta.py` (**nuevo**, en la raiz)

**Interfaces:**
- Consumes: nada.
- Produces, y lo usa la Tarea 5:
  - `memory.ruta_carta(nombre: str) -> pathlib.Path`
  - `memory.leer_carta(nombre: str) -> dict` con exactamente
    `{"estado": "ausente" | "vacia" | "escrita", "texto": str}`

**Por que un archivo de test nuevo:** `test_memory.py` **no tiene un solo
`def test_`** -- es de los que corren por `main()` y pytest no colecta nada de
el. Un test puesto ahi no corre nunca.

- [ ] **Step 1: Escribir los tests que fallan**

Crear `test_memoria_carta.py`:

```python
#!/usr/bin/env python3
"""
test_memoria_carta.py — la carta de un departamento.

Archivo propio y no `test_memory.py`: ese corre por `main()` y pytest no
colecta nada de el, asi que un test ahi no correria nunca.
"""
import pathlib

import pytest

from calipso import memory


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Parchea la CONSTANTE, no el entorno.

    `memory.py` congela `CALIPSO_HOME` al importarse (es una constante de
    modulo, no una funcion), y el `conftest.py` de la raiz ya la fijo a un
    home desechable antes de que nada importara. Un `monkeypatch.setenv`
    aca no tendria ningun efecto: el valor ya esta leido.
    """
    monkeypatch.setattr(memory, "CALIPSO_HOME", tmp_path)
    return tmp_path


def test_la_ruta_es_pura_y_no_crea_nada(home):
    """Instanciar `Memory.departamento(...)` hace mkdir de dos directorios y
    abre un chroma. Leer una carta no puede tener ese efecto: seria crear un
    sqlite por departamento como consecuencia de pintar una pantalla."""
    antes = sorted(p.name for p in home.iterdir())
    r = memory.ruta_carta("taller")
    assert r.name == "carta.md"
    assert sorted(p.name for p in home.iterdir()) == antes


def test_sin_archivo_la_carta_esta_ausente(home):
    assert memory.leer_carta("taller") == {"estado": "ausente", "texto": ""}


def test_un_archivo_en_blanco_es_vacia_y_no_ausente(home):
    """`load_core` devuelve "" en los dos casos y por eso no sirve para esto.
    Ausente es "Pedro no escribio"; vacia es "Pedro escribio nada", que es
    una respuesta distinta y el jefe tiene que poder distinguirlas."""
    r = memory.ruta_carta("taller")
    r.parent.mkdir(parents=True, exist_ok=True)
    r.write_text("   \n\n  ", encoding="utf-8")
    assert memory.leer_carta("taller") == {"estado": "vacia", "texto": ""}


def test_una_carta_escrita_vuelve_con_su_texto(home):
    r = memory.ruta_carta("taller")
    r.parent.mkdir(parents=True, exist_ok=True)
    r.write_text("  I+D para los proyectos de Pedro.\n", encoding="utf-8")
    assert memory.leer_carta("taller") == {
        "estado": "escrita", "texto": "I+D para los proyectos de Pedro."}


def test_la_carta_vive_afuera_del_core(home):
    """El invariante de procedencia, verificado por RUTA y no construyendo
    una `Memory`.

    El core alimenta el bloque "Lo que aprendiste antes" del prompt, y una
    instruccion de Pedro no puede llegarle al modelo rotulada como una
    conclusion propia del jefe. `load_core` hace glob sobre `core/*.md`:
    alcanza con que la carta no este ahi abajo.

    Y se prueba asi a proposito: `Memory.__init__` carga un modelo de
    embeddings (`SentenceTransformerEmbeddingFunction`), asi que construir
    una para comprobar una ruta seria un test lento y fragil por un motivo
    ajeno a lo que prueba.
    """
    carta = memory.ruta_carta("taller")
    core = home / "memoria" / "departamento" / "taller" / "core"
    assert core not in carta.parents


def test_dos_departamentos_no_comparten_carta(home):
    for nombre in ("taller", "research"):
        r = memory.ruta_carta(nombre)
        r.parent.mkdir(parents=True, exist_ok=True)
        r.write_text(f"soy {nombre}", encoding="utf-8")
    assert memory.leer_carta("taller")["texto"] == "soy taller"
    assert memory.leer_carta("research")["texto"] == "soy research"


def test_una_carta_ilegible_no_revienta(home):
    """El disco puede tener cualquier cosa. Una carta que no se puede leer
    se trata como ausente: el jefe dice que no la tiene, que es verdad."""
    r = memory.ruta_carta("taller")
    r.parent.mkdir(parents=True, exist_ok=True)
    r.write_bytes(b"\xc3")
    assert memory.leer_carta("taller")["estado"] in ("ausente", "escrita")
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_memoria_carta.py -q`
Expected: FAIL con `AttributeError: module 'calipso.memory' has no attribute 'ruta_carta'`

- [ ] **Step 3: Las dos funciones**

En `calipso/memory.py`, junto a `Memory.departamento` (para que el layout viva
en un solo lugar), a nivel de modulo:

```python
def ruta_carta(nombre: str) -> pathlib.Path:
    """Donde vive la carta de un departamento: el texto que Pedro escribe
    diciendo para que existe, que mira y que no le toca.

    PURA: no crea directorios y no abre chroma. Es lo que la separa de
    `Memory.departamento(...)`, que construye un `Scope` y cuyo `__init__`
    hace mkdir de dos carpetas y abre un `PersistentClient`. Leer una carta
    -- o pintar una pantalla con N departamentos -- no puede crear N sqlite
    como efecto.

    AFUERA de `core/` a proposito. El core alimenta el bloque "Lo que
    aprendiste antes" del prompt del jefe: una carta ahi adentro le llegaria
    al modelo rotulada como una conclusion que el departamento saco solo, y
    es justo lo contrario -- es una instruccion de Pedro. Los dos canales
    quedan separados por construccion, sin exclusiones ni nombres
    reservados.
    """
    clave = _slug(pathlib.Path(nombre))
    return CALIPSO_HOME / "memoria" / "departamento" / clave / "carta.md"


def leer_carta(nombre: str) -> dict:
    """La carta y su estado, que son tres y no dos.

    `load_core` no sirve para esto porque devuelve "" tanto si no hay
    archivo como si lo hay vacio, y el prompt tiene que distinguir "Pedro no
    escribio" de "Pedro escribio nada": la segunda es una respuesta.

    Una carta ilegible se trata como ausente. Es el lado honesto: el jefe
    dice que no tiene carta, que es verdad, en vez de recibir bytes rotos.
    """
    try:
        crudo = ruta_carta(nombre).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return {"estado": "ausente", "texto": ""}
    texto = crudo.strip()
    if not texto:
        return {"estado": "vacia", "texto": ""}
    return {"estado": "escrita", "texto": texto}
```

**`CALIPSO_HOME` es la constante de modulo**, la misma que usa
`Memory.departamento` en su linea `base = CALIPSO_HOME / "memoria" / ...`. Se
lee como global adentro de la funcion, que es lo que hace que el
`monkeypatch.setattr(memory, "CALIPSO_HOME", ...)` del fixture funcione: la
busqueda del global pasa en cada llamada, no al definir.

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest test_memoria_carta.py test_memoria_ambito.py -q`
Expected: PASS

- [ ] **Step 5: Que tocar la carta dispare sus tests**

En `calipso/verification.py`, la rama del bibliotecario/memoria ya agrega
`test_memoria_ambito` con un comentario que explica por que hizo falta
(`test_memory.py` es de los de `main()`). El archivo nuevo tiene el mismo
problema y necesita la misma linea:

```python
            _add(plan, "test_memoria_carta",
                 f"{path} toca la carta que Pedro le escribe a un departamento")
```

Y su comando en el allowlist de `calipso/tools/commands.py`, con el molde de
`test_memoria_ambito` que ya esta ahi:

```python
    "test_memoria_carta": {
        "title": "Probar la carta del departamento",
        "description": "Ejecuta test_memoria_carta.py con pytest.",
        "args": ["{python}", "-m", "pytest", "-q", "test_memoria_carta.py"],
        "timeout": 120,
    },
```

- [ ] **Step 6: Commit**

```bash
git add calipso/memory.py test_memoria_carta.py calipso/verification.py calipso/tools/commands.py
git commit -m "feat(memoria): la carta de un departamento, leida sin crear nada"
```

---

### Task 3: Que proyectos le tocan a una cuenta

**Files:**
- Modify: `calipso/plantel/decision.py`
- Test: `test_plantel_decision.py`

**Interfaces:**
- Consumes: nada.
- Produces, y lo usa la Tarea 4:
  `decision.proyectos_de(proyectos: list[dict], cuenta: str) -> list[dict]`,
  donde cada dict de salida tiene exactamente
  `{"nombre": str, "texto": str, "fuente": "pedro" | "readme" | "ninguna"}`.

**El agujero que este filtro tiene que cerrar, y que dos jueces distintos
encontraron:** el jefe despierta con la cuenta **completa** (`dep:taller`), y
el catastro guarda `departamento`. Si uno guarda `taller` y el otro compara
`dep:taller`, **el resultado es la lista vacia y no falla nada**: la asignacion
se ve bien guardada en el disco y el prompt sale sin proyectos. El filtro
compara la cuenta completa, y hay un test que lo fija.

- [ ] **Step 1: Escribir los tests que fallan**

En `test_plantel_decision.py`. **Ese archivo no tiene helpers** -- verificado:
cada test arma sus dicts inline. Estos hacen lo mismo.

```python
def test_solo_los_proyectos_de_esa_cuenta():
    proyectos = [
        {"nombre": "lector", "departamento": "dep:taller", "linea": "el banco"},
        {"nombre": "atlas", "departamento": "dep:research", "linea": "feeds"},
        {"nombre": "suelto", "departamento": None, "linea": "x"},
    ]
    salida = dec.proyectos_de(proyectos, "dep:taller")
    assert [p["nombre"] for p in salida] == ["lector"]


def test_el_filtro_compara_la_cuenta_COMPLETA():
    """El jefe despierta como `dep:taller` y el catastro guarda lo que se le
    haya escrito. Si el filtro comparara el nombre desnudo contra la cuenta,
    o al reves, el resultado seria la lista vacia SIN QUE NADA FALLE: la
    asignacion se ve bien en el disco y el prompt sale sin proyectos."""
    assert dec.proyectos_de(
        [{"nombre": "lector", "departamento": "taller"}], "dep:taller") == []
    assert dec.proyectos_de(
        [{"nombre": "lector", "departamento": "dep:taller"}], "taller") == []


def test_la_linea_de_pedro_gana_al_readme():
    p = [{"nombre": "lector", "departamento": "dep:taller",
          "linea": "lo que escribio Pedro", "resumen": "lo del README"}]
    salida = dec.proyectos_de(p, "dep:taller")[0]
    assert salida["texto"] == "lo que escribio Pedro"
    assert salida["fuente"] == "pedro"


def test_sin_linea_cae_al_readme_y_lo_dice():
    p = [{"nombre": "lector", "departamento": "dep:taller",
          "linea": "", "resumen": "lo del README"}]
    salida = dec.proyectos_de(p, "dep:taller")[0]
    assert salida["texto"] == "lo del README"
    assert salida["fuente"] == "readme"


def test_sin_nada_lo_dice_en_vez_de_inventar():
    p = [{"nombre": "lector", "departamento": "dep:taller"}]
    salida = dec.proyectos_de(p, "dep:taller")[0]
    assert salida["texto"] == ""
    assert salida["fuente"] == "ninguna"


def test_una_linea_de_puros_espacios_no_es_una_linea():
    p = [{"nombre": "lector", "departamento": "dep:taller",
          "linea": "   ", "resumen": "lo del README"}]
    assert dec.proyectos_de(p, "dep:taller")[0]["fuente"] == "readme"


def test_sin_proyectos_devuelve_lista_vacia_y_no_revienta():
    assert dec.proyectos_de([], "dep:taller") == []
    assert dec.proyectos_de(None, "dep:taller") == []
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_plantel_decision.py -q -k proyectos_de or cuenta_COMPLETA`
Expected: FAIL con `AttributeError: module ... has no attribute 'proyectos_de'`

- [ ] **Step 3: El filtro**

En `calipso/plantel/decision.py`, arriba de `prompt`:

```python
def proyectos_de(proyectos, cuenta: str) -> list[dict]:
    """Los proyectos que le tocan a esta cuenta, con la procedencia de su
    texto dicha.

    Compara la CUENTA COMPLETA (`dep:taller`), no el nombre desnudo. Si los
    dos lados usaran formatos distintos, esto devolveria la lista vacia sin
    que nada fallara: la asignacion se veria bien guardada y el prompt
    saldria sin proyectos. Hay un test que fija las dos direcciones.

    La procedencia se devuelve como un valor -- `pedro`, `readme` o
    `ninguna` -- y no como texto ya formateado, para que el prompt decida
    como decirlo y para que no haya dos implementaciones de la misma frase.
    Un jefe que lee una linea de Pedro y una sacada de un README no puede
    tratarlas igual: la primera es una decision, la segunda es lo que un
    archivo dijo alguna vez.
    """
    salida = []
    for p in (proyectos or []):
        if p.get("departamento") != cuenta:
            continue
        linea = (p.get("linea") or "").strip()
        resumen = (p.get("resumen") or "").strip()
        if linea:
            texto, fuente = linea, "pedro"
        elif resumen:
            texto, fuente = resumen, "readme"
        else:
            texto, fuente = "", "ninguna"
        salida.append({"nombre": p.get("nombre", ""), "texto": texto,
                       "fuente": fuente})
    return salida
```

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_decision.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/plantel/decision.py test_plantel_decision.py
git commit -m "feat(plantel): que proyectos le tocan a una cuenta, con su procedencia"
```

---

### Task 4: Los dos bloques del prompt

**Files:**
- Modify: `calipso/plantel/decision.py` (la funcion `prompt`)
- Test: `test_plantel_decision.py`

**Interfaces:**
- Consumes: `decision.proyectos_de` de la Tarea 3; el dict de `leer_carta` de
  la Tarea 2 (por parametro, no por import).
- Produces, y lo usa la Tarea 5:
  `prompt(situacion, sesgo_pct, nucleo="", recientes=(), carta=None, proyectos=None)`
  -- los dos nuevos con default, para no romper las llamadas que ya existen en
  los tests del prompt.

**Restriccion dura, verificada, la misma que la gramatica:** dos tests afirman
por substring sobre el prompt entero que las palabras `trabajar` y `comentar`
no aparecen cuando el menu no las ofrece. **Ningun texto nuevo puede
contenerlas** -- ni la plantilla, ni un ejemplo, ni un encabezado.

- [ ] **Step 1: Escribir los tests que fallan**

En `test_plantel_decision.py`, con `_situacion_minima()` que ese archivo ya
tiene (agregado por el plan de la gramatica):

```python
def test_la_carta_sale_como_su_propio_bloque():
    p = dec.prompt(_situacion_minima(), 50,
                   carta={"estado": "escrita", "texto": "I+D para Pedro."})
    assert "Este departamento:" in p
    assert "I+D para Pedro." in p


def test_la_carta_NO_sale_bajo_lo_que_aprendiste_antes():
    """El invariante de procedencia. Si la carta viajara por el nucleo, el
    prompt le diria al modelo que una instruccion de Pedro es algo que el
    departamento concluyo solo."""
    p = dec.prompt(_situacion_minima(), 50, nucleo="lo que aprendi solo",
                   carta={"estado": "escrita", "texto": "LA CARTA"})
    cabeza = p.split("Lo que aprendiste antes:")[1].split("\n\n")[0]
    assert "LA CARTA" not in cabeza


def test_sin_carta_el_bloque_lo_dice_en_vez_de_desaparecer():
    """Hoy el bloque del nucleo se esfuma cuando esta vacio, asi que "nadie
    escribio" y "escribio nada" se leen igual y el jefe no puede notar que le
    falta algo."""
    p = dec.prompt(_situacion_minima(), 50,
                   carta={"estado": "ausente", "texto": ""})
    assert "Este departamento:" in p
    assert "no tiene carta" in p


def test_una_carta_vacia_no_se_lee_igual_que_una_ausente():
    ausente = dec.prompt(_situacion_minima(), 50,
                         carta={"estado": "ausente", "texto": ""})
    vacia = dec.prompt(_situacion_minima(), 50,
                       carta={"estado": "vacia", "texto": ""})
    assert ausente != vacia


def test_los_proyectos_salen_con_su_procedencia():
    p = dec.prompt(_situacion_minima(), 50, proyectos=[
        {"nombre": "lector", "texto": "el banco", "fuente": "pedro"},
        {"nombre": "atlas", "texto": "feeds", "fuente": "readme"}])
    assert "Proyectos a tu cargo:" in p
    assert "lector" in p and "el banco" in p
    assert "(de Pedro)" in p and "(del README)" in p


def test_sin_proyectos_el_bloque_lo_dice():
    p = dec.prompt(_situacion_minima(), 50, proyectos=[])
    assert "Proyectos a tu cargo:" in p
    assert "ninguno asignado" in p


def test_un_proyecto_sin_texto_lo_dice_y_no_miente():
    p = dec.prompt(_situacion_minima(), 50, proyectos=[
        {"nombre": "suelto", "texto": "", "fuente": "ninguna"}])
    assert "suelto" in p


def test_los_bloques_nuevos_no_traen_las_palabras_prohibidas():
    """Dos tests que ya existen afirman que `trabajar` y `comentar` no
    aparecen cuando el menu no las ofrece. Cualquier texto nuevo que las
    contenga los rompe aunque el menu este perfecto."""
    p = dec.prompt(_situacion_minima(), 50,
                   carta={"estado": "ausente", "texto": ""}, proyectos=[])
    assert "trabajar" not in p and "comentar" not in p


def test_sin_los_parametros_nuevos_el_prompt_sigue_saliendo():
    """Los doce tests viejos del prompt llaman sin carta y sin proyectos.
    Los defaults tienen que dejarlos pasar."""
    assert dec.prompt(_situacion_minima(), 50)
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_plantel_decision.py -q -k "carta or proyectos_salen or bloque"`
Expected: FAIL con `TypeError: prompt() got an unexpected keyword argument 'carta'`

- [ ] **Step 3: Los dos bloques**

En `calipso/plantel/decision.py`, la firma:

```python
def prompt(situacion: dict, sesgo_pct: int, nucleo: str = "",
          recientes: "list[str] | tuple" = (), carta: dict | None = None,
          proyectos: "list[dict] | None" = None) -> str:
```

Y arriba del `return`, junto a `aprendido` y `ultimas`:

```python
    # La carta de Pedro, en SU PROPIO bloque y no adentro de `aprendido`.
    # El bloque de arriba se titula "Lo que aprendiste antes": una
    # instruccion de Pedro ahi adentro le llegaria al modelo rotulada como
    # una conclusion que el departamento saco solo, que es lo contrario de
    # lo que es.
    #
    # Y habla cuando esta vacia, con tres estados y no dos. Hoy el bloque
    # del nucleo desaparece entero si no hay texto, asi que "nadie escribio"
    # y "escribio nada" se leen igual y el jefe no puede notar que le falta
    # algo.
    c = carta or {"estado": "ausente", "texto": ""}
    if c["estado"] == "escrita":
        bloque_carta = f"Este departamento:\n{c['texto']}\n\n"
    elif c["estado"] == "vacia":
        bloque_carta = ("Este departamento: Pedro empezo su carta y la dejo "
                        "en blanco.\n\n")
    else:
        bloque_carta = ("Este departamento: todavia no tiene carta. Pedro no "
                        "escribio para que existe, asi que no sabes que te "
                        "toca ni que no.\n\n")

    # Los proyectos, con la procedencia DICHA: una linea de Pedro es una
    # decision; una sacada de un README es lo que un archivo dijo alguna vez.
    _COMO = {"pedro": "(de Pedro)", "readme": "(del README)",
             "ninguna": "(sin descripcion)"}
    ps = proyectos or []
    if ps:
        filas = "\n".join(
            # sin `texto` no se deja un doble espacio ni dos puntos huerfanos:
            # "  - suelto (sin descripcion)" se lee; "  - suelto:  (...)" no.
            (f"  - {p['nombre']}: {p['texto']} {_COMO[p['fuente']]}"
             if p["texto"] else f"  - {p['nombre']} {_COMO[p['fuente']]}")
            for p in ps)
        bloque_proyectos = f"Proyectos a tu cargo:\n{filas}\n\n"
    else:
        bloque_proyectos = "Proyectos a tu cargo: ninguno asignado.\n\n"
```

Y los dos entran al `return` **antes** de `aprendido`:

```python
    return (
        bloque_carta +
        bloque_proyectos +
        aprendido +
        ultimas +
        catalogo +
        f"Sos el jefe del departamento {s['nombre']} ...
```

**Por que arriba, sabiendo que arriba es lo que se trunca primero:** porque es
lo correcto en significado -- lo que el departamento ES viene antes de cuanta
plata tiene -- y porque la Tarea 1 ya fijo un `num_ctx` con holgura. La Tarea 6
mide si sobrevive. Si no sobrevive, el orden se cambia con el dato en la mano.

- [ ] **Step 4: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_decision.py -q`
Expected: PASS, incluidos los doce tests viejos del prompt.

- [ ] **Step 5: Commit**

```bash
git add calipso/plantel/decision.py test_plantel_decision.py
git commit -m "feat(plantel): el prompt dice que es el departamento y que proyectos le tocan"
```

---

### Task 5: El cableado

**Files:**
- Modify: `calipso/plantel/jefe.py` (el `Contexto` y la llamada a `prompt`)
- Modify: `calipso/server.py` (donde se construye el `Contexto`, cerca de la 2784)
- Test: `test_plantel_jefe.py`, `test_plantel_server.py`

**Interfaces:**
- Consumes: `memory.leer_carta` (Tarea 2), `decision.proyectos_de` (Tarea 3),
  `decision.prompt(..., carta=, proyectos=)` (Tarea 4).
- Produces: nada.

**Todo se inyecta.** Ni `jefe.py` ni `decision.py` ganan un import nuevo:
`server.py` lee la carta y el catastro y los pone en el `Contexto`, igual que
ya hace con la memoria y el bus. Es el patron del modulo, y es lo que permite
que los tests inyecten una carta sin tocar disco.

- [ ] **Step 1: Escribir los tests que fallan**

En `test_plantel_jefe.py`, y `armar()` gana dos parametros opcionales:

```python
def armar(tmp_path, respuesta="nada\nno hay nada", saldo=400_000,
         presupuesto_semanal_mm=25_000, techo_preseed_mm=0,
         techo_preseed_ciclo_mm=10_000_000, carta=None, proyectos=None):
```

y en el `j.Contexto(...)`:

```python
        carta=carta or {"estado": "ausente", "texto": ""},
        proyectos=proyectos or [],
```

Los tests nuevos:

```python
def test_la_carta_del_contexto_llega_al_prompt(tmp_path):
    visto = {}
    ctx, _, _ = armar(tmp_path, carta={"estado": "escrita",
                                       "texto": "SOY EL TALLER"})
    ctx.pensar = lambda p: visto.setdefault("p", p) or "nada\nx"
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    assert "SOY EL TALLER" in visto["p"]


def test_los_proyectos_del_contexto_llegan_filtrados_por_cuenta(tmp_path):
    """El jefe de `dep:atlas` no puede ver los proyectos de otro."""
    visto = {}
    ctx, _, _ = armar(tmp_path, proyectos=[
        {"nombre": "mio", "departamento": "dep:atlas", "linea": "el mio"},
        {"nombre": "ajeno", "departamento": "dep:taller", "linea": "el ajeno"}])
    ctx.pensar = lambda p: visto.setdefault("p", p) or "nada\nx"
    it.poner_modo(tmp_path, "vivo")
    j.tic(ctx, "dep:atlas", W)
    assert "el mio" in visto["p"] and "el ajeno" not in visto["p"]


def test_sin_carta_ni_proyectos_el_tic_sigue_andando(tmp_path):
    """Los 44 tests viejos construyen el Contexto sin los campos nuevos."""
    ctx, contratos, _ = armar(tmp_path, "nada\ntodo tranquilo")
    it.poner_modo(tmp_path, "vivo")
    out = j.tic(ctx, "dep:atlas", W)
    assert out["accion"] == "nada" and contratos == []
```

Y en `test_plantel_server.py`, uno que fije que **produccion** inyecta las dos
cosas -- no alcanza con que el arnes las acepte:

```python
def test_produccion_le_inyecta_la_carta_y_los_proyectos_al_jefe(
        tmp_path, monkeypatch):
    """El arnes de test_plantel_jefe.py construye el Contexto a mano, asi
    que puede pasar aunque produccion nunca las mande. Este es el guarda
    apuntado al unico lugar que importa."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setattr(memory, "CALIPSO_HOME", tmp_path)
    carta = memory.ruta_carta("atlas")
    carta.parent.mkdir(parents=True, exist_ok=True)
    carta.write_text("SOY ATLAS", encoding="utf-8")

    visto = {}
    monkeypatch.setattr(srv._plantel_jefe, "tic",
                        lambda ctx, cuenta, semana: visto.update(ctx=ctx))
    # disparar la rutina de departamento por el mismo camino que la corre el
    # ticker; mira como lo hace el test vecino que ya la ejercita.
    ...
    assert visto["ctx"].carta["texto"] == "SOY ATLAS"
    assert isinstance(visto["ctx"].proyectos, list)
```

Los puntos suspensivos son deliberados: **el disparo de la rutina sale del
test vecino que ya la ejercita en ese archivo**, y copiarlo mal es peor que
leerlo. Lo que este test fija son las dos ultimas assertions.

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_plantel_jefe.py -q -k "carta_del_contexto or proyectos_del_contexto"`
Expected: FAIL con `TypeError: Contexto.__init__() got an unexpected keyword argument 'carta'`

- [ ] **Step 3: El `Contexto` gana dos campos**

En `calipso/plantel/jefe.py`, despues de `publicar` (que ya tiene default, asi
que los nuevos tambien tienen que tenerlo o el dataclass no compila):

```python
    # Lo que el departamento ES, y que proyectos le tocan. Se INYECTAN, no se
    # leen: `jefe.py` no importa `memory` ni `catastro`, igual que no importa
    # el kernel ni el bus. Es lo que deja que los tests pongan una carta sin
    # tocar disco, y lo que evita que leer una carta cree directorios.
    carta: dict = field(default_factory=lambda: {"estado": "ausente",
                                                 "texto": ""})
    proyectos: list = field(default_factory=list)
```

- [ ] **Step 4: `tic` los pasa**

La llamada a `dec.prompt` pasa a:

```python
        p = dec.prompt(s, sesgo, ctx.memoria.load_core(),
                       ctx.memoria.recent(limit=5),
                       carta=ctx.carta,
                       proyectos=dec.proyectos_de(ctx.proyectos, cuenta))
```

- [ ] **Step 5: `server.py` los construye**

Donde se arma el `Contexto` del jefe, las dos lineas nuevas. La carta sale de
`mem` -- el modulo, no una instancia de `Scope` -- y los proyectos del
catastro, que ya se lee en otros lugares del server:

```python
            carta=leer_carta(cuenta.split(":", 1)[1]),
            proyectos=catastro.cargar(),
```

Los dos nombres estan verificados. `catastro` ya se importa asi en
`server.py:62` (`from calipso import catastro`). `leer_carta` **hay que
agregarlo** a la linea que ya existe en `server.py:90`:

```python
from calipso.memory import Memory, leer_carta  # noqa: E402
```

Y ojo con el corte del prefijo: `leer_carta` recibe el nombre **sin** `dep:`,
igual que `mem.departamento(...)` dos lineas mas arriba, porque el slug del
directorio no lleva prefijo. Pero `proyectos_de` compara la cuenta **con**
prefijo. Los dos cortes son correctos y distintos: uno es una ruta de disco, el
otro es una cuenta contable.

- [ ] **Step 6: Correr los tests**

Run: `.venv/bin/python -m pytest test_plantel_jefe.py test_plantel_server.py test_plantel_decision.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add calipso/plantel/jefe.py calipso/server.py test_plantel_jefe.py test_plantel_server.py
git commit -m "feat(plantel): la carta y los proyectos llegan al jefe por el contexto"
```

---

### Task 6: El experimento

**Files:**
- Create: `experimentos/carta_vs_sin_carta.py`
- Test: ninguno. **Es un script de una corrida, no una suite.**

**Interfaces:**
- Consumes: `decision.prompt` (Tarea 4), `decision.proyectos_de` (Tarea 3), y
  el `num_ctx` de la Tarea 1.
- Produces: **la decision de si la Fase 2 se escribe.**

**Que es y que no es.** No es un criterio de aceptacion del codigo: su
resultado no dice si esto esta bien implementado, dice si vale la pena
construir la pantalla. Un resultado negativo es un resultado util y barato. No
corre en CI, no bloquea nada, y se lee una vez.

**No importa `calipso` fuera de pytest sin proteccion.** El script tiene que
exportar `CALIPSO_HOME` a un temporal antes de importar nada del paquete, y
decirlo en su docstring. Verifica como lo hace `conftest.py` en la raiz y copia
ese camino.

- [ ] **Step 1: Escribir el script**

```python
#!/usr/bin/env python3
"""
experimentos/carta_vs_sin_carta.py — la medicion que decide la Fase 2.

La hipotesis de todo este trabajo: un jefe con contexto propone mejor que uno
sin contexto. Es razonable y no esta probada, y probarla es barato -- el
modelo local es un POST a Ollama que no gasta cuota ni plata.

Este script arma situaciones sinteticas, renderiza el prompt CON y SIN los dos
bloques nuevos, se los manda al mismo modelo y muestra las dos decisiones al
lado. No decide nada solo: lo lee Pedro.

CALIPSO_HOME va a un temporal ANTES de importar el paquete: importar calipso
suelto escribe en el home real.
"""
```

El cuerpo, completo salvo las situaciones:

```python
import os
import pathlib
import tempfile

# ANTES de importar calipso: el paquete escribe en el home real.
os.environ["CALIPSO_HOME"] = tempfile.mkdtemp(prefix="carta-exp-")

import dispatch                                          # noqa: E402
from calipso.plantel import decision as dec              # noqa: E402
from calipso.plantel import ficha                        # noqa: E402

CARTA = {"estado": "escrita", "texto":
         "El taller hace I+D para los proyectos de Pedro. Mira prototipos, "
         "bancos de prueba y hardware. No le toca mejorar a Calipso mismo."}

PROYECTOS = [{"nombre": "calipso-lector",
              "texto": "convertir el Musnap en la pantalla de Calipso; el "
                       "plugin arranca y falta el banco de pruebas",
              "fuente": "pedro"}]

SIN_CARTA = {"estado": "ausente", "texto": ""}


def situaciones() -> list[tuple[str, dict]]:
    """Media docena de fotos distintas del mismo departamento.

    Se arman a mano y no salen del disco: el experimento no necesita
    economia sembrada, y asi cada corrida compara exactamente lo mismo.
    """
    ...   # ver abajo


def pensar(prompt: str) -> str:
    """El mismo camino que `_pensar_local`, con el mismo `num_ctx`."""
    cfg = dispatch.CONFIG["local"]
    data = dispatch._http_post_json(
        cfg["base_url"],
        {"model": cfg["model"], "prompt": prompt, "stream": False,
         "options": {"temperature": 0, "num_ctx": 8192}})
    return (data or {}).get("response", "")


def decidir(p: str) -> str:
    """De la respuesta cruda a una linea legible: la accion, y la ficha si
    parseo."""
    accion, _ref, _motivo = dec.parsear(p)
    if accion != "proponer":
        return accion
    f = ficha.parsear_ficha(p)
    if f is None:
        return "proponer (ficha ilegible)"
    return f"proponer -> {f['promete']}: {f['sobre']} ({f['tarda']})"


def main() -> int:
    try:
        pensar("hola")
    except Exception as exc:
        print(f"No hay modelo local disponible: {exc}")
        print("Levanta Ollama con qwen2.5:7b y volve a correr.")
        return 1

    for nombre, s in situaciones():
        con = dec.prompt(s, 50, carta=CARTA, proyectos=PROYECTOS)
        sin = dec.prompt(s, 50, carta=SIN_CARTA, proyectos=[])
        print(f"\n=== {nombre}")
        print(f"    prompt con carta: {len(con):5d} chars | "
              f"sin carta: {len(sin):5d} chars")
        print(f"    la carta esta en el prompt: {CARTA['texto'][:20] in con}")
        print(f"    CON carta -> {decidir(pensar(con))}")
        print(f"    SIN carta -> {decidir(pensar(sin))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

**Las situaciones son lo unico que queda por escribir**, y salen de copiar
`_situacion_minima()` de `test_plantel_decision.py` seis veces, variando lo que
puede cambiar la decision: sin nada; con un trabajo vivo; con dos propuestas
propias en pie; con una descartada de esta semana; con la bandeja llena
(tres propuestas); y una con el catalogo poblado. Cada una es una tupla
`(nombre_legible, dict)`.

**Por que `dispatch._http_post_json` y no un `requests` propio:** es el mismo
camino que usa produccion, asi que si la config del modelo cambia, el
experimento cambia con ella en vez de medir otra cosa.

- [ ] **Step 2: Correrlo**

```bash
.venv/bin/python experimentos/carta_vs_sin_carta.py
```

Requiere Ollama corriendo con `qwen2.5:7b`. Si no esta, el script tiene que
decirlo y salir, no reventar con un error de conexion crudo.

- [ ] **Step 3: Leer las tres cosas que se miden**

En orden de importancia:

1. **Si la ficha cambia.** Con carta, el jefe propone sobre lo que la carta
   nombra? Sin carta, propone generico? **Es la hipotesis entera.**
2. **Si la ficha sigue parseando.** Los bloques nuevos empujan las
   instrucciones de formato mas lejos del final. La gramatica recien fusionada
   depende de que el modelo las obedezca: si la carta la rompe, la carta cuesta
   mas de lo que da.
3. **Si la carta llega.** El prompt entero entra en `num_ctx`, o se corta algo.

- [ ] **Step 4: Commit**

```bash
git add experimentos/carta_vs_sin_carta.py
git commit -m "feat(experimentos): medir si la carta cambia lo que el jefe decide"
```

- [ ] **Step 5: Anotar el resultado en el spec**

El resultado va al spec como una seccion nueva, con el numero de situaciones,
que cambio y que no. **Ese texto es lo que decide si se escribe la Fase 2**, y
tiene que quedar escrito aunque el resultado sea negativo -- sobre todo si es
negativo.

---

## Lo que esta Fase NO hace

- **La pantalla, los endpoints y la reforma del catastro.** Son la Fase 2 y no
  se escriben hasta que la Tarea 6 conteste. Su costo real esta documentado en
  la seccion 8 del spec: separar la tabla que la maquina reconstruye de la que
  escribe Pedro, un candado para `catastro.json`, y que el escaneo se niegue a
  escribir sobre una lectura rota.
- **Declarar un proyecto sin `.git`.** Es de la Fase 2. Mientras tanto,
  `calipso-lector` sigue invisible para el catastro y no se le puede asignar
  departamento.
- **Escribir la carta desde ningun lado.** En esta fase Pedro la escribe con su
  editor. La pantalla es la Fase 2.
- **Limpiar las fuentes rotas** -- el mojibake, la cronologia, las metas de
  prueba. Es su propio spec y no es prerequisito de esto.
- **Que alguien lea la carta de verdad.** Hace falta sembrar, crear y habilitar
  una rutina de tipo `departamento` por cada uno (hoy hay **cero**), y el
  interruptor en vivo. El experimento no depende de nada de eso: corre contra
  situaciones sinteticas.
