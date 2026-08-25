"""Tests de departamentos, mercado y direccion: la capa de juego economico."""
import pytest

from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import cuenta_pedro as cp
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"
W = "2026-W35"


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


@pytest.fixture
def registro(tmp_path):
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("mercadeo", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=20_000,
                             techo_api_ciclo_mm=10_000))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    return r


def _capital(k, monto, destino=t.TESORO):
    return k.acunar(TS, W, destino, monto, t.SubtipoAcunacion.CAPITAL,
                    {"tipo": "firma_pedro"})


def test_cuentas_por_zona(registro):
    assert registro.obtener("mercadeo").cuenta == "dep:mercadeo"
    assert registro.obtener("finanzas").cuenta == "personal:finanzas"


def test_registro_persiste_y_ajusta(tmp_path, registro):
    registro.ajustar("mercadeo", presupuesto_semanal_mm=30_000)
    r2 = deps.Registro(tmp_path / "departamentos.json")
    assert r2.obtener("mercadeo").presupuesto_semanal_mm == 30_000
    assert len(r2.todos()) == 2
    with pytest.raises(deps.ErrorDepartamento):
        r2.alta(deps.Departamento("mercadeo", deps.ZONA_FABRICA))  # repetido
    with pytest.raises(deps.ErrorDepartamento):
        r2.obtener("fantasma")


def test_quiebra_congela_y_rescate_descongela(k):
    _capital(k, 10_000, destino="dep:a")
    assert not deps.es_congelado(k.libro.asientos(), "dep:a")
    deps.declarar_quiebra(k, TS, W, "dep:a")
    assert deps.es_congelado(k.libro.asientos(), "dep:a")
    _capital(k, 5_000, destino=t.CUENTA_PEDRO)
    cp.rescatar(k, TS, W, "dep:a", 5_000, firma={"tipo": "firma_pedro"})
    assert not deps.es_congelado(k.libro.asientos(), "dep:a")


