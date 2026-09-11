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

from calipso import aduana, browser, deps, discovery, github, web
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


@pytest.mark.parametrize("url", [
    "http://example.com/", "http://192.168.1.66:8000", "http://[::1:8000/x",
    "ftp://localhost/x", "localhost:8000", "",
])
def test_before_after_capture_rechaza_lo_que_no_es_loopback(libro, monkeypatch, url):
    """La excepcion del canario para la captura descansa en "loopback por
    construccion": ahora se verifica al entrar. Es un guard de programador
    (ValueError), no un cruce: ni playwright ni deps se tocan."""
    def bomba(*a, **k):
        raise AssertionError("no debe llegar a deps/playwright")
    monkeypatch.setattr(deps, "is_ready", bomba)
    with pytest.raises(ValueError, match="solo captura loopback"):
        browser.before_after_capture(url, lambda: None, quien=quien_de_prueba())
    assert cruces_del_libro(libro) == []


@pytest.mark.parametrize("url", ["http://localhost:8000", "http://127.0.0.1:8000/",
                                 "http://[::1]:8000", "https://localhost/x"])
def test_before_after_capture_acepta_loopback(libro, monkeypatch, url):
    _playwright_falso(monkeypatch)
    monkeypatch.setattr(deps, "is_ready", lambda t: True)
    antes, despues = browser.before_after_capture(url, lambda: None, settle_ms=0,
                                                  quien=quien_de_prueba())
    assert antes == b"png" and despues == b"png"


# --- github.py -----------------------------------------------------------------

def test_default_runner_cruza_cada_gh(libro, monkeypatch):
    cap = _Captura(stdout='{"login": "pedro"}')
    monkeypatch.setattr(github, "_which_gh", lambda: "/usr/bin/gh")
    monkeypatch.setattr(github.subprocess, "run", cap)
    q = quien_de_prueba(origen="ui", endpoint="/api/github/overview", chat=None,
                        gesto=None, ruta=None)
    run = github.default_runner(cwd="/tmp", quien=q)
    assert run(["gh", "api", "user"]) == (0, '{"login": "pedro"}', "")
    assert cap.llamadas == [["/usr/bin/gh", "api", "user"]]
    c, = cruces_del_libro(libro)
    assert c["quien"] == q.a_dict()
    assert c["proposito"] == "gh api user"
    assert c["destino"] == {"host": "api.github.com", "url": None}
    assert c["carga"] == {"tipo": "consulta", "texto": "gh api user"}
    assert c["resultado"]["bytes"] == len('{"login": "pedro"}')


def test_default_runner_sin_gh_en_path_no_cruza(libro, monkeypatch):
    monkeypatch.setattr(github, "_which_gh", lambda: None)
    assert github.default_runner(quien=quien_de_prueba())(["gh", "pr", "list"])[0] == 127
    assert cruces_del_libro(libro) == []


def test_git_runner_con_log_no_cruza_y_con_fetch_si(libro, monkeypatch):
    cap = _Captura()
    monkeypatch.setattr(github.shutil, "which", lambda n: "/usr/bin/git")
    monkeypatch.setattr(github.subprocess, "run", cap)
    run = github.git_runner(cwd="/tmp", quien=quien_de_prueba())
    assert run(["log", "-1"])[0] == 0
    assert run(["remote", "get-url", "origin"])[0] == 0
    assert run(["-c", "core.pager=cat", "branch", "--show-current"])[0] == 0
    assert run(["git", "status"])[0] == 0            # un `git` inicial se tolera
    assert cruces_del_libro(libro) == []
    assert run(["fetch", "origin", "3f2a9c1e4b7d6a5f8e9c0b1a2d3e4f5a6b7c8d9e"])[0] == 0
    assert run(["clone", "https://pedro:s3cr3t@github.com/x/y.git"])[0] == 0
    fetch, clone = cruces_del_libro(libro)
    assert fetch["proposito"] == "git fetch"
    assert fetch["carga"]["texto"] == "git fetch origin 3f2a9c1e4b7d6a5f8e9c0b1a2d3e4f5a6b7c8d9e"
    assert fetch["destino"] == {"host": None, "url": None}
    assert clone["destino"]["host"] == "github.com"
    assert "s3cr3t" not in libro.read_text()
    # porcelana compuesta que sale a la red (fix round 1): `remote update` y
    # `submodule update` no son `fetch` pero fetchean; cruzan con su verbo
    assert run(["remote", "update"])[0] == 0
    assert run(["submodule", "update", "--remote"])[0] == 0
    assert [c["proposito"] for c in cruces_del_libro(libro)] == [
        "git fetch", "git clone", "git remote update", "git submodule update"]
    assert len(cap.llamadas) == 8


