"""Los canarios: anclaje, degeneracion y ventana (spec 2026-09-11).

Modulo PURO: sin modelo, sin disco, sin red, sin importar `server`. Corre al
cierre de cada turno del chat, en hilo, sobre lo que el turno ya tiene, y
devuelve un veredicto con tres partes. No frena, no reintenta, no reescribe
(decision de Pedro: marcar y medir). La unica accion no pasiva vive aca
tambien -`recortar`, lo volatil antes que lo estable cuando el prompt local
no cabe- y la llama el server ANTES de mandar, anotando lo que saco.

Umbrales en un solo lugar (UMBRALES), calibrados contra
experimentos/anclaje_banco.py y experimentos/degeneracion_banco.py; las
notas de calibracion estan al lado de cada numero.
"""
from __future__ import annotations

import json
import math
import re
import time
import unicodedata

from calipso import prompt_compiler
from calipso.abismo import turno as abismo_turno

# --- tope de tiempo (invariante 3): el server lo aplica con wait_for -------
TOPE_SEGUNDOS = 2.0

# --- umbrales, en un solo lugar --------------------------------------------
UMBRALES = {
    # anclaje: una afirmacion de recuerdo ancla si al menos esta fraccion de
    # sus palabras de contenido aparece en el contexto, o un bigrama entero
    "recuerdo_fraccion": 0.5,
    "palabra_min_letras": 4,
    # degeneracion (banco: 19 rotas -15 reales-, 32 sanas, 0 falsos)
    "repeticion_ngrama": 6,
    "repeticion_veces": 3,
    "repeticion_lineas_seguidas": 3,
    # corrida de letras no latinas SIN que la puntuacion la corte: con 15
    # estricto se perdian 5 de 9 casos de chino reales (la coma y el punto
    # CJK cortan la corrida; posicion_produccion.jsonl:65 da 10); con 10 y
    # la corrida laxa se atrapan los 9 y el maximo sobre 1290 sanas es 0
    "alfabeto_corrida": 10,
    "alfabeto_fraccion": 0.20,
    "fuga_contrato_palabras": 8,
    "formato_claves": 3,
    # ventana (spec 2.3)
    "truncado_evaluado_alto": 0.95,
    "truncado_evaluado_bajo": 0.85,
    "fallback_chars_por_token": 3.3,
    "template_por_mensaje": 5,      # <|im_start|>rol\n ... <|im_end|>\n
    "template_cierre": 3,           # <|im_start|>assistant\n
}

# el conjunto del spec (2.2): la union de server.py:1424 (code, repo,
# agentic), skills.py:82 (repo, code, refactor, exec) y orchestrator.py:47
# (analysis, code, repo, agentic, exec) sin `analysis`; no existe como
# constante en ningun otro modulo, por eso vive aca
TIPOS_CON_CODIGO = frozenset({"code", "repo", "refactor", "exec", "agentic"})

# secciones del system (titulos de prompt_compiler.context_sections mas las
# que el server suma). Las de INSTRUCCION son contra las que corre
# fuga_del_contrato; las VOLATILES son las unicas que el recorte toca; el
# resto es estable. "" es una seccion cruda (el system de /nube viaja
# entero asi): cuenta como instruccion y estable.
SECCIONES_INSTRUCCION = frozenset({"Sistema", "Constitucion de Calipso",
                                   "Contrato interno", ""})
SECCION_RECUERDOS = "Recuerdos relevantes"
SECCION_REPO = "Repo"
PREFIJO_WEB = "Resultados web para: "
PREFIJO_BLOQUE = "Lo que subio del abismo (fuente: "

