# Calipso — guía para agentes (handoff)

> **Qué es Calipso:** el asistente personal multi-modelo de Pedro (tipo "Jarvis"),
> con interfaz web (editor de código + chat), memoria que evoluciona, y un
> orquestador que enruta cada petición a la boca más adecuada. Es **para Pedro**,
> corre **local** y se accede desde su red (y, a futuro, desde el iPhone).
>
> **Idioma:** Pedro escribe en español. Responde en español.
> **Estado:** funcional de punta a punta. Esta guía es la fuente de verdad.

## Estado del cerebro (lo construido, resumen)

- **Ruteo a nivel de MODELO** (`calipso/capabilities.py`): registro donde cada modelo
  (Haiku/Sonnet/Opus, Codex gpt-5-codex/-mini/gpt-5.5, DeepSeek, Fable 5, local qwen)
  declara tier (small/mid/frontier/apex), persona (filósofo), costo y afinidad por
  tarea. `choose(features, effort)` puntúa afinidad×costo×tier×intensidad → elige el
  modelo por tarea; suscripción > API paga. NO es un gate que prueba en orden.
- **Intensidad ("ultrathink")**: fast/balanced/think/ultra, derivada de la complejidad;
  más intensidad exige tier más alto. Slash: `/fast /think /ultrathink /model /local
  /claude /codex /help`. A la API se le pasa `output_config.effort`.
- **Features** (`dispatch.extract_features`): {type, complexity, private, needs_repo}.
- **Memoria** (`calipso/memory.py`): híbrida (markdown core + Chroma episódica),
  jerárquica global/proyecto, embeddings multilingües `bge-m3`, `reflect()` promueve.
- **Contexto presupuestado** (cache-friendly, just-in-time; ~5KB/turno).
- **Aprendizaje** (`calipso/learning.py`): telemetría → ajusta pesos por modelo,
  global y por repo. POST /api/learn.
- **Sesiones** (`calipso/sessions.py`): cada sesión tiene su elenco (roster temático
  distinto → nombres cambian por sesión); por agente: nombre, intensidad, enabled.
  Panel en la UI. Endpoints /api/session*.
- **Descubrimiento + updates** (`calipso/discovery.py`): registra modelos vivos
  (Ollama/LiteLLM), avisa de updates (CLIs vs npm, modelos nuevos). /api/discover,
  /api/updates.
- **Steering**: el WS lee mensajes en paralelo; escribir mientras responde interrumpe
  (barge-in); `/stop` detiene. UI: botón Detener + frases de "pensando".
- **Navegación web** (`calipso/web.py`): search (DuckDuckGo HTML, POST, sin llave) +
  fetch (texto legible). El chat detecta `needs_web` (o `/web`), busca+lee, inyecta el
  material como contexto (grounding) y manda eventos "web" al panel de preview.

## DIRECCIÓN MAYOR pendiente — agentes DINÁMICOS (multi-agente)
Pedro NO quiere un roster fijo precargado; quiere que Calipso **descomponga** la
petición y **cree agentes a medida por subtarea**, con rol/traits/quirks y su
(modelo + intensidad): ej. "esta parte fácil → agente con Haiku; esta necesita razonar
→ agente que planee a máximo esfuerzo; otro que edite código" y los coordine. Es
orquestación multi-agente (planner → equipo → merge). El panel/roster actual pasa a ser
plantillas/defaults. Es el próximo salto grande tras lo conversacional. Además: VOZ
multilingüe para narrar prompts (Web Speech API en navegador / Whisper local), estilo
ChatGPT (entiende en cualquier idioma en una sola frase).
- **Costos** (`calipso/costs.py`), **telemetría** (`calipso/telemetry.py`),
  **seguridad** (TOTP + token en `server.py`), **config** (`calipso/config.py`).

Pendientes (en la memoria de Claude): #5 quota_low real (budget-aware), /api/learn
periódico, loguear aceptar/descartar propuestas, effort real a sub-claude/local,
preview de navegación web (si Calipso navega), descubrimiento de modelos de suscripción.

