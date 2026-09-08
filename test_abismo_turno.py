"""El estado del turno y las piezas puras de la reentrada (spec seccion 4)."""
import pytest

from calipso.abismo import marca, turno


def test_el_estado_arranca_vacio_y_el_reset_lo_deja_igual():
    e = turno.EstadoTurno()
    assert (e.consultas, e.bloques, e.tramos, e.tramos_crudos, e.sintetica, e.apagada) == (0, [], [], [], False, False)
    e.consultas, e.sintetica, e.apagada = 2, True, True
    e.bloques.append("b"); e.tramos.append("t"); e.tramos_crudos.append("c")
    e.reset()
    assert e == turno.EstadoTurno()


def test_puede_cortar_bajo_el_tope_y_encendida():
    e = turno.EstadoTurno()
    assert e.puede_cortar() is True
    e.consultas = turno.ABISMO_CONSULTAS_MAX
    assert e.puede_cortar() is False
    e.consultas, e.apagada = 0, True
    assert e.puede_cortar() is False


def test_el_prompt_de_reentrada_lleva_bloques_mensaje_y_venias_diciendo():
    system, usuario = turno.prompt_reentrada(
        "SISTEMA", ["=== bloque uno ===", "=== bloque dos ==="],
        ["Dejame ver ", "que dije "], "que libro lei")
    assert system == "SISTEMA\n\n=== bloque uno ===\n\n=== bloque dos ==="
    assert usuario.startswith("que libro lei\n\n")
    assert "Venias diciendo: Dejame ver que dije \n" in usuario
    assert usuario.endswith(turno.INSTRUCCION_CONTINUAR)


def test_sin_bloques_el_system_no_cambia():
    system, _ = turno.prompt_reentrada("SISTEMA", [], ["a"], "m")
    assert system == "SISTEMA"


def test_la_senal_lleva_los_campos_fijos_de_cada_fase():
    assert turno.senal("pondering", "chats") == {
        "type": "abismo", "fase": "pondering", "fuente": "chats",
        "verbo": "buscando en tus chats"}
    assert turno.senal("pescado", "memoria", tamano=120) == {
        "type": "abismo", "fase": "pescado", "fuente": "memoria",
        "tamano": 120, "viaje": {"destino": "local"}}
    v = {"destino": "nube", "tapados": [{"marcador": "[ID_1]", "tipo": "identidad"}], "texto_tapado": "x"}
    assert turno.senal("pescado", "chats", tamano=1, viaje=v)["viaje"] == v
    assert turno.senal("fallo", "proyecto", motivo="solo_hondo")["motivo"] == "solo_hondo"
    # un motivo fuera de la lista cerrada se normaliza a "error"
    assert turno.senal("fallo", "proyecto", motivo="lo que sea")["motivo"] == "error"
    assert turno.senal("fallo", "proyecto")["motivo"] == "error"
    with pytest.raises(ValueError):
        turno.senal("bailando", "chats")


def test_el_motivo_de_la_consulta():
    assert turno.motivo_de_consulta({"estado": "fallo", "aviso": "la consulta no trajo nada"}) == "vacio"
    assert turno.motivo_de_consulta({"estado": "fallo", "aviso": "chats.json roto"}) == "error"


def test_cortar_en_marca_corta_en_la_primera_valida():
    texto = "Dejame ver ⟦abismo:zzz nada⟧ y ⟦abismo:chats libro⟧ esto vino sin contexto"
    tramo, m = turno.cortar_en_marca(texto)
    assert tramo == "Dejame ver ⟦abismo:zzz nada⟧ y "   # la ilegible queda: el Emisor la retira
    assert m == marca.Marca("chats", "libro")
    assert turno.cortar_en_marca("sin marcas") == ("sin marcas", None)
    assert turno.cortar_en_marca("") == ("", None)


def test_prefijo_congelado_y_retirar_marcas():
    assert turno.prefijo_congelado("hola ⟦abismo:chats x⟧ resto") == "hola "
    assert turno.prefijo_congelado("hola ⟦abismo:zzz x⟧ resto") is None
    assert turno.retirar_marcas("a ⟦abismo:chats x⟧ b ⟦abismo:zzz⟧ c") == "a  b  c"


def test_recortar_abierta_saca_la_marca_a_medio_llegar_del_final():
    """Entre dos tics del preview el parcial puede terminar en una marca
    que abrio y no cerro: Pedro no la lee cruda (spec seccion 4)."""
    assert turno.recortar_abierta("Dejame ver ⟦abismo:chats lib") == "Dejame ver "
    assert turno.recortar_abierta("Dejame ver ⟦abismo:") == "Dejame ver "
    assert turno.recortar_abierta("hola ⟦abismo:chats x⟧ resto") == "hola ⟦abismo:chats x⟧ resto"
    assert turno.recortar_abierta("") == ""
