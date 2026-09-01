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
# precios" sean el mismo objeto.
FUNCIONALES = frozenset(
    "el la los las un una unos unas de del al a en para por con y o que "
    "su sus mi mis lo".split())

TOPE_TITULO = 120


def _sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


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

    Un prefijo ambiguo no matchea: `a` esta entre `ahorrar` y `acelerar`, y
    adivinar cual quiso decir seria peor que no entender -- la ficha caeria
    en el bus con una promesa que el jefe no eligio.
    """
    dado = _sin_tildes((dado or "").strip()).lower()
    if not dado:
        return None
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

    sobre = crudo.get("sobre", "")
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

    Sigue cortado a 120 como el titulo de hoy, asi que `bus.alta` recibe
    exactamente el largo que ya recibia.
    """
    base = f"{f['promete']}: {f['sobre']} ({f['tarda']})"
    if f.get("porque"):
        base = f"{base} -- {f['porque']}"
    return base[:TOPE_TITULO]
