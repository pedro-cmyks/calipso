# El inbox, parte 1: la cinta

> **Para agentes:** SUB-SKILL REQUERIDA: usar `superpowers:subagent-driven-development`
> (recomendado) o `superpowers:executing-plans` para ejecutar tarea por tarea.
> Los pasos usan checkbox (`- [ ]`).

**Goal:** Que las cuatro bandejas que ya existen -la mesa, permisos, el
bibliotecario y las cartas del cierre- se vean en una sola lista, cada una
conservando sus verbos exactos, con un badge que cuente decisiones y no mienta.

**Architecture:** Cada origen expone un **descriptor** y un **adaptador** al lado
de su propio modulo; un endpoint agregador los junta bajo el candado del libro;
y un modulo puro del cliente dibuja la lista. El inbox no sabe nada de ninguna
bandeja: pide descriptores y obedece. El aprendiz (reglas, `no_siempre`) y el
PvP van en un plan aparte -- esto es solo leer y mostrar.

**Tech Stack:** Python 3.14 + FastAPI + pytest en el servidor. Modulos ES sueltos
servidos desde `/static/fabrica`, sin bundler, con `node --test` en el cliente.

**Spec:** `docs/superpowers/specs/2026-08-31-inbox-design.md` (commit `3d7bb36`)

---

## Correcciones al spec que este plan incorpora

Salieron de extraer las formas reales. **Las cinco estan verificadas** y el spec
habra que corregirlo despues; el plan ya las asume.

1. **El ruteo por prefijo del id NO funciona.** El spec (seccion 3) dice que los
   ids son opacos con prefijo propio y que la lista mezclada "rutea la accion por
   el prefijo, sin tabla de traduccion ni campo extra". **Falso para las cartas:**
   `_id_carta` devuelve `f"{tipo}:{quien}:{semana}"` (`operacion.py:83-85`), o sea
   `"mandato:dep:a:2026-W35"`. El item unificado lleva `origen` como campo.
2. **`/api/economia/cola` no es "la bandeja de cartas".** Su lista `pendientes`
   mezcla cartas (`es_carta: true`, 7 campos, todo adentro de `carta`) con
   compuertas (`es_carta` ausente, 12 campos planos). Hay que filtrar por
   `es_carta`, o el inbox ofrece "atender" sobre una compuerta y eso da 500.
3. **Hay TRES claves distintas de "esta bandeja existe":** `activa` en economia
   (bus y cola), `activo` en permisos, y **ninguna** en memoria. Confundirlas deja
   el contador en cero en silencio.
4. **Sin economia sembrada -- el estado de hoy -- `bus` y `cola` devuelven
   literalmente `{"activa": false}` y nada mas.** No hay `propuestas: []`. Todo
   acceso va con `(datos.propuestas || [])`.
5. **`vencidas` tiene cinco campos, no diez** (id, departamento, titulo, semana,
   presupuesto_mm) y su unico verbo valido es descartar: financiar da 400.

### Y una correccion de diseño, que es la unica que necesita el visto de Pedro

El spec (seccion 8) dice **"pestaña global, no cuarta sub-pestaña de la mesa"**, y
el argumento era que meterlo adentro daria tres niveles de pestañas anidados. Ese
argumento se apoyaba en un hecho incompleto: **en escritorio no hay pestañas.**
La grilla es de cuatro columnas fijas (`grid-template-areas: "chats centro mapa
mesa"`, `estilo.css:23-25`) y `#pestanas { display: none }` (`estilo.css:162`).
Las pestañas existen solo en telefono, y son tres.

O sea que una "pestaña global" nueva no tiene columna en escritorio, y agregarla
obliga a cuatro cambios de CSS no obvios (la grilla de `#pestanas`, doce
selectores de ocultamiento en vez de seis, el markup, y el `for` de `app.js:217`).

**Lo que hace este plan:** el panel que hoy se llama **Mesa** pasa a ser el
**Inbox**, y su primera sub-vista es **Todo** -- la lista unificada. Las
sub-vistas que ya estan (Decidir, Plata, Permisos) no se tocan. Con eso: ninguna
columna nueva, ningun cambio de grilla, ningun nivel de anidamiento nuevo, y en
telefono sigue habiendo tres pestañas. **La mesa no queda "adentro del inbox" como
subordinada: es uno de los cuatro origenes, que es exactamente lo que el spec
dice que es.**

Si Pedro prefiere la cuarta columna, se cambia la Tarea 7 y nada mas: las tareas
1 a 6 son de servidor y de modulo puro, y no dependen del layout.

---

## Global Constraints

- **Cero emojis.** En codigo, en UI y en cualquier texto. Texto plano o simbolos
  tipograficos.
- **Nombres, comentarios y documentacion en español.** Mensajes de commit **sin
  tildes ni eñe**.
- **Nunca importar calipso fuera de pytest.** `conftest.py` pisa `CALIPSO_HOME`
  con un tmpdir antes de recolectar; un `python -c "import calipso.server"` suelto
  escribe en el `~/.calipso` real de Pedro.
- **Un test que toque permisos y biblioteca a la vez necesita las dos cosas:**
  `monkeypatch.setattr(srv, "_ECO_BASE", home)` **y**
  `monkeypatch.setenv("CALIPSO_HOME", str(home))`. `permisos/almacen.py` resuelve
  el home en cada llamada; `librarian.py` y `memory.py` lo congelan al importar.
- **Suite de python:** `.venv/bin/python -m pytest -q --ignore=test_chat_live.py`
  desde `/var/home/pedro/calipso`. Hoy: **816 verdes**.
- **Suite de cliente:** `node --test` con
  `~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node`, **con
  `calipso/web/fabrica/` como cwd** -- nunca como argumento posicional.
  Hoy: **352 verdes**.
- **Todo lo que entra por `innerHTML` se escapa.** Los titulos los escribe un
  modelo. El molde es `escapar()` en `mesa.js:5-7` y `permisos.js:11-14`.
- **Un archivo nuevo del cliente va agregado a `SHELL` en `calipso/web/sw.js`** o
  la PWA no lo cachea. No hay test que lo detecte.

---

## File Structure

**Se crean:**

| Archivo | Responsabilidad |
|---|---|
| `calipso/inbox.py` | El agregador: junta los cuatro adaptadores en una lista de items. No sabe de HTTP ni de ninguna bandeja en particular. |
| `calipso/web/fabrica/inbox.js` | Modulo puro: de la respuesta del endpoint al HTML. Sin fetch, sin DOM. |
| `test_inbox.py` | Los adaptadores y el agregador. |
| `test_inbox_server.py` | El endpoint, con las cuatro bandejas montadas a mano. |
| `calipso/web/fabrica/inbox.test.js` | El modulo puro del cliente. |

**Se modifican:**

| Archivo | Cambio |
|---|---|
| `calipso/economia/bus.py` | Descriptor + adaptador de la mesa. |
| `calipso/permisos/motor.py` | Descriptor + adaptador de permisos. |
| `calipso/librarian.py` | Descriptor + adaptador del bibliotecario. |
| `calipso/economia/cola.py` | Descriptor + adaptador de las cartas. |
| `calipso/server.py` | El endpoint `GET /api/inbox`. |
| `calipso/web/fabrica/app.js` | Cableado: fetch, pintado, listeners, intervalo. |
| `calipso/web/fabrica/index.html` | La sub-vista "Todo" y su boton. |
| `calipso/web/fabrica/sw.js` | `inbox.js` a `SHELL`. |
| `calipso/verification.py`, `calipso/tools/commands.py` | Enganchar los tests nuevos. |

