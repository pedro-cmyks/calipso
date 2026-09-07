"""El resolvedor de la consulta -- spec 2026-09-07, seccion 4.

100% local siempre (invariante 1). Fallo cerrado: una consulta jamas rompe
una respuesta (invariante 4) -- toda excepcion degrada a estado "fallo" y el
turno sigue sin contexto extra.
"""
from __future__ import annotations

import os

from calipso.abismo import fuentes, marca

ABISMO_BLOQUE_MAX = int(os.environ.get("ABISMO_BLOQUE_MAX", "2000"))


def _fallo(fuente: str, aviso: str) -> dict:
    return {"estado": "fallo", "fuente": fuente, "texto": "",
            "bloques": [], "aviso": aviso[:200]}


def resolver(m: marca.Marca, *, mem=None, obtener=None, brief=None,
             consolidado=None, zona_chat: str = "fabrica") -> dict:
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
    except Exception as e:
        return _fallo(m.fuente, str(e))
    bloques = [(t, a) for t, a in bloques if t.strip()]
    if not bloques:
        return _fallo(m.fuente, "la consulta no trajo nada")
    partes = [f"=== Lo que subio del abismo (fuente: {m.fuente}) ==="]
    for texto, anillo in bloques:
        partes.append(f"[anillo {anillo}]\n{texto.strip()}")
    return {"estado": "pescado", "fuente": m.fuente,
            "texto": "\n".join(partes)[:ABISMO_BLOQUE_MAX],
            "bloques": bloques, "aviso": ""}
