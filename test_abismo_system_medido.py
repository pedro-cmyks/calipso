"""La letra del system local de produccion es la que PASO el porton sobre el
system de produccion (2026-09-10, h05 opcion a de Pedro): identidad corta en
vez de CALIPSO.md cortado, contrato interno podado, y el bloque del abismo con
las senales de Pedro. Evidencia: experimentos/consulta_abismo_system_resultados.md
(seccion 4: memoria 30/36, chats 36/36, proyecto 30/36, espurias 0/72 a N=6).

Regla: NO cambiar ninguna de estas tres letras sin re-correr el banco
(`experimentos/consulta_abismo_system.py`). Este test las ata byte a byte a los
archivos medidos: `experimentos/variantes/system-podada.txt` (identidad y
contrato interno) y `experimentos/variantes/contrato-existe-senales.txt` (el
bloque). Lo unico que varia legitimamente es el contenido dinamico: los nombres
del catastro en la cola de repos y la linea de departamentos.
"""
import json
import pathlib

import calipso.server as srv
from calipso import prompt_compiler
from calipso.abismo import contrato

RAIZ = pathlib.Path(__file__).resolve().parent
MEDIDO = RAIZ / "experimentos" / "variantes"


def _seccion(texto: str, titulo: str) -> str:
    """El cuerpo de una seccion `=== titulo ===` del system medido."""
    marca = f"=== {titulo} ===\n"
    i = texto.index(marca) + len(marca)
    j = texto.find("\n\n=== ", i)
    return texto[i:] if j < 0 else texto[i:j]


def _system_medido() -> str:
    return (MEDIDO / "system-podada.txt").read_text(encoding="utf-8")


def _bloque_medido(repos: str) -> str:
    letra = (MEDIDO / "contrato-existe-senales.txt").read_text(encoding="utf-8").strip()
    return letra.replace("{repos}", repos)


def _catastro(tmp_path, monkeypatch, nombres):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    (tmp_path / "catastro.json").write_text(json.dumps({
        "raices": [], "proyectos": [{"nombre": n, "ruta": f"/x/{n}"} for n in nombres]}),
        encoding="utf-8")


def test_la_identidad_de_produccion_es_la_medida():
    """SYSTEM es la identidad corta que se midio como seccion `Sistema`.
    CALIPSO.md sigue siendo el documento del repo; al 7b no le llega."""
    assert srv.SYSTEM == _seccion(_system_medido(), "Sistema")
    assert not hasattr(srv, "_identity_doc")


def test_el_bloque_del_abismo_es_la_letra_con_senales(tmp_path, monkeypatch):
    _catastro(tmp_path, monkeypatch, ["calipso", "Observatory-Global", "mapa-ciudad"])
    esperado = _bloque_medido("repo: calipso, Observatory-Global, mapa-ciudad.")
    assert contrato.bloque_contrato(["calipso", "Observatory-Global", "mapa-ciudad"]) == esperado


def test_el_bloque_sin_repos_conserva_la_letra():
    assert contrato.bloque_contrato(()) == _bloque_medido("el detalle de un repo del catastro.")


def test_el_contrato_interno_de_produccion_es_el_podado(tmp_path, monkeypatch):
    """La seccion `Contrato interno` medida, con el bloque viejo reemplazado por
    la letra con senales (asi se midio: el script sustituia el bloque en el
    system armado). La economia no sembrada da la misma linea de foco que en
    la medicion (el home de la medicion tampoco tenia economia)."""
    _catastro(tmp_path, monkeypatch, ["calipso", "Observatory-Global", "mapa-ciudad"])
    medido = _seccion(_system_medido(), "Contrato interno")
    # el system-podada.txt se genero con la letra VIEJA del bloque y la cola
    # "repo: calipso y 2 mas." (techo de 600 de entonces); la medicion real
    # sustituyo ese bloque por la letra con senales con la misma cola.
    i = medido.index("=== El abismo ===")
    esperado = medido[:i] + _bloque_medido("repo: calipso, Observatory-Global, mapa-ciudad.")
    assert prompt_compiler.internal_contract({}, base=tmp_path) == esperado


def test_el_system_local_no_lleva_la_constitucion(tmp_path, monkeypatch):
    """Ni la seccion ni el texto de CALIPSO.md entran al system local."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    texto = prompt_compiler.render_context(srv._build_context("hola", "runtime", {"type": "chat"}))
    assert "=== Constitucion de Calipso ===" not in texto
    assert "Los modelos no son la identidad de Calipso" not in texto
    assert texto.startswith("=== Sistema ===\n" + srv.SYSTEM)


def test_las_instrucciones_que_competian_no_estan(tmp_path, monkeypatch):
    """Las siete instrucciones que se podaron (medicion ronda 1) no vuelven."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    texto = prompt_compiler.internal_contract({"type": "code", "needs_repo": True}, base=tmp_path)
    for frase in ("Tipo de tarea inferido", "Traduce el pedido natural",
                  "contexto probabilistico", "Actua antes de describir",
                  "Ante un roadblock", "separa idea, implementado",
                  "Repo requerido"):
        assert frase not in texto, frase
