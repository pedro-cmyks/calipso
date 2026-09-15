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

import contextlib
import json
import os
import pathlib
import re
import shutil
import subprocess
from typing import Any, Callable

from calipso import aduana

# runner(args) -> (returncode, stdout, stderr)
Runner = Callable[[list[str]], "tuple[int, str, str]"]

# git cruza SOLO con subcomando de red (spec seccion 7, ruling): rev-parse,
# log, status, remote get-url, branch son locales y no cruzan. La lista es
# negra (cruza lo listado) y por eso tiene que ser completa: una linea de
# mas es inocua -la aduana no frena-, una de menos rompe la invariante 1.
# Ademas de la porcelana obvia entran la plumbing de transporte y los
# subcomandos que mezclan verbos locales y de red (`submodule update`/`add`
# clonan; `svn`, `lfs`, `p4` hablan con su servidor): esos entran enteros.
# `remote` y `archive` son locales salvo por verbo o bandera: los resuelve
# `subcomando_git_de_red`.
GIT_DE_RED = ("fetch", "push", "pull", "clone", "ls-remote",
              "submodule", "svn", "lfs", "p4", "request-pull",
              "send-email", "imap-send",
              "fetch-pack", "send-pack", "http-fetch", "http-push")
# verbos de `git remote` que hablan con el remoto (`get-url`, `set-url`,
# `-v`, `add`, `remove`, `rename` son locales; `show` sin `-n` y `set-head
# -a` consultan)
GIT_REMOTE_DE_RED = ("update", "prune", "show", "set-head")
# opciones globales de git que llevan su valor en el token SIGUIENTE
# (git.c, handle_options). `--exec-path` no esta: solo imprime la ruta y
# sale, el valor va pegado (`--exec-path=/x`); `--super-prefix` no existe
# desde 2.40 pero era de dos tokens.
_GIT_OPCIONES_CON_VALOR = ("-c", "-C", "--git-dir", "--work-tree", "--namespace",
                           "--super-prefix", "--config-env", "--shallow-file",
                           "--attr-source")


def _which_gh() -> str | None:
    for name in ("gh.exe", "gh.cmd", "gh"):
        found = shutil.which(name)
        if found:
            return found
    return None


def env_git_blindado(anular_global: bool = True) -> dict:
    """El escudo por entorno contra el .git/config de un repo ajeno, para
    TODO proceso que corra git (directo o por dentro, como gh) sobre un cwd
    conmutable. GIT_CONFIG_COUNT inyecta config con la maxima precedencia
    -- equivalente a -c, pisa el config LOCAL del repo, y lo hereda
    cualquier git hijo -- para anular core.fsmonitor/diff.external/pager.
    Verificado empiricamente en la revision de seguridad 2026-09-07 (C1):
    sin esto, `git checkout -b` o un `git status` interno de gh ejecutan el
    comando que el repo declare. Un solo helper para que los runners no
    vuelvan a divergir.

    `anular_global=False` deja el ~/.gitconfig de Pedro en pie (ahi viven
    su user.name/user.email, el UNICO lugar): es lo que necesita un CLI
    agente que commitea legitimamente. El trio de GIT_CONFIG_COUNT alcanza
    para pisar el config LOCAL del repo hostil, que es el vector."""
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


def default_runner(cwd: str | None = None, timeout: int = 15,
                   *, quien: aduana.Quien) -> Runner:
    """Runner real que ejecuta `gh` (primer arg) buscandolo en PATH. Todo
    `gh` que pasa por aca es de red: el `with` de la aduana vive en el
    closure `run`, y el Quien queda capturado (la firma `Runner` no
    cambia). Sin `gh` en PATH devuelve 127 sin cruzar: no hubo salida."""
    exe = _which_gh()
    env = env_git_blindado()

    def run(args: list[str]) -> tuple[int, str, str]:
        if not exe:
            return (127, "", "gh no esta en PATH")
        sub = args[1:] if args and args[0] == "gh" else list(args)
        try:
            # el `except` queda afuera del cruce: la aduana anota `fallo`
            # (timeout, FileNotFoundError) y re-lanza; aca se traga como hoy
            with aduana.cruzar(quien, "gh " + " ".join(sub[:2]),
                               destino="api.github.com",
                               carga=["gh", *sub]) as cruce:
                proc = subprocess.run(
                    [exe, *sub],
                    cwd=cwd, env=env, text=True, capture_output=True,
                    encoding="utf-8", errors="replace", timeout=timeout)
                cruce.entro(len(proc.stdout or "") + len(proc.stderr or ""))
            return (proc.returncode, proc.stdout or "", proc.stderr or "")
        except Exception as e:  # pragma: no cover - depende del entorno
            return (1, "", str(e))

    return run


