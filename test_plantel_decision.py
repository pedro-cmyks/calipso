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


def test_parsear_las_cinco_acciones():
    assert dec.parsear("nada\nno hay plata")[:2] == ("nada", None)
    assert dec.parsear("proponer\nhay hueco en precios")[:2] == ("proponer", None)
    assert dec.parsear("trabajar p1\nva quedando corto")[:2] == ("trabajar", "p1")
    assert dec.parsear("comentar p2\nel criterio es flojo")[:2] == ("comentar", "p2")
    assert dec.parsear("pedir 20000\nnecesito arrancar")[:2] == ("pedir", "20000")


def test_pedir_exige_un_monto_entero_positivo():
    """La ronda pre-seed: el jefe declara cuanto pide, y el parser sigue
    siendo estricto con la forma -sin numero, o con algo que no es un
    entero positivo, no hay pedido."""
    for basura in ("pedir\nnecesito plata", "pedir mucho\nnecesito plata",
                   "pedir -5\nnecesito plata", "pedir 0\nnecesito plata",
                   "pedir 5.5\nnecesito plata"):
        accion, ref, _ = dec.parsear(basura)
        assert accion == "nada", f"{basura!r} no cayo en nada"
        assert ref is None
    assert dec.parsear("pedir 1\narranco chico")[:2] == ("pedir", "1")


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
    for dato in ("atlas", "400000", "25000", "7000", "p1", "radar", "p2"):
        assert dato in p, f"al prompt le falta {dato}"
    assert "Capacidad de computo: 50 mm por unidad de claude_max (lista 100)." in p
    assert "explorar" in p
    # y ofrece exactamente las cinco acciones
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


def test_el_prompt_no_ofrece_trabajar_sin_trabajos_vivos():
    """El modelo elige `trabajar` en buena medida porque esta en el menu:
    ofrecerlo sin trabajos vivos invita a inventar un id -se lo vio pasar
    con qwen2.5:3b, razonando sobre proponer y emitiendo trabajar 1 con la
    lista vacia. `nada`, `proponer` y `pedir` van siempre."""
    s = {"nombre": "atlas", "disponible_mm": 0, "saldo_mm": 0,
         "presupuesto_semanal_mm": 0, "salidas_semana_mm": 0,
         "compuertas_pendientes": 0, "trabajos": [], "propuestas_ajenas": [],
         "capacidad": None}
    p = dec.prompt(s, 50)
    assert "trabajar" not in p
    assert "nada" in p and "proponer" in p and "pedir" in p


def test_el_prompt_ofrece_pedir_este_o_no_quebrado():
    """La ronda pre-seed no depende de que el departamento este quebrado:
    quien decide si hace falta pedir es Pedro desde la mesa, no este
    prompt -asi que `pedir <monto>` va en el menu siempre, con billetera
    llena o vacia."""
    s = {"nombre": "atlas", "disponible_mm": 400_000, "saldo_mm": 400_000,
         "presupuesto_semanal_mm": 25_000, "salidas_semana_mm": 0,
         "compuertas_pendientes": 0, "trabajos": [], "propuestas_ajenas": [],
         "capacidad": None}
    p = dec.prompt(s, 50)
    assert "pedir <monto>" in p


def test_el_prompt_ofrece_trabajar_con_trabajos_vivos():
    s = {"nombre": "atlas", "disponible_mm": 0, "saldo_mm": 0,
         "presupuesto_semanal_mm": 0, "salidas_semana_mm": 0,
         "compuertas_pendientes": 0,
         "trabajos": [{"id": "p1", "titulo": "radar", "gastado_mm": 0,
                       "presupuesto_mm": 1_000}],
         "propuestas_ajenas": [], "capacidad": None}
    p = dec.prompt(s, 50)
    assert "trabajar <id>" in p
    # tener un trabajo vivo tambien da algo sobre lo que comentar
    assert "comentar <id>" in p


