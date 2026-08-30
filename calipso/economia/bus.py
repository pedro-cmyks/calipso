"""
calipso/economia/bus.py — El bus de propuestas.

Una propuesta declara que quiere hacer, cuanto pide y su criterio de
muerte ANTES de empezar (spec 7). Los eventos van a un JSONL propio
(no son asientos monetarios); la plata del trabajo vive en la cuenta
trabajo:<id> del libro, movida siempre via Kernel.

Dos tipos de propuesta comparten el mismo bus. Una de `tipo="trabajo"`
(el default) se financia desde la billetera de otro departamento de
fabrica y la plata cae en la cuenta trabajo:<id> — produce un trabajo,
con su gasto y su criterio de muerte. Una de `tipo="preseed"` es la ronda
pre-seed: se financia contra el TESORO, no contra ningun departamento, y
la plata cae en la cuenta DEL DEPARTAMENTO dueno, no en trabajo:<id> —
produce capital, no un trabajo, asi que no tiene gasto que medir ni
liquidacion que hacer: al pagarse pasa a `cerrada` y sale de `activas()`,
que es la lista de trabajos EN CURSO.
"""
from __future__ import annotations

import json
import pathlib

from . import capacidad as cap
from . import departamentos as deps
from .mercado import ErrorMercado, Mercado
from .tipos import Asiento, TESORO, TipoAsiento

_CLAVES_CRITERIO = {"gasto_max_mm", "semanas_max"}
_TIPOS_PROPUESTA = {"trabajo", "preseed"}


class ErrorBus(Exception):
    pass


def cuenta_trabajo(id: str) -> str:
    return f"trabajo:{id}"


class Bus:
    def __init__(self, ruta: pathlib.Path):
        self.ruta = pathlib.Path(ruta)
        self._eventos: list[dict] = []
        if self.ruta.exists():
            for linea in self.ruta.read_text(encoding="utf-8").splitlines():
                if linea.strip():
                    self._eventos.append(json.loads(linea))

    def _apilar(self, evento: dict) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False,
                               separators=(",", ":")) + "\n")
            f.flush()
        self._eventos.append(evento)

    def alta(self, ts: str, semana: str, id: str, departamento_cuenta: str,
             titulo: str, presupuesto_mm: int, retorno_mm: int,
             criterio: dict, tipo: str = "trabajo") -> None:
        if not id or ":" in id:
            raise ErrorBus(f"id invalido: {id!r}")
        if any(e["id"] == id for e in self._eventos):
            raise ErrorBus(f"propuesta repetida: {id}")
        if tipo not in _TIPOS_PROPUESTA:
            raise ErrorBus(f"tipo de propuesta invalido: {tipo!r}")
        if not criterio or not set(criterio) <= _CLAVES_CRITERIO:
            raise ErrorBus(
                f"criterio de muerte invalido (claves {_CLAVES_CRITERIO}): "
                f"{criterio!r}")
        for clave, valor in criterio.items():
            if not (isinstance(valor, int) and not isinstance(valor, bool)
                    and valor > 0):
                raise ErrorBus(f"criterio con valor invalido: {clave}={valor!r}")
        if not (isinstance(presupuesto_mm, int) and not isinstance(presupuesto_mm, bool)
                and presupuesto_mm > 0):
            raise ErrorBus(
                f"presupuesto_mm debe ser entero positivo: {presupuesto_mm!r}")
        if not (isinstance(retorno_mm, int) and not isinstance(retorno_mm, bool)
                and retorno_mm > 0):
            raise ErrorBus(
                f"retorno_mm debe ser entero positivo: {retorno_mm!r}")
        self._apilar({"ts": ts, "semana": semana, "evento": "alta", "id": id,
                      "departamento": departamento_cuenta, "titulo": titulo,
                      "presupuesto_mm": presupuesto_mm,
                      "retorno_mm": retorno_mm, "criterio": criterio,
                      "tipo": tipo})

    def _eventos_de(self, id: str) -> list[dict]:
        eventos = [e for e in self._eventos if e["id"] == id]
        if not eventos:
            raise ErrorBus(f"propuesta inexistente: {id}")
        return eventos

    def estado(self, id: str) -> str:
        return self._eventos_de(id)[-1]["evento"]

    def datos(self, id: str) -> dict:
        eventos = self._eventos_de(id)
        d = dict(eventos[0])
        for e in eventos[1:]:
            if e["evento"] == "financiada" and "semana_financiada" not in d:
                d["semana_financiada"] = e["semana"]
            # cuando Pedro dijo que no. `descartar` es terminal, asi que
            # hay a lo sumo una: la lee `situacion` para que el "no" pese
            # en la semana en que se dijo y no para siempre.
            elif e["evento"] == "descartada":
                d["semana_descartada"] = e["semana"]
        return d

    def ids(self) -> list[str]:
        return sorted({e["id"] for e in self._eventos})

    def activas(self) -> list[str]:
        return [i for i in self.ids() if self.estado(i) == "financiada"]

    def marcar(self, ts: str, semana: str, id: str, evento: str) -> None:
        estado = self.estado(id)  # tambien exige que exista
        if evento not in _TRANSICIONES.get(estado, frozenset()):
            raise ErrorBus(f"transicion invalida: {estado} -> {evento}")
        self._apilar({"ts": ts, "semana": semana, "evento": evento, "id": id})


