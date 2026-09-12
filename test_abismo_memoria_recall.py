"""Memory.recall abierto a consultas por ambito (spec seccion 7), y de una
sola embedding con guardia de count (spec memoria por Ollama 2026-09-12).

Sin chroma: se prueba el ruteo de scopes con dobles que respetan la costura
nueva -- `count()` (la guardia) y `recall(query, n, embedding=None)` (el
vector viene calculado una vez desde Memory) -- y con `EmbedFalsa`, que no
toca la red y anota cada lista de textos que embebio.
"""
from calipso import memoria_embed, memory


class _FalsoScope:
    def __init__(self, name, hits):
        self.name = name
        self._hits = hits
        self.vectores = []

    def count(self):
        return len(self._hits)

    def recall(self, query, n, embedding=None):
        self.vectores.append(embedding)
        return [dict(h, scope=self.name) for h in self._hits]


def _mem_doble():
    m = memory.Memory.__new__(memory.Memory)
    m._embed = memoria_embed.EmbedFalsa()
    m.glob = _FalsoScope("global", [{"text": "g1", "score": 0.9},
                                    {"text": "g2", "score": 0.5}])
    m.project = _FalsoScope("project", [{"text": "p1", "score": 0.7}])
    m._deps = {}
    return m


def test_sin_ambitos_es_la_conducta_de_hoy():
    hits = _mem_doble().recall("q", n=3)
    assert [h["text"] for h in hits] == ["g1", "p1", "g2"]  # fusion por score


def test_ambitos_filtra_por_nombre():
    hits = _mem_doble().recall("q", n=5, ambitos=("global",))
    assert {h["scope"] for h in hits} == {"global"}


def test_ambito_inexistente_devuelve_vacio():
    assert _mem_doble().recall("q", n=5, ambitos=("departamento:taller",)) == []


def test_una_sola_embedding_para_todos_los_ambitos_y_ninguna_sin_episodios():
    m = _mem_doble()
    m.recall("q", n=3)
    assert m._embed.llamadas == [["q"]]
    assert m.glob.vectores == m.project.vectores and len(m.glob.vectores) == 1
    assert m.glob.vectores[0] == m._embed.embed(["q"])[0]
    vacia = _mem_doble()
    vacia.glob = _FalsoScope("global", [])
    vacia.project = _FalsoScope("project", [])
    assert vacia.recall("q", n=3) == [] and vacia._embed.llamadas == []


def test_un_embedder_caido_es_fail_open_con_fila(monkeypatch):
    filas = []
    monkeypatch.setattr(memory.telemetry, "log_event", lambda kind, **k: filas.append({"kind": kind, **k}))

    class _Caido(memoria_embed.EmbedFalsa):
        def embed(self, textos, timeout=None):
            raise memoria_embed.EmbedError("connection refused")
    m = _mem_doble()
    m._embed = _Caido()
    assert m.recall("q", n=3) == []
    assert m.recall_ok is False and m.ultimo_recall_fallo["error"] == "connection refused"
    assert filas == [{"kind": "memoria", "accion": "recall_fallo", "error": "connection refused"}]
    assert m.glob.vectores == []          # no llego a consultar ningun ambito
