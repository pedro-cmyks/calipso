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

from .candado import escribir_json_atomico
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
    # Cuanto puede PEDIR este departamento en una ronda pre-seed, como
    # maximo, por pedido. No es plata: es autorizacion a pedirla. Lo que
    # sale del tesoro lo decide Pedro en la mesa, propuesta por propuesta.
    #
    # La perilla existe porque el monto no lo puede inventar el modelo: el
    # de 3b alucina numeros y aca los numeros gastan plata de verdad (ver
    # el docstring de `_contratar_para` en server.py). El jefe pide DENTRO
    # de este techo; lo que pida de mas se recorta a el.
    #
    # Nace en CERO, igual que `presupuesto_semanal_mm` y
    # `techo_api_ciclo_mm`: un departamento recien sembrado no puede pedir
    # hasta que Pedro diga cuanto, y no hay ningun default inventado en
    # ninguna capa. Cero significa "todavia no", no "sin limite".
    techo_preseed_mm: int = 0

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
        """Atomico: `escribir_json_atomico` y no `write_text`.

        `ajustar` lo hace alcanzable N veces desde http (una por toque de
        perilla), y `write_text` trunca en el lugar: una escritura cortada
        a la mitad deja departamentos.json invalido y con eso la economia
        entera sin cargar -- `/api/economia/config`, `/api/economia/tablero`
        y `/api/economia/bus` revientan las tres. Ver el docstring del
        helper."""
        datos = {n: asdict(d) for n, d in self._deps.items()}
        escribir_json_atomico(self.ruta, datos)

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
        """Cambia perillas de un departamento ya dado de alta, y guarda.

        Es la contra-cara de que la configuracion de la economia sea de
        ESCRITURA UNICA: `POST /api/economia/sembrar` escribe
        departamentos.json una sola vez y se niega a correr de nuevo, asi
        que sin esto cambiar un numero es editar el json a mano. Su
        llamador de produccion es
        `POST /api/economia/departamentos/{nombre}/perillas`.

        `replace` sobre el frozen dataclass hace que una perilla
        inexistente reviente con TypeError (no se escribe una clave que
        despues nadie lee) y que `__post_init__` vuelva a validar lo que
        cambio. El nombre y la zona NO son perillas: cambiarlos moveria la
        cuenta del departamento, y el libro es append-only -- los asientos
        viejos seguirian apuntando a la cuenta anterior. El endpoint solo
        deja pasar los campos numericos.
        """
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
