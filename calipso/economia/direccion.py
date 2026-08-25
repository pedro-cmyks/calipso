"""
calipso/economia/direccion.py — El mandato de direccion.

Direccion asigna presupuestos desde el tesoro dentro de un mandato con
umbral ACUMULADO por departamento y semana (un umbral por asiento se
evade fraccionando — spec 8), paga las cartas de sistema con su propio
presupuesto de PT, y adelanta compuertas obligatorias de departamentos
sin caja como credito prioritario (invariante 6).
"""
from __future__ import annotations

from . import departamentos as deps
from . import pt
from .mercado import Mercado
from .tipos import (Asiento, CUENTA_PEDRO, DIRECCION, Divisa,
                    POOL_PT_FABRICA, TESORO, TipoAsiento)

UMBRAL_MANDATO_MM = 100_000


class ErrorDireccion(Exception):
    pass


def asignado_semana(asientos, dep_cuenta: str, semana: str) -> int:
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.TRANSFERENCIA
               and a.origen == TESORO and a.destino == dep_cuenta
               and a.detalle.get("motivo") == "presupuesto"
               and a.semana == semana)


def asignar_presupuesto(mercado: Mercado, ts: str, semana: str,
                        dep_cuenta: str, mm: int, firma: dict | None = None,
                        umbral_mm: int = UMBRAL_MANDATO_MM) -> Asiento:
    mercado.dep_por_cuenta(dep_cuenta)  # debe existir
    asientos = mercado.k.libro.asientos()
    if deps.es_congelado(asientos, dep_cuenta):
        raise ErrorDireccion(f"un congelado no recibe presupuesto: {dep_cuenta}")
    acumulado = asignado_semana(asientos, dep_cuenta, semana)
    if acumulado + mm > umbral_mm and not firma:
        raise ErrorDireccion(
            f"mandato excedido sin firma: {acumulado}+{mm} > {umbral_mm} "
            f"(compuerta d)")
    detalle = {"firma": firma} if firma else None
    return mercado.k.transferir(ts, semana, TESORO, dep_cuenta, mm,
                                motivo="presupuesto", detalle_extra=detalle)


def _pagar_pt(mercado: Mercado, ts: str, semana: str, mpt: int,
              ref: str) -> tuple[list[Asiento], int]:
    """Pre-valida AMBOS recursos antes del primer append: un libro
    append-only no tiene rollback, asi que el orden es validar todo,
    despues escribir."""
    k = mercado.k
    tipo = pt.tipo_de_cambio(k.libro.asientos(), semana)
    mm = mpt * tipo // 1000
    if mpt > k.saldo(POOL_PT_FABRICA, Divisa.PT):
        raise ErrorDireccion(
            f"pool de PT insuficiente para la carta: pide {mpt}, "
            f"hay {k.saldo(POOL_PT_FABRICA, Divisa.PT)}")
    if mm > k.disponible(DIRECCION):
        raise ErrorDireccion(
            f"direccion sin caja para la carta: pide {mm}, "
            f"disponible {k.disponible(DIRECCION)}")
    transfer = k.transferir(ts, semana, DIRECCION, CUENTA_PEDRO, mm,
                            motivo="carta_sistema", ref=ref)
    consumo = pt.consumir_fabrica(k, ts, semana, mpt, ref=ref,
                                  pagador=DIRECCION)
    return [transfer, consumo], mm


def pagar_carta_sistema(mercado: Mercado, ts: str, semana: str, mpt: int,
                        ref: str) -> list[Asiento]:
    asientos, _ = _pagar_pt(mercado, ts, semana, mpt, ref)
    return asientos


def adelantar_obligatoria(mercado: Mercado, ts: str, semana: str,
                          dep_cuenta: str, mpt: int, ref: str) -> list[Asiento]:
    asientos, mm = _pagar_pt(mercado, ts, semana, mpt, ref)
    acr = mercado.k.registrar_acreencia(ts, semana, DIRECCION, dep_cuenta,
                                        mm, ref=f"adelanto:{ref}")
    return asientos + [acr]
