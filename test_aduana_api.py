"""Los enchufes del SERVER por TestClient y `GET /api/aduana` (spec seccion 12):
que cada endpoint arme el Quien con lo que tiene (`endpoint`, `desde` de
`request.state.sesion`, `proyecto` = ROOT.name), que los dos ejecutores que
eran `async def` con `subprocess.run` inline corran FUERA del loop, y que el
turno de `ws_chat` construya el Quien con chat, gesto, ruta y desde.

Moldes: `_pedir`/`_local`/`_sesion` de test_sesiones_server.py (host remoto
via `httpx.ASGITransport`, sesion viva sin pasar por el alta); el harness
`chat` de test_abismo_chat.py para el websocket.
"""
from __future__ import annotations

import asyncio
import errno
import json
import pathlib
import subprocess
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso import aduana, sesiones
from test_aduana import cruces_del_libro, libro, quien_de_prueba  # noqa: F401

REMOTO = "192.168.1.66"


@pytest.fixture(autouse=True)
def _almacen_aislado(tmp_path, monkeypatch):
    """El almacen de sesiones del modulo, no el de Pedro (molde
    test_sesiones_server.py:36-41), y el registro del corte en vivo limpio."""
    monkeypatch.setattr(sesiones, "_ruta", lambda: tmp_path / "sesiones.json")
    monkeypatch.setattr(sesiones, "_CACHE", sesiones._cache_vacia())
    srv._ws_generaciones.clear()
    yield
    srv._ws_generaciones.clear()


def _local() -> TestClient:
    """Loopback CON el token: `desde` = maquina."""
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def _pedir(ip: str, metodo: str, ruta: str, cuerpo=None, cookies=None) -> httpx.Response:
    transporte = httpx.ASGITransport(app=srv.app, client=(ip, 4321))

    async def _ir():
        async with httpx.AsyncClient(transport=transporte, base_url="http://calipso",
                                     cookies=cookies) as c:
            return await c.request(metodo, ruta, json=cuerpo)
    return asyncio.run(_ir())


def _sesion(tipo: str, aparato: str = "Aparato de prueba") -> str:
    return sesiones.crear_viva(aparato, tipo)


class _RunEspia:
    """`subprocess.run` falso que anota si corrio EN el loop: adentro de un
    `async def` `asyncio.get_running_loop()` contesta; en `to_thread` o en el
    threadpool levanta RuntimeError. Es la asercion exacta de "nunca desde
    el loop", sin comparar nombres de hilos."""

    def __init__(self, returncode: int = 0, stdout: str = "salida"):
        self.llamadas: list[dict] = []
        self.returncode, self.stdout = returncode, stdout

    def __call__(self, args, **kwargs):
        try:
            asyncio.get_running_loop()
            en_loop = True
        except RuntimeError:
            en_loop = False
        self.llamadas.append({"args": list(args), "en_loop": en_loop,
                              "hilo": threading.current_thread().name,
                              "cwd": kwargs.get("cwd"), "env": kwargs.get("env")})
        return subprocess.CompletedProcess(args, self.returncode, stdout=self.stdout,
                                           stderr="")


# --- Task 3: contribute/run y updates/run ---------------------------------------

def test_contribute_run_corre_fuera_del_loop_y_cruza_como_gesto(libro, monkeypatch):
    espia = _RunEspia(stdout="forked")
    monkeypatch.setattr(srv.subprocess, "run", espia)
    monkeypatch.setattr(srv, "_cmd_exe", lambda n: "/usr/bin/gh")
    r = _local().post("/api/github/contribute/run",
                      json={"action": "fork", "opts": {}, "confirm": True})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True and r.json()["stdout"] == "forked"
    assert espia.llamadas[0]["en_loop"] is False, "subprocess.run corrio en el loop"
    assert espia.llamadas[0]["cwd"] == str(srv.ROOT)
    assert espia.llamadas[0]["env"].get("GIT_CONFIG_COUNT") == "3"   # el escudo sigue
    c, = cruces_del_libro(libro)
    assert c["quien"] == {"origen": "gesto", "chat": None, "proyecto": srv.ROOT.name,
                          "gesto": None, "ruta": None, "rutina": None, "departamento": None,
                          "endpoint": "/api/github/contribute/run",
                          "desde": {"credencial": "maquina"}}
    assert c["proposito"] == "gh repo fork"
    assert c["destino"] == {"host": "api.github.com", "url": None}
    assert c["carga"] == {"tipo": "consulta", "texto": "gh repo fork --clone=false"}
    assert c["resultado"]["estado"] == "ok" and c["resultado"]["bytes"] == len("forked")


def test_un_pr_cruza_con_el_cuerpo_recortado(libro, monkeypatch):
    monkeypatch.setattr(srv.subprocess, "run", _RunEspia())
    monkeypatch.setattr(srv, "_cmd_exe", lambda n: "/usr/bin/gh")
    r = _local().post("/api/github/contribute/run", json={
        "action": "pr", "confirm": True,
        "opts": {"title": "Arregla el login", "body": "linea uno\nlinea dos\nlinea tres\nlinea CUATRO"}})
    assert r.status_code == 200, r.text
    c, = cruces_del_libro(libro)
    assert c["proposito"] == "gh pr create"
    assert c["carga"]["tipo"] == "cuerpo"
    assert c["carga"]["lineas"] == "Arregla el login\nlinea uno\nlinea dos"
    assert c["carga"]["tamano"] == len("Arregla el login\nlinea uno\nlinea dos\nlinea tres\nlinea CUATRO".encode())
    assert "CUATRO" not in libro.read_text()


