"""
calipso/economia/reloj.py — La frontera de entrada del tiempo (spec 9).

El clock-out es el evento que dispara el cobro: fabrica sirve la compuerta
con el tiempo real medido, personal consume la reserva de PT, empleo y
tuning solo registran. Un tramo huerfano jamas inventa duracion: se
concilia con minutos declarados por Pedro y sin cobro.
Determinista: los ts son parametros; los minutos salen de restar ISO.
"""
from __future__ import annotations

import datetime
import json
import pathlib

from . import pt
from .cola import Cola, ErrorCola
from .tipos import Divisa, POOL_PT_PERSONAL

CATEGORIAS = {"fabrica", "personal", "empleo", "tuning"}


class ErrorReloj(Exception):
    pass


def _minutos(ts_in: str, ts_out: str) -> int:
    a = datetime.datetime.fromisoformat(ts_in)
    b = datetime.datetime.fromisoformat(ts_out)
    return int((b - a).total_seconds()) // 60


class Reloj:
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

    def abierto(self) -> dict | None:
        abiertos = [e for e in self._eventos if e["evento"] == "in"]
        cerrados = {e["ts_in"] for e in self._eventos
                    if e["evento"] in ("out", "conciliado")}
        pend = [e for e in abiertos if e["ts"] not in cerrados]
        return dict(pend[-1]) if pend else None

    def clock_in(self, ts: str, semana: str, categoria: str,
                 ref: str | None = None, cola: Cola | None = None) -> None:
        if categoria not in CATEGORIAS:
            raise ErrorReloj(f"categoria invalida: {categoria!r}")
        if categoria == "fabrica":
            if not ref or cola is None:
                raise ErrorReloj(
                    "fabrica exige ref (id de compuerta) y la cola para validarlo")
            try:
                datos = cola.datos(ref)
            except ErrorCola:
                raise ErrorReloj(f"compuerta inexistente: {ref}") from None
            if datos.get("es_carta") or cola.estado(ref) != "encolada":
                raise ErrorReloj(f"la compuerta no esta pendiente: {ref}")
        if categoria == "personal" and not (ref or "").startswith("personal:"):
            raise ErrorReloj("personal exige ref personal:<departamento>")
        if self.abierto():
            raise ErrorReloj("ya hay un tramo abierto: clock_out primero")
        self._apilar({"ts": ts, "semana": semana, "evento": "in",
                      "categoria": categoria, "ref": ref})

    def clock_out(self, mercado, cola: Cola, ts: str, semana: str) -> dict:
        tramo = self.abierto()
        if not tramo:
            raise ErrorReloj("no hay tramo abierto")
        minutos = _minutos(tramo["ts"], ts)
        if minutos <= 0:
            raise ErrorReloj(f"duracion invalida: {minutos} minutos")
        mpt_real = minutos * 1000 // 60
        categoria = tramo["categoria"]
        error_cobro = None
        desborde = 0
        try:
            if categoria == "fabrica":
                cola.servir(mercado, ts, semana, tramo["ref"], mpt_real)
            elif categoria == "personal":
                disponible_pt = mercado.k.saldo(POOL_PT_PERSONAL, Divisa.PT)
                consumible = min(disponible_pt, mpt_real)
                if consumible <= 0:
                    raise pt.ErrorPT("reserva personal agotada")
                tipo = pt.tipo_de_cambio(mercado.k.libro.asientos(), semana)
                pt.consumir_personal(mercado.k, ts, semana, consumible,
                                     departamento=tramo["ref"],
                                     tipo_vigente_mm=tipo)
                if consumible < mpt_real:
                    desborde = mpt_real - consumible
        except (ErrorCola, pt.ErrorPT) as exc:
            # el tiempo queda registrado; el cobro fallido no atasca el reloj
            error_cobro = str(exc)
        evento = {"ts": ts, "semana": semana, "evento": "out",
                  "ts_in": tramo["ts"], "categoria": categoria,
                  "minutos": minutos}
        if error_cobro:
            evento["sin_cobro"] = True
            evento["error"] = error_cobro
        if desborde:
            evento["desborde_mpt"] = desborde
        self._apilar(evento)
        return {"minutos": minutos, "mpt_real": mpt_real,
                "categoria": categoria, "sin_cobro": bool(error_cobro),
                "desborde_mpt": desborde}

    def huerfanos(self, semana_actual: str) -> list[dict]:
        tramo = self.abierto()
        if tramo and tramo["semana"] < semana_actual:
            return [dict(tramo)]
        return []

    def conciliar(self, ts: str, semana: str, ts_in: str,
                  minutos: int) -> None:
        if not isinstance(minutos, int) or isinstance(minutos, bool) \
                or minutos <= 0:
            raise ErrorReloj(f"minutos debe ser entero positivo: {minutos!r}")
        tramo = self.abierto()
        if not tramo or tramo["ts"] != ts_in:
            raise ErrorReloj(f"no hay tramo abierto con ts {ts_in}")
        self._apilar({"ts": ts, "semana": semana, "evento": "conciliado",
                      "ts_in": ts_in, "categoria": tramo["categoria"],
                      "minutos": minutos})

    def minutos_por_categoria(self, semanas: list[str]) -> dict[str, int]:
        out: dict[str, int] = {}
        ins = {e["ts"]: e for e in self._eventos if e["evento"] == "in"}
        for e in self._eventos:
            if e["evento"] in ("out", "conciliado"):
                origen = ins.get(e["ts_in"])
                if origen and origen["semana"] in semanas:
                    cat = e["categoria"]
                    out[cat] = out.get(cat, 0) + e["minutos"]
        return out
