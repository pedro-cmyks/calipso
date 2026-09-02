# El juez de privacidad y la redaccion (Fase 2, parte 1) -- plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir, como librerias probadas en aislado y SIN cablear al camino vivo, el juez de privacidad de dos capas (detector determinista de secretos + juez LLM local) y la capa de redaccion/reposicion con marcadores estables.

**Architecture:** Un paquete nuevo `calipso/privacidad/` con cuatro modulos de responsabilidad unica: `detector.py` (regex/entropia, la capa de credenciales, instantaneo), `juez_llm.py` (una llamada a Ollama con el prompt ya medido, la capa de lenguaje humano), `juez.py` (une las dos capas en un veredicto; credencial o LLM caido => fallo cerrado), y `redaccion.py` (tapa los tramos humanos con marcadores estables por conversacion y los repone). Nada de esto toca `server.py` ni la UI: eso es el parte 2. El banco de `experimentos/juez_privacidad.py` (ya en la rama) queda como guarda de regresion.

**Tech Stack:** Python 3.14, pytest. Ollama local (`qwen2.5:7b` via `dispatch.CONFIG["local"]` y `dispatch._http_post_json`). Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-02-ruteo-vivo-y-privacidad-design.md` (Fase 2, secciones 8-10). El cableado al camino vivo y la UI del degradado avisado (secciones 9 y 12) son el parte 2, NO entran aca.

## Global Constraints

- **SIN EMOJIS.** Codigo, comentarios, texto que ve Pedro, mensajes de commit.
- **Nombres, comentarios y docstrings en ESPANOL.** Commits **sin tildes ni enie**.
- **NUNCA importar `calipso` fuera de pytest.** Los tests corren bajo pytest (que aisla `CALIPSO_HOME`, ver `test_aislacion_home.py`). **HAY UN SERVIDOR CORRIENDO: no pararlo, no reiniciarlo.**
- **`git add` con rutas explicitas.**
- **El juez corre LOCAL, las dos capas.** Ningun texto que se juzga sale de la maquina para juzgarlo. `juez_llm` habla solo con Ollama local.
- **Una credencial detectada => fallo cerrado.** Nunca se redacta ni se manda tapada (spec seccion 9, decision de Pedro 2026-09-02). Si el juez LLM no responde, tambien fallo cerrado: sin poder verificar, no se manda.
- **El contrato del juez son subcadenas tipadas**, no offsets: `{"texto": <literal>, "tipo": <uno de seis>}`. Las posiciones las deriva la redaccion buscando la subcadena.
- **Los seis tipos:** `identidad`, `credencial`, `salud`, `ubicacion`, `financiero`, `contacto`.
- **Sin techos de latencia (principio de Pedro).** Este plan no impone limites de tiempo; el juez tarda lo que la inferencia necesita. El unico desperdicio a evitar (recarga fria del modelo, correr el juez donde el dato no sale) es del parte 2 (el cableado); aca las librerias solo hacen su trabajo cuando se las llama.
- **Interprete:** `.venv/bin/python`. Tests: `.venv/bin/python -m pytest <archivo> -q` desde `/var/home/pedro/calipso`.

---

## Contexto verificado (leer antes de la Tarea 1)

1. **La medicion ya paso** (spec seccion 10, `experimentos/juez_privacidad.py`): el 7b solo NO pasa el piso (deja pasar blobs de maquina: un JWT, un `rk_live_`); el detector determinista cierra esos huecos con cero falsos positivos sobre los negativos; el hibrido PASA (credencial 39/39, salud 36/36). Este plan promueve ese detector-prototipo (que hoy vive inline en el experimento) a modulo de produccion.
2. **La llamada a Ollama** que usa Calipso: `dispatch._http_post_json(url, payload)` (POST no-streaming, devuelve el dict parseado; la respuesta esta en `data["response"]`). `dispatch.CONFIG["local"]` = `{"base_url": "http://localhost:11434/api/generate", "model": "qwen2.5:7b"}`. `format: "json"` fuerza salida JSON parseable; `options: {"temperature": 0, "num_ctx": 4096}`.
3. **El prompt del juez** ya validado esta en `experimentos/juez_privacidad.py` como `JUEZ_SISTEMA`. La Tarea 2 lo lleva a `juez_llm.py` como la fuente de verdad de produccion (el experimento puede seguir con su copia; la unificacion es del parte 2).
4. **El flag `private` de hoy** es `dispatch.PRIVATE` (regex debil, `dispatch.py:124`), usado en `extract_features`. NO se toca en este plan (es del cableado, parte 2). Aca solo se construye el reemplazo.
5. **La convencion de tests** es plana: `test_*.py` en la raiz. Los tests de este plan son `test_privacidad_*.py`.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `calipso/privacidad/__init__.py` | marca el paquete; sin logica |
| `calipso/privacidad/detector.py` | detector determinista de secretos (T1) |
| `calipso/privacidad/juez_llm.py` | la llamada al juez LLM local (T2) |
| `calipso/privacidad/juez.py` | une las dos capas en un veredicto (T3) |
| `calipso/privacidad/redaccion.py` | marcadores estables: tapar y reponer (T4) |
| `test_privacidad_detector.py` | tests de T1 |
| `test_privacidad_juez_llm.py` | tests de T2 (mock HTTP + integracion opcional) |
| `test_privacidad_juez.py` | tests de T3 |
| `test_privacidad_redaccion.py` | tests de T4 |
| `test_privacidad_guarda.py` | guarda de regresion del detector contra el banco (T5) |

## Los tipos que comparten las tareas

- **Tramo:** `dict` con `{"texto": str, "tipo": str}` (`tipo` en los seis).
- **Veredicto** (lo que devuelve `juez.juzgar`): `dict` con
  `{"tramos": list[Tramo], "fallo_cerrado": bool, "motivo": str}`.
  `motivo` en `{"credencial", "juez_local_caido", ""}`. `tramos` son solo los de
  lenguaje humano (a redactar) y esta vacio si `fallo_cerrado`.

---

### Task 1: El detector determinista de secretos

**Files:**
- Create: `calipso/privacidad/__init__.py` (vacio, con un docstring de una linea)
- Create: `calipso/privacidad/detector.py`
- Test: `test_privacidad_detector.py`

**Interfaces:**
- Produces: `detectar_secretos(texto: str) -> list[dict]`, cada dict `{"texto": str, "tipo": "credencial"}`. Devuelve TODOS los secretos que reconoce (findall), o `[]`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# test_privacidad_detector.py
from calipso.privacidad.detector import detectar_secretos


def _textos(prompt):
    return {t["texto"] for t in detectar_secretos(prompt)}


def test_agarra_los_blobs_que_el_llm_deja_pasar():
    # el JWT y la api key rk_live_ que el 7b dejo pasar en la medicion
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N"
    assert jwt in _textos(f"me devuelve este bearer {jwt} y no se si expiro")
    assert "rk_live_51H8xQ2eZvKYlo2Cq9Zt7" in _textos(
        "STRIPE_KEY=rk_live_51H8xQ2eZvKYlo2Cq9Zt7\nDEBUG=true")


def test_agarra_las_otras_clases_de_secreto():
    assert detectar_secretos("ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8")   # prefijo github
    assert detectar_secretos("-----BEGIN OPENSSH PRIVATE KEY----- b3BlbnNz")  # PEM
    assert detectar_secretos("postgres://calipso:Sup3rS3cret@db.interno:5432/prod")  # conn
    assert detectar_secretos("la clave es xK9$mR2vLp8qWz4T3nB7")             # entropia, sin pista


def test_todos_son_tipo_credencial():
    for t in detectar_secretos("token ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"):
        assert t["tipo"] == "credencial"


def test_no_se_dispara_en_texto_inocente():
    # los negativos de la medicion: 'clave del exito', un SKU, password generico
    assert detectar_secretos("la clave del exito es la constancia") == []
    assert detectar_secretos("el producto SKU-4472-B no carga") == []
    assert detectar_secretos("quiero una contrasena mas segura en general") == []
    assert detectar_secretos("me explicas la diferencia entre lista y tupla?") == []
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `.venv/bin/python -m pytest test_privacidad_detector.py -q`
Expected: FAIL (`ModuleNotFoundError: calipso.privacidad.detector`)

- [ ] **Step 3: Escribir el detector**

`calipso/privacidad/__init__.py`:
```python
"""Fase 2 del ruteo: el juez de privacidad y la redaccion (librerias)."""
```

`calipso/privacidad/detector.py`:
```python
"""La capa determinista del juez de privacidad: reconoce SECRETOS de maquina
(claves, tokens, API keys) que el juez LLM deja pasar por ser blobs opacos.
Instantaneo, sin llamadas. Todo lo que marca es tipo 'credencial', y una
credencial hace fallar cerrado el prompt (nunca se redacta ni se manda tapada).

Medido en experimentos/juez_privacidad.py: cierra exactamente los huecos del 7b
(un JWT, un rk_live_) con cero falsos positivos sobre los negativos del banco.
"""
import math
import re
from collections import Counter

