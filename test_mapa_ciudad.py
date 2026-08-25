"""Tests de la derivacion del libro al modelo de ciudad."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import cola as cola_mod
from calipso.economia import departamentos as deps
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.mapa import ciudad as ciu

TS = "2026-08-25T10:00:00"
W = "2026-W35"


def _lapso(asientos):
    return ciu.lapso_ventana(cap.semanas_operativas(asientos))


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


def test_el_orden_cuenta_edificios_y_no_pools_ni_tesoro(mundo):
    """M8: pt:fabrica, tesoro y direccion no son departamentos. Si se los
    cuenta se quedan con los primeros lugares y el orden miente."""
    k, r, b, c = mundo
    _semana_op(k, W)                      # aparece pt:fabrica
    _capital(k, 1_000, t.TESORO)          # aparece tesoro
    _capital(k, 1_000, "dep:mercado")     # el PRIMER edificio del libro
    _capital(k, 1_000, "dep:curiosos")
    edis = {e["id"]: e for e in ciu.edificios(k.libro.asientos(), r, b, c)}
    assert edis["dep:mercado"]["orden"] == 0
    assert edis["dep:curiosos"]["orden"] == 1


def test_el_que_paga_es_mas_viejo_que_el_que_cobra(mundo):
    """M8: dentro de un mismo asiento se lee primero el origen."""
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 200_000, t.TESORO)
    # primera aparicion de AMBOS en el mismo asiento: el que paga ya tenia
    # plata, asi que es el mas viejo
    k.transferir(TS, W, t.TESORO, "dep:mercado", 50_000, motivo="presupuesto")
    k.transferir(TS, W, "dep:mercado", "dep:curiosos", 10_000,
                 motivo="servicio")
    edis = {e["id"]: e for e in ciu.edificios(k.libro.asientos(), r, b, c)}
    assert edis["dep:mercado"]["orden"] < edis["dep:curiosos"]["orden"]


def test_congelado_se_ve_en_el_estado(mundo):
    k, r, b, c = mundo
    _capital(k, 1_000, "dep:curiosos")
    antes = {e["id"]: e for e in ciu.edificios(k.libro.asientos(), r, b, c)}
    assert antes["dep:curiosos"]["estado"] == "activo"  # antes de la quiebra
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


def test_la_ejecucion_de_una_reserva_tambien_es_gasto(mundo):
    """M6: bus.gastado ya la cuenta. Dos lecturas del mismo libro no pueden
    discrepar sobre que es gasto."""
    k, r, b, c = mundo
    _capital(k, 100_000, "dep:mercado", ts="2026-08-24T09:00:00")
    k.reservar("2026-08-25T09:00:00", W, "dep:mercado", 10_000, ref="x1")
    k.ejecutar_reserva("2026-08-25T10:00:00", W, "x1", t.CUENTA_PEDRO)
    assert ciu.actividad_de(k.libro.asientos(), "dep:mercado") == 1


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
        asientos, edis, ciu.duenos_de(b), _lapso(asientos))}
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
        asientos, edis, ciu.duenos_de(b), _lapso(asientos))}
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
    assert ciu.calles(asientos, edis, ciu.duenos_de(b), _lapso(asientos)) == []


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
    asientos = k.libro.asientos()
    duenos = ciu.duenos_de(b)
    cs = ciu.calles(asientos, ciu.edificios(asientos, r, b, c), duenos,
                    _lapso(asientos))
    us = ciu.unidades(asientos, b.activas(), duenos, cs)
    assert len(us) == 1
    assert us[0]["id"] == "radar"
    assert us[0]["dueno"] == "dep:mercado"
    assert us[0]["gastado_mm"] == 7_000
    # camina hacia el mayor cofinanciador que no es el dueno
    assert us[0]["hacia"] == "dep:curiosos"


def test_una_venta_no_desaparece_de_la_ventana_sin_emision_de_pt(mundo):
    """M7: la ventana es un LAPSO entre la primera y la ultima de las ocho
    semanas operativas, no el conjunto de sus etiquetas. Una semana sin
    emision de PT dentro del lapso sigue contando, igual que en pt.py."""
    k, r, b, c = mundo
    _semana_op(k, "2026-W30")
    _capital(k, 400_000, "dep:mercado")
    # W33 nunca se abrio: no hay emision de PT esa semana
    k.transferir(TS, "2026-W33", "dep:mercado", "dep:curiosos", 250_000,
                 motivo="servicio")
    _semana_op(k, "2026-W35")
    asientos = k.libro.asientos()
    edis = ciu.edificios(asientos, r, b, c)
    cs = ciu.calles(asientos, edis, ciu.duenos_de(b), _lapso(asientos))
    assert [(x["a"], x["b"], x["peso_mm"]) for x in cs] == [
        ("dep:curiosos", "dep:mercado", 250_000)]


def test_hacia_solo_nombra_calles_que_existen(mundo):
    """C2: la unidad camina por esa calle. Con la financiacion ya fuera de
    la ventana no hay calle, y entonces no hay a donde caminar."""
    k, r, b, c = mundo
    _semana_op(k, "2026-W10")
    _capital(k, 200_000, "dep:mercado")
    _capital(k, 200_000, "dep:curiosos")
    b.alta(TS, "2026-W10", "radar", "dep:mercado", "radar", 10_000, 30_000,
           {"gasto_max_mm": 50_000})
    b.marcar(TS, "2026-W10", "radar", "financiada")
    k.transferir(TS, "2026-W10", "dep:curiosos", "trabajo:radar", 60_000,
                 motivo="financiacion")
    for s in ("2026-W20", "2026-W21", "2026-W22", "2026-W23", "2026-W24",
              "2026-W25", "2026-W26", "2026-W27", "2026-W28"):
        _semana_op(k, s)
    m = ciu.ciudad(k.libro.asientos(), r, b, c, "2026-W28")
    # el aporte sigue en el libro, pero su semana quedo fuera de la ventana
    assert bus_mod.aportes(k.libro.asientos(), "radar") == {
        "dep:curiosos": 60_000}
    assert m["calles"] == []
    assert m["unidades"][0]["hacia"] is None
    # y la regla general: todo hacia no nulo nombra una calle del modelo
    pares = {(x["a"], x["b"]) for x in m["calles"]}
    for u in m["unidades"]:
        if u["hacia"] is not None:
            assert tuple(sorted((u["dueno"], u["hacia"]))) in pares


def test_avisos_traen_lo_que_espera_tu_firma(mundo):
    k, r, b, c = mundo
    _semana_op(k, W)
    _capital(k, 200_000, "dep:mercado")
    c.encolar(k, TS, W, "c1", "dep:mercado", "llamar", tipo="contacto",
              obligatoria=True, mpt_estimado=500, monedas_en_juego=90_000)
    c.encolar_carta(TS, W, "renovacion:claude_max:0",
                    {"tipo": "renovacion", "suscripcion": "claude_max"})
    avs = {a["id"]: a for a in ciu.avisos(c.pendientes())}
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
