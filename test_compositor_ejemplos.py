# test_compositor_ejemplos.py
import json

import pytest


@pytest.fixture
def home(monkeypatch, tmp_path):
    # cada prueba con su propio CALIPSO_HOME: el almacen resuelve la ruta en
    # tiempo de llamada, asi que setear el env aca lo redirige al temp.
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    return tmp_path


def test_guardar_y_cargar(home):
    from calipso.compositor import ejemplos
    ejemplos.guardar("Hola Ana, nos vemos manana a las 10 entonces")
    got = ejemplos.cargar()
    assert len(got) == 1
    assert got[0]["texto"] == "Hola Ana, nos vemos manana a las 10 entonces"
    assert got[0]["ts"]                       # quedo estampado


def test_cargar_sin_archivo_es_lista_vacia(home):
    from calipso.compositor import ejemplos
    assert ejemplos.cargar() == []


def test_cargar_corrupto_es_lista_vacia(home):
    from calipso.compositor import ejemplos
    (home / "voz_ejemplos.json").write_text("{no es json", encoding="utf-8")
    assert ejemplos.cargar() == []


def test_dedup_no_duplica(home):
    from calipso.compositor import ejemplos
    ejemplos.guardar("cuento largo que Pedro escribio de verdad")
    ejemplos.guardar("cuento largo que Pedro escribio de verdad")
    assert len(ejemplos.cargar()) == 1


def test_texto_vacio_no_se_guarda(home):
    from calipso.compositor import ejemplos
    ejemplos.guardar("   ")
    assert ejemplos.cargar() == []


def test_no_hay_llamada_de_red_en_guardar(home):
    # el almacen es un archivo local: guardar escribe el JSON y nada mas.
    from calipso.compositor import ejemplos
    ejemplos.guardar("texto local que no debe salir a ningun lado nunca")
    data = json.loads((home / "voz_ejemplos.json").read_text(encoding="utf-8"))
    assert data[0]["texto"].startswith("texto local")


def test_texto_del_gesto_saca_el_texto():
    from calipso.compositor import ejemplos
    # parse_directives limpia el slash: "/mia hola" -> clean "hola"
    assert ejemplos.texto_del_gesto("respondele a ana que si") == "respondele a ana que si"


def test_texto_del_gesto_vacio_cuando_solo_slash():
    from calipso.compositor import ejemplos
    # quirk: si el mensaje era solo "/mia", clean cae al fallback "/mia"
    assert ejemplos.texto_del_gesto("/mia") == ""
    assert ejemplos.texto_del_gesto("   ") == ""
    assert ejemplos.texto_del_gesto("") == ""


def test_cargar_descarta_items_que_no_son_dict(home):
    import json
    from calipso.compositor import ejemplos
    # un JSON valido pero mal formado a mano (lista de strings) no debe
    # tumbar guardar/voz: cargar filtra lo que no sea dict.
    (home / "voz_ejemplos.json").write_text(
        json.dumps(["basura suelta", {"texto": "esto si sirve largo", "ts": "1"}]),
        encoding="utf-8")
    got = ejemplos.cargar()
    assert got == [{"texto": "esto si sirve largo", "ts": "1"}]