# Prefijos de secretos conocidos: si aparece uno, lo que sigue es una clave.
_PREFIJOS = re.compile(
    r"\b(sk-[a-z]+-|sk_live_|rk_live_|ghp_|gho_|ghs_|github_pat_|AKIA|ASIA|"
    r"AIza|xox[baprs]-|glpat-|npm_)[A-Za-z0-9_\-/]{6,}")
# Un JWT: tres bloques base64url separados por puntos, arrancando en eyJ.
_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]{6,}")
# Cabecera de clave privada PEM (con lo que le siga en la misma linea).
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[^\n]*")
# Cadena de conexion con credencial embebida: esquema://usuario:clave@host
_CONN = re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s:@/]+:[^\s:@/]+@[^\s]+")
# Tokens largos, mezclados y de alta entropia: probable secreto sin pista lexica.
_TOKEN = re.compile(r"[A-Za-z0-9_\-/+.=]{20,}")


def _entropia(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values())


def detectar_secretos(texto: str) -> list[dict]:
    """Todos los tramos de `texto` que parecen un secreto de maquina. Cada uno
    `{"texto": <literal>, "tipo": "credencial"}`. Puede haber varios."""
    vistos: set[str] = set()
    tramos: list[dict] = []

    def agregar(s: str) -> None:
        s = s.strip()
        if s and s not in vistos:
            vistos.add(s)
            tramos.append({"texto": s, "tipo": "credencial"})

    for rx in (_PREFIJOS, _JWT, _PEM, _CONN):
        for m in rx.finditer(texto):
            agregar(m.group(0))
    for tok in _TOKEN.findall(texto):
        if "@" in tok:
            continue  # los mails los marca el juez LLM como 'contacto', no aca
        if _entropia(tok) >= 3.6 and re.search(r"[a-z]", tok) and re.search(r"[0-9]", tok):
            agregar(tok)
    return tramos
