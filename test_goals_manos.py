"""Las manos del goal (spec 2026-09-13, seccion 7) con un CLI FALSO que
habla stream-json: la invocacion (argv, --settings con el sandbox y el hook,
stdin, cwd, env), el parser (unidades, comandos, veredicto, rate_limit, la
sonda del hook), el golpe (timeout que mata el grupo, cancelar, hook
inactivo = matar), la sonda del hook real, el detector de secretos y el
revisor de otra familia. Nada invoca claude ni codex reales.

`cli_falso_stream`, `lineas_golpe` y `lineas_revisor` los importa
test_goals_runner.py.
"""
from __future__ import annotations

import json
import os
import pathlib
import signal
import subprocess
import sys
import textwrap
import threading
import time

import pytest

from calipso import goals, goals_hook, goals_manos as gm


def lineas_golpe(session_id="s-1", comandos=(), veredicto=None, con_hook=True, unidades=2,
                 rate=0.37, tools=None, denials=(), escrituras=()) -> list[dict]:
    """Un golpe en stream-json como el de la sonda real (terreno A.5/A.6):
    init, rate_limit_event, por cada comando un assistant/tool_use +
    hook_started/hook_response (si con_hook) + user/tool_result, el
    StructuredOutput del veredicto y el result con usage.iterations."""
    tools = tools if tools is not None else ["Bash", "Edit", "Write", "Read", "StructuredOutput"]
    out = [{"type": "system", "subtype": "init", "cwd": "/x", "session_id": session_id,
            "tools": tools, "mcp_servers": [], "model": "claude-opus-5",
            "permissionMode": "acceptEdits", "claude_code_version": "2.1.270"},
           {"type": "rate_limit_event", "session_id": session_id,
            "rate_limit_info": {"status": "allowed", "resetsAt": 1789330200,
                                "rateLimitType": "five_hour",
                                "unifiedWindows": {"five_hour": {"utilization": rate, "resetsAt": 1789330200},
                                                   "seven_day": {"utilization": 0.13, "resetsAt": 1789819200}}}}]
    n = 0
    for i, (cmd, salida) in enumerate(comandos):
        n += 1
        tid = f"toolu_{i}"
        out.append({"type": "assistant", "session_id": session_id,
                    "message": {"id": f"msg_{n}", "role": "assistant",
                                "content": [{"type": "tool_use", "id": tid, "name": "Bash",
                                             "input": {"command": cmd}}],
                                "usage": {"input_tokens": 2, "output_tokens": 5}}})
        if con_hook:
            out.append({"type": "system", "subtype": "hook_started", "hook_id": "h", "hook_name": "goal",
                        "hook_event": "PreToolUse", "session_id": session_id})
            out.append({"type": "system", "subtype": "hook_response", "hook_id": "h", "hook_name": "goal",
                        "hook_event": "PreToolUse", "exit_code": 0, "outcome": "success",
                        "stdout": "", "stderr": "", "session_id": session_id})
        out.append({"type": "user", "session_id": session_id,
                    "message": {"role": "user", "content": [{"tool_use_id": tid, "type": "tool_result",
                                                             "content": salida}]}})
    for i, (ruta, contenido) in enumerate(escrituras):
        n += 1
        tid = f"toolu_w{i}"
        out.append({"type": "assistant", "session_id": session_id,
                    "message": {"id": f"msg_{n}", "role": "assistant",
                                "content": [{"type": "tool_use", "id": tid, "name": "Write",
                                             "input": {"file_path": ruta, "content": contenido}}],
                                "usage": {"input_tokens": 2, "output_tokens": 5}}})
        if con_hook:
            out.append({"type": "system", "subtype": "hook_response", "hook_event": "PreToolUse",
                        "exit_code": 0, "session_id": session_id})
        out.append({"type": "user", "session_id": session_id,
                    "message": {"role": "user", "content": [{"tool_use_id": tid, "type": "tool_result",
                                                             "content": "ok"}]}})
    v = veredicto or {"estado": "sigo", "resumen": "segui"}
    out.append({"type": "assistant", "session_id": session_id,
                "message": {"id": "msg_final", "role": "assistant",
                            "content": [{"type": "tool_use", "id": "toolu_so", "name": "StructuredOutput",
                                         "input": v}], "usage": {"input_tokens": 2, "output_tokens": 5}}})
    out.append({"type": "user", "session_id": session_id,
                "message": {"role": "user", "content": [{"tool_use_id": "toolu_so", "type": "tool_result",
                                                         "content": "Structured output provided successfully"}]}})
    out.append({"type": "result", "subtype": "success", "is_error": False, "num_turns": n + 1,
                "duration_ms": 2194, "total_cost_usd": 0.09, "session_id": session_id,
                "usage": {"input_tokens": 2, "output_tokens": 56,
                          "iterations": [{"type": "message"} for _ in range(unidades)]},
                "modelUsage": {"claude-opus-5": {"costUSD": 0.09}},
                "permission_denials": list(denials), "result": json.dumps(v), "structured_output": v})
    return out


def lineas_revisor(cumplido, falta=(), nota="") -> list[dict]:
    v = {"cumplido": bool(cumplido), "falta": list(falta), "nota": nota}
    return [{"type": "system", "subtype": "init", "session_id": "rev"},
            {"type": "result", "subtype": "success", "session_id": "rev", "result": json.dumps(v),
             "structured_output": v, "usage": {"iterations": [{"type": "message"}]}}]


@pytest.fixture
def cli_falso_stream(tmp_path):
    """El CLI falso del golpe (decision 27): lee el prompt por STDIN, anota
    argv, cwd, stdin, el JSON de --settings, el --json-schema, el contrato y
    el env (CALIPSO_GOAL_COMPUERTAS, CALIPSO_HOME, las credenciales que NO
    tienen que viajar) en llamada-N.json, y emite las lineas del guion.
    Un paso puede `dormir` (timeout), dejar un `hijo` (killpg), escribir la
    `salida_codex` (-o) y salir con `exit`/`stderr`."""
    carpeta = tmp_path / "cli"
    carpeta.mkdir()
    script = carpeta / "claude_falso.py"
    script.write_text(f"#!{sys.executable}\n" + textwrap.dedent('''
        import json, os, pathlib, subprocess, sys, time
        base = pathlib.Path(__file__).parent
        n = len(list(base.glob("llamada-*.json")))
        args = sys.argv[1:]
        def val(flag):
            return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None
        stdin = "" if sys.stdin.isatty() else sys.stdin.read()
        settings = val("--settings")
        try:
            settings = json.loads(settings) if settings and settings.lstrip().startswith("{") else settings
        except Exception:
            pass
        contrato = ""
        if val("--append-system-prompt-file"):
            contrato = pathlib.Path(val("--append-system-prompt-file")).read_text(encoding="utf-8")
        (base / f"llamada-{n}.json").write_text(json.dumps({
            "argv": args, "cwd": os.getcwd(), "stdin": stdin, "settings": settings,
            "schema": val("--json-schema"), "contrato": contrato,
            "salida_codex": val("-o"), "schema_codex": val("--output-schema"),
            "env": {k: os.environ.get(k) for k in ("CALIPSO_GOAL_COMPUERTAS", "CALIPSO_HOME",
                                                     "ANTHROPIC_API_KEY", "CALIPSO_TOKEN", "PYTHONPATH")},
        }), encoding="utf-8")
        guion = json.loads((base / "guion.json").read_text(encoding="utf-8"))
        paso = guion[min(n, len(guion) - 1)]
        if paso.get("hijo"):
            h = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])
            (base / "hijo.pid").write_text(str(h.pid), encoding="utf-8")
        for linea in paso.get("lineas", []):
            sys.stdout.write(json.dumps(linea) + "\\n")
            sys.stdout.flush()
            time.sleep(paso.get("pausa", 0))
        if paso.get("dormir"):
            time.sleep(paso["dormir"])
        if paso.get("stderr"):
            sys.stderr.write(paso["stderr"])
        if val("-o") and paso.get("salida_codex") is not None:
            pathlib.Path(val("-o")).write_text(json.dumps(paso["salida_codex"]), encoding="utf-8")
        sys.exit(paso.get("exit", 0))
    '''), encoding="utf-8")
    script.chmod(0o755)

    class CLI:
        ruta = str(script)
        ruta_codex = str(script)     # el mismo script sirve de codex falso (respeta -o y --output-schema)

        def guion(self, pasos):
            (carpeta / "guion.json").write_text(json.dumps(pasos), encoding="utf-8")

        def llamadas(self):
            return [json.loads(f.read_text(encoding="utf-8"))
                    for f in sorted(carpeta.glob("llamada-*.json"))]

        def hijo_pid(self):
            p = carpeta / "hijo.pid"
            return int(p.read_text(encoding="utf-8")) if p.exists() else None
    return CLI()


@pytest.fixture
def goal_en_disco(tmp_path, monkeypatch):
    home = tmp_path / ".calipso"
    home.mkdir()
    monkeypatch.setenv("CALIPSO_HOME", str(home))
    monkeypatch.setattr(goals, "CALIPSO_HOME", home)
    monkeypatch.setattr(goals.telemetry, "LEDGER", home / "telemetry.jsonl")
    g = goals.crear("crea saludo.py", proyecto=None, tope={"golpes": 3}, dominios=["pypi.org"])
    clon = goals.dir_goal(g["id"]) / "repo"
    (clon / ".git").mkdir(parents=True)
    g["repo"] = str(clon)
    goals.escribir(g)
    g = goals.load(None, g["id"])
    ruta = goals.escribir_compuertas(g)
    return {"goal": g, "clon": clon, "compuertas": ruta, "home": home}


