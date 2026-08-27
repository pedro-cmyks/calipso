# test_economia_cierre_rutina.py
"""El sexto kind de rutina: "cierre", que dispara
`economia.operacion.cerrar_semana_operativa` -- el latido que hoy solo
corre a mano via POST /api/economia/cierre y que nadie llama nunca.

Aisla CALIPSO_HOME/`_ECO_BASE` en tmp_path en cada test (patron de
test_economia_server.py): la economia nunca se construye contra el
~/.calipso real de Pedro.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso import routines as calipso_routines
from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.economia.pagador import Pagador

TS = "2026-08-25T09:00:00"


def _armar_economia(base) -> Pagador:
    """Siembra libro/departamentos/suscripciones bajo `base/economia`,
    igual que la fixture `cliente` de test_economia_server.py."""
    eco = base / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=10_000,
                             techo_api_ciclo_mm=500_000))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    k.acunar(TS, "2026-W30", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    return Pagador(eco)


# ---------------------------------------------------------------------
# routines.py: el kind existe y nace apagado
# ---------------------------------------------------------------------

def test_cierre_es_un_kind_soportado():
    assert "cierre" in calipso_routines.KINDS


def test_cierre_nace_deshabilitada_en_el_seed():
    # _seed() es puro (no toca disco): seguro de llamar sin aislar CALIPSO_HOME
    seed = calipso_routines._seed()
    rutina = next(r for r in seed if r["kind"] == "cierre")
    assert rutina["enabled"] is False
    assert rutina["interval_minutes"] == 1440


def test_las_seis_rutinas_conocidas_siguen_ahi():
    seed = calipso_routines._seed()
    assert {r["kind"] for r in seed} == {
        "reflect", "learn", "backup", "catastro", "cierre"}


# ---------------------------------------------------------------------
# el handler: mismo llamador que api_eco_cierre, con economia inactiva
# ---------------------------------------------------------------------

def test_handler_sin_economia_no_revienta(tmp_path, monkeypatch):
    # ~/.calipso/economia ni existe: ni libro, ni departamentos, ni
    # suscripciones -- el escenario real de hoy en la maquina de Pedro.
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    handler = srv._routine_handlers()["cierre"]
    handler({"kind": "cierre"})  # no debe lanzar nada


def test_handler_via_run_due_con_economia_inactiva_marca_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(calipso_routines, "CALIPSO_HOME", tmp_path / ".calipso")
    rt = calipso_routines.add("cierre", "Cerrar semana operativa", 1440,
                              enabled=True)
    import datetime
    ran = calipso_routines.run_due(
        datetime.datetime.now(), srv._routine_handlers())
    de_cierre = next(r for r in ran if r["id"] == rt["id"])
    assert de_cierre["status"] == "ok"


# ---------------------------------------------------------------------
# el handler ejecuta el mismo pulso que api_eco_cierre
# ---------------------------------------------------------------------

def test_handler_expira_pt_y_reparte_presupuesto(tmp_path, monkeypatch):
    p0 = _armar_economia(tmp_path / ".calipso")
    pt.emitir_semana(p0.leer_kernel(), TS, "2026-W30", 4_000, 0)

    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, "2026-W30"))
    handler = srv._routine_handlers()["cierre"]
    handler({"kind": "cierre"})

    k2 = p0.leer_kernel()
    # dep:a tiene presupuesto_semanal_mm=10_000: el cierre se lo asigno
    assert k2.saldo("dep:a") == 10_000
    # el pool de fabrica (4_000 - 0 de reserva) expiro al cerrar la semana
    assert k2.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 0


def test_handler_no_asigna_presupuesto_de_direccion(tmp_path, monkeypatch):
    """La rutina no tiene quien le pase presupuesto_direccion_mm: hereda
    el 0 explicito del endpoint, no inventa una cifra. DIRECCION sigue en
    cero tras el cierre automatico."""
    p0 = _armar_economia(tmp_path / ".calipso")
    pt.emitir_semana(p0.leer_kernel(), TS, "2026-W30", 4_000, 0)

    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, "2026-W30"))
    srv._routine_handlers()["cierre"]({"kind": "cierre"})

    k2 = p0.leer_kernel()
    assert k2.saldo(t.DIRECCION) == 0


# ---------------------------------------------------------------------
# idempotencia: dos disparos de la misma semana no duplican nada
# ---------------------------------------------------------------------

def test_handler_es_idempotente_en_la_misma_semana(tmp_path, monkeypatch):
    p0 = _armar_economia(tmp_path / ".calipso")
    pt.emitir_semana(p0.leer_kernel(), TS, "2026-W30", 4_000, 0)

    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, "2026-W30"))
    handler = srv._routine_handlers()["cierre"]

    handler({"kind": "cierre"})
    k1 = p0.leer_kernel()
    saldo_1 = k1.saldo("dep:a")
    asientos_1 = len(k1.libro.asientos())

    # una rutina que corre cada hora podria disparar el cierre varias
    # veces sobre la misma semana operativa; no debe pagar dos veces
    handler({"kind": "cierre"})
    handler({"kind": "cierre"})
    k2 = p0.leer_kernel()
    assert k2.saldo("dep:a") == saldo_1 == 10_000
    assert len(k2.libro.asientos()) == asientos_1


# ---------------------------------------------------------------------
# la prueba que importa: la rutina dispara la quiebra tecnica y congela
# ---------------------------------------------------------------------

def test_handler_declara_quiebra_y_congela_el_departamento(tmp_path, monkeypatch):
    """Hoy `es_congelado` no puede devolver True en produccion porque
    nadie corre el cierre. Esta prueba arma un departamento en quiebra
    tecnica, corre la rutina, y confirma que el mecanismo SI se dispara."""
    p0 = _armar_economia(tmp_path / ".calipso")
    k = p0.leer_kernel()
    pt.emitir_semana(k, TS, "2026-W30", 4_000, 0)

    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, "2026-W30"))
    handler = srv._routine_handlers()["cierre"]

    # semana 1: dep:a recibe su presupuesto semanal (10_000) via la rutina
    handler({"kind": "cierre"})
    assert deps.es_congelado(p0.leer_kernel().libro.asientos(), "dep:a") is False

    # dep:a gasta TODO lo que tiene -> queda en quiebra tecnica
    m = p0.mercado_fresco()
    m.gastar_api(TS, "2026-W30", "dep:a", 10_000)
    assert m.k.saldo("dep:a") == 0

    # semana 2: se abre y se cierra -> el cierre debe declarar la quiebra
    pt.emitir_semana(p0.leer_kernel(), TS, "2026-W31", 4_000, 0)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, "2026-W31"))
    handler({"kind": "cierre"})

    asientos_final = p0.leer_kernel().libro.asientos()
    assert deps.es_congelado(asientos_final, "dep:a") is True
    # y el congelado no recibio un segundo presupuesto en la semana que quebro
    assert p0.leer_kernel().saldo("dep:a") == 0

    # el cierre siguiente (idempotente) no re-declara la quiebra ni la
    # descongela sola
    pt.emitir_semana(p0.leer_kernel(), TS, "2026-W32", 4_000, 0)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, "2026-W32"))
    handler({"kind": "cierre"})
    assert deps.es_congelado(p0.leer_kernel().libro.asientos(), "dep:a") is True


# ---------------------------------------------------------------------
# la migracion: routines.json ya existente (como el de Pedro) tambien
# gana el kind, apagado
# ---------------------------------------------------------------------

def test_asegurar_rutina_cierre_agrega_si_falta_y_es_idempotente(tmp_path, monkeypatch):
    monkeypatch.setattr(calipso_routines, "CALIPSO_HOME", tmp_path / ".calipso")
    # simula un routines.json viejo, de antes de que "cierre" existiera como
    # kind -- escrito a mano para no pasar por _seed(), que ya conoce
    # "cierre" con el cambio de esta rama
    calipso_routines.save([
        {"id": "rt_vieja1", "kind": "reflect", "label": "Reflexionar",
         "interval_minutes": 1440, "enabled": False, "last_run": None,
         "last_status": None},
        {"id": "rt_vieja2", "kind": "catastro", "label": "Catastro",
         "interval_minutes": 60, "enabled": True, "last_run": None,
         "last_status": None},
    ])
    antes = calipso_routines.load()
    assert not any(r["kind"] == "cierre" for r in antes)

    srv._asegurar_rutina_cierre()
    despues = calipso_routines.load()
    cierres = [r for r in despues if r["kind"] == "cierre"]
    assert len(cierres) == 1
    assert cierres[0]["enabled"] is False

    # correrlo de nuevo no duplica
    srv._asegurar_rutina_cierre()
    otra_vez = calipso_routines.load()
    assert len([r for r in otra_vez if r["kind"] == "cierre"]) == 1


# ---------------------------------------------------------------------
# de punta a punta por la API publica: agregar y correr a mano
# ---------------------------------------------------------------------

@pytest.fixture
def cliente(tmp_path, monkeypatch):
    p0 = _armar_economia(tmp_path / ".calipso")
    pt.emitir_semana(p0.leer_kernel(), TS, "2026-W30", 4_000, 0)
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, "2026-W30"))
    monkeypatch.setattr(calipso_routines, "CALIPSO_HOME", tmp_path / ".calipso")
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN}), p0


def test_cierre_como_rutina_por_la_api(cliente):
    c, p0 = cliente
    r = c.post("/api/routines", json={
        "kind": "cierre", "label": "Cerrar semana operativa",
        "interval_minutes": 1440, "enabled": False})
    assert r.status_code == 200
    rutina = r.json()
    assert rutina["enabled"] is False  # nace apagada tambien via la API

    r2 = c.post(f"/api/routines/{rutina['id']}/run")
    assert r2.status_code == 200
    body = r2.json()
    assert body["ok"] is True and body["status"] == "ok"

    k2 = p0.leer_kernel()
    assert k2.saldo("dep:a") == 10_000
