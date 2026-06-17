#!/usr/bin/env python3
"""
calipso/backup.py - backup local del runtime de Calipso (SPEC Fase 6).

Respalda lo que Pedro no quiere perder (memoria curada, metas, config, chats)
a un zip con timestamp dentro de `CALIPSO_HOME/backups/`. Es 100% local: no sube
nada a ningun lado. Excluye caches pesados (modelos/embeddings) y la propia
carpeta de backups para no anidar respaldos.
"""
from __future__ import annotations

import datetime
import os
import pathlib
import zipfile

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))

# Caches/artefactos que no tiene sentido respaldar (pesan y se regeneran).
SKIP_DIRS = {"backups", "models", "model_cache", "__pycache__", ".cache"}


def _backups_dir() -> pathlib.Path:
    d = CALIPSO_HOME / "backups"
    d.mkdir(parents=True, exist_ok=True)
    return d


def create_backup(stamp: str | None = None) -> dict:
    """Crea un zip del runtime curado. `stamp` permite tests deterministas."""
    home = CALIPSO_HOME
    home.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out = _backups_dir() / f"calipso-backup-{stamp}.zip"
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(home):
            rootp = pathlib.Path(root)
            # no descender en directorios excluidos
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            rel_root = rootp.relative_to(home)
            if any(part in SKIP_DIRS for part in rel_root.parts):
                continue
            for name in files:
                fp = rootp / name
                if fp == out:
                    continue
                try:
                    zf.write(fp, str(fp.relative_to(home)))
                    count += 1
                except Exception:
                    continue
    return {
        "ok": True,
        "path": str(out),
        "files": count,
        "bytes": out.stat().st_size if out.exists() else 0,
    }


def list_backups() -> list[dict]:
    d = _backups_dir()
    items = []
    for f in sorted(d.glob("calipso-backup-*.zip"), reverse=True):
        st = f.stat()
        items.append({
            "name": f.name,
            "path": str(f),
            "bytes": st.st_size,
            "modified": datetime.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        })
    return items
