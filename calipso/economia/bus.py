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

# Cuantas semanas operativas mira hacia atras el techo acumulado de
# pre-seed (`Departamento.techo_preseed_ciclo_mm`). Vive ACA y no en
# `capacidad` a proposito: coincide en valor con `SEMANAS_POR_CICLO` pero
# no es el mismo numero. Aquel es el periodo de FACTURACION de las
# suscripciones -- lo usan el precio por escasez, la cuota del cristal y
# el cierre mensual, y ahi el reset en bloque es correcto porque una
# suscripcion factura en bloque. Este acota el CAUDAL de capital hacia un
# departamento, que es otra cosa; atarlos con una sola constante haria que
# tocar el caudal moviera la facturacion. Ver `ventana_preseed`.
VENTANA_PRESEED_SEMANAS = 4


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
        # EL SEGUNDO TECHO: el del CICLO, y este ata tambien a Pedro.
        #
        # El de arriba acota cuanto vale cada ronda; sin este, tres rondas
        # de 50.000 entran 150.000 y ninguna puerta se entera. El freno del
        # jefe (`jefe._puede`) es la primera linea y ya cuenta lo pedido en
        # pie, pero no alcanza para cerrar el caso: dos pedidos publicados
        # cuando todavia habia lugar se financian los dos, uno tras otro, y
        # cruzan el techo entre los dos. Lo pedido lo frena alla; lo
        # financiado solo se puede frenar ACA, que es el unico lugar por
        # donde la plata sale de verdad.
        #
        # Aca se cuenta SOLO lo financiado, no lo pendiente: sumar los
        # otros pedidos en pie trabaria a Pedro para pagar cualquiera de
        # ellos -- dos pedidos que juntos pasan el techo se bloquearian
        # mutuamente y ninguno se podria pagar. El primero pasa, el segundo
        # choca. Descartar, como siempre, no cuenta contra nada: devolver
        # el cupo es para lo que existe.
        #
        # Y frena a PEDRO igual que al jefe, sin override: la salida es
        # subir la perilla desde la pantalla de Plata, que es una decision
        # explicita y queda escrita en departamentos.json. No pasa por el
        # motor de permisos a proposito -- un "si, siempre" ahi seria una
        # segunda fuente de verdad sobre cuanto capital entra por ventana, y
        # la perilla dejaria de ser el techo. Lo que no puede pasar es que
        # se cruce en silencio.
        #
        # La ventana es DESLIZANTE (`ventana_preseed`) y no el ciclo de
        # facturacion. Con el ciclo, el acumulado no decaia sino que se
        # reseteaba de golpe en la quinta semana operativa, y este mismo
        # freno dejaba pasar el techo entero en la ultima semana del ciclo N
        # y otra vez en la primera del N+1: 2x el techo en dos semanas de
        # calendario seguidas, que es exactamente la rafaga que el techo
        # existe para impedir.
        techo_ciclo = int(dep.techo_preseed_ciclo_mm or 0)
        if techo_ciclo <= 0:
            raise ErrorBus(
                f"{dueno} no tiene techo de pre-seed acumulado: la perilla "
                "`techo_preseed_ciclo_mm` esta en cero y cero es 'todavia "
                "no', no 'sin limite'")
        ops = cap.semanas_operativas(asientos)
        # TODAS las ventanas que contienen `semana`, no solo la que CIERRA
        # en ella. `semana` es cualquier operativa y no la ultima abierta
        # (esta puerta nunca lo exigio, a diferencia de la gemela de
        # `operacion.cerrar_semana_operativa`), y las ventanas deslizantes
        # se SOLAPAN: un asiento en una semana ya pasada entra en hasta
        # `VENTANA_PRESEED_SEMANAS` ventanas, y todas menos la ultima ya
        # fueron validadas y nadie las vuelve a mirar. Mirando solo la que
        # cierra en `semana`, el invariante -- en ninguna corrida de cuatro
        # semanas operativas entra mas que el techo -- se rompia de forma
        # permanentemente invisible: el proximo `financiar` sigue viendo su
        # propia ventana limpia y sigue informando el numero de antes.
        #
        # Con la ventana FIJA esto era inocuo (los ciclos eran bloques
        # disjuntos: cargar un ciclo viejo cargaba el unico bloque que el
        # chequeo miraba), asi que el agujero lo abrio el deslizamiento.
        #
        # Se valida aca y no exigiendo `semana == ops[-1]` porque lo que
        # hay que defender es el INVARIANTE, no la fecha: cerrar la puerta
        # de entrada lo delegaria en que ningun otro camino escriba un
        # pre-seed con fecha propia.
        desde = ops.index(semana)
        for cierre in ops[desde:desde + VENTANA_PRESEED_SEMANAS]:
            semanas = ventana_preseed(ops, cierre)
            ya = preseed_en_ventana(asientos, dueno, semanas)
            if ya + mm <= techo_ciclo:
                continue
            # y el alivio con nombre y numero, que la ventana fija no podia
            # dar: ahi el cupo volvia entero y en silencio, aca se sabe cual
            # semana sale y cuanto se lleva con ella. Solo para la ventana
            # de HOY: "al abrir la proxima" no dice nada util sobre una
            # corrida que ya quedo atras.
            alivio = ""
            if cierre == semana:
                sale, libera = libera_preseed(asientos, dueno, ops, semana)
                alivio = (f" Al abrir la proxima semana operativa sale "
                          f"{sale} de la ventana y con ella se liberan "
                          f"{libera} mm." if libera else "")
            corrida = (f"las ultimas {VENTANA_PRESEED_SEMANAS} semanas "
                       f"operativas ({semanas[0]}..{semanas[-1]})"
                       if cierre == semana
                       else (f"la corrida de {len(semanas)} semanas "
                             f"operativas ({semanas[0]}..{semanas[-1]}), "
                             f"que {semana} tambien integra"))
            raise ErrorBus(
                f"techo de pre-seed superado: {dueno} ya recibio {ya} mm de "
                f"pre-seed en {corrida} y {mm} mm mas "
                f"pasan de {techo_ciclo} mm.{alivio} Para darle mas ahora, "
                "subi la perilla `techo_preseed_ciclo_mm`")
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


