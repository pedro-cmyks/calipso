"""La superficie de juicio del PvP: los endpoints cumplio/no-cumplio anotan
el veredicto de Pedro sobre un trabajo financiado que llego a su plazo
(calipso.plantel.promesas), y la mesa (api_eco_bus) surface la lista
`por_juzgar` y el `standing` por propuesta.

Mismo molde que test_mesa_reacciones_server.py: el bus guarda
"departamento" CON el prefijo de cuenta ("dep:atlas"), pero promesas -como
la carta y las reacciones- vive pelada de prefijo
(memoria/departamento/atlas/). Los helpers de siembra devuelven el nombre
PELADO a proposito.

CALIPSO_HOME se aisla por test (monkeypatch.setenv): sin esto, las promesas
escritas aca se cuelan al home compartido de la suite (fijado por el
conftest de la raiz) y contaminan otros tests que leen ese mismo home."""
import calipso.server as srv
from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.bus import Bus
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from fastapi.testclient import TestClient
import json

import pytest

TS = "2026-08-26T10:00:00"
W = "2026-W35"
W_VENCE = "2026-W36"


@pytest.fixture
def cliente():
    return TestClient(app=srv.app, cookies={srv.COOKIE: srv.TOKEN})


def _economia_de_prueba(base, abrir=True):
    """Calcado de _economia_de_prueba en test_mesa_reacciones_server.py."""
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


def _sembrar_trabajo_vencido(tmp_path, monkeypatch, id="p1",
                              cuenta="dep:atlas", clave="el radar"):
    """Economia sembrada + un trabajo FINANCIADO cuyo plazo (semanas_max=1)
    ya paso: se abre una semana operativa mas alla de la financiacion y el
    reloj corre hasta ella. Aisla CALIPSO_HOME y `_ECO_BASE` para no
    compartir home con la suite ni con otros tests de este archivo.

    Devuelve (id, nombre_dep, clave). `nombre_dep` va PELADO del prefijo
    "dep:" -- el mismo nombre con el que `_juzgar` en server.py llama a
    `promesas.anotar` (le saca el prefijo antes de llamar)."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    eco = _economia_de_prueba(tmp_path)
    b = Bus(eco / "bus.jsonl")
    b.alta(TS, W, id, cuenta, "descartar el radar", 10_000, 10_000,
           {"gasto_max_mm": 10_000, "semanas_max": 1},
           forma={"sobre": clave, "clave": clave,
                  "promete": "descartar", "tarda": "corto"})
    b.marcar(TS, W, id, "financiada")
    k = Kernel(Libro(eco / "libro.jsonl"))
    pt.expirar_pools(k, TS, W_VENCE)
    pt.emitir_semana(k, TS, W_VENCE, 4_000, 1_000)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W_VENCE))
    dep = b.datos(id)["departamento"]
    nombre = dep.split(":", 1)[1] if ":" in dep else dep
    return id, nombre, clave


def _sembrar_trabajo_reciente(tmp_path, monkeypatch, id="p1",
                               cuenta="dep:atlas", clave="el radar"):
    """Gemelo de `_sembrar_trabajo_vencido`: un trabajo FINANCIADO pero
    `semanas_max=4` y sin abrir ninguna semana mas alla de la financiacion
    -- `bus.vencida` tiene que dar False."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    eco = _economia_de_prueba(tmp_path)
    b = Bus(eco / "bus.jsonl")
    b.alta(TS, W, id, cuenta, "descartar el radar", 10_000, 10_000,
           {"gasto_max_mm": 10_000, "semanas_max": 4},
           forma={"sobre": clave, "clave": clave,
                  "promete": "descartar", "tarda": "corto"})
    b.marcar(TS, W, id, "financiada")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    dep = b.datos(id)["departamento"]
    nombre = dep.split(":", 1)[1] if ":" in dep else dep
    return id, nombre, clave


def test_cumplio_anota_el_veredicto(cliente, tmp_path, monkeypatch):
    id_, dep, _ = _sembrar_trabajo_vencido(tmp_path, monkeypatch)
    r = cliente.post(f"/api/economia/bus/{id_}/cumplio", json={"palabras": "listo"})
    assert r.status_code == 200
    from calipso.plantel import promesas
    assert promesas.leer(dep)[-1]["cumplio"] is True
    assert promesas.standing(dep) == {"cumplidas": 1, "total": 1}


def test_no_cumplio_anota_false(cliente, tmp_path, monkeypatch):
    id_, dep, _ = _sembrar_trabajo_vencido(tmp_path, monkeypatch)
    r = cliente.post(f"/api/economia/bus/{id_}/no-cumplio", json={})
    assert r.status_code == 200
    from calipso.plantel import promesas
    assert promesas.leer(dep)[-1]["cumplio"] is False


