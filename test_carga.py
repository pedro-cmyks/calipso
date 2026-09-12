"""El sensor de la carga (spec 2026-09-11, secciones 2 y 6): los tres niveles
y sus bordes con /proc y /api/ps FALSOS (nada de esto toca la maquina ni
Ollama), las perillas por nivel, el contador de uso con hilos, la histeresis,
los dos helpers traidos de resource_dispatcher, los avisos, las cuentas del
dia y `--esperar` (no cargada por default, `--holgada` exige holgada) que vence con 3.

`medida(nivel, ...)` es el molde de Carga que los otros archivos de tests
importan (test_carga_decide.py, test_carga_chat.py, test_carga_vigia.py,
test_carga_api.py): una Carga coherente con su nivel, sin medir nada.
"""
from __future__ import annotations

import contextlib
import dataclasses
import io
import json
import threading

import pytest

from calipso import carga

MEMINFO_HOLGADA = (
    "MemTotal:       11917720 kB\nMemFree:          465764 kB\n"
    "MemAvailable:    7554048 kB\nSwapTotal:       5958652 kB\nSwapFree:        2256184 kB\n")
MEMINFO_CARGADA = MEMINFO_HOLGADA.replace("MemAvailable:    7554048 kB", "MemAvailable:     512000 kB")
MEMINFO_JUSTA = MEMINFO_HOLGADA.replace("MemAvailable:    7554048 kB", "MemAvailable:    6144000 kB")
PSI_0 = "some avg10=0.00 avg60=0.00 avg300=0.00 total=1\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=1\n"
LOAD_BAJA = "1.85 1.92 3.31 1/1257 775214\n"


def lector(meminfo=MEMINFO_HOLGADA, psi_mem=PSI_0, psi_cpu=PSI_0, loadavg=LOAD_BAJA):
    """Un `leer(ruta)` falso: None en una ruta = OSError (el archivo no esta)."""
    tabla = {"/proc/meminfo": meminfo, "/proc/pressure/memory": psi_mem,
             "/proc/pressure/cpu": psi_cpu, "/proc/loadavg": loadavg}

    def _leer(ruta):
        if tabla.get(ruta) is None:
            raise OSError(f"no existe {ruta}")
        return tabla[ruta]
    return _leer


def medida(nivel="holgada", mem=None, motivo=None, modelos=(), necesidad=5746,
           modelo_cargado_mb=0, **campos):
    """Una Carga coherente con `nivel` sin medir nada: el molde para los
    tests de _decide, del harness, del vigia y del endpoint. La memoria
    efectiva (ola de fix, punto 1) es `mem + modelo_cargado_mb` salvo que
    venga en `campos`."""
    por_nivel = {"holgada": (7377, ""), "justa": (6200, "mem 6200 < 5746+1024"),
                 "cargada": (480, "mem 480 < 5746")}
    mem_def, motivo_def = por_nivel[nivel]
    disponible = mem if mem is not None else mem_def
    base = dict(nivel=nivel, motivo=motivo if motivo is not None else motivo_def,
                mem_disponible_mb=disponible,
                mem_efectiva_mb=campos.pop("mem_efectiva_mb", disponible + modelo_cargado_mb),
                modelo_cargado_mb=modelo_cargado_mb,
                mem_total_mb=11638, swap_usado_mb=3615, swap_libre_mb=2203,
                psi_mem_some10=0.0, psi_mem_full10=0.0, psi_cpu_some10=0.0,
                load1=1.85, ncpu=16, modelos_cargados=list(modelos), necesidad_mb=necesidad,
                modelo="qwen2.5:7b",
                medido={"meminfo": True, "psi_mem": True, "psi_cpu": True, "loadavg": True, "ollama": True},
                medido_en="2026-09-11T18:41:37")
    base.update(campos)
    return carga.Carga(**base)


@pytest.fixture(autouse=True)
def _sensor_limpio():
    carga.olvidar()
    yield
    carga.olvidar()


# --- la necesidad del modelo ---------------------------------------------------

def test_necesidad_es_el_blob_del_gguf_mas_el_margen(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path))
    manifiesto = tmp_path / "manifests" / "registry.ollama.ai" / "library" / "qwen2.5"
    manifiesto.mkdir(parents=True)
    (tmp_path / "blobs").mkdir()
    blob = tmp_path / "blobs" / "sha256-abc"
    with open(blob, "wb") as f:
        f.truncate(100 * 2**20)          # 100 MiB sin escribirlos
    (manifiesto / "7b").write_text(json.dumps({"layers": [
        {"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:abc"}]}),
        encoding="utf-8")
    assert carga.necesidad_mb("qwen2.5:7b") == 100 + carga.UMBRALES["MARGEN_MODELO_MB"]


def test_sin_blob_la_necesidad_es_el_default(tmp_path, monkeypatch):
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-hay"))
    assert carga.necesidad_mb("qwen2.5:7b") == carga.UMBRALES["NECESIDAD_DEFAULT_MB"]
    assert carga.necesidad_mb(None) == carga.UMBRALES["NECESIDAD_DEFAULT_MB"]