# senales de memoria en la RESPUESTA (clase 2 del anclaje) y en la PREGUNTA
# (cuando aplica la marca visible), normalizadas (sin acentos, minusculas)
# "anotado" NO esta aca aunque el spec lo liste en las dos clases: es una
# ACCION (abajo); como senal de recuerdo doblaba la marca ("He anotado la
# fecha de cumpleanos de tu hermana": 2 falsos de recuerdo en el banco,
# porque lo anotado es lo que Pedro acaba de decir). Decision 3 del plan.
SENALES_RESPUESTA = ("recuerdo que", "te conte", "me dijiste", "quedamos en",
                     "hablamos de", "la ultima vez", "en la ultima conversacion",
                     "segun mi recuerdo", "de acuerdo con los recuerdos",
                     # sumadas por el banco: "la ultima discusion sobre el
                     # presupuesto del taller se refiere a que aun no hemos
                     # llegado a un acuerdo" (porton:19) no traia ninguna
                     "la ultima discusion", "la ultima charla")
SENALES_PREGUNTA = ("te conte", "lo tenes", "acordate", "me dijiste", "la otra vez",
                    "que dejamos", "te dije", "te pase", "no me acuerdo",
                    "me acuerdo", "retoma")
# acciones afirmadas (clase 3) -> lo que el turno tiene que haber hecho
ACCIONES = {
    "consulto": (r"\bconsulte\b", r"\bconsultando (los|tus|mis) recuerdos",
                 r"\bbusque en (tus|los|mis) (chats|recuerdos|registros|conversaciones)"),
    "recordo": (r"\banote\b", r"\banotado\b", r"\blo guard(o|e)\b"),
    "repo": (r"\brevise el repo\b", r"\bmire el repo\b"),
    "web": (r"\bbusque en (la web|internet)\b",),
}
# una oracion que OFRECE o PREGUNTA no afirma nada: 4 de 5 "la ultima vez"
# reales y el unico "busque en tus" eran preguntas u ofertas a Pedro
_OFERTA = re.compile(r"\b(si (deseas|queres|quieres) que|quieres que|queres que|"
                     r"puedo|podria|podrias|necesitas que)\b")

STOPWORDS = frozenset("""
a al algo alguna algunas alguno algunos ante antes aqui asi aun aunque bien cada
casi como con contra cual cuales cuando cuanto de del desde donde dos el ella
ellas ellos en entre era eran es esa esas ese eso esos esta estaba estaban
estamos estan estar este esto estos fue fueron ha haber habia hace hacer hasta
hay la las le les lo los mas me mi mis mientras mismo mucho muy nada ni no nos
nosotros nuestra nuestro o otra otras otro otros para pero poco por porque
que quien quienes se sea ser si sin sobre solo son soy su sus tal tambien
tan tanto te tener tengo ti tiene tienen toda todas todo todos tu tus un una
unas uno unos usted vos ya yo ahora luego entonces donde cuando mientras
segun pues sino vez veces esta estas mismo misma
tuve tuvo tuviste hemos han has he hubo
""".split())

# --- normalizacion (spec 2.1: minusculas, sin acentos, mojibake por linea,
# espacios colapsados) ------------------------------------------------------

def quitar_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


def _desmojibakear(linea: str) -> str:
    """'preguntÃ³' -> 'pregunto' si la linea es latin-1 leido como utf-8."""
    if "Ã" not in linea and "Â" not in linea:
        return linea
    try:
        return linea.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return linea


def normalizar(texto: str, conservar_saltos: bool = False) -> str:
    """Minusculas, sin acentos, mojibake por linea, espacios colapsados.
    Con `conservar_saltos` cada linea se colapsa por separado y los `\\n`
    quedan: el eco del molde de chats se busca al inicio de un parrafo."""
    lineas = [_desmojibakear(l) for l in (texto or "").split("\n")]
    if conservar_saltos:
        return "\n".join(" ".join(quitar_acentos(l).lower().split()) for l in lineas)
    plano = quitar_acentos("\n".join(lineas)).lower()
    return " ".join(plano.split())


def _oraciones(texto: str) -> list[str]:
    piezas = re.split(r"(?<=[.!?])\s+|\n+", texto or "")
    return [p.strip() for p in piezas if p.strip()]


