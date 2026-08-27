#!/usr/bin/env python3
"""
test_permisos_server.py — El motor de permisos por HTTP, con las acciones
de plata como primer consumidor (spec de ojos y manos, seccion 5).

Mismo patron que test_economia_server.py (TestClient + cookie), con una
diferencia que importa: ademas de pisar `srv._ECO_BASE` -- que es un
CALIPSO_HOME congelado al importar, la trampa que ya se cazo con
catastro.json -- se fija la VARIABLE DE ENTORNO, porque el motor de
permisos la resuelve en cada llamada. Sin las dos, la mitad de este
archivo escribiria en el ~/.calipso real de Pedro.
"""
import json

import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso.economia import departamentos as deps
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.permisos import motor as permisos_motor


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    home = tmp_path / ".calipso"
    eco = home / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    k.acunar("2026-08-27T09:00:00", "2026-W35", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", home)
    monkeypatch.setenv("CALIPSO_HOME", str(home))
    monkeypatch.setattr(srv, "_eco_ahora",
                        lambda: ("2026-08-27T10:00:00", "2026-W35"))
    c = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})
    c.home = home
    return c


def acunaciones(home):
    lineas = (home / "economia" / "libro.jsonl").read_text().splitlines()
    return [json.loads(x) for x in lineas if x.strip()
            and json.loads(x)["tipo"] == "acunacion"]


def acunar(cliente, monto_mm, **extra):
    return cliente.post("/api/economia/frontera/acunar",
                        json={"subtipo": "capital", "destino": "tesoro",
                              "monto_mm": monto_mm,
                              "evidencia": {"tipo": "firma_pedro"}, **extra})


# --------------------------------------------------------------------------
# El camino entero
# --------------------------------------------------------------------------

def test_por_debajo_del_techo_acuna_sola(cliente):
    antes = len(acunaciones(cliente.home))
    r = acunar(cliente, 50_000)          # 50 monedas
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert len(acunaciones(cliente.home)) == antes + 1


def test_por_encima_del_techo_queda_esperando(cliente):
    antes = len(acunaciones(cliente.home))
    r = acunar(cliente, 500_000)         # 500 monedas
    assert r.status_code == 409, r.text
    assert "pendiente" in r.json()["detail"]
    # y no acuno nada
    assert len(acunaciones(cliente.home)) == antes

    v = cliente.get("/api/permisos").json()
    assert v["activo"] is True
    assert len(v["pendientes"]) == 1
    assert v["pendientes"][0]["accion"]["forma"]["monto_mm"] == 500_000
    assert v["techos"]["plata_mm"] == 100_000


def test_pedro_contesta_que_si_y_recien_ahi_acuna(cliente):
    antes = len(acunaciones(cliente.home))
    acunar(cliente, 500_000)
    sol = cliente.get("/api/permisos").json()["pendientes"][0]

    r = cliente.post(f"/api/permisos/solicitudes/{sol['id']}/responder",
                     json={"respuesta": "si"})
    assert r.status_code == 200, r.text
    assert r.json()["ejecucion"]["ejecutada"] is True
    assert r.json()["solicitud"]["estado"] == "ejecutada"
    ac = acunaciones(cliente.home)
    assert len(ac) == antes + 1
    assert ac[-1]["monto"] == 500_000
    # y ya no queda nada pendiente
    assert cliente.get("/api/permisos").json()["pendientes"] == []


def test_contestar_dos_veces_no_acuna_dos_veces(cliente):
    acunar(cliente, 500_000)
    sol = cliente.get("/api/permisos").json()["pendientes"][0]
    cliente.post(f"/api/permisos/solicitudes/{sol['id']}/responder",
                 json={"respuesta": "si"})
    n = len(acunaciones(cliente.home))
    r = cliente.post(f"/api/permisos/solicitudes/{sol['id']}/responder",
                     json={"respuesta": "si"})
    assert r.status_code == 400
    assert len(acunaciones(cliente.home)) == n


def test_pedro_contesta_que_no(cliente):
    antes = len(acunaciones(cliente.home))
    acunar(cliente, 500_000)
    sol = cliente.get("/api/permisos").json()["pendientes"][0]
    r = cliente.post(f"/api/permisos/solicitudes/{sol['id']}/responder",
                     json={"respuesta": "no"})
    assert r.json()["solicitud"]["estado"] == "negada"
    assert len(acunaciones(cliente.home)) == antes


def test_la_plata_no_admite_permiso_permanente(cliente):
    acunar(cliente, 500_000)
    sol = cliente.get("/api/permisos").json()["pendientes"][0]
    r = cliente.post(f"/api/permisos/solicitudes/{sol['id']}/responder",
                     json={"respuesta": "si_siempre"})
    assert r.status_code == 400
    assert "pregunta siempre" in r.json()["detail"]
    assert cliente.get("/api/permisos").json()["concedidos"] == []


def test_el_techo_se_mueve_por_la_api(cliente):
    r = cliente.post("/api/permisos/techo",
                     json={"nombre": "plata_mm", "valor": 900_000})
    assert r.status_code == 200
    assert r.json()["techos"]["plata_mm"] == 900_000
    assert acunar(cliente, 500_000).status_code == 200


def test_un_techo_invalido_se_rechaza(cliente):
    assert cliente.post("/api/permisos/techo",
                        json={"nombre": "plata_mm",
                              "valor": -1}).status_code == 400


# --------------------------------------------------------------------------
# El banco personal, por la misma puerta
# --------------------------------------------------------------------------