def _partir_git(args: list[str]) -> tuple[str | None, list[str]]:
    """(subcomando, lo que le sigue) de un argv de git: salta un `git`
    inicial (produccion no lo pasa; test_seguridad_git_blindado.py si), las
    opciones globales de un token (`--bare`, `--git-dir=/x`) y las de dos
    (`-c k=v`, `-C dir`, `--git-dir /x`: `_GIT_OPCIONES_CON_VALOR`). Sin
    las de dos tokens el valor se tomaria por subcomando y `--git-dir
    /x/.git fetch` saldria a la red sin linea."""
    resto = list(args[1:] if args and args[0] == "git" else args)
    while resto:
        a = resto.pop(0)
        if a in _GIT_OPCIONES_CON_VALOR:
            if resto:
                resto.pop(0)
            continue
        if a.startswith("-"):
            continue
        return a, resto
    return None, []


def subcomando_git(args: list[str]) -> str | None:
    """El subcomando de un argv de git (ver `_partir_git`)."""
    return _partir_git(args)[0]


def _verbo(resto: list[str]) -> str | None:
    """El primer token que no es opcion: el verbo de un subcomando compuesto
    (`remote -v update` -> `update`)."""
    return next((a for a in resto if not a.startswith("-")), None)


def subcomando_git_de_red(args: list[str]) -> str | None:
    """El proposito del cruce (`fetch`, `remote update`, `archive
    --remote`, `lfs fetch`) si el argv sale a la red; None si es local.
    `GIT_DE_RED` entra entero, con su verbo si lo tiene, para que el
    tablero diga `git submodule update` y no `git submodule`; `remote`
    solo con verbo de `GIT_REMOTE_DE_RED`; `archive` solo con `--remote`."""
    sub, resto = _partir_git(args)
    if sub is None:
        return None
    verbo = _verbo(resto)
    if sub in GIT_DE_RED:
        return f"{sub} {verbo}" if verbo and sub in ("submodule", "svn", "lfs", "p4") else sub
    if sub == "remote":
        return f"remote {verbo}" if verbo in GIT_REMOTE_DE_RED else None
    if sub == "archive" and any(a == "--remote" or a.startswith("--remote=") for a in resto):
        return "archive --remote"
    return None


def _destino_git(args: list[str]) -> str | None:
    """La URL del remoto si viene en el argv (`git clone https://...`,
    `archive --remote=git@...`); con un nombre (`origin`) el destino no se
    conoce y queda None."""
    for a in args:
        v = a.split("=", 1)[1] if a.startswith("--") and "=" in a else a
        if "://" in v or v.startswith("git@"):
            return v
    return None


def git_runner(cwd: str | None = None, timeout: int = 10,
               *, quien: aduana.Quien) -> Runner:
    """Cruza SOLO con subcomando de red (`subcomando_git_de_red`); lo local
    corre bajo `contextlib.nullcontext()`. El canario acepta el cruce
    condicional porque el Call a `aduana.cruzar` esta en el closure. Limite
    conocido: en un clon parcial (`--filter`) un `log -p` puede fetchear
    blobs del promisor sin pasar por aca; el ROOT de Calipso no lo es."""
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


def git_local(args: list[str], cwd: str | None = None,
              timeout: int = 120) -> tuple[int, str, str]:
    """git LOCAL para el clon del goal (spec 2026-09-13, ruling 15.4):
    clone de una ruta, checkout -b, diff --stat, fetch de una ruta local.
    NO va por `git_runner`: `clone`/`fetch` estan en GIT_DE_RED y un clon
    local cruzaria la aduana con destino None (Trampa 11), y `git_runner`
    anula el gitconfig global (sin identidad no hay commit desde el
    server). El escudo por entorno queda (core.fsmonitor, diff.external,
    core.pager). Entra al canario de la aduana como `git local:`."""
    exe = shutil.which("git.exe") or shutil.which("git")
    if not exe:
        return (127, "", "git no esta en PATH")
    env = env_git_blindado(anular_global=False)
    try:
        proc = subprocess.run(
            [exe, *args], cwd=cwd, env=env, text=True, capture_output=True,
            encoding="utf-8", errors="replace", timeout=timeout)
        return (proc.returncode, proc.stdout or "", proc.stderr or "")
    except Exception as e:
        return (1, "", str(e))


