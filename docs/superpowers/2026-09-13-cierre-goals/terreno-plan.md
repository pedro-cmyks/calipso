# Terreno para el plan del goal que corre (2026-09-13)

Lectura sobre el worktree `/var/home/pedro/calipso/.claude/worktrees/goals` (rama `feat/goals`, HEAD
`0cfc8bb` = main `4c5a1f9` + dos commits de docs: las lineas de codigo son las de main). Solo lectura del
arbol. Todo `archivo:linea` verificado hoy con `sed -n`/`grep -n`. Lo del CLI se verifico con `claude
--help`, `codex exec --help`, `strings` sobre los binarios y UNA sonda real (seccion A.6: una llamada por
suscripcion, sin herramientas, en un directorio vacio; costo 0.09 USD de lista, ventana 5h al 37 %).

Contenido:
- A. Claude Code 2.1.270 y Codex 0.142.4: flags, sandbox, hook, stream-json (con la sonda entera)
- B. systemd-run, bwrap, socat en esta maquina
- C. El repo: goals.py, server.py, capabilities, dispatch, permisos, aduana, detector, economia, github,
  carga, consumo, sesiones, fabrica, PWA, tests, conftest
- Trampas
- No confirmado

---

## A. Los CLIs

### A.1 `claude` 2.1.270: donde esta y que es

- `which claude` -> `/home/pedro/.local/bin/claude` -> symlink a
  `/home/pedro/.local/share/claude/versions/2.1.270`, ELF x86-64 (bun + JS embebido; `strings -n 6` da
  488.909 lineas; los textos citados abajo salen de ahi).
- `claude -p --help` imprime la MISMA ayuda que `claude --help`.

### A.2 Flags verificadas (texto de `claude --help`, 2026-09-13)

| flag | sintaxis / valores | nota |
|---|---|---|
| `-p, --print` | | "Input must be provided either through stdin or as a prompt argument when using --print" (string del binario): el prompt por stdin FUNCIONA (la sonda lo uso). |
| `--permission-mode <mode>` | `acceptEdits`, `auto`, `bypassPermissions`, `manual`, `dontAsk`, `plan` | `--restricted` rechaza `bypassPermissions`. |
| `--permission-prompts <target>` | `host` (default) o `none` | "none (nobody: anything that would prompt is denied automatically; the permission mode still decides everything else)". Solo con `--print`. |
| `--allowedTools, --allowed-tools <tools...>` | "Comma or space-separated list of tool names to allow (e.g. "Bash(git *) Edit")" | acepta patrones `Bash(git *)`; el parser del binario los trata como variadicos (`--allowedTools` esta en el set de flags que consumen varios tokens). |
| `--disallowedTools, --disallowed-tools <tools...>` | idem | "list of tool names to deny". |
| `--tools <tools...>` | `""` = ninguno, `"default"` = todos, o `"Bash,Edit,Read"` | Solo builtins: la sonda con `--tools ''` igual listo `StructuredOutput` (de `--json-schema`) y 11 tools MCP de `claude.ai Google Drive` (ver A.6). Sin `--strict-mcp-config` los MCP del usuario ENTRAN aunque `--setting-sources` este vacio. |
| `--restricted` | | "removes the built-in tools that run commands or code (Bash, PowerShell, REPL...) and WebFetch unless --tools names them, and ignores user, project and local settings files (managed settings and --settings still apply; add --strict-mcp-config to skip MCP servers too). Also confines the file tools to the working directories (--add-dir included), refuses bypassPermissions, and lets only a person or the configured permission handler approve writes to settings, git and tool-configuration files." Con `--permission-prompts none` esas escrituras quedan denegadas. String del binario: `permissionDecision=allow ignored: a confined session takes grants only from its command line` (un hook NO puede dar allow bajo `--restricted`; deny si). |
| `--setting-sources <sources>` | "Comma-separated list of setting sources to load (user, project, local)" | Parser del binario (funcion `tTr`): `if(e==="")return[]` -> la cadena vacia es VALIDA y significa ninguno; cualquier otro token distinto de user/project/local lanza `Invalid setting source: X. Valid options are: user, project, local`. Con `[]` quedan solo `flagSettings` (lo de `--settings`) y `policySettings` (managed). La sonda con `--setting-sources ''` ignoro el `model` de `~/.claude/settings.json` (`claude-fable-5-1[1m]`) y corrio `claude-opus-5[1m]`. |
| `--strict-mcp-config` | | "Only use MCP servers from --mcp-config, ignoring all other MCP configurations". |
| `--settings <file-or-json>` | ruta o JSON inline | "Path to a settings JSON file or a JSON string to load additional settings from". Errores del binario: `Error: Invalid JSON provided to --settings`, `Error: Settings file not found:`, `Error: Settings file exceeds the NMiB limit`. La funcion que digiere `--settings` extrae `sandboxSettings`, `envVars`, y `hasHooks: g, hooks: g ? e.hooks : void 0` (los `hooks` del `--settings` se leen; que se EJECUTEN en `-p` no se corrio: No confirmado). |
| `--output-format <format>` | `text`, `json`, `stream-json` | Solo con `--print`. Binario: `Error: When using --print, --output-format=stream-json requires --verbose` (verificado en la sonda: con `--verbose` anda). |
| `--verbose` | | obligatorio con `stream-json`. |
| `--include-hook-events` | | "Include all hook lifecycle events in the output stream (only works with --output-format=stream-json)". Emite `{"type":"system","subtype":"hook_started"|"hook_progress"|"hook_response",...}` (A.5). |
| `--json-schema <schema>` | JSON inline | "JSON Schema for structured output validation". El binario valida: `--json-schema is not valid JSON`, `must be a JSON object`. Aparece como herramienta `StructuredOutput` y el veredicto sale en `result.structured_output` (dict) y `result.result` (string JSON). Subtype de fallo: `error_max_structured_output_retries`. |
| `--session-id <uuid>` | UUID valido | |
| `-r, --resume [value]` | id de sesion | la sesion tiene que estar persistida en `~/.claude/projects/<slug del cwd>/<id>.jsonl` (la sonda dejo el suyo ahi: A.6). `--no-session-persistence` (solo `--print`) es INCOMPATIBLE con `--resume` entre golpes: no pasarla. |
| `--append-system-prompt-file <file>` | ruta | la usa el server hoy (`server.py:3538`). |
| `--append-system-prompt <prompt>`, `--system-prompt <prompt>` | | |
| `--input-format <format>` | `text` (default), `stream-json` | "realtime streaming input"; exige `--print` y `--output-format=stream-json` (strings: `--input-format=stream-json requires output-format=stream-json`). No hace falta para el golpe: el prompt va por stdin en modo `text`. |
| `--add-dir <directories...>` | rutas | "Additional directories to allow tool access to" (solo file tools). |
| `--model <model>` | alias (`opus`, `sonnet`, `fable`) o nombre completo | |
| `--effort <level>` | `low, medium, high, xhigh, max` | |
| `--max-budget-usd <amount>` | | solo `--print`; es de API, no de cuota. |
| `--bare` | | salta hooks y "OAuth and keychain are never read": mata la suscripcion. NO usar. |
| `--safe-mode` | | apaga customizaciones; auth normal. |
| `-w, --worktree [name]` | | crea `<repo>/.claude/worktrees/<name>`. No se usa (ruling 15.4: clon). |
| `--max-turns` | NO EXISTE como flag | solo aparece dentro de una lista interna de flags y como `maxTurns` de agentes; el tope del golpe es el timeout externo. |
| `--fallback-model`, `--agents`, `--mcp-config`, `--bg`, `--forward-subagent-text`, `--include-partial-messages`, `--replay-user-messages`, `--no-session-persistence`, `--fork-session` | existen | no se usan en el golpe. |

Flags que el SDK interno conoce y NO estan en `--help` (lista `["--allowedTools",...,"--max-turns","--task-budget",...]` del binario): `--max-turns` y `--task-budget` figuran en esa lista interna pero `claude --help` no los lista y la lente los probo ausentes; no apoyarse en ellos (No confirmado).

### A.3 Las claves del sandbox en `settings` (zod embebido en el binario, todas bajo `sandbox`)

Schema real (`u$t=f(()=>u({enabled:H().optional(), failIfUnavailable:..., autoAllowBashIfSandboxed:H().optional(), allowUnsandboxedCommands:..., network:el(), filesystem:tl(), credentials:sl(), ignoreViolations:..., enableWeakerNestedSandbox:..., excludedCommands:T(o()).optional(), ripgrep:..., bwrapPath:..., socatPath:...})`).

| clave | tipo | estado | descripcion textual del binario |
|---|---|---|---|
| `sandbox.enabled` | bool | CONFIRMADA (schema) | |
| `sandbox.failIfUnavailable` | bool | CONFIRMADA | "Exit with an error at startup if sandbox.enabled is true but the sandbox cannot start (missing dependencies or unsupported platform). When false (default), a warning is shown and commands run unsandboxed." **Ponerla en `true`**: sin ella el sandbox falla ABIERTO. |
| `sandbox.allowUnsandboxedCommands` | bool | CONFIRMADA | "Allow commands to run outside the sandbox via the dangerouslyDisableSandbox parameter. When false, the dangerouslyDisableSandbox parameter is completely ignored and all commands must run sandboxed. Default: true." |
| `sandbox.excludedCommands` | list[str] | CONFIRMADA (schema, sin descripcion) | el binario tiene la accion `sandbox_exclude_command` que agrega un patron a esa lista en los settings del usuario. |
| `sandbox.autoAllowBashIfSandboxed` | bool | CONFIRMADA (schema, sin descripcion propia) | mencion textual: "sandbox.autoAllowBashIfSandboxed is independent and still defaults to true, so set it to false to keep prompting for sandboxed commands". Con `true` + `acceptEdits` + `permission-prompts none`, un Bash sandboxeado corre sin prompt; es lo que el golpe quiere. |
| `sandbox.filesystem.allowWrite` | list[str] | CONFIRMADA | "Additional paths to allow writing within the sandbox. Merged with paths from Edit(...) allow permission rules." |
| `sandbox.filesystem.denyWrite` | list[str] | CONFIRMADA | "Additional paths to deny writing within the sandbox. Merged with paths from Edit(...) deny permission rules." |
| `sandbox.filesystem.denyRead` | list[str] | CONFIRMADA | "Additional paths to deny reading within the sandbox. Merged with paths from Read(...) deny permission rules." En Linux se implementa con tmpfs sobre la ruta (`[Sandbox Linux] Re-bound write path wiped by denyRead tmpfs`). |
| `sandbox.filesystem.allowRead` | list[str] | CONFIRMADA | "Paths to re-allow reading within denyRead regions. Takes precedence over denyRead for matching paths." |
| `sandbox.filesystem.allowManagedReadPathsOnly`, `sandbox.filesystem.disabled` | | existen | no usar. |
| `sandbox.network.allowedDomains` | list[str] | CONFIRMADA | wildcard: "Wildcards are only allowed as a single trailing "*"". |
| `sandbox.network.deniedDomains` | list[str] | CONFIRMADA | "Domains that are always blocked, even if matched by allowedDomains." |
| `sandbox.network.strictAllowlist` | bool | CONFIRMADA | "When true, the sandbox runtime deterministically denies hosts not in allowedDomains instead of prompting. Enforced for sandboxed commands only — in-process tools such as WebFetch are not gated by..." **Ponerla en `true`** (sin ella un host fuera de la lista pide permiso; bajo `none` se niega igual, pero la fila del hook cambia). WebFetch/WebSearch son in-process: el sandbox NO los filtra. |
| `sandbox.network.allowUnixSockets` | list[str] | CONFIRMADA | "macOS only: Unix socket paths to allow. Ignored on Linux (seccomp cannot filter by path)." |
| `sandbox.network.allowAllUnixSockets` | bool | CONFIRMADA | "If true, allow all Unix sockets (disables blocking on both platforms)." |
| `sandbox.network.allowLocalBinding`, `httpProxyPort`, `socksProxyPort`, `allowManagedDomainsOnly`, `tlsTerminate` | | existen | no usar. |
| `sandbox.credentials.files[]` `{path, mode: deny|mask, extract}`, `sandbox.credentials.envVars[]` `{name, mode}` | | CONFIRMADAS | "deny blocks reads inside the sandbox" para archivos; "deny unsets the variable for sandboxed commands" para env. Alternativa a `denyRead` para credenciales sueltas. |
| `sandbox.enableWeakerNestedSandbox`, `ignoreViolations`, `bwrapPath`, `socatPath`, `enabledPlatforms`, `ripgrep` | | existen | `bwrapPath`/`socatPath` "Only honored from admin-controlled managed settings". |

Resolucion de rutas: "Same resolution as sandbox.filesystem.* paths: absolute, ~ expanded, or relative to the settings file root (project root for project settings, ~/.claude for user settings)". Para `--settings` inline no se dice cual es la raiz: **usar rutas ABSOLUTAS** en el JSON del goal.

