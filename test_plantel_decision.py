"""Tests del sesgo, el prompt y el parseo (spec secciones 4.2 y 5)."""
from calipso.plantel import decision as dec
from calipso.plantel import ficha


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


def test_un_superindice_no_es_un_monto():
    """`'²'.isdigit()` es True y `int('²')` revienta con ValueError: los
    superindices son Numeric_Type=Digit sin ser decimales. La promesa de
    este parser es que lo que no se entiende es NADA; con `isdigit`, un
    `pedir ²` salia por el `except` de `tic` y se anotaba como "reviento
    actuando" en la memoria del jefe."""
    assert dec.parsear("pedir ²\nmotivo") == ("nada", None, "motivo")
    # el digito arabe SI es decimal y `int()` lo lee: sigue pasando
    assert dec.parsear("pedir ٥\nmotivo") == ("pedir", "٥", "motivo")


def _situacion_minima() -> dict:
    """Lo minimo que `prompt` indexa con corchetes. Las claves que lee con
    `.get()` -propuestas_propias, descartadas_semana, catalogo- se omiten a
    proposito: asi los tests que no hablan de ellas ejercitan el camino de
    una situacion que no las trae."""
    return {"nombre": "atlas", "disponible_mm": 400_000, "saldo_mm": 400_000,
            "presupuesto_semanal_mm": 25_000, "salidas_semana_mm": 7_000,
            "compuertas_pendientes": 2, "trabajos": [],
            "propuestas_ajenas": [], "capacidad": None}


def test_el_prompt_pide_la_ficha_con_sus_cuatro_renglones():
    p = dec.prompt(_situacion_minima(), 50)
    for campo in ("sobre:", "promete:", "tarda:", "porque:"):
        assert campo in p, campo


def test_el_prompt_nombra_las_seis_promesas_y_los_cuatro_plazos():
    p = dec.prompt(_situacion_minima(), 50)
    for palabra in ficha.PROMESAS:
        assert palabra in p, palabra
    for plazo in ficha.PLAZOS:
        assert plazo in p, plazo


def test_una_propuesta_con_forma_se_muestra_como_ficha():
    s = _situacion_minima()
    s["propuestas_propias"] = [{
        "id": "p4", "titulo": "lo viejo", "presupuesto_mm": 0,
        "forma": {"sobre": "el banco del lector", "clave": "banco+lector",
                  "promete": "construir", "tarda": "medio"}}]
    p = dec.prompt(s, 50)
    assert "construir: el banco del lector (medio)" in p
    assert "lo viejo" not in p


def test_una_propuesta_sin_forma_muestra_su_titulo():
    """Compatibilidad: no se le inventa una ficha a partir del titulo.
    Seria adivinar, y un objeto adivinado entraria al catalogo como si el
    departamento lo hubiera nombrado."""
    s = _situacion_minima()
    s["propuestas_propias"] = [{"id": "p4", "titulo": "algo viejo",
                                "presupuesto_mm": 0, "forma": None}]
    assert "algo viejo" in dec.prompt(s, 50)


def test_el_catalogo_aparece_cuando_hay_objetos():
    s = _situacion_minima()
    s["catalogo"] = ["el radar de precios"]
    p = dec.prompt(s, 50)
    assert "el radar de precios" in p


def test_sin_objetos_el_bloque_del_catalogo_no_aparece():
    """Un encabezado sobre una lista vacia le ensena al modelo que ese
    bloque no dice nada."""
    s = _situacion_minima()
    s["catalogo"] = []
    assert "que ya nombraste" not in dec.prompt(s, 50)


def test_los_trabajos_siguen_mostrando_su_titulo():
    """Un trabajo vivo ya no es una propuesta esperando: su identidad no
    esta en disputa, asi que no cambia de render."""
    s = _situacion_minima()
    s["trabajos"] = [{"id": "p1", "titulo": "radar de precios",
                      "gastado_mm": 1000, "presupuesto_mm": 10_000,
                      "forma": {"sobre": "x", "clave": "x",
                                "promete": "medir", "tarda": "corto"}}]
    assert "radar de precios" in dec.prompt(s, 50)


def test_solo_los_proyectos_de_esa_cuenta():
    proyectos = [
        {"nombre": "lector", "departamento": "dep:taller", "linea": "el banco"},
        {"nombre": "atlas", "departamento": "dep:research", "linea": "feeds"},
        {"nombre": "suelto", "departamento": None, "linea": "x"},
    ]
    salida = dec.proyectos_de(proyectos, "dep:taller")
    assert [p["nombre"] for p in salida] == ["lector"]


def test_el_filtro_compara_la_cuenta_COMPLETA():
    """El jefe despierta como `dep:taller` y el catastro guarda lo que se le
    haya escrito. Si el filtro comparara el nombre desnudo contra la cuenta,
    o al reves, el resultado seria la lista vacia SIN QUE NADA FALLE: la
    asignacion se ve bien en el disco y el prompt sale sin proyectos."""
    assert dec.proyectos_de(
        [{"nombre": "lector", "departamento": "taller"}], "dep:taller") == []
    assert dec.proyectos_de(
        [{"nombre": "lector", "departamento": "dep:taller"}], "taller") == []