```

- [ ] **Step 4: Correr y ver verde**

Run: `.venv/bin/python -m pytest test_privacidad_detector.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/privacidad/__init__.py calipso/privacidad/detector.py test_privacidad_detector.py
git commit -m "feat(privacidad): detector determinista de secretos (la capa de credenciales)"
```

---

### Task 2: El juez LLM local

**Files:**
- Create: `calipso/privacidad/juez_llm.py`
- Test: `test_privacidad_juez_llm.py`

**Interfaces:**
- Consumes: `dispatch._http_post_json`, `dispatch.CONFIG["local"]`.
- Produces: `juzgar_llm(texto: str, base_url: str | None = None, modelo: str | None = None) -> dict`, devuelve `{"tramos": list[dict], "ok": bool}`. `ok=False` si Ollama no responde o la respuesta no parsea (senal de fallo cerrado). `tramos` son `{"texto","tipo"}`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# test_privacidad_juez_llm.py
import json
from calipso.privacidad import juez_llm


def test_parsea_los_tramos_de_una_respuesta_valida(monkeypatch):
    respuesta = {"response": json.dumps(
        {"tramos": [{"texto": "3865-4421", "tipo": "contacto"},
                    {"texto": "", "tipo": "salud"}]})}
    monkeypatch.setattr(juez_llm.dispatch, "_http_post_json",
                        lambda url, payload: respuesta)
    r = juez_llm.juzgar_llm("mi numero es 3865-4421")
    assert r["ok"] is True
    # descarta el tramo con texto vacio
    assert r["tramos"] == [{"texto": "3865-4421", "tipo": "contacto"}]


def test_manda_temperatura_0_y_format_json(monkeypatch):
    capturado = {}
    def fake(url, payload):
        capturado["payload"] = payload
        return {"response": '{"tramos": []}'}
    monkeypatch.setattr(juez_llm.dispatch, "_http_post_json", fake)
    juez_llm.juzgar_llm("hola")
    assert capturado["payload"]["format"] == "json"
    assert capturado["payload"]["options"]["temperature"] == 0
    assert capturado["payload"]["stream"] is False


def test_ollama_caido_da_ok_false(monkeypatch):
    def cae(url, payload):
        raise OSError("connection refused")
    monkeypatch.setattr(juez_llm.dispatch, "_http_post_json", cae)
    r = juez_llm.juzgar_llm("cualquier cosa")
    assert r["ok"] is False
    assert r["tramos"] == []


def test_respuesta_no_json_da_ok_false(monkeypatch):
    monkeypatch.setattr(juez_llm.dispatch, "_http_post_json",
                        lambda url, payload: {"response": "no soy json {{"})
    r = juez_llm.juzgar_llm("cualquier cosa")
    assert r["ok"] is False
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `.venv/bin/python -m pytest test_privacidad_juez_llm.py -q`
Expected: FAIL (`ModuleNotFoundError` / `AttributeError`)

- [ ] **Step 3: Escribir el juez LLM**

`calipso/privacidad/juez_llm.py`:
```python
"""La capa de lenguaje humano del juez de privacidad: una llamada al modelo
local (Ollama) que marca datos sensibles que ningun regex agarra (nombres,
direcciones, telefonos, condiciones de salud, DNI en contexto).

Corre LOCAL: el texto a juzgar nunca sale de la maquina. Temperatura 0 (fiabilidad
sobre creatividad) y `format: json` para una salida parseable. Si Ollama no
responde o devuelve basura, `ok=False`: sin poder verificar, el llamador falla
cerrado -- no se manda nada a la nube.
"""
import json

