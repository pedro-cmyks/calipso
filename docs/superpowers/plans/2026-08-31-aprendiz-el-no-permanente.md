# El aprendiz, parte 1: el no permanente

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que Pedro pueda decir "no, nunca mas" a una solicitud de permiso y que
eso corte de verdad en el motor, no en la pantalla; y que esa regla se vea y se
revoque en el mismo lugar donde ya se ven los si permanentes.

**Architecture:** No se construye un almacen nuevo ni una pantalla nueva. La
regla de negar se guarda en la MISMA lista `concedidos` de `permisos.json` con
un campo `efecto` (`"permitir"` / `"denegar"`), porque `revocar`, su endpoint y
su boton ya cuelgan de esa lista: con un campo, el `no_siempre` nace revocable y
visible sin escribir una linea de revocacion nueva. El corte va en
`motor.evaluar`, inmediatamente despues del consumo de aprobadas y ANTES de
`clasificar` -- que es la unica posicion desde la que un "no" puede tapar algo
que hoy es de nivel directo.

**Tech Stack:** Python 3.14, pytest, `node --test` para el cliente (via
`test_fabrica_js.py`). Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-08-31-inbox-design.md`, seccion 4c ("El
aprendiz: toda respuesta puede dejar regla"). Las tres reglas de esa seccion son
la autoridad de este plan; la regla 2 dice literalmente: *"`no_siempre` existe.
Hoy no existe en ninguna de las cuatro, y es la unica mitad que le falta al
sistema para poder encoger."*

## Global Constraints

- **Sin emojis.** En ningun lado: ni en el codigo, ni en los comentarios, ni en
  la UI, ni en los mensajes de commit. Texto plano o simbolos tipograficos.
- **Nombres, comentarios y docs en espanol.** Los mensajes de commit sin tildes
  ni enie.
- **Nunca importar `calipso` fuera de pytest.** El paquete escribe en el
  `~/.calipso` real. Todos los tests de este plan corren bajo el fixture `home`
  de `test_permisos.py`, que fija `CALIPSO_HOME` en un temporal.
- **`git add` con rutas explicitas**, nunca `-A` ni `.`: hay agentes en paralelo
  compartiendo el indice de git.
- **La escritura de `permisos.json` va bajo `candado(ruta_permisos())` y por
  `_guardar`** (temporal + `os.replace`). Ninguna funcion nueva escribe ese
  archivo de otra forma.
- **Releer el estado FRESCO dentro del candado.** El patron del modulo es
  `with candado(ruta): d = config(); mutar(d); _guardar(ruta, d)`. Nunca cachear
  `config()` antes de tomar el candado.
- **Comandos de verificacion:** `.venv/bin/python -m pytest <archivo> -q` desde
  `/var/home/pedro/calipso`. Los tests del cliente corren dentro de
  `test_fabrica_js.py`, que es tambien un test de pytest.

---

## Contexto verificado (leer antes de la Tarea 1)

Tres hechos que se verificaron leyendo el codigo y que este plan da por ciertos.
Si alguno resulta falso al implementar, es un defecto del plan y hay que
arreglar el plan, no compensarlo en el codigo.

1. **`concedidos` hoy no tiene ningun campo de efecto.** Una regla es un dict
   plano de 8 claves (`almacen.py:224-227`): `id`, `ts`, `familia`, `operacion`,
   `forma`, `chat`, `origen`, `texto`. No guarda `detalle`, ni `clave`, ni
   vencimiento. Es deliberadamente mas pobre que la solicitud de la que salio.

2. **La comparacion "esto ya esta contestado" es `cubre(permiso, a)`**
   (`acciones.py:457-466`): igualdad de `familia`, igualdad de `operacion`, y la
   `forma` por un cobertor despachado por familia (`_COBERTURAS`), con
   `_cubre_exacto` de default y una sola familia con subsuncion (`archivo`, por
   `raiz`). NO confundirla con `Accion.clave()` (`acciones.py:73-80`), que es
   identidad exacta y sirve para la pared de solicitudes abiertas, nunca para
   permisos.

3. **`config()` no normaliza nada** (`almacen.py:154-155`): copia los dicts de
   `concedidos` tal como estan en disco, sin agregar claves faltantes. Un
   `permisos.json` escrito por la version de hoy tiene reglas SIN campo
   `efecto`. Por eso el default se aplica en el punto de comparacion
   (`regla.get("efecto", "permitir")`) y nunca confiando en que la escritura lo
   puso.

## Las cinco decisiones que este plan toma

Ninguna esta en el spec; las cinco son de implementacion y se dejan escritas
para que Pedro pueda darlas vuelta sin tener que leer el codigo.

- **D1 -- misma lista `concedidos`, no una lista `denegados` aparte.**
  `revocar` (`almacen.py:238-246`) filtra por id sobre `d["concedidos"]`, y el
  endpoint `POST /api/permisos/concedidos/{id}/revocar` (`server.py:4618-4626`)
  y el boton de la UI (`permisos.js:142`, `app.js:523-525`) cuelgan de esa misma
  lista. Con un campo `efecto`, el `no_siempre` nace revocable sin escribir una
  linea nueva. Con una segunda lista habria que duplicar revocar, el endpoint,
  el barrido y la vista.

- **D2 -- `no_siempre` SI se admite sobre lo que pregunta siempre.**
  `si_siempre` esta prohibido ahi (`almacen.py:368-371` y `:220-223`) porque el
  criterio de 5.4 es que lo irreversible no admite un SI en blanco. Un NO
  permanente sobre acunar 500 monedas falla hacia el lado conservador, asi que
  la guarda pasa a valer solo para `efecto == "permitir"`.

- **D3 -- deny-wins, y ademas la regla nueva barre a la contraria.** El corte
  del no va antes de `clasificar`, asi que de hecho el no gana. Pero dejar las
  dos reglas vivas convertiria la pantalla en una trampa: Pedro revocaria el
  "no" esperando volver a que le pregunten y en silencio quedaria el "si"
  viejo. Por eso escribir una regla borra, en la misma escritura, cualquier
  regla del efecto contrario que cubra la accion que se esta contestando.

- **D4 -- una solicitud ya APROBADA y sin ejecutar se sigue ejecutando.** El
  corte del no va DESPUES del consumo de aprobadas. Pedro aprobo esa solicitud
  concreta antes; la regla gobierna lo que venga. Es la misma semantica del
  spec ("revocar una regla devuelve el futuro, nunca lo que la regla escondio")
  aplicada en el otro sentido.

- **D5 -- no se construye el agregador generico de reglas todavia.** El spec
  pide una pantalla de reglas unica y global, armada pidiendole a cada origen
  las suyas. Hoy permisos es el UNICO origen con reglas, y por D1 sus reglas de
  negar aparecen solas en la pantalla que ya existe. El `juntar_reglas` generico
  se escribe cuando haya un segundo origen con reglas -- que hoy no puede
  haberlo (ver "Lo que este plan NO hace" al final).

---

## Estructura de archivos

| Archivo | Responsabilidad en este plan |
|---|---|
| `calipso/permisos/almacen.py` | La mitad negativa del almacen: `efecto`, `anotar_regla`, `regla_que_cubre`, el barrido de la contraria, el rastro al revocar |
| `calipso/permisos/motor.py` | El corte en `evaluar`, la escritura de la regla en `responder`, el verbo en `descriptor()` y en `como_items()` |
| `calipso/web/fabrica/permisos.js` | El cuarto boton, y que una tarjeta de regla diga si permite o si niega |
| `calipso/web/fabrica/app.js` | La etiqueta del aviso para el verbo nuevo |
| `test_permisos.py` | Los tests del almacen y del motor |
| `test_inbox.py` | Los dos tests que afirman la lista de verbos de hoy |
| `calipso/web/fabrica/permisos.test.js` | Los tests del cliente |

`calipso/server.py` NO se toca: `api_permisos_responder` pasa `body.respuesta`
crudo y `almacen.RESPUESTAS` es el unico validador de pertenencia, asi que
agregar el verbo a esa tupla lo habilita en toda la superficie de una vez.
`calipso/inbox.py` tampoco se toca.

---

### Task 1: La mitad negativa del almacen

**Files:**
- Modify: `calipso/permisos/almacen.py:73` (RESPUESTAS), `:190-194`
  (cubierta_por_permiso), `:204-235` (conceder), `:238-246` (revocar)
- Test: `test_permisos.py`

**Interfaces:**
- Consumes: nada de tareas anteriores.
- Produces, y las tres las usa la Tarea 2:
  - `almacen.EFECTOS = ("permitir", "denegar")`
  - `almacen.anotar_regla(a: Accion, ctx: Contexto, texto: str, siempre_pregunta: bool = False, forma: dict | None = None, efecto: str = "permitir") -> dict`
  - `almacen.regla_que_cubre(a: Accion, efecto: str) -> dict | None`
  - `almacen.conceder(...)` queda con la misma firma de hoy y el mismo
    comportamiento, delegando en `anotar_regla` con `efecto="permitir"`.

- [ ] **Step 1: Escribir los tests que fallan**

En `test_permisos.py`, al final de la seccion de permisos permanentes:

```python
def test_una_regla_de_negar_se_guarda_con_su_efecto(home):
    almacen.anotar_regla(acunar(150_000), Contexto("pedro"),
                         "acunar 150 monedas", siempre_pregunta=True,
                         efecto="denegar")
    reglas = almacen.concedidos()
    assert len(reglas) == 1
    assert reglas[0]["efecto"] == "denegar"
    # la regla de negar vive en la MISMA lista que las de permitir: por eso
    # nace revocable, visible y barrible sin codigo nuevo (D1)
    assert reglas[0]["familia"] == "plata"