def _palabras(texto: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", texto)


# --- el contexto de anclaje, con fuente (spec 2.1) -------------------------

FUENTES = ("mensaje_pedro", "system_estable", "recuerdo_pedro", "recuerdo_calipso",
           "historial_pedro", "historial_calipso", "bloque")
FUENTES_CALIPSO = frozenset({"recuerdo_calipso", "historial_calipso"})


def es_volatil_recuerdos(titulo: str) -> bool:
    return titulo == SECCION_RECUERDOS


def es_bloque(titulo: str) -> bool:
    return titulo.startswith(PREFIJO_BLOQUE)


def es_web(titulo: str) -> bool:
    return titulo.startswith(PREFIJO_WEB)


def _partir_recuerdos(cuerpo: str) -> tuple[str, str]:
    """Las vinetas de `memoria_procedencia.presentar`: '- Pedro dijo (...)'
    es de Pedro; '  Calipso contesto (...)' y '  Calipso no tenia el dato'
    son de Calipso; '- Registro (...)' (una meta, una ficha: no es voz de
    Calipso) va con Pedro."""
    pedro, calipso = [], []
    for linea in cuerpo.split("\n"):
        if linea.startswith("  Calipso"):
            calipso.append(linea)
        else:
            pedro.append(linea)
    return "\n".join(pedro), "\n".join(calipso)


def contexto_del_turno(secciones, historial, mensaje, bloques) -> dict[str, str]:
    """{fuente: texto crudo}. Las secciones estables son todas menos los
    recuerdos y los bloques del abismo (que viajan como secciones en la
    reentrada Y llegan en `bloques`: se leen de `bloques`)."""
    estable, rec_pedro, rec_calipso = [], "", ""
    for titulo, cuerpo in secciones:
        if es_volatil_recuerdos(titulo):
            rec_pedro, rec_calipso = _partir_recuerdos(cuerpo)
        elif es_bloque(titulo):
            continue
        else:
            estable.append(cuerpo)
    return {
        "mensaje_pedro": mensaje or "",
        "system_estable": "\n".join(estable),
        "recuerdo_pedro": rec_pedro,
        "recuerdo_calipso": rec_calipso,
        "historial_pedro": "\n".join(m.get("content", "") for m in (historial or [])
                                     if m.get("role") == "user"),
        "historial_calipso": "\n".join(m.get("content", "") for m in (historial or [])
                                       if m.get("role") == "assistant"),
        "bloque": "\n".join(bloques or []),
    }


# --- hechos duros (clase 1) ------------------------------------------------

_URL = re.compile(r"https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.]+")
_MARCADOR = re.compile(r"\[[A-Z_]+_\d+\]")          # [CONTACTO_1], [ID_2]: /nube
_NOMBRE = re.compile(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+)\b")
_TITULO_TRAS = re.compile(
    r"\b(?:libro|novela|pelicula|película|serie)\s+"
    r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]*(?:\s+[a-záéíóúñ]+){1,7})")
_CONECTORES = frozenset({"de", "del", "la", "el", "los", "las", "y", "en", "un", "una"})
_TITULO_ENTRE = re.compile(r"[\"“`]([^\"”`\n]{3,80})[\"”`]")
_FECHA_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# mes -> numero, con las dos grafias de septiembre (un dict, no la posicion
# en la lista: con 13 grafias `index % 13 + 1` corria octubre-diciembre)
_MES_NUM = {**{m: i + 1 for i, m in enumerate(
    "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre".split())},
    "setiembre": 9}
# las regex de fecha, numero y ruta corren sobre el texto CRUDO de la
# respuesta (la clave se normaliza despues) con IGNORECASE: '3.101 COP',
# '14 de Agosto', 'README.MD' (ejemplos literales del spec 2.1)
_FECHA_TEXTO = re.compile(r"\b(\d{1,2}) de (" + "|".join(_MES_NUM) + r")(?: de (\d{4}))?\b", re.IGNORECASE)
_NUMERO_UNIDAD = re.compile(
    r"(?:\$\s?(\d[\d.,]*)|\b(\d[\d.,]*)\s?(?:%|dolares|dólares|usd|cop|pesos|euros|eur|"
    r"dias|días|horas|minutos|meses|semanas|anos|años|km|kg|mb|gb|ms|tokens|chars|"
    r"caracteres|monedas|milimonedas|mm)\b)", re.IGNORECASE)
