"""Los endpoints del interruptor y la rutina del departamento."""
import json
import threading

import dispatch
import pytest
from fastapi.testclient import TestClient

import calipso.routines as routines
import calipso.server as srv
from calipso import memory
from calipso.economia import departamentos as eco_deps
from calipso.economia import tipos as eco_tipos
from calipso.economia.candado import candado as candado_real
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.plantel import ficha as _ficha
from calipso.plantel import interruptor as it
from calipso.plantel import jefe as _jefe


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


def test_el_modelo_local_recibe_un_contexto_explicito(monkeypatch):
    """Ollama trunca desde el COMIENZO del prompt cuando no entra, y
    `decision.prompt` pone lo mas importante primero. Sin `num_ctx` fijo,
    el jefe puede dejar de ver su carta sin que nada avise -- y la medicion
    de la Tarea 6 no podria distinguir "el modelo la ignoro" de "nunca le
    llego"."""
    visto = {}

    def post_espia(url, cuerpo):
        visto.update(cuerpo)
        return {"response": "nada\nno hay nada"}

    monkeypatch.setattr(dispatch, "_http_post_json", post_espia)
    srv._pensar_local("un prompt cualquiera")
    assert visto["options"]["num_ctx"] == 8192
    assert visto["options"]["temperature"] == 0


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