# --- settings y argv ----------------------------------------------------------------

def test_settings_del_goal_enciende_el_sandbox_y_el_hook(goal_en_disco):
    c = goals.compuertas_de(goal_en_disco["goal"])
    s = gm.settings_del_goal(c, hook_python="/venv/bin/python", hook_path="/repo/calipso/goals_hook.py",
                             compuertas_path=str(goal_en_disco["compuertas"]))
    sb = s["sandbox"]
    assert sb["enabled"] is True and sb["failIfUnavailable"] is True
    assert sb["allowUnsandboxedCommands"] is False and sb["excludedCommands"] == []
    assert sb["autoAllowBashIfSandboxed"] is True
    assert sb["filesystem"]["allowWrite"] == [str(goal_en_disco["clon"])]
    for d in ("~/.ssh", "~/.gnupg", "~/.aws", "~/.config/gh", "~/.claude/.credentials.json",
              "~/.codex", "~/.calipso"):
        assert os.path.expanduser(d) in sb["filesystem"]["denyRead"]
    assert all(os.path.isabs(p) for p in sb["filesystem"]["denyRead"])
    # instalar_en_goal es directo (la tabla de Pedro): sin los indices de paquetes
    # en la red del sandbox era una compuerta imposible (primer goal real en
    # produccion: `pip install pytest` en el venv del clon -> pypi.org denegado)
    # (el goal declara pypi.org como dominio: no se repite)
    assert sb["network"]["allowedDomains"] == ["api.anthropic.com", *gm.DOMINIOS_INDICES]
    assert "files.pythonhosted.org" in gm.DOMINIOS_INDICES and "registry.npmjs.org" in gm.DOMINIOS_INDICES
    assert sb["network"]["deniedDomains"] == ["github.com", "api.github.com"]
    assert sb["network"]["strictAllowlist"] is True
    h = s["hooks"]["PreToolUse"]
    assert len(h) == 1 and h[0]["matcher"] == "Bash|Edit|Write|MultiEdit|NotebookEdit|Read|Glob|Grep|WebFetch|WebSearch"
    assert h[0]["hooks"] == [{"type": "command", "command": "/venv/bin/python",
                              "args": ["/repo/calipso/goals_hook.py", "--compuertas",
                                       str(goal_en_disco["compuertas"])],
                              "timeout": 20}]
    # con una raiz declarada, se suma a allowWrite
    c2 = {**c, "raices": ["/tmp/desc"]}
    assert gm.settings_del_goal(c2)["sandbox"]["filesystem"]["allowWrite"] == [str(goal_en_disco["clon"]), "/tmp/desc"]


def test_argv_claude_del_golpe():
    a = gm.argv_claude("/x/claude", contrato="/g/contrato.md", settings={"sandbox": {"enabled": True}},
                       schema=gm.ESQUEMA_VEREDICTO, session_id="u-1", resume=False, model="opus")
    assert a[:2] == ["/x/claude", "-p"]
    assert a[a.index("--permission-mode") + 1] == "acceptEdits"
    assert a[a.index("--permission-prompts") + 1] == "none"
    assert "--restricted" in a and "--strict-mcp-config" in a and "--verbose" in a
    assert a[a.index("--tools") + 1] == "Bash,Edit,Write,MultiEdit,Read,Glob,Grep"
    assert a[a.index("--setting-sources") + 1] == ""
    assert json.loads(a[a.index("--settings") + 1]) == {"sandbox": {"enabled": True}}
    assert a[a.index("--output-format") + 1] == "stream-json" and "--include-hook-events" in a
    assert json.loads(a[a.index("--json-schema") + 1]) == gm.ESQUEMA_VEREDICTO
    assert a[a.index("--session-id") + 1] == "u-1" and "--resume" not in a
    assert a[a.index("--append-system-prompt-file") + 1] == "/g/contrato.md"
    assert a[a.index("--model") + 1] == "opus"
    for prohibido in ("--bare", "--dangerously-skip-permissions", "bypassPermissions", "--no-session-persistence"):
        assert prohibido not in a
    b = gm.argv_claude("/x/claude", contrato="/g/c.md", settings={}, schema=gm.ESQUEMA_VEREDICTO,
                       session_id="u-1", resume=True, web=True)
    assert b[b.index("--resume") + 1] == "u-1" and "--session-id" not in b
    assert b[b.index("--tools") + 1] == "Bash,Edit,Write,MultiEdit,Read,Glob,Grep,WebSearch,WebFetch"
    assert "--model" not in b


def test_argv_claude_lleva_add_dir_por_cada_raiz():
    """Spec 15.5 y el smoke (G3, corridas 3 y 6): con `--permission-mode
    acceptEdits` el CLI niega un Write fuera del cwd aunque el hook lo
    permita (permission_denials), y el martillo caia a mv/cp por Bash. Lo
    que gobierna las herramientas de archivo es `--add-dir`: una por raiz
    (declarada o aprobada por raiz_nueva), ninguna sin raices."""
    a = gm.argv_claude("/x/claude", contrato="/g/c.md", settings={}, schema=gm.ESQUEMA_VEREDICTO,
                       session_id="u-1", resume=False, raices=["/tmp/desc", "/home/p/Notas"])
    dirs = [a[i + 1] for i, t in enumerate(a) if t == "--add-dir"]
    assert dirs == ["/tmp/desc", "/home/p/Notas"]
    b = gm.argv_claude("/x/claude", contrato="/g/c.md", settings={}, schema=gm.ESQUEMA_VEREDICTO,
                       session_id="u-1", resume=False)
    assert "--add-dir" not in b


def test_argv_codex_del_golpe():
    a = gm.argv_codex("/x/codex", cwd="/g/repo", raices=["/tmp/d"], salida="/g/out.txt",
                      schema_file="/g/s.json", model="gpt-5.5")
    assert a[:2] == ["/x/codex", "exec"] and a[a.index("-m") + 1] == "gpt-5.5"
    assert a[a.index("-s") + 1] == "workspace-write" and a[a.index("-C") + 1] == "/g/repo"
    assert a[a.index("--add-dir") + 1] == "/tmp/d" and "--json" in a
    assert a[a.index("-o") + 1] == "/g/out.txt" and a[a.index("--output-schema") + 1] == "/g/s.json"
    assert "--ephemeral" not in a and "--dangerously-bypass-approvals-and-sandbox" not in a
    assert a[-1] == "-"


def test_argv_systemd_envuelve_en_un_scope_con_tope():
    a = gm.argv_systemd(["/x/claude", "-p"], "calipso-goal-g1-3", 900)
    assert a[:3] == ["systemd-run", "--user", "--scope"]
    assert "--unit=calipso-goal-g1-3" in a and "-p" in a and "RuntimeMaxSec=930" in a
    assert a[a.index("--") + 1:] == ["/x/claude", "-p"]


