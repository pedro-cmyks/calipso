"""Tests de la divisa CRISTAL: capacidad de suscripcion, no plata.

Emision por ciclo, consumo que nunca rechaza, descubierto, cierre del
ciclo en cero exacto, y el acople que este modulo NO puede tocar: el
cierre semanal no debe declarar en quiebra a nadie por consumir cristales.
"""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import cierre
from calipso.economia import cristal
from calipso.economia import departamentos as deps
from calipso.economia import mercado as mkt
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.balances import saldos
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"

# capacidad_ciclo 1.000, reserva personal 200 -> 800 para la fabrica
SUS = cap.Suscripcion("claude_max", 100_000, 1_000, 200, 500)
FAB = t.cuenta_cristal("claude_max", "fabrica")
PER = t.cuenta_cristal("claude_max", "personal")


@pytest.fixture
def k(tmp_path):
    return Kernel(Libro(tmp_path / "libro.jsonl"))


def _saldo(k, cuenta):
    return k.saldo(cuenta, t.Divisa.CRISTAL)


# -- el conjunto cerrado de cuentas (trampa 1) -----------------------------
def test_la_cuenta_se_deriva_no_se_escribe_a_mano(k):
    assert FAB == "cristal:claude_max:fabrica"
    assert PER == "cristal:claude_max:personal"
    assert t.cuentas_cristal({"claude_max": SUS}) == {FAB, PER}
    assert t.cuentas_cristal(["a", "b"]) == {
        "cristal:a:fabrica", "cristal:a:personal",
        "cristal:b:fabrica", "cristal:b:personal"}


def test_zona_desconocida_no_construye_cuenta():
    with pytest.raises(t.AsientoInvalido):
        t.cuenta_cristal("claude_max", "direccion")
    with pytest.raises(t.AsientoInvalido):
        t.cuenta_cristal("claude_max", "Fabrica")


def test_nombre_de_suscripcion_ambiguo_no_construye_cuenta():
    for malo in ["Claude_Max", "claude max", "claude:max", "", "_x", ":"]:
        with pytest.raises(t.AsientoInvalido):
            t.cuenta_cristal(malo, "fabrica")


def test_una_cuenta_mal_tipeada_no_valida(k):
    """Lo que un `startswith` habria dejado pasar.

    "cristal:claude_maxx:fabrica" empieza con "cristal:" igual que la
    buena, y se comeria cristales sin que nadie lo note. El validador no
    mira el prefijo: exige que la cuenta sea EXACTAMENTE la derivada de la
    suscripcion y la zona que el propio asiento declara.
    """
    mala = "cristal:claude_maxx:fabrica"
    assert mala.startswith(t.PREFIJO_CRISTAL + ":")  # un prefijo la aceptaria
    with pytest.raises(t.AsientoInvalido):
        k.libro.append(ts=TS, semana="2026-W35",
                       tipo=t.TipoAsiento.EMISION_CRISTAL,
                       divisa=t.Divisa.CRISTAL, monto=800, destino=mala,
                       detalle={"suscripcion": "claude_max",
                                "zona": "fabrica"})
    assert k.libro.asientos() == []


def test_cristal_exige_declarar_suscripcion_y_zona(k):
    with pytest.raises(t.AsientoInvalido):
        k.libro.append(ts=TS, semana="2026-W35",
                       tipo=t.TipoAsiento.CONSUMO_CRISTAL,
                       divisa=t.Divisa.CRISTAL, monto=10, origen=FAB,
                       detalle={"suscripcion": "claude_max"})


