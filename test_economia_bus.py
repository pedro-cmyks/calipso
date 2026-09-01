"""Tests del bus de propuestas: eventos, financiacion, muerte y liquidacion."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import mercado as mkt
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"
W = "2026-W30"

SUS = cap.Suscripcion(nombre="claude_max", costo_mensual_mm=100_000,
                      capacidad_ciclo=1_000, reserva_personal=200,
                      costo_api_mm_por_unidad=500)


@pytest.fixture
def entorno(tmp_path):
    k = Kernel(Libro(tmp_path / "libro.jsonl"))
    r = deps.Registro(tmp_path / "departamentos.json")
    # LAS DOS perillas de pre-seed porque `financiar` relee las dos al
    # PAGAR una ronda: la de hoy es la que autoriza, no la que estaba
    # cuando el pedido se publico. `techo_preseed_ciclo_mm` bien alto para
    # que no sea el que corta en los tests que miran el otro techo; el que
    # lo prueba a el lo baja a proposito.
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA, techo_api_ciclo_mm=500_000,
                             techo_preseed_mm=200_000,
                             techo_preseed_ciclo_mm=10_000_000))
    r.alta(deps.Departamento("b", deps.ZONA_FABRICA, techo_api_ciclo_mm=500_000))
    m = mkt.Mercado(k, r, {"claude_max": SUS})
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    return k, m, b


def _capital(k, monto, destino):
    k.acunar(TS, "2026-W30", destino, monto, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})


def _semana_op(k, semana):
    pt.emitir_semana(k, TS, semana, 4_000, 0)
    pt.expirar_pools(k, TS, semana)


CRITERIO = {"gasto_max_mm": 50_000}


def test_alta_estado_y_persistencia(tmp_path, entorno):
    k, m, b = entorno
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar vertical x",
           presupuesto_mm=100_000, retorno_mm=300_000, criterio=CRITERIO)
    assert b.estado("p1") == "alta"
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "p1", "dep:a", "repetida", 1, 1, CRITERIO)
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "p2", "dep:a", "sin criterio", 1, 1, {})
    b2 = bus_mod.Bus(tmp_path / "bus.jsonl")
    assert b2.estado("p1") == "alta"
    with pytest.raises(bus_mod.ErrorBus):
        b2.estado("fantasma")


def test_alta_valida_valores(entorno):
    k, m, b = entorno
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "v1", "dep:a", "malo", 100_000, 300_000,
               {"gasto_max_mm": "abc"})
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "v2", "dep:a", "malo", 100_000, 300_000,
               {"semanas_max": -5})
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "v3", "dep:a", "malo", 0, 300_000,
               {"gasto_max_mm": 50_000})


def test_financiar_transfiere_y_marca(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    _capital(k, 100_000, "dep:b")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 60_000)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:b", 40_000)  # cofinancia
    assert b.estado("p1") == "financiada"
    assert b.datos("p1")["semana_financiada"] == "2026-W30"
    asientos = k.libro.asientos()
    assert k.saldo("trabajo:p1") == 100_000
    assert bus_mod.aportes(asientos, "p1") == {"dep:a": 60_000, "dep:b": 40_000}


def test_no_se_financia_propuesta_de_congelado(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:b")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    deps.declarar_quiebra(k, TS, "2026-W30", "dep:a")
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:b", 10_000)


def test_gastado_pliega_todas_las_salidas(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 80_000)
    # el trabajo gasta por la puerta del Mercado, con dueno explicito
    m.gastar_api(TS, "2026-W30", "trabajo:p1", 20_000, ref="trabajo:p1",
                 dueno="dep:a")
    m.comprar_capacidad(TS, "2026-W30", "trabajo:p1", "claude_max", 50,
                        ref="trabajo:p1", dueno="dep:a")  # 50 u a 100 = 5_000
    assert bus_mod.gastado(k.libro.asientos(), "p1") == 25_000


def test_muere_por_gasto_y_liquida_proporcional(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    _capital(k, 100_000, "dep:b")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000,
           {"gasto_max_mm": 25_000})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 60_000)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:b", 40_000)
    k.destruir(TS, "2026-W30", "trabajo:p1", 30_000, motivo="api",
               ref="trabajo:p1")  # 30k > 25k: muerto
    muertos = bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W30")
    assert muertos == ["p1"]
    assert b.estado("p1") == "liquidada"
    assert k.saldo("trabajo:p1") == 0
    # saldo 70k proporcional a aportes 60/40: a 42k, b 28k
    assert k.saldo("dep:a") == 100_000 - 60_000 + 42_000
    assert k.saldo("dep:b") == 100_000 - 40_000 + 28_000


def test_muere_por_semanas(entorno):
    k, m, b = entorno
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]:
        _semana_op(k, sem)
    _capital(k, 50_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 50_000, 100_000,
           {"semanas_max": 2})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 30_000)
    assert bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W32") == []
    assert bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W33") == ["p1"]
    assert k.saldo("dep:a") == 50_000  # todo devuelto: no gasto nada


def test_tesoro_no_financia_sin_mandato(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.financiar(m, b, TS, "2026-W30", "p1",
                          financiador_cuenta=t.TESORO, mm=10_000)


def test_financiar_exige_semana_operativa(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.financiar(m, b, TS, "2026-W99", "p1", "dep:a", 10_000)


def test_liquidacion_reanudable(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000,
           {"gasto_max_mm": 25_000})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 50_000)
    k.destruir(TS, "2026-W30", "trabajo:p1", 30_000, motivo="api",
               ref="trabajo:p1")  # 30k > 25k: muerto
    muertos = bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W30")
    assert muertos == ["p1"]
    assert b.estado("p1") == "liquidada"
    assert k.saldo("trabajo:p1") == 0
    saldo_a = k.saldo("dep:a")
    # segunda pasada: idempotente, ya no esta "financiada" asi que no
    # vuelve a intentar transferir ni a re-marcar.
    assert bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W30") == []
    assert k.saldo("dep:a") == saldo_a


def test_marcar_transiciones_ilegales(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000,
           {"gasto_max_mm": 10_000})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 50_000)
    b.marcar(TS, "2026-W30", "p1", "muerta")
    b.marcar(TS, "2026-W30", "p1", "liquidada")
    with pytest.raises(bus_mod.ErrorBus):
        b.marcar(TS, "2026-W30", "p1", "financiada")  # sobre una liquidada
    b.alta(TS, "2026-W30", "p2", "dep:a", "radar2", 50_000, 100_000,
           {"gasto_max_mm": 10_000})
    bus_mod.financiar(m, b, TS, "2026-W30", "p2", "dep:a", 20_000)
    with pytest.raises(bus_mod.ErrorBus):
        b.marcar(TS, "2026-W30", "p2", "liquidada")  # salta "muerta"


def test_alta_valida_id(entorno):
    k, m, b = entorno
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "", "dep:a", "malo", 1, 1, CRITERIO)
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "trabajo:p1", "dep:a", "malo", 1, 1, CRITERIO)


def test_vivo_no_se_liquida(entorno):
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 50_000, 100_000,
           {"gasto_max_mm": 25_000})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 30_000)
    k.destruir(TS, "2026-W30", "trabajo:p1", 10_000, motivo="api",
               ref="trabajo:p1")
    assert bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W30") == []
    assert b.estado("p1") == "financiada"


def test_una_propuesta_en_alta_se_puede_descartar(entorno):
    """Sin esto, una propuesta que Pedro no quiere no tiene salida, y el jefe
    se frena para siempre al llegar a su techo de propuestas."""
    k, m, b = entorno
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.descartar(b, TS, "2026-W30", "p1")
    assert b.estado("p1") == "descartada"


def test_descartada_es_terminal(entorno):
    k, m, b = entorno
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.descartar(b, TS, "2026-W30", "p1")
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.descartar(b, TS, "2026-W30", "p1")
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 1_000)


def test_una_financiada_no_se_puede_descartar(entorno):
    """Ahi ya hay plata en trabajo:<id>, y devolverla prorrateada es trabajo
    de evaluar_y_liquidar_muertos, no de una marca cruda."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 50_000)
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.descartar(b, TS, "2026-W30", "p1")


