"""El vigia dentro del tick de las rutinas (spec 2026-09-11, 3.3, rulings
9.11 y 9.12): mide en el to_thread, evicta SOLO lo que /api/ps de ESA
medicion listo, SOLO modelos de Calipso, SOLO con en_uso == 0; suspende el
local tras la descarga; anota todo en telemetria; un fallo del vigia no se
lleva las rutinas; y las pospuestas de run_due dejan su fila. Ollama es un
hook: `srv._ollama_evict` espiado, `srv._medir_carga` fijo."""
from __future__ import annotations

import datetime

import pytest

import calipso.server as srv
from calipso import carga
from calipso import routines as calipso_routines
from test_carga import medida

AHORA = datetime.datetime(2026, 9, 11, 19, 0, 0)


@pytest.fixture
def tick(monkeypatch, tmp_path):
    carga.olvidar()
    monkeypatch.setattr(calipso_routines, "CALIPSO_HOME", tmp_path)
    for r in calipso_routines.load():
        calipso_routines.update(r["id"], {"enabled": False})
    filas = []
    monkeypatch.setattr(srv.telemetry, "log_event", lambda kind, **k: filas.append({"kind": kind, **k}))
    evictados = []
    monkeypatch.setattr(srv, "_ollama_evict", lambda modelo: evictados.append(modelo) or True)

    def correr(m, handlers=None):
        monkeypatch.setattr(srv, "_medir_carga", lambda: m)
        return srv._tick_con_carga(AHORA, handlers or {})
    yield {"filas": filas, "evictados": evictados, "correr": correr}
    carga.olvidar()


def _de(filas, accion):
    return [f for f in filas if f["kind"] == "carga" and f.get("accion") == accion]


def test_cargada_con_el_7b_listado_y_sin_uso_lo_descarga_una_vez_y_suspende(tick):
    tick["correr"](medida("cargada", modelos=["qwen2.5:7b"]))
    assert tick["evictados"] == ["qwen2.5:7b"]
    assert carga.local_suspendido is True
    fila = _de(tick["filas"], "descarga")[0]
    assert fila["modelo"] == "qwen2.5:7b" and fila["ok"] is True
    assert fila["nivel"] == "cargada" and fila["mem_disponible_mb"] == 480


def test_con_el_7b_cargado_en_reposo_no_descarga_y_en_el_oom_si(tick):
    """Ola de fix, punto 1: la memoria efectiva cuenta el modelo cargado. (a)
    2709 libres con el 7b listado (5203) es holgada efectiva: el vigia NO
    evicta (antes descargaba el 7b a los 60 s de cada turno local). (b) el
    OOM: 500 + 5203 = 5703 < 5746 -> cargada -> descarga y suspende."""
    tick["correr"](medida("holgada", mem=2709, modelos=["qwen2.5:7b"], modelo_cargado_mb=5203))
    assert tick["evictados"] == [] and carga.local_suspendido is False
    assert _de(tick["filas"], "descarga") == []
    oom = medida("cargada", mem=500, modelos=["qwen2.5:7b"], modelo_cargado_mb=5203,
                 motivo="mem efectiva 5703 < 5746")
    assert oom.mem_efectiva_mb == 5703
    tick["correr"](oom)
    assert tick["evictados"] == ["qwen2.5:7b"] and carga.local_suspendido is True
    fila = _de(tick["filas"], "descarga")[0]
    assert fila["mem_disponible_mb"] == 500 and fila["mem_efectiva_mb"] == 5703


def test_con_el_modelo_en_uso_no_descarga_y_lo_anota(tick):
    carga.tomar()
    tick["correr"](medida("cargada", modelos=["qwen2.5:7b"]))
    assert tick["evictados"] == [] and carga.local_suspendido is False
    assert _de(tick["filas"], "descarga_diferida")[0]["en_uso"] == 1
    carga.soltar()


def test_un_evict_que_falla_no_suspende_y_deja_descarga_fallida(tick, monkeypatch):
    monkeypatch.setattr(srv, "_ollama_evict", lambda modelo: False)
    descargados = srv._vigia_del_modelo(medida("cargada", modelos=["qwen2.5:7b"]))
    assert descargados == [] and carga.local_suspendido is False
    assert _de(tick["filas"], "descarga") == []
    fila = _de(tick["filas"], "descarga_fallida")[0]
    assert fila["modelo"] == "qwen2.5:7b" and fila["ok"] is False and fila["nivel"] == "cargada"


