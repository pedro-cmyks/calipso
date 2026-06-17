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

import pathlib
import re

from calipso import deps


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
