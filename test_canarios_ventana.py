"""La ventana (spec 2026-09-11, seccion 2.3): el presupuesto con el
template de Ollama, el recorte en orden con los intocables (tests que
fallan si los toca), `no_cabe`, el truncado por pasada, y el tokenizador
real desde el GGUF con su fallback."""
from __future__ import annotations

import os
import pathlib
import statistics


import pytest

from calipso import canarios as c
from calipso import prompt_compiler, tokenizador

# un contador inyectado y previsible: 1 token por caracter
POR_CHAR = len

SECCIONES = [
    ("Sistema", "S" * 100),
    ("Memoria nucleo", "M" * 100),
    ("Contrato interno", "C" * 100),
    ("Recuerdos relevantes", "- Pedro dijo (2026-08-20): a" + "\n  Calipso contesto (local, 2026-08-20): b"
                             + "\n- Pedro dijo (2026-08-21): c" + "\n- Registro (goal, 2026-08-22): d"),
    ("Repo", "R" * 100),
    ("Proyectos", "P" * 50),
    ("Meta activa", "=== Meta activa ===\nG" * 3),
    ("Economia", "E" * 50),
    ("Estado operativo", "=== Estado real de Calipso ===\nO" * 3),
    ("Adjuntos del turno", "A" * 200),
    ("Departamento en foco", "D" * 50),
    ("Resultados web para: x", "W" * 100),
    ("Lo que subio del abismo (fuente: chats)", "[anillo 2]\nB1" * 20),
    ("Lo que subio del abismo (fuente: memoria)", "[anillo 3]\nB2" * 20),
]
HISTORIAL = [{"role": "user", "content": "u1"}, {"role": "assistant", "content": "a1"},
             {"role": "user", "content": "u2"}, {"role": "assistant", "content": "a2"},
             {"role": "user", "content": "u3"}]
INTOCABLES = ("Sistema", "Memoria nucleo", "Contrato interno", "Proyectos", "Meta activa",
              "Economia", "Estado operativo", "Adjuntos del turno", "Departamento en foco")


def _titulos(secciones):
    return [t for t, _ in secciones]


# --- presupuesto ------------------------------------------------------------

def test_el_presupuesto_suma_el_template_de_ollama_por_mensaje_y_el_cierre():
    secs = [("Sistema", "hola")]
    render = prompt_compiler.render_context(secs)
    esperado = (len(render) + 5) + (len("u1") + 5) + (len("a1") + 5) + (len("msg") + 5) + 3
    assert c.presupuesto(secs, HISTORIAL[:2], "msg", contar=POR_CHAR) == esperado
    # sin contador: el fallback de 3.3 chars/token
    assert c.presupuesto(secs, [], "x" * 33) == c.contar_fallback(render) + 5 + 10 + 5 + 3


# --- recorte ----------------------------------------------------------------

def test_sin_apuro_no_se_recorta_nada_y_las_secciones_vuelven_iguales():
    secs, hist, info = c.recortar(SECCIONES, HISTORIAL, "m", num_ctx=10_000, contar=POR_CHAR)
    assert secs == SECCIONES and hist == HISTORIAL
    assert info["recorte"] == [] and info["cabe"] is True and info["no_cabe"] is False
    assert info["estimado"] == info["estimado_final"]


def test_el_recorte_va_en_orden_historial_recuerdos_repo_web_bloque_viejo():
    total = c.presupuesto(SECCIONES, HISTORIAL, "m", contar=POR_CHAR)
    # justo por debajo del total: alcanza con sacar dos mensajes viejos
    secs, hist, info = c.recortar(SECCIONES, HISTORIAL, "m", num_ctx=total - 1, contar=POR_CHAR)
    assert info["recorte"] == ["historial:2"] and hist == HISTORIAL[2:]
    # el techo mas abajo: se agota el historial, despues los recuerdos de a
    # UNA vineta (la ultima, la de menor score), despues Repo, web, y el
    # bloque MAS VIEJO; el de esta pasada (el ultimo) no se toca
    # (1351 es lo que queda con todo lo volatil afuera: justo cabe)
    secs, hist, info = c.recortar(SECCIONES, HISTORIAL, "m", num_ctx=1351, contar=POR_CHAR)
    assert hist == []
    assert info["recorte"][:3] == ["historial:2", "historial:2", "historial:1"]
    assert info["recorte"].count("recuerdo:1") == 3       # tres vinetas: se agoto la seccion
    assert "Recuerdos relevantes" not in _titulos(secs)
    assert info["recorte"][-3:] == ["repo", "web", "bloque:1"]
    assert "Repo" not in _titulos(secs) and "Resultados web para: x" not in _titulos(secs)
    assert _titulos(secs)[-1] == "Lo que subio del abismo (fuente: memoria)"
    assert "Lo que subio del abismo (fuente: chats)" not in _titulos(secs)
    assert info["cabe"] is True and info["no_cabe"] is False