def test_negar_para_siempre_si_admite_lo_que_pregunta_siempre(home):
    # el corte de 5.4 es contra el SI en blanco sobre lo irreversible. Un NO
    # permanente sobre acunar falla hacia el lado conservador (D2).
    with pytest.raises(ErrorPermisos):
        almacen.anotar_regla(acunar(500_000), Contexto("pedro"), "x",
                             siempre_pregunta=True, efecto="permitir")
    r = almacen.anotar_regla(acunar(500_000), Contexto("pedro"), "x",
                             siempre_pregunta=True, efecto="denegar")
    assert r["efecto"] == "denegar"


def test_conceder_sigue_siendo_lo_que_era(home):
    # `conceder` es ahora un envoltorio, y no puede cambiar de significado:
    # sigue escribiendo permitir y sigue negandose sobre lo irreversible
    r = almacen.conceder(acunar(99_999), Contexto("pedro"), "x")
    assert r["efecto"] == "permitir"
    assert almacen.regla_que_cubre(acunar(99_999), "permitir") is not None
    assert almacen.regla_que_cubre(acunar(99_999), "denegar") is None


def test_una_regla_sin_efecto_se_lee_como_permitir(home):
    # `config()` no normaliza: un permisos.json escrito por la version
    # anterior tiene reglas sin la clave. El default se aplica al comparar,
    # nunca confiando en que la escritura lo puso.
    almacen.conceder(acunar(99_999), Contexto("pedro"), "x")
    p = almacen.ruta_permisos()
    d = json.loads(p.read_text(encoding="utf-8"))
    del d["concedidos"][0]["efecto"]
    p.write_text(json.dumps(d), encoding="utf-8")
    assert almacen.regla_que_cubre(acunar(99_999), "permitir") is not None


