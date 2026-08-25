"""
calipso/mapa/ciudad.py — Del libro al modelo.

Cada departamento es un edificio cuyo tamano sale de su saldo, cuyo estado
sale de su quiebra y cuya actividad sale de si gasto en los ultimos dias
del propio libro (nunca del reloj del sistema: eso romperia el
determinismo del mapa).
"""
from __future__ import annotations

import datetime

from calipso.economia import balances as bal
from calipso.economia import departamentos as deps
from calipso.economia.tipos import (Asiento, CUENTA_PEDRO, DIRECCION, Divisa,
                                    TESORO, TipoAsiento)

DIAS_ACTIVIDAD = 3
ACTIVIDAD_MAX = 3


def _digitos(n: int) -> int:
    return len(str(n)) if n > 0 else 0


def tamano_de(saldo_mm: int) -> int:
    """Escala 1-9: crece rapido al principio y lento despues, para que un
    departamento rico no tape a los demas."""
    return min(9, 1 + _digitos(max(0, saldo_mm) // 1000))


def actividad_de(asientos: list[Asiento], cuenta: str,
                 dias: int = DIAS_ACTIVIDAD) -> int:
    """Senal de vida barata: cuantos de los ultimos dias tuvieron gasto.
    La ventana se mide contra el ultimo asiento DEL LIBRO."""
    if not asientos:
        return 0
    fin = datetime.date.fromisoformat(max(a.ts for a in asientos)[:10])
    ventana = {(fin - datetime.timedelta(days=i)).isoformat()
               for i in range(dias)}
    salidas = (TipoAsiento.DESTRUCCION, TipoAsiento.TRANSFERENCIA)
    con_gasto = {a.ts[:10] for a in asientos
                 if a.origen == cuenta and a.tipo in salidas
                 and a.ts[:10] in ventana}
    return min(ACTIVIDAD_MAX, len(con_gasto))


def duenos_de(bus) -> dict[str, str]:
    """id de trabajo -> cuenta del departamento dueno."""
    return {id: bus.datos(id)["departamento"] for id in bus.ids()}


def _orden_de_aparicion(asientos: list[Asiento]) -> dict[str, int]:
    """Antiguedad: en que posicion aparecio cada cuenta por primera vez."""
    visto: dict[str, int] = {}
    for a in asientos:
        for cuenta in (a.destino, a.origen):
            if cuenta and cuenta not in visto:
                visto[cuenta] = len(visto)
    return visto


def edificios(asientos: list[Asiento], registro, bus, cola) -> list[dict]:
    saldos = bal.saldos(asientos)
    aparicion = _orden_de_aparicion(asientos)
    nunca = len(aparicion)
    duenos = duenos_de(bus)
    vivos = set(bus.activas())
    pendientes = [p for p in cola.pendientes() if not p.get("es_carta")]

    filas = [(d.cuenta, d.nombre, d.zona) for d in registro.todos()]
    filas.append((CUENTA_PEDRO, "pedro", deps.ZONA_PERSONAL))

    out = []
    for cuenta, nombre, zona in sorted(filas):
        saldo = saldos.get((cuenta, Divisa.MONEDA), 0)
        out.append({
            "id": cuenta,
            "nombre": nombre,
            "zona": zona,
            "orden": aparicion.get(cuenta, nunca),
            "tamano": tamano_de(saldo),
            "estado": ("congelado" if deps.es_congelado(asientos, cuenta)
                       else "activo"),
            "saldo_mm": saldo,
            "actividad": actividad_de(asientos, cuenta),
            "trabajos": sorted(id for id in vivos
                               if duenos.get(id) == cuenta),
            "compuertas": sum(1 for p in pendientes
                              if p.get("departamento") == cuenta),
        })
    return out