**Por que el descriptor y el adaptador van al lado de cada origen y no en
`inbox.py`:** es la decision de la seccion 3 del spec. Si vivieran en el inbox,
agregar el correo mañana obligaria a tocar el inbox -- o sea recentralizar lo que
el spec acaba de repartir. `inbox.py` solo los llama.

---

## El item unificado

La forma que producen los cuatro adaptadores, y que el cliente consume:

```python
{
    "id": str,          # opaco, del origen. Puede tener ":" (cartas).
    "origen": str,      # "mesa" | "permisos" | "biblioteca" | "cartas"
    "clase": str,       # "decision" | "aviso"
    "ts": str,          # ISO. "" si el origen no lo tiene.
    "titulo": str,      # una linea, ya legible. Lo escapa el cliente.
    "cuerpo": dict,     # opaco, tipado por origen. El inbox no lo interpreta.
    "estado": str,      # del origen, sin traducir
    "respuesta": dict | None,
}
```

Y el descriptor de cada origen:

```python
{
    "origen": str,
    "verbos": [{"nombre": str, "etiqueta": str, "alcances": [str],
                "parametros": [str]}],
    "reloj": str | None,        # None = no vence. Dos de cuatro no vencen.
    "clase_por_defecto": str,
    "vara": str | None,         # None en este plan: el PvP es el plan 2
    "lugares": int | None,      # None = sin limite. Ver plan 2.
}
```

---

### Task 1: El descriptor y el adaptador de la mesa

**Files:**
- Modify: `calipso/economia/bus.py` (agregar al final del modulo)
- Test: `test_inbox.py` (crear)

**Interfaces:**
- Produces: `bus.descriptor() -> dict`, `bus.como_items(datos_endpoint: dict) -> list[dict]`

Ojo con dos cosas verificadas: `datos_endpoint` es lo que devuelve
`GET /api/economia/bus`, que sin economia sembrada es **literalmente
`{"activa": false}`**; y `vencidas` tiene **cinco** campos, no los diez de
`propuestas`.

- [ ] **Step 1: Escribir el test que falla**

```python
# test_inbox.py
"""Los adaptadores que convierten cada bandeja en items del inbox.

El inbox no sabe nada de ninguna bandeja: cada origen se traduce a si mismo.
Estos tests son el contrato de esa traduccion.
"""
from calipso.economia import bus as eco_bus


def test_la_mesa_se_declara_sin_vara_todavia():
    """El PvP es el plan 2. Hoy el descriptor lo dice explicitamente en vez
    de inventar una vara que no tiene con que comparar: `retorno_mm` es una
    copia de `presupuesto_mm` para los dos tipos de propuesta."""
    d = eco_bus.descriptor()
    assert d["origen"] == "mesa"
    assert d["vara"] is None
    assert {v["nombre"] for v in d["verbos"]} == {"financiar", "descartar"}


def test_financiar_declara_que_lleva_parametro():
    """Financiar no es un si: es un si-con-cuenta-pagadora. El inbox tiene
    que saberlo para no dibujar un boton que miente."""
    d = eco_bus.descriptor()
    financiar = next(v for v in d["verbos"] if v["nombre"] == "financiar")
    assert "cuenta" in financiar["parametros"]


def test_sin_economia_sembrada_no_hay_items_y_no_revienta():
    """El estado de HOY: el endpoint devuelve {"activa": false} y NADA mas.
    Ni `propuestas` ni `vencidas`."""
    assert eco_bus.como_items({"activa": False}) == []


def test_una_propuesta_se_vuelve_un_item():
    datos = {"activa": True, "propuestas": [
        {"id": "a-1a2b3c4d", "estado": "alta", "departamento": "dep:a",
         "tipo": "trabajo", "titulo": "escribir el landing",
         "presupuesto_mm": 50000, "retorno_mm": 50000,
         "criterio": {"gasto_max_mm": 50000}, "gastado_mm": 0, "aportes": {}}],
        "vencidas": []}
    items = eco_bus.como_items(datos)
    assert len(items) == 1
    it = items[0]
    assert it["id"] == "a-1a2b3c4d"
    assert it["origen"] == "mesa"
    assert it["clase"] == "decision"
    assert it["titulo"] == "escribir el landing"
    assert it["cuerpo"]["presupuesto_mm"] == 50000
    assert it["estado"] == "alta"


def test_una_vencida_tambien_es_item_pero_solo_admite_descartar():
    """Cinco campos, no diez. Un render unico para las dos leeria undefined."""
    datos = {"activa": True, "propuestas": [], "vencidas": [
        {"id": "a-9f9f9f9f", "departamento": "dep:a", "titulo": "ronda",
         "semana": "2026-W35", "presupuesto_mm": 100000}]}
    items = eco_bus.como_items(datos)
    assert len(items) == 1
    assert items[0]["estado"] == "vencida"
    assert items[0]["cuerpo"]["verbos_validos"] == ["descartar"]


def test_un_preseed_paga_el_tesoro_y_no_ofrece_eleccion():
    """`bus.financiar` rechaza cualquier billetera que no sea el tesoro para
    un pre-seed. Un selector ahi seria un menu donde todo falla."""
    datos = {"activa": True, "vencidas": [], "propuestas": [
        {"id": "a-1", "estado": "alta", "departamento": "dep:a",
         "tipo": "preseed", "titulo": "ronda", "presupuesto_mm": 100000,
         "retorno_mm": 100000, "criterio": {}, "gastado_mm": 0,
         "aportes": {}}]}
    assert eco_bus.como_items(datos)[0]["cuerpo"]["cuenta_fija"] == "tesoro"
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `.venv/bin/python -m pytest -q test_inbox.py`
Expected: FAIL con `AttributeError: module 'calipso.economia.bus' has no attribute 'descriptor'`

- [ ] **Step 3: Implementar lo minimo**

```python
# al final de calipso/economia/bus.py

ORIGEN_INBOX = "mesa"


def descriptor() -> dict:
    """Lo que la mesa declara de si misma para el inbox.

    Vive aca y no en el inbox a proposito (spec seccion 3): si viviera
    alla, agregar un origen nuevo obligaria a tocar el inbox.

    `vara` y `lugares` van en None porque el PvP es otro plan, y porque
    hoy la mesa no tendria con que comparar: `retorno_mm` es una copia
    literal de `presupuesto_mm` para los dos tipos de propuesta.
    """
    return {
        "origen": ORIGEN_INBOX,
        "verbos": [
            # financiar NO es un si: es un si-con-cuenta-pagadora
            {"nombre": "financiar", "etiqueta": "Financiar",
             "alcances": ["una_vez"], "parametros": ["cuenta"]},
            {"nombre": "descartar", "etiqueta": "Descartar",
             "alcances": ["una_vez"], "parametros": []},
        ],
        "reloj": "semanas_operativas",   # solo vencen los pre-seed
        "clase_por_defecto": "decision",
        "vara": None,
        "lugares": None,
    }