def test_descartar_no_mueve_el_libro(entorno):
    """Nada se transfiere a trabajo:<id> hasta que alguien financia, asi que
    descartar no tiene plata que devolver."""
    k, m, b = entorno
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    antes = len(k.libro.asientos())
    bus_mod.descartar(b, TS, "2026-W30", "p1")
    assert len(k.libro.asientos()) == antes


# -- pre-seed: la ronda con la que arranca un departamento ------------------
#
# Un pre-seed es una propuesta de `tipo="preseed"`: no se financia contra la
# billetera de otro departamento sino contra el tesoro, y la plata cae en la
# cuenta DEL DEPARTAMENTO dueno, no en trabajo:<id> -no produce un trabajo,
# produce capital.


def test_alta_default_tipo_trabajo(entorno):
    """El default no rompe a nadie que ya llamaba `alta` sin `tipo`."""
    k, m, b = entorno
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    assert b.datos("p1")["tipo"] == "trabajo"


def test_alta_valida_tipo(entorno):
    k, m, b = entorno
    with pytest.raises(bus_mod.ErrorBus):
        b.alta(TS, "2026-W30", "p1", "dep:a", "malo", 1, 1, CRITERIO,
              tipo="capital")


def test_financiar_preseed_va_a_la_cuenta_del_departamento(entorno):
    """La plata del pre-seed no toca trabajo:<id>: cae directo en la cuenta
    del departamento, porque no financia un trabajo, financia el arranque."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 200_000, t.TESORO)
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco de cero", 150_000,
          150_000, {"gasto_max_mm": 150_000}, tipo="preseed")
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 150_000)
    # y queda CERRADA en el acto: la plata ya cayo, no hay nada mas que
    # decidir sobre este pedido y no tiene que seguir ocupando la mesa
    assert b.estado("p1") == "cerrada"
    assert k.saldo("dep:a") == 150_000
    assert k.saldo(bus_mod.cuenta_trabajo("p1")) == 0
    assert bus_mod.aportes(k.libro.asientos(), "p1") == {}


def test_preseed_no_se_financia_con_billetera_de_departamento(entorno):
    """Solo el tesoro financia un pre-seed: la billetera de otro
    departamento no es de donde sale la ronda pre-seed."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 200_000, "dep:b")
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco de cero", 150_000,
          150_000, {"gasto_max_mm": 150_000}, tipo="preseed")
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:b", 150_000)


