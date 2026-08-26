"""Tests del sesgo, el prompt y el parseo (spec secciones 4.2 y 5)."""
from calipso.plantel import decision as dec


def test_capacidad_barata_empuja_a_explorar():
    """Es el punto de todo el arreglo del precio: la capacidad que esta por
    evaporarse hace racional explorar."""
    # perilla en 30, unidad al 40% de la lista -> +30
    assert dec.sesgo_efectivo(30, precio_mm=40, precio_base_mm=100) == 60


def test_capacidad_cara_empuja_a_terminar_lo_empezado():
    assert dec.sesgo_efectivo(30, precio_mm=160, precio_base_mm=100) == 0
    assert dec.sesgo_efectivo(80, precio_mm=160, precio_base_mm=100) == 50


def test_al_precio_de_lista_la_perilla_manda_sola():
    assert dec.sesgo_efectivo(30, precio_mm=100, precio_base_mm=100) == 30


def test_el_sesgo_queda_entre_0_y_100():
    assert dec.sesgo_efectivo(95, precio_mm=1, precio_base_mm=100) == 100
    assert dec.sesgo_efectivo(5, precio_mm=900, precio_base_mm=100) == 0


def test_sin_capacidad_la_perilla_pasa_tal_cual():
    """Un departamento personal no compra capacidad de fabrica: su perilla
    no se modula por un precio que no paga."""
    assert dec.sesgo_efectivo(30, precio_mm=0, precio_base_mm=0) == 30


def test_parsear_las_cuatro_acciones():
    assert dec.parsear("nada\nno hay plata")[:2] == ("nada", None)
    assert dec.parsear("proponer\nhay hueco en precios")[:2] == ("proponer", None)
    assert dec.parsear("trabajar p1\nva quedando corto")[:2] == ("trabajar", "p1")
    assert dec.parsear("comentar p2\nel criterio es flojo")[:2] == ("comentar", "p2")


def test_el_motivo_sale_de_la_segunda_linea():
    accion, ref, motivo = dec.parsear("trabajar p1\nel radar ya tiene datos")
    assert (accion, ref) == ("trabajar", "p1")
    assert motivo == "el radar ya tiene datos"


def test_lo_que_no_se_entiende_es_nada():
    """Un modelo que alucina no puede gastar."""
    for basura in ("", "   ", "bailar", "{}", "Claro! Con gusto te ayudo:",
                   "trabajar", "comentar"):
        accion, ref, _ = dec.parsear(basura)
        assert accion == "nada", f"{basura!r} no cayo en nada"
        assert ref is None


def test_tolera_mayusculas_y_dos_puntos():
    """El modelo chico formatea como quiere; lo que importa es la accion."""
    assert dec.parsear("Trabajar: p1\nmotivo")[:2] == ("trabajar", "p1")
    assert dec.parsear("NADA")[0] == "nada"


def test_la_prosa_cae_en_nada():
    """Un modelo que escribe una oracion completa en vez del comando cae en nada."""
    accion, ref, _ = dec.parsear("Trabajar en el radar seria una buena idea\nporque hace falta")
    assert accion == "nada"
    assert ref is None
    accion, ref, _ = dec.parsear("Comentar esto es innecesario, mejor dejarlo\nmotivo")
    assert accion == "nada"
    assert ref is None


def test_proponer_devuelve_ref_none():
    """Proponer no recibe un id: solo ofrece una idea nueva."""
    accion, ref, motivo = dec.parsear("proponer\nhiay hueco en precios")
    assert accion == "proponer"
    assert ref is None
    accion, ref, _ = dec.parsear("proponer p3\nmotivo")
    assert accion == "proponer"
    assert ref is None


def test_el_prompt_lleva_los_numeros_que_hacen_falta():
    s = {"nombre": "atlas", "disponible_mm": 400_000, "saldo_mm": 400_000,
         "presupuesto_semanal_mm": 25_000, "salidas_semana_mm": 7_000,
         "compuertas_pendientes": 2,
         "trabajos": [{"id": "p1", "titulo": "radar", "gastado_mm": 1_000,
                       "presupuesto_mm": 10_000}],
         "propuestas_ajenas": [{"id": "p2", "titulo": "encuesta",
                                "dueno": "dep:mercado"}],
         "capacidad": {"nombre": "claude_max", "precio_mm": 50,
                       "precio_base_mm": 100}}
    p = dec.prompt(s, 60)
    for dato in ("atlas", "400000", "25000", "7000", "p1", "radar", "p2",
                 "claude_max", "50"):
        assert dato in p, f"al prompt le falta {dato}"
    assert "explorar" in p
    # y ofrece exactamente las cuatro acciones
    for accion in dec.ACCIONES:
        assert accion in p


def test_el_prompt_lleva_lo_que_el_departamento_aprendio():
    """Sin esto la memoria del departamento seria de solo escritura: el jefe
    guarda cada decision y no vuelve a leer ninguna."""
    s = {"nombre": "atlas", "disponible_mm": 0, "saldo_mm": 0,
         "presupuesto_semanal_mm": 0, "salidas_semana_mm": 0,
         "compuertas_pendientes": 0, "trabajos": [], "propuestas_ajenas": [],
         "capacidad": None}
    assert "el radar de precios no rindio" in dec.prompt(
        s, 50, nucleo="# atlas\nel radar de precios no rindio")
    assert "Lo que aprendiste" not in dec.prompt(s, 50, nucleo="   ")


def test_el_prompt_sin_trabajos_ni_propuestas_no_miente():
    s = {"nombre": "atlas", "disponible_mm": 0, "saldo_mm": 0,
         "presupuesto_semanal_mm": 0, "salidas_semana_mm": 0,
         "compuertas_pendientes": 0, "trabajos": [], "propuestas_ajenas": [],
         "capacidad": None}
    p = dec.prompt(s, 50)
    assert "ninguno" in p and "ninguna" in p
    assert "sin capacidad" in p
