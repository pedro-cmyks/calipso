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
from . import eficiencia as efi
from .mercado import ErrorMercado, Mercado
from .tipos import Asiento, TESORO, TipoAsiento

_CLAVES_CRITERIO = {"gasto_max_mm", "semanas_max"}
_TIPOS_PROPUESTA = {"trabajo", "preseed"}

# La forma de una propuesta: lo UNICO que se compara. El titulo es prosa y
# no participa de ninguna comparacion, igual que en el motor de permisos.
#
# Se listan aca y NO se importan de `calipso.plantel.ficha` a proposito: el
# bus es el libro, y el libro no puede depender de quien lo escribe. Si el
# plantel cambia su vocabulario, el bus tiene que seguir leyendo lo que ya
# esta escrito -- y que las dos listas se separen tiene que romper un test,
# no una lectura del libro.
_CLAVES_FORMA = {"sobre", "clave", "promete", "tarda"}
_PROMESAS = {"ahorrar", "acelerar", "arreglar", "medir", "construir",
             "descartar"}
_PLAZOS = {"corto", "medio", "largo", "no se"}

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
             criterio: dict, tipo: str = "trabajo",
             forma: dict | None = None) -> None:
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
        # OPCIONAL, no obligatoria para tipo="trabajo", que era lo natural:
        # `alta` tiene dos llamadores de produccion y 123 sitios de llamada
        # en los tests. Hacerla obligatoria convierte un cambio de dos
        # lineas en un barrido mecanico de 123 ediciones. Y seria
        # incoherente: si LEER tolera que no este -- una propuesta escrita
        # antes de que la forma existiera -- ESCRIBIR tambien.
        # El guarda de que el camino de produccion siempre la manda vive en
        # test_plantel_server.py, apuntado al unico lugar que importa.
        if forma is not None:
            if not isinstance(forma, dict) or set(forma) != _CLAVES_FORMA:
                raise ErrorBus(
                    f"forma invalida (claves {_CLAVES_FORMA}): {forma!r}")
            if forma["promete"] not in _PROMESAS:
                raise ErrorBus(f"promesa invalida: {forma['promete']!r}")
            if forma["tarda"] not in _PLAZOS:
                raise ErrorBus(f"plazo invalido: {forma['tarda']!r}")
            for clave in ("sobre", "clave"):
                if not (isinstance(forma[clave], str) and forma[clave].strip()):
                    raise ErrorBus(
                        f"forma con {clave} vacio: {forma[clave]!r}")
        if not (isinstance(presupuesto_mm, int) and not isinstance(presupuesto_mm, bool)
                and presupuesto_mm > 0):
            raise ErrorBus(
                f"presupuesto_mm debe ser entero positivo: {presupuesto_mm!r}")
        if not (isinstance(retorno_mm, int) and not isinstance(retorno_mm, bool)
                and retorno_mm > 0):
            raise ErrorBus(
                f"retorno_mm debe ser entero positivo: {retorno_mm!r}")
        evento = {"ts": ts, "semana": semana, "evento": "alta", "id": id,
                  "departamento": departamento_cuenta, "titulo": titulo,
                  "presupuesto_mm": presupuesto_mm,
                  "retorno_mm": retorno_mm, "criterio": criterio,
                  "tipo": tipo}
        if forma is not None:
            evento["forma"] = dict(forma)
        self._apilar(evento)

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
    # UNA sola vez, y no tres. `semanas_operativas` es un set-comprehension
    # sobre el libro entero mas un `sorted`, y `asientos` es un snapshot
    # inmutable que no cambia adentro de esta llamada: las tres respuestas
    # eran identicas por construccion. La rama de pre-seed la pedia en el
    # vencimiento y otra vez en el chequeo multi-ventana.
    ops = cap.semanas_operativas(asientos)
    if semana not in ops:
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
        # `mercado.consumir_capacidad` le cobra a un departamento personal
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
        # VENCIMIENTO. Un pedido vive la ventana en la que nacio y despues
        # no se paga mas. Es el mismo gesto que las dos puertas de abajo --
        # releer al PAGAR lo que valia al publicar-- y sin el, el resto del
        # vencimiento seria de mentira: `situacion` dejaria de reservarle
        # cupo al pedido viejo, el jefe pediria otra ronda, y Pedro podria
        # pagar las dos. Dos veces el techo, que es lo que este techo
        # existe para impedir. Aca es donde la plata sale de verdad, asi que
        # aca es donde el vencimiento tiene que ser cierto.
        # Contra la ULTIMA operativa y no contra `semana`. Esta puerta
        # acepta cualquier semana operativa a proposito (ver el chequeo
        # multi-ventana de abajo: defiende el invariante, no la fecha), y
        # eso le daba al vencimiento una llave de repuesto -- el mismo
        # pedido que hoy se rechaza por vencido se pagaba sin una queja
        # fechandolo cuatro semanas atras, porque la ventana se armaba con
        # el `semana` del llamador. `semana` dice DONDE cae el asiento;
        # cuando la fabrica ya siguio operando sin ese pedido no lo desanda
        # elegir una fecha de pago mas comoda. Los lectores siguen
        # preguntando "sigue vivo en la semana que te doy", que es lo que
        # necesitan: el que tiene que leer el reloj de hoy es el unico
        # lugar por donde la plata sale.
        if preseed_vencido(datos, ops, ops[-1]):
            raise ErrorBus(
                f"el pre-seed {id} esta vencido: se publico en "
                f"{datos.get('semana')} y esa semana ya salio de la ventana "
                f"de {VENTANA_PRESEED_SEMANAS} semanas operativas. Ya no "
                f"reserva cupo de {dueno}, asi que el jefe puede volver a "
                "pedir la ronda con los numeros de hoy")
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