def test_env_del_golpe(goal_en_disco, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setenv("PYTHONPATH", "/repo")
    env = gm.env_del_golpe(str(goal_en_disco["compuertas"]), str(goal_en_disco["home"] / "vacio"))
    assert env[goals_hook.VAR_COMPUERTAS] == str(goal_en_disco["compuertas"])
    assert env["CALIPSO_HOME"] == str(goal_en_disco["home"] / "vacio")
    assert "ANTHROPIC_API_KEY" not in env and "PYTHONPATH" not in env


# --- el parser -----------------------------------------------------------------------

def test_parser_unidades_comandos_veredicto_y_rate_limit():
    p = gm.Parser()
    for l in lineas_golpe(comandos=[("pytest -q", "1 passed"), ("ls", "a.py")],
                          veredicto={"estado": "terminar", "resumen": "listo"}, unidades=3):
        assert p.alimentar(json.dumps(l)) is None
    p.cerrar()
    assert p.session_id == "s-1" and p.model == "claude-opus-5"
    assert p.unidades == 3
    assert [c["cmd"] for c in p.comandos] == ["pytest -q", "ls"]
    assert p.comandos[0]["resultado_tail"] == "1 passed"
    assert p.veredicto == {"estado": "terminar", "resumen": "listo"}
    assert p.rate_limit == {"five_hour": 0.37, "seven_day": 0.13, "resets_at": 1789330200}
    assert p.costo_usd == 0.09 and p.hooks == 2 and p.violacion is None
    assert p.resultado["subtype"] == "success"


def test_parser_sin_result_cuenta_message_ids():
    p = gm.Parser()
    lineas = lineas_golpe(comandos=[("a", "x"), ("b", "y")])[:-1]     # sin el result
    for l in lineas:
        p.alimentar(json.dumps(l))
    p.cerrar()
    assert p.unidades == 3 and p.veredicto is None                    # msg_1, msg_2, msg_final


def test_parser_sonda_del_hook():
    """Trampa 2: el hook corre ENTRE el tool_use y el tool_result. Un
    tool_result de una herramienta con hook sin hook_response en el medio =
    violacion. StructuredOutput no cuenta."""
    p = gm.Parser()
    for l in lineas_golpe(comandos=[("ls", "a")], con_hook=False):
        v = p.alimentar(json.dumps(l))
        if v:
            break
    assert p.violacion and "hook inactivo" in p.violacion and "Bash" in p.violacion
    # con hook: sin violacion, y el StructuredOutput sin hook no molesta
    p2 = gm.Parser()
    assert all(p2.alimentar(json.dumps(l)) is None for l in lineas_golpe(comandos=[("ls", "a")]))
    # un MCP inesperado en init: violacion
    p3 = gm.Parser()
    v = p3.alimentar(json.dumps(lineas_golpe(tools=["Bash", "mcp__claude_ai_Google_Drive__copy_file"])[0]))
    assert v and "mcp inesperado" in v


def test_parser_solo_cuenta_hook_response_pretooluse():
    """C4 (Codex): un `hook_response` sin `hook_event` (o de otro evento)
    contaba como PreToolUse y evitaba `hook inactivo`. Solo cuenta el que
    dice `hook_event == "PreToolUse"`."""
    for fila_rara in ({"type": "system", "subtype": "hook_response", "exit_code": 0, "session_id": "s-1"},
                      {"type": "system", "subtype": "hook_response", "hook_event": "PostToolUse", "exit_code": 0,
                       "session_id": "s-1"},
                      {"type": "system", "subtype": "hook_response", "hook_event": None, "exit_code": 0,
                       "session_id": "s-1"}):
        lineas = lineas_golpe(comandos=[("ls", "a")], con_hook=False)
        i = next(k for k, l in enumerate(lineas) if l.get("type") == "user")
        lineas.insert(i, fila_rara)
        p = gm.Parser()
        for l in lineas:
            if p.alimentar(json.dumps(l)):
                break
        assert p.violacion and "hook inactivo" in p.violacion and p.hooks == 0, (fila_rara, p.violacion)


def _stream_paralelo(hooks_antes_del_primero, hooks_entre, ids_en_hook=False):
    """Dos tool_use en el MISMO assistant (Claude Code corre en paralelo los
    Read/Grep/Glob): los hooks arrancan juntos y el stream sale en orden de
    terminacion. init, assistant(A, B), N hook_response, tool_result(B),
    M hook_response, tool_result(A), result."""
    def hook(tid):
        fila = {"type": "system", "subtype": "hook_response", "hook_event": "PreToolUse",
                "exit_code": 0, "session_id": "s-1"}
        if ids_en_hook:
            fila["tool_use_id"] = tid
        return fila

    def resultado(tid):
        return {"type": "user", "session_id": "s-1",
                "message": {"role": "user", "content": [{"tool_use_id": tid, "type": "tool_result",
                                                         "content": "ok"}]}}
    out = [lineas_golpe()[0],
           {"type": "assistant", "session_id": "s-1",
            "message": {"id": "msg_1", "role": "assistant",
                        "content": [{"type": "tool_use", "id": "toolu_a", "name": "Read",
                                     "input": {"file_path": "a.py"}},
                                    {"type": "tool_use", "id": "toolu_b", "name": "Grep",
                                     "input": {"pattern": "x"}}]}}]
    out += [hook("toolu_b") for _ in range(hooks_antes_del_primero)]
    out.append(resultado("toolu_b"))
    out += [hook("toolu_a") for _ in range(hooks_entre)]
    out.append(resultado("toolu_a"))
    out.append(lineas_golpe()[-1])
    return out


def test_parser_sonda_del_hook_con_herramientas_en_paralelo():
    """La sonda cuenta, no aparea por orden: con dos tool_use en paralelo el
    hook_response de B puede salir antes que el de A y el tool_result de B
    antes que el hook_response de A. Eso NO es un hook inactivo (cada
    hook_response precede al tool_result de SU tool). Un solo hook_response
    para dos resultados si lo es."""
    p = gm.Parser()
    assert all(p.alimentar(json.dumps(l)) is None for l in _stream_paralelo(1, 1))
    assert p.violacion is None and p.hooks == 2
    # los dos hook_response juntos y los tool_result invertidos: tampoco
    p2 = gm.Parser()
    assert all(p2.alimentar(json.dumps(l)) is None for l in _stream_paralelo(2, 0))
    assert p2.violacion is None
    # un solo hook_response para dos tool_result: el segundo es la violacion
    p3 = gm.Parser()
    vistos = [p3.alimentar(json.dumps(l)) for l in _stream_paralelo(1, 0)]
    assert p3.violacion and "hook inactivo" in p3.violacion and "toolu_a" in p3.violacion
    assert vistos.index(p3.violacion) == 4                       # recien en el tool_result de A
    # el primer tool_result sin ningun hook_response: violacion (0 < 1)
    p4 = gm.Parser()
    vistos = [p4.alimentar(json.dumps(l)) for l in _stream_paralelo(0, 2)]
    assert p4.violacion and "toolu_b" in p4.violacion and vistos.index(p4.violacion) == 2


def test_parser_sonda_del_hook_aparea_por_id_si_el_stream_lo_trae():
    """Si el hook_response real trae tool_use_id, ademas de contar se
    aparea por id: un tool_result cuyo tool_use no tuvo SU hook_response es
    violacion aunque la cuenta cierre."""
    p = gm.Parser()
    assert all(p.alimentar(json.dumps(l)) is None for l in _stream_paralelo(1, 1, ids_en_hook=True))
    assert p.violacion is None
    # hook_response(B) con id, tool_result(A): la cuenta cierra (1 >= 1) pero A no tuvo hook
    lineas = _stream_paralelo(1, 0, ids_en_hook=True)
    lineas[3], lineas[4] = lineas[4], lineas[3]                  # tool_result(A) antes que el de B
    p2 = gm.Parser()
    vistos = [p2.alimentar(json.dumps(l)) for l in lineas]
    assert p2.violacion and "hook inactivo" in p2.violacion and "toolu_a" in p2.violacion
    assert vistos.index(p2.violacion) == 3


def test_parser_guarda_el_is_error_de_cada_comando_y_el_result_con_error():
    """rev:manos-runner: el tool_result del stream trae `is_error: true`
    cuando el comando salio distinto de 0: es la senal real de un fallo
    (no_converge la usa en vez de buscar 'error' en la cola, que marcaba un
    `ls` con errors.py como fallo); y el `result` con `is_error` es donde
    el CLI cuenta por que corto (el limite de cuota puede venir ahi con
    exit 1, no solo por stderr)."""
    lineas = lineas_golpe(comandos=[("pytest -q", "1 failed"), ("ls", "errors.py")])
    for l in lineas:
        if l.get("type") == "user" and l["message"]["content"][0]["tool_use_id"] == "toolu_0":
            l["message"]["content"][0]["is_error"] = True
    p = gm.Parser()
    for l in lineas:
        p.alimentar(json.dumps(l))
    assert [(c["cmd"], c["error"]) for c in p.comandos] == [("pytest -q", True), ("ls", False)]
    assert p.error_texto == ""
    p2 = gm.Parser()
    p2.alimentar(json.dumps(lineas[0]))
    p2.alimentar(json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True,
                             "result": "You've hit your usage limit. Resets at 6pm", "session_id": "s-1"}))
    assert p2.error_texto == "You've hit your usage limit. Resets at 6pm" and p2.veredicto is None
    p3 = gm.Parser()
    p3.alimentar(json.dumps({"type": "error", "message": "rate limit reached"}))
    p3.alimentar(json.dumps({"type": "turn.failed", "error": {"message": "quota exceeded"}}))
    assert "rate limit reached" in p3.error_texto and "quota exceeded" in p3.error_texto


def test_texto_de_fallo_no_mira_las_lineas_json_del_stream():
    """`rate_limit_event` esta en TODO stream de claude y `rate_limit` es un
    patron de cuota: un golpe que sale 1 por otra cosa con esa linea en la
    cola del stdout no es un fallo por cuota. Entran stderr, el `result`
    con is_error y las lineas sueltas (no JSON) del stdout."""
    r = gm.Resultado(exit=1, stderr_tail="", error_texto="",
                     stdout_tail=json.dumps(lineas_golpe()[1]) + "\n" + json.dumps(
                         {"type": "result", "is_error": True, "result": "Error: boom"}))
    assert gm.es_fallo_de_cuota(gm.texto_de_fallo(r)) is False
    r2 = gm.Resultado(exit=1, stderr_tail="", error_texto="You've hit your usage limit", stdout_tail="")
    assert gm.es_fallo_de_cuota(gm.texto_de_fallo(r2)) is True
    r3 = gm.Resultado(exit=1, stderr_tail="", error_texto="", stdout_tail="Claude usage limit reached\n")
    assert gm.es_fallo_de_cuota(gm.texto_de_fallo(r3)) is True
    r4 = gm.Resultado(exit=1, stderr_tail="rate limit", error_texto="", stdout_tail="")
    assert gm.es_fallo_de_cuota(gm.texto_de_fallo(r4)) is True


def test_texto_de_fallo_descarta_la_primera_linea_partida_de_un_tail_recortado():
    """Re-review del carril 2 (menor): el tail del stdout son los ultimos
    TAIL_MAX bytes, asi que su primera linea puede ser un JSON del stream
    cortado por la mitad (`...ate limit ..."}`) que no empieza con `{` y se
    leia como una linea suelta: un tool_result con `rate limit` adentro
    pasaba por fallo de cuota. Recortado (len >= TAIL_MAX) y con la primera
    linea sin `{`, esa linea se descarta; una linea suelta entera al final
    y un tail corto siguen contando."""
    largo = json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "content": "grep -rn 'rate limit' src -- hay un rate limit en el cliente " * 40}]}})
    tail = (largo + "\n" + json.dumps({"type": "result", "is_error": True, "result": "Error: boom"}))[-gm.TAIL_MAX:]
    assert len(tail) == gm.TAIL_MAX and not tail.startswith("{") and "rate limit" in tail.splitlines()[0]
    r = gm.Resultado(exit=1, stderr_tail="", error_texto="", stdout_tail=tail)
    assert gm.es_fallo_de_cuota(gm.texto_de_fallo(r)) is False
    # la ultima linea suelta (un error impreso a secas) sigue entrando
    tail2 = (largo + "\nClaude usage limit reached")[-gm.TAIL_MAX:]
    r2 = gm.Resultado(exit=1, stderr_tail="", error_texto="", stdout_tail=tail2)
    assert gm.es_fallo_de_cuota(gm.texto_de_fallo(r2)) is True
    # un tail corto (no recortado) no pierde su primera linea
    r3 = gm.Resultado(exit=1, stderr_tail="", error_texto="", stdout_tail="rate limit reached\n")
    assert gm.es_fallo_de_cuota(gm.texto_de_fallo(r3)) is True


