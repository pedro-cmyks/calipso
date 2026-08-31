"""
calipso/economia/capacidad.py — Suscripciones como capacidad revendida.

Las monedas miden plata; la cuota mide capacidad (spec 4.2). Este modulo
es pura derivacion: la configuracion de cada suscripcion (con la reserva
personal de Pedro prorrateada fuera de la economia de la fabrica) y las
funciones que pliegan consumo, precio por escasez y recaudacion desde el
libro. Quien ESCRIBE compras es el Mercado.
"""
from __future__ import annotations

from dataclasses import dataclass

from .tipos import (Asiento, TipoAsiento, DIRECCION, ZONA_CRISTAL_FABRICA,
                    es_nombre_suscripcion)

SEMANAS_POR_CICLO = 4


class ErrorCapacidad(Exception):
    pass


def _entero_positivo(valor: int, nombre: str) -> None:
    if not isinstance(valor, int) or isinstance(valor, bool) or valor <= 0:
        raise ErrorCapacidad(f"{nombre} debe ser entero positivo: {valor!r}")


@dataclass(frozen=True)
class Suscripcion:
    nombre: str
    costo_mensual_mm: int
    capacidad_ciclo: int
    reserva_personal: int
    costo_api_mm_por_unidad: int

    def __post_init__(self):
        # El nombre es el que va a nombrar las cuentas de cristal
        # (`cristal:<nombre>:<zona>`), asi que se valida ACA, contra la
        # misma gramatica del libro. Antes se construia cualquier cosa
        # —"Claude_Max", "claude max"— y el fallo llegaba tarde, en el
        # append, como `AsientoInvalido`: una excepcion de otra capa, que
        # el pagador no cuenta entre las economicas y que por lo tanto
        # rompia el dispatch en vez de aparcar el cargo.
        if not es_nombre_suscripcion(self.nombre):
            raise ErrorCapacidad(
                f"nombre de suscripcion invalido: {self.nombre!r} "
                "(minusculas, digitos, guion y guion bajo)")
        _entero_positivo(self.costo_mensual_mm, "costo_mensual_mm")
        _entero_positivo(self.capacidad_ciclo, "capacidad_ciclo")
        _entero_positivo(self.costo_api_mm_por_unidad, "costo_api_mm_por_unidad")
        if (not isinstance(self.reserva_personal, int)
                or isinstance(self.reserva_personal, bool)
                or not 0 <= self.reserva_personal < self.capacidad_ciclo):
            raise ErrorCapacidad(
                f"reserva_personal fuera de [0, capacidad): {self.reserva_personal!r}")

    @property
    def capacidad_fabrica(self) -> int:
        return self.capacidad_ciclo - self.reserva_personal

    @property
    def costo_fabrica_mm(self) -> int:
        return self.costo_mensual_mm * self.capacidad_fabrica // self.capacidad_ciclo

    @property
    def precio_base_mm(self) -> int:
        return max(1, self.costo_fabrica_mm // self.capacidad_fabrica)

    @property
    def tope_mm(self) -> int:
        return self.costo_api_mm_por_unidad * 9 // 10


def semanas_operativas(asientos: list[Asiento]) -> list[str]:
    return sorted({a.semana for a in asientos
                   if a.tipo is TipoAsiento.EMISION_PT})


def posicion_ciclo(semana: str, semanas_ops: list[str]) -> tuple[int, int]:
    """(indice de ciclo, fraccion transcurrida en %) de una semana operativa."""
    try:
        i = semanas_ops.index(semana)
    except ValueError:
        raise ErrorCapacidad(f"semana no operativa: {semana}") from None
    return i // SEMANAS_POR_CICLO, (i % SEMANAS_POR_CICLO + 1) * 100 // SEMANAS_POR_CICLO


def semanas_del_ciclo(ciclo: int, semanas_ops: list[str]) -> list[str]:
    return semanas_ops[ciclo * SEMANAS_POR_CICLO:(ciclo + 1) * SEMANAS_POR_CICLO]


def _compras(asientos: list[Asiento], nombre: str, semanas: list[str]):
    for a in asientos:
        if (a.tipo is TipoAsiento.TRANSFERENCIA and a.destino == DIRECCION
                and a.detalle.get("suscripcion") == nombre
                and a.semana in semanas):
            yield a


def _es_consumo_cristal_fabrica(a: Asiento, nombre: str) -> bool:
    return (a.tipo is TipoAsiento.CONSUMO_CRISTAL
            and a.detalle.get("suscripcion") == nombre
            and a.detalle.get("zona") == ZONA_CRISTAL_FABRICA)


def consumo_fabrica(asientos: list[Asiento], nombre: str,
                    semanas: list[str]) -> int:
    """Unidades de capacidad de fabrica consumidas en esas SEMANAS.

    Dos formas del MISMO hecho, y las dos cuentan. La vieja compraba la
    unidad con una transferencia a direccion (`mercado.comprar_capacidad`);
    la de hoy la descuenta del pool de cristal
    (`mercado.consumir_capacidad`), porque la suscripcion es costo hundido y
    consumirla no mueve una moneda. El libro es append-only: las compras ya
    escritas siguen siendo consumo del ciclo en que se hicieron, asi que
    leer solo la forma nueva le borraria el piso al guardia de cuota en todo
    ciclo anterior al cambio. Un hecho escribe UNA de las dos formas —el
    cristal reemplaza a la transferencia, no la acompaña— asi que sumarlas
    no cuenta dos veces.

    ESTE PLIEGUE NO ES EL DE LA CUOTA. Contesta "que paso en estas semanas"
    y sirve para eso: auditar una semana, comparar dos. Quien pregunta por
    la cuota de un ciclo —el techo que frena y el piso que pinta— tiene que
    usar `consumo_fabrica_ciclo`: una semana se vuelve operativa recien
    cuando Pedro aprieta el boton, y el consumo de una semana que nunca se
    abrio no cae en las semanas de NINGUN ciclo, asi que aca es invisible
    para siempre. Ver el docstring de `consumo_fabrica_ciclo`.
    """
    return (sum(a.detalle["unidades"]
                for a in _compras(asientos, nombre, semanas))
            + sum(a.monto for a in asientos
                  if _es_consumo_cristal_fabrica(a, nombre)
                  and a.semana in semanas))


def consumo_fabrica_ciclo(asientos: list[Asiento], nombre: str, ciclo: int,
                          semanas: list[str]) -> int:
    """Unidades de la cuota del CICLO que la fabrica ya uso.

    El pliegue de la cuota, y el unico que puede serlo. Las dos formas se
    cuentan con la ventana que cada una admite:

    - La compra vieja no lleva ciclo estampado, pero `comprar_capacidad`
      exigia semana operativa (`_ciclo`), asi que siempre cae adentro de
      `semanas` y plegarla por semana es exacto.
    - El consumo de cristal se cuenta por el CICLO ESTAMPADO en el asiento,
      que es el del pool del que salieron las unidades (`cristal.consumir`
      lo resuelve al escribir). Plegarlo por semana lo perdia: consumir
      dejo de exigir semana operativa —el modelo ya contesto y el hecho no
      espera al boton de abrir—, asi que el consumo del lunes sin abrir, o
      el de una semana que Pedro se saltea entera, no entra en las semanas
      de ningun ciclo y desaparece de las dos lecturas que lo necesitan: el
      techo que frena (`mercado.consumir_capacidad`) y el piso que pinta
      (`cierre._rojo_de_ciclo`). Un techo ciego no es un techo, y un ciclo
      que gasto el 87% de la cuota se informaba como ciclo sin uso.

    Cuenta lo mismo que `cristal.consumo_del_ciclo` para la zona fabrica —a
    proposito: el pool, el guardia y el color tienen que contar el mismo
    numero o el ciclo cierra en cero declarando un consumo que su cuota no
    podia respaldar—. Lo que agrega es la forma vieja, que el cristal no
    conoce.

    DE DONDE SALE `ciclo`, que son dos relojes y conviene decirlo. Quien
    esta por ESCRIBIR una unidad lo pide con `cristal.ciclo_abierto` (el
    pool del que va a salir); quien LEE un ciclo del calendario operativo
    —el cierre, el jefe, la pantalla— lo pide con `ciclo_de_hoy` o
    `posicion_ciclo`. Coinciden porque `operacion` los ata: emite la cuota
    en la primera semana operativa del ciclo y barre los pools en la
    ultima. Si la emision de un ciclo falla (queda dicho en stderr y el
    pool viejo sin barrer), el reloj del cristal se queda atras y el que
    manda es el, porque es el que dice de donde salen las unidades.
    """
    return (sum(a.detalle["unidades"]
                for a in _compras(asientos, nombre, semanas))
            + sum(a.monto for a in asientos
                  if _es_consumo_cristal_fabrica(a, nombre)
                  and a.detalle.get("ciclo") == ciclo))


def consumo_personal(asientos: list[Asiento], nombre: str,
                     semanas: list[str]) -> int:
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.APUNTE
               and a.detalle.get("nota") == "consumo_personal_capacidad"
               and a.detalle.get("suscripcion") == nombre
               and a.semana in semanas)