def test_un_manifiesto_que_no_es_dict_no_revienta_la_necesidad_ni_medir(tmp_path, monkeypatch):
    """Fail-open de verdad (ola de fix, punto 4): un manifiesto de Ollama que
    es JSON valido pero no dict (`[1]`) levantaba AttributeError en
    `tokenizador.blob_del_modelo`; `necesidad_mb` solo atrapaba OSError y
    `_decide` reventaba en cada turno. Ahora: NECESIDAD_DEFAULT_MB y `medir`
    no levanta."""
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path))
    manifiesto = tmp_path / "manifests" / "registry.ollama.ai" / "library" / "qwen2.5"
    manifiesto.mkdir(parents=True)
    (manifiesto / "7b").write_text("[1]", encoding="utf-8")
    assert carga.necesidad_mb("qwen2.5:7b") == carga.UMBRALES["NECESIDAD_DEFAULT_MB"]
    c = carga.medir("qwen2.5:7b", leer=lector(), ps=lambda: [], ncpu=16)
    assert c.necesidad_mb == carga.UMBRALES["NECESIDAD_DEFAULT_MB"] and c.nivel == "holgada"


# --- nivel(): pura sobre numeros ------------------------------------------------

def test_los_tres_niveles_por_memoria():
    assert carga.nivel(480, 5746, 0.0, 0.0, 0.0, 1.0, 16) == ("cargada", "mem 480 < 5746")
    assert carga.nivel(6200, 5746, 0.0, 0.0, 0.0, 1.0, 16) == ("justa", "mem 6200 < 5746+1024")
    assert carga.nivel(7377, 5746, 0.0, 0.0, 0.0, 1.0, 16) == ("holgada", "")


def test_el_modelo_cargado_cuenta_como_memoria_efectiva():
    """Ruling de la ola de fix (punto 1, revierte en parte el 9.1 del spec):
    el nivel se mide contra la memoria EFECTIVA para el modelo, MemAvailable
    mas el `size` de los modelos de Calipso que /api/ps lista en esa
    medicion (lo que devuelve un evict). Con el 7b cargado y nada mas la
    Ally es holgada; el OOM del 17:07 (500 + 5203 = 5703 < 5746) sigue
    siendo cargada. El motivo dice `mem efectiva` cuando hay modelo cargado."""
    # (a) el 7b cargado en reposo: 2709 libres + 5203 del 7b = 7912 -> holgada
    assert carga.nivel(2709, 5746, 0.0, 0.0, 0.0, 1.0, 16, modelo_cargado_mb=5203) == ("holgada", "")
    # (b) el OOM: 500 + 5203 = 5703 < 5746 -> cargada
    assert carga.nivel(500, 5746, 0.0, 0.0, 0.0, 1.0, 16, modelo_cargado_mb=5203) == (
        "cargada", "mem efectiva 5703 < 5746")
    # justa por memoria efectiva: 1478 + 5203 = 6681 entre 5746 y 6770
    assert carga.nivel(1478, 5746, 0.0, 0.0, 0.0, 1.0, 16, modelo_cargado_mb=5203) == (
        "justa", "mem efectiva 6681 < 5746+1024")
    # sin modelo cargado la forma es la de siempre
    assert carga.nivel(5506, 5746, 0.0, 0.0, 0.0, 1.0, 16, modelo_cargado_mb=0) == ("cargada", "mem 5506 < 5746")


def test_psi_alto_con_memoria_libre_es_cargada():
    assert carga.nivel(7377, 5746, 22.0, 0.0, 0.0, 1.0, 16)[0] == "cargada"
    assert carga.nivel(7377, 5746, 0.0, 6.0, 0.0, 1.0, 16)[0] == "cargada"
    # de laboratorio: con el 7b cargado y el swap a 68 kB el PSI dio 0,00-0,16
    # (terreno-maquina, T2); lo que ve el OOM que viene es MemAvailable
    assert carga.nivel(7377, 5746, 7.0, 0.0, 0.0, 1.0, 16) == ("justa", "psi_mem_some10 7.0 >= 5")


def test_cpu_ocupada_con_ram_de_sobra_es_justa_nunca_cargada():
    assert carga.nivel(7377, 5746, 0.0, 0.0, 30.0, 1.0, 16) == ("justa", "psi_cpu_some10 30.0 >= 25")
    assert carga.nivel(7377, 5746, 0.0, 0.0, 0.0, 9.9, 16) == ("justa", "load1 9.9 >= 8.0")
    # jugando con el juego quieto (17:55): load1 4,65 de 16 -> holgada
    assert carga.nivel(6897, 5746, 0.0, 0.0, 0.0, 4.65, 16) == ("holgada", "")


def test_una_senal_no_medida_no_decide():
    # sin PSI ni load: solo la memoria decide
    assert carga.nivel(7377, 5746, None, None, None, None, 16) == ("holgada", "")
    assert carga.nivel(480, 5746, None, None, None, None, 16)[0] == "cargada"
    # sin memoria: el PSI decide
    assert carga.nivel(None, 5746, 22.0, 0.0, 0.0, 1.0, 16)[0] == "cargada"
    # nada medido: holgada
    assert carga.nivel(None, 5746, None, None, None, None, 16) == ("holgada", "")


