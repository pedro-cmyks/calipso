"""Los adaptadores que convierten cada bandeja en items del inbox.

El inbox no sabe nada de ninguna bandeja: cada origen se traduce a si mismo.
Estos tests son el contrato de esa traduccion.
"""
from calipso.economia import bus as eco_bus


def test_la_mesa_se_declara_sin_vara_todavia():
    """El PvP es el plan 2. Hoy el descriptor lo dice explicitamente en vez
    de inventar una vara que no tiene con que comparar: `retorno_mm` es una
    copia de `presupuesto_mm` para los dos tipos de propuesta."""
    d = eco_bus.descriptor()
    assert d["origen"] == "mesa"
    assert d["vara"] is None
    assert {v["nombre"] for v in d["verbos"]} == {"financiar", "descartar"}


def test_financiar_declara_que_lleva_parametro():
    """Financiar no es un si: es un si-con-cuenta-pagadora. El inbox tiene
    que saberlo para no dibujar un boton que miente."""
    d = eco_bus.descriptor()
    financiar = next(v for v in d["verbos"] if v["nombre"] == "financiar")
    assert "cuenta" in financiar["parametros"]


def test_sin_economia_sembrada_no_hay_items_y_no_revienta():
    """El estado de HOY: el endpoint devuelve {"activa": false} y NADA mas.
    Ni `propuestas` ni `vencidas`."""
    assert eco_bus.como_items({"activa": False}) == []


def test_una_propuesta_se_vuelve_un_item():
    datos = {"activa": True, "propuestas": [
        {"id": "a-1a2b3c4d", "estado": "alta", "departamento": "dep:a",
         "tipo": "trabajo", "titulo": "escribir el landing",
         "presupuesto_mm": 50000, "retorno_mm": 50000,
         "criterio": {"gasto_max_mm": 50000}, "gastado_mm": 0, "aportes": {}}],
        "vencidas": []}
    items = eco_bus.como_items(datos)
    assert len(items) == 1
    it = items[0]
    assert it["id"] == "a-1a2b3c4d"
    assert it["origen"] == "mesa"
    assert it["clase"] == "decision"
    assert it["titulo"] == "escribir el landing"
    assert it["cuerpo"]["presupuesto_mm"] == 50000
    assert it["estado"] == "alta"


def test_una_vencida_tambien_es_item_pero_solo_admite_descartar():
    """Cinco campos, no diez. Un render unico para las dos leeria undefined."""
    datos = {"activa": True, "propuestas": [], "vencidas": [
        {"id": "a-9f9f9f9f", "departamento": "dep:a", "titulo": "ronda",
         "semana": "2026-W35", "presupuesto_mm": 100000}]}
    items = eco_bus.como_items(datos)
    assert len(items) == 1
    assert items[0]["estado"] == "vencida"
    assert items[0]["cuerpo"]["verbos_validos"] == ["descartar"]


def test_un_preseed_paga_el_tesoro_y_no_ofrece_eleccion():
    """`bus.financiar` rechaza cualquier billetera que no sea el tesoro para
    un pre-seed. Un selector ahi seria un menu donde todo falla."""
    datos = {"activa": True, "vencidas": [], "propuestas": [
        {"id": "a-1", "estado": "alta", "departamento": "dep:a",
         "tipo": "preseed", "titulo": "ronda", "presupuesto_mm": 100000,
         "retorno_mm": 100000, "criterio": {}, "gastado_mm": 0,
         "aportes": {}}]}
    assert eco_bus.como_items(datos)[0]["cuerpo"]["cuenta_fija"] == "tesoro"


def test_una_propuesta_financiada_no_ofrece_descartar():
    """`_TRANSICIONES["financiada"]` es {"muerta","cerrada"}: descartar una
    financiada es transicion invalida y el endpoint da 400. Financiar SI
    sigue valido -- es como se acumulan los aportes."""
    datos = {"activa": True, "vencidas": [], "propuestas": [
        {"id": "a-2", "estado": "financiada", "departamento": "dep:a",
         "tipo": "trabajo", "titulo": "ya financiada", "presupuesto_mm": 50000,
         "retorno_mm": 50000, "criterio": {}, "gastado_mm": 10000,
         "aportes": {"dep:b": 50000}}]}
    it = eco_bus.como_items(datos)[0]
    assert it["cuerpo"]["verbos_validos"] == ["financiar"]


