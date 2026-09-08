"""El filtro de la marca del abismo para el stream -- spec seccion 4.

Hermano del `Filtro` de calipso/mapa/foco.py: copia la idea (retener la cola
sospechosa hasta poder decidir) y NO la clase, porque las reglas divergen en
tres puntos que el spec declara:

1. El cuerpo va hasta 400 chars (el tope holgado de `marca.PATRON`, no los
   160 de `MAX_PREGUNTA`): el filtro retiene `len("⟦abismo:") + 400 + 1` y
   decide con `marca.parsear`. Retener solo 160 dejaria escapar cruda una
   marca de 200 chars, que `marca.py` quiso justamente atrapar como
   ilegible. Filtro y `marca.PATRON` juzgan igual QUE es una marca (cuerpo
   de 1 a 400 chars sin corchetes); `parsear` decide si es valida.
2. Una marca VALIDA corta: queda pendiente en `tomar_marca()` y lo que venga
   despues (el resto del trozo y los trozos siguientes hasta que la
   consuman) se descarta -- el modelo siguio escribiendo sin el contexto que
   pidio. Salvo que `puede_cortar()` diga que no (tope de consultas,
   fallback, orquestador): ahi la marca se retira con aviso y el texto
   posterior sigue saliendo (los dos regimenes del spec, a proposito).
3. `cerrar()` DESCARTA lo retenido con aviso, nunca lo vuelca crudo
   (divergencia deliberada de foco, spec seccion 11).

Sin marca en el stream, los bytes que salen son identicos a los que entraron
(invariante 3). El filtro es puro: no hace I/O; los avisos se acumulan en
`tomar_avisos()` y el Emisor los lleva a telemetry -- sin el cuerpo de la
marca, que no se persiste en ningun lado.
"""
from __future__ import annotations

from typing import Callable

from calipso.abismo import marca

ABRE = marca.ABRE + "abismo:"
CIERRA = marca.CIERRA
CUERPO_MAX = 400                              # el tope holgado de marca.PATRON
RETENCION_MAX = len(ABRE) + CUERPO_MAX + 1    # con esto a la vista ya decide


def _retenible(texto: str) -> int:
    """Cuantos caracteres del final pueden ser el principio de ABRE."""
    for k in range(min(len(texto), len(ABRE) - 1), 0, -1):
        if ABRE.startswith(texto[-k:]):
            return k
    return 0


def _es_cuerpo_de_marca(cuerpo: str) -> bool:
    """El mismo juicio que `marca.PATRON`: de 1 a 400 chars sin corchetes."""
    return (1 <= len(cuerpo) <= CUERPO_MAX
            and marca.ABRE not in cuerpo and CIERRA not in cuerpo)


class FiltroAbismo:
    """Uno por turno. No es reentrante y no se comparte entre conexiones."""

    def __init__(self, puede_cortar: Callable[[], bool] = lambda: True):
        self._puede_cortar = puede_cortar
        self._resto = ""
        self._marca: marca.Marca | None = None
        self._avisos: list[dict] = []

    def comer(self, trozo: str) -> str:
        """Devuelve el texto visible del trozo; deja la marca valida pendiente."""
        if self._marca is not None:
            return ""       # ya corto: lo posterior se descarta hasta tomar_marca()
        buf = self._resto + trozo
        self._resto = ""
        visible: list[str] = []
        while buf:
            i = buf.find(ABRE)
            if i < 0:
                k = _retenible(buf)
                visible.append(buf[:len(buf) - k] if k else buf)
                self._resto = buf[len(buf) - k:] if k else ""
                break
            visible.append(buf[:i])
            j = buf.find(CIERRA, i + len(ABRE))
            if j < 0:
                if len(buf) - i >= RETENCION_MAX:
                    # con RETENCION_MAX chars a la vista ya se sabe: abrio y
                    # no cerro en un cuerpo plausible, era texto
                    visible.append(buf[i:i + len(ABRE)])
                    buf = buf[i + len(ABRE):]
                    continue
                self._resto = buf[i:]
                break
            cuerpo = buf[i + len(ABRE):j]
            if not _es_cuerpo_de_marca(cuerpo):
                # cerro, pero PATRON tampoco lo tomaria por marca: era texto
                visible.append(buf[i:i + len(ABRE)])
                buf = buf[i + len(ABRE):]
                continue
            m = marca.parsear(cuerpo)
            buf = buf[j + len(CIERRA):]
            if m is None:
                self._avisos.append({"clase": "ilegible", "largo": len(cuerpo)})
                continue
            if not self._puede_cortar():
                self._avisos.append({"clase": "sin_corte", "fuente": m.fuente,
                                     "largo": len(cuerpo)})
                continue
            self._marca = m
            break           # lo que quedaba en buf vino sin contexto: se descarta
        return "".join(visible)

    def cerrar(self) -> str:
        """Una marca abierta al final del stream (lo retenido ya empezo con
        `⟦abismo:`) se descarta con aviso, jamas se vuelca cruda (spec
        seccion 11). Un prefijo suelto (`⟦`, `⟦abi`) todavia no es marca: es
        texto y Pedro tiene que verlo, igual que con foco (invariante 3)."""
        resto, self._resto = self._resto, ""
        if not resto:
            return ""
        if resto.startswith(ABRE):
            self._avisos.append({"clase": "abierta", "largo": len(resto)})
            return ""
        return resto

    def tomar_marca(self) -> marca.Marca | None:
        """La marca valida pendiente, consumida: el filtro vuelve a dejar
        pasar texto (la continuacion de la reentrada)."""
        m, self._marca = self._marca, None
        return m

    def tomar_avisos(self) -> list[dict]:
        avisos, self._avisos = self._avisos, []
        return avisos
