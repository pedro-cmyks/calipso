#!/usr/bin/env python3
"""
test_github.py - GitHub remoto: parsing, overview y gating de contribucion.

No requiere `gh` ni red: inyecta un runner falso que devuelve salidas tipicas.
"""
from __future__ import annotations

import json

from calipso import github


def check(name: str, cond: bool, fails: list[str]) -> None:
    print(f"  [{'OK' if cond else 'FAIL'}] {name}")
    if not cond:
        fails.append(name)


def fake_gh(responses: dict[str, tuple[int, str, str]]):
    """Runner que matchea por prefijo de comando (sin el exe)."""
    def run(args: list[str]) -> tuple[int, str, str]:
        key = " ".join(args)
        for prefix, resp in responses.items():
            if key.startswith(prefix):
                return resp
        return (1, "", f"sin mock para: {key}")
    return run


def main() -> int:
    fails: list[str] = []

    # --- usuario autenticado ---
    gh = fake_gh({
        "gh api user": (0, json.dumps({"login": "pedro", "name": "Pedro"}), ""),
    })
    user = github.gh_user(gh)
    check("usuario autenticado parseado", user["authenticated"] and user["login"] == "pedro", fails)

    gh_no = fake_gh({"gh api user": (1, "", "not logged in")})
    user_no = github.gh_user(gh_no)
    check("no autenticado se reporta", user_no["authenticated"] is False, fails)

    # --- repos ---
    repos_json = json.dumps([
        {"nameWithOwner": "pedro/calipso", "description": "asistente",
         "isPrivate": True, "isFork": False, "updatedAt": "2026-06-01", "url": "u"},
        {"nameWithOwner": "pedro/fork", "description": None,
         "isPrivate": False, "isFork": True, "updatedAt": "2026-05-01", "url": "u2"},
    ])
    gh_repos = fake_gh({"gh repo list": (0, repos_json, "")})
    repos = github.list_repos(gh_repos)
    check("lista repos parseada", len(repos) == 2 and repos[0]["name"] == "pedro/calipso", fails)
    check("private/fork normalizados", repos[0]["private"] is True and repos[1]["fork"] is True, fails)

    # --- assigned ---
    issues_json = json.dumps([{"title": "bug login", "number": 7, "url": "iu",
                               "repository": {"nameWithOwner": "pedro/calipso"}}])
    gh_assigned = fake_gh({
        "gh search issues": (0, issues_json, ""),
        "gh search prs": (0, "[]", ""),
    })
    assigned = github.assigned_items(gh_assigned)
    check("issues asignados parseados", len(assigned["issues"]) == 1 and assigned["issues"][0]["repo"] == "pedro/calipso", fails)
    check("prs asignados vacios ok", assigned["prs"] == [], fails)

    # --- parse_remote ---
    https = github.parse_remote("https://github.com/pedro/calipso.git")
    ssh = github.parse_remote("git@github.com:pedro/calipso.git")
    none = github.parse_remote("https://gitlab.com/x/y.git")
    check("parse remote https", https and https["name"] == "pedro/calipso", fails)
    check("parse remote ssh", ssh and ssh["owner"] == "pedro", fails)
    check("remote no-github es None", none is None, fails)

    # --- overview ---
    git = fake_gh({
        "remote get-url origin": (0, "https://github.com/pedro/calipso.git\n", ""),
        "branch --show-current": (0, "main\n", ""),
    })
    gh_ov = fake_gh({
        "gh pr list": (0, json.dumps([
            {"number": 12, "title": "feat", "url": "pu",
             "headRefName": "feat-x", "isDraft": False}]), ""),
    })
    ov = github.repo_overview(gh_ov, git)
    check("overview detecta remoto", ov["has_github_remote"] and ov["remote"]["name"] == "pedro/calipso", fails)
    check("overview branch", ov["branch"] == "main", fails)
    check("overview PRs abiertos", len(ov["open_prs"]) == 1 and ov["open_prs"][0]["number"] == 12, fails)

    git_noremote = fake_gh({
        "remote get-url origin": (1, "", "no remote"),
        "branch --show-current": (0, "main\n", ""),
    })
    ov2 = github.repo_overview(gh_ov, git_noremote)
    check("sin remoto no consulta PRs", ov2["has_github_remote"] is False and ov2["open_prs"] == [], fails)

    # --- contribucion: planificar exige aprobacion, no ejecuta ---
    plan = github.plan_contribution("pr", {"title": "T", "body": "B", "draft": True})
    check("plan pr ok y requiere aprobacion", plan["ok"] and plan["requires_approval"] is True, fails)
    check("plan pr arma comando", "--draft" in plan["argv"] and "pr" in plan["argv"], fails)

    plan_branch = github.plan_contribution("branch", {"name": "fix-login"})
    check("plan branch arma git checkout -b", plan_branch["argv"] == ["git", "checkout", "-b", "fix-login"], fails)

    bad = github.plan_contribution("nuke")
    check("accion desconocida rechazada", bad["ok"] is False, fails)
    incomplete = github.plan_contribution("clone", {})
    check("clone sin repo rechazado", incomplete["ok"] is False, fails)

    if fails:
        print("\nFALLARON:", fails)
        return 1
    print("\nOK: GitHub remoto verificable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
