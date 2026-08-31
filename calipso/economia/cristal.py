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
suscripcion factura y resetea. Cuando EMPIEZA un ciclo lo decide el
llamador (con `capacidad.posicion_ciclo`) y entra como dato en
`emitir_ciclo` y `expirar_ciclo`, igual que entra el `ts`. A que ciclo
pertenece un CONSUMO, en cambio, no lo decide nadie de afuera: se deriva
del libro al escribirlo (`ciclo_abierto`), porque es el ciclo del que
salen las unidades y tiene que coincidir con el pool que las descuenta.

Dos cuentas por suscripcion y nada mas: `cristal:<sus>:fabrica` y
`cristal:<sus>:personal`. Sin bolsillos por departamento: hoy ningun
departamento gasta capacidad por su cuenta (`trabajar` es un no-op
declarado en `server.py`), asi que un bolsillo por departamento seria una
cuenta que nadie mueve. El departamento que consumio queda anotado en
`detalle["titular"]` — NUNCA en `detalle["departamento"]`, ver `consumir`.

Quien lo llama en produccion: `mercado.consumir_capacidad` (por donde
entra todo consumo de capacidad de la fabrica, desde `pagador._aplicar`) y
`operacion`, que emite la cuota al abrir el ciclo y barre los pools al
cerrarlo. La emision y el barrido son los que mantienen honesto el
medidor: consumir sin emitir es legal —el pool queda en descubierto y el
libro no pierde el hecho— pero deja `totales()` reportando cuota cero
contra consumo N.
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


def _exigir_suscripcion(sus) -> None:
    """El objeto tiene que ser una `capacidad.Suscripcion`, no cualquier `.nombre`.

    Aca se cierra la ultima dimension de la trampa 1: `cuenta_cristal`
    garantiza que la cuenta se derive de lo que el asiento declara, pero
    no que el nombre sea una suscripcion REAL. Eso no lo puede saber el
    validador (no puede depender de configuracion); lo sabe el tipo. Con
    un duck-typing bastaba cualquier objeto con `.nombre` —un
    `Departamento`, una clase inventada— para abrir un par de cuentas de
    cristal que despues nadie emite ni barre.
    """
    if not isinstance(sus, Suscripcion):
        raise ErrorCristal(
            "se esperaba una capacidad.Suscripcion configurada, no "
            f"{type(sus).__name__}")


def cupo(sus: Suscripcion, zona: str) -> int:
    """Los cristales que le tocan a la zona en un ciclo."""
    _exigir_suscripcion(sus)
    _exigir_zona(zona)
    return (sus.capacidad_fabrica if zona == ZONA_CRISTAL_FABRICA
            else sus.reserva_personal)


def saldo(k: Kernel, sus: Suscripcion, zona: str) -> int:
    """Cristales que quedan. Puede ser NEGATIVO: ver `consumir`.

    Valida sus argumentos aunque solo LEA: sin esto una zona mala reventaba
    adentro de `cuenta_cristal` con `AsientoInvalido`, una excepcion de la
    capa de tipos cruzando la frontera del modulo por dos funciones de
    lectura, y distinta de la que levantan `cupo` y `consumir` para el
    mismo error del llamador.
    """
    _exigir_suscripcion(sus)
    _exigir_zona(zona)
    return k.saldo(cuenta_cristal(sus.nombre, zona), Divisa.CRISTAL)


def descubierto(k: Kernel, sus: Suscripcion, zona: str) -> int:
    """Cuanto se consumio de mas alla del cupo. Cero si el pool alcanza."""
    return max(0, -saldo(k, sus, zona))


# -- emision ---------------------------------------------------------------
def _emitido(asientos: list[Asiento], nombre: str, ciclo: int,
             zona: str) -> bool:
    """Si ya hay emision DE CUOTA para esa (suscripcion, ciclo, zona).

    Filtra por motivo a proposito: una condonacion de descubierto tambien
    es una `emision_cristal` (ver `expirar_ciclo`), y no es cuota. Quien
    impide reabrir un ciclo cerrado es `_cerrado`, no este filtro: si un
    ciclo tiene condonacion es porque su cierre paso, y ahi la re-llamada
    rebota por cerrado, no por emitida.
    """
    return any(a.tipo is TipoAsiento.EMISION_CRISTAL
               and a.detalle.get("suscripcion") == nombre
               and a.detalle.get("ciclo") == ciclo
               and a.detalle.get("zona") == zona
               and a.detalle.get("motivo") == MOTIVO_CUOTA
               for a in asientos)


def _ciclo_de(a: Asiento) -> int | None:
    c = a.detalle.get("ciclo")
    return c if isinstance(c, int) and not isinstance(c, bool) else None


