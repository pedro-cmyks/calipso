"""Memory.recall abierto a consultas por ambito (spec seccion 7).

Sin chroma ni embeddings: se prueba el ruteo de scopes con dobles, porque
construir Memory real descarga el modelo de embeddings y abre clientes.
"""
from calipso import memory


class _FalsoScope:
    def __init__(self, name, hits):
        self.name = name
        self._hits = hits

    def recall(self, query, n):
        return [dict(h, scope=self.name) for h in self._hits]


def _mem_doble():
    m = memory.Memory.__new__(memory.Memory)
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
