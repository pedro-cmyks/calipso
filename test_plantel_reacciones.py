# test_plantel_reacciones.py
import json

import pytest


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    return tmp_path


def _forma(sobre="el radar de precios", promete="medir", tarda="corto"):
    from calipso.plantel import ficha
    return {"sobre": sobre, "clave": ficha.normalizar(sobre),
            "promete": promete, "tarda": tarda}


def test_anotar_y_leer(home):
    from calipso.plantel import reacciones
    reacciones.anotar("taller", "descarto", _forma(), "muy caro", "taller-1")
    got = reacciones.leer("taller")
    assert len(got) == 1
    assert got[0]["reaccion"] == "descarto"
    assert got[0]["palabras"] == "muy caro"
    assert got[0]["forma"]["clave"] == _forma()["clave"]
    assert got[0]["ts"]


def test_leer_sin_archivo_es_lista_vacia(home):
    from calipso.plantel import reacciones
    assert reacciones.leer("taller") == []


def test_leer_corrupto_levanta(home):
    from calipso.plantel import reacciones
    ruta = home / "memoria" / "departamento" / "taller" / "reacciones.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("{no es json", encoding="utf-8")
    with pytest.raises(reacciones.ErrorReacciones):
        reacciones.leer("taller")


def test_leer_no_lista_levanta(home):
    from calipso.plantel import reacciones
    ruta = home / "memoria" / "departamento" / "taller" / "reacciones.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text('{"reaccion": "descarto"}', encoding="utf-8")
    with pytest.raises(reacciones.ErrorReacciones):
        reacciones.leer("taller")


def test_reaccion_desconocida_levanta(home):
    from calipso.plantel import reacciones
    with pytest.raises(reacciones.ErrorReacciones):
        reacciones.anotar("taller", "meh", _forma(), "", "taller-1")


def test_esta_vetada_solo_con_no_mas_y_misma_clave(home):
    from calipso.plantel import reacciones
    f = _forma()
    lista = [
        {"reaccion": "descarto", "forma": f, "palabras": "", "propuesta_id": "a"},
        {"reaccion": "no_mas", "forma": f, "palabras": "no", "propuesta_id": "b"},
    ]
    assert reacciones.esta_vetada(lista, f["clave"]) is True
    # una clave distinta no esta vetada
    assert reacciones.esta_vetada(lista, "otra+cosa") is False
    # un descarto (blando) NO es un veto
    solo_descarto = [{"reaccion": "descarto", "forma": f, "palabras": "", "propuesta_id": "a"}]
    assert reacciones.esta_vetada(solo_descarto, f["clave"]) is False


def test_no_usa_write_text_pelado(home):
    # el registro va por el escritor atomico compartido: tras anotar existe el
    # json final y NO queda ningun .tmp tirado.
    from calipso.plantel import reacciones
    reacciones.anotar("taller", "no_mas", _forma(), "no mas", "taller-1")
    dir_dep = home / "memoria" / "departamento" / "taller"
    nombres = [p.name for p in dir_dep.iterdir()]
    assert "reacciones.json" in nombres
    assert not any(n.startswith("reacciones.json.tmp") for n in nombres)


def test_no_importa_memory():
    # jefe.py lee este registro y se cuida de no arrastrar chromadb; el modulo
    # no puede importar calipso.memory (que importa chromadb en el tope).
    import ast
    import pathlib
    src = pathlib.Path("calipso/plantel/reacciones.py").read_text(encoding="utf-8")
    arbol = ast.parse(src)
    importados = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            importados += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            importados.append(n.module or "")
    assert not any("memory" in m for m in importados)
    assert not any("chromadb" in m for m in importados)
