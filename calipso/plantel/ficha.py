#!/usr/bin/env python3
"""
calipso/plantel/ficha.py — la gramatica de `proponer`.

Una propuesta se identificaba por un renglon de prosa cortado a 120
caracteres, y eso hacia imposible el "nunca mas" de la mesa: comparar
titulos por igualdad no atrapa nada -- el mismo modelo escribe "radar de
precios" y "un radar de precios de la competencia" en dos tics -- y por
substring atrapa de mas y no se le puede explicar a Pedro el dia que
revoque.

Este modulo es la forma que faltaba, y copia el molde del motor de
permisos: separa la FORMA -- lo unico que se compara -- del titulo y la
prosa, que Pedro lee y que no participan de ninguna comparacion.

Puro a proposito: no toca disco, no importa nada del proyecto y no tiene
estado. Todo lo que decide se decide con el texto que recibe.
"""
from __future__ import annotations

import unicodedata

# Las seis promesas son el vocabulario entero: lo que no esta aca, un
# departamento no lo puede pedir. Cada una trae su unidad de medida, asi
# que la propuesta nace con un criterio de exito que no inventa el modelo.
PROMESAS = ("ahorrar", "acelerar", "arreglar", "medir", "construir",
            "descartar")

METRICA = {
    "ahorrar": "milimonedas por semana que dejan de salir de esa cuenta",
    "acelerar": "semanas hasta cerrar",
    "arreglar": "veces que vuelve a fallar",
    "medir": "existe el numero: si o no",
    "construir": "usos en cuatro semanas",
    "descartar": "milimonedas por semana que dejan de salir",
}

# `no se` existe a proposito: sin el, un modelo que no sabe elige uno al
# azar y la mentira entra al criterio de muerte. Declararlo es informacion;
# adivinarlo es ruido.
PLAZOS = ("corto", "medio", "largo", "no se")

# `no se` toma el valor que el codigo usaba escrito a mano antes de que
# existiera esta tabla: es el unico de los cuatro que no empeora nada.
SEMANAS_MAX = {"corto": 1, "medio": 4, "largo": 12, "no se": 4}

CAMPOS = ("sobre", "promete", "tarda", "porque")

# Se descartan al normalizar para que "el radar de precios" y "radar
# precios" sean el mismo objeto. `y` y `o` NO estan en esta lista: un
# articulo no cambia que es el objeto, pero una conjuncion puede unir dos
# objetos distintos -- "el banco y el lector" no es lo mismo que "el
# banco del lector", y confundirlos fundiria "dos cosas" con "una cosa de
# otra".
FUNCIONALES = frozenset(
    "el la los las un una unos unas de del al a en para por con que "
    "su sus mi mis lo".split())

TOPE_TITULO = 120

# El techo de `sobre` existe por el libro append-only, no por estetica.
# `_pensar_local` no le manda a Ollama ningun tope de salida y `bus.alta`
# solo valida que `sobre` sea un string no vacio: un modelo local atascado
# en un loop de repeticion escribiria un `sobre` gigante en el bus, de
# donde no se puede borrar nunca, y ademas vuelve al prompt de ese
# departamento para siempre porque el catalogo incluye lo muerto a
# proposito. Un objeto real mide decenas de caracteres; con un tope de
# unos cientos no se pierde nada de lo que importa.
TOPE_SOBRE = 300


def _sin_tildes(texto: str) -> str:
    """Saca acentos y dieresis letra por letra, pero protege la ñ.

    La ñ no es una vocal acentuada: es su propia letra, distinta de la
    ene, y por eso el NFKD no la puede descomponer -- si se le sacara la
    virgulilla, "campaña" (la de marketing) se fundiria con "campana"
    (la del campanario), y son dos objetos distintos de verdad. La
    dieresis si se saca, porque ahi es un accesorio sobre una vocal: la
    palabra es la misma con o sin ella.
    """
    resultado = []
    for c in texto:
        if c in ("ñ", "Ñ"):
            resultado.append(c)
            continue
        resultado.extend(d for d in unicodedata.normalize("NFKD", c)
                          if not unicodedata.combining(d))
    return "".join(resultado)


