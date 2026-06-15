#!/usr/bin/env python3
"""
dispatch.py — Orquestador multi-modelo en terminal.

Tres "bocas":
  1. SUSCRIPCIÓN  -> lanza el CLI oficial (claude / codex) como subproceso.
                     Usa tu cuota Pro/Max o ChatGPT. NO gasta API.
  2. API          -> habla con un proxy LiteLLM local que unifica
                     Anthropic + OpenAI + DeepSeek bajo un endpoint OpenAI.
  3. LOCAL        -> Ollama, para tareas triviales / privadas.

Routing HÍBRIDO:
  - Primero intenta decidir por REGLAS (flags + palabras clave).
  - Si las reglas no dan veredicto claro, pregunta a un modelo
    clasificador LOCAL (Ollama) que devuelve JSON.

Uso:
  python dispatch.py "refactoriza este módulo y agrega tests"
  python dispatch.py --route local "resume este texto"
  python dispatch.py --dry-run "explícame esta arquitectura"
"""

from __future__ import annotations
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

try:
    from calipso.config import dispatch_config, load_config
except Exception:
    dispatch_config = None
    load_config = None

# ----------------------------------------------------------------------------
# CONFIGURACIÓN  (ajusta a tu entorno)
# ----------------------------------------------------------------------------

CONFIG = {
    # --- Boca SUSCRIPCIÓN ---
    # Comandos del CLI oficial. {prompt} se reemplaza por tu petición.
    # IMPORTANTE: para usar la suscripción, NO debe existir ANTHROPIC_API_KEY
    # en el entorno del subproceso (la borramos abajo en run_subscription()).
    "subscription": {
        "claude": ["claude", "-p", "{prompt}"],          # Claude Code headless
        "codex":  ["codex", "exec", "{prompt}"],         # Codex headless
    },

    # --- Boca API (LiteLLM proxy local, formato OpenAI) ---
    "api": {
        "base_url": "http://localhost:4000/v1/chat/completions",
        # Mejor desde el entorno; cae al default local si no está exportada.
        "api_key": os.environ.get("LITELLM_MASTER_KEY", "sk-litellm-local"),
        "model": "deepseek-chat",        # modelo por defecto para la ruta API
    },

    # --- Boca LOCAL (Ollama) ---
    "local": {
        "base_url": "http://localhost:11434/api/generate",
        "model": "qwen2.5:7b",           # modelo de ejecución local
    },

    # --- Clasificador (también Ollama, modelo pequeño y rápido) ---
    "classifier": {
        "base_url": "http://localhost:11434/api/generate",
        "model": "qwen2.5:3b",
    },
}

if dispatch_config:
    CONFIG = dispatch_config()

# Ruta a la que caemos si el clasificador local falla. "local" para no escalar
# a una API de pago por accidente (privacidad/coste).
SAFE_FALLBACK = "local"

# Log de decisiones (JSONL). Sirve para afinar luego los regex con datos reales.
# Se puede desactivar con --no-log o DISPATCH_NO_LOG=1.
LOG_PATH = os.path.expanduser(os.environ.get(
    "DISPATCH_LOG", "~/.dispatch/decisions.jsonl"))
LOG_PROMPT_MAX = 500  # se trunca el prompt guardado (privacidad/tamaño)

# ----------------------------------------------------------------------------
# CAPA 1: REGLAS  (rápidas, deterministas, gratis)
# ----------------------------------------------------------------------------

# Palabras que sugieren tarea de CÓDIGO pesada e interactiva -> suscripción.
CODE_HEAVY = re.compile(
    r"\b(refactor|refactoriza|implementa|debug|depura|test|tests|"
    r"arregla|build|compila|migra|repositorio|repo|pull request|stack trace)\b",
    re.IGNORECASE,
)

# Palabras que sugieren tarea TRIVIAL / privada -> local.
TRIVIAL = re.compile(
    r"\b(resume|resumen|traduce|traducir|reformula|clasifica|"
    r"corrige ortograf|formatea|lista|extrae)\b",
    re.IGNORECASE,
)