def precio_unidad_mm(sus: Suscripcion, consumido: int, fraccion_pct: int) -> int:
    """Precio por escasez (spec 4.2): base x factor, tope en 0,9 x API."""
    r_pct = consumido * 100 * 100 // (sus.capacidad_fabrica * fraccion_pct)
    return min(sus.precio_base_mm * max(100, r_pct) // 100, sus.tope_mm)


def recaudacion(asientos: list[Asiento], nombre: str,
                semanas: list[str]) -> int:
    """Milimonedas que la venta de capacidad le devolvio a direccion.

    Mide PLATA, no uso, y por eso no cambio con el cristal: un consumo de
    capacidad ya no le transfiere nada a direccion. Bajo costo hundido este
    numero deja de crecer por definicion —no hay nada que recuperar— y por
    eso `cierre` ya no lo usa para pintar el ciclo (ver
    `cierre._rojo_de_ciclo`). Sigue siendo cierto y sigue informando: es lo
    que las compras VIEJAS del libro recaudaron.
    """
    return sum(a.monto for a in _compras(asientos, nombre, semanas))


def ciclo_de_hoy(semanas_ops: list[str], semana: str) -> int:
    """El INDICE del ciclo en el que cae `semana`, este operativa o no.

    La mitad que faltaba de `semanas_del_ciclo_de_hoy`: la misma aritmetica
    (la semana de hoy insertada en su lugar), pero devolviendo el numero de
    ciclo en vez de la lista de semanas. Hace falta desde que el consumo de
    capacidad se pliega por el ciclo ESTAMPADO y no por la semana
    (`consumo_fabrica_ciclo`): quien quiere el consumido del ciclo en curso
    necesita nombrarlo, y calcularlo por su cuenta seria una segunda
    aritmetica de "en que ciclo estoy".
    """
    if semana in semanas_ops:
        return posicion_ciclo(semana, semanas_ops)[0]
    return posicion_ciclo(semana, sorted(set(semanas_ops) | {semana}))[0]


def semanas_del_ciclo_de_hoy(semanas_ops: list[str], semana: str) -> list[str]:
    """Las semanas operativas del ciclo en el que cae `semana`, este esa
    semana ya emitida o no. Nunca levanta.

    `posicion_ciclo` solo sabe de semanas OPERATIVAS -- las que ya
    emitieron su PT -- y una semana se vuelve operativa recien cuando
    alguien aprieta `POST /api/economia/semana/abrir`, que es un boton
    manual. O sea que TODA semana empieza afuera de `semanas_ops` y sigue
    afuera hasta que Pedro lo toca: no es una ventana rara, es el estado
    por defecto de cada lunes.

    Preguntar "en que ciclo estoy" con `if semana in ops` contesta "en
    ninguno" durante esa ventana, y de ahi todo acumulado del ciclo da
    cero -- un techo de ciclo que se resetea solo los lunes no es un
    techo. Aca se contesta con la lista que va a existir cuando la semana
    se abra: la de hoy insertada en su lugar, y despues filtrada a las
    que existen de verdad. Es la MISMA aritmetica que `posicion_ciclo` va
    a dar despues del boton.

    Vive ACA y no en server.py porque la pregunta no es de la frontera
    http: la hacen los dos lados. `server` la usa para el consumido de las
    suscripciones que Pedro ve y para el guardia de POST .../capacidad, y
    `plantel.situacion` para el gasto de API del jefe, que corre
    desatendido y no puede reventar por una semana sin abrir. Dos
    respuestas distintas a "en que ciclo estoy" serian dos techos.

    Y NO la usa `bus.financiar`: el techo de pre-seed acumulado dejo de
    medirse sobre el ciclo de facturacion y se mide sobre una ventana
    DESLIZANTE propia (`bus.ventana_preseed`), que es otra pregunta con
    otra respuesta. Nombrarlo aca mandaba a quien persigue "quien contesta
    en que ciclo estoy" justo al lugar donde vive la OTRA ventana.
    """
    ciclo = ciclo_de_hoy(semanas_ops, semana)
    if semana in semanas_ops:
        return semanas_del_ciclo(ciclo, semanas_ops)
    futuras = sorted(set(semanas_ops) | {semana})
    reales = set(semanas_ops)
    return [x for x in semanas_del_ciclo(ciclo, futuras) if x in reales]
