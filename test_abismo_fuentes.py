"""Las fuentes del abismo devuelven sub-bloques (texto, anillo) -- spec 6-7."""
import json

from calipso import chats
from calipso.abismo import anillos, fuentes


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


def test_extracto_sin_claves_devuelve_vacio():
    assert fuentes._extracto("linea uno\nlinea dos", "a el de") == ""