# Palabras que sugieren razonamiento amplio barato -> API (DeepSeek).
CHEAP_REASONING = re.compile(
    r"\b(explica|compara|analiza|brainstorm|ideas|borrador|draft|"
    r"investiga|pros y contras)\b",
    re.IGNORECASE,
)


def decide_by_rules(prompt: str) -> dict | None:
    """Devuelve un veredicto {ruta, cliente} o None si no está claro.

    PRECEDENCIA (el orden importa):
      1. Código pesado      -> suscripción (gana siempre, aunque sea largo).
      2. Trivial / privado  -> local (la privacidad/coste mandan; el tamaño NO
                               lo manda a suscripción, antes era un bug).
      3. Razonamiento barato-> API.
      4. Solo-tamaño        -> suscripción (prompt muy largo sin otra señal:
                               necesita contexto grande).
      5. Nada claro         -> None (pasa al clasificador).
    """
    p = prompt.strip()
    long_prompt = len(p) > 800
    routing = (load_config() if load_config else {}).get("routing", {})
    sub_client = routing.get("subscription_client", "claude")
    subscription_first = routing.get("policy", "subscription_first") == "subscription_first"

    if CODE_HEAVY.search(p):
        return {"route": "subscription", "client": sub_client,
                "why": "tarea de código pesada"}

    if TRIVIAL.search(p):
        return {"route": "local", "client": None,
                "why": "tarea trivial/privada (local aunque sea larga)"}

    if CHEAP_REASONING.search(p):
        if subscription_first:
            return {"route": "subscription", "client": sub_client,
                    "why": "razonamiento amplio; politica suscripcion primero"}
        return {"route": "api", "client": None,
                "why": "razonamiento barato"}

    if long_prompt:
        return {"route": "subscription", "client": sub_client,
                "why": "prompt largo sin señal clara; necesita contexto grande"}

    return None  # -> pasa al clasificador


# ----------------------------------------------------------------------------
# CAPA 2: CLASIFICADOR LOCAL  (solo si las reglas no decidieron)
# ----------------------------------------------------------------------------

CLASSIFIER_SYSTEM = (
    "Eres un enrutador. Clasifica la PETICIÓN del usuario en UNA ruta. "
    "Responde SOLO con JSON, sin texto extra, sin markdown.\n"
    "Rutas posibles:\n"
    '  "subscription" -> tarea de código compleja/interactiva (usar claude o codex)\n'
    '  "api"          -> razonamiento general, análisis, redacción\n'
    '  "local"        -> tarea trivial, corta o sensible a privacidad\n'
    'Formato exacto: {"route":"...","client":"claude|codex|null","why":"..."}'
)


def decide_by_model(prompt: str) -> dict:
    cfg = CONFIG["classifier"]
    full = (
        f"{CLASSIFIER_SYSTEM}\n\nPETICIÓN:\n{prompt}\n\nJSON:"
    )
    payload = {
        "model": cfg["model"],
        "prompt": full,
        "stream": False,
        "format": "json",      # Ollama fuerza salida JSON válida
        "options": {"temperature": 0},
    }
    try:
        raw = _http_post_json(cfg["base_url"], payload)
        text = raw.get("response", "{}")
        data = json.loads(text)
        # Normaliza
        route = data.get("route", "api")
        if route not in ("subscription", "api", "local"):
            route = "api"
        client = data.get("client")
        if client in ("null", "", None):
            client = "claude" if route == "subscription" else None
        return {"route": route, "client": client, "source": "model",
                "why": data.get("why", "decisión del clasificador")}
    except Exception as e:
        # Fallback SEGURO: nunca escalar a una API de pago en silencio si el
        # clasificador local falla (privacidad/coste). Caemos a LOCAL; si Ollama
        # también está caído, run_local() fallará de forma visible, no oculta.
        return {"route": SAFE_FALLBACK, "client": None, "source": "fallback",
                "why": f"clasificador falló ({e}); fallback seguro a {SAFE_FALLBACK}"}


def route(prompt: str, forced: str | None) -> dict:
    if forced:
        client = "claude" if forced == "subscription" else None
        return {"route": forced, "client": client, "source": "forced",
                "why": "forzado por --route"}
    verdict = decide_by_rules(prompt)
    if verdict is not None:
        verdict["source"] = "rules"
        return verdict
    return decide_by_model(prompt)


