"""
calipso/plantel/interruptor.py — El estado operativo del plantel.

Esto gasta plata mientras Pedro duerme, asi que el freno no puede vivir solo
en memoria: sobrevive al reinicio del servidor y se toca desde el telefono.
El archivo es la verdad; el proceso lo relee en cada tic.
"""
from __future__ import annotations

import json
import os
import pathlib
import threading
from dataclasses import dataclass, replace

from calipso.economia.candado import candado

ARCHIVO = "plantel.json"
MODOS = ("ensayo", "vivo")


@dataclass(frozen=True)
class Estado:
    encendido: bool = True
    modo: str = "ensayo"      # arranca sin gastar: mira, decide y publica
    techo_tics: int = 200     # por departamento y por semana


def ruta(base) -> pathlib.Path:
    return pathlib.Path(base) / "economia" / ARCHIVO


def _crudo(base) -> dict:
    try:
        d = json.loads(ruta(base).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d if isinstance(d, dict) else {}


def _guardar(base, d: dict) -> None:
    """Atomico a proposito: write_text trunca en el lugar, asi que un lector
    concurrente veia un JSON a medias, _crudo devolvia {} y leer() caia al
    default MAS permisivo (encendido=True, techo 200). O sea que apretar
    parar mientras la fabrica escribia podia no parar nada. Con os.replace el
    lector ve el contenido viejo o el nuevo, nunca uno a medias."""
    p = ruta(base)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.tmp{os.getpid()}.{threading.get_ident()}")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


def _techo(d: dict) -> int:
    crudo = d.get("techo_tics")
    try:
        return int(crudo) if crudo is not None else Estado.techo_tics
    except (TypeError, ValueError):
        return Estado.techo_tics


def leer(base) -> Estado:
    """Un archivo ausente, ilegible o con un modo inventado da el estado por
    defecto. Corre al principio de cada tic: no puede ser una fuente de
    fallas nueva, y un modo raro no puede volverse permiso para gastar."""
    d = _crudo(base)
    modo = d.get("modo")
    return Estado(encendido=bool(d.get("encendido", True)),
                  modo=modo if modo in MODOS else "ensayo",
                  techo_tics=_techo(d))


def escribir(base, estado: Estado) -> Estado:
    """Conserva los contadores, que viven en el mismo archivo."""
    with candado(ruta(base)):
        d = _crudo(base)
        d.update({"encendido": estado.encendido, "modo": estado.modo,
                  "techo_tics": estado.techo_tics})
        _guardar(base, d)
    return estado


def parar(base) -> Estado:
    return escribir(base, replace(leer(base), encendido=False))


def reanudar(base) -> Estado:
    return escribir(base, replace(leer(base), encendido=True))


def poner_modo(base, modo: str) -> Estado:
    if modo not in MODOS:
        raise ValueError(f"modo invalido: {modo!r} (son {MODOS})")
    return escribir(base, replace(leer(base), modo=modo))


def puede_gastar(estado: Estado) -> bool:
    """En ensayo el jefe mira, decide y publica al pulso — pero no contrata
    ni paga. Es el modo en el que arranca."""
    return estado.encendido and estado.modo == "vivo"


def _clave(cuenta: str, semana: str) -> str:
    return f"{cuenta}|{semana}"


def tics(base, cuenta: str, semana: str) -> int:
    return int(_crudo(base).get("tics", {}).get(_clave(cuenta, semana), 0))


def anotar_tic(base, cuenta: str, semana: str) -> int:
    with candado(ruta(base)):
        d = _crudo(base)
        contadores = d.setdefault("tics", {})
        conteo = int(contadores.get(_clave(cuenta, semana), 0)) + 1
        contadores[_clave(cuenta, semana)] = conteo
        _guardar(base, d)
        return conteo


def hay_cuerda(base, estado: Estado, cuenta: str, semana: str) -> bool:
    """Falso cuando el departamento ya gasto su techo de tics de la semana:
    un bug que gire no puede vaciar la billetera."""
    return tics(base, cuenta, semana) < estado.techo_tics


def tomar_tic(base, cuenta: str, semana: str) -> bool:
    """Chequear el techo y anotar el tic, en una sola operacion atomica.

    Separadas dejaban una carrera: dos tics concurrentes del mismo
    departamento —el ticker de rutinas y el boton de correr a mano— leian el
    mismo contador y pasaban los dos, asi que el techo se aflojaba. Bajo
    candado, el que pierde ve el contador ya incrementado y se vuelve sin
    cuerda.

    El techo sale del MISMO dict que se lee bajo candado, no del `Estado`
    que el llamador leyo afuera: una lectura sin candado se puede topar con
    un archivo a medio escribir y traer un techo mas permisivo que el
    real."""
    with candado(ruta(base)):
        d = _crudo(base)
        techo = _techo(d)
        contadores = d.setdefault("tics", {})
        clave = _clave(cuenta, semana)
        if int(contadores.get(clave, 0)) >= techo:
            return False
        contadores[clave] = int(contadores.get(clave, 0)) + 1
        _guardar(base, d)
        return True
