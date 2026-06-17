#!/usr/bin/env python3
"""
Arranca Calipso y abre el navegador.

Uso:
  python launch_calipso.py

Este archivo existe para que Calipso se sienta como aplicacion: si el servidor
no esta prendido, lo prende; espera a que responda; abre la URL con token.
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
TOKEN_FILE = pathlib.Path.home() / ".calipso" / "token"
HOST = os.environ.get("CALIPSO_HOST", "127.0.0.1")
PORT = int(os.environ.get("CALIPSO_PORT", "8000"))


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def _token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    return ""


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
    token = _token()
    open_url = url + (f"?token={token}" if token else "")

    if _port_open(HOST, PORT):
        print(f"[calipso] Ya esta prendido: {url}")
        webbrowser.open(open_url)
        return 0

    env = dict(os.environ)
    env.setdefault("CALIPSO_ROOT", str(ROOT))
    print("[calipso] Prendiendo servidor local...")
    proc = subprocess.Popen(
        [sys.executable, "calipso/server.py"],
        cwd=str(ROOT),
        env=env,
    )
    ready_url = open_url or url
    if not _wait_ready(ready_url):
        print("[calipso] No alcanzo a arrancar. Revisa la ventana de consola.")
        return 1

    token = _token()
    open_url = url + (f"?token={token}" if token else "")
    print(f"[calipso] Listo: {url}")
    webbrowser.open(open_url)
    print("[calipso] Deja esta ventana abierta mientras uses Calipso.")
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
