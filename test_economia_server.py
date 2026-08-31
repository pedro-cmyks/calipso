# test_economia_server.py
"""Tests de los endpoints de economia (patron TestClient + cookie del repo)."""
import json
import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.cola import Cola
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    # economia activa en un HOME temporal
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    k.acunar("2026-08-25T09:00:00", "2026-W35", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    # sin cache: cada request reconstruye desde los archivos
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_tablero_responde(cliente):
    r = cliente.get("/api/economia/tablero")
    assert r.status_code == 200
    body = r.json()
    assert body["activa"] is True
    assert body["tablero"]["tesoro_mm"] == 1_200_000


def test_cola_atender_carta(cliente):
    # sembrar una carta via los modulos (el server comparte la carpeta)
    r = cliente.get("/api/economia/cola")
    assert r.json()["pendientes"] == []


def test_sin_auth_rechaza(tmp_path):
    c = TestClient(srv.app)
    assert c.get("/api/economia/tablero",
                 follow_redirects=False).status_code in (302, 401, 403)


def test_abrir_y_fichar_por_la_api(cliente, tmp_path, monkeypatch):
    # ts deterministicos: abrir, clock-in y clock-out (42 min despues)
    tss = iter(["2026-08-25T09:00:00", "2026-08-25T09:00:00",
               "2026-08-25T09:42:00"])
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (next(tss), "2026-W35"))

    r = cliente.post("/api/economia/abrir",
                     json={"cuota_firmable_mpt": 4_000,
                           "reserva_personal_mpt": 1_000})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # sembrar una compuerta con los modulos directamente, misma carpeta
    eco = tmp_path / ".calipso" / "economia"
    k = Kernel(Libro(eco / "libro.jsonl"))
    k.acunar("2026-08-25T09:00:00", "2026-W35", "dep:a", 50_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    Cola(eco / "cola.jsonl").encolar(
        k, "2026-08-25T09:00:00", "2026-W35", "c1", "dep:a", "llamar",
        tipo="contacto", obligatoria=True, mpt_estimado=500,
        monedas_en_juego=9_000)

    r = cliente.post("/api/economia/reloj/in",
                     json={"categoria": "fabrica", "ref": "c1"})
    assert r.status_code == 200

    r = cliente.post("/api/economia/reloj/out")
    assert r.status_code == 200

    k2 = Kernel(Libro(eco / "libro.jsonl"))
    assert k2.saldo(t.CUENTA_PEDRO) > 0


def test_cierre_por_la_api(cliente, monkeypatch):
    monkeypatch.setattr(
        srv, "_eco_ahora", lambda: ("2026-08-25T09:00:00", "2026-W35"))
    r = cliente.post("/api/economia/abrir",
                     json={"cuota_firmable_mpt": 4_000,
                           "reserva_personal_mpt": 0})
    assert r.status_code == 200

    r = cliente.post("/api/economia/cierre",
                     json={"presupuesto_direccion_mm": 0})
    assert r.status_code == 200
    body = r.json()
    assert "expiradas" in body


# --- la semana como dato: el viaje de diez dias ---------------------------
# `abrir` y `cierre` derivaban la semana de datetime.now() y ningun cuerpo
# aceptaba otra. Eso trababa la economia con solo irse unos dias, y de los
# dos lados a la vez: no se puede cerrar la vieja porque hoy no es esa, y no
# se puede abrir la nueva porque la vieja no se cerro. Encima las dos
# negativas salian como 500 opacos.

def test_se_puede_abrir_una_semana_que_no_es_la_de_hoy(cliente):
    r = cliente.post("/api/economia/abrir",
                     json={"cuota_firmable_mpt": 4000,
                           "reserva_personal_mpt": 1000,
                           "semana": "2026-W30"})
    assert r.status_code == 200, r.text
    assert r.json()["semana"] == "2026-W30"


def test_sin_semana_sigue_usando_el_calendario(cliente):
    """El default no cambia: quien no manda semana opera sobre hoy."""
    r = cliente.post("/api/economia/abrir",
                     json={"cuota_firmable_mpt": 4000})
    assert r.status_code == 200, r.text
    assert r.json()["semana"] == srv._eco_ahora()[1]


def test_volver_de_viaje_no_traba_la_economia(cliente):
    """El escenario completo: se abrio W30, Pedro no firmo nada y volvio dos
    semanas despues. Antes esto era un callejon sin salida."""
    cliente.post("/api/economia/abrir",
                 json={"cuota_firmable_mpt": 4000, "semana": "2026-W30"})

    # cerrar la de HOY se niega: la del calendario nunca se abrio
    hoy = cliente.post("/api/economia/cierre", json={})
    assert hoy.status_code == 400, hoy.text
    assert "no operativa" in hoy.json()["detail"]

    # abrir la siguiente tambien se niega: el pool de W30 tiene saldo
    otra = cliente.post("/api/economia/abrir",
                        json={"cuota_firmable_mpt": 4000,
                              "semana": "2026-W32"})
    assert otra.status_code == 400, otra.text
    assert "sin cerrar" in otra.json()["detail"]

    # la salida: cerrar la que de verdad quedo abierta, y seguir
    cerrada = cliente.post("/api/economia/cierre", json={"semana": "2026-W30"})
    assert cerrada.status_code == 200, cerrada.text
    abierta = cliente.post("/api/economia/abrir",
                           json={"cuota_firmable_mpt": 4000,
                                 "semana": "2026-W32"})
    assert abierta.status_code == 200, abierta.text


def test_los_dos_errores_dejan_de_ser_500_opacos(cliente):
    """La pantalla muestra `detail`: si sale 500 no tiene que mostrar."""
    cliente.post("/api/economia/abrir",
                 json={"cuota_firmable_mpt": 4000, "semana": "2026-W30"})
    r = cliente.post("/api/economia/abrir",
                     json={"cuota_firmable_mpt": 4000, "semana": "2026-W31"})
    assert r.status_code == 400
    assert r.json()["detail"], "el 400 llego sin motivo que mostrar"


def test_una_semana_mal_escrita_no_entra_al_libro(cliente):
    """El libro es append-only: una semana con forma invalida no sale mas."""
    for mala in ["2026-35", "W35", "2026-W3", "", "2026-W35; drop"]:
        r = cliente.post("/api/economia/abrir",
                         json={"cuota_firmable_mpt": 4000, "semana": mala})
        assert r.status_code == 400, f"paso una semana invalida: {mala!r}"
        assert "semana invalida" in r.json()["detail"]