def clonar_para_goal(proyecto: str, destino: str, rama: str) -> dict:
    """`git clone --no-hardlinks <proyecto> <destino>` + `git checkout -b
    <rama>`. Siempre un clon, nunca un worktree (ruling 15.4: un worktree
    comparte .git, .venv y el checkout que sirve el server real). Copia
    REAL de los objetos: un clone local por defecto los enlaza (hardlink)
    con el origen, y el origen es el checkout que sirve el server; con el
    enlace, una escritura in-place sobre `.git/objects` desde un golpe
    corromperia el proyecto real (invariante 5). El .git de Calipso pesa
    unos MB: la copia cuesta lo mismo que el enlace. Un `destino` que ya
    existe es un error y NO se toca (un reintento tras un crash o la
    reconciliacion del arranque no puede llevarse el trabajo de los golpes
    anteriores); un fallo del clone no deja nada (git limpia lo que el
    mismo creo); un fallo del checkout borra el clon recien creado (ese
    si es nuestro). `error` lleva el stderr."""
    origen = pathlib.Path(proyecto).expanduser()
    if not (origen / ".git").exists():
        return {"ok": False, "clon": None, "rama": rama,
                "error": f"{origen} no es un repo git"}
    if pathlib.Path(destino).exists():
        return {"ok": False, "clon": None, "rama": rama,
                "error": f"{destino} ya existe"}
    rc, _, err = git_local(["clone", "--no-hardlinks", "--quiet", str(origen), destino])
    if rc != 0:
        return {"ok": False, "clon": None, "rama": rama, "error": err.strip() or f"git clone exit {rc}"}
    rc, _, err = git_local(["checkout", "-q", "-b", rama], cwd=destino)
    if rc != 0:
        shutil.rmtree(destino, ignore_errors=True)
        return {"ok": False, "clon": None, "rama": rama, "error": err.strip() or f"git checkout exit {rc}"}
    # la base de la rama del goal: el runner mide el diff de cada golpe
    # contra ella (no contra HEAD), asi un commit del martillo cuenta como
    # diff nuevo y el revisor ve el trabajo acumulado
    rc, out, _ = git_local(["rev-parse", "HEAD"], cwd=destino)
    base_sha = out.strip() if rc == 0 and out.strip() else None
    return {"ok": True, "clon": destino, "rama": rama, "error": None, "base_sha": base_sha}


def diff_stat(clon: str, base: str = "HEAD") -> str:
    """`git diff --stat <base>` mas los archivos sin seguimiento (uno por
    linea, `?? ruta`): lo que el martillo dejo en el clon tras el golpe.
    `base` es el `base_sha` de la rama del goal (el runner lo pasa): el
    contrato manda commitear al cerrar cada golpe, y contra HEAD un golpe
    que commiteo daria diff vacio (falsa no convergencia)."""
    rc, out, _ = git_local(["diff", "--stat", base], cwd=clon)
    partes = [out.strip()] if rc == 0 and out.strip() else []
    rc, out, _ = git_local(["status", "--porcelain", "--untracked-files=all"], cwd=clon)
    if rc == 0:
        sin = [l for l in out.splitlines() if l.startswith("??")]
        if sin:
            partes.append("\n".join(sin))
    return "\n".join(partes)


DIFF_COMPLETO_MAX = 60_000


def diff_completo(clon: str, maximo: int = DIFF_COMPLETO_MAX, base: str = "HEAD") -> str:
    """El diff REAL para el revisor (spec seccion 6.2 y ruling 15.1: 'el juez
    ve el diff real'): `git diff <base>` mas el contenido de cada archivo sin
    seguimiento (cabecera `?? ruta` y sus lineas con `+`), recortado a
    `maximo` caracteres con una marca. `base` como en `diff_stat` (el
    trabajo acumulado de la rama del goal, commits incluidos). `diff_stat`
    sigue siendo lo que va al ledger y al prompt del martillo.
    `--no-ext-diff` porque el escudo de `env_git_blindado` pone
    `diff.external=""` y con eso git 2.55 intenta correr un comando vacio
    para la salida en parche (`external diff died`, rc 128); `--stat` no
    pasa por ahi."""
    partes: list[str] = []
    rc, out, _ = git_local(["diff", "--no-ext-diff", base], cwd=clon)
    if rc == 0 and out.strip():
        partes.append(out.rstrip("\n"))
    rc, out, _ = git_local(["status", "--porcelain", "--untracked-files=all"], cwd=clon)
    if rc == 0:
        for l in out.splitlines():
            if not l.startswith("??"):
                continue
            ruta = l[3:].strip()
            try:
                contenido = (pathlib.Path(clon) / ruta).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            partes.append(f"?? {ruta}\n" + "\n".join("+" + x for x in contenido.splitlines()))
    texto = "\n".join(partes)
    if len(texto) > maximo:
        texto = texto[:maximo] + f"\n[... diff recortado a {maximo} caracteres]"
    return texto


def traer_rama(proyecto: str, clon: str, rama: str) -> tuple[int, str, str]:
    """Trae la rama del clon al repo de origen SIN mergear (`git fetch
    <clon> rama:rama`, ruta local, sin red): el merge es de Pedro
    (compuerta `merge`, pregunta)."""
    return git_local(["fetch", "--quiet", clon, f"{rama}:{rama}"], cwd=proyecto)


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
