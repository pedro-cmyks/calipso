"""La etapa de viaje -- spec secciones 4 y 8 (enmienda 2026-09-08).

Funcion PURA entre la pesca y el envio: recibe los sub-bloques (texto,
anillo) que devolvio el resolvedor, el destino y el MapaMarcadores de la
conversacion, y devuelve que viaja. Tres pasos, en este orden y no en otro:

1. Anillos: lo que `anillos.puede_viajar` no deja (a la nube, todo anillo
   3) se descarta ANTES de que el juez lo vea. Si no queda nada: fallo
   `solo_hondo`.
2. El juez de dos capas (`privacidad.juez.juzgar`) sobre el texto que
   queda: credencial, juez caido o tipo desconocido = fallo cerrado del
   envio ENTERO de esa consulta (la regla del ruteo: sin condicion).
3. Redaccion con el MISMO mapa que tapo el mensaje: `[ID_1]` es la misma
   persona en el mensaje, en el bloque y en la respuesta, y el reponer de
   siempre restaura todo.

Con destino `local` es transparente: todo pasa, nada se tapa, el juez no
corre. Un solo camino para todas las rutas.
"""
from __future__ import annotations

from calipso.abismo import anillos, consulta
from calipso.privacidad import juez, redaccion


def etiquetar(fuente: str, bloques: list[tuple[str, int]]) -> str:
    """El mismo texto etiquetado que arma `consulta.resolver` (fuente y
    anillo por sub-bloque, bajo ABISMO_BLOQUE_MAX): el viaje lo re-arma con
    lo que sobrevive a los anillos. Si esto y el resolvedor divergen, el
    modelo ve dos formatos para lo mismo; test_abismo_viaje lo custodia."""
    partes = [f"=== Lo que subio del abismo (fuente: {fuente}) ==="]
    for texto, anillo in bloques:
        partes.append(f"[anillo {anillo}]\n{texto.strip()}")
    return "\n".join(partes)[:consulta.ABISMO_BLOQUE_MAX]


def _fallo(motivo: str) -> dict:
    return {"estado": "fallo", "texto": "", "tapados": [], "motivo": motivo}


def preparar_viaje(bloques: list[tuple[str, int]], destino: str, mapa,
                   fuente: str = "") -> dict:
    """Que viaja de lo pescado. Lo humano que marca el juez se TAPA y viaja
    (spec secciones 4 y 8, enmienda 2026-09-08); la frase "un sub-bloque de
    chats con salud adentro se hunde a 3" de la seccion 6 es de la version
    original del spec y queda superada por la enmienda: el juez solo puede
    tapar o cortar el envio entero, nunca cambiar el anillo de un bloque."""
    bloques = [(t, a) for t, a in bloques if t and t.strip()]
    if not bloques:
        return _fallo("vacio")
    if destino == "local":
        return {"estado": "viaja", "texto": etiquetar(fuente, bloques),
                "tapados": [], "motivo": ""}
    viajan = [(t, a) for t, a in bloques if anillos.puede_viajar(a, destino)]
    if not viajan:
        return _fallo("solo_hondo")
    texto = etiquetar(fuente, viajan)
    try:
        veredicto = juez.juzgar(texto)
    except Exception:
        return _fallo("juez_local_caido")
    if veredicto["fallo_cerrado"]:
        return _fallo(veredicto["motivo"] or "error")
    tramos = veredicto["tramos"]
    tapado = redaccion.redactar(texto, tramos, mapa)
    tapados = [{"marcador": mapa.marcador_para(t["texto"], t["tipo"]),
                "tipo": t["tipo"]} for t in tramos]
    return {"estado": "viaja", "texto": tapado, "tapados": tapados, "motivo": ""}
