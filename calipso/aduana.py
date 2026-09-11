"""La aduana: el unico punto por el que Calipso sale a internet, y lo que anota
(spec docs/superpowers/specs/2026-09-10-aduana-design.md).

Mide, no frena. Dos entradas:

    with aduana.cruzar(quien, proposito="buscar en la web", destino=url,
                       carga=consulta) as cruce:
        pagina = urllib.request.urlopen(req, timeout=10).read()
        cruce.entro(len(pagina))

    aduana.declarar(quien, proposito="modelo de embeddings",
                    destino="huggingface.co", motivo=EMBED_MODEL)

`cruzar` es un context manager SINCRONO: al salir escribe UNA linea en
`aduana.jsonl` (bajo CALIPSO_HOME) con `ok` o `fallo` + el nombre de la
excepcion, que se re-lanza intacta. `declarar` escribe una linea con
`declarado: true`, sin bytes ni resultado, para lo que sale desde adentro de
una libreria. El `with` vive en la funcion que hace la llamada de red, y el
`Quien` le llega por parametro, sin default (invariante 6).

Este modulo es SINCRONO y toma un flock para escribir. El flock JAMAS puede
tomarse en el event loop (la trampa que ya obligo a `to_thread` en
`economia_brief` y en la capa de sesion): quien cruce desde un endpoint async
lo envuelve en `asyncio.to_thread`. Si igual lo llaman desde el loop, la
aduana lo detecta, NO toma el candado, cuenta el hueco en `sin_libro` y avisa
por telemetria (`aduana_en_loop`): fail-open, nunca fail-hang.

Fail-open en todo lo del libro (invariante 3): candado tomado, disco lleno,
sin permisos -> el cruce sigue, el contador en memoria `SIN_LIBRO` lo cuenta
y `telemetry.log_event("aduana_sin_libro", ...)` es el segundo canal. Un
fallo del libro jamas reemplaza la excepcion del bloque (invariante 2).
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import datetime
import hashlib
import json
import os
import pathlib
import re
import threading
import time
import urllib.parse
import uuid

from calipso import telemetry
from calipso.economia.candado import ErrorCandado, candado
from calipso.permisos.acciones import calipso_home
from calipso.privacidad import detector

ORIGENES = ("turno", "gesto", "rutina", "jefe", "arranque", "ui")
RUTAS = ("local", "subscription", "api", "orchestrator")
CREDENCIALES = ("maquina", "sesion")

# la carga acotada (spec seccion 5)
CONSULTA_MAX = 500
CUERPO_LINEAS = 3
CUERPO_LINEAS_MAX = 200

# el candado: no bloqueante con reintento acotado (spec seccion 6), para el
# flock AJENO (otro proceso). Entre HILOS del mismo proceso serializa
# `_ENTRE_HILOS`: `candado(no_bloquear=True)` tambien levanta ErrorCandado al
# instante si otro hilo tiene el RLock, y dos cruces simultaneos del
# threadpool perdian el segundo. Una escritura son microsegundos: esperar
# entre hilos no cuelga nada. El mismo Lock cubre los contadores de modulo
# (`SIN_LIBRO`, `_DECLARADOS`). NO lo toma `leer()`: bajo el candado
# bloqueante, un .lock ajeno colgado dejaria colgados a los escritores.
REINTENTOS = 3
ESPERA_S = 0.05
_ENTRE_HILOS = threading.Lock()

SECRETO = "[SECRETO]"
# las regex LEXICAS del detector: las unicas que corren sobre host, path y
# argv (invariante 9). `_HEX`, `_BASE32` y `_TOKEN` jamas ahi: un SHA de
# commit, una ruta de GitHub o un id de Google Docs no son secretos.
LEXICAS = (detector._PREFIJOS, detector._JWT, detector._PEM, detector._CONN)
_VALOR_DE_QUERY = re.compile(r"=([^&]*)")
# un segmento de query SIN `=` que se conserva: alfanumerico y corto
# (`?raw`, `?v2`, `?download`). Mas largo o con otros caracteres, se tapa.
_SUELTO_CORTO = re.compile(r"[A-Za-z0-9_\-]{1,12}")
PROPOSITO_MAX = 120


@dataclasses.dataclass(frozen=True, kw_only=True)
class Quien:
    """Quien dispara el cruce (spec seccion 4). Obligatorio, tipado, por
    parametro. `origen`, `proyecto` y `desde` no tienen default: el sitio
    de llamada los sabe siempre, y un default se vuelve el valor mas
    frecuente en un mes."""
    origen: str
    proyecto: str
    desde: dict
    chat: str | None = None
    gesto: str | None = None
    ruta: str | None = None
    rutina: dict | None = None
    departamento: str | None = None
    endpoint: str | None = None

    def __post_init__(self) -> None:
        if self.origen not in ORIGENES:
            raise ValueError(f"origen desconocido: {self.origen!r}")
        if not isinstance(self.proyecto, str) or not self.proyecto:
            raise ValueError("proyecto vacio")
        if (not isinstance(self.desde, dict)
                or self.desde.get("credencial") not in CREDENCIALES):
            raise ValueError(f"desde invalido: {self.desde!r}")
        if self.ruta is not None and self.ruta not in RUTAS:
            raise ValueError(f"ruta desconocida: {self.ruta!r}")
        if self.rutina is not None and not (
                isinstance(self.rutina, dict) and "kind" in self.rutina
                and "id" in self.rutina):
            raise ValueError(f"rutina invalida: {self.rutina!r}")

    def a_dict(self) -> dict:
        return dataclasses.asdict(self)


class Cuerpo:
    """Marca explicita de que la carga es un CUERPO (un PR, un POST con datos):
    al libro van tamano, sha256 y tres lineas, nunca el cuerpo entero."""
    __slots__ = ("texto",)

    def __init__(self, texto: str) -> None:
        self.texto = texto if isinstance(texto, str) else str(texto)


class Cruce:
    """Lo que el bloque puede contarle a la aduana: los bytes que volvieron."""
    __slots__ = ("bytes",)

    def __init__(self) -> None:
        self.bytes: int | None = None

    def entro(self, n: int) -> None:
        self.bytes = int(n)


# --- el libro -----------------------------------------------------------------

def _ruta() -> pathlib.Path:
    """Resuelta en CADA llamada: `CALIPSO_HOME` puede cambiar despues de
    que este modulo se importo (y en la suite, cambia)."""
    return calipso_home() / "aduana.jsonl"


def _ahora() -> str:
    """Hora local sin tz con segundos, como telemetry.jsonl y costs.jsonl:
    'hoy' en GET /api/aduana es un prefijo YYYY-MM-DD y correlaciona por ts."""
    return datetime.datetime.now().isoformat(timespec="seconds")


def _hoy() -> str:
    return datetime.date.today().isoformat()


def _endurecer(ruta: pathlib.Path) -> None:
    """Deja el archivo en 0600 si estaba mas abierto. Copia de
    `server._endurecer` (server.py:183): el kernel no importa server."""
    try:
        modo = ruta.stat().st_mode & 0o777
        if modo & 0o077:
            ruta.chmod(0o600)
    except OSError:
        pass


def _append(ruta: pathlib.Path, linea: str) -> None:
    """Una `write` por linea. Nace 0600 por `os.open(..., O_CREAT, 0o600)`:
    `open(..., "a")` naceria con el umask (0644 en la Ally). Si el archivo
    ya existia con otro modo, se endurece ANTES de escribirle."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if ruta.exists():
        _endurecer(ruta)
    fd = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as f:
        f.write(linea + "\n")


