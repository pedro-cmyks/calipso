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

IMAGE_MIMES = {
    "image/png", "image/jpeg", "image/jpg", "image/gif",
    "image/webp", "image/bmp", "image/tiff",
}
_ANTHROPIC_VISION_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
_OLLAMA_VISION_NAMES = {"llava", "moondream", "bakllava", "llava-phi3", "minicpm-v",
                         "llava-llama3", "qwen2-vl", "llama3.2-vision"}

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


def is_image(mime: str | None) -> bool:
    return bool(mime) and mime.split(";")[0].strip().lower() in IMAGE_MIMES


def image_bytes_b64(project_root: str | None, attachment_id: str) -> tuple[str, str] | None:
    """Devuelve (base64_str, media_type) para adjuntos de imagen, o None si no es imagen."""
    meta = load(project_root, attachment_id)
    if not meta or not is_image(meta.get("mime")):
        return None
    d = _attachment_dir(project_root, attachment_id)
    raw_path = d / "content.bin"
    if not raw_path.exists():
        raw_path = d / "content.txt"
        if not raw_path.exists():
            return None
    try:
        raw = raw_path.read_bytes()
        b64 = base64.b64encode(raw).decode("ascii")
        media_type = (meta.get("mime") or "image/png").split(";")[0].strip()
        return b64, media_type
    except Exception:
        return None


def has_images(project_root: str | None, ids: list[str]) -> bool:
    for aid in ids:
        meta = load(project_root, aid)
        if meta and is_image(meta.get("mime")):
            return True
    return False


def ollama_vision_model() -> str | None:
    return None


def vision_describe(project_root: str | None, ids: list[str],
                    question: str = "Describe en detalle lo que ves en esta imagen.") -> str | None:
    """Describe imagen(es) con el motor de visión disponible.
    Prioridad: SDK Anthropic (ANTHROPIC_API_KEY) > Ollama vision model.
    Devuelve texto con la descripción, o None si no hay capacidad de visión."""
    image_ids = [aid for aid in ids
                 if (m := load(project_root, aid)) and is_image(m.get("mime"))]
    if not image_ids:
        return None

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        return _vision_anthropic(project_root, image_ids, question, api_key)

    vm = ollama_vision_model()
    if vm:
        return _vision_ollama(project_root, image_ids, question, vm)

    return None


def _vision_anthropic(project_root: str | None, image_ids: list[str],
                      question: str, api_key: str) -> str | None:
    try:
        import anthropic as _ant
        client = _ant.Anthropic(api_key=api_key)
        content: list = []
        for aid in image_ids:
            result = image_bytes_b64(project_root, aid)
            if not result:
                continue
            b64, media_type = result
            if media_type not in _ANTHROPIC_VISION_MIMES:
                continue
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64},
            })
        if not content:
            return None
        content.append({"type": "text", "text": question})
        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=1024,
            messages=[{"role": "user", "content": content}],
        )
        return msg.content[0].text if msg.content else None
    except Exception as e:
        return f"[vision SDK error: {e}]"


def _vision_ollama(project_root: str | None, image_ids: list[str],
                   question: str, model: str) -> str | None:
    try:
        import urllib.request as _ur, json as _j
        images_b64 = []
        for aid in image_ids:
            result = image_bytes_b64(project_root, aid)
            if result:
                images_b64.append(result[0])
        if not images_b64:
            return None
        payload = _j.dumps({
            "model": model, "prompt": question,
            "images": images_b64, "stream": False,
        }).encode()
        req = _ur.Request("http://localhost:11434/api/generate", data=payload,
                          method="POST")
        req.add_header("Content-Type", "application/json")
        with _ur.urlopen(req, timeout=60) as r:
            return _j.loads(r.read()).get("response", "").strip() or None
    except Exception as e:
        return f"[vision Ollama error: {e}]"


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