def ventana_pagable(semanas_ops: list[str], semana: str) -> list[str]:
    """La ventana contra la que un pre-seed se mediria si se lo pagara en
    `semana`. Gemela de `ventana_preseed`, y contesta otra pregunta.

    Aquella contesta "cuanto capital entro en la corrida que termina en
    `semana`", que es la del TECHO y se mide donde el asiento CAE. Esta
    contesta "si se pagara en `semana`, contra que corrida se mediria", que
    es la del VENCIMIENTO. Con `semana` operativa las dos dan lo mismo; se
    separan justo en el borde que abrio la ranura impagable:

    Mientras la semana de hoy no esta abierta, `ventana_preseed` la agrega
    como QUINTA etiqueta y deja adentro las cuatro operativas de atras. Para
    el techo eso es lo correcto y esta escrito ahi: tardar en abrir el lunes
    lo APRIETA, nunca lo afloja. Para el vencimiento era una fila que no se
    podia pagar de ninguna manera: un pedido nacido en la mas vieja de esas
    cuatro seguia sin vencer, la mesa le pintaba su boton `financiar` -- y
    `financiar` exige una semana OPERATIVA, asi que el boton no podia
    funcionar; y abrirla, que es lo unico que lo habilitaria y lo que el
    aviso de la mesa le pide a Pedro con un boton al lado, corre la ventana
    a cuatro etiquetas y vence el pedido en el mismo acto. No habia ninguna
    secuencia en la que esa fila se pudiera pagar, y mostrarla es
    exactamente lo que la mesa dice de si misma que no hace.

    Aca `semana` entra como si ya estuviera ABIERTA, porque abrirla es la
    unica forma en que se la podria pagar. Asi la respuesta no se da vuelta
    con el gesto de Pedro: el pedido vence antes de que la mesa lo ofrezca,
    en vez de vencer por haber aceptado el consejo de la propia pantalla.

    El TECHO no se toca: `preseed_en_ventana` y el chequeo multi-ventana de
    `financiar` siguen midiendose con `ventana_preseed` sobre las
    operativas de verdad.
    """
    return ventana_preseed(sorted({*semanas_ops, semana}), semana)


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