def normalizar(texto: str) -> str:
    """La clave de identidad de un objeto.

    Explicable el dia que Pedro revoque, que es el requisito que descarta
    cualquier comparacion difusa: "dijiste que no a este objeto, escrito
    asi".

    Se ORDENA porque el orden de las palabras es lo que un modelo mas
    varia y en una frase nominal casi nunca carga significado. Los DIGITOS
    se quedan: sin ellos "el modelo 7b" y "el modelo 3b" serian la misma
    familia, y son cosas distintas.
    """
    limpio = _sin_tildes(texto or "").lower()
    tokens = []
    actual = []
    for c in limpio:
        if c.isalnum():
            actual.append(c)
        elif actual:
            tokens.append("".join(actual))
            actual = []
    if actual:
        tokens.append("".join(actual))
    return "+".join(sorted(t for t in tokens if t and t not in FUNCIONALES))


def _por_prefijo(dado: str, opciones) -> str | None:
    """El valor de `opciones` que `dado` prefija, si es UNO solo.

    Un valor EXACTO gana aunque prefije a otra opcion mas larga: el
    vocabulario esta pensado para crecer de mano de Pedro, y el dia que
    una promesa nueva prefije a una vieja, escribir la vieja completa y
    exacta tiene que seguir matcheando. Fuera de ese caso, un prefijo
    ambiguo no matchea: `a` esta entre `ahorrar`, `acelerar` y
    `arreglar`, y adivinar cual quiso decir seria peor que no entender --
    la ficha caeria en el bus con una promesa que el jefe no eligio.
    """
    dado = _sin_tildes((dado or "").strip()).lower()
    if not dado:
        return None
    if dado in opciones:
        return dado
    calzan = [o for o in opciones if o.startswith(dado)]
    return calzan[0] if len(calzan) == 1 else None


def parsear_ficha(texto: str) -> dict | None:
    """Los cuatro renglones de una propuesta, o `None` si no se entienden.

    Repara antes de rendirse: el orden no importa, las claves se matchean
    por prefijo unico y sin mayusculas ni tildes, los valores tambien, y un
    renglon con una clave que no matchea se ignora en vez de romper.

    `None` NO es un error: es la valvula. El llamador la desvia a un aviso
    con la prosa cruda adentro, que es lo que evita que la gramatica
    amordace al departamento.
    """
    crudo: dict[str, str] = {}
    for linea in (texto or "").splitlines():
        if ":" not in linea:
            continue
        clave, _, valor = linea.partition(":")
        campo = _por_prefijo(clave.strip(), CAMPOS)
        if campo is None or campo in crudo:
            continue        # el primero gana: un renglon repetido no pisa
        crudo[campo] = valor.strip()

    # El recorte pasa ANTES de calcular la clave: la clave tiene que salir
    # del texto que efectivamente se guarda, no de uno mas largo que nunca
    # llega al libro.
    sobre = crudo.get("sobre", "")[:TOPE_SOBRE]
    clave = normalizar(sobre)
    if not clave:
        return None         # sin objeto, o un objeto de puros funcionales
    promete = _por_prefijo(crudo.get("promete", ""), PROMESAS)
    tarda = _por_prefijo(crudo.get("tarda", ""), PLAZOS)
    if promete is None or tarda is None:
        return None
    return {"sobre": sobre, "clave": clave, "promete": promete,
            "tarda": tarda, "porque": crudo.get("porque", "")}


def titulo_de(f: dict) -> str:
    """Lo que Pedro lee en la mesa. No participa de ninguna comparacion.

    Sigue acotado a 120 como el titulo de hoy. Lo primero que se
    sacrifica cuando no entra todo es el `porque` -- puede desaparecer
    entero -- y recien despues, si hace falta, se recorta el `sobre`,
    siempre dejando el `(<tarda>)` entero y cerrado: nunca un slice
    ciego que podria cortar a mitad de un parentesis o dejar un `--`
    colgando y leerse como software roto.

    Ese recorte inteligente asume un `promete` y un `tarda` cortos, como
    los que entrega `parsear_ficha` -- valores de PROMESAS y PLAZOS. Pero
    esta funcion es publica y no valida nada, asi que por las dudas
    lleva ademas un tope duro al final, que vale para cualquier entrada,
    incluida una armada a mano fuera del camino sancionado.
    """
    prefijo = f"{f['promete']}: "
    sufijo = f" ({f['tarda']})"
    lugar_sobre = max(TOPE_TITULO - len(prefijo) - len(sufijo), 0)
    sobre = f["sobre"][:lugar_sobre]
    base = f"{prefijo}{sobre}{sufijo}"

    porque = f.get("porque")
    if porque:
        lugar_porque = TOPE_TITULO - len(base) - len(" -- ")
        if lugar_porque > 0:
            base = f"{base} -- {porque[:lugar_porque]}"

    return base[:TOPE_TITULO]