# un numeral con separadores: la clave se normaliza (punto de miles fuera,
# coma decimal a punto) y el contexto se normaliza IGUAL al buscarla
_NUMERAL = re.compile(r"\d[\d.,]*")
_RUTA = re.compile(r"(?<![\w/])((?:[\w.-]*[A-Za-z][\w.-]*/)+[\w.-]+|"
                   r"[\w-]+\.(?:py|md|json|jsonl|txt|csv|js|html))\b", re.IGNORECASE)
_IDENT = re.compile(r"\b(?:goal|job|chat|agente|sesion|c|dep)_[0-9a-f]{4,}\b|"
                    r"\b(?:feat|fix|chore|docs|plan|spec)/[\w.-]+|\b[\w.-]+:\d+\.?\d*[bB]\b|"
                    r"\b[0-9a-f]{7,40}\b")
_TECNOLOGIAS = frozenset({"node.js", "vue.js", "next.js", "nuxt.js", "three.js",
                          "d3.js", "socket.io", "chart.js", "express.js"})
_NO_NOMBRES = frozenset({"calipso", "pedro"})
_ABRIDORES = frozenset("""hola fue uso usa use soy era eran tengo tenia recuerdo entendido
    entiendo claro bueno segun ver mira gracias buen dia hoy ayer manana anotado anote
    consultando busque revise dejame vamos continuemos parece creo pienso segui
    respuesta pregunta nota ojo importante ejemplo""".split())
_DIAS = frozenset("lunes martes miercoles jueves viernes sabado domingo".split())


def _enmascarar(texto: str) -> tuple[str, list[str]]:
    urls = _URL.findall(texto)
    texto = _URL.sub(" ", texto)
    texto = _MARCADOR.sub(" ", texto)
    return texto, urls


def _numeral_normalizado(num: str) -> str:
    """'1.200' -> '1200', '3.101' -> '3101', '1,5' -> '1.5', '120' -> '120'."""
    return re.sub(r"[.,](?=\d{3}\b)", "", num).replace(",", ".")


def _mes(nombre: str) -> int:
    return _MES_NUM[quitar_acentos(nombre).lower()]


def hechos_duros(respuesta: str) -> list[dict]:
    """[{texto, tipo, clave, parcial}] en orden de aparicion, sin repetir
    clave. `clave` es lo que se busca en el contexto normalizado."""
    texto, urls = _enmascarar(respuesta or "")
    hechos: list[dict] = []
    vistos: set[str] = set()

    def sumar(tipo, literal, clave=None, parcial=False):
        clave = normalizar(clave if clave is not None else literal)
        if not clave or clave in vistos:
            return
        vistos.add(clave)
        hechos.append({"texto": literal.strip(), "tipo": tipo, "clave": clave,
                       "parcial": parcial})

    for u in urls:
        sumar("url", u)
    for m in _FECHA_ISO.finditer(texto):
        a, mes, d = m.groups()
        sumar("fecha", m.group(0), f"{int(d)}-{int(mes)}-{a}")
    for m in _FECHA_TEXTO.finditer(texto):
        d, mes, a = m.groups()
        clave = f"{int(d)}-{_mes(mes)}"
        sumar("fecha", m.group(0), clave + (f"-{a}" if a else ""), parcial=not a)
    for m in _NOMBRE.finditer(texto):
        palabras = [p for p in m.group(1).split()
                    if quitar_acentos(p).lower() not in _NO_NOMBRES | _DIAS]
        # la primera palabra de una oracion va con mayuscula por la oracion,
        # no por ser nombre: "Fue Gabriel Garcia Marquez" -> se pela "Fue"
        # si es una palabra comun; "Mariana Quintero te presto" se queda
        if palabras and quitar_acentos(palabras[0]).lower() in _ABRIDORES | STOPWORDS:
            palabras = palabras[1:]
        if len(palabras) < 2:
            continue          # "Hola Pedro", "Uso Node": no son un nombre
        sumar("nombre", " ".join(palabras))
    for m in _TITULO_TRAS.finditer(texto):
        # "Mayuscula + de/del/la/el + minusculas" tras libro/novela/...:
        # "El nombre de la rosa" si; "el libro rosa" no (sin mayuscula). Se
        # pelan los conectores que quedan colgando al final ("... rosa el")
        palabras = m.group(1).split()
        while len(palabras) > 1 and palabras[-1] in _CONECTORES:
            palabras.pop()
        if len(palabras) >= 2 and _CONECTORES & set(palabras[1:]):
            sumar("titulo", " ".join(palabras))
    for m in _TITULO_ENTRE.finditer(texto):
        # dos palabras o mas y mayuscula inicial: "Cien anos de soledad" si,
        # "git status" y ") y termina (" no
        if len(m.group(1).split()) >= 2 and m.group(1)[0].isupper():
            sumar("titulo", m.group(1))
    for m in _NUMERO_UNIDAD.finditer(texto):
        num = m.group(1) or m.group(2)
        sumar("numero", m.group(0), _numeral_normalizado(num))
    for m in _RUTA.finditer(texto):
        if m.group(1).lower() in _TECNOLOGIAS:
            continue
        sumar("archivo", m.group(1))
    for m in _IDENT.finditer(texto):
        sumar("identificador", m.group(0))
    return hechos


