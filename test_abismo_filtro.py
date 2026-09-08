"""El filtro de streaming de la marca del abismo (spec secciones 4 y 11) y su
composicion con el de foco en el Emisor."""
import asyncio
import json

import calipso.server as srv
from calipso.abismo import filtro, marca
from calipso.mapa import foco
from calipso.mapa import pulso as p


def _f(puede=True):
    return filtro.FiltroAbismo(puede_cortar=lambda: puede)


def test_sin_marca_es_transparente_byte_a_byte():
    f = _f()
    texto = "una respuesta comun, con ⟦foco:atlas⟧ y un ⟧ suelto"
    assert f.comer(texto) == texto
    assert f.cerrar() == "" and f.tomar_marca() is None and f.tomar_avisos() == []


def test_una_marca_valida_corta_y_descarta_lo_posterior():
    f = _f()
    assert f.comer("Dejame ver ⟦abismo:chats libro agosto⟧ y sigo hablando") == "Dejame ver "
    assert f.comer("mas texto que vino sin contexto") == ""
    assert f.tomar_marca() == marca.Marca("chats", "libro agosto")
    # consumida la marca, el filtro deja pasar la continuacion de la reentrada
    assert f.comer("la continuacion") == "la continuacion"
    assert f.tomar_marca() is None and f.tomar_avisos() == []


def test_la_marca_partida_en_trozos_igual_se_arma():
    f = _f()
    assert f.comer("vamos a ⟦abi") == "vamos a "
    assert f.comer("smo:memoria que le gus") == ""
    assert f.comer("ta leer⟧ ahora") == ""
    assert f.tomar_marca() == marca.Marca("memoria", "que le gusta leer")


def test_una_marca_ilegible_se_retira_con_aviso_y_sin_corte():
    f = _f()
    assert f.comer("hola ⟦abismo:memorai que dije⟧ sigo") == "hola  sigo"
    assert f.tomar_marca() is None
    assert f.tomar_avisos() == [{"clase": "ilegible", "largo": 16}]


def test_con_el_tope_alcanzado_la_marca_se_retira_y_el_texto_posterior_vale():
    f = _f(puede=False)
    assert f.comer("hola ⟦abismo:chats libro⟧ sigo") == "hola  sigo"
    assert f.tomar_marca() is None
    assert f.tomar_avisos() == [{"clase": "sin_corte", "fuente": "chats", "largo": 11}]


def test_una_marca_abierta_al_cerrar_se_descarta_con_aviso():
    f = _f()
    assert f.comer("termino asi ⟦abismo:chats sin cie") == "termino asi "
    assert f.cerrar() == ""          # jamas se vuelca cruda (divergencia de foco)
    assert f.tomar_avisos() == [{"clase": "abierta", "largo": len("⟦abismo:chats sin cie")}]


def test_un_prefijo_suelto_al_cerrar_es_texto_y_se_vuelca():
    """Un `⟦` (o `⟦abi`) al final del stream NO es una marca inconclusa:
    nunca llego a `⟦abismo:`. Es texto, Pedro tiene que verlo, igual que con
    foco (invariante 3: sin marca, bytes identicos). Solo lo que ya abrio la
    marca se descarta."""
    f = _f()
    assert f.comer("termino con ⟦") == "termino con "
    assert f.cerrar() == "⟦" and f.tomar_avisos() == []
    g = _f()
    assert g.comer("y esto ⟦abi") == "y esto "
    assert g.cerrar() == "⟦abi" and g.tomar_avisos() == []
    # y por la tuberia compuesta del Emisor: foco vuelca el `⟦` que retenia,
    # el abismo lo mira, no es marca, y sale
    ws = WSFalso()
    em = srv.Emisor(ws, filtros=[foco.Filtro(), filtro.FiltroAbismo()], pulso=p.Pulso())

    async def turno():
        return (await em.chunk("mira: ⟦")) + (await em.cerrar())

    assert asyncio.run(turno()) == "mira: ⟦"
    assert "".join(textos(ws)) == "mira: ⟦"


def test_una_marca_de_200_chars_no_se_escapa_cruda():
    """El tope de la pregunta es 160, pero el filtro retiene hasta el tope
    holgado de PATRON (400): la marca larga es ilegible, no texto."""
    f = _f()
    cuerpo = "memoria " + "x" * 192
    assert f.comer("a ⟦abismo:" + cuerpo + "⟧ b") == "a  b"
    assert f.tomar_marca() is None
    assert [a["clase"] for a in f.tomar_avisos()] == ["ilegible"]


def _visible(texto):
    return _f().comer(texto)