def test_parser_tolera_basura_y_denials():
    p = gm.Parser()
    assert p.alimentar("no es json") is None
    assert p.alimentar("") is None
    for l in lineas_golpe(denials=[{"tool_name": "Bash", "tool_input": {"command": "gh pr create"}}]):
        p.alimentar(json.dumps(l))
    p.cerrar()
    assert p.denials == [{"tool_name": "Bash", "tool_input": {"command": "gh pr create"}}]


# --- el golpe -------------------------------------------------------------------------

def _contrato(tmp_path, texto="CONTRATO"):
    """El contrato tiene que existir: el CLI falso lo lee (como el real)."""
    p = tmp_path / "contrato.md"
    p.write_text(texto, encoding="utf-8")
    return str(p)


def _argv_falso(cli, extra=()):
    return [cli.ruta, "-p", "--restricted", "--settings", json.dumps({"sandbox": {"enabled": True}}),
            "--append-system-prompt-file", *extra]


def test_golpear_pasa_stdin_settings_y_env_y_parsea(cli_falso_stream, goal_en_disco, tmp_path):
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_golpe(comandos=[("pytest -q", "ok")],
                                       veredicto={"estado": "sigo", "resumen": "hice"})}])
    contrato = _contrato(tmp_path)
    env = gm.env_del_golpe(str(goal_en_disco["compuertas"]), str(tmp_path / "vacio"))
    r = gm.golpear(argv=_argv_falso(cli, [contrato]), stdin="PROMPT secreto ghp_abcdefghijklmnop",
                   cwd=str(goal_en_disco["clon"]), env=env, timeout_s=30, usar_systemd=False)
    assert r.exit == 0 and r.motivo is None and not r.timeout and not r.matado
    assert r.session_id == "s-1" and r.unidades == 2 and [c["cmd"] for c in r.comandos] == ["pytest -q"]
    assert r.veredicto == {"estado": "sigo", "resumen": "hice"} and r.duracion_ms >= 0
    assert r.rate_limit["five_hour"] == 0.37 and r.subtype == "success"
    ll = cli.llamadas()[0]
    assert ll["stdin"] == "PROMPT secreto ghp_abcdefghijklmnop"        # el prompt va por stdin tal cual
    assert "PROMPT" not in " ".join(ll["argv"])
    assert ll["cwd"] == str(goal_en_disco["clon"]) and ll["contrato"] == "CONTRATO"
    assert ll["settings"] == {"sandbox": {"enabled": True}}
    assert ll["env"]["CALIPSO_GOAL_COMPUERTAS"] == str(goal_en_disco["compuertas"])
    assert ll["env"]["CALIPSO_HOME"] == str(tmp_path / "vacio")
    assert ll["env"]["ANTHROPIC_API_KEY"] is None and ll["env"]["PYTHONPATH"] is None


def test_golpear_timeout_mata_el_grupo_entero(cli_falso_stream, goal_en_disco, tmp_path):
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_golpe()[:2], "hijo": True, "dormir": 60}])
    t0 = time.monotonic()
    r = gm.golpear(argv=_argv_falso(cli, [_contrato(tmp_path)]), stdin="x",
                   cwd=str(goal_en_disco["clon"]), env=dict(os.environ), timeout_s=2,
                   usar_systemd=False, sondeo_s=0.2)
    assert time.monotonic() - t0 < 15
    assert r.timeout is True and r.matado is True and r.motivo == "timeout"
    assert r.session_id == "s-1"                                       # lo que alcanzo a parsear
    hijo = cli.hijo_pid()
    assert hijo
    time.sleep(0.5)
    with pytest.raises(ProcessLookupError):
        os.kill(hijo, 0)                                                # el nieto murio con el grupo


def test_golpear_hook_inactivo_mata_y_lo_dice(cli_falso_stream, goal_en_disco, tmp_path):
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_golpe(comandos=[("ls", "a")], con_hook=False), "pausa": 0.05,
                "dormir": 30}])
    r = gm.golpear(argv=_argv_falso(cli, [_contrato(tmp_path)]), stdin="x",
                   cwd=str(goal_en_disco["clon"]), env=dict(os.environ), timeout_s=20,
                   usar_systemd=False, sondeo_s=0.1)
    assert r.matado is True and r.motivo and r.motivo.startswith("hook inactivo")
    assert r.timeout is False


def test_golpear_cancelar_mata_y_publica_el_handle(cli_falso_stream, goal_en_disco, tmp_path):
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_golpe()[:1], "dormir": 30}])
    cancelar = threading.Event()
    threading.Timer(0.5, cancelar.set).start()
    vistos = []
    r = gm.golpear(argv=_argv_falso(cli, [_contrato(tmp_path)]), stdin="x",
                   cwd=str(goal_en_disco["clon"]), env=dict(os.environ), timeout_s=20,
                   usar_systemd=False, cancelar=cancelar, sondeo_s=0.1, al_lanzar=vistos.append)
    assert r.matado is True and r.motivo == "cancelado"
    assert len(vistos) == 1 and vistos[0].pid and vistos[0].poll() is not None   # el Popen, ya muerto


def test_golpear_publica_la_unidad_del_scope_junto_con_el_handle(cli_falso_stream, goal_en_disco, tmp_path,
                                                                monkeypatch):
    """`al_lanzar(proc, unidad)`: el runner guarda la unidad para que
    matar_golpe pare el scope ademas del grupo. Con un `al_lanzar` de un
    solo parametro (los tests viejos, `vistos.append`) se llama como antes;
    sin systemd la unidad publicada es None."""
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_golpe()[:1], "dormir": 30}])
    monkeypatch.setattr(gm, "argv_systemd", lambda argv, unidad, t: argv)      # sin systemd-run real
    paradas = []
    monkeypatch.setattr(gm, "_parar_unidad", paradas.append)
    cancelar = threading.Event()
    threading.Timer(0.5, cancelar.set).start()
    vistos = []
    r = gm.golpear(argv=_argv_falso(cli, [_contrato(tmp_path)]), stdin="x",
                   cwd=str(goal_en_disco["clon"]), env=dict(os.environ), timeout_s=20,
                   usar_systemd=True, unidad="calipso-goal-t-1", cancelar=cancelar, sondeo_s=0.1,
                   al_lanzar=lambda proc, unidad: vistos.append((proc, unidad)))
    assert r.motivo == "cancelado" and len(vistos) == 1
    assert vistos[0][0].pid and vistos[0][1] == "calipso-goal-t-1" and paradas == ["calipso-goal-t-1"]
    cli.guion([{"lineas": lineas_golpe()}])
    vistos2 = []
    gm.golpear(argv=_argv_falso(cli, [_contrato(tmp_path)]), stdin="x", cwd=str(goal_en_disco["clon"]),
               env=dict(os.environ), timeout_s=20, usar_systemd=False, unidad="calipso-goal-t-2",
               al_lanzar=lambda proc, unidad: vistos2.append(unidad))
    assert vistos2 == [None]


def test_golpear_con_cancelar_ya_puesto_dice_cancelado_aunque_el_cli_ya_murio(cli_falso_stream,
                                                                             goal_en_disco, tmp_path):
    """El sondeo mira `cancelar` antes que poll(): un CLI matado por parar
    (muere en ms) vuelve con motivo cancelado, no None."""
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_golpe()[:1]}])
    cancelar = threading.Event()
    cancelar.set()
    r = gm.golpear(argv=_argv_falso(cli, [_contrato(tmp_path)]), stdin="x",
                   cwd=str(goal_en_disco["clon"]), env=dict(os.environ), timeout_s=20,
                   usar_systemd=False, cancelar=cancelar, sondeo_s=0.5)
    assert r.motivo == "cancelado" and r.matado is True


def test_golpear_exit_distinto_de_cero_y_cuota(cli_falso_stream, goal_en_disco, tmp_path):
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_golpe()[:1], "stderr": "You've hit your usage limit.", "exit": 1}])
    r = gm.golpear(argv=_argv_falso(cli, [_contrato(tmp_path)]), stdin="x",
                   cwd=str(goal_en_disco["clon"]), env=dict(os.environ), timeout_s=20, usar_systemd=False)
    assert r.exit == 1 and r.veredicto is None and "usage limit" in r.stderr_tail
    assert gm.es_fallo_de_cuota(r.stderr_tail) is True
    assert gm.es_fallo_de_cuota("Error: file not found") is False


# --- el criterio confinado (cierre 2026-09-14, critico) -----------------------------------

