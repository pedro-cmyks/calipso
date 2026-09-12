"""El reindexado de la memoria episodica: la procedencia (spec 2026-09-11,
seccion 3) y el cambio de embedder (spec memoria por Ollama 2026-09-12): un
solo tiro sobre el home, con el server apagado. `--aplicar` agrega a cada
episodio VIEJO que parsea como par de chat los metadatos que lo nuevo ya trae
(`procedencia=1`, `ruta` = la `route` decidida), conservando id, documento,
embedding y cantidad. `--embeddings` copia la coleccion vieja `episodic`
(MiniLM, 384 dims) a la viva `episodic-<tag>` (`episodic-bge-m3`) con los
MISMOS ids, documentos y metadatos, embebiendo por Ollama en lotes por
tamano; idempotente (un id que ya esta solo converge sus metadatos); NO borra
la vieja; imprime cuantos copio y cuantos quedan.

    python -m calipso.memoria_reindex --vista        # cuenta (procedencia y sin_reindexar), no escribe
    python -m calipso.memoria_reindex --aplicar      # la procedencia (merge, idempotente)
    python -m calipso.memoria_reindex --aplicar --forzar   # con el server prendido
    python -m calipso.memoria_reindex --embeddings   # episodic -> episodic-<tag>; SOLO con el server apagado
    python -m calipso.memoria_reindex --embeddings --falsa   # con la EF falsa (hash), a proposito: tests

`--embeddings` anuncia el embedder antes del bucle (`embedder: OllamaEmbed
bge-m3:latest 1024 dims @ <url>`), se niega con 2 si la EF es la falsa de la
suite y no vino `--falsa` (un `CALIPSO_EMBED_FALSA=1` heredado de la shell
llenaria la viva con vectores de hash sin decirlo) y, si Ollama no contesta
o el modelo no esta (`EmbedError`), lo dice en una linea y devuelve 3: la
vieja queda intacta y se vuelve a correr.

`--vista` y `--aplicar` operan sobre la VIVA si existe y sobre la vieja si
no: `--embeddings` y luego `--aplicar`, o al reves, convergen. `--embeddings`
no admite `--forzar` (ruling 8.9): un corte no atomico entre las dos
colecciones no tiene arreglo despues; ademas toma la lista de ids de la
vieja antes y despues y, si aparecieron ids durante la corrida, lo dice y no
declara `sin_reindexar = 0`.

Abre cada ambito por directorio (`global/chroma` y `projects/*/chroma` bajo
CALIPSO_HOME) con `chromadb.PersistentClient` + `get_collection(<nombre>,
embedding_function=None)`, NO via `memory.Scope` (exige la funcion de
embeddings y hace mkdir de un core_dir que aca no se conoce). Verificado en
chromadb 1.5.9: `update(ids, metadatas)` sin `documents` MERGEA metadatos,
un `None` BORRA la clave (por eso los nuevos se arman sin None), y no toca
documento, id ni embedding. Ese `update` reconstruye la funcion de
embeddings persistida en el schema de la coleccion aunque no embeba nada:
en la viva es `calipso_ollama`, pura (sin red); en la vieja `episodic` es la
SentenceTransformer de MiniLM, que sin torch en el venv chroma degrada a
None con un aviso y sigue, y con torch todavia instalado saldria a
huggingface.co salvo que el hub este offline: por eso las dos variables de
abajo se fijan ANTES de importar chromadb (`setdefault`: un
`HF_HUB_OFFLINE=0` explicito de Pedro manda). Sin red, sin aduana: este
proceso no es el server.

`--vista` solo hace `get` y `count`: no carga el modelo, y SE PERMITE con
el server prendido (ruling 7 del plan, tomado por Pedro el 2026-09-11: es
de solo lectura, dos clientes sobre el mismo directorio no corrompen nada,
y sirve justamente para mirar los conteos sin apagar el server; el costo es
un conteo que no incluya el episodio que el server escribe en ese instante).
Solo `--aplicar` chequea el puerto, y se niega salvo `--forzar`.
"""
from __future__ import annotations

