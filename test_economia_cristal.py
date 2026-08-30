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
    Un RESTO sin barrer (saldo > 0) bloquea la emision; un descubierto no,
    ver test_un_cargo_tardio_no_traba_la_apertura_del_ciclo."""
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
    cuota, consumido, expirado, condonado = cristal.totales(k.libro.asientos())
    suma = sum(v for (_c, div), v in saldos(k.libro.asientos()).items()
               if div is t.Divisa.CRISTAL)
    return cuota + condonado - consumido - expirado, suma


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


# -- el descubierto en pie no traba la apertura (el guard `!= 0`) -----------
def test_un_cargo_tardio_no_traba_la_apertura_del_ciclo(k):
    """`consumir` promete no rechazar nunca; `emitir_ciclo` exigia el pool
    en cero exacto. Las dos cosas juntas dejaban el ciclo IMPOSIBLE de
    abrir: un cargo llegado despues del cierre pone el pool en negativo y
    la fabrica corria el ciclo entero con cero cristales, cayendo al API
    caro — el desastre que la condonacion existe para evitar. Y no se
    autorecuperaba: cada reintento volvia a fallar."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 700, titular="dep:a")
    cristal.cerrar_ciclo(k, TS, "2026-W38", 0, {"claude_max": SUS})
    assert _saldo(k, FAB) == 0

    # el cargo tardio: mismo ts/semana viejos, como los replaya
    # `pagador.reintentar_pendientes`
    cristal.consumir_fabrica(k, TS, "2026-W38", SUS, 50, titular="dep:a")
    assert _saldo(k, FAB) == -50

    out = cristal.emitir_ciclo(k, TS, "2026-W39", 1, SUS)   # no levanta
    assert [a.destino for a in out] == [FAB, PER]
    assert _saldo(k, FAB) == 750   # el pool nuevo absorbe el descubierto
    assert _saldo(k, PER) == 200


def test_un_cargo_entre_el_cierre_y_la_emision_se_estampa_en_el_ciclo_nuevo(k):
    """El ciclo abierto DESPUES de un cierre es c+1, no el ultimo emitido.

    Gemelo del de arriba, que mira los SALDOS del pool: el pool no tiene
    ciclos —descuenta por orden de llegada— asi que ninguna de sus
    aserciones cambia si el ciclo estampado es el equivocado. Lo que se
    mira aca es el ESTAMPADO, que es la otra mitad de la promesa de
    `consumir`: el pool y `consumo_del_ciclo` tienen que contar lo mismo.

    Sin la rama que abre en c+1 tras un cierre, `_ciclo_abierto` se queda
    en el ultimo ciclo con cuota emitida y el cargo tardio cae en el ciclo
    0: el pliegue reporta 850 consumidos contra una cuota de 800 que
    ademas expiro 50 sin usar —imposible, y ademas roba el consumo al
    ciclo 1, que es el pool que de verdad lo paga (ver la emision de abajo,
    que nace con el descubierto descontado)."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 750, titular="dep:a")
    # cierre con resto: 50 expiran, y esa expiracion ES la marca de cierre.
    # Con resto CERO exacto no hay asiento y el rincon esta documentado en
    # `_ciclo_abierto`; por eso el consumo no llega a los 800.
    cristal.cerrar_ciclo(k, TS, "2026-W38", 0, {"claude_max": SUS})
    assert _saldo(k, FAB) == 0

    # el cargo tardio: llega despues del cierre y antes de la emision, con
    # el ts y la semana viejos, como los replaya `reintentar_pendientes`
    a = cristal.consumir_fabrica(k, TS, "2026-W38", SUS, 100, titular="dep:a")
    assert a.detalle["ciclo"] == 1

    asientos = k.libro.asientos()
    # el ciclo 0 cierra cuadrado: lo consumido mas lo expirado es la cuota
    assert cristal.consumo_del_ciclo(asientos, "claude_max", "fabrica", 0) == 750
    assert cristal.consumo_del_ciclo(asientos, "claude_max", "fabrica", 1) == 100
    # y el ciclo 1 lo paga de verdad: su cuota nace con el descubierto adentro
    cristal.emitir_ciclo(k, TS, "2026-W39", 1, SUS)
    assert _saldo(k, FAB) == 700


def test_el_bootstrap_no_queda_muerto(k):
    """El caso que el propio modulo declara legal: el cargo llega antes de
    que el ciclo 0 se abra. Si eso trabara la primera emision, el modulo
    quedaria muerto por construccion apenas se cablee el pagador."""
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 5, titular="dep:a")
    assert _saldo(k, FAB) == -5

    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)   # no levanta
    assert _saldo(k, FAB) == 795
    # y el consumo previo se atribuyo al ciclo que lo paga
    assert cristal.consumo_del_ciclo(k.libro.asientos(), "claude_max",
                                     "fabrica", 0) == 5


def test_un_resto_sin_barrer_bloquea_sin_escribir_nada(k):
    """El libro no tiene rollback: se validan los dos pools ANTES del
    primer append. Con el chequeo adentro del bucle, la emision de fabrica
    quedaba escrita para siempre y el llamador recibia la excepcion y
    descartaba el resultado: ciclo medio abierto, y ningun reintento lo
    arregla."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    # un cierre cortado a la mitad: expira fabrica y no personal
    k.libro.append(ts=TS, semana="2026-W38",
                   tipo=t.TipoAsiento.EXPIRACION_CRISTAL,
                   divisa=t.Divisa.CRISTAL, monto=800, origen=FAB,
                   detalle={"suscripcion": "claude_max", "zona": "fabrica",
                            "ciclo": 0})
    antes = len(k.libro.asientos())
    with pytest.raises(cristal.ErrorCristal, match="sin cerrar"):
        cristal.emitir_ciclo(k, TS, "2026-W39", 1, SUS)
    assert len(k.libro.asientos()) == antes   # ni un asiento
    assert _saldo(k, FAB) == 0 and _saldo(k, PER) == 200