def test_la_calibracion_anotada_cae_donde_dice():
    """La tabla del modulo es ejecutable: cada escena medida cae en el nivel
    que dice. Desde el smoke del 2026-09-11 (corrida 3) ninguna fila queda sin
    numeros: la 'cargada de verdad' la lleno el reservador del paso R."""
    assert carga.CALIBRACION
    for fila in carga.CALIBRACION:
        assert fila["cuando"] and fila["mem_disponible_mb"] is not None, fila["escena"]
        assert "modelo_cargado_mb" in fila, fila["escena"]
        n, _ = carga.nivel(fila["mem_disponible_mb"], fila["necesidad_mb"],
                           fila["psi_mem_some10"], fila["psi_mem_full10"],
                           fila["psi_cpu_some10"], fila["load1"], fila["ncpu"],
                           modelo_cargado_mb=fila["modelo_cargado_mb"])
        assert n == fila["nivel"], fila["escena"]


def test_la_calibracion_con_el_7b_cargado_cae_donde_dice_el_ruling():
    """Las filas con el 7b adentro, recalculadas con la memoria efectiva
    (ola de fix, punto 1): M (2709 + 5203) y V (2469 + 5203) son holgada; el
    OOM (500 + 5203 = 5703) sigue cargada; 18:22-18:25 (1478/1578 + 5203)
    quedan justa por load1 >= 8 (y 18:22 tambien por la memoria: 6681 < 6770)."""
    por_cuando = {f["cuando"]: f for f in carga.CALIBRACION}
    assert por_cuando["2026-09-11T22:47:15"]["modelo_cargado_mb"] == 5203
    assert por_cuando["2026-09-11T22:47:15"]["nivel"] == "holgada"
    assert por_cuando["2026-09-11T22:47:24"]["nivel"] == "holgada"
    assert por_cuando["2026-09-11 17:07:59"]["modelo_cargado_mb"] == 5203
    assert por_cuando["2026-09-11 17:07:59"]["nivel"] == "cargada"
    assert por_cuando["2026-09-11 18:22:32"]["nivel"] == "justa"
    assert por_cuando["2026-09-11 18:25:38"]["nivel"] == "justa"
    # las filas sin modelo no cambian
    assert por_cuando["2026-09-11T22:47:52"]["modelo_cargado_mb"] == 0
    assert "punto 1" in carga.__doc__ or "memoria EFECTIVA" in carga.__doc__


def test_la_fila_cargada_de_verdad_es_la_del_reservador_del_smoke():
    """La fila que el plan dejo en None (Task 6) lleva los numeros del paso R de
    la corrida 3 del smoke: cargada por MemAvailable con PSI casi cero y sin
    modelo cargado (1536 MB de bytes aleatorios apartados), y la escena dice de
    donde salieron (el script y el informe)."""
    filas = [f for f in carga.CALIBRACION if f["escena"].startswith("cargada de verdad")]
    assert len(filas) == 1
    fila = filas[0]
    assert fila["cuando"] == "2026-09-11T22:47:52"
    assert "experimentos/carga_smoke.py" in fila["escena"]
    assert "docs/superpowers/2026-09-11-smoke-carga.md" in fila["escena"]
    assert (fila["mem_disponible_mb"], fila["necesidad_mb"], fila["nivel"]) == (5555, 5746, "cargada")
    assert carga.nivel(fila["mem_disponible_mb"], fila["necesidad_mb"], fila["psi_mem_some10"],
                       fila["psi_mem_full10"], fila["psi_cpu_some10"], fila["load1"],
                       fila["ncpu"], modelo_cargado_mb=fila["modelo_cargado_mb"]) == ("cargada", "mem 5555 < 5746")
    # cargada por memoria y nada mas: el PSI no llego ni al umbral de holgada
    assert fila["psi_mem_some10"] < carga.UMBRALES["PSI_MEM_SOME_HOLGADA"]


# --- medir(): con /proc y /api/ps falsos --------------------------------------

def test_medir_con_proc_y_ps_falsos_da_los_tres_niveles():
    c = carga.medir("qwen2.5:7b", leer=lector(), ps=lambda: [], ncpu=16, necesidad=5746)
    assert (c.nivel, c.motivo, c.mem_disponible_mb, c.mem_total_mb) == ("holgada", "", 7377, 11638)
    assert (c.swap_usado_mb, c.swap_libre_mb) == (3615, 2203)
    assert c.medido == {"meminfo": True, "psi_mem": True, "psi_cpu": True, "loadavg": True, "ollama": True}
    assert c.modelos_cargados == [] and c.necesidad_mb == 5746 and c.modelo == "qwen2.5:7b"
    assert c.medido_en and "T" in c.medido_en
    c2 = carga.medir("qwen2.5:7b", leer=lector(meminfo=MEMINFO_CARGADA),
                     ps=lambda: [{"name": "qwen2.5:7b", "size_mb": 5203, "expires_at": "x"}],
                     ncpu=16, necesidad=5746)
    assert c2.nivel == "cargada" and c2.modelos_cargados == ["qwen2.5:7b"]
    assert c2.motivo == "mem efectiva 5703 < 5746"       # 500 + 5203 del 7b listado
    assert (c2.mem_efectiva_mb, c2.modelo_cargado_mb) == (5703, 5203)
    assert (c.mem_efectiva_mb, c.modelo_cargado_mb) == (7377, 0)
    c3 = carga.medir("qwen2.5:7b", leer=lector(meminfo=MEMINFO_JUSTA), ps=lambda: [],
                     ncpu=16, necesidad=5746)
    assert c3.nivel == "justa"