def _escribir(linea: str) -> None:
    """Serializada entre hilos por `_ENTRE_HILOS` y, adentro, bajo el candado
    del libro no bloqueante, 3 x 50 ms (solo el proceso ajeno lo hace
    fallar). Levanta lo que haya pasado: quien decide que hacer con el
    fallo es `_anotar`."""
    ruta = _ruta()
    ultimo: Exception | None = None
    with _ENTRE_HILOS:
        for intento in range(REINTENTOS):
            try:
                with candado(ruta, no_bloquear=True):
                    _append(ruta, linea)
                return
            except ErrorCandado as exc:
                ultimo = exc
                if intento < REINTENTOS - 1:
                    time.sleep(ESPERA_S)
    assert ultimo is not None
    raise ultimo


# el hueco visible: cuantos cruces no llegaron al libro, desde cuando y por
# que. En MEMORIA a proposito: con el disco lleno, un aviso que dependa del
# disco no se veria justo cuando importa.
SIN_LIBRO: dict = {"n": 0, "desde": None, "ultimo_error": None}
# las declaraciones "una vez por proceso" ya hechas (clave -> True)
_DECLARADOS: set[str] = set()


def sin_libro() -> dict:
    with _ENTRE_HILOS:
        return dict(SIN_LIBRO)