def _armar_economia(base, **perillas):
    """Una economia minima en `base/economia`: un asiento (acunacion), el
    registro con dep:atlas, y suscripciones vacias. Devuelve la ruta del
    libro.

    Las perillas van al REGISTRO y no solo al dict de situacion porque el
    contratista relee las dos de pre-seed adentro del candado, contra el
    registro fresco: la perilla de hoy es la que autoriza, no la que
    estaba cuando el tic empezo a pensar (mismo criterio que
    `bus.financiar`).
    """
    eco = base / "economia"
    eco.mkdir(parents=True, exist_ok=True)
    ruta_libro = eco / "libro.jsonl"
    k = Kernel(Libro(ruta_libro))
    k.acunar("2026-08-01T09:00:00", "2026-W31", eco_tipos.TESORO, 1_000_000,
             eco_tipos.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    r = eco_deps.Registro(eco / "departamentos.json")
    r.alta(eco_deps.Departamento("atlas", eco_deps.ZONA_FABRICA, **perillas))
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


def test_produccion_le_inyecta_la_carta_y_los_proyectos_al_jefe(
        tmp_path, monkeypatch):
    """El arnes de test_plantel_jefe.py construye el Contexto a mano, asi
    que puede pasar aunque produccion nunca las mande. Este es el guarda
    apuntado al unico lugar que importa.

    `catastro.cargar()` va con stub a proposito: sin uno, el home
    desechable de este test arranca sin `catastro.json`, y `cargar()` cae
    siempre en `escanear()` -- que recorre el home REAL de Pedro con
    subprocesos git y despues escribe. Este test no necesita ejercitar el
    catastro real, solo que la lista que sea que devuelva `cargar()` llegue
    al `Contexto`.

    El `assert` de mas abajo compara contra el valor EXACTO que devuelve el
    stub, no solo `isinstance(..., list)`: ese chequeo mas debil pasaba
    igual si `server.py` dejara de pasar `proyectos=catastro.cargar()`,
    porque `Contexto.proyectos` tiene `default_factory=list` y llegaria
    `[]` -- una lista vacia tambien es una lista. Comparar contra el valor
    fijo del stub es lo que hace que este test pruebe la mitad del nombre
    que dice "y los proyectos", no solo la de la carta."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setattr(memory, "CALIPSO_HOME", tmp_path)
    carta = memory.ruta_carta("atlas")
    carta.parent.mkdir(parents=True, exist_ok=True)
    carta.write_text("SOY ATLAS", encoding="utf-8")
    monkeypatch.setattr(srv.catastro, "cargar",
                        lambda *a, **k: [{"nombre": "atlas"}])

    _armar_economia(tmp_path)

    visto = {}
    monkeypatch.setattr(srv._plantel_jefe, "tic",
                        lambda ctx, cuenta, semana: visto.update(ctx=ctx))
    # disparar la rutina de departamento por el mismo camino que la corre el
    # ticker; el mismo que ejercita
    # test_el_tic_no_pierde_un_asiento_escrito_a_medias, de aca arriba.
    handlers = srv._routine_handlers()
    handlers["departamento"]({"cuenta": "dep:atlas"})

    assert visto["ctx"].carta["texto"] == "SOY ATLAS"
    assert visto["ctx"].proyectos == [{"nombre": "atlas"}]


# Una ficha real, compartida por todos los tests de `proponer` de aca en
# mas: produccion ya no escribe nada en el bus sin ella, asi que hasta los
# tests que no miran `forma` ni `titulo` (los de candado, techo y billetera)
# tienen que pasarla para seguir ejercitando el camino que dicen ejercitar.
FICHA = {"sobre": "el radar de precios", "clave": "precios+radar",
         "promete": "descartar", "tarda": "corto", "porque": "no rindio"}


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

        def ids(self):
            # el contratista relee el techo de propuestas adentro del
            # candado (la segunda linea contra la carrera de dos tics
            # simultaneos): un bus vacio no frena nada
            return []

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
    resultado = contratar(situacion, "proponer", None, "hay hueco",
                          ficha=FICHA)

    assert altas, "bus.alta nunca se llamo"
    assert resultado["accion"] == "proponer"


def _contratar_real(tmp_path, monkeypatch, **perillas):
    """El contratista de PRODUCCION contra un bus de verdad en disco."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    _armar_economia(tmp_path, **perillas)
    pagador = srv._EcoPagador.desde_entorno(tmp_path)
    contratar = srv._contratar_para("dep:atlas", pagador,
                                    "2026-08-01T09:10:00", "2026-W31")
    return contratar, srv._eco_bus.Bus(pagador.ruta_bus)


def test_el_camino_de_produccion_siempre_manda_la_forma(tmp_path, monkeypatch):
    """El guarda de la seccion 8 del spec, apuntado al unico lugar que
    importa: `forma` es opcional en `bus.alta` para no barrer 123 sitios de
    test, asi que lo que hay que fijar es que produccion nunca se la
    olvide."""
    contratar, _ = _contratar_real(tmp_path, monkeypatch)
    r = contratar({"nombre": "atlas", "presupuesto_semanal_mm": 10_000,
                   "agresividad_pct": 100, "salidas_semana_mm": 0},
                  "proponer", None, "no rindio", ficha=FICHA)
    # `Bus` no relee disco: es una foto tomada al construirse. Hay que
    # construir uno NUEVO despues del alta para ver lo que quedo escrito,
    # el mismo criterio que usa el resto del archivo.
    bus_real = srv._eco_bus.Bus(srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    datos = bus_real.datos(r["propuesta"])
    assert datos["forma"] == {"sobre": "el radar de precios",
                              "clave": "precios+radar",
                              "promete": "descartar", "tarda": "corto"}


def test_el_titulo_sale_de_la_ficha_y_no_del_motivo_crudo(tmp_path, monkeypatch):
    contratar, _ = _contratar_real(tmp_path, monkeypatch)
    r = contratar({"nombre": "atlas", "presupuesto_semanal_mm": 10_000,
                   "agresividad_pct": 100, "salidas_semana_mm": 0},
                  "proponer", None, "no rindio", ficha=FICHA)
    bus_real = srv._eco_bus.Bus(srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    assert bus_real.datos(r["propuesta"])["titulo"] == (
        "descartar: el radar de precios (corto) -- no rindio")


def test_el_plazo_de_la_ficha_manda_el_criterio_de_muerte(tmp_path, monkeypatch):
    """Antes eran cuatro semanas escritas a mano, iguales para una
    propuesta de una semana que para una de un trimestre."""
    contratar, _ = _contratar_real(tmp_path, monkeypatch)
    largo = {**FICHA, "tarda": "largo"}
    r = contratar({"nombre": "atlas", "presupuesto_semanal_mm": 10_000,
                   "agresividad_pct": 100, "salidas_semana_mm": 0},
                  "proponer", None, "x", ficha=largo)
    bus_real = srv._eco_bus.Bus(srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    assert bus_real.datos(r["propuesta"])["criterio"]["semanas_max"] == 12


def test_sin_ficha_el_contratista_no_escribe_nada(tmp_path, monkeypatch):
    """No hay camino de produccion que llegue aca sin ficha -- el jefe la
    desvia antes -- pero si alguna vez lo hubiera, escribir una propuesta
    sin identidad en un libro append-only es peor que no escribir."""
    contratar, bus_real = _contratar_real(tmp_path, monkeypatch)
    r = contratar({"nombre": "atlas", "presupuesto_semanal_mm": 10_000,
                   "agresividad_pct": 100, "salidas_semana_mm": 0},
                  "proponer", None, "hay hueco")
    assert r["en"] == "nada"
    assert bus_real.ids() == []


def test_la_clave_de_la_forma_real_corresponde_a_su_sobre(tmp_path, monkeypatch):
    """`bus.alta` no puede verificar esto: para comparar `clave` contra
    `sobre` tendria que importar `calipso.plantel.ficha.normalizar`, y el
    libro no puede depender de quien lo escribe. Una `clave` mentirosa
    entraria al libro sin que nada la detecte, y en un libro append-only
    eso no se corrige despues. Esta es la unica garantia que va a existir
    de esa correspondencia: contra el contratista de produccion, no contra
    un doble de test."""
    contratar, _ = _contratar_real(tmp_path, monkeypatch)
    r = contratar({"nombre": "atlas", "presupuesto_semanal_mm": 10_000,
                   "agresividad_pct": 100, "salidas_semana_mm": 0},
                  "proponer", None, "no rindio", ficha=FICHA)
    bus_real = srv._eco_bus.Bus(srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    forma = bus_real.datos(r["propuesta"])["forma"]
    assert forma["clave"] == _ficha.normalizar(forma["sobre"])


def test_pedir_publica_un_preseed_en_el_bus(tmp_path, monkeypatch):
    """El traductor que faltaba: hasta ahora `pedir` caia en la rama de
    `proponer` y publicaba un trabajo, que se financia contra la billetera
    de OTRO departamento -- justo lo que un departamento sin plata no puede
    conseguir. Tiene que salir como `tipo="preseed"`, que se financia
    contra el tesoro."""
    contratar, _ = _contratar_real(tmp_path, monkeypatch,
                                   techo_preseed_mm=150_000,
                                   techo_preseed_ciclo_mm=10_000_000)
    s = {"nombre": "atlas", "presupuesto_semanal_mm": 0,
         "agresividad_pct": 30, "salidas_semana_mm": 0,
         "techo_preseed_mm": 150_000}
    r = contratar(s, "pedir", "120000", "arrancamos de cero")

    assert r["tipo"] == "preseed"
    assert r["monto_mm"] == 120_000
    bus = srv._eco_bus.Bus(
        srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    d = bus.datos(r["propuesta"])
    assert d["tipo"] == "preseed"
    assert d["departamento"] == "dep:atlas"
    assert d["presupuesto_mm"] == 120_000
    assert d["titulo"] == "arrancamos de cero"


def test_el_monto_del_preseed_lo_recorta_la_perilla(tmp_path, monkeypatch):
    """LA REGLA: los numeros los declara el jefe desde sus PERILLAS, no el
    modelo. `decision.parsear` exige un entero positivo, pero un entero
    positivo alucinado sigue siendo alucinado -- el de 3b nombra ids que no
    existen. El peor caso tiene que ser exactamente el techo que puso
    Pedro."""
    contratar, _ = _contratar_real(tmp_path, monkeypatch,
                                   techo_preseed_mm=50_000,
                                   techo_preseed_ciclo_mm=10_000_000)
    s = {"nombre": "atlas", "presupuesto_semanal_mm": 0,
         "agresividad_pct": 30, "salidas_semana_mm": 0,
         "techo_preseed_mm": 50_000}
    r = contratar(s, "pedir", "999999999", "quiero todo")
    assert r["monto_mm"] == 50_000

    bus = srv._eco_bus.Bus(
        srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    assert bus.datos(r["propuesta"])["presupuesto_mm"] == 50_000


def test_sin_techo_el_contratista_no_escribe_en_el_bus(tmp_path, monkeypatch):
    """Segunda linea de defensa: el freno de verdad vive en `jefe._puede`,
    pero el contratista tambien se llama directo (esta el precedente en
    este mismo archivo) y no puede escribir un pre-seed de monto inventado
    si Pedro no dijo cuanto."""
    contratar, _ = _contratar_real(tmp_path, monkeypatch)
    s = {"nombre": "atlas", "presupuesto_semanal_mm": 0,
         "agresividad_pct": 30, "salidas_semana_mm": 0,
         "techo_preseed_mm": 0}
    r = contratar(s, "pedir", "120000", "arrancamos de cero")
    assert r["en"] == "nada" and "techo de pre-seed" in r["motivo"]

    bus = srv._eco_bus.Bus(
        srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    assert bus.ids() == []


def test_un_superindice_no_revienta_el_contratista(tmp_path, monkeypatch):
    """`'²'.isdigit()` es True y `int('²')` revienta con ValueError: los
    superindices son Numeric_Type=Digit pero no decimales. El sintoma no
    era un crash visible sino una mentira en el registro del jefe -- en vez
    de caer en el recorte al techo, caia en el `except` de `tic` y se
    anotaba como "reviento actuando". Con `.isdecimal()`, lo que no es un
    monto se trata como si no hubiera venido: se pide el techo."""
    contratar, _ = _contratar_real(tmp_path, monkeypatch,
                                   techo_preseed_mm=50_000,
                                   techo_preseed_ciclo_mm=10_000_000)
    s = {"nombre": "atlas", "presupuesto_semanal_mm": 0,
         "agresividad_pct": 30, "salidas_semana_mm": 0,
         "techo_preseed_mm": 50_000}
    r = contratar(s, "pedir", "²", "quiero arrancar")
    assert r["monto_mm"] == 50_000
    # y el digito arabe, que `int()` si lee, se sigue leyendo
    r2 = contratar(s, "pedir", "٥", "cinco")
    assert r2["monto_mm"] == 5


def test_el_techo_de_propuestas_se_relee_adentro_del_candado(
        tmp_path, monkeypatch):
    """TOCTOU: `jefe._puede` chequea el techo contra la foto que trajo
    `situacion`, tomada AFUERA del candado, y el bus se escribe adentro.
    Dos tics simultaneos del mismo departamento leen el mismo conteo y
    pasan los dos -- y los dos llamadores que producen la carrera existen,
    son los que nombra el docstring de `interruptor.tomar_tic`: el ticker
    de rutinas y el boton de correr a mano."""
    contratar, bus = _contratar_real(tmp_path, monkeypatch)
    s = {"nombre": "atlas", "presupuesto_semanal_mm": 10_000,
         "agresividad_pct": 100, "salidas_semana_mm": 0,
         "disponible_mm": 100_000}

    salidas, arranque = [], threading.Barrier(6)

    def tic():
        arranque.wait()
        salidas.append(contratar(dict(s), "proponer", None, "otra apuesta",
                                 ficha=FICHA))

    hilos = [threading.Thread(target=tic) for _ in range(6)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    bus = srv._eco_bus.Bus(srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    assert len(bus.ids()) <= _jefe.TECHO_PROPUESTAS
    assert sum(1 for x in salidas if x.get("en") == "nada") >= 1


def test_sin_presupuesto_semanal_el_tope_lo_da_la_billetera(
        tmp_path, monkeypatch):
    """El capital del pre-seed llegaba y quedaba inerte: el monto de una
    propuesta se calculaba contra `presupuesto_semanal_mm`, que el pre-seed
    no toca y nada mueve solo, asi que un departamento con 300.000 recien
    financiados publicaba propuestas de UN milimon. El dia 1 no son una
    perilla sino dos, y nada lo decia."""
    contratar, _ = _contratar_real(tmp_path, monkeypatch)
    s = {"nombre": "atlas", "presupuesto_semanal_mm": 0,
         "agresividad_pct": 30, "salidas_semana_mm": 0,
         "disponible_mm": 300_000}
    r = contratar(s, "proponer", None, "ahora si a trabajar", ficha=FICHA)
    bus = srv._eco_bus.Bus(srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    assert bus.datos(r["propuesta"])["presupuesto_mm"] == 90_000


# -- el techo del ciclo, segunda linea: adentro del candado ----------------

def test_el_techo_del_ciclo_recorta_el_pedido_a_lo_que_queda(
        tmp_path, monkeypatch):
    """El techo del ciclo RECORTA, no solo frena, igual que el techo por
    pedido. Publicar un pedido por mas de lo que se le puede pagar es
    publicar una propuesta que `bus.financiar` va a rechazar con Pedro ya
    mirandola: la bandeja se llena de pedidos impagables y el techo de
    propuestas se consume con ellos."""
    contratar, _ = _contratar_real(tmp_path, monkeypatch,
                                   techo_preseed_mm=150_000,
                                   techo_preseed_ciclo_mm=60_000)
    bus = srv._eco_bus.Bus(
        srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    bus.alta("2026-08-01T09:00:00", "2026-W31", "viejo", "dep:atlas",
             "primera ronda", 40_000, 40_000, {"gasto_max_mm": 40_000},
             tipo="preseed")
    s = {"nombre": "atlas", "presupuesto_semanal_mm": 0,
         "agresividad_pct": 30, "salidas_semana_mm": 0,
         "techo_preseed_mm": 150_000}

    r = contratar(s, "pedir", "150000", "quiero todo")
    assert r["monto_mm"] == 20_000, "no recorto a lo que queda de la ventana"
    assert r["libre_ventana_mm"] == 20_000
    assert r["techo_ventana_mm"] == 60_000
    # y sin el nombre viejo: los dos numeros se miden sobre la ventana
    # deslizante, no sobre el ciclo de facturacion
    assert "libre_ciclo_mm" not in r and "techo_ciclo_mm" not in r
    bus2 = srv._eco_bus.Bus(
        srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    assert bus2.datos(r["propuesta"])["presupuesto_mm"] == 20_000


def test_sin_lugar_en_el_ciclo_el_contratista_no_escribe_en_el_bus(
        tmp_path, monkeypatch):
    """TOCTOU: `jefe._puede` mira el acumulado contra la foto que trajo
    `situacion`, tomada AFUERA del candado, y el bus se escribe adentro.
    Dos tics simultaneos del mismo departamento leen el mismo acumulado y
    pasan los dos. Segunda linea, con el registro, el libro y el bus
    frescos -- el mismo criterio que `_bandeja_llena`."""
    contratar, _ = _contratar_real(tmp_path, monkeypatch,
                                   techo_preseed_mm=150_000,
                                   techo_preseed_ciclo_mm=40_000)
    bus = srv._eco_bus.Bus(
        srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    bus.alta("2026-08-01T09:00:00", "2026-W31", "viejo", "dep:atlas",
             "primera ronda", 40_000, 40_000, {"gasto_max_mm": 40_000},
             tipo="preseed")
    s = {"nombre": "atlas", "presupuesto_semanal_mm": 0,
         "agresividad_pct": 30, "salidas_semana_mm": 0,
         "techo_preseed_mm": 150_000}

    r = contratar(s, "pedir", "50000", "otra ronda")
    assert r["en"] == "nada" and "techo de la ventana" in r["motivo"]
    bus2 = srv._eco_bus.Bus(
        srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    assert bus2.ids() == ["viejo"], "escribio igual"


def test_la_perilla_bajada_a_cero_mientras_el_tic_pensaba_frena(
        tmp_path, monkeypatch):
    """Las perillas se releen del registro FRESCO adentro del candado y no
    de la foto de `situacion`: "me arrepenti, cerra la canilla" tiene que
    cerrar tambien el pedido que ya estaba pensandose. Mismo criterio que
    `bus.financiar`, que relee el techo al PAGAR."""
    contratar, _ = _contratar_real(tmp_path, monkeypatch,
                                   techo_preseed_mm=150_000,
                                   techo_preseed_ciclo_mm=0)
    # la foto vieja todavia dice que habia techo
    s = {"nombre": "atlas", "presupuesto_semanal_mm": 0,
         "agresividad_pct": 30, "salidas_semana_mm": 0,
         "techo_preseed_mm": 150_000}
    r = contratar(s, "pedir", "50000", "arrancamos")
    assert r["en"] == "nada" and "quedo en cero" in r["motivo"]
    bus = srv._eco_bus.Bus(
        srv._EcoPagador.desde_entorno(tmp_path).ruta_bus)
    assert bus.ids() == []


class _PagadorContado:
    """Un pagador de verdad, con un contador sobre `leer_kernel`: cada
    llamada es un parseo COMPLETO del libro (`Libro()` no cachea)."""

    def __init__(self, real):
        self._real = real
        self.lecturas = 0

    def leer_kernel(self):
        self.lecturas += 1
        return self._real.leer_kernel()

    def __getattr__(self, nombre):
        return getattr(self._real, nombre)


def test_la_bandeja_no_pliega_el_libro_si_no_hay_preseed_que_mirar(
        tmp_path, monkeypatch):
    """El techo de bandeja corre ADENTRO del candado global de economia, en
    el bucle del jefe que corre desatendido a doscientos tics por semana y
    por departamento, y el docstring de `_jefe` dice que tener el flock
    tomado durante segundos serializa el chat y a dispatch contra el.

    Para consultar el vencimiento de un pre-seed hay que plegar el libro,
    pero solo si hay un pre-seed en pie que mirar: `proponer` no tiene
    ninguno y pagaba un `Kernel(Libro(...))` entero igual, donde antes de
    este techo no leia el libro en absoluto. Y `pedir` lo pagaba DOS veces
    en el mismo candado -- el conteo de bandeja y el recorte del monto--
    aunque nadie mas pueda escribir mientras el flock esta tomado, que es
    para lo que se toma."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    _armar_economia(tmp_path, techo_preseed_mm=150_000,
                    techo_preseed_ciclo_mm=10_000_000)
    pagador = _PagadorContado(srv._EcoPagador.desde_entorno(tmp_path))
    contratar = srv._contratar_para("dep:atlas", pagador,
                                    "2026-08-01T09:10:00", "2026-W31")
    s = {"nombre": "atlas", "presupuesto_semanal_mm": 1_000,
         "agresividad_pct": 100, "salidas_semana_mm": 0,
         "techo_preseed_mm": 150_000}

    r = contratar(s, "proponer", None, "hay hueco", ficha=FICHA)
    assert r["propuesta"]
    assert pagador.lecturas == 0, "proponer plego el libro sin un pre-seed"

    pagador.lecturas = 0
    r2 = contratar(s, "pedir", "50000", "arrancamos")
    assert r2["monto_mm"] == 50_000
    assert pagador.lecturas == 1, f"{pagador.lecturas} parseos en un pedir"

    # y con un pre-seed en pie el vencimiento SI se consulta: la guardia
    # ahorra el parseo, no lo saltea
    pagador.lecturas = 0
    r3 = contratar(s, "proponer", None, "otra", ficha=FICHA)
    assert r3["propuesta"]
    assert pagador.lecturas == 1


def test_la_ruta_local_del_chat_ejecuta_en_ollama_no_en_claude(monkeypatch):
    """La fuga central: la ruta 'local' corria `claude -p`, mandando el dato
    a Anthropic bajo la etiqueta 'local'. Tiene que transmitir desde el
    Ollama que ya corre."""
    llamado = {}

    def ollama_espia(url, payload, usage=None):
        llamado["url"] = url
        llamado["messages"] = payload.get("messages")
        yield "respuesta de ollama"

    def subprocess_prohibido(*a, **k):
        raise AssertionError("la ruta local NO puede llamar a subprocess (claude)")

    monkeypatch.setattr(srv.dispatch, "_ollama_chat_chunks", ollama_espia)
    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: True)
    monkeypatch.setattr(srv.subprocess, "run", subprocess_prohibido)

    gen, modelo = srv._chunks_for("local", "SOY EL SISTEMA", "hola", {},
                                  chat_id=None)
    salida = "".join(gen)
    assert "respuesta de ollama" in salida
    assert modelo == srv.dispatch.CONFIG["local"]["model"]
    # el system viaja: el bug viejo lo tiraba
    assert any(m.get("role") == "system" and "SOY EL SISTEMA" in m.get("content", "")
               for m in llamado["messages"])


def test_la_ruta_local_con_ollama_caido_falla_cerrado_y_no_llama_claude(monkeypatch):
    """Fallo cerrado: si Ollama no responde, la ruta local NO degrada a
    claude. Da un mensaje claro y no ejecuta nada remoto."""
    def subprocess_prohibido(*a, **k):
        raise AssertionError("Ollama caido no puede caer a claude")

    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: False)
    monkeypatch.setattr(srv.subprocess, "run", subprocess_prohibido)

    gen, modelo = srv._chunks_for("local", "sys", "hola", {}, chat_id=None)
    salida = "".join(gen)
    assert "no" in salida.lower() and "local" in salida.lower()
    assert modelo != "claude"


def test_local_up_refleja_la_salud_real_de_ollama(monkeypatch):
    """Estaba hardcodeado en False 'sin Ollama', pero Ollama corre. Con la
    salud real, un Ollama vivo se ve vivo y el scorer puede elegir local."""
    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: True)
    monkeypatch.setattr(srv, "_http_up_cached", lambda url: True)
    h = srv._connector_health(use_cache=False)
    assert h["local"]["ready"] is True

    monkeypatch.setattr(srv, "_http_up", lambda url, timeout=1.5: False)
    h2 = srv._connector_health(use_cache=False)
    assert h2["local"]["ready"] is False


def test_la_api_paga_no_gana_sin_gesto_explicito(monkeypatch):
    """El freno de API forzada solo vivia en el CLI muerto. En el chat vivo,
    si las suscripciones caen y el proxy esta arriba, la API paga ganaba en
    silencio."""
    # un ranking donde la API queda primera (suscripciones no disponibles)
    ranking = [{"key": "api:deepseek-chat", "route": "api", "client": None,
                "model": "deepseek-chat", "persona": "Confucio", "tier": "mid",
                "score": 0.5}]
    monkeypatch.setattr(srv.capabilities, "choose", lambda *a, **k: list(ranking))
    verdict, *_ = srv._decide("analiza esto")
    assert verdict["route"] != "api"


def test_la_api_paga_si_gana_cuando_pedro_la_fuerza(monkeypatch):
    """Con /api, Pedro forzo el gesto explicito y ahi si la API puede ganar."""
    ranking = [{"key": "api:deepseek-chat", "route": "api", "client": None,
                "model": "deepseek-chat", "persona": "Confucio", "tier": "mid",
                "score": 0.5}]
    monkeypatch.setattr(srv.capabilities, "choose", lambda *a, **k: list(ranking))
    # con /api la directiva arma force_route == "api"
    verdict, *_ = srv._decide("/api analiza esto")
    assert verdict["route"] == "api"
