"""`/goal` de punta a punta por el harness del chat (spec goals 2026-09-13,
seccion 4): la propuesta (la cabeza se dobla: `_cabeza_del_goal`), dale, no,
parar, segui, estado, `meta:` como alias, el inbox (la propuesta es una
solicitud estacionada del motor de permisos) y `_goal_context` recortado.

Nada invoca claude ni codex: `_cabeza_del_goal` se reemplaza por una funcion
que devuelve el JSON de la propuesta. El home es temporal por test (goals,
permisos y telemetria).
"""
from __future__ import annotations

import json
import subprocess

import pytest

import calipso.server as srv
from calipso import goals, goals_manos
from calipso.permisos import almacen as permisos_almacen
from test_abismo_chat import chat, de_tipo, texto_visible  # noqa: F401

# Las funciones REALES, capturadas al importar: el fixture `chat` (que corre
# ANTES que `goal_home`) pisa `srv.goals.activo`/`active` con lambdas, y
# `srv.goals` ES `calipso.goals`, asi que `goals.activo` leido dentro del
# fixture ya seria la lambda y el setattr un no-op.
_ACTIVO_REAL = goals.activo
_ACTIVE_REAL = goals.active


PROPUESTA = {
    "titulo": "saludo.py con hola() y su test",
    "criterio": {"tipo": "comando", "comando": "pytest -q"},
    "tope": {"golpes": 6, "minutos": 10, "unidades": 30},
    "familias": ["repo"], "raices": [], "dominios": [],
    "plan": ["leer el repo", "escribir saludo.py", "escribir el test", "correr pytest"],
    "manos": "claude",
    "unidades_estimadas": 20, "minutos_estimados": 6,
}


@pytest.fixture
def goal_home(chat, tmp_path, monkeypatch):
    """El harness `chat` apaga el goal (activo -> None): aca se re-enciende
    sobre un home temporal propio, con las funciones reales capturadas
    arriba (no `goals.activo`, que a esta altura ya es la lambda)."""
    home = tmp_path / ".calipso"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("CALIPSO_HOME", str(home))
    monkeypatch.setattr(goals, "CALIPSO_HOME", home)
    monkeypatch.setattr(goals.telemetry, "LEDGER", home / "telemetry.jsonl")
    monkeypatch.setattr(srv.goals, "activo", _ACTIVO_REAL)
    monkeypatch.setattr(srv.goals, "active", _ACTIVE_REAL)
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: dict(PROPUESTA))
    # los probes de los CLIs reales NO corren en la suite: la disponibilidad
    # se fija (opus y codex "disponibles"; la cabeza esta doblada arriba)
    monkeypatch.setattr(srv, "_backend_availability",
                        lambda: {k: True for k in srv.capabilities.REGISTRY})
    monkeypatch.setattr(srv, "_backend_quota_low", lambda: {})
    return home


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proyecto"
    r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    (r / "README.md").write_text("hola\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(r), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", "inicial"], check=True)
    return r


def _dicho(eventos):
    """Lo que Calipso dijo: los chunks y los `error` (los avisos de /goal
    salen como error, molde /redacta)."""
    return texto_visible(eventos) + " " + " ".join(e["text"] for e in de_tipo(eventos, "error"))


def _proponer(chat, repo):
    return chat.turno(f"/goal crea un modulo saludo.py con hola() y su test "
                      f"hasta: pytest en verde tope: 6 golpes 10m en: {repo}")


def test_goal_propone_y_queda_proposed(goal_home, chat, repo):
    eventos = _proponer(chat, repo)
    texto = texto_visible(eventos)
    assert len(de_tipo(eventos, "done")) == 1
    assert "saludo.py con hola() y su test" in texto and "proposed" in texto
    assert "pytest -q" in texto and "6 golpes" in texto and "/goal dale" in texto
    g = goals.list_goals()[0]
    assert g["status"] == goals.PROPOSED and g["proyecto"] == str(repo)
    assert g["criterio"] == {"tipo": "comando", "comando": "pytest -q"}
    assert g["tope"] == {"golpes": 6, "minutos": 10, "unidades": 30, "mm": 0}
    assert g["plan"] == PROPUESTA["plan"] and g["manos"] == "claude"
    assert goals.activo() is None
    # el turno no ruteo a ningun modelo: la ultima llamada del modelo falso no existe
    assert chat.modelo.llamadas == []
    # y el mensaje quedo en el chat como de Calipso con route goal
    assert chat.mensajes()[-1]["meta"]["route"] == "goal"


