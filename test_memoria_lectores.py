"""Los dos lectores de la memoria episodica presentan con procedencia y
cortan DESPUES de presentar (spec 2026-09-11, seccion 2 y 5): el system del
turno (`_build_context` -> `context_sections`) y la fuente `memoria` del
abismo (`fuentes.memoria`), esta bajo el techo del bloque (`etiquetar`)."""
from __future__ import annotations

import calipso.server as srv
from calipso import chronology, memoria_procedencia as mp, prompt_compiler
from calipso.abismo import anillos, consulta, fuentes

META = {"ts": "2026-09-10T20:58:05", "route": "local", "kind": "chat"}
BASURA = "Pedro pregunto: /local\nCalipso respondio: hola"
NO_SABER = ("Pedro pregunto: /local quien me presto el libro rosa?\n"
            "Calipso respondio: Entiendo. No tengo registros de quien te presto un libro.")


def _par(i: int) -> str:
    return f"Pedro pregunto: pregunta {i}\nCalipso respondio: respuesta {i}"


class _MemoriaConHits:
    def __init__(self, hits, core=""):
        self._hits, self._core = hits, core
        self.pedido = None

    def recall(self, query, n=5, ambitos=None):
        self.pedido = {"query": query, "n": n}
        return self._hits[:n]

    def load_core(self):
        return self._core


def _hit(texto, score, meta=META):
    return {"text": texto, "meta": meta, "score": score, "scope": "global"}


# --- context_sections -------------------------------------------------------

def test_context_sections_pega_los_recuerdos_ya_presentados_sin_score():
    presentado = mp.presentar(_par(1), META, variante="A")
    secciones = prompt_compiler.context_sections(
        "Eres Calipso.", recalled=[{"text": presentado, "score": 0.91, "meta": META}])
    cuerpo = dict(secciones)["Recuerdos relevantes"]
    assert cuerpo == presentado
    assert "0.91" not in cuerpo and "Pedro pregunto:" not in cuerpo
    assert cuerpo.startswith("- Pedro dijo (2026-09-10): pregunta 1\n  Calipso contesto (local, 2026-09-10): respuesta 1")


def test_context_sections_sin_recuerdos_no_arma_la_seccion():
    secciones = prompt_compiler.context_sections("Eres Calipso.", recalled=[])
    assert "Recuerdos relevantes" not in dict(secciones)


# --- _build_context ---------------------------------------------------------

def test_build_context_presenta_salta_la_basura_y_corta_despues(monkeypatch):
    hits = [_hit(BASURA, 0.95), _hit(NO_SABER, 0.9)] + [
        _hit(_par(i), round(0.8 - i * 0.05, 2)) for i in range(7)]
    mem = _MemoriaConHits(hits)
    monkeypatch.setattr(srv, "mem", mem)
    monkeypatch.setattr(srv, "RECALL_MAX", 4)
    monkeypatch.setattr(srv, "RECALL_MIN_SCORE", 0.30)
    monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)
    system = srv._build_context("que libro lei", "runtime", {"type": "chat"})
    assert mem.pedido["n"] == 8
    bloque = system.split("=== Recuerdos relevantes ===\n")[1].split("\n\n===")[0]
    vinetas = [v for v in bloque.split("\n- ") if v]
    # 8 pedidos: la basura se salta, el no-saber degradado y 3 pares -> 4 vinetas
    assert len(vinetas) == 4
    assert "Pedro dijo (2026-09-10): quien me presto el libro rosa?" in bloque
    assert "Calipso no tenia el dato entonces (local, 2026-09-10)." in bloque
    assert "No tengo registros" not in bloque
    assert "pregunta 2" in bloque and "pregunta 3" not in bloque
    assert "Pedro pregunto:" not in system and "/local" not in bloque


def test_build_context_bajo_el_umbral_no_entra_y_sin_hits_no_hay_seccion(monkeypatch):
    mem = _MemoriaConHits([_hit(_par(1), 0.1)])
    monkeypatch.setattr(srv, "mem", mem)
    system = srv._build_context("hola", "runtime", {"type": "chat"})
    assert "Recuerdos relevantes" not in system


