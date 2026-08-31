"""
calipso/economia/mercado.py — La unica puerta de gasto de los departamentos.

El Kernel garantiza que la plata no se invente; el Mercado garantiza que
las POLITICAS se cumplan: congelados no compran ni reciben, la zona
personal no toca capacidad ni API de la fabrica (invariante 12), el techo
de API exige firma (compuerta c) y la cuota de suscripcion es finita.

Esas politicas valen igual cuando el gasto no es de plata: la capacidad de
suscripcion se consume en CRISTALES (`consumir_capacidad`) y sigue
entrando por esta misma puerta, porque las reglas de zona, de congelado y
de dueno de un trabajo no son del Kernel ni de la divisa.
"""
from __future__ import annotations

from . import capacidad as cap
from . import cristal
from . import departamentos as deps
from .kernel import Kernel
from .tipos import Asiento, DIRECCION


class ErrorMercado(Exception):
    pass


def _entero_positivo(valor: int, nombre: str) -> None:
    if not isinstance(valor, int) or isinstance(valor, bool) or valor <= 0:
        raise ErrorMercado(f"{nombre} debe ser entero positivo: {valor!r}")


def gasto_api_ciclo(asientos, dep_cuenta: str, semanas: list[str]) -> int:
    """Gasto de API del departamento MAS el de sus trabajos (detalle dueno)."""
    from .tipos import TipoAsiento
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.DESTRUCCION
               and a.detalle.get("motivo") == "api" and a.semana in semanas
               and (a.origen == dep_cuenta
                    or a.detalle.get("dueno") == dep_cuenta))


