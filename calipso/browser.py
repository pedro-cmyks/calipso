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

from calipso import aduana, deps


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


def _ensure(quien: aduana.Quien) -> None:
    """El primer camino a `deps.ensure`: hereda el Quien de la operacion
    que necesito el navegador."""
    if not deps.is_ready("browser"):
        deps.ensure("browser", quien)


def _needs_browser_install(exc: Exception) -> bool:
    msg = str(exc).lower()
    return (
        "executable doesn't exist" in msg
        or "playwright install" in msg
        or "browser was just installed or updated" in msg
    )


def screenshot(url: str, path: str | None = None, full_page: bool = True,
               width: int = 1280, height: int = 900, timeout: int = 25000,
               *, quien: aduana.Quien) -> bytes:
    """`quien` es keyword-only y sin default: un cruce sin Quien no compila.
    Un cruce por captura (los dos `page.goto` van adentro del mismo); lo
    que Chromium cargue como sub-recurso el server no lo ve (limite
    honesto, spec seccion 8)."""
    exigir_url_publica(url)   # la defensa vive aca, no solo en el endpoint
    _ensure(quien)
    from playwright.sync_api import sync_playwright

    def capture() -> bytes:
        with aduana.cruzar(quien, "captura con Chromium", destino=url,
                           carga=url) as cruce:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page(viewport={"width": width, "height": height})
                try:
                    page.goto(url, wait_until="networkidle", timeout=timeout)
                except Exception:
                    page.goto(url, timeout=timeout)  # reintento sin esperar networkidle
                png = page.screenshot(full_page=full_page)
                browser.close()
            cruce.entro(len(png))
            return png

    try:
        png = capture()
    except Exception as exc:
        if not _needs_browser_install(exc):
            raise
        deps.ensure("browser", quien, run_post=True)
        png = capture()
    if path:
        pathlib.Path(path).write_bytes(png)
    return png


_UI_EXTS = {".html", ".css", ".js"}


def _es_loopback(url: str) -> bool:
    """http(s) a `localhost` o a una IP de loopback (127.0.0.0/8, ::1). Lo
    que urlsplit no parsea, o no tiene host, no es loopback demostrado."""
    try:
        partes = urllib.parse.urlsplit(url)
        host = partes.hostname
    except ValueError:
        return False
    if partes.scheme not in ("http", "https") or not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


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
    *,
    quien: aduana.Quien,
) -> tuple[bytes, bytes]:
    """Captura before/after de la UI al aplicar un cambio.

    apply_fn() escribe el archivo a disco. La URL debe estar corriendo antes de llamar.
    Devuelve (before_png, after_png).

    La captura NO cruza: la unica llamada (server.api_apply_proposal) es a
    http://localhost:8000, y ACA se verifica que la URL sea loopback (un
    guard de programador, ValueError: no es un cruce, y la excepcion del
    canario descansa en esto). Lo que SI cruza son los dos caminos a
    `deps.ensure` (pip / playwright install), con el Quien del endpoint.
    """
    if not _es_loopback(url):
        raise ValueError("before_after_capture solo captura loopback")
    import time as _time
    _ensure(quien)
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
        deps.ensure("browser", quien, run_post=True)
        return _run()


def render(url: str, timeout: int = 25000, max_chars: int = 6000,
           *, quien: aduana.Quien) -> str:
    """Texto de la pagina ya renderizada, con JS ejecutado. Un cruce por
    render, con el Quien del turno que llego por `web.research`."""
    _ensure(quien)
    from playwright.sync_api import sync_playwright

    def capture_text() -> str:
        with aduana.cruzar(quien, "renderizar con Chromium", destino=url,
                           carga=url) as cruce:
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                try:
                    page.goto(url, wait_until="networkidle", timeout=timeout)
                except Exception:
                    page.goto(url, timeout=timeout)
                text = page.inner_text("body")
                browser.close()
            cruce.entro(len(text))
            return text

    try:
        text = capture_text()
    except Exception as exc:
        if not _needs_browser_install(exc):
            raise
        deps.ensure("browser", quien, run_post=True)
        text = capture_text()
    return re.sub(r"\n\s*\n+", "\n", text).strip()[:max_chars]


if __name__ == "__main__":
    # smoke a mano: sale a internet de verdad y anota en el libro del
    # CALIPSO_HOME vigente
    png = screenshot("https://example.com", "/tmp/calipso_browser_test.png",
                     quien=aduana.Quien(origen="gesto", proyecto="smoke",
                                        desde={"credencial": "maquina"}))
    print(f"screenshot OK: {len(png)} bytes")