def test_git_runner_cruza_con_opcion_global_de_dos_tokens_antes_del_fetch(libro, monkeypatch):
    """Fix round 1: `--git-dir /x/.git fetch` es un fetch. Antes el parser
    tomaba `/x/.git` por subcomando y el fetch salia sin linea (invariante
    1 rota, del lado que no es inocuo). El mismo argv con `--git-dir=/x`
    (un token) ya funcionaba y sigue."""
    cap = _Captura()
    monkeypatch.setattr(github.shutil, "which", lambda n: "/usr/bin/git")
    monkeypatch.setattr(github.subprocess, "run", cap)
    run = github.git_runner(cwd="/tmp", quien=quien_de_prueba())
    assert run(["--git-dir", "/x/.git", "fetch", "origin"])[0] == 0
    assert run(["--git-dir=/x/.git", "--work-tree", "/x", "log", "-1"])[0] == 0
    c, = cruces_del_libro(libro)
    assert c["proposito"] == "git fetch"
    assert c["carga"]["texto"] == "git --git-dir /x/.git fetch origin"
    assert cap.llamadas == [["/usr/bin/git", "--git-dir", "/x/.git", "fetch", "origin"],
                            ["/usr/bin/git", "--git-dir=/x/.git", "--work-tree", "/x", "log", "-1"]]


@pytest.mark.parametrize("opcion", ["-c", "-C", "--git-dir", "--work-tree", "--namespace",
                                    "--super-prefix", "--config-env", "--shallow-file",
                                    "--attr-source"])
def test_subcomando_git_salta_las_opciones_globales_que_llevan_valor(opcion):
    assert github.subcomando_git([opcion, "valor", "fetch", "origin"]) == "fetch"
    assert github.subcomando_git(["git", opcion, "valor", "-p", "log"]) == "log"
    assert github.subcomando_git([opcion, "valor"]) is None


def test_subcomando_git_trata_exec_path_y_los_flags_como_un_token():
    # `git --exec-path` solo imprime la ruta y sale: no toma valor (git.c);
    # `--git-dir=/x` y `--bare` tampoco
    assert github.subcomando_git(["--exec-path", "fetch"]) == "fetch"
    assert github.subcomando_git(["--git-dir=/x/.git", "--bare", "status"]) == "status"
    assert github.subcomando_git([]) is None


def test_subcomando_git_de_red_distingue_verbo_y_bandera():
    """Fix round 1: la lista negra tiene que ser completa. `remote` y
    `archive` son locales salvo por verbo/bandera; `submodule`, `svn`,
    `lfs` mezclan verbos y entran enteros (una linea de mas es inocua)."""
    red = github.subcomando_git_de_red
    assert red(["remote", "get-url", "origin"]) is None
    assert red(["remote", "-v"]) is None
    assert red(["remote", "add", "origin", "https://x/y.git"]) is None
    assert red(["remote", "-v", "update"]) == "remote update"
    assert red(["remote", "prune", "origin"]) == "remote prune"
    assert red(["remote", "show", "origin"]) == "remote show"
    assert red(["remote", "set-head", "origin", "-a"]) == "remote set-head"
    assert red(["archive", "-o", "x.tar", "HEAD"]) is None
    assert red(["archive", "--remote=git@github.com:x/y.git", "HEAD"]) == "archive --remote"
    assert red(["archive", "--remote", "https://x/y.git", "HEAD"]) == "archive --remote"
    assert red(["submodule", "status"]) == "submodule status"
    assert red(["submodule", "--quiet", "add", "https://x/y.git"]) == "submodule add"
    assert red(["lfs", "fetch"]) == "lfs fetch"
    assert red(["svn", "rebase"]) == "svn rebase"
    assert red(["lfs"]) == "lfs"
    assert red(["ls-remote", "origin"]) == "ls-remote"
    assert red(["log", "-1"]) is None
    assert red([]) is None


def test_los_runners_exigen_quien():
    with pytest.raises(TypeError):
        github.default_runner(cwd="/tmp")     # type: ignore[call-arg]
    with pytest.raises(TypeError):
        github.git_runner(cwd="/tmp")         # type: ignore[call-arg]


# --- discovery.py ----------------------------------------------------------------

def test_npm_latest_cruza_con_carga_nada(libro, monkeypatch):
    visto = _urlopen_falso(monkeypatch, discovery, b'{"version": "2.0.1"}')
    q = quien_de_prueba(origen="ui", endpoint="/api/updates", chat=None, gesto=None, ruta=None)
    assert discovery._npm_latest("@anthropic-ai/claude-code", q) == "2.0.1"
    assert visto[0]["url"] == "https://registry.npmjs.org/@anthropic-ai/claude-code/latest"
    c, = cruces_del_libro(libro)
    assert c["quien"] == q.a_dict() and c["proposito"] == "version en npm"
    assert c["destino"]["host"] == "registry.npmjs.org"
    assert c["carga"] == {"tipo": "nada"}
    assert c["resultado"]["bytes"] == len('{"version": "2.0.1"}')


