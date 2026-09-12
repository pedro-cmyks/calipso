"""calipso/carga.py -- el sensor de la maquina y las perillas del modelo local
(spec docs/superpowers/specs/2026-09-11-carga-design.md, secciones 2 y 3).

Pedro, 2026-09-11: "que todos los procesos que corran sean mindful de los
recursos y que ocupen cuando puedan ocupar y que sean mas ligeros cuando hay
mucha carga". El disparador: Ollama muerto por OOM mientras Pedro jugaba
(17:07:59, `anon-rss:5873568kB`, `Free swap = 232kB`) y el 7b todavia
cargado a las 17:50 con 500 MB disponibles.

PURO: lee /proc/meminfo, /proc/pressure/{memory,cpu}, /proc/loadavg y hace
GET /api/ps a Ollama (loopback, 0,5 s); no escribe nada y no tiene
CALIPSO_HOME. Alcance global ("la Ally esta cargada", no "mi cgroup"). Mide
recursos, no nombres de programas. Cuesta microsegundos mas el `ps`; se mide
por decision (en el hilo de `_decide`, en el `to_thread` del ticker), nunca en
el event loop, y no se cachea mas de CACHE_S.

Unidades: "MB" en los textos = MiB (kB // 1024 de /proc/meminfo, bytes // 2**20
del blob): la calibracion cierra SOLO asi (4466 + 1280 = 5746 contra 5736 MiB
del anon-rss del OOM; ver CALIBRACION).

Fail-open por senal (invariante 5): lo que no se pudo medir no decide; si
nada se pudo medir, `holgada` con `medido` todo en False y Calipso se comporta
como hoy. Rollback en caliente (ola de fix, punto 3): `CALIPSO_CARGA=off` en
el entorno del server (leido POR LLAMADA, `carga_activa`, patron de
`canarios.canarios_activos`) hace que `medir` devuelva esa misma Carga holgada
con `apagado: True` sin leer /proc ni hacer el GET: sin vigia, sin pospuestas,
sin marca, sin histeresis, perillas de holgada. Cualquier otro valor o ausente
es prendido.

Los tres niveles (contra la necesidad del modelo del chat):
  cargada  si mem_efectiva < necesidad  o  psi_mem some avg10 >= 20  o  full avg10 >= 5
  holgada  si mem_efectiva >= necesidad + MARGEN_LIBRE_MB  y  psi_mem some < 5
           y  psi_cpu some < 25  y  load1 < ncpu / 2
  justa    en el medio (incluida la CPU ocupada con RAM de sobra: el decode del
           7b usa los 16 hilos y le pega a un juego aunque sobre memoria)
donde la memoria EFECTIVA para el modelo (ruling de la ola de fix del
2026-09-11, punto 1, que revierte en parte el 9.1 del spec) es
  mem_efectiva_mb = MemAvailable + sum(size de los modelos de Calipso que /api/ps
                    de ESA medicion lista)
o sea exactamente lo que devuelve un evict. Medido en el smoke: con el 7b
cargado y NADA mas, MemAvailable baja de 7179 a 2709 (< 5746) y el sensor
decia `cargada`: el vigia descargaba el 7b a los 60 s de todo turno local en
holgada y el chat quedaba en suscripcion hasta la proxima holgada, lo
contrario de "ocupen cuando puedan ocupar" en el caso mas comun. Con la
memoria efectiva: 2709 + 5203 = 7912 -> holgada; el OOM del 17:07 (500 +
5203 = 5703 < 5746) sigue dando cargada, el vigia descarga y el chat va a
suscripcion con marca. El ping-pong desaparece por construccion: antes y
despues de un evict la memoria efectiva es la misma. Si /api/ps no responde
(`medido["ollama"]` False) la memoria efectiva es la disponible (fail-open).
Los avisos siguen diciendo "N MB libres" con MemAvailable, que es lo que
Pedro entiende.
El swap NO entra: es zram con swappiness 180 (lleno es estado normal). Se
mide y se anota, no decide (ruling 9.3).

Uso desde la terminal (los procesos del agente, spec 3.9):
  CALIPSO_HOME=$(mktemp -d) .venv/bin/python -m calipso.carga            # imprime la medicion
  CALIPSO_HOME=$(mktemp -d) .venv/bin/python -m calipso.carga --esperar  # bloquea hasta no cargada
      (`justa` o `holgada`; mide cada ESPERA_S; con --tope N segundos, default 600; al vencer sale
      con 3 y no corre nada). Con --holgada exige `holgada`.
  Ruling del controlador (ledger de la carga, tras la Task 1): con el server real corriendo (1,5 GB)
  la Ally en reposo mide `justa` (5800-6500 MB contra 6770 de holgada), asi que esperar `holgada`
  literal nunca abria; `justa` quiere decir que el modelo entra con menos de 1 GB de sobra: el
  margen es comodidad, no correccion. Costo si esta mal: un smoke que compite por el ultimo GB.
"""
from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime
import json
import os
import pathlib
import sys
import threading
import time
import urllib.request