def preseed_vencido(datos: dict, semanas_ops: list[str], semana: str) -> bool:
    """Si ese pedido de pre-seed ya salio de la ventana en la que nacio.

    LO QUE ARREGLA. Una propuesta de trabajo puede morir; un pedido de
    pre-seed no podia. `evaluar_y_liquidar_muertos` solo recorre
    `activas()` -- las FINANCIADAS-- asi que un pedido en `alta` no pasaba
    ni cerca, y encima su `criterio` es inerte por construccion (no abre
    `trabajo:<id>`, no hay gasto que medir: quien lo publica manda
    `{"gasto_max_mm": monto}` solo porque `alta` exige un criterio no
    vacio). Resultado: lo unico que sacaba un pedido de la bandeja era que
    Pedro lo financiara o lo descartara, y mientras tanto seguia
    reservandole cupo del techo acumulado al departamento -- para siempre.
    La inaccion de Pedro se volvia una condena.

    CUANTO VIVE, y por que exactamente eso. Vive la ventana en la que
    nacio: mientras la semana del alta siga adentro de `ventana_preseed`,
    el pedido esta en pie. Reservar cupo mientras tanto es CORRECTO --
    Pedro lo puede pagar con un toque y esa plata va a consumir el cupo de
    la ventana en la que la pague-- y el corte cae justo donde esa reserva
    deja de tener sentido: `financiar` rechaza un pedido vencido, asi que
    no hay ninguna ventana futura contra la cual pudiera pagarse. Ni un
    dia menos (seria romper la reserva, que esta verificada) ni un dia mas
    (seria la condena de antes).

    QUIEN LO DISPARA: NADIE, y eso es lo importante. Esto es una funcion
    del libro, no un evento, exactamente como `preseed_en_ventana` y
    `libera_preseed`: nadie escribe "esta semana salio de la ventana", la
    ventana se corre sola porque se RECALCULA en cada lectura. Un
    vencimiento por evento habria tenido que colgarse de
    `evaluar_y_liquidar_muertos`, que solo corre desde
    `cierre.cerrar_semana_economia` -- o sea desde la rutina "cierre", que
    nace deshabilitada A PROPOSITO (`routines.DEFAULTS`: prender ese piloto
    automatico expira PT, declara quiebras y liquida trabajos mientras
    Pedro duerme) o desde `POST /api/economia/cierre` a mano. En la maquina
    de Pedro eso no corre, asi que un vencimiento atado ahi seria
    decorativo: el bug seguiria vivo con un arreglo escrito al lado. Sin
    disparador no hay nada que encender.

    Y el reloj es el que ya rige este techo: las semanas OPERATIVAS -- un
    pedido no caduca porque paso el tiempo, caduca porque la fabrica siguio
    operando sin el. La ventana que se lee aca es `ventana_pagable` y no
    `ventana_preseed`: la del techo se mide donde el asiento cae, esta se
    mide desde la frontera y contando la semana de hoy como si ya estuviera
    abierta, porque abrirla es lo unico que la volveria pagable. Con la del
    techo el vencimiento tenia una llave de repuesto por atras (financiar
    fechando el pago en una semana vieja) y una ranura impagable por
    adelante (la fila que la mesa pinta el lunes y que abrir la semana mata
    en el mismo acto); las dos estan escritas en `ventana_pagable`.

    Y no borra nada. El bus es append-only y el evento `alta` sigue ahi con
    su semana; lo que cambia es que los lectores dejan de contarlo como
    vivo y `financiar` deja de pagarlo. Descartarlo sigue siendo legal (es
    la marca que Pedro ya conocia), solo que ya no hace falta.
    """
    if datos.get("tipo") != "preseed":
        # una propuesta de trabajo ya tiene su muerte (`criterio` +
        # `evaluar_y_liquidar_muertos`, que si la alcanza porque vive
        # financiada) y no reserva cupo de ningun techo de caudal
        return False
    nacio = datos.get("semana") or ""
    if not nacio or not semanas_ops:
        # sin semanas operativas la ventana nunca rodo: hacer vencer aca
        # seria expirar por el paso del tiempo, que es justo lo que este
        # techo se niega a hacer. Y sin semana de alta (una linea vieja del
        # bus real de Pedro) no se inventa un vencimiento: el default
        # tolerante de siempre.
        return False
    return nacio < ventana_pagable(semanas_ops, semana)[0]


