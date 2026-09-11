"""La memoria con procedencia: lo que dijo Calipso es contexto, no evidencia
(spec 2026-09-11, secciones 2 y 4).

Un episodio del chat se guarda como el par `Pedro pregunto: ...\\nCalipso
respondio: ...` (server.py, el `remember` del final de `ws_chat`). Al leer,
ese par NO se le muestra crudo al modelo: se parte (`partir`), se limpia la
pregunta de los gestos (`limpiar_gestos`), se clasifica la respuesta
(`clasificar`) y se presenta con quien dijo que, cuando y por que ruta
(`presentar`). Un no-saber de Calipso se reemplaza por la frase fija: un
"no tengo registros" de ayer no es un recuerdo, y devolverselo al 7b como
recuerdo era lo que lo hacia repetirlo (h06 del smoke del abismo).

Todo es PURO y determinista: sin modelo, sin disco, sin red. Decidir al leer
es lo que permite afinar los patrones sin tocar lo guardado. Este modulo no
importa calipso.server (lo usan `abismo/fuentes.py`, que tiene la misma
regla, y `server._build_context`).
"""
from __future__ import annotations

import os
import re
import unicodedata

# --- la clasificacion (spec seccion 2, "la clasificacion es determinista") ---
#
# Sobre la respuesta en minusculas y sin acentos. Dos familias (ruling):
# los FUERTES degradan solos si arrancan dentro de los primeros
# POSICION_MAX chars (medido en 148 no-saber reales: mediana 0, p90 116,
# maximo 202); mas tarde la respuesta ya tiene contenido. Los DEBILES solo
# degradan si antes no hay ninguna oracion afirmativa con contenido. La
# otra clausula del spec para los debiles ("o si van con un fuerte") queda
# subsumida por la regla de posicion: un fuerte antes de POSICION_MAX ya
# degrada solo, y uno despues es, por ese mismo ruling, una respuesta con
# contenido que un debil al lado no vuelve no-saber (decision 4 del plan).
#
# La lista vive SOLO aca y se mide contra experimentos/no_saber_banco.py:
# afinarla es tocar estas tuplas y correr el banco, nunca el disco.

PATRONES_FUERTES = (
    r"no tengo registros?",
    r"no tengo (esa|esta|la|ninguna) informacion",
    r"no tengo informacion",
    r"no tengo (ese|el|ningun) dato",
    r"no tengo acceso",
    r"no me consta",
    r"no recuerdo",
    r"no encuentro (registro|informacion|nada)",
    r"no puedo (acceder|confirmar|verificar|recordar)",
    r"no esta (registrad|en mi memoria|en mi cronologia)",
    r"no hay (registro|informacion) (de|sobre)",
    # sumado por el banco (decision 3 del plan): "no hay informacion
    # disponible sobre su estado"; NO atrapa "no hay informacion adicional
    # disponible sobre este commit", que viene despues de un dato
    r"no hay informacion disponible",
    # sumado por el porton (ruling 6 del ledger): el 7b vio la frase fija
    # 'Calipso no tenia el dato entonces' y la parafraseo en plural ("No
    # teniamos el dato del presupuesto del taller registrado en ese
    # momento"); sin esto ese eco se guardaba como dato y volvia al turno
    # siguiente como 'Calipso contesto'. NO atrapa "no tenemos un registro
    # detallado" (cha-decision, banco: confabula y despues duda)
    r"no teniamos (el|ese|este|ningun|la) (dato|informacion)",
)

PATRONES_DEBILES = (
    # `recordar` cubre `recordarme`; `proporcionar` cubre `proporcionarme`
    r"podrias (darme|proporcionar|recordar|decirme|contarme|compartir)",
    r"me podrias (recordar|decir|dar)",
    r"puedes (darme|proporcionar|recordar|decirme|contarme|compartir)",
    r"necesito mas (contexto|detalles)",
    r"dame mas detalles",
    r"cuentame (un poco )?mas",
)

POSICION_MAX = 250

# lo que abre una oracion sin decir nada: se pela antes de contar palabras
_RELLENO = re.compile(
    r"^(?:(?:claro|por supuesto|entendido|entiendo|de acuerdo|perfecto|vale|"
    r"ok|si|hola|buen dia|buenas|gracias|pedro)[,.!:;\s]*)+")