from calipso.permisos import motor as permisos_motor


def test_permisos_no_ofrece_despues_ni_vence():
    """Un 'despues' sobre un permiso no aplaza: prolonga un bloqueo global.
    Y permisos no vence: grep de venc|caduc|expir en el paquete da cero."""
    d = permisos_motor.descriptor()
    assert d["origen"] == "permisos"
    assert d["reloj"] is None
    assert "despues" not in {v["nombre"] for v in d["verbos"]}
    assert {v["nombre"] for v in d["verbos"]} == {"si", "si_siempre", "no"}


def test_solo_lo_abierto_es_item():
    """`aprobadas` y `registro` no son items pendientes. Contarlos miente."""
    datos_endpoint = {"activo": True,
                      "pendientes": [{"id": "sol_a", "ts": "2026-08-31T11:00:00",
                                      "estado": "pendiente", "texto": "acunar 500000 mm",
                                      "siempre_pregunta": False, "accion": {},
                                      "contexto": {}, "motivo": "supera el techo"}],
                      "estacionadas": [], "aprobadas": [{"id": "sol_vieja"}],
                      "registro": [{"id": "sol_x"}], "concedidos": [], "error": None}
    items = permisos_motor.como_items(datos_endpoint)
    assert [i["id"] for i in items] == ["sol_a"]
    assert items[0]["origen"] == "permisos"
    assert items[0]["clase"] == "decision"


def test_siempre_pregunta_no_ofrece_el_verbo_siempre():
    """`si_siempre` sobre una solicitud con siempre_pregunta da 400. El
    inbox no puede dibujar un verbo que el origen no declaro."""
    datos_endpoint = {"activo": True, "estacionadas": [], "aprobadas": [],
                      "registro": [], "concedidos": [], "error": None,
                      "pendientes": [{"id": "sol_b", "ts": "", "estado": "pendiente",
                                      "texto": "acunar", "siempre_pregunta": True,
                                      "accion": {}, "contexto": {}, "motivo": ""}]}
    it = permisos_motor.como_items(datos_endpoint)[0]
    assert it["cuerpo"]["verbos_validos"] == ["si", "no"]


def test_vacio_por_error_no_se_confunde_con_vacio_de_verdad():
    """El endpoint devuelve `error` con las listas vacias cuando el archivo
    no se puede leer. Un badge en cero ahi es el badge mintiendo."""
    datos_endpoint = {"activo": True, "pendientes": [], "estacionadas": [],
                      "aprobadas": [], "registro": [], "concedidos": [],
                      "error": "solicitudes.json ilegible"}
    items = permisos_motor.como_items(datos_endpoint)
    assert len(items) == 1
    assert items[0]["clase"] == "aviso"
    assert items[0]["estado"] == "error"
    assert "ilegible" in items[0]["titulo"]


def test_permisos_inactivo_no_da_items():
    assert permisos_motor.como_items({"activo": False}) == []


from calipso import librarian


def test_la_biblioteca_deja_editar_antes_de_aceptar():
    """La respuesta no es si/no: es 'si, pero asi'."""
    d = librarian.descriptor()
    assert d["origen"] == "biblioteca"
    assert d["reloj"] is None
    aceptar = next(v for v in d["verbos"] if v["nombre"] == "aceptar")
    assert "texto" in aceptar["parametros"]


def test_el_proyecto_es_obligatorio():
    """`_slug(None)` devuelve 'global' y lee un archivo distinto y vacio:
    pedir sin proyecto no falla, MIENTE. Aca falla."""
    import pytest
    with pytest.raises(ValueError):
        librarian.como_items({"proposals": []}, proyecto="")


