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
    assert sb["network"]["allowedDomains"] == ["api.anthropic.com", "pypi.org"]
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


def test_golpear_exit_distinto_de_cero_y_cuota(cli_falso_stream, goal_en_disco, tmp_path):
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_golpe()[:1], "stderr": "You've hit your usage limit.", "exit": 1}])
    r = gm.golpear(argv=_argv_falso(cli, [_contrato(tmp_path)]), stdin="x",
                   cwd=str(goal_en_disco["clon"]), env=dict(os.environ), timeout_s=20, usar_systemd=False)
    assert r.exit == 1 and r.veredicto is None and "usage limit" in r.stderr_tail
    assert gm.es_fallo_de_cuota(r.stderr_tail) is True
    assert gm.es_fallo_de_cuota("Error: file not found") is False


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


# --- el detector de secretos sobre el ledger ---------------------------------------------

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
    assert r == {"cumplido": False, "falta": ["falta el test"], "nota": "casi", "revisor": "codex"}
    ll = cli.llamadas()[0]
    assert ll["argv"][0] == "exec" and "read-only" in ll["argv"]      # el falso anota sys.argv[1:]
    assert "crea saludo.py" in ll["stdin"] and "+def hola()" in ll["stdin"]
    assert ll["schema_codex"] and ll["salida_codex"]                 # --output-schema y -o, archivos


def test_revisar_con_claude_falso_cuando_las_manos_fueron_codex(cli_falso_stream, goal_en_disco):
    cli = cli_falso_stream
    cli.guion([{"lineas": lineas_revisor(True, nota="bien")}])
    r = gm.revisar(manos_del_golpe="codex", exes={"claude": cli.ruta}, goal_texto="x",
                   criterio={"tipo": "revisor", "texto": ""}, resumen_ledger="", diff="", salidas="",
                   cwd=str(goal_en_disco["clon"]), timeout=30)
    assert r == {"cumplido": True, "falta": [], "nota": "bien", "revisor": "claude"}
    ll = cli.llamadas()[0]
    assert ll["argv"][ll["argv"].index("--tools") + 1] == "Read,Glob,Grep"     # solo lectura
    assert "--restricted" in ll["argv"] and "Write" not in ll["argv"][ll["argv"].index("--tools") + 1]


def test_revisar_sin_la_otra_familia_es_none(goal_en_disco):
    assert gm.revisar(manos_del_golpe="claude", exes={"claude": "/x"}, goal_texto="x",
                      criterio={}, resumen_ledger="", diff="", salidas="",
                      cwd=str(goal_en_disco["clon"])) is None