Dependencias en Linux (strings): `bubblewrap (bwrap) not installed`, `socat not installed`, `seccomp not available - unix socket access not restricted`. El proxy de red es `socat ... TCP-LISTEN:3128,fork,reuseaddr UNIX-CONNECT:` (http) y `TCP-LISTEN:1080` (socks) dentro del bwrap. Aviso textual: "Sandboxed commands lose your home directory (SSH keys, home-installed tools) until you re-open paths with sandbox.filesystem.allowRead" (el sandbox tapa HOME por defecto en algun modo; No confirmado cual sin correrlo).

### A.4 El protocolo del hook `PreToolUse`

Schema del hook de comando (zod `Rd()`): `{type:"command", command:<str>, args:<list[str]> opcional, if:<matcher>, shell:"bash"|"powershell", timeout:<n positivo, segundos>, statusMessage, once, async, asyncRewake}`. Texto de `args`: "Argument list for exec form. When present, `command` is resolved as an executable and spawned directly with these arguments — no shell. ... When absent, `command` runs through a shell (bash on POSIX...)". **Usar la forma exec**: `{"type":"command","command":"/var/home/pedro/calipso/.venv/bin/python","args":["/ruta/absoluta/calipso/goals_hook.py"],"timeout":20}`.

Forma en settings: `{"hooks":{"PreToolUse":[{"matcher":"Bash|Edit|Write|MultiEdit|Read|Glob|Grep|WebFetch|WebSearch","hooks":[{...}]}]}}` (doc embebida: "Common tool matchers: Bash, Write, Edit, Read, Glob, Grep").

Stdin (JSON, una linea). Schema zod: `{hook_event_name:"PreToolUse", tool_name, tool_input, tool_use_id}` sobre una base comun; la doc embebida lista `session_id`, `transcript_path`, `cwd`, `permission_mode` como campos comunes; la lente vio ademas `scratchpad_dir`, `prompt_id`, `agent_id`. `tool_input` de Bash es `{"command": "...", "description"?, "timeout"?}`; de Edit/Write `{"file_path": ..., ...}`.

Salida:
- Exit 2: "Exit code 2 - show stderr to model and block tool call". El motivo va por STDERR.
- Exit 0 con JSON en stdout: `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"|"deny"|"ask","permissionDecisionReason":"...","updatedInput":{...}}}`. `decision:"block"` esta "deprecated for PreToolUse".
- Cualquier otro exit: "Other exit codes - show stderr to user only but continue with tool call" (FAIL-OPEN). Strings: `Failed with non-blocking status code:`, `. Treating as non-blocking. `, `Hook command failed to spawn (`, `]: blocked (exit 2); its output could not be processed`.
- Bajo `--restricted`, `allow` se ignora (`permissionDecision=allow ignored: a confined session takes grants only from its command line`); `deny` vale. Bajo `--permission-prompts none`, `ask` es deny.
- Timeout: `timeout` en segundos por hook (schema). El DEFAULT del hook de comando NO se pudo leer del binario (solo "default 60" para el hook de agente). Un hook que vence: string `hook timed out` -> No confirmado si bloquea o no; asumir fail-open y poner `timeout` explicito bajo (20 s) y sonda (A.5).

### A.5 Eventos del `stream-json` (verificado con la sonda y con el JS)

Orden real observado (A.6): `system/init` -> `rate_limit_event` -> `assistant` (uno POR BLOQUE de contenido: text y tool_use salen en lineas separadas con el mismo `message.id`) -> `user` con `tool_result` -> `result`.

- `{"type":"system","subtype":"init","cwd","session_id","tools":[...],"mcp_servers":[{name,status}],"model","permissionMode","slash_commands","apiKeySource","claude_code_version","output_style","agents","skills","plugins","capabilities","uuid","messaging_socket_path",...}`.
- `{"type":"rate_limit_event","rate_limit_info":{"status":"allowed","resetsAt":<epoch>,"rateLimitType":"five_hour","overageStatus":"rejected","overageDisabledReason":"out_of_credits","isUsingOverage":false,"unifiedWindows":{"five_hour":{"utilization":0.37,"resetsAt":...},"seven_day":{"utilization":0.13,"resetsAt":...}}},"session_id"}`. **Claude SI expone la cuota en el stream** (la lente y `consumo.py` decian que no): `utilization` 0..1 por ventana. El runner lo lee del propio golpe.
- `{"type":"assistant","message":{"model","id":"msg_...","role","content":[{"type":"text","text"}|{"type":"tool_use","id":"toolu_...","name","input":{...}}],"usage":{input_tokens,cache_creation_input_tokens,cache_read_input_tokens,output_tokens,...}},"parent_tool_use_id":null,"session_id","uuid","timestamp","request_id","wire_tool_inputs"?}`. Para contar LLAMADAS API: distintos `message.id` (o `request_id`), no lineas `assistant`.
- `{"type":"user","message":{"role":"user","content":[{"tool_use_id","type":"tool_result","content":"..."}]},"tool_use_result":...,"session_id",...}`.
- `{"type":"system","subtype":"hook_started","hook_id","hook_name","hook_event"}`, `hook_progress` (+`stdout`,`stderr`,`output`), `hook_response` (+`output`,`stdout`,`stderr`,`exit_code`?,`outcome`) — solo con `--include-hook-events` (`setAllHookEventsEnabled`; `SessionStart` y `Setup` salen siempre). El hook corre ENTRE el `assistant` con el `tool_use` y el `user` con el `tool_result`: la regla del parser es "para cada `tool_use` de una herramienta con hook, tiene que aparecer un `hook_response` con `hook_event:"PreToolUse"` ANTES del `tool_result` correspondiente", no antes del `tool_use`.
- `{"type":"result","subtype":"success"|"error_during_execution"|"error_max_turns"|"error_max_budget_usd"|"error_max_structured_output_retries","is_error","num_turns","result":<str>,"structured_output":<obj>,"stop_reason","duration_ms","duration_api_ms","total_cost_usd","usage":{...,"iterations":[{input_tokens,output_tokens,...,"type":"message"}, ...]},"modelUsage":{<modelo>:{inputTokens,outputTokens,costUSD,...}},"permission_denials":[...],"terminal_reason","session_id","result_index","uuid",...}`. **`usage.iterations` es la lista de llamadas API del turno**: `unidades = len(result.usage.iterations)` (la sonda: 1 iteracion, `num_turns: 2`, y `modelUsage` con una llamada extra a haiku de 900 tokens que NO figura en `iterations`).

### A.6 LA SONDA (una sola, sin herramientas, directorio vacio)

Comando (cwd = `.../scratchpad/sonda_vacia`, vacio antes y despues):

```
printf 'Responde solo la palabra hola' | claude -p --restricted --tools '' --setting-sources '' \
  --output-format stream-json --verbose \
  --json-schema '{"type":"object","properties":{"estado":{"type":"string"}},"required":["estado"]}'
```

exit 0, stderr vacio, 6 lineas de stdout (copiadas enteras; uuids y epochs reales):

```
{"type":"system","subtype":"init","cwd":"/tmp/claude-1000/-var-home-pedro/ebfda634-eb83-4bb3-ae22-845ab7d0582c/scratchpad/sonda_vacia","session_id":"cb01e83b-203f-41ce-bcde-4afe792e5a5d","tools":["StructuredOutput","mcp__claude_ai_Google_Drive__copy_file","mcp__claude_ai_Google_Drive__create_file","mcp__claude_ai_Google_Drive__download_file_content","mcp__claude_ai_Google_Drive__get_file_metadata","mcp__claude_ai_Google_Drive__get_file_permissions","mcp__claude_ai_Google_Drive__list_recent_files","mcp__claude_ai_Google_Drive__read_file_content","mcp__claude_ai_Google_Drive__search_files","mcp__claude_ai_Google_Drive__share_file","mcp__claude_ai_Google_Drive__trash_file","mcp__claude_ai_Google_Drive__update_file"],"mcp_servers":[{"name":"claude.ai Google Drive","status":"connected"}],"model":"claude-opus-5[1m]","permissionMode":"default","slash_commands":["deep-research","design","design-sync","dataviz","update-config","verify","debug","code-review","simplify","batch","fewer-permission-prompts","doctor","loop","schedule","claude-api","workflow-authoring","run","run-skill-generator","advisor","agents","auto-mode-setup","autocompact","clear","color","compact","config","output-style","context","effort","fast","heapdump","init","mcp","import","model","__remote-workflow","workflow-launch-exec","reload-plugins","reload-skills","rename","ultrareview","security-review","usage-credits","extra-usage","usage","insights","recap","skill-doctor","goal","design-consent","design-revoke","list-agents","team-onboarding"],"terminal_slash_commands":["doctor","color","reload-plugins"],"apiKeySource":"none","claude_code_version":"2.1.270","output_style":"default","agents":["claude","Explore","general-purpose","Plan","statusline-setup"],"skills":["deep-research","design","design-sync","dataviz","update-config","verify","debug","code-review","simplify","batch","fewer-permission-prompts","doctor","loop","schedule","claude-api","workflow-authoring","run","run-skill-generator"],"plugins":[],"capabilities":["interrupt_receipt_v1","interrupt_cancel_queued_v1","msg_lifecycle_v1"],"analytics_disabled":false,"product_feedback_disabled":false,"uuid":"43d34ba8-ab9e-42e0-8f14-83c6e003d339","messaging_socket_path":"/run/user/1000/cc-socks/1272400.sock","fast_mode_state":"off","fast_mode_disabled_reason":"sdk_opt_in_required"}
{"type":"rate_limit_event","rate_limit_info":{"status":"allowed","resetsAt":1789330200,"rateLimitType":"five_hour","overageStatus":"rejected","overageDisabledReason":"out_of_credits","isUsingOverage":false,"unifiedWindows":{"five_hour":{"utilization":0.37,"resetsAt":1789330200},"seven_day":{"utilization":0.13,"resetsAt":1789819200}}},"uuid":"7123a1cd-b620-4cec-9609-7bd7cff206fe","session_id":"cb01e83b-203f-41ce-bcde-4afe792e5a5d"}
{"type":"assistant","message":{"model":"claude-opus-5","id":"msg_011Cf1oo1uLFYBY4mwBsQx17","type":"message","role":"assistant","content":[{"type":"text","text":"hola"}],"container":null,"stop_reason":null,"stop_sequence":null,"stop_details":null,"usage":{"input_tokens":2,"cache_creation_input_tokens":9016,"cache_read_input_tokens":0,"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":9016},"output_tokens":1,"service_tier":"standard","inference_geo":"not_available"},"diagnostics":null,"context_management":null},"parent_tool_use_id":null,"session_id":"cb01e83b-203f-41ce-bcde-4afe792e5a5d","uuid":"441c7059-89e1-415a-bb3f-2996e907d06b","timestamp":"2026-09-13T17:09:05.048Z","request_id":"req_011Cf1oo1DubM1FCEVfWqqGk"}
{"type":"assistant","message":{"model":"claude-opus-5","id":"msg_011Cf1oo1uLFYBY4mwBsQx17","type":"message","role":"assistant","content":[{"type":"tool_use","id":"toolu_01MV68ts7VL7qWQhmTqyPDAg","name":"StructuredOutput","input":{"estado":"hola"},"caller":{"type":"direct"}}],"container":null,"stop_reason":null,"stop_sequence":null,"stop_details":null,"usage":{"input_tokens":2,"cache_creation_input_tokens":9016,"cache_read_input_tokens":0,"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":9016},"output_tokens":1,"service_tier":"standard","inference_geo":"not_available"},"diagnostics":null,"context_management":null},"parent_tool_use_id":null,"session_id":"cb01e83b-203f-41ce-bcde-4afe792e5a5d","uuid":"55a27872-7fdc-4784-bf46-74629018644a","timestamp":"2026-09-13T17:09:05.061Z","request_id":"req_011Cf1oo1DubM1FCEVfWqqGk","wire_tool_inputs":{"toolu_01MV68ts7VL7qWQhmTqyPDAg":{"estado":"hola"}}}
{"type":"user","message":{"role":"user","content":[{"tool_use_id":"toolu_01MV68ts7VL7qWQhmTqyPDAg","type":"tool_result","content":"Structured output provided successfully"}]},"parent_tool_use_id":null,"session_id":"cb01e83b-203f-41ce-bcde-4afe792e5a5d","uuid":"b97f8476-c6c4-49c8-8623-cb5a97308bc0","timestamp":"2026-09-13T17:09:05.066Z","tool_use_result":"Structured output provided successfully"}
{"duration_api_ms":3249,"stop_reason":"tool_use","session_id":"cb01e83b-203f-41ce-bcde-4afe792e5a5d","total_cost_usd":0.09253999999999998,"usage":{"input_tokens":2,"cache_creation_input_tokens":9016,"cache_read_input_tokens":0,"output_tokens":56,"output_tokens_details":{"thinking_tokens":0},"server_tool_use":{"web_search_requests":0,"web_fetch_requests":0},"service_tier":"standard","cache_creation":{"ephemeral_1h_input_tokens":9016,"ephemeral_5m_input_tokens":0},"inference_geo":"not_available","iterations":[{"input_tokens":2,"output_tokens":56,"cache_read_input_tokens":0,"cache_creation_input_tokens":9016,"cache_creation":{"ephemeral_5m_input_tokens":0,"ephemeral_1h_input_tokens":9016},"type":"message"}],"speed":"standard"},"modelUsage":{"claude-haiku-4-5-20251001":{"inputTokens":900,"outputTokens":14,"cacheReadInputTokens":0,"cacheCreationInputTokens":0,"webSearchRequests":0,"costUSD":0.0009699999999999999,"contextWindow":200000,"maxOutputTokens":32000,"thinkingTokens":0,"canonicalModel":"claude-haiku-4-5","provider":"firstParty","costBasis":"list"},"claude-opus-5[1m]":{"inputTokens":2,"outputTokens":56,"cacheReadInputTokens":0,"cacheCreationInputTokens":9016,"webSearchRequests":0,"costUSD":0.09156999999999998,"contextWindow":1000000,"maxOutputTokens":64000,"thinkingTokens":0,"canonicalModel":"claude-opus-5","provider":"firstParty","costBasis":"list"}},"permission_denials":[],"terminal_reason":"completed","fast_mode_state":"off","fast_mode_disabled_reason":"sdk_opt_in_required","subagent_stats":{"spawned":0,"requested":{"background":0,"foreground":0,"unset":0},"started_in_background":0,"max_depth":0,"spawned_by_subagents":0,"completed":0,"failed":0,"killed":{"parent":0,"user":0,"system":0},"refused":{"depth_limit":0,"concurrency_limit":0,"budget":0},"by_type":{}},"is_error":false,"num_turns":2,"subtype":"success","api_error_status":null,"result":"{\"estado\":\"hola\"}","structured_output":{"estado":"hola"},"ttft_ms":1969,"type":"result","duration_ms":2194,"uuid":"cb4d8b8e-af1b-413c-8d5f-d65f1b3d69ef","ttft_stream_ms":870,"time_to_request_ms":30,"first_content_frame_ms":870,"queued_turn_count":0,"result_index":0}
```

