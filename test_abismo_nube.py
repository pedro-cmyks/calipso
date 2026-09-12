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


def _turno_con_un_solo_done(chat, texto):
    """`Harness.turno` mas la guarda del `done` unico (constraint global: un
    solo `done` por turno). `turno` ya sigue escuchando `DRENAJE` segundos
    despues del primer `done` (el buffer del socket de prueba no tiene tope y
    un duplicado saldria del mismo camino microsegundos despues), asi que la
    cuenta es sobre TODO lo que llego y no una guarda vacua."""
    eventos = chat.turno(texto)
    tipos = [e["type"] for e in eventos]
    assert tipos.count("done") == 1, f"un done de mas al final del turno: {tipos}"
    return eventos


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
    _sembrar_chat_viejo(["con Ana hablamos del libro de cocina el 20 de agosto"])
    # historial previo del MISMO chat: sin el, `_history_messages` devolveria
    # [] igual y la asercion de "sin historial" seria vacua
    chats.append(chat.chat_id, "user", "hola")
    chats.append(chat.chat_id, "assistant", "hola Pedro")
    chat.modelo.guiones = [["Le dije a [ID_1] que ", "⟦abismo:chats libro⟧", " fin"],
                           ["y seguimos: fue el 20 de agosto con [ID_2]"]]
    eventos = _turno_con_un_solo_done(chat, "/nube /api que hablamos con Marta y Ana del libro")
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
    # el canario del turno tapado: corre sobre el texto CRUDO ENTERO (los dos
    # tramos, con marcadores) contra el contexto tapado que viajo; los
    # marcadores no son hechos, la fecha que solo dijo el ultimo tramo ancla
    # en el bloque tapado y nada sale sin anclar
    v = de_tipo(eventos, "canario")[0]
    assert v["anclaje"]["tapado"] is True and v["anclaje"]["sin_anclaje"] == []
    assert not any("[ID_" in h["texto"] for h in v["anclaje"]["hechos"])
    assert [(h["texto"], h["fuentes"]) for h in v["anclaje"]["hechos"] if h["tipo"] == "fecha"] == [
        ("20 de agosto", ["bloque"])]
    assert [f["ruta"] for f in v["ventana"]] == ["api", "api"]
    assert v["ventana"][0]["num_ctx"] is None and v["ventana"][0]["recorte"] == []
    # api: se estima y se anota, no se juzga (decision 7): la pasada 1 se
    # corto en la marca antes del done ("sin medicion"); la 2 llego al done
    # con prompt_tokens=10 contra un system de cientos de tokens y aun asi
    # NO es "truncado" (None: sin techo no se compara)
    assert [f["truncado"] for f in v["ventana"]] == ["sin medicion", None]
    assert "cocina" not in json.dumps(v)
    assert segunda["messages"][1]["content"].startswith("que hablamos con [ID_1] y [ID_2] del libro")
    assert "Venias diciendo: Le dije a [ID_1] que " in segunda["messages"][1]["content"]
    # ni la marca ni el bloque se persisten, se recuerdan o se telemetrian
    crudo = (chat.tmp / "chats.json").read_text(encoding="utf-8")
    assert "Lo que subio" not in crudo and "cocina" not in chat.mensajes()[-1]["text"]
    assert "⟦" not in crudo
    assert not any("Lo que subio" in r for r in chat.memoria.recordado)
    tele = (chat.tmp / "telemetry.jsonl").read_text(encoding="utf-8")
    assert "cocina" not in tele and "Ana" not in tele
    assert chat.telemetria("abismo")[0]["destino"] == "nube"


def test_en_nube_un_turno_local_previo_de_la_misma_conversacion_no_viaja_por_el_bloque(chat, monkeypatch):
    """La sonda V1 del cierre (h04): la Fase 2a dejo la conversacion fuera de
    todo envio a la nube (chat_id_nube=None) y la fuente `chats` la volvia a
    meter por el bloque: un turno LOCAL previo del mismo chat viajaba,
    tapado solo por el juez. En /nube el chat activo entero queda fuera de
    la pesca; los otros chats viajan por el viaje, como siempre."""
    _juez_que_tapa_nombres(monkeypatch)
    _sembrar_chat_viejo(["con Ana hablamos del libro de recetas"])
    chats.append(chat.chat_id, "user", "el libro que me presto Marta es de cocina")
    chats.append(chat.chat_id, "assistant", "que bueno ese libro de Marta")
    chat.modelo.guiones = [["Dejame ver ", "⟦abismo:chats libro⟧"], ["y seguimos"]]
    eventos = _turno_con_un_solo_done(chat, "/nube /api que libro era")
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "pescado"]
    assert "recetas" in abismo[1]["viaje"]["texto_tapado"]
    assert "cocina" not in abismo[1]["viaje"]["texto_tapado"]
    envios = json.dumps(chat.modelo.llamadas)
    assert "recetas" in envios
    assert "presto" not in envios and "cocina" not in envios and "Marta" not in envios