---

## 1. Arranque rápido

```bash
# Requisitos ya instalados en la máquina de Pedro (ver §5).
python calipso/server.py
# -> imprime el token y la URL. Abrir:
#    http://localhost:8000/?token=<TOKEN>      (local)
#    http://192.168.1.10:8000/?token=<TOKEN>   (desde otro dispositivo en el WiFi)
```

El token vive en `~/.calipso/token` (se autogenera). NO lo escribas en el repo.
Sin token válido, todo da 401 / redirige a `/login`.

Pruebas:
```bash
python test_streaming.py   # parsers de streaming (mock, sin modelos)
python test_memory.py      # memoria jerárquica + reflect (usa Ollama)
```

---

## 2. Arquitectura

```
Navegador (PC / iPhone)
   │  http + WebSocket (con token)
   ▼
calipso/server.py  (FastAPI)  ── el "cuerpo"
   ├─ UI web: calipso/web/index.html  (explorador + editor Monaco + chat)
   ├─ API archivos: /api/tree, /api/file (GET/PUT)  [anti path-traversal]
   ├─ chat: /ws/chat  (router → memoria → streaming → registra costo → recuerda)
   ├─ memoria: /api/memory, /api/reflect
   ├─ costos: /api/costs
   └─ seguridad: token (cookie httponly) + /login
   │
   ├── dispatch.py        ── el "cerebro" (router multi-modelo)
   ├── calipso/memory.py  ── memoria híbrida y jerárquica
   └── calipso/costs.py   ── tracker de gastos
```

### El cerebro — `dispatch.py`
Router híbrido: **reglas** (regex + tamaño) y si no deciden, un **clasificador
local** (qwen2.5:3b vía Ollama, devuelve JSON). Tres "bocas":
- **subscription**: lanza `claude`/`codex` como subproceso. **CRÍTICO:** borra
  `ANTHROPIC_API_KEY` (y `ANTHROPIC_AUTH_TOKEN`) del entorno para usar la
  suscripción y NO facturar API. Preserva `CLAUDE_CODE_OAUTH_TOKEN`.
- **api**: proxy LiteLLM local (`http://localhost:4000`, formato OpenAI).
- **local**: Ollama (`http://localhost:11434`).
Streaming: `_sse_text_chunks` (SSE de LiteLLM) y `_ollama_text_chunks` (NDJSON
de Ollama); ambos aceptan un dict `usage` que rellenan con tokens.
Log de decisiones en `~/.dispatch/decisions.jsonl`. Fallback seguro = `local`
(no escalar a API de pago en silencio si el clasificador cae).

### La memoria — `calipso/memory.py`
Híbrida y por **ámbitos** (como Claude Code: usuario vs proyecto):
- **CORE** (markdown, estilo Obsidian): curado, editable a mano, git-eable.
- **EPISÓDICA** (ChromaDB): volumen, recuperación por significado.
- **GLOBAL** (`~/.calipso/global/{core,chroma}`): quién es Pedro, cómo trabaja.
- **PROYECTO** (`<proyecto>/.calipso/core` + `~/.calipso/projects/<slug>/chroma`):
  qué es el proyecto, qué se está haciendo.
`Memory(project_root=...)`; `load_core()` combina ámbitos; `recall()` mergea por
score; `remember()`; `reflect()` = consolidación (lee episódico reciente, qwen2.5:7b
extrae hechos duraderos, los clasifica global/project y los promueve al core).
**Embeddings: `bge-m3` vía Ollama (MULTILINGÜE).** El modelo por defecto de Chroma
(all-MiniLM, inglés) rankeaba MAL el español — no lo uses. Requiere `pip install ollama`.

### Los costos — `calipso/costs.py`
`log_usage()` → `~/.calipso/costs.jsonl`. `monthly_report()` → total + desglose
por modelo/ruta/día. **api** = por token (variable), **subscription** = fijo
mensual, **local** = gratis. Precios/suscripciones en `PRICING`/`SUBSCRIPTIONS`
(o override en `~/.calipso/pricing.json`). ⚠️ Los montos de suscripción son
PLACEHOLDERS ($100/$20) — Pedro debe poner los reales.

