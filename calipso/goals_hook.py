#!/usr/bin/env python3
"""
calipso/goals_hook.py - el hook PreToolUse del goal (spec 2026-09-13,
seccion 7, ruling 15.5): la SEGUNDA capa detras del sandbox nativo de Claude
Code. Stdlib puro (no importa calipso: si el repo esta roto, el hook sigue
denegando), interprete absoluto, y FAIL-CLOSED: cualquier error -- stdin
ilegible, JSON de compuertas ausente o roto, registro que no se puede
escribir, una excepcion propia -- es exit 2 con el motivo en stderr, que es
lo unico que Claude Code trata como bloqueo (terreno A.4: "Exit code 2 -
show stderr to model and block tool call"; cualquier otro exit deja pasar).

Que decide:
  Bash      ALLOW-LIST de comandos simples (ALLOW_EXES, los ejecutables del
            clon y de su venv); deniega lo que no sabe parsear (compuestos:
            `;`, `&&`, `||`, `|`, `$(`, backticks, redirecciones; heredocs;
            envoltorios: bash -c, sh -c, eval, source, xargs, env, nohup,
            setsid, find -exec/-delete; git -C, --git-dir, worktree,
            update-ref, branch -D, remote, fetch, pull, clone, config); lo
            NUNCA (gh, git push, sudo, pkexec, su, rpm-ostree
            rebase|reset|rollback, flatpak remote-delete|remote-modify,
            mail, sendmail, rm o cat sobre las rutas protegidas -- tambien
            por glob (`~/.ss*`: se expande aca como lo haria bash), como
            valor de una opcion (`--directory=~/.ssh`, `-C~/.ssh`) o como
            archivo que curl/wget subirian (`-T`, `-d @`, `-F x=@`); una
            variable en una ruta (`/var/home/$USER/.ssh`) se deniega porque
            bash la expande despues del hook); y las
            compuertas por familia con la tabla del goal (instalar_en_goal
            directo dentro del venv del clon / npm sin -g; instalar_home,
            instalar_sistema, borrar_fuera en pregunta salvo preautorizada).
  Edit/Write/MultiEdit  dentro del clon o de una raiz declarada; nunca
            `.claude/`, `.git/hooks/`, `.git/config` del clon (el martillo no
            se auto-escala); fuera = pregunta raiz_nueva.
  Read/Glob/Grep  todo salvo las rutas protegidas (NUNCA). El resto del
            confinamiento lo hace `--restricted` (los file tools no salen de
            los working directories).
  WebFetch/WebSearch  solo con dominios declarados; el host tiene que estar
            en la lista (son in-process: el sandbox no las filtra, Trampa 8).

La tabla del goal llega por un JSON (`compuertas.json`, lo escribe
goals.escribir_compuertas) cuya ruta viene en la variable de entorno
CALIPSO_GOAL_COMPUERTAS del proceso claude (el hook la hereda) o, de
respaldo, en `--compuertas <ruta>`. Cada decision se anota en el
`registro` (hook.jsonl del goal): el runner lo lee para el ledger y la
aduana.

Salida: permitir = exit 0 sin stdout (bajo --restricted un `allow` del hook
se ignora igual: "a confined session takes grants only from its command
line"); denegar = una linea `goal_hook: DENEGADO (...)` en stderr y exit 2.
"""
from __future__ import annotations

import datetime
import fnmatch
import json
import os
import pathlib
import shlex
import sys

VAR_COMPUERTAS = "CALIPSO_GOAL_COMPUERTAS"

# Las rutas de Pedro que NUNCA se leen ni se borran desde un golpe
# (permisos/acciones.py:176-183 mas ~/.claude, ~/.codex, ~/.calipso).
PROTEGIDAS = ("~/.ssh", "~/.gnupg", "~/.aws", "~/.config/gh", "~/.claude", "~/.codex",
              "~/.calipso", "~/.local/share/keyrings", "~/.password-store")
NUNCA_EXES = {"sudo", "pkexec", "doas", "su", "gh", "mail", "sendmail", "mutt"}
COMPUESTOS = (";", "&&", "||", "|", "$(", "`", ">", "<", "<<", "&")
ENVOLTORIOS = {"bash", "sh", "zsh", "dash", "fish", "eval", "source", ".", "xargs", "env",
               "nohup", "setsid", "exec", "command", "builtin", "watch", "script", "ssh",
               "scp", "sftp", "rsync", "nc", "ncat", "telnet"}