def _fecha_en(clave: str, contexto_norm: str) -> bool:
    """Una fecha sin ano ancla contra dia-mes en cualquier ano; con ano,
    contra la misma fecha en cualquiera de las dos escrituras."""
    partes = clave.split("-")
    d, mes = int(partes[0]), int(partes[1])
    ano = partes[2] if len(partes) == 3 else None
    for m in _FECHA_ISO.finditer(contexto_norm):
        a, mm, dd = m.groups()
        if int(dd) == d and int(mm) == mes and (ano is None or a == ano):
            return True
    for m in _FECHA_TEXTO.finditer(contexto_norm):
        dd, mm, a = m.groups()
        if int(dd) == d and _mes(mm) == mes and (ano is None or a == ano or a is None):
            return True
    return False


def _clave_en(hecho: dict, contexto_norm: str) -> bool:
    if hecho["tipo"] == "fecha":
        return _fecha_en(hecho["clave"], contexto_norm)
    if hecho["tipo"] == "numero":
        # los numerales del contexto se normalizan como la clave: '1.200
        # dolares' repetido bien contra 'techo de 1.200 dolares' ancla
        contexto_num = _NUMERAL.sub(lambda m: _numeral_normalizado(m.group(0)), contexto_norm)
        return re.search(r"(?<![\d.])" + re.escape(hecho["clave"]) + r"(?![\d])", contexto_num) is not None
    return hecho["clave"] in contexto_norm


# --- afirmaciones de recuerdo (clase 2) y acciones (clase 3) ---------------

def _contenido(oracion_norm: str, senal: str) -> list[str]:
    sin_senal = oracion_norm.replace(senal, " ")
    minimo = UMBRALES["palabra_min_letras"]
    return [p for p in _palabras(sin_senal)
            if len(p) >= minimo and p not in STOPWORDS]


def _senal_en(oracion_norm: str, senales) -> str | None:
    """La primera senal que aparece como palabras enteras ('te conte' no
    esta en 'este contexto'); None si alguna senal de la oracion lleva un
    'no' adelante ('no hablamos de detalles' es honesto)."""
    positiva = None
    for s in senales:
        m = re.search(r"(?<![a-z])(no )?" + re.escape(s) + r"(?![a-z])", oracion_norm)
        if m and m.group(1):
            return None       # una senal negada: la oracion no afirma un recuerdo
        if m and positiva is None:
            positiva = s
    return positiva


