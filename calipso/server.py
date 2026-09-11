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
import logging
import os
import pathlib
import re
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               RedirectResponse, Response)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

# El cerebro (router) y la memoria viven en el repo raÃƒÂ­z / paquete calipso.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import dispatch  # noqa: E402
from calipso import capabilities  # noqa: E402
from calipso import attachments  # noqa: E402
from calipso import chats  # noqa: E402
from calipso.compositor import redactor as compositor_redactor  # noqa: E402
from calipso.compositor import ejemplos as compositor_ejemplos  # noqa: E402
from calipso import config as calipso_config  # noqa: E402
from calipso import browser as calipso_browser  # noqa: E402
from calipso import catastro  # noqa: E402
from calipso import chronology as calipso_chronology  # noqa: E402
from calipso import connectors as calipso_connectors  # noqa: E402
from calipso import consumo as calipso_consumo  # noqa: E402
from calipso import costs  # noqa: E402
from calipso import developer  # noqa: E402
from calipso import deps  # noqa: E402
from calipso import discovery  # noqa: E402
from calipso import github as calipso_github  # noqa: E402
from calipso import learning  # noqa: E402
from calipso import goals  # noqa: E402
from calipso import inbox as _inbox  # noqa: E402
from calipso import jobs  # noqa: E402
from calipso import librarian  # noqa: E402
from calipso import orchestrator  # noqa: E402
from calipso.privacidad import conversacion, redaccion  # noqa: E402
from calipso.privacidad import nube as privacidad_nube  # noqa: E402
from calipso.abismo import consulta as abismo_consulta  # noqa: E402
from calipso.abismo import contrato as abismo_contrato  # noqa: E402
from calipso.abismo import filtro as abismo_filtro  # noqa: E402
from calipso.abismo import marca as abismo_marca  # noqa: E402
from calipso.abismo import turno as abismo_turno  # noqa: E402
from calipso.abismo import viaje as abismo_viaje  # noqa: E402
try:
    from calipso import resource_dispatcher as _rd  # noqa: E402
except Exception:
    _rd = None  # type: ignore[assignment]
from calipso import prompt_compiler  # noqa: E402
from calipso import routines as calipso_routines  # noqa: E402
from calipso import backup as calipso_backup  # noqa: E402
from calipso import sesiones  # noqa: E402
from calipso import sessions  # noqa: E402
from calipso import skills  # noqa: E402
from calipso import telemetry  # noqa: E402
from calipso import web as calipso_web  # noqa: E402
from calipso import aduana  # noqa: E402
from calipso import canarios  # noqa: E402
from calipso import memoria_procedencia  # noqa: E402
from calipso import tokenizador  # noqa: E402
from calipso import verification  # noqa: E402
from calipso.tools import commands as calipso_commands  # noqa: E402
from calipso.memory import EMBED_MODEL, Memory, leer_carta  # noqa: E402

# RaÃƒÂ­z del proyecto que Calipso muestra/edita. Por defecto, el cwd.
ROOT = pathlib.Path(os.environ.get("CALIPSO_ROOT", os.getcwd())).resolve()
WEB = pathlib.Path(__file__).parent / "web"

# El arranque no pasa por _switch_project, asi que su techo (no abrir el
# home entero) se replica aca: `python calipso/server.py` corrido desde ~
# dejaba ROOT=home con todo lo que eso abre por /api/file (revision de
# seguridad 2026-09-07, ronda del punto 2). Se degrada al repo de Calipso.
if ROOT == pathlib.Path.home().resolve():
    ROOT = pathlib.Path(__file__).resolve().parent.parent
    print(f"[calipso] CALIPSO_ROOT era el home entero: degradado a {ROOT}")

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

# La cookie de la capa de sesion: identidad de APARATO, no de la
# maquina. Es la unica credencial que vale desde afuera, y jamas
# contiene ni deriva el TOKEN (invariante 1). El max_age espeja el
# sueno de `sesiones.SESION_SUENO_DIAS`: una cookie que sobreviva a
# la sesion solo consigue 401 al aparato.
COOKIE_SESION = "calipso_sesion"
SESION_COOKIE_MAX_AGE = 30 * 86400


def _home_calipso() -> pathlib.Path:
    """El home de Calipso, con CALIPSO_HOME por delante del `~`.

    Los otros veinte modulos que resuelven esta ruta (config.py, memory.py,
    economia/pagador.py, consumo.py, ...) miran la variable; estas dos
    lineas eran las unicas del paquete que no, y las dos ESCRIBEN al
    importarse la primera vez (`_load_token` genera y guarda un token si no
    existe). O sea que un `import calipso.server` con CALIPSO_HOME puesto
    -una suite, un script, un subproceso- podia escribir igual en el
    ~/.calipso real. La red del conftest no lo cubre: fija la variable, y
    estas dos lineas no la leian."""
    return pathlib.Path(os.environ.get("CALIPSO_HOME",
                                       os.path.expanduser("~/.calipso")))


_TOKEN_FILE = _home_calipso() / "token"
_TOTP_SECRET_FILE = _home_calipso() / "totp_secret"


def _host() -> str:
    """Donde escucha el servidor. Por defecto, solo esta maquina.

    Hasta el 2026-08-31 esto era un `host="0.0.0.0"` escrito a mano en el
    `__main__`. CALIPSO_HOST existia, pero solo lo leia launch_calipso.py:24
    para decidir que URL abrir en el navegador y cual sondear: NO ataba el
    socket. O sea que Calipso escuchaba en toda la wifi siempre, con un token
    que viaja en el query string y que hasta hoy vivia en 0644.

    El default se cierra. Para abrirlo hay que pedirlo, y se ve al arrancar:

        CALIPSO_HOST=0.0.0.0 python calipso/server.py

    Para llegar desde otro aparato -el lector- el camino es Tailscale, no la
    wifi: direccion estable por aparato, cifrado, y sin abrir un puerto a
    cualquiera que este en la misma red."""
    return os.environ.get("CALIPSO_HOST", "127.0.0.1")


def _endurecer(ruta: pathlib.Path) -> None:
    """Deja el archivo en 0600 si estaba mas abierto.

    El token no es solo un segundo factor: el shell de escritorio entra con
    el (`/?token=...`) en vez de pedir TOTP, asi que es LA credencial de esta
    instalacion. Un 0644 lo deja legible para cualquier otro usuario de la
    maquina, y el que lo lee entra a un servidor con acceso a todos los
    archivos de Pedro y a los endpoints que mueven plata."""
    try:
        modo = ruta.stat().st_mode & 0o777
        if modo & 0o077:
            ruta.chmod(0o600)
    except OSError:
        pass          # sin permiso para cambiarlo: mejor seguir que no arrancar


