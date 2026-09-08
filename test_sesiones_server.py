#!/usr/bin/env python3
"""
test_sesiones_server.py — Los endpoints del alta de aparatos (spec de la capa
de sesion, seccion 3 "El guard" punto 2 y "Alta, revocacion y corte";
invariantes 4, 6 y 8).

Lo que se prueba aca no es el almacen (eso es test_sesiones.py) sino la
COSTURA: quien entra sin credencial, quien no entra ni con ella, y que el
freno del alta no comparta un solo contador con el del login. El canario de
esa separacion (martillar `golpear` y ver que `/login` sigue contestando 401)
existe porque compartir el balde le regalaria a un martillador anonimo la
palanca para dejar a Pedro afuera de su propio TOTP.

El host remoto se simula con `httpx.ASGITransport(client=(ip, puerto))`: el
`TestClient` de Starlette siempre dice "testclient", que `_es_loopback`
acepta, asi que con el solo no se puede escribir un test de "desde afuera".
"""
import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso import sesiones

REMOTO = "192.168.1.66"


@pytest.fixture(autouse=True)
def _almacen_aislado(tmp_path, monkeypatch):
    """El almacen del modulo, no el de Pedro. La cache es un dict de modulo:
    uno nuevo por test para que ninguno herede el archivo del anterior."""
    monkeypatch.setattr(sesiones, "_ruta", lambda: tmp_path / "sesiones.json")
    monkeypatch.setattr(sesiones, "_CACHE", sesiones._cache_vacia())


@pytest.fixture(autouse=True)
def _freno_limpio():
    """Los contadores del freno son estado de modulo compartido con el login:
    un test que los deje sucios frena al siguiente."""
    with srv._login_lock:
        srv._login_fallos.clear()
    yield
    with srv._login_lock:
        srv._login_fallos.clear()


@pytest.fixture(autouse=True)
def _reloj_del_freno(monkeypatch):
    """Congelado: el backoff se mide en segundos y una suite lenta no puede
    cambiar el resultado de un assert."""
    monkeypatch.setattr(srv, "_login_reloj", lambda: 1000.0)


# --- helpers ----------------------------------------------------------------

def _pedir(ip: str, metodo: str, ruta: str, cuerpo=None,
           cookies=None) -> httpx.Response:
    transporte = httpx.ASGITransport(app=srv.app, client=(ip, 4321))

    async def _ir():
        async with httpx.AsyncClient(transport=transporte,
                                     base_url="http://calipso",
                                     cookies=cookies) as c:
            return await c.request(metodo, ruta, json=cuerpo)

    return asyncio.run(_ir())


def _postear(ip: str, ruta: str, cuerpo=None, cookies=None) -> httpx.Response:
    return _pedir(ip, "POST", ruta, cuerpo if cuerpo is not None else {},
                  cookies)


def _local() -> TestClient:
    """Loopback CON la credencial de hoy. Aprobar, rechazar y listar viven
    detras del guard, y el guard todavia es el viejo (cookie-token)."""
    return TestClient(app=srv.app, cookies={srv.COOKIE: srv.TOKEN})


def _golpe(ip: str = REMOTO, aparato: str = "Lector de Pedro",
           tipo: str = "lector") -> str:
    r = _postear(ip, "/api/aparatos/golpear",
                 {"aparato": aparato, "tipo": tipo})
    assert r.status_code == 200, r.text
    return r.json()["id_pedido"]


def _fallos(clave: str) -> int:
    with srv._login_lock:
        return srv._login_fallos.get(clave, [0])[0]


# --- golpear ----------------------------------------------------------------

def test_golpear_remoto_estaciona_el_pedido_sin_credencial():
    r = _postear(REMOTO, "/api/aparatos/golpear",
                 {"aparato": "Musnap Neo C", "tipo": "lector"})
    assert r.status_code == 200, r.text
    id_pedido = r.json()["id_pedido"]
    assert sesiones.estado(id_pedido) == "golpeando"
    # estacionado, no vivo: el aparato no se aprueba solo
    assert sesiones.resolver(id_pedido) is None


def test_golpear_rechaza_el_tipo_basura_y_el_nombre_largo():
    r = _postear(REMOTO, "/api/aparatos/golpear",
                 {"aparato": "Ally", "tipo": "administrador"})
    assert r.status_code == 422, r.text
    r = _postear(REMOTO, "/api/aparatos/golpear",
                 {"aparato": "x" * 61, "tipo": "lector"})
    assert r.status_code == 422, r.text
    assert sesiones.listar() == []
    # un pedido invalido es un fallo: sin eso, el 422 seria un martillo gratis
    assert _fallos(f"aparatos:{REMOTO}") == 2


