"""
calipso/economia/candado.py — Escritor unico por archivo de libro.

Un flock exclusivo sobre <ruta>.lock protege entre PROCESOS (dispatch y
server escriben el mismo libro); un RLock por ruta protege entre HILOS
del mismo proceso (FastAPI sirve endpoints en threadpool) y hace el
candado REENTRANTE: la operacion puede tomarlo y llamar funciones que
tambien lo toman. Regla de uso: quien escribe toma el candado y
construye su estado (Kernel/Libro/Cola/...) DESPUES de adquirirlo —
nunca cachear escritores entre adquisiciones.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import pathlib
import threading


class ErrorCandado(Exception):
    pass


def escribir_json_atomico(ruta: pathlib.Path, datos) -> None:
    """Escribe un json de configuracion sin que exista un estado a medias.

    El candado de arriba resuelve la mitad del problema: que dos
    ESCRITORES no se pisen. Esta funcion resuelve la otra mitad, que el
    candado no toca: `Path.write_text` trunca EN EL LUGAR, asi que entre
    el truncate y el write el archivo existe con cero bytes -- y si la
    escritura se corta a la mitad (disco lleno, kill, RLIMIT), lo que
    queda en disco es json invalido. Para departamentos.json o
    suscripciones.json eso no es un archivo raro: es la economia ENTERA
    que deja de cargar, y el unico arreglo es abrir el archivo con un
    editor -- justo lo que los endpoints de configuracion vinieron a
    eliminar.

    Escribir un temporal en el MISMO directorio y `os.replace` lo hace
    indivisible: el lector ve el contenido viejo o el nuevo, nunca uno a
    medias, y una escritura cortada solo ensucia el temporal. Mismo
    patron que `permisos/almacen.py`, `consumo.py`, `routines.py` y
    `plantel/interruptor.py`; vive ACA para que economia tenga uno solo y
    no una quinta copia.
    """
    ruta = pathlib.Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(f"{ruta.name}.tmp{os.getpid()}."
                         f"{threading.get_ident()}")
    try:
        tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        os.replace(tmp, ruta)
    finally:
        # si el replace no llego a pasar (disco lleno, permisos) no dejamos
        # el temporal tirado
        with contextlib.suppress(OSError):
            tmp.unlink()


_guardia = threading.Lock()
_por_ruta: dict[str, dict] = {}


def _entrada(lock_path: str) -> dict:
    with _guardia:
        if lock_path not in _por_ruta:
            _por_ruta[lock_path] = {"rlock": threading.RLock(),
                                    "fd": None, "profundidad": 0}
        return _por_ruta[lock_path]


@contextlib.contextmanager
def candado(ruta: pathlib.Path, no_bloquear: bool = False):
    lock_path = str(pathlib.Path(str(ruta) + ".lock"))
    ent = _entrada(lock_path)
    if not ent["rlock"].acquire(blocking=not no_bloquear):
        raise ErrorCandado(f"candado tomado por otro hilo: {lock_path}")
    try:
        ent["profundidad"] += 1
        if ent["profundidad"] == 1:
            pathlib.Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
            f = open(lock_path, "a")
            flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if no_bloquear else 0)
            try:
                fcntl.flock(f.fileno(), flags)
            except BlockingIOError:
                f.close()
                raise ErrorCandado(
                    f"candado tomado por otro proceso: {lock_path}") from None
            ent["fd"] = f
        yield
    finally:
        ent["profundidad"] -= 1
        if ent["profundidad"] == 0 and ent["fd"] is not None:
            with contextlib.suppress(OSError):
                fcntl.flock(ent["fd"].fileno(), fcntl.LOCK_UN)
            ent["fd"].close()
            ent["fd"] = None
        ent["rlock"].release()
