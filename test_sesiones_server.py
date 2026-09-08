#!/usr/bin/env python3
"""
test_sesiones_server.py — El alta de aparatos y el guard que resuelve
sesiones (spec de la capa de sesion, seccion 3 "El guard" puntos 1-6 y
"Alta, revocacion y corte"; invariantes 1, 2, 3, 4, 6 y 8).

Lo que se prueba aca no es el almacen (eso es test_sesiones.py) sino la
COSTURA: quien entra sin credencial, quien no entra ni con ella, con que
alcance entra el que entra, y que el freno del alta no comparta un solo
contador con el del login. El canario de esa separacion (martillar `golpear`
y ver que `/login` sigue contestando 401) existe porque compartir el balde le
regalaria a un martillador anonimo la palanca para dejar a Pedro afuera de su
propio TOTP.

El host remoto se simula con `httpx.ASGITransport(client=(ip, puerto))`: el
`TestClient` de Starlette dice "testclient" por default, que `_es_loopback`
acepta, asi que sin eso no se puede escribir un test de "desde afuera". Los
websockets van por el otro camino -`websocket_connect` no es un request de
httpx-: ahi el host remoto se pone en `TestClient(..., client=(ip, puerto))`.
"""
import asyncio
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import calipso.server as srv
from calipso import sesiones
from calipso.mapa import pulso

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
def _generaciones_limpias():
    """El registro del corte en vivo es estado de modulo, como los contadores
    del freno: un hash revocado en un test no puede llegar al siguiente."""
    srv._ws_generaciones.clear()
    yield
    srv._ws_generaciones.clear()


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


def _login(ip: str, code: str) -> httpx.Response:
    """El POST de /login va en formulario, no en JSON: `login_submit` parsea
    el body crudo con `parse_qs`."""
    transporte = httpx.ASGITransport(app=srv.app, client=(ip, 4321))

    async def _ir():
        async with httpx.AsyncClient(transport=transporte,
                                     base_url="http://calipso") as c:
            return await c.post("/login", data={"code": code})

    return asyncio.run(_ir())


def _local() -> TestClient:
    """Loopback CON el token. Sigue entrando porque el token vale desde la
    propia maquina (invariante 2): lo que perdio es el viaje remoto."""
    return TestClient(app=srv.app, cookies={srv.COOKIE: srv.TOKEN})


def _sesion(tipo: str, aparato: str = "Aparato de prueba") -> str:
    """El id en claro de una sesion viva de ese tipo, sin pasar por el alta:
    lo que se prueba con el es el guard, no el ciclo de vida."""
    return sesiones.crear_viva(aparato, tipo)


def _hash_de(aparato: str) -> str:
    return next(s["hash_id"] for s in sesiones.listar()
                if s["aparato"] == aparato)


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

def test_aprobar_desde_una_sesion_navegador_remota_es_403():
    """Ninguna sesion consagra jamas a otra. La credencial de este test era
    la cookie-token desde un host remoto; esa ya muere en el guard (401), asi
    que la unica que llega hasta el endpoint es la sesion mas poderosa que
    hay -- `navegador`, que pasa el alcance con "*" -- y ahi la frena el
    invariante 4."""
    id_pedido = _golpe()
    r = _postear(REMOTO, "/api/aparatos/aprobar",
                 {"id_pedido": id_pedido, "tipo": "navegador"},
                 cookies={srv.COOKIE_SESION: _sesion("navegador")})
    assert r.status_code == 403, r.text
    assert r.json() == {"detail": "aprobar es solo desde la Ally"}
    assert sesiones.estado(id_pedido) == "golpeando"


def test_rechazar_desde_una_sesion_navegador_remota_es_403():
    id_pedido = _golpe()
    r = _postear(REMOTO, "/api/aparatos/rechazar", {"id_pedido": id_pedido},
                 cookies={srv.COOKIE_SESION: _sesion("navegador")})
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


