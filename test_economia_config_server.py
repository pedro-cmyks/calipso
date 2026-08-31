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


# --------------------------------------------------------------------------
# Los agujeros de la primera version, cada uno con su puerta
# --------------------------------------------------------------------------

def _comprar(cliente, unidades=300, semana=W, suscripcion="chatgpt_plus"):
    """La fabrica compra capacidad de verdad, para que el ciclo tenga
    consumo que defender."""
    from calipso.economia.pagador import Pagador

    p = Pagador(cliente.home / "economia")
    m = p.mercado_fresco()
    m.k.acunar(TS, semana, "dep:atlas", 400_000, t.SubtipoAcunacion.CAPITAL,
               {"tipo": "firma_pedro"})
    m.comprar_capacidad(TS, semana, "dep:atlas", suscripcion, unidades)


def test_el_guardia_del_ciclo_muerde_aunque_la_semana_no_este_abierta(
        cliente, monkeypatch):
    """El mismo cambio que da 409 el jueves entraba con 200 el lunes.

    El guardia miraba el consumo solo `if ops and semana in ops`, y una
    semana se vuelve operativa recien cuando alguien emite su PT -- un
    boton manual, sin ninguna rutina que lo apriete. O sea que TODA semana
    empieza con `semana not in ops`: no es una ventana rara, es el estado
    por defecto de cada lunes. Y la semana, cuando se abre, cae en el MISMO
    ciclo: el consumo de las anteriores sigue contando."""
    _comprar(cliente, 300)
    # jueves: la semana de hoy ya emitio su PT
    r = cliente.post("/api/economia/suscripciones/chatgpt_plus/capacidad",
                     json={"capacidad_ciclo": 250, "reserva_personal": 20})
    assert r.status_code == 409, r.text

    # lunes siguiente: mismo ciclo, misma peticion, PT todavia sin emitir
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, "2026-W36"))
    r = cliente.post("/api/economia/suscripciones/chatgpt_plus/capacidad",
                     json={"capacidad_ciclo": 250, "reserva_personal": 20})
    assert r.status_code == 409, r.text
    assert "ya compro 300 unidades" in r.json()["detail"]
    assert _suscripciones(cliente.home)["chatgpt_plus"]["capacidad_ciclo"] == 1_000


def test_el_consumido_que_ve_pedro_no_espera_al_boton_de_abrir(
        cliente, monkeypatch):
    """El numero que la pantalla dibuja como piso antes de tocar "aplicar"
    tiene que ser el mismo que va a mirar el guardia. Daba 0 durante toda
    la ventana en que la semana no estaba abierta."""
    _comprar(cliente, 300)
    monkeypatch.setattr(srv, "_eco_ahora", lambda: (TS, "2026-W36"))
    d = cliente.get("/api/economia/config").json()
    fila = next(s for s in d["suscripciones"] if s["nombre"] == "chatgpt_plus")
    assert fila["consumido_ciclo"] == 300


def test_una_capacidad_que_apaga_el_precio_no_entra(cliente):
    """`capacidad_ciclo` tenia piso (`ge=1`) y guardia hacia abajo, y nada
    hacia arriba: un numero de mas se aplicaba sin preguntar (por debajo
    del techo de plata el motor de permisos ni se entera), apagaba el
    precio por escasez y dejaba a la fabrica comprando capacidad que el
    plan no rinde -- cada compra estampada en el libro append-only con el
    precio equivocado. El techo no es inventado: pasado ese punto
    `precio_base_mm` no lo fija la division sino el `max(1, ...)`."""
    r = cliente.post("/api/economia/suscripciones/chatgpt_plus/capacidad",
                     json={"capacidad_ciclo": 800_000, "reserva_personal": 0})
    assert r.status_code == 400, r.text
    assert "menos de un milimon" in r.json()["detail"]
    assert _suscripciones(cliente.home)["chatgpt_plus"]["capacidad_ciclo"] == 1_000
    # y el motor de permisos no vio nada que autorizar: no se estaciono
    assert cliente.get("/api/permisos").json()["pendientes"] == []
    # el numero grande pero honesto si entra (20.000 mm de costo, una
    # unidad por milimon es el limite)
    r = cliente.post("/api/economia/suscripciones/chatgpt_plus/capacidad",
                     json={"capacidad_ciclo": 15_000, "reserva_personal": 0})
    assert r.status_code == 200, r.text


