#!/usr/bin/env python3
"""
calipso/doclinks.py - validador de links/rutas en la documentacion (SPEC Fase 3).

Detecta drift: cuando SPEC/AGENTS/LIBRARY/RUNBOOK/CALIPSO mencionan un archivo del
repo que ya no existe (modulo renombrado, test borrado, etc.).

Es conservador a proposito: solo valida referencias que claramente apuntan a
archivos internos del repo. Omite URLs, rutas de runtime (`~/.calipso`,
`CALIPSO_HOME/...`), comodines, fragmentos de comando y placeholders. Mejor no
avisar que dar un falso positivo que rompa la verificacion.
"""
from __future__ import annotations

import pathlib
import re

DOCS = ["SPEC.md", "AGENTS.md", "LIBRARY.md", "RUNBOOK.md", "CALIPSO.md"]

# Tokens entre backticks. Capturamos lo de adentro para inspeccionarlo.
_BACKTICK = re.compile(r"`([^`\n]+)`")

# Extensiones de archivos que viven en el repo.
_REPO_EXT = (".py", ".js", ".html", ".css", ".json", ".svg", ".bat", ".ps1", ".md")


def _is_internal_ref(token: str) -> bool:
    """True si el token parece una ruta de archivo interna del repo."""
    t = token.strip()
    if not t or " " in t or "\t" in t:
        return False
    # nada de URLs, runtime, placeholders, globs o anclas de markdown
    bad = ("http://", "https://", "~", "{", "}", "<", ">", "*", "$", "#")
    if any(b in t for b in bad):
        return False
    if t.startswith(("/", ".")) or ":" in t:
        return False
    if "CALIPSO_HOME" in t or t.startswith("~"):
        return False
    if not t.endswith(_REPO_EXT):
        return False
    # patron interno: calipso/..., test_*.py, o script raiz conocido
    if t.startswith("calipso/"):
        return True
    if re.fullmatch(r"test_[a-z0-9_]+\.py", t):
        return True
    if re.fullmatch(r"[A-Za-z0-9_]+\.(py|bat|ps1)", t):
        return True
    return False


def audit(root: str | pathlib.Path | None = None) -> dict:
    root = pathlib.Path(root or pathlib.Path(__file__).resolve().parent.parent)
    broken: list[dict] = []
    checked = 0
    for doc in DOCS:
        path = root / doc
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        seen: set[str] = set()
        for m in _BACKTICK.finditer(text):
            token = m.group(1).strip().rstrip(".,;:)")
            if token in seen or not _is_internal_ref(token):
                continue
            seen.add(token)
            checked += 1
            # nombre suelto (sin "/"): vale si existe en raiz o como modulo en calipso/
            exists = (root / token).exists()
            if not exists and "/" not in token:
                exists = (root / "calipso" / token).exists()
            if not exists:
                broken.append({"doc": doc, "ref": token})
    return {"ok": not broken, "checked": checked, "broken": broken}