def test_venta_propia_tambien_descongela(k):
    deps.declarar_quiebra(k, TS, W, "dep:a")
    k.acunar(TS, W, "dep:a", 1_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"})
    assert not deps.es_congelado(k.libro.asientos(), "dep:a")


def test_capital_no_descongela(k):
    """Solo rescate firmado o venta propia sacan del congelamiento (spec 5)."""
    deps.declarar_quiebra(k, TS, W, "dep:a")
    _capital(k, 1_000, destino="dep:a")  # capital directo, sin marca de rescate
    assert deps.es_congelado(k.libro.asientos(), "dep:a")


from calipso.economia import mercado as mkt

SUS = cap.Suscripcion(nombre="claude_max", costo_mensual_mm=100_000,
                      capacidad_ciclo=1_000, reserva_personal=200,
                      costo_api_mm_por_unidad=500)


@pytest.fixture
def mercado(k, registro):
    return mkt.Mercado(k, registro, {"claude_max": SUS})


def _semana_op(k, semana):
    pt.emitir_semana(k, TS, semana, 4_000, 0)
    pt.expirar_pools(k, TS, semana)


def test_comprar_capacidad_cobra_precio_por_escasez(k, mercado):
    _semana_op(k, "2026-W35")
    _capital(k, 100_000, destino="dep:mercadeo")
    a = mercado.comprar_capacidad(TS, "2026-W35", "dep:mercadeo",
                                  "claude_max", 10)
    assert a.monto == 1_000            # 10 unidades a precio base 100
    assert k.saldo(t.DIRECCION) == 1_000
    # tras consumir 400 en el 25% del ciclo, el precio dobla (factor 200)
    mercado.comprar_capacidad(TS, "2026-W35", "dep:mercadeo",
                              "claude_max", 390)
    b = mercado.comprar_capacidad(TS, "2026-W35", "dep:mercadeo",
                                  "claude_max", 10)
    assert b.monto == 2_000            # 10 unidades a 200


def test_cuota_agotada_rechaza(k, mercado):
    _semana_op(k, "2026-W35")
    _capital(k, 1_000_000, destino="dep:mercadeo")
    with pytest.raises(mkt.ErrorMercado):
        mercado.comprar_capacidad(TS, "2026-W35", "dep:mercadeo",
                                  "claude_max", 801)  # fabrica = 800


def test_zona_personal_no_compra_capacidad_de_fabrica(k, mercado):
    _semana_op(k, "2026-W35")
    with pytest.raises(mkt.ErrorMercado):
        mercado.comprar_capacidad(TS, "2026-W35", "personal:finanzas",
                                  "claude_max", 1)


def test_reserva_personal_se_consume_y_agota(k, mercado):
    _semana_op(k, "2026-W35")
    a = mercado.usar_reserva_personal(TS, "2026-W35", "claude_max", 150,
                                      "personal:finanzas")
    assert a.tipo is t.TipoAsiento.APUNTE and a.monto == 150
    with pytest.raises(mkt.ErrorMercado):
        mercado.usar_reserva_personal(TS, "2026-W35", "claude_max", 51,
                                      "personal:finanzas")  # reserva 200


def test_congelado_no_compra_ni_recibe(k, mercado):
    _semana_op(k, "2026-W35")
    _capital(k, 50_000, destino="dep:mercadeo")
    _capital(k, 50_000, destino="dep:otro")
    deps.declarar_quiebra(k, TS, "2026-W35", "dep:mercadeo")
    with pytest.raises(mkt.ErrorMercado):
        mercado.comprar_capacidad(TS, "2026-W35", "dep:mercadeo",
                                  "claude_max", 1)
    with pytest.raises(mkt.ErrorMercado):
        mercado.gastar_api(TS, "2026-W35", "dep:mercadeo", 100)
    with pytest.raises(mkt.ErrorMercado):
        mercado.vender_servicio(TS, "2026-W35", "dep:otro",
                                "dep:mercadeo", 100)


def test_techo_api_exige_firma_para_superarse(k, mercado):
    _semana_op(k, "2026-W35")
    _capital(k, 100_000, destino="dep:mercadeo")
    mercado.gastar_api(TS, "2026-W35", "dep:mercadeo", 9_000)
    with pytest.raises(mkt.ErrorMercado):
        mercado.gastar_api(TS, "2026-W35", "dep:mercadeo", 2_000)  # 11k > techo 10k
    a = mercado.gastar_api(TS, "2026-W35", "dep:mercadeo", 2_000,
                           firma={"tipo": "firma_pedro"})
    assert a.monto == 2_000


def test_trabajo_gasta_con_dueno_y_cuenta_contra_su_techo(k, mercado):
    """La puerta de gasto de los trabajos: politicas y techo del dueno."""
    _semana_op(k, "2026-W35")
    _capital(k, 50_000, destino="trabajo:p1")
    _capital(k, 50_000, destino="dep:mercadeo")
    with pytest.raises(mkt.ErrorMercado):
        mercado.gastar_api(TS, "2026-W35", "trabajo:p1", 1_000)  # sin dueno
    mercado.gastar_api(TS, "2026-W35", "trabajo:p1", 6_000, dueno="dep:mercadeo")
    # el gasto del trabajo cuenta contra el techo del dueno (10_000)
    with pytest.raises(mkt.ErrorMercado):
        mercado.gastar_api(TS, "2026-W35", "dep:mercadeo", 5_000)  # 6k+5k > 10k
    a = mercado.gastar_api(TS, "2026-W35", "dep:mercadeo", 5_000,
                           firma={"tipo": "firma_pedro"})
    assert a.detalle["firma"] == {"tipo": "firma_pedro"}  # auditable
    # dueno congelado: sus trabajos tampoco gastan
    deps.declarar_quiebra(k, TS, "2026-W35", "dep:mercadeo")
    with pytest.raises(mkt.ErrorMercado):
        mercado.gastar_api(TS, "2026-W35", "trabajo:p1", 100,
                           dueno="dep:mercadeo")


def test_vender_servicio_entre_departamentos(k, mercado, registro):
    registro.alta(deps.Departamento("produccion", deps.ZONA_FABRICA))
    _semana_op(k, "2026-W35")
    _capital(k, 10_000, destino="dep:produccion")
    mercado.vender_servicio(TS, "2026-W35", "dep:produccion",
                            "dep:mercadeo", 4_000)
    assert k.saldo("dep:mercadeo") == 4_000
