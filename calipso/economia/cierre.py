"""
calipso/economia/cierre.py — El pulso de la economia.

El cierre semanal ejecuta en orden: muertes de trabajos, quiebras,
presupuestos (direccion y departamentos, dentro del mandato), cartas de
cierre departamental, y el cierre de PT. El cierre de ciclo (cada 4
semanas operativas) decide renovaciones con numeros — cuanto de la cuota
uso la fabrica, ver `_rojo_de_ciclo` — y aplica el circuit breaker: dos
ciclos rojos con la carta sin atender vuelven la renovacion manual
(spec 4.2).
Las cartas son datos devueltos; la cola que las presenta es del Plan 3.
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass

from . import bus as bus_mod
from . import capacidad as cap
from . import departamentos as deps
from . import direccion
from . import eficiencia
from . import pt
from .kernel import SinSaldo
from .mercado import Mercado
from .tipos import DIRECCION, SubtipoAcunacion, TESORO, TipoAsiento


@dataclass(frozen=True)
class CierreEconomia:
    semana: str
    quiebras: list
    trabajos_muertos: list
    cartas: list
    cierre_pt: pt.CierreSemana


def _primera_semana(asientos, cuenta: str) -> str | None:
    for a in asientos:
        if cuenta in (a.origen, a.destino) or \
                a.detalle.get("departamento") == cuenta:
            return a.semana
    return None


def _ventas_en(asientos, cuentas: set[str], semanas: list[str]) -> int:
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.ACUNACION
               and a.subtipo == SubtipoAcunacion.VENTA.value
               and a.destino in cuentas and a.semana in semanas)


def cerrar_semana_economia(mercado: Mercado, bus: bus_mod.Bus, ts: str,
                           semana: str, refs_no_servidas: list[str] = (),
                           presupuesto_direccion_mm: int = 0,
                           ventana_carta_cierre: int = 8,
                           umbral_mandato_mm: int = direccion.UMBRAL_MANDATO_MM
                           ) -> CierreEconomia:
    k = mercado.k
    cartas: list[dict] = []

    # 1) trabajos muertos
    muertos = bus_mod.evaluar_y_liquidar_muertos(mercado, bus, ts, semana)

    # 2) quiebras nuevas (solo fabrica; los ya congelados no se re-declaran)
    quiebras: list[str] = []
    for dep in mercado.registro.todos():
        if dep.zona != deps.ZONA_FABRICA:
            continue
        asientos = k.libro.asientos()
        if (not deps.es_congelado(asientos, dep.cuenta)
                and k.disponible(dep.cuenta) <= 0
                and _primera_semana(asientos, dep.cuenta) is not None
                and _primera_semana(asientos, dep.cuenta) < semana):
            deps.declarar_quiebra(k, ts, semana, dep.cuenta)
            quiebras.append(dep.cuenta)

    # 3) presupuesto de direccion
    if presupuesto_direccion_mm > 0:
        ya_direccion = sum(a.monto for a in k.libro.asientos()
                           if a.tipo is TipoAsiento.TRANSFERENCIA
                           and a.origen == TESORO and a.destino == DIRECCION
                           and a.detalle.get("motivo") == "presupuesto_direccion"
                           and a.semana == semana)
        if ya_direccion < presupuesto_direccion_mm:
            # idempotencia: un reintento del cierre solo transfiere el
            # faltante hasta completar el presupuesto pedido
            k.transferir(ts, semana, TESORO, DIRECCION,
                         presupuesto_direccion_mm - ya_direccion,
                         motivo="presupuesto_direccion")

    # 4) presupuestos semanales de departamentos
    for dep in mercado.registro.todos():
        if dep.zona != deps.ZONA_FABRICA or dep.presupuesto_semanal_mm <= 0:
            continue
        if deps.es_congelado(k.libro.asientos(), dep.cuenta):
            continue
        ya = direccion.asignado_semana(k.libro.asientos(), dep.cuenta, semana)
        if ya >= dep.presupuesto_semanal_mm:
            continue  # idempotencia: un reintento del cierre no paga dos veces
        try:
            # FIX I7 (spec-owner ruling): la perilla de Pedro (el
            # presupuesto_semanal_mm configurado por el mismo Pedro) no
            # pasa por el mandato — se firma con su propio origen auditable.
            direccion.asignar_presupuesto(
                mercado, ts, semana, dep.cuenta,
                dep.presupuesto_semanal_mm - ya, umbral_mm=umbral_mandato_mm,
                firma={"tipo": "perilla_pedro",
                       "perilla": "presupuesto_semanal_mm"})
        except direccion.ErrorDireccion:
            cartas.append({"tipo": "mandato", "departamento": dep.cuenta,
                           "monto": dep.presupuesto_semanal_mm})
        except SinSaldo:
            cartas.append({"tipo": "tesoro_insuficiente",
                           "departamento": dep.cuenta,
                           "monto": dep.presupuesto_semanal_mm})

    # 5) cartas de cierre departamental
    asientos = k.libro.asientos()
    ops = cap.semanas_operativas(asientos)
    duenos = {id: bus.datos(id)["departamento"] for id in bus.ids()}
    ventana = ops[-ventana_carta_cierre:]
    for dep in mercado.registro.todos():
        if dep.zona != deps.ZONA_FABRICA:
            continue
        primera = _primera_semana(asientos, dep.cuenta)
        if primera is None:
            continue
        # FIX I9: una primera semana no operativa (p.ej. capital acuñado
        # antes de la primera emision de PT) no exime de la carta — se
        # ubica su posicion entre las semanas operativas en vez de exigir
        # pertenencia exacta.
        idx = bisect.bisect_left(ops, primera)
        if idx >= len(ops):
            continue
        if len(ops) - idx < ventana_carta_cierre:
            continue  # todavia no vivio la ventana completa
        cuentas = {dep.cuenta} | {bus_mod.cuenta_trabajo(id)
                                  for id, d in duenos.items()
                                  if d == dep.cuenta}
        if _ventas_en(asientos, cuentas, ventana) == 0:
            cartas.append({"tipo": "cierre_departamento",
                           "departamento": dep.cuenta})

    # 6) cierre de PT
    cierre_pt = pt.cerrar_semana(k, ts, semana,
                                 refs_reservas_no_servidas=list(refs_no_servidas))
    return CierreEconomia(semana=semana, quiebras=quiebras,
                          trabajos_muertos=muertos, cartas=cartas,
                          cierre_pt=cierre_pt)


# el apunte que estampa el color de un ciclo al cerrarlo
NOTA_COLOR_CICLO = "color_ciclo"

# Por debajo de este porcentaje de la cuota del ciclo, el ciclo es rojo.
# PROPUESTA DE ESTE TRABAJO, no decision de Pedro: el criterio (aprovechar
# la cuota) reemplaza al de recuperacion, que bajo costo hundido quedo roto
# —ver `_rojo_de_ciclo`—, pero el NUMERO lo tiene que confirmar Pedro. Es
# la unica perilla del color y por eso vive aca, con nombre, en vez de
# quedar de literal adentro de una comparacion.
PISO_APROVECHAMIENTO_PCT = 40


def _color_estampado(asientos, nombre: str, semanas: list[str]) -> bool | None:
    """El color que se le puso a ese ciclo cuando cerro, o None si es un
    ciclo cerrado antes de que esto existiera."""
    for a in asientos:
        if (a.tipo is TipoAsiento.APUNTE
                and a.detalle.get("nota") == NOTA_COLOR_CICLO
                and a.detalle.get("suscripcion") == nombre
                and a.semana in semanas):
            return bool(a.detalle.get("rojo"))
    return None


def _es_huella_juzgable(a, nombre: str) -> bool:
    """Si ese asiento prueba que la suscripcion ya tenia algo que juzgar.

    La lista es blanca y corta a proposito. Vale como huella el USO de la
    capacidad —una compra vieja contra direccion, un consumo de cristal— y
    el JUICIO de un ciclo anterior (la estampa de color). Nada mas.

    El consumo cuenta sin mirarle la ZONA, y no es un descuido: la pregunta
    aca es si habia algo que juzgar, no si lo uso la fabrica — eso lo
    contesta el numero. Una suscripcion que Pedro ya esta usando por su
    reserva mientras la fabrica no toca su cuota es exactamente el ciclo
    que el color tiene que poder pintar de rojo.

    Lo que NO vale, y es la razon de que esto exista: la emision de la
    cuota y el barrido del ciclo. Los escribe `operacion` sola, al abrir y
    al cerrar, y llevan `detalle["suscripcion"]` igual que un consumo — o
    sea que con "cualquier asiento con el nombre" la exencion de arranque
    en frio quedaba anulada por la propia maquinaria que la acompaña: la
    cuota del ciclo 0 se emite en su PRIMERA semana, asi que el ciclo 0 ya
    se juzgaba, salia rojo con la fabrica todavia en cero, y el breaker se
    armaba al cerrar el ciclo 1 — exactamente el daño que la exencion
    existe para evitar. Emitir una cuota no es usarla.
    """
    if a.detalle.get("suscripcion") != nombre:
        return False
    if a.tipo is TipoAsiento.CONSUMO_CRISTAL:
        return True
    if a.tipo is TipoAsiento.TRANSFERENCIA and a.destino == DIRECCION:
        return True
    return (a.tipo is TipoAsiento.APUNTE
            and a.detalle.get("nota") == NOTA_COLOR_CICLO)


def _primera_semana_suscripcion(asientos, nombre: str) -> str | None:
    """La primera semana con huella juzgable de la suscripcion.

    El gemelo de `_primera_semana` para una suscripcion: no pregunta QUE
    paso, pregunta si ya habia algo que juzgar. Lo que cuenta como huella
    lo decide `_es_huella_juzgable`.
    """
    for a in asientos:
        if _es_huella_juzgable(a, nombre):
            return a.semana
    return None


def _rojo_de_ciclo(asientos, sus: cap.Suscripcion, ciclo: int,
                   ops: list[str]) -> bool:
    """El color de UN ciclo: el estampado si lo tiene, y si no el calculado.

    QUE MIDE, y por que dejo de medir lo de antes. Media recuperacion:
    `recaudacion(ciclo) < costo_fabrica_mm`, o sea cuanto de lo que Pedro
    paga por el plan le volvia a direccion vendiendole capacidad a la
    fabrica. Con la suscripcion como COSTO HUNDIDO (decision de Pedro del
    2026-08-31: "costo hundido de la fabrica, el cristal reemplaza"),
    consumir capacidad ya no transfiere una moneda a direccion: la
    recaudacion queda estructuralmente en cero, TODO ciclo daria rojo y a
    los dos rojos seguidos el breaker le exigiria firma a Pedro para
    renovar. El criterio viejo no quedo impreciso, quedo roto: no hay nada
    que recuperar.

    Lo que decide una renovacion cuando la plata ya se gasto es otra
    pregunta: la uso la fabrica? Un ciclo donde la fabrica consumio el 5%
    de la cuota que Pedro pago es plata tirada; uno que llego al techo es
    señal de que hace falta mas. Asi que el color mide APROVECHAMIENTO:
    rojo es consumir menos de `PISO_APROVECHAMIENTO_PCT` de la cuota del
    ciclo. El piso es propuesta de este trabajo, no decision de Pedro.

    Contra la cuota CONFIGURADA (`capacidad_fabrica`) y no contra los
    cristales emitidos: es el mismo numero con el que
    `mercado.consumir_capacidad` corta por "cuota agotada", asi que el
    techo que frena y el piso que pinta miden la misma cuota — y existe
    aunque `cristal.emitir_ciclo` no haya corrido nunca para ese ciclo.

    Que dependa de la configuracion de HOY es el mismo problema que
    `_color_estampado` ya resolvia para el criterio viejo, y lo sigue
    resolviendo para este: `capacidad_fabrica` es exactamente la perilla
    que `POST /api/economia/suscripciones/{n}/capacidad` mueve. Sin la
    estampa, repreciar la capacidad repintaria ciclos ya cerrados, y como
    `cerrar_ciclo` camina hacia atras contando rojos consecutivos, armaria
    o DESARMARIA el breaker hacia atras. Un ciclo cerrado tiene su color
    decidido, como sus asientos: se estampa al cerrar y despues se lee.

    POR CICLO ESTAMPADO Y NO POR SEMANA (`cap.consumo_fabrica_ciclo`).
    Consumir dejo de exigir semana operativa, asi que el consumo del lunes
    sin abrir —o de una semana entera que Pedro no abrio— no cae en las
    semanas de ningun ciclo: plegando por semana, un ciclo que se comio el
    87% de la cuota se informaba como ciclo sin uso, se pintaba rojo y dos
    asi armaban el breaker. Es la contracara del techo que frena, y por eso
    los dos leen el mismo pliegue.

    ARRANQUE EN FRIO. Una suscripcion recien sembrada no consumio nada
    porque la fabrica todavia no existe, y dos ciclos asi armarian el
    breaker antes del primer request. Se copia el patron con el que las
    quiebras no matan a un departamento recien nacido (`_primera_semana`
    y su `< semana`): a una suscripcion sin huella juzgable cuando el ciclo
    cerro no se la pinta de rojo. La huella es USO o JUICIO, nunca la
    maquinaria de la cuota (ver `_es_huella_juzgable`), y la estampa de
    color del ciclo anterior alcanza: la exencion dura el arranque —un
    ciclo— y no se vuelve un permiso permanente.
    """
    semanas = cap.semanas_del_ciclo(ciclo, ops)
    estampado = _color_estampado(asientos, sus.nombre, semanas)
    if estampado is not None:
        return estampado
    if not semanas:
        return False
    primera = _primera_semana_suscripcion(asientos, sus.nombre)
    if primera is None or primera >= semanas[-1]:
        return False  # no habia nada que juzgar cuando el ciclo cerro
    consumido = cap.consumo_fabrica_ciclo(asientos, sus.nombre, ciclo,
                                          semanas)
    # multiplicado en vez de dividido: con la division el piso se redondea
    # distinto segun el tamano de la cuota
    return consumido * 100 < sus.capacidad_fabrica * PISO_APROVECHAMIENTO_PCT


def cerrar_ciclo(mercado: Mercado, ts: str, semana: str,
                 cartas_atendidas: frozenset = frozenset(),
                 firmas: dict | None = None) -> list[dict]:
    firmas = firmas or {}
    k = mercado.k
    asientos = k.libro.asientos()
    ops = cap.semanas_operativas(asientos)
    ciclo, fraccion = cap.posicion_ciclo(semana, ops)
    if fraccion != 100:
        return []  # la semana no cierra un ciclo
    informes: list[dict] = []
    for nombre, sus in sorted(mercado.suscripciones.items()):
        semanas = cap.semanas_del_ciclo(ciclo, ops)
        recaudado = cap.recaudacion(asientos, nombre, semanas)
        # el mismo pliegue que decide el color, para que el informe y la
        # carta de renovacion no puedan contradecirlo
        consumido = cap.consumo_fabrica_ciclo(asientos, nombre, ciclo,
                                              semanas)
        rojo = _rojo_de_ciclo(asientos, sus, ciclo, ops)
        if _color_estampado(asientos, nombre, semanas) is None:
            # se estampa ANTES de caminar hacia atras, para que el ciclo que
            # cierra hoy se lea igual que los anteriores. Idempotente: una
            # segunda corrida sobre la misma semana encuentra la estampa y
            # no escribe otra. Van tambien los numeros con los que se
            # decidio: la estampa es la unica copia que queda de una cuenta
            # que la configuracion de manana ya no reproduce.
            k.apuntar(ts, semana, 1,
                      {"nota": NOTA_COLOR_CICLO, "suscripcion": nombre,
                       "ciclo": ciclo, "rojo": rojo,
                       "consumido": consumido,
                       "capacidad_fabrica": sus.capacidad_fabrica,
                       "piso_aprovechamiento_pct": PISO_APROVECHAMIENTO_PCT,
                       "recaudacion_mm": recaudado,
                       "costo_fabrica_mm": sus.costo_fabrica_mm})
            asientos = k.libro.asientos()
        rojos = 0
        c = ciclo
        while c >= 0 and _rojo_de_ciclo(asientos, sus, c, ops):
            rojos += 1
            c -= 1
        carta_id = f"renovacion:{nombre}"
        breaker = (rojos >= 2 and carta_id not in cartas_atendidas)
        requiere_firma = breaker and not firmas.get(nombre)
        ya_renovada = any(a.tipo is TipoAsiento.DESTRUCCION
                          and a.ref == carta_id and a.semana in semanas
                          for a in asientos)
        renovada = ya_renovada
        tesoro_insuficiente = False
        if not requiere_firma and not ya_renovada:
            # FIX I6 (spec-owner ruling): la renovacion se paga DESDE
            # DIRECCION, no directo del tesoro — el tesoro solo repone lo
            # que falte para cubrir el costo del mes. Si ni el tesoro
            # alcanza, no revienta con un SinSaldo crudo: se informa
            # (FIX I8b) y se sigue con la siguiente suscripcion.
            falta = sus.costo_mensual_mm - k.disponible(DIRECCION)
            if falta > 0:
                try:
                    k.transferir(ts, semana, TESORO, DIRECCION, falta,
                                 motivo="reposicion_direccion", ref=carta_id)
                except SinSaldo:
                    tesoro_insuficiente = True
            if not tesoro_insuficiente:
                detalle = {"firma": firmas[nombre]} if firmas.get(nombre) else None
                k.destruir(ts, semana, DIRECCION, sus.costo_mensual_mm,
                           motivo="renovacion", ref=carta_id,
                           detalle_extra=detalle)
                renovada = True
        informes.append({"suscripcion": nombre, "recaudacion_mm": recaudado,
                         "costo_fabrica_mm": sus.costo_fabrica_mm,
                         # lo que decide el color desde que la suscripcion
                         # es costo hundido: cuanto de la cuota se uso
                         "consumido_ciclo": consumido,
                         "capacidad_fabrica": sus.capacidad_fabrica,
                         "piso_aprovechamiento_pct": PISO_APROVECHAMIENTO_PCT,
                         "rojo": rojo, "rojos_consecutivos": rojos,
                         "renovada": renovada,
                         "requiere_firma": requiere_firma,
                         "tesoro_insuficiente": tesoro_insuficiente,
                         # FIX I8a: eficiencia de la suscripcion en el
                         # ciclo (cortes por departamento llegan con Plan 3).
                         # Con el `ciclo` para que su denominador sea el
                         # mismo `consumido` de arriba: si no, el informe se
                         # contradice a si mismo en una semana salteada.
                         "eficiencia_pormil": eficiencia.eficiencia_suscripcion(
                             asientos, sus, semanas, mercado.suscripciones,
                             ciclo)})
    return informes