def _reset_para_tests() -> None:
    with _ENTRE_HILOS:
        SIN_LIBRO.update({"n": 0, "desde": None, "ultimo_error": None})
        _DECLARADOS.clear()


def _contar_hueco(error: str) -> int:
    """Suma el hueco bajo el Lock y devuelve el n resultante (para el aviso
    de telemetria, sin releer el contador fuera del Lock)."""
    with _ENTRE_HILOS:
        SIN_LIBRO["n"] += 1
        SIN_LIBRO["ultimo_error"] = error[:200]
        if SIN_LIBRO["desde"] is None:
            SIN_LIBRO["desde"] = _ahora()
        return SIN_LIBRO["n"]


def _en_el_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _error_sin_ruta(exc: BaseException) -> str:
    """El texto del hueco SIN la ruta del disco: `OSError.filename` y el
    mensaje de ErrorCandado llevan la ruta absoluta del libro o del .lock,
    y `ultimo_error` sale por GET /api/aduana y por telemetry.jsonl (0644).
    ErrorCandado -> solo la clase; OSError -> clase + strerror; el resto ->
    clase + mensaje (un TypeError de json.dumps no lleva rutas)."""
    nombre = type(exc).__name__
    if isinstance(exc, ErrorCandado):
        return nombre
    if isinstance(exc, OSError):
        return f"{nombre}: {exc.strerror}" if exc.strerror else nombre
    return f"{nombre}: {exc}"


def _anotar(registro: dict) -> None:
    """Escribe la linea o cuenta el hueco. JAMAS levanta (invariantes 2 y 3).
    La telemetria va SIN destino ni carga: telemetry.jsonl es 0644."""
    origen = registro.get("quien", {}).get("origen")
    proposito = registro.get("proposito")
    if _en_el_loop():
        n = _contar_hueco("aduana_en_loop")
        telemetry.log_event("aduana_en_loop", origen=origen,
                            proposito=proposito, n=n)
        return
    try:
        _escribir(json.dumps(registro, ensure_ascii=False))
    except Exception as exc:
        error = _error_sin_ruta(exc)
        n = _contar_hueco(error)
        telemetry.log_event("aduana_sin_libro", error=error[:200],
                            origen=origen, proposito=proposito, n=n)


# --- el saneo (invariante 9) --------------------------------------------------

def _tapar_lexicas(texto: str) -> str:
    for rx in LEXICAS:
        texto = rx.sub(SECRETO, texto)
    return texto


def _tapar_todo(texto: str) -> str:
    """El detector completo (las siete regex): para lo que viene del mensaje
    de Pedro. Reemplazo por literal, del tramo mas largo al mas corto (molde
    privacidad/redaccion.redactar)."""
    tramos = detector.detectar_secretos(texto)
    for t in sorted(tramos, key=lambda x: len(x["texto"]), reverse=True):
        texto = texto.replace(t["texto"], SECRETO)
    return texto


