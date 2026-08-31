"""Las dos puertas que estaban abiertas para cualquiera con el token.

No son tests de una feature: son la prueba de que dos agujeros concretos
siguen cerrados. Si alguno se pone en verde despues de un cambio, el agujero
volvio.
"""
import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso.browser import UrlNoPermitida, exigir_url_publica


@pytest.fixture
def cliente():
    return TestClient(srv.app)


# --- la captura de pantalla como escaner de la red de Pedro ---------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/login",       # el propio Calipso, sin autenticar
    "http://localhost:8000",
    "http://[::1]:8000",
    "http://192.168.1.1",                # el router
    "http://10.0.0.5",
    "http://169.254.169.254/",           # metadatos de nube
])
def test_no_se_pueden_mirar_direcciones_internas(url):
    with pytest.raises(UrlNoPermitida):
        exigir_url_publica(url)


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://x/y", "/sin/esquema"])
def test_solo_http_y_https(url):
    with pytest.raises(UrlNoPermitida):
        exigir_url_publica(url)


def test_una_url_publica_pasa():
    assert exigir_url_publica("https://example.com") == "https://example.com"


def test_el_endpoint_traduce_el_rechazo_a_400(cliente):
    """400 y no 502: no fallo el sitio, es que no se va a mirar. Y el 502
    haria pensar que reintentar sirve."""
    r = cliente.get("/api/browser/screenshot",
                    params={"url": "http://127.0.0.1:8000/login",
                            "token": srv.TOKEN})
    assert r.status_code == 400
    assert "interna" in r.json()["detail"]


# --- pip install arbitrario ------------------------------------------------

def test_no_se_instala_un_paquete_arbitrario(cliente):
    """`deps.ensure_pip` corre `pip install <lo que venga>`. Con el token en
    la mano eso era ejecucion de codigo remota."""
    r = cliente.post("/api/deps/install", params={"token": srv.TOKEN},
                     json={"package": "cualquier-cosa"})
    assert r.status_code == 403


def test_el_catalogo_cerrado_sigue_andando(cliente):
    """Lo que si se puede instalar es lo que esta en deps.TOOLS. Una
    herramienta desconocida no revienta: contesta que no la conoce."""
    r = cliente.post("/api/deps/install", params={"token": srv.TOKEN},
                     json={"tool": "no-existe-esta-herramienta"})
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_sin_token_ninguna_de_las_dos(cliente):
    assert cliente.post("/api/deps/install",
                        json={"tool": "browser"}).status_code == 401
    assert cliente.get("/api/browser/screenshot",
                       params={"url": "https://example.com"}).status_code == 401


# --- el socket abierto a toda la wifi -------------------------------------
# El tercer agujero: `calipso/server.py` ataba el socket con un "0.0.0.0"
# escrito a mano, asi que Calipso escuchaba en toda la red local siempre.
# CALIPSO_HOST existia pero solo lo leia el lanzador para elegir que URL
# abrir en el navegador: no llegaba al bind. Con el token viajando en el
# query string, cualquiera en la misma wifi tenia la puerta enfrente.

def test_por_defecto_solo_escucha_en_esta_maquina(monkeypatch):
    monkeypatch.delenv("CALIPSO_HOST", raising=False)
    assert srv._host() == "127.0.0.1"


def test_se_puede_abrir_pero_hay_que_pedirlo(monkeypatch):
    """No se prohibe abrirlo: se prohibe que pase sin que nadie lo escriba."""
    monkeypatch.setenv("CALIPSO_HOST", "0.0.0.0")
    assert srv._host() == "0.0.0.0"


def test_el_bind_del_arranque_sale_de_host_y_no_de_una_constante():
    """El agujero no era el default: era que el default no se podia cambiar.
    Si alguien vuelve a escribir la direccion a mano en el __main__, esto
    se pone en rojo."""
    import pathlib
    fuente = pathlib.Path(srv.__file__).read_text(encoding="utf-8")
    arranque = fuente.split('if __name__ == "__main__":')[-1]
    assert "uvicorn.run(app, host=host" in arranque
    assert '"0.0.0.0"' not in arranque