def test_cristal_exige_su_divisa_y_su_direccion(k):
    with pytest.raises(t.AsientoInvalido):  # divisa ajena
        k.libro.append(ts=TS, semana="2026-W35",
                       tipo=t.TipoAsiento.EMISION_CRISTAL,
                       divisa=t.Divisa.PT, monto=800, destino=FAB,
                       detalle={"suscripcion": "claude_max", "zona": "fabrica"})
    with pytest.raises(t.AsientoInvalido):  # emision con origen
        k.libro.append(ts=TS, semana="2026-W35",
                       tipo=t.TipoAsiento.EMISION_CRISTAL,
                       divisa=t.Divisa.CRISTAL, monto=800, origen=PER,
                       destino=FAB,
                       detalle={"suscripcion": "claude_max", "zona": "fabrica"})
    with pytest.raises(t.AsientoInvalido):  # consumo con destino
        k.libro.append(ts=TS, semana="2026-W35",
                       tipo=t.TipoAsiento.CONSUMO_CRISTAL,
                       divisa=t.Divisa.CRISTAL, monto=10, origen=FAB,
                       destino=PER,
                       detalle={"suscripcion": "claude_max", "zona": "fabrica"})


def test_las_ramas_de_moneda_rechazan_la_divisa_cristal(k):
    """La tercera divisa no se cuela por la puerta de la plata."""
    for tipo, campos in [
        (t.TipoAsiento.ACUNACION, {"destino": "dep:a",
                                   "subtipo": "capital",
                                   "detalle": {"evidencia": {"x": 1}}}),
        (t.TipoAsiento.DESTRUCCION, {"origen": "dep:a"}),
        (t.TipoAsiento.TRANSFERENCIA, {"origen": "dep:a", "destino": "dep:b"}),
        (t.TipoAsiento.RESERVA, {"origen": "dep:a", "ref": "r-1"}),
        (t.TipoAsiento.LIBERACION, {"ref": "r-1"}),
        (t.TipoAsiento.EJECUCION_RESERVA, {"origen": "dep:a",
                                           "destino": "dep:b", "ref": "r-1"}),
    ]:
        with pytest.raises(t.AsientoInvalido):
            t.Asiento(seq=1, ts=TS, semana="2026-W35", tipo=tipo,
                      divisa=t.Divisa.CRISTAL, monto=10, **campos).validar()


# -- emision ---------------------------------------------------------------
def test_emitir_ciclo_parte_fabrica_y_personal(k):
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    assert _saldo(k, FAB) == 800
    assert _saldo(k, PER) == 200


def test_no_se_emite_dos_veces_el_mismo_ciclo(k):
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    with pytest.raises(cristal.ErrorCristal):
        cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    assert _saldo(k, FAB) == 800  # y no duplico nada


def test_emision_parcial_se_completa_en_la_re_llamada(k):
    """Recuperacion: si solo un pool quedo emitido, la re-llamada completa
    el otro en vez de rebotar el ciclo entero."""
    k.libro.append(ts=TS, semana="2026-W35",
                   tipo=t.TipoAsiento.EMISION_CRISTAL,
                   divisa=t.Divisa.CRISTAL, monto=800, destino=FAB,
                   detalle={"suscripcion": "claude_max", "zona": "fabrica",
                            "ciclo": 0, "motivo": cristal.MOTIVO_CUOTA,
                            "capacidad": 800, "reserva": 200})
    out = cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    assert [a.destino for a in out] == [PER]
    assert _saldo(k, FAB) == 800 and _saldo(k, PER) == 200


def test_re_llamada_con_otro_split_es_error(k):
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    otra = cap.Suscripcion("claude_max", 100_000, 2_000, 200, 500)
    with pytest.raises(cristal.ErrorCristal):
        cristal.emitir_ciclo(k, TS, "2026-W35", 0, otra)