# ----------------------------------------------------------------------------
# EJECUTORES  (las tres bocas)
# ----------------------------------------------------------------------------

def run_subscription(prompt: str, client: str, cwd: str | None = None) -> int:
    """Lanza el CLI oficial como subproceso. Respeta el OAuth de la suscripción.

    Facturación (verificado con la doc oficial / guías 2026):
      - Si ANTHROPIC_API_KEY existe en el entorno, el CLI la PREFIERE y factura
        API en silencio. La borramos para forzar la suscripción (OAuth).
      - Para headless puro (sin sesión interactiva previa) conviene exportar
        CLAUDE_CODE_OAUTH_TOKEN (`claude setup-token`): lo PRESERVAMOS aquí.
      - 'cwd' deja que Claude Code lea el repo del proyecto (CLAUDE.md, tools).
    """
    template = CONFIG["subscription"].get(client)
    if not template:
        print(f"[error] cliente desconocido: {client}", file=sys.stderr)
        return 2
    if shutil.which(template[0]) is None:
        print(f"[error] '{template[0]}' no está instalado o no está en PATH.",
              file=sys.stderr)
        return 127

    cmd = [arg.replace("{prompt}", prompt) for arg in template]

    # Clave: quitar las credenciales de API para NO caer en facturación por API.
    # NO tocamos CLAUDE_CODE_OAUTH_TOKEN: ese ES el de la suscripción.
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)

    where = f" (cwd={cwd})" if cwd else ""
    print(f"[dispatcher] -> SUSCRIPCIÓN vía '{client}'{where}\n", file=sys.stderr)
    return subprocess.run(cmd, env=env, cwd=cwd).returncode


def run_api(prompt: str, stream: bool = True) -> int:
    """Habla con LiteLLM (formato OpenAI chat/completions)."""
    cfg = CONFIG["api"]
    headers = {"Authorization": f"Bearer {cfg['api_key']}"}
    payload = {
        "model": cfg["model"],
        "messages": [{"role": "user", "content": prompt}],
        "stream": stream,
    }
    print(f"[dispatcher] -> API vía LiteLLM ({cfg['model']})\n", file=sys.stderr)
    if stream:
        return _emit(_sse_text_chunks(cfg["base_url"], payload, headers), "API")
    # No-stream: una sola respuesta completa (útil para pipes/captura).
    try:
        data = _http_post_json(cfg["base_url"], payload, headers)
        print(data["choices"][0]["message"]["content"])
        return 0
    except Exception as e:
        print(f"[error] API falló: {e}", file=sys.stderr)
        return 1


def run_local(prompt: str, stream: bool = True) -> int:
    """Ejecuta en Ollama local."""
    cfg = CONFIG["local"]
    payload = {"model": cfg["model"], "prompt": prompt, "stream": stream}
    print(f"[dispatcher] -> LOCAL vía Ollama ({cfg['model']})\n", file=sys.stderr)
    if stream:
        return _emit(_ollama_text_chunks(cfg["base_url"], payload), "local")
    try:
        data = _http_post_json(cfg["base_url"], payload)
        print(data.get("response", ""))
        return 0
    except Exception as e:
        print(f"[error] local falló: {e}", file=sys.stderr)
        return 1


# ----------------------------------------------------------------------------
# UTILIDADES
# ----------------------------------------------------------------------------

def log_decision(prompt: str, verdict: dict) -> None:
    """Append-only JSONL con la decisión de routing. Nunca rompe el flujo:
    cualquier error al escribir se ignora (es telemetría, no crítico)."""
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        entry = {
            "ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "len": len(prompt),
            "prompt": prompt[:LOG_PROMPT_MAX],
            "route": verdict.get("route"),
            "client": verdict.get("client"),
            "source": verdict.get("source"),
            "why": verdict.get("why"),
        }
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass  # telemetría best-effort


def _http_post_json(url: str, payload: dict, headers: dict | None = None) -> dict:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())