def test_un_ciclo_cerrado_no_se_reabre(k):
    """Que el pool este en cero no prueba que el ciclo no haya cerrado:
    cero es, sobre todo, como lo deja el cierre. La re-llamada de
    recuperacion inyectaba cuota fresca en un ciclo muerto — capacidad
    inventada, para siempre, en un libro append-only."""
    k.libro.append(ts=TS, semana="2026-W35",
                   tipo=t.TipoAsiento.EMISION_CRISTAL,
                   divisa=t.Divisa.CRISTAL, monto=800, destino=FAB,
                   detalle={"suscripcion": "claude_max", "zona": "fabrica",
                            "ciclo": 0, "motivo": cristal.MOTIVO_CUOTA,
                            "capacidad": 800, "reserva": 200})
    cristal.consumir_personal(k, TS, "2026-W36", SUS, 120,
                              titular="personal:finanzas")
    cristal.expirar_ciclo(k, TS, "2026-W38", 0, SUS)   # cierra: expira y condona
    assert _saldo(k, FAB) == 0 and _saldo(k, PER) == 0

    with pytest.raises(cristal.ErrorCristal, match="ya cerrado"):
        cristal.emitir_ciclo(k, TS, "2026-W39", 0, SUS)
    assert _saldo(k, PER) == 0
    # y el ciclo siguiente si abre: no quedo trabado por el anterior
    cristal.emitir_ciclo(k, TS, "2026-W39", 1, SUS)
    assert _saldo(k, FAB) == 800


def test_un_ciclo_viejo_no_se_reabre_ni_sin_asiento_de_cierre(k):
    """La segunda marca de cierre: la cuota de un ciclo POSTERIOR ya
    emitida. Cubre el cierre que no escribio nada porque los dos pools
    quedaron exactos en cero."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 800, titular="dep:a")
    cristal.consumir_personal(k, TS, "2026-W35", SUS, 200,
                              titular="personal:finanzas")
    assert cristal.cerrar_ciclo(k, TS, "2026-W38", 0,
                                {"claude_max": SUS}).expirado == {}
    cristal.emitir_ciclo(k, TS, "2026-W39", 1, SUS)
    with pytest.raises(cristal.ErrorCristal, match="ya cerrado"):
        cristal.emitir_ciclo(k, TS, "2026-W43", 0, SUS)


def test_la_idempotencia_es_por_ciclo_y_motivo(k):
    """Con los dos pools barridos a cero por el CONSUMO (no por el cierre),
    la re-llamada tiene que rebotar por 'ya emitido' y no por otra guarda:
    si la llave (ciclo, motivo) del detalle se pierde, el ciclo se emite
    dos veces y la capacidad inventada queda para siempre."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 800, titular="dep:a")
    cristal.consumir_personal(k, TS, "2026-W35", SUS, 200,
                              titular="personal:finanzas")
    assert _saldo(k, FAB) == 0 and _saldo(k, PER) == 0

    with pytest.raises(cristal.ErrorCristal, match="ya emitido"):
        cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    assert _saldo(k, FAB) == 0 and _saldo(k, PER) == 0
    cuota, consumido, _exp, _cond = cristal.totales(k.libro.asientos())
    assert (cuota, consumido) == (1000, 1000)