MEMINFO_7B_EN_REPOSO = MEMINFO_HOLGADA.replace("MemAvailable:    7554048 kB", "MemAvailable:    2774016 kB")   # 2709 MiB
MEMINFO_OOM = MEMINFO_HOLGADA.replace("MemAvailable:    7554048 kB", "MemAvailable:     512000 kB")           # 500 MiB
MEMINFO_5506 = MEMINFO_HOLGADA.replace("MemAvailable:    7554048 kB", "MemAvailable:    5638144 kB")          # 5506 MiB
PS_7B = [{"name": "qwen2.5:7b", "size_mb": 5203, "expires_at": "x"}]


def test_medir_con_el_7b_cargado_en_reposo_es_holgada_y_sin_ps_es_cargada():
    """Ola de fix, punto 1: (a) el 7b cargado y nada mas (2709 libres, ps lo
    lista con 5203) -> holgada; (b) el OOM (500 libres, 7b listado) ->
    cargada; (c) ps caido con 2709 libres -> cargada (fail-open: sin ps la
    memoria efectiva es la disponible); (d) 5506 libres sin modelo -> cargada."""
    a = carga.medir("qwen2.5:7b", leer=lector(meminfo=MEMINFO_7B_EN_REPOSO), ps=lambda: PS_7B,
                    ncpu=16, necesidad=5746)
    assert (a.nivel, a.motivo) == ("holgada", "")
    assert (a.mem_disponible_mb, a.modelo_cargado_mb, a.mem_efectiva_mb) == (2709, 5203, 7912)
    b = carga.medir("qwen2.5:7b", leer=lector(meminfo=MEMINFO_OOM), ps=lambda: PS_7B,
                    ncpu=16, necesidad=5746)
    assert (b.nivel, b.motivo, b.mem_efectiva_mb) == ("cargada", "mem efectiva 5703 < 5746", 5703)
    c = carga.medir("qwen2.5:7b", leer=lector(meminfo=MEMINFO_7B_EN_REPOSO), ps=lambda: None,
                    ncpu=16, necesidad=5746)
    assert (c.nivel, c.motivo) == ("cargada", "mem 2709 < 5746")
    assert (c.modelo_cargado_mb, c.mem_efectiva_mb, c.medido["ollama"]) == (0, 2709, False)
    d = carga.medir("qwen2.5:7b", leer=lector(meminfo=MEMINFO_5506), ps=lambda: [],
                    ncpu=16, necesidad=5746)
    assert (d.nivel, d.motivo, d.mem_efectiva_mb) == ("cargada", "mem 5506 < 5746", 5506)


def test_solo_los_modelos_propios_suman_a_la_memoria_efectiva():
    """Un modelo ajeno listado no cuenta (el vigia no lo descargaria); por
    defecto cuenta solo el modelo contra el que se mide; con
    `modelos_propios=` cuentan todos los de Calipso (el 3b del clasificador)."""
    ajeno_y_3b = PS_7B + [{"name": "llama3:8b", "size_mb": 4000, "expires_at": "x"},
                          {"name": "qwen2.5:3b", "size_mb": 1900, "expires_at": "x"}]
    c = carga.medir("qwen2.5:7b", leer=lector(meminfo=MEMINFO_OOM), ps=lambda: ajeno_y_3b,
                    ncpu=16, necesidad=5746)
    assert c.modelo_cargado_mb == 5203 and c.nivel == "cargada"
    assert c.modelos_cargados == ["qwen2.5:7b", "llama3:8b", "qwen2.5:3b"]
    c2 = carga.medir("qwen2.5:7b", leer=lector(meminfo=MEMINFO_OOM), ps=lambda: ajeno_y_3b,
                     ncpu=16, necesidad=5746, modelos_propios={"qwen2.5:7b", "qwen2.5:3b"})
    assert c2.modelo_cargado_mb == 5203 + 1900 and c2.mem_efectiva_mb == 500 + 5203 + 1900
    assert c2.nivel == "holgada"                     # 7603 >= 5746 + 1024
    # los avisos siguen diciendo los MB libres de verdad (lo que Pedro entiende)
    assert carga.marca(carga.fila(c), "subscription")["mem_disponible_mb"] == 500