def test_trabajo_no_se_financia_con_tesoro_pero_preseed_si(entorno):
    """La misma cuenta (tesoro) es invalida para un `trabajo` y es la UNICA
    valida para un `preseed`: el tipo, no la cuenta, decide la puerta."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, t.TESORO)
    b.alta(TS, "2026-W30", "trabajo1", "dep:a", "radar", 100_000, 300_000,
          CRITERIO)  # tipo="trabajo" por default
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.financiar(m, b, TS, "2026-W30", "trabajo1", t.TESORO, 10_000)
    b.alta(TS, "2026-W30", "preseed1", "dep:a", "arranco", 100_000, 100_000,
          {"gasto_max_mm": 100_000}, tipo="preseed")
    bus_mod.financiar(m, b, TS, "2026-W30", "preseed1", t.TESORO, 100_000)
    assert b.estado("preseed1") == "cerrada"


def test_preseed_no_tiene_ciclo_de_muerte(entorno):
    """Un pre-seed financiado no abre trabajo:<id>, asi que no hay gasto que
    medir contra el criterio de muerte ni liquidacion que hacer: se cierra
    al pagarse -no es un trabajo en curso, y por eso tampoco queda en
    `activas()` esperando una muerte que no le puede llegar."""
    k, m, b = entorno
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]:
        _semana_op(k, sem)
    _capital(k, 100_000, t.TESORO)
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco", 100_000, 100_000,
          {"semanas_max": 1}, tipo="preseed")
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 100_000)
    assert bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W33") == []
    assert b.estado("p1") == "cerrada"
    assert b.activas() == []
    assert k.saldo("dep:a") == 100_000


def test_preseed_no_cuenta_para_el_mandato_de_direccion(entorno):
    """direccion.asignado_semana suma solo motivo == "presupuesto": un
    pre-seed usa su propio motivo y no cuenta contra el umbral del mandato
    -un pre-seed no es presupuesto semanal."""
    from calipso.economia import direccion
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, t.TESORO)
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco", 100_000, 100_000,
          {"gasto_max_mm": 100_000}, tipo="preseed")
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 100_000)
    assert direccion.asignado_semana(k.libro.asientos(), "dep:a",
                                     "2026-W30") == 0


# --------------------------------------------------------------------------
# La ronda pre-seed, con sus tres puertas: de quien es, cuanto, y hasta
# cuando sigue en la mesa.
# --------------------------------------------------------------------------

def test_el_tesoro_no_financia_un_preseed_de_la_zona_personal(entorno):
    """La rama de trabajo tiene puerta de zona sobre el FINANCIADOR; la de
    pre-seed no tenia ninguna sobre el DUENO, asi que el tesoro terminaba
    financiando directo una billetera `personal:` -- por encima de
    `cuenta_pedro.financiar_personal`, que existe para exigir lo contrario.
    Y el efecto no es cosmetico: `mercado.comprar_capacidad` le cobra a un
    departamento personal contra la reserva personal de la suscripcion, y
    `pagador.cargar_api` ignora por completo las cuentas `personal:*`."""
    k, m, b = entorno
    # sin `techo_preseed_mm`: ese techo ya no se puede poner en una zona
    # personal (`Departamento.__post_init__` lo rechaza, que es la puerta
    # que le faltaba a `POST /api/economia/sembrar`). No hace falta para
    # este test y nunca hizo: la puerta de zona de `financiar` corre ANTES
    # de leer la perilla, asi que lo que el docstring protege se sigue
    # ejercitando igual -- y la propuesta puede existir en el bus sin
    # ninguna perilla, porque `bus.alta` no mira el registro.
    m.registro.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    _semana_op(k, "2026-W30")
    _capital(k, 400_000, t.TESORO)
    b.alta(TS, "2026-W30", "ps1", "personal:finanzas", "arranco", 400_000,
           400_000, {"gasto_max_mm": 400_000}, tipo="preseed")
    with pytest.raises(bus_mod.ErrorBus) as exc:
        bus_mod.financiar(m, b, TS, "2026-W30", "ps1", t.TESORO, 400_000)
    assert "cuenta_pedro" in str(exc.value)
    assert k.saldo("personal:finanzas") == 0


def test_un_preseed_no_se_paga_por_mas_de_lo_que_pide(entorno):
    """`financiar` no comparaba `mm` contra NADA. Un pedido publicado por
    50.000 -recortado por la perilla, que es toda la gracia del recorte- se
    pagaba por 4.000.000 sin una queja, y esa plata se quedaba para siempre
    en la billetera del departamento: un pre-seed no abre `trabajo:<id>` y
    `evaluar_y_liquidar_muertos` no lo liquida nunca."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 4_000_000, t.TESORO)
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    with pytest.raises(bus_mod.ErrorBus) as exc:
        bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 4_000_000)
    assert "mas de lo autorizado" in str(exc.value)
    assert k.saldo("dep:a") == 0
    # por el monto que pide, si
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 50_000)
    assert k.saldo("dep:a") == 50_000


def test_bajar_la_perilla_a_cero_tambien_frena_lo_que_ya_esta_en_la_bandeja(entorno):
    """El techo se aplicaba una sola vez, al publicar; despues el monto
    vivia en el bus y nadie lo volvia a comparar contra la perilla de hoy.
    "En cero no pide" era cierto para los pedidos nuevos y falso para los
    viejos: el gesto de "me arrepenti, cerra la canilla" no cerraba."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 400_000, t.TESORO)
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco", 200_000, 200_000,
           {"gasto_max_mm": 200_000}, tipo="preseed")
    m.registro.ajustar("a", techo_preseed_mm=0)
    with pytest.raises(bus_mod.ErrorBus) as exc:
        bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 200_000)
    assert "no tiene techo de pre-seed" in str(exc.value)
    assert k.saldo("dep:a") == 0
    # y si Pedro la baja a la mitad, se paga hasta la mitad
    m.registro.ajustar("a", techo_preseed_mm=80_000)
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 200_000)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 80_000)
    assert k.saldo("dep:a") == 80_000


def test_un_preseed_financiado_no_queda_como_trabajo_vivo(entorno):
    """`activas()` es de donde `mapa/ciudad` y `prompt_compiler` sacan los
    trabajos en curso. Un pre-seed financiado se quedaba ahi para siempre
    -`financiada` es terminal para el, `evaluar_y_liquidar_muertos` lo
    saltea y `descartar` solo acepta `alta`- asi que cada ronda que Pedro
    aprobaba sumaba una unidad fantasma en el mapa y un proyecto fantasma
    en el contexto del chat, los dos con gasto cero eterno porque la cuenta
    `trabajo:<id>` no existe."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 400_000, t.TESORO)
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco", 150_000, 150_000,
           {"gasto_max_mm": 150_000}, tipo="preseed")
    b.alta(TS, "2026-W30", "t1", "dep:a", "un trabajo de verdad", 10_000,
           30_000, CRITERIO)
    _capital(k, 50_000, "dep:b")
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 150_000)
    bus_mod.financiar(m, b, TS, "2026-W30", "t1", "dep:b", 10_000)
    # el trabajo si, el pre-seed no
    assert b.activas() == ["t1"]
    assert b.estado("p1") == "cerrada"


# -- el segundo techo del pre-seed: el acumulado por CICLO -----------------

