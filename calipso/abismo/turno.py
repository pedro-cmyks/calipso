"""El estado del turno y las piezas puras de la reentrada -- spec seccion 4.

Vive junto al estado de conexion de `ws_chat`, atraviesa reentradas y solo
un mensaje real de Pedro lo resetea (invariante 8). Todo lo de aca es puro:
sin WebSocket, sin modelo, sin disco.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from calipso.abismo import marca

ABISMO_CONSULTAS_MAX = 3          # consultas por turno (spec seccion 4)
FASES = ("pondering", "pescado", "fallo")
MOTIVOS = ("vacio", "credencial", "solo_hondo", "juez_local_caido",
           "tipo_desconocido", "error")
VERBOS = {"memoria": "buscando en tu memoria",
          "chats": "buscando en tus chats",
          "proyecto": "mirando el repo"}
INSTRUCCION_CONTINUAR = "Segui exactamente desde ahi, sin repetir."
# las letras que el canario `fuga_de_reentrada` caza en la respuesta
# (canarios.py); la Task 7 suma la letra con bloques
LETRAS_REENTRADA = (INSTRUCCION_CONTINUAR,)


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


def prompt_reentrada(system_base: str, bloques: list[str],
                     tramos_crudos: list[str], mensaje: str) -> tuple[str, str]:
    """(system, mensaje de usuario) de la pasada sintetica. Los bloques van
    como append post-compile del system base del turno (construido UNA vez:
    no se re-corre recall ni economia). El parcial viaja por UNA sola via,
    el "venias diciendo" del mensaje, nunca como mensaje assistant. El
    mensaje original tambien viaja: `_history_messages` descarta el ultimo
    mensaje del chat (el de Pedro), asi que sin esto la reentrada no sabria
    que se le pregunto."""
    system = system_base + "".join("\n\n" + b for b in bloques if b)
    venia = "".join(tramos_crudos)
    usuario = f"{mensaje}\n\nVenias diciendo: {venia}\n{INSTRUCCION_CONTINUAR}"
    return system, usuario


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