import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import argparse  # noqa: E402
import pathlib  # noqa: E402
import socket  # noqa: E402
import sys  # noqa: E402

import chromadb  # noqa: E402
from chromadb.errors import NotFoundError  # noqa: E402

from calipso import memoria_embed  # noqa: E402  (registra la EF calipso_ollama en chroma)
from calipso import memoria_procedencia as mp  # noqa: E402

COLECCION_VIEJA = memoria_embed.COLECCION_VIEJA      # "episodic": MiniLM, solo origen
COLECCION_VIVA = memoria_embed.COLECCION_VIVA        # "episodic-<tag>": la que abre el server
LOTE = 100


def home() -> pathlib.Path:
    """Resuelto por llamada, no congelado al importar (test_aislacion_home):
    el script se corre con `export CALIPSO_HOME=...` o sobre el real."""
    return pathlib.Path(os.environ.get("CALIPSO_HOME",
                                       os.path.expanduser("~/.calipso")))


def puerto() -> int:
    """El del lanzador (launch_calipso.py): CALIPSO_PORT, default 8000."""
    try:
        return int(os.environ.get("CALIPSO_PORT", "8000"))
    except (TypeError, ValueError):
        return 8000


def ambitos(base: pathlib.Path) -> list[tuple[str, pathlib.Path]]:
    """(nombre, directorio chroma) de cada ambito que EXISTE: `global` y cada
    `projects/<slug>`. Solo los que ya tienen `chroma.sqlite3`: abrir un
    PersistentClient sobre un directorio vacio lo crea, y el reindex no
    crea nada. Los departamentos (memoria/departamento/*) no entran: el spec
    los deja afuera."""
    salida = []
    g = base / "global" / "chroma"
    if (g / "chroma.sqlite3").exists():
        salida.append(("global", g))
    proyectos = base / "projects"
    if proyectos.is_dir():
        for d in sorted(proyectos.iterdir()):
            c = d / "chroma"
            if (c / "chroma.sqlite3").exists():
                salida.append((f"projects/{d.name}", c))
    return salida


def _server_prendido(port: int, host: str = "127.0.0.1") -> bool:
    """Loopback: pregunta si algo escucha en el puerto del server. Es por
    completitud del recorrido (un server vivo sigue escribiendo episodios),
    no por integridad: dos PersistentClient sobre el mismo directorio no
    corrompen nada (sondeado)."""
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False


def abrir(cliente):
    """(coleccion, nombre) para la procedencia: la VIVA si existe, si no la
    vieja; (None, None) si el directorio no tiene ninguna. Sin EF: `get`,
    `count` y `update(ids, metadatas)` no embeben (en la viva reconstruyen
    `calipso_ollama`, que es pura; en la vieja, la ST persistida, de ahi el
    hub offline de arriba)."""
    for nombre in (COLECCION_VIVA, COLECCION_VIEJA):
        try:
            return cliente.get_collection(nombre, embedding_function=None), nombre
        except NotFoundError:
            continue
    return None, None


def _linea_estado(nombre: str, cliente, coleccion: str | None = None) -> str:
    """`<ambito>: N en episodic, M en episodic-<tag>, sin_reindexar K`; lo que
    `--vista` y `--aplicar` imprimen antes de la linea de procedencia."""
    partes = []
    for col in (COLECCION_VIEJA, COLECCION_VIVA):
        ids = memoria_embed.ids_de(cliente, col)
        partes.append(f"{len(ids)} en {col}" if ids is not None else f"sin {col}")
    texto = f"{nombre}: {', '.join(partes)}, sin_reindexar {memoria_embed.sin_reindexar(cliente)}"
    if coleccion:
        texto += f" (procedencia sobre {coleccion})"
    return texto