def test_el_techo_del_ciclo_frena_la_segunda_ronda(entorno):
    """EL CASO QUE SOLO ESTE TECHO ATRAPA. Con el techo por pedido en
    50.000 y la bandeja despejada, un jefe publica 50.000 tres veces antes
    de chocar `TECHO_PROPUESTAS`, y las tres pasan el freno del jefe si se
    publicaron cuando todavia habia lugar. Dos pedidos EN PIE se financian
    uno tras otro y cruzan el techo entre los dos: lo pedido lo puede
    frenar el jefe, lo financiado solo se puede frenar aca, que es el
    unico lugar por donde la plata sale de verdad."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 1_000_000, t.TESORO)
    m.registro.ajustar("a", techo_preseed_mm=50_000,
                       techo_preseed_ciclo_mm=80_000)
    for i in (1, 2):
        b.alta(TS, "2026-W30", f"p{i}", "dep:a", f"ronda {i}", 50_000, 50_000,
               {"gasto_max_mm": 50_000}, tipo="preseed")

    # la primera entra entera: 50.000 <= 80.000
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 50_000)
    assert k.saldo("dep:a") == 50_000

    # la segunda no: 50.000 + 50.000 pasa el techo del ciclo
    with pytest.raises(bus_mod.ErrorBus) as exc:
        bus_mod.financiar(m, b, TS, "2026-W30", "p2", t.TESORO, 50_000)
    assert "techo de pre-seed superado" in str(exc.value)
    assert "ultimas 4 semanas operativas" in str(exc.value)
    assert k.saldo("dep:a") == 50_000, "cruzo el techo acumulado"

    # lo que entra en lo que queda, si: el techo acota, no prohibe
    bus_mod.financiar(m, b, TS, "2026-W30", "p2", t.TESORO, 30_000)
    assert k.saldo("dep:a") == 80_000


def test_el_techo_del_ciclo_ata_a_pedro_y_la_salida_es_subir_la_perilla(entorno):
    """Un techo que Pedro puede cruzar sin enterarse no es un techo, pero
    Pedro es el dueno: la salida existe y es EXPLICITA -- subir la perilla,
    que queda escrita en departamentos.json. Una sola fuente de verdad y
    ningun override silencioso."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 1_000_000, t.TESORO)
    m.registro.ajustar("a", techo_preseed_ciclo_mm=60_000)
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco", 100_000, 100_000,
           {"gasto_max_mm": 100_000}, tipo="preseed")
    with pytest.raises(bus_mod.ErrorBus) as exc:
        bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 100_000)
    assert "subi la perilla" in str(exc.value)

    m.registro.ajustar("a", techo_preseed_ciclo_mm=100_000)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 100_000)
    assert k.saldo("dep:a") == 100_000


