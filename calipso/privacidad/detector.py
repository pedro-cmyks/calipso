"""La capa determinista del juez de privacidad: reconoce SECRETOS de maquina
(claves, tokens, API keys) que el juez LLM deja pasar por ser blobs opacos.
Instantaneo, sin llamadas. Todo lo que marca es tipo 'credencial', y una
credencial hace fallar cerrado el prompt (nunca se redacta ni se manda tapada).

Medido en experimentos/juez_privacidad.py: cierra exactamente los huecos del 7b
(un JWT, un rk_live_) con cero falsos positivos sobre los negativos del banco.
"""
import math
import re
from collections import Counter

# Prefijos de secretos conocidos: si aparece uno, lo que sigue es una clave.
_PREFIJOS = re.compile(
    r"\b(sk-[a-z]+-|sk_live_|rk_live_|ghp_|gho_|ghs_|github_pat_|AKIA|ASIA|"
    r"AIza|xox[baprs]-|glpat-|npm_)[A-Za-z0-9_\-/]{6,}")
# Un JWT: tres bloques base64url separados por puntos, arrancando en eyJ.
_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]{6,}")
# Cabecera de clave privada PEM (con lo que le siga en la misma linea).
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[^\n]*")
# Cadena de conexion con credencial embebida: esquema://usuario:clave@host
_CONN = re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s:@/]+:[^\s:@/]+@[^\s]+")
# hash o secreto hexadecimal (128 bits o mas): 32+ chars hex seguidos.
_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")
# secreto base32 (TOTP/2FA): mayusculas y digitos 2-7. Exige al menos un
# digito [2-7] en el match para no marcar palabras/acronimos en mayusculas.
_BASE32 = re.compile(r"\b[A-Z2-7]{16,}\b")
# Tokens largos, mezclados y de alta entropia: probable secreto sin pista lexica.
# Sin simbolos humanos como "$": esta capa es de FORMATO MAQUINA (base64/base64url/
# hex/base32). Una password humana con simbolos es dominio del juez LLM.
_TOKEN = re.compile(r"[A-Za-z0-9_\-/+.=]{20,}")


def _entropia(s: str) -> float:
    if not s:
        return 0.0
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in Counter(s).values())


def detectar_secretos(texto: str) -> list[dict]:
    """Todos los tramos de `texto` que parecen un secreto de maquina. Cada uno
    `{"texto": <literal>, "tipo": "credencial"}`. Puede haber varios."""
    vistos: set[str] = set()
    tramos: list[dict] = []

    def agregar(s: str) -> None:
        s = s.strip()
        if s and s not in vistos:
            vistos.add(s)
            tramos.append({"texto": s, "tipo": "credencial"})

    for rx in (_PREFIJOS, _JWT, _PEM, _CONN):
        for m in rx.finditer(texto):
            agregar(m.group(0))
    for m in _HEX.finditer(texto):
        agregar(m.group(0))
    for m in _BASE32.finditer(texto):
        if re.search(r"[2-7]", m.group(0)):
            agregar(m.group(0))
    for tok in _TOKEN.findall(texto):
        if "@" in tok:
            continue  # los mails los marca el juez LLM como 'contacto', no aca
        clases = (bool(re.search(r"[a-z]", tok)) + bool(re.search(r"[A-Z]", tok))
                  + bool(re.search(r"[0-9]", tok)))
        if _entropia(tok) >= 4.2 and clases >= 2:
            agregar(tok)
    return tramos
