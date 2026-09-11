"""El reindexado de la memoria episodica con procedencia (spec 2026-09-11,
seccion 3): un solo tiro sobre el home, con el server apagado, que agrega a
cada episodio VIEJO que parsea como par de chat los metadatos que lo nuevo ya
trae (`procedencia=1`, `ruta` = la `route` decidida, unica disponible),
conservando id, documento, embedding y cantidad.

    python -m calipso.memoria_reindex --vista      # cuenta, no escribe
    python -m calipso.memoria_reindex --aplicar    # escribe (merge, idempotente)
    python -m calipso.memoria_reindex --aplicar --forzar   # con el server prendido

Abre cada ambito por directorio (`global/chroma` y `projects/*/chroma` bajo
CALIPSO_HOME) con `chromadb.PersistentClient` + `get_collection("episodic",
embedding_function=None)`, NO via `memory.Scope` (exige la funcion de
embeddings y hace mkdir de un core_dir que aca no se conoce). Verificado en
chromadb 1.5.9: `update(ids, metadatas)` sin `documents` MERGEA metadatos,
un `None` BORRA la clave (por eso los nuevos se arman sin None), y no toca
documento, id ni embedding. PERO ese `update` reconstruye la funcion de
embeddings persistida en el schema de la coleccion (SentenceTransformer)
aunque no embeba nada, y cargarla sale a huggingface.co salvo que el hub
este en modo offline: por eso las dos variables de abajo se fijan ANTES de
importar chromadb (`setdefault`: un `HF_HUB_OFFLINE=0` explicito de Pedro
manda). Eso protege la corrida por CLI (proceso limpio: el acto de Pedro) y
el archivo de tests corrido en aislado; dentro de la suite entera llega
tarde (calipso.server ya construyo Memory() con el hub online al importar,
conducta de main) y el test del fixture real no sale a la red porque
reutiliza el modelo ya cargado en el proceso. Sin red, sin aduana: este
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

from calipso import memoria_procedencia as mp  # noqa: E402

COLECCION = "episodic"
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


def abrir(chroma_dir: pathlib.Path):
    """La coleccion, o None si el directorio no la tiene."""
    cliente = chromadb.PersistentClient(path=str(chroma_dir))
    try:
        return cliente.get_collection(COLECCION, embedding_function=None)
    except NotFoundError:
        return None


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
    modo.add_argument("--vista", action="store_true", help="contar, no escribir")
    modo.add_argument("--aplicar", action="store_true", help="escribir los metadatos")
    ap.add_argument("--forzar", action="store_true",
                    help="aplicar aunque el server responda en CALIPSO_PORT")
    args = ap.parse_args(argv)
    base = home()
    print(f"home: {base}", file=salida)
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
    for nombre, chroma_dir in lista:
        col = abrir(chroma_dir)
        if col is None:
            print(f"{nombre}: sin coleccion {COLECCION} (se salta)", file=salida)
            continue
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
