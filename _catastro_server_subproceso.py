#!/usr/bin/env python3
"""
_catastro_server_subproceso.py - el cuerpo real de test_catastro_server.py,
corrido SIEMPRE en un proceso propio.

Por que un proceso aparte y no solo "fijar CALIPSO_HOME antes de importar"
adentro del mismo proceso de pytest: se probo eso primero y no alcanza.
`calipso.server` (y lo que importa: memory.py, jobs.py, chats.py,
goals.py...) fija su `CALIPSO_HOME` -- o el de cada submodulo, cada uno
por separado -- la PRIMERA vez que algo en el proceso hace
`import calipso.server`. Si CUALQUIER otro archivo de la suite de tests ya
hizo ese import antes (con el `~/.calipso` real de la maquina), el modulo
queda cacheado en `sys.modules` con esos valores ya resueltos, y fijar la
variable de entorno despues -- aunque sea antes del `import` de ESTE
archivo -- no cambia nada: Python no vuelve a ejecutar el modulo. La
prueba llego a escribir en el `~/.calipso` real de Pedro por esta via
exacta (confirmado corriendo la suite completa: `~/.calipso/catastro.json`
terminaba pisado por rutas de `/tmp` de los tests).

Un proceso de Python nuevo no tiene ese problema: no hay nada cacheado
todavia, asi que fijar las variables de entorno ANTES de cualquier import
(lo que hace este archivo, arriba de todo) es efectivo siempre, sin
importar el orden de collection de pytest ni que otro archivo haya
importado `calipso.server` antes en el proceso padre.

El resultado se escribe en el archivo pasado como argv[1], nunca en
stdout: huggingface_hub y chromadb escriben avisos y barras de progreso
por su cuenta al importar/usar el modelo de embeddings, y mezclar eso con
el JSON de resultados lo rompe.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

_RESULT_PATH = pathlib.Path(sys.argv[1])

_HOME = tempfile.mkdtemp(prefix="calipso_catastro_srv_home_")
os.environ["CALIPSO_HOME"] = _HOME
_ROOT_DIR = tempfile.mkdtemp(prefix="calipso_catastro_srv_root_")
os.environ["CALIPSO_ROOT"] = _ROOT_DIR


def _git(args: list[str], cwd) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def _repo(path: pathlib.Path) -> pathlib.Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(["init", "-q"], path)
    _git(["config", "user.email", "pedro@example.com"], path)
    _git(["config", "user.name", "Pedro"], path)
    _git(["commit", "-q", "--allow-empty", "-m", "inicial"], path)
    return path


_repo(pathlib.Path(_ROOT_DIR))

# la raiz declarada del catastro tiene que incluir CALIPSO_ROOT (y todo lo
# que este archivo vaya a abrir), o _switch_project rechaza hasta el
# arranque.
_RAIZ = pathlib.Path(tempfile.mkdtemp(prefix="calipso_catastro_srv_raiz_"))
(pathlib.Path(_HOME) / "catastro.json").write_text(json.dumps({
    "raices": [{"ruta": str(_RAIZ), "profundidad": 3},
              {"ruta": str(pathlib.Path(_ROOT_DIR).resolve()), "profundidad": 1}],
    "proyectos": [],
}), encoding="utf-8")

# recien aca, con el entorno ya fijado, los primeros imports de calipso.*
# de todo el proceso.
import calipso.server as srv  # noqa: E402
from calipso import catastro  # noqa: E402
from calipso import routines as calipso_routines  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

cliente = TestClient(srv.app)

resultados: dict[str, bool] = {}
errores: dict[str, str] = {}


def _check(nombre: str, fn) -> None:
    try:
        fn()
        resultados[nombre] = True
    except Exception as exc:  # noqa: BLE001 - se quiere capturar cualquier falla
        resultados[nombre] = False
        errores[nombre] = f"{type(exc).__name__}: {exc}"


def _repo_en_raiz(nombre: str) -> pathlib.Path:
    return _repo(_RAIZ / nombre)


# --- el techo de ROOT vive en _switch_project, no en un solo endpoint -----

def _t_switch_project_dentro_de_una_raiz_declarada_funciona() -> None:
    proyecto = _repo_en_raiz("adentro")
    original = srv.ROOT
    try:
        srv._switch_project(str(proyecto))
        assert srv.ROOT == proyecto.resolve()
    finally:
        srv._switch_project(str(original))


def _t_switch_project_fuera_de_las_raices_da_400_y_no_mueve_root() -> None:
    afuera = pathlib.Path(tempfile.mkdtemp(prefix="calipso_afuera_"))
    original = srv.ROOT
    try:
        srv._switch_project(str(afuera))
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("no rechazo una ruta fuera de las raices")
    assert srv.ROOT == original


def _t_switch_project_la_raiz_no_puede_ser_barra() -> None:
    original = srv.ROOT
    try:
        srv._switch_project("/")
    except Exception as exc:
        assert getattr(exc, "status_code", None) == 400
    else:
        raise AssertionError("no rechazo /")
    assert srv.ROOT == original


def _t_api_project_open_delega_en_switch_project_y_respeta_el_techo() -> None:
    r = cliente.post("/api/project/open", params={"token": srv.TOKEN},
                     json={"path": "/"})
    assert r.status_code == 400
    assert "raices" in r.json()["detail"] or "raiz" in r.json()["detail"]


def _t_api_chats_con_project_path_en_el_body_respeta_el_techo() -> None:
    r = cliente.post("/api/chats", params={"token": srv.TOKEN},
                     json={"project_path": "/"})
    assert r.status_code == 400


def _t_activate_respeta_el_techo() -> None:
    proyecto = _repo_en_raiz("para-activar")
    r = cliente.post("/api/chats", params={"token": srv.TOKEN},
                     json={"project_path": str(proyecto)})
    assert r.status_code == 200
    chat_id = r.json()["id"]

    otra_raiz = pathlib.Path(tempfile.mkdtemp(prefix="calipso_otra_raiz_"))
    original_raices = catastro.raices()
    try:
        catastro._guardar_json({
            "raices": [{"ruta": str(otra_raiz), "profundidad": 1}],
            "proyectos": [],
        })
        r2 = cliente.post(f"/api/chats/{chat_id}/activate",
                          params={"token": srv.TOKEN})
        assert r2.status_code == 400
    finally:
        catastro._guardar_json({"raices": original_raices, "proyectos": []})
        srv._switch_project(str(_ROOT_DIR))


def _t_repo_brief_no_mueve_root_y_describe_otro_proyecto() -> None:
    otro = _repo_en_raiz("otro-proyecto")
    (otro / "README.md").write_text("Otro proyecto\nResumen.\n", encoding="utf-8")
    original = srv.ROOT

    brief = srv._repo_brief(otro)

    assert srv.ROOT == original
    assert "README.md" in brief


def _t_endpoint_catastro_lista() -> None:
    r = cliente.get("/api/catastro", params={"token": srv.TOKEN})
    assert r.status_code == 200
    assert "proyectos" in r.json()


def _t_endpoint_catastro_detalle_404_si_no_existe() -> None:
    r = cliente.get("/api/catastro/no-existe-este-nombre",
                    params={"token": srv.TOKEN})
    assert r.status_code == 404


def _t_endpoint_catastro_detalle_trae_el_brief_sin_mover_root() -> None:
    _repo_en_raiz("con-detalle")
    catastro.cargar(forzar_escaneo=True)
    original = srv.ROOT

    r = cliente.get("/api/catastro/con-detalle", params={"token": srv.TOKEN})

    assert r.status_code == 200
    body = r.json()
    assert body["proyecto"]["nombre"] == "con-detalle"
    assert "brief" in body
    assert srv.ROOT == original


def _t_asegurar_rutina_catastro_agrega_si_falta_y_es_idempotente() -> None:
    for r in calipso_routines.load():
        if r["kind"] == "catastro":
            calipso_routines.remove(r["id"])
    assert not any(r["kind"] == "catastro" for r in calipso_routines.load())

    srv._asegurar_rutina_catastro()
    despues = [r for r in calipso_routines.load() if r["kind"] == "catastro"]
    assert len(despues) == 1
    assert despues[0]["enabled"] is True

    srv._asegurar_rutina_catastro()  # correrlo de nuevo no duplica
    assert len([r for r in calipso_routines.load()
               if r["kind"] == "catastro"]) == 1


_check("switch_project_dentro_de_una_raiz_declarada_funciona",
      _t_switch_project_dentro_de_una_raiz_declarada_funciona)
_check("switch_project_fuera_de_las_raices_da_400_y_no_mueve_root",
      _t_switch_project_fuera_de_las_raices_da_400_y_no_mueve_root)
_check("switch_project_la_raiz_no_puede_ser_barra",
      _t_switch_project_la_raiz_no_puede_ser_barra)
_check("api_project_open_delega_en_switch_project_y_respeta_el_techo",
      _t_api_project_open_delega_en_switch_project_y_respeta_el_techo)
_check("api_chats_con_project_path_en_el_body_respeta_el_techo",
      _t_api_chats_con_project_path_en_el_body_respeta_el_techo)
_check("activate_respeta_el_techo", _t_activate_respeta_el_techo)
_check("repo_brief_no_mueve_root_y_describe_otro_proyecto",
      _t_repo_brief_no_mueve_root_y_describe_otro_proyecto)
_check("endpoint_catastro_lista", _t_endpoint_catastro_lista)
_check("endpoint_catastro_detalle_404_si_no_existe",
      _t_endpoint_catastro_detalle_404_si_no_existe)
_check("endpoint_catastro_detalle_trae_el_brief_sin_mover_root",
      _t_endpoint_catastro_detalle_trae_el_brief_sin_mover_root)
_check("asegurar_rutina_catastro_agrega_si_falta_y_es_idempotente",
      _t_asegurar_rutina_catastro_agrega_si_falta_y_es_idempotente)

_RESULT_PATH.write_text(
    json.dumps({"resultados": resultados, "errores": errores}),
    encoding="utf-8")