# Comandos simples que no salen del clon ni tocan el sistema. Todo lo demas
# (salvo las familias de abajo) se deniega: la lista es blanca a proposito.
ALLOW_EXES = {
    "ls", "cat", "head", "tail", "wc", "grep", "rg", "find", "sed", "awk", "cut", "sort", "uniq",
    "tr", "echo", "printf", "pwd", "mkdir", "touch", "cp", "mv", "diff", "which", "true", "false",
    "test", "[", "stat", "file", "basename", "dirname", "realpath", "readlink", "date", "sleep",
    "tee", "tree", "du", "df", "ps", "python", "python3", "pytest", "node", "npx", "cargo", "go",
    "make", "cmake", "gcc", "g++", "cc", "rustc", "ruby", "bundle", "black", "ruff", "mypy",
    "flake8", "isort", "pyright", "tsc", "eslint", "prettier", "jq", "tar", "unzip", "zip",
    "gzip", "gunzip", "sha256sum", "md5sum", "chmod", "ln", "seq", "xxd", "hexdump", "less",
    "more", "yes", "nproc", "uname", "id", "whoami", "hostname", "uv", "poetry", "pipx", "rm",
    "git", "pip", "pip3", "npm", "yarn", "pnpm", "flatpak", "rpm-ostree", "curl", "wget",
}
GIT_PERMITIDOS = {"status", "diff", "log", "show", "add", "commit", "checkout", "switch",
                  "restore", "branch", "stash", "rev-parse", "ls-files", "mv", "rm", "tag",
                  "merge", "rebase", "reset", "blame", "grep", "describe", "shortlog", "cherry-pick",
                  "revert", "clean", "init", "apply", "format-patch", "diff-tree", "cat-file",
                  "rev-list", "name-rev", "symbolic-ref"}
GIT_PROHIBIDOS = {"push", "fetch", "pull", "clone", "remote", "worktree", "update-ref", "config",
                  "submodule", "lfs", "svn", "p4", "ls-remote", "send-email", "request-pull",
                  "gc", "reflog", "filter-branch", "replace", "notes", "daemon", "instaweb",
                  "credential", "credential-store", "credential-cache", "archive", "bundle"}
GIT_OPCIONES_PROHIBIDAS = ("-C", "--git-dir", "--work-tree", "--exec-path", "-c", "--config-env",
                           "--namespace")
# Los ejecutables que miran rutas: cada token con pinta de ruta pasa por las
# protegidas (NUNCA) y, los que escriben, por la auto-escalada. curl/wget
# ademas: el archivo que subirian es un dato de Pedro antes que un hecho web.
EXES_DE_RUTAS = ("cat", "head", "tail", "less", "more", "cp", "mv", "ln", "tar", "zip", "sed", "awk",
                 "grep", "rg", "find", "stat", "file", "wc", "xxd", "hexdump")
EXES_QUE_TOCAN = ("touch", "tee", "mkdir", "chmod")
EXES_QUE_ESCRIBEN = ("cp", "mv", "ln", "sed") + EXES_QUE_TOCAN
SUBEN_ARCHIVOS = ("curl", "wget")
# Un glob o una variable en un token con pinta de ruta: bash los expande
# DESPUES del hook (el hook ve `~/.ss*`, bash corre `cat ~/.ssh`). El glob se
# expande aca como lo haria bash, acotado; la variable no se ve adonde apunta.
GLOB = "*?["
MAX_MATCHES = 256
DOMINIO_API = "api.anthropic.com"
INSTRUCCION_PREGUNTA = ("esta compuerta esta en pregunta: pedila en tu veredicto con estado "
                        "\"preguntar\" y la compuerta (familia y forma); Pedro decide")


class Decision:
    __slots__ = ("permitir", "motivo", "familia", "forma")

    def __init__(self, permitir: bool, motivo: str, familia: str | None = None,
                 forma: dict | None = None) -> None:
        self.permitir = permitir
        self.motivo = motivo
        self.familia = familia
        self.forma = forma


# --------------------------------------------------------------------------
# rutas
# --------------------------------------------------------------------------

def _resolver(ruta: str, cwd: str | None) -> pathlib.Path:
    p = pathlib.Path(os.path.expanduser(str(ruta)))
    if not p.is_absolute() and cwd:
        p = pathlib.Path(cwd) / p
    try:
        return p.resolve(strict=False)
    except OSError:
        return p


