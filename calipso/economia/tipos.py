"""
calipso/economia/tipos.py — Tipos base del libro contable.

Dos divisas: la moneda (1 moneda = 1.000 milimonedas = 1 USD) y el
pedro-token (1 PT = 1.000 mili-PT = 1 hora firmable de Pedro). Todos los
montos son enteros; el estado se deriva del libro, nunca se edita.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from enum import Enum

MILIS = 1000

TESORO = "tesoro"
CUENTA_PEDRO = "cuenta_pedro"
DIRECCION = "direccion"
POOL_PT_FABRICA = "pt:fabrica"
POOL_PT_PERSONAL = "pt:personal"

_RE_SEMANA = re.compile(r"^\d{4}-W\d{2}$")


class Divisa(str, Enum):
    MONEDA = "moneda"
    PT = "pt"


class TipoAsiento(str, Enum):
    ACUNACION = "acunacion"
    DESTRUCCION = "destruccion"
    TRANSFERENCIA = "transferencia"
    RESERVA = "reserva"
    LIBERACION = "liberacion"
    EJECUCION_RESERVA = "ejecucion_reserva"
    EMISION_PT = "emision_pt"
    CONSUMO_PT = "consumo_pt"
    EXPIRACION_PT = "expiracion_pt"
    APUNTE = "apunte"
    ACREENCIA = "acreencia"


class SubtipoAcunacion(str, Enum):
    VENTA = "venta"
    CAPITAL = "capital"


class AsientoInvalido(Exception):
    pass


_POOLS_PT = {POOL_PT_FABRICA, POOL_PT_PERSONAL}


@dataclass(frozen=True)
class Asiento:
    seq: int
    ts: str
    semana: str
    tipo: TipoAsiento
    divisa: Divisa
    monto: int
    origen: str | None = None
    destino: str | None = None
    subtipo: str | None = None
    ref: str | None = None
    detalle: dict = field(default_factory=dict, compare=True)

    def validar(self) -> None:
        if not isinstance(self.monto, int) or isinstance(self.monto, bool) \
                or self.monto <= 0:
            raise AsientoInvalido(f"monto debe ser entero positivo: {self.monto!r}")
        if not _RE_SEMANA.match(self.semana):
            raise AsientoInvalido(f"semana debe ser YYYY-Www: {self.semana!r}")
        t = self.tipo
        if t is TipoAsiento.ACUNACION:
            if self.divisa is not Divisa.MONEDA or not self.destino or self.origen:
                raise AsientoInvalido("acunacion: divisa moneda, destino si, origen no")
            if self.subtipo not in {s.value for s in SubtipoAcunacion}:
                raise AsientoInvalido(f"acunacion exige subtipo venta|capital: {self.subtipo!r}")
            if not self.detalle.get("evidencia"):
                raise AsientoInvalido("acunacion exige detalle['evidencia'] (invariante 4)")
        elif t is TipoAsiento.DESTRUCCION:
            if self.divisa is not Divisa.MONEDA:
                raise AsientoInvalido("destruccion es solo en monedas: el PT tiene su propio tipo, expiracion_pt")
            if not self.origen or self.destino:
                raise AsientoInvalido("destruccion: origen si, destino no")
        elif t in (TipoAsiento.TRANSFERENCIA, TipoAsiento.EJECUCION_RESERVA):
            if t is TipoAsiento.TRANSFERENCIA and self.divisa is not Divisa.MONEDA:
                raise AsientoInvalido("transferencia es solo en monedas: el PT se emite, consume y expira con sus propios tipos")
            if not self.origen or not self.destino or self.origen == self.destino:
                raise AsientoInvalido(f"{t.value}: origen y destino distintos requeridos")
            if t is TipoAsiento.EJECUCION_RESERVA:
                if self.divisa is not Divisa.MONEDA:
                    raise AsientoInvalido("el escrow es solo en monedas: los PT se consumen del pool, nunca se reservan")
                if not self.ref:
                    raise AsientoInvalido("ejecucion_reserva exige ref de la reserva")
        elif t is TipoAsiento.RESERVA:
            if self.divisa is not Divisa.MONEDA:
                raise AsientoInvalido("el escrow es solo en monedas: los PT se consumen del pool, nunca se reservan")
            if not self.origen or not self.ref:
                raise AsientoInvalido("reserva exige origen y ref")
        elif t is TipoAsiento.LIBERACION:
            if self.divisa is not Divisa.MONEDA:
                raise AsientoInvalido("el escrow es solo en monedas: los PT se consumen del pool, nunca se reservan")
            if not self.ref:
                raise AsientoInvalido("liberacion exige ref")
        elif t is TipoAsiento.EMISION_PT:
            if self.divisa is not Divisa.PT or self.destino not in _POOLS_PT:
                raise AsientoInvalido("emision_pt: divisa pt y destino un pool pt:*")
        elif t in (TipoAsiento.CONSUMO_PT, TipoAsiento.EXPIRACION_PT):
            if self.divisa is not Divisa.PT or self.origen not in _POOLS_PT:
                raise AsientoInvalido(f"{t.value}: divisa pt y origen un pool pt:*")
        elif t is TipoAsiento.ACREENCIA:
            d = self.detalle
            if not d.get("acreedor") or not d.get("deudor"):
                raise AsientoInvalido("acreencia exige detalle acreedor y deudor")
            if not self.ref:
                raise AsientoInvalido("acreencia exige ref")

    def a_json(self) -> str:
        d = asdict(self)
        d["tipo"] = self.tipo.value
        d["divisa"] = self.divisa.value
        return json.dumps(d, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def de_json(linea: str) -> "Asiento":
        d = json.loads(linea)
        d["tipo"] = TipoAsiento(d["tipo"])
        d["divisa"] = Divisa(d["divisa"])
        return Asiento(**d)