def test_una_sesion_tablero_no_ve_la_lista_de_aparatos():
    """El GET que consume la sub-pestana "Aparatos" de /fabrica: lo ven
    loopback y una sesion `navegador`, no un `tablero`. Es lo que hace que la
    UI, ante un 403, tenga que decir "solo desde la Ally o desde un
    navegador" en vez de dibujar una lista vacia -- que se leeria como
    "ningun aparato entro", que es otra cosa."""
    _golpe()
    r = _pedir(REMOTO, "GET", "/api/aparatos",
               cookies={srv.COOKIE_SESION: _sesion("tablero")})
    assert r.status_code == 403, r.text
    assert r.json() == {"detail": "fuera del alcance del aparato"}


def test_una_aprobacion_sin_canjear_figura_viva_y_sin_hash():
    """La forma exacta que /fabrica muestra como "aprobado, esperando al
    aparato": el hash nace en el CANJE, asi que entre el si de Pedro y la
    primera entrada del aparato no hay con que revocar. Sin este contrato la
    lista dibujaria un boton de revocar que solo puede dar 404."""
    id_pedido = _golpe()
    assert _local().post("/api/aparatos/aprobar",
                         json={"id_pedido": id_pedido,
                               "tipo": "lector"}).status_code == 200
    fila = _local().get("/api/aparatos").json()["aparatos"][0]
    assert fila["efectivo"] == "viva"
    assert fila["hash_id"] is None


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


def test_revocar_desde_una_sesion_lector_es_403():
    """Este test mandaba la cookie-token desde un host remoto y esperaba el
    403 de `revocar`; esa cookie ya no llega (401 en el guard). Quien puede
    intentarlo ahora es una sesion, y el `lector` muere antes, en el alcance:
    revocar no figura en su tabla."""
    r = _postear(REMOTO, "/api/aparatos/deadbeef/revocar",
                 cookies={srv.COOKIE_SESION: _sesion("lector")})
    assert r.status_code == 403, r.text
    assert r.json() == {"detail": "fuera del alcance del aparato"}


def test_revocar_desde_una_sesion_navegador_remota_corta_la_otra():
    """El caso que `request.state.sesion` existe para servir (D3: revocar
    desde otro dispositivo). Y de paso: el guard puebla ese estado."""
    id_lector = _sesion("lector", aparato="Musnap robado")
    r = _postear(REMOTO, f"/api/aparatos/{_hash_de('Musnap robado')}/revocar",
                 cookies={srv.COOKIE_SESION: _sesion("navegador",
                                                     aparato="Celular")})
    assert r.status_code == 200, r.text
    assert sesiones.resolver(id_lector) is None


# --- el guard: el alcance manda (invariante 3) ------------------------------

def test_una_sesion_tablero_no_toca_los_archivos_de_la_maquina():
    """El canario del tablero: ve todo y firma la mesa, pero /api/file es la
    maquina de Pedro. Fail-closed, no una lista de vedadas."""
    r = _pedir(REMOTO, "GET", "/api/file?path=README.md",
               cookies={srv.COOKIE_SESION: _sesion("tablero")})
    assert r.status_code == 403, r.text
    assert r.json() == {"detail": "fuera del alcance del aparato"}


def test_una_sesion_tablero_si_ve_el_tablero_de_economia():
    """La otra mitad del alcance: si nada pasara, el 403 no probaria nada.
    Lo que se mide es el guard, no lo que conteste economia."""
    r = _pedir(REMOTO, "GET", "/api/economia/tablero",
               cookies={srv.COOKIE_SESION: _sesion("tablero")})
    assert r.status_code not in (401, 403), r.text


def test_una_sesion_lector_no_entra_a_fabrica():
    """El alcance aplica a TODA ruta, no solo a /api: /fabrica es html y el
    403 sale igual (invariante 3)."""
    r = _pedir(REMOTO, "GET", "/fabrica",
               cookies={srv.COOKIE_SESION: _sesion("lector")})
    assert r.status_code == 403, r.text
    assert r.json() == {"detail": "fuera del alcance del aparato"}


