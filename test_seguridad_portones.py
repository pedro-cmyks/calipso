"""Revision de seguridad 2026-09-07, punto 3a: tres de los portones que
bloquean abrir CALIPSO_HOST -- C3 (freno de fuerza bruta en /login), C7/S3
(CALIPSO_NO_TOTP solo desde loopback) y C8 (?token= solo desde la propia
maquina). OJO: abrir el host sigue bloqueado por lo que falta del punto 3
(capa de sesion + identidad de aparato, ver la adenda 3a del informe)."""
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
    # 900 LITERAL: el numero ES el contrato (mismo criterio que 2.0/4.0);
    # bajar el tope debilita el freno y tiene que romper este test
    assert (srv._login_espera("h", srv._LOGIN_MAX_FALLOS_HOST)
            == pytest.approx(900.0))
    assert srv._LOGIN_MAX_FALLOS_GLOBAL == 20


def test_el_decaimiento_evapora_typos_pero_no_regala_rafagas(monkeypatch):
    # Las dos propiedades del decaimiento, juntas porque juntas son el
    # contrato: (a) la historia inocente se evapora sola -- 3 typos de hace
    # semanas mueren; (b) el atacante que pausa 901s ve su contador bajar
    # UNO, no reiniciarse (la poda que borraba la entrada entera le
    # regalaba una rafaga fresca: ~13x mas intentos/dia, simulado en la
    # verificacion adversaria).
    t = [1000.0]
    monkeypatch.setattr(srv, "_login_reloj", lambda: t[0])
    for _ in range(3):
        srv._login_fallo("inocente")
    for _ in range(25):
        srv._login_fallo("*")
    t[0] += 4 * srv._LOGIN_BACKOFF_TOPE + 1
    srv._login_fallo("otro-host")
    with srv._login_lock:
        assert "inocente" not in srv._login_fallos      # 3 - 4 ventanas: muerto
        assert srv._login_fallos["*"][0] == 25 - 4      # decae, no resetea
        assert srv._login_fallos["otro-host"][0] == 1
    # y el que decayo sigue frenado si aun supera el umbral
    espera = srv._login_espera("*", srv._LOGIN_MAX_FALLOS_GLOBAL)
    assert espera > 0


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
    monkeypatch.setattr(srv, "_login_reloj", lambda: 1000.0)  # sin flakiness
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


def test_login_exitoso_planta_cookie_y_limpia_el_host(monkeypatch):
    monkeypatch.setattr(srv, "_TOTP_DISABLED", False)
    monkeypatch.setattr(srv, "_verify_totp", lambda code: code == "123456")
    monkeypatch.setattr(srv, "_login_reloj", lambda: 1000.0)
    c = TestClient(app=srv.app)
    for _ in range(4):
        assert c.post("/login", data={"code": "000000"}).status_code == 401
    r = c.post("/login", data={"code": "123456"}, follow_redirects=False)
    assert r.status_code == 303
    assert srv.COOKIE in r.cookies
    with srv._login_lock:
        assert "testclient" not in srv._login_fallos  # el host se limpia
        assert srv._login_fallos["*"][0] == 4         # el balde global no


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


def _postear_login_como(ip: str, code: str) -> httpx.Response:
    transporte = httpx.ASGITransport(app=srv.app, client=(ip, 4321))

    async def _ir():
        async with httpx.AsyncClient(transport=transporte,
                                     base_url="http://calipso") as c:
            return await c.post("/login", data={"code": code})

    return asyncio.run(_ir())


def test_no_totp_no_vale_desde_afuera(monkeypatch):
    # El canario de C7: revertir el bypass a `if _TOTP_DISABLED or ...`
    # tiene que romper ESTE test, no solo los helpers.
    monkeypatch.setattr(srv, "_TOTP_DISABLED", True)
    monkeypatch.setattr(srv, "_verify_totp", lambda code: False)
    monkeypatch.setattr(srv, "_login_reloj", lambda: 1000.0)
    assert _postear_login_como("192.168.1.66", "000000").status_code == 401
    assert _postear_login_como("127.0.0.1", "000000").status_code == 303


def test_el_balde_global_frena_por_el_endpoint(monkeypatch):
    monkeypatch.setattr(srv, "_TOTP_DISABLED", False)
    monkeypatch.setattr(srv, "_verify_totp", lambda code: False)
    monkeypatch.setattr(srv, "_login_reloj", lambda: 1000.0)
    with srv._login_lock:
        srv._login_fallos["*"] = [srv._LOGIN_MAX_FALLOS_GLOBAL, 1000.0]
    assert _postear_login_como("10.9.8.7", "000000").status_code == 429


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
