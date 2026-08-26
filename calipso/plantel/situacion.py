"""
calipso/plantel/situacion.py — Del libro al estado del departamento.

Lo que el jefe mira antes de decidir. Pura y gratis: pliega asientos y
archivos de estado, no llama a ningun modelo, no abre red y no lee el reloj
del sistema. Misma clase de funcion que calipso/mapa/ciudad.py, y se testea
igual: contra un libro sintetico, campo por campo.
"""
from __future__ import annotations

from calipso.economia import balances as bal
from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import mercado as mercado_mod
from calipso.economia.tipos import Divisa, TipoAsiento

# Que asientos sacan plata de una cuenta. Mismo criterio que bus.gastado y
# que mapa/ciudad.py: dos lecturas del mismo libro no pueden discrepar sobre
# que es gasto.
_SALIDAS = (TipoAsiento.DESTRUCCION, TipoAsiento.TRANSFERENCIA,
            TipoAsiento.EJECUCION_RESERVA)


def salidas_de(asientos, cuenta: str, semanas: list[str]) -> int:
    """Todo lo que salio de la cuenta en esas semanas."""
    return sum(a.monto for a in asientos
               if a.tipo in _SALIDAS and a.origen == cuenta
               and a.semana in semanas and a.divisa is Divisa.MONEDA)


def _capacidad(asientos, suscripciones, semana, ops):
    """La suscripcion mas barata ahora mismo, con su precio y su ritmo.

    El jefe no elige proveedor —eso es el spec de mezcla multi-proveedor—
    pero si necesita saber si sobra capacidad barata, porque es lo que hace
    racional explorar a fin de ciclo."""
    if not suscripciones or not ops or semana not in ops:
        return None
    ciclo, fraccion = cap.posicion_ciclo(semana, ops)
    semanas = cap.semanas_del_ciclo(ciclo, ops)
    mejor = None
    for nombre, sus in sorted(suscripciones.items()):
        consumido = cap.consumo_fabrica(asientos, nombre, semanas)
        fila = {"nombre": nombre,
                "precio_mm": cap.precio_unidad_mm(sus, consumido, fraccion),
                "precio_base_mm": sus.precio_base_mm,
                "consumido": consumido,
                "capacidad_fabrica": sus.capacidad_fabrica,
                "fraccion_ciclo_pct": fraccion}
        if mejor is None or fila["precio_mm"] < mejor["precio_mm"]:
            mejor = fila
    return mejor


def situacion(kernel, registro, bus, cola, suscripciones, semana: str,
              cuenta: str) -> dict:
    """Todo lo que el jefe necesita para decidir, plegado del libro."""
    asientos = kernel.libro.asientos()
    dep = registro.obtener(cuenta.split(":", 1)[1])
    ops = cap.semanas_operativas(asientos)
    semanas_ciclo = []
    if ops and semana in ops:
        ciclo, _ = cap.posicion_ciclo(semana, ops)
        semanas_ciclo = cap.semanas_del_ciclo(ciclo, ops)

    # OJO con los estados del bus: `alta` es una propuesta sin financiar y
    # `financiada` es un trabajo vivo. `bus.activas()` devuelve SOLO las
    # financiadas, asi que iterar por ahi dejaria al jefe sin ver ninguna
    # propuesta — y `comentar` sin nada sobre lo que opinar.
    trabajos, propias, ajenas = [], [], []
    for id_ in bus.ids():
        estado = bus.estado(id_)
        if estado not in ("alta", "financiada"):
            continue                       # muerta o liquidada: ya no se decide
        datos = bus.datos(id_)
        mio = datos.get("departamento") == cuenta
        base = {"id": id_, "titulo": datos.get("titulo", ""),
                "presupuesto_mm": datos.get("presupuesto_mm", 0)}
        if estado == "financiada":
            if mio:
                trabajos.append({**base,
                                 "gastado_mm": bus_mod.gastado(asientos, id_)})
            continue
        if mio:
            propias.append(base)           # ya la propuso: no la repita
        else:
            ajenas.append({**base, "dueno": datos.get("departamento", "")})

    return {
        "cuenta": cuenta,
        "nombre": dep.nombre,
        "zona": dep.zona,
        "saldo_mm": bal.saldos(asientos).get((cuenta, Divisa.MONEDA), 0),
        "disponible_mm": kernel.disponible(cuenta),
        "presupuesto_semanal_mm": dep.presupuesto_semanal_mm,
        "explorar_explotar_pct": dep.explorar_explotar_pct,
        "agresividad_pct": dep.agresividad_pct,
        "techo_api_ciclo_mm": dep.techo_api_ciclo_mm,
        "gasto_api_ciclo_mm": mercado_mod.gasto_api_ciclo(
            asientos, cuenta, semanas_ciclo) if semanas_ciclo else 0,
        "salidas_semana_mm": salidas_de(asientos, cuenta, [semana]),
        "trabajos": trabajos,
        "propuestas_propias": propias,
        "propuestas_ajenas": ajenas,
        "compuertas_pendientes": sum(
            1 for c in cola.pendientes() if c.get("departamento") == cuenta),
        "capacidad": _capacidad(asientos, suscripciones, semana, ops),
    }
