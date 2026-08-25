# calipso/economia/pt.py
"""
calipso/economia/pt.py — La divisa del tiempo de Pedro.

Emision semanal fija (cuota firmable), reserva personal apartada primero,
consumo por firma servida, expiracion al cierre: el tiempo no se acumula.
El tipo de cambio es un pliegue deterministico de la historia (task 8).
"""
from __future__ import annotations

from .kernel import Kernel
from .tipos import (Asiento, Divisa, SubtipoAcunacion, TipoAsiento,
                    POOL_PT_FABRICA, POOL_PT_PERSONAL)


class ErrorPT(Exception):
    pass


def _ya_emitida(k: Kernel, semana: str) -> bool:
    return any(a.tipo is TipoAsiento.EMISION_PT and a.semana == semana
               for a in k.libro.asientos())


def emitir_semana(k: Kernel, ts: str, semana: str, cuota_firmable_mpt: int,
                  reserva_personal_mpt: int) -> list[Asiento]:
    if not 0 <= reserva_personal_mpt <= cuota_firmable_mpt:
        raise ErrorPT("reserva personal fuera de rango [0, cuota]")
    if _ya_emitida(k, semana):
        raise ErrorPT(f"semana ya emitida: {semana}")
    for pool in (POOL_PT_FABRICA, POOL_PT_PERSONAL):
        if k.saldo(pool, Divisa.PT) != 0:
            raise ErrorPT(f"pool {pool} sin cerrar: expirar antes de emitir")
    out = []
    fabrica = cuota_firmable_mpt - reserva_personal_mpt
    if fabrica:
        out.append(k.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.EMISION_PT,
            divisa=Divisa.PT, monto=fabrica, destino=POOL_PT_FABRICA))
    if reserva_personal_mpt:
        out.append(k.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.EMISION_PT,
            divisa=Divisa.PT, monto=reserva_personal_mpt,
            destino=POOL_PT_PERSONAL))
    return out


def _consumir(k: Kernel, ts: str, semana: str, pool: str, monto_mpt: int,
              ref: str | None, detalle: dict) -> Asiento:
    if monto_mpt > k.saldo(pool, Divisa.PT):
        raise ErrorPT(f"pool {pool}: pide {monto_mpt}, "
                      f"hay {k.saldo(pool, Divisa.PT)}")
    return k.libro.append(
        ts=ts, semana=semana, tipo=TipoAsiento.CONSUMO_PT,
        divisa=Divisa.PT, monto=monto_mpt, origen=pool, ref=ref,
        detalle=detalle)


def consumir_fabrica(k: Kernel, ts: str, semana: str, monto_mpt: int,
                     ref: str, pagador: str) -> Asiento:
    return _consumir(k, ts, semana, POOL_PT_FABRICA, monto_mpt, ref,
                     {"pagador": pagador})


def consumir_personal(k: Kernel, ts: str, semana: str, monto_mpt: int,
                      departamento: str, tipo_vigente_mm: int) -> list[Asiento]:
    consumo = _consumir(k, ts, semana, POOL_PT_PERSONAL, monto_mpt, None,
                        {"departamento": departamento})
    out = [consumo]
    costo = monto_mpt * tipo_vigente_mm // 1000
    if costo > 0:  # un apunte de monto 0 seria un asiento invalido
        out.append(k.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.APUNTE,
            divisa=Divisa.MONEDA, monto=costo,
            detalle={"nota": "costo_oportunidad", "departamento": departamento,
                     "tipo_mm": tipo_vigente_mm}))
    return out


def expirar_pools(k: Kernel, ts: str, semana: str) -> list[Asiento]:
    out = []
    for pool in (POOL_PT_FABRICA, POOL_PT_PERSONAL):
        resto = k.saldo(pool, Divisa.PT)
        if resto:
            out.append(k.libro.append(
                ts=ts, semana=semana, tipo=TipoAsiento.EXPIRACION_PT,
                divisa=Divisa.PT, monto=resto, origen=pool))
    return out


def tipo_de_cambio(asientos: list[Asiento], hasta_semana: str,
                   ventana: int = 8, banda_pct: int = 25,
                   arranque_mm: int = 5000, minimo_mm: int = 1000,
                   min_semanas_consumo: int = 4) -> int:
    """Pliegue deterministico del contrato de spec 3.2.

    Cociente de totales sobre las ultimas `ventana` semanas operativas
    (semanas con emision de PT), recalculado en orden semana a semana para
    que la banda encadene igual siempre: misma historia, mismo numero.
    """
    semanas = sorted({a.semana for a in asientos
                      if a.tipo is TipoAsiento.EMISION_PT
                      and a.semana <= hasta_semana})
    ventas_por_semana: dict[str, int] = {}
    consumo_por_semana: dict[str, int] = {}
    for a in asientos:
        if a.semana > hasta_semana:
            continue
        if (a.tipo is TipoAsiento.ACUNACION
                and a.subtipo == SubtipoAcunacion.VENTA.value):
            ventas_por_semana[a.semana] = \
                ventas_por_semana.get(a.semana, 0) + a.monto
        elif (a.tipo is TipoAsiento.CONSUMO_PT
                and a.origen == POOL_PT_FABRICA):
            consumo_por_semana[a.semana] = \
                consumo_por_semana.get(a.semana, 0) + a.monto

    tipo = arranque_mm
    for i, sem in enumerate(semanas):
        vent = semanas[max(0, i + 1 - ventana):i + 1]
        consumo = sum(consumo_por_semana.get(s, 0) for s in vent)
        con_consumo = sum(1 for s in vent if consumo_por_semana.get(s, 0) > 0)
        if consumo == 0:
            pass  # regla (c): se mantiene
        elif con_consumo < min_semanas_consumo:
            tipo = arranque_mm  # regla (d)
        else:
            ventas = sum(ventas_por_semana.get(s, 0) for s in vent)
            objetivo = ventas * 1000 // consumo
            piso_banda = tipo * (100 - banda_pct) // 100
            techo_banda = tipo * (100 + banda_pct) // 100
            tipo = min(max(objetivo, piso_banda), techo_banda)  # regla (e)
        tipo = max(tipo, minimo_mm)  # regla (f)
    return tipo
