"""Los anillos: la frontera determinista por profundidad (spec seccion 6).

El piso es de la FUENTE; el juez de calipso/privacidad solo puede hundir un
sub-bloque concreto (nunca subirlo), y se aplica ANTES de puede_viajar. La
clase credencial no es un anillo: corta el envio entero (regla del ruteo).
"""
from __future__ import annotations

ORILLA = 1      # detalle de proyectos/repos
MEDIA_AGUA = 2  # historial de chats, memoria episodica
HONDO = 3       # core curado, cronologia, lo humano-sensible

PISO_FUENTE = {"proyecto": ORILLA, "chats": MEDIA_AGUA, "memoria": MEDIA_AGUA}


def piso(fuente: str) -> int:
    """Fallo cerrado: fuente desconocida se trata como lo mas hondo."""
    return PISO_FUENTE.get(fuente, HONDO)


def puede_preguntar(anillo: int, consumidor: str) -> bool:
    """Rebanada 1: el unico consumidor cableado es el chat de Pedro."""
    return consumidor == "chat"


def puede_viajar(anillo: int, destino: str) -> bool:
    """Rebanada 1: la consulta no corre en turnos /nube (spec seccion 8),
    asi que a "nube" no viaja nada. La firma completa queda para que las
    rebanadas 2 y 4 implementen la politica (3 jamas; 1-2 redactados)."""
    return destino == "local"
