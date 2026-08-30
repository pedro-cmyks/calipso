"""Tests del cierre semanal y mensual: el pulso de la economia."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import cierre
from calipso.economia import departamentos as deps
from calipso.economia import mercado as mkt
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"

SUS = {"claude_max": cap.Suscripcion("claude_max", 100_000, 1_000, 200, 500)}


@pytest.fixture
def entorno(tmp_path):
    k = Kernel(Libro(tmp_path / "libro.jsonl"))
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=10_000,
                             techo_api_ciclo_mm=500_000))
    r.alta(deps.Departamento("b", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=10_000,
                             techo_api_ciclo_mm=500_000))
    m = mkt.Mercado(k, r, SUS)
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    k.acunar(TS, "2026-W30", t.TESORO, 1_200_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    return k, m, b


def _semana(k, semana):
    pt.emitir_semana(k, TS, semana, 4_000, 0)


def test_cierre_semanal_asigna_declara_y_cierra(entorno):
    k, m, b = entorno
    _semana(k, "2026-W30")
    # dep:b gasta hasta quedar en cero para quebrar en el cierre
    cierre_0 = cierre.cerrar_semana_economia(m, b, TS, "2026-W30")
    assert k.saldo("dep:a") == 10_000 and k.saldo("dep:b") == 10_000
    assert cierre_0.quiebras == []
    # idempotencia: un reintento del mismo cierre no paga dos veces
    cierre.cerrar_semana_economia(m, b, TS, "2026-W30")
    assert k.saldo("dep:a") == 10_000 and k.saldo("dep:b") == 10_000
    m.gastar_api(TS, "2026-W30", "dep:b", 10_000)
    _semana(k, "2026-W31")
    c = cierre.cerrar_semana_economia(m, b, TS, "2026-W31")
    assert c.quiebras == ["dep:b"]
    assert deps.es_congelado(k.libro.asientos(), "dep:b")
    # el congelado no recibio presupuesto en ese cierre; el activo si
    assert k.saldo("dep:a") == 20_000
    assert k.saldo("dep:b") == 0
    # y el cierre siguiente no re-declara la quiebra
    _semana(k, "2026-W32")
    c2 = cierre.cerrar_semana_economia(m, b, TS, "2026-W32")
    assert c2.quiebras == []


def test_perilla_de_pedro_no_pasa_por_mandato(entorno):
    k, m, b = entorno
    m.registro.ajustar("a", presupuesto_semanal_mm=150_000)  # > umbral 100k
    _semana(k, "2026-W30")
    c = cierre.cerrar_semana_economia(m, b, TS, "2026-W30")
    assert not any(carta["tipo"] == "mandato" for carta in c.cartas)
    assert k.saldo("dep:a") == 150_000  # la perilla asigna sin pasar por el mandato
    asiento = next(a for a in k.libro.asientos()
                   if a.detalle.get("motivo") == "presupuesto"
                   and a.destino == "dep:a")
    assert asiento.detalle["firma"]["tipo"] == "perilla_pedro"


def test_carta_de_cierre_departamental(entorno):
    k, m, b = entorno
    semanas = [f"2026-W{n}" for n in range(30, 34)]
    for sem in semanas:
        _semana(k, sem)
        c = cierre.cerrar_semana_economia(m, b, TS, sem,
                                          ventana_carta_cierre=3)
    # tras 4 semanas operativas sin ventas, ambos deps tienen carta
    tipos = [carta["tipo"] for carta in c.cartas]
    assert tipos.count("cierre_departamento") == 2
    # una venta al dep la evita la semana siguiente
    k.acunar(TS, "2026-W33", "dep:a", 1_000, t.SubtipoAcunacion.VENTA,
             {"tipo": "firma_pedro"})
    _semana(k, "2026-W34")
    c2 = cierre.cerrar_semana_economia(m, b, TS, "2026-W34",
                                       ventana_carta_cierre=3)
    afectados = [carta["departamento"] for carta in c2.cartas
                 if carta["tipo"] == "cierre_departamento"]
    assert afectados == ["dep:b"]


def test_carta_de_cierre_con_primera_semana_no_operativa(entorno):
    """FIX I9: una primera semana no operativa no exime de la carta."""
    k, m, b = entorno
    k.acunar(TS, "2026-W28", "dep:a", 10_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})  # semana sin emision de PT
    semanas = ["2026-W30", "2026-W31", "2026-W32"]
    for sem in semanas:
        _semana(k, sem)
        c = cierre.cerrar_semana_economia(m, b, TS, sem,
                                          ventana_carta_cierre=3)
    afectados = [carta["departamento"] for carta in c.cartas
                 if carta["tipo"] == "cierre_departamento"]
    assert "dep:a" in afectados


def _ciclo_completo(k, m, b, semanas, unidades_por_semana=0):
    for sem in semanas:
        _semana(k, sem)
        cierre.cerrar_semana_economia(m, b, TS, sem)  # asigna presupuestos
        if unidades_por_semana:
            m.comprar_capacidad(TS, sem, "dep:a", "claude_max",
                                unidades_por_semana)


def test_cierre_de_ciclo_renueva_automatico_si_no_es_rojo(entorno):
    k, m, b = entorno
    m.registro.ajustar("a", presupuesto_semanal_mm=100_000)
    # 4 semanas comprando a ritmo la cuota completa (800 unidades a precio
    # base 100): recaudacion 80_000 == costo prorrateado -> no es rojo
    semanas = ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]
    _ciclo_completo(k, m, b, semanas, unidades_por_semana=200)
    tesoro_antes = k.saldo(t.TESORO)
    informes = cierre.cerrar_ciclo(m, TS, "2026-W33")
    inf = informes[0]
    assert inf["rojo"] is False and inf["renovada"] is True
    assert "eficiencia_pormil" in inf
    # FIX I6: la renovacion sale de direccion; direccion ya tenia la
    # recaudacion del ciclo (80_000), asi que el tesoro solo repone la
    # diferencia hasta el costo mensual (100_000 - 80_000 = 20_000)
    assert k.saldo(t.TESORO) == tesoro_antes - 20_000
    assert k.saldo(t.DIRECCION) == 0  # 80_000 + 20_000 - 100_000
    # idempotencia: un reintento no destruye el tesoro dos veces
    informes_bis = cierre.cerrar_ciclo(m, TS, "2026-W33")
    assert informes_bis[0]["renovada"] is True
    assert k.saldo(t.TESORO) == tesoro_antes - 20_000


def test_circuit_breaker_tras_dos_ciclos_rojos_sin_atender(entorno):
    k, m, b = entorno
    semanas = [f"2026-W{n}" for n in range(30, 38)]  # 2 ciclos, sin compras
    _ciclo_completo(k, m, b, semanas)
    informes_1 = cierre.cerrar_ciclo(m, TS, "2026-W33")
    assert informes_1[0]["rojo"] is True and informes_1[0]["renovada"] is True
    informes_2 = cierre.cerrar_ciclo(m, TS, "2026-W37")
    inf = informes_2[0]
    assert inf["rojos_consecutivos"] == 2
    assert inf["requiere_firma"] is True and inf["renovada"] is False
    # con firma, renueva
    informes_3 = cierre.cerrar_ciclo(m, TS, "2026-W37",
                                     firmas={"claude_max": {"tipo": "firma_pedro"}})
    assert informes_3[0]["renovada"] is True


def test_carta_atendida_desarma_el_breaker(entorno):
    k, m, b = entorno
    semanas = [f"2026-W{n}" for n in range(30, 38)]  # 2 ciclos, sin compras
    _ciclo_completo(k, m, b, semanas)
    cierre.cerrar_ciclo(m, TS, "2026-W33")
    informes = cierre.cerrar_ciclo(
        m, TS, "2026-W37",
        cartas_atendidas=frozenset({"renovacion:claude_max"}))
    inf = informes[0]
    assert inf["requiere_firma"] is False and inf["renovada"] is True


def test_renovacion_con_tesoro_agotado(tmp_path):
    """FIX I6/I8b: si ni el tesoro puede reponer a direccion, se informa
    en vez de reventar con un SinSaldo crudo."""
    k = Kernel(Libro(tmp_path / "libro.jsonl"))
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA,
                             presupuesto_semanal_mm=0,  # no toca el tesoro
                             techo_api_ciclo_mm=500_000))
    m = mkt.Mercado(k, r, SUS)
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    k.acunar(TS, "2026-W30", t.TESORO, 50_000,
             t.SubtipoAcunacion.CAPITAL, {"tipo": "firma_pedro"})
    semanas = ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]
    for sem in semanas:
        _semana(k, sem)
        cierre.cerrar_semana_economia(m, b, TS, sem)
    informes = cierre.cerrar_ciclo(m, TS, "2026-W33")
    inf = informes[0]
    assert inf["tesoro_insuficiente"] is True
    assert inf["renovada"] is False


def test_ciclo_incompleto_no_renueva(entorno):
    k, m, b = entorno
    _semana(k, "2026-W30")
    cierre.cerrar_semana_economia(m, b, TS, "2026-W30")
    assert cierre.cerrar_ciclo(m, TS, "2026-W30") == []


def test_repreciar_la_capacidad_no_repinta_un_ciclo_ya_cerrado(entorno):
    """El circuit breaker de renovacion cuenta ciclos rojos consecutivos, y
    "rojo" era `recaudacion(ciclo) < sus.costo_fabrica_mm DE HOY`. Ese
    numero se mueve con la perilla que reprecia la capacidad
    (`POST /api/economia/suscripciones/{n}/capacidad`), asi que repreciar
    cambiaba retroactivamente el color de ciclos ya cerrados y con eso
    armaba o DESARMABA el breaker: dos ciclos rojos que exigian la firma de
    Pedro pasaban a uno, la suscripcion se renovaba sola y el breaker no
    aparecia nunca. Un ciclo cerrado tiene su color decidido, como sus
    asientos: se estampa al cerrar."""
    k, m, b = entorno
    m.registro.ajustar("a", presupuesto_semanal_mm=100_000)
    semanas = [f"2026-W{n}" for n in range(30, 38)]  # dos ciclos
    for i, sem in enumerate(semanas):
        _semana(k, sem)
        cierre.cerrar_semana_economia(m, b, TS, sem)
        if i == 0:
            m.comprar_capacidad(TS, sem, "dep:a", "claude_max", 100)

    ciclo_0 = ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]
    recaudado = cap.recaudacion(k.libro.asientos(), "claude_max", ciclo_0)
    # rojo con la configuracion de hoy (costo_fabrica 80.000) y verde con
    # la que Pedro esta por aplicar (capacidad 220 -> costo_fabrica 9.090):
    # justo la ventana donde el color cambia de signo
    assert 9_090 < recaudado < 80_000

    informes_0 = cierre.cerrar_ciclo(m, TS, "2026-W33")
    assert informes_0[0]["rojo"] is True

    # Pedro reprecia la capacidad medida entre los dos cierres
    m_repreciado = mkt.Mercado(
        k, m.registro,
        {"claude_max": cap.Suscripcion("claude_max", 100_000, 220, 200, 500)})
    assert m_repreciado.suscripciones["claude_max"].costo_fabrica_mm < recaudado

    informes_1 = cierre.cerrar_ciclo(m_repreciado, TS, "2026-W37")
    inf = informes_1[0]
    assert inf["rojos_consecutivos"] == 2, "el ciclo 0 se repinto de verde"
    assert inf["requiere_firma"] is True and inf["renovada"] is False


def test_el_color_de_un_ciclo_se_estampa_una_sola_vez(entorno):
    """Idempotente: cerrar dos veces la misma semana no deja dos estampas,
    y la segunda corrida lee la primera."""
    k, m, b = entorno
    semanas = ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]
    _ciclo_completo(k, m, b, semanas)
    cierre.cerrar_ciclo(m, TS, "2026-W33")
    cierre.cerrar_ciclo(m, TS, "2026-W33")
    estampas = [a for a in k.libro.asientos()
                if a.tipo is t.TipoAsiento.APUNTE
                and a.detalle.get("nota") == cierre.NOTA_COLOR_CICLO]
    assert len(estampas) == 1
    assert estampas[0].detalle["suscripcion"] == "claude_max"
    assert estampas[0].detalle["ciclo"] == 0