def test_branch_es_local_y_no_cruza_pero_corre_fuera_del_loop(libro, monkeypatch):
    espia = _RunEspia()
    monkeypatch.setattr(srv.subprocess, "run", espia)
    r = _local().post("/api/github/contribute/run",
                      json={"action": "branch", "opts": {"name": "fix-login"}, "confirm": True})
    assert r.status_code == 200, r.text
    assert espia.llamadas[0]["args"][1:] == ["checkout", "-b", "fix-login"]
    assert espia.llamadas[0]["en_loop"] is False
    assert cruces_del_libro(libro) == []


def test_contribute_run_sin_confirm_ni_cruza_ni_corre(libro, monkeypatch):
    espia = _RunEspia()
    monkeypatch.setattr(srv.subprocess, "run", espia)
    r = _local().post("/api/github/contribute/run", json={"action": "fork", "opts": {}})
    assert r.status_code == 403
    assert espia.llamadas == [] and cruces_del_libro(libro) == []


def test_un_error_del_subproceso_es_500_y_fallo_en_el_libro(libro, monkeypatch):
    def bomba(*a, **k):
        raise subprocess.TimeoutExpired("gh", 120)
    monkeypatch.setattr(srv.subprocess, "run", bomba)
    monkeypatch.setattr(srv, "_cmd_exe", lambda n: "/usr/bin/gh")
    r = _local().post("/api/github/contribute/run",
                      json={"action": "fork", "opts": {}, "confirm": True})
    assert r.status_code == 500
    assert cruces_del_libro(libro)[0]["resultado"] == {
        "estado": "fallo", "error": "TimeoutExpired",
        "ms": cruces_del_libro(libro)[0]["resultado"]["ms"], "bytes": None}


def test_updates_run_corre_fuera_del_loop_y_cruza_con_el_paquete(libro, monkeypatch):
    espia = _RunEspia(stdout="added 1 package")
    monkeypatch.setattr(srv.subprocess, "run", espia)
    monkeypatch.setitem(srv.SUBSCRIPTION_CONNECTORS["claude"], "install",
                        ["npm", "install", "-g", "@anthropic-ai/claude-code@latest"])
    r = _local().post("/api/updates/run", json={"cli": "claude"})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "stdout": "added 1 package", "stderr": ""}
    assert espia.llamadas[0]["en_loop"] is False, "subprocess.run corrio en el loop"
    c, = cruces_del_libro(libro)
    assert c["quien"]["origen"] == "gesto" and c["quien"]["endpoint"] == "/api/updates/run"
    assert c["quien"]["proyecto"] == srv.ROOT.name
    assert c["proposito"] == "npm install -g"
    assert c["destino"] == {"host": "registry.npmjs.org", "url": None}
    assert c["carga"] == {"tipo": "consulta", "texto": "@anthropic-ai/claude-code@latest"}


def test_updates_run_desde_una_sesion_navegador_anota_el_aparato(libro, monkeypatch):
    monkeypatch.setattr(srv.subprocess, "run", _RunEspia())
    monkeypatch.setitem(srv.SUBSCRIPTION_CONNECTORS["claude"], "install", ["npm", "i", "-g", "x"])
    r = _pedir(REMOTO, "POST", "/api/updates/run", {"cli": "claude"},
               cookies={srv.COOKIE_SESION: _sesion("navegador", "Celular de Pedro")})
    assert r.status_code == 200, r.text
    c, = cruces_del_libro(libro)
    desde = c["quien"]["desde"]
    assert desde["credencial"] == "sesion" and desde["tipo"] == "navegador"
    assert desde["aparato"] == "Celular de Pedro" and len(desde["hash"]) == 8


def test_updates_run_con_el_npm_caido_devuelve_ok_false_sin_levantar(libro, monkeypatch):
    def bomba(*a, **k):
        raise FileNotFoundError("npm")
    monkeypatch.setattr(srv.subprocess, "run", bomba)
    monkeypatch.setitem(srv.SUBSCRIPTION_CONNECTORS["claude"], "install", ["npm", "i", "-g", "x"])
    r = _local().post("/api/updates/run", json={"cli": "claude"})
    assert r.status_code == 200 and r.json()["ok"] is False and "npm" in r.json()["stderr"]
    assert cruces_del_libro(libro)[0]["resultado"]["error"] == "FileNotFoundError"


def test_sin_la_aduana_escribible_contribute_y_updates_siguen_igual(libro, monkeypatch):
    """Spec seccion 12, por enchufe: con el libro roto (un `_escribir` que
    revienta) los dos ejecutores devuelven 200 igual, el hueco se cuenta en
    `sin_libro` y no queda linea."""
    monkeypatch.setattr(aduana, "_escribir", lambda linea: (_ for _ in ()).throw(OSError("disco")))
    monkeypatch.setattr(srv.subprocess, "run", _RunEspia(stdout="ok"))
    monkeypatch.setattr(srv, "_cmd_exe", lambda n: "/usr/bin/gh")
    monkeypatch.setitem(srv.SUBSCRIPTION_CONNECTORS["claude"], "install", ["npm", "i", "-g", "x"])
    r1 = _local().post("/api/github/contribute/run",
                       json={"action": "fork", "opts": {}, "confirm": True})
    r2 = _local().post("/api/updates/run", json={"cli": "claude"})
    assert r1.status_code == 200 and r1.json()["ok"] is True, r1.text
    assert r2.status_code == 200 and r2.json()["ok"] is True, r2.text
    assert cruces_del_libro(libro) == [] and aduana.sin_libro()["n"] == 2


def test_desde_de_sesion_y_quien_http():
    assert srv._desde_de_sesion(None) == {"credencial": "maquina"}
    assert srv._desde_de_sesion(True) == {"credencial": "maquina"}
    assert srv._desde_de_sesion({"tipo": "tablero", "aparato": "Musnap", "hash_id": "a" * 64}) == {
        "credencial": "sesion", "tipo": "tablero", "aparato": "Musnap", "hash": "aaaaaaaa"}

    class _Req:
        class state:
            pass
    q = srv._quien_http(_Req(), "ui", "/api/updates")
    assert q == aduana.Quien(origen="ui", proyecto=srv.ROOT.name, endpoint="/api/updates",
                             desde={"credencial": "maquina"})