def _es_condonacion(a: Asiento) -> bool:
    return (a.tipo is TipoAsiento.EMISION_CRISTAL
            and a.detalle.get("motivo") == MOTIVO_CONDONACION)


def _cerrado(asientos: list[Asiento], nombre: str, ciclo: int) -> bool:
    """Si ese ciclo YA CERRO, y por lo tanto no se puede reabrir.

    Un pool en cero no prueba que el ciclo no haya cerrado: cero es
    tambien —y sobre todo— como lo deja `expirar_ciclo`. Sin esta
    comprobacion, la re-llamada de recuperacion que promete
    `emitir_ciclo` inyectaba cuota fresca en un ciclo muerto (y de paso
    dejaba el siguiente trabado con "pool sin cerrar").

    Dos marcas, las dos derivadas del libro: un asiento de cierre PROPIO
    (expiracion o condonacion de ese ciclo), o la cuota de un ciclo
    POSTERIOR ya emitida. La segunda cubre el caso en que el cierre no
    escribio nada porque los dos pools ya estaban exactos en cero.
    """
    for a in asientos:
        if a.detalle.get("suscripcion") != nombre:
            continue
        c = _ciclo_de(a)
        if c is None:
            continue
        if c == ciclo and (a.tipo is TipoAsiento.EXPIRACION_CRISTAL
                           or _es_condonacion(a)):
            return True
        if (c > ciclo and a.tipo is TipoAsiento.EMISION_CRISTAL
                and a.detalle.get("motivo") == MOTIVO_CUOTA):
            return True
    return False


def ciclo_abierto(asientos: list[Asiento], nombre: str) -> int:
    """El ciclo al que hay que cargar un consumo que se escribe AHORA.

    El pool no tiene ciclos: descuenta por orden de llegada del asiento.
    El pliegue de auditoria si los tiene. Para que los dos cuenten lo
    mismo, el ciclo se resuelve al ESCRIBIR —el ciclo del que salen las
    unidades— y queda estampado en el asiento; no se deduce despues de la
    semana del hecho, que para un cargo reintentado es la semana vieja y
    manda el consumo al ciclo equivocado.

    Es el ultimo ciclo con cuota emitida, o el siguiente al ultimo cerrado
    si el cierre ya paso y la emision todavia no (ahi caen los cargos
    tardios). Sin nada emitido ni cerrado es el ciclo 0: un consumo
    anterior a la primera emision lo paga el pool del ciclo 0, que nace
    con ese descubierto.

    Rincon conocido: un pool que cierra en cero EXACTO no deja asiento de
    cierre (un asiento de monto cero es invalido), asi que un cargo
    tardio contra esa zona, llegado antes de la emision siguiente, se
    atribuye al ciclo que cerro y lo paga el pool del que abre. Pide
    igualdad exacta entre consumo y cuota: con resto hay expiracion y con
    descubierto hay condonacion, y las dos son marca de cierre.

    Es publica porque el guardia de cuota (`mercado.consumir_capacidad`)
    tiene que preguntar la misma cosa ANTES de escribir: contar el consumo
    de otro ciclo —o de otra ventana— seria acotar una cuota distinta de la
    que la unidad va a descontar.
    """
    abierto = 0
    for a in asientos:
        if a.detalle.get("suscripcion") != nombre:
            continue
        c = _ciclo_de(a)
        if c is None:
            continue
        if (a.tipo is TipoAsiento.EMISION_CRISTAL
                and a.detalle.get("motivo") == MOTIVO_CUOTA):
            abierto = max(abierto, c)
        elif a.tipo is TipoAsiento.EXPIRACION_CRISTAL or _es_condonacion(a):
            abierto = max(abierto, c + 1)
    return abierto