from calipso import tokenizador

OLLAMA = "http://localhost:11434"
NIVELES = ("holgada", "justa", "cargada")

# `num_ctx` del chat local (era `server.CHAT_NUM_CTX`; vive aca para que el
# juez de /nube use el MISMO valor sin importar `server` -- ciclo: server ->
# privacidad.nube -> juez -> juez_llm). Ollama recrea el runner al cambiar
# `num_ctx`: con 4096 en el juez y 8192 en el chat, cada /nube recargaba el
# 7b (spec 3.5). 8192 es holgura, no capacidad: cada token de contexto cuesta
# RAM en la Ally. Como corta Ollama, medido por endpoint (spec canarios,
# seccion 1): /api/generate trunca el prompt plano desde el COMIENZO;
# /api/chat descarta primero los mensajes mas viejos que no son system.
CHAT_NUM_CTX = 8192

# Los umbrales, en un solo lugar (invariante 4). Cambiarlos es ruling de Pedro.
UMBRALES: dict[str, float | int] = {
    # necesidad del modelo = blob del GGUF + este margen. Calibrado al RSS
    # anonimo real del llama-server en el OOM: 5736 MiB con `-c 8192` y
    # `--no-mmap`, 1270 sobre el blob de 4466 (ruling 9.5)
    "MARGEN_MODELO_MB": 1280,
    # holgada exige la necesidad mas este margen libre
    "MARGEN_LIBRE_MB": 1024,
    # si el blob no se encuentra (Ollama no instalado, modelo no bajado)
    "NECESIDAD_DEFAULT_MB": 6000,
    # PSI de memoria (avg10, %): cargada por presion aunque sobre MemAvailable
    "PSI_MEM_SOME_CARGADA": 20.0,
    "PSI_MEM_FULL_CARGADA": 5.0,
    # holgada pide presion casi nula
    "PSI_MEM_SOME_HOLGADA": 5.0,
    # la CPU entra solo en justa (ruling 9.4): un juego en 16 cores no produce
    # presion de CPU (17:55: PSI cpu 0, load1 4,65)
    "PSI_CPU_SOME_HOLGADA": 25.0,
    "LOAD1_HOLGADA_FRACCION": 0.5,      # load1 < ncpu * 0.5
    # el sensor
    "CACHE_S": 2.0,
    "PS_TIMEOUT_S": 0.5,
    # el tick del vigia mide /api/ps con mas paciencia (ola de fix, punto
    # 6a): bajo carga 0,5 s puede no alcanzar y el vigia no descargaba nada
    "PS_TIMEOUT_TICK_S": 2.0,
    "EVICT_TIMEOUT_S": 10.0,
}

