#!/usr/bin/env python3
"""
test_plantel_ficha.py — La gramatica de `proponer` (spec del 2026-09-01).

Modulo puro: no toca disco, no importa nada del proyecto, no necesita
fixture de home.
"""
from calipso.plantel import ficha


# --------------------------------------------------------------------------
# normalizar: la funcion de identidad
# --------------------------------------------------------------------------

def test_la_misma_cosa_escrita_distinto_da_la_misma_clave():
    assert ficha.normalizar("El Radar de Precios!") == "precios+radar"
    assert ficha.normalizar("el radar de precios") == "precios+radar"
    assert ficha.normalizar("  radar   precios ") == "precios+radar"


def test_el_orden_de_las_palabras_no_importa():
    # es lo que un modelo mas varia, y en una frase nominal casi nunca
    # carga significado
    assert ficha.normalizar("precios radar") == ficha.normalizar("radar precios")


def test_los_digitos_se_quedan():
    # descartarlos haria que dos modelos distintos fueran la misma familia
    assert ficha.normalizar("el modelo 7b") == "7b+modelo"
    assert ficha.normalizar("el modelo 3b") == "3b+modelo"
    assert ficha.normalizar("el modelo 7b") != ficha.normalizar("el modelo 3b")


def test_singular_y_plural_son_dos_familias():
    # no se usa stemming: seria difuso y no se podria explicar el dia que
    # Pedro revoque
    assert ficha.normalizar("radar de precio") != ficha.normalizar("radar de precios")


def test_solo_funcionales_no_es_un_objeto():
    # un objeto sin contenido no es un objeto
    assert ficha.normalizar("el") == ""
    assert ficha.normalizar("de la") == ""


def test_la_enie_sobrevive_pero_la_diaresis_no():
    # la eñe es una letra propia, no una vocal con acento: fundirla con la
    # ene confundiria dos objetos distintos de verdad
    assert ficha.normalizar("el año") != ficha.normalizar("el ano")
    assert ficha.normalizar("la campaña") != ficha.normalizar("la campana")
    # la diaresis si es un accesorio sobre una vocal: la palabra es la misma
    assert ficha.normalizar("el pingüino") == ficha.normalizar("el pinguino")


def test_conjuncion_no_es_funcional():
    # un articulo no cambia que es el objeto, pero una conjuncion puede
    # unir dos objetos distintos: "dos cosas" no es "una cosa de otra"
    assert ficha.normalizar("el banco y el lector") != ficha.normalizar(
        "el banco del lector")


# --------------------------------------------------------------------------
# _por_prefijo: el matcheo de claves y valores
# --------------------------------------------------------------------------

def test_un_valor_exacto_gana_aunque_prefije_a_otro_mas_largo():
    # el vocabulario esta pensado para crecer: el dia que una promesa nueva
    # prefije a una vieja, la vieja completa y exacta tiene que seguir
    # matcheando en vez de caer en la cuenta de ambiguos
    opciones = ("medir", "medirlo")
    assert ficha._por_prefijo("medir", opciones) == "medir"


# --------------------------------------------------------------------------
# parsear_ficha: la reparacion antes de rendirse
# --------------------------------------------------------------------------

FICHA_OK = """proponer
sobre: el radar de precios
promete: descartar
tarda: corto
porque: no rindio y sigue gastando"""


def test_una_ficha_completa_se_lee_entera():
    f = ficha.parsear_ficha(FICHA_OK)
    assert f == {"sobre": "el radar de precios", "clave": "precios+radar",
                 "promete": "descartar", "tarda": "corto",
                 "porque": "no rindio y sigue gastando"}


def test_el_orden_de_los_renglones_no_importa():
    f = ficha.parsear_ficha(
        "proponer\ntarda: corto\nporque: da igual\npromete: medir\n"
        "sobre: el clasificador")
    assert f["promete"] == "medir" and f["tarda"] == "corto"


def test_las_claves_se_matchean_por_prefijo_unico_y_sin_mayusculas():
    f = ficha.parsear_ficha(
        "proponer\nSOBRE : el radar\nProm: medir\nTARDA: corto")
    assert f["sobre"] == "el radar" and f["promete"] == "medir"


def test_los_valores_tambien_se_matchean_por_prefijo():
    f = ficha.parsear_ficha("proponer\nsobre: el radar\npromete: desc\ntarda: cor")
    assert f["promete"] == "descartar" and f["tarda"] == "corto"


def test_un_prefijo_ambiguo_no_matchea():
    # `a` esta entre ahorrar, acelerar y arreglar: adivinar seria peor que
    # no entender
    assert ficha.parsear_ficha(
        "proponer\nsobre: el radar\npromete: a\ntarda: corto") is None


def test_porque_puede_faltar():
    f = ficha.parsear_ficha("proponer\nsobre: el radar\npromete: medir\ntarda: corto")
    assert f is not None and f["porque"] == ""


def test_un_renglon_que_no_matchea_se_ignora_y_no_rompe():
    f = ficha.parsear_ficha(
        "proponer\nsobre: el radar\nfulano: cualquier cosa\n"
        "promete: medir\ntarda: corto")
    assert f is not None and f["sobre"] == "el radar"


