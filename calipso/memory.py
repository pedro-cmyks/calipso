#!/usr/bin/env python3
"""
calipso/memory.py — Memoria híbrida y JERÁRQUICA de Calipso.

Dos formatos (cada uno en lo que hace bien):
  CORE  (markdown, estilo Obsidian)  -> curado, editable a mano, git-eable.
  EPISÓDICA (ChromaDB, vector)       -> volumen, recuperación por significado.

Y dos ÁMBITOS (scopes), como en Claude Code (usuario vs proyecto):
  GLOBAL   -> quién es Pedro y cómo le gusta trabajar. Sirve en TODO proyecto.
              Vive en ~/.calipso/global/{core, chroma}.
  PROYECTO -> qué es ESTE proyecto y qué estamos haciendo. Atado a la ruta.
              core markdown en <proyecto>/.calipso/core (viaja con el repo);
              vectores centralizados en ~/.calipso/projects/<slug>/chroma.

Al chatear, Calipso carga GLOBAL + PROYECTO y recuerda de ambos = buen contexto:
sabe quién eres Y de qué va el proyecto.

EVOLUCIÓN (el "arte"): reflect() lee lo episódico reciente, le pide a un LLM
local extraer hechos DURADEROS y clasificarlos (global/proyecto), y los promueve
al core curado. Es la "consolidación/reflection" de la literatura de agentes.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re

import re as _re
import shutil
import subprocess

from calipso import aduana

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))

# Modelo multilingüe local; se descarga automáticamente en el primer uso (~470 MB).
EMBED_MODEL = os.environ.get("CALIPSO_EMBED_MODEL",
                             "paraphrase-multilingual-MiniLM-L12-v2")


def _slug(path: pathlib.Path) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(path).lower()).strip("-")[:80] or "root"


class Scope:
    """Un ámbito de memoria: core markdown + episódica Chroma."""

    def __init__(self, name: str, core_dir: pathlib.Path,
                 chroma_dir: pathlib.Path, embed) -> None:
        self.name = name
        self.core_dir = pathlib.Path(core_dir)
        self.core_dir.mkdir(parents=True, exist_ok=True)
        chroma_dir = pathlib.Path(chroma_dir)
        chroma_dir.mkdir(parents=True, exist_ok=True)
        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._col = self._client.get_or_create_collection(
            "episodic", embedding_function=embed,
            metadata={"hnsw:space": "cosine"})

    # --- core markdown ---
    def load_core(self) -> str:
        parts = []
        for md in sorted(self.core_dir.glob("*.md")):
            parts.append(f"### {md.stem}\n{md.read_text(encoding='utf-8').strip()}")
        return "\n\n".join(parts)

    def append_core(self, filename: str, bullet: str) -> bool:
        """Añade una línea-hecho a un .md del core. Evita duplicados exactos."""
        p = self.core_dir / f"{filename}.md"
        existing = p.read_text(encoding="utf-8") if p.exists() else ""
        if bullet.strip() in existing:
            return False
        # Sin encabezado propio: load_core() ya antepone el título del archivo.
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"- {bullet.strip()}\n")
        return True

    def write_core(self, name: str, content: str) -> pathlib.Path:
        p = self.core_dir / f"{name}.md"
        p.write_text(content.strip() + "\n", encoding="utf-8")
        return p

    # --- episódica ---
    def remember(self, text: str, **meta) -> str:
        """Guarda un episodio, de forma corregible y sin perder escrituras.

        Las dos decisiones de acá deciden si esta memoria se puede arreglar
        alguna vez, y las dos estaban del lado que no:

        **`upsert` y no `add`.** Comprobado sobre chromadb 1.5.9: un `add`
        con un id que ya existe **conserva el documento viejo en silencio**
        -- no levanta, y `count()` ni se mueve. O sea que un episodio
        guardado mal era permanente por diseño: reindexarlo no lo corregía,
        lo ignoraba. Con `upsert`, volver a escribir el mismo episodio lo
        pisa, que es lo que hace falta el día que haya que reparar el
        corpus (y ya hay 13 documentos guardados con el texto roto).

        **El id sale del contenido, no de `count()`.** El id anterior era
        `m{count}-{ts}`, y `count()` se lee ANTES de escribir: dos
        escrituras en el mismo segundo daban el mismo id, y con `add` la
        segunda se descartaba sin aviso. Un hash de (texto, ts, meta) no
        choca por accidente, y choca a propósito exactamente cuando tiene
        que hacerlo: reintentar la misma escritura es idempotente en vez de
        duplicar."""
        clean = {k: v for k, v in meta.items() if v is not None}
        clean["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
        huella = repr((text, sorted(clean.items())))
        mem_id = "m" + hashlib.sha256(huella.encode("utf-8")).hexdigest()[:24]
        self._col.upsert(documents=[text], metadatas=[clean], ids=[mem_id])
        return mem_id

    def recall(self, query: str, n: int = 5) -> list[dict]:
        total = self._col.count()
        if total == 0:
            return []
        res = self._col.query(query_texts=[query], n_results=min(n, total))
        out = []
        for doc, md, dist in zip(res["documents"][0], res["metadatas"][0],
                                 res["distances"][0]):
            out.append({"text": doc, "meta": md, "score": round(1 - dist, 3),
                        "scope": self.name})
        return out

    def recent(self, limit: int = 20) -> list[str]:
        data = self._col.get()
        rows = list(zip(data["documents"], data["metadatas"]))
        rows.sort(key=lambda r: (r[1] or {}).get("ts", ""))
        return [d for d, _ in rows[-limit:]]

    def count(self) -> int:
        return self._col.count()


REFLECT_PROMPT = (
    "Eres el proceso de memoria de Calipso. Lee estos intercambios entre Pedro "
    "y Calipso y extrae SOLO hechos DURADEROS que valga la pena recordar a largo "
    "plazo. Clasifica cada hecho:\n"
    '  "global"  = sobre quién es Pedro o cómo le gusta trabajar (sirve en '
    "cualquier proyecto).\n"
    '  "project" = sobre ESTE proyecto: qué es o qué están haciendo.\n'
    "Ignora saludos y charla trivial. Si no hay nada que valga, facts vacío.\n\n"
    "EJEMPLO:\n"
    "Intercambio: Pedro dijo que vive en Bogotá y que el proyecto usa Postgres.\n"
    'Respuesta: {"facts":[{"scope":"global","fact":"Pedro vive en Bogotá"},'
    '{"scope":"project","fact":"El proyecto usa Postgres"}]}\n\n'
    "Ahora extrae de estos intercambios:\n{episodes}\n\n"
    "Responde SOLO JSON con la clave facts:"
)


class Memory:
    """Fachada: une los ámbitos global y de proyecto."""

    def __init__(self, project_root: str | None = None) -> None:
        self._embed = SentenceTransformerEmbeddingFunction(model_name=EMBED_MODEL)
        g = CALIPSO_HOME / "global"
        self.glob = Scope("global", g / "core", g / "chroma", self._embed)
        self.project: Scope | None = None
        self._deps: dict[str, Scope] = {}
        if project_root:
            root = pathlib.Path(project_root).resolve()
            self.project = Scope(
                "project", root / ".calipso" / "core",
                CALIPSO_HOME / "projects" / _slug(root) / "chroma", self._embed)

    @property
    def _scopes(self) -> list[Scope]:
        return [s for s in (self.glob, self.project) if s]

    def departamento(self, nombre: str) -> Scope:
        """La memoria propia de un departamento (spec de la economia, 6).

        Memoizada: cada Scope abre un cliente de Chroma y el jefe la pide en
        cada tic. NO entra en `_scopes` a proposito — esa es la lectura
        combinada del chat, y la memoria de un departamento no tiene por que
        aparecer en las conversaciones de Pedro.
        """
        clave = _slug(pathlib.Path(nombre))
        if clave not in self._deps:
            base = CALIPSO_HOME / "memoria" / "departamento" / clave
            self._deps[clave] = Scope(f"departamento:{clave}",
                                      base / "core", base / "chroma",
                                      self._embed)
        return self._deps[clave]

    # --- lectura combinada ---
    def load_core(self) -> str:
        blocks = []
        if (g := self.glob.load_core()):
            blocks.append("# Sobre Pedro (global)\n" + g)
        if self.project and (p := self.project.load_core()):
            blocks.append("# Sobre este proyecto\n" + p)
        return "\n\n".join(blocks)

    def recall(self, query: str, n: int = 5,
               ambitos: tuple[str, ...] | None = None) -> list[dict]:
        """ambitos=None: la fusion de siempre (global+proyecto). Con ambitos,
        solo los scopes nombrados -- la consulta dirigida del abismo. El
        umbral sigue viviendo en el llamador (server.py para el turno,
        abismo/fuentes.py para la consulta)."""
        scopes = [s for s in self._scopes
                  if ambitos is None or s.name in ambitos]
        hits = []
        for s in scopes:
            hits += s.recall(query, n)
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:n]

    # --- escritura ---
    def remember(self, text: str, scope: str = "auto", **meta) -> str:
        """Guarda episódico. scope 'auto' = proyecto si hay, si no global.

        OJO CON 'auto', que es una trampa y ya mordió: el "si no hay
        proyecto" casi nunca pasa. El chat SIEMPRE tiene proyecto, así que
        `auto` ahí quiere decir "el proyecto, siempre" -- y durante dos meses
        archivó las conversaciones de Pedro bajo el repo que tuviera abierto,
        dejando el ámbito global en cero filas.

        `auto` no es un enrutador: es un default. Si lo que guardás puede no
        ser del proyecto, decí el ámbito. Enrutar de verdad -mirar el
        contenido y decidir dónde va- es trabajo del abismo, no de acá."""
        target = self.glob
        if scope == "global":
            target = self.glob
        elif self.project and scope in ("project", "auto"):
            target = self.project
        return target.remember(text, **meta)

    # --- evolución (reflection / consolidación) ---
    def reflect(self, quien, limit: int = 20) -> list[dict]:
        """Promueve hechos duraderos de lo episódico reciente al core curado.
        Manda hasta `limit` episodios a `claude -p` (fuera del proceso, sin
        juez): se DECLARA en la aduana por llamada, con el Quien de quien lo
        disparo (la rutina, el boton o POST /api/reflect). Los episodios no
        van al libro."""
        source = self.project or self.glob
        episodes = source.recent(limit)
        if not episodes:
            return []
        # .replace (no .format) para no chocar con las llaves del JSON de ejemplo.
        prompt = REFLECT_PROMPT.replace(
            "{episodes}", "\n".join(f"- {e}" for e in episodes))
        try:
            exe = shutil.which("claude")
            if not exe:
                return [{"error": "claude no instalado; reflect no disponible"}]
            env = {**os.environ}
            env.pop("ANTHROPIC_API_KEY", None)
            env.pop("ANTHROPIC_AUTH_TOKEN", None)
            # el CLI no necesita las credenciales del servidor ni de litellm
            # (revision de seguridad 2026-09-07, punto 2)
            env.pop("CALIPSO_TOKEN", None)
            env.pop("LITELLM_MASTER_KEY", None)
            aduana.declarar(quien, "reflect", destino="api.anthropic.com",
                            motivo=f"{len(episodes)} episodios a claude -p")
            result = subprocess.run(
                [exe, "-p", prompt],
                capture_output=True, text=True, timeout=120, env=env
            )
            text = result.stdout.strip()
            text = _re.sub(r"^```(?:json)?\s*|\s*```$", "", text,
                           flags=_re.MULTILINE).strip()
            facts = json.loads(text).get("facts", [])
        except Exception as e:
            return [{"error": str(e)}]
        promoted = []
        for f in facts:
            scope_name = f.get("scope", "project")
            fact = (f.get("fact") or "").strip()
            if not fact:
                continue
            target = self.glob if scope_name == "global" else (self.project or self.glob)
            if target.append_core("aprendido", fact):
                promoted.append({"scope": target.name, "fact": fact})
        return promoted


# --- la carta de un departamento -------------------------------------------
# A nivel de modulo y junto a `Memory.departamento`, para que el layout de
# "memoria/departamento/<clave>/..." viva en un solo lugar.

def ruta_carta(nombre: str) -> pathlib.Path:
    """Donde vive la carta de un departamento: el texto que Pedro escribe
    diciendo para que existe, que mira y que no le toca.

    PURA: no crea directorios y no abre chroma. Es lo que la separa de
    `Memory.departamento(...)`, que construye un `Scope` y cuyo `__init__`
    hace mkdir de dos carpetas y abre un `PersistentClient`. Leer una carta
    -- o pintar una pantalla con N departamentos -- no puede crear N sqlite
    como efecto.

    AFUERA de `core/` a proposito. El core alimenta el bloque "Lo que
    aprendiste antes" del prompt del jefe: una carta ahi adentro le llegaria
    al modelo rotulada como una conclusion que el departamento saco solo, y
    es justo lo contrario -- es una instruccion de Pedro. Los dos canales
    quedan separados por construccion, sin exclusiones ni nombres
    reservados.
    """
    clave = _slug(pathlib.Path(nombre))
    return CALIPSO_HOME / "memoria" / "departamento" / clave / "carta.md"


def leer_carta(nombre: str) -> dict:
    """La carta y su estado, que son tres y no dos.

    `load_core` no sirve para esto porque devuelve "" tanto si no hay
    archivo como si lo hay vacio, y el prompt tiene que distinguir "Pedro no
    escribio" de "Pedro escribio nada": la segunda es una respuesta.

    Una carta ilegible se trata como ausente. Es el lado honesto: el jefe
    dice que no tiene carta, que es verdad, en vez de recibir bytes rotos.
    """
    try:
        crudo = ruta_carta(nombre).read_text(encoding="utf-8")
    except (OSError, ValueError):
        return {"estado": "ausente", "texto": ""}
    texto = crudo.strip()
    if not texto:
        return {"estado": "vacia", "texto": ""}
    return {"estado": "escrita", "texto": texto}


if __name__ == "__main__":
    m = Memory(project_root=os.getcwd())
    print(f"[calipso.memory] global core: {m.glob.core_dir}")
    if m.project:
        print(f"[calipso.memory] project core: {m.project.core_dir}")
    print(f"[calipso.memory] episodios global={m.glob.count()} "
          f"project={m.project.count() if m.project else '-'}")