Lo que la sonda demostro: (1) stdin como prompt funciona; (2) `--setting-sources ''` es valido; (3) `--restricted --tools ''` deja `StructuredOutput` + MCP de claude.ai: hace falta `--strict-mcp-config`; (4) existe `rate_limit_event` con `utilization` por ventana; (5) `usage.iterations` = llamadas API; (6) la sesion se PERSISTIO en `~/.claude/projects/-tmp-claude-1000--var-home-pedro-...-sonda-vacia/cb01e83b-....jsonl` (slug del cwd: para `--resume` el cwd del golpe N+1 tiene que ser el mismo clon); (7) el directorio quedo vacio (el CLI no escribe en el cwd); (8) `permissionMode: "default"` aunque no se paso `--permission-mode` (con `acceptEdits` cambiara).

### A.7 Codex 0.142.4

- `which codex` -> `/run/user/1000/fnm_multishells/<pid>_<ts>/bin/codex` (shim de fnm; el PATH del server puede no tenerlo: `_subscription_command` usa `shutil.which`). Node wrapper `.../@openai/codex/bin/codex.js`; binario nativo
  `.../@openai/codex/node_modules/@openai/codex-linux-x64/vendor/x86_64-unknown-linux-musl/bin/codex` (681.011 strings).
- `codex exec [OPTIONS] [PROMPT]`: "If not provided as an argument (or if `-` is used), instructions are read from stdin. If stdin is piped and a prompt is also provided, stdin is appended as a `<stdin>` block".
- `-s, --sandbox <read-only | workspace-write | danger-full-access>`; `-C, --cd <DIR>` "working root"; `--add-dir <DIR>` "Additional directories that should be writable alongside the primary workspace" (repetible); `--json` "Print events to stdout as JSONL"; `-o, --output-last-message <FILE>`; `--output-schema <FILE>` "Path to a JSON Schema file describing the model's final response shape" (ARCHIVO, no inline); `--ephemeral` "Run without persisting session files to disk"; `--skip-git-repo-check`; `-c key=value` (TOML); `-m <MODEL>`; `--ignore-user-config`; `--ignore-rules`; `--dangerously-bypass-approvals-and-sandbox`. Subcomandos `exec resume`, `exec review`.
- Config de red del sandbox: struct `SandboxWorkspaceWrite { writable_roots, network_access, exclude_tmpdir_env_var, exclude_slash_tmp }` y clave top `sandbox_workspace_write` (strings del nativo). En TOML: `[sandbox_workspace_write] network_access = true`, o `-c sandbox_workspace_write.network_access=true`. `~/.codex/config.toml` de Pedro (224 bytes, sin tokens) solo tiene `[projects."/var/home/pedro"] trust_level = "trusted"`, otro `projects` de un scratchpad viejo y `[tui.model_availability_nux] "gpt-5.5" = 1`: NO hay `sandbox_workspace_write` -> red apagada por defecto (default del CLI; no corrido).
- Cuota: strings `You've hit your usage limit.` (variantes con Plus/creditos/admin). En los jsonl de sesion: `rate_limits.primary.used_percent`, `resets_at`, `window_minutes` (lo lee `consumo._extraer_codex`, C.12). Con `--ephemeral` NO se escribe el jsonl de sesion: si el runner quiere `resets_at` de Codex, no usar `--ephemeral` o leer el `--json`.
- Eventos `--json` (nombres presentes en el nativo): `thread.started`, `turn.started`, `turn.completed`, `turn.failed`, `item.started`, `item.completed`; items con `command_execution` (`aggregated_output`, `exit_code`), `agent_message`, `file_change`, `web_search`. La forma exacta de cada linea NO se corrio (No confirmado).
- Sandbox de kernel: `landlock` x18, `seccomp` x12 en el nativo.

---

## B. La maquina

- `systemd-run --version` -> `systemd 259 (259.8-1.fc44)`. Prueba inocua: `systemd-run --user --scope -p RuntimeMaxSec=5 sleep 1` -> `Running as unit: run-p1270732-i1259773.scope; invocation ID: ...`, exit 0. **Funciona.** Con `--scope` el proceso corre en el cgroup del scope y `RuntimeMaxSec` lo mata entero (incluido lo que deje con `nohup`/`setsid`). Sumar `--unit=calipso-goal-<id>-<n>` para poder `systemctl --user stop` desde el apagado.
- `bwrap --version` -> `bubblewrap 0.12.0`, `/usr/bin/bwrap`.
- `socat` -> `/usr/bin/socat` (lo exige el proxy de red del sandbox de Claude Code; ver A.3).
- Interprete del hook: `/var/home/pedro/calipso/.venv/bin/python` (absoluto). El hook no debe importar `calipso` (fail-closed puro).

---

## C. El repo

### C.1 `calipso/goals.py` (443 lineas, Goal Mode viejo)

```python
# calipso/goals.py:20-25
CALIPSO_HOME = pathlib.Path(os.environ.get(
    "CALIPSO_HOME", os.path.expanduser("~/.calipso")))

ACTIVE_STATES = {"active", "waiting", "blocked"}
FINAL_STATES = {"complete", "cancelled"}
VALID_STATES = ACTIVE_STATES | FINAL_STATES
```

```python
# calipso/goals.py:28-48
def _slug(project_root: str | None) -> str:
    if not project_root:
        return "global"
    p = pathlib.Path(project_root).resolve()
    return str(p).replace(":", "").replace("\\", "-").replace("/", "-").strip("-")

def _goals_dir(project_root: str | None) -> pathlib.Path:
    d = CALIPSO_HOME / "projects" / _slug(project_root) / "goals"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _goal_dir(project_root: str | None, goal_id: str) -> pathlib.Path:
    d = _goals_dir(project_root) / goal_id
    d.mkdir(parents=True, exist_ok=True)
    return d

def _active_file(project_root: str | None) -> pathlib.Path:
    return _goals_dir(project_root) / "active.txt"
```

`detect` (:62-79): regex `^meta\s*:`, `^mi objetivo es`, `^persigue esto hasta dejarlo listo`, `^quiero que sigas con esto hasta completarlo`, `^dejame listo`, `^déjame listo` (IGNORECASE) -> devuelve el texto o None. `propose_criteria` (:82-118) y `propose_subtasks` (:121-132) inventan 5 items por palabras clave.

```python
# calipso/goals.py:135-163
def create(project_root: str | None, objective: str, title: str | None = None,
           criteria: list[dict[str, Any]] | list[str] | None = None,
           subtasks: list[dict[str, Any]] | list[str] | None = None,
           make_active: bool = True, **data: Any) -> dict[str, Any]:
    goal_id = f"goal_{uuid.uuid4().hex[:12]}"
    normalized_criteria = _normalize_items(
        criteria if criteria is not None else propose_criteria(objective),
        prefix="c", done_key=True)
    normalized_subtasks = _normalize_items(
        subtasks if subtasks is not None else propose_subtasks(objective),
        prefix="t", status_key=True)
    goal = {
        "id": goal_id,
        "title": title or _title_from(objective),
        "objective": objective.strip(),
        "status": "active",
        "criteria": normalized_criteria,
        "subtasks": normalized_subtasks,
        "evidence": [],
        "blockers": [],
        "created_at": _now(),
        "updated_at": _now(),
        **data,
    }
    _write(project_root, goal)
    event(project_root, goal_id, "created", objective=goal["objective"])
    if make_active:
        set_active(project_root, goal_id)
    return goal
```

```python
# calipso/goals.py:189-222
def _write(project_root: str | None, goal: dict[str, Any]) -> None:
    goal["updated_at"] = _now()
    p = _goal_dir(project_root, goal["id"]) / "goal.json"
    p.write_text(json.dumps(goal, ensure_ascii=False, indent=2), encoding="utf-8")

def load(project_root: str | None, goal_id: str) -> dict[str, Any] | None:
    p = _goal_dir(project_root, goal_id) / "goal.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

def set_active(project_root: str | None, goal_id: str | None) -> None:
    p = _active_file(project_root)
    if goal_id:
        p.write_text(goal_id, encoding="utf-8")
    elif p.exists():
        p.unlink()

def active(project_root: str | None) -> dict[str, Any] | None:
    p = _active_file(project_root)
    if not p.exists():
        return None
    goal_id = p.read_text(encoding="utf-8").strip()
    goal = load(project_root, goal_id) if goal_id else None
    if not goal or goal.get("status") in FINAL_STATES:
        set_active(project_root, None)
        return None
    return goal
```

`_write` NO es atomico (`write_text` directo, :192); `active()` BORRA `active.txt` si `load` falla por cualquier motivo (:219-221). `list_goals` (:225-234) hace `glob("*/goal.json")` por mtime. `update` (:237-260): valida `status in VALID_STATES` (levanta `ValueError("estado invalido")` :243-244), parchea `title/objective/criteria/subtasks`, `blocker` -> `status = "blocked"` (:253-257), escribe y anota `updated`. `add_evidence` (:263-272), `set_criterion` (:275-301, llama `check_auto_close`), `set_subtask` (:304-323), `add_criterion`/`add_subtask`/`edit_item_text`/`remove_item` (:335-389), `check_auto_close` (:392-421: `status = "complete"` si todos los criterios `done`).

```python
# calipso/goals.py:424-443
def event(project_root: str | None, goal_id: str, action: str,
          **data: Any) -> dict[str, Any]:
    entry = {"ts": _now(), "goal_id": goal_id, "action": action, **data}
    p = _goal_dir(project_root, goal_id) / "events.jsonl"
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry

def events(project_root: str | None, goal_id: str, limit: int = 200) -> list[dict[str, Any]]:
    p = _goal_dir(project_root, goal_id) / "events.jsonl"
    if not p.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
```

Quien llama a `goals.*` en el server (grep): `active(str(ROOT))` en :1348, :1385, :1473, :1597, :1635, :3125, :3629, :3864, :4844, :5531, :5569, :5572, :5734, :5744; `add_evidence` en :1365, :1394, :1513, :1612, :3636, :3703, :3748, :3772, :5577, :5627 y `developer.py:124, :141`; `detect`/`create` en :3944-3946 y :5540. `test_goals.py:27` fija `create -> status == "active"` y `:50-51` `update(status="complete")` limpia activa: conservar `create`/`update` para lo viejo; el `transicionar` nuevo es otra puerta. Otros tests que tocan `goals.`: test_attachments (2), test_commands (2), test_developer (1), test_proposals (2), test_verification (2), test_abismo_chat (1: el monkeypatch).

