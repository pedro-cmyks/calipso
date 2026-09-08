"""Tests del endpoint del mapa (patron TestClient + cookie del repo)."""
import json
import re
import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso.economia import departamentos as deps
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.mapa import urbanismo as urb


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("mercado", deps.ZONA_FABRICA))
    r.alta(deps.Departamento("curiosos", deps.ZONA_FABRICA))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    k.acunar("2026-08-25T09:00:00", "2026-W35", "dep:mercado", 50_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_ciudad_responde_con_coordenadas(cliente):
    """Coordenadas de verdad: no alcanza con que sean enteros. Un urbanismo
    borrado devuelve todo en el origen y eso tiene que fallar aca."""
    r = cliente.get("/api/mapa/ciudad")
    assert r.status_code == 200
    body = r.json()
    assert body["activa"] is True
    modelo = body["ciudad"]
    edis = {e["id"]: e for e in modelo["edificios"]}
    assert edis["dep:mercado"]["saldo_mm"] == 50_000
    assert edis["dep:mercado"]["tamano"] == 3
    puntos = [(e["x"], e["y"]) for e in edis.values()]
    assert all(isinstance(x, int) and isinstance(y, int) for x, y in puntos)
    assert len(set(puntos)) == len(puntos)   # nadie encimado
    assert sum(1 for p in puntos if p == (0, 0)) == 1  # solo el ancla
    # y son EXACTAMENTE las que da el urbanismo sobre este mismo modelo
    esperadas = urb.urbanizar(modelo["edificios"], modelo["calles"])
    assert {e["id"]: (e["x"], e["y"]) for e in modelo["edificios"]} == esperadas


def test_el_endpoint_entrega_los_campos_que_el_cliente_gasta(cliente):
    """Spec 7: la tarjeta del edificio muestra saldo, gasto del ciclo,
    ventas de la ventana y eficiencia."""
    edis = {e["id"]: e for e in
            cliente.get("/api/mapa/ciudad").json()["ciudad"]["edificios"]}
    m = edis["dep:mercado"]
    assert m["gasto_ciclo_mm"] == 0 and m["ventas_ventana_mm"] == 0
    # el endpoint SI alcanza el estado de suscripciones: no va en None
    assert m["eficiencia_pormil"] == 0


def test_ciudad_es_estable_entre_llamadas(cliente):
    """Invariante 2: el mapa no se mueve solo entre dos requests."""
    uno = cliente.get("/api/mapa/ciudad").json()
    dos = cliente.get("/api/mapa/ciudad").json()
    assert uno["ciudad"]["edificios"] == dos["ciudad"]["edificios"]
    # ... y lo que se compara no es una lista de ceros
    puntos = {(e["x"], e["y"]) for e in uno["ciudad"]["edificios"]}
    assert len(puntos) == len(uno["ciudad"]["edificios"]) > 1


def test_sin_economia_responde_inactiva(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / "vacio")
    c = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})
    assert c.get("/api/mapa/ciudad").json() == {"activa": False}


def test_sin_auth_rechaza(cliente):
    c = TestClient(srv.app)
    assert c.get("/api/mapa/ciudad",
                 follow_redirects=False).status_code in (302, 401, 403)


def test_fabrica_sirve_la_app(cliente):
    r = cliente.get("/fabrica")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "/static/fabrica/app.js" in r.text


def test_los_modulos_del_cliente_se_sirven(cliente):
    for modulo in ("app.js", "camara.js", "ciudad.js", "mapa.js",
                   "sprites.js", "paleta.js"):
        r = cliente.get(f"/static/fabrica/{modulo}")
        assert r.status_code == 200, modulo
        assert "javascript" in r.headers["content-type"], modulo


def test_el_manifest_de_la_fabrica_arranca_en_la_fabrica(cliente):
    r = cliente.get("/fabrica/manifest.json")
    assert r.status_code == 200
    m = r.json()
    # el manifest global arranca en "/" y abriria la UI vieja
    assert m["start_url"] == "/fabrica"


