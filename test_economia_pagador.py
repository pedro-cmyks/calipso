# test_economia_pagador.py
"""Tests del pagador: el adaptador entre dispatch y la economia."""
import json
import pytest

from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import pagador as pag
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"
W = "2026-W35"


@pytest.fixture
def base(tmp_path):
    eco = tmp_path / "economia"
    eco.mkdir()
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("mercadeo", deps.ZONA_FABRICA,
                             techo_api_ciclo_mm=500_000))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    k.acunar(TS, W, "dep:mercadeo", 100_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    return tmp_path


def test_desde_entorno_inactivo_sin_archivos(tmp_path):
    assert pag.Pagador.desde_entorno(tmp_path) is None


def test_cargar_api_por_tokens(base):
    p = pag.Pagador.desde_entorno(base)
    mm = p.cargar_api(TS, W, "dep:mercadeo", "deepseek-chat",
                      prompt_tokens=100_000, completion_tokens=50_000)
    assert mm == 82  # ceil((100k*270 + 50k*1100) / 1M)
    assert p.leer_kernel().saldo("dep:mercadeo") == 100_000 - 82


def test_cero_tokens_no_genera_cargo(base):
    p = pag.Pagador.desde_entorno(base)
    assert p.cargar_api(TS, W, "dep:mercadeo", "deepseek-chat", 0, 0) == 0
    assert p.pendientes() == []
    assert p.leer_kernel().saldo("dep:mercadeo") == 100_000


def test_cargar_api_de_trabajo_resuelve_dueno(base):
    from calipso.economia import bus as bus_mod
    b = bus_mod.Bus(base / "economia" / "bus.jsonl")
    b.alta(TS, W, "p1", "dep:mercadeo", "radar", 10_000, 20_000,
           {"gasto_max_mm": 50_000})
    Kernel(Libro(base / "economia" / "libro.jsonl")).transferir(
        TS, W, "dep:mercadeo", "trabajo:p1", 1_000, motivo="financiacion")
    p = pag.Pagador.desde_entorno(base)
    p.cargar_api(TS, W, "trabajo:p1", "deepseek-chat", 1_000_000, 0)  # 270 mm
    assert p.pendientes() == []
    assert p.leer_kernel().saldo("trabajo:p1") == 1_000 - 270


def test_cuenta_personal_no_carga_api(base):
    p = pag.Pagador.desde_entorno(base)
    assert p.cargar_api(TS, W, "personal", "deepseek-chat", 1000, 1000) is None
    assert p.leer_kernel().saldo("dep:mercadeo") == 100_000


def test_cargar_suscripcion_por_unidad(base):
    p = pag.Pagador.desde_entorno(base)
    p.cargar_suscripcion(TS, W, "dep:mercadeo", "claude_max")
    # 1 unidad a precio base 100
    assert p.leer_kernel().saldo(t.DIRECCION) == 100
    p.cargar_suscripcion(TS, W, "personal", "claude_max")
    asientos = p.leer_kernel().libro.asientos()
    assert cap.consumo_personal(asientos, "claude_max", [W]) == 1


def test_fallo_economico_degrada_a_pendiente(base):
    p = pag.Pagador.desde_entorno(base)
    # semana no operativa: el cargo no puede aplicarse -> pendiente
    p.cargar_suscripcion(TS, "2026-W99", "dep:mercadeo", "claude_max")
    assert len(p.pendientes()) == 1
    assert p.leer_kernel().saldo(t.DIRECCION) == 0
    # el reintento re-aplica con la semana ORIGINAL del cargo, que sigue
    # sin ser operativa: queda pendiente
    assert p.reintentar_pendientes() == 0
    assert len(p.pendientes()) == 1


def test_reintento_aplica_cuando_puede(base):
    p = pag.Pagador.desde_entorno(base)
    # techo agotado -> pendiente; al reintentar con techo ampliado, pasa
    registro = deps.Registro(base / "economia" / "departamentos.json")
    registro.ajustar("mercadeo", techo_api_ciclo_mm=10)
    p.cargar_api(TS, W, "dep:mercadeo", "deepseek-chat", 100_000, 50_000)
    assert len(p.pendientes()) == 1
    registro.ajustar("mercadeo", techo_api_ciclo_mm=500_000)
    assert p.reintentar_pendientes() == 1  # el mercado fresco ve el ajuste
    assert p.pendientes() == []
    assert p.leer_kernel().saldo("dep:mercadeo") == 100_000 - 82


def test_el_cliente_se_traduce_a_la_suscripcion_que_existe():
    """dispatch.py tenia esta traduccion copiada a mano; dos verdades para
    un solo dato es como se desincronizan."""
    from calipso.economia.pagador import suscripcion_de_cliente
    assert suscripcion_de_cliente("claude") == "claude_max"
    assert suscripcion_de_cliente("codex") == "chatgpt_plus"
    assert suscripcion_de_cliente("CLAUDE") == "claude_max"
    assert suscripcion_de_cliente(None) == "claude_max"