def afirmaciones_de_recuerdo(respuesta: str) -> list[dict]:
    """[{texto, senal, palabras}] por oracion con senal; las interrogativas
    y las ofertas no afirman nada."""
    salida = []
    for oracion in _oraciones(respuesta or ""):
        o = normalizar(oracion)
        if o.endswith("?") or o.startswith("¿") or "?" in oracion:
            continue
        if _OFERTA.search(o):
            continue
        senal = _senal_en(o, SENALES_RESPUESTA)
        if senal is None:
            continue
        salida.append({"texto": oracion.strip(), "senal": senal,
                       "palabras": _contenido(o, senal)})
    return salida


def acciones_afirmadas(respuesta: str) -> list[dict]:
    salida = []
    for oracion in _oraciones(respuesta or ""):
        o = normalizar(oracion)
        if o.endswith("?") or "?" in oracion or _OFERTA.search(o):
            continue
        for accion, patrones in ACCIONES.items():
            for p in patrones:
                m = re.search(p, o)
                if m:
                    salida.append({"texto": oracion.strip(), "accion": accion,
                                   "evidencia": m.group(0)})
                    break
            else:
                continue
            break
    return salida


def _contenido_del_contexto(texto_norm: str) -> str:
    minimo = UMBRALES["palabra_min_letras"]
    return " ".join(p for p in _palabras(texto_norm)
                    if len(p) >= minimo and p not in STOPWORDS)


FUENTES_EPISODICAS = frozenset({"recuerdo_pedro", "recuerdo_calipso",
                                "historial_pedro", "historial_calipso", "bloque"})


def _recuerdo_anclado(palabras: list[str], contenidos: dict[str, str]) -> list[str]:
    """Las fuentes en las que la afirmacion ancla: la mitad de las palabras
    (en cualquier fuente) o un bigrama entero (solo en las fuentes
    EPISODICAS: un par de palabras del system -el nombre de un proyecto,
    una linea de la economia- es vocabulario del tema, no un recuerdo; el
    banco lo mide: "quedamos en revisar los costos ... del proyecto
    mapa-ciudad" anclaba por 'mapa ciudad' en Proyectos). [] si en ninguna."""
    if not palabras:
        return []
    fuentes = []
    minimo = math.ceil(len(palabras) * UMBRALES["recuerdo_fraccion"])
    for fuente, contenido in contenidos.items():
        if not contenido or fuente == "mensaje_pedro":
            continue
        presentes = sum(1 for p in palabras if re.search(r"\b" + re.escape(p) + r"\b", contenido))
        bigrama = (fuente in FUENTES_EPISODICAS and
                   any(f"{a} {b}" in contenido for a, b in zip(palabras, palabras[1:])))
        if presentes >= minimo or bigrama:
            fuentes.append(fuente)
    return fuentes