def test_el_prompt_no_ofrece_comentar_sin_nada_que_comentar():
    s = {"nombre": "atlas", "disponible_mm": 0, "saldo_mm": 0,
         "presupuesto_semanal_mm": 0, "salidas_semana_mm": 0,
         "compuertas_pendientes": 0, "trabajos": [], "propuestas_ajenas": [],
         "capacidad": None}
    p = dec.prompt(s, 50)
    assert "comentar" not in p
    assert "nada" in p and "proponer" in p


def test_el_prompt_ofrece_comentar_con_propuestas_ajenas():
    s = {"nombre": "atlas", "disponible_mm": 0, "saldo_mm": 0,
         "presupuesto_semanal_mm": 0, "salidas_semana_mm": 0,
         "compuertas_pendientes": 0, "trabajos": [],
         "propuestas_ajenas": [{"id": "p2", "titulo": "encuesta",
                                "dueno": "dep:mercado"}],
         "capacidad": None}
    p = dec.prompt(s, 50)
    assert "comentar <id>" in p
    # sin trabajos vivos, trabajar sigue afuera
    assert "trabajar" not in p


def test_el_prompt_ofrece_comentar_con_propuestas_propias():
    """`propuestas_propias` se lee con `.get` (algunas situaciones no la
    traen); tiene que disparar el menu de `comentar` igual que las otras
    dos fuentes."""
    s = {"nombre": "atlas", "disponible_mm": 0, "saldo_mm": 0,
         "presupuesto_semanal_mm": 0, "salidas_semana_mm": 0,
         "compuertas_pendientes": 0, "trabajos": [], "propuestas_ajenas": [],
         "propuestas_propias": [{"id": "p3", "titulo": "algo"}],
         "capacidad": None}
    p = dec.prompt(s, 50)
    assert "comentar <id>" in p


def test_el_prompt_sin_trabajos_ni_propuestas_no_miente():
    s = {"nombre": "atlas", "disponible_mm": 0, "saldo_mm": 0,
         "presupuesto_semanal_mm": 0, "salidas_semana_mm": 0,
         "compuertas_pendientes": 0, "trabajos": [], "propuestas_ajenas": [],
         "capacidad": None}
    p = dec.prompt(s, 50)
    assert "ninguno" in p and "ninguna" in p
    assert "sin capacidad" in p

def test_el_prompt_lleva_las_decisiones_recientes():
    """Sin esto el jefe le pregunta al modelo desde cero en cada tic, y un
    modelo sin memoria de lo que ya decidio propone lo mismo una y otra
    vez."""
    s = {"nombre": "atlas", "disponible_mm": 0, "saldo_mm": 0,
         "presupuesto_semanal_mm": 0, "salidas_semana_mm": 0,
         "compuertas_pendientes": 0, "trabajos": [], "propuestas_ajenas": [],
         "capacidad": None}
    p = dec.prompt(s, 50, recientes=["proponer: radar de precios",
                                     "nada: nada nuevo que ofrecer"])
    assert "radar de precios" in p
    assert "nada nuevo que ofrecer" in p
    assert "no repitas lo mismo" in p


def test_el_prompt_sin_recientes_no_lleva_el_bloque():
    s = {"nombre": "atlas", "disponible_mm": 0, "saldo_mm": 0,
         "presupuesto_semanal_mm": 0, "salidas_semana_mm": 0,
         "compuertas_pendientes": 0, "trabajos": [], "propuestas_ajenas": [],
         "capacidad": None}
    p = dec.prompt(s, 50)
    assert "ultimos tics" not in p


def test_el_prompt_prohibe_otros_idiomas():
    """El 7b mezcla chino en el motivo -el titulo que Pedro lee en el bus.
    Medido: una prohibicion pegada a la instruccion de formato lo saca, una
    cabecera al principio del prompt no."""
    s = {"nombre": "atlas", "disponible_mm": 0, "saldo_mm": 0,
         "presupuesto_semanal_mm": 0, "salidas_semana_mm": 0,
         "compuertas_pendientes": 0, "trabajos": [], "propuestas_ajenas": [],
         "capacidad": None}
    p = dec.prompt(s, 50)
    assert "castellano" in p
    assert "chino" in p