def test_build_context_honra_la_variante_del_porton(monkeypatch):
    mem = _MemoriaConHits([_hit(NO_SABER, 0.9)])
    monkeypatch.setattr(srv, "mem", mem)
    monkeypatch.setenv("MEMORIA_PRESENTAR", "B")
    system = srv._build_context("hola", "runtime", {"type": "chat"})
    assert "Pedro dijo (2026-09-10): quien me presto el libro rosa?" in system
    assert "no tenia el dato" not in system
    monkeypatch.setenv("MEMORIA_PRESENTAR", "off")
    system = srv._build_context("hola", "runtime", {"type": "chat"})
    assert f"- (0.9) {NO_SABER}" in system


# --- fuentes.memoria --------------------------------------------------------

def test_fuentes_memoria_presenta_y_corta_a_recall_top_despues(tmp_path, monkeypatch):
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)
    hits = [_hit(BASURA, 0.95)] + [_hit(_par(i), round(0.9 - i * 0.05, 2)) for i in range(11)]
    mem = _MemoriaConHits(hits)
    bloques = fuentes.memoria("que libro lei", mem)
    assert mem.pedido["n"] == fuentes.RECALL_N
    episodico = [t for t, a in bloques if a == anillos.MEDIA_AGUA]
    assert len(episodico) == 1
    texto = episodico[0]
    assert texto.startswith("recuerdos:\n- Pedro dijo (2026-09-10): pregunta 0\n  Calipso contesto (local, 2026-09-10): respuesta 0")
    assert texto.count("- Pedro dijo") == fuentes.RECALL_TOP == 8
    assert "pregunta 7" in texto and "pregunta 8" not in texto
    assert "/local" not in texto and "Pedro pregunto:" not in texto


def test_fuentes_memoria_bajo_el_techo_del_bloque(tmp_path, monkeypatch):
    """Ocho episodios del orquestador (5000+ chars cada uno) presentados con
    los topes: cada vineta queda acotada y el bloque etiquetado cae bajo
    ABISMO_BLOQUE_MAX con las primeras vinetas ENTERAS. El corte sigue
    siendo de `etiquetar`, no de la fuente."""
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)
    largo = "Pedro pregunto: como viene el repo?\nCalipso respondio: " + "x" * 5000
    hits = [_hit(largo, round(0.9 - i * 0.01, 2)) for i in range(8)]
    bloques = fuentes.memoria("como viene el repo", _MemoriaConHits(hits))
    texto = [t for t, a in bloques if a == anillos.MEDIA_AGUA][0]
    vinetas = texto.split("\n- ")[1:]
    assert len(vinetas) == 8
    assert all(len(v) <= mp.TOPE_PREGUNTA + mp.TOPE_RESPUESTA + 80 for v in vinetas)
    etiquetado = consulta.etiquetar("memoria", bloques)
    assert len(etiquetado) <= consulta.ABISMO_BLOQUE_MAX
    primera = "- Pedro dijo (2026-09-10): como viene el repo?\n  Calipso contesto (local, 2026-09-10): " + "x" * 400 + "..."
    assert etiquetado.count(primera) >= 2


def test_fuentes_memoria_tolera_hits_sin_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    monkeypatch.delenv("MEMORIA_PRESENTAR", raising=False)
    bloques = fuentes.memoria("hecho", _MemoriaConHits([{"text": "hecho 0", "score": 0.9, "scope": "global"}]))
    texto = [t for t, a in bloques if a == anillos.MEDIA_AGUA][0]
    assert texto == "recuerdos:\n- Registro (episodio, ?): hecho 0"


def test_fuentes_memoria_off_es_el_bloque_crudo_de_main_sin_score(tmp_path, monkeypatch):
    """La condicion `antes` del porton: con MEMORIA_PRESENTAR=off la fuente
    del abismo pega `- texto` SIN score, como fuentes.py:118 de main (el
    score solo lo pegaba el system). Pasa en main y tiene que seguir
    pasando: es el control de que `off` reproduce el abismo byte a byte."""
    monkeypatch.setattr(chronology, "CALIPSO_HOME", tmp_path)
    monkeypatch.setenv("MEMORIA_PRESENTAR", "off")
    bloques = fuentes.memoria("que libro lei", _MemoriaConHits([_hit(_par(1), 0.9)]))
    texto = [t for t, a in bloques if a == anillos.MEDIA_AGUA][0]
    assert texto == "recuerdos:\n- " + _par(1)
    assert "0.9" not in texto
