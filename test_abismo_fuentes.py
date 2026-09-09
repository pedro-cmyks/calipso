"""Las fuentes del abismo devuelven sub-bloques (texto, anillo) -- spec 6-7."""
import datetime
import json
import pathlib

from calipso import chats
from calipso.abismo import anillos, fuentes

import pytest


def _sembrar_chats(tmp_path, monkeypatch):
    data = {"active": "c1", "chats": {
        "c1": {"id": "c1", "title": "lecturas", "messages": [
            {"role": "user", "text": "empece El nombre de la rosa, es un libro alucinante", "meta": {},
             "ts": "2026-08-03T10:00:00"},
            {"role": "assistant", "text": "buen libro", "meta": {},
             "ts": "2026-08-03T10:00:05"},
            {"role": "user", "text": "/redacta hola", "meta": {},
             "ts": "2026-08-04T10:00:00"},
        ]},
        "c2": {"id": "c2", "title": "compras", "messages": [
            {"role": "user", "text": "el libro de cocina llego roto", "meta": {},
             "ts": "2026-09-01T09:00:00"},
        ]},
    }}
    f = tmp_path / "chats.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(chats, "CHAT_FILE", f)


def test_todos_devuelve_chats_completos(tmp_path, monkeypatch):
    _sembrar_chats(tmp_path, monkeypatch)
    todos = chats.todos()
    assert {c["id"] for c in todos} == {"c1", "c2"}
    assert todos[0]["messages"]  # completos, no el conteo de list_chats


def test_chats_viejos_busca_por_palabra(tmp_path, monkeypatch):
    _sembrar_chats(tmp_path, monkeypatch)
    bloques = fuentes.chats_viejos("libro")
    assert bloques and all(a == anillos.MEDIA_AGUA for _, a in bloques)
    textos = "\n".join(t for t, _ in bloques)
    assert "El nombre de la rosa" in textos
    assert "cocina" in textos
    assert "[lecturas 2026-08-03]" in textos  # titulo y fecha del fragmento


def test_chats_viejos_no_pesca_lo_que_el_chat_activo_ya_tiene_en_contexto(tmp_path, monkeypatch):
    """h04 del cierre: la fuente pescaba el chat ACTIVO y la propia pregunta
    (mas reciente primero, tope 8), desplazando a los chats viejos. Los
    ultimos `en_contexto` mensajes del activo ya viajan en `messages`: no
    se pescan. Los anteriores a esa ventana si (spec seccion 1: "mas alla de
    los 12 mensajes de _HISTORY_TURNS")."""
    _sembrar_chats(tmp_path, monkeypatch)
    # c1: [rosa (0), buen libro (1), /redacta (2)]: con los ultimos 2 en
    # contexto, "rosa" (indice 0) sigue siendo pescable y "buen libro" no
    textos = "\n".join(t for t, _ in fuentes.chats_viejos("libro", chat_activo="c1", en_contexto=2))
    assert "rosa" in textos and "cocina" in textos and "buen libro" not in textos
    textos = "\n".join(t for t, _ in fuentes.chats_viejos("libro", chat_activo="c1", en_contexto=3))
    assert "rosa" not in textos and "cocina" in textos
    # otro chat activo: c1 entero sigue siendo viejo
    textos = "\n".join(t for t, _ in fuentes.chats_viejos("libro", chat_activo="c2", en_contexto=2))
    assert "rosa" in textos and "buen libro" in textos and "cocina" not in textos


def test_chats_viejos_deja_fuera_el_chat_activo_entero_si_se_lo_pide(tmp_path, monkeypatch):
    """`en_contexto=None`: el activo entero queda afuera. Es lo que pide un
    turno /nube, donde el historial no viaja (chat_id_nube=None, Fase 2a) y
    el bloque no puede ser la puerta de atras de un turno local previo."""
    _sembrar_chats(tmp_path, monkeypatch)
    textos = "\n".join(t for t, _ in fuentes.chats_viejos("libro", chat_activo="c1", en_contexto=None))
    assert "rosa" not in textos and "buen libro" not in textos and "cocina" in textos
    # sin chat activo declarado, todo es viejo (los tests del 1a siguen tal cual)
    assert len(fuentes.chats_viejos("libro")) == 3


def test_chats_viejos_respeta_rango(tmp_path, monkeypatch):
    _sembrar_chats(tmp_path, monkeypatch)
    bloques = fuentes.chats_viejos("libro desde:2026-09")
    textos = "\n".join(t for t, _ in bloques)
    assert "cocina" in textos
    assert "rosa" not in textos


def test_chats_viejos_ignora_gestos(tmp_path, monkeypatch):
    _sembrar_chats(tmp_path, monkeypatch)
    bloques = fuentes.chats_viejos("redacta")
    assert bloques == []  # los mensajes que empiezan con "/" no se pescan


def test_palabras_ignora_el_signo_de_apertura():
    # "¿donde?" pegado al signo no debe convertirse en una palabra distinta
    # de "donde" -- el ¿ no es una letra.
    assert "donde" in fuentes._palabras("¿donde estara?")