# La calibracion, anotada y EJECUTABLE (test_carga.py recorre todas las
# filas): escenas reales de la Ally (11638 MiB, 16 hilos), necesidad del 7b
# 5746 (4466 + 1280). Los PSI son `avg10` en %; `mem` es MemAvailable en MiB;
# `modelo_cargado_mb` es el `size` del 7b que /api/ps listaba (5203) o 0.
# Ola de fix del 2026-09-11 (punto 1): el nivel se recalculo con la memoria
# efectiva (MemAvailable + modelo cargado); las filas con el 7b adentro
# cambiaron: M y V pasan de cargada a holgada, 18:22 y 18:25 de cargada a
# justa (por load1 >= 8, y 18:22 tambien por 6681 < 6770); el OOM sigue cargada.
CALIBRACION: list[dict] = [
    {"cuando": "2026-09-11 17:07:59", "escena": "OOM: Ollama muerto mientras Pedro jugaba (swap libre 232 kB); efectiva 500 + 5203 = 5703 < 5746",
     "mem_disponible_mb": 500, "modelo_cargado_mb": 5203, "necesidad_mb": 5746, "psi_mem_some10": None, "psi_mem_full10": None,
     "psi_cpu_some10": None, "load1": None, "ncpu": 16, "swap_usado_mb": 5819, "nivel": "cargada"},
    {"cuando": "2026-09-11 17:55", "escena": "jugando, con el juego quieto; /api/ps vacio",
     "mem_disponible_mb": 6897, "modelo_cargado_mb": 0, "necesidad_mb": 5746, "psi_mem_some10": 0.0, "psi_mem_full10": 0.0,
     "psi_cpu_some10": 0.0, "load1": 4.65, "ncpu": 16, "swap_usado_mb": 5150, "nivel": "holgada"},
    {"cuando": "2026-09-11 18:05", "escena": "reposo (dos python, plasma y steam frios en zram: swap al 95%)",
     "mem_disponible_mb": 7377, "modelo_cargado_mb": 0, "necesidad_mb": 5746, "psi_mem_some10": 0.0, "psi_mem_full10": 0.0,
     "psi_cpu_some10": None, "load1": None, "ncpu": 16, "swap_usado_mb": 5200, "nivel": "holgada"},
    {"cuando": "2026-09-11 18:22:32", "escena": "smoke con el 7b cargado (Pedro no jugaba); swap libre 449 MiB; JUSTA por efectiva 6681 < 6770 y load1 8,54",
     "mem_disponible_mb": 1478, "modelo_cargado_mb": 5203, "necesidad_mb": 5746, "psi_mem_some10": 0.0, "psi_mem_full10": 0.0,
     "psi_cpu_some10": 0.0, "load1": 8.54, "ncpu": 16, "swap_usado_mb": 5370, "nivel": "justa"},
    {"cuando": "2026-09-11 18:25:38", "escena": "idem, tres minutos despues; swap libre 68 kB y PSI mem 0,16: el PSI no ve el OOM que viene; JUSTA por load1 9,96 (efectiva 6781)",
     "mem_disponible_mb": 1578, "modelo_cargado_mb": 5203, "necesidad_mb": 5746, "psi_mem_some10": 0.16, "psi_mem_full10": 0.16,
     "psi_cpu_some10": 0.46, "load1": 9.96, "ncpu": 16, "swap_usado_mb": 5819, "nivel": "justa"},
    {"cuando": "2026-09-11 18:41:37", "escena": "reposo tras el smoke, sin modelo cargado: JUSTA por memoria (5876 entre 5746 y 6770)",
     "mem_disponible_mb": 5876, "modelo_cargado_mb": 0, "necesidad_mb": 5746, "psi_mem_some10": 0.0, "psi_mem_full10": 0.0,
     "psi_cpu_some10": 0.04, "load1": 1.85, "ncpu": 16, "swap_usado_mb": 3615, "nivel": "justa"},
    # Las cinco que siguen las imprimio el smoke de la Task 6 (experimentos/
    # carga_smoke.py, corrida 3, 22:45-22:51, con el server REAL apagado por el
    # controlador; docs/superpowers/2026-09-11-smoke-carga.md). `cuando` es el
    # `medido_en` de cada Carga tal cual salio en el log. Ninguna llego a
    # `cargada` por PSI: en todas decidio MemAvailable (el PSI mas alto de la
    # corrida fue 1,51 durante la carga del 7b; el vigia lo vio en 0,76 con
    # 860 MB libres y 944 MB de zram libre a mitad del turno C).
    {"cuando": "2026-09-11T22:45:40",
     "escena": "smoke: el server desechable arriba (~1,5 GB) y el server real APAGADO; /api/ps vacio",
     "mem_disponible_mb": 7179, "modelo_cargado_mb": 0, "necesidad_mb": 5746, "psi_mem_some10": 0.0, "psi_mem_full10": 0.0,
     "psi_cpu_some10": 0.0, "load1": 2.02, "ncpu": 16, "swap_usado_mb": 4156, "nivel": "holgada"},
    {"cuando": "2026-09-11T22:47:15",
     "escena": "smoke, paso M: con el 7b cargado por /local (num_ctx 8192): HOLGADA por efectiva 2709 + 5203 = 7912 (punto 1)",
     "mem_disponible_mb": 2709, "modelo_cargado_mb": 5203, "necesidad_mb": 5746, "psi_mem_some10": 0.28, "psi_mem_full10": 0.28,
     "psi_cpu_some10": 0.0, "load1": 6.46, "ncpu": 16, "swap_usado_mb": 4194, "nivel": "holgada"},
    {"cuando": "2026-09-11T22:47:24",
     "escena": "smoke, paso V: el 7b recien recargado (keep_alive 5m); HOLGADA por efectiva 2469 + 5203 = 7672: el vigia NO lo descarga",
     "mem_disponible_mb": 2469, "modelo_cargado_mb": 5203, "necesidad_mb": 5746, "psi_mem_some10": 1.39, "psi_mem_full10": 1.39,
     "psi_cpu_some10": 0.0, "load1": 5.7, "ncpu": 16, "swap_usado_mb": 4191, "nivel": "holgada"},
    {"cuando": "2026-09-11T22:47:52",
     "escena": "cargada de verdad: el reservador del smoke (experimentos/carga_smoke.py, paso R, 1536 MB de "
               "bytes aleatorios, sin modelo cargado; docs/superpowers/2026-09-11-smoke-carga.md)",
     "mem_disponible_mb": 5555, "modelo_cargado_mb": 0, "necesidad_mb": 5746, "psi_mem_some10": 0.11, "psi_mem_full10": 0.11,
     "psi_cpu_some10": 0.0, "load1": 4.14, "ncpu": 16, "swap_usado_mb": 4191, "nivel": "cargada"},
    {"cuando": "2026-09-11T22:49:08",
     "escena": "smoke, paso P: el reservador otra vez hasta cargada tras C (2048 MB: cargar el 7b en C mando "
               "~700 MB frios de otros procesos a zram y al descargarse sobro memoria)",
     "mem_disponible_mb": 5513, "modelo_cargado_mb": 0, "necesidad_mb": 5746, "psi_mem_some10": 0.03, "psi_mem_full10": 0.03,
     "psi_cpu_some10": 0.0, "load1": 5.94, "ncpu": 16, "swap_usado_mb": 4887, "nivel": "cargada"},
]

