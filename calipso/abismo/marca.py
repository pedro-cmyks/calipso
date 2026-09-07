"""La gramatica de la marca del abismo -- spec 2026-09-07, seccion 5.

Gramatica CERRADA y en un solo lugar: esta regex la comparten el filtro de
streaming (plan 1b) y el detector one-shot del banco. No hay fallback "sin
fuente cae a memoria": lo que no matchea la lista es ilegible, se retira con
aviso y se mide como tal.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ABRE = "⟦"    # los mismos corchetes que la marca de foco (mapa/foco.py)
CIERRA = "⟧"
FUENTES = ("memoria", "chats", "proyecto")
MAX_PREGUNTA = 160  # chars del cuerpo entre "abismo:" y el cierre

# El cuerpo no puede contener el corchete de cierre; el tope de la regex va
# holgado (el exacto lo valida parsear) para que una marca larga se detecte
# como marca ilegible y no se escape entera al texto.
PATRON = re.compile(
    re.escape(ABRE) + r"abismo:([^" + CIERRA + r"]{1,400})" + re.escape(CIERRA))


@dataclass(frozen=True)
class Marca:
    fuente: str
    resto: str


def parsear(cuerpo: str) -> Marca | None:
    """El cuerpo es lo que va entre 'abismo:' y el cierre. None = ilegible."""
    cuerpo = cuerpo.strip()
    if not cuerpo or len(cuerpo) > MAX_PREGUNTA:
        return None
    partes = cuerpo.split(None, 1)
    fuente = partes[0].lower()
    if fuente not in FUENTES:
        return None
    resto = partes[1].strip() if len(partes) > 1 else ""
    if not resto:
        return None  # toda fuente exige contenido (proyecto: al menos el nombre)
    return Marca(fuente=fuente, resto=resto)


def encontrar(texto: str) -> list[Marca | None]:
    """Todas las marcas de un texto, en orden. None por cada ilegible."""
    return [parsear(m.group(1)) for m in PATRON.finditer(texto)]