def test_el_split_se_compara_entero_capacidad_y_reserva(k):
    """`capacidad_fabrica` es derivada, asi que un test que mueve
    `capacidad_ciclo` mueve las dos claves a la vez y no distingue si el
    guardia mira las dos. Aca la fabrica coincide y solo cambia la
    reserva."""
    k.libro.append(ts=TS, semana="2026-W35",
                   tipo=t.TipoAsiento.EMISION_CRISTAL,
                   divisa=t.Divisa.CRISTAL, monto=800, destino=FAB,
                   detalle={"suscripcion": "claude_max", "zona": "fabrica",
                            "ciclo": 0, "motivo": cristal.MOTIVO_CUOTA,
                            "capacidad": 800, "reserva": 200})
    otra = cap.Suscripcion("claude_max", 100_000, 2_000, 1_200, 500)
    assert otra.capacidad_fabrica == 800        # la mitad que coincide
    with pytest.raises(cristal.ErrorCristal, match="otro split"):
        cristal.emitir_ciclo(k, TS, "2026-W35", 0, otra)
    assert _saldo(k, PER) == 0


# -- la suscripcion tiene que ser una suscripcion ---------------------------
def test_los_verbos_exigen_una_suscripcion_configurada(k):
    """La ultima dimension de la trampa 1: que el nombre sea una
    suscripcion REAL. Estaba solo en la documentacion — cualquier objeto
    con `.nombre` abria un par de cuentas de cristal que despues nadie
    emite ni barre."""
    class Falsa:
        nombre = "inventada"

    d = deps.Departamento("a", deps.ZONA_FABRICA, presupuesto_semanal_mm=0,
                          techo_api_ciclo_mm=1)
    for impostor in [Falsa(), d, "claude_max", None]:
        with pytest.raises(cristal.ErrorCristal, match="Suscripcion"):
            cristal.consumir_fabrica(k, TS, "2026-W35", impostor, 7,
                                     titular="dep:a")
        with pytest.raises(cristal.ErrorCristal, match="Suscripcion"):
            cristal.emitir_ciclo(k, TS, "2026-W35", 0, impostor)
        with pytest.raises(cristal.ErrorCristal, match="Suscripcion"):
            cristal.expirar_ciclo(k, TS, "2026-W35", 0, impostor)
    assert k.libro.asientos() == []


def test_un_nombre_ambiguo_no_llega_a_construirse(k):
    """El fallo tardio que quedaba: la suscripcion se construia con
    cualquier nombre y recien explotaba contra el libro, con
    `AsientoInvalido` — una excepcion que el pagador no cuenta entre las
    economicas y que por lo tanto rompe el dispatch en vez de aparcar el
    cargo. Ahora rebota en el constructor, con el error de su capa."""
    for malo in ["Claude_Max", "claude max", "claude:max", "", "_x", 7]:
        with pytest.raises(cap.ErrorCapacidad, match="nombre de suscripcion"):
            cap.Suscripcion(malo, 100_000, 1_000, 200, 500)


def test_saldo_y_descubierto_validan_su_zona(k):
    """Dos funciones de LECTURA que filtraban `AsientoInvalido` desde la
    capa de tipos, distinto de lo que levantan `cupo` y `consumir` para el
    mismo error del llamador."""
    for zona in ["direccion", "Fabrica", ""]:
        with pytest.raises(cristal.ErrorCristal, match="zona invalida"):
            cristal.saldo(k, SUS, zona)
        with pytest.raises(cristal.ErrorCristal, match="zona invalida"):
            cristal.descubierto(k, SUS, zona)
        with pytest.raises(cristal.ErrorCristal, match="zona invalida"):
            cristal.cupo(SUS, zona)


