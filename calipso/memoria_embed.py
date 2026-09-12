"""La funcion de embeddings de la memoria episodica: `bge-m3` en Ollama por
`POST /api/embed`, sin torch en el proceso (spec memoria por Ollama
2026-09-12, seccion 2).

Puro salvo el POST a loopback, que vive en la funcion de modulo
`_post_embed` (el canario de la aduana arma su clave con nombres de funcion,
no de clase: `calipso/memoria_embed.py:_post_embed` esta en EXCEPCIONES).

`OllamaEmbed` es la EF que chroma persiste en el esquema de la coleccion
(`name() = "calipso_ollama"`, `get_config() = {url, model, dims}`) y
reconstruye con `build_from_config` al crear la coleccion y DOS veces por
cada upsert/update (sondeado sobre chromadb 1.5.9): por eso es PURA al
construirse (ruling 8.2): sin red, sin disco, dims fijas por config. Nadie
deja que chroma la llame para embeber: `Scope.remember` y el reindex embeben
por afuera con `embeber(...)` y pasan `embeddings=` explicitos; `recall`
consulta con `query_embeddings`. Asi los timeouts van por uso (ruling 8.7):
recall 10 s (el turno sigue sin recuerdos), remember y reindex 120 s por
lote; y los lotes son por tamano (<= LOTE_CHARS por request; un documento
largo va solo), no por cantidad.

`EmbedFalsa` (hash determinista a EMBED_DIMS, sin red) es la de la suite:
`memory.Memory()` la elige con `CALIPSO_EMBED_FALSA=1`, que conftest.py fija
antes de importar calipso (ruling 8.10). Es HIJA de `OllamaEmbed` y comparte
nombre y config: el esquema persistido en la suite es el mismo que en
produccion, y el fixture generado con la EF real se abre con la falsa sin
conflicto (chroma compara solo `name()`).

Lo que se embebe (ruling 8.5): `texto_para_embedding(doc)` = la pregunta de
Pedro (limpia de gestos) y las primeras 150 palabras de la respuesta, sin las
etiquetas del par. MiniLM veia 128 tokens (la pregunta y el arranque de la
respuesta); el par entero de 2-6k chars queda dominado por la respuesta y
cuesta 2-5 s. El documento guardado no cambia.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
import warnings

import numpy as np
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from chromadb.errors import NotFoundError
from chromadb.utils.embedding_functions import register_embedding_function

from calipso import carga
from calipso import config as calipso_config
from calipso import memoria_procedencia

TIMEOUT_RECALL_S = 10.0       # el turno sigue sin recuerdos (ruling 8.7)
TIMEOUT_REMEMBER_S = 120.0    # remember y reindex, por lote
LOTE_CHARS = 8000             # lotes por tamano, no por cantidad
PALABRAS_RESPUESTA = 150      # ruling 8.5; el banco 2026-09-12 midio 0 / 150 / par entero (10_000): 150 separa mejor (margen 0.155 contra 0.0849 del par y -0.0036 de la pregunta sola)
PALABRAS_OTRO = 300           # un documento que no es un par (meta, ficha del jefe): fijo, no depende del de arriba


class EmbedError(RuntimeError):
    """Ollama no contesto, contesto otra cosa o con otras dimensiones."""


def embed_tag(nombre: str) -> str:
    """El nombre del modelo saneado para el nombre de la coleccion: sin
    `:latest` y solo `[a-zA-Z0-9._-]` (chroma rechaza `episodic-bge-m3:latest`
    con InvalidArgumentError; sondeado). `bge-m3:latest` -> `bge-m3`."""
    base = nombre[:-len(":latest")] if nombre.endswith(":latest") else nombre
    tag = re.sub(r"[^a-zA-Z0-9._-]+", "-", base).strip("-._")
    return tag or "sin-modelo"


EMBED_TAG = embed_tag(calipso_config.EMBED_MODEL)
COLECCION_VIEJA = "episodic"                  # MiniLM, 384 dims: solo origen del reindex
COLECCION_VIVA = f"episodic-{EMBED_TAG}"      # la que abre Scope


def texto_para_embedding(doc: str, palabras: int | None = None) -> str:
    """Lo que se embebe de un episodio (ruling 8.5). Un par de chat: la
    pregunta limpia de gestos y las primeras `palabras` de la respuesta
    (PALABRAS_RESPUESTA si no viene, leido por llamada: el banco y sus tests
    pueden cambiar el numero), separadas por un salto de linea, sin las
    etiquetas. Otro formato (una meta, una ficha del jefe): sus primeras
    PALABRAS_OTRO palabras, sea cual sea `palabras` (con la variante
    pregunta sola, 0, una meta no puede quedar vacia)."""
    palabras = PALABRAS_RESPUESTA if palabras is None else palabras
    par = memoria_procedencia.partir(doc)
    if par is None:
        palabras_doc = (doc or "").split()
        if len(palabras_doc) <= PALABRAS_OTRO:
            return (doc or "").strip()          # entero, con sus saltos de linea
        return " ".join(palabras_doc[:PALABRAS_OTRO])
    pregunta, respuesta = par
    pregunta = memoria_procedencia.limpiar_gestos(pregunta) or pregunta
    cabeza = " ".join(respuesta.split()[:palabras])
    return f"{pregunta}\n{cabeza}".strip()


def lotes(textos: list[str], max_chars: int | None = None) -> list[list[str]]:
    """Parte `textos` en lotes contiguos de a lo sumo `max_chars` (suma de
    largos; LOTE_CHARS si no viene, leido por llamada para que un test lo
    pueda bajar); un texto mas largo que el tope va solo en su lote. Conserva
    el orden: el llamador alinea las respuestas por posicion."""
    max_chars = LOTE_CHARS if max_chars is None else max_chars
    salida: list[list[str]] = []
    actual: list[str] = []
    largo = 0
    for t in textos:
        if actual and largo + len(t) > max_chars:
            salida.append(actual)
            actual, largo = [], 0
        actual.append(t)
        largo += len(t)
    if actual:
        salida.append(actual)
    return salida


CUERPO_ERROR_CHARS = 300      # cuanto del cuerpo de un error HTTP de Ollama viaja en el EmbedError


def _post_embed(url: str, payload: dict, timeout: float) -> dict:
    """El unico POST del modulo: `{base}/api/embed` por urllib, loopback (no
    cruza la aduana; entrada en EXCEPCIONES del canario). Cualquier fallo
    (conexion, timeout, HTTP, JSON) es EmbedError. Un error HTTP conserva el
    CUERPO que Ollama manda (`{"error": "model 'bge-m3:latest' not found, try
    pulling it first"}`, hasta CUERPO_ERROR_CHARS): `str(HTTPError)` es solo
    "HTTP Error 404: Not Found" y las filas `recall_fallo` / `remember_fallo`
    no decian por que (ola de fix, punto 1)."""
    datos = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=datos, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            cuerpo = e.read()[:CUERPO_ERROR_CHARS].decode("utf-8", errors="replace")
        except Exception:
            cuerpo = ""
        raise EmbedError(f"POST {url}: {e} {cuerpo}".rstrip()) from e
    except Exception as e:
        raise EmbedError(f"POST {url}: {e}") from e


@register_embedding_function
class OllamaEmbed(EmbeddingFunction[Documents]):
    """La EF de produccion. Pura al construirse (ruling 8.2)."""

    def __init__(self, url: str | None = None, model: str | None = None,
                 dims: int | None = None, timeout: float = TIMEOUT_REMEMBER_S) -> None:
        self.url = (url or calipso_config.EMBED_URL).rstrip("/")
        self.model = model or calipso_config.EMBED_MODEL
        self.dims = int(dims or calipso_config.EMBED_DIMS)
        self.timeout = timeout

    def embed(self, textos: list[str], timeout: float | None = None) -> list[list[float]]:
        """Los vectores de `textos`, en orden, por lotes de LOTE_CHARS, con el
        payload pasado por `carga.payload_local` (num_thread y keep_alive por
        nivel: un solo camino a Ollama, invariante 5) y dentro de
        `carga.usando()` (el vigia no descarga a mitad). Una lista vacia
        devuelve [] sin POST (chroma revienta con `ef([])`)."""
        textos = list(textos)
        if not textos:
            return []
        nivel = carga.nivel_reciente()
        salida: list[list[float]] = []
        with carga.usando():
            for lote in lotes(textos):
                payload = carga.payload_local(
                    {"model": self.model, "input": lote, "truncate": True}, nivel,
                    keep_alive=carga.keep_alive_embed(nivel))
                datos = _post_embed(f"{self.url}/api/embed", payload, timeout or self.timeout)
                vectores = datos.get("embeddings") if isinstance(datos, dict) else None
                if not isinstance(vectores, list) or len(vectores) != len(lote):
                    cuantos = len(vectores) if isinstance(vectores, list) else "?"
                    # un 200 con {"error": ...} y sin `embeddings`: el motivo va en el mensaje
                    error = datos.get("error") if isinstance(datos, dict) else None
                    raise EmbedError(f"{self.model}: esperaba {len(lote)} vectores y vinieron {cuantos}"
                                     + (f" (Ollama: {str(error)[:CUERPO_ERROR_CHARS]})" if error else ""))
                for v in vectores:
                    if not isinstance(v, list) or len(v) != self.dims:
                        raise EmbedError(f"{self.model}: vector de {len(v) if isinstance(v, list) else '?'} "
                                         f"dimensiones; la config dice {self.dims}")
                    salida.append([float(x) for x in v])
        return salida

    def __call__(self, input: Documents) -> Embeddings:
        # la firma exacta que chroma valida (self, input); en produccion nadie
        # llega por aca (embeddings explicitos), pero queda para una EF pasada
        # a mano a chroma
        return [np.array(v, dtype=np.float32) for v in self.embed(list(input))]

    @staticmethod
    def name() -> str:
        return "calipso_ollama"

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def get_config(self) -> dict:
        return {"url": self.url, "model": self.model, "dims": self.dims}

    @classmethod
    def build_from_config(cls, config: dict) -> "OllamaEmbed":
        # puro: chroma lo llama al crear la coleccion y dos veces por upsert
        return cls(url=config.get("url"), model=config.get("model"), dims=config.get("dims"))

    @staticmethod
    def validate_config(config: dict) -> None:
        return None

    def validate_config_update(self, old_config: dict, new_config: dict) -> None:
        return None


class EmbedFalsa(OllamaEmbed):
    """La EF de la suite: un vector determinista por hash del texto (sha256
    repetido hasta EMBED_DIMS, normalizado), sin red. Mismo texto, mismo
    vector: consultar con el texto exacto de lo embebido da distancia 0.
    `llamadas` guarda cada lista de textos que se le pidio (los tests cuentan
    embeddings por recall)."""

    def __init__(self, url: str | None = None, model: str | None = None,
                 dims: int | None = None, timeout: float = TIMEOUT_REMEMBER_S) -> None:
        super().__init__(url=url, model=model, dims=dims, timeout=timeout)
        self.llamadas: list[list[str]] = []

    def embed(self, textos: list[str], timeout: float | None = None) -> list[list[float]]:
        textos = list(textos)
        self.llamadas.append(list(textos))
        salida = []
        for t in textos:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            crudo = np.frombuffer((h * (self.dims // len(h) + 1))[: self.dims],
                                  dtype=np.uint8).astype(np.float32)
            salida.append((crudo / np.linalg.norm(crudo)).tolist())
        return salida


def embedder_por_env() -> OllamaEmbed:
    """La EF que `Memory()` construye si no le inyectan una: la falsa con
    `CALIPSO_EMBED_FALSA=1` (la suite), la real si no."""
    if os.environ.get("CALIPSO_EMBED_FALSA") == "1":
        return EmbedFalsa()
    return OllamaEmbed()


def embeber(ef, textos: list[str], timeout: float | None = None) -> list[list[float]]:
    """La unica costura para pedir vectores con timeout por uso: las EFs de
    Calipso tienen `embed(textos, timeout=)`; una EF ajena de chroma (una
    inyectada en `Memory(embed=)`) se llama con `__call__` y se convierte."""
    if hasattr(ef, "embed"):
        return ef.embed(list(textos), timeout=timeout)
    return [[float(x) for x in v] for v in ef(list(textos))]


def ids_de(cliente, nombre: str) -> set[str] | None:
    """Los ids de la coleccion `nombre` del cliente, o None si no existe.
    `get(include=[])` no reconstruye la EF persistida ni importa nada. Sobre
    la vieja `episodic` (EF sentence_transformer persistida) chroma, sin
    torch en el venv, avisa `UserWarning: Could not reconstruct embedding
    function ...` y sigue con la EF en None: se calla aca (saldria en cada
    arranque y en cada /api/memory); cualquier otro aviso pasa."""
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Could not reconstruct embedding function",
                                category=UserWarning)
        try:
            col = cliente.get_collection(nombre, embedding_function=None)
        except NotFoundError:
            return None
        return set(col.get(include=[])["ids"])


def sin_reindexar(cliente) -> int:
    """Cuantos documentos de la vieja `episodic` no estan en `episodic-<tag>`
    (invariante 3: se ve hasta que sea 0). Es EL calculo: lo usan el server
    (`/api/memory`, el arranque) y el reindex (`--vista`, `--embeddings`)."""
    viejos = ids_de(cliente, COLECCION_VIEJA)
    if not viejos:
        return 0
    vivos = ids_de(cliente, COLECCION_VIVA) or set()
    return len(viejos - vivos)
