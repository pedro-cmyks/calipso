"""Tests de la frontera: candado, fixes parkeados, cola, reloj, personal, operacion."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import candado as cnd
from calipso.economia import capacidad as cap
from calipso.economia import cola as cola_mod
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
