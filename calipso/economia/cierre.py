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

from dataclasses import dataclass

from . import bus as bus_mod
from . import capacidad as cap
from . import departamentos as deps
from . import direccion
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
        k.transferir(ts, semana, TESORO, DIRECCION, presupuesto_direccion_mm,
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
            direccion.asignar_presupuesto(mercado, ts, semana, dep.cuenta,
                                          dep.presupuesto_semanal_mm - ya,
                                          umbral_mm=umbral_mandato_mm)
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
        if primera is None or primera not in ops:
            continue
        if len(ops) - ops.index(primera) < ventana_carta_cierre:
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


def _rojo_de_ciclo(asientos, sus: cap.Suscripcion, ciclo: int,
                   ops: list[str]) -> bool:
    semanas = cap.semanas_del_ciclo(ciclo, ops)
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
        rojo = recaudado < sus.costo_fabrica_mm
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
        if not requiere_firma and not ya_renovada:
            detalle = {"firma": firmas[nombre]} if firmas.get(nombre) else None
            k.destruir(ts, semana, TESORO, sus.costo_mensual_mm,
                       motivo="renovacion", ref=carta_id,
                       detalle_extra=detalle)
            renovada = True
        informes.append({"suscripcion": nombre, "recaudacion_mm": recaudado,
                         "costo_fabrica_mm": sus.costo_fabrica_mm,
                         "rojo": rojo, "rojos_consecutivos": rojos,
                         "renovada": renovada,
                         "requiere_firma": requiere_firma})
    return informes
