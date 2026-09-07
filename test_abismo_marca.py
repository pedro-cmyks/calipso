"""La gramatica cerrada de la marca del abismo (spec seccion 5)."""
from calipso.abismo import marca


def test_marca_valida_por_fuente():
    m = marca.parsear("memoria que le gusta leer a Pedro")
    assert m == marca.Marca(fuente="memoria", resto="que le gusta leer a Pedro")
    m = marca.parsear("chats agosto libro desde:2026-08 hasta:2026-08")
    assert m.fuente == "chats"
    m = marca.parsear("proyecto calipso")
    assert m == marca.Marca(fuente="proyecto", resto="calipso")


def test_fuente_desconocida_es_ilegible():
    assert marca.parsear("memorai que dije ayer") is None      # typo: NO cae a memoria
    assert marca.parsear("fondo algo") is None                 # fuente de otra rebanada
    assert marca.parsear("") is None


def test_sin_resto_es_ilegible():
    assert marca.parsear("memoria") is None
    assert marca.parsear("proyecto   ") is None


def test_tope_de_pregunta():
    assert marca.parsear("memoria " + "x" * 152) is None       # cuerpo > 160
    assert marca.parsear("memoria " + "x" * 100) is not None


def test_encontrar_en_texto():
    texto = ("Dejame ver ⟦abismo:chats libro agosto⟧ y tambien "
             "⟦abismo:zzz nada⟧ al final.")
    marcas = marca.encontrar(texto)
    assert len(marcas) == 2
    assert marcas[0] == marca.Marca(fuente="chats", resto="libro agosto")
    assert marcas[1] is None                                   # ilegible, cuenta para aviso


def test_encontrar_sin_marcas():
    assert marca.encontrar("un texto cualquiera sin marcas") == []