def _escribir_secreto(ruta: pathlib.Path, contenido: str) -> None:
    """Crea el archivo ya en 0600, sin una ventana en la que este abierto."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.touch(mode=0o600, exist_ok=True)
    _endurecer(ruta)
    ruta.write_text(contenido, encoding="utf-8")


def _load_token() -> str:
    if (env := os.environ.get("CALIPSO_TOKEN")):
        return env
    if _TOKEN_FILE.exists():
        _endurecer(_TOKEN_FILE)
        return _TOKEN_FILE.read_text(encoding="utf-8").strip()
    tok = secrets.token_urlsafe(12)
    _escribir_secreto(_TOKEN_FILE, tok)
    return tok


TOKEN = _load_token()


def _valid(provided: str | None) -> bool:
    return bool(provided) and hmac.compare_digest(provided, TOKEN)


def _get_totp_secret() -> str:
    if _TOTP_SECRET_FILE.exists():
        _endurecer(_TOTP_SECRET_FILE)
        return _TOTP_SECRET_FILE.read_text(encoding="utf-8").strip()
    raw = secrets.token_bytes(20)
    secret = base64.b32encode(raw).decode("ascii").rstrip("=")
    _escribir_secreto(_TOTP_SECRET_FILE, secret)
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
    if not _TOTP_SECRET_FILE.exists():
        # Sin secreto no hay codigo que valga, y CREARLO no es cosa de esta
        # funcion. `_get_totp_secret` lo genera cuando falta, y /login entra
        # sin guard: cualquier POST con seis digitos -un remoto anonimo, un
        # flatpak, otro uid- daba a luz el secreto sin que nadie viera el
        # QR, y la ventana del punto 1 del guard ("no existe totp_secret")
        # se cerraba para siempre con un secreto que Pedro nunca enrolo. El
        # unico lugar que lo crea es `setup_page`, detras de esa ventana.
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


def _es_loopback(host: str | None) -> bool:
    """La propia maquina. Incluye "testclient" (el host sintetico del
    TestClient de Starlette) para que la suite ejercite los flujos locales;
    ese valor no puede llegar por red real (no es una IP)."""
    return (host or "") in ("127.0.0.1", "::1", "::ffff:127.0.0.1",
                            "localhost", "testclient")


def _desde_de_sesion(sesion) -> dict:
    """`desde` del Quien (spec seccion 4) a partir de `_ws_autorizado` (ws:
    dict | True) o de `getattr(request.state, "sesion", None)` (http: dict |
    None). El guard solo puebla `request.state.sesion` en la rama de cookie
    de sesion; con el token de loopback no hay atributo: eso ES maquina."""
    if isinstance(sesion, dict):
        return {"credencial": "sesion", "tipo": sesion.get("tipo"),
                "aparato": sesion.get("aparato"),
                "hash": (sesion.get("hash_id") or "")[:8]}
    return {"credencial": "maquina"}


def _proyecto() -> str:
    """El `proyecto` del Quien (spec seccion 4): el nombre de ROOT en este
    momento (ROOT es global y conmutable: se lee al armar el Quien, nunca
    se cachea). `pathlib.Path("/").name` es "" y `Quien.__post_init__`
    levanta 'proyecto vacio': con ROOT en la raiz se caia el websocket en
    cada turno. UNICO sitio que deriva el proyecto de ROOT."""
    return ROOT.name or str(ROOT)


def _quien_http(request: Request, origen: str, endpoint: str, **campos) -> aduana.Quien:
    """El Quien de un endpoint: `ui` (lo dispara la pagina sola, un GET al
    cargar) o `gesto` (un click, un POST), con `endpoint`, `desde` y el
    proyecto de ROOT en este momento (`_proyecto()`)."""
    return aduana.Quien(origen=origen, proyecto=_proyecto(), endpoint=endpoint,
                        desde=_desde_de_sesion(getattr(request.state, "sesion", None)),
                        **campos)


def _gesto_de(directives: dict) -> str | None:
    """El slash reconstruido desde `capabilities.parse_directives` (spec
    seccion 4). Un solo texto: /web manda (es el gesto que abre la web); si
    no, /nube; si no, el de ruta (/claude /codex /local /api); /plan; o
    `/model X`. Sin slash, None: el proposito dice que fue por heuristica.
    `effort` no se reconstruye: lo ponen tanto /fast como la palabra
    'rapido', y por AST no se distinguen."""
    if directives.get("force_web"):
        return "/web"
    if directives.get("nube"):
        return "/nube"
    fr = directives.get("force_route")
    fm = directives.get("force_model")
    if fr == "subscription" and fm in ("claude", "codex"):
        return "/" + fm
    if fr in ("local", "api"):
        return "/" + fr
    if directives.get("force_team"):
        return "/plan"
    if fm:
        return f"/model {fm}"
    return None


# --- freno de fuerza bruta del login (revision de seguridad 2026-09-07, C3)
# Sin esto, /login (la unica ruta sin guard) aceptaba intentos infinitos de
# TOTP a velocidad de loopback: ~333k de esperanza para ganar EL token.
# Backoff exponencial por host desde el 5to fallo, y un balde global ("*")
# desde el 20mo para que varias IPs de una LAN no paralelicen el ataque.
_LOGIN_MAX_FALLOS_HOST = 5
_LOGIN_MAX_FALLOS_GLOBAL = 20
_LOGIN_BACKOFF_BASE = 2.0    # segundos: 2, 4, 8, ... por fallo extra
_LOGIN_BACKOFF_TOPE = 900.0  # 15 minutos
_login_lock = threading.Lock()
_login_fallos: dict[str, list] = {}  # clave -> [fallos, monotonic del ultimo]
_login_reloj = time.monotonic        # inyectable en tests


def _login_espera(clave: str, max_fallos: int) -> float:
    """Segundos de castigo que le quedan a esta clave (0 = puede intentar)."""
    with _login_lock:
        reg = _login_fallos.get(clave)
        if not reg or reg[0] < max_fallos:
            return 0.0
        fallos, ultimo = reg
        castigo = min(_LOGIN_BACKOFF_TOPE,
                      _LOGIN_BACKOFF_BASE * (2 ** (fallos - max_fallos)))
        return max(0.0, castigo - (_login_reloj() - ultimo))


def _login_fallo(clave: str) -> None:
    """Registra el fallo y DECAE lo viejo: por cada ventana completa de
    calma (el tope de castigo, 900s) el contador baja UNO, y la entrada
    recien muere al llegar a cero. Dos disenos anteriores fallaron y los
    dos los cazo la verificacion adversaria: el trinquete monotono (nunca
    olvidaba: los typos de semanas escalaban a lockouts de 15 minutos para
    todos, y un host hostil sostenia ese DoS con un fallo cada tanto) y la
    poda que BORRABA la entrada entera (regalaba una rafaga fresca de
    intentos a un atacante que pausara 901s: de ~96 a ~1300 intentos/dia,
    simulado). El decaimiento conserva ambas propiedades: la historia
    inocente se evapora sola y el atacante pausado ve su contador bajar de
    a uno por ventana, no reiniciarse."""
    with _login_lock:
        ahora = _login_reloj()
        for k in list(_login_fallos):
            fallos, ultimo = _login_fallos[k]
            ventanas = int((ahora - ultimo) // _LOGIN_BACKOFF_TOPE)
            if ventanas <= 0:
                continue
            fallos -= ventanas
            if fallos <= 0:
                del _login_fallos[k]
            else:
                # el resto de la ventana en curso se conserva: adelantar
                # `ultimo` solo lo decaido evita descontar dos veces
                _login_fallos[k] = [
                    fallos, ultimo + ventanas * _LOGIN_BACKOFF_TOPE]
        fallos = _login_fallos.get(clave, [0, 0.0])[0]
        _login_fallos[clave] = [fallos + 1, ahora]


def _login_exito(clave: str) -> None:
    with _login_lock:
        _login_fallos.pop(clave, None)


# --- freno propio del alta de aparatos (spec, invariante 6)
# Golpear/estado/canjear entran SIN credencial (un aparato que todavia no
# existe no tiene ninguna), asi que llevan freno igual que /login. La
# maquinaria es la misma; las claves son otras a proposito: con el balde
# compartido, veinte golpes anonimos dejaban a Pedro afuera de su propio
# TOTP -- el DoS del login regalado a cualquiera que alcance el puerto.
_APARATOS_EXENTAS = ("/api/aparatos/golpear", "/api/aparatos/estado",
                     "/api/aparatos/canjear")


def _aparatos_espera(host: str) -> float:
    """Segundos de castigo que le quedan al alta desde ese host (0 = pasa)."""
    return max(_login_espera(f"aparatos:{host}", _LOGIN_MAX_FALLOS_HOST),
               _login_espera("aparatos:*", _LOGIN_MAX_FALLOS_GLOBAL))


def _aparatos_fallo(host: str) -> None:
    """Cuenta un golpe nuevo -tambien el que sale bien, para que quien
    martilla se frene solo- y un estado/canje con un id desconocido. Sondear
    un pedido VALIDO no pasa por aca: es el flujo feliz esperando a Pedro, y
    cobrarselo mataria al aparato legitimo que sondea cada pocos segundos."""
    _login_fallo(f"aparatos:{host}")
    _login_fallo("aparatos:*")


def _aparatos_frenado(espera: float) -> JSONResponse:
    """El 429 del freno. No cuenta como fallo (no llego a intentar nada) y
    dice cuando volver: el aparato legitimo que se paso reintenta solo."""
    return JSONResponse({"detail": "demasiados intentos"}, status_code=429,
                        headers={"Retry-After": str(int(espera) + 1)})


# --- el tope del cuerpo en las rutas sin credencial
# Golpear/estado/canjear y /login leen un body que manda cualquiera, y
# uvicorn no limita el tamano: `await request.json()` era un cuerpo de GB
# creciendo en memoria antes de que el freno se cobrara nada. 4 KB es
# holgado -un golpe pesa menos de cien bytes, un login menos de veinte-.
CUERPO_MAX_BYTES = 4096


def _cuerpo_declarado_excede(request: Request) -> bool:
    """El Content-Length, cuando viene: el rechazo mas barato, antes de leer
    un solo byte. Un cliente que mienta (o mande chunked, sin cabecera) se
    topa igual con el tope de `_leer_cuerpo_acotado`."""
    largo = request.headers.get("content-length", "")
    return largo.isdigit() and int(largo) > CUERPO_MAX_BYTES


def _cuerpo_grande() -> JSONResponse:
    return JSONResponse({"detail": "cuerpo demasiado grande"}, status_code=413)


async def _leer_cuerpo_acotado(request: Request) -> bytes:
    """El body entero, o 413 apenas pasa el tope: se lee por trozos y se
    corta ahi, asi que lo que sobra nunca toca la memoria."""
    cuerpo = bytearray()
    async for trozo in request.stream():
        cuerpo.extend(trozo)
        if len(cuerpo) > CUERPO_MAX_BYTES:
            raise HTTPException(status_code=413,
                                detail="cuerpo demasiado grande")
    return bytes(cuerpo)


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


def _sin_credencial(path: str) -> Response:
    """La puerta cerrada: json para las apis, la pantalla de login para el
    resto. Se llama desde dos ramas del guard -sin nada, y con una credencial
    que no vale desde ahi- y las dos tienen que contestar IGUAL: un remoto
    que distinguiera los dos casos tendria un oraculo de validez del token."""
    if path.startswith("/api") or path.startswith("/ws"):
        return JSONResponse({"detail": "no autorizado"}, status_code=401)
    return RedirectResponse(url="/login", status_code=303)


def _expirar_token_viajero(resp: Response, request: Request,
                           host: str) -> Response:
    """La limpieza del punto 4 del guard: la cookie-token que un remoto
    PRESENTA se expira, valga o no. Esas cookies se plantaron con un anio de
    vida cuando el token si viajaba, y hay dos poblaciones que limpiar: el
    navegador que trae la vieja y ninguna otra cosa (401), y el que ademas
    trae una sesion viva porque entro por /login despues del upgrade -- la
    rama del token no llega a mirarlo nunca y el TOKEN seguiria saliendo a
    la red en cada request hasta 2027.

    "Valga o no" es lo que importa, por dos razones. Rotar el token es paso
    obligatorio del despliegue (spec, "Migracion y despliegue"), y despues
    de rotar la cookie vieja ya no es valida: condicionar la limpieza a
    `_valid` la dejaba viva un anio, justo en el orden que el spec manda. Y
    condicionarla era un oraculo (C8): status y body son iguales para la
    cookie valida y la invalida a proposito, pero el Set-Cookie solo para
    la valida le decia a un remoto si un token fugado por otra via seguia
    vigente. Borrando lo que el cliente presento, valga o no, solo aprende
    que mando una cookie -- cosa que ya sabe."""
    if not _es_loopback(host) and request.cookies.get(COOKIE) is not None:
        resp.delete_cookie(COOKIE)
    return resp


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    path = request.url.path
    host = request.client.host if request.client else ""
    if path == "/login":
        if request.method == "POST" and _cuerpo_declarado_excede(request):
            return _cuerpo_grande()
        return await call_next(request)
    if (path == "/setup" and _es_loopback(host)
            and not _TOTP_SECRET_FILE.exists()
            and _valid(request.query_params.get("token"))):
        # La ventana del primer arranque, con las tres condiciones juntas.
        # Loopback solo no alcanza: en esta maquina corren flatpaks y otros
        # uid, y cualquiera de ellos habria podido pedir el QR antes que
        # Pedro y quedarse con SU segundo factor. El token si prueba que es
        # el uid de Pedro, porque `~/.calipso/token` esta en 0600. Con el
        # secreto ya escrito la ventana se cierra sola y /setup vuelve al
        # camino normal (donde la pantalla ya no muestra nada).
        return await call_next(request)
    if path == "/setup" and not _TOTP_SECRET_FILE.exists():
        # Fuera de esa ventana, /setup no se sirve a NADIE mientras el
        # secreto falte: servirlo es CREARLO (`_get_totp_secret` lo genera y
        # lo escribe) y despues mostrarlo en claro. Sin esta linea, una
        # sesion `navegador` -alcance `*`- se llevaba el segundo factor de
        # Pedro desde otra maquina: la sesion se revoca (invariante 9), el
        # enrolamiento del autenticador NO, y ese aparato entraria por
        # /login para siempre sin pasar nunca por la Ally (invariante 4).
        # Con el secreto ya escrito la regla no aplica: la pantalla de
        # despues no muestra nada y sigue siendo una ruta como cualquier
        # otra.
        return _sin_credencial(path)
    if request.method == "POST" and path in _APARATOS_EXENTAS:
        # el alta de aparatos no puede exigir credencial -es como se
        # consigue la primera- y paga con su freno propio. Por METODO
        # ademas de por path: un GET a estas rutas sigue el camino normal.
        espera = _aparatos_espera(host)
        if espera > 0:
            return _aparatos_frenado(espera)
        if _cuerpo_declarado_excede(request):
            # pesa como un golpe mas: quien manda cuerpos asi no es un
            # aparato esperando a Pedro
            _aparatos_fallo(host)
            return _cuerpo_grande()
        return await call_next(request)
    if (galleta_sesion := request.cookies.get(COOKIE_SESION)):
        # La credencial de un APARATO, y la unica que vale desde afuera. Va
        # a un hilo porque `resolver` puede escribir (renueva `ultima_vez`
        # con histeresis, y mata a la que se durmio): el flock jamas en el
        # event loop. Una cookie que no resuelve -revocada, caduca, basura-
        # sigue de largo: quizas el mismo request trae el token y viene de
        # la propia maquina.
        ses = await asyncio.to_thread(sesiones.resolver, galleta_sesion)
        if ses:
            # `.get` y no `ses["tipo"]`: el registro sale del disco, y
            # `permite` es fail-closed hasta con un tipo que no es texto --
            # un KeyError aca desarmaria justo esa defensa (500 en vez de
            # 403) para un archivo editado a mano al que le falte el campo
            if not sesiones.permite(ses.get("tipo"), path, request.method):
                # el alcance aplica a TODA ruta, no solo a /api (invariante
                # 3): el `tablero` que pide /fabrica/algo tambien rebota
                return _expirar_token_viajero(JSONResponse(
                    {"detail": "fuera del alcance del aparato"},
                    status_code=403), request, host)
            request.state.sesion = ses
            resp = await call_next(request)
            if ses.get("renovada"):
                # el aparato que entra todos los dias no puede perder la
                # cookie a los 30 dias con la sesion viva: cada renovacion
                # del almacen re-planta la cookie con max_age fresco
                resp.set_cookie(COOKIE_SESION, galleta_sesion, httponly=True,
                                samesite="lax", max_age=SESION_COOKIE_MAX_AGE)
            return _expirar_token_viajero(resp, request, host)
    galleta_token = request.cookies.get(COOKIE)
    if _valid(galleta_token) or _valid(request.query_params.get("token")):
        # C8 (revision de seguridad 2026-09-07) y despues el invariante 2 de
        # la capa de sesion: el TOKEN identifica a la MAQUINA de Pedro, asi
        # que vale solo desde ella -- por cookie igual que por URL. Un
        # aparato remoto entra por identidad de aparato (la cookie de
        # sesion) o por /login con TOTP, que le da una.
        # (los websockets NO pasan por este middleware http: ws_chat y
        # ws_mapa autentican su propio handshake -- no agregar "/ws" aca
        # creyendo que protege)
        if not _es_loopback(host):
            # y ADEMAS expira la cookie-token si vino (el `?token=` a secas
            # no dispara la limpieza: no hay nada que borrar). La misma
            # respuesta, cabecera por cabecera, que la de la rama de abajo
            # con una cookie-token invalida: ver `_expirar_token_viajero`
            return _expirar_token_viajero(_sin_credencial(path), request,
                                          host)
        if _valid(galleta_token):
            return await call_next(request)
        if path.startswith("/api") or request.method != "GET":
            resp = await call_next(request)
            resp.set_cookie(COOKIE, TOKEN, httponly=True, samesite="lax",
                            max_age=31_536_000)
            return resp
        return _session_response(path)
    # sin credencial que valga desde aca. Si el remoto trajo una cookie-token
    # que NO vale (la de antes de rotar el token), se expira igual que la
    # valida de arriba: distinguirlas por el Set-Cookie era el oraculo de
    # validez que C8 cerro, y sin esto las viejas vivian su anio entero
    return _expirar_token_viajero(_sin_credencial(path), request, host)


async def _ws_autorizado(ws: WebSocket) -> dict | bool | None:
    """La credencial del handshake: el punto 6 del guard, el unico que no
    vive en `auth_guard` -- ese es middleware http y los websockets no lo
    cruzan. Sin esta funcion los ws se quedaban con "cookie == TOKEN", que
    desde afuera es justo lo que el invariante 2 prohibe.

    Devuelve el registro de la sesion cuando entro por sesion (el corte por
    generaciones necesita saber DE QUIEN es el socket) mas `generacion`, la
    foto del registro de revocaciones para ese hash; `True` cuando entro
    con el token desde la propia maquina; y None cuando no entra. La sesion
    se mira primero para que el que trae las dos cosas quede identificado
    como aparato y no como maquina.

    Que ws abre cada tipo no se decide aca: lo dice la tabla de alcances
    (`/ws/mapa` figura en la del tablero; a `/ws/chat` solo lo cubre el `*`
    del navegador). Una segunda copia de esa tabla en el handshake se
    desincronizaria sola.
    """
    host = ws.client.host if ws.client else ""
    if (galleta_sesion := ws.cookies.get(COOKIE_SESION)):
        # La foto de la generacion se saca ANTES de resolver, por hash. Al
        # reves -resolver en el hilo y fotografiar al envolver el socket-
        # una revocacion que aterrizara entre las dos cosas (almacen ya
        # revocado, contador ya subido) dejaba un socket con la foto NUEVA:
        # vigente para siempre, sordo a la revocacion que ya paso. Con la
        # foto primero cualquier intercalado cierra, porque
        # `aparatos_revocar` escribe el almacen antes de subir el contador:
        # o `resolver` ya devuelve None, o la foto es la vieja y el primer
        # chequeo corta.
        generacion = _generacion_de(sesiones.hash_de(galleta_sesion))
        # a un hilo por lo mismo que en el guard: `resolver` puede escribir
        # (renueva `ultima_vez`, mata a la dormida) y el flock jamas corre
        # en el event loop
        ses = await asyncio.to_thread(sesiones.resolver, galleta_sesion)
        # el handshake es un GET. `.get("tipo")` y no `ses["tipo"]`: el
        # registro sale del disco y `permite` es fail-closed hasta con el
        # campo ausente -- un KeyError aca desarmaria esa misma defensa
        if ses and sesiones.permite(ses.get("tipo"), ws.url.path, "GET"):
            return dict(ses, generacion=generacion)
    if _valid(ws.cookies.get(COOKIE)) and _es_loopback(host):
        # el token identifica a la MAQUINA de Pedro, asi que vale solo desde
        # ella (invariante 2): un aparato remoto entra por sesion o no entra
        return True
    return None


# --------------------------------------------------------------------------
# EL CORTE EN VIVO: revocar mata los websockets que YA estaban abiertos
# (spec seccion 3, "Corte de WS vivos"; invariante 9)
# --------------------------------------------------------------------------
# Hasta aca revocar solo cerraba la puerta a los handshakes NUEVOS: el socket
# que ya estaba adentro seguia hablando hasta que el cliente se fuera. El
# registro es de memoria a proposito -- lo unico que tiene que sobrevivir es
# el proceso que sostiene esos sockets; despues de un reinicio no queda
# ninguno vivo y `resolver` ya rechaza a la revocada en el handshake.
_ws_generaciones: dict[str, int] = {}


def _generacion_de(hash_id: str) -> int:
    """Cero es la respuesta para el hash que nadie revoco todavia: asi el
    handshake no tiene que dar de alta nada."""
    return _ws_generaciones.get(hash_id, 0)


def _revocar_en_vivo(hash_id: str) -> None:
    """Le mueve el piso a los sockets abiertos de esa sesion: la generacion
    que guardaron en el handshake deja de coincidir y el proximo chequeo los
    cierra.

    Incrementa aunque no haya ningun socket abierto -- averiguarlo costaria
    un registro de conexiones y el dict crece, como mucho, con una entrada
    por revocacion de la vida del proceso.

    LIMITE CONOCIDO: la expiracion por reloj (una sesion que se duerme o
    cumple 180 dias mientras su ws esta abierto) no pasa por aca; esa muere
    en la proxima reconexion, cuando `resolver` la rechaza."""
    _ws_generaciones[hash_id] = _generacion_de(hash_id) + 1


class _SocketVigilado:
    """El socket de una sesion, envuelto para que ninguna emision sobreviva a
    la revocacion.

    Por que un proxy y no un chequeo en cada punto de emision: `ws_chat`
    emite desde 46 lugares -- el cuerpo del handler, los helpers que reciben
    el `ws` (`_run_dynamic_team`, `_run_subscription_text_live`), la clase
    `Emisor` y el borrador que corre suelto con `ensure_future`. Tocarlos uno
    por uno deja el invariante colgado del proximo que agregue el numero 47.
    Envolver el socket una sola vez, apenas se sabe de quien es, cubre a todos
    sin que ninguno se entere.

    Envuelve las cinco puertas del socket y no solo las dos que el server usa
    hoy (`send_json` y `receive_text`) por lo mismo: la que se estrene manana
    ya nace vigilada. Lo demas pasa derecho por `__getattr__` (`cookies`,
    `client`, `url`, `accept`, `close`): esto es un guardia, no una fachada.
    """

    def __init__(self, ws: WebSocket, hash_id: str,
                 generacion: int | None = None) -> None:
        self._ws = ws
        self._hash_id = hash_id
        # la foto del handshake: si el numero cambia, esta sesion se revoco
        # despues de que este socket entrara. La saca `_ws_autorizado`
        # ANTES de resolver (ver ahi por que); sin foto se toma la de ahora
        self._generacion = (_generacion_de(hash_id) if generacion is None
                            else generacion)

    def __getattr__(self, nombre: str):
        return getattr(self._ws, nombre)

    def vigente(self) -> bool:
        return _generacion_de(self._hash_id) == self._generacion

    async def cerrar_revocado(self) -> None:
        """1008 es "politica violada", el mismo codigo con el que el
        handshake rechaza a una sesion muerta: el cliente ve una sola razon
        de cierre y no tiene que distinguir el momento.

        El cierre puede fallar (el cliente ya se fue, el socket ya se cerro
        por el otro lado) y eso no cambia lo que hay que hacer: dejar de
        hablarle."""
        with contextlib.suppress(Exception):
            await self._ws.close(code=1008)

    async def _vigilar(self) -> None:
        if self.vigente():
            return
        await self.cerrar_revocado()
        # WebSocketDisconnect y no una excepcion propia: cada handler ya la
        # atrapa para limpiar cuando el cliente se desconecta, y una sesion
        # revocada es exactamente eso, un cliente que dejo de estar
        raise WebSocketDisconnect(1008)

    async def send_json(self, *args, **kwargs):
        await self._vigilar()
        return await self._ws.send_json(*args, **kwargs)

    async def send_text(self, *args, **kwargs):
        await self._vigilar()
        return await self._ws.send_text(*args, **kwargs)

    async def send_bytes(self, *args, **kwargs):
        await self._vigilar()
        return await self._ws.send_bytes(*args, **kwargs)

    async def receive_text(self, *args, **kwargs):
        await self._vigilar()
        return await self._ws.receive_text(*args, **kwargs)

    async def receive_json(self, *args, **kwargs):
        await self._vigilar()
        return await self._ws.receive_json(*args, **kwargs)


async def _vigilar_socket(
        ws: WebSocket,
        sesion: dict | bool | None) -> WebSocket | _SocketVigilado | None:
    """Envuelve el socket cuando entro por sesion y lo deja crudo cuando
    entro con el token: el token es la maquina de Pedro y esta capa no lo
    revoca (su unica revocacion es rotarlo en la Ally).

    Falla CERRADO: un registro de sesion sin `hash_id` no tiene con que
    vigilarse, y un socket que ninguna revocacion pueda alcanzar no entra
    -- se cierra con 1008 y se devuelve None, antes del accept. Hoy no
    pasa (`resolver` busca por hash), pero esto es una capa de
    autenticacion y la version anterior devolvia el socket crudo."""
    if sesion is True:
        return ws
    hash_id = sesion.get("hash_id") if isinstance(sesion, dict) else None
    if not hash_id:
        await ws.close(code=1008)
        return None
    return _SocketVigilado(ws, hash_id, sesion.get("generacion"))


async def _cortar_si_revocada(ws: WebSocket | _SocketVigilado) -> bool:
    """True cuando la sesion del socket se revoco -- y para entonces el
    socket ya quedo cerrado con 1008.

    Es el chequeo de los bucles que pueden pasar horas sin emitir ni recibir
    nada: sin el, un socket ocioso sobrevive a la revocacion hasta que
    alguien hable."""
    if not isinstance(ws, _SocketVigilado) or ws.vigente():
        return False
    await ws.cerrar_revocado()
    return True


_TOTP_DISABLED = os.environ.get("CALIPSO_NO_TOTP", "").strip().lower() in ("1", "true", "yes")


def _totp_bypass_permitido(host: str | None) -> bool:
    """S3 (decidida en el spec de ojos-y-manos, implementada en la revision
    de seguridad 2026-09-07, C7): CALIPSO_NO_TOTP es un interruptor de
    desarrollo y SOLO vale desde la propia maquina. Un origen remoto exige
    TOTP siempre, aunque la variable haya quedado puesta."""
    return _TOTP_DISABLED and _es_loopback(host)


def _login_mode_html(host: str | None) -> str:
    if _totp_bypass_permitido(host):
        return ('<p style="color:#4ea1ff;font-size:13px">TOTP desactivado '
                '— ingresa cualquier codigo</p>')
    return "<p>Codigo de autenticador</p>"


@app.get("/login")
def login_page(request: Request) -> HTMLResponse:
    cliente = request.client.host if request.client else ""
    return HTMLResponse(LOGIN_HTML.replace("{error}", "")
                        .replace("{totp_mode}", _login_mode_html(cliente)))


@app.post("/login")
async def login_submit(request: Request):
    cliente = request.client.host if request.client else ""
    espera = max(_login_espera(cliente, _LOGIN_MAX_FALLOS_HOST),
                 _login_espera("*", _LOGIN_MAX_FALLOS_GLOBAL))
    if espera > 0:
        error = (f'<p class="err">Demasiados intentos. '
                 f'Espera {int(espera) + 1} segundos.</p>')
        return HTMLResponse(LOGIN_HTML.replace("{error}", error)
                            .replace("{totp_mode}", _login_mode_html(cliente)),
                            status_code=429)
    body = (await _leer_cuerpo_acotado(request)).decode("utf-8",
                                                        errors="ignore")
    data = urllib.parse.parse_qs(body)
    code = data.get("code", [""])[0]
    if _totp_bypass_permitido(cliente) or _verify_totp(code):
        # el exito limpia el contador del host; el balde global queda (un
        # acierto en medio de una lluvia de fallos no la amnistia)
        _login_exito(cliente)
        if _es_loopback(cliente):
            return _session_response("/")
        # Desde afuera, el premio del TOTP es una SESION, jamas el token
        # (invariante 1). Es la unica excepcion a "el aparato no se aprueba
        # solo", y es explicita en el spec: un codigo del autenticador es
        # Pedro en persona, no un aparato consagrandose. El alcance es
        # `navegador` porque quien tiene el TOTP ya tiene la casa entera.
        id_sesion = await asyncio.to_thread(
            sesiones.crear_viva, f"navegador {cliente}"[:60], "navegador")
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie(COOKIE_SESION, id_sesion, httponly=True,
                        samesite="lax", max_age=SESION_COOKIE_MAX_AGE)
        return resp
    _login_fallo(cliente)
    _login_fallo("*")
    error = '<p class="err">Codigo invalido. Revisa el autenticador y vuelve a intentar.</p>'
    return HTMLResponse(LOGIN_HTML.replace("{error}", error)
                        .replace("{totp_mode}", _login_mode_html(cliente)),
                        status_code=401)


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


# --------------------------------------------------------------------------
# ALTA DE APARATOS: golpear -> Pedro aprueba -> canjear (capa de sesion)
# --------------------------------------------------------------------------
# Los tres primeros son los EXENTOS del guard y entran sin credencial. Los
# otros viven detras del guard y ademas exigen la propia maquina: aprobar es
# solo-loopback (invariante 4), asi que ninguna sesion consagra jamas a otra.


async def _cuerpo_json(request: Request) -> dict:
    """El body como dict, o vacio si vino roto. Estas rutas las pega
    cualquiera sin credencial: un cuerpo basura tiene que morir en la
    validacion del almacen -422 y un fallo contado- y no en un 500.

    Y un cuerpo que pase el tope muere en 413 sin leerse entero. El guard
    ya rechazo el Content-Length declarado; aca cae el que vino chunked o
    mintio la cabecera. En las rutas sin credencial cuenta como fallo del
    freno; en aprobar/rechazar (la Ally) no, que el freno es del alta.

    Cualquier OTRA rotura de la lectura es un cuerpo vacio, no una
    excepcion: leer por trozos agrego un modo de falla que `request.json()`
    no tenia -el cliente que se corta a mitad del cuerpo levanta
    `ClientDisconnect`-, y dejarlo subir como excepcion ASGI le regalaba al
    martillador un intento que el freno no cuenta (el fallo lo cobra la ruta
    DESPUES de este helper)."""
    try:
        crudo = await _leer_cuerpo_acotado(request)
    except HTTPException:
        if request.url.path in _APARATOS_EXENTAS:
            _aparatos_fallo(request.client.host if request.client else "")
        raise
    except Exception:
        return {}
    try:
        datos = json.loads(crudo)
    except ValueError:
        return {}
    return datos if isinstance(datos, dict) else {}


def _id_pedido(cuerpo: dict) -> str:
    """El id de pedido viaja SIEMPRE por el body, nunca por el path: el
    access log ve el path. Lo que no sea texto es un id desconocido como
    cualquier otro, no un 500."""
    valor = cuerpo.get("id_pedido")
    return valor if isinstance(valor, str) else ""


def _solo_la_ally(host: str) -> None:
    """Invariante 4: la aprobacion se firma en la maquina, no por la red.
    Rechazar comparte el mensaje porque comparte la razon."""
    if not _es_loopback(host):
        raise HTTPException(status_code=403,
                            detail="aprobar es solo desde la Ally")


@app.post("/api/aparatos/golpear")
async def aparatos_golpear(request: Request):
    """El aparato se anuncia y queda esperando. El fallo se cuenta ANTES de
    mirar el pedido: golpe valido, tipo basura o cuerpo roto pesan igual,
    que es lo que hace que martillar esta ruta se frene solo."""
    host = request.client.host if request.client else ""
    cuerpo = await _cuerpo_json(request)
    _aparatos_fallo(host)
    try:
        return await asyncio.to_thread(sesiones.golpear,
                                       cuerpo.get("aparato"),
                                       cuerpo.get("tipo"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except sesiones.Lleno as exc:
        # el otro 429 de esta ruta (la sala de espera llena, no el freno) y
        # lleva Retry-After igual: el aparato legitimo que llego tarde tiene
        # que reintentar solo. 60s porque los golpes caducan a los 10 min,
        # asi que la sala se vacia sola y sondear cada minuto la alcanza.
        raise HTTPException(status_code=429, detail=str(exc),
                            headers={"Retry-After": "60"})


@app.post("/api/aparatos/estado")
async def aparatos_estado(request: Request):
    """El sondeo del aparato mientras espera a Pedro. `sesiones.estado` no
    toma el candado (lee por cache de stat), asi que no necesita hilo."""
    host = request.client.host if request.client else ""
    cuerpo = await _cuerpo_json(request)
    situacion = sesiones.estado(_id_pedido(cuerpo))
    if situacion is None:
        _aparatos_fallo(host)
        raise HTTPException(status_code=404, detail="pedido desconocido")
    return {"estado": situacion}


@app.post("/api/aparatos/canjear")
async def aparatos_canjear(request: Request):
    """El id de sesion nace aca y se entrega UNA sola vez, en la cookie
    (invariante 8). Un segundo canje encuentra el id_pedido quemado."""
    host = request.client.host if request.client else ""
    cuerpo = await _cuerpo_json(request)
    id_sesion = await asyncio.to_thread(sesiones.canjear, _id_pedido(cuerpo))
    if id_sesion is None:
        _aparatos_fallo(host)
        raise HTTPException(status_code=404, detail="pedido desconocido")
    # el tipo lo eligio Pedro al aprobar y el aparato necesita saber con que
    # alcance quedo; el canje devuelve el id pelado, asi que se relee. None
    # solo si alguien revoco entre estas dos lineas: la cookie sale igual y
    # el proximo request la encuentra muerta, que es lo correcto.
    registro = await asyncio.to_thread(sesiones.resolver, id_sesion)
    resp = JSONResponse({"ok": True,
                         "tipo": registro.get("tipo") if registro else None})
    resp.set_cookie(COOKIE_SESION, id_sesion, httponly=True, samesite="lax",
                    max_age=SESION_COOKIE_MAX_AGE)
    return resp


@app.post("/api/aparatos/aprobar")
async def aparatos_aprobar(request: Request):
    """Pedro dice que si y elige el tipo (el sugerido por el aparato ni se
    mira). El 404 no repite el id_pedido: es la credencial del canje."""
    _solo_la_ally(request.client.host if request.client else "")
    cuerpo = await _cuerpo_json(request)
    try:
        await asyncio.to_thread(sesiones.aprobar, _id_pedido(cuerpo),
                                cuerpo.get("tipo"))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except KeyError:
        raise HTTPException(status_code=404, detail="no hay un golpe vigente")
    return {"ok": True}


@app.post("/api/aparatos/rechazar")
async def aparatos_rechazar(request: Request):
    """Sin marcha atras: el aparato rechazado vuelve a golpear."""
    _solo_la_ally(request.client.host if request.client else "")
    cuerpo = await _cuerpo_json(request)
    try:
        await asyncio.to_thread(sesiones.rechazar, _id_pedido(cuerpo))
    except KeyError:
        raise HTTPException(status_code=404, detail="pedido desconocido")
    return {"ok": True}


@app.get("/api/aparatos")
def aparatos_listar(request: Request):
    """Lo que muestra /fabrica, con el estado EFECTIVO del reloj (una sesion
    dormida ya figura muerta sin esperar a que alguien la resuelva).
    `def` y no `async def` porque no hay nada que esperar: FastAPI corre el
    codigo sincrono en su threadpool.

    El `id_pedido` de los golpes que esperan sale solo hacia loopback: la
    Ally es la que aprueba y rechaza por body. Una sesion `navegador`
    remota ve la lista (D3: revocar desde otro aparato) pero no aprueba ni
    rechaza, asi que el id no le sirve para nada legitimo -- y si es la
    credencial de un canje, le sirve para robarse la sesion que Pedro
    aprobo para otro aparato."""
    filas = sesiones.listar()
    if not _es_loopback(request.client.host if request.client else ""):
        for fila in filas:
            fila["id_pedido"] = None
    return {"aparatos": filas}


@app.post("/api/aparatos/{hash_id}/revocar")
async def aparatos_revocar(hash_id: str, request: Request):
    """El hash SI viaja por el path: no es una credencial (el id en claro
    jamas toca el disco). Loopback o una sesion `navegador` -- el lector y
    el tablero no revocan. `request.state.sesion` lo va a poblar el guard de
    la capa siguiente; hasta entonces solo entra por loopback."""
    host = request.client.host if request.client else ""
    ses = getattr(request.state, "sesion", None)
    if not (_es_loopback(host) or (ses and ses.get("tipo") == "navegador")):
        raise HTTPException(
            status_code=403,
            detail="revocar es solo desde la Ally o un navegador")
    try:
        await asyncio.to_thread(sesiones.revocar, hash_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="no hay una sesion viva")
    # despues del almacen, no antes: si `revocar` falla, la sesion sigue viva
    # y sus sockets no tienen por que caerse
    _revocar_en_vivo(hash_id)
    return {"ok": True}


@app.get("/api/aduana")
def api_aduana(request: Request, desde: str | None = None, hasta: str | None = None,
               origen: str | None = None) -> dict:
    """Los cruces del libro (por defecto hoy) con totales, el hueco en
    memoria (`sin_libro`, sin tocar el disco) y las lineas rotas contadas,
    nunca escondidas (spec seccion 9). `def` y no `async def`: lee bajo el
    candado del libro, en el threadpool (invariante 8).

    Alcance por sesion (ruling 15.3, default seguro): loopback con el token
    y una sesion `navegador` ven todo; `tablero` -y cualquier tipo que no
    sea navegador- recibe los cruces SIN `carga`, SIN `quien.chat` y SIN
    `destino.url`: la carga de un /web es el mensaje crudo de Pedro, y el
    tablero por decision previa no ve chats. `lector` no llega: el guard lo
    rebota con 403 por ALCANCES."""
    respuesta = aduana.leer(desde=desde, hasta=hasta, origen=origen)
    ses = getattr(request.state, "sesion", None)
    if ses and ses.get("tipo") != "navegador":
        return aduana.recortar_para_tablero(respuesta)
    return respuesta


# Defensa en profundidad de _safe (revision de seguridad 2026-09-07, C2):
# aunque ROOT quedara siendo ancestro de estas carpetas (una raiz de catastro
# rara, un symlink), las credenciales de Pedro y el estado de Calipso no se
# sirven por /api/file. Espeja las carpetas de calipso/permisos/acciones.py.
_VEDADAS_RELATIVAS_AL_HOME = (
    (".ssh",), (".gnupg",), (".aws",), (".calipso",),
    (".config", "gh"), (".claude",),
)


def _safe(rel: str) -> pathlib.Path:
    """Resuelve 'rel' dentro de ROOT o lanza 400 si se sale (path-traversal).
    Y las carpetas vedadas del home no se sirven nunca, este donde este ROOT."""
    p = (ROOT / rel).resolve()
    if p != ROOT and ROOT not in p.parents:
        raise HTTPException(status_code=400, detail="ruta fuera del proyecto")
    home = pathlib.Path.home().resolve()
    vedadas = [home.joinpath(*partes) for partes in _VEDADAS_RELATIVAS_AL_HOME]
    # el estado real de Calipso, este donde este (CALIPSO_HOME puede apuntar
    # fuera de ~/.calipso)
    vedadas.append(_home_calipso().resolve())
    for v in vedadas:
        if p == v or v in p.parents:
            raise HTTPException(status_code=400, detail="ruta vedada")
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
def api_apply_proposal(change_id: str, request: Request, verify: bool = False,
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
            # la captura es loopback y no cruza; los deps.ensure de adentro si
            before_png, after_png = calipso_browser.before_after_capture(
                "http://localhost:8000", _write_file,
                quien=_quien_http(request, "gesto", "/api/proposals/{change_id}/apply"))
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
    """git blindado, el mismo escudo de catastro._git y tools/commands: un
    .git/config ajeno puede traer core.fsmonitor="comando; false" y ese
    comando corre en un `git status` comun (verificado con repo de prueba,
    ver catastro.py). ROOT es conmutable a cualquier repo del catastro via
    /api/project/open, asi que este helper corre git sobre repos que Pedro
    no escribio -- y la UI dispara /api/git/status sola al abrir. Revision
    de seguridad 2026-09-07, C1."""
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=", "-c", "diff.external=",
         "-c", "core.pager=cat", *args],
        cwd=str(ROOT), env=env, text=True, capture_output=True,
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
    # --no-ext-diff --no-textconv: un repo ajeno puede declarar drivers de
    # diff por archivo (.gitattributes + [diff "x"] command=...) que el
    # escudo de -c NO tapa y que ejecutan comandos en un `git diff` --
    # verificado empiricamente (revision de seguridad 2026-09-07).
    args = ["diff", "--no-ext-diff", "--no-textconv", "--"]
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

def _gh_runner(quien: aduana.Quien):
    return calipso_github.default_runner(cwd=str(ROOT), quien=quien)


@app.get("/api/github/overview")
def api_github_overview(request: Request) -> dict:
    if not calipso_github.available():
        return {"available": False, "reason": "gh no esta instalado",
                "user": None, "repo": None}
    quien = _quien_http(request, "ui", "/api/github/overview")
    gh = _gh_runner(quien)
    user = calipso_github.gh_user(gh)
    overview = calipso_github.repo_overview(
        gh, calipso_github.git_runner(cwd=str(ROOT), quien=quien))
    return {
        "available": True,
        "authenticated": user["authenticated"],
        "user": user,
        "repo": overview,
    }


@app.get("/api/github/repos")
def api_github_repos(request: Request, limit: int = 10) -> dict:
    if not calipso_github.available():
        raise HTTPException(status_code=404, detail="gh no esta instalado")
    repos = calipso_github.list_repos(
        _gh_runner(_quien_http(request, "ui", "/api/github/repos")),
        limit=max(1, min(limit, 50)))
    return {"repos": repos}


@app.get("/api/github/assigned")
def api_github_assigned(request: Request, limit: int = 10) -> dict:
    if not calipso_github.available():
        raise HTTPException(status_code=404, detail="gh no esta instalado")
    return calipso_github.assigned_items(
        _gh_runner(_quien_http(request, "ui", "/api/github/assigned")),
        limit=max(1, min(limit, 50)))


@app.post("/api/github/contribute/plan")
async def api_github_contribute_plan(request: Request) -> dict:
    """Planifica una accion de contribucion SIN ejecutarla."""
    data = await request.json()
    action = data.get("action", "")
    opts = data.get("opts") or {}
    return calipso_github.plan_contribution(action, opts)


def _correr_contribucion(run_cmd: list[str], action: str, opts: dict,
                         quien: aduana.Quien) -> subprocess.CompletedProcess:
    """Sincrona, en `to_thread`: el subprocess (hasta 120 s) y el flock del
    libro fuera del loop (invariante 8; hasta hoy corria inline en el
    `async def` y bloqueaba el loop). Por accion (spec seccion 7):
    `branch` es `git checkout -b`, local, no cruza; `pr` cruza con el
    cuerpo: `aduana.Cuerpo(titulo + '\\n' + body)` desde `opts`, y la aduana
    se queda con las TRES primeras lineas del cuerpo (spec seccion 5), o sea
    el titulo y las dos primeras del body (decision 15 del plan); nunca el
    argv que lo lleva entero. `clone`/`fork` cruzan con el argv como
    consulta."""
    if action == "branch":
        cruce = contextlib.nullcontext()
    elif action == "pr":
        cruce = aduana.cruzar(quien, "gh pr create", destino="api.github.com",
                              carga=aduana.Cuerpo(f"{opts.get('title', '')}\n"
                                                  f"{opts.get('body', '')}"))
    else:
        cruce = aduana.cruzar(quien, f"gh repo {action}",
                              destino="github.com" if action == "clone" else "api.github.com",
                              carga=["gh", *run_cmd[1:]])
    with cruce as c:
        # env blindado: este ejecutor corre git/gh sobre ROOT (conmutable a
        # un repo ajeno) y un `git checkout -b` dispara el core.fsmonitor
        # del repo -- verificado (revision de seguridad 2026-09-07, C1).
        proc = subprocess.run(
            run_cmd, cwd=str(ROOT), env=calipso_github.env_git_blindado(),
            text=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=120)
        if c is not None:
            c.entro(len(proc.stdout or "") + len(proc.stderr or ""))
    return proc


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
    quien = _quien_http(request, "gesto", "/api/github/contribute/run")
    try:
        proc = await asyncio.to_thread(_correr_contribucion, run_cmd, action, opts, quien)
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
    # un modelo fuera de la maquina se declara por cambio de config
    # (invariante 7); en hilo: el declarar toma el candado del libro
    await asyncio.to_thread(_declarar_modelos_fuera,
                            _quien_http(request, "gesto", "/api/config"))
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
    # El techo de verdad (revision de seguridad 2026-09-07, C2): con la raiz
    # por defecto del catastro (el home entero), este era el agujero -- abrir
    # "~" o "~/.calipso" como proyecto dejaba /api/file leer la llave SSH o
    # el token y escribir ~/.ssh/authorized_keys. Ni el home, ni el estado de
    # Calipso, ni las carpetas ocultas del home son proyectos.
    home = pathlib.Path.home().resolve()
    ch = _home_calipso().resolve()
    if p == home:
        raise HTTPException(status_code=400,
                            detail="el home entero no se abre como proyecto")
    if p == ch or ch in p.parents:
        raise HTTPException(status_code=400,
                            detail="el estado de Calipso no es un proyecto")
    try:
        rel = p.relative_to(home)
        if rel.parts and rel.parts[0].startswith("."):
            raise HTTPException(
                status_code=400,
                detail="las carpetas ocultas del home no se abren como proyecto")
    except ValueError:
        pass  # fuera del home: lo decide el techo del catastro
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
def api_connectors(request: Request) -> dict:
    """`ui`: lo dispara index.html:1531 al cargar."""
    quien = _quien_http(request, "ui", "/api/connectors")
    return {
        "cli": {
            name: {
                "docs": connector["docs"],
                "state": _cli_probe(name, quien),
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

_LOOPBACK_HOSTS = ("127.0.0.1", "::1", "localhost")


def _declarar_modelos_fuera(quien: aduana.Quien) -> int:
    """Un `declarar` por boca (local/api/classifier) cuyo `base_url` no sea
    loopback (invariante 7: la aduana no conoce a los modelos; un modelo
    fuera de la maquina se declara al cargar la config y al cambiarla, no
    se cruza por turno). Devuelve cuantos declaro. El dia uno: cero.
    Sincrona y con candado: al arrancar corre sin loop; desde PUT
    /api/config va en `to_thread`."""
    n = 0
    for boca in ("local", "api", "classifier"):
        url = (dispatch.CONFIG.get(boca) or {}).get("base_url") or ""
        if not url:
            continue
        try:
            host = urllib.parse.urlsplit(url).hostname or ""
            motivo = boca
        except ValueError:
            # `http://[::1:11434/x` ('Invalid IPv6 URL'): fail-open. Un
            # host que no se puede leer no es loopback demostrado: se
            # declara como fuera, con destino=url (la aduana lo sanea) y el
            # motivo lo dice. Sin esto el arranque perdia en silencio la
            # memoria, los probes y `_backend_availability`, y PUT
            # /api/config daba 500 DESPUES de guardar la config.
            host, motivo = "?", f"{boca}: base_url no parseable"
        if host and host not in _LOOPBACK_HOSTS:
            aduana.declarar(quien, "modelo fuera de la maquina", destino=url, motivo=motivo)
            n += 1
    return n


def _declarar_arranque() -> None:
    """Lo que sale al arrancar el proceso, declarado UNA vez (spec seccion
    7). La memoria sale a huggingface.co al construirse (`SentenceTransformer`
    sin `local_files_only`: metadatos + un HEAD por archivo aunque el cache
    este completo): se declara ACA y no en `Memory.__init__`, porque
    `_switch_project` reconstruye la memoria en el loop y chromadb cachea
    el modelo por clase (no vuelve a salir). NO se llama a nivel de modulo:
    con `uvicorn calipso.server:app` (asi arranca el shell de escritorio,
    ver `_instalar_filtro_de_token`, y asi levanta el smoke) el import del
    modulo corre ADENTRO del loop (uvicorn 0.49: `Server._serve` ->
    `config.load()`), la aduana detectaria el loop y NO escribiria
    (`aduana_en_loop`), y la memoria quedaria sin declarar. Se llama desde
    `_calentar_probes`, en `to_thread` desde `_startup_warm`, donde el
    candado se puede tomar. Con `python calipso/server.py` daria igual."""
    quien = aduana.Quien(origen="arranque", proyecto=_proyecto(),
                         desde={"credencial": "maquina"})
    aduana.declarar_una_vez("memoria", quien, "modelo de embeddings",
                            destino="huggingface.co", motivo=EMBED_MODEL)
    _declarar_modelos_fuera(quien)


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

# La identidad corta: lo que CALIPSO.md dice de QUIEN es Calipso, escrito
# para el modelo y no para un humano. Reemplaza al par SYSTEM + seccion
# "Constitucion de Calipso" (CALIPSO.md cortado a 3000 chars) que entraba en
# cada turno local: la medicion del 2026-09-10 (h05, opcion a de Pedro) mostro
# que ese documento, mas las doce instrucciones del contrato interno,
# competian con el contrato del abismo hasta borrarle la mejora entera (0
# marcas utiles en memoria con el system real; 30/36 con este). CALIPSO.md
# sigue siendo el documento de identidad del repo; al 7b no le llega.
# LETRA MEDIDA: no cambiarla sin re-correr experimentos/consulta_abismo_system.py
# (test_abismo_system_medido.py la ata byte a byte a variantes/system-podada.txt).
SYSTEM = (
    "Eres Calipso, el asistente personal local de Pedro. Pedro habla siempre "
    "con Calipso: Claude, Codex, las APIs y los modelos locales son "
    "herramientas internas tuyas, nunca tu identidad. No digas que eres "
    "Alibaba, OpenAI, Anthropic, Claude, Codex ni Ollama. Si Pedro pregunta "
    "que modelo o ruta usas, responde solo con el estado real que recibes en "
    "el contexto. Eres honesto sobre tu estado: si no sabes algo, una "
    "conexion no esta configurada o un dato te falta, lo dices sin inventar. "
    "Prefieres entregar menos, pero real, antes que un relleno bonito."
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
    # cwd=ROOT es conmutable a un repo ajeno: escudo git tambien aca
    # (revision de seguridad 2026-09-07, ronda del punto 2)
    env_probe = calipso_github.env_git_blindado(anular_global=False)
    try:
        result = subprocess.run(
            [exe, "--version"], cwd=str(ROOT), text=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=5, env=env_probe)
        executable = result.returncode == 0
        authenticated = None
        if client == "claude" and executable:
            auth = subprocess.run(
                [exe, "auth", "status"], cwd=str(ROOT), text=True,
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=5, env=env_probe)
            try:
                authenticated = json.loads(auth.stdout).get("loggedIn", False)
            except Exception:
                authenticated = auth.returncode == 0
        elif client == "codex" and executable:
            auth = subprocess.run(
                [exe, "login", "status"], cwd=str(ROOT), text=True,
                capture_output=True, encoding="utf-8", errors="replace",
                timeout=5, env=env_probe)
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


def _cli_probe(name: str, quien: aduana.Quien) -> dict:
    c = CLI_CONNECTORS.get(name)
    if not c:
        return {"installed": False, "ready": False, "error": "conector desconocido"}
    exe = _cmd_exe(c["exe"])
    if not exe:
        return {"installed": False, "ready": False, "error": "no esta en PATH"}
    # `gh auth status` sale a api.github.com; `--version` no. Se declara UNA
    # vez por proceso (spec seccion 7), sin bytes: el probe no es un cruce
    aduana.declarar_una_vez(
        f"cli_probe:{name}", quien, f"probe {c['exe']}: --version y auth status",
        destino="api.github.com" if name == "github" else None)
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
    # la salud REAL de Ollama, no una constante: el chat ya puede ejecutar
    # local (ver la ruta local de `_chunks_for`), asi que apagarlo a mano
    # dejaba muerta la unica boca que mantiene lo privado en la maquina.
    # Se prueba /api/tags y NO base_url: base_url es /api/generate, que solo
    # acepta POST -- un GET da 405 y diria "caido" con Ollama vivo.
    _salud_ollama = dispatch.CONFIG["local"]["base_url"].replace(
        "/api/generate", "/api/tags")
    local_up = (_http_up_cached if use_cache else _http_up)(_salud_ollama)
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
    # No escalar a API paga en silencio: un veredicto de API solo vale si
    # Pedro lo forzo. El freno viejo (`api_only_when_forced`) solo vivia en
    # el CLI muerto `dispatch.py` y nunca corria en el chat, asi que si las
    # suscripciones caian y el proxy pago estaba arriba, la API ganaba sola.
    if d.get("force_route") != "api":
        ranked = [r for r in ranked if r["route"] != "api"]
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
    if features.get("private"):
        # un prompt privado tiene un solo camino -- local o fallo cerrado --
        # y la orquestacion lo repartiria a backends que no son private_ok.
        # Va ANTES que `force_team`: un `/team` explicito sobre un prompt
        # privado tambien tiene que respetar la privacidad. El filtro no
        # puede tener una puerta de atras.
        return False
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
                            departamento: str | None = None,
                            allow_paid: bool = False) -> tuple[str, dict, str | None]:
    # allow_paid simetrico al filtro de _decide (Task 3): sin gesto explicito
    # de Pedro (force_route=="api"), el equipo dinamico no cae en API paga.
    plan_obj = await asyncio.to_thread(_plan_dynamic_team, chat_msg, features)
    team = orchestrator.build_team(
        plan_obj, _backend_availability(), project_root=str(ROOT),
        session=sessions.active(), allow_paid=allow_paid)
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
            session=sessions.active(), allow_paid=allow_paid)
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
                # "/stop" (el CLI de un agente interrumpido) no es un mensaje
                # para despues: no pisa lo que Pedro escriba durante otro agente
                queued_msg = queued_msg or (queued if queued != "/stop" else None)
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
            # La del abismo se retira ANTES y con aviso (spec seccion 4: la
            # ruta orquestador queda fuera, "se ignoran con aviso"); despues
            # `_limpiar_marcas` saca las de foco y cualquier empalme.
            mango.razonando(_limpiar_marcas(_retirar_con_aviso(output, "agente")))
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
            # "/stop" (el CLI de un agente interrumpido) no es un mensaje
            # para despues: no pisa lo que Pedro escriba durante otro agente
            queued_msg = queued_msg or (queued if queued != "/stop" else None)
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
    # la salud REAL de Ollama, no una constante: el chat ya puede ejecutar
    # local (ver la ruta local de `_chunks_for`), asi que apagarlo a mano
    # dejaba muerta la unica boca que mantiene lo privado en la maquina.
    # Se prueba /api/tags y NO base_url: base_url es /api/generate, que solo
    # acepta POST -- un GET da 405 y diria "caido" con Ollama vivo.
    # Esta funcion no tiene `use_cache` (a diferencia de _connector_health):
    # sigue el mismo patron que `api_up` arriba y usa siempre el cache.
    _salud_ollama = dispatch.CONFIG["local"]["base_url"].replace(
        "/api/generate", "/api/tags")
    local_up = _http_up_cached(_salud_ollama)
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
CONTEXT_CORE_MAX = int(os.environ.get("CALIPSO_CORE_MAX", "3000"))
RECALL_MIN_SCORE = float(os.environ.get("CALIPSO_RECALL_MIN", "0.30"))
RECALL_MAX = int(os.environ.get("CALIPSO_RECALL_MAX", "4"))
REPO_BRIEF_MAX = int(os.environ.get("CALIPSO_REPO_BRIEF_MAX", "4500"))


# `_identity_doc` (CALIPSO.md cortado a 3000 chars como seccion
# "Constitucion de Calipso") murio el 2026-09-10: ver el comentario de SYSTEM.


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


_SISTEMA_NUBE_MINIMO = (
    "Sos Calipso, el asistente de Pedro. Responde el mensaje del usuario de "
    "forma util y concisa. El mensaje puede contener marcadores como [ID_1], "
    "[SALUD_1], [CONTACTO_1], [LUGAR_1]: son datos personales tapados por "
    "privacidad. Tratalos como referencias opacas, no intentes adivinar su "
    "valor real, y usalos tal cual en tu respuesta cuando necesites referirte "
    "a ellos."
)


# la linea que acompana al contrato en /nube: lo que suba del abismo ya paso
# por el viaje y puede traer los mismos marcadores que el mensaje.
_NUBE_ABISMO_MARCADORES = (
    "Lo que suba del abismo (el bloque \"Lo que subio del abismo\") puede "
    "traer marcadores [TIPO_N] como el mensaje: son datos tapados por "
    "privacidad, usalos tal cual y no intentes adivinarlos."
)


def _sistema_nube() -> str:
    """El system de un turno /nube tapado: el minimo de siempre + el contrato
    del abismo en su variante SIN nombres de repos (spec seccion 8.1: cero
    datos derivados de Pedro; el modelo pide por nombre y el nombre lo trae
    el mensaje, si lo trae) + la linea de los marcadores. En produccion el
    contrato va segundo, detras del minimo, no tercero de ocho secciones
    como en local; no se re-mide (los modelos de nube son mas capaces que
    el 7b con el que se calibro la letra)."""
    return "\n\n".join([_SISTEMA_NUBE_MINIMO,
                        abismo_contrato.bloque_contrato(()),
                        _NUBE_ABISMO_MARCADORES])


def _sistema_del_turno(chat_msg: str, runtime: str, features: dict,
                       a_la_nube_tapado: bool) -> list[tuple[str, str]]:
    """Las SECCIONES del system del turno (titulo, cuerpo); el string plano
    lo arma `prompt_compiler.render_context` recien al armar el payload
    (spec canarios 2.3: la estructura se conserva para poder recortar y
    para que el canario sepa que seccion es que). Si el turno va a la nube
    tapado (/nube), NO se arma el contexto completo (recuerdos, economia,
    catastro) porque llevaria datos sensibles sin tapar a la nube: se usa
    el system minimo de nube, que desde el abismo lleva el contrato sin
    nombres (`_sistema_nube`), como UNA seccion cruda (titulo vacio: se
    rinde tal cual, byte a byte lo de antes). Si no, el contexto de
    siempre."""
    if a_la_nube_tapado:
        return [("", _sistema_nube())]
    return _build_context(chat_msg, runtime, features)


def _secciones_del_turno(secciones_base: list[tuple[str, str]], *,
                         vision_text: str = "", aviso_imagen: bool = False,
                         attachment_context: str = "", bloque_dep: str = "",
                         web_material: dict | None = None,
                         a_la_nube_tapado: bool = False) -> list[tuple[str, str]]:
    """Las secciones de `_sistema_del_turno` mas las que el server suma:
    vision, el aviso de imagen sin vision (cruda: no tenia titulo), los
    adjuntos, el departamento en foco y los resultados web. Los tres
    ultimos ya traen su `=== X ===` adentro y `seccion_de_bloque` lo
    vuelve titulo, asi `render_context` da byte a byte el system de antes
    (test_turno_secciones.py lo fija). En /nube-a-la-nube adjuntos y
    departamento no van: son crudos (no pasan por la compuerta de
    redaccion) y podrian llevar datos sensibles; `web_material` ya queda
    en None en /nube (canal de web salteado antes)."""
    secciones = list(secciones_base)
    if vision_text:
        secciones.append(("Vision de imagen adjunta", vision_text))
    elif aviso_imagen:
        secciones.append(("", "[Imagen adjunta registrada. Para análisis visual automático: "
                              "instala 'ollama pull moondream' o configura ANTHROPIC_API_KEY.]"))
    if attachment_context and not a_la_nube_tapado:
        secciones.append(prompt_compiler.seccion_de_bloque(attachment_context))
    if bloque_dep and not a_la_nube_tapado:
        secciones.append(prompt_compiler.seccion_de_bloque(bloque_dep))
    if web_material and (web_material["results"] or web_material["pages"]):
        secciones.append(prompt_compiler.seccion_de_bloque(calipso_web.context_block(web_material)))
    return secciones


def _build_context(user_msg: str, runtime: str, features: dict | None = None,
                   ) -> list[tuple[str, str]]:
    """Contexto ordenado para caché (estable -> volátil) y presupuestado,
    como lista de SECCIONES (titulo, cuerpo) de `context_sections`; el
    string es `prompt_compiler.render_context(...)` (spec canarios 2.3).

    Estable (prefijo, se cachea en sub/api): identidad + memoria núcleo.
    Volátil (sufijo): recuerdos relevantes (podados por score) + estado real.
    Just-in-time: los archivos del repo NO se precargan; se piden bajo demanda.

    Arma el brief de economia, que toma el candado del libro (flock
    exclusivo y bloqueante): se llama SIEMPRE desde un hilo, igual que
    `_ficha_y_cuenta` y `_cobrar_turno`.
    """
    # --- prefijo estable (cacheable) ---
    core = mem.load_core()

    # --- sufijo volátil ---
    # con procedencia (spec 2026-09-11): se pide n=8, se PRESENTA cada hit
    # (quien dijo que, cuando, por que ruta; el no-saber degradado; el
    # gesto sin texto saltado) y recien ahi se corta a RECALL_MAX, para que
    # un salto no achique el bloque. `text` de cada item ya es la vineta.
    recalled = memoria_procedencia.presentar_recuerdos(
        [r for r in mem.recall(user_msg, n=8) if r["score"] >= RECALL_MIN_SCORE],
        RECALL_MAX)
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
    return prompt_compiler.context_sections(
        SYSTEM, core=core, recalled=recalled,
        repo_brief=repo_brief, goal_block=goal_block, runtime=runtime,
        economia=economia, proyectos=proyectos, features=features,
        core_limit=CONTEXT_CORE_MAX, base=_ECO_BASE)


def _HISTORY_TURNS_CONST():
    return 12


_HISTORY_TURNS = 12  # max mensajes del historial (6 intercambios)

# `num_ctx` explicito en la llamada local del chat (spec del abismo,
# seccion 4, presupuesto de contexto). El mismo valor que `_pensar_local`
# y por la misma razon: sin el, con el default (2048 en la mayoria de los
# builds) una reentrada con hasta tres bloques del abismo mas el parcial
# dejaria de ver justo el system con el contrato, en silencio. Como corta
# Ollama, medido por endpoint (spec canarios 2026-09-11, seccion 1): en
# /api/generate (`_pensar_local`) trunca el prompt plano desde el COMIENZO;
# en /api/chat (este chat) descarta primero los mensajes MAS VIEJOS que no
# son system y conserva el system y el ultimo mensaje, y recien corta por
# tokens desde el principio cuando esos dos solos no caben: el peligro real
# es un system gordo (adjuntos, brief, bloques), no el historial. Desde los
# canarios el presupuesto se mide ANTES de cada pasada con el tokenizador
# real y lo volatil se recorta a la vista (`canarios.recortar`); este es el
# techo. 8192 es holgura, no capacidad: cada token de contexto cuesta RAM
# en la Ally.
CHAT_NUM_CTX = 8192


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
                chat_id: str | None = None, history: list[dict] | None = None):
    """Devuelve (generador, modelo, messages) segun la ruta con historial de
    conversacion. `history` prearmado (la ventana lo recorta por pasada,
    spec canarios 2.3); sin el, se lee del chat como siempre. `messages` es
    exactamente lo que viajo (system + historial + user), para que el
    canario compare contra eso y no contra una reconstruccion; con Ollama
    caido es lo que HABRIA viajado."""
    if history is None:
        history = _history_messages(chat_id)
    messages = [{"role": "system", "content": system}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_msg})

    if route == "api":
        cfg = dispatch.CONFIG["api"]
        mdl = model or cfg["model"]
        payload = {"model": mdl, "stream": True,
                   "stream_options": {"include_usage": True}, "messages": messages}
        if effort is not None:
            payload["output_config"] = {"effort": capabilities.EFFORT_PARAM[effort]}
        headers = {"Authorization": f"Bearer {cfg['api_key']}"}
        return dispatch._sse_text_chunks(cfg["base_url"], payload, headers, usage), mdl, messages

    # LA RUTA LOCAL ES LOCAL: transmite desde el Ollama que ya corre, con el
    # mismo `messages` que la rama api de arriba. El bug viejo corria
    # `claude -p` -- mandaba el dato privado a Anthropic bajo la etiqueta
    # 'local', tiraba el system y no pasaba el modelo. Ver la fuga central en
    # el spec del 2026-09-02.
    cfg = dispatch.CONFIG["local"]
    mdl = model or cfg["model"]
    # OJO: `base_url` es http://localhost:11434/api/generate, que SOLO acepta
    # POST -- un GET (que es lo que hace `_http_up`) da 405 y diria "caido"
    # aunque Ollama este vivo. Se prueba /api/tags, que si responde a GET.
    salud_ollama = cfg["base_url"].replace("/api/generate", "/api/tags")
    if not _http_up(salud_ollama):
        # FALLO CERRADO: lo unico que llega aca con Ollama caido es el
        # fallback de ranking vacio (todo lo demas tambien esta caido), asi
        # que degradar a claude no protege a nadie y rompe la promesa de que
        # lo privado no sale de la maquina. Se para y se dice.
        def _local_caido():
            yield ("[Calipso] no puedo contestar esto con el modelo local: "
                   "Ollama no esta disponible. No lo mando a la nube.")
        return _local_caido(), mdl, messages
    payload = {"model": mdl, "messages": messages, "stream": True,
               "options": {"num_ctx": CHAT_NUM_CTX}}
    return dispatch._ollama_chat_chunks(cfg["base_url"], payload, usage), mdl, messages


def _ventana_antes(secciones: list[tuple[str, str]], historial: list[dict],
                   mensaje: str, route: str, model: str | None, pasada: int,
                   ) -> tuple[list[tuple[str, str]], list[dict], dict]:
    """La ventana ANTES de una pasada (spec canarios 2.3), en hilo: el
    presupuesto con el tokenizador real del modelo local (o el fallback) y,
    SOLO donde el techo es real y lo impone Calipso (ruta local,
    CHAT_NUM_CTX), el recorte de lo volatil. En api y suscripcion solo se
    estima (num_ctx None: no hay techo configurado, y `truncado` queda
    None: no se juzga, decision 7). Devuelve (secciones, historial, fila)
    con la fila de la ventana a medio llenar."""
    contar, origen = tokenizador.contador(model or dispatch.CONFIG["local"]["model"])
    num_ctx = CHAT_NUM_CTX if route == "local" else None
    secciones, historial, info = canarios.recortar(secciones, historial, mensaje, num_ctx, contar)
    fila = {"pasada": pasada, "ruta": route, "estimado": info["estimado_final"],
            "estimado_sin_recorte": info["estimado"], "num_ctx": num_ctx,
            "cabe": info["cabe"], "recorte": info["recorte"], "no_cabe": info["no_cabe"],
            "tokenizador": origen, "evaluado": None, "truncado": None, "done_reason": None}
    return secciones, historial, fila


def _ventana_despues(fila: dict, usage_pasada: dict) -> dict:
    """La ventana DESPUES de la pasada: `evaluado` es prompt_eval_count de
    ESA pasada (None si se corto antes del done: usage_pasada queda vacio),
    y el truncado se decide con `canarios.truncado`."""
    fila["evaluado"] = usage_pasada.get("prompt_tokens")
    fila["done_reason"] = usage_pasada.get("done_reason")
    fila["truncado"] = canarios.truncado(fila["estimado"], fila["evaluado"], fila["num_ctx"])
    return fila


def _contexto_persistido(secciones, mensajes, bloques) -> dict:
    """SOLO con CANARIOS_PERSISTIR_CONTEXTO=1 (el server desechable del
    porton y del smoke): la fila `chat_turn` lleva el system, el historial
    y los bloques que viajaron, para el banco de anclaje y para `sin_dato
    falso`. En produccion la variable no esta y la fila no lleva nada de
    esto (invariante 7: lo que el canario extrae no sale de telemetry.jsonl
    y chats.json; y esto ni siquiera entra ahi)."""
    if os.environ.get("CANARIOS_PERSISTIR_CONTEXTO") != "1":
        return {}
    return {"contexto": {"secciones": [list(s) for s in secciones],
                         "historial": [m for m in (mensajes or [])[1:-1]],
                         "bloques": list(bloques)}}


async def _veredicto_del_turno(**campos) -> dict:
    """`canarios.veredicto` en hilo (invariante 4) con tope de tiempo y
    fail-open (invariante 3): si levanta o se pasa de `TOPE_SEGUNDOS`, el
    turno se entrega igual y el fallo va a la fila `chat_turn`."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(canarios.veredicto, **campos),
                                      timeout=canarios.TOPE_SEGUNDOS)
    except Exception as e:      # TimeoutError incluido
        print(f"[calipso] el canario fallo: {type(e).__name__}: {e}", file=sys.stderr)
        return {"error": type(e).__name__, "detalle": str(e)[:200], "anclaje": None,
                "degeneracion": [], "ventana": list(campos.get("ventana") or [])}


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
    # Entorno saneado y blindado (revision de seguridad 2026-09-07, punto 2):
    # el CLI corre con cwd=ROOT (un repo conmutable) y ejecuta git por dentro
    # -- el escudo por env (GIT_CONFIG_COUNT) anula el core.fsmonitor del
    # repo, misma clase que C1. Y las credenciales que el CLI no necesita no
    # viajan: CALIPSO_TOKEN es del servidor, LITELLM_MASTER_KEY de la ruta
    # api, y las claves Anthropic no le sirven a ninguno de los dos clientes
    # de suscripcion (el patron de saneo ya existia en memory.reflect).
    # anular_global=False: el CLI agente commitea legitimamente y su
    # identidad (user.name/email) vive SOLO en el ~/.gitconfig de Pedro.
    env = calipso_github.env_git_blindado(anular_global=False)
    env.pop("CALIPSO_TOKEN", None)
    env.pop("LITELLM_MASTER_KEY", None)
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
        chat_id: str | None = None,
        congelar=None) -> tuple[str, str | None]:
    """`congelar(parcial) -> str | None`: cuando devuelve un texto, el preview
    `process/running` se congela ahi (spec seccion 4: Pedro no lee texto que
    despues se descarta). El proceso corre a termino igual; matarlo por una
    marca dejaria un job en estado raro y perderia la parte util."""
    cmd, env, temp_name, output_name = _subscription_invocation(
        client, system, user_msg, model, chat_id=chat_id)
    started = time.perf_counter()
    last_notice = started
    pending_msg: str | None = None
    preview_congelado: str | None = None
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
                if congelar is not None and preview_congelado is None and partial:
                    preview_congelado = congelar(partial)
                muestra = partial if preview_congelado is None else preview_congelado
                # una marca a medio llegar al final del parcial se recorta
                # (Pedro no la lee cruda entre dos tics); las cerradas las
                # saca _limpiar_marcas
                muestra = abismo_turno.recortar_abierta(muestra)
                await ws.send_json({
                    "type": "process", "action": "running",
                    "job_id": job["id"],
                    "label": label, "client": client, "model": model,
                    "elapsed": round(now - started),
                    "tokens": max(1, ((len(system) + len(user_msg)) + len(partial)) // 4),
                    "partial": _limpiar_marcas(muestra)[-3000:] if muestra else "",
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
                        jobs.write_artifact(str(ROOT), job["id"], "partial-output.txt",
                                            _limpiar_marcas(partial))
                    # stderr tambien limpio: es un artefacto de jobs como los
                    # otros dos, y un CLI que eco-ee su entrada dejaria la
                    # marca en disco (la marca jamas se persiste, spec 4)
                    if stderr:
                        jobs.write_artifact(str(ROOT), job["id"], "stderr.txt", _limpiar_marcas(stderr))
                    # el segundo valor es "/stop": un /stop durante el CLI es
                    # el gesto mas fuerte de Pedro y el bucle one-shot del
                    # abismo lo tiene que ver como steer (sin pesca, sin
                    # reinvocacion). Para los demas llamadores es un no-op:
                    # queda en `pending` y el tope del turno lo saltea
                    if partial:
                        return partial + "\n\n...(proceso interrumpido)", "/stop"
                    if stderr:
                        return stderr + "\n\n...(proceso interrumpido)", "/stop"
                    return "...(proceso interrumpido sin salida parcial)", "/stop"
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
            # limpio de marcas: este `msg` va a jobs.update(error=), al
            # jobs.event(error=) y, via el RuntimeError, a fallbacks[].error
            # del chat_turn de telemetry -- tres sumideros que la seccion 4
            # del spec le prohibe a la marca
            msg = _limpiar_marcas(stderr or partial or "").strip()
            jobs.update(str(ROOT), job["id"], status="failed", error=msg)
            jobs.event(str(ROOT), job["id"], "failed", error=msg[:1000])
            # el job fallido se anuncia por el WS como los demas estados
            # (start/running/done/stopped): la UI no tenia ni ese indicio
            await ws.send_json({"type": "process", "action": "failed",
                                "job_id": job["id"], "label": label,
                                "client": client, "model": model,
                                "error": msg[:300]})
            if active_goal:
                goals.add_evidence(
                    str(ROOT), active_goal["id"], "job",
                    f"Proceso fallo: {label}", job_id=job["id"], status="failed")
            if partial:
                jobs.write_artifact(str(ROOT), job["id"], "partial-output.txt",
                                    _limpiar_marcas(partial))
            if stderr:
                jobs.write_artifact(str(ROOT), job["id"], "stderr.txt", _limpiar_marcas(stderr))
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
            jobs.write_artifact(str(ROOT), job["id"], "output.txt", _limpiar_marcas(text))
        if stderr:
            jobs.write_artifact(str(ROOT), job["id"], "stderr.txt", _limpiar_marcas(stderr))
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


# /redacta guarda el ultimo pedido por chat, a nivel de modulo (no de la
# conexion de websocket): asi /otra puede pedir "otra version" aunque el
# gesto llegue en una vuelta distinta del loop. Mismo patron que
# `conversacion._por_chat`.
_ultimo_pedido: dict[str, str] = {}

# cada cuanto despierta un chat ocioso a mirar si su sesion sigue viva. Alto a
# proposito: es el peor caso de un socket que ya no deberia existir, no una
# latencia que Pedro sienta.
LATIDO_CHAT_S = 30.0


async def _proximo_del_chat(ws: WebSocket | _SocketVigilado,
                            inbox: asyncio.Queue) -> str | None:
    """Lo proximo que mande el cliente, o None cuando el socket se termino.

    Espera con plazo en vez de quedarse colgada del `get`: el chat ocioso es
    justo el que no se enteraria nunca de que su sesion fue revocada. El
    latido no manda nada al cliente -- es un despertar del servidor, y la PWA
    no tiene por que aprender un tipo de evento nuevo para esto."""
    while True:
        try:
            return await asyncio.wait_for(inbox.get(), timeout=LATIDO_CHAT_S)
        except asyncio.TimeoutError:
            if await _cortar_si_revocada(ws):
                return None


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket) -> None:
    # de quien es este socket: con eso se envuelve para el corte en vivo
    sesion = await _ws_autorizado(ws)
    if not sesion:
        await ws.close(code=1008)   # politica violada: sin credencial
        return
    # antes del accept y de cualquier emision: de aca en adelante `ws` es el
    # vigilado, asi que los 46 puntos de emision de este handler y todo lo
    # que reciba el socket quedan cubiertos sin tocarlos
    ws = await _vigilar_socket(ws, sesion)
    if ws is None:
        return                      # sin hash no se vigila: ya cerro 1008
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
    # el estado del turno del abismo (spec seccion 4): vive junto al resto
    # del estado de la CONEXION porque atraviesa las reentradas sinteticas
    # de un turno, y lo resetea SOLO un mensaje real de Pedro (mas abajo,
    # donde paquete y steer ya convergieron en `user_msg`: invariante 8).
    estado_abismo = abismo_turno.EstadoTurno()
    try:
        while True:
            chat_id = chats.active_id()
            attachment_ids: list[str] = []
            if pending is not None:
                user_msg, pending = pending, None
            else:
                raw = await _proximo_del_chat(ws, inbox)
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
            estado_abismo.reset()      # un mensaje real de Pedro, paquete o steer
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

            # /mia: Pedro trae de vuelta su version FINAL editada de un
            # borrador. Calipso la GUARDA como ejemplo fuerte de su voz y no
            # hace nada mas: no responde, no rutea, no cobra, no toca historial
            # ni memoria. Asi el compositor aprende su voz real de lo que el
            # corrige (ver calipso/compositor/ejemplos.py y voz.ejemplos_de_voz).
            if directives.get("mia"):
                texto_mia = compositor_ejemplos.texto_del_gesto(chat_msg)
                if not texto_mia:
                    await ws.send_json({"type": "error",
                                        "text": "pega tu version despues de /mia"})
                    await ws.send_json({"type": "done"})
                    continue
                compositor_ejemplos.guardar(texto_mia)
                await ws.send_json({"type": "chunk",
                                    "text": "guardado como ejemplo de tu voz"})
                await ws.send_json({"type": "done"})
                continue

            # /redacta y /otra: Calipso REDACTA, no responde -- el turno no
            # es una respuesta de la conversacion, es un borrador aparte que
            # Pedro copia. Se desvia ANTES del ruteo normal, y corre SIEMPRE
            # en local (MVP Fase 1: el borrador nunca sale a la nube).
            if directives.get("redacta") or directives.get("otra"):
                if directives.get("redacta"):
                    # quirk de `parse_directives`: si el mensaje es SOLO el
                    # slash, `clean` cae al fallback y queda "/redacta" (no
                    # ""). Sin pedido de verdad no hay nada que guardar ni
                    # que redactar.
                    crudo = chat_msg.strip()
                    pedido = crudo if crudo and crudo.lower() != "/redacta" else ""
                    if pedido:
                        _ultimo_pedido[chat_id] = pedido
                else:
                    pedido = _ultimo_pedido.get(chat_id) or ""
                if not pedido:
                    aviso = ("pega el hilo o deci que queres decir"
                              if directives.get("redacta") else
                              "deci /redacta primero")
                    await ws.send_json({"type": "error", "text": aviso})
                    await ws.send_json({"type": "done"})
                    continue
                system_b, user_b = compositor_redactor.preparar_borrador(
                    pedido, chats._load(), compositor_ejemplos.cargar())
                await ws.send_json({"type": "borrador", "action": "inicio"})
                usage_b: dict = {}
                emisor_b = Emisor(ws)
                # `chat_id=None`: el borrador no arrastra el historial de la
                # conversacion (es un texto aparte, no una respuesta en ella)
                # -- mismo motivo por el que, mas abajo, no se guarda con
                # `chats.append` como turno de "assistant".
                # el borrador es local-only (Fase 1): si Ollama tose a mitad
                # de camino, se avisa con "error" y se corta el turno -- NO
                # se degrada a la nube (ver comentario de la compuerta de
                # privacidad mas abajo).
                try:
                    gen_b, model_b, _ = _chunks_for(
                        "local", system_b, user_b, usage_b,
                        _route_model_name("local"), chat_id=None)
                    while True:
                        if not inbox.empty():  # steering: barge-in del borrador
                            steer = inbox.get_nowait()
                            try:
                                gen_b.close()
                            except Exception:
                                pass
                            await ws.send_json({"type": "steered"})
                            if steer and steer.strip() and steer.strip() != "/stop":
                                pending = steer
                            break
                        chunk_b = await asyncio.to_thread(_next_or_stop, gen_b, sentinel)
                        if chunk_b is sentinel:
                            break
                        await emisor_b.chunk(chunk_b)
                except Exception as e:
                    await ws.send_json({"type": "error",
                                        "text": f"no pude armar el borrador: {e}"})
                    await ws.send_json({"type": "done"})
                    continue
                await emisor_b.cerrar()
                # cost/done como un turno local normal -- pero SIN cobrarle
                # nada a ningun departamento: local ya es gratis (Fase 1;
                # ver `_cobrar_turno`), asi que no hace falta tocar el libro
                # de la economia para este borrador.
                entry_b = costs.log_usage(
                    "local", model_b, usage_b.get("prompt_tokens", 0),
                    usage_b.get("completion_tokens", 0))
                await ws.send_json({
                    "type": "cost", "model": model_b, "route": "local",
                    "tokens": entry_b["prompt_tokens"] + entry_b["completion_tokens"],
                    "cost_usd": entry_b["cost_usd"]})
                await ws.send_json({"type": "done"})
                continue

            # quien paga y que sabe Calipso del departamento son dos
            # preguntas distintas con dos fuentes distintas: ver
            # `_ficha_y_cuenta`. Va en un hilo porque derivar la ficha toma el
            # candado del libro.
            bloque_dep, cuenta = await asyncio.to_thread(_ficha_y_cuenta,
                                                         departamento)
            route = verdict["route"]
            model = verdict.get("model")

            # compuerta de privacidad: SOLO corre con el gesto explicito
            # `/nube`. Sin el, el chat se comporta exactamente como antes de
            # esta seccion -- `nube_local` arranca en False y `mensaje_saliente`
            # / `chat_id_nube` valen lo mismo que `chat_msg` / `chat_id` de
            # siempre, asi que ningun sitio de envio de abajo cambia de
            # comportamiento si Pedro no pidio la nube.
            nube_local = False
            mapa = None
            mensaje_saliente = chat_msg
            chat_id_nube = chat_id
            if directives.get("nube"):
                mapa = conversacion.mapa_para(chat_id)
                # el juez es una llamada bloqueante a Ollama: en un hilo,
                # como el resto de las llamadas al modelo local del turno.
                dec = await asyncio.to_thread(
                    privacidad_nube.preparar_envio, chat_msg, mapa)
                r = privacidad_nube.ruteo_para_nube(
                    dec, route, directives.get("force_route"))
                route = r["route"]
                verdict["route"] = r["route"]
                nube_local = r["nube_local"]
                if nube_local:
                    # fallo cerrado: una credencial (o un juez que no puede
                    # categorizar con seguridad) nunca sale, ni tapada. El
                    # modelo tambien se resetea a uno local de verdad -- el
                    # veredicto original pudo haber elegido un modelo de
                    # suscripcion/api que Ollama no tiene.
                    model = _route_model_name("local")
                    await ws.send_json({"type": "privacidad", "action": "local",
                                        "motivo": dec["motivo"]})
                else:
                    await ws.send_json({"type": "privacidad", "action": "tapado",
                                        "tapados": dec["tapados"],
                                        "texto_tapado": dec["texto"]})
                    if route != "local":
                        # va a la nube tapado: sin historial (chat_id None)
                        # para no filtrar un turno privado anterior de la
                        # misma conversacion. Si Pedro forzo /local a la vez
                        # que /nube, route se queda "local" (arriba) y esta
                        # rama no corre: al modelo local le llega el texto
                        # real, no marcadores que nadie va a reponer.
                        mensaje_saliente = r["mensaje"]
                        chat_id_nube = None
                        if route == "subscription" and not verdict.get("client"):
                            # la ruta local (la que /nube subio) no trae
                            # cliente de suscripcion -- los modelos locales
                            # no tienen uno. Resolver antes de llamar.
                            verdict["client"] = (
                                _best_subscription_client(None) or "claude")
                            model = _route_model_name("subscription", verdict["client"])

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
            # la tuberia de filtros del turno conversacional: foco primero,
            # abismo despues (spec seccion 4). `puede_cortar` mira el estado
            # del turno en el momento de cada marca: bajo el tope corta, con
            # el tope alcanzado o la consulta apagada retira sin cortar.
            # En la ruta one-shot (suscripcion) el corte lo decide SOLO el
            # detector sobre el texto crudo (`cortar_en_marca`, mas abajo):
            # el filtro no corta nunca, retira con aviso. Si pudiera cortar
            # por su cuenta -una marca que PATRON no ve porque foco o
            # `reponer` la cambian ANTES de que el filtro la mire- quedaria
            # una marca pendiente que nadie consume y el resto del turno se
            # tragaria en silencio.
            corta_el_filtro = (estado_abismo.puede_cortar if route != "subscription"
                               else (lambda: False))
            emisor = Emisor(ws, agente_id=agente_id, filtros=[
                *([_mapa_foco.Filtro()] if _mapa_foco is not None else []),
                abismo_filtro.FiltroAbismo(puede_cortar=corta_el_filtro)])
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
            # en /nube no se lanza el borrador: corre `claude -p` con el
            # mensaje crudo (chat_msg), sin pasar por la compuerta de
            # redaccion -- un canal lateral a la nube que se salteo.
            if _edit_target and not directives.get("nube"):
                asyncio.ensure_future(_run_chat_draft(
                    ws, chat_msg, _edit_target, f"{agente_id}:borrador",
                    departamento))

            # el Quien del turno para la aduana (spec seccion 4): chat_id ya
            # es str (se creo en el bloque de arriba si faltaba), ROOT ya es
            # el proyecto del chat (`_switch_project` corrio antes), `route`
            # es la decidida (post-/nube), `sesion` es lo que devolvio
            # `_ws_autorizado`. Se arma UNA vez por turno: la web y la
            # vision por SDK lo heredan.
            quien_turno = aduana.Quien(
                origen="turno",
                chat=chat_id,
                proyecto=_proyecto(),
                gesto=_gesto_de(directives),
                # una ruta que la aduana no conoce va como None (la telemetria
                # del turno la conserva, correlable por chat y ts): el
                # ValueError de `Quien.__post_init__` jamas mata el turno
                # (invariante 2: medir no rompe el producto). Hoy `route` solo
                # vale local/subscription/api; esto cubre el dia que `_decide`
                # o `ruteo_para_nube` devuelvan una nueva
                ruta=route if route in aduana.RUTAS else None,
                desde=_desde_de_sesion(sesion),
            )

            # 1.5) navegación web si la tarea lo pide (grounding + preview)
            web_material = None
            # en /nube se saltea: `calipso_web.research` manda el mensaje
            # crudo (chat_msg) a DuckDuckGo, otro canal lateral a la nube.
            if (features.get("needs_web") or directives.get("force_web")) \
                    and not directives.get("nube"):
                await ws.send_json({"type": "web", "action": "search",
                                    "query": chat_msg[:140]})
                # todo lo de adentro (search, fetch, render, deps.ensure)
                # corre en este hilo: el flock del libro nunca cae en el loop
                web_material = await asyncio.to_thread(
                    calipso_web.research, chat_msg, 4, 2, quien_turno)
                await ws.send_json({
                    "type": "web", "action": "results",
                    "results": web_material["results"],
                    "pages": [{"url": p["url"], "title": p["title"]}
                              for p in web_material["pages"]]})

            # 2) contexto (core + recuerdos) y 3) streaming
            runtime = _harness_context(verdict, route, model, note)
            # `_build_context` arma el brief de economia bajo el candado del
            # libro (flock bloqueante); en un hilo, igual que `_ficha_y_cuenta`.
            # si el turno va a la nube tapado (/nube y la ruta no quedo en
            # local), el system tiene que ser minimo: `_build_context` trae
            # recuerdos y contexto personal sin tapar, y saldria crudo.
            a_la_nube_tapado = bool(directives.get("nube")) and route != "local"
            secciones_base = await asyncio.to_thread(
                _sistema_del_turno, chat_msg, runtime, features, a_la_nube_tapado)
            # vision: describir imágenes antes de inyectar contexto de adjuntos.
            # en /nube se saltea: `vision_describe` puede mandar la imagen mas
            # el mensaje crudo (chat_msg) a Anthropic -- ante la duda (no hay
            # certeza de un camino local sin fuga), saltear es lo seguro.
            vision_text, aviso_imagen = "", False
            if attachments.has_images(str(ROOT), attachment_ids) \
                    and not directives.get("nube"):
                vision_text = await asyncio.to_thread(
                    attachments.vision_describe, str(ROOT), attachment_ids, chat_msg,
                    quien=quien_turno)
                if not vision_text:
                    vm = attachments.ollama_vision_model()
                    aviso_imagen = not vm and not os.environ.get("ANTHROPIC_API_KEY")
            attachment_context = attachments.context_block(str(ROOT), attachment_ids)
            # las secciones que el server suma (adjuntos y departamento no
            # van en /nube-a-la-nube: ver `_secciones_del_turno`); el string
            # plano se rinde recien para el payload, y en la ruta local con
            # streaming se rinde POR PASADA (la ventana recorta antes)
            secciones = _secciones_del_turno(
                secciones_base, vision_text=vision_text, aviso_imagen=aviso_imagen,
                attachment_context=attachment_context, bloque_dep=bloque_dep,
                web_material=web_material, a_la_nube_tapado=a_la_nube_tapado)
            system = prompt_compiler.render_context(secciones)
            usage: dict = {}
            used_route = route
            full = ""
            agent_team: dict | None = None
            # lo que el canario lee al cierre (spec canarios): la ventana por
            # pasada, el usage de cada pasada y lo que viajo en la ultima
            ventana: list[dict] = []
            usages: list[dict] = []
            mensajes_pasada: list[dict] | None = None
            secciones_pasada: list[tuple[str, str]] = secciones
            steered = False
            # el texto CRUDO entero del turno (con marcadores, sin marcas)
            # donde `full` es el REPUESTO: suscripcion y orquestador lo
            # acumulan invocacion por invocacion; en streaming no hay
            # reponer y `full` ya es crudo (queda ""). El canario de un
            # turno tapado ancla sobre esto (decision 18)
            crudo_total = ""
            try:
                if _should_orchestrate(features, directives, chat_msg) and not nube_local:
                    runtime = _harness_context(
                        verdict, "orchestrator", model,
                        f"equipo dinamico sobre ruta base {route}")
                    secciones = _secciones_del_turno(
                        await asyncio.to_thread(
                            _sistema_del_turno, chat_msg, runtime, features, a_la_nube_tapado),
                        attachment_context=attachment_context, bloque_dep=bloque_dep,
                        web_material=web_material, a_la_nube_tapado=a_la_nube_tapado)
                    system = prompt_compiler.render_context(secciones)
                    full, agent_team, queued = await _run_dynamic_team(
                        ws, inbox, mensaje_saliente, features, system, verdict,
                        approval_required=bool(directives.get("force_team")),
                        departamento=departamento,
                        allow_paid=(directives.get("force_route") == "api"))
                    if queued:
                        pending = queued
                    used_route = "orchestrator"
                    usage["completion_tokens"] = len(full.split())
                    crudo_total = full
                    if mapa is not None:
                        full = redaccion.reponer(full, mapa)
                    # ruta orquestador: fuera del abismo (spec seccion 4).
                    # Las marcas de los agentes ya se retiraron con
                    # _limpiar_marcas; una que llegue en la sintesis se
                    # retira con aviso, sin corte.
                    estado_abismo.apagada = True
                    full = await emisor.chunk(full)
                elif route == "subscription":
                    # EL ABISMO en la ruta one-shot (spec secciones 4 y 8):
                    # no hay stream que cortar. El detector lee el texto
                    # entero cuando vuelve; la primera marca valida corta (lo
                    # posterior vino sin contexto y se descarta) y la
                    # reentrada re-invoca el CLI completo: una consulta son
                    # DOS invocaciones reales, declaradas en telemetry (el
                    # probe pasivo de consumo las ve). Si la consulta falla,
                    # o el steer gana, no se reinvoca: lo que el CLI escribio
                    # despues de la marca vale, sin marcas (seccion 8.4).
                    secciones_base = secciones
                    mensaje_turno = mensaje_saliente
                    # el destino del abismo (viaje.py): "nube" = el gesto
                    # /nube (anillos + juez); "local" = el modelo de la
                    # maquina (transparente); "afuera" = suscripcion o API
                    # sin /nube (los modelos ven todo, pero la credencial
                    # jamas sale: spec de la aduana 13 y 15.1)
                    destino = ("nube" if a_la_nube_tapado
                               else "local" if route == "local" else "afuera")
                    etiqueta = f"{verdict.get('persona') or verdict['client']} via {verdict['client']}"
                    while True:
                        # las suscripciones solo ESTIMAN (no exponen el tamano
                        # del prompt): una fila de ventana por invocacion,
                        # sin evaluado ("sin medicion")
                        _, _, fila_ventana = await asyncio.to_thread(
                            _ventana_antes, secciones, [], mensaje_turno, route, model,
                            len(ventana) + 1)
                        ventana.append(_ventana_despues(fila_ventana, {}))
                        texto, queued = await _run_subscription_text_live(
                            ws, inbox, verdict["client"], system, mensaje_turno, model,
                            # la reentrada deja un SEGUNDO registro de job (no
                            # un cobro): que se distinga en el panel y en
                            # process/start
                            label=(etiqueta if not estado_abismo.sintetica else
                                   f"{etiqueta} (reentrada del abismo {estado_abismo.consultas})"),
                            chat_id=chat_id_nube,
                            congelar=abismo_turno.prefijo_congelado)
                        if queued:
                            pending = queued     # un texto de Pedro, o "/stop" (no-op en el tope del turno)
                        usage["completion_tokens"] = (usage.get("completion_tokens", 0)
                                                      + len(texto.split()))
                        tramo_crudo, marca_valida = abismo_turno.cortar_en_marca(texto)
                        if marca_valida is not None and not estado_abismo.puede_cortar():
                            # tope alcanzado: la marca se retira (lo hace el
                            # filtro, con aviso) y el texto posterior vale
                            tramo_crudo, marca_valida = texto, None
                        # en /nube la nube escribe con marcadores: se repone
                        # lo visible; lo CRUDO es lo que vuelve a la nube
                        visible = (redaccion.reponer(tramo_crudo, mapa)
                                   if mapa is not None else tramo_crudo)
                        # lo crudo de ESTA invocacion, incluida la ultima (la
                        # respuesta de la reentrada, que `tramos_crudos` no
                        # guarda porque no la corta ninguna marca)
                        crudo_total += abismo_turno.retirar_marcas(tramo_crudo)
                        visible = await emisor.chunk(visible)
                        # el texto llego ENTERO: nada de lo que la tuberia
                        # retenga puede completarse en otra invocacion. Se
                        # vuelca aca (un corchete suelto se ve; un `⟦abismo:`
                        # abierto se descarta con aviso, spec seccion 11) en
                        # vez de arrastrarlo por la pesca y la reinvocacion,
                        # donde se tragaba la continuacion entera
                        visible += await emisor.cerrar()
                        full += visible
                        if marca_valida is None:
                            break
                        estado_abismo.tramos.append(visible)
                        # crudo (con marcadores, invariante 9) pero SIN las
                        # marcas ilegibles anteriores al corte ni una abierta
                        # al final: el modelo no tiene que releer su propia
                        # marca fallida en el "venias diciendo" (los
                        # marcadores [ID_N] no son marcas)
                        estado_abismo.tramos_crudos.append(abismo_turno.recortar_abierta(
                            abismo_turno.retirar_marcas(tramo_crudo)))
                        if queued:
                            # el steer de Pedro gana (spec seccion 10); tambien
                            # el /stop, que ya mato al CLI: ni pesca ni reinvocacion
                            telemetry.log_event("abismo", evento="abortada_por_steer",
                                                consultas=estado_abismo.consultas,
                                                momento="cli")
                            hubo_bloque = False
                        else:
                            hubo_bloque = await _pescar_abismo(
                                ws, marca_valida, estado_abismo, destino=destino,
                                mapa=mapa, departamento=departamento,
                                agente_id=agente_id, inbox=inbox, chat_id=chat_id)
                        if not hubo_bloque:
                            # lo posterior a la marca vale (seccion 8.4, la
                            # letra exacta: aca el texto posterior existe).
                            # Sus marcas se retiran CON aviso por fuera del
                            # filtro, que con la consulta a medias no puede
                            # volver a cortar (dejaria una marca pendiente
                            # que nadie consume)
                            resto_crudo = _retirar_con_aviso(texto[len(tramo_crudo):], "posterior")
                            crudo_total += resto_crudo
                            full += await emisor.chunk(
                                redaccion.reponer(resto_crudo, mapa)
                                if mapa is not None else resto_crudo)
                            break
                        secciones, mensaje_turno = abismo_turno.prompt_reentrada(
                            secciones_base, estado_abismo.bloques,
                            estado_abismo.tramos_crudos, mensaje_saliente)
                        system = prompt_compiler.render_context(secciones)
                        estado_abismo.sintetica = True
                        telemetry.log_event("abismo", evento="reinvocacion_suscripcion",
                                            client=verdict["client"],
                                            consultas=estado_abismo.consultas)
                else:
                    # EL ABISMO (spec seccion 4): el bucle de streaming de
                    # siempre, envuelto en un bucle exterior que reentra al
                    # modelo despues de cada consulta. Todo lo que esta
                    # afuera de este `while` (chats.append, mem.remember,
                    # _cobrar_turno, cost, done, emisor.cerrar) corre UNA vez
                    # por turno: esos son los catorce salteos de la pasada
                    # sintetica, gratis por construccion. El system base del
                    # turno se guarda una vez: la reentrada NO re-corre
                    # `_sistema_del_turno` (recall, economia bajo candado).
                    secciones_base = secciones
                    mensaje_turno = mensaje_saliente
                    # el historial se arma UNA vez por turno (antes se releia
                    # chats.json en cada pasada; es el mismo: el mensaje de
                    # Pedro ya esta persistido y el de Calipso recien al
                    # final) y viaja prearmado a `_chunks_for`, que devuelve
                    # los messages que mando (spec canarios 2.3)
                    historial = _history_messages(chat_id_nube)
                    # el destino del abismo (viaje.py): "nube" = el gesto
                    # /nube (anillos + juez); "local" = el modelo de la
                    # maquina (transparente); "afuera" = suscripcion o API
                    # sin /nube (los modelos ven todo, pero la credencial
                    # jamas sale: spec de la aduana 13 y 15.1)
                    destino = ("nube" if a_la_nube_tapado
                               else "local" if route == "local" else "afuera")
                    while True:
                        if estado_abismo.sintetica and not inbox.empty():
                            # el steer de Pedro gana (spec seccion 10): llego
                            # con el corte o durante la pesca (que ya cerro
                            # su senal en `fallo`). Se atiende como el
                            # barge-in de abajo sin abrir otro stream para
                            # cerrarlo enseguida; la consulta queda abortada
                            # y el proximo turno resetea el estado.
                            steer = inbox.get_nowait()
                            telemetry.log_event("abismo", evento="abortada_por_steer",
                                                consultas=estado_abismo.consultas,
                                                momento="pesca")
                            await ws.send_json({"type": "steered"})
                            full += " …(interrumpido)"
                            steered = True
                            if steer and steer.strip() and steer.strip() != "/stop":
                                pending = steer
                            break
                        # un `usage` por pasada: los generadores ASIGNAN, no
                        # suman (dispatch.py:434-436, :487-489). Se acumula
                        # abajo. La pasada cortada nunca entrega el suyo
                        # (llega en el chunk final): en api es una
                        # subfacturacion real, declarada (invariante 5).
                        usage_pasada: dict = {}
                        # la ventana, por pasada (spec canarios 2.3, invariante
                        # 9): presupuesto y, en local, el recorte de lo volatil
                        # ANTES de mandar; en hilo (el tokenizador se carga la
                        # primera vez y encode no es gratis)
                        secciones_pasada, historial_pasada, fila_ventana = await asyncio.to_thread(
                            _ventana_antes, secciones, historial, mensaje_turno, route, model,
                            len(ventana) + 1)
                        gen, model, mensajes_pasada = _chunks_for(
                            route, prompt_compiler.render_context(secciones_pasada), mensaje_turno,
                            usage_pasada, model, verdict.get("effort"),
                            chat_id=chat_id_nube, history=historial_pasada)
                        marca_pendiente = None
                        desde = len(full)
                        while True:
                            if not inbox.empty():  # steering: barge-in mientras responde
                                steer = inbox.get_nowait()
                                try:
                                    gen.close()
                                except Exception:
                                    pass
                                if estado_abismo.sintetica:
                                    # steer durante el stream de la reentrada
                                    # (spec seccion 10, "idem"): la fila de
                                    # aviso, ademas del steered de siempre
                                    telemetry.log_event("abismo", evento="abortada_por_steer",
                                                        consultas=estado_abismo.consultas,
                                                        momento="reentrada")
                                await ws.send_json({"type": "steered"})
                                full += " …(interrumpido)"
                                steered = True
                                if steer and steer.strip() and steer.strip() != "/stop":
                                    pending = steer
                                break
                            chunk = await asyncio.to_thread(_next_or_stop, gen, sentinel)
                            if chunk is sentinel:
                                break
                            full += await emisor.chunk(chunk)
                            marca_pendiente = emisor.marca_abismo()
                            if marca_pendiente is not None:
                                # el corte: DESPUES de emisor.chunk (la marca
                                # ya salio del filtro) y ANTES de la proxima
                                # to_thread (ningun hilo esta iterando el
                                # generador). El mismo gesto que el steering.
                                try:
                                    gen.close()
                                except Exception:
                                    pass
                                break
                        for k in ("prompt_tokens", "completion_tokens"):
                            usage[k] = usage.get(k, 0) + usage_pasada.get(k, 0)
                        ventana.append(_ventana_despues(fila_ventana, usage_pasada))
                        usages.append(dict(usage_pasada))
                        if marca_pendiente is None:
                            break
                        tramo = full[desde:]
                        estado_abismo.tramos.append(tramo)
                        estado_abismo.tramos_crudos.append(tramo)   # en streaming no hay reponer
                        if not inbox.empty():
                            # el steer llego con el corte: ni pondering ni
                            # pesca; el tope del bucle lo atiende
                            estado_abismo.sintetica = True
                            continue
                        # tras un `fallo` (pesca vacia, error, steer durante
                        # la pesca, o el viaje que no deja subir el bloque
                        # en /nube) se reentra SIN bloque (spec seccion 4,
                        # paso 4): en streaming el generador ya se cerro en
                        # la marca y "el texto posterior vale" (seccion 8.4)
                        # no existe. La regla literal de 8.4 la cumple solo
                        # la ruta one-shot (Task 7). Con steer, el tope del
                        # bucle aborta antes de abrir el stream.
                        await _pescar_abismo(ws, marca_pendiente, estado_abismo,
                                             destino=destino, mapa=mapa,
                                             departamento=departamento,
                                             agente_id=agente_id, inbox=inbox,
                                             chat_id=chat_id)
                        secciones, mensaje_turno = abismo_turno.prompt_reentrada(
                            secciones_base, estado_abismo.bloques,
                            estado_abismo.tramos_crudos, mensaje_saliente)
                        estado_abismo.sintetica = True
            except Exception as e:  # p.ej. LiteLLM apagado en ruta api
                # el exito del alterno se declara con una bandera y no con
                # `full` no vacio: desde el abismo `full` ya lleva el tramo
                # pescado cuando la REINVOCACION del CLI falla, y con `full`
                # como senal ese fallo pasaba por exito (sin fallback local,
                # sin meta, sin fila) y el turno cerraba con el tramo a medias
                alterno_ok = False
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
                                # este fallback manda `mensaje_saliente` (ya
                                # tapado si /nube) a otra suscripcion: sigue
                                # siendo un envio a la nube, mismo criterio.
                                a_la_nube_tapado = (bool(directives.get("nube"))
                                                     and used_route != "local")
                                system = prompt_compiler.render_context(_secciones_del_turno(
                                    await asyncio.to_thread(
                                        _sistema_del_turno, chat_msg, runtime, features,
                                        a_la_nube_tapado),
                                    attachment_context=attachment_context, bloque_dep=bloque_dep,
                                    a_la_nube_tapado=a_la_nube_tapado))
                                estado_abismo.apagada = True   # un turno que cayo al fallback no consulta
                                texto_alterno, queued = await _run_subscription_text_live(
                                    ws, inbox, alternate, system, mensaje_saliente, None,
                                    label=f"fallback via {alternate}",
                                    chat_id=chat_id_nube)
                                if queued:
                                    pending = queued
                                usage["completion_tokens"] = (usage.get("completion_tokens", 0)
                                                              + len(texto_alterno.split()))
                                crudo_total += abismo_turno.retirar_marcas(texto_alterno)
                                if mapa is not None:
                                    texto_alterno = redaccion.reponer(texto_alterno, mapa)
                                # se SUMA al tramo que Pedro ya leyo (si la
                                # que fallo fue la reinvocacion del abismo):
                                # lo persistido es lo que se vio, no solo lo
                                # del alterno
                                full += await emisor.chunk(texto_alterno)
                                used_route = "subscription"
                                route = "subscription"
                                alterno_ok = True
                                raise StopIteration
                            except StopIteration:
                                pass
                            except Exception as e2:
                                e = e2
                            else:
                                continue
                    if not alterno_ok:
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
                        # este ultimo fallback ya corre en local (chat_msg
                        # crudo, chat_id sin tapar mas abajo): used_route
                        # acaba de quedar "local", asi que el criterio da
                        # False y el contexto completo de siempre aplica.
                        a_la_nube_tapado = (bool(directives.get("nube"))
                                             and used_route != "local")
                        secciones = _secciones_del_turno(
                            await asyncio.to_thread(
                                _sistema_del_turno, chat_msg, runtime, features,
                                a_la_nube_tapado),
                            attachment_context=attachment_context, bloque_dep=bloque_dep,
                            a_la_nube_tapado=a_la_nube_tapado)
                        estado_abismo.apagada = True   # un turno que cayo al fallback no consulta
                        # una sola pasada, con su ventana (recorte en local)
                        secciones_pasada, historial_pasada, fila_ventana = await asyncio.to_thread(
                            _ventana_antes, secciones, _history_messages(chat_id), chat_msg,
                            "local", model, len(ventana) + 1)
                        gen, model, mensajes_pasada = _chunks_for(
                            "local", prompt_compiler.render_context(secciones_pasada), chat_msg,
                            usage, chat_id=chat_id, history=historial_pasada)
                        while True:
                            if not inbox.empty():  # steering en el fallback local
                                steer = inbox.get_nowait()
                                try:
                                    gen.close()
                                except Exception:
                                    pass
                                await ws.send_json({"type": "steered"})
                                full += " …(interrumpido)"
                                steered = True
                                if steer and steer.strip() and steer.strip() != "/stop":
                                    pending = steer
                                break
                            chunk = await asyncio.to_thread(_next_or_stop, gen, sentinel)
                            if chunk is sentinel:
                                break
                            full += await emisor.chunk(chunk)
                        ventana.append(_ventana_despues(fila_ventana, usage))
                        usages.append(dict(usage))
                else:
                    await ws.send_json({"type": "error", "text": str(e)})
            except StopIteration:
                pass

            # lo que el filtro venia reteniendo por si era una marca: si la
            # respuesta termino en un corchete suelto, Pedro tiene que verlo
            full += await emisor.cerrar()

            # 3b) los canarios (spec 2026-09-11): anclaje, degeneracion y
            # ventana sobre lo que el turno ya tiene, en hilo, con tope y
            # fail-open. Marcan y miden, no frenan (decision de Pedro). El
            # veredicto va a la fila `chat_turn`, al meta del mensaje, a la
            # senal ws (antes del done) y, en dos numeros, al remember.
            veredicto = await _veredicto_del_turno(
                respuesta=full, secciones=secciones_pasada, mensajes=mensajes_pasada,
                mensaje=mensaje_saliente, bloques=list(estado_abismo.bloques),
                features=features, usages=usages, ventana=ventana,
                hizo={"consulto": estado_abismo.consultas > 0,
                      "recordo": bool(full.strip()),
                      "repo": bool(features.get("needs_repo")),
                      "web": bool(web_material and (web_material["results"] or web_material["pages"]))},
                consultas=estado_abismo.consultas, steered=steered,
                tapado=a_la_nube_tapado,
                # el texto crudo ENTERO del turno: `crudo_total` donde full
                # es repuesto (suscripcion, orquestador); en streaming
                # `full` ya es crudo (decision 18)
                texto_crudo=crudo_total or full)

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
                abismo_consultas=estado_abismo.consultas,
                canarios=veredicto,
                latency_ms=round((time.perf_counter() - turn_started) * 1000),
                cost_usd=entry["cost_usd"],
                **_contexto_persistido(secciones_pasada, mensajes_pasada, estado_abismo.bloques),
            )
            # la senal a las dos UIs, ANTES del done: se aplica sobre el
            # mensaje que se esta cerrando
            await ws.send_json({"type": "canario", **veredicto})

            # 5) recordar el intercambio (episodica)
            #
            # Tres cosas se arreglaron aca el 2026-08-31, y las tres son la
            # misma clase de error: lo que se guarda mal se recupera mal, y
            # nadie se entera porque no levanta ninguna excepcion.
            #
            # 1. El literal tenia las dos vocales acentuadas doble-encodeadas
            #    (el mojibake clasico: una A con tilde donde va la vocal), asi
            #    que la cadena rota se EMBEBIA tal cual y cada intercambio
            #    degradaba su propia recuperacion. No se transcribe aca a
            #    proposito: escribirla para explicarla es como vuelve.
            # 2. Iba a `scope="auto"`, que es "el proyecto si hay proyecto"
            #    (memory.py:187-194) -- y el chat SIEMPRE tiene proyecto. O
            #    sea que la vida de Pedro se archivaba bajo el repo que
            #    tuviera abierto, y el ambito global termino con cero filas
            #    despues de dos meses. Va a global: en la conversacion la
            #    constante es Pedro, el repo es la variable. Lo que si es
            #    del proyecto lo escriben los que hablan del proyecto
            #    (reflect, el bibliotecario, el jefe de departamento).
            # 3. Corria sobre el event loop, a diferencia del `remember` de
            #    la meta ocho lineas mas arriba (:2377), que ya va por hilo.
            #
            # Y la procedencia (spec 2026-09-11, seccion 2): el par sigue
            # siendo el documento (el embedding no cambia), pero la pregunta
            # es la LIMPIA (`chat_msg`, sin el `/local` de adelante) y los
            # metadatos dicen quien contesto de verdad: `ruta` es la USADA
            # (`used_route`: local tras un fallback, orchestrator con equipo,
            # subscription con el alterno; `route` sigue siendo la decidida),
            # `modelo` el que contesto, `chat` el id y `procedencia=1` la
            # marca para contar y para la idempotencia del reindex. Lo que
            # sea None lo descarta `Scope.remember`. Se lee con
            # `memoria_procedencia.presentar`, nunca crudo.
            # Y los canarios (spec 2026-09-11): dos numeros del veredicto,
            # `degeneracion` y `sin_anclaje` (None si el canario fallo).
            if full.strip():
                try:
                    await asyncio.to_thread(
                        mem.remember,
                        f"Pedro pregunto: {chat_msg}\nCalipso respondio: {full.strip()}",
                        scope="global", route=verdict["route"], kind="chat",
                        ruta=used_route, modelo=model, chat=chat_id, procedencia=1,
                        **canarios.resumen_de_remember(veredicto))
                except Exception:
                    pass    # recordar no puede voltear un turno ya contestado
            if full.strip():
                chats.append(chat_id, "assistant", full.strip(), {
                    "route": used_route,
                    "model": model,
                    "client": verdict.get("client"),
                    "agent_team": agent_team,
                    "canarios": veredicto,
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
def api_reflect(request: Request) -> dict:
    """Dispara la consolidaciÃƒÂ³n: promueve hechos duraderos al core curado."""
    promoted = mem.reflect(_quien_http(request, "gesto", "/api/reflect"))
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
    La de cierre SI escribe el libro de la economia: dispara el mismo pulso
    semanal que hoy solo corre a mano via POST /api/economia/cierre. La de
    consumo (calipso/consumo.py) solo lee jsonl locales -- ningun modelo,
    ningun CLI, ninguna decision economica.
    """
    def _reflect(r):
        # el Quien viaja en el dict de la rutina cuando lo manda el boton
        # (`api_routines_run`, como dict JSON-seguro); el ticker no lo trae:
        # rutina desde la maquina. ROOT se lee ACA, al correr: los handlers
        # son closures fijos creados una vez al arrancar el ticker.
        if r.get("quien"):
            quien = aduana.Quien(**r["quien"])
        else:
            quien = aduana.Quien(origen="rutina", proyecto=_proyecto(),
                                 rutina={"kind": r["kind"], "id": r["id"]},
                                 desde={"credencial": "maquina"})
        mem.reflect(quien)

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
            carta=leer_carta(cuenta.split(":", 1)[1]),
            proyectos=catastro.cargar(),
            publicar=_publicar_jefe(cuenta))
        # SIN candado envolvente durante el tic: incluye una llamada a un
        # modelo, y tener el flock tomado durante segundos serializa el chat
        # y a dispatch contra el. La lectura de arriba ya paso por su
        # candado; la escritura del bus (si el jefe propone) toma el suyo
        # en `_contratar_para`.
        _plantel_jefe.tic(ctx, cuenta, semana)

    def _cierre(_r):
        # el sexto kind: dispara el pulso semanal de la economia (expirar
        # PT, declarar quiebras, liquidar trabajos que no rinden, repartir
        # presupuesto de direccion, reintentar cargos pendientes). No
        # reimplementa nada -- es el mismo llamador que POST
        # /api/economia/cierre (api_eco_cierre), con el mismo candado y el
        # mismo cuidado de reconstruir el estado FRESCO adentro.
        eco = _economia()
        if eco is None:
            return  # sin ~/.calipso/economia todavia: nada que cerrar
        ts, semana = _eco_ahora()
        with _eco_candado(eco["pagador"].ruta_libro):
            eco = _economia()  # fresco BAJO el candado (reentrante adentro)
            _eco_op.cerrar_semana_operativa(
                eco["pagador"].mercado_fresco(), eco["bus"], eco["cola"],
                ts, semana,
                # api_eco_cierre recibe este monto en el cuerpo del pedido;
                # una rutina no tiene quien se lo pase. Su propio default
                # (0) ya significa "no asignar presupuesto de direccion en
                # este cierre" -- heredar ese default es la decision
                # explicita de no inventarle a Pedro una politica fiscal
                # que nunca pidio. Si el la quiere, la corre a mano con el
                # monto que decida via el endpoint.
                presupuesto_direccion_mm=0)
            eco["pagador"].reintentar_pendientes()

    def _consumo(_r):
        # mismo espiritu que _catastro: barre lo que ya esta en disco
        # (calipso_consumo.escanear) y deja una foto plegada
        # (calipso_consumo.resumen) -- nunca llama a `claude`/`codex`, y
        # por lo tanto nunca gasta la cuota que esta midiendo.
        calipso_consumo.escanear()
        calipso_consumo.resumen()

    return {"reflect": _reflect, "learn": _learn, "backup": _backup,
            "catastro": _catastro, "departamento": _departamento,
            "cierre": _cierre, "consumo": _consumo}


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
def api_routines_run(routine_id: str, request: Request) -> dict:
    """Corre una rutina ahora, ignorando el vencimiento (boton manual)."""
    routine = calipso_routines.get(routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="rutina no encontrada")
    handler = _routine_handlers().get(routine["kind"])
    if handler is None:
        raise HTTPException(status_code=400, detail="kind sin handler")
    now = datetime.datetime.now()
    # `gesto` con la rutina que dispara: el Quien viaja dentro del dict
    # porque los handlers son `Callable[[dict], Any]` compartidos con el ticker
    quien = _quien_http(request, "gesto", "/api/routines/{id}/run",
                        rutina={"kind": routine["kind"], "id": routine["id"]})
    try:
        handler(dict(routine, quien=quien.a_dict()))
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
            # con el token en la URL y desde la propia maquina: mientras
            # el secreto falte, /setup no se sirve de otra forma
            else "Abre /setup?token=<el token> en la propia maquina.",
            # sin boton mientras falte el secreto: un "Abrir" a /setup a
            # secas rebota a /login (la cookie-token no abre la ventana del
            # punto 1) y contradice el detail. El token no se pone en la
            # URL del boton: dejaria `?token=` en el historial, que es lo
            # que C4 saco. Con el secreto escrito el enlace vuelve.
            "/setup" if _TOTP_SECRET_FILE.exists() else None),
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
        quien = _quien_http(request, "gesto", "/api/deps/install")
        return await asyncio.to_thread(deps.ensure, body["tool"], quien)
    if body.get("package"):
        # `deps.ensure_pip` (borrada con la aduana) corria `pip install <lo
        # que venga>`, o sea ejecucion de codigo arbitrario para cualquiera
        # que tenga el token. La rama se cierra: lo que se puede instalar es
        # el catalogo cerrado de `deps.TOOLS`, y para sumar algo se edita
        # ese catalogo, no se manda por HTTP.
        raise HTTPException(
            status_code=403,
            detail="instalar un paquete arbitrario esta cerrado: usa 'tool' "
                   "del catalogo de deps.TOOLS")
    raise HTTPException(status_code=400, detail="falta 'tool'")


@app.get("/api/browser/screenshot")
async def api_browser_screenshot(url: str, request: Request, full: bool = False):
    """Screenshot real de una URL con el navegador (instala Playwright si falta).
    Para la aduana es `ui`: su unico llamador es un <img src> que la pagina
    arma sola tras cada /web (index.html:1278), sin click."""
    quien = _quien_http(request, "ui", "/api/browser/screenshot")
    try:
        png = await asyncio.to_thread(calipso_browser.screenshot, url, None, full,
                                      quien=quien)
    except calipso_browser.UrlNoPermitida as e:
        # 400 y no 502: no es que el sitio fallo, es que no se va a mirar
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"no se pudo capturar: {e}")
    return Response(content=png, media_type="image/png")


@app.get("/api/updates")
def api_updates(request: Request) -> dict:
    """Versiones de CLIs (+ si hay update en npm) y modelos nuevos descubiertos.
    `ui`: lo dispara index.html:2680 al cargar `/`."""
    return discovery.updates(_quien_http(request, "ui", "/api/updates"))


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


def _correr_actualizacion(cmd: list[str], quien: aduana.Quien) -> dict:
    """Sincrona, en `to_thread` (invariante 8). Cruza con el paquete como
    consulta (`cmd[-1]`, p.ej. `@anthropic-ai/claude-code@latest`) y el
    registry de npm como destino nominal. El `except` se conserva: un npm
    caido es `{ok: False}`, no un 500, y el libro dice `fallo`."""
    try:
        with aduana.cruzar(quien, "npm install -g", destino="registry.npmjs.org",
                           carga=cmd[-1]) as cruce:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            cruce.entro(len(result.stdout or "") + len(result.stderr or ""))
        return {
            "ok": result.returncode == 0,
            "stdout": result.stdout[-1000:],
            "stderr": result.stderr[-500:],
        }
    except Exception as e:
        return {"ok": False, "stderr": str(e)}


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
    quien = _quien_http(request, "gesto", "/api/updates/run")
    return await asyncio.to_thread(_correr_actualizacion, cmd, quien)


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


def _cargar_whisper(quien: aduana.Quien):
    """Sincrona, en `to_thread`: declara la descarga del modelo (huggingface.co,
    desde adentro de faster_whisper) UNA vez por proceso y construye el modelo.
    La bandera de `_whisper_model is None` ya da el "una vez"; la de
    `declarar_una_vez` es la que se evalua antes del candado."""
    from faster_whisper import WhisperModel
    aduana.declarar_una_vez("whisper", quien, "modelo whisper",
                            destino="huggingface.co",
                            motivo="Systran/faster-whisper-tiny")
    return WhisperModel("tiny", device="cpu", compute_type="int8")


async def _get_whisper(quien: aduana.Quien):
    global _whisper_model
    async with _whisper_lock:
        if _whisper_model is None:
            _whisper_model = await asyncio.to_thread(_cargar_whisper, quien)
    return _whisper_model


@app.post("/api/transcribe")
async def api_transcribe(request: Request, audio: UploadFile = File(...)) -> dict:
    import tempfile, os
    data = await audio.read()
    suffix = pathlib.Path(audio.filename or "audio.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(data)
        tmp = f.name
    try:
        try:
            model = await _get_whisper(_quien_http(request, "gesto", "/api/transcribe"))
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
    from calipso.economia import (balances as _eco_balances,
                                  bus as _eco_bus, capacidad as _eco_cap,
                                  cola as _eco_cola,
                                  departamentos as _eco_deps,
                                  operacion as _eco_op,
                                  personal as _eco_personal,
                                  pt as _eco_pt,
                                  reloj as _eco_reloj,
                                  tipos as _eco_tipos)
    from calipso.economia.candado import (candado as _eco_candado,
                                          escribir_json_atomico as
                                          _eco_escribir_json)
    from calipso.economia.pagador import (Pagador as _EcoPagador,
                                          suscripcion_de_cliente as
                                          _eco_suscripcion,
                                          SUSCRIPCION_POR_CLIENTE as
                                          _ECO_SUS_POR_CLIENTE,
                                          _ERRORES_ECONOMICOS as
                                          _eco_errores_economicos)
    from calipso import siembra as _siembra  # noqa: E402
except Exception:  # economia no disponible: los endpoints responden inactivo
    _EcoPagador = None
    _eco_suscripcion = None
    _ECO_SUS_POR_CLIENTE = {}
    _eco_bus = _eco_cola = _eco_op = _eco_personal = _eco_reloj = _eco_candado = None
    _eco_pt = None
    _eco_balances = None
    _eco_escribir_json = None
    _eco_deps = None
    _eco_tipos = None
    _eco_errores_economicos = None
    _siembra = None

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


_RE_SEMANA_ISO = re.compile(r"^\d{4}-W\d{2}$")


def _eco_semana_pedida(pedida: str | None, semana_hoy: str) -> str:
    """La semana sobre la que se opera: la que pidan, o la del calendario.

    `semana_hoy` entra por parametro y no se lee de adentro a proposito: el
    llamador ya leyo el reloj una vez para el `ts`, y leerlo dos veces en el
    mismo request puede caer a los dos lados de un borde de semana.

    Abrir y cerrar la semana derivaban la semana de `datetime.now()` y
    ningun cuerpo aceptaba otra. Eso traba la economia con solo irse de
    viaje, y el bloqueo es de los dos lados a la vez:

    - `cerrar_semana_operativa` solo cierra la ULTIMA semana abierta
      (`operacion.py:101`). Si volves un martes de otra semana, la del
      calendario no es esa, y se niega.
    - `emitir_semana` se niega a abrir mientras un pool de PT tenga saldo
      (`pt.py:54`) -- que es exactamente lo que pasa cuando no firmaste
      nada mientras no estabas.

    O sea: no podes cerrar la vieja porque hoy no es esa, y no podes abrir
    la nueva porque la vieja no se cerro. La cadencia de la economia es un
    acto deliberado de Pedro, no una funcion del reloj de la maquina, asi
    que la semana tiene que poder viajar como dato.

    Se valida con la misma forma que exige el libro (`tipos._RE_SEMANA`):
    una semana mal escrita entra a un libro append-only y no sale."""
    if pedida is None:
        return semana_hoy
    if not _RE_SEMANA_ISO.match(pedida):
        raise HTTPException(
            status_code=400,
            detail=f"semana invalida: {pedida!r}. La forma es 2026-W35.")
    return pedida


class EcoAtenderBody(BaseModel):
    firma: dict | None = None


class EcoRelojInBody(BaseModel):
    categoria: str
    ref: str | None = None


class EcoCierreBody(BaseModel):
    presupuesto_direccion_mm: int = 0
    semana: str | None = None      # None = la del calendario


class EcoAbrirBody(BaseModel):
    cuota_firmable_mpt: int
    reserva_personal_mpt: int = 0
    semana: str | None = None      # None = la del calendario


class EcoConciliarBody(BaseModel):
    ts_in: str
    minutos: int


# El techo de los numeros de plata en la frontera http. No sale del
# dominio -- el libro no tiene monto maximo -- sino del viaje: estas
# perillas se serializan a json y las dibuja el navegador, y arriba de
# 2**53-1 un entero deja de sobrevivir el ida y vuelta por JavaScript.
# Sin esto, un `{"techo_preseed_mm": 10**400}` entraba con 200 y quedaba
# escrito con sus 401 digitos en departamentos.json.
_MAX_MM = 2 ** 53 - 1


def _no_booleano(v):
    """`True` es un `int` en Python y pydantic en modo lax lo acepta: un
    `{"techo_preseed_mm": true}` entraba como 1 y se escribia a disco. En
    una perilla de plata eso no es una coercion util, es un cuerpo mal
    armado que nadie quiso mandar."""
    if isinstance(v, bool):
        raise ValueError("se esperaba un entero, no un booleano")
    return v


class MesaFinanciarBody(BaseModel):
    """El unico cuerpo de la frontera que mueve plata de verdad.

    Vive DEBAJO de `_MAX_MM` y `_no_booleano` porque hasta hoy vivia
    arriba, y por eso era el unico cuerpo de plata sin ninguno de los dos:
    un `{"mm": true}` entraba como 1 (pydantic en modo lax acepta el bool
    como int), contestaba 200, escribia una transferencia de 1 mm y
    CERRABA la ronda -- y como el libro es append-only y un pre-seed pasa
    a `cerrada` al pagarse, una ronda de 100.000 se quemaba por un `true`
    perdido en el json, sin forma de completarla. El negativo y el cero se
    frenaban recien abajo, en `Asiento.__post_init__`: la frontera no los
    miraba.

    `gt=0` y no `ge=0`: el libro exige monto positivo (`monto debe ser
    entero positivo`), asi que el cero es un 400 seguro tres capas mas
    abajo. Frenarlo aca es la misma puerta, dicha antes.
    """
    model_config = ConfigDict(extra="forbid")

    cuenta: str
    mm: int = Field(gt=0, le=_MAX_MM)
    # opcional: lo que Pedro dijo al financiar, para el registro de
    # reacciones (calipso.plantel.reacciones). Sin palabras la propuesta
    # se financia igual -- no es un requisito, es aprendizaje si esta.
    palabras: str = ""

    sin_booleanos = field_validator("*", mode="before")(_no_booleano)


class MesaDescartarBody(BaseModel):
    """Body opcional de `descartar`: las palabras de Pedro, si las dejo.
    `extra="forbid"` como el resto de los cuerpos de la mesa."""
    model_config = ConfigDict(extra="forbid")

    palabras: str = ""


class MesaNoMasBody(BaseModel):
    """Body opcional de `no-mas`, gemelo de `MesaDescartarBody`."""
    model_config = ConfigDict(extra="forbid")

    palabras: str = ""


class MesaVeredictoBody(BaseModel):
    """Body opcional de `cumplio`/`no-cumplio`: las palabras de Pedro al
    juzgar si el trabajo cumplio lo que prometio. Mismo molde que
    `MesaDescartarBody` y `MesaNoMasBody`."""
    model_config = ConfigDict(extra="forbid")

    palabras: str = ""


class EcoSembrarDepartamentoBody(BaseModel):
    """La puerta de rango tambien vale ACA.

    `PerillasDepartamentoBody` -- el otro escritor http del mismo archivo,
    en el mismo modulo -- documenta por que sus `ge`/`le` existen:
    `Departamento` no valida rangos, y un porcentaje de 900 o un
    presupuesto negativo no rompen nada ruidosamente, se convierten en
    decisiones raras del jefe tres capas mas abajo. Los mismos numeros que
    aquel rechaza con 422 entraban por este con 200 -- y peor, porque
    sembrar es de ESCRITURA UNICA: el departamento nacia fuera del rango
    que la otra puerta define y no habia forma de sacarlo de ahi salvo
    editando el json. Un caso concreto: con `presupuesto_semanal_mm <= 0`
    el freno de agresividad de `jefe._puede` ni siquiera corre (esta detras
    de `if ... > 0`), asi que la perilla nace muda.
    """
    model_config = ConfigDict(extra="forbid")

    nombre: str
    zona: str  # "fabrica" | "personal" (deps.ZONA_FABRICA / ZONA_PERSONAL)
    presupuesto_semanal_mm: int = Field(default=0, ge=0, le=_MAX_MM)
    techo_api_ciclo_mm: int = Field(default=0, ge=0, le=_MAX_MM)
    explorar_explotar_pct: int = Field(default=50, ge=0, le=100)
    agresividad_pct: int = Field(default=30, ge=0, le=100)
    # cuanto puede PEDIR en una ronda pre-seed (departamentos.py). Default
    # cero, igual que las otras dos perillas de plata: sembrar no inventa
    # un monto: hasta que Pedro diga cuanto, el departamento no pide.
    techo_preseed_mm: int = Field(default=0, ge=0, le=_MAX_MM)
    # el segundo techo del pre-seed, el acumulado por ciclo. Default cero
    # por lo mismo, y aca cero FRENA: ver departamentos.py.
    techo_preseed_ciclo_mm: int = Field(default=0, ge=0, le=_MAX_MM)

    sin_booleanos = field_validator("*", mode="before")(_no_booleano)


class SuscripcionCapacidadBody(BaseModel):
    """El numero medido, listo para aplicarse (el probe de calipso/consumo).

    `reserva_personal` es opcional pero NO independiente: `Suscripcion`
    exige `0 <= reserva_personal < capacidad_ciclo`, asi que bajar la
    capacidad por debajo de la reserva que ya estaba puesta invalida la
    suscripcion entera. Cuando eso pasa el endpoint lo dice y no escribe;
    mandar las dos claves juntas es la forma de moverlas sin pasar por un
    estado invalido.
    """
    capacidad_ciclo: int = Field(ge=1)
    reserva_personal: int | None = Field(default=None, ge=0)
    # quien pide, para el motor de permisos (ver `_permisos_contexto`)
    origen: str = "pedro"
    chat: str | None = None
    departamento: str | None = None
    corrida: str | None = None


class PerillasDepartamentoBody(BaseModel):
    """Las perillas de un departamento YA sembrado, todas opcionales.

    Solo lo que venga en el cuerpo se cambia (`exclude_unset`): mandar el
    dict entero con defaults pisaria en silencio perillas que Pedro no
    toco. Ni `nombre` ni `zona` estan aca a proposito -- ver
    `Registro.ajustar`: mover la cuenta de un departamento deja los
    asientos viejos apuntando a la anterior, y el libro es append-only.

    Los `ge`/`le` son la puerta de la frontera http: `Departamento` no
    valida rangos (nunca los necesito, porque hasta hoy los numeros solo
    entraban por el sembrado), y un porcentaje de 900 o un techo negativo
    no rompen nada ruidosamente -- se convierten en decisiones raras del
    jefe tres capas mas abajo. `EcoSembrarDepartamentoBody` tiene los
    mismos, por lo mismo: media puerta no es una puerta.

    Y `extra="forbid"` para que el parrafo de arriba sea verdad y no una
    intencion: sin el, un cuerpo con `nombre` o `zona` se descartaba
    callado y devolvia 200 -- quien los mandaba se iba creyendo que movio
    la cuenta de un departamento.
    """
    model_config = ConfigDict(extra="forbid")

    presupuesto_semanal_mm: int | None = Field(default=None, ge=0, le=_MAX_MM)
    techo_api_ciclo_mm: int | None = Field(default=None, ge=0, le=_MAX_MM)
    explorar_explotar_pct: int | None = Field(default=None, ge=0, le=100)
    agresividad_pct: int | None = Field(default=None, ge=0, le=100)
    techo_preseed_mm: int | None = Field(default=None, ge=0, le=_MAX_MM)
    techo_preseed_ciclo_mm: int | None = Field(default=None, ge=0, le=_MAX_MM)

    sin_booleanos = field_validator("*", mode="before")(_no_booleano)


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


class EcoSembrarPerillasBody(BaseModel):
    """Las perillas de fabrica que `sembrar_guiado` aplica a cada depto de
    zona fabrica (paso 5). Mismos rangos que `EcoSembrarDepartamentoBody` y
    `PerillasDepartamentoBody`: la puerta de rango vale aca tambien."""
    model_config = ConfigDict(extra="forbid")

    presupuesto_semanal_mm: int = Field(default=0, ge=0, le=_MAX_MM)
    techo_preseed_mm: int = Field(default=0, ge=0, le=_MAX_MM)
    techo_preseed_ciclo_mm: int = Field(default=0, ge=0, le=_MAX_MM)
    techo_api_ciclo_mm: int = Field(default=0, ge=0, le=_MAX_MM)

    sin_booleanos = field_validator("*", mode="before")(_no_booleano)


class EcoSembrarGuiadoBody(BaseModel):
    """El cuerpo del helper guiado de un solo tiro (`sembrar_guiado`):
    junta lo que hoy son varias llamadas sueltas (sembrar, abrir semana,
    acunar tesoro, poner perillas, agregar rutinas, poner modo vivo) en un
    unico POST con preview/confirmacion -- ver `api_eco_sembrar_guiado`."""
    model_config = ConfigDict(extra="forbid")

    confirmacion: str = ""
    departamentos: list[EcoSembrarDepartamentoBody]
    suscripciones: dict[str, EcoSembrarSuscripcionBody] = {}
    capital_tesoro_mm: int = Field(ge=0, le=_MAX_MM)
    cuota_firmable_mpt: int = Field(gt=0, le=_MAX_MM)
    reserva_personal_mpt: int = Field(default=0, ge=0, le=_MAX_MM)
    rutina_interval_min: int = Field(default=60, ge=1)
    perillas_fabrica: EcoSembrarPerillasBody

    sin_booleanos = field_validator("*", mode="before")(_no_booleano)


class EcoPersonalMovimientoBody(BaseModel):
    tipo: str  # "ingreso" | "gasto" (personal.py), o su sinonimo "egreso"
    monto_mm: int
    categoria: str
    nota: str = ""
    # quien pide, para el motor de permisos. Ver `_permisos_contexto`: el
    # default "pedro" es porque este endpoint es hoy el formulario de
    # /fabrica; una rutina de departamento declara lo suyo y cae sola en el
    # camino desatendido de 5.6.
    origen: str = "pedro"
    chat: str | None = None
    departamento: str | None = None
    corrida: str | None = None


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
    # quien pide, para el motor de permisos (ver `_permisos_contexto`)
    origen: str = "pedro"
    chat: str | None = None
    departamento: str | None = None
    corrida: str | None = None


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
            ops_mesa = _eco_cap.semanas_operativas(asientos)

            def _standing_de(dep_crudo: str) -> dict:
                # el bus guarda el departamento CON el prefijo de cuenta
                # ("dep:atlas"); promesas, como la carta y las reacciones,
                # vive pelada de prefijo (mismo motivo que _anotar_reaccion).
                # Degrada ante un registro corrupto: la mesa es lectura, no
                # puede tumbarse por un promesas.json ilegible de UN
                # departamento.
                nombre = dep_crudo.split(":", 1)[1] if ":" in dep_crudo else dep_crudo
                try:
                    return (_plantel_promesas.standing(nombre) if nombre
                            else {"cumplidas": 0, "total": 0})
                except _plantel_promesas.ErrorPromesas:
                    return {"cumplidas": 0, "total": 0}   # degrada, no 500

            propuestas = []
            vencidas = []
            for id_ in bus.ids():
                estado = bus.estado(id_)
                # la mesa es para decidir, no un historial: lo descartado,
                # muerto y liquidado no vuelve a aparecer
                if estado not in ("alta", "financiada"):
                    continue
                d = bus.datos(id_)
                # y un pre-seed VENCIDO tampoco: `bus.financiar` lo rechaza,
                # asi que la fila seria un boton "financiar" que no puede
                # funcionar -- peor que no mostrarla. Ya no reserva cupo de
                # nadie (`situacion` lo saca de las tres listas), asi que
                # tampoco hay nada que Pedro tenga que despejar: la bandeja
                # se resuelve sola, que es todo el punto. Se mira aca con la
                # MISMA funcion que el freno del jefe y que `financiar`: dos
                # respuestas a "sigue vivo este pedido" serian dos techos.
                if estado == "alta" and _eco_bus.preseed_vencido(
                        d, ops_mesa, semana):
                    # pero SI aparte, con su id, porque si no es un
                    # huerfano permanente. El bus es append-only y nadie
                    # barre: el pedido se queda en `alta` para siempre, y
                    # sacarlo de la unica pantalla que daba su id borraba
                    # el ultimo camino para limpiarlo -- `descartar` sigue
                    # contestando 200, solo que el id ya no se veia en
                    # ningun lado. Y no es solo prolijidad: cada
                    # departamento acumula un `alta` muerto por ventana
                    # vencida, para siempre, y los cinco lectores del bus
                    # (esta mesa y la config en cada GET, `_bandeja_llena` y
                    # el recorte en cada tic del jefe) los vuelven a leer y
                    # a evaluar cada vez. El conjunto solo crece.
                    #
                    # Van en otra lista y no en `propuestas` a proposito:
                    # no hay ninguna decision que tomar sobre ellos -- no
                    # reservan cupo, no se pueden financiar, la ronda ya se
                    # puede volver a pedir-- asi que no son filas de la
                    # mesa. Es una pila para tirar, y lo unico que hace
                    # falta es que tenga tacho.
                    vencidas.append({
                        "id": id_,
                        "departamento": d.get("departamento", ""),
                        "titulo": d.get("titulo", ""),
                        "semana": d.get("semana", ""),
                        "presupuesto_mm": d.get("presupuesto_mm", 0),
                    })
                    continue
                # .get() con default, como situacion.py: una linea vieja o
                # de un esquema anterior en el bus real de Pedro no puede
                # tumbar la mesa entera con un 500 mudo.
                fila = {
                    "id": id_, "estado": estado,
                    "departamento": d.get("departamento", ""),
                    # SIN esto la mesa no puede financiar un pre-seed: se
                    # paga contra el TESORO y no contra la billetera de
                    # otro departamento (bus.financiar lo exige), y el
                    # selector de mesa.js solo lista departamentos de
                    # fabrica. El default "trabajo" es el mismo que usa
                    # `bus.financiar` para las lineas viejas del bus real
                    # de Pedro, escritas antes de que el campo existiera.
                    "tipo": d.get("tipo", "trabajo"),
                    "titulo": d.get("titulo", ""),
                    "presupuesto_mm": d.get("presupuesto_mm", 0),
                    "retorno_mm": d.get("retorno_mm", 0),
                    "criterio": d.get("criterio", {}),
                    "gastado_mm": _eco_bus.gastado(asientos, id_,
                                                   m.suscripciones),
                    "aportes": _eco_bus.aportes(asientos, id_),
                }
                # la metrica de exito NO se guarda en el libro: se deriva de
                # `promete` cada vez que se muestra. Es la unica manera de
                # que cambiar la tabla arregle tambien las propuestas
                # viejas.
                # `.get()`, no corchetes: esta funcion es deliberadamente
                # defensiva para tolerar una linea vieja o editada a mano
                # del bus real de Pedro (comentario de mas arriba), y con
                # corchetes esta era la unica de las tres derivaciones que
                # revienta con un 500 en toda la mesa en vez de degradar.
                f = d.get("forma")
                if f and _plantel_ficha is not None:
                    fila["metrica"] = _plantel_ficha.METRICA.get(
                        f.get("promete"), "")
                fila["standing"] = _standing_de(d.get("departamento", ""))
                propuestas.append(fila)
            # el PvP: los trabajos que ya llegaron a su plazo y todavia no
            # tienen veredicto. Recorre TODOS los ids del bus -- no solo
            # `alta`/`financiada` como el filtro de arriba -- porque un
            # trabajo liquidado o muerto sigue siendo juzgable (bus.vencida
            # mira `semana_financiada`, que `datos` conserva aun asi).
            por_juzgar = []
            for id_ in bus.ids():
                d = bus.datos(id_)
                if not _eco_bus.vencida(d, ops_mesa, semana):
                    continue
                dep_crudo = d.get("departamento", "")
                nombre = dep_crudo.split(":", 1)[1] if ":" in dep_crudo else dep_crudo
                try:
                    if not nombre or _plantel_promesas.juzgada(nombre, id_):
                        continue
                except _plantel_promesas.ErrorPromesas:
                    continue   # registro corrupto: la mesa degrada, no 500
                f = d.get("forma") or {}
                por_juzgar.append({
                    "id": id_, "departamento": dep_crudo,
                    "titulo": d.get("titulo", ""),
                    "promete": f.get("promete", ""),
                    "metrica": (_plantel_ficha.METRICA.get(f.get("promete"), "")
                                if _plantel_ficha is not None else ""),
                    "sobre": f.get("sobre", "")})
            deps_fabrica = [
                {"cuenta": f"dep:{x.nombre}", "nombre": x.nombre,
                 "zona": x.zona,
                 "disponible_mm": m.k.saldo(f"dep:{x.nombre}")}
                for x in m.registro.todos() if x.zona == _eco_deps.ZONA_FABRICA]
            abierta = semana in _eco_cap.semanas_operativas(asientos)
            # un pre-seed lo paga el TESORO, no una billetera de fabrica:
            # sin este saldo la mesa no puede avisar "no alcanza" antes de
            # que Pedro toque financiar, que es lo que ya hace con los
            # trabajos (`alcanza` en mesa.js).
            tesoro = m.k.saldo(_eco_tipos.TESORO)
    except _eco_errores_economicos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    # las fichas que no se entendieron viajan con la mesa y no por un
    # origen nuevo del inbox: son produccion de la fabrica que no llego
    # al bus, asi que pertenecen a la misma bandeja que las que si
    # llegaron -- y un origen nuevo obligaria a un descriptor entero
    # para algo que no tiene ni un verbo. Si el modulo no se pudo
    # importar, la clave va vacia: una bandeja que pierde sus avisos es
    # mejor que una que no carga.
    ilegibles = (_plantel_ilegibles.colapsados(_ECO_BASE, semana)
                 if _plantel_ilegibles is not None else [])
    return {"activa": True, "semana": semana, "semana_abierta": abierta,
            "propuestas": propuestas, "vencidas": vencidas,
            "departamentos": deps_fabrica, "tesoro_mm": tesoro,
            "ilegibles": ilegibles, "por_juzgar": por_juzgar}


@app.get("/api/inbox")
def api_inbox() -> dict:
    """Las cuatro bandejas en una lista.

    Un solo endpoint y no cuatro fetch del cliente, por dos razones. La
    primera es el candado: bus y cola leen el MISMO libro, `api_eco_bus`
    toma el suyo y `api_eco_cola` NO -- es el unico lector de economia sin
    candado, y su vecino lo dice textual: "y no es un ejemplo". Sin un
    candado de afuera, el bus toma y suelta, y despues la cola lee sin
    ninguno: las dos mitades de la misma pantalla pueden ver estados
    distintos. Con este, las dos leen bajo una sola tenencia.

    Tomarlo aca y que `api_eco_bus` tome el suyo adentro es seguro y
    verificado: `candado` es REENTRANTE -- un `rlock` con contador de
    profundidad (`economia/candado.py:74-90`), asi que la adquisicion
    interna no suelta la externa al salir.

    La segunda razon es que las cuatro fuentes declaran su disponibilidad
    con TRES claves distintas (`activa` en economia, `activo` en permisos,
    ninguna en memoria): traducir eso una vez del lado del servidor es
    mejor que repetirlo en el cliente.

    Se le pasan a `_inbox.juntar` CALLABLES, no datos ya traidos: `api_eco_bus`
    llama adentro a `mercado_fresco()`, que puede levantar
    `json.JSONDecodeError` si `suscripciones.json` esta corrupto -- un error
    que `_ERRORES_ECONOMICOS` no cubre, asi que nadie lo atajaba. Si esos
    `obtener_*` se llamaran ACA, afuera, un archivo de economia corrupto
    tumbaria el endpoint entero con un 400 o un 500 sin capturar (no hay
    handler global) antes de que `juntar` viera un solo item. Dejando que
    `juntar` sea quien llame a `obtener_bus()` puertas adentro de su propio
    try/except, traer el dato y traducirlo quedan bajo la MISMA guarda por
    origen -- el mismo principio de "una bandeja rota no voltea a las otras
    tres" que el modulo ya declara, extendido a la mitad que antes quedaba
    afuera.
    """
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None

    def obtener_bus() -> dict:
        return api_eco_bus() if p0 else {"activa": False}

    def obtener_cola() -> dict:
        return api_eco_cola() if p0 else {"activa": False}

    def obtener_permisos() -> dict:
        return ({"activo": True, **_permisos.vista()}
                if _permisos is not None else {"activo": False})

    def obtener_memoria() -> dict:
        return {"proposals": librarian.list_proposals(str(ROOT), "pending")}

    # nullcontext cuando no hay economia sembrada: sin p0 no hay ruta de
    # libro que tomar, y las otras dos bandejas no la necesitan.
    candado_eco = (_eco_candado(p0.ruta_libro) if p0
                   else contextlib.nullcontext())
    with candado_eco:
        items, fallaron = _inbox.juntar(
            obtener_bus, obtener_permisos, obtener_memoria, ROOT.name,
            obtener_cola)
    return {"items": items,
            "descriptores": _inbox.descriptores(),
            "pendientes": _inbox.cuenta_de_decisiones(items),
            "fallaron": fallaron}


def _anotar_reaccion(p0, id: str, reaccion: str, palabras: str) -> None:
    """Anota la reaccion de Pedro sobre una propuesta. Deriva depto y forma
    del bus. No mueve plata ni toca el libro; su propio archivo, atomico.

    El bus guarda "departamento" con el prefijo de cuenta ("dep:atlas"),
    pero la carta de ese departamento vive pelada de prefijo
    (`leer_carta(cuenta.split(":", 1)[1])`, mas arriba en este archivo) y
    `reacciones._slug` tiene que caer en el MISMO directorio que
    `memory._slug` -- si se anota con el prefijo, la reaccion cae en
    `memoria/departamento/dep-atlas/` y el jefe, que lee con el nombre
    pelado, nunca la encuentra."""
    bus = _eco_bus.Bus(p0.ruta_bus)
    d = bus.datos(id)
    dep = d.get("departamento", "")
    nombre = dep.split(":", 1)[1] if ":" in dep else dep
    if nombre:
        _plantel_reacciones.anotar(nombre, reaccion, d.get("forma"),
                                   palabras, id)


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
                    or _eco_bus.aportes(m.k.libro.asientos(), id)
                    or _eco_bus.aporte_preseed(m.k.libro.asientos(), id)):
                # los dos pliegues, porque los dos tipos de propuesta dejan
                # la plata en cuentas distintas: `aportes` mira
                # `trabajo:<id>` y `aporte_preseed` el `ref` del asiento
                # (un pre-seed cae en la cuenta del departamento). Mirar
                # solo el primero dejaba el corte contra el LIBRO ciego
                # para los pre-seeds, que es justo el caso nuevo.
                raise HTTPException(
                    status_code=400,
                    detail=f"la propuesta {id} ya no esta esperando plata")
            _eco_bus.financiar(m, bus, ts, semana, id, body.cuenta, body.mm)
        _anotar_reaccion(p0, id, "financio", body.palabras)
    except HTTPException:
        raise
    except _eco_errores_economicos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except _plantel_reacciones.ErrorReacciones as exc:
        # el financiar YA quedo asentado en el bus (la accion economica
        # terminal): un registro de reacciones corrupto no lo revierte,
        # pero tampoco puede quedar mudo -- falla cerrado con 400.
        raise HTTPException(
            status_code=400,
            detail=f"no se pudo registrar la reaccion: {exc}") from None
    return {"ok": True}


@app.post("/api/economia/bus/{id}/descartar")
def api_eco_bus_descartar(id: str, body: MesaDescartarBody) -> dict:
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
                    or _eco_bus.aportes(m.k.libro.asientos(), id)
                    or _eco_bus.aporte_preseed(m.k.libro.asientos(), id)):
                raise HTTPException(
                    status_code=400,
                    detail=f"la propuesta {id} ya no se puede descartar")
            _eco_bus.descartar(bus, ts, semana, id)
        _anotar_reaccion(p0, id, "descarto", body.palabras)
    except HTTPException:
        raise
    except _eco_errores_economicos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except _plantel_reacciones.ErrorReacciones as exc:
        # el descarte YA quedo asentado en el bus; el registro corrupto
        # falla cerrado con 400, no se lo traga en silencio.
        raise HTTPException(
            status_code=400,
            detail=f"no se pudo registrar la reaccion: {exc}") from None
    return {"ok": True}


@app.post("/api/economia/bus/{id}/no-mas")
def api_eco_bus_no_mas(id: str, body: MesaNoMasBody) -> dict:
    """Pedro dice NO MAS: descarta esta propuesta Y veta el tema. El piso lo
    lee el jefe (reacciones.esta_vetada) y no vuelve a proponer esa clave en
    este departamento. Mismo corte que descartar contra el LIBRO."""
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    ts, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            m = p0.mercado_fresco()
            bus = _eco_bus.Bus(p0.ruta_bus)
            if (bus.estado(id) != "alta"
                    or _eco_bus.aportes(m.k.libro.asientos(), id)
                    or _eco_bus.aporte_preseed(m.k.libro.asientos(), id)):
                raise HTTPException(
                    status_code=400,
                    detail=f"la propuesta {id} ya no se puede descartar")
            _eco_bus.descartar(bus, ts, semana, id)
        _anotar_reaccion(p0, id, "no_mas", body.palabras)
    except HTTPException:
        raise
    except _eco_errores_economicos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except _plantel_reacciones.ErrorReacciones as exc:
        # el descarte YA quedo asentado en el bus; el registro corrupto
        # falla cerrado con 400, no se lo traga en silencio.
        raise HTTPException(
            status_code=400,
            detail=f"no se pudo registrar la reaccion: {exc}") from None
    return {"ok": True}


def _juzgar(id: str, cumplio: bool, palabras: str) -> dict:
    """Pedro juzga si un trabajo cumplio su promesa. Reputacion, no plata:
    no toca el bus ni el libro. Falla 400 si el trabajo no esta vencido o ya
    fue juzgado. El nombre del depto va pelado del prefijo dep: (mismo motivo
    que _anotar_reaccion)."""
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    _, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            m = p0.mercado_fresco()
            bus = _eco_bus.Bus(p0.ruta_bus)
            d = bus.datos(id)
            ops = _eco_cap.semanas_operativas(m.k.libro.asientos())
            dep = d.get("departamento", "")
            nombre = dep.split(":", 1)[1] if ":" in dep else dep
            if not nombre or not _eco_bus.vencida(d, ops, semana):
                raise HTTPException(
                    status_code=400,
                    detail=f"la propuesta {id} no esta lista para juzgar")
            if _plantel_promesas.juzgada(nombre, id):
                raise HTTPException(
                    status_code=400,
                    detail=f"la propuesta {id} ya fue juzgada")
        _plantel_promesas.anotar(nombre, id, d.get("forma"), cumplio, palabras)
    except HTTPException:
        raise
    except _eco_errores_economicos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except _plantel_promesas.ErrorPromesas as exc:
        raise HTTPException(
            status_code=400,
            detail=f"no se pudo registrar el veredicto: {exc}") from None
    return {"ok": True}


@app.post("/api/economia/bus/{id}/cumplio")
def api_eco_bus_cumplio(id: str, body: MesaVeredictoBody) -> dict:
    return _juzgar(id, True, body.palabras)


@app.post("/api/economia/bus/{id}/no-cumplio")
def api_eco_bus_no_cumplio(id: str, body: MesaVeredictoBody) -> dict:
    return _juzgar(id, False, body.palabras)


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
    ts, semana_hoy = _eco_ahora()
    semana = _eco_semana_pedida(body.semana, semana_hoy)
    with _eco_candado(p0.ruta_libro):
        eco = _economia()  # fresco BAJO el candado (reentrante adentro)
        try:
            res = _eco_op.cerrar_semana_operativa(
                eco["pagador"].mercado_fresco(), eco["bus"], eco["cola"],
                ts, semana,
                presupuesto_direccion_mm=body.presupuesto_direccion_mm)
        except (_eco_op.ErrorOperacion, _eco_pt.ErrorPT) as e:
            # Salian como 500 opacos: la pantalla muestra `detail` y no
            # tenia nada que mostrar. Son las dos negativas que Pedro se
            # come al volver de un viaje, y las dos se resuelven mandando
            # la semana -- asi que el mensaje tiene que llegar entero.
            raise HTTPException(status_code=400, detail=str(e)) from None
        aplicados = eco["pagador"].reintentar_pendientes()
    return {"ok": True, "expiradas": res["expiradas"],
            "informes_ciclo": res["informes_ciclo"],
            "pendientes_aplicados": aplicados}


@app.post("/api/economia/abrir")
def api_eco_abrir(body: EcoAbrirBody) -> dict:
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    ts, semana_hoy = _eco_ahora()
    semana = _eco_semana_pedida(body.semana, semana_hoy)
    with _eco_candado(p0.ruta_libro):
        eco = _economia()  # fresco BAJO el candado
        m = eco["pagador"].mercado_fresco()
        # las suscripciones viajan porque abrir la PRIMERA semana de un
        # ciclo tambien emite su cuota de cristal (la capacidad que la
        # fabrica va a consumir en el ciclo); sin ellas el pool arranca en
        # cero y todo consumo queda estampado como descubierto
        try:
            _eco_op.abrir_semana(m.k, ts, semana,
                                 body.cuota_firmable_mpt,
                                 body.reserva_personal_mpt,
                                 suscripciones=m.suscripciones)
        except (_eco_op.ErrorOperacion, _eco_pt.ErrorPT) as e:
            raise HTTPException(status_code=400, detail=str(e)) from None
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


@app.post("/api/economia/sembrar-guiado")
def api_eco_sembrar_guiado(body: EcoSembrarGuiadoBody) -> dict:
    """Helper guiado de un solo tiro. Sin `confirmacion` -> PREVIEW (no
    escribe). Con la frase exacta -> ejecuta los 7 pasos, re-entrante. La
    siembra es un acto de Pedro; el preview es la red antes del acto
    irreversible (el padron)."""
    if _siembra is None:
        raise HTTPException(status_code=400,
                            detail="la economia no esta disponible")
    ts, semana = _eco_ahora()
    config = {
        "departamentos": [d.model_dump() for d in body.departamentos],
        "suscripciones": {n: s.model_dump()
                          for n, s in body.suscripciones.items()},
        "capital_tesoro_mm": body.capital_tesoro_mm,
        "cuota_firmable_mpt": body.cuota_firmable_mpt,
        "reserva_personal_mpt": body.reserva_personal_mpt,
        "rutina_interval_min": body.rutina_interval_min,
        "perillas_fabrica": body.perillas_fabrica.model_dump()}
    ejecutar = body.confirmacion == _siembra.CONFIRMACION
    if body.confirmacion and not ejecutar:
        raise HTTPException(
            status_code=400,
            detail=f"para ejecutar, confirmacion debe ser exactamente "
                   f"'{_siembra.CONFIRMACION}'")
    try:
        return _siembra.sembrar_guiado(str(_ECO_BASE), config, ts, semana,
                                       ejecutar=ejecutar)
    except (_eco_errores_economicos, _eco_deps.ErrorDepartamento,
            _eco_cap.ErrorCapacidad, _eco_pt.ErrorPT, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.post("/api/economia/departamentos/{nombre}/perillas")
def api_eco_departamento_perillas(nombre: str,
                                  body: PerillasDepartamentoBody) -> dict:
    """Cambiar un numero de un departamento sin editar el json a mano.

    LA RAIZ QUE ESTO DESTAPA: la configuracion de la economia era de
    ESCRITURA UNICA. `POST /api/economia/sembrar` escribe
    departamentos.json una sola vez y se niega a correr de nuevo -- con
    razon, porque el libro es append-only y sembrar dos veces no se
    deshace -- pero eso dejaba el unico camino para mover una perilla en
    "abri el json con un editor". `Registro.ajustar` ya existia y no lo
    llamaba nadie de produccion; este es su primer llamador.

    NO pasa por el motor de permisos, y es una decision, no un olvido. El
    motor existe para lo que NO SE DESHACE SOLO (permisos/motor.py, 5.2):
    un asiento acunado queda en el libro para siempre. Una perilla se
    deshace escribiendola de nuevo -- el json no es append-only -- y
    ademas no mueve un solo milimon: `techo_preseed_mm` autoriza a PEDIR,
    y todo lo que se pide sigue necesitando que Pedro toque "financiar"
    en la mesa, que es donde la plata sale de verdad y donde ya hay una
    mano humana. Meterla en el registro de permisos junto a las
    irreversibles diluiria exactamente la señal que ese registro existe
    para dar.

    Lo que SI la protege es que ningun departamento tiene boca http: el
    jefe actua por `contratar` inyectado (`_contratar_para`), que no llega
    aca. El dia que un departamento pueda llamar endpoints, subirse su
    propio techo es un rodeo y este endpoint pasa a ser consumidor del
    motor -- con `origen`/`corrida` en el cuerpo, como los de plata.
    """
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    perillas = body.model_dump(exclude_unset=True, exclude_none=True)
    if not perillas:
        raise HTTPException(
            status_code=400,
            detail="no viene ninguna perilla que cambiar")
    try:
        # escritura: candado, y el Registro construido FRESCO adentro (misma
        # regla que `bus.alta` en `_contratar_para` -- no se cachean
        # escritores entre adquisiciones del candado)
        with _eco_candado(p0.ruta_libro):
            registro = _eco_deps.Registro(p0.ruta_registro)
            if ((perillas.get("techo_preseed_mm")
                 or perillas.get("techo_preseed_ciclo_mm"))
                    and registro.obtener(nombre).zona != _eco_deps.ZONA_FABRICA):
                # un departamento personal no tiene jefe que pida ni ronda
                # pre-seed que financiar: `bus.financiar` rechaza un
                # pre-seed cuyo dueno no sea de fabrica (la zona personal se
                # financia desde cuenta_pedro, no desde el tesoro), asi que
                # esta perilla ahi seria un numero que no autoriza nada.
                raise HTTPException(
                    status_code=400,
                    detail=(f"{nombre} es un departamento personal: el techo "
                            "de pre-seed es una perilla de fabrica"))
            dep = registro.ajustar(nombre, **perillas)
    except HTTPException:
        raise
    except _eco_deps.ErrorDepartamento as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return {"ok": True, "departamento": dataclasses.asdict(dep)}


# --------------------------------------------------------------------------
# PERMISOS (spec de ojos y manos, seccion 5): el motor, y su primer
# consumidor -- las acciones de plata.
#
# Acunar 500 monedas y correr un `rm -rf` son la misma pregunta: una accion
# que no se deshace sola. Por eso el umbral de plata no es un mecanismo
# aparte sino el primer llamador de `permisos.evaluar`. Cuando se enchufen
# la terminal, los archivos y las apps, van por la misma puerta.
# --------------------------------------------------------------------------
try:
    from calipso import permisos as _permisos
    from calipso.permisos import almacen as _permisos_almacen
    from calipso.permisos import motor as _permisos_motor
except Exception:  # sin motor de permisos los endpoints lo dicen, no mienten
    _permisos = _permisos_almacen = _permisos_motor = None


class EcoPermisoResponderBody(BaseModel):
    # "si" | "si_siempre" | "no" | "no_siempre" (las cuatro salidas de 5.4)
    respuesta: str
    # una forma MAS ANCHA para la regla permanente ("escribir bajo
    # ~/Downloads" en vez de ese archivo suelto). Viaja con las dos
    # respuestas que dejan regla, pero solo la acepta `si_siempre`: tiene
    # que cubrir la accion que se esta contestando o `anotar_regla` la
    # rechaza, y con `no_siempre` la rechaza siempre -- una regla de negar
    # mas ancha que la accion bloquea sin dejar item en ninguna bandeja.
    forma: dict | None = None


class PermisoTechoBody(BaseModel):
    nombre: str = "plata_mm"
    valor: int


def _permisos_contexto(body) -> "_permisos.Contexto":
    """Quien pide, desde el cuerpo del request.

    El default es "pedro" y no el lado desatendido porque estos endpoints
    SON hoy la superficie de Pedro: los dispara el formulario de /fabrica,
    con el a un dedo del boton. Una rutina que llame por HTTP declara su
    `origen`, su `departamento` y su `corrida` y cae sola en el camino de
    5.6. Y el default no es una puerta: con origen "pedro" una accion por
    encima del techo igual queda PENDIENTE y no se ejecuta -- nadie se
    auto-aprueba, solo cambia si el pedido espera en un prompt o se
    estaciona.
    """
    return _permisos.Contexto(
        origen=getattr(body, "origen", None) or "pedro",
        chat=getattr(body, "chat", None),
        departamento=getattr(body, "departamento", None),
        corrida=getattr(body, "corrida", None))


def _permisos_puerta(accion, body) -> None:
    """Pasa por el motor, o corta el request.

    Corta con 409 y no con 202 a proposito. 202 es el codigo semanticamente
    correcto para "aceptado, todavia no hecho", pero la UI que ya existe
    (`calipso/web/fabrica/app.js`) trata cualquier `r.ok` como exito y le
    dice a Pedro "listo: se pusieron 500 monedas en el tesoro". Decirle que
    la plata entro cuando no entro es peor que un codigo menos elegante, y
    la tira de 5.9 -- que es la que va a leer el cuerpo estructurado -- se
    construye despues. Con 409, la UI de hoy muestra el `detail`, que dice
    exactamente que paso y con que id.
    """
    if _permisos is None:
        raise HTTPException(
            status_code=503,
            detail="el motor de permisos no esta disponible en este build")
    res = _permisos.evaluar(accion, _permisos_contexto(body))
    if res.permitido:
        return
    if res.estado == _permisos.ESTADO_NEGADO:
        raise HTTPException(status_code=403, detail=res.motivo)
    sol = res.solicitud or {}
    raise HTTPException(
        status_code=409,
        detail=(f"{res.estado}: {sol.get('texto') or accion.titulo}. "
                f"{res.motivo}. Contestala en /api/permisos "
                f"(solicitud {sol.get('id')})"))


def _eco_movimiento_ahora(tipo: str, monto_mm: int, categoria: str,
                          nota: str) -> dict:
    """El movimiento en si, sin permisos: lo llama el endpoint cuando el
    motor deja pasar, y el ejecutor cuando Pedro contesta que si."""
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    ts, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            eco = _economia()  # fresco BAJO el candado
            eco["personal"].registrar(
                ts, semana, _ECO_PERSONAL_TIPO_SINONIMOS.get(tipo, tipo),
                monto_mm, categoria, nota=nota)
    except _eco_personal.ErrorPersonal as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"ok": True}


def _eco_acunar_ahora(subtipo: str, destino: str, monto_mm: int,
                      evidencia: dict, detalle_extra: dict | None) -> dict:
    """La acunacion en si, ya validada por el endpoint. Misma separacion
    que el movimiento: la validacion de forma corre ANTES de pedir permiso
    (no tiene sentido estacionar un pedido invalido y hacer que Pedro lo
    apruebe para que despues falle), y esto es solo la escritura."""
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    ts, semana = _eco_ahora()
    try:
        with _eco_candado(p0.ruta_libro):
            if subtipo == "venta" and destino.startswith("trabajo:"):
                id_trabajo = destino.split(":", 1)[1]
                if id_trabajo not in _eco_bus.Bus(p0.ruta_bus).activas():
                    raise HTTPException(
                        status_code=400,
                        detail=f"trabajo no vivo: {destino}")
                detalle_extra = {**(detalle_extra or {}),
                                 "trabajo": id_trabajo}
            asiento = p0.leer_kernel().acunar(
                ts, semana, destino, monto_mm,
                _eco_tipos.SubtipoAcunacion(subtipo), evidencia,
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


def _ejecutor_movimiento(a) -> dict:
    return _eco_movimiento_ahora(a.forma["tipo"], a.forma["monto_mm"],
                                 a.forma["categoria"],
                                 a.detalle.get("nota", ""))


def _ejecutor_acunar(a) -> dict:
    return _eco_acunar_ahora(a.forma["subtipo"], a.forma["destino"],
                             a.forma["monto_mm"],
                             a.detalle.get("evidencia") or {},
                             a.detalle.get("detalle_extra"))


if _permisos_motor is not None:
    # el contrato de enchufe: la respuesta de Pedro tiene que poder
    # COMPLETAR la accion, no solo autorizarla, porque quien la pidio ya
    # se volvio con un 409.
    _permisos_motor.registrar_ejecutor("plata", "movimiento",
                                       _ejecutor_movimiento)
    _permisos_motor.registrar_ejecutor("plata", "acunar", _ejecutor_acunar)


@app.get("/api/permisos")
def api_permisos() -> dict:
    """La tira de 5.9: prompts pendientes, solicitudes estacionadas de los
    departamentos, y los permisos permanentes con su id para revocar.

    Endpoint propio y no el bus ni la cola: una propuesta del bus y una
    carta de la cola son objetos economicos -- con escrow, con asientos, y
    su atencion la lee `cerrar_ciclo` -- y un permiso no lo es. Meterlo ahi
    convertiria el libro contable en un log de permisos."""
    if _permisos is None:
        return {"activo": False}
    return {"activo": True, **_permisos.vista()}


@app.post("/api/permisos/solicitudes/{id_solicitud}/responder")
def api_permisos_responder(id_solicitud: str,
                           body: EcoPermisoResponderBody) -> dict:
    """Las cuatro salidas de 5.4. El modelo puede PEDIR; conceder es de
    Pedro, siempre, y este endpoint es el unico camino que escribe un
    permiso permanente."""
    if _permisos is None:
        raise HTTPException(status_code=503,
                            detail="el motor de permisos no esta disponible")
    try:
        return _permisos_motor.responder(id_solicitud, body.respuesta,
                                         quien="pedro",
                                         forma_permanente=body.forma)
    except _permisos.ErrorPermisos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.post("/api/permisos/concedidos/{id_permiso}/revocar")
def api_permisos_revocar(id_permiso: str) -> dict:
    if _permisos is None:
        raise HTTPException(status_code=503,
                            detail="el motor de permisos no esta disponible")
    if not _permisos_almacen.revocar(id_permiso):
        raise HTTPException(status_code=404,
                            detail=f"no hay permiso {id_permiso}")
    return {"ok": True}


@app.post("/api/permisos/techo")
def api_permisos_techo(body: PermisoTechoBody) -> dict:
    """El techo de plata, configurable y no una constante escondida. En
    milimonedas: 100.000 mm = 100 monedas, que es donde Pedro lo puso."""
    if _permisos is None:
        raise HTTPException(status_code=503,
                            detail="el motor de permisos no esta disponible")
    try:
        return {"ok": True,
                "techos": _permisos_almacen.poner_techo(body.nombre,
                                                        body.valor)}
    except _permisos.ErrorPermisos as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@app.get("/api/economia/config")
def api_eco_config() -> dict:
    """La configuracion editable de la economia, y el numero medido al lado.

    Un solo GET para las dos superficies nuevas porque las dos viven en la
    misma pantalla (la sub-pestana "Plata" de la mesa) y ninguna de las dos
    justifica un endpoint propio: son la MISMA pregunta -- "que numeros
    tiene puesta la economia hoy y cuales habria que corregir".

    Las perillas de cada departamento (que hasta hoy solo se veian abriendo
    departamentos.json) mas cada suscripcion con lo que el probe pasivo de
    `calipso/consumo.py` propone para su `capacidad_ciclo`. El probe se LEE,
    no se corre: `consumo.cargar_resumen` abre la foto que ya dejo la rutina
    "consumo"; correr `resumen()` aca convertiria un GET en una escritura y
    un barrido de ~200 MB de jsonl.

    `medido` puede ser None de tres formas distintas y todas son normales:
    sin foto todavia (la rutina no corrio), sin proveedor que corresponda a
    esa suscripcion, o con proveedor pero sin suficiente historia para
    proponer nada. La pantalla las distingue; este endpoint no las disfraza
    de cero.
    """
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        return {"activa": False}
    _, semana = _eco_ahora()
    with _eco_candado(p0.ruta_libro):
        m = p0.mercado_fresco()
        asientos = m.k.libro.asientos()
        deps_objeto = m.registro.todos()
        departamentos = [dataclasses.asdict(d) for d in deps_objeto]
        suscripciones = dict(m.suscripciones)
        # lo pedido y todavia en la mesa, por departamento. Va ACA, con el
        # candado tomado, por la misma razon que el resto de los lectores
        # de economia: el bus se lee entero de una.
        #
        # Y al lado, CUANTAS propuestas en pie tiene cada uno: es el otro
        # freno que deja mudo a un departamento (`TECHO_PROPUESTAS` en
        # `jefe._puede`, el de "que Pedro despeje antes de sumar otra") y
        # hasta hoy no se veia en ninguna pantalla. Se cuentan las de los
        # DOS tipos, igual que `situacion.propuestas_propias`, porque el
        # techo que miran es el mismo.
        ops_bus = _eco_cap.semanas_operativas(asientos)
        pendiente_por_cuenta: dict[str, int] = {}
        propias_por_cuenta: dict[str, int] = {}
        bus_config = _eco_bus.Bus(p0.ruta_bus)
        for id_ in bus_config.ids():
            if bus_config.estado(id_) != "alta":
                continue
            d_ = bus_config.datos(id_)
            # un pre-seed vencido no cuenta para ninguno de los dos: no se
            # puede financiar, no reserva cupo y no ocupa bandeja. Misma
            # funcion que `situacion` y que `bus.financiar`.
            if _eco_bus.preseed_vencido(d_, ops_bus, semana):
                continue
            cuenta_ = d_.get("departamento", "")
            propias_por_cuenta[cuenta_] = propias_por_cuenta.get(cuenta_, 0) + 1
            if d_.get("tipo") != "preseed":
                continue
            pendiente_por_cuenta[cuenta_] = (
                pendiente_por_cuenta.get(cuenta_, 0)
                + d_.get("presupuesto_mm", 0))
    ops = _eco_cap.semanas_operativas(asientos)
    ciclo = None
    if ops and semana in ops:
        ciclo, _fraccion = _eco_cap.posicion_ciclo(semana, ops)
    # el ciclo se informa solo cuando la semana ya emitio su PT (`ciclo`
    # nombra una posicion real); el CONSUMIDO de mas abajo no espera al
    # boton y por eso lo pliega `_eco_consumido_ciclo`, que es la misma
    # cuenta que hace el guardia de POST .../capacidad.
    #
    # la OTRA ventana, la del caudal de capital: el techo acumulado de
    # pre-seed se mide sobre las ultimas `VENTANA_PRESEED_SEMANAS` semanas
    # operativas, deslizante, y NO sobre el ciclo de facturacion de arriba
    # (que es el que sigue rigiendo el consumido de las suscripciones). Con
    # el ciclo, el acumulado se reseteaba de golpe en la quinta semana y el
    # techo entero entraba dos veces en dos semanas de calendario seguidas.
    # Ver `bus.ventana_preseed`.
    semanas_ventana = _eco_bus.ventana_preseed(ops, semana)
    # el acumulado de pre-seed de la ventana, al lado de su techo. Es la
    # mitad que faltaba: la mesa muestra cada pedido suelto y ninguna
    # pantalla decia cuanto capital ya entro, asi que el techo seria un
    # numero que Pedro pone a ciegas y un rechazo que le llega recien al
    # tocar "financiar". Se pliega del LIBRO, igual que el freno.
    for dep, fila in zip(deps_objeto, departamentos):
        fila["preseed_ventana_mm"] = _eco_bus.preseed_en_ventana(
            asientos, dep.cuenta, semanas_ventana)
        # y cuanto cupo devuelve la proxima rodada, con el nombre de la
        # semana que sale. Es lo que la ventana deslizante permite decir y
        # la fija no podia: ahi el cupo volvia entero, de golpe y sin
        # ninguna senal de que la ventana acababa de rodar.
        (fila["preseed_libera_al_salir"],
         fila["preseed_libera_mm"]) = _eco_bus.libera_preseed(
            asientos, dep.cuenta, ops, semana)
        # y al lado, lo PEDIDO que sigue en la mesa. Los dos numeros no
        # son el mismo y la pantalla los decia como si lo fueran: el
        # acumulado de arriba es lo que Pedro ya financio (el unico que
        # mira `bus.financiar`), y este es la reserva que `jefe._puede` le
        # suma para no publicar lo que no se le va a poder pagar. Sin
        # este, un pedido olvidado en la mesa deja al jefe mudo con el
        # acumulado de la ventana a la vista en CERO -- y nada en la pantalla
        # sugiere que lo que lo suelta es descartarlo.
        fila["preseed_pendiente_mm"] = pendiente_por_cuenta.get(
            dep.cuenta, 0)
        # y las dos piezas que faltaban para poder DECIR por que un
        # departamento esta callado, en vez de dejar a Pedro deduciendolo de
        # cuatro numeros sueltos. `disponible_mm` es el primer freno del
        # pre-seed ("ya tiene lo que una ronda le daria") y hasta hoy no
        # viajaba; `propuestas_propias` es el otro freno que lo deja mudo
        # (TECHO_PROPUESTAS, "que Pedro despeje antes de sumar otra") y
        # tampoco.
        fila["disponible_mm"] = _eco_balances.disponible(
            asientos, dep.cuenta, _eco_tipos.Divisa.MONEDA)
        fila["propuestas_propias"] = propias_por_cuenta.get(dep.cuenta, 0)
        # y el freno mismo, en palabras: el MISMO texto que recibio el jefe,
        # producido por la misma funcion (`jefe.freno_preseed`) sobre las
        # mismas claves. Reescribirlo en la pantalla seria una segunda
        # fuente de verdad sobre cuatro frenos, y ese es exactamente el error
        # que este techo ya cometio dos veces. None cuando puede pedir.
        #
        # Solo para la zona FABRICA: un departamento personal no pide
        # pre-seed (`bus.financiar` lo corta por zona y `Departamento`
        # rechaza la perilla), asi que su techo es cero por construccion y
        # `freno_preseed` contestaria "Pedro todavia no autorizo" -- un
        # freno de mentira sobre algo que ese departamento nunca hace.
        # `bloquePreseed` ya filtra por zona y no lo pintaria, pero el dato
        # tiene que ser cierto igual: la pantalla no es la unica que puede
        # leerlo.
        fila["freno_pedir"] = (
            _plantel_jefe.freno_preseed(fila)
            if _plantel_jefe and dep.zona == _eco_deps.ZONA_FABRICA else None)
        # y de que CLASE es ese freno, que decide como se pinta. Un
        # departamento recien dado de alta tiene las dos perillas de
        # pre-seed en cero -- `techo_preseed_mm` nace en cero-- y el freno
        # contesta "Pedro todavia no autorizo": eso no es algo trabado, es
        # el estado por defecto, y pintarlo en --acento con la barra al
        # costado le estrenaba a cada departamento nuevo un aviso rojo
        # permanente. Un renglon rojo que esta siempre se vuelve invisible
        # igual de rapido que uno verde, y despues el que si importa
        # aparece al lado de uno que Pedro ya aprendio a ignorar. Sale de
        # la misma escalera que el texto (`jefe.preseed_sin_autorizar`) y
        # no de releer las perillas por afuera: con el techo por pedido
        # puesto y el de la ventana en cero, el freno que gana puede ser el
        # de la billetera, que si es de verdad.
        fila["freno_pedir_sin_autorizar"] = bool(
            _plantel_jefe and dep.zona == _eco_deps.ZONA_FABRICA
            and _plantel_jefe.preseed_sin_autorizar(fila))
    resumen = calipso_consumo.cargar_resumen() or {}
    filas = []
    for nombre, sus in sorted(suscripciones.items()):
        filas.append({
            **dataclasses.asdict(sus),
            "capacidad_fabrica": sus.capacidad_fabrica,
            "precio_base_mm": sus.precio_base_mm,
            # lo ya consumido en el ciclo en curso: es el piso por debajo
            # del cual bajar la capacidad deja la cuota agotada hasta que
            # el ciclo termine (ver el guardia de POST .../capacidad)
            "consumido_ciclo": _eco_consumido_ciclo(asientos, nombre, semana),
            "medido": _eco_capacidad_medida(resumen, nombre),
        })
    return {"activa": True, "semana": semana, "ciclo": ciclo,
            "departamentos": departamentos, "suscripciones": filas,
            # el largo de la ventana del pre-seed viaja al cliente para que
            # la pantalla no escriba un "4" propio: seria una segunda fuente
            # de verdad sobre el mismo techo, y el dia que se mueva la
            # constante la pantalla mentiria sin que nada falle.
            "preseed_ventana_semanas": _eco_bus.VENTANA_PRESEED_SEMANAS,
            # y al lado, CUANTAS etiquetas de semana se sumaron de verdad
            # para el acumulado de arriba. No son el mismo numero y la
            # pantalla los decia con uno solo: la REGLA es "en ninguna
            # corrida de 4 semanas operativas entra mas que el techo" (la
            # constante), pero `ventana_preseed` mete la semana de hoy
            # SIEMPRE, este abierta o no, asi que mientras el lunes no se
            # abre el tramo que se suma son cinco etiquetas
            # (`previas[-4:] + [hoy]`) -- y toda semana empieza sin abrir,
            # que es el estado por defecto de cada lunes, no una ventana
            # rara. Va en la direccion segura (aprieta, nunca afloja, y eso
            # es a proposito: ver el docstring de `ventana_preseed`), pero
            # rotulado con el 4 el numero que Pedro lee al lado del techo no
            # era la suma de lo que el renglon decia que sumaba. Dos hechos
            # distintos, una sola fuente de verdad cada uno.
            "preseed_ventana_sumadas": len(semanas_ventana),
            # y el techo de propuestas en pie, por la misma razon que el
            # largo de la ventana viaja: la pantalla dice "N de M en la
            # mesa" y M es `jefe.TECHO_PROPUESTAS`. Escribir un 3 propio
            # alla seria una segunda fuente de verdad sobre el freno.
            "techo_propuestas": (_plantel_jefe.TECHO_PROPUESTAS
                                 if _plantel_jefe else None),
            "medido_generado": resumen.get("generado")}


def _eco_capacidad_medida(resumen: dict, nombre: str) -> dict | None:
    """Lo que el probe propone para ESA suscripcion, o None.

    La traduccion proveedor -> suscripcion sale de
    `pagador.SUSCRIPCION_POR_CLIENTE` ("claude" -> "claude_max", "codex" ->
    "chatgpt_plus"), que es la MISMA tabla con la que dispatch decide a que
    suscripcion cobrarle un turno. Escribirla de nuevo aca dejaria dos
    lugares donde el mapeo puede discrepar, y el sintoma seria el peor
    posible: medir una suscripcion y aplicarselo a otra.

    Se devuelve la `nota` del probe tal cual. Es lo que separa una
    medicion de una extrapolacion (Codex expone `used_percent` real,
    Claude no expone ningun porcentaje) y esconderla dejaria a Pedro
    aplicando dos numeros que no valen lo mismo como si valieran igual.
    """
    for cliente, suscripcion in sorted(_ECO_SUS_POR_CLIENTE.items()):
        if suscripcion != nombre:
            continue
        prov = resumen.get(cliente) or {}
        inf = prov.get("inferencia") or {}
        return {"proveedor": cliente,
                "capacidad_ciclo_propuesta": inf.get(
                    "capacidad_ciclo_propuesta"),
                "nota": inf.get("nota") or prov.get("nota") or "",
                "medicion": prov.get("medicion")}
    return None


def _eco_semanas_del_ciclo_de_hoy(asientos: list, semana: str) -> list[str]:
    """Las semanas operativas del ciclo en el que cae HOY, este la semana
    de hoy ya emitida o no.

    La aritmetica vive en `capacidad.semanas_del_ciclo_de_hoy` y su
    docstring explica por que hace falta (toda semana empieza afuera de
    las operativas hasta que Pedro aprieta el boton de abrir). Se movio
    para alla porque la MISMA pregunta la hace tambien `plantel.situacion`
    -- el gasto de API del jefe --, y dos respuestas distintas a "en que
    ciclo estoy" serian dos techos. Esto queda como el nombre que ya usan
    los llamadores de este modulo.

    Lo que NO la hace es `bus.financiar`: el techo de pre-seed acumulado
    se mide sobre `bus.ventana_preseed`, que es deslizante y no el ciclo.
    """
    return _eco_cap.semanas_del_ciclo_de_hoy(
        _eco_cap.semanas_operativas(asientos), semana)


def _eco_consumido_ciclo(asientos: list, nombre: str, semana: str) -> int:
    """Lo que la fabrica ya consumio de la cuota del ciclo en curso.

    Un solo lugar para los dos lectores de este modulo —el numero que la
    pantalla le muestra a Pedro como piso, y el guardia de
    POST .../capacidad que lo hace cumplir— porque son el MISMO numero: si
    difirieran, la pantalla invitaria a aplicar una capacidad que el
    guardia despues rechaza.

    Pliega por el ciclo ESTAMPADO en el consumo y no por la semana (ver
    `capacidad.consumo_fabrica_ciclo`): consumir dejo de esperar al boton
    de abrir, asi que el consumo de la semana en curso —que es el estado
    por defecto de cada lunes— no cae en las semanas de ningun ciclo.
    """
    ops = _eco_cap.semanas_operativas(asientos)
    return _eco_cap.consumo_fabrica_ciclo(
        asientos, nombre, _eco_cap.ciclo_de_hoy(ops, semana),
        _eco_cap.semanas_del_ciclo_de_hoy(ops, semana))


def _eco_capacidad_preparar(nombre: str, capacidad_ciclo: int,
                            reserva_personal: int | None) -> dict:
    """Valida el cambio contra las invariantes y contra el ciclo en curso.

    Corre ANTES de pedir permiso, por la misma razon que
    `_eco_acunar_ahora`: no tiene sentido estacionar un pedido invalido y
    hacer que Pedro lo apruebe para que despues falle.

    Tres puertas, y ninguna es la misma:

    1. `Suscripcion.__post_init__` -- entero positivo y
       `0 <= reserva_personal < capacidad_ciclo`. Las dos claves estan
       ACOPLADAS: bajar la capacidad por debajo de la reserva que ya
       estaba puesta invalida la suscripcion, asi que el error lo dice con
       las dos y no con una.

    2. El ciclo EN CURSO. `mercado.consumir_capacidad` corta con "cuota
       agotada" cuando `consumido + unidades > capacidad_fabrica`, y
       `consumido` se pliega del libro (asientos ya escritos, que no se
       reescriben) por el CICLO ESTAMPADO, no por semana: ver
       `capacidad.consumo_fabrica_ciclo`. Bajar `capacidad_fabrica` por
       debajo de lo que este ciclo YA consumio deja a la fabrica sin poder
       consumir una sola unidad mas hasta que el ciclo termine -- y de paso
       manda
       `precio_unidad_mm` al tope, porque divide por `capacidad_fabrica`.
       Eso no es un numero corregido, es la fabrica apagada por cuatro
       semanas. Se corta aca y se dice cuando se puede.

       Y el "ciclo en curso" NO es "la semana de hoy si ya la abrieron":
       una semana se vuelve operativa recien cuando alguien emite su PT a
       mano, asi que hasta ese boton `semana not in ops` -- el estado por
       defecto de cada lunes. Mirar el consumo solo en ese caso dejaba
       pasar el lunes exactamente el cambio que el jueves daba 409, y la
       semana, una vez emitida, cae en el MISMO ciclo. Ver
       `_eco_semanas_del_ciclo_de_hoy`.

    3. El TECHO. `capacidad_ciclo` tenia piso (`ge=1`) y este guardia hacia
       abajo, y nada hacia arriba: un numero de mas apagaba el precio por
       escasez sin preguntarle a nadie. El dominio da un solo techo no
       inventado -- que el precio por unidad no caiga por debajo del
       milimon -- y es el que se aplica.
    """
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    _, semana = _eco_ahora()
    with _eco_candado(p0.ruta_libro):
        m = p0.mercado_fresco()
        asientos = m.k.libro.asientos()
        suscripciones = dict(m.suscripciones)
    if nombre not in suscripciones:
        raise HTTPException(status_code=404,
                            detail=f"suscripcion desconocida: {nombre}")
    vieja = suscripciones[nombre]
    reserva = (vieja.reserva_personal if reserva_personal is None
               else reserva_personal)
    try:
        nueva = dataclasses.replace(vieja, capacidad_ciclo=capacidad_ciclo,
                                    reserva_personal=reserva)
    except _eco_cap.ErrorCapacidad as exc:
        raise HTTPException(
            status_code=400,
            detail=(f"{exc}. capacidad_ciclo y reserva_personal se mueven "
                    f"juntas: la reserva de hoy es {vieja.reserva_personal} "
                    f"y tiene que quedar dentro de [0, {capacidad_ciclo}) "
                    "-- manda las dos claves en el mismo pedido")) from None
    # el precio por unidad no puede caer por debajo del milimon: pasado ese
    # punto `precio_base_mm` (= `max(1, costo_fabrica_mm //
    # capacidad_fabrica)`) no lo fija la division sino el `max`, y el
    # mercado deja de medir escasez. La fabrica compra a 1 mm capacidad que
    # el plan no rinde, cada compra queda estampada en el libro
    # append-only con ese precio, y el guardia de abajo despues impide
    # volver atras hasta que el ciclo cierre. Es el unico techo que el
    # dominio da solo: el numero que llega puede venir del probe
    # (`capacidad_ciclo_propuesta`, una division por un `used_percent` que a
    # principio de ventana es arbitrariamente chico), y hasta aca entraba
    # sin que nada lo comparara contra nada.
    if nueva.capacidad_fabrica > nueva.costo_fabrica_mm:
        raise HTTPException(
            status_code=400,
            detail=(f"capacidad_ciclo {capacidad_ciclo} deja "
                    f"{nueva.capacidad_fabrica} unidades para la fabrica y "
                    f"el plan cuesta {nueva.costo_fabrica_mm} mm por ciclo: "
                    "cada unidad saldria menos de un milimon y el precio "
                    "dejaria de medir escasez. El techo es una unidad por "
                    "milimon de costo"))
    consumido = _eco_consumido_ciclo(asientos, nombre, semana)
    if consumido > nueva.capacidad_fabrica:
        raise HTTPException(
            status_code=409,
            detail=(f"este ciclo ya compro {consumido} unidades de {nombre} "
                    f"y la capacidad nueva deja {nueva.capacidad_fabrica} "
                    "para la fabrica: aplicarlo ahora deja la cuota agotada "
                    "hasta que el ciclo cierre. Aplicalo al empezar el "
                    "ciclo siguiente, o dejalo en un numero por encima de "
                    "lo ya consumido"))
    return {"vieja": vieja, "nueva": nueva, "consumido": consumido}


def _eco_capacidad_ahora(nombre: str, capacidad_ciclo: int,
                         reserva_personal: int | None) -> dict:
    """La escritura en si, ya con el permiso resuelto.

    Re-valida en vez de confiar en lo que decidio el endpoint: entre las
    dos puede haber pasado un cierre de ciclo, una compra de capacidad o
    -- en el camino largo, el del prompt -- todo el tiempo que Pedro tardo
    en contestar. Misma separacion que `_eco_movimiento_ahora` y
    `_eco_acunar_ahora`.

    Y el candado ENVUELVE la validacion junto con la escritura, no solo la
    escritura: el candado es reentrante (candado.py), asi que
    `_eco_capacidad_preparar` lo vuelve a tomar adentro sin trabarse, y
    entre "esto es valido" y "esto queda escrito" no se cuela una compra
    de capacidad que deje el numero nuevo por debajo de lo ya consumido.

    Escribe suscripciones.json entero: es la unica forma que tiene el
    archivo (`pagador.mercado_fresco` lo lee como un dict completo), y el
    resto queda intacto porque las otras suscripciones se vuelven a
    serializar tal como se leyeron.
    """
    p0 = _EcoPagador.desde_entorno(_ECO_BASE) if _EcoPagador else None
    if not p0:
        raise HTTPException(status_code=400, detail="la economia no esta activa")
    with _eco_candado(p0.ruta_libro):
        datos = _eco_capacidad_preparar(nombre, capacidad_ciclo,
                                        reserva_personal)
        suscripciones = dict(p0.mercado_fresco().suscripciones)
        suscripciones[nombre] = datos["nueva"]
        # ATOMICO, no `write_text`: `write_text` trunca en el lugar, asi que
        # una escritura cortada a la mitad (disco lleno, kill) deja
        # suscripciones.json invalido y con eso la economia entera sin
        # cargar -- y el unico arreglo seria abrir el archivo con un editor,
        # justo lo que este endpoint vino a eliminar. Ver
        # `candado.escribir_json_atomico`.
        _eco_escribir_json(p0.ruta_sus,
                           {n: dataclasses.asdict(s)
                            for n, s in suscripciones.items()})
    nueva = datos["nueva"]
    return {"ok": True, "suscripcion": dataclasses.asdict(nueva),
            "precio_base_mm": nueva.precio_base_mm,
            "precio_base_mm_anterior": datos["vieja"].precio_base_mm}


def _ejecutor_capacidad(a) -> dict:
    return _eco_capacidad_ahora(a.forma["suscripcion"],
                                a.forma["capacidad_ciclo"],
                                a.forma["reserva_personal"])


if _permisos_motor is not None:
    # el tercer consumidor del motor, registrado ACA y no arriba con los
    # otros dos porque `_ejecutor_capacidad` se define en este bloque.
    # Sin ejecutor, un "si" de Pedro autorizaria el cambio sin aplicarlo, y
    # quien lo pidio ya se volvio con un 409.
    _permisos_motor.registrar_ejecutor("plata", "capacidad",
                                       _ejecutor_capacidad)


@app.post("/api/economia/suscripciones/{nombre}/capacidad")
def api_eco_suscripcion_capacidad(nombre: str,
                                  body: SuscripcionCapacidadBody) -> dict:
    """Aplicar el `capacidad_ciclo` medido, sin editar suscripciones.json.

    LA RAIZ: `POST /api/economia/sembrar` escribe suscripciones.json una
    sola vez, con un default de 1.000 que el propio codigo marca
    "ESTIMACION A AJUSTAR". El probe pasivo (`calipso/consumo.py`) mide el
    uso real y propone un numero, y hasta ahora no habia forma de
    aplicarlo que no fuera un editor de texto.

    SI PASA POR EL MOTOR DE PERMISOS, al reves que las perillas de un
    departamento, y la diferencia es exactamente el criterio del motor:
    que no se deshaga solo.

    Una perilla de departamento se deshace escribiendola de nuevo. Esto no.
    `capacidad_ciclo` es el DENOMINADOR del precio de la capacidad
    (`Suscripcion.precio_base_mm` = costo_fabrica / capacidad_fabrica), y
    el precio es lo que se estampa en cada compra que el mercado escribe
    en el libro -- que es append-only. Volver el numero a su valor viejo no
    reprecia esas compras: quedan para siempre. Y el precio no se queda
    quieto ahi: alimenta `precio_unidad_mm`, que alimenta
    `decision.sesgo_efectivo`, que inclina la proxima decision de cada
    jefe. Un numero mal aplicado no es un campo mal escrito, es una serie
    de asientos y de decisiones que ya pasaron.

    Va como familia "plata" y no como una familia nueva porque es
    literalmente una accion de plata: cambia a cuanto se cobra algo. El
    monto que se compara contra el techo es el `costo_mensual_mm` de la
    suscripcion -- lo que Pedro paga por mes por la capacidad que se esta
    repreciando. No es un monto inventado para tener uno: es el numero que
    esta arriba y abajo de la division que se esta cambiando.

    LO QUE ESTO NO ARREGLA, y hay que decirlo: los pliegues que comparan
    CICLOS ENTRE SI. `cristal` estampa el split en cada emision
    (`detalle["capacidad"]`/`["reserva"]`), asi que sus lecturas por ciclo
    siguen siendo honestas despues del cambio. `capacidad.py` no estampa
    nada: `precio_unidad_mm` y `situacion._capacidad` leen SIEMPRE la
    configuracion de hoy, asi que "cuanto de su cuota uso el ciclo 0" se
    responde con la capacidad de hoy y no con la que ese ciclo tenia. Los
    asientos viejos no cambian; la lectura de los ciclos viejos si. El
    guardia de abajo evita el dano dentro del ciclo EN CURSO y el color de
    los ciclos ya cerrados lo protege `cierre._rojo_de_ciclo`, que desde
    este cambio lee el color ESTAMPADO al cerrar en vez de recalcularlo con
    la configuracion de hoy.

    Y un rebote que `cristal` si tiene, para el dia que el pagador lo
    enchufe (hoy no tiene ningun llamador de produccion): `emitir_ciclo`
    estampa el split en la emision y exige el MISMO split al re-emitir, asi
    que si una emision quedo cortada entre los dos pools -- capacidad
    emitida, reserva no -- y en el medio se reprecia, la re-llamada rebota
    con "ya iniciado con otro split" (cristal.py). No se pierde nada: hay
    que terminar la emision con el split viejo antes de aplicar el nuevo.
    """
    if _permisos is None:
        raise HTTPException(
            status_code=503,
            detail="el motor de permisos no esta disponible en este build")
    # la forma se valida ANTES de pedir permiso
    datos = _eco_capacidad_preparar(nombre, body.capacidad_ciclo,
                                    body.reserva_personal)
    vieja, nueva = datos["vieja"], datos["nueva"]
    accion = _permisos.Accion(
        familia="plata", operacion="capacidad",
        forma={"suscripcion": nombre,
               "capacidad_ciclo": nueva.capacidad_ciclo,
               "reserva_personal": nueva.reserva_personal},
        # `monto_mm` va en el detalle y no en la forma: es lo que
        # `_clasificar_plata` compara contra el techo, pero no es parte de
        # la IDENTIDAD del cambio (dos pedidos iguales no se distinguen por
        # el costo de la suscripcion). `Accion.clave` solo mira la forma.
        detalle={"monto_mm": vieja.costo_mensual_mm,
                 "capacidad_ciclo_anterior": vieja.capacidad_ciclo,
                 "reserva_personal_anterior": vieja.reserva_personal,
                 "precio_base_mm_anterior": vieja.precio_base_mm,
                 "precio_base_mm_nuevo": nueva.precio_base_mm},
        titulo=(f"repreciar la capacidad de {nombre}: "
                f"{vieja.capacidad_ciclo} -> {nueva.capacidad_ciclo} "
                f"unidades por ciclo (la unidad pasa de "
                f"{vieja.precio_base_mm} a {nueva.precio_base_mm} mm)"))
    _permisos_puerta(accion, body)
    return _eco_capacidad_ahora(nombre, body.capacidad_ciclo,
                                body.reserva_personal)


@app.post("/api/economia/personal/movimiento")
def api_eco_personal_movimiento(body: EcoPersonalMovimientoBody) -> dict:
    """El banco de Pedro (spec 8.4): un ingreso o un egreso SUYO, en
    personal.jsonl. Nunca acuna, nunca toca el libro de la fabrica --
    LibroPersonal.registrar ni siquiera abre el Kernel -- asi que la
    invariante 11 (los libros personales son privados) no se toca.

    Pasa por el motor de permisos: por debajo del techo de plata se
    registra solo, por encima queda esperando la respuesta de Pedro.
    """
    accion = _permisos.Accion(
        familia="plata", operacion="movimiento",
        forma={"tipo": body.tipo, "monto_mm": body.monto_mm,
               "categoria": body.categoria},
        detalle={"nota": body.nota},
        titulo=f"registrar un {body.tipo} de {body.monto_mm} mm en "
               f"{body.categoria}") if _permisos else None
    _permisos_puerta(accion, body)
    return _eco_movimiento_ahora(body.tipo, body.monto_mm, body.categoria,
                                 body.nota)


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

    # el motor de permisos va DESPUES de las reglas taxativas y ANTES de
    # abrir el libro: estacionar un pedido invalido haria que Pedro apruebe
    # algo que despues falla, y el prompt tiene que mostrar exactamente lo
    # que va a pasar si dice que si.
    accion = _permisos.Accion(
        familia="plata", operacion="acunar",
        forma={"subtipo": body.subtipo, "destino": body.destino,
               "monto_mm": body.monto_mm, "proyecto": body.proyecto},
        detalle={"evidencia": body.evidencia,
                 "detalle_extra": detalle_extra},
        titulo=f"acunar {body.monto_mm} mm ({body.subtipo}) a "
               f"{body.destino}") if _permisos else None
    _permisos_puerta(accion, body)
    return _eco_acunar_ahora(body.subtipo, body.destino, body.monto_mm,
                             body.evidencia, detalle_extra)


# El plantel tiene su PROPIO try/except, separado del bloque MAPA de abajo:
# un fallo importando calipso.plantel no puede caer en el mismo except que
# _mapa_ficha, porque _cobrar_turno corta en seco y cobra 0 cuando
# _mapa_ficha is None. Antes de esto, romper el plantel dejaba el chat
# entero cobrando en silencio a nadie.
try:
    from calipso.plantel import ficha as _plantel_ficha
    from calipso.plantel import ilegibles as _plantel_ilegibles
    from calipso.plantel import interruptor as _plantel_it
    from calipso.plantel import jefe as _plantel_jefe
    from calipso.plantel import promesas as _plantel_promesas  # noqa: E402
    from calipso.plantel import reacciones as _plantel_reacciones  # noqa: E402
except Exception:  # el plantel no esta disponible: el tablero responde inactivo
    _plantel_ficha = None
    _plantel_ilegibles = None
    _plantel_it = _plantel_jefe = None
    _plantel_promesas = None
    _plantel_reacciones = None


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

    OJO: NO se usa `_chunks_for("local", ...)`. Esa es la ruta "local" del
    chat, un generador que transmite por WebSocket; este helper es sincrono
    (el tic de decision del jefe necesita un string entero, no un stream),
    asi que habla con Ollama directo por `dispatch.CONFIG["local"]`. Desde
    la Fase 1 del ruteo, la ruta "local" del chat TAMBIEN corre Ollama (o
    falla cerrado): las dos son gratis. Antes no -- la ruta "local"
    ejecutaba `claude -p` (el viejo `_local_via_sub`, ya borrado) y decidir
    por ahi habria costado una unidad de suscripcion por tic y por
    departamento. La razon de mantenerlos separados hoy es la forma de la
    llamada (sincrona vs stream), no el costo, y "decidir es gratis" pasa a
    ser verdad por los dos lados.

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
         # `num_ctx` explicito y no el default de Ollama, por dos razones que
         # se descubrieron midiendo: Ollama trunca desde el COMIENZO del
         # prompt, y `decision.prompt` pone primero lo que mas importa (lo
         # aprendido, y ahora la carta del departamento). Con el default,
         # crecer el prompt hace que el jefe deje de ver justo lo que se le
         # agrego, en silencio: sin error y sin aviso.
         # 8192 y no mas: `qwen2.5:7b` soporta bastante mas, pero cada token
         # de contexto cuesta RAM en la maquina de Pedro y el prompt entero
         # de un tic hoy no llega ni cerca. Es holgura, no capacidad.
         "options": {"temperature": 0, "num_ctx": 8192}})
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
    def _bandeja_llena(bus_fresco, ops=None) -> bool:
        """El techo de propuestas, RELEIDO adentro del candado.

        `jefe._puede` ya lo chequea, pero contra la foto que trajo
        `situacion`, tomada afuera del candado: dos tics simultaneos del
        mismo departamento leen el mismo conteo y pasan los dos. No es
        teorico -- `interruptor.tomar_tic` cerro exactamente esta carrera
        para el contador de tics y su docstring nombra a los dos llamadores
        que la producen, "el ticker de rutinas y el boton de correr a
        mano", y ese boton existe (`POST /api/routines/{id}/run`). Aca es
        la segunda linea: el conteo se rehace con el Bus fresco, adentro
        del candado, justo antes de escribir.
        """
        if _plantel_jefe is None:
            return False
        propias = 0
        for id_ in bus_fresco.ids():
            if bus_fresco.estado(id_) != "alta":
                continue
            d_ = bus_fresco.datos(id_)
            if d_.get("departamento") != cuenta:
                continue
            # un pre-seed vencido no ocupa lugar en la bandeja: ya no se
            # puede financiar y `situacion` no lo cuenta, asi que contarlo
            # aca dejaria al departamento frenado por un pedido que ningun
            # gesto de Pedro tiene que despejar. Misma funcion que
            # `situacion`, a proposito.
            #
            # Y el libro se pliega SOLO si hay un pre-seed que mirar. Antes
            # de esta guardia, este conteo -- que corre adentro del candado
            # global de economia, en el bucle desatendido del jefe, a
            # doscientos tics por semana y por departamento-- construia un
            # `Kernel(Libro(...))` entero SIEMPRE, incluso para publicar una
            # propuesta de trabajo, que no tiene ningun vencimiento que
            # consultar: donde antes habia CERO lecturas del libro habia una
            # de medio segundo con cien mil asientos, y el docstring de
            # `_jefe` dice que tener el flock tomado durante segundos
            # serializa el chat y a dispatch contra el. `ops` ademas llega
            # hecha cuando el llamador ya lo plego (ver `pedir`).
            if d_.get("tipo") == "preseed":
                if ops is None:
                    ops = _eco_cap.semanas_operativas(
                        pagador.leer_kernel().libro.asientos())
                if _eco_bus.preseed_vencido(d_, ops, semana):
                    continue
            propias += 1
        return propias >= _plantel_jefe.TECHO_PROPUESTAS

    def contratar(situacion: dict, accion: str, ref: str | None,
                  motivo: str = "", ficha=None):
        if accion == "comentar":
            # opinar es barato: no contrata a nadie y no cobra
            return {"accion": "comentar", "ref": ref, "en": "memoria"}

        if accion == "trabajar":
            # todavia no ejecuta: la frontera de salida no esta construida
            # (spec, seccion 11). Se deja el gancho, no un cobro fantasma.
            return {"accion": "trabajar", "ref": ref, "en": "nada",
                    "motivo": "ejecutar trabajo todavia no existe"}

        if accion == "pedir":
            # La ronda pre-seed: el departamento pide capital al TESORO por
            # el mismo bus donde propone, y Pedro elige en la mesa. El canal
            # de abajo ya existe (bus.alta con tipo="preseed", que financia
            # contra el tesoro y deja la plata en la cuenta DEL
            # departamento); lo que faltaba era este traductor.
            #
            # EL MONTO NO LO PONE EL MODELO. `decision.parsear` ya exige que
            # `pedir <monto>` traiga un entero positivo, pero un entero
            # positivo alucinado sigue siendo alucinado: el de 3b nombra
            # ids que no existen y no hay razon para creerle un numero. La
            # perilla `techo_preseed_mm` del departamento -- que la puso
            # Pedro -- es el techo, y lo que el modelo diga se RECORTA a el.
            # Asi el peor caso del modelo es exactamente el numero que Pedro
            # autorizo, y no uno inventado.
            #
            # Techo en cero: Pedro todavia no dijo cuanto puede pedir este
            # departamento, asi que no se escribe nada en el bus. No es un
            # error del jefe (decidio bien), es una perilla sin poner: se
            # devuelve el no-op con el motivo, igual que `trabajar`.
            techo = int(situacion.get("techo_preseed_mm") or 0)
            if techo <= 0:
                return {"accion": "pedir", "ref": ref, "en": "nada",
                        "motivo": "sin techo de pre-seed: Pedro todavia no "
                                  "autorizo cuanto puede pedir este "
                                  "departamento"}
            # `.isdecimal()` y no `.isdigit()`: los dos aceptan los
            # digitos arabes ('٥'), pero `isdigit` tambien acepta los
            # superindices ('²') -- Numeric_Type=Digit sin ser decimales --
            # y ahi `int()` revienta con ValueError. El sintoma no era un
            # crash visible sino una mentira en el registro del jefe: en vez
            # de caer en el recorte al techo, que es la promesa del parser
            # tolerante, caia en el `except` de `tic` y se reportaba como
            # "reviento actuando".
            pedido = int(ref) if (ref or "").isdecimal() else techo
            propuesta = f"{situacion['nombre']}-{uuid.uuid4().hex[:8]}"
            titulo = (motivo or f"ronda pre-seed de {situacion['nombre']}")[:120]
            with _eco_candado(pagador.ruta_libro):
                bus_fresco = _eco_bus.Bus(pagador.ruta_bus)
                # el libro, UNA vez para las dos cosas que lo necesitan aca
                # adentro: el techo de bandeja y el recorte de abajo. Eran
                # dos parseos completos del mismo archivo en el mismo
                # candado, y el segundo no podia ver nada que el primero no
                # hubiera visto -- nadie mas puede escribir mientras este
                # flock esta tomado, que es para lo que se toma.
                asientos_frescos = pagador.leer_kernel().libro.asientos()
                ops_frescas = _eco_cap.semanas_operativas(asientos_frescos)
                if _bandeja_llena(bus_fresco, ops_frescas):
                    return {"accion": "pedir", "ref": ref, "en": "nada",
                            "motivo": "la bandeja se lleno mientras este tic "
                                      "decidia: que Pedro despeje antes de "
                                      "sumar otra"}
                # EL TECHO ACUMULADO, releido adentro del candado, por la
                # misma razon que `_bandeja_llena` de arriba: `jefe._puede`
                # ya lo chequeo contra la foto que trajo `situacion`, que
                # se tomo AFUERA -- dos tics simultaneos del mismo
                # departamento leen el mismo acumulado y pasan los dos.
                # Aca se rehace con el registro, el libro y el bus
                # frescos, que es tambien lo unico que ve una perilla que
                # Pedro bajo mientras el tic pensaba.
                #
                # El techo ACUMULADO ademas RECORTA, no solo frena: igual
                # que `techo_preseed_mm` recorta cada pedido, lo que
                # quede libre en la ventana recorta este. Publicar un pedido
                # por mas de lo que se le puede pagar es publicar una
                # propuesta que `bus.financiar` va a rechazar con Pedro ya
                # mirandola.
                dep_fresco = _eco_deps.Registro(
                    pagador.ruta_registro).obtener(situacion["nombre"])
                techo = int(dep_fresco.techo_preseed_mm or 0)
                techo_ciclo = int(dep_fresco.techo_preseed_ciclo_mm or 0)
                if techo <= 0 or techo_ciclo <= 0:
                    return {"accion": "pedir", "ref": ref, "en": "nada",
                            "motivo": "la perilla de pre-seed quedo en cero "
                                      "mientras este tic decidia: Pedro "
                                      "cerro la canilla"}
                # la ventana del CAUDAL (deslizante, `bus.ventana_preseed`)
                # y no la del ciclo de facturacion: tienen que ser la misma
                # que mira `bus.financiar` al pagar, o el recorte de aca
                # publicaria un monto que alla se rechaza.
                semanas = _eco_bus.ventana_preseed(ops_frescas, semana)
                usado = _eco_bus.preseed_en_ventana(asientos_frescos, cuenta,
                                                    semanas)
                for id_ in bus_fresco.ids():
                    d = bus_fresco.datos(id_)
                    if (bus_fresco.estado(id_) == "alta"
                            and d.get("departamento") == cuenta
                            and d.get("tipo") == "preseed"
                            # un pedido vencido ya no se puede financiar, asi
                            # que no reserva nada: sumarlo aca recortaria el
                            # pedido nuevo contra plata que nadie va a pagar
                            and not _eco_bus.preseed_vencido(
                                d, ops_frescas, semana)):
                        usado += int(d.get("presupuesto_mm") or 0)
                libre = techo_ciclo - usado
                if libre <= 0:
                    return {"accion": "pedir", "ref": ref, "en": "nada",
                            "motivo": f"el techo de la ventana es "
                                      f"{techo_ciclo} mm y ya van {usado} "
                                      "entre lo financiado y lo pedido en "
                                      "pie"}
                monto = max(1, min(pedido, techo, libre))
                # `criterio` es obligatorio en `bus.alta` y para un pre-seed
                # es INERTE: no abre `trabajo:<id>`, asi que no tiene gasto
                # que medir y `evaluar_y_liquidar_muertos` lo saltea. Se
                # manda el propio monto para no meter en el bus un segundo
                # numero distinto que despues nadie usa. Y `retorno_mm` es
                # el mismo monto por lo mismo: un pre-seed no promete un
                # retorno, entrega capital.
                bus_fresco.alta(ts, semana, propuesta, cuenta, titulo,
                                monto, monto, {"gasto_max_mm": monto},
                                tipo="preseed")
            # `ventana` y no `ciclo` en las claves: los dos numeros salen de
            # `ventana_preseed` doce lineas mas arriba, que es la ventana
            # DESLIZANTE del caudal de capital y no el ciclo de facturacion.
            # El motivo de al lado ya dice "el techo de la ventana es";
            # estas eran el ultimo resto del nombre viejo.
            return {"accion": "pedir", "ref": ref, "propuesta": propuesta,
                    "tipo": "preseed", "monto_mm": monto, "techo_mm": techo,
                    "techo_ventana_mm": techo_ciclo,
                    "libre_ventana_mm": libre}

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
        if situacion["presupuesto_semanal_mm"] <= 0:
            # Sin presupuesto semanal el tope no lo da la perilla: lo da la
            # BILLETERA. Es el estado de un departamento recien pre-seedeado
            # -- capital en la cuenta y `presupuesto_semanal_mm` todavia en
            # cero, porque el pre-seed no la toca y nada la mueve sola -- y
            # con el tope en cero toda propuesta que publicaba valia
            # `max(1, 0 - 0)` = 1 milimon. El capital llegaba y quedaba
            # inerte: se lo dejaba proponer y lo que proponia no servia. La
            # agresividad sigue midiendo lo mismo (que fraccion se
            # compromete), solo cambia contra que.
            tope = (situacion.get("disponible_mm", 0)
                    * situacion["agresividad_pct"] // 100)
        presupuesto = max(1, tope - situacion["salidas_semana_mm"])
        if ficha is None:
            # No hay camino de produccion que llegue aca sin ficha: `tic` la
            # desvia a la valvula antes de contratar. Pero el libro es
            # append-only, asi que una propuesta sin identidad escrita por
            # un llamador futuro no se podria borrar despues.
            return {"accion": accion, "ref": ref, "en": "nada",
                    "motivo": "una propuesta sin ficha no tiene identidad: "
                              "no se escribe"}
        propuesta = f"{situacion['nombre']}-{uuid.uuid4().hex[:8]}"
        # El titulo sale de la ficha, no del motivo crudo: es lo que Pedro
        # lee, y ahora lleva adentro lo mismo que la maquina compara.
        titulo = _plantel_ficha.titulo_de(ficha)
        # `semanas_max` sale del plazo que declaro el jefe. Antes eran
        # cuatro semanas escritas a mano, iguales para una propuesta de una
        # semana que para una de un trimestre.
        semanas = _plantel_ficha.SEMANAS_MAX[ficha["tarda"]]
        # al libro va la forma SIN `porque`: la prosa no se compara, y
        # guardarla adentro de la forma invitaria a compararla.
        forma = {c: ficha[c] for c in ("sobre", "clave", "promete", "tarda")}
        # bus.alta ES una escritura: va bajo el mismo candado que las demas
        # escrituras de economia, con un Bus fresco construido adentro.
        with _eco_candado(pagador.ruta_libro):
            bus_fresco = _eco_bus.Bus(pagador.ruta_bus)
            if _bandeja_llena(bus_fresco):   # segunda linea: ver arriba
                return {"accion": accion, "ref": ref, "en": "nada",
                        "motivo": "la bandeja se lleno mientras este tic "
                                  "decidia: que Pedro despeje antes de "
                                  "sumar otra"}
            bus_fresco.alta(ts, semana, propuesta, cuenta, titulo,
                            presupuesto, presupuesto,
                            {"gasto_max_mm": presupuesto,
                             "semanas_max": semanas},
                            forma=forma)
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
    # de quien es este socket: con eso se envuelve para el corte en vivo
    sesion = await _ws_autorizado(ws)
    if not sesion:
        await ws.close(code=1008)   # politica violada: sin credencial
        return
    ws = await _vigilar_socket(ws, sesion)
    if ws is None:
        return                      # sin hash no se vigila: ya cerro 1008
    await ws.accept()
    if EL_PULSO is None:
        await ws.send_json({"evento": "sin-pulso"})
        await ws.close()
        return
    cursor = 0            # cero, no el presente: el que llega tarde recibe
    vueltas = 0           # lo que el anillo todavia guarda
    try:
        while True:
            # aca no hace falta latido aparte: el tick ya corre cada cuarto de
            # segundo y un lookup de dict por vuelta no se siente
            if await _cortar_si_revocada(ws):
                return
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


def _avisar_abismo(aviso: dict) -> None:
    """"Queda aviso" (spec seccion 9) para una marca que se retiro del texto
    sin consulta -ilegible, sin corte por tope, abierta al cerrar-: fila en
    telemetry.jsonl. Sin senal al WS: no hubo pondering que cerrar. Y sin el
    cuerpo de la marca, que no se persiste en ningun lado."""
    telemetry.log_event("abismo", evento="retirada", **aviso)


# la marca mas corta posible: abre, un char de cuerpo y cierra. Es lo que cada
# vuelta de `_retirar_abismo` acorta como minimo, y de ahi sale su tope.
_MARCA_MINIMA = len(abismo_filtro.ABRE) + 1 + len(abismo_marca.CIERRA)


def _retirar_abismo(texto: str) -> tuple[str, int]:
    """Saca las marcas del abismo hasta PUNTO FIJO y dice cuantas saco.

    Una sola pasada de `sub` no alcanza: el cuerpo de `PATRON` no admite
    corchetes, asi que sacar una marca puede ARMAR otra con el texto de los
    dos costados -"⟦abismo:⟦abismo:chats x⟧chats y⟧" deja "⟦abismo:chats y⟧",
    valida y completa- y esa quedaria en el texto que se manda al panel y al
    `jobs.event` del preview, o sea en disco, contra la regla de que la marca
    jamas se persiste. El filtro del stream llega al mismo lugar por otro
    camino: se queda con la primera marca valida y descarta todo lo que venga
    detras, empalme incluido. Aca no hay corte que descarte nada, asi que el
    retiro tiene que insistir hasta que no quede ninguna.

    El tope de vueltas es de seguridad y no de corte: cada vuelta que saca
    algo acorta el texto en al menos una marca minima, asi que el punto fijo
    entra siempre; el tope solo evita que un cambio futuro de la gramatica
    -una que pudiera crecer- cuelgue el bucle."""
    texto = texto or ""
    total = 0
    for _ in range(len(texto) // _MARCA_MINIMA + 1):
        texto, n = abismo_marca.PATRON.subn("", texto)
        if not n:
            break
        total += n
    return texto, total


def _retirar_con_aviso(texto: str, clase: str) -> str:
    """Retira las marcas del abismo de un texto que NO pasa por el filtro del
    Emisor -la sintesis de los agentes del orquestador, lo posterior a una
    marca en la ruta one-shot- y deja el aviso que el spec exige (seccion
    4: "se ignoran con aviso"): una fila por retiro, con la cantidad, sin
    el cuerpo. Solo la gramatica del abismo: la de foco la retira quien
    corresponda (el filtro de foco del Emisor, o `_limpiar_marcas`)."""
    limpio, n = _retirar_abismo(texto)
    if n:
        _avisar_abismo({"clase": clase, "largo": 0, "cantidad": n})
    return limpio


class Emisor:
    """Todo lo que Pedro lee sale por aca.

    Tres cosas en un solo lugar: retirar la marca de foco del texto visible,
    publicar el foco apenas aparece (la camara vuela mientras Calipso sigue
    escribiendo) y darle al pulso lo que se va diciendo. Antes los chunks
    salian desde cinco puntos de `ws_chat`, y filtrar en cinco lugares es
    filtrar en cuatro.

    Desde el abismo (spec seccion 4) los filtros son una tuberia ordenada:
    foco primero, abismo despues. La marca del abismo no se resuelve aca
    (es I/O y hay que cerrar el generador): se entrega hacia arriba por
    `marca_abismo()` y la consume el bucle de `ws_chat`."""

    def __init__(self, ws, agente_id: str | None = None, resolver=None,
                 pulso=None, filtro=None, filtros=None, avisar=None):
        self.ws = ws
        self.agente_id = agente_id
        self._resolver = resolver or _resolver_foco
        self._pulso = pulso if pulso is not None else EL_PULSO
        # el default es SOLO foco: el borrador de /redacta construye
        # `Emisor(ws)` y no tiene quien resuelva una consulta (spec seccion
        # 11); el turno conversacional pasa la lista completa a mano.
        if filtros is not None:
            self._filtros = list(filtros)
        elif filtro is not None:
            self._filtros = [filtro]
        else:
            self._filtros = [_mapa_foco.Filtro()] if _mapa_foco is not None else []
        self._avisar = avisar or _avisar_abismo
        self.focos: list[str] = []

    async def _soltar(self, visible: str) -> str:
        if not visible:
            return ""      # un chunk vacio la UI vieja lo pinta igual
        await self.ws.send_json({"type": "chunk", "text": visible})
        if self._pulso is not None and self.agente_id:
            self._pulso.publicar(self.agente_id, "razonando", texto=visible)
        return visible

    def _cosechar(self) -> None:
        """Lo que los filtros vieron: focos (se resuelven y publican aca, es
        una lectura de un JSON chico) y avisos del abismo (a telemetry)."""
        for f in self._filtros:
            for nombre in (f.tomar_focos() if hasattr(f, "tomar_focos") else ()):
                destino = self._resolver(nombre)
                if destino is None:
                    continue          # el modelo se invento un departamento
                self.focos.append(destino)
                if self._pulso is not None:
                    self._pulso.enfocar(destino)
            for aviso in (f.tomar_avisos() if hasattr(f, "tomar_avisos") else ()):
                self._avisar(aviso)

    async def chunk(self, texto: str) -> str:
        """Manda lo visible y devuelve exactamente eso, para que el que
        acumula la respuesta acumule lo mismo que Pedro leyo."""
        visible = texto
        for f in self._filtros:
            visible = f.comer(visible)
        visible = await self._soltar(visible)
        self._cosechar()
        return visible

    def marca_abismo(self):
        """La marca valida pendiente del filtro del abismo, consumida; None
        si no hay filtro o no hay marca. Cuando la hay, lo que los filtros
        ANTERIORES de la tuberia retenian es posterior a la marca (el
        corchete de un `⟦fo` a medio llegar) y se descarta con ella."""
        for i, f in enumerate(self._filtros):
            if not hasattr(f, "tomar_marca"):
                continue
            m = f.tomar_marca()
            if m is not None:
                for previo in self._filtros[:i]:
                    previo.cerrar()
            return m
        return None

    async def cerrar(self) -> str:
        """Una marca de foco que nunca cerro es texto y Pedro tiene que
        verlo; lo que suelta un filtro pasa por los que le siguen (asi el
        abismo mira el corchete que foco venia reteniendo), y lo que retenga
        el del abismo se descarta con aviso (spec seccion 11)."""
        salida = ""
        for i, f in enumerate(self._filtros):
            cola = f.cerrar()
            for siguiente in self._filtros[i + 1:]:
                cola = siguiente.comer(cola)
            salida += cola
        self._cosechar()
        return await self._soltar(salida)


def _limpiar_marcas(texto: str) -> str:
    """El parcial de la suscripcion se remanda ENTERO cada dos segundos, asi
    que no necesita la maquinaria de retencion del Filtro: alcanza con sacar
    las marcas completas. Una marca a medio llegar se limpia sola en el envio
    siguiente, porque el texto se relee desde cero.

    Compone las dos gramaticas EN EL MISMO ORDEN que la tuberia de filtros del
    Emisor -foco primero, abismo despues- y por la misma razon: una marca de
    foco metida en el cuerpo del abismo lo parte en dos y tapa la marca
    entera, asi que si el abismo va primero la ve el que limpia despues, no
    el que limpia antes. Al reves las dos rutas juzgaban distinto el mismo
    texto, y la del preview dejaba en disco la marca que la del stream
    retiraba. El retiro del abismo va al final y hasta punto fijo
    (`_retirar_abismo`) para que ningun empalme deje una marca armada.

    Es el retiro que cubre la ruta orquestador (spec seccion 4: las marcas de
    los agentes se ignoran con aviso) y el preview y los artefactos de la
    suscripcion."""
    texto = _mapa_foco.limpiar(texto) if _mapa_foco is not None else (texto or "")
    return _retirar_abismo(texto)[0]


# --------------------------------------------------------------------------
# EL ABISMO (spec 2026-09-07, seccion 4): la consulta in-band del chat
# --------------------------------------------------------------------------
def _zona_del_chat(departamento: str | None) -> str:
    """La zona del turno sale del edificio que Pedro tiene tocado: la cuenta
    codifica la zona (`personal:` contra `dep:`, la inversa de
    `ficha.cuenta_pagadora`). Sin edificio tocado no hay senal de zona y la
    frontera falla cerrada: `fabrica`, que es la que NO deja pasar el
    consolidado del libro personal (spec seccion 6)."""
    return "personal" if (departamento or "").startswith("personal:") else "fabrica"


def _consolidado_personal() -> str | None:
    """El neto del libro personal, formateado para la fuente `memoria`. Lee
    SOLO el jsonl privado (invariante 11), sin candado ni libro de la
    fabrica; se llama en hilo y solo cuando la zona es personal, asi no se
    carga el archivo para que la frontera lo tire igual. La incoherencia
    preexistente con `_formatear_economia` (que mete el neto en el system
    de TODOS los turnos sin mirar zona) no se arregla aca."""
    if _eco_personal is None:
        return None
    ruta = _ECO_BASE / "economia" / "personal.jsonl"
    if not ruta.exists():
        return None
    r = _eco_personal.LibroPersonal(ruta).resumen()
    return (f"ingresos {r['ingresos_mm']} mm, gastos {r['gastos_mm']} mm, "
            f"neto {r['neto_mm']} mm")


async def _pescar_abismo(ws, m, estado, *, destino: str, mapa,
                         departamento: str | None,
                         agente_id: str | None = None,
                         inbox: asyncio.Queue | None = None,
                         chat_id: str | None = None) -> bool:
    """Una consulta al abismo de punta a punta: pondering -> resolver en
    hilo (100% local, invariante 1) -> viaje -> pescado/fallo. Cuenta la
    consulta contra el tope, acumula el bloque en el estado del turno y
    devuelve True si hay un bloque nuevo para la reentrada.

    Fallo cerrado en todo (invariante 4): cualquier excepcion degrada a
    "seguir sin contexto extra" con senal `fallo` y fila en telemetry; toda
    senal de pondering tiene cierre. `mem` se lee del modulo en el momento
    de resolver (se reasigna al cambiar de proyecto) y jamas se construye
    uno nuevo por consulta.

    El steer de Pedro gana (spec seccion 10): la pesca corre en hilo y no
    se interrumpe, pero si al volver hay algo en `inbox` la senal cierra en
    `fallo` (motivo `error`: MOTIVOS es cerrada y no tiene uno de aborto;
    el `steered` que sigue lo explica en la UI) y el bloque NO entra al
    estado -bloque descartado, aviso-. El bucle que llamo atiende el steer
    en su tope."""
    estado.consultas += 1
    await ws.send_json(abismo_turno.senal("pondering", m.fuente))
    # la misma senal al pulso del mapa (spec seccion 9): la escena de la
    # rebanada 3 la lee de ahi. Va con el `agente_id` del turno para colgar
    # del escritorio que el `inicio` ya abrio
    if EL_PULSO is not None and agente_id:
        EL_PULSO.publicar(agente_id, "abismo", fase="pondering", fuente=m.fuente)
    inicio = time.perf_counter()
    motivo = ""
    motivo_telemetry = ""
    v: dict = {}
    try:
        zona = _zona_del_chat(departamento)
        consolidado = (await asyncio.to_thread(_consolidado_personal)
                       if zona == "personal" else None)
        # la fuente `chats` no pesca lo que el modelo ya tiene del chat en
        # curso: en local, la ventana del historial mas la pregunta (que ya
        # se persistio: `_history_messages` descarta el ultimo mensaje y
        # toma `_HISTORY_TURNS` anteriores); en /nube, el chat activo
        # ENTERO -- la conversacion no viaja (chat_id_nube=None, Fase 2a) y
        # el bloque no puede ser la puerta de atras de un turno local previo
        en_contexto = None if destino == "nube" else _HISTORY_TURNS + 1
        r = await asyncio.to_thread(
            abismo_consulta.resolver, m, mem=mem, obtener=catastro.obtener,
            brief=_repo_brief, consolidado=consolidado, zona_chat=zona,
            chat_activo=chat_id, en_contexto=en_contexto)
        if r["estado"] != "pescado":
            motivo = abismo_turno.motivo_de_consulta(r)
        else:
            v = await asyncio.to_thread(abismo_viaje.preparar_viaje, r["bloques"],
                                        destino, mapa, fuente=m.fuente)
            if v["estado"] != "viaja":
                motivo = v["motivo"]
    except Exception as exc:
        motivo = "error"
        print(f"[calipso] la consulta al abismo fallo: {exc}", file=sys.stderr)
    if not motivo and inbox is not None and not inbox.empty():
        # el steer de Pedro llego mientras se pescaba: la consulta se
        # cancela aca, antes de dar por pescado nada
        motivo, motivo_telemetry = "error", "abortada_por_steer"
    ms = round((time.perf_counter() - inicio) * 1000)
    if motivo:
        await ws.send_json(abismo_turno.senal("fallo", m.fuente, motivo=motivo))
        if EL_PULSO is not None and agente_id:
            EL_PULSO.publicar(agente_id, "abismo", fase="fallo", fuente=m.fuente,
                              motivo=motivo)
        telemetry.log_event("abismo", evento="consulta", fuente=m.fuente,
                            resultado="fallo", motivo=motivo_telemetry or motivo,
                            destino=destino, consultas=estado.consultas,
                            latencia_ms=ms)
        return False
    estado.bloques.append(v["texto"])
    viaje_info = ({"destino": destino} if destino != "nube" else
                  {"destino": "nube", "tapados": v["tapados"],
                   "texto_tapado": v["texto"]})
    await ws.send_json(abismo_turno.senal("pescado", m.fuente,
                                          tamano=len(v["texto"]), viaje=viaje_info))
    # al pulso va el tamano, nunca el bloque: el pulso es efimero pero se
    # replica a todo cliente del mapa, y el bloque pescado no sale del turno
    # (invariante 2)
    if EL_PULSO is not None and agente_id:
        EL_PULSO.publicar(agente_id, "abismo", fase="pescado", fuente=m.fuente,
                          tamano=len(v["texto"]))
    telemetry.log_event("abismo", evento="consulta", fuente=m.fuente,
                        resultado="pescado", chars=len(v["texto"]), destino=destino,
                        tapados=len(v["tapados"]), consultas=estado.consultas,
                        latencia_ms=ms)
    return True


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
    se cobra en unidades de capacidad, asi que devuelve cero. La local corre
    Ollama de verdad -gratis-, no una suscripcion disfrazada: no debita
    ninguna unidad y tambien devuelve cero, sin tocar el libro."""
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
        if route == "subscription":
            pagador.cargar_suscripcion(ts, semana, cuenta,
                                       _eco_suscripcion(client))
        # `route == "local"` no cae en ninguna rama de arriba y a proposito:
        # ahora corre Ollama de verdad (Tarea 1), y Ollama no cobra. Antes
        # esta rama la trataba como una suscripcion de `claude` disfrazada
        # -el fallback local corria `claude -p`- y le debitaba una unidad de
        # capacidad que nunca se uso. El `return 0` de abajo alcanza: no hay
        # nada que cobrarle al libro de suscripcion.
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


def _asegurar_rutina_cierre() -> None:
    """Mismo problema que `_asegurar_rutina_catastro`, mismo arreglo: un
    ~/.calipso que ya tenia routines.json antes de que "cierre" existiera
    como kind nunca lo ve aparecer solo. A diferencia de catastro, esta
    rutina nace APAGADA (ver el comentario junto a routines.DEFAULTS):
    encender el cierre automatico de la economia -- expirar PT, declarar
    quiebras, liquidar trabajos -- es decision de Pedro, no nuestra. Sin
    este arreglo la rutina existiria en el codigo pero Pedro nunca la
    veria en su panel para poder prenderla."""
    try:
        if not any(r.get("kind") == "cierre" for r in calipso_routines.load()):
            calipso_routines.add(
                "cierre", "Cerrar semana operativa de la economia",
                1440, enabled=False)
    except Exception:
        pass


def _asegurar_rutina_consumo() -> None:
    """Mismo problema, mismo arreglo, tercera vez: un ~/.calipso que ya
    tenia routines.json antes de que "consumo" existiera como kind nunca
    lo ve aparecer solo. Igual que catastro (y a diferencia de cierre) nace
    HABILITADA: no gasta nada -- solo lee jsonl locales -- y no toma
    ninguna decision economica, asi que no hay motivo para que Pedro tenga
    que acordarse de prenderla (ver el comentario junto a
    routines.DEFAULTS)."""
    try:
        if not any(r.get("kind") == "consumo" for r in calipso_routines.load()):
            calipso_routines.add(
                "consumo", "Medir consumo real de las suscripciones",
                60, enabled=True)
    except Exception:
        pass


def _calentar_probes() -> dict:
    """En hilo (`to_thread` desde `_startup_warm`): declara UNA vez la memoria
    y los modelos fuera de la maquina (`_declarar_arranque`; no puede ir a
    nivel de modulo: con `uvicorn calipso.server:app` el import corre en el
    loop) y los probes `claude/codex --version`, `auth status`, `login
    status`, y calienta el cache. `_subscription_probe` queda SIN llamada a
    la aduana a proposito: se alcanza desde el loop via `_harness_context`
    en cada turno, y ahi el candado no se puede tomar (spec seccion 3)."""
    _declarar_arranque()
    aduana.declarar_una_vez(
        "probes", aduana.Quien(origen="arranque", proyecto=_proyecto(),
                               desde={"credencial": "maquina"}),
        "probes claude/codex: --version, auth status, login status", destino=None)
    return _backend_availability()


@app.on_event("startup")
async def _startup_warm() -> None:
    # cada paso con su try: un `discover` que levanta (Ollama caido, una
    # config rara) no se lleva la declaracion de la memoria ni los probes
    try:
        found = await asyncio.to_thread(discovery.discover, True)
        if found["added"]:
            print(f"[calipso] modelos descubiertos: {found['added']}")
    except Exception:
        pass
    try:
        await asyncio.to_thread(_calentar_probes)  # declara la memoria y los probes, pre-calienta el cache
    except Exception:
        pass
    await asyncio.to_thread(_asegurar_rutina_catastro)
    await asyncio.to_thread(_asegurar_rutina_cierre)
    await asyncio.to_thread(_asegurar_rutina_consumo)
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


def _enmascarar_token(texto: str) -> str:
    limpio = re.sub(r"token=[^&\s\"']+", "token=***", texto)
    if TOKEN:
        limpio = limpio.replace(TOKEN, "***")
    return limpio


class _FiltroToken(logging.Filter):
    """Enmascara la credencial en los logs de uvicorn (revision de seguridad
    2026-09-07, C4): el access log por default escribe la request CON query
    string, y auth_guard acepta ?token= -- cada GET con token era una copia
    de la credencial en disco/scrollback.

    El access log de uvicorn emite (client, metodo, full_path, http_ver,
    status) como 5-tupla en record.args y su AccessFormatter la DESEMPACA:
    aplanar args rompia el formatter y perdia justo las lineas enmascaradas
    (lo cazo la ronda adversaria) -- por eso aca se enmascara ADENTRO de la
    tupla y solo se aplana en records sin args de acceso."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if (isinstance(args, tuple) and len(args) == 5
                and isinstance(args[2], str)):
            limpio = _enmascarar_token(args[2])
            if limpio != args[2]:
                record.args = (args[0], args[1], limpio, args[3], args[4])
            return True
        msg = record.getMessage()
        limpio = _enmascarar_token(msg)
        if limpio != msg:
            record.msg = limpio
            record.args = ()
        return True


def _instalar_filtro_de_token() -> None:
    """Idempotente, y se llama AL IMPORTAR el modulo (abajo): el shell de
    escritorio arranca el server via `uvicorn calipso.server:app` (import,
    no __main__), y un filtro instalado solo en __main__ lo dejaba sin
    cubrir -- lo cazo la ronda adversaria. Los filtros de logger sobreviven
    al dictConfig de uvicorn (borra handlers, no filters)."""
    for nombre in ("uvicorn.access", "uvicorn.error", "uvicorn"):
        logger = logging.getLogger(nombre)
        if not any(isinstance(f, _FiltroToken) for f in logger.filters):
            logger.addFilter(_FiltroToken())


_instalar_filtro_de_token()

if __name__ == "__main__":
    host = _host()
    print(f"[calipso] sirviendo {ROOT}")
    # El token NO se imprime (quedaba en scrollback/journal): esta en el
    # archivo, que ya vive en 0600.
    print(f"[calipso] token de acceso: en {_TOKEN_FILE}")
    print(f"[calipso] local:  http://127.0.0.1:8000")
    if host != "127.0.0.1":
        import socket
        ip = socket.gethostbyname(socket.gethostname())
        print(f"[calipso] ABIERTO en {host} — tambien entra http://{ip}:8000")
        # C8: criterio invertido (ronda adversaria) -- el aviso duro salta
        # para TODO host que no sea loopback ni la red de Tailscale
        # (100.64.0.0/10, el camino bendecido del lector), no solo para el
        # literal todas-las-interfaces ("::" y una IP de LAN pelada exponen
        # lo mismo).
        import ipaddress
        try:
            en_tailscale = ipaddress.ip_address(host) in (
                ipaddress.ip_network("100.64.0.0/10"))
        except ValueError:
            en_tailscale = False
        if not en_tailscale:
            print("[calipso] OJO: este host abre HTTP SIN CIFRAR fuera de "
                  "la maquina. Para el lector usa la IP de Tailscale "
                  "(100.x) como CALIPSO_HOST.")
    # proxy_headers=False: Calipso no corre detras de ningun proxy, y el
    # default de uvicorn (confiar X-Forwarded-For desde loopback) dejaba
    # que un proceso local forjara request.client.host -- la clave del
    # freno de login (verificacion adversaria del 3a).
    uvicorn.run(app, host=host, port=8000, proxy_headers=False)