def test_con_root_en_la_raiz_el_proyecto_no_queda_vacio(libro, monkeypatch):
    """`pathlib.Path("/").name` es "": `Quien.__post_init__` levanta
    'proyecto vacio', y `quien_turno` se arma en TODO turno antes del try
    (el websocket se caia en cada mensaje; los endpoints daban 500). El
    helper `_proyecto()` (`ROOT.name or str(ROOT)`) es el UNICO sitio que
    deriva el proyecto de ROOT."""
    monkeypatch.setattr(srv, "ROOT", pathlib.Path("/"))
    assert srv._proyecto() == "/"

    class _Req:
        class state:
            pass
    q = srv._quien_http(_Req(), "ui", "/api/updates")
    assert q.proyecto == "/"
    # los otros sitios que arman un Quien desde ROOT tampoco revientan
    srv._declarar_arranque()
    monkeypatch.setattr(srv, "_backend_availability", lambda: {"ok": True})
    srv._calentar_probes()
    assert {c["quien"]["proyecto"] for c in cruces_del_libro(libro)} == {"/"}
    # y con un ROOT normal, sigue siendo el nombre
    monkeypatch.setattr(srv, "ROOT", pathlib.Path("/tmp/proyectos/calipso"))
    assert srv._proyecto() == "calipso"


def test_ningun_sitio_del_server_deriva_el_proyecto_por_su_cuenta():
    """Guardia de texto: `proyecto=ROOT.name` no vuelve a aparecer; todo
    Quien del server pasa por `_proyecto()` (_quien_http, _declarar_arranque,
    quien_turno, el handler _reflect del ticker, _calentar_probes)."""
    fuente = pathlib.Path(srv.__file__).read_text(encoding="utf-8")
    assert "proyecto=ROOT.name" not in fuente
    assert fuente.count("proyecto=_proyecto()") >= 5


# --- Task 4: el turno de ws_chat y los endpoints de web/browser/deps -----------

from test_abismo_chat import Harness, chat, de_tipo  # noqa: E402,F401


def _research_espia(monkeypatch):
    vistos: list[tuple] = []

    def research(query, n, read, quien):
        vistos.append((query, n, read, quien))
        return {"query": query, "results": [], "pages": []}
    monkeypatch.setattr(srv.calipso_web, "research", research)
    return vistos


def test_un_web_del_turno_arma_el_quien_con_chat_proyecto_gesto_ruta_y_desde(chat, libro, monkeypatch):
    vistos = _research_espia(monkeypatch)
    eventos = chat.turno("/web precio del dolar")
    assert [e["action"] for e in de_tipo(eventos, "web")] == ["search", "results"]
    (query, n, read, quien), = vistos
    assert (query, n, read) == ("precio del dolar", 4, 2)
    assert quien == aduana.Quien(origen="turno", chat=chat.chat_id, proyecto=srv.ROOT.name,
                                 gesto="/web", ruta="local", desde={"credencial": "maquina"})


def test_una_busqueda_por_heuristica_va_sin_gesto(chat, libro, monkeypatch):
    vistos = _research_espia(monkeypatch)
    from test_abismo_chat import _decide_local

    def _decide_con_web(user_msg, last_features=None, last_verdict=None):
        verdict, features, ranked, d = _decide_local(user_msg, last_features, last_verdict)
        return verdict, dict(features, needs_web=True), ranked, d
    monkeypatch.setattr(srv, "_decide", _decide_con_web)
    chat.turno("precio del dolar hoy")
    assert vistos[0][3].gesto is None and vistos[0][3].origen == "turno"


def test_una_ruta_que_la_aduana_no_conoce_no_rompe_el_turno(chat, libro, monkeypatch):
    """Invariante 2 (medir jamas rompe el producto): si `_decide` devolviera
    una ruta que `aduana.RUTAS` no conoce, el Quien la deja en None en vez
    de reventar el turno con el ValueError de `Quien.__post_init__`. El
    resto del turno trata una ruta desconocida como local (`_chunks_for`)."""
    vistos = _research_espia(monkeypatch)
    from test_abismo_chat import _decide_local

    def _decide_rara(user_msg, last_features=None, last_verdict=None):
        verdict, features, ranked, d = _decide_local(user_msg, last_features, last_verdict)
        return dict(verdict, route="rara"), dict(features, needs_web=True), ranked, d
    monkeypatch.setattr(srv, "_decide", _decide_rara)
    eventos = chat.turno("precio del dolar hoy")
    assert [e["type"] for e in eventos].count("done") == 1
    assert vistos[0][3].ruta is None and vistos[0][3].origen == "turno"


def test_en_nube_no_hay_research_y_no_hay_cruce(chat, libro, monkeypatch):
    from calipso.privacidad import juez
    # un turno /nube pasa por la compuerta de privacidad: el juez LLM se dobla
    # (molde test_abismo_nube.py:28-38); el detector real no marca nada aca
    monkeypatch.setattr(juez.juez_llm, "juzgar_llm", lambda t: {"ok": True, "tramos": []})
    vistos = _research_espia(monkeypatch)
    chat.turno("/nube /web precio del dolar")
    assert vistos == [] and cruces_del_libro(libro) == []


def test_un_web_desde_una_sesion_navegador_lleva_el_aparato(chat, libro, monkeypatch):
    vistos = _research_espia(monkeypatch)
    remoto = TestClient(srv.app, client=(REMOTO, 4321),
                        cookies={srv.COOKIE_SESION: _sesion("navegador", "Celular de Pedro")})
    h = Harness(remoto, chat.chat_id, chat.modelo, chat.memoria, chat.pulso, chat.tmp)
    h.turno("/web precio del dolar")
    desde = vistos[0][3].desde
    assert desde["credencial"] == "sesion" and desde["tipo"] == "navegador"
    assert desde["aparato"] == "Celular de Pedro" and len(desde["hash"]) == 8