# -- el ciclo del consumo: el pool y el pliegue cuentan lo mismo -----------
def test_el_consumo_se_atribuye_al_ciclo_del_que_sale(k):
    """El pool descuenta por orden de llegada; el pliegue atribuia por
    `semana`. Un cargo reintentado conserva su semana vieja, asi que salia
    del pool del ciclo NUEVO y se contaba en el VIEJO: un ciclo cerrado en
    cero declarando mas consumo del que su cuota podia respaldar."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W36", SUS, 300, titular="dep:a")
    cristal.cerrar_ciclo(k, TS, "2026-W38", 0, {"claude_max": SUS})
    cristal.emitir_ciclo(k, TS, "2026-W39", 1, SUS)
    # el reintento: semana del hecho (ciclo 0), pool del ciclo 1
    a = cristal.consumir_fabrica(k, TS, "2026-W36", SUS, 200, titular="dep:a")
    assert a.semana == "2026-W36" and a.detalle["ciclo"] == 1

    A = k.libro.asientos()
    assert cristal.consumo_del_ciclo(A, "claude_max", "fabrica", 0) == 300
    assert cristal.consumo_del_ciclo(A, "claude_max", "fabrica", 1) == 200
    # y el pliegue cuadra con el pool, que es lo que se rompia
    assert 800 - cristal.consumo_del_ciclo(A, "claude_max", "fabrica", 1) \
        == _saldo(k, FAB) == 600


def test_un_consumo_en_semana_sin_emision_de_pt_igual_se_cuenta(k):
    """`semanas_del_ciclo` sale de las semanas con EMISION_PT; la
    suscripcion sirve requests igual en una semana que Pedro no abrio. Por
    semana, esos cristales eran invisibles para la auditoria del ciclo
    mientras el pool si los descontaba."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W36", SUS, 100, titular="dep:a")
    cristal.consumir_fabrica(k, TS, "2026-W40", SUS, 300, titular="dep:a")
    A = k.libro.asientos()
    assert cristal.consumo_del_ciclo(A, "claude_max", "fabrica", 0) == 400
    assert 800 - 400 == _saldo(k, FAB)


def test_la_deuda_de_una_zona_sin_cuota_queda_atada_a_su_ciclo(k):
    """Con `reserva_personal = 0` el pool personal no se emite nunca, pero
    `consumir_personal` escribe igual: el descubierto cruza al ciclo
    siguiente. Que cruce el saldo es una cosa; que se pierda de vista de
    que ciclo viene, otra."""
    sus = cap.Suscripcion("chatgpt_plus", 100_000, 1_000, 0, 500)
    per = t.cuenta_cristal("chatgpt_plus", "personal")
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, sus)
    cristal.consumir_personal(k, TS, "2026-W35", sus, 40,
                              titular="personal:finanzas")
    cristal.cerrar_ciclo(k, TS, "2026-W38", 0, {"chatgpt_plus": sus})
    assert _saldo(k, per) == 0                     # el cierre lo condono
    A = k.libro.asientos()
    assert cristal.consumo_del_ciclo(A, "chatgpt_plus", "personal", 0) == 40


# -- pliegues de lectura ---------------------------------------------------
def test_totales_no_confunde_cuota_con_condonacion(k):
    """La condonacion es una `emision_cristal`, pero no es capacidad
    concedida: sumada al mismo total, el descubierto se autocancelaba y un
    medidor de uso no podia pasar de 100% nunca."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 950, titular="dep:a")
    cristal.consumir_personal(k, TS, "2026-W35", SUS, 200,
                              titular="personal:finanzas")
    assert cristal.totales(k.libro.asientos()) == (1000, 1150, 0, 0)

    cristal.cerrar_ciclo(k, TS, "2026-W38", 0, {"claude_max": SUS})
    cuota, consumido, expirado, condonado = cristal.totales(k.libro.asientos())
    assert (cuota, consumido, expirado, condonado) == (1000, 1150, 0, 150)
    assert consumido * 100 // cuota == 115   # y no 100


def test_cupo_es_el_split_de_la_suscripcion():
    assert cristal.cupo(SUS, "fabrica") == 800
    assert cristal.cupo(SUS, "personal") == 200


def test_descubierto_es_cero_con_el_pool_sano(k):
    """El unico assert que habia lo media con el pool ya en negativo, o
    sea justo donde el `max(0, ...)` no hace nada."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 300, titular="dep:a")
    assert _saldo(k, FAB) == 500
    assert cristal.descubierto(k, SUS, "fabrica") == 0
    assert cristal.descubierto(k, SUS, "personal") == 0