def _tapar_valores(query: str) -> str:
    """`a=1&token=abc` -> `a=[SECRETO]&token=[SECRETO]`: los nombres se
    conservan, todo valor no vacio se tapa. Un segmento SIN `=` (`?ghp_...`,
    `?a=1&deadbeef...`) no tiene nombre que conservar: pasa por las lexicas
    y, si no es un token alfanumerico corto, se tapa entero."""
    partes: list[str] = []
    for seg in query.split("&"):
        if "=" in seg:
            partes.append(_VALOR_DE_QUERY.sub(
                lambda m: "=" + SECRETO if m.group(1) else "=", seg))
        elif not seg:
            partes.append(seg)
        else:
            suelto = _tapar_lexicas(seg)
            partes.append(suelto if _SUELTO_CORTO.fullmatch(suelto) else SECRETO)
    return "&".join(partes)


def _parsear(url: str) -> urllib.parse.SplitResult | None:
    """`urlsplit` fail-open: None si no puede parsear (`http://[::1/x`
    levanta ValueError, 'Invalid IPv6 URL'). Lo que no parsea no es una URL
    saneable: quien llama lo tapa entero, jamas lo anota crudo, y el cruce
    no se frena por eso (invariante 2)."""
    try:
        return urllib.parse.urlsplit(url)
    except ValueError:
        return None


def _es_url(texto: str) -> bool:
    p = _parsear(texto)
    return p is not None and p.scheme in ("http", "https") and bool(p.netloc)


def sanear_url(url: str) -> str:
    """userinfo -> [SECRETO]; VALORES de query y fragmento -> [SECRETO]
    (nombres conservados; un fragmento sin `=` es un valor entero); sobre
    host y path solo las lexicas. Una URL que urlsplit no parsea vuelve
    como [SECRETO] entero: no se pudo sanear, no se anota cruda."""
    p = _parsear(url)
    if p is None:
        return SECRETO
    hostport = p.netloc.rsplit("@", 1)[-1]
    netloc = _tapar_lexicas(hostport)
    if "@" in p.netloc:
        netloc = SECRETO + "@" + netloc
    path = _tapar_lexicas(p.path)
    query = _tapar_valores(p.query)
    if not p.fragment:
        fragment = ""
    elif "=" in p.fragment:
        fragment = _tapar_valores(p.fragment)
    else:
        fragment = SECRETO
    return urllib.parse.urlunsplit((p.scheme, netloc, path, query, fragment))


def _destino(destino: str | None) -> dict:
    """`{host, url}`. Una URL se parsea y se sanea; un nombre de servicio
    (pypi.org, api.github.com: nominal, lo que el sitio sabe) va como host."""
    if not destino:
        return {"host": None, "url": None}
    if "://" in destino:
        p = _parsear(destino)
        host = p.hostname if p is not None else None
        return {"host": _tapar_lexicas(host) if host else None,
                "url": sanear_url(destino)}
    return {"host": _tapar_lexicas(destino), "url": None}


def _texto_de_sitio(texto: str) -> str:
    """Un texto que viene del SITIO de llamada, no de Pedro (un token de
    argv, un proposito, un motivo, el gesto): una URL http(s) pasa por
    `sanear_url` (userinfo, query y fragmento tapados); lo que urlsplit no
    parsea se tapa entero (un `?pwd=` ahi no pasaria por el saneo de
    valores); el resto solo por las lexicas (invariante 9: sin `_HEX` ni
    `_TOKEN`, un SHA o una ruta de GitHub no son secretos)."""
    if _parsear(texto) is None:
        return SECRETO
    if _es_url(texto):
        return sanear_url(texto)
    return _tapar_lexicas(texto)


def _texto_seguro(texto, tope: int | None = None) -> str | None:
    """`proposito`, `motivo` y `quien.gesto` al armar el registro: None
    queda None; el resto por `_texto_de_sitio` y, si hay tope, recortado
    DESPUES de sanear (un `/model ghp_...` no va crudo al libro)."""
    if texto is None:
        return None
    limpio = _texto_de_sitio(str(texto))
    return limpio[:tope] if tope else limpio


