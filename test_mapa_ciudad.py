"""Tests de la derivacion del libro al modelo de ciudad."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import cola as cola_mod
from calipso.economia import departamentos as deps
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
