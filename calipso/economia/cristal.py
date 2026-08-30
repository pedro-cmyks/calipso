"""
calipso/economia/cristal.py — La divisa de la capacidad de las suscripciones.

Gemelo de `pt.py`, con el mismo ciclo de vida: emision al abrir el
periodo, consumo mientras corre, expiracion al cerrarlo. Lo que cambia es
QUE se mide.

Las monedas miden plata: lo que sale de la cuenta de Pedro cuando se paga
la suscripcion o una llamada de API. Los cristales miden CAPACIDAD: los
requests que esa suscripcion —ya pagada— sirve dentro de su ciclo. Gastar
un cristal no gasta una moneda: la plata se gasto una vez, cuando se pago
el mes. Confundirlas cobra dos veces lo mismo, y ademas rompe: un cargo
de capacidad contra una cuenta sin monedas levanta `SinSaldo`, y como
`SinSaldo` es un error economico el cargo se aparca y se reintenta para
siempre sin poder aplicarse nunca — la suscripcion se consume de verdad y
el libro anota cero unidades.

El periodo del cristal es el CICLO (4 semanas operativas, ver
`capacidad.SEMANAS_POR_CICLO`), no la semana: es el ciclo el que la
suscripcion factura y resetea. El indice de ciclo lo resuelve el llamador
con `capacidad.posicion_ciclo`; aca entra como dato, igual que entra el
`ts`. Este modulo no decide cuando empieza un ciclo, solo lleva su cuenta.

Dos cuentas por suscripcion y nada mas: `cristal:<sus>:fabrica` y
`cristal:<sus>:personal`. Sin bolsillos por departamento: hoy ningun
departamento gasta capacidad por su cuenta (`trabajar` es un no-op
declarado en `server.py`), asi que un bolsillo por departamento seria una
cuenta que nadie mueve. El departamento que consumio queda anotado en
`detalle["titular"]` — NUNCA en `detalle["departamento"]`, ver `consumir`.

NADIE LLAMA A ESTE MODULO TODAVIA. Hasta que el pagador lo llame, no
escribe un solo asiento en el libro de nadie: es un paso reversible del
todo, a proposito.
"""
from __future__ import annotations

from dataclasses import dataclass

from .capacidad import Suscripcion
from .kernel import Kernel
from .tipos import (Asiento, Divisa, TipoAsiento, ZONAS_CRISTAL,
                    ZONA_CRISTAL_FABRICA, ZONA_CRISTAL_PERSONAL,
                    cuenta_cristal)

MOTIVO_CUOTA = "cuota"
MOTIVO_CONDONACION = "condonacion"


class ErrorCristal(Exception):
    pass


def _exigir_ciclo(ciclo: int) -> None:
    if not isinstance(ciclo, int) or isinstance(ciclo, bool) or ciclo < 0:
        raise ErrorCristal(f"ciclo debe ser entero >= 0: {ciclo!r}")


def _exigir_zona(zona: str) -> None:
    if zona not in ZONAS_CRISTAL:
        raise ErrorCristal(f"zona invalida: {zona!r} (solo {ZONAS_CRISTAL})")


def cupo(sus: Suscripcion, zona: str) -> int:
    """Los cristales que le tocan a la zona en un ciclo."""
    _exigir_zona(zona)
    return (sus.capacidad_fabrica if zona == ZONA_CRISTAL_FABRICA
            else sus.reserva_personal)


def saldo(k: Kernel, sus: Suscripcion, zona: str) -> int:
    """Cristales que quedan. Puede ser NEGATIVO: ver `consumir`."""
    return k.saldo(cuenta_cristal(sus.nombre, zona), Divisa.CRISTAL)


def descubierto(k: Kernel, sus: Suscripcion, zona: str) -> int:
    """Cuanto se consumio de mas alla del cupo. Cero si el pool alcanza."""
    return max(0, -saldo(k, sus, zona))