def test_una_regla_nueva_barre_a_la_contraria_sobre_la_misma_forma(home):
    # sin esto la pantalla seria una trampa: Pedro revocaria el "no"
    # esperando volver a que le pregunten, y en silencio quedaria vivo el
    # "si" viejo (D3)
    almacen.conceder(acunar(99_999), Contexto("pedro"), "x")
    almacen.anotar_regla(acunar(99_999), Contexto("pedro"), "x",
                         efecto="denegar")
    reglas = almacen.concedidos()
    assert len(reglas) == 1
    assert reglas[0]["efecto"] == "denegar"


def test_revocar_una_regla_deja_linea_en_el_registro(home):
    # revocar un "no" devuelve el futuro. Sin esta linea no queda en ningun
    # lado cuando dejo de valer.
    r = almacen.anotar_regla(acunar(150_000), Contexto("pedro"), "x",
                             siempre_pregunta=True, efecto="denegar")
    assert almacen.revocar(r["id"]) is True
    lineas = [l for l in almacen.registro(50)
              if l.get("evento") == "revocacion"]
    assert len(lineas) == 1
    assert lineas[0]["permiso"] == r["id"]
    assert lineas[0]["efecto"] == "denegar"
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_permisos.py -q -k "regla or conceder_sigue"`
Expected: FAIL con `AttributeError: module ... has no attribute 'anotar_regla'`

- [ ] **Step 3: `RESPUESTAS` y `EFECTOS`**

En `calipso/permisos/almacen.py`, reemplazar la linea 73:

```python
RESPUESTAS = ("si", "si_siempre", "no", "no_siempre")

# El signo de una regla permanente. Vive en la MISMA lista `concedidos`
# porque `revocar`, su endpoint y su boton ya cuelgan de esa lista: con un
# campo, el "no para siempre" nace revocable y visible sin una linea de
# revocacion nueva. `config()` no normaliza los dicts que lee del disco, asi
# que el default se aplica SIEMPRE al comparar (`.get("efecto", "permitir")`)
# y nunca confiando en que la escritura lo puso.
EFECTOS = ("permitir", "denegar")
```

- [ ] **Step 4: `regla_que_cubre`, y `cubierta_por_permiso` encima**

Reemplazar `cubierta_por_permiso` (`almacen.py:190-194`) por:

```python
def regla_que_cubre(a: Accion, efecto: str) -> dict | None:
    for regla in concedidos():
        if regla.get("efecto", "permitir") == efecto and cubre(regla, a):
            return regla
    return None


def cubierta_por_permiso(a: Accion) -> dict | None:
    """El si permanente. Se deja con su nombre y su firma de siempre para no
    tocar al llamador de `motor.evaluar`."""
    return regla_que_cubre(a, "permitir")
```

- [ ] **Step 5: `anotar_regla`, y `conceder` como envoltorio**

Reemplazar `conceder` (`almacen.py:204-235`) por:

```python
def anotar_regla(a: Accion, ctx: Contexto, texto: str,
                 siempre_pregunta: bool = False, forma: dict | None = None,
                 efecto: str = "permitir") -> dict:
    """La regla permanente de 5.4, en sus dos signos. Guarda cuando se
    escribio, desde que chat y con que texto exacto.

    El SI se NIEGA sobre lo que pregunta siempre, y la negativa vive aca y
    no solo en el endpoint: es la ultima linea antes del disco, asi que
    ningun llamador futuro -- ni un endpoint nuevo, ni el motor -- puede
    escribir por accidente un si permanente sobre un git push o sobre una
    acunacion. El NO no tiene esa restriccion a proposito: lo que pregunta
    siempre es lo irreversible, y un no permanente sobre eso falla hacia el
    lado conservador.

    `forma` permite escribir una forma MAS ANCHA que la de la accion
    -- "escribir bajo ~/Downloads" en vez de ese archivo suelto -- pero solo
    cuando esa forma efectivamente tapa la accion que se esta contestando:
    nadie escribe una regla que no cubre lo que tiene delante. Vale para los
    dos signos, y para el no importa mas: una regla de negar demasiado ancha
    es un bloqueo silencioso, porque el motor niega antes de crear la
    solicitud y no aparece nada en ninguna bandeja.

    Y escribir una regla BORRA la contraria que cubra esta misma accion, en
    la misma escritura. Si no, revocar el "no" devolveria en silencio el
    "si" viejo en vez de devolver la pregunta, que es exactamente la trampa
    que la regla 3 del spec quiere evitar.
    """
    if efecto not in EFECTOS:
        raise ErrorPermisos(f"efecto invalido: {efecto!r} (son {EFECTOS})")
    if siempre_pregunta and efecto == "permitir":
        raise ErrorPermisos(
            "esta operacion pregunta siempre (5.4): no admite permiso "
            "permanente")
    regla = {"id": _id("per"), "ts": _ahora(),
             "familia": a.familia, "operacion": a.operacion,
             "forma": dict(forma) if forma else dict(a.forma),
             "efecto": efecto,
             "chat": ctx.chat, "origen": ctx.origen, "texto": texto}
    if not cubre(regla, a):
        raise ErrorPermisos(
            "la forma de la regla no cubre la accion que se esta contestando")
    contraria = "denegar" if efecto == "permitir" else "permitir"
    with candado(ruta_permisos()):
        d = config()
        d["concedidos"] = [r for r in d["concedidos"]
                           if not (r.get("efecto", "permitir") == contraria
                                   and cubre(r, a))]
        d["concedidos"].append(regla)
        _guardar(ruta_permisos(), d)
    return regla


def conceder(a: Accion, ctx: Contexto, texto: str,
             siempre_pregunta: bool = False, forma: dict | None = None) -> dict:
    """El si permanente. Envoltorio de `anotar_regla` con su firma de
    siempre: lo llaman el motor y los tests, y cambiarles la firma no
    agregaria nada."""
    return anotar_regla(a, ctx, texto, siempre_pregunta, forma,
                        efecto="permitir")