def test_en_nube_una_credencial_en_lo_pescado_no_sale_y_la_nube_sigue_sin_bloque(chat, monkeypatch):
    _juez_que_tapa_nombres(monkeypatch, con_credencial=True)
    _sembrar_chat_viejo(["el token del libro es ghp_abcdef no lo pierdas"])
    chat.modelo.guiones = [["Dejame ver ", "⟦abismo:chats libro⟧"], ["y sigo"]]
    eventos = _turno_con_un_solo_done(chat, "/nube /api que libro tenia token")
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
    eventos = _turno_con_un_solo_done(chat, "/nube /api donde vive")
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
    eventos = _turno_con_un_solo_done(chat, "/nube /claude que hablamos con Marta del libro")
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


def test_en_nube_por_suscripcion_el_canario_no_ve_el_historial_que_no_viajo(chat, cli_falso, monkeypatch):
    """La contracara del anclaje contra el historial en suscripcion sin tapar
    (fix round 1 de la Task 5): tapado, la conversacion no viaja
    (chat_id_nube=None, Fase 2a) y el canario tampoco la ve. Un turno local
    previo del mismo chat no es fuente de anclaje ni entra al contexto que
    el desechable persiste: el hecho que solo estaba ahi sale
    `sin_anclaje`, no anclado en un historial que el CLI no recibio."""
    _juez_que_tapa_nombres(monkeypatch)
    monkeypatch.setenv("CANARIOS_PERSISTIR_CONTEXTO", "1")
    chats.append(chat.chat_id, "user", "el libro que me presto Marta es de cocina, de Paula Ortiz")
    chats.append(chat.chat_id, "assistant", "que bueno ese libro de Marta")
    cli_falso.guion([{"partes": ["Le dije a [ID_1] que el libro es de Paula Ortiz"], "pausa": 0}])
    eventos = _turno_con_un_solo_done(chat, "/nube /claude que libro me presto Marta")
    assert texto_visible(eventos) == "Le dije a Marta que el libro es de Paula Ortiz"
    llamadas = cli_falso.llamadas()
    assert len(llamadas) == 1 and "Conversaci" not in llamadas[0]["prompt"]
    assert "cocina" not in json.dumps(llamadas) and "Marta" not in json.dumps(llamadas)
    fila = chat.telemetria("chat_turn")[0]
    assert fila["contexto"]["historial"] == []
    a = fila["canarios"]["anclaje"]
    assert a["tapado"] is True
    assert [(h["tipo"], h["texto"]) for h in a["sin_anclaje"]] == [("nombre", "Paula Ortiz")]
    assert not any("historial" in f for h in a["hechos"] for f in h["fuentes"])


def test_en_nube_por_suscripcion_reponer_no_le_da_al_filtro_una_marca_que_el_detector_no_vio(chat, cli_falso, monkeypatch):
    """S11b del cierre (h01): el detector juzga el texto CRUDO (161 chars de
    cuerpo con cinco [ID_1]: ilegible por largo) pero lo visible pasa por
    `reponer` ANTES del filtro y el cuerpo queda en 156: el filtro la tomaba
    por valida y cortaba solo, tragando el resto sin rastro. En one-shot el
    filtro no corta: la retira con aviso y lo posterior vale."""
    _juez_que_tapa_nombres(monkeypatch)
    _sembrar_chat_viejo(["con Marta hablamos del libro"])
    cuerpo_crudo = "chats " + "x" * 120 + " [ID_1]" * 5
    assert len(cuerpo_crudo) == 161
    cli_falso.guion([{"partes": ["Le dije ⟦abismo:" + cuerpo_crudo + "⟧ y esto sigue"], "pausa": 0},
                     {"partes": ["NO deberia reinvocar"], "pausa": 0}])
    eventos = _turno_con_un_solo_done(chat, "/nube /claude que hablamos con Marta del libro")
    assert de_tipo(eventos, "abismo") == []
    assert texto_visible(eventos) == "Le dije  y esto sigue"
    assert len(cli_falso.llamadas()) == 1
    assert [f["clase"] for f in chat.telemetria("abismo")] == ["sin_corte"]


def test_en_nube_por_suscripcion_un_bloque_que_no_viaja_no_reinvoca(chat, cli_falso, monkeypatch):
    """La letra exacta del 8.4, en la unica ruta donde el texto posterior
    existe: el viaje falla (credencial), no se reinvoca, lo que el CLI
    escribio despues de la marca vale, y el secreto no sale."""
    _juez_que_tapa_nombres(monkeypatch, con_credencial=True)
    _sembrar_chat_viejo(["el token del libro es ghp_abcdef"])
    cli_falso.guion([{"partes": ["Dejame ver ⟦abismo:chats libro⟧ y sigo sin el"], "pausa": 0}])
    eventos = _turno_con_un_solo_done(chat, "/nube /claude que libro tenia token")
    abismo = de_tipo(eventos, "abismo")
    assert [a["fase"] for a in abismo] == ["pondering", "fallo"]
    assert abismo[1]["motivo"] == "credencial"
    assert texto_visible(eventos) == "Dejame ver  y sigo sin el"
    assert len(cli_falso.llamadas()) == 1
    assert "ghp_" not in json.dumps(cli_falso.llamadas())
    assert "ghp_" not in (chat.tmp / "telemetry.jsonl").read_text(encoding="utf-8")
