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
    """La politica de la columna "Viaje a la nube" (spec seccion 6, enmienda
    2026-09-08): destino local deja pasar todo; a la nube viajan la orilla y
    media agua (redactados despues por el juez, en viaje.py) y lo hondo
    JAMAS, ni tapado. Un destino desconocido no deja pasar nada."""
    if destino == "local":
        return True
    if destino == "nube":
        return anillo in (ORILLA, MEDIA_AGUA)
    return False
