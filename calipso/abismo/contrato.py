"""El contrato de la marca y el indice de lo consultable -- spec seccion 7.

Funcion PURA: la consume `internal_contract` (prompt_compiler) como bloque
final del contrato interno, `_sistema_nube` (server) en su variante sin
nombres, y el banco de medicion. Techo propio para no pagar en cada turno lo
que se ahorra consultando.

LA LETRA ESTA MEDIDA DOS VECES Y ES LA SEGUNDA LA QUE VALE. La variante "dura"
(porton v2, 2026-09-07) se midio con el contrato SOLO, junto a una identidad
de dos renglones, y su 83% de memoria era copia literal del molde
(`⟦abismo:memoria pregunta⟧` textual, 30 de 30). La letra de hoy, "existe con
senales" (2026-09-10, h05 opcion a de Pedro), se midio SOBRE el system de
produccion podado, contando solo marcas UTILES: memoria 30/36, chats 36/36,
proyecto 30/36, espurias 0/72, ruteo 84/96, cero copias literales a N=6.
Lo que la hace funcionar en este 7b, por orden de peso: (1) las SENALES
lexicas de Pedro ("te conte", "lo tenes", "acordate", "la otra vez", "que
dejamos") que le dicen al modelo que el dato existe; (2) el error exacto
nombrado ("no tengo registros" sin consultar); (3) los comodines entre < >
"con tus palabras", que matan la copia literal. Decirle que la memoria
"existe" sin las senales no movio nada.
Numeros y protocolo: experimentos/consulta_abismo_system_resultados.md. NO
cambiar la letra sin re-correr `experimentos/consulta_abismo_system.py`:
test_abismo_system_medido.py la ata byte a byte al archivo medido
(experimentos/variantes/contrato-existe-senales.txt). Una ronda que quiso
afinar el ruteo tocando solo las lineas de las fuentes empeoro proyecto y el
ruteo global: la letra esta en un optimo local, mover una linea mueve las otras.
"""
from __future__ import annotations

from calipso.abismo import marca

# La letra con senales mide 1067 chars sin nombres; el techo deja lugar a
# unos diez nombres de repo antes de recortar con la cola "y N mas".
INDICE_MAX = 1300


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
            ("Este prompt trae apenas un resumen minimo. La memoria completa de "
             "Pedro, sus chats viejos y el detalle de sus repos EXISTEN y viven en "
             "el abismo: no estan aca, pero se consultan. El peor error: contestar "
             "\"no tengo registros\", \"no tengo esa informacion\" o pedirle a Pedro "
             "que te lo repita SIN haber consultado antes; el segundo peor, "
             "inventar el dato. Lo que no esta en este prompt se consulta, no se "
             "declara ausente. Cuando Pedro dice \"te conte\", \"lo tenes\", "
             "\"acordate\", \"la otra vez\" o \"que dejamos\", el dato existe: "
             "consulta antes de contestar."),
            ("Para consultar, pedilo a mitad de frase con UNA marca; entre los "
             "corchetes va lo que buscas, con tus palabras:"),
            f"{a}abismo:memoria <que queres saber de Pedro>{c} -- recuerdos, quien es Pedro.",
            (f"{a}abismo:chats <palabras clave de esa charla> desde:AAAA-MM hasta:AAAA-MM{c}"
             " -- charlas viejas; las fechas son opcionales."),
            f"{a}abismo:proyecto <nombre del repo>{c} -- {repos}",
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
        # ... CONSULTA", que es el desempate. Nunca se rebana el texto.
        texto = _armar([], 0)
    return texto
