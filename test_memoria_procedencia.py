"""La memoria con procedencia, en aislado (spec 2026-09-11, seccion 5):
`clasificar` contra el banco, `partir` y `presentar` con lo nuevo, lo viejo
(las dos variantes rotas), meta ausente, basura, sin ruta y topes; y
`presentar_recuerdos`, el corte DESPUES de presentar que usan los dos
lectores."""
from __future__ import annotations

from calipso import memoria_procedencia as mp
from experimentos import no_saber_banco as banco


# --- clasificar -------------------------------------------------------------

def test_el_banco_atrapa_los_no_saber_y_no_degrada_ningun_dato():
    """El piso del spec: 0 falsos `sin_dato` sobre respuestas con dato y
    >= 90% de los no-saber atrapados. Si un patron nuevo rompe esto, el
    rojo lista las filas."""
    r = banco.medir(mp.clasificar)
    assert r["falsos"] == 0, r["fallas"]
    assert r["recall"] >= 0.90, (r["atrapados"], r["no_saber"], r["fallas"])
    assert r["no_saber"] >= 20 and r["datos"] >= 20   # el banco no se vacio


def test_un_fuerte_degrada_solo_si_arranca_antes_de_los_250_chars():
    relleno = "Hay contenido de verdad en esta respuesta. " * 7   # 301 chars
    assert mp.clasificar("No tengo registros de eso.") == "sin_dato"
    assert mp.clasificar(relleno + "No tengo registros de eso.") == "dato"
    assert mp.clasificar("Bueno. " * 10 + "No tengo registros de eso.") == "sin_dato"


def test_los_acentos_y_las_mayusculas_no_esconden_un_patron():
    assert mp.clasificar("NO TENGO INFORMACIÓN sobre eso.") == "sin_dato"
    assert mp.clasificar("No está registrado en mi memoria.") == "sin_dato"
    assert mp.quitar_acentos("información año") == "informacion ano"


def test_un_debil_no_degrada_si_antes_hay_una_afirmativa_con_contenido():
    assert mp.clasificar("Claro, Pedro. ¿Podrías darme más detalles?") == "sin_dato"
    assert mp.clasificar(
        "El commit fue el 2026-09-09 en main. ¿Podrías darme más detalles?") == "dato"


def test_una_respuesta_que_es_solo_una_pregunta_es_sin_dato():
    assert mp.clasificar("¿A cuál idea te refieres?") == "sin_dato"
    assert mp.clasificar("Anoté el 12 de octubre. ¿Algo más?") == "dato"


def test_la_respuesta_vacia_es_sin_dato():
    assert mp.clasificar("") == "sin_dato"
    assert mp.clasificar("   \n") == "sin_dato"


def test_la_parafrasis_de_la_frase_fija_en_plural_es_un_no_saber():
    """El eco parafraseado del porton (A, presupuesto, pasada 1): el 7b vio
    'Calipso no tenia el dato entonces' y contesto en plural. Sin este
    patron ese eco se guardaba como `dato` y volvia al turno siguiente como
    'Calipso contesto (...): No teniamos el dato...' (ruling 6 del ledger:
    se suma como fuerte y se verifica 0 falsos en el banco)."""
    eco = ("No teníamos el dato del presupuesto del taller registrado en ese "
           "momento. ¿Necesitas que busque más información sobre este tema?")
    assert mp.clasificar(eco) == "sin_dato"
    assert mp.clasificar("No teníamos la información entonces.") == "sin_dato"
    assert mp.clasificar("No teníamos ningún dato de eso.") == "sin_dato"
    # la regla de posicion vale igual que para los demas fuertes
    relleno = "Hay contenido de verdad en esta respuesta. " * 7   # 301 chars
    assert mp.clasificar(relleno + "No teníamos el dato.") == "dato"
    # 'no tenemos un registro detallado' (cha-decision, banco) sigue siendo dato
    assert mp.clasificar(
        "La ultima discusion se centro en revisar los gastos. Sin embargo, no "
        "tenemos un registro detallado de esa conversacion.") == "dato"


# --- partir y limpiar_gestos ------------------------------------------------

NUEVO = "Pedro pregunto: que libro lei\nCalipso respondio: El nombre de la rosa."
VIEJO_1 = "Pedro preguntÃ³: -q\nCalipso respondiÃ³: Nada. Sigo esperando."
VIEJO_2 = "Pedro preguntÃƒÂ³: hola\nCalipso respondiÃƒÂ³: Hola Pedro."


def test_partir_lo_nuevo_y_las_dos_variantes_rotas():
    assert mp.partir(NUEVO) == ("que libro lei", "El nombre de la rosa.")
    assert mp.partir(VIEJO_1) == ("-q", "Nada. Sigo esperando.")
    assert mp.partir(VIEJO_2) == ("hola", "Hola Pedro.")


