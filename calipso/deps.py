#!/usr/bin/env python3
"""
calipso/deps.py — Calipso instala dependencias cuando las necesita.

Filosofía: una dependencia faltante NO es un roadblock que se salta. Es algo que
se diagnostica y se resuelve. Cuando una herramienta requiere un paquete que no
está, Calipso lo instala (pip + pasos post-instalación, ej. descargar el
navegador de Playwright) y deja la capacidad lista.

Uso típico desde una herramienta:
    from calipso import deps
    deps.ensure("browser", quien)   # instala si hace falta; idempotente
    from playwright.sync_api import sync_playwright
"""
from __future__ import annotations

import importlib
import pathlib
import subprocess
import sys

from calipso import aduana

# Capacidades conocidas: qué hay que instalar para habilitar cada una.
TOOLS: dict[str, dict] = {
    "browser": {
        "module": "playwright",
        "pip": ["playwright"],
        "post": [[sys.executable, "-m", "playwright", "install", "chromium"]],
        "desc": "Navegador real (Playwright + Chromium): render de páginas JS, "
                "screenshots y click-test de la UI.",
    },
    # Futuras capacidades se agregan aquí (imágenes, pdf, audio, etc.)
}


def _importable(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False


def _browser_ready() -> bool:
    if not _importable("playwright"):
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return pathlib.Path(p.chromium.executable_path).exists()
    except Exception:
        return False


def is_ready(tool: str) -> bool:
    spec = TOOLS.get(tool)
    if not spec:
        return False
    if tool == "browser":
        return _browser_ready()
    return _importable(spec["module"])


def status() -> dict:
    return {name: {"ready": is_ready(name), "desc": spec["desc"]}
            for name, spec in TOOLS.items()}


class InstalacionFallida(Exception):
    """`returncode != 0`: se levanta ADENTRO del cruce para que el libro diga
    `fallo` (un pip que falla no es un cruce `ok`), y se traga en `_run`."""


def _destino_de(cmd: list[str]) -> str | None:
    """Nominal: lo que el sitio sabe, no el host resuelto (pip y playwright
    deciden solos a donde van)."""
    if "pip" in cmd:
        return "pypi.org"
    if "playwright" in cmd:
        return "cdn.playwright.dev"
    return None


def _run(cmd: list[str], log: list[str], quien: aduana.Quien,
         timeout: int = 600) -> bool:
    """La unica funcion de este modulo que ejecuta: el `with` de la aduana
    vive aca. `carga` es el argv (saneo lexico); los bytes son lo unico
    medible, stdout + stderr."""
    try:
        with aduana.cruzar(quien, "instalar dependencia",
                           destino=_destino_de(cmd), carga=cmd) as cruce:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                               encoding="utf-8", errors="replace")
            cruce.entro(len(r.stdout or "") + len(r.stderr or ""))
            tail = (r.stdout or "")[-300:] + (r.stderr or "")[-300:]
            log.append(f"$ {' '.join(cmd)}\n{tail.strip()}")
            if r.returncode != 0:
                raise InstalacionFallida(r.returncode)
        return True
    except InstalacionFallida:
        return False
    except Exception as e:
        log.append(f"$ {' '.join(cmd)}\nERROR: {e}")
        return False


def ensure(tool: str, quien: aduana.Quien, run_post: bool = True) -> dict:
    """Garantiza que la capacidad esté lista. Instala si falta. Idempotente.
    `quien` es el de la operacion que la necesito (el turno, el gesto)."""
    spec = TOOLS.get(tool)
    if not spec:
        return {"ok": False, "tool": tool, "error": "herramienta desconocida"}

    log: list[str] = []
    already = _importable(spec["module"])
    ok = True
    if not already:
        ok = _run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                   *spec["pip"]], log, quien)
    # pasos post (descargar navegador, etc.) — idempotentes, se corren igual
    if ok and run_post:
        for cmd in spec.get("post", []):
            ok = _run(cmd, log, quien) and ok
    ready = is_ready(tool)
    return {"ok": ok and ready, "tool": tool, "already": already,
            "ready": ready, "log": log}


if __name__ == "__main__":
    import json
    print(json.dumps(status(), indent=2, ensure_ascii=False))
