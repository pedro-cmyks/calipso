"""Un test por enchufe con la red FALSA (spec seccion 12): el sitio produce UN
cruce con el Quien correcto y la carga recortada, y sin la aduana escribible
sigue funcionando igual. Los sitios del server (ws_chat, endpoints) estan en
test_aduana_api.py; aca los modulos: web, deps, github, browser, discovery.
"""
from __future__ import annotations

import io
import subprocess
import sys
import types

import pytest

from calipso import aduana, browser, deps, web
from test_aduana import cruces_del_libro, libro, quien_de_prueba  # noqa: F401


class _RespuestaFalsa(io.BytesIO):
    """Lo que devuelve `urlopen`: un context manager con `.read()`."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def _urlopen_falso(monkeypatch, modulo, cuerpo: bytes = b"<html>ok</html>",
                   levanta: Exception | None = None):
    visto: list[dict] = []

    def urlopen(req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else req
        visto.append({"url": url, "timeout": timeout,
                      "data": getattr(req, "data", None)})
        if levanta:
            raise levanta
        return _RespuestaFalsa(cuerpo)
    monkeypatch.setattr(modulo.urllib.request, "urlopen", urlopen)
    return visto


class _Captura:
    """`subprocess.run` doblado (molde test_seguridad_git_blindado.py): anota
    argv y kwargs, devuelve lo que se le diga."""

    def __init__(self, returncode=0, stdout="salida", stderr="", levanta=None):
        self.llamadas: list[list[str]] = []
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr
        self.levanta = levanta

    def __call__(self, args, **kwargs):
        self.llamadas.append(list(args))
        if self.levanta:
            raise self.levanta
        return subprocess.CompletedProcess(args, self.returncode,
                                           stdout=self.stdout, stderr=self.stderr)


# --- web.py ---------------------------------------------------------------------

def test_search_cruza_con_la_query_como_consulta(libro, monkeypatch):
    visto = _urlopen_falso(monkeypatch, web, b'<a class="result__a" href="https://x.com/p">T</a>')
    q = quien_de_prueba()
    r = web.search("precio del dolar hoy", 5, q)
    assert r == [{"title": "T", "url": "https://x.com/p", "snippet": ""}]
    assert visto[0]["url"] == "https://html.duckduckgo.com/html/"
    c, = cruces_del_libro(libro)
    assert c["quien"] == q.a_dict()
    assert c["proposito"] == "buscar en la web"
    assert c["destino"]["host"] == "html.duckduckgo.com"
    assert c["carga"] == {"tipo": "consulta", "texto": "precio del dolar hoy"}
    assert c["resultado"]["estado"] == "ok" and c["resultado"]["bytes"] == len(
        b'<a class="result__a" href="https://x.com/p">T</a>')


def test_fetch_cruza_con_la_url_saneada_y_un_fallo_devuelve_vacio(libro, monkeypatch):
    _urlopen_falso(monkeypatch, web, levanta=TimeoutError("lento"))
    assert web.fetch("https://user:pw@x.com/p?token=abc123", 2500, quien_de_prueba()) == ""
    c, = cruces_del_libro(libro)
    assert c["proposito"] == "leer una pagina"
    assert c["carga"]["texto"] == "https://[SECRETO]@x.com/p?token=[SECRETO]"
    assert c["destino"] == {"host": "x.com", "url": "https://[SECRETO]@x.com/p?token=[SECRETO]"}
    assert c["resultado"] == {"estado": "fallo", "error": "TimeoutError",
                              "ms": c["resultado"]["ms"], "bytes": None}
    assert "pw" not in libro.read_text() and "abc123" not in libro.read_text()


def test_research_hereda_el_mismo_quien_a_search_fetch_y_render(libro, monkeypatch):
    q = quien_de_prueba(chat="chat_web")
    monkeypatch.setattr(web, "search", lambda query, n, quien: (
        [{"title": "T", "url": "https://x.com/p", "snippet": ""}]
        if quien is q else []))
    monkeypatch.setattr(web, "fetch", lambda url, max_chars, quien: "" if quien is q else "no")
    monkeypatch.setattr(deps, "is_ready", lambda tool: True)
    vistos = []
    monkeypatch.setattr(browser, "render",
                        lambda url, timeout=25000, max_chars=6000, *, quien: (
                            vistos.append(quien) or "renderizado"))
    m = web.research("que hora es", 4, 2, q)
    assert m["pages"] == [{"url": "https://x.com/p", "title": "T", "text": "renderizado"}]
    assert vistos == [q]


def test_research_sin_quien_no_compila():
    with pytest.raises(TypeError):
        web.research("hola", 4, 2)          # type: ignore[call-arg]
    with pytest.raises(TypeError):
        web.search("hola", 5)               # type: ignore[call-arg]
    with pytest.raises(TypeError):
        web.fetch("https://x.com", 2500)    # type: ignore[call-arg]


def test_sin_la_aduana_escribible_la_web_sigue_igual(libro, monkeypatch):
    _urlopen_falso(monkeypatch, web, b"<p>texto</p>")
    monkeypatch.setattr(aduana, "_escribir", lambda linea: (_ for _ in ()).throw(OSError("disco")))
    assert web.fetch("https://x.com/p", 2500, quien_de_prueba()) == "texto"
    assert cruces_del_libro(libro) == []
    assert aduana.sin_libro()["n"] == 1


def test_una_busqueda_por_heuristica_lo_dice_en_el_proposito(libro, monkeypatch):
    """Spec seccion 4, fila `gesto`: sin slash el gesto es None Y el
    proposito lo dice; en el libro una busqueda que decidio `needs_web` no
    puede quedar identica a una que Pedro pidio con /web."""
    _urlopen_falso(monkeypatch, web, b"")
    web.search("precio del dolar", 5, quien_de_prueba(gesto=None))
    web.search("precio del dolar", 5, quien_de_prueba(gesto="/web"))
    a, b = cruces_del_libro(libro)
    assert a["proposito"] == "busqueda por heuristica" and a["quien"]["gesto"] is None
    assert b["proposito"] == "buscar en la web" and b["quien"]["gesto"] == "/web"


# --- deps.py ---------------------------------------------------------------------

def test_ensure_cruza_el_pip_y_el_playwright_install(libro, monkeypatch):
    cap = _Captura()
    monkeypatch.setattr(deps.subprocess, "run", cap)
    monkeypatch.setattr(deps, "_importable", lambda m: False)
    monkeypatch.setattr(deps, "is_ready", lambda t: True)
    q = quien_de_prueba(origen="gesto", endpoint="/api/deps/install", chat=None,
                        gesto=None, ruta=None)
    r = deps.ensure("browser", q)
    assert r["ok"] is True and len(cap.llamadas) == 2
    pip, pw = cruces_del_libro(libro)
    assert pip["quien"] == q.a_dict() and pw["quien"] == q.a_dict()
    assert pip["proposito"] == "instalar dependencia"
    assert pip["destino"] == {"host": "pypi.org", "url": None}
    assert pip["carga"]["texto"].endswith("-m pip install --disable-pip-version-check playwright")
    assert pw["destino"] == {"host": "cdn.playwright.dev", "url": None}
    assert pw["carga"]["texto"].endswith("-m playwright install chromium")
    assert pip["resultado"]["estado"] == "ok" and pip["resultado"]["bytes"] == len("salida")


def test_un_pip_que_falla_es_un_cruce_fallo_y_ensure_dice_no(libro, monkeypatch):
    monkeypatch.setattr(deps.subprocess, "run", _Captura(returncode=1, stderr="error"))
    monkeypatch.setattr(deps, "_importable", lambda m: False)
    monkeypatch.setattr(deps, "is_ready", lambda t: False)
    r = deps.ensure("browser", quien_de_prueba())
    assert r["ok"] is False and len(r["log"]) == 1
    c, = cruces_del_libro(libro)
    assert c["resultado"]["estado"] == "fallo" and c["resultado"]["error"] == "InstalacionFallida"


def test_un_timeout_del_subproceso_se_traga_como_hoy_y_queda_como_fallo(libro, monkeypatch):
    monkeypatch.setattr(deps.subprocess, "run",
                        _Captura(levanta=subprocess.TimeoutExpired("pip", 600)))
    monkeypatch.setattr(deps, "_importable", lambda m: False)
    monkeypatch.setattr(deps, "is_ready", lambda t: False)
    r = deps.ensure("browser", quien_de_prueba())
    assert r["ok"] is False and "ERROR" in r["log"][0]
    assert cruces_del_libro(libro)[0]["resultado"]["error"] == "TimeoutExpired"


def test_una_herramienta_desconocida_no_cruza(libro):
    assert deps.ensure("no-existe", quien_de_prueba())["ok"] is False
    assert cruces_del_libro(libro) == []


def test_ensure_pip_ya_no_existe():
    assert not hasattr(deps, "ensure_pip")


# --- browser.py ----------------------------------------------------------------

class _PaginaFalsa:
    def __init__(self, fallos: list):
        self.fallos = fallos

    def goto(self, url, **kw):
        if self.fallos:
            raise self.fallos.pop(0)

    def screenshot(self, **kw):
        return b"png"

    def inner_text(self, sel):
        return "texto  renderizado"


class _ChromiumFalso:
    def __init__(self, fallos):
        self.fallos = fallos

    def launch(self):
        return self

    def new_page(self, **kw):
        return _PaginaFalsa(self.fallos)

    def close(self):
        pass


def _playwright_falso(monkeypatch, fallos=None):
    fallos = fallos if fallos is not None else []
    modulo = types.ModuleType("playwright.sync_api")

    class _Ctx:
        def __enter__(self):
            return types.SimpleNamespace(chromium=_ChromiumFalso(fallos))

        def __exit__(self, *a):
            return False
    modulo.sync_playwright = lambda: _Ctx()
    monkeypatch.setitem(sys.modules, "playwright.sync_api", modulo)
    monkeypatch.setitem(sys.modules, "playwright", types.ModuleType("playwright"))
    return fallos


def test_screenshot_cruza_una_vez_por_captura(libro, monkeypatch):
    _playwright_falso(monkeypatch)
    monkeypatch.setattr(browser, "exigir_url_publica", lambda url: url)
    monkeypatch.setattr(deps, "is_ready", lambda t: True)
    q = quien_de_prueba(origen="ui", endpoint="/api/browser/screenshot", chat=None,
                        gesto=None, ruta=None)
    assert browser.screenshot("https://x.com/p?k=v", None, False, quien=q) == b"png"
    c, = cruces_del_libro(libro)
    assert c["quien"] == q.a_dict() and c["proposito"] == "captura con Chromium"
    assert c["destino"]["url"] == "https://x.com/p?k=[SECRETO]"
    assert c["carga"]["texto"] == "https://x.com/p?k=[SECRETO]"
    assert c["resultado"] == {"estado": "ok", "ms": c["resultado"]["ms"], "bytes": 3}


def test_el_reintento_por_instalacion_hereda_el_quien_a_deps(libro, monkeypatch):
    fallos = _playwright_falso(monkeypatch, [RuntimeError("Executable doesn't exist; playwright install"),
                                             RuntimeError("Executable doesn't exist; playwright install")])
    monkeypatch.setattr(browser, "exigir_url_publica", lambda url: url)
    monkeypatch.setattr(deps, "is_ready", lambda t: True)
    monkeypatch.setattr(deps, "_importable", lambda m: True)
    monkeypatch.setattr(deps.subprocess, "run", _Captura())
    q = quien_de_prueba()
    assert browser.screenshot("https://x.com/", quien=q) == b"png"
    propositos = [c["proposito"] for c in cruces_del_libro(libro)]
    assert propositos == ["captura con Chromium", "instalar dependencia", "captura con Chromium"]
    assert cruces_del_libro(libro)[0]["resultado"]["error"] == "RuntimeError"
    assert all(c["quien"] == q.a_dict() for c in cruces_del_libro(libro))
    assert fallos == []


def test_render_cruza_con_el_quien_del_turno(libro, monkeypatch):
    _playwright_falso(monkeypatch)
    monkeypatch.setattr(deps, "is_ready", lambda t: True)
    assert browser.render("https://x.com/js", max_chars=5, quien=quien_de_prueba()) == "texto"
    c, = cruces_del_libro(libro)
    assert c["proposito"] == "renderizar con Chromium" and c["resultado"]["bytes"] == len("texto  renderizado")


def test_before_after_capture_no_cruza_pero_su_deps_ensure_si(libro, monkeypatch):
    _playwright_falso(monkeypatch)
    monkeypatch.setattr(deps, "is_ready", lambda t: False)
    monkeypatch.setattr(deps, "_importable", lambda m: True)
    monkeypatch.setattr(deps.subprocess, "run", _Captura())
    q = quien_de_prueba(origen="gesto", endpoint="/api/proposals/{change_id}/apply",
                        chat=None, gesto=None, ruta=None)
    antes, despues = browser.before_after_capture("http://localhost:8000", lambda: None,
                                                  settle_ms=0, quien=q)
    assert antes == b"png" and despues == b"png"
    propositos = [c["proposito"] for c in cruces_del_libro(libro)]
    assert propositos == ["instalar dependencia"]     # playwright install, no la captura
