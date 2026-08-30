"""
calipso/economia/cierre.py — El pulso de la economia.

El cierre semanal ejecuta en orden: muertes de trabajos, quiebras,
presupuestos (direccion y departamentos, dentro del mandato), cartas de
cierre departamental, y el cierre de PT. El cierre de ciclo (cada 4
semanas operativas) decide renovaciones con numeros — recaudacion contra
costo prorrateado — y aplica el circuit breaker: dos ciclos rojos con la
carta sin atender vuelven la renovacion manual (spec 4.2).
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


def _rojo_de_ciclo(asientos, sus: cap.Suscripcion, ciclo: int,
                   ops: list[str]) -> bool:
    """El color de UN ciclo: el estampado si lo tiene, y si no el calculado.

    El calculo compara la recaudacion de ese ciclo contra el
    `costo_fabrica_mm` de HOY, y ese numero se mueve: es
    `costo_mensual_mm * (capacidad_ciclo - reserva_personal) //
    capacidad_ciclo`, o sea que depende de la perilla que
    `POST /api/economia/suscripciones/{n}/capacidad` reprecia. Con eso
    solo, repreciar la capacidad cambiaba RETROACTIVAMENTE el color de
    ciclos ya cerrados -- y `cerrar_ciclo` camina hacia atras contando
    rojos consecutivos, asi que armaba o DESARMABA el circuit breaker de
    renovacion: dos ciclos rojos que exigian la firma de Pedro pasaban a
    uno, la suscripcion se renovaba sola y el breaker no aparecia nunca.
    Este es el pliegue que compara ciclos entre si con consecuencia real,
    y no lo cubria ningun guardia: el del ciclo en curso mira
    `consumido > capacidad_fabrica`, no el color de los anteriores.

    Un ciclo cerrado tiene su color decidido, como sus asientos: se estampa
    al cerrar y despues se lee. Los cerrados ANTES de este cambio no tienen
    estampa y se siguen calculando como antes -- no hay de donde sacarles
    el numero que tenian, y inventarlo seria peor que declararlo.
    """
    semanas = cap.semanas_del_ciclo(ciclo, ops)
    estampado = _color_estampado(asientos, sus.nombre, semanas)
    if estampado is not None:
        return estampado
    return cap.recaudacion(asientos, sus.nombre, semanas) < sus.costo_fabrica_mm


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
        rojo = _rojo_de_ciclo(asientos, sus, ciclo, ops)
        if _color_estampado(asientos, nombre, semanas) is None:
            # se estampa ANTES de caminar hacia atras, para que el ciclo que
            # cierra hoy se lea igual que los anteriores. Idempotente: una
            # segunda corrida sobre la misma semana encuentra la estampa y
            # no escribe otra.
            k.apuntar(ts, semana, 1,
                      {"nota": NOTA_COLOR_CICLO, "suscripcion": nombre,
                       "ciclo": ciclo, "rojo": rojo,
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
                         "rojo": rojo, "rojos_consecutivos": rojos,
                         "renovada": renovada,
                         "requiere_firma": requiere_firma,
                         "tesoro_insuficiente": tesoro_insuficiente,
                         # FIX I8a: eficiencia de la suscripcion en el
                         # ciclo (cortes por departamento llegan con Plan 3)
                         "eficiencia_pormil": eficiencia.eficiencia_suscripcion(
                             asientos, sus, semanas, mercado.suscripciones)})
    return informes