def test_el_hasta_y_el_tope_de_pedro_pisan_a_la_propuesta(goal_home, chat, repo):
    chat.turno(f"/goal ordena el README hasta: existe README.md tope: 2 golpes en: {repo}")
    g = goals.list_goals()[0]
    assert g["criterio"] == {"tipo": "archivo", "ruta": "README.md"}
    assert g["tope"]["golpes"] == 2 and g["tope"]["minutos"] == 10   # el resto de la propuesta


def test_meta_es_alias_y_produce_proposed(goal_home, chat, repo):
    eventos = chat.turno(f"meta: dejame listo saludo.py en: {repo}")
    assert "proposed" in texto_visible(eventos)
    assert goals.list_goals()[0]["status"] == goals.PROPOSED
    assert goals.activo() is None                                  # nunca active por meta:


def test_goal_solo_es_un_aviso(goal_home, chat):
    eventos = chat.turno("/goal")
    assert de_tipo(eventos, "error") and "deci que queres" in de_tipo(eventos, "error")[0]["text"]
    assert len(de_tipo(eventos, "done")) == 1 and goals.list_goals() == []


def test_goal_privado_nace_sin_manos(goal_home, chat, repo, monkeypatch):
    llamadas = []
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: llamadas.append(a) or dict(PROPUESTA))
    eventos = chat.turno(f"/goal ordena el archivo secreto con mis password en: {repo}")
    texto = texto_visible(eventos)
    assert "privado" in texto and "manos de suscripcion" in texto
    g = goals.list_goals()[0]
    assert g["privado"] is True and g["status"] == goals.PROPOSED
    assert llamadas == []                                          # la cabeza frontera NO corrio


def test_sin_cabeza_disponible_propuesta_heuristica(goal_home, chat, repo, monkeypatch):
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: None)
    eventos = chat.turno(f"/goal crea saludo.py hasta que pytest pase en: {repo}")
    assert "la cabeza no contesto: propuesta heuristica" in texto_visible(eventos)
    assert goals.list_goals()[0]["status"] == goals.PROPOSED
    # y sin ningun backend de suscripcion disponible, ni se la llama
    llamadas = []
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: llamadas.append(1))
    monkeypatch.setattr(srv, "_backend_availability", lambda: {})
    eventos = chat.turno(f"/goal ordena el README en: {repo}")
    assert "sin cabeza frontera disponible" in texto_visible(eventos) and llamadas == []


def test_la_propuesta_es_una_solicitud_estacionada_en_el_inbox(goal_home, chat, repo):
    _proponer(chat, repo)
    g = goals.list_goals()[0]
    abiertas = permisos_almacen.abiertas()
    assert len(abiertas) == 1
    s = abiertas[0]
    assert s["estado"] == "estacionada" and s["accion"]["familia"] == "goal"
    assert s["accion"]["operacion"] == "dale" and s["accion"]["forma"] == {"goal": g["id"]}
    assert s["contexto"]["origen"] == "goal"
    # la espera apunta a la solicitud: el runner (Task 4) consume el si del inbox
    assert goals.load(None, g["id"])["espera"] == {"motivo": "dale", "solicitud": s["id"]}
    r = chat.cliente.get("/api/inbox")
    items = [i for i in r.json()["items"] if i["origen"] == "permisos"]
    assert len(items) == 1 and "saludo.py" in items[0]["titulo"]
    assert "si" in items[0]["cuerpo"]["verbos_validos"] and "no" in items[0]["cuerpo"]["verbos_validos"]