import dispatch

_TIPOS = ("identidad", "credencial", "salud", "ubicacion", "financiero", "contacto")

# El prompt validado en experimentos/juez_privacidad.py (seccion 10 del spec).
JUEZ_SISTEMA = """\
Sos un filtro de privacidad local. Recibis el mensaje de un usuario y marcas
que trozos contienen datos personales sensibles, para taparlos antes de que el
mensaje salga de la maquina. Trabajas local justamente para que estos datos no
salgan.

Marca un trozo si es alguno de estos tipos:
- identidad: DNI, cedula, pasaporte, numero de identificacion, nombre completo
  de una persona real junto a otro dato que la identifique.
- credencial: contrasena, clave, token, API key, clave SSH/privada, secreto,
  cadena de conexion con clave. Estos NUNCA pueden salir.
- salud: diagnostico, enfermedad, medicamento recetado, resultado de estudio,
  condicion fisica o mental, discapacidad, embarazo.
- ubicacion: direccion de domicilio, coordenadas, un lugar preciso donde vive
  o esta la persona.
- financiero: numero de tarjeta, cuenta bancaria, CBU/IBAN, salario, ingreso.
- contacto: telefono, email, usuario de contacto directo.

Reglas:
- Copia el trozo TAL CUAL aparece en el mensaje, sin reformular ni recortar de
  mas. Debe poder encontrarse por busqueda exacta en el texto.
- Ante la duda entre marcar o no una credencial o un dato de salud, MARCALO.
  Dejar pasar una clave o una condicion de salud es el peor error.
- No marques palabras genericas que no son un dato concreto ("mi contrasena es
  segura" no tiene contrasena; "la clave del exito" no es una credencial).
- Si no hay ningun dato sensible, devolve la lista vacia.

Devolve SOLO un JSON con esta forma exacta:
{"tramos": [{"texto": "<el trozo literal>", "tipo": "<uno de los seis>"}]}

Ejemplo de formato (solo para la forma, no para que categorias buscar):
Mensaje: "escribime al 11-2233-4455 cuando puedas"
Salida: {"tramos": [{"texto": "11-2233-4455", "tipo": "contacto"}]}
"""