def test_no_se_emite_sobre_un_pool_sin_barrer(k):
    """La capacidad no se acumula: la suscripcion resetea, no ahorra.
    Que el pool este en cero es la prueba de que el ciclo anterior cerro."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 100, titular="dep:a")
    with pytest.raises(cristal.ErrorCristal):
        cristal.emitir_ciclo(k, TS, "2026-W39", 1, SUS)
    assert _saldo(k, FAB) == 700  # ni un cristal de mas


def test_reserva_personal_cero_no_abre_pool_personal(k):
    sus = cap.Suscripcion("chatgpt_plus", 100_000, 1_000, 0, 500)
    out = cristal.emitir_ciclo(k, TS, "2026-W35", 0, sus)
    assert len(out) == 1
    assert _saldo(k, t.cuenta_cristal("chatgpt_plus", "personal")) == 0


def test_ciclo_debe_ser_entero_no_negativo(k):
    for malo in [-1, "0", 1.0, True]:
        with pytest.raises(cristal.ErrorCristal):
            cristal.emitir_ciclo(k, TS, "2026-W35", malo, SUS)


# -- consumo ---------------------------------------------------------------
def test_consumir_descuenta_del_pool_de_su_zona(k):
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    a = cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 300, titular="dep:a")
    assert a.origen == FAB and a.monto == 300
    assert a.detalle["titular"] == "dep:a"
    assert "descubierto" not in a.detalle
    assert _saldo(k, FAB) == 500 and _saldo(k, PER) == 200
    cristal.consumir_personal(k, TS, "2026-W35", SUS, 50,
                              titular="personal:finanzas")
    assert _saldo(k, PER) == 150


def test_consumir_nunca_rechaza_y_deja_descubierto(k):
    """Cuando llega el cargo el modelo ya contesto: el consumo se asienta
    igual y la cuenta queda en negativo. Un recurso que MIDE un hecho
    consumado puede quedar en descubierto."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 800, titular="dep:a")
    assert _saldo(k, FAB) == 0
    a = cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 120, titular="dep:a")
    assert a.monto == 120                 # se asento entero
    assert a.detalle["descubierto"] == 120
    assert _saldo(k, FAB) == -120
    assert cristal.descubierto(k, SUS, "fabrica") == 120
    # y sigue sin rechazar con el pool ya en negativo
    b = cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 30, titular="dep:a")
    assert b.detalle["descubierto"] == 30
    assert _saldo(k, FAB) == -150


def test_consumo_a_caballo_declara_solo_la_parte_sin_respaldo(k):
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    a = cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 900, titular="dep:a")
    assert a.detalle["descubierto"] == 100  # 800 con respaldo, 100 sin
    assert _saldo(k, FAB) == -100


def test_consumir_sin_pool_emitido_tampoco_rechaza(k):
    """El caso que hoy rompe: el cargo llega y no hay nada emitido. Se
    asienta igual — el libro no puede anotar cero unidades de algo que se
    consumio de verdad."""
    a = cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 5, titular="dep:a")
    assert a.monto == 5 and a.detalle["descubierto"] == 5
    assert _saldo(k, FAB) == -5


def test_consumo_de_cero_unidades_no_escribe_nada(k):
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    antes = len(k.libro.asientos())
    assert cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 0,
                                    titular="dep:a") is None
    assert cristal.consumir_fabrica(k, TS, "2026-W35", SUS, -3,
                                    titular="dep:a") is None
    assert len(k.libro.asientos()) == antes


def test_llamado_malformado_si_es_ruidoso(k):
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    with pytest.raises(cristal.ErrorCristal):
        cristal.consumir(k, TS, "2026-W35", SUS, "fabrica", "3", "dep:a")
    with pytest.raises(cristal.ErrorCristal):
        cristal.consumir(k, TS, "2026-W35", SUS, "direccion", 3, "dep:a")
    with pytest.raises(cristal.ErrorCristal):
        cristal.consumir(k, TS, "2026-W35", SUS, "fabrica", 3, "")


def test_el_consumo_no_toca_una_sola_moneda(k):
    k.acunar(TS, "2026-W35", "dep:a", 10_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 900, titular="dep:a")
    assert k.saldo("dep:a", t.Divisa.MONEDA) == 10_000
    assert k.disponible("dep:a") == 10_000


# -- cierre de ciclo -------------------------------------------------------
def test_expirar_pierde_lo_que_no_se_uso(k):
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 300, titular="dep:a")
    out = cristal.expirar_ciclo(k, TS, "2026-W38", 0, SUS)
    assert {a.origen: a.monto for a in out} == {FAB: 500, PER: 200}
    assert _saldo(k, FAB) == 0 and _saldo(k, PER) == 0