@pytest.fixture
def home_falso(monkeypatch):
    """Un HOME de mentira FUERA de /tmp: el confinado monta un tmpfs sobre
    /tmp, asi que un home bajo tmp_path quedaria tapado por eso y no por la
    barrera que se quiere medir (home de solo lectura + tmpfs sobre cada
    DENY_READ). Bajo /var/tmp (o TMPDIR si no se puede) el home es visible
    de solo lectura y el test mide lo que importa. Se borra al salir."""
    import shutil as _sh
    import tempfile
    base = "/var/tmp" if os.access("/var/tmp", os.W_OK) else None
    casa = pathlib.Path(tempfile.mkdtemp(prefix="calipso-home-falso-", dir=base))
    (casa / ".ssh").mkdir()
    (casa / ".ssh" / "x").write_text("llave de mentira\n", encoding="utf-8")
    (casa / ".claude").mkdir()
    (casa / ".claude" / ".credentials.json").write_text("{\"token\": \"de mentira\"}", encoding="utf-8")
    (casa / ".claude" / "projects").mkdir()
    (casa / ".claude" / "projects" / "sesion.jsonl").write_text("transcripcion de mentira\n", encoding="utf-8")
    (casa / ".local" / "share" / "keyrings").mkdir(parents=True)
    (casa / ".local" / "share" / "keyrings" / "login.keyring").write_text("llavero de mentira\n", encoding="utf-8")
    (casa / "Documentos").mkdir()
    monkeypatch.setenv("HOME", str(casa))
    try:
        yield casa
    finally:
        _sh.rmtree(casa, ignore_errors=True)


def _script(clon, nombre, cuerpo):
    p = clon / nombre
    p.write_text("#!/bin/sh\n" + cuerpo + "\n", encoding="utf-8")
    p.chmod(0o755)
    return p


def _compuertas(clon, raices=()):
    return {"goal": "goal_t", "clon": str(clon), "cwd": str(clon), "raices": list(raices), "dominios": [],
            "niveles": dict(goals.NIVEL_DE), "preautorizadas": [], "venv": str(clon / ".venv"),
            "registro": str(clon.parent / "hook.jsonl")}


def test_argv_bwrap_es_el_espejo_del_sandbox_del_golpe(home_falso, tmp_path):
    clon = tmp_path / "clon"
    clon.mkdir()
    raiz = tmp_path / "Descargas"
    raiz.mkdir()
    a = gm.argv_bwrap(["/x/pytest", "-q"], cwd=str(clon), compuertas=_compuertas(clon, [str(raiz), "/no/existe"]),
                      bwrap="/usr/bin/bwrap")
    assert a[0] == "/usr/bin/bwrap" and a[1:4] == ["--ro-bind", "/", "/"]
    assert "--dev" in a and "--proc" in a and a[a.index("--tmpfs") + 1] == "/tmp"
    binds = [(a[i + 1], a[i + 2]) for i, t in enumerate(a) if t == "--bind"]
    assert binds == [(str(clon), str(clon)), (str(raiz), str(raiz))]        # la raiz que no existe no se monta
    tmpfs = [a[i + 1] for i, t in enumerate(a) if t == "--tmpfs"]
    assert str(home_falso / ".ssh") in tmpfs and str(home_falso / "Documentos") not in tmpfs
    assert str(home_falso / ".calipso") not in tmpfs                          # no existe en el home falso: no se monta
    # las PROTEGIDAS del hook que no son DENY_READ del sandbox (~/.claude
    # entero, los keyrings) tambien van tapadas (re-review del carril 2);
    # lo que cuelga de un tmpfs ya montado no se monta aparte
    assert str(home_falso / ".claude") in tmpfs and str(home_falso / ".local" / "share" / "keyrings") in tmpfs
    ro = [(a[i + 1], a[i + 2]) for i, t in enumerate(a) if t == "--ro-bind"]
    assert not any(d.startswith(str(home_falso / ".claude")) for _, d in ro)
    assert len(tmpfs) == len(set(tmpfs))
    for flag in ("--unshare-net", "--unshare-pid", "--die-with-parent", "--new-session"):
        assert flag in a
    assert a.index("--unshare-pid") > a.index("--proc")                    # el /proc nuevo es el del namespace
    assert a[a.index("--chdir") + 1] == str(clon)
    assert a[a.index("--") + 1:] == ["/x/pytest", "-q"]
    assert a.index("--tmpfs") < a.index("--bind")                          # el clon se monta DESPUES del tmpfs de /tmp


def test_argv_bwrap_tapa_un_archivo_protegido_con_dev_null(home_falso, tmp_path, monkeypatch):
    """Un DENY_READ o PROTEGIDA que es un ARCHIVO no admite tmpfs: se tapa
    con /dev/null de solo lectura (hoy `.credentials.json` cae bajo el
    tmpfs de ~/.claude; la rama queda para cuando la lista traiga otro)."""
    monkeypatch.setattr(gm, "DENY_READ", ["~/.ssh", "~/.netrc-falso"])
    monkeypatch.setattr(goals_hook, "PROTEGIDAS", ("~/.ssh",))
    (home_falso / ".netrc-falso").write_text("machine x login y\n", encoding="utf-8")
    clon = tmp_path / "clon"
    clon.mkdir()
    a = gm.argv_bwrap(["/x/pytest"], cwd=str(clon), compuertas=_compuertas(clon), bwrap="/usr/bin/bwrap")
    ro = [(a[i + 1], a[i + 2]) for i, t in enumerate(a) if t == "--ro-bind"]
    assert ("/dev/null", str(home_falso / ".netrc-falso")) in ro
    assert [a[i + 1] for i, t in enumerate(a) if t == "--tmpfs"] == ["/tmp", str(home_falso / ".ssh")]


def test_correr_confinado_escribe_en_el_clon_y_no_fuera_ni_lee_lo_protegido(home_falso, tmp_path):
    """Critico del cierre: el comando del criterio corria fuera del sandbox
    con el HOME real, red abierta y ~/.ssh legible, ejecutando codigo que
    el martillo dejo en el clon (conftest.py, check.py). Bajo bwrap: el clon
    es escribible, el home no (EROFS), ~/.ssh no se lee, y el proceso se
    publica por al_lanzar."""
    clon = tmp_path / "clon"
    clon.mkdir()
    casa = home_falso
    _script(clon, "escribe.sh", f'echo ok > "{clon}/ok.txt"')
    _script(clon, "fuera.sh", f'echo x > "{casa}/fuera.txt"')
    _script(clon, "lee.sh", f'ls "{casa}/.claude" "{casa}/.local/share/keyrings"; cat "{casa}/.ssh/x"; '
                            f'cat "{casa}/.claude/.credentials.json"; cat "{casa}/.local/share/keyrings/login.keyring"; '
                            f'cat "{casa}/.claude/projects/sesion.jsonl"')
    _script(clon, "lee_doc.sh", f'ls "{casa}/Documentos" && echo LEGIBLE')
    vistos = []
    r = gm.correr_confinado(["./escribe.sh"], cwd=str(clon), compuertas=_compuertas(clon), timeout_s=30,
                            usar_systemd=False, al_lanzar=lambda proc, unidad: vistos.append((proc, unidad)))
    assert r.exit == 0 and r.motivo is None, (r.exit, r.motivo, r.stderr_tail)
    assert (clon / "ok.txt").read_text(encoding="utf-8").strip() == "ok"
    assert len(vistos) == 1 and vistos[0][0].pid and vistos[0][1] is None and r.duracion_ms >= 0
    r = gm.correr_confinado(["./fuera.sh"], cwd=str(clon), compuertas=_compuertas(clon), timeout_s=30,
                            usar_systemd=False)
    assert r.exit != 0 and "ead-only" in r.stderr_tail and not (casa / "fuera.txt").exists()
    r = gm.correr_confinado(["./lee.sh"], cwd=str(clon), compuertas=_compuertas(clon), timeout_s=30,
                            usar_systemd=False)
    assert r.exit != 0 and "llave" not in r.stdout_tail and "de mentira" not in r.stdout_tail
    assert "sesion.jsonl" not in r.stdout_tail and "login.keyring" not in r.stdout_tail   # ni listar
    # lo del home que no es DENY_READ se lee (solo lectura): el criterio no es el martillo
    r = gm.correr_confinado(["./lee_doc.sh"], cwd=str(clon), compuertas=_compuertas(clon), timeout_s=30,
                            usar_systemd=False)
    assert r.exit == 0 and "LEGIBLE" in r.stdout_tail
    # una raiz declarada si es escribible
    raiz = tmp_path / "Descargas"
    raiz.mkdir()
    _script(clon, "raiz.sh", f'echo x > "{raiz}/notas.txt"')
    r = gm.correr_confinado(["./raiz.sh"], cwd=str(clon), compuertas=_compuertas(clon, [str(raiz)]),
                            timeout_s=30, usar_systemd=False)
    assert r.exit == 0 and (raiz / "notas.txt").exists()


def test_correr_confinado_sin_red(home_falso, tmp_path):
    clon = tmp_path / "clon"
    clon.mkdir()
    _script(clon, "red.sh", "cat /proc/net/route | tail -n +2 | wc -l; ls /sys/class/net")
    r = gm.correr_confinado(["./red.sh"], cwd=str(clon), compuertas=_compuertas(clon), timeout_s=30,
                            usar_systemd=False)
    assert r.exit == 0 and r.stdout_tail.split()[0] == "0" and "lo" in r.stdout_tail   # solo loopback, sin rutas


