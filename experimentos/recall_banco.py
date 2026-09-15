#!/usr/bin/env python3
"""El banco de recall (spec memoria por Ollama 2026-09-12, seccion 3; ruling
8.6): mide SEPARACION, no `hit@4` literal. Lo que habia no media nada: los 16
episodios del fixture son 8 preguntas por 2 pasadas (duplicados) y las
consultas eran la pregunta literal, asi que hit@4 daba ~100% con cualquier
embedder.

El banco: por cada uno de los 8 topicos del fixture, la pregunta literal mas
dos parafrasis escritas a mano (una sobre la pregunta, otra sobre el
CONTENIDO de la respuesta) y 8 consultas negativas (temas ausentes); los
duplicados cuentan como UN acierto (hit@1 por TOPICO); las filas reales del
home entran con consultas escritas a partir de su contenido (`--home` y
`--reales`; es local: no sale nada, y el MD solo muestra ids y numeros de las
reales). Condiciones: `minilm` (la ST en proceso, el par entero como en
produccion, truncado a 128 tokens; importa sentence_transformers solo si
esta: corre ANTES del uninstall) y `bge-m3` por Ollama en tres variantes del
texto embebido: `pregunta` (palabras=0), `pregunta+150` (la de produccion) y
`par` (palabras=10_000: la pregunta limpia + la respuesta ENTERA, sin las
etiquetas; es la forma que `PALABRAS_RESPUESTA = 10_000` aterriza, no el
documento crudo: lo que se mide es lo que se aterrizaria). Metricas por
condicion: hit@1 por topico, hit@4,
la distribucion de scores (aciertos contra negativas; score = coseno = 1 -
distancia de chroma) y el MARGEN = min(score de los aciertos top-1) -
max(score top-1 de las negativas); un umbral sugerido = el punto medio del
margen. Regla de parada: si bge-m3 no iguala el hit@1 por topico de MiniLM o
su margen es negativo, se para y se le dice a Pedro (no se aterriza a ciegas).

El RUIDO INTRA-CORPUS (ola de fix del cierre, punto 7): el margen se mide
contra temas AUSENTES, pero el ruido de siempre es otro episodio del mismo
corpus. Por condicion, `ruido_intra_corpus` toma los hits de OTRO topico en
el top-4 de las positivas (literal, parafrasis y reales), su max y cuantos
pasan el umbral sugerido y los de referencia (0.476 el turno, 0.44 el
abismo, 0.30 el viejo de MiniLM). Se calcula del JSONL (`--informe`, sin
Ollama). En la corrida del 2026-09-12: 63 hits de otro topico en
`bge-m3:pregunta+150`, 22 pasan 0.476 (MiniLM: 45 de 63 pasaban su 0.30):
un umbral por margen no filtra el ruido intra-corpus; los umbrales siguen
PROVISORIOS y se re-miden cuando el corpus crezca.

    python experimentos/recall_banco.py                       # todas las condiciones (Ollama + la ST)
    python experimentos/recall_banco.py --condiciones bge-m3:pregunta+150
    python experimentos/recall_banco.py --home ~/.calipso --listar-reales    # los docs reales, para escribir las consultas
    python experimentos/recall_banco.py --home ~/.calipso --reales /ruta/reales.json
    python experimentos/recall_banco.py --informe             # el MD desde el JSONL, sin Ollama

`reales.json`: `[{"id": "<id de chroma>", "consulta": "...", "tipo": "contenido"}, ...]`
(NO se commitea: vive en el scratchpad de la sesion). Salidas:
experimentos/recall_banco_resultados.jsonl (una fila por consulta y
condicion) y experimentos/recall_banco_resultados.md. Antes de tocar Ollama
corre `python -m calipso.carga --esperar` (la regla de recursos; `--sin-esperar`
la salta solo si ya se corrio a mano).
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import statistics
import subprocess
import sys
import tempfile
import time

RAIZ = pathlib.Path(__file__).resolve().parent.parent
if "CALIPSO_HOME" not in os.environ:
    # un home propio y se borra al salir (/tmp es RAM); si vino de afuera NO se toca
    import atexit, shutil
    os.environ["CALIPSO_HOME"] = tempfile.mkdtemp(prefix="recall-banco-home-")
    atexit.register(shutil.rmtree, os.environ["CALIPSO_HOME"], True)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.pop("CALIPSO_EMBED_FALSA", None)
sys.path.insert(0, str(RAIZ))

import chromadb  # noqa: E402
import numpy as np  # noqa: E402

from calipso import memoria_embed as me  # noqa: E402
from calipso import memoria_procedencia as mp  # noqa: E402

FIXTURE = RAIZ / "experimentos" / "fixtures" / "memoria_smoke_home"
SALIDA_JSONL = RAIZ / "experimentos" / "recall_banco_resultados.jsonl"
SALIDA_MD = RAIZ / "experimentos" / "recall_banco_resultados.md"
MINILM = "paraphrase-multilingual-MiniLM-L12-v2"
TOP = 4
CONDICIONES = ("minilm", "bge-m3:pregunta", "bge-m3:pregunta+150", "bge-m3:par")
# los umbrales contra los que se cuenta el ruido intra-corpus, ademas del sugerido
UMBRALES_REFERENCIA = {"0.476": 0.476, "0.44": 0.44, "0.30": 0.30}   # turno, abismo, MiniLM viejo

# los 8 topicos del fixture: topico -> fragmento que identifica la pregunta del documento
TOPICOS = {
    "libro_empezado": "que libro te conte que empece",
    "libro_rosa": "quien me presto el libro rosa",
    "presupuesto_taller": "presupuesto del taller",
    "mariana_agosto": "retoma lo que dejamos sobre mariana",
    "repo_calipso": "como viene el repo de calipso",
    "mapa_ciudad": "detalle del proyecto mapa-ciudad",
    "buen_dia": "buen dia! como va todo",
    "websocket": "que es un websocket",
}

# (id, topico, tipo, texto). Literal = la pregunta del documento sin el gesto
# (asi llega `chat_msg` al recall); parafrasis escritas a mano.
CONSULTAS = [
    ("libro_empezado/literal", "libro_empezado", "literal", "hola, que libro te conte que empece?"),
    ("libro_empezado/pregunta", "libro_empezado", "parafrasis_pregunta", "que libro te dije que habia arrancado a leer?"),
    ("libro_empezado/contenido", "libro_empezado", "parafrasis_contenido", "el libro de ciencia ficcion que empezamos a leer juntos"),
    ("libro_rosa/literal", "libro_rosa", "literal", "che, quien me presto el libro rosa? no me acuerdo"),
    ("libro_rosa/pregunta", "libro_rosa", "parafrasis_pregunta", "no recuerdo quien me dio prestado el libro rosa"),
    ("libro_rosa/contenido", "libro_rosa", "parafrasis_contenido", "revisar mis libretas personales para ver quien me presto un libro"),
    ("presupuesto_taller/literal", "presupuesto_taller", "literal", "en que quedamos la otra vez con el presupuesto del taller?"),
    ("presupuesto_taller/pregunta", "presupuesto_taller", "parafrasis_pregunta", "cuanta plata habiamos acordado para el taller?"),
    ("presupuesto_taller/contenido", "presupuesto_taller", "parafrasis_contenido", "no hay registros de una conversacion sobre el presupuesto"),
    ("mariana_agosto/literal", "mariana_agosto", "literal", "retoma lo que dejamos sobre mariana, la charla de agosto"),
    ("mariana_agosto/pregunta", "mariana_agosto", "parafrasis_pregunta", "seguimos con lo de mariana que hablamos en agosto"),
    ("mariana_agosto/contenido", "mariana_agosto", "parafrasis_contenido", "la charla con Mariana del 20 de agosto de 2026"),
    ("repo_calipso/literal", "repo_calipso", "literal", "como viene el repo de calipso, en que rama esta y que se toco ultimo?"),
    ("repo_calipso/pregunta", "repo_calipso", "parafrasis_pregunta", "estado del repositorio calipso: rama actual y ultimos cambios"),
    ("repo_calipso/contenido", "repo_calipso", "parafrasis_contenido", "Heraclito el analista reviso la rama del repo y no pudo completar la sintesis"),
    ("mapa_ciudad/literal", "mapa_ciudad", "literal", "dame el detalle del proyecto mapa-ciudad"),
    ("mapa_ciudad/pregunta", "mapa_ciudad", "parafrasis_pregunta", "contame de que va mapa-ciudad"),
    ("mapa_ciudad/contenido", "mapa_ciudad", "parafrasis_contenido", "un mapa interactivo de la ciudad con el backend casi listo"),
    ("buen_dia/literal", "buen_dia", "literal", "buen dia! como va todo?"),
    ("buen_dia/pregunta", "buen_dia", "parafrasis_pregunta", "hola, como venimos con todo?"),
    ("buen_dia/contenido", "buen_dia", "parafrasis_contenido", "estamos avanzando bien en varios frentes"),
    ("websocket/literal", "websocket", "literal", "explicame en dos lineas que es un websocket"),
    ("websocket/pregunta", "websocket", "parafrasis_pregunta", "que es un websocket, en breve"),
    ("websocket/contenido", "websocket", "parafrasis_contenido", "conexiones bidireccionales entre servidor y cliente con una sola conexion abierta"),
]
NEGATIVAS = [
    ("neg/tokio", "que hora es en tokio ahora"),
    ("neg/pan", "receta de pan casero con masa madre"),
    ("neg/rueda", "como se cambia una rueda pinchada"),
    ("neg/waterloo", "cuando fue la batalla de waterloo"),
    ("neg/rodilla", "me duele la rodilla al correr"),
    ("neg/alquiler", "que dice el contrato de alquiler sobre las mascotas"),
    ("neg/mongolia", "cual es la capital de mongolia"),
    ("neg/wifi", "como configuro el wifi del router nuevo"),
]


# --- el corpus ------------------------------------------------------------------

def _leer_coleccion(chroma_dir: pathlib.Path, origen: str) -> list[dict]:
    """Los documentos de la vieja `episodic` (o de la viva si la vieja no esta)
    sobre una COPIA temporal del directorio: chroma escribe su WAL al abrir."""
    copia = pathlib.Path(tempfile.mkdtemp(prefix="recall-banco-chroma-"))
    shutil.copytree(chroma_dir, copia, dirs_exist_ok=True)
    cliente = chromadb.PersistentClient(path=str(copia))
    col = None
    for nombre in (me.COLECCION_VIEJA, me.COLECCION_VIVA):
        try:
            col = cliente.get_collection(nombre, embedding_function=None)
            break
        except Exception:
            continue
    if col is None:
        return []
    datos = col.get(include=["documents", "metadatas"])
    return [{"id": i, "texto": d, "origen": origen, "meta": m or {}}
            for i, d, m in zip(datos["ids"], datos["documents"], datos["metadatas"])
            if isinstance(d, str) and d.strip()]


def topico_de(doc: str) -> str | None:
    par = mp.partir(doc)
    pregunta = mp.limpiar_gestos(par[0]) if par else (doc or "")
    pregunta = pregunta.lower()
    for topico, fragmento in TOPICOS.items():
        if fragmento in pregunta:
            return topico
    return None


def corpus(home: pathlib.Path | None) -> list[dict]:
    docs = _leer_coleccion(FIXTURE / "global" / "chroma", "fixture")
    for d in docs:
        d["topico"] = topico_de(d["texto"])
    if home:
        reales = _leer_coleccion(home / "projects" / "var-home-pedro-calipso" / "chroma", "real")
        for d in reales:
            d["topico"] = f"real/{d['id']}"
        docs += reales
    return docs


def consultas_de(reales: list[dict] | None) -> list[dict]:
    salida = [{"id": i, "topico": t, "tipo": tipo, "texto": x} for i, t, tipo, x in CONSULTAS]
    salida += [{"id": i, "topico": None, "tipo": "negativa", "texto": x} for i, x in NEGATIVAS]
    for r in reales or []:
        salida.append({"id": f"real/{r['id']}/{r.get('tipo', 'contenido')}", "topico": f"real/{r['id']}",
                       "tipo": f"real_{r.get('tipo', 'contenido')}", "texto": r["consulta"]})
    return salida


# --- las condiciones ------------------------------------------------------------

def texto_doc(condicion: str, doc: str) -> str:
    """El texto que cada condicion embebe. Solo `minilm` embebe el documento
    CRUDO (con las etiquetas y los gestos: reproduce la produccion vieja);
    las tres de bge-m3 pasan por `texto_para_embedding` con el numero que
    el Step 10 aterrizaria (0 / 150 / 10_000): se mide la forma aterrizable."""
    if condicion == "minilm":
        return doc
    if condicion == "bge-m3:pregunta":
        return me.texto_para_embedding(doc, palabras=0)
    if condicion == "bge-m3:pregunta+150":
        return me.texto_para_embedding(doc, palabras=150)
    if condicion == "bge-m3:par":
        return me.texto_para_embedding(doc, palabras=10_000)
    raise ValueError(condicion)


def embedder_de(condicion: str):
    """(embed, nota) o (None, por que no) -- la ST solo si esta instalada."""
    if condicion == "minilm":
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as e:
            return None, f"sentence_transformers no importable: {e}"
        modelo = SentenceTransformer(MINILM, device="cpu")

        def embed(textos):
            return modelo.encode(list(textos), normalize_embeddings=True).tolist()
        return embed, f"{MINILM} en proceso, max_seq_length {modelo.max_seq_length}"
    ef = me.OllamaEmbed()

    def embed(textos):
        return ef.embed(list(textos), timeout=900)
    return embed, f"{ef.model} por {ef.url}/api/embed, {ef.dims} dims"


def _normalizar(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return m / n


def correr_condicion(condicion: str, embed, docs: list[dict], consultas: list[dict]) -> list[dict]:
    t0 = time.monotonic()
    D = _normalizar(np.asarray(embed([texto_doc(condicion, d["texto"]) for d in docs]), dtype=np.float64))
    t_docs = time.monotonic() - t0
    t0 = time.monotonic()
    Q = _normalizar(np.asarray(embed([c["texto"] for c in consultas]), dtype=np.float64))
    t_cons = time.monotonic() - t0
    S = Q @ D.T
    filas = []
    for qi, c in enumerate(consultas):
        orden = [int(j) for j in np.argsort(-S[qi])[:TOP]]
        top = [{"id": docs[j]["id"], "topico": docs[j]["topico"], "origen": docs[j]["origen"],
                "score": round(float(S[qi, j]), 4)} for j in orden]
        propios = [j for j, d in enumerate(docs) if c["topico"] is not None and d["topico"] == c["topico"]]
        mejor = round(float(max(S[qi, j] for j in propios)), 4) if propios else None
        filas.append({
            "condicion": condicion, "consulta": c["id"], "topico": c["topico"], "tipo": c["tipo"],
            "top": top, "mejor_correcto": mejor,
            "acierto1": bool(propios) and top[0]["topico"] == c["topico"],
            "acierto4": bool(propios) and any(t["topico"] == c["topico"] for t in top),
            "s_docs": round(t_docs, 2), "s_consultas": round(t_cons, 2), "n_docs": len(docs)})
    return filas


# --- las metricas y el informe ---------------------------------------------------

def ruido_intra_corpus(filas: list[dict]) -> dict:
    """Por condicion: los scores de OTRO topico en el top-4 de las consultas
    POSITIVAS (literal, parafrasis y reales; las negativas no tienen topico
    propio y ya las mide el margen), ordenados de mayor a menor; `n`, `max`
    y `pasan` = cuantos llegan a cada umbral de UMBRALES_REFERENCIA."""
    por_cond: dict[str, list[float]] = {}
    for f in filas:
        if f["tipo"] == "negativa" or f["topico"] is None:
            continue
        scores = por_cond.setdefault(f["condicion"], [])
        scores += [t["score"] for t in f["top"] if t["topico"] != f["topico"]]
    salida = {}
    for nombre, scores in por_cond.items():
        scores.sort(reverse=True)
        salida[nombre] = {"n": len(scores), "max": scores[0] if scores else None, "scores": scores,
                          "pasan": {k: sum(s >= u for s in scores) for k, u in UMBRALES_REFERENCIA.items()}}
    return salida


def resumen(filas: list[dict]) -> dict:
    """Por condicion: hit@1 y hit@4 por topico y totales, la distribucion de
    scores, el margen, el umbral sugerido y el ruido intra-corpus (con
    cuantos de sus hits pasan el umbral sugerido)."""
    por_cond: dict[str, dict] = {}
    for f in filas:
        r = por_cond.setdefault(f["condicion"], {"topicos": {}, "aciertos": [], "negativas": [],
                                                  "reales": [0, 0], "n_docs": f["n_docs"],
                                                  "s_docs": f["s_docs"], "s_consultas": f["s_consultas"]})
        if f["tipo"] == "negativa":
            r["negativas"].append(f["top"][0]["score"])
            continue
        if f["tipo"].startswith("real_"):
            r["reales"][1] += 1
            r["reales"][0] += int(f["acierto1"])
            if f["acierto1"]:
                r["aciertos"].append(f["top"][0]["score"])
            continue
        t = r["topicos"].setdefault(f["topico"], {"hit1": 0, "hit4": 0, "n": 0})
        t["n"] += 1
        t["hit1"] += int(f["acierto1"])
        t["hit4"] += int(f["acierto4"])
        if f["acierto1"]:
            r["aciertos"].append(f["top"][0]["score"])
    for nombre, r in por_cond.items():
        r["hit1"] = sum(t["hit1"] for t in r["topicos"].values())
        r["hit4"] = sum(t["hit4"] for t in r["topicos"].values())
        r["n"] = sum(t["n"] for t in r["topicos"].values())
        ac, ne = r["aciertos"], r["negativas"]
        r["aciertos_min_med_max"] = (round(min(ac), 4), round(statistics.median(ac), 4), round(max(ac), 4)) if ac else None
        r["negativas_min_med_max"] = (round(min(ne), 4), round(statistics.median(ne), 4), round(max(ne), 4)) if ne else None
        r["margen"] = round(min(ac) - max(ne), 4) if ac and ne else None
        r["umbral_sugerido"] = round((min(ac) + max(ne)) / 2, 3) if ac and ne and min(ac) > max(ne) else None
    ruido = ruido_intra_corpus(filas)
    for nombre, r in por_cond.items():
        ru = ruido.get(nombre, {"n": 0, "max": None, "scores": [], "pasan": {k: 0 for k in UMBRALES_REFERENCIA}})
        u = r["umbral_sugerido"]
        r["ruido"] = {**ru, "pasan_sugerido": sum(s >= u for s in ru["scores"]) if u is not None else None}
    return por_cond


def regla_de_parada(res: dict) -> list[str]:
    """Para cada variante de bge-m3: iguala el hit@1 por topico de MiniLM y su
    margen es positivo. Si MiniLM no corrio, solo el margen."""
    avisos = []
    base = res.get("minilm")
    for nombre, r in res.items():
        if not nombre.startswith("bge-m3"):
            continue
        if r["margen"] is None or r["margen"] < 0:
            avisos.append(f"{nombre}: margen {r['margen']} (negativo o sin datos): PARAR y decirle a Pedro")
        if base:
            peores = [t for t, v in r["topicos"].items() if v["hit1"] < base["topicos"].get(t, {}).get("hit1", 0)]
            if peores:
                avisos.append(f"{nombre}: hit@1 por debajo de MiniLM en {peores}: PARAR y decirle a Pedro")
    return avisos


SECCION_UMBRALES = "## Umbrales elegidos"


def conservar_del_md(texto: str | None) -> dict:
    """Lo que `--informe` conserva del MD anterior al regenerarlo desde el
    JSONL: la fecha de la corrida (la del calculo no es una corrida nueva) y
    la seccion de umbrales elegidos, que se completa a mano."""
    salida: dict = {"corrida": None, "umbrales": None}
    if not texto:
        return salida
    for linea in texto.splitlines():
        if linea.startswith("Corrida: "):
            salida["corrida"] = linea[len("Corrida: "):].split(".")[0]
            break
    if SECCION_UMBRALES in texto:
        cuerpo = texto[texto.index(SECCION_UMBRALES):]
        fin = cuerpo.find("\n## ", len(SECCION_UMBRALES))
        salida["umbrales"] = (cuerpo if fin < 0 else cuerpo[:fin]).rstrip("\n").splitlines()
    return salida


def informe(filas: list[dict], conservar: dict | None = None) -> str:
    res = resumen(filas)
    conservar = conservar or {}
    L = ["# Banco de recall: MiniLM contra bge-m3 en tres variantes (spec memoria por Ollama, seccion 3)", ""]
    L.append(f"Corrida: {conservar.get('corrida') or time.strftime('%Y-%m-%d %H:%M')}. "
             f"Consultas por condicion: {len({f['consulta'] for f in filas})} "
             f"({len(CONSULTAS)} positivas = 8 topicos x 3, {len(NEGATIVAS)} negativas"
             + (", mas las reales" if any(f["tipo"].startswith("real_") for f in filas) else "") + "). "
             "Score = coseno (= 1 - distancia de chroma). Los duplicados del fixture cuentan como UN acierto (por topico).")
    L += ["", "## Resumen por condicion", "",
          "| condicion | docs | hit@1 | hit@4 | reales hit@1 | aciertos min/med/max | negativas min/med/max | margen | umbral sugerido | s docs | s consultas |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for nombre in CONDICIONES:
        r = res.get(nombre)
        if not r:
            L.append(f"| {nombre} | - | no corrio | | | | | | | | |")
            continue
        L.append(f"| {nombre} | {r['n_docs']} | {r['hit1']}/{r['n']} | {r['hit4']}/{r['n']} | "
                 f"{r['reales'][0]}/{r['reales'][1]} | {r['aciertos_min_med_max']} | {r['negativas_min_med_max']} | "
                 f"{r['margen']} | {r['umbral_sugerido']} | {r['s_docs']} | {r['s_consultas']} |")
    L += ["", "## hit@1 por topico (de 3 consultas: literal, parafrasis de la pregunta, parafrasis del contenido)", "",
          "| topico | " + " | ".join(c for c in CONDICIONES if c in res) + " |",
          "|---|" + "---|" * len([c for c in CONDICIONES if c in res])]
    for topico in TOPICOS:
        L.append(f"| {topico} | " + " | ".join(
            f"{res[c]['topicos'].get(topico, {}).get('hit1', 0)}/3 (hit@4 {res[c]['topicos'].get(topico, {}).get('hit4', 0)}/3)"
            for c in CONDICIONES if c in res) + " |")
    L += ["", "## Ruido intra-corpus: otro topico en el top-4 de las positivas", "",
          "El margen se mide contra temas AUSENTES (las negativas); el ruido de siempre es OTRO episodio del mismo "
          "corpus. Por condicion: cuantos hits de otro topico hay en el top-4 de las consultas positivas (literal, "
          "parafrasis y reales), el max de sus scores y cuantos pasan el umbral sugerido de la condicion y los de "
          "referencia (0.476 el turno, 0.44 la consulta del abismo, 0.30 el viejo de MiniLM). Un umbral por margen "
          "no filtra este ruido: los umbrales siguen PROVISORIOS y se re-miden cuando el corpus crezca.", "",
          "| condicion | hits de otro topico | max | pasan el sugerido | pasan 0.476 | pasan 0.44 | pasan 0.30 |",
          "|---|---|---|---|---|---|---|"]
    for nombre in [c for c in CONDICIONES if c in res] + [c for c in res if c not in CONDICIONES]:
        r = res[nombre]
        ru = r["ruido"]
        sugerido = f"{ru['pasan_sugerido']}/{ru['n']} ({r['umbral_sugerido']})" if ru["pasan_sugerido"] is not None else "- (sin umbral)"
        L.append(f"| {nombre} | {ru['n']} | {ru['max']} | {sugerido} | {ru['pasan']['0.476']}/{ru['n']} | "
                 f"{ru['pasan']['0.44']}/{ru['n']} | {ru['pasan']['0.30']}/{ru['n']} |")
    L += ["", "## Regla de parada", ""]
    avisos = regla_de_parada(res)
    L += [f"- {a}" for a in avisos] or ["- ninguna variante de bge-m3 queda por debajo de MiniLM y todos los margenes son positivos"]
    if conservar.get("umbrales"):
        L += [""] + list(conservar["umbrales"]) + [""]
    else:
        L += ["", f"{SECCION_UMBRALES} (a completar a mano al anotar: ver el plan, Task 3, Step 10)", "",
              "- `RECALL_MIN_SCORE` (server.py): ", "- `RECALL_UMBRAL` (abismo/fuentes.py): ",
              "- variante aterrizada (`PALABRAS_RESPUESTA`): ", ""]
    L += ["## Detalle: top-1 por consulta", "", "| condicion | consulta | tipo | top-1 (topico, score) | mejor del topico | acierto@1 |", "|---|---|---|---|---|---|"]
    for f in filas:
        t = f["top"][0]
        quien = t["topico"] if t["origen"] == "fixture" else f"real:{t['id']}"
        L.append(f"| {f['condicion']} | {f['consulta']} | {f['tipo']} | {quien} ({t['score']}) | {f['mejor_correcto']} | {'si' if f['acierto1'] else 'no'} |")
    return "\n".join(L) + "\n"


# --- main --------------------------------------------------------------------------

def esperar_recursos() -> None:
    r = subprocess.run([sys.executable, "-m", "calipso.carga", "--esperar", "--tope", "600"],
                       cwd=str(RAIZ), env=os.environ)
    if r.returncode != 0:
        sys.exit(f"[recursos] --esperar salio con {r.returncode}: BLOQUEADO, no corro el banco (codigo 3)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--condiciones", default=",".join(CONDICIONES))
    ap.add_argument("--home", type=pathlib.Path, default=None, help="el CALIPSO_HOME real, solo lectura (copia a tmp)")
    ap.add_argument("--reales", type=pathlib.Path, default=None, help="JSON con las consultas de las filas reales")
    ap.add_argument("--listar-reales", action="store_true", help="imprimir los docs reales (id y texto) y salir")
    ap.add_argument("--informe", action="store_true", help="rehacer el MD desde el JSONL, sin Ollama")
    ap.add_argument("--sin-esperar", action="store_true")
    args = ap.parse_args(argv)
    if args.informe:
        filas = [json.loads(l) for l in SALIDA_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
        viejo = SALIDA_MD.read_text(encoding="utf-8") if SALIDA_MD.exists() else None
        SALIDA_MD.write_text(informe(filas, conservar_del_md(viejo)), encoding="utf-8")
        for nombre, r in resumen(filas).items():
            ru = r["ruido"]
            print(f"[banco] {nombre}: ruido intra-corpus {ru['n']} hits, max {ru['max']}, "
                  f"pasan el sugerido {ru['pasan_sugerido']}, pasan 0.476 {ru['pasan']['0.476']}")
        print(SALIDA_MD)
        return 0
    docs = corpus(args.home)
    if args.listar_reales:
        for d in docs:
            if d["origen"] == "real":
                print(f"--- {d['id']} ({len(d['texto'])} chars, {d['meta'].get('ts')})\n{d['texto'][:600]}\n")
        return 0
    sin_topico = [d["id"] for d in docs if d["topico"] is None]
    if sin_topico:
        print(f"[banco] OJO: {len(sin_topico)} documentos del fixture sin topico (distractores): {sin_topico}")
    reales = json.loads(args.reales.read_text(encoding="utf-8")) if args.reales else None
    consultas = consultas_de(reales)
    condiciones = [c.strip() for c in args.condiciones.split(",") if c.strip()]
    if any(c.startswith("bge-m3") for c in condiciones) and not args.sin_esperar:
        esperar_recursos()
    filas: list[dict] = []
    for condicion in condiciones:
        embed, nota = embedder_de(condicion)
        if embed is None:
            print(f"[banco] {condicion}: no corre ({nota})")
            continue
        print(f"[banco] {condicion}: {nota}; {len(docs)} docs, {len(consultas)} consultas", flush=True)
        filas += correr_condicion(condicion, embed, docs, consultas)
    with open(SALIDA_JSONL, "w", encoding="utf-8") as f:
        for fila in filas:
            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
    SALIDA_MD.write_text(informe(filas), encoding="utf-8")
    res = resumen(filas)
    for nombre, r in res.items():
        print(f"[banco] {nombre}: hit@1 {r['hit1']}/{r['n']} hit@4 {r['hit4']}/{r['n']} reales {r['reales'][0]}/{r['reales'][1]} "
              f"margen {r['margen']} umbral sugerido {r['umbral_sugerido']}")
    for aviso in regla_de_parada(res):
        print(f"[banco] PARADA: {aviso}")
    print(f"[banco] {SALIDA_JSONL}\n[banco] {SALIDA_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