def _item(id_, titulo, estado, cuerpo) -> dict:
    return {"id": id_, "origen": ORIGEN_INBOX, "clase": "decision",
            "ts": "", "titulo": titulo, "cuerpo": cuerpo,
            "estado": estado, "respuesta": None}


def como_items(datos_endpoint: dict) -> list[dict]:
    """Traduce la respuesta de GET /api/economia/bus a items del inbox.

    Sin economia sembrada -- el estado de hoy -- esa respuesta es
    literalmente `{"activa": False}`: sin `propuestas` y sin `vencidas`.
    Por eso todos los accesos van con default.
    """
    items = []
    for p in datos_endpoint.get("propuestas") or []:
        cuerpo = {"departamento": p.get("departamento"),
                  "tipo": p.get("tipo"),
                  "presupuesto_mm": p.get("presupuesto_mm"),
                  "gastado_mm": p.get("gastado_mm"),
                  "verbos_validos": ["financiar", "descartar"]}
        if p.get("tipo") == "preseed":
            # un pre-seed lo paga el tesoro y nada mas: bus.financiar
            # rechaza cualquier billetera de departamento
            cuerpo["cuenta_fija"] = "tesoro"
        items.append(_item(p.get("id"), p.get("titulo") or "",
                           p.get("estado") or "alta", cuerpo))
    for v in datos_endpoint.get("vencidas") or []:
        # cinco campos, no diez, y financiar da 400 sobre un vencido
        items.append(_item(
            v.get("id"), v.get("titulo") or "", "vencida",
            {"departamento": v.get("departamento"),
             "semana": v.get("semana"),
             "presupuesto_mm": v.get("presupuesto_mm"),
             "verbos_validos": ["descartar"]}))
    return items
```

- [ ] **Step 4: Correr el test y ver que pasa**

Run: `.venv/bin/python -m pytest -q test_inbox.py`
Expected: PASS, 6 tests

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/bus.py test_inbox.py
git commit -m "feat(inbox): la mesa se declara y se traduce a items"
```

---

### Task 2: El descriptor y el adaptador de permisos

**Files:**
- Modify: `calipso/permisos/motor.py` (agregar al final)
- Test: `test_inbox.py` (agregar)

**Interfaces:**
- Consumes: nada de la Tarea 1.
- Produces: `motor.descriptor() -> dict`, `motor.como_items(vista: dict) -> list[dict]`

Tres cosas verificadas que el codigo tiene que respetar: la clave es **`activo`**
(masculino) y no `activa`; `vista()` devuelve `aprobadas` y `registro`, que **no
son items pendientes**; y `vista()` devuelve `error` con las listas vacias cuando
`solicitudes.json` no se puede leer -- **vacio-por-error y vacio-de-verdad se ven
igual**, que es justo cuando el badge miente.

- [ ] **Step 1: Escribir el test que falla**

```python
# agregar a test_inbox.py
from calipso.permisos import motor as permisos_motor


def test_permisos_no_ofrece_despues_ni_vence():
    """Un 'despues' sobre un permiso no aplaza: prolonga un bloqueo global.
    Y permisos no vence: grep de venc|caduc|expir en el paquete da cero."""
    d = permisos_motor.descriptor()
    assert d["origen"] == "permisos"
    assert d["reloj"] is None
    assert "despues" not in {v["nombre"] for v in d["verbos"]}
    assert {v["nombre"] for v in d["verbos"]} == {"si", "si_siempre", "no"}


def test_solo_lo_abierto_es_item():
    """`aprobadas` y `registro` no son items pendientes. Contarlos miente."""
    vista = {"activo": True,
             "pendientes": [{"id": "sol_a", "ts": "2026-08-31T11:00:00",
                             "estado": "pendiente", "texto": "acunar 500000 mm",
                             "siempre_pregunta": False, "accion": {},
                             "contexto": {}, "motivo": "supera el techo"}],
             "estacionadas": [], "aprobadas": [{"id": "sol_vieja"}],
             "registro": [{"id": "sol_x"}], "concedidos": [], "error": None}
    items = permisos_motor.como_items(vista)
    assert [i["id"] for i in items] == ["sol_a"]
    assert items[0]["origen"] == "permisos"
    assert items[0]["clase"] == "decision"


def test_siempre_pregunta_no_ofrece_el_verbo_siempre():
    """`si_siempre` sobre una solicitud con siempre_pregunta da 400. El
    inbox no puede dibujar un verbo que el origen no declaro."""
    vista = {"activo": True, "estacionadas": [], "aprobadas": [],
             "registro": [], "concedidos": [], "error": None,
             "pendientes": [{"id": "sol_b", "ts": "", "estado": "pendiente",
                             "texto": "acunar", "siempre_pregunta": True,
                             "accion": {}, "contexto": {}, "motivo": ""}]}
    it = permisos_motor.como_items(vista)[0]
    assert it["cuerpo"]["verbos_validos"] == ["si", "no"]


def test_vacio_por_error_no_se_confunde_con_vacio_de_verdad():
    """vista() devuelve `error` con las listas vacias cuando el archivo no
    se puede leer. Un badge en cero ahi es el badge mintiendo."""
    vista = {"activo": True, "pendientes": [], "estacionadas": [],
             "aprobadas": [], "registro": [], "concedidos": [],
             "error": "solicitudes.json ilegible"}
    items = permisos_motor.como_items(vista)
    assert len(items) == 1
    assert items[0]["clase"] == "aviso"
    assert items[0]["estado"] == "error"
    assert "ilegible" in items[0]["titulo"]


def test_permisos_inactivo_no_da_items():
    assert permisos_motor.como_items({"activo": False}) == []
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `.venv/bin/python -m pytest -q test_inbox.py -k permisos`
Expected: FAIL con `AttributeError: module 'calipso.permisos.motor' has no attribute 'descriptor'`

- [ ] **Step 3: Implementar lo minimo**

```python
# al final de calipso/permisos/motor.py

ORIGEN_INBOX = "permisos"


def descriptor() -> dict:
    """Lo que permisos declara de si mismo para el inbox.

    NO hay verbo "despues". Mientras una solicitud este abierta, esa forma
    exacta no pasa por ningun chat, ningun departamento ni ningun techo
    nuevo: aplazarla no es aplazar, es prolongar un bloqueo global.

    `reloj: None` no es un olvido: permisos no vence. Es una de las dos
    bandejas que tienen que declararlo explicitamente, porque el default
    no se puede inferir.
    """
    return {
        "origen": ORIGEN_INBOX,
        "verbos": [
            {"nombre": "si", "etiqueta": "Si",
             "alcances": ["una_vez"], "parametros": []},
            {"nombre": "si_siempre", "etiqueta": "Si, siempre",
             "alcances": ["siempre"], "parametros": []},
            {"nombre": "no", "etiqueta": "No",
             "alcances": ["una_vez"], "parametros": []},
        ],
        "reloj": None,
        "clase_por_defecto": "decision",
        "vara": None,
        "lugares": None,
    }


