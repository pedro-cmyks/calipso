"""La senal del abismo tambien va al pulso del mapa (spec seccion 9): las
dos listas de eventos -la del server y la del cliente- se tocan juntas."""
import pathlib
import re

from calipso.mapa import pulso as p

FABRICA = pathlib.Path(__file__).parent / "calipso" / "web" / "fabrica"


def conocidos_del_cliente() -> list[str]:
    js = (FABRICA / "pulso.js").read_text(encoding="utf-8")
    cuerpo = js.split("const CONOCIDOS = [", 1)[1].split("];", 1)[0]
    return re.findall(r'"([a-z_]+)"', cuerpo)


def test_las_dos_listas_de_eventos_del_pulso_estan_acopladas():
    """Sumar un evento a una sola lista no pone nada en rojo: el server
    revienta o el cliente lo descarta mudo. Este test es la costura."""
    assert set(conocidos_del_cliente()) == set(p.EVENTOS)


def test_el_abismo_es_un_evento_del_pulso():
    pu = p.Pulso()
    ev = pu.publicar("chat:x", "abismo", fase="pondering", fuente="chats",
                     departamento="dep:atlas")
    assert ev["evento"] == "abismo" and ev["fase"] == "pondering" and ev["fuente"] == "chats"
    assert [e["evento"] for e in pu.eventos("chat:x")] == ["abismo"]
