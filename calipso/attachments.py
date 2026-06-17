#!/usr/bin/env python3
"""
calipso/attachments.py - adjuntos persistentes para el chat.

V0 cubre archivos de texto: se guardan por proyecto, se presupuestan para
contexto y quedan referenciables por id. Binarios/imagenes se registran como
metadata pero no se inyectan al prompt.
"""
from __future__ import annotations

import base64
import datetime
import json
import os
import pathlib
import uuid
from typing import Any

CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))

MAX_CONTEXT_CHARS = 12_000
MAX_FOLDER_FILES = 40
MAX_FILE_CHARS = 3_000

IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}

TEXT_EXTS = {
    ".md", ".txt", ".py", ".js", ".ts", ".tsx", ".jsx", ".json", ".yaml",
    ".yml", ".html", ".css", ".csv", ".xml", ".toml", ".ini", ".cfg",
}


def _slug(project_root: str | None) -> str:
    if not project_root:
        return "global"
    p = pathlib.Path(project_root).resolve()
    return str(p).replace(":", "").replace("\\", "-").replace("/", "-").strip("-")


def _attachments_dir(project_root: str | None) -> pathlib.Path:
    d = CALIPSO_HOME / "projects" / _slug(project_root) / "attachments"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _attachment_dir(project_root: str | None, attachment_id: str) -> pathlib.Path:
    d = _attachments_dir(project_root) / attachment_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def create(project_root: str | None, name: str, content: str,
           mode: str = "read_only", mime: str | None = None,
           encoding: str = "text", source: dict[str, Any] | None = None) -> dict[str, Any]:
    attachment_id = f"att_{uuid.uuid4().hex[:12]}"
    safe_name = pathlib.Path(name or "adjunto.txt").name or "adjunto.txt"
    d = _attachment_dir(project_root, attachment_id)
    if encoding == "base64":
        raw = base64.b64decode(content.encode("ascii"), validate=False)
        (d / "content.bin").write_bytes(raw)
        text_preview = ""
        size = len(raw)
    else:
        text_preview = content
        (d / "content.txt").write_text(content, encoding="utf-8")
        size = len(content.encode("utf-8"))
    meta = {
        "id": attachment_id,
        "name": safe_name,
        "mode": mode if mode in {"read_only", "editable"} else "read_only",
        "mime": mime or "text/plain",
        "encoding": encoding,
        "size": size,
        "created_at": _now(),
        "context_chars": min(len(text_preview), MAX_CONTEXT_CHARS),
    }
    if source:
        meta["source"] = source
    (d / "attachment.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def folder_bundle(project_root: str, rel_path: str = "", max_chars: int = MAX_CONTEXT_CHARS,
                  max_files: int = MAX_FOLDER_FILES) -> tuple[str, dict[str, Any]]:
    root = pathlib.Path(project_root).resolve()
    target = (root / rel_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError("ruta fuera del proyecto")
    if not target.exists() or not target.is_dir():
        raise ValueError("no es una carpeta")

    files: list[pathlib.Path] = []
    skipped: list[str] = []
    for p in sorted(target.rglob("*")):
        if len(files) >= max_files:
            skipped.append("limite de archivos alcanzado")
            break
        if any(part in IGNORE_DIRS for part in p.relative_to(target).parts):
            continue
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if p.suffix.lower() not in TEXT_EXTS:
            skipped.append(f"{rel} (tipo no textual)")
            continue
        try:
            if p.stat().st_size > MAX_FILE_CHARS * 6:
                skipped.append(f"{rel} (archivo grande)")
                continue
            p.read_text(encoding="utf-8")
        except Exception:
            skipped.append(f"{rel} (no legible)")
            continue
        files.append(p)

    lines = [
        f"Carpeta adjunta: {target.relative_to(root).as_posix() if target != root else '.'}",
        f"Archivos incluidos: {len(files)}",
        "",
        "Manifest:",
        *[f"- {p.relative_to(root).as_posix()} ({p.stat().st_size} bytes)" for p in files],
    ]
    if skipped:
        lines.extend(["", "Omitidos:", *[f"- {s}" for s in skipped[:30]]])

    remaining = max_chars - sum(len(x) + 1 for x in lines)
    blocks: list[str] = []
    for p in files:
        if remaining <= 0:
            break
        rel = p.relative_to(root).as_posix()
        text = p.read_text(encoding="utf-8", errors="replace")
        chunk = text[:min(MAX_FILE_CHARS, remaining)]
        blocks.append(f"\n--- archivo {rel} ---\n{chunk}")
        remaining -= len(chunk) + len(rel) + 20
    content = "\n".join(lines + blocks)
    if len(content) > max_chars:
        content = content[:max_chars] + "\n...[recortado por presupuesto]"
    source = {
        "kind": "folder",
        "path": target.relative_to(root).as_posix() if target != root else ".",
        "files_included": [p.relative_to(root).as_posix() for p in files],
        "files_skipped": skipped[:30],
        "max_chars": max_chars,
        "max_files": max_files,
    }
    return content, source


def load(project_root: str | None, attachment_id: str) -> dict[str, Any] | None:
    p = _attachment_dir(project_root, attachment_id) / "attachment.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def content(project_root: str | None, attachment_id: str,
            max_chars: int = MAX_CONTEXT_CHARS) -> str:
    d = _attachment_dir(project_root, attachment_id)
    p = d / "content.txt"
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8", errors="replace")
    return text[:max_chars]


def list_attachments(project_root: str | None = None,
                     limit: int = 50) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    root = _attachments_dir(project_root)
    for p in sorted(root.glob("*/attachment.json"),
                    key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def context_block(project_root: str | None, ids: list[str],
                  max_total: int = MAX_CONTEXT_CHARS) -> str:
    if not ids:
        return ""
    blocks: list[str] = []
    remaining = max_total
    for attachment_id in ids:
        meta = load(project_root, attachment_id)
        if not meta:
            continue
        text = content(project_root, attachment_id, remaining)
        header = (
            f"--- adjunto {meta.get('name')} "
            f"({meta.get('mode')}, {meta.get('mime')}, id={attachment_id}) ---"
        )
        source = meta.get("source") or {}
        if source.get("path"):
            bits = [f"origen: {source.get('path')}"]
            if source.get("selection"):
                bits.append(f"seleccion: {source.get('selection')}")
            header = header + "\n" + " | ".join(bits)
        if text:
            block = f"{header}\n{text}"
        else:
            block = f"{header}\n[adjunto binario/no textual; usar como referencia, no como texto]"
        blocks.append(block)
        remaining -= len(text)
        if remaining <= 0:
            break
    if not blocks:
        return ""
    return "=== Adjuntos del turno ===\n" + "\n\n".join(blocks)
