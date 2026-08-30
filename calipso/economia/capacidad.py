"""
calipso/economia/capacidad.py — Suscripciones como capacidad revendida.

Las monedas miden plata; la cuota mide capacidad (spec 4.2). Este modulo
es pura derivacion: la configuracion de cada suscripcion (con la reserva
personal de Pedro prorrateada fuera de la economia de la fabrica) y las
funciones que pliegan consumo, precio por escasez y recaudacion desde el
libro. Quien ESCRIBE compras es el Mercado.
"""
from __future__ import annotations

from dataclasses import dataclass

from .tipos import Asiento, TipoAsiento, DIRECCION, es_nombre_suscripcion

SEMANAS_POR_CICLO = 4


class ErrorCapacidad(Exception):
    pass


def _entero_positivo(valor: int, nombre: str) -> None:
    if not isinstance(valor, int) or isinstance(valor, bool) or valor <= 0:
        raise ErrorCapacidad(f"{nombre} debe ser entero positivo: {valor!r}")


@dataclass(frozen=True)
class Suscripcion:
    nombre: str
    costo_mensual_mm: int
    capacidad_ciclo: int
    reserva_personal: int
    costo_api_mm_por_unidad: int

    def __post_init__(self):
        # El nombre es el que va a nombrar las cuentas de cristal
        # (`cristal:<nombre>:<zona>`), asi que se valida ACA, contra la
        # misma gramatica del libro. Antes se construia cualquier cosa
        # —"Claude_Max", "claude max"— y el fallo llegaba tarde, en el
        # append, como `AsientoInvalido`: una excepcion de otra capa, que
        # el pagador no cuenta entre las economicas y que por lo tanto
        # rompia el dispatch en vez de aparcar el cargo.
        if not es_nombre_suscripcion(self.nombre):
            raise ErrorCapacidad(
                f"nombre de suscripcion invalido: {self.nombre!r} "
                "(minusculas, digitos, guion y guion bajo)")
        _entero_positivo(self.costo_mensual_mm, "costo_mensual_mm")
        _entero_positivo(self.capacidad_ciclo, "capacidad_ciclo")
        _entero_positivo(self.costo_api_mm_por_unidad, "costo_api_mm_por_unidad")
        if (not isinstance(self.reserva_personal, int)
                or isinstance(self.reserva_personal, bool)
                or not 0 <= self.reserva_personal < self.capacidad_ciclo):
            raise ErrorCapacidad(
                f"reserva_personal fuera de [0, capacidad): {self.reserva_personal!r}")

    @property
    def capacidad_fabrica(self) -> int:
        return self.capacidad_ciclo - self.reserva_personal

    @property
    def costo_fabrica_mm(self) -> int:
        return self.costo_mensual_mm * self.capacidad_fabrica // self.capacidad_ciclo

    @property
    def precio_base_mm(self) -> int:
        return max(1, self.costo_fabrica_mm // self.capacidad_fabrica)

    @property
    def tope_mm(self) -> int:
        return self.costo_api_mm_por_unidad * 9 // 10


def semanas_operativas(asientos: list[Asiento]) -> list[str]:
    return sorted({a.semana for a in asientos
                   if a.tipo is TipoAsiento.EMISION_PT})


def posicion_ciclo(semana: str, semanas_ops: list[str]) -> tuple[int, int]:
    """(indice de ciclo, fraccion transcurrida en %) de una semana operativa."""
    try:
        i = semanas_ops.index(semana)
    except ValueError:
        raise ErrorCapacidad(f"semana no operativa: {semana}") from None
    return i // SEMANAS_POR_CICLO, (i % SEMANAS_POR_CICLO + 1) * 100 // SEMANAS_POR_CICLO


def semanas_del_ciclo(ciclo: int, semanas_ops: list[str]) -> list[str]:
    return semanas_ops[ciclo * SEMANAS_POR_CICLO:(ciclo + 1) * SEMANAS_POR_CICLO]


def _compras(asientos: list[Asiento], nombre: str, semanas: list[str]):
    for a in asientos:
        if (a.tipo is TipoAsiento.TRANSFERENCIA and a.destino == DIRECCION
                and a.detalle.get("suscripcion") == nombre
                and a.semana in semanas):
            yield a


def consumo_fabrica(asientos: list[Asiento], nombre: str,
                    semanas: list[str]) -> int:
    return sum(a.detalle["unidades"] for a in _compras(asientos, nombre, semanas))


def consumo_personal(asientos: list[Asiento], nombre: str,
                     semanas: list[str]) -> int:
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.APUNTE
               and a.detalle.get("nota") == "consumo_personal_capacidad"
               and a.detalle.get("suscripcion") == nombre
               and a.semana in semanas)


def precio_unidad_mm(sus: Suscripcion, consumido: int, fraccion_pct: int) -> int:
    """Precio por escasez (spec 4.2): base x factor, tope en 0,9 x API."""
    r_pct = consumido * 100 * 100 // (sus.capacidad_fabrica * fraccion_pct)
    return min(sus.precio_base_mm * max(100, r_pct) // 100, sus.tope_mm)


def recaudacion(asientos: list[Asiento], nombre: str,
                semanas: list[str]) -> int:
    return sum(a.monto for a in _compras(asientos, nombre, semanas))