def test_jamas_evicta_lo_que_no_vio_cargado_ni_lo_que_no_es_de_calipso(tick):
    tick["correr"](medida("cargada", modelos=[]))                 # nada listado: nada
    tick["correr"](medida("cargada", modelos=["llama3:8b"]))      # ajeno: nada
    assert tick["evictados"] == [] and _de(tick["filas"], "descarga") == []


def test_los_tres_modelos_de_calipso_son_los_de_config_y_el_de_vision(monkeypatch):
    assert srv._modelos_de_calipso() == {srv.dispatch.CONFIG["local"]["model"],
                                         srv.dispatch.CONFIG["classifier"]["model"]}
    monkeypatch.setattr(srv.attachments, "ollama_vision_model", lambda: "moondream")
    assert "moondream" in srv._modelos_de_calipso()


def test_medir_carga_del_server_pasa_los_modelos_de_calipso_como_propios(monkeypatch):
    """La memoria efectiva suma SOLO lo que el vigia puede descargar (punto
    1): el server mide con `modelos_propios=_modelos_de_calipso()`."""
    vistos = {}

    def medir(modelo, **k):
        vistos["modelo"], vistos["k"] = modelo, k
        return medida("holgada")
    monkeypatch.setattr(carga, "medir", medir)
    srv._medir_carga()
    assert vistos["modelo"] == srv.dispatch.CONFIG["local"]["model"]
    assert vistos["k"]["modelos_propios"] == srv._modelos_de_calipso()


def test_bajo_holgada_o_justa_el_vigia_no_toca_nada(tick):
    tick["correr"](medida("holgada", modelos=["qwen2.5:7b"]))
    tick["correr"](medida("justa", modelos=["qwen2.5:7b"]))
    assert tick["evictados"] == [] and carga.local_suspendido is False


def test_una_medicion_que_revienta_no_se_lleva_las_rutinas_y_deja_vigia_error(tick, monkeypatch):
    """Fail-open en el tick (ola de fix, punto 4): `_medir_carga()` estaba
    fuera del try y si levantaba, el ticker se lo tragaba y NINGUNA rutina
    corria, en silencio. Ahora: fila `vigia_error` con el error y las
    rutinas corren sin nivel (como hoy)."""
    def revienta():
        raise AttributeError("'list' object has no attribute 'get'")
    monkeypatch.setattr(srv, "_medir_carga", revienta)
    rt = calipso_routines.add("catastro", "cat", 60, enabled=True)
    corridas = []
    ran = srv._tick_con_carga(AHORA, {"catastro": lambda r: corridas.append(r["id"])})
    assert corridas == [rt["id"]]
    assert ran == [{"id": rt["id"], "kind": "catastro", "status": "ok"}]
    fila = _de(tick["filas"], "vigia_error")[0]
    assert "'list' object" in fila["error"] and "nivel" not in fila
    assert tick["evictados"] == [] and _de(tick["filas"], "pospone") == []


def test_un_vigia_que_revienta_no_se_lleva_las_rutinas_y_las_pospuestas_dejan_fila(tick, monkeypatch):
    def revienta(modelo):
        raise RuntimeError("ollama colgado")
    monkeypatch.setattr(srv, "_ollama_evict", revienta)
    rt = calipso_routines.add("catastro", "cat", 60, enabled=True)
    corridas = []
    ran = tick["correr"](medida("cargada", modelos=["qwen2.5:7b"]),
                         {"catastro": lambda r: corridas.append(r["id"])})
    assert corridas == []                                   # pospuesta: no corrio
    assert _de(tick["filas"], "vigia_error")[0]["error"] == "ollama colgado"
    assert ran == [{"id": rt["id"], "kind": "catastro", "status": calipso_routines.POSPUESTA}]
    pos = _de(tick["filas"], "pospone")[0]
    assert pos["rutina"] == "catastro" and pos["rutina_id"] == rt["id"] and pos["nivel"] == "cargada"
    assert calipso_routines.get(rt["id"])["last_run"] is None