def movimientos(home):
    p = home / "economia" / "personal.jsonl"
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def test_movimiento_bajo_el_techo_pasa_solo(cliente):
    r = cliente.post("/api/economia/personal/movimiento",
                     json={"tipo": "ingreso", "monto_mm": 90_000,
                           "categoria": "sueldo"})
    assert r.status_code == 200, r.text
    assert len(movimientos(cliente.home)) == 1


def test_movimiento_sobre_el_techo_pregunta_y_despues_pasa(cliente):
    r = cliente.post("/api/economia/personal/movimiento",
                     json={"tipo": "gasto", "monto_mm": 300_000,
                           "categoria": "alquiler", "nota": "agosto"})
    assert r.status_code == 409, r.text
    assert movimientos(cliente.home) == []
    sol = cliente.get("/api/permisos").json()["pendientes"][0]
    cliente.post(f"/api/permisos/solicitudes/{sol['id']}/responder",
                 json={"respuesta": "si"})
    movs = movimientos(cliente.home)
    assert len(movs) == 1
    assert movs[0]["monto_mm"] == 300_000
    assert movs[0]["nota"] == "agosto"   # el detalle llega al ejecutor


# --------------------------------------------------------------------------
# 5.6 -- el camino desatendido, por HTTP
# --------------------------------------------------------------------------

def test_una_rutina_estaciona_y_no_deja_prompt_colgado(cliente):
    r = acunar(cliente, 500_000, origen="rutina", departamento="dep:a",
               corrida="corr-1")
    assert r.status_code == 409
    assert "estacionada" in r.json()["detail"]
    v = cliente.get("/api/permisos").json()
    assert v["pendientes"] == []          # no hay prompt esperando a nadie
    assert len(v["estacionadas"]) == 1
    assert acunaciones(cliente.home) == acunaciones(cliente.home)


def test_lo_estacionado_no_se_rodea_por_otro_endpoint(cliente):
    acunar(cliente, 500_000, origen="rutina", departamento="dep:a",
           corrida="corr-1")
    # la misma corrida intenta un movimiento que POR SU MONTO seria directo
    r = cliente.post("/api/economia/personal/movimiento",
                     json={"tipo": "gasto", "monto_mm": 1_000,
                           "categoria": "cafe", "origen": "rutina",
                           "departamento": "dep:a", "corrida": "corr-1"})
    assert r.status_code == 409, r.text
    assert movimientos(cliente.home) == []
    sol = cliente.get("/api/permisos").json()["estacionadas"][0]
    assert any(i["que"] == "rodeo de corrida" for i in sol["intentos"])


def test_lo_estacionado_no_se_rodea_por_otro_departamento(cliente):
    acunar(cliente, 500_000, origen="rutina", departamento="dep:a",
           corrida="corr-1")
    r = acunar(cliente, 500_000, origen="rutina", departamento="dep:b",
               corrida="corr-2")
    assert r.status_code == 409
    v = cliente.get("/api/permisos").json()
    assert len(v["estacionadas"]) == 1    # una sola pared, no dos


def test_una_estacionada_aprobada_la_retoma_la_rutina(cliente):
    antes = len(acunaciones(cliente.home))
    acunar(cliente, 500_000, origen="rutina", departamento="dep:a",
           corrida="corr-1")
    sol = cliente.get("/api/permisos").json()["estacionadas"][0]
    r = cliente.post(f"/api/permisos/solicitudes/{sol['id']}/responder",
                     json={"respuesta": "si"})
    # aprobar una estacionada NO la ejecuta: la rutina la retoma
    assert r.json()["ejecucion"] is None
    assert len(acunaciones(cliente.home)) == antes
    # y en la corrida siguiente pasa, una sola vez
    assert acunar(cliente, 500_000, origen="rutina", departamento="dep:a",
                  corrida="corr-2").status_code == 200
    assert len(acunaciones(cliente.home)) == antes + 1
    assert acunar(cliente, 500_000, origen="rutina", departamento="dep:a",
                  corrida="corr-3").status_code == 409


# --------------------------------------------------------------------------
# La puerta de siempre
# --------------------------------------------------------------------------

def test_sin_auth_no_se_contesta_un_prompt(cliente):
    acunar(cliente, 500_000)
    sol = cliente.get("/api/permisos").json()["pendientes"][0]
    anon = TestClient(srv.app)
    r = anon.post(f"/api/permisos/solicitudes/{sol['id']}/responder",
                  json={"respuesta": "si"}, follow_redirects=False)
    assert r.status_code in (401, 403, 302)
    assert anon.get("/api/permisos",
                    follow_redirects=False).status_code in (401, 403, 302)


def test_la_validacion_del_endpoint_corre_antes_del_prompt(cliente):
    # un pedido invalido no se estaciona para que Pedro apruebe algo que
    # despues va a fallar igual
    r = cliente.post("/api/economia/frontera/acunar",
                     json={"subtipo": "capital", "destino": "dep:a",
                           "monto_mm": 900_000,
                           "evidencia": {"tipo": "firma_pedro"}})
    assert r.status_code == 400
    assert cliente.get("/api/permisos").json()["pendientes"] == []


def test_revocar_un_permiso_inexistente(cliente):
    assert cliente.post(
        "/api/permisos/concedidos/per_nada/revocar").status_code == 404


def test_el_registro_deja_rastro_de_todo(cliente):
    acunar(cliente, 1_000)
    acunar(cliente, 500_000)
    reg = cliente.get("/api/permisos").json()["registro"]
    estados = [l.get("estado") for l in reg if l.get("estado")]
    assert "permitido" in estados and "pendiente" in estados
