#!/usr/bin/env python3
"""
calipso/github.py - GitHub remoto: repos, issues/PRs, repo actual y flujo de
contribucion.

Distingue tres planos (SPEC 4.6):
  - git local: lo maneja el servidor (`/api/git/*`).
  - GitHub remoto: repos, issues, PRs de la cuenta via `gh`.
  - flujo de contribucion: clonar, branch, fork, PR.

Politica (SPEC 11): leer es libre; clonar/branch/fork/PR/push exigen aprobacion
explicita. Por eso las acciones de escritura se *planifican* (devuelven el comando
y `requires_approval=True`) y solo se ejecutan con `confirm=True`.

El runner de `gh`/`git` se inyecta para poder probar sin red ni autenticacion.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any, Callable

# runner(args) -> (returncode, stdout, stderr)
Runner = Callable[[list[str]], "tuple[int, str, str]"]


def _which_gh() -> str | None:
    for name in ("gh.exe", "gh.cmd", "gh"):
        found = shutil.which(name)
        if found:
            return found
    return None


def env_git_blindado() -> dict:
    """El escudo por entorno contra el .git/config de un repo ajeno, para
    TODO proceso que corra git (directo o por dentro, como gh) sobre un cwd
    conmutable. GIT_CONFIG_COUNT inyecta config con la maxima precedencia
    -- equivalente a -c, pisa el config LOCAL del repo, y lo hereda
    cualquier git hijo -- para anular core.fsmonitor/diff.external/pager.
    Verificado empiricamente en la revision de seguridad 2026-09-07 (C1):
    sin esto, `git checkout -b` o un `git status` interno de gh ejecutan el
    comando que el repo declare. Un solo helper para que los runners no
    vuelvan a divergir."""
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    for i, (k, v) in enumerate((("core.fsmonitor", ""),
                                ("diff.external", ""),
                                ("core.pager", "cat"))):
        env[f"GIT_CONFIG_KEY_{i}"] = k
        env[f"GIT_CONFIG_VALUE_{i}"] = v
    env["GIT_CONFIG_COUNT"] = "3"
    return env


def default_runner(cwd: str | None = None, timeout: int = 15) -> Runner:
    """Runner real que ejecuta `gh` (primer arg) buscandolo en PATH."""
    exe = _which_gh()
    env = env_git_blindado()

    def run(args: list[str]) -> tuple[int, str, str]:
        if not exe:
            return (127, "", "gh no esta en PATH")
        try:
            proc = subprocess.run(
                [exe, *args[1:]] if args and args[0] == "gh" else [exe, *args],
                cwd=cwd, env=env, text=True, capture_output=True,
                encoding="utf-8", errors="replace", timeout=timeout)
            return (proc.returncode, proc.stdout or "", proc.stderr or "")
        except Exception as e:  # pragma: no cover - depende del entorno
            return (1, "", str(e))

    return run


def git_runner(cwd: str | None = None, timeout: int = 10) -> Runner:
    exe = shutil.which("git.exe") or shutil.which("git")
    env = env_git_blindado()

    def run(args: list[str]) -> tuple[int, str, str]:
        if not exe:
            return (127, "", "git no esta en PATH")
        try:
            proc = subprocess.run(
                [exe, *args], cwd=cwd, env=env, text=True,
                capture_output=True,
                encoding="utf-8", errors="replace", timeout=timeout)
            return (proc.returncode, proc.stdout or "", proc.stderr or "")
        except Exception as e:  # pragma: no cover
            return (1, "", str(e))

    return run


def _json(stdout: str, fallback: Any) -> Any:
    try:
        return json.loads(stdout)
    except Exception:
        return fallback


def available() -> bool:
    return _which_gh() is not None


def gh_user(run: Runner) -> dict[str, Any]:
    """Usuario autenticado. {authenticated, login, name, error}."""
    code, out, err = run(["gh", "api", "user", "--jq",
                          "{login: .login, name: .name}"])
    if code != 0:
        return {"authenticated": False, "login": None, "name": None,
                "error": (err or out or "no autenticado").strip().splitlines()[0]
                if (err or out).strip() else "no autenticado"}
    data = _json(out, {})
    login = data.get("login")
    return {
        "authenticated": bool(login),
        "login": login,
        "name": data.get("name"),
        "error": "" if login else "respuesta inesperada de gh",
    }


def list_repos(run: Runner, limit: int = 10) -> list[dict[str, Any]]:
    fields = "nameWithOwner,description,isPrivate,updatedAt,url,isFork"
    code, out, _ = run(["gh", "repo", "list", "--limit", str(limit),
                        "--json", fields])
    if code != 0:
        return []
    repos = _json(out, [])
    return [
        {
            "name": r.get("nameWithOwner"),
            "description": (r.get("description") or "").strip(),
            "private": bool(r.get("isPrivate")),
            "fork": bool(r.get("isFork")),
            "updated_at": r.get("updatedAt"),
            "url": r.get("url"),
        }
        for r in repos if isinstance(r, dict)
    ]


def assigned_items(run: Runner, limit: int = 10) -> dict[str, list[dict[str, Any]]]:
    """Issues y PRs abiertos asignados a la cuenta autenticada."""
    def search(kind: str) -> list[dict[str, Any]]:
        code, out, _ = run([
            "gh", "search", kind, "--assignee", "@me", "--state", "open",
            "--limit", str(limit), "--json", "title,number,url,repository"])
        if code != 0:
            return []
        items = _json(out, [])
        result = []
        for it in items:
            if not isinstance(it, dict):
                continue
            repo = it.get("repository") or {}
            result.append({
                "title": it.get("title"),
                "number": it.get("number"),
                "url": it.get("url"),
                "repo": repo.get("nameWithOwner") if isinstance(repo, dict) else None,
            })
        return result

    return {"issues": search("issues"), "prs": search("prs")}


def parse_remote(url: str) -> dict[str, Any] | None:
    """Extrae owner/repo de un remote de GitHub (https o ssh)."""
    url = (url or "").strip()
    if not url:
        return None
    m = re.search(r"github\.com[/:]([^/]+)/(.+?)(?:\.git)?/?$", url)
    if not m:
        return None
    return {"owner": m.group(1), "repo": m.group(2),
            "name": f"{m.group(1)}/{m.group(2)}"}


def repo_overview(gh: Runner, git: Runner) -> dict[str, Any]:
    """Repo local + remoto GitHub + PRs abiertos relacionados."""
    code, out, _ = git(["remote", "get-url", "origin"])
    remote = parse_remote(out) if code == 0 else None
    branch_code, branch_out, _ = git(["branch", "--show-current"])
    branch = branch_out.strip() if branch_code == 0 else None
    overview: dict[str, Any] = {
        "has_github_remote": bool(remote),
        "remote": remote,
        "branch": branch or None,
        "open_prs": [],
    }
    if not remote:
        return overview
    code, out, _ = gh(["gh", "pr", "list", "--json",
                       "number,title,url,headRefName,isDraft", "--limit", "20"])
    if code == 0:
        prs = _json(out, [])
        overview["open_prs"] = [
            {
                "number": p.get("number"),
                "title": p.get("title"),
                "url": p.get("url"),
                "branch": p.get("headRefName"),
                "draft": bool(p.get("isDraft")),
            }
            for p in prs if isinstance(p, dict)
        ]
    return overview


# --------------------------------------------------------------------------
# Flujo de contribucion: planificar (seguro) vs ejecutar (con confirm).
# --------------------------------------------------------------------------

CONTRIB_ACTIONS = {
    "clone": {
        "requires_approval": True,
        "reason": "clona un repo (escribe fuera del proyecto activo)",
    },
    "branch": {
        "requires_approval": True,
        "reason": "crea una branch local nueva",
    },
    "fork": {
        "requires_approval": True,
        "reason": "crea un fork en tu cuenta de GitHub",
    },
    "pr": {
        "requires_approval": True,
        "reason": "abre un pull request",
    },
}


def _build_command(action: str, opts: dict[str, Any]) -> list[str]:
    if action == "clone":
        repo = opts.get("repo", "")
        cmd = ["gh", "repo", "clone", repo]
        if opts.get("dir"):
            cmd.append(opts["dir"])
        return cmd
    if action == "branch":
        return ["git", "checkout", "-b", opts.get("name", "")]
    if action == "fork":
        return ["gh", "repo", "fork", "--clone=false"]
    if action == "pr":
        cmd = ["gh", "pr", "create", "--title", opts.get("title", ""),
               "--body", opts.get("body", "")]
        if opts.get("draft"):
            cmd.append("--draft")
        if opts.get("base"):
            cmd += ["--base", opts["base"]]
        return cmd
    return []


def plan_contribution(action: str, opts: dict[str, Any] | None = None) -> dict[str, Any]:
    """Devuelve el comando a ejecutar SIN ejecutarlo. Nunca pushea/forkea solo."""
    opts = opts or {}
    meta = CONTRIB_ACTIONS.get(action)
    if not meta:
        return {"ok": False, "error": f"accion no soportada: {action}"}
    cmd = _build_command(action, opts)
    if not cmd or not all(cmd):
        return {"ok": False, "error": "faltan datos para la accion"}
    return {
        "ok": True,
        "action": action,
        "command": " ".join(cmd),
        "argv": cmd,
        "requires_approval": meta["requires_approval"],
        "reason": meta["reason"],
    }