def test_una_cookie_de_sesion_muerta_no_es_credencial():
    id_sesion = _sesion("navegador")
    sesiones.revocar(_hash_de("Aparato de prueba"))
    r = _pedir(REMOTO, "GET", "/api/aparatos",
               cookies={srv.COOKIE_SESION: id_sesion})
    assert r.status_code == 401, r.text


# --- el guard: el token es solo-loopback (invariantes 1 y 2) ----------------

def test_la_cookie_token_remota_es_401_y_ademas_sale_vencida():
    """El canario del punto 4 del guard. Las cookies-token viejas viven un
    anio en los navegadores remotos que ya entraron: el 401 tiene que
    limpiarlas, no solo rechazarlas."""
    r = _pedir(REMOTO, "GET", "/api/tree", cookies={srv.COOKIE: srv.TOKEN})
    assert r.status_code == 401, r.text
    assert r.json() == {"detail": "no autorizado"}
    galleta = r.headers["set-cookie"]
    assert galleta.startswith('calipso_token=""')   # vaciada
    assert "Max-Age=0" in galleta                   # y vencida
    # el mismo path con que se planto: una borrada en otro path deja viva la
    # que se queria limpiar y el navegador se queda con las dos
    assert "Path=/" in galleta


def test_la_cookie_token_remota_tambien_muere_en_una_ruta_html():
    r = _pedir(REMOTO, "GET", "/", cookies={srv.COOKIE: srv.TOKEN})
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/login"
    assert "Max-Age=0" in r.headers["set-cookie"]


def test_el_token_por_url_remoto_no_expira_ninguna_cookie():
    """Sin oraculo: quien tira un `?token=` a ver si pega no se lleva ni una
    señal distinta de la del token invalido."""
    r = _pedir(REMOTO, "GET", f"/api/tree?token={srv.TOKEN}")
    assert r.status_code == 401, r.text
    assert "set-cookie" not in r.headers


def test_la_cookie_token_sigue_entrando_desde_loopback():
    """La Ally y el shell Tauri quedan intactos: el punto 4 acota el ORIGEN,
    no la credencial."""
    r = _pedir("127.0.0.1", "GET", "/api/tree",
               cookies={srv.COOKIE: srv.TOKEN})
    assert r.status_code == 200, r.text
    assert "set-cookie" not in r.headers


def _token_vencido(resp: httpx.Response) -> bool:
    """La cookie del token, vaciada y con Max-Age=0, en el Set-Cookie."""
    return any(g.startswith('calipso_token=""') and "Max-Age=0" in g
               and "Path=/" in g
               for g in resp.headers.get_list("set-cookie"))


def test_la_cookie_token_remota_muere_tambien_con_una_sesion_viva():
    """La poblacion que el punto 4 queria limpiar es justamente esta: el
    navegador remoto que YA tenia la cookie-token de un anio y que despues
    entra por /login. Si la sesion gana el guard y nadie mira la otra cookie,
    ese navegador sigue mandando el TOKEN por la LAN hasta 2027."""
    r = _pedir(REMOTO, "GET", "/api/tree",
               cookies={srv.COOKIE_SESION: _sesion("navegador"),
                        srv.COOKIE: srv.TOKEN})
    assert r.status_code == 200, r.text
    assert _token_vencido(r), r.headers.get_list("set-cookie")


def test_la_cookie_token_remota_muere_tambien_en_el_403_del_alcance():
    """El aparato fuera de alcance rebota, pero el token que traia colgando
    tampoco tiene por que seguir viajando."""
    r = _pedir(REMOTO, "GET", "/api/tree",
               cookies={srv.COOKIE_SESION: _sesion("lector"),
                        srv.COOKIE: srv.TOKEN})
    assert r.status_code == 403, r.text
    assert r.json() == {"detail": "fuera del alcance del aparato"}
    assert _token_vencido(r), r.headers.get_list("set-cookie")


