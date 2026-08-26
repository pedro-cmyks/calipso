"""Tests del pulso: la capa viva del mapa (spec seccion 5)."""
from calipso.mapa import pulso as p


def ev(evento, ts, **campos):
    """Un evento como el que arma `publicar`, para probar las derivadas."""
    return {"seq": 0, "ts": ts, "agente_id": "a1", "departamento": "dep:atlas",
            "trabajo": None, "rol": "scout", "modelo": "sonnet",
            "evento": evento, **campos}


def test_el_estado_se_deriva_del_ultimo_evento():
    """Un agente no declara su estado: se lo lee de lo que hizo."""
    assert p.estado_de([], 100.0) == "esperando"
    assert p.estado_de([ev("inicio", 100.0)], 101.0) == "esperando"
    assert p.estado_de([ev("razonando", 100.0, texto="hola")], 101.0) == "razonando"
    assert p.estado_de([ev("herramienta", 100.0, nombre="grep",
                           resumen="3 hits")], 101.0) == "razonando"
    assert p.estado_de([ev("fin", 100.0, runtime_ms=5, resultado="ok")],
                       101.0) == "liberado"


def test_el_que_dejo_de_publicar_se_marca_inactivo():
    """Spec: diez minutos sin eventos y el escritorio queda vacio. El corte
    es contra el reloj que se le pasa, no contra el del sistema."""
    eventos = [ev("razonando", 100.0, texto="pensando")]
    assert p.estado_de(eventos, 100.0 + 599, inactivo_s=600) == "razonando"
    assert p.estado_de(eventos, 100.0 + 601, inactivo_s=600) == "inactivo"
    # pero un agente ya liberado no se vuelve inactivo con el tiempo: se
    # solto, que es una cosa distinta de haberse colgado
    fin = [ev("fin", 100.0, runtime_ms=5, resultado="ok")]
    assert p.estado_de(fin, 100.0 + 9_999, inactivo_s=600) == "liberado"


def test_los_tokens_son_acumulados_no_incrementales():
    """El evento `tokens` trae el TOTAL. Sumar los eventos contaria dos
    veces el mismo consumo y el popup mostraria el doble de lo gastado."""
    eventos = [ev("inicio", 100.0),
               ev("tokens", 101.0, tokens_in=100, tokens_out=10, costo_mm=5),
               ev("tokens", 102.0, tokens_in=300, tokens_out=40, costo_mm=17)]
    r = p.resumen(eventos, 103.0)
    assert (r["tokens_in"], r["tokens_out"], r["costo_mm"]) == (300, 40, 17)


def test_el_resumen_junta_el_razonamiento_y_el_ultimo_diff():
    eventos = [ev("inicio", 100.0),
               ev("razonando", 100.5, texto="mirando "),
               ev("razonando", 100.9, texto="el libro"),
               ev("diff", 101.0, ruta="a.py", diff="- viejo\n+ nuevo"),
               ev("diff", 102.0, ruta="b.py", diff="- otro\n+ nuevo")]
    r = p.resumen(eventos, 103.0)
    assert r["texto"] == "mirando el libro"
    assert r["diff"] == {"ruta": "b.py", "diff": "- otro\n+ nuevo"}
    # sin evento `fin`, el runtime se mide de punta a punta de lo publicado
    assert r["runtime_ms"] == 2000


class Reloj:
    """Un reloj que avanza cuando se lo dice el test, no cuando pasa el
    tiempo de verdad."""

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t

    def avanzar(self, s):
        self.t += s


def test_la_identidad_se_hereda_del_inicio():
    """Cada evento sale con departamento, rol y modelo aunque el que
    publica solo mande el texto: el cliente indexa por departamento y un
    evento sin departamento no tiene escritorio donde caer."""
    reloj = Reloj()
    pu = p.Pulso(ahora=reloj)
    pu.publicar("a1", "inicio", departamento="dep:atlas", rol="scout",
                modelo="sonnet")
    ev = pu.publicar("a1", "razonando", texto="mirando")
    assert ev["departamento"] == "dep:atlas"
    assert ev["rol"] == "scout" and ev["modelo"] == "sonnet"
    assert ev["seq"] == 2 and ev["ts"] == 1000.0


def test_los_anillos_no_crecen_sin_limite():
    """Spec: los anillos son de tamano fijo. Un proceso que corre una semana
    no puede quedarse con todo lo que paso en la semana."""
    pu = p.Pulso(ahora=Reloj(), por_agente=3, recientes=2, flujo=4)
    pu.publicar("a1", "inicio", departamento="dep:atlas")
    for i in range(10):
        pu.publicar("a1", "razonando", texto=str(i))
    assert len(pu.eventos("a1")) == 3
    assert [e["texto"] for e in pu.eventos("a1")] == ["7", "8", "9"]
    # y el anillo de agentes tambien: al entrar el tercero, el primero se va
    # ENTERO (sus eventos tambien, o el diccionario crece igual)
    pu.publicar("a2", "inicio", departamento="dep:atlas")
    pu.publicar("a3", "inicio", departamento="dep:atlas")
    assert pu.recientes() == ["a3", "a2"]
    assert pu.eventos("a1") == []