def test_el_swap_lleno_con_memoria_libre_no_decide():
    lleno = MEMINFO_HOLGADA.replace("SwapFree:        2256184 kB", "SwapFree:             68 kB")
    c = carga.medir("qwen2.5:7b", leer=lector(meminfo=lleno), ps=lambda: [], ncpu=16, necesidad=5746)
    assert c.nivel == "holgada" and c.swap_libre_mb == 0 and c.swap_usado_mb == 5818


def test_sin_pressure_el_psi_no_decide_y_medido_lo_dice():
    c = carga.medir("qwen2.5:7b", leer=lector(psi_mem=None, psi_cpu=None), ps=lambda: [],
                    ncpu=16, necesidad=5746)
    assert c.nivel == "holgada" and c.medido["psi_mem"] is False and c.medido["psi_cpu"] is False
    assert (c.psi_mem_some10, c.psi_mem_full10, c.psi_cpu_some10) == (0.0, 0.0, 0.0)
    # la memoria sigue decidiendo sola
    c2 = carga.medir("qwen2.5:7b", leer=lector(meminfo=MEMINFO_CARGADA, psi_mem=None, psi_cpu=None),
                     ps=lambda: [], ncpu=16, necesidad=5746)
    assert c2.nivel == "cargada"


def test_el_psi_se_mide_por_archivo_y_solo_el_que_fallo_no_decide():
    """Ola de fix, punto 6c: antes el PSI se descartaba en bloque si fallaba
    uno de los dos archivos. Con /proc/pressure/cpu ausente, la memoria
    sigue decidiendo por PSI (22 -> cargada) y `medido` lo dice por archivo;
    y al reves, sin /proc/pressure/memory el PSI de CPU sigue contando."""
    psi_mem_alto = "some avg10=22.00 avg60=0.00 avg300=0.00 total=1\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=1\n"
    c = carga.medir("qwen2.5:7b", leer=lector(psi_mem=psi_mem_alto, psi_cpu=None), ps=lambda: [],
                    ncpu=16, necesidad=5746)
    assert c.nivel == "cargada" and c.motivo == "psi_mem_some10 22.0 >= 20"
    assert c.medido["psi_mem"] is True and c.medido["psi_cpu"] is False
    assert (c.psi_mem_some10, c.psi_cpu_some10) == (22.0, 0.0)
    psi_cpu_alto = "some avg10=30.00 avg60=0.00 avg300=0.00 total=1\n"
    c2 = carga.medir("qwen2.5:7b", leer=lector(psi_mem=None, psi_cpu=psi_cpu_alto), ps=lambda: [],
                     ncpu=16, necesidad=5746)
    assert c2.nivel == "justa" and c2.motivo == "psi_cpu_some10 30.0 >= 25"
    assert c2.medido["psi_mem"] is False and c2.medido["psi_cpu"] is True


def test_medir_con_ps_timeout_propio_lo_pasa_al_lector_de_api_ps(monkeypatch):
    """Ola de fix, punto 6a: el tick mide con `ps_timeout=PS_TIMEOUT_TICK_S`
    (2 s): bajo carga /api/ps con 0,5 s puede no responder y el vigia no
    descargaba ni dejaba rastro."""
    vistos = []
    monkeypatch.setattr(carga, "ollama_loaded_models",
                        lambda base=None, timeout=None: vistos.append(timeout) or [])
    monkeypatch.setattr(carga, "necesidad_mb", lambda modelo: 5746)
    monkeypatch.setattr(carga, "_leer_proc", lector())
    assert carga.UMBRALES["PS_TIMEOUT_TICK_S"] == 2.0
    carga.medir("qwen2.5:7b", ps_timeout=carga.UMBRALES["PS_TIMEOUT_TICK_S"])
    assert vistos == [2.0]
    carga.olvidar()
    carga.medir("qwen2.5:7b")
    assert vistos == [2.0, None]           # sin timeout propio: el default (PS_TIMEOUT_S)


def test_ps_caido_deja_sin_modelos_y_el_resto_decide():
    c = carga.medir("qwen2.5:7b", leer=lector(meminfo=MEMINFO_CARGADA), ps=lambda: None,
                    ncpu=16, necesidad=5746)
    assert c.nivel == "cargada" and c.modelos_cargados == [] and c.medido["ollama"] is False


def test_nada_medible_es_holgada_con_medido_todo_falso():
    c = carga.medir("qwen2.5:7b", leer=lector(None, None, None, None), ps=lambda: None,
                    ncpu=16, necesidad=5746)
    assert c.nivel == "holgada" and c.motivo == ""
    assert c.medido == {"meminfo": False, "psi_mem": False, "psi_cpu": False, "loadavg": False, "ollama": False}
    assert c.mem_disponible_mb == 0


def test_la_cache_dura_dos_segundos_y_solo_sin_lectores_inyectados(monkeypatch):
    reloj = [100.0]
    monkeypatch.setattr(carga.time, "monotonic", lambda: reloj[0])
    llamadas = []

    def leer(ruta):
        llamadas.append(ruta)
        return lector()(ruta)
    monkeypatch.setattr(carga, "_leer_proc", leer)
    monkeypatch.setattr(carga, "ollama_loaded_models", lambda base=None, timeout=None: [])
    monkeypatch.setattr(carga, "necesidad_mb", lambda modelo: 5746)
    a = carga.medir("qwen2.5:7b")
    n = len(llamadas)
    b = carga.medir("qwen2.5:7b")
    assert b is a and len(llamadas) == n           # fresca: no se releyo nada
    reloj[0] += carga.UMBRALES["CACHE_S"] + 0.1
    c = carga.medir("qwen2.5:7b")
    assert c is not a and len(llamadas) > n
    assert carga.nivel_reciente() == "holgada"