def test_una_sesion_desde_loopback_no_le_toca_la_cookie_token():
    """El canario del ORIGEN: la limpieza es para el token que salio a la
    red. Un navegador de la propia maquina con las dos cookies no puede
    perder la del token por haber usado una sesion."""
    r = _pedir("127.0.0.1", "GET", "/api/tree",
               cookies={srv.COOKIE_SESION: _sesion("navegador"),
                        srv.COOKIE: srv.TOKEN})
    assert r.status_code == 200, r.text
    assert "set-cookie" not in r.headers


# --- el guard: /login remoto crea sesion, no reparte el token ---------------

def test_el_login_remoto_deja_sesion_y_no_planta_el_token(monkeypatch):
    """La excepcion explicita del invariante 4: el TOTP es Pedro en persona.
    Lo que NO puede pasar es que se lleve el token (invariante 1)."""
    monkeypatch.setattr(srv, "_TOTP_DISABLED", False)
    monkeypatch.setattr(srv, "_verify_totp", lambda code: True)
    r = _login(REMOTO, "123456")
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/"
    galletas = r.headers.get_list("set-cookie")
    assert not any(g.startswith("calipso_token=") for g in galletas)
    (sesion,) = [g for g in galletas if g.startswith("calipso_sesion=")]
    assert "HttpOnly" in sesion
    assert "SameSite=lax" in sesion
    assert "Max-Age=2592000" in sesion
    id_sesion = r.cookies["calipso_sesion"]
    assert sesiones.resolver(id_sesion)["tipo"] == "navegador"
    assert [s["aparato"] for s in sesiones.listar()] == [f"navegador {REMOTO}"]


def test_el_login_local_sigue_plantando_el_token(monkeypatch):
    monkeypatch.setattr(srv, "_TOTP_DISABLED", False)
    monkeypatch.setattr(srv, "_verify_totp", lambda code: True)
    r = _login("127.0.0.1", "123456")
    assert r.status_code == 303, r.text
    galletas = r.headers.get_list("set-cookie")
    assert any(g.startswith("calipso_token=") for g in galletas)
    assert not any(g.startswith("calipso_sesion=") for g in galletas)
    # y no estaciona un aparato por cada login de la propia maquina
    assert sesiones.listar() == []


def test_el_login_remoto_fallido_no_crea_nada(monkeypatch):
    monkeypatch.setattr(srv, "_TOTP_DISABLED", True)   # el bypass es loopback
    monkeypatch.setattr(srv, "_verify_totp", lambda code: False)
    assert _login(REMOTO, "000000").status_code == 401
    assert sesiones.listar() == []


def test_el_login_no_da_a_luz_el_secreto_totp(tmp_path, monkeypatch):
    """El secreto nace SOLO en la ventana del punto 1 (/setup?token= desde
    loopback). Antes, `_verify_totp` llamaba a `_get_totp_secret`, que lo
    GENERA si falta: cualquier POST /login con seis digitos -de un remoto
    anonimo, de un flatpak, de otro uid- escribia el secreto sin que nadie
    viera el QR, la condicion "no existe totp_secret" dejaba de cumplirse y
    /setup?token= le mostraba a Pedro "ya esta configurado". Enrolamiento
    brickeado hasta borrar el archivo a mano.

    Sin parchear `_verify_totp`: lo que se prueba es justamente lo que hace
    con el archivo ausente."""
    monkeypatch.setattr(srv, "_TOTP_DISABLED", False)
    secreto = tmp_path / "totp_secret"
    monkeypatch.setattr(srv, "_TOTP_SECRET_FILE", secreto)
    assert _login(REMOTO, "123456").status_code == 401
    assert not secreto.exists(), "un remoto anonimo creo el secreto TOTP"
    # loopback tampoco: no es Pedro (flatpaks, otros uid)
    assert _login("127.0.0.1", "123456").status_code == 401
    assert not secreto.exists(), "un login local sin secreto lo creo"
    # y la ventana del primer arranque sigue abierta para Pedro
    r = _pedir("127.0.0.1", "GET", f"/setup?token={srv.TOKEN}")
    assert r.status_code == 200, r.text
    assert "otpauth://" in r.text
    assert secreto.exists()