# las acciones que llevan las filas `kind: carga` de telemetria (spec 4) y
# que la pestana Aduana cuenta por dia; `descarga_diferida`, `descarga_fallida`,
# `vigia_error` (decision 16 del plan) y `ps_no_medido` (ola de fix, punto
# 6a: cargada sin respuesta de /api/ps en el tick) existen tambien y no se cuentan
ACCIONES = ("suscripcion", "local_con_aviso", "descarga", "pospone", "sin_3b", "sin_vision")

# los textos del aviso, en un solo lugar (spec 3.2). Son una MARCA (senal ws
# + meta.carga), jamas texto de la respuesta
# `{nivel}` porque la marca tambien sale bajo `justa` con el local suspendido
# (histeresis, spec 3.4): "maquina justa (6200 MB libres): contesto por X"
AVISOS = {
    "suscripcion": "maquina {nivel} ({mb} MB libres): contesto por {persona}",
    "local": "maquina {nivel} ({mb} MB libres): {gesto} es local, puede tardar o fallar",
}
GESTO_SIN_NOMBRE = "la respuesta"
ESPERA_S = 15


@dataclasses.dataclass
class Carga:
    nivel: str
    motivo: str
    mem_disponible_mb: int
    # la memoria EFECTIVA para el modelo (punto 1 de la ola de fix): la
    # disponible mas el `size` de los modelos propios que /api/ps listo en
    # esta medicion; es la que decide el nivel
    mem_efectiva_mb: int
    modelo_cargado_mb: int
    mem_total_mb: int
    swap_usado_mb: int
    swap_libre_mb: int
    psi_mem_some10: float
    psi_mem_full10: float
    psi_cpu_some10: float
    load1: float
    ncpu: int
    modelos_cargados: list[str]
    necesidad_mb: int
    modelo: str
    medido: dict[str, bool]
    medido_en: str
    # True solo con CALIPSO_CARGA=off (el rollback en caliente, punto 3)
    apagado: bool = False


def fila(c: Carga) -> dict:
    """La Carga como dict plano: la fila de telemetria (`kind: carga`),
    `verdict["carga_medicion"]` y `GET /api/carga`."""
    return dataclasses.asdict(c)


# --- lectura de /proc -----------------------------------------------------------

def _leer_proc(ruta: str) -> str:
    return pathlib.Path(ruta).read_text(encoding="utf-8")


def _meminfo(texto: str) -> dict[str, int]:
    """{"MemTotal": kB, ...} de /proc/meminfo."""
    out: dict[str, int] = {}
    for linea in texto.splitlines():
        clave, _, resto = linea.partition(":")
        partes = resto.split()
        if partes and partes[0].isdigit():
            out[clave.strip()] = int(partes[0])
    return out


def _psi(texto: str) -> tuple[float, float]:
    """(some avg10, full avg10) de /proc/pressure/{memory,cpu}; `full` puede
    faltar (cpu en kernels viejos): 0.0."""
    valores = {"some": 0.0, "full": 0.0}
    for linea in texto.splitlines():
        campos = linea.split()
        if campos and campos[0] in valores:
            for campo in campos[1:]:
                if campo.startswith("avg10="):
                    valores[campos[0]] = float(campo[len("avg10="):])
    return valores["some"], valores["full"]


def _loadavg(texto: str) -> float:
    return float(texto.split()[0])


# --- la necesidad y el nivel ----------------------------------------------------

def necesidad_mb(modelo: str | None) -> int:
    """Blob del GGUF del modelo (~/.ollama, `tokenizador.blob_del_modelo`) mas
    MARGEN_MODELO_MB; NECESIDAD_DEFAULT_MB si no se encuentra. Una sola fuente
    (ruling 9.5): el `size` de /api/ps solo existe cuando ya se cargo.
    Fail-open de verdad (ola de fix, punto 4): CUALQUIER error del manifiesto
    (un JSON valido que no es dict, `[1]`, levanta AttributeError en
    `blob_del_modelo`) da el default; antes solo se atrapaba OSError y
    `_decide` reventaba en cada turno."""
    if not modelo:
        return int(UMBRALES["NECESIDAD_DEFAULT_MB"])
    try:
        blob = tokenizador.blob_del_modelo(modelo)
        if blob is None:
            return int(UMBRALES["NECESIDAD_DEFAULT_MB"])
        return blob.stat().st_size // 2**20 + int(UMBRALES["MARGEN_MODELO_MB"])
    except Exception:
        return int(UMBRALES["NECESIDAD_DEFAULT_MB"])