```

- [ ] **Step 6: El rastro al revocar**

Reemplazar `revocar` (`almacen.py:238-246`) por:

```python
def revocar(id_permiso: str) -> bool:
    with candado(ruta_permisos()):
        d = config()
        revocada = next((c for c in d["concedidos"]
                         if c.get("id") == id_permiso), None)
        if revocada is None:
            return False
        d["concedidos"] = [c for c in d["concedidos"]
                           if c.get("id") != id_permiso]
        _guardar(ruta_permisos(), d)
        # revocar una regla de negar devuelve el futuro. Sin esta linea no
        # queda en ningun lado cuando dejo de valer, y el rastro de 5.4
        # tendria un agujero justo en el unico evento que reabre un caudal.
        anotar({"evento": "revocacion", "permiso": id_permiso,
                "efecto": revocada.get("efecto", "permitir"),
                "familia": revocada.get("familia"),
                "operacion": revocada.get("operacion"),
                "forma": revocada.get("forma")})
        return True
```

- [ ] **Step 7: Correr los tests**

Run: `.venv/bin/python -m pytest test_permisos.py -q`
Expected: PASS, incluidos los que ya existian (`conceder` no cambio de
comportamiento).

- [ ] **Step 8: Commit**

```bash
git add calipso/permisos/almacen.py test_permisos.py
git commit -m "feat(permisos): el almacen guarda reglas con signo, no solo permisos"
```

---

### Task 2: El corte, y donde va

**Files:**
- Modify: `calipso/permisos/motor.py:155-165` (el corte en `evaluar`),
  `:265-271` (la escritura en `responder`)
- Test: `test_permisos.py`

**Interfaces:**
- Consumes: `almacen.anotar_regla(...)` y `almacen.regla_que_cubre(a, efecto)`
  de la Tarea 1.
- Produces: `motor.responder(id, "no_siempre")` escribe una regla de negar y
  devuelve `{"solicitud": ..., "permiso": <la regla>, "ejecucion": None}`.

- [ ] **Step 1: Escribir el test que fallaria si el corte va en el lugar equivocado**

Este es el test que carga el peso de toda la tarea. La posicion del corte no se
puede verificar con un caso cualquiera: si va donde hoy vive el del si
(`motor.py:174-180`), TODO lo demas sigue en verde y solo se rompe cuando la
accion es de nivel directo. Ese es el caso que hay que escribir, y la secuencia
es realista: Pedro dice que nunca mas, y despues sube el techo.

En `test_permisos.py`:

```python
def test_un_no_permanente_tapa_lo_que_despues_pasa_a_ser_directo(home):
    """El caso que fija DONDE va el corte.

    Acunar 150 monedas esta sobre el techo: pregunta. Pedro contesta que
    nunca mas. Despues sube el techo a 200 monedas, y eso convierte la misma
    accion en NIVEL_DIRECTO.

    Si el corte del no viviera donde vive el del si -- despues de
    `clasificar` y bajo `if not v.siempre_pregunta` -- subir el techo
    anularia en silencio el no permanente de Pedro. Va antes de clasificar
    justamente para que no pueda pasar.
    """
    r = motor.evaluar(acunar(150_000), Contexto("pedro"))
    assert r.estado == motor.ESTADO_PENDIENTE
    motor.responder(r.solicitud["id"], "no_siempre")

    almacen.poner_techo("plata_mm", 200_000)
    assert acciones.clasificar(acunar(150_000),
                               almacen.techos()).nivel == NIVEL_DIRECTO

    r2 = motor.evaluar(acunar(150_000), Contexto("pedro"))
    assert r2.estado == motor.ESTADO_NEGADO
    assert "regla permanente" in r2.motivo


def test_un_no_permanente_no_crea_solicitud(home):
    """La regla filtra en el productor: el item no llega a existir.

    Es tambien la razon por la que la pantalla de reglas deja de ser un lujo
    y pasa a ser requisito: una regla de negar demasiado ancha no deja
    rastro en ninguna bandeja, y el unico lugar donde Pedro puede enterarse
    es la lista de reglas y el registro.
    """
    r = motor.evaluar(acunar(150_000), Contexto("pedro"))
    motor.responder(r.solicitud["id"], "no_siempre")
    antes = len(almacen.solicitudes())

    r2 = motor.evaluar(acunar(150_000), Contexto("otro_chat"))
    assert r2.estado == motor.ESTADO_NEGADO
    assert len(almacen.solicitudes()) == antes


def test_revocar_el_no_devuelve_la_pregunta_y_no_el_si_viejo(home):
    """La otra mitad de D3, del lado del motor."""
    r = motor.evaluar(acunar(150_000), Contexto("pedro"))
    salida = motor.responder(r.solicitud["id"], "no_siempre")
    almacen.revocar(salida["permiso"]["id"])

    r2 = motor.evaluar(acunar(150_000), Contexto("pedro"))
    assert r2.estado == motor.ESTADO_PENDIENTE


def test_no_siempre_deja_la_solicitud_negada(home):
    r = motor.evaluar(acunar(150_000), Contexto("pedro"))
    salida = motor.responder(r.solicitud["id"], "no_siempre")
    assert salida["solicitud"]["estado"] == almacen.ESTADO_NEGADA
    assert salida["ejecucion"] is None
    assert salida["permiso"]["efecto"] == "denegar"


