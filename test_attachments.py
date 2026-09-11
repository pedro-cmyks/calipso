#!/usr/bin/env python3
"""
test_attachments.py - adjuntos de chat persistentes.
"""
import importlib
import os
import tempfile
import base64
import pathlib

_HOME = tempfile.mkdtemp(prefix="calipso_attachments_home_")
_ROOT = tempfile.mkdtemp(prefix="calipso_attachments_root_")
os.environ["CALIPSO_HOME"] = _HOME
os.environ["CALIPSO_ROOT"] = _ROOT

from fastapi.testclient import TestClient  # noqa: E402
from calipso import attachments, goals, jobs  # noqa: E402

server = importlib.import_module("calipso.server")  # noqa: E402


def main() -> int:
    fails = []

    def check(name, cond, extra=""):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' ' + extra) if extra else ''}")
        if not cond:
            fails.append(name)

    client = TestClient(server.app)
    client.cookies.set(server.COOKIE, server.TOKEN)
    goal = goals.create(_ROOT, "usar adjuntos reales")
    resp = client.post("/api/attachments", json={
        "name": "contexto.txt",
        "content": "dato importante para Calipso\n",
        "mode": "editable",
        "mime": "text/plain",
        "encoding": "text",
        "source": {
            "kind": "editor_selection",
            "path": "contexto.txt",
            "selection": "1:1-1:29",
        },
    })
    data = resp.json()
    att = data.get("attachment")
    job = data.get("job")
    check("sube adjunto", resp.status_code == 200 and att and att["name"] == "contexto.txt")
    check("crea job adjunto", job and job["kind"] == "attachment" and job["status"] == "done")
    check("artifact adjunto", any(a["name"] == "contexto.txt" for a in jobs.artifacts(_ROOT, job["id"])))
    loaded = client.get(f"/api/attachments/{att['id']}").json()
    check("lee adjunto", "dato importante" in loaded["content"])
    check("metadata editable", loaded["attachment"]["mode"] == "editable")
    check("metadata origen", loaded["attachment"]["source"]["path"] == "contexto.txt")
    block = attachments.context_block(_ROOT, [att["id"]])
    check("context block", "Adjuntos del turno" in block and "dato importante" in block)
    check("context block origen", "origen: contexto.txt" in block and "seleccion: 1:1-1:29" in block)
    updated = goals.load(_ROOT, goal["id"])
    check("evidencia en meta", updated and updated["evidence"][-1]["kind"] == "attachment")
    img_resp = client.post("/api/attachments", json={
        "name": "captura.png",
        "content": base64.b64encode(b"\x89PNG\r\n\x1a\nmini").decode("ascii"),
        "mode": "read_only",
        "mime": "image/png",
        "encoding": "base64",
        "source": {"kind": "image_upload"},
    })
    img = img_resp.json().get("attachment")
    img_job = img_resp.json().get("job")
    check("sube imagen", img_resp.status_code == 200 and img["mime"] == "image/png")
    check("imagen como binario", img["encoding"] == "base64" and img["context_chars"] == 0)
    img_artifacts = jobs.artifacts(_ROOT, img_job["id"])
    check("artifact imagen", any(a["name"] == "captura.png" and a["size"] > 0 for a in img_artifacts))
    img_block = attachments.context_block(_ROOT, [img["id"]])
    check("context block imagen", "adjunto binario/no textual" in img_block)
    docs = pathlib.Path(_ROOT) / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "intro.md").write_text("# Intro\nDato de carpeta\n", encoding="utf-8")
    (docs / "config.json").write_text('{"ok": true}\n', encoding="utf-8")
    (docs / "logo.bin").write_bytes(b"\x00\x01")
    folder_resp = client.post("/api/attachments/folder", json={
        "path": "docs",
        "mode": "read_only",
        "max_chars": 2000,
        "max_files": 10,
    })
    folder_data = folder_resp.json()
    folder = folder_data.get("attachment")
    folder_job = folder_data.get("job")
    check("adjunta carpeta", folder_resp.status_code == 200 and folder["source"]["kind"] == "folder")
    check("carpeta incluye archivos", "docs/intro.md" in folder["source"]["files_included"])
    folder_loaded = client.get(f"/api/attachments/{folder['id']}").json()
    check("carpeta legible", "Dato de carpeta" in folder_loaded["content"])
    folder_artifacts = jobs.artifacts(_ROOT, folder_job["id"])
    check("artifact carpeta", any(a["name"].endswith(".md") for a in folder_artifacts))
    folder_block = attachments.context_block(_ROOT, [folder["id"]])
    check("context block carpeta", "Carpeta adjunta: docs" in folder_block and "docs/config.json" in folder_block)

    # ── Vision API ────────────────────────────────────────────────────────────
    check("is_image PNG", attachments.is_image("image/png"))
    check("is_image JPEG", attachments.is_image("image/jpeg"))
    check("is_image texto no", not attachments.is_image("text/plain"))
    check("has_images detecta imagen", attachments.has_images(_ROOT, [img["id"]]))
    check("has_images ignora texto", not attachments.has_images(_ROOT, []))
    b64_result = attachments.image_bytes_b64(_ROOT, img["id"])
    check("image_bytes_b64 devuelve tuple", b64_result is not None and len(b64_result) == 2)
    # vision_describe sin backend disponible devuelve None (sin API key ni modelo local)
    import os as _os
    _orig_key = _os.environ.pop("ANTHROPIC_API_KEY", None)
    from calipso import aduana
    desc = attachments.vision_describe(_ROOT, [img["id"]], quien=aduana.Quien(
        origen="gesto", proyecto="prueba", desde={"credencial": "maquina"}))
    if _orig_key:
        _os.environ["ANTHROPIC_API_KEY"] = _orig_key
    check("vision_describe sin backend retorna None", desc is None)

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: adjuntos persistentes funcionando")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