def test_fabrica_sin_auth_manda_al_login(cliente):
    # /fabrica no es /api ni /ws: el middleware redirige en vez de dar 401
    c = TestClient(srv.app)
    r = c.get("/fabrica", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def shell_del_service_worker() -> list[str]:
    """Las URLs que el service worker precachea."""
    import re
    sw = (srv.WEB / "sw.js").read_text(encoding="utf-8")
    urls = re.findall(r'"(/[^"]*)"', sw.split("const SHELL")[1].split("];")[0])
    assert urls, "no se pudo leer el SHELL del service worker"
    return urls


def test_todo_el_shell_del_service_worker_existe(cliente):
    """cache.addAll rechaza el lote entero si una URL da 404, y el service
    worker se lo traga con un catch. Que falle aca en vez de en silencio."""
    for url in shell_del_service_worker():
        assert cliente.get(url).status_code == 200, url


def test_el_shell_no_se_olvida_de_ningun_archivo_de_la_fabrica():
    """Que todas las URLs del SHELL existan no dice nada de las que faltan.
    Un modulo afuera del SHELL no rompe nada online y deja la fabrica
    inservible sin conexion, que es justamente para lo que esta el SHELL.
    La lista se saca de los archivos REALES del directorio."""
    fabrica = srv.WEB / "fabrica"
    esperados = {f"/static/fabrica/{p.name}"
                 for p in sorted(fabrica.iterdir())
                 if (p.suffix == ".css"
                     or (p.suffix == ".js" and not p.name.endswith(".test.js")))}
    assert esperados, f"no se encontro ningun modulo en {fabrica}"
    faltan = esperados - set(shell_del_service_worker())
    assert not faltan, (
        "estos archivos de la fabrica no estan en el SHELL de "
        f"calipso/web/sw.js: {sorted(faltan)}")


def test_la_fabrica_registra_el_service_worker_y_su_manifest():
    """Sin el registro, toda la parte de PWA de la fabrica es inerte; con el
    manifest global, el icono de la pantalla de inicio abre la UI vieja."""
    html = (srv.WEB / "fabrica" / "index.html").read_text(encoding="utf-8")
    assert "serviceWorker" in html and "/sw.js" in html, (
        "index.html de la fabrica no registra el service worker")
    assert 'rel="manifest"' in html and "/fabrica/manifest.json" in html, (
        "index.html de la fabrica no enlaza el manifest de la fabrica")


def test_la_mesa_y_el_plantel_tienen_su_div_en_el_html():
    """app.js hace document.getElementById("mesa") y ("plantel"); sin el div
    en el HTML, cajaMesa y cajaPlantel quedan null, las guardas de app.js
    hacen que pintarMesa/pintarPlantel nunca escriban nada, y la mesa entera
    desaparece con todos los tests de mesa.js y de plantel.js en verde
    igual -- porque ninguno de esos tests toca el HTML real."""
    html = (srv.WEB / "fabrica" / "index.html").read_text(encoding="utf-8")
    assert 'id="mesa"' in html, "index.html de la fabrica no tiene #mesa"
    assert 'id="plantel"' in html, "index.html de la fabrica no tiene #plantel"


def test_cada_badge_de_la_submesa_cuelga_de_su_propia_sub_pestana():
    """Un badge dice "hay algo esperandote ACA". Prendido al lado de una
    bandeja que no lo contiene miente: Pedro abre esa, la encuentra vacia y
    lo que esperaba se vence mientras busca donde no es (un golpe de aparato
    dura GOLPE_TTL_MIN = 10 minutos). Ningun test de JS puede ver esto -- el
    DOM de mentira de arranque.test.js no sabe DONDE vive cada span-, asi que
    la correspondencia se fija aca: el badge #badge-X vive adentro del boton
    data-vista="X" y cuenta esa bandeja."""
    html = (srv.WEB / "fabrica" / "index.html").read_text(encoding="utf-8")
    nav = re.search(r'<nav id="submesa">(.*?)</nav>', html, re.S)
    assert nav, "index.html de la fabrica no tiene la nav #submesa"
    badges_por_vista = {}
    for boton in nav.group(1).split("<button")[1:]:
        vista = re.search(r'data-vista="([^"]+)"', boton)
        assert vista, f"un boton de #submesa no declara data-vista: {boton}"
        badges_por_vista[vista.group(1)] = re.findall(r'id="badge-([^"]+)"',
                                                      boton)
    for vista, badges in badges_por_vista.items():
        assert badges in ([], [vista]), (
            f'el boton data-vista="{vista}" de #submesa lleva los badges '
            f"{badges}: un badge cuenta la bandeja del boton donde vive")
    for vista in ("permisos", "aparatos"):
        assert badges_por_vista.get(vista) == [vista], (
            f'la sub-pestana "{vista}" no tiene badge propio: lo que espera '
            "respuesta ahi quedaria contado al lado de otra bandeja")
