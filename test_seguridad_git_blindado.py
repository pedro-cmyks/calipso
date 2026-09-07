"""Revision de seguridad 2026-09-07, C1: todo git que corre sobre un repo
conmutable (ROOT del catastro) va blindado contra el .git/config del repo.
El vector (core.fsmonitor ejecuta comandos en un `git status` comun) esta
verificado y documentado en catastro.py; estos tests fijan que server._git
y el runner de gh llevan el mismo escudo y no vuelvan a divergir."""
import subprocess

import calipso.server as srv
from calipso import github


class _Captura:
    def __init__(self):
        self.args = None
        self.kwargs = None

    def __call__(self, args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")


def test_server_git_lleva_el_escudo(monkeypatch):
    cap = _Captura()
    monkeypatch.setattr(srv.subprocess, "run", cap)
    srv._git(["status", "--porcelain=v1"])
    assert cap.args[0] == "git"
    plano = " ".join(cap.args)
    assert "-c core.fsmonitor=" in plano
    assert "-c diff.external=" in plano
    assert "-c core.pager=cat" in plano
    assert cap.args[-2:] == ["status", "--porcelain=v1"]
    env = cap.kwargs.get("env")
    assert env is not None and env.get("GIT_CONFIG_GLOBAL") == "/dev/null"


def test_gh_runner_hereda_el_escudo_por_env(monkeypatch):
    cap = _Captura()
    monkeypatch.setattr(github, "_which_gh", lambda: "gh")
    monkeypatch.setattr(github.subprocess, "run", cap)
    runner = github.default_runner(cwd="/tmp")
    runner(["gh", "pr", "list"])
    env = cap.kwargs.get("env")
    assert env is not None
    assert env.get("GIT_CONFIG_GLOBAL") == "/dev/null"
    assert env.get("GIT_CONFIG_COUNT") == "3"
    claves = {env.get(f"GIT_CONFIG_KEY_{i}") for i in range(3)}
    assert claves == {"core.fsmonitor", "diff.external", "core.pager"}
    assert env.get("GIT_CONFIG_VALUE_0") == ""  # fsmonitor anulado
