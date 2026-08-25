"""
calipso/economia/balances.py — Derivacion pura de estado desde el libro.

Ningun balance se guarda: todo se pliega desde los asientos, siempre.
Eso hace los numeros reproducibles (misma historia, mismo numero) y
elimina la clase entera de bugs de "el cache dice otra cosa".
"""
from __future__ import annotations

from collections import defaultdict

from .tipos import Asiento, Divisa, TipoAsiento

_SIN_EFECTO = {TipoAsiento.APUNTE, TipoAsiento.ACREENCIA,
               TipoAsiento.RESERVA, TipoAsiento.LIBERACION}


def saldos(asientos: list[Asiento]) -> dict[tuple[str, Divisa], int]:
    s: dict[tuple[str, Divisa], int] = defaultdict(int)
    for a in asientos:
        if a.tipo in _SIN_EFECTO:
            continue
        if a.origen:
            s[(a.origen, a.divisa)] -= a.monto
        if a.destino:
            s[(a.destino, a.divisa)] += a.monto
    return dict(s)


def reservas_activas(asientos: list[Asiento]) -> dict[str, tuple[str, int]]:
    r: dict[str, tuple[str, int]] = {}
    for a in asientos:
        if a.tipo is TipoAsiento.RESERVA:
            r[a.ref] = (a.origen, a.monto)
        elif a.tipo in (TipoAsiento.LIBERACION, TipoAsiento.EJECUCION_RESERVA):
            r.pop(a.ref, None)
    return r


def disponible(asientos: list[Asiento], cuenta: str, divisa: Divisa) -> int:
    base = saldos(asientos).get((cuenta, divisa), 0)
    if divisa is Divisa.MONEDA:
        base -= sum(m for (cta, m) in reservas_activas(asientos).values()
                    if cta == cuenta)
    return base
