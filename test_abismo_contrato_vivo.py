"""El contrato del abismo dentro del system de verdad: en local con los
nombres del catastro (spec seccion 5), en /nube sin ellos (seccion 8.1)."""
import json

import calipso.server as srv
from calipso import catastro, prompt_compiler
from calipso.abismo import contrato, marca


def _catastro(tmp_path, monkeypatch, nombres):
    # catastro.calipso_home() relee la variable en cada llamada: alcanza setenv
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    (tmp_path / "catastro.json").write_text(json.dumps({
        "raices": [], "proyectos": [{"nombre": n, "ruta": f"/x/{n}"} for n in nombres]}),
        encoding="utf-8")


def test_nombres_no_escanea_nunca(tmp_path, monkeypatch):
    """El contrato corre en CADA turno y en tests con home vacio: un
    catastro que no existe da lista vacia, jamas un escaneo del disco."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))

    def bomba():
        raise AssertionError("el contrato no escanea el disco")
    monkeypatch.setattr(catastro, "escanear", bomba)
    assert catastro.nombres() == []
    _catastro(tmp_path, monkeypatch, ["calipso", "atlas"])
    assert catastro.nombres() == ["calipso", "atlas"]


def test_el_contrato_interno_ensena_la_marca_del_abismo_con_los_repos(tmp_path, monkeypatch):
    _catastro(tmp_path, monkeypatch, ["calipso", "atlas"])
    texto = prompt_compiler.internal_contract({}, base=tmp_path)
    assert texto.endswith(contrato.bloque_contrato(["calipso", "atlas"]))
    assert f"{marca.ABRE}abismo:proyecto nombre{marca.CIERRA} -- repo: calipso, atlas." in texto
    assert "⟦foco:<nombre>⟧" in texto          # el de foco sigue ahi, antes


def test_el_system_de_nube_lleva_el_contrato_sin_nombres(tmp_path, monkeypatch):
    _catastro(tmp_path, monkeypatch, ["calipso", "atlas"])
    nube = srv._sistema_del_turno("hola", "runtime", {}, True)
    assert nube.startswith(srv._SISTEMA_NUBE_MINIMO)
    assert contrato.bloque_contrato(()) in nube
    assert "calipso" not in nube and "atlas" not in nube
    assert "[TIPO_N]" in nube
    # y sin /nube el system sigue siendo el compilado de siempre
    monkeypatch.setattr(srv, "_build_context", lambda *a, **k: "COMPILADO")
    assert srv._sistema_del_turno("hola", "runtime", {}, False) == "COMPILADO"
