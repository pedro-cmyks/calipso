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
    # dale/segui fallan rapido si las manos no estan en el PATH del server
    # (cierre 2026-09-14): en el harness estan, sin depender de la maquina
    monkeypatch.setattr(srv, "_subscription_command", lambda c: f"/x/{c}")
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


def test_sin_con_las_manos_son_claude_aunque_la_cabeza_sugiera_codex(goal_home, chat, repo, monkeypatch):
    """Ruling 2026-09-14 (cambio de la decision 14 del plan): sin `con:` las
    manos son SIEMPRE claude (la barrera verificada: sandbox + hook); la
    sugerencia de la cabeza queda en propuesta.manos_sugeridas con un aviso,
    hasta que un smoke confirme codex como manos."""
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: {**PROPUESTA, "manos": "codex"})
    eventos = _proponer(chat, repo)
    g = goals.list_goals()[0]
    assert g["manos"] == "claude"
    assert g["propuesta"]["manos_sugeridas"] == "codex"
    assert any("la cabeza sugiere codex" in a for a in g["propuesta"]["avisos"])
    assert "la cabeza sugiere codex" in _dicho(eventos) and "manos: claude" in texto_visible(eventos)


def test_con_codex_manda_las_manos(goal_home, chat, repo):
    chat.turno(f"/goal crea un modulo saludo.py con hola() y su test hasta: pytest en verde "
               f"tope: 6 golpes 10m en: {repo} con: codex")
    g = goals.list_goals()[0]
    assert g["manos"] == "codex" and g["propuesta"]["manos_sugeridas"] == "claude"
    assert not any("la cabeza sugiere" in a for a in g["propuesta"]["avisos"])


def test_con_codex_con_web_cae_a_claude_con_aviso(goal_home, chat, repo, monkeypatch):
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: {
        **PROPUESTA, "manos": "codex", "familias": ["repo", "web"], "dominios": ["pypi.org"]})
    eventos = chat.turno(f"/goal anota la version de requests que hay en pypi en VERSION.txt "
                         f"hasta: existe VERSION.txt tope: 2 golpes 5m en: {repo} con: codex")
    g = goals.list_goals()[0]
    assert g["manos"] == "claude" and g["propuesta"]["manos_sugeridas"] == "codex"
    assert any("codex corre sin red" in a for a in g["propuesta"]["avisos"])
    assert "codex corre sin red" in _dicho(eventos)


def test_con_invalido_es_un_aviso_y_no_gasta_la_cabeza(goal_home, chat, repo, monkeypatch):
    llamadas = []
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: llamadas.append(1) or dict(PROPUESTA))
    eventos = chat.turno(f"/goal crea saludo.py hasta: pytest en verde tope: 6 golpes 10m en: {repo} con: gemini")
    assert "manos invalidas" in _dicho(eventos)
    assert llamadas == [] and goals.list_goals() == []


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


# --- cierre 2026-09-14 (carril 3): dale solo proposed, segui con tope, cumplido con no ----------

def _waiting(goal_id, motivo, **detalle):
    """Deja el goal en curso waiting con un motivo y una solicitud viva."""
    return goals.transicionar(goal_id, goals.WAITING, motivo,
                              motivo_detalle={"solicitud": f"sol_{motivo}", **detalle})


