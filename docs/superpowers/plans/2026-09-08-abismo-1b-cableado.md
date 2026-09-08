# El abismo 1b -- el cableado de la consulta al chat vivo (local, API, suscripcion y /nube): plan de implementacion

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que Calipso, a mitad de una respuesta del chat, pueda pedirle un dato al abismo con la marca `⟦abismo:FUENTE RESTO⟧`, que el server la retire del texto, pesque (100% local), la deje viajar solo por la etapa de viaje cuando el turno es /nube, y reentre al modelo para que siga en la MISMA burbuja -- con el pondering visible en las dos UIs y en el pulso, sin que la marca ni el bloque pescado se persistan jamas.

**Architecture:** El paquete puro `calipso/abismo/` (ya en main desde el 1a) gana tres modulos nuevos, todos sin I/O: `filtro.py` (el filtro de streaming, hermano del de foco, que corta en la primera marca valida), `viaje.py` (anillos -> juez -> redaccion, transparente en local) y `turno.py` (el estado del turno, el prompt de la reentrada, la senal y el detector one-shot). El cableado vive en `calipso/server.py`: el `Emisor` compone una lista ordenada de filtros (foco primero, abismo despues) y expone la marca hacia arriba; el bucle de streaming de `ws_chat` se envuelve en un bucle exterior que corta el generador, pesca en hilo y reinvoca `_chunks_for` con el system base mas los bloques; la ruta de suscripcion detecta sobre el texto entero y reinvoca el CLI; /nube pasa el bloque por el viaje y devuelve a la nube los tramos CRUDOS. Todo lo que esta fuera del bucle exterior (chats.append, mem.remember, _cobrar_turno, cost, done) corre una vez por turno: los catorce salteos de la pasada sintetica salen gratis por construccion.

**Tech Stack:** Python 3 + pytest en la raiz del repo (`fastapi.testclient.TestClient` con `websocket_connect("/ws/chat")` y un generador espia en lugar de Ollama), JavaScript puro con `node --test` para `calipso/web/fabrica/`, `node --check` via `test_ui.py` para la PWA. Sin dependencias nuevas.

**Spec:** `docs/superpowers/specs/2026-09-07-abismo-consulta-design.md` (autoridad; enmendado el 2026-09-08 con la seccion 8, /nube con etapa de viaje). Guia del controlador con los rulings que este plan implementa: la seccion "Rulings" de abajo los repite en una linea cada uno.

## Global Constraints

