#!/usr/bin/env python3
"""
test_catastro_server.py - integracion del catastro con el servidor: el
techo de ROOT en `_switch_project` (hallazgo S4 del spec de ojos y manos,
"El techo de ROOT va en _switch_project, no en el endpoint de abrir
proyecto"), `_repo_brief` recibiendo la raiz como parametro, y los dos
endpoints GET /api/catastro.

Aisla CALIPSO_HOME y CALIPSO_ROOT en directorios temporales ANTES de
importar calipso.server: el modulo arma ROOT y la memoria hibrida al
importarse, y cada submodulo que toca (memory.py, jobs.py, chats.py,
goals.py...) calcula SU PROPIO CALIPSO_HOME de forma independiente al
importarse (no hay un unico punto de verdad). Aislar despues con
monkeypatch solo alcanza al modulo que se parcha -- se probo, y
`_switch_project`/`POST /api/chats` igual escribian chats y memoria
reales bajo el ~/.calipso real de Pedro por las otras puertas.

Por eso este archivo, igual que test_commands.py y test_routines.py,
corre standalone: `pytest test_catastro_server.py`, nunca junto con otros
archivos que ya hayan importado calipso.server con el entorno real (test_
seguridad_puertas.py, test_economia_brief.py) en la misma sesion de
pytest -- ahi si, aislar despues de importar no sirve de nada.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import tempfile

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
# que este test vaya a abrir), o _switch_project rechaza hasta el arranque.
_RAIZ = pathlib.Path(tempfile.mkdtemp(prefix="calipso_catastro_srv_raiz_"))
(pathlib.Path(_HOME) / "catastro.json").write_text(json.dumps({
    "raices": [{"ruta": str(_RAIZ), "profundidad": 3},
              {"ruta": str(pathlib.Path(_ROOT_DIR).resolve()), "profundidad": 1}],
    "proyectos": [],
}), encoding="utf-8")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import calipso.server as srv  # noqa: E402
from calipso import catastro  # noqa: E402


@pytest.fixture
def cliente():
    return TestClient(srv.app)


def _repo_en_raiz(nombre: str) -> pathlib.Path:
    return _repo(_RAIZ / nombre)


# --- el techo de ROOT vive en _switch_project, no en un solo endpoint -----

def test_switch_project_dentro_de_una_raiz_declarada_funciona():
    proyecto = _repo_en_raiz("adentro")
    original = srv.ROOT
    try:
        srv._switch_project(str(proyecto))
        assert srv.ROOT == proyecto.resolve()
    finally:
        srv._switch_project(str(original))


def test_switch_project_fuera_de_las_raices_da_400_y_no_mueve_root():
    afuera = pathlib.Path(tempfile.mkdtemp(prefix="calipso_afuera_"))
    original = srv.ROOT
    with pytest.raises(Exception) as excinfo:
        srv._switch_project(str(afuera))
    status = getattr(excinfo.value, "status_code", None)
    assert status == 400
    assert srv.ROOT == original


def test_switch_project_la_raiz_no_puede_ser_barra():
    original = srv.ROOT
    with pytest.raises(Exception) as excinfo:
        srv._switch_project("/")
    assert getattr(excinfo.value, "status_code", None) == 400
    assert srv.ROOT == original


def test_api_project_open_delega_en_switch_project_y_respeta_el_techo(cliente):
    """api_project_open (POST /api/project/open) ya no reasigna ROOT por su
    cuenta: llama a _switch_project, y por eso hereda el mismo techo."""
    r = cliente.post("/api/project/open", params={"token": srv.TOKEN},
                     json={"path": "/"})
    assert r.status_code == 400
    assert "raices" in r.json()["detail"] or "raiz" in r.json()["detail"]


def test_api_chats_con_project_path_en_el_body_respeta_el_techo(cliente):
    """La segunda puerta que el spec nombra explicito: un POST /api/chats
    con project_path en el body no puede envenenar ROOT con una ruta
    fuera de las raices declaradas -- eso sobreviviria al reinicio via
    chats.json."""
    r = cliente.post("/api/chats", params={"token": srv.TOKEN},
                     json={"project_path": "/"})
    assert r.status_code == 400


def test_activate_respeta_el_techo(cliente):
    """La tercera puerta: activar un chat cuyo project_path haya quedado
    fuera de las raices declaradas (p.ej. porque Pedro edito
    catastro.json despues) tiene que rechazar, no reasignar ROOT en
    silencio."""
    proyecto = _repo_en_raiz("para-activar")
    r = cliente.post("/api/chats", params={"token": srv.TOKEN},
                     json={"project_path": str(proyecto)})
    assert r.status_code == 200
    chat_id = r.json()["id"]

    # ahora una raiz mas angosta que ya no cubre `proyecto`.
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


# --- _repo_brief recibe la raiz, no lee el global ROOT ----------------------

def test_repo_brief_no_mueve_root_y_describe_otro_proyecto():
    otro = _repo_en_raiz("otro-proyecto")
    (otro / "README.md").write_text("Otro proyecto\nResumen.\n", encoding="utf-8")
    original = srv.ROOT

    brief = srv._repo_brief(otro)

    assert srv.ROOT == original  # no se movio
    assert "README.md" in brief


# --- GET /api/catastro y GET /api/catastro/{nombre} ------------------------

def test_endpoint_catastro_lista(cliente):
    r = cliente.get("/api/catastro", params={"token": srv.TOKEN})
    assert r.status_code == 200
    assert "proyectos" in r.json()


def test_endpoint_catastro_detalle_404_si_no_existe(cliente):
    r = cliente.get("/api/catastro/no-existe-este-nombre",
                    params={"token": srv.TOKEN})
    assert r.status_code == 404


def test_endpoint_catastro_detalle_trae_el_brief_sin_mover_root(cliente):
    _repo_en_raiz("con-detalle")
    catastro.cargar(forzar_escaneo=True)
    original = srv.ROOT

    r = cliente.get("/api/catastro/con-detalle", params={"token": srv.TOKEN})

    assert r.status_code == 200
    body = r.json()
    assert body["proyecto"]["nombre"] == "con-detalle"
    assert "brief" in body
    assert srv.ROOT == original


# --- la rutina catastro se agrega sola en maquinas con routines.json viejo -

def test_asegurar_rutina_catastro_agrega_si_falta_y_es_idempotente():
    """`routines.DEFAULTS` solo siembra al crear routines.json por primera
    vez: una maquina con un routines.json de antes de este cambio (como
    esta misma, verificado con GET /api/routines antes de agregar esta
    migracion) nunca ve aparecer "catastro" sola. `_asegurar_rutina_
    catastro` (llamada en el startup del servidor) es el parche."""
    from calipso import routines as calipso_routines

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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