Molde atomico a copiar para `goal.json`/`activo.json`:

```python
# calipso/catastro.py:204-215
def _guardar_json(data: dict[str, Any]) -> None:
    """Atomico, mismo patron que routines.save(): temporal en el mismo
    directorio + os.replace, para que un lector concurrente nunca vea un
    JSON a medio escribir."""
    p = _file()
    tmp = p.with_name(f"{p.name}.tmp{os.getpid()}.{threading.get_ident()}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, p)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()
```

### C.2 `server.py`: los bloques del goal viejo

Bloque `goals.detect` (corre en CADA turno, ANTES de `_decide`):

```python
# calipso/server.py:3944-3966
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
```

Justo despues (:3971-3972): `verdict, features, ranked, directives = await asyncio.to_thread(_decide, user_msg, _last_features, _last_verdict)`. Al conectar el ws (:3864-3866) se emite `{"type":"goal","action":"active","goal":...}` si hay activo; al cierre del turno (:4844-4850) `goal/auto_closed` si el activo quedo `complete`.

```python
# calipso/server.py:3124-3158 (recortado a lo que importa)
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
    ...  # criterios[:8], subtareas[:8], evidencia[-5:], bloqueos[-3:]
    return "\n".join(lines)
```

Lo inyecta `prompt_compiler.py:236-237` (`if goal_block: sections.append(("Meta activa", goal_block))`) via `_sistema_del_turno` (:3281). `_goal_response` (:3161-3172) es texto fijo.

Endpoints (todos `def`, threadpool, todos con `str(ROOT)`):

```python
# calipso/server.py:5528-5544
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
```

```python
# calipso/server.py:5547-5572
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
```

`POST .../evidence` (:5575-5580), `POST .../advance` (:5583-5588 -> `developer.advance_goal`), `POST .../draft` (:5591-5636, `async`, usa `_run_subscription_text("claude", ..., "sonnet")` y `PENDING_CHANGES`), `PUT .../criteria/{id}` (:5639-5649), `PUT .../subtasks/{id}` (:5652-). Modelos (:1251-1283): `GoalBody{objective, title, criteria, subtasks, make_active=True}`, `GoalUpdateBody{title, objective, status, criteria, subtasks, blocker, active}`, `GoalEvidenceBody{kind="note", text, data}`, `GoalCriterionBody{done=True, evidence}`, `GoalSubtaskBody{status="done"}`.

### C.3 `server.py`: el molde `/redacta`, `_gesto_de`, `_gesto_local`, `_decide`

```python
# calipso/server.py:4007-4030 (la rama corre DESPUES de _decide, ANTES del ruteo)
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
                    uso_local.soltar()     # como /help y /mia: la salida temprana no deja el contador en 1
                    continue
                system_b, user_b = compositor_redactor.preparar_borrador(
                    pedido, chats._load(), compositor_ejemplos.cargar())
```

`chat_msg` es `directives["clean"]` (el texto sin slashes). Regla del molde: toda salida temprana emite `done`, hace `uso_local.soltar()` y `continue`.

```python
# calipso/server.py:326-345
def _gesto_de(directives: dict) -> str | None:
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
```

`_gesto_local` (:2510-2540): `/local`, `/redacta`, `/otra`, `features.private` -> `"prompt privado"`, `/model X` local, `"sin suscripcion"`. `_decide` (:2582-2690): `d = parse_directives(user_msg)`; `features = dispatch.extract_features(d["clean"])`; `sel_effort = d["effort"] or derive_effort(complexity)`; mide carga (`_medir_carga()`, :2606); `avail = _backend_availability()`; `_rankear` (:2620-2636) = `capabilities.choose(features, sel_effort, disponibles, quota, project_root=str(ROOT))` + filtro `force_route` + saca `api` salvo `/api` + `force_model`; bajo `cargada` apaga los locales (:2646-2652); veredicto `{route, client, model, model_id, persona, tier, effort, effort_name, session, source, why}` (:2670-2681). Para la cabeza de la propuesta: llamar `_decide(texto_del_goal)` en hilo y pisar `sel_effort` con `EFFORT["ultra"]` (3) para el piso frontera (`EFFORT_MIN_TIER[3] == 2`), o rankear a mano con `capabilities.choose(features, 3, avail)`.

### C.4 `server.py`: `_subscription_invocation`, los runners, el entorno

```python
# calipso/server.py:3490-3514
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
    history = _history_messages(chat_id)
    ...
    prompt = f"{history_block}Pedro: {user_msg}\nCalipso:"
```

```python
# calipso/server.py:3515-3548
    temp_names: list[str] = []
    if len(prompt) > 7000:
        with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", suffix=".prompt.md", delete=False,
                dir=str(ROOT)) as f:
            f.write(prompt)
            prompt_name = f.name
            temp_names.append(prompt_name)
        prompt = ("Lee el prompt completo desde este archivo local ...")
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
        cmd = [(exe if i == 0 else
                arg.replace("{prompt}", prompt).replace("{output}", output_name))
               for i, arg in enumerate(template)]
        if model and model.startswith("gpt"):  # elige el modelo de Codex
            cmd[1:1] = ["-m", model]  # tras 'exec'... insertamos antes de exec
```

```python
# calipso/server.py:3557-3565 (lo UNICO que el golpe reusa: el entorno)
    env = calipso_github.env_git_blindado(anular_global=False)
    env.pop("CALIPSO_TOKEN", None)
    env.pop("LITELLM_MASTER_KEY", None)
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    return cmd, env, temp_names, output_name
```

`_cleanup_subscription_files` (:3567-3580). `_subscription_command(client)` (:2239-2242) = `shutil.which(client)` en Linux. `_run_subscription_text` (:3582-3599): `subprocess.run(cmd, cwd=str(ROOT), ..., timeout=None, env=env)`, exit != 0 -> `RuntimeError(stderr or stdout)`; codex lee `output_name`.

`_run_subscription_text_live` (:3602-3805), el molde del Popen sondeado:

```python
# calipso/server.py:3620-3639
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
```

```python
# calipso/server.py:3662-3699 (recortado)
        while proc.poll() is None:
            now = time.perf_counter()
            if now - last_notice >= 2:
                partial, _ = _read_partial()
                ...
                await ws.send_json({"type": "process", "action": "running", ...})
                jobs.event(str(ROOT), job["id"], "running", elapsed=round(now - started), ...)
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
                    ...
            await asyncio.sleep(1.5)
        await asyncio.to_thread(proc.wait)
        partial, stderr = _read_partial()
        if proc.returncode != 0:
            msg = _limpiar_marcas(stderr or partial or "").strip()
            jobs.update(str(ROOT), job["id"], status="failed", error=msg)
```

Al final (:3760-3776): `process/done`, `jobs.update(done)`, `write_artifact("output.txt")`, `add_evidence` al goal viejo; `finally` (:3790-3805) cierra y borra stdout/stderr temporales. Sin `start_new_session`, sin timeout. No hay `killpg`/`os.setsid` en todo `server.py` (grep vacio, verificado por la lente).

`_history_messages` (:3330-3348): ultimos `_HISTORY_TURNS` mensajes del chat (`text`, no `meta`); con `chat_id=None` devuelve `[]`.

### C.5 `server.py`: fondo, arranque, apagado, cobro, inbox

```python
# calipso/server.py:2437-2453
_TAREAS_DE_FONDO: set[asyncio.Task] = set()
REMEMBER_EN_VUELO_MAX = 2
_SEMAFORO_REMEMBER: tuple[asyncio.AbstractEventLoop, asyncio.Semaphore] | None = None
FONDO_PLAZO_APAGADO_S = 10.0

def _en_fondo(coro) -> asyncio.Task:
    tarea = asyncio.create_task(coro)
    _TAREAS_DE_FONDO.add(tarea)
    tarea.add_done_callback(_TAREAS_DE_FONDO.discard)
    return tarea
```

```python
# calipso/server.py:2467-2477
async def _esperar_fondo_al_apagar(plazo: float = FONDO_PLAZO_APAGADO_S) -> None:
    vivas = [t for t in list(_TAREAS_DE_FONDO) if not t.done()]
    if not vivas:
        return
    _, pendientes = await asyncio.wait(vivas, timeout=plazo)
    if pendientes:
        telemetry.log_event("memoria", accion="remember_pendiente", n=len(pendientes))
```

```python
# calipso/server.py:8897-8931
@app.on_event("startup")
async def _startup_warm() -> None:
    try:
        found = await asyncio.to_thread(discovery.discover, True)
        ...
    except Exception:
        pass
    try:
        await asyncio.to_thread(_calentar_probes)
    except Exception:
        pass
    try:
        await asyncio.to_thread(_anunciar_memoria)
    except Exception:
        pass
    await asyncio.to_thread(_asegurar_rutina_catastro)
    await asyncio.to_thread(_asegurar_rutina_cierre)
    await asyncio.to_thread(_asegurar_rutina_consumo)
    try:
        asyncio.create_task(_routines_ticker())
    except Exception:
        pass

@app.on_event("shutdown")
async def _shutdown_fondo() -> None:
    try:
        await _esperar_fondo_al_apagar()
    except Exception:
        pass
```

El ticker (`create_task` pelado, :8919) muere con el loop; maneja `CancelledError` (:5936-5937). Sitio para `_GOALS_EN_CURSO`: un `dict` a nivel de modulo junto a :2437, `_reconciliar_goals` en `_startup_warm` (en `to_thread`, antes del ticker) y `_apagar_goals` en `_shutdown_fondo` ANTES de `_esperar_fondo_al_apagar` (matar el Popen y escribir `waiting` en hilo: `goals.transicionar` bajo `to_thread`).

```python
# calipso/server.py:8787-8826 (firma y cuerpo util)
def _cobrar_turno(cuenta: str, route: str, client: str | None,
                  model: str | None, usage: dict) -> int:
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
    except Exception as exc:
        print(f"[calipso] no se pudo cobrar el turno a {cuenta}: {exc}",
              file=sys.stderr)
    return 0
```

No pasa `unidades` ni `ref`: para el goal, llamar `pagador.cargar_suscripcion(ts, semana, cuenta, _eco_suscripcion(client), unidades=<n>)` directo (la firma lo admite: C.9) desde un hilo. `_cuenta_en_foco(departamento)` (:8740-8750) -> `"personal"` si no hay departamento registrado. `_eco_ahora()` (:6003) devuelve `(ts, semana)`; `_ECO_BASE` (:5980) es `CALIPSO_HOME` (los tests lo parchean a `tmp_path/.calipso`).

```python
# calipso/server.py:1485-1491 (_run_chat_draft._cobrar_borrador: el molde de "cada golpe cobra")
        def _cobrar_borrador() -> None:
            _cobrar_turno(_cuenta_en_foco(departamento), "subscription",
                          "claude", "sonnet", {})

        await asyncio.to_thread(_cobrar_borrador)
```

`api_inbox` (:6518-6580): `def`, arma `obtener_bus/obtener_cola/obtener_permisos/obtener_memoria` como callables, toma `_eco_candado(p0.ruta_libro)` una vez y llama `_inbox.juntar(obtener_bus, obtener_permisos, obtener_memoria, ROOT.name, obtener_cola)`; devuelve `{"items", "descriptores": _inbox.descriptores(), "pendientes": cuenta_de_decisiones(items), "fallaron"}`. `obtener_permisos` = `{"activo": True, **_permisos.vista()}`.

```python
# calipso/inbox.py:56-57 y 83-99
def juntar(obtener_bus, obtener_permisos, obtener_memoria, proyecto: str,
           obtener_cola) -> tuple[list[dict], list[str]]:
    ...
    llamadas = [
        ("mesa", eco_bus, lambda: eco_bus.como_items(obtener_bus())),
        ("permisos", permisos_motor,
         lambda: permisos_motor.como_items(obtener_permisos())),
        ("biblioteca", librarian,
         lambda: librarian.como_items(obtener_memoria(), proyecto)),
        ("cartas", eco_cola, lambda: eco_cola.como_items(obtener_cola())),
    ]
    for nombre, modulo, fn in llamadas:
        if modulo is None:
            fallaron.append(nombre)
            continue
        try:
            items.extend(fn())
        except Exception:
            fallaron.append(nombre)
    return items, fallaron
```

`descriptores()` (:50-53) junta `m.descriptor()` de `(eco_bus, permisos_motor, librarian, eco_cola)`. `test_inbox_server.py:140-143` llama `juntar` con exactamente 5 posicionales y espera `set(descriptores) == {"mesa","permisos","cartas"}` sin biblioteca: sumar un quinto origen `goals` rompe esa firma y ese assert (parametro nuevo al final con default `None` y el assert se actualiza). La pregunta del goal puede ir SIN origen nuevo si se estaciona en el motor de permisos (aparece como item `permisos`).

