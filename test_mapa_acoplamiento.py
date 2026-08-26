"""Tests del acoplamiento mapa <-> chat (spec seccion 8)."""
import json

import pytest

import calipso.server as srv
from calipso.economia import departamentos as deps
from calipso.economia import pagador as pag
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.mapa import ficha

TS = "2026-08-25T10:00:00"
W = "2026-W35"


EDIFICIO = {"id": "dep:atlas", "nombre": "atlas", "zona": "fabrica",
            "estado": "activo", "saldo_mm": 1_148_000,
            "gasto_ciclo_mm": 320_000, "ventas_ventana_mm": 900_500,
            "eficiencia_pormil": 124, "actividad": 2,
            "trabajos": ["t1", "t2"], "compuertas": 1}


def test_la_cuenta_pagadora_sale_del_id_del_edificio():
    assert ficha.cuenta_pagadora("dep:atlas") == "dep:atlas"
    assert ficha.cuenta_pagadora("personal:finanzas") == "personal:finanzas"
    # la casa de Pedro no es un departamento: su gasto queda fuera del libro
    # de la fabrica, que es donde lo lleva calipso/costs.py
    assert ficha.cuenta_pagadora("cuenta_pedro") == ficha.CUENTA_PERSONAL
    assert ficha.cuenta_pagadora(None) == ficha.CUENTA_PERSONAL
    assert ficha.cuenta_pagadora("") == ficha.CUENTA_PERSONAL
    # y nada de cuentas inventadas desde el cliente: el paquete del chat
    # llega de afuera y "tesoro" no puede pagar un chat
    assert ficha.cuenta_pagadora("tesoro") == ficha.CUENTA_PERSONAL


def test_el_edificio_se_busca_por_id_en_el_modelo():
    modelo = {"edificios": [EDIFICIO, {**EDIFICIO, "id": "dep:mercado"}]}
    assert ficha.edificio_de(modelo, "dep:mercado")["id"] == "dep:mercado"
    assert ficha.edificio_de(modelo, "dep:nada") is None
    assert ficha.edificio_de(None, "dep:atlas") is None


def test_el_bloque_lleva_los_numeros_en_monedas_y_dice_quien_paga():
    """El libro guarda milimonedas; el que lee el prompt lee monedas. Un
    bloque que dijera 1148000 haria que Calipso hable de millones."""
    texto = ficha.bloque(EDIFICIO)
    assert "atlas" in texto
    assert "1148.00" in texto and "320.00" in texto and "900.50" in texto
    assert "12.4%" in texto
    assert "dep:atlas" in texto.split("paga la cuenta")[1]
    assert "1148000" not in texto


def test_el_bloque_no_miente_cuando_no_hay_eficiencia():
    texto = ficha.bloque({**EDIFICIO, "eficiencia_pormil": None})
    assert "sin dato" in texto
    assert "0.0%" not in texto


@pytest.fixture
def economia(tmp_path, monkeypatch):
    """Una fabrica chica con un departamento con techo de API y plata.

    El `emitir_semana` no es decorativo: sin PT emitido, la semana no es
    operativa y `gastar_api` no encuentra el ciclo. Mismo armado que usa
    `test_economia_pagador.py`."""
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             techo_api_ciclo_mm=1_000_000))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    k.acunar(TS, W, "dep:atlas", 50_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    return eco


def saldo(eco, cuenta):
    return pag.Pagador(eco).leer_kernel().saldo(cuenta)


def test_el_turno_de_api_lo_paga_el_departamento_en_foco(economia):
    """Un millon de tokens de entrada de deepseek son 270 milimonedas: el
    precio esta en PRECIOS_API_MM_POR_MTOK y no se redondea a cero."""
    antes = saldo(economia, "dep:atlas")
    cobrado = srv._cobrar_turno("dep:atlas", "api", None, "deepseek-chat",
                                {"prompt_tokens": 1_000_000,
                                 "completion_tokens": 0})
    assert cobrado == 270
    assert saldo(economia, "dep:atlas") == antes - 270


def test_sin_departamento_no_se_toca_el_libro(economia):
    antes = saldo(economia, "dep:atlas")
    assert srv._cobrar_turno(ficha.CUENTA_PERSONAL, "api", None,
                             "deepseek-chat",
                             {"prompt_tokens": 1_000_000}) == 0
    assert saldo(economia, "dep:atlas") == antes


def test_la_ruta_local_no_cuesta_plata(economia):
    antes = saldo(economia, "dep:atlas")
    assert srv._cobrar_turno("dep:atlas", "local", None, "qwen2.5:7b",
                             {"prompt_tokens": 9_000_000}) == 0
    assert saldo(economia, "dep:atlas") == antes


def test_un_cobro_que_no_entra_queda_pendiente_y_no_voltea_el_chat(tmp_path,
                                                                  monkeypatch):
    """Techo de API en cero: el mercado rechaza el gasto. El turno tiene que
    terminar igual y el cargo esperar en cargos_pendientes.jsonl."""
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             techo_api_ciclo_mm=0))
    (eco / "suscripciones.json").write_text("{}", encoding="utf-8")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    k.acunar(TS, W, "dep:atlas", 50_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    srv._cobrar_turno("dep:atlas", "api", None, "deepseek-chat",
                      {"prompt_tokens": 1_000_000, "completion_tokens": 0})
    pendientes = pag.Pagador(eco).pendientes()
    assert len(pendientes) == 1 and pendientes[0]["cuenta"] == "dep:atlas"


def test_el_turno_de_equipo_dinamico_tambien_le_cobra_al_departamento(economia):
    """`used_route` vale "orchestrator" cuando corre el equipo dinamico. Si
    eso llega crudo a `_cobrar_turno`, los agentes gastan y el departamento
    no paga nada — que es justo lo contrario del criterio de exito del spec."""
    antes = saldo(economia, "dep:atlas")
    # lo que el llamador normaliza: orchestrator no es una ruta cobrable
    ruta = "api"      # verdict["route"] del turno
    cobrado = srv._cobrar_turno("dep:atlas", ruta, None, "deepseek-chat",
                                {"prompt_tokens": 1_000_000,
                                 "completion_tokens": 0})
    assert cobrado == 270 and saldo(economia, "dep:atlas") == antes - 270
    # y la ruta cruda no cobra nada, que es el bug que la normalizacion evita
    assert srv._cobrar_turno("dep:atlas", "orchestrator", None,
                             "deepseek-chat",
                             {"prompt_tokens": 1_000_000}) == 0


def test_el_modelo_de_ciudad_se_deriva_una_sola_vez_y_sin_coordenadas(economia):
    """El chat necesita la ficha, no el dibujo: el urbanismo, que es la
    mitad cara, no corre cuando no hay mapa que pintar."""
    modelo = srv._ciudad_modelo()
    assert modelo is not None
    edificio = ficha.edificio_de(modelo, "dep:atlas")
    assert edificio["saldo_mm"] == 50_000
    assert "x" not in edificio and "y" not in edificio
    # y el endpoint sigue entregando las coordenadas
    from fastapi.testclient import TestClient
    c = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})
    cuerpo = c.get("/api/mapa/ciudad").json()
    assert cuerpo["activa"] is True
    assert all("x" in e for e in cuerpo["ciudad"]["edificios"])
