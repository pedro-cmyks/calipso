"""
calipso/economia/operacion.py — La rutina de frontera.

Abrir la semana (emitir PT, y la cuota de cristal si la semana abre un
ciclo) y cerrarla (expirar cola, cierre economico, cartas a la cola, ciclo
mensual con la atencion registrada y el barrido de los pools de cristal) —
todo bajo el candado de escritor unico. Este modulo ES la frontera: sus
llamadores estampan fechas reales; el nucleo recibe ts y semana como datos.

Los dos ciclos de vida corren aca porque aca esta el pulso: el PT vive una
SEMANA (se emite al abrir, expira al cerrar) y el cristal vive un CICLO
(cuatro semanas operativas, que es lo que la suscripcion factura y
resetea). Son cadencias distintas sobre el mismo latido.
"""
from __future__ import annotations

import datetime
import sys

from . import bus as bus_mod
from . import capacidad as cap
from . import cierre
from . import cola as cola_mod
from . import cristal as cristal_mod
from . import pt
from .candado import candado
from .capacidad import ErrorCapacidad
from .kernel import Kernel
from .mercado import Mercado


class ErrorOperacion(Exception):
    pass


def semana_iso(fecha: str) -> str:
    d = datetime.date.fromisoformat(fecha)
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def abrir_semana(k: Kernel, ts: str, semana: str, cuota_firmable_mpt: int,
                 reserva_personal_mpt: int,
                 suscripciones: dict[str, cap.Suscripcion] | None = None):
    """Emite el PT de la semana y, si esta semana ABRE un ciclo, la cuota
    de cristal de cada suscripcion.

    `suscripciones` es opcional porque el PT no las necesita y hay
    llamadores (tests, arranques a mano) que solo abren la semana. Sin
    ellas la fabrica igual puede consumir capacidad —`cristal.consumir`
    nunca rechaza— pero el pool arranca en cero, cada consumo queda
    estampado como descubierto y `cristal.totales()` reporta cuota 0 contra
    consumo N. O sea: no rompe, miente.

    La emision de cristal va DESPUES del PT y no puede voltearlo. El PT ya
    quedo escrito y el libro no tiene rollback (`libro.append`), asi que
    una cuota que no se puede emitir —tipicamente un pool del ciclo
    anterior sin barrer, porque la ultima semana de ese ciclo nunca se
    cerro— dejaria la semana a medio abrir y sin forma de reintentar. Se
    informa y se sigue: el consumo del ciclo corre en descubierto, que es
    un estado declarado legal y visible, no una perdida de datos.
    """
    with candado(k.libro.ruta):
        emitidos = pt.emitir_semana(k, ts, semana, cuota_firmable_mpt,
                                    reserva_personal_mpt)
        if suscripciones:
            ops = cap.semanas_operativas(k.libro.asientos())
            ciclo, _fraccion = cap.posicion_ciclo(semana, ops)
            # "abre el ciclo" es ser su PRIMERA semana operativa, no una
            # fraccion: comparar contra un porcentaje ata esto a que
            # SEMANAS_POR_CICLO divida a 100.
            if cap.semanas_del_ciclo(ciclo, ops)[0] == semana:
                for _nombre, sus in sorted(suscripciones.items()):
                    try:
                        cristal_mod.emitir_ciclo(k, ts, semana, ciclo, sus)
                    except cristal_mod.ErrorCristal as exc:
                        print(f"[operacion] cuota de cristal sin emitir "
                              f"({sus.nombre}, ciclo {ciclo}): {exc}",
                              file=sys.stderr)
        return emitidos


def _id_carta(carta: dict, semana: str) -> str:
    quien = carta.get("departamento") or carta.get("suscripcion") or "general"
    return f"{carta['tipo']}:{quien}:{semana}"


def cerrar_semana_operativa(mercado: Mercado, bus: bus_mod.Bus,
                            cola: cola_mod.Cola, ts: str, semana: str,
                            presupuesto_direccion_mm: int = 0) -> dict:
    k = mercado.k
    with candado(k.libro.ruta):
        try:
            ops = cap.semanas_operativas(k.libro.asientos())
            ciclo, fraccion = cap.posicion_ciclo(semana, ops)
        except ErrorCapacidad as exc:
            raise ErrorOperacion(
                f"la semana no esta abierta (emitir primero): {exc}") from exc
        if semana != ops[-1]:
            raise ErrorOperacion(
                f"solo se cierra la ultima semana abierta ({ops[-1]}), no {semana}")
        expiradas = cola.expirar_semana(k, ts, semana)
        res = cierre.cerrar_semana_economia(
            mercado, bus, ts, semana, refs_no_servidas=[],
            presupuesto_direccion_mm=presupuesto_direccion_mm)
        for carta in res.cartas:
            cola.encolar_carta(ts, semana, _id_carta(carta, semana), carta)
        informes = []
        cierre_cristal = None
        if fraccion == 100:
            # traduccion cola -> cierre: la carta de renovacion del ciclo
            # ANTERIOR (creada en su cierre con sufijo :N-1) es la que Pedro
            # atiende durante el ciclo corriente, asi que ambos sufijos
            # cuentan para desarmar el breaker; las firmas se indexan por
            # suscripcion
            sufijos = (f":{ciclo - 1}", f":{ciclo}")
            atendidas = frozenset(
                "renovacion:" + id.split(":")[1]
                for id in cola.cartas_atendidas()
                if id.startswith("renovacion:") and id.endswith(sufijos))
            firmas = {id.split(":")[1]: f for id, f in cola.firmas().items()
                      if id.startswith("renovacion:") and id.endswith(sufijos)}
            informes = cierre.cerrar_ciclo(mercado, ts, semana,
                                           cartas_atendidas=atendidas,
                                           firmas=firmas)
            for inf in informes:
                if inf["requiere_firma"] or inf["rojo"]:
                    cola.encolar_carta(
                        ts, semana,
                        f"renovacion:{inf['suscripcion']}:{ciclo}",
                        {"tipo": "renovacion", **inf})
            # el barrido de los pools de cristal cierra el ciclo en cero:
            # lo que sobro expira (la capacidad no se ahorra de un ciclo
            # para el otro) y el descubierto se condona. Va DESPUES del
            # informe: el color del ciclo se lee sobre el libro tal como el
            # ciclo corrio, no sobre uno ya barrido. Un fallo aca no puede
            # voltear un cierre ya escrito, por lo mismo que en
            # `abrir_semana`: se informa y el ciclo siguiente lo reintenta.
            try:
                cierre_cristal = cristal_mod.cerrar_ciclo(
                    k, ts, semana, ciclo, mercado.suscripciones)
            except cristal_mod.ErrorCristal as exc:
                print(f"[operacion] pools de cristal sin barrer "
                      f"(ciclo {ciclo}): {exc}", file=sys.stderr)
        return {"cierre": res, "informes_ciclo": informes,
                "expiradas": expiradas, "cierre_cristal": cierre_cristal}
