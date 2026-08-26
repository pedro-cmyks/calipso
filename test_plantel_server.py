"""Los endpoints del interruptor y la rutina del departamento."""
import json
import threading

import dispatch
import pytest
from fastapi.testclient import TestClient

import calipso.routines as routines
import calipso.server as srv
from calipso.economia import departamentos as eco_deps
from calipso.economia import tipos as eco_tipos
from calipso.economia.candado import candado as candado_real
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.plantel import interruptor as it


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    return TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})


def test_el_tablero_del_plantel_arranca_en_ensayo(cliente):
    d = cliente.get("/api/plantel").json()
    assert d["encendido"] is True and d["modo"] == "ensayo"


def test_parar_y_reanudar_por_http(cliente, tmp_path):
    assert cliente.post("/api/plantel/parar").json()["encendido"] is False
    assert it.leer(tmp_path).encendido is False
    assert cliente.post("/api/plantel/reanudar").json()["encendido"] is True


def test_poner_el_modo_por_http(cliente, tmp_path):
    assert cliente.put("/api/plantel/modo", json={"modo": "vivo"}).json()["modo"] == "vivo"
    assert it.leer(tmp_path).modo == "vivo"


def test_un_modo_inventado_se_rechaza_con_400(cliente, tmp_path):
    """El endpoint es la superficie por la que se suelta a la fabrica a
    gastar: no puede aceptar cualquier cosa.

    La asercion mira el archivo crudo, no `it.leer`: `leer` normaliza
    cualquier modo desconocido a "ensayo", asi que pasaria igual aunque
    `poner_modo` hubiera llegado a escribir "turbo" en disco."""
    assert cliente.put("/api/plantel/modo", json={"modo": "turbo"}).status_code == 400
    ruta = it.ruta(tmp_path)
    crudo = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    assert crudo.get("modo") != "turbo"