def test_correr_confinado_sin_bwrap_no_corre(home_falso, tmp_path, monkeypatch):
    clon = tmp_path / "clon"
    clon.mkdir()
    _script(clon, "escribe.sh", f'echo ok > "{clon}/ok.txt"')
    monkeypatch.setenv("PATH", str(tmp_path / "vacio"))
    r = gm.correr_confinado(["./escribe.sh"], cwd=str(clon), compuertas=_compuertas(clon), timeout_s=30,
                            usar_systemd=False)
    assert r.exit is None and r.motivo == "criterio: sin bwrap no se corre (barrera)"
    assert not (clon / "ok.txt").exists()                                    # fail-closed: no corrio


def test_correr_confinado_resuelve_el_ejecutable(home_falso, tmp_path, monkeypatch):
    """rev:lente-riesgo: el PATH del server real no tiene .venv/bin y todo
    criterio `pytest -q` fallaba con Errno 2. `<clon>/.venv/bin/<exe>`
    primero, despues el PATH, y para pytest/python `sys.executable`; sin
    resolver, el juez dice por que."""
    clon = tmp_path / "clon"
    (clon / ".venv" / "bin").mkdir(parents=True)
    _script(clon / ".venv" / "bin", "pytest", 'echo "venv-pytest $@"; echo "PATH=$PATH"')
    r = gm.correr_confinado(["pytest", "-q", "tests/"], cwd=str(clon), compuertas=_compuertas(clon),
                            timeout_s=30, usar_systemd=False)
    assert r.exit == 0 and "venv-pytest -q tests/" in r.stdout_tail
    assert f"PATH={clon / '.venv' / 'bin'}{os.pathsep}" in r.stdout_tail   # el venv del clon primero en el PATH
    # sin venv y sin pytest en el PATH: el interprete del server con -m pytest
    which_real = gm.shutil.which
    monkeypatch.setattr(gm.shutil, "which", lambda exe, **k: which_real(exe, **k) if exe == "bwrap" else None)
    clon2 = tmp_path / "clon2"
    clon2.mkdir()
    r = gm.correr_confinado(["python", "-c", "import sys; print(sys.executable)"], cwd=str(clon2),
                            compuertas=_compuertas(clon2), timeout_s=30, usar_systemd=False)
    assert r.exit == 0 and r.stdout_tail.strip() == sys.executable
    assert gm.resolver_exe("pytest", str(clon2), "") == [sys.executable, "-m", "pytest"]
    assert gm.resolver_exe("python3", str(clon2), "") == [sys.executable]
    r = gm.correr_confinado(["noexiste-xyz", "-q"], cwd=str(clon2), compuertas=_compuertas(clon2),
                            timeout_s=30, usar_systemd=False)
    assert r.exit is None and r.motivo == "criterio: noexiste-xyz no esta en el PATH del server ni en el venv del clon"
    # una ruta relativa al clon (./check.sh, .venv/bin/pytest) y una absoluta
    _script(clon2, "check.sh", "echo check")
    assert gm.resolver_exe("./check.sh", str(clon2), "") == [str(clon2 / "check.sh")]
    assert gm.resolver_exe("/bin/sh", str(clon2), "") == ["/bin/sh"]
    assert gm.resolver_exe("./no.sh", str(clon2), "") is None


def test_correr_confinado_timeout_mata_lo_de_adentro(home_falso, tmp_path):
    """El comando y lo que deja de fondo (`sleep 120 &`, un nieto que
    `--die-with-parent` solo no alcanza: re-review del carril 2) mueren
    con bwrap: `--unshare-pid` los pone en un namespace cuyo PID 1 es
    bwrap. Un `$$` de adentro no sirve afuera (es el pid del namespace),
    asi que los dos sleep corren por un symlink con nombre propio y se
    buscan por la linea de comandos desde el host."""
    clon = tmp_path / "clon"
    clon.mkdir()
    marca = f"calipso-test-fondo-{os.getpid()}"
    (clon / marca).symlink_to("/usr/bin/sleep")
    _script(clon, "duerme.sh", f'./{marca} 120 & exec ./{marca} 60')
    t0 = time.monotonic()
    r = gm.correr_confinado(["./duerme.sh"], cwd=str(clon), compuertas=_compuertas(clon), timeout_s=1,
                            usar_systemd=False, sondeo_s=0.1)
    assert time.monotonic() - t0 < 15 and r.timeout is True and r.motivo == "timeout" and r.matado is True
    time.sleep(0.5)
    vivos = subprocess.run(["pgrep", "-f", marca], capture_output=True, text=True).stdout.split()
    for v in vivos:
        os.kill(int(v), signal.SIGKILL)                            # que no quede colgado si el test falla
    assert vivos == [], f"un sleep sobrevivio a bwrap: {vivos}"
    # y cancelar lo corta igual
    cancelar = threading.Event()
    threading.Timer(0.5, cancelar.set).start()
    r = gm.correr_confinado(["./duerme.sh"], cwd=str(clon), compuertas=_compuertas(clon), timeout_s=30,
                            usar_systemd=False, sondeo_s=0.1, cancelar=cancelar)
    assert r.motivo == "cancelado" and r.matado is True


def test_correr_confinado_con_scope_publica_la_unidad(home_falso, tmp_path, monkeypatch):
    clon = tmp_path / "clon"
    clon.mkdir()
    _script(clon, "ok.sh", "echo ok")
    monkeypatch.setattr(gm, "argv_systemd", lambda argv, unidad, t: argv)       # sin systemd-run real
    vistos = []
    r = gm.correr_confinado(["./ok.sh"], cwd=str(clon), compuertas=_compuertas(clon), timeout_s=30,
                            usar_systemd=True, unidad="calipso-goal-g-criterio-2",
                            al_lanzar=lambda proc, unidad: vistos.append(unidad))
    assert r.exit == 0 and vistos == ["calipso-goal-g-criterio-2"]


# --- la sonda del hook real ------------------------------------------------------------

def test_sondear_hook_con_el_hook_real(goal_en_disco):
    ok, motivo = gm.sondear_hook(str(goal_en_disco["compuertas"]))
    assert ok is True, motivo
    ok, motivo = gm.sondear_hook(str(goal_en_disco["compuertas"]), hook_path="/no/existe.py")
    assert ok is False and motivo
    # un hook que deja pasar gh pr create no sirve
    permisivo = goal_en_disco["home"] / "permisivo.py"
    permisivo.write_text("import sys; sys.exit(0)\n", encoding="utf-8")
    ok, motivo = gm.sondear_hook(str(goal_en_disco["compuertas"]), hook_path=str(permisivo))
    assert ok is False and "exit 0" in motivo


# --- el esquema estricto de codex (smoke corrida 3, No confirmado 7) ----------------------

def _objetos(nodo):
    """Todos los nodos de esquema con type object (recursivo)."""
    if isinstance(nodo, dict):
        t = nodo.get("type")
        if t == "object" or (isinstance(t, list) and "object" in t):
            yield nodo
        for v in nodo.values():
            yield from _objetos(v)
    elif isinstance(nodo, list):
        for v in nodo:
            yield from _objetos(v)


def test_esquema_para_codex_es_estricto_y_no_toca_el_original():
    """El smoke vio a codex salir 1 en 2,5 s con `invalid_json_schema:
    'additionalProperties' is required to be supplied and to be false`: el
    modo estricto de OpenAI exige additionalProperties false y todas las
    claves en required (lo opcional se vuelve nullable) en CADA objeto."""
    e = gm.esquema_para_codex(gm.ESQUEMA_VEREDICTO)
    assert e["additionalProperties"] is False and e["required"] == list(e["properties"])
    assert e["properties"]["estado"] == {"type": "string", "enum": ["sigo", "terminar", "preguntar"]}
    assert e["properties"]["pregunta"]["type"] == ["string", "null"]
    c = e["properties"]["compuerta"]
    assert c["type"] == ["object", "null"] and c["additionalProperties"] is False
    assert c["required"] == ["familia", "forma"] and c["properties"]["forma"]["additionalProperties"] is False
    assert c["properties"]["forma"]["properties"]["argv"]["type"] == ["array", "null"]
    # el original sigue permisivo (claude lo recibe por --json-schema)
    assert "additionalProperties" not in gm.ESQUEMA_VEREDICTO
    assert gm.ESQUEMA_VEREDICTO["required"] == ["estado", "resumen"]
    for esquema in (gm.ESQUEMA_PROPUESTA, gm.ESQUEMA_REVISOR, gm.ESQUEMA_VEREDICTO):
        for o in _objetos(gm.esquema_para_codex(esquema)):
            assert o["additionalProperties"] is False and o["required"] == list(o.get("properties") or {})


def test_sin_nulos_deja_el_veredicto_de_codex_como_el_de_claude():
    v = {"estado": "sigo", "resumen": "hice", "pregunta": None,
         "compuerta": {"familia": None, "forma": {"raiz": None, "argv": ["a"]}}, "l": [{"a": None, "b": 1}, None]}
    assert gm.sin_nulos(v) == {"estado": "sigo", "resumen": "hice",
                               "compuerta": {"forma": {"argv": ["a"]}}, "l": [{"b": 1}, None]}
    assert gm.sin_nulos({"estado": "sigo", "resumen": "x", "pregunta": None, "compuerta": None}) == \
        {"estado": "sigo", "resumen": "x"}


# --- el detector de secretos sobre el ledger ---------------------------------------------

