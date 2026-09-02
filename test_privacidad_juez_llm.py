import json
from calipso.privacidad import juez_llm


def test_parsea_los_tramos_de_una_respuesta_valida(monkeypatch):
    respuesta = {"response": json.dumps(
        {"tramos": [{"texto": "3865-4421", "tipo": "contacto"},
                    {"texto": "", "tipo": "salud"}]})}
    monkeypatch.setattr(juez_llm.dispatch, "_http_post_json",
                        lambda url, payload: respuesta)
    r = juez_llm.juzgar_llm("mi numero es 3865-4421")
    assert r["ok"] is True
    # descarta el tramo con texto vacio
    assert r["tramos"] == [{"texto": "3865-4421", "tipo": "contacto"}]


def test_manda_temperatura_0_y_format_json(monkeypatch):
    capturado = {}
    def fake(url, payload):
        capturado["payload"] = payload
        return {"response": '{"tramos": []}'}
    monkeypatch.setattr(juez_llm.dispatch, "_http_post_json", fake)
    juez_llm.juzgar_llm("hola")
    assert capturado["payload"]["format"] == "json"
    assert capturado["payload"]["options"]["temperature"] == 0
    assert capturado["payload"]["stream"] is False


def test_ollama_caido_da_ok_false(monkeypatch):
    def cae(url, payload):
        raise OSError("connection refused")
    monkeypatch.setattr(juez_llm.dispatch, "_http_post_json", cae)
    r = juez_llm.juzgar_llm("cualquier cosa")
    assert r["ok"] is False
    assert r["tramos"] == []


def test_respuesta_no_json_da_ok_false(monkeypatch):
    monkeypatch.setattr(juez_llm.dispatch, "_http_post_json",
                        lambda url, payload: {"response": "no soy json {{"})
    r = juez_llm.juzgar_llm("cualquier cosa")
    assert r["ok"] is False
