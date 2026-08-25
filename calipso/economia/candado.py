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
import pathlib
import threading


class ErrorCandado(Exception):
    pass


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
                ent["profundidad"] -= 1
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