def reindexar_embeddings(cliente, ef) -> dict:
    """Copia `episodic` a `episodic-<tag>` por ids (spec memoria por Ollama,
    seccion 2): lee la vieja con `get` (sin EF: no importa torch), crea la
    viva con la EF nueva (chroma persiste name + config; los vectores van
    explicitos), hace `update(ids, metadatas)` para los ids que ya estan
    (convergen sin re-embeber) y `upsert` con embeddings de
    `texto_para_embedding` para los que faltan, por lotes de LOTE_CHARS.
    Un documento sin texto no se copia (queda en `sin_reindexar` para
    siempre: se cuenta en `sin_documento` y la linea lo dice); un metadato
    vacio va como None (chroma rechaza `{}`). Devuelve copiados, `ya_estaban`
    (los ids de la vieja que ya estaban en la viva), `actualizados` (los de
    esos con metadatos, que se mergean), `sin_documento`, los ids que
    aparecieron en la vieja durante la corrida y `sin_reindexar` al final.
    Un `EmbedError` sale tal cual: `main` lo atrapa y lo dice."""
    try:
        vieja = cliente.get_collection(COLECCION_VIEJA, embedding_function=None)
    except NotFoundError:
        return {"copiados": 0, "ya_estaban": 0, "actualizados": 0, "sin_documento": 0, "aparecidos": 0,
                "sin_reindexar": 0, "sin_vieja": True}
    viva = cliente.get_or_create_collection(COLECCION_VIVA, embedding_function=ef,
                                            metadata={"hnsw:space": "cosine"})
    ids_antes = set(vieja.get(include=[])["ids"])
    datos = vieja.get(include=["documents", "metadatas"])
    presentes = set(viva.get(include=[])["ids"])
    nuevos: list[tuple[str, str, dict | None]] = []
    ya: list[tuple[str, dict]] = []
    sin_documento = 0
    for id_, doc, meta in zip(datos["ids"], datos["documents"], datos["metadatas"]):
        meta_ = meta if isinstance(meta, dict) and meta else None
        if id_ in presentes:
            if meta_:
                ya.append((id_, meta_))
            continue
        if not isinstance(doc, str) or not doc.strip():
            sin_documento += 1
            continue
        nuevos.append((id_, doc, meta_))
    for i in range(0, len(ya), LOTE):
        lote = ya[i:i + LOTE]
        viva.update(ids=[p[0] for p in lote], metadatas=[p[1] for p in lote])
    copiados = 0
    textos = [memoria_embed.texto_para_embedding(doc) for _, doc, _ in nuevos]
    pos = 0
    for lote in memoria_embed.lotes(textos):
        tramo = nuevos[pos:pos + len(lote)]
        pos += len(lote)
        vectores = memoria_embed.embeber(ef, lote, timeout=memoria_embed.TIMEOUT_REMEMBER_S)
        viva.upsert(ids=[t[0] for t in tramo], documents=[t[1] for t in tramo],
                    metadatas=[t[2] for t in tramo], embeddings=vectores)
        copiados += len(tramo)
    ids_despues = set(vieja.get(include=[])["ids"])
    vivos = set(viva.get(include=[])["ids"])
    return {"copiados": copiados, "ya_estaban": len(presentes & ids_antes), "actualizados": len(ya),
            "sin_documento": sin_documento, "aparecidos": len(ids_despues - ids_antes),
            "sin_reindexar": len(ids_despues - vivos), "sin_vieja": False}


def revisar(col) -> dict:
    """Lee todo y clasifica sin escribir. `pendientes` son los (id, meta
    nueva) que `aplicar` escribiria: pares de chat (kind 'chat' o sin kind)
    sin `procedencia` todavia, con `{**meta, procedencia: 1, ruta: route}`
    sin ningun None."""
    datos = col.get(include=["documents", "metadatas"])
    r = {"episodios": 0, "con_procedencia": 0, "parsean": 0,
         "chat_no_parsean": 0, "no_chat": 0, "sin_dato": 0, "basura": 0,
         "raros": 0, "pendientes": []}
    for id_, doc, meta in zip(datos["ids"], datos["documents"], datos["metadatas"]):
        r["episodios"] += 1
        if not isinstance(meta, dict) or not isinstance(doc, str):
            r["raros"] += 1          # se salta y se cuenta, jamas se pisa
            continue
        kind = meta.get("kind")
        es_chat = kind in (None, "chat")
        par = mp.partir(doc)
        if meta.get("procedencia") == 1:
            r["con_procedencia"] += 1
        if not es_chat:
            r["no_chat"] += 1
            continue
        if par is None:
            if kind == "chat":
                r["chat_no_parsean"] += 1
            else:
                r["no_chat"] += 1    # sin kind y sin forma de par: no es un chat
            continue
        r["parsean"] += 1
        pregunta, respuesta = par
        if not mp.limpiar_gestos(pregunta):
            r["basura"] += 1
        elif mp.clasificar(respuesta) == "sin_dato":
            r["sin_dato"] += 1
        if meta.get("procedencia") == 1:
            continue                 # ya reindexado: idempotencia
        nuevos = {"procedencia": 1}
        if meta.get("route"):
            nuevos["ruta"] = meta["route"]
        r["pendientes"].append((id_, {**meta, **nuevos}))
    return r