_TRANSICIONES = {
    "alta": frozenset({"financiada", "descartada"}),
    # `cerrada` es el final de un PRE-SEED: la plata ya cayo en la cuenta
    # del departamento y no hay nada mas que decidir sobre ese pedido. Sin
    # este estado, `financiada` era terminal para un pre-seed pero seguia
    # contando como propuesta viva: quedaba para siempre en la mesa (que
    # filtra por "alta" o "financiada" y dice de si misma "es para decidir,
    # no un historial") y en `activas()`, que es de donde `mapa/ciudad` y
    # `prompt_compiler` sacan los trabajos en curso -- una unidad fantasma
    # en el mapa y un proyecto fantasma en el contexto del chat, los dos
    # con gasto cero eterno porque la cuenta `trabajo:<id>` no existe.
    "financiada": frozenset({"muerta", "cerrada"}),
    "muerta": frozenset({"liquidada"}),
}


def financiar(mercado: Mercado, bus: Bus, ts: str, semana: str, id: str,
              financiador_cuenta: str, mm: int) -> Asiento:
    if bus.estado(id) not in ("alta", "financiada"):
        raise ErrorBus(f"propuesta no financiable en estado {bus.estado(id)}")
    datos = bus.datos(id)
    dueno = datos["departamento"]
    tipo = datos.get("tipo", "trabajo")
    asientos = mercado.k.libro.asientos()
    if semana not in cap.semanas_operativas(asientos):
        raise ErrorBus(f"semana no operativa: {semana}")
    if deps.es_congelado(asientos, dueno):
        raise ErrorBus(
            f"financiar la propuesta de un congelado es rescatarlo: {dueno}")
    if tipo == "preseed":
        # Un pre-seed no es plata de otro departamento: es capital del
        # tesoro para arrancar. No hay "financiador de fabrica" que valga
        # aca -es Pedro decidiendo desde la mesa, y cae en la cuenta DEL
        # DEPARTAMENTO, no en trabajo:<id> (no produce un trabajo).
        if financiador_cuenta != TESORO:
            raise ErrorBus(
                "un pre-seed se financia contra el tesoro, no contra una "
                f"billetera de departamento: {financiador_cuenta}")
        # puerta de zona del DUENO, gemela de la que la rama de trabajo
        # tiene sobre el financiador. La rama de trabajo la exige y esta no
        # la exigia: el tesoro terminaba financiando directo una billetera
        # `personal:`, por encima de `cuenta_pedro.financiar_personal`, que
        # existe justamente para lo contrario (la zona personal se financia
        # SOLO desde la cuenta de Pedro). Y el efecto no es cosmetico:
        # `mercado.comprar_capacidad` le cobra a un departamento personal
        # contra la `reserva_personal` de la suscripcion y
        # `pagador.cargar_api` ignora las cuentas `personal:*`, asi que esa
        # plata compra capacidad reservada de Pedro y despues gasta fuera
        # del libro de la fabrica.
        try:
            dep = mercado.dep_por_cuenta(dueno)
        except ErrorMercado:
            raise ErrorBus(f"departamento sin registrar: {dueno}") from None
        if dep.zona != deps.ZONA_FABRICA:
            raise ErrorBus(
                "un pre-seed es capital de fabrica: la zona personal se "
                f"financia desde cuenta_pedro, no desde el tesoro ({dueno})")
        # el monto autorizado, releido en el momento de PAGAR y no una sola
        # vez cuando se publico. Dos cosas distintas se caian por aca:
        #
        #  - `mm` no se comparaba con NADA. Un pedido publicado por 50.000
        #    -recortado por la perilla, que es toda la gracia del recorte-
        #    se pagaba por 4.000.000 sin una queja, y esa plata no tiene
        #    camino de vuelta: un pre-seed no abre `trabajo:<id>` y
        #    `evaluar_y_liquidar_muertos` no lo liquida nunca.
        #  - bajar la perilla a cero frenaba los pedidos NUEVOS pero no los
        #    que ya estaban en la bandeja, que se seguian pagando por el
        #    monto viejo. "Me arrepenti, cerra la canilla" no cerraba.
        techo = int(dep.techo_preseed_mm or 0)
        if techo <= 0:
            raise ErrorBus(
                f"{dueno} no tiene techo de pre-seed: la perilla esta en "
                "cero y un pedido viejo no se paga con la perilla vieja")
        autorizado = min(techo, int(datos.get("presupuesto_mm", 0)))
        if mm > autorizado:
            raise ErrorBus(
                f"el pre-seed {id} pide {datos.get('presupuesto_mm', 0)} mm "
                f"con un techo de {techo} mm: {mm} mm es mas de lo "
                f"autorizado ({autorizado} mm)")
        destino = dueno
        motivo = "preseed"
        # `ref` = el id de la propuesta. Un trabajo se identifica por su
        # cuenta destino (`trabajo:<id>`); un pre-seed cae en la cuenta DEL
        # departamento, que es la misma para todos sus pre-seeds, asi que
        # sin esto no hay forma de saber que pedido pago una transferencia
        # -- y el corte de `api_eco_bus_financiar` contra el LIBRO (la
        # fuente de verdad cuando el proceso muere entre la transferencia y
        # la marca) no tendria nada que mirar.
        #
        # `ref` en una TRANSFERENCIA no es libre del todo, y la garantia no
        # es la del escrow (`balances.reservas_activas` lee el ref solo en
        # sus tres tipos): quien tambien lo lee es
        # `kernel.acreencias_pendientes`, que acumula `pagos[a.ref]` para
        # CUALQUIER transferencia con ref, sin mirar deudor ni motivo. Lo
        # que salva de que un pre-seed financiado se cuente como pago de
        # una deuda es que los dos espacios de nombres no se cruzan:
        # `bus.alta` prohibe ':' en el id de una propuesta y los dos sitios
        # que registran acreencias (`cola.py`, `direccion.py`) usan
        # `ref=f"adelanto:{...}"`. El dia que se afloje una de esas dos
        # cosas, esto colisiona.
        ref_asiento = id
    else:
        # puerta de origen (FIX C1): solo un departamento de fabrica
        # registrado puede financiar un trabajo; el tesoro y cuentas
        # fantasma quedan afuera.
        try:
            dep = mercado.dep_por_cuenta(financiador_cuenta)
        except ErrorMercado:
            raise ErrorBus(f"financiador invalido: {financiador_cuenta}") from None
        if dep.zona != deps.ZONA_FABRICA:
            raise ErrorBus("solo departamentos de fabrica financian propuestas")
        if deps.es_congelado(asientos, financiador_cuenta):
            raise ErrorBus(f"un congelado no financia: {financiador_cuenta}")
        destino = cuenta_trabajo(id)
        motivo = "financiacion"
        ref_asiento = None
    a = mercado.k.transferir(ts, semana, financiador_cuenta, destino, mm,
                             motivo=motivo, ref=ref_asiento)
    if bus.estado(id) == "alta":
        bus.marcar(ts, semana, id, "financiada")
    if tipo == "preseed":
        # y se cierra en el acto: no queda nada por decidir ni por gastar
        # contra este pedido. La marca `financiada` queda en el jsonl (es
        # append-only: `aporte_preseed` y el historial la siguen viendo);
        # lo que cambia es el estado, que deja de decir "esto sigue en
        # juego" en las superficies que lo leen -- la mesa de Pedro y
        # `activas()`.
        bus.marcar(ts, semana, id, "cerrada")
    return a


