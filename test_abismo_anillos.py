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


def test_a_la_nube_viajan_la_orilla_y_media_agua_y_lo_hondo_jamas():
    # enmienda 2026-09-08: la columna "Viaje a la nube" ya no es politica
    # futura. Local deja pasar todo; nube deja 1 y 2 (redactados despues
    # por el juez, en viaje.py) y el 3 nunca, ni tapado.
    for a in (anillos.ORILLA, anillos.MEDIA_AGUA, anillos.HONDO):
        assert anillos.puede_viajar(a, "local") is True
    assert anillos.puede_viajar(anillos.ORILLA, "nube") is True
    assert anillos.puede_viajar(anillos.MEDIA_AGUA, "nube") is True
    assert anillos.puede_viajar(anillos.HONDO, "nube") is False
    assert anillos.puede_viajar(anillos.ORILLA, "marte") is False   # fallo cerrado