### Seguridad — token (en `server.py`)
Middleware HTTP + chequeo en el WebSocket. Cookie `calipso_token` httponly.
Entra con `/?token=...` (guarda cookie 1 año) o por `/login`. **Próximo paso: TOTP** (§7).
Servidor atado a `0.0.0.0` (toda la red local). Para acceso remoto seguro:
**Tailscale** (red privada cifrada, gratis) — NUNCA abrir el puerto a internet.

---

## 3. Qué está HECHO y VERIFICADO

- [x] Router con reglas + clasificador, 3 bocas, streaming, log, safety de billing
      — `test_streaming.py` + dry-runs + local real contra Ollama.
- [x] Editor de código (Monaco) + API de archivos con anti path-traversal — en navegador.
- [x] Chat (WebSocket): router → memoria → streaming → costo → recuerda — en navegador.
- [x] Memoria jerárquica (global + proyecto) + `reflect()` — `test_memory.py` + live
      (un dato dicho por chat se promovió al core global).
- [x] Tracker de costos + línea "💰 ruta · tokens · costo" en el chat + `/api/costs`.
- [x] Red local (`0.0.0.0`) — IP del PC de Pedro: **192.168.1.10** (WiFi).
- [x] Token de acceso (cookie httponly, middleware + WS, /login) — verificado 401/200.

---

## 4. Mapa del repo

```
dispatch.py            cerebro: router multi-modelo (CLI + librería)
SETUP.md               setup histórico del dispatcher CLI (pre-Calipso)
test_streaming.py      tests de los parsers de streaming
test_memory.py         tests de memoria jerárquica + reflect
calipso/
  server.py            servidor FastAPI (el cuerpo) — punto de entrada
  memory.py            memoria híbrida y jerárquica
  costs.py             tracker de gastos
  __init__.py
  web/index.html       UI: explorador + Monaco + chat (una sola página)
.claude/launch.json    config de preview (uvicorn en 0.0.0.0:8000)
```
Datos de runtime (fuera del repo): `~/.calipso/` (global core, chroma, token,
costs.jsonl, projects/<slug>) y `~/.dispatch/decisions.jsonl`.

---

## 5. Entorno y dependencias

- **OS:** Windows 11, PowerShell. **Python 3.12.**
- **pip:** `litellm[proxy]` (trae fastapi/uvicorn/websockets), `chromadb`, `ollama`.
- **Ollama** (winget `Ollama.Ollama`), modelos: `qwen2.5:3b` (clasificador),
  `qwen2.5:7b` (chat/reflect), `bge-m3` (embeddings multilingües).
- **No instalado aún:** los CLIs `claude`/`codex` (boca suscripción) y LiteLLM
  arrancado (boca api). El chat hoy usa `local`; api/subscription degradan a local.

⚠️ **GOTCHA — sin GPU:** la máquina corre Ollama 100% en CPU (`size_vram=0`).
qwen2.5:7b genera lento (~20-30s con contexto). Para responsividad considerar:
clasificador/embeddings más livianos, cache de ruteo, o modelo de chat más chico.

---

## 6. Decisiones clave (no re-litigar)

- **Memoria:** híbrida markdown + ChromaDB, jerárquica global/proyecto. Markdown-first
  para lo curado (transparente, Obsidian-abrible, sync-friendly); vector solo para volumen.
- **Cuerpo:** código propio robando ideas de **Odysseus** (PewDiePie, open source:
  github.com/pewdiepie-archdaemon/odysseus) — su capa de memoria, PWA, agent loop.
  NO forkear.
- **Multi-PC:** peers que se conocen, **SIN duplicar archivos** (Pedro no quiere gasto
  de datos). Modelo FEDERADO: cada PC dueño de sus archivos, Calipso consciente de la
  UBICACIÓN y los usa bajo demanda vía el API del PC dueño. Trade-off aceptado: si el
  dueño está apagado, su archivo no está disponible. Descartado Syncthing.