def test_expirar_con_saldo_negativo_no_revienta_el_cierre(k):
    """La trampa de `pt.expirar_pools`: `if resto:` da True con -100 y el
    validador exige monto entero POSITIVO. Con un pool en descubierto ese
    cierre levantaba AsientoInvalido a mitad de camino y el ciclo no
    cerraba nunca."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 950, titular="dep:a")
    assert _saldo(k, FAB) == -150

    out = cristal.expirar_ciclo(k, TS, "2026-W38", 0, SUS)  # no levanta
    condonacion = next(a for a in out if a.destino == FAB)
    assert condonacion.tipo is t.TipoAsiento.EMISION_CRISTAL
    assert condonacion.monto == 150
    assert condonacion.detalle["motivo"] == cristal.MOTIVO_CONDONACION
    assert _saldo(k, FAB) == 0   # el ciclo cierra en cero exacto
    assert _saldo(k, PER) == 0

    # y por eso el ciclo siguiente PUEDE abrir: el descubierto no se
    # arrastra ni deja el medidor trabado para siempre
    cristal.emitir_ciclo(k, TS, "2026-W39", 1, SUS)
    assert _saldo(k, FAB) == 800


def test_expirar_un_pool_ya_en_cero_no_escribe(k):
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 800, titular="dep:a")
    cristal.consumir_personal(k, TS, "2026-W35", SUS, 200,
                              titular="personal:finanzas")
    assert cristal.expirar_ciclo(k, TS, "2026-W38", 0, SUS) == []


def test_cerrar_ciclo_barre_todas_las_suscripciones(k):
    otra = cap.Suscripcion("chatgpt_plus", 50_000, 400, 100, 300)
    subs = {"claude_max": SUS, "chatgpt_plus": otra}
    for sus in subs.values():
        cristal.emitir_ciclo(k, TS, "2026-W35", 0, sus)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 900, titular="dep:a")
    c = cristal.cerrar_ciclo(k, TS, "2026-W38", 0, subs)
    assert c.ciclo == 0
    assert c.condonado == {FAB: 100}
    assert c.expirado == {PER: 200,
                          t.cuenta_cristal("chatgpt_plus", "fabrica"): 300,
                          t.cuenta_cristal("chatgpt_plus", "personal"): 100}
    assert not [v for (cuenta, div), v in saldos(k.libro.asientos()).items()
                if div is t.Divisa.CRISTAL and v != 0]  # todos en cero


# -- conservacion ----------------------------------------------------------
def _conservacion(k):
    emitido, consumido, expirado = cristal.totales(k.libro.asientos())
    suma = sum(v for (_c, div), v in saldos(k.libro.asientos()).items()
               if div is t.Divisa.CRISTAL)
    return emitido - consumido - expirado, suma


def test_conservacion_emitido_menos_consumido_menos_expirado(k):
    otra = cap.Suscripcion("chatgpt_plus", 50_000, 400, 100, 300)
    subs = {"claude_max": SUS, "chatgpt_plus": otra}

    for sus in subs.values():
        cristal.emitir_ciclo(k, TS, "2026-W35", 0, sus)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 300, titular="dep:a")
    cristal.consumir_personal(k, TS, "2026-W36", SUS, 250,   # descubierto
                              titular="personal:finanzas")
    cristal.consumir_fabrica(k, TS, "2026-W36", otra, 400, titular="dep:b")
    izq, der = _conservacion(k)
    assert izq == der

    cristal.cerrar_ciclo(k, TS, "2026-W38", 0, subs)
    izq, der = _conservacion(k)
    assert izq == der == 0  # ciclo cerrado: todos los pools en cero

    for sus in subs.values():
        cristal.emitir_ciclo(k, TS, "2026-W39", 1, sus)
    cristal.consumir_fabrica(k, TS, "2026-W39", SUS, 100, titular="dep:a")
    izq, der = _conservacion(k)
    assert izq == der == 800 - 100 + 200 + 300 + 100


def test_el_invariante_global_de_monedas_sigue_filtrado_por_divisa(k):
    """La tercera divisa no entra en la suma de la plata."""
    k.acunar(TS, "2026-W35", t.TESORO, 500_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    k.transferir(TS, "2026-W35", t.TESORO, "dep:a", 200_000, motivo="x")
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 900, titular="dep:a")
    s = saldos(k.libro.asientos())
    acunado = sum(a.monto for a in k.libro.asientos()
                  if a.tipo is t.TipoAsiento.ACUNACION)
    destruido = sum(a.monto for a in k.libro.asientos()
                    if a.tipo is t.TipoAsiento.DESTRUCCION)
    total_moneda = sum(v for (_c, div), v in s.items()
                       if div is t.Divisa.MONEDA)
    assert total_moneda == acunado - destruido == 500_000


def test_reproducible_reconstruyendo_desde_disco(k):
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 900, titular="dep:a")
    cristal.cerrar_ciclo(k, TS, "2026-W38", 0, {"claude_max": SUS})
    k2 = Kernel(Libro(k.libro.ruta))
    assert saldos(k2.libro.asientos()) == saldos(k.libro.asientos())
    assert cristal.totales(k2.libro.asientos()) == \
        cristal.totales(k.libro.asientos())


# -- el acople con el cierre (trampa 3) ------------------------------------
def test_el_acople_de_primera_semana_es_real(k):
    """El control del test de abajo: `cierre._primera_semana` SI da por
    nacido a un departamento que aparece en `detalle["departamento"]`. Por
    eso el consumo de cristales usa `titular` y no esa clave."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 10, titular="dep:a")
    assert cierre._primera_semana(k.libro.asientos(), "dep:a") is None

    # la clave equivocada, en el mismo libro, lo hace nacer
    k.apuntar(TS, "2026-W35", 1, {"nota": "x", "departamento": "dep:a"})
    assert cierre._primera_semana(k.libro.asientos(), "dep:a") == "2026-W35"