def test_una_aprobada_sin_ejecutar_sobrevive_a_la_regla(home):
    """D4: el corte va DESPUES del consumo de aprobadas. Pedro aprobo esa
    solicitud concreta antes; la regla gobierna lo que venga.

    `desatendido` no es un parametro de `Contexto`: es una propiedad
    derivada de `origen not in ORIGENES_ATENDIDOS` (`acciones.py:108-110`,
    y los atendidos son "chat" y "pedro"). El molde de un contexto de
    rutina es el de `test_lo_estacionado_termina_la_corrida`. Y la segunda
    corrida lleva OTRO id a proposito: es lo que hace de verdad la rutina
    -- "la retoma en su proxima corrida" -- y ademas evita la pared de
    corrida, que es un corte anterior y taparia lo que este test mide.
    """
    ctx = Contexto("rutina", departamento="dep:atlas", corrida="corr-1")
    r = motor.evaluar(acunar(150_000), ctx)
    assert r.estado == motor.ESTADO_ESTACIONADA
    motor.responder(r.solicitud["id"], "si")
    almacen.anotar_regla(acunar(150_000), Contexto("pedro"), "x",
                         siempre_pregunta=True, efecto="denegar")

    proxima = Contexto("rutina", departamento="dep:atlas", corrida="corr-2")
    r2 = motor.evaluar(acunar(150_000), proxima)
    assert r2.estado == motor.ESTADO_PERMITIDO
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_permisos.py -q -k "no_permanente or no_siempre or aprobada_sin_ejecutar or devuelve_la_pregunta"`
Expected: FAIL. El primero falla en `motor.responder(..., "no_siempre")` con
`ErrorPermisos: respuesta invalida` si la Tarea 1 no esta, y con
`assert 'permitido' == 'negado'` si esta pero el corte no.

- [ ] **Step 3: El corte en `evaluar`**

En `calipso/permisos/motor.py`, insertar el bloque nuevo justo despues del `for`
que consume aprobadas (termina en `:163`) y ANTES de `v = clasificar(a, almacen.techos())`:

```python
        regla = almacen.regla_que_cubre(a, "denegar")
        if regla is not None:
            return _anotar(a, ctx, Resolucion(
                ESTADO_NEGADO, f"regla permanente de no: {regla['id']}",
                permiso=regla))
```

Y extender el docstring de `evaluar`, que enumera el orden de los cortes y dice
que no es cosmetico. Reemplazar el item 4 por:

```python
      4. una regla permanente de NO, antes de clasificar. Tiene que ir aca y
         no donde va el si: despues de clasificar ya pasaron NIVEL_NUNCA y
         NIVEL_DIRECTO, asi que un no puesto alla jamas taparia escribir
         dentro de las raices, ni un comando del allowlist, ni un monto bajo
         el techo -- y subir el techo anularia en silencio un no que Pedro
         ya habia dado. Va despues del consumo de aprobadas a proposito: lo
         que Pedro ya aprobo, se ejecuta; la regla gobierna lo que venga.
      5. recien ahi, el nivel.
```

- [ ] **Step 4: La escritura en `responder`**

En `motor.responder`, reemplazar el bloque de `si_siempre` (`:265-271`):

```python
    if respuesta in ("si_siempre", "no_siempre"):
        a = Accion.de_dict(s["accion"])
        ctx = Contexto.de_dict(s.get("contexto"))
        # el orden importa y es el de hoy: primero se responde la solicitud,
        # despues se escribe la regla. Si la segunda escritura falla, queda
        # una decision sin regla -- molesto, se vuelve a preguntar. Al reves
        # quedaria una regla sin decision, que es el lado peligroso: una
        # regla de negar escrita sobre algo que Pedro nunca termino de
        # contestar.
        permiso = almacen.anotar_regla(
            a, ctx, s.get("texto", ""),
            siempre_pregunta=s.get("siempre_pregunta", False),
            forma=forma_permanente,
            efecto="permitir" if respuesta == "si_siempre" else "denegar")
```

Y actualizar el docstring de `responder`, que hoy dice "Las tres salidas de
5.4": pasan a ser cuatro, y la cuarta es "no, y no me preguntes mas".

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/python -m pytest test_permisos.py test_permisos_server.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add calipso/permisos/motor.py test_permisos.py
git commit -m "feat(permisos): el no permanente corta en el motor, antes de clasificar"
```

---

### Task 3: El verbo, en el descriptor y en el inbox

**Files:**
- Modify: `calipso/permisos/motor.py:337-364` (descriptor), `:393-396`
  (verbos de `como_items`)
- Test: `test_inbox.py:96`, `test_inbox.py:123`

**Interfaces:**
- Consumes: nada nuevo; solo declara lo que las Tareas 1 y 2 hicieron posible.
- Produces: `descriptor()["verbos"]` incluye
  `{"nombre": "no_siempre", "etiqueta": "No, nunca mas", "alcances": ["siempre"], "parametros": []}`.
  La Tarea 4 lee esa etiqueta.

- [ ] **Step 1: Actualizar los dos tests que afirman la lista de hoy**

En `test_inbox.py`, la linea 96:

```python
    assert {v["nombre"] for v in d["verbos"]} == {"si", "si_siempre", "no",
                                                  "no_siempre"}
    # `alcances` es donde un origen declara que verbos dejan regla. Hoy
    # permisos es el unico que declara "siempre", y ahora lo declara en los
    # dos signos: es la mitad que el spec (4c, regla 2) dice que faltaba.
    siempre = {v["nombre"] for v in d["verbos"] if "siempre" in v["alcances"]}
    assert siempre == {"si_siempre", "no_siempre"}
```

Y la linea 123, en `test_..._siempre_pregunta`:

```python
    # si_siempre no aparece sobre lo que pregunta siempre -- lo cortan las
    # dos capas del almacen y daria 400. no_siempre SI, porque un no
    # permanente sobre lo irreversible falla hacia el lado conservador.
    assert it["cuerpo"]["verbos_validos"] == ["si", "no", "no_siempre"]
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_inbox.py -q`
Expected: FAIL, dos tests, por conjuntos y listas distintas.

- [ ] **Step 3: El verbo en el descriptor**

En `motor.descriptor()`, agregar el cuarto verbo despues de `no`:

```python
            {"nombre": "no", "etiqueta": "No",
             "alcances": ["una_vez"], "parametros": []},
            {"nombre": "no_siempre", "etiqueta": "No, nunca mas",
             "alcances": ["siempre"], "parametros": []},
```

Y agregarle al docstring del descriptor:

