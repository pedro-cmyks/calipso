"""
calipso/permisos/almacen.py — Lo que sobrevive al reinicio.

Tres archivos, con tres vidas distintas, y por eso tres archivos y no uno:

  ~/.calipso/permisos.json              CONFIGURACION de Pedro. Los permisos
                                        permanentes concedidos, el techo de
                                        plata y las listas de pre-autorizados
                                        de los departamentos. Cambia poco, la
                                        escribe Pedro, y perderla es perder
                                        decisiones suyas. El spec la nombra
                                        por su ruta (5.4).
  ~/.calipso/permisos/solicitudes.json  ESTADO. Los prompts pendientes y las
                                        solicitudes estacionadas. Cambia en
                                        cada accion que pregunta. Meterla en
                                        el archivo de arriba haria que cada
                                        prompt reescriba la configuracion de
                                        Pedro, y un corte a mitad de esa
                                        escritura le costaria sus permisos.
  ~/.calipso/permisos/registro.jsonl    RASTRO. Una linea por decision, append
                                        only, nunca se edita. Es lo que hace
                                        auditable todo lo demas (5.4): deja
                                        rastro se haya preguntado o no.

Las dos escrituras de json copian, tal cual, la solucion de
`calipso/plantel/interruptor.py`: temporal en el mismo directorio +
`os.replace`, todo bajo `candado`. No es gusto por la simetria. `write_text`
trunca EN EL LUGAR, asi que un lector concurrente ve un json a medias, la
lectura falla, y el codigo cae a su default -- y aca el default de "no pude
leer los permisos" tiene que ser el lado seguro, no el permisivo. Con
`os.replace` el lector ve el contenido viejo o el nuevo, nunca uno a medias;
con el candado, dos escritores no se pisan entre procesos (el server y una
rutina de dispatch escriben lo mismo). Eso costo cinco rondas de arreglo en
el interruptor; aca se copia en vez de repetirlas.

Y una asimetria deliberada en como se falla:

  permisos.json ilegible  -> se sigue SIN permisos concedidos. Todo pregunta.
                             Molesto, seguro.
  solicitudes.json ilegible -> ErrorPermisos, y el motor NIEGA. No se puede
                             saber que quedo estacionado, y sin saberlo la
                             pared de 5.6.4 no existe: dejar pasar seria
                             exactamente el rodeo que esa regla prohibe.
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import pathlib
import threading
import uuid

from calipso.economia.candado import candado

from .acciones import (Accion, Contexto, ErrorPermisos, calipso_home, cubre,
                       TECHOS_DEFECTO)

ESTADO_PENDIENTE = "pendiente"
ESTADO_ESTACIONADA = "estacionada"
ESTADO_APROBADA = "aprobada"
ESTADO_NEGADA = "negada"
ESTADO_EJECUTANDO = "ejecutando"
ESTADO_EJECUTADA = "ejecutada"
ESTADO_FALLIDA = "fallida"

# Lo que todavia espera una respuesta de Pedro. Estos son los que ponen la
# pared: mientras una forma este aca, esa misma forma no pasa por ningun
# otro lado.
ESTADOS_ABIERTOS = (ESTADO_PENDIENTE, ESTADO_ESTACIONADA)

RESPUESTAS = ("si", "si_siempre", "no", "no_siempre")

# El signo de una regla permanente. Vive en la MISMA lista `concedidos`
# porque `revocar`, su endpoint y su boton ya cuelgan de esa lista: con un
# campo, el "no para siempre" nace revocable y visible sin una linea de
# revocacion nueva. `config()` no normaliza los dicts que lee del disco, asi
# que el default se aplica SIEMPRE al comparar (`.get("efecto", "permitir")`)
# y nunca confiando en que la escritura lo puso.
EFECTOS = ("permitir", "denegar")

# El default de 5.6, "que es de Pedro cambiar (asi no queda vacio)": lo que
# un departamento puede hacer de noche sin preguntarle a nadie. Comandos de
# LECTURA del allowlist y la suite de tests; nada de red, nada de instalar,
# nada irreversible, y ninguna accion de plata -- acunar de noche siempre
# se estaciona. Escribir dentro de ~/.calipso y de la raiz del proyecto del
# departamento ya es DIRECTO por 5.3, asi que no necesita estar en esta
# lista: la lista es solo para lo que, sin ella, preguntaria.
PREAUTORIZADO_DEFECTO = [
    {"familia": "comando", "operacion": "allowlist", "forma": {"id": "git_status"}},
    {"familia": "comando", "operacion": "allowlist", "forma": {"id": "git_diff"}},
    {"familia": "comando", "operacion": "allowlist", "forma": {"id": "git_diff_staged"}},
    {"familia": "comando", "operacion": "allowlist", "forma": {"id": "git_log"}},
    {"familia": "comando", "operacion": "allowlist", "forma": {"id": "test_all"}},
]


def ruta_permisos() -> pathlib.Path:
    return calipso_home() / "permisos.json"


def _carpeta() -> pathlib.Path:
    return calipso_home() / "permisos"


def ruta_solicitudes() -> pathlib.Path:
    return _carpeta() / "solicitudes.json"


def ruta_registro() -> pathlib.Path:
    return _carpeta() / "registro.jsonl"


def _ahora() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _id(prefijo: str) -> str:
    return f"{prefijo}_{uuid.uuid4().hex[:12]}"


def _guardar(p: pathlib.Path, d: dict) -> None:
    """Atomico: ver el docstring del modulo. Copiado de
    plantel/interruptor.py:_guardar."""
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.tmp{os.getpid()}.{threading.get_ident()}")
    try:
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, p)
    finally:
        # si el replace no llego a pasar (disco lleno, permisos) no dejamos
        # el temporal tirado
        with contextlib.suppress(OSError):
            tmp.unlink()


# --------------------------------------------------------------------------
# permisos.json -- la configuracion de Pedro
# --------------------------------------------------------------------------

def _config_vacia() -> dict:
    return {"version": 1, "techos": dict(TECHOS_DEFECTO),
            "concedidos": [], "preautorizados": {}}


def config() -> dict:
    """Un archivo ausente o ilegible da la configuracion VACIA: sin ningun
    permiso concedido, con los techos por defecto. El lado seguro es el
    conjunto chico -- si los permisos de Pedro no se pueden leer, se
    pregunta de mas, no se deja pasar de mas."""
    p = ruta_permisos()
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _config_vacia()
    if not isinstance(d, dict):
        return _config_vacia()
    base = _config_vacia()
    base["techos"] = {**base["techos"], **(d.get("techos") or {})}
    base["concedidos"] = [c for c in (d.get("concedidos") or [])
                          if isinstance(c, dict)]
    pre = d.get("preautorizados")
    base["preautorizados"] = pre if isinstance(pre, dict) else {}
    return base


def techos() -> dict:
    return config()["techos"]


def poner_techo(nombre: str, valor: int) -> dict:
    if not isinstance(valor, int) or isinstance(valor, bool) or valor < 0:
        raise ErrorPermisos(f"un techo es un entero >= 0: {valor!r}")
    with candado(ruta_permisos()):
        d = config()
        d["techos"][nombre] = valor
        _guardar(ruta_permisos(), d)
        return d["techos"]


def concedidos() -> list[dict]:
    return config()["concedidos"]


def preautorizados(departamento: str | None) -> list[dict]:
    """La lista del departamento, o el default del spec si no declaro
    ninguna. Un departamento que declara `[]` explicitamente se queda sin
    nada: declarar la lista vacia es una decision, no un olvido."""
    d = config()["preautorizados"]
    if departamento and departamento in d:
        lista = d.get(departamento)
        return [x for x in (lista or []) if isinstance(x, dict)]
    return list(PREAUTORIZADO_DEFECTO)


def regla_que_cubre(a: Accion, efecto: str) -> dict | None:
    for regla in concedidos():
        if regla.get("efecto", "permitir") == efecto and cubre(regla, a):
            return regla
    return None


def cubierta_por_permiso(a: Accion) -> dict | None:
    """El si permanente. Se deja con su nombre y su firma de siempre para no
    tocar al llamador de `motor.evaluar`."""
    return regla_que_cubre(a, "permitir")


def cubierta_por_preautorizacion(a: Accion, departamento: str | None) -> dict | None:
    for permiso in preautorizados(departamento):
        if cubre(permiso, a):
            return permiso
    return None


def anotar_regla(a: Accion, ctx: Contexto, texto: str,
                 siempre_pregunta: bool = False, forma: dict | None = None,
                 efecto: str = "permitir") -> dict:
    """La regla permanente de 5.4, en sus dos signos. Guarda cuando se
    escribio, desde que chat y con que texto exacto.

    El SI se NIEGA sobre lo que pregunta siempre, y la negativa vive aca y
    no solo en el endpoint: es la ultima linea antes del disco, asi que
    ningun llamador futuro -- ni un endpoint nuevo, ni el motor -- puede
    escribir por accidente un si permanente sobre un git push o sobre una
    acunacion. El NO no tiene esa restriccion a proposito: lo que pregunta
    siempre es lo irreversible, y un no permanente sobre eso falla hacia el
    lado conservador.

    `forma` permite escribir una forma MAS ANCHA que la de la accion
    -- "escribir bajo ~/Downloads" en vez de ese archivo suelto -- pero solo
    cuando esa forma efectivamente tapa la accion que se esta contestando:
    nadie escribe una regla que no cubre lo que tiene delante. Vale para los
    dos signos, y para el no importa mas: una regla de negar demasiado ancha
    es un bloqueo silencioso, porque el motor niega antes de crear la
    solicitud y no aparece nada en ninguna bandeja.

    Y escribir una regla BORRA la contraria que cubra esta misma accion, en
    la misma escritura. Si no, revocar el "no" devolveria en silencio el
    "si" viejo en vez de devolver la pregunta, que es exactamente la trampa
    que la regla 3 del spec quiere evitar.
    """
    if efecto not in EFECTOS:
        raise ErrorPermisos(f"efecto invalido: {efecto!r} (son {EFECTOS})")
    if siempre_pregunta and efecto == "permitir":
        raise ErrorPermisos(
            "esta operacion pregunta siempre (5.4): no admite permiso "
            "permanente")
    regla = {"id": _id("per"), "ts": _ahora(),
             "familia": a.familia, "operacion": a.operacion,
             "forma": dict(forma) if forma else dict(a.forma),
             "efecto": efecto,
             "chat": ctx.chat, "origen": ctx.origen, "texto": texto}
    if not cubre(regla, a):
        raise ErrorPermisos(
            "la forma de la regla no cubre la accion que se esta contestando")
    contraria = "denegar" if efecto == "permitir" else "permitir"
    with candado(ruta_permisos()):
        d = config()
        d["concedidos"] = [r for r in d["concedidos"]
                           if not (r.get("efecto", "permitir") == contraria
                                   and cubre(r, a))]
        d["concedidos"].append(regla)
        _guardar(ruta_permisos(), d)
    return regla


def conceder(a: Accion, ctx: Contexto, texto: str,
             siempre_pregunta: bool = False, forma: dict | None = None) -> dict:
    """El si permanente. Envoltorio de `anotar_regla` con su firma de
    siempre: lo llaman el motor y los tests, y cambiarles la firma no
    agregaria nada."""
    return anotar_regla(a, ctx, texto, siempre_pregunta, forma,
                        efecto="permitir")


def revocar(id_permiso: str) -> bool:
    with candado(ruta_permisos()):
        d = config()
        revocada = next((c for c in d["concedidos"]
                         if c.get("id") == id_permiso), None)
        if revocada is None:
            return False
        d["concedidos"] = [c for c in d["concedidos"]
                           if c.get("id") != id_permiso]
        _guardar(ruta_permisos(), d)
        # revocar una regla de negar devuelve el futuro. Sin esta linea no
        # queda en ningun lado cuando dejo de valer, y el rastro de 5.4
        # tendria un agujero justo en el unico evento que reabre un caudal.
        anotar({"evento": "revocacion", "permiso": id_permiso,
                "efecto": revocada.get("efecto", "permitir"),
                "familia": revocada.get("familia"),
                "operacion": revocada.get("operacion"),
                "forma": revocada.get("forma")})
        return True


# --------------------------------------------------------------------------
# solicitudes.json -- el estado
# --------------------------------------------------------------------------

def _leer_solicitudes() -> dict:
    """Ausente = nunca hubo solicitudes, y eso es legitimo. PRESENTE pero
    ilegible es otra cosa, y no se puede tratar igual: adentro puede haber
    una solicitud estacionada, y sin poder leerla la pared de 5.6.4 no
    existe. Levanta, y el motor niega."""
    p = ruta_solicitudes()
    if not p.exists():
        return {"version": 1, "solicitudes": []}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ErrorPermisos(
            f"no se pueden leer las solicitudes ({p}): {exc}") from None
    if not isinstance(d, dict) or not isinstance(d.get("solicitudes"), list):
        raise ErrorPermisos(f"solicitudes ilegibles: {p}")
    return d


def solicitudes() -> list[dict]:
    return _leer_solicitudes()["solicitudes"]


def obtener(id_solicitud: str) -> dict | None:
    for s in solicitudes():
        if s.get("id") == id_solicitud:
            return s
    return None


def abiertas() -> list[dict]:
    return [s for s in solicitudes() if s.get("estado") in ESTADOS_ABIERTOS]


def por_forma(clave: str) -> dict | None:
    """La solicitud abierta que ya puso la pared sobre esta forma exacta,
    venga del departamento que venga y del chat que venga."""
    for s in abiertas():
        if s.get("clave") == clave:
            return s
    return None


def por_corrida(corrida: str | None) -> dict | None:
    """La solicitud que ESTACIONO esta corrida. La marca no se levanta
    cuando Pedro aprueba: la corrida ya termino (5.6.2), y la rutina
    retoma en la PROXIMA, con un id nuevo. Cualquier cosa que siga
    saliendo de la corrida vieja es un rodeo."""
    if not corrida:
        return None
    for s in solicitudes():
        if s.get("estaciono_corrida") and \
                (s.get("contexto") or {}).get("corrida") == corrida:
            return s
    return None


def _escribir(d: dict) -> None:
    _guardar(ruta_solicitudes(), d)


def crear(a: Accion, ctx: Contexto, estado: str, nivel: str, motivo: str,
          siempre_pregunta: bool, texto: str) -> dict:
    if estado not in ESTADOS_ABIERTOS:
        raise ErrorPermisos(f"una solicitud nace abierta: {estado!r}")
    with candado(ruta_solicitudes()):
        d = _leer_solicitudes()
        # idempotente por forma: si la misma forma ya esta abierta, no se
        # crea una segunda -- se devuelve la que ya puso la pared
        clave = a.clave()
        for s in d["solicitudes"]:
            if s.get("clave") == clave and s.get("estado") in ESTADOS_ABIERTOS:
                return dict(s)
        s = {"id": _id("sol"), "ts": _ahora(), "estado": estado,
             "clave": clave, "accion": a.a_dict(), "contexto": ctx.a_dict(),
             "nivel": nivel, "motivo": motivo,
             "siempre_pregunta": bool(siempre_pregunta), "texto": texto,
             "estaciono_corrida": bool(estado == ESTADO_ESTACIONADA
                                       and ctx.corrida),
             "intentos": [], "respondida": None, "resultado": None}
        d["solicitudes"].append(s)
        _escribir(d)
        return dict(s)


def anotar_intento(id_solicitud: str, a: Accion, ctx: Contexto,
                   que: str) -> dict | None:
    """El rodeo queda anotado EN LA SOLICITUD (5.6.4), que es donde Pedro
    lo va a ver: no en un log aparte que nadie abre."""
    with candado(ruta_solicitudes()):
        d = _leer_solicitudes()
        for s in d["solicitudes"]:
            if s.get("id") == id_solicitud:
                s.setdefault("intentos", []).append(
                    {"ts": _ahora(), "que": que, "accion": a.a_dict(),
                     "contexto": ctx.a_dict()})
                _escribir(d)
                return dict(s)
    return None


def responder(id_solicitud: str, respuesta: str, quien: str) -> dict:
    """Las tres salidas de 5.4. `si_siempre` no concede aca -- solo marca
    la solicitud; el permiso lo escribe el motor con `conceder`, que es
    quien se niega sobre lo irreversible."""
    if respuesta not in RESPUESTAS:
        raise ErrorPermisos(
            f"respuesta invalida: {respuesta!r} (son {RESPUESTAS})")
    with candado(ruta_solicitudes()):
        d = _leer_solicitudes()
        for s in d["solicitudes"]:
            if s.get("id") != id_solicitud:
                continue
            if s.get("estado") not in ESTADOS_ABIERTOS:
                raise ErrorPermisos(
                    f"la solicitud ya esta {s.get('estado')}: {id_solicitud}")
            if respuesta == "si_siempre" and s.get("siempre_pregunta"):
                raise ErrorPermisos(
                    "esta operacion pregunta siempre (5.4): no admite "
                    "permiso permanente")
            s["estado"] = (ESTADO_APROBADA if respuesta in ("si", "si_siempre")
                           else ESTADO_NEGADA)
            s["respondida"] = {"ts": _ahora(), "respuesta": respuesta,
                               "quien": quien}
            _escribir(d)
            return dict(s)
    raise ErrorPermisos(f"solicitud inexistente: {id_solicitud}")


def tomar_para_ejecutar(id_solicitud: str) -> dict | None:
    """aprobada -> ejecutando, en UNA sola operacion bajo candado.

    Sin esto, contestar que si dos veces (dos pestanas, un doble toque, un
    reintento de la red) acuna dos veces, y el libro es append-only: la
    segunda moneda no se devuelve. El que pierde la carrera ve la
    solicitud ya en `ejecutando` y se vuelve con None."""
    with candado(ruta_solicitudes()):
        d = _leer_solicitudes()
        for s in d["solicitudes"]:
            if s.get("id") == id_solicitud:
                if s.get("estado") != ESTADO_APROBADA:
                    return None
                s["estado"] = ESTADO_EJECUTANDO
                _escribir(d)
                return dict(s)
    return None


def cerrar_ejecucion(id_solicitud: str, ok: bool, resultado: dict) -> dict | None:
    with candado(ruta_solicitudes()):
        d = _leer_solicitudes()
        for s in d["solicitudes"]:
            if s.get("id") == id_solicitud:
                s["estado"] = ESTADO_EJECUTADA if ok else ESTADO_FALLIDA
                s["resultado"] = resultado
                s["cerrada_ts"] = _ahora()
                _escribir(d)
                return dict(s)
    return None


# --------------------------------------------------------------------------
# registro.jsonl -- el rastro
# --------------------------------------------------------------------------

def anotar(linea: dict) -> None:
    """Append puro, como `cola._apilar`: una linea corta abierta en modo
    "a" no se entrelaza con la de otro proceso. Nunca levanta: que el
    rastro falle no puede volverse una forma de bloquear -- ni de permitir
    -- una accion."""
    try:
        p = ruta_registro()
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": _ahora(), **linea}, ensure_ascii=False,
                               separators=(",", ":")) + "\n")
            f.flush()
    except OSError:
        pass


def registro(limite: int = 200) -> list[dict]:
    p = ruta_registro()
    if not p.exists():
        return []
    try:
        lineas = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for linea in lineas[-limite:]:
        if not linea.strip():
            continue
        try:
            out.append(json.loads(linea))
        except ValueError:
            continue
    return out
