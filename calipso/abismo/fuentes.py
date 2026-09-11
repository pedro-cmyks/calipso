"""Las fuentes del abismo -- spec 2026-09-07, secciones 6-7.

Cada fuente devuelve una LISTA de sub-bloques (texto, anillo): una misma
fuente puede pescar profundidades distintas. Dependencias INYECTADAS (mem,
obtener, brief): este modulo no importa calipso.server jamas.
"""
from __future__ import annotations

import pathlib
import re
import sys

from calipso import chats, chronology, memoria_procedencia
from calipso.abismo import anillos

CHATS_MAX_FRAGMENTOS = 8
CHATS_FRAGMENTO_CHARS = 200

RECALL_N = 12
RECALL_TOP = 8
RECALL_UMBRAL = 0.20

_RANGO = re.compile(r"\b(desde|hasta):(\d{4}-\d{2})\b")


def _rango(resto: str) -> tuple[str | None, str | None, str]:
    """Extrae la mini-sintaxis desde:/hasta: (spec seccion 5). Lo que no
    parsea queda como palabras: sin interpretacion de fechas en lenguaje
    natural ("agosto" es una palabra, no un rango)."""
    desde = hasta = None
    for m in _RANGO.finditer(resto):
        if m.group(1) == "desde":
            desde = m.group(2)
        else:
            hasta = m.group(2)
    palabras = _RANGO.sub(" ", resto)
    return desde, hasta, " ".join(palabras.split())


def _palabras(texto: str) -> set[str]:
    """Claves de busqueda: palabras de 4+ letras, en minusculas.

    Clase solo-letras: a-z + acentuadas (à-öø-ÿ), sin el hueco ×/÷ (U+00D7,
    U+00F7) y sin el bloque de puntuacion U+0080-U+00BF (¡ ¿ « » ° etc). La
    version anterior, a-ÿ, colaba esa puntuacion como si fuera letra: una
    palabra pegada a un "¿" de apertura (rutina en espanol) no matcheaba
    nada -- "¿donde?" quedaba como {'¿donde'}, que no interseca {'donde'}.
    """
    return set(re.findall(r"[0-9a-zà-öø-ÿ]{4,}", texto.lower()))


def chats_viejos(resto: str, *, chat_activo: str | None = None,
                 en_contexto: int | None = 0) -> list[tuple[str, int]]:
    """Busqueda lexica sobre chats.json, mas alla del historial del turno.

    El chat ACTIVO se pesca solo por fuera de lo que el modelo ya tiene: sus
    ultimos `en_contexto` mensajes (la ventana del historial mas la pregunta
    actual, que ya esta persistida cuando la consulta corre) no entran al
    bloque. Pescarlos desplazaba a los chats viejos del tope de 8 y le
    devolvia al modelo su propia pregunta como "lo que subio". Lo anterior a
    esa ventana en el mismo chat si se pesca (spec seccion 1: "mas alla de
    los 12 mensajes de _HISTORY_TURNS"). Con `en_contexto=None` el activo
    queda fuera ENTERO: es lo que pide un turno /nube, donde la conversacion
    no viaja (Fase 2a, chat_id_nube=None) y el bloque no puede ser la puerta
    de atras de un turno local previo. Sin `chat_activo`, todo es viejo."""
    desde, hasta, palabras = _rango(resto)
    claves = _palabras(palabras)
    if not claves:
        return []
    hallados = []  # (ts, fragmento)
    for chat in chats.todos():
        titulo = (chat.get("title") or "?").strip()
        mensajes = chat.get("messages", [])
        if chat_activo is not None and chat.get("id") == chat_activo:
            if en_contexto is None:
                continue
            mensajes = mensajes[:len(mensajes) - max(0, en_contexto)]
        for msg in mensajes:
            texto = (msg.get("text") or "").strip()
            if not texto or texto.startswith("/"):
                continue  # los gestos no se pescan (la leccion de voz._es_util)
            ts = msg.get("ts") or ""
            mes = ts[:7]
            if desde and mes and mes < desde:
                continue
            if hasta and mes and mes > hasta:
                continue
            if not (_palabras(texto) & claves):
                continue
            frag = f"[{titulo} {ts[:10]}] {texto[:CHATS_FRAGMENTO_CHARS]}"
            hallados.append((ts, frag))
    hallados.sort(reverse=True)  # mas reciente primero
    return [(frag, anillos.MEDIA_AGUA)
            for _, frag in hallados[:CHATS_MAX_FRAGMENTOS]]


def _extracto(texto: str, pregunta: str, max_lineas: int = 12) -> str:
    """Lineas del texto que comparten alguna clave con la pregunta. La fuente
    puede LEER el core entero (sin el truncado a 3000 del turno); lo que entra
    al bloque son los renglones relevantes, no el archivo."""
    claves = _palabras(pregunta)
    if not claves:
        return ""
    lineas = [ln for ln in texto.splitlines()
              if not ln.startswith("#") and (_palabras(ln) & claves)]
    return "\n".join(lineas[:max_lineas])


def memoria(pregunta: str, mem, consolidado: str | None = None,
            zona_chat: str = "fabrica") -> list[tuple[str, int]]:
    """Recall dirigido + extractos de core/cronologia. El consolidado del
    libro personal conserva su frontera de zona (spec seccion 6 e invariante
    del spec de proyectos): solo en chats de zona personal."""
    bloques: list[tuple[str, int]] = []
    # con procedencia (spec 2026-09-11): presentar cada hit y recien ahi
    # cortar a RECALL_TOP, como en server._build_context. El techo del
    # bloque entero sigue siendo de `consulta.etiquetar`. `con_score=False`:
    # esta fuente nunca pego el score (solo cuenta en la variante off).
    recuerdos = memoria_procedencia.presentar_recuerdos(
        [h for h in mem.recall(pregunta, n=RECALL_N)
         if h.get("score", 0) >= RECALL_UMBRAL],
        RECALL_TOP, con_score=False)
    if recuerdos:
        lineas = "\n".join(r["text"] for r in recuerdos)
        bloques.append((f"recuerdos:\n{lineas}", anillos.MEDIA_AGUA))
    if (core := _extracto(mem.load_core(), pregunta)):
        bloques.append((f"del core:\n{core}", anillos.HONDO))
    # spec seccion 7: "la cronologia entera"; el techo de ABISMO_BLOQUE_MAX
    # acota el bloque resultante, no la lectura. chronology.load(limit=80)
    # por defecto -- lo forzamos a leer todo sin tocar chronology.py.
    crono = chronology.load(limit=sys.maxsize)
    lineas_crono = "\n".join(
        e["raw"] for e in crono["entries"]
        if _palabras(e.get("text", "")) & _palabras(pregunta))
    if lineas_crono:
        bloques.append((f"cronologia:\n{lineas_crono}", anillos.HONDO))
    if consolidado and zona_chat == "personal":
        bloques.append((f"libro personal (consolidado):\n{consolidado}",
                        anillos.HONDO))
    return bloques


def proyecto(resto: str, obtener, brief) -> list[tuple[str, int]]:
    """El detalle de un repo del catastro, sin mover ROOT (la logica de
    api_catastro_detalle, con el brief inyectado). v1: el primer token es el
    nombre; la pregunta extra se ignora y va el brief entero."""
    nombre = resto.split()[0]
    p = obtener(nombre)
    if p is None:
        raise ValueError(f"el proyecto {nombre!r} no esta en el catastro")
    texto = brief(pathlib.Path(p["ruta"]))
    return [(f"proyecto {nombre}:\n{texto}", anillos.ORILLA)]