def test_calipso_carga_off_apaga_el_sensor_por_llamada(monkeypatch):
    """El rollback en caliente (ola de fix, punto 3): con CALIPSO_CARGA=off
    (leido POR LLAMADA, patron de canarios_activos) `medir` devuelve una
    Carga holgada con `medido` todo en False y `apagado: True` (la rama del
    invariante 5: Calipso se comporta como hoy, sin vigia ni pospuestas ni
    marca ni histeresis, perillas de holgada). Sin leer /proc ni Ollama."""
    monkeypatch.setenv("CALIPSO_CARGA", "OFF")
    leidos = []

    def leer(ruta):
        leidos.append(ruta)
        return lector()(ruta)
    c = carga.medir("qwen2.5:7b", leer=leer, ps=lambda: leidos.append("ps") or PS_7B, ncpu=16,
                    necesidad=5746)
    assert c.nivel == "holgada" and c.motivo == "" and c.apagado is True
    assert c.medido == {"meminfo": False, "psi_mem": False, "psi_cpu": False, "loadavg": False, "ollama": False}
    assert leidos == [] and c.modelos_cargados == [] and c.mem_disponible_mb == 0
    assert carga.nivel_reciente() == "holgada" and carga.fila(c)["apagado"] is True
    # tambien sin inyeccion: no lee /proc ni hace GET
    monkeypatch.setattr(carga, "_leer_proc", leer)
    monkeypatch.setattr(carga, "ollama_loaded_models", lambda base=None, timeout=None: leidos.append("ps") or [])
    assert carga.medir("qwen2.5:7b").apagado is True and leidos == []
    # ausente, vacio o cualquier otro valor: prendido
    for valor in ("", "on", "0", "false"):
        monkeypatch.setenv("CALIPSO_CARGA", valor)
        assert carga.carga_activa() is True
        assert carga.medir("qwen2.5:7b", leer=lector(), ps=lambda: [], ncpu=16, necesidad=5746).apagado is False
    monkeypatch.delenv("CALIPSO_CARGA")
    assert carga.carga_activa() is True
    assert carga.medir("qwen2.5:7b", leer=lector(meminfo=MEMINFO_CARGADA), ps=lambda: [], ncpu=16,
                       necesidad=5746).nivel == "cargada"


def test_nivel_reciente_es_holgada_sin_medicion_y_sigue_a_la_ultima():
    assert carga.nivel_reciente() == "holgada"
    carga.medir("qwen2.5:7b", leer=lector(meminfo=MEMINFO_CARGADA), ps=lambda: [], ncpu=16, necesidad=5746)
    assert carga.nivel_reciente() == "cargada"
    carga.olvidar()
    assert carga.nivel_reciente() == "holgada"


# --- las perillas ---------------------------------------------------------------

def test_keep_alive_y_num_thread_por_nivel():
    """Bajo cargada el keep_alive es "30s", no 0 (ola de fix, punto 2): con 0
    Ollama descargaba el 7b al terminar CADA pasada y /nube (juez + turno) y
    las reentradas del abismo pagaban una carga desde disco por pasada (N
    48-56 s contra A 36-42 s). Con 30 s las pasadas de un turno comparten el
    runner y el vigia descarga en el tick siguiente cuando en_uso llega a 0."""
    assert carga.keep_alive("holgada") == "5m"
    assert carga.keep_alive("justa") == "2m"
    assert carga.keep_alive("cargada") == "30s"
    assert "30s" in carga.keep_alive.__doc__ and "48-56" in carga.keep_alive.__doc__
    assert carga.keep_alive(None) == "5m"
    assert carga.num_thread("holgada", ncpu=16) is None
    assert carga.num_thread("justa", ncpu=16) == 8
    assert carga.num_thread("cargada", ncpu=16) == 8
    assert carga.num_thread("cargada", ncpu=1) == 1


def test_payload_local_agrega_las_perillas_sin_pisar_options_ni_mutar():
    base = {"model": "m", "prompt": "p", "stream": False, "options": {"temperature": 0, "num_ctx": 8192}}
    h = carga.payload_local(base, "holgada")
    assert h["keep_alive"] == "5m" and h["options"] == {"temperature": 0, "num_ctx": 8192}
    assert "num_thread" not in h["options"]
    c = carga.payload_local(base, "cargada")
    assert c["keep_alive"] == "30s"
    assert c["options"] == {"temperature": 0, "num_ctx": 8192, "num_thread": carga.num_thread("cargada")}
    assert "keep_alive" not in base and "num_thread" not in base["options"]   # no muta
    sin_options = carga.payload_local({"model": "m", "prompt": "p"}, "justa")
    assert sin_options["keep_alive"] == "2m" and sin_options["options"] == {"num_thread": carga.num_thread("justa")}
    assert "options" not in carga.payload_local({"model": "m"}, "holgada")
    # sin nivel toma el reciente (holgada si no se midio)
    assert carga.payload_local({"model": "m"})["keep_alive"] == "5m"


