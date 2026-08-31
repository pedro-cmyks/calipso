"""
calipso/economia/eficiencia.py — Resultado por unidad consumida.

Cada venta con trabajo de origen se prorratea entre los consumos de ese
trabajo, proporcional al costo API equivalente de cada consumo (spec 4.2).
El numerador es siempre senal exterior (subtipo venta); el capital y las
ventas sin trabajo no atribuyen nada.

El denominador cuenta capacidad en DOS formas —la compra vieja en monedas
y el consumo de cristal de hoy— y las lee en un solo lugar,
`consumo_de_suscripcion`: es el punto donde este modulo se acopla a la
divisa, y esta escrito una vez para que los tres pliegues no puedan
discrepar.
"""
from __future__ import annotations

from .capacidad import Suscripcion
from .tipos import (Asiento, DIRECCION, SubtipoAcunacion, TipoAsiento,
                    ZONA_CRISTAL_FABRICA)

# el prefijo de la cuenta de un trabajo (`bus.cuenta_trabajo`), escrito aca
# como lo escribe `mercado._politica`: importar `bus` desde este modulo de
# lectura pura seria traerse media economia para comparar un prefijo.
PREFIJO_TRABAJO = "trabajo:"


def consumo_de_suscripcion(a: Asiento,
                           suscripciones: dict[str, Suscripcion]
                           ) -> tuple[str, int] | None:
    """(suscripcion, milimonedas de API equivalentes) si el asiento es
    consumo de capacidad DE LA FABRICA; None si no lo es.

    Este modulo no importaba `Divisa` ni una vez: su filtro por divisa era
    implicito, via `TipoAsiento.TRANSFERENCIA`, que el validador fuerza a
    moneda (`tipos.Asiento.validar`). Con la suscripcion como costo hundido
    el consumo dejo de ser una transferencia y paso a ser un
    `CONSUMO_CRISTAL`, o sea INVISIBLE para ese filtro — y una eficiencia
    ciega a su propio denominador no levanta ninguna excepcion: informa
    cero (ver `eficiencia_pormil`) y ese cero va derecho al informe de
    renovacion que lee Pedro.

    Las dos formas se leen aca, en un solo lugar, para que los tres
    pliegues de abajo no puedan quedar desincronizados entre si. El libro
    es append-only: las compras viejas siguen siendo consumo real y siguen
    contando.

    La unidad es la trampa: la transferencia lleva las unidades en
    `detalle["unidades"]` y su MONTO son milimonedas de precio por escasez
    —que no es costo de API—, mientras que el consumo de cristal lleva las
    unidades en el monto (un cristal = una unidad). Las dos se convierten
    con `costo_api_mm_por_unidad`, que es la moneda comun de este modulo:
    lo que esa unidad habria costado por API.
    """
    nombre = a.detalle.get("suscripcion")
    if nombre not in suscripciones:
        return None
    sus = suscripciones[nombre]
    if a.tipo is TipoAsiento.TRANSFERENCIA and a.destino == DIRECCION:
        return nombre, a.detalle["unidades"] * sus.costo_api_mm_por_unidad
    if (a.tipo is TipoAsiento.CONSUMO_CRISTAL
            and a.detalle.get("zona") == ZONA_CRISTAL_FABRICA):
        return nombre, a.monto * sus.costo_api_mm_por_unidad
    return None


def ventas_por_trabajo(asientos: list[Asiento],
                       semanas: list[str]) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in asientos:
        if (a.tipo is TipoAsiento.ACUNACION
                and a.subtipo == SubtipoAcunacion.VENTA.value
                and a.semana in semanas and a.detalle.get("trabajo")):
            id = a.detalle["trabajo"]
            out[id] = out.get(id, 0) + a.monto
    return out


def costos_de_trabajo(asientos: list[Asiento], id: str,
                      suscripciones: dict[str, Suscripcion],
                      semanas: list[str] | None = None) -> dict[str, int]:
    ref = PREFIJO_TRABAJO + id
    out: dict[str, int] = {}
    for a in asientos:
        if a.ref != ref:
            continue
        if semanas is not None and a.semana not in semanas:
            continue
        if (a.tipo is TipoAsiento.DESTRUCCION
                and a.detalle.get("motivo") == "api"):
            out["api"] = out.get("api", 0) + a.monto
            continue
        consumo = consumo_de_suscripcion(a, suscripciones)
        if consumo:
            nombre, mm = consumo
            clave = f"sus:{nombre}"
            out[clave] = out.get(clave, 0) + mm
    return out


def atribucion_por_suscripcion(asientos: list[Asiento], semanas: list[str],
                               suscripciones: dict[str, Suscripcion]
                               ) -> dict[str, int]:
    out: dict[str, int] = {}
    for id, venta in ventas_por_trabajo(asientos, semanas).items():
        costos = costos_de_trabajo(asientos, id, suscripciones)
        total = sum(costos.values())
        if total == 0:
            continue
        for clave, costo in costos.items():
            if clave.startswith("sus:"):
                nombre = clave[4:]
                out[nombre] = out.get(nombre, 0) + venta * costo // total
    return out