# -- emision ---------------------------------------------------------------
def _emitido(asientos: list[Asiento], nombre: str, ciclo: int,
             zona: str) -> bool:
    """Si ya hay emision DE CUOTA para esa (suscripcion, ciclo, zona).

    Filtra por motivo a proposito: una condonacion de descubierto tambien
    es una `emision_cristal` (ver `expirar_ciclo`), y si contara aca una
    re-llamada de recuperacion creeria que el ciclo ya emitio su cuota.
    """
    return any(a.tipo is TipoAsiento.EMISION_CRISTAL
               and a.detalle.get("suscripcion") == nombre
               and a.detalle.get("ciclo") == ciclo
               and a.detalle.get("zona") == zona
               and a.detalle.get("motivo") == MOTIVO_CUOTA
               for a in asientos)


def emitir_ciclo(k: Kernel, ts: str, semana: str, ciclo: int,
                 sus: Suscripcion) -> list[Asiento]:
    """Abre el ciclo de una suscripcion: cuota a la fabrica, reserva a Pedro.

    Idempotente por (suscripcion, ciclo): si los dos pools ya se emitieron,
    levanta `ErrorCristal` en vez de duplicar. Si solo uno se emitio (un
    corte a mitad de la emision), la re-llamada completa el que falta —
    pero exigiendo el MISMO split: si la configuracion de la suscripcion
    cambio entre las dos llamadas, eso no es una recuperacion, es un ciclo
    con dos cuotas distintas, y se rechaza.

    Se niega a emitir sobre un pool que no este barrido, igual que
    `pt.emitir_semana`: emitir encima de un resto sin expirar acumula
    capacidad de un ciclo en el siguiente, y la capacidad NO se acumula —
    la suscripcion resetea, no ahorra. Que el pool este en cero es la
    prueba de que el ciclo anterior cerro.
    """
    _exigir_ciclo(ciclo)
    asientos = k.libro.asientos()
    for a in asientos:
        if (a.tipo is TipoAsiento.EMISION_CRISTAL
                and a.detalle.get("suscripcion") == sus.nombre
                and a.detalle.get("ciclo") == ciclo
                and a.detalle.get("capacidad") is not None
                and (a.detalle["capacidad"] != sus.capacidad_fabrica
                     or a.detalle["reserva"] != sus.reserva_personal)):
            raise ErrorCristal(
                f"ciclo {ciclo} de {sus.nombre} ya iniciado con otro split: "
                f"({a.detalle['capacidad']}, {a.detalle['reserva']})")
    objetivos = [(ZONA_CRISTAL_FABRICA, sus.capacidad_fabrica),
                 (ZONA_CRISTAL_PERSONAL, sus.reserva_personal)]
    pendientes = [(zona, monto) for zona, monto in objetivos
                  if monto > 0 and not _emitido(asientos, sus.nombre, ciclo,
                                                zona)]
    if not pendientes:
        raise ErrorCristal(f"ciclo ya emitido para {sus.nombre}: {ciclo}")
    out = []
    for zona, monto in pendientes:
        cuenta = cuenta_cristal(sus.nombre, zona)
        if k.saldo(cuenta, Divisa.CRISTAL) != 0:
            raise ErrorCristal(
                f"pool {cuenta} sin cerrar: expirar antes de emitir")
        out.append(k.libro.append(
            ts=ts, semana=semana, tipo=TipoAsiento.EMISION_CRISTAL,
            divisa=Divisa.CRISTAL, monto=monto, destino=cuenta,
            detalle={"suscripcion": sus.nombre, "zona": zona, "ciclo": ciclo,
                     "motivo": MOTIVO_CUOTA,
                     "capacidad": sus.capacidad_fabrica,
                     "reserva": sus.reserva_personal}))
    return out


