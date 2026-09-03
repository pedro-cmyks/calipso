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


def ejemplos_de_voz(chats_data: dict, guardados: list = (), n: int = 6) -> list[str]:
    """Hasta `n` ejemplos de la voz de Pedro. Los `guardados` (lo que trajo
    con /mia -- su voz de verdad) van PRIMERO, mas recientes por `ts`; el
    resto se rellena con sus mensajes de chat (role=="user", recientes, sin
    triviales ni ordenes). Sin duplicados. Sin `guardados` se comporta igual
    que antes: solo mensajes de chat."""
    ej: list[str] = []
    vistos: set[str] = set()

    # 1) los /mia primero, mas recientes por ts (sort estable: los empates
    #    mantienen su orden de aparicion).
    priori = sorted(
        (g for g in (guardados or []) if _es_util(g.get("texto", ""))),
        key=lambda g: g.get("ts", ""), reverse=True)
    for g in priori:
        t = g["texto"].strip()
        if t not in vistos:
            vistos.add(t)
            ej.append(t)
            if len(ej) >= n:
                return ej

    # 2) rellenar con los mensajes reales de Pedro de los chats, por recencia
    #    real (ts descendente). un mensaje sin ts (dato viejo) usa "" y queda
    #    al final.
    mensajes: list[tuple[str, str]] = []
    for chat in (chats_data or {}).get("chats", {}).values():
        for m in chat.get("messages", []):
            if m.get("role") == "user" and _es_util(m.get("text", "")):
                mensajes.append((m.get("ts", ""), m["text"].strip()))
    mensajes.sort(key=lambda par: par[0], reverse=True)
    for _, texto in mensajes:
        if texto not in vistos:
            vistos.add(texto)
            ej.append(texto)
            if len(ej) >= n:
                break
    return ej
