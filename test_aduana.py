"""La aduana en aislado (spec seccion 12): la forma de la linea, el fail-open,
el libro 0600, el loop, el recorte y el banco del saneo.

Es ademas el HARNESS que reusan test_aduana_enchufes.py, test_aduana_api.py y
test_aduana_canario.py: la fixture `libro` (el libro en tmp_path, el estado
de modulo limpio y la telemetria espiada), `quien_de_prueba(...)` y
`cruces_del_libro(ruta)`. Se pisa `aduana._ruta` en vez de CALIPSO_HOME
(criterio de test_sesiones.py): el temporal queda explicito en cada assert.
"""
from __future__ import annotations

import asyncio
import errno
import json
import os
import pathlib
import stat
import subprocess
import sys
import threading
import time

import pytest

from calipso import aduana


# --- el harness --------------------------------------------------------------

class EspiaTelemetria:
    """`telemetry.log_event` doblado: lo que la aduana avisa, en memoria."""

    def __init__(self) -> None:
        self.eventos: list[dict] = []

    def __call__(self, kind: str, **data) -> dict:
        e = {"kind": kind, **data}
        self.eventos.append(e)
        return e

    def de(self, kind: str) -> list[dict]:
        return [e for e in self.eventos if e["kind"] == kind]


class _Libro(pathlib.PosixPath):
    """La ruta del libro con la telemetria espiada colgada (`.telemetria`):
    un PosixPath pelado no admite atributos."""


@pytest.fixture
def libro(tmp_path, monkeypatch):
    """El libro en tmp_path, `SIN_LIBRO` y las banderas de `declarar_una_vez`
    limpios (son estado de modulo: sin reset un test hereda el n del
    anterior), y la telemetria espiada en `libro.telemetria`."""
    p = _Libro(tmp_path / "aduana.jsonl")
    monkeypatch.setattr(aduana, "_ruta", lambda: p)
    aduana._reset_para_tests()
    espia = EspiaTelemetria()
    monkeypatch.setattr(aduana.telemetry, "log_event", espia)
    p.telemetria = espia
    return p


def quien_de_prueba(**cambios) -> aduana.Quien:
    base = {"origen": "turno", "proyecto": "calipso", "chat": "chat_x",
            "gesto": "/web", "ruta": "local",
            "desde": {"credencial": "maquina"}}
    base.update(cambios)
    return aduana.Quien(**base)


def cruces_del_libro(ruta: pathlib.Path) -> list[dict]:
    if not ruta.exists():
        return []
    lineas = ruta.read_text(encoding="utf-8").split("\n")
    if lineas and lineas[-1] == "":
        lineas.pop()
    return [json.loads(l) for l in lineas]


# --- Quien ------------------------------------------------------------------

def test_un_quien_exige_origen_proyecto_y_desde():
    with pytest.raises(TypeError):
        aduana.Quien(origen="turno")                              # type: ignore[call-arg]
    with pytest.raises(ValueError):
        quien_de_prueba(origen="desconocido")
    with pytest.raises(ValueError):
        quien_de_prueba(desde={"credencial": "cookie"})
    with pytest.raises(ValueError):
        quien_de_prueba(ruta="nube")
    with pytest.raises(ValueError):
        quien_de_prueba(rutina={"kind": "reflect"})               # sin id
    q = quien_de_prueba(rutina={"kind": "reflect", "id": "rt_1"})
    with pytest.raises(Exception):
        q.origen = "gesto"                                        # type: ignore[misc]


def test_cruzar_sin_quien_no_pasa(libro):
    with pytest.raises(TypeError):
        with aduana.cruzar({"origen": "turno"}, "x", None):       # type: ignore[arg-type]
            pass
    assert cruces_del_libro(libro) == []


# --- la linea -----------------------------------------------------------------

