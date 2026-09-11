"""El estado del turno y las piezas puras de la reentrada (spec seccion 4)."""
import pathlib

import pytest

from calipso import prompt_compiler
from calipso.abismo import anillos, consulta, fuentes, marca, turno, viaje
from calipso.privacidad import juez
from calipso.privacidad.redaccion import MapaMarcadores


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
    """Los bloques entran como secciones (titulo pelado de su `=== ===`) y
    el render es byte a byte el append de antes."""
    secciones, usuario = turno.prompt_reentrada(
        [("Sistema", "SISTEMA")],
        ["=== bloque uno ===\n[anillo 1]\nuno", "=== bloque dos ===\n[anillo 2]\ndos"],
        ["Dejame ver ", "que dije "], "que libro lei")
    assert secciones == [("Sistema", "SISTEMA"), ("bloque uno", "[anillo 1]\nuno"),
                         ("bloque dos", "[anillo 2]\ndos")]
    assert prompt_compiler.render_context(secciones) == (
        "=== Sistema ===\nSISTEMA\n\n=== bloque uno ===\n[anillo 1]\nuno"
        "\n\n=== bloque dos ===\n[anillo 2]\ndos")
    assert usuario.startswith("que libro lei\n\n")
    assert "Venias diciendo: Dejame ver que dije \n" in usuario
    # con bloques va la letra nueva (spec canarios, seccion 4)
    assert usuario.endswith(turno.INSTRUCCION_CONTINUAR_CON_BLOQUES)


def test_sin_bloques_el_system_no_cambia_y_la_letra_es_la_de_siempre(monkeypatch):
    monkeypatch.delenv("CALIPSO_REENTRADA", raising=False)
    secciones, usuario = turno.prompt_reentrada([("Sistema", "SISTEMA")], [], ["a"], "m")
    assert secciones == [("Sistema", "SISTEMA")]
    assert usuario.endswith(turno.INSTRUCCION_CONTINUAR)
    assert "SOLO en lo que subio" not in usuario
    # un bloque vacio no cuenta como bloque (tras un fallo la lista puede traer "")
    _, usuario = turno.prompt_reentrada([("Sistema", "S")], [""], ["a"], "m")
    assert usuario.endswith(turno.INSTRUCCION_CONTINUAR)


def test_las_letras_de_la_reentrada_son_las_medidas(monkeypatch):
    """Byte a byte contra experimentos/variantes/ (como el contrato del
    abismo): cambiar la letra es re-correr el porton."""
    variantes = pathlib.Path(__file__).resolve().parent / "experimentos" / "variantes"
    assert turno.INSTRUCCION_CONTINUAR == (variantes / "reentrada-sin-bloques.txt").read_text(encoding="utf-8").strip()
    assert turno.INSTRUCCION_CONTINUAR_CON_BLOQUES == (variantes / "reentrada-con-bloques.txt").read_text(encoding="utf-8").strip()
    assert turno.LETRAS_REENTRADA == (turno.INSTRUCCION_CONTINUAR, turno.INSTRUCCION_CONTINUAR_CON_BLOQUES)
    # el interruptor del porton, leido por llamada
    monkeypatch.setenv("CALIPSO_REENTRADA", "vieja")
    assert turno.letra_activa() == "vieja"
    _, usuario = turno.prompt_reentrada([("Sistema", "S")], ["=== b ===\nx"], ["a"], "m")
    assert usuario.endswith(turno.INSTRUCCION_CONTINUAR)
    monkeypatch.setenv("CALIPSO_REENTRADA", "lo que sea")
    assert turno.letra_activa() == turno.LETRA_DEFAULT


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


_HONDO = [("del core:\n- vive en Cordoba", anillos.HONDO)]
_ORILLA = [("proyecto calipso:\nbrief", anillos.ORILLA)]


def test_los_motivos_reales_del_viaje_sobreviven_a_la_senal(monkeypatch):
    """Acopla la lista cerrada MOTIVOS con lo que emiten DE VERDAD el viaje y
    el juez: un motivo que no este en la lista lo aplana `senal` a "error" sin
    hacer ruido, y la UI mostraria el motivo equivocado (spec seccion 9)."""
    cortado = {"tramos": [], "fallo_cerrado": True, "motivo": "tipo_desconocido"}

    def caido(texto):
        raise RuntimeError("el juez local no responde")

    casos = [([], lambda t: cortado, "vacio"),
             (_HONDO, lambda t: cortado, "solo_hondo"),
             (_ORILLA, caido, "juez_local_caido"),
             (_ORILLA, lambda t: cortado, "tipo_desconocido"),
             (_ORILLA, lambda t: dict(cortado, motivo="credencial"), "credencial")]
    for bloques, juzgar, esperado in casos:
        monkeypatch.setattr(juez, "juzgar", juzgar)
        r = viaje.preparar_viaje(bloques, "nube", MapaMarcadores(), fuente="memoria")
        assert r["motivo"] == esperado
        assert turno.senal("fallo", "memoria", motivo=r["motivo"])["motivo"] == esperado


def test_el_motivo_de_la_consulta(monkeypatch):
    """Contra el resultado REAL del resolvedor y no contra el literal: el
    aviso de la pesca vacia lo escribe consulta._fallo, y si cambia ahi el
    motivo pasaria a "error" en silencio (Pedro leeria el motivo equivocado
    en la senal)."""
    monkeypatch.setattr(fuentes, "chats_viejos", lambda resto, **kw: [])
    vacia = consulta.resolver(marca.Marca("chats", "zzz"))
    assert vacia["estado"] == "fallo"
    assert turno.motivo_de_consulta(vacia) == "vacio"

    def bomba(resto, **kw):
        raise RuntimeError("chats.json roto")
    monkeypatch.setattr(fuentes, "chats_viejos", bomba)
    assert turno.motivo_de_consulta(consulta.resolver(marca.Marca("chats", "zzz"))) == "error"


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
