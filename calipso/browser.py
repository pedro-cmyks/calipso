#!/usr/bin/env python3
"""
calipso/browser.py - Navegador real (Playwright) para Calipso.

Habilita render de paginas con JS, screenshots y click-test de la UI. Si la
dependencia o el binario de Chromium faltan, los instala con deps.ensure("browser")
y reintenta una vez.

  screenshot(url, path) -> bytes PNG
  render(url)           -> texto de la pagina ya renderizada
"""
from __future__ import annotations

import ipaddress
import pathlib
import re
import socket
import urllib.parse

from calipso import deps


class UrlNoPermitida(Exception):
    """La URL apunta adentro de la red de Pedro, o no es web."""


def exigir_url_publica(url: str) -> str:
    """Rechaza todo lo que no sea una pagina publica de internet.

    Sin esto, cualquiera que consiga disparar una captura convierte a Calipso
    en un escaner de la red de Pedro: le pasa http://127.0.0.1:8000 o la IP de
    su router y se lleva la foto. Y como la captura se pide por GET desde un
    <img>, con la cookie en SameSite=lax alcanza con que Pedro abra una
    pestana cualquiera para dispararla.

    Limitacion conocida y aceptada: se resuelve el nombre una vez aca y el
    navegador lo resuelve de nuevo despues, asi que un DNS que conteste
    distinto entre las dos consultas se escapa. Cerrar eso exige fijar la IP
    en el navegador, que es mucho mas caro; esto tapa el caso directo, que es
    el que esta abierto hoy.
    """
    partes = urllib.parse.urlsplit(url)
    if partes.scheme not in ("http", "https"):
        raise UrlNoPermitida(f"esquema no permitido: {partes.scheme or 'ninguno'}")
    host = partes.hostname
    if not host:
        raise UrlNoPermitida("la URL no tiene host")
    try:
        infos = socket.getaddrinfo(host, partes.port or
                                   (443 if partes.scheme == "https" else 80),
                                   proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise UrlNoPermitida(f"no se pudo resolver {host}: {exc}") from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            raise UrlNoPermitida(f"{host} resuelve a una direccion interna: {ip}")
    return url


def _ensure() -> None:
    if not deps.is_ready("browser"):
        deps.ensure("browser")


def _needs_browser_install(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "executable doesn't exist" in msg
        or "playwright install" in msg
        or "browser was just installed or updated" in msg
    )


def screenshot(url: str, path: str | None = None, full_page: bool = True,
               width: int = 1280, height: int = 900, timeout: int = 25000) -> bytes:
    exigir_url_publica(url)   # la defensa vive aca, no solo en el endpoint
    _ensure()
    from playwright.sync_api import sync_playwright

    def capture() -> bytes:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            try:
                page.goto(url, wait_until="networkidle", timeout=timeout)
            except Exception:
                page.goto(url, timeout=timeout)  # reintento sin esperar networkidle
            png = page.screenshot(full_page=full_page)
            browser.close()
            return png

    try:
        png = capture()
    except Exception as exc:
        if not _needs_browser_install(exc):
            raise
        deps.ensure("browser", run_post=True)
        png = capture()
    if path:
        pathlib.Path(path).write_bytes(png)
    return png


_UI_EXTS = {".html", ".css", ".js"}


def is_ui_file(file_path: str) -> bool:
    """True si el archivo afecta la UI de Calipso (web/)."""
    p = pathlib.Path(file_path)
    return p.suffix in _UI_EXTS and "web" in p.parts


def before_after_capture(
    url: str,
    apply_fn,
    width: int = 1280,
    height: int = 900,
    timeout: int = 20000,
    settle_ms: int = 800,
) -> tuple[bytes, bytes]:
    """Captura before/after de la UI al aplicar un cambio.

    apply_fn() escribe el archivo a disco. La URL debe estar corriendo antes de llamar.
    Devuelve (before_png, after_png).
    """
    import time as _time
    _ensure()
    from playwright.sync_api import sync_playwright

    def _snap(page) -> bytes:
        try:
            page.goto(url, wait_until="load", timeout=timeout)
        except Exception:
            pass
        return page.screenshot(full_page=False)

    def _run() -> tuple[bytes, bytes]:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})
            before = _snap(page)
            apply_fn()
            _time.sleep(settle_ms / 1000)
            after = _snap(page)
            browser.close()
        return before, after

    try:
        return _run()
    except Exception as exc:
        if not _needs_browser_install(exc):
            raise
        deps.ensure("browser", run_post=True)
        return _run()


def render(url: str, timeout: int = 25000, max_chars: int = 6000) -> str:
    """Texto de la pagina ya renderizada, con JS ejecutado."""
    _ensure()
    from playwright.sync_api import sync_playwright

    def capture_text() -> str:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=timeout)
            except Exception:
                page.goto(url, timeout=timeout)
            text = page.inner_text("body")
            browser.close()
            return text

    try:
        text = capture_text()
    except Exception as exc:
        if not _needs_browser_install(exc):
            raise
        deps.ensure("browser", run_post=True)
        text = capture_text()
    return re.sub(r"\n\s*\n+", "\n", text).strip()[:max_chars]


if __name__ == "__main__":
    png = screenshot("https://example.com", "/tmp/calipso_browser_test.png")
    print(f"screenshot OK: {len(png)} bytes")