- **Remoto seguro:** Tailscale + token de app. NUNCA port-forwarding.
- **Embeddings multilingües** obligatorios (bge-m3). **Billing:** nunca pasar
  `ANTHROPIC_API_KEY` al subproceso de la boca suscripción.

---

## 7. PRÓXIMA TAREA (lo que pidió Pedro): autenticación TOTP + QR

Reemplazar el token-string por **TOTP** (código rotativo de 6 dígitos, compatible
con Microsoft/Google Authenticator). Flujo:

1. **Setup (una vez):** generar un secreto base32 y guardarlo en `~/.calipso/totp_secret`.
   Mostrar un **QR** del `otpauth://` URI para enrolar en el autenticador del teléfono.
2. **Login:** la página `/login` pide el código de 6 dígitos; se valida; si es correcto
   se setea la cookie de sesión (el mismo mecanismo de cookie que ya existe).
3. Mantener el token-string actual como **recuperación** (fallback).

Sketch (recomendado `pip install pyotp qrcode[pil]`; TOTP también es implementable
en stdlib con hmac/hashlib/struct/time si se quiere cero-deps):
```python
import pyotp, qrcode, io, base64, pathlib
SECRET_FILE = pathlib.Path.home()/".calipso"/"totp_secret"
def get_secret():
    if SECRET_FILE.exists(): return SECRET_FILE.read_text().strip()
    s = pyotp.random_base32(); SECRET_FILE.write_text(s); return s
def provisioning_uri():
    return pyotp.totp.TOTP(get_secret()).provisioning_uri(name="Pedro", issuer_name="Calipso")
def verify(code: str) -> bool:
    return pyotp.TOTP(get_secret()).verify(code, valid_window=1)
def qr_png_data_uri():
    img = qrcode.make(provisioning_uri()); buf = io.BytesIO(); img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
```
- Nuevo endpoint `GET /setup` (protegido por el token actual la primera vez) que muestra
  el QR (`qr_png_data_uri()`).
- `/login` (GET): input numérico de 6 dígitos → POST → `verify()` → set cookie → redirect.
- Reusar `auth_guard` y el chequeo del WebSocket tal cual (la cookie de sesión no cambia).

---

## 8. Backlog (después de TOTP)

1. **Multi-PC federado:** "índice de ubicación" de archivos + selector de máquina en la
   UI; Calipso-A lee archivos de Calipso-B vía su `/api/file` (sin copiar). Ver §6.
2. **Tailscale:** Pedro instala el cliente en iPhone + sus 2 PCs (mismo login). Guiarlo.
3. **PWA:** `manifest.json` + service worker para instalar la web como app en el iPhone
   (apunta a `192.168.1.10:8000` o al nombre Tailscale).
4. **Fase C — proveedores + presupuesto:** hacer fácil añadir APIs/suscripciones, y que
   el ruteo sea consciente del saldo/cuota ANTES de pedir (no rutear a API sin saldo ni a
   suscripción con cuota agotada). `costs.py` es la semilla. Cuando LiteLLM esté encendido,
   su `/spend/logs` da el gasto API exacto.
5. **Perf en CPU:** cache de veredictos de ruteo; clasificador por embeddings (más rápido
   que el LLM); modelo de chat más liviano.
6. **Bocas vivas:** instalar `claude`/`codex` (login con la suscripción) y arrancar LiteLLM
   con `litellm.config.yaml` (ver SETUP.md) para activar api/subscription.

---

## 9. Contexto extra

Memoria persistente de sesiones Claude (si el agente es Claude Code) en
`~/.claude/projects/C--Users-Pedro-Desktop-proycto/memory/` (MEMORY.md + decisiones).
Codex no la lee — por eso este AGENTS.md es autocontenido.

**Nota meta:** esta sesión se cerró porque Pedro se quedó sin usage de Claude y se pasó
a Codex. Ese problema —repartir trabajo entre proveedores según cuota disponible— es
literalmente lo que Calipso (§8.4) está diseñado para resolver.
