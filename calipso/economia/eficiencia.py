"""
calipso/economia/eficiencia.py — Resultado por unidad consumida.

Cada venta con trabajo de origen se prorratea entre los consumos de ese
trabajo, proporcional al costo API equivalente de cada consumo (spec 4.2).
El numerador es siempre senal exterior (subtipo venta); el capital y las
ventas sin trabajo no atribuyen nada.
"""
from __future__ import annotations

from .capacidad import Suscripcion
from .tipos import Asiento, DIRECCION, SubtipoAcunacion, TipoAsiento


def ventas_por_trabajo(asientos: list[Asiento],
                       semanas: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in asientos:
        if (a.tipo is TipoAsiento.ACUNACION
                and a.subtipo == SubtipoAcunacion.VENTA.value
                and a.semana in semanas and a.detalle.get("trabajo")):
            id = a.detalle["trabajo"]
            out[id] = out.get(id, 0) + a.monto
    return out


def costos_de_trabajo(asientos: list[Asiento], id: str,
                      suscripciones: dict[str, Suscripcion],
                      semanas: list[str] | None = None) -> dict[str, int]:
    ref = f"trabajo:{id}"
    out: dict[str, int] = {}
    for a in asientos:
        if a.ref != ref:
            continue
        if semanas is not None and a.semana not in semanas:
            continue
        if (a.tipo is TipoAsiento.DESTRUCCION
                and a.detalle.get("motivo") == "api"):
            out["api"] = out.get("api", 0) + a.monto
        elif (a.tipo is TipoAsiento.TRANSFERENCIA and a.destino == DIRECCION
                and a.detalle.get("suscripcion") in suscripciones):
            nombre = a.detalle["suscripcion"]
            sus = suscripciones[nombre]
            clave = f"sus:{nombre}"
            out[clave] = out.get(clave, 0) + \
                a.detalle["unidades"] * sus.costo_api_mm_por_unidad
    return out


def atribucion_por_suscripcion(asientos: list[Asiento], semanas: list[str],
                               suscripciones: dict[str, Suscripcion]
                               ) -> dict[str, int]:
    out: dict[str, int] = {}
    for id, venta in ventas_por_trabajo(asientos, semanas).items():
        costos = costos_de_trabajo(asientos, id, suscripciones)
        total = sum(costos.values())
        if total == 0:
            continue
        for clave, costo in costos.items():
            if clave.startswith("sus:"):
                nombre = clave[4:]
                out[nombre] = out.get(nombre, 0) + venta * costo // total
    return out


def eficiencia_pormil(atribuido_mm: int, consumido_api_mm: int) -> int:
    if consumido_api_mm <= 0:
        return 0
    return atribuido_mm * 1000 // consumido_api_mm


def eficiencia_suscripcion(asientos: list[Asiento], sus: Suscripcion,
                           semanas: list[str],
                           suscripciones: dict[str, Suscripcion]) -> int:
    atribuida = atribucion_por_suscripcion(asientos, semanas,
                                           suscripciones).get(sus.nombre, 0)
    consumido = sum(a.detalle["unidades"] * sus.costo_api_mm_por_unidad
                    for a in asientos
                    if a.tipo is TipoAsiento.TRANSFERENCIA
                    and a.destino == DIRECCION
                    and a.detalle.get("suscripcion") == sus.nombre
                    and a.semana in semanas)
    return eficiencia_pormil(atribuida, consumido)


def costo_api_directo(asientos: list[Asiento], dep_cuenta: str,
                      semanas: list[str],
                      suscripciones: dict[str, Suscripcion]) -> int:
    """Gasto directo del departamento (sin trabajos) en API equivalente."""
    total = 0
    for a in asientos:
        if a.origen != dep_cuenta or a.semana not in semanas:
            continue
        if (a.tipo is TipoAsiento.DESTRUCCION
                and a.detalle.get("motivo") == "api"):
            total += a.monto
        elif (a.tipo is TipoAsiento.TRANSFERENCIA and a.destino == DIRECCION
                and a.detalle.get("suscripcion") in suscripciones):
            sus = suscripciones[a.detalle["suscripcion"]]
            total += a.detalle["unidades"] * sus.costo_api_mm_por_unidad
    return total


def eficiencia_departamento(asientos: list[Asiento], dep_cuenta: str,
                            semanas: list[str],
                            suscripciones: dict[str, Suscripcion],
                            duenos: dict[str, str]) -> int:
    ventas = sum(v for id, v in ventas_por_trabajo(asientos, semanas).items()
                 if duenos.get(id) == dep_cuenta)
    consumido = costo_api_directo(asientos, dep_cuenta, semanas, suscripciones)
    trabajos = {id for id, d in duenos.items() if d == dep_cuenta}
    for id in trabajos:
        consumido += sum(costos_de_trabajo(asientos, id, suscripciones,
                                           semanas).values())
    return eficiencia_pormil(ventas, consumido)
