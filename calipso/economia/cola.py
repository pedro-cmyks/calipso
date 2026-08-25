"""
calipso/economia/cola.py — La cola de compuertas (spec 9).

Dos carriles: sesion acumula la semana y se ordena por monedas en juego;
goteo interrumpe con recargo y tope. El escrow se toma al encolar al tipo
vigente y el cobro real ocurre al servir (reloj). Una obligatoria sin
caja no se cae: se encola marcada para adelanto de direccion.
Las cartas del cierre entran sin escrow y su atencion queda registrada
para el cerrar_ciclo (cartas_atendidas / firmas).
"""
from __future__ import annotations

import json
import pathlib

from . import balances as bal
from . import departamentos as deps
from . import pt
from .kernel import Kernel
from .tipos import CUENTA_PEDRO, DIRECCION, Divisa, POOL_PT_FABRICA, TipoAsiento

CARRIL_SESION = "sesion"
CARRIL_GOTEO = "goteo"
RECARGO_GOTEO_PCT = 200
TOPE_GOTEO_SEMANAL = 2
_TIPOS = {"contacto", "publicacion", "gasto", "opinion"}


class ErrorCola(Exception):
    pass


def _redondear_mpt(mpt_real: int) -> int:
    return max(500, ((mpt_real + 499) // 500) * 500)


class Cola:
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

    def _de(self, id: str) -> list[dict]:
        ev = [e for e in self._eventos if e["id"] == id]
        if not ev:
            raise ErrorCola(f"item inexistente: {id}")
        return ev

    def estado(self, id: str) -> str:
        return self._de(id)[-1]["evento"]

    def datos(self, id: str) -> dict:
        return dict(self._de(id)[0])

    # -- encolado ----------------------------------------------------------
    def encolar(self, k: Kernel, ts: str, semana: str, id: str,
                departamento: str, titulo: str, tipo: str, obligatoria: bool,
                mpt_estimado: int, monedas_en_juego: int,
                carril: str = CARRIL_SESION) -> None:
        if any(e["id"] == id for e in self._eventos):
            raise ErrorCola(f"id repetido: {id}")
        if tipo not in _TIPOS:
            raise ErrorCola(f"tipo de compuerta invalido: {tipo!r}")
        if carril not in (CARRIL_SESION, CARRIL_GOTEO):
            raise ErrorCola(f"carril invalido: {carril!r}")
        if (not isinstance(mpt_estimado, int) or isinstance(mpt_estimado, bool)
                or mpt_estimado <= 0 or mpt_estimado % 500 != 0):
            raise ErrorCola(
                f"mpt_estimado debe ser multiplo positivo de 500: {mpt_estimado!r}")
        if carril == CARRIL_GOTEO:
            goteos = sum(1 for e in self._eventos
                         if e["evento"] == "encolada"
                         and e["carril"] == CARRIL_GOTEO
                         and e["semana"] == semana)
            if goteos >= TOPE_GOTEO_SEMANAL:
                raise ErrorCola(
                    f"tope de goteo semanal alcanzado ({TOPE_GOTEO_SEMANAL})")
        asientos = k.libro.asientos()
        tipo_mm = pt.tipo_de_cambio(asientos, semana)
        costo = mpt_estimado * tipo_mm // 1000
        if carril == CARRIL_GOTEO:
            costo = costo * RECARGO_GOTEO_PCT // 100
        congelado = deps.es_congelado(asientos, departamento)
        if congelado and not obligatoria:
            raise ErrorCola(
                f"un congelado no compra firmas opcionales: {departamento}")
        adelanto = False
        if congelado or k.disponible(departamento) < costo:
            if obligatoria:
                adelanto = True  # invariante 6: las obligatorias no se caen
            else:
                raise ErrorCola(
                    f"sin caja para la opcional: pide {costo}, "
                    f"disponible {k.disponible(departamento)}")
        # el evento se apila ANTES de la reserva: un crash entre ambos deja
        # una compuerta sin escrow (servir/expirar lo toleran), nunca una
        # reserva fantasma sin evento que la libere
        self._apilar({"ts": ts, "semana": semana, "evento": "encolada",
                      "id": id, "departamento": departamento,
                      "titulo": titulo, "tipo": tipo,
                      "obligatoria": obligatoria, "carril": carril,
                      "mpt_estimado": mpt_estimado, "tipo_mm": tipo_mm,
                      "monedas_en_juego": monedas_en_juego,
                      "adelanto": adelanto, "es_carta": False})
        if not adelanto:
            k.reservar(ts, semana, departamento, costo, ref=f"cola:{id}")

    def encolar_carta(self, ts: str, semana: str, id: str,
                      carta: dict) -> None:
        if any(e["id"] == id for e in self._eventos):
            return  # las cartas del cierre pueden re-emitirse: idempotente
        self._apilar({"ts": ts, "semana": semana, "evento": "encolada",
                      "id": id, "carta": carta, "es_carta": True,
                      "carril": CARRIL_SESION,
                      "monedas_en_juego": carta.get("monto", 0)})

    # -- lectura -----------------------------------------------------------
    def pendientes(self) -> list[dict]:
        out = []
        for e in self._eventos:
            if e["evento"] == "encolada" and self.estado(e["id"]) == "encolada":
                out.append(dict(e))
        return sorted(out, key=lambda e: (not e.get("es_carta", False),
                                          -e.get("monedas_en_juego", 0)))

    # -- resolucion --------------------------------------------------------
    def _liberar_si_reservada(self, k: Kernel, ts: str, semana: str,
                              id: str) -> None:
        # tolerante: libera solo si la reserva existe de verdad (un crash
        # entre el evento y la reserva, o un reintento, la dejan ausente)
        if f"cola:{id}" in bal.reservas_activas(k.libro.asientos()):
            k.liberar(ts, semana, ref=f"cola:{id}")

    def rechazar(self, k: Kernel, ts: str, semana: str, id: str) -> None:
        if self.estado(id) != "encolada":
            raise ErrorCola(f"no esta pendiente: {id}")
        self._liberar_si_reservada(k, ts, semana, id)
        self._apilar({"ts": ts, "semana": semana, "evento": "rechazada",
                      "id": id})

    def atender_carta(self, ts: str, semana: str, id: str,
                      firma: dict | None = None) -> None:
        if not self.datos(id).get("es_carta"):
            raise ErrorCola(f"no es una carta: {id}")
        if self.estado(id) != "encolada":
            raise ErrorCola(f"carta ya resuelta: {id}")
        self._apilar({"ts": ts, "semana": semana, "evento": "atendida",
                      "id": id, "firma": firma})

    def cartas_atendidas(self) -> frozenset:
        return frozenset(e["id"] for e in self._eventos
                         if e["evento"] == "atendida")

    def firmas(self) -> dict:
        return {e["id"]: e["firma"] for e in self._eventos
                if e["evento"] == "atendida" and e.get("firma")}

    def expirar_semana(self, k: Kernel, ts: str, semana: str) -> list[str]:
        out = []
        for e in list(self._eventos):
            if (e["evento"] == "encolada" and not e.get("es_carta")
                    and e["semana"] == semana
                    and self.estado(e["id"]) == "encolada"):
                self._liberar_si_reservada(k, ts, semana, e["id"])
                self._apilar({"ts": ts, "semana": semana,
                              "evento": "expirada", "id": e["id"]})
                out.append(e["id"])
        return out

    # -- servicio ------------------------------------------------------------
    def servir(self, mercado, ts: str, semana: str, id: str,
               mpt_real: int) -> dict:
        datos = self.datos(id)
        if datos.get("es_carta"):
            raise ErrorCola(f"las cartas se atienden, no se sirven: {id}")
        if self.estado(id) != "encolada":
            raise ErrorCola(f"no esta pendiente: {id}")
        if not isinstance(mpt_real, int) or isinstance(mpt_real, bool) \
                or mpt_real <= 0:
            raise ErrorCola(f"mpt_real debe ser entero positivo: {mpt_real!r}")
        k = mercado.k
        dep = datos["departamento"]
        ref = f"cola:{id}"
        mpt_cobrado = _redondear_mpt(mpt_real)
        cobro = mpt_cobrado * datos["tipo_mm"] // 1000
        if datos["carril"] == CARRIL_GOTEO:
            cobro = cobro * RECARGO_GOTEO_PCT // 100

        # estado real previo (reanudable tras crash a mitad de un intento)
        asientos = k.libro.asientos()
        ya_pagado = sum(a.monto for a in asientos
                        if a.tipo is TipoAsiento.TRANSFERENCIA
                        and a.destino == CUENTA_PEDRO and a.ref == ref)
        consumo_hecho = any(a.tipo is TipoAsiento.CONSUMO_PT and a.ref == ref
                            for a in asientos)
        reservas = bal.reservas_activas(asientos)
        monto_reservado = reservas[ref][1] if ref in reservas else 0
        pendiente = max(0, cobro - ya_pagado)
        disponible_total = k.disponible(dep) + monto_reservado
        del_dep = min(pendiente, disponible_total)
        faltante = pendiente - del_dep

        # PRE-VALIDACION antes del primer append (patron _pagar_pt):
        if not consumo_hecho and \
                k.saldo(POOL_PT_FABRICA, Divisa.PT) < mpt_cobrado:
            raise ErrorCola(
                f"pool de fabrica insuficiente: pide {mpt_cobrado}, "
                f"hay {k.saldo(POOL_PT_FABRICA, Divisa.PT)}")
        if faltante > 0 and datos["obligatoria"]:
            if k.disponible(DIRECCION) < faltante:
                raise ErrorCola(
                    f"direccion sin caja para el adelanto: {faltante}")
        elif faltante > 0:
            faltante = 0  # la opcional cobra hasta donde alcanza

        # escrituras, todas tolerantes a reintento
        self._liberar_si_reservada(k, ts, semana, id)
        if del_dep > 0:
            k.transferir(ts, semana, dep, CUENTA_PEDRO, del_dep,
                         motivo="firma_servida", ref=ref)
        if faltante > 0:
            k.transferir(ts, semana, DIRECCION, CUENTA_PEDRO, faltante,
                         motivo="carta_sistema", ref=ref)
            k.registrar_acreencia(ts, semana, DIRECCION, dep, faltante,
                                  ref=f"adelanto:{id}")
        if not consumo_hecho:
            pt.consumir_fabrica(k, ts, semana, mpt_cobrado, ref=ref,
                                pagador=dep)
        cobro_efectivo = ya_pagado + del_dep + faltante
        self._apilar({"ts": ts, "semana": semana, "evento": "servida",
                      "id": id, "mpt_real": mpt_real,
                      "mpt_cobrado": mpt_cobrado, "cobro_mm": cobro_efectivo})
        return {"mpt_cobrado": mpt_cobrado, "cobro_mm": cobro_efectivo,
                "adelantado_mm": faltante}
