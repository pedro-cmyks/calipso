#!/usr/bin/env python3
"""
calipso/browser.py — Navegador real (Playwright) para Calipso.

Habilita render de páginas con JS, screenshots y click-test de la UI. Si la
dependencia no está, la instala sola (deps.ensure('browser')) — no se bloquea.

  screenshot(url, path) -> bytes PNG
  render(url)           -> texto de la página ya renderizada (mejor que urllib)
"""
from __future__ import annotations

import pathlib
import re

from calipso import deps


def _ensure() -> None:
    if not deps.is_ready("browser"):
        deps.ensure("browser")


def screenshot(url: str, path: str | None = None, full_page: bool = True,
               width: int = 1280, height: int = 900, timeout: int = 25000) -> bytes:
    _ensure()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": width, "height": height})
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout)
        except Exception:
            page.goto(url, timeout=timeout)  # reintento sin esperar networkidle
        png = page.screenshot(full_page=full_page)
        browser.close()
    if path:
        pathlib.Path(path).write_bytes(png)
    return png


def render(url: str, timeout: int = 25000, max_chars: int = 6000) -> str:
    """Texto de la página YA renderizada (ejecuta JS, a diferencia de web.fetch)."""
    _ensure()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=timeout)
        except Exception:
            page.goto(url, timeout=timeout)
        text = page.inner_text("body")
        browser.close()
    return re.sub(r"\n\s*\n+", "\n", text).strip()[:max_chars]


if __name__ == "__main__":
    png = screenshot("https://example.com", "/tmp/calipso_browser_test.png")
    print(f"screenshot OK: {len(png)} bytes")