def eficiencia_pormil(atribuido_mm: int, consumido_api_mm: int) -> int:
    if consumido_api_mm <= 0:
        return 0
    return atribuido_mm * 1000 // consumido_api_mm


def eficiencia_suscripcion(asientos: list[Asiento], sus: Suscripcion,
                           semanas: list[str],
                           suscripciones: dict[str, Suscripcion],
                           ciclo: int | None = None) -> int:
    """Por mil de venta atribuida sobre el API equivalente consumido.

    `ciclo` mueve la ventana del DENOMINADOR, y solo la del denominador:
    con un ciclo dado, un consumo de cristal cuenta por el ciclo ESTAMPADO
    en vez de por su semana. Lo pasa `cierre.cerrar_ciclo`, que informa
    sobre un ciclo y no sobre una lista de semanas: consumir dejo de
    esperar al boton de abrir la semana, asi que el consumo de una semana
    que Pedro nunca abrio no cae en las semanas de ningun ciclo — y un
    denominador que pierde lo que el mismo informe cuenta en
    `consumido_ciclo` deja la carta de renovacion contradiciendose sola,
    diciendo "uso 700 de 800" al lado de "0 por mil".

    El NUMERADOR sigue siendo por semana, y esta bien: una venta es un
    hecho de su semana y no sale de ningun pool. Sin `ciclo` todo se pliega
    por semana, que es lo que necesita quien mira una ventana movil
    (`eficiencia_departamento`) en vez de un ciclo de facturacion.
    """
    atribuida = atribucion_por_suscripcion(asientos, semanas,
                                           suscripciones).get(sus.nombre, 0)
    consumido = 0
    for a in asientos:
        if ciclo is not None and a.tipo is TipoAsiento.CONSUMO_CRISTAL:
            en_ventana = a.detalle.get("ciclo") == ciclo
        else:
            en_ventana = a.semana in semanas
        if not en_ventana:
            continue
        consumo = consumo_de_suscripcion(a, suscripciones)
        if consumo and consumo[0] == sus.nombre:
            consumido += consumo[1]
    return eficiencia_pormil(atribuida, consumido)


def costo_api_directo(asientos: list[Asiento], dep_cuenta: str,
                      semanas: list[str],
                      suscripciones: dict[str, Suscripcion]) -> int:
    """Gasto directo del departamento (sin trabajos) en API equivalente.

    "Directo" se decidia con `a.origen == dep_cuenta`, que alcanzaba
    mientras todo gasto salia de una cuenta: el gasto de un trabajo tiene
    origen `trabajo:<id>` y por eso quedaba afuera (lo cuenta
    `costos_de_trabajo`, y sumar los dos lo contaria dos veces). Un consumo
    de cristal no sale de ninguna cuenta de departamento: sale del POOL
    (`cristal:<sus>:<zona>`), y el departamento viaja en
    `detalle["titular"]`. Con el filtro por origen adelante, TODO consumo de
    cristal se descartaba antes de mirarle el tipo.

    Asi que para el cristal el corte es otro y es el mismo de siempre en
    espiritu: es directo lo que el departamento consumio como titular y NO
    en nombre de un trabajo suyo — el consumo de un trabajo lleva su ref
    forzado (`mercado.consumir_capacidad`, FIX I4) y lo cuenta
    `costos_de_trabajo`.
    """
    total = 0
    for a in asientos:
        if a.semana not in semanas:
            continue
        if (a.tipo is TipoAsiento.DESTRUCCION and a.origen == dep_cuenta
                and a.detalle.get("motivo") == "api"):
            total += a.monto
            continue
        propio = (a.origen == dep_cuenta
                  or (a.detalle.get("titular") == dep_cuenta
                      and not (a.ref or "").startswith(PREFIJO_TRABAJO)))
        if not propio:
            continue
        consumo = consumo_de_suscripcion(a, suscripciones)
        if consumo:
            total += consumo[1]
    return total


def eficiencia_departamento(asientos: list[Asiento], dep_cuenta: str,
                            semanas: list[str],
                            suscripciones: dict[str, Suscripcion],
                            duenos: dict[str, str]) -> int:
    ventas = sum(v for id, v in ventas_por_trabajo(asientos, semanas).items()
                 if duenos.get(id) == dep_cuenta)
    consumido = costo_api_directo(asientos, dep_cuenta, semanas, suscripciones)
    trabajos = {id for id, d in duenos.items() if d == dep_cuenta}
    for id in trabajos:
        consumido += sum(costos_de_trabajo(asientos, id, suscripciones,
                                           semanas).values())
    return eficiencia_pormil(ventas, consumido)
