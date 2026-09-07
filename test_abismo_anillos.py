"""La frontera determinista por profundidad (spec seccion 6)."""
from calipso.abismo import anillos


def test_pisos_por_fuente():
    assert anillos.piso("proyecto") == anillos.ORILLA
    assert anillos.piso("chats") == anillos.MEDIA_AGUA
    assert anillos.piso("memoria") == anillos.MEDIA_AGUA


def test_fuente_desconocida_cae_a_lo_hondo():
    # Fallo cerrado: lo que no se conoce se trata como lo mas delicado.
    assert anillos.piso("fondo") == anillos.HONDO


def test_solo_el_chat_pregunta_en_esta_rebanada():
    for a in (anillos.ORILLA, anillos.MEDIA_AGUA, anillos.HONDO):
        assert anillos.puede_preguntar(a, "chat") is True
        assert anillos.puede_preguntar(a, "jefe") is False
        assert anillos.puede_preguntar(a, "lector") is False


def test_a_la_nube_no_viaja_nada_en_esta_rebanada():
    # La politica (anillo 3 jamas, 1-2 redactados) es de rebanadas futuras;
    # aca la consulta no corre en /nube, asi que el viaje a nube es False
    # para TODO anillo (spec seccion 8).
    for a in (anillos.ORILLA, anillos.MEDIA_AGUA, anillos.HONDO):
        assert anillos.puede_viajar(a, "local") is True
        assert anillos.puede_viajar(a, "nube") is False