def test_tapar_no_tapa_rutas_de_archivo_pero_si_los_secretos_adentro():
    """Smoke corrida 5: la regla de entropia del detector (_TOKEN) marcaba la
    ruta del goal en el PROMPT (`/tmp/goals-smoke-<x>/Descargas`) y el
    martillo pidio la raiz literal "[SECRETO]"; en produccion tapa 43/300
    rutas de clon y 286/300 de contrato.md (ids hex al azar). Una ruta de
    archivo no es un secreto; lo que SI lo es (prefijos, hex de 32, PEM,
    JWT) se tapa aunque venga dentro de una ruta."""
    from calipso.privacidad import detector as det
    rutas = ["/tmp/goals-smoke-dqz8nryc/Descargas", "/home/pedro/.calipso/goals/goal_0123456789ab/contrato.md",
             "ls -la /tmp/goals-smoke-dqz8nryc/trabajo/goal_0123456789ab/repo",
             "cp /etc/hostname ~/goals-smoke-dqz8nryc/Descargas/notas.txt", "./trabajo/goal_0123456789ab/repo/x.py"]
    assert any(det.detectar_secretos(r) for r in rutas)          # el detector solo las marcaria
    for r in rutas:
        assert gm.tapar(r) == (r, 0), r
    blob = "QWxhZGRpbjpvcGVuIHNlc2FtZQ1234567890xyzABC"
    assert det.detectar_secretos(blob)                            # un blob opaco de alta entropia
    assert gm.tapar(blob) == ("[SECRETO]", 1)
    for con_secreto in ["/tmp/x/ghp_abcdefghijklmnopqrstuvwxyz0123", "/tmp/x/0123456789abcdef0123456789abcdef/y",
                        "token ghp_abcdefghijklmnopqrstuvwxyz0123 en /tmp/goals-smoke-dqz8nryc/Descargas"]:
        texto, n = gm.tapar(con_secreto)
        assert n >= 1 and "[SECRETO]" in texto and "ghp_" not in texto and "0123456789abcdef0123456789abcdef" not in texto
    fila, n = gm.tapar_fila({"comandos": [{"cmd": "cp /etc/hostname /tmp/goals-smoke-dqz8nryc/Descargas/notas.txt"}],
                             "veredicto_del_golpe": {"compuerta": {"forma": {"raiz": "/tmp/goals-smoke-dqz8nryc/Descargas"}}}})
    assert n == 0 and fila["veredicto_del_golpe"]["compuerta"]["forma"]["raiz"] == "/tmp/goals-smoke-dqz8nryc/Descargas"


def test_tapar_tapa_el_segmento_de_una_ruta_con_pinta_de_secreto():
    """Cierre 2026-09-14 (rev:manos-runner sobre f15f918): eximir la ruta
    ENTERA dejaba pasar un secreto de entropia en posicion de segmento,
    que es donde aparece en un `ls`/`find`/`cat` (`/tmp/x/<blob>`,
    `~/.ssh/<clave>`). Ruling: tapar por segmento: el detector corre sobre
    cada segmento y se reemplazan solo los marcados; las rutas normales
    (ids hex del goal, tmp del smoke, CamelCase) quedan intactas."""
    from calipso.privacidad import detector as det
    blob = "Xk9pLm2Qw8Rt5Yu7Iv3Oz6Bn1Ca4De0F"
    llave = "AAAAC3NzaC1lZDI1NTE5AAAAIGx0Pz9QmR7vTk3LwXyZaBcDeFgHiJkLmNoPqRs"
    for ruta, esperado in ((f"/tmp/x/{blob}", "/tmp/x/[SECRETO]"),
                           (f"/tmp/{blob}/a.txt", "/tmp/[SECRETO]/a.txt"),
                           (f"/a/b/{blob}.pem", "/a/b/[SECRETO]"),
                           (f"ls ~/.config/gcloud/legacy_credentials/{blob}",
                            "ls ~/.config/gcloud/legacy_credentials/[SECRETO]"),
                           (f"cat /run/user/1000/keyring/{blob}", "cat /run/user/1000/keyring/[SECRETO]"),
                           (f"/home/pedro/.ssh/{llave}/x", "/home/pedro/.ssh/[SECRETO]/x"),
                           (f"/tmp/{blob}/{llave}", "/tmp/[SECRETO]/[SECRETO]")):
        texto, n = gm.tapar(ruta)
        assert texto == esperado and n == esperado.count("[SECRETO]"), (ruta, texto, n)
    for intacta in ("/home/pedro/.calipso/goals/goal_0123456789ab/contrato.md",
                    "/tmp/goals-smoke-dqz8nryc/Descargas", "/var/home/pedro/calipso/.claude/worktrees/goals",
                    "/tmp/goals-smoke-x7k2mq9w/trabajo/goal_9f8e7d6c5b4a/repo/src/MyAwesomeProject/SomeVeryLongFileName.java",
                    "./node_modules/@types/someLib/dist/someLib.d.ts"):
        assert gm.tapar(intacta) == (intacta, 0), intacta
    # las reglas explicitas siguen tapando en cualquier posicion, tambien dentro de una ruta
    for con_secreto, resto in (("/tmp/x/ghp_abcdefghijklmnopqrstuvwxyz0123", "ghp_"),
                               ("cat /tmp/0123456789abcdef0123456789abcdef/y", "0123456789abcdef"),
                               ("curl -H 'Authorization: Bearer sk-ant-abcdefghijklmnop' https://x/y/z", "sk-ant"),
                               ("-----BEGIN PRIVATE KEY----- x", "BEGIN PRIVATE"),
                               ("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", "wJalr")):
        texto, n = gm.tapar(con_secreto)
        assert n >= 1 and "[SECRETO]" in texto and resto not in texto, (con_secreto, texto)
    # limitacion declarada: un secreto CON barras pegado detras de un prefijo de ruta
    # (`/x/y/` + la clave AWS) no tiene ningun segmento que el detector marque solo
    # (todos miden menos de 20), y juntar segmentos vuelve a tapar rutas normales
    aws = "/x/y/wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    assert not any(det.detectar_secretos(seg) for seg in aws.split("/"))
    assert gm.tapar(aws) == (aws, 0)


def test_tapar_y_tapar_fila():
    texto, n = gm.tapar("token ghp_abcdefghijklmnopqrstuvwxyz0123 y una clave -----BEGIN PRIVATE KEY----- x")
    assert n == 2 and "ghp_" not in texto and "[SECRETO]" in texto
    fila = {"n": 1, "session_id": "cb01e83b-203f-41ce-bcde-4afe792e5a5d",
            "diff_stat": "saludo.py | 3 +++ 0123456789abcdef0123456789abcdef01234567",
            "comandos": [{"cmd": "curl -H 'Authorization: Bearer sk-ant-abcdefghijklmnop'", "resultado_tail": "ok"}],
            "veredicto_del_golpe": {"resumen": "use AKIAABCDEFGHIJKLMNOP"}}
    tapada, n = gm.tapar_fila(fila)
    assert n == 2
    assert tapada["session_id"] == fila["session_id"]                    # SIN_TAPAR (Trampa 19)
    assert tapada["diff_stat"] == fila["diff_stat"]
    assert "sk-ant" not in tapada["comandos"][0]["cmd"] and "AKIA" not in tapada["veredicto_del_golpe"]["resumen"]
    assert tapada["n"] == 1


# --- el revisor de otra familia ------------------------------------------------------------

def test_otra_familia():
    assert gm.otra_familia("claude") == "codex" and gm.otra_familia("codex") == "claude"


def test_revisar_con_codex_falso_cuando_las_manos_fueron_claude(cli_falso_stream, goal_en_disco):
    cli = cli_falso_stream
    cli.guion([{"salida_codex": {"cumplido": False, "falta": ["falta el test"], "nota": "casi"}}])
    r = gm.revisar(manos_del_golpe="claude", exes={"codex": cli.ruta_codex}, goal_texto="crea saludo.py",
                   criterio={"tipo": "revisor", "texto": ""}, resumen_ledger="golpe 1: hice saludo.py",
                   diff="+def hola()", salidas="", cwd=str(goal_en_disco["clon"]), timeout=30)
    assert r == {"cumplido": False, "falta": ["falta el test"], "nota": "casi", "revisor": "codex", "unidades": 1}
    ll = cli.llamadas()[0]
    assert ll["argv"][0] == "exec" and "read-only" in ll["argv"]      # el falso anota sys.argv[1:]
    assert "crea saludo.py" in ll["stdin"] and "+def hola()" in ll["stdin"]
    assert ll["schema_codex"] and ll["salida_codex"]                 # --output-schema y -o, archivos


def _revisar_claude(cli, goal_en_disco, **extra):
    c = goals.compuertas_de(goal_en_disco["goal"])
    return gm.revisar(manos_del_golpe="codex", exes={"claude": cli.ruta}, goal_texto="x",
                      criterio={"tipo": "revisor", "texto": ""}, resumen_ledger="", diff="", salidas="",
                      cwd=str(goal_en_disco["clon"]), timeout=30, compuertas=c,
                      compuertas_path=str(goal_en_disco["compuertas"]), **extra)