def anclaje(respuesta: str, contexto: dict[str, str], turno: dict) -> dict:
    """Las tres clases contra el contexto con fuente (spec 2.1). `turno`:
    {mensaje, consultas, hizo: {consulto, recordo, repo, web}, tapado}."""
    contexto_norm = {f: normalizar(t) for f, t in contexto.items()}
    contenidos = {f: _contenido_del_contexto(t) for f, t in contexto_norm.items()}
    mensaje_norm = contexto_norm.get("mensaje_pedro", "")
    hechos, sin_anclaje = [], []
    for h in hechos_duros(respuesta):
        # lo que Pedro dijo en el mismo mensaje no es un hecho de Calipso
        if _clave_en(h, mensaje_norm):
            continue
        fuentes = [f for f, t in contexto_norm.items() if t and _clave_en(h, t)]
        item = {"texto": h["texto"], "tipo": h["tipo"], "parcial": h["parcial"]}
        if fuentes:
            hechos.append({**item, "fuentes": fuentes})
        else:
            sin_anclaje.append(item)
    # las palabras de la pregunta son el TEMA, no la afirmacion: no anclan
    # (la trilogia inventada comparte 'libro' y 'conte' con la pregunta)
    del_mensaje = set(_palabras(mensaje_norm)) | _NO_NOMBRES
    for a in afirmaciones_de_recuerdo(respuesta):
        palabras = [p for p in a["palabras"] if p not in del_mensaje]
        fuentes = _recuerdo_anclado(palabras, contenidos)
        item = {"texto": a["texto"], "tipo": "recuerdo", "senal": a["senal"]}
        if fuentes:
            hechos.append({**item, "fuentes": fuentes})
        elif palabras:
            sin_anclaje.append(item)
    hizo = turno.get("hizo") or {}
    for a in acciones_afirmadas(respuesta):
        item = {"texto": a["texto"], "tipo": "accion", "accion": a["accion"],
                "evidencia": a["evidencia"]}
        if hizo.get(a["accion"]):
            hechos.append({**item, "fuentes": ["turno"]})
        else:
            sin_anclaje.append(item)
    solo_calipso = sum(1 for h in hechos
                       if h["fuentes"] and set(h["fuentes"]) <= FUENTES_CALIPSO)
    aplica_por = []
    if (turno.get("consultas") or 0) > 0:
        aplica_por.append("consulta")
    pregunta = normalizar(turno.get("mensaje") or "")
    aplica_por += [f"senal:{s}" for s in SENALES_PREGUNTA
                   if re.search(r"(?<![a-z])" + re.escape(s) + r"(?![a-z])", pregunta)]
    return {"hechos": hechos, "sin_anclaje": sin_anclaje,
            "aplica": bool(aplica_por), "aplica_por": aplica_por,
            "anclado_solo_en_calipso": solo_calipso,
            "tapado": bool(turno.get("tapado"))}


# --- degeneracion (spec 2.2) -----------------------------------------------

def _es_latina(ch: str) -> bool:
    try:
        return "LATIN" in unicodedata.name(ch)
    except ValueError:
        return False


def _alfabeto(respuesta: str) -> dict | None:
    letras = [c for c in respuesta if c.isalpha()]
    if not letras:
        return None
    no_latinas = sum(1 for c in letras if not _es_latina(c))
    # la corrida LAXA: solo una letra latina o un digito la corta; la
    # puntuacion (incluida la CJK) y los espacios no
    mejor, actual, inicio, mejor_desde = 0, 0, 0, 0
    for i, c in enumerate(respuesta):
        if c.isalpha() and not _es_latina(c):
            if actual == 0:
                inicio = i
            actual += 1
            if actual > mejor:
                mejor, mejor_desde = actual, inicio
        elif c.isalpha() or c.isdigit():
            actual = 0
    fraccion = no_latinas / len(letras)
    if mejor >= UMBRALES["alfabeto_corrida"] or fraccion > UMBRALES["alfabeto_fraccion"]:
        return {"senal": "alfabeto", "evidencia": respuesta[mejor_desde:mejor_desde + 40],
                "corrida": mejor, "fraccion": round(fraccion, 3)}
    return None


def _repeticion(respuesta: str) -> dict | None:
    n, veces = UMBRALES["repeticion_ngrama"], UMBRALES["repeticion_veces"]
    palabras = _palabras(normalizar(respuesta))
    cuentas: dict[tuple, int] = {}
    for i in range(len(palabras) - n + 1):
        g = tuple(palabras[i:i + n])
        cuentas[g] = cuentas.get(g, 0) + 1
        if cuentas[g] >= veces:
            return {"senal": "repeticion", "evidencia": " ".join(g), "veces": cuentas[g]}
    lineas = [l.strip() for l in respuesta.split("\n") if l.strip()]
    seguidas = UMBRALES["repeticion_lineas_seguidas"]
    for i in range(len(lineas) - seguidas + 1):
        if len(set(lineas[i:i + seguidas])) == 1:
            return {"senal": "repeticion", "evidencia": lineas[i][:80], "veces": seguidas}
    return None