def test_un_cruce_ok_escribe_una_linea_con_la_forma_del_spec(libro, monkeypatch):
    monkeypatch.setattr(aduana, "_ahora", lambda: "2026-09-10T15:04:05")
    q = quien_de_prueba()
    with aduana.cruzar(q, proposito="buscar en la web",
                       destino="https://html.duckduckgo.com/html/",
                       carga="precio del dolar hoy") as cruce:
        cruce.entro(48213)
    lineas = cruces_del_libro(libro)
    assert len(lineas) == 1
    c = lineas[0]
    assert c["ts"] == "2026-09-10T15:04:05"
    assert c["id"].startswith("cr_") and len(c["id"]) == 15
    assert c["quien"] == {"origen": "turno", "chat": "chat_x", "proyecto": "calipso",
                          "gesto": "/web", "ruta": "local", "rutina": None,
                          "departamento": None, "endpoint": None,
                          "desde": {"credencial": "maquina"}}
    assert c["proposito"] == "buscar en la web"
    assert c["destino"] == {"host": "html.duckduckgo.com",
                            "url": "https://html.duckduckgo.com/html/"}
    assert c["carga"] == {"tipo": "consulta", "texto": "precio del dolar hoy"}
    assert c["resultado"]["estado"] == "ok"
    assert c["resultado"]["bytes"] == 48213
    assert isinstance(c["resultado"]["ms"], int) and c["resultado"]["ms"] >= 0
    assert c["declarado"] is False
    assert libro.telemetria.eventos == []


def test_un_fallo_se_anota_y_la_excepcion_se_relanza_intacta(libro):
    class Rara(RuntimeError):
        pass
    with pytest.raises(Rara) as exc:
        with aduana.cruzar(quien_de_prueba(), "leer una pagina",
                           destino="https://ejemplo.com/x", carga=None):
            raise Rara("se cayo")
    assert str(exc.value) == "se cayo"
    c = cruces_del_libro(libro)[0]
    assert c["resultado"]["estado"] == "fallo"
    assert c["resultado"]["error"] == "Rara"
    assert c["resultado"]["bytes"] is None
    assert c["carga"] == {"tipo": "nada"}


def test_un_fallo_del_libro_no_reemplaza_la_excepcion_del_bloque(libro, monkeypatch):
    def bomba(linea):
        raise OSError(errno.ENOSPC, "sin espacio")
    monkeypatch.setattr(aduana, "_escribir", bomba)
    with pytest.raises(KeyError):
        with aduana.cruzar(quien_de_prueba(), "x", None):
            raise KeyError("la del bloque")
    assert aduana.sin_libro()["n"] == 1
    assert "ENOSPC" in aduana.sin_libro()["ultimo_error"] or "sin espacio" in aduana.sin_libro()["ultimo_error"]


def test_la_aduana_no_altera_el_valor_del_bloque(libro):
    with aduana.cruzar(quien_de_prueba(), "x", None) as cruce:
        valor = "lo que devolvio la red"
        cruce.entro(len(valor))
    assert valor == "lo que devolvio la red"
    assert cruces_del_libro(libro)[0]["resultado"]["bytes"] == 22


# --- la carga (spec seccion 5) -------------------------------------------------

def test_una_consulta_se_recorta_a_500(libro):
    # palabras y no "a" * 900: 900 caracteres hex seguidos son un secreto
    # para `_HEX`, y el saneo corre ANTES del recorte
    with aduana.cruzar(quien_de_prueba(), "x", None, carga="palabra " * 200):
        pass
    c = cruces_del_libro(libro)[0]["carga"]
    assert c["tipo"] == "consulta" and len(c["texto"]) == 500


def test_un_cuerpo_va_como_tamano_hash_y_tres_lineas(libro):
    texto = "titulo del PR\nlinea dos\nlinea tres\nlinea cuatro NO va\n" + "z" * 5000
    with aduana.cruzar(quien_de_prueba(), "abrir un PR", "api.github.com",
                       carga=aduana.Cuerpo(texto)):
        pass
    c = cruces_del_libro(libro)[0]["carga"]
    assert c["tipo"] == "cuerpo"
    assert c["tamano"] == len(texto.encode("utf-8"))
    assert len(c["sha256"]) == 12
    assert c["lineas"] == "titulo del PR\nlinea dos\nlinea tres"
    assert "cuatro" not in json.dumps(c) and "zzzz" not in json.dumps(c)


def test_tres_lineas_largas_se_recortan_a_200(libro):
    with aduana.cruzar(quien_de_prueba(), "x", None,
                       carga=aduana.Cuerpo("x" * 150 + "\n" + "y" * 150)):
        pass
    assert len(cruces_del_libro(libro)[0]["carga"]["lineas"]) == 200


