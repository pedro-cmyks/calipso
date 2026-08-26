"""Tests de la marca de foco (spec seccion 8, chat -> mapa)."""
import asyncio

import calipso.server as srv
from calipso import prompt_compiler
from calipso.economia import departamentos as deps
from calipso.mapa import ficha
from calipso.mapa import foco
from calipso.mapa import pulso as p


def test_una_marca_entera_desaparece_del_texto():
    f = foco.Filtro()
    assert f.comer("miremos ⟦foco:atlas⟧ un rato") == "miremos  un rato"
    assert f.tomar_focos() == ["atlas"]
    # y tomarlos los consume: la camara no vuela dos veces por lo mismo
    assert f.tomar_focos() == []


def test_la_marca_partida_en_tres_trozos_igual_se_arma():
    """Es el caso real: el stream corta donde se le da la gana, y una marca
    de trece caracteres cae partida a menudo."""
    f = foco.Filtro()
    assert f.comer("vamos a ⟦fo") == "vamos a "
    assert f.comer("co:atl") == ""
    assert f.comer("as⟧ ahora") == " ahora"
    assert f.tomar_focos() == ["atlas"]
    assert f.cerrar() == ""


def test_lo_retenido_que_no_era_marca_se_devuelve_al_cerrar():
    """Un texto que empieza como la marca y no lo es no se puede tragar: si
    la respuesta termina con un corchete raro, Pedro tiene que verlo."""
    f = foco.Filtro()
    assert f.comer("mira este simbolo: ⟦") == "mira este simbolo: "
    assert f.cerrar() == "⟦"
    assert f.tomar_focos() == []


def test_una_marca_que_nunca_cierra_es_texto():
    """Sin tope, un `⟦foco:` sin cierre se come el resto de la respuesta."""
    f = foco.Filtro()
    largo = "x" * (foco.MAX_NOMBRE + 5)
    salida = f.comer("hola ⟦foco:" + largo)
    assert salida == "hola ⟦foco:" + largo
    assert f.tomar_focos() == []


def test_dos_marcas_en_el_mismo_trozo():
    f = foco.Filtro()
    assert f.comer("⟦foco:atlas⟧ y ⟦foco:mercado⟧") == " y "
    assert f.tomar_focos() == ["atlas", "mercado"]


def test_una_marca_vacia_no_enfoca_nada():
    f = foco.Filtro()
    assert f.comer("nada ⟦foco:⟧ aca") == "nada  aca"
    assert f.tomar_focos() == []


def test_el_texto_sin_marcas_pasa_intacto_y_sin_retener_nada():
    f = foco.Filtro()
    assert f.comer("una respuesta comun y corriente") == (
        "una respuesta comun y corriente")
    assert f.cerrar() == ""


def test_limpiar_saca_las_marcas_de_un_texto_entero():
    """Para el acumulado de la ruta de suscripcion, que no es incremental."""
    assert foco.limpiar("hola ⟦foco:atlas⟧ y ⟦foco:mercado⟧ chau") == (
        "hola  y  chau")
    # una marca a medio llegar se deja: el proximo envio trae el texto entero
    assert foco.limpiar("cortada ⟦foco:atl") == "cortada ⟦foco:atl"
    assert foco.limpiar("") == "" and foco.limpiar(None) == ""


class WSFalso:
    """Anota lo que se manda, en vez de mandarlo."""

    def __init__(self):
        self.enviados = []

    async def send_json(self, dato):
        self.enviados.append(dato)


def textos(ws):
    return [e["text"] for e in ws.enviados if e.get("type") == "chunk"]


def test_el_nombre_se_resuelve_contra_los_departamentos_que_existen():
    edificios = [{"id": "dep:atlas", "nombre": "atlas"},
                 {"id": "personal:finanzas", "nombre": "finanzas"}]
    assert ficha.id_de_nombre("atlas", edificios) == "dep:atlas"
    assert ficha.id_de_nombre("Atlas", edificios) == "dep:atlas"   # sin caso
    assert ficha.id_de_nombre("dep:atlas", edificios) == "dep:atlas"
    assert ficha.id_de_nombre("finanzas", edificios) == "personal:finanzas"
    # el modelo se puede inventar un departamento: eso no vuela a ningun lado
    assert ficha.id_de_nombre("ministerio", edificios) is None