def test_no_se_es_un_plazo_valido():
    f = ficha.parsear_ficha("proponer\nsobre: el radar\npromete: medir\ntarda: no se")
    assert f is not None and f["tarda"] == "no se"


def test_lo_que_falta_deja_la_ficha_ilegible():
    sin_sobre = "proponer\npromete: medir\ntarda: corto"
    sin_promete = "proponer\nsobre: el radar\ntarda: corto"
    sin_tarda = "proponer\nsobre: el radar\npromete: medir"
    promete_invalido = "proponer\nsobre: el radar\npromete: bailar\ntarda: corto"
    for texto in (sin_sobre, sin_promete, sin_tarda, promete_invalido):
        assert ficha.parsear_ficha(texto) is None, texto


def test_un_sobre_sin_contenido_deja_la_ficha_ilegible():
    assert ficha.parsear_ficha(
        "proponer\nsobre: el\npromete: medir\ntarda: corto") is None


def test_la_prosa_libre_de_hoy_ya_no_es_una_ficha():
    # este es el cambio: lo que hoy pasa como propuesta, ahora es ilegible
    # y va a la valvula
    assert ficha.parsear_ficha("proponer\nhay hueco en precios") is None


def test_un_sobre_gigante_no_se_guarda_entero():
    # el libro es append-only: un modelo local atascado en un loop de
    # repeticion no puede escribir un `sobre` sin techo, porque de ahi no
    # se lo puede borrar nunca
    sobre_gigante = "palabra " * 200
    f = ficha.parsear_ficha(
        f"proponer\nsobre: {sobre_gigante}\npromete: medir\ntarda: corto")
    assert f is not None
    assert len(f["sobre"]) <= ficha.TOPE_SOBRE


def test_el_recorte_del_sobre_pasa_antes_de_calcular_la_clave():
    # la clave tiene que salir del texto que efectivamente se guarda, no
    # de uno mas largo que nunca llega al libro: una palabra que solo
    # aparece despues del tope no puede colarse en la clave
    relleno = "palabra " * 200  # muy por encima del tope
    f = ficha.parsear_ficha(
        f"proponer\nsobre: {relleno}unica\npromete: medir\ntarda: corto")
    assert f is not None
    assert len(f["sobre"]) == ficha.TOPE_SOBRE
    assert "unica" not in f["sobre"]
    assert "unica" not in f["clave"]


# --------------------------------------------------------------------------
# las tablas y el titulo
# --------------------------------------------------------------------------

def test_cada_promesa_trae_su_metrica_y_cada_plazo_su_semana():
    assert set(ficha.METRICA) == set(ficha.PROMESAS)
    assert set(ficha.SEMANAS_MAX) == set(ficha.PLAZOS)
    assert ficha.SEMANAS_MAX["corto"] == 1
    assert ficha.SEMANAS_MAX["largo"] == 12
    # `no se` toma el valor de hoy a proposito: es el unico que no empeora
    # nada respecto del 4 literal que habia
    assert ficha.SEMANAS_MAX["no se"] == 4
    # un repetido en la tupla no lo atrapa el set: lo atrapa el largo
    assert len(ficha.PROMESAS) == len(set(ficha.PROMESAS))
    assert len(ficha.PLAZOS) == len(set(ficha.PLAZOS))


def test_el_titulo_nunca_pasa_de_120_ni_con_un_dict_armado_a_mano():
    # parsear_ficha nunca entrega un promete/tarda largo, pero titulo_de
    # es publica y no valida: el tope tiene que ser incondicional
    f = {"sobre": "el radar", "clave": "el+radar",
         "promete": "x" * 150, "tarda": "y" * 150, "porque": ""}
    assert len(ficha.titulo_de(f)) <= 120


def test_el_titulo_se_arma_con_la_ficha():
    f = ficha.parsear_ficha(FICHA_OK)
    assert ficha.titulo_de(f) == (
        "descartar: el radar de precios (corto) -- no rindio y sigue gastando")


def test_sin_porque_el_titulo_no_arrastra_el_separador():
    f = ficha.parsear_ficha("proponer\nsobre: el radar\npromete: medir\ntarda: corto")
    assert ficha.titulo_de(f) == "medir: el radar (corto)"


def test_el_titulo_no_pasa_de_120():
    f = ficha.parsear_ficha(
        "proponer\nsobre: " + "x" * 200 + "\npromete: medir\ntarda: corto")
    titulo = ficha.titulo_de(f)
    assert len(titulo) <= 120
    # se recorta el sobre, nunca el resultado final: el parentesis del
    # plazo tiene que quedar entero y cerrado
    assert titulo.endswith(")")


def test_el_titulo_recorta_el_porque_y_no_el_plazo():
    f = ficha.parsear_ficha(
        "proponer\nsobre: el radar\npromete: medir\ntarda: corto\n"
        "porque: " + "x" * 300)
    titulo = ficha.titulo_de(f)
    assert len(titulo) <= 120
    assert "(corto)" in titulo
