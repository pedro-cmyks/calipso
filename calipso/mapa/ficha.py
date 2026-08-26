"""
calipso/mapa/ficha.py — De un edificio a contexto y a una cuenta que paga.

El departamento no es otro interlocutor (invariante 7): es un objetivo del
cerebro. Este modulo hace las dos traducciones que eso necesita — el bloque
de texto que Calipso recibe, y la cuenta que va a pagar el turno — y las
hace puras, sobre el modelo de ciudad que el mapa ya deriva.
"""
from __future__ import annotations


def id_de_nombre(nombre: str, edificios: list[dict]) -> str | None:
    """`atlas` -> `dep:atlas`. None si ese departamento no existe: el modelo
    se puede inventar un nombre y la camara no vuela a la nada."""
    if not nombre:
        return None
    buscado = nombre.strip().lower()
    for e in edificios:
        if e["id"].lower() == buscado or (e.get("nombre") or "").lower() == buscado:
            return e["id"]
    return None
