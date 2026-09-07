"""Las fuentes del abismo -- spec 2026-09-07, secciones 6-7.

Cada fuente devuelve una LISTA de sub-bloques (texto, anillo): una misma
fuente puede pescar profundidades distintas. Dependencias INYECTADAS (mem,
obtener, brief): este modulo no importa calipso.server jamas.
"""
from __future__ import annotations

import re

from calipso import chats
from calipso.abismo import anillos

CHATS_MAX_FRAGMENTOS = 8
CHATS_FRAGMENTO_CHARS = 200

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
    """Claves de busqueda: palabras de 4+ letras, en minusculas."""
    return set(re.findall(r"[0-9a-za-ÿ]{4,}", texto.lower()))


def chats_viejos(resto: str) -> list[tuple[str, int]]:
    """Busqueda lexica sobre chats.json, mas alla del historial del turno."""
    desde, hasta, palabras = _rango(resto)
    claves = _palabras(palabras)
    if not claves:
        return []
    hallados = []  # (ts, fragmento)
    for chat in chats.todos():
        titulo = (chat.get("title") or "?").strip()
        for msg in chat.get("messages", []):
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
