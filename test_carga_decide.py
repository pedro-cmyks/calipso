"""`_decide` bajo carga (spec 2026-09-11, 3.1 y 6): la carga se mide por el
hook `srv._medir_carga` (aca una Carga fija: nada toca /proc ni Ollama), los
probes se fijan con `_connector_health` (sin subprocess ni urlopen) y el
ranking es el REAL de capabilities sobre el registro por defecto. El prompt
que va local por capacidad con todo disponible es `traduce al ingles: hola`
(translate c1: local:qwen2.5:7b 1.06 primero; medido sobre el registro el
2026-09-11); `hola` a secas rankea opus primero y por eso no sirve para
"habria ido local".
"""
from __future__ import annotations

import pytest

import calipso.server as srv
from calipso import carga
from test_carga import medida

TRADUCE = "traduce al ingles: hola"
SALUD_TODA = {"local": {"ready": True}, "api": {"ready": False},
             "subscription": {"claude": {"ready": True}, "codex": {"ready": True}}}


_CONNECTOR_HEALTH_REAL = srv._connector_health     # para el test de la sonda cacheada


@pytest.fixture(autouse=True)
def _seco(monkeypatch, tmp_path):
    carga.olvidar()
    # el registro por defecto, sin overrides del home de la suite ni del repo
    monkeypatch.setattr(srv.capabilities, "CAP_FILE", tmp_path / "no-hay.json")
    monkeypatch.setattr(srv, "_connector_health", lambda use_cache=True: SALUD_TODA)
    monkeypatch.setattr(srv.sessions, "active", lambda: {"id": "s1", "agents": {}})
    monkeypatch.setattr(srv, "_medir_carga", lambda: medida("holgada"))
    yield
    carga.olvidar()


def _salud(monkeypatch, **partes):
    salud = {"local": dict(SALUD_TODA["local"]), "api": dict(SALUD_TODA["api"]),
             "subscription": {k: dict(v) for k, v in SALUD_TODA["subscription"].items()}}
    for k, v in partes.items():
        salud[k] = v
    monkeypatch.setattr(srv, "_connector_health", lambda use_cache=True: salud)


def _carga(monkeypatch, nivel, **campos):
    monkeypatch.setattr(srv, "_medir_carga", lambda: medida(nivel, **campos))


def _sin_nuevas(verdict):
    return {k: v for k, v in verdict.items() if k not in ("carga_medicion", "avail", "carga")}


# --- holgada: byte a byte ------------------------------------------------------

def test_holgada_decide_como_hoy_y_solo_suma_la_medicion_y_el_avail():
    verdict, features, ranked, d = srv._decide(TRADUCE)
    assert ranked[0]["key"] == "local:qwen2.5:7b"
    assert _sin_nuevas(verdict) == {
        "route": "local", "client": None, "model": "qwen2.5:7b", "model_id": "local:qwen2.5:7b",
        "persona": "Epicteto", "tier": "small", "effort": 0, "effort_name": "fast",
        "session": "s1", "source": "capabilities",
        "why": f"Epicteto (small) para translate c1 intensidad=fast (score {ranked[0]['score']})"}
    assert "carga" not in verdict
    assert verdict["carga_medicion"]["nivel"] == "holgada"
    assert verdict["avail"]["local:qwen2.5:7b"] is True
    assert carga.local_suspendido is False


# --- cargada -------------------------------------------------------------------

def test_cargada_manda_por_suscripcion_lo_que_iba_local_con_marca_y_suspende(monkeypatch):
    _carga(monkeypatch, "cargada", mem=480)
    verdict, _, ranked, _ = srv._decide(TRADUCE)
    assert verdict["route"] == "subscription" and ranked[0]["route"] == "subscription"
    assert verdict["carga"] == {"ruta": "subscription", "gesto": None, "motivo": None}
    assert verdict["carga_medicion"]["mem_disponible_mb"] == 480
    assert verdict["avail"]["local:qwen2.5:7b"] is False and verdict["avail"]["local:qwen2.5:3b"] is False
    assert "maquina cargada (480 MB libres: mem 480 < 5746): por suscripcion en vez de local" in verdict["why"]
    assert carga.local_suspendido is True


