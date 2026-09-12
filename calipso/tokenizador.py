"""El tokenizador del modelo local, armado desde el GGUF de Ollama (spec
2026-09-11, seccion 2.3): `tokenizers` esta en el venv y el header del GGUF
trae vocab, merges y tipos de token; el `tokenizer.json` se genera UNA vez
por blob (clave: el digest del blob, que ya esta en su nombre) bajo
`CALIPSO_HOME/tokenizador/` y se regenera si cambia el modelo. Fallback
por chars/token (`canarios.contar_fallback`, el numero vive SOLO en
`canarios.UMBRALES["fallback_chars_por_token"]`; medido: mediana 3.50 sobre
systems, contratos e historial reales; 4.1 en respuestas; 2.96 con chino;
1.2 en adjuntos de codigo, que es donde el fallback subestima) cuando no
hay GGUF, el `pre` no es `qwen2` o la libreria falla.

Toca el disco (lee `~/.ollama`, escribe el cache): por eso vive aparte de
`canarios.py`, que es puro. El home se resuelve POR LLAMADA (`home()`),
nunca en una constante de modulo (test_aislacion_home.py).

Verificado el 2026-09-11 con qwen2.5:7b: gguf v3, pre=qwen2, 152064 tokens,
151387 merges; los ids coinciden con los de Qwen2.5 (<|im_start|>=151644,
<|im_end|>=151645, system=8948, user=872) solo si los 22 tokens de tipo
CONTROL (3) y USER_DEFINED (4) se registran como AddedToken(special=True):
sin eso `<|im_start|>` sale en 6 piezas. Cargar el json: 235 ms; encode de
9.6k tokens: 10 ms. Sin el modulo `gguf` (no esta en el venv): el header se
parsea a mano.
"""
from __future__ import annotations

import json
import os
import pathlib
import struct
import threading

# el fallback es el MISMO de `canarios.presupuesto` (una sola definicion,
# un solo numero en UMBRALES); canarios es puro y no importa este modulo
from calipso.canarios import contar_fallback

_TIPOS = {0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i", 6: "f", 7: "?", 10: "Q", 11: "q", 12: "d"}
_PATRON_QWEN2 = (r"(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\p{L}\p{N}]?\p{L}+|\p{N}| ?[^\s\p{L}\p{N}]+[\r\n]*|"
                 r"\s*[\r\n]+|\s+(?!\S)|\s+")
_candado = threading.Lock()
_cache: dict[str, object] = {}


def home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CALIPSO_HOME", os.path.expanduser("~/.calipso")))


def modelos_ollama() -> pathlib.Path:
    return pathlib.Path(os.environ.get("OLLAMA_MODELS", os.path.expanduser("~/.ollama/models")))


def blob_del_modelo(nombre: str) -> pathlib.Path | None:
    """`qwen2.5:7b` -> manifests/registry.ollama.ai/library/qwen2.5/7b ->
    la capa `application/vnd.ollama.image.model` -> blobs/sha256-<hex>.
    None si falta cualquier pieza (Ollama no instalado, modelo no bajado)."""
    ruta, _, tag = nombre.partition(":")
    partes = ruta.split("/")
    if len(partes) == 1:
        partes = ["library", partes[0]]
    manifiesto = modelos_ollama() / "manifests" / "registry.ollama.ai" / pathlib.Path(*partes) / (tag or "latest")
    try:
        capas = json.loads(manifiesto.read_text(encoding="utf-8")).get("layers", [])
    except (OSError, ValueError):
        return None
    for capa in capas:
        if capa.get("mediaType") == "application/vnd.ollama.image.model":
            digest = str(capa.get("digest", "")).replace(":", "-")
            blob = modelos_ollama() / "blobs" / digest
            return blob if blob.is_file() else None
    return None


def leer_metadata(ruta: pathlib.Path) -> tuple[int, dict]:
    """(version, kv) leyendo SOLO el header del GGUF; los tensores no se tocan."""
    with open(ruta, "rb") as f:
        def u(fmt):
            return struct.unpack("<" + fmt, f.read(struct.calcsize(fmt)))[0]

        def cadena():
            return f.read(u("Q")).decode("utf-8", "replace")

        def valor(t):
            if t == 8:
                return cadena()
            if t == 9:
                sub, n = u("I"), u("Q")
                return [valor(sub) for _ in range(n)]
            return u(_TIPOS[t])
        if f.read(4) != b"GGUF":
            raise ValueError(f"{ruta} no es GGUF")
        version, _n_tensores, n_kv = u("I"), u("Q"), u("Q")
        return version, {cadena(): valor(u("I")) for _ in range(n_kv)}


def armar(kv: dict):
    """Byte-level BPE de Qwen2 (pre == 'qwen2') con los tokens de control
    registrados. ValueError si el modelo local es de otra familia: ese es
    el caso real de fallback (no la ausencia del GGUF)."""
    from tokenizers import AddedToken, Regex, Tokenizer, decoders, models, pre_tokenizers
    if kv.get("tokenizer.ggml.model") != "gpt2" or kv.get("tokenizer.ggml.pre") != "qwen2":
        raise ValueError(f"tokenizador no soportado: model={kv.get('tokenizer.ggml.model')!r} "
                         f"pre={kv.get('tokenizer.ggml.pre')!r}")
    tokens = kv["tokenizer.ggml.tokens"]
    vocab = {t: i for i, t in enumerate(tokens)}
    merges = [tuple(m.split(" ", 1)) for m in kv["tokenizer.ggml.merges"]]
    tok = Tokenizer(models.BPE(vocab=vocab, merges=merges, byte_fallback=False))
    tok.pre_tokenizer = pre_tokenizers.Sequence([
        pre_tokenizers.Split(Regex(_PATRON_QWEN2), behavior="isolated"),
        pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False)])
    tok.decoder = decoders.ByteLevel()
    tipos = kv["tokenizer.ggml.token_type"]
    tok.add_special_tokens([AddedToken(t, special=True, normalized=False)
                            for t, tipo in zip(tokens, tipos) if tipo in (3, 4)])
    return tok