def aplicar(col, revision: dict) -> int:
    """Escribe los pendientes por lotes con `update(ids, metadatas)` -- sin
    `documents`, para no re-embeber. Devuelve cuantos escribio."""
    pendientes = revision["pendientes"]
    for i in range(0, len(pendientes), LOTE):
        lote = pendientes[i:i + LOTE]
        col.update(ids=[p[0] for p in lote], metadatas=[p[1] for p in lote])
    return len(pendientes)


def _linea_embeddings(nombre: str, r: dict) -> str:
    """Lo que `--embeddings` imprime por ambito: copiados, cuantos ya estaban
    en la viva (aparte cuantos de esos convergieron metadatos), lo que queda
    en `sin_reindexar` y, de eso, cuantos no tienen documento (no se copian
    nunca), y el OJO de los ids aparecidos durante la corrida."""
    texto = (f"{nombre}: {r['copiados']} copiados a {COLECCION_VIVA}, {r['ya_estaban']} ya estaban "
             f"({r['actualizados']} metadatos actualizados), sin_reindexar {r['sin_reindexar']}")
    if r["sin_documento"]:
        texto += f" ({r['sin_documento']} sin documento: no se copian)"
    if r["aparecidos"]:
        texto += f"  OJO: aparecieron {r['aparecidos']} ids en {COLECCION_VIEJA} durante la corrida"
    return texto


def _describir_embedder(ef) -> str:
    """La linea que `--embeddings` imprime antes del bucle: con que se
    embebe (la falsa solo llega aca con `--falsa`)."""
    if isinstance(ef, memoria_embed.EmbedFalsa):
        return "embedder: EmbedFalsa (--falsa)"
    return f"embedder: OllamaEmbed {ef.model} {ef.dims} dims @ {ef.url}"


def _linea(nombre: str, r: dict) -> str:
    return (f"{nombre}: {r['episodios']} episodios, {r['con_procedencia']} con "
            f"procedencia, {r['parsean']} parsean como chat, "
            f"{r['chat_no_parsean']} kind=chat que NO parsean, {r['no_chat']} no chat, "
            f"{r['sin_dato']} sin_dato, {r['basura']} basura, {r['raros']} raros "
            f"-> {len(r['pendientes'])} por reindexar")