def test_partir_tolera_saltos_en_la_pregunta_y_en_la_respuesta():
    texto = "Pedro pregunto: linea 1\nlinea 2\nCalipso respondio: a\n\nb"
    assert mp.partir(texto) == ("linea 1\nlinea 2", "a\n\nb")


def test_partir_devuelve_none_para_lo_que_no_es_un_par():
    assert mp.partir("Pedro definio una meta: X\nCalipso creo Goal Mode: g1") is None
    assert mp.partir("hecho 0") is None
    assert mp.partir("") is None
    assert mp.partir("Calipso respondio: solo\nPedro pregunto: al reves") is None


def test_limpiar_gestos_saca_los_gestos_iniciales_y_solo_esos():
    assert mp.limpiar_gestos("/local hola, que libro?") == "hola, que libro?"
    assert mp.limpiar_gestos("/local /think hola") == "hola"
    assert mp.limpiar_gestos("hola /web algo") == "hola /web algo"
    assert mp.limpiar_gestos("/local") == ""
    assert mp.limpiar_gestos("/nube") == ""
    assert mp.limpiar_gestos("-q") == "-q"
    assert mp.limpiar_gestos("  hola   mundo\n") == "hola mundo"


# --- presentar --------------------------------------------------------------

META = {"ts": "2026-09-10T20:58:05", "route": "local", "kind": "chat"}


def test_presentar_un_par_con_dato_da_la_vineta_de_dos_lineas():
    assert mp.presentar(NUEVO, META, variante="A") == (
        "- Pedro dijo (2026-09-10): que libro lei\n"
        "  Calipso contesto (local, 2026-09-10): El nombre de la rosa.")


def test_presentar_un_no_saber_lo_reemplaza_por_la_frase_fija():
    texto = ("Pedro pregunto: /local quien me presto el libro rosa?\n"
             "Calipso respondio: Entiendo. No tengo registros de quien te presto un libro.")
    assert mp.presentar(texto, META, variante="A") == (
        "- Pedro dijo (2026-09-10): quien me presto el libro rosa?\n"
        "  Calipso no tenia el dato entonces (local, 2026-09-10).")
    assert "No tengo registros" not in mp.presentar(texto, META, variante="A")


def test_la_variante_b_omite_el_renglon_de_calipso_en_el_no_saber():
    texto = ("Pedro pregunto: quien me presto el libro?\n"
             "Calipso respondio: No tengo registros de eso.")
    assert mp.presentar(texto, META, variante="B") == (
        "- Pedro dijo (2026-09-10): quien me presto el libro?")
    # con dato, B es igual a A
    assert mp.presentar(NUEVO, META, variante="B") == mp.presentar(NUEVO, META, variante="A")


def test_la_variante_off_es_el_par_crudo_de_antes():
    assert mp.presentar(NUEVO, META, variante="off") == f"- {NUEVO}"
    assert mp.presentar(NUEVO, META, score=0.91, variante="off") == f"- (0.91) {NUEVO}"
    # por presentar_recuerdos: el system de main pegaba el score, el abismo no
    hit = {"text": NUEVO, "meta": META, "score": 0.91, "scope": "global"}
    assert mp.presentar_recuerdos([hit], 8, variante="off")[0]["text"] == f"- (0.91) {NUEVO}"
    assert mp.presentar_recuerdos([hit], 8, variante="off", con_score=False)[0]["text"] == f"- {NUEVO}"


def test_la_variante_activa_sale_del_entorno_y_sin_variable_es_la_default(monkeypatch):
    monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)
    assert mp.variante_activa() == mp.VARIANTE_DEFAULT == "A"
    monkeypatch.setenv("MEMORIA_PRESENTAR", "B")
    assert mp.variante_activa() == "B"
    monkeypatch.setenv("MEMORIA_PRESENTAR", "cualquiera")
    assert mp.variante_activa() == mp.VARIANTE_DEFAULT


def test_una_variante_explicita_invalida_cae_a_la_activa_del_entorno(monkeypatch):
    """`variante="C"` no es ninguna de las tres: se comporta como
    `variante_activa()` (la del entorno, o la default sin variable), no como
    B por accidente (el minor de la Task 1: cualquier letra que no fuera A ni
    off omitia el renglon de Calipso)."""
    no_saber = ("Pedro pregunto: quien me presto el libro?\n"
                "Calipso respondio: No tengo registros de eso.")
    monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)
    assert mp.presentar(no_saber, META, variante="C") == mp.presentar(no_saber, META, variante="A")
    assert "Calipso no tenia el dato entonces" in mp.presentar(no_saber, META, variante="C")
    monkeypatch.setenv("MEMORIA_PRESENTAR", "off")
    assert mp.presentar(no_saber, META, variante="") == f"- {no_saber}"
    assert mp.presentar(no_saber, META, variante="a") == f"- {no_saber}"   # la letra es exacta


