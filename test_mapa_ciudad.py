"""Tests de la derivacion del libro al modelo de ciudad."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import cola as cola_mod
from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.mapa import ciudad as ciu

TS = "2026-08-25T10:00:00"
W = "2026-W35"


@pytest.fixture
def mundo(tmp_path):
    """Libro sintetico con dos departamentos de fabrica y uno personal."""
    k = Kernel(Libro(tmp_path / "libro.jsonl"))
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("mercado", deps.ZONA_FABRICA))
    r.alta(deps.Departamento("curiosos", deps.ZONA_FABRICA))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    c = cola_mod.Cola(tmp_path / "cola.jsonl")
    return k, r, b, c


def _capital(k, monto, destino, ts=TS, semana=W):
    k.acunar(ts, semana, destino, monto, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})


def test_tamano_crece_con_el_saldo_y_tiene_techo():
    assert ciu.tamano_de(0) == 1
    assert ciu.tamano_de(-500) == 1
    assert ciu.tamano_de(1_000) == 2
    assert ciu.tamano_de(50_000) == 3
    assert ciu.tamano_de(1_000_000) == 5
    assert ciu.tamano_de(10 ** 15) == 9  # techo


def test_edificios_salen_del_registro_con_su_saldo(mundo):
    k, r, b, c = mundo
    _capital(k, 50_000, "dep:mercado")
    _capital(k, 1_000, "personal:finanzas")
    _capital(k, 4_000, t.CUENTA_PEDRO)
    edis = {e["id"]: e for e in ciu.edificios(k.libro.asientos(), r, b, c)}
    assert set(edis) == {"dep:mercado", "dep:curiosos", "personal:finanzas",
                         "cuenta_pedro"}
    assert edis["dep:mercado"]["saldo_mm"] == 50_000
    assert edis["dep:mercado"]["tamano"] == 3
    assert edis["dep:mercado"]["zona"] == deps.ZONA_FABRICA
    assert edis["dep:curiosos"]["tamano"] == 1  # sin plata, sigue existiendo
    assert edis["cuenta_pedro"]["zona"] == deps.ZONA_PERSONAL
    assert edis["cuenta_pedro"]["nombre"] == "pedro"


def test_orden_es_por_primera_aparicion_en_el_libro(mundo):
    k, r, b, c = mundo
    _capital(k, 1_000, "dep:curiosos")   # aparece primero
    _capital(k, 1_000, "dep:mercado")
    edis = {e["id"]: e for e in ciu.edificios(k.libro.asientos(), r, b, c)}
    assert edis["dep:curiosos"]["orden"] < edis["dep:mercado"]["orden"]
    # uno que nunca aparecio queda al final, no rompe
    assert edis["personal:finanzas"]["orden"] > edis["dep:mercado"]["orden"]


def test_congelado_se_ve_en_el_estado(mundo):
    k, r, b, c = mundo
    _capital(k, 1_000, "dep:curiosos")
    assert ciu.edificios(k.libro.asientos(), r, b, c)
    deps.declarar_quiebra(k, TS, W, "dep:curiosos")
    edis = {e["id"]: e for e in ciu.edificios(k.libro.asientos(), r, b, c)}
    assert edis["dep:curiosos"]["estado"] == "congelado"
    assert edis["dep:mercado"]["estado"] == "activo"


def test_actividad_cuenta_dias_con_gasto_contra_el_ultimo_ts(mundo):
    """Determinismo: la ventana se mide contra el libro, no contra el reloj."""
    k, r, b, c = mundo
    _capital(k, 100_000, "dep:mercado", ts="2026-08-19T09:00:00")
    # cuatro dias con gasto, pero solo tres entran en la ventana
    for dia in ("2026-08-20", "2026-08-23", "2026-08-24", "2026-08-25"):
        k.destruir(f"{dia}T10:00:00", W, "dep:mercado", 100, motivo="api")
    asientos = k.libro.asientos()
    assert ciu.actividad_de(asientos, "dep:mercado") == 3  # techo y ventana
    assert ciu.actividad_de(asientos, "dep:curiosos") == 0
    # con dos dias de ventana, solo cuentan los dos ultimos
    assert ciu.actividad_de(asientos, "dep:mercado", dias=2) == 2
    # y no depende del reloj: reconstruido desde disco da lo mismo
    k2 = Kernel(Libro(k.libro.ruta))
    assert ciu.actividad_de(k2.libro.asientos(), "dep:mercado") == 3


def test_trabajos_y_compuertas_se_cuelgan_de_su_dueno(mundo):
    k, r, b, c = mundo
    _capital(k, 100_000, "dep:mercado")
    b.alta(TS, W, "radar", "dep:mercado", "radar vertical", 10_000, 30_000,
           {"gasto_max_mm": 5_000})
    b.marcar(TS, W, "radar", "financiada")
    c.encolar(k, TS, W, "c1", "dep:mercado", "llamar cliente", tipo="contacto",
              obligatoria=True, mpt_estimado=500, monedas_en_juego=90_000)
    edis = {e["id"]: e for e in ciu.edificios(k.libro.asientos(), r, b, c)}
    assert edis["dep:mercado"]["trabajos"] == ["radar"]
    assert edis["dep:mercado"]["compuertas"] == 1
    assert edis["dep:curiosos"]["trabajos"] == []
    assert edis["dep:curiosos"]["compuertas"] == 0


def _semana_op(k, semana):
    pt.emitir_semana(k, TS, semana, 4_000, 0)
    pt.expirar_pools(k, TS, semana)


def test_ancho_por_buckets_de_comercio():
    assert ciu.ancho_de(0) == 1
    assert ciu.ancho_de(9_999) == 1
    assert ciu.ancho_de(10_000) == 2
    assert ciu.ancho_de(100_000) == 3
    assert ciu.ancho_de(1_000_000) == 4


def test_calle_por_servicio_directo_y_cable_entre_zonas(mundo):
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 200_000, "dep:mercado")
    _capital(k, 200_000, "personal:finanzas")
    k.transferir(TS, W, "dep:mercado", "dep:curiosos", 120_000,
                 motivo="servicio")
    k.transferir(TS, W, "personal:finanzas", "dep:mercado", 5_000,
                 motivo="servicio")
    asientos = k.libro.asientos()
    edis = ciu.edificios(asientos, r, b, c)
    cs = {(x["a"], x["b"]): x for x in ciu.calles(
        asientos, edis, ciu.duenos_de(b), [W])}
    assert cs[("dep:curiosos", "dep:mercado")]["peso_mm"] == 120_000
    assert cs[("dep:curiosos", "dep:mercado")]["ancho"] == 3
    assert cs[("dep:curiosos", "dep:mercado")]["tipo"] == "calle"
    # cruza zonas: es cable
    assert cs[("dep:mercado", "personal:finanzas")]["tipo"] == "cable"


def test_financiar_el_trabajo_de_otro_tambien_es_comercio(mundo):
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 200_000, "dep:curiosos")
    b.alta(TS, W, "radar", "dep:mercado", "radar", 10_000, 30_000,
           {"gasto_max_mm": 5_000})
    b.marcar(TS, W, "radar", "financiada")
    k.transferir(TS, W, "dep:curiosos", "trabajo:radar", 40_000,
                 motivo="financiacion")
    asientos = k.libro.asientos()
    edis = ciu.edificios(asientos, r, b, c)
    cs = {(x["a"], x["b"]): x for x in ciu.calles(
        asientos, edis, ciu.duenos_de(b), [W])}
    assert cs[("dep:curiosos", "dep:mercado")]["peso_mm"] == 40_000


def test_la_capacidad_no_crea_calles_entre_departamentos(mundo):
    """Comprar capacidad va a direccion, no al otro departamento."""
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 200_000, "dep:mercado")
    k.transferir(TS, W, "dep:mercado", t.DIRECCION, 30_000, motivo="capacidad",
                 detalle_extra={"suscripcion": "claude_max", "unidades": 10})
    asientos = k.libro.asientos()
    edis = ciu.edificios(asientos, r, b, c)
    assert ciu.calles(asientos, edis, ciu.duenos_de(b), [W]) == []


def test_unidades_son_los_trabajos_vivos(mundo):
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 200_000, "dep:mercado")
    _capital(k, 200_000, "dep:curiosos")
    b.alta(TS, W, "radar", "dep:mercado", "radar", 10_000, 30_000,
           {"gasto_max_mm": 50_000})
    b.marcar(TS, W, "radar", "financiada")
    k.transferir(TS, W, "dep:mercado", "trabajo:radar", 20_000,
                 motivo="financiacion")
    k.transferir(TS, W, "dep:curiosos", "trabajo:radar", 60_000,
                 motivo="financiacion")
    k.destruir(TS, W, "trabajo:radar", 7_000, motivo="api", ref="trabajo:radar")
    us = ciu.unidades(k.libro.asientos(), b, ciu.duenos_de(b))
    assert len(us) == 1
    assert us[0]["id"] == "radar"
    assert us[0]["dueno"] == "dep:mercado"
    assert us[0]["gastado_mm"] == 7_000
    # camina hacia el mayor cofinanciador que no es el dueno
    assert us[0]["hacia"] == "dep:curiosos"


def test_avisos_traen_lo_que_espera_tu_firma(mundo):
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 200_000, "dep:mercado")
    c.encolar(k, TS, W, "c1", "dep:mercado", "llamar", tipo="contacto",
              obligatoria=True, mpt_estimado=500, monedas_en_juego=90_000)
    c.encolar_carta(TS, W, "renovacion:claude_max:0",
                    {"tipo": "renovacion", "suscripcion": "claude_max"})
    avs = {a["id"]: a for a in ciu.avisos(c)}
    assert avs["c1"]["sobre"] == "dep:mercado"
    assert avs["c1"]["monedas_en_juego_mm"] == 90_000
    assert avs["c1"]["tipo"] == "contacto"
    assert avs["renovacion:claude_max:0"]["sobre"] is None


def test_ciudad_arma_la_cabecera_completa(mundo):
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 1_200_000, t.TESORO)
    _capital(k, 5_000, t.CUENTA_PEDRO)
    m = ciu.ciudad(k.libro.asientos(), r, b, c, W, minutos_empleo=9_600)
    assert m["semana"] == W
    assert m["tesoro_mm"] == 1_200_000
    assert m["cuenta_pedro_mm"] == 5_000
    assert m["direccion_mm"] == 0
    assert m["tipo_cambio_mm"] == 5_000     # arranque, sin historia
    assert m["linea_empleo_mm"] == 15_625   # 2.500.000 * 60 // 9600
    assert len(m["edificios"]) == 4
    assert m["calles"] == [] and m["unidades"] == [] and m["avisos"] == []


def test_ciudad_es_reproducible(mundo):
    """Invariante 2: mismo libro, mismo modelo — tambien desde disco."""
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 50_000, "dep:mercado")
    a = ciu.ciudad(k.libro.asientos(), r, b, c, W)
    k2 = Kernel(Libro(k.libro.ruta))
    dos = ciu.ciudad(k2.libro.asientos(), r, b, c, W)
    assert a == dos