# --- el contador de uso ---------------------------------------------------------

def test_usando_cuenta_con_hilos_y_vuelve_a_cero():
    adentro = threading.Event()
    seguir = threading.Event()
    vistos = []

    def uno():
        with carga.usando():
            vistos.append(carga.en_uso)
            adentro.set()
            seguir.wait(5)
    hilos = [threading.Thread(target=uno) for _ in range(3)]
    for h in hilos:
        h.start()
    adentro.wait(5)
    seguir.set()
    for h in hilos:
        h.join(5)
    assert carga.en_uso == 0 and max(vistos) >= 1


def test_uso_es_idempotente():
    u = carga.Uso()
    u.tomar(); u.tomar()
    assert carga.en_uso == 1
    u.soltar(); u.soltar()
    assert carga.en_uso == 0
    u2 = carga.Uso()
    u2.soltar()                       # sin tomar: no baja de cero
    assert carga.en_uso == 0


# --- la histeresis --------------------------------------------------------------

def test_local_suspendido_se_apaga_solo_en_holgada():
    assert carga.local_suspendido is False
    carga.suspender()
    assert carga.local_suspendido is True
    assert carga.liberar_si_holgada(medida("justa")) is False and carga.local_suspendido is True
    assert carga.liberar_si_holgada(medida("cargada")) is False and carga.local_suspendido is True
    assert carga.liberar_si_holgada(medida("holgada")) is True and carga.local_suspendido is False
    carga.suspender()
    carga.liberar()
    assert carga.local_suspendido is False


# --- Ollama: lo traido de resource_dispatcher -----------------------------------

class _Resp:
    def __init__(self, cuerpo):
        self.cuerpo = cuerpo

    def read(self):
        return self.cuerpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_ollama_loaded_models_lee_api_ps_y_none_si_no_responde(monkeypatch):
    pedidos = []

    def urlopen(req, timeout=None):
        pedidos.append((req.full_url, timeout))
        return _Resp(json.dumps({"models": [
            {"name": "qwen2.5:7b", "size": 5455793356, "size_vram": 0, "expires_at": "2026-09-11T18:30:31"}]}).encode())
    monkeypatch.setattr(carga.urllib.request, "urlopen", urlopen)
    assert carga.ollama_loaded_models() == [
        {"name": "qwen2.5:7b", "size_mb": 5203, "expires_at": "2026-09-11T18:30:31"}]
    assert pedidos == [("http://localhost:11434/api/ps", carga.UMBRALES["PS_TIMEOUT_S"])]

    def caido(req, timeout=None):
        raise OSError("connection refused")
    monkeypatch.setattr(carga.urllib.request, "urlopen", caido)
    assert carga.ollama_loaded_models() is None


def test_ollama_evict_manda_keep_alive_0_al_modelo_y_dice_si_pudo(monkeypatch):
    vistos = []

    def urlopen(req, timeout=None):
        vistos.append((req.full_url, json.loads(req.data.decode()), timeout))
        return _Resp(b"{}")
    monkeypatch.setattr(carga.urllib.request, "urlopen", urlopen)
    assert carga.ollama_evict("qwen2.5:7b") is True
    assert vistos == [("http://localhost:11434/api/generate",
                       {"model": "qwen2.5:7b", "prompt": "", "stream": False, "keep_alive": 0},
                       carga.UMBRALES["EVICT_TIMEOUT_S"])]
    monkeypatch.setattr(carga.urllib.request, "urlopen", lambda req, timeout=None: (_ for _ in ()).throw(OSError("x")))
    assert carga.ollama_evict("qwen2.5:7b") is False


# --- los avisos y las cuentas ---------------------------------------------------

def test_marca_compone_el_aviso_desde_avisos():
    m = carga.fila(medida("cargada", mem=480))
    sus = carga.marca(m, "subscription", persona="Mariana")
    assert sus == {"nivel": "cargada", "mem_disponible_mb": 480, "motivo": "mem 480 < 5746",
                   "ruta": "subscription", "gesto": None,
                   "aviso": "maquina cargada (480 MB libres): contesto por Mariana"}
    loc = carga.marca(m, "local", gesto="/local")
    assert loc["aviso"] == "maquina cargada (480 MB libres): /local es local, puede tardar o fallar"
    assert carga.marca(m, "local")["aviso"] == "maquina cargada (480 MB libres): la respuesta es local, puede tardar o fallar"
    assert carga.marca(m, "subscription")["aviso"].endswith("contesto por la suscripcion")
    assert carga.marca(m, "subscription", motivo="local suspendido hasta holgada")["motivo"] == "local suspendido hasta holgada"
    # bajo justa con el local suspendido (histeresis) el aviso dice el nivel real
    j = carga.marca(carga.fila(medida("justa")), "subscription", persona="Mariana",
                    motivo="local suspendido hasta holgada")
    assert j["aviso"] == "maquina justa (6200 MB libres): contesto por Mariana" and j["nivel"] == "justa"