def test_el_tope_del_cuerpo_es_el_mismo_que_el_de_patron():
    """Filtro y PATRON juzgan igual QUE es una marca (la leccion de
    foco.py:81-84): 400 todavia lo es (ilegible, se retira), 401 ya es texto
    y los dos lo dejan intacto."""
    justo = "⟦abismo:" + "z" * filtro.CUERPO_MAX + "⟧"
    pasado = "⟦abismo:" + "z" * (filtro.CUERPO_MAX + 1) + "⟧"
    assert marca.PATRON.sub("", justo) == "" and _visible(justo) == ""
    assert marca.PATRON.sub("", pasado) == pasado and _visible(pasado) == pasado
    # y partido en dos, donde la retencion entra en juego, el juicio no cambia
    g = _f()
    assert g.comer("⟦abismo:" + "z" * (filtro.CUERPO_MAX + 1)) + g.comer("⟧ fin") == pasado + " fin"


def test_un_corchete_anidado_no_secuestra_la_marca_siguiente():
    texto = "x ⟦abismo:zzz ⟦abismo:chats hola⟧ fin"
    assert marca.encontrar(texto) == [marca.Marca("chats", "hola")]
    f = _f()
    assert f.comer(texto) == "x ⟦abismo:zzz "
    assert f.tomar_marca() == marca.Marca("chats", "hola")


def test_una_marca_de_foco_dentro_del_cuerpo_no_se_traga():
    texto = "a ⟦abismo:memoria b ⟦foco:atlas⟧ resto"
    assert marca.encontrar(texto) == []
    assert _visible(texto) == texto   # el filtro de foco, que corre antes, la ve


class WSFalso:
    """Anota lo que se manda, en vez de mandarlo (test_mapa_foco.py:77-84)."""

    def __init__(self):
        self.enviados = []

    async def send_json(self, dato):
        self.enviados.append(dato)


def textos(ws):
    return [e["text"] for e in ws.enviados if e.get("type") == "chunk"]


def test_el_emisor_compuesto_retira_las_dos_marcas_y_entrega_la_del_abismo():
    ws, pu, avisos = WSFalso(), p.Pulso(), []
    em = srv.Emisor(ws, agente_id="a1", resolver=lambda n: "dep:" + n, pulso=pu,
                    filtros=[foco.Filtro(), filtro.FiltroAbismo()],
                    avisar=avisos.append)

    async def turno():
        salida = ""
        salida += await em.chunk("miremos ⟦foco:atlas⟧ y ⟦abi")
        salida += await em.chunk("smo:chats libro⟧ esto no sale")
        m = em.marca_abismo()
        salida += await em.chunk(" la continuacion")
        salida += await em.cerrar()
        return salida, m

    salida, m = asyncio.run(turno())
    assert salida == "miremos  y  la continuacion"
    assert "".join(textos(ws)) == salida
    assert em.focos == ["dep:atlas"]
    assert m == marca.Marca("chats", "libro")
    assert em.marca_abismo() is None and avisos == []


def test_el_emisor_con_solo_foco_sigue_volcando_lo_retenido():
    """La ruta de foco sola no cambia (test_mapa_foco.py:102-125 sigue tal
    cual), y `Emisor(ws)` -el borrador de /redacta- NO lleva el filtro del
    abismo: una marca valida le pasa de largo como texto."""
    ws = WSFalso()
    em = srv.Emisor(ws, filtro=foco.Filtro(), pulso=p.Pulso())

    async def turno():
        return (await em.chunk("mira este simbolo: ⟦")) + (await em.cerrar())

    assert asyncio.run(turno()) == "mira este simbolo: ⟦"
    solo = srv.Emisor(WSFalso(), pulso=p.Pulso())
    assert asyncio.run(solo.chunk("a ⟦abismo:chats x⟧ b")) == "a ⟦abismo:chats x⟧ b"
    assert solo.marca_abismo() is None


def test_el_emisor_compuesto_descarta_la_marca_abierta_con_aviso():
    ws, avisos = WSFalso(), []
    em = srv.Emisor(ws, filtros=[foco.Filtro(), filtro.FiltroAbismo()],
                    pulso=p.Pulso(), avisar=avisos.append)

    async def turno():
        return (await em.chunk("termino asi ⟦abismo:chats sin cie")) + (await em.cerrar())

    assert asyncio.run(turno()) == "termino asi "
    assert [a["clase"] for a in avisos] == ["abierta"]