def test_juzgar_dos_veces_da_400(cliente, tmp_path, monkeypatch):
    id_, dep, _ = _sembrar_trabajo_vencido(tmp_path, monkeypatch)
    assert cliente.post(f"/api/economia/bus/{id_}/cumplio", json={}).status_code == 200
    assert cliente.post(f"/api/economia/bus/{id_}/cumplio", json={}).status_code == 400


def test_juzgar_un_no_vencido_da_400(cliente, tmp_path, monkeypatch):
    id_, dep, _ = _sembrar_trabajo_reciente(tmp_path, monkeypatch)  # financiado, sin vencer
    assert cliente.post(f"/api/economia/bus/{id_}/cumplio", json={}).status_code == 400


def test_la_mesa_trae_por_juzgar_y_standing(cliente, tmp_path, monkeypatch):
    id_, dep, _ = _sembrar_trabajo_vencido(tmp_path, monkeypatch)
    data = cliente.get("/api/economia/bus").json()
    assert any(p["id"] == id_ for p in data["por_juzgar"])
    # tras juzgarlo, sale de por_juzgar y el standing sube
    cliente.post(f"/api/economia/bus/{id_}/cumplio", json={})
    data2 = cliente.get("/api/economia/bus").json()
    assert not any(p["id"] == id_ for p in data2["por_juzgar"])


def test_no_vencido_no_aparece_en_por_juzgar(cliente, tmp_path, monkeypatch):
    id_, dep, _ = _sembrar_trabajo_reciente(tmp_path, monkeypatch)
    data = cliente.get("/api/economia/bus").json()
    assert not any(p["id"] == id_ for p in data["por_juzgar"])


def test_la_fila_de_propuestas_trae_standing(cliente, tmp_path, monkeypatch):
    """El standing viaja en CADA fila de `propuestas`, no solo en
    `por_juzgar` -- Pedro lo tiene que ver antes de financiar de nuevo."""
    id_, dep, _ = _sembrar_trabajo_reciente(tmp_path, monkeypatch)
    data = cliente.get("/api/economia/bus").json()
    fila = next(p for p in data["propuestas"] if p["id"] == id_)
    assert fila["standing"] == {"cumplidas": 0, "total": 0}
    from calipso.plantel import promesas
    promesas.anotar(dep, "otro-id", None, True, "")
    data2 = cliente.get("/api/economia/bus").json()
    fila2 = next(p for p in data2["propuestas"] if p["id"] == id_)
    assert fila2["standing"] == {"cumplidas": 1, "total": 1}


def test_registro_de_promesas_corrupto_no_tumba_la_mesa(cliente, tmp_path,
                                                          monkeypatch):
    """El spec pide que la mesa DEGRADE ante un registro de promesas
    corrupto (a diferencia de los endpoints de juicio, que fallan cerrado):
    un GET sigue en 200 y el standing/por_juzgar de ese depto queda en
    blanco en vez de tumbar toda la mesa con un 500."""
    id_, dep, _ = _sembrar_trabajo_vencido(tmp_path, monkeypatch)
    ruta = tmp_path / "memoria" / "departamento" / dep / "promesas.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("{no es json", encoding="utf-8")

    r = cliente.get("/api/economia/bus")
    assert r.status_code == 200, r.text
    data = r.json()
    fila = next(p for p in data["propuestas"] if p["id"] == id_)
    assert fila["standing"] == {"cumplidas": 0, "total": 0}
    assert not any(p["id"] == id_ for p in data["por_juzgar"])


def test_endpoint_de_juicio_falla_cerrado_con_registro_corrupto(
        cliente, tmp_path, monkeypatch):
    """Gemelo del anterior, pero del lado de los endpoints de juicio: ahi el
    spec pide FALLAR CERRADO (400), no degradar -- lo contrario de la mesa,
    que es lectura pura."""
    id_, dep, _ = _sembrar_trabajo_vencido(tmp_path, monkeypatch)
    ruta = tmp_path / "memoria" / "departamento" / dep / "promesas.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("{no es json", encoding="utf-8")

    r = cliente.post(f"/api/economia/bus/{id_}/cumplio", json={})
    assert r.status_code == 400


def test_juzgar_no_toca_el_bus_ni_la_plata(cliente, tmp_path, monkeypatch):
    """Reputacion, no plata: el estado del bus y el saldo del departamento
    no cambian al juzgar."""
    id_, dep, _ = _sembrar_trabajo_vencido(tmp_path, monkeypatch)
    eco = tmp_path / "economia"
    antes_estado = Bus(eco / "bus.jsonl").estado(id_)
    antes_saldo = Kernel(Libro(eco / "libro.jsonl")).saldo("dep:atlas")

    r = cliente.post(f"/api/economia/bus/{id_}/cumplio", json={"palabras": "ok"})
    assert r.status_code == 200

    assert Bus(eco / "bus.jsonl").estado(id_) == antes_estado
    assert Kernel(Libro(eco / "libro.jsonl")).saldo("dep:atlas") == antes_saldo
