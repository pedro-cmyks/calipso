from calipso.privacidad.detector import detectar_secretos


def _textos(prompt):
    return {t["texto"] for t in detectar_secretos(prompt)}


def test_agarra_los_blobs_que_el_llm_deja_pasar():
    # el JWT y la api key rk_live_ que el 7b dejo pasar en la medicion
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N"
    assert jwt in _textos(f"me devuelve este bearer {jwt} y no se si expiro")
    assert "rk_live_51H8xQ2eZvKYlo2Cq9Zt7" in _textos(
        "STRIPE_KEY=rk_live_51H8xQ2eZvKYlo2Cq9Zt7\nDEBUG=true")


def test_agarra_las_otras_clases_de_secreto():
    assert detectar_secretos("ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8")   # prefijo github
    assert detectar_secretos("-----BEGIN OPENSSH PRIVATE KEY----- b3BlbnNz")  # PEM
    assert detectar_secretos("postgres://calipso:Sup3rS3cret@db.interno:5432/prod")  # conn
    assert detectar_secretos("la clave es xK9$mR2vLp8qWz4T3nB7")             # entropia, sin pista


def test_todos_son_tipo_credencial():
    for t in detectar_secretos("token ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"):
        assert t["tipo"] == "credencial"


def test_no_se_dispara_en_texto_inocente():
    # los negativos de la medicion: 'clave del exito', un SKU, password generico
    assert detectar_secretos("la clave del exito es la constancia") == []
    assert detectar_secretos("el producto SKU-4472-B no carga") == []
    assert detectar_secretos("quiero una contrasena mas segura en general") == []
    assert detectar_secretos("me explicas la diferencia entre lista y tupla?") == []