def como_items(vista: dict) -> list[dict]:
    """Traduce `motor.vista()` a items del inbox.

    La clave de disponibilidad es `activo` (masculino), no `activa`: la de
    economia es la otra y confundirlas deja el contador en cero sin ruido.

    Solo lo ABIERTO es item. `aprobadas` y `registro` vienen en la misma
    vista y no son cosas que esperen a Pedro.

    Y el caso que hace mentir a un badge: `vista()` devuelve `error` con
    todas las listas vacias cuando el archivo no se puede leer. Vacio por
    error se ve igual que vacio de verdad, asi que se emite un aviso -- que
    no cuenta para el badge, pero se ve.
    """
    if not vista.get("activo"):
        return []
    items = []
    if vista.get("error"):
        items.append({
            "id": "permisos:error", "origen": ORIGEN_INBOX, "clase": "aviso",
            "ts": "", "titulo": f"no se pudo leer permisos: {vista['error']}",
            "cuerpo": {"verbos_validos": []}, "estado": "error",
            "respuesta": None})
    for s in (vista.get("pendientes") or []) + (vista.get("estacionadas") or []):
        # si_siempre sobre una solicitud con siempre_pregunta devuelve 400:
        # lo cortan almacen.responder y almacen.conceder, las dos capas
        verbos = ["si", "no"] if s.get("siempre_pregunta") \
            else ["si", "si_siempre", "no"]
        items.append({
            "id": s.get("id"), "origen": ORIGEN_INBOX, "clase": "decision",
            "ts": s.get("ts") or "", "titulo": s.get("texto") or "",
            "cuerpo": {"accion": s.get("accion"),
                       "contexto": s.get("contexto"),
                       "motivo": s.get("motivo"),
                       "verbos_validos": verbos},
            "estado": s.get("estado") or "pendiente", "respuesta": None})
    return items
```

- [ ] **Step 4: Correr el test y ver que pasa**

Run: `.venv/bin/python -m pytest -q test_inbox.py`
Expected: PASS, 11 tests

- [ ] **Step 5: Commit**

```bash
git add calipso/permisos/motor.py test_inbox.py
git commit -m "feat(inbox): permisos se declara sin verbo de aplazar"
```

---

### Task 3: El descriptor y el adaptador del bibliotecario

**Files:**
- Modify: `calipso/librarian.py` (agregar al final)
- Test: `test_inbox.py` (agregar)

**Interfaces:**
- Produces: `librarian.descriptor() -> dict`, `librarian.como_items(datos: dict, proyecto: str) -> list[dict]`

**La asimetria que hay que decir y no aplanar.** El bibliotecario es **por
proyecto** (`librarian.py:33-38`: `CALIPSO_HOME/projects/<slug>/librarian/`) y las
otras tres son globales. Peor: `_slug(None)` devuelve `"global"`, asi que pedir la
bandeja sin proyecto **no falla: miente** -- devuelve un archivo distinto y vacio.

**Decision de este plan:** el item lleva el proyecto en el titulo, y el adaptador
**exige** el proyecto como parametro. No hay default. El criterio de aceptacion
del spec ("cambiar de proyecto no cambia el contenido del inbox") **no se cumple
para esta bandeja**, y el plan lo dice en vez de esconderlo: juntar los stores de
todos los proyectos necesita algo que hoy no existe, y es trabajo de otro plan.

- [ ] **Step 1: Escribir el test que falla**

```python
# agregar a test_inbox.py
import pytest

from calipso import librarian


def test_la_biblioteca_deja_editar_antes_de_aceptar():
    """La respuesta no es si/no: es 'si, pero asi'."""
    d = librarian.descriptor()
    assert d["origen"] == "biblioteca"
    assert d["reloj"] is None
    aceptar = next(v for v in d["verbos"] if v["nombre"] == "aceptar")
    assert "texto" in aceptar["parametros"]


def test_el_proyecto_es_obligatorio():
    """`_slug(None)` devuelve 'global' y lee un archivo distinto y vacio:
    pedir sin proyecto no falla, MIENTE. Aca falla."""
    with pytest.raises(ValueError):
        librarian.como_items({"proposals": []}, proyecto="")


def test_el_item_dice_de_que_proyecto_es():
    """Es la unica de las cuatro que no es global. Se dice, no se aplana."""
    datos = {"proposals": [{"id": "mem_abc123", "text": "Pedro prefiere pytest",
                            "status": "pending", "ts": "2026-08-31T10:00:00",
                            "scope": "global", "target": "pedro-perfil.md"}],
             "events": [{"id": "mem_x"}]}
    items = librarian.como_items(datos, proyecto="calipso")
    assert len(items) == 1
    assert items[0]["origen"] == "biblioteca"
    assert "calipso" in items[0]["titulo"]
    assert items[0]["cuerpo"]["texto"] == "Pedro prefiere pytest"


def test_los_events_no_son_items():
    """/api/memory/inbox devuelve tambien los ultimos 50 eventos del jsonl.
    No son cosas que esperen a Pedro."""
    datos = {"proposals": [], "events": [{"id": "a"}, {"id": "b"}]}
    assert librarian.como_items(datos, proyecto="calipso") == []
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `.venv/bin/python -m pytest -q test_inbox.py -k biblio or proyecto`
Expected: FAIL con `AttributeError: module 'calipso.librarian' has no attribute 'descriptor'`

- [ ] **Step 3: Implementar lo minimo**

```python
# al final de calipso/librarian.py

ORIGEN_INBOX = "biblioteca"


def descriptor() -> dict:
    """Lo que el bibliotecario declara de si mismo para el inbox.

    `aceptar` lleva `texto` porque la respuesta no es si/no: es "si, pero
    asi" -- `update` deja reescribir el contenido antes de aceptarlo.

    `reloj: None`: nada barre `inbox.json`. Es la segunda de las dos
    bandejas que no vencen y tienen que declararlo.
    """
    return {
        "origen": ORIGEN_INBOX,
        "verbos": [
            {"nombre": "aceptar", "etiqueta": "Aceptar",
             "alcances": ["una_vez"], "parametros": ["texto"]},
            {"nombre": "descartar", "etiqueta": "Descartar",
             "alcances": ["una_vez"], "parametros": ["motivo"]},
        ],
        "reloj": None,
        "clase_por_defecto": "decision",
        "vara": None,
        "lugares": None,
    }


def como_items(datos: dict, proyecto: str) -> list[dict]:
    """Traduce la respuesta de GET /api/memory/inbox a items del inbox.

    `proyecto` es OBLIGATORIO y no tiene default. Es la unica de las cuatro
    bandejas que no es global (`_store` cuelga de
    `CALIPSO_HOME/projects/<slug>/librarian/`), y `_slug(None)` no levanta:
    devuelve "global" y lee un archivo distinto y vacio. Un default aca es
    una bandeja que se ve vacia sin que nadie se entere.

    El proyecto va en el titulo porque el inbox es global y esta bandeja no:
    la asimetria se dice, no se aplana.
    """
    if not proyecto:
        raise ValueError(
            "como_items necesita el proyecto: el bibliotecario es por "
            "proyecto y sin el lee la bandeja 'global', que es otra")
    items = []
    for p in datos.get("proposals") or []:
        texto = p.get("text") or ""
        resumen = texto if len(texto) <= 80 else texto[:77] + "..."
        items.append({
            "id": p.get("id"), "origen": ORIGEN_INBOX, "clase": "decision",
            "ts": p.get("ts") or "", "titulo": f"[{proyecto}] {resumen}",
            "cuerpo": {"texto": texto, "scope": p.get("scope"),
                       "target": p.get("target"), "proyecto": proyecto,
                       "verbos_validos": ["aceptar", "descartar"]},
            "estado": p.get("status") or "pending", "respuesta": None})
    return items
```

