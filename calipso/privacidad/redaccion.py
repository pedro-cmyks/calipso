"""Tapar los tramos de lenguaje humano con marcadores estables antes de mandar
a la nube, y reponerlos localmente al volver. Lo sensible nunca esta en el
trafico de salida (spec seccion 9).

Los marcadores son estables por conversacion: el mismo valor real recibe el
mismo marcador en todos los turnos, para que la nube no pierda el hilo. Un
`MapaMarcadores` dura una conversacion; el parte 2 decide donde vive.

Las credenciales NO pasan por aca: fallan cerrado antes (el juez no las deja en
`tramos`).
"""
import re

# tipo del juez -> prefijo del marcador
_PREFIJO = {
    "identidad": "ID",
    "contacto": "CONTACTO",
    "salud": "SALUD",
    "ubicacion": "LUGAR",
    "financiero": "FINANZA",
}


class MapaMarcadores:
    """El diccionario estable de una conversacion: valor real <-> marcador."""

    def __init__(self) -> None:
        self._a_marcador: dict[str, str] = {}   # texto real -> "[TIPO_N]"
        self._a_valor: dict[str, str] = {}       # "[TIPO_N]" -> texto real
        self._conta: dict[str, int] = {}         # prefijo -> ultimo N usado

    def marcador_para(self, texto: str, tipo: str) -> str:
        if texto in self._a_marcador:
            return self._a_marcador[texto]
        prefijo = _PREFIJO.get(tipo, "DATO")
        self._conta[prefijo] = self._conta.get(prefijo, 0) + 1
        marcador = f"[{prefijo}_{self._conta[prefijo]}]"
        self._a_marcador[texto] = marcador
        self._a_valor[marcador] = texto
        return marcador

    def reponer_texto(self, s: str) -> str:
        # reemplaza cada marcador conocido por su valor real
        def sub(m: re.Match) -> str:
            return self._a_valor.get(m.group(0), m.group(0))
        return re.sub(r"\[[A-Z]+_\d+\]", sub, s)


def redactar(texto: str, tramos: list[dict], mapa: MapaMarcadores) -> str:
    """Reemplaza cada tramo por su marcador estable. Tapa los tramos mas largos
    primero: si uno es subcadena de otro, taparlo despues dejaria un pedazo del
    corto suelto adentro del largo."""
    for t in sorted(tramos, key=lambda x: len(x["texto"]), reverse=True):
        if not t["texto"]:
            continue
        marcador = mapa.marcador_para(t["texto"], t["tipo"])
        texto = texto.replace(t["texto"], marcador)
    return texto


def reponer(texto: str, mapa: MapaMarcadores) -> str:
    """Repone los valores reales en un texto con marcadores (la respuesta de la
    nube), localmente, antes de mostrarlo."""
    return mapa.reponer_texto(texto)
