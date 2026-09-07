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