def _ruta_cache(blob: pathlib.Path) -> pathlib.Path:
    return home() / "tokenizador" / (blob.name + ".json")


def _generar_cache(blob: pathlib.Path, cache: pathlib.Path) -> None:
    """Escribe el tokenizer.json ATOMICO (.json.tmp + os.replace): un corte
    a mitad de escritura no deja un cache truncado que despues no carga."""
    _, kv = leer_metadata(blob)
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".json.tmp")
    armar(kv).save(str(tmp))
    os.replace(tmp, cache)


def cargar(nombre: str):
    """El Tokenizer del modelo `nombre`, desde el cache o generado desde el
    GGUF; None si no se puede (y entonces se usa el fallback). Si el cache
    esta pero no carga (truncado, de otra version), se borra y se regenera
    UNA vez antes de caer al fallback. Una vez por proceso y por modelo,
    bajo candado: se llama desde hilos."""
    with _candado:
        if nombre in _cache:
            return _cache[nombre]
        tok = None
        try:
            from tokenizers import Tokenizer
            blob = blob_del_modelo(nombre)
            if blob is not None:
                cache = _ruta_cache(blob)
                if not cache.is_file():
                    _generar_cache(blob, cache)
                    tok = Tokenizer.from_file(str(cache))
                else:
                    try:
                        tok = Tokenizer.from_file(str(cache))
                    except Exception:      # cache roto: se regenera una vez
                        cache.unlink(missing_ok=True)
                        _generar_cache(blob, cache)
                        tok = Tokenizer.from_file(str(cache))
        except Exception:      # sin tokenizers, GGUF raro, disco: fallback
            tok = None
        _cache[nombre] = tok
        return tok


def contador(nombre: str):
    """(contar, "real" | "fallback"): la funcion str -> tokens que usa el
    presupuesto, y de donde salio (va a la fila de la ventana)."""
    tok = cargar(nombre)
    if tok is None:
        return contar_fallback, "fallback"
    return (lambda texto: len(tok.encode(texto or "", add_special_tokens=False).ids)), "real"
