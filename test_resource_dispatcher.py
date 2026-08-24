"""Tests del dispatcher consciente de recursos."""
import pytest

from calipso import resource_dispatcher as rd


def _snap(available_mb: int, installed: list[str], loaded: list | None = None):
    """Snapshot sintetico: sin tocar /proc ni Ollama."""
    return rd.ResourceSnapshot(
        mem={"total_mb": 11_642, "available_mb": available_mb,
             "used_mb": 11_642 - available_mb, "swap_used_mb": 0},
        cpu_load=0.1,
        loaded_models=loaded or [],
        installed_models=installed,
    )


# ---------------------------------------------------------------------------
# _smaller_model
# ---------------------------------------------------------------------------

def test_smaller_model_solo_elige_modelos_instalados():
    """No sirve bajar a un modelo que Ollama no tiene: daria 404 al ejecutar."""
    installed = ["qwen2.5:3b", "qwen2.5:7b"]
    got = rd._smaller_model("qwen2.5:32b", available_mb=9_000, installed=installed)
    assert got in installed
    assert got == "qwen2.5:7b"  # el mas grande que cabe y esta instalado


def test_smaller_model_devuelve_none_si_nada_instalado_cabe():
    """Con un solo modelo instalado y sin RAM para el, no hay downgrade posible."""
    got = rd._smaller_model("qwen2.5:32b", available_mb=3_500,
                            installed=["qwen2.5:7b"])
    assert got is None


def test_smaller_model_nunca_elige_modelo_de_embeddings():
    """bge-m3 cabe en RAM pero no sabe chatear: no es un downgrade valido."""
    got = rd._smaller_model("qwen2.5:32b", available_mb=4_000,
                            installed=["bge-m3", "qwen2.5:7b"])
    assert got != "bge-m3"
    assert got is None


def test_smaller_model_nunca_devuelve_el_mismo_modelo():
    got = rd._smaller_model("qwen2.5:7b", available_mb=9_000,
                            installed=["qwen2.5:7b"])
    assert got is None


# ---------------------------------------------------------------------------
# gate()
# ---------------------------------------------------------------------------

def test_gate_downgrade_respeta_lo_instalado():
    """El bug original: gate bajaba a gemma2:9b sin tenerlo instalado."""
    snap = _snap(9_000, installed=["qwen2.5:3b", "qwen2.5:7b"])
    dec = rd.gate("qwen2.5:32b", route="local", snap=snap)
    assert dec.action == "downgrade"
    assert dec.model == "qwen2.5:7b"
    assert dec.route == "local"


def test_gate_reroute_cuando_no_hay_downgrade_instalado():
    """Sin alternativa local instalada, la tarea sale a la ruta de fallback."""
    snap = _snap(4_000, installed=["qwen2.5:7b"])
    dec = rd.gate("qwen2.5:32b", route="local",
                  fallback_route="subscription", snap=snap)
    assert dec.action == "reroute"
    assert dec.route == "subscription"
    assert dec.model is None


def test_gate_run_cuando_sobra_ram():
    snap = _snap(9_000, installed=["qwen2.5:7b"])
    dec = rd.gate("qwen2.5:7b", route="local", snap=snap)
    assert dec.action == "run"
    assert dec.model == "qwen2.5:7b"


def test_gate_reroute_bajo_ram_critica():
    snap = _snap(2_000, installed=["qwen2.5:3b"])
    dec = rd.gate("qwen2.5:3b", route="local", snap=snap)
    assert dec.action == "reroute"
    assert dec.route == "subscription"


def test_gate_no_restringe_rutas_no_locales():
    dec = rd.gate("claude-opus-5", route="subscription", snap=_snap(500, []))
    assert dec.action == "run"
    assert dec.route == "subscription"


def test_gate_evict_then_run_libera_ram_de_modelos_cargados():
    """Con un modelo ocupando RAM, desalojarlo alcanza para correr el pedido."""
    snap = _snap(3_500, installed=["qwen2.5:7b"],
                 loaded=[{"name": "qwen2.5:3b", "size_mb": 2_500}])
    dec = rd.gate("qwen2.5:7b", route="local", snap=snap)
    assert dec.action == "evict_then_run"
    assert dec.model == "qwen2.5:7b"


# ---------------------------------------------------------------------------
# model_ram_mb
# ---------------------------------------------------------------------------

def test_model_ram_mb_conoce_los_modelos_de_la_tabla():
    assert rd.model_ram_mb("qwen2.5:7b") == 5_500


def test_model_ram_mb_estima_por_parametros_si_no_conoce_el_modelo():
    """Un modelo desconocido de 8B se estima, no cae al default de 5 GB."""
    est = rd.model_ram_mb("modelo-raro:8b")
    assert 5_000 <= est <= 7_000


# ---------------------------------------------------------------------------
# ResourceSnapshot / diagnose sobre el sistema real
# ---------------------------------------------------------------------------

def test_snapshot_real_lee_memoria_del_sistema():
    snap = rd.ResourceSnapshot.take()
    assert snap.mem["total_mb"] > 0
    assert 0 <= snap.available_mb <= snap.mem["total_mb"]


def test_diagnose_devuelve_nivel_conocido():
    d = rd.diagnose()
    assert d["level"] in {"ok", "caution", "warning", "critical"}
    assert d["summary"]