def juzgar_llm(texto: str, base_url: str | None = None,
               modelo: str | None = None) -> dict:
    """Marca los tramos sensibles de `texto` con el modelo local. Devuelve
    {"tramos": [...], "ok": bool}. ok=False si el modelo no responde o su
    salida no parsea -- el llamador lo trata como fallo cerrado."""
    cfg = dispatch.CONFIG["local"]
    payload = {
        "model": modelo or cfg["model"],
        "system": JUEZ_SISTEMA,
        "prompt": texto,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0, "num_ctx": 4096},
    }
    try:
        data = dispatch._http_post_json(base_url or cfg["base_url"], payload)
        obj = json.loads(data.get("response", ""))
    except (OSError, ValueError, json.JSONDecodeError):
        return {"tramos": [], "ok": False}
    crudos = obj.get("tramos", []) if isinstance(obj, dict) else []
    tramos = [{"texto": str(t["texto"]), "tipo": str(t.get("tipo", ""))}
              for t in crudos
              if isinstance(t, dict) and str(t.get("texto", "")).strip()]
    return {"tramos": tramos, "ok": True}
```

- [ ] **Step 4: Correr y ver verde**

Run: `.venv/bin/python -m pytest test_privacidad_juez_llm.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/privacidad/juez_llm.py test_privacidad_juez_llm.py
git commit -m "feat(privacidad): el juez LLM local (la capa de lenguaje humano)"
```

---

### Task 3: El juez de dos capas

**Files:**
- Create: `calipso/privacidad/juez.py`
- Test: `test_privacidad_juez.py`

**Interfaces:**
- Consumes: `detector.detectar_secretos`, `juez_llm.juzgar_llm`.
- Produces: `juzgar(texto: str) -> dict` = `{"tramos": list[dict], "fallo_cerrado": bool, "motivo": str}`. `tramos` son los de lenguaje humano a redactar (vacio si `fallo_cerrado`). `motivo` en `{"credencial", "juez_local_caido", ""}`.

- [ ] **Step 1: Escribir los tests que fallan**

```python
# test_privacidad_juez.py
from calipso.privacidad import juez


def _mock(monkeypatch, secretos, llm):
    monkeypatch.setattr(juez.detector, "detectar_secretos", lambda t: secretos)
    monkeypatch.setattr(juez.juez_llm, "juzgar_llm", lambda t: llm)


def test_credencial_del_detector_falla_cerrado(monkeypatch):
    _mock(monkeypatch,
          [{"texto": "ghp_xxx", "tipo": "credencial"}],
          {"tramos": [], "ok": True})
    v = juez.juzgar("subo esto ghp_xxx?")
    assert v["fallo_cerrado"] is True
    assert v["motivo"] == "credencial"
    assert v["tramos"] == []   # no se redacta una credencial: se corta


def test_credencial_que_marca_el_llm_tambien_falla_cerrado(monkeypatch):
    _mock(monkeypatch, [],
          {"tramos": [{"texto": "hunter2", "tipo": "credencial"}], "ok": True})
    v = juez.juzgar("mi pass es hunter2")
    assert v["fallo_cerrado"] is True
    assert v["motivo"] == "credencial"


def test_llm_caido_falla_cerrado(monkeypatch):
    _mock(monkeypatch, [], {"tramos": [], "ok": False})
    v = juez.juzgar("cualquier cosa")
    assert v["fallo_cerrado"] is True
    assert v["motivo"] == "juez_local_caido"


def test_lenguaje_humano_se_redacta_no_falla_cerrado(monkeypatch):
    _mock(monkeypatch, [],
          {"tramos": [{"texto": "3865-4421", "tipo": "contacto"},
                      {"texto": "lupus", "tipo": "salud"}], "ok": True})
    v = juez.juzgar("mi numero es 3865-4421 y tengo lupus")
    assert v["fallo_cerrado"] is False
    assert v["motivo"] == ""
    assert {"texto": "3865-4421", "tipo": "contacto"} in v["tramos"]
    assert {"texto": "lupus", "tipo": "salud"} in v["tramos"]