# -- forma de los asientos -------------------------------------------------
def test_el_consumo_conserva_la_ref_de_quien_lo_causo(k):
    """La ref es lo que ata el cargo de capacidad al turno o job que lo
    causo: sin ella el asiento no es auditable."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    a = cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 10, titular="dep:a",
                                 ref="turno-77")
    assert a.ref == "turno-77"
    b = cristal.consumir_personal(k, TS, "2026-W35", SUS, 3,
                                  titular="personal:finanzas", ref="job-9")
    assert b.ref == "job-9"


def test_titular_y_unidades_exigen_su_tipo(k):
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    for titular in [None, 7, ["dep:a"]]:
        with pytest.raises(cristal.ErrorCristal, match="titular"):
            cristal.consumir(k, TS, "2026-W35", SUS, "fabrica", 3, titular)
    for unidades in [True, False, 3.0, "3"]:
        with pytest.raises(cristal.ErrorCristal, match="unidades"):
            cristal.consumir(k, TS, "2026-W35", SUS, "fabrica", unidades,
                             "dep:a")


def test_el_cierre_declara_el_ciclo_que_cierra(k):
    """Un asiento de cierre sin su ciclo (o con otro) atribuye el cierre al
    ciclo equivocado para siempre."""
    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    cristal.consumir_fabrica(k, TS, "2026-W35", SUS, 900, titular="dep:a")
    out = cristal.expirar_ciclo(k, TS, "2026-W38", 0, SUS)
    porcuenta = {a.destino or a.origen: a for a in out}
    assert porcuenta[FAB].detalle == {"suscripcion": "claude_max",
                                      "zona": "fabrica", "ciclo": 0,
                                      "motivo": cristal.MOTIVO_CONDONACION}
    assert porcuenta[PER].detalle == {"suscripcion": "claude_max",
                                      "zona": "personal", "ciclo": 0}


def test_cerrar_ciclo_barre_en_orden_de_nombre(k):
    """El orden que promete el docstring: reproducible, no el del dict."""
    a = cap.Suscripcion("aaa_plus", 50_000, 400, 100, 300)
    z = cap.Suscripcion("zzz_max", 50_000, 400, 100, 300)
    for sus in (z, a):
        cristal.emitir_ciclo(k, TS, "2026-W35", 0, sus)
    c = cristal.cerrar_ciclo(k, TS, "2026-W38", 0,
                             {"zzz_max": z, "aaa_plus": a})
    assert list(c.expirado) == ["cristal:aaa_plus:fabrica",
                                "cristal:aaa_plus:personal",
                                "cristal:zzz_max:fabrica",
                                "cristal:zzz_max:personal"]


def test_cerrar_ciclo_exige_que_la_clave_sea_el_nombre(k):
    """`mercado` y `capacidad` indexan por la CLAVE del dict y estampan esa
    en los asientos; `cristal` deriva sus cuentas de `sus.nombre`. Un
    `suscripciones.json` con las dos cosas distintas partia la misma
    suscripcion en dos, una por divisa, sin un solo error."""
    sus = cap.Suscripcion("claude_max", 100_000, 1_000, 200, 500)
    with pytest.raises(cristal.ErrorCristal, match="no es el nombre"):
        cristal.cerrar_ciclo(k, TS, "2026-W38", 0, {"claude_maxx": sus})
    assert k.libro.asientos() == []


# -- las puertas del validador (trampa 1, las tres ramas) ------------------
def test_las_tres_ramas_de_cristal_exigen_la_cuenta_derivada(k):
    """La emision, el consumo Y la expiracion. La de expiracion es por
    donde pasan `expirar_ciclo` y la condonacion."""
    mala = "cristal:claude_maxx:fabrica"
    detalle = {"suscripcion": "claude_max", "zona": "fabrica", "ciclo": 0}
    with pytest.raises(t.AsientoInvalido, match="exactamente"):
        k.libro.append(ts=TS, semana="2026-W38",
                       tipo=t.TipoAsiento.EXPIRACION_CRISTAL,
                       divisa=t.Divisa.CRISTAL, monto=500, origen=mala,
                       detalle=detalle)
    with pytest.raises(t.AsientoInvalido, match="exactamente"):
        k.libro.append(ts=TS, semana="2026-W38",
                       tipo=t.TipoAsiento.CONSUMO_CRISTAL,
                       divisa=t.Divisa.CRISTAL, monto=5, origen=mala,
                       detalle=detalle)
    with pytest.raises(t.AsientoInvalido, match="exactamente"):
        k.libro.append(ts=TS, semana="2026-W38",
                       tipo=t.TipoAsiento.EMISION_CRISTAL,
                       divisa=t.Divisa.CRISTAL, monto=5, destino=mala,
                       detalle=detalle)
    assert k.libro.asientos() == []


def test_el_apunte_y_la_acreencia_son_solo_de_plata(k):
    """Las dos ramas que `validar` no tenia. Los dos tipos no mueven
    saldos, pero se LEEN como monedas: `capacidad.consumo_personal` suma
    apuntes, y `kernel.liquidar` paga toda acreencia pendiente con
    transferencias en monedas sin mirar su divisa."""
    for divisa in [t.Divisa.CRISTAL, t.Divisa.PT]:
        with pytest.raises(t.AsientoInvalido, match="solo en monedas"):
            t.Asiento(seq=1, ts=TS, semana="2026-W35",
                      tipo=t.TipoAsiento.APUNTE, divisa=divisa, monto=10,
                      detalle={"nota": "x"}).validar()
        with pytest.raises(t.AsientoInvalido, match="solo en monedas"):
            t.Asiento(seq=1, ts=TS, semana="2026-W35",
                      tipo=t.TipoAsiento.ACREENCIA, divisa=divisa, monto=10,
                      ref="r-1", detalle={"acreedor": "dep:b",
                                          "deudor": "dep:a"}).validar()


def test_una_acreencia_en_cristal_no_puede_cobrar_monedas(k):
    """La forma en que la puerta entornada se explotaba: `liquidar` no
    filtra por divisa."""
    k.acunar(TS, "2026-W35", "dep:a", 50_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    with pytest.raises(t.AsientoInvalido):
        k.libro.append(ts=TS, semana="2026-W35",
                       tipo=t.TipoAsiento.ACREENCIA, divisa=t.Divisa.CRISTAL,
                       monto=7_000, ref="r-x",
                       detalle={"acreedor": "dep:b", "deudor": "dep:a"})
    assert k.acreencias_pendientes("dep:a") == []
    k.liquidar(TS, "2026-W35", "dep:a")
    assert k.saldo("dep:b", t.Divisa.MONEDA) == 0


def test_una_cuenta_fantasma_no_entra_ni_releyendo_el_libro(k):
    """El cierre por derivacion valia solo para la ESCRITURA: `de_json` no
    llama `validar`, asi que una linea escrita por fuera de `append` —otro
    proceso, una edicion, una restauracion— cargaba sin chistar y abria un
    pool de cristal con saldo vivo que `expirar_ciclo` no barre nunca
    (solo recorre las cuentas derivadas de la configuracion)."""
    from calipso.economia.libro import LibroCorrupto

    cristal.emitir_ciclo(k, TS, "2026-W35", 0, SUS)
    linea = t.Asiento(seq=2, ts=TS, semana="2026-W35",
                      tipo=t.TipoAsiento.CONSUMO_CRISTAL,
                      divisa=t.Divisa.CRISTAL, monto=9_999,
                      origen="cristal:claude_maxx:fabrica",
                      detalle={"suscripcion": "claude_max",
                               "zona": "fabrica"}).a_json()
    with k.libro.ruta.open("a", encoding="utf-8") as f:
        f.write(linea + "\n")
    with pytest.raises(LibroCorrupto, match="invalida"):
        Libro(k.libro.ruta)