def descartar(bus: Bus, ts: str, semana: str, id: str) -> None:
    """Pedro dice que no.

    No hay plata que devolver: nada se transfiere a `trabajo:<id>` hasta que
    alguien financia, asi que descartar es solo la marca. Es terminal a
    proposito — en un log append-only, "deshacer" es un estado mas y una regla
    mas; si hace falta una red, que la pida el boton y no el modelo de
    estados. Y no se reusa `muerta` porque mezclaria "nunca arranco" con
    "arranco y fracaso", y el criterio de muerte lee `semana_financiada`, una
    clave que una propuesta en `alta` no tiene.
    """
    bus.marcar(ts, semana, id, "descartada")


def aportes(asientos: list[Asiento], id: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in asientos:
        if (a.tipo is TipoAsiento.TRANSFERENCIA
                and a.destino == cuenta_trabajo(id)
                and a.detalle.get("motivo") == "financiacion"):
            out[a.origen] = out.get(a.origen, 0) + a.monto
    return out


def aporte_preseed(asientos: list[Asiento], id: str) -> int:
    """Lo que el tesoro ya puso en ESE pedido de pre-seed.

    Gemelo de `aportes` para el otro tipo de propuesta. `aportes` mira la
    cuenta destino (`trabajo:<id>`) y para un pre-seed eso no sirve: la
    plata cae en la cuenta del departamento, compartida por todos sus
    pedidos. Se mira el `ref` del asiento, que `financiar` estampa con el
    id de la propuesta.
    """
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.TRANSFERENCIA
               and a.detalle.get("motivo") == "preseed" and a.ref == id)


