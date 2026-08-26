"""
calipso/mapa/foco.py — La marca de control, sacada del texto que Pedro lee.

Calipso emite `⟦foco:atlas⟧` cuando la conversacion pasa a tratar de un
departamento. La marca no se ve: este filtro la retira del stream y la
convierte en un foco para la camara (spec seccion 8).

El stream llega partido en trozos arbitrarios y la marca puede quedar
cortada en cualquier lado, asi que el filtro RETIENE la cola sospechosa
hasta poder decidir. `cerrar()` devuelve lo retenido: una marca que nunca
cierra es texto, y tragarsela seria comerse el final de la respuesta.
"""
from __future__ import annotations

import re

ABRE = "⟦foco:"
CIERRA = "⟧"
MAX_NOMBRE = 60      # mas largo que esto no es un departamento, es texto


def _retenible(texto: str) -> int:
    """Cuantos caracteres del final pueden ser el principio de la marca."""
    for k in range(min(len(texto), len(ABRE) - 1), 0, -1):
        if ABRE.startswith(texto[-k:]):
            return k
    return 0


class Filtro:
    """Uno por turno. No es reentrante y no se comparte entre conexiones."""

    def __init__(self):
        self._resto = ""
        self._focos: list[str] = []

    def comer(self, trozo: str) -> str:
        """Devuelve el texto visible del trozo; guarda los focos que vio."""
        buf = self._resto + trozo
        self._resto = ""
        visible = []
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
                if len(buf) - i > len(ABRE) + MAX_NOMBRE:
                    # abrio y no cerro en un nombre plausible: era texto
                    visible.append(buf[i:i + len(ABRE)])
                    buf = buf[i + len(ABRE):]
                    continue
                self._resto = buf[i:]
                break
            if j - (i + len(ABRE)) > MAX_NOMBRE:
                # cerro, pero con un nombre que ningun departamento tiene:
                # era texto, y `limpiar` lo juzga igual
                visible.append(buf[i:i + len(ABRE)])
                buf = buf[i + len(ABRE):]
                continue
            nombre = buf[i + len(ABRE):j].strip()
            if nombre:
                self._focos.append(nombre)
            buf = buf[j + len(CIERRA):]
        return "".join(visible)

    def cerrar(self) -> str:
        resto, self._resto = self._resto, ""
        return resto

    def tomar_focos(self) -> list[str]:
        """Los consume: la camara no tiene que volar dos veces por lo mismo."""
        focos, self._focos = self._focos, []
        return focos


# el mismo juicio que el Filtro, tope de nombre incluido: si los dos no
# coinciden en que es una marca, uno de los dos se come texto visible
_MARCA = re.compile(re.escape(ABRE) + "[^" + re.escape(CIERRA) + "]{0,"
                    + str(MAX_NOMBRE) + "}" + re.escape(CIERRA))


def limpiar(texto: str) -> str:
    """Saca las marcas COMPLETAS de un texto que ya llego entero.

    El `Filtro` es para un stream partido en trozos; esto es para un
    acumulado que se remanda entero cada tanto (el `partial` de la ruta de
    suscripcion). Sin estado y sin retencion: una marca a medio llegar se
    limpia sola en el envio siguiente."""
    return _MARCA.sub("", texto or "")
