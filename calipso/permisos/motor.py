"""
calipso/permisos/motor.py — La puerta unica.

La regla de 5.2, en una linea: Calipso puede hacer lo que Pedro puede hacer
en su maquina; antes de las acciones que no se deshacen solas, pregunta -- en
el momento, con el texto exacto a la vista; todo queda registrado.

Este archivo es el UNICO lugar donde eso se decide. El umbral de plata no es
un motor aparte: es el primer consumidor de este. Acunar 500 monedas y correr
un `rm -rf` son la misma pregunta -- una accion que no se deshace sola -- y
tener dos motores daria dos lugares donde configurar lo mismo y dos formas de
que se contradigan.

Como se enchufa un consumidor nuevo (la terminal, los archivos, las apps):

  1. armar una `Accion` con su familia, su operacion y su FORMA exacta;
  2. llamar a `evaluar(accion, contexto)`;
  3. si vuelve "permitido", hacerlo; si vuelve "pendiente" o "estacionada",
     NO hacerlo y devolverle a quien pidio el id de la solicitud;
  4. registrar con `registrar_ejecutor(familia, operacion, fn)` como se
     ejecuta esa accion, para que la respuesta de Pedro pueda completarla.

No hay paso 5. La tabla de niveles vive en `acciones.py` y ya cubre las
cuatro familias de 5.3.

Lo que este modulo NUNCA hace: conceder. El modelo puede pedir; la escalada
es de Pedro, siempre (5.4). `evaluar` solo lee permisos; el unico camino que
escribe uno es `responder(..., "si_siempre" o "no_siempre")`, que sale de un
endpoint autenticado.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from . import almacen
from .acciones import (Accion, Contexto, ErrorPermisos, NIVEL_DIRECTO,
                       NIVEL_NUNCA, clasificar)

ESTADO_PERMITIDO = "permitido"
ESTADO_PENDIENTE = "pendiente"
ESTADO_ESTACIONADA = "estacionada"
ESTADO_NEGADO = "negado"


@dataclass(frozen=True)
class Resolucion:
    estado: str
    motivo: str
    nivel: str = ""
    solicitud: dict | None = None
    permiso: dict | None = None

    @property
    def permitido(self) -> bool:
        return self.estado == ESTADO_PERMITIDO

    def a_dict(self) -> dict:
        return {"estado": self.estado, "motivo": self.motivo,
                "nivel": self.nivel, "solicitud": self.solicitud,
                "permiso": self.permiso}


# --------------------------------------------------------------------------
# Ejecutores: como se completa una accion que Pedro aprobo
# --------------------------------------------------------------------------

_EJECUTORES: dict[tuple[str, str], Callable[[Accion], dict]] = {}


def registrar_ejecutor(familia: str, operacion: str,
                       fn: Callable[[Accion], dict]) -> None:
    _EJECUTORES[(familia, operacion)] = fn


def ejecutores() -> tuple[tuple[str, str], ...]:
    return tuple(sorted(_EJECUTORES))


# --------------------------------------------------------------------------
# El texto que ve Pedro
# --------------------------------------------------------------------------

def texto_del_prompt(a: Accion, v) -> str:
    """Una linea con el texto EXACTO a la vista (5.2). Sale de `titulo` si
    el llamador lo escribio, y si no de la forma cruda -- que es peor de
    leer pero nunca miente sobre lo que se va a hacer."""
    if a.titulo:
        return f"{a.titulo} ({v.motivo})"
    return f"{a.familia}/{a.operacion} {a.forma} ({v.motivo})"


# --------------------------------------------------------------------------
# evaluar
# --------------------------------------------------------------------------

def _anotar(a: Accion, ctx: Contexto, res: Resolucion) -> Resolucion:
    """El rastro de 5.4: cada accion deja una linea, se haya preguntado o
    no, y tambien las negadas."""
    almacen.anotar({"familia": a.familia, "operacion": a.operacion,
                    "forma": a.forma, "detalle": a.detalle,
                    "titulo": a.titulo, "contexto": ctx.a_dict(),
                    "nivel": res.nivel, "estado": res.estado,
                    "motivo": res.motivo,
                    "solicitud": (res.solicitud or {}).get("id"),
                    "permiso": (res.permiso or {}).get("id")})
    return res


def evaluar(a: Accion, ctx: Contexto | None = None) -> Resolucion:
    """La unica funcion que decide si algo pasa.

    El orden de los cortes NO es cosmetico:

      1. la pared de la corrida, antes que nada. Si esta corrida ya
         estaciono algo, termino (5.6.2): lo que siga saliendo de ella es
         un rodeo, aunque sea de nivel directo.
      2. la pared de la forma, ANTES de clasificar. Mientras una forma
         este esperando respuesta, esa forma no pasa por ningun lado --
         ni por otro departamento, ni por otro chat, ni porque alguien
         subio el techo mientras tanto. Clasificar primero abriria
         exactamente ese hueco.
      3. una solicitud que Pedro YA aprobo y que todavia no se ejecuto se
         consume aca, atomica: es como la rutina retoma en su proxima
         corrida (5.6.2) sin volver a preguntar y sin poder hacerlo dos
         veces.
      4. una regla permanente de NO, antes de clasificar. Tiene que ir aca y
         no donde va el si: despues de clasificar ya pasaron NIVEL_NUNCA y
         NIVEL_DIRECTO, asi que un no puesto alla jamas taparia escribir
         dentro de las raices, ni un comando del allowlist, ni un monto bajo
         el techo -- y subir el techo anularia en silencio un no que Pedro
         ya habia dado. Va despues del consumo de aprobadas a proposito: lo
         que Pedro ya aprobo, se ejecuta; la regla gobierna lo que venga.
      5. recien ahi, el nivel.
    """
    ctx = ctx or Contexto()
    try:
        pared = almacen.por_corrida(ctx.corrida)
        if pared is not None:
            almacen.anotar_intento(pared["id"], a, ctx, "rodeo de corrida")
            return _anotar(a, ctx, Resolucion(
                ESTADO_ESTACIONADA,
                "la corrida ya quedo estacionada en la solicitud "
                f"{pared['id']}: termino (5.6.2)",
                solicitud=pared))

        abierta = almacen.por_forma(a.clave())
        if abierta is not None:
            mismo = (abierta.get("contexto") or {}) == ctx.a_dict()
            almacen.anotar_intento(
                abierta["id"], a, ctx,
                "reintento del mismo pedido" if mismo
                else "rodeo: otro origen pide la misma forma")
            estado = (ESTADO_PENDIENTE
                      if abierta.get("estado") == almacen.ESTADO_PENDIENTE
                      else ESTADO_ESTACIONADA)
            return _anotar(a, ctx, Resolucion(
                estado, f"ya hay una solicitud {estado} para esta forma "
                        f"({abierta['id']})",
                nivel=abierta.get("nivel", ""), solicitud=abierta))

        for s in almacen.solicitudes():
            if s.get("clave") == a.clave() and \
                    s.get("estado") == almacen.ESTADO_APROBADA:
                tomada = almacen.tomar_para_ejecutar(s["id"])
                if tomada is not None:
                    return _anotar(a, ctx, Resolucion(
                        ESTADO_PERMITIDO,
                        f"Pedro ya la aprobo ({s['id']})",
                        nivel=s.get("nivel", ""), solicitud=tomada))

        # este corte precede a NIVEL_NUNCA: si alguna vez una regla llegara a
        # cubrir una accion de ese nivel, el registro diria "regla permanente
        # de no" en vez del motivo real (la credencial del propio servidor,
        # 5.7). Inalcanzable hoy -- una accion NUNCA nunca crea solicitud, y
        # sin solicitud no hay de donde escribir la regla.
        regla = almacen.regla_que_cubre(a, "denegar")
        if regla is not None:
            return _anotar(a, ctx, Resolucion(
                ESTADO_NEGADO, f"regla permanente de no: {regla['id']}",
                permiso=regla))

        v = clasificar(a, almacen.techos())

        if v.nivel == NIVEL_NUNCA:
            return _anotar(a, ctx, Resolucion(ESTADO_NEGADO, v.motivo,
                                              nivel=v.nivel))
        if v.nivel == NIVEL_DIRECTO:
            return _anotar(a, ctx, Resolucion(ESTADO_PERMITIDO, v.motivo,
                                              nivel=v.nivel))

        if not v.siempre_pregunta:
            permiso = almacen.cubierta_por_permiso(a)
            if permiso is not None:
                return _anotar(a, ctx, Resolucion(
                    ESTADO_PERMITIDO,
                    f"permiso permanente {permiso['id']}",
                    nivel=v.nivel, permiso=permiso))

        texto = texto_del_prompt(a, v)

        if ctx.desatendido:
            # 5.6.3: el camino desatendido NUNCA cae al prompt interactivo.
            # No pregunta, porque no hay a quien; y no se auto-aprueba por
            # ningun default, porque no hay ningun default que tomar.
            if not v.siempre_pregunta:
                pre = almacen.cubierta_por_preautorizacion(a, ctx.departamento)
                if pre is not None:
                    return _anotar(a, ctx, Resolucion(
                        ESTADO_PERMITIDO,
                        f"pre-autorizada por el departamento "
                        f"{ctx.departamento} (5.6.1)",
                        nivel=v.nivel, permiso=pre))
            s = almacen.crear(a, ctx, almacen.ESTADO_ESTACIONADA, v.nivel,
                              v.motivo, v.siempre_pregunta, texto)
            return _anotar(a, ctx, Resolucion(
                ESTADO_ESTACIONADA,
                "no hay a quien preguntarle: queda esperando en /fabrica "
                "(5.6.2)", nivel=v.nivel, solicitud=s))

        s = almacen.crear(a, ctx, almacen.ESTADO_PENDIENTE, v.nivel, v.motivo,
                          v.siempre_pregunta, texto)
        return _anotar(a, ctx, Resolucion(
            ESTADO_PENDIENTE, "esperando la respuesta de Pedro",
            nivel=v.nivel, solicitud=s))

    except ErrorPermisos as exc:
        # el estado no se pudo leer: no se sabe que quedo estacionado, asi
        # que no se puede garantizar que esto no sea un rodeo. Se niega.
        return _anotar(a, ctx, Resolucion(
            ESTADO_NEGADO, f"el motor de permisos no puede decidir: {exc}"))


# --------------------------------------------------------------------------
# La respuesta de Pedro
# --------------------------------------------------------------------------

def ejecutar(solicitud: dict) -> dict:
    """Completa una solicitud ya aprobada. La transicion
    aprobada -> ejecutando es atomica (`tomar_para_ejecutar`), asi que dos
    respuestas que lleguen juntas no acunan dos veces."""
    tomada = almacen.tomar_para_ejecutar(solicitud["id"])
    if tomada is None:
        return {"ejecutada": False,
                "motivo": "no estaba aprobada, o ya la tomo otro"}
    a = Accion.de_dict(tomada["accion"])
    fn = _EJECUTORES.get((a.familia, a.operacion))
    if fn is None:
        almacen.cerrar_ejecucion(
            tomada["id"], False,
            {"error": f"sin ejecutor para {a.familia}/{a.operacion}"})
        return {"ejecutada": False,
                "motivo": f"sin ejecutor para {a.familia}/{a.operacion}"}
    try:
        resultado = fn(a)
    except Exception as exc:
        almacen.cerrar_ejecucion(tomada["id"], False,
                                 {"error": f"{type(exc).__name__}: {exc}"})
        return {"ejecutada": False, "motivo": str(exc)}
    almacen.cerrar_ejecucion(tomada["id"], True, resultado)
    return {"ejecutada": True, "resultado": resultado}


def cerrar(id_solicitud: str, ok: bool, resultado: dict) -> dict | None:
    """Para el consumidor que ejecuta por su cuenta lo que `evaluar`
    consumio de una solicitud aprobada (el caso de la rutina que retoma)."""
    return almacen.cerrar_ejecucion(id_solicitud, ok, resultado)


def responder(id_solicitud: str, respuesta: str, quien: str = "pedro",
              forma_permanente: dict | None = None) -> dict:
    """Las cuatro salidas de 5.4: si una vez, si y no preguntes mas para
    esto, no, y no me preguntes mas.

    Un "si" sobre una solicitud INTERACTIVA se ejecuta ahi mismo: hay
    alguien esperando el efecto. Un "si" sobre una ESTACIONADA no se
    ejecuta aca -- la rutina la retoma en su proxima corrida (5.6.2), y
    `evaluar` la consume sola cuando esa corrida vuelve a pedir la misma
    forma.
    """
    s = almacen.responder(id_solicitud, respuesta, quien)
    permiso = None
    if respuesta in ("si_siempre", "no_siempre"):
        a = Accion.de_dict(s["accion"])
        ctx = Contexto.de_dict(s.get("contexto"))
        # el orden importa y es el de hoy: primero se responde la solicitud,
        # despues se escribe la regla. Si la segunda escritura falla, queda
        # una decision sin regla -- molesto, se vuelve a preguntar. Al reves
        # quedaria una regla sin decision, que es el lado peligroso: una
        # regla de negar escrita sobre algo que Pedro nunca termino de
        # contestar.
        permiso = almacen.anotar_regla(
            a, ctx, s.get("texto", ""),
            siempre_pregunta=s.get("siempre_pregunta", False),
            forma=forma_permanente,
            efecto="permitir" if respuesta == "si_siempre" else "denegar")
    salida = {"solicitud": s, "permiso": permiso, "ejecucion": None}
    interactiva = not Contexto.de_dict(s.get("contexto")).desatendido
    if s["estado"] == almacen.ESTADO_APROBADA and interactiva:
        salida["ejecucion"] = ejecutar(s)
        salida["solicitud"] = almacen.obtener(id_solicitud) or s
    almacen.anotar({"evento": "respuesta", "solicitud": id_solicitud,
                    "respuesta": respuesta, "quien": quien,
                    "permiso": (permiso or {}).get("id"),
                    "ejecucion": salida["ejecucion"]})
    return salida


def aprobadas_para(departamento: str | None = None) -> list[dict]:
    """Lo que la rutina tiene que retomar en su proxima corrida."""
    out = []
    for s in almacen.solicitudes():
        if s.get("estado") != almacen.ESTADO_APROBADA:
            continue
        if departamento and (s.get("contexto") or {}).get(
                "departamento") != departamento:
            continue
        out.append(s)
    return out


# --------------------------------------------------------------------------
# 5.9 -- lo que se ve en /fabrica
# --------------------------------------------------------------------------

def vista(limite_registro: int = 50) -> dict:
    """Tira propia con endpoint propio (5.9): los prompts pendientes, las
    solicitudes estacionadas de los departamentos y los permisos
    permanentes con lo que hace falta para revocarlos.

    No va por el bus ni por la cola de la economia: una propuesta del bus
    y una carta de la cola son objetos ECONOMICOS -- tienen escrow,
    asientos, y su atencion la lee `cerrar_ciclo` -- y un permiso no lo
    es."""
    try:
        todas = almacen.solicitudes()
        error = None
    except ErrorPermisos as exc:
        todas, error = [], str(exc)
    return {
        "pendientes": [s for s in todas
                       if s.get("estado") == almacen.ESTADO_PENDIENTE],
        "estacionadas": [s for s in todas
                         if s.get("estado") == almacen.ESTADO_ESTACIONADA],
        "aprobadas": [s for s in todas
                      if s.get("estado") == almacen.ESTADO_APROBADA],
        "concedidos": almacen.concedidos(),
        "techos": almacen.techos(),
        "registro": almacen.registro(limite_registro),
        "error": error,
    }


# --------------------------------------------------------------------------
# El adaptador para el inbox
# --------------------------------------------------------------------------

ORIGEN_INBOX = "permisos"


def descriptor() -> dict:
    """Lo que permisos declara de si mismo para el inbox.

    NO hay verbo "despues". Mientras una solicitud este abierta, esa forma
    exacta no pasa por ningun chat, ningun departamento ni ningun techo
    nuevo: aplazarla no es aplazar, es prolongar un bloqueo global.

    `reloj: None` no es un olvido: permisos no vence. Es una de las dos
    bandejas que tienen que declararlo explicitamente, porque el default
    no se puede inferir.

    `no_siempre` es la mitad que el spec (4c) dice que le faltaba al sistema
    entero, y permisos es la unica de las cuatro bandejas donde se puede
    escribir hoy: es la unica que ya tiene una FORMA tipada que comparar
    (`acciones.cubre`). Las otras tres identifican sus items por prosa libre.
    """
    return {
        "origen": ORIGEN_INBOX,
        "verbos": [
            {"nombre": "si", "etiqueta": "Si",
             "alcances": ["una_vez"], "parametros": []},
            {"nombre": "si_siempre", "etiqueta": "Si, siempre",
             "alcances": ["siempre"], "parametros": []},
            {"nombre": "no", "etiqueta": "No",
             "alcances": ["una_vez"], "parametros": []},
            {"nombre": "no_siempre", "etiqueta": "No, nunca mas",
             "alcances": ["siempre"], "parametros": []},
        ],
        "reloj": None,
        "clase_por_defecto": "decision",
        "vara": None,
        "lugares": None,
    }


def como_items(datos_endpoint: dict) -> list[dict]:
    """Traduce la respuesta de GET /api/permisos a items del inbox.

    El endpoint agrega la clave `activo` envolviendola sobre motor.vista():
    si `activo` es False, retorna lista vacia. No se puede hacer
    motor.como_items(motor.vista()) sin envolver, porque vista() no tiene
    `activo` -- si alguien lo intenta, cae silencioso.

    La clave de disponibilidad es `activo` (masculino), no `activa`: la de
    economia es la otra y confundirlas deja el contador en cero sin ruido.

    Solo lo ABIERTO es item. `aprobadas` y `registro` vienen en la misma
    respuesta y no son cosas que esperen a Pedro.

    Y el caso que hace mentir a un badge: cuando el archivo solicitudes.json
    no se puede leer, el endpoint devuelve `error` con todas las listas
    vacias. Vacio por error se ve igual que vacio de verdad, asi que se
    emite un aviso -- que no cuenta para el badge, pero se ve.
    """
    if not datos_endpoint.get("activo"):
        return []
    items = []
    if datos_endpoint.get("error"):
        items.append({
            "id": "permisos:error", "origen": ORIGEN_INBOX, "clase": "aviso",
            "ts": "", "titulo": f"no se pudo leer permisos: {datos_endpoint['error']}",
            "cuerpo": {"verbos_validos": []}, "estado": "error",
            "respuesta": None})
    for s in (datos_endpoint.get("pendientes") or []) + (datos_endpoint.get("estacionadas") or []):
        # si_siempre sobre una solicitud con siempre_pregunta devuelve 400:
        # lo cortan `almacen.responder` y `almacen.anotar_regla`, las dos
        # capas. no_siempre no tiene esa restriccion y es a proposito: lo que
        # pregunta siempre es lo irreversible, y un NO permanente sobre eso
        # falla hacia el lado conservador. Dibujar el verbo que va a dar 400
        # es dibujar un boton que miente, asi que la lista se parte aca.
        verbos = ["si", "no", "no_siempre"] if s.get("siempre_pregunta") \
            else ["si", "si_siempre", "no", "no_siempre"]
        items.append({
            "id": s.get("id"), "origen": ORIGEN_INBOX, "clase": "decision",
            "ts": s.get("ts") or "", "titulo": s.get("texto") or "",
            "cuerpo": {"accion": s.get("accion"),
                       "contexto": s.get("contexto"),
                       "motivo": s.get("motivo"),
                       "verbos_validos": verbos},
            "estado": s.get("estado") or "pendiente", "respuesta": None})
    return items
