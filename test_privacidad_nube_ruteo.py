"""Unit tests de `nube.ruteo_para_nube`: la logica pura de ruteo del gesto
`/nube`, sin WebSocket ni servidor (eso lo prueba `test_chat_live.py` a mano
contra el servidor corriendo)."""
from calipso.privacidad import nube


def test_accion_local_fuerza_local_y_corta_nube():
    dec = {"accion": "local", "texto": None, "tapados": [], "motivo": "credencial"}
    r = nube.ruteo_para_nube(dec, "subscription", None)
    assert r == {"route": "local", "nube_local": True, "mensaje": None}


def test_accion_nube_con_route_local_sin_force_sube_a_subscription():
    dec = {"accion": "nube", "texto": "hola [CONTACTO_1]",
           "tapados": [{"marcador": "[CONTACTO_1]", "tipo": "contacto"}], "motivo": ""}
    r = nube.ruteo_para_nube(dec, "local", None)
    assert r["route"] == "subscription"
    assert r["nube_local"] is False
    assert r["mensaje"] == dec["texto"]


def test_accion_nube_con_route_ya_forzada_respeta_api():
    dec = {"accion": "nube", "texto": "hola", "tapados": [], "motivo": ""}
    r = nube.ruteo_para_nube(dec, "api", "api")
    assert r["route"] == "api"
    assert r["nube_local"] is False
    assert r["mensaje"] == dec["texto"]


def test_accion_nube_con_route_local_pero_force_route_no_sube():
    # Pedro forzo /local a proposito: no lo pisa aunque el juez diga nube.
    dec = {"accion": "nube", "texto": "hola", "tapados": [], "motivo": ""}
    r = nube.ruteo_para_nube(dec, "local", "local")
    assert r["route"] == "local"
    assert r["nube_local"] is False
    assert r["mensaje"] == dec["texto"]
