"""
calipso/mapa/pulso.py — La capa viva.

Un anillo de eventos en memoria donde cada agente que corre publica lo que
hace. Nada de esto se persiste y nada de esto es fuente de verdad: si el
pulso dice que un departamento gasto y el libro no lo tiene asentado, manda
el libro (invariante 5 del spec).

Este modulo NO es el bus de la economia (`calipso/economia/bus.py`, que
lleva las propuestas y si se persiste). Se lo llama siempre "el pulso".

El reloj entra inyectado para que un test pueda envejecer un agente diez
minutos sin dormir diez minutos.
"""
from __future__ import annotations

import contextlib
import threading
import time
from collections import deque

EVENTOS = ("inicio", "razonando", "herramienta", "tokens", "diff", "fin",
           "foco")
IDENTIDAD = ("departamento", "trabajo", "rol", "modelo")

POR_AGENTE = 200      # eventos que guarda cada agente
RECIENTES = 50        # agentes que se recuerdan
FLUJO = 500           # eventos que alcanza a recibir un cliente que llega tarde
INACTIVO_S = 600      # diez minutos sin publicar: el escritorio queda vacio


def _ultimo(eventos: list[dict], evento: str) -> dict | None:
    for e in reversed(eventos):
        if e["evento"] == evento:
            return e
    return None


def estado_de(eventos: list[dict], ahora: float,
              inactivo_s: float = INACTIVO_S) -> str:
    """razonando | esperando | liberado | inactivo.

    Un agente liberado se queda liberado por mas que pase el tiempo: que lo
    hayan soltado es una cosa distinta de que se haya colgado, y en el mapa
    se ven distinto (escritorio vacio con rastro contra escritorio mudo)."""
    if not eventos:
        return "esperando"
    ultimo = eventos[-1]
    if ultimo["evento"] == "fin":
        return "liberado"
    if ahora - ultimo["ts"] > inactivo_s:
        return "inactivo"
    if ultimo["evento"] in ("razonando", "herramienta"):
        return "razonando"
    return "esperando"


def _runtime_ms(eventos: list[dict]) -> int:
    fin = _ultimo(eventos, "fin")
    if fin is not None and fin.get("runtime_ms") is not None:
        return int(fin["runtime_ms"])
    if not eventos:
        return 0
    return round((eventos[-1]["ts"] - eventos[0]["ts"]) * 1000)


def resumen(eventos: list[dict], ahora: float,
            inactivo_s: float = INACTIVO_S) -> dict:
    """Lo que llena el popup del empleado."""
    tok = _ultimo(eventos, "tokens") or {}
    dif = _ultimo(eventos, "diff")
    return {
        "estado": estado_de(eventos, ahora, inactivo_s),
        "runtime_ms": _runtime_ms(eventos),
        # el evento `tokens` trae el acumulado, no el incremento: se toma el
        # ultimo, nunca la suma
        "tokens_in": tok.get("tokens_in", 0),
        "tokens_out": tok.get("tokens_out", 0),
        "costo_mm": tok.get("costo_mm", 0),
        "diff": {"ruta": dif["ruta"], "diff": dif["diff"]} if dif else None,
        "texto": "".join(e.get("texto", "") for e in eventos
                         if e["evento"] == "razonando"),
    }


class _Mango:
    """Lo que ve el codigo instrumentado. Agregar un punto nuevo al pulso
    tiene que ser una linea, no una refactorizacion."""

    def __init__(self, pulso: "Pulso", agente_id: str):
        self._pulso = pulso
        self._id = agente_id
        self.resultado = "ok"

    def razonando(self, texto: str) -> None:
        if texto:
            self._pulso.publicar(self._id, "razonando", texto=texto)

    def herramienta(self, nombre: str, resumen: str = "") -> None:
        self._pulso.publicar(self._id, "herramienta", nombre=nombre,
                             resumen=resumen)

    def tokens(self, tokens_in: int, tokens_out: int, costo_mm: int = 0) -> None:
        self._pulso.publicar(self._id, "tokens", tokens_in=tokens_in,
                             tokens_out=tokens_out, costo_mm=costo_mm)

    def diff(self, ruta: str, diff: str) -> None:
        self._pulso.publicar(self._id, "diff", ruta=ruta, diff=diff)


