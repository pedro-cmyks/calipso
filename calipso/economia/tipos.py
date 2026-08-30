"""
calipso/economia/tipos.py — Tipos base del libro contable.

Tres divisas: la moneda (1 moneda = 1.000 milimonedas = 1 USD), el
pedro-token (1 PT = 1.000 mili-PT = 1 hora firmable de Pedro) y el
cristal (1 cristal = 1 unidad de capacidad de una suscripcion). Todos los
montos son enteros; el estado se deriva del libro, nunca se edita.

La moneda mide PLATA: lo que sale de la cuenta bancaria de Pedro. El
cristal mide CAPACIDAD: los requests que la suscripcion ya pagada sirve
en el ciclo. Son cosas distintas y por eso son divisas distintas: gastar
un cristal no gasta una moneda, y un libro que las confunde cobra dos
veces lo que se pago una.
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

# Cristal: el prefijo y las DOS zonas. Dos cuentas por suscripcion y nada
# mas — la de la fabrica entera y la personal de Pedro. Sin bolsillos por
# departamento: hoy ningun departamento gasta capacidad por su cuenta
# (`trabajar` es un no-op declarado en server.py), asi que un bolsillo por
# departamento seria una cuenta que nadie mueve y un pliegue que mentir.
PREFIJO_CRISTAL = "cristal"
ZONA_CRISTAL_FABRICA = "fabrica"
ZONA_CRISTAL_PERSONAL = "personal"
ZONAS_CRISTAL = (ZONA_CRISTAL_FABRICA, ZONA_CRISTAL_PERSONAL)

_RE_SEMANA = re.compile(r"^\d{4}-W\d{2}$")
# El nombre de suscripcion admitido en una cuenta de cristal. Prohibe ":"
# (que haria ambigua la gramatica de la cuenta), espacios y mayusculas
# (dos nombres que solo difieren en la caja son la mejor forma de escribir
# dos cuentas creyendo que es una).
_RE_SUSCRIPCION = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class Divisa(str, Enum):
    MONEDA = "moneda"
    PT = "pt"
    CRISTAL = "cristal"


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
    EMISION_CRISTAL = "emision_cristal"
    CONSUMO_CRISTAL = "consumo_cristal"
    EXPIRACION_CRISTAL = "expiracion_cristal"
    APUNTE = "apunte"
    ACREENCIA = "acreencia"


class SubtipoAcunacion(str, Enum):
    VENTA = "venta"
    CAPITAL = "capital"


class AsientoInvalido(Exception):
    pass


_POOLS_PT = {POOL_PT_FABRICA, POOL_PT_PERSONAL}


def es_nombre_suscripcion(nombre) -> bool:
    """Si el nombre puede nombrar una suscripcion (y por lo tanto una cuenta).

    Vive aca, con la gramatica de las cuentas, para que la capa de
    configuracion (`capacidad.Suscripcion`) rechace en el CONSTRUCTOR el
    mismo nombre que el validador rechazaria al escribir el asiento. Sin
    eso el fallo es tardio: el objeto se construye, viaja, y recien explota
    contra el libro con una excepcion de otra capa.
    """
    return isinstance(nombre, str) and bool(_RE_SUSCRIPCION.match(nombre))


def cuenta_cristal(suscripcion: str, zona: str) -> str:
    """El UNICO constructor de cuentas de cristal: (suscripcion, zona) -> cuenta.

    El conjunto de cuentas validas depende del nombre de la suscripcion,
    que es CONFIGURACION, asi que no se puede enumerar aca como se enumera
    `_POOLS_PT`. Pero tampoco se cierra con un `startswith`: con un prefijo,
    "cristal:claude_maxx:fabrica" valida perfecto y se come cristales que
    nadie vuelve a mirar.

    La salida es cerrar el conjunto POR DERIVACION. Esta funcion es
    inyectiva y total sobre (nombre valido, zona), asi que "la cuenta
    pertenece a la imagen de f" equivale a "la cuenta es exactamente
    f(lo que el asiento declara)" — y eso el validador SI lo puede
    comprobar, porque el asiento declara suscripcion y zona en su detalle.
    Una cuenta mal tipeada deja de coincidir con su propia derivacion y
    rebota. La zona, ademas, es un conjunto cerrado de dos.

    Queda una dimension fuera: que el nombre declarado sea una suscripcion
    REAL. Cerrar eso aca exigiria que este modulo leyera
    `suscripciones.json`, y eso seria peor: `validar()` corre tambien al
    CARGAR el libro (ver `libro._cargar`), asi que un asiento valido
    cuando se escribio pasaria a ser invalido el dia que Pedro da de baja
    una suscripcion y el libro entero dejaria de cargar. Regla general de
    `validar()`, por eso mismo: nunca puede depender de configuracion,
    solo del asiento. Esa dimension se cierra una capa arriba, donde hay
    configuracion: los verbos de `cristal.py` exigen (con isinstance, ver
    `cristal._exigir_suscripcion`) un objeto `capacidad.Suscripcion`, que
    solo existe si esta configurado, y `cuentas_cristal()` entrega el
    conjunto literal para cotejar.
    """
    if zona not in ZONAS_CRISTAL:
        raise AsientoInvalido(
            f"zona de cristal invalida: {zona!r} (solo {ZONAS_CRISTAL})")
    if not es_nombre_suscripcion(suscripcion):
        raise AsientoInvalido(
            f"nombre de suscripcion invalido para una cuenta: {suscripcion!r}")
    return f"{PREFIJO_CRISTAL}:{suscripcion}:{zona}"


def cuentas_cristal(suscripciones) -> set[str]:
    """El conjunto CERRADO de cuentas de cristal de una configuracion dada.

    `suscripciones` es cualquier iterable de nombres (un dict de
    suscripciones sirve: itera sus claves). Para uso de las capas que si
    conocen la configuracion.
    """
    return {cuenta_cristal(n, z) for n in suscripciones for z in ZONAS_CRISTAL}


def _exigir_cuenta_cristal(cuenta: str | None, detalle: dict,
                           etiqueta: str) -> None:
    """La cuenta debe ser EXACTAMENTE la derivada de lo que el asiento declara."""
    sus = detalle.get("suscripcion")
    zona = detalle.get("zona")
    if not sus or not zona:
        raise AsientoInvalido(
            f"{etiqueta} exige detalle['suscripcion'] y detalle['zona']")
    esperada = cuenta_cristal(sus, zona)
    if cuenta != esperada:
        raise AsientoInvalido(
            f"{etiqueta}: la cuenta debe ser exactamente {esperada!r}, "
            f"no {cuenta!r}")


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
        elif t is TipoAsiento.EMISION_CRISTAL:
            if self.divisa is not Divisa.CRISTAL:
                raise AsientoInvalido("emision_cristal: divisa cristal")
            if self.origen or not self.destino:
                raise AsientoInvalido("emision_cristal: destino si, origen no")
            _exigir_cuenta_cristal(self.destino, self.detalle, "emision_cristal")
        elif t is TipoAsiento.CONSUMO_CRISTAL:
            if self.divisa is not Divisa.CRISTAL:
                raise AsientoInvalido("consumo_cristal: divisa cristal")
            if not self.origen or self.destino:
                raise AsientoInvalido("consumo_cristal: origen si, destino no")
            _exigir_cuenta_cristal(self.origen, self.detalle, "consumo_cristal")
        elif t is TipoAsiento.EXPIRACION_CRISTAL:
            if self.divisa is not Divisa.CRISTAL:
                raise AsientoInvalido("expiracion_cristal: divisa cristal")
            if not self.origen or self.destino:
                raise AsientoInvalido("expiracion_cristal: origen si, destino no")
            _exigir_cuenta_cristal(self.origen, self.detalle,
                                   "expiracion_cristal")
        elif t is TipoAsiento.APUNTE:
            # Un apunte no mueve saldos (balances._SIN_EFECTO), pero SI se
            # lee como plata: `capacidad.consumo_personal` y
            # `personal.py` suman su monto. Sin esta rama la divisa
            # quedaba libre y un apunte en PT o en cristal se plegaba como
            # si fueran monedas.
            if self.divisa is not Divisa.MONEDA:
                raise AsientoInvalido(
                    "apunte es solo en monedas: la capacidad y el tiempo "
                    "tienen sus propios tipos de asiento")
        elif t is TipoAsiento.ACREENCIA:
            # Idem, y peor: `kernel.liquidar` paga toda acreencia pendiente
            # con TRANSFERENCIAS en monedas, sin mirar su divisa. Una
            # acreencia denominada en PT o en cristal cobraba plata.
            if self.divisa is not Divisa.MONEDA:
                raise AsientoInvalido(
                    "acreencia es solo en monedas: se liquida con "
                    "transferencias de plata")
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