def test_la_linea_de_pedro_gana_al_readme():
    p = [{"nombre": "lector", "departamento": "dep:taller",
          "linea": "lo que escribio Pedro", "resumen": "lo del README"}]
    salida = dec.proyectos_de(p, "dep:taller")[0]
    assert salida["texto"] == "lo que escribio Pedro"
    assert salida["fuente"] == "pedro"


def test_sin_linea_cae_al_readme_y_lo_dice():
    p = [{"nombre": "lector", "departamento": "dep:taller",
          "linea": "", "resumen": "lo del README"}]
    salida = dec.proyectos_de(p, "dep:taller")[0]
    assert salida["texto"] == "lo del README"
    assert salida["fuente"] == "readme"


def test_sin_nada_lo_dice_en_vez_de_inventar():
    p = [{"nombre": "lector", "departamento": "dep:taller"}]
    salida = dec.proyectos_de(p, "dep:taller")[0]
    assert salida["texto"] == ""
    assert salida["fuente"] == "ninguna"


def test_una_linea_de_puros_espacios_no_es_una_linea():
    p = [{"nombre": "lector", "departamento": "dep:taller",
          "linea": "   ", "resumen": "lo del README"}]
    assert dec.proyectos_de(p, "dep:taller")[0]["fuente"] == "readme"


def test_sin_proyectos_devuelve_lista_vacia_y_no_revienta():
    assert dec.proyectos_de([], "dep:taller") == []
    assert dec.proyectos_de(None, "dep:taller") == []


def test_la_carta_sale_como_su_propio_bloque():
    p = dec.prompt(_situacion_minima(), 50,
                   carta={"estado": "escrita", "texto": "I+D para Pedro."})
    assert "Este departamento:" in p
    assert "I+D para Pedro." in p


def test_la_carta_NO_sale_bajo_lo_que_aprendiste_antes():
    """El invariante de procedencia. Si la carta viajara por el nucleo, el
    prompt le diria al modelo que una instruccion de Pedro es algo que el
    departamento concluyo solo."""
    p = dec.prompt(_situacion_minima(), 50, nucleo="lo que aprendi solo",
                   carta={"estado": "escrita", "texto": "LA CARTA"})
    cabeza = p.split("Lo que aprendiste antes:")[1].split("\n\n")[0]
    assert "LA CARTA" not in cabeza


def test_sin_carta_el_bloque_lo_dice_en_vez_de_desaparecer():
    """Hoy el bloque del nucleo se esfuma cuando esta vacio, asi que "nadie
    escribio" y "escribio nada" se leen igual y el jefe no puede notar que le
    falta algo."""
    p = dec.prompt(_situacion_minima(), 50,
                   carta={"estado": "ausente", "texto": ""})
    assert "Este departamento:" in p
    assert "no tiene carta" in p


def test_una_carta_vacia_no_se_lee_igual_que_una_ausente():
    ausente = dec.prompt(_situacion_minima(), 50,
                         carta={"estado": "ausente", "texto": ""})
    vacia = dec.prompt(_situacion_minima(), 50,
                       carta={"estado": "vacia", "texto": ""})
    assert ausente != vacia


def test_los_proyectos_salen_con_su_procedencia():
    p = dec.prompt(_situacion_minima(), 50, proyectos=[
        {"nombre": "lector", "texto": "el banco", "fuente": "pedro"},
        {"nombre": "atlas", "texto": "feeds", "fuente": "readme"}])
    assert "Proyectos a tu cargo:" in p
    assert "lector" in p and "el banco" in p
    assert "(de Pedro)" in p and "(del README)" in p


def test_sin_proyectos_el_bloque_lo_dice():
    p = dec.prompt(_situacion_minima(), 50, proyectos=[])
    assert "Proyectos a tu cargo:" in p
    assert "ninguno asignado" in p


def test_un_proyecto_sin_texto_lo_dice_y_no_miente():
    p = dec.prompt(_situacion_minima(), 50, proyectos=[
        {"nombre": "suelto", "texto": "", "fuente": "ninguna"}])
    assert "suelto" in p


def test_los_bloques_nuevos_no_traen_las_palabras_prohibidas():
    """Dos tests que ya existen afirman que `trabajar` y `comentar` no
    aparecen cuando el menu no las ofrece. Cualquier texto nuevo que las
    contenga los rompe aunque el menu este perfecto."""
    p = dec.prompt(_situacion_minima(), 50,
                   carta={"estado": "ausente", "texto": ""}, proyectos=[])
    assert "trabajar" not in p and "comentar" not in p


def test_sin_los_parametros_nuevos_el_prompt_sigue_saliendo():
    """Los doce tests viejos del prompt llaman sin carta y sin proyectos.
    Los defaults tienen que dejarlos pasar."""
    assert dec.prompt(_situacion_minima(), 50)