```python
    `no_siempre` es la mitad que el spec (4c) dice que le faltaba al sistema
    entero, y permisos es la unica de las cuatro bandejas donde se puede
    escribir hoy: es la unica que ya tiene una FORMA tipada que comparar
    (`acciones.cubre`). Las otras tres identifican sus items por prosa libre.
```

- [ ] **Step 4: Los verbos validos en `como_items`**

Reemplazar el bloque de `verbos` (`motor.py:393-396`):

```python
        # si_siempre sobre una solicitud con siempre_pregunta devuelve 400:
        # lo cortan `almacen.responder` y `almacen.anotar_regla`, las dos
        # capas. no_siempre no tiene esa restriccion y es a proposito: lo que
        # pregunta siempre es lo irreversible, y un NO permanente sobre eso
        # falla hacia el lado conservador. Dibujar el verbo que va a dar 400
        # es dibujar un boton que miente, asi que la lista se parte aca.
        verbos = ["si", "no", "no_siempre"] if s.get("siempre_pregunta") \
            else ["si", "si_siempre", "no", "no_siempre"]
```

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/python -m pytest test_inbox.py test_inbox_server.py test_permisos.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add calipso/permisos/motor.py test_inbox.py
git commit -m "feat(permisos): el descriptor declara el no permanente como verbo con regla"
```

---

### Task 4: El boton, y que la pantalla diga de que signo es cada regla

**Files:**
- Modify: `calipso/web/fabrica/permisos.js:73-89` (botonesDeRespuesta),
  `:133-151` (tarjetaConcedido, seccionConcedidos)
- Modify: `calipso/web/fabrica/app.js:534-536` (el mapa de etiquetas)
- Test: `calipso/web/fabrica/permisos.test.js`

**Interfaces:**
- Consumes: `vista()["concedidos"]` ya trae el campo `efecto` (es
  `almacen.concedidos()` crudo, `motor.py:322`). No hace falta tocar el
  endpoint ni `server.py`.
- Produces: nada que consuma otra tarea.

Nota sobre el inbox: `calipso/web/fabrica/inbox.js` NO se toca. Sus cuatro
botones salen `disabled` a proposito y su despacho es del plan 2 de la cinta.
La pantalla de permisos tiene su propio listener y su propio POST, que
funcionan hoy: el verbo nuevo llega a Pedro por ahi.

- [ ] **Step 1: Escribir los tests que fallan**

En `calipso/web/fabrica/permisos.test.js`. El primero endurece un test que ya
existe -- hoy afirma `/no preguntes mas/`, que a partir de esta tarea tambien
lo cumple el boton de negar, asi que dejaria de probar lo que dice probar:

```js
test("si siempre_pregunta es falso, el boton de permiso permanente aparece",
     () => {
  const sol = {...SOL_ACUNAR, siempre_pregunta: false};
  const html = textoDePermisos(datos({pendientes: [sol]}));
  assert.match(html, /data-respuesta="si_siempre"/);
  // contra el texto del boton de SI, no contra "no preguntes mas" a secas:
  // el boton de negar tambien lo dice y taparia la ausencia del de si
  assert.match(html, /si, no preguntes mas/);
});

test("el boton de no permanente aparece tambien sobre lo que pregunta " +
     "siempre: un no sobre lo irreversible es el lado conservador", () => {
  const html = textoDePermisos(datos({pendientes: [SOL_ACUNAR]}));
  assert.ok(!html.includes('data-respuesta="si_siempre"'),
            "aparecio un si permanente sobre algo que pregunta siempre");
  assert.match(html, /data-respuesta="no_siempre"/);
});

test("una regla dice si permite o si niega, y una vieja sin efecto permite",
     () => {
  const html = textoDePermisos(datos({concedidos: [
    {id: "per_1", familia: "plata", operacion: "acunar", forma: {}, ts: "",
     efecto: "denegar"},
    {id: "per_2", familia: "comando", operacion: "correr", forma: {}, ts: ""},
  ]}));
  assert.match(html, /niega plata\/acunar/);
  assert.match(html, /permite comando\/correr/);
});
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `.venv/bin/python -m pytest test_fabrica_js.py -q`
Expected: FAIL, tres tests.

- [ ] **Step 3: El cuarto boton**

Reemplazar `botonesDeRespuesta` (`permisos.js:73-89`):

```js
/** Las cuatro salidas de 5.4: si una vez, si y no preguntes mas, no, y no
 *  nunca mas. El segundo solo si el endpoint de verdad lo admite -`si_siempre`
 *  sobre una solicitud con `siempre_pregunta` devuelve 400- y si no, se DICE
 *  por que no esta en vez de dibujar un boton que miente. El cuarto esta
 *  siempre: negar para siempre lo irreversible es el lado conservador, asi
 *  que no tiene la restriccion que tiene su gemelo. */
function botonesDeRespuesta(s) {
  const id = escapar(s.id);
  const siSiempre = s.siempre_pregunta
    ? `<span class="nota">esta accion pregunta siempre: no admite ` +
      `permiso permanente</span>`
    : `<button data-accion="responder" data-id="${id}" ` +
      `data-respuesta="si_siempre">si, no preguntes mas</button>`;
  return `<div class="botones">` +
    `<button data-accion="responder" data-id="${id}" ` +
    `data-respuesta="si">si, una vez</button>` +
    siSiempre +
    `<button data-accion="responder" data-id="${id}" ` +
    `data-respuesta="no">no</button>` +
    `<button data-accion="responder" data-id="${id}" ` +
    `data-respuesta="no_siempre">no, nunca mas</button></div>`;
}
```

- [ ] **Step 4: La tarjeta dice el signo**

Reemplazar `tarjetaConcedido` y `seccionConcedidos` (`permisos.js:133-151`):

