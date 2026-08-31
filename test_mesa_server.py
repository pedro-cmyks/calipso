"""La mesa de Pedro por HTTP: leer el bus, financiar y descartar."""
import json

import pytest
from fastapi.testclient import TestClient

from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.bus import Bus, cuenta_trabajo
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
import calipso.server as srv

TS = "2026-08-26T10:00:00"
W = "2026-W35"


def _economia_de_prueba(base, abrir=True):
    """Una economia minima en disco, como la que arma el bootstrap real."""
    eco = base / "economia"
    eco.mkdir(parents=True, exist_ok=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=25_000,
                             # las dos perillas que autorizan la ronda
                             # pre-seed: `financiar` las relee al pagar, no
                             # alcanza con que estuvieran puestas cuando se
                             # publico. La del ciclo bien alta para que no
                             # sea la que corte aca; el test que la prueba
                             # a ella la baja a proposito
                             techo_preseed_mm=150_000,
                             techo_preseed_ciclo_mm=10_000_000))
    r.alta(deps.Departamento("mercado", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=25_000))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    if abrir:
        pt.emitir_semana(k, TS, W, 4_000, 1_000)
    k.acunar(TS, W, "dep:atlas", 400_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 200_000,
                       "capacidad_ciclo": 2_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    return eco


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    # el reloj real avanza; el libro de prueba solo abre W35. Sin esto los
    # tests se ponen en rojo solos en cuanto el calendario cruza de semana.
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    _economia_de_prueba(tmp_path)
    return TestClient(srv.app), tmp_path


def _propuesta(base, id="p1", cuenta="dep:atlas", titulo="radar de precios"):
    b = Bus(base / "economia" / "bus.jsonl")
    b.alta(TS, W, id, cuenta, titulo, 10_000, 30_000,
           {"gasto_max_mm": 10_000, "semanas_max": 4})
    return b


def test_el_bus_vacio_devuelve_una_lista_vacia(cliente):
    c, base = cliente
    r = c.get("/api/economia/bus", params={"token": srv.TOKEN})
    assert r.status_code == 200
    d = r.json()
    assert d["activa"] is True
    assert d["semana_abierta"] is True
    assert d["propuestas"] == []


def test_una_propuesta_llega_con_lo_que_la_mesa_necesita(cliente):
    c, base = cliente
    _propuesta(base)
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert len(d["propuestas"]) == 1
    p = d["propuestas"][0]
    assert p["id"] == "p1"
    assert p["estado"] == "alta"
    assert p["departamento"] == "dep:atlas"
    assert p["titulo"] == "radar de precios"
    assert p["presupuesto_mm"] == 10_000
    assert p["retorno_mm"] == 30_000
    assert p["criterio"] == {"gasto_max_mm": 10_000, "semanas_max": 4}
    assert p["gastado_mm"] == 0
    assert p["aportes"] == {}


def test_una_propuesta_con_un_campo_faltante_no_tumba_la_mesa(cliente):
    """Hasta esta rama la unica salida era editar bus.jsonl a mano (spec).
    Si en el bus real de Pedro hay una linea de un esquema anterior o
    editada asi, el GET no puede tirar KeyError y devolver un 500 mudo: el
    resto de la mesa tiene que seguir siendo legible."""
    c, base = cliente
    ruta = base / "economia" / "bus.jsonl"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    linea = {"ts": TS, "semana": W, "evento": "alta", "id": "vieja",
             "departamento": "dep:atlas", "titulo": "de otro esquema"}
    with ruta.open("a", encoding="utf-8") as f:
        f.write(json.dumps(linea) + "\n")
    r = c.get("/api/economia/bus", params={"token": srv.TOKEN})
    assert r.status_code == 200, r.text
    d = r.json()
    p = next(x for x in d["propuestas"] if x["id"] == "vieja")
    assert p["presupuesto_mm"] == 0
    assert p["retorno_mm"] == 0
    assert p["criterio"] == {}


def test_los_departamentos_son_solo_los_de_la_fabrica(cliente):
    """El libro rechaza cualquier financiador fuera de la zona fabrica, asi
    que ofrecer otro en el selector seria ofrecer un boton que falla. Hay un
    departamento personal a proposito: sin el, borrar el filtro dejaria este
    test verde igual."""
    c, base = cliente
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    cuentas = {x["cuenta"] for x in d["departamentos"]}
    assert cuentas == {"dep:atlas", "dep:mercado"}
    assert "dep:finanzas" not in cuentas
    assert all(x["zona"] == deps.ZONA_FABRICA for x in d["departamentos"])
    atlas = next(x for x in d["departamentos"] if x["cuenta"] == "dep:atlas")
    assert atlas["disponible_mm"] == 400_000


def test_dice_si_la_semana_esta_abierta(tmp_path, monkeypatch):
    """Sin emision de PT esa semana, TODA financiacion falla. Que la mesa lo
    diga antes es la diferencia entre un aviso y un error incomprensible."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    _economia_de_prueba(tmp_path, abrir=False)
    c = TestClient(srv.app)
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["semana_abierta"] is False


def test_sin_economia_no_esta_activa(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    c = TestClient(srv.app)
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["activa"] is False


def test_sin_token_no_se_lee_el_bus(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    c = TestClient(srv.app)
    assert c.get("/api/economia/bus").status_code == 401


def test_financiar_mueve_la_plata_y_marca(cliente):
    c, base = cliente
    _propuesta(base)
    r = c.post("/api/economia/bus/p1/financiar", params={"token": srv.TOKEN},
               json={"cuenta": "dep:atlas", "mm": 10_000})
    assert r.status_code == 200, r.text
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    p = d["propuestas"][0]
    assert p["estado"] == "financiada"
    assert p["aportes"] == {"dep:atlas": 10_000}
    atlas = next(x for x in d["departamentos"] if x["cuenta"] == "dep:atlas")
    assert atlas["disponible_mm"] == 390_000


def test_el_segundo_toque_no_paga_dos_veces(cliente):
    """`financiar` acepta financiar algo ya financiada (es cofinanciacion),
    asi que dos toques en un telefono lento pagarian dos veces. Se cierra por
    construccion: el endpoint solo acepta propuestas en `alta`."""
    c, base = cliente
    _propuesta(base)
    ok = c.post("/api/economia/bus/p1/financiar", params={"token": srv.TOKEN},
                json={"cuenta": "dep:atlas", "mm": 10_000})
    assert ok.status_code == 200
    otra = c.post("/api/economia/bus/p1/financiar", params={"token": srv.TOKEN},
                  json={"cuenta": "dep:atlas", "mm": 10_000})
    assert otra.status_code == 400
    assert "ya no esta esperando plata" in otra.json()["detail"]
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["propuestas"][0]["aportes"] == {"dep:atlas": 10_000}


def test_no_se_financia_una_alta_con_aporte_ya_en_el_libro(cliente):
    """`financiar` transfiere ANTES de marcar. Si el proceso muere entre las
    dos escrituras (disco lleno, crash a mitad de los appends), la plata ya
    salio pero la propuesta queda en `alta`: el corte no puede confiar solo
    en la marca, tiene que mirar el libro, la fuente de verdad. Se simula el
    aporte a mano, con el mismo motivo que usa `financiar`, sin pasar por
    `bus.marcar` -- asi queda el estado a medio camino que dejaria un
    crash."""
    c, base = cliente
    _propuesta(base)
    k = Kernel(Libro(base / "economia" / "libro.jsonl"))
    k.transferir(TS, W, "dep:atlas", cuenta_trabajo("p1"), 10_000,
                 motivo="financiacion")
    r = c.post("/api/economia/bus/p1/financiar", params={"token": srv.TOKEN},
               json={"cuenta": "dep:atlas", "mm": 10_000})
    assert r.status_code == 400
    assert "ya no esta esperando plata" in r.json()["detail"]
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["propuestas"][0]["estado"] == "alta"


def test_un_error_del_bus_es_400_con_su_mensaje(tmp_path, monkeypatch):
    """Esta es la primera pantalla de economia cuyos errores los lee un
    humano: "semana no operativa" tiene que llegar como texto, no como un 500
    opaco."""
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    _economia_de_prueba(tmp_path, abrir=False)
    c = TestClient(srv.app)
    _propuesta(tmp_path)
    r = c.post("/api/economia/bus/p1/financiar", params={"token": srv.TOKEN},
               json={"cuenta": "dep:atlas", "mm": 10_000})
    assert r.status_code == 400
    assert "semana no operativa" in r.json()["detail"]


def test_financiar_una_propuesta_que_no_existe_es_400(cliente):
    c, base = cliente
    r = c.post("/api/economia/bus/fantasma/financiar",
               params={"token": srv.TOKEN},
               json={"cuenta": "dep:atlas", "mm": 1_000})
    assert r.status_code == 400


def test_descartar_libera_el_lugar(cliente):
    c, base = cliente
    _propuesta(base)
    r = c.post("/api/economia/bus/p1/descartar", params={"token": srv.TOKEN})
    assert r.status_code == 200, r.text
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["propuestas"] == []


def test_no_se_descarta_una_ya_financiada(cliente):
    c, base = cliente
    _propuesta(base)
    c.post("/api/economia/bus/p1/financiar", params={"token": srv.TOKEN},
           json={"cuenta": "dep:atlas", "mm": 10_000})
    r = c.post("/api/economia/bus/p1/descartar", params={"token": srv.TOKEN})
    assert r.status_code == 400


def test_no_se_descarta_una_alta_con_aporte_ya_en_el_libro(cliente):
    """Calcado de test_no_se_financia_una_alta_con_aporte_ya_en_el_libro:
    `descartar` es el gemelo de `financiar` y tenia el mismo hueco. Si el
    proceso muere entre la transferencia y la marca (disco lleno, crash a
    mitad de los appends), la plata ya salio pero la propuesta queda en
    `alta`. Sin este chequeo, descartarla la manda a `descartada` -terminal
    e invisible- y esa plata queda enterrada en trabajo:<id> sin ningun
    camino de vuelta salvo editar bus.jsonl a mano."""
    c, base = cliente
    _propuesta(base)
    k = Kernel(Libro(base / "economia" / "libro.jsonl"))
    k.transferir(TS, W, "dep:atlas", cuenta_trabajo("p1"), 10_000,
                 motivo="financiacion")
    r = c.post("/api/economia/bus/p1/descartar", params={"token": srv.TOKEN})
    assert r.status_code == 400
    assert "ya no se puede descartar" in r.json()["detail"]
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["propuestas"][0]["estado"] == "alta"


def test_sin_token_no_se_financia(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    c = TestClient(srv.app)
    r = c.post("/api/economia/bus/p1/financiar",
               json={"cuenta": "dep:atlas", "mm": 1})
    assert r.status_code == 401


def test_leer_el_bus_toma_el_candado_sobre_el_libro(cliente, monkeypatch):
    """Molde: test_contratar_escribe_el_alta_bajo_candado, en
    test_plantel_server.py (spec seccion 8: "el lector bajo candado"). El
    GET es un lector mas de economia y tiene que serializarse igual que las
    escrituras -- sin este test, sacar el `with _eco_candado(...)` de
    api_eco_bus deja el resto de la suite en verde."""
    c, base = cliente
    _propuesta(base)

    import contextlib as _ctxlib

    rutas_tomadas = []
    candado_original = srv._eco_candado

    @_ctxlib.contextmanager
    def candado_espia(ruta, no_bloquear=False):
        with candado_original(ruta, no_bloquear=no_bloquear):
            rutas_tomadas.append(ruta)
            yield

    monkeypatch.setattr(srv, "_eco_candado", candado_espia)

    r = c.get("/api/economia/bus", params={"token": srv.TOKEN})
    assert r.status_code == 200
    assert rutas_tomadas == [base / "economia" / "libro.jsonl"], (
        "api_eco_bus no tomo el candado sobre ruta_libro")


def _preseed(base, id="ps1", cuenta="dep:atlas", mm=120_000):
    b = Bus(base / "economia" / "bus.jsonl")
    b.alta(TS, W, id, cuenta, "arrancamos de cero", mm, mm,
           {"gasto_max_mm": mm}, tipo="preseed")
    return b


def test_la_mesa_ve_de_que_tipo_es_cada_propuesta(cliente):
    """Sin el `tipo`, la mesa no puede financiar un pre-seed: se paga contra
    el TESORO y no contra la billetera de otro departamento (bus.financiar
    lo exige), y el selector de mesa.js solo lista departamentos de
    fabrica."""
    c, base = cliente
    _propuesta(base, id="p1")
    _preseed(base, id="ps1")
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    tipos = {p["id"]: p["tipo"] for p in d["propuestas"]}
    assert tipos == {"p1": "trabajo", "ps1": "preseed"}


def test_una_linea_vieja_del_bus_se_lee_como_trabajo(cliente):
    """El bus real de Pedro tiene lineas escritas antes de que `tipo`
    existiera. Que la mesa entera se caiga con un 500 mudo por eso seria el
    peor final posible -- mismo criterio que el resto de los `.get()` con
    default de este endpoint."""
    c, base = cliente
    ruta = base / "economia" / "bus.jsonl"
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(
        {"ts": TS, "semana": W, "evento": "alta", "id": "viejo",
         "departamento": "dep:atlas", "titulo": "de antes",
         "presupuesto_mm": 5_000, "retorno_mm": 9_000,
         "criterio": {"gasto_max_mm": 5_000}}) + "\n", encoding="utf-8")
    d = c.get("/api/economia/bus", params={"token": srv.TOKEN}).json()
    assert d["propuestas"][0]["tipo"] == "trabajo"


def test_pedro_financia_un_preseed_contra_el_tesoro(cliente):
    """El entregable de punta a punta: la plata sale del TESORO y cae en la
    cuenta DEL DEPARTAMENTO (no en trabajo:<id>: un pre-seed no es un
    trabajo, entrega capital)."""
    c, base = cliente
    _preseed(base, mm=120_000)
    k = Kernel(Libro(base / "economia" / "libro.jsonl"))
    k.acunar(TS, W, t.TESORO, 500_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    antes = k.saldo("dep:atlas")

    r = c.post("/api/economia/bus/ps1/financiar", params={"token": srv.TOKEN},
               json={"cuenta": t.TESORO, "mm": 120_000})
    assert r.status_code == 200, r.text

    k2 = Kernel(Libro(base / "economia" / "libro.jsonl"))
    assert k2.saldo("dep:atlas") == antes + 120_000
    assert k2.saldo(cuenta_trabajo("ps1")) == 0
    # cerrada, no financiada: la plata cayo y el pedido sale de la mesa
    assert Bus(base / "economia" / "bus.jsonl").estado("ps1") == "cerrada"


def test_un_preseed_ya_pagado_no_se_paga_dos_veces(cliente):
    """El corte mira el LIBRO, no la marca: `financiar` transfiere ANTES de
    marcar, asi que un crash entre las dos escrituras deja la plata afuera
    y la propuesta en `alta`. Para un trabajo eso lo ve `aportes`
    (`trabajo:<id>`); un pre-seed cae en la cuenta del departamento, que es
    la misma para todos sus pedidos, y por eso hace falta `aporte_preseed`,
    que mira el `ref` del asiento."""
    from calipso.economia import bus as bus_mod

    c, base = cliente
    b = _preseed(base, mm=120_000)
    k = Kernel(Libro(base / "economia" / "libro.jsonl"))
    k.acunar(TS, W, t.TESORO, 500_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    c.post("/api/economia/bus/ps1/financiar", params={"token": srv.TOKEN},
           json={"cuenta": t.TESORO, "mm": 120_000})

    # el crash simulado: la marca se pierde, la plata ya salio
    asientos = Kernel(Libro(base / "economia" / "libro.jsonl")).libro.asientos()
    assert bus_mod.aporte_preseed(asientos, "ps1") == 120_000
    lineas = [x for x in (base / "economia" / "bus.jsonl").read_text(
        encoding="utf-8").splitlines()
        if '"financiada"' not in x and '"cerrada"' not in x]
    (base / "economia" / "bus.jsonl").write_text("\n".join(lineas) + "\n",
                                                 encoding="utf-8")
    assert Bus(base / "economia" / "bus.jsonl").estado("ps1") == "alta"

    r = c.post("/api/economia/bus/ps1/financiar", params={"token": srv.TOKEN},
               json={"cuenta": t.TESORO, "mm": 120_000})
    assert r.status_code == 400
    assert Kernel(Libro(base / "economia" / "libro.jsonl")
                  ).saldo("dep:atlas") == 400_000 + 120_000


def test_un_preseed_financiado_sale_de_la_mesa(cliente):
    """La mesa "es para decidir, no un historial", pero para un pre-seed
    `financiada` era un estado FINAL: `evaluar_y_liquidar_muertos` lo
    saltea a proposito, `descartar` solo acepta `alta` y no hay ningun otro
    camino a `muerta`. Cada ronda de capital que Pedro aprobaba le dejaba
    una fila permanente en la superficie donde decide -- exactamente el
    ruido que el techo de propuestas existe para evitar."""
    c, base = cliente
    _preseed(base, mm=120_000)
    k = Kernel(Libro(base / "economia" / "libro.jsonl"))
    k.acunar(TS, W, t.TESORO, 500_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    assert [p["id"] for p in c.get("/api/economia/bus",
                                   params={"token": srv.TOKEN}
                                   ).json()["propuestas"]] == ["ps1"]

    r = c.post("/api/economia/bus/ps1/financiar", params={"token": srv.TOKEN},
               json={"cuenta": t.TESORO, "mm": 120_000})
    assert r.status_code == 200, r.text
    assert c.get("/api/economia/bus", params={"token": srv.TOKEN}
                 ).json()["propuestas"] == []


def test_el_techo_del_ciclo_frena_a_pedro_en_la_mesa(cliente):
    """DE PUNTA A PUNTA, por http: el techo del ciclo ata tambien a Pedro.
    Dos pedidos en pie, cada uno dentro del techo POR PEDIDO; el primero se
    paga, el segundo choca contra el acumulado del ciclo. Es el caso que el
    freno del jefe no puede cerrar solo -- los dos se publicaron cuando
    todavia habia lugar-- y por eso el freno de verdad vive donde la plata
    sale.

    Y la salida es EXPLICITA: subir la perilla, un POST a
    .../perillas, no un override silencioso ni una pregunta del motor de
    permisos que se pueda contestar "si, siempre"."""
    c, base = cliente
    deps.Registro(base / "economia" / "departamentos.json").ajustar(
        "atlas", techo_preseed_ciclo_mm=150_000)
    _preseed(base, id="ps1", mm=100_000)
    _preseed(base, id="ps2", mm=100_000)
    k = Kernel(Libro(base / "economia" / "libro.jsonl"))
    k.acunar(TS, W, t.TESORO, 900_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    antes = k.saldo("dep:atlas")

    r1 = c.post("/api/economia/bus/ps1/financiar", params={"token": srv.TOKEN},
                json={"cuenta": t.TESORO, "mm": 100_000})
    assert r1.status_code == 200, r1.text

    r2 = c.post("/api/economia/bus/ps2/financiar", params={"token": srv.TOKEN},
                json={"cuenta": t.TESORO, "mm": 100_000})
    assert r2.status_code == 400, r2.text
    assert "techo de pre-seed del ciclo" in r2.json()["detail"]
    assert "subi la perilla" in r2.json()["detail"]

    # y la plata NO salio: 100.000, no 200.000
    k2 = Kernel(Libro(base / "economia" / "libro.jsonl"))
    assert k2.saldo("dep:atlas") == antes + 100_000
    assert Bus(base / "economia" / "bus.jsonl").estado("ps2") == "alta"

    # la salida de Pedro: subir la perilla desde la pantalla de Plata
    rp = c.post("/api/economia/departamentos/atlas/perillas",
                params={"token": srv.TOKEN},
                json={"techo_preseed_ciclo_mm": 250_000})
    assert rp.status_code == 200, rp.text
    r3 = c.post("/api/economia/bus/ps2/financiar", params={"token": srv.TOKEN},
                json={"cuenta": t.TESORO, "mm": 100_000})
    assert r3.status_code == 200, r3.text
    assert Kernel(Libro(base / "economia" / "libro.jsonl")).saldo(
        "dep:atlas") == antes + 200_000
