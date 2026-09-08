"""
calipso/sesiones.py — Quien entra: identidad de APARATO, no de agente.

El token de `~/.calipso/token` identifica a la maquina de Pedro y por eso
vale solo desde loopback. Un aparato remoto (el lector, el celular, la PWA)
necesita otra credencial, y esta capa es esa: el aparato GOLPEA, Pedro
aprueba desde la Ally, y el aparato CANJEA una vez el id de sesion que
viaja despues en la cookie `calipso_sesion`.

Tres decisiones que explican casi todo el archivo:

  El disco guarda `sha256(id)`, jamas el id en claro. Asi `sesiones.json`
  deja de ser una credencial robable: quien lo lea se lleva hashes. De ahi
  sale el ruling que mueve la generacion del id al CANJE y no a la
  aprobacion -- entre que Pedro aprueba y el aparato canjea pueden pasar
  minutos, y guardar el id en claro mientras tanto (o tenerlo solo en
  memoria, y perderlo en un reinicio) es exactamente lo que no se puede.
  El registro vive "viva sin hash" en ese hueco, y `resolver` no lo matchea
  nunca.

  Ausente no es lo mismo que ILEGIBLE. Ausente es un almacen que todavia no
  nacio. Ilegible se preserva (`sesiones.json.corrupto-<ts>`) antes de
  escribir nada, y se avisa: adentro puede estar la unica sesion viva de un
  aparato al que Pedro no tiene acceso fisico. El molde es
  `permisos/almacen.py:_leer_solicitudes`, NO `config()`, que pisa en
  silencio.

  Este modulo es SINCRONO y toma un flock para escribir. El flock JAMAS
  puede tomarse en el event loop (la trampa que ya obligo a `to_thread` en
  `economia_brief`): quien llame a `golpear`, `aprobar`, `rechazar`,
  `revocar`, `canjear` o `crear_viva` desde un endpoint async lo envuelve en
  `asyncio.to_thread`. Las lecturas (`resolver`, `estado`, `listar`) no
  toman candado -- se apoyan en una cache por stat del archivo -- salvo
  cuando `resolver` renueva o mata, que es raro por la histeresis.

Los plazos son de dias, asi que todo lo que mira la hora pasa por `_reloj`
(inyectable en tests, igual que `_login_reloj` en server.py).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import secrets
import sys
import time

from calipso.economia.candado import candado, escribir_json_atomico
from calipso.permisos.acciones import calipso_home

# Los plazos del spec. Dormida 30 dias o nacida hace 180 = muerta; el golpe
# de un aparato dura lo que dura el aparato sondeando en vivo.
SESION_SUENO_DIAS = 30
SESION_VIDA_MAX_DIAS = 180
GOLPE_TTL_MIN = 10
GOLPES_PENDIENTES_MAX = 5

# Renovar `ultima_vez` en cada request seria una escritura con flock por
# request. Una hora de histeresis lo baja a 24 escrituras por dia por
# aparato y no cambia en nada el plazo de 30 dias.
RENOVACION_HISTERESIS_S = 3600

# `aparato` es input NO autenticado que termina en la UI de /fabrica.
APARATO_MAX = 60

_DIA_S = 86400

# Reglas por tipo de aparato: `(prefijo, metodos)`, con "*" para "todos".
# Fail-closed: lo que no matchea ninguna regla queda afuera. El criterio del
# tablero es fijo -- ver todo, firmar mesa y permisos, jamas tocar la
# maquina (nada de /api/file, /api/commands, /api/config, /api/project). La
# tabla vive aca porque es del ALMACEN: el guard la consume, no la define.
ALCANCES: dict[str, tuple] = {
    "navegador": (("*", "*"),),
    "lector": (("/api/lectura/", "*"),),
    "tablero": (
        ("/fabrica", ("GET",)),
        ("/static", ("GET",)),
        ("/ws/mapa", ("GET",)),
        ("/api/mapa/", ("GET",)),
        ("/api/economia/", ("GET",)),
        ("/api/permisos", ("GET",)),
        ("/api/inbox", ("GET",)),
        ("/api/economia/bus/", ("POST",)),
        ("/api/permisos/responder", ("POST",)),
    ),
}

ESTADO_GOLPEANDO = "golpeando"
ESTADO_VIVA = "viva"
ESTADO_REVOCADA = "revocada"
ESTADO_RECHAZADA = "rechazada"

_reloj = time.time          # inyectable en tests


class Lleno(Exception):
    """Ya hay GOLPES_PENDIENTES_MAX golpes vigentes. Es distinto de
    ValueError a proposito: esto no es un pedido invalido (422) sino un
    almacen ocupado (429), y el aparato legitimo reintenta cuando los
    vencidos caduquen."""


def _ruta() -> pathlib.Path:
    """Resuelta en CADA llamada: `CALIPSO_HOME` puede cambiar despues de
    que este modulo se importo (y en la suite, cambia)."""
    return calipso_home() / "sesiones.json"


def _avisar(mensaje: str) -> None:
    print(f"[sesiones] {mensaje}", file=sys.stderr)


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(
        ts, datetime.timezone.utc).isoformat()


def _epoch(iso: str | None) -> float:
    """Fecha ilegible = epoch 0, o sea vencida. Fail-closed: un registro con
    la fecha rota muere en vez de vivir para siempre."""
    try:
        return datetime.datetime.fromisoformat(iso).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _hash(id_en_claro: str) -> str:
    return hashlib.sha256(id_en_claro.encode("utf-8")).hexdigest()


def _vacio() -> dict:
    return {"version": 1, "sesiones": []}


def _cache_vacia() -> dict:
    return {"clave": None, "datos": None, "motivo": None}


# La clave es el stat del archivo, no un timestamp propio: `os.replace` deja
# un inodo nuevo, asi que la escritura de OTRO proceso (dispatch, un segundo
# server) invalida esta cache sola, sin que nadie tenga que acordarse.
_CACHE: dict = _cache_vacia()


def _leer_disco() -> tuple[dict, str | None]:
    """(datos, motivo_ilegible). Sin efectos: quien decide que hacer con un
    archivo ilegible es el llamador, porque leer y mutar hacen cosas
    distintas (la lectura falla cerrado, la mutacion preserva y avisa)."""
    p = _ruta()
    try:
        crudo = p.read_text(encoding="utf-8")
    except FileNotFoundError:
        return _vacio(), None
    except OSError as exc:
        return _vacio(), f"no se puede leer {p}: {exc}"
    try:
        datos = json.loads(crudo)
    except ValueError as exc:
        return _vacio(), f"json invalido en {p}: {exc}"
    if not isinstance(datos, dict) or not isinstance(datos.get("sesiones"),
                                                     list):
        return _vacio(), f"forma inesperada en {p}"
    if not all(isinstance(s, dict) for s in datos["sesiones"]):
        return _vacio(), f"registros que no son objetos en {p}"
    return datos, None


def _leer() -> dict:
    """La lectura de los caminos calientes: sin candado y casi siempre sin
    tocar el disco (un `os.stat`). Un archivo ilegible se lee como vacio --
    ninguna sesion resuelve -- y se avisa una sola vez por version del
    archivo, que es lo que evita que el aviso salga en cada request.

    El dict que devuelve es EL de la cache, compartido con la proxima
    llamada: quien lo lea copia lo que se lleva. Mutar el almacen va
    siempre por `_leer_para_mutar` adentro del candado."""
    p = _ruta()
    try:
        st = os.stat(p)
        clave = (str(p), st.st_mtime_ns, st.st_size, st.st_ino)
    except OSError:
        clave = (str(p), None, None, None)
    if _CACHE["clave"] != clave:
        datos, motivo = _leer_disco()
        _CACHE.update({"clave": clave, "datos": datos, "motivo": motivo})
        if motivo:
            _avisar(f"almacen ilegible ({motivo}): ninguna sesion resuelve")
    return _CACHE["datos"]


def _leer_para_mutar() -> dict:
    """Solo desde adentro del candado. Un archivo ilegible se renombra ANTES
    de que la mutacion escriba: preservado y avisado, jamas pisado."""
    datos, motivo = _leer_disco()
    if motivo:
        p = _ruta()
        destino = p.with_name(f"{p.name}.corrupto-{int(_reloj())}")
        os.replace(p, destino)
        _avisar(f"almacen ilegible ({motivo}): preservado en "
                f"{destino.name}; se arranca vacio")
        _CACHE.update(_cache_vacia())
    return datos


def _escribir(datos: dict) -> None:
    """0600 de nacimiento: el archivo tiene hashes de credenciales, y
    `escribir_json_atomico` con `modo` evita la ventana en 0644 que dejaria
    un chmod despues del replace."""
    escribir_json_atomico(_ruta(), datos, modo=0o600)
    _CACHE.update(_cache_vacia())


# --------------------------------------------------------------------------
# el estado derivado del reloj
# --------------------------------------------------------------------------

def _golpe_vencido(reg: dict, ahora: float) -> bool:
    return ahora - _epoch(reg.get("creada")) >= GOLPE_TTL_MIN * 60


def _sesion_caduca(reg: dict, ahora: float) -> bool:
    """Dormida SESION_SUENO_DIAS, o mas vieja que SESION_VIDA_MAX_DIAS. Las
    dos por separado: usarla todos los dias no estira la vida maxima."""
    return (ahora - _epoch(reg.get("ultima_vez"))
            >= SESION_SUENO_DIAS * _DIA_S
            or ahora - _epoch(reg.get("creada"))
            >= SESION_VIDA_MAX_DIAS * _DIA_S)


def _efectivo(reg: dict, ahora: float) -> str:
    """Lo que /fabrica muestra. El archivo puede decir "viva" y el reloj
    decir que no: gana el reloj, porque la muerte la escribe la resolucion y
    esa sesion quizas no vuelva a resolverse nunca."""
    estado_guardado = reg.get("estado")
    if estado_guardado == ESTADO_GOLPEANDO:
        return "caduca" if _golpe_vencido(reg, ahora) else ESTADO_GOLPEANDO
    if estado_guardado == ESTADO_VIVA:
        return "caduca" if _sesion_caduca(reg, ahora) else ESTADO_VIVA
    if estado_guardado == ESTADO_RECHAZADA:
        return ESTADO_RECHAZADA
    # revocada, o un estado que no reconocemos (alguien edito el
    # archivo a mano): ni `estado` ni `resolver` le dan nada a un
    # registro asi, y la lista no puede sugerir lo contrario
    return ESTADO_REVOCADA


def _por_pedido(datos: dict, id_pedido: str) -> dict | None:
    for reg in datos["sesiones"]:
        if reg.get("id_pedido") == id_pedido:
            return reg
    return None


def _por_hash(datos: dict, hash_id: str) -> dict | None:
    for reg in datos["sesiones"]:
        if reg.get("hash_id") == hash_id:
            return reg
    return None


def _validar(aparato, tipo) -> tuple[str, str]:
    """ValueError es 422 en el endpoint: pedido invalido, y NO se estaciona
    nada. `isprintable` cubre los caracteres de control y de yapa los
    invisibles y los de direccion (un nombre con un RTL override entra a la
    UI de /fabrica disfrazado de otro)."""
    if tipo not in ALCANCES:
        raise ValueError(f"tipo de aparato desconocido: {tipo!r}")
    if not isinstance(aparato, str):
        raise ValueError("el nombre del aparato tiene que ser texto")
    nombre = aparato.strip()
    if not nombre:
        raise ValueError("el aparato necesita un nombre")
    if len(nombre) > APARATO_MAX:
        raise ValueError(f"el nombre del aparato pasa de {APARATO_MAX}")
    if not nombre.isprintable():
        raise ValueError("el nombre del aparato tiene caracteres invisibles")
    return nombre, tipo


# --------------------------------------------------------------------------
# el ciclo de vida
# --------------------------------------------------------------------------

def golpear(aparato: str, tipo_sugerido: str) -> dict:
    """El aparato se anuncia y queda esperando a Pedro. El tipo es una
    SUGERENCIA: quien lo fija es Pedro al aprobar.

    Levanta ValueError (422) si el pedido no valida y Lleno (429) si ya hay
    GOLPES_PENDIENTES_MAX vigentes -- sin ese tope, cualquiera que llegue al
    endpoint llena el archivo y la lista de /fabrica.
    """
    nombre, tipo = _validar(aparato, tipo_sugerido)
    with candado(_ruta()):
        datos = _leer_para_mutar()
        ahora = _reloj()
        # los golpes vencidos no ocupan lugar ni ensucian la lista: se van
        # en la escritura del golpe siguiente, que es cuando molestan
        datos["sesiones"] = [s for s in datos["sesiones"]
                             if not (s.get("estado") == ESTADO_GOLPEANDO
                                     and _golpe_vencido(s, ahora))]
        vigentes = sum(1 for s in datos["sesiones"]
                       if s.get("estado") == ESTADO_GOLPEANDO)
        if vigentes >= GOLPES_PENDIENTES_MAX:
            raise Lleno(f"ya hay {vigentes} golpes esperando")
        registro = {"hash_id": None,
                    "id_pedido": secrets.token_urlsafe(32),
                    "aparato": nombre,
                    "tipo": tipo,
                    "creada": _iso(ahora),
                    "ultima_vez": _iso(ahora),
                    "estado": ESTADO_GOLPEANDO}
        datos["sesiones"].append(registro)
        _escribir(datos)
    return {"id_pedido": registro["id_pedido"]}


def aprobar(id_pedido: str, tipo: str) -> None:
    """Pedro dice que si, desde la Ally, y elige el tipo (el sugerido por el
    aparato ni se mira). No genera el id de sesion: eso pasa en el canje,
    para que el id en claro no espere en el disco los minutos que Pedro
    tarde. KeyError si el golpe no existe o ya vencio."""
    if tipo not in ALCANCES:
        raise ValueError(f"tipo de aparato desconocido: {tipo!r}")
    with candado(_ruta()):
        datos = _leer_para_mutar()
        registro = _por_pedido(datos, id_pedido) if id_pedido else None
        if (registro is None
                or registro.get("estado") != ESTADO_GOLPEANDO
                or _golpe_vencido(registro, _reloj())):
            raise KeyError(f"no hay un golpe vigente {id_pedido!r}")
        registro["tipo"] = tipo
        registro["estado"] = ESTADO_VIVA
        _escribir(datos)


def rechazar(id_pedido: str) -> None:
    """KeyError si no existe. Sin marcha atras: el aparato vuelve a
    golpear."""
    with candado(_ruta()):
        datos = _leer_para_mutar()
        registro = _por_pedido(datos, id_pedido) if id_pedido else None
        if registro is None:
            raise KeyError(f"pedido desconocido: {id_pedido!r}")
        registro["estado"] = ESTADO_RECHAZADA
        _escribir(datos)


def revocar(hash_id: str) -> None:
    """Corta una sesion viva. KeyError si no existe o si no esta viva --
    revocar dos veces no es un exito silencioso, es un pedido sobre algo que
    ya no esta."""
    with candado(_ruta()):
        datos = _leer_para_mutar()
        registro = _por_hash(datos, hash_id) if hash_id else None
        if registro is None or registro.get("estado") != ESTADO_VIVA:
            raise KeyError(f"no hay una sesion viva {hash_id!r}")
        registro["estado"] = ESTADO_REVOCADA
        _escribir(datos)


def canjear(id_pedido: str) -> str | None:
    """Entrega el id de sesion EN CLARO, una sola vez, y quema el
    `id_pedido`. Aca nace el id: se guarda su sha256 y el que devuelve esta
    funcion es el unico ejemplar en claro que existe -- si el aparato lo
    pierde, vuelve a golpear. Segundo canje, pedido desconocido, todavia sin
    aprobar, o una aprobacion que durmio hasta caducar = None.

    Lo ultimo es el reloj: una aprobacion que nadie canjeo envejece igual
    que una sesion entregada (invariante 5, dormida 30 dias o nacida hace
    180 = muerta) y `listar` ya la muestra "caduca". Sin mirar la hora aca,
    el almacen se contradecia: /fabrica la daba por muerta y el canje le
    entregaba una credencial en claro, renovandole la `ultima_vez` de
    yapa."""
    if not id_pedido:
        return None
    with candado(_ruta()):
        datos = _leer_para_mutar()
        registro = _por_pedido(datos, id_pedido)
        if (registro is None
                or registro.get("estado") != ESTADO_VIVA
                or registro.get("hash_id")
                or _sesion_caduca(registro, _reloj())):
            return None
        id_en_claro = secrets.token_urlsafe(32)
        registro["hash_id"] = _hash(id_en_claro)
        registro["id_pedido"] = None
        registro["ultima_vez"] = _iso(_reloj())
        _escribir(datos)
    return id_en_claro


def crear_viva(aparato: str, tipo: str) -> str:
    """Una sesion viva sin golpe previo, y devuelve el id EN CLARO. La usa
    `/login` + TOTP desde un aparato remoto: el TOTP es Pedro en persona, no
    un aparato aprobandose solo. Va por afuera del tope de pendientes a
    proposito -- componerla con golpear/aprobar/canjear dejaria que cinco
    golpes de un desconocido bloqueen el login de Pedro."""
    nombre, tipo = _validar(aparato, tipo)
    id_en_claro = secrets.token_urlsafe(32)
    with candado(_ruta()):
        datos = _leer_para_mutar()
        ahora = _reloj()
        datos["sesiones"].append({"hash_id": _hash(id_en_claro),
                                  "id_pedido": None,
                                  "aparato": nombre,
                                  "tipo": tipo,
                                  "creada": _iso(ahora),
                                  "ultima_vez": _iso(ahora),
                                  "estado": ESTADO_VIVA})
        _escribir(datos)
    return id_en_claro


# --------------------------------------------------------------------------
# consultas
# --------------------------------------------------------------------------

def estado(id_pedido: str) -> str | None:
    """Lo que sondea el aparato mientras espera. None es "no hay nada que
    esperar": pedido desconocido, vencido por TTL, o ya canjeado (el
    `id_pedido` se quemo). Nunca escribe."""
    if not id_pedido:
        return None
    registro = _por_pedido(_leer(), id_pedido)
    if registro is None:
        return None
    guardado = registro.get("estado")
    if guardado == ESTADO_GOLPEANDO and _golpe_vencido(registro, _reloj()):
        return None
    if guardado in (ESTADO_GOLPEANDO, ESTADO_VIVA, ESTADO_RECHAZADA):
        return guardado
    return None


def resolver(id_en_claro: str | None) -> dict | None:
    """El registro de la sesion de esa cookie, o None. Corre en CADA request
    con cookie de sesion, asi que el camino feliz es un `os.stat` y un
    sha256.

    Devuelve el registro mas `renovada`: True solo si ESTA llamada escribio
    `ultima_vez`. El guard lo usa para re-plantar la cookie con max_age
    fresco -- sin eso, un aparato que entra todos los dias perderia la
    cookie a los 30 dias con la sesion todavia viva.

    Una sesion vencida (dormida o pasada de la vida maxima) se marca
    revocada ACA: la mata la resolucion, no un cron.
    """
    if not id_en_claro:
        return None
    hash_id = _hash(id_en_claro)
    registro = _por_hash(_leer(), hash_id)
    if registro is None or registro.get("estado") != ESTADO_VIVA:
        return None
    ahora = _reloj()
    if _sesion_caduca(registro, ahora):
        with candado(_ruta()):
            datos = _leer_para_mutar()
            vencida = _por_hash(datos, hash_id)
            if vencida is not None and vencida.get("estado") == ESTADO_VIVA:
                vencida["estado"] = ESTADO_REVOCADA
                _escribir(datos)
        return None
    if ahora - _epoch(registro.get("ultima_vez")) <= RENOVACION_HISTERESIS_S:
        return dict(registro, renovada=False)
    with candado(_ruta()):
        # se relee adentro del candado: entre la lectura cacheada y esta
        # linea, otro proceso pudo revocar esta misma sesion
        datos = _leer_para_mutar()
        fresco = _por_hash(datos, hash_id)
        if fresco is None or fresco.get("estado") != ESTADO_VIVA:
            return None
        fresco["ultima_vez"] = _iso(ahora)
        _escribir(datos)
        return dict(fresco, renovada=True)


def listar() -> list[dict]:
    """Todo lo que hay, con el estado EFECTIVO derivado del reloj. Nunca
    escribe: /fabrica no miente, pero tampoco decide. Incluye `id_pedido`
    porque la UI aprueba por body, y el `hash_id` porque es con lo que se
    revoca (un hash no es una credencial)."""
    ahora = _reloj()
    salida = []
    for registro in _leer()["sesiones"]:
        fila = dict(registro)
        fila["efectivo"] = _efectivo(registro, ahora)
        salida.append(fila)
    return salida