`HELP_TEXT` (:2194-2203): lista `/fast /think /ultrathink /model /local /claude /codex /api /help`; no lista `/web /nube /redacta /otra /mia /plan`.

### C.6 `capabilities.py`

```python
# calipso/capabilities.py:28-35
TIER_RANK = {"small": 0, "mid": 1, "frontier": 2, "apex": 3}
EFFORT = {"fast": 0, "balanced": 1, "think": 2, "ultra": 3}
EFFORT_NAME = {v: k for k, v in EFFORT.items()}
EFFORT_MIN_TIER = {0: 0, 1: 0, 2: 1, 3: 2}
EFFORT_PARAM = {0: "low", 1: "medium", 2: "high", 3: "xhigh"}
```

`REGISTRY` (:41-100): `local:qwen2.5:3b` (small, cost 0, max_complexity 2), `local:qwen2.5:7b` (small, cost 0, speed 0.3, max_complexity 3, `code 0.3, analysis 0.5`), `subscription:claude:haiku` (small), `subscription:claude:sonnet` (mid, `agentic 0.8, repo 0.8`), `subscription:claude:opus` (frontier, `agentic 0.9, repo 0.9, code 0.95`), `subscription:codex:gpt-5.5` (frontier, `code 1.0, agentic 1.0, repo 1.0, exec 1.0`), `api:deepseek-chat` (mid, cost 3), `api:claude-fable-5` (apex, cost 3). `WEIGHTS = {"capability": 1.0, "cost": 0.25, "speed": 0.2, "quota": 0.6, "tier": 0.15}` (:120).

```python
# calipso/capabilities.py:199-235 (parse_directives, cabeza)
def parse_directives(message: str) -> dict:
    out = {"clean": message, "effort": None, "force_model": None,
           "force_route": None, "help": False, "force_web": False,
           "force_team": False, "nube": False, "redacta": False, "otra": False,
           "mia": False}
    low = message.lower()
    tokens = message.split()
    keep = []
    for t in tokens:
        tl = t.lower()
        if tl in ("/help", "/?"):
            out["help"] = True
        elif tl == "/web":
            out["force_web"] = True
        elif tl in ("/plan", "/team", "/equipo"):
            out["force_team"] = True
        elif tl == "/nube":
            out["nube"] = True
        elif tl == "/redacta":
            out["redacta"] = True
        elif tl == "/otra":
            out["otra"] = True
        elif tl == "/mia":
            out["mia"] = True
        elif tl in ("/fast",):
            out["effort"] = EFFORT["fast"]
        elif tl in ("/think",):
            out["effort"] = EFFORT["think"]
        elif tl in ("/ultrathink", "/ultra"):
            out["effort"] = EFFORT["ultra"]
        elif tl in ("/local", "/claude", "/codex", "/api"):
            out["force_route"] = "subscription" if tl in ("/claude", "/codex") else tl[1:]
            if tl in ("/claude", "/codex"):
                out["force_model"] = tl[1:]  # marcador de cliente
        elif tl == "/model":
            keep.append(t)
        else:
            keep.append(t)
```

```python
# calipso/capabilities.py:236-256
    if "/model" in [t.lower() for t in tokens]:
        idx = [t.lower() for t in tokens].index("/model")
        if idx + 1 < len(tokens):
            out["force_model"] = tokens[idx + 1]
            keep = [t for i, t in enumerate(tokens)
                    if i not in (idx, idx + 1) and not t.startswith("/")]
    else:
        keep = [t for t in keep if not t.startswith("/")]
    if out["effort"] is None:
        if any(w in low for w in _ULTRA_WORDS):
            out["effort"] = EFFORT["ultra"]
        elif any(w in low for w in _THINK_WORDS):
            out["effort"] = EFFORT["think"]
        elif any(w in low for w in _FAST_WORDS):
            out["effort"] = EFFORT["fast"]
    out["clean"] = " ".join(keep).strip() or message
    return out
```

La linea :244 (`keep = [t for t in keep if not t.startswith("/")]`) borra `/goal` Y toda ruta absoluta del texto; :255 (`or message`) devuelve el mensaje crudo si `keep` queda vacio. Para `/goal`: detectar el prefijo sobre `message` crudo (`message.split(None, 1)`) y guardar `out["goal_texto"]` = resto literal ANTES del bucle; `clean` sigue para el ruteo.

```python
# calipso/capabilities.py:260-283
def score_model(features: dict, effort: int, m: dict,
                available: bool, quota_low: bool = False) -> float | None:
    if not available:
        return None
    if features.get("private") and not m.get("private_ok"):
        return None
    if m.get("max_complexity", 5) < features.get("complexity", 2):
        return None
    if TIER_RANK.get(m.get("tier", "mid"), 1) < EFFORT_MIN_TIER[effort]:
        return None  # no alcanza la intensidad pedida
    cap = m.get("strengths", {}).get(features.get("type", "reasoning"), 0.4)
    cap *= 1.0 if cap >= 0.6 else 0.7
    score = (
        WEIGHTS["capability"] * cap
        - WEIGHTS["cost"] * m.get("cost", 1)
        + WEIGHTS["speed"] * m.get("speed", 0.5)
        - (WEIGHTS["quota"] if quota_low else 0.0)
    )
    if effort == 0:
        score -= WEIGHTS["tier"] * TIER_RANK.get(m.get("tier", "mid"), 1)
    return round(score, 4)
```

`choose(features, effort, available, quota_low=None, project_root=None)` (:286-304): `load_backends(project_root)`, rankea `{key, route, client, model, persona, tier, score}` desc. Con `effort=3` (`EFFORT_MIN_TIER[3] == 2`) quedan solo frontier/apex: opus, codex, fable-api. `features.private` fuerza `private_ok` (solo los locales). `test_capabilities.py:49-76`: es un script con `check(...)` por directiva (`/ultrathink`, `/model`, `/nube`, `/redacta`, `/otra`, `/mia`): agregar los de `/goal` con el mismo patron.

### C.7 `dispatch.py`

```python
# dispatch.py:119-121
PRIVATE = re.compile(
    r"\b(privado|confidencial|secreto|contraseñas?|password|personales?|sensible|"
    r"no comparta|no compartas)\b", re.IGNORECASE)
```

`REPO` (:122-124: repo|repositorio|pull request|build|compila|migra|despliega|deploy|stack trace), `WRITING`, `TRANSLATE`, `SUMMARIZE`, `AGENTIC` (ejecuta|corre los tests|automatiza|agente|herramienta|run), `CODE_HEAVY`, `TRIVIAL`, `CHEAP_REASONING`, `WEB`.

```python
# dispatch.py:164-193
def extract_features(prompt: str) -> dict:
    p = prompt.strip()
    feat = {"type": None, "complexity": 2,
            "private": bool(PRIVATE.search(p)), "needs_repo": False,
            "needs_web": bool(WEB.search(p)) or bool(re.search(r"https?://", p))}
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
    return feat
```

`dispatch.CONFIG` (:61) = `dispatch_config()` evaluado al importar; `CONFIG["subscription"]["codex"] = ["codex", "exec", "--output-last-message", "{output}", "{prompt}"]` (normalizado en `config.py:94-103`).

### C.8 `calipso/permisos/` (acciones.py, motor.py, almacen.py)

Docstring de enchufe (motor.py:15-25): "1. armar una `Accion` con su familia, su operacion y su FORMA exacta; 2. llamar a `evaluar(accion, contexto)`; 3. si vuelve permitido, hacerlo; si vuelve pendiente o estacionada, NO hacerlo y devolverle a quien pidio el id de la solicitud; 4. registrar con `registrar_ejecutor(familia, operacion, fn)` como se ejecuta esa accion". `_EJECUTORES` se usa en `ejecutar` (:225-244); el server registra `plata/movimiento`, `plata/acunar` (:7217-7219) y `plata/capacidad` (:7691). Import en server: `from calipso import permisos as _permisos` (:7074) con `_permisos_almacen`/`_permisos_motor` (:7078 los pone en None si falla).

```python
# calipso/permisos/acciones.py:37-47
NIVEL_DIRECTO = "directo"
NIVEL_PREGUNTA = "pregunta"
NIVEL_NUNCA = "nunca"
ORIGENES_ATENDIDOS = ("chat", "pedro")
```

```python
# calipso/permisos/acciones.py:59-96 (Accion)
@dataclass(frozen=True)
class Accion:
    familia: str
    operacion: str
    forma: dict = field(default_factory=dict)
    detalle: dict = field(default_factory=dict)
    titulo: str = ""

    def clave(self) -> str:
        return json.dumps([self.familia, self.operacion, self.forma],
                          ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"))

    def a_dict(self) -> dict: ...
    @staticmethod
    def de_dict(d: dict) -> "Accion": ...
```

```python
# calipso/permisos/acciones.py:98-122 (Contexto)
@dataclass(frozen=True)
class Contexto:
    origen: str = "desconocido"
    chat: str | None = None
    departamento: str | None = None
    corrida: str | None = None

    @property
    def desatendido(self) -> bool:
        return self.origen not in ORIGENES_ATENDIDOS

    def a_dict(self) -> dict:
        return {"origen": self.origen, "chat": self.chat,
                "departamento": self.departamento, "corrida": self.corrida}
```

`Veredicto(nivel, motivo, siempre_pregunta=False)` (:125-129). `calipso_home()` (:140-160) resuelve `CALIPSO_HOME` en cada llamada.

```python
# calipso/permisos/acciones.py:176-183 (la lista de denyRead ya existe aca)
NOMBRES_CREDENCIAL_DEL_SERVIDOR = ("token", "totp_secret", "sesiones.json")
CARPETAS_CREDENCIAL = ("~/.ssh", "~/.gnupg", "~/.aws", "~/.config/gh")
ARCHIVOS_CREDENCIAL = ("~/.claude/.credentials.json",)
SUFIJOS_CREDENCIAL = (".pem", ".key", ".p12")
NOMBRES_CREDENCIAL = (".env",)
PREFIJOS_CREDENCIAL = ("id_",)
```

`es_credencial_del_servidor` (:200-209: `~/.calipso/{token,totp_secret,sesiones.json}` y todo `backups/`), `es_credencial_de_pedro` (:212-223), `raices_de_escritura()` (:226-242: `~/.calipso` + `catastro.raices_resueltas()`), `es_irreversible(argv)` (:306-341: git push/clean, commit --amend, reset --hard, rm -rf), `_clasificar_comando` (:344-367: `allowlist` por id -> directo; `correr` argv -> pregunta, irreversible -> pregunta siempre), `_clasificar_archivo` (:370-392: NUNCA credencial del servidor; credencial de Pedro -> pregunta siempre; leer -> directo; escribir dentro de raices -> directo; fuera -> pregunta).

```python
# calipso/permisos/acciones.py:407-433
_CLASIFICADORES: dict[str, Callable[[Accion, dict], Veredicto]] = {
    "plata": _clasificar_plata,
    "comando": _clasificar_comando,
    "archivo": _clasificar_archivo,
    "app": _clasificar_app,
}

def familias() -> tuple[str, ...]:
    return tuple(sorted(_CLASIFICADORES))

def registrar_clasificador(
        familia: str, fn: Callable[[Accion, dict], Veredicto]) -> None:
    _CLASIFICADORES[familia] = fn

def clasificar(a: Accion, techos: dict | None = None) -> Veredicto:
    techos = {**TECHOS_DEFECTO, **(techos or {})}
    fn = _CLASIFICADORES.get(a.familia)
    if fn is None:
        return Veredicto(NIVEL_PREGUNTA,
                         f"familia desconocida: {a.familia!r}")
    return fn(a, techos)
```

El clasificador NO recibe `Contexto`: la politica del goal (tabla + raices) tiene que leerse de otro lado (el `goal.json` por `forma["goal"]`/`detalle`, o un registro por goal en memoria del proceso). `cubre(permiso, accion)` (:474-486) compara familia+operacion+forma; `registrar_cobertura(familia, fn)` (:468-470) para subsuncion (la de `archivo` usa `raiz`, :448-459).

