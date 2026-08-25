"""
calipso/economia/libro.py — Persistencia append-only del libro contable.

Una linea JSON por asiento. Nunca se edita ni borra una linea; todo estado
se deriva plegando los asientos. La carga tolera exactamente un defecto:
la ultima linea truncada (corte a mitad de un append). Cualquier otra
corrupcion levanta LibroCorrupto: eso se mira, no se ignora.
"""
from __future__ import annotations

import logging
import pathlib

from .tipos import Asiento

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
        lineas = self.ruta.read_text(encoding="utf-8").splitlines()
        for i, linea in enumerate(lineas):
            if not linea.strip():
                continue
            try:
                a = Asiento.de_json(linea)
            except Exception as exc:
                if i == len(lineas) - 1:
                    log.warning("libro: ultima linea truncada ignorada (%s)", exc)
                    return
                raise LibroCorrupto(f"linea {i + 1} ilegible: {exc}") from exc
            esperado = len(self._asientos) + 1
            if a.seq != esperado:
                raise LibroCorrupto(f"seq {a.seq} en linea {i + 1}, esperaba {esperado}")
            self._asientos.append(a)

    def asientos(self) -> list[Asiento]:
        return list(self._asientos)

    def append(self, **campos) -> Asiento:
        a = Asiento(seq=len(self._asientos) + 1, **campos)
        a.validar()
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(a.a_json() + "\n")
            f.flush()
        self._asientos.append(a)
        return a