def _carga(carga) -> dict:
    """El recorte y el saneo los hace la aduana, no el sitio (spec 5):
    None -> nada; list[str] -> consulta (argv: cada token URL por el saneo
    de URL, el resto por las lexicas); str URL -> consulta (saneo de URL);
    str que urlsplit no parsea -> consulta [SECRETO] entera (un `?pwd=` ahi
    no pasaria por el saneo de valores); str -> consulta (detector
    completo, viene de Pedro; una frase que menciona una URL es una frase,
    no una URL); Cuerpo -> tamano + sha256[:12] + tres lineas (detector
    completo). Se sanea ANTES de recortar: un tope no puede partir un token
    por la mitad y dejarlo pasar."""
    if carga is None:
        return {"tipo": "nada"}
    if isinstance(carga, Cuerpo):
        texto = carga.texto
        crudo = texto.encode("utf-8", "replace")
        lineas = _tapar_todo(texto).split("\n")[:CUERPO_LINEAS]
        return {"tipo": "cuerpo", "tamano": len(crudo),
                "sha256": hashlib.sha256(crudo).hexdigest()[:12],
                "lineas": "\n".join(lineas)[:CUERPO_LINEAS_MAX]}
    if isinstance(carga, (list, tuple)):
        texto = " ".join(_texto_de_sitio(str(a)) for a in carga)
    elif _parsear(str(carga)) is None or _es_url(str(carga)):
        texto = _texto_de_sitio(str(carga))     # [SECRETO] entera, o la URL saneada
    else:
        texto = _tapar_todo(str(carga))
    return {"tipo": "consulta", "texto": texto[:CONSULTA_MAX]}


# --- las dos entradas ---------------------------------------------------------

def _registro(quien: Quien, proposito: str, destino: str | None,
              carga, declarado: bool) -> dict:
    if not isinstance(quien, Quien):
        raise TypeError("cruzar/declarar exigen un aduana.Quien")
    q = quien.a_dict()
    q["gesto"] = _texto_seguro(q.get("gesto"))
    return {"ts": _ahora(), "id": f"cr_{uuid.uuid4().hex[:12]}",
            "quien": q, "proposito": _texto_seguro(proposito, PROPOSITO_MAX),
            "destino": _destino(destino), "carga": _carga(carga),
            "resultado": None, "declarado": declarado}


@contextlib.contextmanager
def cruzar(quien: Quien, proposito: str, destino: str | None, carga=None):
    """Un cruce. Al entrar no escribe nada; al salir, UNA linea: `ok` si el
    bloque termino, `fallo` con el nombre de la excepcion si levanto (y la
    excepcion sigue su camino intacta). `cruce.entro(n)` es opcional."""
    registro = _registro(quien, proposito, destino, carga, declarado=False)
    cruce = Cruce()
    inicio = time.perf_counter()
    try:
        yield cruce
    except BaseException as exc:
        registro["resultado"] = {
            "estado": "fallo", "error": type(exc).__name__,
            "ms": round((time.perf_counter() - inicio) * 1000),
            "bytes": cruce.bytes}
        _anotar(registro)
        raise
    registro["resultado"] = {"estado": "ok",
                             "ms": round((time.perf_counter() - inicio) * 1000),
                             "bytes": cruce.bytes}
    _anotar(registro)


def declarar(quien: Quien, proposito: str, destino: str | None,
             motivo: str | None = None) -> None:
    """Una puerta que se abre adentro de una libreria, o algo que Pedro
    decidio contar sin medir: una linea con `declarado: true`, sin bytes ni
    resultado."""
    registro = _registro(quien, proposito, destino, None, declarado=True)
    registro["motivo"] = _texto_seguro(motivo)
    _anotar(registro)