def gastado(asientos: list[Asiento], id: str,
            suscripciones: dict[str, cap.Suscripcion] | None = None) -> int:
    """Lo que el trabajo lleva gastado, en milimonedas.

    Es el numerador del criterio de muerte `gasto_max_mm`, asi que lo que
    no entra aca vuelve al trabajo INMORTAL.

    Dos formas, como en todo lo que toca la capacidad de suscripcion. La
    plata sale de `trabajo:<id>` y se cuenta por su monto. La capacidad de
    suscripcion ya NO sale de esa cuenta: bajo costo hundido se descuenta
    del pool de cristal (`cristal:<sus>:fabrica`) y el trabajo viaja en el
    `ref` que `mercado.consumir_capacidad` fuerza — o sea que un trabajo
    cuyo unico costo es la suscripcion tenia gasto cero, no moria nunca y
    ademas se informaba con "gastado 0 mm" en el brief que Calipso lee
    cada turno mientras quemaba la cuota.

    La conversion es la misma que usa la eficiencia
    (`consumo_de_suscripcion`, un solo lector de la divisa para todo el
    libro): las unidades valen lo que HABRIAN costado por API. No es el
    precio por escasez que cobraba la compra vieja —ese precio ya no lo
    paga nadie— pero es la unica medida en milimonedas de una unidad de
    suscripcion, y `gasto_max_mm` esta en milimonedas.

    Sin `suscripciones` no hay conversion posible y se cuenta solo la
    plata: es el default tolerante para los llamadores de lectura que no
    las tienen a mano. Quien DECIDE con este numero —
    `evaluar_y_liquidar_muertos`— las pasa siempre.
    """
    cuenta = cuenta_trabajo(id)
    salidas = (TipoAsiento.TRANSFERENCIA, TipoAsiento.DESTRUCCION,
               TipoAsiento.EJECUCION_RESERVA)
    total = 0
    for a in asientos:
        if a.tipo in salidas and a.origen == cuenta:
            total += a.monto
        elif suscripciones and a.ref == cuenta:
            consumo = efi.consumo_de_suscripcion(a, suscripciones)
            if consumo:
                total += consumo[1]
    return total


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
            #
            # Y el vencimiento del pre-seed PEDIDO no vive aca ni podria:
            # esta funcion solo ve `activas()` y solo corre desde el cierre
            # semanal, que nace deshabilitado. Es `preseed_vencido`, que se
            # calcula del libro sin que nadie lo dispare.
            continue
        criterio = datos["criterio"]
        # con las suscripciones: el gasto de capacidad de un trabajo no
        # sale de su cuenta desde que es costo hundido, y sin esto el
        # criterio de muerte por gasto no se dispara nunca
        gasto = gastado(asientos, id, mercado.suscripciones)
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


ORIGEN_INBOX = "mesa"


