# test_siembra.py -- el orquestador de la siembra guiada, sin HTTP.
import pytest

from calipso.economia import capacidad as cap
from calipso.economia import tipos as t
from calipso.economia.pagador import Pagador
from calipso.plantel import interruptor as it
from calipso import routines

TS = "2026-08-26T10:00:00"
W = "2026-W35"


def _config():
    return {
        "departamentos": [
            {"nombre": "taller", "zona": "fabrica"},
            {"nombre": "development", "zona": "fabrica"},
            {"nombre": "research", "zona": "fabrica"},
            {"nombre": "finanzas", "zona": "personal"},
        ],
        "suscripciones": {"claude_max": {"costo_mensual_mm": 200_000,
                                         "capacidad_ciclo": 2_000,
                                         "reserva_personal": 200,
                                         "costo_api_mm_por_unidad": 500}},
        "capital_tesoro_mm": 100_000,
        "cuota_firmable_mpt": 4_000,
        "reserva_personal_mpt": 1_000,
        "rutina_interval_min": 60,
        "perillas_fabrica": {"presupuesto_semanal_mm": 25_000,
                             "techo_preseed_mm": 50_000,
                             "techo_preseed_ciclo_mm": 150_000,
                             "techo_api_ciclo_mm": 0},
    }


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    # routines.py congela CALIPSO_HOME en una constante de modulo al
    # importarse (routines.py:30-31) y su helper de ruta la usa directo
    # (routines.py:94-95), asi que el setenv de arriba no alcanza: hay que
    # pisar tambien el atributo del modulo ya importado.
    monkeypatch.setattr(routines, "CALIPSO_HOME", tmp_path)
    return tmp_path


def test_preview_no_escribe_nada(home):
    from calipso import siembra
    r = siembra.sembrar_guiado(str(home), _config(), TS, W, ejecutar=False)
    assert "plan" in r and "estado" in r
    assert r["estado"]["sembrada"] is False
    assert not (home / "economia").exists()   # NADA se escribio


def test_ejecutar_corre_los_siete_pasos(home):
    from calipso import siembra
    r = siembra.sembrar_guiado(str(home), _config(), TS, W, ejecutar=True)
    assert r["ok"] is True
    p = Pagador(home / "economia")
    # padron
    assert p.ruta_registro.exists() and p.ruta_sus.exists() and p.ruta_libro.exists()
    reg = __import__("calipso.economia.departamentos", fromlist=["Registro"]).Registro(p.ruta_registro)
    assert {d.nombre for d in reg.todos()} == {"taller", "development", "research", "finanzas"}
    # semana abierta
    asientos = p.leer_kernel().libro.asientos()
    assert W in cap.semanas_operativas(asientos)
    # tesoro con capital
    assert p.leer_kernel().saldo(t.TESORO) == 100_000
    # perillas puestas en los de fabrica (pre-seed > 0, api_ciclo = 0)
    taller = reg.obtener("taller")
    assert taller.techo_preseed_mm == 50_000 and taller.techo_preseed_ciclo_mm == 150_000
    assert taller.techo_api_ciclo_mm == 0
    # una rutina departamento por depto de fabrica
    deptos_rutina = {r_.get("cuenta") for r_ in routines.load() if r_.get("kind") == "departamento"}
    assert deptos_rutina == {"dep:taller", "dep:development", "dep:research"}
    # modo vivo
    assert it.leer(str(home)).modo == "vivo"


def test_re_entrante_no_duplica_ni_rompe(home):
    from calipso import siembra
    siembra.sembrar_guiado(str(home), _config(), TS, W, ejecutar=True)
    # segunda corrida: saltea todo lo hecho, no duplica, no levanta
    r2 = siembra.sembrar_guiado(str(home), _config(), TS, W, ejecutar=True)
    assert r2["ok"] is True
    p = Pagador(home / "economia")
    assert p.leer_kernel().saldo(t.TESORO) == 100_000   # NO re-acuño
    deptos = [r_ for r_ in routines.load() if r_.get("kind") == "departamento"]
    assert len(deptos) == 3                              # NO duplico rutinas


def test_finanzas_no_lleva_rutina_ni_perillas_de_fabrica(home):
    from calipso import siembra
    siembra.sembrar_guiado(str(home), _config(), TS, W, ejecutar=True)
    cuentas = {r_.get("cuenta") for r_ in routines.load() if r_.get("kind") == "departamento"}
    assert "personal:finanzas" not in cuentas and "dep:finanzas" not in cuentas


def test_config_repetida_no_deja_padron_a_medias(home):
    # una config con un nombre repetido (el body guiado no deduplica) tiene
    # que levantar ANTES de escribir el padron: si escribiera un
    # departamentos.json a medias, la re-entrancia quedaria trabada para
    # siempre. Validar-todo-antes-de-escribir (como api_eco_sembrar) lo cierra.
    from calipso import siembra
    from calipso.economia import departamentos as deps
    cfg = _config()
    cfg["departamentos"].append({"nombre": "taller", "zona": "fabrica"})
    with pytest.raises(deps.ErrorDepartamento):
        siembra.sembrar_guiado(str(home), cfg, TS, W, ejecutar=True)
    # NO quedo un departamentos.json a medias
    assert not (home / "economia" / "departamentos.json").exists()
    # y la re-entrancia sigue viva: con una config valida, siembra bien
    r = siembra.sembrar_guiado(str(home), _config(), TS, W, ejecutar=True)
    assert r["ok"] is True and r["estado"]["sembrada"] is True