def test_dale_activa_y_cierra_la_solicitud(goal_home, chat, repo):
    _proponer(chat, repo)
    g = goals.list_goals()[0]
    eventos = chat.turno("/goal dale")
    assert "active" in texto_visible(eventos)
    assert goals.activo()["id"] == g["id"] and goals.load(None, g["id"])["status"] == goals.ACTIVE
    assert permisos_almacen.abiertas() == []
    aprobadas = [s for s in permisos_almacen.solicitudes() if s["estado"] == "aprobada"]
    assert len(aprobadas) == 1 and aprobadas[0]["respondida"]["quien"] == "pedro"


def test_dale_con_tope_y_raiz_ajusta_antes_de_arrancar(goal_home, chat, repo, tmp_path):
    _proponer(chat, repo)
    raiz = tmp_path / "descargas"
    raiz.mkdir()
    chat.turno(f"/goal dale tope: 1h raiz: {raiz}")
    g = goals.activo()
    assert g["tope"]["minutos"] == 60 and g["tope"]["golpes"] == 6
    assert g["compuertas"]["raices"] == [str(raiz)]


def test_dale_sin_proposed_avisa(goal_home, chat):
    eventos = chat.turno("/goal dale")
    assert "no hay ningun goal propuesto" in _dicho(eventos)


def test_no_cancela_la_propuesta(goal_home, chat, repo):
    _proponer(chat, repo)
    g = goals.list_goals()[0]
    eventos = chat.turno("/goal no")
    assert "cancelled" in texto_visible(eventos)
    assert goals.load(None, g["id"])["status"] == goals.CANCELLED
    assert permisos_almacen.abiertas() == []


def test_no_con_otro_goal_en_curso_cancela_la_propuesta_y_no_el_activo(goal_home, chat, repo):
    """Fix round 1: la propuesta termina con "/goal dale ... o /goal no", y ese
    `no` es sobre la PROPUESTA, nunca sobre el goal en curso (cancelled es
    final; en la Task 4 ademas mata el golpe). El goal en curso se cancela
    nombrandolo: `/goal no <id>`."""
    _proponer(chat, repo)
    chat.turno("/goal dale")
    a = goals.activo()
    _proponer(chat, repo)
    propuestos = [g for g in goals.list_goals() if g["status"] == goals.PROPOSED]
    assert len(propuestos) == 1 and propuestos[0]["id"] != a["id"]
    b = propuestos[0]
    texto = texto_visible(chat.turno("/goal no"))
    assert f"goal {b['id']} cancelled" in texto and f"/goal no {a['id']}" in texto
    assert goals.load(None, b["id"])["status"] == goals.CANCELLED
    assert goals.activo()["id"] == a["id"] and goals.activo()["status"] == goals.ACTIVE
    assert permisos_almacen.abiertas() == []
    # con el goal en curso waiting pasa lo mismo
    goals.transicionar(a["id"], goals.WAITING, "pregunta",
                       motivo_detalle={"pregunta": "x?", "solicitud": "sol_a"})
    _proponer(chat, repo)
    chat.turno("/goal no")
    assert goals.activo()["id"] == a["id"] and goals.activo()["status"] == goals.WAITING
    assert [g for g in goals.list_goals() if g["status"] == goals.PROPOSED] == []
    # nombrado, el no cancela el goal en curso
    assert f"goal {a['id']} cancelled" in texto_visible(chat.turno(f"/goal no {a['id']}"))
    assert goals.load(None, a["id"])["status"] == goals.CANCELLED and goals.activo() is None
    # un id que no existe es un aviso, no una cancelacion de otra cosa
    assert "no hay ningun goal goal_nope" in _dicho(chat.turno("/goal no goal_nope"))


