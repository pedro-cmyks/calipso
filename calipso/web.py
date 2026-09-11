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

from calipso import aduana

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Calipso/1.0"


def _get(url: str, quien: aduana.Quien, proposito: str, carga,
         timeout: float = 10.0, data: bytes | None = None) -> str:
    """La unica funcion de este modulo que sale a la red: el `with` de la
    aduana vive aca (spec seccion 3), no en el llamador. `carga` es lo que
    se va: la consulta (search) o la URL (fetch). `data` es el body del
    POST a DDG -la misma consulta urlencoded- y no se anota aparte; el
    header User-Agent jamas se anota (invariante 9.4)."""
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
    with aduana.cruzar(quien, proposito, destino=url, carga=carga) as cruce:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            crudo = r.read()
        cruce.entro(len(crudo))
    return crudo.decode("utf-8", "replace")


def search(query: str, n: int, quien: aduana.Quien) -> list[dict]:
    """Resultados de búsqueda: [{title, url, snippet}]. [] si falla.
    DuckDuckGo HTML requiere POST (no GET). El `except` queda AFUERA del
    cruce: la aduana anota `fallo` y re-lanza, y aca se traga como hoy."""
    # el proposito dice si la busqueda la pidio Pedro (/web) o la decidio
    # la heuristica `needs_web` de `_decide` (spec seccion 4, fila `gesto`:
    # sin slash, `gesto` es None y el proposito lo dice)
    proposito = "buscar en la web" if quien.gesto == "/web" else "busqueda por heuristica"
    try:
        body = urllib.parse.urlencode({"q": query}).encode()
        page = _get("https://html.duckduckgo.com/html/", quien,
                    proposito, query, data=body)
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


def fetch(url: str, max_chars: int, quien: aduana.Quien) -> str:
    """Texto legible de una página (sin scripts/estilos/tags). '' si falla.
    La URL viene del href que devolvio DuckDuckGo: la aduana la sanea."""
    try:
        raw = _get(url, quien, "leer una pagina", url)
    except Exception:
        return ""
    raw = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", raw,
                 flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    return text[:max_chars]


def research(query: str, n_results: int, read: int, quien: aduana.Quien) -> dict:
    """Busca y lee los primeros 'read' resultados. Devuelve material para el
    contexto del modelo + lo que vio (para el preview de la UI).

    Texto vía urllib (rápido); si una página viene vacía (sitio con JS) y el
    navegador ya está instalado, cae a Playwright para renderizarla. El
    MISMO `quien` (el del turno) hereda a la busqueda, a cada pagina y al
    render con Chromium."""
    results = search(query, n_results, quien)
    pages = []
    for r in results[:read]:
        body = fetch(r["url"], 2500, quien)
        if not body:
            try:
                from calipso import deps, browser
                if deps.is_ready("browser"):
                    body = browser.render(r["url"], max_chars=2500, quien=quien)
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
    # smoke a mano: sale a internet de verdad y anota en el libro del
    # CALIPSO_HOME vigente
    m = research("que dia es hoy noticia", 4, 1, aduana.Quien(
        origen="gesto", proyecto="smoke", desde={"credencial": "maquina"}))
    print("resultados:", len(m["results"]), "paginas:", len(m["pages"]))
    for r in m["results"][:3]:
        print(" -", r["title"][:60], r["url"][:50])