def _dentro(hijo: pathlib.Path, padre: pathlib.Path) -> bool:
    return hijo == padre or padre in hijo.parents


def _bajo_protegida(p: pathlib.Path) -> bool:
    """Dentro de una de PROTEGIDAS (el home y `/` a secas solo estan
    protegidos como ruta exacta: lo que cuelga de ellos no)."""
    return any(_dentro(p, pathlib.Path(os.path.expanduser(x)).resolve()) for x in PROTEGIDAS)


def _protegida(p: pathlib.Path) -> bool:
    home = pathlib.Path(os.path.expanduser("~")).resolve()
    if p == home or p == pathlib.Path("/"):
        return True
    return _bajo_protegida(p)


def _pinta_de_ruta(tok: str) -> bool:
    return "/" in tok or tok.startswith(("~", "."))


def _tiene_variable(tok: str) -> bool:
    """Un `$` que bash expandiria: seguido de letra, digito, `_`, `{` o un
    parametro especial. `foo$` o `a/$` (el ancla de sed y grep) no."""
    i = tok.find("$")
    while i != -1:
        sig = tok[i + 1:i + 2]
        if sig and (sig.isalnum() or sig in "_{@*#?!$-"):
            return True
        i = tok.find("$", i + 1)
    return False


def _expandir(patron: str, cwd: str | None) -> list[pathlib.Path] | None:
    """Los matches de un glob como los haria bash sin nullglob ni dotglob
    (`*` y `?` no ven los dotfiles salvo que el segmento empiece con `.`;
    `.` y `..` nunca, como bash 5.2 con globskipdots): rutas resueltas, o el
    literal si no hay match. No entra en una ruta protegida (la devuelve tal
    cual: lo de adentro ya es NUNCA y no hace falta listarlo). None si el
    glob abre mas de MAX_MATCHES rutas: no se sabe que abarca."""
    texto = os.path.expanduser(patron)
    base = pathlib.Path("/") if texto.startswith("/") else pathlib.Path(cwd or ".")
    candidatos = [base]
    for seg in [s for s in texto.split("/") if s]:
        nuevos: list[pathlib.Path] = []
        for c in candidatos:
            if _bajo_protegida(_resolver(str(c), cwd)):
                nuevos.append(c)
            elif not any(ch in seg for ch in GLOB):
                nuevos.append(c / seg)
            else:
                try:
                    hijos = sorted(os.listdir(c))
                except OSError:
                    continue
                nuevos.extend(c / h for h in hijos
                              if (seg.startswith(".") or not h.startswith("."))
                              and fnmatch.fnmatchcase(h, seg))
        if len(nuevos) > MAX_MATCHES:
            return None
        candidatos = nuevos
        if not candidatos:
            break
    return [_resolver(str(c), cwd) for c in candidatos] or [_resolver(patron, cwd)]


def _auto_escalada(p: pathlib.Path, compuertas: dict) -> bool:
    """`.claude/`, `.git/hooks/`, `.git/config` del clon (o del cwd): escribir
    ahi es darse permisos o colgar un hook propio."""
    for base in (compuertas.get("clon"), compuertas.get("cwd")):
        if not base:
            continue
        b = pathlib.Path(base).resolve()
        if _dentro(p, b / ".claude") or _dentro(p, b / ".git" / "hooks") or p == b / ".git" / "config":
            return True
    return False


def _en_alcance(p: pathlib.Path, compuertas: dict) -> str | None:
    """`repo` si esta en el clon/cwd, `raices` si esta en una raiz declarada,
    None si no."""
    for base in (compuertas.get("clon"), compuertas.get("cwd")):
        if base and _dentro(p, pathlib.Path(base).resolve()):
            return "repo"
    for r in compuertas.get("raices") or []:
        if _dentro(p, pathlib.Path(os.path.expanduser(r)).resolve()):
            return "raices"
    return None


def _host(url: str) -> str:
    sin = url.split("://", 1)[1] if "://" in url else url
    return sin.split("/", 1)[0].split("@")[-1].split(":")[0].lower()


def _dominio_permitido(url: str, compuertas: dict) -> bool:
    h = _host(url)
    if not h:
        return False
    if h == DOMINIO_API:
        return True
    for d in compuertas.get("dominios") or []:
        d = str(d).lower()
        if d.endswith("*"):
            if h.startswith(d[:-1]):
                return True
        elif h == d or h.endswith("." + d):
            return True
    return False


