"""Junta ejemplos de COMO ESCRIBE Pedro, de sus mensajes reales, para darselos
al que redacta como muestra de su estilo. No es un modelo entrenado: son los
mensajes de Pedro tal cual, elegidos para que el que redacta imite su voz.

En el MVP la seleccion es simple -- los mas recientes, sin triviales -- que
alcanza para capturar sus habitos de superficie (sin tildes, muletillas, largo
de frase). La recuperacion semantica por registro es un refinamiento posterior.
"""

# Mensajes demasiado cortos o que son solo una orden no muestran su estilo.
_MIN_LARGO = 10


def _es_util(texto: str) -> bool:
    t = (texto or "").strip()
    if len(t) < _MIN_LARGO:
        return False
    if t.startswith("/"):        # una directiva (/nube, /redacta...) no es voz
        return False
    return True


def ejemplos_de_voz(chats_data: dict, n: int = 6) -> list[str]:
    """Hasta `n` mensajes reales de Pedro (role=="user") como ejemplos de su
    voz: los mas recientes primero por su `ts` real (no por posicion en el
    dict de chats), sin duplicados, sin triviales ni ordenes."""
    # recorrer todos los chats juntando (ts, texto) de los mensajes de Pedro.
    # un mensaje sin ts (dato viejo) usa "" y por eso queda al final al
    # ordenar descendente.
    mensajes: list[tuple[str, str]] = []
    for chat in (chats_data or {}).get("chats", {}).values():
        for m in chat.get("messages", []):
            if m.get("role") == "user" and _es_util(m.get("text", "")):
                mensajes.append((m.get("ts", ""), m["text"].strip()))
    # orden por recencia real (ts descendente); sort es estable, asi que los
    # empates (por ejemplo varios sin ts) mantienen su orden de aparicion.
    mensajes.sort(key=lambda par: par[0], reverse=True)
    # sin duplicados -- se queda con el primero, que es el mas reciente --
    # y tope n.
    vistos: set[str] = set()
    ej: list[str] = []
    for _, texto in mensajes:
        if texto not in vistos:
            vistos.add(texto)
            ej.append(texto)
            if len(ej) >= n:
                break
    return ej
