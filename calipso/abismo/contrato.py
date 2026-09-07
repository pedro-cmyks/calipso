"""El contrato de la marca y el indice de lo consultable -- spec seccion 7.

Funcion PURA: el 1b la insertara en internal_contract (prompt_compiler); en
el 1a solo la consume el banco de medicion. Techo propio para no pagar en
cada turno lo que se ahorra consultando.
"""
from __future__ import annotations

from calipso.abismo import marca

INDICE_MAX = 600


def bloque_contrato(nombres_proyectos=()) -> str:
    a, c = marca.ABRE, marca.CIERRA

    def _armar(nombres, extra):
        lineas = [
            "=== El abismo (contexto a demanda) ===",
            ("Si te falta un dato que Calipso deberia saber, pedilo a mitad "
             "de la respuesta con UNA marca:"),
            f"{a}abismo:memoria <pregunta>{c} -- recuerdos, quien es Pedro, su cronologia.",
            f"{a}abismo:chats <palabras, opcional desde:AAAA-MM hasta:AAAA-MM>{c} -- conversaciones viejas.",
            f"{a}abismo:proyecto <nombre>{c} -- el detalle de un repo del catastro.",
        ]
        if nombres:
            cola = f" y {extra} mas" if extra else ""
            lineas.append("Proyectos consultables: " + ", ".join(nombres) + cola + ".")
        lineas.append(("La marca se retira del texto: segui la frase como si "
                       "nada. Maximo 3 por respuesta. Si no te falta nada, "
                       "no consultes."))
        return "\n".join(lineas)

    nombres = list(nombres_proyectos)
    total = len(nombres)
    texto = _armar(nombres, 0)
    while len(texto) > INDICE_MAX and nombres:
        nombres = nombres[:-1]
        texto = _armar(nombres, total - len(nombres))
    return texto[:INDICE_MAX]
