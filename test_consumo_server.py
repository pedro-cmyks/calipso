#!/usr/bin/env python3
"""
test_consumo_server.py - el septimo kind de rutina: "consumo", que corre
`calipso.consumo.escanear()` + `resumen()` -- el probe pasivo que lee lo
que Claude Code y Codex ya escriben solos en disco, sin llamar a ningun
modelo ni CLI. Mismo patron que test_economia_cierre_rutina.py: no hace
falta el subproceso de test_catastro_server.py porque ni routines.py ni
consumo.py necesitan la economia (_ECO_BASE) para nada -- alcanza con
monkeypatch.setattr sobre el atributo ya importado (routines.CALIPSO_HOME,
frozen al importar) y monkeypatch.setenv para consumo.py (que resuelve
CALIPSO_HOME/CLAUDE_HOME/CODEX_HOME en cada llamada, a proposito, ver su
docstring).
"""
from __future__ import annotations

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso import consumo
from calipso import routines as calipso_routines


@pytest.fixture
def aislado(tmp_path, monkeypatch):
    calipso_home = tmp_path / "calipso_home"
    claude_home = tmp_path / "claude_home"
    codex_home = tmp_path / "codex_home"
    for d in (calipso_home, claude_home, codex_home):
        d.mkdir()
    monkeypatch.setattr(calipso_routines, "CALIPSO_HOME", calipso_home)
    monkeypatch.setenv("CALIPSO_HOME", str(calipso_home))
    monkeypatch.setenv("CLAUDE_HOME", str(claude_home))
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    return {"calipso": calipso_home, "claude": claude_home, "codex": codex_home}


# ---------------------------------------------------------------------
# routines.py: el kind existe y nace habilitada
# ---------------------------------------------------------------------

def test_consumo_es_un_kind_soportado():
    assert "consumo" in calipso_routines.KINDS


def test_consumo_nace_habilitada_en_el_seed():
    seed = calipso_routines._seed()
    rutina = next(r for r in seed if r["kind"] == "consumo")
    assert rutina["enabled"] is True
    assert rutina["interval_minutes"] == 60


# ---------------------------------------------------------------------
# el handler: no llama a ningun modelo ni CLI, solo lee jsonl locales
# ---------------------------------------------------------------------

def test_handler_sin_datos_no_revienta(aislado):
    handler = srv._routine_handlers()["consumo"]
    handler({"kind": "consumo"})  # no debe lanzar nada
    assert consumo.cargar_resumen() is not None


def test_handler_via_run_due_marca_ok(aislado):
    rt = calipso_routines.add("consumo", "Medir consumo real", 60, enabled=True)
    import datetime
    ran = calipso_routines.run_due(datetime.datetime.now(), srv._routine_handlers())
    de_consumo = next(r for r in ran if r["id"] == rt["id"])
    assert de_consumo["status"] == "ok"


def test_handler_escanea_un_jsonl_de_claude_de_verdad(aislado):
    archivo = aislado["claude"] / "projects" / "-proj" / "sesion1.jsonl"
    archivo.parent.mkdir(parents=True, exist_ok=True)
    archivo.write_text(json.dumps({
        "type": "assistant", "timestamp": "2026-08-27T10:00:00.000Z",
        "message": {"id": "msg_1", "model": "claude-sonnet-5",
                   "usage": {"input_tokens": 5, "output_tokens": 20,
                            "cache_creation_input_tokens": 0,
                            "cache_read_input_tokens": 0}}}) + "\n",
        encoding="utf-8")

    handler = srv._routine_handlers()["consumo"]
    handler({"kind": "consumo"})

    resumen = consumo.cargar_resumen()
    assert resumen["claude"]["medicion"]["turnos_observados"] == 1
    assert resumen["claude"]["medicion"]["tokens"]["output_tokens"] == 20


# ---------------------------------------------------------------------
# la migracion: routines.json ya existente (como el de Pedro) gana el kind
# ---------------------------------------------------------------------

def test_asegurar_rutina_consumo_agrega_si_falta_y_es_idempotente(aislado):
    calipso_routines.save([
        {"id": "rt_vieja1", "kind": "reflect", "label": "Reflexionar",
         "interval_minutes": 1440, "enabled": False, "last_run": None,
         "last_status": None},
    ])
    antes = calipso_routines.load()
    assert not any(r["kind"] == "consumo" for r in antes)

    srv._asegurar_rutina_consumo()
    despues = calipso_routines.load()
    consumos = [r for r in despues if r["kind"] == "consumo"]
    assert len(consumos) == 1
    assert consumos[0]["enabled"] is True

    srv._asegurar_rutina_consumo()
    otra_vez = calipso_routines.load()
    assert len([r for r in otra_vez if r["kind"] == "consumo"]) == 1


# ---------------------------------------------------------------------
# de punta a punta por la API publica
# ---------------------------------------------------------------------

@pytest.fixture
def cliente(aislado):
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_consumo_como_rutina_por_la_api(cliente, aislado):
    r = cliente.post("/api/routines", json={
        "kind": "consumo", "label": "Medir consumo real de las suscripciones",
        "interval_minutes": 60, "enabled": True})
    assert r.status_code == 200
    rutina = r.json()
    assert rutina["enabled"] is True

    r2 = cliente.post(f"/api/routines/{rutina['id']}/run")
    assert r2.status_code == 200
    body = r2.json()
    assert body["ok"] is True and body["status"] == "ok"

    assert consumo.cargar_resumen() is not None