def _http_post_stream(url: str, payload: dict, headers: dict | None = None):
    """Abre un POST y devuelve la respuesta para iterarla línea a línea."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    return urllib.request.urlopen(req, timeout=300)


def _sse_text_chunks(url: str, payload: dict, headers: dict | None = None,
                     usage: dict | None = None):
    """Trozos de texto de un stream SSE estilo OpenAI (LiteLLM).

    Cada línea es 'data: {json}' con choices[0].delta.content; 'data: [DONE]' cierra.
    Si se pasa 'usage' (dict mutable), se rellena con los tokens del chunk final.
    """
    resp = _http_post_stream(url, payload, headers)
    try:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line or not line.startswith("data:"):
                continue
            data = line[len("data:"):].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            if usage is not None and obj.get("usage"):
                u = obj["usage"]
                usage["prompt_tokens"] = u.get("prompt_tokens", 0)
                usage["completion_tokens"] = u.get("completion_tokens", 0)
            choices = obj.get("choices") or [{}]
            piece = (choices[0].get("delta") or {}).get("content")
            if piece:
                yield piece
    finally:
        resp.close()


def _ollama_text_chunks(url: str, payload: dict, usage: dict | None = None):
    """Trozos de texto de un stream NDJSON de Ollama (campo 'response').

    Si se pasa 'usage', se rellena con prompt_eval_count/eval_count del chunk final.
    """
    resp = _http_post_stream(url, payload)
    try:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            piece = obj.get("response", "")
            if piece:
                yield piece
            if obj.get("done"):
                if usage is not None:
                    usage["prompt_tokens"] = obj.get("prompt_eval_count", 0)
                    usage["completion_tokens"] = obj.get("eval_count", 0)
                break
    finally:
        resp.close()


def _emit(chunks, label: str) -> int:
    """Contrato unificado de salida: consume un iterador de trozos de texto y los
    imprime incrementalmente (streaming). Devuelve 0 si OK, 1 si hubo error.

    Centraliza el manejo de errores para que las tres bocas se comporten igual.
    """
    wrote_any = False
    try:
        for chunk in chunks:
            sys.stdout.write(chunk)
            sys.stdout.flush()
            wrote_any = True
        if wrote_any:
            sys.stdout.write("\n")
            sys.stdout.flush()
        return 0
    except Exception as e:
        prefix = "\n" if wrote_any else ""
        print(f"{prefix}[error] {label} falló: {e}", file=sys.stderr)
        return 1


# ----------------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Dispatcher multi-modelo en terminal.")
    ap.add_argument("prompt", nargs="+", help="Tu petición.")
    ap.add_argument("--route", choices=["subscription", "api", "local"],
                    help="Forzar una ruta (salta el clasificador).")
    ap.add_argument("--client", choices=["claude", "codex"],
                    help="Forzar cliente de suscripción.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Solo muestra la decisión, no ejecuta.")
    ap.add_argument("--cwd", default=os.getcwd(),
                    help="Directorio de trabajo para la ruta de suscripción "
                         "(para que Claude Code lea el repo). Default: actual.")
    ap.add_argument("--no-stream", action="store_true",
                    help="Desactiva el streaming token-a-token en API/local "
                         "(respuesta completa de una vez).")
    ap.add_argument("--no-log", action="store_true",
                    help=f"No registrar la decisión en {LOG_PATH}.")
    args = ap.parse_args()
    stream = not args.no_stream

    prompt = " ".join(args.prompt)
    verdict = route(prompt, args.route)
    if args.client:
        verdict["client"] = args.client

    print(f"[dispatcher] decisión: {verdict['route']} "
          f"({verdict.get('client') or '-'}) — {verdict['why']}",
          file=sys.stderr)

    if not args.no_log and not os.environ.get("DISPATCH_NO_LOG"):
        log_decision(prompt, verdict)

    if args.dry_run:
        print(json.dumps(verdict, ensure_ascii=False))
        return 0

    r = verdict["route"]
    if r == "subscription":
        return run_subscription(prompt, verdict.get("client") or "claude", args.cwd)
    if r == "api":
        return run_api(prompt, stream)
    if r == "local":
        return run_local(prompt, stream)
    print("[error] ruta desconocida", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
