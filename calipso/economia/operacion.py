"""
calipso/economia/operacion.py — La rutina de frontera.

Abrir la semana (emitir PT) y cerrarla (expirar cola, cierre economico,
cartas a la cola, ciclo mensual con la atencion registrada) — todo bajo
el candado de escritor unico. Este modulo ES la frontera: sus llamadores
estampan fechas reales; el nucleo recibe ts y semana como datos.
"""
from __future__ import annotations

import datetime

from . import bus as bus_mod
from . import capacidad as cap
from . import cierre
from . import cola as cola_mod
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
                 reserva_personal_mpt: int):
    with candado(k.libro.ruta):
        return pt.emitir_semana(k, ts, semana, cuota_firmable_mpt,
                                reserva_personal_mpt)


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
        expiradas = cola.expirar_semana(k, ts, semana)
        res = cierre.cerrar_semana_economia(
            mercado, bus, ts, semana, refs_no_servidas=[],
            presupuesto_direccion_mm=presupuesto_direccion_mm)
        for carta in res.cartas:
            cola.encolar_carta(ts, semana, _id_carta(carta, semana), carta)
        informes = []
        if fraccion == 100:
            # traduccion cola -> cierre: solo la atencion del ciclo CORRIENTE
            # desarma el breaker, y las firmas se indexan por suscripcion
            sufijo = f":{ciclo}"
            atendidas = frozenset(
                "renovacion:" + id.split(":")[1]
                for id in cola.cartas_atendidas()
                if id.startswith("renovacion:") and id.endswith(sufijo))
            firmas = {id.split(":")[1]: f for id, f in cola.firmas().items()
                      if id.startswith("renovacion:") and id.endswith(sufijo)}
            informes = cierre.cerrar_ciclo(mercado, ts, semana,
                                           cartas_atendidas=atendidas,
                                           firmas=firmas)
            for inf in informes:
                if inf["requiere_firma"] or inf["rojo"]:
                    cola.encolar_carta(
                        ts, semana,
                        f"renovacion:{inf['suscripcion']}:{ciclo}",
                        {"tipo": "renovacion", **inf})
        return {"cierre": res, "informes_ciclo": informes,
                "expiradas": expiradas}
