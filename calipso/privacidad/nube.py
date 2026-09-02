"""La compuerta entre un prompt y la nube, cuando Pedro pide ayuda de la nube
sobre un prompt privado (el gesto `/nube`). Corre el juez de dos capas y decide:

- Si el juez falla cerrado (credencial, LLM local caido, o un tipo que no puede
  categorizar con seguridad): el prompt NO va a la nube -- se queda local. Una
  credencial nunca sale, ni tapada.
- Si hay tramos de lenguaje humano: los tapa con marcadores estables y devuelve
  el texto redactado para mandar, mas la lista de que se tapo (para el aviso).
- Si no hay nada sensible: el texto viaja igual.

El juez corre SOLO aca (camino `/nube`), no en cada prompt: local es el default.
"""
from calipso.privacidad import juez
from calipso.privacidad import redaccion
from calipso.privacidad.redaccion import MapaMarcadores


def preparar_envio(texto: str, mapa: MapaMarcadores) -> dict:
    """Decide como (y si) mandar `texto` a la nube. Devuelve
    {"accion": "nube"|"local", "texto": str|None, "tapados": list, "motivo": str}."""
    veredicto = juez.juzgar(texto)
    if veredicto["fallo_cerrado"]:
        return {"accion": "local", "texto": None, "tapados": [],
                "motivo": veredicto["motivo"]}
    tramos = veredicto["tramos"]
    tapado = redaccion.redactar(texto, tramos, mapa)
    tapados = [{"marcador": mapa.marcador_para(t["texto"], t["tipo"]),
                "tipo": t["tipo"]} for t in tramos]
    return {"accion": "nube", "texto": tapado, "tapados": tapados, "motivo": ""}


def ruteo_para_nube(dec: dict, route: str, force_route) -> dict:
    """Traduce la decision del juez (`dec`, de `preparar_envio`) al ruteo
    concreto del turno. Pura: sin WebSocket, sin efectos de lado, testeable
    a mano. Devuelve {"route": str, "nube_local": bool, "mensaje": str|None}:

    - `dec["accion"] == "local"` (fallo cerrado): el turno se queda local.
    - `dec["accion"] == "nube"`: local es la ruta por defecto, asi que si la
      ruta decidida es local y Pedro no forzo otra (`/api`/`/claude`/`/codex`),
      `/nube` la sube a la nube gratis (subscription). Si Pedro ya forzo una
      ruta, se respeta esa -- incluido `/local`, que gana aunque el juez diga
      nube (gesto contradictorio de Pedro, pero explicito).

    `nube_local` significa "este turno se queda LOCAL" -- NO "el juez fallo
    cerrado". Se calcula de la ruta final en AMBAS ramas: si `/local` (u otro
    force_route ya local) deja `route_final == "local"` aunque la accion sea
    "nube", `nube_local` tiene que dar True igual, porque quien consume este
    resultado (ws_chat) usa `nube_local` para saltear la orquestacion -- y un
    turno que se queda local no puede dejar que un equipo dinamico lo mande
    a la nube igual por otro camino (esa fue la fuga real: `/local /nube` con
    un dato humano quedaba con `nube_local=False` y el corte no saltaba)."""
    if dec["accion"] == "local":
        route_final = "local"
        mensaje = None
    else:
        route_final = "subscription" if (route == "local" and not force_route) else route
        mensaje = dec["texto"]
    return {"route": route_final, "nube_local": route_final == "local", "mensaje": mensaje}
