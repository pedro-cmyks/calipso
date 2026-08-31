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
    borde dejaba pasar el doble."""
    k, m, b = entorno
    for w in ("2026-W30", "2026-W31", "2026-W32", "2026-W33", "2026-W34"):
        _semana_op(k, w)
    _capital(k, 1_000_000, t.TESORO)
    m.registro.ajustar("a", techo_preseed_mm=50_000,
                       techo_preseed_ciclo_mm=50_000)
    b.alta(TS, "2026-W30", "p1", "dep:a", "ronda 1", 50_000, 50_000,
           {"gasto_max_mm": 50_000}, tipo="preseed")
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", t.TESORO, 50_000)

    # misma semana: agotado
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