def test_cargada_no_marca_un_turno_que_ya_iba_por_suscripcion(monkeypatch):
    _carga(monkeypatch, "cargada")
    verdict, *_ = srv._decide("analiza esto")
    assert verdict["route"] == "subscription" and "carga" not in verdict
    assert verdict["avail"]["local:qwen2.5:7b"] is False     # los agentes locales del equipo igual se apagan
    assert carga.local_suspendido is False


def test_cargada_jamas_escala_a_la_api_paga(monkeypatch):
    _carga(monkeypatch, "cargada")
    _salud(monkeypatch, api={"ready": True}, subscription={"claude": {"ready": False}, "codex": {"ready": False}})
    verdict, *_ = srv._decide(TRADUCE)
    assert verdict["route"] == "local" and verdict["carga"]["gesto"] == "sin suscripcion"


def test_cargada_con_local_explicito_va_local_con_aviso_y_rompe_la_suspension(monkeypatch):
    _carga(monkeypatch, "cargada", mem=480)
    carga.suspender()
    verdict, *_ = srv._decide("/local " + TRADUCE)
    assert verdict["route"] == "local" and verdict["model"] == "qwen2.5:7b"
    assert verdict["carga"] == {"ruta": "local", "gesto": "/local", "motivo": None}
    assert verdict["why"].startswith("/local: local por construccion")
    assert "puede tardar o fallar" in verdict["why"]
    assert carga.local_suspendido is False


def test_cargada_con_prompt_privado_va_local_con_aviso(monkeypatch):
    _carga(monkeypatch, "cargada")
    verdict, features, *_ = srv._decide("esto es privado: mi clave del banco")
    assert features["private"] is True
    assert verdict["route"] == "local" and verdict["carga"]["gesto"] == "prompt privado"
    assert verdict["avail"]["local:qwen2.5:7b"] is True       # con gesto, los locales no se apagan


def test_cargada_sin_suscripcion_va_local_con_aviso(monkeypatch):
    _carga(monkeypatch, "cargada")
    _salud(monkeypatch, subscription={"claude": {"ready": False}, "codex": {"ready": False}})
    verdict, *_ = srv._decide(TRADUCE)
    assert verdict["route"] == "local" and verdict["carga"]["gesto"] == "sin suscripcion"


def test_cargada_con_force_model_local_va_local(monkeypatch):
    _carga(monkeypatch, "cargada")
    verdict, *_ = srv._decide("/model qwen2.5:7b " + TRADUCE)
    assert verdict["route"] == "local" and verdict["model_id"] == "local:qwen2.5:7b"
    assert verdict["carga"]["gesto"] == "/model qwen2.5:7b"


def test_redacta_y_otra_son_locales_por_construccion(monkeypatch):
    _carga(monkeypatch, "cargada")
    for gesto, texto in (("/redacta", "/redacta hola mariana, te escribo por lo del libro"), ("/otra", "/otra")):
        verdict, *_ = srv._decide(texto)
        assert verdict["route"] == "local" and verdict["carga"]["gesto"] == gesto, gesto
        assert verdict["why"].startswith(f"{gesto}: local por construccion")


# --- la histeresis ---------------------------------------------------------------

def test_suspendido_y_justa_sigue_por_suscripcion_y_holgada_lo_libera(monkeypatch):
    carga.suspender()
    _carga(monkeypatch, "justa", mem=6200)
    verdict, *_ = srv._decide(TRADUCE)
    assert verdict["route"] == "subscription"
    assert verdict["carga"] == {"ruta": "subscription", "gesto": None,
                                "motivo": "local suspendido hasta holgada"}
    # el sufijo de why dice el nivel REAL (justa), no "cargada"; el aviso de
    # la senal lo compone carga.marca con el mismo nivel (test_carga.py)
    assert "; maquina justa (6200 MB libres: local suspendido hasta holgada): por suscripcion en vez de local" in verdict["why"]
    assert carga.local_suspendido is True
    _carga(monkeypatch, "holgada")
    verdict, *_ = srv._decide(TRADUCE)
    assert verdict["route"] == "local" and "carga" not in verdict
    assert carga.local_suspendido is False


# --- /local cerrado de verdad (los cuatro caminos) --------------------------------