def test_un_argv_va_unido_y_una_url_va_saneada(libro):
    with aduana.cruzar(quien_de_prueba(), "gh", "api.github.com",
                       carga=["gh", "pr", "list", "--limit", "10"]):
        pass
    with aduana.cruzar(quien_de_prueba(), "fetch", "https://x.com/a?b=1",
                       carga="https://x.com/a?b=1"):
        pass
    a, b = cruces_del_libro(libro)
    assert a["carga"]["texto"] == "gh pr list --limit 10"
    assert a["destino"] == {"host": "api.github.com", "url": None}
    assert b["carga"]["texto"] == "https://x.com/a?b=[SECRETO]"
    assert b["destino"]["url"] == "https://x.com/a?b=[SECRETO]"


# --- declarar ------------------------------------------------------------------

def test_declarar_escribe_una_linea_marcada_sin_resultado(libro):
    q = quien_de_prueba(origen="arranque", chat=None, gesto=None, ruta=None)
    aduana.declarar(q, proposito="modelo de embeddings",
                    destino="huggingface.co", motivo="all-MiniLM-L6-v2")
    c = cruces_del_libro(libro)[0]
    assert c["declarado"] is True
    assert c["resultado"] is None
    assert c["motivo"] == "all-MiniLM-L6-v2"
    assert c["destino"] == {"host": "huggingface.co", "url": None}
    assert c["carga"] == {"tipo": "nada"}


def test_declarar_una_vez_evalua_la_bandera_antes_del_candado(libro, monkeypatch):
    q = quien_de_prueba(origen="arranque")
    assert aduana.declarar_una_vez("memoria", q, "modelo de embeddings",
                                   "huggingface.co") is True
    # la segunda vez el candado NO se toca: una bomba en `candado` lo prueba
    def bomba(*a, **k):
        raise AssertionError("el candado no debe tomarse en un no-op")
    monkeypatch.setattr(aduana, "candado", bomba)
    assert aduana.declarar_una_vez("memoria", q, "modelo de embeddings",
                                   "huggingface.co") is False
    assert len(cruces_del_libro(libro)) == 1


# --- fail-open (invariante 3) ------------------------------------------------

def test_candado_tomado_por_otro_proceso_es_fail_open_con_aviso(libro):
    lock = str(libro) + ".lock"
    sostener = ("import fcntl,sys\n"
                "f=open(sys.argv[1],'a')\n"
                "fcntl.flock(f.fileno(), fcntl.LOCK_EX)\n"
                "print('HOLDING', flush=True)\n"
                "sys.stdin.readline()\n")
    proc = subprocess.Popen([sys.executable, "-c", sostener, lock],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True)
    assert proc.stdout.readline().strip() == "HOLDING"
    try:
        with aduana.cruzar(quien_de_prueba(), "x", None) as cruce:
            cruce.entro(1)      # el cruce SIGUE
    finally:
        proc.stdin.write("\n")
        proc.stdin.flush()
        proc.wait(timeout=10)
    assert not libro.exists() or cruces_del_libro(libro) == []
    hueco = aduana.sin_libro()
    assert hueco["n"] == 1 and hueco["desde"] and "ErrorCandado" in hueco["ultimo_error"]
    avisos = libro.telemetria.de("aduana_sin_libro")
    assert len(avisos) == 1 and avisos[0]["n"] == 1
    assert "destino" not in avisos[0] and "carga" not in avisos[0]
    # y despues de la contencion, el libro vuelve a escribirse
    with aduana.cruzar(quien_de_prueba(), "y", None):
        pass
    assert [c["proposito"] for c in cruces_del_libro(libro)] == ["y"]


