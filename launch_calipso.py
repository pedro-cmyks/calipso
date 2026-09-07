#!/usr/bin/env python3
"""
Arranca Calipso y abre el navegador.

Uso:
  python launch_calipso.py

Este archivo existe para que Calipso se sienta como aplicacion: si el servidor
no esta prendido, lo prende; espera a que responda; abre la URL.

La URL va SIN token (revision de seguridad 2026-09-07, C4): con ?token= la
credencial quedaba en el historial del navegador (que con sync viaja a la
nube), en el argv de xdg-open visible en /proc, y en el access log. La
primera vez en un navegador se entra por /login con TOTP y la cookie dura.
"""
from __future__ import annotations

import os
import pathlib
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = pathlib.Path(__file__).resolve().parent
HOST = os.environ.get("CALIPSO_HOST", "127.0.0.1")
PORT = int(os.environ.get("CALIPSO_PORT", "8000"))


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def _wait_ready(url: str, seconds: int = 45) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.5) as r:
                return r.status < 500
        except Exception:
            time.sleep(0.5)
    return False


def main() -> int:
    url = f"http://{HOST}:{PORT}/"

    if _port_open(HOST, PORT):
        print(f"[calipso] Ya esta prendido: {url}")
        webbrowser.open(url)
        return 0

    env = dict(os.environ)
    env.setdefault("CALIPSO_ROOT", str(ROOT))
    print("[calipso] Prendiendo servidor local...")
    proc = subprocess.Popen(
        [sys.executable, "calipso/server.py"],
        cwd=str(ROOT),
        env=env,
    )
    if not _wait_ready(url):
        print("[calipso] No alcanzo a arrancar. Revisa la ventana de consola.")
        return 1

    print(f"[calipso] Listo: {url}")
    webbrowser.open(url)
    print("[calipso] Deja esta ventana abierta mientras uses Calipso.")
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
