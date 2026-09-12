"""El turno bajo carga por el harness de ws (spec 2026-09-11, 3.2 y 6): la
senal `carga` ANTES del primer chunk, `meta.carga` en chats.json, el aviso
FUERA de `full` (ni en el texto visible, ni en el mensaje guardado, ni en el
episodio de memoria, ni en la respuesta que ve el canario), el fallback a
local bajo cargada con su aviso, /redacta con la senal, y el contador de uso
alrededor del turno local. `_decide` es el falso del harness: la decision
viaja por VEREDICTO_EXTRA (test_abismo_chat.py).
"""
from __future__ import annotations

import json

import pytest

import calipso.server as srv
import test_abismo_chat
from calipso import carga
from test_abismo_chat import chat, de_tipo, texto_visible, ModeloEspia  # noqa: F401
from test_abismo_suscripcion import cli_falso  # noqa: F401
from test_carga import medida

MEDICION_CARGADA = carga.fila(medida("cargada", mem=480))
AVISO_LOCAL = "maquina cargada (480 MB libres): /local es local, puede tardar o fallar"


@pytest.fixture(autouse=True)
def _contador_limpio():
    carga.olvidar()
    yield
    carga.olvidar()


def _extra(monkeypatch, **campos):
    monkeypatch.setattr(test_abismo_chat, "VEREDICTO_EXTRA", dict(campos))


def _indices(eventos):
    return {t: [i for i, e in enumerate(eventos) if e.get("type") == t] for t in ("meta", "carga", "chunk", "done")}


def test_la_senal_carga_llega_antes_del_primer_chunk_y_meta_carga_queda(chat, monkeypatch):
    _extra(monkeypatch, carga={"ruta": "local", "gesto": "/local", "motivo": None},
           carga_medicion=MEDICION_CARGADA)
    eventos = chat.turno("/local hola")
    idx = _indices(eventos)
    assert len(idx["carga"]) == 1 and idx["meta"][0] < idx["carga"][0] < idx["chunk"][0]
    senal = de_tipo(eventos, "carga")[0]
    assert senal == {"type": "carga", "nivel": "cargada", "mem_disponible_mb": 480,
                     "motivo": "mem 480 < 5746", "ruta": "local", "gesto": "/local", "aviso": AVISO_LOCAL}
    meta = chat.mensajes()[-1]["meta"]
    assert meta["carga"] == {k: v for k, v in senal.items() if k != "type"}
    assert meta["route"] == "local"
    fila = chat.telemetria("carga")[0]
    assert fila["accion"] == "local_con_aviso" and fila["gesto"] == "/local" and fila["chat"] == chat.chat_id
    assert fila["mem_disponible_mb"] == 480 and fila["necesidad_mb"] == 5746


def test_el_aviso_no_entra_en_full_ni_en_la_memoria_ni_en_el_canario(chat, monkeypatch):
    """Invariante 7: falla si el aviso entra en `full`, en el episodio de
    memoria o en `respuesta` del canario."""
    _extra(monkeypatch, carga={"ruta": "local", "gesto": "/local", "motivo": None},
           carga_medicion=MEDICION_CARGADA)
    vistos = {}
    real = srv._veredicto_del_turno

    async def espia(**campos):
        vistos["respuesta"] = campos["respuesta"]
        return await real(**campos)
    monkeypatch.setattr(srv, "_veredicto_del_turno", espia)
    eventos = chat.turno("/local hola")
    assert texto_visible(eventos) == "hola Pedro"
    assert chat.mensajes()[-1]["text"] == "hola Pedro"
    assert chat.memoria.recordado[-1] == "Pedro pregunto: hola\nCalipso respondio: hola Pedro"
    assert vistos["respuesta"] == "hola Pedro"
    # la fila chat_turn NO se asserta limpia: en produccion `why` lleva el
    # sufijo "; maquina cargada (...)" a proposito (decision 7: llega al
    # modelo por _harness_context y a chat_turn) y la invariante 7 no habla
    # de telemetria. Lo que si: el aviso no vive en la fila como clave propia
    fila = chat.telemetria("chat_turn")[0]
    assert "aviso" not in fila and "carga" not in fila
    assert fila["response_chars"] == len("hola Pedro")


def test_bajo_cargada_por_suscripcion_la_marca_dice_la_persona(chat, cli_falso, monkeypatch):
    _extra(monkeypatch, route="subscription", client="claude", model="claude-sonnet",
           model_id="subscription:claude:sonnet", persona="Mariana",
           carga={"ruta": "subscription", "gesto": None, "motivo": None},
           carga_medicion=MEDICION_CARGADA)
    cli_falso.guion([{"partes": ["Hola desde la nube"]}])
    eventos = chat.turno("hola")
    senal = de_tipo(eventos, "carga")[0]
    assert senal["aviso"] == "maquina cargada (480 MB libres): contesto por Mariana"
    assert senal["ruta"] == "subscription" and senal["gesto"] is None
    assert texto_visible(eventos) == "Hola desde la nube"
    assert chat.mensajes()[-1]["meta"]["route"] == "subscription"
    assert chat.mensajes()[-1]["meta"]["carga"]["aviso"].endswith("contesto por Mariana")
    assert chat.telemetria("carga")[0]["accion"] == "suscripcion"
    assert carga.en_uso == 0


