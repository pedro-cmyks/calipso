"""El bucle del goal (spec 2026-09-13, seccion 5) con MANOS FALSAS, sin
tarea de fondo: `Runner.iteracion()` se llama directo. Las inyecciones
(manos, juez, carga, consumo, pagador, preguntar, evaluar_solicitud,
sondear, clonar, diff, diff_completo, criterio, aduana) son funciones de este archivo que
anotan lo que reciben. La aduana con origen goal y el Pagador con unidades
se prueban de verdad al final, y el apagado/arranque del server con un
proceso falso vivo.

El clon y la carpeta de trabajo viven en `goals.dir_trabajo(id)` (ruling
del controlador 2026-09-14: fuera de ~/.calipso, que es DENY_READ del
sandbox y PROTEGIDA del hook); goal.json, golpes, compuertas.json,
contrato.md y hook.jsonl siguen en `goals.dir_goal(id)`.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import threading
import time

import pytest

import calipso.server as srv
from calipso import aduana, goals, goals_manos as gm, goals_runner as gr
from calipso.economia import departamentos as deps
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.permisos import almacen as permisos_almacen
from test_carga import medida
from test_goals_manos import cli_falso_stream, lineas_golpe  # noqa: F401


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / ".calipso"
    h.mkdir()
    monkeypatch.setenv("CALIPSO_HOME", str(h))
    monkeypatch.setenv("CALIPSO_GOALS_TRABAJO", str(tmp_path / "trabajo"))
    monkeypatch.setattr(goals, "CALIPSO_HOME", h)
    monkeypatch.setattr(goals.telemetry, "LEDGER", h / "telemetry.jsonl")
    monkeypatch.setattr(goals.telemetry, "CALIPSO_HOME", h)
    return h


class Falsas:
    """Las inyecciones del runner, con guion y memoria."""

    def __init__(self, resultados=(), juicios=(), nivel="holgada", consumo=None):
        self.resultados = list(resultados)     # Resultado por golpe, en orden (el ultimo se repite)
        self.juicios = list(juicios)           # dict del revisor por llamada (None = sin otra familia)
        self.nivel = nivel
        self.consumo_valor = consumo or {"codex_used_percent": 10.0, "claude_limite": False, "resets_at": None}
        self.llamadas = {"manos": [], "juez": [], "pagador": [], "preguntar": [], "aduana": [],
                         "criterio": [], "sondear": 0, "clonar": 0, "evaluar": []}
        self.solicitudes = {}                  # id -> estado ("aprobada"/"negada"/None)
        self.criterio_ok = True

    def manos(self, goal, n, prompt, contrato, cancelar):
        # invariante 3: la fila `inicio` de ESTE golpe ya esta en el ledger
        ultima = goals.golpes(goal["id"])[-1]
        assert ultima["fase"] == "inicio" and ultima["n"] == n, "golpe sin fila inicio antes de ejecutarse"
        self.llamadas["manos"].append({"n": n, "prompt": prompt, "contrato": contrato, "manos": goal["manos"]})
        r = self.resultados[min(len(self.llamadas["manos"]) - 1, len(self.resultados) - 1)]
        return r

    def juez(self, goal, resumen, diff, salidas):
        # invariante 3 tambien para el revisor: su fila `inicio` (manos
        # revisor:<otra familia>, paso revisar) ya esta en el ledger
        ultima = goals.golpes(goal["id"])[-1]
        assert ultima["fase"] == "inicio" and ultima["manos"].startswith("revisor:"), \
            "revisor sin fila inicio antes de ejecutarse"
        assert ultima["paso"] == "revisar"
        self.llamadas["juez"].append({"resumen": resumen, "diff": diff, "n": ultima["n"]})
        if not self.juicios:
            return None
        return self.juicios[min(len(self.llamadas["juez"]) - 1, len(self.juicios) - 1)]

    def carga(self):
        return medida(self.nivel)

    def consumo(self):
        return dict(self.consumo_valor)

    def pagador(self, goal, unidades, manos):
        self.llamadas["pagador"].append({"unidades": unidades, "manos": manos})
        return {"cuenta": "personal", "cobrado": False, "unidades": unidades}

    def preguntar(self, goal, operacion, forma_extra=None, titulo=None, n=0):
        sid = f"sol_{len(self.llamadas['preguntar']) + 1}"
        self.llamadas["preguntar"].append({"operacion": operacion, "forma": forma_extra, "n": n, "id": sid})
        self.solicitudes[sid] = None
        return {"id": sid, "estado": "estacionada"}

    def evaluar(self, sid):
        self.llamadas["evaluar"].append(sid)
        return self.solicitudes.get(sid)

    def sondear(self, compuertas_path):
        self.llamadas["sondear"] += 1
        return True, "hook activo"

    def clonar(self, goal):
        self.llamadas["clonar"] += 1
        clon = goals.dir_trabajo(goal["id"]) / "repo"
        (clon / ".git").mkdir(parents=True, exist_ok=True)
        return {"ok": True, "clon": str(clon), "rama": f"goal/{goal['id']}", "error": None}

    def diff(self, goal):
        return getattr(self, "diff_valor", "saludo.py | 3 +++")

    def diff_completo(self, goal):
        return getattr(self, "diff_completo_valor",
                       "diff --git a/saludo.py b/saludo.py\n+def hola():\n+    return 'hola'")

    def criterio(self, goal):
        self.llamadas["criterio"].append(goal["criterio"])
        return self.criterio_ok, "1 passed" if self.criterio_ok else "1 failed"

    def aduana(self, goal, n, fase, **campos):
        self.llamadas["aduana"].append({"n": n, "fase": fase, **campos})

    def runner(self, goal_id):
        return gr.Runner(goal_id, manos=self.manos, juez=self.juez, carga_fn=self.carga,
                         consumo_fn=self.consumo, pagador_fn=self.pagador, preguntar=self.preguntar,
                         evaluar_solicitud=self.evaluar, sondear=self.sondear,
                         clonar=self.clonar, diff_fn=self.diff, diff_completo_fn=self.diff_completo,
                         correr_criterio=self.criterio, aduana_fn=self.aduana)


FUTURO = int(time.time()) + 3600      # un resets_at que todavia no paso
PASADO = 1789330200                   # 2026-09-13T20:10Z: una ventana ya vencida


def resultado(estado="sigo", resumen="hice algo", unidades=2, comandos=(), exit=0, motivo=None,
              timeout=False, matado=False, veredicto=None, stderr="", rate=0.37, pregunta=None,
              compuerta=None, resets_at=PASADO, stdout=""):
    v = veredicto if veredicto is not None else {"estado": estado, "resumen": resumen}
    if pregunta:
        v["pregunta"] = pregunta
    if compuerta:
        v["compuerta"] = compuerta
    return gm.Resultado(exit=exit, motivo=motivo, timeout=timeout, matado=matado, session_id="s-1",
                        unidades=unidades, comandos=[{"id": f"t{i}", "cmd": c, "resultado_tail": r}
                                                     for i, (c, r) in enumerate(comandos)],
                        veredicto=v if exit == 0 and not matado else None,
                        rate_limit={"five_hour": rate, "seven_day": 0.1, "resets_at": resets_at},
                        duracion_ms=1500, costo_usd=0.05, stderr_tail=stderr, stdout_tail=stdout,
                        subtype="success")


def goal_activo(home, tmp_path, **campos):
    proyecto = tmp_path / "proyecto"
    if not proyecto.exists():
        proyecto.mkdir()
        subprocess.run(["git", "init", "-q", str(proyecto)], check=True)
        (proyecto / "README.md").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(proyecto), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(proyecto), "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-q", "-m", "i"], check=True)
    base = dict(proyecto=str(proyecto), criterio={"tipo": "comando", "comando": "pytest -q"},
                tope={"golpes": 6, "minutos": 60, "unidades": 60})
    base.update(campos)
    g = goals.crear("crea saludo.py con hola() y su test", **base)
    return goals.transicionar(g["id"], goals.ACTIVE, "dale")


def filas(goal_id):
    return goals.golpes(goal_id)


# --- el ciclo entero ---------------------------------------------------------------

def test_el_ciclo_entero(home, tmp_path):
    """proposed -> dale -> golpes -> terminar -> criterio ok -> revisor de
    otra familia falla -> sigue -> cumple -> waiting cumplido -> Pedro ->
    complete."""
    f = Falsas(resultados=[resultado("sigo", "escribi saludo.py", comandos=[("ls", "a")]),
                           resultado("terminar", "listo", comandos=[("pytest -q", "1 passed")]),
                           resultado("terminar", "agregue el test")],
               juicios=[{"cumplido": False, "falta": ["falta el test de hola"], "nota": "casi", "revisor": "codex"},
                        {"cumplido": True, "falta": [], "nota": "bien", "revisor": "codex"}])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    # golpe 1: clona, sondea el hook, escribe compuertas, golpea, cobra, anota
    it = r.iteracion()
    assert it["accion"] == "golpe" and it["estado"] == goals.ACTIVE and it["n"] == 1
    assert f.llamadas["clonar"] == 1 and f.llamadas["sondear"] == 1
    g1 = goals.load(None, g["id"])
    assert g1["repo"] == str(goals.dir_trabajo(g["id"]) / "repo")
    assert (goals.dir_goal(g["id"]) / "compuertas.json").exists()
    assert (goals.dir_goal(g["id"]) / "contrato.md").exists()
    fl = filas(g["id"])
    assert fl[0]["fase"] == "fin" and fl[0]["unidades"] == 2 and fl[0]["diff_stat"] == "saludo.py | 3 +++"
    assert fl[0]["veredicto_del_golpe"] == {"estado": "sigo", "resumen": "escribi saludo.py"}
    assert fl[0]["comandos"][0]["cmd"] == "ls" and fl[0]["cobro"]["unidades"] == 2
    assert fl[0]["rate_limit"]["five_hour"] == 0.37 and fl[0]["manos"] == "claude"
    assert f.llamadas["pagador"] == [{"unidades": 2, "manos": "claude"}]
    assert [a["fase"] for a in f.llamadas["aduana"]] == ["inicio", "fin"]
    m1 = f.llamadas["manos"][0]
    assert "crea saludo.py" in m1["prompt"] and "pytest -q" in m1["contrato"]
    assert "golpe 1" not in m1["prompt"]                          # el primer golpe no tiene ledger
    # golpe 2: terminar -> criterio ok -> revisor dice que falta -> sigue
    it = r.iteracion()
    assert it["accion"] == "juez" and it["estado"] == goals.ACTIVE
    assert f.llamadas["criterio"] == [g["criterio"]] and len(f.llamadas["juez"]) == 1
    assert f.llamadas["juez"][0]["diff"].startswith("diff --git")  # el diff REAL, no el diff_stat (ruling 15.1)
    fl = filas(g["id"])
    assert len(fl) == 3                                           # golpe 2 + la fila del revisor
    assert fl[2]["manos"] == "revisor:codex" and fl[2]["juez"]["cumplido"] is False
    assert fl[2]["juez"]["independencia"] == "proveedor_distinto"
    assert fl[1]["juez"]["criterio"] == {"ok": True, "salida": "1 passed"}
    assert f.llamadas["pagador"][-1] == {"unidades": 1, "manos": "revisor:codex"}
    # golpe 3: el prompt lleva la falta SIN recortar y el ledger resumido con el diff_stat
    it = r.iteracion()
    m3 = f.llamadas["manos"][2]
    assert "falta el test de hola" in m3["prompt"] and "saludo.py | 3 +++" in m3["prompt"]
    assert "golpe 1" in m3["prompt"] and "escribi saludo.py" in m3["prompt"]
    assert it["accion"] == "juez" and it["estado"] == goals.WAITING
    g3 = goals.load(None, g["id"])
    assert g3["espera"]["motivo"] == "cumplido" and g3["espera"]["solicitud"] == "sol_1"
    assert f.llamadas["preguntar"][-1]["operacion"] == "cerrar"
    # waiting: sin respuesta, nada; con el si de Pedro, complete
    assert r.iteracion()["accion"] == "esperando"
    f.solicitudes["sol_1"] = "aprobada"
    it = r.iteracion()
    assert it["accion"] == "complete" and it["estado"] == goals.COMPLETE
    assert goals.load(None, g["id"])["status"] == goals.COMPLETE and goals.activo() is None
    assert r.iteracion()["accion"] == "nada"
    tele = [json.loads(l) for l in (home / "telemetry.jsonl").read_text().splitlines()]
    # golpe 1, golpe 2, revisor 3, golpe 4, revisor 5
    assert [x["n"] for x in tele if x["kind"] == "goal" and x.get("accion") == "golpe"] == [1, 2, 3, 4, 5]


def test_dale_desde_el_inbox_arranca_y_no_desde_el_inbox_cancela(home, tmp_path):
    """Un proposed con su solicitud `dale` estacionada: el runner la mira."""
    f = Falsas(resultados=[resultado("sigo")])
    g = goals.crear("x", proyecto=None, tope={"golpes": 2})
    goal = goals.load(None, g["id"])
    goal["espera"] = {"motivo": "dale", "solicitud": "sol_dale"}
    goals.escribir(goal)
    r = f.runner(g["id"])
    f.solicitudes["sol_dale"] = None
    assert r.iteracion()["accion"] == "esperando"
    f.solicitudes["sol_dale"] = "aprobada"
    it = r.iteracion()
    assert it["accion"] == "retomado" and it["estado"] == goals.ACTIVE
    g2 = goals.crear("y", proyecto=None, tope={"golpes": 2})
    goal2 = goals.load(None, g2["id"])
    goal2["espera"] = {"motivo": "dale", "solicitud": "sol_no"}
    goals.escribir(goal2)
    f.solicitudes["sol_no"] = "negada"
    assert f.runner(g2["id"]).iteracion()["estado"] == goals.CANCELLED


# --- los cuatro topes ------------------------------------------------------------------

def test_tope_de_golpes(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo")])
    g = goal_activo(home, tmp_path, tope={"golpes": 2, "minutos": 60, "unidades": 60})
    r = f.runner(g["id"])
    assert r.iteracion()["accion"] == "golpe"
    it = r.iteracion()
    assert it["accion"] == "golpe" and it["estado"] == goals.WAITING
    assert goals.load(None, g["id"])["espera"] == {"motivo": "tope", "tope": "golpes",
                                                    "consumo": goals.consumo(goals.load(None, g["id"]))}
    assert len(f.llamadas["manos"]) == 2


def test_tope_de_minutos(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo")])
    f.resultados[0].duracion_ms = 61_000
    g = goal_activo(home, tmp_path, tope={"golpes": 9, "minutos": 1, "unidades": 60})
    r = f.runner(g["id"])
    assert r.iteracion()["estado"] == goals.WAITING
    assert goals.load(None, g["id"])["espera"]["tope"] == "minutos"


def test_tope_de_unidades(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo", unidades=40)])
    g = goal_activo(home, tmp_path, tope={"golpes": 9, "minutos": 60, "unidades": 40})
    assert f.runner(g["id"]).iteracion()["estado"] == goals.WAITING
    assert goals.load(None, g["id"])["espera"]["tope"] == "unidades"


def test_tope_de_mm_no_frena_en_cero(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo")])
    g = goal_activo(home, tmp_path, tope={"golpes": 9, "minutos": 60, "unidades": 60, "mm": 0})
    assert f.runner(g["id"]).iteracion()["estado"] == goals.ACTIVE


# --- no convergencia, JSON invalido, timeout ----------------------------------------------

def test_no_convergencia_tres_golpes_sin_diff_nuevo(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo")])
    f.diff_valor = ""
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    assert r.iteracion()["estado"] == goals.ACTIVE
    assert r.iteracion()["estado"] == goals.ACTIVE
    it = r.iteracion()
    assert it["estado"] == goals.WAITING
    e = goals.load(None, g["id"])["espera"]
    assert e["motivo"] == "no_convergencia" and "tres golpes" in e["diagnostico"]
    assert any("cambiar el plan" in o for o in e["opciones"])
    assert any("cambiar de manos" in o for o in e["opciones"])


def test_no_convergencia_misma_falta_dos_veces(home, tmp_path):
    f = Falsas(resultados=[resultado("terminar")],
               juicios=[{"cumplido": False, "falta": ["falta x"], "nota": "", "revisor": "codex"}])
    g = goal_activo(home, tmp_path, criterio={"tipo": "revisor", "texto": ""})
    r = f.runner(g["id"])
    f.diff_valor = "a"
    assert r.iteracion()["estado"] == goals.ACTIVE
    f.diff_valor = "b"
    assert r.iteracion()["estado"] == goals.WAITING
    assert "misma falta" in goals.load(None, g["id"])["espera"]["diagnostico"]


def test_no_convergencia_mismo_comando_fallando(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo", comandos=[("pytest -q", "1 failed, exit code 1")])])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    f.diff_valor = "a"
    assert r.iteracion()["estado"] == goals.ACTIVE
    f.diff_valor = "b"
    assert r.iteracion()["estado"] == goals.WAITING
    assert "mismo comando" in goals.load(None, g["id"])["espera"]["diagnostico"]


def test_no_converge_es_puro():
    assert gr.no_converge([]) is None
    base = [{"n": i, "fase": "fin", "diff_stat": "", "comandos": []} for i in (1, 2)]
    assert gr.no_converge(base) is None
    assert "tres golpes" in gr.no_converge(base + [{"n": 3, "fase": "fin", "diff_stat": "", "comandos": []}])
    con_juez = [{"n": 1, "fase": "fin", "diff_stat": "a", "juez": {"falta": ["x", "y"]}},
                {"n": 2, "fase": "fin", "diff_stat": "b", "juez": {"falta": ["y", "x"]}}]
    assert "misma falta" in gr.no_converge(con_juez)


def test_veredicto_invalido_cuenta_y_se_le_dice(home, tmp_path):
    f = Falsas(resultados=[resultado(veredicto={"estado": "volando"}), resultado("sigo")])
    f.resultados[0].veredicto = {"estado": "volando"}
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    it = r.iteracion()
    assert it["accion"] == "golpe" and it["estado"] == goals.ACTIVE
    assert filas(g["id"])[0]["veredicto_invalido"] is True
    r.iteracion()
    assert "veredicto anterior no fue valido" in f.llamadas["manos"][1]["prompt"]


def test_la_fila_fin_guarda_la_salida_cruda_solo_cuando_el_golpe_falla(home, tmp_path):
    """Ruling 2026-09-14: un golpe que falla dice por que en el ledger
    (invariante "nunca muere en silencio"). Con exit != 0 la fila `fin`
    lleva `salida_tail` = los ultimos 1500 caracteres del stdout crudo,
    pasados por el detector; con veredicto y exit 0 no se guarda (el stream
    ya esta resumido en la fila)."""
    cola = "\nerror: token ghp_abcdefghijklmnopqrstuvwxyz0123 no sirve\n"
    f = Falsas(resultados=[resultado(exit=1, stdout="relleno " * 300 + "x" * 1400 + cola),
                           resultado("sigo", stdout='{"type": "result", "subtype": "success"}')])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    r.iteracion()
    r.iteracion()
    fl = filas(g["id"])
    assert fl[0]["exit"] == 1 and "salida_tail" in fl[0]
    assert fl[0]["salida_tail"].endswith("error: token [SECRETO] no sirve\n")
    assert "ghp_" not in fl[0]["salida_tail"] and not fl[0]["salida_tail"].startswith("relleno")
    assert len(fl[0]["salida_tail"]) <= 1500 and fl[0]["secretos_tapados"] >= 1
    assert fl[1]["exit"] == 0 and fl[1]["veredicto_del_golpe"]["estado"] == "sigo"
    assert "salida_tail" not in fl[1]


def test_la_salida_cruda_tambien_queda_con_golpe_matado_o_sin_veredicto_ni_result(home, tmp_path):
    """Las otras dos formas de morir en silencio: matado (timeout, parar) y
    un exit 0 sin veredicto ni linea `result` (el CLI corto sin decir nada)."""
    mudo = gm.Resultado(exit=0, session_id="s-1", unidades=0, duracion_ms=10, stdout_tail="una linea suelta")
    f = Falsas(resultados=[resultado(exit=None, motivo="timeout", timeout=True, matado=True, stdout="a medias"),
                           mudo])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    r.iteracion()
    f.diff_valor = "otro.py | 1 +"
    r.iteracion()
    fl = filas(g["id"])
    assert fl[0]["motivo"] == "timeout" and fl[0]["salida_tail"] == "a medias"
    assert fl[1]["exit"] == 0 and fl[1]["veredicto_del_golpe"] is None and fl[1]["salida_tail"] == "una linea suelta"


def test_timeout_cuenta_como_golpe(home, tmp_path):
    f = Falsas(resultados=[resultado(exit=None, motivo="timeout", timeout=True, matado=True), resultado("sigo")])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    assert r.iteracion()["estado"] == goals.ACTIVE
    assert filas(g["id"])[0]["motivo"] == "timeout" and filas(g["id"])[0]["cuenta_para_tope"] is not False


# --- preguntar, compuerta, raiz nueva ------------------------------------------------------

def test_preguntar_deja_waiting_y_la_respuesta_retoma(home, tmp_path):
    f = Falsas(resultados=[resultado("preguntar", "necesito saber", pregunta="uso pytest o unittest?"),
                           resultado("sigo")])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    it = r.iteracion()
    assert it["estado"] == goals.WAITING
    e = goals.load(None, g["id"])["espera"]
    assert e["motivo"] == "pregunta" and e["pregunta"] == "uso pytest o unittest?" and e["solicitud"] == "sol_1"
    assert f.llamadas["preguntar"][0]["operacion"] == "pregunta"
    assert f.llamadas["preguntar"][0]["forma"] == {"n": 1, "pregunta": "uso pytest o unittest?"}
    f.solicitudes["sol_1"] = "aprobada"
    assert r.iteracion()["estado"] == goals.ACTIVE
    r.iteracion()
    assert "Pedro respondio: si" in f.llamadas["manos"][1]["prompt"]


def test_compuerta_pregunta_preautoriza_en_el_goal(home, tmp_path):
    f = Falsas(resultados=[resultado("preguntar", "instalar", pregunta="instalo typescript global?",
                                     compuerta={"familia": "instalar_home",
                                                "forma": {"argv": ["npm", "install", "-g", "typescript"]}}),
                           resultado("sigo")])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    assert r.iteracion()["estado"] == goals.WAITING
    assert f.llamadas["preguntar"][0]["operacion"] == "compuerta"
    f.solicitudes["sol_1"] = "aprobada"
    assert r.iteracion()["estado"] == goals.ACTIVE
    c = json.loads((goals.dir_goal(g["id"]) / "compuertas.json").read_text())
    assert c["preautorizadas"] == [{"familia": "instalar_home",
                                    "forma": {"argv": ["npm", "install", "-g", "typescript"]}}]
    # y al cerrar el goal la preautorizacion expira
    goals.transicionar(g["id"], goals.WAITING, "parado por Pedro")
    goals.transicionar(g["id"], goals.CANCELLED, "no")
    r.iteracion()
    c = json.loads((goals.dir_goal(g["id"]) / "compuertas.json").read_text())
    assert c["preautorizadas"] == []


def test_compuerta_nunca_no_se_pregunta(home, tmp_path):
    f = Falsas(resultados=[resultado("preguntar", "publicar", pregunta="hago el PR?",
                                     compuerta={"familia": "publicar", "forma": {}}),
                           resultado("sigo")])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    assert r.iteracion()["estado"] == goals.ACTIVE
    assert f.llamadas["preguntar"] == []
    r.iteracion()
    assert "NUNCA" in f.llamadas["manos"][1]["prompt"]


def test_raiz_nueva_aprobada_se_suma_al_goal(home, tmp_path):
    raiz = tmp_path / "Descargas"
    raiz.mkdir()
    f = Falsas(resultados=[resultado("preguntar", "raiz", pregunta="puedo escribir en Descargas?",
                                     compuerta={"familia": "raiz_nueva", "forma": {"raiz": str(raiz)}}),
                           resultado("sigo")])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    assert r.iteracion()["estado"] == goals.WAITING
    f.solicitudes["sol_1"] = "aprobada"
    r.iteracion()
    assert goals.load(None, g["id"])["compuertas"]["raices"] == [str(raiz)]


# --- carga y cuota -------------------------------------------------------------------------

def test_cargada_pospone_sin_gastar(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo")], nivel="cargada")
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    it = r.iteracion()
    assert it["accion"] == "pospuesto" and it["estado"] == goals.ACTIVE
    assert f.llamadas["manos"] == [] and filas(g["id"]) == []
    tele = [json.loads(l) for l in (home / "telemetry.jsonl").read_text().splitlines()]
    pos = [x for x in tele if x["kind"] == "carga" and x.get("accion") == "pospone"]
    assert pos and pos[0]["rutina"] == "goal" and pos[0]["rutina_id"] == g["id"]
    f.nivel = "justa"
    assert r.iteracion()["accion"] == "golpe"


def test_el_sensor_de_carga_que_revienta_no_frena_el_goal(home, tmp_path):
    """Molde _tick_con_carga: un fallo del sensor (ps, /proc) deja su fila
    `vigia_error` y el goal golpea sin nivel; nunca queda failed por eso."""
    f = Falsas(resultados=[resultado("sigo")])

    def carga():
        raise RuntimeError("ps se colgo")
    f.carga = carga
    g = goal_activo(home, tmp_path)
    it = f.runner(g["id"]).iteracion()
    assert it["accion"] == "golpe" and it["estado"] == goals.ACTIVE
    tele = [json.loads(l) for l in (home / "telemetry.jsonl").read_text().splitlines()]
    assert any(x["kind"] == "carga" and x.get("accion") == "vigia_error" and x.get("rutina_id") == g["id"]
               for x in tele)


def test_cuota_agotada_deja_waiting_sin_caer_al_7b(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo")],
               consumo={"codex_used_percent": 95.0, "claude_limite": False, "resets_at": FUTURO})
    g = goal_activo(home, tmp_path, manos="codex")
    r = f.runner(g["id"])
    it = r.iteracion()
    assert it["accion"] == "cuota" and it["estado"] == goals.WAITING
    e = goals.load(None, g["id"])["espera"]
    assert e["motivo"] == "cuota" and e["resets_at"] == FUTURO and f.llamadas["manos"] == []
    assert goals.load(None, g["id"])["manos"] == "codex"      # nadie cambio de manos


def test_la_cuota_de_codex_con_la_ventana_vencida_no_frena(home, tmp_path):
    """El freno pasivo no es pegajoso: una lectura cuyo `resets_at` ya paso
    es de una ventana vieja (nadie la refresca sin golpear) y no vale."""
    f = Falsas(resultados=[resultado("sigo")],
               consumo={"codex_used_percent": 95.0, "claude_limite": False, "resets_at": PASADO})
    g = goal_activo(home, tmp_path, manos="codex")
    it = f.runner(g["id"]).iteracion()
    assert it["accion"] == "golpe" and it["estado"] == goals.ACTIVE and len(f.llamadas["manos"]) == 1
    # claude_limite con la ventana vencida tampoco
    f2 = Falsas(resultados=[resultado("sigo")],
                consumo={"codex_used_percent": 0.0, "claude_limite": True, "resets_at": PASADO})
    goals.transicionar(g["id"], goals.CANCELLED, "x")
    g2 = goal_activo(home, tmp_path)
    assert f2.runner(g2["id"]).iteracion()["accion"] == "golpe"
    # y con la ventana viva si frena
    f3 = Falsas(resultados=[resultado("sigo")],
                consumo={"codex_used_percent": 0.0, "claude_limite": True, "resets_at": FUTURO})
    goals.transicionar(g2["id"], goals.CANCELLED, "x")
    g3 = goal_activo(home, tmp_path)
    assert f3.runner(g3["id"]).iteracion()["accion"] == "cuota"


def test_fallo_del_cli_por_cuota_no_cuenta_contra_el_tope(home, tmp_path):
    f = Falsas(resultados=[resultado(exit=1, stderr="You've hit your usage limit. resets at 18:00")])
    g = goal_activo(home, tmp_path, tope={"golpes": 1, "minutos": 60, "unidades": 60})
    r = f.runner(g["id"])
    it = r.iteracion()
    assert it["estado"] == goals.WAITING and goals.load(None, g["id"])["espera"]["motivo"] == "cuota"
    fl = filas(g["id"])
    assert fl[0]["cuenta_para_tope"] is False and goals.consumo(goals.load(None, g["id"]))["golpes"] == 0


def test_el_ultimo_rate_limit_de_claude_frena(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo", rate=0.96, resets_at=FUTURO), resultado("sigo")])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    assert r.iteracion()["estado"] == goals.ACTIVE
    it = r.iteracion()
    assert it["accion"] == "cuota" and goals.load(None, g["id"])["espera"]["motivo"] == "cuota"
    assert goals.load(None, g["id"])["espera"]["resets_at"] == FUTURO and len(f.llamadas["manos"]) == 1


def test_el_rate_limit_de_claude_con_la_ventana_vencida_no_frena(home, tmp_path):
    """La fila del ledger no se refresca sin golpear: si su `resets_at` ya
    paso, la ventana es otra y el goal golpea (antes quedaba atrapado en
    waiting cuota hasta `segui con: codex` o cancelar)."""
    f = Falsas(resultados=[resultado("sigo", rate=0.96, resets_at=PASADO), resultado("sigo")])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    assert r.iteracion()["estado"] == goals.ACTIVE
    it = r.iteracion()
    assert it["accion"] == "golpe" and it["estado"] == goals.ACTIVE and len(f.llamadas["manos"]) == 2


def test_el_segui_de_pedro_no_vuelve_a_caer_en_la_cuota_ya_vista(home, tmp_path):
    """Una lectura anterior a la ultima activacion ya freno una vez: el
    `/goal segui` de Pedro (una activacion nueva) golpea, y la lectura del
    golpe nuevo decide de ahi en mas."""
    f = Falsas(resultados=[resultado("sigo", rate=0.96, resets_at=FUTURO),
                           resultado("sigo", rate=0.97, resets_at=FUTURO)])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    assert r.iteracion()["estado"] == goals.ACTIVE
    assert r.iteracion()["accion"] == "cuota"
    # _now() resuelve segundos: la lectura vieja queda ANTES de la activacion
    # y el golpe nuevo DESPUES (un empate cuenta como lectura nueva)
    time.sleep(1.1)
    goals.transicionar(g["id"], goals.ACTIVE, "segui de Pedro")
    time.sleep(1.1)
    it = r.iteracion()
    assert it["accion"] == "golpe" and len(f.llamadas["manos"]) == 2
    assert r.iteracion()["accion"] == "cuota"                  # la lectura NUEVA (0.97, viva) frena


# --- el juez -------------------------------------------------------------------------------

def test_criterio_no_cumplido_sigue_sin_revisor(home, tmp_path):
    f = Falsas(resultados=[resultado("terminar"), resultado("sigo")],
               juicios=[{"cumplido": True, "falta": [], "nota": "", "revisor": "codex"}])
    f.criterio_ok = False
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    assert r.iteracion()["estado"] == goals.ACTIVE
    assert f.llamadas["juez"] == []                            # el criterio medible corta antes
    assert filas(g["id"])[0]["juez"]["criterio"] == {"ok": False, "salida": "1 failed"}
    r.iteracion()
    assert "criterio" in f.llamadas["manos"][1]["prompt"] and "1 failed" in f.llamadas["manos"][1]["prompt"]


def test_criterio_archivo_y_numero(home, tmp_path):
    g = goal_activo(home, tmp_path, criterio={"tipo": "archivo", "ruta": "saludo.py"})
    goal = goals.load(None, g["id"])
    goal["repo"] = str(tmp_path / "clon")
    (tmp_path / "clon").mkdir()
    goals.escribir(goal)
    ok, salida = gr.juzgar_criterio(goals.load(None, g["id"]), None)
    assert ok is False and "no existe" in salida
    (tmp_path / "clon" / "saludo.py").write_text("x", encoding="utf-8")
    assert gr.juzgar_criterio(goals.load(None, g["id"]), None)[0] is True
    goals.transicionar(g["id"], goals.CANCELLED, "x")
    g2 = goal_activo(home, tmp_path, criterio={"tipo": "numero", "metrica": "unidades", "umbral": 5,
                                                 "comparacion": "<="})
    goals.golpe_inicio(g2["id"], 1, manos="claude", paso="x")
    goals.golpe_fin(g2["id"], 1, unidades=3, duracion_ms=1)
    assert gr.juzgar_criterio(goals.load(None, g2["id"]), None)[0] is True
    assert gr.juzgar_criterio({"criterio": {"tipo": "revisor"}, "id": g2["id"]}, None) == (None, "sin criterio medible")
    # un criterio compuesto no se corre (corre FUERA del sandbox): falla
    ok, salida = gr.juzgar_criterio({"criterio": {"tipo": "comando", "comando": "pytest -q; curl x"},
                                     "id": g2["id"], "repo": str(tmp_path / "clon")}, None)
    assert ok is False and "compuesto" in salida
    ok, salida = gr.juzgar_criterio({"criterio": {"tipo": "comando", "comando": "true"},
                                     "id": g2["id"], "repo": str(tmp_path / "clon")}, None)
    assert ok is True


def test_sin_otra_familia_pedro_sin_veredicto_de_modelo(home, tmp_path):
    f = Falsas(resultados=[resultado("terminar")], juicios=[])      # juez -> None
    g = goal_activo(home, tmp_path, criterio={"tipo": "revisor", "texto": "que quede lindo"})
    r = f.runner(g["id"])
    it = r.iteracion()
    assert it["estado"] == goals.WAITING
    e = goals.load(None, g["id"])["espera"]
    assert e["motivo"] == "cumplido" and e["sin_veredicto_de_modelo"] is True
    assert e["independencia"] == "ninguna" and "sin veredicto de modelo" in e["resumen"]
    assert f.llamadas["preguntar"][0]["operacion"] == "cerrar"
    # la fila del revisor se abrio ANTES de invocarlo (invariante 3) y cierra sin cobrar ni contar
    fl = filas(g["id"])
    assert fl[1]["manos"] == "revisor:codex" and fl[1]["fase"] == "fin" and fl[1]["motivo"] == "sin otra familia"
    assert fl[1]["unidades"] == 0 and fl[1]["cuenta_para_tope"] is False and "cobro" not in fl[1]


def test_el_revisor_es_un_golpe_con_fila_inicio_antes_y_sin_golpe_apagado(home, tmp_path):
    """Spec 6.2: el revisor cuenta como golpe y se cobra. Invariante 3: su
    fila `inicio` va ANTES de invocarlo (Falsas.juez lo exige), y mientras
    corren el criterio y el revisor `sin_golpe` esta apagado (parar y el
    apagado los esperan en vez de transicionar por encima)."""
    f = Falsas(resultados=[resultado("terminar")],
               juicios=[{"cumplido": True, "falta": [], "nota": "bien", "revisor": "codex"}])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    vistos = {}
    juez_base, crit_base = f.juez, f.criterio

    def juez(goal, resumen, diff, salidas):
        vistos["revisor"] = r.sin_golpe.is_set()
        return juez_base(goal, resumen, diff, salidas)

    def criterio(goal):
        vistos["criterio"] = r.sin_golpe.is_set()
        return crit_base(goal)
    r.juez, r.correr_criterio = juez, criterio
    it = r.iteracion()
    assert it["estado"] == goals.WAITING and vistos == {"criterio": False, "revisor": False}
    assert r.sin_golpe.is_set() and r.golpe_en_curso is None
    fl = filas(g["id"])
    assert fl[1]["manos"] == "revisor:codex" and fl[1]["paso"] == "revisar" and fl[1]["fase"] == "fin"
    assert fl[1]["unidades"] == 1 and fl[1]["cobro"]["unidades"] == 1 and fl[1]["ts"] and fl[1]["ts_fin"]
    assert fl[1]["duracion_ms"] >= 0 and f.llamadas["juez"][0]["n"] == 2


def test_parar_durante_el_revisor_no_transiciona_y_deja_la_fila(home, tmp_path):
    """`cancelar` puesto mientras corre el revisor (parar/apagar lo mataron:
    vuelve None): la fila del revisor cierra con motivo cancelado, sin
    cobro, y el runner NO transiciona (lo hace parar/apagar, sin la carrera
    waiting -> waiting). Si el revisor alcanzo a contestar, la revision
    queda anotada pero tampoco se transiciona. Y con `cancelar` puesto
    durante el criterio, el revisor ni se invoca."""
    f = Falsas(resultados=[resultado("terminar")], juicios=[])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    juez_base = f.juez

    def juez_matado(goal, resumen, diff, salidas):
        juez_base(goal, resumen, diff, salidas)
        r.cancelar.set()
        return None
    r.juez = juez_matado
    it = r.iteracion()
    assert it["motivo"] == "cancelado" and goals.load(None, g["id"])["status"] == goals.ACTIVE
    fl = filas(g["id"])
    assert fl[1]["manos"] == "revisor:codex" and fl[1]["motivo"] == "cancelado"
    assert fl[1]["cuenta_para_tope"] is False and "cobro" not in fl[1]
    assert f.llamadas["preguntar"] == [] and f.llamadas["pagador"][-1]["manos"] == "claude"
    assert fl[0]["juez"]["criterio"]["ok"] is True
    # el revisor que alcanzo a contestar: queda anotado y cobrado, no se transiciona
    r.cancelar.clear()
    f.juicios = [{"cumplido": True, "falta": [], "nota": "ok", "revisor": "codex"}]

    def juez_justo(goal, resumen, diff, salidas):
        v = juez_base(goal, resumen, diff, salidas)
        r.cancelar.set()
        return v
    r.juez = juez_justo
    it = r.iteracion()
    assert it["motivo"] == "cancelado" and goals.load(None, g["id"])["status"] == goals.ACTIVE
    fl = filas(g["id"])
    assert fl[3]["manos"] == "revisor:codex" and fl[3]["juez"]["cumplido"] is True and fl[3]["cobro"]["unidades"] == 1
    assert f.llamadas["preguntar"] == []
    # cancelar durante el criterio: el revisor no se invoca
    r.cancelar.clear()
    antes = len(f.llamadas["juez"])

    def criterio(goal):
        r.cancelar.set()
        return True, "1 passed"
    r.correr_criterio = criterio
    it = r.iteracion()
    assert it["motivo"] == "cancelado" and len(f.llamadas["juez"]) == antes
    assert goals.load(None, g["id"])["status"] == goals.ACTIVE and filas(g["id"])[-1]["manos"] == "claude"
    assert r.sin_golpe.is_set()


def test_criterio_medible_ok_y_sin_otra_familia_es_cumplido_con_criterio(home, tmp_path):
    f = Falsas(resultados=[resultado("terminar")], juicios=[])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    assert r.iteracion()["estado"] == goals.WAITING
    e = goals.load(None, g["id"])["espera"]
    assert e["motivo"] == "cumplido" and e["independencia"] == "ninguna" and e["criterio"]["ok"] is True


# --- hook inactivo, clon que falla, manos que revientan ----------------------------------------

def test_hook_inactivo_es_failed(home, tmp_path):
    f = Falsas(resultados=[resultado(exit=None, motivo="hook inactivo: tool_result de Bash sin hook_response", matado=True)])
    g = goal_activo(home, tmp_path)
    it = f.runner(g["id"]).iteracion()
    assert it["estado"] == goals.FAILED and "hook inactivo" in goals.load(None, g["id"])["motivo_cierre"]
    assert goals.activo() is None


def test_sonda_del_hook_que_falla_es_failed_sin_invocar(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo")])
    f.sondear = lambda ruta: (False, "el hook dejo pasar gh pr create (exit 0)")
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    it = r.iteracion()
    assert it["estado"] == goals.FAILED and f.llamadas["manos"] == []
    assert "hook inactivo" in goals.load(None, g["id"])["motivo_cierre"]


def test_clon_que_falla_es_failed(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo")])
    f.clonar = lambda goal: {"ok": False, "clon": None, "rama": "x", "error": "no es un repo"}
    g = goal_activo(home, tmp_path)
    assert f.runner(g["id"]).iteracion()["estado"] == goals.FAILED


def test_manos_que_revientan_es_failed_no_tumba_nada(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo")])

    def manos(*a, **k):
        raise RuntimeError("se rompio todo")
    f.manos = manos
    g = goal_activo(home, tmp_path)
    it = f.runner(g["id"]).iteracion()
    assert it["estado"] == goals.FAILED and "se rompio todo" in goals.load(None, g["id"])["motivo_cierre"]


def test_parar_durante_el_golpe_no_juzga_ni_transiciona(home, tmp_path):
    """/goal parar y el apagado ponen `cancelar` y matan el CLI; si el sondeo
    de golpear vio el proceso muerto antes que `cancelar` (motivo None), el
    runner igual corta: la fila dice cancelado y no cuenta para el tope, no
    se llama al juez ni se transiciona (parar/apagar lo hacen; sin eso, con
    un tope chico, tope/no_convergencia corrian contra 'parado por Pedro'
    y uno de los dos reventaba con waiting -> waiting)."""
    f = Falsas(resultados=[resultado("terminar")],
               juicios=[{"cumplido": True, "falta": [], "nota": "", "revisor": "codex"}])
    g = goal_activo(home, tmp_path, tope={"golpes": 1, "minutos": 60, "unidades": 60})
    r = f.runner(g["id"])
    manos_base = f.manos

    def manos_con_veredicto(goal, n, prompt, contrato, cancelar):
        res = manos_base(goal, n, prompt, contrato, cancelar)
        cancelar.set()                       # parar llego justo cuando el CLI terminaba
        return res
    r.manos = manos_con_veredicto
    it = r.iteracion()
    assert it["accion"] == "golpe" and it["motivo"] == "cancelado" and it["estado"] == goals.ACTIVE
    assert f.llamadas["juez"] == [] and goals.load(None, g["id"])["status"] == goals.ACTIVE
    fila = filas(g["id"])[0]
    assert fila["motivo"] == "cancelado" and fila["cuenta_para_tope"] is False and fila["unidades"] == 2
    # parar transiciona sin carrera; segui y otro golpe matado (exit -15, motivo None)
    goals.transicionar(g["id"], goals.WAITING, "parado por Pedro")
    goals.transicionar(g["id"], goals.ACTIVE, "segui")
    r2 = f.runner(g["id"])

    def manos_matadas(goal, n, prompt, contrato, cancelar):
        manos_base(goal, n, prompt, contrato, cancelar)
        cancelar.set()
        return gm.Resultado(exit=-15, motivo=None, session_id="s-1", unidades=1, duracion_ms=10)
    r2.manos = manos_matadas
    it = r2.iteracion()
    assert it["motivo"] == "cancelado" and goals.load(None, g["id"])["status"] == goals.ACTIVE
    assert filas(g["id"])[1]["motivo"] == "cancelado" and filas(g["id"])[1]["exit"] == -15
    assert goals.consumo(goals.load(None, g["id"])) == {"golpes": 0, "minutos": 0.03, "unidades": 3, "mm": 0}
    # con cancelar puesto antes del golpe no se abre fila ni se invoca nada
    r3 = f.runner(g["id"])
    r3.cancelar.set()
    it = r3.iteracion()
    assert it["motivo"] == "cancelado" and len(filas(g["id"])) == 2 and len(f.llamadas["manos"]) == 2


def test_parar_goal_mientras_corre_el_golpe_deja_parado_por_pedro(home, tmp_path):
    """La carrera del ultimo golpe por el camino del server: manos que
    esperan `cancelar` (el CLI matado por parar) y vuelven con motivo None;
    _parar_goal espera el golpe y transiciona; el runner (tope de 1 golpe)
    no transiciona ni revienta, y la espera queda con el motivo de Pedro."""
    g = goal_activo(home, tmp_path, tope={"golpes": 1, "minutos": 60, "unidades": 60})
    f = Falsas(resultados=[resultado("sigo")])
    r = f.runner(g["id"])
    manos_base = f.manos

    def manos(goal, n, prompt, contrato, cancelar):
        manos_base(goal, n, prompt, contrato, cancelar)
        cancelar.wait(10)
        return gm.Resultado(exit=-15, session_id="s-1", unidades=1, duracion_ms=10)
    r.manos = manos
    srv._GOALS_EN_CURSO[g["id"]] = {"tarea": None, "runner": r}
    salida = {}
    hilo = threading.Thread(target=lambda: salida.update(r.iteracion()))
    hilo.start()
    limite = time.monotonic() + 5
    while r.sin_golpe.is_set() and time.monotonic() < limite:
        time.sleep(0.02)
    assert not r.sin_golpe.is_set()                            # el golpe esta corriendo
    goal = srv._parar_goal(g["id"])
    hilo.join(timeout=10)
    assert not hilo.is_alive() and salida["motivo"] == "cancelado"
    assert goal["status"] == goals.WAITING and goal["espera"]["motivo"] == "parado por Pedro"
    assert goals.load(None, g["id"])["espera"]["motivo"] == "parado por Pedro"
    assert filas(g["id"])[0]["motivo"] == "cancelado" and srv._GOALS_EN_CURSO == {}


def test_otro_goal_en_curso_no_muere_en_silencio(home, tmp_path):
    """Invariante 8 con un goal waiting: el dale del inbox sobre otro goal no
    pisa al que espera; el segundo queda con su espera `otro goal activo`,
    un evento `error` y telemetria; el primero no pierde su solicitud."""
    f = Falsas(resultados=[resultado("preguntar", "necesito saber", pregunta="a o b?")])
    a = goal_activo(home, tmp_path)
    assert f.runner(a["id"]).iteracion()["estado"] == goals.WAITING
    b = goals.crear("y", proyecto=None, tope={"golpes": 2})
    goal_b = goals.load(None, b["id"])
    goal_b["espera"] = {"motivo": "dale", "solicitud": "sol_b"}
    goals.escribir(goal_b)
    f.solicitudes["sol_b"] = "aprobada"
    rb = f.runner(b["id"])
    it = rb.iteracion()
    assert it["accion"] == "esperando" and it["estado"] == goals.PROPOSED and "en curso" in it["error"]
    gb = goals.load(None, b["id"])
    assert gb["espera"]["motivo"] == "otro goal activo" and gb["espera"]["solicitud"] is None
    assert [e for e in goals.events(None, b["id"]) if e["action"] == "error"]
    tele = [json.loads(l) for l in (home / "telemetry.jsonl").read_text().splitlines()]
    assert any(x["kind"] == "goal" and x.get("accion") == "error" and x.get("goal_id") == b["id"] for x in tele)
    ga = goals.load(None, a["id"])
    assert goals.activo()["id"] == a["id"] and ga["espera"]["solicitud"] == "sol_1"
    assert rb.iteracion()["accion"] == "nada"                     # proposed sin solicitud: el bucle termina
    # con `a` cerrado, b arranca como siempre (el dale del chat)
    goals.transicionar(a["id"], goals.CANCELLED, "no")
    assert goals.transicionar(b["id"], goals.ACTIVE, "dale")["status"] == goals.ACTIVE


def test_las_compuertas_usadas_van_a_la_fila_y_a_la_aduana_con_deshacer(home, tmp_path):
    """Spec 7/8 y ruling 15.14: las decisiones del hook (hook.jsonl) durante
    el golpe entran a la fila `fin` y a la carga del cruce, con la linea de
    deshacer de cada instalacion; las de un comando simple (sin familia) y
    las de golpes anteriores no."""
    f = Falsas(resultados=[resultado("sigo")])
    g = goal_activo(home, tmp_path)
    registro = goals.dir_goal(g["id"]) / "hook.jsonl"
    registro.write_text(json.dumps({"ts": "x", "tool": "Bash", "decision": "allow", "familia": "instalar_en_goal",
                                    "motivo": "viejo", "forma": {"argv": ["pip", "install", "viejo"]},
                                    "resumen": "pip install viejo"}) + "\n", encoding="utf-8")
    manos_base = f.manos

    def manos(goal, n, prompt, contrato, cancelar):
        with open(registro, "a", encoding="utf-8") as fh:
            for fila in (
                {"ts": "y", "tool": "Bash", "decision": "allow", "familia": "instalar_en_goal",
                 "motivo": "pip en el venv del clon", "forma": {"argv": [".venv/bin/pip", "install", "requests"]},
                 "resumen": ".venv/bin/pip install requests"},
                {"ts": "y", "tool": "Bash", "decision": "deny", "familia": "instalar_home",
                 "motivo": "npm -g: fuera del goal", "forma": {"argv": ["npm", "install", "-g", "typescript"]},
                 "resumen": "npm install -g typescript"},
                {"ts": "y", "tool": "Bash", "decision": "allow", "familia": None, "motivo": "comando simple",
                 "forma": None, "resumen": "pytest -q"},
            ):
                fh.write(json.dumps(fila) + "\n")
        return manos_base(goal, n, prompt, contrato, cancelar)
    f.manos = manos
    r = f.runner(g["id"])
    assert r.iteracion()["accion"] == "golpe"
    usadas = filas(g["id"])[0]["compuertas_usadas"]
    assert [u["familia"] for u in usadas] == ["instalar_en_goal", "instalar_home"]
    assert usadas[0]["deshacer"] == ".venv/bin/pip uninstall -y requests" and usadas[0]["decision"] == "allow"
    assert usadas[1]["deshacer"] == "npm uninstall -g typescript" and usadas[1]["decision"] == "deny"
    fin = [a for a in f.llamadas["aduana"] if a["fase"] == "fin"][0]
    assert fin["compuertas"] == usadas and fin["dominios"] == []


def test_linea_de_deshacer_es_pura():
    d = gr.linea_de_deshacer
    assert d("instalar_en_goal", {"argv": ["pip", "install", "a", "b"]}) == "pip uninstall -y a b"
    assert d("instalar_home", {"argv": ["pip", "install", "--user", "x"]}) == "pip uninstall -y x"
    assert d("instalar_en_goal", {"argv": ["python", "-m", "pip", "install", "x"]}) == "python -m pip uninstall -y x"
    assert d("instalar_en_goal", {"argv": ["npm", "i", "left-pad"]}) == "npm uninstall left-pad"
    assert d("instalar_home", {"argv": ["yarn", "global", "add", "x"]}) == "yarn global remove x"
    assert d("instalar_home", {"argv": ["flatpak", "install", "--user", "flathub", "org.x.Y"]}) == "flatpak uninstall --user org.x.Y"
    assert d("instalar_sistema", {"argv": ["rpm-ostree", "install", "htop"]}) == "rpm-ostree uninstall htop"
    assert d("instalar_en_goal", {"argv": ["pip", "install", "-r", "req.txt"]}) is None
    assert d("web", {"urls": ["https://x"]}) is None and d(None, None) is None


def test_goal_sin_repo_corre_en_trabajo(home, tmp_path):
    f = Falsas(resultados=[resultado("sigo")])
    g = goals.crear("busca precios", proyecto=None, tope={"golpes": 2})
    goals.transicionar(g["id"], goals.ACTIVE, "dale")
    r = f.runner(g["id"])
    assert r.iteracion()["accion"] == "golpe"
    assert f.llamadas["clonar"] == 0 and goals.load(None, g["id"])["repo"] is None
    assert (goals.dir_trabajo(g["id"]) / "trabajo").is_dir()
    c = json.loads((goals.dir_goal(g["id"]) / "compuertas.json").read_text())
    assert c["cwd"] == str(goals.dir_trabajo(g["id"]) / "trabajo") and c["clon"] is None


def test_el_diff_se_mide_contra_la_base_de_la_rama_no_contra_head(home, tmp_path):
    """El contrato manda commitear al cerrar cada golpe: el diff (stat y
    completo) se mide contra el `base_sha` que el clon guardo en goal.json,
    asi un commit cuenta como diff nuevo, el revisor ve el trabajo acumulado
    y tres golpes que commitean no son 'sin diff nuevo'. Clon y diff
    REALES (sin inyectar)."""
    f = Falsas(resultados=[resultado("sigo")])
    g = goal_activo(home, tmp_path)
    r = gr.Runner(g["id"], juez=f.juez, carga_fn=f.carga, consumo_fn=f.consumo, pagador_fn=f.pagador,
                  preguntar=f.preguntar, evaluar_solicitud=f.evaluar, sondear=f.sondear,
                  correr_criterio=f.criterio, aduana_fn=f.aduana)
    manos_base = f.manos

    def manos(goal, n, prompt, contrato, cancelar):
        clon = goal["repo"]
        (pathlib.Path(clon) / f"paso{n}.py").write_text(f"x = {n}\n", encoding="utf-8")
        subprocess.run(["git", "-C", clon, "add", "-A"], check=True)
        subprocess.run(["git", "-C", clon, "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-q", "-m", f"golpe {n}"], check=True)
        return manos_base(goal, n, prompt, contrato, cancelar)
    r.manos = manos
    for _ in (1, 2, 3):
        it = r.iteracion()
        assert it["accion"] == "golpe" and it["estado"] == goals.ACTIVE, it
    goal = goals.load(None, g["id"])
    base = subprocess.run(["git", "-C", goal["proyecto"], "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()
    assert goal["base_sha"] == base and len(base) == 40
    fl = filas(g["id"])
    assert "paso1.py" in fl[0]["diff_stat"] and "paso1.py" in fl[2]["diff_stat"] and "paso3.py" in fl[2]["diff_stat"]
    assert len({fl[0]["diff_stat"], fl[1]["diff_stat"], fl[2]["diff_stat"]}) == 3
    completo = r.diff_completo_fn(goal)
    assert "diff --git" in completo and "+x = 1" in completo and "+x = 3" in completo
    assert gr.no_converge(fl) is None


# --- las manos reales sobre el CLI falso ---------------------------------------------------------

def test_manos_con_cli_arma_el_golpe_entero(home, tmp_path, cli_falso_stream, monkeypatch):
    cli = cli_falso_stream
    g = goal_activo(home, tmp_path, dominios=["pypi.org"])
    sid = g["session_id"]            # el CLI reporta el --session-id que le dimos; la fila lo guarda
    cli.guion([{"lineas": lineas_golpe(session_id=sid, comandos=[("pytest -q", "1 passed")],
                                       veredicto={"estado": "sigo", "resumen": "hice"})},
               {"lineas": lineas_golpe(session_id=sid, veredicto={"estado": "terminar", "resumen": "listo"})}])
    f = Falsas(juicios=[])
    f.manos = gr.manos_con_cli({"claude": cli.ruta, "codex": cli.ruta_codex}, timeout_s=30, usar_systemd=False)
    r = f.runner(g["id"])
    assert r.iteracion()["accion"] == "golpe"
    ll = cli.llamadas()[0]
    a = ll["argv"]
    assert a[a.index("--session-id") + 1] == g["session_id"] and "--resume" not in a
    assert a[a.index("--tools") + 1].endswith("WebSearch,WebFetch")          # el goal declaro dominios
    assert ll["settings"]["sandbox"]["network"]["allowedDomains"] == ["api.anthropic.com", "pypi.org"]
    assert ll["settings"]["hooks"]["PreToolUse"][0]["hooks"][0]["args"][0] == str(gm.HOOK_PATH)
    assert ll["env"]["CALIPSO_GOAL_COMPUERTAS"] == str(goals.dir_goal(g["id"]) / "compuertas.json")
    assert ll["env"]["CALIPSO_HOME"] == str(goals.dir_goal(g["id"]) / "home_vacio")
    assert ll["cwd"] == goals.load(None, g["id"])["repo"]
    assert "crea saludo.py" in ll["stdin"] and "CONTRATO DEL GOAL" in ll["contrato"]
    assert filas(g["id"])[0]["session_id"] == sid and filas(g["id"])[0]["unidades"] == 2
    assert filas(g["id"])[0]["comandos"][0]["cmd"] == "pytest -q"
    r.iteracion()
    a2 = cli.llamadas()[1]["argv"]
    assert a2[a2.index("--resume") + 1] == g["session_id"] and "--session-id" not in a2


def test_cambiar_de_manos_a_claude_arranca_la_sesion_y_no_resume_una_que_no_existe(home, tmp_path,
                                                                                    cli_falso_stream):
    """`--resume` solo si el ledger tiene una fila de claude con la sesion
    del goal: tras golpes con codex (`/goal segui con: claude`), o tras un
    golpe de claude cortado antes de que el CLI persistiera la sesion (sin
    session_id en la fila), el golpe arranca con --session-id; recien con
    una fila de claude con esa sesion, --resume."""
    cli = cli_falso_stream
    g = goal_activo(home, tmp_path, manos="codex")
    sid = g["session_id"]
    cli.guion([{"salida_codex": {"estado": "sigo", "resumen": "hice"}, "lineas": []},
               {"lineas": [], "exit": 1, "stderr": "boom"},                       # claude cortado: sin sesion
               {"lineas": lineas_golpe(session_id=sid, veredicto={"estado": "sigo", "resumen": "x"})},
               {"lineas": lineas_golpe(session_id=sid, veredicto={"estado": "sigo", "resumen": "y"})}])
    f = Falsas(juicios=[])
    f.manos = gr.manos_con_cli({"claude": cli.ruta, "codex": cli.ruta_codex}, timeout_s=30, usar_systemd=False)
    r = f.runner(g["id"])
    f.diff_valor = "a"
    assert r.iteracion()["accion"] == "golpe" and filas(g["id"])[0]["manos"] == "codex"
    goal = goals.load(None, g["id"])
    goal["manos"] = "claude"                                   # lo que hace /goal segui con: claude
    goals.escribir(goal)
    f.diff_valor = "b"
    assert r.iteracion()["accion"] == "golpe"
    a2 = cli.llamadas()[1]["argv"]
    assert a2[a2.index("--session-id") + 1] == sid and "--resume" not in a2
    assert filas(g["id"])[1]["manos"] == "claude" and filas(g["id"])[1]["session_id"] is None
    f.diff_valor = "c"
    assert r.iteracion()["accion"] == "golpe"
    a3 = cli.llamadas()[2]["argv"]
    assert a3[a3.index("--session-id") + 1] == sid and "--resume" not in a3    # todavia sin sesion de claude
    assert filas(g["id"])[2]["session_id"] == sid
    f.diff_valor = "d"
    assert r.iteracion()["accion"] == "golpe"
    a4 = cli.llamadas()[3]["argv"]
    assert a4[a4.index("--resume") + 1] == sid and "--session-id" not in a4


def test_correccion_de_sesion_es_pura():
    """La eleccion --session-id / --resume se autocorrige por lo que dice
    el CLI, no por adivinar del ledger: `Session ID x is already in use`
    (la sesion SI existe) -> --resume; `No conversation found with session
    ID` -> --session-id; un solo sentido por vez; nada con exit 0, matado
    (timeout, parar) o `cancelar` puesto; el texto puede venir por stdout."""
    en_uso = gm.Resultado(exit=1, stderr_tail="Error: Session ID abc is already in use.\n")
    no_hay = gm.Resultado(exit=1, stderr_tail="No conversation found with session ID: abc\n")
    assert gr.correccion_de_sesion(en_uso, resume=False) is True
    assert gr.correccion_de_sesion(no_hay, resume=True) is False
    assert gr.correccion_de_sesion(en_uso, resume=True) is None          # ya era --resume: nada que corregir
    assert gr.correccion_de_sesion(no_hay, resume=False) is None
    assert gr.correccion_de_sesion(gm.Resultado(exit=0, stderr_tail=en_uso.stderr_tail), resume=False) is None
    assert gr.correccion_de_sesion(gm.Resultado(exit=1, matado=True, stderr_tail=en_uso.stderr_tail),
                                   resume=False) is None
    assert gr.correccion_de_sesion(gm.Resultado(exit=1, stderr_tail="boom"), resume=False) is None
    puesto = threading.Event()
    puesto.set()
    assert gr.correccion_de_sesion(en_uso, resume=False, cancelar=puesto) is None
    assert gr.correccion_de_sesion(gm.Resultado(exit=1, stdout_tail="Session ID x is already in use."),
                                   resume=False) is True
    assert gr.REINTENTOS_DE_SESION == {True: "--session-id en uso -> --resume",
                                       False: "sesion no encontrada -> --session-id"}


def test_session_id_en_uso_relanza_con_resume_sin_fila_extra(home, tmp_path, cli_falso_stream):
    """El server murio durante el golpe 1 de claude y la reconciliacion
    cerro la fila SIN session_id (un ledger anterior a este fix): el ledger
    dice --session-id, pero el CLI SI persistio la sesion y aborta con
    `Session ID x is already in use` (exit 1 antes de la API: no gasta
    cuota). Las manos se corrigen solas: relanzan el MISMO golpe con
    --resume, sin fila extra, y la fila dice el reintento."""
    cli = cli_falso_stream
    g = goal_activo(home, tmp_path)
    sid = g["session_id"]
    goals.golpe_inicio(g["id"], 1, manos="claude", paso="x")
    goals.golpe_fin(g["id"], 1, motivo="cortado por el reinicio", unidades=0, duracion_ms=0)
    cli.guion([{"lineas": [], "exit": 1, "stderr": f"Error: Session ID {sid} is already in use.\n"},
               {"lineas": lineas_golpe(session_id=sid, veredicto={"estado": "sigo", "resumen": "segui"})}])
    f = Falsas(juicios=[])
    f.manos = gr.manos_con_cli({"claude": cli.ruta, "codex": cli.ruta_codex}, timeout_s=30, usar_systemd=False)
    r = f.runner(g["id"])
    f.diff_valor = "a"
    assert r.iteracion()["accion"] == "golpe"
    ll = cli.llamadas()
    assert len(ll) == 2
    a1, a2 = ll[0]["argv"], ll[1]["argv"]
    assert a1[a1.index("--session-id") + 1] == sid and "--resume" not in a1
    assert a2[a2.index("--resume") + 1] == sid and "--session-id" not in a2
    assert ll[1]["stdin"] == ll[0]["stdin"] and ll[1]["contrato"] == ll[0]["contrato"]   # el mismo golpe
    fl = filas(g["id"])
    assert [x["n"] for x in fl] == [1, 2]                                            # sin fila extra
    assert fl[1]["session_id"] == sid and fl[1]["exit"] == 0 and fl[1]["unidades"] == 2
    assert fl[1]["veredicto_del_golpe"] == {"estado": "sigo", "resumen": "segui"}
    assert fl[1]["reintento"] == "--session-id en uso -> --resume" and fl[1]["cuenta_para_tope"] is True
    # el golpe siguiente ya resume derecho, sin reintento
    f.diff_valor = "b"
    assert r.iteracion()["accion"] == "golpe"
    ll = cli.llamadas()
    a3 = ll[2]["argv"]
    assert len(ll) == 3 and a3[a3.index("--resume") + 1] == sid and "--session-id" not in a3
    assert filas(g["id"])[2]["reintento"] is None


def test_resume_de_una_sesion_inexistente_relanza_con_session_id(home, tmp_path, cli_falso_stream):
    """El simetrico: el ledger tiene una fila de claude con la sesion
    (--resume), pero el CLI no la encuentra (`No conversation found with
    session ID`: no la persistio, o se borro): se relanza el mismo golpe
    con --session-id (sesion nueva; el prompt lleva el resumen del ledger,
    el martillo no arranca de cero)."""
    cli = cli_falso_stream
    g = goal_activo(home, tmp_path)
    sid = g["session_id"]
    cli.guion([{"lineas": lineas_golpe(session_id=sid, veredicto={"estado": "sigo", "resumen": "uno"})},
               {"lineas": [], "exit": 1, "stderr": f"No conversation found with session ID: {sid}\n"},
               {"lineas": lineas_golpe(session_id=sid, veredicto={"estado": "sigo", "resumen": "dos"})}])
    f = Falsas(juicios=[])
    f.manos = gr.manos_con_cli({"claude": cli.ruta, "codex": cli.ruta_codex}, timeout_s=30, usar_systemd=False)
    r = f.runner(g["id"])
    f.diff_valor = "a"
    assert r.iteracion()["accion"] == "golpe"
    f.diff_valor = "b"
    assert r.iteracion()["accion"] == "golpe"
    ll = cli.llamadas()
    assert len(ll) == 3
    a2, a3 = ll[1]["argv"], ll[2]["argv"]
    assert a2[a2.index("--resume") + 1] == sid and "--session-id" not in a2
    assert a3[a3.index("--session-id") + 1] == sid and "--resume" not in a3
    fl = filas(g["id"])
    assert [x["n"] for x in fl] == [1, 2] and fl[1]["session_id"] == sid and fl[1]["exit"] == 0
    assert fl[1]["veredicto_del_golpe"] == {"estado": "sigo", "resumen": "dos"}
    assert fl[1]["reintento"] == "sesion no encontrada -> --session-id"


def test_el_reintento_de_sesion_es_uno_solo(home, tmp_path, cli_falso_stream):
    """Dos correcciones contradictorias (en uso -> --resume -> no
    encontrada) no forman un bucle: UN reintento por golpe; la fila queda
    con el fallo del reintento y sin sesion (el golpe siguiente vuelve a
    elegir por el ledger y a corregirse si hace falta)."""
    cli = cli_falso_stream
    g = goal_activo(home, tmp_path)
    sid = g["session_id"]
    cli.guion([{"lineas": [], "exit": 1, "stderr": f"Error: Session ID {sid} is already in use.\n"},
               {"lineas": [], "exit": 1, "stderr": f"No conversation found with session ID: {sid}\n"},
               {"lineas": [], "exit": 1, "stderr": f"Error: Session ID {sid} is already in use.\n"}])
    f = Falsas(juicios=[])
    f.manos = gr.manos_con_cli({"claude": cli.ruta, "codex": cli.ruta_codex}, timeout_s=30, usar_systemd=False)
    r = f.runner(g["id"])
    assert r.iteracion()["accion"] == "golpe"
    ll = cli.llamadas()
    assert len(ll) == 2 and "--session-id" in ll[0]["argv"] and "--resume" in ll[1]["argv"]
    fl = filas(g["id"])
    assert len(fl) == 1 and fl[0]["exit"] == 1 and fl[0]["session_id"] is None
    assert "No conversation found" in fl[0]["stderr_tail"]
    assert fl[0]["reintento"] == "--session-id en uso -> --resume" and fl[0]["cuenta_para_tope"] is True


def test_manos_con_cli_codex(home, tmp_path, cli_falso_stream):
    cli = cli_falso_stream
    # codex en modo estricto devuelve TODAS las claves (las opcionales en null)
    cli.guion([{"salida_codex": {"estado": "sigo", "resumen": "hice", "pregunta": None, "compuerta": None},
                "lineas": []}])
    f = Falsas(juicios=[])
    f.manos = gr.manos_con_cli({"claude": cli.ruta, "codex": cli.ruta_codex}, timeout_s=30, usar_systemd=False)
    g = goal_activo(home, tmp_path, manos="codex")
    r = f.runner(g["id"])
    assert r.iteracion()["accion"] == "golpe"
    a = cli.llamadas()[0]["argv"]
    assert a[0] == "exec" and a[a.index("-s") + 1] == "workspace-write"   # el falso anota sys.argv[1:]
    assert filas(g["id"])[0]["veredicto_del_golpe"] == {"estado": "sigo", "resumen": "hice"}
    # el esquema que recibe codex es el estricto (smoke corrida 3: invalid_json_schema sin esto)
    esquema = json.loads((goals.dir_goal(g["id"]) / "esquema-veredicto.json").read_text(encoding="utf-8"))
    assert esquema["additionalProperties"] is False and esquema["required"] == list(esquema["properties"])


def test_manos_con_cli_publica_el_handle_en_el_runner(home, tmp_path, cli_falso_stream):
    """Decision 17: el Popen del golpe vive en runner.golpe_en_curso mientras
    corre (`al_lanzar=runner.registrar_golpe`), `sin_golpe` esta apagado, y
    cancelar + matar_golpe lo cortan; al volver, el handle se limpia."""
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_golpe()[:1], "dormir": 30}])
    f = Falsas(juicios=[])
    g = goal_activo(home, tmp_path)
    r = f.runner(g["id"])
    r.manos = gr.manos_con_cli({"claude": cli.ruta, "codex": cli.ruta_codex}, timeout_s=30,
                               usar_systemd=False, al_lanzar=r.registrar_golpe)
    salida = {}
    hilo = threading.Thread(target=lambda: salida.update(r.iteracion()))
    hilo.start()
    limite = time.monotonic() + 10
    while r.golpe_en_curso is None and time.monotonic() < limite:
        time.sleep(0.05)
    assert r.golpe_en_curso is not None and r.golpe_en_curso.poll() is None
    assert r.esperar_golpe(0.1) is False                          # hay un golpe en curso
    r.cancelar.set()
    r.matar_golpe()
    hilo.join(timeout=15)
    assert not hilo.is_alive() and r.golpe_en_curso is None and r.esperar_golpe(0) is True
    assert salida["accion"] == "golpe" and filas(g["id"])[0]["fase"] == "fin"


# --- la aduana con origen goal y el Pagador con unidades --------------------------------------------

def test_quien_con_origen_goal():
    q = aduana.Quien(origen="goal", proyecto="proyecto", desde={"credencial": "maquina"},
                     gesto="/goal", rutina={"kind": "goal", "id": "goal_abc"})
    assert q.origen == "goal" and q.rutina == {"kind": "goal", "id": "goal_abc"}
    assert "goal" in aduana.ORIGENES


def test_aduana_del_goal_escribe_el_cruce_con_el_proyecto_del_goal(home, tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "ROOT", tmp_path / "otro-root")
    g = goal_activo(home, tmp_path)
    goal = goals.load(None, g["id"])
    srv._aduana_del_goal(goal, 1, "inicio", manos="claude")
    srv._aduana_del_goal(goal, 1, "fin", comandos=["ls"], bytes_entrados=120, dominios=["pypi.org"],
                         compuertas=[{"familia": "instalar_en_goal", "decision": "allow",
                                      "resumen": "pip install requests", "deshacer": "pip uninstall -y requests"}])
    libro = home / "aduana.jsonl"
    filas_ad = [json.loads(l) for l in libro.read_text().splitlines()]
    assert len(filas_ad) == 2
    assert filas_ad[0]["quien"]["origen"] == "goal" and filas_ad[0]["quien"]["proyecto"] == "proyecto"
    assert filas_ad[0]["quien"]["rutina"] == {"kind": "goal", "id": g["id"]}
    assert filas_ad[0]["declarado"] is True and filas_ad[1]["resultado"]["estado"] == "ok"
    assert filas_ad[1]["destino"] == {"host": None, "url": None}
    carga = filas_ad[1]["carga"]["texto"]                         # spec 8: dominios y la linea de deshacer
    assert "dominios: pypi.org" in carga and "uninstall" in carga and "instalar_en_goal" in carga


@pytest.fixture
def economia(home, monkeypatch):
    """Molde `base` de test_economia_pagador.py: un departamento de fabrica
    (`a`, cuya cuenta e id de foco es `dep:a`: `_cuenta_en_foco` valida el
    id contra `_edificios_livianos`, que lista `d.cuenta`), la suscripcion
    claude_max y el ciclo emitido (el pool de cristal existe: sin
    `pt.emitir_semana` la unidad queda en descubierto)."""
    from calipso.economia import pt
    eco = home / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA, techo_api_ciclo_mm=500_000))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    pt.emitir_semana(k, "2026-09-13T09:00:00", "2026-W37", 4_000, 0)
    k.acunar("2026-09-13T09:00:00", "2026-W37", "dep:a", 100_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", home)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: ("2026-09-13T10:00:00", "2026-W37"))
    return eco


def test_cobrar_golpe_con_unidades_reales_y_ref(home, tmp_path, economia):
    from calipso.economia import capacidad as cap
    from calipso.economia import pagador as pag
    g = goal_activo(home, tmp_path, departamento="dep:a")     # el id del departamento es su cuenta (dep:a)
    cobro = srv._cobrar_golpe(goals.load(None, g["id"]), 17, "claude")
    assert cobro["unidades"] == 17 and cobro["cobrado"] is True and cobro["ref"] == f"goal:{g['id']}"
    assert cobro["cuenta"] == "dep:a"
    p = pag.Pagador.desde_entorno(home)
    assert p.pendientes() == []
    asientos = p.leer_kernel().libro.asientos()
    assert cap.consumo_fabrica(asientos, "claude_max", ["2026-W37"]) == 17    # 17 unidades, no 1
    consumo = [a for a in asientos if a.tipo is t.TipoAsiento.CONSUMO_CRISTAL][0]
    assert consumo.detalle["titular"] == "dep:a"
    assert consumo.ref == f"goal:{g['id']}"                                   # el concepto (tipos.Asiento.ref)
    # sin departamento (cuenta personal) no se debita y se dice
    g2 = goals.crear("y", proyecto=None, tope={"golpes": 1})
    cobro = srv._cobrar_golpe(goals.load(None, g2["id"]), 3, "codex")
    assert cobro["cobrado"] is False and cobro["unidades"] == 3


# --- el apagado y el arranque --------------------------------------------------------------------

def test_apagar_goals_mata_el_proceso_y_deja_waiting(home, tmp_path, monkeypatch):
    import asyncio
    g = goal_activo(home, tmp_path)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"], start_new_session=True)
    f = Falsas(resultados=[resultado("sigo")])
    runner = f.runner(g["id"])
    runner.golpe_en_curso = proc
    goals.golpe_inicio(g["id"], 1, manos="claude", paso="x")

    async def _corre():
        async def _bucle():
            await asyncio.sleep(3600)
        tarea = asyncio.create_task(_bucle())
        srv._GOALS_EN_CURSO[g["id"]] = {"tarea": tarea, "runner": runner}
        t0 = time.monotonic()
        await srv._apagar_goals()
        return time.monotonic() - t0
    dur = asyncio.run(_corre())
    assert dur < 10 and proc.poll() is not None
    assert runner.cancelar.is_set()
    g2 = goals.load(None, g["id"])
    assert g2["status"] == goals.WAITING and g2["espera"]["motivo"] == "server apagado"
    assert srv._GOALS_EN_CURSO == {}


def test_reconciliar_goals_al_arrancar(home, tmp_path, monkeypatch):
    g = goal_activo(home, tmp_path)
    goal = goals.load(None, g["id"])
    clon = goals.dir_trabajo(g["id"]) / "repo"
    subprocess.run(["git", "clone", "-q", goal["proyecto"], str(clon)], check=True)
    goal["repo"] = str(clon)
    goals.escribir(goal)
    (clon / "sucio.py").write_text("x", encoding="utf-8")
    goals.golpe_inicio(g["id"], 1, manos="claude", paso="x")   # un golpe cortado (sin fin)
    lanzados = []
    monkeypatch.setattr(srv, "_lanzar_bucle", lambda gid: lanzados.append(gid))
    ids = srv._reconciliar_goals()
    assert ids == [g["id"]]
    g2 = goals.load(None, g["id"])
    assert g2["status"] == goals.WAITING and g2["espera"]["motivo"] == "server reiniciado"
    assert "sucio.py" in g2["espera"]["git_status"]
    fl = filas(g["id"])
    assert fl[0]["fase"] == "fin" and fl[0]["motivo"] == "cortado por el reinicio"
    assert fl[0]["session_id"] == g["session_id"]        # el golpe de claude corrio: la sesion existe
    evs = [e for e in goals.events(None, g["id"]) if e["action"] == "reconciliado"]
    assert evs and lanzados == [g["id"]]
    # una segunda vez no hace nada: un waiting SIN solicitud no se relanza
    # (el bucle no tendria nada que sondear; lo relanza /goal segui)
    assert srv._reconciliar_goals() == []
    # un waiting CON solicitud (espera una respuesta del inbox) se relanza
    g2 = goals.load(None, g["id"])
    g2["espera"] = {**g2["espera"], "solicitud": "sol_x"}
    goals.escribir(g2)
    assert srv._reconciliar_goals() == [g["id"]] and lanzados == [g["id"], g["id"]]
    # y un proposed con su solicitud `dale` estacionada tambien (el dale del inbox)
    p = goals.crear("y", proyecto=None, tope={"golpes": 2})
    goal_p = goals.load(None, p["id"])
    goal_p["espera"] = {"motivo": "dale", "solicitud": "sol_dale"}
    goals.escribir(goal_p)
    assert set(srv._reconciliar_goals()) == {g["id"], p["id"]}


def test_reconciliar_guarda_la_sesion_de_claude_y_el_segui_resume_derecho(home, tmp_path, cli_falso_stream,
                                                                          monkeypatch):
    """La reconciliacion cierra el golpe cortado CON la sesion del goal si
    las manos eran claude (el golpe corrio: el CLI la persistio) y sin
    sesion si eran codex: tras `/goal segui` el golpe siguiente resume
    derecho, sin gastar un lanzamiento en el `already in use`."""
    cli = cli_falso_stream
    monkeypatch.setattr(srv, "_lanzar_bucle", lambda gid: None)
    g = goal_activo(home, tmp_path, manos="codex")
    sid = g["session_id"]
    goals.golpe_inicio(g["id"], 1, manos="codex", paso="x")
    assert srv._reconciliar_goals() == [g["id"]]
    fl = filas(g["id"])
    assert fl[0]["motivo"] == "cortado por el reinicio" and fl[0].get("session_id") is None
    goal = goals.load(None, g["id"])
    goal["manos"] = "claude"                                   # /goal segui con: claude
    goals.escribir(goal)
    goals.transicionar(g["id"], goals.ACTIVE, "segui")
    goals.golpe_inicio(g["id"], 2, manos="claude", paso="x")   # y el server volvio a morir en el golpe
    assert srv._reconciliar_goals() == [g["id"]]
    fl = filas(g["id"])
    assert fl[1]["motivo"] == "cortado por el reinicio" and fl[1]["session_id"] == sid
    goals.transicionar(g["id"], goals.ACTIVE, "segui")
    cli.guion([{"lineas": lineas_golpe(session_id=sid, veredicto={"estado": "sigo", "resumen": "tres"})}])
    f = Falsas(juicios=[])
    f.manos = gr.manos_con_cli({"claude": cli.ruta, "codex": cli.ruta_codex}, timeout_s=30, usar_systemd=False)
    r = f.runner(g["id"])
    assert r.iteracion()["accion"] == "golpe"
    ll = cli.llamadas()
    a = ll[0]["argv"]
    assert len(ll) == 1 and a[a.index("--resume") + 1] == sid and "--session-id" not in a
    assert filas(g["id"])[2]["session_id"] == sid and filas(g["id"])[2]["reintento"] is None


def test_el_bucle_viejo_no_borra_la_entrada_nueva(home, tmp_path, monkeypatch):
    """Carrera parar + segui: la tarea vieja, al terminar, saca SOLO su
    propia entrada de _GOALS_EN_CURSO; la nueva (otro runner) queda, y la
    cancelacion va por el loop (_cancelar_tarea)."""
    import asyncio
    monkeypatch.setattr(gr, "GOAL_TICK_S", 0.05)
    g = goal_activo(home, tmp_path)
    goals.transicionar(g["id"], goals.WAITING, "parado por Pedro")
    f = Falsas()
    viejo, nuevo = f.runner(g["id"]), f.runner(g["id"])

    async def _corre():
        tarea = asyncio.create_task(srv._bucle_del_goal(g["id"]))
        srv._GOALS_EN_CURSO[g["id"]] = {"tarea": tarea, "runner": viejo}
        await asyncio.sleep(0.2)                                   # ya dio vueltas ('esperando')
        # parar + segui: la entrada se reemplaza mientras la vieja sigue viva
        otra = asyncio.create_task(asyncio.sleep(3600))
        srv._GOALS_EN_CURSO[g["id"]] = {"tarea": otra, "runner": nuevo}
        srv._cancelar_tarea(tarea)
        await asyncio.wait([tarea], timeout=5)
        assert tarea.done()
        e = srv._GOALS_EN_CURSO.get(g["id"])
        otra.cancel()
        return e["runner"] if e else None
    assert asyncio.run(_corre()) is nuevo
    srv._GOALS_EN_CURSO.clear()
