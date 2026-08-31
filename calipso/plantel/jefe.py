"""
calipso/plantel/jefe.py — El bucle: mirar, decidir, actuar.

Lo unico del plantel que llama modelos y mueve plata. Todo lo caro entra
inyectado —el modelo, el contratista, el pulso, la memoria— para que el bucle
entero se pueda testear sin un solo modelo y sin tocar el libro.

`comentar` no toca el bus a proposito: el bus no tiene superficie de
comentarios. El jefe escribe su opinion en su memoria y la publica al pulso.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from . import decision as dec
from . import interruptor as it
from . import situacion as sit

TECHO_PROPUESTAS = 3   # propuestas propias sin financiar, antes de frenar


@dataclass
class Contexto:
    base: Any                     # CALIPSO_HOME
    kernel: Any
    registro: Any
    bus: Any
    cola: Any
    suscripciones: dict
    memoria: Any                  # el Scope del departamento
    pensar: Callable[[str], str]
    contratar: Callable[[dict, str, "str | None", str], Any]
    publicar: Callable[..., None] = field(
        default=lambda evento, **campos: None)


def _puede(estado, s: dict, accion: str, ref: str | None) -> tuple[bool, str]:
    """Los frenos, del mas barato de chequear al mas caro de violar."""
    if accion == "nada":
        return False, "no hay nada que hacer"

    # El jefe solo puede referirse a lo que su propia situacion le mostro.
    # Un modelo de 3b nombra ids que no existen: se lo vio contestar
    # "trabajar 1" con la lista de trabajos vivos vacia. El parser valida la
    # FORMA de la respuesta; esto valida la REFERENCIA.
    if accion == "trabajar":
        if ref not in {t["id"] for t in s["trabajos"]}:
            return False, f"no existe el trabajo {ref!r}"
    if accion == "comentar":
        conocidos = {p["id"] for p in s.get("propuestas_propias", [])}
        conocidos |= {p["id"] for p in s["propuestas_ajenas"]}
        conocidos |= {t["id"] for t in s["trabajos"]}
        if ref not in conocidos:
            return False, f"no existe la propuesta {ref!r}"
        # opinar no contrata a nadie ni cobra (el contratista lo devuelve como
        # no-op), asi que no hay gasto que frenar — y en ensayo formar criterio
        # es exactamente lo que queremos ver pasar
        return True, ""
    if not it.puede_gastar(estado):
        return False, f"modo {estado.modo}: mira y decide, no gasta"
    if accion in ("proponer", "pedir"):
        # Proponer y pedir no gastan: solo escriben en el bus (financiar es
        # lo que gasta, y eso lo hace Pedro desde la mesa, no el jefe aca).
        # El freno de saldo protege CONTRATAR sin fondos, no PEDIR fondos —
        # si viviera aca, un departamento quebrado o recien nacido no podria
        # ni pedir la ronda pre-seed que lo saca de estar quebrado.
        #
        # El techo de propuestas propias sin financiar SI sigue valiendo
        # para los dos: el modelo ve las que ya tiene en pie y propone otra
        # igual igual, asi que a 200 tics por semana el bus de Pedro se
        # llena de duplicados y deja de servir para lo unico que sirve: que
        # Pedro elija. Que despeje la bandeja primero.
        propias = len(s.get("propuestas_propias", []))
        if propias >= TECHO_PROPUESTAS:
            return False, (f"ya tiene {propias} propuestas sin financiar: "
                           f"que Pedro despeje antes de sumar otra")
        if accion == "pedir" and int(s.get("techo_preseed_mm") or 0) <= 0:
            # El monto del pre-seed sale de la perilla `techo_preseed_mm`,
            # no del modelo, y en cero significa que Pedro todavia no dijo
            # cuanto puede pedir este departamento. El freno vive ACA y no
            # en el prompt: `pedir` sigue en el menu (es Pedro quien decide
            # si hace falta, no el prompt -- ver decision.prompt), pero un
            # pedido sin techo no llega al bus, no se anota en la memoria
            # del jefe y no se reporta como que actuo. El contratista lo
            # vuelve a chequear antes de escribir: es la segunda linea, no
            # la primera.
            return False, ("sin techo de pre-seed: Pedro todavia no "
                           "autorizo cuanto puede pedir")
        if accion == "pedir":
            # El techo ACUMULADO. `techo_preseed_mm` recorta cada pedido,
            # pero el unico freno de caudal -TECHO_PROPUESTAS- no ve los
            # pre-seed ya financiados: `situacion` los saca de las dos
            # listas, asi que cada financiacion vaciaba el contador y
            # habilitaba otras tres rondas. El techo real terminaba siendo
            # `techo_preseed_mm` x 200 tics por semana mientras Pedro
            # siguiera tocando financiar, y la mesa no le mostraba ningun
            # acumulado: cada fila era un pedido suelto.
            #
            # El freno sale de lo que el pre-seed ES: capital para
            # ARRANCAR, "que un departamento sin plata pueda pedirla". Un
            # departamento que ya tiene en la billetera lo que una ronda le
            # daria no esta arrancando. Se cuenta lo que tiene mas lo que ya
            # pidio y sigue en la mesa, para que tres pedidos en pie no den
            # tres veces el techo.
            techo = int(s.get("techo_preseed_mm") or 0)
            ya = (int(s.get("disponible_mm") or 0)
                  + int(s.get("preseed_pendiente_mm") or 0))
            if ya >= techo:
                return False, (f"ya tiene {ya} mm entre billetera y pedidos "
                               f"en pie, y el techo de la ronda es {techo}: "
                               "el pre-seed es para arrancar sin plata")
            # EL SEGUNDO TECHO, el del CICLO, y el ultimo de los frenos
            # porque es el mas caro de chequear: los de arriba miran un
            # numero de la perilla o una lista corta; este pliega el libro
            # entero de las semanas del ciclo.
            #
            # Que cuenta: lo FINANCIADO del ciclo mas lo PEDIDO que sigue
            # en la mesa. Las dos cosas, y por motivos distintos. Lo
            # financiado ya salio del tesoro y el libro no lo desescribe:
            # es piso duro. Lo pedido todavia no es plata, pero es plata
            # que Pedro puede soltar con un toque, asi que vale como
            # reserva mientras siga en pie -- sin eso, publicar dos
            # pedidos que juntos pasan el techo es gratis, y el freno
            # llega recien en `bus.financiar`, con el pedido ya en la
            # bandeja de Pedro pidiendole plata que no le puede dar. Y es
            # solo una reserva: si Pedro descarta, el cupo vuelve entero,
            # que es la razon por la que descartar existe.
            #
            # Del lado de Pedro se cuenta distinto (solo lo financiado):
            # ver el comentario en `bus.financiar`.
            techo_ciclo = int(s.get("techo_preseed_ciclo_mm") or 0)
            if techo_ciclo <= 0:
                return False, ("sin techo de pre-seed por ciclo: Pedro "
                               "todavia no autorizo cuanto capital puede "
                               "entrar por ciclo")
            ya_ciclo = (int(s.get("preseed_ciclo_mm") or 0)
                        + int(s.get("preseed_pendiente_mm") or 0))
            if ya_ciclo >= techo_ciclo:
                return False, (f"el techo del ciclo es {techo_ciclo} mm y "
                               f"entre lo financiado y lo pedido en pie ya "
                               f"van {ya_ciclo}: que Pedro suba la perilla "
                               "o espere al ciclo que viene")
        if accion == "proponer" and s["presupuesto_semanal_mm"] > 0:
            # La agresividad mide contra el presupuesto SEMANAL. Un
            # departamento recien dado de alta todavia no tiene presupuesto
            # semanal (esta esperando justo el pre-seed que "pedir" le
            # permite pedir): con presupuesto en cero el tope tambien da
            # cero, y `salidas_semana_mm >= 0` es siempre verdadero, asi que
            # el freno frenaba para siempre por un motivo que no es
            # agresividad. Sin presupuesto todavia, este freno no aplica.
            tope = s["presupuesto_semanal_mm"] * s["agresividad_pct"] // 100
            if s["salidas_semana_mm"] >= tope:
                return False, (f"agresividad: ya comprometio "
                               f"{s['salidas_semana_mm']} de {tope} mm")
        return True, ""
    if s["disponible_mm"] <= 0:
        return False, "sin saldo disponible"
    return True, ""


def tic(ctx: Contexto, cuenta: str, semana: str) -> dict:
    """Un despertar. Devuelve que decidio y por que, siempre."""
    def corto(accion: str, motivo: str, freno: str) -> dict:
        """Los caminos que salen antes de saber el sesgo."""
        return {"cuenta": cuenta, "accion": accion, "ref": None,
                "motivo": motivo, "sesgo_pct": 0, "actuo": False,
                "freno": freno, "resultado": None}

    try:
        estado = it.leer(ctx.base)
        if not estado.encendido:
            # cortar ANTES del modelo: apagar la fabrica no puede seguir
            # costando un tic por departamento
            return corto("apagado", "el interruptor esta en parar", "apagado")
        if not it.tomar_tic(ctx.base, cuenta, semana):
            return corto("sin_cuerda",
                         f"ya uso sus {estado.techo_tics} tics de la semana",
                         "techo de tics")
        s = sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                          ctx.suscripciones, semana, cuenta)
        cap = s["capacidad"] or {}
        sesgo = dec.sesgo_efectivo(s["explorar_explotar_pct"],
                                   cap.get("precio_mm", 0),
                                   cap.get("precio_base_mm", 0))
    except Exception as exc:
        # todavia no se publico `inicio`, asi que no hay agente que cerrar:
        # lo unico que falta garantizar es que el llamador reciba su dict
        return corto("nada", f"no llego a decidir: {exc}",
                     "fallo antes de decidir")

    def salida(accion="nada", ref=None, motivo="", actuo=False, freno="",
               resultado=None) -> dict:
        """Las ocho claves, siempre: la rutina de la Tarea 6 las lee todas."""
        return {"cuenta": cuenta, "accion": accion, "ref": ref,
                "motivo": motivo, "sesgo_pct": sesgo, "actuo": actuo,
                "freno": freno, "resultado": resultado}

    # el prompt se arma ANTES del `inicio`: si la memoria o la forma de
    # `situacion` fallan, no es culpa del modelo, y asi tampoco queda un
    # agente abierto en el pulso sin nadie que lo cierre
    try:
        p = dec.prompt(s, sesgo, ctx.memoria.load_core(),
                       ctx.memoria.recent(limit=5))
    except Exception as exc:
        return salida(motivo=f"no armo el prompt: {exc}",
                      freno="fallo antes de pensar")

    ctx.publicar("inicio", departamento=cuenta, rol="jefe")
    fin = "ok"
    try:
        try:
            crudo = ctx.pensar(p)
        except Exception as exc:
            fin = "error"
            return salida(motivo=f"no penso: {exc}", freno="el modelo fallo")

        accion, ref, motivo = dec.parsear(crudo)
        ctx.publicar("razonando",
                     texto=f"{accion} {ref or ''} — {motivo}".strip())

        permiso, freno = _puede(estado, s, accion, ref)
        resultado = None
        if permiso:
            resultado = ctx.contratar(s, accion, ref, motivo)
            try:
                ctx.memoria.remember(f"{accion} {ref or ''}: {motivo}".strip(),
                                     kind="jefe", departamento=cuenta)
            except Exception as exc:
                # contratar ya ocurrio y ya se cobro: decir que no actuo
                # seria mentir sobre plata que salio
                fin = "error"
                motivo = f"{motivo} (no pudo anotar en su memoria: {exc})"
        return salida(accion, ref, motivo, permiso, freno, resultado)
    except Exception as exc:
        fin = "error"
        return salida(motivo=f"reviento actuando: {exc}",
                      freno="fallo al actuar")
    finally:
        # el `fin` sale SIEMPRE (misma regla que pulso.py): un agente que
        # revienta y queda razonando deja el escritorio ocupado por un fantasma
        ctx.publicar("fin", resultado=fin)
