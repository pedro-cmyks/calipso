#!/usr/bin/env python3
"""
test_commands.py - runner allowlist de comandos.
"""
import os
import pathlib
import subprocess
import tempfile

_HOME = tempfile.mkdtemp(prefix="calipso_commands_")
os.environ["CALIPSO_HOME"] = _HOME

from calipso import goals, jobs  # noqa: E402
from calipso.tools import commands  # noqa: E402


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True,
                   capture_output=True, text=True)


def main() -> int:
    fails = []

    def check(name, cond, extra=""):
        print(f"  [{'OK' if cond else 'FAIL'}] {name}{(' ' + extra) if extra else ''}")
        if not cond:
            fails.append(name)

    project = os.getcwd()
    allowed = commands.list_commands()
    check("lista comandos allowlist", any(c["id"] == "test_developer" for c in allowed))
    try:
        commands.run(project, "rm_rf")
        rejected = False
    except KeyError:
        rejected = True
    check("rechaza comando no permitido", rejected)

    goal = goals.create(project, "verificar Calipso")
    result = commands.run(project, "test_developer", goal["id"], timeout=120)
    job = result["job"]
    arts = jobs.artifacts(project, job["id"])
    updated = goals.load(project, goal["id"])
    stdout = jobs.read_artifact(project, job["id"], "stdout.txt").decode("utf-8")
    check("ejecuta comando permitido", result["status"] == "done" and result["returncode"] == 0)
    check("crea job command", job and job["kind"] == "command")
    check("artifacts stdout/result", {"stdout.txt", "result.json"}.issubset({a["name"] for a in arts}))
    check("stdout contiene OK", "OK: developer loop minimo funcionando" in stdout)
    check("evidencia en meta", updated and updated["evidence"][-1]["kind"] == "command")

    # --- el piso de ejecucion: un repo ajeno no puede correr SU test_ui.py
    # en vez del de Calipso, ni ejecutar codigo via su .git/config --------
    with tempfile.TemporaryDirectory(prefix="calipso_repo_ajeno_") as tmp:
        repo_ajeno = pathlib.Path(tmp)
        marcador_ui = repo_ajeno / "PRUEBA_TEST_UI_EJECUTADO"
        (repo_ajeno / "test_ui.py").write_text(
            "import pathlib\n"
            f"pathlib.Path({str(marcador_ui)!r}).write_text('si')\n")
        res_ui = commands.run(str(repo_ajeno), "ui_syntax")
        check("ui_syntax corre el test_ui.py de calipso, no el del repo abierto",
             not marcador_ui.exists())
        check("y el resultado es el de calipso (repo real, no el ajeno)",
             "OK: UI web" in res_ui["stdout"])

        _git(["init", "-q"], repo_ajeno)
        marcador_git = repo_ajeno / "PRUEBA_GIT_CONFIG_EJECUTADO"
        _git(["config", "core.fsmonitor", f"touch {marcador_git}; false"],
            repo_ajeno)
        commands.run(str(repo_ajeno), "git_status")
        check("git_status no ejecuta lo que declare .git/config del repo",
             not marcador_git.exists())

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: comandos allowlist funcionando")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
