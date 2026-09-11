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
import json
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
