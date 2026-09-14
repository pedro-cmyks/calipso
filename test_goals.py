#!/usr/bin/env python3
"""
test_goals.py - el goal que corre (spec 2026-09-13) sobre el Goal Mode viejo.

Lo viejo que queda (create/update/add_evidence/set_criterion/set_subtask,
events) se sigue probando; `detect` y `check_auto_close` ya no existen
(ruling 15.3). Lo nuevo: campos, `transicionar` con transiciones cerradas y
escritura atomica, `activo.json` global, `golpes.jsonl`, `COMPUERTAS`, la
gramatica de `/goal`, `structured_output_de`, `contexto_recortado` y el clon.

Todo sobre un CALIPSO_HOME temporal: `goals.CALIPSO_HOME` es una constante
congelada al importar (test_aislacion_home.py la vigila), asi que el fixture
la pisa con monkeypatch ADEMAS de la variable de entorno.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import tempfile

import pytest

from calipso import github, goals


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / ".calipso"
    h.mkdir()
    monkeypatch.setenv("CALIPSO_HOME", str(h))
    monkeypatch.setattr(goals, "CALIPSO_HOME", h)
    monkeypatch.setattr(goals.telemetry, "LEDGER", h / "telemetry.jsonl")
    monkeypatch.setattr(goals.telemetry, "CALIPSO_HOME", h)
    return h


@pytest.fixture
def repo(tmp_path):
    """Un repo git temporal con un commit, SIN remoto (nunca sale a la red)."""
    r = tmp_path / "proyecto"
    r.mkdir()
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    (r / "README.md").write_text("hola\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(r), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", "inicial"], check=True)
    return r


def _telemetria(home, kind):
    p = home / "telemetry.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()
            if l.strip() and json.loads(l).get("kind") == kind]


# --- lo viejo que queda -------------------------------------------------------

def test_lo_viejo_sigue(home, tmp_path):
    project = str(tmp_path / "p")
    goal = goals.create(project, "dejame Calipso listo para usarlo desde el iPhone")
    assert goal["id"].startswith("goal_") and goal["status"] == "active"
    assert len(goal["criteria"]) >= 3 and "dispositivo" in goal["criteria"][0]["text"].lower()
    assert goals.active(project)["id"] == goal["id"]
    assert goals.activo()["id"] == goal["id"]            # el puntero es GLOBAL
    assert goals.list_goals(project)[0]["id"] == goal["id"]
    goals.add_evidence(project, goal["id"], "job", "Proceso terminado", job_id="job_demo")
    goals.set_criterion(project, goal["id"], "c1", True, "Abre en smoke visual")
    goals.set_subtask(project, goal["id"], "t1", "done")
    updated = goals.load(project, goal["id"])
    assert any(e.get("job_id") == "job_demo" for e in updated["evidence"])
    assert updated["criteria"][0]["done"] is True
    assert updated["subtasks"][0]["status"] == "done"
    assert goals.events(project, goal["id"])[-1]["action"] == "subtask"
    goals.update(project, goal["id"], status="blocked", blocker="falta Tailscale")
    assert goals.active(project)["status"] == "blocked"
    goals.update(project, goal["id"], status="complete")
    assert goals.active(project) is None


def test_detect_y_check_auto_close_ya_no_existen(home, tmp_path):
    assert not hasattr(goals, "detect")
    assert not hasattr(goals, "check_auto_close")
    project = str(tmp_path / "p")
    g = goals.create(project, "test sin auto cierre", criteria=["c a", "c b"])
    goals.set_criterion(project, g["id"], "c1", True)
    r = goals.set_criterion(project, g["id"], "c2", True)
    # todos los criterios hechos y la meta SIGUE activa: nadie es complete sin juez
    assert r["status"] == "active" and goals.load(project, g["id"])["status"] == "active"


# --- los campos y crear -------------------------------------------------------

def test_crear_nace_proposed_con_campos_y_sin_activar(home, repo):
    g = goals.crear("crea un modulo saludo.py con hola() y su test",
                    proyecto=str(repo), criterio={"tipo": "comando", "comando": "pytest -q"},
                    tope={"golpes": 6, "minutos": 10}, plan=["leer", "escribir", "probar"])
    assert g["status"] == goals.PROPOSED
    assert g["criterio"] == {"tipo": "comando", "comando": "pytest -q"}
    assert g["tope"] == {"golpes": 6, "minutos": 10, "unidades": 60, "mm": 0}
    assert g["compuertas"]["niveles"] == goals.NIVEL_DE
    assert g["compuertas"]["raices"] == [] and g["dominios"] == []
    assert g["proyecto"] == str(repo) and g["proyecto_nombre"] == "proyecto"
    assert g["repo"] is None and g["manos"] == "claude" and g["privado"] is False
    assert len(g["session_id"]) == 36
    assert goals.activo() is None                          # proposed no es activo
    assert (goals.raiz_goals() / g["id"] / "goal.json").exists()
    assert goals.load(None, g["id"])["id"] == g["id"]      # la carpeta nueva
    assert goals.list_goals()[0]["id"] == g["id"]
    assert goals.events(None, g["id"])[0]["action"] == "created"


def test_crear_sin_tope_usa_el_defecto_y_valida(home, repo):
    g = goals.crear("x", proyecto=str(repo))
    assert g["tope"] == goals.TOPE_DEFECTO
    with pytest.raises(goals.ErrorGoal):
        goals.crear("x", proyecto=str(repo), tope={"golpes": 0})
    with pytest.raises(goals.ErrorGoal):
        goals.crear("x", proyecto=str(repo), manos="gemini")
    with pytest.raises(goals.ErrorGoal):
        goals.crear("x", proyecto=str(repo), criterio={"tipo": "magia"})


def test_compuertas_es_la_tabla_de_pedro(home):
    assert goals.COMPUERTAS["directo"] == ("repo", "web", "instalar_en_goal", "raices")
    assert goals.COMPUERTAS["pregunta"] == ("merge", "push", "borrar_fuera", "raiz_nueva",
                                            "instalar_home", "instalar_sistema")
    assert goals.COMPUERTAS["nunca"] == ("gastar", "publicar", "correo", "datos_de_pedro",
                                         "rpm_ostree_rebase", "flatpak_remote_delete")
    assert goals.NIVEL_DE["merge"] == "pregunta" and goals.NIVEL_DE["gastar"] == "nunca"
    assert goals.NIVEL_DE["repo"] == "directo"
    assert set(goals.NIVEL_DE) == {f for fs in goals.COMPUERTAS.values() for f in fs}


# --- transicionar --------------------------------------------------------------

def test_transicionar_cierra_las_transiciones_y_escribe_activo(home, repo):
    g = goals.crear("x", proyecto=str(repo))
    with pytest.raises(goals.ErrorGoal):
        goals.transicionar(g["id"], goals.WAITING)           # proposed -> waiting no existe
    with pytest.raises(goals.ErrorGoal):
        goals.transicionar(g["id"], "volando")
    a = goals.transicionar(g["id"], goals.ACTIVE, "dale de Pedro")
    assert a["status"] == goals.ACTIVE and goals.activo()["id"] == g["id"]
    assert json.loads(goals.ruta_activo().read_text(encoding="utf-8"))["id"] == g["id"]
    w = goals.transicionar(g["id"], goals.WAITING, "tope", motivo_detalle={"tope": "golpes"})
    assert w["status"] == goals.WAITING and w["espera"] == {"motivo": "tope", "tope": "golpes"}
    assert goals.activo()["id"] == g["id"]                  # waiting sigue siendo el activo
    c = goals.transicionar(g["id"], goals.COMPLETE, "dale final")
    assert c["status"] == goals.COMPLETE and goals.activo() is None
    with pytest.raises(goals.ErrorGoal):
        goals.transicionar(g["id"], goals.ACTIVE)            # de un final no se sale
    evs = [e for e in goals.events(None, g["id"]) if e["action"] == "transicion"]
    assert [(e["de"], e["a"]) for e in evs] == [
        ("proposed", "active"), ("active", "waiting"), ("waiting", "complete")]
    assert evs[0]["motivo"] == "dale de Pedro"
    filas = _telemetria(home, "goal")
    assert [f["a"] for f in filas if f.get("accion") == "transicion"] == ["active", "waiting", "complete"]


def test_un_solo_goal_activo_por_server(home, repo):
    a = goals.crear("a", proyecto=str(repo))
    b = goals.crear("b", proyecto=str(repo))
    goals.transicionar(a["id"], goals.ACTIVE)
    with pytest.raises(goals.ErrorGoal, match="ya hay un goal en curso"):
        goals.transicionar(b["id"], goals.ACTIVE)
    goals.transicionar(a["id"], goals.CANCELLED, "no de Pedro")
    assert goals.transicionar(b["id"], goals.ACTIVE)["status"] == goals.ACTIVE
    # tambien con el otro en `waiting` (invariante 8 sin muerte silenciosa):
    # un tercero no lo pisa y el que espera no pierde su solicitud
    goals.transicionar(b["id"], goals.WAITING, "pregunta", motivo_detalle={"solicitud": "sol_1"})
    c = goals.crear("c", proyecto=str(repo))
    with pytest.raises(goals.ErrorGoal, match="en curso.*waiting.*esperando: pregunta"):
        goals.transicionar(c["id"], goals.ACTIVE)
    assert goals.activo()["id"] == b["id"] and goals.activo()["espera"]["solicitud"] == "sol_1"


def test_transicionar_es_atomico_y_no_deja_temporales(home, repo):
    g = goals.crear("x", proyecto=str(repo))
    goals.transicionar(g["id"], goals.ACTIVE)
    carpeta = goals.raiz_goals() / g["id"]
    assert not [p for p in carpeta.iterdir() if ".tmp" in p.name]
    assert not [p for p in goals.raiz_goals().iterdir() if ".tmp" in p.name]
    # `escribir` no toca status: un goal cargado antes de la transicion no la pisa
    viejo = goals.load(None, g["id"])
    goals.transicionar(g["id"], goals.WAITING, "tope")
    viejo["plan"] = ["otro"]
    with pytest.raises(goals.ErrorGoal, match="status"):
        goals.escribir(viejo)
    assert goals.load(None, g["id"])["status"] == goals.WAITING


def test_activo_roto_no_se_borra_solo(home, repo):
    """Trampa 17: el `active()` viejo borraba el puntero si `load` fallaba."""
    g = goals.crear("x", proyecto=str(repo))
    goals.transicionar(g["id"], goals.ACTIVE)
    (goals.raiz_goals() / g["id"] / "goal.json").write_text("{roto", encoding="utf-8")
    assert goals.activo() is None
    assert goals.ruta_activo().exists()


def test_failed_y_proposed_son_estados_validos_del_update_viejo(home, tmp_path):
    project = str(tmp_path / "p")
    g = goals.create(project, "viejo")
    assert goals.update(project, g["id"], status="failed")["status"] == "failed"
    assert goals.active(project) is None
    with pytest.raises(ValueError):
        goals.update(project, g["id"], status="volando")


def test_update_no_escribe_status_en_un_goal_que_corre(home, repo):
    """Spec seccion 3: `transicionar` es lo UNICO que escribe status en un
    goal que corre (el que tiene tope); `update(status=)` queda para los
    goals viejos (sin tope)."""
    g = goals.crear("x", proyecto=str(repo))
    with pytest.raises(ValueError, match="transicionar"):
        goals.update(None, g["id"], status="complete")
    assert goals.load(None, g["id"])["status"] == goals.PROPOSED
    # `blocker` era la otra puerta al status: el boton bloquear de la goal bar
    # vieja manda {status: blocked, blocker}; el PUT rechaza status, pero
    # blocker solo escribia BLOCKED directo y dejaba al goal fuera de
    # TRANSICIONES (ni waiting ni failed desde ahi: invariante 6)
    with pytest.raises(ValueError, match="transicionar"):
        goals.update(None, g["id"], blocker="falta Tailscale")
    en_disco = goals.load(None, g["id"])
    assert en_disco["status"] == goals.PROPOSED and en_disco["blockers"] == []
    assert not [e for e in goals.events(None, g["id"]) if e.get("action") == "updated"]
    assert goals.update(None, g["id"], title="otro")["title"] == "otro"     # el resto sigue
    # y el runner sigue pudiendo estacionar y fallar el goal
    goals.transicionar(g["id"], goals.ACTIVE)
    assert goals.transicionar(g["id"], goals.WAITING, motivo="sonda")["status"] == goals.WAITING
    assert goals.transicionar(g["id"], goals.FAILED, motivo="sonda")["status"] == goals.FAILED


# --- golpes.jsonl, consumo y tope ---------------------------------------------

def test_golpes_dos_filas_por_golpe_fundidas_y_el_consumo(home, repo):
    g = goals.crear("x", proyecto=str(repo), tope={"golpes": 2, "minutos": 1, "unidades": 5})
    goals.golpe_inicio(g["id"], 1, manos="claude", paso="leer")
    assert goals.golpes(g["id"]) == [{"n": 1, "manos": "claude", "paso": "leer",
                                      "ts": goals.golpes(g["id"])[0]["ts"], "fase": "inicio"}]
    goals.golpe_fin(g["id"], 1, unidades=3, duracion_ms=20_000, diff_stat="1 file changed",
                    veredicto_del_golpe={"estado": "sigo", "resumen": "lei"})
    filas = goals.golpes(g["id"])
    assert len(filas) == 1 and filas[0]["fase"] == "fin" and filas[0]["unidades"] == 3
    assert filas[0]["paso"] == "leer" and "ts_fin" in filas[0]
    assert goals.consumo(goals.load(None, g["id"])) == {"golpes": 1, "minutos": 0.33,
                                                         "unidades": 3, "mm": 0}
    assert goals.tope_alcanzado(goals.load(None, g["id"])) is None
    goals.golpe_inicio(g["id"], 2, manos="claude", paso="escribir")
    goals.golpe_fin(g["id"], 2, unidades=1, duracion_ms=50_000)
    assert goals.tope_alcanzado(goals.load(None, g["id"])) == "golpes"
    # un golpe que no cuenta (cuota) no suma al tope de golpes pero si al de unidades
    goals.golpe_inicio(g["id"], 3, manos="claude", paso="x")
    goals.golpe_fin(g["id"], 3, unidades=2, duracion_ms=1000, cuenta_para_tope=False)
    c = goals.consumo(goals.load(None, g["id"]))
    assert c["golpes"] == 2 and c["unidades"] == 6
    assert goals.tope_alcanzado(goals.load(None, g["id"])) == "golpes"


def test_tope_por_minutos_y_unidades(home, repo):
    g = goals.crear("x", proyecto=str(repo), tope={"golpes": 9, "minutos": 1, "unidades": 4})
    goals.golpe_inicio(g["id"], 1, manos="claude", paso="a")
    goals.golpe_fin(g["id"], 1, unidades=1, duracion_ms=61_000)
    assert goals.tope_alcanzado(goals.load(None, g["id"])) == "minutos"
    g2 = goals.crear("y", proyecto=str(repo), tope={"golpes": 9, "minutos": 90, "unidades": 4})
    goals.golpe_inicio(g2["id"], 1, manos="claude", paso="a")
    goals.golpe_fin(g2["id"], 1, unidades=4, duracion_ms=1000)
    assert goals.tope_alcanzado(goals.load(None, g2["id"])) == "unidades"


def test_golpe_sin_fin_se_ve_como_cortado(home, repo):
    g = goals.crear("x", proyecto=str(repo))
    goals.golpe_inicio(g["id"], 1, manos="claude", paso="a")
    assert goals.golpes(g["id"])[0]["fase"] == "inicio"
    assert goals.consumo(goals.load(None, g["id"]))["golpes"] == 1   # cuenta igual: se gasto


# --- la gramatica de /goal ---------------------------------------------------------

@pytest.mark.parametrize("texto,esperado", [
    ("2h", {"minutos": 120}),
    ("20 golpes", {"golpes": 20}),
    ("60 unidades", {"unidades": 60}),
    ("1h 10 golpes", {"minutos": 60, "golpes": 10}),
    ("45m", {"minutos": 45}),
    ("6 golpes 10m", {"golpes": 6, "minutos": 10}),
    ("nada", {}),
])
def test_parse_tope(texto, esperado):
    assert goals.parse_tope(texto) == esperado


def test_parse_goal_texto_con_hasta_tope_en_y_raiz():
    d = goals.parse_goal_texto(
        "crea un modulo saludo.py con hola() y su test hasta: pytest en verde "
        "tope: 6 golpes 10m en: /tmp/repo raiz: ~/Descargas")
    assert d["verbo"] is None
    assert d["texto"] == "crea un modulo saludo.py con hola() y su test"
    assert d["hasta"] == "pytest en verde"
    assert d["tope"] == {"golpes": 6, "minutos": 10}
    assert d["en"] == "/tmp/repo" and d["raiz"] == "~/Descargas"


@pytest.mark.parametrize("texto,verbo,resto", [
    ("dale", "dale", {}),
    ("dale tope: 1h raiz: ~/Descargas", "dale", {"tope": {"minutos": 60}, "raiz": "~/Descargas"}),
    ("no", "no", {}),
    ("parar", "parar", {}),
    ("segui proba con la otra libreria", "segui", {"nota": "proba con la otra libreria"}),
    ("segui con: codex", "segui", {"con": "codex"}),
    ("estado", "estado", {}),
])
def test_parse_goal_texto_verbos(texto, verbo, resto):
    d = goals.parse_goal_texto(texto)
    assert d["verbo"] == verbo
    for k, v in resto.items():
        assert d[k] == v


def test_parse_criterio():
    assert goals.parse_criterio("pytest en verde") == {"tipo": "comando", "comando": "pytest -q"}
    assert goals.parse_criterio("pytest -q tests/") == {"tipo": "comando", "comando": "pytest -q tests/"}
    assert goals.parse_criterio("existe saludo.py") == {"tipo": "archivo", "ruta": "saludo.py"}
    assert goals.parse_criterio("que salga 0: make check") == {"tipo": "comando", "comando": "make check"}
    assert goals.parse_criterio("que quede lindo") == {"tipo": "revisor", "texto": "que quede lindo"}
    assert goals.parse_criterio("") == {"tipo": "revisor", "texto": ""}


# --- structured_output_de y los textos ---------------------------------------------

def test_structured_output_de_toma_el_result():
    lineas = [json.dumps({"type": "system", "subtype": "init"}),
              json.dumps({"type": "assistant", "message": {"content": []}}),
              json.dumps({"type": "result", "subtype": "success",
                          "structured_output": {"estado": "sigo"}, "result": "{\"estado\":\"sigo\"}"})]
    assert goals.structured_output_de("\n".join(lineas)) == {"estado": "sigo"}
    # sin structured_output pero con result JSON: se parsea el string
    sin = json.dumps({"type": "result", "subtype": "success", "result": "{\"estado\":\"terminar\"}"})
    assert goals.structured_output_de(sin) == {"estado": "terminar"}
    assert goals.structured_output_de("basura\n{no json") is None
    assert goals.structured_output_de("") is None


def test_contexto_recortado_y_resumen(home, repo):
    g = goals.crear("crea saludo.py", proyecto=str(repo), tope={"golpes": 3})
    goals.transicionar(g["id"], goals.ACTIVE)
    goals.golpe_inicio(g["id"], 1, manos="claude", paso="escribir")
    goals.golpe_fin(g["id"], 1, unidades=2, duracion_ms=1000, diff_stat="1 file changed",
                    veredicto_del_golpe={"estado": "sigo", "resumen": "escribi saludo.py"})
    goals.transicionar(g["id"], goals.WAITING, "tope", motivo_detalle={"tope": "golpes"})
    ctx = goals.contexto_recortado(goals.load(None, g["id"]))
    assert "=== Goal activo ===" in ctx and g["id"] in ctx and "waiting" in ctx
    assert "ultimo golpe: 1" in ctx and "escribi saludo.py" in ctx and "espera: tope" in ctx
    assert "1 file changed" not in ctx                       # el ledger NO entra al system
    r = goals.resumen(goals.load(None, g["id"]))
    assert "1/3 golpes" in r and "2/60 unidades" in r and "waiting" in r


def test_nota_de_pedro_entra_al_ledger(home, repo):
    g = goals.crear("x", proyecto=str(repo))
    goals.nota_de_pedro(g["id"], "proba con la otra libreria")
    assert goals.load(None, g["id"])["ultima_nota"] == "proba con la otra libreria"
    ev = goals.events(None, g["id"])[-1]
    assert ev["action"] == "nota_pedro" and ev["texto"] == "proba con la otra libreria"


def test_aplicar_respuesta_preautoriza_suma_la_raiz_y_deja_la_nota(home, repo, tmp_path):
    """Lo que el si de Pedro cambia en el goal antes de retomar (decision 16):
    lo aplican igual el runner (inbox) y `/goal segui` (chat)."""
    g = goals.crear("x", proyecto=str(repo))
    goals.transicionar(g["id"], goals.ACTIVE)
    compuerta = {"familia": "instalar_home", "forma": {"argv": ["npm", "install", "-g", "x"]}}
    goals.transicionar(g["id"], goals.WAITING, "compuerta", motivo_detalle={
        "pregunta": "instalo?", "compuerta": compuerta, "solicitud": "sol_1"})
    goals.aplicar_respuesta(g["id"], "negada")
    assert not goals.load(None, g["id"])["compuertas"].get("preautorizadas")
    g2 = goals.aplicar_respuesta(g["id"], "aprobada")
    assert g2["compuertas"]["preautorizadas"] == [compuerta]
    c = json.loads((goals.dir_goal(g["id"]) / "compuertas.json").read_text(encoding="utf-8"))
    assert c["preautorizadas"] == [compuerta]
    assert g2["status"] == goals.WAITING                       # no transiciona: eso es del que llama
    goals.transicionar(g["id"], goals.ACTIVE)
    raiz = tmp_path / "Descargas"
    raiz.mkdir()
    goals.transicionar(g["id"], goals.WAITING, "raiz_nueva", motivo_detalle={
        "pregunta": "puedo?", "raiz": str(raiz), "solicitud": "sol_2"})
    assert goals.aplicar_respuesta(g["id"], "aprobada")["compuertas"]["raices"] == [str(raiz)]
    notas = [e for e in goals.events(None, g["id"]) if e["action"] == "nota_pedro"]
    assert len(notas) == 3 and "Pedro respondio: no" in notas[0]["texto"]
    # sobre una espera que no es de esas (tope, cumplido...) no toca nada
    goals.transicionar(g["id"], goals.ACTIVE)
    goals.transicionar(g["id"], goals.WAITING, "tope", motivo_detalle={"tope": "golpes"})
    assert goals.aplicar_respuesta(g["id"], "aprobada")["compuertas"]["raices"] == [str(raiz)]
    assert len([e for e in goals.events(None, g["id"]) if e["action"] == "nota_pedro"]) == 3


def test_propuesta_sin_modelo(home, repo):
    p = goals.propuesta_sin_modelo("busca cuanto cuesta un asset en sketchfab", en=None)
    assert p["manos"] == "claude" and "web" in p["familias"] and p["tope"] == goals.TOPE_DEFECTO
    assert p["criterio"]["tipo"] == "revisor" and p["aviso"]
    p2 = goals.propuesta_sin_modelo("crea saludo.py hasta que pytest pase", en=str(repo))
    assert "repo" in p2["familias"] and p2["criterio"]["tipo"] == "comando"


def test_compuertas_de_y_escribir_compuertas(home, repo):
    g = goals.crear("x", proyecto=str(repo), compuertas={"raices": ["~/Descargas"]},
                    dominios=["pypi.org"])
    g["repo"] = str(goals.dir_goal(g["id"]) / "repo")
    goals.escribir(g)
    c = goals.compuertas_de(goals.load(None, g["id"]))
    assert c["goal"] == g["id"] and c["clon"] == g["repo"] and c["cwd"] == g["repo"]
    assert c["raices"] == [os.path.expanduser("~/Descargas")]
    assert c["dominios"] == ["pypi.org"] and c["niveles"] == goals.NIVEL_DE
    assert c["preautorizadas"] == [] and c["venv"] == str(pathlib.Path(g["repo"]) / ".venv")
    assert c["registro"] == str(goals.dir_goal(g["id"]) / "hook.jsonl")
    ruta = goals.escribir_compuertas(goals.load(None, g["id"]))
    assert ruta == goals.dir_goal(g["id"]) / "compuertas.json"
    assert json.loads(ruta.read_text(encoding="utf-8")) == c


# --- el clon (github.py) -----------------------------------------------------------

def test_clonar_para_goal_crea_la_rama_y_diff_stat(home, repo, tmp_path):
    destino = tmp_path / "clon"
    r = github.clonar_para_goal(str(repo), str(destino), "goal/goal_abc")
    assert r["ok"] is True and r["clon"] == str(destino) and r["rama"] == "goal/goal_abc"
    rc, out, _ = github.git_local(["rev-parse", "--abbrev-ref", "HEAD"], cwd=str(destino))
    assert rc == 0 and out.strip() == "goal/goal_abc"
    assert github.diff_stat(str(destino)) == "" and github.diff_completo(str(destino)) == ""
    (destino / "saludo.py").write_text("def hola():\n    return 'hola'\n", encoding="utf-8")
    assert "saludo.py" in github.diff_stat(str(destino))        # incluye los sin seguimiento
    completo = github.diff_completo(str(destino))               # el diff REAL para el revisor
    assert "?? saludo.py" in completo and "+def hola" in completo
    subprocess.run(["git", "-C", str(destino), "add", "saludo.py"], check=True)
    subprocess.run(["git", "-C", str(destino), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", "saludo"], check=True)
    (destino / "README.md").write_text("hola\nchau\n", encoding="utf-8")
    completo = github.diff_completo(str(destino))
    assert "diff --git" in completo and "+chau" in completo and "saludo.py" not in completo
    assert github.diff_completo(str(destino), maximo=10).endswith("caracteres]")
    rc, out, err = github.traer_rama(str(repo), str(destino), "goal/goal_abc")
    assert rc == 0, err
    rc, out, _ = github.git_local(["branch", "--list", "goal/goal_abc"], cwd=str(repo))
    assert "goal/goal_abc" in out
    # el proyecto NO se mergeo: su HEAD sigue en el commit inicial
    rc, out, _ = github.git_local(["log", "--oneline"], cwd=str(repo))
    assert out.strip().count("\n") == 0 and "inicial" in out


def test_diff_stat_y_diff_completo_contra_la_base_del_goal(home, repo, tmp_path):
    """El runner mide contra `base_sha` (el HEAD del clon al clonar, que
    `clonar_para_goal` devuelve), no contra HEAD: el contrato manda
    commitear al cerrar cada golpe y un commit tiene que contar como diff
    nuevo (y el revisor ver el trabajo acumulado). Sin `base`, HEAD como
    siempre."""
    destino = tmp_path / "clon"
    r = github.clonar_para_goal(str(repo), str(destino), "goal/goal_base")
    rc, out, _ = github.git_local(["rev-parse", "HEAD"], cwd=str(destino))
    assert rc == 0 and r["base_sha"] == out.strip() and len(r["base_sha"]) == 40
    (destino / "saludo.py").write_text("def hola():\n    return 'hola'\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(destino), "add", "saludo.py"], check=True)
    subprocess.run(["git", "-C", str(destino), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "-m", "saludo"], check=True)
    assert github.diff_stat(str(destino)) == ""                                  # contra HEAD: nada
    assert "saludo.py" in github.diff_stat(str(destino), base=r["base_sha"])     # contra la base: el commit
    completo = github.diff_completo(str(destino), base=r["base_sha"])
    assert "diff --git" in completo and "+def hola" in completo
    assert github.diff_completo(str(destino)) == ""
    (destino / "chau.py").write_text("x\n", encoding="utf-8")                     # sin seguimiento: tambien
    assert "?? chau.py" in github.diff_stat(str(destino), base=r["base_sha"])
    assert "+x" in github.diff_completo(str(destino), base=r["base_sha"])


def test_clonar_para_goal_falla_limpio(home, tmp_path):
    r = github.clonar_para_goal(str(tmp_path / "no-existe"), str(tmp_path / "clon"), "goal/x")
    assert r["ok"] is False and r["error"]
    assert not (tmp_path / "clon").exists()


def test_clonar_para_goal_no_borra_un_destino_que_ya_existe(home, repo, tmp_path):
    """Un `destino` que la funcion no creo no se toca: un reintento del runner
    tras un crash (o la reconciliacion del arranque) sobre `dir_goal(id)/repo`
    ya clonado no puede llevarse el trabajo de los golpes anteriores."""
    destino = tmp_path / "clon"
    destino.mkdir()
    (destino / "trabajo.txt").write_text("de un golpe anterior\n", encoding="utf-8")
    r = github.clonar_para_goal(str(repo), str(destino), "goal/x")
    assert r["ok"] is False and r["clon"] is None and "ya existe" in r["error"]
    assert (destino / "trabajo.txt").read_text(encoding="utf-8") == "de un golpe anterior\n"


def test_clonar_para_goal_con_rama_invalida_borra_solo_su_clon(home, repo, tmp_path):
    """Si falla el `checkout -b`, el clon recien creado (ese SI es nuestro)
    se borra y `destino` queda sin crear."""
    destino = tmp_path / "clon"
    r = github.clonar_para_goal(str(repo), str(destino), "goal/..rota")
    assert r["ok"] is False and r["error"]
    assert not destino.exists()


def test_clonar_para_goal_copia_los_objetos_sin_enlaces_duros(home, repo, tmp_path):
    """Invariante 5: el checkout que sirve el server no es escribible desde un
    golpe. Un clone local por defecto ENLAZA (hardlink) los objetos con el
    origen: una escritura in-place sobre `.git/objects/xx/yyy` en el clon
    corromperia el objeto del proyecto real. Copia real: `st_nlink == 1` y
    otro inodo que el del origen."""
    destino = tmp_path / "clon"
    assert github.clonar_para_goal(str(repo), str(destino), "goal/x")["ok"] is True
    sueltos = [p for p in (destino / ".git" / "objects").rglob("*")
               if p.is_file() and p.parent.name not in ("info", "pack")]
    assert len(sueltos) >= 3                     # blob, tree y commit del fixture
    for objeto in sueltos:
        assert objeto.stat().st_nlink == 1, objeto
        gemelo = repo / ".git" / "objects" / objeto.parent.name / objeto.name
        assert gemelo.exists() and gemelo.stat().st_ino != objeto.stat().st_ino


# --- la raiz de trabajo: el clon y trabajo/ fuera de ~/.calipso ---------------

def test_la_raiz_de_trabajo_no_cae_bajo_lo_protegido(monkeypatch):
    """Ruling del controlador (2026-09-14): ~/.calipso esta en DENY_READ del
    sandbox y en PROTEGIDAS del hook, asi que el clon y trabajo/ viven en
    `raiz_trabajo()` (env CALIPSO_GOALS_TRABAJO o ~/.local/share/calipso/goals);
    si no, el martillo no podria leer su propio clon. Sin la env, la raiz por
    defecto no cae bajo ninguna ruta protegida (solo expanduser: no se lee ni
    se crea nada en el home real)."""
    from calipso import goals_hook, goals_manos
    monkeypatch.delenv("CALIPSO_GOALS_TRABAJO", raising=False)
    raiz = goals.raiz_trabajo()
    assert raiz == pathlib.Path(os.path.expanduser("~/.local/share/calipso/goals"))
    for protegida in (*goals_manos.DENY_READ, *goals_hook.PROTEGIDAS):
        p = pathlib.Path(os.path.expanduser(protegida))
        assert p != raiz and p not in raiz.parents, f"{raiz} cae bajo {protegida}"
    monkeypatch.setenv("CALIPSO_GOALS_TRABAJO", "/x/y")
    assert goals.raiz_trabajo() == pathlib.Path("/x/y")


def test_dir_trabajo_y_compuertas_siguen_la_raiz_de_trabajo(home, tmp_path, monkeypatch):
    """`dir_trabajo(id)` crea `<raiz>/<id>`; `compuertas_de` pone el cwd del
    goal sin repo en `<raiz>/<id>/trabajo`; el registro del hook y el resto
    (goal.json, golpes, compuertas.json) siguen en dir_goal, bajo el home."""
    monkeypatch.setenv("CALIPSO_GOALS_TRABAJO", str(tmp_path / "trabajo"))
    g = goals.crear("x", proyecto=None, tope={"golpes": 1})
    d = goals.dir_trabajo(g["id"])
    assert d == tmp_path / "trabajo" / g["id"] and d.is_dir()
    c = goals.compuertas_de(g)
    assert c["cwd"] == str(d / "trabajo") and c["clon"] is None
    assert c["registro"] == str(goals.dir_goal(g["id"]) / "hook.jsonl")
    assert not str(d).startswith(str(home)) and str(goals.dir_goal(g["id"])).startswith(str(home))


def main() -> int:
    """`tools/commands.py` corre `python test_goals.py` (allowlist test_goals)."""
    return pytest.main([__file__, "-q", "-p", "no:cacheprovider"])


if __name__ == "__main__":
    raise SystemExit(main())
