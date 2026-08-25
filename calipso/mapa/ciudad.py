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
# que asientos sacan plata de una cuenta. Mismo criterio que bus.gastado:
# la ejecucion de una reserva tambien es plata que se fue.
_SALIDAS = (TipoAsiento.DESTRUCCION, TipoAsiento.TRANSFERENCIA,
            TipoAsiento.EJECUCION_RESERVA)


def _digitos(n: int) -> int:
    return len(str(n)) if n > 0 else 0


def tamano_de(saldo_mm: int) -> int:
    """Escala 1-9: crece rapido al principio y lento despues, para que un
    departamento rico no tape a los demas."""
    return min(9, 1 + _digitos(max(0, saldo_mm) // 1000))


def ultimo_ts(asientos: list[Asiento]) -> str | None:
    """El reloj del mapa es el libro, nunca el del sistema."""
    return max((a.ts for a in asientos), default=None)


def actividad_de(asientos: list[Asiento], cuenta: str,
                 dias: int = DIAS_ACTIVIDAD, fin_ts: str | None = None) -> int:
    """Senal de vida barata: cuantos de los ultimos dias tuvieron gasto.
    La ventana se mide contra el ultimo asiento DEL LIBRO. `fin_ts` se pasa
    ya calculado desde arriba para no volver a recorrer el libro por
    edificio."""
    fin_ts = fin_ts or ultimo_ts(asientos)
    if fin_ts is None:
        return 0
    fin = datetime.date.fromisoformat(fin_ts[:10])
    ventana = {(fin - datetime.timedelta(days=i)).isoformat()
               for i in range(dias)}
    con_gasto = {a.ts[:10] for a in asientos
                 if a.origen == cuenta and a.tipo in _SALIDAS
                 and a.ts[:10] in ventana}
    return min(ACTIVIDAD_MAX, len(con_gasto))


def duenos_de(bus) -> dict[str, str]:
    """id de trabajo -> cuenta del departamento dueno."""
    return {id: bus.datos(id)["departamento"] for id in bus.ids()}


def _orden_de_aparicion(asientos: list[Asiento],
                        cuentas: set[str]) -> dict[str, int]:
    """Antiguedad: en que posicion aparecio cada EDIFICIO por primera vez.

    Solo cuentan las cuentas que van a ser edificios: `pt:fabrica`,
    `tesoro` y `direccion` no son departamentos y si se los cuenta se
    quedan con los primeros lugares. Dentro de un mismo asiento se lee
    primero el origen: en una transferencia entre dos cuentas nuevas, el
    que paga ya tenia plata, asi que es el mas viejo."""
    visto: dict[str, int] = {}
    for a in asientos:
        for cuenta in (a.origen, a.destino):
            if cuenta in cuentas and cuenta not in visto:
                visto[cuenta] = len(visto)
    return visto


def lapso_ventana(ops: list[str],
                  ventana: int = VENTANA_SEMANAS) -> tuple[str, str]:
    """La ventana de comercio como LAPSO entre la primera y la ultima de
    las `ventana` semanas operativas, no como pertenencia al conjunto de
    etiquetas: una venta no desaparece de la ventana solo porque su semana
    no tuvo emision de PT. Mismo criterio que pt.tipo_de_cambio.

    Devuelve (piso exclusivo, techo inclusivo)."""
    if not ops:
        return ("", "")
    return (ops[-ventana - 1] if len(ops) > ventana else "", ops[-1])


def en_ventana(semana: str, lapso: tuple[str, str]) -> bool:
    piso, techo = lapso
    return bool(techo) and piso < semana <= techo


def edificios(asientos: list[Asiento], registro, bus, cola) -> list[dict]:
    return _edificios(asientos, registro, bus.activas(), duenos_de(bus),
                      cola.pendientes(), bal.saldos(asientos))


def _edificios(asientos: list[Asiento], registro, activas: list[str],
               duenos: dict[str, str], pendientes: list[dict],
               saldos: dict) -> list[dict]:
    filas = [(d.cuenta, d.nombre, d.zona) for d in registro.todos()]
    filas.append((CUENTA_PEDRO, "pedro", deps.ZONA_PERSONAL))
    cuentas = {c for c, _, _ in filas}
    aparicion = _orden_de_aparicion(asientos, cuentas)
    nunca = len(aparicion)
    vivos = set(activas)
    compuertas = [p for p in pendientes if not p.get("es_carta")]
    fin_ts = ultimo_ts(asientos)

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
            "actividad": actividad_de(asientos, cuenta, fin_ts=fin_ts),
            "trabajos": sorted(id for id in vivos
                               if duenos.get(id) == cuenta),
            "compuertas": sum(1 for p in compuertas
                              if p.get("departamento") == cuenta),
        })
    return out