class Pulso:
    """Tres estructuras: los eventos de cada agente (para el popup), el
    orden de los agentes recientes (para saber a quien olvidar) y el flujo
    global (para el que se conecta y quiere ver lo que ya paso).

    Todo bajo un lock: los agentes publican desde hilos de trabajo
    (`asyncio.to_thread`) y el WebSocket lee desde el event loop."""

    def __init__(self, ahora=time.time, por_agente: int = POR_AGENTE,
                 recientes: int = RECIENTES, flujo: int = FLUJO,
                 inactivo_s: float = INACTIVO_S):
        self._ahora = ahora
        self._n = por_agente
        self._inactivo_s = inactivo_s
        self._por_agente: dict[str, deque] = {}
        self._orden: deque = deque(maxlen=recientes)
        self._flujo: deque = deque(maxlen=flujo)
        self._fichas: dict[str, dict] = {}
        self._seq = 0
        self._lock = threading.Lock()

    # -- publicar ----------------------------------------------------------
    def publicar(self, agente_id: str | None, evento: str, **campos) -> dict:
        if evento not in EVENTOS:
            raise ValueError(f"evento desconocido: {evento!r}")
        with self._lock:
            self._seq += 1
            ident = dict(self._fichas.get(agente_id, {})) if agente_id else {}
            for k in IDENTIDAD:
                valor = campos.pop(k, None)
                if valor is not None:
                    ident[k] = valor
            if agente_id:
                self._fichas[agente_id] = ident
            ev = {"seq": self._seq, "ts": round(self._ahora(), 3),
                  "agente_id": agente_id, "evento": evento,
                  "departamento": ident.get("departamento"),
                  "trabajo": ident.get("trabajo"),
                  "rol": ident.get("rol"), "modelo": ident.get("modelo"),
                  **campos}
            self._flujo.append(ev)
            if agente_id:
                anillo = self._por_agente.get(agente_id)
                if anillo is None:
                    # el agente entra: si el anillo de agentes esta lleno, el
                    # mas viejo se va con TODO lo suyo. Si no, los dos
                    # diccionarios crecen para siempre y el anillo no sirve
                    # de nada
                    if len(self._orden) == self._orden.maxlen:
                        viejo = self._orden[0]
                        self._por_agente.pop(viejo, None)
                        self._fichas.pop(viejo, None)
                    anillo = self._por_agente[agente_id] = deque(maxlen=self._n)
                    self._orden.append(agente_id)
                anillo.append(ev)
            return ev

    def enfocar(self, departamento: str) -> dict:
        """La camara mira para alla. Viaja por el mismo canal que el resto
        para que el cliente tenga un solo cursor y un solo reductor."""
        return self.publicar(None, "foco", departamento=departamento)

    @contextlib.contextmanager
    def agente(self, agente_id: str, departamento: str | None = None,
               trabajo: str | None = None, rol: str | None = None,
               modelo: str | None = None):
        arranque = self._ahora()
        self.publicar(agente_id, "inicio", departamento=departamento,
                      trabajo=trabajo, rol=rol, modelo=modelo)
        mango = _Mango(self, agente_id)
        try:
            yield mango
        except BaseException:
            mango.resultado = "error"
            raise
        finally:
            # el `fin` sale SIEMPRE: un agente que revienta y queda
            # razonando para siempre deja el escritorio ocupado por un
            # fantasma
            self.publicar(agente_id, "fin",
                          runtime_ms=round((self._ahora() - arranque) * 1000),
                          resultado=mango.resultado)

    # -- leer --------------------------------------------------------------
    def eventos(self, agente_id: str) -> list[dict]:
        with self._lock:
            return list(self._por_agente.get(agente_id, ()))

    def recientes(self) -> list[str]:
        """Del mas nuevo al mas viejo."""
        with self._lock:
            return list(reversed(self._orden))

    def desde(self, seq: int = 0) -> tuple[int, list[dict]]:
        """Lo que paso despues de `seq`, y el cursor nuevo.

        Si entre dos consultas pasaron mas eventos de los que el flujo
        guarda, los del medio se pierden: el pulso es efimero y el cliente
        se entera del estado igual por el proximo evento de cada agente."""
        with self._lock:
            return self._seq, [e for e in self._flujo if e["seq"] > seq]

    def empleados(self, departamento: str) -> list[dict]:
        """La vista derivada de la seccion 5: un escritorio por agente que el
        departamento tiene asignado ahora, el mas nuevo primero."""
        ahora = self._ahora()
        with self._lock:
            ids = [i for i in reversed(self._orden)
                   if self._fichas.get(i, {}).get("departamento") == departamento]
            datos = [(i, dict(self._fichas[i]), list(self._por_agente[i]))
                     for i in ids]
        salida = []
        for agente_id, ficha, eventos in datos:
            salida.append({"agente_id": agente_id, "rol": ficha.get("rol"),
                           "modelo": ficha.get("modelo"),
                           "trabajo": ficha.get("trabajo"),
                           **resumen(eventos, ahora, self._inactivo_s)})
        return salida


EL_PULSO = Pulso()
"""La instancia del proceso. El server publica y lee de esta; los tests se
arman la suya."""
