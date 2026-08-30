"""calipso/economia — kernel de la economia de la fabrica (spec 2026-08-24).

Contrato de escritor unico: exactamente una instancia de Kernel/Libro por
archivo y por proceso; escritores concurrentes corrompen la cadena de seq.
El locking llega con la integracion del servidor (Plan 3).
"""
from __future__ import annotations

import os
import pathlib

from . import balances, cristal, cuenta_pedro, pt, tipos  # noqa: F401
from . import bus, capacidad, cierre, departamentos, direccion, eficiencia, mercado  # noqa: F401
from . import candado, cola, operacion, pagador, personal, reloj  # noqa: F401
from .kernel import Kernel, OperacionInvalida, SinSaldo  # noqa: F401
from .libro import Libro, LibroCorrupto                  # noqa: F401

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))
RUTA_LIBRO_DEFECTO = CALIPSO_HOME / "economia" / "libro.jsonl"