def test_las_vinetas_se_recortan_de_a_una_desde_la_de_menor_score():
    secs = [("Sistema", "S"), ("Recuerdos relevantes", SECCIONES[3][1])]
    base = c.presupuesto(secs, [], "m", contar=POR_CHAR)
    secs2, _, info = c.recortar(secs, [], "m", num_ctx=base - 1, contar=POR_CHAR)
    assert info["recorte"] == ["recuerdo:1"]
    assert secs2[1][1] == ("- Pedro dijo (2026-08-20): a\n  Calipso contesto (local, 2026-08-20): b"
                           "\n- Pedro dijo (2026-08-21): c")


@pytest.mark.parametrize("intocable", INTOCABLES)
def test_los_intocables_no_se_tocan_ni_cuando_no_cabe(intocable):
    """Invariante 8: el system base, el contrato, la memoria nucleo, el
    Estado real, el mensaje y los adjuntos sobreviven a un recorte que
    agota todo lo volatil. Un test por seccion: falla si el recorte la
    toca."""
    secs, hist, info = c.recortar(SECCIONES, HISTORIAL, "mensaje de Pedro", num_ctx=10, contar=POR_CHAR)
    assert info["no_cabe"] is True and info["cabe"] is False
    assert dict(secs)[intocable] == dict(SECCIONES)[intocable]


def test_el_mensaje_de_pedro_y_el_ultimo_bloque_no_se_tocan_y_no_cabe_queda_anotado():
    secs, hist, info = c.recortar(SECCIONES, HISTORIAL, "mensaje de Pedro", num_ctx=10, contar=POR_CHAR)
    assert hist == []
    assert _titulos(secs) == list(INTOCABLES) + ["Lo que subio del abismo (fuente: memoria)"]
    assert info["recorte"][-1] == "bloque:1" and info["estimado_final"] > 10
    # el mensaje no es parte de lo recortable: `recortar` ni lo devuelve
    assert c.presupuesto(secs, hist, "mensaje de Pedro", contar=POR_CHAR) == info["estimado_final"]


def test_sin_techo_no_se_recorta_y_cabe_es_none():
    secs, hist, info = c.recortar(SECCIONES, HISTORIAL, "m", num_ctx=None, contar=POR_CHAR)
    assert secs == SECCIONES and hist == HISTORIAL and info["cabe"] is None and info["recorte"] == []


# --- truncado por pasada ------------------------------------------------------

def test_truncado_por_pasada():
    assert c.truncado(7000, 7000, 8192) is False
    assert c.truncado(9000, 8000, 8192) is True          # estimado > num_ctx
    assert c.truncado(7000, 7800, 8192) is True          # evaluado >= 0.95 * num_ctx
    assert c.truncado(7000, 5000, 8192) is True          # evaluado < 0.85 * estimado
    assert c.truncado(7000, None, 8192) == "sin medicion"
    # api: sin techo NO se juzga (None), ni siquiera con un evaluado muy
    # menor al estimado: lo cuenta el tokenizador del proveedor, no el de
    # qwen, y la tercera regla seria ruido (decision 7)
    assert c.truncado(100, 100, None) is None
    assert c.truncado(1000, 10, None) is None
    assert c.truncado(100, None, None) == "sin medicion"    # suscripcion: no expone el prompt
    # la ventana de antes fallo (fila con estimado None, fail-open): no se juzga
    assert c.truncado(None, 100, 8192) is None
    assert c.truncado(None, None, 8192) == "sin medicion"


# --- el interruptor ------------------------------------------------------------

def test_canarios_activos_lee_el_env_por_llamada(monkeypatch):
    """CALIPSO_CANARIOS=off apaga los canarios en caliente (ola de fix del
    cierre, punto 4); ausente, vacio o cualquier otra cosa: prendidos."""
    monkeypatch.delenv("CALIPSO_CANARIOS", raising=False)
    assert c.canarios_activos() is True
    monkeypatch.setenv("CALIPSO_CANARIOS", "off")
    assert c.canarios_activos() is False
    monkeypatch.setenv("CALIPSO_CANARIOS", "OFF")
    assert c.canarios_activos() is False
    monkeypatch.setenv("CALIPSO_CANARIOS", "on")
    assert c.canarios_activos() is True
    monkeypatch.setenv("CALIPSO_CANARIOS", "")
    assert c.canarios_activos() is True


