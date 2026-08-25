"""
calipso/economia/pagador.py — El adaptador de cobro para dispatch.

Todo request lleva cuenta pagadora (spec 11). El pagador convierte uso
real (tokens de API, requests de suscripcion) en asientos via Mercado.
Nunca rompe el flujo del dispatch: un cargo que no puede aplicarse queda
en cargos_pendientes.jsonl y se reintenta desde la operacion.
El uso personal de API queda fuera del libro de la fabrica (lo lleva
calipso/costs.py); la cuenta personal de suscripcion va contra la
reserva personal. Este modulo es FRONTERA: sus llamadores estampan
ts/semana reales.
"""
from __future__ import annotations

import json
import pathlib
import sys

from . import departamentos as deps
from .bus import Bus, ErrorBus
from .candado import candado
from .capacidad import ErrorCapacidad, Suscripcion
from .kernel import Kernel, OperacionInvalida
from .libro import Libro
from .mercado import ErrorMercado, Mercado

PRECIOS_API_MM_POR_MTOK = {"deepseek-chat": (270, 1100)}
PRECIO_DESCONOCIDO = (3000, 15000)  # conservador

_ERRORES_ECONOMICOS = (ErrorMercado, ErrorCapacidad, ErrorBus,
                       OperacionInvalida)


class Pagador:
    """Sin estado cacheado: solo rutas. Cada cobro toma el candado y
    construye un Mercado fresco adentro — escritor unico de verdad."""

    def __init__(self, eco: pathlib.Path):
        self.eco = pathlib.Path(eco)
        self.ruta_libro = self.eco / "libro.jsonl"
        self.ruta_registro = self.eco / "departamentos.json"
        self.ruta_sus = self.eco / "suscripciones.json"
        self.ruta_bus = self.eco / "bus.jsonl"
        self.ruta_pendientes = self.eco / "cargos_pendientes.jsonl"

    @staticmethod
    def desde_entorno(base: pathlib.Path | None = None) -> "Pagador | None":
        raiz = pathlib.Path(base) if base else \
            pathlib.Path(pathlib.Path.home() / ".calipso")
        p = Pagador(raiz / "economia")
        if not (p.ruta_libro.exists() and p.ruta_registro.exists()
                and p.ruta_sus.exists()):
            return None
        return p

    # -- construccion fresca (llamar BAJO candado para escribir) -----------
    def mercado_fresco(self) -> Mercado:
        datos = json.loads(self.ruta_sus.read_text(encoding="utf-8"))
        suscripciones = {n: Suscripcion(**c) for n, c in datos.items()}
        return Mercado(Kernel(Libro(self.ruta_libro)),
                       deps.Registro(self.ruta_registro), suscripciones)

    def leer_kernel(self) -> Kernel:
        return Kernel(Libro(self.ruta_libro))

    # -- pendientes --------------------------------------------------------
    def _reescribir_pendientes(self, cargos: list[dict]) -> None:
        contenido = "".join(json.dumps(c, ensure_ascii=False,
                                       separators=(",", ":")) + "\n"
                            for c in cargos)
        self.ruta_pendientes.parent.mkdir(parents=True, exist_ok=True)
        self.ruta_pendientes.write_text(contenido, encoding="utf-8")

    def _apilar_pendiente(self, cargo: dict) -> None:
        self._reescribir_pendientes(self.pendientes() + [cargo])
        print(f"[pagador] cargo pendiente: {cargo.get('tipo')} "
              f"{cargo.get('cuenta')}", file=sys.stderr)

    def pendientes(self) -> list[dict]:
        if not self.ruta_pendientes.exists():
            return []
        return [json.loads(l) for l in
                self.ruta_pendientes.read_text(encoding="utf-8").splitlines()
                if l.strip()]

    def reintentar_pendientes(self) -> int:
        aplicados = 0
        with candado(self.ruta_libro):
            quedan = self.pendientes()
            i = 0
            while i < len(quedan):
                try:
                    self._aplicar(quedan[i])
                except _ERRORES_ECONOMICOS:
                    i += 1
                    continue
                except Exception as exc:  # cargo malformado: conservar
                    print(f"[pagador] cargo ilegible: {exc}", file=sys.stderr)
                    i += 1
                    continue
                del quedan[i]
                self._reescribir_pendientes(quedan)  # tras CADA aplicado
                aplicados += 1
        return aplicados

    # -- cargos ------------------------------------------------------------
    def _dueno_de(self, cuenta: str) -> str:
        if not self.ruta_bus.exists():
            raise ErrorBus(f"sin bus para resolver el dueno de {cuenta}")
        id_trabajo = cuenta.split(":", 1)[1]
        return Bus(self.ruta_bus).datos(id_trabajo)["departamento"]

    def _aplicar(self, cargo: dict) -> None:
        m = self.mercado_fresco()  # relee el libro bajo el candado
        cuenta = cargo["cuenta"]
        dueno = self._dueno_de(cuenta) if cuenta.startswith("trabajo:") else None
        if cargo["tipo"] == "api":
            m.gastar_api(cargo["ts"], cargo["semana"], cuenta, cargo["mm"],
                         dueno=dueno)
        elif cuenta == "personal":
            m.usar_reserva_personal(cargo["ts"], cargo["semana"],
                                    cargo["suscripcion"], cargo["unidades"],
                                    "personal:finanzas")
        else:
            m.comprar_capacidad(cargo["ts"], cargo["semana"], cuenta,
                                cargo["suscripcion"], cargo["unidades"],
                                dueno=dueno)

    def _cobrar(self, cargo: dict) -> None:
        with candado(self.ruta_libro):
            try:
                self._aplicar(cargo)
            except _ERRORES_ECONOMICOS:
                self._apilar_pendiente(cargo)

    def cargar_api(self, ts: str, semana: str, cuenta: str, modelo: str,
                   prompt_tokens: int, completion_tokens: int) -> int | None:
        if cuenta == "personal" or cuenta.startswith("personal:"):
            return None  # fuera del libro de la fabrica (costs.py lo lleva)
        pin, pout = PRECIOS_API_MM_POR_MTOK.get(modelo, PRECIO_DESCONOCIDO)
        mm = -(-(prompt_tokens * pin + completion_tokens * pout) // 1_000_000)
        if mm <= 0:
            # un request sin usage medible no consumió nada facturable; no
            # se genera cargo (evitar un pendiente estructuralmente eterno)
            return 0
        self._cobrar({"ts": ts, "semana": semana, "tipo": "api",
                      "cuenta": cuenta, "mm": mm, "modelo": modelo})
        return mm

    def cargar_suscripcion(self, ts: str, semana: str, cuenta: str,
                           suscripcion: str, unidades: int = 1) -> None:
        self._cobrar({"ts": ts, "semana": semana, "tipo": "suscripcion",
                      "cuenta": cuenta, "suscripcion": suscripcion,
                      "unidades": unidades})