def test_dale_solo_arranca_un_proposed_y_por_http_un_waiting_retoma(goal_home, chat, repo):
    """rev:server importante: `POST /api/goals/{id}/dale` sobre un waiting
    con espera compuerta lo ponia active SIN aplicar la respuesta (sin
    preautorizar la forma: el hook seguia denegando) y sin cerrar la
    solicitud abierta. Ahora `_arrancar_goal` exige proposed y el POST dale
    sobre un waiting deriva a `_retomar_goal` (un si que aplica)."""
    _proponer(chat, repo)
    chat.turno("/goal dale")
    g = goals.activo()
    compuerta = {"familia": "instalar_home", "forma": {"argv": ["npm", "install", "-g", "typescript"]}}
    _waiting(g["id"], "compuerta", pregunta="instalo typescript global?", compuerta=compuerta)
    with pytest.raises(goals.ErrorGoal, match="dale solo arranca un goal proposed"):
        srv._arrancar_goal(g["id"])
    assert goals.load(None, g["id"])["status"] == goals.WAITING
    r = chat.cliente.post(f"/api/goals/{g['id']}/dale", json={"tope": "1h"})
    assert r.status_code == 200, r.text
    g2 = goals.load(None, g["id"])
    assert g2["status"] == goals.ACTIVE and g2["tope"]["minutos"] == 60
    assert g2["compuertas"]["preautorizadas"] == [compuerta]
    c = json.loads((goals.dir_goal(g["id"]) / "compuertas.json").read_text(encoding="utf-8"))
    assert c["preautorizadas"] == [compuerta]
    # una raiz en el dale de un waiting no se aplica en silencio: 409 y que hacer
    _waiting(g["id"], "parado por Pedro")
    r = chat.cliente.post(f"/api/goals/{g['id']}/dale", json={"raiz": str(repo)})
    assert r.status_code == 409 and "segui" in r.json()["detail"]
    assert goals.load(None, g["id"])["status"] == goals.WAITING


@pytest.mark.parametrize("motivo,detalle", [
    ("pregunta", {"pregunta": "sigo con la libreria x?"}),
    ("compuerta", {"pregunta": "instalo?", "compuerta": {"familia": "instalar_home", "forma": {"argv": ["pip", "x"]}}}),
    ("raiz_nueva", {"raiz": "/var/tmp/raiz-nueva-del-test", "pregunta": "escribo ahi?"}),
    ("parado por Pedro", {}),
    ("cuota", {"manos": "claude"}),
    ("no_convergencia", {"diagnostico": "tres golpes sin diff nuevo"}),
])
def test_dale_por_chat_con_el_activo_waiting_y_sin_proposed_vale_como_segui(goal_home, chat, repo,
                                                                           motivo, detalle):
    """rev:server menor: con el goal en curso esperando y sin proposed,
    `/goal dale` (la respuesta natural a 'instalo typescript global?')
    contestaba 'no hay ningun goal propuesto': negaba el goal que esta
    esperando. Ahora vale como `segui` y lo dice."""
    _proponer(chat, repo)
    chat.turno("/goal dale")
    g = goals.activo()
    _waiting(g["id"], motivo, **detalle)
    eventos = chat.turno("/goal dale")
    texto = texto_visible(eventos)
    assert "active" in texto and "segui" in texto and not de_tipo(eventos, "error")
    g2 = goals.load(None, g["id"])
    assert g2["status"] == goals.ACTIVE
    if motivo == "compuerta":
        assert g2["compuertas"]["preautorizadas"] == [detalle["compuerta"]]
    if motivo == "raiz_nueva":
        assert detalle["raiz"] in g2["compuertas"]["raices"]


def _gastar_golpes(goal_id, n, unidades=1):
    for i in range(1, n + 1):
        goals.golpe_inicio(goal_id, i, manos="claude", paso="x")
        goals.golpe_fin(goal_id, i, unidades=unidades, duracion_ms=1000)