def test_la_propuesta_queda_en_el_ledger_del_goal_y_en_la_telemetria(goal_home, chat, repo, monkeypatch):
    """Fix round 1 (invariantes 3 y 9): la propuesta es un golpe SIN
    herramientas que SALE a la suscripcion (el texto del goal, el repo, el
    criterio): queda como el golpe 0 en golpes.jsonl (sin contar para el
    tope) y como fila de telemetria. Un goal privado no sale a ningun lado:
    sin golpe, con la fila de telemetria que lo dice."""
    _proponer(chat, repo)
    g = goals.list_goals()[0]
    filas = goals.golpes(g["id"])
    assert len(filas) == 1
    f = filas[0]
    assert f["n"] == 0 and f["fase"] == "fin" and f["tipo"] == "propuesta"
    assert f["cuenta_para_tope"] is False and f["ok"] is True
    assert f["client"] in goals.MANOS and f["manos"] == f["client"]
    assert f["modelo"] == goals.load(None, g["id"])["propuesta"]["modelo"]
    assert f["duracion_s"] >= 0 and f["ts"] <= f["ts_fin"]
    assert goals.consumo(g) == {"golpes": 0, "minutos": 0, "unidades": 0, "mm": 0}
    ev = [e for e in srv.telemetry.recent(500)
          if e.get("kind") == "goal" and e.get("accion") == "propuesta"]
    assert len(ev) == 1 and ev[0]["goal_id"] == g["id"]
    assert ev[0]["cabeza"] == f["client"] and ev[0]["modelo"] == f["modelo"]
    assert ev[0]["ok"] is True and ev[0]["heuristica"] is False and ev[0]["privado"] is False
    # la cabeza que no contesta tambien queda: el prompt salio igual
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: None)
    chat.turno("/goal no")
    _proponer(chat, repo)
    g2 = goals.list_goals()[0]
    f2 = goals.golpes(g2["id"])[0]
    assert f2["tipo"] == "propuesta" and f2["ok"] is False and f2["cuenta_para_tope"] is False
    ev2 = [e for e in srv.telemetry.recent(500) if e.get("accion") == "propuesta"
           and e.get("goal_id") == g2["id"]]
    assert len(ev2) == 1 and ev2[0]["ok"] is False and ev2[0]["heuristica"] is True
    # el goal privado: la cabeza no corrio, nada salio, sin golpe
    chat.turno("/goal no")
    chat.turno(f"/goal ordena el archivo secreto con mis password en: {repo}")
    g3 = goals.list_goals()[0]
    assert g3["privado"] is True and goals.golpes(g3["id"]) == []
    ev3 = [e for e in srv.telemetry.recent(500) if e.get("accion") == "propuesta"
           and e.get("goal_id") == g3["id"]]
    assert len(ev3) == 1 and ev3[0]["cabeza"] is None and ev3[0]["privado"] is True
    assert ev3[0]["heuristica"] is True


def test_parar_deja_waiting_y_segui_retoma_con_nota(goal_home, chat, repo):
    _proponer(chat, repo)
    chat.turno("/goal dale")
    g = goals.activo()
    eventos = chat.turno("/goal parar")
    assert "waiting" in texto_visible(eventos)
    assert goals.load(None, g["id"])["espera"]["motivo"] == "parado por Pedro"
    eventos = chat.turno("/goal segui proba con la otra libreria")
    assert "active" in texto_visible(eventos)
    g2 = goals.load(None, g["id"])
    assert g2["status"] == goals.ACTIVE and g2["ultima_nota"] == "proba con la otra libreria"
    assert [e for e in goals.events(None, g["id"]) if e["action"] == "nota_pedro"]


def test_segui_con_cambia_las_manos(goal_home, chat, repo):
    _proponer(chat, repo)
    chat.turno("/goal dale")
    chat.turno("/goal parar")
    chat.turno("/goal segui con: codex")
    assert goals.activo()["manos"] == "codex"
    chat.turno("/goal parar")
    eventos = chat.turno("/goal segui con: gemini")
    assert "manos invalidas" in _dicho(eventos)
    assert goals.activo()["status"] == goals.WAITING


def test_segui_sin_waiting_avisa(goal_home, chat, repo):
    _proponer(chat, repo)
    chat.turno("/goal dale")
    assert "no esta esperando" in _dicho(chat.turno("/goal segui x"))


def test_estado_devuelve_el_resumen(goal_home, chat, repo):
    assert "no hay ningun goal" in _dicho(chat.turno("/goal estado"))
    _proponer(chat, repo)
    chat.turno("/goal dale")
    texto = texto_visible(chat.turno("/goal estado"))
    assert "0/6 golpes" in texto and "0/30 unidades" in texto and "active" in texto


