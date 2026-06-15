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
import datetime
import difflib
import hashlib
import hmac
import io
import json
import os
import pathlib
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
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# El cerebro (router) y la memoria viven en el repo raÃƒÂ­z / paquete calipso.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import dispatch  # noqa: E402
from calipso import capabilities  # noqa: E402
from calipso import chats  # noqa: E402
from calipso import config as calipso_config  # noqa: E402
from calipso import costs  # noqa: E402
from calipso import discovery  # noqa: E402
from calipso import learning  # noqa: E402
from calipso import orchestrator  # noqa: E402
from calipso import sessions  # noqa: E402
from calipso import telemetry  # noqa: E402
from calipso import web as calipso_web  # noqa: E402
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
<div class=c><div class=l>Calipso</div><p>Codigo de autenticador</p>
{error}
<form method=post action="/login">
<input name=code inputmode=numeric autocomplete=one-time-code pattern="[0-9 ]{{6,8}}"
autofocus placeholder="000000" maxlength=8><br><button>Entrar</button></form>
<p class=m>El token antiguo sigue funcionando como recuperacion con <code>?token=...</code>.</p></div>
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
    return HTMLResponse(LOGIN_HTML.replace("{error}", ""))


@app.post("/login")
async def login_submit(request: Request):
    body = (await request.body()).decode("utf-8", errors="ignore")
    data = urllib.parse.parse_qs(body)
    code = data.get("code", [""])[0]
    if _verify_totp(code):
        return _session_response("/")
    error = '<p class="err">Codigo invalido. Revisa el autenticador y vuelve a intentar.</p>'
    return HTMLResponse(LOGIN_HTML.replace("{error}", error), status_code=401)


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


@app.put("/api/file")
def api_save_file(body: SaveBody) -> dict:
    p = _safe(body.path)
    if p.is_dir():
        raise HTTPException(status_code=400, detail="es una carpeta")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body.content, encoding="utf-8", newline="")
    return {"ok": True, "bytes": len(body.content.encode("utf-8"))}


PENDING_CHANGES: dict[str, dict] = {}


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
def api_apply_proposal(change_id: str) -> dict:
    item = PENDING_CHANGES.get(change_id)
    if not item:
        raise HTTPException(status_code=404, detail="propuesta no existe")
    p = _safe(item["path"])
    if p.is_dir():
        raise HTTPException(status_code=400, detail="es una carpeta")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(item["content"], encoding="utf-8", newline="")
    del PENDING_CHANGES[change_id]
    return {"ok": True, "path": item["path"]}


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
    global ROOT, mem
    data = await request.json()
    raw = str(data.get("path") or "").strip().strip('"')
    if not raw:
        raise HTTPException(status_code=400, detail="falta ruta")
    p = pathlib.Path(os.path.expandvars(os.path.expanduser(raw))).resolve()
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=400, detail="la ruta no existe o no es carpeta")
    ROOT = p
    mem = Memory(project_root=str(ROOT))
    _remember_project(ROOT)
    return {"ok": True, "name": ROOT.name, "path": str(ROOT)}


def _switch_project(path: str) -> None:
    global ROOT, mem
    p = pathlib.Path(os.path.expandvars(os.path.expanduser(path))).resolve()
    if not p.exists() or not p.is_dir():
        raise HTTPException(status_code=400, detail="la ruta del chat no existe")
    ROOT = p
    mem = Memory(project_root=str(ROOT))
    _remember_project(ROOT)


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
    return {
        "routing": cfg["routing"],
        "subscription": {
            "claude": _subscription_probe("claude"),
            "codex": _subscription_probe("codex"),
        },
        "api": {
            "base_url": cfg["api"]["base_url"],
            "model": cfg["api"]["model"],
            "up": _http_up(cfg["api"]["base_url"].replace("/v1/chat/completions", "/health")),
        },
        "local": {
            "base_url": cfg["local"]["base_url"],
            "model": cfg["local"]["model"],
            "up": _http_up("http://localhost:11434/api/tags"),
        },
        "classifier": cfg["classifier"],
    }


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


