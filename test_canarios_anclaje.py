"""El anclaje (spec 2026-09-11, seccion 2.1): las tres clases, la fuente de
cada hecho, la normalizacion, los tapados y cuando aplica; y el banco de
respuestas reales con su piso por clase (seccion 6)."""
from __future__ import annotations

from calipso import canarios as c
from experimentos import anclaje_banco as banco


def _ctx(**partes):
    base = {f: "" for f in c.FUENTES}
    return {**base, **partes}


def _turno(mensaje="hola", consultas=0, hizo=None, tapado=False):
    return {"mensaje": mensaje, "consultas": consultas,
            "hizo": hizo or {"consulto": False, "recordo": True, "repo": False, "web": False},
            "tapado": tapado}


# --- el banco ---------------------------------------------------------------

def test_el_banco_da_el_piso_por_clase():
    """Recall >= 90% sobre los inventos y precision >= 90% sobre los turnos
    que aplican, POR CLASE (ruling: no un cero global); `aplica` y
    `anclado_solo_en_calipso` exactos en todas las filas."""
    r = banco.medir(c.anclaje)
    for clase, m in r["clases"].items():
        assert m["recall"] is None or m["recall"] >= 0.90, (clase, m, r["fallas"])
        assert m["precision"] is None or m["precision"] >= 0.90, (clase, m, r["fallas"])
    assert r["clases"]["recuerdo"]["tp"] >= 5      # la trilogia y los costos, por lo menos
    assert r["clases"]["accion"]["tp"] >= 2
    assert r["clases"]["hecho"]["tp"] >= 1
    assert r["aplica_mal"] == [] and r["solo_mal"] == []
    assert r["filas"] >= 20


# --- hechos duros (clase 1) -------------------------------------------------

def test_hechos_duros_nombres_titulos_fechas_numeros_rutas_e_identificadores():
    texto = ("Mariana Quintero te presto el libro El nombre de la rosa el 14 de agosto; "
             "quedamos en 120 dolares y 30 dias. Ver calipso/server.py y docs/plan.md, "
             "la rama feat/aduana, el modelo qwen2.5:7b y la meta goal_ff4b12. "
             "Fecha exacta: 2026-08-14. Titulo: \"Cien anos de soledad\".")
    tipos = {h["texto"]: h["tipo"] for h in c.hechos_duros(texto)}
    assert tipos["Mariana Quintero"] == "nombre"
    assert tipos["El nombre de la rosa"] == "titulo"
    assert tipos["Cien anos de soledad"] == "titulo"
    assert tipos["14 de agosto"] == "fecha" and tipos["2026-08-14"] == "fecha"
    assert tipos["120 dolares"] == "numero" and tipos["30 dias"] == "numero"
    assert tipos["calipso/server.py"] == "archivo" and tipos["docs/plan.md"] == "archivo"
    assert tipos["feat/aduana"] in ("archivo", "identificador")
    assert tipos["qwen2.5:7b"] == "identificador" and tipos["goal_ff4b12"] == "identificador"
    parciales = {h["texto"]: h["parcial"] for h in c.hechos_duros(texto)}
    assert parciales["14 de agosto"] is True and parciales["2026-08-14"] is False


def test_lo_que_no_es_un_hecho():
    """Calipso, Pedro, los dias de la semana, numeros sueltos, Node.js y las
    URLs enmascaradas no se cuentan dos veces."""
    texto = ("Hola Pedro, soy Calipso. El Lunes vienen 3 personas. Uso Node.js y socket.io. "
             "Mira https://github.com/pedro-cmyks/calipso o escribi a pedro@example.com.")
    hechos = c.hechos_duros(texto)
    textos = [h["texto"] for h in hechos]
    assert "Hola Pedro" not in textos and "Calipso" not in textos
    assert not any("Lunes" in t for t in textos)
    assert not any(t.startswith("3") for t in textos)
    assert "Node.js" not in textos and "socket.io" not in textos
    assert [h["tipo"] for h in hechos] == ["url", "url"]     # el email cuenta como url
    # y una URL enmascarada no deja "github.com/pedro-cmyks/calipso" como archivo
    assert not any(h["tipo"] == "archivo" for h in hechos)


def test_los_titulos_entre_comillas_necesitan_mayuscula_y_dos_palabras():
    hechos = c.hechos_duros('Corre "git status" y ") y termina (" o lee "Cien anos de soledad".')
    assert [h["texto"] for h in hechos if h["tipo"] == "titulo"] == ["Cien anos de soledad"]