def test_dale_sobre_waiting_cumplido_cierra_complete(goal_home, chat, repo):
    _proponer(chat, repo)
    chat.turno("/goal dale")
    g = goals.activo()
    goals.transicionar(g["id"], goals.WAITING, "cumplido", motivo_detalle={"resumen": "listo"})
    srv._estacionar_para_pedro(goals.load(None, g["id"]), "cerrar", n=3)
    eventos = chat.turno("/goal dale")
    assert "complete" in texto_visible(eventos)
    assert goals.load(None, g["id"])["status"] == goals.COMPLETE and goals.activo() is None
    assert permisos_almacen.abiertas() == []


def test_dale_con_otro_goal_esperando_avisa_y_no_lo_pisa(goal_home, chat, repo):
    """Invariante 8 con un goal waiting: el dale sobre otro no lo pisa ni lo
    hace desaparecer; el chat lo dice."""
    _proponer(chat, repo)
    chat.turno("/goal dale")
    a = goals.activo()
    goals.transicionar(a["id"], goals.WAITING, "pregunta",
                       motivo_detalle={"pregunta": "x?", "solicitud": "sol_a"})
    _proponer(chat, repo)
    eventos = chat.turno("/goal dale")
    assert "ya hay un goal en curso" in _dicho(eventos) and "esperando: pregunta" in _dicho(eventos)
    assert goals.activo()["id"] == a["id"] and goals.activo()["espera"]["solicitud"] == "sol_a"


def test_segui_sobre_una_compuerta_aplica_la_preautorizacion(goal_home, chat, repo):
    """Un `/goal segui` es un si (decision 16): aplica lo MISMO que el si del
    inbox (la forma queda preautorizada en el goal y en compuertas.json)."""
    _proponer(chat, repo)
    chat.turno("/goal dale")
    g = goals.activo()
    compuerta = {"familia": "instalar_home", "forma": {"argv": ["npm", "install", "-g", "typescript"]}}
    goals.transicionar(g["id"], goals.WAITING, "compuerta", motivo_detalle={
        "pregunta": "instalo typescript global?", "solicitud": "sol_c", "compuerta": compuerta})
    eventos = chat.turno("/goal segui dale")
    assert "active" in texto_visible(eventos)
    c = json.loads((goals.dir_goal(g["id"]) / "compuertas.json").read_text(encoding="utf-8"))
    assert c["preautorizadas"] == [compuerta]
    assert goals.load(None, g["id"])["compuertas"]["preautorizadas"] == [compuerta]


def test_en_sin_repo_git_es_un_aviso(goal_home, chat, tmp_path):
    (tmp_path / "carpeta").mkdir()
    eventos = chat.turno(f"/goal ordena esto en: {tmp_path / 'carpeta'}")
    assert "no es un repo git" in _dicho(eventos) and goals.list_goals() == []


def test_gesto_de_es_goal():
    d = srv.capabilities.parse_directives("/goal x")
    assert srv._gesto_de(d) == "/goal"
    assert srv._gesto_de(srv.capabilities.parse_directives("/goal /claude x")) == "/goal"


def test_goal_context_recortado_en_el_system(goal_home, chat, repo):
    _proponer(chat, repo)
    chat.turno("/goal dale")
    ctx = srv._goal_context()
    assert ctx.startswith("=== Goal activo ===") and "active" in ctx
    assert "golpes.jsonl" not in ctx and "criterios de listo" not in ctx


# --- los endpoints ------------------------------------------------------------