def test_sin_nada_sensible_no_falla_y_sin_tramos(monkeypatch):
    _mock(monkeypatch, [], {"tramos": [], "ok": True})
    v = juez.juzgar("me explicas las tuplas?")
    assert v == {"tramos": [], "fallo_cerrado": False, "motivo": ""}
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `.venv/bin/python -m pytest test_privacidad_juez.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Escribir el juez combinado**

`calipso/privacidad/juez.py`:
```python
"""El juez de privacidad de dos capas. Une el detector determinista (credenciales)
con el juez LLM local (lenguaje humano) en un solo veredicto.

Reglas (spec seccion 8 y 9):
- El detector corre primero (instantaneo). Si marca una credencial: FALLO CERRADO.
- Si el juez LLM no pudo verificar (ok=False): FALLO CERRADO -- sin verificar, no
  se manda nada.
- Si el LLM tambien marca algo como credencial: FALLO CERRADO.
- El resto (lenguaje humano) son los tramos a redactar antes de mandar a la nube.

Una credencial NUNCA queda en `tramos`: no se redacta, el prompt entero se corta.
"""
from calipso.privacidad import detector, juez_llm

_HUMANOS = ("identidad", "salud", "ubicacion", "financiero", "contacto")


def juzgar(texto: str) -> dict:
    """Veredicto de privacidad de `texto`.
    {"tramos": [...lenguaje humano a redactar...], "fallo_cerrado": bool,
     "motivo": "credencial" | "juez_local_caido" | ""}."""
    if detector.detectar_secretos(texto):
        return {"tramos": [], "fallo_cerrado": True, "motivo": "credencial"}

    r = juez_llm.juzgar_llm(texto)
    if not r["ok"]:
        return {"tramos": [], "fallo_cerrado": True, "motivo": "juez_local_caido"}

    if any(t["tipo"] == "credencial" for t in r["tramos"]):
        return {"tramos": [], "fallo_cerrado": True, "motivo": "credencial"}

    humanos = [t for t in r["tramos"] if t["tipo"] in _HUMANOS]
    return {"tramos": humanos, "fallo_cerrado": False, "motivo": ""}
```

- [ ] **Step 4: Correr y ver verde**

Run: `.venv/bin/python -m pytest test_privacidad_juez.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/privacidad/juez.py test_privacidad_juez.py
git commit -m "feat(privacidad): el juez de dos capas -- credencial o LLM caido es fallo cerrado"
```

---

### Task 4: La redaccion con marcadores estables

**Files:**
- Create: `calipso/privacidad/redaccion.py`
- Test: `test_privacidad_redaccion.py`

**Interfaces:**
- Produces:
  - `class MapaMarcadores` con `marcador_para(texto: str, tipo: str) -> str` (estable: el mismo `texto` da el mismo marcador siempre) y `reponer_texto(s: str) -> str`.
  - `redactar(texto: str, tramos: list[dict], mapa: MapaMarcadores) -> str`.
  - `reponer(texto: str, mapa: MapaMarcadores) -> str`.

**Nota de diseno:** los marcadores son estables **por conversacion**: un `MapaMarcadores` vive lo que dura una conversacion (quien lo crea y persiste es el parte 2). El mismo valor real recibe el mismo marcador en todos los turnos, para que la nube no pierda el hilo (spec seccion 12.3).

- [ ] **Step 1: Escribir los tests que fallan**

```python
# test_privacidad_redaccion.py
from calipso.privacidad.redaccion import MapaMarcadores, redactar, reponer


def test_redacta_y_repone_ida_y_vuelta():
    mapa = MapaMarcadores()
    tramos = [{"texto": "3865-4421", "tipo": "contacto"},
              {"texto": "Juan Perez", "tipo": "identidad"}]
    tapado = redactar("soy Juan Perez, mi numero es 3865-4421", tramos, mapa)
    assert "3865-4421" not in tapado
    assert "Juan Perez" not in tapado
    assert "[CONTACTO_1]" in tapado
    assert "[ID_1]" in tapado
    # la respuesta de la nube, con los marcadores, se repone al valor real
    assert reponer("te llamo al [CONTACTO_1], [ID_1]", mapa) == "te llamo al 3865-4421, Juan Perez"


def test_marcador_estable_entre_turnos():
    mapa = MapaMarcadores()
    m1 = mapa.marcador_para("3865-4421", "contacto")
    m2 = mapa.marcador_para("3865-4421", "contacto")   # mismo valor, otro turno
    assert m1 == m2 == "[CONTACTO_1]"
    otro = mapa.marcador_para("11-9999", "contacto")   # valor distinto
    assert otro == "[CONTACTO_2]"


