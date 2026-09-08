"""El turno /nube con modelo falso por TestClient (spec seccion 15, enmienda
2026-09-08): el contrato de nube viaja sin nombres; el bloque viaja tapado
con el mapa de la conversacion y se ve que viajo; una credencial en lo
pescado no aparece en ningun envio; solo hondo sigue sin bloque; los tramos
que vuelven a la nube son los crudos, no los repuestos; el bloque no se
persiste; el done es uno solo."""
import json

import calipso.server as srv
from calipso import chats
from calipso.abismo import contrato
from calipso.privacidad import juez
from test_abismo_chat import chat, de_tipo, texto_visible  # noqa: F401
from test_abismo_chat import _sembrar_chat_viejo
from test_abismo_suscripcion import cli_falso  # noqa: F401


def _juez_que_tapa_nombres(monkeypatch, con_credencial=False):
    """El juez de dos capas, doble: Marta y Ana son identidades (se tapan) y,
    si se pide, cualquier texto con `ghp_` es credencial (corta el envio)."""
    monkeypatch.setattr(juez.detector, "detectar_secretos",
                        lambda t: ([{"texto": "ghp_abcdef", "tipo": "credencial"}]
                                   if con_credencial and "ghp_" in t else []))
    monkeypatch.setattr(juez.juez_llm, "juzgar_llm",
                        lambda t: {"ok": True, "tramos": (
                            [{"texto": n, "tipo": "identidad"}
                             for n in ("Marta", "Ana") if n in t])})


def test_en_nube_el_bloque_viaja_tapado_con_el_mapa_del_mensaje_y_se_ve(chat, monkeypatch):
    _juez_que_tapa_nombres(monkeypatch)
    # el chat viejo nombra a Ana y NO a Marta: asi el marcador del bloque
    # solo puede salir del mapa que ya tapo el mensaje (ver abajo)
    _sembrar_chat_viejo(["con Ana hablamos del libro de cocina"])
    # historial previo del MISMO chat: sin el, `_history_messages` devolveria
    # [] igual y la asercion de "sin historial" seria vacua
    chats.append(chat.chat_id, "user", "hola")
    chats.append(chat.chat_id, "assistant", "hola Pedro")
    chat.modelo.guiones = [["Le dije a [ID_1] que ", "⟦abismo:chats libro⟧", " fin"],
                           ["y seguimos"]]
    eventos = chat.turno("/nube /api que hablamos con Marta y Ana del libro")
    tipos = [e["type"] for e in eventos]
    assert tipos.count("done") == 1
    tapado = [e for e in eventos if e["type"] == "privacidad"][0]
    assert tapado["action"] == "tapado"
    assert tapado["texto_tapado"] == "que hablamos con [ID_1] y [ID_2] del libro"
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "pescado"]
    viaje = abismo[1]["viaje"]
    assert viaje["destino"] == "nube"
    # el bloque se tapa con el MAPA DE LA CONVERSACION, el mismo que tapo el
    # mensaje: Ana ya es [ID_2] ahi (Marta se llevo el [ID_1]) y el bloque la
    # nombra con ese marcador. Con un mapa nuevo por consulta seria [ID_1] y
    # la nube leeria a Ana y a Marta como la misma persona
    assert viaje["tapados"] == [{"marcador": "[ID_2]", "tipo": "identidad"}]
    assert "Ana" not in viaje["texto_tapado"] and "[ID_2]" in viaje["texto_tapado"]
    # el segundo envio: system minimo + contrato SIN nombres + el bloque
    # tapado, sin historial (chat_id_nube=None) y con el mensaje tapado
    primera, segunda = chat.modelo.llamadas
    system2 = segunda["messages"][0]["content"]
    assert system2.startswith(srv._SISTEMA_NUBE_MINIMO)
    assert contrato.bloque_contrato(()) in system2
    assert "=== Lo que subio del abismo (fuente: chats) ===" in system2
    assert "Marta" not in json.dumps(chat.modelo.llamadas)
    assert "Ana" not in json.dumps(chat.modelo.llamadas)
    assert [m["role"] for m in segunda["messages"]] == ["system", "user"]
    assert segunda["messages"][1]["content"].startswith("que hablamos con [ID_1] y [ID_2] del libro")
    assert "Venias diciendo: Le dije a [ID_1] que " in segunda["messages"][1]["content"]
    # el bloque no se persiste ni se recuerda
    crudo = (chat.tmp / "chats.json").read_text(encoding="utf-8")
    assert "Lo que subio" not in crudo and "cocina" not in chat.mensajes()[-1]["text"]
    assert not any("Lo que subio" in r for r in chat.memoria.recordado)
    assert chat.telemetria("abismo")[0]["destino"] == "nube"