def test_con_los_canarios_apagados_la_ventana_de_antes_estima_sin_recortar(monkeypatch):
    import calipso.server as srv
    monkeypatch.setenv("CALIPSO_CANARIOS", "off")
    monkeypatch.setattr(srv, "CHAT_NUM_CTX", 5)
    monkeypatch.setattr(tokenizador, "cargar", lambda nombre: None)
    historial = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "hola Pedro"}]
    secciones, hist, fila = srv._ventana_antes(SECCIONES, historial, "hola", "local", None, 1)
    assert fila["apagado"] is True and fila["num_ctx"] is None and fila["recorte"] == []
    assert fila["cabe"] is None and fila["estimado"] > 5
    assert secciones == SECCIONES and hist == historial
    monkeypatch.delenv("CALIPSO_CANARIOS")
    _, hist, fila = srv._ventana_antes(SECCIONES, historial, "hola", "local", None, 1)
    assert "apagado" not in fila and fila["num_ctx"] == 5 and hist == []


# --- el tokenizador -----------------------------------------------------------

def test_sin_gguf_el_contador_es_el_fallback_de_3_3(monkeypatch, tmp_path):
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-hay"))
    monkeypatch.setattr(tokenizador, "_cache", {})
    contar, origen = tokenizador.contador("qwen2.5:7b")
    assert origen == "fallback" and contar("x" * 33) == 10 and contar("") == 0
    assert tokenizador.blob_del_modelo("qwen2.5:7b") is None


def test_el_fallback_del_tokenizador_es_el_de_canarios_y_sigue_a_umbrales(monkeypatch, tmp_path):
    """El 3.3 vive en UMBRALES (canarios) y en ningun otro lado: el contador
    que el server usa sin GGUF es la MISMA funcion que `presupuesto` usa
    sin contador, y recalibrar UMBRALES mueve a los dos (fix round 1)."""
    assert tokenizador.contar_fallback is c.contar_fallback
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path / "no-hay"))
    monkeypatch.setattr(tokenizador, "_cache", {})
    contar, origen = tokenizador.contador("qwen2.5:7b")
    assert origen == "fallback" and contar is c.contar_fallback
    monkeypatch.setitem(c.UMBRALES, "fallback_chars_por_token", 11)
    assert contar("x" * 33) == 3
    secs = [("Sistema", "S" * 22)]
    assert c.presupuesto(secs, [], "x" * 33) == c.presupuesto(secs, [], "x" * 33, contar=contar)


def test_el_manifest_de_ollama_lleva_al_blob_del_modelo(monkeypatch, tmp_path):
    raiz = tmp_path / "manifests" / "registry.ollama.ai" / "library" / "qwen2.5"
    raiz.mkdir(parents=True)
    (tmp_path / "blobs").mkdir()
    (tmp_path / "blobs" / "sha256-abc").write_bytes(b"GGUF")
    (raiz / "7b").write_text('{"layers": [{"mediaType": "application/vnd.ollama.image.template", "digest": "sha256:zzz"},'
                             '{"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:abc"}]}')
    monkeypatch.setenv("OLLAMA_MODELS", str(tmp_path))
    assert tokenizador.blob_del_modelo("qwen2.5:7b") == tmp_path / "blobs" / "sha256-abc"
    assert tokenizador.blob_del_modelo("qwen2.5:3b") is None       # sin manifest


_BLOB = tokenizador.blob_del_modelo("qwen2.5:7b")


