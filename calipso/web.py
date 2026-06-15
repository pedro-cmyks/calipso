#!/usr/bin/env python3
"""
calipso/web.py — Navegación web ligera (búsqueda + fetch), sin API key.

Calipso puede buscar en la web y leer páginas para fundamentar respuestas
(grounding). Usa DuckDuckGo HTML (sin llave) y un extractor de texto simple.
La UI muestra un preview de lo que Calipso buscó/leyó.
"""
from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Calipso/1.0"


def _get(url: str, timeout: float = 10.0, data: bytes | None = None) -> str:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def search(query: str, n: int = 5) -> list[dict]:
    """Resultados de búsqueda: [{title, url, snippet}]. [] si falla.
    DuckDuckGo HTML requiere POST (no GET)."""
    try:
        body = urllib.parse.urlencode({"q": query}).encode()
        page = _get("https://html.duckduckgo.com/html/", data=body)
    except Exception:
        return []
    results = []
    # cada resultado: <a class="result__a" href="...">titulo</a> + snippet
    for block in re.split(r'class="result__a"', page)[1:]:
        href_m = re.search(r'href="([^"]+)"', block)
        title_m = re.search(r'>(.*?)</a>', block, re.S)
        if not href_m or not title_m:
            continue
        href = href_m.group(1)
        # DDG envuelve la URL en un redirect con uddg=
        q = urllib.parse.urlparse(href).query
        target = urllib.parse.parse_qs(q).get("uddg", [href])[0]
        title = html.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip()
        snip_m = re.search(r'class="result__snippet"[^>]*>(.*?)</a>', block, re.S)
        snippet = html.unescape(re.sub(r"<[^>]+>", "", snip_m.group(1))).strip() if snip_m else ""
        if title and target.startswith("http"):
            results.append({"title": title, "url": target, "snippet": snippet[:300]})
        if len(results) >= n:
            break
    return results


def fetch(url: str, max_chars: int = 4000) -> str:
    """Texto legible de una página (sin scripts/estilos/tags). '' si falla."""
    try:
        raw = _get(url)
    except Exception:
        return ""
    raw = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", raw,
                 flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:max_chars]


def research(query: str, n_results: int = 4, read: int = 2) -> dict:
    """Busca y lee los primeros 'read' resultados. Devuelve material para el
    contexto del modelo + lo que vio (para el preview de la UI).

    Texto vía urllib (rápido); si una página viene vacía (sitio con JS) y el
    navegador ya está instalado, cae a Playwright para renderizarla."""
    results = search(query, n_results)
    pages = []
    for r in results[:read]:
        body = fetch(r["url"], 2500)
        if not body:
            try:
                from calipso import deps, browser
                if deps.is_ready("browser"):
                    body = browser.render(r["url"], max_chars=2500)
            except Exception:
                body = ""
        if body:
            pages.append({"url": r["url"], "title": r["title"], "text": body})
    return {"query": query, "results": results, "pages": pages}


def context_block(material: dict) -> str:
    """Arma el bloque de contexto web para el modelo."""
    parts = [f"=== Resultados web para: {material['query']} ==="]
    for r in material["results"][:4]:
        parts.append(f"- {r['title']} — {r['url']}\n  {r.get('snippet', '')}")
    for p in material["pages"]:
        parts.append(f"\n[{p['title']}] ({p['url']})\n{p['text']}")
    parts.append("\nUsa esta información para responder; cita la fuente (URL) "
                 "cuando corresponda. Si no alcanza, dilo.")
    return "\n".join(parts)


if __name__ == "__main__":
    m = research("que dia es hoy noticia", 4, 1)
    print("resultados:", len(m["results"]), "paginas:", len(m["pages"]))
    for r in m["results"][:3]:
        print(" -", r["title"][:60], r["url"][:50])
