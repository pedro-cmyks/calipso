"""Revision de seguridad 2026-09-07, C1 (+fix round): todo git que corre
sobre un repo conmutable (ROOT del catastro) va blindado contra el
.git/config y el .gitattributes del repo. Ademas de fijar banderas y env,
estos tests incluyen el CANARIO REAL (el molde de test_catastro): un repo
hostil de verdad, con control positivo que demuestra que el canario canta
sin el escudo."""
import pathlib
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


# --- forma: banderas y env ---------------------------------------------------

def test_server_git_lleva_el_escudo(monkeypatch):
    cap = _Captura()
    monkeypatch.setattr(srv.subprocess, "run", cap)
    srv._git(["status", "--porcelain=v1"])
    plano = " ".join(cap.args)
    assert "-c core.fsmonitor=" in plano
    assert "-c diff.external=" in plano
    assert "-c core.pager=cat" in plano
    env = cap.kwargs.get("env")
    assert env is not None and env.get("GIT_CONFIG_GLOBAL") == "/dev/null"


def test_env_blindado_pares_clave_valor():
    env = github.env_git_blindado()
    assert env.get("GIT_CONFIG_COUNT") == "3"
    assert env.get("GIT_CONFIG_GLOBAL") == "/dev/null"
    assert env.get("GIT_CONFIG_SYSTEM") == "/dev/null"
    pares = {env[f"GIT_CONFIG_KEY_{i}"]: env[f"GIT_CONFIG_VALUE_{i}"]
             for i in range(3)}
    assert pares == {"core.fsmonitor": "", "diff.external": "",
                     "core.pager": "cat"}


def test_los_dos_runners_de_github_llevan_el_env(monkeypatch):
    cap = _Captura()
    monkeypatch.setattr(github, "_which_gh", lambda: "gh")
    monkeypatch.setattr(github.subprocess, "run", cap)
    github.default_runner(cwd="/tmp")(["gh", "pr", "list"])
    assert cap.kwargs["env"].get("GIT_CONFIG_COUNT") == "3"
    github.git_runner(cwd="/tmp")(["git", "branch", "--show-current"])
    assert cap.kwargs["env"].get("GIT_CONFIG_COUNT") == "3"


# --- el canario real ---------------------------------------------------------

def _repo_hostil(tmp_path):
    """Un repo con core.fsmonitor que toca un marker: si el marker aparece,
    el comando del repo se ejecuto."""
    repo = tmp_path / "hostil"
    repo.mkdir()
    marker = tmp_path / "marker"
    subprocess.run(["git", "init", "-q", str(repo)], check=True,
                   capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "core.fsmonitor",
                    f"touch {marker}; false"], check=True,
                   capture_output=True)
    (repo / "a.txt").write_text("hola\n", encoding="utf-8")
    return repo, marker


def test_canario_fsmonitor_control_positivo_y_escudo(tmp_path, monkeypatch):
    repo, marker = _repo_hostil(tmp_path)
    # control positivo: SIN escudo, el status ejecuta el payload
    subprocess.run(["git", "status", "--porcelain=v1"], cwd=str(repo),
                   capture_output=True)
    assert marker.exists(), "el canario no canta: fsmonitor no disparo ni sin escudo"
    marker.unlink()
    # con el escudo de server._git, no
    monkeypatch.setattr(srv, "ROOT", repo)
    r = srv._git(["status", "--porcelain=v1"])
    assert r.returncode == 0
    assert not marker.exists()


def test_canario_env_blindado_pisa_config_local(tmp_path):
    repo, marker = _repo_hostil(tmp_path)
    subprocess.run(["git", "checkout", "-qb", "rama"], cwd=str(repo),
                   env=github.env_git_blindado(), capture_output=True)
    assert not marker.exists()


def test_canario_diff_driver_no_dispara(tmp_path, monkeypatch):
    repo, marker = _repo_hostil(tmp_path)
    marker2 = tmp_path / "marker2"
    subprocess.run(["git", "-C", str(repo), "config", "diff.evil.command",
                    f"touch {marker2}"], check=True, capture_output=True)
    (repo / ".gitattributes").write_text("*.txt diff=evil\n", encoding="utf-8")
    ident = ["-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(["git", "-C", str(repo), *ident, "-c", "core.fsmonitor=",
                    "add", "-A"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), *ident, "-c", "core.fsmonitor=",
                    "commit", "-qm", "x"], check=True, capture_output=True)
    (repo / "a.txt").write_text("cambiado\n", encoding="utf-8")
    # control positivo: un diff desnudo (solo con el escudo viejo de -c)
    # ejecuta el driver
    subprocess.run(["git", "-c", "core.fsmonitor=", "-c", "diff.external=",
                    "-c", "core.pager=cat", "diff", "--", "a.txt"],
                   cwd=str(repo), capture_output=True)
    assert marker2.exists(), "el canario no canta: el driver no disparo sin --no-ext-diff"
    marker2.unlink()
    # el endpoint parcheado (via api_git_diff -> --no-ext-diff) no lo dispara
    monkeypatch.setattr(srv, "ROOT", repo)
    out = srv.api_git_diff(path=None)
    assert not marker2.exists()
    assert "diff" in out


def test_tripwire_sumideros_de_la_ui_escapados():
    """C5: los sumideros nombrados por la revision quedan con esc(). Un
    refactor que los devuelva a interpolacion cruda rompe este test."""
    html = (pathlib.Path(__file__).parent / "calipso" / "web"
            / "index.html").read_text(encoding="utf-8")
    crudos = ["<span>${name}</span>", ">${p.path}</span>",
              ">${f.path}</span>", "<summary>${title}</summary>",
              'data-plugin="${p.name}"']
    for patron in crudos:
        assert patron not in html, f"sumidero sin esc(): {patron}"
    assert "${esc(name)}" in html
    assert "<summary>${esc(title)}</summary>" in html