# --------------------------------------------------------------------------
# Bash
# --------------------------------------------------------------------------

def partir(comando: str) -> list[str] | None:
    """argv de un comando SIMPLE; None si esta vacio, es compuesto, tiene
    heredoc/redireccion/subshell o no se puede tokenizar. Se mira el texto
    ANTES de shlex (shlex se come los operadores)."""
    texto = (comando or "").strip()
    if not texto or "\n" in texto:
        return None
    for op in COMPUESTOS:
        if op in texto:
            return None
    try:
        argv = shlex.split(texto)
    except ValueError:
        return None
    if not argv:
        return None
    for tok in argv:
        if "$(" in tok or "`" in tok or tok.startswith("$"):
            return None
    return argv


def _flags_cortas(argv: list[str]) -> str:
    return "".join(x[1:] for x in argv if x.startswith("-") and not x.startswith("--"))


def _candidatos_de_ruta(exe: str, argv: list[str]) -> list[str]:
    """Los tokens de argv[1:] que pueden ser una ruta: los que no son
    opcion, el valor de `--opcion=valor` y lo pegado a una opcion corta
    (`-C/x`); para curl/wget, ademas, lo que sigue a `@` (`-d @archivo`,
    `-F campo=@archivo`) y nunca las URLs (esas van por dominio)."""
    out = []
    for tok in argv[1:]:
        if exe in SUBEN_ARCHIVOS and "://" in tok:
            continue
        if tok.startswith("--"):
            val = tok.split("=", 1)[1] if "=" in tok else ""
        elif tok.startswith("-"):
            val = tok[2:]
        else:
            val = tok
        if exe in SUBEN_ARCHIVOS:
            if "=@" in val:
                val = val.split("=@", 1)[1]
            if val.startswith("@"):
                val = val[1:]
        if val:
            out.append(val)
    return out


def _rutas_resueltas(exe: str, argv: list[str], cwd: str | None) -> tuple[list[pathlib.Path], str | None]:
    """(rutas resueltas, motivo para DENEGAR). Un token con pinta de ruta
    (lleva `/` o empieza con `~` o `.`) con una variable adentro se deniega:
    bash la expande despues del hook y no se ve adonde apunta; con un glob
    se expande aca y entra cada match (o el literal si no hay ninguno)."""
    rutas: list[pathlib.Path] = []
    for tok in _candidatos_de_ruta(exe, argv):
        if _pinta_de_ruta(tok):
            if _tiene_variable(tok):
                return [], f"{exe}: variable en la ruta {tok}, no se ve adonde apunta"
            if any(ch in tok for ch in GLOB):
                matches = _expandir(tok, cwd)
                if matches is None:
                    return [], f"{exe}: el glob {tok} abre mas de {MAX_MATCHES} rutas"
                rutas.extend(matches)
                continue
        rutas.append(_resolver(tok, cwd))
    return rutas, None


def _exe_de(argv: list[str], compuertas: dict) -> tuple[str, str]:
    """(nombre del ejecutable, 'venv'|'clon'|'sistema'|'ruta_fuera')."""
    tok = argv[0]
    nombre = pathlib.Path(tok).name
    if "/" in tok:
        p = _resolver(tok, compuertas.get("cwd"))
        venv = compuertas.get("venv")
        if venv and _dentro(p, pathlib.Path(venv).resolve()):
            return nombre, "venv"
        if _en_alcance(p, compuertas) == "repo":
            return nombre, "clon"
        return nombre, "ruta_fuera"
    return nombre, "sistema"


def _familia_git(argv: list[str]) -> tuple[str | None, str, dict | None]:
    resto = argv[1:]
    for tok in resto:
        if tok in GIT_OPCIONES_PROHIBIDAS or any(tok.startswith(o + "=") for o in GIT_OPCIONES_PROHIBIDAS):
            return "DENEGAR", f"git con {tok}: sale del clon", None
    sub = next((t for t in resto if not t.startswith("-")), None)
    if sub == "push":
        return "NUNCA", "git push: el push lo hace Calipso con el dale de Pedro (compuerta push)", None
    if sub in GIT_PROHIBIDOS or sub is None:
        return "DENEGAR", f"git {sub}: fuera del allow-list del clon", None
    if sub == "branch" and any(t in ("-D", "-d", "--delete") for t in resto):
        return "DENEGAR", "git branch -D: fuera del allow-list", None
    if sub not in GIT_PERMITIDOS:
        return "DENEGAR", f"git {sub}: fuera del allow-list del clon", None
    return None, f"git {sub} en el clon", None


