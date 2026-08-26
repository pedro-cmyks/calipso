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
    contratar: Callable[[dict, str, "str | None"], Any]
    publicar: Callable[..., None] = field(
        default=lambda evento, **campos: None)


def _puede(estado, s: dict, accion: str) -> tuple[bool, str]:
    """Los frenos, del mas barato de chequear al mas caro de violar."""
    if accion == "nada":
        return False, "no hay nada que hacer"
    if not it.puede_gastar(estado):
        return False, f"modo {estado.modo}: mira y decide, no gasta"
    if s["disponible_mm"] <= 0:
        return False, "sin saldo disponible"
    if accion == "proponer":
        tope = s["presupuesto_semanal_mm"] * s["agresividad_pct"] // 100
        if s["salidas_semana_mm"] >= tope:
            return False, (f"agresividad: ya comprometio "
                           f"{s['salidas_semana_mm']} de {tope} mm")
    return True, ""


def tic(ctx: Contexto, cuenta: str, semana: str) -> dict:
    """Un despertar. Devuelve que decidio y por que, siempre."""
    estado = it.leer(ctx.base)
    if not estado.encendido:
        # cortar ANTES del modelo: apagar la fabrica no puede seguir
        # costando un tic por departamento
        return {"cuenta": cuenta, "accion": "apagado", "ref": None,
                "motivo": "el interruptor esta en parar", "sesgo_pct": 0,
                "actuo": False, "freno": "apagado", "resultado": None}
    if not it.hay_cuerda(ctx.base, estado, cuenta, semana):
        return {"cuenta": cuenta, "accion": "sin_cuerda", "ref": None,
                "motivo": f"ya uso sus {estado.techo_tics} tics de la semana",
                "sesgo_pct": 0, "actuo": False, "freno": "techo de tics",
                "resultado": None}
    it.anotar_tic(ctx.base, cuenta, semana)

    s = sit.situacion(ctx.kernel, ctx.registro, ctx.bus, ctx.cola,
                      ctx.suscripciones, semana, cuenta)
    cap = s["capacidad"] or {}
    sesgo = dec.sesgo_efectivo(s["explorar_explotar_pct"],
                               cap.get("precio_mm", 0),
                               cap.get("precio_base_mm", 0))

    ctx.publicar("inicio", departamento=cuenta, rol="jefe")
    try:
        crudo = ctx.pensar(dec.prompt(s, sesgo, ctx.memoria.load_core()))
    except Exception as exc:
        ctx.publicar("fin", resultado="error")
        return {"cuenta": cuenta, "accion": "nada", "ref": None,
                "motivo": f"no penso: {exc}", "sesgo_pct": sesgo,
                "actuo": False, "freno": "el modelo fallo", "resultado": None}

    accion, ref, motivo = dec.parsear(crudo)
    ctx.publicar("razonando",
                 texto=f"{accion} {ref or ''} — {motivo}".strip())

    permiso, freno = _puede(estado, s, accion)
    resultado = None
    if permiso:
        resultado = ctx.contratar(s, accion, ref)
        ctx.memoria.remember(f"{accion} {ref or ''}: {motivo}".strip(),
                             kind="jefe", departamento=cuenta)
    ctx.publicar("fin", resultado="ok")
    return {"cuenta": cuenta, "accion": accion, "ref": ref, "motivo": motivo,
            "sesgo_pct": sesgo, "actuo": permiso, "freno": freno,
            "resultado": resultado}
