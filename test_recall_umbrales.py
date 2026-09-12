"""Los umbrales del recall se re-miden, no se heredan (spec memoria por Ollama
2026-09-12, seccion 3): los dos numeros quedan PROVISORIOS y anotados con el
banco en el fuente, y tienen vuelta atras por env
(`CALIPSO_RECALL_MIN_SCORE`, con el viejo `CALIPSO_RECALL_MIN` como alias, y
`CALIPSO_RECALL_UMBRAL`); un env roto cae al default."""
from __future__ import annotations

import pathlib

from calipso import memoria_procedencia as mp

RAIZ = pathlib.Path(__file__).resolve().parent


def test_umbral_por_env_manda_el_nombre_luego_el_alias_luego_el_default(monkeypatch):
    monkeypatch.delenv("X_NUEVO", raising=False)
    monkeypatch.delenv("X_VIEJO", raising=False)
    assert mp.umbral_por_env("X_NUEVO", 0.3, alias="X_VIEJO") == 0.3
    monkeypatch.setenv("X_VIEJO", "0.25")
    assert mp.umbral_por_env("X_NUEVO", 0.3, alias="X_VIEJO") == 0.25
    monkeypatch.setenv("X_NUEVO", "0.55")
    assert mp.umbral_por_env("X_NUEVO", 0.3, alias="X_VIEJO") == 0.55
    monkeypatch.setenv("X_NUEVO", "no-es-numero")
    assert mp.umbral_por_env("X_NUEVO", 0.3, alias="X_VIEJO") == 0.3
    monkeypatch.setenv("X_NUEVO", "")
    assert mp.umbral_por_env("X_NUEVO", 0.3) == 0.3


def test_los_dos_umbrales_estan_marcados_provisorios_y_atados_al_banco():
    server = (RAIZ / "calipso" / "server.py").read_text(encoding="utf-8")
    fuentes = (RAIZ / "calipso" / "abismo" / "fuentes.py").read_text(encoding="utf-8")
    i = server.index("RECALL_MIN_SCORE = memoria_procedencia.umbral_por_env(")
    assert "PROVISORIO" in server[i - 900:i] and "recall_banco" in server[i - 900:i]
    assert '"CALIPSO_RECALL_MIN_SCORE"' in server[i:i + 200] and 'alias="CALIPSO_RECALL_MIN"' in server[i:i + 200]
    j = fuentes.index("RECALL_UMBRAL = memoria_procedencia.umbral_por_env(")
    assert "PROVISORIO" in fuentes[j - 900:j] and "recall_banco" in fuentes[j - 900:j]
    assert '"CALIPSO_RECALL_UMBRAL"' in fuentes[j:j + 120]


def test_los_umbrales_vigentes_son_numeros_en_rango():
    import calipso.server as srv
    from calipso.abismo import fuentes
    assert 0.0 < srv.RECALL_MIN_SCORE < 1.0 and 0.0 < fuentes.RECALL_UMBRAL < 1.0


# --- el ruido intra-corpus del banco (ola de fix del cierre, punto 7) -------------

def _banco():
    """`experimentos/recall_banco.py` importado por ruta, sin sus efectos sobre
    el entorno de la suite: al importar quita CALIPSO_EMBED_FALSA (el banco
    embebe de verdad) y aca se restaura. No toca Ollama: solo el calculo."""
    import importlib.util
    import os
    guardado = os.environ.get("CALIPSO_EMBED_FALSA")
    try:
        spec = importlib.util.spec_from_file_location("recall_banco", RAIZ / "experimentos" / "recall_banco.py")
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
    finally:
        if guardado is not None:
            os.environ["CALIPSO_EMBED_FALSA"] = guardado
    return modulo


def _fila(cond, consulta, topico, tipo, top):
    return {"condicion": cond, "consulta": consulta, "topico": topico, "tipo": tipo,
            "top": [{"id": f"d{i}", "topico": t, "origen": "fixture", "score": s} for i, (t, s) in enumerate(top)],
            "mejor_correcto": None, "acierto1": top[0][0] == topico, "acierto4": any(t == topico for t, _ in top),
            "s_docs": 1.0, "s_consultas": 0.5, "n_docs": 4}


def test_el_ruido_intra_corpus_es_el_max_de_otro_topico_en_el_top4_de_las_positivas():
    """El margen del banco se mide contra temas AUSENTES (las negativas); el
    ruido de siempre es OTRO episodio del mismo corpus. Por condicion: cuantos
    hits de otro topico hay en el top-4 de las positivas (literal, parafrasis
    y reales), el max de sus scores y cuantos pasan el umbral sugerido y los
    vigentes (0.476 turno, 0.44 abismo, 0.30 el viejo de MiniLM)."""
    rb = _banco()
    filas = [
        _fila("c", "a/literal", "a", "literal", [("a", 0.9), ("b", 0.5), ("a", 0.45), ("c", 0.2)]),
        _fila("c", "a/pregunta", "a", "parafrasis_pregunta", [("b", 0.7), ("a", 0.6), ("c", 0.31), ("a", 0.1)]),
        _fila("c", "neg/x", None, "negativa", [("a", 0.8), ("b", 0.8), ("c", 0.8), ("a", 0.8)]),  # no cuenta
        _fila("c", "real/r1/contenido", "real/r1", "real_contenido", [("real/r1", 0.9), ("a", 0.48), ("b", 0.2), ("c", 0.1)]),
    ]
    r = rb.ruido_intra_corpus(filas)["c"]
    assert r["n"] == 7 and r["max"] == 0.7
    assert r["pasan"] == {"0.476": 3, "0.44": 3, "0.30": 4}       # 0.5, 0.7, 0.48 / idem / mas 0.31
    assert r["scores"] == sorted(r["scores"], reverse=True)
    res = rb.resumen(filas)["c"]
    assert res["ruido"]["n"] == 7 and res["ruido"]["max"] == 0.7
    assert res["umbral_sugerido"] == 0.85 and res["ruido"]["pasan_sugerido"] == 0   # (0.9 + 0.8) / 2; nada llega
    md = rb.informe(filas)
    assert "## Ruido intra-corpus" in md and "| c | 7 | 0.7 |" in md


def test_el_ruido_intra_corpus_de_la_corrida_commiteada():
    """Los numeros del JSONL commiteado (corrida 2026-09-12 13:06): 63 hits
    de otro topico en el top-4 de las positivas de `bge-m3:pregunta+150`, 22
    pasan 0.476; MiniLM con su 0.30 viejo dejaba pasar 45 de 63."""
    import json
    rb = _banco()
    filas = [json.loads(l) for l in (RAIZ / "experimentos" / "recall_banco_resultados.jsonl")
             .read_text(encoding="utf-8").splitlines() if l.strip()]
    ruido = rb.ruido_intra_corpus(filas)
    assert ruido["bge-m3:pregunta+150"]["n"] == 63 and ruido["bge-m3:pregunta+150"]["max"] == 0.6961
    assert ruido["bge-m3:pregunta+150"]["pasan"]["0.476"] == 22
    assert ruido["minilm"]["n"] == 63 and ruido["minilm"]["pasan"]["0.30"] == 45
    res = rb.resumen(filas)
    assert res["bge-m3:pregunta+150"]["ruido"]["pasan_sugerido"] == 22      # el sugerido ES 0.476
    assert res["minilm"]["ruido"]["pasan_sugerido"] == 26                   # 0.374