- [ ] **Step 4: Correr el test y ver que pasa**

Run: `.venv/bin/python -m pytest -q test_inbox.py`
Expected: PASS, 15 tests

- [ ] **Step 5: Commit**

```bash
git add calipso/librarian.py test_inbox.py
git commit -m "feat(inbox): la biblioteca se declara, y su proyecto es obligatorio"
```

---

### Task 4: El descriptor y el adaptador de las cartas

**Files:**
- Modify: `calipso/economia/cola.py` (agregar al final)
- Test: `test_inbox.py` (agregar)

**Interfaces:**
- Produces: `cola.descriptor() -> dict`, `cola.como_items(datos_endpoint: dict) -> list[dict]`

**Es la bandeja mas traicionera de las cuatro**, y las tres trampas estan
verificadas: `pendientes` mezcla **cartas y compuertas**, discriminadas por
`es_carta`; una carta **no tiene `titulo`** -- hay que derivarlo de `carta["tipo"]`,
que es una de cuatro constantes; y los ids llevan **dos puntos**
(`"mandato:dep:a:2026-W35"`), asi que el ruteo por prefijo del spec no aplica.

- [ ] **Step 1: Escribir el test que falla**

```python
# agregar a test_inbox.py
from calipso.economia import cola as eco_cola


def test_las_cartas_no_vencen_y_sus_dos_verbos_no_son_simetricos():
    """Estan exceptuadas a mano de expirar_semana. Y `rechazar` funciona
    sobre una carta pero NO alimenta cartas_atendidas(), asi que no desarma
    el breaker: los dos verbos no hacen lo mismo al reves."""
    d = eco_cola.descriptor()
    assert d["origen"] == "cartas"
    assert d["reloj"] is None
    assert {v["nombre"] for v in d["verbos"]} == {"atender", "rechazar"}


def test_una_compuerta_no_es_una_carta():
    """`pendientes` mezcla las dos. Sin filtrar, el inbox ofrece 'atender'
    sobre una compuerta y eso da 500."""
    datos = {"activa": True, "pendientes": [
        {"id": "c1", "departamento": "dep:a", "titulo": "llamar",
         "tipo": "contacto", "obligatoria": True, "mpt_estimado": 500},
        {"id": "renovacion:claude_max:0", "es_carta": True,
         "carta": {"tipo": "renovacion", "suscripcion": "claude_max"},
         "carril": "normal", "monedas_en_juego": 0}]}
    items = eco_cola.como_items(datos)
    assert [i["id"] for i in items] == ["renovacion:claude_max:0"]


def test_el_titulo_de_una_carta_se_deriva_de_su_tipo():
    """Una carta no trae `titulo`: no tiene esa clave. Hay que armarlo."""
    datos = {"activa": True, "pendientes": [
        {"id": "cierre_departamento:dep:a:2026-W35", "es_carta": True,
         "carta": {"tipo": "cierre_departamento", "departamento": "dep:a"}}]}
    it = eco_cola.como_items(datos)[0]
    assert it["titulo"]
    assert "dep:a" in it["titulo"]


def test_el_id_de_una_carta_lleva_dos_puntos():
    """Por eso el item lleva `origen` y no se rutea por el prefijo del id,
    como decia el spec."""
    datos = {"activa": True, "pendientes": [
        {"id": "mandato:dep:a:2026-W35", "es_carta": True,
         "carta": {"tipo": "mandato", "departamento": "dep:a"}}]}
    it = eco_cola.como_items(datos)[0]
    assert ":" in it["id"]
    assert it["origen"] == "cartas"


def test_sin_economia_sembrada_no_hay_cartas():
    assert eco_cola.como_items({"activa": False}) == []
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `.venv/bin/python -m pytest -q test_inbox.py -k carta`
Expected: FAIL con `AttributeError: module 'calipso.economia.cola' has no attribute 'descriptor'`

- [ ] **Step 3: Implementar lo minimo**

```python
# al final de calipso/economia/cola.py

ORIGEN_INBOX = "cartas"

# El titulo se deriva del tipo porque una carta NO trae `titulo`: la clave
# no existe en su evento. Los cuatro tipos son los que emite el cierre.
_TITULO_DE_CARTA = {
    "mandato": "mandato de la direccion para {quien}",
    "tesoro_insuficiente": "el tesoro no alcanza para {quien}",
    "cierre_departamento": "{quien} lleva ocho semanas sin vender",
    "renovacion": "renovar la suscripcion {quien}",
}


def descriptor() -> dict:
    """Lo que la bandeja de cartas declara de si misma.

    `reloj: None` y es a mano: `expirar_semana` filtra `not
    e.get("es_carta")`, asi que una carta encolada queda encolada para
    siempre hasta que alguien la atienda o la rechace.

    Los dos verbos NO son simetricos y conviene saberlo: `rechazar`
    funciona sobre una carta y la saca de la lista, pero solo
    `atender_carta` alimenta `cartas_atendidas()`, que es lo que desarma el
    breaker de renovacion en el cierre.
    """
    return {
        "origen": ORIGEN_INBOX,
        "verbos": [
            {"nombre": "atender", "etiqueta": "Atender",
             "alcances": ["una_vez"], "parametros": ["firma"]},
            {"nombre": "rechazar", "etiqueta": "Rechazar",
             "alcances": ["una_vez"], "parametros": []},
        ],
        "reloj": None,
        "clase_por_defecto": "decision",
        "vara": None,
        "lugares": None,
    }


def como_items(datos_endpoint: dict) -> list[dict]:
    """Traduce GET /api/economia/cola a items del inbox, solo las cartas.

    `pendientes` mezcla DOS formas incompatibles en el mismo array: una
    compuerta (con departamento, titulo, tipo, obligatoria, mpt_estimado) y
    una carta (con `carta` adentro y `es_carta: True`). Sin filtrar, el
    inbox ofreceria "atender" sobre una compuerta, y el endpoint contesta
    500 con eso.
    """
    items = []
    for e in datos_endpoint.get("pendientes") or []:
        if not e.get("es_carta"):
            continue
        carta = e.get("carta") or {}
        quien = (carta.get("departamento") or carta.get("suscripcion")
                 or carta.get("quien") or "")
        plantilla = _TITULO_DE_CARTA.get(carta.get("tipo"),
                                         "carta {quien}")
        items.append({
            "id": e.get("id"), "origen": ORIGEN_INBOX, "clase": "decision",
            "ts": e.get("ts") or "",
            "titulo": plantilla.format(quien=quien).strip(),
            "cuerpo": {"carta": carta,
                       "verbos_validos": ["atender", "rechazar"]},
            "estado": "encolada", "respuesta": None})
    return items