def test_el_cursor_entrega_lo_nuevo_en_orden():
    """Es el contrato del WebSocket: el cliente guarda un numero y pregunta
    que paso despues de ese numero."""
    pu = p.Pulso(ahora=Reloj())
    pu.publicar("a1", "inicio", departamento="dep:atlas")
    pu.publicar("a1", "razonando", texto="uno")
    cursor, nuevos = pu.desde(0)
    assert [e["evento"] for e in nuevos] == ["inicio", "razonando"]
    assert cursor == 2
    cursor, nuevos = pu.desde(cursor)
    assert nuevos == [] and cursor == 2
    pu.publicar("a1", "razonando", texto="dos")
    _, nuevos = pu.desde(cursor)
    assert [e["texto"] for e in nuevos] == ["dos"]


def test_el_flujo_aguanta_un_turno_entero_de_chunks():
    """El `Emisor` publica un evento `razonando` por CADA chunk del stream, y
    el que se reconecta reproduce el flujo desde cero. Con el flujo
    dimensionado para 500 eventos, el `inicio` del agente se caia del anillo
    dentro del mismo turno; a partir de ahi la reproduccion ya no reiniciaba
    el escritorio y el cliente duplicaba el texto."""
    pu = p.Pulso(ahora=Reloj())
    pu.publicar("a1", "inicio", departamento="dep:atlas")
    for _ in range(2000):
        pu.publicar("a1", "razonando", texto="x")
    _, nuevos = pu.desde(0)
    assert nuevos[0]["evento"] == "inicio", (
        "el inicio del turno ya no esta en el flujo: el que se reconecta "
        "recibe el turno a medio empezar")


def test_el_foco_viaja_por_el_mismo_canal_sin_agente():
    pu = p.Pulso(ahora=Reloj())
    ev = pu.enfocar("dep:atlas")
    assert ev["evento"] == "foco" and ev["agente_id"] is None
    assert ev["departamento"] == "dep:atlas"
    assert pu.desde(0)[1] == [ev]


def test_el_envoltorio_abre_y_cierra_solo():
    reloj = Reloj()
    pu = p.Pulso(ahora=reloj)
    with pu.agente("a1", departamento="dep:atlas", rol="scout",
                   modelo="sonnet") as mango:
        reloj.avanzar(1.5)
        mango.razonando("pensando")
        mango.tokens(100, 20, 7)
    tipos = [e["evento"] for e in pu.eventos("a1")]
    assert tipos == ["inicio", "razonando", "tokens", "fin"]
    fin = pu.eventos("a1")[-1]
    assert fin["runtime_ms"] == 1500 and fin["resultado"] == "ok"


def test_un_agente_que_revienta_igual_se_cierra_y_lo_dice():
    """Sin esto, un agente que falla queda razonando para siempre en el
    mapa y el escritorio nunca se libera."""
    pu = p.Pulso(ahora=Reloj())
    try:
        with pu.agente("a1", departamento="dep:atlas"):
            raise RuntimeError("se cayo el backend")
    except RuntimeError:
        pass
    fin = pu.eventos("a1")[-1]
    assert fin["evento"] == "fin" and fin["resultado"] == "error"


def test_los_empleados_son_los_del_departamento_y_traen_su_resumen():
    reloj = Reloj()
    pu = p.Pulso(ahora=reloj)
    with pu.agente("a1", departamento="dep:atlas", rol="scout") as m:
        m.tokens(100, 20, 7)
    pu.publicar("b1", "inicio", departamento="dep:mercado", rol="vendedor")
    reloj.avanzar(1)
    pu.publicar("a2", "inicio", departamento="dep:atlas", rol="copista")
    empleados = pu.empleados("dep:atlas")
    assert [e["agente_id"] for e in empleados] == ["a2", "a1"]  # el nuevo primero
    assert empleados[0]["estado"] == "esperando"
    assert empleados[1]["estado"] == "liberado"
    assert empleados[1]["tokens_in"] == 100 and empleados[1]["rol"] == "scout"
    assert [e["agente_id"] for e in pu.empleados("dep:mercado")] == ["b1"]
    assert pu.empleados("dep:nadie") == []


def test_un_evento_desconocido_no_entra():
    """El cliente hace un switch sobre el tipo: un tipo inventado se le
    escurre entero y no hay forma de notarlo desde el navegador."""
    pu = p.Pulso(ahora=Reloj())
    try:
        pu.publicar("a1", "pensando_mucho")
    except ValueError as e:
        assert "pensando_mucho" in str(e)
    else:
        raise AssertionError("publicar acepto un evento que no existe")