def familia_de_argv(argv: list[str], compuertas: dict) -> tuple[str | None, str, dict | None]:
    """(familia, motivo, forma). familia None = comando simple permitido;
    "NUNCA" = lo que no se hace jamas; "DENEGAR" = no se sabe parsear o no
    esta en el allow-list; una familia de la tabla = una compuerta con su
    forma concreta (ruling 15.11)."""
    if not argv:
        return "DENEGAR", "comando vacio", None
    exe, donde = _exe_de(argv, compuertas)
    if exe in NUNCA_EXES:
        return "NUNCA", f"{exe}: publicar/gastar/correo/escalar no se hace desde un golpe", None
    if exe in ENVOLTORIOS:
        return "DENEGAR", f"{exe}: envoltorio, no se ve adentro", None
    if exe in ("python", "python3", "node", "ruby", "perl") and any(t in ("-c", "-e") for t in argv[1:3]):
        return "DENEGAR", f"{exe} -c/-e: no se ve adentro", None
    if donde == "ruta_fuera":
        return "DENEGAR", f"{argv[0]}: ejecutable fuera del clon y de su venv", None
    cwd = compuertas.get("cwd")
    if exe == "git":
        return _familia_git(argv)
    if exe == "rm":
        rutas, motivo = _rutas_resueltas(exe, argv, cwd)
        if motivo:
            return "DENEGAR", motivo, None
        for p in rutas:
            if _protegida(p):
                return "NUNCA", f"rm sobre {p}: datos de Pedro", {"ruta": str(p)}
            if _auto_escalada(p, compuertas):
                return "DENEGAR", f"rm sobre {p}: auto-escalada", None
        for p in rutas:
            if _en_alcance(p, compuertas) is None:
                return "borrar_fuera", f"rm fuera del clon y las raices: {p}", {"ruta": str(p)}
        return None, "rm dentro del clon o de una raiz", None
    if exe in EXES_DE_RUTAS or exe in EXES_QUE_TOCAN or exe in SUBEN_ARCHIVOS:
        rutas, motivo = _rutas_resueltas(exe, argv, cwd)
        if motivo:
            return "DENEGAR", motivo, None
        for p in rutas:
            if _protegida(p):
                return "NUNCA", f"{exe} sobre {p}: datos de Pedro", None
            if exe in EXES_QUE_ESCRIBEN and _auto_escalada(p, compuertas):
                return "DENEGAR", f"{exe} sobre {p}: auto-escalada", None
        if exe == "find" and any(t in ("-exec", "-execdir", "-ok", "-okdir", "-delete") for t in argv):
            return "DENEGAR", "find con -exec/-delete: no se ve adentro", None
        if exe in SUBEN_ARCHIVOS:
            urls = [t for t in argv[1:] if "://" in t]
            if not urls or not all(_dominio_permitido(u, compuertas) for u in urls):
                return "DENEGAR", "dominio no declarado", None
            return "web", "web a un dominio declarado", {"urls": urls}
        return None, "comando simple permitido", None
    if exe in ("pip", "pip3") or (exe in ("python", "python3") and argv[1:3] == ["-m", "pip"]) \
            or (exe == "uv" and argv[1:2] == ["pip"]):
        verbo = next((t for t in argv[1:] if t in ("install", "uninstall", "download")), None)
        if verbo is None:
            return None, "pip de consulta", None
        if "--user" in argv or donde == "sistema" and exe in ("pip", "pip3", "python", "python3"):
            return "instalar_home", "pip fuera del venv del clon", {"argv": argv}
        return "instalar_en_goal", "pip en el venv del clon", {"argv": argv}
    if exe in ("npm", "yarn", "pnpm"):
        if any(t in ("-g", "--global") for t in argv) or argv[1:3] == ["global", "add"]:
            return "instalar_home", "npm -g: fuera del goal", {"argv": argv}
        if any(t in ("install", "i", "ci", "add") for t in argv[1:2]):
            return "instalar_en_goal", "npm install en el cwd", {"argv": argv}
        return None, "npm de consulta o script", None
    if exe == "flatpak":
        if any(t in ("remote-delete", "remote-modify") for t in argv):
            return "NUNCA", "flatpak remote-delete/modify", None
        if "--system" in argv or "remote-add" in argv:
            return "instalar_sistema", "flatpak de sistema", {"argv": argv}
        if "install" in argv or "uninstall" in argv or "update" in argv:
            if "--user" in argv:
                return "instalar_home", "flatpak --user", {"argv": argv}
            return "instalar_sistema", "flatpak install sin --user es de sistema en Bazzite", {"argv": argv}
        if argv[1:2] in (["list"], ["info"], ["search"]):
            return None, "flatpak de consulta", None
        return "DENEGAR", f"flatpak {argv[1:2]}: fuera del allow-list", None
    if exe == "rpm-ostree":
        if any(t in ("rebase", "reset", "rollback", "deploy", "upgrade", "override") for t in argv):
            return "NUNCA", "rpm-ostree rebase/reset/rollback: nunca", None
        if any(t in ("install", "uninstall") for t in argv):
            return "instalar_sistema", "rpm-ostree install", {"argv": argv}
        if argv[1:2] == ["status"]:
            return None, "rpm-ostree status", None
        return "DENEGAR", "rpm-ostree: fuera del allow-list", None
    if exe in ALLOW_EXES or donde in ("venv", "clon"):
        return None, "comando simple permitido", None
    return "DENEGAR", f"{exe}: fuera del allow-list", None