def test_segui_acepta_tope_y_sobre_waiting_tope_sin_tope_nuevo_dice_como(goal_home, chat, repo):
    """rev:server importante: un goal que toco el tope quedaba waiting y no
    habia camino para levantarlo: `/goal segui` descartaba `tope:` y en el
    primer tick el runner volvia a waiting:tope sin decirlo. Ahora `segui`
    (chat y POST) acepta `tope:`, y un segui sin tope nuevo sobre
    waiting:tope con el tope todavia tocado es un aviso con el comando."""
    _proponer(chat, repo)
    chat.turno("/goal dale")
    g = goals.activo()
    _gastar_golpes(g["id"], 6)                                     # el tope: 6 golpes
    goals.transicionar(g["id"], goals.WAITING, "tope", motivo_detalle={"tope": "golpes", "solicitud": "sol_t"})
    eventos = chat.turno("/goal segui dale que va")
    assert "toco el tope de golpes" in _dicho(eventos) and "/goal segui tope:" in _dicho(eventos)
    assert goals.load(None, g["id"])["status"] == goals.WAITING
    # y el dale (= segui) sobre ese waiting dice lo mismo
    assert "toco el tope de golpes" in _dicho(chat.turno("/goal dale"))
    eventos = chat.turno("/goal segui tope: 10 golpes")
    assert "active" in texto_visible(eventos) and not de_tipo(eventos, "error")
    g2 = goals.load(None, g["id"])
    assert g2["status"] == goals.ACTIVE and g2["tope"]["golpes"] == 10 and g2["tope"]["minutos"] == 10
    ev = [e for e in goals.events(None, g["id"]) if e["action"] == "tope_cambiado"]
    assert ev and ev[-1]["a"]["golpes"] == 10 and ev[-1]["de"]["golpes"] == 6
    # la nota y el tope juntos: la nota es la nota, el tope es el tope
    goals.transicionar(g["id"], goals.WAITING, "parado por Pedro")
    chat.turno("/goal segui proba con la otra libreria tope: 1h")
    g3 = goals.load(None, g["id"])
    assert g3["ultima_nota"] == "proba con la otra libreria" and g3["tope"]["minutos"] == 60
    # por HTTP: GoalSeguiBody.tope
    goals.transicionar(g["id"], goals.WAITING, "parado por Pedro")
    r = chat.cliente.post(f"/api/goals/{g['id']}/segui", json={"tope": "20 unidades"})
    assert r.status_code == 200 and r.json()["goal"]["tope"]["unidades"] == 20
    # un tope invalido por HTTP es 409, no un 500
    goals.transicionar(g["id"], goals.WAITING, "parado por Pedro")
    r = chat.cliente.post(f"/api/goals/{g['id']}/segui", json={"tope": "0 golpes"})
    assert r.status_code == 409 and "tope" in r.json()["detail"]


def test_segui_sin_tope_sobre_waiting_tope_pasa_si_el_runner_ya_lo_amplio(goal_home, chat, repo):
    """El si del inbox a la solicitud `retomar` amplia el tope un 50 %
    (goals.ampliar_tope); si el goal quedo waiting:tope igual (p. ej. otro
    goal en curso en ese momento), un `/goal segui` sin tope nuevo no
    tiene por que fallar: el tope ya no esta tocado."""
    _proponer(chat, repo)
    chat.turno("/goal dale")
    g = goals.activo()
    _gastar_golpes(g["id"], 6)
    goals.transicionar(g["id"], goals.WAITING, "tope", motivo_detalle={"tope": "golpes"})
    goals.ampliar_tope(goals.load(None, g["id"]))                  # 6 -> 9 golpes
    eventos = chat.turno("/goal segui")
    assert "active" in texto_visible(eventos) and not de_tipo(eventos, "error")
    assert goals.load(None, g["id"])["tope"]["golpes"] == 9


def test_responder_acepta_nota_y_el_runner_la_aplica_como_nota_de_pedro(goal_home, chat, repo):
    """rev:lente-spec (Pedro no se pierde): la pregunta abierta del martillo
    llegaba al inbox como si/no y no habia donde escribir el texto. Ahora
    `POST /api/permisos/solicitudes/{id}/responder` acepta `nota`, la
    guarda en la solicitud, `_evaluar_solicitud` la devuelve con el estado
    y el runner la aplica como nota de Pedro (goals.aplicar_respuesta)."""
    _proponer(chat, repo)
    g = goals.list_goals()[0]
    s = permisos_almacen.abiertas()[0]
    r = chat.cliente.post(f"/api/permisos/solicitudes/{s['id']}/responder",
                          json={"respuesta": "si", "nota": "usa la otra libreria"})
    assert r.status_code == 200, r.text
    assert r.json()["solicitud"]["nota"] == "usa la otra libreria"
    assert permisos_almacen.obtener(s["id"])["nota"] == "usa la otra libreria"
    assert srv._evaluar_solicitud(s["id"]) == ("aprobada", "usa la otra libreria")
    it = srv._runner_de(g["id"]).iteracion()
    assert it["accion"] == "retomado"
    assert goals.load(None, g["id"])["ultima_nota"] == "usa la otra libreria"
    # sin nota, lo de siempre: el estado solo, y la solicitud sin la clave
    chat.turno(f"/goal no {g['id']}")
    _proponer(chat, repo)
    s2 = permisos_almacen.abiertas()[0]
    r = chat.cliente.post(f"/api/permisos/solicitudes/{s2['id']}/responder", json={"respuesta": "no"})
    assert r.status_code == 200 and "nota" not in r.json()["solicitud"]
    assert srv._evaluar_solicitud(s2["id"]) == "negada"
    # una nota vacia o de espacios no es una nota
    g3 = goals.list_goals()[0]
    chat.turno(f"/goal no {g3['id']}")
    _proponer(chat, repo)
    s3 = permisos_almacen.abiertas()[0]
    r = chat.cliente.post(f"/api/permisos/solicitudes/{s3['id']}/responder", json={"respuesta": "si", "nota": "  "})
    assert r.status_code == 200 and "nota" not in r.json()["solicitud"]


