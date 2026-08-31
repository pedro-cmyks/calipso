# test_economia_pagador.py
"""Tests del pagador: el adaptador entre dispatch y la economia."""
import json
import pytest

from calipso.economia import capacidad as cap
from calipso.economia import departamentos as deps
from calipso.economia import pagador as pag
from calipso.economia import pt
from calipso.economia import tipos as t
from calipso.economia.libro import Libro
from calipso.economia.kernel import Kernel

TS = "2026-08-25T10:00:00"
W = "2026-W35"


@pytest.fixture
def base(tmp_path):
    eco = tmp_path / "economia"
    eco.mkdir()
    k = Kernel(Libro(eco / "libro.jsonl"))
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("mercadeo", deps.ZONA_FABRICA,
                             techo_api_ciclo_mm=500_000))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    (eco / "suscripciones.json").write_text(json.dumps({
        "claude_max": {"nombre": "claude_max", "costo_mensual_mm": 100_000,
                       "capacidad_ciclo": 1_000, "reserva_personal": 200,
                       "costo_api_mm_por_unidad": 500}}), encoding="utf-8")
    pt.emitir_semana(k, TS, W, 4_000, 0)
    k.acunar(TS, W, "dep:mercadeo", 100_000, t.SubtipoAcunacion.CAPITAL,
             {"tipo": "firma_pedro"})
    return tmp_path


def test_desde_entorno_inactivo_sin_archivos(tmp_path):
    assert pag.Pagador.desde_entorno(tmp_path) is None


def test_cargar_api_por_tokens(base):
    p = pag.Pagador.desde_entorno(base)
    mm = p.cargar_api(TS, W, "dep:mercadeo", "deepseek-chat",
                      prompt_tokens=100_000, completion_tokens=50_000)
    assert mm == 82  # ceil((100k*270 + 50k*1100) / 1M)
    assert p.leer_kernel().saldo("dep:mercadeo") == 100_000 - 82


def test_cero_tokens_no_genera_cargo(base):
    p = pag.Pagador.desde_entorno(base)
    assert p.cargar_api(TS, W, "dep:mercadeo", "deepseek-chat", 0, 0) == 0
    assert p.pendientes() == []
    assert p.leer_kernel().saldo("dep:mercadeo") == 100_000


def test_cargar_api_de_trabajo_resuelve_dueno(base):
    from calipso.economia import bus as bus_mod
    b = bus_mod.Bus(base / "economia" / "bus.jsonl")
    b.alta(TS, W, "p1", "dep:mercadeo", "radar", 10_000, 20_000,
           {"gasto_max_mm": 50_000})
    Kernel(Libro(base / "economia" / "libro.jsonl")).transferir(
        TS, W, "dep:mercadeo", "trabajo:p1", 1_000, motivo="financiacion")
    p = pag.Pagador.desde_entorno(base)
    p.cargar_api(TS, W, "trabajo:p1", "deepseek-chat", 1_000_000, 0)  # 270 mm
    assert p.pendientes() == []
    assert p.leer_kernel().saldo("trabajo:p1") == 1_000 - 270


def test_cuenta_personal_no_carga_api(base):
    p = pag.Pagador.desde_entorno(base)
    assert p.cargar_api(TS, W, "personal", "deepseek-chat", 1000, 1000) is None
    assert p.leer_kernel().saldo("dep:mercadeo") == 100_000


def test_cargar_suscripcion_no_mueve_monedas_y_descuenta_cristal(base):
    """Costo hundido: la unidad de suscripcion sale de una cuota que Pedro
    ya pago, no de la billetera del departamento contra direccion. Antes
    este cargo transferia 100 mm (el precio por escasez) a direccion; el
    cristal REEMPLAZA a esa transferencia, no la acompaña."""
    p = pag.Pagador.desde_entorno(base)
    p.cargar_suscripcion(TS, W, "dep:mercadeo", "claude_max")
    k = p.leer_kernel()
    assert p.pendientes() == []
    assert k.saldo(t.DIRECCION) == 0
    assert k.saldo("dep:mercadeo") == 100_000
    asientos = k.libro.asientos()
    # y sin embargo la unidad quedo contada: el guardia de cuota, el brief
    # y la eficiencia leen esto
    assert cap.consumo_fabrica(asientos, "claude_max", [W]) == 1
    # el pool arranca en cero (nadie emitio el ciclo en este fixture), asi
    # que la unidad queda en descubierto — declarado legal, y visible
    assert k.saldo(t.cuenta_cristal("claude_max", "fabrica"),
                   t.Divisa.CRISTAL) == -1
    consumo = [a for a in asientos
               if a.tipo is t.TipoAsiento.CONSUMO_CRISTAL][0]
    # el departamento va como `titular`: con la clave `departamento`, el
    # cierre semanal lo daria por nacido y lo declararia en quiebra por
    # tener cero MONEDAS (ver cristal.consumir)
    assert consumo.detalle["titular"] == "dep:mercadeo"
    assert "departamento" not in consumo.detalle
    p.cargar_suscripcion(TS, W, "personal", "claude_max")
    asientos = p.leer_kernel().libro.asientos()
    assert cap.consumo_personal(asientos, "claude_max", [W]) == 1


def test_una_semana_sin_abrir_ya_no_aparca_el_consumo(base):
    """El consumo de capacidad no espera al boton de abrir la semana.

    Una semana se vuelve operativa recien cuando Pedro la abre a mano, o
    sea que todo lunes empieza fuera de las operativas. La COMPRA podia
    esperar ahi; un consumo no: el modelo ya contesto y la suscripcion ya
    se gasto, y aparcarlo dejaba el libro anotando cero sobre capacidad
    realmente servida."""
    p = pag.Pagador.desde_entorno(base)
    p.cargar_suscripcion(TS, "2026-W99", "dep:mercadeo", "claude_max")
    assert p.pendientes() == []
    asientos = p.leer_kernel().libro.asientos()
    assert cap.consumo_fabrica(asientos, "claude_max", ["2026-W99"]) == 1