def test_chats_viejos_encuentra_pregunta_con_signos(tmp_path, monkeypatch):
    data = {"active": "c1", "chats": {
        "c1": {"id": "c1", "title": "casa", "messages": [
            {"role": "user", "text": "¿donde deje las llaves?", "meta": {},
             "ts": "2026-08-05T10:00:00"},
        ]},
    }}
    f = tmp_path / "chats.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(chats, "CHAT_FILE", f)
    bloques = fuentes.chats_viejos("¿donde?")
    textos = "\n".join(t for t, _ in bloques)
    assert "llaves" in textos


def test_rango_parsea_y_limpia():
    desde, hasta, palabras = fuentes._rango("libro desde:2026-08 hasta:2026-09 rosa")
    assert (desde, hasta) == ("2026-08", "2026-09")
    assert "desde:" not in palabras and "libro" in palabras and "rosa" in palabras


from calipso import chronology


class _FalsaMemoria:
    """Doble de Memory: solo lo que la fuente usa (recall + load_core)."""

    def __init__(self, hits, core=""):
        self._hits, self._core = hits, core
        self.pedido = None

    def recall(self, query, n=5, ambitos=None):
        self.pedido = {"query": query, "n": n, "ambitos": ambitos}
        return self._hits

    def load_core(self):
        return self._core


def test_memoria_recall_dirigido_sin_techos_del_turno(tmp_path, monkeypatch):
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    hits = [{"text": f"hecho {i}", "score": 0.9 - i * 0.1, "scope": "global"}
            for i in range(10)]  # los dos ultimos quedan bajo el umbral 0.20
    mem = _FalsaMemoria(hits)
    bloques = fuentes.memoria("que hago los domingos", mem)
    assert mem.pedido["n"] == fuentes.RECALL_N          # 12, no los 8 del turno
    episodico = [t for t, a in bloques if a == anillos.MEDIA_AGUA]
    assert len(episodico) == 1
    assert "hecho 0" in episodico[0]
    assert "hecho 8" not in episodico[0]                 # score 0.1 < 0.20
    assert "hecho 9" not in episodico[0]


def test_memoria_extractos_del_core_van_al_anillo_hondo(tmp_path, monkeypatch):
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    core = ("### perfil\n- A Pedro le gusta leer novela historica\n"
            "- Toma cafe sin azucar\n")
    mem = _FalsaMemoria([], core=core)
    bloques = fuentes.memoria("que novela le gusta", mem)
    hondos = [t for t, a in bloques if a == anillos.HONDO]
    assert any("novela historica" in t for t in hondos)
    assert not any("cafe" in t for t in hondos)          # linea sin clave no entra


def test_memoria_consolidado_solo_en_zona_personal(tmp_path, monkeypatch):
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    mem = _FalsaMemoria([])
    con = fuentes.memoria("plata", mem, consolidado="neto: 100",
                          zona_chat="personal")
    sin = fuentes.memoria("plata", mem, consolidado="neto: 100",
                          zona_chat="fabrica")
    assert any("neto: 100" in t and a == anillos.HONDO for t, a in con)
    assert not any("neto" in t for t, _ in sin)


def test_memoria_lee_la_cronologia_entera(tmp_path, monkeypatch):
    # spec seccion 7: "la cronologia entera". chronology.load() por defecto
    # trae solo las ultimas 80 (200 en el bug reportado) -- sembramos 250
    # entradas con la clave buscada en la mas VIEJA (la primera del archivo)
    # para probar que ya no queda afuera del corte.
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    p = chronology.path()
    dias = [datetime.date(2020, 1, 1) + datetime.timedelta(days=i)
            for i in range(250)]
    lineas = [f"- {d.isoformat()} | tema | evento numero {i}"
              for i, d in enumerate(dias)]
    lineas[0] = f"- {dias[0].isoformat()} | tema | trufa la mas vieja de todas"
    p.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    mem = _FalsaMemoria([])
    bloques = fuentes.memoria("trufa", mem)
    hondos = [t for t, a in bloques if a == anillos.HONDO]
    assert any("trufa" in t for t in hondos)


def test_extracto_sin_claves_devuelve_vacio():
    assert fuentes._extracto("linea uno\nlinea dos", "a el de") == ""


def test_proyecto_devuelve_brief_en_la_orilla():
    obtener = lambda nombre: ({"nombre": "calipso", "ruta": "/tmp/x"}
                              if nombre == "calipso" else None)
    brief = lambda raiz: f"brief de {raiz}"
    bloques = fuentes.proyecto("calipso que rutas tiene", obtener, brief)
    assert bloques == [("proyecto calipso:\nbrief de /tmp/x", anillos.ORILLA)]


def test_proyecto_desconocido_levanta():
    with pytest.raises(ValueError):
        fuentes.proyecto("inexistente", lambda n: None, lambda r: "")