def test_segui_sobre_cumplido_cierra_la_solicitud_cerrar_con_no_y_la_nota(goal_home, chat, repo):
    """rev:server menor: `/goal segui <nota>` sobre espera `cumplido`
    significa 'no esta cumplido, segui' y sin embargo cerraba la solicitud
    `cerrar` con `si`: el registro de permisos decia que Pedro aprobo
    'cumplido?' cuando lo devolvio con nota. Ahora se cierra con `no` y la
    nota (como el runner por el inbox); `si` solo para las otras esperas."""
    _proponer(chat, repo)
    chat.turno("/goal dale")
    g = goals.activo()
    goals.transicionar(g["id"], goals.WAITING, "cumplido", motivo_detalle={"resumen": "listo"})
    s = srv._estacionar_para_pedro(goals.load(None, g["id"]), "cerrar", n=3)
    eventos = chat.turno("/goal segui falta el test del borde")
    assert "active" in texto_visible(eventos) and not de_tipo(eventos, "error")
    s2 = permisos_almacen.obtener(s["id"])
    assert s2["estado"] == "negada" and s2["respondida"]["respuesta"] == "no"
    assert s2["nota"] == "falta el test del borde"
    g2 = goals.load(None, g["id"])
    assert g2["status"] == goals.ACTIVE and g2["ultima_nota"] == "falta el test del borde"
    assert permisos_almacen.abiertas() == []
    # sin nota: la nota del runner (`no esta cumplido: falta algo`), no un si
    goals.transicionar(g["id"], goals.WAITING, "cumplido", motivo_detalle={"resumen": "listo"})
    s = srv._estacionar_para_pedro(goals.load(None, g["id"]), "cerrar", n=5)
    chat.turno("/goal segui")
    s2 = permisos_almacen.obtener(s["id"])
    assert s2["estado"] == "negada" and "no esta cumplido" in s2["nota"]
    assert "no esta cumplido" in goals.load(None, g["id"])["ultima_nota"]
    # y sobre una pregunta el segui sigue siendo un si
    goals.transicionar(g["id"], goals.WAITING, "pregunta", motivo_detalle={"pregunta": "sigo?"})
    s = srv._estacionar_para_pedro(goals.load(None, g["id"]), "pregunta", {"n": 7}, n=7)
    chat.turno("/goal segui si, con la libreria x")
    s2 = permisos_almacen.obtener(s["id"])
    assert s2["respondida"]["respuesta"] == "si" and s2["nota"] == "si, con la libreria x"


def test_una_excepcion_cualquiera_en_goal_no_cierra_el_websocket(goal_home, chat, repo, monkeypatch):
    """rev:server menor (invariante 6: nunca tumba el chat): `_atender_goal`
    solo atrapaba ErrorGoal y la rama de ws_chat no envolvia nada: una
    propuesta con forma inesperada o un fallo del almacen subia hasta el
    handler y cerraba el websocket. Ahora el catch-all contesta `goal:
    <exc>` como error, deja la fila goal/error y el turno termina con done."""
    proponer_real = srv._proponer_goal

    def _revienta(*a, **k):
        raise RuntimeError("la propuesta vino con una lista donde iba un dict")
    monkeypatch.setattr(srv, "_proponer_goal", _revienta)
    eventos = chat.turno(f"/goal ordena el README en: {repo}")
    errores = de_tipo(eventos, "error")
    assert len(de_tipo(eventos, "done")) == 1
    assert errores and errores[0]["text"] == "goal: la propuesta vino con una lista donde iba un dict"
    ev = [e for e in srv.telemetry.recent(200) if e.get("kind") == "goal" and e.get("accion") == "error"]
    assert ev and "lista" in ev[-1]["error"] and ev[-1]["verbo"] is None
    # y el chat sigue vivo: el turno siguiente contesta como siempre
    assert texto_visible(chat.turno("hola")) == "hola Pedro"
    # un verbo que revienta tambien
    monkeypatch.setattr(srv, "_cancelar_goal", _revienta)
    monkeypatch.setattr(srv, "_proponer_goal", proponer_real)
    chat.turno(f"/goal ordena el README en: {repo}")
    eventos = chat.turno("/goal no")
    assert "goal: la propuesta vino" in _dicho(eventos) and len(de_tipo(eventos, "done")) == 1