```python
# calipso/permisos/motor.py:110-135 (evaluar: orden de cortes) y 227-250 (desatendido)
def evaluar(a: Accion, ctx: Contexto | None = None) -> Resolucion:
    ctx = ctx or Contexto()
    try:
        pared = almacen.por_corrida(ctx.corrida)
        if pared is not None:
            almacen.anotar_intento(pared["id"], a, ctx, "rodeo de corrida")
            return _anotar(a, ctx, Resolucion(ESTADO_ESTACIONADA, "la corrida ya quedo estacionada ...", solicitud=pared))
        abierta = almacen.por_forma(a.clave())
        if abierta is not None: ... return ESTADO_PENDIENTE|ESTADO_ESTACIONADA
        for s in almacen.solicitudes():
            if s.get("clave") == a.clave() and s.get("estado") == almacen.ESTADO_APROBADA:
                tomada = almacen.tomar_para_ejecutar(s["id"])
                if tomada is not None:
                    return _anotar(a, ctx, Resolucion(ESTADO_PERMITIDO, f"Pedro ya la aprobo ({s['id']})", ...))
        regla = almacen.regla_que_cubre(a, "denegar")
        if regla is not None: return ESTADO_NEGADO
        v = clasificar(a, almacen.techos())
        if v.nivel == NIVEL_NUNCA: return ESTADO_NEGADO (sin solicitud)
        if v.nivel == NIVEL_DIRECTO: return ESTADO_PERMITIDO
        if not v.siempre_pregunta:
            permiso = almacen.cubierta_por_permiso(a)
            if permiso is not None: return ESTADO_PERMITIDO
        texto = texto_del_prompt(a, v)
        if ctx.desatendido:
            if not v.siempre_pregunta:
                pre = almacen.cubierta_por_preautorizacion(a, ctx.departamento)
                if pre is not None: return ESTADO_PERMITIDO ("pre-autorizada por el departamento")
            s = almacen.crear(a, ctx, almacen.ESTADO_ESTACIONADA, v.nivel, v.motivo, v.siempre_pregunta, texto)
            return _anotar(a, ctx, Resolucion(ESTADO_ESTACIONADA, "no hay a quien preguntarle: queda esperando en /fabrica (5.6.2)", nivel=v.nivel, solicitud=s))
        s = almacen.crear(a, ctx, almacen.ESTADO_PENDIENTE, ...)
        return _anotar(a, ctx, Resolucion(ESTADO_PENDIENTE, "esperando la respuesta de Pedro", ...))
    except ErrorPermisos as exc:
        return _anotar(a, ctx, Resolucion(ESTADO_NEGADO, f"el motor de permisos no puede decidir: {exc}"))
```

`Resolucion(estado, motivo, nivel, solicitud, permiso)` con `.permitido` (:50-63). `_anotar` (:96-107) escribe `registro.jsonl` en cada evaluacion. Estados: `ESTADO_PERMITIDO/PENDIENTE/ESTACIONADA/NEGADO` (:44-47).

`responder(id_solicitud, respuesta, quien="pedro", forma_permanente=None)` (:270-333): `respuesta in ("si","si_siempre","no","no_siempre")`; `si` sobre una ESTACIONADA NO ejecuta (:280-283): la corrida siguiente vuelve a pedir la MISMA forma y `evaluar` la consume (corte 3). `aprobadas_para(departamento)` (:336-346) lista las aprobadas sin llamador hoy. `por_corrida` (almacen.py:401-412): "La marca no se levanta cuando Pedro aprueba: la corrida ya termino, y la rutina retoma en la PROXIMA, con un id nuevo" -> `corrida = f"{goal_id}:{n_golpe}"`.

```python
# calipso/permisos/almacen.py:419-441 (crear: idempotente por forma)
def crear(a: Accion, ctx: Contexto, estado: str, nivel: str, motivo: str,
          siempre_pregunta: bool, texto: str) -> dict:
    if estado not in ESTADOS_ABIERTOS:
        raise ErrorPermisos(f"una solicitud nace abierta: {estado!r}")
    with candado(ruta_solicitudes()):
        d = _leer_solicitudes()
        clave = a.clave()
        for s in d["solicitudes"]:
            if s.get("clave") == clave and s.get("estado") in ESTADOS_ABIERTOS:
                return dict(s)
        s = {"id": _id("sol"), "ts": _ahora(), "estado": estado,
             "clave": clave, "accion": a.a_dict(), "contexto": ctx.a_dict(),
             "nivel": nivel, "motivo": motivo,
             "siempre_pregunta": bool(siempre_pregunta), "texto": texto,
             "estaciono_corrida": bool(estado == ESTADO_ESTACIONADA
                                       and ctx.corrida),
             "intentos": [], "respondida": None, "resultado": None}
        d["solicitudes"].append(s)
        _escribir(d)
        return dict(s)
```

Archivos (almacen.py:1-44): `~/.calipso/permisos.json` (config), `~/.calipso/permisos/solicitudes.json` (estado, bajo `candado` = flock + RLock), `~/.calipso/permisos/registro.jsonl`. `PREAUTORIZADO_DEFECTO` (:90-96): git_status/git_diff/git_diff_staged/git_log/test_all del allowlist; `preautorizados(departamento)` (:187-195) desde `permisos.json["preautorizados"]`.

Inbox: `descriptor()` (motor.py:378-410; `ORIGEN_INBOX = "permisos"` :375) devuelve `{"origen": ORIGEN_INBOX, "verbos": [{nombre, etiqueta, alcances, parametros}...], "reloj", "clase_por_defecto": "decision", "vara", "lugares"}`; `como_items(datos_endpoint)` (:413-467) exige `activo`, y por cada `pendientes + estacionadas` arma `{"id", "origen", "clase": "decision", "ts", "titulo": s["texto"], "cuerpo": {"accion", "contexto", "motivo", "verbos_validos"}, "estado", "respuesta": None}`; con `siempre_pregunta` saca `si_siempre`. Endpoint de respuesta: `POST /api/permisos/solicitudes/{id}/responder` (body `respuesta`, `forma` opcional; server.py:7222-7275 segun el informe de economia). `_permisos_contexto(body)` (server.py:7097-7113): `Contexto(origen=body.origen or "pedro", chat, departamento, corrida)`; `_permisos_puerta(accion, body)` (:7116-7141): 403 si negado, 409 con el id si pendiente/estacionada.

### C.9 `calipso/aduana.py`

```python
# calipso/aduana.py:55-57
ORIGENES = ("turno", "gesto", "rutina", "jefe", "arranque", "ui")
RUTAS = ("local", "subscription", "api", "orchestrator")
CREDENCIALES = ("maquina", "sesion")
```

`Quien` (:88-120): dataclass `frozen, kw_only` con `origen, proyecto, desde` obligatorios y `chat, gesto, ruta, rutina, departamento, endpoint` opcionales; `__post_init__` levanta `ValueError` con origen fuera de `ORIGENES` (:105-106), `proyecto` vacio, `desde.credencial` fuera de `CREDENCIALES`, `ruta` fuera de `RUTAS`, `rutina` sin `kind`+`id` (:114-117). NO tiene campo `goal`: sumar `"goal"` a `ORIGENES` (y al spec de la aduana `2026-09-10-aduana-design.md:93` y a `test_aduana.py`) y llevar el id en `rutina={"kind": "goal", "id": goal_id}`.

`_ruta()` (:145-148) = `calipso_home() / "aduana.jsonl"` resuelto por llamada. `_anotar` (:257-273): si `_en_el_loop()` cuenta hueco `aduana_en_loop` y NO escribe -> `cruzar` siempre en hilo. `_tapar_todo` (:283-288) usa `detector.detectar_secretos`. `_destino(None)` -> `{"host": None, "url": None}` (:351-361). `_carga` (:388-413): `list` -> consulta con cada token por `_texto_de_sitio`; `Cuerpo(texto)` -> `{tipo: cuerpo, tamano, sha256[:12], lineas}` (3 lineas tapadas); `str` -> detector completo; tope `CONSULTA_MAX = 500`. `cruzar(quien, proposito, destino, carga=None)` es contextmanager que anota `ok|fallo` con `ms` y `bytes` (`cruce.entro(n)`); `declarar(quien, proposito, destino, motivo)`; `declarar_una_vez(clave, ...)` (:418-474). `PROPOSITO_MAX = 120` (:85).

Molde de cruce alrededor de un subprocess (server.py:5280-5296, en hilo):

```python
    with aduana.cruzar(quien, "npm install -g", destino="registry.npmjs.org",
                       carga=cmd[-1]) as cruce:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        cruce.entro(len(result.stdout or "") + len(result.stderr or ""))
```

Para un Popen sondeado desde el loop el `with cruzar` no puede envolver el `await`: abrir el cruce en un hilo al lanzar (o `declarar` al lanzar y `cruzar` corto al terminar) y anotar en `EXCEPCIONES` del canario el sitio del Popen con motivo `modelo:` si no lleva el Call (C.15).

### C.10 `calipso/privacidad/detector.py`

```python
# calipso/privacidad/detector.py:14-31 (las regex)
_PREFIJOS = re.compile(
    r"\b(sk-[a-z]+-|sk_live_|rk_live_|ghp_|gho_|ghs_|github_pat_|AKIA|ASIA|"
    r"AIza|xox[baprs]-|glpat-|npm_)[A-Za-z0-9_\-/]{6,}")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]{6,}")
_PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[^\n]*")
_CONN = re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s:@/]+:[^\s:@/]+@[^\s]+")
_HEX = re.compile(r"\b[0-9a-fA-F]{32,}\b")
_BASE32 = re.compile(r"\b[A-Z2-7]{16,}\b")
_TOKEN = re.compile(r"[A-Za-z0-9_\-/+.=]{20,}")
```

```python
# calipso/privacidad/detector.py:41-74
def detectar_secretos(texto: str) -> list[dict]:
    """Todos los tramos de `texto` que parecen un secreto de maquina. Cada uno
    `{"texto": <literal>, "tipo": "credencial"}`. Puede haber varios."""
    ...
    for rx in (_PREFIJOS, _JWT, _PEM, _CONN): agregar(m.group(0))
    for m in _HEX.finditer(texto): agregar(m.group(0))
    for m in _BASE32.finditer(texto):
        if re.search(r"[2-7]", m.group(0)): agregar(m.group(0))
    for tok in _TOKEN.findall(texto):
        if "@" in tok: continue
        clases = (...minusculas + mayusculas + digitos...)
        if _entropia(tok) >= 4.2 and clases >= 2: agregar(tok)
    return tramos
```

Devuelve tramos literales; el reemplazo lo hace el llamador (molde `aduana._tapar_todo`: ordenar por longitud desc y `replace` por `SECRETO`). OJO: `_HEX` marca cualquier SHA de git de 40 chars y `_TOKEN` cualquier base64 largo (un `session_id` uuid NO cae: tiene guiones y menos entropia? un uuid4 sin guiones SI cae en `_HEX`): al tapar el ledger, excluir explicitamente los `session_id`/`request_id`/shas del diff_stat o aceptar el falso positivo.

### C.11 `calipso/economia/pagador.py`

```python
# calipso/economia/pagador.py:28-36
PRECIOS_API_MM_POR_MTOK = {"deepseek-chat": (270, 1100)}
PRECIO_DESCONOCIDO = (3000, 15000)  # conservador
SUSCRIPCION_POR_CLIENTE = {"claude": "claude_max", "codex": "chatgpt_plus"}

def suscripcion_de_cliente(cliente: str | None) -> str:
    return SUSCRIPCION_POR_CLIENTE.get((cliente or "").strip().lower(), "claude_max")
```

```python
# calipso/economia/pagador.py:59-67, 150-175
    @staticmethod
    def desde_entorno(base: pathlib.Path | None = None) -> "Pagador | None":
        raiz = pathlib.Path(base) if base else pathlib.Path(
            os.environ.get("CALIPSO_HOME", os.path.expanduser("~/.calipso")))
        p = Pagador(raiz / "economia")
        if not (p.ruta_libro.exists() and p.ruta_registro.exists()
                and p.ruta_sus.exists()):
            return None
        return p

    def _cobrar(self, cargo: dict) -> None:
        with candado(self.ruta_libro):
            try:
                self._aplicar(cargo)
            except _ERRORES_ECONOMICOS:
                self._apilar_pendiente(cargo)

    def cargar_api(self, ts, semana, cuenta, modelo, prompt_tokens, completion_tokens) -> int | None:
        if cuenta == "personal" or cuenta.startswith("personal:"):
            return None
        pin, pout = PRECIOS_API_MM_POR_MTOK.get(modelo, PRECIO_DESCONOCIDO)
        mm = -(-(prompt_tokens * pin + completion_tokens * pout) // 1_000_000)
        if mm <= 0:
            return 0
        self._cobrar({"ts": ts, "semana": semana, "tipo": "api",
                      "cuenta": cuenta, "mm": mm, "modelo": modelo})
        return mm

    def cargar_suscripcion(self, ts: str, semana: str, cuenta: str,
                           suscripcion: str, unidades: int = 1) -> None:
        self._cobrar({"ts": ts, "semana": semana, "tipo": "suscripcion",
                      "cuenta": cuenta, "suscripcion": suscripcion,
                      "unidades": unidades})
```

