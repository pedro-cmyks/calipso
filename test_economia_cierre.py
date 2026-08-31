"""Tests del cierre semanal y mensual: el pulso de la economia."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import capacidad as cap
from calipso.economia import cierre
from calipso.economia import cristal
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


def _huella(m, semana="2026-W30", unidades=1):
    """Una unidad consumida, para que la suscripcion EXISTA en el libro.

    El color de un ciclo mide aprovechamiento de la cuota, y a una
    suscripcion que todavia no aparecia en el libro cuando el ciclo cerro
    no se la pinta de rojo: es el arranque en frio, no un ciclo malo (ver
    `cierre._rojo_de_ciclo`). Una unidad de 800 sigue estando muy por
    debajo del piso, asi que el ciclo es rojo igual — lo que cambia es que
    ahora hay algo que juzgar.
    """
    m.consumir_capacidad(TS, semana, "dep:a", "claude_max", unidades)


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


def test_el_color_mide_aprovechamiento_y_no_recaudacion(entorno):
    """Bajo costo hundido direccion no recauda NADA por la capacidad, asi
    que el criterio viejo (`recaudacion < costo_fabrica_mm`) pintaba de rojo
    todo ciclo posible y a los dos rojos el breaker le exigia firma a Pedro
    para renovar. Lo que decide una renovacion cuando la plata ya se gasto
    es otra pregunta: la uso la fabrica?"""
    k, m, b = entorno
    semanas = ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]
    _ciclo_completo(k, m, b, semanas)
    # 400 de 800: la mitad de la cuota, por encima del piso del 40%
    m.consumir_capacidad(TS, "2026-W30", "dep:a", "claude_max", 400)
    assert cap.recaudacion(k.libro.asientos(), "claude_max", semanas) == 0
    inf = cierre.cerrar_ciclo(m, TS, "2026-W33")[0]
    assert inf["consumido_ciclo"] == 400
    assert inf["recaudacion_mm"] == 0  # y aun asi verde
    assert inf["rojo"] is False and inf["renovada"] is True


def test_un_ciclo_que_desaprovecha_la_cuota_es_rojo(entorno):
    """El otro lado del mismo criterio: un ciclo donde la fabrica consumio
    el 12,5% de lo que Pedro pago es plata tirada, y eso es lo que la carta
    de renovacion tiene que decir."""
    k, m, b = entorno
    semanas = ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]
    _ciclo_completo(k, m, b, semanas)
    m.consumir_capacidad(TS, "2026-W30", "dep:a", "claude_max", 100)
    inf = cierre.cerrar_ciclo(m, TS, "2026-W33")[0]
    assert inf["consumido_ciclo"] == 100
    assert inf["rojo"] is True


def test_el_arranque_en_frio_no_arma_el_breaker(entorno):
    """Recien sembrada, la fabrica no consume nada porque todavia no existe:
    con el color midiendo aprovechamiento, los dos primeros ciclos darian
    rojo y el breaker le pediria firma a Pedro antes del primer request. A
    una suscripcion que todavia no aparecia en el libro no se la juzga —el
    mismo patron con el que las quiebras no matan a un departamento recien
    nacido— y la exencion se termina en cuanto hay una huella."""
    k, m, b = entorno
    _ciclo_completo(k, m, b, [f"2026-W{n}" for n in range(30, 38)])
    inf_0 = cierre.cerrar_ciclo(m, TS, "2026-W33")[0]
    assert inf_0["rojo"] is False  # no habia nada que juzgar
    inf_1 = cierre.cerrar_ciclo(m, TS, "2026-W37")[0]
    # el ciclo 1 ya se juzga (la estampa del ciclo 0 alcanza como huella),
    # pero un solo rojo no arma nada
    assert inf_1["rojo"] is True and inf_1["rojos_consecutivos"] == 1
    assert inf_1["requiere_firma"] is False and inf_1["renovada"] is True


def test_la_huella_del_arranque_en_frio_es_uso_o_juicio(entorno):
    """Que cuenta como "ya habia algo que juzgar", asiento por asiento.

    La lista es blanca porque la maquinaria de la cuota escribe con la
    misma clave `detalle["suscripcion"]` que un consumo: la emision del
    ciclo (que `operacion.abrir_semana` hace en la PRIMERA semana del ciclo
    0) y el barrido del cierre. Con "cualquier asiento con el nombre", esa
    emision anulaba la exencion justo en el ciclo que existe para proteger.
    Emitir una cuota no es usarla; barrer el pool tampoco."""
    k, m, b = entorno
    _semana(k, "2026-W30")
    sus = SUS["claude_max"]
    cristal.emitir_ciclo(k, TS, "2026-W30", 0, sus)
    cristal.expirar_ciclo(k, TS, "2026-W30", 0, sus)
    asientos = k.libro.asientos()
    assert [a.tipo for a in asientos if a.detalle.get("suscripcion")]
    assert cierre._primera_semana_suscripcion(asientos, "claude_max") is None
    # un consumo si es huella
    m.consumir_capacidad(TS, "2026-W31", "dep:a", "claude_max", 1)
    assert cierre._primera_semana_suscripcion(
        k.libro.asientos(), "claude_max") == "2026-W31"


def test_circuit_breaker_tras_dos_ciclos_rojos_sin_atender(entorno):
    k, m, b = entorno
    semanas = [f"2026-W{n}" for n in range(30, 38)]  # 2 ciclos, sin compras
    _ciclo_completo(k, m, b, semanas)
    _huella(m)
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
    _huella(m)
    cierre.cerrar_ciclo(m, TS, "2026-W33")
    informes = cierre.cerrar_ciclo(
        m, TS, "2026-W37",
        cartas_atendidas=frozenset({"renovacion:claude_max"}))
    inf = informes[0]
    # el breaker estaba ARMADO (dos rojos) y lo desarma la carta atendida:
    # sin los dos rojos este test pasaria sin probar nada
    assert inf["rojos_consecutivos"] == 2
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
    "rojo" se calcula contra la capacidad configurada DE HOY. Ese numero se
    mueve con la perilla que reprecia la capacidad
    (`POST /api/economia/suscripciones/{n}/capacidad`), asi que repreciar
    cambiaba retroactivamente el color de ciclos ya cerrados y con eso
    armaba o DESARMABA el breaker: dos ciclos rojos que exigian la firma de
    Pedro pasaban a uno, la suscripcion se renovaba sola y el breaker no
    aparecia nunca. Un ciclo cerrado tiene su color decidido, como sus
    asientos: se estampa al cerrar.

    La perilla es la MISMA con el criterio de aprovechamiento —de hecho
    entra mas derecho: `capacidad_fabrica` es el denominador del color, no
    ya un termino del costo prorrateado."""
    k, m, b = entorno
    m.registro.ajustar("a", presupuesto_semanal_mm=100_000)
    semanas = [f"2026-W{n}" for n in range(30, 38)]  # dos ciclos
    for i, sem in enumerate(semanas):
        _semana(k, sem)
        cierre.cerrar_semana_economia(m, b, TS, sem)
        if i == 0:
            m.comprar_capacidad(TS, sem, "dep:a", "claude_max", 100)

    ciclo_0 = ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]
    consumido = cap.consumo_fabrica(k.libro.asientos(), "claude_max", ciclo_0)
    # rojo con la capacidad de hoy (800 para la fabrica: el piso son 320
    # unidades) y verde con la que Pedro esta por aplicar (capacidad 220 ->
    # 20 para la fabrica, piso 8): justo la ventana donde el color cambia
    # de signo
    assert consumido == 100
    assert 8 < consumido < 320

    informes_0 = cierre.cerrar_ciclo(m, TS, "2026-W33")
    assert informes_0[0]["rojo"] is True

    # Pedro reprecia la capacidad medida entre los dos cierres
    m_repreciado = mkt.Mercado(
        k, m.registro,
        {"claude_max": cap.Suscripcion("claude_max", 100_000, 220, 200, 500)})
    assert m_repreciado.suscripciones["claude_max"].capacidad_fabrica < consumido

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
