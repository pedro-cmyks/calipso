"""Revision de seguridad 2026-09-07, punto 3a: los portones de la puerta de
red que bloqueaban abrir CALIPSO_HOST -- C3 (freno de fuerza bruta en
/login), C7/S3 (CALIPSO_NO_TOTP solo desde loopback) y C8 (?token= solo
desde la propia maquina)."""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

import calipso.server as srv


@pytest.fixture(autouse=True)
def _login_limpio():
    with srv._login_lock:
        srv._login_fallos.clear()
    yield
    with srv._login_lock:
        srv._login_fallos.clear()


# --- helpers ----------------------------------------------------------------

def test_es_loopback():
    assert srv._es_loopback("127.0.0.1")
    assert srv._es_loopback("::1")
    assert srv._es_loopback("testclient")
    assert not srv._es_loopback("192.168.1.7")
    assert not srv._es_loopback("100.101.102.103")
    assert not srv._es_loopback(None)


# --- C3: el freno de fuerza bruta -------------------------------------------

def test_backoff_exponencial_desde_el_quinto_fallo(monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(srv, "_login_reloj", lambda: t[0])
    for _ in range(4):
        srv._login_fallo("h")
    assert srv._login_espera("h", srv._LOGIN_MAX_FALLOS_HOST) == 0.0
    srv._login_fallo("h")  # 5to: castigo base
    assert srv._login_espera("h", srv._LOGIN_MAX_FALLOS_HOST) == pytest.approx(2.0)
    t[0] += 2.5  # paso el castigo
    assert srv._login_espera("h", srv._LOGIN_MAX_FALLOS_HOST) == 0.0
    srv._login_fallo("h")  # 6to: castigo doble
    assert srv._login_espera("h", srv._LOGIN_MAX_FALLOS_HOST) == pytest.approx(4.0)


def test_castigo_con_tope(monkeypatch):
    t = [1000.0]
    monkeypatch.setattr(srv, "_login_reloj", lambda: t[0])
    for _ in range(30):
        srv._login_fallo("h")
    assert (srv._login_espera("h", srv._LOGIN_MAX_FALLOS_HOST)
            == pytest.approx(srv._LOGIN_BACKOFF_TOPE))


def test_exito_limpia_el_host_pero_no_el_balde_global(monkeypatch):
    monkeypatch.setattr(srv, "_login_reloj", lambda: 1000.0)
    for _ in range(6):
        srv._login_fallo("h")
        srv._login_fallo("*")
    srv._login_exito("h")
    assert srv._login_espera("h", srv._LOGIN_MAX_FALLOS_HOST) == 0.0
    # el balde global no llego a su umbral (20) pero conserva los fallos
    with srv._login_lock:
        assert srv._login_fallos["*"][0] == 6


def test_el_endpoint_devuelve_429_tras_cinco_fallos(monkeypatch):
    monkeypatch.setattr(srv, "_TOTP_DISABLED", False)
    monkeypatch.setattr(srv, "_verify_totp", lambda code: False)
    c = TestClient(app=srv.app)
    for _ in range(5):
        r = c.post("/login", data={"code": "000000"})
        assert r.status_code == 401
    r = c.post("/login", data={"code": "000000"})
    assert r.status_code == 429
    assert "Demasiados intentos" in r.text
    # y el 429 NO consume el codigo: no siguio contando fallos
    with srv._login_lock:
        assert srv._login_fallos["testclient"][0] == 5


def test_el_balde_global_frena_hosts_nuevos(monkeypatch):
    monkeypatch.setattr(srv, "_login_reloj", lambda: 1000.0)
    for _ in range(srv._LOGIN_MAX_FALLOS_GLOBAL):
        srv._login_fallo("*")
    # un host que jamas fallo queda igualmente frenado por el balde global
    espera = max(srv._login_espera("fresco", srv._LOGIN_MAX_FALLOS_HOST),
                 srv._login_espera("*", srv._LOGIN_MAX_FALLOS_GLOBAL))
    assert espera > 0


# --- C7/S3: el bypass de TOTP solo desde la propia maquina -------------------

def test_totp_bypass_solo_loopback(monkeypatch):
    monkeypatch.setattr(srv, "_TOTP_DISABLED", True)
    assert srv._totp_bypass_permitido("127.0.0.1")
    assert srv._totp_bypass_permitido("testclient")
    assert not srv._totp_bypass_permitido("192.168.1.7")
    monkeypatch.setattr(srv, "_TOTP_DISABLED", False)
    assert not srv._totp_bypass_permitido("127.0.0.1")


def test_el_anuncio_de_totp_desactivado_no_se_muestra_a_remotos(monkeypatch):
    monkeypatch.setattr(srv, "_TOTP_DISABLED", True)
    assert "desactivado" in srv._login_mode_html("127.0.0.1")
    assert "desactivado" not in srv._login_mode_html("10.0.0.9")


# --- C8: ?token= solo desde la propia maquina --------------------------------

def _pedir_como(ip: str, ruta: str) -> httpx.Response:
    transporte = httpx.ASGITransport(app=srv.app, client=(ip, 4321))

    async def _ir():
        async with httpx.AsyncClient(transport=transporte,
                                     base_url="http://calipso") as c:
            return await c.get(ruta)

    return asyncio.run(_ir())


def test_token_por_url_entra_desde_loopback():
    r = _pedir_como("127.0.0.1", f"/api/project?token={srv.TOKEN}")
    assert r.status_code == 200


def test_token_por_url_no_entra_desde_afuera():
    r = _pedir_como("192.168.1.66", f"/api/project?token={srv.TOKEN}")
    assert r.status_code == 401
    r = _pedir_como("100.101.102.103", f"/?token={srv.TOKEN}")
    assert r.status_code == 303  # a /login, sin sesion
    assert r.headers["location"] == "/login"


def test_cookie_si_entra_desde_afuera():
    # La cookie (ganada por /login con TOTP) es la via remota legitima.
    transporte = httpx.ASGITransport(app=srv.app, client=("192.168.1.66", 4321))

    async def _ir():
        async with httpx.AsyncClient(transport=transporte,
                                     base_url="http://calipso",
                                     cookies={srv.COOKIE: srv.TOKEN}) as c:
            return await c.get("/api/project")

    assert asyncio.run(_ir()).status_code == 200