def nivel(mem_disponible_mb: int | None, necesidad_mb: int,
          psi_mem_some10: float | None, psi_mem_full10: float | None,
          psi_cpu_some10: float | None, load1: float | None,
          ncpu: int, modelo_cargado_mb: int = 0) -> tuple[str, str]:
    """(nivel, motivo), puro sobre numeros. `None` en una senal = no se pudo
    medir: esa senal no decide (fail-open por senal). Cargada si CUALQUIER
    senal medida dispara; holgada si TODAS las medidas pasan; justa en el
    medio; nada medido -> holgada. La memoria que decide es la EFECTIVA:
    `mem_disponible_mb + modelo_cargado_mb` (punto 1 de la ola de fix); el
    motivo dice `mem efectiva N` cuando hay modelo cargado y `mem N` si no."""
    u = UMBRALES
    mem_efectiva_mb = None if mem_disponible_mb is None else mem_disponible_mb + (modelo_cargado_mb or 0)
    etiqueta = "mem efectiva" if modelo_cargado_mb else "mem"
    if mem_efectiva_mb is not None and mem_efectiva_mb < necesidad_mb:
        return "cargada", f"{etiqueta} {mem_efectiva_mb} < {necesidad_mb}"
    if psi_mem_some10 is not None and psi_mem_some10 >= u["PSI_MEM_SOME_CARGADA"]:
        return "cargada", f"psi_mem_some10 {psi_mem_some10} >= {u['PSI_MEM_SOME_CARGADA']:g}"
    if psi_mem_full10 is not None and psi_mem_full10 >= u["PSI_MEM_FULL_CARGADA"]:
        return "cargada", f"psi_mem_full10 {psi_mem_full10} >= {u['PSI_MEM_FULL_CARGADA']:g}"
    motivos = []
    if mem_efectiva_mb is not None and mem_efectiva_mb < necesidad_mb + u["MARGEN_LIBRE_MB"]:
        motivos.append(f"{etiqueta} {mem_efectiva_mb} < {necesidad_mb}+{u['MARGEN_LIBRE_MB']}")
    if psi_mem_some10 is not None and psi_mem_some10 >= u["PSI_MEM_SOME_HOLGADA"]:
        motivos.append(f"psi_mem_some10 {psi_mem_some10} >= {u['PSI_MEM_SOME_HOLGADA']:g}")
    if psi_cpu_some10 is not None and psi_cpu_some10 >= u["PSI_CPU_SOME_HOLGADA"]:
        motivos.append(f"psi_cpu_some10 {psi_cpu_some10} >= {u['PSI_CPU_SOME_HOLGADA']:g}")
    if load1 is not None and ncpu and load1 >= ncpu * u["LOAD1_HOLGADA_FRACCION"]:
        motivos.append(f"load1 {load1} >= {ncpu * u['LOAD1_HOLGADA_FRACCION']}")
    if motivos:
        return "justa", "; ".join(motivos)
    return "holgada", ""


# --- medir ----------------------------------------------------------------------

_ultima: Carga | None = None
_ultima_t: float = 0.0


def carga_activa() -> bool:
    """El rollback en caliente (ola de fix, punto 3): False solo con
    CALIPSO_CARGA=off (sin distinguir mayusculas); ausente, vacio o cualquier
    otro valor es prendido. Se lee por llamada, nunca congelado."""
    return os.environ.get("CALIPSO_CARGA", "on").strip().lower() != "off"


def _apagada(modelo: str, ncpu: int, ahora: datetime.datetime | None) -> Carga:
    """La Carga de CALIPSO_CARGA=off: holgada, nada medido, `apagado` True."""
    return Carga(nivel="holgada", motivo="", mem_disponible_mb=0, mem_efectiva_mb=0,
                 modelo_cargado_mb=0, mem_total_mb=0, swap_usado_mb=0, swap_libre_mb=0,
                 psi_mem_some10=0.0, psi_mem_full10=0.0, psi_cpu_some10=0.0, load1=0.0,
                 ncpu=ncpu, modelos_cargados=[], necesidad_mb=int(UMBRALES["NECESIDAD_DEFAULT_MB"]),
                 modelo=modelo,
                 medido={"meminfo": False, "psi_mem": False, "psi_cpu": False, "loadavg": False, "ollama": False},
                 medido_en=(ahora or datetime.datetime.now()).isoformat(timespec="seconds"),
                 apagado=True)


