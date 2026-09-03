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
- Escribi en espanol NEUTRO y claro. NO uses regionalismos de ningun pais (ni
  "che"/"dale" argentinos, ni "chido" mexicano, ni ninguno) SALVO que los
  ejemplos de Pedro de abajo los muestren. Ante la duda, neutro: es mejor sonar
  neutro que inventarle a Pedro un acento que no es el suyo. Su voz de verdad
  se aprende de sus ejemplos, no se adivina.
- De los ejemplos toma solo lo OBSERVABLE: largo de frase, si usa tildes o no,
  como saluda, sus muletillas, que tan formal es. Adapta la formalidad al
  contexto (a un amigo mas suelto que a un cliente), pero sin inventar
  vocabulario regional que no veas.
- Devolve SOLO el texto listo para mandar, sin preambulo, sin comillas, sin
  explicar. Nada de "aca va tu respuesta:".
"""

_CON_EJEMPLOS = """
Asi escribe Pedro (ejemplos reales de sus mensajes; imita SOLO lo observable,
no inventes un acento que no este aca):
{ejemplos}
"""

_SIN_EJEMPLOS = """
No hay ejemplos de la voz de Pedro disponibles: escribi en espanol NEUTRO,
natural y directo, sin inventar un estilo ni un acento que no conoces.
"""


def construir_prompt(pedido: str, ejemplos: list[str]) -> tuple[str, str]:
    """(system, user) para redactar en la voz de Pedro."""
    if ejemplos:
        bloque = "\n".join(f"- {e}" for e in ejemplos)
        system = _BASE + _CON_EJEMPLOS.format(ejemplos=bloque)
    else:
        system = _BASE + _SIN_EJEMPLOS
    return system, pedido


def preparar_borrador(pedido: str, chats_data: dict,
                      guardados: list = ()) -> tuple[str, str]:
    """Junta los ejemplos de voz de Pedro -- los que trajo con /mia
    (`guardados`) primero, luego sus mensajes de chat -- y arma el (system,
    user) para el borrador. La cara testeable de lo que hace el chat en
    /redacta."""
    ejemplos = voz.ejemplos_de_voz(chats_data, guardados)
    return construir_prompt(pedido, ejemplos)
