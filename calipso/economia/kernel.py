"""
calipso/economia/kernel.py — Operaciones validadas sobre el libro.

El Kernel es la unica puerta de escritura de la economia: valida
invariantes (sin sobregiro, acunacion con evidencia) antes de apilar
asientos. No conoce departamentos ni politicas: eso vive arriba.
"""
from __future__ import annotations

from . import balances as bal
from .libro import Libro
from .tipos import (AsientoInvalido, Asiento, Divisa, SubtipoAcunacion,
                    TipoAsiento, TESORO)


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

    def _append(self, **campos) -> Asiento:
        try:
            return self.libro.append(**campos)
        except AsientoInvalido as exc:
            raise OperacionInvalida(str(exc)) from exc

    # -- operaciones -------------------------------------------------------
    def acunar(self, ts: str, semana: str, destino: str, monto: int,
               subtipo: SubtipoAcunacion, evidencia: dict) -> Asiento:
        if not evidencia:
            raise OperacionInvalida("acunar exige evidencia (invariante 4)")
        if not isinstance(subtipo, SubtipoAcunacion):
            raise OperacionInvalida(f"subtipo debe ser SubtipoAcunacion: {subtipo!r}")
        return self._append(
            ts=ts, semana=semana, tipo=TipoAsiento.ACUNACION,
            divisa=Divisa.MONEDA, monto=monto, destino=destino,
            subtipo=subtipo.value, detalle={"evidencia": evidencia})

    def destruir(self, ts: str, semana: str, origen: str, monto: int,
                 motivo: str, ref: str | None = None) -> Asiento:
        self._exigir(origen, monto)
        return self._append(
            ts=ts, semana=semana, tipo=TipoAsiento.DESTRUCCION,
            divisa=Divisa.MONEDA, monto=monto, origen=origen, ref=ref,
            detalle={"motivo": motivo})

    def transferir(self, ts: str, semana: str, origen: str, destino: str,
                   monto: int, motivo: str, ref: str | None = None,
                   detalle_extra: dict | None = None) -> Asiento:
        self._exigir(origen, monto)
        detalle = {"motivo": motivo} | (detalle_extra or {})
        return self._append(
            ts=ts, semana=semana, tipo=TipoAsiento.TRANSFERENCIA,
            divisa=Divisa.MONEDA, monto=monto, origen=origen,
            destino=destino, ref=ref, detalle=detalle)

    # -- escrow ------------------------------------------------------------
    def _reserva(self, ref: str) -> tuple[str, int]:
        r = bal.reservas_activas(self.libro.asientos())
        if ref not in r:
            raise OperacionInvalida(f"reserva inexistente o ya cerrada: {ref}")
        return r[ref]

    def reservar(self, ts: str, semana: str, cuenta: str, monto: int,
                 ref: str) -> Asiento:
        if ref in bal.reservas_activas(self.libro.asientos()):
            raise OperacionInvalida(f"ref de reserva repetida: {ref}")
        self._exigir(cuenta, monto)
        return self._append(
            ts=ts, semana=semana, tipo=TipoAsiento.RESERVA,
            divisa=Divisa.MONEDA, monto=monto, origen=cuenta, ref=ref)

    def liberar(self, ts: str, semana: str, ref: str) -> Asiento:
        cuenta, monto = self._reserva(ref)
        return self._append(
            ts=ts, semana=semana, tipo=TipoAsiento.LIBERACION,
            divisa=Divisa.MONEDA, monto=monto, ref=ref,
            detalle={"cuenta": cuenta})

    def ejecutar_reserva(self, ts: str, semana: str, ref: str, destino: str,
                         detalle_extra: dict | None = None) -> Asiento:
        cuenta, monto = self._reserva(ref)
        return self._append(
            ts=ts, semana=semana, tipo=TipoAsiento.EJECUCION_RESERVA,
            divisa=Divisa.MONEDA, monto=monto, origen=cuenta,
            destino=destino, ref=ref, detalle=(detalle_extra or {}))

    # -- acreencias ----------------------------------------------------------
    def registrar_acreencia(self, ts: str, semana: str, acreedor: str,
                            deudor: str, monto: int, ref: str) -> Asiento:
        return self._append(
            ts=ts, semana=semana, tipo=TipoAsiento.ACREENCIA,
            divisa=Divisa.MONEDA, monto=monto, ref=ref,
            detalle={"acreedor": acreedor, "deudor": deudor})

    def acreencias_pendientes(self, deudor: str) -> list[tuple[str, str, int]]:
        pagos: dict[str, int] = {}
        acre: list[tuple[str, str, int]] = []
        for a in self.libro.asientos():
            if (a.tipo is TipoAsiento.ACREENCIA
                    and a.detalle.get("deudor") == deudor):
                acre.append((a.ref, a.detalle["acreedor"], a.monto))
            elif a.tipo is TipoAsiento.TRANSFERENCIA and a.ref:
                pagos[a.ref] = pagos.get(a.ref, 0) + a.monto
        out = []
        for ref, acreedor, monto in acre:
            pend = monto - pagos.get(ref, 0)
            if pend > 0:
                out.append((ref, acreedor, pend))
        return out

    def liquidar(self, ts: str, semana: str, cuenta: str) -> list[Asiento]:
        out: list[Asiento] = []
        for ref, acreedor, pend in self.acreencias_pendientes(cuenta):
            pago = min(pend, self.disponible(cuenta))
            if pago > 0:
                out.append(self.transferir(ts, semana, cuenta, acreedor,
                                           pago, motivo="liquidacion",
                                           ref=ref))
        resto = self.disponible(cuenta)
        if resto > 0:
            out.append(self.transferir(ts, semana, cuenta, TESORO, resto,
                                       motivo="liquidacion_remanente"))
        return out