def main(argv: list[str] | None = None, salida=None) -> int:
    salida = salida or sys.stdout
    ap = argparse.ArgumentParser(prog="python -m calipso.memoria_reindex",
                                 description=__doc__.split("\n\n")[0])
    modo = ap.add_mutually_exclusive_group(required=True)
    modo.add_argument("--vista", action="store_true", help="contar (procedencia y sin_reindexar), no escribir")
    modo.add_argument("--aplicar", action="store_true", help="escribir los metadatos de procedencia")
    modo.add_argument("--embeddings", action="store_true",
                      help=f"copiar {COLECCION_VIEJA} a {COLECCION_VIVA} embebiendo por Ollama "
                           "(solo con el server apagado; sin --forzar)")
    ap.add_argument("--forzar", action="store_true",
                    help="aplicar aunque el server responda en CALIPSO_PORT (no vale con --embeddings)")
    ap.add_argument("--falsa", action="store_true",
                    help="con --embeddings: permitir la EF falsa de la suite (CALIPSO_EMBED_FALSA=1, "
                         "vectores de hash) a proposito; sin el flag se niega")
    args = ap.parse_args(argv)
    if args.embeddings and args.forzar:
        # antes de mirar el puerto: con --embeddings, --forzar no existe (ruling 8.9),
        # tambien con el server apagado
        print("--embeddings no admite --forzar (ruling 8.9): corre siempre con el server apagado; "
              "un corte no atomico entre las dos colecciones no tiene arreglo despues.", file=salida)
        return 2
    base = home()
    print(f"home: {base}", file=salida)
    if args.embeddings and _server_prendido(puerto()):
        print(f"el server responde en el puerto {puerto()}: apagalo. --embeddings no admite --forzar "
              "(ruling 8.9): un corte no atomico entre las dos colecciones no tiene arreglo despues.",
              file=salida)
        return 2
    if args.aplicar and _server_prendido(puerto()):
        if not args.forzar:
            print(f"el server responde en el puerto {puerto()}: apagalo (o --forzar). "
                  "No es por integridad -- dos clientes no corrompen el chroma -- "
                  "sino para que el recorrido sea completo: un server vivo sigue "
                  "escribiendo episodios.", file=salida)
            return 2
        print(f"el server responde en el puerto {puerto()}; --forzar: sigo", file=salida)
    lista = ambitos(base)
    if not lista:
        print("ningun ambito con chroma bajo el home", file=salida)
        return 1
    ef = None
    if args.embeddings:
        ef = memoria_embed.embedder_por_env()
        if isinstance(ef, memoria_embed.EmbedFalsa) and not args.falsa:
            # un CALIPSO_EMBED_FALSA=1 heredado de la shell llenaria la viva
            # de un home con vectores de hash sin decirlo (ola de fix, punto 3b)
            print("CALIPSO_EMBED_FALSA=1: --embeddings no escribe vectores falsos en un home "
                  "(usar env -u CALIPSO_EMBED_FALSA, o --falsa a proposito)", file=salida)
            return 2
        print(_describir_embedder(ef), file=salida)
    for nombre, chroma_dir in lista:
        cliente = chromadb.PersistentClient(path=str(chroma_dir))
        if args.embeddings:
            try:
                r = reindexar_embeddings(cliente, ef)
            except memoria_embed.EmbedError as e:
                # Ollama caido o el modelo sin bajar: una linea, no un traceback;
                # la vieja no se toco y la viva a medias converge en la proxima corrida
                # el nombre para `ollama pull` es el del modelo sin `:latest` (no el
                # tag de la coleccion, que sanea otros caracteres)
                modelo = ef.model[:-len(":latest")] if ef.model.endswith(":latest") else ef.model
                print(f"{nombre}: no se pudo embeber por Ollama ({e}); si el modelo no esta: "
                      f"ollama pull {modelo}; la coleccion vieja queda intacta, "
                      "volver a correr --embeddings", file=salida)
                return 3
            if r["sin_vieja"]:
                print(f"{nombre}: sin coleccion {COLECCION_VIEJA} (se salta)", file=salida)
                continue
            print(_linea_embeddings(nombre, r), file=salida)
            continue
        col, coleccion = abrir(cliente)
        if col is None:
            print(f"{nombre}: sin coleccion {COLECCION_VIVA} ni {COLECCION_VIEJA} (se salta)", file=salida)
            continue
        print(_linea_estado(nombre, cliente, coleccion), file=salida)
        r = revisar(col)
        print(_linea(nombre, r), file=salida)
        if not args.aplicar:
            continue
        if not r["pendientes"]:
            print(f"{nombre}: nada que escribir (ya reindexado o sin pares de chat)", file=salida)
            continue
        n = aplicar(col, r)
        despues = col.count()
        print(f"{nombre}: {n} episodios reindexados; count {r['episodios']} -> {despues}"
              + ("" if despues == r["episodios"] else "  OJO: la cantidad cambio durante la corrida"),
              file=salida)
    return 0


if __name__ == "__main__":
    sys.exit(main())