_MIN_PALABRAS = 3

_FUERTES = tuple(re.compile(p) for p in PATRONES_FUERTES)
_DEBILES = tuple(re.compile(p) for p in PATRONES_DEBILES)


def quitar_acentos(texto: str) -> str:
    """'informacion' con tilde y sin tilde son la misma palabra para los patrones."""
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


def _normalizar(respuesta: str) -> str:
    return quitar_acentos(respuesta).lower()


def _oraciones(texto: str) -> list[str]:
    """Oraciones COMPLETAS: cerradas por . ! ? o por un salto de linea. Un
    fragmento final sin cierre no cuenta (es lo que precede a un debil que
    esta en medio de la oracion: 'Claro, para poder ayudarte mejor, me
    podrias...')."""
    piezas = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", texto)]
    piezas = [p for p in piezas if p]
    if piezas and not re.search(r"[.!?]$", piezas[-1]) and not texto.endswith("\n"):
        piezas = piezas[:-1]
    return piezas


def _afirmativa_con_contenido(oracion: str) -> bool:
    """Ni pregunta ni relleno: por lo menos _MIN_PALABRAS palabras despues
    de pelar 'Claro, Pedro.' y parientes."""
    o = oracion.strip()
    if o.endswith("?") or o.startswith("¿") or o.startswith("?"):
        return False
    pelada = _RELLENO.sub("", o)
    return len(pelada.split()) >= _MIN_PALABRAS


def clasificar(respuesta: str) -> str:
    """'sin_dato' si la respuesta es un no-saber; 'dato' si informa algo
    (aunque sea una confabulacion: eso no se detecta sin modelo, lo ataca la
    procedencia + la consulta al abismo)."""
    low = _normalizar(respuesta or "")
    if not low.strip():
        return "sin_dato"
    for patron in _FUERTES:
        m = patron.search(low)
        if m and m.start() < POSICION_MAX:
            return "sin_dato"
    for patron in _DEBILES:
        m = patron.search(low)
        if m and not any(_afirmativa_con_contenido(o)
                         for o in _oraciones(low[:m.start()])):
            return "sin_dato"
    if low.rstrip().endswith("?") and not any(
            _afirmativa_con_contenido(o) for o in _oraciones(low)):
        return "sin_dato"
    return "dato"


# --- el parser, tolerante y en un solo lugar (spec seccion 2) --------------
#
# Lo viejo no siempre dice "Pedro pregunto:": de junio a agosto se guardo con
# acentos rotos (una A con tilde donde iba la o; en el ambito de proyecto por
# scope="auto"). `\S*` se come cualquier cola hasta los dos puntos.

_PAR = re.compile(
    r"^Pedro pregunt\S*:\s*(.*?)\nCalipso respondi\S*:\s*(.*)\Z", re.DOTALL)


def partir(texto: str) -> tuple[str, str] | None:
    """(pregunta, respuesta) si el texto es un par de chat; None si no."""
    m = _PAR.match(texto or "")
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def limpiar_gestos(pregunta: str) -> str:
    """Saca los gestos iniciales ('/local hola' -> 'hola') y colapsa el
    espacio. Lo viejo se guardo con `user_msg` crudo; lo nuevo con
    `chat_msg`, que ya viene limpio salvo cuando el mensaje era SOLO gestos
    (`parse_directives` cae al crudo: '/local' llega tal cual). Devuelve ''
    para ese caso: la basura del spec."""
    tokens = (pregunta or "").split()
    while tokens and tokens[0].startswith("/"):
        tokens.pop(0)
    return " ".join(tokens)


# --- la presentacion (spec seccion 2, invariantes 1-3) ----------------------

TOPE_PREGUNTA = 200
TOPE_RESPUESTA = 400
SIN_DATO = "Calipso no tenia el dato entonces"

# La variante la fija el porton (spec seccion 5): A = frase fija; B = se
# omite el renglon de Calipso cuando es sin_dato; off = el par crudo de antes
# (solo para medir el 'antes' sobre la misma rama). En produccion la variable
# no esta puesta y vale VARIANTE_DEFAULT.
VARIANTE_DEFAULT = "A"
VARIANTES = ("A", "B", "off")