# -- consumo ---------------------------------------------------------------
def consumir(k: Kernel, ts: str, semana: str, sus: Suscripcion, zona: str,
             unidades: int, titular: str, ref: str | None = None
             ) -> Asiento | None:
    """Asienta capacidad ya consumida. NUNCA rechaza por falta de saldo.

    Cuando llega el cargo el modelo ya contesto: la suscripcion se gasto,
    el request se sirvio, el hecho paso. `_cobrar_turno` dice en su propio
    docstring que nunca voltea el chat, y un consumo que se niega a
    escribirse deja el libro mintiendo sobre lo que la fabrica uso. Asi
    que si el pool esta seco el asiento se escribe IGUAL y la cuenta queda
    en DESCUBIERTO: saldo negativo.

    Un recurso que MIDE un hecho consumado puede quedar en negativo; el
    libro de la plata no puede (el Kernel exige disponible antes de mover
    una moneda, invariante 7). No es la misma regla porque no es la misma
    clase de cosa: la plata se respalda antes de salir, la capacidad se
    cuenta despues de haberse ido. Esto no inventa nada — registra lo que
    ya paso.

    El descubierto vive en el propio pool, no en una cuenta aparte: dos
    cuentas por suscripcion y nada mas, y un solo asiento por hecho. Lo
    que el asiento agrega es `detalle["descubierto"]`: cuantas de estas
    unidades quedaron sin respaldo en el momento de escribirlas, para que
    quien audite no tenga que reconstruir el saldo instante a instante.
    El ciclo se cierra en cero de todas formas, ver `expirar_ciclo`.

    El departamento va en `detalle["titular"]`, NUNCA en
    `detalle["departamento"]`: `cierre._primera_semana` da por "nacido" a
    todo departamento que aparezca en `detalle["departamento"]`, y el
    cierre declara la quiebra de todo departamento nacido con
    `k.disponible(cuenta) <= 0` EN MONEDAS. Con la clave equivocada,
    consumir cristales —que no toca una sola moneda— congelaria
    departamentos.

    `unidades <= 0` no es un consumo: no hay hecho que asentar y devuelve
    None sin escribir (un asiento de monto cero es invalido, y un cargo
    aparcado por eso se reintentaria eternamente). Un llamado MALFORMADO
    —unidades no entera, zona desconocida, titular vacio— si levanta
    `ErrorCristal`: es un bug del llamador, no una condicion economica, y
    tiene que ser ruidoso en vez de convertirse en un pendiente eterno.
    """
    if not isinstance(unidades, int) or isinstance(unidades, bool):
        raise ErrorCristal(f"unidades debe ser entero: {unidades!r}")
    _exigir_zona(zona)
    if not titular or not isinstance(titular, str):
        raise ErrorCristal(f"titular debe ser una cuenta no vacia: {titular!r}")
    if unidades <= 0:
        return None
    cuenta = cuenta_cristal(sus.nombre, zona)
    disponible = max(0, k.saldo(cuenta, Divisa.CRISTAL))
    detalle = {"suscripcion": sus.nombre, "zona": zona, "titular": titular}
    sin_respaldo = unidades - disponible
    if sin_respaldo > 0:
        detalle["descubierto"] = sin_respaldo
    return k.libro.append(
        ts=ts, semana=semana, tipo=TipoAsiento.CONSUMO_CRISTAL,
        divisa=Divisa.CRISTAL, monto=unidades, origen=cuenta, ref=ref,
        detalle=detalle)


def consumir_fabrica(k: Kernel, ts: str, semana: str, sus: Suscripcion,
                     unidades: int, titular: str, ref: str | None = None
                     ) -> Asiento | None:
    return consumir(k, ts, semana, sus, ZONA_CRISTAL_FABRICA, unidades,
                    titular, ref)


def consumir_personal(k: Kernel, ts: str, semana: str, sus: Suscripcion,
                      unidades: int, titular: str, ref: str | None = None
                      ) -> Asiento | None:
    return consumir(k, ts, semana, sus, ZONA_CRISTAL_PERSONAL, unidades,
                    titular, ref)


