"""
calipso/economia/kernel.py — Operaciones validadas sobre el libro.

El Kernel es la unica puerta de escritura de la economia: valida
invariantes (sin sobregiro, acunacion con evidencia) antes de apilar
asientos. No conoce departamentos ni politicas: eso vive arriba.
"""
from __future__ import annotations

from . import balances as bal
from .libro import Libro
from .tipos import Asiento, Divisa, SubtipoAcunacion, TipoAsiento


class OperacionInvalida(Exception):
    pass


class SinSaldo(OperacionInvalida):
    pass


class Kernel:
    def __init__(self, libro: Libro):
        self.libro = libro

    # -- consultas ---------------------------------------------------------
    def saldo(self, cuenta: str, divisa: Divisa = Divisa.MONEDA) -> int:
        return bal.saldos(self.libro.asientos()).get((cuenta, divisa), 0)

    def disponible(self, cuenta: str, divisa: Divisa = Divisa.MONEDA) -> int:
        return bal.disponible(self.libro.asientos(), cuenta, divisa)

    def _exigir(self, cuenta: str, monto: int, divisa: Divisa = Divisa.MONEDA):
        disp = self.disponible(cuenta, divisa)
        if monto > disp:
            raise SinSaldo(f"{cuenta}: pide {monto}, disponible {disp}")

    # -- operaciones -------------------------------------------------------
    def acunar(self, ts: str, semana: str, destino: str, monto: int,
               subtipo: SubtipoAcunacion, evidencia: dict) -> Asiento:
        if not evidencia:
            raise OperacionInvalida("acunar exige evidencia (invariante 4)")
        return self.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.ACUNACION,
            divisa=Divisa.MONEDA, monto=monto, destino=destino,
            subtipo=subtipo.value, detalle={"evidencia": evidencia})

    def destruir(self, ts: str, semana: str, origen: str, monto: int,
                 motivo: str, ref: str | None = None) -> Asiento:
        self._exigir(origen, monto)
        return self.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.DESTRUCCION,
            divisa=Divisa.MONEDA, monto=monto, origen=origen, ref=ref,
            detalle={"motivo": motivo})

    def transferir(self, ts: str, semana: str, origen: str, destino: str,
                   monto: int, motivo: str, ref: str | None = None,
                   detalle_extra: dict | None = None) -> Asiento:
        self._exigir(origen, monto)
        detalle = {"motivo": motivo} | (detalle_extra or {})
        return self.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.TRANSFERENCIA,
            divisa=Divisa.MONEDA, monto=monto, origen=origen,
            destino=destino, ref=ref, detalle=detalle)
