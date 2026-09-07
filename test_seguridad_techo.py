"""Revision de seguridad 2026-09-07, punto 2: el techo de _switch_project
(C2), la defensa en profundidad de _safe, el filtro de token en los logs y
el entorno saneado de los CLIs de suscripcion (C4 + deferido de C1)."""
import logging
import pathlib

import pytest
from fastapi import HTTPException

import calipso.server as srv


# --- C2: el techo de _switch_project ----------------------------------------

def _permitir_catastro(monkeypatch):
    monkeypatch.setattr(srv.catastro, "dentro_de_alguna_raiz", lambda p: True)


def test_el_home_no_se_abre_como_proyecto(monkeypatch):
    _permitir_catastro(monkeypatch)
    with pytest.raises(HTTPException) as e:
        srv._switch_project(str(pathlib.Path.home()))
    assert e.value.status_code == 400


def test_calipso_home_no_es_proyecto(tmp_path, monkeypatch):
    _permitir_catastro(monkeypatch)
    monkeypatch.setattr(srv, "_home_calipso", lambda: tmp_path)
    with pytest.raises(HTTPException) as e:
        srv._switch_project(str(tmp_path))
    assert e.value.status_code == 400
    sub = tmp_path / "global"
    sub.mkdir()
    with pytest.raises(HTTPException):
        srv._switch_project(str(sub))


def test_carpeta_oculta_del_home_no_es_proyecto(monkeypatch):
    _permitir_catastro(monkeypatch)
    oculta = pathlib.Path.home() / ".config"
    if not oculta.is_dir():
        pytest.skip("no hay ~/.config en esta maquina")
    with pytest.raises(HTTPException) as e:
        srv._switch_project(str(oculta))
    assert e.value.status_code == 400


def test_carpeta_normal_sin_repo_si_se_abre(tmp_path, monkeypatch):
    # calipso-lector no es un repo git y ES un proyecto legitimo de Pedro:
    # el techo no exige repo, solo veda home/estado/ocultas.
    _permitir_catastro(monkeypatch)
    proyecto = tmp_path / "proyecto-normal"
    proyecto.mkdir()
    monkeypatch.setattr(srv, "Memory", lambda project_root=None: srv.mem)
    monkeypatch.setattr(srv, "_remember_project", lambda p: None)
    monkeypatch.setattr(srv.catastro, "marcar_visto", lambda p: None)
    viejo = srv.ROOT
    try:
        srv._switch_project(str(proyecto))
        assert srv.ROOT == proyecto
    finally:
        srv.ROOT = viejo


# --- C2: defensa en profundidad de _safe ------------------------------------

def test_safe_veda_credenciales_aunque_root_las_contenga(monkeypatch):
    monkeypatch.setattr(srv, "ROOT", pathlib.Path.home().resolve())
    for rel in (".ssh/id_ed25519", ".aws/credentials", ".gnupg/x",
                ".calipso/token", ".config/gh/hosts.yml",
                ".claude/.credentials.json"):
        with pytest.raises(HTTPException) as e:
            srv._safe(rel)
        assert e.value.status_code == 400, rel


def test_safe_sigue_sirviendo_lo_normal(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "ROOT", tmp_path)
    (tmp_path / "a.txt").write_text("hola", encoding="utf-8")
    assert srv._safe("a.txt") == tmp_path / "a.txt"


# --- C4: el filtro de token en los logs -------------------------------------

def _record(msg):
    return logging.LogRecord(name="uvicorn.access", level=logging.INFO,
                             pathname="", lineno=0, msg=msg, args=(),
                             exc_info=None)


def test_filtro_enmascara_query_token():
    rec = _record('127.0.0.1 - "GET /?token=SECRETO123 HTTP/1.1" 200')
    assert srv._FiltroToken().filter(rec) is True
    assert "SECRETO123" not in rec.getMessage()
    assert "token=***" in rec.getMessage()


def test_filtro_enmascara_el_token_literal():
    rec = _record(f"algo raro con {srv.TOKEN} adentro")
    srv._FiltroToken().filter(rec)
    assert srv.TOKEN not in rec.getMessage()


def test_filtro_deja_pasar_lineas_normales():
    rec = _record('127.0.0.1 - "GET /api/chats HTTP/1.1" 200')
    antes = rec.getMessage()
    srv._FiltroToken().filter(rec)
    assert rec.getMessage() == antes


# --- punto 2: entorno saneado de los CLIs de suscripcion --------------------

def test_env_de_suscripcion_sin_credenciales_y_con_escudo(monkeypatch):
    monkeypatch.setenv("CALIPSO_TOKEN", "tok")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "llm")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "ant")
    monkeypatch.setattr(srv, "_subscription_command", lambda c: "/bin/echo")
    cmd, env, temps, out = srv._subscription_invocation(
        "claude", "sistema", "hola")
    try:
        for clave in ("CALIPSO_TOKEN", "LITELLM_MASTER_KEY",
                      "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
            assert clave not in env
        assert env.get("GIT_CONFIG_COUNT") == "3"  # el escudo git de C1
    finally:
        srv._cleanup_subscription_files(temps, out)


# --- C4: el lanzador ya no pasea el token -----------------------------------

def test_lanzador_sin_token_en_la_url():
    texto = (pathlib.Path(__file__).parent
             / "launch_calipso.py").read_text(encoding="utf-8")
    assert "?token=" not in texto.replace("con ?token=", "")  # solo en el docstring