def test_el_item_dice_de_que_proyecto_es():
    """Es la unica de las cuatro que no es global. Se dice, no se aplana."""
    datos = {"proposals": [{"id": "mem_abc123", "text": "Pedro prefiere pytest",
                            "status": "pending", "ts": "2026-08-31T10:00:00",
                            "scope": "global", "target": "pedro-perfil.md"}],
             "events": [{"id": "mem_x"}]}
    items = librarian.como_items(datos, proyecto="calipso")
    assert len(items) == 1
    assert items[0]["origen"] == "biblioteca"
    assert "calipso" in items[0]["titulo"]
    assert items[0]["cuerpo"]["texto"] == "Pedro prefiere pytest"


def test_los_events_no_son_items():
    """/api/memory/inbox devuelve tambien los ultimos 50 eventos del jsonl.
    No son cosas que esperen a Pedro."""
    datos = {"proposals": [], "events": [{"id": "a"}, {"id": "b"}]}
    assert librarian.como_items(datos, proyecto="calipso") == []


def test_una_propuesta_ya_resuelta_no_ofrece_verbos():
    """El store solo acciona sobre `pending` (librarian.py:158) y fija
    "accepted"/"discarded" al accionar. El endpoint filtra pending solo POR
    DEFECTO, asi que una resuelta puede llegar: no puede ofrecer verbos que
    el backend ya rechaza."""
    datos = {"proposals": [{"id": "mem_x", "text": "algo", "status": "accepted",
                            "ts": "2026-08-31T10:00:00", "scope": "global",
                            "target": "pedro-perfil.md"}], "events": []}
    it = librarian.como_items(datos, proyecto="calipso")[0]
    assert it["cuerpo"]["verbos_validos"] == []


from calipso.economia import cola as eco_cola


def test_las_cartas_no_vencen_y_sus_dos_verbos_no_son_simetricos():
    """Estan exceptuadas a mano de expirar_semana. Y `rechazar` funciona
    sobre una carta pero NO alimenta cartas_atendidas(), asi que no desarma
    el breaker: los dos verbos no hacen lo mismo al reves."""
    d = eco_cola.descriptor()
    assert d["origen"] == "cartas"
    assert d["reloj"] is None
    assert {v["nombre"] for v in d["verbos"]} == {"atender", "rechazar"}


def test_una_compuerta_no_es_una_carta():
    """`pendientes` mezcla las dos. Sin filtrar, el inbox ofrece 'atender'
    sobre una compuerta y eso da 500."""
    datos = {"activa": True, "pendientes": [
        {"id": "c1", "departamento": "dep:a", "titulo": "llamar",
         "tipo": "contacto", "obligatoria": True, "mpt_estimado": 500},
        {"id": "renovacion:claude_max:0", "es_carta": True,
         "carta": {"tipo": "renovacion", "suscripcion": "claude_max"},
         "carril": "normal", "monedas_en_juego": 0}]}
    items = eco_cola.como_items(datos)
    assert [i["id"] for i in items] == ["renovacion:claude_max:0"]


def test_el_titulo_de_una_carta_se_deriva_de_su_tipo():
    """Una carta no trae `titulo`: no tiene esa clave. Hay que armarlo."""
    datos = {"activa": True, "pendientes": [
        {"id": "cierre_departamento:dep:a:2026-W35", "es_carta": True,
         "carta": {"tipo": "cierre_departamento", "departamento": "dep:a"}}]}
    it = eco_cola.como_items(datos)[0]
    assert it["titulo"]
    assert "dep:a" in it["titulo"]


def test_el_id_de_una_carta_lleva_dos_puntos():
    """Por eso el item lleva `origen` y no se rutea por el prefijo del id,
    como decia el spec."""
    datos = {"activa": True, "pendientes": [
        {"id": "mandato:dep:a:2026-W35", "es_carta": True,
         "carta": {"tipo": "mandato", "departamento": "dep:a"}}]}
    it = eco_cola.como_items(datos)[0]
    assert ":" in it["id"]
    assert it["origen"] == "cartas"


def test_sin_economia_sembrada_no_hay_cartas():
    assert eco_cola.como_items({"activa": False}) == []