def test_la_cuota_del_ciclo_sigue_frenando_a_la_fabrica(base):
    """`cristal.consumir` NUNCA rechaza —mide un hecho consumado— asi que
    el unico freno de cuota que existe es el del mercado. Sin el, la
    fabrica consumiria sin tope y la unica senal seria el descubierto del
    pool, que hoy no lee nadie."""
    p = pag.Pagador.desde_entorno(base)
    p.cargar_suscripcion(TS, W, "dep:mercadeo", "claude_max", unidades=800)
    assert p.pendientes() == []  # 800 = capacidad_fabrica (1.000 - 200)
    p.cargar_suscripcion(TS, W, "dep:mercadeo", "claude_max")
    assert len(p.pendientes()) == 1
    asientos = p.leer_kernel().libro.asientos()
    assert cap.consumo_fabrica(asientos, "claude_max", [W]) == 800


def test_la_cuota_frena_tambien_en_una_semana_sin_abrir(base):
    """El guardia mide por CICLO ESTAMPADO, no por semana.

    Una semana se vuelve operativa recien cuando Pedro aprieta el boton de
    abrir, o sea que todo lunes empieza afuera de las operativas — y desde
    que consumir dejo de esperar ese boton, el consumo se escribe igual.
    Plegando el consumido por SEMANA, el guardia leia cero justo en la
    ventana que el cristal vino a habilitar: la fabrica consumia sin tope y
    el descubierto del pool era la unica senal, que no lee nadie."""
    p = pag.Pagador.desde_entorno(base)
    p.cargar_suscripcion(TS, "2026-W99", "dep:mercadeo", "claude_max",
                         unidades=800)
    assert p.pendientes() == []      # 800 = capacidad_fabrica (1.000 - 200)
    # la unidad 801 del MISMO ciclo rebota, con su semana todavia cerrada
    p.cargar_suscripcion(TS, "2026-W99", "dep:mercadeo", "claude_max")
    assert len(p.pendientes()) == 1
    asientos = p.leer_kernel().libro.asientos()
    # el pliegue por semana no lo ve, y es exactamente lo que el guardia no
    # podia mirar: por eso la cuota tiene su propio pliegue
    assert cap.consumo_fabrica(asientos, "claude_max", [W]) == 0
    assert cap.consumo_fabrica_ciclo(asientos, "claude_max", 0, [W]) == 800


def test_la_cuota_cuenta_las_semanas_salteadas_del_ciclo(base):
    """Y no se resetea porque Pedro no abrio una semana. Con el pliegue por
    semana, lo consumido en una semana que nunca se abre no cae en ningun
    ciclo: la cuota volvia a estar entera cada vez que el calendario pasaba
    por una semana sin abrir."""
    p = pag.Pagador.desde_entorno(base)
    p.cargar_suscripcion(TS, "2026-W98", "dep:mercadeo", "claude_max",
                         unidades=500)
    p.cargar_suscripcion(TS, "2026-W99", "dep:mercadeo", "claude_max",
                         unidades=300)
    assert p.pendientes() == []
    p.cargar_suscripcion(TS, W, "dep:mercadeo", "claude_max")  # semana abierta
    assert len(p.pendientes()) == 1   # 800 + 1 > 800, aunque sean 3 semanas


def test_fallo_economico_degrada_a_pendiente(base):
    p = pag.Pagador.desde_entorno(base)
    # un congelado no gasta (politica del mercado, no del cristal): el
    # cargo no puede aplicarse -> pendiente. Antes este test usaba una
    # semana no operativa, que ya no falla: el consumo de capacidad no
    # necesita que la semana este abierta.
    k = Kernel(Libro(base / "economia" / "libro.jsonl"))
    deps.declarar_quiebra(k, TS, W, "dep:mercadeo")
    p.cargar_suscripcion(TS, W, "dep:mercadeo", "claude_max")
    assert len(p.pendientes()) == 1
    asientos = p.leer_kernel().libro.asientos()
    assert cap.consumo_fabrica(asientos, "claude_max", [W]) == 0
    # el reintento re-aplica el cargo original, y el departamento sigue
    # congelado: queda pendiente
    assert p.reintentar_pendientes() == 0
    assert len(p.pendientes()) == 1


def test_reintento_aplica_cuando_puede(base):
    p = pag.Pagador.desde_entorno(base)
    # techo agotado -> pendiente; al reintentar con techo ampliado, pasa
    registro = deps.Registro(base / "economia" / "departamentos.json")
    registro.ajustar("mercadeo", techo_api_ciclo_mm=10)
    p.cargar_api(TS, W, "dep:mercadeo", "deepseek-chat", 100_000, 50_000)
    assert len(p.pendientes()) == 1
    registro.ajustar("mercadeo", techo_api_ciclo_mm=500_000)
    assert p.reintentar_pendientes() == 1  # el mercado fresco ve el ajuste
    assert p.pendientes() == []
    assert p.leer_kernel().saldo("dep:mercadeo") == 100_000 - 82


def test_el_cliente_se_traduce_a_la_suscripcion_que_existe():
    """dispatch.py tenia esta traduccion copiada a mano; dos verdades para
    un solo dato es como se desincronizan."""
    from calipso.economia.pagador import suscripcion_de_cliente
    assert suscripcion_de_cliente("claude") == "claude_max"
    assert suscripcion_de_cliente("codex") == "chatgpt_plus"
    assert suscripcion_de_cliente("CLAUDE") == "claude_max"
    assert suscripcion_de_cliente(None) == "claude_max"