# --- el guard: /setup endurecido (punto 1) ---------------------------------

def test_setup_sin_token_redirige_aunque_no_haya_totp_secret(tmp_path,
                                                             monkeypatch):
    """La ventana del primer arranque: loopback NO es Pedro (flatpaks, otros
    uid). Sin token no se ve el QR aunque el secreto todavia no exista."""
    monkeypatch.setattr(srv, "_TOTP_SECRET_FILE", tmp_path / "totp_secret")
    r = _pedir("127.0.0.1", "GET", "/setup")
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/login"
    assert not (tmp_path / "totp_secret").exists()


def test_setup_con_token_desde_loopback_muestra_el_qr(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_TOTP_SECRET_FILE", tmp_path / "totp_secret")
    r = _pedir("127.0.0.1", "GET", f"/setup?token={srv.TOKEN}")
    assert r.status_code == 200, r.text
    assert "otpauth://" in r.text
    # la exencion es una ventana, no un login: no planta la cookie del token
    assert "set-cookie" not in r.headers


def test_setup_con_token_desde_afuera_no_regala_el_secreto(tmp_path,
                                                           monkeypatch):
    monkeypatch.setattr(srv, "_TOTP_SECRET_FILE", tmp_path / "totp_secret")
    r = _pedir(REMOTO, "GET", f"/setup?token={srv.TOKEN}")
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/login"
    assert not (tmp_path / "totp_secret").exists()


def test_setup_con_sesion_navegador_remota_no_regala_el_secreto(tmp_path,
                                                                monkeypatch):
    """El alcance `*` del navegador NO es una llave del segundo factor.
    Servir /setup con el secreto ausente es crearlo y mostrarlo en claro, y
    ese enrolamiento no se revoca: la sesion muere (invariante 9) y el
    aparato sigue entrando por /login para siempre sin pasar por la Ally
    (invariante 4). Mientras el secreto no exista, la ventana del punto 1 es
    la UNICA puerta de /setup."""
    monkeypatch.setattr(srv, "_TOTP_SECRET_FILE", tmp_path / "totp_secret")
    r = _pedir(REMOTO, "GET", "/setup",
               cookies={srv.COOKIE_SESION: _sesion("navegador")})
    assert r.status_code == 303, r.text
    assert r.headers["location"] == "/login"
    assert "otpauth://" not in r.text
    assert not (tmp_path / "totp_secret").exists()


def test_setup_con_el_secreto_escrito_sigue_abierto_a_la_sesion(tmp_path,
                                                                monkeypatch):
    """La otra mitad: cerrada la ventana, la regla no le quita nada a nadie.
    La pantalla de despues no muestra ni el QR ni el secreto, asi que el
    navegador remoto la ve como cualquier otra ruta de su alcance."""
    secreto = tmp_path / "totp_secret"
    secreto.write_text("JBSWY3DPEHPK3PXP", encoding="utf-8")
    monkeypatch.setattr(srv, "_TOTP_SECRET_FILE", secreto)
    r = _pedir(REMOTO, "GET", "/setup",
               cookies={srv.COOKIE_SESION: _sesion("navegador")})
    assert r.status_code == 200, r.text
    assert "otpauth://" not in r.text
    assert "JBSWY3DPEHPK3PXP" not in r.text


def test_el_checklist_no_ofrece_abrir_setup_mientras_falte_el_secreto(
        tmp_path, monkeypatch):
    """El unico boton que el server le ofrecia a Pedro para enrolar el
    autenticador apuntaba a `/setup` a secas, que desde la rama exige
    `?token=` en la query (punto 1 del guard): el clic desde la Ally, con la
    cookie-token, daba 303 a /login. El detail ya decia el camino correcto;
    el boton lo contradecia. Mientras el secreto falte, el item es una
    instruccion y no un enlace."""
    monkeypatch.setattr(srv, "_TOTP_SECRET_FILE", tmp_path / "totp_secret")
    r = _local().get("/api/launch/checklist")
    assert r.status_code == 200, r.text
    item = next(i for i in r.json()["items"] if i["key"] == "totp")
    assert item["ok"] is False
    assert item["action"] == "", item
    assert "/setup?token=" in item["detail"]
    # y lo que ese boton habria hecho, para que conste: la cookie-token sola
    # no abre /setup mientras falte el secreto
    r = _local().get("/setup", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
    # con el secreto escrito el item cierra solo
    (tmp_path / "totp_secret").write_text("JBSWY3DPEHPK3PXP", encoding="utf-8")
    item = next(i for i in _local().get("/api/launch/checklist").json()["items"]
                if i["key"] == "totp")
    assert item["ok"] is True


# --- el guard: la cookie de sesion que se usa no caduca ---------------------

def test_la_sesion_usada_a_diario_renueva_su_cookie(monkeypatch):
    """Sin esto, un aparato que entra todos los dias perderia la cookie a los
    30 dias con la sesion todavia viva. La histeresis de una hora es la que
    evita un Set-Cookie por request."""
    galletas = {srv.COOKIE_SESION: _sesion("navegador")}
    r = _pedir(REMOTO, "GET", "/api/aparatos", cookies=galletas)
    assert r.status_code == 200, r.text
    assert "set-cookie" not in r.headers      # dentro de la histeresis

    despues = time.time() + sesiones.RENOVACION_HISTERESIS_S + 60
    monkeypatch.setattr(sesiones, "_reloj", lambda: despues)
    r = _pedir(REMOTO, "GET", "/api/aparatos", cookies=galletas)
    assert r.status_code == 200, r.text
    galleta = r.headers["set-cookie"]
    assert galleta.startswith(f"calipso_sesion={galletas[srv.COOKIE_SESION]}")
    assert "HttpOnly" in galleta
    assert "SameSite=lax" in galleta
    assert "Max-Age=2592000" in galleta


def test_una_sesion_sin_tipo_en_el_disco_no_abre_nada():
    """La cadena fail-closed llega hasta el guard: `sesiones.json` es un
    archivo que se puede editar a mano, y un registro al que le falte el
    `tipo` tiene que dar 403, no un 500."""
    id_sesion = _sesion("navegador")
    ruta = sesiones._ruta()
    crudo = ruta.read_text(encoding="utf-8")
    mutilado = crudo.replace('"tipo": "navegador"', '"tipo": null')
    assert mutilado != crudo, "cambio el formato del almacen: revisar el test"
    # la cache del almacen se invalida sola con el stat del archivo
    ruta.write_text(mutilado, encoding="utf-8")
    r = _pedir(REMOTO, "GET", "/api/aparatos",
               cookies={srv.COOKIE_SESION: id_sesion})
    assert r.status_code == 403, r.text
    assert r.json() == {"detail": "fuera del alcance del aparato"}


# --- el guard: los websockets (punto 6, invariante 2) -----------------------

def _ws(ip: str, cookies: dict) -> TestClient:
    """Un cliente de websocket con host propio. `websocket_connect` no viaja
    por `httpx.ASGITransport` -no es un request http-, asi que el `client=`
    del TestClient es el unico lugar donde se le puede poner un host remoto a
    un handshake."""
    return TestClient(srv.app, client=(ip, 4321), cookies=cookies)


def _rebota(c: TestClient, ruta: str) -> None:
    """El handshake muere con 1008 antes de aceptar: el cierre llega en el
    `__enter__`, no en el primer receive."""
    with pytest.raises(WebSocketDisconnect) as caida:
        with c.websocket_connect(ruta):
            pass
    assert caida.value.code == 1008


def _entra(c: TestClient, ruta: str) -> None:
    with c.websocket_connect(ruta):
        pass


def test_el_ws_del_chat_con_la_cookie_token_remota_se_cierra():
    """EL canario del invariante 2. Los ws no pasan por `auth_guard`, asi que
    hasta esta tarea la cookie del token abria el chat desde cualquier host:
    el guard http ya la rechazaba de afuera y el handshake no."""
    _rebota(_ws(REMOTO, {srv.COOKIE: srv.TOKEN}), "/ws/chat")


def test_un_ws_sin_ninguna_credencial_se_cierra():
    """El piso, y desde loopback para que no lo sostenga el host: la maquina
    de Pedro no es una credencial (aca corren flatpaks y otros uid), el token
    si."""
    c = _ws("127.0.0.1", {})
    _rebota(c, "/ws/chat")
    _rebota(c, "/ws/mapa")


def test_el_ws_del_mapa_con_la_cookie_token_remota_se_cierra():
    _rebota(_ws(REMOTO, {srv.COOKIE: srv.TOKEN}), "/ws/mapa")


def test_los_ws_con_el_token_desde_loopback_siguen_entrando():
    """La otra mitad del invariante 2: la Ally no perdio nada."""
    c = _ws("127.0.0.1", {srv.COOKIE: srv.TOKEN})
    _entra(c, "/ws/chat")
    _entra(c, "/ws/mapa")


def test_una_sesion_navegador_remota_entra_a_los_dos_ws():
    """Lo que hacia incoherente a la fase 1 sin esta tarea: la PWA entra por
    /login con TOTP, recibe su sesion... y se quedaba sin chat."""
    c = _ws(REMOTO, {srv.COOKIE_SESION: _sesion("navegador")})
    _entra(c, "/ws/chat")
    _entra(c, "/ws/mapa")


def test_una_sesion_tablero_entra_al_mapa_y_no_al_chat():
    """Quien decide es la tabla de alcances, no el handshake: el `tablero`
    tiene `/ws/mapa` con GET y nada mas."""
    c = _ws(REMOTO, {srv.COOKIE_SESION: _sesion("tablero")})
    _entra(c, "/ws/mapa")
    _rebota(c, "/ws/chat")


def test_una_sesion_lector_no_abre_ningun_ws():
    c = _ws(REMOTO, {srv.COOKIE_SESION: _sesion("lector")})
    _rebota(c, "/ws/chat")
    _rebota(c, "/ws/mapa")


def test_una_sesion_revocada_no_abre_un_ws_nuevo():
    """Cortar los ws que YA estaban vivos es otra tarea (el corte por
    generaciones); lo que esto sostiene es que la sesion muerta no abre uno."""
    c = _ws(REMOTO, {srv.COOKIE_SESION: _sesion("navegador")})
    sesiones.revocar(_hash_de("Aparato de prueba"))
    _rebota(c, "/ws/chat")
    _rebota(c, "/ws/mapa")


# --- el corte en vivo de los ws (spec seccion 3, "Corte de WS vivos") -------

def _cierre_del_ws(ws, plazo: float = 5.0) -> int:
    """El codigo con el que el SERVIDOR cerro el socket, esperando `plazo`
    como mucho.

    En un hilo aparte porque `receive_json` del TestClient no acepta timeout:
    si el corte no llega, un test que tiene que fallar colgaria la suite
    entera en vez de fallar."""
    caidas: list[BaseException] = []

    def _leer() -> None:
        try:
            ws.receive_json()
        except BaseException as exc:      # se re-mira afuera del hilo
            caidas.append(exc)

    hilo = threading.Thread(target=_leer, daemon=True)
    hilo.start()
    hilo.join(plazo)
    assert caidas, f"el ws seguia abierto {plazo} s despues de la revocacion"
    assert isinstance(caidas[0], WebSocketDisconnect), repr(caidas[0])
    return caidas[0].code


def test_revocar_corta_el_ws_del_chat_aunque_este_ocioso(monkeypatch):
    """El agujero que quedaba abierto: revocar frenaba los handshakes NUEVOS
    y el socket que ya estaba adentro seguia hablando. Ocioso es el caso
    dificil -- nadie escribe, asi que el corte solo puede venir del latido.

    Revoca por la ruta http de verdad: lo que se prueba aca es que el hook
    este enganchado al endpoint, no que el registro sepa contar."""
    monkeypatch.setattr(srv, "LATIDO_CHAT_S", 0.05)
    c = _ws(REMOTO, {srv.COOKIE_SESION: _sesion("navegador")})
    hash_id = _hash_de("Aparato de prueba")
    with c.websocket_connect("/ws/chat") as ws:
        assert _local().post(
            f"/api/aparatos/{hash_id}/revocar").status_code == 200
        assert _cierre_del_ws(ws) == 1008


def test_revocar_corta_el_ws_del_mapa_en_el_proximo_tick(monkeypatch):
    """El mapa no tiene tarea receptora ni latido con timeout: su chequeo va
    en el tick, que ya corre cada cuarto de segundo."""
    monkeypatch.setattr(srv, "EL_PULSO", pulso.Pulso())
    c = _ws(REMOTO, {srv.COOKIE_SESION: _sesion("tablero")})
    hash_id = _hash_de("Aparato de prueba")
    with c.websocket_connect("/ws/mapa") as ws:
        srv._revocar_en_vivo(hash_id)
        assert _cierre_del_ws(ws) == 1008


def test_el_socket_vigilado_no_deja_pasar_una_emision_de_una_revocada():
    """El proxy es lo que cubre los 46 puntos de emision de `ws_chat` sin
    tocar ninguno: los helpers, el `Emisor` y el borrador que corre suelto
    reciben el socket envuelto y quedan vigilados sin enterarse."""
    class _Falso:
        """Un socket de mentira, no un mock: registra lo que salio."""

        def __init__(self):
            self.enviado = []
            self.cerrado_con = None
            self.cookies = {"marca": "pasa de largo"}

        async def send_json(self, dato):
            self.enviado.append(dato)

        async def close(self, code=1000):
            self.cerrado_con = code

    crudo = _Falso()
    vigilado = srv._SocketVigilado(crudo, "hash-de-prueba")
    asyncio.run(vigilado.send_json({"type": "a tiempo"}))
    assert vigilado.cookies == {"marca": "pasa de largo"}

    srv._revocar_en_vivo("hash-de-prueba")
    with pytest.raises(WebSocketDisconnect) as caida:
        asyncio.run(vigilado.send_json({"type": "tarde"}))
    assert caida.value.code == 1008
    assert crudo.enviado == [{"type": "a tiempo"}]
    assert crudo.cerrado_con == 1008


def test_una_revocacion_no_toca_el_ws_abierto_con_el_token(monkeypatch):
    """La otra mitad: el corte es por sesion, no un interruptor general. La
    Ally entra con el token de la maquina y no tiene sesion que revocar, asi
    que su socket no se envuelve y ninguna revocacion lo alcanza."""
    monkeypatch.setattr(srv, "EL_PULSO", pulso.Pulso())
    _sesion("navegador", aparato="Celular revocado")
    c = _ws("127.0.0.1", {srv.COOKIE: srv.TOKEN})
    with c.websocket_connect("/ws/mapa") as ws:
        srv._revocar_en_vivo(_hash_de("Celular revocado"))
        srv.EL_PULSO.publicar("a1", "inicio", departamento="dep:atlas")
        assert ws.receive_json()["evento"] == "inicio"
