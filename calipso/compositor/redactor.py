"""Arma el prompt que hace que el modelo escriba EN LA VOZ de Pedro. Puro: no
llama a ningun modelo, solo construye (system, user). Quien lo corre es el
chat (con el modelo local por default).
"""

from calipso.compositor import voz

_BASE = """\
Sos el compositor de voz de Calipso. Tu tarea NO es responderle a Pedro: es
escribir un texto COMO LO ESCRIBIRIA PEDRO, para que el lo mande como suyo.

El mensaje de Pedro es una de dos cosas, y tenes que inferir cual:
- un mensaje que a Pedro le llego y quiere responder -> escribi SU respuesta;
- una intencion ("decile a X que...") -> escribi ese texto desde cero.

Reglas:
- Escribi en la VOZ de Pedro: su registro, sus muletillas, su puntuacion, su
  largo de frase. Adapta el registro al contexto (a un amigo distinto que a un
  cliente), pero siempre suena a el.
- Devolve SOLO el texto listo para mandar, sin preambulo, sin comillas, sin
  explicar. Nada de "aca va tu respuesta:".
"""

_CON_EJEMPLOS = """
Asi escribe Pedro (ejemplos reales de sus mensajes, imita este estilo):
{ejemplos}
"""

_SIN_EJEMPLOS = """
No hay ejemplos de la voz de Pedro disponibles: escribi natural y directo,
sin inventar un estilo que no conoces.
"""


def construir_prompt(pedido: str, ejemplos: list[str]) -> tuple[str, str]:
    """(system, user) para redactar en la voz de Pedro."""
    if ejemplos:
        bloque = "\n".join(f"- {e}" for e in ejemplos)
        system = _BASE + _CON_EJEMPLOS.format(ejemplos=bloque)
    else:
        system = _BASE + _SIN_EJEMPLOS
    return system, pedido


def preparar_borrador(pedido: str, chats_data: dict) -> tuple[str, str]:
    """Junta los ejemplos de voz de Pedro y arma el (system, user) para el
    borrador. La cara testeable de lo que hace el chat en /redacta."""
    ejemplos = voz.ejemplos_de_voz(chats_data)
    return construir_prompt(pedido, ejemplos)
