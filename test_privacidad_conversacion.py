from calipso.privacidad import conversacion
from calipso.privacidad.redaccion import MapaMarcadores


def test_mismo_chat_id_mismo_mapa():
    m1 = conversacion.mapa_para("chat-1")
    m2 = conversacion.mapa_para("chat-1")
    assert m1 is m2
    assert isinstance(m1, MapaMarcadores)


def test_chat_ids_distintos_mapas_distintos():
    assert conversacion.mapa_para("chat-a") is not conversacion.mapa_para("chat-b")


def test_none_no_cachea():
    assert conversacion.mapa_para(None) is not conversacion.mapa_para(None)


def test_olvidar_libera():
    m1 = conversacion.mapa_para("chat-x")
    conversacion.olvidar("chat-x")
    assert conversacion.mapa_para("chat-x") is not m1