def test_dos_valores_distinto_tipo_numeran_por_tipo():
    mapa = MapaMarcadores()
    assert mapa.marcador_para("Ana", "identidad") == "[ID_1]"
    assert mapa.marcador_para("Belgrano 1234", "ubicacion") == "[LUGAR_1]"


def test_redacta_los_tramos_largos_primero():
    # si un tramo es subcadena de otro, tapar el mas largo primero evita
    # dejar un pedazo del corto suelto adentro del largo
    mapa = MapaMarcadores()
    tramos = [{"texto": "Ana", "tipo": "identidad"},
              {"texto": "Ana Gomez", "tipo": "identidad"}]
    tapado = redactar("firma Ana Gomez", tramos, mapa)
    assert "Ana" not in tapado
    assert tapado == "firma [ID_1]"
```

- [ ] **Step 2: Correr y ver que fallan**

Run: `.venv/bin/python -m pytest test_privacidad_redaccion.py -q`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Escribir la redaccion**

`calipso/privacidad/redaccion.py`:
```python
"""Tapar los tramos de lenguaje humano con marcadores estables antes de mandar
a la nube, y reponerlos localmente al volver. Lo sensible nunca esta en el
trafico de salida (spec seccion 9).

Los marcadores son estables por conversacion: el mismo valor real recibe el
mismo marcador en todos los turnos, para que la nube no pierda el hilo. Un
`MapaMarcadores` dura una conversacion; el parte 2 decide donde vive.

Las credenciales NO pasan por aca: fallan cerrado antes (el juez no las deja en
`tramos`).
"""
import re

# tipo del juez -> prefijo del marcador
_PREFIJO = {
    "identidad": "ID",
    "contacto": "CONTACTO",
    "salud": "SALUD",
    "ubicacion": "LUGAR",
    "financiero": "FINANZA",
}


class MapaMarcadores:
    """El diccionario estable de una conversacion: valor real <-> marcador."""

    def __init__(self) -> None:
        self._a_marcador: dict[str, str] = {}   # texto real -> "[TIPO_N]"
        self._a_valor: dict[str, str] = {}       # "[TIPO_N]" -> texto real
        self._conta: dict[str, int] = {}         # prefijo -> ultimo N usado

    def marcador_para(self, texto: str, tipo: str) -> str:
        if texto in self._a_marcador:
            return self._a_marcador[texto]
        prefijo = _PREFIJO.get(tipo, "DATO")
        self._conta[prefijo] = self._conta.get(prefijo, 0) + 1
        marcador = f"[{prefijo}_{self._conta[prefijo]}]"
        self._a_marcador[texto] = marcador
        self._a_valor[marcador] = texto
        return marcador

    def reponer_texto(self, s: str) -> str:
        # reemplaza cada marcador conocido por su valor real
        def sub(m: re.Match) -> str:
            return self._a_valor.get(m.group(0), m.group(0))
        return re.sub(r"\[[A-Z]+_\d+\]", sub, s)


def redactar(texto: str, tramos: list[dict], mapa: MapaMarcadores) -> str:
    """Reemplaza cada tramo por su marcador estable. Tapa los tramos mas largos
    primero: si uno es subcadena de otro, taparlo despues dejaria un pedazo del
    corto suelto adentro del largo."""
    for t in sorted(tramos, key=lambda x: len(x["texto"]), reverse=True):
        marcador = mapa.marcador_para(t["texto"], t["tipo"])
        texto = texto.replace(t["texto"], marcador)
    return texto


def reponer(texto: str, mapa: MapaMarcadores) -> str:
    """Repone los valores reales en un texto con marcadores (la respuesta de la
    nube), localmente, antes de mostrarlo."""
    return mapa.reponer_texto(texto)