def test_una_escritura_cortada_no_deja_suscripciones_json_invalido(
        cliente, monkeypatch):
    """`write_text` trunca EN EL LUGAR: una escritura cortada a la mitad
    (disco lleno, kill) dejaba el json invalido y la economia ENTERA sin
    cargar -- y el unico arreglo era abrir el archivo con un editor, justo
    lo que este endpoint vino a eliminar."""
    import pathlib

    ruta = cliente.home / "economia" / "suscripciones.json"
    antes = ruta.read_text(encoding="utf-8")

    entero = pathlib.Path.write_text

    def cortado(self, data, *a, **kw):
        entero(self, data[:len(data) // 2], *a, **kw)
        raise OSError(27, "File too large")

    monkeypatch.setattr(pathlib.Path, "write_text", cortado)
    with pytest.raises(OSError):
        srv._eco_capacidad_ahora("chatgpt_plus", 500, 20)
    monkeypatch.undo()

    assert ruta.read_text(encoding="utf-8") == antes
    assert cliente.get("/api/economia/config").status_code == 200


def test_una_escritura_cortada_no_deja_departamentos_json_invalido(
        cliente, monkeypatch):
    """Gemelo del anterior sobre el otro archivo. `Registro._guardar` es
    ahora alcanzable N veces desde http (una por toque de perilla), y con
    `write_text` una escritura cortada dejaba departamentos.json invalido:
    `/api/economia/config`, `/api/economia/tablero` y `/api/economia/bus`
    revientan las tres, y tres de los seis departamentos desaparecen del
    archivo."""
    import pathlib

    ruta = cliente.home / "economia" / "departamentos.json"
    antes = ruta.read_text(encoding="utf-8")
    registro = deps.Registro(ruta)

    entero = pathlib.Path.write_text

    def cortado(self, data, *a, **kw):
        entero(self, data[:len(data) // 2], *a, **kw)
        raise OSError(27, "File too large")

    monkeypatch.setattr(pathlib.Path, "write_text", cortado)
    with pytest.raises(OSError):
        registro.ajustar("atlas", techo_preseed_mm=5_000)
    monkeypatch.undo()

    assert ruta.read_text(encoding="utf-8") == antes
    assert deps.Registro(ruta).obtener("atlas").techo_preseed_mm == 0
    assert cliente.get("/api/economia/config").status_code == 200


def test_sembrar_valida_los_rangos_igual_que_las_perillas(cliente):
    """Media puerta no es una puerta: los mismos numeros que el endpoint de
    perillas rechaza con 422 los escribia el sembrado con 200 -- y peor,
    porque sembrar es de escritura unica: el departamento nacia fuera del
    rango que la otra puerta define."""
    for perilla, valor in (("presupuesto_semanal_mm", -100_000),
                           ("explorar_explotar_pct", 900),
                           ("agresividad_pct", -50),
                           ("techo_preseed_mm", -1)):
        r = cliente.post("/api/economia/sembrar", json={
            "departamentos": [{"nombre": "raro", "zona": "fabrica",
                               perilla: valor}]})
        assert r.status_code == 422, (perilla, r.text)


def test_las_perillas_rechazan_booleanos_y_claves_que_no_son_perillas(cliente):
    """`true` colaba como 1 (pydantic en modo lax), un entero de 401
    digitos se persistia tal cual, y `nombre`/`zona` -- que el docstring
    dice que NO acepta -- se descartaban en silencio con 200: quien los
    mandaba se iba creyendo que movio la cuenta de un departamento."""
    for cuerpo in ({"techo_preseed_mm": True},
                   {"techo_preseed_mm": 10 ** 400},
                   {"nombre": "otro", "techo_preseed_mm": 1},
                   {"zona": "personal"}):
        r = cliente.post("/api/economia/departamentos/atlas/perillas",
                         json=cuerpo)
        assert r.status_code == 422, (cuerpo, r.text)
    assert _departamentos(cliente.home)["atlas"]["techo_preseed_mm"] == 0


def test_el_techo_de_preseed_no_es_una_perilla_de_la_zona_personal(cliente):
    """Un departamento personal no tiene jefe que pida ni ronda que
    financiar: `bus.financiar` rechaza un pre-seed cuyo dueno no sea de
    fabrica. La perilla ahi seria un numero que no autoriza nada."""
    r = deps.Registro(cliente.home / "economia" / "departamentos.json")
    r.alta(deps.Departamento("pedro_personal", deps.ZONA_PERSONAL))
    resp = cliente.post("/api/economia/departamentos/pedro_personal/perillas",
                        json={"techo_preseed_mm": 999_999})
    assert resp.status_code == 400, resp.text
    assert "perilla de fabrica" in resp.json()["detail"]
    assert _departamentos(cliente.home)["pedro_personal"]["techo_preseed_mm"] == 0
    # las otras perillas de un personal siguen entrando
    assert cliente.post("/api/economia/departamentos/pedro_personal/perillas",
                        json={"explorar_explotar_pct": 20}).status_code == 200


# -- el segundo techo del pre-seed: el acumulado por CICLO -----------------

def test_el_techo_del_ciclo_se_cambia_por_el_mismo_endpoint(cliente):
    """La perilla nueva tiene que poder moverse sin editar el json, igual
    que la otra: si no, el techo del ciclo seria un numero que solo existe
    para quien abra departamentos.json en un editor."""
    r = cliente.post("/api/economia/departamentos/atlas/perillas",
                     json={"techo_preseed_mm": 50_000,
                           "techo_preseed_ciclo_mm": 150_000})
    assert r.status_code == 200, r.text
    d = _departamentos(cliente.home)["atlas"]
    assert d["techo_preseed_mm"] == 50_000
    assert d["techo_preseed_ciclo_mm"] == 150_000
    # y se puede volver a cerrar la canilla, que es para lo que el cero
    # tiene que seguir siendo un valor legitimo
    assert cliente.post("/api/economia/departamentos/atlas/perillas",
                        json={"techo_preseed_ciclo_mm": 0}).status_code == 200
    assert _departamentos(cliente.home)["atlas"]["techo_preseed_ciclo_mm"] == 0


def test_el_techo_del_ciclo_tiene_la_misma_puerta_de_rango(cliente):
    """Media puerta no es una puerta: los booleanos, los negativos y los
    enteros que no sobreviven el viaje por JavaScript se rechazan igual que
    en la perilla hermana."""
    for cuerpo in ({"techo_preseed_ciclo_mm": True},
                   {"techo_preseed_ciclo_mm": -1},
                   {"techo_preseed_ciclo_mm": 10 ** 400}):
        r = cliente.post("/api/economia/departamentos/atlas/perillas",
                         json=cuerpo)
        assert r.status_code == 422, (cuerpo, r.text)
    r = cliente.post("/api/economia/sembrar", json={
        "departamentos": [{"nombre": "raro", "zona": "fabrica",
                           "techo_preseed_ciclo_mm": -1}]})
    assert r.status_code == 422, r.text


def test_el_techo_del_ciclo_tampoco_es_una_perilla_de_la_zona_personal(cliente):
    """Misma razon que su hermana: un departamento personal no tiene ronda
    pre-seed que financiar (`bus.financiar` la rechaza), asi que un techo
    ahi seria un numero que no acota nada."""
    r = deps.Registro(cliente.home / "economia" / "departamentos.json")
    r.alta(deps.Departamento("pedro_personal", deps.ZONA_PERSONAL))
    resp = cliente.post("/api/economia/departamentos/pedro_personal/perillas",
                        json={"techo_preseed_ciclo_mm": 999_999})
    assert resp.status_code == 400, resp.text
    assert _departamentos(
        cliente.home)["pedro_personal"]["techo_preseed_ciclo_mm"] == 0


def test_la_config_muestra_el_acumulado_del_ciclo_al_lado_del_techo(cliente):
    """La mitad que faltaba: la mesa muestra cada pedido suelto y ninguna
    pantalla decia cuanto capital ya entro. Sin el acumulado a la vista,
    el techo del ciclo es un numero que Pedro pone a ciegas y un rechazo
    que le llega recien al tocar "financiar"."""
    from calipso.economia import bus as bus_mod
    from calipso.economia import mercado as mkt

    d = cliente.get("/api/economia/config").json()
    atlas = [x for x in d["departamentos"] if x["nombre"] == "atlas"][0]
    assert atlas["techo_preseed_ciclo_mm"] == 0
    assert atlas["preseed_ventana_mm"] == 0

    cliente.post("/api/economia/departamentos/atlas/perillas",
                 json={"techo_preseed_mm": 80_000,
                       "techo_preseed_ciclo_mm": 200_000})
    eco = cliente.home / "economia"
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    b = bus_mod.Bus(eco / "bus.jsonl")
    b.alta(TS, W, "ps1", "dep:atlas", "arranco", 80_000, 80_000,
           {"gasto_max_mm": 80_000}, tipo="preseed")
    bus_mod.financiar(mkt.Mercado(k, r, {}), b, TS, W, "ps1", t.TESORO, 80_000)

    d2 = cliente.get("/api/economia/config").json()
    atlas2 = [x for x in d2["departamentos"] if x["nombre"] == "atlas"][0]
    assert atlas2["preseed_ventana_mm"] == 80_000
    assert atlas2["techo_preseed_ciclo_mm"] == 200_000


def test_sembrar_tampoco_deja_poner_el_techo_de_preseed_en_lo_personal(cliente,
                                                                       tmp_path):
    """La guardia de zona estaba de un lado solo. `POST .../perillas`
    rechazaba las dos perillas de pre-seed en un departamento personal con
    400; `POST /api/economia/sembrar` las escribia con 200 -- y sembrar es
    de ESCRITURA UNICA, asi que el departamento nacia con un techo que no
    autoriza nada y no habia forma de sacarlo salvo editando el json.

    Y el numero ahi no es inofensivo: `jefe._puede` y `_contratar_para` no
    miran la zona, asi que el jefe de un personal con las dos perillas
    puestas PUBLICA pedidos que `bus.financiar` rechaza siempre ("un
    pre-seed es capital de fabrica"). La bandeja de Pedro se llena de
    propuestas impagables y se le come TECHO_PROPUESTAS: exactamente el mal
    que el techo del ciclo existe para evitar.

    Por eso la guardia bajo al dominio (`Departamento.__post_init__`) en
    vez de duplicarse en el segundo endpoint: es un invariante del
    departamento, y dos puertas que hay que acordarse de cerrar de a una
    ya demostraron que se cierra una sola."""
    import calipso.server as srv

    home = tmp_path / "otra"
    (home / "economia").mkdir(parents=True)
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(srv, "_ECO_BASE", home)
    monkeypatch.setenv("CALIPSO_HOME", str(home))
    c = TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})
    try:
        for perilla in ("techo_preseed_mm", "techo_preseed_ciclo_mm"):
            r = c.post("/api/economia/sembrar", json={
                "departamentos": [{"nombre": "atlas", "zona": "fabrica"},
                                  {"nombre": "yo", "zona": "personal",
                                   perilla: 999_999}],
                "suscripciones": {}})
            assert r.status_code == 400, (perilla, r.text)
            assert "perilla de fabrica" in r.json()["detail"]
            # y no escribio NADA: sembrar valida todo en memoria antes
            assert not (home / "economia" / "departamentos.json").exists()
        # el mismo sembrado sin la perilla entra
        r = c.post("/api/economia/sembrar", json={
            "departamentos": [{"nombre": "atlas", "zona": "fabrica",
                               "techo_preseed_ciclo_mm": 999_999},
                              {"nombre": "yo", "zona": "personal"}],
            "suscripciones": {}})
        assert r.status_code == 200, r.text
    finally:
        monkeypatch.undo()


def test_la_config_muestra_lo_pedido_y_sin_financiar_al_lado_del_acumulado(
        cliente):
    """El acumulado del ciclo y lo pedido en pie NO son el mismo numero, y
    la pantalla los decia como si lo fueran: la nota prometia que el techo
    del ciclo contaba "lo que ya financiaste mas lo que sigue en la mesa"
    -- esa es la regla del JEFE (`jefe._puede`) -- pegada a un
    acumulado que sale de `preseed_ventana_mm` y cuenta solo lo
    financiado, igual que el freno de `bus.financiar`.

    Con un pedido olvidado en la mesa el bloque se leia
    "entro ...: 0 de 60.000" con 60.000 reservados, el jefe mudo
    y nada que sugiriera que descartar es lo unico que lo suelta."""
    from calipso.economia import bus as bus_mod

    cliente.post("/api/economia/departamentos/atlas/perillas",
                 json={"techo_preseed_mm": 150_000,
                       "techo_preseed_ciclo_mm": 60_000})
    b = bus_mod.Bus(cliente.home / "economia" / "bus.jsonl")
    b.alta(TS, W, "ps1", "dep:atlas", "arranco", 60_000, 60_000,
           {"gasto_max_mm": 60_000}, tipo="preseed")
    atlas = [x for x in cliente.get("/api/economia/config").json()
             ["departamentos"] if x["nombre"] == "atlas"][0]
    assert atlas["preseed_ventana_mm"] == 0, "no se financio nada todavia"
    assert atlas["preseed_pendiente_mm"] == 60_000

    # descartar lo suelta, y la pantalla lo tiene que reflejar
    bus_mod.descartar(bus_mod.Bus(cliente.home / "economia" / "bus.jsonl"),
                      TS, W, "ps1")
    atlas2 = [x for x in cliente.get("/api/economia/config").json()
              ["departamentos"] if x["nombre"] == "atlas"][0]
    assert atlas2["preseed_pendiente_mm"] == 0

    # y un trabajo comun no cuenta: la reserva es del pre-seed
    b2 = bus_mod.Bus(cliente.home / "economia" / "bus.jsonl")
    b2.alta(TS, W, "t1", "dep:atlas", "un trabajo", 10_000, 30_000,
            {"gasto_max_mm": 10_000})
    atlas3 = [x for x in cliente.get("/api/economia/config").json()
              ["departamentos"] if x["nombre"] == "atlas"][0]
    assert atlas3["preseed_pendiente_mm"] == 0
