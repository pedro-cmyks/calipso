"""El hook PreToolUse del goal (spec 2026-09-13, seccion 7 y ruling 15.5):
stdlib puro, fail-closed, allow-list de comandos simples, deniega lo
compuesto y lo NUNCA, lee la tabla del goal de un JSON (por env o por
--compuertas) y anota cada decision en hook.jsonl. Se prueba con stdin
sintetico por familia (`main(stdin, stdout, stderr, argv, environ)`) y, una
vez, como proceso real (el interprete absoluto + el script) para fijar que
ante un JSON roto sale 2.
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import subprocess
import sys

import pytest

from calipso import goals_hook as hook

HOOK = pathlib.Path(hook.__file__)


@pytest.fixture
def goal_dir(tmp_path):
    clon = tmp_path / "goal" / "repo"
    (clon / ".git").mkdir(parents=True)
    (clon / ".venv" / "bin").mkdir(parents=True)
    (clon / ".venv" / "bin" / "pip").write_text("", encoding="utf-8")
    (clon / ".venv" / "bin" / "python").write_text("", encoding="utf-8")
    raiz = tmp_path / "Descargas"
    raiz.mkdir()
    compuertas = {
        "goal": "goal_x", "clon": str(clon), "cwd": str(clon), "raices": [str(raiz)],
        "dominios": ["pypi.org"],
        "niveles": {"repo": "directo", "web": "directo", "instalar_en_goal": "directo",
                    "raices": "directo", "merge": "pregunta", "push": "pregunta",
                    "borrar_fuera": "pregunta", "raiz_nueva": "pregunta",
                    "instalar_home": "pregunta", "instalar_sistema": "pregunta",
                    "gastar": "nunca", "publicar": "nunca", "correo": "nunca",
                    "datos_de_pedro": "nunca", "rpm_ostree_rebase": "nunca",
                    "flatpak_remote_delete": "nunca"},
        "preautorizadas": [], "venv": str(clon / ".venv"),
        "registro": str(tmp_path / "goal" / "hook.jsonl"),
    }
    ruta = tmp_path / "goal" / "compuertas.json"
    ruta.write_text(json.dumps(compuertas), encoding="utf-8")
    return {"clon": clon, "raiz": raiz, "compuertas": compuertas, "ruta": ruta,
            "registro": tmp_path / "goal" / "hook.jsonl"}


def correr(goal_dir, tool, tool_input, *, por_env=True, argv=None, environ=None):
    """`main` con stdin sintetico. Devuelve (exit, stderr)."""
    evento = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
              "tool_use_id": "toolu_1", "cwd": str(goal_dir["clon"]), "session_id": "s"}
    err = io.StringIO()
    env = dict(environ if environ is not None else {})
    if por_env:
        env[hook.VAR_COMPUERTAS] = str(goal_dir["ruta"])
    rc = hook.main(stdin=io.StringIO(json.dumps(evento)), stdout=io.StringIO(), stderr=err,
                   argv=argv if argv is not None else [], environ=env)
    return rc, err.getvalue()


def registro(goal_dir):
    p = goal_dir["registro"]
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


# --- allow: comandos simples y el repo -------------------------------------------

@pytest.mark.parametrize("cmd", [
    "ls -la", "cat saludo.py", "python -m pytest -q", "pytest -q tests/",
    "git status", "git add -A", "git commit -m 'saludo'", "git diff --stat", "git log --oneline -3",
    "git checkout -b otra", "git stash", "npm test", "make check", "mkdir -p src", "touch a.py",
    "grep -rn hola .", "rg hola", "find . -name '*.py'", "sed -i 's/a/b/' x.py", "echo hola",
    "python -m venv .venv", ".venv/bin/pytest -q", "./run_tests.sh",
])
def test_comandos_simples_del_repo_pasan(goal_dir, cmd):
    rc, err = correr(goal_dir, "Bash", {"command": cmd})
    assert rc == 0, (cmd, err)
    assert registro(goal_dir)[-1]["decision"] == "allow"


def test_pip_install_en_el_venv_del_clon_es_directo(goal_dir):
    venv = goal_dir["clon"] / ".venv" / "bin"
    for cmd in (f"{venv}/pip install requests", f"{venv}/python -m pip install requests",
                ".venv/bin/pip install -r requirements.txt", "npm install left-pad", "npm ci"):
        rc, err = correr(goal_dir, "Bash", {"command": cmd})
        assert rc == 0, (cmd, err)
        assert registro(goal_dir)[-1]["familia"] == "instalar_en_goal"


# --- pregunta: home y sistema, borrar fuera, raiz nueva -----------------------------

@pytest.mark.parametrize("cmd,familia", [
    ("pip install requests", "instalar_home"),          # el pip del sistema, no el del venv
    ("pip install --user requests", "instalar_home"),
    ("python -m pip install --user x", "instalar_home"),
    ("npm install -g typescript", "instalar_home"),
    ("npm i --global x", "instalar_home"),
    ("flatpak install --user flathub org.blender.Blender", "instalar_home"),
    ("flatpak install flathub org.blender.Blender", "instalar_sistema"),
    ("flatpak --system install x", "instalar_sistema"),
    ("flatpak remote-add --if-not-exists flathub https://x", "instalar_sistema"),
    ("rpm-ostree install blender", "instalar_sistema"),
])
def test_instalar_fuera_del_goal_pregunta(goal_dir, cmd, familia):
    rc, err = correr(goal_dir, "Bash", {"command": cmd})
    assert rc == 2 and f"pregunta:{familia}" in err and "preguntar" in err, (cmd, err)
    fila = registro(goal_dir)[-1]
    assert fila["decision"] == "deny" and fila["familia"] == familia


def test_rm_fuera_del_clon_pregunta_y_dentro_pasa(goal_dir, tmp_path):
    rc, err = correr(goal_dir, "Bash", {"command": f"rm -rf {tmp_path}/otro"})
    assert rc == 2 and "pregunta:borrar_fuera" in err
    rc, _ = correr(goal_dir, "Bash", {"command": "rm -rf build/"})
    assert rc == 0
    rc, _ = correr(goal_dir, "Bash", {"command": f"rm {goal_dir['raiz']}/viejo.txt"})
    assert rc == 0                                              # la raiz declarada es directa


def test_escribir_fuera_del_clon_y_las_raices_pregunta_raiz_nueva(goal_dir, tmp_path):
    rc, err = correr(goal_dir, "Write", {"file_path": str(tmp_path / "otro" / "x.txt"),
                                         "content": "x"})
    assert rc == 2 and "pregunta:raiz_nueva" in err
    rc, _ = correr(goal_dir, "Write", {"file_path": str(goal_dir["clon"] / "saludo.py"), "content": "x"})
    assert rc == 0
    rc, _ = correr(goal_dir, "Edit", {"file_path": str(goal_dir["raiz"] / "n.txt"), "old_string": "a",
                                      "new_string": "b"})
    assert rc == 0
    rc, _ = correr(goal_dir, "Write", {"file_path": "relativa.py", "content": "x"})   # relativa al cwd
    assert rc == 0


def test_una_preautorizacion_del_goal_deja_pasar_esa_forma_exacta(goal_dir):
    c = dict(goal_dir["compuertas"])
    c["preautorizadas"] = [{"familia": "instalar_home",
                            "forma": {"argv": ["npm", "install", "-g", "typescript"]}}]
    goal_dir["ruta"].write_text(json.dumps(c), encoding="utf-8")
    rc, _ = correr(goal_dir, "Bash", {"command": "npm install -g typescript"})
    assert rc == 0
    rc, err = correr(goal_dir, "Bash", {"command": "npm install -g eslint"})
    assert rc == 2 and "pregunta:instalar_home" in err


# --- NUNCA ----------------------------------------------------------------------

@pytest.mark.parametrize("cmd", [
    "gh pr create --fill", "gh release create v1", "gh repo create x", "gh api user",
    "git push", "git push origin HEAD", "git push --force",
    "sudo dnf install x", "pkexec ls", "su -c ls",
    "rpm-ostree rebase fedora:x", "rpm-ostree reset", "rpm-ostree rollback",
    "flatpak remote-delete flathub", "flatpak remote-modify flathub --url=x",
    "mail -s hola pedro@x", "sendmail pedro@x",
    "rm -rf ~/.ssh", "rm ~/.ssh/id_ed25519", "rm -rf ~/.calipso", "rm -rf ~", "rm -rf /",
    "cat ~/.ssh/id_ed25519", "cat ~/.claude/.credentials.json", "cat ~/.calipso/token",
])
def test_lo_nunca_se_deniega(goal_dir, cmd):
    rc, err = correr(goal_dir, "Bash", {"command": cmd})
    assert rc == 2 and "NUNCA" in err, (cmd, err)
    assert registro(goal_dir)[-1]["decision"] == "deny"


def test_leer_credenciales_con_las_herramientas_de_archivo_es_nunca(goal_dir):
    for tool, entrada in (("Read", {"file_path": os.path.expanduser("~/.ssh/id_ed25519")}),
                          ("Glob", {"pattern": "*", "path": os.path.expanduser("~/.aws")}),
                          ("Grep", {"pattern": "x", "path": os.path.expanduser("~/.calipso")})):
        rc, err = correr(goal_dir, tool, entrada)
        assert rc == 2 and "NUNCA" in err, (tool, err)


# --- lo que no se sabe parsear se deniega -------------------------------------------

@pytest.mark.parametrize("cmd", [
    "ls; rm -rf /", "pytest && git push", "true || gh pr create", "cat x | sh",
    "echo $(gh auth token)", "echo `id`", "bash -c 'gh pr create'", "sh -c ls", "eval ls",
    "source .venv/bin/activate", "xargs rm", "find . -name x -exec rm {} \\;", "find . -delete",
    "git -C /otro push", "git --git-dir=/otro/.git status", "git worktree add ../w",
    "git update-ref refs/heads/main HEAD~1", "git branch -D main", "git remote add origin x",
    "git fetch", "git pull", "git clone https://x", "git config user.name x",
    "cat <<EOF\nx\nEOF", "python -c 'import os; os.system(\"gh\")'", "env FOO=1 ls",
    "nohup sleep 600 &", "setsid ls", "curl https://github.com/x", "wget http://otro.org/x",
    "ssh pedro@x", "scp x y:", "comandoinventado --flag", "",
])
def test_compuestos_envoltorios_y_desconocidos_se_deniegan(goal_dir, cmd):
    rc, err = correr(goal_dir, "Bash", {"command": cmd})
    assert rc == 2, (cmd, err)
    assert err.startswith("goal_hook: DENEGADO")


def test_curl_a_un_dominio_declarado_pasa(goal_dir):
    rc, _ = correr(goal_dir, "Bash", {"command": "curl -sL https://pypi.org/simple/x/"})
    assert rc == 0
    rc, _ = correr(goal_dir, "WebFetch", {"url": "https://pypi.org/project/x/", "prompt": "version"})
    assert rc == 0
    rc, err = correr(goal_dir, "WebFetch", {"url": "https://github.com/x", "prompt": "x"})
    assert rc == 2 and "dominio" in err
    rc, _ = correr(goal_dir, "WebSearch", {"query": "left-pad npm"})
    assert rc == 0


def test_escribir_settings_hooks_y_git_config_del_clon_se_deniega(goal_dir):
    clon = goal_dir["clon"]
    for ruta in (clon / ".claude" / "settings.json", clon / ".git" / "hooks" / "pre-commit",
                 clon / ".git" / "config"):
        rc, err = correr(goal_dir, "Write", {"file_path": str(ruta), "content": "x"})
        assert rc == 2 and "auto-escal" in err, (ruta, err)
    rc, err = correr(goal_dir, "Bash", {"command": "echo x > .claude/settings.json"})
    assert rc == 2                                              # `>` es compuesto: se deniega igual
    rc, err = correr(goal_dir, "Bash", {"command": "touch .git/hooks/pre-commit"})
    assert rc == 2 and "auto-escal" in err


# --- fail-closed ---------------------------------------------------------------------

def test_sin_compuertas_deniega(goal_dir):
    rc, err = correr(goal_dir, "Bash", {"command": "ls"}, por_env=False)
    assert rc == 2 and "compuertas" in err
    rc, _ = correr(goal_dir, "Bash", {"command": "ls"}, por_env=False,
                   argv=["--compuertas", str(goal_dir["ruta"])])
    assert rc == 0                                              # el respaldo por argumento


def test_stdin_roto_o_evento_raro_deniega(goal_dir):
    env = {hook.VAR_COMPUERTAS: str(goal_dir["ruta"])}
    assert hook.main(stdin=io.StringIO("{no json"), stdout=io.StringIO(), stderr=io.StringIO(),
                     argv=[], environ=env) == 2
    assert hook.main(stdin=io.StringIO(""), stdout=io.StringIO(), stderr=io.StringIO(),
                     argv=[], environ=env) == 2
    assert hook.main(stdin=io.StringIO(json.dumps({"hook_event_name": "PreToolUse",
                                                    "tool_name": "HerramientaNueva",
                                                    "tool_input": {}})),
                     stdout=io.StringIO(), stderr=io.StringIO(), argv=[], environ=env) == 2
    # StructuredOutput es la salida del --json-schema: pasa (no es una herramienta)
    assert hook.main(stdin=io.StringIO(json.dumps({"hook_event_name": "PreToolUse",
                                                    "tool_name": "StructuredOutput",
                                                    "tool_input": {"estado": "sigo"}})),
                     stdout=io.StringIO(), stderr=io.StringIO(), argv=[], environ=env) == 0


def test_un_error_interno_deniega(goal_dir, monkeypatch):
    monkeypatch.setattr(hook, "decidir", lambda *a, **k: 1 / 0)
    rc, err = correr(goal_dir, "Bash", {"command": "ls"})
    assert rc == 2 and "error interno" in err


def test_un_registro_que_no_se_puede_escribir_deniega(goal_dir):
    c = dict(goal_dir["compuertas"])
    c["registro"] = "/proc/no/se/puede/hook.jsonl"
    goal_dir["ruta"].write_text(json.dumps(c), encoding="utf-8")
    rc, err = correr(goal_dir, "Bash", {"command": "ls"})
    assert rc == 2


def test_como_proceso_real_con_json_roto_sale_2(goal_dir, tmp_path):
    """El interprete absoluto + el script, como lo invoca claude: un
    compuertas.json roto -> exit 2 y el motivo en stderr."""
    goal_dir["ruta"].write_text("{roto", encoding="utf-8")
    evento = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                         "tool_input": {"command": "ls"}, "tool_use_id": "t"})
    r = subprocess.run([sys.executable, str(HOOK)], input=evento, capture_output=True, text=True,
                       env={**os.environ, hook.VAR_COMPUERTAS: str(goal_dir["ruta"])}, timeout=20)
    assert r.returncode == 2 and "DENEGADO" in r.stderr
    # y la sonda del runner: gh pr create -> 2 con el JSON sano
    goal_dir["ruta"].write_text(json.dumps(goal_dir["compuertas"]), encoding="utf-8")
    evento = json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash",
                         "tool_input": {"command": "gh pr create --fill"}, "tool_use_id": "sonda"})
    r = subprocess.run([sys.executable, str(HOOK), "--compuertas", str(goal_dir["ruta"])],
                       input=evento, capture_output=True, text=True, env=dict(os.environ), timeout=20)
    assert r.returncode == 2 and "NUNCA" in r.stderr


def test_el_hook_no_importa_calipso():
    fuente = HOOK.read_text(encoding="utf-8")
    assert "from calipso" not in fuente and "import calipso" not in fuente


def test_familia_de_argv_es_pura(goal_dir):
    c = goal_dir["compuertas"]
    assert hook.familia_de_argv(["ls", "-la"], c) == (None, "comando simple permitido", None)
    assert hook.familia_de_argv(["gh", "pr", "create"], c)[0] == "NUNCA"
    f, _, forma = hook.familia_de_argv(["npm", "install", "-g", "x"], c)
    assert f == "instalar_home" and forma == {"argv": ["npm", "install", "-g", "x"]}
    f, _, forma = hook.familia_de_argv(["rm", "-rf", "/tmp/otro"], c)
    assert f == "borrar_fuera" and forma == {"ruta": "/tmp/otro"}