class Mercado:
    def __init__(self, kernel: Kernel, registro: deps.Registro,
                 suscripciones: dict[str, cap.Suscripcion]):
        self.k = kernel
        self.registro = registro
        self.suscripciones = dict(suscripciones)

    # -- helpers -----------------------------------------------------------
    def dep_por_cuenta(self, cuenta: str) -> deps.Departamento:
        for d in self.registro.todos():
            if d.cuenta == cuenta:
                return d
        raise ErrorMercado(f"cuenta sin departamento registrado: {cuenta}")

    def _sus(self, nombre: str) -> cap.Suscripcion:
        try:
            return self.suscripciones[nombre]
        except KeyError:
            raise ErrorMercado(f"suscripcion desconocida: {nombre}") from None

    def _exigir_activo(self, cuenta: str) -> None:
        if deps.es_congelado(self.k.libro.asientos(), cuenta):
            raise ErrorMercado(f"departamento congelado: {cuenta}")

    def _ciclo(self, semana: str) -> tuple[list[str], int]:
        asientos = self.k.libro.asientos()
        ops = cap.semanas_operativas(asientos)
        try:
            ciclo, fraccion = cap.posicion_ciclo(semana, ops)
        except cap.ErrorCapacidad as exc:
            # contrato del modulo: solo ErrorMercado sale de esta puerta
            raise ErrorMercado(str(exc)) from exc
        return cap.semanas_del_ciclo(ciclo, ops), fraccion

    def _politica(self, pagador: str, dueno: str | None) -> deps.Departamento:
        """Resuelve el departamento contra el que se evaluan las politicas.

        Un trabajo gasta con dueno explicito (el llamador lo resuelve via
        bus); las reglas de zona, congelado y techo son del dueno.
        """
        if pagador.startswith("trabajo:"):
            if not dueno:
                raise ErrorMercado(
                    f"un trabajo gasta con dueno explicito: {pagador}")
            dep = self.dep_por_cuenta(dueno)
        else:
            dep = self.dep_por_cuenta(pagador)
        if dep.zona != deps.ZONA_FABRICA:
            raise ErrorMercado(
                "la zona personal no compra capacidad ni API de la fabrica "
                "(invariante 12)")
        self._exigir_activo(dep.cuenta)
        return dep

    # -- operaciones -------------------------------------------------------
    def consumir_capacidad(self, ts: str, semana: str, pagador: str,
                           sus_nombre: str, unidades: int,
                           ref: str | None = None,
                           dueno: str | None = None) -> Asiento:
        """Descuenta del pool de cristal la capacidad que la fabrica ya uso.

        El gemelo de `comprar_capacidad` bajo la decision de Pedro del
        2026-08-31: la suscripcion es COSTO HUNDIDO de la fabrica, no un
        servicio que direccion revende. Consumir una unidad ya no mueve una
        moneda contra `direccion`; descuenta de una cuota que Pedro ya pago.
        El cristal REEMPLAZA a la transferencia, nunca la acompaña: dos
        asientos por el mismo hecho cobrarian dos veces lo que se pago una
        vez, que es justo lo que la divisa existe para evitar.

        Pasa por `_politica` y no llama derecho a `cristal.consumir` porque
        ahi viven las tres reglas que no son del cristal: un congelado no
        gasta, la zona personal no toca capacidad de fabrica (invariante
        12) y un trabajo gasta con dueno explicito. Saltearlas seria mover
        la puerta de gasto, no cambiar la divisa.

        La cuota SIGUE siendo finita, y este es el unico lugar donde puede
        serlo: `cristal.consumir` no rechaza nunca —por diseño, porque mide
        un hecho consumado— asi que sin este guardia la fabrica consumiria
        sin tope y la unica señal seria el descubierto del pool, que hoy no
        lee nadie.

        EL GUARDIA MIDE POR CICLO ESTAMPADO, no por semana, y ahi esta la
        diferencia con `comprar_capacidad`. Una compra exigia semana
        operativa: nunca se escribia una unidad afuera de la ventana que el
        guardia miraba. Un consumo no puede exigirla —el modelo ya contesto
        y el hecho no espera al boton de abrir—, y toda semana empieza
        afuera de las operativas: plegando por semana, el guardia leia cero
        justo en la ventana que este cambio vino a habilitar y la fabrica
        consumia sin tope todo lunes sin abrir (y toda semana que Pedro se
        saltee entera). Se mide con `cap.consumo_fabrica_ciclo` sobre el
        ciclo que `cristal.consumir` le va a estampar a ESTA unidad
        (`cristal.ciclo_abierto`): el guardia cuenta exactamente lo que
        comparte pool con lo que esta por escribir, que es la unica ventana
        que no puede quedar ciega.
        """
        dep = self._politica(pagador, dueno)
        _entero_positivo(unidades, "unidades")
        sus = self._sus(sus_nombre)
        asientos = self.k.libro.asientos()
        # `semanas` es solo para las compras VIEJAS, que no llevan ciclo
        # estampado; el consumo de cristal lo cuenta el ciclo. Y sale de
        # `semanas_del_ciclo_de_hoy` y no de `_ciclo` porque `_ciclo`
        # levanta si la semana no es operativa, que es el estado por
        # defecto de cada lunes.
        semanas = cap.semanas_del_ciclo_de_hoy(
            cap.semanas_operativas(asientos), semana)
        ciclo = cristal.ciclo_abierto(asientos, sus_nombre)
        consumido = cap.consumo_fabrica_ciclo(asientos, sus_nombre, ciclo,
                                              semanas)
        if consumido + unidades > sus.capacidad_fabrica:
            raise ErrorMercado(
                f"cuota agotada: {consumido}+{unidades} > {sus.capacidad_fabrica}")
        if pagador.startswith("trabajo:"):
            # FIX I4 (ver comprar_capacidad): el ref de un trabajo se fuerza
            # a su propia cuenta. `eficiencia.costos_de_trabajo` filtra por
            # ese ref, asi que sin esto el consumo se escribe pero no se
            # atribuye a nada.
            ref = pagador
        # el departamento va como `titular`, NUNCA como `departamento`: ver
        # el docstring de `cristal.consumir` (con esa clave, consumir
        # cristales congelaria departamentos en el cierre semanal).
        # `_entero_positivo` ya descarto el unico caso en que `consumir`
        # devuelve None (unidades <= 0), asi que aca siempre hay asiento.
        return cristal.consumir_fabrica(self.k, ts, semana, sus, unidades,
                                        titular=dep.cuenta, ref=ref)

    def comprar_capacidad(self, ts: str, semana: str, pagador: str,
                          sus_nombre: str, unidades: int,
                          ref: str | None = None,
                          dueno: str | None = None) -> Asiento:
        """Compra capacidad EN MONEDAS, contra direccion.

        Sin llamadores de produccion desde que la suscripcion es costo
        hundido: el pagador entra por `consumir_capacidad`. Se conserva
        porque el libro es append-only y este es el asiento que explica las
        compras ya escritas (y el precio por escasez que las fecho); no es
        el camino para cobrar capacidad nueva.
        """
        dep = self._politica(pagador, dueno)
        _entero_positivo(unidades, "unidades")
        sus = self._sus(sus_nombre)
        semanas, fraccion = self._ciclo(semana)
        consumido = cap.consumo_fabrica(self.k.libro.asientos(),
                                        sus_nombre, semanas)
        if consumido + unidades > sus.capacidad_fabrica:
            raise ErrorMercado(
                f"cuota agotada: {consumido}+{unidades} > {sus.capacidad_fabrica}")
        # FIX I5: precio marginal por unidad, no precio unico al lote — cada
        # unidad paga el factor de escasez que le toca segun el consumo
        # acumulado justo antes de ella.
        precio = sum(cap.precio_unidad_mm(sus, consumido + u, fraccion)
                    for u in range(unidades))
        detalle = {"suscripcion": sus_nombre, "unidades": unidades}
        if pagador.startswith("trabajo:"):
            detalle["dueno"] = dep.cuenta
            # FIX I4: el ref de un trabajo se fuerza siempre a su propia
            # cuenta; la atribucion de eficiencia no se evade omitiendolo.
            ref = pagador
        return self.k.transferir(
            ts, semana, pagador, DIRECCION, precio, motivo="capacidad",
            ref=ref, detalle_extra=detalle)

    def usar_reserva_personal(self, ts: str, semana: str, sus_nombre: str,
                              unidades: int, departamento_cuenta: str) -> Asiento:
        # FIX I3 (invariante 12): la reserva personal es exclusiva de la
        # zona personal; la fabrica no puede consumirla.
        dep = self.dep_por_cuenta(departamento_cuenta)
        if dep.zona != deps.ZONA_PERSONAL:
            raise ErrorMercado(
                "la reserva personal es de la zona personal (invariante 12)")
        _entero_positivo(unidades, "unidades")
        sus = self._sus(sus_nombre)
        semanas, _ = self._ciclo(semana)
        usado = cap.consumo_personal(self.k.libro.asientos(),
                                     sus_nombre, semanas)
        if usado + unidades > sus.reserva_personal:
            raise ErrorMercado(
                f"reserva personal agotada: {usado}+{unidades} > {sus.reserva_personal}")
        return self.k.apuntar(ts, semana, unidades,
                              {"nota": "consumo_personal_capacidad",
                               "suscripcion": sus_nombre,
                               "departamento": departamento_cuenta})

    def gastar_api(self, ts: str, semana: str, pagador: str, mm: int,
                   ref: str | None = None, firma: dict | None = None,
                   dueno: str | None = None) -> Asiento:
        dep = self._politica(pagador, dueno)
        _entero_positivo(mm, "mm")
        semanas, _ = self._ciclo(semana)
        gastado = gasto_api_ciclo(self.k.libro.asientos(), dep.cuenta, semanas)
        if gastado + mm > dep.techo_api_ciclo_mm and not firma:
            raise ErrorMercado(
                f"techo de API del ciclo superado sin firma: "
                f"{gastado}+{mm} > {dep.techo_api_ciclo_mm} (compuerta c)")
        detalle = {}
        if pagador.startswith("trabajo:"):
            detalle["dueno"] = dep.cuenta
            # FIX I4: ver comprar_capacidad — ref forzado a la cuenta del
            # trabajo.
            ref = pagador
        if firma:
            detalle["firma"] = firma
        return self.k.destruir(ts, semana, pagador, mm, motivo="api", ref=ref,
                               detalle_extra=detalle or None)

    def vender_servicio(self, ts: str, semana: str, origen: str,
                        destino: str, mm: int,
                        ref: str | None = None) -> Asiento:
        # FIX C1 (critico): ambos lados deben ser departamentos registrados
        # (cualquier zona) — nada de tesoro ni cuentas fantasma.
        self.dep_por_cuenta(origen)
        self.dep_por_cuenta(destino)
        self._exigir_activo(origen)
        if deps.es_congelado(self.k.libro.asientos(), destino):
            raise ErrorMercado(
                f"un congelado no recibe transferencias internas: {destino}")
        return self.k.transferir(ts, semana, origen, destino, mm,
                                 motivo="servicio", ref=ref)
