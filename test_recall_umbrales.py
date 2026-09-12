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