def test_n_hilos_escribiendo_a_la_vez_dejan_n_lineas_sin_hueco(libro, monkeypatch):
    """El candado no bloqueante con 3 x 50 ms es para el flock AJENO (otro
    proceso: fail-hang), pero `candado(no_bloquear=True)` tambien levanta
    ErrorCandado al instante si OTRO HILO del proceso tiene el RLock: con un
    disco lento y dos cruces del threadpool a la vez, el segundo se perdia
    (sin_libro). Un Lock de modulo serializa `_escribir` entre hilos ANTES
    del candado (una escritura son microsegundos: esperar entre hilos no
    cuelga nada); el no bloqueante queda solo para el proceso ajeno."""
    original = aduana._append

    def lento(ruta, linea):
        time.sleep(0.2)             # mas que los 3 x 50 ms del reintento
        original(ruta, linea)
    monkeypatch.setattr(aduana, "_append", lento)
    n = 4
    barrera = threading.Barrier(n)

    def cruce(i):
        barrera.wait()
        with aduana.cruzar(quien_de_prueba(), f"hilo {i}", None):
            pass
    hilos = [threading.Thread(target=cruce, args=(i,)) for i in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert sorted(c["proposito"] for c in cruces_del_libro(libro)) == [
        f"hilo {i}" for i in range(n)]
    assert aduana.sin_libro()["n"] == 0
    assert libro.telemetria.de("aduana_sin_libro") == []


def test_declarar_una_vez_desde_n_hilos_declara_una_sola(libro):
    """La bandera de `declarar_una_vez` se evalua y se marca bajo el mismo
    Lock entre hilos (los contadores sin lock, parkeados, los cubre este)."""
    n = 6
    barrera = threading.Barrier(n)
    resultados: list[bool] = []

    def una_vez():
        barrera.wait()
        resultados.append(aduana.declarar_una_vez(
            "memoria", quien_de_prueba(origen="arranque"), "modelo", "huggingface.co"))
    hilos = [threading.Thread(target=una_vez) for _ in range(n)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    assert resultados.count(True) == 1 and len(cruces_del_libro(libro)) == 1


def test_enospc_simulado_es_fail_open_con_aviso(libro, monkeypatch):
    def bomba(ruta, linea):
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(aduana, "_append", bomba)
    with aduana.cruzar(quien_de_prueba(), "x", None):
        pass
    with aduana.cruzar(quien_de_prueba(), "y", None):
        pass
    assert aduana.sin_libro()["n"] == 2
    assert "No space left" in aduana.sin_libro()["ultimo_error"]
    assert [e["n"] for e in libro.telemetria.de("aduana_sin_libro")] == [1, 2]


@pytest.mark.skipif(os.geteuid() == 0, reason="root escribe igual")
def test_sin_permisos_es_fail_open_con_aviso(libro, tmp_path, monkeypatch):
    cerrado = tmp_path / "cerrado"
    cerrado.mkdir()
    cerrado.chmod(0o500)
    monkeypatch.setattr(aduana, "_ruta", lambda: cerrado / "aduana.jsonl")
    try:
        with aduana.cruzar(quien_de_prueba(), "x", None):
            pass
    finally:
        cerrado.chmod(0o700)
    assert aduana.sin_libro()["n"] == 1
    assert "PermissionError" in aduana.sin_libro()["ultimo_error"]


def test_desde_el_loop_no_toma_el_candado_y_avisa(libro, monkeypatch):
    def bomba(*a, **k):
        raise AssertionError("el candado no se toma en el loop")
    monkeypatch.setattr(aduana, "candado", bomba)

    async def en_el_loop():
        with aduana.cruzar(quien_de_prueba(), "x", None):
            pass
        aduana.declarar(quien_de_prueba(origen="arranque"), "y", None)
    asyncio.run(en_el_loop())
    assert not libro.exists()
    assert aduana.sin_libro()["n"] == 2
    assert aduana.sin_libro()["ultimo_error"] == "aduana_en_loop"
    assert len(libro.telemetria.de("aduana_en_loop")) == 2
    assert libro.telemetria.de("aduana_sin_libro") == []


def test_en_un_hilo_del_loop_si_escribe(libro):
    async def en_hilo():
        def cruce():
            with aduana.cruzar(quien_de_prueba(), "x", None):
                pass
        await asyncio.to_thread(cruce)
    asyncio.run(en_hilo())
    assert len(cruces_del_libro(libro)) == 1


# --- el archivo ---------------------------------------------------------------

def test_el_libro_nace_0600_con_umask_022(libro):
    viejo = os.umask(0o022)
    try:
        with aduana.cruzar(quien_de_prueba(), "x", None):
            pass
    finally:
        os.umask(viejo)
    assert stat.S_IMODE(os.stat(libro).st_mode) == 0o600


def test_un_libro_que_existia_0644_se_endurece(libro):
    libro.write_text('{"ts": "2026-01-01T00:00:00", "quien": {}}\n', encoding="utf-8")
    libro.chmod(0o644)
    with aduana.cruzar(quien_de_prueba(), "x", None):
        pass
    assert stat.S_IMODE(os.stat(libro).st_mode) == 0o600
    assert len(cruces_del_libro(libro)) == 2      # append, nunca reemplazo


def test_la_ruta_se_resuelve_en_cada_escritura(tmp_path, monkeypatch):
    aduana._reset_para_tests()
    monkeypatch.setattr(aduana.telemetry, "log_event", EspiaTelemetria())
    uno, otro = tmp_path / "uno", tmp_path / "otro"
    monkeypatch.setenv("CALIPSO_HOME", str(uno))
    with aduana.cruzar(quien_de_prueba(), "x", None):
        pass
    monkeypatch.setenv("CALIPSO_HOME", str(otro))
    with aduana.cruzar(quien_de_prueba(), "y", None):
        pass
    assert [c["proposito"] for c in cruces_del_libro(uno / "aduana.jsonl")] == ["x"]
    assert [c["proposito"] for c in cruces_del_libro(otro / "aduana.jsonl")] == ["y"]


def test_el_modulo_no_congela_el_home_al_importar():
    assert not isinstance(getattr(aduana, "CALIPSO_HOME", None), pathlib.Path)


# --- el banco del saneo (invariante 9) ---------------------------------------

@pytest.mark.parametrize("url", [
    "https://github.com/pedro-cmyks/Observatory-Global/pull/12",
    "https://www.lanacion.com.ar/economia/dolar-hoy-2026-09-10-nid10092026/",
    "https://docs.google.com/document/d/1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcd/edit",
    "https://html.duckduckgo.com/html/",
])
def test_falsos_positivos_quedan_intactos(url):
    assert aduana.sanear_url(url) == url


def test_un_argv_con_sha_queda_intacto():
    argv = ["git", "fetch", "origin", "3f2a9c1e4b7d6a5f8e9c0b1a2d3e4f5a6b7c8d9e"]
    assert aduana._carga(argv)["texto"] == " ".join(argv)


@pytest.mark.parametrize("url,esperado", [
    ("https://user:pass@host.com/x", "https://[SECRETO]@host.com/x"),
    ("https://host.com/x?token=deadbeefdeadbeefdeadbeefdeadbeef&q=hola",
     "https://host.com/x?token=[SECRETO]&q=[SECRETO]"),
    ("https://host.com/x?vacio=&q=1", "https://host.com/x?vacio=&q=[SECRETO]"),
    ("https://host.com/x#access_token=abc&type=bearer",
     "https://host.com/x#access_token=[SECRETO]&type=[SECRETO]"),
    ("https://host.com/x#readme", "https://host.com/x#[SECRETO]"),
    # `_PREFIJOS` admite `/` en la cola del token: se lleva el resto del path
    ("https://host.com/ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123/x",
     "https://host.com/[SECRETO]"),
    ("https://host.com/eyJhbGciOi.eyJzdWIiOiIx.SflKxwRJSMeKKF2",
     "https://host.com/[SECRETO]"),
])
def test_positivos_tapados_en_la_url(url, esperado):
    assert aduana.sanear_url(url) == esperado


def test_un_argv_de_gh_tapa_solo_lo_lexico():
    argv = ["gh", "auth", "login", "--with-token", "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"]
    assert aduana._carga(argv)["texto"] == "gh auth login --with-token [SECRETO]"
    conn = ["git", "clone", "https://pedro:s3cr3t@github.com/x/y.git"]
    assert "[SECRETO]" in aduana._carga(conn)["texto"] and "s3cr3t" not in aduana._carga(conn)["texto"]


def test_una_consulta_de_pedro_pasa_por_el_detector_completo():
    c = aduana._carga("mira este token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV")
    assert c["texto"] == "mira este token [SECRETO]"
    c = aduana._carga("precio del dolar hoy")
    assert c["texto"] == "precio del dolar hoy"


def test_las_tres_lineas_de_un_cuerpo_pasan_por_el_detector(libro):
    with aduana.cruzar(quien_de_prueba(), "pr", "api.github.com",
                       carga=aduana.Cuerpo("fix\n-----BEGIN RSA PRIVATE KEY----- abc\nfin")):
        pass
    lineas = cruces_del_libro(libro)[0]["carga"]["lineas"]
    assert "PRIVATE KEY" not in lineas and "[SECRETO]" in lineas


# --- lo que urlsplit no puede parsear (fail-open del saneo) --------------------

def test_una_url_malformada_no_frena_el_cruce_y_va_tapada(libro):
    """`urlsplit("http://[::1/x")` levanta ValueError ('Invalid IPv6 URL').
    La aduana no frena (invariante 2): el bloque corre y la linea se escribe;
    la URL que no se pudo sanear no se anota cruda (invariante 9)."""
    corrio = False
    with aduana.cruzar(quien_de_prueba(), "x", "http://[::1/x?pwd=abc") as cruce:
        corrio = True
        cruce.entro(1)
    assert corrio
    lineas = cruces_del_libro(libro)
    assert len(lineas) == 1
    assert lineas[0]["destino"] == {"host": None, "url": "[SECRETO]"}
    assert lineas[0]["resultado"]["estado"] == "ok"
    assert aduana.sin_libro()["n"] == 0
    assert "abc" not in json.dumps(lineas[0])


def test_sanear_url_malformada_devuelve_secreto():
    assert aduana.sanear_url("http://[::1/x") == "[SECRETO]"
    assert aduana.sanear_url("//[::1/x?pwd=abc") == "[SECRETO]"


def test_una_carga_str_malformada_no_se_anota_cruda(libro):
    with aduana.cruzar(quien_de_prueba(), "x", None, carga="http://[::1/x?pwd=abc"):
        pass
    assert cruces_del_libro(libro)[0]["carga"] == {"tipo": "consulta",
                                                   "texto": "[SECRETO]"}


def test_una_frase_de_pedro_con_una_url_adentro_sigue_por_el_detector_completo():
    """Decision 2 del plan: solo un str que PARSEA como URL http(s) va por
    `sanear_url`; una frase de Pedro que menciona una URL es una consulta y
    va por el detector completo (spec 9.3), no se tapa entera."""
    texto = "mira https://x.com/?q=hola que raro"
    assert aduana._carga(texto)["texto"] == texto


# --- el lector ----------------------------------------------------------------

def test_leer_devuelve_hoy_con_totales_y_cuenta_las_lineas_rotas(libro, monkeypatch):
    relojes = iter(["2026-09-09T23:59:59", "2026-09-10T10:00:00",
                    "2026-09-10T11:00:00", "2026-09-10T12:00:00"])
    monkeypatch.setattr(aduana, "_ahora", lambda: next(relojes))
    with aduana.cruzar(quien_de_prueba(), "ayer", "https://a.com/"):
        pass
    with aduana.cruzar(quien_de_prueba(), "web", "https://a.com/", carga="q"):
        pass
    with aduana.cruzar(quien_de_prueba(origen="ui", endpoint="/api/updates",
                                       chat=None, gesto=None, ruta=None),
                       "npm", "https://registry.npmjs.org/x"):
        pass
    aduana.declarar(quien_de_prueba(origen="arranque",
                                    desde={"credencial": "sesion", "tipo": "navegador",
                                           "aparato": "cel", "hash": "abcd1234"}),
                    "modelo", "huggingface.co")
    with open(libro, "a", encoding="utf-8") as f:
        f.write("{esto no es json\n")
    monkeypatch.setattr(aduana, "_hoy", lambda: "2026-09-10")
    r = aduana.leer()
    assert [c["proposito"] for c in r["cruces"]] == ["web", "npm", "modelo"]
    assert r["ilegibles"] == 1
    assert r["totales"]["por_origen"] == {"turno": 1, "ui": 1, "arranque": 1}
    assert r["totales"]["por_destino"] == {"a.com": 1, "registry.npmjs.org": 1,
                                           "huggingface.co": 1}
    assert r["totales"]["por_proyecto"] == {"calipso": 3}
    assert r["totales"]["por_desde"] == {"maquina": 2, "sesion:navegador": 1}
    assert r["totales"]["declarados"] == 1
    assert r["sin_libro"] == {"n": 0, "desde": None, "ultimo_error": None}
    # filtros
    assert [c["proposito"] for c in aduana.leer(origen="ui")["cruces"]] == ["npm"]
    assert [c["proposito"] for c in
            aduana.leer(desde="2026-09-09", hasta="2026-09-10T10:30:00")["cruces"]] == ["ayer", "web"]


def test_recortar_para_tablero_saca_carga_chat_y_url(libro):
    with aduana.cruzar(quien_de_prueba(), "web", "https://a.com/p?x=1", carga="secreto humano"):
        pass
    r = aduana.recortar_para_tablero(aduana.leer())
    c = r["cruces"][0]
    assert "carga" not in c
    assert "chat" not in c["quien"] and c["quien"]["origen"] == "turno"
    assert c["destino"] == {"host": "a.com"}
    assert c["proposito"] == "web" and c["resultado"]["estado"] == "ok"
    assert "secreto humano" not in json.dumps(r)
    assert r["totales"]["por_origen"] == {"turno": 1}
