from calipso.privacidad import juez


def _mock(monkeypatch, secretos, llm):
    monkeypatch.setattr(juez.detector, "detectar_secretos", lambda t: secretos)
    monkeypatch.setattr(juez.juez_llm, "juzgar_llm", lambda t: llm)


def test_credencial_del_detector_falla_cerrado(monkeypatch):
    _mock(monkeypatch,
          [{"texto": "ghp_xxx", "tipo": "credencial"}],
          {"tramos": [], "ok": True})
    v = juez.juzgar("subo esto ghp_xxx?")
    assert v["fallo_cerrado"] is True
    assert v["motivo"] == "credencial"
    assert v["tramos"] == []   # no se redacta una credencial: se corta


def test_credencial_que_marca_el_llm_tambien_falla_cerrado(monkeypatch):
    _mock(monkeypatch, [],
          {"tramos": [{"texto": "hunter2", "tipo": "credencial"}], "ok": True})
    v = juez.juzgar("mi pass es hunter2")
    assert v["fallo_cerrado"] is True
    assert v["motivo"] == "credencial"
    assert v["tramos"] == []


def test_llm_caido_falla_cerrado(monkeypatch):
    _mock(monkeypatch, [], {"tramos": [], "ok": False})
    v = juez.juzgar("cualquier cosa")
    assert v["fallo_cerrado"] is True
    assert v["motivo"] == "juez_local_caido"
    assert v["tramos"] == []


def test_tipo_desconocido_del_llm_falla_cerrado(monkeypatch):
    # el LLM marco un tramo sensible pero con un tipo fuera de las seis
    # categorias conocidas (ej: el 7b etiqueta salud como "medicamento
    # recetado"): no sabemos si es credencial o lenguaje humano, asi que
    # no se descarta en silencio -> fallo cerrado.
    _mock(monkeypatch, [],
          {"tramos": [{"texto": "sertralina 50mg", "tipo": "medicamento recetado"}],
           "ok": True})
    v = juez.juzgar("tomo sertralina 50mg")
    assert v["fallo_cerrado"] is True
    assert v["motivo"] == "tipo_desconocido"
    assert v["tramos"] == []


def test_tipo_vacio_del_llm_falla_cerrado(monkeypatch):
    _mock(monkeypatch, [],
          {"tramos": [{"texto": "sertralina 50mg", "tipo": ""}], "ok": True})
    v = juez.juzgar("tomo sertralina 50mg")
    assert v["fallo_cerrado"] is True
    assert v["motivo"] == "tipo_desconocido"
    assert v["tramos"] == []


def test_lenguaje_humano_se_redacta_no_falla_cerrado(monkeypatch):
    _mock(monkeypatch, [],
          {"tramos": [{"texto": "3865-4421", "tipo": "contacto"},
                      {"texto": "lupus", "tipo": "salud"}], "ok": True})
    v = juez.juzgar("mi numero es 3865-4421 y tengo lupus")
    assert v["fallo_cerrado"] is False
    assert v["motivo"] == ""
    assert {"texto": "3865-4421", "tipo": "contacto"} in v["tramos"]
    assert {"texto": "lupus", "tipo": "salud"} in v["tramos"]


def test_sin_nada_sensible_no_falla_y_sin_tramos(monkeypatch):
    _mock(monkeypatch, [], {"tramos": [], "ok": True})
    v = juez.juzgar("me explicas las tuplas?")
    assert v == {"tramos": [], "fallo_cerrado": False, "motivo": ""}