def declarar_una_vez(clave: str, quien: Quien, proposito: str,
                     destino: str | None, motivo: str | None = None) -> bool:
    """`declarar` con bandera por proceso: la bandera se evalua y se marca
    bajo `_ENTRE_HILOS` (dos hilos no declaran dos veces) y ANTES de tocar
    el candado (un no-op nunca toma el flock). Devuelve True si declaro,
    False si ya estaba declarado."""
    with _ENTRE_HILOS:
        if clave in _DECLARADOS:
            return False
        _DECLARADOS.add(clave)
    declarar(quien, proposito, destino, motivo)
    return True


# --- el lector (GET /api/aduana) ----------------------------------------------

def _desde_clave(desde: dict | None) -> str:
    if not isinstance(desde, dict):
        return "?"
    if desde.get("credencial") == "sesion":
        return f"sesion:{desde.get('tipo') or '?'}"
    return str(desde.get("credencial") or "?")


def leer(desde: str | None = None, hasta: str | None = None,
         origen: str | None = None) -> dict:
    """Los cruces del libro entre `desde` y `hasta` (ISO local, prefijo
    alcanza: '2026-09-10'), por defecto hoy; `origen` filtra. Bajo el
    candado BLOQUEANTE, a diferencia del escritor (no bloqueante con
    reintento, spec seccion 6): quien llama esta en el threadpool, nunca en
    el loop; una lectura de KB bajo el flock dura microsegundos, y el unico
    otro tomador del `.lock` es el propio server (un escritor concurrente
    espera menos que sus 3 x 50 ms). Un `.lock` colgado por otro proceso
    dejaria colgado ESTE hilo del threadpool, no el turno: limite conocido,
    aceptado a proposito. Las lineas rotas se cuentan en `ilegibles`, jamas
    se editan."""
    ruta = _ruta()
    hoy = _hoy()
    desde = desde or hoy
    hasta = hasta or hoy
    if len(hasta) == 10:            # una fecha sola cubre el dia entero
        hasta = hasta + "T23:59:59"
    cruces: list[dict] = []
    ilegibles = 0
    if ruta.exists():
        with candado(ruta):
            texto = ruta.read_text(encoding="utf-8")
        lineas = texto.split("\n")
        if lineas and lineas[-1] == "":
            lineas.pop()
        for linea in lineas:
            try:
                c = json.loads(linea)
                ts = c["ts"]
                if not isinstance(c["quien"], dict):
                    raise TypeError
            except Exception:
                ilegibles += 1
                continue
            if ts < desde or ts > hasta:
                continue
            if origen and c["quien"].get("origen") != origen:
                continue
            cruces.append(c)
    totales = {"por_origen": {}, "por_destino": {}, "por_proyecto": {},
               "por_desde": {}, "declarados": 0}

    def sumar(clave: str, valor) -> None:
        v = str(valor) if valor is not None else "?"
        totales[clave][v] = totales[clave].get(v, 0) + 1

    for c in cruces:
        q = c.get("quien") or {}
        sumar("por_origen", q.get("origen"))
        sumar("por_destino", (c.get("destino") or {}).get("host"))
        sumar("por_proyecto", q.get("proyecto"))
        sumar("por_desde", _desde_clave(q.get("desde")))
        if c.get("declarado"):
            totales["declarados"] += 1
    return {"cruces": cruces, "totales": totales, "sin_libro": sin_libro(),
            "ilegibles": ilegibles}


def recortar_para_tablero(respuesta: dict) -> dict:
    """Lo que ve una sesion `tablero` (spec seccion 9, ruling 15.3): totales
    + origen + host + proposito + estado; SIN `carga`, SIN `quien.chat` y
    SIN `destino.url` (la carga de un /web es el mensaje crudo de Pedro y el
    tablero no ve chats)."""
    recortados = []
    for c in respuesta["cruces"]:
        q = dict(c.get("quien") or {})
        q.pop("chat", None)
        recortados.append({
            "ts": c.get("ts"), "id": c.get("id"), "quien": q,
            "proposito": c.get("proposito"),
            "destino": {"host": (c.get("destino") or {}).get("host")},
            "resultado": c.get("resultado"), "declarado": c.get("declarado"),
            "motivo": c.get("motivo")})
    return dict(respuesta, cruces=recortados)