def preseed_en_ventana(asientos: list[Asiento], cuenta: str,
                       semanas: list[str]) -> int:
    """Todo el pre-seed que YA entro a esa cuenta en esas semanas.

    Hermano de `aporte_preseed`, que mira UN pedido; este mira UN
    departamento y un tramo de semanas, que es lo que pide el techo
    acumulado: el pedido es la unidad del techo por pedido, el
    departamento es la unidad del techo del caudal.

    Se llamaba `preseed_del_ciclo` mientras el tramo era el ciclo de
    facturacion. Ya no lo es (`ventana_preseed`) y el nombre viejo mentia
    sobre la unica cosa que importa entender de este techo: cual es la
    ventana. La funcion no cambio, cambio quien le pasa las semanas.

    Se pliega del LIBRO y no del bus a proposito. El bus dice lo que se
    pidio y lo que se marco; el libro dice lo que se pago, y es lo unico
    que no se puede desescribir. Si una marca del bus se pierde entre dos
    appends -- el hueco que `api_eco_bus_financiar` ya cubre mirando el
    libro -- el techo tiene que seguir contando esa plata.

    `motivo == "preseed"` y destino, los dos: la cuenta del departamento
    tambien recibe transferencias que no son pre-seed (un rescate, una
    venta de servicio), y un techo que las contara frenaria rondas por
    plata que no vino del tesoro.
    """
    return sum(a.monto for a in asientos
               if a.tipo is TipoAsiento.TRANSFERENCIA
               and a.detalle.get("motivo") == "preseed"
               and a.destino == cuenta and a.semana in semanas)


