"""
calipso/economia/libro.py — Persistencia append-only del libro contable.

Una linea JSON por asiento. Nunca se edita ni borra una linea; todo estado
se deriva plegando los asientos. Cada linea se valida al escribirse Y al
releerse, asi que las reglas de `Asiento.validar` cierran el libro de
verdad y no solo su puerta de escritura.

La carga tolera exactamente un defecto: la ultima linea truncada (corte a
mitad de un append); en ese caso el archivo se repara truncando el
fragmento nunca valido, para que el proximo append no se le pegue encima.
Cualquier otra corrupcion levanta LibroCorrupto: eso se mira, no se
ignora.
"""
from __future__ import annotations

import logging
import pathlib

from .tipos import Asiento, AsientoInvalido

log = logging.getLogger("calipso.economia.libro")


class ErrorLibro(Exception):
    pass


class LibroCorrupto(ErrorLibro):
    pass


class Libro:
    def __init__(self, ruta: pathlib.Path):
        self.ruta = pathlib.Path(ruta)
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self._asientos: list[Asiento] = []
        self._cargar()

    def _cargar(self) -> None:
        if not self.ruta.exists():
            return
        # split explicito en "\n": splitlines() tambien parte por
        # U+2028/U+2029/U+0085, que pueden aparecer dentro de un detalle.
        lineas = self.ruta.read_text(encoding="utf-8").split("\n")
        if lineas and lineas[-1] == "":
            lineas.pop()
        offset = 0  # bytes de las lineas buenas ya consumidas, con su "\n"
        for i, linea in enumerate(lineas):
            tam = len(linea.encode("utf-8")) + 1
            if not linea.strip():
                offset += tam
                continue
            try:
                a = Asiento.de_json(linea)
            except Exception as exc:
                if i == len(lineas) - 1:
                    log.warning(
                        "libro: ultima linea truncada, reparando (%s)", exc)
                    with self.ruta.open("r+b") as f:
                        f.truncate(offset)
                    return
                raise LibroCorrupto(f"linea {i + 1} ilegible: {exc}") from exc
            # Revalidar al cargar. `de_json` construye el dataclass y nada
            # mas: sin esto, una linea que NUNCA habria pasado por
            # `append` (otro escritor, una edicion a mano, una restauracion
            # de backup) entra al pliegue como si fuera un asiento sano —
            # p.ej. una cuenta de cristal mal tipeada, que abre un pool
            # fantasma con saldo vivo que nadie barre nunca. Es corrupcion,
            # y este modulo la mira en vez de ignorarla. Va DESPUES del
            # rescate de la ultima linea truncada, a proposito: un asiento
            # invalido es corrupcion siempre, aunque sea el ultimo, y
            # truncarlo seria borrar una linea de un libro append-only.
            try:
                a.validar()
            except AsientoInvalido as exc:
                raise LibroCorrupto(
                    f"linea {i + 1} invalida: {exc}") from exc
            esperado = len(self._asientos) + 1
            if a.seq != esperado:
                raise LibroCorrupto(f"seq {a.seq} en linea {i + 1}, esperaba {esperado}")
            self._asientos.append(a)
            offset += tam

    def asientos(self) -> list[Asiento]:
        return list(self._asientos)

    def append(self, **campos) -> Asiento:
        a = Asiento(seq=len(self._asientos) + 1, **campos)
        a.validar()
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(a.a_json() + "\n")
            f.flush()
        # copia de ida y vuelta por disco: aisla la memoria de cualquier
        # dict mutable (p.ej. detalle) que el llamador siga referenciando.
        a = Asiento.de_json(a.a_json())
        self._asientos.append(a)
        return a