def _fuga_del_contrato(respuesta_norm: str, secciones) -> dict | None:
    n = UMBRALES["fuga_contrato_palabras"]
    palabras_resp = _palabras(respuesta_norm)
    if len(palabras_resp) < n:
        return None
    ngramas_resp = {tuple(palabras_resp[i:i + n]) for i in range(len(palabras_resp) - n + 1)}
    for titulo, cuerpo in secciones:
        if titulo not in SECCIONES_INSTRUCCION:
            continue
        palabras = _palabras(normalizar(cuerpo))
        for i in range(len(palabras) - n + 1):
            g = tuple(palabras[i:i + n])
            if g in ngramas_resp:
                return {"senal": "fuga_del_contrato", "evidencia": " ".join(g),
                        "seccion": titulo}
    return None


_ECO = (re.compile(r"pedro dijo \("), re.compile(r"calipso contesto \("),
        re.compile(r"pedro pregunto:"), re.compile(r"calipso respondio:"),
        re.compile(r"\[anillo"), re.compile(r"=== lo que subio"),
        re.compile(r"(?:^|[\n.!?]\s*)\[[^\]\n]{1,60} \d{4}-\d{2}-\d{2}\]"))
_TEMPLATE = re.compile(r"(?:^|\n)\s*(user|assistant|system)\s*(?:\n|$)|<\|im_(?:start|end)\|>")
_SOLO_PUNTUACION = re.compile(r"^[\s\W_]*$")


def _formato_no_pedido(respuesta: str, features: dict | None) -> dict | None:
    if (features or {}).get("type") in TIPOS_CON_CODIGO:
        return None
    r = (respuesta or "").strip()
    try:
        entero = json.loads(r)
    except (ValueError, TypeError):
        entero = None
    if isinstance(entero, (dict, list)):
        return {"senal": "formato_no_pedido", "evidencia": r[:60], "forma": "json_entero"}
    if "```json" in r:
        return {"senal": "formato_no_pedido", "evidencia": "```json", "forma": "fence_json"}
    i = r.find("{")
    if i >= 0:
        claves = re.findall(r'"[^"\n]+"\s*:', r[i:])
        if len(claves) >= UMBRALES["formato_claves"]:
            return {"senal": "formato_no_pedido", "evidencia": " ".join(claves[:3]),
                    "forma": "objeto"}
    return None


def degeneracion(respuesta: str, secciones, features, usages, turno) -> dict:
    """{"senales": [...]} con evidencia; `usages` son los usage por pasada,
    `turno` = {steered: bool}."""
    senales = []
    r = respuesta or ""
    norm = normalizar(r)
    # el eco del molde de chats se busca al inicio de un parrafo: sobre la
    # forma que conserva los saltos (`normalizar` los colapsa y la
    # alternativa `\n` del ultimo patron de _ECO nunca matcheaba: un
    # 'Entendido\n\n[Charla con Mariana 2026-08-20] ...' sin punto antes
    # pasaba limpio)
    norm_saltos = normalizar(r, conservar_saltos=True)
    for s in (_repeticion(r), _alfabeto(r), _fuga_del_contrato(norm, secciones)):
        if s:
            senales.append(s)
    # la letra mas larga primero: la corta es prefijo de la larga
    letras = sorted(abismo_turno.LETRAS_REENTRADA, key=len, reverse=True) + ["Venias diciendo:"]
    for letra in letras:
        if normalizar(letra) in norm:
            senales.append({"senal": "fuga_de_reentrada", "evidencia": letra})
            break
    for p in _ECO:
        m = p.search(norm_saltos)
        if m:
            senales.append({"senal": "eco_de_episodio", "evidencia": m.group(0).strip()})
            break
    s = _formato_no_pedido(r, features)
    if s:
        senales.append(s)
    if not turno.get("steered"):
        cortada = any((u or {}).get("done_reason") == "length" for u in (usages or []))
        if cortada or _SOLO_PUNTUACION.match(r):
            senales.append({"senal": "cortada",
                            "evidencia": "done_reason=length" if cortada else "respuesta vacia"})
    m = _TEMPLATE.search(r)
    if m:
        senales.append({"senal": "fuga_de_template", "evidencia": m.group(0).strip()})
    return {"senales": senales}
