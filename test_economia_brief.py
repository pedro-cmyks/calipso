# test_economia_brief.py
"""Tests del brief de economia que entra en el contexto de cada turno.

Dos caminos a probar (`economia_brief` en calipso/prompt_compiler.py):
apagada (falta algun archivo de los tres que Pagador.desde_entorno exige)
y activa (los tres estan, se lee bajo el candado del libro). Tambien se
prueba el kwarg nuevo de `context_sections`/`compile_context`, y por que
`_build_context` en calipso/server.py se despacha SIEMPRE con
asyncio.to_thread: `economia_brief` toma un flock bloqueante que un cierre
semanal puede sostener largo rato.
"""
import asyncio
import json
import threading
import time

import pytest

from calipso import prompt_compiler
from calipso.economia import departamentos as deps
from calipso.economia import bus as bus_mod
from calipso.economia import tipos as t
from calipso.economia.candado import candado
from calipso.economia.kernel import Kernel
from calipso.economia.libro import Libro
from calipso.economia.personal import LibroPersonal

TS = "2026-08-25T10:00:00"
W = "2026-W35"


def _sembrar_suscripciones(eco):
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")


def _sembrar_economia_activa(tmp_path, n_departamentos=2, n_proyectos=1):
    """Economia minima con un departamento con plata, uno de apoyo en cero
    (legitimo: no todo saldo bajo es una alarma) y un proyecto financiado."""
    eco = tmp_path / "economia"
    eco.mkdir()
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("mercadeo", deps.ZONA_FABRICA,
                             techo_api_ciclo_mm=500_000))
    r.alta(deps.Departamento("apoyo", deps.ZONA_FABRICA))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    for i in range(max(0, n_departamentos - 3)):
        r.alta(deps.Departamento(f"extra{i}", deps.ZONA_FABRICA))
    _sembrar_suscripciones(eco)
    capital = max(200_000, 25_000 * max(n_proyectos, 1))
    k.acunar(TS, W, "dep:mercadeo", capital, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    bus = bus_mod.Bus(eco / "bus.jsonl")
    for i in range(n_proyectos):
        id_ = f"radar{i}"
        bus.alta(TS, W, id_, "dep:mercadeo", f"Radar de mercado {i}",
                 presupuesto_mm=50_000, retorno_mm=150_000,
                 criterio={"gasto_max_mm": 50_000})
        k.transferir(TS, W, "dep:mercadeo", f"trabajo:{id_}", 20_000,
                     motivo="financiacion")
        bus.marcar(TS, W, id_, "financiada")
        k.destruir(TS, W, f"trabajo:{id_}", 1_000, motivo="api")
    return tmp_path


# -- camino apagado ---------------------------------------------------------

def test_apagada_sin_economia_dice_la_verdad_concreta(tmp_path):
    texto = prompt_compiler.economia_brief(tmp_path)
    assert "apagada" in texto
    assert "libro.jsonl" in texto
    assert "departamentos.json" in texto
    assert "suscripciones.json" in texto
    assert str(tmp_path / "economia") in texto
    # la mentira que origino la tarea: nunca "no tengo acceso" / sandbox
    assert "no tengo acceso" not in texto.lower()
    assert "sandbox" not in texto.lower()


def test_apagada_lista_solo_lo_que_falta(tmp_path):
    eco = tmp_path / "economia"
    eco.mkdir()
    (eco / "libro.jsonl").write_text("", encoding="utf-8")
    (eco / "departamentos.json").write_text("{}", encoding="utf-8")
    # falta suscripciones.json
    texto = prompt_compiler.economia_brief(tmp_path)
    assert "apagada" in texto
    assert "suscripciones.json" in texto
    assert "libro.jsonl" not in texto
    assert "departamentos.json" not in texto


def test_apagada_acepta_base_como_string(tmp_path):
    texto = prompt_compiler.economia_brief(str(tmp_path))
    assert "apagada" in texto


# -- camino activo ------------------------------------------------------

def test_activa_lista_departamentos_y_marca_el_saldo_cero_como_legitimo(tmp_path):
    _sembrar_economia_activa(tmp_path)
    texto = prompt_compiler.economia_brief(tmp_path)
    assert "La economia de la fabrica esta activa" in texto
    assert "dep:mercadeo" in texto
    assert "dep:apoyo" in texto
    assert "saldo 0 mm" in texto  # apoyo nunca recibio capital
    assert "no mide su salud" in texto  # el saldo bajo no es una alarma


def test_activa_lista_proyectos_financiados(tmp_path):
    _sembrar_economia_activa(tmp_path)
    texto = prompt_compiler.economia_brief(tmp_path)
    assert "radar0" in texto
    assert "Radar de mercado 0" in texto
    assert "dueno dep:mercadeo" in texto
    assert "presupuesto 50000 mm" in texto
    assert "gastado 1000 mm" in texto


def test_activa_no_muestra_proyectos_no_financiados(tmp_path):
    _sembrar_economia_activa(tmp_path, n_proyectos=0)
    eco = tmp_path / "economia"
    bus = bus_mod.Bus(eco / "bus.jsonl")
    bus.alta(TS, W, "propuesta_sin_financiar", "dep:mercadeo", "todavia no",
             presupuesto_mm=1_000, retorno_mm=2_000,
             criterio={"gasto_max_mm": 1_000})
    texto = prompt_compiler.economia_brief(tmp_path)
    assert "propuesta_sin_financiar" not in texto
    assert "Sin proyectos financiados activos" in texto


def test_activa_reporta_saldos_generales_y_suscripciones(tmp_path):
    _sembrar_economia_activa(tmp_path)
    texto = prompt_compiler.economia_brief(tmp_path)
    assert "tesoro" in texto
    assert "direccion" in texto
    assert "cuenta_pedro" in texto
    assert "claude_max" in texto
    assert "milimonedas" in texto  # aclara la unidad una sola vez


def test_activa_reporta_pendientes_cuando_hay(tmp_path):
    _sembrar_economia_activa(tmp_path)
    eco = tmp_path / "economia"
    # un congelado no gasta -> el cargo de suscripcion no se puede aplicar.
    # (Antes se usaba una semana no operativa; desde que la capacidad se
    # descuenta en cristales, un consumo no necesita la semana abierta.)
    from calipso.economia.pagador import Pagador
    k = Kernel(Libro(eco / "libro.jsonl"))
    deps.declarar_quiebra(k, TS, W, "dep:mercadeo")
    p = Pagador.desde_entorno(tmp_path)
    p.cargar_suscripcion(TS, W, "dep:mercadeo", "claude_max")
    texto = prompt_compiler.economia_brief(tmp_path)
    assert "Cargos pendientes de aplicar: 1" in texto


def test_activa_incluye_resumen_personal_solo_si_existe(tmp_path):
    _sembrar_economia_activa(tmp_path)
    texto_sin = prompt_compiler.economia_brief(tmp_path)
    assert "Libro personal" not in texto_sin
    lp = LibroPersonal(tmp_path / "economia" / "personal.jsonl")
    lp.registrar(TS, W, "ingreso", 500_000, "sueldo")
    lp.registrar(TS, W, "gasto", 100_000, "alquiler")
    texto_con = prompt_compiler.economia_brief(tmp_path)
    assert "Libro personal" in texto_con
    assert "ingresos 500000 mm" in texto_con
    assert "gastos 100000 mm" in texto_con
    assert "neto 400000 mm" in texto_con


def test_activa_congelado_se_marca(tmp_path):
    _sembrar_economia_activa(tmp_path)
    eco = tmp_path / "economia"
    k = Kernel(Libro(eco / "libro.jsonl"))
    deps.declarar_quiebra(k, TS, W, "dep:apoyo")
    texto = prompt_compiler.economia_brief(tmp_path)
    assert "dep:apoyo (fabrica): saldo 0 mm, congelado" in texto


# -- techo de tamano ------------------------------------------------------

def test_activa_respeta_el_techo_de_tamano_con_muchos_departamentos_y_proyectos(tmp_path):
    _sembrar_economia_activa(tmp_path, n_departamentos=40, n_proyectos=25)
    texto = prompt_compiler.economia_brief(tmp_path)
    assert len(texto) <= prompt_compiler.ECONOMIA_BRIEF_MAX
    assert "departamento(s) mas, no listados" in texto
    assert "proyecto(s) mas, no listados" in texto


# -- degradacion ante lectura fallida (no es "apagada") --------------------

def test_activa_pero_lectura_fallida_no_se_confunde_con_apagada(tmp_path):
    _sembrar_economia_activa(tmp_path)
    # corrompe suscripciones.json DESPUES de que los tres archivos ya
    # existen: Pagador.desde_entorno solo mira que existan, no que sean
    # JSON valido, asi que esto dispara la excepcion recien al leer.
    (tmp_path / "economia" / "suscripciones.json").write_text(
        "esto no es json", encoding="utf-8")
    texto = prompt_compiler.economia_brief(tmp_path)
    assert "apagada" not in texto
    assert "activa" in texto
    assert "no se pudo leer" in texto


# -- context_sections / compile_context: el kwarg nuevo --------------------

def test_context_sections_incluye_la_seccion_economia_cuando_hay_texto():
    secciones = prompt_compiler.context_sections(
        "Eres Calipso.", economia="datos economicos de prueba")
    assert ("Economia", "datos economicos de prueba") in secciones


def test_context_sections_omite_economia_vacia():
    secciones = prompt_compiler.context_sections("Eres Calipso.", economia="")
    titulos = [t for t, _ in secciones]
    assert "Economia" not in titulos


def test_compile_context_renderiza_la_seccion_economia():
    texto = prompt_compiler.compile_context(
        "Eres Calipso.", economia="la fabrica tiene N mm en el tesoro")
    assert "=== Economia ===" in texto
    assert "la fabrica tiene N mm en el tesoro" in texto


def test_economia_va_antes_del_estado_operativo():
    # orden estable -> volatil -> estado (docstring de context_sections)
    texto = prompt_compiler.compile_context(
        "Eres Calipso.", economia="X", runtime="Y")
    assert texto.index("=== Economia ===") < texto.index("=== Estado operativo ===")


# -- el candado: por que _build_context se llama SIEMPRE desde un hilo -----

def test_economia_brief_bloquea_mientras_el_candado_esta_tomado(tmp_path):
    """`economia_brief` toma el mismo candado (flock bloqueante) que un
    cierre semanal puede sostener largo rato. Esto demuestra el mecanismo
    por el cual llamarlo directo sobre el event loop lo colgaria entero;
    por eso las 4 llamadas a `_build_context` en calipso/server.py van bajo
    `asyncio.to_thread` (ver el test siguiente para el lado bueno)."""
    _sembrar_economia_activa(tmp_path)
    ruta_libro = tmp_path / "economia" / "libro.jsonl"
    bloqueado = threading.Event()
    soltar = threading.Event()

    def mantener_candado():
        with candado(ruta_libro):
            bloqueado.set()
            soltar.wait(timeout=2)

    hilo = threading.Thread(target=mantener_candado)
    hilo.start()
    assert bloqueado.wait(timeout=2), "el hilo no tomo el candado a tiempo"

    resultado = {}

    def leer():
        resultado["texto"] = prompt_compiler.economia_brief(tmp_path)

    lector = threading.Thread(target=leer)
    inicio = time.monotonic()
    lector.start()
    time.sleep(0.15)
    assert lector.is_alive(), (
        "economia_brief termino sin esperar el candado: dejo de ser "
        "seguro leer el libro mientras alguien lo escribe")
    soltar.set()
    lector.join(timeout=2)
    hilo.join(timeout=2)
    assert time.monotonic() - inicio >= 0.15
    assert "La economia de la fabrica esta activa" in resultado["texto"]


def test_build_context_en_un_hilo_no_cuelga_el_event_loop(tmp_path, monkeypatch):
    """El lado bueno del test anterior: despachado con asyncio.to_thread
    (como hacen las 4 llamadas reales en calipso/server.py), el candado
    bloquea el HILO del pool, no el event loop: otras corrutinas siguen
    corriendo mientras tanto."""
    import calipso.server as srv

    _sembrar_economia_activa(tmp_path)
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path)
    ruta_libro = tmp_path / "economia" / "libro.jsonl"
    bloqueado = threading.Event()
    soltar = threading.Event()

    def mantener_candado():
        with candado(ruta_libro):
            bloqueado.set()
            soltar.wait(timeout=2)

    async def escenario():
        hilo = threading.Thread(target=mantener_candado)
        hilo.start()
        assert bloqueado.wait(timeout=2), "el hilo no tomo el candado a tiempo"

        latidos = 0

        async def latido():
            nonlocal latidos
            for _ in range(6):
                await asyncio.sleep(0.02)
                latidos += 1

        tarea_latido = asyncio.create_task(latido())
        tarea_contexto = asyncio.create_task(
            asyncio.to_thread(srv._build_context, "hola", "runtime", {}))
        await asyncio.sleep(0.15)
        # el candado sigue tomado: el event loop, mientras tanto, no se
        # congelo -- el latido avanzo en paralelo al hilo bloqueado
        assert latidos >= 3, "el event loop se colgo con el candado tomado"
        soltar.set()
        contexto = await tarea_contexto
        await tarea_latido
        hilo.join(timeout=2)
        return contexto

    contexto = asyncio.run(escenario())
    assert "La economia de la fabrica esta activa" in contexto
