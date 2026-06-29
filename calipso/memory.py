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
import json
import os
import pathlib
import re

import re as _re
import shutil
import subprocess

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
        clean = {k: v for k, v in meta.items() if v is not None}
        clean["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
        mem_id = f"m{self._col.count()}-{clean['ts']}"
        self._col.add(documents=[text], metadatas=[clean], ids=[mem_id])
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
        if project_root:
            root = pathlib.Path(project_root).resolve()
            self.project = Scope(
                "project", root / ".calipso" / "core",
                CALIPSO_HOME / "projects" / _slug(root) / "chroma", self._embed)

    @property
    def _scopes(self) -> list[Scope]:
        return [s for s in (self.glob, self.project) if s]

    # --- lectura combinada ---
    def load_core(self) -> str:
        blocks = []
        if (g := self.glob.load_core()):
            blocks.append("# Sobre Pedro (global)\n" + g)
        if self.project and (p := self.project.load_core()):
            blocks.append("# Sobre este proyecto\n" + p)
        return "\n\n".join(blocks)

    def recall(self, query: str, n: int = 5) -> list[dict]:
        hits = []
        for s in self._scopes:
            hits += s.recall(query, n)
        hits.sort(key=lambda h: h["score"], reverse=True)
        return hits[:n]

    # --- escritura ---
    def remember(self, text: str, scope: str = "auto", **meta) -> str:
        """Guarda episódico. scope 'auto' = proyecto si hay, si no global."""
        target = self.glob
        if scope == "global":
            target = self.glob
        elif self.project and scope in ("project", "auto"):
            target = self.project
        return target.remember(text, **meta)

    # --- evolución (reflection / consolidación) ---
    def reflect(self, limit: int = 20) -> list[dict]:
        """Promueve hechos duraderos de lo episódico reciente al core curado."""
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


if __name__ == "__main__":
    m = Memory(project_root=os.getcwd())
    print(f"[calipso.memory] global core: {m.glob.core_dir}")
    if m.project:
        print(f"[calipso.memory] project core: {m.project.core_dir}")
    print(f"[calipso.memory] episodios global={m.glob.count()} "
          f"project={m.project.count() if m.project else '-'}")
