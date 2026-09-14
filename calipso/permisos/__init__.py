"""
calipso/permisos — El motor de permisos (spec de ojos y manos, seccion 5).

Un solo motor para todo lo que no se deshace solo: acunar monedas, correr
un comando fuera del allowlist, escribir afuera de las raices, matar un
proceso ajeno. La pregunta es la misma -- "esto no se deshace, lo hago?" --
asi que el lugar donde se decide tambien es uno solo.

  acciones.py  la tabla de niveles de 5.3 y las formas que se comparan
  almacen.py   lo que sobrevive al reinicio: permisos, solicitudes, rastro
  motor.py     evaluar(), responder(), y el registro de ejecutores
"""
from .acciones import (Accion, Contexto, ErrorPermisos, NIVEL_DIRECTO,
                       NIVEL_NUNCA, NIVEL_PREGUNTA, clasificar)
from .motor import (ESTADO_ESTACIONADA, ESTADO_NEGADO, ESTADO_PENDIENTE,
                    ESTADO_PERMITIDO, Resolucion, evaluar,
                    registrar_ejecutor, responder, vista)

__all__ = [
    "Accion", "Contexto", "ErrorPermisos", "Resolucion",
    "NIVEL_DIRECTO", "NIVEL_PREGUNTA", "NIVEL_NUNCA",
    "ESTADO_PERMITIDO", "ESTADO_PENDIENTE", "ESTADO_ESTACIONADA",
    "ESTADO_NEGADO",
    "clasificar", "evaluar", "responder", "registrar_ejecutor", "vista",
]

# la familia `goal` (spec goals 2026-09-13, seccion 8): se registra al
# importar el paquete, con red (si goals_hook no importa, el motor sigue
# sin la familia y una Accion goal cae en "familia desconocida" = pregunta)
try:
    from . import goal as _goal
    _goal.registrar()
except Exception:  # pragma: no cover
    pass