def test_golpear_con_el_almacen_lleno_es_429():
    for _ in range(sesiones.GOLPES_PENDIENTES_MAX):
        _golpe(ip="10.0.0.5")
    r = _postear("10.0.0.9", "/api/aparatos/golpear",
                 {"aparato": "Ally", "tipo": "lector"})
    assert r.status_code == 429, r.text
    # el 429 del almacen lleno, no el del freno: el host que pide es otro y
    # no tiene ni un fallo. Dos 429 distintos que hay que poder distinguir.
    assert "golpes esperando" in r.json()["detail"]


# --- estado -----------------------------------------------------------------

def test_estado_de_un_pedido_desconocido_es_404_y_cuenta_fallo():
    r = _postear(REMOTO, "/api/aparatos/estado", {"id_pedido": "inventado"})
    assert r.status_code == 404, r.text
    assert _fallos(f"aparatos:{REMOTO}") == 1


def test_sondear_un_pedido_valido_es_gratis():
    id_pedido = _golpe()
    with srv._login_lock:
        srv._login_fallos.clear()   # el golpe ya conto; lo que se mide es el sondeo
    for _ in range(30):
        r = _postear(REMOTO, "/api/aparatos/estado", {"id_pedido": id_pedido})
        assert r.status_code == 200, r.text
        assert r.json() == {"estado": "golpeando"}
    with srv._login_lock:
        assert srv._login_fallos == {}


# --- el freno propio --------------------------------------------------------

def test_martillar_golpear_frena_sin_tocar_el_balde_del_login(monkeypatch):
    """El canario de la separacion: un martillador anonimo se frena a si
    mismo y NO deja a Pedro afuera del TOTP."""
    monkeypatch.setattr(srv, "_TOTP_DISABLED", False)
    monkeypatch.setattr(srv, "_verify_totp", lambda code: False)
    codigos = [_postear(REMOTO, "/api/aparatos/golpear",
                        {"aparato": "Ally", "tipo": "lector"}).status_code
               for _ in range(25)]
    assert 429 in codigos
    assert codigos[-1] == 429
    assert _fallos(f"aparatos:{REMOTO}") == srv._LOGIN_MAX_FALLOS_HOST
    assert _fallos("aparatos:*") == srv._LOGIN_MAX_FALLOS_HOST
    with srv._login_lock:
        assert "*" not in srv._login_fallos       # el balde del login, intacto
        assert REMOTO not in srv._login_fallos    # y su clave pelada tambien
    # y el login del mismo host sigue vivo: 401 (codigo malo), no 429
    r = _pedir(REMOTO, "POST", "/login")
    assert r.status_code == 401, r.text


def test_el_429_del_freno_trae_retry_after():
    for _ in range(srv._LOGIN_MAX_FALLOS_HOST):
        _postear(REMOTO, "/api/aparatos/estado", {"id_pedido": "inventado"})
    r = _postear(REMOTO, "/api/aparatos/estado", {"id_pedido": "inventado"})
    assert r.status_code == 429, r.text
    assert r.json() == {"detail": "demasiados intentos"}
    assert int(r.headers["Retry-After"]) > 0
    # el 429 no consume nada: el contador quedo donde estaba
    assert _fallos(f"aparatos:{REMOTO}") == srv._LOGIN_MAX_FALLOS_HOST


def test_el_freno_del_login_no_frena_el_alta():
    """La otra mitad de la separacion: los baldes del login llenos no le
    cierran la puerta a un aparato que recien llega."""
    for _ in range(srv._LOGIN_MAX_FALLOS_GLOBAL):
        srv._login_fallo("*")
    srv._login_fallo(REMOTO)
    assert sesiones.estado(_golpe()) == "golpeando"


# --- aprobar y rechazar: solo desde la Ally (invariante 4) -------------------

def test_aprobar_desde_remoto_es_403_aunque_traiga_la_credencial():
    id_pedido = _golpe()
    r = _postear(REMOTO, "/api/aparatos/aprobar",
                 {"id_pedido": id_pedido, "tipo": "navegador"},
                 cookies={srv.COOKIE: srv.TOKEN})
    assert r.status_code == 403, r.text
    assert r.json() == {"detail": "aprobar es solo desde la Ally"}
    assert sesiones.estado(id_pedido) == "golpeando"


def test_rechazar_desde_remoto_es_403_aunque_traiga_la_credencial():
    id_pedido = _golpe()
    r = _postear(REMOTO, "/api/aparatos/rechazar", {"id_pedido": id_pedido},
                 cookies={srv.COOKIE: srv.TOKEN})
    assert r.status_code == 403, r.text
    assert sesiones.estado(id_pedido) == "golpeando"