def test_cuentas_del_dia_cuenta_solo_hoy_y_solo_kind_carga():
    filas = [
        {"ts": "2026-09-11T10:00:00", "kind": "carga", "accion": "suscripcion"},
        {"ts": "2026-09-11T10:01:00", "kind": "carga", "accion": "suscripcion"},
        {"ts": "2026-09-11T10:02:00", "kind": "carga", "accion": "descarga"},
        {"ts": "2026-09-11T10:03:00", "kind": "carga", "accion": "pospone", "rutina_id": "r1"},
        {"ts": "2026-09-11T10:04:00", "kind": "carga", "accion": "pospone", "rutina_id": "r1"},   # el tick siguiente: la misma rutina
        {"ts": "2026-09-11T10:04:00", "kind": "carga", "accion": "vigia_error"},
        {"ts": "2026-09-11T10:04:30", "kind": "carga", "accion": "descarga_fallida"},
        {"ts": "2026-09-10T10:00:00", "kind": "carga", "accion": "suscripcion"},
        {"ts": "2026-09-11T10:05:00", "kind": "chat_turn", "accion": "suscripcion"},
    ]
    assert carga.cuentas_del_dia(filas, hoy="2026-09-11") == {
        "suscripcion": 2, "local_con_aviso": 0, "descarga": 1, "pospone": 1, "sin_3b": 0, "sin_vision": 0}
    assert carga.cuentas_del_dia([], hoy="2026-09-11") == {a: 0 for a in carga.ACCIONES}


# --- python -m calipso.carga ----------------------------------------------------

def test_esperar_que_vence_sale_con_3_y_no_duerme_de_mas():
    dormidos = []
    salida = io.StringIO()
    codigo = carga.main(["--esperar", "--tope", "30"], salida=salida,
                        medir_=lambda: medida("cargada"), dormir=lambda s: dormidos.append(s))
    assert codigo == 3
    assert dormidos == [15, 15]                       # 0, 15, 30 -> vencio
    assert "cargada" in salida.getvalue() and "vencio" in salida.getvalue()


def test_esperar_vuelve_0_en_cuanto_no_esta_cargada():
    """Ruling del controlador (ledger, tras la Task 1): con el server real
    corriendo la Ally en reposo mide `justa` (5800-6500 MB contra 6770 de
    holgada), asi que el default de --esperar es NO cargada: `justa` abre."""
    niveles = iter(["cargada", "justa", "holgada"])
    dormidos = []
    salida = io.StringIO()
    codigo = carga.main(["--esperar"], salida=salida,
                        medir_=lambda: medida(next(niveles)), dormir=lambda s: dormidos.append(s))
    assert codigo == 0 and dormidos == [15]
    assert salida.getvalue().count("\n") == 2
    assert "justa" in salida.getvalue().splitlines()[-1]


def test_esperar_con_holgada_exige_holgada():
    niveles = iter(["cargada", "justa", "holgada"])
    dormidos = []
    salida = io.StringIO()
    codigo = carga.main(["--esperar", "--holgada"], salida=salida,
                        medir_=lambda: medida(next(niveles)), dormir=lambda s: dormidos.append(s))
    assert codigo == 0 and dormidos == [15, 15]
    assert salida.getvalue().count("\n") == 3


def test_esperar_con_holgada_vence_con_3_si_solo_hay_justa():
    dormidos = []
    salida = io.StringIO()
    codigo = carga.main(["--esperar", "--holgada", "--tope", "30"], salida=salida,
                        medir_=lambda: medida("justa"), dormir=lambda s: dormidos.append(s))
    assert codigo == 3 and dormidos == [15, 15]
    assert "vencio" in salida.getvalue() and "holgada" in salida.getvalue().splitlines()[-1]


def test_la_ayuda_y_el_docstring_dicen_lo_que_espera_cada_flag():
    buf = io.StringIO()                                # argparse escribe la ayuda en sys.stdout
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit) as e:
        carga.main(["--help"])
    assert e.value.code == 0
    ayuda = buf.getvalue()
    assert "--holgada" in ayuda and "no cargada" in ayuda and "justa o holgada" in ayuda
    assert "--holgada" in carga.__doc__ and "no cargada" in carga.__doc__


def test_sin_flag_imprime_la_medicion_y_con_json_la_fila_entera():
    salida = io.StringIO()
    assert carga.main([], salida=salida, medir_=lambda: medida("justa")) == 0
    assert salida.getvalue().startswith("nivel=justa mem=6200MB necesidad=5746")
    salida = io.StringIO()
    assert carga.main(["--json"], salida=salida, medir_=lambda: medida("justa")) == 0
    assert json.loads(salida.getvalue())["nivel"] == "justa"


def test_carga_no_congela_el_home():
    assert not hasattr(carga, "CALIPSO_HOME")
    assert dataclasses.is_dataclass(carga.Carga)