def test_endpoints_dale_parar_segui_no_estado(goal_home, chat, repo):
    _proponer(chat, repo)
    g = goals.list_goals()[0]
    c = chat.cliente
    r = c.post(f"/api/goals/{g['id']}/dale", json={"tope": "1h"})
    assert r.status_code == 200 and r.json()["goal"]["status"] == goals.ACTIVE
    assert r.json()["goal"]["tope"]["minutos"] == 60
    r = c.post(f"/api/goals/{g['id']}/parar")
    assert r.status_code == 200 and r.json()["goal"]["status"] == goals.WAITING
    r = c.post(f"/api/goals/{g['id']}/segui", json={"nota": "dale con la otra", "con": "codex"})
    assert r.status_code == 200 and r.json()["goal"]["status"] == goals.ACTIVE
    assert r.json()["goal"]["manos"] == "codex"
    r = c.get(f"/api/goals/{g['id']}/estado")
    assert r.status_code == 200 and "0/6 golpes" in r.json()["resumen"]
    # fix round 1: la propuesta es el golpe 0 del ledger (no cuenta para el tope)
    assert r.json()["consumo"]["golpes"] == 0
    assert [f["tipo"] for f in r.json()["golpes"]] == ["propuesta"]
    r = c.get(f"/api/goals/{g['id']}")
    assert r.status_code == 200 and r.json()["goal"]["id"] == g["id"]
    assert [(f["n"], f["tipo"]) for f in r.json()["golpes"]] == [(0, "propuesta")]
    r = c.post(f"/api/goals/{g['id']}/no")
    assert r.status_code == 200 and r.json()["goal"]["status"] == goals.CANCELLED
    assert c.post("/api/goals/goal_nope/dale").status_code == 404
    r = c.post(f"/api/goals/{g['id']}/dale")
    assert r.status_code == 409                                  # de cancelled no se sale


def test_put_status_y_active_dan_400(goal_home, chat, repo):
    _proponer(chat, repo)
    g = goals.list_goals()[0]
    r = chat.cliente.put(f"/api/goals/{g['id']}", json={"status": "active"})
    assert r.status_code == 400 and "dale" in r.json()["detail"]
    r = chat.cliente.put(f"/api/goals/{g['id']}", json={"active": True})
    assert r.status_code == 400
    r = chat.cliente.put(f"/api/goals/{g['id']}", json={"title": "otro"})
    assert r.status_code == 200 and r.json()["goal"]["title"] == "otro"
    assert goals.load(None, g["id"])["status"] == goals.PROPOSED


def test_api_goals_lista_con_consumo(goal_home, chat, repo):
    _proponer(chat, repo)
    r = chat.cliente.get("/api/goals")
    assert r.status_code == 200
    assert r.json()["activo"] is None and r.json()["goals"][0]["consumo"]["golpes"] == 0
    chat.turno("/goal dale")
    r = chat.cliente.get("/api/goals?limit=1")
    assert r.json()["activo"]["status"] == goals.ACTIVE and r.json()["active"]["id"] == r.json()["activo"]["id"]


def test_dale_desde_el_inbox_por_el_camino_real(goal_home, chat, repo):
    """Decision 16: el si del inbox sobre la propuesta lo consume el runner
    (proposed con espera.solicitud), sin pasar por el chat. Una
    `iteracion()` a mano del runner del server (en el harness no hay loop
    principal: _lanzar_bucle no crea la tarea)."""
    from calipso import goals_runner  # noqa: F401  (la Task 4 la trae al server)
    _proponer(chat, repo)
    g = goals.list_goals()[0]
    s = permisos_almacen.abiertas()[0]
    assert goals.load(None, g["id"])["espera"] == {"motivo": "dale", "solicitud": s["id"]}
    runner = srv._runner_de(g["id"])
    assert runner.iteracion()["accion"] == "esperando"            # sin respuesta, nada
    r = chat.cliente.post(f"/api/permisos/solicitudes/{s['id']}/responder", json={"respuesta": "si"})
    assert r.status_code == 200, r.text
    assert r.json()["ejecucion"] is None                          # estacionada: no se ejecuta ahi
    it = runner.iteracion()
    assert it["accion"] == "retomado" and goals.load(None, g["id"])["status"] == goals.ACTIVE
    assert goals.activo()["id"] == g["id"]
    assert permisos_almacen.obtener(s["id"])["estado"] == permisos_almacen.ESTADO_EJECUTADA
    # y el no del inbox cancela
    chat.turno("/goal no")
    _proponer(chat, repo)
    g2 = goals.list_goals()[0]
    s2 = permisos_almacen.abiertas()[0]
    chat.cliente.post(f"/api/permisos/solicitudes/{s2['id']}/responder", json={"respuesta": "no"})
    assert srv._runner_de(g2["id"]).iteracion()["estado"] == goals.CANCELLED