@pytest.mark.skipif(_BLOB is None, reason="sin el GGUF de qwen2.5:7b en esta maquina")
def test_el_tokenizador_real_reproduce_los_ids_de_qwen_y_se_cachea_en_el_home(monkeypatch, tmp_path):
    """No llama a Ollama: lee el header del GGUF (11 MB de 4.6 GB) y escribe
    el tokenizer.json bajo CALIPSO_HOME (el de la suite, temporal)."""
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path))
    monkeypatch.setattr(tokenizador, "_cache", {})
    contar, origen = tokenizador.contador("qwen2.5:7b")
    assert origen == "real"
    cache = tmp_path / "tokenizador" / (_BLOB.name + ".json")
    assert cache.is_file() and cache.stat().st_size > 5_000_000
    tok = tokenizador.cargar("qwen2.5:7b")
    assert tok.encode("<|im_start|>system\nhola<|im_end|>\n", add_special_tokens=False).ids == \
        [151644, 8948, 198, 71, 7924, 151645, 198]
    assert contar("<|im_start|>system\nhola<|im_end|>\n") == 7
    for s in ("hola que tal, como andas", "2026-08-14 | 120 dolares", "Mariana Quintero me presto el libro"):
        assert tok.decode(tok.encode(s).ids) == s
    # calibracion sobre 3+ prompts reales: min, mediana y max de chars/token
    variantes = pathlib.Path(__file__).parent / "experimentos" / "variantes"
    textos = [(variantes / n).read_text(encoding="utf-8")
              for n in ("system-podada.txt", "system-actual.txt", "contrato-existe-senales.txt")]
    ratios = sorted(len(t) / contar(t) for t in textos)
    assert 3.0 <= ratios[0] and statistics.median(ratios) <= 3.8 and ratios[-1] <= 4.2, ratios
    # el caso que el fallback subestima: un adjunto con forma de codigo
    codigo = "x = 1\n" * 2000
    assert len(codigo) / contar(codigo) < 2.0


def _ollama_falso(tmp_path):
    """Un manifest y un blob de mentira para `blob_del_modelo`; la metadata
    la inyecta cada test (un BPE de tres tokens con la forma de qwen2)."""
    raiz = tmp_path / "ollama" / "manifests" / "registry.ollama.ai" / "library" / "qwen2.5"
    raiz.mkdir(parents=True)
    (tmp_path / "ollama" / "blobs").mkdir()
    (tmp_path / "ollama" / "blobs" / "sha256-abc").write_bytes(b"GGUF")
    (raiz / "7b").write_text('{"layers": [{"mediaType": "application/vnd.ollama.image.model", "digest": "sha256:abc"}]}')
    return tmp_path / "ollama"


_KV_CHICO = {"tokenizer.ggml.model": "gpt2", "tokenizer.ggml.pre": "qwen2",
             "tokenizer.ggml.tokens": ["a", "b", "ab", "<|im_end|>"],
             "tokenizer.ggml.merges": ["a b"], "tokenizer.ggml.token_type": [1, 1, 1, 3]}


def test_un_cache_truncado_se_borra_y_se_regenera_una_vez(monkeypatch, tmp_path):
    """Ola de fix del cierre (punto 8): un tokenizer.json roto (un corte a
    mitad de escritura) hacia caer al fallback para siempre. Ahora el cache
    se escribe a .json.tmp + os.replace, y si `Tokenizer.from_file` falla
    con el cache presente se borra y se regenera UNA vez."""
    pytest.importorskip("tokenizers")
    monkeypatch.setenv("OLLAMA_MODELS", str(_ollama_falso(tmp_path)))
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(tokenizador, "_cache", {})
    lecturas = []
    monkeypatch.setattr(tokenizador, "leer_metadata", lambda blob: lecturas.append(blob) or (3, _KV_CHICO))
    cache = tmp_path / "home" / "tokenizador" / "sha256-abc.json"
    cache.parent.mkdir(parents=True)
    cache.write_text('{"version": "1.0", "truncated', encoding="utf-8")
    contar, origen = tokenizador.contador("qwen2.5:7b")
    assert origen == "real" and contar("ab") == 1 and contar("ba") == 2
    assert len(lecturas) == 1 and cache.is_file() and cache.stat().st_size > 100
    assert not list(cache.parent.glob("*.tmp"))
    # con el cache sano no se vuelve a leer el GGUF
    monkeypatch.setattr(tokenizador, "_cache", {})
    assert tokenizador.contador("qwen2.5:7b")[1] == "real" and len(lecturas) == 1


def test_el_cache_del_tokenizador_se_escribe_atomico(monkeypatch, tmp_path):
    pytest.importorskip("tokenizers")
    monkeypatch.setenv("OLLAMA_MODELS", str(_ollama_falso(tmp_path)))
    monkeypatch.setenv("CALIPSO_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(tokenizador, "_cache", {})
    monkeypatch.setattr(tokenizador, "leer_metadata", lambda blob: (3, _KV_CHICO))
    escritos = []
    real = os.replace

    def espia(origen, destino):
        escritos.append((pathlib.Path(origen).name, pathlib.Path(destino).name))
        real(origen, destino)
    monkeypatch.setattr(tokenizador.os, "replace", espia)
    assert tokenizador.contador("qwen2.5:7b")[1] == "real"
    assert escritos == [("sha256-abc.json.tmp", "sha256-abc.json")]
