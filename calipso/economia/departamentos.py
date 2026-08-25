"""
calipso/economia/departamentos.py — Departamentos y su estado.

El registro guarda CONFIGURACION (zona y perillas de Pedro); el estado
congelado se deriva del libro, nunca se guarda: quiebra declarada en un
cierre congela, y solo un rescate firmado o una venta propia descongelan
(spec 5). El capital sin marca de rescate NO descongela: esa es la
decision de Pedro que el codigo protege.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass, asdict, replace

from .kernel import Kernel
from .tipos import Asiento, SubtipoAcunacion, TipoAsiento

ZONA_FABRICA = "fabrica"
ZONA_PERSONAL = "personal"


class ErrorDepartamento(Exception):
    pass


@dataclass(frozen=True)
class Departamento:
    nombre: str
    zona: str
    presupuesto_semanal_mm: int = 0
    techo_api_ciclo_mm: int = 0
    explorar_explotar_pct: int = 50
    agresividad_pct: int = 30

    def __post_init__(self):
        if self.zona not in (ZONA_FABRICA, ZONA_PERSONAL):
            raise ErrorDepartamento(f"zona invalida: {self.zona!r}")
        if not self.nombre or ":" in self.nombre:
            raise ErrorDepartamento(f"nombre invalido: {self.nombre!r}")

    @property
    def cuenta(self) -> str:
        prefijo = "dep" if self.zona == ZONA_FABRICA else "personal"
        return f"{prefijo}:{self.nombre}"


class Registro:
    def __init__(self, ruta: pathlib.Path):
        self.ruta = pathlib.Path(ruta)
        self._deps: dict[str, Departamento] = {}
        if self.ruta.exists():
            datos = json.loads(self.ruta.read_text(encoding="utf-8"))
            self._deps = {n: Departamento(**campos) for n, campos in datos.items()}

    def _guardar(self) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        datos = {n: asdict(d) for n, d in self._deps.items()}
        self.ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1),
                             encoding="utf-8")

    def alta(self, dep: Departamento) -> None:
        if dep.nombre in self._deps:
            raise ErrorDepartamento(f"departamento repetido: {dep.nombre}")
        self._deps[dep.nombre] = dep
        self._guardar()

    def obtener(self, nombre: str) -> Departamento:
        try:
            return self._deps[nombre]
        except KeyError:
            raise ErrorDepartamento(f"departamento inexistente: {nombre}") from None

    def todos(self) -> list[Departamento]:
        return list(self._deps.values())

    def ajustar(self, nombre: str, **perillas) -> Departamento:
        nuevo = replace(self.obtener(nombre), **perillas)
        self._deps[nombre] = nuevo
        self._guardar()
        return nuevo


def es_congelado(asientos: list[Asiento], cuenta: str) -> bool:
    congelado = False
    for a in asientos:
        if (a.tipo is TipoAsiento.APUNTE
                and a.detalle.get("nota") == "quiebra"
                and a.detalle.get("departamento") == cuenta):
            congelado = True
        elif (a.tipo is TipoAsiento.TRANSFERENCIA and a.destino == cuenta
                and a.detalle.get("rescate")):
            congelado = False
        elif (a.tipo is TipoAsiento.ACUNACION and a.destino == cuenta
                and a.subtipo == SubtipoAcunacion.VENTA.value):
            congelado = False
    return congelado


def declarar_quiebra(k: Kernel, ts: str, semana: str, cuenta: str) -> Asiento:
    return k.apuntar(ts, semana, 1,
                     {"nota": "quiebra", "departamento": cuenta})