def variante_activa() -> str:
    v = (os.environ.get("MEMORIA_PRESENTAR") or "").strip()
    return v if v in VARIANTES else VARIANTE_DEFAULT


def _recortar(texto: str, tope: int) -> str:
    plano = " ".join((texto or "").split())
    if len(plano) <= tope:
        return plano
    return plano[:tope].rstrip() + "..."


def presentar(texto: str, meta: dict | None = None, *,
              tope_pregunta: int = TOPE_PREGUNTA,
              tope_respuesta: int = TOPE_RESPUESTA,
              score: float | None = None,
              variante: str | None = None) -> str:
    """Lo que el modelo ve de un episodio: una vineta con procedencia.

    Par de chat:
        - Pedro dijo (2026-08-14): empece El nombre de la rosa
          Calipso contesto (local, 2026-08-14): Buena eleccion. Anotado...
    Par con un no-saber (variante A):
        - Pedro dijo (2026-09-10): quien me presto el libro rosa?
          Calipso no tenia el dato entonces (local, 2026-09-10).
    Lo que no parsea como par (metas, fichas): nunca el crudo sin etiqueta:
        - Registro (goal, 2026-08-14): Pedro definio una meta: ...
    Pregunta que era solo un gesto ('/local'): '' -- el lector la salta.

    `meta` tolera None y claves ausentes (los dobles de los tests pasan hits
    sin meta): fecha '?' y ruta '?'. La ruta sale de `ruta` (la usada, lo
    nuevo) o de `route` (la decidida, lo viejo).

    Variante `off` (solo para medir el 'antes' del porton): el crudo de
    main, `- (score) texto` si llega `score` (el system: prompt_compiler
    pegaba el score) y `- texto` si no (el abismo: fuentes.memoria nunca lo
    pego). Quien decide si viaja el score es `presentar_recuerdos`."""
    meta = meta or {}
    variante = variante or variante_activa()
    if variante == "off":
        return f"- ({score}) {texto}" if score is not None else f"- {texto}"
    fecha = str(meta.get("ts") or "")[:10] or "?"
    par = partir(texto)
    if par is None:
        kind = meta.get("kind") or "episodio"
        return f"- Registro ({kind}, {fecha}): {_recortar(texto, tope_respuesta)}"
    pregunta, respuesta = par
    pregunta = limpiar_gestos(pregunta)
    if not pregunta:
        return ""
    ruta = meta.get("ruta") or meta.get("route") or "?"
    lineas = [f"- Pedro dijo ({fecha}): {_recortar(pregunta, tope_pregunta)}"]
    if clasificar(respuesta) == "sin_dato":
        if variante == "A":
            lineas.append(f"  {SIN_DATO} ({ruta}, {fecha}).")
    else:
        lineas.append(f"  Calipso contesto ({ruta}, {fecha}): "
                      f"{_recortar(respuesta, tope_respuesta)}")
    return "\n".join(lineas)


def presentar_recuerdos(hits: list[dict], tope: int, *,
                        variante: str | None = None,
                        con_score: bool = True) -> list[dict]:
    """Los dos lectores (el system del turno y la fuente `memoria` del
    abismo) pasan por aca: presentar cada hit, SALTAR los vacios y recien
    ahi cortar a `tope` (spec: presentar ANTES del corte, para que un salto
    no achique el bloque). Devuelve los hits con `text` ya presentado (el
    resto del hit -score, meta, scope- viaja intacto).

    `con_score` solo importa en la variante `off`: el system de main pegaba
    `- (score) texto` (con_score=True, `_build_context`) y el abismo `- texto`
    (con_score=False, `fuentes.memoria`). En A y B el score nunca se ve."""
    salida = []
    for h in hits:
        texto = presentar(h.get("text") or "", h.get("meta"),
                          score=h.get("score") if con_score else None,
                          variante=variante)
        if not texto:
            continue
        salida.append({**h, "text": texto})
        if len(salida) >= tope:
            break
    return salida