# --- S5: la propuesta es el golpe 0 (aduana + cobro), el revisor con compuertas, traer_rama --------

def _libro_aduana(goal_home):
    libro = goal_home / "aduana.jsonl"
    if not libro.exists():
        return []
    return [json.loads(l) for l in libro.read_text(encoding="utf-8").splitlines() if l.strip()]


def test_la_propuesta_cruza_la_aduana_y_se_cobra_con_las_unidades_reales(goal_home, chat, repo, monkeypatch):
    """rev:lente-spec importante (invariante 9, spec 8, ruling 15.12): la
    propuesta salia a la suscripcion (el texto del goal, el repo, el
    criterio) sin cruzar la aduana y sin cobrarse. Ahora es el golpe 0:
    `_aduana_del_goal(goal, 0, "inicio")` ANTES de la cabeza (declarado con
    el id del goal, que se reserva antes), `"fin"` despues, la fila 0 con
    las unidades reales de `goals_manos.cabeza` y el cobro del Pagador."""
    cobros = []
    monkeypatch.setattr(srv, "_cobrar_golpe", lambda goal, unidades, manos: cobros.append(
        {"goal": goal["id"], "unidades": unidades, "manos": manos}) or {"cuenta": "personal", "unidades": unidades,
                                                                         "cobrado": False})
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: goals_manos.Cabeza(
        veredicto=dict(PROPUESTA), unidades=3, salida_tail='{"type":"result"}', session_id="s-0", exit=0))
    _proponer(chat, repo)
    g = goals.list_goals()[0]
    f = goals.golpes(g["id"])[0]
    assert f["n"] == 0 and f["tipo"] == "propuesta" and f["ok"] is True
    assert f["unidades"] == 3 and f["cuenta_para_tope"] is False and "salida_tail" not in f
    assert f["cobro"]["unidades"] == 3
    assert cobros == [{"goal": g["id"], "unidades": 3, "manos": f["client"]}]
    libro = _libro_aduana(goal_home)
    assert [x["quien"]["rutina"]["id"] for x in libro] == [g["id"], g["id"]]
    assert libro[0]["declarado"] is True and libro[0]["quien"]["origen"] == "goal"
    assert libro[0]["quien"]["proyecto"] == "proyecto"
    assert libro[1]["resultado"]["estado"] == "ok" and libro[1]["destino"] == {"host": None, "url": None}
    # el declarado salio ANTES de que existiera el goal (el id se reservo)
    assert libro[0]["ts"] <= goals.load(None, g["id"])["created_at"]
    assert goals.consumo(g)["unidades"] == 3 and goals.consumo(g)["golpes"] == 0


def test_la_cabeza_que_falla_deja_motivo_y_salida_tail_en_la_fila_0_y_no_cobra(goal_home, chat, repo, monkeypatch):
    cobros = []
    monkeypatch.setattr(srv, "_cobrar_golpe", lambda goal, unidades, manos: cobros.append(unidades) or {})
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: goals_manos.Cabeza(
        veredicto=None, unidades=0, salida_tail="Error: ghp_abcdefghijklmnop0123 no vale", motivo="exit 1", exit=1))
    eventos = _proponer(chat, repo)
    assert "la cabeza no contesto: propuesta heuristica" in texto_visible(eventos)
    g = goals.list_goals()[0]
    f = goals.golpes(g["id"])[0]
    assert f["ok"] is False and f["motivo"] == "exit 1" and f["exit"] == 1 and f["unidades"] == 0
    assert "no vale" in f["salida_tail"] and "ghp_" not in f["salida_tail"]     # tapada
    assert "cobro" not in f and cobros == []
    libro = _libro_aduana(goal_home)
    assert len(libro) == 2 and libro[1]["resultado"]["estado"] == "ok"
    # la cabeza que contesta con un dict pelado (el harness viejo) sigue valiendo
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: dict(PROPUESTA))
    chat.turno("/goal no")
    _proponer(chat, repo)
    g2 = goals.list_goals()[0]
    assert goals.golpes(g2["id"])[0]["ok"] is True and goals.golpes(g2["id"])[0]["unidades"] == 0