```

- [ ] **Step 4: Correr el test y ver que pasa**

Run: `.venv/bin/python -m pytest -q test_inbox.py`
Expected: PASS, 20 tests

- [ ] **Step 5: Commit**

```bash
git add calipso/economia/cola.py test_inbox.py
git commit -m "feat(inbox): las cartas se declaran, y se separan de las compuertas"
```

---

### Task 5: El agregador y el endpoint

**Files:**
- Create: `calipso/inbox.py`
- Modify: `calipso/server.py` (endpoint nuevo, al lado de `api_eco_bus`)
- Test: `test_inbox_server.py` (crear)

**Interfaces:**
- Consumes: `descriptor()` y `como_items()` de los cuatro modulos anteriores.
- Produces: `GET /api/inbox -> {"items": [...], "descriptores": {...}, "pendientes": int}`

**Un solo endpoint y no cuatro fetch**, por un motivo verificado: tres de las
cuatro lecturas son del mismo libro y **`api_eco_cola` es el unico lector de
economia sin candado** -- su propio vecino lo dice textual: *"y no es un
ejemplo"*. Juntarlas del lado del servidor permite tomar el candado una vez y
leer bus y cola coherentes entre si.

- [ ] **Step 1: Escribir el test que falla**

```python
# test_inbox_server.py
"""El endpoint que junta las cuatro bandejas.

Se monta el home a mano porque el estado de hoy es que la economia no esta
sembrada: sin eso, tres de las cuatro fuentes contestan vacio y el test no
probaria nada.
"""
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
    """Las DOS cosas: _ECO_BASE y CALIPSO_HOME.

    `permisos/almacen.py` resuelve el home en cada llamada, mientras que
    `librarian.py` lo congela al importar. Sin las dos, el test escribe en
    el ~/.calipso real."""
    home = tmp_path / ".calipso"
    eco = home / "economia"
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
    monkeypatch.setattr(srv, "_ECO_BASE", home)
    monkeypatch.setenv("CALIPSO_HOME", str(home))
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_el_inbox_contesta_con_las_cuatro_declaraciones(cliente):
    r = cliente.get("/api/inbox")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo["descriptores"]) == {
        "mesa", "permisos", "biblioteca", "cartas"}


def test_una_propuesta_de_la_mesa_llega_al_inbox(cliente, tmp_path):
    from calipso.economia.bus import Bus
    b = Bus(tmp_path / ".calipso" / "economia" / "bus.jsonl")
    b.alta("2026-08-25T09:00:00", "2026-W35", "p1", "dep:a",
           "escribir el landing", 50_000, 50_000, {"gasto_max_mm": 50_000})
    items = cliente.get("/api/inbox").json()["items"]
    de_mesa = [i for i in items if i["origen"] == "mesa"]
    assert len(de_mesa) == 1
    assert de_mesa[0]["titulo"] == "escribir el landing"


def test_el_contador_cuenta_decisiones_y_no_avisos(cliente):
    """Es la unica forma real en que este diseño fracasa: si el numero no
    baja nunca, Pedro deja de mirarlo."""
    cuerpo = cliente.get("/api/inbox").json()
    decisiones = [i for i in cuerpo["items"] if i["clase"] == "decision"]
    assert cuerpo["pendientes"] == len(decisiones)


def test_sin_auth_rechaza(tmp_path):
    assert TestClient(srv.app).get("/api/inbox").status_code == 401


def test_una_bandeja_rota_no_voltea_el_inbox(cliente, tmp_path, monkeypatch):
    """Cuatro fuentes es cuatro veces la chance de que una falle. Si una se
    cae, las otras tres se siguen viendo y se dice cual fallo."""
    def explota(*a, **k):
        raise RuntimeError("bandeja rota")
    monkeypatch.setattr(srv._inbox.librarian, "como_items", explota)
    cuerpo = cliente.get("/api/inbox").json()
    assert r"biblioteca" in cuerpo["fallaron"]
    assert cuerpo["descriptores"]["mesa"]
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `.venv/bin/python -m pytest -q test_inbox_server.py`
Expected: FAIL con 404 en `/api/inbox`

- [ ] **Step 3: Implementar el agregador**

```python
# calipso/inbox.py
"""El agregador del inbox: junta las cuatro bandejas en una sola lista.

No sabe nada de ninguna bandeja. Cada origen declara lo suyo -- sus verbos,
su reloj, su clase -- y se traduce a si mismo; aca solo se los llama y se
junta el resultado. Agregar el correo mañana es agregarlo a `ORIGENES`.

Una bandeja rota no puede voltear a las otras tres: cuatro fuentes es
cuatro veces la chance de que una falle, y un inbox que desaparece entero
porque una fuente se cayo es peor que uno incompleto que lo dice.
"""
from __future__ import annotations

from calipso import librarian
from calipso.economia import bus as eco_bus
from calipso.economia import cola as eco_cola
from calipso.permisos import motor as permisos_motor


def descriptores() -> dict:
    return {d["origen"]: d for d in (
        eco_bus.descriptor(), permisos_motor.descriptor(),
        librarian.descriptor(), eco_cola.descriptor())}


def juntar(datos_bus: dict, vista_permisos: dict,
           datos_memoria: dict, proyecto: str,
           datos_cola: dict) -> tuple[list[dict], list[str]]:
    """Devuelve (items, origenes_que_fallaron).

    El orden de la lista es el de los origenes y dentro de cada uno el que
    trae la bandeja. Ordenar por urgencia es el PvP, y va en el plan 2.
    """
    fallaron: list[str] = []
    items: list[dict] = []
    llamadas = [
        ("mesa", lambda: eco_bus.como_items(datos_bus)),
        ("permisos", lambda: permisos_motor.como_items(vista_permisos)),
        ("biblioteca", lambda: librarian.como_items(datos_memoria, proyecto)),
        ("cartas", lambda: eco_cola.como_items(datos_cola)),
    ]
    for nombre, fn in llamadas:
        try:
            items.extend(fn())
        except Exception:
            fallaron.append(nombre)
    return items, fallaron


def cuenta_de_decisiones(items: list[dict]) -> int:
    """El badge cuenta decisiones, nunca avisos. Un aviso no espera a nadie."""
    return sum(1 for i in items if i.get("clase") == "decision")
```

- [ ] **Step 4: Implementar el endpoint**

```python
# en calipso/server.py, despues de api_eco_bus.
# Arriba, con los otros imports de modulos de calipso:
#     from calipso import inbox as _inbox

@app.get("/api/inbox")
def api_inbox() -> dict:
    """Las cuatro bandejas en una lista.

    Un solo endpoint y no cuatro fetch del cliente, por dos razones. La
    primera es el candado: bus y cola leen el MISMO libro, `api_eco_bus`
    toma el suyo y `api_eco_cola` NO -- es el unico lector de economia sin
    candado, y su vecino lo dice textual: "y no es un ejemplo". Sin un
    candado de afuera, el bus toma y suelta, y despues la cola lee sin
    ninguno: las dos mitades de la misma pantalla pueden ver estados
    distintos. Con este, las dos leen bajo una sola tenencia.

    Tomarlo aca y que `api_eco_bus` tome el suyo adentro es seguro y
    verificado: `candado` es REENTRANTE -- un `rlock` con contador de
    profundidad (`economia/candado.py:74-90`), asi que la adquisicion
    interna no suelta la externa al salir.

    La segunda razon es que las cuatro fuentes
    declaran su disponibilidad con TRES claves distintas (`activa` en
    economia, `activo` en permisos, ninguna en memoria): traducir eso una
    vez del lado del servidor es mejor que repetirlo en el cliente.
    """
    datos_bus: dict = {"activa": False}
    datos_cola: dict = {"activa": False}
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if p0:
        with _eco_candado(p0.ruta_libro):
            datos_bus = api_eco_bus()
            datos_cola = api_eco_cola()
    vista_permisos = ({"activo": True, **_permisos.vista()}
                      if _permisos is not None else {"activo": False})
    datos_memoria = {"proposals": librarian.list_proposals(str(ROOT),
                                                           "pending")}
    items, fallaron = _inbox.juntar(
        datos_bus, vista_permisos, datos_memoria, ROOT.name, datos_cola)
    return {"items": items,
            "descriptores": _inbox.descriptores(),
            "pendientes": _inbox.cuenta_de_decisiones(items),
            "fallaron": fallaron}
```

