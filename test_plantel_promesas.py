# test_plantel_promesas.py
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
    from calipso.plantel import promesas
    promesas.anotar("atlas", "atlas-1", _forma(), True, "tarde pero cumplio")
    got = promesas.leer("atlas")
    assert len(got) == 1
    assert got[0]["propuesta_id"] == "atlas-1"
    assert got[0]["cumplio"] is True
    assert got[0]["palabras"] == "tarde pero cumplio"
    assert got[0]["ts"]


def test_leer_sin_archivo_es_lista_vacia(home):
    from calipso.plantel import promesas
    assert promesas.leer("atlas") == []


def test_leer_corrupto_levanta(home):
    from calipso.plantel import promesas
    ruta = home / "memoria" / "departamento" / "atlas" / "promesas.json"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text("{no es json", encoding="utf-8")
    with pytest.raises(promesas.ErrorPromesas):
        promesas.leer("atlas")


def test_dedup_por_propuesta_un_trabajo_se_juzga_una_vez(home):
    from calipso.plantel import promesas
    promesas.anotar("atlas", "atlas-1", _forma(), True, "")
    promesas.anotar("atlas", "atlas-1", _forma(), False, "cambio de opinion")
    got = promesas.leer("atlas")
    assert len(got) == 1                 # gana el primero, no se duplica
    assert got[0]["cumplio"] is True


def test_juzgada(home):
    from calipso.plantel import promesas
    assert promesas.juzgada("atlas", "atlas-1") is False
    promesas.anotar("atlas", "atlas-1", _forma(), True, "")
    assert promesas.juzgada("atlas", "atlas-1") is True
    assert promesas.juzgada("atlas", "atlas-2") is False


def test_standing_cuenta_cumplidas_y_total(home):
    from calipso.plantel import promesas
    assert promesas.standing("atlas") == {"cumplidas": 0, "total": 0}
    promesas.anotar("atlas", "atlas-1", _forma(), True, "")
    promesas.anotar("atlas", "atlas-2", _forma(), False, "")
    promesas.anotar("atlas", "atlas-3", _forma(), True, "")
    assert promesas.standing("atlas") == {"cumplidas": 2, "total": 3}


def test_no_usa_write_text_pelado(home):
    from calipso.plantel import promesas
    promesas.anotar("atlas", "atlas-1", _forma(), True, "")
    dir_dep = home / "memoria" / "departamento" / "atlas"
    nombres = [p.name for p in dir_dep.iterdir()]
    assert "promesas.json" in nombres
    assert not any(n.startswith("promesas.json.tmp") for n in nombres)


def test_no_importa_memory():
    import ast
    import pathlib
    src = pathlib.Path("calipso/plantel/promesas.py").read_text(encoding="utf-8")
    arbol = ast.parse(src)
    mods = []
    for n in ast.walk(arbol):
        if isinstance(n, ast.Import):
            mods += [a.name for a in n.names]
        elif isinstance(n, ast.ImportFrom):
            mods.append(n.module or "")
    assert not any("memory" in m for m in mods)
    assert not any("chromadb" in m for m in mods)