```

- [ ] **Step 4: Correr y ver verde**

Run: `.venv/bin/python -m pytest test_privacidad_redaccion.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add calipso/privacidad/redaccion.py test_privacidad_redaccion.py
git commit -m "feat(privacidad): redaccion con marcadores estables por conversacion"
```

---

### Task 5: La guarda de regresion del detector

**Files:**
- Create: `test_privacidad_guarda.py`

**Interfaces:**
- Consumes: `detector.detectar_secretos`.

**Por que:** la medicion (spec seccion 10) dice que el detector es la autoridad
para credenciales, con un piso: agarra todos los blobs de maquina y no se dispara
en los negativos. El detector es deterministico, asi que ese piso SI se puede
fijar en un test rapido de pytest (a diferencia del juez LLM, que queda como
medicion manual en `experimentos/juez_privacidad.py`). Este test es la guarda:
si alguien afloja una regla del detector, se pone rojo.

- [ ] **Step 1: Escribir la guarda**

```python
# test_privacidad_guarda.py
"""Guarda de regresion del detector determinista contra un set de secretos que
DEBE agarrar y de negativos donde NO debe dispararse. La parte LLM del juez no
se testea aca (es no-deterministica y lenta): su medicion vive en
experimentos/juez_privacidad.py. Esto fija el piso de la capa que si es fija."""
import pytest
from calipso.privacidad.detector import detectar_secretos

# secretos de maquina: cada uno tiene que salir marcado
SECRETOS = [
    "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "-----BEGIN OPENSSH PRIVATE KEY----- b3BlbnNzaC1rZXktdjEAAAAABG5vbmU",
    "7645123456:AAFhSj2kL9mNpQrStUvWxYz0123456789ab",
    "postgres://calipso:Sup3rS3cret@db.interno:5432/prod",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J",
    "sk-proj-Abc123XyZ456Def789Ghi012Jkl345Mno678",
    "ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
    "rk_live_51H8xQ2eZvKYlo2Cq9Zt7",
    "xK9$mR2vLp8qWz4T3nB7",
]

# texto inocente: el detector NO se puede disparar
NEGATIVOS = [
    "la clave del exito es la constancia",
    "quiero una contrasena mas segura en general",
    "el producto SKU-4472-B del catalogo no carga",
    "me explicas la diferencia entre una lista y una tupla?",
    "el evento es el 03/07/2027, armame la agenda",
    "en general que habitos mejoran la salud del corazon?",
]


@pytest.mark.parametrize("s", SECRETOS)
def test_el_detector_agarra_todo_secreto(s):
    assert detectar_secretos(s), f"el detector dejo pasar un secreto: {s!r}"


@pytest.mark.parametrize("s", NEGATIVOS)
def test_el_detector_no_se_dispara_en_inocente(s):
    assert detectar_secretos(s) == [], f"falso positivo del detector en: {s!r}"
```

- [ ] **Step 2: Correr y ver verde (el detector de la T1 ya existe)**

Run: `.venv/bin/python -m pytest test_privacidad_guarda.py -q`
Expected: PASS (si algun caso falla, es un hueco real del detector -- arreglar `detector.py`, no el test)

- [ ] **Step 3: Correr toda la suite de privacidad junta**

Run: `.venv/bin/python -m pytest test_privacidad_detector.py test_privacidad_juez_llm.py test_privacidad_juez.py test_privacidad_redaccion.py test_privacidad_guarda.py -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add test_privacidad_guarda.py
git commit -m "test(privacidad): guarda de regresion del detector contra el banco"
```

---

## Lo que este plan NO hace (es el parte 2)

- **Cablear el juez al camino vivo** (`server.py`, `_decide`, el reemplazo de `dispatch.PRIVATE`, correr el juez solo en el camino a la nube, reponer en la respuesta). Es lo mas riesgoso -- toca la ruta de privacidad viva -- y arranca cuando el parte 1 este probado.
- **La UI del degradado avisado** (mostrar en `/fabrica` que se tapo y que viaja, antes de mandar).
- **Mantener el modelo caliente** (el desperdicio de recarga fria que midio la seccion 10). Es una decision de cableado/config del parte 2.
- **Los adjuntos** (juzgar el texto de un adjunto). Spec seccion 12.1, parte 2 o despues.
- **Tocar `dispatch.PRIVATE` o el jefe de un departamento.**

## Nota de verificacion final

Al terminar las cinco tareas: la suite entera verde, y las cuatro librerias
existen y se prueban solas, sin tocar `server.py` ni la UI. El detector pasa su
guarda; el juez combina bien las dos capas con fallo cerrado en credencial y en
LLM caido; la redaccion tapa y repone con marcadores estables. La medicion
completa (`experimentos/juez_privacidad.py`) sigue siendo la guarda del juez LLM,
corrida a mano. Nada de esto cambia el comportamiento del chat todavia -- eso es
el parte 2.