```js
/** El signo va primero y con todas las letras. Dos reglas de la misma
 *  familia y operacion se ven identicas si no se dice cual permite y cual
 *  niega, y revocar la equivocada es exactamente la trampa que la regla 3
 *  del spec quiere evitar. Una regla vieja no trae el campo -- se escribio
 *  antes de que existiera el no-- y esas son todas de permitir. */
function tarjetaConcedido(regla) {
  const p = regla || {};
  const verbo = p.efecto === "denegar" ? "niega" : "permite";
  return `<div class="permiso">` +
    `<div class="cabeza">${verbo} ${escapar(p.familia || "?")}/` +
    `${escapar(p.operacion || "?")}</div>` +
    `<div class="fila"><span>forma</span>` +
    `<span>${escapar(JSON.stringify(p.forma || {}))}</span></div>` +
    `<div class="fila"><span>escrita</span><span>${escapar(p.ts || "")}` +
    `</span></div>` +
    `<button data-accion="revocar" data-id="${escapar(p.id)}">revocar</button>` +
    `</div>`;
}

function seccionConcedidos(concedidos) {
  const cuerpo = concedidos.length
    ? concedidos.map(tarjetaConcedido).join("")
    : `<div class="vacio">Ninguna regla permanente.</div>`;
  return `<div class="subtitulo">reglas permanentes</div>` + cuerpo;
}
```

- [ ] **Step 5: La etiqueta del aviso**

En `calipso/web/fabrica/app.js`, en el mapa de etiquetas (`:534-536`):

```js
      const etiqueta = {si: "aprobada una vez", si_siempre: "aprobada para siempre",
                        no: "rechazada",
                        no_siempre: "rechazada para siempre"}[boton.dataset.respuesta]
        || "contestada";
```

- [ ] **Step 6: Correr los tests**

Run: `.venv/bin/python -m pytest test_fabrica_js.py -q`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add calipso/web/fabrica/permisos.js calipso/web/fabrica/app.js calipso/web/fabrica/permisos.test.js
git commit -m "feat(fabrica): el boton de no permanente, y la pantalla dice de que signo es cada regla"
```

---

### Task 5: Que tocar permisos dispare los tests de permisos

**Files:**
- Modify: `calipso/tools/commands.py:170-176` (agregar `test_permisos` al lado
  de `test_inbox`)
- Modify: `calipso/verification.py:102-110` (una rama propia para permisos)
- Test: `test_verification.py`, `test_commands.py`

**Interfaces:**
- Consumes: nada. Es independiente de las cuatro tareas anteriores y se puede
  hacer antes o despues; va al final porque su test es la suite entera.
- Produces: nada.

**Verificado, no supuesto:** hoy `verification.py` nombra `permisos/motor.py`
una sola vez, y es dentro de la rama del INBOX (`:103`), que corre `test_inbox`.
O sea: tocar el motor de permisos NO corre `test_permisos.py`, y tocar
`calipso/permisos/almacen.py` no corre nada mas que `py_compile_core`. Es
exactamente el agujero que la rama de `test_memoria_ambito` (`:81-85`) y la de
`test_contrato_departamentos` (`:89-95`) documentan haber tapado en su momento:
la verificacion que el repo indica daba verde sin correr una sola assertion
sobre lo que se acababa de cambiar. Este plan agrega el corte permanente que
niega acciones antes de que nazca la solicitud; dejarlo sin esa red seria
agregar la funcion mas silenciosa del motor a la parte del motor que la
verificacion no mira.

- [ ] **Step 1: Escribir el test que falla**

En `test_verification.py`:

```python
def test_tocar_permisos_corre_los_tests_de_permisos():
    """El motor de permisos aparecia solo dentro de la rama del inbox, asi
    que tocarlo corria test_inbox y no test_permisos; y el almacen no
    disparaba nada. Un corte que NIEGA antes de crear la solicitud es lo
    mas silencioso que hay en el motor: sin esta red, romperlo da verde."""
    for ruta in ("calipso/permisos/almacen.py", "calipso/permisos/motor.py",
                 "calipso/permisos/acciones.py"):
        plan = verification.recommend(files=[{"path": ruta}])
        ids = [c["command_id"] for c in plan["commands"]]
        assert "test_permisos" in ids, ruta
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `.venv/bin/python -m pytest test_verification.py -q -k permisos`
Expected: FAIL con `assert 'test_permisos' in ['py_compile_core']`

- [ ] **Step 3: El comando en el allowlist**

En `calipso/tools/commands.py`, junto a `test_inbox` (`:170-176`):

```python
    "test_permisos": {
        "title": "Probar el motor de permisos",
        "description": "Ejecuta test_permisos.py y test_permisos_server.py.",
        "args": ["{python}", "-m", "pytest", "-q",
                 "test_permisos.py", "test_permisos_server.py"],
        "timeout": 120,
    },
```

- [ ] **Step 4: La rama en el recomendador**

En `calipso/verification.py`, antes de la rama del inbox (`:102`):

```python
        if "permisos" in lower:
            types.add("permisos")
            # el motor de permisos aparecia SOLO dentro de la rama del
            # inbox, que corre test_inbox: tocar `almacen.py` no disparaba
            # nada y tocar `motor.py` corria los tests del agregador, no los
            # del motor. El corte del no permanente niega antes de crear la
            # solicitud -- no deja item en ninguna bandeja -- asi que es
            # justo lo que un verde sin assertions no atraparia.
            _add(plan, "test_permisos", f"{path} toca el motor de permisos")
```

La rama del inbox se deja como esta: `permisos/motor.py` tiene que seguir
disparando `test_inbox` tambien, porque ahi vive el adaptador
(`descriptor()`/`como_items()`) que la Tarea 3 cambia. Las dos ramas son
verdaderas al mismo tiempo y `_add` ya deduplica por `command_id`.

- [ ] **Step 5: Correr los tests**

Run: `.venv/bin/python -m pytest test_verification.py test_commands.py -q`
Expected: PASS