def test_el_goal_privado_no_cruza_la_aduana(goal_home, chat, repo):
    chat.turno(f"/goal ordena el archivo secreto con mis password en: {repo}")
    assert goals.list_goals()[0]["privado"] is True and _libro_aduana(goal_home) == []


def test_el_juez_real_le_pasa_las_compuertas_del_goal_al_revisor(goal_home, chat, repo, monkeypatch):
    """rev:lente-spec (ruling 15.7, revisor con barrera): `revisar` acepta
    `compuertas`/`compuertas_path` (carril 2) y sin ellas el revisor claude
    va sin herramientas; el server las lee de compuertas.json del goal."""
    _proponer(chat, repo)
    chat.turno("/goal dale")
    g = goals.load(None, goals.activo()["id"])
    g["compuertas"]["raices"] = ["/var/tmp/raiz-del-test"]
    goals.escribir(g)
    ruta = goals.escribir_compuertas(g)
    llamadas = []
    monkeypatch.setattr(srv.goals_manos, "revisar", lambda **k: llamadas.append(k) or {"cumplido": True,
                                                                                       "unidades": 1, "revisor": "codex"})
    monkeypatch.setattr(srv, "_subscription_command", lambda c: f"/x/{c}")
    r = srv._juez_real(g, "resumen", "diff", "salidas")
    assert r["cumplido"] is True and len(llamadas) == 1
    k = llamadas[0]
    assert k["compuertas_path"] == str(ruta)
    assert k["compuertas"] == json.loads(ruta.read_text(encoding="utf-8"))
    assert k["compuertas"]["raices"] == ["/var/tmp/raiz-del-test"]
    assert k["exes"] == {"claude": "/x/claude", "codex": "/x/codex"} and k["manos_del_golpe"] == "claude"


def test_el_runner_del_server_trae_la_rama_al_cerrar(goal_home, chat, repo, monkeypatch):
    _proponer(chat, repo)
    g = goals.list_goals()[0]
    llamadas = []
    monkeypatch.setattr(srv.calipso_github, "traer_rama",
                        lambda proyecto, clon, rama: llamadas.append((proyecto, clon, rama)) or (0, "", ""))
    runner = srv._runner_de(g["id"])
    assert runner.traer_rama_fn is not None
    goal = {**g, "repo": "/x/clon"}
    assert runner.traer_rama_fn(goal) == (0, "", "")
    assert llamadas == [(str(repo), "/x/clon", f"goal/{g['id']}")]


def test_parar_estaciona_retomar_en_el_inbox_y_segui_la_cierra(goal_home, chat, repo):
    """Pedro no se pierde (ruling del cierre): un waiting `parado por Pedro`
    no tenia solicitud y no aparecia en el inbox. Ahora `/goal parar`
    estaciona `retomar` (goals_runner.estacionar_retomar con
    _estacionar_para_pedro) y `/goal segui` la cierra con si."""
    _proponer(chat, repo)
    chat.turno("/goal dale")
    g = goals.activo()
    chat.turno("/goal parar")
    g2 = goals.load(None, g["id"])
    assert g2["status"] == goals.WAITING and g2["espera"]["motivo"] == "parado por Pedro"
    abiertas = permisos_almacen.abiertas()
    assert len(abiertas) == 1 and abiertas[0]["accion"]["operacion"] == "retomar"
    assert abiertas[0]["id"] == g2["espera"]["solicitud"]
    assert abiertas[0]["accion"]["forma"] == {"goal": g["id"], "motivo": "parado por Pedro", "vez": 1}
    assert "seguir?" in abiertas[0]["texto"] and g2["espera"]["opciones"]
    items = [i for i in chat.cliente.get("/api/inbox").json()["items"] if i["origen"] == "permisos"]
    assert len(items) == 1 and "seguir?" in items[0]["titulo"]
    chat.turno("/goal segui dale")
    assert goals.load(None, g["id"])["status"] == goals.ACTIVE and permisos_almacen.abiertas() == []
    assert permisos_almacen.obtener(abiertas[0]["id"])["respondida"]["respuesta"] == "si"
    # y por HTTP lo mismo: POST parar deja la solicitud, POST segui la cierra
    chat.cliente.post(f"/api/goals/{g['id']}/parar")
    s = permisos_almacen.abiertas()
    assert len(s) == 1 and s[0]["accion"]["forma"]["vez"] == 2
    chat.cliente.post(f"/api/goals/{g['id']}/segui", json={"nota": "sigue"})
    assert permisos_almacen.abiertas() == [] and goals.load(None, g["id"])["status"] == goals.ACTIVE


