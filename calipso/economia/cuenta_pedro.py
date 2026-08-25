"""
calipso/economia/cuenta_pedro.py — Las cuatro salidas de la cuenta de Pedro.

La cuenta vive en el libro general (la escribe solo el kernel); estas
funciones son las UNICAS formas tipadas de sacar plata de ella (spec 3.2).
"""
from __future__ import annotations

from .kernel import Kernel, OperacionInvalida
from .tipos import Asiento, CUENTA_PEDRO, TESORO


def retirar(k: Kernel, ts: str, semana: str, monto: int) -> Asiento:
    return k.destruir(ts, semana, CUENTA_PEDRO, monto, motivo="retiro_pedro")


def reinyectar(k: Kernel, ts: str, semana: str, monto: int) -> Asiento:
    return k.transferir(ts, semana, CUENTA_PEDRO, TESORO, monto,
                        motivo="reinyeccion")


def financiar_personal(k: Kernel, ts: str, semana: str, departamento: str,
                       monto: int) -> Asiento:
    if not departamento.startswith("personal:"):
        raise OperacionInvalida(
            f"solo se financian departamentos personal:* — {departamento!r}")
    return k.transferir(ts, semana, CUENTA_PEDRO, departamento, monto,
                        motivo="financiacion_personal")


def rescatar(k: Kernel, ts: str, semana: str, departamento: str, monto: int,
             firma: dict) -> Asiento:
    if not firma:
        raise OperacionInvalida("rescate exige firma de Pedro")
    return k.transferir(ts, semana, CUENTA_PEDRO, departamento, monto,
                        motivo="rescate",
                        detalle_extra={"rescate": True, "firma": firma})