def gastado(asientos: list[Asiento], id: str) -> int:
    cuenta = cuenta_trabajo(id)
    salidas = (TipoAsiento.TRANSFERENCIA, TipoAsiento.DESTRUCCION,
               TipoAsiento.EJECUCION_RESERVA)
    return sum(a.monto for a in asientos
               if a.tipo in salidas and a.origen == cuenta)


def semanas_transcurridas(semanas_ops: list[str], desde: str,
                          hasta: str) -> int:
    try:
        return semanas_ops.index(hasta) - semanas_ops.index(desde)
    except ValueError:
        raise ErrorBus(f"semana no operativa: {desde!r} o {hasta!r}") from None


def evaluar_y_liquidar_muertos(mercado: Mercado, bus: Bus, ts: str,
                               semana: str) -> list[str]:
    asientos = mercado.k.libro.asientos()
    ops = cap.semanas_operativas(asientos)
    muertos: list[str] = []
    for id in bus.activas():
        datos = bus.datos(id)
        if datos.get("tipo") == "preseed":
            # un pre-seed no abre trabajo:<id>: la plata ya esta en la
            # cuenta del departamento. No hay gasto que medir contra un
            # criterio de muerte ni liquidacion proporcional que hacer.
            #
            # Desde que `financiar` lo cierra en el acto, un pre-seed no
            # llega aca por `activas()` -- queda en `cerrada`, no en
            # `financiada`. Esto sigue por los buses escritos ANTES de ese
            # cambio, que si pueden tener un pre-seed en `financiada`: sin
            # el guard, el primer cierre que los alcance les buscaria un
            # gasto que no existe.
            continue
        criterio = datos["criterio"]
        gasto = gastado(asientos, id)
        muere = ("gasto_max_mm" in criterio
                 and gasto > criterio["gasto_max_mm"])
        if not muere and "semanas_max" in criterio:
            muere = semanas_transcurridas(
                ops, datos["semana_financiada"], semana) > criterio["semanas_max"]
        if not muere:
            continue
        # FIX I1: primero las devoluciones, despues las marcas. Un crash a
        # mitad de las transferencias deja la propuesta en "financiada"; la
        # proxima evaluacion vuelve a detectar la muerte y reintenta desde
        # el saldo remanente (el guard "parte > 0" evita duplicar lo ya
        # devuelto), y solo entonces las marcas aterrizan. Idempotente por
        # construccion.
        cuenta = cuenta_trabajo(id)
        asientos = mercado.k.libro.asientos()  # frescos: incluyen el gasto del loop
        aportado = aportes(asientos, id)
        saldo = mercado.k.saldo(cuenta)
        ya_devuelto = {
            fin: sum(a.monto for a in asientos
                     if a.tipo is TipoAsiento.TRANSFERENCIA
                     and a.origen == cuenta and a.destino == fin
                     and a.detalle.get("motivo") == "liquidacion_trabajo")
            for fin in aportado}
        saldo_original = saldo + sum(ya_devuelto.values())
        total = sum(aportado.values())
        financiadores = sorted(aportado)
        # partes teoricas sobre el saldo ORIGINAL (suma exacta: el ultimo cierra)
        partes = {}
        repartido = 0
        for i, fin in enumerate(financiadores):
            if i < len(financiadores) - 1:
                partes[fin] = saldo_original * aportado[fin] // total
            else:
                partes[fin] = saldo_original - repartido
            repartido += partes[fin]
        for fin in financiadores:
            pendiente = partes[fin] - ya_devuelto.get(fin, 0)
            if pendiente > 0:
                mercado.k.transferir(ts, semana, cuenta, fin, pendiente,
                                     motivo="liquidacion_trabajo")
        bus.marcar(ts, semana, id, "muerta")
        bus.marcar(ts, semana, id, "liquidada")
        muertos.append(id)
    return muertos