@pytest.mark.parametrize("valor", ["off", "0", "no", "OFF"])
def test_calipso_goals_off_apaga_la_funcion_entera(goal_home, chat, repo, monkeypatch, valor):
    """rev:lente-riesgo importante: no habia interruptor para apagar la
    funcion si algo sale mal en produccion (el server relanzaba bucles en
    cada arranque y cada /goal gastaba una llamada de opus). `CALIPSO_GOALS`
    (default on): off|0|no -> `_atender_goal` contesta sin gastar la
    cabeza, `_lanzar_bucle` no lanza nada (dale, segui, propuesta,
    reconciliacion) y dale/segui no transicionan (un active sin runner
    seria un goal muerto en silencio)."""
    _proponer(chat, repo)                                          # con la funcion encendida
    g = goals.list_goals()[0]
    monkeypatch.setenv("CALIPSO_GOALS", valor)
    llamadas = []
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: llamadas.append(1) or dict(PROPUESTA))
    eventos = chat.turno(f"/goal ordena el README en: {repo}")
    assert "goals apagados por CALIPSO_GOALS=off" in _dicho(eventos) and llamadas == []
    assert "goals apagados" in _dicho(chat.turno("/goal dale"))
    assert goals.load(None, g["id"])["status"] == goals.PROPOSED
    r = chat.cliente.post(f"/api/goals/{g['id']}/dale")
    assert r.status_code == 409 and "CALIPSO_GOALS" in r.json()["detail"]
    with pytest.raises(goals.ErrorGoal, match="CALIPSO_GOALS"):
        srv._retomar_goal(g["id"])
    runners = []
    monkeypatch.setattr(srv, "_runner_de", lambda gid: runners.append(gid))
    srv._lanzar_bucle(g["id"])
    assert srv._reconciliar_goals() == [g["id"]] and runners == []   # tocado, pero sin bucle
    assert srv._GOALS_EN_CURSO == {}
    # el estado sigue leyendose
    assert "proposed" in texto_visible(chat.turno("/goal estado"))


def test_calipso_goals_on_por_defecto(goal_home, chat, repo, monkeypatch):
    monkeypatch.delenv("CALIPSO_GOALS", raising=False)
    assert srv._goals_apagados() is False
    monkeypatch.setenv("CALIPSO_GOALS", "on")
    assert srv._goals_apagados() is False
    monkeypatch.setenv("CALIPSO_GOALS", "")
    assert srv._goals_apagados() is False


