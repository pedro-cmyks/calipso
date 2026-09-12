"""`run_due(now, handlers, nivel=None)` (spec 2026-09-11, 3.7): bajo cargada
toda rutina vencida se pospone; bajo justa solo `departamento` (la unica que
carga el modelo local); una pospuesta NO pasa por mark_run (last_run intacto,
sigue vencida al tick siguiente) y se anota en `ran` con POSPUESTA; sin
nivel, como hoy (test_routines.py, el script, sigue verde)."""
from __future__ import annotations

import datetime

import pytest

from calipso import routines as calipso_routines


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(calipso_routines, "CALIPSO_HOME", tmp_path)
    for r in calipso_routines.load():
        calipso_routines.update(r["id"], {"enabled": False})
    dep = calipso_routines.add("departamento", "dep", 60, enabled=True, cuenta="atlas")
    cat = calipso_routines.add("catastro", "cat", 60, enabled=True)
    return {"departamento": dep["id"], "catastro": cat["id"]}


def _handlers(corridas):
    return {"departamento": lambda r: corridas.append("departamento"),
            "catastro": lambda r: corridas.append("catastro")}


def test_bajo_cargada_todas_se_posponen_sin_mark_run_y_siguen_vencidas(home):
    now = datetime.datetime(2026, 9, 11, 19, 0, 0)
    corridas = []
    ran = calipso_routines.run_due(now, _handlers(corridas), nivel="cargada")
    assert corridas == []
    assert sorted((r["kind"], r["status"]) for r in ran) == [
        ("catastro", calipso_routines.POSPUESTA), ("departamento", calipso_routines.POSPUESTA)]
    for r in calipso_routines.load():
        if r["id"] in home.values():
            assert r["last_run"] is None and r["last_status"] is None
            assert calipso_routines.is_due(r, now + datetime.timedelta(seconds=60))


def test_bajo_justa_solo_departamento_se_pospone(home):
    now = datetime.datetime(2026, 9, 11, 19, 0, 0)
    corridas = []
    ran = calipso_routines.run_due(now, _handlers(corridas), nivel="justa")
    assert corridas == ["catastro"]
    estados = {r["kind"]: r["status"] for r in ran}
    assert estados == {"catastro": "ok", "departamento": calipso_routines.POSPUESTA}
    cat = calipso_routines.get(home["catastro"])
    assert cat["last_run"] == "2026-09-11T19:00:00" and cat["last_status"] == "ok"
    assert calipso_routines.get(home["departamento"])["last_run"] is None


def test_bajo_holgada_o_sin_nivel_corren_todas_como_hoy(home):
    now = datetime.datetime(2026, 9, 11, 19, 0, 0)
    corridas = []
    ran = calipso_routines.run_due(now, _handlers(corridas), nivel="holgada")
    assert sorted(corridas) == ["catastro", "departamento"]
    assert all(r["status"] == "ok" for r in ran)
    # sin nivel (los tres llamadores viejos, posicional): como hoy
    corridas.clear()
    ran = calipso_routines.run_due(now + datetime.timedelta(hours=2), _handlers(corridas))
    assert sorted(corridas) == ["catastro", "departamento"]


def test_se_pospone_es_la_regla_del_spec():
    assert calipso_routines.PESADAS == ("departamento",)
    assert calipso_routines.se_pospone("reflect", "cargada") is True
    assert calipso_routines.se_pospone("departamento", "justa") is True
    assert calipso_routines.se_pospone("reflect", "justa") is False
    assert calipso_routines.se_pospone("departamento", "holgada") is False
    assert calipso_routines.se_pospone("departamento", None) is False
