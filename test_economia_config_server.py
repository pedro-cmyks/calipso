#!/usr/bin/env python3
"""
test_economia_config_server.py — La configuracion de la economia deja de
ser de escritura unica.

`POST /api/economia/sembrar` escribe departamentos.json y suscripciones.json
una sola vez y se niega a correr de nuevo (con razon: el libro es
append-only). Eso dejaba un solo camino para mover un numero: abrir el json
en un editor. Aca se prueban los dos caminos que lo reemplazan, y la
diferencia deliberada entre ellos:

  POST /api/economia/departamentos/{n}/perillas    NO pasa por permisos
  POST /api/economia/suscripciones/{n}/capacidad   SI pasa por permisos

No es una inconsistencia: una perilla se deshace escribiendola de nuevo y
no mueve un milimon; repreciar la capacidad cambia el denominador del
precio, y ese precio se estampa en asientos que no se reescriben.

Mismo patron que test_permisos_server.py, con la variable de entorno
ademas del `_ECO_BASE`: el motor de permisos resuelve CALIPSO_HOME en cada
llamada, asi que sin las dos la mitad del archivo escribiria en el
~/.calipso real de Pedro.
"""
import json

import pytest
from fastapi.testclient import TestClient

import calipso.server as srv
from calipso import consumo
from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro

TS = "2026-08-27T10:00:00"
W = "2026-W35"


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    home = tmp_path / ".calipso"
    eco = home / "economia"
    eco.mkdir(parents=True)
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=25_000))
    pt.emitir_semana(k, TS, W, 4_000, 1_000)
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 200_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 3_000},
        "chatgpt_plus": {"nombre": "chatgpt_plus", "costo_mensual_mm": 20_000,
                         "capacidad_ciclo": 1_000, "reserva_personal": 200,
                         "costo_api_mm_por_unidad": 3_000}}),
        encoding="utf-8")
    k.acunar(TS, W, t.TESORO, 1_200_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    monkeypatch.setattr(srv, "_ECO_BASE", home)
    monkeypatch.setenv("CALIPSO_HOME", str(home))
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, W))
    c = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})
    c.home = home
    return c


def _suscripciones(home) -> dict:
    return json.loads(
        (home / "economia" / "suscripciones.json").read_text(encoding="utf-8"))


