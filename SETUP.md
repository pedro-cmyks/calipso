# Dispatcher multi-modelo — Setup

Un solo comando en terminal que enruta entre tres "bocas":

| Boca | Cómo conecta | Qué cobra |
|------|-------------|-----------|
| **Suscripción** | subproceso a `claude` / `codex` (CLI oficial) | tu cuota Pro/Max y ChatGPT — **no** API |
| **API** | proxy LiteLLM local (Anthropic + OpenAI + DeepSeek) | por token |
| **Local** | Ollama | gratis |

Decisión **híbrida**: reglas primero; si hay duda, un modelo clasificador local (Ollama) devuelve JSON.

---

## 1. Requisitos

```bash
# CLIs de suscripción (ya los usas)
#   claude  -> Claude Code   (login con tu plan Max/Pro: `claude` y autenticas)
#   codex   -> Codex         (login con tu ChatGPT)

# Ollama (motor local + clasificador)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:3b      # clasificador (pequeño, rápido)
ollama pull qwen2.5:7b      # ejecución local

# LiteLLM (proxy de APIs)
pip install 'litellm[proxy]'
```

---

## 2. LiteLLM: unificar tus 3 APIs

Crea `litellm.config.yaml`:

```yaml
model_list:
  - model_name: deepseek-chat
    litellm_params:
      model: deepseek/deepseek-chat
      api_key: os.environ/DEEPSEEK_API_KEY

  - model_name: gpt
    litellm_params:
      model: openai/gpt-4o
      api_key: os.environ/OPENAI_API_KEY

  - model_name: claude-api
    litellm_params:
      model: anthropic/claude-sonnet-4-6
      api_key: os.environ/ANTHROPIC_API_KEY

litellm_settings:
  drop_params: true

general_settings:
  master_key: sk-litellm-local   # debe coincidir con CONFIG["api"]["api_key"]
```

Exporta tus llaves y arranca el proxy:

```bash
export DEEPSEEK_API_KEY=...
export OPENAI_API_KEY=...
export ANTHROPIC_API_KEY=...     # OJO: ver nota de seguridad abajo

litellm --config litellm.config.yaml --port 4000
```

---

## 3. ⚠️ Nota crítica de seguridad (suscripción vs API)

`claude` decide entre suscripción y API según la variable `ANTHROPIC_API_KEY`:

- Si **existe** en el entorno → Claude Code cobra por **API**.
- Si **no existe** → usa tu **suscripción**.

LiteLLM necesita esa variable, pero el dispatcher la **borra** del entorno del
subproceso antes de lanzar `claude` (ver `run_subscription()`), así que la ruta
de suscripción nunca cae en facturación por error. También borra
`ANTHROPIC_AUTH_TOKEN` por si acaso, pero **preserva** `CLAUDE_CODE_OAUTH_TOKEN`
(ese es el de la suscripción).

Recomendado: corre LiteLLM en **otra terminal/proceso** con la variable
exportada solo ahí, y mantén tu shell interactiva **sin** `ANTHROPIC_API_KEY`.

**Headless puro** (cron, sin haber hecho `claude login` interactivo antes):
genera un token con `claude setup-token` y expórtalo como
`CLAUDE_CODE_OAUTH_TOKEN`. Para **verificar** que cobró suscripción y no API,
la respuesta de Claude Code trae `rateLimitType: "5h"` cuando usa el plan.

**Fallback seguro**: si el clasificador local (Ollama) está caído, el dispatcher
NO escala a la API de pago en silencio — cae a `local` (constante `SAFE_FALLBACK`
en `dispatch.py`). Si Ollama también está caído, falla de forma visible.

---

## 4. Alias para invocar desde cualquier lado

En tu `~/.zshrc` o `~/.bashrc`:

```bash
alias ai='python3 ~/dispatcher/dispatch.py'
```

Uso:

```bash
ai "refactoriza el módulo de auth y agrega tests"   # -> suscripción (claude)
ai "resume este texto"                              # -> local (Ollama)
ai "compara REST vs gRPC"                            # -> API (DeepSeek)
ai --route subscription --client codex "..."         # forzar Codex
ai --dry-run "..."                                   # ver decisión sin ejecutar
ai --cwd ~/mirepo "arregla el bug de login"          # suscripción lee ese repo
ai --no-stream "..."                                 # respuesta completa de una vez
ai --no-log "..."                                    # no registrar la decisión
```

---

## 5. Ajustes que querrás hacer

- **Reglas**: edita los regex `CODE_HEAVY`, `TRIVIAL`, `CHEAP_REASONING`.
- **Modelos**: cambia `CONFIG["api"]["model"]`, `["local"]["model"]`, etc.
- **Streaming**: API (SSE de LiteLLM) y local (NDJSON de Ollama) ya emiten
  token a token por defecto. Desactívalo con `--no-stream`. La ruta de
  suscripción ya streameaba (hereda stdout del CLI).
- **Log de decisiones**: cada ejecución registra la decisión en
  `~/.dispatch/decisions.jsonl` (configurable con `DISPATCH_LOG`, desactivable
  con `--no-log` o `DISPATCH_NO_LOG=1`). Úsalo para afinar los regex con datos
  reales: mira qué prompts cayeron en `source:"model"` o `"fallback"` (las
  reglas no los atraparon) y conviértelos en reglas.
- **Contexto de archivos**: para tareas de código real, conviene que la ruta
  de suscripción corra dentro del directorio del proyecto (Claude Code ya lee
  el repo). Puedes pasar `cwd=` a `subprocess.run`.