def test_sin_auth_no_se_puede_parar_ni_soltar(tmp_path, monkeypatch):
    """Si el auth_guard alguna vez se rompe, este test no puede terminar
    escribiendo en el ~/.calipso real y parando la fabrica de Pedro."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    c = TestClient(srv.app)
    assert c.post("/api/plantel/parar", follow_redirects=False).status_code in (401, 403, 302)


def test_pensar_local_no_corre_claude_por_subscripcion(monkeypatch):
    """La trampa cara del brief: decidir por el escalon barato no puede
    terminar ejecutando `claude -p`, que gastaria una unidad de suscripcion
    por tic y por departamento. `_pensar_local` tiene que pegarle a Ollama
    y nunca abrir un subproceso.

    Y la trampa gemela, al reves: `CONFIG["local"]` y `CONFIG["classifier"]`
    comparten `base_url` (mismo Ollama), asi que afirmar solo la URL no
    distinguiria una entrada de la otra -- el modelo tiene que quedar
    afirmado tambien, o este test pasaria igual si `_pensar_local` volviera
    a pegarle al 3b del clasificador."""
    llamadas = []

    def falso_post(url, payload, headers=None):
        llamadas.append((url, payload.get("model")))
        return {"response": "nada -- sin plata"}

    def spia_subprocess(*args, **kwargs):
        raise AssertionError("_pensar_local no puede correr un subproceso")

    monkeypatch.setattr(dispatch, "_http_post_json", falso_post)
    monkeypatch.setattr(srv.subprocess, "run", spia_subprocess)

    resultado = srv._pensar_local("hola")

    cfg = dispatch.CONFIG["local"]
    assert llamadas == [(cfg["base_url"], cfg["model"])]
    assert cfg["model"] != dispatch.CONFIG["classifier"]["model"]
    assert resultado == "nada -- sin plata"


def test_la_rutina_de_departamento_es_un_kind_valido():
    assert "departamento" in routines.KINDS


def test_la_rutina_guarda_a_que_departamento_pertenece(tmp_path, monkeypatch):
    """El ticker le pasa la rutina al handler: si no lleva la cuenta, el
    handler no sabe a quien despertar."""
    monkeypatch.setattr(routines, "CALIPSO_HOME", tmp_path)
    r = routines.add("departamento", "atlas", 60, cuenta="dep:atlas")
    assert r["cuenta"] == "dep:atlas"
    assert routines.get(r["id"])["cuenta"] == "dep:atlas"


def test_las_rutinas_viejas_sin_cuenta_no_revientan(tmp_path, monkeypatch):
    """El archivo de rutinas de Pedro ya existe y sus entradas NO tienen el
    campo. Usar `add` no probaria eso, porque `add` siempre lo escribe: hay
    que escribir el archivo a mano, como quedo en disco antes del cambio."""
    import json
    monkeypatch.setattr(routines, "CALIPSO_HOME", tmp_path)
    (tmp_path / "routines.json").write_text(json.dumps([
        {"id": "rt_viejo", "kind": "reflect", "label": "reflexionar",
         "interval_minutes": 1440, "enabled": False,
         "last_run": None, "last_status": None}]), encoding="utf-8")
    viejas = routines.load()
    assert viejas and viejas[0].get("cuenta") is None
    assert routines.get("rt_viejo")["kind"] == "reflect"


# --------------------------------------------------------------------------
# C1 (revision amplia de la rama): el candado del libro en _departamento
# --------------------------------------------------------------------------

def _armar_economia(base):
    """Una economia minima en `base/economia`: un asiento (acunacion), el
    registro con dep:atlas, y suscripciones vacias. Devuelve la ruta del
    libro."""
    eco = base / "economia"
    eco.mkdir(parents=True, exist_ok=True)
    ruta_libro = eco / "libro.jsonl"
    k = Kernel(Libro(ruta_libro))
    k.acunar("2026-08-01T09:00:00", "2026-W31", eco_tipos.TESORO, 1_000_000,
             eco_tipos.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    r = eco_deps.Registro(eco / "departamentos.json")
    r.alta(eco_deps.Departamento("atlas", eco_deps.ZONA_FABRICA))
    (eco / "suscripciones.json").write_text("{}", encoding="utf-8")
    return ruta_libro


class _ScopeFalso:
    def load_core(self):
        return ""

    def remember(self, *a, **k):
        pass


class _MemFalsa:
    def departamento(self, _nombre):
        return _ScopeFalso()


class _JefeFalso:
    """Reemplaza a calipso.plantel.jefe para estos tests: lo unico bajo
    prueba es la lectura del mercado bajo candado, que pasa ANTES de que
    `_departamento` arme el Contexto. `tic` no necesita decidir nada de
    verdad."""

    @staticmethod
    def Contexto(**kwargs):
        return kwargs

    @staticmethod
    def tic(ctx, cuenta, semana):
        return {"accion": "nada"}


def test_el_tic_no_pierde_un_asiento_escrito_a_medias(tmp_path, monkeypatch):
    """C1 (critico): `_departamento` llamaba a `mercado_fresco()` -que
    reconstruye Libro leyendo el archivo entero- SIN el candado del libro:
    el unico de los siete call sites de economia en server.py que lo hacia.
    `Libro._cargar` repara una ultima linea que no parsea TRUNCANDO el
    archivo, asi que un tic que lee mientras otro proceso (dispatch, el
    chat) esta a mitad de un append real puede comerse ese asiento, para
    siempre. El arreglo serializa la lectura con el mismo candado que usan
    los otros seis call sites, y lo suelta ANTES de pensar.

    Sin sleeps: dos threading.Event fuerzan que el escritor este
    DEMOSTRABLEMENTE a mitad de un append (candado tomado, linea partida en
    el archivo) antes de que el lector arranque, y el test verifica que el
    lector queda BLOQUEADO hasta que el escritor termina y suelta el
    candado -- si no bloqueara, leeria la linea partida y la perderia."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setattr(srv, "mem", _MemFalsa())
    monkeypatch.setattr(srv, "_plantel_jefe", _JefeFalso())

    ruta_libro = _armar_economia(tmp_path)

    # el segundo asiento, tal como lo escribiria Libro.append -- partido en
    # dos escrituras para simular un append real interrumpido a mitad de
    # camino (el mismo estado que "con un append a medias" del hallazgo)
    segundo = eco_tipos.Asiento(
        seq=2, ts="2026-08-01T09:05:00", semana="2026-W31",
        tipo=eco_tipos.TipoAsiento.ACUNACION, divisa=eco_tipos.Divisa.MONEDA,
        monto=500, destino=eco_tipos.TESORO,
        subtipo=eco_tipos.SubtipoAcunacion.CAPITAL.value,
        detalle={"evidencia": {"tipo": "firma_pedro"}})
    linea = segundo.a_json() + "\n"
    mitad = len(linea) // 2

    escribio_mitad = threading.Event()
    puede_terminar = threading.Event()

    def escritor():
        # sostiene el MISMO candado que usan los siete call sites de
        # economia -- exactamente lo que dispatch o el chat hacen de verdad
        with candado_real(ruta_libro):
            with ruta_libro.open("a", encoding="utf-8") as f:
                f.write(linea[:mitad])
                f.flush()
            escribio_mitad.set()
            puede_terminar.wait(timeout=5)
            with ruta_libro.open("a", encoding="utf-8") as f:
                f.write(linea[mitad:])
                f.flush()

    hilo_escritor = threading.Thread(target=escritor)
    hilo_escritor.start()
    assert escribio_mitad.wait(timeout=5), "el escritor no arranco a tiempo"

    resultado = {}

    def lector():
        handlers = srv._routine_handlers()
        handlers["departamento"]({"cuenta": "dep:atlas"})
        resultado["asientos"] = Libro(ruta_libro).asientos()

    hilo_lector = threading.Thread(target=lector)
    hilo_lector.start()

    # con el fix, el lector tiene que quedar bloqueado en el candado: el
    # escritor todavia no solto. Si esto NO bloqueara (el bug original), el
    # lector ya habria terminado -y truncado la linea partida- para cuando
    # llega este join.
    hilo_lector.join(timeout=1)
    assert hilo_lector.is_alive(), (
        "el lector no espero al candado del escritor: leyo (y pudo haber "
        "truncado) el libro mientras el append todavia estaba a mitad de "
        "camino")

    puede_terminar.set()
    hilo_escritor.join(timeout=5)
    hilo_lector.join(timeout=5)

    assert not hilo_lector.is_alive(), "el lector nunca termino"
    assert len(resultado["asientos"]) == 2, (
        "el asiento escrito a medias se perdio: el lector no espero a que "
        "el escritor completara su append")
    assert ruta_libro.read_text(encoding="utf-8").count("\n") == 2, (
        "el archivo quedo truncado")