def test_revisar_con_claude_falso_corre_con_la_barrera_del_golpe(cli_falso_stream, goal_en_disco):
    """rev:manos-runner (importante): el revisor claude corria con
    Read/Glob/Grep SIN --settings (ni sandbox con denyRead ni hook) ni la
    sonda del Parser: una sesion con lectura sobre TODO el disco, y lo que
    lee viaja a la API (invariante 9, ruling 15.7). Ahora lleva el
    --settings del goal (sandbox + hook con Read|Glob|Grep),
    --include-hook-events, --permission-prompts none, el env del golpe y
    devuelve las unidades reales del stream."""
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_revisor(True, nota="bien")}])
    r = _revisar_claude(cli, goal_en_disco)
    assert r == {"cumplido": True, "falta": [], "nota": "bien", "revisor": "claude", "unidades": 1}
    ll = cli.llamadas()[0]
    a = ll["argv"]
    assert a[a.index("--tools") + 1] == "Read,Glob,Grep" and "--restricted" in a
    assert "--include-hook-events" in a and a[a.index("--permission-prompts") + 1] == "none"
    assert a[a.index("--setting-sources") + 1] == "" and "--strict-mcp-config" in a
    s = ll["settings"]
    assert s["sandbox"]["enabled"] is True and s["sandbox"]["failIfUnavailable"] is True
    assert os.path.expanduser("~/.ssh") in s["sandbox"]["filesystem"]["denyRead"]
    h = s["hooks"]["PreToolUse"][0]
    assert "Read" in h["matcher"] and "Glob" in h["matcher"] and "Grep" in h["matcher"]
    assert h["hooks"][0]["args"] == [str(gm.HOOK_PATH), "--compuertas", str(goal_en_disco["compuertas"])]
    assert ll["env"]["CALIPSO_GOAL_COMPUERTAS"] == str(goal_en_disco["compuertas"])
    assert ll["env"]["CALIPSO_HOME"] == str(goals.dir_goal(goal_en_disco["goal"]["id"]) / "home_vacio")
    for prohibido in ("--bare", "--dangerously-skip-permissions", "bypassPermissions", "acceptEdits"):
        assert prohibido not in a
    # las unidades reales: tres iteraciones
    cli.guion([{"lineas": [lineas_revisor(False, falta=["x"])[0],
                           {**lineas_revisor(False, falta=["x"])[1],
                            "usage": {"iterations": [{"type": "message"}] * 3}}]}])
    r = _revisar_claude(cli, goal_en_disco)
    assert r["cumplido"] is False and r["falta"] == ["x"] and r["unidades"] == 3


def test_revisar_con_claude_sin_compuertas_va_sin_herramientas(cli_falso_stream, goal_en_disco):
    """Sin la barrera (compuertas) el revisor claude no recibe Read/Glob/
    Grep: solo el diff y las salidas que le mandamos (fail-closed)."""
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_revisor(True)}])
    r = gm.revisar(manos_del_golpe="codex", exes={"claude": cli.ruta}, goal_texto="x", criterio={},
                   resumen_ledger="", diff="", salidas="", cwd=str(goal_en_disco["clon"]), timeout=30)
    assert r["cumplido"] is True
    a = cli.llamadas()[0]["argv"]
    assert a[a.index("--tools") + 1] == "" and "--settings" not in a


def test_revisar_claude_con_hook_inactivo_se_mata_y_lo_dice(cli_falso_stream, goal_en_disco):
    """El stream del revisor pasa por el Parser: un tool_result de Read sin
    hook_response PreToolUse antes = hook inactivo -> se mata y vuelve sin
    veredicto, con el motivo y la cola del stdout."""
    cli = cli_falso_stream
    lineas = [lineas_revisor(True)[0],
              {"type": "assistant", "session_id": "rev",
               "message": {"id": "m1", "role": "assistant",
                           "content": [{"type": "tool_use", "id": "t1", "name": "Read",
                                        "input": {"file_path": "/etc/passwd"}}]}},
              {"type": "user", "session_id": "rev",
               "message": {"role": "user", "content": [{"tool_use_id": "t1", "type": "tool_result",
                                                        "content": "root:x:0:0"}]}}]
    cli.guion([{"lineas": lineas, "pausa": 0.05, "dormir": 30}])
    r = _revisar_claude(cli, goal_en_disco)
    assert r["cumplido"] is None and r["motivo"].startswith("hook inactivo") and r["revisor"] == "claude"
    assert "root:x:0:0" in r["salida_tail"] and r["unidades"] >= 1
    # el mismo stream con su hook_response: sin violacion
    lineas.insert(2, {"type": "system", "subtype": "hook_response", "hook_event": "PreToolUse", "exit_code": 0})
    cli.guion([{"lineas": lineas + [lineas_revisor(True)[1]]}])
    assert _revisar_claude(cli, goal_en_disco)["cumplido"] is True


def test_revisar_que_falla_dice_por_que_con_la_cola(cli_falso_stream, goal_en_disco):
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_revisor(True)[:1], "stderr": "boom", "exit": 1}])
    r = _revisar_claude(cli, goal_en_disco)
    assert r["cumplido"] is None and r["motivo"] == "exit 1" and r["unidades"] == 0
    assert "init" in r["salida_tail"]
    cli.guion([{"lineas": [lineas_revisor(True)[0],
                           {"type": "result", "subtype": "success", "session_id": "rev", "result": "no es json"}]}])
    r = _revisar_claude(cli, goal_en_disco)
    assert r["cumplido"] is None and "sin veredicto" in r["motivo"]
    cli.guion([{"salida_codex": {"cumplido": True, "falta": [], "nota": ""}, "exit": 2, "stderr": "codex roto"}])
    r = gm.revisar(manos_del_golpe="claude", exes={"codex": cli.ruta_codex}, goal_texto="x", criterio={},
                   resumen_ledger="", diff="", salidas="", cwd=str(goal_en_disco["clon"]), timeout=30)
    assert r["cumplido"] is None and r["motivo"] == "exit 2" and "codex roto" in r["salida_tail"] and r["unidades"] == 0


def test_cabeza_devuelve_unidades_salida_y_sesion(cli_falso_stream, goal_en_disco, tmp_path):
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_golpe(unidades=4, veredicto={"titulo": "t", "manos": "claude"})}])
    vacio = tmp_path / "vacio"
    vacio.mkdir()
    c = gm.cabeza("claude", cli.ruta, "SISTEMA", "PROMPT", gm.ESQUEMA_PROPUESTA, cwd=str(vacio), timeout=30)
    assert isinstance(c, gm.Cabeza) and c.veredicto == {"titulo": "t", "manos": "claude"}
    assert c.unidades == 4 and c.session_id == "s-1" and c.exit == 0 and c.motivo is None
    assert '"type": "result"' in c.salida_tail
    a = cli.llamadas()[0]["argv"]
    assert "--settings" not in a and "--include-hook-events" not in a          # la propuesta: sin hooks
    # la envoltura vieja devuelve solo el dict
    cli.guion([{"lineas": lineas_golpe(veredicto={"titulo": "u", "manos": "claude"})}])
    assert gm.cabeza_sin_herramientas("claude", cli.ruta, "S", "P", gm.ESQUEMA_PROPUESTA, cwd=str(vacio),
                                      timeout=30) == {"titulo": "u", "manos": "claude"}


def test_revisar_publica_el_handle_y_matarlo_lo_corta(cli_falso_stream, goal_en_disco):
    """El revisor cuenta como golpe (spec 6.2): `al_lanzar` publica su Popen
    apenas existe (el runner lo guarda en golpe_en_curso, como el del
    martillo) y matarlo lo corta: revisar -> None, sin colgar."""
    cli = cli_falso_stream
    cli.guion([{"salida_codex": {"cumplido": True, "falta": [], "nota": ""}, "dormir": 30}])
    vistos, salida = [], {}

    def _corre():
        salida["r"] = gm.revisar(manos_del_golpe="claude", exes={"codex": cli.ruta_codex}, goal_texto="x",
                                 criterio={}, resumen_ledger="", diff="", salidas="",
                                 cwd=str(goal_en_disco["clon"]), timeout=60, al_lanzar=vistos.append)
    hilo = threading.Thread(target=_corre)
    hilo.start()
    limite = time.monotonic() + 10
    while not vistos and time.monotonic() < limite:
        time.sleep(0.05)
    assert vistos and vistos[0].pid and vistos[0].poll() is None
    gm.matar(vistos[0])
    hilo.join(timeout=15)
    assert not hilo.is_alive() and vistos[0].poll() is not None
    assert salida["r"]["cumplido"] is None and salida["r"]["motivo"].startswith("exit ")


def test_revisar_sin_la_otra_familia_es_none(goal_en_disco):
    assert gm.revisar(manos_del_golpe="claude", exes={"claude": "/x"}, goal_texto="x",
                      criterio={}, resumen_ledger="", diff="", salidas="",
                      cwd=str(goal_en_disco["clon"])) is None


def test_los_indices_de_paquetes_entran_solo_con_instalar_en_goal_directo(goal_en_disco):
    """La red del sandbox lleva pypi/npm SOLO porque `instalar_en_goal` es
    directo en la tabla del goal; si Pedro la baja a pregunta o nunca, los
    indices salen de la lista y el martillo tiene que preguntar (web)."""
    c = json.loads(goal_en_disco["compuertas"].read_text(encoding="utf-8"))   # el JSON que lee el hook
    c["niveles"] = {**c.get("niveles", {}), "instalar_en_goal": "pregunta"}
    c["dominios"] = []
    s = gm.settings_del_goal(c, hook_python="/venv/bin/python", hook_path="/repo/calipso/goals_hook.py",
                             compuertas_path="/x/compuertas.json")
    assert s["sandbox"]["network"]["allowedDomains"] == ["api.anthropic.com"]
    c["niveles"]["instalar_en_goal"] = "directo"
    s = gm.settings_del_goal(c, hook_python="/venv/bin/python", hook_path="/repo/calipso/goals_hook.py",
                             compuertas_path="/x/compuertas.json")
    assert s["sandbox"]["network"]["allowedDomains"] == ["api.anthropic.com", *gm.DOMINIOS_INDICES]
    assert "github.com" not in s["sandbox"]["network"]["allowedDomains"]