SUBSCRIPTION_CONNECTORS = {
    "claude": {
        "install": ["npm.cmd", "install", "-g", "@anthropic-ai/claude-code@latest"],
        "login": ["claude.cmd", "auth", "login"],
        "docs": "https://code.claude.com/docs/en/setup",
    },
    "codex": {
        "install": ["npm.cmd", "install", "-g", "@openai/codex"],
        "login": ["codex.cmd", "login"],
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


def _backend_availability() -> dict:
    """Mapa {backend_key: disponible} para el router por capacidades."""
    cfg = calipso_config.load_config()
    ollama_up = _http_up_cached("http://localhost:11434/api/tags")
    api_up = _http_up_cached(
        cfg["api"]["base_url"].replace("/v1/chat/completions", "/health"))
    av: dict[str, bool] = {}
    for key, b in capabilities.load_backends().items():
        route = b.get("route")
        if route == "local":
            av[key] = ollama_up
        elif route == "api":
            av[key] = api_up
        elif route == "subscription":
            av[key] = _probe_cached(b.get("client")).get("ready", False)
        else:
            av[key] = False
    return av


def _backend_quota_low() -> dict:
    # TODO (fase C): leer cuota/saldo real por backend. Por ahora, ninguno.
    return {}


def _decide(user_msg: str) -> tuple[dict, dict, list, dict]:
    """Decisión a nivel de MODELO: directivas (slash/intensidad) -> features ->
    intensidad -> choose(). Devuelve (verdict, features, ranked, directivas)."""
    d = capabilities.parse_directives(user_msg)
    features = dispatch.extract_features(d["clean"])
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
                            verdict: dict) -> tuple[str, dict, str | None]:
    plan_obj = await asyncio.to_thread(_plan_dynamic_team, chat_msg, features)
    team = orchestrator.build_team(
        plan_obj, _backend_availability(), project_root=str(ROOT),
        session=sessions.active())
    agents = team.get("agents", [])
    if not agents:
        raise RuntimeError("no hay agentes disponibles para el equipo dinamico")
    await ws.send_json({"type": "agent", "action": "team", "agents": agents})
    results: list[dict] = []
    queued_msg: str | None = None
    for idx, agent in enumerate(agents, start=1):
        await ws.send_json({"type": "agent", "action": "start", "index": idx,
                            "agent": agent})
        agent_system = orchestrator.agent_system(agent, base_system)
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
    probes = {"claude": _subscription_probe("claude"), "codex": _subscription_probe("codex")}
    api_up = _http_up(cfg["api"]["base_url"].replace("/v1/chat/completions", "/health"))
    local_up = _http_up("http://localhost:11434/api/tags")
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


def _repo_brief() -> str:
    """Mapa compacto del repo para fallbacks sin herramientas de archivo."""
    files: list[str] = []
    for p in ROOT.rglob("*"):
        try:
            rel = p.relative_to(ROOT)
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
    for name in ("AGENTS.md", "CALIPSO.md", "README.md", "SETUP.md"):
        p = ROOT / name
        if not p.exists() or not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            continue
        if text:
            blocks.append(f"Extracto de {name}:\n{text[:1400]}")
    return "\n\n".join(blocks)[:REPO_BRIEF_MAX]


def _build_context(user_msg: str, runtime: str, features: dict | None = None) -> str:
    """Contexto ordenado para caché (estable -> volátil) y presupuestado.

    Estable (prefijo, se cachea en sub/api): identidad + memoria núcleo.
    Volátil (sufijo): recuerdos relevantes (podados por score) + estado real.
    Just-in-time: los archivos del repo NO se precargan; se piden bajo demanda.
    """
    # --- prefijo estable (cacheable) ---
    blocks = [SYSTEM]
    ident = _identity_doc()
    if ident:
        blocks.append("=== Constitucion de Calipso ===\n" + ident)
    core = mem.load_core()
    if core:
        blocks.append("=== Memoria nucleo ===\n" + core[:CONTEXT_CORE_MAX])

    # --- sufijo volátil ---
    recalled = [r for r in mem.recall(user_msg, n=8)
                if r["score"] >= RECALL_MIN_SCORE][:RECALL_MAX]
    if recalled:
        lines = "\n".join(f"- ({r['score']}) {r['text']}" for r in recalled)
        blocks.append("=== Recuerdos relevantes ===\n" + lines)
    if features and features.get("needs_repo"):
        blocks.append("=== Repo ===\n" + _repo_brief())
    blocks.append(runtime)
    return "\n\n".join(b for b in blocks if b)


def _chunks_for(route: str, system: str, user_msg: str, usage: dict,
                model: str | None = None, effort: int | None = None):
    """Devuelve (generador, modelo) segÃƒÂºn la ruta. Reusa los parsers de
    streaming del router (SSE / NDJSON) y captura tokens en 'usage'."""
    if route == "api":
        cfg = dispatch.CONFIG["api"]
        mdl = model or cfg["model"]
        payload = {"model": mdl, "stream": True,
                   "stream_options": {"include_usage": True}, "messages": [
                       {"role": "system", "content": system},
                       {"role": "user", "content": user_msg}]}
        if effort is not None:  # intensidad real para modelos thinking (vía LiteLLM)
            payload["output_config"] = {"effort": capabilities.EFFORT_PARAM[effort]}
        headers = {"Authorization": f"Bearer {cfg['api_key']}"}
        return dispatch._sse_text_chunks(cfg["base_url"], payload, headers, usage), mdl
    # local (Ollama) Ã¢â‚¬â€ y tambiÃƒÂ©n el fallback de cualquier otra ruta por ahora.
    cfg = dispatch.CONFIG["local"]
    mdl = model or cfg["model"]
    prompt = f"{system}\n\nUsuario: {user_msg}\nCalipso:"
    payload = {"model": mdl, "prompt": prompt, "stream": True}
    return dispatch._ollama_text_chunks(cfg["base_url"], payload, usage), mdl


def _subscription_invocation(client: str, system: str, user_msg: str,
                             model: str | None = None) -> tuple[list[str], dict, str | None, str | None]:
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
    prompt = f"Usuario: {user_msg}\nCalipso:"
    cmd = [exe if i == 0 else arg.replace("{prompt}", prompt)
           for i, arg in enumerate(template)]
    temp_name = None
    output_name = None
    if client == "claude":
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", suffix=".md", delete=False) as f:
            f.write(system_prompt)
            temp_name = f.name
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
    return cmd, env, temp_name, output_name


def _cleanup_subscription_files(temp_name: str | None, output_name: str | None) -> None:
    if temp_name:
        try:
            pathlib.Path(temp_name).unlink(missing_ok=True)
        except Exception:
            pass
    if output_name:
        try:
            pathlib.Path(output_name).unlink(missing_ok=True)
        except Exception:
            pass


def _run_subscription_text(client: str, system: str, user_msg: str,
                           model: str | None = None) -> str:
    cmd, env, temp_name, output_name = _subscription_invocation(
        client, system, user_msg, model)
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
        label: str = "proceso") -> tuple[str, str | None]:
    cmd, env, temp_name, output_name = _subscription_invocation(
        client, system, user_msg, model)
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
                            "label": label, "client": client, "model": model,
                            "prompt_tokens": max(1, (len(system) + len(user_msg)) // 4)})
        while proc.poll() is None:
            now = time.perf_counter()
            if now - last_notice >= 5:
                partial, _ = _read_partial()
                await ws.send_json({
                    "type": "process", "action": "running",
                    "label": label, "client": client, "model": model,
                    "elapsed": round(now - started),
                    "tokens": max(1, ((len(system) + len(user_msg)) + len(partial)) // 4),
                    "hint": "sigue corriendo; envia /stop para cancelar o escribe y lo atiendo al terminar"})
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
                                        "label": label})
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
            raise RuntimeError(msg or f"{client} fallo con exit {proc.returncode}")
        text = partial
        elapsed = round(time.perf_counter() - started)
        await ws.send_json({"type": "process", "action": "done",
                            "label": label, "elapsed": elapsed,
                            "tokens": max(1, ((len(system) + len(user_msg)) + len(text)) // 4)})
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
    try:
        while True:
            chat_id = chats.active_id()
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
                    else:
                        user_msg = raw
                except Exception:
                    user_msg = raw
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
            chats.append(chat_id, "user", user_msg)
            turn_started = time.perf_counter()
            fallbacks: list[dict] = []
            # avisa de inmediato que está pensando (los probes pueden tardar)
            await ws.send_json({"type": "thinking"})

            # 1) routing a nivel de MODELO (afinidad x costo x tier x intensidad)
            #    en un hilo: los probes de suscripción son síncronos y NO deben
            #    bloquear el event loop (si no, no se puede interrumpir/steerear).
            verdict, features, ranked, directives = await asyncio.to_thread(
                _decide, user_msg)
            if directives.get("help"):
                await ws.send_json({"type": "chunk", "text": HELP_TEXT})
                await ws.send_json({"type": "done"})
                continue
            chat_msg = directives["clean"]
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
            system = _build_context(chat_msg, runtime, features)
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
                    system = _build_context(chat_msg, runtime, features)
                    if web_material and (web_material["results"] or web_material["pages"]):
                        system += "\n\n" + calipso_web.context_block(web_material)
                    full, agent_team, queued = await _run_dynamic_team(
                        ws, inbox, chat_msg, features, system, verdict)
                    if queued:
                        pending = queued
                    used_route = "orchestrator"
                    usage["completion_tokens"] = len(full.split())
                    await ws.send_json({"type": "chunk", "text": full})
                elif route == "subscription":
                    full, queued = await _run_subscription_text_live(
                        ws, inbox, verdict["client"], system, chat_msg, model,
                        label=f"{verdict.get('persona') or verdict['client']} via {verdict['client']}")
                    if queued:
                        pending = queued
                    usage["completion_tokens"] = len(full.split())
                    await ws.send_json({"type": "chunk", "text": full})
                else:
                    gen, model = _chunks_for(route, system, chat_msg, usage, model,
                                             verdict.get("effort"))
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
                        full += chunk
                        await ws.send_json({"type": "chunk", "text": chunk})
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
                                system = _build_context(chat_msg, runtime, features)
                                full, queued = await _run_subscription_text_live(
                                    ws, inbox, alternate, system, chat_msg, None,
                                    label=f"fallback via {alternate}")
                                if queued:
                                    pending = queued
                                usage["completion_tokens"] = len(full.split())
                                await ws.send_json({"type": "chunk", "text": full})
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
                        system = _build_context(chat_msg, runtime, features)
                        gen, model = _chunks_for("local", system, chat_msg, usage)
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
                            full += chunk
                            await ws.send_json({"type": "chunk", "text": chunk})
                else:
                    await ws.send_json({"type": "error", "text": str(e)})
            except StopIteration:
                pass

            # 4) registrar costo/uso y avisar
            entry = costs.log_usage(
                used_route, model, usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0), client=verdict.get("client"))
            await ws.send_json({"type": "cost", "model": model, "route": used_route,
                                "tokens": entry["prompt_tokens"] + entry["completion_tokens"],
                                "cost_usd": entry["cost_usd"]})
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


@app.get("/api/updates")
def api_updates() -> dict:
    """Versiones de CLIs (+ si hay update en npm) y modelos nuevos descubiertos."""
    return discovery.updates()


@app.post("/api/learn")
def api_learn(scope: str = "global") -> dict:
    """Bucle de aprendizaje: telemetría → pesos de ruteo.
    scope=global (todo) o scope=project (solo este repo)."""
    if scope == "project":
        return learning.learn(project_root=str(ROOT), project=str(ROOT))
    return learning.learn()


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


@app.get("/api/telemetry")
def api_telemetry(limit: int = 100) -> dict:
    return {"events": telemetry.recent(limit)}


@app.on_event("startup")
async def _startup_warm() -> None:
    try:
        found = await asyncio.to_thread(discovery.discover, True)
        if found["added"]:
            print(f"[calipso] modelos descubiertos: {found['added']}")
        await asyncio.to_thread(_backend_availability)  # pre-calienta el cache de probes
    except Exception:
        pass


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


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