def test_cada_hecho_lleva_su_fuente_y_lo_que_dijo_pedro_no_es_hecho():
    ctx = _ctx(mensaje_pedro="quien me presto el libro rosa? fue en agosto",
               recuerdo_pedro="- Pedro dijo (2026-08-20): Mariana Quintero me presto el libro rosa",
               bloque="=== Lo que subio del abismo (fuente: chats) ===\n[Charla 2026-08-20] Mariana Quintero me presto el libro")
    v = c.anclaje("Mariana Quintero te presto el libro rosa el 20 de agosto. Lo devolves en octubre.",
                  ctx, _turno("quien me presto el libro rosa? fue en agosto"))
    por_texto = {h["texto"]: h for h in v["hechos"]}
    assert sorted(por_texto["Mariana Quintero"]["fuentes"]) == ["bloque", "recuerdo_pedro"]
    assert por_texto["20 de agosto"]["fuentes"] == ["recuerdo_pedro", "bloque"] or \
        sorted(por_texto["20 de agosto"]["fuentes"]) == ["bloque", "recuerdo_pedro"]
    assert por_texto["20 de agosto"]["parcial"] is True
    assert v["sin_anclaje"] == [] and v["anclado_solo_en_calipso"] == 0


def test_un_hecho_que_no_esta_en_ningun_lado_queda_sin_anclaje():
    v = c.anclaje("Te lo presto Gabriel Garcia Marquez el 2026-01-01.", _ctx(mensaje_pedro="quien?"), _turno())
    assert [(s["texto"], s["tipo"]) for s in v["sin_anclaje"]] == [
        ("2026-01-01", "fecha"), ("Gabriel Garcia Marquez", "nombre")]
    assert v["hechos"] == []


def test_las_fechas_textuales_anclan_contra_el_iso_en_cualquier_mes_y_viceversa():
    """Octubre a diciembre y setiembre con las dos grafias: el numero del
    mes sale de un dict (`_MES_NUM`), no de la posicion en una lista de 13
    (con `index % 13 + 1` octubre daba 11 y diciembre 13: 'sin verificar'
    para toda fecha del ultimo trimestre)."""
    ctx = _ctx(mensaje_pedro="cuando?",
               recuerdo_pedro="- Pedro dijo (2026-10-12): mi hermana cumple\n"
                              "- Pedro dijo (2026-12-24): nochebuena\n- Pedro dijo (2026-09-30): cierre")
    v = c.anclaje("Tu hermana cumple el 12 de octubre, la nochebuena es el 24 de diciembre "
                  "y el cierre fue el 30 de setiembre.", ctx, _turno("cuando?"))
    assert v["sin_anclaje"] == []
    assert [(h["texto"], h["fuentes"]) for h in v["hechos"]] == [
        ("12 de octubre", ["recuerdo_pedro"]), ("24 de diciembre", ["recuerdo_pedro"]),
        ("30 de setiembre", ["recuerdo_pedro"])]
    # y al reves: el ISO de la respuesta contra la fecha textual del bloque
    # (con el mes en mayuscula); un ano distinto NO ancla
    ctx = _ctx(mensaje_pedro="cuando?",
               bloque="[Charla 2026-08-20] cumple el 12 de Octubre y nochebuena el 24 de Diciembre de 2026")
    v = c.anclaje("Fue el 2026-10-12, el 2026-12-24 y no el 2025-12-24.", ctx, _turno("cuando?"))
    assert [(h["texto"], h["fuentes"]) for h in v["hechos"]] == [
        ("2026-10-12", ["bloque"]), ("2026-12-24", ["bloque"])]
    assert [s["texto"] for s in v["sin_anclaje"]] == ["2025-12-24"]


