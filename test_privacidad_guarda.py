# test_privacidad_guarda.py
"""Guarda de regresion del detector determinista contra un set de secretos que
DEBE agarrar y de negativos donde NO debe dispararse. La parte LLM del juez no
se testea aca (es no-deterministica y lenta): su medicion vive en
experimentos/juez_privacidad.py. Esto fija el piso de la capa que si es fija."""
import pytest
from calipso.privacidad.detector import detectar_secretos

# secretos de maquina: cada uno tiene que salir marcado
SECRETOS = [
    "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    "-----BEGIN OPENSSH PRIVATE KEY----- b3BlbnNzaC1rZXktdjEAAAAABG5vbmU",
    "7645123456:AAFhSj2kL9mNpQrStUvWxYz0123456789ab",
    "postgres://calipso:Sup3rS3cret@db.interno:5432/prod",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J",
    "sk-proj-Abc123XyZ456Def789Ghi012Jkl345Mno678",
    "ghp_A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8",
    "rk_live_51H8xQ2eZvKYlo2Cq9Zt7",
    "GVXW4LN7ARQK3ZJT6YHD2MPSFB5UECIO",
]

# texto inocente: el detector NO se puede disparar
NEGATIVOS = [
    "la clave del exito es la constancia",
    "quiero una contrasena mas segura en general",
    "el producto SKU-4472-B del catalogo no carga",
    "me explicas la diferencia entre una lista y una tupla?",
    "el evento es el 03/07/2027, armame la agenda",
    "en general que habitos mejoran la salud del corazon?",
]


@pytest.mark.parametrize("s", SECRETOS)
def test_el_detector_agarra_todo_secreto(s):
    assert detectar_secretos(s), f"el detector dejo pasar un secreto: {s!r}"


@pytest.mark.parametrize("s", NEGATIVOS)
def test_el_detector_no_se_dispara_en_inocente(s):
    assert detectar_secretos(s) == [], f"falso positivo del detector en: {s!r}"