def test_el_enganche_del_entorno_llega_a_presentar_sin_variante_explicita(monkeypatch):
    """Los dos lectores llaman a `presentar_recuerdos` SIN variante: lo que
    manda es MEMORIA_PRESENTAR (el porton) o la default (produccion)."""
    no_saber = ("Pedro pregunto: quien me presto el libro?\n"
                "Calipso respondio: No tengo registros de eso.")
    hit = {"text": no_saber, "meta": META, "score": 0.91, "scope": "global"}
    monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)
    assert mp.presentar(no_saber, META) == (
        "- Pedro dijo (2026-09-10): quien me presto el libro?\n"
        "  Calipso no tenia el dato entonces (local, 2026-09-10).")
    assert mp.presentar_recuerdos([hit], 8)[0]["text"] == mp.presentar(no_saber, META, variante="A")
    monkeypatch.setenv("MEMORIA_PRESENTAR", "B")
    assert mp.presentar(no_saber, META) == "- Pedro dijo (2026-09-10): quien me presto el libro?"
    assert mp.presentar_recuerdos([hit], 8)[0]["text"] == mp.presentar(no_saber, META, variante="B")
    monkeypatch.setenv("MEMORIA_PRESENTAR", "off")
    assert mp.presentar(no_saber, META) == f"- {no_saber}"
    assert mp.presentar_recuerdos([hit], 8)[0]["text"] == f"- (0.91) {no_saber}"
    assert mp.presentar_recuerdos([hit], 8, con_score=False)[0]["text"] == f"- {no_saber}"


def test_la_ruta_usada_manda_sobre_la_decidida_y_sin_ninguna_es_interrogante():
    meta = {"ts": "2026-09-11T10:00:00", "route": "api", "ruta": "local"}
    assert "Calipso contesto (local, 2026-09-11)" in mp.presentar(NUEVO, meta, variante="A")
    assert "Calipso contesto (api, 2026-09-11)" in mp.presentar(
        NUEVO, {"ts": "2026-09-11T10:00:00", "route": "api"}, variante="A")
    assert "Calipso contesto (?, 2026-09-11)" in mp.presentar(
        NUEVO, {"ts": "2026-09-11T10:00:00"}, variante="A")


def test_meta_ausente_o_none_da_fecha_y_ruta_interrogante():
    assert mp.presentar(NUEVO, None, variante="A") == (
        "- Pedro dijo (?): que libro lei\n"
        "  Calipso contesto (?, ?): El nombre de la rosa.")
    assert mp.presentar(NUEVO, {}, variante="A") == mp.presentar(NUEVO, None, variante="A")


def test_lo_viejo_se_presenta_igual_que_lo_nuevo_y_sin_el_gesto():
    viejo = ("Pedro pregunto: /local hola, que libro te conte que empece?\n"
             "Calipso respondio: Estare encantado. Actualmente no tengo ese dato en mi memoria.")
    assert mp.presentar(viejo, META, variante="A") == (
        "- Pedro dijo (2026-09-10): hola, que libro te conte que empece?\n"
        "  Calipso no tenia el dato entonces (local, 2026-09-10).")
    assert mp.presentar(VIEJO_2, META, variante="A") == (
        "- Pedro dijo (2026-09-10): hola\n"
        "  Calipso contesto (local, 2026-09-10): Hola Pedro.")


def test_el_gesto_sin_texto_es_la_unica_basura_y_da_vacio():
    solo_gesto = "Pedro pregunto: /local\nCalipso respondio: Hola, en que te ayudo?"
    assert mp.presentar(solo_gesto, META, variante="A") == ""
    assert mp.presentar(solo_gesto, META, variante="B") == ""
    # "-q" no es basura: se presenta como lo que es
    assert mp.presentar(VIEJO_1, META, variante="A").startswith("- Pedro dijo (2026-09-10): -q")