def test_el_fallo_cerrado_del_juez_de_nube_bajo_cargada_avisa_local(chat, monkeypatch):
    """Gesto local por construccion que _decide no ve (spec 3.1, invariante
    2): el veredicto iba por suscripcion por capacidad (sin marca) y el juez
    de /nube cierra en local. El turno contesta local bajo carga: senal
    {ruta: local, gesto: fallo cerrado del juez} antes del primer chunk,
    meta.carga y fila local_con_aviso; sin suspender nada."""
    _extra(monkeypatch, route="subscription", client="claude", model="claude-sonnet",
           model_id="subscription:claude:sonnet", persona="Mariana",
           carga_medicion=MEDICION_CARGADA)
    monkeypatch.setattr(srv.privacidad_nube, "preparar_envio",
                        lambda texto, mapa: {"accion": "local", "motivo": "credencial"})
    eventos = chat.turno("/nube analiza esto")
    idx = _indices(eventos)
    assert len(idx["carga"]) == 1 and idx["meta"][0] < idx["carga"][0] < idx["chunk"][0]
    senal = de_tipo(eventos, "carga")[0]
    assert senal["ruta"] == "local" and senal["gesto"] == "fallo cerrado del juez"
    assert senal["aviso"] == "maquina cargada (480 MB libres): fallo cerrado del juez es local, puede tardar o fallar"
    assert [e["action"] for e in de_tipo(eventos, "privacidad")] == ["local"]
    assert texto_visible(eventos) == "hola Pedro"
    meta = chat.mensajes()[-1]["meta"]
    assert meta["route"] == "local" and meta["carga"]["gesto"] == "fallo cerrado del juez"
    assert chat.telemetria("carga")[0]["accion"] == "local_con_aviso"
    assert carga.local_suspendido is False and carga.en_uso == 0


def test_un_turno_holgado_no_lleva_senal_ni_meta_carga(chat, monkeypatch):
    _extra(monkeypatch, carga_medicion=carga.fila(medida("holgada")))
    eventos = chat.turno("hola")
    assert de_tipo(eventos, "carga") == []
    assert "carga" not in chat.mensajes()[-1]["meta"]
    assert chat.telemetria("carga") == []


def test_el_fallback_a_local_bajo_cargada_avisa_y_la_meta_dice_local(chat, cli_falso, monkeypatch):
    _extra(monkeypatch, route="subscription", client="claude", model="claude-sonnet",
           model_id="subscription:claude:sonnet", persona="Mariana",
           carga={"ruta": "subscription", "gesto": None, "motivo": None},
           carga_medicion=MEDICION_CARGADA)
    cli_falso.guion([{"partes": [], "stderr": "caido", "exit": 1}])
    monkeypatch.setattr(srv, "_best_subscription_client", lambda p: None)
    chat.modelo.guiones = [["respuesta local"]]
    eventos = chat.turno("hola")
    assert [m.get("note") for m in de_tipo(eventos, "meta")] == [None, "fallback a local"]
    senales = de_tipo(eventos, "carga")
    assert [s["ruta"] for s in senales] == ["subscription", "local"]
    assert senales[1]["aviso"] == "maquina cargada (480 MB libres): fallback es local, puede tardar o fallar"
    assert texto_visible(eventos) == "respuesta local"
    meta = chat.mensajes()[-1]["meta"]
    assert meta["route"] == "local" and meta["carga"]["ruta"] == "local" and meta["carga"]["gesto"] == "fallback"
    assert [f["accion"] for f in chat.telemetria("carga")] == ["suscripcion", "local_con_aviso"]


def test_redacta_bajo_cargada_avisa_por_senal_y_no_persiste_turno(chat, monkeypatch):
    _extra(monkeypatch, carga={"ruta": "local", "gesto": "/redacta", "motivo": None},
           carga_medicion=MEDICION_CARGADA)
    # el borrador en si no es lo que se prueba: system y user fijos
    monkeypatch.setattr(srv.compositor_redactor, "preparar_borrador",
                        lambda pedido, chats_, ejemplos: ("SYSTEM BORRADOR", pedido))
    antes = len(chat.mensajes())
    eventos = chat.turno("/redacta contale a mariana que el libro me gusto")
    tipos = [e["type"] for e in eventos]
    assert tipos.index("carga") < tipos.index("borrador") < tipos.index("chunk")
    assert de_tipo(eventos, "carga")[0]["aviso"] == "maquina cargada (480 MB libres): /redacta es local, puede tardar o fallar"
    assert len(chat.mensajes()) == antes + 1           # solo el de Pedro
    assert chat.telemetria("carga")[0]["accion"] == "local_con_aviso"
    assert carga.en_uso == 0


def test_el_turno_local_corre_con_el_contador_tomado_y_lo_suelta(chat, monkeypatch):
    class Mirando(ModeloEspia):
        def __call__(self, url, payload, *resto):
            self.visto = carga.en_uso
            return super().__call__(url, payload, *resto)
    modelo = Mirando([["hola ", "Pedro"]])
    monkeypatch.setattr(srv.dispatch, "_ollama_chat_chunks", modelo)
    chat.turno("hola")
    assert modelo.visto == 1 and carga.en_uso == 0