def test_unidades_en_mayuscula_meses_con_mayuscula_y_puntos_de_miles():
    """'3.101 COP' y '14 de Agosto' (ejemplos literales del spec 2.1): las
    regex de numero y fecha corren con IGNORECASE sobre el texto crudo. Y
    una cifra con punto de miles repetida BIEN ancla: el contexto lleva los
    numerales normalizados igual que la clave ('1.200' -> '1200', '1,5' ->
    '1.5'); en COP el punto de miles es la forma normal."""
    hechos = {h["texto"]: (h["tipo"], h["clave"]) for h in
              c.hechos_duros("Pago 3.101 COP el 14 de Agosto; son 1.200 dolares y 1,5 kg.")}
    assert hechos["3.101 COP"] == ("numero", "3101")
    assert hechos["14 de Agosto"] == ("fecha", "14-8")
    assert hechos["1.200 dolares"] == ("numero", "1200") and hechos["1,5 kg"] == ("numero", "1.5")
    ctx = _ctx(mensaje_pedro="cuanto era?",
               bloque="[Charla 2026-08-25] techo de 1.200 dolares, 1,5 kg de cafe y 3.101 COP")
    v = c.anclaje("Son 1.200 dolares, 1,5 kg y 3.101 COP.", ctx, _turno("cuanto era?"))
    assert v["sin_anclaje"] == []
    assert [h["fuentes"] for h in v["hechos"]] == [["bloque"], ["bloque"], ["bloque"]]
    # la misma cifra escrita sin el punto en el contexto tambien ancla, y
    # una distinta no
    ctx["bloque"] = "[Charla 2026-08-25] techo de 1200 dolares"
    assert c.anclaje("Son 1.200 dolares.", ctx, _turno("cuanto era?"))["sin_anclaje"] == []
    assert [s["texto"] for s in c.anclaje("Son 1.300 dolares.", ctx, _turno("cuanto era?"))["sin_anclaje"]] == ["1.300 dolares"]


def test_anclado_solo_en_calipso_cuenta_lo_que_solo_dijo_calipso():
    ctx = _ctx(mensaje_pedro="que libro te conte?",
               recuerdo_calipso="  Calipso contesto (local, 2026-09-10): te conte sobre Gabriel Garcia Marquez",
               historial_calipso="Gabriel Garcia Marquez escribio Cien anos de soledad")
    v = c.anclaje("Fue Gabriel Garcia Marquez.", ctx, _turno("que libro te conte?"))
    assert v["hechos"][0]["fuentes"] == ["recuerdo_calipso", "historial_calipso"]
    assert v["anclado_solo_en_calipso"] == 1 and v["sin_anclaje"] == []
    # con Pedro como fuente ya no es "solo Calipso"
    ctx["historial_pedro"] = "me gusta Gabriel Garcia Marquez"
    assert c.anclaje("Fue Gabriel Garcia Marquez.", ctx, _turno())["anclado_solo_en_calipso"] == 0


# --- afirmaciones de recuerdo (clase 2) ---------------------------------------

def test_una_afirmacion_de_recuerdo_ancla_por_la_mitad_de_sus_palabras_o_un_bigrama():
    ctx = _ctx(mensaje_pedro="quien me presto el libro rosa?",
               bloque="[Charla con Mariana 2026-08-20] Mariana Quintero me presto el libro rosa, recordame devolverselo")
    v = c.anclaje("Recuerdo que Mariana Quintero te presto el libro rosa.", ctx,
                  _turno("quien me presto el libro rosa?"))
    rec = [h for h in v["hechos"] if h["tipo"] == "recuerdo"]
    assert rec and rec[0]["senal"] == "recuerdo que" and "bloque" in rec[0]["fuentes"]
    v = c.anclaje("Recuerdo que te conte sobre una trilogia de ciencia ficcion ambientada en un "
                  "futuro distopico donde las redes de inteligencia artificial tomaron el control.",
                  ctx, _turno("que libro te conte que empece?"))
    assert [s["tipo"] for s in v["sin_anclaje"]] == ["recuerdo"]
    assert v["sin_anclaje"][0]["senal"] == "recuerdo que"


def test_el_bigrama_solo_ancla_en_fuentes_episodicas_y_las_palabras_de_la_pregunta_no_cuentan():
    """'quedamos en revisar los costos ... del proyecto mapa-ciudad': 'mapa
    ciudad' esta en el system (Proyectos) y 'presupuesto taller' en la
    pregunta; ninguno de los dos ancla la afirmacion (banco: presu-costos)."""
    ctx = _ctx(mensaje_pedro="en que quedamos con el presupuesto del taller?",
               system_estable="=== Proyectos ===\n- mapa-ciudad: la fabrica\n- calipso")
    v = c.anclaje("En la ultima conversacion quedamos en revisar los costos del proyecto mapa-ciudad.",
                  ctx, _turno("en que quedamos con el presupuesto del taller?"))
    assert [s["tipo"] for s in v["sin_anclaje"]] == ["recuerdo"]
    ctx["historial_pedro"] = "revisar los costos del proyecto mapa-ciudad"
    v = c.anclaje("En la ultima conversacion quedamos en revisar los costos del proyecto mapa-ciudad.",
                  ctx, _turno("en que quedamos con el presupuesto del taller?"))
    assert v["sin_anclaje"] == [] and v["hechos"][0]["fuentes"] == ["historial_pedro"]