def test_npm_latest_caido_es_none_y_fallo_en_el_libro(libro, monkeypatch):
    _urlopen_falso(monkeypatch, discovery, levanta=OSError("sin red"))
    assert discovery._npm_latest("@openai/codex", quien_de_prueba()) is None
    assert cruces_del_libro(libro)[0]["resultado"]["error"] == "OSError"


def test_updates_pasa_el_quien_a_npm_latest(libro, tmp_path, monkeypatch):
    monkeypatch.setattr(discovery, "SNAP", tmp_path / "discovered.json")
    monkeypatch.setattr(discovery, "CALIPSO_HOME", tmp_path)
    monkeypatch.setattr(discovery, "discover", lambda register=True: {"local": [], "api": [], "added": []})
    monkeypatch.setattr(discovery, "_cli_version", lambda c: "1.0.0" if c == "claude" else None)
    vistos = []
    monkeypatch.setattr(discovery, "_npm_latest", lambda pkg, quien: vistos.append((pkg, quien)) or "1.0.1")
    q = quien_de_prueba(origen="ui")
    r = discovery.updates(q)
    assert vistos == [("@anthropic-ai/claude-code", q)]
    assert r["clis"]["claude"] == {"installed": "1.0.0", "latest": "1.0.1", "outdated": True}
    with pytest.raises(TypeError):
        discovery.updates()                   # type: ignore[call-arg]


def test_sin_la_aduana_escribible_deps_github_y_discovery_siguen_igual(libro, monkeypatch):
    """Spec seccion 12, por enchufe (web ya tiene el suyo arriba): con el
    libro roto los tres devuelven lo mismo que con el libro sano, el hueco
    se cuenta en `sin_libro` y no queda linea. Vale la pena porque deps y
    github tienen `except` propios alrededor del `with`."""
    monkeypatch.setattr(aduana, "_escribir", lambda linea: (_ for _ in ()).throw(OSError("disco")))
    monkeypatch.setattr(deps.subprocess, "run", _Captura())
    monkeypatch.setattr(deps, "_importable", lambda m: True)
    monkeypatch.setattr(deps, "is_ready", lambda t: True)
    assert deps.ensure("browser", quien_de_prueba())["ok"] is True      # 1 cruce (playwright install)
    monkeypatch.setattr(github, "_which_gh", lambda: "/usr/bin/gh")
    monkeypatch.setattr(github.subprocess, "run", _Captura(stdout="{}"))
    assert github.default_runner(quien=quien_de_prueba())(["gh", "api", "user"]) == (0, "{}", "")
    _urlopen_falso(monkeypatch, discovery, b'{"version": "1"}')
    assert discovery._npm_latest("@openai/codex", quien_de_prueba()) == "1"
    assert cruces_del_libro(libro) == [] and aduana.sin_libro()["n"] == 3


# --- attachments.py: vision por SDK, declarada por llamada --------------------------

from calipso import attachments  # noqa: E402


def test_vision_por_sdk_se_declara_por_llamada_sin_la_imagen(libro, monkeypatch, tmp_path):
    llamadas = []

    class _Mensajes:
        def create(self, **kw):
            llamadas.append(kw)
            return types.SimpleNamespace(content=[types.SimpleNamespace(text="una foto")])

    class _Anthropic:
        def __init__(self, api_key):
            self.messages = _Mensajes()
    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=_Anthropic))
    monkeypatch.setattr(attachments, "image_bytes_b64", lambda root, aid: ("QUJDREVG", "image/png"))
    q = quien_de_prueba(gesto=None)
    assert attachments._vision_anthropic(str(tmp_path), ["att_1"], "que ves", "sk-ant-x", q) == "una foto"
    assert len(llamadas) == 1
    c, = cruces_del_libro(libro)
    assert c["declarado"] is True and c["quien"] == q.a_dict()
    assert c["proposito"] == "vision por SDK" and c["destino"]["host"] == "api.anthropic.com"
    assert c["motivo"] == "claude-opus-4-5" and c["carga"] == {"tipo": "nada"}
    assert "QUJDREVG" not in libro.read_text() and "sk-ant" not in libro.read_text()


def test_vision_describe_exige_quien(tmp_path):
    with pytest.raises(TypeError):
        attachments.vision_describe(str(tmp_path), [])        # type: ignore[call-arg]