def test_help_lista_goal(goal_home, chat):
    assert "/goal" in texto_visible(chat.turno("/help"))


# --- la cabeza sin herramientas (goals_manos v1) --------------------------------

def test_argv_de_la_cabeza():
    a = goals_manos.argv_cabeza_claude("/x/claude", "/tmp/c.md", goals_manos.ESQUEMA_PROPUESTA,
                                       model="opus")
    assert a[:2] == ["/x/claude", "-p"] and "--restricted" in a
    assert a[a.index("--tools") + 1] == "" and a[a.index("--setting-sources") + 1] == ""
    assert "--strict-mcp-config" in a and "--verbose" in a
    assert a[a.index("--output-format") + 1] == "stream-json"
    assert json.loads(a[a.index("--json-schema") + 1]) == goals_manos.ESQUEMA_PROPUESTA
    assert a[a.index("--append-system-prompt-file") + 1] == "/tmp/c.md"
    assert a[a.index("--model") + 1] == "opus"
    assert not any(t.startswith("--bare") or "bypass" in t for t in a)
    b = goals_manos.argv_cabeza_codex("/x/codex", "/tmp/dir", "/tmp/out.txt", "/tmp/s.json")
    assert b[:2] == ["/x/codex", "exec"] and b[b.index("-s") + 1] == "read-only"
    assert b[b.index("-C") + 1] == "/tmp/dir" and b[b.index("-o") + 1] == "/tmp/out.txt"
    assert b[b.index("--output-schema") + 1] == "/tmp/s.json" and "--json" in b
    assert "--skip-git-repo-check" in b and b[-1] == "-"


def test_env_saneado_saca_las_credenciales(monkeypatch):
    monkeypatch.setenv("CALIPSO_TOKEN", "t")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "l")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "a")
    env = goals_manos.env_saneado()
    for k in ("CALIPSO_TOKEN", "ANTHROPIC_API_KEY", "LITELLM_MASTER_KEY", "ANTHROPIC_AUTH_TOKEN"):
        assert k not in env
    assert env["GIT_CONFIG_COUNT"] == "3" and "GIT_CONFIG_GLOBAL" not in env


def test_cabeza_sin_herramientas_con_un_cli_falso(tmp_path):
    exe = tmp_path / "claude_falso.py"
    exe.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, pathlib, sys\n"
        "base = pathlib.Path(__file__).parent\n"
        "(base / 'llamada.json').write_text(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(),"
        " 'stdin': sys.stdin.read(), 'contrato': pathlib.Path(sys.argv[sys.argv.index("
        "'--append-system-prompt-file') + 1]).read_text()}))\n"
        "print(json.dumps({'type': 'system', 'subtype': 'init'}))\n"
        "print(json.dumps({'type': 'result', 'subtype': 'success', 'structured_output':"
        " {'titulo': 'x', 'manos': 'claude'}}))\n", encoding="utf-8")
    exe.chmod(0o755)
    cwd = tmp_path / "vacio"
    cwd.mkdir()
    r = goals_manos.cabeza_sin_herramientas(
        "claude", str(exe), "SISTEMA", "PROMPT del goal", goals_manos.ESQUEMA_PROPUESTA,
        cwd=str(cwd), timeout=30)
    assert r == {"titulo": "x", "manos": "claude"}
    ll = json.loads((tmp_path / "llamada.json").read_text())
    assert ll["stdin"] == "PROMPT del goal" and ll["cwd"] == str(cwd)
    assert "-p" in ll["argv"] and "PROMPT" not in " ".join(ll["argv"])   # nunca por argv
    assert ll["contrato"] == "SISTEMA"
    assert list(cwd.iterdir()) == []                            # el contrato NO vive en el cwd
    # un CLI que falla o no da JSON -> None (fail-open hacia la heuristica)
    exe.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(3)\n", encoding="utf-8")
    assert goals_manos.cabeza_sin_herramientas(
        "claude", str(exe), "S", "P", goals_manos.ESQUEMA_PROPUESTA, cwd=str(cwd), timeout=30) is None