`_aplicar` (:126-148): `api` -> `mercado.gastar_api(...)`; `cuenta == "personal"` -> `usar_reserva_personal`; otra -> `consumir_capacidad(ts, semana, cuenta, suscripcion, unidades, dueno=dueno)` SIN `ref` (el mercado lo acepta: `mercado.py:97-100`). Para el concepto `goal:<id>` hay que sumar `ref` a `cargar_suscripcion` y a `_aplicar` (o poner `goal:<id>` en el cargo y pasarlo). `unidades` ya es parametro: la fila del ledger lleva `len(usage.iterations)`.

### C.12 `calipso/github.py`

```python
# calipso/github.py:66-91
def env_git_blindado(anular_global: bool = True) -> dict:
    env = os.environ.copy()
    if anular_global:
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        env["GIT_CONFIG_SYSTEM"] = os.devnull
    for i, (k, v) in enumerate((("core.fsmonitor", ""),
                                ("diff.external", ""),
                                ("core.pager", "cat"))):
        env[f"GIT_CONFIG_KEY_{i}"] = k
        env[f"GIT_CONFIG_VALUE_{i}"] = v
    env["GIT_CONFIG_COUNT"] = "3"
    return env
```

```python
# calipso/github.py:186-217
def git_runner(cwd: str | None = None, timeout: int = 10,
               *, quien: aduana.Quien) -> Runner:
    exe = shutil.which("git.exe") or shutil.which("git")
    env = env_git_blindado()

    def run(args: list[str]) -> tuple[int, str, str]:
        if not exe:
            return (127, "", "git no esta en PATH")
        red = subcomando_git_de_red(args)
        if red:
            cruce = aduana.cruzar(quien, f"git {red}", destino=_destino_git(args),
                                  carga=["git", *args])
        else:
            cruce = contextlib.nullcontext()
        try:
            with cruce as c:
                proc = subprocess.run(
                    [exe, *args], cwd=cwd, env=env, text=True,
                    capture_output=True,
                    encoding="utf-8", errors="replace", timeout=timeout)
                if c is not None:
                    c.entro(len(proc.stdout or "") + len(proc.stderr or ""))
            return (proc.returncode, proc.stdout or "", proc.stderr or "")
        except Exception as e:  # pragma: no cover
            return (1, "", str(e))

    return run
```

`Runner = Callable[[list[str]], tuple[int, str, str]]` (:30). `GIT_DE_RED` (:41-44) incluye `clone`, `fetch`, `push`, `pull`, `ls-remote`, `submodule`...; `subcomando_git_de_red(args)` (:156-170); `_partir_git` (:125-143) salta `-C dir`, `-c k=v`, `--git-dir X`. `default_runner` (:94-122) es de `gh` y SIEMPRE cruza con `destino="api.github.com"`. `git_runner` anula el gitconfig global (sin identidad: un `git commit` por ahi falla); el clon local con `git clone <ruta> <destino>` (usa hardlinks automaticos entre repos del mismo filesystem) y `git checkout -b goal/<id>` no son de red (`clone` SI esta en `GIT_DE_RED`: un clon LOCAL cruzaria la aduana con `destino=None`; pasar `--no-hardlinks`? no: el hardlink es lo que lo hace barato; aceptar el cruce o usar un runner propio con `env_git_blindado(anular_global=False)` y `subprocess.run` + `EXCEPCIONES` motivo `git local:`). `timeout` default 10 s: un clon de un repo grande necesita mas (pasar `timeout=120`).

### C.13 `calipso/carga.py`

```python
# calipso/carga.py:363-365 (firma) y 450-454
def medir(modelo: str | None = None, *, leer=None, ps=None, ncpu: int | None = None,
          necesidad: int | None = None, ahora: datetime.datetime | None = None,
          modelos_propios=None, ps_timeout: float | None = None) -> Carga:

def nivel_reciente() -> str:
    return _ultima.nivel if _ultima is not None else "holgada"
```

`Carga.nivel` in `("holgada", "justa", "cargada")` (`NIVELES`, :82); `medir` cachea `CACHE_S` por proceso (:383-385); `carga.fila(c)` = `dataclasses.asdict`; `olvidar()` (:457-463) para fixtures. El server mide con `_medir_carga(ps_timeout=None)` (server.py:2486-2494) en HILO. `tomar/soltar/usando()` (:561-585) y `Uso` (:588-605) solo importan para el modelo local (el goal no lo usa salvo cabeza privada). `_tick_con_carga` (server.py:5895-5921) es el molde de "posponer": `telemetry.log_event("carga", accion="pospone", rutina=<kind>, rutina_id=<id>, **carga.fila(medida))`; `cuentas_del_dia` (carga.py:706-721) cuenta `pospone` por `rutina_id` distintos: usar `rutina_id=goal_id`.

### C.14 `calipso/consumo.py` (la cuota, pasiva)

Docstring (:1-60): Claude escribe `~/.claude/projects/<proyecto>/<sesion>.jsonl` con `message.usage` y "NINGUN porcentaje de cuota" (desmentido por la sonda para el stream-json: A.5); Codex escribe `~/.codex/sessions/<anio>/<mes>/<dia>/rollout-*.jsonl` con `event_msg/token_count` y `rate_limits.primary.used_percent` (ventana 300 min), `secondary.used_percent` (10080 min), `resets_at` (epoch), `plan_type`. `_extraer_codex` (:258-299) devuelve `{ts, id, input_tokens, ..., primary_used_percent, primary_window_minutos, primary_resets_at, secondary_used_percent, secondary_window_minutos, secondary_resets_at, plan_type}`. `resumen()` (:549-557) escribe `~/.calipso/consumo_resumen.json` y devuelve `{"generado", "claude": {"medicion": {turnos_observados, tokens, desde, hasta}, "inferencia": {...}}, "codex": {"medicion": {"plan_type", "ventana_primaria_5h": {"used_percent", "window_minutos", "resets_at", "turnos_en_la_ventana", "capacidad_ventana_inferida"}, "ventana_secundaria_semanal": {...}}, "inferencia": {...}}}`; `cargar_resumen()` (:577) lo lee sin escanear. Para el paso 1 del bucle: `consumo.cargar_resumen()["codex"]["medicion"]["ventana_primaria_5h"]["used_percent"] > 90` -> `waiting cuota`; para Claude, el `rate_limit_event` del ULTIMO golpe (guardarlo en `golpes.jsonl`: `utilization` de `five_hour` y `seven_day`).

### C.15 `sesiones.ALCANCES`, fabrica, PWA, tests

```python
# calipso/sesiones.py:81-98
ALCANCES: dict[str, tuple] = {
    "navegador": (("*", "*"),),
    "lector": (("/api/lectura/", "*"),),
    "tablero": (
        ("/fabrica", ("GET",)),
        ("/static/", ("GET",)),
        ("/ws/mapa", ("GET",)),
        ("/api/mapa/", ("GET",)),
        ("/api/economia/", ("GET",)),
        ("/api/permisos", ("GET",)),
        ("/api/inbox", ("GET",)),
        ("/api/plantel", ("GET",)),
        ("/api/routines", ("GET",)),
        ("/api/aduana", ("GET",)),
        ("/api/carga", ("GET",)),
        ("/api/economia/bus/", ("POST",)),          # LA MESA
        ("/api/permisos/solicitudes/", ("POST",)),  # firmar solicitudes
    ),
}
```

`test_sesiones.py:381-405` (parametrize "el tablero ve toda la fabrica", test en :405: pares `(path, "GET")`), `:408-417` (POSTs permitidos, test en :417), `:420-460` (negados; `/api/routines` POST/PUT/DELETE, `/api/routines/abc/run` POST negados). Sumar `("/api/goals", ("GET",))` y sus filas.

Fabrica: `sw.js:1` `CACHE = "calipso-shell-v7"`, `SHELL` :2-31 (ultimo `/static/fabrica/carga.js`); `test_mapa_server.py:126-147` exige todo `.js` no-test y `.css` de `fabrica/` en el SHELL. `aduana.js:1` `import {escapar} from "./paneles.js"`; modulo puro (:1-8). `app.js:29` import; `pintarBadge(badge, n)` :506-511; `pintarAduana` :812-835 (fetch `/api/aduana` + `/api/carga`, 401/403 -> "Solo desde la Ally, un navegador o un tablero."); submesa :849-870 (`cajaX?.classList.toggle("oculto", vista !== "x")` :861, `if (vista === "aduana") pintarAduana()` :869); intervalos de 60 s :1396-1412 (`setInterval(pintarAparatos, 60_000).unref?.()`). `fabrica/index.html:56-73`: botones `data-vista` en `#submesa` y cajas `<div id="x" class="x-panel oculto">`. `chat.js:47-48`: `EVENTOS_DEL_STREAM = new Set(["chunk","done","meta","cost","chat","error","abismo","canario","carga"])`. `test_fabrica_js.py:70-94`: `node --test` con `cwd=FABRICA`, `# fail 0`, `# pass >= PISO_DE_TESTS`. `arranque.test.js:143-151` monta un DOM sin `goals`: `if (!caja) return` y `caja?.addEventListener`.

PWA `index.html`: CSS `#goalBar` :64-75 (`display:none`; `.active` -> flex); HTML :360-375 (seis botones `goalAdvance/goalVerify/goalEvidence/goalBlock/goalComplete/goalCancel` + `goalOpen`); `renderGoal(goal)` :1993-2009 (lee `criteria`, `subtasks`, pinta `goalTitle/goalState/goalProgress/goalNext`); `loadGoal()` :2152-2157 (`GET /api/goals?limit=8` -> `renderGoal(data.active)`), llamada al cargar :2630; **:2159-2164 asigna `document.getElementById("goalAdvance").onclick = ...` sin guarda: quitar un boton del HTML revienta el script entero de la PWA**; rama `m.type === "goal"` :2345-2362 (`active` -> `addMsg("meta", ...)`, `auto_closed` -> tarjeta). `test_ui.py` no menciona `goal` (grep vacio).

Tests del chat:

```python
# test_abismo_chat.py:84-98
def _decide_local(user_msg, last_features=None, last_verdict=None):
    d = srv.capabilities.parse_directives(user_msg)
    route = d.get("force_route") or "local"
    client = d.get("force_model") if route == "subscription" else None
    verdict = {"route": route, "client": client, "model": "modelo-falso",
               "model_id": f"{route}:modelo-falso", "persona": "Epicteto",
               "tier": "small", "effort": 1, "effort_name": "balanced",
               "session": "s", "source": "harness", "why": "harness"}
    features = {"type": "chat", "complexity": 1, "needs_repo": False,
                "needs_web": False, "private": False}
    verdict.update(VEREDICTO_EXTRA)
    return verdict, features, [], d
```

`Harness` (:135-208): `turno(texto, departamento=None, hasta_dones=1)` (:150-164) abre `/ws/chat`, `recibir` hasta N `done` (plazo 60 s), `lo_que_siga` 0.25 s, `esperar_fondo()` (:166-183: revienta a los 5 s si queda una tarea viva en `srv._TAREAS_DE_FONDO`); `mensajes()`, `telemetria(kind)`; `de_tipo(eventos, tipo)` :225; `texto_visible` :229. Fixture `chat` (:234-266): parchea `chats.CHAT_FILE`, `telemetry.LEDGER`, `_ECO_BASE`, `mem`, `EL_PULSO`, `_http_up`, `_decide`, `_build_context`, `_harness_context`, `_extract_edit_target`, `tokenizador.cargar`, `catastro.obtener`, **`goals.active -> None` y `goals.detect -> None` (:260-261)**, `dispatch._ollama_chat_chunks`; `TestClient(srv.app, cookies={srv.COOKIE: srv.TOKEN})`.

```python
# test_abismo_suscripcion.py:21-63 (cli_falso, recortado)
@pytest.fixture
def cli_falso(tmp_path, monkeypatch):
    carpeta = tmp_path / "cli"
    carpeta.mkdir()
    script = carpeta / "claude_falso.py"
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''
        import json, pathlib, sys, time
        base = pathlib.Path(__file__).parent
        n = len(list(base.glob("llamada-*.json")))
        args = sys.argv[1:]
        sistema = ""
        if "--append-system-prompt-file" in args:
            ruta = args[args.index("--append-system-prompt-file") + 1]
            sistema = pathlib.Path(ruta).read_text(encoding="utf-8")
        prompt = args[args.index("-p") + 1] if "-p" in args else ""
        (base / f"llamada-{n}.json").write_text(
            json.dumps({"sistema": sistema, "prompt": prompt}), encoding="utf-8")
        guion = json.loads((base / "guion.json").read_text(encoding="utf-8"))
        paso = guion[min(n, len(guion) - 1)]
        for parte in paso["partes"]:
            sys.stdout.write(parte)
            sys.stdout.flush()
            time.sleep(paso.get("pausa", 0))
        if paso.get("stderr"):
            sys.stderr.write(paso["stderr"])
        sys.exit(paso.get("exit", 0))
    '''), encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr(srv, "_subscription_command", lambda c: str(script))

    class CLI:
        def guion(self, pasos): ...
        def llamadas(self): ...
    return CLI()
```