def _departamentos(home) -> dict:
    return json.loads(
        (home / "economia" / "departamentos.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# GET /api/economia/config -- lo que Pedro ve antes de tocar nada
# --------------------------------------------------------------------------

def test_la_config_muestra_las_perillas_y_las_suscripciones(cliente):
    d = cliente.get("/api/economia/config").json()
    assert d["activa"] is True
    assert [x["nombre"] for x in d["departamentos"]] == ["atlas"]
    # la perilla nueva viaja con las otras, y nace en cero
    assert d["departamentos"][0]["techo_preseed_mm"] == 0
    nombres = [s["nombre"] for s in d["suscripciones"]]
    assert nombres == ["chatgpt_plus", "claude_max"]
    claude = next(s for s in d["suscripciones"] if s["nombre"] == "claude_max")
    # los derivados van calculados: la pantalla no vuelve a dividir
    assert claude["capacidad_fabrica"] == 800
    assert claude["precio_base_mm"] == 200


def test_sin_foto_del_probe_la_medicion_es_none_y_no_cero(cliente):
    """None y 0 no son lo mismo: cero seria "medimos y da cero", y lo que
    pasa es que la rutina de consumo todavia no corrio. Dibujar un cero
    ahi invitaria a aplicar un numero que nadie midio."""
    d = cliente.get("/api/economia/config").json()
    claude = next(s for s in d["suscripciones"] if s["nombre"] == "claude_max")
    assert claude["medido"]["proveedor"] == "claude"
    assert claude["medido"]["capacidad_ciclo_propuesta"] is None
    assert d["medido_generado"] is None


def test_la_medicion_del_probe_llega_a_la_suscripcion_que_le_toca(cliente):
    """La traduccion proveedor -> suscripcion sale de la MISMA tabla que usa
    dispatch para cobrar (`SUSCRIPCION_POR_CLIENTE`). Escribirla dos veces
    tendria el peor sintoma posible: medir una y aplicarselo a la otra."""
    consumo._guardar_resumen({
        "generado": "2026-08-27T09:00:00+00:00",
        "claude": {"medicion": {"turnos_observados": 340},
                   "inferencia": {"capacidad_ciclo_propuesta": 1_360,
                                  "nota": "extrapolacion lineal"}},
        "codex": {"medicion": {"plan_type": "plus"},
                  "inferencia": {"capacidad_ciclo_propuesta": 88,
                                 "nota": "apoyada en used_percent"}}})
    d = cliente.get("/api/economia/config").json()
    porNombre = {s["nombre"]: s for s in d["suscripciones"]}
    assert porNombre["claude_max"]["medido"]["capacidad_ciclo_propuesta"] == 1_360
    assert porNombre["chatgpt_plus"]["medido"]["capacidad_ciclo_propuesta"] == 88
    # la nota viaja tal cual: es lo que separa una medicion de una
    # extrapolacion, y esconderla dejaria a Pedro tratando a las dos igual
    assert "extrapolacion" in porNombre["claude_max"]["medido"]["nota"]
    assert d["medido_generado"] == "2026-08-27T09:00:00+00:00"


# --------------------------------------------------------------------------
# Las perillas de un departamento
# --------------------------------------------------------------------------

def test_la_perilla_de_preseed_se_cambia_por_la_api(cliente):
    r = cliente.post("/api/economia/departamentos/atlas/perillas",
                     json={"techo_preseed_mm": 150_000})
    assert r.status_code == 200, r.text
    assert r.json()["departamento"]["techo_preseed_mm"] == 150_000
    # y quedo en disco, que es lo unico que lee el jefe en su proximo tic
    assert _departamentos(cliente.home)["atlas"]["techo_preseed_mm"] == 150_000


def test_solo_se_cambia_lo_que_viene_en_el_cuerpo(cliente):
    """`exclude_unset`: mandar el dict entero con defaults pisaria en
    silencio perillas que Pedro no toco."""
    cliente.post("/api/economia/departamentos/atlas/perillas",
                 json={"techo_preseed_mm": 10_000})
    assert _departamentos(cliente.home)["atlas"]["presupuesto_semanal_mm"] == 25_000
    assert _departamentos(cliente.home)["atlas"]["explorar_explotar_pct"] == 50


def test_un_cuerpo_vacio_no_es_un_no_op_silencioso(cliente):
    r = cliente.post("/api/economia/departamentos/atlas/perillas", json={})
    assert r.status_code == 400
    assert "ninguna perilla" in r.json()["detail"]


def test_un_departamento_que_no_existe_da_404(cliente):
    r = cliente.post("/api/economia/departamentos/fantasma/perillas",
                     json={"techo_preseed_mm": 1_000})
    assert r.status_code == 404


def test_un_porcentaje_fuera_de_rango_no_entra(cliente):
    """`Departamento` no valida rangos (nunca los necesito: los numeros solo
    entraban por el sembrado). La puerta esta en la frontera http, que es
    donde entran las palabras del usuario."""
    for cuerpo in ({"explorar_explotar_pct": 900},
                   {"agresividad_pct": -1},
                   {"techo_preseed_mm": -5}):
        assert cliente.post("/api/economia/departamentos/atlas/perillas",
                            json=cuerpo).status_code == 422
    assert _departamentos(cliente.home)["atlas"]["explorar_explotar_pct"] == 50


def test_la_perilla_no_deja_rastro_en_el_motor_de_permisos(cliente):
    """La decision explicita: cambiar una perilla NO pasa por el motor.
    Es reversible (se escribe de nuevo) y no mueve un milimon -- lo que se
    pide sigue necesitando que Pedro financie en la mesa. Meterla en el
    mismo registro que las irreversibles diluye la señal de ese registro."""
    antes = len(cliente.get("/api/permisos").json()["registro"])
    r = cliente.post("/api/economia/departamentos/atlas/perillas",
                     json={"techo_preseed_mm": 5_000_000})   # 5.000 monedas
    assert r.status_code == 200          # ni 409 ni prompt, por grande que sea
    vista = cliente.get("/api/permisos").json()
    assert vista["pendientes"] == [] and vista["estacionadas"] == []
    assert len(vista["registro"]) == antes


# --------------------------------------------------------------------------
# La capacidad de una suscripcion
# --------------------------------------------------------------------------

def test_por_debajo_del_techo_la_capacidad_se_aplica_sola(cliente):
    """chatgpt_plus cuesta 20.000 mm por mes: por debajo del techo de plata
    (100.000 mm), asi que el motor la deja pasar y se aplica ahi mismo."""
    r = cliente.post("/api/economia/suscripciones/chatgpt_plus/capacidad",
                     json={"capacidad_ciclo": 352})
    assert r.status_code == 200, r.text
    assert _suscripciones(cliente.home)["chatgpt_plus"]["capacidad_ciclo"] == 352
    # y el precio de la unidad se movio: es el efecto, no un detalle
    assert r.json()["precio_base_mm"] != r.json()["precio_base_mm_anterior"]


def test_por_encima_del_techo_pregunta_y_no_escribe(cliente):
    """claude_max cuesta 200.000 mm por mes: por encima del techo. El
    cambio queda esperando la respuesta de Pedro y el json NO se toca --
    409 y no 202, igual que los otros consumidores de plata, porque la UI
    trata cualquier `ok` como exito."""
    r = cliente.post("/api/economia/suscripciones/claude_max/capacidad",
                     json={"capacidad_ciclo": 1_360})
    assert r.status_code == 409, r.text
    assert _suscripciones(cliente.home)["claude_max"]["capacidad_ciclo"] == 1_000
    pendientes = cliente.get("/api/permisos").json()["pendientes"]
    assert len(pendientes) == 1
    assert "repreciar la capacidad de claude_max" in pendientes[0]["texto"]


def test_el_si_de_pedro_completa_el_cambio(cliente):
    """El contrato de enchufe: quien pidio ya se volvio con un 409, asi que
    la respuesta tiene que poder COMPLETAR la accion, no solo autorizarla.
    Sin el ejecutor registrado, el si de Pedro autorizaria un cambio que
    nadie aplica."""
    cliente.post("/api/economia/suscripciones/claude_max/capacidad",
                 json={"capacidad_ciclo": 1_360})
    sol = cliente.get("/api/permisos").json()["pendientes"][0]
    r = cliente.post(f"/api/permisos/solicitudes/{sol['id']}/responder",
                     json={"respuesta": "si"})
    assert r.status_code == 200, r.text
    assert r.json()["ejecucion"]["ejecutada"] is True
    assert _suscripciones(cliente.home)["claude_max"]["capacidad_ciclo"] == 1_360


def test_bajar_la_capacidad_por_debajo_de_la_reserva_lo_dice_con_las_dos(cliente):
    """`Suscripcion` exige `0 <= reserva_personal < capacidad_ciclo`: las dos
    claves estan acopladas y mover una puede invalidar a la otra. El error
    tiene que nombrar la reserva que estorba, o Pedro no tiene forma de
    saber que le falta mandar."""
    r = cliente.post("/api/economia/suscripciones/chatgpt_plus/capacidad",
                     json={"capacidad_ciclo": 100})   # reserva es 200
    assert r.status_code == 400
    detalle = r.json()["detail"]
    assert "reserva_personal" in detalle and "200" in detalle
    assert _suscripciones(cliente.home)["chatgpt_plus"]["capacidad_ciclo"] == 1_000
    # y con las dos juntas si entra, sin pasar por un estado invalido
    r = cliente.post("/api/economia/suscripciones/chatgpt_plus/capacidad",
                     json={"capacidad_ciclo": 100, "reserva_personal": 20})
    assert r.status_code == 200, r.text
    fila = _suscripciones(cliente.home)["chatgpt_plus"]
    assert (fila["capacidad_ciclo"], fila["reserva_personal"]) == (100, 20)


def test_no_se_puede_dejar_la_cuota_agotada_a_mitad_de_ciclo(cliente):
    """El guardia que muerde HOY. `mercado.comprar_capacidad` corta con
    "cuota agotada" cuando `consumido + unidades > capacidad_fabrica`, y
    `consumido` se pliega de asientos ya escritos. Bajar la capacidad por
    debajo de lo que este ciclo YA compro no es corregir un numero: es
    apagar la fabrica hasta que el ciclo cierre, y de paso mandar
    `precio_unidad_mm` al tope (divide por `capacidad_fabrica`)."""
    from calipso.economia import capacidad as cap
    from calipso.economia import departamentos as d
    from calipso.economia.mercado import Mercado
    from calipso.economia.pagador import Pagador

    p = Pagador(cliente.home / "economia")
    m = p.mercado_fresco()
    m.k.acunar(TS, W, "dep:atlas", 400_000, t.SubtipoAcunacion.CAPITAL,
               {"tipo": "firma_pedro"})
    m.comprar_capacidad(TS, W, "dep:atlas", "chatgpt_plus", 300)

    r = cliente.post("/api/economia/suscripciones/chatgpt_plus/capacidad",
                     json={"capacidad_ciclo": 250, "reserva_personal": 20})
    assert r.status_code == 409, r.text
    assert "ya compro 300 unidades" in r.json()["detail"]
    assert _suscripciones(cliente.home)["chatgpt_plus"]["capacidad_ciclo"] == 1_000
    # por encima de lo consumido si entra: el guardia acota, no prohibe
    r = cliente.post("/api/economia/suscripciones/chatgpt_plus/capacidad",
                     json={"capacidad_ciclo": 400, "reserva_personal": 20})
    assert r.status_code == 200, r.text


def test_una_suscripcion_que_no_existe_da_404(cliente):
    r = cliente.post("/api/economia/suscripciones/gemini_pro/capacidad",
                     json={"capacidad_ciclo": 500})
    assert r.status_code == 404