def test_dale_y_segui_fallan_rapido_si_las_manos_no_estan_en_el_path(goal_home, chat, repo, monkeypatch):
    """rev:lente-riesgo importante: el server resuelve claude/codex por SU
    PATH; relanzado desde una shell sin .bashrc (ssh no interactivo, un
    servicio) el goal no fallaba rapido: cada golpe devolvia exit 127 hasta
    no convergencia. Ahora `_arrancar_goal` y `_retomar_goal` lo dicen
    antes de transicionar (chat y 409 por HTTP) y no se gasta ningun golpe."""
    _proponer(chat, repo)
    g = goals.list_goals()[0]
    monkeypatch.setattr(srv, "_subscription_command", lambda c: None)
    eventos = chat.turno("/goal dale")
    assert "claude no esta en el PATH del server" in _dicho(eventos)
    assert goals.load(None, g["id"])["status"] == goals.PROPOSED and goals.activo() is None
    r = chat.cliente.post(f"/api/goals/{g['id']}/dale")
    assert r.status_code == 409 and "claude no esta en el PATH" in r.json()["detail"]
    # con las manos presentes arranca; parado, un segui con: codex sin codex falla igual
    monkeypatch.setattr(srv, "_subscription_command", lambda c: "/x/claude" if c == "claude" else None)
    chat.turno("/goal dale")
    assert goals.activo()["status"] == goals.ACTIVE
    chat.turno("/goal parar")
    assert "codex no esta en el PATH del server" in _dicho(chat.turno("/goal segui con: codex"))
    g2 = goals.load(None, g["id"])
    assert g2["status"] == goals.WAITING and g2["manos"] == "claude"    # no se cambio nada
    r = chat.cliente.post(f"/api/goals/{g['id']}/segui", json={"con": "codex"})
    assert r.status_code == 409 and "codex no esta" in r.json()["detail"]
    assert "active" in texto_visible(chat.turno("/goal segui"))


def test_post_api_goals_pasa_por_la_propuesta(goal_home, chat, repo, tmp_path, monkeypatch):
    """rev:server menor y rev:lente-spec menor: POST /api/goals creaba un
    proposed sin la validacion de `en:` (un ROOT sin .git daba un goal que
    fallaba al clonar), sin dispatch.PRIVATE (un texto privado arrancaba
    con manos claude tras el dale), sin propuesta de cabeza ni solicitud
    `dale` en el inbox, e ignoraba make_active/criteria/subtasks en
    silencio. Ahora pasa por `_proponer_goal` y lo viejo con contenido es 400."""
    llamadas = []
    monkeypatch.setattr(srv, "_cabeza_del_goal", lambda *a, **k: llamadas.append(1) or dict(PROPUESTA))
    c = chat.cliente
    r = c.post("/api/goals", json={"objective": f"crea saludo.py hasta: pytest en verde tope: 3 golpes en: {repo}",
                                   "title": "el saludo"})
    assert r.status_code == 200, r.text
    g = r.json()["goal"]
    assert g["status"] == goals.PROPOSED and g["proyecto"] == str(repo) and g["title"] == "el saludo"
    assert g["tope"]["golpes"] == 3 and g["criterio"] == {"tipo": "comando", "comando": "pytest -q"}
    assert g["propuesta"]["plan"] == PROPUESTA["plan"] and llamadas == [1]
    assert "proposed" in r.json()["texto"] and "/goal dale" in r.json()["texto"]
    s = permisos_almacen.abiertas()
    assert len(s) == 1 and s[0]["accion"]["operacion"] == "dale" and s[0]["accion"]["forma"]["goal"] == g["id"]
    assert goals.load(None, g["id"])["espera"] == {"motivo": "dale", "solicitud": s[0]["id"]}
    assert goals.golpes(g["id"])[0]["tipo"] == "propuesta"
    # privado: sin cabeza, sin manos de suscripcion
    r = c.post("/api/goals", json={"objective": f"ordena el archivo con mis password en: {repo}"})
    assert r.status_code == 200 and r.json()["goal"]["privado"] is True and llamadas == [1]
    # en: que no es repo -> 400 (antes: un proposed que fallaba al clonar)
    (tmp_path / "carpeta").mkdir()
    r = c.post("/api/goals", json={"objective": f"ordena esto en: {tmp_path / 'carpeta'}"})
    assert r.status_code == 400 and "no es un repo git" in r.json()["detail"]
    # lo viejo con contenido no se ignora en silencio
    for cuerpo in ({"objective": "x", "make_active": True}, {"objective": "x", "criteria": ["a"]},
                   {"objective": "x", "subtasks": ["b"]}):
        r = c.post("/api/goals", json=cuerpo)
        assert r.status_code == 400 and "dale" in r.json()["detail"], cuerpo
    assert c.post("/api/goals", json={"objective": "   "}).status_code == 400
    assert c.post("/api/goals", json={"objective": "dale"}).status_code == 400