def ancho_de(peso_mm: int) -> int:
    for tope, ancho in _ANCHOS:
        if peso_mm < tope:
            return ancho
    return 4


def calles(asientos: list[Asiento], edificios_: list[dict],
           duenos: dict[str, str], lapso: tuple[str, str]) -> list[dict]:
    """Comercio directo entre departamentos: servicios vendidos y
    financiacion del trabajo de otro. La compra de capacidad no cuenta:
    su destino es direccion, no el otro departamento."""
    zona = {e["id"]: e["zona"] for e in edificios_}
    pesos: dict[tuple[str, str], int] = {}
    for a in asientos:
        if (a.tipo is not TipoAsiento.TRANSFERENCIA
                or not en_ventana(a.semana, lapso)):
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


def unidades(asientos: list[Asiento], activas: list[str],
             duenos: dict[str, str], calles_: list[dict]) -> list[dict]:
    """La unidad camina por una calle, asi que `hacia` solo puede nombrar a
    un cofinanciador que TENGA calle en el modelo. Los aportes se leen del
    libro entero pero las calles son de la ventana: un trabajo de larga
    vida con la financiacion ya fuera de ventana no tiene a donde caminar,
    y entonces `hacia` es None y el cliente lo dibuja quieto en su casa."""
    con_calle = {(c["a"], c["b"]) for c in calles_}
    out = []
    for id in activas:
        dueno = duenos.get(id, "")
        aportes = bus_mod.aportes(asientos, id)
        ajenos = sorted(((monto, quien) for quien, monto in aportes.items()
                         if quien != dueno
                         and tuple(sorted((dueno, quien))) in con_calle),
                        reverse=True)
        out.append({"id": id, "dueno": dueno,
                    "gastado_mm": bus_mod.gastado(asientos, id),
                    "hacia": ajenos[0][1] if ajenos else None})
    return out


def avisos(pendientes: list[dict]) -> list[dict]:
    out = []
    for p in pendientes:
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
    # todo lo caro se calcula UNA vez y baja por parametro: este pliegue
    # corre bajo el candado del libro en cada refresco del mapa, y
    # cola.pendientes() es cuadratico en los eventos de la cola.
    saldos = bal.saldos(asientos)
    pendientes = cola.pendientes()
    duenos = duenos_de(bus)
    activas = bus.activas()
    ops = cap.semanas_operativas(asientos)
    lapso = lapso_ventana(ops)
    edis = _edificios(asientos, registro, activas, duenos, pendientes, saldos)
    cas = calles(asientos, edis, duenos, lapso)
    return {
        "semana": semana,
        "tesoro_mm": saldos.get((TESORO, Divisa.MONEDA), 0),
        "cuenta_pedro_mm": saldos.get((CUENTA_PEDRO, Divisa.MONEDA), 0),
        "direccion_mm": saldos.get((DIRECCION, Divisa.MONEDA), 0),
        "tipo_cambio_mm": pt.tipo_de_cambio(asientos, semana) if ops else 5_000,
        "linea_empleo_mm": per_mod.linea_empleo_mm_por_hora(
            per_mod.SUELDO_MENSUAL_MM, minutos_empleo),
        "edificios": edis,
        "calles": cas,
        "unidades": unidades(asientos, activas, duenos, cas),
        "avisos": avisos(pendientes),
    }
