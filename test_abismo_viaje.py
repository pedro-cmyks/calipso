"""La etapa de viaje en aislado (spec seccion 15, enmienda 2026-09-08)."""
import pytest

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


_DOBLE_DE_FUENTE = {"chats": "chats_viejos", "proyecto": "proyecto",
                    "memoria": "memoria"}


def _texto_del_resolvedor(monkeypatch, fuente, bloques):
    """El texto que arma el resolvedor DE VERDAD, con la fuente doblada."""
    from calipso.abismo import fuentes
    monkeypatch.setattr(fuentes, _DOBLE_DE_FUENTE[fuente], lambda *a, **k: bloques)
    return consulta.resolver(marca.Marca(fuente, "hola"))["texto"]


@pytest.mark.parametrize("fuente", ["chats", "proyecto", "memoria"])
def test_el_etiquetado_del_viaje_es_el_mismo_que_el_del_resolvedor(monkeypatch, fuente):
    """El custodio de que el modelo vea UN solo formato. Va con DOS
    sub-bloques y las TRES fuentes a proposito: con uno solo y una sola,
    un separador entre sub-bloques o un encabezado distinto por fuente
    divergian en verde."""
    bloques = BLOQUES[:2]
    assert viaje.etiquetar(fuente, bloques) == _texto_del_resolvedor(
        monkeypatch, fuente, bloques)


def test_el_etiquetado_recorta_el_techo_igual_que_el_resolvedor(monkeypatch):
    """El caso que cruza el techo: el recorte es del bloque ENTERO, no por
    sub-bloque, y es el mismo de los dos lados."""
    largo = "x" * consulta.ABISMO_BLOQUE_MAX
    largos = [(largo, anillos.MEDIA_AGUA), (largo, anillos.ORILLA)]
    texto = viaje.etiquetar("chats", largos)
    assert len(texto) == consulta.ABISMO_BLOQUE_MAX
    assert texto == _texto_del_resolvedor(monkeypatch, "chats", largos)


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


def test_una_credencial_no_viaja_a_ningun_destino_que_no_sea_local(monkeypatch):
    """Las dos politicas juntas (spec de la aduana, secciones 13 y 15.1):
    sin /nube el anillo 3 viaja (arriba, `test_destino_local_es_transparente...`)
    PERO una credencial falla cerrado el envio entero en TODO destino que no
    sea local (`afuera` = suscripcion o API sin /nube; `nube`), con el
    detector determinista de verdad y sin que el juez LLM corra. Al modelo
    local no se le corta nada: el spec lo exime."""
    def bomba(*a, **k):
        raise AssertionError("el juez LLM no debe correr")
    monkeypatch.setattr(juez.juez_llm, "juzgar_llm", bomba)
    con_credencial = BLOQUES + [("token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123",
                                 anillos.ORILLA)]
    for destino in ("afuera", "nube"):
        r = viaje.preparar_viaje(con_credencial, destino, MapaMarcadores(),
                                 fuente="chats")
        assert r == {"estado": "fallo", "texto": "", "tapados": [],
                     "motivo": "credencial"}, destino
    r = viaje.preparar_viaje(con_credencial, "local", MapaMarcadores(), fuente="chats")
    assert r["estado"] == "viaja" and "ghp_" in r["texto"]   # 15.1 exime al destino local


def test_afuera_la_credencial_la_corta_el_detector_no_el_juez(monkeypatch):
    """Con el juez de dos capas prohibido, destino `afuera` sigue fallando
    cerrado: es el detector solo, sin anillos ni juez. Y el anillo 3 sin
    llave sigue viajando afuera, entero (la otra mitad de la decision: "los
    modelos ven todo")."""
    _juez_prohibido(monkeypatch)
    hondo_con_llave = [("del core:\n- llave eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV",
                        anillos.HONDO)]
    r = viaje.preparar_viaje(hondo_con_llave, "afuera", MapaMarcadores())
    assert r["estado"] == "fallo" and r["motivo"] == "credencial"
    assert r["texto"] == ""
    r = viaje.preparar_viaje(BLOQUES[2:], "afuera", MapaMarcadores())
    assert r["estado"] == "viaja" and "[anillo 3]" in r["texto"] and r["tapados"] == []


def test_en_local_el_detector_no_corre_y_un_sha_no_corta(monkeypatch):
    """Lo que motivo el destino `afuera` (control negativo, pasa hoy y tiene
    que seguir pasando): el detector marca SHAs de commit, rutas con fecha
    y URLs largas (sondeado 2026-09-10). En local NO corre, porque el spec
    exime al modelo de la maquina y el abismo no puede quedar ciego en los
    turnos mas comunes de Pedro."""
    _juez_prohibido(monkeypatch)
    con_sha = [("del core:\n- el commit 3f2a9c1e4b7d6a5f8e9c0b1a2d3e4f5a6b7c8d9e rompio el login",
                anillos.HONDO)]
    r = viaje.preparar_viaje(con_sha, "local", MapaMarcadores())
    assert r["estado"] == "viaja" and "3f2a9c1e" in r["texto"]