def test_en_nube_una_credencial_en_lo_pescado_no_sale_y_la_nube_sigue_sin_bloque(chat, monkeypatch):
    _juez_que_tapa_nombres(monkeypatch, con_credencial=True)
    _sembrar_chat_viejo(["el token del libro es ghp_abcdef no lo pierdas"])
    chat.modelo.guiones = [["Dejame ver ", "⟦abismo:chats libro⟧"], ["y sigo"]]
    eventos = chat.turno("/nube /api que libro tenia token")
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "fallo"]
    assert abismo[1]["motivo"] == "credencial"
    # la nube sigue sin el bloque: en las rutas en vivo eso es la reentrada
    # sin bloque (seccion 4 paso 4; ver el preambulo), o sea DOS llamadas, la
    # segunda sin el ENCABEZADO del bloque; y el secreto no aparece en NINGUN
    # envio ni en la telemetria. El encabezado entero (`=== Lo que subio del
    # abismo`) y no la frase suelta: el system de nube nombra el bloque en la
    # linea de los marcadores (`_NUBE_ABISMO_MARCADORES`), asi que buscar
    # "Lo que subio" a secas da positivo aunque no viaje nada
    assert len(chat.modelo.llamadas) == 2
    assert "ghp_" not in json.dumps(chat.modelo.llamadas)
    assert "=== Lo que subio del abismo" not in chat.modelo.llamadas[1]["messages"][0]["content"]
    assert texto_visible(eventos) == "Dejame ver y sigo"
    assert "ghp_" not in (chat.tmp / "telemetry.jsonl").read_text(encoding="utf-8")


def test_en_nube_solo_hondo_sigue_sin_bloque_y_sin_juez(chat, monkeypatch):
    def juez_solo_del_mensaje(texto):
        # la compuerta /nube del MENSAJE si lo llama (`preparar_envio`, en
        # hilo, ANTES de cualquier consulta): una bomba a secas reventaria
        # el turno sin `done`. Lo que no puede llegarle es el bloque
        # pescado: con solo anillo 3 el viaje lo descarta antes del juez. Si
        # llegara, esta asercion sube por el fallo cerrado del viaje como
        # `juez_local_caido` y la asercion del motivo, abajo, lo delata.
        assert "Lo que subio del abismo" not in texto, "con solo hondo el juez no corre"
        return {"tramos": [], "fallo_cerrado": False, "motivo": ""}
    monkeypatch.setattr(juez, "juzgar", juez_solo_del_mensaje)
    chat.memoria.core = "### perfil\n- Marta vive en Cordoba con Pedro\n"
    chat.modelo.guiones = [["a ⟦abismo:memoria donde vive Marta⟧"], ["b"]]
    eventos = chat.turno("/nube /api donde vive")
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "fallo"]
    assert abismo[1]["motivo"] == "solo_hondo"
    assert "Cordoba" not in json.dumps(chat.modelo.llamadas)
    # reentrada sin bloque (rutas en vivo): dos llamadas, la segunda sin el
    # encabezado del bloque (la frase suelta la trae el system de nube)
    assert len(chat.modelo.llamadas) == 2
    assert "=== Lo que subio del abismo" not in chat.modelo.llamadas[1]["messages"][0]["content"]
    assert texto_visible(eventos) == "a b"
    # la compuerta del mensaje corrio UNA vez: salteo 4 de la pasada sintetica
    assert len([e for e in eventos if e["type"] == "privacidad"]) == 1


def test_en_nube_por_suscripcion_los_tramos_vuelven_crudos(chat, cli_falso, monkeypatch):
    """El canario de la invariante 9: Pedro ve "Marta" (repuesto), la nube
    recibe "[ID_1]" (crudo) en el venias diciendo y en el bloque."""
    _juez_que_tapa_nombres(monkeypatch)
    _sembrar_chat_viejo(["con Marta hablamos del libro de cocina"])
    cli_falso.guion([{"partes": ["Le dije a [ID_1] que ⟦abismo:chats libro⟧ nada"], "pausa": 0},
                     {"partes": ["y seguimos"], "pausa": 0}])
    eventos = chat.turno("/nube /claude que hablamos con Marta del libro")
    assert texto_visible(eventos) == "Le dije a Marta que y seguimos"
    llamadas = cli_falso.llamadas()
    assert len(llamadas) == 2
    assert "Venias diciendo: Le dije a [ID_1] que " in llamadas[1]["prompt"]
    assert "[ID_1]" in llamadas[1]["sistema"] and "cocina" in llamadas[1]["sistema"]
    assert "Marta" not in json.dumps(llamadas)
    assert contrato.bloque_contrato(()) in llamadas[0]["sistema"]
    # lo persistido es lo repuesto que Pedro vio, sin bloque
    assert chat.mensajes()[-1]["text"] == "Le dije a Marta que y seguimos"
    assert "Lo que subio" not in (chat.tmp / "chats.json").read_text(encoding="utf-8")


def test_en_nube_por_suscripcion_un_bloque_que_no_viaja_no_reinvoca(chat, cli_falso, monkeypatch):
    """La letra exacta del 8.4, en la unica ruta donde el texto posterior
    existe: el viaje falla (credencial), no se reinvoca, lo que el CLI
    escribio despues de la marca vale, y el secreto no sale."""
    _juez_que_tapa_nombres(monkeypatch, con_credencial=True)
    _sembrar_chat_viejo(["el token del libro es ghp_abcdef"])
    cli_falso.guion([{"partes": ["Dejame ver ⟦abismo:chats libro⟧ y sigo sin el"], "pausa": 0}])
    eventos = chat.turno("/nube /claude que libro tenia token")
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "fallo"]
    assert abismo[1]["motivo"] == "credencial"
    assert texto_visible(eventos) == "Dejame ver  y sigo sin el"
    assert len(cli_falso.llamadas()) == 1
    assert "ghp_" not in json.dumps(cli_falso.llamadas())
    assert "ghp_" not in (chat.tmp / "telemetry.jsonl").read_text(encoding="utf-8")
