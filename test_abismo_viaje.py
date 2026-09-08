"""La etapa de viaje en aislado (spec seccion 15, enmienda 2026-09-08)."""
from calipso.abismo import anillos, consulta, marca, viaje
from calipso.privacidad import juez
from calipso.privacidad.redaccion import MapaMarcadores


def _juez(monkeypatch, secretos, llm):
    """El molde de test_privacidad_juez.py: detector y LLM dobles."""
    monkeypatch.setattr(juez.detector, "detectar_secretos", lambda t: secretos)
    monkeypatch.setattr(juez.juez_llm, "juzgar_llm", lambda t: llm)


def _juez_prohibido(monkeypatch):
    def bomba(*a, **k):
        raise AssertionError("el juez no debe correr")
    monkeypatch.setattr(juez, "juzgar", bomba)


BLOQUES = [("proyecto calipso:\nbrief", anillos.ORILLA),
           ("[t 2026-08-01] hola Marta", anillos.MEDIA_AGUA),
           ("del core:\n- vive en Cordoba", anillos.HONDO)]


def test_destino_local_es_transparente_y_no_corre_el_juez(monkeypatch):
    _juez_prohibido(monkeypatch)
    r = viaje.preparar_viaje(BLOQUES, "local", MapaMarcadores(), fuente="memoria")
    assert r["estado"] == "viaja" and r["tapados"] == [] and r["motivo"] == ""
    assert "vive en Cordoba" in r["texto"] and "[anillo 3]" in r["texto"]
    assert r["texto"].startswith("=== Lo que subio del abismo (fuente: memoria) ===")


def test_el_etiquetado_del_viaje_es_el_mismo_que_el_del_resolvedor(monkeypatch):
    from calipso.abismo import fuentes
    monkeypatch.setattr(fuentes, "chats_viejos", lambda resto: BLOQUES[1:2])
    r = consulta.resolver(marca.Marca("chats", "hola"))
    assert viaje.etiquetar("chats", BLOQUES[1:2]) == r["texto"]


def test_el_etiquetado_respeta_el_techo():
    largo = [("x" * 5000, anillos.MEDIA_AGUA)]
    assert len(viaje.etiquetar("chats", largo)) <= consulta.ABISMO_BLOQUE_MAX


def test_a_la_nube_lo_hondo_se_descarta_antes_del_juez(monkeypatch):
    visto = {}

    def juzgar(texto):
        visto["texto"] = texto
        return {"tramos": [], "fallo_cerrado": False, "motivo": ""}
    monkeypatch.setattr(juez, "juzgar", juzgar)
    r = viaje.preparar_viaje(BLOQUES, "nube", MapaMarcadores(), fuente="memoria")
    assert r["estado"] == "viaja"
    assert "Cordoba" not in visto["texto"] and "Cordoba" not in r["texto"]
    assert "[anillo 1]" in r["texto"] and "[anillo 2]" in r["texto"]


def test_solo_hondo_falla_cerrado_sin_juez(monkeypatch):
    _juez_prohibido(monkeypatch)
    r = viaje.preparar_viaje(BLOQUES[2:], "nube", MapaMarcadores())
    assert r == {"estado": "fallo", "texto": "", "tapados": [], "motivo": "solo_hondo"}


def test_credencial_en_cualquier_sub_bloque_falla_cerrado_el_envio_entero(monkeypatch):
    _juez(monkeypatch, [{"texto": "ghp_xxx", "tipo": "credencial"}], {"tramos": [], "ok": True})
    r = viaje.preparar_viaje(BLOQUES, "nube", MapaMarcadores())
    assert r["estado"] == "fallo" and r["motivo"] == "credencial"
    assert r["texto"] == "" and r["tapados"] == []


def test_juez_caido_y_tipo_desconocido_fallan_cerrado(monkeypatch):
    _juez(monkeypatch, [], {"tramos": [], "ok": False})
    assert viaje.preparar_viaje(BLOQUES, "nube", MapaMarcadores())["motivo"] == "juez_local_caido"
    _juez(monkeypatch, [], {"tramos": [{"texto": "sertralina", "tipo": "medicamento"}], "ok": True})
    assert viaje.preparar_viaje(BLOQUES, "nube", MapaMarcadores())["motivo"] == "tipo_desconocido"


def test_un_juez_que_revienta_es_fallo_cerrado(monkeypatch):
    def bomba(texto):
        raise RuntimeError("ollama se cayo")
    monkeypatch.setattr(juez, "juzgar", bomba)
    assert viaje.preparar_viaje(BLOQUES, "nube", MapaMarcadores())["motivo"] == "juez_local_caido"


def test_lo_humano_se_tapa_con_el_mapa_compartido_de_la_conversacion(monkeypatch):
    _juez(monkeypatch, [], {"tramos": [{"texto": "Marta", "tipo": "identidad"}], "ok": True})
    mapa = MapaMarcadores()
    marcador_del_mensaje = mapa.marcador_para("Marta", "identidad")   # ya tapada en el mensaje
    r = viaje.preparar_viaje(BLOQUES, "nube", mapa, fuente="chats")
    assert r["estado"] == "viaja"
    assert "Marta" not in r["texto"] and marcador_del_mensaje in r["texto"]
    assert r["tapados"] == [{"marcador": marcador_del_mensaje, "tipo": "identidad"}]
    # el reponer de siempre restaura la misma persona
    assert mapa.reponer_texto(r["texto"]).count("Marta") == 1


def test_sin_bloques_es_vacio(monkeypatch):
    _juez_prohibido(monkeypatch)
    assert viaje.preparar_viaje([("  ", 1)], "nube", MapaMarcadores())["motivo"] == "vacio"