def medir(modelo: str | None = None, *, leer=None, ps=None, ncpu: int | None = None,
          necesidad: int | None = None, ahora: datetime.datetime | None = None,
          modelos_propios=None, ps_timeout: float | None = None) -> Carga:
    """La medicion. `leer(ruta) -> str` (OSError si no esta), `ps() -> list |
    None` (None = Ollama no responde), `ncpu` y `necesidad` son inyectables
    para los tests; sin inyeccion se lee /proc, se hace GET /api/ps y se
    cachea CACHE_S. Toda medicion queda como la ultima (`nivel_reciente`).
    `modelos_propios` son los nombres cuyo `size` en /api/ps suma a la
    memoria efectiva (los que el vigia puede descargar: el server pasa
    `_modelos_de_calipso()`); sin la lista cuenta solo `modelo`. `ps_timeout`
    es el del GET a /api/ps (el tick del vigia pasa PS_TIMEOUT_TICK_S)."""
    global _ultima, _ultima_t
    inyectado = leer is not None or ps is not None or ncpu is not None or necesidad is not None
    modelo = modelo or ""
    if not carga_activa():
        c = _apagada(modelo, ncpu or os.cpu_count() or 1, ahora)
        _ultima, _ultima_t = c, time.monotonic()
        return c
    propios = set(modelos_propios) if modelos_propios is not None else ({modelo} if modelo else set())
    if (not inyectado and _ultima is not None and _ultima.modelo == modelo
            and time.monotonic() - _ultima_t < UMBRALES["CACHE_S"]):
        return _ultima
    leer = leer or _leer_proc
    ps = ps or (lambda: ollama_loaded_models(timeout=ps_timeout))
    ncpu = ncpu or os.cpu_count() or 1
    medido = {"meminfo": False, "psi_mem": False, "psi_cpu": False, "loadavg": False, "ollama": False}

    mem: dict[str, int] = {}
    try:
        mem = _meminfo(leer("/proc/meminfo"))
        medido["meminfo"] = "MemAvailable" in mem
    except Exception:
        pass
    # el PSI se mide POR ARCHIVO (ola de fix, punto 6c): si falla uno, el
    # otro sigue decidiendo; antes se descartaban los dos en bloque
    psi_mem = psi_cpu = (0.0, 0.0)
    try:
        psi_mem = _psi(leer("/proc/pressure/memory"))
        medido["psi_mem"] = True
    except Exception:
        pass
    try:
        psi_cpu = _psi(leer("/proc/pressure/cpu"))
        medido["psi_cpu"] = True
    except Exception:
        pass
    load1 = 0.0
    try:
        load1 = _loadavg(leer("/proc/loadavg"))
        medido["loadavg"] = True
    except Exception:
        pass
    modelos: list[str] = []
    modelo_cargado = 0
    try:
        lista = ps()
        if lista is not None:
            modelos = [str(m.get("name", "")) for m in lista if m.get("name")]
            modelo_cargado = sum(int(m.get("size_mb") or 0) for m in lista
                                 if m.get("name") and str(m.get("name")) in propios)
            medido["ollama"] = True
    except Exception:
        pass

    necesidad_ = int(necesidad) if necesidad is not None else necesidad_mb(modelo or None)
    disponible = mem.get("MemAvailable", 0) // 1024
    swap_total = mem.get("SwapTotal", 0) // 1024
    swap_libre = mem.get("SwapFree", 0) // 1024
    n, motivo = nivel(disponible if medido["meminfo"] else None, necesidad_,
                      psi_mem[0] if medido["psi_mem"] else None,
                      psi_mem[1] if medido["psi_mem"] else None,
                      psi_cpu[0] if medido["psi_cpu"] else None,
                      load1 if medido["loadavg"] else None, ncpu,
                      modelo_cargado_mb=modelo_cargado)
    c = Carga(nivel=n, motivo=motivo, mem_disponible_mb=disponible,
              mem_efectiva_mb=disponible + modelo_cargado, modelo_cargado_mb=modelo_cargado,
              mem_total_mb=mem.get("MemTotal", 0) // 1024,
              swap_usado_mb=max(swap_total - swap_libre, 0), swap_libre_mb=swap_libre,
              psi_mem_some10=psi_mem[0], psi_mem_full10=psi_mem[1], psi_cpu_some10=psi_cpu[0],
              load1=load1, ncpu=ncpu, modelos_cargados=modelos, necesidad_mb=necesidad_,
              modelo=modelo, medido=medido,
              medido_en=(ahora or datetime.datetime.now()).isoformat(timespec="seconds"))
    _ultima, _ultima_t = c, time.monotonic()
    return c


def nivel_reciente() -> str:
    """El nivel de la ultima medicion de este proceso ("holgada" si no hubo):
    lo que usan los usos sueltos del modelo (agentes, clasificador, jefe, juez,
    vision) para `payload_local` sin enhebrar el nivel por tres firmas."""
    return _ultima.nivel if _ultima is not None else "holgada"


def olvidar() -> None:
    """Para los tests: sin ultima medicion, sin suspension, contador en cero."""
    global _ultima, _ultima_t, local_suspendido, en_uso
    _ultima, _ultima_t = None, 0.0
    local_suspendido = False
    with _lock:
        en_uso = 0


# --- las perillas por nivel (spec 2, ultimo punto) ------------------------------

_KEEP_ALIVE = {"holgada": "5m", "justa": "2m", "cargada": "30s"}


def keep_alive(nivel: str | None):
    """holgada: el default de Ollama (5 min), explicito porque en Ollama gana
    el keep_alive de la ULTIMA request y tras un evict (0) hay que devolverlo;
    justa: 2 min; cargada: "30s", NO 0 (ola de fix del 2026-09-11, punto 2).
    Medido en el smoke con 0: Ollama descargaba el 7b al terminar CADA pasada
    y /nube (juez + turno) y las reentradas del abismo pagaban una carga
    desde disco por pasada (turno N 48-56 s contra A 36-42 s; a mitad de N
    /api/ps vacio y 4212 MB libres contra 1925 tres segundos antes). Con 30 s
    las pasadas de un mismo turno comparten el runner y el vigia descarga en
    el tick siguiente (60 s) cuando `en_uso` llega a 0: el 7b no sobrevive
    mas de ~90 s despues del turno."""
    return _KEEP_ALIVE.get(nivel or "holgada", "5m")


