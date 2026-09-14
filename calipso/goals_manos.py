"""
calipso/goals_manos.py - las manos del goal (spec 2026-09-13, seccion 7).

v1 (Task 2): la cabeza SIN herramientas -- la propuesta del goal y, mas
adelante, el revisor `claude` -- por `claude -p --restricted --tools ""` o
`codex exec -s read-only`, con el prompt por STDIN (nunca por argv: `ps` lo
veria) y el contrato del system en un archivo FUERA del cwd, en un
directorio vacio. El veredicto vuelve por `--json-schema` (Claude:
`result.structured_output` del stream-json) o `--output-schema` (Codex: el
archivo de `-o`).

La Task 3 suma el golpe con herramientas (sandbox, hook, stream-json con la
sonda del hook, timeout que mata el grupo, detector de secretos).

Todo subprocess vive en una funcion de modulo con nombre propio: el canario
de la aduana (test_aduana_canario.py) arma su clave con la pila de
FunctionDef, y cada una tiene su entrada `modelo:`/`local:` en EXCEPCIONES.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import pathlib
import signal
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from typing import Callable

from calipso import github as calipso_github
from calipso import goals
from calipso.privacidad import detector

TIMEOUT_CABEZA_S = 180

# El JSON que la cabeza devuelve al proponer (spec seccion 4).
ESQUEMA_PROPUESTA: dict = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "criterio": {
            "type": "object",
            "properties": {
                "tipo": {"type": "string", "enum": ["comando", "archivo", "numero", "revisor"]},
                "comando": {"type": "string"},
                "ruta": {"type": "string"},
                "metrica": {"type": "string"},
                "umbral": {"type": "number"},
                "texto": {"type": "string"},
            },
            "required": ["tipo"],
        },
        "tope": {
            "type": "object",
            "properties": {"golpes": {"type": "integer"}, "minutos": {"type": "integer"},
                           "unidades": {"type": "integer"}},
            "required": ["golpes", "minutos", "unidades"],
        },
        "familias": {"type": "array", "items": {"type": "string"}},
        "raices": {"type": "array", "items": {"type": "string"}},
        "dominios": {"type": "array", "items": {"type": "string"}},
        "plan": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 6},
        "manos": {"type": "string", "enum": ["claude", "codex"]},
        "unidades_estimadas": {"type": "integer"},
        "minutos_estimados": {"type": "integer"},
    },
    "required": ["titulo", "criterio", "tope", "familias", "raices", "dominios", "plan", "manos"],
}


def env_saneado(base: dict | None = None) -> dict:
    """El entorno de toda invocacion del goal: el escudo git por entorno
    (server._subscription_invocation, revision de seguridad 2026-09-07) sin
    anular el gitconfig global (el martillo commitea con la identidad de
    Pedro), y sin las credenciales que el CLI no necesita: CALIPSO_TOKEN es
    del servidor, LITELLM_MASTER_KEY de la ruta api, las claves Anthropic no
    le sirven a la suscripcion. PYTHONPATH tampoco viaja (el martillo no
    importa el repo de Calipso)."""
    env = calipso_github.env_git_blindado(anular_global=False)
    if base is not None:
        env = {**base, **{k: v for k, v in env.items() if k.startswith("GIT_CONFIG")}}
    for k in ("CALIPSO_TOKEN", "LITELLM_MASTER_KEY", "ANTHROPIC_API_KEY",
              "ANTHROPIC_AUTH_TOKEN", "PYTHONPATH"):
        env.pop(k, None)
    return env


def argv_cabeza_claude(exe: str, contrato: str, schema: dict,
                       model: str | None = None, tools: str = "",
                       settings: dict | None = None) -> list[str]:
    """`claude -p` sin herramientas (terreno A.2/A.6, confirmadas por
    `--help` salvo `--append-system-prompt-file`, que `--help` de 2.1.270 no
    lista: esta confirmada por el uso del server en el turno real
    (server.py:3538) y por el texto de `--bare`, y el smoke la ejercita):
    `--restricted --tools ""` (ninguna builtin), `--setting-sources ""`
    (ni los 90 permissions.allow ni los plugins de Pedro), `--strict-mcp-config`
    (Trampa 1: sin esto entra el MCP de Google Drive), `stream-json` con
    `--verbose` (obligatorio) y `--json-schema` inline. El prompt va por
    stdin. Con `settings` (el revisor con herramientas de lectura: cierre
    2026-09-14) van ademas `--settings <json>` (el sandbox con denyRead y
    el hook), `--include-hook-events` (la sonda del Parser) y
    `--permission-prompts none` (lo que pediria permiso se niega solo)."""
    argv = [exe, "-p", "--restricted", "--tools", tools, "--setting-sources", "",
            "--strict-mcp-config", "--output-format", "stream-json", "--verbose",
            "--json-schema", json.dumps(schema, ensure_ascii=False),
            "--append-system-prompt-file", contrato]
    if settings is not None:
        argv += ["--settings", json.dumps(settings, ensure_ascii=False), "--include-hook-events",
                 "--permission-prompts", "none"]
    if model:
        argv += ["--model", model]
    return argv


def argv_cabeza_codex(exe: str, cwd: str, salida: str, schema_file: str,
                      model: str | None = None) -> list[str]:
    """`codex exec` solo lectura (terreno A.7): `-s read-only`, `-C <dir>`,
    `--json`, `-o <archivo>` (el ultimo mensaje), `--output-schema <ARCHIVO>`
    (Codex toma un archivo, no JSON inline: Trampa 10), `--skip-git-repo-check`
    (el directorio vacio no es un repo) y `-` = el prompt por stdin."""
    argv = [exe, "exec"]
    if model:
        argv += ["-m", model]
    argv += ["-s", "read-only", "-C", cwd, "--json", "-o", salida,
             "--output-schema", schema_file, "--skip-git-repo-check", "-"]
    return argv


def _correr_cabeza(argv: list[str], stdin: str, cwd: str, env: dict,
                   timeout: float, al_lanzar: Callable | None = None) -> tuple[int, str, str]:
    """El unico subprocess de la cabeza: CLI de suscripcion, lo mide la
    telemetria y la economia (canario: `modelo:`). Bloqueante: se llama en
    hilo (`asyncio.to_thread`) y con timeout. Popen con sesion propia (el
    timeout mata el grupo, como el golpe) y `al_lanzar(proc)` apenas
    existe: el revisor cuenta como golpe y el runner guarda su handle en
    `golpe_en_curso` para que parar/apagar lo maten en vez de dejarlo
    gastando cuota huerfano."""
    try:
        proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                encoding="utf-8", errors="replace", start_new_session=True)
    except Exception as e:
        return (1, "", str(e))
    publicar(al_lanzar, proc, None)
    try:
        out, err = proc.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        matar(proc)
        return (124, "", f"timeout a los {timeout} s")
    except Exception as e:
        matar(proc)
        return (1, "", str(e))
    return (proc.returncode, out or "", err or "")


@dataclasses.dataclass
class Cabeza:
    """Lo que vuelve de un golpe de la cabeza (la propuesta, el revisor):
    el JSON del esquema o None, y lo que el ledger necesita para cobrarlo y
    para decir por que fallo (ruling 15.12: unidades reales; invariante
    'nunca muere en silencio': salida_tail)."""
    veredicto: dict | None = None
    unidades: int = 0
    salida_tail: str = ""
    session_id: str | None = None
    motivo: str | None = None          # None | "exit N" | "timeout" | "cancelado" | "hook inactivo: ..." | "sin veredicto"
    exit: int | None = None


def cabeza(client: str, exe: str, system: str, prompt: str, schema: dict, *, cwd: str,
           env: dict | None = None, model: str | None = None, timeout: float = TIMEOUT_CABEZA_S,
           tools: str = "", al_lanzar: Callable | None = None, settings: dict | None = None,
           cancelar: threading.Event | None = None) -> Cabeza:
    """Un golpe de la cabeza: sin herramientas (la propuesta) o con las de
    lectura y la barrera (`settings`: el revisor claude). El contrato
    (`system`) se escribe en un temporal FUERA de `cwd` y se borra al
    salir; el prompt va por stdin. `cwd` tiene que ser un directorio vacio
    o de solo lectura para el modelo. claude corre por `golpear`: el
    stream pasa por el Parser (unidades = len(usage.iterations), session_id,
    y la sonda del hook: un tool_result sin hook_response mata el proceso y
    vuelve sin veredicto con el motivo), con timeout que mata el grupo y
    `al_lanzar` que publica el Popen. codex sigue por `_correr_cabeza`
    (communicate: su --json no se parsea, No confirmado 7) y vale 1 unidad
    cuando contesta."""
    env = env if env is not None else env_saneado()
    temporales: list[str] = []
    try:
        if client == "claude":
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".contrato.md",
                                             delete=False) as f:
                f.write(system)
                temporales.append(f.name)
            argv = argv_cabeza_claude(exe, temporales[0], schema, model, tools=tools, settings=settings)
            r = golpear(argv=argv, stdin=prompt, cwd=cwd, env=env, timeout_s=timeout, cancelar=cancelar,
                        usar_systemd=False, al_lanzar=al_lanzar)
            c = Cabeza(unidades=r.unidades, salida_tail=(r.stdout_tail or "")[-1500:],
                       session_id=r.session_id, exit=r.exit, motivo=r.motivo)
            if r.motivo is None and r.exit != 0:
                c.motivo = f"exit {r.exit}"
            if c.motivo is None:
                c.veredicto = r.veredicto if isinstance(r.veredicto, dict) else None
                if c.veredicto is None:
                    c.motivo = "sin veredicto (la cabeza no devolvio el JSON del esquema)"
            return c
        if client == "codex":
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".schema.json",
                                             delete=False) as f:
                json.dump(esquema_para_codex(schema), f)      # el modo estricto de OpenAI
                temporales.append(f.name)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".salida.txt",
                                             delete=False) as f:
                temporales.append(f.name)
            argv = argv_cabeza_codex(exe, cwd, temporales[1], temporales[0], model)
            rc, out, err = _correr_cabeza(argv, f"{system}\n\n{prompt}", cwd, env, timeout,
                                          al_lanzar=al_lanzar)
            c = Cabeza(salida_tail=((out or "") + (err or ""))[-1500:], exit=rc)
            if rc == 124:
                c.motivo = "timeout"
                return c
            if rc != 0:
                c.motivo = f"exit {rc}"
                return c
            c.unidades = 1
            try:
                texto = pathlib.Path(temporales[1]).read_text(encoding="utf-8").strip()
                v = json.loads(texto) if texto else None
                c.veredicto = sin_nulos(v) if isinstance(v, dict) else None
            except (OSError, json.JSONDecodeError):
                c.veredicto = None
            if c.veredicto is None:
                c.motivo = "sin veredicto (codex no escribio el JSON del esquema)"
            return c
        return Cabeza(motivo=f"cliente desconocido: {client}")
    finally:
        for t in temporales:
            try:
                os.unlink(t)
            except OSError:
                pass


def cabeza_sin_herramientas(client: str, exe: str, system: str, prompt: str,
                            schema: dict, *, cwd: str, env: dict | None = None,
                            model: str | None = None,
                            timeout: float = TIMEOUT_CABEZA_S,
                            tools: str = "", al_lanzar: Callable | None = None) -> dict | None:
    """La envoltura vieja de `cabeza`: solo el JSON del esquema o None (exit
    distinto de 0, timeout, sin JSON). La usa el server para la propuesta
    hasta que pase a `cabeza` (unidades reales para el cobro del golpe 0)."""
    return cabeza(client, exe, system, prompt, schema, cwd=cwd, env=env, model=model, timeout=timeout,
                  tools=tools, al_lanzar=al_lanzar).veredicto


# ==========================================================================
# v2 (Task 3): el golpe con herramientas
# ==========================================================================

HOOK_PATH = pathlib.Path(__file__).with_name("goals_hook.py")
HOOK_PYTHON = sys.executable
TIMEOUT_REVISOR_S = 300
TIMEOUT_SONDA_S = 20
SONDEO_S = 0.5
GRACIA_KILL_S = 5.0
HERRAMIENTAS = ["Bash", "Edit", "Write", "MultiEdit", "Read", "Glob", "Grep"]
HERRAMIENTAS_WEB = ["WebSearch", "WebFetch"]
HERRAMIENTAS_LECTURA = "Read,Glob,Grep"
CON_HOOK = set(HERRAMIENTAS + HERRAMIENTAS_WEB + ["NotebookEdit"])
MATCHER_HOOK = "Bash|Edit|Write|MultiEdit|NotebookEdit|Read|Glob|Grep|WebFetch|WebSearch"
# spec seccion 7: la lista ya existe en permisos/acciones.py:176-183 mas
# ~/.codex y ~/.calipso; ~/.claude entero NO (el CLI lo necesita; Trampa 5)
DENY_READ = ["~/.ssh", "~/.gnupg", "~/.aws", "~/.config/gh", "~/.claude/.credentials.json",
             "~/.codex", "~/.calipso"]
DOMINIO_API = "api.anthropic.com"
DOMINIOS_NEGADOS = ["github.com", "api.github.com"]
SIN_TAPAR = {"session_id", "request_id", "diff_stat", "id", "goal", "n", "ts", "ts_fin",
             "message_id", "tool_use_id"}
PATRONES_CUOTA = ("usage limit", "rate limit", "hit your usage", "rate_limit", "quota",
                  "resets at", "limit reached", "overloaded")

# El veredicto estructurado con el que termina cada golpe (spec seccion 5.2).
ESQUEMA_VEREDICTO: dict = {
    "type": "object",
    "properties": {
        "estado": {"type": "string", "enum": ["sigo", "terminar", "preguntar"]},
        "resumen": {"type": "string"},
        "pregunta": {"type": "string"},
        "compuerta": {
            "type": "object",
            "properties": {
                "familia": {"type": "string"},
                # la forma exacta, con las claves que el hook y el motor
                # entienden (goals_hook: argv de un comando, ruta de un
                # archivo, raiz de una raiz nueva; host de WebFetch)
                "forma": {
                    "type": "object",
                    "properties": {"raiz": {"type": "string"}, "ruta": {"type": "string"},
                                   "argv": {"type": "array", "items": {"type": "string"}},
                                   "host": {"type": "string"}},
                },
            },
        },
    },
    "required": ["estado", "resumen"],
}


def esquema_para_codex(esquema: dict) -> dict:
    """El mismo esquema en el modo ESTRICTO que exige la API de OpenAI para
    `--output-schema` (smoke corrida 3, No confirmado 7: codex salia 1 en
    2,5 s con `invalid_json_schema: 'additionalProperties' is required to be
    supplied and to be false`): en cada objeto `additionalProperties: false`
    y TODAS las claves en `required`; lo que era opcional pasa a nullable
    (`type: [..., "null"]`, `null` en el enum). El original no se toca:
    claude lo recibe permisivo por --json-schema. Lo que codex conteste con
    null se limpia con `sin_nulos` al leerlo."""
    def _nodo(n, requerido=True):
        if isinstance(n, list):
            return [_nodo(x) for x in n]
        if not isinstance(n, dict):
            return n
        out = {k: (_nodo(v) if k not in ("properties",) else v) for k, v in n.items()}
        t = out.get("type")
        es_objeto = t == "object" or (isinstance(t, list) and "object" in t)
        if es_objeto:
            props = out.get("properties") or {}
            req = set(out.get("required") or [])
            out["properties"] = {k: _nodo(v, requerido=k in req) for k, v in props.items()}
            out["required"] = list(props)
            out["additionalProperties"] = False
        if not requerido:
            if isinstance(t, str):
                out["type"] = [t, "null"]
            elif isinstance(t, list) and "null" not in t:
                out["type"] = [*t, "null"]
            if "enum" in out and None not in out["enum"]:
                out["enum"] = [*out["enum"], None]
        return out
    return _nodo(esquema)


def sin_nulos(v):
    """Recursivo: saca las claves con valor null de los dicts (codex, en
    modo estricto, manda todas las claves del esquema; las opcionales que
    no uso vienen en null y el runner las espera ausentes, como en claude)."""
    if isinstance(v, dict):
        return {k: sin_nulos(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [sin_nulos(x) for x in v]
    return v

# La respuesta del revisor de otra familia (spec seccion 6.2).
ESQUEMA_REVISOR: dict = {
    "type": "object",
    "properties": {
        "cumplido": {"type": "boolean"},
        "falta": {"type": "array", "items": {"type": "string"}},
        "nota": {"type": "string"},
    },
    "required": ["cumplido", "falta", "nota"],
}

CONTRATO_REVISOR = (
    "Eres el REVISOR de un goal de Calipso: otro modelo hizo el trabajo y vos "
    "no lo hiciste. Solo lectura sobre el clon (podes leer archivos). Recibis "
    "el goal, el criterio, el resumen del ledger, el diff y las salidas. "
    "Contesta SOLO el JSON del esquema: cumplido (true solo si el goal esta "
    "hecho de verdad, no si 'casi'), falta (la lista concreta de lo que "
    "falta, vacia si cumplido) y nota (una linea)."
)


def GOLPE_TIMEOUT_S() -> int:
    """Por llamada: CALIPSO_GOAL_TIMEOUT_S (el smoke pone 180), default 900."""
    try:
        return max(30, int(os.environ.get("CALIPSO_GOAL_TIMEOUT_S", "900")))
    except ValueError:
        return 900


def es_fallo_de_cuota(texto: str) -> bool:
    low = (texto or "").lower()
    return any(p in low for p in PATRONES_CUOTA)


def otra_familia(manos: str) -> str:
    return "codex" if manos == "claude" else "claude"


# --------------------------------------------------------------------------
# settings, argv, env
# --------------------------------------------------------------------------

def settings_del_goal(compuertas: dict, *, hook_python: str | None = None,
                      hook_path: str | None = None,
                      compuertas_path: str | None = None) -> dict:
    """El `--settings` del golpe (terreno A.3, todas las claves CONFIRMADAS
    en el schema del binario 2.1.270): el sandbox nativo sobre bubblewrap
    con `failIfUnavailable: true` (sin eso falla ABIERTO: Trampa 7),
    `allowUnsandboxedCommands: false`, `excludedCommands: []`,
    `autoAllowBashIfSandboxed: true` (con acceptEdits + permission-prompts
    none un Bash sandboxeado corre sin prompt), escritura = el clon (o la
    carpeta de trabajo) + las raices, `denyRead` de las credenciales y de
    ~/.calipso (rutas ABSOLUTAS: con --settings inline no se sabe la raiz
    de resolucion), red = api.anthropic.com + los dominios del goal con
    `strictAllowlist: true` y github negado (el push es un hecho de red
    imposible). Y el hook PreToolUse en forma exec (A.4) con `--compuertas`
    de respaldo y `timeout: 20`.

    A VERIFICAR EN EL SMOKE (No confirmado 1, 3, 4, 5): que los `hooks` de
    --settings se ejecuten bajo -p --restricted (la sonda por golpe lo va a
    decir), que el sandbox arranque en esta maquina, que denyRead tape un
    `cat ~/.ssh/id_ed25519`, que HOME tapado no rompa pip/npm."""
    cwd = compuertas.get("cwd") or compuertas.get("clon")
    escritura = [cwd] + [os.path.expanduser(r) for r in compuertas.get("raices") or []]
    hook = [{"type": "command", "command": hook_python or HOOK_PYTHON,
             "args": [hook_path or str(HOOK_PATH)]
             + (["--compuertas", compuertas_path] if compuertas_path else []),
             "timeout": TIMEOUT_SONDA_S}]
    return {
        "sandbox": {
            "enabled": True,
            "failIfUnavailable": True,
            "allowUnsandboxedCommands": False,
            "excludedCommands": [],
            "autoAllowBashIfSandboxed": True,
            "filesystem": {
                "allowWrite": escritura,
                "denyRead": [os.path.expanduser(d) for d in DENY_READ],
            },
            "network": {
                "allowedDomains": [DOMINIO_API] + [str(d) for d in compuertas.get("dominios") or []],
                "deniedDomains": list(DOMINIOS_NEGADOS),
                "strictAllowlist": True,
            },
        },
        "hooks": {"PreToolUse": [{"matcher": MATCHER_HOOK, "hooks": hook}]},
    }


def argv_claude(exe: str, *, contrato: str, settings: dict, schema: dict,
                session_id: str, resume: bool, model: str | None = None,
                web: bool = False, raices: list[str] | None = None) -> list[str]:
    """`claude -p` con herramientas (terreno A.2: confirmadas por `--help`
    salvo `--append-system-prompt-file`, que `--help` de 2.1.270 no lista y
    esta confirmada por el uso del server en el turno real, server.py:3538,
    y por el texto de `--bare`; el smoke la ejercita): el prompt por stdin; `--permission-mode acceptEdits --permission-prompts
    none` (lo que pediria permiso se niega solo); `--restricted --tools
    <lista>` (WebSearch/WebFetch SOLO con dominios: decision 22);
    `--setting-sources ""` (ni plugins ni permissions.allow de Pedro),
    `--strict-mcp-config` (Trampa 1), `--settings <json inline>`,
    `stream-json --verbose --include-hook-events` (la sonda), `--json-schema`
    (el veredicto), `--session-id` en el golpe 1 y `--resume` despues
    (misma sesion, mismo cwd: Trampa 5), `--model` explicito (Trampa 6:
    con setting-sources vacio el model de ~/.claude/settings.json no
    aplica), `--add-dir` por cada raiz (spec 15.5: es lo que gobierna
    Write/Edit fuera del cwd; el smoke G3 vio al CLI negar un Write a una
    raiz aprobada aunque el hook la permitiera, y al martillo caer a mv por
    Bash). Nunca --max-turns (no existe), --bare, bypassPermissions ni
    --no-session-persistence (rompe --resume)."""
    tools = ",".join(HERRAMIENTAS + (HERRAMIENTAS_WEB if web else []))
    argv = [exe, "-p", "--permission-mode", "acceptEdits", "--permission-prompts", "none",
            "--restricted", "--tools", tools, "--setting-sources", "", "--strict-mcp-config",
            "--settings", json.dumps(settings, ensure_ascii=False),
            "--output-format", "stream-json", "--verbose", "--include-hook-events",
            "--json-schema", json.dumps(schema, ensure_ascii=False),
            "--append-system-prompt-file", contrato]
    argv += ["--resume", session_id] if resume else ["--session-id", session_id]
    for r in raices or []:
        argv += ["--add-dir", str(r)]
    if model:
        argv += ["--model", model]
    return argv


def argv_codex(exe: str, *, cwd: str, raices: list[str], salida: str, schema_file: str,
               model: str | None = None) -> list[str]:
    """`codex exec -s workspace-write` (terreno A.7): sandbox de kernel
    (landlock + seccomp) con la red APAGADA por defecto (ruling 15.10),
    `-C <clon>`, `--add-dir` por raiz, `--json`, `-o <ultimo mensaje>`,
    `--output-schema <archivo>` y el prompt por stdin (`-`). Sin
    `--ephemeral` (el jsonl de sesion es lo que consumo.py lee para
    resets_at). LA FORMA DE LAS LINEAS --json ES 'No confirmado 7': el
    veredicto se lee del archivo -o, no del stream."""
    argv = [exe, "exec"]
    if model:
        argv += ["-m", model]
    argv += ["-s", "workspace-write", "-C", cwd]
    for r in raices:
        argv += ["--add-dir", r]
    argv += ["--json", "-o", salida, "--output-schema", schema_file, "-"]
    return argv


def argv_systemd(argv: list[str], unidad: str, timeout_s: int) -> list[str]:
    """Cada golpe en su cgroup (terreno B: systemd-run --user --scope
    funciona en esta maquina; RuntimeMaxSec mata el scope entero, incluido
    lo que el martillo deje con nohup/setsid). El tope del scope va 30 s
    por encima del timeout propio: el que mata primero es golpear()."""
    return ["systemd-run", "--user", "--scope", f"--unit={unidad}", "-p",
            f"RuntimeMaxSec={int(timeout_s) + 30}", "--", *argv]


def env_del_golpe(compuertas_path: str, home_vacio: str, base: dict | None = None) -> dict:
    """`env_saneado` mas CALIPSO_GOAL_COMPUERTAS (el hook la hereda,
    decision 8) y CALIPSO_HOME apuntando a una carpeta VACIA del goal
    (spec seccion 7: fuera del alcance; si el martillo importa calipso, no
    ve el home real)."""
    env = env_saneado(base)
    env["CALIPSO_GOAL_COMPUERTAS"] = compuertas_path
    env["CALIPSO_HOME"] = home_vacio
    return env


# --------------------------------------------------------------------------
# el parser del stream-json
# --------------------------------------------------------------------------

class Parser:
    """Lee el stream-json linea a linea (terreno A.5): `system/init`
    (session_id, model, tools), `rate_limit_event` (la cuota de Claude por
    ventana: Trampa 4), `assistant` (un bloque por linea: los `tool_use`
    de Bash son los comandos; los `message.id` distintos cuentan llamadas si
    no llega el result), `system/hook_response` (la sonda), `user` con
    `tool_result` (el resultado de cada comando; y la VIOLACION si llega
    sin hook_response entre medio: Trampa 2), `result` (unidades =
    len(usage.iterations), veredicto = structured_output, costo). Un MCP en
    `init.tools` es violacion (Trampa 1). `alimentar` devuelve el motivo
    de la violacion la primera vez que la ve; None si no.

    La sonda del hook CUENTA, no aparea por orden: con dos tool_use en el
    mismo assistant (Claude Code corre en paralelo los Read/Grep/Glob) los
    hooks arrancan juntos y el stream sale en orden de terminacion, asi que
    el hook_response de B puede preceder al de A y el tool_result de B al
    hook_response de A. Como cada hook_response precede al tool_result de
    SU tool, `hook_response vistos < tool_result con hook vistos` es la
    unica senal fiable (y detecta igual el hook ausente en el primer
    resultado: 0 < 1). Si el hook_response trae `tool_use_id` (el terreno
    no lo vio; el smoke lo dira), ademas se aparea por id."""

    def __init__(self) -> None:
        self.session_id: str | None = None
        self.model: str | None = None
        self.tools: list[str] = []
        self.unidades = 0
        self.message_ids: set[str] = set()
        self.comandos: list[dict] = []
        self._tool_uses: dict[str, dict] = {}
        self.hooks = 0                          # hook_response PreToolUse vistos
        self._resultados_con_hook = 0           # tool_result de herramientas con hook vistos
        self._hook_ids: set[str] = set()        # tool_use_id de los hook_response, si los traen
        self._hooks_sin_id = 0
        self.veredicto: dict | None = None
        self.rate_limit: dict | None = None
        self.denials: list[dict] = []
        self.resultado: dict | None = None
        self.costo_usd: float | None = None
        self.violacion: str | None = None
        self.texto_final: str = ""
        self.error_texto: str = ""              # el `result` con is_error, y las lineas error/turn.failed

    def alimentar(self, linea: str) -> str | None:
        linea = (linea or "").strip()
        if not linea.startswith("{"):
            return None
        try:
            fila = json.loads(linea)
        except json.JSONDecodeError:
            return None
        tipo = fila.get("type")
        if tipo == "system":
            return self._system(fila)
        if tipo == "rate_limit_event":
            self._rate_limit(fila)
        elif tipo == "assistant":
            self._assistant(fila)
        elif tipo == "user":
            return self._user(fila)
        elif tipo == "result":
            self._result(fila)
        elif tipo in ("error", "turn.failed"):
            # donde un CLI cuenta por que corto (codex --json manda eventos
            # error/turn.failed; claude lo dice en el result con is_error)
            err = fila.get("error") if isinstance(fila.get("error"), dict) else {}
            texto = str(fila.get("message") or err.get("message") or "")
            if texto:
                self.error_texto = (self.error_texto + "\n" + texto).strip()
        return None

    def _violar(self, motivo: str) -> str:
        if self.violacion is None:
            self.violacion = motivo
        return motivo

    def _system(self, fila: dict) -> str | None:
        sub = fila.get("subtype")
        if sub == "init":
            self.session_id = fila.get("session_id") or self.session_id
            self.model = fila.get("model")
            self.tools = list(fila.get("tools") or [])
            raras = [t for t in self.tools if str(t).startswith("mcp__")]
            if raras:
                return self._violar(f"mcp inesperado en la sesion: {raras[:3]}")
        elif sub == "hook_response" and fila.get("hook_event") == "PreToolUse":
            # solo el hook_event explicito cuenta para la sonda (C4 del
            # cierre: uno sin hook_event contaba y tapaba un hook inactivo)
            self.hooks += 1
            if fila.get("tool_use_id"):
                self._hook_ids.add(str(fila["tool_use_id"]))
            else:
                self._hooks_sin_id += 1
        return None

    def _rate_limit(self, fila: dict) -> None:
        info = fila.get("rate_limit_info") or {}
        ventanas = info.get("unifiedWindows") or {}
        self.rate_limit = {
            "five_hour": (ventanas.get("five_hour") or {}).get("utilization"),
            "seven_day": (ventanas.get("seven_day") or {}).get("utilization"),
            "resets_at": info.get("resetsAt"),
        }

    def _assistant(self, fila: dict) -> None:
        msg = fila.get("message") or {}
        if msg.get("id"):
            self.message_ids.add(msg["id"])
        self.session_id = fila.get("session_id") or self.session_id
        for bloque in msg.get("content") or []:
            if bloque.get("type") == "text":
                self.texto_final = bloque.get("text") or self.texto_final
            if bloque.get("type") != "tool_use":
                continue
            nombre = bloque.get("name")
            tid = bloque.get("id")
            self._tool_uses[tid] = {"name": nombre, "input": bloque.get("input") or {}}
            if nombre == "Bash":
                self.comandos.append({"id": tid, "cmd": str((bloque.get("input") or {}).get("command") or ""),
                                      "resultado_tail": None, "error": None})

    def _user(self, fila: dict) -> str | None:
        msg = fila.get("message") or {}
        contenido = msg.get("content")
        if not isinstance(contenido, list):
            return None
        for bloque in contenido:
            if not isinstance(bloque, dict) or bloque.get("type") != "tool_result":
                continue
            tid = bloque.get("tool_use_id")
            uso = self._tool_uses.get(tid) or {}
            nombre = uso.get("name")
            if nombre in CON_HOOK:
                self._resultados_con_hook += 1
                if self.hooks < self._resultados_con_hook:
                    return self._violar(f"hook inactivo: tool_result de {nombre} sin hook_response "
                                        f"PreToolUse antes (tool_use {tid}: {self.hooks} hook_response "
                                        f"para {self._resultados_con_hook} resultados con hook)")
                if self._hook_ids and not self._hooks_sin_id and tid not in self._hook_ids:
                    return self._violar(f"hook inactivo: tool_result de {nombre} sin hook_response "
                                        f"PreToolUse para su tool_use ({tid})")
            if nombre == "Bash":
                salida = bloque.get("content")
                if isinstance(salida, list):
                    salida = " ".join(str(b.get("text", "")) for b in salida if isinstance(b, dict))
                for c in self.comandos:
                    if c["id"] == tid:
                        c["resultado_tail"] = str(salida or "")[-300:]
                        # la senal real de que el comando fallo (exit != 0):
                        # no_converge compara solo comandos con error
                        c["error"] = bool(bloque.get("is_error"))
        return None

    def _result(self, fila: dict) -> None:
        self.resultado = fila
        self.session_id = fila.get("session_id") or self.session_id
        if fila.get("is_error"):
            self.error_texto = (self.error_texto + "\n" + str(fila.get("result") or "")).strip()
        iteraciones = (fila.get("usage") or {}).get("iterations")
        if isinstance(iteraciones, list) and iteraciones:
            self.unidades = len(iteraciones)
        self.costo_usd = fila.get("total_cost_usd")
        self.denials = list(fila.get("permission_denials") or [])
        so = fila.get("structured_output")
        if isinstance(so, dict):
            self.veredicto = so
        else:
            try:
                v = json.loads(fila.get("result") or "")
                self.veredicto = v if isinstance(v, dict) else None
            except (TypeError, json.JSONDecodeError):
                self.veredicto = None

    def cerrar(self) -> None:
        """Al terminar el proceso: sin result, las unidades son los
        message.id distintos (decision 6)."""
        if self.resultado is None and self.message_ids:
            self.unidades = max(self.unidades, len(self.message_ids))


# --------------------------------------------------------------------------
# el golpe: Popen con sesion propia, sondeado, timeout que mata el grupo
# --------------------------------------------------------------------------

@dataclasses.dataclass
class Resultado:
    exit: int | None = None
    motivo: str | None = None          # None | "timeout" | "cancelado" | "hook inactivo: ..." | "mcp inesperado..."
    timeout: bool = False
    matado: bool = False
    session_id: str | None = None
    unidades: int = 0
    comandos: list = dataclasses.field(default_factory=list)
    veredicto: dict | None = None
    rate_limit: dict | None = None
    denials: list = dataclasses.field(default_factory=list)
    duracion_ms: int = 0
    costo_usd: float | None = None
    stderr_tail: str = ""
    stdout_tail: str = ""
    secretos_tapados: int = 0
    subtype: str | None = None
    model: str | None = None
    reintento: str | None = None       # la autocorreccion --session-id/--resume (goals_runner.correccion_de_sesion)
    error_texto: str = ""              # Parser.error_texto: el result con is_error, los eventos error

    def a_dict(self) -> dict:
        return dataclasses.asdict(self)


def lanzar(argv: list[str], cwd: str, env: dict, stdout_f, stderr_f) -> subprocess.Popen:
    """El Popen del golpe: sesion propia (`start_new_session=True`: el
    grupo entero muere con killpg, incluido lo que el martillo deje con
    nohup), stdin en PIPE (el prompt), stdout/stderr a archivos (sondeados
    desde `golpear`). Canario de la aduana: `modelo:` (CLI de suscripcion;
    el cruce lo hace el runner alrededor, decision 23)."""
    return subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=stdout_f,
                            stderr=stderr_f, text=True, encoding="utf-8", errors="replace",
                            start_new_session=True)


def unidad_activa(unidad: str) -> bool:
    """`systemctl --user is-active <unidad>` == 0: el scope existe y corre
    (canario: local). La reconciliacion del arranque lo pregunta antes de
    parar el scope de un golpe cortado para anotar si habia un huerfano
    (el server murio sin shutdown y el golpe siguio solo). Sin systemctl o
    ante cualquier error, False."""
    try:
        r = subprocess.run(["systemctl", "--user", "is-active", unidad], capture_output=True, text=True,
                           timeout=10)
    except Exception:
        return False
    return r.returncode == 0


def _parar_unidad(unidad: str) -> None:
    """`systemctl --user stop <unidad>`: el scope entero (canario: local)."""
    try:
        subprocess.run(["systemctl", "--user", "stop", unidad], capture_output=True, text=True,
                       timeout=10)
    except Exception:
        pass


def matar(proc: subprocess.Popen, unidad: str | None = None) -> None:
    """SIGTERM al grupo, GRACIA_KILL_S, SIGKILL al grupo; y el scope si lo
    hubo. Nunca levanta."""
    for senal in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, senal)
        except ProcessLookupError:
            break
        except Exception:
            pass
        limite = time.monotonic() + GRACIA_KILL_S
        while time.monotonic() < limite and proc.poll() is None:
            time.sleep(0.05)
        if proc.poll() is not None:
            break
    if unidad:
        _parar_unidad(unidad)
    try:
        proc.wait(timeout=GRACIA_KILL_S)
    except Exception:
        pass


def publicar(al_lanzar: Callable | None, proc: subprocess.Popen, unidad: str | None) -> None:
    """`al_lanzar(proc, unidad)` -- el runner guarda las dos cosas
    (registrar_golpe) para que matar_golpe pare el scope ademas del grupo;
    un `al_lanzar` de un solo parametro (`vistos.append` de los tests) se
    llama como antes. Nunca levanta: publicar no puede tumbar el golpe."""
    if al_lanzar is None:
        return
    try:
        al_lanzar(proc, unidad)
    except TypeError:
        try:
            al_lanzar(proc)
        except Exception:
            pass
    except Exception:
        pass


def golpear(*, argv: list[str], stdin: str, cwd: str, env: dict, timeout_s: float,
            cancelar: threading.Event | None = None, usar_systemd: bool | None = None,
            unidad: str | None = None, sondeo_s: float = SONDEO_S,
            parser: Parser | None = None,
            al_lanzar: Callable[[subprocess.Popen], None] | None = None,
            lanzar_fn: Callable | None = None) -> Resultado:
    """UN golpe, bloqueante (se llama en hilo desde el runner): lanza,
    escribe el prompt por stdin, sondea cada `sondeo_s` el stdout (lineas
    nuevas al parser), y mata el grupo ante timeout, `cancelar` (el apagado
    del server, /goal parar) o una violacion del parser (hook inactivo,
    mcp inesperado: ruling 15.5). Devuelve el Resultado con lo que se
    alcanzo a parsear. `usar_systemd` None = si `systemd-run` esta en PATH
    y hay `unidad`. `al_lanzar(proc)` se llama apenas existe el Popen: asi
    el runner publica el handle en `golpe_en_curso` (decision 17) y
    `matar_golpe` tiene a quien matar; recibe tambien la unidad del scope
    (None sin systemd) para pararla ademas del grupo. `lanzar_fn` es el
    Popen que se usa (`lanzar`, el CLI de suscripcion; `lanzar_confinado`,
    el criterio bajo bwrap): el sondeo, el timeout, cancelar y el scope
    son los mismos para los dos."""
    parser = parser or Parser()
    if usar_systemd is None:
        usar_systemd = bool(unidad) and shutil.which("systemd-run") is not None
    cmd = argv_systemd(argv, unidad, int(timeout_s)) if (usar_systemd and unidad) else argv
    scope = unidad if (usar_systemd and unidad) else None
    r = Resultado()
    t0 = time.monotonic()
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", errors="replace", suffix=".golpe.stdout",
                                     delete=False) as out_f, \
            tempfile.NamedTemporaryFile("w+", encoding="utf-8", errors="replace", suffix=".golpe.stderr",
                                        delete=False) as err_f:
        out_name, err_name = out_f.name, err_f.name
    try:
        with open(out_name, "w", encoding="utf-8") as out_f, open(err_name, "w", encoding="utf-8") as err_f:
            try:
                proc = (lanzar_fn or lanzar)(cmd, cwd, env, out_f, err_f)
            except Exception as exc:
                r.exit, r.motivo, r.stderr_tail = 127, f"no se pudo lanzar: {exc}", str(exc)
                return r
            publicar(al_lanzar, proc, scope)

            def _escribir_stdin() -> None:
                # en hilo: un prompt mas largo que el buffer del pipe (64 KB:
                # el ledger con las `falta` sin recortar) bloquearia el write
                # hasta que el CLI lea, y el sondeo de abajo no correria
                try:
                    proc.stdin.write(stdin)
                    proc.stdin.close()
                except Exception:
                    pass
            threading.Thread(target=_escribir_stdin, daemon=True).start()
            offset = 0
            resto = ""
            with open(out_name, "r", encoding="utf-8", errors="replace") as lector:
                while True:
                    lector.seek(offset)
                    trozo = lector.read()
                    offset = lector.tell()
                    if trozo:
                        resto += trozo
                        lineas = resto.split("\n")
                        resto = lineas.pop()
                        for l in lineas:
                            v = parser.alimentar(l)
                            if v:
                                r.motivo, r.matado = v, True
                                matar(proc, scope)
                                break
                    # `cancelar` ANTES de poll(): parar/apagar matan el CLI
                    # (muere en ms) y el sondeo lo veria muerto antes que
                    # cancelado, dejando la fila con motivo None
                    if cancelar is not None and cancelar.is_set():
                        r.motivo, r.matado = "cancelado", True
                        matar(proc, scope)
                        break
                    if proc.poll() is not None:
                        break
                    if time.monotonic() - t0 > timeout_s:
                        r.motivo, r.timeout, r.matado = "timeout", True, True
                        matar(proc, scope)
                        break
                    time.sleep(sondeo_s)
                lector.seek(offset)
                for l in (resto + lector.read()).split("\n"):
                    if l.strip() and not r.matado:
                        parser.alimentar(l)
            try:
                proc.wait(timeout=GRACIA_KILL_S)
            except Exception:
                pass
            r.exit = proc.returncode
        parser.cerrar()
        with open(err_name, "r", encoding="utf-8", errors="replace") as f:
            r.stderr_tail = f.read()[-2000:]
        with open(out_name, "r", encoding="utf-8", errors="replace") as f:
            r.stdout_tail = f.read()[-2000:]
    finally:
        for n in (out_name, err_name):
            try:
                os.unlink(n)
            except OSError:
                pass
    r.duracion_ms = int((time.monotonic() - t0) * 1000)
    r.session_id = parser.session_id
    r.unidades = parser.unidades
    r.comandos = parser.comandos
    r.veredicto = parser.veredicto
    r.rate_limit = parser.rate_limit
    r.denials = parser.denials
    r.costo_usd = parser.costo_usd
    r.subtype = (parser.resultado or {}).get("subtype")
    r.model = parser.model
    r.error_texto = parser.error_texto
    return r


def texto_de_fallo(r: Resultado) -> str:
    """Donde el CLI dice por que fallo, para `es_fallo_de_cuota`: stderr,
    el `result` con is_error del stream (claude puede mandar el limite ahi
    con exit 1, no por stderr: antes ese golpe contaba contra el tope y el
    goal repetia golpes fallidos) y las lineas SUELTAS del stdout (no JSON:
    un error impreso a secas). Las lineas JSON del stream no entran:
    `rate_limit_event` esta en todo stream de claude y `rate_limit` es un
    patron de cuota, un exit 1 por otra cosa pareceria cuota."""
    sueltas = [l for l in (r.stdout_tail or "").splitlines()
               if l.strip() and not l.lstrip().startswith("{")]
    return "\n".join([r.stderr_tail or "", r.error_texto or "", *sueltas])


# --------------------------------------------------------------------------
# el criterio confinado: bwrap espejo del sandbox del golpe
# --------------------------------------------------------------------------

CRITERIO_TIMEOUT_S = 600


class _SinParser(Parser):
    """El sondeo de `golpear` sin leer el stream: el criterio (pytest, make)
    no habla stream-json, y una linea suya que casualmente fuera JSON no
    puede contar como veredicto ni como violacion."""

    def alimentar(self, linea: str) -> str | None:
        return None


def resolver_exe(exe: str, cwd: str, path: str) -> list[str] | None:
    """El ejecutable del criterio, resuelto ANTES de entrar al sandbox
    (rev:lente-riesgo: el PATH del server real no tiene .venv/bin y todo
    `pytest -q` fallaba con Errno 2): una ruta (`./check.sh`,
    `.venv/bin/pytest`, `/usr/bin/make`) contra el cwd; si no,
    `<cwd>/.venv/bin/<exe>` > el PATH que recibe el proceso > para
    pytest/python/python3 el interprete del server (`-m pytest`). None si
    no hay como correrlo."""
    if "/" in exe:
        ruta = os.path.normpath(os.path.join(cwd, exe)) if not os.path.isabs(exe) else exe
        return [ruta] if os.path.isfile(ruta) and os.access(ruta, os.X_OK) else None
    venv = os.path.join(cwd, ".venv", "bin", exe)
    if os.path.isfile(venv) and os.access(venv, os.X_OK):
        return [venv]
    w = shutil.which(exe, path=path or None)
    if w:
        return [w]
    if exe == "pytest":
        return [sys.executable, "-m", "pytest"]
    if exe in ("python", "python3"):
        return [sys.executable]
    return None


def argv_bwrap(argv: list[str], *, cwd: str, compuertas: dict, bwrap: str = "bwrap") -> list[str]:
    """El espejo del sandbox del golpe (settings_del_goal) en bubblewrap
    (ruling del cierre, criterio confinado): todo el sistema de solo
    lectura, /dev y /proc nuevos, /tmp privado, el clon (o la carpeta de
    trabajo) y las raices declaradas escribibles, un tmpfs vacio sobre cada
    DENY_READ que exista (~/.ssh, ~/.calipso...; un DENY_READ que es un
    ARCHIVO, `~/.claude/.credentials.json`, no admite tmpfs y se tapa con
    /dev/null de solo lectura), sin red, y el comando muere con bwrap
    (`--die-with-parent`: killpg sobre bwrap lo alcanza aunque
    `--new-session` lo ponga en otra sesion). El clon se monta DESPUES del
    tmpfs de /tmp: en los tests vive ahi abajo. Una raiz que no existe no
    se monta (bwrap fallaria entero)."""
    out = [bwrap, "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--tmpfs", "/tmp",
           "--bind", cwd, cwd]
    for r in compuertas.get("raices") or []:
        ruta = os.path.expanduser(str(r))
        if os.path.isdir(ruta):
            out += ["--bind", ruta, ruta]
    for d in DENY_READ:
        ruta = os.path.expanduser(d)
        if os.path.isdir(ruta):
            out += ["--tmpfs", ruta]
        elif os.path.exists(ruta):
            out += ["--ro-bind", "/dev/null", ruta]
    out += ["--unshare-net", "--die-with-parent", "--new-session", "--chdir", cwd, "--", *argv]
    return out


def lanzar_confinado(argv: list[str], cwd: str, env: dict, stdout_f, stderr_f) -> subprocess.Popen:
    """El Popen del criterio bajo bwrap (canario: local, no sale de la
    maquina: `--unshare-net`). Sesion propia como el golpe: killpg mata a
    bwrap y bwrap mata lo de adentro."""
    return subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE, stdout=stdout_f,
                            stderr=stderr_f, text=True, encoding="utf-8", errors="replace",
                            start_new_session=True)


def correr_confinado(argv: list[str], *, cwd: str, compuertas: dict, timeout_s: float,
                     unidad: str | None = None, al_lanzar: Callable | None = None,
                     cancelar: threading.Event | None = None, env: dict | None = None,
                     usar_systemd: bool | None = None, sondeo_s: float = SONDEO_S) -> Resultado:
    """UN comando local bajo la barrera del golpe (el criterio medible:
    critico del cierre 2026-09-14, el comando corria como Pedro con el HOME
    real, red y ~/.ssh legibles, ejecutando lo que el martillo dejo en el
    clon). Fail-closed: sin bwrap en el PATH no se corre (motivo en el
    Resultado, el juez lo dice). `env` es el del golpe (env_del_golpe:
    CALIPSO_HOME vacio), con `<cwd>/.venv/bin` primero en el PATH; el
    ejecutable se resuelve afuera (`resolver_exe`). Sondeo, timeout que
    mata el grupo y el scope, `cancelar` y `al_lanzar(proc, unidad)`: los
    de `golpear`."""
    bwrap = shutil.which("bwrap")
    if not bwrap:
        return Resultado(exit=None, motivo="criterio: sin bwrap no se corre (barrera)")
    env = dict(env if env is not None else env_saneado())
    env["PATH"] = str(pathlib.Path(cwd) / ".venv" / "bin") + os.pathsep + (env.get("PATH") or os.defpath)
    if not argv:
        return Resultado(exit=None, motivo="criterio vacio: no se corre")
    resuelto = resolver_exe(str(argv[0]), cwd, env["PATH"])
    if not resuelto:
        return Resultado(exit=None,
                         motivo=f"criterio: {argv[0]} no esta en el PATH del server ni en el venv del clon")
    cmd = argv_bwrap([*resuelto, *[str(a) for a in argv[1:]]], cwd=cwd, compuertas=compuertas, bwrap=bwrap)
    return golpear(argv=cmd, stdin="", cwd=cwd, env=env, timeout_s=timeout_s, cancelar=cancelar,
                   usar_systemd=usar_systemd, unidad=unidad, sondeo_s=sondeo_s, parser=_SinParser(),
                   al_lanzar=al_lanzar, lanzar_fn=lanzar_confinado)


def sondear_hook(compuertas_path: str, *, hook_python: str | None = None,
                 hook_path: str | None = None, cwd: str | None = None) -> tuple[bool, str]:
    """Antes del primer golpe de cada goal (ruling 15.5): el hook real con
    stdin sintetico (`gh pr create`) tiene que salir 2. Cualquier otra
    cosa (0, 1, timeout, no existe) = el goal no corre. Canario: local."""
    evento = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                         "tool_input": {"command": "gh pr create --fill"},
                         "tool_use_id": "sonda", "cwd": cwd or ""})
    argv = [hook_python or HOOK_PYTHON, hook_path or str(HOOK_PATH), "--compuertas", compuertas_path]
    try:
        r = subprocess.run(argv, input=evento, capture_output=True, text=True,
                           timeout=TIMEOUT_SONDA_S,
                           env={**env_saneado(), "CALIPSO_GOAL_COMPUERTAS": compuertas_path})
    except subprocess.TimeoutExpired:
        return False, f"la sonda del hook vencio a los {TIMEOUT_SONDA_S} s"
    except Exception as exc:
        return False, f"no se pudo correr el hook: {exc}"
    if r.returncode != 2:
        return False, f"el hook dejo pasar `gh pr create` (exit {r.returncode}): {r.stderr.strip()[:200]}"
    if "DENEGADO" not in r.stderr:
        return False, f"el hook salio 2 sin motivo: {r.stderr.strip()[:200]}"
    return True, "hook activo: gh pr create -> exit 2"


# --------------------------------------------------------------------------
# el detector de secretos sobre lo que va al ledger y al prompt
# --------------------------------------------------------------------------

# una ruta de archivo: absoluta, ~/ o ./ y ../, dos o mas barras, segmentos de
# caracteres de ruta (sin + ni =, que son de base64) y cortos
_RE_RUTA = re.compile(r"^(?:~|\.{1,2})?/(?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-]*$")


def _es_secreto_explicito(t: str) -> bool:
    """Lo que el detector marca por una REGLA (prefijo conocido, JWT, PEM,
    cadena de conexion, hex de 32+, base32), no por entropia."""
    d = detector
    if any(rx.search(t) for rx in (d._PREFIJOS, d._JWT, d._PEM, d._CONN, d._HEX)):
        return True
    return any(re.search(r"[2-7]", m.group(0)) for m in d._BASE32.finditer(t))


def _es_ruta(t: str) -> bool:
    """Un tramo que solo la regla de entropia del detector marcaria y que es
    una ruta de archivo (smoke corrida 5: `/tmp/goals-smoke-<x>/Descargas`
    tapada en el prompt; en produccion 43/300 rutas de clon y 286/300 de
    contrato.md con ids hex al azar). Una ruta no es un secreto; un secreto
    DENTRO de una ruta (`/tmp/x/ghp_...`, un hex de 32) sigue siendo
    explicito y se tapa igual."""
    return (bool(_RE_RUTA.match(t)) and t.count("/") >= 2
            and all(len(seg) <= 64 for seg in t.split("/")) and not _es_secreto_explicito(t))


def _tapar_segmentos(ruta: str) -> tuple[str, int]:
    """Una ruta que el detector marco entera solo por entropia: se tapan
    los segmentos que el detector marca SOLOS (`/tmp/x/<blob>`,
    `~/.ssh/<clave>`: donde aparece un secreto en un `ls`/`find`), y el
    resto de la ruta queda. Un secreto con barras pegado detras de un
    prefijo de ruta (`/x/y/` + una clave AWS) no tiene segmento que marque
    solo y no se tapa: juntar segmentos volveria a tapar rutas normales
    (`goals-smoke-x/Descargas`, dos carpetas CamelCase), que es lo que
    f15f918 saco del prompt y del ledger."""
    partes = ruta.split("/")
    n = 0
    for i, seg in enumerate(partes):
        if seg and detector.detectar_secretos(seg):
            partes[i] = "[SECRETO]"
            n += 1
    return "/".join(partes), n


def tapar(texto: str) -> tuple[str, int]:
    """Molde aduana._tapar_todo: los tramos del detector, del mas largo al
    mas corto, reemplazados por [SECRETO]. Devuelve (texto, cuantos). Una
    ruta de archivo que el detector marca solo por entropia (`_es_ruta`)
    no se tapa entera (el prompt y el ledger del goal estan hechos de
    rutas): se tapan sus segmentos con pinta de secreto, si los hay."""
    n = 0
    for t in sorted(detector.detectar_secretos(texto or ""), key=lambda x: len(x["texto"]), reverse=True):
        literal = t["texto"]
        if _es_ruta(literal):
            nuevo, k = _tapar_segmentos(literal)
        else:
            nuevo, k = "[SECRETO]", 1
        if k:
            texto = texto.replace(literal, nuevo)
            n += k
    return texto, n


def tapar_fila(fila: dict) -> tuple[dict, int]:
    """Recursivo sobre str/list/dict; salta SIN_TAPAR (session_id, shas del
    diff_stat: Trampa 19)."""
    total = 0

    def _t(v, clave=None):
        nonlocal total
        if clave in SIN_TAPAR:
            return v
        if isinstance(v, str):
            s, n = tapar(v)
            total += n
            return s
        if isinstance(v, list):
            return [_t(x) for x in v]
        if isinstance(v, dict):
            return {k: _t(x, k) for k, x in v.items()}
        return v
    return _t(fila), total


# --------------------------------------------------------------------------
# el revisor de otra familia
# --------------------------------------------------------------------------

def revisar(*, manos_del_golpe: str, exes: dict, goal_texto: str, criterio: dict,
            resumen_ledger: str, diff: str, salidas: str, cwd: str, env: dict | None = None,
            timeout: float = TIMEOUT_REVISOR_S, al_lanzar: Callable | None = None,
            compuertas: dict | None = None, compuertas_path: str | None = None,
            cancelar: threading.Event | None = None) -> dict | None:
    """El revisor de OTRA familia en solo lectura sobre el clon (spec
    seccion 6.2): manos claude -> `codex exec -s read-only`; manos codex ->
    `claude -p --restricted --tools Read,Glob,Grep` CON la barrera del golpe
    (cierre 2026-09-14: sin --settings era una sesion con lectura sobre
    todo el disco, y lo que lee viaja a la API): `settings_del_goal`
    (sandbox con denyRead + el hook, cuyo matcher incluye Read|Glob|Grep),
    el env del golpe (CALIPSO_GOAL_COMPUERTAS, CALIPSO_HOME vacio) y la
    sonda del Parser (un tool_result sin hook_response = matar). Sin
    `compuertas` el revisor claude va SIN herramientas (fail-closed: solo el
    diff y las salidas que le mandamos). El de codex corre con `-s
    read-only`: su sandbox no restringe lecturas del home (residuo
    declarado en la adenda). `diff` es el diff COMPLETO (ruling 15.1).

    None si la otra familia no esta (`exes` sin su ejecutable): no hay
    veredicto de modelo (decision 15). Si esta y falla (exit != 0, timeout,
    hook inactivo, sin JSON) vuelve un dict con `cumplido: None`, el
    `motivo` y `salida_tail` (el runner lo anota en la fila del revisor).
    Siempre trae `unidades` (claude: las del stream; codex: 1 si contesto)
    y `revisor`. Cuenta como golpe y se cobra: lo hace el runner, que
    ademas recibe el Popen por `al_lanzar`."""
    otra = otra_familia(manos_del_golpe)
    exe = (exes or {}).get(otra)
    if not exe:
        return None
    prompt = (f"GOAL: {goal_texto}\nCRITERIO: {json.dumps(criterio or {}, ensure_ascii=False)}\n\n"
              f"LEDGER (resumen):\n{resumen_ledger}\n\nDIFF:\n{diff[:20000]}\n\nSALIDAS:\n{salidas[:8000]}\n")
    prompt, _ = tapar(prompt)
    settings, tools = None, ""
    if otra == "claude" and compuertas is not None:
        settings = settings_del_goal(compuertas, compuertas_path=compuertas_path)
        tools = HERRAMIENTAS_LECTURA
        if env is None and compuertas_path:
            home_vacio = pathlib.Path(compuertas_path).parent / "home_vacio"
            home_vacio.mkdir(exist_ok=True)
            env = env_del_golpe(compuertas_path, str(home_vacio))
    c = cabeza(otra, exe, CONTRATO_REVISOR, prompt, ESQUEMA_REVISOR, cwd=cwd, env=env, timeout=timeout,
               tools=tools, al_lanzar=al_lanzar, settings=settings, cancelar=cancelar)
    base = {"revisor": otra, "unidades": int(c.unidades or 0)}
    v = c.veredicto
    if not isinstance(v, dict) or "cumplido" not in v:
        return {**base, "cumplido": None, "motivo": c.motivo or "sin veredicto del revisor",
                "salida_tail": c.salida_tail}
    return {**base, "cumplido": bool(v.get("cumplido")), "falta": [str(x) for x in (v.get("falta") or [])],
            "nota": str(v.get("nota") or "")}