def test_local_con_model_local_respeta_el_modelo_forzado():
    """`/local /model qwen2.5:3b` elige el 3b hoy (ranking filtrado a local y
    luego `forced`): el veredicto directo no puede pisarlo con el configurado."""
    verdict, *_ = srv._decide("/local /model qwen2.5:3b " + TRADUCE)
    assert verdict["route"] == "local" and verdict["model"] == "qwen2.5:3b"
    assert verdict["model_id"] == "local:qwen2.5:3b"
    assert verdict["why"].startswith("/local: local por construccion")


def test_local_con_ollama_caido_sigue_siendo_local(monkeypatch):
    _salud(monkeypatch, local={"ready": False})
    verdict, *_ = srv._decide("/local " + TRADUCE)
    assert verdict["route"] == "local" and verdict["model_id"] == "local:qwen2.5:7b"


def test_local_con_complejidad_5_sigue_siendo_local(monkeypatch):
    real = srv.dispatch.extract_features
    monkeypatch.setattr(srv.dispatch, "extract_features", lambda t: dict(real(t), complexity=5))
    verdict, *_ = srv._decide("/local " + TRADUCE)
    assert verdict["route"] == "local"


def test_local_con_think_sigue_siendo_local():
    verdict, *_ = srv._decide("/local /think " + TRADUCE)
    assert verdict["route"] == "local" and verdict["effort_name"] == "think"


def test_local_con_la_salud_cacheada_en_false_sigue_siendo_local(monkeypatch):
    """La sonda lenta: `_http_up` de /api/tags pasado de 1,5 s deja `local`
    en False por 20 s aunque Ollama viva. Antes `/local` caia al ranking
    entero en silencio (test_porton_reentrada.py:34-36)."""
    monkeypatch.setattr(srv, "_connector_health", _CONNECTOR_HEALTH_REAL)   # la real, con las sondas dobladas
    monkeypatch.setattr(srv, "_http_up_cached", lambda url: False)
    monkeypatch.setattr(srv, "_probe_cached", lambda c: {"ready": True, "error": None})
    verdict, *_ = srv._decide("/local " + TRADUCE)
    assert verdict["route"] == "local"


# --- /model <local> cerrado como /local (ola de fix, punto 9) --------------------

def test_model_local_con_ollama_caido_sigue_siendo_local(monkeypatch):
    """`/model qwen2.5:7b` con la salud local en False caia al ranking
    entero y salia por suscripcion sin marca (verificado: haiku)."""
    _salud(monkeypatch, local={"ready": False})
    verdict, *_ = srv._decide("/model qwen2.5:7b " + TRADUCE)
    assert verdict["route"] == "local" and verdict["model_id"] == "local:qwen2.5:7b"
    assert verdict["why"].startswith("/model qwen2.5:7b: local por construccion")


def test_model_local_con_complejidad_5_sigue_siendo_local(monkeypatch):
    real = srv.dispatch.extract_features
    monkeypatch.setattr(srv.dispatch, "extract_features", lambda t: dict(real(t), complexity=5))
    verdict, *_ = srv._decide("/model qwen2.5:3b " + TRADUCE)
    assert verdict["route"] == "local" and verdict["model_id"] == "local:qwen2.5:3b"
    assert verdict["model"] == "qwen2.5:3b"


def test_model_local_con_think_sigue_siendo_local():
    verdict, *_ = srv._decide("/model qwen2.5:7b /think " + TRADUCE)
    assert verdict["route"] == "local" and verdict["effort_name"] == "think"


def test_model_local_no_rompe_la_suspension_ni_cambia_el_camino_de_suscripcion(monkeypatch):
    """Solo `/local` explicito libera la histeresis; `/model <local>` va
    local con aviso pero deja la suspension como esta. Y `/model` con un
    backend de suscripcion sigue por el ranking, como hoy."""
    _carga(monkeypatch, "cargada")
    carga.suspender()
    verdict, *_ = srv._decide("/model qwen2.5:7b " + TRADUCE)
    assert verdict["route"] == "local" and verdict["carga"]["gesto"] == "/model qwen2.5:7b"
    assert carga.local_suspendido is True
    verdict, *_ = srv._decide("/model sonnet " + TRADUCE)
    assert verdict["route"] == "subscription" and "carga" not in verdict