# -- cierre de ciclo -------------------------------------------------------
def expirar_ciclo(k: Kernel, ts: str, semana: str, ciclo: int,
                  sus: Suscripcion) -> list[Asiento]:
    """Cierra los dos pools de la suscripcion, en cero exacto.

    El signo decide el asiento:

    - resto > 0: `expiracion_cristal`. Lo que no se uso se pierde — la
      suscripcion no ahorra capacidad de un mes para el otro.
    - resto < 0: `emision_cristal` de CONDONACION por el descubierto. El
      sobreconsumo del ciclo que cierra no se arrastra al que abre: el
      pool mide el margen REAL del ciclo nuevo (la suscripcion resetea de
      verdad), y arrastrar una deuda que ademas puede componerse dejaria
      el medidor en negativo permanente y a la fabrica cayendo siempre al
      API caro. La condonacion es un asiento explicito, no un olvido: el
      descubierto queda para siempre en el libro, contado y fechado.
    - resto == 0: nada que escribir.

    `pt.expirar_pools` hace `if resto:` — y `bool(-100)` es True mientras
    el validador exige monto entero POSITIVO. Copiar esa linea con una
    cuenta que puede quedar negativa reventaba el cierre del ciclo con
    `AsientoInvalido` a mitad de camino, dejando unos pools cerrados y
    otros no, y sin cerrar nunca. Aca se compara contra cero, no se evalua
    la verdad del entero.

    Las tres direcciones quedan puras —emision suma al destino, consumo y
    expiracion restan del origen— y por eso vale exacto, sin excepciones:
    emitido - consumido - expirado == suma de saldos en CRISTAL.
    """
    _exigir_ciclo(ciclo)
    out = []
    for zona in ZONAS_CRISTAL:
        cuenta = cuenta_cristal(sus.nombre, zona)
        resto = k.saldo(cuenta, Divisa.CRISTAL)
        base = {"suscripcion": sus.nombre, "zona": zona, "ciclo": ciclo}
        if resto > 0:
            out.append(k.libro.append(
                ts=ts, semana=semana, tipo=TipoAsiento.EXPIRACION_CRISTAL,
                divisa=Divisa.CRISTAL, monto=resto, origen=cuenta,
                detalle=base))
        elif resto < 0:
            out.append(k.libro.append(
                ts=ts, semana=semana, tipo=TipoAsiento.EMISION_CRISTAL,
                divisa=Divisa.CRISTAL, monto=-resto, destino=cuenta,
                detalle=base | {"motivo": MOTIVO_CONDONACION}))
    return out


@dataclass(frozen=True)
class CierreCiclo:
    ciclo: int
    expirado: dict[str, int]    # cuenta -> cristales que se perdieron
    condonado: dict[str, int]   # cuenta -> descubierto saldado


def cerrar_ciclo(k: Kernel, ts: str, semana: str, ciclo: int,
                 suscripciones: dict[str, Suscripcion]) -> CierreCiclo:
    """Cierra el ciclo de todas las suscripciones, en orden de nombre."""
    expirado: dict[str, int] = {}
    condonado: dict[str, int] = {}
    for _nombre, sus in sorted(suscripciones.items()):
        for a in expirar_ciclo(k, ts, semana, ciclo, sus):
            if a.tipo is TipoAsiento.EXPIRACION_CRISTAL:
                expirado[a.origen] = a.monto
            else:
                condonado[a.destino] = a.monto
    return CierreCiclo(ciclo=ciclo, expirado=expirado, condonado=condonado)


# -- pliegues de lectura ---------------------------------------------------
def totales(asientos: list[Asiento]) -> tuple[int, int, int]:
    """(emitido, consumido, expirado) en cristales, sobre todo el libro."""
    emitido = consumido = expirado = 0
    for a in asientos:
        if a.divisa is not Divisa.CRISTAL:
            continue
        if a.tipo is TipoAsiento.EMISION_CRISTAL:
            emitido += a.monto
        elif a.tipo is TipoAsiento.CONSUMO_CRISTAL:
            consumido += a.monto
        elif a.tipo is TipoAsiento.EXPIRACION_CRISTAL:
            expirado += a.monto
    return emitido, consumido, expirado


def consumo_del_ciclo(asientos: list[Asiento], nombre: str, zona: str,
                      semanas: list[str]) -> int:
    """Cristales consumidos por (suscripcion, zona) en esas semanas."""
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.CONSUMO_CRISTAL
               and a.detalle.get("suscripcion") == nombre
               and a.detalle.get("zona") == zona
               and a.semana in semanas)
