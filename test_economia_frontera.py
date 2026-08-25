"""Tests de la frontera: candado, fixes parkeados, cola, reloj, personal, operacion."""
import pytest

from calipso.economia import bus as bus_mod
from calipso.economia import candado as cnd
from calipso.economia import capacidad as cap
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