def test_el_emisor_retira_la_marca_publica_el_foco_y_alimenta_al_pulso():
    ws, pu = WSFalso(), p.Pulso()
    edificios = [{"id": "dep:atlas", "nombre": "atlas"}]
    em = srv.Emisor(ws, agente_id="a1",
                    resolver=lambda n: ficha.id_de_nombre(n, edificios),
                    pulso=pu, filtro=foco.Filtro())

    async def turno():
        salida = ""
        salida += await em.chunk("vamos a ⟦fo")
        salida += await em.chunk("co:atlas⟧ mirar")
        salida += await em.cerrar()
        return salida

    assert asyncio.run(turno()) == "vamos a  mirar"
    # lo que salio por el socket es lo mismo que se devolvio, sin la marca
    assert "".join(textos(ws)) == "vamos a  mirar"
    assert em.focos == ["dep:atlas"]
    # el foco viaja por el pulso, que es lo que el mapa esta escuchando
    eventos = pu.desde(0)[1]
    assert [e["evento"] for e in eventos if e["evento"] == "foco"] == ["foco"]
    assert [e for e in eventos if e["evento"] == "foco"][0]["departamento"] == "dep:atlas"
    # y el razonamiento del turno queda en el anillo del agente
    assert "".join(e.get("texto", "") for e in pu.eventos("a1")) == "vamos a  mirar"


def test_el_emisor_no_manda_chunks_vacios():
    """Un trozo que era pura marca no puede salir como un chunk vacio: la UI
    vieja lo pinta igual y queda un turno con un salto de linea de mas."""
    import asyncio

    ws = WSFalso()
    em = srv.Emisor(ws, filtro=foco.Filtro())
    asyncio.run(em.chunk("⟦foco:atlas⟧"))
    assert textos(ws) == []


def test_el_contrato_interno_le_dice_al_modelo_como_emitir_la_marca():
    """La instruccion vive en el compilador de prompts (spec seccion 8), no
    suelta en un f-string del server. `test_prompt_compiler.py` no lo cubre:
    es de los que pytest no colecta (tiene main(), no tests)."""
    texto = prompt_compiler.internal_contract({})
    assert foco.ABRE in texto and foco.CIERRA in texto
    assert "no la ve" in texto or "no se muestra" in texto


def test_el_parcial_de_la_suscripcion_tampoco_muestra_la_marca():
    """El otro camino por el que el texto del modelo llega a Pedro: el
    acumulado que la ruta de suscripcion remanda cada dos segundos."""
    assert srv._limpiar_marcas("corriendo ⟦foco:atlas⟧ todavia") == (
        "corriendo  todavia")
    assert srv._limpiar_marcas("") == ""


def test_los_edificios_livianos_no_tocan_el_libro(tmp_path, monkeypatch):
    """Se lee el registro, que es un JSON chico, no el libro entero: esto
    corre en cada turno de chat para resolver el nombre del foco."""
    eco = tmp_path / ".calipso" / "economia"
    eco.mkdir(parents=True)
    (eco / "libro.jsonl").write_text("", encoding="utf-8")
    (eco / "suscripciones.json").write_text("{}", encoding="utf-8")
    r = deps.Registro(eco / "departamentos.json")
    r.alta(deps.Departamento("atlas", deps.ZONA_FABRICA))
    r.alta(deps.Departamento("finanzas", deps.ZONA_PERSONAL))
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / ".calipso")
    assert srv._edificios_livianos() == [{"id": "dep:atlas", "nombre": "atlas"},
                                         {"id": "personal:finanzas",
                                          "nombre": "finanzas"}]


def test_sin_economia_no_hay_a_quien_enfocar(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "_ECO_BASE", tmp_path / "vacio")
    assert srv._edificios_livianos() == []


def visible_del_filtro(texto):
    """Lo que un `Filtro` deja ver de un texto que le llega de una sola vez,
    lo retenido incluido: el equivalente exacto de `limpiar(texto)`."""
    f = foco.Filtro()
    return f.comer(texto) + f.cerrar()


def test_un_nombre_larguisimo_no_es_marca_ni_para_el_filtro_ni_para_limpiar():
    """`limpiar` y el `Filtro` tienen que juzgar igual: si uno cree que hay
    marca donde el otro ve texto, el que la ve de mas se come texto visible.
    Un nombre de miles de caracteres no es un departamento, es texto."""
    texto = "ojo " + foco.ABRE + "y" * 5000 + foco.CIERRA + " con esto"
    assert foco.limpiar(texto) == texto
    assert visible_del_filtro(texto) == texto      # entero en un solo trozo
    f = foco.Filtro()
    f.comer(texto)
    assert f.tomar_focos() == []
    # y partido, donde la retencion entra en juego, el juicio no cambia
    g = foco.Filtro()
    partido = (g.comer("ojo " + foco.ABRE + "y" * 5000)
               + g.comer(foco.CIERRA + " con esto") + g.cerrar())
    assert partido == texto
    assert g.tomar_focos() == []


def test_el_tope_del_nombre_es_el_mismo_de_los_dos_lados():
    """El borde exacto: MAX_NOMBRE todavia es marca, uno mas ya es texto."""
    justo = foco.ABRE + "z" * foco.MAX_NOMBRE + foco.CIERRA
    pasado = foco.ABRE + "z" * (foco.MAX_NOMBRE + 1) + foco.CIERRA
    assert foco.limpiar(justo) == "" and visible_del_filtro(justo) == ""
    assert foco.limpiar(pasado) == pasado
    assert visible_del_filtro(pasado) == pasado
