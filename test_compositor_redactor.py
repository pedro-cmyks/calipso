# test_compositor_redactor.py
from calipso.compositor.redactor import construir_prompt


def test_el_system_lleva_los_ejemplos_y_la_instruccion():
    system, user = construir_prompt("respondele esto", ["che como va", "todo piola"])
    assert "che como va" in system and "todo piola" in system   # los ejemplos
    assert "voz" in system.lower()                              # la instruccion de voz
    # infiere responder-vs-desde-cero e instruye SOLO el borrador
    assert "solo" in system.lower() or "sin preambulo" in system.lower()
    assert user == "respondele esto"


def test_sin_ejemplos_igual_arma_prompt():
    system, user = construir_prompt("decile a ana que no llego", [])
    assert isinstance(system, str) and system
    assert user == "decile a ana que no llego"
    # sin ejemplos, el system lo dice (no inventa una voz falsa)
    assert "sin ejemplos" in system.lower() or "no hay ejemplos" in system.lower()
