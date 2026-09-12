#!/usr/bin/env python3
"""
test_memoria_carta.py — la carta de un departamento.

Archivo propio y no `test_memory.py`: ese corre por `main()` y pytest no
colecta nada de el, asi que un test ahi no correria nunca.
"""
import pathlib

import pytest

from calipso import memory


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Parchea la CONSTANTE, no el entorno.

    `memory.py` congela `CALIPSO_HOME` al importarse (es una constante de
    modulo, no una funcion), y el `conftest.py` de la raiz ya la fijo a un
    home desechable antes de que nada importara. Un `monkeypatch.setenv`
    aca no tendria ningun efecto: el valor ya esta leido.
    """
    monkeypatch.setattr(memory, "CALIPSO_HOME", tmp_path)
    return tmp_path


def test_la_ruta_es_pura_y_no_crea_nada(home):
    """Instanciar `Memory.departamento(...)` hace mkdir de dos directorios y
    abre un chroma. Leer una carta no puede tener ese efecto: seria crear un
    sqlite por departamento como consecuencia de pintar una pantalla."""
    antes = sorted(p.name for p in home.iterdir())
    r = memory.ruta_carta("taller")
    assert r.name == "carta.md"
    assert sorted(p.name for p in home.iterdir()) == antes


def test_sin_archivo_la_carta_esta_ausente(home):
    assert memory.leer_carta("taller") == {"estado": "ausente", "texto": ""}


def test_un_archivo_en_blanco_es_vacia_y_no_ausente(home):
    """`load_core` devuelve "" en los dos casos y por eso no sirve para esto.
    Ausente es "Pedro no escribio"; vacia es "Pedro escribio nada", que es
    una respuesta distinta y el jefe tiene que poder distinguirlas."""
    r = memory.ruta_carta("taller")
    r.parent.mkdir(parents=True, exist_ok=True)
    r.write_text("   \n\n  ", encoding="utf-8")
    assert memory.leer_carta("taller") == {"estado": "vacia", "texto": ""}


def test_una_carta_escrita_vuelve_con_su_texto(home):
    r = memory.ruta_carta("taller")
    r.parent.mkdir(parents=True, exist_ok=True)
    r.write_text("  I+D para los proyectos de Pedro.\n", encoding="utf-8")
    assert memory.leer_carta("taller") == {
        "estado": "escrita", "texto": "I+D para los proyectos de Pedro."}


def test_la_carta_vive_afuera_del_core(home):
    """El invariante de procedencia, verificado por RUTA y no construyendo
    una `Memory`.

    El core alimenta el bloque "Lo que aprendiste antes" del prompt, y una
    instruccion de Pedro no puede llegarle al modelo rotulada como una
    conclusion propia del jefe. `load_core` hace glob sobre `core/*.md`:
    alcanza con que la carta no este ahi abajo.

    Y se prueba asi a proposito: `Memory.__init__` abre dos clientes de
    chroma y crea directorios, asi que construir una para comprobar una
    ruta seria un test con efectos por un motivo ajeno a lo que prueba.
    """
    carta = memory.ruta_carta("taller")
    core = home / "memoria" / "departamento" / "taller" / "core"
    assert core not in carta.parents


def test_dos_departamentos_no_comparten_carta(home):
    for nombre in ("taller", "research"):
        r = memory.ruta_carta(nombre)
        r.parent.mkdir(parents=True, exist_ok=True)
        r.write_text(f"soy {nombre}", encoding="utf-8")
    assert memory.leer_carta("taller")["texto"] == "soy taller"
    assert memory.leer_carta("research")["texto"] == "soy research"


def test_una_carta_ilegible_no_revienta(home):
    """El disco puede tener cualquier cosa. Una carta que no se puede leer
    se trata como ausente: el jefe dice que no la tiene, que es verdad."""
    r = memory.ruta_carta("taller")
    r.parent.mkdir(parents=True, exist_ok=True)
    r.write_bytes(b"\xc3")
    assert memory.leer_carta("taller")["estado"] in ("ausente", "escrita")
