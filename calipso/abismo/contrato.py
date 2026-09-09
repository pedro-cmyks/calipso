"""El contrato de la marca y el indice de lo consultable -- spec seccion 7.

Funcion PURA: el 1b la insertara en internal_contract (prompt_compiler); en
el 1a solo la consume el banco de medicion. Techo propio para no pagar en
cada turno lo que se ahorra consultando.

La forma es la variante "dura" que PASO el porton v2 (2026-09-07): abre
negando la fuente inventada, nombra el peor error con todas las letras,
prohibe la formula exacta que el 7b mas repitio al confabular ("segun mis
registros") y cierra con el desempate que ya funciono en el juez de
privacidad (ante la duda, CONSULTA). Contra la linea base subio memoria
17%->83%, proyecto 50%->100% y chats 67%->100% sin mover las espurias (8%).
Numeros y protocolo: experimentos/consulta_abismo_resultados_v2.md. NO
cambiar la letra sin re-correr el banco: cada palabra de este bloque esta
medida.
"""
from __future__ import annotations

from calipso.abismo import marca

INDICE_MAX = 600


def bloque_contrato(nombres_proyectos=()) -> str:
    a, c = marca.ABRE, marca.CIERRA

    def _armar(nombres, extra):
        if nombres:
            cola = f" y {extra} mas" if extra else ""
            repos = "repo: " + ", ".join(nombres) + cola + "."
        elif extra:
            # El recorte vacio la lista (nombres muy largos): cola honesta en
            # vez de esconder que el catastro existe (minor del review 1a),
            # corta para que el cierre medido entre siempre. "Pedilos por
            # nombre" ya lo dice la marca de la linea.
            repos = f"un repo del catastro; hay {extra} mas."
        else:
            repos = "el detalle de un repo del catastro."
        return "\n".join([
            "=== El abismo ===",
            ("No sabes nada de Pedro fuera de este prompt. El peor error: "
             "inventar un dato sobre el (un recuerdo, sus chats, el estado "
             "de un repo). Prohibido \"segun mis registros\" sin consultar."),
            "Si te falta el dato, pedilo a mitad de frase con UNA marca:",
            f"{a}abismo:memoria pregunta{c} -- recuerdos, quien es Pedro.",
            f"{a}abismo:chats palabras, opcional desde:AAAA-MM hasta:AAAA-MM{c} -- charlas viejas.",
            f"{a}abismo:proyecto nombre{c} -- {repos}",
            ("La marca se retira del texto: segui como si nada. Maximo 3 por "
             "respuesta. Ante la duda entre contestar de memoria o consultar, "
             "CONSULTA."),
        ])

    nombres = list(nombres_proyectos)
    total = len(nombres)
    texto = _armar(nombres, 0)
    while len(texto) > INDICE_MAX and nombres:
        nombres = nombres[:-1]
        texto = _armar(nombres, total - len(nombres))
    if len(texto) > INDICE_MAX:
        # ni un nombre entra y la cola honesta tampoco: vuelve la variante
        # sin nombres (la medida) antes que cortar el cierre "Ante la duda
        # ... CONSULTA", que es el desempate al que el porton v2 le atribuye
        # la mejora. Nunca se rebana el texto.
        texto = _armar([], 0)
    return texto