- SIN EMOJIS en codigo, tests, docs y salidas.
- NUNCA importar calipso fuera de pytest sin `CALIPSO_HOME` a un temporal ANTES del import.
- Suite completa antes de CADA commit verificando el EXIT CODE: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?` (linea base en main hoy: 1374 passed, 4 warnings preexistentes). Si se toca `calipso/web/`, tambien `node --test` desde `calipso/web/fabrica/` (Node: `~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node`, el directorio como cwd; linea base 401 pass). Un modulo JS nuevo entra al SHELL de `calipso/web/sw.js` (lo exige test_mapa_server).
- `git add` con rutas explicitas. Anclas por SIMBOLO en server.py (las lineas se corren entre merges).
- Constantes del spec, verbatim: `ABISMO_BLOQUE_MAX = 2000`; `marca.MAX_PREGUNTA = 160`; `marca.PATRON` cierra el cuerpo en 400 (el filtro RETIENE `len("⟦abismo:") + 400 + 1` y decide con `marca.parsear`, no con 160: retener 160 dejaria escapar cruda una marca de 200); tope `ABISMO_CONSULTAS_MAX = 3` por turno; `contrato.INDICE_MAX = 600`; la LETRA medida de `contrato.bloque_contrato` (las siete lineas de `_armar` con nombres y la variante `()`) NO se cambia; la cola honesta del `elif extra:` nacio en el review del 1a DESPUES de la medicion y la Task 12 la acorta para que el cierre entre siempre; senal `{type:"abismo", fase:"pondering"|"pescado"|"fallo", fuente, ...}` con `verbo` en pondering, `tamano` + `viaje` en pescado (`{destino:"local"}` o `{destino:"nube", tapados:[{marcador,tipo}], texto_tapado}`), `motivo` en fallo (`vacio` | `credencial` | `solo_hondo` | `juez_local_caido` | `tipo_desconocido` | `error`); `num_ctx` del chat local = 8192 (constante `CHAT_NUM_CTX`, el mismo valor que `_pensar_local`).
- La marca JAMAS se persiste (chats.json, output.txt/partial-output.txt de jobs, memoria, telemetry con el texto). El bloque pescado JAMAS se persiste. Un solo `done` por turno; un solo par user/assistant.
- Fallo cerrado en todo: cualquier excepcion de la consulta degrada a seguir sin contexto, con senal `fallo` y `telemetry.log_event("abismo", ...)`.
- Ritual de cierre de rama: smoke en vivo con server desechable + ronda adversaria antes del merge (es lo que cazo bugs reales en la capa de sesion; ver `docs/superpowers/2026-09-08-cierre-capa-de-sesion/`).

## Rulings del controlador (una linea cada uno; el detalle vive en cada task)

1. `calipso/abismo/filtro.py` con `FiltroAbismo(puede_cortar)`: `comer`, `cerrar` (descarta con aviso, jamas vuelca), `tomar_marca`. Copia la idea de `mapa/foco.py`, no la clase.
2. `Emisor` compone `filtros: list` (foco primero, abismo despues); `chunk` encadena `comer`; `cerrar` encadena; `marca_abismo()` delega. El borrador `Emisor(ws)` NO recibe el filtro del abismo.
3. `calipso/abismo/turno.py`: `EstadoTurno` (consultas, bloques, tramos, tramos_crudos, sintetica, reset), `prompt_reentrada`, `senal`. El estado se declara junto al estado de conexion y se resetea SOLO cuando entra un mensaje real de Pedro (la linea `user_msg = user_msg.strip()` cubre paquete y steer).
4. La reentrada en local/API envuelve el bucle de streaming en un `while True` exterior; el corte del generador va DESPUES de `emisor.chunk` y ANTES de la proxima `to_thread(_next_or_stop)`; el steer gana y se chequea PRIMERO en cada vuelta, y `_pescar_abismo` mira el inbox al volver de la pesca: si hay steer, cierra en `fallo` y el bloque no entra al estado (spec seccion 10).
5. Suscripcion one-shot: `marca` sobre el texto entero, la primera valida corta, reinvocacion real del CLI (dos invocaciones, declaradas), preview congelado via `congelar`, `_limpiar_marcas` suma `marca.PATRON` y limpia los artefactos de jobs. Un `/stop` durante el CLI ni pesca ni reinvoca. Orquestador: retiro con aviso (`_retirar_con_aviso` + `_limpiar_marcas`), sin corte.
6. /nube: `destino = "nube" if a_la_nube_tapado else "local"`, `mapa = conversacion.mapa_para(chat_id)`, system base `_sistema_nube()`, `tramos_crudos` = lo que escribio la nube antes de `reponer`. El bloque entra SOLO por `prompt_reentrada`.
7. Contrato en local: `prompt_compiler.internal_contract` suma `contrato.bloque_contrato(nombres)` como bloque final de "Contrato interno"; no se re-mide.
8. `viaje.preparar_viaje(bloques, destino, mapa) -> {"estado","texto","tapados","motivo"}`; `anillos.puede_viajar("nube")` real.
9. Zona y consolidado los fabrica el server: prefijo `personal:` del departamento; `LibroPersonal.resumen()` solo en zona personal.
10. Task 1 = el harness (`test_abismo_chat.py`) que todo lo posterior reusa.
11. UIs: renglon hermano de "pensando", nunca un turno; cierre garantizado en el cliente. `sw.js` CACHE a v4.
12. Pulso: `EVENTOS` y `CONOCIDOS` juntos, con test que acople las dos listas.
13. Minors del 1a al final. 14. Task final: smoke + ronda adversaria + merge.

## Mapa de lineas (spec -> hoy, main `5502823`; anclar siempre por simbolo)

| Que | Hoy | Simbolo |
|---|---|---|
| estado de conexion de `ws_chat` | `calipso/server.py:3176-3183` | `pending = None` ... `departamento = None` |
| reset del turno (paquete o steer) | `:3209` | `user_msg = user_msg.strip()` |
| `chats.append("user")` / `thinking` / `goals.detect` | `:3222` / `:3228` / `:3230` | |
| `_decide` en hilo | `:3257-3258` | `verdict, features, ranked, directives = await asyncio.to_thread(` |
| borrador `Emisor(ws)` | `:3310` | `emisor_b = Emisor(ws)` |
| compuerta /nube | `:3373-3416` | `nube_local = False` ... `chat_id_nube = None` |
| `Emisor` del turno | `:3428-3429` | `agente_id = "chat:" + uuid...` / `emisor = Emisor(ws, agente_id=agente_id)` |
| system compilado + `a_la_nube_tapado` | `:3473-3475` | `a_la_nube_tapado = bool(directives.get("nube")) and route != "local"` |
| append post-compile | `:3498-3503` | `if attachment_context and not a_la_nube_tapado:` |
| rama orquestador / suscripcion / local-api | `:3509-3532` / `:3533-3543` / `:3544-3562` | `if _should_orchestrate(` / `elif route == "subscription":` / `else:` + `gen, model = _chunks_for(route, ...` |
| fallback entre suscripciones / a local | `:3565-3616` / `:3621-3665` | `alternate = _best_subscription_client(` / `used_route, usage = "local", {}` |
| `emisor.cerrar()` | `:3673` | `full += await emisor.cerrar()` |
| `_cobrar_turno` / `cost` / pulso `fin` / `chat_turn` | `:3685-3687` / `:3688` / `:3696` / `:3701-3721` | |
| `mem.remember` / `chats.append("assistant")` / `done` | `:3744-3751` / `:3753` / `:3774` | |
| `_SISTEMA_NUBE_MINIMO` / `_sistema_del_turno` | `:2704-2711` / `:2714-2722` | |
| `_HISTORY_TURNS` / `_history_messages` / `_chunks_for` / payload local | `:2774` / `:2777` / `:2799` / `:2841` | `payload = {"model": mdl, "messages": messages, "stream": True}` |
| `_run_subscription_text_live` / preview / `jobs.event` del preview / artefactos | `:2956` / `:3011-3020` / `:3021-3024` / `:3048, :3074, :3089` | `if now - last_notice >= 2:` ... `"hint"` / `jobs.event(str(ROOT), job["id"], "running",` / `jobs.write_artifact(...)` |
| los tres `return` del `/stop` / el `msg` del `returncode != 0` | `:3052-3055` / `:3066` | `return partial + "\n\n...(proceso interrumpido)", None` / `msg = (stderr or partial or "").strip()` |
| `_run_dynamic_team`: `queued_msg` de los agentes y de la sintesis / el retiro de marcas de un agente | `:2481` / `:2536` / `:2505` | `queued_msg = queued_msg or queued` / `mango.razonando(_limpiar_marcas(output))` |
| `test_privacidad_nube_system.py`: la asercion del system minimo | `test_privacidad_nube_system.py:17-19` | `assert resultado == srv._SISTEMA_NUBE_MINIMO` |
| imports condicionales del mapa y el pulso | `:6663-6674` / `:6680-6685` | `from calipso.mapa import foco as _mapa_foco` |
| `Emisor` / `_limpiar_marcas` | `:7110-7156` / `:7159-7164` | `class Emisor:` / `def _limpiar_marcas` |
| `mem` global / `_repo_brief` / `_ECO_BASE` / `_eco_personal` | `:1998` / `:2618` / `:4692` / `:4681` (bloque `except` de la economia) | |
| `internal_contract` / `context_sections` | `calipso/prompt_compiler.py:62-89` / `:194-235` | |
| `catastro.cargar` / `obtener` | `calipso/catastro.py:482` / `:496` | |
| `EVENTOS` / `publicar` | `calipso/mapa/pulso.py:22-23` / `:139-141` | |
| `CONOCIDOS` / rama `foco` | `calipso/web/fabrica/pulso.js:35-36` / `:57-61` | |
| PWA: `onmessage`, `steered`, `chunk`, `error`, `done`, `onclose`, `renderHistory`, `startThinking` | `calipso/web/index.html:2255`, `:2355`, `:2357`, `:2406`, `:2408`, `:2418`, `:2172`, `:2435-2450` | `ws.onclose = () => { addMsg("meta", "desconectado, reintentando..."); setTimeout(connect, 1500); };` |
| fabrica: `estadoInicial`, `EVENTOS_DEL_STREAM`, `aplicarEvento`, `case "thinking"`, `cargar` | `calipso/web/fabrica/chat.js:10-14`, `:37-38`, `:40-99`, `:54-56`, `:151-158` | |
| fabrica: `conversacion`, `pintarConversacion`, callback de `crearChat`, timers | `calipso/web/fabrica/app.js:1063`, `:1081-1104`, `:1106-1123`, `:1210-1225` | |

## Orden de tasks y desvios del orden sugerido (con su razon)

Se sigue el orden de la guia (1..13) con dos desvios:

- El minor "PATRON que traga `⟦` anidado" se hace en la **Task 2** y no en la 12: el mapa del filtro (seccion 7.4) exige que el filtro y `marca.PATRON` juzguen igual que es una marca, y el test de coherencia de la Task 2 no puede pasar con la regex de hoy.
- El bump de `sw.js` a `calipso-shell-v4` va en la **Task 10** (la primera que toca archivos precacheados) y la Task 11 no vuelve a subirlo: las dos aterrizan en el mismo merge.
- Los imports de `calipso.abismo` en `server.py` van SIN try/except, al lado de los de `calipso.privacidad` (`server.py:81-82`, que ya entran sin guarda): son paquete de primera clase, no un subsistema opcional como el mapa. El mapa del filtro (2.1) sugeria guardarlos; el precedente de privacidad pesa mas y evita `if ... is not None` en el bucle.

Rama de trabajo: `feat/abismo-1b` desde main, en la raiz del repo (sin worktree: el harness bloquea git desde un worktree, memoria del proyecto). Cada task termina en un commit; la Task 13 mergea con `--no-ff`.

---

### Task 1: El harness de `ws_chat` con modelo falso + `num_ctx` explicito en la ruta local

**Files:**
- Create: `test_abismo_chat.py`
- Modify: `calipso/server.py:2774` (bajo `_HISTORY_TURNS = 12`: nueva constante `CHAT_NUM_CTX`)
- Modify: `calipso/server.py:2841` (`payload = {"model": mdl, "messages": messages, "stream": True}` en `_chunks_for`)
- Test: `test_abismo_chat.py`

**Interfaces:**
- Consumes: `srv.app`, `srv.COOKIE`, `srv.TOKEN` (`calipso/server.py:128`, `:212`), `srv._es_loopback` acepta el host `"testclient"` (`:281-286`), `chats.create/append/get` (`calipso/chats.py:80,100,55`), `capabilities.parse_directives` (`calipso/capabilities.py:199`), `dispatch._ollama_chat_chunks(url, payload, usage=None)` (`dispatch.py:465`).
- Produces: `CHAT_NUM_CTX = 8192` en `calipso/server.py`; el payload local lleva `"options": {"num_ctx": CHAT_NUM_CTX}`. En `test_abismo_chat.py`: `MemoriaFalsa`, `ModeloEspia(guiones)` (callable `(url, payload, *resto)` que devuelve un generador y anota `llamadas: list[dict]`), `_decide_local(user_msg, last_features=None, last_verdict=None)`, `Harness` con `turno(texto, departamento=None, hasta_dones=1) -> list[dict]`, `recibir(ws, hasta_dones=1)`, `paquete(texto, departamento=None) -> str`, `mensajes() -> list[dict]`, `telemetria(kind=None) -> list[dict]`; helpers `de_tipo(eventos, tipo)`, `texto_visible(eventos)`; fixture `chat` (atributos `cliente`, `chat_id`, `modelo`, `memoria`, `pulso`, `tmp`; deja `catastro.obtener` en `lambda nombre: None` para que ninguna marca `proyecto` escanee el home real). Todas las tasks de cableado (6, 7, 8, 9) importan esto. Ojo con `ModeloEspia`: elige el guion por el indice GLOBAL de `llamadas`, que NO se vacia entre turnos (el test del steer de la Task 6 cuenta las llamadas de dos turnos seguidos); un test que encadena turnos con guiones nuevos hace `chat.modelo.llamadas.clear()` antes de cada uno.

- [ ] **Step 1: Crear la rama**

```bash
cd /var/home/pedro/calipso && git checkout main && git pull --ff-only && git checkout -b feat/abismo-1b
```

- [ ] **Step 2: Escribir el harness y los dos primeros tests (en rojo)**

```python
# test_abismo_chat.py
"""El molde que faltaba: `ws_chat` de punta a punta con un modelo local FALSO
y el socket real del TestClient (spec seccion 15).

Nada de esto toca la red ni el home real: el home lo aisla conftest.py y cada
test ademas monkeypatchea las constantes YA CONGELADAS (chats.CHAT_FILE,
telemetry.LEDGER, _ECO_BASE) hacia tmp_path. El modelo es un generador espia
que sigue un guion por invocacion y anota cada payload; el ruteo se fuerza a
local con un `_decide` falso que conserva el parseo REAL de las directivas,
asi `/nube`, `/api` y `/claude` siguen significando lo mismo que en
produccion. El system compilado se reemplaza por una constante (recall,
economia bajo candado y catastro no son lo que se prueba aca), pero
`_sistema_del_turno` sigue siendo el real: la compuerta /nube se ejercita.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso import chats
from calipso.mapa import pulso as p


class MemoriaFalsa:
    """Doble de `Memory`: lo que el turno usa (recall, load_core, remember)."""

    def __init__(self, core: str = ""):
        self.core = core
        self.recordado: list[str] = []

    def recall(self, query, n=5, ambitos=None):
        return []

    def load_core(self):
        return self.core

    def remember(self, text, scope="auto", **meta):
        self.recordado.append(text)
        return "id-falso"


class ModeloEspia:
    """El modelo falso de las rutas local (`_ollama_chat_chunks(url, payload,
    usage)`) y api (`_sse_text_chunks(url, payload, headers, usage)`): en las
    dos, el ultimo posicional es el `usage` mutable. `guiones[i]` es la lista
    de trozos de la invocacion numero i (la ultima se repite si hay mas
    invocaciones que guiones). Anota cada payload en `llamadas`: ahi se lee
    el system, los messages y las options de cada pasada."""

    def __init__(self, guiones):
        self.guiones = [list(g) for g in guiones]
        self.llamadas: list[dict] = []

    def __call__(self, url, payload, *resto):
        usage = resto[-1] if resto else None
        self.llamadas.append(payload)
        trozos = self.guiones[min(len(self.llamadas) - 1, len(self.guiones) - 1)]

        def _gen():
            for t in trozos:
                yield t
            if isinstance(usage, dict):
                usage["prompt_tokens"] = 10
                usage["completion_tokens"] = len(trozos)
        return _gen()


def _decide_local(user_msg, last_features=None, last_verdict=None):
    """`_decide` sin probes ni ranking: ruta local salvo que Pedro fuerce otra
    con un slash (`/api`, `/claude`). Las directivas se parsean con el parser
    REAL, que es lo que hace que `/nube` siga siendo `/nube`."""
    d = srv.capabilities.parse_directives(user_msg)
    route = d.get("force_route") or "local"
    client = d.get("force_model") if route == "subscription" else None
    verdict = {"route": route, "client": client, "model": "modelo-falso",
               "model_id": f"{route}:modelo-falso", "persona": "Epicteto",
               "tier": "small", "effort": 1, "effort_name": "balanced",
               "session": "s", "source": "harness", "why": "harness"}
    features = {"type": "chat", "complexity": 1, "needs_repo": False,
                "needs_web": False, "private": False}
    return verdict, features, [], d


class Harness:
    def __init__(self, cliente, chat_id, modelo, memoria, pulso, tmp):
        self.cliente = cliente
        self.chat_id = chat_id
        self.modelo = modelo
        self.memoria = memoria
        self.pulso = pulso
        self.tmp = tmp

    def paquete(self, texto, departamento=None):
        paquete = {"text": texto, "chat_id": self.chat_id}
        if departamento:
            paquete["departamento"] = departamento
        return json.dumps(paquete)

    def turno(self, texto, departamento=None, hasta_dones=1):
        """Manda un paquete real y junta todo lo que el server emite hasta el
        `done` numero `hasta_dones` (2 cuando un steer encola otro turno)."""
        with self.cliente.websocket_connect("/ws/chat") as ws:
            ws.send_text(self.paquete(texto, departamento))
            return self.recibir(ws, hasta_dones)

    @staticmethod
    def recibir(ws, hasta_dones=1):
        eventos, dones = [], 0
        while dones < hasta_dones:
            ev = ws.receive_json()
            eventos.append(ev)
            if ev.get("type") == "done":
                dones += 1
        return eventos

    def mensajes(self):
        return chats.get(self.chat_id)["messages"]

    def telemetria(self, kind=None):
        ruta = self.tmp / "telemetry.jsonl"
        if not ruta.exists():
            return []
        filas = [json.loads(linea) for linea in
                 ruta.read_text(encoding="utf-8").splitlines() if linea.strip()]
        return [f for f in filas if kind is None or f.get("kind") == kind]


def de_tipo(eventos, tipo):
    return [e for e in eventos if e.get("type") == tipo]


def texto_visible(eventos):
    return "".join(e["text"] for e in de_tipo(eventos, "chunk"))


@pytest.fixture
def chat(tmp_path, monkeypatch):
    monkeypatch.setattr(chats, "CHAT_FILE", tmp_path / "chats.json")
    monkeypatch.setattr(srv.telemetry, "LEDGER", tmp_path / "telemetry.jsonl")
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    memoria = MemoriaFalsa()
    monkeypatch.setattr(srv, "mem", memoria)
    pu = p.Pulso()
    monkeypatch.setattr(srv, "EL_PULSO", pu)
    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: True)
    monkeypatch.setattr(srv, "_decide", _decide_local)
    monkeypatch.setattr(srv, "_build_context",
                        lambda user_msg, runtime, features=None: "SISTEMA BASE")
    monkeypatch.setattr(srv, "_harness_context", lambda *a, **k: "estado")
    monkeypatch.setattr(srv, "_extract_edit_target", lambda *a, **k: None)
    # la fuente `proyecto` recibe `catastro.obtener`, que sin catastro.json
    # en el home de la suite ESCANEA el home real de Pedro (`cargar()` ->
    # `escanear()` sobre `Path.home()`): cerrado aca para todo el harness;
    # los tests de esa fuente inyectan el suyo
    monkeypatch.setattr(srv.catastro, "obtener", lambda nombre: None)
    monkeypatch.setattr(srv.goals, "active", lambda raiz: None)
    monkeypatch.setattr(srv.goals, "detect", lambda texto: None)
    modelo = ModeloEspia([["hola ", "Pedro"]])
    monkeypatch.setattr(srv.dispatch, "_ollama_chat_chunks", modelo)
    monkeypatch.setattr(srv.dispatch, "_sse_text_chunks", modelo)
    creado = chats.create(str(srv.ROOT), "prueba")
    cliente = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})
    return Harness(cliente, creado["id"], modelo, memoria, pu, tmp_path)


def test_un_turno_plano_da_thinking_chunks_y_un_solo_done(chat):
    eventos = chat.turno("hola")
    tipos = [e["type"] for e in eventos]
    assert tipos[0] == "thinking"
    assert texto_visible(eventos) == "hola Pedro"
    assert tipos.count("done") == 1 and tipos[-1] == "done"
    assert len(chat.modelo.llamadas) == 1
    # el par user/assistant queda escrito una sola vez, y la memoria tambien
    assert [(m["role"], m["text"]) for m in chat.mensajes()] == [
        ("user", "hola"), ("assistant", "hola Pedro")]
    assert len(chat.memoria.recordado) == 1


def test_la_llamada_local_del_chat_fija_num_ctx(chat):
    """La leccion de la medicion del jefe (spec seccion 4): Ollama trunca
    desde el COMIENZO y sin `num_ctx` explicito la reentrada con 6000 chars
    de bloques se comeria el system con el contrato, en silencio."""
    chat.turno("hola")
    payload = chat.modelo.llamadas[0]
    assert payload["options"]["num_ctx"] == srv.CHAT_NUM_CTX == 8192
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][-1] == {"role": "user", "content": "hola"}
```

- [ ] **Step 3: Correrlos para verlos fallar**

Run: `.venv/bin/python -m pytest -q test_abismo_chat.py`
Expected: `1 passed, 1 failed` -- el primero pasa (el harness ya habla con `ws_chat` real), el segundo falla con `KeyError: 'options'` (o `AttributeError: module 'calipso.server' has no attribute 'CHAT_NUM_CTX'`). Si el primero NO pasa, el harness esta mal montado y hay que arreglarlo antes de seguir: es la pieza que todo lo demas reusa.

- [ ] **Step 4: La constante y el payload**

En `calipso/server.py`, debajo de `_HISTORY_TURNS = 12  # max mensajes del historial (6 intercambios)` (`:2774`):

```python
# `num_ctx` explicito en la llamada local del chat (spec del abismo,
# seccion 4, presupuesto de contexto). El mismo valor que `_pensar_local`
# y por la misma razon: Ollama trunca desde el COMIENZO del prompt, y con el
# default (2048 en la mayoria de los builds) una reentrada con hasta tres
# bloques del abismo mas el parcial dejaria de ver justo el system con el
# contrato, en silencio. 8192 es holgura, no capacidad: cada token de
# contexto cuesta RAM en la Ally.
CHAT_NUM_CTX = 8192
```

Y en `_chunks_for`, la linea `payload = {"model": mdl, "messages": messages, "stream": True}` (`:2841`) pasa a:

```python
    payload = {"model": mdl, "messages": messages, "stream": True,
               "options": {"num_ctx": CHAT_NUM_CTX}}
```

- [ ] **Step 5: Verde y suite completa**

Run: `.venv/bin/python -m pytest -q test_abismo_chat.py`
Expected: `2 passed`

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
Expected: `1376 passed, 4 warnings` y `EXIT=0` (`test_plantel_server.py:734` sigue en verde: mira `messages`, no `options`).

- [ ] **Step 6: Commit**

```bash
git add test_abismo_chat.py calipso/server.py
git commit -m "test(abismo): harness de ws_chat con modelo falso y socket real; feat: num_ctx explicito (CHAT_NUM_CTX=8192) en la ruta local del chat"
```

Riesgos anotados por los mapas: `_decide` real corre probes sincronos y `_harness_context` sondea Claude/Codex/LiteLLM -- los dos van patcheados o el harness tarda y toca la red. `srv.mem` se pasa por VALOR al resolver (mapa de dependencias 1.3): el monkeypatch del global alcanza porque `ws_chat` lo lee del modulo en cada uso.

---

### Task 2: `FiltroAbismo` + `Emisor` compuesto + `_limpiar_marcas` (y el `PATRON` sin corchete anidado)

**Files:**
- Create: `calipso/abismo/filtro.py`
- Modify: `calipso/abismo/marca.py:21-22` (`PATRON`)
- Modify: `calipso/server.py:81-82` (imports de `calipso.privacidad`: se suman los del abismo al lado)
- Modify: `calipso/server.py:7110-7156` (`class Emisor`) y `:7159-7164` (`_limpiar_marcas`)
- Test: `test_abismo_filtro.py` (nuevo), `test_abismo_marca.py` (un test mas)

**Interfaces:**
- Consumes: `marca.ABRE`, `marca.CIERRA`, `marca.PATRON`, `marca.parsear`, `marca.Marca` (`calipso/abismo/marca.py`); `foco.Filtro` (`calipso/mapa/foco.py:30-78`); `telemetry.log_event(kind, **data)` (`calipso/telemetry.py:14`).
- Produces: `calipso/abismo/filtro.py`: `ABRE = "⟦abismo:"`, `CIERRA = "⟧"`, `CUERPO_MAX = 400`, `RETENCION_MAX = len(ABRE) + CUERPO_MAX + 1`; `class FiltroAbismo(puede_cortar: Callable[[], bool] = lambda: True)` con `comer(trozo: str) -> str`, `cerrar() -> str` (una marca ABIERTA -lo retenido empieza con `⟦abismo:`- se descarta con aviso y devuelve `""`; un prefijo suelto como `⟦` o `⟦abi` todavia no es marca: es texto y se vuelca, invariante 3), `tomar_marca() -> marca.Marca | None`, `tomar_avisos() -> list[dict]` (cada aviso `{"clase": "ilegible"|"sin_corte"|"abierta", "largo": int}` mas `"fuente"` en `sin_corte`; NUNCA el cuerpo: la marca no se persiste ni en telemetry). `marca.PATRON` excluye `⟦` del cuerpo. En `calipso/server.py`: `Emisor(ws, agente_id=None, resolver=None, pulso=None, filtro=None, filtros=None, avisar=None)` con `chunk`, `cerrar`, `marca_abismo() -> marca.Marca | None`; `_avisar_abismo(aviso: dict) -> None`; `_retirar_con_aviso(texto: str, clase: str) -> str` (retira SOLO la gramatica del abismo de un texto que no pasa por el filtro del Emisor y deja una fila `retirada` con `clase` y `cantidad`; la usan la ruta orquestador y el resto posterior del one-shot, Task 7); `_limpiar_marcas(texto)` retira las dos gramaticas; los modulos `abismo_consulta`, `abismo_contrato`, `abismo_filtro`, `abismo_marca`, `abismo_turno`, `abismo_viaje` importados al tope (los tres ultimos existen recien en las Tasks 3-4: **en esta task se importan solo `abismo_filtro` y `abismo_marca`**, y las Tasks 3, 4 y 5 agregan cada una el suyo).

- [ ] **Step 1: Los tests del filtro, en rojo**

```python
# test_abismo_filtro.py
"""El filtro de streaming de la marca del abismo (spec secciones 4 y 11) y su
composicion con el de foco en el Emisor."""
import asyncio
import json

import calipso.server as srv
from calipso.abismo import filtro, marca
from calipso.mapa import foco
from calipso.mapa import pulso as p


def _f(puede=True):
    return filtro.FiltroAbismo(puede_cortar=lambda: puede)


def test_sin_marca_es_transparente_byte_a_byte():
    f = _f()
    texto = "una respuesta comun, con ⟦foco:atlas⟧ y un ⟧ suelto"
    assert f.comer(texto) == texto
    assert f.cerrar() == "" and f.tomar_marca() is None and f.tomar_avisos() == []


def test_una_marca_valida_corta_y_descarta_lo_posterior():
    f = _f()
    assert f.comer("Dejame ver ⟦abismo:chats libro agosto⟧ y sigo hablando") == "Dejame ver "
    assert f.comer("mas texto que vino sin contexto") == ""
    assert f.tomar_marca() == marca.Marca("chats", "libro agosto")
    # consumida la marca, el filtro deja pasar la continuacion de la reentrada
    assert f.comer("la continuacion") == "la continuacion"
    assert f.tomar_marca() is None and f.tomar_avisos() == []


def test_la_marca_partida_en_trozos_igual_se_arma():
    f = _f()
    assert f.comer("vamos a ⟦abi") == "vamos a "
    assert f.comer("smo:memoria que le gus") == ""
    assert f.comer("ta leer⟧ ahora") == ""
    assert f.tomar_marca() == marca.Marca("memoria", "que le gusta leer")


def test_una_marca_ilegible_se_retira_con_aviso_y_sin_corte():
    f = _f()
    assert f.comer("hola ⟦abismo:memorai que dije⟧ sigo") == "hola  sigo"
    assert f.tomar_marca() is None
    assert f.tomar_avisos() == [{"clase": "ilegible", "largo": 16}]


def test_con_el_tope_alcanzado_la_marca_se_retira_y_el_texto_posterior_vale():
    f = _f(puede=False)
    assert f.comer("hola ⟦abismo:chats libro⟧ sigo") == "hola  sigo"
    assert f.tomar_marca() is None
    assert f.tomar_avisos() == [{"clase": "sin_corte", "fuente": "chats", "largo": 11}]


def test_una_marca_abierta_al_cerrar_se_descarta_con_aviso():
    f = _f()
    assert f.comer("termino asi ⟦abismo:chats sin cie") == "termino asi "
    assert f.cerrar() == ""          # jamas se vuelca cruda (divergencia de foco)
    assert f.tomar_avisos() == [{"clase": "abierta", "largo": len("⟦abismo:chats sin cie")}]


def test_un_prefijo_suelto_al_cerrar_es_texto_y_se_vuelca():
    """Un `⟦` (o `⟦abi`) al final del stream NO es una marca inconclusa:
    nunca llego a `⟦abismo:`. Es texto, Pedro tiene que verlo, igual que con
    foco (invariante 3: sin marca, bytes identicos). Solo lo que ya abrio la
    marca se descarta."""
    f = _f()
    assert f.comer("termino con ⟦") == "termino con "
    assert f.cerrar() == "⟦" and f.tomar_avisos() == []
    g = _f()
    assert g.comer("y esto ⟦abi") == "y esto "
    assert g.cerrar() == "⟦abi" and g.tomar_avisos() == []
    # y por la tuberia compuesta del Emisor: foco vuelca el `⟦` que retenia,
    # el abismo lo mira, no es marca, y sale
    ws = WSFalso()
    em = srv.Emisor(ws, filtros=[foco.Filtro(), filtro.FiltroAbismo()], pulso=p.Pulso())

    async def turno():
        return (await em.chunk("mira: ⟦")) + (await em.cerrar())

    assert asyncio.run(turno()) == "mira: ⟦"
    assert "".join(textos(ws)) == "mira: ⟦"


def test_una_marca_de_200_chars_no_se_escapa_cruda():
    """El tope de la pregunta es 160, pero el filtro retiene hasta el tope
    holgado de PATRON (400): la marca larga es ilegible, no texto."""
    f = _f()
    cuerpo = "memoria " + "x" * 192
    assert f.comer("a ⟦abismo:" + cuerpo + "⟧ b") == "a  b"
    assert f.tomar_marca() is None
    assert [a["clase"] for a in f.tomar_avisos()] == ["ilegible"]


def _visible(texto):
    return _f().comer(texto)


def test_el_tope_del_cuerpo_es_el_mismo_que_el_de_patron():
    """Filtro y PATRON juzgan igual QUE es una marca (la leccion de
    foco.py:81-84): 400 todavia lo es (ilegible, se retira), 401 ya es texto
    y los dos lo dejan intacto."""
    justo = "⟦abismo:" + "z" * filtro.CUERPO_MAX + "⟧"
    pasado = "⟦abismo:" + "z" * (filtro.CUERPO_MAX + 1) + "⟧"
    assert marca.PATRON.sub("", justo) == "" and _visible(justo) == ""
    assert marca.PATRON.sub("", pasado) == pasado and _visible(pasado) == pasado
    # y partido en dos, donde la retencion entra en juego, el juicio no cambia
    g = _f()
    assert g.comer("⟦abismo:" + "z" * (filtro.CUERPO_MAX + 1)) + g.comer("⟧ fin") == pasado + " fin"


def test_un_corchete_anidado_no_secuestra_la_marca_siguiente():
    texto = "x ⟦abismo:zzz ⟦abismo:chats hola⟧ fin"
    assert marca.encontrar(texto) == [marca.Marca("chats", "hola")]
    f = _f()
    assert f.comer(texto) == "x ⟦abismo:zzz "
    assert f.tomar_marca() == marca.Marca("chats", "hola")


def test_una_marca_de_foco_dentro_del_cuerpo_no_se_traga():
    texto = "a ⟦abismo:memoria b ⟦foco:atlas⟧ resto"
    assert marca.encontrar(texto) == []
    assert _visible(texto) == texto   # el filtro de foco, que corre antes, la ve


class WSFalso:
    """Anota lo que se manda, en vez de mandarlo (test_mapa_foco.py:77-84)."""

    def __init__(self):
        self.enviados = []

    async def send_json(self, dato):
        self.enviados.append(dato)


def textos(ws):
    return [e["text"] for e in ws.enviados if e.get("type") == "chunk"]


def test_el_emisor_compuesto_retira_las_dos_marcas_y_entrega_la_del_abismo():
    ws, pu, avisos = WSFalso(), p.Pulso(), []
    em = srv.Emisor(ws, agente_id="a1", resolver=lambda n: "dep:" + n, pulso=pu,
                    filtros=[foco.Filtro(), filtro.FiltroAbismo()],
                    avisar=avisos.append)

    async def turno():
        salida = ""
        salida += await em.chunk("miremos ⟦foco:atlas⟧ y ⟦abi")
        salida += await em.chunk("smo:chats libro⟧ esto no sale")
        m = em.marca_abismo()
        salida += await em.chunk(" la continuacion")
        salida += await em.cerrar()
        return salida, m

    salida, m = asyncio.run(turno())
    assert salida == "miremos  y  la continuacion"
    assert "".join(textos(ws)) == salida
    assert em.focos == ["dep:atlas"]
    assert m == marca.Marca("chats", "libro")
    assert em.marca_abismo() is None and avisos == []


def test_el_emisor_con_solo_foco_sigue_volcando_lo_retenido():
    """La ruta de foco sola no cambia (test_mapa_foco.py:102-125 sigue tal
    cual), y `Emisor(ws)` -el borrador de /redacta- NO lleva el filtro del
    abismo: una marca valida le pasa de largo como texto."""
    ws = WSFalso()
    em = srv.Emisor(ws, filtro=foco.Filtro(), pulso=p.Pulso())

    async def turno():
        return (await em.chunk("mira este simbolo: ⟦")) + (await em.cerrar())

    assert asyncio.run(turno()) == "mira este simbolo: ⟦"
    solo = srv.Emisor(WSFalso(), pulso=p.Pulso())
    assert asyncio.run(solo.chunk("a ⟦abismo:chats x⟧ b")) == "a ⟦abismo:chats x⟧ b"
    assert solo.marca_abismo() is None


def test_el_emisor_compuesto_descarta_la_marca_abierta_con_aviso():
    ws, avisos = WSFalso(), []
    em = srv.Emisor(ws, filtros=[foco.Filtro(), filtro.FiltroAbismo()],
                    pulso=p.Pulso(), avisar=avisos.append)

    async def turno():
        return (await em.chunk("termino asi ⟦abismo:chats sin cie")) + (await em.cerrar())

    assert asyncio.run(turno()) == "termino asi "
    assert [a["clase"] for a in avisos] == ["abierta"]


def test_el_aviso_por_defecto_deja_fila_en_telemetry_sin_el_texto(tmp_path, monkeypatch):
    monkeypatch.setattr(srv.telemetry, "LEDGER", tmp_path / "t.jsonl")
    em = srv.Emisor(WSFalso(), filtros=[filtro.FiltroAbismo()], pulso=p.Pulso())
    asyncio.run(em.chunk("hola ⟦abismo:memorai x⟧ sigo"))
    filas = [json.loads(l) for l in (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()]
    assert filas[-1]["kind"] == "abismo" and filas[-1]["evento"] == "retirada"
    assert filas[-1]["clase"] == "ilegible" and "memorai" not in json.dumps(filas)


def test_retirar_con_aviso_saca_solo_el_abismo_y_deja_la_cantidad(tmp_path, monkeypatch):
    """El retiro por fuera del filtro (la sintesis de los agentes, el resto
    posterior del one-shot): "se ignoran CON aviso" (spec seccion 4) es una
    fila por retiro, con la cantidad y sin el cuerpo. La gramatica de foco
    no es asunto suyo."""
    monkeypatch.setattr(srv.telemetry, "LEDGER", tmp_path / "t.jsonl")
    texto = "a ⟦abismo:chats x⟧ b ⟦abismo:zzz⟧ c ⟦foco:atlas⟧"
    assert srv._retirar_con_aviso(texto, "agente") == "a  b  c ⟦foco:atlas⟧"
    filas = [json.loads(l) for l in (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(filas) == 1 and filas[0]["evento"] == "retirada"
    assert filas[0]["clase"] == "agente" and filas[0]["cantidad"] == 2
    assert "chats x" not in json.dumps(filas)
    # sin marcas no hay fila
    assert srv._retirar_con_aviso("sin marcas", "agente") == "sin marcas"
    assert len((tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_limpiar_marcas_saca_las_dos_gramaticas():
    assert srv._limpiar_marcas("a ⟦abismo:chats x⟧ b ⟦foco:atlas⟧ c") == "a  b  c"
    assert srv._limpiar_marcas("cortada ⟦abismo:chats x") == "cortada ⟦abismo:chats x"
    assert srv._limpiar_marcas("") == "" and srv._limpiar_marcas(None) == ""
```

Y en `test_abismo_marca.py`, al final:

```python
def test_un_corchete_anidado_no_traga_la_marca_siguiente():
    # la ilegible abierta no puede comerse la valida que viene detras, ni
    # una marca de foco puede quedar adentro del cuerpo del abismo
    assert marca.encontrar("x ⟦abismo:zzz ⟦abismo:chats hola⟧") == [marca.Marca("chats", "hola")]
    assert marca.encontrar("x ⟦abismo:memoria a ⟦foco:atlas⟧ resto") == []
```

- [ ] **Step 2: Verlos fallar**

Run: `.venv/bin/python -m pytest -q test_abismo_filtro.py test_abismo_marca.py`
Expected: `1 error` en la colecta (`ImportError: cannot import name 'filtro' from 'calipso.abismo'`); pytest se interrumpe ahi (`Interrupted: 1 error during collection`) y NO corre el otro archivo. Para ver el rojo de la marca: `.venv/bin/python -m pytest -q test_abismo_marca.py` -> `1 failed, 6 passed` (el anidado devuelve una sola marca ilegible).

- [ ] **Step 3: `PATRON` sin corchete anidado**

`calipso/abismo/marca.py:18-22` pasa a:

```python
# El cuerpo no puede contener ningun corchete: ni el de cierre ni el de
# apertura (una ilegible abierta se tragaba la valida que venia detras, y una
# marca de foco quedaba adentro del cuerpo del abismo, invisible para el
# filtro de foco que corre antes). El tope de la regex va holgado (el exacto
# lo valida parsear) para que una marca larga se detecte como marca ilegible
# y no se escape entera al texto.
PATRON = re.compile(
    re.escape(ABRE) + r"abismo:([^" + CIERRA + ABRE + r"]{1,400})" + re.escape(CIERRA))
```

- [ ] **Step 4: `calipso/abismo/filtro.py` completo**

```python
"""El filtro de la marca del abismo para el stream -- spec seccion 4.

Hermano del `Filtro` de calipso/mapa/foco.py: copia la idea (retener la cola
sospechosa hasta poder decidir) y NO la clase, porque las reglas divergen en
tres puntos que el spec declara:

1. El cuerpo va hasta 400 chars (el tope holgado de `marca.PATRON`, no los
   160 de `MAX_PREGUNTA`): el filtro retiene `len("⟦abismo:") + 400 + 1` y
   decide con `marca.parsear`. Retener solo 160 dejaria escapar cruda una
   marca de 200 chars, que `marca.py` quiso justamente atrapar como
   ilegible. Filtro y `marca.PATRON` juzgan igual QUE es una marca (cuerpo
   de 1 a 400 chars sin corchetes); `parsear` decide si es valida.
2. Una marca VALIDA corta: queda pendiente en `tomar_marca()` y lo que venga
   despues (el resto del trozo y los trozos siguientes hasta que la
   consuman) se descarta -- el modelo siguio escribiendo sin el contexto que
   pidio. Salvo que `puede_cortar()` diga que no (tope de consultas,
   fallback, orquestador): ahi la marca se retira con aviso y el texto
   posterior sigue saliendo (los dos regimenes del spec, a proposito).
3. `cerrar()` DESCARTA lo retenido con aviso, nunca lo vuelca crudo
   (divergencia deliberada de foco, spec seccion 11).

Sin marca en el stream, los bytes que salen son identicos a los que entraron
(invariante 3). El filtro es puro: no hace I/O; los avisos se acumulan en
`tomar_avisos()` y el Emisor los lleva a telemetry -- sin el cuerpo de la
marca, que no se persiste en ningun lado.
"""
from __future__ import annotations

from typing import Callable

from calipso.abismo import marca

ABRE = marca.ABRE + "abismo:"
CIERRA = marca.CIERRA
CUERPO_MAX = 400                              # el tope holgado de marca.PATRON
RETENCION_MAX = len(ABRE) + CUERPO_MAX + 1    # con esto a la vista ya decide


def _retenible(texto: str) -> int:
    """Cuantos caracteres del final pueden ser el principio de ABRE."""
    for k in range(min(len(texto), len(ABRE) - 1), 0, -1):
        if ABRE.startswith(texto[-k:]):
            return k
    return 0


def _es_cuerpo_de_marca(cuerpo: str) -> bool:
    """El mismo juicio que `marca.PATRON`: de 1 a 400 chars sin corchetes."""
    return (1 <= len(cuerpo) <= CUERPO_MAX
            and marca.ABRE not in cuerpo and CIERRA not in cuerpo)


class FiltroAbismo:
    """Uno por turno. No es reentrante y no se comparte entre conexiones."""

    def __init__(self, puede_cortar: Callable[[], bool] = lambda: True):
        self._puede_cortar = puede_cortar
        self._resto = ""
        self._marca: marca.Marca | None = None
        self._avisos: list[dict] = []

    def comer(self, trozo: str) -> str:
        """Devuelve el texto visible del trozo; deja la marca valida pendiente."""
        if self._marca is not None:
            return ""       # ya corto: lo posterior se descarta hasta tomar_marca()
        buf = self._resto + trozo
        self._resto = ""
        visible: list[str] = []
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
                if len(buf) - i >= RETENCION_MAX:
                    # con RETENCION_MAX chars a la vista ya se sabe: abrio y
                    # no cerro en un cuerpo plausible, era texto
                    visible.append(buf[i:i + len(ABRE)])
                    buf = buf[i + len(ABRE):]
                    continue
                self._resto = buf[i:]
                break
            cuerpo = buf[i + len(ABRE):j]
            if not _es_cuerpo_de_marca(cuerpo):
                # cerro, pero PATRON tampoco lo tomaria por marca: era texto
                visible.append(buf[i:i + len(ABRE)])
                buf = buf[i + len(ABRE):]
                continue
            m = marca.parsear(cuerpo)
            buf = buf[j + len(CIERRA):]
            if m is None:
                self._avisos.append({"clase": "ilegible", "largo": len(cuerpo)})
                continue
            if not self._puede_cortar():
                self._avisos.append({"clase": "sin_corte", "fuente": m.fuente,
                                     "largo": len(cuerpo)})
                continue
            self._marca = m
            break           # lo que quedaba en buf vino sin contexto: se descarta
        return "".join(visible)

    def cerrar(self) -> str:
        """Una marca abierta al final del stream (lo retenido ya empezo con
        `⟦abismo:`) se descarta con aviso, jamas se vuelca cruda (spec
        seccion 11). Un prefijo suelto (`⟦`, `⟦abi`) todavia no es marca: es
        texto y Pedro tiene que verlo, igual que con foco (invariante 3)."""
        resto, self._resto = self._resto, ""
        if not resto:
            return ""
        if resto.startswith(ABRE):
            self._avisos.append({"clase": "abierta", "largo": len(resto)})
            return ""
        return resto

    def tomar_marca(self) -> marca.Marca | None:
        """La marca valida pendiente, consumida: el filtro vuelve a dejar
        pasar texto (la continuacion de la reentrada)."""
        m, self._marca = self._marca, None
        return m

    def tomar_avisos(self) -> list[dict]:
        avisos, self._avisos = self._avisos, []
        return avisos
```

- [ ] **Step 5: El `Emisor` compuesto y `_limpiar_marcas` en `server.py`**

Imports, al lado de los de privacidad (`calipso/server.py:81-82`):

```python
from calipso.privacidad import conversacion, redaccion  # noqa: E402
from calipso.privacidad import nube as privacidad_nube  # noqa: E402
from calipso.abismo import filtro as abismo_filtro  # noqa: E402
from calipso.abismo import marca as abismo_marca  # noqa: E402
```

El bloque `class Emisor` (`:7110-7156`) y `_limpiar_marcas` (`:7159-7164`) se reemplazan ENTEROS por esto (la docstring de la clase se conserva; `_avisar_abismo` va ANTES de la clase porque es su default):

```python
def _avisar_abismo(aviso: dict) -> None:
    """"Queda aviso" (spec seccion 9) para una marca que se retiro del texto
    sin consulta -ilegible, sin corte por tope, abierta al cerrar-: fila en
    telemetry.jsonl. Sin senal al WS: no hubo pondering que cerrar. Y sin el
    cuerpo de la marca, que no se persiste en ningun lado."""
    telemetry.log_event("abismo", evento="retirada", **aviso)


def _retirar_con_aviso(texto: str, clase: str) -> str:
    """Retira las marcas del abismo de un texto que NO pasa por el filtro del
    Emisor -la sintesis de los agentes del orquestador, lo posterior a una
    marca en la ruta one-shot- y deja el aviso que el spec exige (seccion
    4: "se ignoran con aviso"): una fila por retiro, con la cantidad, sin
    el cuerpo. Solo la gramatica del abismo: la de foco la retira quien
    corresponda (el filtro de foco del Emisor, o `_limpiar_marcas`)."""
    n = len(abismo_marca.PATRON.findall(texto or ""))
    if n:
        _avisar_abismo({"clase": clase, "largo": 0, "cantidad": n})
    return abismo_marca.PATRON.sub("", texto or "")


class Emisor:
    """Todo lo que Pedro lee sale por aca.

    Tres cosas en un solo lugar: retirar la marca de foco del texto visible,
    publicar el foco apenas aparece (la camara vuela mientras Calipso sigue
    escribiendo) y darle al pulso lo que se va diciendo. Antes los chunks
    salian desde cinco puntos de `ws_chat`, y filtrar en cinco lugares es
    filtrar en cuatro.

    Desde el abismo (spec seccion 4) los filtros son una tuberia ordenada:
    foco primero, abismo despues. La marca del abismo no se resuelve aca
    (es I/O y hay que cerrar el generador): se entrega hacia arriba por
    `marca_abismo()` y la consume el bucle de `ws_chat`."""

    def __init__(self, ws, agente_id: str | None = None, resolver=None,
                 pulso=None, filtro=None, filtros=None, avisar=None):
        self.ws = ws
        self.agente_id = agente_id
        self._resolver = resolver or _resolver_foco
        self._pulso = pulso if pulso is not None else EL_PULSO
        # el default es SOLO foco: el borrador de /redacta construye
        # `Emisor(ws)` y no tiene quien resuelva una consulta (spec seccion
        # 11); el turno conversacional pasa la lista completa a mano.
        if filtros is not None:
            self._filtros = list(filtros)
        elif filtro is not None:
            self._filtros = [filtro]
        else:
            self._filtros = [_mapa_foco.Filtro()] if _mapa_foco is not None else []
        self._avisar = avisar or _avisar_abismo
        self.focos: list[str] = []

    async def _soltar(self, visible: str) -> str:
        if not visible:
            return ""      # un chunk vacio la UI vieja lo pinta igual
        await self.ws.send_json({"type": "chunk", "text": visible})
        if self._pulso is not None and self.agente_id:
            self._pulso.publicar(self.agente_id, "razonando", texto=visible)
        return visible

    def _cosechar(self) -> None:
        """Lo que los filtros vieron: focos (se resuelven y publican aca, es
        una lectura de un JSON chico) y avisos del abismo (a telemetry)."""
        for f in self._filtros:
            for nombre in (f.tomar_focos() if hasattr(f, "tomar_focos") else ()):
                destino = self._resolver(nombre)
                if destino is None:
                    continue          # el modelo se invento un departamento
                self.focos.append(destino)
                if self._pulso is not None:
                    self._pulso.enfocar(destino)
            for aviso in (f.tomar_avisos() if hasattr(f, "tomar_avisos") else ()):
                self._avisar(aviso)

    async def chunk(self, texto: str) -> str:
        """Manda lo visible y devuelve exactamente eso, para que el que
        acumula la respuesta acumule lo mismo que Pedro leyo."""
        visible = texto
        for f in self._filtros:
            visible = f.comer(visible)
        visible = await self._soltar(visible)
        self._cosechar()
        return visible

    def marca_abismo(self):
        """La marca valida pendiente del filtro del abismo, consumida; None
        si no hay filtro o no hay marca. Cuando la hay, lo que los filtros
        ANTERIORES de la tuberia retenian es posterior a la marca (el
        corchete de un `⟦fo` a medio llegar) y se descarta con ella."""
        for i, f in enumerate(self._filtros):
            if not hasattr(f, "tomar_marca"):
                continue
            m = f.tomar_marca()
            if m is not None:
                for previo in self._filtros[:i]:
                    previo.cerrar()
            return m
        return None

    async def cerrar(self) -> str:
        """Una marca de foco que nunca cerro es texto y Pedro tiene que
        verlo; lo que suelta un filtro pasa por los que le siguen (asi el
        abismo mira el corchete que foco venia reteniendo), y lo que retenga
        el del abismo se descarta con aviso (spec seccion 11)."""
        salida = ""
        for i, f in enumerate(self._filtros):
            cola = f.cerrar()
            for siguiente in self._filtros[i + 1:]:
                cola = siguiente.comer(cola)
            salida += cola
        self._cosechar()
        return await self._soltar(salida)


def _limpiar_marcas(texto: str) -> str:
    """El parcial de la suscripcion se remanda ENTERO cada dos segundos, asi
    que no necesita la maquinaria de retencion del Filtro: alcanza con sacar
    las marcas completas. Una marca a medio llegar se limpia sola en el envio
    siguiente, porque el texto se relee desde cero.

    Compone las dos gramaticas: la del abismo (`marca.PATRON`, la misma regex
    del filtro y del banco) y la de foco. Es el retiro que cubre la ruta
    orquestador (spec seccion 4: las marcas de los agentes se ignoran con
    aviso) y el preview y los artefactos de la suscripcion."""
    texto = abismo_marca.PATRON.sub("", texto or "")
    return _mapa_foco.limpiar(texto) if _mapa_foco is not None else texto
```

- [ ] **Step 6: Verde y suite completa**

Run: `.venv/bin/python -m pytest -q test_abismo_filtro.py test_abismo_marca.py test_mapa_foco.py`
Expected: `17 passed` + `7 passed` + `18 passed` (test_mapa_foco.py entero sigue en verde: `filtro=` sigue vivo, `em.cerrar()` con foco solo vuelca igual, `_limpiar_marcas` sigue sacando foco).

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
Expected: `1394 passed, 4 warnings`, `EXIT=0`.

- [ ] **Step 7: Commit**

```bash
git add calipso/abismo/filtro.py calipso/abismo/marca.py calipso/server.py test_abismo_filtro.py test_abismo_marca.py
git commit -m "feat(abismo): FiltroAbismo (corta en la marca valida, retiene 409, descarta al cerrar), Emisor con tuberia de filtros y marca_abismo(), _limpiar_marcas con las dos gramaticas, PATRON sin corchete anidado"
```

Riesgos anotados por los mapas: (a) el borrador (`server.py:3310`, `Emisor(ws)`) NO cambia y NO lleva el abismo -- el default de `filtros` es foco solo; el test `test_el_emisor_con_solo_foco_sigue_volcando_lo_retenido` lo custodia. (b) El `Emisor` del turno (`:3429`) tampoco cambia en esta task: si llevara el filtro sin el bucle de la Task 6, una marca valida truncaria la respuesta sin reentrada. (c) La latencia del corte es `retencion(foco) + retencion(abismo)`: un `⟦` al final de un trozo lo retiene foco (5 chars max) y el abismo lo ve un trozo despues; aceptado (mapa del filtro 7.2). (d) Un `⟦` o `⟦abi` solitario al final de la respuesta NO se pierde en el `cerrar()` compuesto: foco lo vuelca, el abismo lo mira, no empieza con `⟦abismo:` y sale como texto (invariante 3; `test_un_prefijo_suelto_al_cerrar_es_texto_y_se_vuelca`). Solo lo que ya abrio la marca se descarta. (e) `_retirar_con_aviso` queda definido aca y sin llamador hasta la Task 7 (orquestador y resto posterior del one-shot): su test unitario es el que lo custodia mientras tanto.

---

### Task 3: `viaje.py` + `anillos.puede_viajar` real

**Files:**
- Create: `calipso/abismo/viaje.py`
- Modify: `calipso/abismo/anillos.py:26-30` (`puede_viajar`)
- Modify: `calipso/server.py:83` (un import mas: `abismo_viaje`, al lado de los de la Task 2)
- Test: `test_abismo_viaje.py` (nuevo), `test_abismo_anillos.py:23-29` (se reescribe el test del viaje)

**Interfaces:**
- Consumes: `anillos.ORILLA/MEDIA_AGUA/HONDO`, `consulta.ABISMO_BLOQUE_MAX` (`calipso/abismo/consulta.py:13`), `juez.juzgar(texto) -> {"tramos","fallo_cerrado","motivo"}` (`calipso/privacidad/juez.py:18`), `redaccion.redactar(texto, tramos, mapa)` y `MapaMarcadores.marcador_para(texto, tipo)` (`calipso/privacidad/redaccion.py:49`, `:32`).
- Produces: `anillos.puede_viajar(anillo, destino) -> bool` (local: todo; nube: 1 y 2; otro destino: nada). `viaje.etiquetar(fuente: str, bloques: list[tuple[str, int]]) -> str` (el mismo texto que arma `consulta.resolver`). `viaje.preparar_viaje(bloques: list[tuple[str, int]], destino: str, mapa, fuente: str = "") -> dict` con `{"estado": "viaja"|"fallo", "texto": str, "tapados": list[{"marcador","tipo"}], "motivo": ""|"vacio"|"solo_hondo"|"credencial"|"juez_local_caido"|"tipo_desconocido"|"error"}`. (El `fuente` opcional no esta en la firma del ruling 8: hace falta para re-armar el encabezado "=== Lo que subio del abismo (fuente: X) ===" con lo que sobrevive.)

- [ ] **Step 1: Tests en rojo**

`test_abismo_anillos.py`: reemplazar `test_a_la_nube_no_viaja_nada_en_esta_rebanada` (`:23-29`) por:

```python
def test_a_la_nube_viajan_la_orilla_y_media_agua_y_lo_hondo_jamas():
    # enmienda 2026-09-08: la columna "Viaje a la nube" ya no es politica
    # futura. Local deja pasar todo; nube deja 1 y 2 (redactados despues
    # por el juez, en viaje.py) y el 3 nunca, ni tapado.
    for a in (anillos.ORILLA, anillos.MEDIA_AGUA, anillos.HONDO):
        assert anillos.puede_viajar(a, "local") is True
    assert anillos.puede_viajar(anillos.ORILLA, "nube") is True
    assert anillos.puede_viajar(anillos.MEDIA_AGUA, "nube") is True
    assert anillos.puede_viajar(anillos.HONDO, "nube") is False
    assert anillos.puede_viajar(anillos.ORILLA, "marte") is False   # fallo cerrado
```

`test_abismo_viaje.py` entero:

```python
"""La etapa de viaje en aislado (spec seccion 15, enmienda 2026-09-08)."""
from calipso.abismo import anillos, consulta, marca, viaje
from calipso.privacidad import juez
from calipso.privacidad.redaccion import MapaMarcadores


def _juez(monkeypatch, secretos, llm):
    """El molde de test_privacidad_juez.py: detector y LLM dobles."""
    monkeypatch.setattr(juez.detector, "detectar_secretos", lambda t: secretos)
    monkeypatch.setattr(juez.juez_llm, "juzgar_llm", lambda t: llm)


def _juez_prohibido(monkeypatch):
    def bomba(*a, **k):
        raise AssertionError("el juez no debe correr")
    monkeypatch.setattr(juez, "juzgar", bomba)


BLOQUES = [("proyecto calipso:\nbrief", anillos.ORILLA),
           ("[t 2026-08-01] hola Marta", anillos.MEDIA_AGUA),
           ("del core:\n- vive en Cordoba", anillos.HONDO)]


def test_destino_local_es_transparente_y_no_corre_el_juez(monkeypatch):
    _juez_prohibido(monkeypatch)
    r = viaje.preparar_viaje(BLOQUES, "local", MapaMarcadores(), fuente="memoria")
    assert r["estado"] == "viaja" and r["tapados"] == [] and r["motivo"] == ""
    assert "vive en Cordoba" in r["texto"] and "[anillo 3]" in r["texto"]
    assert r["texto"].startswith("=== Lo que subio del abismo (fuente: memoria) ===")


def test_el_etiquetado_del_viaje_es_el_mismo_que_el_del_resolvedor(monkeypatch):
    from calipso.abismo import fuentes
    monkeypatch.setattr(fuentes, "chats_viejos", lambda resto: BLOQUES[1:2])
    r = consulta.resolver(marca.Marca("chats", "hola"))
    assert viaje.etiquetar("chats", BLOQUES[1:2]) == r["texto"]


def test_el_etiquetado_respeta_el_techo(monkeypatch):
    largo = [("x" * 5000, anillos.MEDIA_AGUA)]
    assert len(viaje.etiquetar("chats", largo)) <= consulta.ABISMO_BLOQUE_MAX


def test_a_la_nube_lo_hondo_se_descarta_antes_del_juez(monkeypatch):
    visto = {}

    def juzgar(texto):
        visto["texto"] = texto
        return {"tramos": [], "fallo_cerrado": False, "motivo": ""}
    monkeypatch.setattr(juez, "juzgar", juzgar)
    r = viaje.preparar_viaje(BLOQUES, "nube", MapaMarcadores(), fuente="memoria")
    assert r["estado"] == "viaja"
    assert "Cordoba" not in visto["texto"] and "Cordoba" not in r["texto"]
    assert "[anillo 1]" in r["texto"] and "[anillo 2]" in r["texto"]


def test_solo_hondo_falla_cerrado_sin_juez(monkeypatch):
    _juez_prohibido(monkeypatch)
    r = viaje.preparar_viaje(BLOQUES[2:], "nube", MapaMarcadores())
    assert r == {"estado": "fallo", "texto": "", "tapados": [], "motivo": "solo_hondo"}


def test_credencial_en_cualquier_sub_bloque_falla_cerrado_el_envio_entero(monkeypatch):
    _juez(monkeypatch, [{"texto": "ghp_xxx", "tipo": "credencial"}], {"tramos": [], "ok": True})
    r = viaje.preparar_viaje(BLOQUES, "nube", MapaMarcadores())
    assert r["estado"] == "fallo" and r["motivo"] == "credencial"
    assert r["texto"] == "" and r["tapados"] == []


def test_juez_caido_y_tipo_desconocido_fallan_cerrado(monkeypatch):
    _juez(monkeypatch, [], {"tramos": [], "ok": False})
    assert viaje.preparar_viaje(BLOQUES, "nube", MapaMarcadores())["motivo"] == "juez_local_caido"
    _juez(monkeypatch, [], {"tramos": [{"texto": "sertralina", "tipo": "medicamento"}], "ok": True})
    assert viaje.preparar_viaje(BLOQUES, "nube", MapaMarcadores())["motivo"] == "tipo_desconocido"


def test_un_juez_que_revienta_es_fallo_cerrado(monkeypatch):
    def bomba(texto):
        raise RuntimeError("ollama se cayo")
    monkeypatch.setattr(juez, "juzgar", bomba)
    assert viaje.preparar_viaje(BLOQUES, "nube", MapaMarcadores())["motivo"] == "juez_local_caido"


def test_lo_humano_se_tapa_con_el_mapa_compartido_de_la_conversacion(monkeypatch):
    _juez(monkeypatch, [], {"tramos": [{"texto": "Marta", "tipo": "identidad"}], "ok": True})
    mapa = MapaMarcadores()
    marcador_del_mensaje = mapa.marcador_para("Marta", "identidad")   # ya tapada en el mensaje
    r = viaje.preparar_viaje(BLOQUES, "nube", mapa, fuente="chats")
    assert r["estado"] == "viaja"
    assert "Marta" not in r["texto"] and marcador_del_mensaje in r["texto"]
    assert r["tapados"] == [{"marcador": marcador_del_mensaje, "tipo": "identidad"}]
    # el reponer de siempre restaura la misma persona
    assert mapa.reponer_texto(r["texto"]).count("Marta") == 1


def test_sin_bloques_es_vacio(monkeypatch):
    _juez_prohibido(monkeypatch)
    assert viaje.preparar_viaje([("  ", 1)], "nube", MapaMarcadores())["motivo"] == "vacio"
```

- [ ] **Step 2: Verlos fallar**

Run: `.venv/bin/python -m pytest -q test_abismo_viaje.py test_abismo_anillos.py`
Expected: `1 error` en la colecta (`ImportError: cannot import name 'viaje' from 'calipso.abismo'`); pytest se interrumpe ahi y NO corre el otro archivo. Para ver el rojo de los anillos: `.venv/bin/python -m pytest -q test_abismo_anillos.py` -> `1 failed, 3 passed` (`puede_viajar(ORILLA, "nube")` da False hoy).

- [ ] **Step 3: `puede_viajar` real**

`calipso/abismo/anillos.py:26-30` pasa a:

```python
def puede_viajar(anillo: int, destino: str) -> bool:
    """La politica de la columna "Viaje a la nube" (spec seccion 6, enmienda
    2026-09-08): destino local deja pasar todo; a la nube viajan la orilla y
    media agua (redactados despues por el juez, en viaje.py) y lo hondo
    JAMAS, ni tapado. Un destino desconocido no deja pasar nada."""
    if destino == "local":
        return True
    if destino == "nube":
        return anillo in (ORILLA, MEDIA_AGUA)
    return False
```

- [ ] **Step 4: `calipso/abismo/viaje.py` completo**

```python
"""La etapa de viaje -- spec secciones 4 y 8 (enmienda 2026-09-08).

Funcion PURA entre la pesca y el envio: recibe los sub-bloques (texto,
anillo) que devolvio el resolvedor, el destino y el MapaMarcadores de la
conversacion, y devuelve que viaja. Tres pasos, en este orden y no en otro:

1. Anillos: lo que `anillos.puede_viajar` no deja (a la nube, todo anillo
   3) se descarta ANTES de que el juez lo vea. Si no queda nada: fallo
   `solo_hondo`.
2. El juez de dos capas (`privacidad.juez.juzgar`) sobre el texto que
   queda: credencial, juez caido o tipo desconocido = fallo cerrado del
   envio ENTERO de esa consulta (la regla del ruteo: sin condicion).
3. Redaccion con el MISMO mapa que tapo el mensaje: `[ID_1]` es la misma
   persona en el mensaje, en el bloque y en la respuesta, y el reponer de
   siempre restaura todo.

Con destino `local` es transparente: todo pasa, nada se tapa, el juez no
corre. Un solo camino para todas las rutas.
"""
from __future__ import annotations

from calipso.abismo import anillos, consulta
from calipso.privacidad import juez, redaccion


def etiquetar(fuente: str, bloques: list[tuple[str, int]]) -> str:
    """El mismo texto etiquetado que arma `consulta.resolver` (fuente y
    anillo por sub-bloque, bajo ABISMO_BLOQUE_MAX): el viaje lo re-arma con
    lo que sobrevive a los anillos. Si esto y el resolvedor divergen, el
    modelo ve dos formatos para lo mismo; test_abismo_viaje lo custodia."""
    partes = [f"=== Lo que subio del abismo (fuente: {fuente}) ==="]
    for texto, anillo in bloques:
        partes.append(f"[anillo {anillo}]\n{texto.strip()}")
    return "\n".join(partes)[:consulta.ABISMO_BLOQUE_MAX]


def _fallo(motivo: str) -> dict:
    return {"estado": "fallo", "texto": "", "tapados": [], "motivo": motivo}


def preparar_viaje(bloques: list[tuple[str, int]], destino: str, mapa,
                   fuente: str = "") -> dict:
    """Que viaja de lo pescado. Lo humano que marca el juez se TAPA y viaja
    (spec secciones 4 y 8, enmienda 2026-09-08); la frase "un sub-bloque de
    chats con salud adentro se hunde a 3" de la seccion 6 es de la version
    original del spec y queda superada por la enmienda: el juez solo puede
    tapar o cortar el envio entero, nunca cambiar el anillo de un bloque."""
    bloques = [(t, a) for t, a in bloques if t and t.strip()]
    if not bloques:
        return _fallo("vacio")
    if destino == "local":
        return {"estado": "viaja", "texto": etiquetar(fuente, bloques),
                "tapados": [], "motivo": ""}
    viajan = [(t, a) for t, a in bloques if anillos.puede_viajar(a, destino)]
    if not viajan:
        return _fallo("solo_hondo")
    texto = etiquetar(fuente, viajan)
    try:
        veredicto = juez.juzgar(texto)
    except Exception:
        return _fallo("juez_local_caido")
    if veredicto["fallo_cerrado"]:
        return _fallo(veredicto["motivo"] or "error")
    tramos = veredicto["tramos"]
    tapado = redaccion.redactar(texto, tramos, mapa)
    tapados = [{"marcador": mapa.marcador_para(t["texto"], t["tipo"]),
                "tipo": t["tipo"]} for t in tramos]
    return {"estado": "viaja", "texto": tapado, "tapados": tapados, "motivo": ""}
```

Y en `calipso/server.py`, junto a los imports de la Task 2: `from calipso.abismo import viaje as abismo_viaje  # noqa: E402`.

- [ ] **Step 5: Verde y suite**

Run: `.venv/bin/python -m pytest -q test_abismo_viaje.py test_abismo_anillos.py`
Expected: `10 passed` + `4 passed`

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
Expected: `1404 passed, 4 warnings`, `EXIT=0`.

- [ ] **Step 6: Commit**

```bash
git add calipso/abismo/viaje.py calipso/abismo/anillos.py calipso/server.py test_abismo_viaje.py test_abismo_anillos.py
git commit -m "feat(abismo): la etapa de viaje (anillos -> juez -> redaccion con el mapa de la conversacion; local transparente) y puede_viajar real"
```

Riesgos anotados: `viaje.py` importa `consulta` (por `ABISMO_BLOQUE_MAX`), y `consulta` importa `fuentes` -> `chats`, `chronology`: cadena liviana, sin ciclo (`consulta` no importa `viaje`). El juez tarda 3-4 s por bloque (medido en la Fase 2) y NO se capea: corre en hilo desde el server (Task 6), nunca sobre el event loop.

---

### Task 4: `turno.py` -- el estado del turno, el prompt de la reentrada, la senal y el detector one-shot

**Files:**
- Create: `calipso/abismo/turno.py`
- Modify: `calipso/server.py:83` (import `abismo_turno`)
- Test: `test_abismo_turno.py`

**Interfaces:**
- Consumes: `marca.PATRON`, `marca.parsear`, `marca.Marca`; el aviso exacto de la pesca vacia, `"la consulta no trajo nada"` (`calipso/abismo/consulta.py:37`).
- Produces (todo puro): `ABISMO_CONSULTAS_MAX = 3`; `FASES`, `MOTIVOS`, `VERBOS`, `INSTRUCCION_CONTINUAR`; `@dataclass EstadoTurno(consultas: int = 0, bloques: list[str], tramos: list[str], tramos_crudos: list[str], sintetica: bool = False, apagada: bool = False)` con `reset() -> None` y `puede_cortar() -> bool` (`not apagada and consultas < ABISMO_CONSULTAS_MAX`); `prompt_reentrada(system_base: str, bloques: list[str], tramos_crudos: list[str], mensaje: str) -> tuple[str, str]`; `senal(fase: str, fuente: str, **campos) -> dict`; `motivo_de_consulta(resultado: dict) -> str`; `cortar_en_marca(texto: str) -> tuple[str, marca.Marca | None]`; `prefijo_congelado(texto: str) -> str | None`; `retirar_marcas(texto: str) -> str`; `recortar_abierta(texto: str) -> str` (una marca a medio llegar al FINAL del texto se recorta: para el preview de suscripcion, Task 7). (Desvio del ruling 3, declarado: `prompt_reentrada` recibe ademas `mensaje`, el mensaje original del turno, porque `_history_messages` descarta el ultimo mensaje del chat -el de Pedro- y sin esto la reentrada no sabria que se le pregunto. Y `EstadoTurno` gana `apagada`, la llave para que el fallback y el orquestador retiren las marcas sin cortar.)

- [ ] **Step 1: Tests en rojo**

```python
# test_abismo_turno.py
"""El estado del turno y las piezas puras de la reentrada (spec seccion 4)."""
import pytest

from calipso.abismo import marca, turno


def test_el_estado_arranca_vacio_y_el_reset_lo_deja_igual():
    e = turno.EstadoTurno()
    assert (e.consultas, e.bloques, e.tramos, e.tramos_crudos, e.sintetica, e.apagada) == (0, [], [], [], False, False)
    e.consultas, e.sintetica, e.apagada = 2, True, True
    e.bloques.append("b"); e.tramos.append("t"); e.tramos_crudos.append("c")
    e.reset()
    assert e == turno.EstadoTurno()


def test_puede_cortar_bajo_el_tope_y_encendida():
    e = turno.EstadoTurno()
    assert e.puede_cortar() is True
    e.consultas = turno.ABISMO_CONSULTAS_MAX
    assert e.puede_cortar() is False
    e.consultas, e.apagada = 0, True
    assert e.puede_cortar() is False


def test_el_prompt_de_reentrada_lleva_bloques_mensaje_y_venias_diciendo():
    system, usuario = turno.prompt_reentrada(
        "SISTEMA", ["=== bloque uno ===", "=== bloque dos ==="],
        ["Dejame ver ", "que dije "], "que libro lei")
    assert system == "SISTEMA\n\n=== bloque uno ===\n\n=== bloque dos ==="
    assert usuario.startswith("que libro lei\n\n")
    assert "Venias diciendo: Dejame ver que dije \n" in usuario
    assert usuario.endswith(turno.INSTRUCCION_CONTINUAR)


def test_sin_bloques_el_system_no_cambia():
    system, _ = turno.prompt_reentrada("SISTEMA", [], ["a"], "m")
    assert system == "SISTEMA"


def test_la_senal_lleva_los_campos_fijos_de_cada_fase():
    assert turno.senal("pondering", "chats") == {
        "type": "abismo", "fase": "pondering", "fuente": "chats",
        "verbo": "buscando en tus chats"}
    assert turno.senal("pescado", "memoria", tamano=120) == {
        "type": "abismo", "fase": "pescado", "fuente": "memoria",
        "tamano": 120, "viaje": {"destino": "local"}}
    v = {"destino": "nube", "tapados": [{"marcador": "[ID_1]", "tipo": "identidad"}], "texto_tapado": "x"}
    assert turno.senal("pescado", "chats", tamano=1, viaje=v)["viaje"] == v
    assert turno.senal("fallo", "proyecto", motivo="solo_hondo")["motivo"] == "solo_hondo"
    # un motivo fuera de la lista cerrada se normaliza a "error"
    assert turno.senal("fallo", "proyecto", motivo="lo que sea")["motivo"] == "error"
    assert turno.senal("fallo", "proyecto")["motivo"] == "error"
    with pytest.raises(ValueError):
        turno.senal("bailando", "chats")


def test_el_motivo_de_la_consulta():
    assert turno.motivo_de_consulta({"estado": "fallo", "aviso": "la consulta no trajo nada"}) == "vacio"
    assert turno.motivo_de_consulta({"estado": "fallo", "aviso": "chats.json roto"}) == "error"


def test_cortar_en_marca_corta_en_la_primera_valida():
    texto = "Dejame ver ⟦abismo:zzz nada⟧ y ⟦abismo:chats libro⟧ esto vino sin contexto"
    tramo, m = turno.cortar_en_marca(texto)
    assert tramo == "Dejame ver ⟦abismo:zzz nada⟧ y "   # la ilegible queda: el Emisor la retira
    assert m == marca.Marca("chats", "libro")
    assert turno.cortar_en_marca("sin marcas") == ("sin marcas", None)
    assert turno.cortar_en_marca("") == ("", None)


def test_prefijo_congelado_y_retirar_marcas():
    assert turno.prefijo_congelado("hola ⟦abismo:chats x⟧ resto") == "hola "
    assert turno.prefijo_congelado("hola ⟦abismo:zzz x⟧ resto") is None
    assert turno.retirar_marcas("a ⟦abismo:chats x⟧ b ⟦abismo:zzz⟧ c") == "a  b  c"


def test_recortar_abierta_saca_la_marca_a_medio_llegar_del_final():
    """Entre dos tics del preview el parcial puede terminar en una marca
    que abrio y no cerro: Pedro no la lee cruda (spec seccion 4)."""
    assert turno.recortar_abierta("Dejame ver ⟦abismo:chats lib") == "Dejame ver "
    assert turno.recortar_abierta("Dejame ver ⟦abismo:") == "Dejame ver "
    assert turno.recortar_abierta("hola ⟦abismo:chats x⟧ resto") == "hola ⟦abismo:chats x⟧ resto"
    assert turno.recortar_abierta("") == ""
```

- [ ] **Step 2: Verlos fallar**

Run: `.venv/bin/python -m pytest -q test_abismo_turno.py`
Expected: `ImportError: cannot import name 'turno' from 'calipso.abismo'`.

- [ ] **Step 3: `calipso/abismo/turno.py` completo**

```python
"""El estado del turno y las piezas puras de la reentrada -- spec seccion 4.

Vive junto al estado de conexion de `ws_chat`, atraviesa reentradas y solo
un mensaje real de Pedro lo resetea (invariante 8). Todo lo de aca es puro:
sin WebSocket, sin modelo, sin disco.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from calipso.abismo import marca

ABISMO_CONSULTAS_MAX = 3          # consultas por turno (spec seccion 4)
FASES = ("pondering", "pescado", "fallo")
MOTIVOS = ("vacio", "credencial", "solo_hondo", "juez_local_caido",
           "tipo_desconocido", "error")
VERBOS = {"memoria": "buscando en tu memoria",
          "chats": "buscando en tus chats",
          "proyecto": "mirando el repo"}
INSTRUCCION_CONTINUAR = "Segui exactamente desde ahi, sin repetir."


@dataclass
class EstadoTurno:
    """Lo que la pasada sintetica necesita saber del turno: cuantas veces
    consulto, que subio (los textos que ya viajaron, en orden), que vio
    Pedro (tramos visibles, ya filtrados) y que escribio el modelo ANTES de
    reponer (tramos crudos: en local son identicos a `tramos`; en /nube
    llevan los marcadores y son los que vuelven a la nube, invariante 9).
    `apagada`: la consulta no corre en lo que queda del turno (fallback,
    orquestador): las marcas se retiran sin cortar."""
    consultas: int = 0
    bloques: list[str] = field(default_factory=list)
    tramos: list[str] = field(default_factory=list)
    tramos_crudos: list[str] = field(default_factory=list)
    sintetica: bool = False
    apagada: bool = False

    def reset(self) -> None:
        self.consultas = 0
        self.bloques = []
        self.tramos = []
        self.tramos_crudos = []
        self.sintetica = False
        self.apagada = False

    def puede_cortar(self) -> bool:
        """Bajo el tope y con la consulta encendida, una marca valida corta.
        Si no, se retira y el texto posterior vale (los dos regimenes del
        spec, a proposito)."""
        return not self.apagada and self.consultas < ABISMO_CONSULTAS_MAX


def prompt_reentrada(system_base: str, bloques: list[str],
                     tramos_crudos: list[str], mensaje: str) -> tuple[str, str]:
    """(system, mensaje de usuario) de la pasada sintetica. Los bloques van
    como append post-compile del system base del turno (construido UNA vez:
    no se re-corre recall ni economia). El parcial viaja por UNA sola via,
    el "venias diciendo" del mensaje, nunca como mensaje assistant. El
    mensaje original tambien viaja: `_history_messages` descarta el ultimo
    mensaje del chat (el de Pedro), asi que sin esto la reentrada no sabria
    que se le pregunto."""
    system = system_base + "".join("\n\n" + b for b in bloques if b)
    venia = "".join(tramos_crudos)
    usuario = f"{mensaje}\n\nVenias diciendo: {venia}\n{INSTRUCCION_CONTINUAR}"
    return system, usuario


def senal(fase: str, fuente: str, **campos) -> dict:
    """El dict de `{type:"abismo"}` con los campos fijos por fase (spec
    seccion 9): `verbo` en pondering, `tamano` + `viaje` en pescado,
    `motivo` (de la lista cerrada) en fallo. Lo que sobra en `campos` viaja
    tal cual."""
    if fase not in FASES:
        raise ValueError(f"fase desconocida: {fase!r}")
    s = {"type": "abismo", "fase": fase, "fuente": fuente}
    if fase == "pondering":
        s["verbo"] = campos.pop("verbo", None) or VERBOS.get(fuente, "consultando el abismo")
    elif fase == "pescado":
        s["tamano"] = int(campos.pop("tamano", 0))
        s["viaje"] = campos.pop("viaje", None) or {"destino": "local"}
    else:
        motivo = campos.pop("motivo", "error")
        s["motivo"] = motivo if motivo in MOTIVOS else "error"
    s.update(campos)
    return s


def motivo_de_consulta(resultado: dict) -> str:
    """El motivo de la senal `fallo` a partir de lo que devolvio
    `consulta.resolver`: la pesca vacia es `vacio` (el aviso exacto de
    consulta._fallo, "la consulta no trajo nada"); todo lo demas, `error`."""
    return "vacio" if resultado.get("aviso") == "la consulta no trajo nada" else "error"


def cortar_en_marca(texto: str) -> tuple[str, marca.Marca | None]:
    """El detector one-shot (suscripcion, spec secciones 4 y 8): la primera
    marca VALIDA corta. Devuelve (lo anterior a la marca, la marca) o (el
    texto entero, None). Las ilegibles anteriores quedan en el texto: el
    Emisor las retira con aviso, como en el stream."""
    texto = texto or ""
    for m in marca.PATRON.finditer(texto):
        valida = marca.parsear(m.group(1))
        if valida is not None:
            return texto[:m.start()], valida
    return texto, None


def prefijo_congelado(texto: str) -> str | None:
    """Para el preview de suscripcion: lo visible hasta la primera marca
    valida, o None si todavia no hay ninguna (el preview sigue avanzando)."""
    tramo, m = cortar_en_marca(texto)
    return tramo if m is not None else None


def retirar_marcas(texto: str) -> str:
    """Todas las marcas del abismo (validas e ilegibles) fuera del texto: lo
    que el CLI escribio despues de una marca que no se pudo atender."""
    return marca.PATRON.sub("", texto or "")


# una marca que abrio y todavia no cerro, al FINAL del texto (el mismo
# cuerpo sin corchetes que PATRON, pero sin exigir el cierre)
_ABIERTA_AL_FINAL = re.compile(
    re.escape(marca.ABRE) + r"abismo:[^" + marca.CIERRA + marca.ABRE + r"]{0,400}$")


def recortar_abierta(texto: str) -> str:
    """Para el preview de suscripcion: una marca del abismo a medio llegar al
    final del parcial se recorta, asi Pedro no la lee cruda entre dos tics
    (spec seccion 4: no lee texto que despues se descarta). Las cerradas las
    saca `_limpiar_marcas`; un prefijo suelto (`⟦abi`) se ve un tic, como
    con foco."""
    return _ABIERTA_AL_FINAL.sub("", texto or "")
```

Y en `calipso/server.py`, junto a los imports de la Task 2: `from calipso.abismo import turno as abismo_turno  # noqa: E402`.

- [ ] **Step 4: Verde y suite**

Run: `.venv/bin/python -m pytest -q test_abismo_turno.py`
Expected: `9 passed`

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
Expected: `1413 passed, 4 warnings`, `EXIT=0`.

- [ ] **Step 5: Commit**

```bash
git add calipso/abismo/turno.py calipso/server.py test_abismo_turno.py
git commit -m "feat(abismo): EstadoTurno, prompt_reentrada, senal por fase, detector one-shot (cortar_en_marca, prefijo_congelado, retirar_marcas)"
```

Nota sobre "aviso de telemetry" (orden sugerido, item 4): las filas `kind="abismo"` ya salen del `Emisor` (Task 2, `evento="retirada"`); las de la consulta (`evento="consulta"`, `"abortada_por_steer"`, `"reinvocacion_suscripcion"`) las escribe el server en las Tasks 6 y 7, que es donde nace el dato.

---

### Task 5: El contrato en el system de verdad -- local con nombres, nube sin nombres

**Files:**
- Modify: `calipso/catastro.py:496-501` (debajo de `obtener`: nueva `nombres()`)
- Modify: `calipso/prompt_compiler.py:15` (import) y `:62-89` (`internal_contract`: un elemento mas, el ultimo)
- Modify: `calipso/server.py:83` (import `abismo_contrato`), `:2704-2722` (`_SISTEMA_NUBE_MINIMO`, nueva `_NUBE_ABISMO_MARCADORES`, nueva `_sistema_nube()`, `_sistema_del_turno`)
- Modify: `test_privacidad_nube_system.py:17-19` (la asercion `resultado == srv._SISTEMA_NUBE_MINIMO` se pone en rojo con `_sistema_nube()`: se reescribe)
- Test: `test_abismo_contrato_vivo.py`, `test_privacidad_nube_system.py`

**Interfaces:**
- Consumes: `contrato.bloque_contrato(nombres_proyectos=()) -> str` (`calipso/abismo/contrato.py:24`); `catastro._file()`, `catastro._cargar_json()` (`calipso/catastro.py:102`, `:189`); `catastro.calipso_home()` relee `CALIPSO_HOME` en cada llamada (`:56`).
- Produces: `catastro.nombres() -> list[str]` (solo lee, nunca escanea). `prompt_compiler.internal_contract` termina con `abismo_contrato.bloque_contrato(catastro.nombres())`. `server._NUBE_ABISMO_MARCADORES: str`, `server._sistema_nube() -> str` (= `_SISTEMA_NUBE_MINIMO + "\n\n" + bloque_contrato(()) + "\n\n" + _NUBE_ABISMO_MARCADORES`); `_sistema_del_turno(..., a_la_nube_tapado=True)` devuelve `_sistema_nube()`.

- [ ] **Step 1: Tests en rojo**

```python
# test_abismo_contrato_vivo.py
"""El contrato del abismo dentro del system de verdad: en local con los
nombres del catastro (spec seccion 5), en /nube sin ellos (seccion 8.1)."""
import json

import calipso.server as srv
from calipso import catastro, prompt_compiler
from calipso.abismo import contrato, marca


def _catastro(tmp_path, monkeypatch, nombres):
    # catastro.calipso_home() relee la variable en cada llamada: alcanza setenv
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    (tmp_path / "catastro.json").write_text(json.dumps({
        "raices": [], "proyectos": [{"nombre": n, "ruta": f"/x/{n}"} for n in nombres]}),
        encoding="utf-8")


def test_nombres_no_escanea_nunca(tmp_path, monkeypatch):
    """El contrato corre en CADA turno y en tests con home vacio: un
    catastro que no existe da lista vacia, jamas un escaneo del disco."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))

    def bomba():
        raise AssertionError("el contrato no escanea el disco")
    monkeypatch.setattr(catastro, "escanear", bomba)
    assert catastro.nombres() == []
    _catastro(tmp_path, monkeypatch, ["calipso", "atlas"])
    assert catastro.nombres() == ["calipso", "atlas"]


def test_el_contrato_interno_ensena_la_marca_del_abismo_con_los_repos(tmp_path, monkeypatch):
    _catastro(tmp_path, monkeypatch, ["calipso", "atlas"])
    texto = prompt_compiler.internal_contract({}, base=tmp_path)
    assert texto.endswith(contrato.bloque_contrato(["calipso", "atlas"]))
    assert f"{marca.ABRE}abismo:proyecto nombre{marca.CIERRA} -- repo: calipso, atlas." in texto
    assert "⟦foco:<nombre>⟧" in texto          # el de foco sigue ahi, antes


def test_el_system_de_nube_lleva_el_contrato_sin_nombres(tmp_path, monkeypatch):
    _catastro(tmp_path, monkeypatch, ["calipso", "atlas"])
    nube = srv._sistema_del_turno("hola", "runtime", {}, True)
    assert nube.startswith(srv._SISTEMA_NUBE_MINIMO)
    assert contrato.bloque_contrato(()) in nube
    assert "calipso" not in nube and "atlas" not in nube
    assert "[TIPO_N]" in nube
    # y sin /nube el system sigue siendo el compilado de siempre
    monkeypatch.setattr(srv, "_build_context", lambda *a, **k: "COMPILADO")
    assert srv._sistema_del_turno("hola", "runtime", {}, False) == "COMPILADO"
```

Y en `test_privacidad_nube_system.py`, el primer test (`test_a_la_nube_tapado_usa_el_system_minimo_y_no_toca_build_context`) afirma hoy `resultado == srv._SISTEMA_NUBE_MINIMO` (`:17-19`): desde el abismo el system de nube ya no es el minimo pelado. Sus tres lineas finales pasan a:

```python
    resultado = srv._sistema_del_turno("mi dato", "rt", {}, a_la_nube_tapado=True)

    # desde el abismo el system de nube es el minimo MAS el contrato sin
    # nombres y la linea de marcadores (spec seccion 8.1): sigue sin tocar
    # _build_context
    assert resultado == srv._sistema_nube()
    assert resultado.startswith(srv._SISTEMA_NUBE_MINIMO)
    assert llamado == [], "no debe llamar a _build_context en /nube tapado"
```

(la docstring de ese test, "se devuelve `_SISTEMA_NUBE_MINIMO` tal cual", pasa a "se devuelve `_sistema_nube()`: el minimo mas el contrato del abismo sin nombres".)

- [ ] **Step 2: Verlos fallar**

Run: `.venv/bin/python -m pytest -q test_abismo_contrato_vivo.py test_privacidad_nube_system.py`
Expected: `4 failed, 1 passed` -- los tres del archivo nuevo (`AttributeError: module 'calipso.catastro' has no attribute 'nombres'`; el contrato no termina con el bloque; el system de nube es el minimo pelado) y el reescrito de `test_privacidad_nube_system.py` (`AttributeError: module 'calipso.server' has no attribute '_sistema_nube'`); `test_sin_nube_tapado_usa_el_contexto_completo` sigue en verde.

- [ ] **Step 3: `catastro.nombres()`**

En `calipso/catastro.py`, debajo de `obtener` (`:496-501`):

```python
def nombres() -> list[str]:
    """Los nombres del catastro SIN escanear jamas: para el contrato del
    abismo, que corre en cada turno y en tests con home vacio. Un catastro
    que todavia no existe da una lista vacia; el escaneo de la primera vez
    sigue siendo de `cargar()` (lo dispara `proyectos_brief` en el mismo
    turno). Orden: el de `cargar`, por `visto` descendente -- los mas usados
    primero, que es lo que el recorte del contrato quiere conservar."""
    if not _file().exists():
        return []
    return [p["nombre"] for p in _cargar_json()["proyectos"]]
```

- [ ] **Step 4: El bloque en `internal_contract`**

`calipso/prompt_compiler.py`, imports (`:15`, debajo de `from calipso import catastro`):

```python
from calipso.abismo import contrato as abismo_contrato
```

(cadena liviana: `contrato` importa solo `marca`, que importa `re` y `dataclasses`; NUNCA importar `fuentes` desde aca).

Y en `internal_contract` (`:68-89`), el ultimo elemento de la lista pasa de

```python
        f"Repo requerido: {'si' if needs_repo else 'no'}. Web requerida: {'si' if needs_web else 'no'}.",
    ])
```

a

```python
        f"Repo requerido: {'si' if needs_repo else 'no'}. Web requerida: {'si' if needs_web else 'no'}.",
        # El abismo (spec 2026-09-07, seccion 5): la sintaxis de la marca y
        # el indice de lo consultable, como bloque FINAL de esta seccion.
        # La letra esta medida (porton v2) y no se toca; lo unico que decide
        # este archivo es DONDE va: cuarta seccion de diez, no al final del
        # system como en el banco. Queda anotado, no se re-mide.
        abismo_contrato.bloque_contrato(catastro.nombres()),
    ])
```

- [ ] **Step 5: `_sistema_nube()` en `server.py`**

Import, junto a los de las Tasks 2-4: `from calipso.abismo import contrato as abismo_contrato  # noqa: E402`.

Debajo de `_SISTEMA_NUBE_MINIMO = (...)` (`:2704-2711`) y ANTES de `_sistema_del_turno`:

```python
# la linea que acompana al contrato en /nube: lo que suba del abismo ya paso
# por el viaje y puede traer los mismos marcadores que el mensaje.
_NUBE_ABISMO_MARCADORES = (
    "Lo que suba del abismo (el bloque \"Lo que subio del abismo\") puede "
    "traer marcadores [TIPO_N] como el mensaje: son datos tapados por "
    "privacidad, usalos tal cual y no intentes adivinarlos."
)


def _sistema_nube() -> str:
    """El system de un turno /nube tapado: el minimo de siempre + el contrato
    del abismo en su variante SIN nombres de repos (spec seccion 8.1: cero
    datos derivados de Pedro; el modelo pide por nombre y el nombre lo trae
    el mensaje, si lo trae) + la linea de los marcadores. En produccion el
    contrato va segundo, detras del minimo, no tercero de ocho secciones
    como en local; no se re-mide (los modelos de nube son mas capaces que
    el 7b con el que se calibro la letra)."""
    return "\n\n".join([_SISTEMA_NUBE_MINIMO,
                        abismo_contrato.bloque_contrato(()),
                        _NUBE_ABISMO_MARCADORES])
```

Y `_sistema_del_turno` (`:2714-2722`):

```python
def _sistema_del_turno(chat_msg: str, runtime: str, features: dict,
                       a_la_nube_tapado: bool) -> str:
    """El system del turno. Si el turno va a la nube tapado (/nube), NO se
    arma el contexto completo (recuerdos, economia, catastro) porque llevaria
    datos sensibles sin tapar a la nube: se usa el system minimo de nube, que
    desde el abismo lleva el contrato sin nombres (`_sistema_nube`). Si no,
    el contexto de siempre."""
    if a_la_nube_tapado:
        return _sistema_nube()
    return _build_context(chat_msg, runtime, features)
```

- [ ] **Step 6: Verde y suite**

Run: `.venv/bin/python -m pytest -q test_abismo_contrato_vivo.py test_privacidad_nube_system.py test_contrato_departamentos.py test_mapa_foco.py`
Expected: `3 passed` + `2 passed` + los de `test_contrato_departamentos.py` y `test_mapa_foco.py` sin cambios (miran `⟦foco:<nombre>⟧`, `no la ve`, `No la emitas`, que siguen en el texto).

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
Expected: `1416 passed, 4 warnings`, `EXIT=0`.

- [ ] **Step 7: Commit**

```bash
git add calipso/catastro.py calipso/prompt_compiler.py calipso/server.py test_abismo_contrato_vivo.py test_privacidad_nube_system.py
git commit -m "feat(abismo): el contrato entra al system de todos los turnos (local con los nombres del catastro, /nube sin nombres + linea de marcadores); catastro.nombres() sin escaneo"
```

Riesgos anotados: desde este commit el system de TODOS los turnos no-/nube ensena la marca (invariante 3 reformulada). Hasta la Task 6 el `Emisor` del turno NO lleva el filtro del abismo, asi que una marca que el 7b emita entre este commit y el siguiente saldria VISIBLE en el chat: la rama no se despliega a medias (las Tasks 5 y 6 aterrizan juntas en el merge). Las dos lineas "preguntame por nombre" de `proyectos_brief` (`prompt_compiler.py:456-457`) pasan de promesa vacia a promesa cumplida y se dejan como estan (reescribirlas cambia el texto medido de otra seccion; queda anotado para el smoke).

---

### Task 6: El cableado en local/API -- el bucle exterior, el tope, el steer, los salteos, la persistencia fusionada

**Files:**
- Modify: `calipso/server.py:83` (import `abismo_consulta`)
- Modify: `calipso/server.py:3176-3183` (estado de conexion: `estado_abismo`), `:3209` (reset), `:3428-3429` (el `Emisor` del turno con la tuberia), `:3521-3532` (rama orquestador: `apagada`), `:3533-3543` (rama suscripcion: `apagada`, provisorio hasta la Task 7), `:3544-3562` (rama local/api: el bucle exterior), `:3598-3607` y `:3649-3665` (los dos fallbacks: `apagada`), `:3701-3721` (`chat_turn` con `abismo_consultas`)
- Modify: `calipso/server.py:7159-7164` (debajo de `_limpiar_marcas`: `_zona_del_chat`, `_consolidado_personal`, `_pescar_abismo`)
- Test: `test_abismo_chat.py` (nueve tests mas)

**Interfaces:**
- Consumes: `abismo_filtro.FiltroAbismo(puede_cortar)`, `Emisor(filtros=...)`, `emisor.marca_abismo()` (Task 2); `abismo_viaje.preparar_viaje(bloques, destino, mapa, fuente=)` (Task 3); `abismo_turno.EstadoTurno`, `prompt_reentrada`, `senal`, `motivo_de_consulta` (Task 4); `abismo_consulta.resolver(m, *, mem, obtener, brief, consolidado, zona_chat)` (`calipso/abismo/consulta.py:21`); `catastro.obtener`, `_repo_brief`, el global `mem`, `_eco_personal.LibroPersonal(ruta).resumen()` (`calipso/economia/personal.py:27,51`), `_ECO_BASE`.
- Produces: `_zona_del_chat(departamento: str | None) -> str` (`"personal"` | `"fabrica"`); `_consolidado_personal() -> str | None`; `async _pescar_abismo(ws, m, estado, *, destino: str, mapa, departamento: str | None, agente_id: str | None = None, inbox: asyncio.Queue | None = None) -> bool` (True si hay bloque nuevo; `agente_id` queda reservado para el pulso, Task 9; con `inbox`, un steer que llego durante la pesca cierra la senal en `fallo` -motivo `error`, `MOTIVOS` es cerrada- y el bloque NO entra al estado: spec seccion 10, "bloque descartado, fase fallo, aviso"). El estado de conexion `estado_abismo: abismo_turno.EstadoTurno`. Telemetry: `kind="abismo"` con `evento="consulta"` (`fuente`, `resultado`, `motivo`|`chars`, `destino`, `tapados`, `consultas`, `latencia_ms`; el `motivo` de una pesca abortada por steer es `abortada_por_steer`) y `evento="abortada_por_steer"` con `momento` (`"pesca"` en el tope del bucle exterior, `"reentrada"` en el steer del bucle interior de una pasada sintetica; la Task 7 suma `"cli"`); `chat_turn` gana `abismo_consultas`.

- [ ] **Step 1: Los nueve tests en rojo (al final de `test_abismo_chat.py`)**

```python
import threading
import time


def _sembrar_chat_viejo(textos):
    """Otra conversacion, mas vieja, que la fuente `chats` puede pescar."""
    viejo = chats.create(str(srv.ROOT), "lecturas")
    for t in textos:
        chats.append(viejo["id"], "user", t)
    return viejo["id"]


def test_una_marca_valida_corta_pesca_y_la_continuacion_sigue_en_la_misma_burbuja(chat):
    _sembrar_chat_viejo(["empece El nombre de la rosa, es un libro alucinante"])
    # historial previo del MISMO chat: la reentrada tiene que llevarlo, y
    # sin el parcial (que todavia no se persistio); con un chat vacio la
    # asercion del historial seria vacua
    chats.append(chat.chat_id, "user", "hola")
    chats.append(chat.chat_id, "assistant", "hola Pedro")
    chat.modelo.guiones = [["Dejame ver ", "⟦abismo:chats libro⟧", " esto no se ve"],
                           ["y sigo ", "con contexto"]]
    eventos = chat.turno("que libro lei")
    tipos = [e["type"] for e in eventos]
    # la senal, con cierre
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "pescado"]
    assert abismo[0]["fuente"] == "chats" and abismo[0]["verbo"] == "buscando en tus chats"
    assert abismo[1]["tamano"] > 0 and abismo[1]["viaje"] == {"destino": "local"}
    # la marca no llega a Pedro, lo posterior a la marca se descarta y la
    # continuacion sigue sin cerrar la burbuja: un solo thinking, un solo done
    assert texto_visible(eventos) == "Dejame ver y sigo con contexto"
    assert tipos.count("done") == 1 and tipos.count("thinking") == 1
    assert tipos.index("abismo") > tipos.index("thinking")
    # dos invocaciones al modelo: la reentrada lleva el bloque como append del
    # system base, el "venias diciendo" en el mensaje, num_ctx fijado y el
    # historial SIN el parcial (que todavia no se persistio)
    assert len(chat.modelo.llamadas) == 2
    primera, segunda = chat.modelo.llamadas
    assert segunda["options"]["num_ctx"] == srv.CHAT_NUM_CTX
    system2 = segunda["messages"][0]["content"]
    assert system2.startswith(primera["messages"][0]["content"])
    assert "=== Lo que subio del abismo (fuente: chats) ===" in system2
    assert "El nombre de la rosa" in system2
    usuario2 = segunda["messages"][-1]["content"]
    assert usuario2.startswith("que libro lei")
    assert "Venias diciendo: Dejame ver " in usuario2
    # el historial normal viaja (`_history_messages` descarta solo el ultimo
    # mensaje, el de Pedro) y el parcial NO va como mensaje assistant: su
    # unica via es el "venias diciendo"
    assert segunda["messages"][1:3] == [{"role": "user", "content": "hola"},
                                        {"role": "assistant", "content": "hola Pedro"}]
    assert "Dejame ver" not in json.dumps(segunda["messages"][:-1])
    # persistencia fusionada: un solo par user/assistant nuevo, ya filtrado,
    # sin marca ni bloque; la memoria recuerda una sola vez
    assert [(m["role"], m["text"]) for m in chat.mensajes()] == [
        ("user", "hola"), ("assistant", "hola Pedro"),
        ("user", "que libro lei"), ("assistant", "Dejame ver y sigo con contexto")]
    crudo = (chat.tmp / "chats.json").read_text(encoding="utf-8")
    assert "⟦" not in crudo and "Lo que subio" not in crudo
    assert len(chat.memoria.recordado) == 1 and "⟦" not in chat.memoria.recordado[0]
    filas = chat.telemetria("abismo")
    assert [f["evento"] for f in filas] == ["consulta"]
    assert filas[0]["resultado"] == "pescado" and filas[0]["destino"] == "local"


def test_la_pasada_sintetica_no_repite_nada_del_turno(chat, monkeypatch):
    """Los catorce salteos del spec, medidos: meta, cost, chat/updated,
    thinking y done salen una vez; el pulso abre y cierra un solo escritorio;
    chat_turn se escribe una vez y cuenta la consulta; y los cuatro que el
    fixture patchea sin contar (_decide, goals.detect, _sistema_del_turno,
    _cobrar_turno) corren UNA vez: si una regresion los moviera adentro del
    bucle exterior, esto lo ve (todos se resuelven como globales del modulo
    en el momento de la llamada, asi que el monkeypatch alcanza)."""
    llamadas = {"decide": 0, "goals": 0, "system": 0, "cobro": 0}

    def decide(*a, **k):
        llamadas["decide"] += 1
        return _decide_local(*a, **k)
    monkeypatch.setattr(srv, "_decide", decide)
    monkeypatch.setattr(srv.goals, "detect",
                        lambda texto: llamadas.__setitem__("goals", llamadas["goals"] + 1))
    sistema_real = srv._sistema_del_turno

    def sistema(*a, **k):
        llamadas["system"] += 1
        return sistema_real(*a, **k)
    monkeypatch.setattr(srv, "_sistema_del_turno", sistema)
    cobrar_real = srv._cobrar_turno

    def cobrar(*a, **k):
        llamadas["cobro"] += 1
        return cobrar_real(*a, **k)
    monkeypatch.setattr(srv, "_cobrar_turno", cobrar)
    _sembrar_chat_viejo(["un libro"])
    chat.modelo.guiones = [["a ⟦abismo:chats libro⟧"], ["b"]]
    eventos = chat.turno("libro")
    tipos = [e["type"] for e in eventos]
    for tipo in ("thinking", "meta", "cost", "done"):
        assert tipos.count(tipo) == 1, tipo
    assert len([e for e in eventos if e["type"] == "chat" and e.get("action") == "updated"]) == 1
    pulso = [e["evento"] for e in chat.pulso.desde(0)[1]]
    assert pulso.count("inicio") == 1 and pulso.count("fin") == 1
    turnos = chat.telemetria("chat_turn")
    assert len(turnos) == 1 and turnos[0]["abismo_consultas"] == 1
    assert llamadas == {"decide": 1, "goals": 1, "system": 1, "cobro": 1}


def test_el_tope_de_tres_consultas_por_turno(chat):
    _sembrar_chat_viejo(["un libro"])
    chat.modelo.guiones = [["a ⟦abismo:chats libro⟧"], ["b ⟦abismo:chats libro⟧"],
                           ["c ⟦abismo:chats libro⟧"], ["d ⟦abismo:chats libro⟧ e"]]
    eventos = chat.turno("libros")
    fases = [a["fase"] for a in de_tipo(eventos, "abismo")]
    assert fases == ["pondering", "pescado"] * 3
    # la cuarta marca no corta: se retira con aviso y el texto posterior vale
    assert texto_visible(eventos) == "a b c d  e"
    assert len(chat.modelo.llamadas) == 4
    retiradas = [f for f in chat.telemetria("abismo") if f["evento"] == "retirada"]
    assert [f["clase"] for f in retiradas] == ["sin_corte"]
    assert chat.telemetria("chat_turn")[0]["abismo_consultas"] == 3
    # invariante 8: un mensaje real de Pedro resetea el contador, y el turno
    # siguiente vuelve a poder consultar
    chat.modelo.guiones = [["z ⟦abismo:chats libro⟧"], ["w"]]
    chat.modelo.llamadas.clear()      # el espia elige el guion por el indice global
    eventos = chat.turno("otra vez")
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "pescado"]
    assert texto_visible(eventos) == "z w"
    assert chat.telemetria("chat_turn")[-1]["abismo_consultas"] == 1


def test_la_pesca_vacia_es_fallo_y_la_reentrada_sigue_sin_bloque(chat):
    chat.modelo.guiones = [["Dejame ver ", "⟦abismo:chats zzzz⟧ nada"], ["y sigo"]]
    eventos = chat.turno("hola")
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "fallo"]
    assert abismo[1]["motivo"] == "vacio"
    assert texto_visible(eventos) == "Dejame ver y sigo"
    assert len(chat.modelo.llamadas) == 2
    assert "Lo que subio" not in chat.modelo.llamadas[1]["messages"][0]["content"]
    assert "Venias diciendo: Dejame ver " in chat.modelo.llamadas[1]["messages"][-1]["content"]


def test_una_consulta_que_revienta_degrada_a_seguir_sin_contexto(chat, monkeypatch):
    def bomba(m, **kw):
        raise RuntimeError("chroma caido")
    monkeypatch.setattr(srv.abismo_consulta, "resolver", bomba)
    chat.modelo.guiones = [["a ⟦abismo:memoria que leo⟧"], ["b"]]
    eventos = chat.turno("hola")
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "fallo"]
    assert abismo[1]["motivo"] == "error"
    assert texto_visible(eventos) == "a b"
    assert [e["type"] for e in eventos].count("done") == 1
    assert chat.telemetria("abismo")[0]["motivo"] == "error"


def test_una_marca_ilegible_se_retira_sin_cortar(chat):
    chat.modelo.guiones = [["hola ⟦abismo:memorai que dije⟧ sigo"]]
    eventos = chat.turno("hola")
    assert texto_visible(eventos) == "hola  sigo"
    assert de_tipo(eventos, "abismo") == [] and len(chat.modelo.llamadas) == 1
    assert [f["clase"] for f in chat.telemetria("abismo")] == ["ilegible"]


def test_una_marca_abierta_al_fin_del_stream_no_se_vuelca(chat):
    chat.modelo.guiones = [["termino asi ", "⟦abismo:chats sin cie"]]
    eventos = chat.turno("hola")
    assert texto_visible(eventos) == "termino asi "
    assert chat.mensajes()[-1]["text"] == "termino asi"
    assert [f["clase"] for f in chat.telemetria("abismo")] == ["abierta"]


def test_la_zona_y_el_consolidado_los_pone_el_server(chat, monkeypatch):
    """La frontera del consolidado del libro personal (spec seccion 6): solo
    llega a la fuente en un chat de zona personal, y la zona sale del prefijo
    de la cuenta del edificio tocado. Sin edificio: fabrica."""
    eco = chat.tmp / ".calipso" / "economia"
    eco.mkdir(parents=True)
    (eco / "personal.jsonl").write_text(json.dumps({
        "ts": "2026-09-01T10:00:00", "semana": "2026-W36", "tipo": "ingreso",
        "monto_mm": 1000, "categoria": "sueldo", "nota": ""}) + "\n", encoding="utf-8")
    visto = []

    def espia(m, **kw):
        visto.append((kw["zona_chat"], kw["consolidado"]))
        return {"estado": "fallo", "fuente": m.fuente, "texto": "", "bloques": [],
                "aviso": "la consulta no trajo nada"}
    monkeypatch.setattr(srv.abismo_consulta, "resolver", espia)
    for dep in ("personal:finanzas", "dep:atlas", None):
        chat.modelo.guiones = [["a ⟦abismo:memoria plata⟧"], ["b"]]
        chat.modelo.llamadas.clear()      # el espia elige el guion por el indice global
        chat.turno("hola", departamento=dep)
    assert visto == [("personal", "ingresos 1000 mm, gastos 0 mm, neto 1000 mm"),
                     ("fabrica", None), ("fabrica", None)]


def test_el_steer_de_pedro_gana_durante_la_pesca(chat, monkeypatch):
    """La carrera del spec (seccion 10): un steer que llega mientras se pesca
    aborta la consulta (sin reentrada, aviso en telemetry) y se procesa como
    hoy: es el turno siguiente. El steer viaja como texto crudo, como lo manda
    `planSend` de la PWA (el steer JSON de `send()` es una rareza previa que
    este plan no toca)."""
    visto, liberar = threading.Event(), threading.Event()

    def pesca_lenta(m, **kw):
        visto.set()
        liberar.wait(10)
        return {"estado": "pescado", "fuente": m.fuente, "texto": "=== bloque ===",
                "bloques": [("un bloque", 2)], "aviso": ""}
    monkeypatch.setattr(srv.abismo_consulta, "resolver", pesca_lenta)
    chat.modelo.guiones = [["Dejame ver ", "⟦abismo:chats libro⟧"], ["respuesta al steer"]]
    with chat.cliente.websocket_connect("/ws/chat") as ws:
        ws.send_text(chat.paquete("que libro lei"))
        assert visto.wait(10), "la pesca no arranco"
        ws.send_text("otra cosa")
        time.sleep(0.5)          # que el receptor lo deje en el inbox antes de soltar la pesca
        liberar.set()
        eventos = chat.recibir(ws, hasta_dones=2)
    tipos = [e["type"] for e in eventos]
    assert "steered" in tipos and tipos.count("done") == 2
    # la senal cerro en `fallo` (spec seccion 10: bloque descartado, fase
    # fallo, aviso): la pesca termino en su hilo, `_pescar_abismo` vio el
    # steer en el inbox y no dio `pescado`; MOTIVOS es cerrada, el motivo
    # de la senal es `error` y el de telemetry, `abortada_por_steer`
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "fallo"]
    assert de_tipo(eventos, "abismo")[1]["motivo"] == "error"
    assert tipos.index("steered") > tipos.index("abismo")
    # la consulta se aborto: sin reentrada; el steer fue el turno siguiente
    assert len(chat.modelo.llamadas) == 2
    assert chat.modelo.llamadas[1]["messages"][-1]["content"] == "otra cosa"
    assert "Venias diciendo" not in json.dumps(chat.modelo.llamadas)
    filas = chat.telemetria("abismo")
    assert [f["evento"] for f in filas] == ["consulta", "abortada_por_steer"]
    assert filas[0]["motivo"] == "abortada_por_steer" and filas[1]["momento"] == "pesca"
    roles = [(m["role"], m["text"].split(" ")[0]) for m in chat.mensajes()]
    assert roles == [("user", "que"), ("assistant", "Dejame"), ("user", "otra"), ("assistant", "respuesta")]
```

- [ ] **Step 2: Verlos fallar**

Run: `.venv/bin/python -m pytest -q test_abismo_chat.py`
Expected: `2 passed, 9 failed` (hoy la marca sale VISIBLE como chunk -- el `Emisor` del turno no lleva el filtro -- y no hay eventos `abismo`). Los tres que hacen `monkeypatch.setattr(srv.abismo_consulta, ...)` (el que revienta, el de la zona y el del steer) fallan en esa linea con `AttributeError: module 'calipso.server' has no attribute 'abismo_consulta'`: cuentan como FAILED y no como ERROR porque el `setattr` esta en el cuerpo del test, no en un fixture; y el del steer no llega a esperar en `visto.wait(10)` porque el `setattr` viene antes.

- [ ] **Step 3: El import, el estado de conexion y su reset**

Import, junto a los de las Tasks 2-5: `from calipso.abismo import consulta as abismo_consulta  # noqa: E402`.

En `ws_chat`, el bloque `departamento = None` (`:3183`) pasa a:

```python
    departamento = None
    # el estado del turno del abismo (spec seccion 4): vive junto al resto
    # del estado de la CONEXION porque atraviesa las reentradas sinteticas
    # de un turno, y lo resetea SOLO un mensaje real de Pedro (mas abajo,
    # donde paquete y steer ya convergieron en `user_msg`: invariante 8).
    estado_abismo = abismo_turno.EstadoTurno()
```

Y la linea `user_msg = user_msg.strip()` (`:3209`) pasa a:

```python
            user_msg = user_msg.strip()
            estado_abismo.reset()      # un mensaje real de Pedro, paquete o steer
```

- [ ] **Step 4: El `Emisor` del turno con la tuberia**

`emisor = Emisor(ws, agente_id=agente_id)` (`:3429`) pasa a:

```python
            # la tuberia de filtros del turno conversacional: foco primero,
            # abismo despues (spec seccion 4). `puede_cortar` mira el estado
            # del turno en el momento de cada marca: bajo el tope corta, con
            # el tope alcanzado o la consulta apagada retira sin cortar.
            emisor = Emisor(ws, agente_id=agente_id, filtros=[
                *([_mapa_foco.Filtro()] if _mapa_foco is not None else []),
                abismo_filtro.FiltroAbismo(puede_cortar=estado_abismo.puede_cortar)])
```

- [ ] **Step 5: Los tres helpers, debajo de `_limpiar_marcas` (`:7164`)**

```python
# --------------------------------------------------------------------------
# EL ABISMO (spec 2026-09-07, seccion 4): la consulta in-band del chat
# --------------------------------------------------------------------------
def _zona_del_chat(departamento: str | None) -> str:
    """La zona del turno sale del edificio que Pedro tiene tocado: la cuenta
    codifica la zona (`personal:` contra `dep:`, la inversa de
    `ficha.cuenta_pagadora`). Sin edificio tocado no hay senal de zona y la
    frontera falla cerrada: `fabrica`, que es la que NO deja pasar el
    consolidado del libro personal (spec seccion 6)."""
    return "personal" if (departamento or "").startswith("personal:") else "fabrica"


def _consolidado_personal() -> str | None:
    """El neto del libro personal, formateado para la fuente `memoria`. Lee
    SOLO el jsonl privado (invariante 11), sin candado ni libro de la
    fabrica; se llama en hilo y solo cuando la zona es personal, asi no se
    carga el archivo para que la frontera lo tire igual. La incoherencia
    preexistente con `_formatear_economia` (que mete el neto en el system
    de TODOS los turnos sin mirar zona) no se arregla aca."""
    if _eco_personal is None:
        return None
    ruta = _ECO_BASE / "economia" / "personal.jsonl"
    if not ruta.exists():
        return None
    r = _eco_personal.LibroPersonal(ruta).resumen()
    return (f"ingresos {r['ingresos_mm']} mm, gastos {r['gastos_mm']} mm, "
            f"neto {r['neto_mm']} mm")


async def _pescar_abismo(ws, m, estado, *, destino: str, mapa,
                         departamento: str | None,
                         agente_id: str | None = None,
                         inbox: asyncio.Queue | None = None) -> bool:
    """Una consulta al abismo de punta a punta: pondering -> resolver en
    hilo (100% local, invariante 1) -> viaje -> pescado/fallo. Cuenta la
    consulta contra el tope, acumula el bloque en el estado del turno y
    devuelve True si hay un bloque nuevo para la reentrada.

    Fallo cerrado en todo (invariante 4): cualquier excepcion degrada a
    "seguir sin contexto extra" con senal `fallo` y fila en telemetry; toda
    senal de pondering tiene cierre. `mem` se lee del modulo en el momento
    de resolver (se reasigna al cambiar de proyecto) y jamas se construye
    uno nuevo por consulta.

    El steer de Pedro gana (spec seccion 10): la pesca corre en hilo y no
    se interrumpe, pero si al volver hay algo en `inbox` la senal cierra en
    `fallo` (motivo `error`: MOTIVOS es cerrada y no tiene uno de aborto;
    el `steered` que sigue lo explica en la UI) y el bloque NO entra al
    estado -bloque descartado, aviso-. El bucle que llamo atiende el steer
    en su tope."""
    estado.consultas += 1
    await ws.send_json(abismo_turno.senal("pondering", m.fuente))
    inicio = time.perf_counter()
    motivo = ""
    motivo_telemetry = ""
    v: dict = {}
    try:
        zona = _zona_del_chat(departamento)
        consolidado = (await asyncio.to_thread(_consolidado_personal)
                       if zona == "personal" else None)
        r = await asyncio.to_thread(
            abismo_consulta.resolver, m, mem=mem, obtener=catastro.obtener,
            brief=_repo_brief, consolidado=consolidado, zona_chat=zona)
        if r["estado"] != "pescado":
            motivo = abismo_turno.motivo_de_consulta(r)
        else:
            v = await asyncio.to_thread(abismo_viaje.preparar_viaje, r["bloques"],
                                        destino, mapa, fuente=m.fuente)
            if v["estado"] != "viaja":
                motivo = v["motivo"]
    except Exception as exc:
        motivo = "error"
        print(f"[calipso] la consulta al abismo fallo: {exc}", file=sys.stderr)
    if not motivo and inbox is not None and not inbox.empty():
        # el steer de Pedro llego mientras se pescaba: la consulta se
        # cancela aca, antes de dar por pescado nada
        motivo, motivo_telemetry = "error", "abortada_por_steer"
    ms = round((time.perf_counter() - inicio) * 1000)
    if motivo:
        await ws.send_json(abismo_turno.senal("fallo", m.fuente, motivo=motivo))
        telemetry.log_event("abismo", evento="consulta", fuente=m.fuente,
                            resultado="fallo", motivo=motivo_telemetry or motivo,
                            destino=destino, consultas=estado.consultas,
                            latencia_ms=ms)
        return False
    estado.bloques.append(v["texto"])
    viaje_info = ({"destino": "local"} if destino == "local" else
                  {"destino": "nube", "tapados": v["tapados"],
                   "texto_tapado": v["texto"]})
    await ws.send_json(abismo_turno.senal("pescado", m.fuente,
                                          tamano=len(v["texto"]), viaje=viaje_info))
    telemetry.log_event("abismo", evento="consulta", fuente=m.fuente,
                        resultado="pescado", chars=len(v["texto"]), destino=destino,
                        tapados=len(v["tapados"]), consultas=estado.consultas,
                        latencia_ms=ms)
    return True
```

- [ ] **Step 6: El bucle exterior en la rama local/api**

La rama `else:` de `:3544-3562` (desde `gen, model = _chunks_for(route, system, mensaje_saliente, usage, model,` hasta `full += await emisor.chunk(chunk)`) se reemplaza ENTERA por:

```python
                else:
                    # EL ABISMO (spec seccion 4): el bucle de streaming de
                    # siempre, envuelto en un bucle exterior que reentra al
                    # modelo despues de cada consulta. Todo lo que esta
                    # afuera de este `while` (chats.append, mem.remember,
                    # _cobrar_turno, cost, done, emisor.cerrar) corre UNA vez
                    # por turno: esos son los catorce salteos de la pasada
                    # sintetica, gratis por construccion. El system base del
                    # turno se guarda una vez: la reentrada NO re-corre
                    # `_sistema_del_turno` (recall, economia bajo candado).
                    system_base = system
                    mensaje_turno = mensaje_saliente
                    destino = "nube" if a_la_nube_tapado else "local"
                    while True:
                        if estado_abismo.sintetica and not inbox.empty():
                            # el steer de Pedro gana (spec seccion 10): llego
                            # con el corte o durante la pesca (que ya cerro
                            # su senal en `fallo`). Se atiende como el
                            # barge-in de abajo sin abrir otro stream para
                            # cerrarlo enseguida; la consulta queda abortada
                            # y el proximo turno resetea el estado.
                            steer = inbox.get_nowait()
                            telemetry.log_event("abismo", evento="abortada_por_steer",
                                                consultas=estado_abismo.consultas,
                                                momento="pesca")
                            await ws.send_json({"type": "steered"})
                            full += " …(interrumpido)"
                            if steer and steer.strip() and steer.strip() != "/stop":
                                pending = steer
                            break
                        # un `usage` por pasada: los generadores ASIGNAN, no
                        # suman (dispatch.py:434-436, :487-489). Se acumula
                        # abajo. La pasada cortada nunca entrega el suyo
                        # (llega en el chunk final): en api es una
                        # subfacturacion real, declarada (invariante 5).
                        usage_pasada: dict = {}
                        gen, model = _chunks_for(route, system, mensaje_turno, usage_pasada,
                                                 model, verdict.get("effort"),
                                                 chat_id=chat_id_nube)
                        marca_pendiente = None
                        desde = len(full)
                        while True:
                            if not inbox.empty():  # steering: barge-in mientras responde
                                steer = inbox.get_nowait()
                                try:
                                    gen.close()
                                except Exception:
                                    pass
                                if estado_abismo.sintetica:
                                    # steer durante el stream de la reentrada
                                    # (spec seccion 10, "idem"): la fila de
                                    # aviso, ademas del steered de siempre
                                    telemetry.log_event("abismo", evento="abortada_por_steer",
                                                        consultas=estado_abismo.consultas,
                                                        momento="reentrada")
                                await ws.send_json({"type": "steered"})
                                full += " …(interrumpido)"
                                if steer and steer.strip() and steer.strip() != "/stop":
                                    pending = steer
                                break
                            chunk = await asyncio.to_thread(_next_or_stop, gen, sentinel)
                            if chunk is sentinel:
                                break
                            full += await emisor.chunk(chunk)
                            marca_pendiente = emisor.marca_abismo()
                            if marca_pendiente is not None:
                                # el corte: DESPUES de emisor.chunk (la marca
                                # ya salio del filtro) y ANTES de la proxima
                                # to_thread (ningun hilo esta iterando el
                                # generador). El mismo gesto que el steering.
                                try:
                                    gen.close()
                                except Exception:
                                    pass
                                break
                        for k in ("prompt_tokens", "completion_tokens"):
                            usage[k] = usage.get(k, 0) + usage_pasada.get(k, 0)
                        if marca_pendiente is None:
                            break
                        tramo = full[desde:]
                        estado_abismo.tramos.append(tramo)
                        estado_abismo.tramos_crudos.append(tramo)   # en streaming no hay reponer
                        if not inbox.empty():
                            # el steer llego con el corte: ni pondering ni
                            # pesca; el tope del bucle lo atiende
                            estado_abismo.sintetica = True
                            continue
                        # tras un `fallo` (pesca vacia, error, steer durante
                        # la pesca, o el viaje que no deja subir el bloque
                        # en /nube) se reentra SIN bloque (spec seccion 4,
                        # paso 4): en streaming el generador ya se cerro en
                        # la marca y "el texto posterior vale" (seccion 8.4)
                        # no existe. La regla literal de 8.4 la cumple solo
                        # la ruta one-shot (Task 7). Con steer, el tope del
                        # bucle aborta antes de abrir el stream.
                        await _pescar_abismo(ws, marca_pendiente, estado_abismo,
                                             destino=destino, mapa=mapa,
                                             departamento=departamento,
                                             agente_id=agente_id, inbox=inbox)
                        system, mensaje_turno = abismo_turno.prompt_reentrada(
                            system_base, estado_abismo.bloques,
                            estado_abismo.tramos_crudos, mensaje_saliente)
                        estado_abismo.sintetica = True
```

- [ ] **Step 7: Las ramas que NO consultan, y el `chat_turn`**

Cuatro sitios donde el texto entero pasa por `emisor.chunk(full)` o por otro bucle de streaming sin reentrada: ahi una marca valida NO puede cortar (truncaria la respuesta sin nadie que reentre). Antes de cada uno va `estado_abismo.apagada = True`:

1. Rama orquestador, antes de `full = await emisor.chunk(full)` (`:3532`):
```python
                    # ruta orquestador: fuera del abismo (spec seccion 4).
                    # Las marcas de los agentes ya se retiraron con
                    # _limpiar_marcas; una que llegue en la sintesis se
                    # retira con aviso, sin corte.
                    estado_abismo.apagada = True
                    full = await emisor.chunk(full)
```
2. Rama suscripcion, antes de `full = await emisor.chunk(full)` (`:3543`) -- PROVISORIO, la Task 7 lo reemplaza por el detector one-shot:
```python
                    estado_abismo.apagada = True   # hasta el cableado one-shot (Task 7)
                    full = await emisor.chunk(full)
```
3. Fallback entre suscripciones, antes de `full, queued = await _run_subscription_text_live(` (`:3598`):
```python
                                estado_abismo.apagada = True   # un turno que cayo al fallback no consulta
```
4. Fallback a local, antes de `gen, model = _chunks_for("local", system, chat_msg, usage, chat_id=chat_id)` (`:3649`):
```python
                        estado_abismo.apagada = True   # un turno que cayo al fallback no consulta
```

Y en `telemetry.log_event("chat_turn", ...)` (`:3701-3721`), debajo de `agent_team=agent_team,`:

```python
                abismo_consultas=estado_abismo.consultas,
```

- [ ] **Step 8: Verde y suite**

Run: `.venv/bin/python -m pytest -q test_abismo_chat.py`
Expected: `11 passed` (el de la carrera tarda medio segundo mas por el `sleep`).

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
Expected: `1425 passed, 4 warnings`, `EXIT=0`.

- [ ] **Step 9: Commit**

```bash
git add calipso/server.py test_abismo_chat.py
git commit -m "feat(abismo): la consulta cableada a ws_chat en local/api -- bucle exterior con corte del generador, pesca en hilo, reentrada sintetica sin repetir el turno, tope de 3, steer que gana, persistencia fusionada"
```

Riesgos anotados por los mapas, y como los cierra este cableado:
- El corte del generador va DESPUES de `emisor.chunk` y ANTES de la proxima `to_thread(_next_or_stop)` (mapa de rutas, seccion 7): nunca se cierra un generador que un hilo esta iterando.
- El steer gana en cuatro momentos: en el bucle interior (como hoy; en una pasada sintetica deja ademas la fila `abortada_por_steer` con `momento="reentrada"`), con el corte (el `if not inbox.empty()` antes de pescar), durante la pesca (`_pescar_abismo` mira el inbox al volver del hilo y cierra la senal en `fallo`, bloque descartado: la pesca no se interrumpe porque corre en hilo, pero no da `pescado`) y despues de la pesca (el tope del bucle exterior con `sintetica`, fila con `momento="pesca"`). Los tres ultimos no abren un stream nuevo para cerrarlo enseguida. El orden de senales que ve la UI en la carrera es `pondering` -> `fallo` -> `steered`.
- Desvio declarado del spec 8.4 en las rutas que streamean (local, api, `/nube /api`): un fallo POST-corte -pesca vacia, error, o viaje que no deja pasar el bloque- reentra SIN bloque (spec seccion 4, paso 4). El generador ya esta cerrado cuando la pesca o el viaje deciden y no existe "texto posterior" que valga. El regimen literal de 8.4 ("la reentrada NO se hace, el texto posterior vale") es el de la ruta one-shot (Task 7), donde el texto posterior existe. La Task 8 lo prueba con dos llamadas al modelo y lo deja aclarado en el spec.
- `full += " …(interrumpido)"` sigue siendo del steer, no del abismo; el corte por marca no agrega texto a `full`.
- El fallback local (`:3650-3665`) y el orquestador quedan con la consulta APAGADA, no cableada: un turno que cayo al fallback no consulta (declarado). El fallback rearma el system de cero y no sabe de los bloques pescados: si la reentrada revienta, la respuesta se rehace desde el fallback (conducta preexistente del fallback, compatible con la invariante 4).
- La reentrada en ruta api pierde el `usage` de la pasada cortada: subfacturacion real, declarada en el comentario del bucle y en `chat_turn.abismo_consultas`.
- El `Emisor` es unico por turno y `emisor.cerrar()` sigue corriendo UNA vez (`:3673`), fuera del bucle: entre pasadas no se vuelca lo retenido por foco.
- `estado_abismo` se declara con el estado de conexion: el `reset()` en `:3209` cubre paquete real y steer con una linea, y la reentrada (que no pasa por el `while` del turno) no lo toca.

---

### Task 7: El cableado en suscripcion (deteccion one-shot, preview congelado, reinvocacion, jobs limpios) + la ruta orquestador

**Files:**
- Modify: `calipso/server.py:2956-2960` (firma de `_run_subscription_text_live`: `congelar=None`), `:3011-3020` (el preview), `:3048`, `:3074`, `:3089` (los artefactos de jobs), `:3052-3055` (los tres `return` del `/stop`: segundo valor `"/stop"`), `:3066` (`msg = (stderr or partial or "").strip()`: limpio de marcas), `:2481` y `:2536` (`_run_dynamic_team`: `queued_msg` no se queda con un `"/stop"`), `:2505` (`mango.razonando(_limpiar_marcas(output))`: con aviso), `:3533-3543` (la rama de suscripcion: el bucle exterior one-shot)
- Test: `test_abismo_suscripcion.py`

**Interfaces:**
- Consumes: el harness de la Task 1 (`chat`, `de_tipo`, `texto_visible`); `abismo_turno.cortar_en_marca`, `prefijo_congelado`, `retirar_marcas`, `prompt_reentrada` (Task 4); `_pescar_abismo` (Task 6); `_subscription_command(client) -> str | None` (`calipso/server.py:2034`) y el template `dispatch.CONFIG["subscription"]["claude"]` (`["claude", "-p", "{prompt}"]`, que `_subscription_invocation` convierte en `[exe, "--append-system-prompt-file", <archivo>, "-p", <prompt>]`, `:2886-2894`); `jobs.artifact_path(project_root, job_id, name)` (`calipso/jobs.py:109`).
- Produces: `_run_subscription_text_live(ws, inbox, client, system, user_msg, model=None, label="proceso", chat_id=None, congelar: Callable[[str], str | None] | None = None)`; el `partial` del preview se congela en lo que devuelve `congelar` y una marca a medio llegar al final se recorta (`abismo_turno.recortar_abierta`); tras un `/stop` devuelve `"/stop"` como segundo valor (antes `None`): los llamadores lo dejan en `pending`, que el tope del turno ya trata como no-op (`if not user_msg or user_msg == "/stop": continue`), y `_run_dynamic_team` no lo deja pisar un texto real de Pedro; `output.txt`, `partial-output.txt` y el `msg` de un CLI que sale con error pasan por `_limpiar_marcas`. Telemetry `kind="abismo"`, `evento="reinvocacion_suscripcion"` (`client`, `consultas`) y `evento="abortada_por_steer"` con `momento="cli"`; la reinvocacion lleva `label=f"{etiqueta} (reentrada del abismo N)"` (un segundo registro de job, distinguible; no un cobro). Fixture `cli_falso` con `guion(pasos: list[{"partes": list[str], "pausa": float}])` y `llamadas() -> list[{"sistema", "prompt"}]` (la Task 8 lo reusa).

- [ ] **Step 1: Tests en rojo**

```python
# test_abismo_suscripcion.py
"""La consulta en la ruta one-shot (spec seccion 4, "Regla de las rutas"): no
hay stream que cortar, el detector lee el texto entero, la reentrada re-invoca
el CLI (dos invocaciones reales, declaradas) y el preview se congela en la
primera marca. Y la ruta orquestador, que queda fuera: sus marcas se retiran
con aviso."""
import asyncio
import json
import pathlib
import sys
import textwrap

import pytest

import calipso.server as srv
from calipso import jobs
from calipso.mapa import pulso as p
from test_abismo_chat import chat, de_tipo, texto_visible  # noqa: F401  (fixture + helpers)
from test_abismo_chat import _sembrar_chat_viejo


@pytest.fixture
def cli_falso(tmp_path, monkeypatch):
    """Un CLI de suscripcion de mentira: sigue un guion por invocacion (partes
    con pausa entre ellas, asi el preview de 2 s alcanza a verlas llegar) y
    anota el system y el prompt que recibio en llamada-N.json."""
    carpeta = tmp_path / "cli"
    carpeta.mkdir()
    script = carpeta / "claude_falso.py"
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''
        import json, pathlib, sys, time
        base = pathlib.Path(__file__).parent
        n = len(list(base.glob("llamada-*.json")))
        args = sys.argv[1:]
        sistema = ""
        if "--append-system-prompt-file" in args:
            ruta = args[args.index("--append-system-prompt-file") + 1]
            sistema = pathlib.Path(ruta).read_text(encoding="utf-8")
        prompt = args[args.index("-p") + 1] if "-p" in args else ""
        (base / f"llamada-{n}.json").write_text(
            json.dumps({"sistema": sistema, "prompt": prompt}), encoding="utf-8")
        guion = json.loads((base / "guion.json").read_text(encoding="utf-8"))
        paso = guion[min(n, len(guion) - 1)]
        for parte in paso["partes"]:
            sys.stdout.write(parte)
            sys.stdout.flush()
            time.sleep(paso.get("pausa", 0))
    '''), encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr(srv, "_subscription_command", lambda c: str(script))

    class CLI:
        def guion(self, pasos):
            (carpeta / "guion.json").write_text(json.dumps(pasos), encoding="utf-8")

        def llamadas(self):
            return [json.loads(f.read_text(encoding="utf-8"))
                    for f in sorted(carpeta.glob("llamada-*.json"))]
    return CLI()


def test_en_suscripcion_la_marca_corta_congela_el_preview_y_reinvoca(chat, cli_falso):
    _sembrar_chat_viejo(["empece El nombre de la rosa, es un libro alucinante"])
    # pausa 3.5: el bucle del preview tica a los 3.0 y 6.0 s (avisa cada 2 s
    # sobre un sleep de 1.5), asi que hay UN tic antes de la marca (parcial
    # "Dejame ver", sin espacio final por el strip de _read_partial) y UNO
    # despues (congelado en "Dejame ver "). Con 2.5 el unico tic caia a 0.45 s
    # de la segunda escritura y una maquina cargada lo dejaba en rojo.
    cli_falso.guion([{"partes": ["Dejame ver ", "⟦abismo:chats libro⟧ esto no se ve"], "pausa": 3.5},
                     {"partes": ["y sigo con contexto"], "pausa": 0}])
    eventos = chat.turno("/claude que libro lei")
    tipos = [e["type"] for e in eventos]
    assert texto_visible(eventos) == "Dejame ver y sigo con contexto"
    assert tipos.count("done") == 1
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "pescado"]
    # el preview: avanza hasta la marca y ahi se congela; nunca muestra lo
    # que despues se descarta, ni la marca
    parciales = [e["partial"] for e in de_tipo(eventos, "process") if e.get("action") == "running"]
    assert parciales and any(pp == "Dejame ver " for pp in parciales)
    assert not any("esto no se ve" in pp or "⟦" in pp for pp in parciales)
    # dos invocaciones reales: la segunda lleva el bloque en el system y el
    # "venias diciendo" en el prompt
    llamadas = cli_falso.llamadas()
    assert len(llamadas) == 2
    assert "=== Lo que subio del abismo (fuente: chats) ===" in llamadas[1]["sistema"]
    assert "El nombre de la rosa" in llamadas[1]["sistema"]
    assert "Venias diciendo: Dejame ver " in llamadas[1]["prompt"]
    assert "Lo que subio" not in llamadas[0]["sistema"]
    # declaradas en telemetry
    eventos_abismo = [f["evento"] for f in chat.telemetria("abismo")]
    assert eventos_abismo == ["consulta", "reinvocacion_suscripcion"]
    # los artefactos de los dos jobs no llevan la marca
    for ev in de_tipo(eventos, "process"):
        if ev.get("action") == "start":
            ruta = jobs.artifact_path(str(srv.ROOT), ev["job_id"], "output.txt")
            assert ruta.exists() and "⟦" not in ruta.read_text(encoding="utf-8")
    # y la persistencia sigue siendo un solo par, sin marca ni bloque
    assert [(m["role"], m["text"]) for m in chat.mensajes()] == [
        ("user", "/claude que libro lei"), ("assistant", "Dejame ver y sigo con contexto")]


def test_en_suscripcion_una_pesca_vacia_no_reinvoca_y_el_texto_posterior_vale(chat, cli_falso):
    """Spec seccion 8.4 aplicado al one-shot: sin bloque no hay reentrada;
    lo que el CLI escribio despues de la marca vale, sin marcas."""
    cli_falso.guion([{"partes": ["Dejame ver ⟦abismo:chats zzzz⟧ y sigo sin contexto"], "pausa": 0}])
    eventos = chat.turno("/claude hola")
    assert texto_visible(eventos) == "Dejame ver  y sigo sin contexto"
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "fallo"]
    assert de_tipo(eventos, "abismo")[1]["motivo"] == "vacio"
    assert len(cli_falso.llamadas()) == 1


def test_un_stop_durante_el_cli_no_pesca_ni_reinvoca(chat, cli_falso):
    """El gesto mas fuerte de Pedro (invariante 8): un /stop mata el CLI y NO
    dispara la pesca ni una segunda invocacion, aunque el parcial que el CLI
    alcanzo a escribir tenga una marca valida. Lo que alcanzo a escribir
    vale, sin la marca, con el "(proceso interrumpido)" de siempre."""
    _sembrar_chat_viejo(["un libro"])
    cli_falso.guion([{"partes": ["Dejame ver ⟦abismo:chats libro⟧", " tarde"], "pausa": 4.0}])
    with chat.cliente.websocket_connect("/ws/chat") as ws:
        ws.send_text(chat.paquete("/claude que libro lei"))
        primero = []
        while not any(e.get("type") == "process" and e.get("action") == "start" for e in primero):
            primero.append(ws.receive_json())      # thinking, meta, ..., process/start
        ws.send_text("/stop")                      # con el CLI vivo (lo atiende el tic de 1.5 s)
        eventos = primero + chat.recibir(ws)
    assert de_tipo(eventos, "abismo") == []
    assert len(cli_falso.llamadas()) == 1
    assert [e["type"] for e in eventos].count("done") == 1
    visible = texto_visible(eventos)
    assert visible.startswith("Dejame ver ") and "(proceso interrumpido)" in visible
    assert "⟦" not in visible and "tarde" not in visible
    assert [f["momento"] for f in chat.telemetria("abismo") if f["evento"] == "abortada_por_steer"] == ["cli"]


def test_en_suscripcion_la_cuarta_marca_no_corta(chat, cli_falso):
    """El tope en one-shot (spec seccion 4): la cuarta marca se retira con
    aviso, sin reinvocar, y el texto posterior vale."""
    _sembrar_chat_viejo(["un libro"])
    cli_falso.guion([{"partes": ["a ⟦abismo:chats libro⟧"], "pausa": 0}] * 3
                    + [{"partes": ["d ⟦abismo:chats libro⟧ e"], "pausa": 0}])
    eventos = chat.turno("/claude libros")
    assert [a["fase"] for a in de_tipo(eventos, "abismo")] == ["pondering", "pescado"] * 3
    assert texto_visible(eventos) == "a a a d  e" and len(cli_falso.llamadas()) == 4
    retiradas = [f for f in chat.telemetria("abismo") if f["evento"] == "retirada"]
    assert [f["clase"] for f in retiradas] == ["sin_corte"]


def test_en_suscripcion_una_marca_abierta_al_final_no_se_vuelca(chat, cli_falso):
    """Seccion 11 en one-shot: el texto del CLI pasa por el mismo Emisor, asi
    que una marca abierta al final se descarta con aviso y no se vuelca."""
    cli_falso.guion([{"partes": ["termino asi ⟦abismo:chats sin cie"], "pausa": 0}])
    eventos = chat.turno("/claude hola")
    assert texto_visible(eventos) == "termino asi "
    assert de_tipo(eventos, "abismo") == [] and len(cli_falso.llamadas()) == 1
    assert [f["clase"] for f in chat.telemetria("abismo")] == ["abierta"]


def test_los_archivos_temporales_de_las_dos_invocaciones_se_borran(chat, cli_falso, monkeypatch):
    """El bloque pescado viaja a la reinvocacion en el archivo del system
    (`--append-system-prompt-file`, un `.md` en el tmpdir del sistema), no en
    el `.prompt.md` de ROOT (que solo existe con prompts de mas de 7000
    chars): `_cleanup_subscription_files` los borra en el finally, en las
    DOS invocaciones. Es un sumidero del bloque; el smoke lo re-mira."""
    creados = []
    real = srv.tempfile.NamedTemporaryFile

    def espia(*a, **k):
        f = real(*a, **k)
        creados.append(f.name)
        return f
    monkeypatch.setattr(srv.tempfile, "NamedTemporaryFile", espia)
    _sembrar_chat_viejo(["un libro"])
    cli_falso.guion([{"partes": ["a ⟦abismo:chats libro⟧"], "pausa": 0},
                     {"partes": ["b"], "pausa": 0}])
    chat.turno("/claude libro")
    sistemas = [n for n in creados if n.endswith(".md")]
    assert len(sistemas) == 2, creados            # un archivo de system por invocacion
    assert not any(pathlib.Path(n).exists() for n in creados)


def test_el_agente_de_equipo_no_publica_la_marca_del_abismo_al_pulso(monkeypatch):
    """La ruta orquestador queda FUERA (spec seccion 4): la marca que emita un
    agente se retira via _retirar_con_aviso + _limpiar_marcas y se ignora
    CON aviso (fila en telemetry). El molde de test_mapa_foco.py:139-176,
    con la marca del abismo."""
    pu = p.Pulso()
    monkeypatch.setattr(srv, "EL_PULSO", pu)
    monkeypatch.setattr(srv, "_plan_dynamic_team", lambda *a, **k: {"plan": 1})
    monkeypatch.setattr(srv, "_backend_availability", lambda *a, **k: {})
    monkeypatch.setattr(srv.sessions, "active", lambda *a, **k: None)
    monkeypatch.setattr(srv.orchestrator, "build_team", lambda *a, **k: {
        "agents": [{"role": "scout", "task": "mira", "model": "sonnet",
                    "persona": "explorador", "route": "api"}],
        "synthesis": ""})
    monkeypatch.setattr(srv.orchestrator, "agent_system", lambda *a, **k: "s")
    monkeypatch.setattr(srv.orchestrator, "synthesis_prompt", lambda *a, **k: "u")
    filas = []
    monkeypatch.setattr(srv.telemetry, "log_event",
                        lambda kind, **k: filas.append({"kind": kind, **k}))
    monkeypatch.setattr(srv, "_run_backend_text", lambda *a, **k: "listo")

    async def _agente(ws, inbox, agent, system, task):
        return "vamos a ⟦abismo:chats x⟧ mirar", None
    monkeypatch.setattr(srv, "_run_agent_text", _agente)

    class WSFalso:
        def __init__(self):
            self.enviados = []

        async def send_json(self, dato):
            self.enviados.append(dato)

    final, _, _ = asyncio.run(srv._run_dynamic_team(
        WSFalso(), asyncio.Queue(), "hace algo", {}, "base",
        {"route": "api", "client": None, "model": "m"}, departamento="dep:atlas"))
    assert final == "listo"
    razonado = "".join(e.get("texto", "") for e in pu.desde(0)[1] if e["evento"] == "razonando")
    assert razonado == "vamos a  mirar" and "⟦" not in razonado
    # "se ignoran CON aviso": una fila por retiro, con la cantidad
    retiradas = [f for f in filas if f["kind"] == "abismo" and f.get("evento") == "retirada"]
    assert [(f["clase"], f["cantidad"]) for f in retiradas] == [("agente", 1)]
```

- [ ] **Step 2: Verlos fallar**

Run: `.venv/bin/python -m pytest -q test_abismo_suscripcion.py`
Expected: `2 passed, 5 failed`. Fallan: los dos de la marca que pesca (hoy el texto entero pasa por `emisor.chunk` con la consulta apagada, asi que la marca se retira sin pescar -`assert [...] == ["pondering", "pescado"]` da `[]`- y hay una sola invocacion), el de la cuarta marca (idem), el de los temporales (una sola invocacion: `len(sistemas) == 2` da 1) y el del orquestador (la marca ya se retira -Task 2- pero sin la fila `retirada`). Pasan ya el del `/stop` y el de la marca abierta: son guardas de regresion del cableado one-shot -el del `/stop` vuelve a rojo si el Step 4 se hiciera sin el cambio de los `return` del Step 3-.

- [ ] **Step 3: `congelar` y los artefactos limpios en `_run_subscription_text_live`**

La firma (`:2956-2960`) pasa a:

```python
async def _run_subscription_text_live(
        ws: WebSocket, inbox: asyncio.Queue, client: str, system: str,
        user_msg: str, model: str | None = None,
        label: str = "proceso",
        chat_id: str | None = None,
        congelar=None) -> tuple[str, str | None]:
    """`congelar(parcial) -> str | None`: cuando devuelve un texto, el preview
    `process/running` se congela ahi (spec seccion 4: Pedro no lee texto que
    despues se descarta). El proceso corre a termino igual; matarlo por una
    marca dejaria un job en estado raro y perderia la parte util."""
```

Debajo de `pending_msg: str | None = None` (`:2965`): `preview_congelado: str | None = None`.

El preview (`:3011-3020`, desde `if now - last_notice >= 2:` hasta la linea del `"hint"`) pasa a:

```python
            if now - last_notice >= 2:
                partial, _ = _read_partial()
                if congelar is not None and preview_congelado is None and partial:
                    preview_congelado = congelar(partial)
                muestra = partial if preview_congelado is None else preview_congelado
                # una marca a medio llegar al final del parcial se recorta
                # (Pedro no la lee cruda entre dos tics); las cerradas las
                # saca _limpiar_marcas
                muestra = abismo_turno.recortar_abierta(muestra)
                await ws.send_json({
                    "type": "process", "action": "running",
                    "job_id": job["id"],
                    "label": label, "client": client, "model": model,
                    "elapsed": round(now - started),
                    "tokens": max(1, ((len(system) + len(user_msg)) + len(partial)) // 4),
                    "partial": _limpiar_marcas(muestra)[-3000:] if muestra else "",
                    "hint": "sigue corriendo; envia /stop para cancelar o escribe y lo atiendo al terminar"})
```

El `jobs.event(str(ROOT), job["id"], "running", elapsed=..., tokens=...)` de `:3021-3024` y el `last_notice = now` de `:3025` que siguen quedan como estan (reemplazar de mas deja un `tokens=max(...))` colgado y `SyntaxError` al importar `calipso.server`).

Los tres `return` del camino `/stop` (`:3052-3055`, dentro de `if clean == "/stop":`) devuelven `"/stop"` como segundo valor en vez de `None`: un `/stop` durante el CLI es el gesto mas fuerte de Pedro y el bucle one-shot del Step 4 lo tiene que ver como steer (sin pesca, sin reinvocacion). Para los llamadores de hoy es un no-op: `pending = "/stop"` y el tope del `while` del turno hace `if not user_msg or user_msg == "/stop": continue` (`:3210`).

```python
                    if partial:
                        return partial + "\n\n...(proceso interrumpido)", "/stop"
                    if stderr:
                        return stderr + "\n\n...(proceso interrumpido)", "/stop"
                    return "...(proceso interrumpido sin salida parcial)", "/stop"
```

En `_run_dynamic_team`, las dos acumulaciones `queued_msg = queued_msg or queued` (`:2481` tras `_run_agent_text`, y `:2536` tras la sintesis por suscripcion) pasan a:

```python
                # "/stop" (el CLI de un agente interrumpido) no es un mensaje
                # para despues: no pisa lo que Pedro escriba durante otro agente
                queued_msg = queued_msg or (queued if queued != "/stop" else None)
```

(la misma linea en los dos sitios; asi la conducta del equipo queda identica a la de hoy, donde el `/stop` devolvia `None`).

El `msg` del CLI que sale con error (`:3066`, `msg = (stderr or partial or "").strip()`) pasa a `msg = _limpiar_marcas(stderr or partial or "").strip()`: ese `msg` va a `jobs.update(error=msg)`, a `jobs.event(error=msg[:1000])` y, via el `RuntimeError`, a `fallbacks[].error` de `chat_turn` en telemetry -tres sumideros que la seccion 4 del spec prohibe para la marca-.

Y los tres artefactos:
- `:3048`: `jobs.write_artifact(str(ROOT), job["id"], "partial-output.txt", _limpiar_marcas(partial))`
- `:3074`: `jobs.write_artifact(str(ROOT), job["id"], "partial-output.txt", _limpiar_marcas(partial))`
- `:3089`: `jobs.write_artifact(str(ROOT), job["id"], "output.txt", _limpiar_marcas(text))`

- [ ] **Step 4: El bucle one-shot en la rama de suscripcion**

La rama `elif route == "subscription":` (`:3533-3543`, incluido el `estado_abismo.apagada = True` provisorio de la Task 6) se reemplaza ENTERA por:

```python
                elif route == "subscription":
                    # EL ABISMO en la ruta one-shot (spec secciones 4 y 8):
                    # no hay stream que cortar. El detector lee el texto
                    # entero cuando vuelve; la primera marca valida corta (lo
                    # posterior vino sin contexto y se descarta) y la
                    # reentrada re-invoca el CLI completo: una consulta son
                    # DOS invocaciones reales, declaradas en telemetry (el
                    # probe pasivo de consumo las ve). Si la consulta falla,
                    # o el steer gana, no se reinvoca: lo que el CLI escribio
                    # despues de la marca vale, sin marcas (seccion 8.4).
                    system_base = system
                    mensaje_turno = mensaje_saliente
                    destino = "nube" if a_la_nube_tapado else "local"
                    etiqueta = f"{verdict.get('persona') or verdict['client']} via {verdict['client']}"
                    while True:
                        texto, queued = await _run_subscription_text_live(
                            ws, inbox, verdict["client"], system, mensaje_turno, model,
                            # la reentrada deja un SEGUNDO registro de job (no
                            # un cobro): que se distinga en el panel y en
                            # process/start
                            label=(etiqueta if not estado_abismo.sintetica else
                                   f"{etiqueta} (reentrada del abismo {estado_abismo.consultas})"),
                            chat_id=chat_id_nube,
                            congelar=abismo_turno.prefijo_congelado)
                        if queued:
                            pending = queued     # un texto de Pedro, o "/stop" (no-op en el tope del turno)
                        usage["completion_tokens"] = (usage.get("completion_tokens", 0)
                                                      + len(texto.split()))
                        tramo_crudo, marca_valida = abismo_turno.cortar_en_marca(texto)
                        if marca_valida is not None and not estado_abismo.puede_cortar():
                            # tope alcanzado: la marca se retira (lo hace el
                            # filtro, con aviso) y el texto posterior vale
                            tramo_crudo, marca_valida = texto, None
                        # en /nube la nube escribe con marcadores: se repone
                        # lo visible; lo CRUDO es lo que vuelve a la nube
                        visible = (redaccion.reponer(tramo_crudo, mapa)
                                   if mapa is not None else tramo_crudo)
                        visible = await emisor.chunk(visible)
                        full += visible
                        if marca_valida is None:
                            break
                        estado_abismo.tramos.append(visible)
                        # crudo (con marcadores, invariante 9) pero SIN las
                        # marcas ilegibles anteriores al corte: el modelo no
                        # tiene que releer su propia marca fallida en el
                        # "venias diciendo" (los marcadores [ID_N] no son marcas)
                        estado_abismo.tramos_crudos.append(abismo_turno.retirar_marcas(tramo_crudo))
                        if queued:
                            # el steer de Pedro gana (spec seccion 10); tambien
                            # el /stop, que ya mato al CLI: ni pesca ni reinvocacion
                            telemetry.log_event("abismo", evento="abortada_por_steer",
                                                consultas=estado_abismo.consultas,
                                                momento="cli")
                            hubo_bloque = False
                        else:
                            hubo_bloque = await _pescar_abismo(
                                ws, marca_valida, estado_abismo, destino=destino,
                                mapa=mapa, departamento=departamento,
                                agente_id=agente_id, inbox=inbox)
                        if not hubo_bloque:
                            # lo posterior a la marca vale (seccion 8.4, la
                            # letra exacta: aca el texto posterior existe).
                            # Sus marcas se retiran CON aviso por fuera del
                            # filtro, que con la consulta a medias no puede
                            # volver a cortar (dejaria una marca pendiente
                            # que nadie consume)
                            resto_crudo = _retirar_con_aviso(texto[len(tramo_crudo):], "posterior")
                            full += await emisor.chunk(
                                redaccion.reponer(resto_crudo, mapa)
                                if mapa is not None else resto_crudo)
                            break
                        system, mensaje_turno = abismo_turno.prompt_reentrada(
                            system_base, estado_abismo.bloques,
                            estado_abismo.tramos_crudos, mensaje_saliente)
                        estado_abismo.sintetica = True
                        telemetry.log_event("abismo", evento="reinvocacion_suscripcion",
                                            client=verdict["client"],
                                            consultas=estado_abismo.consultas)
```

Y en `_run_dynamic_team` (`:2505`), el retiro de las marcas de un agente gana el aviso que el spec exige (seccion 4: "se ignoran con aviso"):

```python
            mango.razonando(_limpiar_marcas(_retirar_con_aviso(output, "agente")))
```

- [ ] **Step 5: Verde y suite**

Run: `.venv/bin/python -m pytest -q test_abismo_suscripcion.py`
Expected: `7 passed` (el primero tarda unos 10 s: siete del CLI falso con sus pausas de 3.5 s y el tic de 1.5 s del bucle; el del `/stop` unos 3 s; el archivo entero, cerca de 25 s).

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
Expected: `1432 passed, 4 warnings`, `EXIT=0`.

- [ ] **Step 6: Commit**

```bash
git add calipso/server.py test_abismo_suscripcion.py
git commit -m "feat(abismo): la consulta en suscripcion -- detector one-shot, preview congelado en la marca, reinvocacion real del CLI declarada, artefactos de jobs sin marca; la ruta orquestador retira la marca con aviso"
```

Riesgos anotados por los mapas:
- Dos archivos temporales por invocacion llevan texto del turno (`_subscription_invocation`, `:2866-2894`): el `.prompt.md` DENTRO de `ROOT` (solo si el prompt pasa los 7000 chars; lleva el historial y el "venias diciendo") y el `.md` del system en el tmpdir del sistema (`--append-system-prompt-file`; es ESTE el que lleva el bloque pescado en la reinvocacion). Los dos los borra `_cleanup_subscription_files` en el `finally` de `_run_subscription_text_live` (`:3110`): `test_los_archivos_temporales_de_las_dos_invocaciones_se_borran` lo afirma con el CLI falso, y el smoke (Task 13) re-mira los dos despues de una /nube.
- El fallback entre suscripciones (`:3565-3616`) sigue one-shot y APAGADO: si la reinvocacion revienta, el fallback REASIGNA `full` con la respuesta del otro cliente (conducta preexistente del fallback: la respuesta se rehace de cero, con el system recompilado). Declarado, no se toca.
- El cobro por suscripcion sigue siendo UNA unidad por turno (`_cobrar_turno`, `:7286-7287`): el libro subestima la segunda invocacion; el spec ya lo decidio (invariante 5) y la fila `reinvocacion_suscripcion` es la declaracion.
- `_run_agent_text` (`:2396-2407`) llama a `_run_subscription_text_live` sin `congelar`: los agentes del orquestador no congelan nada, y sus marcas se retiran con aviso en `:2505`.
- Los agentes del orquestador HEREDAN el contrato del abismo por `base_system` (`orchestrator.agent_system(agent, base_system, ...)`, preexistente con foco): reciben "Ante la duda, CONSULTA", consultan al vacio y su marca se retira con aviso; el agente sigue como si hubiera tenido el contexto. Es la lectura que este plan toma de la seccion 11 ("ni ensenan el contrato"); quitar el bloque de `agent_system` es de la rebanada 4 (jefes que consultan).
- La reinvocacion deja un segundo registro de job (`jobs.start` con la etiqueta "(reentrada del abismo N)") y un segundo `process/start`: un registro, no un cobro (invariante 5). La fila `reinvocacion_suscripcion` lleva `consultas`, que es el N de la etiqueta: asi se correlacionan.
- Un `/stop` durante el CLI vuelve como `queued == "/stop"`: el bucle lo trata como steer (ni pesca ni reinvocacion; el parcial vale, sin la marca), `pending = "/stop"` es un no-op en el tope del turno, y en el equipo dinamico no pisa un texto real. Antes de este cambio un `/stop` sobre un parcial con marca valida pescaba y RE-INVOCABA el CLI contra el gesto mas fuerte de Pedro.

---

### Task 8: /nube -- destino, mapa, crudo contra repuesto, credencial que no sale, bloque que no se persiste

**Files:**
- Modify: `docs/superpowers/specs/2026-09-07-abismo-consulta-design.md` (seccion 8, punto 4: una oracion de aclaracion, Step 3)
- Test: `test_abismo_nube.py` (nuevo; el cableado de `destino`/`mapa`/system base ya quedo puesto en las Tasks 5-7 -- esta task lo PRUEBA de punta a punta y corrige lo que los tests encuentren)

**Interfaces:**
- Consumes: el harness (`chat`, `ModeloEspia` cubre `_sse_text_chunks`), `cli_falso` y `_sembrar_chat_viejo`; `juez.detector.detectar_secretos` y `juez.juez_llm.juzgar_llm` como dobles (el molde de `test_privacidad_juez.py:4-6`); `conversacion.mapa_para(chat_id)` (`calipso/privacidad/conversacion.py:14`); `srv._SISTEMA_NUBE_MINIMO`, `contrato.bloque_contrato(())`.
- Produces: la prueba de las cuatro decisiones de la seccion 8 del spec y de las invariantes 2 y 9. Ningun simbolo nuevo.

Que hace hoy cada ruta con /nube, para leer los tests: `/nube /api` fuerza `route == "api"` (`ruteo_para_nube` respeta la ruta forzada, `nube.py:56`), asi que la consulta corta EN VIVO en el bucle de la Task 6 con `destino="nube"` y `mapa` real; el system es `_sistema_nube()`; el historial va apagado (`chat_id_nube=None`). La rama api de streaming NO repone marcadores en vivo (preexistente: solo las ramas one-shot y el fallback llaman `redaccion.reponer`, `:3531`, `:3542`, `:3606`), asi que en api los tramos crudos y visibles coinciden. `/nube /claude` va por suscripcion: ahi si hay `reponer`, y es donde se prueba el canario de los tramos crudos.

Y como se lee el punto 4 de la seccion 8 ("cuando el bloque no puede viajar, la nube sigue sin el") en cada ruta: en `/nube /api` (streaming) el generador ya esta cerrado cuando el viaje decide, asi que la nube "sigue sin el bloque" por REENTRADA sin bloque (spec seccion 4, paso 4): dos llamadas al modelo, la segunda sin "Lo que subio"; no existe "texto posterior" que valga. En `/nube /claude` (one-shot) se cumple la letra exacta: sin reinvocar, y lo que el CLI escribio despues de la marca vale. Los tests de abajo fijan las dos lecturas, y el Step 3 deja la aclaracion escrita en el spec.

- [ ] **Step 1: Tests en rojo**

```python
# test_abismo_nube.py
"""El turno /nube con modelo falso por TestClient (spec seccion 15, enmienda
2026-09-08): el contrato de nube viaja sin nombres; el bloque viaja tapado
con el mapa de la conversacion y se ve que viajo; una credencial en lo
pescado no aparece en ningun envio; solo hondo sigue sin bloque; los tramos
que vuelven a la nube son los crudos, no los repuestos; el bloque no se
persiste; el done es uno solo."""
import json

import calipso.server as srv
from calipso.abismo import contrato
from calipso.privacidad import juez
from test_abismo_chat import chat, de_tipo, texto_visible  # noqa: F401
from test_abismo_chat import _sembrar_chat_viejo
from test_abismo_suscripcion import cli_falso  # noqa: F401


def _juez_que_tapa_a_marta(monkeypatch, con_credencial=False):
    """El juez de dos capas, doble: Marta es identidad (se tapa) y, si se
    pide, cualquier texto con `ghp_` es credencial (corta el envio)."""
    monkeypatch.setattr(juez.detector, "detectar_secretos",
                        lambda t: ([{"texto": "ghp_abcdef", "tipo": "credencial"}]
                                   if con_credencial and "ghp_" in t else []))
    monkeypatch.setattr(juez.juez_llm, "juzgar_llm",
                        lambda t: {"ok": True, "tramos": (
                            [{"texto": "Marta", "tipo": "identidad"}] if "Marta" in t else [])})


def test_en_nube_el_bloque_viaja_tapado_con_el_mapa_del_mensaje_y_se_ve(chat, monkeypatch):
    _juez_que_tapa_a_marta(monkeypatch)
    _sembrar_chat_viejo(["con Marta hablamos del libro de cocina"])
    chat.modelo.guiones = [["Le dije a [ID_1] que ", "⟦abismo:chats libro⟧", " fin"],
                           ["y seguimos"]]
    eventos = chat.turno("/nube /api que hablamos con Marta del libro")
    tipos = [e["type"] for e in eventos]
    assert tipos.count("done") == 1
    tapado = [e for e in eventos if e["type"] == "privacidad"][0]
    assert tapado["action"] == "tapado" and tapado["texto_tapado"] == "que hablamos con [ID_1] del libro"
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "pescado"]
    viaje = abismo[1]["viaje"]
    assert viaje["destino"] == "nube"
    assert viaje["tapados"] == [{"marcador": "[ID_1]", "tipo": "identidad"}]
    assert "Marta" not in viaje["texto_tapado"] and "[ID_1]" in viaje["texto_tapado"]
    # el segundo envio: system minimo + contrato SIN nombres + el bloque
    # tapado, sin historial (chat_id_nube=None) y con el mensaje tapado
    primera, segunda = chat.modelo.llamadas
    system2 = segunda["messages"][0]["content"]
    assert system2.startswith(srv._SISTEMA_NUBE_MINIMO)
    assert contrato.bloque_contrato(()) in system2
    assert "=== Lo que subio del abismo (fuente: chats) ===" in system2
    assert "Marta" not in json.dumps(chat.modelo.llamadas)
    assert [m["role"] for m in segunda["messages"]] == ["system", "user"]
    assert segunda["messages"][1]["content"].startswith("que hablamos con [ID_1] del libro")
    assert "Venias diciendo: Le dije a [ID_1] que " in segunda["messages"][1]["content"]
    # el bloque no se persiste ni se recuerda
    crudo = (chat.tmp / "chats.json").read_text(encoding="utf-8")
    assert "Lo que subio" not in crudo and "cocina" not in chat.mensajes()[-1]["text"]
    assert not any("Lo que subio" in r for r in chat.memoria.recordado)
    assert chat.telemetria("abismo")[0]["destino"] == "nube"


def test_en_nube_una_credencial_en_lo_pescado_no_sale_y_la_nube_sigue_sin_bloque(chat, monkeypatch):
    _juez_que_tapa_a_marta(monkeypatch, con_credencial=True)
    _sembrar_chat_viejo(["el token del libro es ghp_abcdef no lo pierdas"])
    chat.modelo.guiones = [["Dejame ver ", "⟦abismo:chats libro⟧"], ["y sigo"]]
    eventos = chat.turno("/nube /api que libro tenia token")
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "fallo"]
    assert abismo[1]["motivo"] == "credencial"
    # la nube sigue sin el bloque: en las rutas en vivo eso es la reentrada
    # sin bloque (seccion 4 paso 4; ver el preambulo), o sea DOS llamadas, la
    # segunda sin "Lo que subio"; y el secreto no aparece en NINGUN envio ni
    # en la telemetria
    assert len(chat.modelo.llamadas) == 2
    assert "ghp_" not in json.dumps(chat.modelo.llamadas)
    assert "Lo que subio" not in chat.modelo.llamadas[1]["messages"][0]["content"]
    assert texto_visible(eventos) == "Dejame ver y sigo"
    assert "ghp_" not in (chat.tmp / "telemetry.jsonl").read_text(encoding="utf-8")


def test_en_nube_solo_hondo_sigue_sin_bloque_y_sin_juez(chat, monkeypatch):
    def juez_solo_del_mensaje(texto):
        # la compuerta /nube del MENSAJE si lo llama (`preparar_envio`, en
        # hilo, ANTES de cualquier consulta): una bomba a secas reventaria
        # el turno sin `done`. Lo que no puede llegarle es el bloque
        # pescado: con solo anillo 3 el viaje lo descarta antes del juez. Si
        # llegara, esta asercion sube por el fallo cerrado del viaje como
        # `juez_local_caido` y la asercion del motivo, abajo, lo delata.
        assert "Lo que subio del abismo" not in texto, "con solo hondo el juez no corre"
        return {"tramos": [], "fallo_cerrado": False, "motivo": ""}
    monkeypatch.setattr(juez, "juzgar", juez_solo_del_mensaje)
    chat.memoria.core = "### perfil\n- Marta vive en Cordoba con Pedro\n"
    chat.modelo.guiones = [["a ⟦abismo:memoria donde vive Marta⟧"], ["b"]]
    eventos = chat.turno("/nube /api donde vive")
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "fallo"]
    assert abismo[1]["motivo"] == "solo_hondo"
    assert "Cordoba" not in json.dumps(chat.modelo.llamadas)
    # reentrada sin bloque (rutas en vivo): dos llamadas, la segunda limpia
    assert len(chat.modelo.llamadas) == 2
    assert "Lo que subio" not in chat.modelo.llamadas[1]["messages"][0]["content"]
    assert texto_visible(eventos) == "a b"
    # la compuerta del mensaje corrio UNA vez: salteo 4 de la pasada sintetica
    assert len([e for e in eventos if e["type"] == "privacidad"]) == 1


def test_en_nube_por_suscripcion_los_tramos_vuelven_crudos(chat, cli_falso, monkeypatch):
    """El canario de la invariante 9: Pedro ve "Marta" (repuesto), la nube
    recibe "[ID_1]" (crudo) en el venias diciendo y en el bloque."""
    _juez_que_tapa_a_marta(monkeypatch)
    _sembrar_chat_viejo(["con Marta hablamos del libro de cocina"])
    cli_falso.guion([{"partes": ["Le dije a [ID_1] que ⟦abismo:chats libro⟧ nada"], "pausa": 0},
                     {"partes": ["y seguimos"], "pausa": 0}])
    eventos = chat.turno("/nube /claude que hablamos con Marta del libro")
    assert texto_visible(eventos) == "Le dije a Marta que y seguimos"
    llamadas = cli_falso.llamadas()
    assert len(llamadas) == 2
    assert "Venias diciendo: Le dije a [ID_1] que " in llamadas[1]["prompt"]
    assert "[ID_1]" in llamadas[1]["sistema"] and "cocina" in llamadas[1]["sistema"]
    assert "Marta" not in json.dumps(llamadas)
    assert contrato.bloque_contrato(()) in llamadas[0]["sistema"]
    # lo persistido es lo repuesto que Pedro vio, sin bloque
    assert chat.mensajes()[-1]["text"] == "Le dije a Marta que y seguimos"
    assert "Lo que subio" not in (chat.tmp / "chats.json").read_text(encoding="utf-8")


def test_en_nube_por_suscripcion_un_bloque_que_no_viaja_no_reinvoca(chat, cli_falso, monkeypatch):
    """La letra exacta del 8.4, en la unica ruta donde el texto posterior
    existe: el viaje falla (credencial), no se reinvoca, lo que el CLI
    escribio despues de la marca vale, y el secreto no sale."""
    _juez_que_tapa_a_marta(monkeypatch, con_credencial=True)
    _sembrar_chat_viejo(["el token del libro es ghp_abcdef"])
    cli_falso.guion([{"partes": ["Dejame ver ⟦abismo:chats libro⟧ y sigo sin el"], "pausa": 0}])
    eventos = chat.turno("/nube /claude que libro tenia token")
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "fallo"]
    assert abismo[1]["motivo"] == "credencial"
    assert texto_visible(eventos) == "Dejame ver  y sigo sin el"
    assert len(cli_falso.llamadas()) == 1
    assert "ghp_" not in json.dumps(cli_falso.llamadas())
    assert "ghp_" not in (chat.tmp / "telemetry.jsonl").read_text(encoding="utf-8")
```

- [ ] **Step 2: Correrlos**

Run: `.venv/bin/python -m pytest -q test_abismo_nube.py`
Expected: `5 passed` si las Tasks 5-7 quedaron como el plan las escribe. Si alguno falla, el fallo dice donde se aparto el cableado de la seccion 8 del spec (destino, mapa, system base, crudo contra repuesto): se corrige en `server.py` y se anota en el commit. No se ajustan las aserciones para que pasen.

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
Expected: `1437 passed, 4 warnings`, `EXIT=0`.

- [ ] **Step 3: La aclaracion de una oracion en el spec (seccion 8, punto 4)**

En `docs/superpowers/specs/2026-09-07-abismo-consulta-design.md`, seccion 8, el punto 4 termina hoy en "Descartados: pasar la continuacion a local (cambio de modelo a mitad de burbuja) y cortar con aviso." A continuacion, en el mismo parrafo, se agrega:

```
 **Aclaracion del plan 1b (2026-09-08):** en las rutas que streamean (local, api, `/nube /api`) el generador ya esta cerrado cuando el viaje decide, asi que "la nube sigue sin el bloque" se cumple por REENTRADA sin bloque (seccion 4, paso 4) y no existe "texto posterior"; la letra de este punto ("la reentrada NO se hace, el texto posterior vale") es la de la ruta one-shot (suscripcion), donde el texto posterior existe.
```

Sin esto, un revisor de la ronda adversaria (Task 13, `adversaria-completitud.md`) marca los dos tests de `/nube /api` de arriba como incumplimiento del 8.4.

- [ ] **Step 4: Commit**

```bash
git add test_abismo_nube.py docs/superpowers/specs/2026-09-07-abismo-consulta-design.md calipso/server.py
git commit -m "test(abismo): el turno /nube de punta a punta -- contrato sin nombres, bloque tapado con el mapa de la conversacion y visible, credencial que no sale (en vivo y one-shot), solo hondo sin juez, tramos crudos por suscripcion, nada persistido; spec: aclaracion del 8.4 por ruta"
```

(`calipso/server.py` va en el `git add` solo si el Step 2 obligo a corregir algo; si no, el commit lleva el test y el spec.)

Riesgos anotados: desvio declarado del spec 8.4 en `/nube /api` (y en toda ruta que streamea): con el bloque que no puede viajar la nube sigue sin el, pero por REENTRADA sin bloque (el generador ya se cerro), no por "el texto posterior vale"; ese regimen es el de suscripcion (`test_en_nube_por_suscripcion_un_bloque_que_no_viaja_no_reinvoca`). Queda anotado para `adversaria-completitud.md` y aclarado en el spec (Step 3). La rama api de /nube streamea marcadores sin reponer (preexistente, fuera de este plan; el spec dice que en api el corte es en vivo "como local", y asi queda). El `mapa` es por `chat_id` y vive en memoria del proceso (`conversacion._por_chat`): el segundo turno de la misma conversacion reusa `[ID_1]` para Marta, que es lo que la reentrada necesita. La compuerta binaria `a_la_nube_tapado` de los cuatro sitios de append (`:3498-3503`, `:3515-3520`, `:3594-3597`, `:3645-3648`) NO se toca: el bloque entra por `prompt_reentrada` y por ningun otro lado (seccion 8.2).

---

### Task 9: El pulso -- `EVENTOS` y `CONOCIDOS` juntos, con el test que los acopla

**Files:**
- Modify: `calipso/mapa/pulso.py:22-23` (`EVENTOS`)
- Modify: `calipso/web/fabrica/pulso.js:24-33` (`vacio`: campo `abismo`), `:35-36` (`CONOCIDOS`), `:71-96` (un `case "abismo"`)
- Modify: `calipso/server.py` (`_pescar_abismo`, Task 6: tres `EL_PULSO.publicar`)
- Test: `test_abismo_pulso.py` (nuevo), `calipso/web/fabrica/pulso.test.js` (un test mas), `test_abismo_chat.py` (un test mas)

**Interfaces:**
- Consumes: `Pulso.publicar(agente_id, evento, **campos)` revienta con evento desconocido (`calipso/mapa/pulso.py:139-141`); `aplicarEvento(estado, ev, ahora)` descarta lo que no esta en `CONOCIDOS` (`pulso.js:38-39`) y todo evento de empleado exige `departamento` y `agente_id` (`:62`).
- Produces: `EVENTOS = (..., "foco", "abismo")`; `CONOCIDOS = [..., "foco", "abismo"]`; cada empleado del pulso gana `abismo: null | {fase, fuente}`; `_pescar_abismo` publica `EL_PULSO.publicar(agente_id, "abismo", fase=..., fuente=...)` en las tres fases.

- [ ] **Step 1: Tests en rojo**

```python
# test_abismo_pulso.py
"""La senal del abismo tambien va al pulso del mapa (spec seccion 9): las
dos listas de eventos -la del server y la del cliente- se tocan juntas."""
import pathlib
import re

from calipso.mapa import pulso as p

FABRICA = pathlib.Path(__file__).parent / "calipso" / "web" / "fabrica"


def conocidos_del_cliente() -> list[str]:
    js = (FABRICA / "pulso.js").read_text(encoding="utf-8")
    cuerpo = js.split("const CONOCIDOS = [", 1)[1].split("];", 1)[0]
    return re.findall(r'"([a-z_]+)"', cuerpo)


def test_las_dos_listas_de_eventos_del_pulso_estan_acopladas():
    """Sumar un evento a una sola lista no pone nada en rojo: el server
    revienta o el cliente lo descarta mudo. Este test es la costura."""
    assert set(conocidos_del_cliente()) == set(p.EVENTOS)


def test_el_abismo_es_un_evento_del_pulso():
    pu = p.Pulso()
    ev = pu.publicar("chat:x", "abismo", fase="pondering", fuente="chats",
                     departamento="dep:atlas")
    assert ev["evento"] == "abismo" and ev["fase"] == "pondering" and ev["fuente"] == "chats"
    assert [e["evento"] for e in pu.eventos("chat:x")] == ["abismo"]
```

En `pulso.test.js`, despues del test `"el foco se guarda con su seq para que no vuele dos veces"`:

```js
test("el abismo cuelga del escritorio del turno y lo deja razonando", () => {
  const base = aplicarEvento(estadoInicial(), ev("inicio"), 5000);
  const e = aplicarEvento(base, ev("abismo", {fase: "pondering", fuente: "chats"}, 2), 5001);
  assert.notEqual(e, base);                        // ya no es un desconocido
  const [empleado] = empleadosDe(e, "dep:atlas");
  assert.deepEqual(empleado.abismo, {fase: "pondering", fuente: "chats"});
  assert.equal(empleado.estado, "razonando");
  const f = aplicarEvento(e, ev("abismo", {fase: "pescado", fuente: "chats", tamano: 12}, 3), 5002);
  assert.deepEqual(empleadosDe(f, "dep:atlas")[0].abismo, {fase: "pescado", fuente: "chats"});
  assert.equal(empleadosDe(f, "dep:atlas")[0].texto, "", "el abismo no es texto del razonamiento");
});
```

Y al final de `test_abismo_chat.py`:

```python
def test_la_senal_del_abismo_se_publica_al_pulso(chat):
    _sembrar_chat_viejo(["un libro"])
    chat.modelo.guiones = [["a ⟦abismo:chats libro⟧"], ["b"]]
    chat.turno("libro", departamento="dep:atlas")
    eventos = [e for e in chat.pulso.desde(0)[1] if e["evento"] == "abismo"]
    assert [(e["fase"], e["fuente"]) for e in eventos] == [("pondering", "chats"), ("pescado", "chats")]
    assert all(e["agente_id"].startswith("chat:") and e["departamento"] == "dep:atlas" for e in eventos)
```

- [ ] **Step 2: Verlos fallar**

Run: `.venv/bin/python -m pytest -q test_abismo_pulso.py test_abismo_chat.py`
Expected: `test_las_dos_listas...` pasa (hoy las dos listas coinciden), `test_el_abismo_es_un_evento_del_pulso` falla con `ValueError: evento desconocido: 'abismo'`, `test_la_senal_del_abismo_se_publica_al_pulso` falla (`[] == [...]`).

Run: `cd calipso/web/fabrica && ~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test 2>&1 | tail -5`
Expected: `# fail 1` (el nuevo: `aplicarEvento` devuelve `base` porque `abismo` no esta en `CONOCIDOS`).

- [ ] **Step 3: Las dos listas y el reductor**

`calipso/mapa/pulso.py:22-23`:

```python
EVENTOS = ("inicio", "razonando", "herramienta", "tokens", "diff", "fin",
           "foco", "abismo")
```

`calipso/web/fabrica/pulso.js`: en `vacio` (`:24-33`), despues de `herramienta: null,`: `abismo: null,`. `CONOCIDOS` (`:35-36`):

```js
const CONOCIDOS = ["inicio", "razonando", "herramienta", "tokens", "diff",
                   "fin", "foco", "abismo"];
```

Y en el `switch (ev.evento)` (`:71-96`), antes de `default:`:

```js
    case "abismo":
      // la consulta al abismo del turno de chat (spec del abismo, seccion
      // 9): pondering | pescado | fallo. No es texto del razonamiento: el
      // texto sigue llegando por `razonando`; esto es un estado al lado
      e.abismo = {fase: ev.fase, fuente: ev.fuente};
      if (ev.fase === "pondering") e.estado = "razonando";
      break;
```

- [ ] **Step 4: El server publica**

En `_pescar_abismo` (Task 6, debajo de `_limpiar_marcas`), tres lineas:

Despues de `await ws.send_json(abismo_turno.senal("pondering", m.fuente))`:
```python
    if EL_PULSO is not None and agente_id:
        EL_PULSO.publicar(agente_id, "abismo", fase="pondering", fuente=m.fuente)
```
Despues del `send_json` de `fallo`:
```python
        if EL_PULSO is not None and agente_id:
            EL_PULSO.publicar(agente_id, "abismo", fase="fallo", fuente=m.fuente,
                              motivo=motivo)
```
Despues del `send_json` de `pescado`:
```python
    if EL_PULSO is not None and agente_id:
        EL_PULSO.publicar(agente_id, "abismo", fase="pescado", fuente=m.fuente,
                          tamano=len(v["texto"]))
```

(El `agente_id` del turno ya viaja a `_pescar_abismo` desde las Tasks 6 y 7: el `agente_id = "chat:" + uuid...` de `:3428`, que el `publicar(agente_id, "inicio", departamento=departamento, ...)` de `:3433` ya ato al edificio tocado.)

- [ ] **Step 5: Verde, suite y node**

Run: `.venv/bin/python -m pytest -q test_abismo_pulso.py test_abismo_chat.py test_mapa_pulso.py`
Expected: `2 passed`, `12 passed`, y `test_mapa_pulso.py` sin cambios (`test_un_evento_desconocido_no_entra` sigue usando `pensando_mucho`).

Run: `cd calipso/web/fabrica && ~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test 2>&1 | tail -5`
Expected: `# pass 402`, `# fail 0`.

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
Expected: `1440 passed, 4 warnings`, `EXIT=0` (incluye `test_fabrica_js.py`, que corre node).

- [ ] **Step 6: Commit**

```bash
git add calipso/mapa/pulso.py calipso/web/fabrica/pulso.js calipso/web/fabrica/pulso.test.js calipso/server.py test_abismo_pulso.py test_abismo_chat.py
git commit -m "feat(abismo): la senal del abismo va al pulso (EVENTOS y CONOCIDOS juntos, test que los acopla; el escritorio del turno guarda fase y fuente)"
```

Riesgos anotados: sin `departamento` (chat sin edificio tocado) el evento entra al flujo pero no cuelga de ningun escritorio (`pulso.js:62`): para esta rebanada alcanza (la escena del abismo es la rebanada 3). Publicar desde `_pescar_abismo` ANTES de esta task habria reventado con `ValueError` dentro del `try` y convertido cada consulta en `fallo`: por eso el `publicar` se agrega recien aca, junto con `EVENTOS`.

---

### Task 10: La PWA -- el renglon del abismo en `index.html`, `sw.js` a v4

**Files:**
- Modify: `calipso/web/index.html:282-284` (CSS `.thinking`: se suma `.abismo` al lado), `:2172-2176` (`renderHistory`), `:2355-2357` (rama `steered` + rama nueva `abismo`), `:2406-2416` (`error` y `done`), `:2418` (`ws.onclose`), `:2435-2450` (`startThinking`/`stopThinking`: se suman `startAbismo`/`stopAbismo`/`textoDeAbismo`/`addDetalleViaje`)
- Modify: `calipso/web/sw.js:1` (`CACHE`)
- Modify: `test_ui.py:37-41` (una linea `check` mas)
- Test: `test_ui.py` (manual: `.venv/bin/python test_ui.py`), `test_mapa_server.py` (el SHELL sigue existiendo)

**Interfaces:**
- Consumes: `addMsg(cls, text)` (`index.html:1649`), `addDetail(key, title, body)` (`:1899`, escapa con `esc`), `messages`, `botEl` (`:595`, `:600`), `stopThinking()` (`:2447`).
- Produces: `startAbismo(m)`, `stopAbismo()`, `textoDeAbismo(m)`, `addDetalleViaje(m)`; la rama `m.type === "abismo"` en `ws.onmessage`; CSS `.abismo`; `CACHE = "calipso-shell-v4"`.

- [ ] **Step 1: El check en rojo**

En `test_ui.py`, entre el `check("panel rutinas", ...)` (`:40-41`) y `scripts = re.findall(...)`:

```python
    check("rama del abismo", all(x in text for x in (
        "startAbismo", "stopAbismo", 'm.type === "abismo"', "addDetalleViaje",
        "abismoEl")), fails)
```

Run: `.venv/bin/python test_ui.py; echo EXIT=$?`
Expected: `[FAIL] rama del abismo`, `EXIT=1`.

- [ ] **Step 2: El CSS**

`index.html:282-284`, debajo de `.thinking::after { content: "…"; }`:

```css
  .abismo { align-self: flex-start; color: var(--accent2); font-size: 12.5px;
            font-style: italic; padding: 2px 6px; }
```

- [ ] **Step 3: El estado y las funciones, debajo de `stopThinking()` (`:2450`)**

```js
// El pondering del abismo (spec del abismo, seccion 9): un renglon HERMANO
// del "pensando", nunca un mensaje ni un turno. La burbuja abierta (botEl)
// no se toca en ninguna fase: la continuacion cae en la misma. El elapsed
// se cuenta aca, en el cliente: el server no tiene el bucle de 2 s de la
// suscripcion. El cierre lo garantiza el cliente: done, error, steered y
// cambiar de chat lo apagan aunque el pescado nunca haya llegado.
let abismoEl = null, abismoTimer = null, abismoDesde = 0;
const ABISMO_VERBOS = {memoria: "buscando en tu memoria",
                       chats: "buscando en tus chats", proyecto: "mirando el repo"};
const ABISMO_MOTIVOS = {vacio: "no trajo nada", credencial: "esto no sale de la maquina",
                        solo_hondo: "solo habia hondo", juez_local_caido: "el juez local no responde",
                        tipo_desconocido: "tipo desconocido, no sale", error: "fallo la consulta"};
function startAbismo(m) {
  stopThinking();
  const verbo = m.verbo || ABISMO_VERBOS[m.fuente] || "consultando el abismo";
  abismoDesde = Date.now();
  if (!abismoEl) {
    abismoEl = document.createElement("div");
    abismoEl.className = "abismo";
    messages.appendChild(abismoEl);
  }
  const tick = () => {
    abismoEl.textContent = `${verbo}... ${Math.round((Date.now() - abismoDesde) / 1000)} s`;
    messages.scrollTop = messages.scrollHeight;
  };
  if (abismoTimer) clearInterval(abismoTimer);
  tick(); abismoTimer = setInterval(tick, 1000);
}
function stopAbismo() {
  if (abismoTimer) { clearInterval(abismoTimer); abismoTimer = null; }
  if (abismoEl) { abismoEl.remove(); abismoEl = null; }
  abismoDesde = 0;
}
function textoDeAbismo(m) {
  // la misma letra que textoDeAbismo de la fabrica (chat.js): una senal, un texto
  if (m.fase === "pescado") {
    let nube = "";
    if (m.viaje && m.viaje.destino === "nube") {
      const tapados = (m.viaje.tapados || []).map(t => t.marcador).join(", ");
      nube = ", viajo tapado a la nube" + (tapados ? ": " + tapados : "");
    }
    return `del abismo: ${m.fuente} (${m.tamano || 0} chars${nube})`;
  }
  return `el abismo (${m.fuente}): ${ABISMO_MOTIVOS[m.motivo] || m.motivo || "fallo"}`;
}
function addDetalleViaje(m) {
  const tapados = (m.viaje.tapados || []).map(t => `${t.marcador} (${t.tipo})`).join(", ") || "nada tapado";
  addDetail(null, `lo que viajo a la nube desde ${m.fuente}`,
            `tapados: ${tapados}\n\n${m.viaje.texto_tapado || ""}`);
}
```

- [ ] **Step 4: Las ramas en `ws.onmessage`**

`:2355-2357` pasa a:

```js
    } else if (m.type === "steered") {
      stopThinking(); stopAbismo(); addMsg("meta", "interrumpido"); botEl = null;
    } else if (m.type === "abismo") {
      if (m.fase === "pondering") {
        startAbismo(m);
      } else {
        stopAbismo();
        addMsg("meta", textoDeAbismo(m));
        if (m.fase === "pescado" && m.viaje && m.viaje.destino === "nube") addDetalleViaje(m);
      }
    } else if (m.type === "chunk") {
```

`:2406-2409` (`error` y `done`):

```js
    } else if (m.type === "error") {
      stopThinking(); stopAbismo(); addMsg("meta", "! " + m.text);
    } else if (m.type === "done") {
      stopThinking(); stopAbismo();
```

Y en `renderHistory` (`:2174-2176`), despues de `botEl = null;`: `stopAbismo();`.

Y `ws.onclose` (`:2418`), que reconecta y hoy no apaga nada, pasa a (un pondering abierto cuando se cae el socket no puede quedar contando segundos para siempre; `stopThinking` no esta ahi hoy y no se agrega: fuera del plan):

```js
  ws.onclose = () => { stopAbismo(); addMsg("meta", "desconectado, reintentando..."); setTimeout(connect, 1500); };
```

- [ ] **Step 5: `sw.js`**

`calipso/web/sw.js:1`: `const CACHE = "calipso-shell-v4";` (un byte distinto en `sw.js` dispara install+activate; el `activate` borra la v3; ver mapa de clientes, seccion 4).

- [ ] **Step 6: Verificar**

Run: `.venv/bin/python test_ui.py; echo EXIT=$?`
Expected: todos `[OK]` incluido `rama del abismo` y `javascript valido`; `EXIT=0`.

Run: `.venv/bin/python -m pytest -q test_mapa_server.py; .venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
Expected: `test_mapa_server.py` en verde (el SHELL no cambio de entradas); `1440 passed, 4 warnings`, `EXIT=0`.

- [ ] **Step 7: Commit**

```bash
git add calipso/web/index.html calipso/web/sw.js test_ui.py
git commit -m "feat(abismo): el renglon del abismo en la PWA (hermano del pensando, misma burbuja, cierre en done/error/steered/historial, detalle del viaje tapado); sw.js a v4"
```

Riesgos anotados: `steered` cierra la burbuja en la PWA (`botEl = null`) y ahora tambien el pondering: el steer gana. `addDetail` escapa con `esc()`, asi que el `texto_tapado` (texto del abismo, potencialmente con angulos) no se interpreta como HTML. No hay test de DOM para `index.html` (no hay jsdom y no lo va a haber): el comportamiento se ve en el smoke de la Task 13.

---

### Task 11: La fabrica -- `chat.js` gana un campo (no un turno), `app.js` lo pinta fuera de la conversacion

**Files:**
- Modify: `calipso/web/fabrica/chat.js:10-14` (`estadoInicial`), `:37-38` (`EVENTOS_DEL_STREAM`), `:54-56` (`thinking`), `:67-74` (`done`), `:87-91` (`error`), nuevo `case "abismo"`, `:151-158` (`cargar`), nueva `textoDeAbismo` exportada
- Modify: `calipso/web/fabrica/index.html:24` (nodo `#abismo` fuera de `#conversacion`, con el renglon `#abismo-texto` y el detalle `#abismo-viaje` adentro)
- Modify: `calipso/web/fabrica/app.js:16` (import), `:1063` (`cajaAbismo` y los tres nodos hijos), `:1106-1123` (callback de `crearChat`: `pintarAbismo`)
- Modify: `calipso/web/fabrica/estilo.css:73-76` (`.abismo` y su detalle) y `:139-140` (la regla de ocultado del modo razonamiento)
- Test: `calipso/web/fabrica/chat.test.js` (siete tests mas), `calipso/web/fabrica/arranque.test.js:116` (ids `abismo`, `abismo-texto`, `abismo-viaje`, `abismo-viaje-texto`) y dos tests mas

**Interfaces:**
- Consumes: el reductor puro `aplicarEvento(estado, ev)` y `crearChat(alCambiar, ConstructorWS)` (`chat.js:40`, `:103`); el DOM de mentira de `arranque.test.js` (`nodo(id)`, `montarNavegador`, `socket.dice`); `.oculto { display: none !important; }` (`estilo.css:163`).
- Produces: `estado.abismo: null | {fase, fuente, verbo, tamano, motivo, viaje, n}` (`thinking`, `done`, `error` y `cargar` lo dejan en `null`); `"abismo"` en `EVENTOS_DEL_STREAM`; `export function textoDeAbismo(abismo, segundos) -> string`; `pintarAbismo(estado)` en `app.js`; nodos `<div id="abismo" class="abismo oculto">` con `<span id="abismo-texto">` (el renglon) y `<details id="abismo-viaje" class="oculto">` con `<pre id="abismo-viaje-texto">` (el detalle del viaje tapado, spec seccion 9: "en las dos UIs").

- [ ] **Step 1: Tests en rojo**

En `chat.test.js`, importar `textoDeAbismo` junto a los demas (`:4-5`):

```js
import {estadoInicial, aplicarEvento, paquete, crearChat,
        turnosDeHistorial, textoDeAbismo} from "./chat.js";
```

Y al final del archivo:

```js
// --- El abismo: un renglon hermano del pensando, nunca un turno ---------

test("el pondering del abismo no agrega turnos y el chunk siguiente sigue en el mismo", () => {
  const e = aplicar([{type: "thinking"}, {type: "chunk", text: "Dejame ver "},
                     {type: "abismo", fase: "pondering", fuente: "chats",
                      verbo: "buscando en tus chats"},
                     {type: "chunk", text: "y sigo"}]);
  assert.equal(e.turnos.length, 1);
  assert.equal(e.turnos[0].texto, "Dejame ver y sigo");
  assert.equal(e.abismo.fase, "pondering");
  assert.equal(e.abismo.fuente, "chats");
  assert.equal(e.abismo.n, 1);
});

test("pescado reemplaza el pondering y done lo apaga", () => {
  let e = aplicar([{type: "thinking"},
                   {type: "abismo", fase: "pondering", fuente: "memoria"},
                   {type: "abismo", fase: "pescado", fuente: "memoria", tamano: 120,
                    viaje: {destino: "local"}}]);
  assert.deepEqual({fase: e.abismo.fase, tamano: e.abismo.tamano, n: e.abismo.n},
                   {fase: "pescado", tamano: 120, n: 1});
  e = aplicarEvento(e, {type: "done"});
  assert.equal(e.abismo, null);
});

test("un thinking nuevo apaga un pondering colgado del turno anterior", () => {
  // un turno que murio sin done (socket caido) no deja el renglon vivo
  // hasta el done del turno siguiente: el thinking del turno nuevo lo apaga
  const e = aplicar([{type: "thinking"}, {type: "abismo", fase: "pondering", fuente: "chats"},
                     {type: "thinking"}]);
  assert.equal(e.abismo, null);
});

test("la segunda consulta del mismo turno sube n, y error y cargar apagan", () => {
  let e = aplicar([{type: "thinking"},
                   {type: "abismo", fase: "pondering", fuente: "chats"},
                   {type: "abismo", fase: "pescado", fuente: "chats", tamano: 5},
                   {type: "abismo", fase: "pondering", fuente: "proyecto"}]);
  assert.equal(e.abismo.n, 2);
  assert.equal(aplicarEvento(e, {type: "error", text: "x"}).abismo, null);
  const vistos = [];
  const chat = crearChat(x => vistos.push(x), WSFalso);
  chat.cargar({id: "c9", messages: []});
  assert.equal(vistos.at(-1).abismo, null);
});

test("una fase inventada del abismo no cambia nada", () => {
  const antes = aplicar([{type: "thinking"}]);
  const despues = aplicarEvento(antes, {type: "abismo", fase: "bailando", fuente: "chats"});
  assert.equal(despues.abismo, antes.abismo);
});

test("un abismo que llega despues de cargar otro chat se descarta", () => {
  const {chat, disparar} = wsAbierto();
  disparar({type: "thinking"});
  chat.cargar({id: "c9", messages: [{role: "user", text: "viejo"}]});
  disparar({type: "abismo", fase: "pondering", fuente: "chats"});
  assert.equal(chat.estado().abismo, null);
});

test("el texto del renglon del abismo", () => {
  assert.equal(textoDeAbismo({fase: "pondering", fuente: "chats", verbo: ""}, 3),
               "buscando en tus chats... 3 s");
  assert.equal(textoDeAbismo({fase: "pondering", fuente: "chats", verbo: "hurgando"}, 0),
               "hurgando... 0 s");
  assert.equal(textoDeAbismo({fase: "pescado", fuente: "memoria", tamano: 120,
                              viaje: {destino: "local"}}, 0),
               "del abismo: memoria (120 chars)");
  assert.equal(textoDeAbismo({fase: "pescado", fuente: "chats", tamano: 12,
                              viaje: {destino: "nube", tapados: [{marcador: "[ID_1]", tipo: "identidad"}]}}, 0),
               "del abismo: chats (12 chars, viajo tapado a la nube: [ID_1])");
  assert.equal(textoDeAbismo({fase: "fallo", fuente: "chats", motivo: "solo_hondo"}, 0),
               "el abismo (chats): solo habia hondo");
});
```

En `arranque.test.js`, la lista de ids (`:116-120`) gana `"abismo"`, `"abismo-texto"`, `"abismo-viaje"` y `"abismo-viaje-texto"` (despues de `"razonamiento"`; el DOM de mentira solo conoce los ids de esa lista y `textContent` es una propiedad plana, por eso el renglon y el detalle son nodos con id propio y no hijos creados al vuelo), y al final del archivo:

```js
test("el pondering del abismo no agrega nodos a la conversacion y el chunk sigue en el mismo", () => {
  socket.dice({type: "done"});
  socket.dice({type: "thinking"});
  socket.dice({type: "chunk", text: "Dejame ver "});
  const nodoAbierto = conversacion.hijos.at(-1);
  const cuantos = conversacion.hijos.length;
  socket.dice({type: "abismo", fase: "pondering", fuente: "chats", verbo: "buscando en tus chats"});
  const caja = nav.nodos.get("abismo");
  const renglon = nav.nodos.get("abismo-texto");
  assert.ok(!caja.classList.contains("oculto"), "el renglon del abismo no se mostro");
  assert.ok(renglon.textContent.startsWith("buscando en tus chats..."), renglon.textContent);
  assert.equal(conversacion.hijos.length, cuantos, "el pondering se pinto como turno");
  socket.dice({type: "abismo", fase: "pescado", fuente: "chats", tamano: 40, viaje: {destino: "local"}});
  socket.dice({type: "chunk", text: "y sigo"});
  assert.equal(conversacion.hijos.at(-1), nodoAbierto, "la continuacion abrio otra burbuja");
  assert.equal(nodoAbierto.textContent, "Dejame ver y sigo");
  assert.equal(renglon.textContent, "del abismo: chats (40 chars)");
  assert.ok(nav.nodos.get("abismo-viaje").classList.contains("oculto"), "en local no hay detalle del viaje");
  socket.dice({type: "done"});
  assert.ok(caja.classList.contains("oculto"), "done no apago el renglon");
});

test("con destino nube el renglon del abismo despliega el texto tapado", () => {
  // spec seccion 9: el detalle desplegable con el texto tapado va en las
  // DOS UIs; es la informacion verificable de que viajo (seccion 8.3)
  socket.dice({type: "thinking"});
  socket.dice({type: "abismo", fase: "pondering", fuente: "chats"});
  const detalle = nav.nodos.get("abismo-viaje");
  assert.ok(detalle.classList.contains("oculto"), "el detalle se mostro antes de pescar");
  socket.dice({type: "abismo", fase: "pescado", fuente: "chats", tamano: 40,
               viaje: {destino: "nube", tapados: [{marcador: "[ID_1]", tipo: "identidad"}],
                       texto_tapado: "hola [ID_1]"}});
  assert.ok(!detalle.classList.contains("oculto"), "el detalle del viaje no se mostro");
  assert.equal(nav.nodos.get("abismo-viaje-texto").textContent, "hola [ID_1]");
  assert.equal(nav.nodos.get("abismo-texto").textContent,
               "del abismo: chats (40 chars, viajo tapado a la nube: [ID_1])");
  socket.dice({type: "done"});
  assert.ok(detalle.classList.contains("oculto"), "done no apago el detalle");
  assert.ok(nav.nodos.get("abismo").classList.contains("oculto"), "done no apago el renglon");
});
```

Run: `cd calipso/web/fabrica && ~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test 2>&1 | tail -5`
Expected: `# fail 9` (siete en `chat.test.js` y dos en `arranque.test.js`), o menos si la colecta de `chat.test.js` se rompe por `textoDeAbismo` sin exportar (el archivo entero cuenta como un fallo).

- [ ] **Step 2: `chat.js`**

`estadoInicial` (`:10-14`):

```js
export function estadoInicial() {
  return {turnos: [], pensando: false, chatId: null, ruta: null,
          modelo: null, costo_usd: 0, tokens: 0, costo_mm: 0, cuenta: null,
          conectado: false, epoca: 0, streamViejo: false, abismo: null};
}
```

`EVENTOS_DEL_STREAM` (`:37-38`): `new Set(["chunk", "done", "meta", "cost", "chat", "error", "abismo"])` -- sin esto un pondering del turno anterior se pinta encima del chat recien cargado (el caso del comentario de `:30-36`).

En el `switch`: `case "thinking"` (`:54-56`) gana `e.abismo = null;` junto a `e.pensando = true;` (un turno que murio sin `done` -socket caido- no deja el renglon vivo hasta el `done` del turno siguiente: el `thinking` del turno nuevo lo apaga, y `n` no cuenta desde un fantasma), `case "done"` gana `e.abismo = null;` (junto a `e.pensando = false;`), `case "error"` idem, y entre `done` y `meta`:

```js
    case "abismo": {
      // El pondering NO es un turno: si entrara a `turnos`, el proximo
      // chunk abriria otra burbuja (el `case "chunk"` mira el ultimo turno
      // abierto). Es un campo al lado. `n` cuenta las consultas del turno
      // para que app.js distinga "segunda consulta" (reiniciar el reloj)
      // de "repintado" (no reiniciarlo): este reductor no tiene reloj.
      if (ev.fase === "pondering") {
        e.abismo = {fase: "pondering", fuente: ev.fuente, verbo: ev.verbo || "",
                    tamano: 0, motivo: "", viaje: null,
                    n: (estado.abismo ? estado.abismo.n : 0) + 1};
      } else if (ev.fase === "pescado" || ev.fase === "fallo") {
        e.abismo = {fase: ev.fase, fuente: ev.fuente, verbo: "",
                    tamano: ev.tamano || 0, motivo: ev.motivo || "",
                    viaje: ev.viaje || null,
                    n: estado.abismo ? estado.abismo.n : 1};
      }
      break;                // cualquier otra fase: fallo cerrado, no se toca nada
    }
```

`cargar` (`:151-158`): la lista de reseteo gana `abismo: null` al lado de `pensando: false`.

Y la funcion pura, exportada, antes de `crearChat`:

```js
const VERBOS = {memoria: "buscando en tu memoria", chats: "buscando en tus chats",
                proyecto: "mirando el repo"};
const MOTIVOS = {vacio: "no trajo nada", credencial: "esto no sale de la maquina",
                 solo_hondo: "solo habia hondo", juez_local_caido: "el juez local no responde",
                 tipo_desconocido: "tipo desconocido, no sale", error: "fallo la consulta"};

/** El renglon del abismo, con los segundos contados por quien pinta. */
export function textoDeAbismo(abismo, segundos) {
  if (abismo.fase === "pondering") {
    const verbo = abismo.verbo || VERBOS[abismo.fuente] || "consultando el abismo";
    return `${verbo}... ${segundos} s`;
  }
  if (abismo.fase === "pescado") {
    let nube = "";
    if (abismo.viaje && abismo.viaje.destino === "nube") {
      const tapados = (abismo.viaje.tapados || []).map(t => t.marcador).join(", ");
      nube = ", viajo tapado a la nube" + (tapados ? ": " + tapados : "");
    }
    return `del abismo: ${abismo.fuente} (${abismo.tamano || 0} chars${nube})`;
  }
  return `el abismo (${abismo.fuente}): ${MOTIVOS[abismo.motivo] || abismo.motivo || "fallo"}`;
}
```

- [ ] **Step 3: `index.html`, `estilo.css`, `app.js`**

`calipso/web/fabrica/index.html:24`, entre `#conversacion` y `#razonamiento`:

```html
    <div id="conversacion" class="conversacion"></div>
    <div id="abismo" class="abismo oculto">
      <span id="abismo-texto"></span>
      <details id="abismo-viaje" class="oculto">
        <summary>lo que viajo a la nube</summary>
        <pre id="abismo-viaje-texto"></pre>
      </details>
    </div>
    <div id="razonamiento" class="razonamiento oculto"></div>
```

(Fuera de `#conversacion` porque `pintarConversacion` indexa por posicion contra `nodosDeTurno` y el reset de epoca hace `conversacion.innerHTML = ""`. Los tres hijos son fijos y con id: `pintarAbismo` solo escribe `textContent` y clases, nunca crea nodos ni usa `innerHTML`, asi el DOM de mentira de `arranque.test.js` -que conoce los ids de su lista y trata `textContent` como propiedad plana- puede afirmar el detalle.)

`estilo.css`, debajo de `.conversacion .turno.error` (`:76`):

```css
.abismo { padding: 0 10px 8px; color: var(--acento); font-size: 12px; font-style: italic; }
.abismo details { margin-top: 4px; font-style: normal; }
.abismo summary { cursor: pointer; }
.abismo pre { white-space: pre-wrap; margin: 4px 0 0; font-size: 11px; }
```

y la regla de ocultado (`:139-140`) pasa a:

```css
#panel-centro[data-modo="razonamiento"] .conversacion,
#panel-centro[data-modo="razonamiento"] .abismo,
#panel-centro[data-modo="razonamiento"] #entrada { display: none; }
```

`app.js`: el import (`:16`) pasa a `import {crearChat, textoDeAbismo} from "./chat.js";`. Debajo de `const conversacion = document.getElementById("conversacion");` (`:1063`):

```js
const cajaAbismo = document.getElementById("abismo");
const textoAbismo = document.getElementById("abismo-texto");
const viajeAbismo = document.getElementById("abismo-viaje");
const viajeAbismoTexto = document.getElementById("abismo-viaje-texto");
// el reloj del pondering vive aca y no en el reductor (que no tiene reloj):
// `n` distingue una consulta nueva de un repintado. `.unref?.()` como en
// los otros timers de este archivo: sin el, node --test no termina.
let abismoTimer = null, abismoN = 0, abismoDesde = 0;

function pintarAbismo(estado) {
  const a = estado.abismo;
  if (!a) {
    if (abismoTimer) { clearInterval(abismoTimer); abismoTimer = null; }
    abismoN = 0;
    cajaAbismo.classList.add("oculto");
    viajeAbismo.classList.add("oculto");
    return;
  }
  cajaAbismo.classList.remove("oculto");
  if (a.fase === "pondering") {
    viajeAbismo.classList.add("oculto");
    if (a.n !== abismoN) {
      abismoN = a.n;
      abismoDesde = Date.now();
      if (abismoTimer) clearInterval(abismoTimer);
      const tic = () => {
        textoAbismo.textContent = textoDeAbismo(a, Math.round((Date.now() - abismoDesde) / 1000));
      };
      tic();
      abismoTimer = setInterval(tic, 1000);
      abismoTimer.unref?.();
    }
    return;
  }
  if (abismoTimer) { clearInterval(abismoTimer); abismoTimer = null; }
  textoAbismo.textContent = textoDeAbismo(a, 0);
  // el detalle del viaje tapado (spec seccion 9, "en las dos UIs"): el
  // texto tal cual salio, por textContent y nunca innerHTML -- es texto del
  // abismo, que puede traer angulos
  const viajo = a.fase === "pescado" && !!a.viaje && a.viaje.destino === "nube";
  viajeAbismo.classList.toggle("oculto", !viajo);
  viajeAbismoTexto.textContent = viajo ? (a.viaje.texto_tapado || "") : "";
}
```

Y en el callback de `crearChat` (`:1106-1123`), inmediatamente despues de `pintarConversacion(estado.turnos);`: `pintarAbismo(estado);`.

- [ ] **Step 4: Verde, node y suite**

Run: `cd calipso/web/fabrica && ~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test 2>&1 | tail -5`
Expected: `# pass 411`, `# fail 0`.

Run: `.venv/bin/python -m pytest -q test_mapa_server.py test_fabrica_js.py; .venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
Expected: `test_el_shell_no_se_olvida_de_ningun_archivo_de_la_fabrica` en verde (no hay modulo nuevo: `chat.js`, `app.js`, `estilo.css` ya estan en el SHELL); `1440 passed, 4 warnings`, `EXIT=0`.

- [ ] **Step 5: Commit**

```bash
git add calipso/web/fabrica/chat.js calipso/web/fabrica/chat.test.js calipso/web/fabrica/app.js calipso/web/fabrica/arranque.test.js calipso/web/fabrica/index.html calipso/web/fabrica/estilo.css
git commit -m "feat(abismo): el renglon del abismo en la fabrica -- estado.abismo en el reductor (nunca un turno), pintado fuera de la conversacion con reloj propio, cierre en done/error/cargar"
```

Riesgos anotados por el mapa de clientes: NO se toca el `case "chunk"` (`chat.js:57-66`): como el pondering no es un turno, el ultimo elemento de `turnos` sigue siendo la burbuja abierta y la continuacion se pega ahi -- eso es TODA la implementacion de "misma burbuja" en la fabrica, y lo custodian el test del reductor y el de `arranque.test.js`. `steered` no esta en el reductor (cae en `default`): en la fabrica un steer ya continua en la misma burbuja y el abismo hereda eso; el pondering colgado lo apaga el `done` del turno interrumpido, y el de un turno que murio sin `done` lo apaga el `thinking` del siguiente. El detalle del viaje se pinta con `textContent` sobre un `<pre>` fijo: el `texto_tapado` es texto del abismo y nunca se interpreta como HTML. `sw.js` sigue en v4 (subido en la Task 10, mismo merge).

---

### Task 12: Los minors del 1a -- armado dentro del try, env con fallback, el trim del contrato, el banco que no pisa

**Files:**
- Modify: `calipso/abismo/consulta.py:13` (`ABISMO_BLOQUE_MAX`) y `:21-43` (`resolver`)
- Modify: `calipso/abismo/contrato.py:31-35` (la cola honesta) y `:51-57` (el trim)
- Modify: `experimentos/consulta_abismo.py:254-258` (la ruta de salida)
- Test: `test_abismo_minors.py` (nuevo), `test_abismo_contrato.py:13-17` (una asercion mas)

(El minor del `PATRON` anidado ya se hizo en la Task 2: lo exigia la coherencia filtro/PATRON.)

**Interfaces:**
- Consumes: `consulta._fallo`, `fuentes.*` (dobles por monkeypatch), `contrato.bloque_contrato` y `contrato.INDICE_MAX` (`_armar` es un closure adentro de `bloque_contrato`, no un atributo del modulo: ningun test lo toca), `os.environ`.
- Produces: `consulta._entero_env(nombre: str, defecto: int) -> int`; `resolver` con el armado ADENTRO del `try`; `contrato.bloque_contrato` que nunca corta el cierre "CONSULTA." (cola honesta mas corta: `"un repo del catastro; hay N mas."`; si aun asi no entra, la variante medida sin nombres); `experimentos/consulta_abismo._ruta_de_salida(por_defecto: pathlib.Path) -> pathlib.Path`.

- [ ] **Step 1: Tests en rojo**

```python
# test_abismo_minors.py
"""Los cinco minors diferidos del review del 1a (mapa de dependencias,
seccion 5) que el 1b tiene que cerrar porque ahora el paquete esta en el
camino vivo del server."""
import os
import pathlib
import subprocess
import sys
import textwrap

from calipso.abismo import anillos, consulta, contrato, fuentes, marca

RAIZ = pathlib.Path(__file__).resolve().parent


def test_una_fuente_que_devuelve_basura_es_fallo_suave(monkeypatch):
    """Invariante 4: el armado del bloque (filtrado, etiquetado, techo) vive
    ADENTRO del try. Una fuente que devuelve None o tuplas de tres no puede
    subir como TypeError por la pasada sintetica hasta el WS."""
    monkeypatch.setattr(fuentes, "chats_viejos", lambda resto: None)
    r = consulta.resolver(marca.Marca("chats", "x"))
    assert r["estado"] == "fallo" and r["texto"] == "" and r["bloques"] == []
    monkeypatch.setattr(fuentes, "chats_viejos", lambda resto: [("a", 2, "de mas")])
    assert consulta.resolver(marca.Marca("chats", "x"))["estado"] == "fallo"
    monkeypatch.setattr(fuentes, "chats_viejos", lambda resto: [("ok", anillos.MEDIA_AGUA)])
    assert consulta.resolver(marca.Marca("chats", "x"))["estado"] == "pescado"


def test_el_env_mal_tipeado_no_impide_arrancar(monkeypatch):
    monkeypatch.setenv("ABISMO_BLOQUE_MAX", "mucho")
    assert consulta._entero_env("ABISMO_BLOQUE_MAX", 2000) == 2000
    monkeypatch.setenv("ABISMO_BLOQUE_MAX", "1500")
    assert consulta._entero_env("ABISMO_BLOQUE_MAX", 2000) == 1500
    monkeypatch.delenv("ABISMO_BLOQUE_MAX")
    assert consulta._entero_env("ABISMO_BLOQUE_MAX", 2000) == 2000


def test_el_trim_del_contrato_nunca_corta_el_cierre():
    """El desempate medido del porton v2 ("Ante la duda ... CONSULTA.") es lo
    ultimo del bloque: ni sesenta nombres largos ni un catastro real pueden
    dejarlo a la mitad."""
    for nombres in ((), ("calipso", "atlas", "calipso-lector"),
                    tuple(f"proyecto-con-nombre-largo-{i:03d}" for i in range(60)),
                    tuple(f"Observatory-Global-{i}" for i in range(9))):
        b = contrato.bloque_contrato(nombres)
        assert len(b) <= contrato.INDICE_MAX, len(nombres)
        assert b.endswith("CONSULTA."), (len(nombres), b[-60:])


def test_una_recorrida_del_banco_no_pisa_las_observaciones(tmp_path):
    """El banco se importa en un subproceso con CALIPSO_HOME temporal (la
    regla del repo: jamas importar calipso sin el home apuntado a un tmp), y
    se prueba solo la eleccion de la ruta de salida, no la corrida."""
    codigo = textwrap.dedent(f"""
        import os, pathlib, sys
        sys.path.insert(0, {str(RAIZ / "experimentos")!r})
        sys.path.insert(0, {str(RAIZ)!r})
        import consulta_abismo as banco
        p = pathlib.Path({str(tmp_path)!r}) / "consulta_abismo_resultados.md"
        assert banco._ruta_de_salida(p) == p, "sin archivo previo se escribe en el default"
        p.write_text("## Observaciones escritas a mano", encoding="utf-8")
        otra = banco._ruta_de_salida(p)
        assert otra != p and otra.parent == p.parent and otra.suffix == ".md", otra
        os.environ["ABISMO_RESULTADOS"] = str(p.parent / "forzado.md")
        assert banco._ruta_de_salida(p).name == "forzado.md"
        print("OK")
    """)
    r = subprocess.run([sys.executable, "-c", codigo],
                       env={**os.environ, "CALIPSO_HOME": str(tmp_path / "home")},
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr
```

Y en `test_abismo_contrato.py`, `test_respeta_el_techo_con_muchos_proyectos` (`:13-17`) gana una linea final: `assert b.endswith("CONSULTA.")`.

Run: `.venv/bin/python -m pytest -q test_abismo_minors.py test_abismo_contrato.py`
Expected: `4 failed` en el nuevo (TypeError en el primero, `AttributeError: _entero_env`, el trim corta "consul", `AttributeError: _ruta_de_salida`) y `1 failed` en el de contrato.

- [ ] **Step 2: `consulta.py`**

```python
def _entero_env(nombre: str, defecto: int) -> int:
    """Un env mal tipeado no puede impedir que arranque el server: desde el
    1b este modulo esta en la cadena de import de calipso/server.py."""
    try:
        return int(os.environ.get(nombre, defecto))
    except (TypeError, ValueError):
        return defecto


ABISMO_BLOQUE_MAX = _entero_env("ABISMO_BLOQUE_MAX", 2000)
```

Y `resolver` entero (`:21-43`):

```python
def resolver(m: marca.Marca, *, mem=None, obtener=None, brief=None,
             consolidado=None, zona_chat: str = "fabrica") -> dict:
    # el armado tambien va adentro del try (minor del review 1a): una fuente
    # que devuelva algo que no sea una lista de pares (texto, anillo) es un
    # fallo suave, no un TypeError que suba por la pasada sintetica
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
        bloques = [(t, a) for t, a in bloques if t.strip()]
        if not bloques:
            return _fallo(m.fuente, "la consulta no trajo nada")
        partes = [f"=== Lo que subio del abismo (fuente: {m.fuente}) ==="]
        for texto, anillo in bloques:
            partes.append(f"[anillo {anillo}]\n{texto.strip()}")
        texto = "\n".join(partes)[:ABISMO_BLOQUE_MAX]
    except Exception as e:
        return _fallo(m.fuente, str(e))
    return {"estado": "pescado", "fuente": m.fuente, "texto": texto,
            "bloques": bloques, "aviso": ""}
```

- [ ] **Step 3: `contrato.py`**

La cola honesta (`:31-35`) pasa a:

```python
        elif extra:
            # El recorte vacio la lista (nombres muy largos): cola honesta en
            # vez de esconder que el catastro existe (minor del review 1a),
            # corta para que el cierre medido entre siempre. "Pedilos por
            # nombre" ya lo dice la marca de la linea.
            repos = f"un repo del catastro; hay {extra} mas."
```

Y el trim (`:51-57`):

```python
    nombres = list(nombres_proyectos)
    total = len(nombres)
    texto = _armar(nombres, 0)
    while len(texto) > INDICE_MAX and nombres:
        nombres = nombres[:-1]
        texto = _armar(nombres, total - len(nombres))
    if len(texto) > INDICE_MAX:
        # ni un nombre entra y la cola honesta tampoco: vuelve la variante
        # sin nombres (la medida) antes que cortar el cierre "Ante la duda
        # ... CONSULTA", que es el desempate al que el porton v2 le atribuye
        # la mejora. Nunca se rebana el texto.
        texto = _armar([], 0)
    return texto
```

- [ ] **Step 4: El banco**

En `experimentos/consulta_abismo.py`, `import datetime` junto a los otros imports de la cabecera, y antes de `def main()`:

```python
def _ruta_de_salida(por_defecto: pathlib.Path) -> pathlib.Path:
    """Sin ABISMO_RESULTADOS, una re-corrida no pisa el reporte anterior (que
    tiene Observaciones escritas a mano): escribe al lado, con fecha y hora."""
    env = os.environ.get("ABISMO_RESULTADOS")
    if env:
        return pathlib.Path(env)
    if not por_defecto.exists():
        return por_defecto
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    return por_defecto.with_name(f"{por_defecto.stem}-{stamp}{por_defecto.suffix}")
```

Y las lineas `:254-257` pasan a:

```python
    out = _ruta_de_salida(pathlib.Path(__file__).parent / "consulta_abismo_resultados.md")
    out.write_text(reporte, encoding="utf-8")
```

- [ ] **Step 5: Verde y suite**

Run: `.venv/bin/python -m pytest -q test_abismo_minors.py test_abismo_contrato.py test_abismo_consulta.py test_abismo_viaje.py`
Expected: `4 passed`, `3 passed`, `5 passed`, `10 passed` (el etiquetado del viaje sigue igual al del resolvedor).

Run: `.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?`
Expected: `1444 passed, 4 warnings`, `EXIT=0`.

- [ ] **Step 6: Commit**

```bash
git add calipso/abismo/consulta.py calipso/abismo/contrato.py experimentos/consulta_abismo.py test_abismo_minors.py test_abismo_contrato.py
git commit -m "fix(abismo): minors del 1a -- armado dentro del try, env con fallback, el trim del contrato nunca corta el cierre, el banco no pisa las observaciones"
```

Riesgos anotados: la cola honesta cambia de letra (`"; hay N mas."`), pero esa frase nacio en el review del 1a DESPUES de la medicion: la letra medida (las siete lineas de `_armar` con nombres, y la variante `()`) no se toca. La lista real del catastro de Pedro se prueba en el smoke (Task 13) con `catastro.nombres()` en vivo.

---

### Task 13: Cierre de rama -- smoke en vivo con server desechable, ronda adversaria, merge

**Files:**
- Create: `docs/superpowers/2026-09-08-smoke-abismo-1b.md` (el informe del smoke, paso por paso con salidas reales)
- Create: `docs/superpowers/2026-09-08-cierre-abismo-1b/` (`README.md`, `revision-final.md`, `adversaria-eficacia.md`, `adversaria-regresiones.md`, `adversaria-completitud.md`, `ledger.md`)
- Modify: lo que la ronda encuentre (una sola ola de fix, con re-review)
- Test: la suite entera + node, y el smoke mismo

**Interfaces:**
- Consumes: todo lo anterior; el ritual documentado en `docs/superpowers/2026-09-08-cierre-capa-de-sesion/README.md` y la receta del server desechable de `docs/superpowers/2026-09-08-smoke-capa-de-sesion.md` (seccion "Entorno").
- Produces: la rama `feat/abismo-1b` mergeada a `main` con `--no-ff`, o la lista de lo que la frena.

Esta task describe el guion, no codigo. Se ejecuta a mano (o con los agentes del ritual), y cada paso deja su salida en el informe.

- [ ] **Step 1: El server desechable**

Jamas el server real ni el puerto 8000. Home nuevo y vacio, token conocido, Ollama real de la Ally (el 7b), sin `CALIPSO_NO_TOTP`:

```bash
export CALIPSO_HOME=$(mktemp -d /tmp/abismo-smoke-XXXX)
export CALIPSO_TOKEN=$(.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(24))")
cd /var/home/pedro/calipso
.venv/bin/python -m uvicorn calipso.server:app --host 127.0.0.1 --port 8772 > $CALIPSO_HOME/server.log 2>&1 &
for i in $(seq 1 40); do curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8772/login && break; sleep 1; done
ls -laR --time-style=full-iso ~/.calipso | md5sum      # la huella del home REAL, antes
```

Sembrar en ese home lo que la pesca necesita: un `chats.json` con dos conversaciones viejas (una con "El nombre de la rosa", otra con un nombre de persona y un dato de salud), un `catastro.json` con las raices reales de Pedro (copiado del real, solo lectura) y un `global/core/` con dos lineas del perfil. Registrar `catastro.nombres()` en vivo, `len(contrato.bloque_contrato(catastro.nombres()))` (tiene que dar `<= 600` y terminar en `CONSULTA.`) y CUANTOS nombres sobreviven en la linea `repo:` del bloque: con `bloque_contrato(())` en 596 de 600, se espera que entren uno o dos nombres cortos y que el catastro real caiga a la cola honesta ("un repo del catastro; hay N mas."). Ese numero, no solo el largo, es el dato con el que se evalua la promesa "preguntame por nombre" de `proyectos_brief` (Task 5, riesgos).

- [ ] **Step 2: El cliente de prueba**

`test_chat_live.py` es el molde (script manual contra `ws://localhost:8000/ws/chat` con el token de `~/.calipso/token`): se copia a `$CALIPSO_HOME/chat_live.py` apuntando a `ws://127.0.0.1:8772/ws/chat` con `CALIPSO_TOKEN`, imprimiendo CADA evento crudo con timestamp (los `abismo` en particular) y el texto visible acumulado.

- [ ] **Step 3: Una conversacion local que pesca (pasa/no pasa, con salida)**

1. "hola, que libro te conte que empece?" -> se espera `pondering` (fuente `chats`, verbo), `pescado` con `viaje.destino == "local"` y `tamano > 0`, la continuacion en la MISMA burbuja, un solo `done`. Registrar la latencia del pondering.
2. Verificar con `jq` sobre `$CALIPSO_HOME/chats.json` que el ultimo par user/assistant es UNO solo, que no hay `⟦` ni `Lo que subio` en todo el archivo, y que `telemetry.jsonl` tiene la fila `abismo`/`consulta` con `resultado: pescado` y la `chat_turn` con `abismo_consultas: 1`.
3. "y de que proyecto estaba hablando en el catastro, el de calipso?" -> `pondering` con fuente `proyecto` (o `memoria`: se registra lo que el 7b elija; lo que se mide es que la marca corte y la reentrada siga).
4. Un turno plano ("gracias") -> ningun evento `abismo`, bytes identicos (invariante 3): comparar el texto visible con lo que el server logueo.
5. El steer: mandar un mensaje largo que provoque consulta y, apenas salga `pondering`, mandar "otra cosa" en crudo -> `steered`, sin `Venias diciendo` en el log del server, y el turno siguiente contesta "otra cosa".
6. Abrir la PWA (`http://127.0.0.1:8772/?token=$CALIPSO_TOKEN`) y la fabrica (`/fabrica`) en Chromium (playwright de python, como en el smoke anterior) y repetir el paso 1 mirando: el renglon "buscando en tus chats... N s" hermano del pensando, que desaparece con `pescado` dejando el `meta` "del abismo: chats (N chars)", y que la burbuja es UNA. Captura de pantalla a `$CALIPSO_HOME/pwa.png` y `fabrica.png`.

- [ ] **Step 4: Una /nube que muestra el viaje tapado y que no salio**

Requiere una suscripcion real (`claude` en PATH) o `/nube /api` contra el LiteLLM local si esta arriba. Si ninguna esta disponible, se deja constancia y el paso queda como "no ejercitado en vivo, cubierto por test_abismo_nube.py".

1. "/nube que hablamos con <nombre sembrado> del libro?" -> `privacidad/tapado` con `[ID_1]`; luego `pondering`, `pescado` con `viaje.destino == "nube"`, `tapados` con `[ID_1]` y `texto_tapado` SIN el nombre. En la PWA, el desplegable "lo que viajo a la nube desde chats".
2. Verificar en `server.log` (o con un proxy de captura) que el system del segundo envio NO lleva nombres de repos ni el nombre de la persona, y que el `Venias diciendo` va con `[ID_1]`.
3. Los dos sumideros temporales: `ls /var/home/pedro/calipso/*.prompt.md` -> vacio (el archivo del prompt largo, dentro de ROOT, se borro) Y `ls ${TMPDIR:-/tmp}/tmp*.md 2>/dev/null | wc -l` igual antes y despues de la /nube. El BLOQUE viaja en el segundo (el archivo del system, `--append-system-prompt-file`, `tempfile` con `suffix=".md"` en el tmpdir del sistema), no en el `.prompt.md`; los dos los borra `_cleanup_subscription_files` en el `finally` (`test_los_archivos_temporales_de_las_dos_invocaciones_se_borran` lo afirma con el CLI falso).
4. Un turno /nube donde lo pescado tenga solo core (anillo 3) -> `fallo` con `solo_hondo` y la nube sigue sin el bloque.

- [ ] **Step 5: Cierre del entorno**

Matar el server, comparar la huella del home REAL con la del Step 1 (tiene que ser identica), y escribir el informe `docs/superpowers/2026-09-08-smoke-abismo-1b.md` con cada paso, su salida y PASA / NO PASA.

- [ ] **Step 6: La ronda adversaria (el ritual de la capa de sesion)**

Cuatro informes, cada uno de un agente distinto, con sondas corridas de verdad (fuera del arbol de tests, contra el server desechable o contra el paquete):

- `revision-final.md`: la rama entera (`git diff main...feat/abismo-1b`) contra el spec, seccion por seccion, con triage "debe cerrarse antes del merge" / "puede esperar".
- `adversaria-eficacia.md`: ataque a las nueve invariantes de la seccion 13 del spec. Sondas obligatorias: (1) un chunk con dos marcas validas seguidas; (2) una marca valida seguida de `⟦foco:...⟧` en el mismo chunk; (3) un `⟦` retenido por foco justo antes de `abismo:` partido en tres trozos; (4) marca de 400 y de 401 chars por el stream; (5) el steer en cada uno de los tres momentos (con el corte, durante la pesca, durante la reentrada); (6) `/nube` con credencial en el bloque y en el mensaje a la vez; (7) `chats.json` con una marca vieja adentro (sembrada a mano: la fuente `chats` la pesca y el filtro la retira otra vez?); (8) `ABISMO_BLOQUE_MAX=mucho` en el env del server; (9) el tope: cuatro marcas en una respuesta de suscripcion.
- `adversaria-regresiones.md`: que cambio para lo que ya funcionaba: `/redacta` (sin filtro del abismo), `/team`, el fallback local, el steer sin marcas, la PWA offline con el SHELL v4, la fabrica cargando otro chat a mitad de un pondering, `test_chat_live.py` a mano.
- `adversaria-completitud.md`: tabla promesa por promesa del spec (secciones 4, 5, 8, 9, 10, 11, 13, 15) y de este plan contra el codigo y los tests.

Los hallazgos se unifican, los Critical/Important pasan por refutadores independientes, y se cierran en UNA ola de fix con re-review acotado (tope 5 rondas). Minors residuales: al `ledger.md` con nombre y dueno.

- [ ] **Step 7: Merge**

```bash
.venv/bin/python -m pytest -q --ignore=test_chat_live.py; echo EXIT=$?     # 0 failed
cd calipso/web/fabrica && ~/.local/share/fnm/node-versions/v22.23.0/installation/bin/node --test 2>&1 | tail -3; cd -
git add docs/superpowers/2026-09-08-smoke-abismo-1b.md docs/superpowers/2026-09-08-cierre-abismo-1b/
git commit -m "docs(abismo): smoke en vivo del 1b y los informes del cierre de rama"
git checkout main && git merge --no-ff feat/abismo-1b -m "merge: el abismo 1b -- la consulta cableada al chat vivo (local, api, suscripcion, /nube con viaje), senal en las dos UIs y en el pulso, smoke en vivo y ronda adversaria cerrada"
git push
```

Sin rotar el token ni reiniciar el server real: eso es paso de Pedro. Actualizar el dossier de memoria `project_calipso_abismo.md` con el estado (1b en main) y lo que quedo residual.

---

## Self-review

### 1. Cobertura del spec, seccion por seccion -> task

| Spec | Requisito | Task |
|---|---|---|
| 3 | marca in-band con reentrada; continuar, no regenerar; pondering visible; /nube con viaje | 6, 7, 8, 9-11 |
| 4 `fuentes/anillos/viaje/consulta` | `viaje.py` puro con los tres pasos; `puede_viajar` real | 3 |
| 4 el filtro | hermano de foco; lista ordenada en `Emisor`; 160 de pregunta con retencion 409 (ruling); marca inconclusa se retira; tras cada chunk el bucle mira el filtro y cierra el generador | 2, 6 |
| 4 la reentrada sintetica | estado del turno junto al estado de conexion; salteos por enumeracion (gratis por el bucle exterior, medidos en `test_la_pasada_sintetica_no_repite_nada_del_turno`); prompt = system base + bloques + historial sin parcial + venias diciendo; un solo par persistido; marca jamas persistida; `num_ctx` explicito | 1, 4, 6 |
| 4 el flujo | validacion pre-corte, solo la valida corta, ilegible con aviso, fallo post-corte con reentrada sin bloque, `pescado` con tamano | 2, 6 |
| 4 regla de las rutas | local/api en vivo; suscripcion one-shot con preview congelado (y la marca a medio llegar recortada) y dos invocaciones declaradas; `/stop` durante el CLI ni pesca ni reinvoca; orquestador via `_retirar_con_aviso` + `_limpiar_marcas` (con aviso) | 6, 7 |
| 4 tope | 3 por turno; bajo el tope corta; alcanzado retira sin corte | 4, 6 (test del tope), 7 |
| 4 fallo cerrado | cualquier error degrada con `fallo` + telemetry; sin marca el filtro es transparente | 2, 6 |
| 5 gramatica y contrato | `PATRON` unica (sin anidado); contrato con indice en `internal_contract` | 2, 5 |
| 6 anillos | viaje 1-2 redactados, 3 nunca, credencial corta el envio; consolidado solo en zona personal; bloque efimero | 3, 6 (zona/consolidado, no persistencia) |
| 7 fuentes | sin cambios (1a; hueco declarado abajo: `memoria` sin ambito); las dependencias reales las inyecta `_pescar_abismo` | 6 |
| 8 /nube | contrato sin nombres + linea de marcadores; excepcion unica a la compuerta (por `prompt_reentrada`); degradado avisado (`viaje` en `pescado`, detalle en las DOS UIs); sin viaje la nube sigue (en vivo: reentrada sin bloque, declarado y aclarado en el spec; one-shot: la letra exacta, sin reinvocar); suscripcion one-shot; tramos crudos | 5, 6, 7, 8, 10, 11 |
| 9 la senal | tres fases con cierre; motivos; renglon hermano en las dos UIs con segundos en el cliente y detalle desplegable en las dos; cierre tambien en `onclose` (PWA) y `thinking` (fabrica); pulso `EVENTOS`+`CONOCIDOS` | 4, 6, 9, 10, 11 |
| 10 steering | el steer gana con el corte, durante la pesca (`_pescar_abismo` cierra en `fallo`, bloque descartado) y en la reentrada (fila `abortada_por_steer` con `momento`); one-shot: texto encolado y `/stop`; no usa `pending`; test de la carrera con las fases | 6 (y 7 para one-shot) |
| 11 casos borde | marca abierta al EOF; chats.json con el texto fusionado; modos con pipeline propio afuera (borrador sin filtro, orquestador apagado); goals no corren en la sintetica (fuera del bucle) | 2, 6, 7 |
| 12 porton | ya corrido (1a); este plan es el 1b | -- |
| 13 invariantes 1-9 | 1 (resolver local, `_pescar_abismo`), 2 (viaje + no persistencia, tests de 6 y 8), 3 (transparencia, test de 2), 4 (fallo cerrado, tests de 6), 5 (sin cobro extra: cobro fuera del bucle; usage declarado), 6 (juez solo hunde: `viaje` descarta 3 antes y falla cerrado), 7 (solo el camino filtro -> resolvedor interpreta; `_limpiar_marcas` retira lo demas), 8 (reset en `:3209`), 9 (crudo a la nube, canario en 8) | 2-8 |
| 15 verificacion | harness `ws_chat` con modelo falso (1); tests enumerados (2, 3, 4, 6, 7, 8); smoke y review final de rama (13) | 1-13 |
| 16 vocabulario | ni "cerebro" ni "capa" en el codigo nuevo | todas |

Huecos declarados (no son tasks porque el spec o los mapas los dejan afuera): el fallback local no consulta (apagado, Task 6); la rama api de /nube streamea marcadores sin reponer (preexistente, Task 8); el steer JSON de `send()` de la PWA llega crudo a `pending` (preexistente, fuera del plan); `_formatear_economia` mete el neto personal en todos los turnos (preexistente, anotado en `_consolidado_personal`); la fuente `memoria` no elige ambito (`fuentes.memoria` llama `mem.recall(pregunta, n=...)` sin `ambitos`, 1a, aunque `Memory.recall` ya lo acepta): consulta la fusion global+proyecto de siempre, y el "ambito elegible" de la seccion 7 queda para cuando haya una senal de ambito en la marca; los agentes del orquestador heredan el contrato por `base_system` (Task 7, riesgos).

### 2. Scan de placeholders

Buscado en el plan: "TBD", "TODO", "implement later", "similar a la Task", "agregar manejo", "etc." en pasos de codigo. Ninguno. Cada bloque de codigo es el que se escribe; los tres tests que se repiten entre archivos (`WSFalso`, `_sembrar_chat_viejo`, el molde del orquestador) van copiados enteros o importados por nombre desde `test_abismo_chat.py` / `test_abismo_suscripcion.py`. La Task 13 describe un guion a mano, por diseno (ruling 14).

### 3. Consistencia de nombres y firmas entre tasks

- Modulos en `server.py`: `abismo_filtro` (T2), `abismo_marca` (T2), `abismo_viaje` (T3), `abismo_turno` (T4), `abismo_contrato` (T5), `abismo_consulta` (T6). Los tests monkeypatchean `srv.abismo_consulta.resolver` (T6, T8) con ese nombre.
- `Emisor(ws, agente_id=None, resolver=None, pulso=None, filtro=None, filtros=None, avisar=None)` (T2) es lo que construyen T2 (tests), T6 (`filtros=[...]`) y lo que sigue usando el borrador (`Emisor(ws)`). `emisor.marca_abismo()` (T2) lo consume T6.
- `FiltroAbismo(puede_cortar=...)` (T2) recibe `estado_abismo.puede_cortar` (metodo de `EstadoTurno`, T4) en T6. Avisos `{"clase", "largo"[, "fuente"]}` (T2) son los que T6 lee de telemetry (`clase`).
- `preparar_viaje(bloques, destino, mapa, fuente="")` (T3) es como lo llama `_pescar_abismo` (T6); devuelve `texto`, `tapados`, `motivo`, que T6 pone en `viaje_info` y T8 lee en `viaje.tapados` / `viaje.texto_tapado`.
- `prompt_reentrada(system_base, bloques, tramos_crudos, mensaje)` (T4) se llama igual en T6 y T7; `senal(fase, fuente, **campos)` produce exactamente los dicts que T10 y T11 leen (`fase`, `fuente`, `verbo`, `tamano`, `viaje`, `motivo`).
- `cortar_en_marca`, `prefijo_congelado`, `retirar_marcas`, `recortar_abierta` (T4) son los cuatro que usa T7; `congelar=abismo_turno.prefijo_congelado` calza con `congelar(partial) -> str | None`.
- `_pescar_abismo(ws, m, estado, *, destino, mapa, departamento, agente_id=None, inbox=None) -> bool` (T6) lo llaman T6 y T7 con `agente_id=agente_id, inbox=inbox`; T9 usa ese `agente_id` para publicar.
- `_retirar_con_aviso(texto, clase)` (T2) lo llaman T7 en `_run_dynamic_team` (`clase="agente"`) y en el resto posterior del one-shot (`clase="posterior"`); las filas `retirada` con `cantidad` son las que leen el test del orquestador (T7) y el unitario (T2).
- `_run_subscription_text_live(...) -> (texto, "/stop" | texto | None)` (T7): los cuatro llamadores (`_run_agent_text`, la sintesis del equipo, el turno, el fallback entre suscripciones) siguen compilando; `_run_dynamic_team` filtra el `"/stop"`.
- `catastro.nombres()` (T5) alimenta `internal_contract` (T5) y el smoke (T13); `_sistema_nube()` (T5) es lo que `_sistema_del_turno` devuelve y lo que T8 comprueba (`_SISTEMA_NUBE_MINIMO` + `bloque_contrato(())`).
- Harness: `chat` (fixture), `ModeloEspia.guiones`/`.llamadas`, `Harness.turno/recibir/paquete/mensajes/telemetria`, `de_tipo`, `texto_visible`, `_sembrar_chat_viejo` (T1/T6) importados por T7 y T8 con esos nombres; `cli_falso.guion/llamadas` (T7) importado por T8.
- Eventos del pulso: `"abismo"` en `EVENTOS` y `CONOCIDOS` (T9), publicado con `fase`/`fuente` (T9), leido en `pulso.js` como `ev.fase`/`ev.fuente`.
- Conteos esperados de la suite: 1374 (base) -> 1376 (T1) -> 1394 (T2: 17 filtro + 1 marca) -> 1404 (T3: 10) -> 1413 (T4: 9) -> 1416 (T5: 3; `test_privacidad_nube_system.py` se reescribe, no suma) -> 1425 (T6: 9) -> 1432 (T7: 7) -> 1437 (T8: 5) -> 1440 (T9: 3) -> 1440 (T10, T11) -> 1444 (T12: 4); node 401 -> 402 (T9) -> 411 (T11: 7 en chat.test.js + 2 en arranque.test.js). Si un numero difiere en uno por un test movido, lo que manda es `0 failed` y `EXIT=0`.

### 4. Lo que cambio tras la ronda de tres lentes (2026-09-08)

Tres criticas independientes (cobertura, placeholders/consistencia, factibilidad con sonda corrida) sobre la version anterior de este plan. Aplicado, por id de informe:

- Cobertura [1] (Critical): un `/stop` durante el CLI pescaba y RE-INVOCABA. `_run_subscription_text_live` devuelve `"/stop"` como segundo valor; `_run_dynamic_team` no lo deja pisar un texto real; test `test_un_stop_durante_el_cli_no_pesca_ni_reinvoca` (Task 7).
- Cobertura [2] / Placeholders 2 / Factibilidad 1 (Critical): la bomba sobre `juez.juzgar` del test de solo hondo reventaba la compuerta del MENSAJE (confirmado con sonda). El juez doble contesta el mensaje y solo se niega al bloque; se afirma ademas que la compuerta corrio una vez (Task 8).
- Cobertura [3] / Placeholders 4: desvio del spec 8.4 en las rutas que streamean, ahora declarado (comentario en el bucle de la Task 6, riesgos de las Tasks 6 y 8, preambulo y comentarios de los tests de la Task 8, y una oracion de aclaracion en el spec, Task 8 Step 3).
- Cobertura [4]: el test de los salteos cuenta `_decide`, `goals.detect`, `_sistema_del_turno` y `_cobrar_turno` con espias (Task 6).
- Cobertura [5]: la fabrica muestra el detalle del viaje tapado (`#abismo-viaje` con `texto_tapado`, nodos fijos con id para el DOM de mentira), con test en `arranque.test.js` (Task 11).
- Cobertura [6]: `FiltroAbismo.cerrar()` vuelca un prefijo suelto (`⟦`, `⟦abi`) y solo descarta lo que ya abrio la marca; test del filtro y del Emisor compuesto; riesgo (d) de la Task 2 reescrito.
- Cobertura [7]: `_retirar_con_aviso` (Task 2, con test) para el orquestador (`:2505`) y el resto posterior del one-shot (Task 7); el test del orquestador captura telemetry en vez de anularla.
- Cobertura [8] / Factibilidad 4: `tramos_crudos` en one-shot sin las marcas ilegibles previas al corte.
- Cobertura [9]: el test del tope hace un cuarto turno (reset por mensaje real, invariante 8).
- Cobertura [10] (b): fila `abortada_por_steer` con `momento` (`pesca`, `reentrada`, `cli`); la (a) quedo superada por Factibilidad 3.
- Cobertura [11]: cierre del renglon en `ws.onclose` (PWA) y en `thinking` (fabrica, con test).
- Cobertura [12]: el `msg` del CLI que sale con error pasa por `_limpiar_marcas` (`:3066`).
- Cobertura [13]: tres tests one-shot mas (tope, marca abierta al final, `/nube /claude` con viaje fallido sin reinvocar).
- Cobertura [14]: `abismo_turno.recortar_abierta` (Task 4, con test) aplicada al preview (Task 7).
- Cobertura [15]: la reinvocacion lleva etiqueta propia de job; declarado en riesgos.
- Cobertura [16]: docstring de `preparar_viaje` (la frase "se hunde a 3" de la seccion 6 queda superada) y riesgo de la Task 7 (los agentes heredan el contrato por `base_system`).
- Cobertura [17]: hueco declarado: la fuente `memoria` no elige ambito.
- Cobertura [18]: el smoke mira los dos archivos temporales; test de los temporales de las dos invocaciones (Task 7).
- Cobertura [19]: el test de la marca valida siembra historial y afirma que viaja sin el parcial.
- Placeholders 1: el test de la zona reinicia `llamadas` del espia por turno (y la nota en Produces de la Task 1).
- Placeholders 3: el rango del preview es `:3011-3020`; el `jobs.event` de `:3021-3024` queda (reemplazar de mas era un `SyntaxError`).
- Placeholders 5: `RETENCION_MAX` es la constante que decide en `comer`.
- Placeholders 6: la restriccion global distingue la letra medida de la cola honesta; `contrato._armar` fuera del Consumes de la Task 12.
- Placeholders 7: `textoDeAbismo` de la PWA muestra los marcadores como la fabrica.
- Placeholders 8: las salidas en rojo de las Tasks 2 y 3 describen la colecta interrumpida.
- Factibilidad 2: `test_privacidad_nube_system.py:17-19` se reescribe en la Task 5 (Files, Step 1, Step 2, Step 6, `git add`).
- Factibilidad 3: `_pescar_abismo` recibe `inbox` y cierra en `fallo` si el steer llego durante la pesca; el test de la carrera afirma las fases y el orden con `steered`.
- Factibilidad 6: `pausa: 3.5` en el primer test de suscripcion (dos tics del preview, uno a cada lado de la marca).
- Factibilidad 7: el fixture del harness deja `catastro.obtener` en `lambda nombre: None`.
- Factibilidad 8: el smoke registra cuantos nombres sobreviven en el contrato.

No aplicado, con su razon:

- Factibilidad 5 ("el rojo de la Task 6 es `2 passed, 6 failed, 3 errors`"): incorrecto. Los tres `monkeypatch.setattr(srv.abismo_consulta, ...)` estan en el CUERPO de los tests, no en un fixture: pytest reporta un `AttributeError` del cuerpo como FAILED, no como ERROR; y el del steer no llega a esperar en `visto.wait(10)` porque el `setattr` viene antes. Queda `2 passed, 9 failed`, con la aclaracion en el Step 2 de la Task 6.
- Cobertura [10] (a) (declarar que la pesca emite `pescado` y despues `steered`): superado por Factibilidad 3, que arregla la conducta en vez de declararla. La letra del spec ("bloque descartado, fase `fallo`, aviso") se cumple.
