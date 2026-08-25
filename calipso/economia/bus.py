"""
calipso/economia/bus.py — El bus de propuestas.

Una propuesta declara que quiere hacer, cuanto pide y su criterio de
muerte ANTES de empezar (spec 7). Los eventos van a un JSONL propio
(no son asientos monetarios); la plata del trabajo vive en la cuenta
trabajo:<id> del libro, movida siempre via Kernel.
"""
from __future__ import annotations

import json
import pathlib

from . import capacidad as cap
from . import departamentos as deps
from .mercado import Mercado
from .tipos import Asiento, TipoAsiento

_CLAVES_CRITERIO = {"gasto_max_mm", "semanas_max"}


class ErrorBus(Exception):
    pass


def cuenta_trabajo(id: str) -> str:
    return f"trabajo:{id}"


class Bus:
    def __init__(self, ruta: pathlib.Path):
        self.ruta = pathlib.Path(ruta)
        self._eventos: list[dict] = []
        if self.ruta.exists():
            for linea in self.ruta.read_text(encoding="utf-8").splitlines():
                if linea.strip():
                    self._eventos.append(json.loads(linea))

    def _apilar(self, evento: dict) -> None:
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False,
                               separators=(",", ":")) + "\n")
            f.flush()
        self._eventos.append(evento)

    def alta(self, ts: str, semana: str, id: str, departamento_cuenta: str,
             titulo: str, presupuesto_mm: int, retorno_mm: int,
             criterio: dict) -> None:
        if any(e["id"] == id for e in self._eventos):
            raise ErrorBus(f"propuesta repetida: {id}")
        if not criterio or not set(criterio) <= _CLAVES_CRITERIO:
            raise ErrorBus(
                f"criterio de muerte invalido (claves {_CLAVES_CRITERIO}): "
                f"{criterio!r}")
        for clave, valor in criterio.items():
            if not (isinstance(valor, int) and not isinstance(valor, bool)
                    and valor > 0):
                raise ErrorBus(f"criterio con valor invalido: {clave}={valor!r}")
        if not (isinstance(presupuesto_mm, int) and not isinstance(presupuesto_mm, bool)
                and presupuesto_mm > 0):
            raise ErrorBus(
                f"presupuesto_mm debe ser entero positivo: {presupuesto_mm!r}")
        if not (isinstance(retorno_mm, int) and not isinstance(retorno_mm, bool)
                and retorno_mm > 0):
            raise ErrorBus(
                f"retorno_mm debe ser entero positivo: {retorno_mm!r}")
        self._apilar({"ts": ts, "semana": semana, "evento": "alta", "id": id,
                      "departamento": departamento_cuenta, "titulo": titulo,
                      "presupuesto_mm": presupuesto_mm,
                      "retorno_mm": retorno_mm, "criterio": criterio})

    def _eventos_de(self, id: str) -> list[dict]:
        eventos = [e for e in self._eventos if e["id"] == id]
        if not eventos:
            raise ErrorBus(f"propuesta inexistente: {id}")
        return eventos

    def estado(self, id: str) -> str:
        return self._eventos_de(id)[-1]["evento"]

    def datos(self, id: str) -> dict:
        eventos = self._eventos_de(id)
        d = dict(eventos[0])
        for e in eventos[1:]:
            if e["evento"] == "financiada" and "semana_financiada" not in d:
                d["semana_financiada"] = e["semana"]
        return d

    def ids(self) -> list[str]:
        return sorted({e["id"] for e in self._eventos})

    def activas(self) -> list[str]:
        return [i for i in self.ids() if self.estado(i) == "financiada"]

    def marcar(self, ts: str, semana: str, id: str, evento: str) -> None:
        self._eventos_de(id)  # debe existir
        self._apilar({"ts": ts, "semana": semana, "evento": evento, "id": id})


def financiar(mercado: Mercado, bus: Bus, ts: str, semana: str, id: str,
              financiador_cuenta: str, mm: int) -> Asiento:
    if bus.estado(id) not in ("alta", "financiada"):
        raise ErrorBus(f"propuesta no financiable en estado {bus.estado(id)}")
    asientos = mercado.k.libro.asientos()
    dueno = bus.datos(id)["departamento"]
    if deps.es_congelado(asientos, dueno):
        raise ErrorBus(
            f"financiar la propuesta de un congelado es rescatarlo: {dueno}")
    if deps.es_congelado(asientos, financiador_cuenta):
        raise ErrorBus(f"un congelado no financia: {financiador_cuenta}")
    a = mercado.k.transferir(ts, semana, financiador_cuenta,
                             cuenta_trabajo(id), mm, motivo="financiacion")
    if bus.estado(id) == "alta":
        bus.marcar(ts, semana, id, "financiada")
    return a


def aportes(asientos: list[Asiento], id: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for a in asientos:
        if (a.tipo is TipoAsiento.TRANSFERENCIA
                and a.destino == cuenta_trabajo(id)
                and a.detalle.get("motivo") == "financiacion"):
            out[a.origen] = out.get(a.origen, 0) + a.monto
    return out


def gastado(asientos: list[Asiento], id: str) -> int:
    cuenta = cuenta_trabajo(id)
    salidas = (TipoAsiento.TRANSFERENCIA, TipoAsiento.DESTRUCCION,
               TipoAsiento.EJECUCION_RESERVA)
    return sum(a.monto for a in asientos
               if a.tipo in salidas and a.origen == cuenta)


def semanas_transcurridas(semanas_ops: list[str], desde: str,
                          hasta: str) -> int:
    try:
        return semanas_ops.index(hasta) - semanas_ops.index(desde)
    except ValueError:
        raise ErrorBus(f"semana no operativa: {desde!r} o {hasta!r}") from None


def evaluar_y_liquidar_muertos(mercado: Mercado, bus: Bus, ts: str,
                               semana: str) -> list[str]:
    asientos = mercado.k.libro.asientos()
    ops = cap.semanas_operativas(asientos)
    muertos: list[str] = []
    for id in bus.activas():
        datos = bus.datos(id)
        criterio = datos["criterio"]
        gasto = gastado(asientos, id)
        muere = ("gasto_max_mm" in criterio
                 and gasto > criterio["gasto_max_mm"])
        if not muere and "semanas_max" in criterio:
            muere = semanas_transcurridas(
                ops, datos["semana_financiada"], semana) > criterio["semanas_max"]
        if not muere:
            continue
        bus.marcar(ts, semana, id, "muerta")
        cuenta = cuenta_trabajo(id)
        saldo = mercado.k.saldo(cuenta)
        aportado = aportes(asientos, id)
        total = sum(aportado.values())
        financiadores = sorted(aportado)
        devuelto = 0
        for i, fin in enumerate(financiadores):
            if i < len(financiadores) - 1:
                parte = saldo * aportado[fin] // total
            else:
                parte = saldo - devuelto  # el ultimo cierra la cuenta exacta
            if parte > 0:
                mercado.k.transferir(ts, semana, cuenta, fin, parte,
                                     motivo="liquidacion_trabajo")
                devuelto += parte
        bus.marcar(ts, semana, id, "liquidada")
        muertos.append(id)
    return muertos