def descriptor() -> dict:
    """Lo que la mesa declara de si misma para el inbox.

    Vive aca y no en el inbox a proposito (spec seccion 3): si viviera
    alla, agregar un origen nuevo obligaria a tocar el inbox.

    `vara` y `lugares` van en None porque el PvP es otro plan, y porque
    hoy la mesa no tendria con que comparar: `retorno_mm` es una copia
    literal de `presupuesto_mm` para los dos tipos de propuesta.
    """
    return {
        "origen": ORIGEN_INBOX,
        "verbos": [
            # financiar NO es un si: es un si-con-cuenta-pagadora
            {"nombre": "financiar", "etiqueta": "Financiar",
             "alcances": ["una_vez"], "parametros": ["cuenta"]},
            {"nombre": "descartar", "etiqueta": "Descartar",
             "alcances": ["una_vez"], "parametros": []},
        ],
        "reloj": "semanas_operativas",   # solo vencen los pre-seed
        "clase_por_defecto": "decision",
        "vara": None,
        "lugares": None,
    }


def _item(id_, titulo, estado, cuerpo) -> dict:
    return {"id": id_, "origen": ORIGEN_INBOX, "clase": "decision",
            "ts": "", "titulo": titulo, "cuerpo": cuerpo,
            "estado": estado, "respuesta": None}


def como_items(datos_endpoint: dict) -> list[dict]:
    """Traduce la respuesta de GET /api/economia/bus a items del inbox.

    Sin economia sembrada -- el estado de hoy -- esa respuesta es
    literalmente `{"activa": False}`: sin `propuestas` y sin `vencidas`.
    Por eso todos los accesos van con default.
    """
    items = []
    for p in datos_endpoint.get("propuestas") or []:
        estado = p.get("estado") or "alta"
        # verbos_validos depende del estado porque _TRANSICIONES especifica
        # que transiciones son validas. financiada solo puede ir a muerta o
        # cerrada (_TRANSICIONES["financiada"]), no a descartada: eso da 400
        if estado == "financiada":
            verbos_validos = ["financiar"]
        else:
            verbos_validos = ["financiar", "descartar"]
        cuerpo = {"departamento": p.get("departamento"),
                  "tipo": p.get("tipo"),
                  "presupuesto_mm": p.get("presupuesto_mm"),
                  "gastado_mm": p.get("gastado_mm"),
                  "metrica": p.get("metrica", ""),
                  "verbos_validos": verbos_validos}
        if p.get("tipo") == "preseed":
            # un pre-seed lo paga el tesoro y nada mas: bus.financiar
            # rechaza cualquier billetera de departamento
            cuerpo["cuenta_fija"] = "tesoro"
        items.append(_item(p.get("id"), p.get("titulo") or "",
                           estado, cuerpo))
    for v in datos_endpoint.get("vencidas") or []:
        # cinco campos, no diez, y financiar da 400 sobre un vencido
        items.append(_item(
            v.get("id"), v.get("titulo") or "", "vencida",
            {"departamento": v.get("departamento"),
             "semana": v.get("semana"),
             "presupuesto_mm": v.get("presupuesto_mm"),
             "verbos_validos": ["descartar"]}))
    # Las fichas que no se entendieron. Son AVISOS y no decisiones: nada
    # espera un verbo de Pedro, y contarlas para el badge lo haria mentir.
    # El molde es el aviso que emite el adaptador de permisos cuando no
    # puede leer su archivo: clase "aviso", `verbos_validos` vacio.
    for i, fila in enumerate(datos_endpoint.get("ilegibles") or []):
        veces = fila.get("veces", 1)
        repeticion = f" (x{veces})" if veces > 1 else ""
        items.append({
            "id": f"ilegible:{i}", "origen": ORIGEN_INBOX, "clase": "aviso",
            "ts": fila.get("ts", ""),
            "titulo": f"{fila.get('departamento', '?')} escribio algo que no "
                      f"entra en una ficha{repeticion}: {fila.get('crudo', '')}",
            "cuerpo": {"departamento": fila.get("departamento", ""),
                       "crudo": fila.get("crudo", ""),
                       "veces": veces, "verbos_validos": []},
            "estado": "aviso", "respuesta": None})
    return items