def _aplicar_tabla(familia: str | None, motivo: str, forma: dict | None,
                   compuertas: dict) -> Decision:
    if familia is None:
        return Decision(True, motivo, None, forma)
    if familia == "NUNCA":
        return Decision(False, f"NUNCA: {motivo}", "NUNCA", forma)
    if familia == "DENEGAR":
        return Decision(False, motivo, None, forma)
    nivel = (compuertas.get("niveles") or {}).get(familia)
    if nivel == "directo":
        return Decision(True, f"{familia}: directo", familia, forma)
    if nivel == "pregunta":
        for pre in compuertas.get("preautorizadas") or []:
            if pre.get("familia") == familia and pre.get("forma") == forma:
                return Decision(True, f"{familia}: preautorizada por Pedro para este goal", familia, forma)
        return Decision(False, f"pregunta:{familia}: {motivo}. {INSTRUCCION_PREGUNTA}", familia, forma)
    if nivel == "nunca":
        return Decision(False, f"NUNCA: {familia}: {motivo}", familia, forma)
    return Decision(False, f"familia sin nivel en la tabla: {familia}", familia, forma)


def decidir_bash(comando: str, compuertas: dict) -> Decision:
    argv = partir(comando)
    if argv is None:
        return Decision(False, "compuesto, heredoc, redireccion o vacio: no se sabe parsear", None)
    familia, motivo, forma = familia_de_argv(argv, compuertas)
    return _aplicar_tabla(familia, motivo, forma, compuertas)


# --------------------------------------------------------------------------
# archivos y web
# --------------------------------------------------------------------------

def decidir_archivo(tool: str, tool_input: dict, compuertas: dict) -> Decision:
    ruta = tool_input.get("file_path") or tool_input.get("path") or tool_input.get("notebook_path")
    cwd = compuertas.get("cwd")
    if tool in ("Read", "Glob", "Grep"):
        if not ruta:
            return Decision(True, f"{tool} sin ruta (el cwd)", None)
        p = _resolver(ruta, cwd)
        if _protegida(p):
            return Decision(False, f"NUNCA: {tool} sobre {p}: datos de Pedro", "datos_de_pedro")
        return Decision(True, f"{tool} permitido", None)
    if not ruta:
        return Decision(False, f"{tool} sin file_path", None)
    p = _resolver(ruta, cwd)
    if _protegida(p):
        return Decision(False, f"NUNCA: {tool} sobre {p}: datos de Pedro", "datos_de_pedro")
    if _auto_escalada(p, compuertas):
        return Decision(False, f"{tool} sobre {p}: auto-escalada (.claude, .git/hooks, .git/config)", None)
    alcance = _en_alcance(p, compuertas)
    if alcance:
        return _aplicar_tabla(alcance, f"{tool} dentro de {alcance}", {"ruta": str(p)}, compuertas)
    return _aplicar_tabla("raiz_nueva", f"{tool} fuera del clon y las raices: {p}",
                          {"raiz": str(p.parent)}, compuertas)


