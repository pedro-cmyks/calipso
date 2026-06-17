#!/usr/bin/env python3
"""
calipso/deps.py — Calipso instala dependencias cuando las necesita.

Filosofía: una dependencia faltante NO es un roadblock que se salta. Es algo que
se diagnostica y se resuelve. Cuando una herramienta requiere un paquete que no
está, Calipso lo instala (pip + pasos post-instalación, ej. descargar el
navegador de Playwright) y deja la capacidad lista.

Uso típico desde una herramienta:
    from calipso import deps
    deps.ensure("browser")      # instala si hace falta; idempotente
    from playwright.sync_api import sync_playwright
"""
from __future__ import annotations

import importlib
import pathlib
import subprocess
import sys

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


def _run(cmd: list[str], log: list[str], timeout: int = 600) -> bool:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")
        tail = (r.stdout or "")[-300:] + (r.stderr or "")[-300:]
        log.append(f"$ {' '.join(cmd)}\n{tail.strip()}")
        return r.returncode == 0
    except Exception as e:
        log.append(f"$ {' '.join(cmd)}\nERROR: {e}")
        return False


def ensure(tool: str, run_post: bool = True) -> dict:
    """Garantiza que la capacidad esté lista. Instala si falta. Idempotente."""
    spec = TOOLS.get(tool)
    if not spec:
        return {"ok": False, "tool": tool, "error": "herramienta desconocida"}

    log: list[str] = []
    already = _importable(spec["module"])
    ok = True
    if not already:
        ok = _run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
                   *spec["pip"]], log)
    # pasos post (descargar navegador, etc.) — idempotentes, se corren igual
    if ok and run_post:
        for cmd in spec.get("post", []):
            ok = _run(cmd, log) and ok
    ready = is_ready(tool)
    return {"ok": ok and ready, "tool": tool, "already": already,
            "ready": ready, "log": log}


def ensure_pip(package: str, module: str | None = None) -> dict:
    """Instala un paquete pip arbitrario (módulo opcional para verificar)."""
    module = module or package.split("[")[0].replace("-", "_")
    if _importable(module):
        return {"ok": True, "already": True, "package": package}
    log: list[str] = []
    ok = _run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
               package], log)
    return {"ok": ok and _importable(module), "already": False,
            "package": package, "log": log}


if __name__ == "__main__":
    import json
    print(json.dumps(status(), indent=2, ensure_ascii=False))