def num_thread(nivel: str | None, ncpu: int | None = None) -> int | None:
    """holgada: ninguno (Ollama decide); justa/cargada: la mitad de los hilos."""
    if (nivel or "holgada") == "holgada":
        return None
    return max(1, (ncpu or os.cpu_count() or 2) // 2)


def payload_local(payload: dict, nivel: str | None = None) -> dict:
    """Un solo helper para hablar con Ollama (spec 3.6): agrega `keep_alive` de
    primer nivel y `options.num_thread` segun el nivel (el reciente si no viene).
    Devuelve un dict NUEVO; no muta `payload` ni sus `options`."""
    nivel = nivel or nivel_reciente()
    nuevo = dict(payload)
    nuevo["keep_alive"] = keep_alive(nivel)
    hilos = num_thread(nivel)
    if hilos is not None:
        nuevo["options"] = {**(payload.get("options") or {}), "num_thread": hilos}
    return nuevo


# --- el contador de uso (spec 3.3, invariante 6) --------------------------------

_lock = threading.Lock()
en_uso: int = 0


def tomar() -> None:
    global en_uso
    with _lock:
        en_uso += 1


def soltar() -> None:
    global en_uso
    with _lock:
        en_uso = max(en_uso - 1, 0)


@contextlib.contextmanager
def usando():
    """El modelo local esta en uso mientras dura el bloque: el vigia no
    descarga con `en_uso > 0`."""
    tomar()
    try:
        yield
    finally:
        soltar()


class Uso:
    """Un tenedor idempotente del contador para un turno del chat (de que la
    ruta queda final hasta `done`, pasadas del abismo incluidas): `tomar()`
    suma una sola vez, `soltar()` resta solo si tomo."""

    def __init__(self) -> None:
        self._tiene = False

    def tomar(self) -> None:
        if not self._tiene:
            tomar()
            self._tiene = True

    def soltar(self) -> None:
        if self._tiene:
            soltar()
            self._tiene = False


# --- la histeresis (spec 3.4, ruling 9.6) --------------------------------------

local_suspendido: bool = False


def suspender() -> None:
    """Tras una descarga por carga o un turno mandado a suscripcion por carga:
    el chat vuelve a local solo cuando una medicion da holgada."""
    global local_suspendido
    local_suspendido = True


def liberar() -> None:
    """`/local` explicito rompe la suspension."""
    global local_suspendido
    local_suspendido = False


def liberar_si_holgada(c: Carga) -> bool:
    """Apaga la suspension SOLO con una medicion holgada (no justa: descargar
    5,4 GB sube MemAvailable justo por encima de la necesidad). True si la apago."""
    if local_suspendido and c.nivel == "holgada":
        liberar()
        return True
    return False


# --- Ollama: lo que sirve de resource_dispatcher (ruling 9.7) -------------------

def _ollama_get(path: str, base: str = OLLAMA, timeout: float | None = None):
    """GET al Ollama local; None si no responde (no levanta)."""
    try:
        req = urllib.request.Request(f"{base}{path}")
        with urllib.request.urlopen(req, timeout=timeout or UMBRALES["PS_TIMEOUT_S"]) as r:
            return json.loads(r.read().decode())
    except Exception:
        return None


def ollama_loaded_models(base: str = OLLAMA, timeout: float | None = None) -> list[dict] | None:
    """Modelos cargados en Ollama (/api/ps): [{name, size_mb, expires_at}].
    None si Ollama no responde (distinto de [] = responde y no hay ninguno).
    `size_mb` es `size_vram or size` (en esta maquina size_vram es 0)."""
    data = _ollama_get("/api/ps", base, timeout)
    if not isinstance(data, dict):
        return None
    out = []
    for m in data.get("models") or []:
        size_bytes = m.get("size_vram") or m.get("size") or 0
        out.append({"name": m.get("name", ""), "size_mb": size_bytes // (1024 * 1024),
                    "expires_at": m.get("expires_at", "")})
    return out


def ollama_evict(model: str, base: str = OLLAMA, timeout: float | None = None) -> bool:
    """Descarga `model` de la RAM de Ollama con una inferencia vacia y
    keep_alive 0. OJO: a un modelo NO cargado esto lo CARGA (ruling 9.12): el
    vigia solo evicta lo que vio en /api/ps en la misma medicion."""
    payload = json.dumps({"model": model, "prompt": "", "stream": False,
                          "keep_alive": 0}).encode()
    try:
        req = urllib.request.Request(f"{base}/api/generate", data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=timeout or UMBRALES["EVICT_TIMEOUT_S"]):
            pass
        return True
    except Exception:
        return False


# --- la marca y las cuentas ------------------------------------------------------

def marca(medicion: dict, ruta: str, gesto: str | None = None,
          persona: str | None = None, motivo: str | None = None) -> dict:
    """Lo que viaja como senal `{type: "carga", ...}` y se guarda en
    `meta.carga`: los cuatro campos del spec mas `gesto` y `aviso` (el texto
    lo compone el server desde AVISOS; JS solo lo muestra)."""
    mb = medicion.get("mem_disponible_mb")
    nivel_ = medicion.get("nivel") or "cargada"
    if ruta == "subscription":
        aviso = AVISOS["suscripcion"].format(nivel=nivel_, mb=mb, persona=persona or "la suscripcion")
    else:
        aviso = AVISOS["local"].format(nivel=nivel_, mb=mb, gesto=gesto or GESTO_SIN_NOMBRE)
    return {"nivel": medicion.get("nivel"), "mem_disponible_mb": mb,
            "motivo": motivo if motivo is not None else medicion.get("motivo", ""),
            "ruta": ruta, "gesto": gesto, "aviso": aviso}


def cuentas_del_dia(filas: list[dict], hoy: str | None = None) -> dict[str, int]:
    """Las cuentas del dia derivadas de telemetria (spec 4): filas `kind:
    carga` cuyo `ts` empieza por hoy, por `accion` de ACCIONES. `pospone`
    cuenta RUTINAS distintas (`rutina_id`), no filas: el ticker escribe una
    fila por rutina vencida en cada tick (60 s) mientras dure la carga."""
    hoy = hoy or datetime.date.today().isoformat()
    cuentas = {a: 0 for a in ACCIONES}
    pospuestas: set = set()
    for f in filas:
        if f.get("kind") != "carga" or not str(f.get("ts", "")).startswith(hoy):
            continue
        if f.get("accion") == "pospone":
            pospuestas.add(f.get("rutina_id") or f.get("ts"))
        elif f.get("accion") in cuentas:
            cuentas[f["accion"]] += 1
    cuentas["pospone"] = len(pospuestas)
    return cuentas


# --- python -m calipso.carga ----------------------------------------------------

def _linea(c: Carga) -> str:
    return (f"nivel={c.nivel} mem={c.mem_disponible_mb}MB "
            + (f"efectiva={c.mem_efectiva_mb}MB (modelo {c.modelo_cargado_mb}MB) " if c.modelo_cargado_mb else "")
            + f"necesidad={c.necesidad_mb} "
            f"psi_mem={c.psi_mem_some10}/{c.psi_mem_full10} psi_cpu={c.psi_cpu_some10} "
            f"load1={c.load1}/{c.ncpu} swap_usado={c.swap_usado_mb}MB "
            f"modelos={c.modelos_cargados} medido={c.medido}"
            + (f" motivo={c.motivo}" if c.motivo else ""))


def _modelo_configurado() -> str:
    from calipso import config as calipso_config   # lee config.json del CALIPSO_HOME (solo lectura)
    return calipso_config.load_config()["local"]["model"]


def _modelos_configurados() -> set[str]:
    """Los modelos propios para la memoria efectiva desde la terminal: el del
    chat y el del clasificador (el server suma el de vision si hay)."""
    from calipso import config as calipso_config
    cfg = calipso_config.load_config()
    return {cfg["local"]["model"], (cfg.get("classifier") or {}).get("model") or cfg["local"]["model"]}


def main(argv: list[str] | None = None, salida=None, medir_=None, dormir=None) -> int:
    salida = salida or sys.stdout
    dormir = dormir or time.sleep
    ap = argparse.ArgumentParser(prog="python -m calipso.carga",
                                 description="la carga de la maquina segun el sensor de Calipso")
    ap.add_argument("--esperar", action="store_true",
                    help=f"bloquear hasta no cargada (justa o holgada), midiendo cada {ESPERA_S} s")
    ap.add_argument("--holgada", action="store_true",
                    help="con --esperar: exigir holgada (el default abre con justa)")
    ap.add_argument("--tope", type=int, default=600,
                    help="segundos maximos de --esperar; al vencer sale con 3 y no corre nada")
    ap.add_argument("--json", action="store_true", help="la medicion entera como JSON")
    args = ap.parse_args(argv)
    medir_ = medir_ or (lambda: medir(_modelo_configurado(), modelos_propios=_modelos_configurados()))
    if not args.esperar:
        c = medir_()
        print(json.dumps(fila(c), ensure_ascii=False) if args.json else _linea(c), file=salida)
        return 0
    abre = ("holgada",) if args.holgada else ("holgada", "justa")
    esperado = 0
    while True:
        c = medir_()
        print(f"[carga] {esperado} s: {_linea(c)}", file=salida, flush=True)
        if c.nivel in abre:
            return 0
        if esperado >= args.tope:
            print(f"[carga] vencio el tope de {args.tope} s sin {' ni '.join(abre)}: "
                  "no corro nada (codigo 3)", file=salida, flush=True)
            return 3
        dormir(ESPERA_S)
        esperado += ESPERA_S


if __name__ == "__main__":
    sys.exit(main())