- [ ] **Step 5: Correr el test y ver que pasa**

Run: `.venv/bin/python -m pytest -q test_inbox_server.py`
Expected: PASS, 5 tests

- [ ] **Step 6: Correr la suite entera**

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py`
Expected: PASS, 841 tests (816 + 20 + 5)

- [ ] **Step 7: Commit**

```bash
git add calipso/inbox.py calipso/server.py test_inbox_server.py
git commit -m "feat(inbox): un endpoint junta las cuatro bandejas bajo un candado"
```

---

### Task 6: El modulo puro del cliente

**Files:**
- Create: `calipso/web/fabrica/inbox.js`
- Test: `calipso/web/fabrica/inbox.test.js` (crear)

**Interfaces:**
- Consumes: la respuesta de `GET /api/inbox` (Tarea 5).
- Produces: `textoDeInbox(datos)`, `contadorDeInbox(datos)`, `escapar(s)`

Sin fetch y sin DOM: es la regla del archivo vecino. Lo que decide QUE se muestra
vive aca; el DOM y los fetch viven en `app.js`.

- [ ] **Step 1: Escribir el test que falla**

```javascript
// calipso/web/fabrica/inbox.test.js
import {test} from "node:test";
import assert from "node:assert/strict";
import {textoDeInbox, contadorDeInbox} from "./inbox.js";

const DESCRIPTORES = {
  mesa: {origen: "mesa", verbos: [
    {nombre: "financiar", etiqueta: "Financiar", parametros: ["cuenta"]},
    {nombre: "descartar", etiqueta: "Descartar", parametros: []}]},
  permisos: {origen: "permisos", verbos: [
    {nombre: "si", etiqueta: "Si", parametros: []},
    {nombre: "si_siempre", etiqueta: "Si, siempre", parametros: []},
    {nombre: "no", etiqueta: "No", parametros: []}]},
};

function datos(items) {
  return {items, descriptores: DESCRIPTORES, pendientes: items.length,
          fallaron: []};
}

test("el inbox vacio lo dice y no queda en blanco", () => {
  const html = textoDeInbox(datos([]));
  assert.match(html, /nada esperando|no hay nada/i);
});

test("solo se dibujan los verbos que el item declara validos", () => {
  const html = textoDeInbox(datos([{
    id: "sol_a", origen: "permisos", clase: "decision", ts: "", estado: "pendiente",
    titulo: "acunar 500000 mm", respuesta: null,
    cuerpo: {verbos_validos: ["si", "no"]}}]));
  assert.match(html, /data-verbo="si"/);
  assert.match(html, /data-verbo="no"/);
  assert.ok(!html.includes('data-verbo="si_siempre"'),
            "dibujo un verbo que el item no declaro");
});

test("el titulo se escapa: lo escribe un modelo", () => {
  const html = textoDeInbox(datos([{
    id: "a-1", origen: "mesa", clase: "decision", ts: "", estado: "alta",
    titulo: '<script>alert(1)</script>', respuesta: null,
    cuerpo: {verbos_validos: ["descartar"]}}]));
  assert.ok(!html.includes("<script"));
  assert.match(html, /&lt;script/);
});

test("un id con dos puntos no rompe el markup", () => {
  const html = textoDeInbox(datos([{
    id: "mandato:dep:a:2026-W35", origen: "cartas", clase: "decision",
    ts: "", estado: "encolada", titulo: "mandato", respuesta: null,
    cuerpo: {verbos_validos: ["atender"]}}]));
  assert.match(html, /data-id="mandato:dep:a:2026-W35"/);
  assert.match(html, /data-origen="cartas"/);
});

test("el contador cuenta decisiones y no avisos", () => {
  const d = datos([
    {id: "a", origen: "mesa", clase: "decision", cuerpo: {}, titulo: "x"},
    {id: "b", origen: "permisos", clase: "aviso", cuerpo: {}, titulo: "y"}]);
  assert.equal(contadorDeInbox(d), 1);
});

test("una bandeja caida se dice, no se calla", () => {
  const d = datos([]);
  d.fallaron = ["biblioteca"];
  assert.match(textoDeInbox(d), /biblioteca/);
});

test("null o undefined no revientan", () => {
  assert.match(textoDeInbox(null), /nada esperando|no hay nada/i);
  assert.equal(contadorDeInbox(undefined), 0);
});
```

- [ ] **Step 2: Correr el test y ver que falla**

Run (cwd `calipso/web/fabrica/`):
`~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test inbox.test.js`
Expected: FAIL con `Cannot find module './inbox.js'`

- [ ] **Step 3: Implementar el modulo**

```javascript
// calipso/web/fabrica/inbox.js
// La lista unificada de las cuatro bandejas. Modulo PURO: lo que decide QUE
// se muestra vive aca; el DOM y los fetch viven en app.js.
//
// El inbox no sabe nada de ninguna bandeja. Dibuja los verbos que el item
// declara validos y nada mas: un boton que el origen no declaro es un boton
// que miente -- financiar sobre un vencido da 400, y `si_siempre` sobre una
// solicitud con siempre_pregunta tambien.

export function escapar(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => (
    {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));
}

const ETIQUETA_ORIGEN = {
  mesa: "la fabrica", permisos: "permiso",
  biblioteca: "memoria", cartas: "el cierre",
};

export function contadorDeInbox(datos) {
  return (datos?.items || []).filter(i => i.clase === "decision").length;
}

function fila(item, descriptores) {
  const desc = descriptores?.[item.origen];
  const validos = item.cuerpo?.verbos_validos || [];
  const botones = (desc?.verbos || [])
    .filter(v => validos.includes(v.nombre))
    .map(v => `<button data-inbox="responder" data-verbo="${escapar(v.nombre)}"` +
              ` data-id="${escapar(item.id)}"` +
              ` data-origen="${escapar(item.origen)}" type="button">` +
              `${escapar(v.etiqueta)}</button>`)
    .join("");
  const cuenta = item.cuerpo?.cuenta_fija
    ? ` <span class="nota">paga el tesoro</span>` : "";
  return `<div class="fila" data-id="${escapar(item.id)}"` +
         ` data-origen="${escapar(item.origen)}">` +
         `<span class="etiqueta">${escapar(ETIQUETA_ORIGEN[item.origen] || item.origen)}</span> ` +
         `<span class="titulo">${escapar(item.titulo)}</span>${cuenta}` +
         `<div class="acciones">${botones}</div></div>`;
}