def test_sin_techo_de_ciclo_no_se_paga_ninguna_ronda(entorno):
    """Cero es "todavia no", no "sin limite" -- la misma regla que
    `techo_preseed_mm` y que `techo_api_ciclo_mm` (que en cero manda todo
    gasto de API a la compuerta c). Un default que autoriza algo es
    exactamente como un techo se cruza en silencio."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 400_000, t.TESORO)
    m.registro.ajustar("a", techo_preseed_ciclo_mm=0)
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco", 10_000, 10_000,
           {"gasto_max_mm": 10_000}, tipo="preseed")
    with pytest.raises(bus_mod.ErrorBus) as exc:
        bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 10_000)
    assert "techo de pre-seed acumulado" in str(exc.value)
    assert k.saldo("dep:a") == 0


def test_el_techo_del_ciclo_se_suelta_al_ciclo_siguiente(entorno):
    """Es un techo POR VENTANA, no un tope de por vida: pasadas cuatro
    semanas operativas desde la que consumio el cupo, el acumulado vuelve a
    cero y el departamento puede volver a pedir. Eso es lo que hace que la
    decision de Pedro sea periodica y no definitiva.

    El test sobrevivio al cambio de ventana fija a deslizante sin tocar una
    sola asercion, y eso es el punto: lo que cambio no es CUANTO dura el
    cupo (cuatro semanas operativas, antes y ahora) sino DESDE CUANDO se
    cuenta. Con la fija se contaba desde el borde del ciclo, y por eso el
    borde dejaba pasar el doble.

    Las semanas se abren EN ORDEN y no las cinco de una: la ronda 1 se paga
    en W30 cuando W30 es la ultima operativa, que es lo que pasa en la
    maquina de Pedro (`api_eco_bus_financiar` fecha con `_eco_ahora`).
    Abrirlas todas antes y recien despues pagar en W30 era una comodidad
    del armado, y desde que el vencimiento se mide con `ventana_pagable`
    es ademas el gesto que este arreglo prohibe: pagar en una semana vieja
    un pedido que la ventana de hoy ya dejo atras. Lo que el test mide -- que
    el cupo vuelve cuatro semanas operativas despues-- es lo mismo."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 1_000_000, t.TESORO)
    m.registro.ajustar("a", techo_preseed_mm=50_000,
                       techo_preseed_ciclo_mm=50_000)
    b.alta(TS, "2026-W30", "p1", "dep:a", "ronda 1", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 50_000)
    for w in ("2026-W31", "2026-W32", "2026-W33", "2026-W34"):
        _semana_op(k, w)

    # misma ventana: agotado
    b.alta(TS, "2026-W33", "p2", "dep:a", "ronda 2", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.financiar(m, b, TS, "2026-W33", "p2", t.TESORO, 50_000)

    # W34: la ventana de hoy es W31..W34 y W30 ya salio, asi que el
    # acumulado esta en cero. (Con la ventana fija el motivo era otro -- se
    # abria el ciclo 1 -- y el mismo motivo era el que dejaba pasar el
    # doble un dia antes; ver `test_la_ventana_deslizante_frena_la_rafaga`.)
    bus_mod.financiar(m, b, TS, "2026-W34", "p2", t.TESORO, 50_000)
    assert k.saldo("dep:a") == 100_000


def test_el_acumulado_del_ciclo_solo_cuenta_pre_seed(entorno):
    """`preseed_en_ventana` mira `motivo == "preseed"` y no todo lo que
    entra a la cuenta: un rescate o el cobro de un servicio vendido a otro
    departamento no son capital de arranque, y contarlos frenaria rondas
    por plata que no vino del tesoro."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 1_000_000, t.TESORO)
    _capital(k, 300_000, "dep:b")
    m.registro.ajustar("a", techo_preseed_mm=50_000,
                       techo_preseed_ciclo_mm=50_000)
    # b le vende un servicio a a: entra plata que NO es pre-seed
    m.vender_servicio(TS, "2026-W30", "dep:b", "dep:a", 300_000)
    assert k.saldo("dep:a") == 300_000

    semanas = bus_mod.ventana_preseed(
        cap.semanas_operativas(k.libro.asientos()), "2026-W30")
    assert bus_mod.preseed_en_ventana(
        k.libro.asientos(), "dep:a", semanas) == 0

    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 50_000)
    assert bus_mod.preseed_en_ventana(
        k.libro.asientos(), "dep:a", semanas) == 50_000


# -- la ventana DESLIZANTE: el agujero que dejaba entrar 2x el techo -------

def test_la_ventana_deslizante_frena_la_rafaga_del_doble(entorno):
    """EL DEFECTO. El techo acumulado se medía sobre el ciclo de
    facturacion, que es una ventana FIJA (`ops[c*4:(c+1)*4]`): el acumulado
    no decaia, se reseteaba de golpe al abrirse la quinta semana operativa.
    Financiar el techo entero en la ultima semana del ciclo N y otra vez en
    la primera del N+1 metia 2x el techo en dos semanas de CALENDARIO
    seguidas -- exactamente la rafaga que el techo existe para impedir,
    porque la perilla esta para acotar cuanto capital entra antes de que
    Pedro tenga que volver a decidir a conciencia.

    Con la ventana deslizante el invariante vale siempre y no solo en los
    bordes del ciclo: en ninguna corrida de cuatro semanas operativas entra
    mas que el techo. Y no es un bloqueo perpetuo -- la ultima parte del
    test: el cupo vuelve cuando la semana que lo consumio sale por atras."""
    k, m, b = entorno
    for w in ("2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"):
        _semana_op(k, w)
    _capital(k, 1_000_000, t.TESORO)
    m.registro.ajustar("a", techo_preseed_mm=50_000,
                       techo_preseed_ciclo_mm=50_000)

    # el techo entero en W33, la ULTIMA semana operativa del ciclo 0
    b.alta(TS, "2026-W33", "p1", "dep:a", "ronda 1", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    bus_mod.financiar(m, b, TS, "2026-W33", "p1", t.TESORO, 50_000)
    assert k.saldo("dep:a") == 50_000

    # y el techo entero otra vez en W34, la PRIMERA del ciclo 1: siete dias
    # despues. Con la ventana fija esto entraba sin que nada se enterara
    b.alta(TS, "2026-W34", "p2", "dep:a", "ronda 2", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    with pytest.raises(bus_mod.ErrorBus) as exc:
        bus_mod.financiar(m, b, TS, "2026-W34", "p2", t.TESORO, 50_000)
    assert "techo de pre-seed superado" in str(exc.value)
    assert "2026-W31..2026-W34" in str(exc.value), "la ventana no es la de 4"
    assert k.saldo("dep:a") == 50_000, "entro 2x el techo en dos semanas"

    # y no es perpetuo: W37 es la cuarta operativa despues de W33, asi que
    # W33 ya salio de la ventana y el cupo volvio entero
    for w in ("2026-W35", "2026-W36", "2026-W37"):
        _semana_op(k, w)
    bus_mod.financiar(m, b, TS, "2026-W37", "p2", t.TESORO, 50_000)
    assert k.saldo("dep:a") == 100_000


def test_la_ventana_dice_cuando_vuelve_el_cupo_y_cuanto(entorno):
    """Lo que la deslizante PERMITE y la fija no: ponerle nombre y numero
    al alivio. Con el reset en bloque el cupo volvia entero, de golpe, y
    Pedro no tenia ninguna senal de que la ventana acababa de rodar."""
    k, m, b = entorno
    for w in ("2026-W30", "2026-W31", "2026-W32", "2026-W33"):
        _semana_op(k, w)
    _capital(k, 1_000_000, t.TESORO)
    m.registro.ajustar("a", techo_preseed_mm=50_000,
                       techo_preseed_ciclo_mm=50_000)
    b.alta(TS, "2026-W30", "p1", "dep:a", "ronda 1", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 50_000)

    ops = cap.semanas_operativas(k.libro.asientos())
    assert bus_mod.libera_preseed(
        k.libro.asientos(), "dep:a", ops, "2026-W33") == ("2026-W30", 50_000)

    b.alta(TS, "2026-W33", "p2", "dep:a", "ronda 2", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    with pytest.raises(bus_mod.ErrorBus) as exc:
        bus_mod.financiar(m, b, TS, "2026-W33", "p2", t.TESORO, 50_000)
    assert "sale 2026-W30 de la ventana" in str(exc.value)
    assert "se liberan 50000 mm" in str(exc.value)

    # y era verdad: abierta W34, W30 salio y el cupo esta
    _semana_op(k, "2026-W34")
    bus_mod.financiar(m, b, TS, "2026-W34", "p2", t.TESORO, 50_000)
    assert k.saldo("dep:a") == 100_000


def test_la_ventana_se_cuenta_en_semanas_operativas_y_la_demora_aprieta():
    """La forma de la ventana, sin libro de por medio.

    Por semana OPERATIVA y no por fecha: el libro indexa todo por semana,
    y una semana que la fabrica no abrio no es una semana en la que el
    departamento pudo hacer nada con ese capital.

    Y lo que importa del lunes sin abrir: mientras la semana no se abre la
    ventana NO rueda y ademas se suma la de hoy, asi que tardar en abrir
    APRIETA el techo. Un techo que se resetea porque Pedro tardo en tocar
    un boton no es un techo; este rueda porque Pedro ABRIO la semana."""
    ops = ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]
    assert bus_mod.ventana_preseed(ops, "2026-W33") == ops
    # la de hoy entra siempre, este abierta o no
    assert bus_mod.ventana_preseed(ops, "2026-W34") == ops + ["2026-W34"]
    # tres semanas sin abrir el boton: las cuatro viejas siguen adentro
    assert bus_mod.ventana_preseed(ops, "2026-W37") == ops + ["2026-W37"]
    # abrir la semana es lo que hace rodar la ventana, y sale la mas vieja
    abiertas = ops + ["2026-W34"]
    assert bus_mod.ventana_preseed(abiertas, "2026-W34") == abiertas[1:]
    # nunca levanta: sin operativas, o con una semana anterior a todas
    assert bus_mod.ventana_preseed([], "2026-W30") == ["2026-W30"]
    assert bus_mod.ventana_preseed(ops, "2026-W01") == ["2026-W01"]
    # y no promete una liberacion que no llega: con menos de cuatro
    # operativas, abrir una mas alarga la ventana sin tirar nada
    assert bus_mod.libera_preseed([], "dep:a", ops[:3], "2026-W32") == (None, 0)


def test_financiar_una_semana_atras_no_rompe_una_ventana_ya_validada(entorno):
    """EL AGUJERO QUE ABRIO LA VENTANA DESLIZANTE. `financiar` acepta
    CUALQUIER semana operativa, no solo la ultima abierta, y solo miraba
    la ventana que CIERRA en esa semana.

    Con la ventana fija eso era inocuo: los ciclos eran bloques disjuntos,
    asi que meter plata en una semana vieja cargaba el unico bloque que el
    chequeo miraba. Con la deslizante las ventanas se SOLAPAN: un asiento
    en una semana ya pasada entra en hasta `VENTANA_PRESEED_SEMANAS`
    ventanas, y todas menos una ya fueron validadas y nadie las vuelve a
    mirar nunca. El invariante que la ventana deslizante existe para
    defender -- en ninguna corrida de cuatro semanas operativas entra mas
    que el techo -- se rompia de forma permanentemente invisible: el
    siguiente `financiar` sigue viendo su propia ventana limpia y sigue
    informando el numero de antes.

    Por eso el chequeo recorre TODAS las ventanas que contienen `semana`,
    no solo la que termina en ella. La alternativa -- copiar el guardia de
    `operacion.cerrar_semana_operativa` y exigir la ultima abierta -- cierra
    la puerta pero no defiende el invariante: lo delega en que nadie mas
    escriba un pre-seed con fecha propia."""
    k, m, b = entorno
    for w in ("2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"):
        _semana_op(k, w)
    _capital(k, 1_000_000, t.TESORO)
    m.registro.ajustar("a", techo_preseed_mm=50_000,
                       techo_preseed_ciclo_mm=50_000)
    b.alta(TS, "2026-W34", "p1", "dep:a", "ronda 1", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    bus_mod.financiar(m, b, TS, "2026-W34", "p1", t.TESORO, 50_000)

    # W31 es operativa y su PROPIA ventana (W30..W31) esta en cero, pero
    # W31 tambien integra la de W34 -- W31..W34 -- que ya tiene el techo
    # entero adentro y que nadie vuelve a validar
    b.alta(TS, "2026-W31", "p2", "dep:a", "ronda 2", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    with pytest.raises(bus_mod.ErrorBus) as exc:
        bus_mod.financiar(m, b, TS, "2026-W31", "p2", t.TESORO, 50_000)
    assert "techo de pre-seed superado" in str(exc.value)
    # y dice CUAL corrida, que no es la que termina en la semana pedida
    assert "2026-W31..2026-W34" in str(exc.value), str(exc.value)
    assert k.saldo("dep:a") == 50_000, "entro 2x el techo por la puerta de atras"

    # el invariante, comprobado sobre TODA corrida de la ventana y no solo
    # sobre la que el ultimo `financiar` miro
    ops = cap.semanas_operativas(k.libro.asientos())
    for w in ops:
        adentro = bus_mod.preseed_en_ventana(
            k.libro.asientos(), "dep:a", bus_mod.ventana_preseed(ops, w))
        assert adentro <= 50_000, f"ventana de {w}: {adentro}"

    # y no es un bloqueo de mas: lo que entra sin romper ninguna corrida
    # sigue entrando. W30 solo integra W30..W31, W30..W32 y W30..W33, y
    # ninguna toca el asiento de W34
    bus_mod.financiar(m, b, TS, "2026-W30", "p2", t.TESORO, 50_000)
    assert k.saldo("dep:a") == 100_000


def test_un_preseed_pedido_vence_con_la_ventana_en_la_que_nacio(entorno):
    """El agujero: un pedido de pre-seed no caduca NUNCA.

    `evaluar_y_liquidar_muertos` solo recorre `activas()` -- las
    financiadas--, asi que un pedido en `alta` no pasa ni cerca; y su
    criterio de muerte es inerte por construccion (no abre `trabajo:<id>`,
    no hay gasto que medir). Resultado: lo unico que sacaba un pedido de la
    bandeja era que Pedro lo financiara o lo descartara, y mientras tanto
    seguia reservando cupo del techo acumulado -- para siempre.

    Vence con la ventana en la que nacio, que es exactamente lo que dura su
    financiabilidad: `preseed_en_ventana` cuenta cuatro semanas operativas
    hacia atras, asi que una vez que la semana del alta sale de la ventana
    el pedido ya no puede pagarse contra ninguna cuenta honesta."""
    k, m, b = entorno
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]:
        _semana_op(k, sem)
    _capital(k, 400_000, t.TESORO)
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco", 150_000, 150_000,
           {"gasto_max_mm": 150_000}, tipo="preseed")
    ops = cap.semanas_operativas(k.libro.asientos())
    # cuatro operativas: W30 sigue adentro de la ventana, el pedido vive
    assert bus_mod.preseed_vencido(b.datos("p1"), ops, "2026-W33") is False
    # Pedro abre la quinta: la ventana rueda y W30 se cae por atras
    _semana_op(k, "2026-W34")
    ops = cap.semanas_operativas(k.libro.asientos())
    assert bus_mod.preseed_vencido(b.datos("p1"), ops, "2026-W34") is True
    with pytest.raises(bus_mod.ErrorBus) as exc:
        bus_mod.financiar(m, b, TS, "2026-W34", "p1", t.TESORO, 150_000)
    assert "vencido" in str(exc.value)
    assert k.saldo("dep:a") == 0


def test_un_pedido_de_preseed_vive_toda_su_ventana(entorno):
    """El otro lado del mismo corte: mientras la semana del alta siga en la
    ventana, el pedido se paga. Un vencimiento que llegue antes seria
    romper lo que ya esta verificado -- que un pedido en pie reserva el cupo
    de la ventana en la que se lo pague."""
    k, m, b = entorno
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]:
        _semana_op(k, sem)
    _capital(k, 400_000, t.TESORO)
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco", 150_000, 150_000,
           {"gasto_max_mm": 150_000}, tipo="preseed")
    bus_mod.financiar(m, b, TS, "2026-W33", "p1", t.TESORO, 150_000)
    assert k.saldo("dep:a") == 150_000
    assert b.estado("p1") == "cerrada"


def test_el_vencimiento_no_toca_una_propuesta_de_trabajo(entorno):
    """Una propuesta de trabajo ya tiene su muerte (`criterio` +
    `evaluar_y_liquidar_muertos`) y no reserva cupo de ningun techo de
    caudal: el vencimiento es del pre-seed y de nadie mas."""
    k, m, b = entorno
    for sem in ["2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"]:
        _semana_op(k, sem)
    _capital(k, 100_000, "dep:b")
    b.alta(TS, "2026-W30", "t1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    ops = cap.semanas_operativas(k.libro.asientos())
    assert bus_mod.preseed_vencido(b.datos("t1"), ops, "2026-W34") is False
    bus_mod.financiar(m, b, TS, "2026-W34", "t1", "dep:b", 100_000)
    assert b.estado("t1") == "financiada"


def test_sin_semanas_operativas_no_vence_nada(entorno):
    """La ventana rueda cuando Pedro ABRE una semana operativa, no cuando
    cambia el almanaque (`ventana_preseed`). Sin ninguna abierta no rodo
    nunca, y hacer vencer ahi seria expirar por el paso del tiempo -- justo
    lo que el resto de este techo se niega a hacer."""
    _k, _m, b = entorno
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco", 150_000, 150_000,
           {"gasto_max_mm": 150_000}, tipo="preseed")
    assert bus_mod.preseed_vencido(b.datos("p1"), [], "2026-W40") is False


def test_no_se_paga_un_vencido_fechando_el_pago_en_una_semana_vieja(entorno):
    """LA LLAVE DE REPUESTO DEL VENCIMIENTO. `financiar` acepta CUALQUIER
    semana operativa y nunca exigio la ultima abierta, y el vencimiento se
    media con la ventana que el LLAMADOR pedia. Entonces la puerta que hace
    real al vencimiento -- la unica por donde la plata sale-- se abria con
    una fecha vieja: el mismo pedido que en la ultima semana se rechaza por
    vencido se pagaba sin una queja fechandolo cuatro semanas atras.

    El vencimiento se mide desde la FRONTERA (`ventana_pagable`): lo que
    vence a un pedido es que la fabrica haya seguido operando sin el, y eso
    no lo desanda elegir una fecha de pago mas comoda.

    Lo que NO cambia, y esta verificado abajo: `financiar` sigue aceptando
    una semana operativa que no es la ultima. Es la decision de
    `test_financiar_una_semana_atras_no_rompe_una_ventana_ya_validada` --
    defender el invariante y no la fecha-- y lo unico que se le agrega es
    que la fecha no puede resucitar un pedido ya vencido."""
    k, m, b = entorno
    for w in ("2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34",
              "2026-W35", "2026-W36", "2026-W37", "2026-W38"):
        _semana_op(k, w)
    _capital(k, 1_000_000, t.TESORO)
    m.registro.ajustar("a", techo_preseed_mm=100_000,
                       techo_preseed_ciclo_mm=100_000)
    b.alta(TS, "2026-W30", "viejo", "dep:a", "ronda vieja", 100_000, 100_000,
           {"gasto_max_mm": 100_000}, tipo="preseed")
    ops = cap.semanas_operativas(k.libro.asientos())
    assert bus_mod.preseed_vencido(b.datos("viejo"), ops, "2026-W38") is True
    # el predicado sigue contestando "en la semana que le das", que es lo
    # que los cinco lectores necesitan: en W33 ese pedido estaba vivo
    assert bus_mod.preseed_vencido(b.datos("viejo"), ops, "2026-W33") is False
    # pero la PUERTA lee el reloj de hoy, no la fecha que elige el llamador
    with pytest.raises(bus_mod.ErrorBus) as exc:
        bus_mod.financiar(m, b, TS, "2026-W33", "viejo", t.TESORO, 100_000)
    assert "vencido" in str(exc.value)
    assert k.saldo("dep:a") == 0, "se pago un vencido por la puerta de atras"

    # y una ronda nueva -- la que el vencimiento habilita-- si se paga, y se
    # paga fechada una semana atras, que es lo que la otra decision protege
    b.alta(TS, "2026-W38", "nuevo", "dep:a", "ronda de hoy", 100_000, 100_000,
           {"gasto_max_mm": 100_000}, tipo="preseed")
    bus_mod.financiar(m, b, TS, "2026-W37", "nuevo", t.TESORO, 100_000)
    assert k.saldo("dep:a") == 100_000


def test_la_ultima_ranura_de_la_ventana_no_se_pinta_como_pagable(entorno):
    """LA RANURA IMPAGABLE. Mientras la semana de hoy no esta abierta,
    `ventana_preseed` devuelve CINCO etiquetas -- las cuatro operativas de
    atras mas hoy-- porque para el TECHO tardar en abrir el lunes tiene que
    apretar, nunca aflojar. Medido con esa ventana, un pedido nacido en la
    mas vieja de esas cuatro seguia sin vencer: la mesa le pintaba la fila
    con su boton `financiar`.

    Pero `financiar` exige una semana operativa, asi que ese boton no podia
    funcionar; y abrir la semana -- lo unico que lo habilitaria, y lo que el
    aviso de la mesa le pide a Pedro con un boton al lado-- corre la ventana
    a cuatro etiquetas y vence el pedido en el mismo acto. No habia ninguna
    secuencia en la que esa fila se pudiera pagar.

    `ventana_pagable` cuenta la semana de hoy como si ya estuviera abierta,
    que es la unica forma en que se la podria pagar: el pedido vence ANTES
    de que la mesa lo ofrezca, y la respuesta no cambia al abrir."""
    k, m, b = entorno
    for w in ("2026-W31", "2026-W32", "2026-W33", "2026-W34"):
        _semana_op(k, w)
    _capital(k, 1_000_000, t.TESORO)
    b.alta(TS, "2026-W31", "ultima-chance", "dep:a", "ronda", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    ops = cap.semanas_operativas(k.libro.asientos())
    # hoy es W35 y todavia no esta abierta
    assert bus_mod.ventana_preseed(ops, "2026-W35") == [
        "2026-W31", "2026-W32", "2026-W33", "2026-W34", "2026-W35"]
    assert bus_mod.preseed_vencido(b.datos("ultima-chance"), ops,
                                   "2026-W35") is True
    # y la respuesta no se da vuelta cuando Pedro abre la semana: antes,
    # abrirla era lo que lo vencia
    _semana_op(k, "2026-W35")
    ops2 = cap.semanas_operativas(k.libro.asientos())
    assert bus_mod.preseed_vencido(b.datos("ultima-chance"), ops2,
                                   "2026-W35") is True
    with pytest.raises(bus_mod.ErrorBus):
        bus_mod.financiar(m, b, TS, "2026-W35", "ultima-chance", t.TESORO,
                          50_000)
    assert k.saldo("dep:a") == 0
    # y el de la ranura de al lado -- el que SI se puede pagar abriendo--
    # sigue vivo antes y despues de abrir: el corte no se corrio de mas
    b.alta(TS, "2026-W32", "todavia", "dep:a", "ronda", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    assert bus_mod.preseed_vencido(b.datos("todavia"), ops,
                                   "2026-W35") is False
    bus_mod.financiar(m, b, TS, "2026-W35", "todavia", t.TESORO, 50_000)
    assert k.saldo("dep:a") == 50_000


def test_sin_semanas_operativas_la_ventana_nunca_rodo(entorno):
    """El borde tolerante de siempre, que `ventana_pagable` no puede
    aflojar: sin ninguna semana operativa la ventana nunca rodo, y hacer
    vencer ahi seria expirar por el paso del tiempo -- justo lo que este
    techo se niega a hacer."""
    k, m, b = entorno
    b.alta(TS, "2026-W30", "p1", "dep:a", "arranco", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    assert bus_mod.preseed_vencido(b.datos("p1"), [], "2026-W99") is False


def test_financiar_pliega_las_semanas_operativas_una_sola_vez(entorno,
                                                              monkeypatch):
    """`semanas_operativas` es un set-comprehension sobre el libro entero
    mas un `sorted`, y `financiar` lo pedia TRES veces por llamada sobre el
    mismo snapshot inmutable de asientos: la guardia de semana operativa,
    el vencimiento y el chequeo multi-ventana. Las tres respuestas eran
    identicas por construccion."""
    k, m, b = entorno
    for w in ("2026-W30", "2026-W31"):
        _semana_op(k, w)
    _capital(k, 1_000_000, t.TESORO)
    m.registro.ajustar("a", techo_preseed_mm=50_000,
                       techo_preseed_ciclo_mm=50_000)
    b.alta(TS, "2026-W31", "p1", "dep:a", "ronda", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    veces = []
    real = cap.semanas_operativas
    monkeypatch.setattr(cap, "semanas_operativas",
                        lambda a: veces.append(1) or real(a))
    bus_mod.financiar(m, b, TS, "2026-W31", "p1", t.TESORO, 50_000)
    assert k.saldo("dep:a") == 50_000
    assert len(veces) == 1, f"{len(veces)} pliegues del libro en un financiar"


def test_un_trabajo_que_solo_consume_suscripcion_muere_igual(entorno):
    """El criterio de muerte `gasto_max_mm` se mide sobre `gastado`, y bajo
    costo hundido la capacidad de suscripcion dejo de salir de la cuenta del
    trabajo: sale del pool de cristal y el trabajo viaja en el `ref`. Sin
    contarla, un trabajo cuyo unico costo es la suscripcion tiene gasto cero,
    no muere nunca, y el brief que Calipso lee cada turno informa "gastado 0
    mm" de un proyecto que esta quemando la cuota."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000,
           {"gasto_max_mm": 10_000})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 60_000)
    # 21 unidades a 500 mm de API equivalente = 10.500 > 10.000
    for _ in range(21):
        m.consumir_capacidad(TS, "2026-W30", "trabajo:p1", "claude_max", 1,
                             dueno="dep:a")
    asientos = k.libro.asientos()
    assert bus_mod.gastado(asientos, "p1", m.suscripciones) == 10_500
    # la plata del trabajo no se movio: por eso el saldo no puede ser el
    # criterio de muerte de un trabajo que gasta capacidad
    assert k.saldo("trabajo:p1") == 60_000
    assert bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W30") == ["p1"]
    assert b.estado("p1") == "liquidada"