def test_contratar_escribe_el_alta_bajo_candado(tmp_path, monkeypatch):
    """C1: `bus.alta` es una ESCRITURA; tiene que tomar el mismo candado que
    las demas escrituras de economia, con un Bus construido de nuevo
    adentro -no cachear un escritor entre adquisiciones es la regla del
    modulo candado."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    _armar_economia(tmp_path)

    candado_activo = []
    candado_original = srv._eco_candado

    import contextlib as _ctxlib

    @_ctxlib.contextmanager
    def candado_espia(ruta, no_bloquear=False):
        with candado_original(ruta, no_bloquear=no_bloquear):
            candado_activo.append(True)
            try:
                yield
            finally:
                candado_activo.pop()

    altas = []

    class _BusEspia:
        def __init__(self, ruta):
            self.ruta = ruta

        def alta(self, *args, **kwargs):
            assert candado_activo, "bus.alta corrio SIN el candado"
            altas.append((args, kwargs))

    class _EcoBusFalso:
        Bus = _BusEspia

    monkeypatch.setattr(srv, "_eco_candado", candado_espia)
    monkeypatch.setattr(srv, "_eco_bus", _EcoBusFalso())

    pagador = srv._EcoPagador.desde_entorno(tmp_path)
    contratar = srv._contratar_para("dep:atlas", pagador,
                                    "2026-08-01T09:10:00", "2026-W31")
    situacion = {"nombre": "atlas", "presupuesto_semanal_mm": 1000,
                "agresividad_pct": 100, "salidas_semana_mm": 0}
    resultado = contratar(situacion, "proponer", None, "hay hueco")

    assert altas, "bus.alta nunca se llamo"
    assert resultado["accion"] == "proponer"
