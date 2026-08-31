"""El endpoint que junta las cuatro bandejas.

Se monta el home a mano porque el estado de hoy es que la economia no esta
sembrada: sin eso, tres de las cuatro fuentes contestan vacio y el test no
probaria nada.
"""
import json
import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso.economia import departamentos as deps
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    """Las DOS cosas: _ECO_BASE y CALIPSO_HOME.

    `permisos/almacen.py` resuelve el home en cada llamada, mientras que
    `librarian.py` lo congela al importar. Sin las dos, el test escribe en
    el ~/.calipso real."""
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
    k.acunar("2026-08-25T09:00:00", "2026-W35", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", home)
    monkeypatch.setenv("CALIPSO_HOME", str(home))
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_el_inbox_contesta_con_las_cuatro_declaraciones(cliente):
    r = cliente.get("/api/inbox")
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo["descriptores"]) == {
        "mesa", "permisos", "biblioteca", "cartas"}


def test_una_propuesta_de_la_mesa_llega_al_inbox(cliente, tmp_path):
    from calipso.economia.bus import Bus
    b = Bus(tmp_path / ".calipso" / "economia" / "bus.jsonl")
    b.alta("2026-08-25T09:00:00", "2026-W35", "p1", "dep:a",
           "escribir el landing", 50_000, 50_000, {"gasto_max_mm": 50_000})
    items = cliente.get("/api/inbox").json()["items"]
    de_mesa = [i for i in items if i["origen"] == "mesa"]
    assert len(de_mesa) == 1
    assert de_mesa[0]["titulo"] == "escribir el landing"


def test_el_contador_cuenta_decisiones_y_no_avisos(cliente, tmp_path):
    """Es la unica forma real en que este diseno fracasa: si el numero no
    baja nunca, Pedro deja de mirarlo.

    Con el home recien montado no hay ningun aviso, asi que comparar
    `pendientes` contra la cuenta de decisiones da 0 == 0 y no prueba
    nada. Por eso se corrompe a mano `permisos/solicitudes.json`: eso hace
    que `motor.vista()` levante `ErrorPermisos`, la atrape y devuelva su
    clave `error`, y que el adaptador de permisos (Tarea 2) traduzca eso a
    un item de clase "aviso" -- el camino de punta a punta que hoy no
    tiene cobertura. El contador tiene que IGNORAR ese aviso.
    """
    solicitudes = tmp_path / ".calipso" / "permisos" / "solicitudes.json"
    solicitudes.parent.mkdir(parents=True, exist_ok=True)
    solicitudes.write_text("esto no es json valido", encoding="utf-8")

    cuerpo = cliente.get("/api/inbox").json()
    avisos = [i for i in cuerpo["items"] if i["clase"] == "aviso"]
    assert len(avisos) >= 1, "el archivo corrupto tiene que emitir un aviso"
    decisiones = [i for i in cuerpo["items"] if i["clase"] == "decision"]
    assert cuerpo["pendientes"] == len(decisiones)
    assert cuerpo["pendientes"] != len(cuerpo["items"])


def test_sin_auth_rechaza(tmp_path):
    assert TestClient(srv.app).get("/api/inbox").status_code == 401


def test_una_bandeja_rota_no_voltea_el_inbox(cliente, tmp_path, monkeypatch):
    """Cuatro fuentes es cuatro veces la chance de que una falle. Si una se
    cae, las otras tres se siguen viendo y se dice cual fallo."""
    def explota(*a, **k):
        raise RuntimeError("bandeja rota")
    monkeypatch.setattr(srv._inbox.librarian, "como_items", explota)
    cuerpo = cliente.get("/api/inbox").json()
    assert "biblioteca" in cuerpo["fallaron"]
    assert cuerpo["descriptores"]["mesa"]
