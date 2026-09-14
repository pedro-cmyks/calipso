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

import json
import os
import pathlib
import subprocess
import tempfile

from calipso import github as calipso_github
from calipso import goals

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
                       model: str | None = None) -> list[str]:
    """`claude -p` sin herramientas (terreno A.2/A.6, confirmadas por
    `--help` salvo `--append-system-prompt-file`, que `--help` de 2.1.270 no
    lista: esta confirmada por el uso del server en el turno real
    (server.py:3538) y por el texto de `--bare`, y el smoke la ejercita):
    `--restricted --tools ""` (ninguna builtin), `--setting-sources ""`
    (ni los 90 permissions.allow ni los plugins de Pedro), `--strict-mcp-config`
    (Trampa 1: sin esto entra el MCP de Google Drive), `stream-json` con
    `--verbose` (obligatorio) y `--json-schema` inline. El prompt va por
    stdin."""
    argv = [exe, "-p", "--restricted", "--tools", "", "--setting-sources", "",
            "--strict-mcp-config", "--output-format", "stream-json", "--verbose",
            "--json-schema", json.dumps(schema, ensure_ascii=False),
            "--append-system-prompt-file", contrato]
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
                   timeout: float) -> tuple[int, str, str]:
    """El unico subprocess de la cabeza: CLI de suscripcion, lo mide la
    telemetria y la economia (canario: `modelo:`). Bloqueante: se llama en
    hilo (`asyncio.to_thread`) y con timeout."""
    try:
        r = subprocess.run(argv, input=stdin, cwd=cwd, env=env, text=True,
                           capture_output=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
        return (r.returncode, r.stdout or "", r.stderr or "")
    except subprocess.TimeoutExpired:
        return (124, "", f"timeout a los {timeout} s")
    except Exception as e:
        return (1, "", str(e))


def cabeza_sin_herramientas(client: str, exe: str, system: str, prompt: str,
                            schema: dict, *, cwd: str, env: dict | None = None,
                            model: str | None = None,
                            timeout: float = TIMEOUT_CABEZA_S) -> dict | None:
    """Un golpe SIN herramientas: devuelve el JSON del esquema o None (exit
    distinto de 0, timeout, sin JSON). El contrato (`system`) se escribe en
    un temporal FUERA de `cwd` y se borra al salir; el prompt va por stdin.
    `cwd` tiene que ser un directorio vacio o de solo lectura para el
    modelo: la cabeza no tiene herramientas, pero el CLI lista el cwd al
    arrancar."""
    env = env if env is not None else env_saneado()
    temporales: list[str] = []
    try:
        if client == "claude":
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".contrato.md",
                                             delete=False) as f:
                f.write(system)
                temporales.append(f.name)
            argv = argv_cabeza_claude(exe, temporales[0], schema, model)
            rc, out, _ = _correr_cabeza(argv, prompt, cwd, env, timeout)
            if rc != 0:
                return None
            return goals.structured_output_de(out)
        if client == "codex":
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".schema.json",
                                             delete=False) as f:
                json.dump(schema, f)
                temporales.append(f.name)
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".salida.txt",
                                             delete=False) as f:
                temporales.append(f.name)
            argv = argv_cabeza_codex(exe, cwd, temporales[1], temporales[0], model)
            rc, out, _ = _correr_cabeza(argv, f"{system}\n\n{prompt}", cwd, env, timeout)
            if rc != 0:
                return None
            try:
                texto = pathlib.Path(temporales[1]).read_text(encoding="utf-8").strip()
                v = json.loads(texto) if texto else None
                return v if isinstance(v, dict) else None
            except (OSError, json.JSONDecodeError):
                return None
        return None
    finally:
        for t in temporales:
            try:
                os.unlink(t)
            except OSError:
                pass