def ventana_preseed(semanas_ops: list[str], semana: str) -> list[str]:
    """Las semanas que cuentan hoy contra `techo_preseed_ciclo_mm`: las
    ultimas `VENTANA_PRESEED_SEMANAS` semanas OPERATIVAS hasta `semana`,
    mas `semana` misma. Nunca levanta.

    NO es el ciclo de facturacion, y por eso es una funcion aparte con su
    propia constante aunque hoy los dos numeros valgan 4. El ciclo
    (`capacidad.SEMANAS_POR_CICLO`, `semanas_del_ciclo_de_hoy`) es una
    ventana FIJA -- `ops[c*4:(c+1)*4]` -- y esta bien que lo sea: una
    suscripcion factura, emite su cuota y la resetea en bloque, de verdad,
    y de ahi cuelgan el precio por escasez, la emision del cristal y el
    cierre mensual. Esto mide otra cosa: el CAUDAL de capital hacia un
    departamento.

    Con la ventana fija el acumulado no decaia, se reseteaba de golpe al
    abrirse la quinta semana operativa: financiar el techo entero en la
    ultima semana del ciclo N y otra vez en la primera del N+1 metia 2x el
    techo en dos semanas de calendario seguidas. El techo existe justamente
    para acotar cuanto capital entra antes de que Pedro tenga que volver a
    decidir a conciencia, y una rafaga del doble en siete dias es lo que
    tiene que impedir. Deslizante, el invariante vale SIEMPRE y no solo en
    los bordes: en ninguna corrida de cuatro semanas operativas entra mas
    que el techo.

    Lo que Pedro pierde es el reset predecible ("el lunes vuelve entero") y
    lo que gana es que el cupo vuelve de a poco, a medida que una semana
    sale por atras -- y eso se puede DECIR, que un reset invisible no se
    podia: ver `libera_preseed`.

    Se cuenta por semana OPERATIVA y no por fecha, por dos razones. El
    libro indexa todo por semana (`a.semana`), asi que es la unica unidad
    que no hay que reconstruir; y una semana que la fabrica no abrio no es
    una semana en la que el departamento pudo hacer nada con ese capital.

    Y `semana` entra SIEMPRE, este operativa o no, para que la ventana sea
    total y no dependa de una guardia de otra capa. Hoy no puede haber
    pre-seed en una semana sin abrir -- `financiar` corta antes con "semana
    no operativa" -- pero esa guardia no es de este techo, y este techo ya
    se rompio dos veces (`server.py`, `situacion.py`) por preguntar "en que
    ventana estoy" con `if semana in ops`.

    Notar de que lado cae la demora, que es la parte que importa: todo
    lunes empieza afuera de las operativas porque abrir la semana es un
    boton manual, y mientras no se abre la ventana NO rueda -- las cuatro
    operativas de atras siguen todas adentro. O sea que tardar en abrir el
    lunes aprieta el techo, nunca lo afloja. Un techo que se resetea porque
    Pedro tardo en tocar un boton no es un techo; este rueda porque Pedro
    ABRIO la semana, que es un acto deliberado suyo.
    """
    previas = sorted(w for w in semanas_ops if w <= semana)
    ventana = previas[-VENTANA_PRESEED_SEMANAS:]
    return ventana if semana in ventana else ventana + [semana]


def libera_preseed(asientos: list[Asiento], cuenta: str,
                   semanas_ops: list[str],
                   semana: str) -> tuple[str | None, int]:
    """(semana que sale de la ventana cuando se abra la proxima operativa,
    cuanto pre-seed libera eso). `(None, 0)` si todavia no sale ninguna.

    Es lo que la ventana deslizante PERMITE y la fija no: decir CUANDO
    vuelve cupo y CUANTO. Con el reset en bloque el cupo aparecia solo y
    Pedro no tenia ninguna senal de que la ventana acababa de rodar; aca el
    numero se pinta al lado del techo y le pone fecha al alivio.

    La ventana rueda cuando se abre una semana operativa nueva, no cuando
    cambia el almanaque: `ventana_preseed` se arma sobre las operativas.
    Por eso la respuesta es "al abrir la proxima", que ademas es un acto de
    Pedro y no una espera pasiva.

    Sale la mas vieja de las `VENTANA_PRESEED_SEMANAS` operativas de hoy, y
    solo si ya hay tantas: con menos, abrir una semana mas alarga la
    ventana sin tirar nada, y prometer una liberacion ahi seria mentir. La
    semana de hoy sin abrir no cuenta para esto -- abrirla ELLA es lo que
    hace rodar la ventana, y lo que se va es la de atras.
    """
    previas = sorted(w for w in semanas_ops if w <= semana)
    if len(previas) < VENTANA_PRESEED_SEMANAS:
        return None, 0
    sale = previas[-VENTANA_PRESEED_SEMANAS]
    return sale, preseed_en_ventana(asientos, cuenta, [sale])


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