def test_el_texto_vacio_da_vacio_en_las_tres_variantes():
    """Main saltaba los hits sin texto (`if item.get("text")` en
    prompt_compiler); `presentar` los devuelve vacios en A, B y tambien en
    off (antes off daba '- ' y A '- Registro (episodio, ?): '), y
    `presentar_recuerdos` los salta como a la basura."""
    for variante in ("A", "B", "off"):
        assert mp.presentar("", META, variante=variante) == ""
        assert mp.presentar("  \n ", None, variante=variante) == ""
        assert mp.presentar("", META, score=0.9, variante=variante) == ""
    hits = [{"text": "", "score": 0.9, "scope": "global"},
            {"text": "hecho 0", "score": 0.8, "scope": "global"}]
    assert [h["score"] for h in mp.presentar_recuerdos(hits, 8, variante="A")] == [0.8]
    assert [h["score"] for h in mp.presentar_recuerdos(hits, 8, variante="off")] == [0.8]


def test_lo_que_no_parsea_lleva_registro_con_kind_y_fecha():
    meta = {"ts": "2026-08-14T09:00:00", "route": "goal", "kind": "goal"}
    texto = "Pedro definio una meta: terminar el lector\nCalipso creo Goal Mode: g-1"
    assert mp.presentar(texto, meta, variante="A") == (
        "- Registro (goal, 2026-08-14): Pedro definio una meta: terminar el lector "
        "Calipso creo Goal Mode: g-1")
    assert mp.presentar("hecho 0", None, variante="A") == "- Registro (episodio, ?): hecho 0"
    assert mp.presentar("hecho 0", {"score": 1}, variante="A") == "- Registro (episodio, ?): hecho 0"


def test_los_topes_recortan_cada_tramo_con_puntos_suspensivos():
    pregunta = "p" * 300
    respuesta = "r" * 5000
    texto = f"Pedro pregunto: {pregunta}\nCalipso respondio: {respuesta}"
    salida = mp.presentar(texto, META, variante="A")
    l1, l2 = salida.split("\n")
    assert l1 == "- Pedro dijo (2026-09-10): " + "p" * 200 + "..."
    assert l2 == "  Calipso contesto (local, 2026-09-10): " + "r" * 400 + "..."
    corto = mp.presentar(texto, META, tope_pregunta=10, tope_respuesta=20, variante="A")
    assert "p" * 10 + "..." in corto and "r" * 20 + "..." in corto
    assert mp.presentar("x" * 900, None, variante="A") == "- Registro (episodio, ?): " + "x" * 400 + "..."


def test_los_saltos_de_linea_se_colapsan_para_que_la_vineta_sea_de_dos_lineas():
    texto = ("Pedro pregunto: dame el detalle\nCalipso respondio: Entendido.\n\n"
             "1. **Objetivo:** un mapa.\n2. **Backend:** una API.")
    salida = mp.presentar(texto, META, variante="A")
    assert salida.count("\n") == 1
    assert "Entendido. 1. **Objetivo:** un mapa. 2. **Backend:** una API." in salida


# --- presentar_recuerdos: presentar ANTES del corte --------------------------

def _hit(texto, score, meta=META):
    return {"text": texto, "meta": meta, "score": score, "scope": "global"}


def test_presentar_recuerdos_salta_los_vacios_antes_de_cortar():
    basura = "Pedro pregunto: /local\nCalipso respondio: hola"
    hits = [_hit(basura, 0.9), _hit(basura, 0.8)] + [
        _hit(f"Pedro pregunto: q{i}\nCalipso respondio: r{i}", round(0.7 - i * 0.01, 2))
        for i in range(6)]
    salida = mp.presentar_recuerdos(hits, 4, variante="A")
    assert len(salida) == 4
    assert [h["score"] for h in salida] == [0.7, 0.69, 0.68, 0.67]
    assert all(h["text"].startswith("- Pedro dijo (2026-09-10): q") for h in salida)
    assert salida[0]["scope"] == "global" and salida[0]["meta"] is META


def test_presentar_recuerdos_tolera_hits_sin_meta_y_conserva_el_texto():
    hits = [{"text": "hecho 0", "score": 0.9, "scope": "global"}]
    salida = mp.presentar_recuerdos(hits, 8, variante="A")
    assert salida == [{"text": "- Registro (episodio, ?): hecho 0", "score": 0.9, "scope": "global"}]
    assert mp.presentar_recuerdos([], 8) == []


def test_presentar_recuerdos_con_tope_cero_o_negativo_devuelve_vacio():
    """RECALL_MAX / RECALL_TOP en 0 significa 'ningun recuerdo', no uno
    (el minor de la Task 1: el corte iba despues del append)."""
    hits = [_hit(f"Pedro pregunto: q{i}\nCalipso respondio: r{i}", 0.9) for i in range(3)]
    assert mp.presentar_recuerdos(hits, 0, variante="A") == []
    assert mp.presentar_recuerdos(hits, -1, variante="A") == []
    assert mp.presentar_recuerdos(hits, 0, variante="off") == []
    assert len(mp.presentar_recuerdos(hits, 1, variante="A")) == 1
