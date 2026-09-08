"""Los cinco minors diferidos del review del 1a (mapa de dependencias,
seccion 5) que el 1b tiene que cerrar porque ahora el paquete esta en el
camino vivo del server."""
import os
import pathlib
import subprocess
import sys
import textwrap

from calipso.abismo import anillos, consulta, contrato, fuentes, marca

RAIZ = pathlib.Path(__file__).resolve().parent


def test_una_fuente_que_devuelve_basura_es_fallo_suave(monkeypatch):
    """Invariante 4: el armado del bloque (filtrado, etiquetado, techo) vive
    ADENTRO del try. Una fuente que devuelve None o tuplas de tres no puede
    subir como TypeError por la pasada sintetica hasta el WS."""
    monkeypatch.setattr(fuentes, "chats_viejos", lambda resto: None)
    r = consulta.resolver(marca.Marca("chats", "x"))
    assert r["estado"] == "fallo" and r["texto"] == "" and r["bloques"] == []
    monkeypatch.setattr(fuentes, "chats_viejos", lambda resto: [("a", 2, "de mas")])
    assert consulta.resolver(marca.Marca("chats", "x"))["estado"] == "fallo"
    monkeypatch.setattr(fuentes, "chats_viejos", lambda resto: [("ok", anillos.MEDIA_AGUA)])
    assert consulta.resolver(marca.Marca("chats", "x"))["estado"] == "pescado"


def test_el_env_mal_tipeado_no_impide_arrancar(monkeypatch):
    monkeypatch.setenv("ABISMO_BLOQUE_MAX", "mucho")
    assert consulta._entero_env("ABISMO_BLOQUE_MAX", 2000) == 2000
    monkeypatch.setenv("ABISMO_BLOQUE_MAX", "1500")
    assert consulta._entero_env("ABISMO_BLOQUE_MAX", 2000) == 1500
    monkeypatch.delenv("ABISMO_BLOQUE_MAX")
    assert consulta._entero_env("ABISMO_BLOQUE_MAX", 2000) == 2000


def test_el_trim_del_contrato_nunca_corta_el_cierre():
    """El desempate medido del porton v2 ("Ante la duda ... CONSULTA.") es lo
    ultimo del bloque: ni sesenta nombres largos ni un catastro real pueden
    dejarlo a la mitad."""
    for nombres in ((), ("calipso", "atlas", "calipso-lector"),
                    tuple(f"proyecto-con-nombre-largo-{i:03d}" for i in range(60)),
                    tuple(f"Observatory-Global-{i}" for i in range(9))):
        b = contrato.bloque_contrato(nombres)
        assert len(b) <= contrato.INDICE_MAX, len(nombres)
        assert b.endswith("CONSULTA."), (len(nombres), b[-60:])


def test_una_recorrida_del_banco_no_pisa_las_observaciones(tmp_path):
    """El banco se importa en un subproceso con CALIPSO_HOME temporal (la
    regla del repo: jamas importar calipso sin el home apuntado a un tmp), y
    se prueba solo la eleccion de la ruta de salida, no la corrida."""
    codigo = textwrap.dedent(f"""
        import os, pathlib, sys
        sys.path.insert(0, {str(RAIZ / "experimentos")!r})
        sys.path.insert(0, {str(RAIZ)!r})
        import consulta_abismo as banco
        p = pathlib.Path({str(tmp_path)!r}) / "consulta_abismo_resultados.md"
        assert banco._ruta_de_salida(p) == p, "sin archivo previo se escribe en el default"
        p.write_text("## Observaciones escritas a mano", encoding="utf-8")
        otra = banco._ruta_de_salida(p)
        assert otra != p and otra.parent == p.parent and otra.suffix == ".md", otra
        os.environ["ABISMO_RESULTADOS"] = str(p.parent / "forzado.md")
        assert banco._ruta_de_salida(p).name == "forzado.md"
        print("OK")
    """)
    # ABISMO_RESULTADOS vacio: si la env viene puesta de afuera (Pedro la usa
    # para correr el banco a un archivo aparte) las dos primeras aserciones
    # medirian otra cosa.
    entorno = {**os.environ, "CALIPSO_HOME": str(tmp_path / "home"),
               "ABISMO_RESULTADOS": ""}
    r = subprocess.run([sys.executable, "-c", codigo],
                       env=entorno, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "OK" in r.stdout, r.stderr
