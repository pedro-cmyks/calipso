"""El resolvedor de la consulta -- spec 2026-09-07, seccion 4.

100% local siempre (invariante 1). Fallo cerrado: una consulta jamas rompe
una respuesta (invariante 4) -- toda excepcion degrada a estado "fallo" y el
turno sigue sin contexto extra.
"""
from __future__ import annotations

import os

from calipso.abismo import fuentes, marca


def _entero_env(nombre: str, defecto: int) -> int:
    """Un env mal tipeado no puede impedir que arranque el server: desde el
    1b este modulo esta en la cadena de import de calipso/server.py."""
    try:
        return int(os.environ.get(nombre, defecto))
    except (TypeError, ValueError):
        return defecto


ABISMO_BLOQUE_MAX = _entero_env("ABISMO_BLOQUE_MAX", 2000)


def etiquetar(fuente: str, bloques: list[tuple[str, int]]) -> str:
    """El bloque etiquetado (encabezado con la fuente, `[anillo N]` por
    sub-bloque, todo bajo ABISMO_BLOQUE_MAX). Vive aca, junto al techo, y lo
    usan los DOS que arman bloque: el resolvedor con lo que pesco y
    `viaje.etiquetar` con lo que sobrevive a los anillos. Un solo armado
    porque el modelo tiene que ver un solo formato para lo mismo; dos copias
    verbatim divergen calladas en el primer cambio de formato."""
    partes = [f"=== Lo que subio del abismo (fuente: {fuente}) ==="]
    for texto, anillo in bloques:
        partes.append(f"[anillo {anillo}]\n{texto.strip()}")
    return "\n".join(partes)[:ABISMO_BLOQUE_MAX]


def _fallo(fuente: str, aviso: str) -> dict:
    return {"estado": "fallo", "fuente": fuente, "texto": "",
            "bloques": [], "aviso": aviso[:200]}


def resolver(m: marca.Marca, *, mem=None, obtener=None, brief=None,
             consolidado=None, zona_chat: str = "fabrica") -> dict:
    # el armado tambien va adentro del try (minor del review 1a): una fuente
    # que devuelva algo que no sea una lista de pares (texto, anillo) es un
    # fallo suave, no un TypeError que suba por la pasada sintetica
    try:
        if m.fuente == "memoria":
            bloques = fuentes.memoria(m.resto, mem, consolidado=consolidado,
                                      zona_chat=zona_chat)
        elif m.fuente == "chats":
            bloques = fuentes.chats_viejos(m.resto)
        elif m.fuente == "proyecto":
            bloques = fuentes.proyecto(m.resto, obtener, brief)
        else:  # la gramatica cerrada no deberia dejar llegar esto
            return _fallo(m.fuente, f"fuente desconocida: {m.fuente}")
        bloques = [(t, a) for t, a in bloques if t.strip()]
        if not bloques:
            return _fallo(m.fuente, "la consulta no trajo nada")
        texto = etiquetar(m.fuente, bloques)
    except Exception as e:
        return _fallo(m.fuente, str(e))
    return {"estado": "pescado", "fuente": m.fuente, "texto": texto,
            "bloques": bloques, "aviso": ""}