def test_consumir_cristales_no_declara_en_quiebra_a_nadie(tmp_path):
    """El test que prueba que la trampa 3 esta cerrada.

    El cierre declara la quiebra de todo departamento nacido con
    `k.disponible(cuenta) <= 0` EN MONEDAS. `dep:a` no tiene una sola
    moneda; si el consumo de cristales lo hiciera nacer, el cierre
    siguiente lo congelaria por gastar capacidad que no cuesta plata.
    """
    k = Kernel(Libro(tmp_path / "libro.jsonl"))
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=0,
                             techo_api_ciclo_mm=500_000))
    m = mkt.Mercado(k, r, {"claude_max": SUS})
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    k.acunar(TS, "2026-W30", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})

    pt.emitir_semana(k, TS, "2026-W30", 4_000, 0)
    cristal.emitir_ciclo(k, TS, "2026-W30", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W30", SUS, 300, titular="dep:a")
    c0 = cierre.cerrar_semana_economia(m, b, TS, "2026-W30")
    assert c0.quiebras == []

    pt.emitir_semana(k, TS, "2026-W31", 4_000, 0)
    # la segunda semana consume hasta el descubierto: ni asi
    cristal.consumir_fabrica(k, TS, "2026-W31", SUS, 900, titular="dep:a")
    assert k.saldo(FAB, t.Divisa.CRISTAL) == -400
    c1 = cierre.cerrar_semana_economia(m, b, TS, "2026-W31")

    assert c1.quiebras == []
    assert deps.es_congelado(k.libro.asientos(), "dep:a") is False
    assert k.disponible("dep:a") == 0  # cero monedas, y sigue sin quebrar
    assert cierre._primera_semana(k.libro.asientos(), "dep:a") is None


def test_api_publica_del_paquete():
    import calipso.economia as eco
    assert eco.cristal is cristal
