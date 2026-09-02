"""El juez de privacidad de dos capas. Une el detector determinista (credenciales)
con el juez LLM local (lenguaje humano) en un solo veredicto.

Reglas (spec seccion 8 y 9):
- El detector corre primero (instantaneo). Si marca una credencial: FALLO CERRADO.
- Si el juez LLM no pudo verificar (ok=False): FALLO CERRADO -- sin verificar, no
  se manda nada.
- Si el LLM tambien marca algo como credencial: FALLO CERRADO.
- El resto (lenguaje humano) son los tramos a redactar antes de mandar a la nube.

Una credencial NUNCA queda en `tramos`: no se redacta, el prompt entero se corta.
"""
from calipso.privacidad import detector, juez_llm

_HUMANOS = ("identidad", "salud", "ubicacion", "financiero", "contacto")


def juzgar(texto: str) -> dict:
    """Veredicto de privacidad de `texto`.
    {"tramos": [...lenguaje humano a redactar...], "fallo_cerrado": bool,
     "motivo": "credencial" | "juez_local_caido" | ""}."""
    if detector.detectar_secretos(texto):
        return {"tramos": [], "fallo_cerrado": True, "motivo": "credencial"}

    r = juez_llm.juzgar_llm(texto)
    if not r["ok"]:
        return {"tramos": [], "fallo_cerrado": True, "motivo": "juez_local_caido"}

    if any(t["tipo"] == "credencial" for t in r["tramos"]):
        return {"tramos": [], "fallo_cerrado": True, "motivo": "credencial"}

    humanos = [t for t in r["tramos"] if t["tipo"] in _HUMANOS]
    return {"tramos": humanos, "fallo_cerrado": False, "motivo": ""}
