"""La mesa anota lo que Pedro dice sobre una propuesta: sus palabras y el
tipo de reaccion (descarto/no_mas/financio), via calipso.plantel.reacciones.
El jefe (fuera del alcance de esta tarea) lee ese registro para aprender."""
import json

import pytest

# el conftest de la raiz ya fija CALIPSO_HOME a un tmp de la suite.
import calipso.server as srv
from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.bus import Bus
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.plantel import reacciones
from fastapi.testclient import TestClient

TS = "2026-08-26T10:00:00"
W = "2026-W35"


@pytest.fixture
def cliente():
    return TestClient(app=srv.app, cookies={srv.COOKIE: srv.TOKEN})


def _economia_de_prueba(base, abrir=True):
    """Calcado de _economia_de_prueba en test_mesa_server.py: una economia
    minima en disco, como la que arma el bootstrap real."""
    eco = base / "economia"
    eco.mkdir(parents=True, exist_ok=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=25_000,
                             techo_preseed_mm=150_000,
                             techo_preseed_ciclo_mm=10_000_000))
    r.alta(deps.Departamento("mercado", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=25_000))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    if abrir:
        pt.emitir_semana(k, TS, W, 4_000, 1_000)
    k.acunar(TS, W, "dep:atlas", 400_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 200_000,
                       "capacidad_ciclo": 2_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    return eco


def _sembrar_propuesta_alta(tmp_path, monkeypatch, id="p1",
                             cuenta="dep:atlas", clave="el radar"):
    """Economia sembrada (calcado de test_mesa_server.py) + una propuesta en
    `alta` CON forma -- sin forma la mesa no tiene de donde derivar el
    "clave" que el piso (`reacciones.esta_vetada`) necesita comparar.

    Apunta el server a un CALIPSO_HOME/economia propio de este test
    (`_ECO_BASE`) y congela el reloj (`_eco_ahora`), igual que el fixture
    `cliente` de test_mesa_server.py -- sin esto dos tests de este archivo
    compartirian el home de la suite entera y el segundo `Registro.alta`
    de "atlas" pisaria al primero.

    Devuelve (id, nombre_dep, clave). `nombre_dep` es exactamente lo que el
    bus guarda en "departamento" (la cuenta "dep:atlas"), porque es
    tambien exactamente lo que `_anotar_reaccion` en server.py le pasa a
    `reacciones.anotar` -- el test tiene que leer del mismo nombre con el
    que se escribio.
    """
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    eco = _economia_de_prueba(tmp_path)
    b = Bus(eco / "bus.jsonl")
    b.alta(TS, W, id, cuenta, "descartar el radar", 10_000, 10_000,
           {"gasto_max_mm": 10_000, "semanas_max": 1},
           forma={"sobre": clave, "clave": clave,
                  "promete": "descartar", "tarda": "corto"})
    dep = b.datos(id)["departamento"]
    return id, dep, clave


def test_descartar_con_palabras_anota_la_reaccion(cliente, tmp_path,
                                                    monkeypatch):
    id_, dep, clave = _sembrar_propuesta_alta(tmp_path, monkeypatch)
    r = cliente.post(f"/api/economia/bus/{id_}/descartar",
                     json={"palabras": "otro angulo"})
    assert r.status_code == 200
    regs = reacciones.leer(dep)
    assert regs and regs[-1]["reaccion"] == "descarto"
    assert regs[-1]["palabras"] == "otro angulo"
    assert regs[-1]["forma"]["clave"] == clave


def test_no_mas_anota_reaccion_no_mas(cliente, tmp_path, monkeypatch):
    id_, dep, clave = _sembrar_propuesta_alta(tmp_path, monkeypatch)
    r = cliente.post(f"/api/economia/bus/{id_}/no-mas",
                     json={"palabras": "no mas de esto"})
    assert r.status_code == 200
    regs = reacciones.leer(dep)
    assert regs[-1]["reaccion"] == "no_mas"
    assert reacciones.esta_vetada(regs, clave) is True


def test_descartar_sin_palabras_sigue_andando(cliente, tmp_path,
                                                monkeypatch):
    id_, dep, _ = _sembrar_propuesta_alta(tmp_path, monkeypatch)
    r = cliente.post(f"/api/economia/bus/{id_}/descartar", json={})
    assert r.status_code == 200
    assert reacciones.leer(dep)[-1]["palabras"] == ""


def test_financiar_con_palabras_anota_financio(cliente, tmp_path,
                                                 monkeypatch):
    id_, dep, _ = _sembrar_propuesta_alta(tmp_path, monkeypatch)
    r = cliente.post(f"/api/economia/bus/{id_}/financiar",
                     json={"cuenta": "dep:atlas", "mm": 10_000,
                           "palabras": "esto si"})
    assert r.status_code == 200
    assert reacciones.leer(dep)[-1]["reaccion"] == "financio"
    assert reacciones.leer(dep)[-1]["palabras"] == "esto si"