export function textoDeInbox(datos) {
  const items = datos?.items || [];
  const fallaron = datos?.fallaron || [];
  const aviso = fallaron.length
    ? `<div class="nota">no se pudo leer: ${escapar(fallaron.join(", "))}</div>`
    : "";
  if (!items.length) {
    return aviso + `<div class="nota">Nada esperando.</div>`;
  }
  return aviso + items.map(i => fila(i, datos.descriptores)).join("");
}
```

- [ ] **Step 4: Correr el test y ver que pasa**

Run (cwd `calipso/web/fabrica/`):
`~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test inbox.test.js`
Expected: PASS, 7 tests

- [ ] **Step 5: Correr la suite del cliente entera**

Run (cwd `calipso/web/fabrica/`):
`~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test`
Expected: PASS, 359 tests (352 + 7), `# fail 0`

- [ ] **Step 6: Commit**

```bash
git add calipso/web/fabrica/inbox.js calipso/web/fabrica/inbox.test.js
git commit -m "feat(inbox): el modulo del cliente dibuja solo los verbos declarados"
```

---

### Task 7: El cableado

**Files:**
- Modify: `calipso/web/fabrica/index.html` (la sub-vista "Todo")
- Modify: `calipso/web/fabrica/app.js` (fetch, pintado, listeners, intervalo)
- Modify: `calipso/web/fabrica/sw.js` (`inbox.js` a `SHELL`)
- Modify: `calipso/verification.py`, `calipso/tools/commands.py`

**Interfaces:**
- Consumes: `textoDeInbox`, `contadorDeInbox` de la Tarea 6; `GET /api/inbox` de la Tarea 5.

**Tres trampas verificadas que rompen la suite si se ignoran:**
1. `arranque.test.js` monta un DOM de mentira con una lista fija de ids, y
   `inbox` no esta ahi. **Sin `if (!cajaInbox) return` al principio de
   `pintarInbox`, importar `app.js` revienta y se cae la suite JS entera.** La
   bitacora ya registra este golpe exacto.
2. `setInterval(...).unref?.()` **no es adorno**: sin `.unref()` el timer sostiene
   vivo el proceso y `node --test` no termina. El `?.` es porque en el navegador
   `setInterval` devuelve un numero.
3. El repintado al cambiar de pestaña **se cablea a mano** (`app.js:229`). Sin
   agregar la rama, la vista muestra la foto del momento de la carga.

- [ ] **Step 1: Agregar la sub-vista al markup**

En `calipso/web/fabrica/index.html`, dentro del `<nav id="submesa">`, como
**primer** boton (antes de "Decidir"):

```html
      <button data-vista="inbox" type="button">Todo
        <span id="badge-inbox" class="badge oculto"></span></button>
```

Y la caja, junto a las otras del panel:

```html
    <div id="caja-inbox" class="oculto"></div>
```

- [ ] **Step 2: Cablear en app.js**

Al lado de los otros imports de modulo:

```javascript
import {textoDeInbox, contadorDeInbox} from "./inbox.js";
```

Y el bloque, copiando el molde de `pintarPermisos`:

```javascript
const cajaInbox = document.getElementById("caja-inbox");
const badgeInbox = document.getElementById("badge-inbox");

async function pintarInbox() {
  // la guarda no es defensiva por gusto: arranque.test.js monta un DOM que
  // no declara este id, y sin esto el import de app.js revienta ahi antes
  // de correr un solo test
  if (!cajaInbox) return;
  try {
    const r = await fetch("/api/inbox");
    const datos = await r.json();
    cajaInbox.innerHTML = textoDeInbox(datos);
    const n = contadorDeInbox(datos);
    if (badgeInbox) {
      badgeInbox.textContent = String(n);
      badgeInbox.classList.toggle("oculto", n === 0);
    }
  } catch (e) {
    cajaInbox.innerHTML = `<div class="nota">no se pudo leer el inbox</div>`;
  }
}
```

En el `for` que cablea las sub-vistas del panel, agregar la rama de repintado:

```javascript
  if (boton.dataset.vista === "inbox") pintarInbox();
```

Y el intervalo, junto a los otros tres:

```javascript
setInterval(pintarInbox, 60_000).unref?.();
```

- [ ] **Step 3: Agregar el archivo al service worker**

En `calipso/web/sw.js`, dentro de `SHELL`:

```javascript
  "/static/fabrica/inbox.js",
```

- [ ] **Step 4: Enganchar los tests a la verificacion del repo**

En `calipso/verification.py`, en la rama que ya existe para economia y permisos,
agregar:

```python
        if "inbox" in lower:
            types.add("inbox")
            _add(plan, "test_inbox", f"{path} toca el inbox")
```

En `calipso/tools/commands.py`:

```python
    "test_inbox": {
        "title": "Probar el inbox",
        "description": "Ejecuta test_inbox.py y test_inbox_server.py.",
        "args": ["{python}", "-m", "pytest", "-q",
                 "test_inbox.py", "test_inbox_server.py"],
        "timeout": 120,
    },
```

- [ ] **Step 5: Correr las dos suites enteras**

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py`
Expected: PASS, 841 tests

Run (cwd `calipso/web/fabrica/`):
`~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test`
Expected: PASS, 359 tests, `# fail 0`

- [ ] **Step 6: Verificar a mano en el navegador**

Levantar el servidor y abrir `/fabrica`. Comprobar:
- La sub-vista "Todo" aparece y el badge no muestra un numero cuando no hay nada.
- Con la economia sin sembrar -- el estado de hoy -- la lista dice "Nada
  esperando" en vez de quedar en blanco o romperse.

- [ ] **Step 7: Commit**

```bash
git add calipso/web/fabrica/index.html calipso/web/fabrica/app.js \
        calipso/web/sw.js calipso/verification.py calipso/tools/commands.py
git commit -m "feat(inbox): la sub-vista Todo, cableada y en el service worker"
```

---

## Lo que este plan NO hace, y va en el plan 2

- **Responder desde el inbox.** Esta cinta muestra y cuenta; los botones llevan
  `data-verbo`, `data-id` y `data-origen`, pero el despacho de la accion a cada
  endpoint es del plan 2. Motivo: los cuatro endpoints de accion tienen cuerpos y
  errores distintos -- `atender` **exige** cuerpo aunque sea `{}`,
  `MesaFinanciarBody` tiene `extra="forbid"` con validador de booleanos, y **los
  endpoints de la cola no atrapan `ErrorCola`**, asi que hoy dan 500 sin `detail`
  y el patron del cliente se rompe ahi. Enchufarlos exige arreglar eso primero.
- **El aprendiz**: reglas, `no_siempre`, la pantalla de reglas, y la degradacion a
  `aviso` sobre fuentes exogenas.
- **El PvP**: la vara, los lugares y el orden. Y su prerequisito, que es la
  gramatica de `proponer` -- la unica decision que el spec deja abierta.
- **El vencimiento por origen.** Los cuatro descriptores ya lo **declaran**
  (`reloj`), pero nadie lo consume todavia: el unico vencimiento que existe sigue
  siendo el de los pre-seed, que es funcion pura del libro y ya funciona. Dos de
  las cuatro bandejas declaran `reloj: None` -- permisos y biblioteca no vencen,
  verificado con grep -- y esa declaracion es lo que el plan 2 necesita para
  ponerles uno sin adivinar el default.
- **El aviso fuera de la pantalla.** Su forma esta decidida en el spec (por el
  pulso, y solo la clase `decision`), pero no existe ningun camino hoy.