Para el golpe: extender a leer `sys.stdin.read()` (el prompt va por stdin, no `-p`), `os.getcwd()`, `sys.argv` entero, el JSON de `--settings` y `--json-schema`, y escribir stream-json por linea (`system/init`, `assistant` con `tool_use`, `system/hook_started|hook_response`, `user` con `tool_result`, `result` con `usage.iterations`, `structured_output`, `permission_denials`). Y un `codex` falso que respete `-o <archivo>` y `--json`.

`test_aduana_api.py:248-254`: `assert "proyecto=ROOT.name" not in fuente` y `fuente.count("proyecto=_proyecto()") >= 5` sobre `server.py`: pasar `proyecto=goal["proyecto_nombre"]` no lo rompe.

`test_aduana_canario.py:33-66` `EXCEPCIONES` (`"archivo:funcion": "motivo"`; `_run_subscription_text` y `_run_subscription_text_live` exentos como `modelo:`; `calipso/catastro.py:_git` y `calipso/server.py:_git` como `git local:`); `_SUBPROCESS = {"run","Popen","check_output","check_call","call"}` (:69); barre `calipso/**/*.py` sin `/web/` mas `dispatch.py` y `launch_calipso.py`; una excepcion huerfana o sobre un sitio que ya cruza es rojo; ningun motivo puede empezar por `pendiente`. Sitios nuevos que va a marcar: el `Popen` de `goals_manos.py`, el `subprocess.run` de la sonda del hook, el `git clone/diff` del clon si no va por `git_runner`, y `systemd-run` (que ES el `Popen`).

`conftest.py:46-55`: `os.environ["CALIPSO_HOME"] = mkdtemp("calipso_suite_home_")` y `os.environ["CALIPSO_EMBED_FALSA"] = "1"` antes de cualquier import; los subprocesos de la suite (el `cli_falso`, el hook real) HEREDAN `CALIPSO_HOME` del entorno.

Otros moldes: `jobs.start(kind, title, project_root=None, **data)` (jobs.py:45-61) escribe `~/.calipso/projects/<slug>/jobs/<id>/job.json` + `events.jsonl`; `memory.reflect` (memory.py:309-355) = `subprocess.run([exe, "-p", prompt], timeout=120, env=env)` con `aduana.declarar(quien, "reflect", destino="api.anthropic.com", motivo=...)` antes; `telemetry.log_event(kind, **data)` (telemetry.py:14-26) nunca levanta.

---

## Trampas

1. **`--tools ''` no saca los MCP**: la sonda con `--restricted --tools '' --setting-sources ''` igual conecto `claude.ai Google Drive` con 11 herramientas (`mcp__claude_ai_Google_Drive__*`) y las listo en `tools`. Sin `--strict-mcp-config` el martillo puede escribir en el Drive de Pedro. Ademas `StructuredOutput` siempre aparece con `--json-schema`: el parser no debe contar `StructuredOutput` como herramienta "sin hook".
2. **El hook corre entre el `tool_use` y el `tool_result`**, no antes del `tool_use`: el `assistant` con el bloque `tool_use` sale primero, despues `hook_started`/`hook_response` (PreToolUse), despues el `user` con `tool_result`. La sonda del hook por golpe: "todo `tool_result` de Bash/Edit/Write/... tiene un `hook_response` PreToolUse entre su `tool_use` y el". Un `tool_use` cuyo `tool_result` llega sin `hook_response` = hook inactivo.
3. **Cada `assistant` es un bloque, no una llamada**: la misma respuesta (`message.id` `msg_011Cf1oo...`) salio como dos lineas `assistant` (text, tool_use) con el mismo `usage`. Contar unidades por `message.id` distintos o, mejor, por `len(result.usage.iterations)` (y sumar `modelUsage` para el costo informativo: la sonda uso haiku aparte, 900 tokens, que no esta en `iterations`).
4. **`rate_limit_event` existe y trae la cuota de Claude** (`unifiedWindows.five_hour.utilization 0.37`, `seven_day 0.13`, `resetsAt` epoch, `overageStatus: rejected`, `overageDisabledReason: out_of_credits`): el runner no necesita `consumo` para Claude; lo guarda del ultimo golpe. Solo se emite en stream-json; `consumo.py` no lo lee (lee los jsonl de sesion).
5. **`--resume` exige sesion persistida bajo `~/.claude/projects/<slug del cwd>/`**: el slug es el cwd con `/` -> `-` (la sonda: `-tmp-claude-1000--var-home-pedro-...-scratchpad-sonda-vacia`). El golpe N+1 tiene que correr con el MISMO cwd (el clon) o `--resume` no encuentra la sesion. `--no-session-persistence` la impide. Y ese jsonl contiene TODO lo que el martillo leyo: el detector de secretos no lo cubre (esta fuera de `~/.calipso`); `denyRead` de `~/.claude` NO se puede poner (el CLI lo necesita fuera del sandbox; los comandos sandboxeados si podrian tenerlo denegado: `~/.claude` entero en `denyRead` es valido porque el sandbox aplica a los comandos, no al CLI; verificar en el smoke que el CLI sigue autenticando).
6. **`--setting-sources ''` es valido** (`tTr("")` -> `[]`) pero SOLO deja `flagSettings` y `policySettings`; el `model` de `~/.claude/settings.json` deja de aplicar (la sonda corrio `claude-opus-5[1m]`, no el `claude-fable-5-1[1m]` de Pedro): el golpe debe pasar `--model` explicito desde el veredicto.
7. **`sandbox.failIfUnavailable` default false = fail-open**: "a warning is shown and commands run unsandboxed". Ponerla `true` y ademas `strictAllowlist: true`; y `--permission-mode acceptEdits` + `autoAllowBashIfSandboxed: true` para que Bash no pida permiso. Bajo `--restricted`, un hook con `permissionDecision: allow` se ignora (`a confined session takes grants only from its command line`); solo `deny` cuenta.
8. **`WebFetch`/`WebSearch` son in-process**: `strictAllowlist` dice "in-process tools such as WebFetch are not gated by" el sandbox; el filtro de dominios del sandbox NO los cubre. Si el goal declara dominios de web, el hook es la unica capa para `WebFetch(url)` (el `tool_input.url`), o se omiten esas dos tools.
9. **El hook de comando: `args` = forma exec sin shell**, `timeout` en segundos por hook; el default del timeout no se pudo leer (No confirmado); un exit distinto de 0 y 2 = "continue with tool call". El hook debe devolver 2 con el motivo en stderr (lo ve el modelo) en TODO error, incluso al parsear stdin.
10. **`codex` esta en un shim de fnm** (`/run/user/1000/fnm_multishells/<pid>_<ts>/bin/codex`): el PATH del server real (lanzado desde otra shell) puede no tenerlo; `_subscription_command("codex")` devolveria None. `--output-schema` de Codex toma un ARCHIVO (no JSON inline); `--ephemeral` apaga el jsonl de sesion que `consumo` lee para `resets_at`.
11. **El clon local cruza la aduana**: `clone` esta en `GIT_DE_RED` (github.py:41) -> `git_runner` lo cruzaria con `destino=None`; y `git_runner` anula el gitconfig global (sin `user.name`: un `git commit` desde el server falla). Para el clon, un runner propio con `env_git_blindado(anular_global=False)` y timeout > 10 s, y excepcion `git local:` en el canario.
12. **`Quien` no acepta `origen="goal"` ni campo `goal`** (aduana.py:55, :105-106): sumar el origen a la tupla + spec + tests, y el id en `rutina={"kind":"goal","id":...}`. `cruzar` en el loop no escribe (cuenta hueco). `proyecto` viene del goal, no de `_proyecto()`.
13. **El clasificador de permisos no ve el `Contexto`** (`fn(a, techos)`, acciones.py:424-433): la familia `goal` tiene que leer la tabla y las raices desde la `forma`/`detalle` de la `Accion` o desde el `goal.json` por id. Y `crear` es idempotente por forma (almacen.py:428-431): dos goals que pidan la misma forma comparten solicitud.
14. **`por_corrida` no se levanta al aprobar** (almacen.py:401-412): `corrida = f"{goal_id}:{n}"` por golpe; al retomar, re-evaluar la MISMA `Accion` (misma `clave`) para consumir la aprobada (motor.py:158-166).
15. **`_esperar_fondo_al_apagar` no cancela** y `Harness.esperar_fondo` revienta con una tarea viva en `_TAREAS_DE_FONDO`: el runner va en `_GOALS_EN_CURSO` propio; `_shutdown_fondo` tiene que matar el Popen antes de esperar 10 s.
16. **`index.html:2159-2164` asigna `onclick` sin guarda a los seis botones**: para dejar la `#goalBar` de solo lectura hay que quitar TAMBIEN esas seis lineas (y `goalOpen`/`loadGoal` si se tocan), o el script inline de la PWA muere al cargar.
17. **`goals.active()` borra `active.txt` si `load` falla** (goals.py:219-221) y `_write` no es atomico (:192): un lector concurrente puede desactivar el goal; `activo.json` global con escritura atomica y `transicionar` como unica puerta.
18. **`inbox.juntar` tiene firma cerrada de 5 posicionales** y `test_inbox_server.py:140-143` fija `{mesa, permisos, cartas}`: un origen `goals` nuevo cambia la firma y el assert. Alternativa sin tocarla: la pregunta del goal es una solicitud estacionada de familia `goal` (aparece en `permisos`).
19. **`detector._HEX`/`_TOKEN` tapan shas y uuids sin guiones**: al tapar el ledger, no pasar `session_id`, `request_id` ni `diff_stat` por el detector, o guardar los ids fuera del texto tapado.
20. **`dispatch.CONFIG["subscription"]["codex"]` mete `-m` ANTES de `exec`** (server.py:3547-3548): armar el argv de Codex desde cero en `goals_manos.py`.
21. **`parse_directives` borra rutas absolutas** (capabilities.py:244) y `/goal` solo cae al fallback `clean = "/goal"` (:255): capturar `goal_texto` del mensaje crudo antes del bucle.
22. **`sw.js` CACHE v7 -> v8** y `goals.js` en `SHELL`, o `test_mapa_server.py:133-147` falla.
23. **`~/.claude/settings.local.json` tiene 90 reglas `permissions.allow`** (entre ellas `Bash(git *)`, `Bash(gh repo *)`, `Bash(ssh *)`): con `--setting-sources ''`/`--restricted` no entran; sin eso el martillo hereda todo eso.

## No confirmado (para el smoke)

1. Que los `hooks` de `--settings <json inline>` se EJECUTEN en `claude -p` con `--restricted` (el binario los lee: `hasHooks`; la ayuda dice que `--settings` aplica bajo `--restricted`; no se corrio un hook real).
2. El timeout DEFAULT del hook de comando y si un hook vencido bloquea o deja pasar (solo hay "default 60" para el hook de agente).
3. Que el sandbox arranque en esta maquina (`bwrap` 0.12.0 + `socat` presentes; `seccomp` y el proxy no probados) y que `failIfUnavailable: true` no lo mate por una dependencia faltante; que `denyRead` sobre `~/.calipso`, `~/.ssh`, `~/.codex`, `~/.claude` tape un `cat` desde Bash; que `allowWrite` = clon + raices deje escribir ahi y en ningun otro lado; que el CLI siga autenticando con `~/.claude` en `denyRead` (el CLI corre fuera del sandbox).
4. Si con `sandbox.enabled` el `HOME` del comando sandboxeado queda tapado por defecto ("Sandboxed commands lose your home directory ... until you re-open paths with sandbox.filesystem.allowRead"): afecta a `pip`/`npm` que leen `~/.cache`, `~/.npmrc`.
5. Que `--permission-mode acceptEdits` + `--permission-prompts none` + `autoAllowBashIfSandboxed` dejen correr Bash sin denegar todo (no se corrio con herramientas).
6. `--allowedTools`/`--disallowedTools` con patrones `Bash(gh pr create*)`: sintaxis del help confirmada, efecto no corrido.
7. La forma exacta de las lineas `--json` de Codex y de `codex exec --output-schema`; y que `-s workspace-write` sin `network_access` corte la red de verdad en Bazzite.
8. `hook_response` incluye `exit_code` solo `...e.exitCode!==void 0&&{exit_code}`; el campo `outcome` (valores) no se vio.
9. Que `systemd-run --user --scope` funcione desde el proceso del server (que corre bajo la sesion de usuario de Pedro; el test se hizo desde un shell interactivo) y que `RuntimeMaxSec` mate al grupo entero.
10. `rate_limit_event`: si se emite en cada golpe o solo al arrancar sesion, y si `overageStatus: rejected` implica que un limite alcanzado devuelve `result.is_error` con texto "limit" (no se alcanzo el limite).
