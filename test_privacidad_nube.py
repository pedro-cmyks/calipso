from calipso.privacidad import nube
from calipso.privacidad.redaccion import MapaMarcadores


def _mock_juez(monkeypatch, veredicto):
    monkeypatch.setattr(nube.juez, "juzgar", lambda t: veredicto)


def test_fallo_cerrado_se_queda_local(monkeypatch):
    _mock_juez(monkeypatch, {"tramos": [], "fallo_cerrado": True, "motivo": "credencial"})
    d = nube.preparar_envio("subo esta clave?", MapaMarcadores())
    assert d["accion"] == "local"
    assert d["motivo"] == "credencial"
    assert d["texto"] is None


def test_humano_se_redacta_para_la_nube(monkeypatch):
    _mock_juez(monkeypatch, {"tramos": [{"texto": "3865-4421", "tipo": "contacto"}],
                             "fallo_cerrado": False, "motivo": ""})
    d = nube.preparar_envio("mi numero es 3865-4421, buscame vuelos", MapaMarcadores())
    assert d["accion"] == "nube"
    assert "3865-4421" not in d["texto"]           # el valor real no viaja
    assert "[CONTACTO_1]" in d["texto"]
    assert d["tapados"] == [{"marcador": "[CONTACTO_1]", "tipo": "contacto"}]


def test_nada_sensible_viaja_igual(monkeypatch):
    _mock_juez(monkeypatch, {"tramos": [], "fallo_cerrado": False, "motivo": ""})
    d = nube.preparar_envio("me explicas las tuplas?", MapaMarcadores())
    assert d["accion"] == "nube"
    assert d["texto"] == "me explicas las tuplas?"
    assert d["tapados"] == []