- [ ] **Step 6: La suite entera**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS, sin ningun test nuevo saltado. `test_fabrica_js.py` tiene un
piso de 90 tests de cliente: este plan agrega, nunca resta.

- [ ] **Step 7: Verificar que el codigo nuevo es solo ascii**

Run: `git diff main | grep -nP '^\+.*[^\x00-\x7F]' || echo "solo ascii"`
Expected: `solo ascii`. Sin emojis y sin tildes en lo agregado.

- [ ] **Step 8: Commit**

```bash
git add calipso/tools/commands.py calipso/verification.py test_verification.py
git commit -m "fix(verificacion): tocar permisos corria los tests del inbox, no los del motor"
```

---

## Lo que este plan NO hace, y por que

**Las otras tres bandejas no reciben `no_siempre`.** No es alcance recortado por
comodidad: ninguna de las tres puede hoy.

- **La mesa.** Es la que mas lo necesita y es la que no se puede. Verificado con
  grep: `descartadas_semana` tiene cuatro apariciones en el repo, se escribe en
  `situacion.py:185`, se lee en `decision.py:53` para armar un renglon del
  prompt, y las otras dos son tests. `jefe._puede` no la nombra nunca. O sea que
  el "no" de la mesa nunca fue un freno: es un pedido a un modelo de 3b, y
  caduca a la semana. El freno tiene que ir en `jefe._puede`, y ahi esta el
  bloqueo: **`_puede` no tiene con que comparar.** La identidad de una propuesta
  es un id uuid nuevo en cada alta y un titulo que es `(motivo or ...)[:120]`
  -- prosa libre de un modelo, truncada, sin validar ni normalizar. Comparar
  titulos por igualdad no atrapa nada ("radar de precios" y "un radar de precios
  de la competencia"), y por substring atrapa de mas y es imposible de explicar
  cuando Pedro vaya a revocar. La mesa necesita que la propuesta tenga una FORMA
  tipada, que es exactamente la decision de la gramatica de `proponer` que esta
  esperando a Pedro.

- **El bibliotecario.** Necesita un almacen nuevo, y el molde que tiene al lado
  esta roto: `_save` (`librarian.py:61-63`) es `write_text` pelado -- sin
  temporal, sin `os.replace`, sin candado -- y `_load` (`:49-58`) atrapa
  `except Exception` a secas y devuelve la lista vacia, asi que el primer
  `_save` posterior sobreescribe un archivo corrupto y las propuestas se pierden
  de verdad, no solo de vista. Ademas es la unica bandeja por proyecto
  (`_slug(None)` devuelve `"global"` en silencio), asi que toda funcion de
  reglas suya tiene que llevar `proyecto` obligatorio. Es un plan propio, y
  empieza por arreglar la escritura.

- **Las cartas.** Tienen forma tipada (`motivo` + `quien`, `cola.py:265-269`),
  asi que mecanicamente se podria. Pero un "nunca mas" sobre una carta de
  renovacion deja armado para siempre el breaker del cierre: solo
  `atender_carta` alimenta `cartas_atendidas()`. Es una decision de la economia,
  no de la maquinaria de reglas.

**La otra mitad de la regla 1 del spec queda para el plan 2 de la cinta.** La
regla dice: *"Toda respuesta se guarda con su alcance declarado... es un campo
del item, y el origen declara que alcances acepta cada verbo."* La segunda
mitad es la Tarea 3. La primera -- que el despacho del inbox mande el alcance
junto con el verbo -- es del plan de la cinta parte 2, que es el que enciende
los cuatro botones que hoy salen `disabled` y todavia no tiene listener en
`app.js`. Cuando se escriba, los `data-*` de `inbox.js` (`data-verbo`,
`data-id`, `data-origen`) necesitan uno mas: `data-alcance`. Este plan no lo
agrega porque agregarlo sin el despacho seria dejar un atributo que nadie lee.

**No se construye el agregador generico de reglas** (`inbox.juntar_reglas`, un
GET propio, revocar ruteado por prefijo de id). Por D1 las reglas de negar de
permisos aparecen en la pantalla que ya existe, con el revocar que ya existe. El
agregador se escribe cuando haya un segundo origen con reglas. Cuando se
escriba, dos cosas del reconocimiento hay que tener a mano: tiene que copiar el
molde de `inbox.juntar` (que reporta `fallaron`) y NO el de
`inbox.descriptores` (que omite en silencio al origen que no importo) -- sobre
una pantalla de revocacion, "ese origen no tiene reglas" cuando en realidad no
se pudieron leer es una mentira peligrosa; y el descriptor no es lugar para la
lista de reglas, porque viaja en cada refresco del inbox y leeria cuatro
archivos cada 60 segundos para no dibujarlos.

## Dos limites conocidos que quedan escritos

- **Un `permisos.json` ilegible desactiva las reglas de negar.** `config()`
  devuelve la configuracion vacia cuando el archivo no se puede leer
  (`almacen.py:140-149`), y para el si eso es el lado seguro -- se pregunta de
  mas. Para el no significa que un json corrupto vuelve a abrir el caudal: se
  vuelve a preguntar, que sigue siendo mejor que ejecutar, pero contradice la
  intuicion de "la regla es permanente".

- **"No corras git nunca mas" no es expresable.** `cubre` exige igualdad de
  `familia` y de `operacion`, y la forma por defecto es igualdad exacta de dict
  entero, asi que `["npm", "test"]` y `["npm", "test", "--", "x"]` son dos
  reglas distintas. Para el no eso es inutilmente estricto -- falla hacia volver
  a preguntar, que es seguro pero molesto. El enchufe para arreglarlo ya existe
  y no lo usa este plan: `registrar_cobertura(familia, fn)`
  (`acciones.py:452-454`), con `_cubre_archivo` (`:433-444`) de molde. Vale la
  pena hacerlo despues de ver que reglas escribe Pedro de verdad, no antes.
