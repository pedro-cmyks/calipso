#!/usr/bin/env python3
"""
calipso/server.py Ã¢â‚¬â€ Servidor de Calipso (Hito 1: visor/editor de cÃƒÂ³digo).

Sirve una UI web con un ÃƒÂ¡rbol de archivos + editor Monaco. Es el primer "cuerpo"
alrededor del cerebro (dispatch.py). MÃƒÂ¡s adelante aquÃƒÂ­ se cuelgan:
  - el chat (WebSocket que llama al router y streamea),
  - el envoltorio de escritorio (Tauri/Electron),
  - el acceso remoto (Tailscale) / bot de WhatsApp.

Arranque:
    python -m uvicorn calipso.server:app --reload --port 8000
o:
    python calipso/server.py
Luego abre http://localhost:8000

Seguridad: todas las rutas de archivo se resuelven y se valida que queden DENTRO
de CALIPSO_ROOT (anti path-traversal).
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import dataclasses
import datetime
import datetime as _dt
import difflib
import hashlib
import hmac
import io
import json
import os
import pathlib
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# El cerebro (router) y la memoria viven en el repo raÃƒÂ­z / paquete calipso.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import dispatch  # noqa: E402
from calipso import capabilities  # noqa: E402
from calipso import attachments  # noqa: E402
from calipso import chats  # noqa: E402
from calipso import config as calipso_config  # noqa: E402
from calipso import browser as calipso_browser  # noqa: E402
from calipso import catastro  # noqa: E402
from calipso import chronology as calipso_chronology  # noqa: E402
from calipso import connectors as calipso_connectors  # noqa: E402
from calipso import costs  # noqa: E402
from calipso import developer  # noqa: E402
from calipso import deps  # noqa: E402
from calipso import discovery  # noqa: E402
from calipso import github as calipso_github  # noqa: E402
from calipso import learning  # noqa: E402
from calipso import goals  # noqa: E402
from calipso import jobs  # noqa: E402
from calipso import librarian  # noqa: E402
from calipso import orchestrator  # noqa: E402
try:
    from calipso import resource_dispatcher as _rd  # noqa: E402
except Exception:
    _rd = None  # type: ignore[assignment]
from calipso import prompt_compiler  # noqa: E402
from calipso import routines as calipso_routines  # noqa: E402
from calipso import backup as calipso_backup  # noqa: E402
from calipso import sessions  # noqa: E402
from calipso import skills  # noqa: E402
from calipso import telemetry  # noqa: E402
from calipso import web as calipso_web  # noqa: E402
from calipso import verification  # noqa: E402
from calipso.tools import commands as calipso_commands  # noqa: E402
from calipso.memory import Memory  # noqa: E402

# RaÃƒÂ­z del proyecto que Calipso muestra/edita. Por defecto, el cwd.
ROOT = pathlib.Path(os.environ.get("CALIPSO_ROOT", os.getcwd())).resolve()
WEB = pathlib.Path(__file__).parent / "web"

# Carpetas que no tiene sentido mostrar en el ÃƒÂ¡rbol.
IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}
# No abrir archivos enormes en el editor.
MAX_FILE_BYTES = 2_000_000

app = FastAPI(title="Calipso")

# --------------------------------------------------------------------------
# SEGURIDAD: token de acceso (defensa en capas, ademÃƒÂ¡s de la red privada)
# --------------------------------------------------------------------------
# Calipso tiene acceso a TODOS tus archivos -> aunque estÃƒÂ© en una red privada
# (Tailscale), exige un token. Se toma de CALIPSO_TOKEN o ~/.calipso/token;
# si no existe, se genera uno y se imprime en consola al arrancar.

COOKIE = "calipso_token"
_TOKEN_FILE = pathlib.Path(os.path.expanduser("~/.calipso")) / "token"
_TOTP_SECRET_FILE = pathlib.Path(os.path.expanduser("~/.calipso")) / "totp_secret"


def _load_token() -> str:
    if (env := os.environ.get("CALIPSO_TOKEN")):
        return env
    if _TOKEN_FILE.exists():
        return _TOKEN_FILE.read_text(encoding="utf-8").strip()
    tok = secrets.token_urlsafe(12)
    _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOKEN_FILE.write_text(tok, encoding="utf-8")
    return tok


TOKEN = _load_token()


def _valid(provided: str | None) -> bool:
    return bool(provided) and hmac.compare_digest(provided, TOKEN)


def _get_totp_secret() -> str:
    if _TOTP_SECRET_FILE.exists():
        return _TOTP_SECRET_FILE.read_text(encoding="utf-8").strip()
    raw = secrets.token_bytes(20)
    secret = base64.b32encode(raw).decode("ascii").rstrip("=")
    _TOTP_SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TOTP_SECRET_FILE.write_text(secret, encoding="utf-8")
    return secret


def _totp_code(secret: str, counter: int) -> str:
    padded = secret + ("=" * ((8 - len(secret) % 8) % 8))
    key = base64.b32decode(padded, casefold=True)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def _verify_totp(code: str, valid_window: int = 1) -> bool:
    clean = "".join(ch for ch in code if ch.isdigit())
    if len(clean) != 6:
        return False
    secret = _get_totp_secret()
    now = int(time.time() // 30)
    return any(
        hmac.compare_digest(clean, _totp_code(secret, now + offset))
        for offset in range(-valid_window, valid_window + 1)
    )


def _provisioning_uri() -> str:
    secret = _get_totp_secret()
    label = urllib.parse.quote("Calipso:Pedro")
    issuer = urllib.parse.quote("Calipso")
    return (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={issuer}&algorithm=SHA1&digits=6&period=30"
    )


def _qr_png_data_uri() -> str | None:
    try:
        import qrcode
    except Exception:
        return None
    img = qrcode.make(_provisioning_uri())
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def _session_response(url: str = "/") -> RedirectResponse:
    resp = RedirectResponse(url=url, status_code=303)
    resp.set_cookie(COOKIE, TOKEN, httponly=True, samesite="lax",
                    max_age=31_536_000)
    return resp


LOGIN_HTML = """<!doctype html><html lang=es><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Calipso - acceso</title>
<style>body{background:#1e1e1e;color:#d4d4d4;font-family:system-ui;display:flex;
height:100vh;margin:0;align-items:center;justify-content:center}
.c{text-align:center;width:min(340px,92vw)}input{background:#252526;border:1px solid #333;color:#d4d4d4;
padding:11px 13px;border-radius:8px;font-size:20px;letter-spacing:4px;text-align:center;width:240px}
button{background:#4ea1ff;color:#fff;border:0;padding:11px 18px;border-radius:8px;
font-size:15px;margin-top:10px;cursor:pointer}.l{color:#4ea1ff;font-weight:700;font-size:22px}
.m{color:#888;font-size:13px;line-height:1.45}.err{color:#f48771;font-size:13px}</style>
<div class=c><div class=l>Calipso</div>{totp_mode}
{error}
<form method=post action="/login">
<input name=code inputmode=numeric autocomplete=one-time-code pattern="[0-9 ]{{6,8}}"
autofocus placeholder="000000" maxlength=8><br><button>Entrar</button></form>
<p class=m>Recuperacion: agrega <code>?token=</code> con el token de
<code>~/.calipso/token</code>. NUNCA se imprime aca: esta pagina la sirve
el server sin autenticar.</p></div>
</html>"""


SETUP_HTML = """<!doctype html><html lang=es><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Calipso - TOTP</title>
<style>body{background:#1e1e1e;color:#d4d4d4;font-family:system-ui;display:flex;
min-height:100vh;margin:0;align-items:center;justify-content:center}
.c{width:min(520px,92vw);text-align:center}.l{color:#4ea1ff;font-weight:700;font-size:22px}
.box{background:#252526;border:1px solid #333;border-radius:10px;padding:18px;margin-top:14px}
img{width:260px;height:260px;image-rendering:pixelated;background:white;padding:12px;border-radius:8px}
code{display:block;overflow:auto;text-align:left;background:#1e1e1e;border:1px solid #333;
padding:10px;border-radius:8px;color:#d4d4d4}.m{color:#aaa;font-size:13px;line-height:1.5}
a{color:#4ea1ff}</style><div class=c><div class=l>Calipso</div>
<h2>Configurar autenticador</h2><div class=box>{qr}<p class=m>Escanea este QR con Microsoft Authenticator,
Google Authenticator o similar. Luego entra por <a href="/login">/login</a> con el codigo de 6 digitos.</p>
<code>{uri}</code></div></div></html>"""


SETUP_DONE_HTML = """<!doctype html><html lang=es><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Calipso - TOTP configurado</title>
<style>body{background:#1e1e1e;color:#d4d4d4;font-family:system-ui;display:flex;
height:100vh;margin:0;align-items:center;justify-content:center}
.c{text-align:center;width:min(420px,92vw)}.l{color:#4ea1ff;font-weight:700;font-size:22px}
.m{color:#aaa;font-size:14px;line-height:1.5}a{color:#4ea1ff}</style>
<div class=c><div class=l>Calipso</div><h2>TOTP ya esta configurado</h2>
<p class=m>Por seguridad, esta pantalla ya no muestra el QR ni el secreto.
Usa <a href="/login">/login</a> para entrar con tu autenticador.</p></div></html>"""


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    path = request.url.path
    if path == "/login":
        return await call_next(request)
    if _valid(request.cookies.get(COOKIE)):
        return await call_next(request)
    if _valid(request.query_params.get("token")):
        if path.startswith("/api") or request.method != "GET":
            resp = await call_next(request)
            resp.set_cookie(COOKIE, TOKEN, httponly=True, samesite="lax",
                            max_age=31_536_000)
            return resp
        return _session_response(path)
    if path.startswith("/api") or path.startswith("/ws"):
        return JSONResponse({"detail": "no autorizado"}, status_code=401)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/login")
def login_page() -> HTMLResponse:
    mode = ('<p style="color:#4ea1ff;font-size:13px">TOTP desactivado — ingresa cualquier codigo</p>'
            if _TOTP_DISABLED else "<p>Codigo de autenticador</p>")
    return HTMLResponse(LOGIN_HTML.replace("{error}", "").replace("{totp_mode}", mode))


_TOTP_DISABLED = os.environ.get("CALIPSO_NO_TOTP", "").strip().lower() in ("1", "true", "yes")


@app.post("/login")
async def login_submit(request: Request):
    body = (await request.body()).decode("utf-8", errors="ignore")
    data = urllib.parse.parse_qs(body)
    code = data.get("code", [""])[0]
    if _TOTP_DISABLED or _verify_totp(code):
        return _session_response("/")
    error = '<p class="err">Codigo invalido. Revisa el autenticador y vuelve a intentar.</p>'
    mode = ('<p style="color:#4ea1ff;font-size:13px">TOTP desactivado — ingresa cualquier codigo</p>'
            if _TOTP_DISABLED else "<p>Codigo de autenticador</p>")
    return HTMLResponse(LOGIN_HTML.replace("{error}", error).replace("{totp_mode}", mode), status_code=401)


@app.get("/setup")
def setup_page() -> HTMLResponse:
    if _TOTP_SECRET_FILE.exists():
        return HTMLResponse(SETUP_DONE_HTML)
    uri = _provisioning_uri()
    qr_data = _qr_png_data_uri()
    if qr_data:
        qr = f'<img src="{qr_data}" alt="QR de Calipso">'
    else:
        qr = '<p class=m>No esta instalado el generador de QR. Usa el enlace de abajo.</p>'
    html = SETUP_HTML.replace("{qr}", qr).replace("{uri}", uri)
    return HTMLResponse(html)


def _safe(rel: str) -> pathlib.Path:
    """Resuelve 'rel' dentro de ROOT o lanza 400 si se sale (path-traversal)."""
    p = (ROOT / rel).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise HTTPException(status_code=400, detail="ruta fuera del proyecto")
    return p


def _build_tree(directory: pathlib.Path) -> list[dict]:
    """ÃƒÂrbol anidado de archivos/carpetas, carpetas primero y ordenado."""
    try:
        entries = list(directory.iterdir())
    except OSError:
        return []
    entries.sort(key=lambda e: (e.is_file(), e.name.lower()))
    out: list[dict] = []
    for e in entries:
        if e.name.startswith(".") or e.name in IGNORE_DIRS:
            continue
        rel = e.relative_to(ROOT).as_posix()
        if e.is_dir():
            out.append({"name": e.name, "path": rel, "type": "dir",
                        "children": _build_tree(e)})
        else:
            out.append({"name": e.name, "path": rel, "type": "file"})
    return out


@app.get("/api/tree")
def api_tree() -> dict:
    return {"root": ROOT.name, "path": str(ROOT), "tree": _build_tree(ROOT)}


@app.get("/api/file")
def api_get_file(path: str) -> dict:
    p = _safe(path)
    if not p.is_file():
        raise HTTPException(status_code=404, detail="no es un archivo")
    if p.stat().st_size > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="archivo demasiado grande")
    raw = p.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=415, detail="archivo binario, no editable")
    return {"path": path, "content": text}


class SaveBody(BaseModel):
    path: str
    content: str


class ProposalBody(BaseModel):
    path: str
    content: str
    source: str = "editor"


class AttachmentBody(BaseModel):
    name: str
    content: str
    mode: str = "read_only"
    mime: str | None = None
    encoding: str = "text"
    source: dict | None = None


class FolderAttachmentBody(BaseModel):
    path: str = ""
    mode: str = "read_only"
    max_chars: int = 12_000
    max_files: int = 40


class GoalBody(BaseModel):
    objective: str
    title: str | None = None
    criteria: list | None = None
    subtasks: list | None = None
    make_active: bool = True


class GoalUpdateBody(BaseModel):
    title: str | None = None
    objective: str | None = None
    status: str | None = None
    criteria: list | None = None
    subtasks: list | None = None
    blocker: str | None = None
    active: bool | None = None


class GoalEvidenceBody(BaseModel):
    kind: str = "note"
    text: str
    data: dict | None = None


class GoalCriterionBody(BaseModel):
    done: bool = True
    evidence: str | None = None


class GoalSubtaskBody(BaseModel):
    status: str = "done"


class CommandRunBody(BaseModel):
    command_id: str
    goal_id: str | None = None
    timeout: int | None = None


class VerificationRunBody(BaseModel):
    goal_id: str | None = None
    commands: list[dict] | None = None
    files: list[dict] | None = None
    proposals: list[dict] | None = None


class MemoryProposalBody(BaseModel):
    text: str
    scope: str = "project"
    target: str = "aprendido"
    rationale: str | None = None
    source: dict | None = None


class MemoryProposalUpdateBody(BaseModel):
    text: str | None = None
    scope: str | None = None
    target: str | None = None
    rationale: str | None = None


class MemorySuggestBody(BaseModel):
    text: str
    source: dict | None = None


class MemoryDiscardBody(BaseModel):
    reason: str | None = None


class ChronologyProposalBody(BaseModel):
    text: str
    topic: str = "Pedro"
    date: str | None = None
    rationale: str | None = None


@app.put("/api/file")
def api_save_file(body: SaveBody) -> dict:
    p = _safe(body.path)
    if p.is_dir():
        raise HTTPException(status_code=400, detail="es una carpeta")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body.content, encoding="utf-8", newline="")
    return {"ok": True, "bytes": len(body.content.encode("utf-8"))}


@app.get("/api/attachments")
def api_attachments(limit: int = 50) -> dict:
    return {"attachments": attachments.list_attachments(str(ROOT), limit)}


@app.post("/api/attachments")
def api_attachment_create(body: AttachmentBody) -> dict:
    meta = attachments.create(
        str(ROOT), body.name, body.content, mode=body.mode,
        mime=body.mime, encoding=body.encoding, source=body.source)
    active_goal = goals.active(str(ROOT))
    job = jobs.start(
        "attachment", f"Adjunto: {meta['name']}", project_root=str(ROOT),
        attachment_id=meta["id"], goal_id=active_goal.get("id") if active_goal else None,
        mode=meta["mode"], mime=meta["mime"])
    if body.encoding == "text":
        jobs.write_artifact(str(ROOT), job["id"], meta["name"], body.content,
                            content_type=meta["mime"])
    else:
        try:
            raw = base64.b64decode(body.content.encode("ascii"), validate=False)
        except Exception:
            raw = b""
        jobs.write_artifact(str(ROOT), job["id"], meta["name"], raw,
                            content_type=meta["mime"])
    jobs.update(str(ROOT), job["id"], status="done", attachment_id=meta["id"])
    if active_goal:
        goals.add_evidence(
            str(ROOT), active_goal["id"], "attachment",
            f"Adjunto agregado: {meta['name']}",
            job_id=job["id"], attachment_id=meta["id"], mode=meta["mode"])
    return {"attachment": meta, "job": jobs.load(str(ROOT), job["id"])}


@app.post("/api/attachments/folder")
def api_attachment_folder(body: FolderAttachmentBody) -> dict:
    _safe(body.path or ".")
    try:
        content, source = attachments.folder_bundle(
            str(ROOT), body.path or "", max_chars=body.max_chars, max_files=body.max_files)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    label = source.get("path") or "."
    meta = attachments.create(
        str(ROOT), f"carpeta {label}", content,
        mode=body.mode if body.mode in {"read_only", "editable"} else "read_only",
        mime="text/markdown", encoding="text", source=source)
    active_goal = goals.active(str(ROOT))
    job = jobs.start(
        "attachment", f"Adjunto carpeta: {label}", project_root=str(ROOT),
        attachment_id=meta["id"], goal_id=active_goal.get("id") if active_goal else None,
        mode=meta["mode"], mime=meta["mime"], path=label)
    jobs.write_artifact(str(ROOT), job["id"], f"{meta['name']}.md", content,
                        content_type=meta["mime"])
    jobs.update(str(ROOT), job["id"], status="done", attachment_id=meta["id"])
    if active_goal:
        goals.add_evidence(
            str(ROOT), active_goal["id"], "attachment",
            f"Carpeta adjunta: {label}",
            job_id=job["id"], attachment_id=meta["id"], mode=meta["mode"],
            path=label, files=len(source.get("files_included") or []))
    return {"attachment": meta, "job": jobs.load(str(ROOT), job["id"])}


@app.get("/api/attachments/{attachment_id}")
def api_attachment(attachment_id: str) -> dict:
    meta = attachments.load(str(ROOT), attachment_id)
    if not meta:
        raise HTTPException(status_code=404, detail="adjunto no existe")
    return {
        "attachment": meta,
        "content": attachments.content(str(ROOT), attachment_id),
    }


PENDING_CHANGES: dict[str, dict] = {}

_RE_CONTINUATION = re.compile(
    r"^\s*(dale|ok|listo|sigue|s[ií]|yes|claro|bueno|perfecto|entendido|genial|"
    r"adelante|hazlo|implement[ao](lo)?|proceed|go ahead|anda|va|venga|"
    r"continua|continúa|exacto|correcto|bien|eso|haz(lo)?|andando)\s*[.!]?\s*$",
    re.IGNORECASE)

_RE_EDIT_INTENT = re.compile(
    r"\b(arregla|arreglar|fixea?|fix|implementa?|refactoriza?|modifica?|añade?|agrega?|"
    r"elimina?|borra?|actualiza?|cambia?|corrige?|edita?|reescribe?|renombra?|mueve?)\b",
    re.IGNORECASE)

_RE_FILE_REF = re.compile(
    r"\b([\w./\-]+\.(py|js|ts|tsx|jsx|html|css|json|yaml|yml|toml|md|sh|sql|cfg|ini))\b")


_RE_UI_TASK = re.compile(
    r"\b(bot[oó]n(es)?|ui\b|interfaz|dise[ñn]o|responsiv|sidebar|drawer|"
    r"layout|componente|modal|css|html|estilo|estiliz|frontend|micr[oó]fon|"
    r"narrar|narraci[oó]n|chat.*panel|panel.*chat|index\.html)\b", re.IGNORECASE)


def _extract_edit_target(message: str, features: dict) -> str | None:
    """Detecta si el mensaje pide editar un archivo conocido en el repo.
    Para tareas de UI sin archivo explícito, cae en index.html."""
    if features.get("type") not in ("code", "repo", "agentic"):
        return None
    if not _RE_EDIT_INTENT.search(message):
        return None
    for m in _RE_FILE_REF.finditer(message):
        candidate = m.group(1)
        target = ROOT / candidate
        if target.is_file():
            return candidate
        name = pathlib.Path(candidate).name
        hits = [p for p in ROOT.rglob(name)
                if not any(skip in p.parts for skip in
                           (".git", "__pycache__", ".venv", "node_modules"))]
        if hits:
            return str(hits[0].relative_to(ROOT))
    # Fallback: tarea de UI sin archivo explícito → index.html
    if _RE_UI_TASK.search(message):
        ui_file = ROOT / "calipso" / "web" / "index.html"
        if ui_file.is_file():
            return "calipso/web/index.html"
    return None


async def _run_chat_draft(ws, chat_msg: str, file_path: str,
                          agente_id: str | None = None,
                          departamento: str | None = None) -> None:
    """Genera borrador desde chat y emite evento 'proposal' por WebSocket.

    Es su propio agente del pulso, no un rastro del turno que lo lanzo: se
    corre con `ensure_future` y llama a otro modelo, asi que su `diff`
    llegaria despues del `fin` del turno y dejaria ese escritorio ocupado
    por un fantasma."""
    with _pulso_agente(agente_id, departamento=departamento, rol="borrador",
                       modelo="sonnet") as mango:
        active_goal = await asyncio.to_thread(goals.active, str(ROOT))
        brief = developer.chat_draft_brief(str(ROOT), chat_msg, file_path, goal=active_goal)
        job = brief["job"]
        try:
            raw = await asyncio.to_thread(
                _run_subscription_text, "claude", brief["system"], brief["user_msg"], "sonnet")
            new_content = developer._strip_fences(raw)
        except Exception as exc:
            jobs.update(str(ROOT), job["id"], status="failed", error=str(exc))
            await ws.send_json({"type": "error", "text": f"borrador fallido: {exc}"})
            return

        # el borrador corre `claude` aparte del turno: consume su propia
        # unidad de suscripcion y la paga el mismo departamento en foco. Va en
        # un hilo porque `_cobrar_turno` toma el candado del libro, igual que
        # el cobro del turno.
        def _cobrar_borrador() -> None:
            _cobrar_turno(_cuenta_en_foco(departamento), "subscription",
                          "claude", "sonnet", {})

        await asyncio.to_thread(_cobrar_borrador)

        change_id = uuid.uuid4().hex[:12]
        item = {
            "id": change_id,
            "path": file_path,
            "source": "chat_draft",
            "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        PENDING_CHANGES[change_id] = {**item, "content": new_content}
        diff = _proposal_diff(file_path, new_content)
        # el rastro del agente: es lo que el popup del empleado muestra como
        # "toco" y lo que el panel de razonamiento pinta abajo del texto
        mango.diff(file_path, diff)

        jobs.write_artifact(str(ROOT), job["id"], "draft.diff", diff)
        jobs.update(str(ROOT), job["id"], status="done",
                    proposal_id=change_id, artifact="draft.diff")

        if active_goal:
            goals.add_evidence(
                str(ROOT), active_goal["id"], "proposal",
                f"Borrador chat para {file_path} (propuesta {change_id})",
                job_id=job["id"], artifact="draft.diff")

        await ws.send_json({
            "type": "proposal",
            "proposal": {**item, "diff": diff},
        })


def _proposal_diff(path: str, content: str) -> str:
    p = _safe(path)
    old = ""
    if p.exists() and p.is_file():
        try:
            old = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            old = "(archivo binario o no legible como texto)\n"
    old_lines = old.splitlines(keepends=True)
    new_lines = content.splitlines(keepends=True)
    return "".join(difflib.unified_diff(
        old_lines, new_lines, fromfile=f"a/{path}", tofile=f"b/{path}"))


@app.get("/api/proposals")
def api_proposals() -> dict:
    return {"proposals": list(PENDING_CHANGES.values())}


@app.post("/api/proposals")
def api_propose_change(body: ProposalBody) -> dict:
    _safe(body.path)
    change_id = uuid.uuid4().hex[:12]
    item = {
        "id": change_id,
        "path": body.path,
        "source": body.source,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    PENDING_CHANGES[change_id] = {**item, "content": body.content}
    return {**item, "diff": _proposal_diff(body.path, body.content)}


@app.get("/api/proposals/{change_id}/diff")
def api_proposal_diff(change_id: str) -> dict:
    item = PENDING_CHANGES.get(change_id)
    if not item:
        raise HTTPException(status_code=404, detail="propuesta no existe")
    return {"id": change_id, "path": item["path"],
            "diff": _proposal_diff(item["path"], item["content"])}


@app.post("/api/proposals/{change_id}/apply")
def api_apply_proposal(change_id: str, verify: bool = False,
                       command_id: str = "py_compile_core") -> dict:
    item = PENDING_CHANGES.get(change_id)
    if not item:
        raise HTTPException(status_code=404, detail="propuesta no existe")
    p = _safe(item["path"])
    if p.is_dir():
        raise HTTPException(status_code=400, detail="es una carpeta")
    diff = _proposal_diff(item["path"], item["content"])
    p.parent.mkdir(parents=True, exist_ok=True)

    # screenshot before/after para cambios de UI
    screenshots: dict[str, str] = {}
    _is_ui = calipso_browser.is_ui_file(item["path"])
    if _is_ui:
        try:
            def _write_file():
                p.write_text(item["content"], encoding="utf-8", newline="")
            before_png, after_png = calipso_browser.before_after_capture(
                "http://localhost:8000", _write_file)
            screenshots["before"] = __import__("base64").b64encode(before_png).decode()
            screenshots["after"] = __import__("base64").b64encode(after_png).decode()
        except Exception:
            p.write_text(item["content"], encoding="utf-8", newline="")
    else:
        p.write_text(item["content"], encoding="utf-8", newline="")

    del PENDING_CHANGES[change_id]
    active_goal = goals.active(str(ROOT))
    job = jobs.start(
        "proposal_apply", f"Aplicar propuesta: {item['path']}",
        project_root=str(ROOT), goal_id=active_goal.get("id") if active_goal else None,
        path=item["path"], source=item.get("source"))
    jobs.write_artifact(str(ROOT), job["id"], "proposal.diff", diff)
    jobs.write_artifact(str(ROOT), job["id"], "applied-content.txt", item["content"])
    if screenshots.get("before"):
        jobs.write_artifact(str(ROOT), job["id"], "ui_before.png",
                            __import__("base64").b64decode(screenshots["before"]))
        jobs.write_artifact(str(ROOT), job["id"], "ui_after.png",
                            __import__("base64").b64decode(screenshots["after"]))
    jobs.update(str(ROOT), job["id"], status="done", path=item["path"])
    jobs.event(str(ROOT), job["id"], "applied", path=item["path"])
    if active_goal:
        goals.add_evidence(
            str(ROOT), active_goal["id"], "proposal",
            f"Propuesta aplicada: {item['path']}",
            job_id=job["id"], path=item["path"], artifact="proposal.diff")
    verification_result = None
    if verify:
        plan = verification.recommend([{"path": item["path"], "status": "proposal"}], [])
        if command_id and command_id != "auto":
            known = {c["id"]: c for c in calipso_commands.list_commands()}
            if command_id not in known:
                raise HTTPException(status_code=400, detail="comando no permitido")
            plan["commands"] = [{
                "command_id": command_id,
                "title": known[command_id]["title"],
                "reason": "forzado desde propuesta",
            }]
            plan["summary"] = command_id
        verification_result = verification.run_plan(
            str(ROOT), plan, active_goal.get("id") if active_goal else None)
    return {
        "ok": True,
        "path": item["path"],
        "job": jobs.load(str(ROOT), job["id"]),
        "goal": goals.active(str(ROOT)),
        "screenshots": screenshots if screenshots else None,
        "verification": {
            "job": verification_result["job"],
            "status": verification_result["report"]["status"],
            "returncode": 0 if verification_result["report"]["status"] == "done" else 1,
        } if verification_result else None,
    }


@app.delete("/api/proposals/{change_id}")
def api_discard_proposal(change_id: str) -> dict:
    if change_id not in PENDING_CHANGES:
        raise HTTPException(status_code=404, detail="propuesta no existe")
    item = PENDING_CHANGES.pop(change_id)
    return {"ok": True, "path": item["path"]}


# --------------------------------------------------------------------------
# GIT  (estado y diffs para confirmar cambios antes de confiar)
# --------------------------------------------------------------------------

def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(ROOT), text=True, capture_output=True,
        encoding="utf-8", errors="replace", timeout=10)


def _git_available() -> bool:
    return _git(["rev-parse", "--is-inside-work-tree"]).returncode == 0


@app.get("/api/git/status")
def api_git_status() -> dict:
    if not _git_available():
        return {"available": False, "clean": True, "branch": None, "files": []}
    branch = _git(["branch", "--show-current"]).stdout.strip() or "HEAD"
    raw = _git(["status", "--porcelain=v1"]).stdout.splitlines()
    files = []
    for line in raw:
        if not line:
            continue
        status = line[:2]
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.append({
            "path": path,
            "status": status,
            "index": status[0],
            "worktree": status[1],
        })
    return {
        "available": True,
        "clean": not files,
        "branch": branch,
        "files": files,
    }


@app.get("/api/git/diff")
def api_git_diff(path: str | None = None) -> dict:
    if not _git_available():
        raise HTTPException(status_code=404, detail="git no disponible")
    args = ["diff", "--"]
    if path:
        _safe(path)
        args.append(path)
    diff = _git(args)
    if diff.returncode != 0:
        raise HTTPException(status_code=500, detail=diff.stderr.strip() or "git diff fallo")
    text = diff.stdout
    if path and not text:
        p = _safe(path)
        if p.is_file() and path in {f["path"] for f in api_git_status()["files"]}:
            try:
                content = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = "(archivo binario o no legible como texto)"
            text = f"Archivo nuevo o sin diff unstaged para {path}\n\n{content}"
    return {"path": path, "diff": text}


# --------------------------------------------------------------------------
# GITHUB REMOTO  (repos, issues/PRs, repo actual, flujo de contribucion)
# Leer es libre; clonar/branch/fork/PR exigen confirm explicito (SPEC 11).
# --------------------------------------------------------------------------

def _gh_runner():
    return calipso_github.default_runner(cwd=str(ROOT))


@app.get("/api/github/overview")
def api_github_overview() -> dict:
    if not calipso_github.available():
        return {"available": False, "reason": "gh no esta instalado",
                "user": None, "repo": None}
    gh = _gh_runner()
    user = calipso_github.gh_user(gh)
    overview = calipso_github.repo_overview(gh, calipso_github.git_runner(cwd=str(ROOT)))
    return {
        "available": True,
        "authenticated": user["authenticated"],
        "user": user,
        "repo": overview,
    }


@app.get("/api/github/repos")
def api_github_repos(limit: int = 10) -> dict:
    if not calipso_github.available():
        raise HTTPException(status_code=404, detail="gh no esta instalado")
    repos = calipso_github.list_repos(_gh_runner(), limit=max(1, min(limit, 50)))
    return {"repos": repos}


@app.get("/api/github/assigned")
def api_github_assigned(limit: int = 10) -> dict:
    if not calipso_github.available():
        raise HTTPException(status_code=404, detail="gh no esta instalado")
    return calipso_github.assigned_items(_gh_runner(), limit=max(1, min(limit, 50)))


@app.post("/api/github/contribute/plan")
async def api_github_contribute_plan(request: Request) -> dict:
    """Planifica una accion de contribucion SIN ejecutarla."""
    data = await request.json()
    action = data.get("action", "")
    opts = data.get("opts") or {}
    return calipso_github.plan_contribution(action, opts)


@app.post("/api/github/contribute/run")
async def api_github_contribute_run(request: Request) -> dict:
    """Ejecuta una accion de contribucion solo con confirm=True (SPEC 11)."""
    data = await request.json()
    action = data.get("action", "")
    opts = data.get("opts") or {}
    if not data.get("confirm"):
        raise HTTPException(status_code=403,
                            detail="esta accion requiere confirmacion explicita")
    plan = calipso_github.plan_contribution(action, opts)
    if not plan.get("ok"):
        raise HTTPException(status_code=400, detail=plan.get("error", "plan invalido"))
    argv = plan["argv"]
    exe0 = argv[0]
    if exe0 == "gh":
        exe = _cmd_exe("gh") or "gh"
    elif exe0 == "git":
        exe = shutil.which("git") or "git"
    else:
        raise HTTPException(status_code=400, detail="ejecutable no permitido")
    run_cmd = [exe, *argv[1:]]
    try:
        proc = subprocess.run(
            run_cmd, cwd=str(ROOT), text=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=120)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "ok": proc.returncode == 0,
        "action": action,
        "command": plan["command"],
        "code": proc.returncode,
        "stdout": (proc.stdout or "").strip(),
        "stderr": (proc.stderr or "").strip(),
    }


# --------------------------------------------------------------------------
# CONFIG  (harness: rutas, modelos y preferencias de costo)
# --------------------------------------------------------------------------

@app.get("/api/config")
def api_config_get() -> dict:
    return calipso_config.load_config()


@app.put("/api/config")
async def api_config_save(request: Request) -> dict:
    data = await request.json()
    cfg = calipso_config.save_config(data)
    dispatch.CONFIG = calipso_config.dispatch_config()
    return cfg


def _remember_project(path: pathlib.Path) -> None:
    cfg = calipso_config.load_config()
    recent = [p for p in cfg.get("projects", {}).get("recent", []) if p != str(path)]
    recent.insert(0, str(path))
    calipso_config.save_config({"projects": {"recent": recent[:12]}})


@app.get("/api/project")
def api_project() -> dict:
    cfg = calipso_config.load_config()
    return {
        "name": ROOT.name,
        "path": str(ROOT),
        "recent": cfg.get("projects", {}).get("recent", []),
    }


@app.post("/api/project/open")
async def api_project_open(request: Request) -> dict:
    data = await request.json()
    raw = str(data.get("path") or "").strip().strip('"')
    if not raw:
        raise HTTPException(status_code=400, detail="falta ruta")
    _switch_project(raw)
    return {"ok": True, "name": ROOT.name, "path": str(ROOT)}


def _switch_project(path: str) -> None:
    """Unico lugar que de verdad reasigna ROOT -- las cuatro puertas que
    cambian de proyecto (este endpoint, POST /api/chats, activate y el
    turno del websocket) pasan todas por aca, directo o via
    api_project_open. Por eso el techo del catastro (hallazgo S4 del spec
    de ojos y manos) va aca y no en un solo endpoint: ponerlo solo en
    /api/project/open dejaba las otras tres puertas abiertas -- un
    POST /api/chats con {"project_path": "/"} en el body reasignaba ROOT
    igual, y la reasignacion sobrevive al reinicio via _remember_project."""
    global ROOT, mem
    p = pathlib.Path(os.path.expandvars(os.path.expanduser(path))).resolve()
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=400, detail="la ruta no existe o no es carpeta")
    if not catastro.dentro_de_alguna_raiz(p):
        raise HTTPException(
            status_code=400,
            detail="la ruta esta fuera de las raices declaradas del catastro "
                   "(~/.calipso/catastro.json)")
    ROOT = p
    mem = Memory(project_root=str(ROOT))
    _remember_project(ROOT)
    catastro.marcar_visto(ROOT)


@app.get("/api/catastro")
def api_catastro() -> dict:
    """El indice completo (3.4 del spec de ojos y manos): lo que entra al
    prompt de cada turno es un resumen acotado de esto mismo
    (`prompt_compiler.proyectos_brief`); esto es la lista entera, sin
    techo, para la UI."""
    return {"proyectos": catastro.cargar()}


@app.get("/api/catastro/{nombre}")
def api_catastro_detalle(nombre: str) -> dict:
    """El detalle de un proyecto que no esta en foco, sin mover ROOT ni la
    memoria (3.4): `_repo_brief` recibe la raiz del proyecto pedido, no
    lee el global ROOT."""
    proyecto = catastro.obtener(nombre)
    if proyecto is None:
        raise HTTPException(status_code=404,
                            detail="proyecto no encontrado en el catastro")
    raiz = pathlib.Path(proyecto["ruta"])
    return {"proyecto": proyecto, "brief": _repo_brief(raiz)}


def _chat_view(chat: dict) -> dict:
    return {
        "id": chat["id"],
        "title": chat.get("title"),
        "project_path": chat.get("project_path"),
        "project_name": chat.get("project_name"),
        "created_at": chat.get("created_at"),
        "updated_at": chat.get("updated_at"),
        "messages": chat.get("messages", []),
    }


@app.get("/api/chats")
def api_chats() -> dict:
    return {"active": chats.active_id(), "chats": chats.list_chats()}


@app.post("/api/chats")
async def api_chat_create(request: Request) -> dict:
    body = await request.json()
    project_path = str(body.get("project_path") or ROOT)
    title = body.get("title")
    _switch_project(project_path)
    chat = chats.create(str(ROOT), title)
    return _chat_view(chat)


@app.get("/api/chats/{chat_id}")
def api_chat_get(chat_id: str) -> dict:
    chat = chats.get(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="chat no existe")
    return _chat_view(chat)


@app.post("/api/chats/{chat_id}/activate")
def api_chat_activate(chat_id: str) -> dict:
    try:
        chat = chats.set_active(chat_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="chat no existe")
    _switch_project(chat["project_path"])
    return _chat_view(chat)


def _http_up(url: str, timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:
        return False


@app.get("/api/harness/status")
def api_harness_status() -> dict:
    cfg = calipso_config.load_config()
    health = _connector_health(use_cache=False)
    return {
        "routing": cfg["routing"],
        "subscription": health["subscription"],
        "api": health["api"],
        "local": health["local"],
        "limits": health["limits"],
        "classifier": cfg["classifier"],
    }


@app.get("/api/connectors/health")
def api_connectors_health() -> dict:
    health = _connector_health(use_cache=False)
    health["routing"] = calipso_connectors.routing_summary(str(ROOT), health)
    return health


@app.get("/api/subscriptions")
def api_subscriptions() -> dict:
    return {
        "connectors": {
            name: {
                "docs": connector["docs"],
                "state": _subscription_probe(name),
            }
            for name, connector in SUBSCRIPTION_CONNECTORS.items()
        }
    }


@app.get("/api/connectors")
def api_connectors() -> dict:
    return {
        "cli": {
            name: {
                "docs": connector["docs"],
                "state": _cli_probe(name),
            }
            for name, connector in CLI_CONNECTORS.items()
        }
    }


@app.post("/api/connectors/{name}/{action}")
def api_connector_action(name: str, action: str) -> dict:
    connector = CLI_CONNECTORS.get(name)
    if not connector:
        raise HTTPException(status_code=404, detail="conector no soportado")
    if action not in ("install", "login"):
        raise HTTPException(status_code=400, detail="accion no soportada")
    cmd = connector[action]
    exe = _cmd_exe(cmd[0]) or cmd[0]
    run_cmd = [exe] + cmd[1:]
    try:
        subprocess.Popen(
            run_cmd, cwd=str(ROOT), creationflags=subprocess.CREATE_NEW_CONSOLE)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "ok": True,
        "connector": name,
        "message": f"{action} lanzado en una terminal nueva",
        "command": " ".join(run_cmd),
    }


@app.post("/api/subscriptions/{client}/install")
def api_subscription_install(client: str) -> dict:
    connector = _connector_or_404(client)
    cmd = connector["install"]
    try:
        subprocess.Popen(
            cmd, cwd=str(ROOT), creationflags=subprocess.CREATE_NEW_CONSOLE)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "ok": True,
        "client": client,
        "message": "instalacion lanzada en una terminal nueva",
        "command": " ".join(cmd),
    }


@app.post("/api/subscriptions/{client}/login")
def api_subscription_login(client: str) -> dict:
    connector = _connector_or_404(client)
    probe = _subscription_probe(client)
    if not probe["installed"]:
        raise HTTPException(status_code=400, detail="primero instala el CLI")
    cmd = connector["login"]
    try:
        subprocess.Popen(
            cmd, cwd=str(ROOT), creationflags=subprocess.CREATE_NEW_CONSOLE)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {
        "ok": True,
        "client": client,
        "message": "login lanzado en una terminal nueva",
        "command": " ".join(cmd),
    }


# --------------------------------------------------------------------------
# CHAT  (memoria + router + streaming)  Ã¢â‚¬â€ el corazÃƒÂ³n de Calipso
# --------------------------------------------------------------------------

mem = Memory(project_root=str(ROOT))  # memoria hÃƒÂ­brida y por ÃƒÂ¡mbitos (global + proyecto)

calipso_chronology.ensure()

HELP_TEXT = (
    "Comandos de Calipso:\n"
    "  /fast        respuesta rápida y barata (modelo chico)\n"
    "  /think       más esfuerzo (tier medio+)\n"
    "  /ultrathink  máximo esfuerzo (tier frontier: Opus/Fable)\n"
    "  /model <x>   forzar un modelo o persona (opus, codex, Aristoteles…)\n"
    "  /local /claude /codex /api  forzar la ruta\n"
    "  /help        esta ayuda\n"
    "Si no pones nada, Calipso decide solo (modelo + intensidad) por la tarea."
)

SYSTEM = (
    "Eres Calipso, el asistente personal local de Pedro. Respondes en espanol, "
    "directo y util. No dices que eres Alibaba, OpenAI, Anthropic, Claude, Codex "
    "ni Ollama: eres Calipso usando un backend. Si te preguntan que modelo o ruta "
    "usas, respondes solo con el estado real que recibes en el contexto. Si no "
    "sabes algo o una conexion no esta configurada, lo dices sin inventar."
)


def _route_model_name(route: str, client: str | None = None) -> str:
    if route == "api":
        return dispatch.CONFIG["api"]["model"]
    if route == "subscription":
        return client or "subscription"
    return dispatch.CONFIG["local"]["model"]


def _subscription_available(client: str | None) -> bool:
    return _subscription_probe(client)["ready"]


def _subscription_command(client: str) -> str | None:
    if os.name == "nt":
        return shutil.which(f"{client}.cmd") or shutil.which(f"{client}.exe") or shutil.which(client)
    return shutil.which(client)


def _subscription_probe(client: str | None) -> dict:
    if not client:
        return {"installed": False, "ready": False, "error": "sin cliente"}
    exe = _subscription_command(client)
    if not exe:
        return {"installed": False, "ready": False, "error": "no esta en PATH"}
    try:
        result = subprocess.run(
            [exe, "--version"], cwd=str(ROOT), text=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=5)
        executable = result.returncode == 0
        authenticated = None
        if client == "claude" and executable:
            auth = subprocess.run(
                [exe, "auth", "status"], cwd=str(ROOT), text=True,
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=5)
            try:
                authenticated = json.loads(auth.stdout).get("loggedIn", False)
            except Exception:
                authenticated = auth.returncode == 0
        elif client == "codex" and executable:
            auth = subprocess.run(
                [exe, "login", "status"], cwd=str(ROOT), text=True,
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=5)
            auth_text = (auth.stdout or "") + (auth.stderr or "")
            authenticated = auth.returncode == 0 and "Logged in" in auth_text
        ready = executable and (authenticated is not False)
        err = (result.stderr or result.stdout or "").strip().splitlines()
        return {
            "installed": True,
            "executable": executable,
            "authenticated": authenticated,
            "ready": ready,
            "path": exe,
            "error": "" if ready else (
                "no autenticado" if authenticated is False else
                (err[0] if err else f"exit {result.returncode}")),
        }
    except Exception as e:
        return {"installed": True, "ready": False, "path": exe, "error": str(e)}


def _npm_install_cmd(pkg: str) -> list[str]:
    npm = shutil.which("npm.cmd") or shutil.which("npm") or "npm"
    return [npm, "install", "-g", pkg]

SUBSCRIPTION_CONNECTORS = {
    "claude": {
        "install": _npm_install_cmd("@anthropic-ai/claude-code@latest"),
        "login": [shutil.which("claude.cmd") or shutil.which("claude") or "claude", "auth", "login"],
        "docs": "https://code.claude.com/docs/en/setup",
    },
    "codex": {
        "install": _npm_install_cmd("@openai/codex@latest"),
        "login": [shutil.which("codex.cmd") or shutil.which("codex") or "codex", "login"],
        "docs": "https://developers.openai.com/codex/cli",
    },
}

CLI_CONNECTORS = {
    "github": {
        "exe": "gh",
        "install": ["winget", "install", "--id", "GitHub.cli", "-e"],
        "login": ["gh", "auth", "login"],
        "status": ["gh", "auth", "status"],
        "docs": "https://cli.github.com/manual/",
    },
}


def _connector_or_404(client: str) -> dict:
    connector = SUBSCRIPTION_CONNECTORS.get(client)
    if not connector:
        raise HTTPException(status_code=404, detail="conector no soportado")
    return connector


def _cmd_exe(name: str) -> str | None:
    if os.name == "nt":
        return shutil.which(f"{name}.cmd") or shutil.which(f"{name}.exe") or shutil.which(name)
    return shutil.which(name)


def _cli_probe(name: str) -> dict:
    c = CLI_CONNECTORS.get(name)
    if not c:
        return {"installed": False, "ready": False, "error": "conector desconocido"}
    exe = _cmd_exe(c["exe"])
    if not exe:
        return {"installed": False, "ready": False, "error": "no esta en PATH"}
    version = ""
    try:
        ver = subprocess.run(
            [exe, "--version"], cwd=str(ROOT), text=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=5)
        version = (ver.stdout or ver.stderr or "").strip().splitlines()[0] if (ver.stdout or ver.stderr) else ""
    except Exception:
        pass
    try:
        status_cmd = [exe if i == 0 else arg for i, arg in enumerate(c["status"])]
        auth = subprocess.run(
            status_cmd, cwd=str(ROOT), text=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=8)
        text = (auth.stdout or "") + (auth.stderr or "")
        ready = auth.returncode == 0
        return {
            "installed": True, "ready": ready, "path": exe,
            "version": version,
            "error": "" if ready else (text.strip().splitlines()[0] if text.strip() else "no autenticado"),
        }
    except Exception as e:
        return {"installed": True, "ready": False, "path": exe,
                "version": version, "error": str(e)}


def _best_subscription_client(preferred: str | None) -> str | None:
    if _subscription_available(preferred):
        return preferred
    for client in ("codex", "claude"):
        if client != preferred and _subscription_available(client):
            return client
    return None


# Cache TTL para los probes: evita 4 subprocess/http por turno de chat (latencia).
_PROBE_CACHE: dict = {}


def _ttl_cached(key: str, ttl: float, producer):
    now = time.time()
    e = _PROBE_CACHE.get(key)
    if e and now - e[0] < ttl:
        return e[1]
    val = producer()
    _PROBE_CACHE[key] = (now, val)
    return val


def _probe_cached(client: str | None) -> dict:
    return _ttl_cached(f"probe:{client}", 20.0, lambda: _subscription_probe(client))


def _http_up_cached(url: str) -> bool:
    return _ttl_cached(f"up:{url}", 20.0, lambda: _http_up(url))


def _connector_health(use_cache: bool = True) -> dict:
    cfg = calipso_config.load_config()
    api_health_url = cfg["api"]["base_url"].replace("/v1/chat/completions", "/health")
    api_up = _http_up_cached(api_health_url) if use_cache else _http_up(api_health_url)
    local_up = False  # sin Ollama
    sub = {
        "claude": _probe_cached("claude") if use_cache else _subscription_probe("claude"),
        "codex": _probe_cached("codex") if use_cache else _subscription_probe("codex"),
    }
    return calipso_connectors.health_status(
        cfg, costs.monthly_report(), sub, api_up, local_up)


def _backend_availability() -> dict:
    """Mapa {backend_key: disponible} para el router por capacidades."""
    return calipso_connectors.backend_availability(
        capabilities.load_backends(), _connector_health())


def _backend_quota_low() -> dict:
    return calipso_connectors.backend_quota_low(
        capabilities.load_backends(), _connector_health())


def _decide(user_msg: str,
            last_features: dict | None = None,
            last_verdict: dict | None = None) -> tuple[dict, dict, list, dict]:
    """Decisión a nivel de MODELO: directivas (slash/intensidad) -> features ->
    intensidad -> choose(). Devuelve (verdict, features, ranked, directivas)."""
    d = capabilities.parse_directives(user_msg)
    features = dispatch.extract_features(d["clean"])
    # Continuaciones cortas ("dale", "sigue", "ok"...) heredan el contexto anterior
    # para no degradar una tarea code/repo a trivial solo por ser un ack.
    if (last_features and last_verdict
            and _RE_CONTINUATION.match(d["clean"])
            and last_features.get("type") not in (None, "trivial", "translate", "summarize")
            and last_verdict.get("route") in ("subscription", "orchestrator")):
        features["type"] = last_features["type"]
        features["complexity"] = max(features["complexity"], last_features.get("complexity", 2))
        features["needs_repo"] = features["needs_repo"] or last_features.get("needs_repo", False)
    sel_effort = d["effort"] if d["effort"] is not None else capabilities.derive_effort(
        features["complexity"])

    # sesión activa: deshabilita los agentes apagados para ESTA sesión
    prof = sessions.active()
    avail = _backend_availability()
    for mid, a in (prof.get("agents") or {}).items():
        if not a.get("enabled", True):
            avail[mid] = False

    ranked = capabilities.choose(features, sel_effort, avail,
                                 _backend_quota_low(), project_root=str(ROOT))
    if d.get("force_route"):
        ranked = [r for r in ranked if r["route"] == d["force_route"]] or ranked
    if d.get("force_model"):
        fm = d["force_model"].lower()
        forced = [r for r in ranked if fm in (
            r["key"].lower(), (r["model"] or "").lower(), (r["client"] or "").lower(),
            (prof["agents"].get(r["key"], {}).get("name") or r["persona"]).lower())]
        if forced:
            ranked = forced

    if ranked:
        top = ranked[0]
        sess = sessions.apply(prof, top["key"], top.get("persona"), top["route"])
        # intensidad efectiva: slash > intensidad de sesión del agente > derivada
        exec_effort = sel_effort
        if d["effort"] is None and sess["intensity"]:
            exec_effort = capabilities.EFFORT[sess["intensity"]]
        verdict = {
            "route": top["route"], "client": top.get("client"),
            "model": top.get("model"), "model_id": top["key"],
            "persona": sess["name"], "tier": top.get("tier"),
            "effort": exec_effort, "effort_name": capabilities.EFFORT_NAME[exec_effort],
            "session": prof["id"], "source": "capabilities",
            "why": f"{sess['name']} ({top.get('tier')}) para {features['type']} "
                   f"c{features['complexity']} intensidad="
                   f"{capabilities.EFFORT_NAME[exec_effort]} (score {top['score']})",
        }
    else:
        verdict = {"route": "local", "client": None, "model": "qwen2.5:7b",
                   "model_id": "local:qwen2.5:7b", "persona": "Epicteto",
                   "tier": "small", "effort": sel_effort,
                   "effort_name": capabilities.EFFORT_NAME[sel_effort],
                   "session": prof["id"], "source": "capabilities",
                   "why": "ningun modelo apto; local"}
    return verdict, features, ranked, d


def _should_orchestrate(features: dict, directives: dict, message: str) -> bool:
    """Activa equipo dinamico solo cuando suma valor real."""
    if directives.get("force_team"):
        return True  # /plan o /team: planning mode explícito
    if directives.get("effort") == capabilities.EFFORT["fast"]:
        return False
    low = message.lower()
    if len(low.split()) < 10 and features.get("complexity", 1) <= 2:
        return False
    hard_types = {"repo", "agentic", "code", "analysis"}
    if features.get("type") in hard_types and features.get("complexity", 1) >= 3:
        return True
    if features.get("complexity", 1) >= 4:
        return True
    if features.get("needs_web") and features.get("complexity", 1) >= 3:
        return True
    multi_signals = (" y ", " tambien ", " ademas ", " luego ", " despues ")
    return features.get("complexity", 1) >= 3 and any(s in low for s in multi_signals)


def _heuristic_plan(request: str, features: dict) -> dict:
    task_type = features.get("type", "reasoning")
    complexity = int(features.get("complexity", 2) or 2)
    if task_type in {"repo", "agentic", "code"}:
        agents = [
            {"role": "arquitecto", "task": "entender el objetivo y proponer la estrategia tecnica minima",
             "tier": "frontier", "intensity": "think", "type": "agentic", "quirk": "pragmatico"},
            {"role": "ingeniero", "task": request,
             "tier": "frontier", "intensity": "think", "type": task_type, "quirk": "meticuloso"},
            {"role": "revisor", "task": "buscar riesgos, huecos y siguientes pasos concretos",
             "tier": "mid", "intensity": "balanced", "type": "analysis", "quirk": "honesto"},
        ]
    elif features.get("needs_web"):
        agents = [
            {"role": "investigador", "task": "separar hechos verificables de supuestos",
             "tier": "mid", "intensity": "balanced", "type": "analysis", "quirk": "esceptico"},
            {"role": "sintetizador", "task": request,
             "tier": "mid", "intensity": "balanced", "type": task_type, "quirk": "claro"},
        ]
    elif complexity >= 4:
        agents = [
            {"role": "analista", "task": "descomponer el problema y detectar decisiones importantes",
             "tier": "frontier", "intensity": "think", "type": "analysis", "quirk": "preciso"},
            {"role": "redactor", "task": request,
             "tier": "mid", "intensity": "balanced", "type": task_type, "quirk": "directo"},
        ]
    else:
        agents = [{"role": "asistente", "task": request, "tier": "mid",
                   "intensity": "balanced", "type": task_type, "quirk": ""}]
    return {"agents": agents[:3], "synthesis": "entrega una sola respuesta util para Pedro"}


def _plan_dynamic_team(request: str, features: dict) -> dict:
    def llm_json(prompt: str) -> dict:
        cfg = dispatch.CONFIG["classifier"]
        try:
            data = dispatch._http_post_json(
                cfg["base_url"],
                {"model": cfg["model"], "prompt": prompt, "stream": False,
                 "format": "json", "options": {"temperature": 0}},
            )
            return json.loads(data.get("response") or "{}")
        except Exception:
            return _heuristic_plan(request, features)

    return orchestrator.plan(request, llm_json)


def _run_backend_text(route: str, client: str | None, model: str | None,
                      system: str, user_msg: str, effort: int | None = None) -> str:
    if route == "subscription":
        if not client:
            raise RuntimeError("suscripcion sin cliente")
        return _run_subscription_text(client, system, user_msg, model)
    if route == "api":
        cfg = dispatch.CONFIG["api"]
        mdl = model or cfg["model"]
        payload = {"model": mdl, "stream": False, "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user_msg},
        ]}
        if effort is not None:
            payload["output_config"] = {"effort": capabilities.EFFORT_PARAM[effort]}
        data = dispatch._http_post_json(
            cfg["base_url"], payload, {"Authorization": f"Bearer {cfg['api_key']}"})
        return (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
    cfg = dispatch.CONFIG["local"]
    mdl = model or cfg["model"]
    data = dispatch._http_post_json(
        cfg["base_url"],
        {"model": mdl, "prompt": f"{system}\n\nUsuario: {user_msg}\nCalipso:",
         "stream": False},
    )
    return (data.get("response") or "").strip()


async def _run_agent_text(ws: WebSocket, inbox: asyncio.Queue, agent: dict,
                          agent_system: str, user_msg: str) -> tuple[str, str | None]:
    if agent.get("route") == "subscription":
        return await _run_subscription_text_live(
            ws, inbox, agent.get("client"), agent_system, user_msg,
            agent.get("model"),
            label=f"agente {agent.get('persona') or agent.get('role')}")
    text = await asyncio.to_thread(
        _run_backend_text, agent["route"], agent.get("client"),
        agent.get("model"), agent_system, user_msg,
        capabilities.EFFORT.get(agent.get("intensity", "balanced"), 1))
    return text, None


async def _run_dynamic_team(ws: WebSocket, inbox: asyncio.Queue, chat_msg: str,
                            features: dict, base_system: str,
                            verdict: dict,
                            approval_required: bool = False,
                            departamento: str | None = None) -> tuple[str, dict, str | None]:
    plan_obj = await asyncio.to_thread(_plan_dynamic_team, chat_msg, features)
    team = orchestrator.build_team(
        plan_obj, _backend_availability(), project_root=str(ROOT),
        session=sessions.active())
    agents = team.get("agents", [])
    if not agents:
        raise RuntimeError("no hay agentes disponibles para el equipo dinamico")

    # PLANNING MODE: propone el plan (todo-list) y espera aprobación o ajuste.
    _APPROVE = {"ok", "okay", "dale", "ejecuta", "ejecutar", "si", "sí", "/run",
                "/ok", "aprobar", "aprobado", "adelante", "hazlo", "listo"}
    _CANCEL = {"/skip", "no", "cancela", "cancelar", "/stop", "para"}
    revise = 0
    while True:
        todos = [{"id": i, "role": a.get("role"), "task": a.get("task"),
                  "persona": a.get("persona"), "model": a.get("model"),
                  "skill": a.get("skill"), "skill_name": a.get("skill_name"),
                  "tier": a.get("tier"), "intensity": a.get("intensity"),
                  "status": "pending"} for i, a in enumerate(agents, start=1)]
        await ws.send_json({"type": "plan", "action": "propose", "todos": todos,
                            "synthesis": team.get("synthesis", ""),
                            "approval_required": approval_required})
        if not approval_required:
            break
        decision = await inbox.get()
        if decision is None:
            return "", {"plan": plan_obj, "agents": []}, None
        d = decision.strip().lower()
        if d in _CANCEL:
            await ws.send_json({"type": "plan", "action": "cancelled"})
            return "Plan cancelado.", {"plan": plan_obj, "agents": []}, None
        if d in _APPROVE:
            break
        revise += 1
        if revise > 3:
            break  # demasiadas vueltas: ejecuta el último plan
        await ws.send_json({"type": "plan", "action": "revising", "note": decision})
        plan_obj = await asyncio.to_thread(
            _plan_dynamic_team,
            f"{chat_msg}\n\nAjuste de Pedro al plan: {decision}", features)
        team = orchestrator.build_team(
            plan_obj, _backend_availability(), project_root=str(ROOT),
            session=sessions.active())
        agents = team.get("agents", []) or agents

    await ws.send_json({"type": "plan", "action": "approved",
                        "approval_required": approval_required})
    await ws.send_json({"type": "agent", "action": "team", "agents": agents})
    results: list[dict] = []
    ws_agente_base = "equipo:" + uuid.uuid4().hex[:8]
    queued_msg: str | None = None
    for idx, agent in enumerate(agents, start=1):
        await ws.send_json({"type": "plan", "action": "todo", "id": idx,
                            "status": "doing"})
        await ws.send_json({"type": "agent", "action": "start", "index": idx,
                            "agent": agent})
        agent_system = orchestrator.agent_system(agent, base_system, chat_msg)
        with _pulso_agente(f"{ws_agente_base}:{idx}", departamento=departamento,
                           rol=agent.get("role"),
                           modelo=agent.get("model")) as mango:
            try:
                output, queued = await _run_agent_text(
                    ws, inbox, agent, agent_system, agent["task"])
                queued_msg = queued_msg or queued
            except Exception as e:
                agent["fallback_error"] = str(e)
                try:
                    output = await asyncio.to_thread(
                        _run_backend_text, "local", None, _route_model_name("local"),
                        agent_system, agent["task"], None)
                    agent["fallback_route"] = "local"
                except Exception as e2:
                    output = (
                        f"No pude ejecutar esta subtarea. Ruta original: "
                        f"{agent.get('route')} {agent.get('model') or ''}. "
                        f"Error: {e}. Fallback local: {e2}."
                    )
                    agent["fallback_route"] = "failed"
            # el agente de un equipo no streamea: `_run_backend_text` devuelve
            # el texto entero. Su razonamiento se publica una vez, al final.
            # El incremental existe solo donde existe el stream, que es el
            # turno principal del chat.
            # Y pasa por el filtro sin estado, no por el `Filtro` del stream:
            # el texto llega entero. Sin esto la marca queda visible en el
            # panel de razonamiento, porque `agent_system` hereda el
            # `base_system` -instruccion de emitir la marca incluida- y esta
            # salida no pasa por el `Emisor`.
            mango.razonando(_limpiar_marcas(output))
            mango.tokens(len(agent_system) // 4, len(output) // 4, 0)
        result = {**agent, "output": output}
        results.append(result)
        telemetry.log_event(
            "agent_turn",
            project=str(ROOT),
            prompt_chars=len(agent["task"]),
            response_chars=len(output),
            route_used=agent.get("route"),
            client=agent.get("client"),
            model=agent.get("model"),
            model_id=agent.get("model_id"),
            persona=agent.get("persona"),
            tier=agent.get("tier"),
            task_type=agent.get("type"),
            fallback_error=agent.get("fallback_error"),
        )
        await ws.send_json({"type": "agent", "action": "done", "index": idx,
                            "agent": agent})
        await ws.send_json({"type": "plan", "action": "todo", "id": idx,
                            "status": "done"})

    await ws.send_json({"type": "plan", "action": "synthesizing"})
    await ws.send_json({"type": "agent", "action": "synthesis"})
    synth_prompt = orchestrator.synthesis_prompt(chat_msg, results)
    try:
        if verdict.get("route") == "subscription":
            final, queued = await _run_subscription_text_live(
                ws, inbox, verdict.get("client"), base_system, synth_prompt,
                verdict.get("model"), label="sintesis")
            queued_msg = queued_msg or queued
        else:
            final = await asyncio.to_thread(
                _run_backend_text, verdict.get("route"), verdict.get("client"),
                verdict.get("model"), base_system, synth_prompt, verdict.get("effort"))
    except Exception as e:
        try:
            final = await asyncio.to_thread(
                _run_backend_text, "local", None, _route_model_name("local"),
                base_system, synth_prompt, None)
        except Exception as e2:
            final = (
                "No pude completar la sintesis automatica. Resultado parcial del equipo:\n\n"
                + "\n\n".join(
                    f"[{r['persona']} - {r['role']}]\n{r['output']}"
                    for r in results)
                + f"\n\nErrores de sintesis: {e}; fallback local: {e2}"
            )
    return final, {"plan": plan_obj, "agents": [
        {k: a.get(k) for k in ("persona", "role", "model_id", "route", "client",
                               "model", "tier", "intensity")}
        for a in agents
    ]}, queued_msg


def _harness_context(verdict: dict, used_route: str, model: str, note: str | None) -> str:
    cfg = calipso_config.load_config()
    probes = {"claude": _probe_cached("claude"), "codex": _probe_cached("codex")}
    api_up = _http_up_cached(cfg["api"]["base_url"].replace("/v1/chat/completions", "/health"))
    local_up = False  # sin Ollama
    return "\n".join([
        "=== Estado real de Calipso ===",
        f"Ruta decidida: {verdict.get('route')}",
        f"Ruta usada en esta respuesta: {used_route}",
        f"Cliente de suscripcion elegido: {verdict.get('client') or 'ninguno'}",
        f"Modelo/backend usado: {model}",
        f"Motivo de ruteo: {verdict.get('why')}",
        f"Nota tecnica: {note or 'ninguna'}",
        f"Politica: {cfg['routing'].get('policy')}",
        f"Suscripciones: claude_ready={probes['claude']['ready']}, codex_ready={probes['codex']['ready']}",
        f"Errores suscripcion: claude={probes['claude'].get('error') or 'ninguno'}, codex={probes['codex'].get('error') or 'ninguno'}",
        f"API configurada: modelo={cfg['api']['model']}, litellm_up={api_up}",
        f"Local configurado: modelo={cfg['local']['model']}, ollama_up={local_up}",
        "Regla: no inventes proveedores, suscripciones, modelos ni credenciales. "
        "Si una ruta no esta disponible, dilo como estado operativo de Calipso.",
        "Si Pedro pregunta que modelo o ruta usas, menciona tanto la ruta decidida "
        "como la ruta usada en esta respuesta.",
    ])


# Economía de contexto (context engineering de Anthropic + prompt caching):
# estable al inicio (cacheable -> 90% descuento en sub/api), volátil al final,
# presupuestado, y just-in-time (no precargar archivos del repo).
CONTEXT_CONST_MAX = int(os.environ.get("CALIPSO_CONST_MAX", "3000"))
CONTEXT_CORE_MAX = int(os.environ.get("CALIPSO_CORE_MAX", "3000"))
RECALL_MIN_SCORE = float(os.environ.get("CALIPSO_RECALL_MIN", "0.30"))
RECALL_MAX = int(os.environ.get("CALIPSO_RECALL_MAX", "4"))
REPO_BRIEF_MAX = int(os.environ.get("CALIPSO_REPO_BRIEF_MAX", "4500"))


def _identity_doc() -> str:
    """Solo la constitución (CALIPSO.md). NO el handoff técnico (AGENTS.md,
    CLAUDE.md, etc.): eso es para agentes de código, no para responderle a Pedro;
    volcarlo cada turno era puro gasto de tokens."""
    p = ROOT / "CALIPSO.md"
    if not (p.exists() and p.is_file()):
        return ""
    try:
        return p.read_text(encoding="utf-8").strip()[:CONTEXT_CONST_MAX]
    except UnicodeDecodeError:
        return ""


def _repo_brief(raiz: pathlib.Path) -> str:
    """Mapa compacto del repo para fallbacks sin herramientas de archivo.

    Recibe la raiz como parametro en vez de leer el global ROOT: asi el
    catastro puede pedir el brief de un proyecto que no esta en foco
    (GET /api/catastro/{nombre}) sin mover ROOT ni la memoria (3.4 del spec
    de ojos y manos)."""
    files: list[str] = []
    for p in raiz.rglob("*"):
        try:
            rel = p.relative_to(raiz)
        except ValueError:
            continue
        parts = rel.parts
        if any(part.startswith(".") or part in IGNORE_DIRS for part in parts):
            continue
        if p.is_file():
            files.append(rel.as_posix())
        if len(files) >= 120:
            break
    files.sort()
    blocks = ["Archivos principales:\n" + "\n".join(f"- {f}" for f in files[:80])]
    for name in ("AGENTS.md", "CALIPSO.md", "LIBRARY.md", "SPEC.md", "README.md", "SETUP.md"):
        p = raiz / name
        if not p.exists() or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            continue
        if text:
            blocks.append(f"Extracto de {name}:\n{text[:1400]}")
    return "\n\n".join(blocks)[:REPO_BRIEF_MAX]


def _goal_context() -> str:
    goal = goals.active(str(ROOT))
    if not goal:
        return ""
    criteria = goal.get("criteria") or []
    done = sum(1 for c in criteria if c.get("done"))
    lines = [
        "=== Meta activa ===",
        f"id: {goal.get('id')}",
        f"titulo: {goal.get('title')}",
        f"estado: {goal.get('status')}",
        f"objetivo: {goal.get('objective')}",
        f"criterios: {done}/{len(criteria)} cumplidos",
    ]
    if criteria:
        lines.append("criterios de listo:")
        for item in criteria[:8]:
            mark = "x" if item.get("done") else " "
            lines.append(f"- [{mark}] {item.get('text', '')}")
    subtasks = goal.get("subtasks") or []
    if subtasks:
        lines.append("subtareas:")
        for item in subtasks[:8]:
            lines.append(f"- {item.get('status', 'pending')}: {item.get('text', '')}")
    evidence = goal.get("evidence") or []
    if evidence:
        lines.append("evidencia reciente:")
        for item in evidence[-5:]:
            lines.append(f"- {item.get('kind')}: {item.get('text')}")
    blockers = goal.get("blockers") or []
    if blockers:
        lines.append("bloqueos:")
        for item in blockers[-3:]:
            lines.append(f"- {item.get('text')}")
    return "\n".join(lines)


def _goal_response(goal: dict) -> str:
    criteria = "\n".join(
        f"- [ ] {item.get('text', '')}" for item in (goal.get("criteria") or []))
    subtasks = "\n".join(
        f"- {item.get('text', '')}" for item in (goal.get("subtasks") or []))
    return (
        f"Listo. Active la meta: {goal.get('title')}\n\n"
        f"Criterios de listo:\n{criteria}\n\n"
        f"Primeras subtareas:\n{subtasks}\n\n"
        "La voy a mantener como meta activa y voy a asociar trabajos, evidencia "
        "y bloqueos futuros a ella. No la marco completa sin evidencia."
    )


def _build_context(user_msg: str, runtime: str, features: dict | None = None) -> str:
    """Contexto ordenado para caché (estable -> volátil) y presupuestado.

    Estable (prefijo, se cachea en sub/api): identidad + memoria núcleo.
    Volátil (sufijo): recuerdos relevantes (podados por score) + estado real.
    Just-in-time: los archivos del repo NO se precargan; se piden bajo demanda.

    Arma el brief de economia, que toma el candado del libro (flock
    exclusivo y bloqueante): se llama SIEMPRE desde un hilo, igual que
    `_ficha_y_cuenta` y `_cobrar_turno`.
    """
    # --- prefijo estable (cacheable) ---
    ident = _identity_doc()
    core = mem.load_core()

    # --- sufijo volátil ---
    recalled = [r for r in mem.recall(user_msg, n=8)
                if r["score"] >= RECALL_MIN_SCORE][:RECALL_MAX]
    repo_brief = ""
    if features and features.get("needs_repo"):
        repo_brief = _repo_brief(ROOT)
    goal_block = _goal_context()
    # la economia entra en CADA turno (no solo cuando needs_repo o el tema
    # ya se noto financiero): Calipso no sabe de antemano cuando Pedro va a
    # preguntar por plata, y ese hueco -verla en su propia API en vez de
    # asumir que el sandbox se lo impide- es justo lo que esta seccion
    # cierra. `economia_brief` toma el candado del libro para leer
    # consistente (invariante de `Libro._cargar`); por eso esta funcion
    # entera se despacha con `asyncio.to_thread` desde el websocket, nunca
    # se llama directo sobre el event loop.
    economia = prompt_compiler.economia_brief(_ECO_BASE)
    # el catastro (calipso/catastro.py) entra en CADA turno, igual que la
    # economia y por la misma razon (3.4 del spec de ojos y manos): Calipso
    # tenia los datos de sus otros proyectos al lado, en el disco, y
    # contestaba "no se" por no tenerlos en el prompt, nunca por no poder
    # leerlos. `cargar()` solo lee catastro.json (o escanea una vez si es
    # la primera vez de la vida del catastro); no toma ningun candado.
    proyectos = prompt_compiler.proyectos_brief(ROOT)
    return prompt_compiler.compile_context(
        SYSTEM, identity=ident, core=core, recalled=recalled,
        repo_brief=repo_brief, goal_block=goal_block, runtime=runtime,
        economia=economia, proyectos=proyectos, features=features,
        core_limit=CONTEXT_CORE_MAX)


def _HISTORY_TURNS_CONST():
    return 12


_HISTORY_TURNS = 12  # max mensajes del historial (6 intercambios)


def _history_messages(chat_id: str | None, limit: int = _HISTORY_TURNS) -> list[dict]:
    """Ultimos N mensajes del chat como lista [{role, content}] para messages[].

    Excluye el ultimo mensaje (el actual, ya incluido como user_msg).
    """
    if not chat_id:
        return []
    chat = chats.get(chat_id)
    if not chat:
        return []
    msgs = chat.get("messages", [])
    prior = msgs[:-1] if msgs else []
    tail = prior[-limit:]
    result = []
    for m in tail:
        role = m.get("role", "")
        text = (m.get("text") or "").strip()
        if role in ("user", "assistant") and text:
            result.append({"role": role, "content": text})
    return result


def _chunks_for(route: str, system: str, user_msg: str, usage: dict,
                model: str | None = None, effort: int | None = None,
                chat_id: str | None = None):
    """Devuelve (generador, modelo) segun la ruta con historial de conversacion."""
    history = _history_messages(chat_id)

    if route == "api":
        cfg = dispatch.CONFIG["api"]
        mdl = model or cfg["model"]
        messages = [{"role": "system", "content": system}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_msg})
        payload = {"model": mdl, "stream": True,
                   "stream_options": {"include_usage": True}, "messages": messages}
        if effort is not None:
            payload["output_config"] = {"effort": capabilities.EFFORT_PARAM[effort]}
        headers = {"Authorization": f"Bearer {cfg['api_key']}"}
        return dispatch._sse_text_chunks(cfg["base_url"], payload, headers, usage), mdl

    # local no disponible (sin Ollama) → suscripción claude
    exe = shutil.which("claude")

    def _local_via_sub():
        if not exe:
            yield "[Calipso] ruta local no disponible y claude no encontrado."
            return
        env = {**os.environ}
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
        result = subprocess.run([exe, "-p", user_msg], capture_output=True,
                                text=True, timeout=300, env=env)
        yield result.stdout or result.stderr or "[sin respuesta]"

    return _local_via_sub(), "claude"

def _subscription_invocation(client: str, system: str, user_msg: str,
                             model: str | None = None,
                             chat_id: str | None = None) -> tuple[list[str], dict, str | None, str | None]:
    template = dispatch.CONFIG["subscription"].get(client)
    if not template:
        raise RuntimeError(f"cliente de suscripcion desconocido: {client}")
    exe = _subscription_command(client)
    if not exe:
        raise RuntimeError(f"{client} no esta instalado")
    system_prompt = (
        f"{system}\n\n"
        "Responde como Calipso. No digas que eres el backend usado."
    )
    # Historial de conversación para que el CLI tenga contexto multi-turno
    history = _history_messages(chat_id)
    history_block = ""
    if history:
        lines = []
        for m in history:
            speaker = "Pedro" if m["role"] == "user" else "Calipso"
            lines.append(f"{speaker}: {m['content']}")
        history_block = "\n\n=== Conversación anterior ===\n" + "\n".join(lines) + "\n\n"
    prompt = f"{history_block}Pedro: {user_msg}\nCalipso:"
    temp_names: list[str] = []
    if len(prompt) > 7000:
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", suffix=".prompt.md", delete=False,
                dir=str(ROOT)) as f:
            f.write(prompt)
            prompt_name = f.name
            temp_names.append(prompt_name)
        prompt = (
            "Lee el prompt completo desde este archivo local y responde la tarea "
            f"como Calipso, sin copiar el archivo literalmente:\n{prompt_name}"
        )
    cmd = [exe if i == 0 else arg.replace("{prompt}", prompt)
           for i, arg in enumerate(template)]
    temp_name = None
    output_name = None
    if client == "claude":
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", suffix=".md", delete=False) as f:
            f.write(system_prompt)
            temp_name = f.name
            temp_names.append(temp_name)
        cmd = [exe]
        if model in ("haiku", "sonnet", "opus"):
            cmd += ["--model", model]  # elige el tier de Claude
        cmd += ["--append-system-prompt-file", temp_name, "-p", prompt]
    elif client == "codex":
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", suffix=".txt", delete=False) as f:
            output_name = f.name
        cmd = [
            (exe if i == 0 else
             arg.replace("{prompt}", prompt).replace("{output}", output_name))
            for i, arg in enumerate(template)
        ]
        if model and model.startswith("gpt"):  # elige el modelo de Codex
            cmd[1:1] = ["-m", model]  # tras 'exec'... insertamos antes de exec
    env = os.environ.copy()
    if client == "claude":
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return cmd, env, temp_names, output_name


def _cleanup_subscription_files(temp_name: str | list[str] | None,
                                output_name: str | None) -> None:
    temp_list = temp_name if isinstance(temp_name, list) else ([temp_name] if temp_name else [])
    for name in temp_list:
        try:
            pathlib.Path(name).unlink(missing_ok=True)
        except Exception:
            pass
    if output_name:
        try:
            pathlib.Path(output_name).unlink(missing_ok=True)
        except Exception:
            pass


def _run_subscription_text(client: str, system: str, user_msg: str,
                           model: str | None = None,
                           chat_id: str | None = None) -> str:
    cmd, env, temp_name, output_name = _subscription_invocation(
        client, system, user_msg, model, chat_id=chat_id)
    try:
        result = subprocess.run(
            cmd, cwd=str(ROOT), text=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=None, env=env)
        if result.returncode != 0:
            msg = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(msg or f"{client} fallo con exit {result.returncode}")
        if output_name:
            out = pathlib.Path(output_name).read_text(encoding="utf-8").strip()
            return out or result.stdout.strip()
        return result.stdout.strip()
    finally:
        _cleanup_subscription_files(temp_name, output_name)


async def _run_subscription_text_live(
        ws: WebSocket, inbox: asyncio.Queue, client: str, system: str,
        user_msg: str, model: str | None = None,
        label: str = "proceso",
        chat_id: str | None = None) -> tuple[str, str | None]:
    cmd, env, temp_name, output_name = _subscription_invocation(
        client, system, user_msg, model, chat_id=chat_id)
    started = time.perf_counter()
    last_notice = started
    pending_msg: str | None = None
    stdout_name = None
    stderr_name = None
    stdout_file = tempfile.NamedTemporaryFile(
        "w+", encoding="utf-8", errors="replace", suffix=".stdout", delete=False)
    stderr_file = tempfile.NamedTemporaryFile(
        "w+", encoding="utf-8", errors="replace", suffix=".stderr", delete=False)
    stdout_name = stdout_file.name
    stderr_name = stderr_file.name
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT), text=True, stdout=stdout_file,
        stderr=stderr_file, encoding="utf-8", errors="replace", env=env)
    active_goal = goals.active(str(ROOT))
    job = jobs.start(
        "subscription_process", label, project_root=str(ROOT),
        client=client, model=model,
        goal_id=active_goal.get("id") if active_goal else None,
        prompt_tokens=max(1, (len(system) + len(user_msg)) // 4))
    if active_goal:
        goals.add_evidence(
            str(ROOT), active_goal["id"], "job",
            f"Proceso iniciado: {label}", job_id=job["id"], status="running")

    def _read_partial() -> tuple[str, str]:
        for f in (stdout_file, stderr_file):
            try:
                f.flush()
            except Exception:
                pass
        stdout = pathlib.Path(stdout_name).read_text(
            encoding="utf-8", errors="replace") if stdout_name else ""
        stderr = pathlib.Path(stderr_name).read_text(
            encoding="utf-8", errors="replace") if stderr_name else ""
        out = ""
        if output_name and pathlib.Path(output_name).exists():
            out = pathlib.Path(output_name).read_text(
                encoding="utf-8", errors="replace").strip()
        return out or stdout.strip(), stderr.strip()

    try:
        await ws.send_json({"type": "process", "action": "start",
                            "job_id": job["id"],
                            "label": label, "client": client, "model": model,
                            "prompt_tokens": max(1, (len(system) + len(user_msg)) // 4)})
        while proc.poll() is None:
            now = time.perf_counter()
            if now - last_notice >= 2:
                partial, _ = _read_partial()
                await ws.send_json({
                    "type": "process", "action": "running",
                    "job_id": job["id"],
                    "label": label, "client": client, "model": model,
                    "elapsed": round(now - started),
                    "tokens": max(1, ((len(system) + len(user_msg)) + len(partial)) // 4),
                    "partial": _limpiar_marcas(partial)[-3000:] if partial else "",
                    "hint": "sigue corriendo; envia /stop para cancelar o escribe y lo atiendo al terminar"})
                jobs.event(
                    str(ROOT), job["id"], "running",
                    elapsed=round(now - started),
                    tokens=max(1, ((len(system) + len(user_msg)) + len(partial)) // 4))
                last_notice = now
            if not inbox.empty():
                msg = await inbox.get()
                if msg is None:
                    proc.terminate()
                    raise RuntimeError("conexion cerrada mientras el proceso seguia")
                clean = msg.strip()
                if clean == "/stop":
                    proc.terminate()
                    try:
                        await asyncio.to_thread(proc.wait, 8)
                    except Exception:
                        proc.kill()
                    partial, stderr = _read_partial()
                    await ws.send_json({"type": "process", "action": "stopped",
                                        "job_id": job["id"], "label": label})
                    jobs.update(str(ROOT), job["id"], status="cancelled")
                    jobs.event(str(ROOT), job["id"], "stopped")
                    if active_goal:
                        goals.add_evidence(
                            str(ROOT), active_goal["id"], "job",
                            f"Proceso cancelado: {label}", job_id=job["id"], status="cancelled")
                    if partial:
                        jobs.write_artifact(str(ROOT), job["id"], "partial-output.txt", partial)
                    if stderr:
                        jobs.write_artifact(str(ROOT), job["id"], "stderr.txt", stderr)
                    if partial:
                        return partial + "\n\n...(proceso interrumpido)", None
                    if stderr:
                        return stderr + "\n\n...(proceso interrumpido)", None
                    return "...(proceso interrumpido sin salida parcial)", None
                if clean:
                    pending_msg = clean
                    await ws.send_json({
                        "type": "process", "action": "queued",
                        "label": label,
                        "hint": "lo recibi; este CLI no acepta steering en vivo, lo proceso al terminar"})
            await asyncio.sleep(1.5)
        await asyncio.to_thread(proc.wait)
        partial, stderr = _read_partial()
        if proc.returncode != 0:
            msg = (stderr or partial or "").strip()
            jobs.update(str(ROOT), job["id"], status="failed", error=msg)
            jobs.event(str(ROOT), job["id"], "failed", error=msg[:1000])
            if active_goal:
                goals.add_evidence(
                    str(ROOT), active_goal["id"], "job",
                    f"Proceso fallo: {label}", job_id=job["id"], status="failed")
            if partial:
                jobs.write_artifact(str(ROOT), job["id"], "partial-output.txt", partial)
            if stderr:
                jobs.write_artifact(str(ROOT), job["id"], "stderr.txt", stderr)
            raise RuntimeError(msg or f"{client} fallo con exit {proc.returncode}")
        text = partial
        elapsed = round(time.perf_counter() - started)
        await ws.send_json({"type": "process", "action": "done",
                            "job_id": job["id"],
                            "label": label, "elapsed": elapsed,
                            "tokens": max(1, ((len(system) + len(user_msg)) + len(text)) // 4)})
        jobs.update(
            str(ROOT), job["id"], status="done", elapsed=elapsed,
            tokens=max(1, ((len(system) + len(user_msg)) + len(text)) // 4))
        jobs.event(str(ROOT), job["id"], "done", elapsed=elapsed)
        if text:
            jobs.write_artifact(str(ROOT), job["id"], "output.txt", text)
        if stderr:
            jobs.write_artifact(str(ROOT), job["id"], "stderr.txt", stderr)
        if active_goal:
            goals.add_evidence(
                str(ROOT), active_goal["id"], "job",
                f"Proceso terminado: {label}", job_id=job["id"], status="done",
                artifact="output.txt" if text else None, elapsed=elapsed)
        return text, pending_msg
    finally:
        for f in (stdout_file, stderr_file):
            try:
                f.close()
            except Exception:
                pass
        for name in (stdout_name, stderr_name):
            try:
                if name:
                    pathlib.Path(name).unlink(missing_ok=True)
            except Exception:
                pass
        _cleanup_subscription_files(temp_name, output_name)


def _next_or_stop(gen, sentinel):
    try:
        return next(gen)
    except StopIteration:
        return sentinel


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    if not _valid(ws.cookies.get(COOKIE)):
        await ws.close(code=1008)  # polÃƒÂ­tica violada: sin token vÃƒÂ¡lido
        return
    await ws.accept()
    active_goal = goals.active(str(ROOT))
    if active_goal:
        await ws.send_json({"type": "goal", "action": "active", "goal": active_goal})
    sentinel = object()
    inbox: asyncio.Queue = asyncio.Queue()

    async def _receiver():
        try:
            while True:
                await inbox.put(await ws.receive_text())
        except Exception:
            await inbox.put(None)  # desconexión

    rtask = asyncio.create_task(_receiver())
    pending = None
    _last_features: dict = {}   # features del turno anterior para contexto
    _last_verdict: dict = {}    # route/model del turno anterior
    # el edificio que Pedro tiene tocado. Es estado de la CONEXION, no del
    # paquete: la vuelta que consume `pending` (steering) saltea el parseo, y
    # ahi Pedro sigue con el mismo edificio tocado en pantalla. Cada paquete
    # nuevo la reasigna, asi que el cliente la apaga mandando el campo vacio.
    departamento = None
    try:
        while True:
            chat_id = chats.active_id()
            attachment_ids: list[str] = []
            if pending is not None:
                user_msg, pending = pending, None
            else:
                raw = await inbox.get()
                if raw is None:
                    break
                try:
                    packet = json.loads(raw)
                    if isinstance(packet, dict):
                        user_msg = str(packet.get("text") or "")
                        chat_id = packet.get("chat_id") or chat_id
                        departamento = packet.get("departamento") or None
                        attachment_ids = [
                            str(x) for x in (packet.get("attachment_ids") or [])
                            if isinstance(x, str)
                        ][:8]
                    else:
                        user_msg = raw
                except Exception:
                    user_msg = raw
                    attachment_ids = []
            user_msg = user_msg.strip()
            if not user_msg or user_msg == "/stop":
                continue  # /stop en reposo no interrumpe nada
            if not chat_id or not chats.get(chat_id):
                chat = chats.create(str(ROOT), user_msg[:70])
                chat_id = chat["id"]
                await ws.send_json({"type": "chat", "action": "active",
                                    "chat": _chat_view(chat)})
            active_chat = chats.get(chat_id)
            if active_chat and active_chat.get("project_path") != str(ROOT):
                _switch_project(active_chat["project_path"])
                await ws.send_json({"type": "project", "action": "changed",
                                    "name": ROOT.name, "path": str(ROOT)})
            chats.append(chat_id, "user", user_msg, {
                "attachment_ids": attachment_ids,
            } if attachment_ids else None)
            turn_started = time.perf_counter()
            fallbacks: list[dict] = []
            # avisa de inmediato que está pensando (los probes pueden tardar)
            await ws.send_json({"type": "thinking"})

            goal_objective = goals.detect(user_msg)
            if goal_objective:
                goal = goals.create(str(ROOT), goal_objective)
                reply = _goal_response(goal)
                await ws.send_json({"type": "goal", "action": "active", "goal": goal})
                await ws.send_json({"type": "chunk", "text": reply})
                chats.append(chat_id, "assistant", reply, {
                    "route": "goal",
                    "goal_id": goal["id"],
                })
                current_chat = chats.get(chat_id)
                if current_chat:
                    await ws.send_json({"type": "chat", "action": "updated",
                                        "chat": _chat_view(current_chat)})
                await ws.send_json({"type": "done"})
                try:
                    await asyncio.to_thread(
                        mem.remember,
                        f"Pedro definio una meta: {goal_objective}\nCalipso creo Goal Mode: {goal['id']}",
                        route="goal", kind="goal")
                except Exception:
                    pass
                continue

            # 1) routing a nivel de MODELO (afinidad x costo x tier x intensidad)
            #    en un hilo: los probes de suscripción son síncronos y NO deben
            #    bloquear el event loop (si no, no se puede interrumpir/steerear).
            verdict, features, ranked, directives = await asyncio.to_thread(
                _decide, user_msg, _last_features, _last_verdict)
            if directives.get("help"):
                await ws.send_json({"type": "chunk", "text": HELP_TEXT})
                await ws.send_json({"type": "done"})
                continue
            chat_msg = directives["clean"]
            # quien paga y que sabe Calipso del departamento son dos
            # preguntas distintas con dos fuentes distintas: ver
            # `_ficha_y_cuenta`. Va en un hilo porque derivar la ficha toma el
            # candado del libro.
            bloque_dep, cuenta = await asyncio.to_thread(_ficha_y_cuenta,
                                                         departamento)
            route = verdict["route"]
            model = verdict.get("model")
            note = "; ".join(f"{r['persona']}={r['score']}" for r in ranked[:3]) or None
            await ws.send_json({"type": "meta", "route": verdict["route"],
                                "used": route, "model": model,
                                "model_id": verdict.get("model_id"),
                                "persona": verdict.get("persona"),
                                "tier": verdict.get("tier"),
                                "effort": verdict.get("effort_name"),
                                "client": verdict.get("client"),
                                "why": verdict["why"], "note": note})

            agente_id = "chat:" + uuid.uuid4().hex[:8]
            emisor = Emisor(ws, agente_id=agente_id)
            if EL_PULSO is not None:
                # abierto y cerrado a mano: envolver el cuerpo del turno
                # re-indentaria doscientas cincuenta lineas. Si el turno
                # revienta sin cerrar, la regla de inactividad libera el
                # escritorio a los diez minutos
                EL_PULSO.publicar(agente_id, "inicio",
                                  departamento=departamento, rol="calipso",
                                  modelo=model)

            # 1.5b) dev loop: si el mensaje pide editar un archivo conocido,
            #         lanzar borrador en background y notificar como evento "proposal"
            _edit_target = _extract_edit_target(chat_msg, features)
            if _edit_target:
                asyncio.ensure_future(_run_chat_draft(
                    ws, chat_msg, _edit_target, f"{agente_id}:borrador",
                    departamento))

            # 1.5) navegación web si la tarea lo pide (grounding + preview)
            web_material = None
            if features.get("needs_web") or directives.get("force_web"):
                await ws.send_json({"type": "web", "action": "search",
                                    "query": chat_msg[:140]})
                web_material = await asyncio.to_thread(
                    calipso_web.research, chat_msg, 4, 2)
                await ws.send_json({
                    "type": "web", "action": "results",
                    "results": web_material["results"],
                    "pages": [{"url": p["url"], "title": p["title"]}
                              for p in web_material["pages"]]})

            # 2) contexto (core + recuerdos) y 3) streaming
            runtime = _harness_context(verdict, route, model, note)
            # `_build_context` arma el brief de economia bajo el candado del
            # libro (flock bloqueante); en un hilo, igual que `_ficha_y_cuenta`.
            system = await asyncio.to_thread(_build_context, chat_msg, runtime, features)
            # vision: describir imágenes antes de inyectar contexto de adjuntos
            if attachments.has_images(str(ROOT), attachment_ids):
                vision_text = await asyncio.to_thread(
                    attachments.vision_describe, str(ROOT), attachment_ids, chat_msg)
                if vision_text:
                    system += "\n\n=== Vision de imagen adjunta ===\n" + vision_text
                else:
                    vm = attachments.ollama_vision_model()
                    if not vm and not os.environ.get("ANTHROPIC_API_KEY"):
                        system += (
                            "\n\n[Imagen adjunta registrada. Para análisis visual automático: "
                            "instala 'ollama pull moondream' o configura ANTHROPIC_API_KEY.]"
                        )
            attachment_context = attachments.context_block(str(ROOT), attachment_ids)
            if attachment_context:
                system += "\n\n" + attachment_context
            if bloque_dep:
                system += "\n\n" + bloque_dep
            if web_material and (web_material["results"] or web_material["pages"]):
                system += "\n\n" + calipso_web.context_block(web_material)
            usage: dict = {}
            used_route = route
            full = ""
            agent_team: dict | None = None
            try:
                if _should_orchestrate(features, directives, chat_msg):
                    runtime = _harness_context(
                        verdict, "orchestrator", model,
                        f"equipo dinamico sobre ruta base {route}")
                    system = await asyncio.to_thread(_build_context, chat_msg, runtime, features)
                    if attachment_context:
                        system += "\n\n" + attachment_context
                    if bloque_dep:
                        system += "\n\n" + bloque_dep
                    if web_material and (web_material["results"] or web_material["pages"]):
                        system += "\n\n" + calipso_web.context_block(web_material)
                    full, agent_team, queued = await _run_dynamic_team(
                        ws, inbox, chat_msg, features, system, verdict,
                        approval_required=bool(directives.get("force_team")),
                        departamento=departamento)
                    if queued:
                        pending = queued
                    used_route = "orchestrator"
                    usage["completion_tokens"] = len(full.split())
                    full = await emisor.chunk(full)
                elif route == "subscription":
                    full, queued = await _run_subscription_text_live(
                        ws, inbox, verdict["client"], system, chat_msg, model,
                        label=f"{verdict.get('persona') or verdict['client']} via {verdict['client']}",
                        chat_id=chat_id)
                    if queued:
                        pending = queued
                    usage["completion_tokens"] = len(full.split())
                    full = await emisor.chunk(full)
                else:
                    gen, model = _chunks_for(route, system, chat_msg, usage, model,
                                             verdict.get("effort"), chat_id=chat_id)
                    while True:
                        if not inbox.empty():  # steering: barge-in mientras responde
                            steer = inbox.get_nowait()
                            try:
                                gen.close()
                            except Exception:
                                pass
                            await ws.send_json({"type": "steered"})
                            full += " …(interrumpido)"
                            if steer and steer.strip() and steer.strip() != "/stop":
                                pending = steer
                            break
                        chunk = await asyncio.to_thread(_next_or_stop, gen, sentinel)
                        if chunk is sentinel:
                            break
                        full += await emisor.chunk(chunk)
            except Exception as e:  # p.ej. LiteLLM apagado en ruta api
                if route != "local":
                    if route == "subscription":
                        alternate = _best_subscription_client(
                            "codex" if verdict.get("client") == "claude" else "claude")
                        if alternate and alternate != verdict.get("client"):
                            await ws.send_json({
                                "type": "meta", "route": verdict["route"],
                                "used": "subscription", "model": alternate,
                                "client": alternate,
                                "why": f"{verdict.get('client')} fallo ({e}); probando {alternate}",
                                "note": "fallback entre suscripciones"})
                            fallbacks.append({
                                "from": verdict.get("client"),
                                "to": alternate,
                                "error": str(e),
                            })
                            try:
                                verdict["client"] = alternate
                                model = _route_model_name("subscription", alternate)
                                runtime = _harness_context(
                                    verdict, "subscription", model,
                                    f"fallback de suscripcion a {alternate}")
                                system = await asyncio.to_thread(_build_context, chat_msg, runtime, features)
                                if attachment_context:
                                    system += "\n\n" + attachment_context
                                if bloque_dep:
                                    system += "\n\n" + bloque_dep
                                full, queued = await _run_subscription_text_live(
                                    ws, inbox, alternate, system, chat_msg, None,
                                    label=f"fallback via {alternate}",
                                    chat_id=chat_id)
                                if queued:
                                    pending = queued
                                usage["completion_tokens"] = len(full.split())
                                full = await emisor.chunk(full)
                                used_route = "subscription"
                                route = "subscription"
                                raise StopIteration
                            except StopIteration:
                                pass
                            except Exception as e2:
                                e = e2
                            else:
                                continue
                        if full:
                            pass
                    if full and used_route == "subscription":
                        pass
                    else:
                        await ws.send_json({"type": "meta", "route": verdict["route"],
                                            "used": "local",
                                            "model": _route_model_name("local"),
                                            "client": verdict.get("client"),
                                            "why": f"ruta {route} falló ({e}); fallback local",
                                            "note": "fallback a local"})
                        fallbacks.append({
                            "from": route,
                            "to": "local",
                            "error": str(e),
                        })
                        used_route, usage = "local", {}
                        model = _route_model_name("local")
                        runtime = _harness_context(verdict, "local", model, f"ruta {route} fallo; fallback local")
                        system = await asyncio.to_thread(_build_context, chat_msg, runtime, features)
                        if attachment_context:
                            system += "\n\n" + attachment_context
                        if bloque_dep:
                            system += "\n\n" + bloque_dep
                        gen, model = _chunks_for("local", system, chat_msg, usage, chat_id=chat_id)
                        while True:
                            if not inbox.empty():  # steering en el fallback local
                                steer = inbox.get_nowait()
                                try:
                                    gen.close()
                                except Exception:
                                    pass
                                await ws.send_json({"type": "steered"})
                                full += " …(interrumpido)"
                                if steer and steer.strip() and steer.strip() != "/stop":
                                    pending = steer
                                break
                            chunk = await asyncio.to_thread(_next_or_stop, gen, sentinel)
                            if chunk is sentinel:
                                break
                            full += await emisor.chunk(chunk)
                else:
                    await ws.send_json({"type": "error", "text": str(e)})
            except StopIteration:
                pass

            # lo que el filtro venia reteniendo por si era una marca: si la
            # respuesta termino en un corchete suelto, Pedro tiene que verlo
            full += await emisor.cerrar()

            # 4) registrar costo/uso, cobrarle al departamento en foco y avisar
            entry = costs.log_usage(
                used_route, model, usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0), client=verdict.get("client"))
            # `used_route` vale "orchestrator" cuando corrio el equipo dinamico,
            # y esa no es una ruta que se pueda cobrar: los agentes gastaron
            # por la ruta base del verdict. Sin esta normalizacion, un turno
            # de equipo con atlas en foco no le cobra un peso a atlas.
            ruta_cobrable = (verdict["route"] if used_route == "orchestrator"
                             else used_route)
            cobrado = await asyncio.to_thread(
                _cobrar_turno, cuenta, ruta_cobrable, verdict.get("client"),
                model, usage)
            await ws.send_json({"type": "cost", "model": model, "route": used_route,
                                "tokens": entry["prompt_tokens"] + entry["completion_tokens"],
                                "cost_usd": entry["cost_usd"],
                                "cuenta": cuenta, "mm": cobrado})
            if EL_PULSO is not None:
                EL_PULSO.publicar(agente_id, "tokens",
                                  tokens_in=entry["prompt_tokens"],
                                  tokens_out=entry["completion_tokens"],
                                  costo_mm=cobrado)
                EL_PULSO.publicar(
                    agente_id, "fin",
                    runtime_ms=round((time.perf_counter() - turn_started) * 1000),
                    resultado="ok")
            telemetry.log_event(
                "chat_turn",
                project=str(ROOT),
                prompt_chars=len(user_msg),
                response_chars=len(full),
                task_type=features.get("type"),
                complexity=features.get("complexity"),
                route_decided=verdict.get("route"),
                route_used=used_route,
                client=verdict.get("client"),
                model=model,
                model_id=verdict.get("model_id"),
                persona=verdict.get("persona"),
                tier=verdict.get("tier"),
                effort=verdict.get("effort_name"),
                why=verdict.get("why"),
                fallbacks=fallbacks,
                agent_team=agent_team,
                latency_ms=round((time.perf_counter() - turn_started) * 1000),
                cost_usd=entry["cost_usd"],
            )

            # 5) recordar el intercambio (episÃƒÂ³dica)
            if full.strip():
                mem.remember(f"Pedro preguntÃƒÂ³: {user_msg}\nCalipso respondiÃƒÂ³: {full.strip()}",
                             route=verdict["route"], kind="chat")
            if full.strip():
                chats.append(chat_id, "assistant", full.strip(), {
                    "route": used_route,
                    "model": model,
                    "client": verdict.get("client"),
                    "agent_team": agent_team,
                })
                current_chat = chats.get(chat_id)
                if current_chat:
                    await ws.send_json({"type": "chat", "action": "updated",
                                        "chat": _chat_view(current_chat)})
            # 5b) auto-cierre de meta: si la activa quedó completa, notificar
            _active = goals.active(str(ROOT))
            if _active and _active.get("status") == "complete":
                await ws.send_json({
                    "type": "goal", "action": "auto_closed",
                    "goal_id": _active.get("id"),
                    "title": _active.get("title"),
                })

            _last_features = features
            _last_verdict = verdict
            await ws.send_json({"type": "done"})
    except WebSocketDisconnect:
        pass
    finally:
        rtask.cancel()


@app.post("/api/reflect")
def api_reflect() -> dict:
    """Dispara la consolidaciÃƒÂ³n: promueve hechos duraderos al core curado."""
    promoted = mem.reflect()
    return {"promoted": promoted}


@app.post("/api/discover")
def api_discover() -> dict:
    """Descubre modelos vivos (Ollama/LiteLLM) y los registra."""
    return discovery.discover(register=True)


# --------------------------------------------------------------------------
# RUTINAS / TIMERS  (reflect/learn/backup periodicos mientras el server vive)
# --------------------------------------------------------------------------

def _routine_handlers() -> dict:
    """Mapea kind -> accion. Las tres viejas son locales y no abren red; la
    de departamento SI gasta: despierta al jefe, que decide en el escalon
    local y puede contratar. Sus frenos viven en calipso/plantel/interruptor.
    """
    def _reflect(_r):
        mem.reflect()

    def _learn(_r):
        learning.learn()
        learning.learn(project_root=str(ROOT), project=str(ROOT))

    def _backup(_r):
        calipso_backup.create_backup()

    def _catastro(_r):
        # forzar_escaneo=True: la rutina existe justamente para mantener
        # el catastro fresco, no para reusar el cache que otro turno ya
        # calento (eso ya lo hace `catastro.cargar()` sin forzar).
        catastro.cargar(forzar_escaneo=True)

    def _departamento(r):
        cuenta = r.get("cuenta")
        if not cuenta:
            return
        if _plantel_jefe is None:
            return
        eco = _economia()
        if eco is None:
            return
        _, semana = _eco_ahora()
        # lector serializado, igual que los otros seis call sites de
        # economia en server.py: el libro se repara truncando una ultima
        # linea que no parsea, asi que leerlo mientras dispatch (u otro
        # departamento) esta a mitad de un append se puede comer un
        # asiento recien escrito, para siempre. El candado se SUELTA antes
        # de armar el Contexto: `tic` piensa afuera de el.
        with _eco_candado(eco["pagador"].ruta_libro):
            m = eco["pagador"].mercado_fresco()
        ts, _ = _eco_ahora()
        ctx = _plantel_jefe.Contexto(
            base=_ECO_BASE, kernel=m.k, registro=m.registro,
            bus=eco["bus"], cola=eco["cola"], suscripciones=m.suscripciones,
            memoria=mem.departamento(cuenta.split(":", 1)[1]),
            pensar=_pensar_local,
            contratar=_contratar_para(cuenta, eco["pagador"], ts, semana),
            publicar=_publicar_jefe(cuenta))
        # SIN candado envolvente durante el tic: incluye una llamada a un
        # modelo, y tener el flock tomado durante segundos serializa el chat
        # y a dispatch contra el. La lectura de arriba ya paso por su
        # candado; la escritura del bus (si el jefe propone) toma el suyo
        # en `_contratar_para`.
        _plantel_jefe.tic(ctx, cuenta, semana)

    return {"reflect": _reflect, "learn": _learn, "backup": _backup,
            "catastro": _catastro, "departamento": _departamento}


@app.get("/api/routines")
def api_routines() -> dict:
    return {"routines": calipso_routines.load(),
            "backups": calipso_backup.list_backups()}


@app.post("/api/routines")
async def api_routines_add(request: Request) -> dict:
    data = await request.json()
    if data.get("kind") == "departamento" and not data.get("cuenta"):
        # sin cuenta, la rutina nace y el handler se va en silencio en su
        # primera linea: Pedro la ve verde en el panel y no pasa nada nunca
        raise HTTPException(status_code=400,
                            detail="una rutina de departamento necesita cuenta")
    try:
        return calipso_routines.add(
            data.get("kind", ""), data.get("label", ""),
            int(data.get("interval_minutes", 1440)),
            bool(data.get("enabled", False)),
            cuenta=data.get("cuenta"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except calipso_routines.ErrorRutinas as e:
        # routines.json esta pero no se pudo leer (una escritura concurrente
        # a mitad de camino, corrupcion real): add() se niega a pisarlo con
        # el seed en vez de perder las rutinas de Pedro. 503, no 500: es
        # transitorio, reintentar en un momento debiera andar.
        raise HTTPException(status_code=503, detail=str(e))


@app.put("/api/routines/{routine_id}")
async def api_routines_update(routine_id: str, request: Request) -> dict:
    patch = await request.json()
    updated = calipso_routines.update(routine_id, patch)
    if updated is None:
        raise HTTPException(status_code=404, detail="rutina no encontrada")
    return updated


@app.delete("/api/routines/{routine_id}")
def api_routines_delete(routine_id: str) -> dict:
    if not calipso_routines.remove(routine_id):
        raise HTTPException(status_code=404, detail="rutina no encontrada")
    return {"ok": True}


@app.post("/api/routines/{routine_id}/run")
def api_routines_run(routine_id: str) -> dict:
    """Corre una rutina ahora, ignorando el vencimiento (boton manual)."""
    routine = calipso_routines.get(routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="rutina no encontrada")
    handler = _routine_handlers().get(routine["kind"])
    if handler is None:
        raise HTTPException(status_code=400, detail="kind sin handler")
    now = datetime.datetime.now()
    try:
        handler(routine)
        status = "ok"
    except Exception as e:
        status = f"error: {e}"
    calipso_routines.mark_run(routine_id, now, status)
    return {"ok": status == "ok", "status": status,
            "routine": calipso_routines.get(routine_id)}


@app.post("/api/backup")
def api_backup() -> dict:
    return calipso_backup.create_backup()


# --------------------------------------------------------------------------
# DEPENDENCIAS  (Calipso instala lo que necesita; no se queda bloqueada)
# --------------------------------------------------------------------------

@app.get("/api/deps")
def api_deps() -> dict:
    """Estado de las capacidades que dependen de paquetes (browser, etc.)."""
    return {"tools": deps.status()}


def _launch_item(key: str, label: str, ok: bool, detail: str,
                 action: str | None = None) -> dict:
    return {
        "key": key,
        "label": label,
        "ok": bool(ok),
        "detail": detail,
        "action": action or "",
    }


@app.get("/api/launch/checklist")
def api_launch_checklist() -> dict:
    """Checklist humano para saber si Calipso esta listo para uso diario."""
    dep_status = deps.status()
    health = _connector_health(use_cache=True)
    subs = health.get("subscription", {})
    any_subscription = any(v.get("ready") for v in subs.values())
    any_backend = bool(
        any_subscription or health.get("local", {}).get("ready") or health.get("api", {}).get("ready"))
    manifest_ok = (WEB / "manifest.json").exists() and (WEB / "sw.js").exists()
    launchers = {
        "windows_bat": (ROOT / "Calipso.bat").exists(),
        "windows_ps1": (ROOT / "Calipso.ps1").exists(),
        "python": (ROOT / "launch_calipso.py").exists(),
    }
    items = [
        _launch_item(
            "server", "Servidor local", True,
            "Calipso respondio a esta solicitud."),
        _launch_item(
            "project", "Proyecto activo", ROOT.exists(),
            str(ROOT) if ROOT.exists() else "La ruta del proyecto no existe."),
        _launch_item(
            "security_token", "Token de recuperacion",
            bool(os.environ.get("CALIPSO_TOKEN") or _TOKEN_FILE.exists()),
            "Token disponible por entorno o archivo." if (
                os.environ.get("CALIPSO_TOKEN") or _TOKEN_FILE.exists())
            else "Falta token de recuperacion."),
        _launch_item(
            "totp", "Login TOTP", _TOTP_SECRET_FILE.exists(),
            "Autenticador configurado." if _TOTP_SECRET_FILE.exists()
            else "Abre /setup para escanear el QR.",
            "/setup"),
        _launch_item(
            "pwa", "PWA celular", manifest_ok,
            "Manifest y service worker presentes." if manifest_ok
            else "Falta manifest.json o sw.js."),
        _launch_item(
            "browser", "Navegador real", bool(dep_status.get("browser", {}).get("ready")),
            "Playwright/Chromium listo." if dep_status.get("browser", {}).get("ready")
            else "Instala la capacidad browser desde dependencias."),
        _launch_item(
            "launchers", "Lanzadores", all(launchers.values()),
            ", ".join(k for k, ok in launchers.items() if ok) or "Sin lanzadores."),
        _launch_item(
            "models", "Modelos disponibles", any_backend,
            "Hay al menos una ruta lista." if any_backend
            else "Revisa Ollama, LiteLLM o login de Claude/Codex."),
        _launch_item(
            "api_budget", "Budget API",
            not bool(health.get("api", {}).get("blocked")),
            health.get("api", {}).get("reason") or (
                f"{health.get('api', {}).get('spent_usd', 0)}/"
                f"{health.get('api', {}).get('limit_usd', 0)} USD usados")),
    ]
    ready = all(item["ok"] for item in items if item["key"] not in {"api_budget"})
    return {
        "ready": ready,
        "summary": "Calipso listo para uso diario" if ready else "Calipso usable, con puntos por revisar",
        "items": items,
        "connectors": health,
    }


@app.post("/api/deps/install")
async def api_deps_install(request: Request) -> dict:
    """Instala una capacidad ('tool') o un paquete pip arbitrario."""
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    if body.get("tool"):
        return await asyncio.to_thread(deps.ensure, body["tool"])
    if body.get("package"):
        # `deps.ensure_pip` corre `pip install <lo que venga>`, o sea ejecucion
        # de codigo arbitrario para cualquiera que tenga el token. La rama se
        # cierra: lo que se puede instalar es el catalogo cerrado de
        # `deps.TOOLS`, y para sumar algo se edita ese catalogo, no se manda
        # por HTTP.
        raise HTTPException(
            status_code=403,
            detail="instalar un paquete arbitrario esta cerrado: usa 'tool' "
                   "del catalogo de deps.TOOLS")
    raise HTTPException(status_code=400, detail="falta 'tool'")


@app.get("/api/browser/screenshot")
async def api_browser_screenshot(url: str, full: bool = False):
    """Screenshot real de una URL con el navegador (instala Playwright si falta)."""
    try:
        png = await asyncio.to_thread(calipso_browser.screenshot, url, None, full)
    except calipso_browser.UrlNoPermitida as e:
        # 400 y no 502: no es que el sitio fallo, es que no se va a mirar
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"no se pudo capturar: {e}")
    return Response(content=png, media_type="image/png")


@app.get("/api/updates")
def api_updates() -> dict:
    """Versiones de CLIs (+ si hay update en npm) y modelos nuevos descubiertos."""
    return discovery.updates()


@app.get("/api/plugins")
def api_plugins_list() -> dict:
    """Plugins instalados en Claude Code."""
    from calipso import plugins as calipso_plugins
    return {"plugins": calipso_plugins.list_installed()}


@app.get("/api/plugins/catalog")
def api_plugins_catalog(search: str = "", limit: int = 50) -> dict:
    """Catálogo de plugins disponibles en el marketplace."""
    from calipso import plugins as calipso_plugins
    return {"plugins": calipso_plugins.list_catalog(search=search, limit=limit)}


@app.post("/api/plugins/install")
async def api_plugins_install(request: Request) -> dict:
    """Instala un plugin via claude -p '/plugin <nombre>'."""
    from calipso import plugins as calipso_plugins
    body = await request.json()
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="falta name")
    return await asyncio.to_thread(calipso_plugins.install, name)


@app.post("/api/updates/run")
async def api_updates_run(request: Request) -> dict:
    """Ejecuta el comando de instalación para actualizar un CLI (claude o codex)."""
    body = await request.json()
    cli = body.get("cli", "")
    connector = SUBSCRIPTION_CONNECTORS.get(cli)
    if not connector:
        raise HTTPException(status_code=404, detail="CLI no soportado")
    cmd = connector.get("install")
    if not cmd:
        raise HTTPException(status_code=400, detail="sin comando de instalación")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout[-1000:],
            "stderr": result.stderr[-500:],
        }
    except Exception as e:
        return {"ok": False, "stderr": str(e)}


@app.post("/api/learn")
def api_learn(scope: str = "global") -> dict:
    """Bucle de aprendizaje: telemetría → pesos de ruteo.
    scope=global (todo) o scope=project (solo este repo)."""
    if scope == "project":
        return learning.learn(project_root=str(ROOT), project=str(ROOT))
    return learning.learn()


@app.get("/api/skills")
def api_skills() -> dict:
    return {"skills": [
        {"id": key, "name": value["name"], "prompt": value["prompt"]}
        for key, value in skills.REGISTRY.items()
    ]}


# --------------------------------------------------------------------------
# SESIONES  (elenco de agentes por sesión: nombre, modelo, intensidad)
# --------------------------------------------------------------------------

def _session_view(prof: dict) -> dict:
    """Perfil enriquecido con tier/ruta de cada modelo (para la UI)."""
    reg = capabilities.REGISTRY
    agents = []
    for mid, a in prof["agents"].items():
        m = reg.get(mid, {})
        agents.append({"model_id": mid, "name": a.get("name"),
                       "intensity": a.get("intensity"), "enabled": a.get("enabled", True),
                       "tier": m.get("tier"), "route": m.get("route"),
                       "model": m.get("model")})
    return {"id": prof["id"], "name": prof.get("name"), "agents": agents}


@app.get("/api/sessions")
def api_sessions() -> dict:
    active = sessions.active()
    return {"active": active["id"],
            "sessions": [{"id": s["id"], "name": s.get("name")}
                         for s in sessions.list_sessions()]}


@app.post("/api/sessions")
async def api_session_create(request: Request) -> dict:
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    return _session_view(sessions.create(body.get("name")))


@app.get("/api/session")
def api_session_get() -> dict:
    return _session_view(sessions.active())


@app.put("/api/session/active")
async def api_session_switch(request: Request) -> dict:
    body = await request.json()
    sid = body.get("id")
    if not sessions.load(sid):
        raise HTTPException(status_code=404, detail="sesion no existe")
    sessions.set_active(sid)
    return _session_view(sessions.active())


@app.put("/api/session/agent")
async def api_session_agent(request: Request) -> dict:
    body = await request.json()
    mid = body.get("model_id")
    if not mid:
        raise HTTPException(status_code=400, detail="falta model_id")
    try:
        prof = sessions.set_agent(
            sessions.active()["id"], mid,
            name=body.get("name"),
            intensity=body["intensity"] if "intensity" in body else "_keep",
            enabled=body.get("enabled"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _session_view(prof)


@app.get("/api/costs")
def api_costs(month: str | None = None) -> dict:
    """Reporte de gastos del mes (suscripciones fijas + API por token)."""
    return costs.monthly_report(month)


@app.get("/api/memory")
def api_memory() -> dict:
    """Estado de la memoria (para el panel / debugging)."""
    return {
        "core": mem.load_core(),
        "global_episodes": mem.glob.count(),
        "project_episodes": mem.project.count() if mem.project else 0,
    }


def _core_files(scope_obj) -> list[dict]:
    files = []
    for path in sorted(scope_obj.core_dir.glob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            text = ""
        files.append({
            "name": path.name,
            "stem": path.stem,
            "chars": len(text),
            "preview": text[:2000],
        })
    return files


@app.get("/api/memory/core")
def api_memory_core() -> dict:
    """Core markdown visible para el panel Memoria, sin exponer secretos."""
    calipso_chronology.ensure()
    return {
        "global": {
            "path": str(mem.glob.core_dir),
            "files": _core_files(mem.glob),
        },
        "project": {
            "path": str(mem.project.core_dir) if mem.project else "",
            "files": _core_files(mem.project) if mem.project else [],
        },
    }


@app.get("/api/memory/chronology")
def api_memory_chronology() -> dict:
    """Linea de tiempo global de Pedro, curada por bibliotecario."""
    return {"chronology": calipso_chronology.load()}


@app.get("/api/memory/inbox")
def api_memory_inbox(status: str | None = "pending") -> dict:
    return {
        "proposals": librarian.list_proposals(str(ROOT), status),
        "events": librarian.events(str(ROOT), 50),
    }


@app.post("/api/memory/inbox/proposals")
def api_memory_propose(body: MemoryProposalBody) -> dict:
    try:
        proposal = librarian.propose(
            str(ROOT), body.text, scope=body.scope, target=body.target,
            rationale=body.rationale, source=body.source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"proposal": proposal}


@app.post("/api/memory/chronology/proposals")
def api_memory_chronology_propose(body: ChronologyProposalBody) -> dict:
    try:
        text = calipso_chronology.format_entry(
            body.text, topic=body.topic, date=body.date)
        proposal = librarian.propose(
            str(ROOT), text, scope="global", target=calipso_chronology.FILENAME,
            rationale=body.rationale or "actualizacion de cronologia personal",
            source={"kind": "chronology"})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"proposal": proposal, "chronology": calipso_chronology.load()}


@app.post("/api/memory/inbox/suggest")
def api_memory_suggest(body: MemorySuggestBody) -> dict:
    proposals = librarian.suggest_from_text(str(ROOT), body.text, source=body.source)
    return {"proposals": proposals}


@app.put("/api/memory/inbox/proposals/{proposal_id}")
def api_memory_update(proposal_id: str, body: MemoryProposalUpdateBody) -> dict:
    proposal = librarian.update(
        str(ROOT), proposal_id,
        **body.dict(exclude_unset=True))
    if not proposal:
        raise HTTPException(status_code=404, detail="propuesta no existe")
    return {"proposal": proposal}


@app.post("/api/memory/inbox/proposals/{proposal_id}/accept")
def api_memory_accept(proposal_id: str) -> dict:
    proposal = librarian.accept(str(ROOT), proposal_id)
    if not proposal:
        raise HTTPException(status_code=404, detail="propuesta no existe")
    return {"proposal": proposal, "memory": api_memory()}


@app.post("/api/memory/inbox/proposals/{proposal_id}/discard")
def api_memory_discard(proposal_id: str, body: MemoryDiscardBody | None = None) -> dict:
    proposal = librarian.discard(str(ROOT), proposal_id, body.reason if body else None)
    if not proposal:
        raise HTTPException(status_code=404, detail="propuesta no existe")
    return {"proposal": proposal}


@app.get("/api/telemetry")
def api_telemetry(limit: int = 100) -> dict:
    return {"events": telemetry.recent(limit)}


@app.get("/api/goals")
def api_goals(limit: int = 50) -> dict:
    return {
        "active": goals.active(str(ROOT)),
        "goals": goals.list_goals(str(ROOT), limit),
    }


@app.post("/api/goals")
def api_goal_create(body: GoalBody) -> dict:
    if not body.objective.strip():
        raise HTTPException(status_code=400, detail="falta objective")
    goal = goals.create(
        str(ROOT), body.objective, title=body.title,
        criteria=body.criteria, subtasks=body.subtasks,
        make_active=body.make_active)
    return {"goal": goal}


@app.get("/api/goals/{goal_id}")
def api_goal(goal_id: str) -> dict:
    goal = goals.load(str(ROOT), goal_id)
    if not goal:
        raise HTTPException(status_code=404, detail="meta no existe")
    return {"goal": goal, "events": goals.events(str(ROOT), goal_id)}


@app.put("/api/goals/{goal_id}")
def api_goal_update(goal_id: str, body: GoalUpdateBody) -> dict:
    changes = body.dict(exclude_unset=True)
    make_active = changes.pop("active", None)
    try:
        goal = goals.update(str(ROOT), goal_id, **changes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if not goal:
        raise HTTPException(status_code=404, detail="meta no existe")
    if make_active is True:
        goals.set_active(str(ROOT), goal_id)
        goal = goals.load(str(ROOT), goal_id) or goal
    elif make_active is False:
        active = goals.active(str(ROOT))
        if active and active.get("id") == goal_id:
            goals.set_active(str(ROOT), None)
    return {"goal": goal, "active": goals.active(str(ROOT))}


@app.post("/api/goals/{goal_id}/evidence")
def api_goal_evidence(goal_id: str, body: GoalEvidenceBody) -> dict:
    goal = goals.add_evidence(
        str(ROOT), goal_id, body.kind, body.text, **(body.data or {}))
    if not goal:
        raise HTTPException(status_code=404, detail="meta no existe")
    return {"goal": goal}


@app.post("/api/goals/{goal_id}/advance")
def api_goal_advance(goal_id: str) -> dict:
    result = developer.advance_goal(str(ROOT), goal_id)
    if not result:
        raise HTTPException(status_code=404, detail="meta no existe")
    return result


class DraftBody(BaseModel):
    file_path: str


@app.post("/api/goals/{goal_id}/draft")
async def api_goal_draft(goal_id: str, body: DraftBody) -> dict:
    brief = developer.draft_brief(str(ROOT), goal_id, body.file_path)
    if not brief:
        raise HTTPException(status_code=404, detail="meta sin subtarea activa o archivo no editable")

    job = brief["job"]
    try:
        raw = await asyncio.to_thread(
            _run_subscription_text,
            "claude", brief["system"], brief["user_msg"], "sonnet")
        new_content = developer._strip_fences(raw)
    except Exception as exc:
        jobs.update(str(ROOT), job["id"], status="failed", error=str(exc))
        raise HTTPException(status_code=502, detail=f"agente fallo: {exc}") from exc

    # Registrar propuesta
    change_id = uuid.uuid4().hex[:12]
    item = {
        "id": change_id,
        "path": body.file_path,
        "source": f"goal_draft:{goal_id}",
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    PENDING_CHANGES[change_id] = {**item, "content": new_content}
    diff = _proposal_diff(body.file_path, new_content)

    jobs.write_artifact(str(ROOT), job["id"], "draft.md", new_content)
    jobs.write_artifact(str(ROOT), job["id"], "draft.diff", diff)
    jobs.update(str(ROOT), job["id"], status="done",
                proposal_id=change_id, artifact="draft.diff")
    goals.add_evidence(
        str(ROOT), goal_id, "proposal",
        f"Borrador generado para {body.file_path} (propuesta {change_id})",
        job_id=job["id"], artifact="draft.diff")

    return {
        "proposal": {**item, "diff": diff},
        "job": jobs.load(str(ROOT), job["id"]),
        "subtask": brief["subtask"],
    }


@app.put("/api/goals/{goal_id}/criteria/{criterion_id}")
def api_goal_criterion(goal_id: str, criterion_id: str, body: GoalCriterionBody) -> dict:
    try:
        goal = goals.set_criterion(
            str(ROOT), goal_id, criterion_id, body.done, body.evidence)
    except KeyError:
        raise HTTPException(status_code=404, detail="criterio no existe")
    if not goal:
        raise HTTPException(status_code=404, detail="meta no existe")
    return {"goal": goal}


@app.put("/api/goals/{goal_id}/subtasks/{subtask_id}")
def api_goal_subtask(goal_id: str, subtask_id: str, body: GoalSubtaskBody) -> dict:
    try:
        goal = goals.set_subtask(str(ROOT), goal_id, subtask_id, body.status)
    except KeyError:
        raise HTTPException(status_code=404, detail="subtarea no existe")
    if not goal:
        raise HTTPException(status_code=404, detail="meta no existe")
    return {"goal": goal}


@app.get("/api/resources")
def api_resources() -> dict:
    """Estado de recursos del sistema + cola del resource_dispatcher."""
    if _rd is None:
        return {"available": False}
    return _rd.diagnose()


@app.get("/api/jobs")
def api_jobs(limit: int = 50) -> dict:
    return {"jobs": jobs.list_jobs(str(ROOT), limit)}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> dict:
    job = jobs.load(str(ROOT), job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job no existe")
    return {
        "job": job,
        "events": jobs.events(str(ROOT), job_id),
        "artifacts": jobs.artifacts(str(ROOT), job_id),
    }


@app.get("/api/jobs/{job_id}/artifacts/{name}")
def api_job_artifact(job_id: str, name: str) -> Response:
    if not jobs.load(str(ROOT), job_id):
        raise HTTPException(status_code=404, detail="job no existe")
    try:
        data = jobs.read_artifact(str(ROOT), job_id, name)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="artifact no existe")
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    content_type = "text/plain; charset=utf-8"
    if name.endswith(".json"):
        content_type = "application/json"
    elif name.endswith(".html"):
        content_type = "text/html; charset=utf-8"
    return Response(data, media_type=content_type)


@app.get("/api/commands")
def api_commands() -> dict:
    return {"commands": calipso_commands.list_commands()}


def _verification_inputs() -> tuple[list[dict], list[dict]]:
    try:
        status = api_git_status()
        files = status.get("files") or []
    except Exception:
        files = []
    proposals = [
        {k: v for k, v in item.items() if k != "content"}
        for item in PENDING_CHANGES.values()
    ]
    return files, proposals


@app.get("/api/verify/recommend")
def api_verify_recommend() -> dict:
    files, proposals = _verification_inputs()
    return {"plan": verification.recommend(files, proposals)}


@app.post("/api/verify/run")
async def api_verify_run(body: VerificationRunBody) -> dict:
    files, proposals = _verification_inputs()
    if body.files is not None:
        files = body.files
    if body.proposals is not None:
        proposals = body.proposals
    plan = verification.recommend(files, proposals)
    if body.commands is not None:
        plan["commands"] = body.commands
        plan["summary"] = " + ".join(str(c.get("command_id")) for c in body.commands)
    goal_id = body.goal_id
    if not goal_id:
        active_goal = goals.active(str(ROOT))
        goal_id = active_goal.get("id") if active_goal else None
    result = await asyncio.to_thread(verification.run_plan, str(ROOT), plan, goal_id)
    return {"plan": plan, **result, "goal": goals.load(str(ROOT), goal_id) if goal_id else None}


@app.post("/api/commands/run")
async def api_command_run(body: CommandRunBody) -> dict:
    goal_id = body.goal_id
    if not goal_id:
        active_goal = goals.active(str(ROOT))
        goal_id = active_goal.get("id") if active_goal else None
    try:
        result = await asyncio.to_thread(
            calipso_commands.run, str(ROOT), body.command_id, goal_id, body.timeout)
    except KeyError:
        raise HTTPException(status_code=400, detail="comando no permitido")
    return {
        "job": result["job"],
        "status": result["status"],
        "returncode": result["returncode"],
        "stdout_preview": (result.get("stdout") or "")[-2000:],
        "stderr_preview": (result.get("stderr") or "")[-2000:],
        "goal": goals.load(str(ROOT), goal_id) if goal_id else None,
    }


_whisper_model = None
_whisper_lock = asyncio.Lock()


async def _get_whisper():
    global _whisper_model
    async with _whisper_lock:
        if _whisper_model is None:
            from faster_whisper import WhisperModel
            _whisper_model = await asyncio.to_thread(
                WhisperModel, "tiny", device="cpu", compute_type="int8")
    return _whisper_model


@app.post("/api/transcribe")
async def api_transcribe(audio: UploadFile = File(...)) -> dict:
    import tempfile, os
    data = await audio.read()
    suffix = pathlib.Path(audio.filename or "audio.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        try:
            model = await _get_whisper()
        except ImportError:
            return {"text": "", "error": "faster-whisper no instalado — corre: pip install faster-whisper"}
        segments, info = await asyncio.to_thread(
            lambda: model.transcribe(tmp, beam_size=5, language=None, vad_filter=True))
        text = " ".join(s.text.strip() for s in segments).strip()
        return {"text": text, "language": info.language}
    except Exception as e:
        return {"text": "", "error": str(e)}
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass


async def _routines_ticker() -> None:
    """Corre rutinas vencidas mientras el server este vivo. Las tres viejas
    son locales; la rutina "departamento" abre red (despierta al jefe)."""
    handlers = _routine_handlers()
    while True:
        try:
            await asyncio.sleep(60)
            now = datetime.datetime.now()
            ran = await asyncio.to_thread(calipso_routines.run_due, now, handlers)
            for r in ran:
                print(f"[calipso] rutina {r['kind']} -> {r['status']}")
        except asyncio.CancelledError:  # pragma: no cover
            break
        except Exception:
            continue


# --------------------------------------------------------------------------
# ECONOMIA (spec 2026-08-24): tablero, cola, reloj y cierre
# --------------------------------------------------------------------------
try:
    from calipso.economia import (bus as _eco_bus, capacidad as _eco_cap,
                                  cola as _eco_cola,
                                  departamentos as _eco_deps,
                                  operacion as _eco_op,
                                  personal as _eco_personal,
                                  reloj as _eco_reloj,
                                  tipos as _eco_tipos)
    from calipso.economia.candado import candado as _eco_candado
    from calipso.economia.pagador import (Pagador as _EcoPagador,
                                          suscripcion_de_cliente as
                                          _eco_suscripcion,
                                          _ERRORES_ECONOMICOS as
                                          _eco_errores_economicos)
except Exception:  # economia no disponible: los endpoints responden inactivo
    _EcoPagador = None
    _eco_suscripcion = None
    _eco_bus = _eco_cola = _eco_op = _eco_personal = _eco_reloj = _eco_candado = None
    _eco_deps = None
    _eco_tipos = None
    _eco_errores_economicos = None

_ECO_BASE = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))


def _economia():
    """Estado FRESCO por request: el estado vive en los archivos, no en el
    proceso — asi dispatch (otro proceso) y este server no se pisan. Los
    endpoints que ESCRIBEN envuelven esta construccion en el candado."""
    if _EcoPagador is None:
        return None
    pagador = _EcoPagador.desde_entorno(_ECO_BASE)
    if pagador is None:
        return None
    eco = _ECO_BASE / "economia"
    return {
        "pagador": pagador,
        "cola": _eco_cola.Cola(eco / "cola.jsonl"),
        "reloj": _eco_reloj.Reloj(eco / "reloj.jsonl"),
        "bus": _eco_bus.Bus(eco / "bus.jsonl"),
        "personal": _eco_personal.LibroPersonal(eco / "personal.jsonl"),
    }


def _eco_ahora() -> tuple[str, str]:
    ahora = _dt.datetime.now()
    return (ahora.isoformat(timespec="seconds"),
            _eco_op.semana_iso(ahora.date().isoformat()))


class EcoAtenderBody(BaseModel):
    firma: dict | None = None


class EcoRelojInBody(BaseModel):
    categoria: str
    ref: str | None = None


class EcoCierreBody(BaseModel):
    presupuesto_direccion_mm: int = 0


class EcoAbrirBody(BaseModel):
    cuota_firmable_mpt: int
    reserva_personal_mpt: int = 0


class EcoConciliarBody(BaseModel):
    ts_in: str
    minutos: int


class MesaFinanciarBody(BaseModel):
    cuenta: str
    mm: int


class EcoSembrarDepartamentoBody(BaseModel):
    nombre: str
    zona: str  # "fabrica" | "personal" (deps.ZONA_FABRICA / ZONA_PERSONAL)
    presupuesto_semanal_mm: int = 0
    techo_api_ciclo_mm: int = 0
    explorar_explotar_pct: int = 50
    agresividad_pct: int = 30


class EcoSembrarSuscripcionBody(BaseModel):
    costo_mensual_mm: int  # el que Pedro paga de verdad; sin default
    # cuantas unidades da el plan por ciclo de 4 semanas. Nadie lo sabe
    # todavia (ni Pedro ni este endpoint pueden derivarlo del codigo):
    # ESTIMACION A AJUSTAR cuando se mida el uso real.
    capacidad_ciclo: int = 1_000
    # unidades del ciclo reservadas para el uso personal de Pedro, afuera
    # de la capacidad de la fabrica (capacidad.py:47-48). ESTIMACION A
    # AJUSTAR junto con capacidad_ciclo.
    reserva_personal: int = 200
    # precio equivalente por unidad si se comprara suelta via API en vez
    # de por el plan; es el tope de la escalada por escasez
    # (capacidad.py:59-60, 0.9x este numero). ESTIMACION A AJUSTAR.
    costo_api_mm_por_unidad: int = 3_000


class EcoSembrarBody(BaseModel):
    departamentos: list[EcoSembrarDepartamentoBody]
    suscripciones: dict[str, EcoSembrarSuscripcionBody] = {}


class EcoPersonalMovimientoBody(BaseModel):
    tipo: str  # "ingreso" | "gasto" (personal.py), o su sinonimo "egreso"
    monto_mm: int
    categoria: str
    nota: str = ""


# Pedro pidio el banco con estas palabras, textual: "ingresos y egresos"
# (ver el encargo). personal.py -- vocabulario preexistente, con sus
# propios tests y llamadores -- solo conoce "ingreso"/"gasto". La
# normalizacion vive ACA, en la frontera http, que es donde entran las
# palabras del usuario; personal.py no se toca.
_ECO_PERSONAL_TIPO_SINONIMOS = {"egreso": "gasto"}


class EcoFronteraAcunarBody(BaseModel):
    subtipo: str  # "capital" | "venta"
    destino: str
    monto_mm: int
    evidencia: dict
    # el slug del proyecto que vendio (spec 8.5): SIEMPRE requerido en una
    # venta, incluso si destino es trabajo:<id> -- el bus no sabe de que
    # proyecto es un trabajo, asi que no hay forma de derivarlo aca.
    proyecto: str | None = None


@app.get("/api/economia/tablero")
def api_eco_tablero() -> dict:
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    _, semana = _eco_ahora()
    # lector serializado: el libro se repara truncando, no se lee a medio
    # escribir (una lectura concurrente con un append de dispatch podria
    # comerse un asiento recien escrito)
    with _eco_candado(p0.ruta_libro):
        eco = _economia()
        m = eco["pagador"].mercado_fresco()
        tab = _eco_personal.tablero(m.k, m.registro, m.suscripciones,
                                    eco["reloj"], eco["personal"], semana)
        pendientes = len(eco["pagador"].pendientes())
    return {"activa": True, "tablero": tab, "pendientes": pendientes}


@app.get("/api/economia/cola")
def api_eco_cola() -> dict:
    eco = _economia()
    if not eco:
        return {"activa": False}
    return {"activa": True, "pendientes": eco["cola"].pendientes()}


@app.get("/api/economia/bus")
def api_eco_bus() -> dict:
    """Lo que Pedro necesita para decidir sobre cada propuesta.

    Lector serializado, como el resto de economia: el libro se repara
    truncando, asi que leerlo a medio append se come un asiento. El unico
    lector sin candado del archivo es `api_eco_cola`, y no es un ejemplo.
    """
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    _, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            eco = _economia()
            m = eco["pagador"].mercado_fresco()
            bus = _eco_bus.Bus(p0.ruta_bus)
            asientos = m.k.libro.asientos()
            propuestas = []
            for id_ in bus.ids():
                estado = bus.estado(id_)
                # la mesa es para decidir, no un historial: lo descartado,
                # muerto y liquidado no vuelve a aparecer
                if estado not in ("alta", "financiada"):
                    continue
                d = bus.datos(id_)
                # .get() con default, como situacion.py: una linea vieja o
                # de un esquema anterior en el bus real de Pedro no puede
                # tumbar la mesa entera con un 500 mudo.
                propuestas.append({
                    "id": id_, "estado": estado,
                    "departamento": d.get("departamento", ""),
                    "titulo": d.get("titulo", ""),
                    "presupuesto_mm": d.get("presupuesto_mm", 0),
                    "retorno_mm": d.get("retorno_mm", 0),
                    "criterio": d.get("criterio", {}),
                    "gastado_mm": _eco_bus.gastado(asientos, id_),
                    "aportes": _eco_bus.aportes(asientos, id_),
                })
            deps_fabrica = [
                {"cuenta": f"dep:{x.nombre}", "nombre": x.nombre,
                 "zona": x.zona,
                 "disponible_mm": m.k.saldo(f"dep:{x.nombre}")}
                for x in m.registro.todos() if x.zona == _eco_deps.ZONA_FABRICA]
            abierta = semana in _eco_cap.semanas_operativas(asientos)
    except _eco_errores_economicos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"activa": True, "semana": semana, "semana_abierta": abierta,
            "propuestas": propuestas, "departamentos": deps_fabrica}


@app.post("/api/economia/bus/{id}/financiar")
def api_eco_bus_financiar(id: str, body: MesaFinanciarBody) -> dict:
    """Pedro dice que si.

    SOLO acepta propuestas en `alta` y sin ningun aporte ya asentado en el
    libro. `financiar` permite cofinanciar una ya financiada, asi que el
    primer corte cierra el doble toque en un telefono lento. Pero
    `financiar` tambien transfiere ANTES de marcar: si el proceso muere
    entre las dos escrituras (disco lleno, crash a mitad de los appends), la
    plata ya salio y la propuesta queda igual en `alta`. Por eso el segundo
    corte mira el LIBRO (la fuente de verdad), no la marca. Deshabilitar el
    boton en la UI es la tercera linea de defensa, no la primera.
    """
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    ts, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            m = p0.mercado_fresco()
            bus = _eco_bus.Bus(p0.ruta_bus)
            if (bus.estado(id) != "alta"
                    or _eco_bus.aportes(m.k.libro.asientos(), id)):
                raise HTTPException(
                    status_code=400,
                    detail=f"la propuesta {id} ya no esta esperando plata")
            _eco_bus.financiar(m, bus, ts, semana, id, body.cuenta, body.mm)
    except HTTPException:
        raise
    except _eco_errores_economicos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"ok": True}


@app.post("/api/economia/bus/{id}/descartar")
def api_eco_bus_descartar(id: str) -> dict:
    """Pedro dice que no. Sin esto el jefe se frena al llegar a su techo.

    Mismo corte que su gemelo `financiar`, y por la misma razon: `financiar`
    transfiere ANTES de marcar, asi que si el proceso muere entre las dos
    escrituras (disco lleno, crash a mitad de los appends) la plata ya salio
    pero la propuesta queda en `alta`. Si esta funcion solo mirara el
    estado, ese caso se podria descartar -- y `descartada` es terminal,
    invisible para la mesa y para `evaluar_y_liquidar_muertos` (que solo
    recorre `activas()`), asi que la plata en `trabajo:<id>` quedaria
    enterrada sin ningun camino de vuelta salvo editar bus.jsonl a mano.
    """
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    ts, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            m = p0.mercado_fresco()
            bus = _eco_bus.Bus(p0.ruta_bus)
            if (bus.estado(id) != "alta"
                    or _eco_bus.aportes(m.k.libro.asientos(), id)):
                raise HTTPException(
                    status_code=400,
                    detail=f"la propuesta {id} ya no se puede descartar")
            _eco_bus.descartar(bus, ts, semana, id)
    except HTTPException:
        raise
    except _eco_errores_economicos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"ok": True}


@app.post("/api/economia/cola/{item_id}/atender")
def api_eco_atender(item_id: str, body: EcoAtenderBody) -> dict:
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    ts, semana = _eco_ahora()
    # fresco BAJO el candado: atender lee estado/datos de la cola, que debe
    # ser el snapshot actual, no uno tomado antes de adquirir el candado
    with _eco_candado(p0.ruta_libro):
        eco = _economia()
        eco["cola"].atender_carta(ts, semana, item_id, firma=body.firma)
    return {"ok": True}


@app.post("/api/economia/cola/{item_id}/rechazar")
def api_eco_rechazar(item_id: str) -> dict:
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    ts, semana = _eco_ahora()
    with _eco_candado(p0.ruta_libro):
        eco = _economia()  # fresco BAJO el candado: ve el libro actual
        eco["cola"].rechazar(eco["pagador"].mercado_fresco().k, ts, semana,
                             item_id)
    return {"ok": True}


@app.post("/api/economia/reloj/in")
def api_eco_reloj_in(body: EcoRelojInBody) -> dict:
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    ts, semana = _eco_ahora()
    with _eco_candado(p0.ruta_libro):
        eco = _economia()
        eco["reloj"].clock_in(ts, semana, body.categoria, ref=body.ref,
                              cola=eco["cola"])
    return {"ok": True}


@app.post("/api/economia/reloj/out")
def api_eco_reloj_out() -> dict:
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    ts, semana = _eco_ahora()
    with _eco_candado(p0.ruta_libro):
        eco = _economia()  # fresco BAJO el candado
        res = eco["reloj"].clock_out(eco["pagador"].mercado_fresco(),
                                     eco["cola"], ts, semana)
    return {"ok": True, **res}


@app.post("/api/economia/cierre")
def api_eco_cierre(body: EcoCierreBody) -> dict:
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    ts, semana = _eco_ahora()
    with _eco_candado(p0.ruta_libro):
        eco = _economia()  # fresco BAJO el candado (reentrante adentro)
        res = _eco_op.cerrar_semana_operativa(
            eco["pagador"].mercado_fresco(), eco["bus"], eco["cola"],
            ts, semana,
            presupuesto_direccion_mm=body.presupuesto_direccion_mm)
        aplicados = eco["pagador"].reintentar_pendientes()
    return {"ok": True, "expiradas": res["expiradas"],
            "informes_ciclo": res["informes_ciclo"],
            "pendientes_aplicados": aplicados}


@app.post("/api/economia/abrir")
def api_eco_abrir(body: EcoAbrirBody) -> dict:
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    ts, semana = _eco_ahora()
    with _eco_candado(p0.ruta_libro):
        eco = _economia()  # fresco BAJO el candado
        _eco_op.abrir_semana(eco["pagador"].mercado_fresco().k, ts, semana,
                             body.cuota_firmable_mpt,
                             body.reserva_personal_mpt)
    return {"ok": True, "semana": semana}


@app.post("/api/economia/reloj/conciliar")
def api_eco_reloj_conciliar(body: EcoConciliarBody) -> dict:
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    ts, semana = _eco_ahora()
    with _eco_candado(p0.ruta_libro):
        eco = _economia()  # fresco BAJO el candado
        eco["reloj"].conciliar(ts, semana, body.ts_in, body.minutos)
    return {"ok": True}


@app.post("/api/economia/sembrar")
def api_eco_sembrar(body: EcoSembrarBody) -> dict:
    """Crea la economia desde cero: libro.jsonl vacio, departamentos.json y
    suscripciones.json (el plan maestro la llama Etapa 2 -- los specs 8.4 y
    8.5 la dan por hecha sin que exista). Parametrizado: Pedro manda la
    lista de departamentos con sus perillas y las suscripciones; nada de
    eso se hardcodea aca.

    Se NIEGA si la economia ya existe. El libro es append-only: sembrar dos
    veces no se deshace, asi que el corte es antes de escribir una sola
    linea, no un merge silencioso.

    Sin pagador, con cuidado: `Pagador.desde_entorno` exige que los tres
    archivos YA existan (por eso los ~20 fixtures de test que arman su
    propia economia siempre crean exactamente esos tres, ni uno mas ni uno
    menos), asi que antes de sembrar no hay pagador que devolver: p0 es
    None por construccion, siempre, en este endpoint. Lo que hace falta del
    pagador para tomar el MISMO candado que protege al resto de las
    escrituras no es el objeto validado por `desde_entorno` -- son solo sus
    rutas. `Pagador(eco_dir)` las da sin exigir que nada exista todavia
    (su __init__ solo arma pathlib.Path, no toca disco), asi que se
    construye un pagador "crudo" con eso alcanza para candado(pagador.ruta_libro).
    """
    if _EcoPagador is None:
        raise HTTPException(
            status_code=400,
            detail="la economia no esta disponible en este build")
    if not body.departamentos:
        raise HTTPException(
            status_code=400,
            detail="sembrar exige al menos un departamento (Pedro decide "
                   "cuales, no hay default)")
    eco_dir = _ECO_BASE / "economia"
    pagador = _EcoPagador(eco_dir)  # crudo: no pasa por desde_entorno
    try:
        with _eco_candado(pagador.ruta_libro):
            eco_dir.mkdir(parents=True, exist_ok=True)
            existentes = [str(p) for p in
                         (pagador.ruta_libro, pagador.ruta_registro,
                          pagador.ruta_sus) if p.exists()]
            if existentes:
                raise HTTPException(
                    status_code=400,
                    detail=("la economia ya esta sembrada "
                            f"({', '.join(existentes)}); para resetear, "
                            f"borra {eco_dir} a mano -- el libro es "
                            "append-only, sembrar de nuevo no lo deshace"))
            # validar TODO en memoria antes de escribir una sola linea: un
            # sembrado a medias (por un departamento invalido a mitad de
            # lista, por ejemplo) es un estado corrupto que nadie deshace
            departamentos = [_eco_deps.Departamento(**d.model_dump())
                             for d in body.departamentos]
            nombres = [d.nombre for d in departamentos]
            if len(nombres) != len(set(nombres)):
                raise HTTPException(
                    status_code=400,
                    detail=f"departamentos repetidos en el pedido: {nombres}")
            suscripciones = {nombre: _eco_cap.Suscripcion(nombre=nombre,
                                                          **s.model_dump())
                             for nombre, s in body.suscripciones.items()}

            registro = _eco_deps.Registro(pagador.ruta_registro)
            for d in departamentos:
                registro.alta(d)
            pagador.ruta_sus.write_text(
                json.dumps({n: dataclasses.asdict(s)
                           for n, s in suscripciones.items()},
                          ensure_ascii=False, indent=1),
                encoding="utf-8")
            pagador.ruta_libro.touch()
    except HTTPException:
        raise
    except (_eco_deps.ErrorDepartamento, _eco_cap.ErrorCapacidad) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"ok": True, "departamentos": nombres,
            "suscripciones": list(suscripciones)}


@app.post("/api/economia/personal/movimiento")
def api_eco_personal_movimiento(body: EcoPersonalMovimientoBody) -> dict:
    """El banco de Pedro (spec 8.4): un ingreso o un egreso SUYO, en
    personal.jsonl. Nunca acuna, nunca toca el libro de la fabrica --
    LibroPersonal.registrar ni siquiera abre el Kernel -- asi que la
    invariante 11 (los libros personales son privados) no se toca.
    """
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    ts, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            eco = _economia()  # fresco BAJO el candado
            tipo = _ECO_PERSONAL_TIPO_SINONIMOS.get(body.tipo, body.tipo)
            eco["personal"].registrar(ts, semana, tipo, body.monto_mm,
                                      body.categoria, nota=body.nota)
    except _eco_personal.ErrorPersonal as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"ok": True}


@app.post("/api/economia/frontera/acunar")
def api_eco_frontera_acunar(body: EcoFronteraAcunarBody) -> dict:
    """La unica puerta por la que entra plata de afuera (spec 8.5,
    invariante 1). Mismo molde que el resto de las escrituras de economia:
    candado, estado fresco adentro, errores de dominio a 400.

    Reglas taxativas, aplicadas ANTES de tocar el libro:
      - subtipo "capital" -> destino SOLO tesoro (Pedro pone plata suya).
      - subtipo "venta" -> destino SOLO proyecto:<slug> o trabajo:<id>
        vivo. Lo de "proyecto activo" no se puede verificar aca: el
        registro de proyectos es de otro spec (seccion 3) y todavia no
        existe en este repo, asi que solo se valida la FORMA del slug; lo
        de trabajo:<id> "vivo" si se verifica de verdad, contra el bus
        real (activas() = financiada, ni muerta ni liquidada ni
        descartada).
      - nunca dep:*, nunca direccion, nunca cuenta_pedro: el que vende es
        el proyecto, el departamento es el que trabaja (spec 8.5).
    """
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")

    if body.subtipo not in ("capital", "venta"):
        raise HTTPException(
            status_code=400,
            detail=f"subtipo invalido: {body.subtipo!r} (capital|venta)")

    detalle_extra: dict | None = None
    if body.subtipo == "capital":
        if body.destino != _eco_tipos.TESORO:
            raise HTTPException(
                status_code=400,
                detail="capital entra solo al tesoro (spec 8.5)")
    else:  # venta
        if (body.destino.startswith("dep:")
                or body.destino in (_eco_tipos.DIRECCION,
                                    _eco_tipos.CUENTA_PEDRO)):
            raise HTTPException(
                status_code=400,
                detail="una venta no entra a un departamento, direccion ni "
                       "cuenta_pedro: el que vende es el proyecto (spec 8.5)")
        if not body.proyecto:
            raise HTTPException(
                status_code=400,
                detail="una venta exige el proyecto que vendio "
                       "(detalle['proyecto'])")
        if body.destino.startswith("proyecto:"):
            slug = body.destino.split(":", 1)[1]
            if not slug:
                raise HTTPException(
                    status_code=400,
                    detail="proyecto:<slug> con slug vacio")
            if slug != body.proyecto:
                raise HTTPException(
                    status_code=400,
                    detail=f"proyecto ({body.proyecto!r}) no coincide con "
                           f"el destino ({body.destino!r})")
        elif not body.destino.startswith("trabajo:"):
            raise HTTPException(
                status_code=400,
                detail="venta exige destino proyecto:<slug> o trabajo:<id>")
        detalle_extra = {"proyecto": body.proyecto}

    ts, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            if body.subtipo == "venta" and body.destino.startswith("trabajo:"):
                id_trabajo = body.destino.split(":", 1)[1]
                if id_trabajo not in _eco_bus.Bus(p0.ruta_bus).activas():
                    raise HTTPException(
                        status_code=400,
                        detail=f"trabajo no vivo: {body.destino}")
                detalle_extra = {**detalle_extra, "trabajo": id_trabajo}
            asiento = p0.leer_kernel().acunar(
                ts, semana, body.destino, body.monto_mm,
                _eco_tipos.SubtipoAcunacion(body.subtipo), body.evidencia,
                detalle_extra=detalle_extra)
    except HTTPException:
        raise
    except _eco_errores_economicos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"ok": True, "asiento": {"seq": asiento.seq, "ts": asiento.ts,
                                    "destino": asiento.destino,
                                    "monto": asiento.monto,
                                    "subtipo": asiento.subtipo,
                                    "detalle": asiento.detalle}}


# El plantel tiene su PROPIO try/except, separado del bloque MAPA de abajo:
# un fallo importando calipso.plantel no puede caer en el mismo except que
# _mapa_ficha, porque _cobrar_turno corta en seco y cobra 0 cuando
# _mapa_ficha is None. Antes de esto, romper el plantel dejaba el chat
# entero cobrando en silencio a nadie.
try:
    from calipso.plantel import interruptor as _plantel_it
    from calipso.plantel import jefe as _plantel_jefe
except Exception:  # el plantel no esta disponible: el tablero responde inactivo
    _plantel_it = _plantel_jefe = None


class PlantelModoBody(BaseModel):
    modo: str


def _plantel_vista() -> dict:
    """Si el plantel no se pudo importar, el tablero lo dice en vez de
    reventar con un AttributeError sobre None."""
    if _plantel_it is None:
        return {"activo": False}
    e = _plantel_it.leer(_ECO_BASE)
    return {"activo": True, "encendido": e.encendido, "modo": e.modo,
            "techo_tics": e.techo_tics}


@app.get("/api/plantel")
def api_plantel() -> dict:
    return _plantel_vista()


@app.post("/api/plantel/parar")
def api_plantel_parar() -> dict:
    if _plantel_it is None:
        return _plantel_vista()
    _plantel_it.parar(_ECO_BASE)
    return _plantel_vista()


@app.post("/api/plantel/reanudar")
def api_plantel_reanudar() -> dict:
    if _plantel_it is None:
        return _plantel_vista()
    _plantel_it.reanudar(_ECO_BASE)
    return _plantel_vista()


@app.put("/api/plantel/modo")
def api_plantel_modo(body: PlantelModoBody) -> dict:
    if _plantel_it is None:
        return _plantel_vista()
    try:
        _plantel_it.poner_modo(_ECO_BASE, body.modo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _plantel_vista()


# --------------------------------------------------------------------------
# MAPA (spec 2026-08-25): el modelo de ciudad
# --------------------------------------------------------------------------
try:
    from calipso.economia import capacidad as _mapa_cap
    from calipso.mapa import ciudad as _mapa_ciudad
    from calipso.mapa import ficha as _mapa_ficha
    from calipso.mapa import foco as _mapa_foco
    from calipso.mapa import urbanismo as _mapa_urbanismo
except Exception:  # el mapa no esta disponible: el endpoint responde inactivo
    _mapa_ciudad = None
    _mapa_urbanismo = None
    _mapa_cap = None
    _mapa_ficha = None
    _mapa_foco = None


# --------------------------------------------------------------------------
# EL PULSO (spec 2026-08-25 secciones 5 y 6): la capa viva
# --------------------------------------------------------------------------
try:
    from calipso.mapa import pulso as _pulso_mod
    EL_PULSO = _pulso_mod.EL_PULSO
except Exception:  # sin pulso el mapa sigue mostrando la foto
    _pulso_mod = None
    EL_PULSO = None


def _pensar_local(prompt: str) -> str:
    """El escalon barato de verdad.

    OJO: NO se usa `_chunks_for("local", ...)`. En este server la ruta
    "local" no es Ollama — `_local_via_sub` ejecuta `claude -p`, o sea que
    decidir consumiria una unidad de suscripcion por tic y por departamento,
    y "decidir es gratis" seria falso.

    Y ojo con la trampa gemela, al reves: la ENTRADA de config
    `dispatch.CONFIG["local"]` si es Ollama (mismo host que el clasificador,
    modelo `qwen2.5:7b`) — no confundirla con la ruta `"local"` de arriba,
    que es un nombre distinto para una cosa distinta. Se usa esta entrada y
    NO `CONFIG["classifier"]` (`qwen2.5:3b`, el que usa `_plan_dynamic_team`):
    medido contra el modelo real, el 3b contesta "nada" y en el mismo parrafo
    se contradice explicando que lo prioritario seria explorar, mientras que
    el 7b sigue el formato de `decision.parsear`. Las dos entradas son
    igual de gratis (mismo Ollama local); la diferencia es solo el tamano
    del modelo.
    """
    cfg = dispatch.CONFIG["local"]
    data = dispatch._http_post_json(
        cfg["base_url"],
        {"model": cfg["model"], "prompt": prompt, "stream": False,
         "options": {"temperature": 0}})
    return str(data.get("response") or "")


def _publicar_jefe(cuenta: str):
    def publicar(evento: str, **campos):
        if EL_PULSO is None:
            return
        EL_PULSO.publicar(f"jefe:{cuenta}", evento, **campos)
    return publicar


def _contratar_para(cuenta: str, pagador, ts: str, semana: str):
    """Lo que el jefe hace cuando decidio que hay algo que hacer.

    `comentar` no toca el bus: el bus no tiene superficie de comentarios, asi
    que la opinion queda en la memoria del departamento (la escribe el jefe)
    y en el pulso.

    NO cobra capacidad por agentes planificados. La capacidad se consume
    cuando el trabajo CORRE, y ejecutar trabajo es la frontera de salida que
    este plan no construye (spec, seccion 11): `trabajar` es un no-op. Cobrar
    sobre un plan que nunca corre metia asientos falsos en el libro, y esos
    asientos alimentan el precio de la capacidad, que alimenta
    `sesgo_efectivo`, que alimenta la proxima decision del jefe — un libro
    con consumo inventado corrompe la señal de precio que realimenta al que
    decide. Un libro sin asiento es mejor que un libro con un asiento falso.

    Recibe `pagador` (no `bus`): `bus.alta` es una ESCRITURA, y la regla del
    modulo candado es no cachear escritores entre adquisiciones — el Bus se
    construye DE NUEVO, adentro del candado, cada vez que se escribe.
    """
    def contratar(situacion: dict, accion: str, ref: str | None,
                  motivo: str = ""):
        if accion == "comentar":
            # opinar es barato: no contrata a nadie y no cobra
            return {"accion": "comentar", "ref": ref, "en": "memoria"}

        if accion == "trabajar":
            # todavia no ejecuta: la frontera de salida no esta construida
            # (spec, seccion 11). Se deja el gancho, no un cobro fantasma.
            return {"accion": "trabajar", "ref": ref, "en": "nada",
                    "motivo": "ejecutar trabajo todavia no existe"}

        # accion == "proponer". SIN planificar aca: es una llamada a un
        # modelo cuya salida no lee nadie, en un bucle que corre desatendido
        # mientras Pedro duerme. Cuando exista la ejecucion de trabajo (la
        # frontera de salida que este plan no construye), planificar va a
        # vivir ahi, con la informacion de ese momento.
        #
        # SIN ESTO el jefe "propone" y no queda rastro: el criterio de exito
        # del spec (un departamento propone algo sin que Pedro le hable) se
        # mide en el bus, no en el pulso.
        #
        # Los numeros los declara el jefe desde sus PERILLAS, no el modelo:
        # pedirle un presupuesto a un modelo de 3b es pedirle un numero
        # alucinado que gasta plata de verdad.
        tope = (situacion["presupuesto_semanal_mm"]
                * situacion["agresividad_pct"] // 100)
        presupuesto = max(1, tope - situacion["salidas_semana_mm"])
        propuesta = f"{situacion['nombre']}-{uuid.uuid4().hex[:8]}"
        # El titulo del bus es lo que Pedro lee para decidir si financia: que
        # sea el motivo que el jefe razono, no el relleno del planificador
        # (`synthesis` es casi siempre la misma constante de fallback).
        titulo = (motivo or f"{accion} {ref or ''}".strip())[:120]
        # bus.alta ES una escritura: va bajo el mismo candado que las demas
        # escrituras de economia, con un Bus fresco construido adentro.
        with _eco_candado(pagador.ruta_libro):
            bus_fresco = _eco_bus.Bus(pagador.ruta_bus)
            bus_fresco.alta(ts, semana, propuesta, cuenta, titulo,
                            presupuesto, presupuesto,
                            {"gasto_max_mm": presupuesto, "semanas_max": 4})
        return {"accion": accion, "ref": ref, "propuesta": propuesta}
    return contratar


SONDEO_S = 0.25
LATIDO_CADA = 40          # sondeos: un latido cada diez segundos


class _MangoNulo:
    """Cuando el pulso no se pudo importar, el codigo instrumentado corre
    igual y no se llena de `if EL_PULSO is not None`."""

    resultado = "ok"

    def razonando(self, texto): pass
    def herramienta(self, nombre, resumen=""): pass
    def tokens(self, tokens_in, tokens_out, costo_mm=0): pass
    def diff(self, ruta, diff): pass


_MANGO_NULO = _MangoNulo()


@contextlib.contextmanager
def _pulso_agente(agente_id: str | None, **campos):
    if EL_PULSO is None or not agente_id:
        yield _MANGO_NULO
        return
    with EL_PULSO.agente(agente_id, **campos) as mango:
        yield mango


@app.websocket("/ws/mapa")
async def ws_mapa(ws: WebSocket) -> None:
    """El pulso, en vivo.

    Se sondea el anillo con un cursor en vez de que el publicador empuje:
    los agentes publican desde hilos de trabajo (`asyncio.to_thread`) y
    tocar el event loop desde otro hilo es la clase de cosa que anda hasta
    que no. El costo es un cuarto de segundo de latencia para ver pensar a
    un agente."""
    if not _valid(ws.cookies.get(COOKIE)):
        await ws.close(code=1008)   # politica violada: sin token valido
        return
    await ws.accept()
    if EL_PULSO is None:
        await ws.send_json({"evento": "sin-pulso"})
        await ws.close()
        return
    cursor = 0            # cero, no el presente: el que llega tarde recibe
    vueltas = 0           # lo que el anillo todavia guarda
    try:
        while True:
            cursor, nuevos = EL_PULSO.desde(cursor)
            for ev in nuevos:
                await ws.send_json(ev)
            vueltas += 1
            if vueltas % LATIDO_CADA == 0:
                # sin trafico, un socket muerto no se nota hasta el proximo
                # evento, que puede no llegar nunca
                await ws.send_json({"evento": "latido", "seq": cursor})
            await asyncio.sleep(SONDEO_S)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        # el cliente reconecta solo y el mapa sigue mostrando la foto, pero
        # que el socket se muera no puede ser invisible: sin esta linea, un
        # evento no serializable o un bug en Pulso.desde deja al cliente
        # reconectando para siempre y a nadie enterado
        print(f"[calipso] el pulso corto el socket del mapa: {exc}",
              file=sys.stderr)


# --------------------------------------------------------------------------
# LA MARCA DE FOCO (spec 2026-08-25 seccion 8): del chat a la camara
# --------------------------------------------------------------------------
def _edificios_livianos() -> list[dict]:
    """`{id, nombre}` de cada departamento registrado, sin abrir el libro.

    Resolver el nombre de un foco corre en cada turno de chat; el registro
    es un JSON de unas lineas y el libro puede ser de megabytes."""
    if _eco_deps is None or _EcoPagador is None:
        return []
    p0 = _EcoPagador.desde_entorno(_ECO_BASE)
    if p0 is None:
        return []
    try:
        registro = _eco_deps.Registro(p0.ruta_registro)
    except Exception:
        return []
    return [{"id": d.cuenta, "nombre": d.nombre} for d in registro.todos()]


def _resolver_foco(nombre: str) -> str | None:
    if _mapa_ficha is None:
        return None
    return _mapa_ficha.id_de_nombre(nombre, _edificios_livianos())


class Emisor:
    """Todo lo que Pedro lee sale por aca.

    Tres cosas en un solo lugar: retirar la marca de foco del texto visible,
    publicar el foco apenas aparece (la camara vuela mientras Calipso sigue
    escribiendo) y darle al pulso lo que se va diciendo. Antes los chunks
    salian desde cinco puntos de `ws_chat`, y filtrar en cinco lugares es
    filtrar en cuatro."""

    def __init__(self, ws, agente_id: str | None = None, resolver=None,
                 pulso=None, filtro=None):
        self.ws = ws
        self.agente_id = agente_id
        self._resolver = resolver or _resolver_foco
        self._pulso = pulso if pulso is not None else EL_PULSO
        self._filtro = filtro if filtro is not None else (
            _mapa_foco.Filtro() if _mapa_foco is not None else None)
        self.focos: list[str] = []

    async def _soltar(self, visible: str) -> str:
        if not visible:
            return ""      # un chunk vacio la UI vieja lo pinta igual
        await self.ws.send_json({"type": "chunk", "text": visible})
        if self._pulso is not None and self.agente_id:
            self._pulso.publicar(self.agente_id, "razonando", texto=visible)
        return visible

    async def chunk(self, texto: str) -> str:
        """Manda lo visible y devuelve exactamente eso, para que el que
        acumula la respuesta acumule lo mismo que Pedro leyo."""
        if self._filtro is None:
            return await self._soltar(texto)
        visible = await self._soltar(self._filtro.comer(texto))
        for nombre in self._filtro.tomar_focos():
            destino = self._resolver(nombre)
            if destino is None:
                continue          # el modelo se invento un departamento
            self.focos.append(destino)
            if self._pulso is not None:
                self._pulso.enfocar(destino)
        return visible

    async def cerrar(self) -> str:
        """Una marca que nunca cerro es texto y Pedro tiene que verlo."""
        if self._filtro is None:
            return ""
        return await self._soltar(self._filtro.cerrar())


def _limpiar_marcas(texto: str) -> str:
    """El parcial de la suscripcion se remanda ENTERO cada dos segundos, asi
    que no necesita la maquinaria de retencion del Filtro: alcanza con sacar
    las marcas completas. Una marca a medio llegar se limpia sola en el envio
    siguiente, porque el texto se relee desde cero."""
    return _mapa_foco.limpiar(texto) if _mapa_foco is not None else texto


def _ciudad_modelo() -> dict | None:
    """El modelo derivado del libro, SIN coordenadas.

    El endpoint le agrega el urbanismo; el chat, que solo quiere la ficha de
    un departamento, se ahorra esa mitad. None si la economia no esta."""
    if _mapa_ciudad is None or _EcoPagador is None:
        return None
    p0 = _EcoPagador.desde_entorno(_ECO_BASE)
    if not p0:
        return None
    _, semana = _eco_ahora()
    # lector serializado: el libro se repara truncando, no se lee a medio
    # escribir
    with _eco_candado(p0.ruta_libro):
        eco = _economia()
        m = eco["pagador"].mercado_fresco()
        asientos = m.k.libro.asientos()
        ops = _mapa_cap.semanas_operativas(asientos)
        minutos = eco["reloj"].minutos_por_categoria(ops[-4:]) if ops else {}
        return _mapa_ciudad.ciudad(
            asientos, m.registro, eco["bus"], eco["cola"], semana,
            minutos_empleo=minutos.get("empleo", 0),
            suscripciones=m.suscripciones)


@app.get("/api/mapa/ciudad")
def api_mapa_ciudad() -> dict:
    modelo = _ciudad_modelo()
    if modelo is None:
        return {"activa": False}
    posiciones = _mapa_urbanismo.urbanizar(modelo["edificios"],
                                           modelo["calles"])
    for e in modelo["edificios"]:
        x, y = posiciones.get(e["id"], (0, 0))
        e["x"], e["y"] = x, y
    return {"activa": True, "ciudad": modelo}


def _departamento_registrado(departamento: str | None) -> bool:
    """Si el id corresponde a un departamento del registro.

    Contra el REGISTRO -un JSON de unas lineas- y no contra la ciudad derivada
    del libro: son dos preguntas distintas y esta corre en cada turno."""
    if not departamento:
        return False
    return any(e["id"] == departamento for e in _edificios_livianos())


def _cuenta_en_foco(departamento: str | None) -> str:
    """La cuenta que paga lo que se gaste con este departamento tocado.

    El id llega del paquete del WebSocket, asi que esto es tambien la
    validacion. Un cargo a una cuenta sin departamento detras lo rechaza el
    mercado y queda pendiente para siempre: una linea por turno y sin techo."""
    if _mapa_ficha is None:
        return "personal"
    if not _departamento_registrado(departamento):
        return _mapa_ficha.CUENTA_PERSONAL
    return _mapa_ficha.cuenta_pagadora(departamento)


def _ficha_y_cuenta(departamento: str | None) -> tuple[str, str]:
    """(bloque de contexto, cuenta que paga) del departamento en foco.

    Dos preguntas distintas con dos fuentes distintas, a proposito. QUIEN PAGA
    se valida contra el registro. QUE SABE Calipso del departamento sale de
    `_ciudad_modelo`, que lee el libro entero bajo el candado y puede reventar
    mientras se lo repara.

    Conflacionar las dos cosas -que es lo que hacia `ws_chat`- degradaba el
    COBRO a `personal` cuando lo unico roto era la derivacion de la ficha, o
    sea justo cuando uno menos quiere que el gasto deje de asentarse. Un
    departamento de zona personal, en cambio, existe y tiene ficha: su cuenta
    colapsa a `personal` porque la zona personal no le compra nada a la
    fabrica (invariante 12), no porque el id sea invalido.

    Toma el candado del libro: se llama SIEMPRE desde un hilo."""
    if _mapa_ficha is None or not _departamento_registrado(departamento):
        # sin departamento que lo respalde no hay ficha que derivar tampoco:
        # el id inventado se ahorra el costo de la ciudad entera
        return "", _mapa_ficha.CUENTA_PERSONAL if _mapa_ficha else "personal"
    cuenta = _mapa_ficha.cuenta_pagadora(departamento)
    try:
        edificio = _mapa_ficha.edificio_de(_ciudad_modelo(), departamento)
    except Exception as exc:
        # invariante 5: una ficha que no se puede derivar degrada a "sin
        # ficha". El libro se repara truncando, asi que leerlo puede reventar;
        # que eso mate el WebSocket dejaria a Pedro sin `done` y al escritorio
        # del pulso sin `fin`.
        print(f"[calipso] no se pudo derivar la ficha de "
              f"{departamento}: {exc}", file=sys.stderr)
        edificio = None
    return (_mapa_ficha.bloque(edificio) if edificio else ""), cuenta


def _cobrar_turno(cuenta: str, route: str, client: str | None,
                  model: str | None, usage: dict) -> int:
    """La billetera del departamento en foco paga el turno.

    Nunca voltea el chat: lo que el mercado rechaza queda en
    cargos_pendientes.jsonl y la operacion lo reintenta. Toma el candado del
    libro, asi que se llama SIEMPRE desde un hilo. Devuelve las milimonedas
    cobradas: la de API es la unica que se cobra en monedas; la suscripcion
    -y la local, que es una suscripcion disfrazada- se cobran en unidades de
    capacidad, asi que devuelven cero."""
    if _EcoPagador is None or _mapa_ficha is None:
        return 0
    if not cuenta or cuenta == _mapa_ficha.CUENTA_PERSONAL:
        return 0
    pagador = _EcoPagador.desde_entorno(_ECO_BASE)
    if pagador is None:
        return 0
    ts, semana = _eco_ahora()
    try:
        if route == "api":
            return pagador.cargar_api(ts, semana, cuenta, model or "",
                                      usage.get("prompt_tokens", 0),
                                      usage.get("completion_tokens", 0)) or 0
        if route in ("subscription", "local"):
            # `local` no es Ollama: `_chunks_for` la resuelve con
            # `_local_via_sub`, que corre `claude -p`. Consume una unidad de
            # suscripcion igual que la ruta de suscripcion, y siempre la de
            # `claude`: el fallback local llega con el `client` de la ruta que
            # fallo, que no es el backend que termino contestando.
            cliente = "claude" if route == "local" else client
            pagador.cargar_suscripcion(ts, semana, cuenta,
                                       _eco_suscripcion(cliente))
    except Exception as exc:
        # el cobro es contabilidad, no la conversacion: que falle no puede
        # dejar a Pedro sin respuesta
        print(f"[calipso] no se pudo cobrar el turno a {cuenta}: {exc}",
              file=sys.stderr)
    return 0


def _asegurar_rutina_catastro() -> None:
    """`routines.DEFAULTS` solo siembra al crear routines.json por primera
    vez (`routines._seed`): una maquina como esta, que ya tenia
    routines.json de antes de que "catastro" existiera como kind, nunca lo
    ve aparecer solo -- confirmado en esta maquina, con GET /api/routines
    mostrando las tres rutinas viejas y ninguna de catastro. Sin esto, el
    catastro igual contesta bien (la primera lectura de `catastro.cargar()`
    escanea sola), pero nunca se refresca solo despues. Se corre una vez
    en cada arranque; agregar la rutina si falta es barato e idempotente."""
    try:
        if not any(r.get("kind") == "catastro" for r in calipso_routines.load()):
            calipso_routines.add(
                "catastro", "Escanear catastro de proyectos",
                60, enabled=True)
    except Exception:
        pass


@app.on_event("startup")
async def _startup_warm() -> None:
    try:
        found = await asyncio.to_thread(discovery.discover, True)
        if found["added"]:
            print(f"[calipso] modelos descubiertos: {found['added']}")
        await asyncio.to_thread(_backend_availability)  # pre-calienta el cache de probes
    except Exception:
        pass
    await asyncio.to_thread(_asegurar_rutina_catastro)
    try:
        asyncio.create_task(_routines_ticker())
    except Exception:
        pass


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/manifest.json")
def manifest() -> FileResponse:
    return FileResponse(WEB / "manifest.json", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker() -> FileResponse:
    return FileResponse(WEB / "sw.js", media_type="application/javascript")


@app.get("/fabrica")
def fabrica() -> FileResponse:
    """La consola de la fabrica. App propia: no toca la UI vieja de `/`."""
    return FileResponse(WEB / "fabrica" / "index.html")


@app.get("/fabrica/manifest.json")
def fabrica_manifest() -> FileResponse:
    """Manifest propio: el global arranca en `/` y abriria la UI vieja."""
    return FileResponse(WEB / "fabrica" / "manifest.json",
                        media_type="application/manifest+json")


# EstÃƒÂ¡ticos (por si aÃƒÂ±adimos assets locales: monaco vendorizado, iconos, etc.)
if WEB.exists():
    app.mount("/static", StaticFiles(directory=str(WEB)), name="static")


if __name__ == "__main__":
    # 0.0.0.0 = escucha en toda la red local: ÃƒÂ¡brelo desde el celular u otro PC
    # en el mismo WiFi con http://<IP-de-tu-PC>:8000
    import socket
    ip = socket.gethostbyname(socket.gethostname())
    print(f"[calipso] sirviendo {ROOT}")
    print(f"[calipso] token de acceso: {TOKEN}")
    print(f"[calipso] entra directo:   http://{ip}:8000/?token={TOKEN}")
    print(f"[calipso] local:  http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