def test_aprobar_desde_loopback_fija_el_tipo_que_elige_pedro():
    """El canario del spec: el tipo del golpe es una SUGERENCIA. Si el
    aparato pudiera elegirse el alcance, pedir "navegador" seria pedir la
    casa entera."""
    id_pedido = _golpe(aparato="Musnap", tipo="navegador")
    r = _local().post("/api/aparatos/aprobar",
                      json={"id_pedido": id_pedido, "tipo": "lector"})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True}
    assert sesiones.estado(id_pedido) == "viva"
    assert [s["tipo"] for s in sesiones.listar()] == ["lector"]


def test_rechazar_desde_loopback_deja_el_pedido_rechazado():
    id_pedido = _golpe()
    r = _local().post("/api/aparatos/rechazar", json={"id_pedido": id_pedido})
    assert r.status_code == 200, r.text
    assert sesiones.estado(id_pedido) == "rechazada"


def test_aprobar_un_pedido_desconocido_es_404():
    r = _local().post("/api/aparatos/aprobar",
                      json={"id_pedido": "inventado", "tipo": "lector"})
    assert r.status_code == 404, r.text
    # el detail distingue este 404 del que da una ruta que no existe
    assert r.json() == {"detail": "no hay un golpe vigente"}


def test_aprobar_con_un_tipo_desconocido_es_422():
    id_pedido = _golpe()
    r = _local().post("/api/aparatos/aprobar",
                      json={"id_pedido": id_pedido, "tipo": "administrador"})
    assert r.status_code == 422, r.text
    assert sesiones.estado(id_pedido) == "golpeando"


# --- canjear: la cookie se entrega UNA vez (invariante 8) --------------------

def test_el_canje_entrega_la_cookie_una_sola_vez():
    id_pedido = _golpe()
    assert _local().post("/api/aparatos/aprobar",
                         json={"id_pedido": id_pedido,
                               "tipo": "lector"}).status_code == 200
    r = _postear(REMOTO, "/api/aparatos/canjear", {"id_pedido": id_pedido})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "tipo": "lector"}
    galleta = r.headers["set-cookie"]
    assert galleta.startswith("calipso_sesion=")
    assert "HttpOnly" in galleta
    assert "SameSite=lax" in galleta
    assert "Max-Age=2592000" in galleta
    assert "Path=/" in galleta
    # la cookie que salio resuelve, y el id en claro no quedo en el disco
    id_sesion = r.cookies["calipso_sesion"]
    assert sesiones.resolver(id_sesion)["tipo"] == "lector"
    assert id_sesion not in (sesiones._ruta()).read_text(encoding="utf-8")
    # segundo canje: el id_pedido se quemo
    otra = _postear(REMOTO, "/api/aparatos/canjear", {"id_pedido": id_pedido})
    assert otra.status_code == 404, otra.text
    assert "set-cookie" not in otra.headers


def test_canjear_sin_aprobacion_es_404():
    r = _postear(REMOTO, "/api/aparatos/canjear", {"id_pedido": _golpe()})
    assert r.status_code == 404, r.text


# --- listar y revocar: detras del guard -------------------------------------

def test_listar_exige_credencial():
    assert _pedir(REMOTO, "GET", "/api/aparatos").status_code == 401
    _golpe()
    r = _local().get("/api/aparatos")
    assert r.status_code == 200, r.text
    fila = r.json()["aparatos"][0]
    assert fila["aparato"] == "Lector de Pedro"
    assert fila["efectivo"] == "golpeando"


def test_los_tres_exentos_lo_son_solo_por_POST():
    """La exencion es por path exacto Y metodo: el POST sin credencial entra
    y un GET a la misma ruta sigue el camino normal del guard."""
    for ruta in ("/api/aparatos/golpear", "/api/aparatos/estado",
                 "/api/aparatos/canjear"):
        assert _postear(REMOTO, ruta).status_code != 401, ruta
        assert _pedir(REMOTO, "GET", ruta).status_code == 401, ruta


def test_revocar_desde_loopback_corta_la_sesion():
    id_pedido = _golpe()
    _local().post("/api/aparatos/aprobar",
                  json={"id_pedido": id_pedido, "tipo": "lector"})
    id_sesion = _postear(REMOTO, "/api/aparatos/canjear",
                         {"id_pedido": id_pedido}).cookies["calipso_sesion"]
    hash_id = sesiones.listar()[0]["hash_id"]
    r = _local().post(f"/api/aparatos/{hash_id}/revocar")
    assert r.status_code == 200, r.text
    assert sesiones.resolver(id_sesion) is None


def test_revocar_desde_remoto_sin_sesion_navegador_es_403():
    r = _postear(REMOTO, "/api/aparatos/deadbeef/revocar",
                 cookies={srv.COOKIE: srv.TOKEN})
    assert r.status_code == 403, r.text
