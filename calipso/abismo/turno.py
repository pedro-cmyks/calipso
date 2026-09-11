"""El estado del turno y las piezas puras de la reentrada -- spec seccion 4.

Vive junto al estado de conexion de `ws_chat`, atraviesa reentradas y solo
un mensaje real de Pedro lo resetea (invariante 8). Todo lo de aca es puro:
sin WebSocket, sin modelo, sin disco.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from calipso import prompt_compiler
from calipso.abismo import marca

ABISMO_CONSULTAS_MAX = 3          # consultas por turno (spec seccion 4)
FASES = ("pondering", "pescado", "fallo")
MOTIVOS = ("vacio", "credencial", "solo_hondo", "juez_local_caido",
           "tipo_desconocido", "error")
VERBOS = {"memoria": "buscando en tu memoria",
          "chats": "buscando en tus chats",
          "proyecto": "mirando el repo"}
INSTRUCCION_CONTINUAR = "Segui exactamente desde ahi, sin repetir."
# La honestidad en la reentrada (spec canarios 2026-09-11, seccion 4): SOLO
# cuando hay bloques, la instruccion suma que lo que sigue se basa en lo que
# subio y en lo que ya tenia, y que si no trae el dato lo diga con esas
# palabras (la frase entra a PATRONES_FUERTES de la memoria por el banco).
# Tras un `fallo` la reentrada va sin bloque y lleva la letra de siempre:
# "se basa SOLO en lo que subio" con nada subido seria un no-saber
# inducido. LETRA MEDIDA por el porton (experimentos/porton_reentrada.py):
# atada byte a byte a experimentos/variantes/reentrada-con-bloques.txt y
# reentrada-sin-bloques.txt (test_abismo_turno.py); no cambiarla sin
# re-correr el porton.
INSTRUCCION_CONTINUAR_CON_BLOQUES = (
    "Segui exactamente desde ahi, sin repetir. Lo que sigue se basa SOLO en lo "
    "que subio del abismo y en lo que ya tenias en este prompt; si lo que subio "
    "no trae el dato, decilo con esas palabras en vez de completarlo.")
# las letras que el canario `fuga_de_reentrada` caza en la respuesta
LETRAS_REENTRADA = (INSTRUCCION_CONTINUAR, INSTRUCCION_CONTINUAR_CON_BLOQUES)
# el interruptor del porton: CALIPSO_REENTRADA=vieja manda la letra de
# siempre aunque haya bloques (la condicion `antes`); cualquier otra cosa o
# ausente es la letra nueva. Se lee POR LLAMADA, nunca congelado
LETRA_DEFAULT = "nueva"


def letra_activa() -> str:
    valor = os.environ.get("CALIPSO_REENTRADA", "").strip().lower()
    return valor if valor in ("vieja", "nueva") else LETRA_DEFAULT


def instruccion_de_reentrada(hay_bloques: bool) -> str:
    if hay_bloques and letra_activa() == "nueva":
        return INSTRUCCION_CONTINUAR_CON_BLOQUES
    return INSTRUCCION_CONTINUAR


@dataclass
class EstadoTurno:
    """Lo que la pasada sintetica necesita saber del turno: cuantas veces
    consulto, que subio (los textos que ya viajaron, en orden), que vio
    Pedro (tramos visibles, ya filtrados) y que escribio el modelo ANTES de
    reponer (tramos crudos: en local son identicos a `tramos`; en /nube
    llevan los marcadores y son los que vuelven a la nube, invariante 9).
    `apagada`: la consulta no corre en lo que queda del turno (fallback,
    orquestador): las marcas se retiran sin cortar."""
    consultas: int = 0
    bloques: list[str] = field(default_factory=list)
    tramos: list[str] = field(default_factory=list)
    tramos_crudos: list[str] = field(default_factory=list)
    sintetica: bool = False
    apagada: bool = False

    def reset(self) -> None:
        self.consultas = 0
        self.bloques = []
        self.tramos = []
        self.tramos_crudos = []
        self.sintetica = False
        self.apagada = False

    def puede_cortar(self) -> bool:
        """Bajo el tope y con la consulta encendida, una marca valida corta.
        Si no, se retira y el texto posterior vale (los dos regimenes del
        spec, a proposito)."""
        return not self.apagada and self.consultas < ABISMO_CONSULTAS_MAX


def prompt_reentrada(secciones_base: list[tuple[str, str]], bloques: list[str],
                     tramos_crudos: list[str], mensaje: str,
                     ) -> tuple[list[tuple[str, str]], str]:
    """(secciones del system, mensaje de usuario) de la pasada sintetica.
    Los bloques van como SECCIONES detras de las del system base del turno
    (construido UNA vez: no se re-corre recall ni economia); cada bloque
    trae su encabezado `=== Lo que subio del abismo (fuente: X) ===` y
    `seccion_de_bloque` lo vuelve (titulo, cuerpo), asi el render es byte a
    byte el append de antes y el recorte de la ventana puede sacar el
    bloque mas viejo sin partir texto (spec canarios 2.3). El parcial viaja
    por UNA sola via, el "venias diciendo" del mensaje, nunca como mensaje
    assistant. El mensaje original tambien viaja: `_history_messages`
    descarta el ultimo mensaje del chat (el de Pedro), asi que sin esto la
    reentrada no sabria que se le pregunto."""
    con_bloques = [b for b in bloques if b]
    secciones = list(secciones_base) + [prompt_compiler.seccion_de_bloque(b)
                                        for b in con_bloques]
    venia = "".join(tramos_crudos)
    instruccion = instruccion_de_reentrada(bool(con_bloques))
    usuario = f"{mensaje}\n\nVenias diciendo: {venia}\n{instruccion}"
    return secciones, usuario


def senal(fase: str, fuente: str, **campos) -> dict:
    """El dict de `{type:"abismo"}` con los campos fijos por fase (spec
    seccion 9): `verbo` en pondering, `tamano` + `viaje` en pescado,
    `motivo` (de la lista cerrada) en fallo. Lo que sobra en `campos` viaja
    tal cual."""
    if fase not in FASES:
        raise ValueError(f"fase desconocida: {fase!r}")
    s = {"type": "abismo", "fase": fase, "fuente": fuente}
    if fase == "pondering":
        s["verbo"] = campos.pop("verbo", None) or VERBOS.get(fuente, "consultando el abismo")
    elif fase == "pescado":
        s["tamano"] = int(campos.pop("tamano", 0))
        s["viaje"] = campos.pop("viaje", None) or {"destino": "local"}
    else:
        motivo = campos.pop("motivo", "error")
        s["motivo"] = motivo if motivo in MOTIVOS else "error"
    s.update(campos)
    return s


def motivo_de_consulta(resultado: dict) -> str:
    """El motivo de la senal `fallo` a partir de lo que devolvio
    `consulta.resolver`: la pesca vacia es `vacio` (el aviso exacto de
    consulta._fallo, "la consulta no trajo nada"); todo lo demas, `error`."""
    return "vacio" if resultado.get("aviso") == "la consulta no trajo nada" else "error"


def cortar_en_marca(texto: str) -> tuple[str, marca.Marca | None]:
    """El detector one-shot (suscripcion, spec secciones 4 y 8): la primera
    marca VALIDA corta. Devuelve (lo anterior a la marca, la marca) o (el
    texto entero, None). Las ilegibles anteriores quedan en el texto: el
    Emisor las retira con aviso, como en el stream."""
    texto = texto or ""
    for m in marca.PATRON.finditer(texto):
        valida = marca.parsear(m.group(1))
        if valida is not None:
            return texto[:m.start()], valida
    return texto, None


def prefijo_congelado(texto: str) -> str | None:
    """Para el preview de suscripcion: lo visible hasta la primera marca
    valida, o None si todavia no hay ninguna (el preview sigue avanzando)."""
    tramo, m = cortar_en_marca(texto)
    return tramo if m is not None else None


def retirar_marcas(texto: str) -> str:
    """Todas las marcas del abismo (validas e ilegibles) fuera del texto: lo
    que el CLI escribio despues de una marca que no se pudo atender."""
    return marca.PATRON.sub("", texto or "")


# una marca que abrio y todavia no cerro, al FINAL del texto (el mismo
# cuerpo sin corchetes que PATRON, pero sin exigir el cierre)
_ABIERTA_AL_FINAL = re.compile(
    re.escape(marca.ABRE) + r"abismo:[^" + marca.CIERRA + marca.ABRE + r"]{0,400}$")


def recortar_abierta(texto: str) -> str:
    """Para el preview de suscripcion: una marca del abismo a medio llegar al
    final del parcial se recorta, asi Pedro no la lee cruda entre dos tics
    (spec seccion 4: no lee texto que despues se descarta). Las cerradas las
    saca `_limpiar_marcas`; un prefijo suelto (`⟦abi`) se ve un tic, como
    con foco."""
    return _ABIERTA_AL_FINAL.sub("", texto or "")
