from calipso.privacidad.redaccion import MapaMarcadores, redactar, reponer


def test_redacta_y_repone_ida_y_vuelta():
    mapa = MapaMarcadores()
    tramos = [{"texto": "3865-4421", "tipo": "contacto"},
              {"texto": "Juan Perez", "tipo": "identidad"}]
    tapado = redactar("soy Juan Perez, mi numero es 3865-4421", tramos, mapa)
    assert "3865-4421" not in tapado
    assert "Juan Perez" not in tapado
    assert "[CONTACTO_1]" in tapado
    assert "[ID_1]" in tapado
    # la respuesta de la nube, con los marcadores, se repone al valor real
    assert reponer("te llamo al [CONTACTO_1], [ID_1]", mapa) == "te llamo al 3865-4421, Juan Perez"


def test_marcador_estable_entre_turnos():
    mapa = MapaMarcadores()
    m1 = mapa.marcador_para("3865-4421", "contacto")
    m2 = mapa.marcador_para("3865-4421", "contacto")   # mismo valor, otro turno
    assert m1 == m2 == "[CONTACTO_1]"
    otro = mapa.marcador_para("11-9999", "contacto")   # valor distinto
    assert otro == "[CONTACTO_2]"


def test_dos_valores_distinto_tipo_numeran_por_tipo():
    mapa = MapaMarcadores()
    assert mapa.marcador_para("Ana", "identidad") == "[ID_1]"
    assert mapa.marcador_para("Belgrano 1234", "ubicacion") == "[LUGAR_1]"


def test_redacta_los_tramos_largos_primero():
    # si un tramo es subcadena de otro, tapar el mas largo primero evita
    # dejar un pedazo del corto suelto adentro del largo
    mapa = MapaMarcadores()
    tramos = [{"texto": "Ana", "tipo": "identidad"},
              {"texto": "Ana Gomez", "tipo": "identidad"}]
    tapado = redactar("firma Ana Gomez", tramos, mapa)
    assert "Ana" not in tapado
    assert tapado == "firma [ID_1]"


def test_tramo_con_texto_vacio_no_corrompe_el_texto():
    # un tramo con texto="" haria str.replace("", marcador), que inserta el
    # marcador entre cada caracter. Se ignora, el resto se tapa normal.
    mapa = MapaMarcadores()
    tramos = [{"texto": "", "tipo": "salud"},
              {"texto": "lupus", "tipo": "salud"}]
    tapado = redactar("tengo lupus", tramos, mapa)
    assert tapado == "tengo [SALUD_1]"
