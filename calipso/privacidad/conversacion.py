"""El mapa de marcadores de una conversacion. Los marcadores de redaccion
tienen que ser estables entre turnos (el mismo valor real -> el mismo
marcador) para que la nube no pierda el hilo. Este modulo guarda un
MapaMarcadores por chat_id, vivo lo que dura el proceso del servidor.

No persiste a disco: un marcador tapa un valor solo en el trafico de salida;
no hay razon para guardarlo entre reinicios.
"""
from calipso.privacidad.redaccion import MapaMarcadores

_por_chat: dict[str, MapaMarcadores] = {}


def mapa_para(chat_id: str | None) -> MapaMarcadores:
    """El MapaMarcadores de una conversacion. Mismo chat_id -> mismo mapa.
    chat_id None (sin conversacion) devuelve uno nuevo, sin cachear."""
    if chat_id is None:
        return MapaMarcadores()
    if chat_id not in _por_chat:
        _por_chat[chat_id] = MapaMarcadores()
    return _por_chat[chat_id]


def olvidar(chat_id: str) -> None:
    """Descarta el mapa de una conversacion (p.ej. al borrarla)."""
    _por_chat.pop(chat_id, None)