def test_gastado_sin_suscripciones_cuenta_solo_la_plata(entorno):
    """El default tolerante para los lectores que no las tienen a mano: sin
    la tabla no hay costo API equivalente que calcular, y se declara en vez
    de inventarse un numero."""
    k, m, b = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000, CRITERIO)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 60_000)
    m.gastar_api(TS, "2026-W30", "trabajo:p1", 7_000, ref="trabajo:p1",
                 dueno="dep:a")
    m.consumir_capacidad(TS, "2026-W30", "trabajo:p1", "claude_max", 4,
                         dueno="dep:a")
    asientos = k.libro.asientos()
    assert bus_mod.gastado(asientos, "p1") == 7_000
    assert bus_mod.gastado(asientos, "p1", m.suscripciones) == 9_000


FORMA_OK = {"sobre": "el radar de precios", "clave": "precios+radar",
            "promete": "descartar", "tarda": "corto"}


def test_una_propuesta_puede_llevar_su_forma(tmp_path):
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    b.alta(TS, W, "p1", "dep:a", "descartar: el radar (corto)", 10_000,
           10_000, {"gasto_max_mm": 10_000, "semanas_max": 1},
           forma=FORMA_OK)
    assert b.datos("p1")["forma"] == FORMA_OK


def test_una_propuesta_sin_forma_sigue_siendo_valida(tmp_path):
    """Compatibilidad: las que se escribieron antes de que la forma
    existiera se leen, se financian y se descartan igual. No hay
    migracion."""
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    b.alta(TS, W, "p1", "dep:a", "radar", 10_000, 10_000,
           {"gasto_max_mm": 10_000})
    assert b.datos("p1").get("forma") is None
    assert b.estado("p1") == "alta"