def test_el_aviso_por_defecto_deja_fila_en_telemetry_sin_el_texto(tmp_path, monkeypatch):
    monkeypatch.setattr(srv.telemetry, "LEDGER", tmp_path / "t.jsonl")
    em = srv.Emisor(WSFalso(), filtros=[filtro.FiltroAbismo()], pulso=p.Pulso())
    asyncio.run(em.chunk("hola ⟦abismo:memorai x⟧ sigo"))
    filas = [json.loads(l) for l in (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()]
    assert filas[-1]["kind"] == "abismo" and filas[-1]["evento"] == "retirada"
    assert filas[-1]["clase"] == "ilegible" and "memorai" not in json.dumps(filas)


def test_retirar_con_aviso_saca_solo_el_abismo_y_deja_la_cantidad(tmp_path, monkeypatch):
    """El retiro por fuera del filtro (la sintesis de los agentes, el resto
    posterior del one-shot): "se ignoran CON aviso" (spec seccion 4) es una
    fila por retiro, con la cantidad y sin el cuerpo. La gramatica de foco
    no es asunto suyo."""
    monkeypatch.setattr(srv.telemetry, "LEDGER", tmp_path / "t.jsonl")
    texto = "a ⟦abismo:chats x⟧ b ⟦abismo:zzz⟧ c ⟦foco:atlas⟧"
    assert srv._retirar_con_aviso(texto, "agente") == "a  b  c ⟦foco:atlas⟧"
    filas = [json.loads(l) for l in (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(filas) == 1 and filas[0]["evento"] == "retirada"
    assert filas[0]["clase"] == "agente" and filas[0]["cantidad"] == 2
    assert "chats x" not in json.dumps(filas)
    # sin marcas no hay fila
    assert srv._retirar_con_aviso("sin marcas", "agente") == "sin marcas"
    assert len((tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_limpiar_marcas_saca_las_dos_gramaticas():
    assert srv._limpiar_marcas("a ⟦abismo:chats x⟧ b ⟦foco:atlas⟧ c") == "a  b  c"
    assert srv._limpiar_marcas("cortada ⟦abismo:chats x") == "cortada ⟦abismo:chats x"
    assert srv._limpiar_marcas("") == "" and srv._limpiar_marcas(None) == ""


EMPALMES = ("⟦abismo:⟦abismo:chats x⟧chats y⟧",
            "a ⟦abismo:chats ⟦foco:atlas⟧ libro⟧ b")


def test_las_dos_rutas_de_retiro_juzgan_igual_el_empalme():
    """Sacar una marca pega el texto de los dos costados, y ese empalme puede
    armar una marca NUEVA y completa: el cuerpo de `PATRON` no admite
    corchetes, asi que la de adentro tapaba a la de afuera y una de foco
    partia el cuerpo del abismo en dos. Con estos dos textos las dos rutas de
    retiro divergian -la tuberia del Emisor cortaba, `_limpiar_marcas` dejaba
    la marca armada y la mandaba a disco-, justo lo que el mapa del filtro
    (7.4) prohibe. Ninguna de las dos puede dejar una marca en pie."""
    for texto in EMPALMES:
        fo, ab = foco.Filtro(), filtro.FiltroAbismo()
        visible = ab.comer(fo.comer(texto)) + ab.comer(fo.cerrar()) + ab.cerrar()
        assert marca.encontrar(visible) == []
        assert marca.encontrar(srv._limpiar_marcas(texto)) == []


def test_limpiar_marcas_llega_al_punto_fijo_y_saca_foco_primero():
    """Las dos rutas de retiro tienen que juzgar igual el mismo texto (mapa
    del filtro 7.4). Con una sola pasada de `sub`, y con el abismo antes que
    foco, quedaba una marca valida y COMPLETA en el texto que sale al panel
    y al `jobs.event` del preview -o sea, en disco-. De ahi las dos cosas:
    el orden de la tuberia del Emisor (foco primero, abismo despues) y el
    punto fijo del retiro del abismo."""
    anidada, tapada = EMPALMES
    assert srv._limpiar_marcas(anidada) == ""
    assert srv._limpiar_marcas(tapada) == "a  b"


def test_retirar_con_aviso_llega_al_punto_fijo_y_cuenta_las_dos_vueltas(tmp_path, monkeypatch):
    """El mismo empalme por la ruta de los agentes: con una sola pasada la
    marca que quedo armada viajaba en el texto de la sintesis y ademas la
    `cantidad` del aviso mentia (informaba 1)."""
    monkeypatch.setattr(srv.telemetry, "LEDGER", tmp_path / "t.jsonl")
    assert srv._retirar_con_aviso("⟦abismo:⟦abismo:chats x⟧chats y⟧", "agente") == ""
    filas = [json.loads(l) for l in (tmp_path / "t.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(filas) == 1 and filas[0]["cantidad"] == 2
