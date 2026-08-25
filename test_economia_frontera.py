"""Tests de la frontera: candado, fixes parkeados, cola, reloj, personal, operacion."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import candado as cnd
from calipso.economia import capacidad as cap
from calipso.economia import cola as cola_mod
from calipso.economia import departamentos as deps
from calipso.economia import direccion as dir_
from calipso.economia import mercado as mkt
from calipso.economia import pt
from calipso.economia import reloj as reloj_mod
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"

SUS = {"claude_max": cap.Suscripcion("claude_max", 100_000, 1_000, 200, 500)}


@pytest.fixture
def entorno(tmp_path):
    k = Kernel(Libro(tmp_path / "libro.jsonl"))
    r = deps.Registro(tmp_path / "departamentos.json")
    r.alta(deps.Departamento("a", deps.ZONA_FABRICA, techo_api_ciclo_mm=500_000))
    r.alta(deps.Departamento("b", deps.ZONA_FABRICA, techo_api_ciclo_mm=500_000))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    m = mkt.Mercado(k, r, SUS)
    b = bus_mod.Bus(tmp_path / "bus.jsonl")
    return k, m, b, tmp_path


def _capital(k, monto, destino):
    k.acunar(TS, "2026-W30", destino, monto, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})


def _semana_op(k, semana, cuota=4_000, reserva=0):
    pt.emitir_semana(k, TS, semana, cuota, reserva)


def test_candado_reentrante_y_exclusivo_entre_procesos(tmp_path):
    import subprocess
    import sys
    ruta = tmp_path / "libro.jsonl"
    sonda = ("import fcntl,sys\n"
             "f=open(sys.argv[1],'a')\n"
             "try:\n"
             "    fcntl.flock(f.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
             "    print('LIBRE')\n"
             "except BlockingIOError:\n"
             "    print('TOMADO')\n")
    lock = str(ruta) + ".lock"
    with cnd.candado(ruta):
        with cnd.candado(ruta):  # reentrante: no se bloquea a si mismo
            r = subprocess.run([sys.executable, "-c", sonda, lock],
                               capture_output=True, text=True)
            assert r.stdout.strip() == "TOMADO"  # otro proceso lo ve tomado
    r = subprocess.run([sys.executable, "-c", sonda, lock],
                       capture_output=True, text=True)
    assert r.stdout.strip() == "LIBRE"  # liberado al salir del todo


def test_contencion_no_bloqueante_no_rompe_el_candado(tmp_path):
    import subprocess
    import sys
    ruta = tmp_path / "libro.jsonl"
    lock = str(ruta) + ".lock"
    sostener = ("import fcntl,sys\n"
                "f=open(sys.argv[1],'a')\n"
                "fcntl.flock(f.fileno(), fcntl.LOCK_EX)\n"
                "print('HOLDING', flush=True)\n"
                "sys.stdin.readline()\n")
    proc = subprocess.Popen([sys.executable, "-c", sostener, lock],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            text=True)
    assert proc.stdout.readline().strip() == "HOLDING"
    try:
        with pytest.raises(cnd.ErrorCandado):
            with cnd.candado(ruta, no_bloquear=True):
                pass
    finally:
        proc.stdin.write("\n")
        proc.stdin.flush()
        proc.wait(timeout=10)
    # tras la contencion fallida, el candado DEBE seguir tomando el flock
    sonda = ("import fcntl,sys\n"
             "f=open(sys.argv[1],'a')\n"
             "try:\n"
             "    fcntl.flock(f.fileno(), fcntl.LOCK_EX|fcntl.LOCK_NB)\n"
             "    print('LIBRE')\n"
             "except BlockingIOError:\n"
             "    print('TOMADO')\n")
    with cnd.candado(ruta):
        r = subprocess.run([sys.executable, "-c", sonda, lock],
                           capture_output=True, text=True)
        assert r.stdout.strip() == "TOMADO"


def test_liquidacion_reanuda_sin_duplicar_pagos(entorno):
    """Fix parkeado del Plan 2: crash entre devoluciones no duplica pagos."""
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, "dep:a")
    _capital(k, 100_000, "dep:b")
    b.alta(TS, "2026-W30", "p1", "dep:a", "radar", 100_000, 300_000,
           {"gasto_max_mm": 25_000})
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:a", 60_000)
    bus_mod.financiar(m, b, TS, "2026-W30", "p1", "dep:b", 40_000)
    m.gastar_api(TS, "2026-W30", "trabajo:p1", 30_000, dueno="dep:a")  # muerto
    # simula un crash previo: la parte de dep:a (42_000 de 70_000) YA se pago
    k.transferir(TS, "2026-W30", "trabajo:p1", "dep:a", 42_000,
                 motivo="liquidacion_trabajo")
    muertos = bus_mod.evaluar_y_liquidar_muertos(m, b, TS, "2026-W30")
    assert muertos == ["p1"]
    assert k.saldo("trabajo:p1") == 0
    assert k.saldo("dep:a") == 100_000 - 60_000 + 42_000  # sin doble pago
    assert k.saldo("dep:b") == 100_000 - 40_000 + 28_000


def test_emision_se_recupera_por_pool(entorno):
    """Fix parkeado: un crash entre las dos emisiones se completa re-llamando."""
    k, m, b, _ = entorno
    # simula el crash: solo el pool de fabrica quedo emitido (3000 de 4000/1000)
    k.libro.append(ts=TS, semana="2026-W30", tipo=t.TipoAsiento.EMISION_PT,
                   divisa=t.Divisa.PT, monto=3_000, destino=t.POOL_PT_FABRICA)
    emitidos = pt.emitir_semana(k, TS, "2026-W30", 4_000, 1_000)
    assert len(emitidos) == 1 and emitidos[0].destino == t.POOL_PT_PERSONAL
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 3_000
    assert k.saldo(t.POOL_PT_PERSONAL, t.Divisa.PT) == 1_000
    with pytest.raises(pt.ErrorPT):
        pt.emitir_semana(k, TS, "2026-W30", 4_000, 1_000)  # nada pendiente


def test_recuperacion_exige_mismo_split(entorno):
    k, m, b, _ = entorno
    pt.emitir_semana(k, TS, "2026-W30", 4_000, 0)
    with pytest.raises(pt.ErrorPT):
        pt.emitir_semana(k, TS, "2026-W30", 5_000, 1_000)  # otro split


@pytest.fixture
def cola(entorno):
    k, m, b, tmp = entorno
    return cola_mod.Cola(tmp / "cola.jsonl")


def test_encolar_reserva_al_tipo_vigente(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "llamar cliente",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=90_000)
    # 500 mpt a tipo 5000 = 2500 mm reservados
    assert k.disponible("dep:a") == 47_500
    assert cola.estado("c1") == "encolada"
    with pytest.raises(cola_mod.ErrorCola):
        cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "repetida",
                     tipo="contacto", obligatoria=True, mpt_estimado=500,
                     monedas_en_juego=1)


def test_goteo_recarga_y_tiene_tope(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "g1", "dep:a", "urgente 1",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=10_000, carril=cola_mod.CARRIL_GOTEO)
    assert k.disponible("dep:a") == 45_000  # 2500 * 2 de recargo
    cola.encolar(k, TS, "2026-W30", "g2", "dep:a", "urgente 2",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=9_000, carril=cola_mod.CARRIL_GOTEO)
    with pytest.raises(cola_mod.ErrorCola):
        cola.encolar(k, TS, "2026-W30", "g3", "dep:a", "urgente 3",
                     tipo="contacto", obligatoria=True, mpt_estimado=500,
                     monedas_en_juego=8_000, carril=cola_mod.CARRIL_GOTEO)


def test_obligatoria_sin_caja_encola_con_adelanto(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    cola.encolar(k, TS, "2026-W30", "c2", "dep:b", "responder cliente",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=5_000)  # dep:b sin un peso
    p = [x for x in cola.pendientes() if x["id"] == "c2"][0]
    assert p["adelanto"] is True
    with pytest.raises(cola_mod.ErrorCola):
        cola.encolar(k, TS, "2026-W30", "c3", "dep:b", "opinion cara",
                     tipo="opinion", obligatoria=False, mpt_estimado=500,
                     monedas_en_juego=1_000)  # lo opcional si se rechaza


def test_orden_cartas_primero_y_monedas_en_juego(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "chica", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=1_000)
    cola.encolar(k, TS, "2026-W30", "c2", "dep:a", "grande", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=50_000)
    cola.encolar_carta(TS, "2026-W30", "k1", {"tipo": "mandato",
                                              "departamento": "dep:a"})
    orden = [x["id"] for x in cola.pendientes()]
    assert orden == ["k1", "c2", "c1"]


def test_atender_carta_y_registro_para_el_cierre(entorno, cola):
    k, m, b, _ = entorno
    cola.encolar_carta(TS, "2026-W30", "renovacion:claude_max",
                       {"tipo": "renovacion", "suscripcion": "claude_max"})
    cola.atender_carta(TS, "2026-W30", "renovacion:claude_max",
                       firma={"tipo": "firma_pedro"})
    assert "renovacion:claude_max" in cola.cartas_atendidas()
    assert cola.firmas()["renovacion:claude_max"] == {"tipo": "firma_pedro"}


def test_expirar_semana_libera_reservas(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "no atendida",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=1_000)
    expirados = cola.expirar_semana(k, TS, "2026-W30")
    assert expirados == ["c1"]
    assert k.disponible("dep:a") == 50_000
    assert cola.estado("c1") == "expirada"


def test_servir_cobra_tiempo_real_y_libera_reserva(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "llamar", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=9_000)
    # 42 minutos reales -> 700 mpt -> redondeo a 1000 mpt -> 5000 mm
    res = cola.servir(m, TS, "2026-W30", "c1", mpt_real=700)
    assert res["mpt_cobrado"] == 1_000 and res["cobro_mm"] == 5_000
    assert k.saldo(t.CUENTA_PEDRO) == 5_000
    assert k.saldo("dep:a") == 45_000
    assert k.disponible("dep:a") == 45_000  # la reserva de 2500 se libero
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 3_000
    assert cola.estado("c1") == "servida"
    with pytest.raises(cola_mod.ErrorCola):
        cola.servir(m, TS, "2026-W30", "c1", mpt_real=500)  # ya servida


def test_servir_goteo_cobra_recargo(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "g1", "dep:a", "urgente", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=9_000,
                 carril=cola_mod.CARRIL_GOTEO)
    res = cola.servir(m, TS, "2026-W30", "g1", mpt_real=500)
    assert res["cobro_mm"] == 5_000  # 500 mpt a 5000 x2 de recargo
    assert k.saldo(t.CUENTA_PEDRO) == 5_000


def test_servir_con_adelanto_de_direccion(entorno, cola):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, t.DIRECCION)
    cola.encolar(k, TS, "2026-W30", "c2", "dep:b", "responder",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=5_000)  # dep:b sin caja -> adelanto
    res = cola.servir(m, TS, "2026-W30", "c2", mpt_real=500)
    assert res["adelantado_mm"] == 2_500
    assert k.saldo(t.CUENTA_PEDRO) == 2_500
    assert k.acreencias_pendientes("dep:b") == \
        [("adelanto:c2", t.DIRECCION, 2_500)]


def test_servir_reanuda_sin_perder_la_acreencia(entorno, cola):
    """Crash entre la transferencia del adelanto y su acreencia: el reintento
    debe recuperar la deuda desde el libro, no perderla ni duplicar el pago."""
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 100_000, t.DIRECCION)
    cola.encolar(k, TS, "2026-W30", "cX", "dep:b", "responder",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=5_000)  # dep:b sin caja -> adelanto
    # simula el crash: la transferencia del adelanto ya se hizo, pero la
    # acreencia que la respalda nunca se registro
    k.transferir(TS, "2026-W30", t.DIRECCION, t.CUENTA_PEDRO, 2_500,
                 motivo="carta_sistema", ref="cola:cX")
    res = cola.servir(m, TS, "2026-W30", "cX", mpt_real=500)
    assert k.saldo(t.CUENTA_PEDRO) == 2_500  # sin doble pago
    assert k.acreencias_pendientes("dep:b") == \
        [("adelanto:cX", t.DIRECCION, 2_500)]  # la deuda se recupero
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 3_500
    assert cola.estado("cX") == "servida"


@pytest.fixture
def reloj(entorno):
    k, m, b, tmp = entorno
    return reloj_mod.Reloj(tmp / "reloj.jsonl")


def test_reloj_fabrica_sirve_la_compuerta(entorno, cola, reloj):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "llamar", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=9_000)
    with pytest.raises(reloj_mod.ErrorReloj):
        reloj.clock_in(TS, "2026-W30", "fabrica", ref="typo", cola=cola)
    reloj.clock_in("2026-08-25T10:00:00", "2026-W30", "fabrica", ref="c1",
                   cola=cola)
    with pytest.raises(reloj_mod.ErrorReloj):
        reloj.clock_in("2026-08-25T10:05:00", "2026-W30", "tuning")  # abierto
    res = reloj.clock_out(m, cola, "2026-08-25T10:42:00", "2026-W30")
    assert res["minutos"] == 42 and res["mpt_real"] == 700
    assert res["sin_cobro"] is False
    assert cola.estado("c1") == "servida"
    assert k.saldo(t.CUENTA_PEDRO) == 5_000  # 1000 mpt redondeados a 5000mm


def test_cobro_fallido_no_atasca_el_reloj(entorno, cola, reloj):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 50_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c9", "dep:a", "se expira", tipo="contacto",
                 obligatoria=True, mpt_estimado=500, monedas_en_juego=1_000)
    reloj.clock_in("2026-08-25T10:00:00", "2026-W30", "fabrica", ref="c9",
                   cola=cola)
    cola.expirar_semana(k, TS, "2026-W30")  # el cierre corrio con el tramo abierto
    res = reloj.clock_out(m, cola, "2026-08-25T10:30:00", "2026-W30")
    assert res["sin_cobro"] is True
    assert reloj.abierto() is None  # el reloj sigue operable
    assert k.saldo(t.CUENTA_PEDRO) == 0  # y no se cobro nada


def test_reloj_personal_consume_reserva(entorno, cola, reloj):
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30", cuota=4_000, reserva=1_000)
    reloj.clock_in("2026-08-25T09:00:00", "2026-W30", "personal",
                   ref="personal:finanzas")
    res = reloj.clock_out(m, cola, "2026-08-25T09:30:00", "2026-W30")
    assert res["mpt_real"] == 500
    assert k.saldo(t.POOL_PT_PERSONAL, t.Divisa.PT) == 500


def test_reloj_empleo_solo_registra(entorno, cola, reloj):
    k, m, b, _ = entorno
    reloj.clock_in("2026-08-25T08:00:00", "2026-W30", "empleo")
    reloj.clock_out(m, cola, "2026-08-25T16:00:00", "2026-W30")
    assert reloj.minutos_por_categoria(["2026-W30"]) == {"empleo": 480}


def test_huerfano_se_concilia_sin_inventar(entorno, cola, reloj):
    k, m, b, _ = entorno
    reloj.clock_in("2026-08-25T08:00:00", "2026-W30", "tuning")
    assert reloj.abierto() is not None
    huerfanos = reloj.huerfanos("2026-W31")
    assert len(huerfanos) == 1
    reloj.conciliar(TS, "2026-W31", huerfanos[0]["ts"], minutos=60)
    assert reloj.abierto() is None
    assert reloj.minutos_por_categoria(["2026-W30"]) == {"tuning": 60}


from calipso.economia import personal as per_mod


def test_libro_personal_registra_y_resume(entorno):
    k, m, b, tmp = entorno
    lp = per_mod.LibroPersonal(tmp / "personal.jsonl")
    lp.registrar(TS, "2026-W30", "ingreso", 2_500_000, "sueldo")
    lp.registrar(TS, "2026-W30", "gasto", 400_000, "suscripciones")
    lp.registrar(TS, "2026-W31", "gasto", 100_000, "comida")
    assert lp.resumen(["2026-W30"]) == {"ingresos_mm": 2_500_000,
                                        "gastos_mm": 400_000,
                                        "neto_mm": 2_100_000}
    assert lp.resumen()["neto_mm"] == 2_000_000
    with pytest.raises(per_mod.ErrorPersonal):
        lp.registrar(TS, "2026-W30", "prestamo", 1, "x")


def test_linea_empleo_medida_y_teorica():
    # 160 horas reales en el mes: 2.5M/160h = 15_625 mm/h
    assert per_mod.linea_empleo_mm_por_hora(2_500_000, 160 * 60) == 15_625
    assert per_mod.linea_empleo_mm_por_hora(2_500_000, 0) == 14_450  # /173


def test_tablero_consolida(entorno, reloj):
    k, m, b, tmp = entorno
    lp = per_mod.LibroPersonal(tmp / "personal.jsonl")
    _semana_op(k, "2026-W30", cuota=4_000, reserva=1_000)
    _capital(k, 1_200_000, t.TESORO)
    _capital(k, 5_000, t.CUENTA_PEDRO)
    tab = per_mod.tablero(k, m.registro, SUS, reloj, lp, "2026-W30")
    assert tab["tesoro_mm"] == 1_200_000
    assert tab["cuenta_pedro_mm"] == 5_000
    assert tab["tipo_cambio_mm"] == 5_000
    assert tab["departamentos"]["dep:a"] == {"saldo_mm": 0,
                                             "congelado": False}


from calipso.economia import operacion as op_mod


def test_semana_iso():
    assert op_mod.semana_iso("2026-08-25") == "2026-W35"
    assert op_mod.semana_iso("2026-01-01") == "2026-W01"


def test_cerrar_semana_operativa_orquesta_todo(entorno, cola):
    k, m, b, _ = entorno
    m.registro.ajustar("a", presupuesto_semanal_mm=10_000)
    _capital(k, 1_200_000, t.TESORO)
    op_mod.abrir_semana(k, TS, "2026-W30", 4_000, 0)
    _capital(k, 20_000, "dep:a")
    cola.encolar(k, TS, "2026-W30", "c1", "dep:a", "sin atender",
                 tipo="contacto", obligatoria=True, mpt_estimado=500,
                 monedas_en_juego=1_000)
    res = op_mod.cerrar_semana_operativa(m, b, cola, TS, "2026-W30")
    assert res["expiradas"] == ["c1"]
    assert cola.estado("c1") == "expirada"
    assert k.saldo("dep:a") == 30_000  # presupuesto asignado
    assert res["informes_ciclo"] == []  # fraccion 25, no cierra ciclo
    # la emision de W30 expiro en el cierre de pt
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 0


def test_ciclo_completo_encola_carta_de_renovacion(entorno, cola):
    k, m, b, _ = entorno
    _capital(k, 1_200_000, t.TESORO)
    semanas = ["2026-W30", "2026-W31", "2026-W32", "2026-W33"]
    for sem in semanas:
        op_mod.abrir_semana(k, TS, sem, 4_000, 0)
        res = op_mod.cerrar_semana_operativa(m, b, cola, TS, sem)
    # W33 cierra el ciclo 0: sin recaudacion -> rojo 1, renueva automatico
    assert len(res["informes_ciclo"]) == 1
    assert res["informes_ciclo"][0]["renovada"] is True


def test_carta_atendida_del_ciclo_previo_desarma_el_breaker(entorno, cola):
    """FIX 1: la carta de renovacion del ciclo N-1 se crea con sufijo :N-1
    en SU cierre, y Pedro la atiende durante el ciclo N — el cierre de N
    debe reconocer esa atencion (no solo la del sufijo :N) para desarmar
    el breaker."""
    k, m, b, _ = entorno
    _capital(k, 1_200_000, t.TESORO)
    semanas = ["2026-W30", "2026-W31", "2026-W32", "2026-W33",
              "2026-W34", "2026-W35", "2026-W36", "2026-W37"]
    res = None
    for sem in semanas:
        op_mod.abrir_semana(k, TS, sem, 4_000, 0)
        res = op_mod.cerrar_semana_operativa(m, b, cola, TS, sem)
        if sem == "2026-W33":
            assert cola.estado("renovacion:claude_max:0") == "encolada"
            cola.atender_carta(TS, "2026-W34", "renovacion:claude_max:0",
                               firma={"tipo": "firma_pedro"})
    # W37 cierra el ciclo 1: dos ciclos rojos seguidos, pero la carta del
    # ciclo previo fue atendida -> el breaker no se dispara
    informe = res["informes_ciclo"][0]
    assert informe["rojos_consecutivos"] == 2
    assert informe["requiere_firma"] is False
    assert informe["renovada"] is True


def test_no_se_cierra_una_semana_vieja(entorno, cola):
    """FIX 3: pt.expirar_pools no filtra por semana, asi que re-cerrar una
    semana vieja despues de abrir la siguiente expiraria la emision fresca."""
    k, m, b, _ = entorno
    _capital(k, 1_200_000, t.TESORO)
    op_mod.abrir_semana(k, TS, "2026-W30", 4_000, 0)
    op_mod.cerrar_semana_operativa(m, b, cola, TS, "2026-W30")
    op_mod.abrir_semana(k, TS, "2026-W31", 4_000, 0)
    with pytest.raises(op_mod.ErrorOperacion):
        op_mod.cerrar_semana_operativa(m, b, cola, TS, "2026-W30")
    op_mod.cerrar_semana_operativa(m, b, cola, TS, "2026-W31")
    assert k.saldo(t.POOL_PT_FABRICA, t.Divisa.PT) == 0  # W31 se expiro bien


def test_desborde_de_reserva_personal_consume_lo_que_queda(entorno, cola, reloj):
    """FIX 4: un tramo personal mas largo que la reserva consume lo que
    queda (no todo-o-nada) y deja constancia del desborde."""
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30", cuota=4_000, reserva=500)
    reloj.clock_in("2026-08-25T09:00:00", "2026-W30", "personal",
                   ref="personal:finanzas")
    # 60 minutos -> 1000 mpt pedidos, solo 500 mpt en la reserva
    res = reloj.clock_out(m, cola, "2026-08-25T10:00:00", "2026-W30")
    assert k.saldo(t.POOL_PT_PERSONAL, t.Divisa.PT) == 0
    assert res["desborde_mpt"] == 500
    assert res["sin_cobro"] is False
    # un segundo tramo personal en la misma semana: la reserva ya esta en 0
    reloj.clock_in("2026-08-25T10:05:00", "2026-W30", "personal",
                   ref="personal:finanzas")
    res2 = reloj.clock_out(m, cola, "2026-08-25T10:20:00", "2026-W30")
    assert res2["sin_cobro"] is True


def test_presupuesto_de_direccion_es_idempotente(entorno, cola):
    """FIX 5a: un reintento del cierre con el mismo presupuesto_direccion_mm
    no duplica la transferencia tesoro->direccion."""
    k, m, b, _ = entorno
    _capital(k, 1_200_000, t.TESORO)
    op_mod.abrir_semana(k, TS, "2026-W30", 4_000, 0)
    op_mod.cerrar_semana_operativa(m, b, cola, TS, "2026-W30",
                                   presupuesto_direccion_mm=50_000)
    assert k.saldo(t.DIRECCION) == 50_000
    op_mod.cerrar_semana_operativa(m, b, cola, TS, "2026-W30",
                                   presupuesto_direccion_mm=50_000)
    assert k.saldo(t.DIRECCION) == 50_000


def test_opcional_desbordada_genera_deuda(entorno, cola):
    """FIX 6: el faltante de una opcional desbordada YA NO se perdona:
    direccion lo cubre con una acreencia, igual que una obligatoria."""
    k, m, b, _ = entorno
    _semana_op(k, "2026-W30")
    _capital(k, 2_500, "dep:a")  # caja justa para el estimado (500 mpt)
    _capital(k, 100_000, t.DIRECCION)
    cola.encolar(k, TS, "2026-W30", "op1", "dep:a", "brainstorm largo",
                 tipo="opinion", obligatoria=False, mpt_estimado=500,
                 monedas_en_juego=1_000)
    assert k.disponible("dep:a") == 0  # todo el capital reservado como escrow
    res = cola.servir(m, TS, "2026-W30", "op1", mpt_real=1_501)
    assert res["mpt_cobrado"] == 2_000
    assert res["cobro_mm"] == 10_000
    assert k.saldo(t.CUENTA_PEDRO) == 10_000  # Pedro cobra el total
    assert k.acreencias_pendientes("dep:a") == \
        [("adelanto:op1", t.DIRECCION, 7_500)]