def test_una_forma_invalida_no_entra_al_libro(tmp_path):
    """El libro es append-only: una forma mal escrita no se puede borrar
    despues, asi que se corta antes de escribirla."""
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    casos = [
        {"sobre": "x", "clave": "x", "promete": "bailar", "tarda": "corto"},
        {"sobre": "x", "clave": "x", "promete": "medir", "tarda": "ya"},
        {"sobre": "x", "clave": "x", "promete": "medir"},
        {"sobre": "", "clave": "x", "promete": "medir", "tarda": "corto"},
        {"sobre": "x", "clave": "", "promete": "medir", "tarda": "corto"},
        {"sobre": "x", "clave": "x", "promete": "medir", "tarda": "corto",
         "de_mas": 1},
        42,
        ["sobre", "clave", "promete", "tarda"],
    ]
    for i, forma in enumerate(casos):
        with pytest.raises(bus_mod.ErrorBus):
            b.alta(TS, W, f"p{i}", "dep:a", "t", 1000, 1000,
                   {"gasto_max_mm": 1000}, forma=forma)


def test_un_preseed_no_lleva_forma(tmp_path):
    """No sale de una ficha: sale de `pedir <monto>`, que es otro verbo."""
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    b.alta(TS, W, "p1", "dep:a", "ronda pre-seed de a", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    assert b.datos("p1").get("forma") is None


def test_el_vocabulario_del_libro_y_el_del_plantel_no_se_separan():
    """La duplicacion es deliberada -- el libro no puede importar de quien
    lo escribe -- pero tiene que ser una copia, no una deriva. El test
    importa `ficha`; `bus.py` sigue sin importarlo, que es lo que el diseno
    protege."""
    from calipso.plantel import ficha as _ficha
    assert set(_ficha.PROMESAS) == bus_mod._PROMESAS
    assert set(_ficha.PLAZOS) == bus_mod._PLAZOS
