"""
calipso/economia/mercado.py — La unica puerta de gasto de los departamentos.

El Kernel garantiza que la plata no se invente; el Mercado garantiza que
las POLITICAS se cumplan: congelados no compran ni reciben, la zona
personal no toca capacidad ni API de la fabrica (invariante 12), el techo
de API exige firma (compuerta c) y la cuota de suscripcion es finita.
"""
from __future__ import annotations

from . import capacidad as cap
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
    def comprar_capacidad(self, ts: str, semana: str, pagador: str,
                          sus_nombre: str, unidades: int,
                          ref: str | None = None,
                          dueno: str | None = None) -> Asiento:
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