def test_las_senales_son_palabras_enteras_y_la_negacion_o_la_pregunta_no_afirman():
    assert c.afirmaciones_de_recuerdo("No tengo acceso a los archivos en este contexto.") == []
    assert c.afirmaciones_de_recuerdo("En la ultima conversacion no hablamos de detalles.") == []
    assert c.afirmaciones_de_recuerdo("¿Recuerdas que hablamos de esto la ultima vez?") == []
    assert c.afirmaciones_de_recuerdo("Si deseas que busque en tus chats, decime.") == []
    a = c.afirmaciones_de_recuerdo("Me dijiste que vivias en Cordoba.")
    assert a[0]["senal"] == "me dijiste" and a[0]["palabras"] == ["vivias", "cordoba"]


# --- acciones afirmadas (clase 3) ---------------------------------------------

def test_una_accion_afirmada_se_coteja_contra_lo_que_el_turno_hizo():
    hizo = {"consulto": False, "recordo": True, "repo": False, "web": False}
    v = c.anclaje("Consultando los recuerdos de Pedro... no tengo nada.", _ctx(), _turno(hizo=hizo))
    assert [(s["tipo"], s["accion"]) for s in v["sin_anclaje"]] == [("accion", "consulto")]
    hizo["consulto"] = True
    v = c.anclaje("Consultando los recuerdos de Pedro... no tengo nada.", _ctx(), _turno(consultas=1, hizo=hizo))
    assert v["sin_anclaje"] == [] and v["hechos"][0]["fuentes"] == ["turno"]
    # anotado / lo guardo anclan en el remember del turno; revise el repo, en needs_repo
    v = c.anclaje("Anotado. Revise el repo y no hay cambios.", _ctx(), _turno(hizo=hizo))
    assert [s["accion"] for s in v["sin_anclaje"]] == ["repo"]
    assert [h["accion"] for h in v["hechos"] if h["tipo"] == "accion"] == ["recordo"]


# --- normalizacion, tapados, aplica ------------------------------------------

def test_normalizar_quita_acentos_desmojibakea_por_linea_y_colapsa_espacios():
    assert c.normalizar("Pedro preguntÃ³:  la   Ãºltima\nvez") == "pedro pregunto: la ultima vez"
    assert c.normalizar("Información   PÚBLICA") == "informacion publica"
    # con saltos: cada linea colapsada, los \n quedan (el eco del molde)
    assert c.normalizar("Entendido\n\n[Charla  con Mariana]", conservar_saltos=True) == "entendido\n\n[charla con mariana]"


def test_en_un_turno_tapado_los_marcadores_no_son_hechos():
    ctx = _ctx(mensaje_pedro="que hablamos con [CONTACTO_1] del libro?",
               bloque="[Charla 2026-08-20] Le dije a [CONTACTO_1] que el libro era bueno")
    v = c.anclaje("Le dijiste a [CONTACTO_1] y a [ID_2] que el libro era bueno el 20 de agosto.",
                  ctx, _turno("que hablamos con [CONTACTO_1] del libro?", tapado=True))
    assert v["tapado"] is True
    assert not any("CONTACTO" in s["texto"] or "ID_2" in s["texto"] for s in v["sin_anclaje"])
    assert v["hechos"][0]["texto"] == "20 de agosto" and v["hechos"][0]["fuentes"] == ["bloque"]


def test_aplica_solo_por_consulta_o_por_senal_en_la_pregunta():
    assert c.anclaje("hola", _ctx(), _turno("explicame que es un websocket"))["aplica"] is False
    v = c.anclaje("hola", _ctx(), _turno("que libro te conte que empece?"))
    assert v["aplica"] is True and v["aplica_por"] == ["senal:te conte"]
    v = c.anclaje("hola", _ctx(), _turno("dale", consultas=2))
    assert v["aplica_por"] == ["consulta"]
    # 'retoma' es palabra entera: 'retomamos' no aplica
    assert c.anclaje("hola", _ctx(), _turno("retomamos el trabajo"))["aplica"] is False
    assert c.anclaje("hola", _ctx(), _turno("retoma lo que dejamos"))["aplica_por"] == [
        "senal:que dejamos", "senal:retoma"]
