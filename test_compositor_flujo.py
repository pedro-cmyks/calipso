# test_compositor_flujo.py -- el lazo completo del gesto, sin el websocket:
# Pedro trae su version final con /mia, y un /redacta posterior la usa.
import pytest


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    return tmp_path


def test_mia_alimenta_el_borrador(home):
    from calipso.compositor import ejemplos, redactor
    # el chat sacaria el texto del gesto y lo guardaria:
    texto = ejemplos.texto_del_gesto("Hola Ana, quedamos manana a las 10 entonces")
    assert texto
    ejemplos.guardar(texto)
    # un /redacta posterior carga los guardados y los mete en el system:
    system, user = redactor.preparar_borrador(
        "decile a luis que confirmo", {"active": None, "chats": {}},
        ejemplos.cargar())
    assert "Hola Ana, quedamos manana a las 10 entonces" in system
    assert user == "decile a luis que confirmo"


def test_mia_solo_slash_no_guarda_nada(home):
    from calipso.compositor import ejemplos
    texto = ejemplos.texto_del_gesto("/mia")   # el quirk del fallback
    assert texto == ""
    # el chat, al ver texto vacio, no llama a guardar: el almacen sigue vacio.
    assert ejemplos.cargar() == []