def decidir_web(tool: str, tool_input: dict, compuertas: dict) -> Decision:
    if not compuertas.get("dominios"):
        return Decision(False, f"{tool}: el goal no declaro dominios", "web")
    if tool == "WebFetch":
        url = str(tool_input.get("url") or "")
        if not _dominio_permitido(url, compuertas):
            return Decision(False, f"WebFetch: dominio no declarado ({_host(url)})", "web")
        return _aplicar_tabla("web", f"WebFetch a {_host(url)}", {"url": url}, compuertas)
    return _aplicar_tabla("web", "WebSearch", {"query": str(tool_input.get("query") or "")[:200]},
                          compuertas)


def decidir(evento: dict, compuertas: dict) -> Decision:
    tool = str(evento.get("tool_name") or "")
    entrada = evento.get("tool_input") or {}
    if not isinstance(entrada, dict):
        return Decision(False, "tool_input no es un objeto", None)
    if tool == "StructuredOutput":
        return Decision(True, "la salida estructurada del veredicto", None)
    if tool == "Bash":
        return decidir_bash(str(entrada.get("command") or ""), compuertas)
    if tool in ("Edit", "Write", "MultiEdit", "NotebookEdit", "Read", "Glob", "Grep"):
        return decidir_archivo(tool, entrada, compuertas)
    if tool in ("WebFetch", "WebSearch"):
        return decidir_web(tool, entrada, compuertas)
    return Decision(False, f"herramienta fuera del contrato del goal: {tool}", None)


# --------------------------------------------------------------------------
# el JSON, el registro, main
# --------------------------------------------------------------------------

def cargar_compuertas(argv: list[str], environ: dict) -> dict:
    ruta = environ.get(VAR_COMPUERTAS)
    if "--compuertas" in argv:
        ruta = ruta or argv[argv.index("--compuertas") + 1]
    if not ruta:
        raise RuntimeError(f"sin compuertas: ni {VAR_COMPUERTAS} ni --compuertas")
    datos = json.loads(pathlib.Path(ruta).read_text(encoding="utf-8"))
    if not isinstance(datos, dict) or "niveles" not in datos:
        raise RuntimeError("compuertas.json sin niveles")
    return datos


def anotar(compuertas: dict, evento: dict, decision: Decision) -> None:
    """Una linea por decision en el registro del goal. Si no se puede
    escribir, se levanta: fail-closed (el runner necesita el rastro)."""
    registro = compuertas.get("registro")
    if not registro:
        raise RuntimeError("compuertas.json sin registro")
    entrada = evento.get("tool_input") or {}
    resumen = (entrada.get("command") or entrada.get("file_path") or entrada.get("url")
               or entrada.get("path") or entrada.get("query") or "")
    fila = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
            "tool": evento.get("tool_name"), "tool_use_id": evento.get("tool_use_id"),
            "decision": "allow" if decision.permitir else "deny",
            "familia": decision.familia, "motivo": decision.motivo, "forma": decision.forma,
            "resumen": str(resumen)[:300]}
    with open(registro, "a", encoding="utf-8") as f:
        f.write(json.dumps(fila, ensure_ascii=False) + "\n")


def main(stdin=None, stdout=None, stderr=None, argv: list[str] | None = None,
         environ: dict | None = None) -> int:
    stdin = stdin if stdin is not None else sys.stdin
    stderr = stderr if stderr is not None else sys.stderr
    argv = list(sys.argv[1:] if argv is None else argv)
    environ = dict(os.environ if environ is None else environ)
    try:
        compuertas = cargar_compuertas(argv, environ)
        crudo = stdin.read()
        evento = json.loads(crudo)
        if not isinstance(evento, dict) or evento.get("hook_event_name", "PreToolUse") != "PreToolUse":
            raise RuntimeError("evento que no es PreToolUse")
        decision = decidir(evento, compuertas)
        anotar(compuertas, evento, decision)
        if decision.permitir:
            return 0
        stderr.write(f"goal_hook: DENEGADO ({decision.familia or 'sin familia'}): {decision.motivo}\n")
        return 2
    except BaseException as exc:  # noqa: BLE001 - fail-closed: TODO error deniega
        try:
            stderr.write(f"goal_hook: DENEGADO (error interno): {type(exc).__name__}: {exc}\n")
        except BaseException:
            pass
        return 2


if __name__ == "__main__":
    sys.exit(main())