def test_gesto_de_reconstruye_el_slash():
    pd = srv.capabilities.parse_directives
    assert srv._gesto_de(pd("/web hola")) == "/web"
    assert srv._gesto_de(pd("/nube hola")) == "/nube"
    assert srv._gesto_de(pd("/claude hola")) == "/claude"
    assert srv._gesto_de(pd("/codex hola")) == "/codex"
    assert srv._gesto_de(pd("/local hola")) == "/local"
    assert srv._gesto_de(pd("/api hola")) == "/api"
    assert srv._gesto_de(pd("/plan hola")) == "/plan"
    assert srv._gesto_de(pd("/model qwen hola")) == "/model qwen"
    assert srv._gesto_de(pd("/web /claude hola")) == "/web"      # el que abre la web manda
    assert srv._gesto_de(pd("hola")) is None


def test_deps_install_cruza_como_gesto(libro, monkeypatch):
    vistos = []
    monkeypatch.setattr(srv.deps, "ensure", lambda tool, quien, run_post=True: (
        vistos.append((tool, quien)) or {"ok": True, "tool": tool}))
    r = _local().post("/api/deps/install", json={"tool": "browser"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert vistos == [("browser", aduana.Quien(origen="gesto", proyecto=srv.ROOT.name,
                                                endpoint="/api/deps/install",
                                                desde={"credencial": "maquina"}))]


def test_screenshot_cruza_como_ui_con_endpoint(libro, monkeypatch):
    vistos = []
    monkeypatch.setattr(srv.calipso_browser, "screenshot",
                        lambda url, path=None, full_page=True, *a, quien, **k: (
                            vistos.append((url, full_page, quien)) or b"png"))
    r = _local().get("/api/browser/screenshot", params={"url": "https://example.com", "full": "true"})
    assert r.status_code == 200 and r.content == b"png"
    assert vistos == [("https://example.com", True, aduana.Quien(
        origen="ui", proyecto=srv.ROOT.name, endpoint="/api/browser/screenshot",
        desde={"credencial": "maquina"}))]


def test_apply_proposal_pasa_el_quien_a_la_captura(libro, tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "ROOT", tmp_path)
    monkeypatch.setattr(srv.goals, "active", lambda raiz: None)
    vistos = []

    def captura(url, apply_fn, *a, quien, **k):
        vistos.append((url, quien))
        apply_fn()
        return b"antes", b"despues"
    monkeypatch.setattr(srv.calipso_browser, "before_after_capture", captura)
    srv.PENDING_CHANGES["cambio_x"] = {"path": "calipso/web/x.html", "content": "<p>x</p>",
                                       "source": "test"}
    r = _local().post("/api/proposals/cambio_x/apply")
    assert r.status_code == 200, r.text
    assert (tmp_path / "calipso/web/x.html").read_text() == "<p>x</p>"
    assert vistos == [("http://localhost:8000", aduana.Quien(
        origen="gesto", proyecto=tmp_path.name, endpoint="/api/proposals/{change_id}/apply",
        desde={"credencial": "maquina"}))]


# --- Task 5: los GET de github y /api/updates --------------------------------------

def test_los_get_de_github_cruzan_como_ui_con_su_endpoint(libro, monkeypatch):
    vistos: list[tuple] = []
    monkeypatch.setattr(srv.calipso_github, "available", lambda: True)
    monkeypatch.setattr(srv.calipso_github, "default_runner",
                        lambda cwd=None, timeout=15, *, quien: (
                            vistos.append(("gh", cwd, quien)) or (lambda args: (0, "{}", ""))))
    monkeypatch.setattr(srv.calipso_github, "git_runner",
                        lambda cwd=None, timeout=10, *, quien: (
                            vistos.append(("git", cwd, quien)) or (lambda args: (0, "", ""))))
    monkeypatch.setattr(srv.calipso_github, "gh_user",
                        lambda gh: {"authenticated": True, "login": "pedro"})
    monkeypatch.setattr(srv.calipso_github, "repo_overview", lambda gh, git: {"remote": None})
    r = _local().get("/api/github/overview")
    assert r.status_code == 200 and r.json()["authenticated"] is True
    esperado = aduana.Quien(origen="ui", proyecto=srv.ROOT.name,
                            endpoint="/api/github/overview", desde={"credencial": "maquina"})
    assert vistos == [("gh", str(srv.ROOT), esperado), ("git", str(srv.ROOT), esperado)]
    vistos.clear()
    monkeypatch.setattr(srv.calipso_github, "list_repos", lambda gh, limit=10: [])
    assert _local().get("/api/github/repos").status_code == 200
    assert vistos[0][2].endpoint == "/api/github/repos"
    vistos.clear()
    monkeypatch.setattr(srv.calipso_github, "assigned_items",
                        lambda gh, limit=10: {"issues": [], "prs": []})
    assert _local().get("/api/github/assigned").status_code == 200
    assert vistos[0][2].endpoint == "/api/github/assigned"


def test_api_updates_cruza_como_ui(libro, monkeypatch):
    vistos = []
    monkeypatch.setattr(srv.discovery, "updates", lambda quien: (
        vistos.append(quien) or {"clis": {}, "new_models": [], "available_models": []}))
    assert _local().get("/api/updates").status_code == 200
    assert vistos == [aduana.Quien(origen="ui", proyecto=srv.ROOT.name,
                                   endpoint="/api/updates", desde={"credencial": "maquina"})]


# --- Task 6: los declarados ---------------------------------------------------------

import sys  # noqa: E402
import types  # noqa: E402


def test_el_arranque_ya_no_declara_la_memoria(libro, monkeypatch):
    """`_declarar_arranque()` NO corre al importar el server: la llama
    `_calentar_probes` en hilo desde `_startup_warm` (con `uvicorn
    calipso.server:app` el import del modulo corre ADENTRO del loop y la
    aduana no escribiria). Y ya no declara la memoria (spec memoria por
    Ollama 2026-09-12): el embedder es Ollama en loopback, sin huggingface.co
    (la entrada `memoria_embed.py:_post_embed` del canario lo documenta). Con
    la config de la suite (todo loopback) dos llamadas dejan el libro vacio."""
    srv._declarar_arranque()
    srv._declarar_arranque()
    assert cruces_del_libro(libro) == []
    assert not hasattr(srv, "EMBED_MODEL")
    assert libro.telemetria.de("aduana_en_loop") == []


def test_un_modelo_fuera_de_la_maquina_se_declara_y_uno_loopback_no(libro, monkeypatch):
    q = quien_de_prueba(origen="arranque", chat=None, gesto=None, ruta=None)
    monkeypatch.setattr(srv.dispatch, "CONFIG", {
        "local": {"base_url": "http://localhost:11434/api/generate"},
        "api": {"base_url": "http://127.0.0.1:4000/v1/chat/completions"},
        "classifier": {"base_url": "http://[::1]:11434/api/generate"}})
    assert srv._declarar_modelos_fuera(q) == 0 and cruces_del_libro(libro) == []
    monkeypatch.setattr(srv.dispatch, "CONFIG", {
        "local": {"base_url": "http://192.168.1.50:11434/api/generate"},
        "api": {"base_url": "https://api.deepseek.com/v1/chat/completions"},
        "classifier": {"base_url": "http://localhost:11434/api/generate"}})
    assert srv._declarar_modelos_fuera(q) == 2
    a, b = cruces_del_libro(libro)
    assert a["proposito"] == "modelo fuera de la maquina" and a["declarado"] is True
    assert a["destino"]["host"] == "192.168.1.50" and a["motivo"] == "local"
    assert b["destino"]["host"] == "api.deepseek.com" and b["motivo"] == "api"


def test_un_base_url_no_parseable_se_declara_como_fuera_sin_reventar(libro, monkeypatch):
    """`urlsplit("http://[::1:11434/x")` levanta ValueError ('Invalid IPv6
    URL'). Sin try, el arranque perdia en silencio la declaracion de la
    memoria, los probes y `_backend_availability`, y PUT /api/config daba
    500 DESPUES de guardar. Fail-open: el host no parseable se trata como
    modelo fuera de la maquina, con destino=url (la aduana lo sanea) y el
    motivo lo dice."""
    q = quien_de_prueba(origen="arranque", chat=None, gesto=None, ruta=None)
    monkeypatch.setattr(srv.dispatch, "CONFIG", {
        "local": {"base_url": "http://localhost:11434/api/generate"},
        "api": {"base_url": "http://127.0.0.1:4000/v1/chat/completions"},
        "classifier": {"base_url": "http://[::1:11434/x?pwd=abc"}})
    assert srv._declarar_modelos_fuera(q) == 1
    c, = cruces_del_libro(libro)
    assert c["proposito"] == "modelo fuera de la maquina" and c["declarado"] is True
    assert c["destino"] == {"host": None, "url": "[SECRETO]"}
    assert c["motivo"] == "classifier: base_url no parseable"
    assert "abc" not in libro.read_text()


def test_put_config_con_base_url_malformado_devuelve_200_y_declara(libro, monkeypatch):
    monkeypatch.setattr(srv.calipso_config, "save_config", lambda data: {"guardado": True})
    monkeypatch.setattr(srv.calipso_config, "dispatch_config", lambda: {
        "subscription": {}, "api": {"base_url": "http://localhost:4000/v1"},
        "local": {"base_url": "http://[::1:11434/x"},
        "classifier": {"base_url": "http://localhost:11434/api/generate"}})
    viejo = srv.dispatch.CONFIG
    try:
        r = _local().put("/api/config", json={"local": {"base_url": "http://[::1:11434/x"}})
    finally:
        srv.dispatch.CONFIG = viejo
    assert r.status_code == 200, r.text
    c, = cruces_del_libro(libro)
    assert c["motivo"] == "local: base_url no parseable" and c["quien"]["origen"] == "gesto"


def test_calentar_probes_termina_con_un_base_url_malformado(libro, monkeypatch):
    monkeypatch.setattr(srv.dispatch, "CONFIG", {
        "local": {"base_url": "http://[::1:11434/x"},
        "api": {"base_url": "http://127.0.0.1:4000/v1"},
        "classifier": {"base_url": "http://localhost:11434/api/generate"}})
    monkeypatch.setattr(srv, "_backend_availability", lambda: {"ok": True})
    assert srv._calentar_probes() == {"ok": True}
    propositos = [c["proposito"] for c in cruces_del_libro(libro)]
    assert propositos == ["modelo fuera de la maquina",
                          "probes claude/codex: --version, auth status, login status"]


def test_put_config_declara_en_hilo_como_gesto(libro, monkeypatch):
    monkeypatch.setattr(srv.calipso_config, "save_config", lambda data: {"guardado": True})
    monkeypatch.setattr(srv.calipso_config, "dispatch_config", lambda: {
        "subscription": {}, "api": {"base_url": "http://localhost:4000/v1"},
        "local": {"base_url": "http://10.0.0.7:11434/api/generate"},
        "classifier": {"base_url": "http://localhost:11434/api/generate"}})
    viejo = srv.dispatch.CONFIG
    try:
        r = _local().put("/api/config", json={"local": {"base_url": "http://10.0.0.7:11434/api/generate"}})
    finally:
        srv.dispatch.CONFIG = viejo
    assert r.status_code == 200 and r.json() == {"guardado": True}
    c, = cruces_del_libro(libro)
    assert c["quien"]["origen"] == "gesto" and c["quien"]["endpoint"] == "/api/config"
    assert c["destino"]["host"] == "10.0.0.7" and c["declarado"] is True
    assert libro.telemetria.de("aduana_en_loop") == []       # fue en to_thread


def test_cli_probe_declara_una_vez_por_proceso(libro, monkeypatch):
    espia = _RunEspia(stdout="gh version 2.0")
    monkeypatch.setattr(srv.subprocess, "run", espia)
    monkeypatch.setattr(srv, "_cmd_exe", lambda n: "/usr/bin/gh")
    q = aduana.Quien(origen="ui", proyecto=srv.ROOT.name, endpoint="/api/connectors",
                     desde={"credencial": "maquina"})
    assert srv._cli_probe("github", q)["ready"] is True
    assert srv._cli_probe("github", q)["installed"] is True
    assert len(espia.llamadas) == 4                       # dos probes por llamada
    c, = cruces_del_libro(libro)                           # una sola declaracion
    assert c["declarado"] is True and c["quien"] == q.a_dict()
    assert c["proposito"] == "probe gh: --version y auth status"
    assert c["destino"] == {"host": "api.github.com", "url": None}


def test_api_connectors_pasa_el_quien_ui(libro, monkeypatch):
    vistos = []
    monkeypatch.setattr(srv, "_cli_probe", lambda name, quien: (
        vistos.append((name, quien)) or {"installed": False, "ready": False}))
    assert _local().get("/api/connectors").status_code == 200
    assert vistos == [("github", aduana.Quien(origen="ui", proyecto=srv.ROOT.name,
                                              endpoint="/api/connectors",
                                              desde={"credencial": "maquina"}))]


def test_whisper_se_declara_una_vez_dentro_del_hilo(libro, monkeypatch):
    construidos = []

    class _WhisperModel:
        def __init__(self, *a, **k):
            construidos.append((a, k))
    monkeypatch.setitem(sys.modules, "faster_whisper",
                        types.SimpleNamespace(WhisperModel=_WhisperModel))
    monkeypatch.setattr(srv, "_whisper_model", None)
    monkeypatch.setattr(srv, "_whisper_lock", asyncio.Lock())
    q = aduana.Quien(origen="gesto", proyecto=srv.ROOT.name, endpoint="/api/transcribe",
                     desde={"credencial": "maquina"})

    async def dos_veces():
        await srv._get_whisper(q)
        await srv._get_whisper(q)
    asyncio.run(dos_veces())
    assert len(construidos) == 1 and construidos[0][0] == ("tiny",)
    c, = cruces_del_libro(libro)
    assert c["declarado"] is True and c["quien"] == q.a_dict()
    assert c["proposito"] == "modelo whisper" and c["destino"]["host"] == "huggingface.co"
    assert c["motivo"] == "Systran/faster-whisper-tiny"
    assert libro.telemetria.de("aduana_en_loop") == []


def test_los_probes_se_declaran_una_vez_al_calentar(libro, monkeypatch):
    """`_calentar_probes` es el unico lugar del arranque que escribe en el
    libro: primero `_declarar_arranque` (los modelos fuera de la maquina,
    cero con la config de la suite; la memoria ya no sale: embebe por Ollama
    en loopback), despues los probes. Dos llamadas, una linea: las banderas
    `una vez` valen por proceso."""
    monkeypatch.setattr(srv, "_backend_availability", lambda: {"ok": True})
    assert srv._calentar_probes() == {"ok": True}
    assert srv._calentar_probes() == {"ok": True}
    c, = cruces_del_libro(libro)
    assert c["declarado"] is True and c["quien"]["origen"] == "arranque"
    assert c["proposito"] == "probes claude/codex: --version, auth status, login status"
    assert c["destino"] == {"host": None, "url": None}


def test_startup_warm_calienta_los_probes_en_hilo(libro, monkeypatch):
    vistos = []

    def calentar():
        try:
            asyncio.get_running_loop()
            vistos.append(True)
        except RuntimeError:
            vistos.append(False)
        return {}
    monkeypatch.setattr(srv, "_calentar_probes", calentar)
    monkeypatch.setattr(srv.discovery, "discover",
                        lambda register=True: {"added": [], "local": [], "api": []})
    # los dobles REGISTRAN: si el implementador reemplaza `_startup_warm`
    # entera por el bloque `try/except` del plan y pierde las seis lineas
    # que siguen (rutinas + ticker), este test se pone en rojo
    llamadas = []
    for nombre in ("_asegurar_rutina_catastro", "_asegurar_rutina_cierre",
                   "_asegurar_rutina_consumo"):
        monkeypatch.setattr(srv, nombre, lambda n=nombre: llamadas.append(n))

    async def _nada():
        return None

    def ticker():
        # se anota al CREAR la corutina (sincrono, garantizado), no al
        # correrla: `asyncio.run` puede cancelar la task antes de su primer paso
        llamadas.append("_routines_ticker")
        return _nada()
    monkeypatch.setattr(srv, "_routines_ticker", ticker)
    asyncio.run(srv._startup_warm())
    assert vistos == [False], "los probes se declararon EN el loop"
    assert llamadas == ["_asegurar_rutina_catastro", "_asegurar_rutina_cierre",
                        "_asegurar_rutina_consumo", "_routines_ticker"]   # el resto de _startup_warm sigue vivo


def test_un_fallo_de_discover_no_se_lleva_los_probes(libro, monkeypatch):
    """Los dos `to_thread` del arranque tienen cada uno su try: un
    `discovery.discover` que levanta no deja sin declarar la memoria ni sin
    calentar los probes (y viceversa)."""
    vistos = []
    monkeypatch.setattr(srv, "_calentar_probes", lambda: vistos.append("probes") or {})

    def revienta(register=True):
        raise RuntimeError("ollama caido")
    monkeypatch.setattr(srv.discovery, "discover", revienta)
    for nombre in ("_asegurar_rutina_catastro", "_asegurar_rutina_cierre",
                   "_asegurar_rutina_consumo"):
        monkeypatch.setattr(srv, nombre, lambda: None)

    async def _nada():
        return None
    monkeypatch.setattr(srv, "_routines_ticker", lambda: _nada())
    asyncio.run(srv._startup_warm())
    assert vistos == ["probes"]


class _AmbitoFalso:
    name = "global"

    def __init__(self, episodios):
        self.episodios, self.core = episodios, []

    def recent(self, limit):
        return self.episodios[:limit]

    def append_core(self, kind, fact):
        self.core.append((kind, fact))
        return True


def test_reflect_se_declara_por_llamada_antes_del_claude(libro, monkeypatch):
    from calipso import memory as memoria
    monkeypatch.setattr(memoria.shutil, "which", lambda n: "/usr/bin/claude")
    espia = _RunEspia(stdout='{"facts": [{"scope": "global", "fact": "Pedro es musico"}]}')
    monkeypatch.setattr(memoria.subprocess, "run", espia)
    yo = types.SimpleNamespace(project=None, glob=_AmbitoFalso(["ep uno", "ep dos"]))
    q = quien_de_prueba(origen="rutina", chat=None, gesto=None, ruta=None,
                        rutina={"kind": "reflect", "id": "rt_1"})
    assert srv.Memory.reflect(yo, q) == [{"scope": "global", "fact": "Pedro es musico"}]
    assert espia.llamadas[0]["args"][:2] == ["/usr/bin/claude", "-p"]
    c, = cruces_del_libro(libro)
    assert c["declarado"] is True and c["quien"]["rutina"] == {"kind": "reflect", "id": "rt_1"}
    assert c["proposito"] == "reflect" and c["motivo"] == "2 episodios a claude -p"
    assert c["destino"]["host"] == "api.anthropic.com"
    assert "ep uno" not in libro.read_text()


def test_reflect_sin_claude_no_declara_nada(libro, monkeypatch):
    from calipso import memory as memoria
    monkeypatch.setattr(memoria.shutil, "which", lambda n: None)
    yo = types.SimpleNamespace(project=None, glob=_AmbitoFalso(["ep"]))
    assert srv.Memory.reflect(yo, quien_de_prueba())[0]["error"].startswith("claude no instalado")
    assert cruces_del_libro(libro) == []


def test_el_handler_de_reflect_arma_el_quien_de_rutina_o_usa_el_del_boton(libro, monkeypatch):
    vistos = []
    monkeypatch.setattr(srv, "mem", types.SimpleNamespace(
        reflect=lambda quien, limit=20: vistos.append(quien) or []))
    handler = srv._routine_handlers()["reflect"]
    handler({"id": "rt_abc", "kind": "reflect", "enabled": True})            # el ticker
    assert vistos[-1] == aduana.Quien(origen="rutina", proyecto=srv.ROOT.name,
                                      rutina={"kind": "reflect", "id": "rt_abc"},
                                      desde={"credencial": "maquina"})
    q = aduana.Quien(origen="gesto", proyecto=srv.ROOT.name, endpoint="/api/routines/{id}/run",
                     rutina={"kind": "reflect", "id": "rt_abc"}, desde={"credencial": "maquina"})
    handler({"id": "rt_abc", "kind": "reflect", "quien": q.a_dict()})       # el boton
    assert vistos[-1] == q


def test_post_reflect_y_routines_run_declaran_como_gesto(libro, monkeypatch):
    vistos = []
    monkeypatch.setattr(srv, "mem", types.SimpleNamespace(
        reflect=lambda quien, limit=20: vistos.append(quien) or []))
    assert _local().post("/api/reflect").status_code == 200
    assert vistos[-1] == aduana.Quien(origen="gesto", proyecto=srv.ROOT.name,
                                      endpoint="/api/reflect", desde={"credencial": "maquina"})
    monkeypatch.setattr(srv.calipso_routines, "get",
                        lambda rid: {"id": rid, "kind": "reflect", "enabled": False})
    monkeypatch.setattr(srv.calipso_routines, "mark_run", lambda *a, **k: None)
    r = _local().post("/api/routines/rt_abc/run")
    assert r.status_code == 200 and r.json()["ok"] is True
    assert vistos[-1] == aduana.Quien(origen="gesto", proyecto=srv.ROOT.name,
                                      endpoint="/api/routines/{id}/run",
                                      rutina={"kind": "reflect", "id": "rt_abc"},
                                      desde={"credencial": "maquina"})


def test_la_vision_del_turno_hereda_el_quien_del_turno(chat, libro, monkeypatch):
    vistos = []
    monkeypatch.setattr(srv.attachments, "has_images", lambda root, ids: True)
    # el doble acepta `permitir_ollama` (spec carga 3.5: la vision por Ollama
    # solo bajo holgada); aca no se mira, el test es sobre el Quien
    monkeypatch.setattr(srv.attachments, "vision_describe",
                        lambda root, ids, question, *, quien, permitir_ollama=True:
                        vistos.append(quien) or None)
    # el paquete del ws lleva `attachment_ids` (server.py:3284); el id no
    # existe en disco: `context_block` lo saltea y `has_images` esta doblado
    with chat.cliente.websocket_connect("/ws/chat") as ws:
        ws.send_text(json.dumps({"text": "que ves", "chat_id": chat.chat_id,
                                 "attachment_ids": ["att_1"]}))
        chat.recibir(ws, 1)
    assert vistos and vistos[0].origen == "turno" and vistos[0].chat == chat.chat_id
    assert vistos[0].gesto is None and vistos[0].ruta == "local"


# --- Task 7: GET /api/aduana ---------------------------------------------------------

def _sembrar(libro, monkeypatch):
    """Tres lineas con reloj fijo (una de ayer, un cruce y un declarado de
    hoy) y una linea rota al final."""
    relojes = iter(["2026-09-09T23:00:00", "2026-09-10T10:00:00", "2026-09-10T11:00:00"])
    monkeypatch.setattr(aduana, "_ahora", lambda: next(relojes))
    monkeypatch.setattr(aduana, "_hoy", lambda: "2026-09-10")
    with aduana.cruzar(quien_de_prueba(chat="chat_ayer"), "ayer", "https://a.com/", carga="vieja"):
        pass
    with aduana.cruzar(quien_de_prueba(chat="chat_1"), "buscar en la web",
                       "https://html.duckduckgo.com/html/", carga="precio del dolar"):
        pass
    aduana.declarar(quien_de_prueba(origen="arranque", chat=None, gesto=None, ruta=None),
                    "modelo de embeddings", "huggingface.co")
    with open(libro, "a", encoding="utf-8") as f:
        f.write("{rota\n")


def test_loopback_ve_todo_con_totales_e_ilegibles(libro, monkeypatch):
    _sembrar(libro, monkeypatch)
    r = _local().get("/api/aduana")
    assert r.status_code == 200, r.text
    d = r.json()
    assert [c["proposito"] for c in d["cruces"]] == ["buscar en la web", "modelo de embeddings"]
    assert d["cruces"][0]["carga"] == {"tipo": "consulta", "texto": "precio del dolar"}
    assert d["cruces"][0]["quien"]["chat"] == "chat_1"
    assert d["cruces"][0]["destino"]["url"] == "https://html.duckduckgo.com/html/"
    assert d["totales"] == {"por_origen": {"turno": 1, "arranque": 1},
                            "por_destino": {"html.duckduckgo.com": 1, "huggingface.co": 1},
                            "por_proyecto": {"calipso": 2}, "por_desde": {"maquina": 2},
                            "declarados": 1}
    assert d["ilegibles"] == 1
    assert d["sin_libro"] == {"n": 0, "desde": None, "ultimo_error": None}


def test_una_linea_editada_a_mano_con_tipos_raros_no_tumba_el_endpoint(libro, monkeypatch):
    _sembrar(libro, monkeypatch)
    with open(libro, "a", encoding="utf-8") as f:
        f.write('{"ts": 123, "quien": {}}\n')
        f.write('{"ts": "2026-09-10T12:00:00", "quien": {"origen": "ui"}, "destino": "x"}\n')
    r = _local().get("/api/aduana")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ilegibles"] == 3 and len(d["cruces"]) == 2


def test_los_filtros_del_querystring(libro, monkeypatch):
    _sembrar(libro, monkeypatch)
    solo_arranque = _local().get("/api/aduana", params={"origen": "arranque"}).json()
    assert [c["proposito"] for c in solo_arranque["cruces"]] == ["modelo de embeddings"]
    rango = _local().get("/api/aduana", params={"desde": "2026-09-09",
                                                "hasta": "2026-09-10T10:30:00"}).json()
    assert [c["proposito"] for c in rango["cruces"]] == ["ayer", "buscar en la web"]


def test_sin_libro_viene_de_memoria_sin_tocar_el_disco(libro, monkeypatch):
    def bomba(ruta, linea):
        raise OSError(errno.ENOSPC, "disco lleno", str(ruta))
    monkeypatch.setattr(aduana, "_append", bomba)
    with aduana.cruzar(quien_de_prueba(), "x", None):
        pass
    d = _local().get("/api/aduana").json()
    assert d["cruces"] == [] and d["ilegibles"] == 0
    assert d["sin_libro"]["n"] == 1 and d["sin_libro"]["ultimo_error"] == "OSError: disco lleno"
    assert str(libro) not in d["sin_libro"]["ultimo_error"]     # sin la ruta del disco


def test_navegador_ve_todo_tablero_recortado_lector_403(libro, monkeypatch):
    _sembrar(libro, monkeypatch)
    nav = _pedir(REMOTO, "GET", "/api/aduana",
                 cookies={srv.COOKIE_SESION: _sesion("navegador", "Celular")})
    assert nav.status_code == 200, nav.text
    assert nav.json()["cruces"][0]["carga"]["texto"] == "precio del dolar"
    assert nav.json()["cruces"][0]["quien"]["chat"] == "chat_1"
    tab = _pedir(REMOTO, "GET", "/api/aduana",
                 cookies={srv.COOKIE_SESION: _sesion("tablero", "Musnap")})
    assert tab.status_code == 200, tab.text
    d = tab.json()
    assert d["totales"]["por_origen"] == {"turno": 1, "arranque": 1}
    assert d["ilegibles"] == 1 and d["sin_libro"]["n"] == 0
    c = d["cruces"][0]
    assert "carga" not in c and "chat" not in c["quien"]
    assert c["destino"] == {"host": "html.duckduckgo.com"}
    assert c["quien"]["origen"] == "turno" and c["proposito"] == "buscar en la web"
    assert c["resultado"]["estado"] == "ok" and c["declarado"] is False
    assert d["cruces"][1]["declarado"] is True
    assert "precio del dolar" not in tab.text and "chat_1" not in tab.text
    lec = _pedir(REMOTO, "GET", "/api/aduana",
                 cookies={srv.COOKIE_SESION: _sesion("lector", "Musnap")})
    assert lec.status_code == 403
    assert lec.json() == {"detail": "fuera del alcance del aparato"}


def test_sin_credencial_es_401():
    assert TestClient(srv.app).get("/api/aduana").status_code == 401
