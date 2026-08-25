"""
calipso/economia/personal.py — Los libros personales y el tablero.

Los libros personales son PRIVADOS (invariante 11): finanzas del mundo
real de Pedro, en su propio JSONL, fuera del libro de la fabrica. El
tablero es un LECTOR que consolida — jamas escribe.
"""
from __future__ import annotations

import json
import pathlib

from . import capacidad as cap
from . import departamentos as deps
from . import pt
from .kernel import Kernel
from .tipos import CUENTA_PEDRO, DIRECCION, TESORO, TipoAsiento

SUELDO_MENSUAL_MM = 2_500_000


class ErrorPersonal(Exception):
    pass


class LibroPersonal:
    def __init__(self, ruta: pathlib.Path):
        self.ruta = pathlib.Path(ruta)
        self._eventos: list[dict] = []
        if self.ruta.exists():
            for linea in self.ruta.read_text(encoding="utf-8").splitlines():
                if linea.strip():
                    self._eventos.append(json.loads(linea))

    def registrar(self, ts: str, semana: str, tipo: str, monto_mm: int,
                  categoria: str, nota: str = "") -> None:
        if tipo not in ("ingreso", "gasto"):
            raise ErrorPersonal(f"tipo invalido: {tipo!r}")
        if not isinstance(monto_mm, int) or isinstance(monto_mm, bool) \
                or monto_mm <= 0:
            raise ErrorPersonal(f"monto_mm debe ser entero positivo: {monto_mm!r}")
        evento = {"ts": ts, "semana": semana, "tipo": tipo,
                  "monto_mm": monto_mm, "categoria": categoria, "nota": nota}
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        with self.ruta.open("a", encoding="utf-8") as f:
            f.write(json.dumps(evento, ensure_ascii=False,
                               separators=(",", ":")) + "\n")
            f.flush()
        self._eventos.append(evento)

    def resumen(self, semanas: list[str] | None = None) -> dict:
        ing = gas = 0
        for e in self._eventos:
            if semanas is not None and e["semana"] not in semanas:
                continue
            if e["tipo"] == "ingreso":
                ing += e["monto_mm"]
            else:
                gas += e["monto_mm"]
        return {"ingresos_mm": ing, "gastos_mm": gas, "neto_mm": ing - gas}


def linea_empleo_mm_por_hora(sueldo_mm: int, minutos_empleo: int) -> int:
    if minutos_empleo <= 0:
        return sueldo_mm // 173  # teorica: ~40 h/semana
    return sueldo_mm * 60 // minutos_empleo


def tablero(k: Kernel, registro: deps.Registro, suscripciones: dict,
            reloj, libro_personal: LibroPersonal, semana: str) -> dict:
    asientos = k.libro.asientos()
    ops = cap.semanas_operativas(asientos)
    minutos = reloj.minutos_por_categoria(ops[-4:]) if ops else {}
    reserva_usada = {nombre: cap.consumo_personal(asientos, nombre, ops[-4:])
                     for nombre in suscripciones} if ops else {}
    ventana = ops[-4:] if ops else None
    costo_op = sum(a.monto for a in asientos
                   if a.tipo is TipoAsiento.APUNTE
                   and a.detalle.get("nota") == "costo_oportunidad"
                   and (ventana is None or a.semana in ventana))
    return {
        "tesoro_mm": k.saldo(TESORO),
        "direccion_mm": k.saldo(DIRECCION),
        "cuenta_pedro_mm": k.saldo(CUENTA_PEDRO),
        "tipo_cambio_mm": pt.tipo_de_cambio(asientos, semana) if ops else 5_000,
        "linea_empleo_mm": linea_empleo_mm_por_hora(
            SUELDO_MENSUAL_MM, minutos.get("empleo", 0)),
        "departamentos": {
            d.cuenta: {"saldo_mm": k.saldo(d.cuenta),
                       "congelado": deps.es_congelado(asientos, d.cuenta)}
            for d in registro.todos()},
        "reserva_personal_usada": reserva_usada,
        "costo_oportunidad_mm": costo_op,
        "personal": libro_personal.resumen(),
    }
