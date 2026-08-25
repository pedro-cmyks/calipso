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
from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import personal as per_mod
from calipso.economia import pt
from calipso.economia.tipos import (Asiento, CUENTA_PEDRO, DIRECCION, Divisa,
                                    TESORO, TipoAsiento)

DIAS_ACTIVIDAD = 3
ACTIVIDAD_MAX = 3
VENTANA_SEMANAS = 8
_ANCHOS = ((10_000, 1), (100_000, 2), (1_000_000, 3))


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


def ancho_de(peso_mm: int) -> int:
    for tope, ancho in _ANCHOS:
        if peso_mm < tope:
            return ancho
    return 4


def calles(asientos: list[Asiento], edificios_: list[dict],
           duenos: dict[str, str], semanas: list[str]) -> list[dict]:
    """Comercio directo entre departamentos: servicios vendidos y
    financiacion del trabajo de otro. La compra de capacidad no cuenta:
    su destino es direccion, no el otro departamento."""
    zona = {e["id"]: e["zona"] for e in edificios_}
    pesos: dict[tuple[str, str], int] = {}
    for a in asientos:
        if a.tipo is not TipoAsiento.TRANSFERENCIA or a.semana not in semanas:
            continue
        motivo = a.detalle.get("motivo")
        if motivo == "servicio":
            otro = a.destino
        elif motivo == "financiacion" and a.destino.startswith("trabajo:"):
            otro = duenos.get(a.destino.split(":", 1)[1])
        else:
            continue
        if not otro or otro == a.origen:
            continue
        if a.origen not in zona or otro not in zona:
            continue
        par = tuple(sorted((a.origen, otro)))
        pesos[par] = pesos.get(par, 0) + a.monto
    return [{"a": x, "b": y, "peso_mm": p, "ancho": ancho_de(p),
             "tipo": "calle" if zona[x] == zona[y] else "cable"}
            for (x, y), p in sorted(pesos.items())]


def unidades(asientos: list[Asiento], bus, duenos: dict[str, str]) -> list[dict]:
    out = []
    for id in bus.activas():
        dueno = duenos.get(id, "")
        aportes = bus_mod.aportes(asientos, id)
        ajenos = sorted(((monto, quien) for quien, monto in aportes.items()
                         if quien != dueno), reverse=True)
        out.append({"id": id, "dueno": dueno,
                    "gastado_mm": bus_mod.gastado(asientos, id),
                    "hacia": ajenos[0][1] if ajenos else None})
    return out


def avisos(cola) -> list[dict]:
    out = []
    for p in cola.pendientes():
        if p.get("es_carta"):
            tipo = (p.get("carta") or {}).get("tipo", "carta")
            sobre = None
        else:
            tipo = p.get("tipo", "compuerta")
            sobre = p.get("departamento")
        out.append({"id": p["id"], "tipo": tipo, "sobre": sobre,
                    "monedas_en_juego_mm": p.get("monedas_en_juego", 0)})
    return out


def ciudad(asientos: list[Asiento], registro, bus, cola, semana: str,
           minutos_empleo: int = 0) -> dict:
    saldos = bal.saldos(asientos)
    ops = cap.semanas_operativas(asientos)
    ventana = ops[-VENTANA_SEMANAS:]
    edis = edificios(asientos, registro, bus, cola)
    duenos = duenos_de(bus)
    return {
        "semana": semana,
        "tesoro_mm": saldos.get((TESORO, Divisa.MONEDA), 0),
        "cuenta_pedro_mm": saldos.get((CUENTA_PEDRO, Divisa.MONEDA), 0),
        "direccion_mm": saldos.get((DIRECCION, Divisa.MONEDA), 0),
        "tipo_cambio_mm": pt.tipo_de_cambio(asientos, semana) if ops else 5_000,
        "linea_empleo_mm": per_mod.linea_empleo_mm_por_hora(
            per_mod.SUELDO_MENSUAL_MM, minutos_empleo),
        "edificios": edis,
        "calles": calles(asientos, edis, duenos, ventana),
        "unidades": unidades(asientos, bus, duenos),
        "avisos": avisos(cola),
    }
