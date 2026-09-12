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
# `tokenizador`: el tokenizer.json del modelo local (11-23 MB), se regenera
# desde el GGUF de ~/.ollama (calipso/tokenizador.py).
SKIP_DIRS = {"backups", "models", "model_cache", "__pycache__", ".cache", "tokenizador"}

# Directorios excluidos SOLO en la raiz del home: logs/ lleva el access log
# que llego a contener el token (revision de seguridad 2026-09-07, C4/C6).
# Un "logs" anidado en un proyecto es una carpeta comun y se respalda.
SKIP_DIRS_RAIZ = {"logs"}

# La credencial del servidor NO se respalda: se regenera. Un zip con el
# token y la semilla TOTP adentro esquivaba el unico NUNCA del motor de
# permisos (que matchea las rutas exactas, no el zip) y nacia 0644
# (revision de seguridad 2026-09-07, C6). Solo aplica en la raiz del home.
# `sesiones.json` va por lo mismo (invariante 7 de la capa de sesion): un zip
# viejo con los hashes de las sesiones vivas y los id_pedido pendientes
# adentro es la misma puerta de al lado, y el almacen se regenera solo -- los
# aparatos vuelven a golpear.
# Solo el nombre exacto: los `sesiones.json.corrupto-<ts>` llevan hashes.
SKIP_FILES_RAIZ = {"token", "totp_secret", "sesiones.json"}


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
    # 0600 desde el nacimiento (touch respeta el modo al crear y ZipFile
    # "w" trunca sin tocarlo): sin ventana world-readable mientras se
    # comprime un zip que lleva chats y memoria enteros.
    out.touch(mode=0o600)
    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(home):
            rootp = pathlib.Path(root)
            # no descender en directorios excluidos
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS
                       and not (rootp == home and d in SKIP_DIRS_RAIZ)]
            rel_root = rootp.relative_to(home)
            if any(part in SKIP_DIRS for part in rel_root.parts):
                continue
            for name in files:
                fp = rootp / name
                if fp == out:
                    continue
                if rootp == home and name in SKIP_FILES_RAIZ:
                    continue
                try:
                    zf.write(fp, str(fp.relative_to(home)))
                    count += 1
                except Exception:
                    continue
    # 0600 como el token mismo: el zip lleva chats y memoria enteros.
    out.chmod(0o600)
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
