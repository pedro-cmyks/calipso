#!/usr/bin/env python3
"""
dispatch.py — CLI de terminal, standalone. El chat vivo NO pasa por aca: su
ruteo real vive en `capabilities.choose` (ver calipso/server.py). Este archivo
solo lo usan invocaciones manuales por terminal y algunos tests/experimentos
que reusan sus utilidades (CONFIG, extract_features, los helpers HTTP/SSE).

Dos bocas reales:
  1. SUSCRIPCIÓN  -> lanza el CLI oficial (claude / codex) como subproceso.
                     Usa tu cuota Pro/Max o ChatGPT. NO gasta API.
  2. API          -> habla con un proxy LiteLLM local que unifica
                     Anthropic + OpenAI + DeepSeek bajo un endpoint OpenAI.

No hay boca LOCAL viva en este CLI: `run_local` no habla con Ollama, solo
redirige a SUSCRIPCIÓN (ver su docstring). Y `decide_by_model` no es un
clasificador: es un stub que siempre devuelve suscripcion, sin llamar a
ningun modelo.

Routing:
  - Primero intenta decidir por REGLAS (flags + palabras clave).
  - Si las reglas no dan veredicto claro, cae al stub `decide_by_model`
    (suscripcion por defecto; no hay clasificador real).

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

try:
    from calipso.economia.pagador import (Pagador as _Pagador,
                                          suscripcion_de_cliente as
                                          _suscripcion_de_cliente)
    from calipso.economia.operacion import semana_iso as _semana_iso
except Exception:
    _Pagador = None
    _suscripcion_de_cliente = None
    _semana_iso = None

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

}

if dispatch_config:
    CONFIG = dispatch_config()

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
    r"arregla|build|compila|migra|repositorio|repo|pull request|stack trace|"
    r"bot[oó]n(es)?|ui\b|interfaz|dise[ñn]o|responsiv|sidebar|drawer|layout|"
    r"componente|modal|css|html|estilo|estiliz|frontend|front.end|micr[oó]fon)\b",
    re.IGNORECASE,
)

# Palabras que sugieren tarea TRIVIAL / privada -> local.
TRIVIAL = re.compile(
    r"\b(resumen|traduce|traducir|reformula|clasifica|"
    r"corrige ortograf|formatea|lista|extrae)\b",
    re.IGNORECASE,
)

# Palabras que sugieren razonamiento amplio barato -> API (DeepSeek).
CHEAP_REASONING = re.compile(
    r"\b(explica|compara|analiza|brainstorm|ideas|borrador|draft|"
    r"investiga|pros y contras)\b",
    re.IGNORECASE,
)

# Pistas extra para extraer FEATURES (no solo la ruta) que alimentan el router
# por puntaje de capacidades.
PRIVATE = re.compile(
    r"\b(privado|confidencial|secreto|contraseñas?|password|personales?|sensible|"
    r"no comparta|no compartas)\b", re.IGNORECASE)
REPO = re.compile(
    r"\b(repo|repositorio|pull request|build|compila|migra|despliega|deploy|"
    r"stack trace)\b", re.IGNORECASE)
WRITING = re.compile(
    r"\b(escribe|redacta|redactar|borrador|draft|correo|email|carta|post|"
    r"art[ií]culo)\b", re.IGNORECASE)
TRANSLATE = re.compile(r"\b(traduce|traducir|traducci)\b", re.IGNORECASE)
SUMMARIZE = re.compile(r"\b(resumen|resumir|sintetiza)\b", re.IGNORECASE)
AGENTIC = re.compile(
    r"\b(ejecuta|corre los tests|automatiza|agente|herramienta|run)\b",
    re.IGNORECASE)
# `hoy` solo no busca (probe 2026-09-15: "que sabes hacer hoy?" fue a
# DuckDuckGo): cuenta junto a lo que cambia con el dia
WEB = re.compile(
    r"\b(busca|b[uú]scame|googlea|noticias?|actualidad|[uú]ltim[ao]s?|"
    r"reciente|precio de|cotizaci[oó]n|clima|qui[eé]n gan|qu[eé] pas[oó]|"
    r"en internet|en la web|search)\b", re.IGNORECASE)
# Lo que pide MANOS sobre la maquina o un archivo nuevo (instalar, descargar,
# guardar, generar un pdf/imagen, abrir, borrar): el modelo chico no puede
# hacerlo y ademas inventa que lo hizo (probe 2026-09-15, el PDF); sube la
# complejidad a 3 (max_complexity del 7b es 2) para que conteste alguien
# capaz de decir la verdad o de proponer un /goal.
MANOS = re.compile(
    r"\b(instal[aá]|desinstal[aá]|descarg[aá]|guard[aá]|d[eé]jalo|dejalo|d[eé]jame el|"
    r"gener[aá] (un[a]? )?(pdf|imagen|archivo|foto|documento)|hazme (un[a]? )?(pdf|imagen|archivo|documento)|"
    r"cre[aá] (un[a]? )?(archivo|pdf|carpeta|documento)|abr[eií]|ejecut[aá]|borr[aá]|elimin[aá]|"
    r"mueve|mov[eé]|copi[aá]|export[aá]|en mi (computador|m[aá]quina|pc|carpeta|disco|escritorio|descargas))\b",
    re.IGNORECASE)

VALID_TYPES = {"trivial", "translate", "summarize", "writing", "reasoning",
               "analysis", "code", "repo", "agentic"}

FEATURES_SYSTEM = (
    "Extrae las features de la PETICIÓN del usuario. Responde SOLO JSON, sin "
    "texto extra. Formato exacto:\n"
    '{"type":"trivial|translate|summarize|writing|reasoning|analysis|code|repo|agentic",'
    '"complexity":1,"private":false,"needs_repo":false}\n'
    "complexity 1 = trivial, 5 = muy complejo. private=true si toca datos "
    "personales/sensibles. needs_repo=true si requiere leer el repositorio."
)


def _estimate_complexity(prompt: str, task_type: str | None) -> int:
    base = 1 if task_type in ("trivial", "translate", "summarize") else 2
    if len(prompt) > 400:
        base += 1
    if len(prompt) > 1200:
        base += 1
    if CODE_HEAVY.search(prompt):
        base += 1
    return max(1, min(5, base))




def extract_features(prompt: str) -> dict:
    """Features para el router por capacidades: {type, complexity, private,
    needs_repo}. Reglas (rápido/gratis) primero; clasificador solo si hace falta."""
    p = prompt.strip()
    feat = {"type": None, "complexity": 2,
            "private": bool(PRIVATE.search(p)), "needs_repo": False,
            "needs_web": bool(WEB.search(p)) or bool(re.search(r"https?://", p)),
            "needs_hands": bool(MANOS.search(p))}
    if CODE_HEAVY.search(p):
        if REPO.search(p):
            feat["type"], feat["needs_repo"] = "repo", True
        elif AGENTIC.search(p):
            feat["type"] = "agentic"
        else:
            feat["type"] = "code"
    elif TRANSLATE.search(p):
        feat["type"] = "translate"
    elif SUMMARIZE.search(p):
        feat["type"] = "summarize"
    elif TRIVIAL.search(p):
        feat["type"] = "trivial"
    elif WRITING.search(p):
        feat["type"] = "writing"
    elif CHEAP_REASONING.search(p):
        feat["type"] = "analysis" if re.search(r"\banaliza", p, re.IGNORECASE) else "reasoning"

    if feat["type"] is None:
        feat["type"] = "reasoning"
    feat["complexity"] = _estimate_complexity(p, feat["type"])
    if feat["needs_hands"]:
        feat["complexity"] = max(feat["complexity"], 3)
    return feat


def decide_by_rules(prompt: str) -> dict | None:
    """Devuelve un veredicto {ruta, cliente} o None si no está claro.

    PRECEDENCIA REAL (el orden de los `if`; no hay boca local en este CLI,
    todo lo que "gana" aca termina en suscripcion o api):
      1. Privado/sensible   -> suscripción (no hay local; ver el `why`).
      2. Código pesado      -> suscripción (tarea de código pesada).
      3. Trivial            -> suscripción (no hay Ollama local que la tome).
      4. Razonamiento barato-> API, salvo que la politica fuerce suscripcion
                               primero (subscription_first).
      5. Solo-tamaño        -> suscripción (prompt muy largo sin otra señal:
                               necesita contexto grande).
      6. Nada claro         -> None (pasa a `decide_by_model`, que es un stub
                               y tambien devuelve suscripcion).
    """
    p = prompt.strip()
    long_prompt = len(p) > 800
    routing = (load_config() if load_config else {}).get("routing", {})
    sub_client = routing.get("subscription_client", "claude")
    subscription_first = routing.get("policy", "subscription_first") == "subscription_first"

    if PRIVATE.search(p):
        return {"route": "subscription", "client": sub_client,
                "why": "datos privados/sensibles; no hay boca local en este "
                       "CLI, va a suscripcion (no a la API paga)"}

    if CODE_HEAVY.search(p):
        return {"route": "subscription", "client": sub_client,
                "why": "tarea de código pesada"}

    if TRIVIAL.search(p):
        return {"route": "subscription", "client": sub_client,
                "why": "tarea trivial; suscripcion (sin Ollama local)"}

    if CHEAP_REASONING.search(p):
        if subscription_first:
            return {"route": "subscription", "client": sub_client,
                    "why": "razonamiento amplio; politica suscripcion primero"}
        return {"route": "api", "client": None,
                "why": "razonamiento barato"}

    if long_prompt:
        return {"route": "subscription", "client": sub_client,
                "why": "prompt largo sin señal clara; necesita contexto grande"}

    return None  # -> pasa a decide_by_model (stub, no hay clasificador real)


# ----------------------------------------------------------------------------
# CAPA 2: STUB  (solo si las reglas no decidieron; no llama a ningun modelo)
# ----------------------------------------------------------------------------

# Prompt de sistema para un clasificador que nunca se cablea: CLASSIFIER_SYSTEM
# no lo lee nadie hoy (decide_by_model no lo usa, es un stub). Queda como
# especificacion para cuando/si se implemente un clasificador de verdad.
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
    """Stub: no llama a ningun modelo, siempre devuelve suscripcion.

    'prompt' no se usa; queda en la firma para cuando (si) se cablee un
    clasificador real.
    """
    routing = (load_config() if load_config else {}).get("routing", {})
    sub_client = routing.get("subscription_client", "claude")
    return {"route": "subscription", "client": sub_client, "source": "rules",
            "why": "reglas no decidieron; suscripcion por defecto"}


def route(prompt: str, forced: str | None) -> dict:
    if forced:
        client = "claude" if forced == "subscription" else None
        return {"route": forced, "client": client, "source": "forced",
                "why": "forzado por --route"}
    verdict = decide_by_rules(prompt)
    if verdict is not None:
        verdict["source"] = "rules"
        return verdict
    verdict = decide_by_model(prompt)
    routing = (load_config() if load_config else {}).get("routing", {})
    if verdict.get("route") == "api" and routing.get("api_only_when_forced", True):
        verdict["route"] = "subscription"
        verdict["client"] = routing.get("subscription_client", "claude")
        verdict["why"] = verdict.get("why", "clasificador eligio api") + "; politica evita API no forzada"
    return verdict


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


def run_api(prompt: str, stream: bool = True, usage: dict | None = None) -> int:
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
        payload["stream_options"] = {"include_usage": True}
        return _emit(_sse_text_chunks(cfg["base_url"], payload, headers, usage), "API")
    # No-stream: una sola respuesta completa (útil para pipes/captura).
    try:
        data = _http_post_json(cfg["base_url"], payload, headers)
        if usage is not None:
            usage.update(data.get("usage") or {})
        print(data["choices"][0]["message"]["content"])
        return 0
    except Exception as e:
        print(f"[error] API falló: {e}", file=sys.stderr)
        return 1


def run_local(prompt: str, stream: bool = True) -> int:
    """Local no disponible (sin Ollama); redirige a suscripción."""
    print("[dispatcher] ruta local no disponible → suscripción", file=sys.stderr)
    routing = (load_config() if load_config else {}).get("routing", {})
    client = routing.get("subscription_client", "claude")
    return run_subscription(prompt, client)


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
    """Trozos de texto de un stream NDJSON de Ollama (campo 'response')."""
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
                    # "length" cuando Ollama corto por num_predict/contexto:
                    # el canario `cortada` lo lee (spec canarios 2.2)
                    usage["done_reason"] = obj.get("done_reason")
                break
    finally:
        resp.close()


def _ollama_chat_chunks(url: str, payload: dict, usage: dict | None = None):
    """Trozos de texto de un stream NDJSON de Ollama /api/chat (campo message.content).

    Usa el endpoint de chat que acepta messages[] con historial estructurado.
    """
    chat_url = url.replace("/api/generate", "/api/chat")
    resp = _http_post_stream(chat_url, payload)
    try:
        for raw in resp:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            piece = (obj.get("message") or {}).get("content", "")
            if piece:
                yield piece
            if obj.get("done"):
                if usage is not None:
                    usage["prompt_tokens"] = obj.get("prompt_eval_count", 0)
                    usage["completion_tokens"] = obj.get("eval_count", 0)
                    usage["done_reason"] = obj.get("done_reason")
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
    ap.add_argument("--cuenta", default="personal",
                    help="cuenta pagadora de la economia (dep:<x>, "
                         "trabajo:<id>, personal)")
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
    usage: dict = {}
    if r == "subscription":
        rc = run_subscription(prompt, verdict.get("client") or "claude", args.cwd)
    elif r == "api":
        rc = run_api(prompt, stream, usage=usage)
    elif r == "local":
        rc = run_local(prompt, stream)
    else:
        print("[error] ruta desconocida", file=sys.stderr)
        return 2

    # Cargo economico best-effort (nunca rompe el flujo, patron log_decision)
    try:
        if _Pagador and _semana_iso:
            pagador = _Pagador.desde_entorno()
            if pagador:
                ahora = datetime.datetime.now()
                ts_eco = ahora.isoformat(timespec="seconds")
                sem = _semana_iso(ahora.date().isoformat())
                if r == "api":
                    pagador.cargar_api(ts_eco, sem, args.cuenta,
                                       CONFIG["api"]["model"],
                                       usage.get("prompt_tokens", 0),
                                       usage.get("completion_tokens", 0))
                else:
                    # subscription Y local: run_local redirige a la
                    # suscripcion, asi que tambien consume una unidad
                    if r == "subscription":
                        cliente = verdict.get("client") or "claude"
                    else:  # local
                        routing = (load_config() if load_config else {}).get(
                            "routing", {})
                        cliente = routing.get("subscription_client", "claude")
                    sus = _suscripcion_de_cliente(cliente)
                    pagador.cargar_suscripcion(ts_eco, sem, args.cuenta, sus)
    except Exception:
        pass  # telemetria economica best-effort

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