def emitir_ciclo(k: Kernel, ts: str, semana: str, ciclo: int,
                 sus: Suscripcion) -> list[Asiento]:
    """Abre el ciclo de una suscripcion: cuota a la fabrica, reserva a Pedro.

    Idempotente por (suscripcion, ciclo): si los dos pools ya se emitieron,
    levanta `ErrorCristal` en vez de duplicar. Si solo uno se emitio (un
    corte a mitad de la emision), la re-llamada completa el que falta —
    pero exigiendo el MISMO split: si la configuracion de la suscripcion
    cambio entre las dos llamadas, eso no es una recuperacion, es un ciclo
    con dos cuotas distintas, y se rechaza. Y un ciclo que YA CERRO no se
    reabre nunca (ver `_cerrado`): cuota fresca en un ciclo muerto es
    capacidad inventada, y en un libro append-only queda para siempre.

    Se niega a emitir sobre un pool con RESTO SIN BARRER (saldo > 0),
    igual que `pt.emitir_semana`: emitir encima de un resto sin expirar
    acumula capacidad de un ciclo en el siguiente, y la capacidad NO se
    acumula — la suscripcion resetea, no ahorra.

    Mira el SIGNO, no la desigualdad con cero. `pt.emitir_semana` compara
    `!= 0` y esta bien alla, porque `pt._consumir` rechaza el sobregiro y
    un pool de PT no puede quedar negativo: ahi todo lo que no es cero es
    resto. Aca el pool puede quedar negativo POR DISENO (`consumir` nunca
    rechaza), y un descubierto no es un resto sin barrer: no hay nada que
    expirar, asi que ese `!= 0` copiado dejaba el ciclo IMPOSIBLE de
    abrir, y como no se autorecuperaba, la fabrica corria el ciclo entero
    con cero cristales — el desastre que la condonacion existe para
    evitar. Es la misma trampa que el `if resto:` de `expirar_ciclo`: una
    comparacion traida de un mundo sin negativos a uno que si los tiene.

    Un descubierto en pie al momento de emitir (cargo tardio, cierre que
    nunca corrio) lo absorbe el pool nuevo: son unidades REALMENTE
    servidas que ya no puede condonar el cierre de un ciclo que ya paso,
    y descontarlas de la cuota nueva es lo unico que mantiene honesto al
    medidor. Se atribuyen al ciclo que las paga: `consumir` estampa el
    ciclo abierto en el asiento, ver `ciclo_abierto`.

    Valida los DOS pools antes del primer append. El libro es append-only
    y no tiene rollback (la regla que enuncia `direccion._pagar_pt`):
    chequear adentro del bucle dejaba la emision de fabrica escrita para
    siempre con el llamador recibiendo una excepcion y descartando el
    resultado — un ciclo medio abierto que ningun reintento arregla.
    """
    _exigir_ciclo(ciclo)
    _exigir_suscripcion(sus)
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
    if _cerrado(asientos, sus.nombre, ciclo):
        raise ErrorCristal(
            f"ciclo {ciclo} de {sus.nombre} ya cerrado: no se reabre")
    objetivos = [(ZONA_CRISTAL_FABRICA, sus.capacidad_fabrica),
                 (ZONA_CRISTAL_PERSONAL, sus.reserva_personal)]
    pendientes = [(zona, monto) for zona, monto in objetivos
                  if monto > 0 and not _emitido(asientos, sus.nombre, ciclo,
                                                zona)]
    if not pendientes:
        raise ErrorCristal(f"ciclo ya emitido para {sus.nombre}: {ciclo}")
    for zona, _monto in pendientes:   # validar TODO antes de escribir nada
        cuenta = cuenta_cristal(sus.nombre, zona)
        resto = k.saldo(cuenta, Divisa.CRISTAL)
        if resto > 0:
            raise ErrorCristal(
                f"pool {cuenta} sin cerrar: expirar antes de emitir "
                f"({resto} sin barrer)")
    out = []
    for zona, monto in pendientes:
        cuenta = cuenta_cristal(sus.nombre, zona)
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

    Y agrega `detalle["ciclo"]`: el ciclo del que SALEN las unidades,
    resuelto contra el libro al escribir (`ciclo_abierto`), no despues a
    partir de `semana`. La semana del asiento es la del hecho, y un cargo
    reintentado desde `cargos_pendientes.jsonl` conserva la vieja: sale
    del pool del ciclo nuevo y un pliegue por semana lo cargaba al ciclo
    viejo. Con el ciclo estampado, el pool y `consumo_del_ciclo` cuentan
    lo mismo — y un consumo en una semana sin emision de PT (la
    suscripcion sirve requests igual) deja de ser invisible.

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
    _exigir_suscripcion(sus)
    _exigir_zona(zona)
    if not titular or not isinstance(titular, str):
        raise ErrorCristal(f"titular debe ser una cuenta no vacia: {titular!r}")
    if unidades <= 0:
        return None
    cuenta = cuenta_cristal(sus.nombre, zona)
    asientos = k.libro.asientos()
    disponible = max(0, k.saldo(cuenta, Divisa.CRISTAL))
    detalle = {"suscripcion": sus.nombre, "zona": zona, "titular": titular,
               "ciclo": ciclo_abierto(asientos, sus.nombre)}
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
    cuota + condonado - consumido - expirado == suma de saldos en CRISTAL.

    Y no barre dos veces el mismo ciclo, que es la simetrica de "un ciclo
    cerrado no se reabre" (`emitir_ciclo`). No es prolijidad: el pulso
    REPITE el cierre —`operacion.cerrar_semana_operativa` solo exige que la
    semana sea la ultima abierta, y la rutina de cierre vuelve a correr— y
    entre ese cierre y la apertura del ciclo siguiente la fabrica sigue
    consumiendo, porque cada turno de chat escribe. Esos consumos ya salen
    del pool del ciclo NUEVO (`ciclo_abierto` los estampa asi apenas hay
    marca de cierre), asi que un segundo barrido los CONDONARIA a nombre
    del ciclo viejo: la fabrica estrenaria el ciclo nuevo con la cuota
    entera y el consumo del hueco no lo pagaria ningun ciclo.

    Rincon conocido, el mismo que documenta `ciclo_abierto`: un ciclo
    cuyos dos pools cerraron en cero EXACTO no deja asiento de cierre, y
    hasta que se emita el ciclo siguiente no hay marca que mirar.
    """
    _exigir_ciclo(ciclo)
    _exigir_suscripcion(sus)
    if _cerrado(k.libro.asientos(), sus.nombre, ciclo):
        return []
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
    """Cierra el ciclo de todas las suscripciones, en orden de nombre.

    Exige que la clave del dict sea el nombre de la suscripcion. El resto
    de la capa de capacidad (`mercado`, `capacidad`, `eficiencia`) indexa
    por la CLAVE y estampa esa en los asientos; `cristal` deriva sus
    cuentas de `sus.nombre`. Nada obligaba a que coincidieran —
    `pagador.mercado_fresco` construye `{n: Suscripcion(**c)}` y el
    `nombre` viene de adentro del json— asi que un `suscripciones.json`
    con clave distinta del nombre partia la misma suscripcion en dos, una
    por divisa, sin un solo error. Se corta aca, en la unica puerta de
    este modulo que ve las claves.
    """
    for nombre, sus in suscripciones.items():
        _exigir_suscripcion(sus)
        if nombre != sus.nombre:
            raise ErrorCristal(
                f"la clave {nombre!r} no es el nombre de la suscripcion "
                f"({sus.nombre!r}): la capacidad y el cristal quedarian "
                "contando suscripciones distintas")
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
def totales(asientos: list[Asiento]) -> tuple[int, int, int, int]:
    """(cuota, consumido, expirado, condonado) en cristales, sobre todo el libro.

    La cuota va SEPARADA de la condonacion aunque las dos sean
    `emision_cristal`, porque son numeros distintos: la cuota es la
    capacidad concedida, la condonacion es descubierto saldado. Sumadas
    en un solo "emitido" —como estaban— el descubierto se autocancelaba
    en cualquier lectura de emitido-contra-consumido: un ciclo con 1.000
    de cuota y 1.150 consumidos reportaba 1.150 emitidos, o sea 100% de
    uso en vez de 115%, y un medidor cableado a este pliegue no podia
    pasar de 100 nunca.

    La conservacion sigue siendo exacta, ahora con los cuatro terminos:
    cuota + condonado - consumido - expirado == suma de saldos en CRISTAL.
    """
    # Sin filtro por divisa: los tres tipos son exclusivos del cristal y el
    # validador lo exige en las dos puertas del libro, la de escritura y la
    # de lectura (`libro._cargar`). Un filtro que ninguna entrada posible
    # puede activar es codigo que ningun test puede matar.
    cuota = consumido = expirado = condonado = 0
    for a in asientos:
        if a.tipo is TipoAsiento.EMISION_CRISTAL:
            if a.detalle.get("motivo") == MOTIVO_CONDONACION:
                condonado += a.monto
            else:
                cuota += a.monto
        elif a.tipo is TipoAsiento.CONSUMO_CRISTAL:
            consumido += a.monto
        elif a.tipo is TipoAsiento.EXPIRACION_CRISTAL:
            expirado += a.monto
    return cuota, consumido, expirado, condonado


def consumo_del_ciclo(asientos: list[Asiento], nombre: str, zona: str,
                      ciclo: int) -> int:
    """Cristales consumidos por (suscripcion, zona) EN ESE CICLO.

    Por el ciclo estampado en el asiento, que es el del pool del que
    salieron las unidades (ver `consumir`), no por la semana: el pool y
    este pliegue tienen que contar lo mismo o el ciclo cierra en cero
    declarando un consumo que su cuota no podia respaldar.
    """
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.CONSUMO_CRISTAL
               and a.detalle.get("suscripcion") == nombre
               and a.detalle.get("zona") == zona
               and a.detalle.get("ciclo") == ciclo)
