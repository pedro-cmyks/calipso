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
            setsid, find -exec/-delete; codigo inline de un interprete en
            cualquier posicion: python -c/-Ic, node -e/-p/--eval, ruby -e,
            perl -e/-E, php -r; npx; git -C, --git-dir, worktree,
            update-ref, branch -D, remote, fetch, pull, clone, rebase
            --exec/-x/-i, config que escribe o sale del clon); lo
            NUNCA (gh, git push, sudo, pkexec, su, rpm-ostree
            rebase|reset|rollback, flatpak remote-delete|remote-modify,
            mail, sendmail, rm o cat sobre las rutas protegidas -- tambien
            por glob (`~/.ss*`) o por llaves (`~/.{ssh,aws}`, `{1..9}`):
            se expanden aca como lo haria bash, con un presupuesto de
            trabajo; un glob cuyo padre es el home o `/` (`rm -rf ~/*`)
            vale como el padre; como valor de una opcion
            (`--directory=~/.ssh`, `-C~/.ssh`) o como archivo que curl/wget
            subirian (`-T`, `-d @`, `-F x=@`, `--data-urlencode n@`); una
            variable en una ruta (`/var/home/$USER/.ssh`) se deniega porque
            bash la expande despues del hook); los ESCRITORES por su ruta
            DESTINO (cp, mv, sed -i, tee, touch, mkdir, chmod, tar -x -C,
            unzip -d, curl -o, wget -O/-P, dd of=, find -fprint...: fuera
            del clon y las raices = pregunta raiz_nueva, como Write); y las
            compuertas por familia con la tabla del goal (instalar_en_goal
            directo dentro del venv del clon / npm sin -g; instalar_home,
            instalar_sistema, borrar_fuera en pregunta salvo preautorizada).
  Edit/Write/MultiEdit  dentro del clon o de una raiz declarada; nunca
            `.claude/`, `.git/hooks/`, `.git/config` del clon (el martillo no
            se auto-escala); fuera = pregunta raiz_nueva.
  Read/Glob/Grep  el clon, las raices y lo que esta fuera del home (`/etc`,
            `/usr`); las rutas protegidas, el home a secas y un ancestro
            del home (`/`, `/var/home`: recorrerlo abarca el home y el
            sandbox no lo tapa) NUNCA; el resto del home de Pedro =
            pregunta raiz_nueva (lo mismo para cat, grep, find, jq... por
            Bash: lo que el martillo lee viaja a la suscripcion; solo ls,
            stat y file sin -R pueden mirar `/` o `/var/home` a secas).
            El resto del confinamiento lo hace `--restricted` (los file
            tools no salen de los working directories).
  WebFetch/WebSearch  solo con dominios declarados; el host tiene que estar
            en la lista (son in-process: el sandbox no las filtra, Trampa 8).

Lo NUNCA sale etiquetado con su familia de la tabla cuando la tiene
(FAMILIAS_NUNCA: datos_de_pedro, publicar, correo, rpm_ostree_rebase,
flatpak_remote_delete) y con "NUNCA" cuando no (sudo/pkexec/doas/su, la
auto-escalada del clon); el motivo lleva el prefijo `NUNCA:` y la tabla del
goal no lo relaja: se deniega por nombre. El motor de permisos
(permisos/goal.py) importa estas mismas funciones y decide lo mismo.

La tabla del goal llega por un JSON (`compuertas.json`, lo escribe
goals.escribir_compuertas) cuya ruta viene en la variable de entorno
CALIPSO_GOAL_COMPUERTAS del proceso claude (el hook la hereda) o, de
respaldo, en `--compuertas <ruta>`. Cada decision se anota en el
`registro` (hook.jsonl del goal): el runner lo lee para el ledger y la
aduana.

Salida: permitir = exit 0 sin stdout (bajo --restricted un `allow` del hook
se ignora igual: "a confined session takes grants only from its command
line"); denegar = una linea `goal_hook: DENEGADO (...)` en stderr y exit 2.
Solo decide eventos con `hook_event_name == "PreToolUse"`: sin nombre se
deniega (JSON que no se entiende); con otro nombre sale 0 sin decidir ni
anotar (no es un allow: el hook esta registrado solo en PreToolUse).
"""
from __future__ import annotations

import datetime
import fnmatch
import json
import os
import pathlib
import shlex
import stat
import sys

VAR_COMPUERTAS = "CALIPSO_GOAL_COMPUERTAS"

# Las rutas de Pedro que NUNCA se leen ni se borran desde un golpe
# (permisos/acciones.py:176-183 mas ~/.claude, ~/.codex, ~/.calipso).
PROTEGIDAS = ("~/.ssh", "~/.gnupg", "~/.aws", "~/.config/gh", "~/.claude", "~/.codex",
              "~/.calipso", "~/.local/share/keyrings", "~/.password-store")
NUNCA_EXES = {"sudo", "pkexec", "doas", "su", "gh", "mail", "sendmail", "mutt"}
# La etiqueta de lo NUNCA: la familia de la tabla (goals.COMPUERTAS["nunca"])
# cuando la tiene, y "NUNCA" cuando no (escalar privilegios, la auto-escalada
# del clon). El motor de permisos (permisos/goal.py) mapea estas familias
# por NOMBRE al nivel nunca, igual que este hook: la tabla del goal no puede
# relajarlas. Es una copia a proposito (el hook no importa calipso);
# test_goals_permisos la compara con la tabla.
FAMILIAS_NUNCA = ("datos_de_pedro", "publicar", "correo", "rpm_ostree_rebase", "flatpak_remote_delete")
FAMILIA_DEL_EXE_NUNCA = {"gh": "publicar", "mail": "correo", "sendmail": "correo", "mutt": "correo"}
COMPUESTOS = (";", "&&", "||", "|", "$(", "`", ">", "<", "<<", "&")
ENVOLTORIOS = {"bash", "sh", "zsh", "dash", "fish", "eval", "source", ".", "xargs", "env",
               "nohup", "setsid", "exec", "command", "builtin", "watch", "script", "ssh",
               "scp", "sftp", "rsync", "nc", "ncat", "telnet"}
# Los interpretes y shells que ejecutan lo que reciben por argv. Con codigo
# inline el hook no puede leer lo que ejecutan: se deniega en CUALQUIER
# posicion de la argv (el smoke adversario paso `python3 -I -S -c` porque
# solo se miraba argv[1:3]) y tambien dentro de un cluster de flags cortas
# (`-Ic`, `-uc`, `-OOc`, `-pe`), leyendo el cluster como el interprete: una
# letra que toma valor (`-m`, `-W`, `-X` de python) se lleva el resto. El
# nombre se compara sin version (python3.12 -> python). Un script del clon
# (`python archivo.py`, `./script.sh`, `bash script.sh`), `make` y `npm run`
# siguen pasando: un goal de codigo corre sus tests y sus scripts, y lo que
# corre adentro lo contiene el sandbox (residuo declarado en la adenda del
# cierre: el hook es una segunda capa por nombre).
INTERPRETES = {"python", "pypy", "node", "ruby", "perl", "php", "sh", "bash", "zsh", "dash", "busybox"}
LETRAS_INLINE = frozenset("ceE")
LETRAS_INLINE_POR_EXE = {"node": frozenset("p"), "php": frozenset("r")}
LETRAS_CON_VALOR = {"python": "mWXQ", "pypy": "mWXQ", "node": "r", "ruby": "rIC", "perl": "IM"}
OPCIONES_INLINE = ("--eval", "--print")
SHELLS = {"bash", "sh", "zsh", "dash"}
# Comandos simples que no salen del clon ni tocan el sistema. Todo lo demas
# (salvo las familias de abajo) se deniega: la lista es blanca a proposito.
ALLOW_EXES = {
    "ls", "cat", "head", "tail", "wc", "grep", "rg", "find", "sed", "awk", "cut", "sort", "uniq",
    "tr", "echo", "printf", "pwd", "mkdir", "touch", "cp", "mv", "diff", "which", "true", "false",
    "test", "[", "stat", "file", "basename", "dirname", "realpath", "readlink", "date", "sleep",
    "tee", "tree", "du", "df", "ps", "python", "python3", "pytest", "node", "cargo", "go",
    "make", "cmake", "gcc", "g++", "cc", "rustc", "ruby", "bundle", "black", "ruff", "mypy",
    "flake8", "isort", "pyright", "tsc", "eslint", "prettier", "jq", "tar", "unzip", "zip",
    "gzip", "gunzip", "sha256sum", "md5sum", "chmod", "ln", "seq", "xxd", "hexdump", "od", "strings", "less",
    "more", "yes", "nproc", "uname", "id", "whoami", "hostname", "uv", "poetry", "pipx", "rm",
    "git", "pip", "pip3", "npm", "yarn", "pnpm", "flatpak", "rpm-ostree", "curl", "wget",
    "install", "chown", "truncate", "dd",
}
GIT_PERMITIDOS = {"status", "diff", "log", "show", "add", "commit", "checkout", "switch",
                  "restore", "branch", "stash", "rev-parse", "ls-files", "mv", "rm", "tag",
                  "merge", "rebase", "reset", "blame", "grep", "describe", "shortlog", "cherry-pick",
                  "revert", "clean", "init", "apply", "format-patch", "diff-tree", "cat-file",
                  "rev-list", "name-rev", "symbolic-ref", "config"}
GIT_PROHIBIDOS = {"push", "fetch", "pull", "clone", "remote", "worktree", "update-ref",
                  "submodule", "lfs", "svn", "p4", "ls-remote", "send-email", "request-pull",
                  "gc", "reflog", "filter-branch", "replace", "notes", "daemon", "instaweb",
                  "credential", "credential-store", "credential-cache", "archive", "bundle"}
GIT_OPCIONES_PROHIBIDAS = ("-C", "--git-dir", "--work-tree", "--exec-path", "-c", "--config-env",
                           "--namespace")
# `git config` solo de consulta: un alias `!cmd` es un envoltorio y un
# `core.hooksPath`/`credential.helper` una escalada; y solo sobre la config
# que ve el clon: `--file` leeria cualquier INI (`~/.aws/credentials`).
GIT_CONFIG_LEE = ("--get", "--get-all", "--list", "-l", "--get-regexp")
GIT_CONFIG_FUERA = ("--file", "-f", "--blob", "--global", "--system", "--edit", "-e")
# Los ejecutables que miran rutas: cada token con pinta de ruta pasa por las
# protegidas (NUNCA) y, los que escriben, por la auto-escalada. curl/wget
# ademas: el archivo que subirian es un dato de Pedro antes que un hecho web.
EXES_DE_RUTAS = ("cat", "head", "tail", "less", "more", "cp", "mv", "ln", "tar", "zip", "sed", "awk",
                 "grep", "rg", "find", "stat", "file", "wc", "xxd", "hexdump")
EXES_QUE_TOCAN = ("touch", "tee", "mkdir", "chmod")
EXES_QUE_ESCRIBEN = ("cp", "mv", "ln", "sed") + EXES_QUE_TOCAN
SUBEN_ARCHIVOS = ("curl", "wget")
# Los que escriben, y DONDE: la ruta destino decide como en Write (protegida
# -> NUNCA; fuera del clon y las raices -> raiz_nueva, pregunta; adentro ->
# allow). Sin esto `curl -o /tmp/x`, `tar -x -C /tmp`, `cp x /tmp/x` salian
# allow porque el exe estaba en la lista y el destino no era protegido (C2
# del cierre; la sonda de destinos del smoke, corrida 6). Por exe:
#   cp/mv/ln/install  el ultimo argumento que no es opcion, o el de -t
#   sed -i            los archivos (el script no); sin -i no escribe
#   tee/touch/mkdir/chmod/chown/truncate  cada argumento
#   tar -x            el -C (sin -C: el cwd); tar -c/-r/-u: el -f
#   unzip             el -d (sin -d: el cwd; -l/-t/-p/-c/-z no escriben); zip: el archivo (y -O)
#   gzip/gunzip       cada archivo (escriben al lado; -c/-t/-l no)
#   curl              -o/--output, --output-dir, -D, -c, --trace...; -O es el cwd
#   wget              -O, -P, -o/-a (el log); sin ellos el cwd
#   dd                of=
#   find              el archivo de -fprint/-fprintf/-fprint0/-fls
# `-` (stdout) y /dev/null no son destinos.
ESCRITORES = {"cp", "mv", "ln", "install", "sed", "tee", "touch", "mkdir", "chmod", "chown", "truncate",
              "tar", "unzip", "zip", "gzip", "gunzip", "curl", "wget", "dd", "find"}
# Los que leen archivos (ademas de EXES_DE_RUTAS): lo que el martillo lee
# viaja a la suscripcion (invariante 9). Toda ruta bajo el HOME de Pedro
# que no esta en el clon, las raices ni las protegidas (`~/Documentos`,
# `~/.bashrc`) es raiz_nueva (pregunta), tambien como fuente de un
# escritor o subida de curl; fuera del home (/etc, /usr, /proc, /tmp) es
# allow (C3 del cierre). `tr` no lee archivos y queda fuera; `jq` lee los
# archivos de entrada (y los de --slurpfile/--rawfile/-f/-L), no el filtro.
LECTORES = ("ls", "diff", "sort", "uniq", "cut", "od", "strings", "tree", "du", "sha256sum", "md5sum", "jq")
# Los unicos que pueden mirar un ANCESTRO del home (`ls /`, `ls -la
# /var/home`, `stat /`, `file /`): sin `-R`/`--recursive` no entran al
# home. Cualquier otro exe con un ancestro como ruta (grep -r, find, tree,
# du, cp -r, tar -c, curl -T, cat, diff -r...) es NUNCA: abarca el home y el
# sandbox no lo tapa (re-review del carril 1).
LEEN_SIN_RECORRER = ("ls", "stat", "file")
EXES_CON_RUTAS = set(EXES_DE_RUTAS) | set(EXES_QUE_TOCAN) | set(SUBEN_ARCHIVOS) | ESCRITORES | set(LECTORES)
# Las opciones que toman valor (letras cortas, largas sin `=`): al buscar los
# argumentos posicionales de un escritor se saltan sus valores, si no
# `cp x /tmp/x -S .bak` tendria como destino `.bak`.
OPCIONES_CON_VALOR = {
    "cp": ("tS", ("--target-directory", "--suffix")), "mv": ("tS", ("--target-directory", "--suffix")),
    "ln": ("tS", ("--target-directory", "--suffix")),
    "install": ("tSmog", ("--target-directory", "--suffix", "--mode", "--owner", "--group", "--strip-program")),
    "touch": ("dtr", ("--date", "--reference", "--time")), "mkdir": ("m", ("--mode", "--context")),
    "chmod": ("", ("--reference",)), "chown": ("", ("--reference", "--from")),
    "truncate": ("sr", ("--size", "--reference")), "tee": ("", ()),
    "zip": ("btnxiOPZ", ()), "gzip": ("S", ("--suffix",)), "gunzip": ("S", ("--suffix",)),
}
OPCIONES_DESTINO = {
    "curl": ("oDc", ("--output", "--output-dir", "--dump-header", "--cookie-jar", "--trace", "--trace-ascii",
                     "--stderr")),
    "wget": ("OPoa", ("--output-document", "--directory-prefix", "--output-file", "--append-output")),
    "unzip": ("d", ()), "zip": ("O", ("--out",)),
    "cp": ("t", ("--target-directory",)), "mv": ("t", ("--target-directory",)),
    "ln": ("t", ("--target-directory",)), "install": ("t", ("--target-directory",)),
}
FIND_ESCRIBE = ("-fprint", "-fprintf", "-fprint0", "-fls")
# Un glob, unas llaves o una variable en un token con pinta de ruta: bash los
# expande DESPUES del hook (el hook ve `~/.ss*` o `~/.{ssh,aws}`, bash corre
# `cat ~/.ssh`). El glob y las llaves se expanden aca como lo haria bash; la
# variable no se ve adonde apunta. La expansion no tiene techo por matches
# (300 fuentes en `cat src/*.py` es trabajo legitimo) sino un presupuesto
# sobre el trabajo real de un comando: entradas de directorio visitadas y
# formas producidas por las llaves; se deniega solo al agotarlo (un hook que
# tarda es fail-open por timeout: no puede explotar listando).
GLOB = "*?["
PRESUPUESTO_EXPANSION = 100_000
# El valor de `-F` de awk, `-d` de cut y `-t` de sort (el separador, pegado
# o separado: `-F/`, `-F .`) nunca es una ruta. Se salta por exe y por
# opcion, nunca por el valor: un `/` pegado a `-C` de tar o a `-t` de cp SI
# es una ruta (`tar -C/ x` archiva desde la raiz). Si otro exe necesita lo
# mismo, se suma aca.
OPCIONES_SIN_RUTA = {"awk": ("-F",), "cut": ("-d",), "sort": ("-t",)}
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
    """Las dos vienen resueltas: alcanza con el prefijo de la cadena (con
    3000 rutas de un glob, `parents` de pathlib por ruta es el desperdicio)."""
    h, p = str(hijo), str(padre)
    return h == p or h.startswith(p.rstrip("/") + "/")


def _hijo_resuelto(c: pathlib.Path, nombre: str) -> pathlib.Path:
    """`c/nombre` con `c` ya resuelto: se resuelve de verdad solo si nombre
    es `.`/`..` o un symlink (un lstat, no un resolve por candidato)."""
    if nombre in (".", ".."):
        return _resolver(str(c / nombre), None)
    hijo = c / nombre
    try:
        if stat.S_ISLNK(os.lstat(hijo).st_mode):
            return _resolver(str(hijo), None)
    except OSError:
        pass
    return hijo


_PROTEGIDAS_CACHE: tuple[str, pathlib.Path, tuple[pathlib.Path, ...], tuple[str, ...]] | None = None


def _protegidas_resueltas() -> tuple[pathlib.Path, ...]:
    """PROTEGIDAS resueltas una sola vez por valor de HOME (los tests lo
    cambian por fixture): cada chequeo es una comparacion de rutas, no
    nueve expanduser+resolve por candidato y por nivel."""
    global _PROTEGIDAS_CACHE
    home = os.path.expanduser("~")
    if _PROTEGIDAS_CACHE is None or _PROTEGIDAS_CACHE[0] != home:
        rutas = tuple(pathlib.Path(os.path.expanduser(x)).resolve() for x in PROTEGIDAS)
        _PROTEGIDAS_CACHE = (home, pathlib.Path(home).resolve(), rutas,
                             tuple(str(r).rstrip("/") + "/" for r in rutas))
    return _PROTEGIDAS_CACHE[2]


def _home_resuelto() -> pathlib.Path:
    _protegidas_resueltas()
    return _PROTEGIDAS_CACHE[1]


def _bajo_protegida(p: pathlib.Path) -> bool:
    """Dentro de una de PROTEGIDAS (el home y `/` a secas solo estan
    protegidos como ruta exacta: lo que cuelga de ellos no). `p` viene
    resuelta: alcanza con el prefijo de la cadena."""
    _protegidas_resueltas()
    texto = str(p).rstrip("/") + "/"
    return any(texto.startswith(q) for q in _PROTEGIDAS_CACHE[3])


def _home_o_raiz(p: pathlib.Path) -> bool:
    return p == _home_resuelto() or p == pathlib.Path("/")


def _bajo_home(p: pathlib.Path) -> bool:
    return _dentro(p, _home_resuelto())


class Abarca(pathlib.PosixPath):
    """El padre de un glob al home o a `/` (`~/*`, `~/.*`, `/*/x`): bash lo
    expande a TODO lo que cuelga, asi que vale como el padre ENTERO y es
    NUNCA tambien para leer. Se distingue de `/` a secas, que si se lee
    (`ls /` lista el sistema)."""


def _abarca_el_home(p: pathlib.Path) -> bool:
    """Un ANCESTRO del home (`/`, `/var`, `/var/home`, `~/..`): recorrerlo,
    copiarlo, archivarlo, borrarlo o cambiarle permisos abarca el home
    entero, y el sandbox NO lo tapa (solo DENY_READ; el resto del home es
    legible desde adentro). El home mismo y lo que cuelga de el no son
    ancestros: van por _protegida/_bajo_home. `p` viene resuelta."""
    return p != _home_resuelto() and _dentro(_home_resuelto(), p)


def _protegida(p: pathlib.Path) -> bool:
    """Lo que no se borra ni se escribe jamas: una protegida, el home, `/`
    a secas o un ancestro del home (`rm -rf /`, `cp -t/`, `tar -x -C/`,
    `rm -rf ~/..`, `chmod -R 777 /var/home`)."""
    return _home_o_raiz(p) or _abarca_el_home(p) or _bajo_protegida(p)


def _protegida_para_leer(p: pathlib.Path) -> bool:
    """Lo que no se lee jamas: una protegida, el home a secas (el padre de
    todas: listarlo o recorrerlo las toca) y el padre de un glob que abarca
    el home o `/`. Un ancestro del home a secas (`/`, `/var/home`) queda
    fuera de aca a proposito: recorrerlo (`grep -r x /`, `find /`, `du`,
    `cp -r`, `tar -c`) es NUNCA por _abarca_el_home, pero `ls /`, `stat /`
    y `file /` sin -R no entran al home y siguen allow (LEEN_SIN_RECORRER)."""
    return isinstance(p, Abarca) or p == _home_resuelto() or _bajo_protegida(p)


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


class PresupuestoAgotado(Exception):
    """La expansion de un comando (globs y llaves) gasto mas trabajo que
    PRESUPUESTO_EXPANSION: no se sabe que abarca."""


class Presupuesto:
    """El trabajo que un comando puede gastar expandiendo: entradas de
    directorio visitadas por los globs y formas producidas por las llaves."""
    __slots__ = ("total", "gastado")

    def __init__(self, total: int) -> None:
        self.total = total
        self.gastado = 0

    def gastar(self, n: int) -> None:
        self.gastado += n
        if self.gastado > self.total:
            raise PresupuestoAgotado(f"mas de {self.total} entradas")


def _llave_que_cierra(tok: str, i: int) -> int:
    """Indice de la `}` que cierra la `{` de tok[i], o -1."""
    nivel = 0
    for j in range(i, len(tok)):
        if tok[j] == "{":
            nivel += 1
        elif tok[j] == "}":
            nivel -= 1
            if nivel == 0:
                return j
    return -1


def _rango_de_llave(cuerpo: str, presupuesto: Presupuesto) -> list[str] | None:
    """`{n..m}`, `{n..m..paso}` (enteros, con el relleno de ceros de bash) o
    `{a..z}` (letras). None si no es una secuencia. Se cuenta ANTES de
    materializar: `{1..999999999}` gasta el presupuesto sin armarse."""
    partes = cuerpo.split("..")
    if len(partes) not in (2, 3):
        return None
    a, b = partes[0], partes[1]
    try:
        paso = abs(int(partes[2])) if len(partes) == 3 else 1
    except ValueError:
        return None
    paso = paso or 1
    if len(a) == 1 and len(b) == 1 and a.isalpha() and b.isalpha():
        lo, hi = ord(a), ord(b)
        conv = chr
        ancho = 0
    else:
        try:
            lo, hi = int(a), int(b)
        except ValueError:
            return None
        rellena = any(len(x.lstrip("-")) > 1 and x.lstrip("-").startswith("0") for x in (a, b))
        ancho = max(len(a), len(b)) if rellena else 0

        def conv(n: int) -> str:
            return ("-" if n < 0 else "") + str(abs(n)).zfill(ancho - (1 if n < 0 else 0)) if ancho else str(n)
    cantidad = abs(hi - lo) // paso + 1
    presupuesto.gastar(cantidad)
    sentido = 1 if lo <= hi else -1
    return [conv(lo + sentido * paso * k) for k in range(cantidad)]


def _alternativas_de_llave(cuerpo: str, presupuesto: Presupuesto) -> list[str] | None:
    """Las alternativas de `{a,b,c}` (comas de primer nivel) o de una
    secuencia; None si las llaves no son una expansion (`{}`, `{a}`,
    `{print $1}`): bash las deja tal cual."""
    partes, nivel, desde = [], 0, 0
    for j, ch in enumerate(cuerpo):
        if ch == "{":
            nivel += 1
        elif ch == "}":
            nivel -= 1
        elif ch == "," and nivel == 0:
            partes.append(cuerpo[desde:j])
            desde = j + 1
    if partes:
        partes.append(cuerpo[desde:])
        presupuesto.gastar(len(partes))
        return partes
    return _rango_de_llave(cuerpo, presupuesto)


def _expandir_llaves(tok: str, presupuesto: Presupuesto) -> list[str]:
    """La brace expansion de bash: la primera llave que abre una expansion
    valida se abre, y cada alternativa mas el resto del token se vuelve a
    expandir (anidadas, varias por token). Lo que no expande queda literal.
    Levanta PresupuestoAgotado si las formas exceden el presupuesto."""
    i = tok.find("{")
    while i != -1:
        j = _llave_que_cierra(tok, i)
        if j != -1:
            alternativas = _alternativas_de_llave(tok[i + 1:j], presupuesto)
            if alternativas is not None:
                pre, post = tok[:i], tok[j + 1:]
                out: list[str] = []
                for alt in alternativas:
                    out.extend(pre + r for r in _expandir_llaves(alt + post, presupuesto))
                return out
        i = tok.find("{", i + 1)
    return [tok]


def _expandir(patron: str, cwd: str | None, presupuesto: Presupuesto) -> list[pathlib.Path]:
    """Los matches de un glob como los haria bash sin nullglob ni dotglob
    (`*` y `?` no ven los dotfiles salvo que el segmento empiece con `.`;
    `.` y `..` nunca, como bash 5.2 con globskipdots): rutas resueltas, o el
    literal si no hay match. No entra en una ruta protegida (la devuelve tal
    cual: lo de adentro ya es NUNCA y no hace falta listarlo). Cada entrada
    de directorio visitada gasta presupuesto; al agotarlo levanta
    PresupuestoAgotado: no se sabe que abarca. Los candidatos se llevan ya
    resueltos: una entrada de scandir solo se resuelve si es un symlink
    (d_type, sin syscall extra), no dos resolve por match."""
    texto = os.path.expanduser(patron)
    base = pathlib.Path("/") if texto.startswith("/") else _resolver(cwd or ".", None)
    candidatos = [base]
    for seg in [s for s in texto.split("/") if s]:
        nuevos: list[pathlib.Path] = []
        for c in candidatos:
            if _bajo_protegida(c):
                nuevos.append(c)
            elif not any(ch in seg for ch in GLOB):
                nuevos.append(_hijo_resuelto(c, seg))
            else:
                try:
                    with os.scandir(c) as it:
                        entradas = list(it)
                except OSError:
                    continue
                presupuesto.gastar(len(entradas) + 1)
                for e in entradas:
                    if (seg.startswith(".") or not e.name.startswith(".")) and fnmatch.fnmatchcase(e.name, seg):
                        hijo = c / e.name
                        nuevos.append(_resolver(str(hijo), None) if e.is_symlink() else hijo)
        candidatos = nuevos
        if not candidatos:
            break
    return candidatos or [_resolver(patron, cwd)]


def _padre_del_glob(forma: str, cwd: str | None) -> pathlib.Path:
    """Lo literal que hay antes del PRIMER segmento con glob, resuelto:
    `~/*`, `~/*/`, `~/*/x`, `~/.ss*` -> el home; `/*/` -> `/`; `src/*/x` ->
    src; `*` -> el cwd. La barra final no cambia lo que abarca (bash expande
    `~/*/` a todos los directorios del home) y un segmento mas tampoco
    (`~/*/*` recorre el home entero)."""
    partes = (forma.rstrip("/") or "/").split("/")
    i = next(k for k, seg in enumerate(partes) if any(ch in seg for ch in GLOB))
    if i == 0:
        return _resolver(cwd or ".", cwd)
    return _resolver("/".join(partes[:i]) or "/", cwd)


_BASES_CACHE: tuple[tuple, tuple[list[pathlib.Path], list[pathlib.Path], list[tuple]]] | None = None


def _bases(compuertas: dict) -> tuple[list[pathlib.Path], list[pathlib.Path], list[tuple]]:
    """(clon y cwd, raices, las rutas de auto-escalada de cada base)
    resueltos una vez por tabla: con 3000 rutas de un glob no se resuelven
    3000 veces."""
    global _BASES_CACHE
    clave = (compuertas.get("clon"), compuertas.get("cwd"), tuple(compuertas.get("raices") or []))
    if _BASES_CACHE is None or _BASES_CACHE[0] != clave:
        repo = [pathlib.Path(b).resolve() for b in clave[:2] if b]
        raices = [pathlib.Path(os.path.expanduser(r)).resolve() for r in clave[2]]
        escaladas = [(b / ".claude", b / ".git" / "hooks", b / ".git" / "config") for b in repo]
        _BASES_CACHE = (clave, (repo, raices, escaladas))
    return _BASES_CACHE[1]


def _auto_escalada(p: pathlib.Path, compuertas: dict) -> bool:
    """`.claude/`, `.git/hooks/`, `.git/config` del clon (o del cwd): escribir
    ahi es darse permisos o colgar un hook propio."""
    for claude, hooks, config in _bases(compuertas)[2]:
        if _dentro(p, claude) or _dentro(p, hooks) or p == config:
            return True
    return False


def _en_alcance(p: pathlib.Path, compuertas: dict) -> str | None:
    """`repo` si esta en el clon/cwd, `raices` si esta en una raiz declarada,
    None si no."""
    repo, raices, _ = _bases(compuertas)
    if any(_dentro(p, b) for b in repo):
        return "repo"
    if any(_dentro(p, r) for r in raices):
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


def _recursivo(argv: list[str]) -> bool:
    """`-R` (en un cluster tambien: `-laR`) o `--recursive`: ls entra a
    los subdirectorios."""
    return "--recursive" in argv or "R" in _flags_cortas(argv)


def _contra(base: str | None, tok: str) -> str:
    """`tok` visto desde `base` (el `-C` vigente de tar): pegado como texto,
    no resuelto, para que _resolver_formas siga viendo los globs, las
    llaves y las variables. Una absoluta o un `~` (bash lo expande antes
    que tar) no cambian."""
    if base is None or tok.startswith(("/", "~")):
        return tok
    return base.rstrip("/") + "/" + tok


def _candidatos_de_tar(argv: list[str]) -> list[str]:
    """Los tokens de tar que pueden ser una ruta, con los OPERANDOS (los
    miembros) vistos desde el `-C dir` anterior: GNU tar aplica cada -C al
    recorrer los nombres, asi que `tar -cf o.tar -C / var/home/pedro/.ssh`
    archiva la protegida (contra el cwd del clon no se veia); un -C
    relativo se encadena con el anterior. El -f, -T y -X se abren contra el
    cwd inicial (medido con tar 1.35) y van tal cual. Estilo viejo (`tar
    cf o.tar ...`): los valores vienen en orden."""
    out: list[str] = []
    base: str | None = None
    pendientes: list[str] = []
    for i, tok in enumerate(argv[1:], 1):
        if pendientes:
            letra = pendientes.pop(0)
            if letra == "C":
                base = _contra(base, tok)
                out.append(base)
            else:
                out.append(tok)
            continue
        if tok.startswith("--"):
            opcion, _, val = tok.partition("=")
            if opcion == "--directory":
                if val:
                    base = _contra(base, val)
                    out.append(base)
                else:
                    pendientes.append("C")
            elif opcion in ("--file", "--files-from", "--exclude-from"):
                if val:
                    out.append(val)
                else:
                    pendientes.append("f")
            elif opcion == "--add-file" and val:
                # un operando mas (se archiva desde el -C vigente, como los
                # sueltos; sin `=` cae abajo como operando y ya se ve desde -C)
                out.append(_contra(base, val))
            elif val:
                out.append(val)
            continue
        viejo = i == 1 and not tok.startswith("-") and tok.isalpha()
        if viejo or (tok.startswith("-") and len(tok) > 1):
            cuerpo = tok if viejo else tok[1:]
            for k, ch in enumerate(cuerpo):
                if ch in "fCTX":
                    resto = cuerpo[k + 1:]
                    if viejo or not resto:
                        pendientes.append(ch)
                    elif ch == "C":
                        base = _contra(base, resto)
                        out.append(base)
                    else:
                        out.append(resto)
                    if not viejo:
                        break
            continue
        out.append(_contra(base, tok))
    return out


def _candidatos_de_ruta(exe: str, argv: list[str]) -> list[str]:
    """Los tokens de argv[1:] que pueden ser una ruta: los que no son
    opcion, el valor de `--opcion=valor` y lo pegado a una opcion corta
    (`-C/x`, `-C/`; no el valor de `-F` de awk, pegado o separado);
    para curl/wget, ademas, lo que sigue a `@` (`-d @archivo`,
    `-F campo=@archivo`, `--data-urlencode nombre@archivo`) y nunca las
    URLs (esas van por dominio). tar aparte: sus operandos se ven desde
    el -C anterior."""
    if exe == "tar":
        return _candidatos_de_tar(argv)
    out = []
    sin_ruta = OPCIONES_SIN_RUTA.get(exe, ())
    saltar = False
    for tok in argv[1:]:
        if saltar:
            saltar = False
            continue
        if tok in sin_ruta:
            saltar = True
            continue
        if exe in SUBEN_ARCHIVOS and "://" in tok:
            continue
        if exe == "dd" and "=" in tok and not tok.startswith("-"):
            out.append(tok.split("=", 1)[1])
            continue
        if tok.startswith("--"):
            val = tok.split("=", 1)[1] if "=" in tok else ""
        elif tok.startswith("-"):
            val = "" if tok[:2] in sin_ruta else tok[2:]
        else:
            val = tok
        if exe in SUBEN_ARCHIVOS and "@" in val:
            val = val.split("@", 1)[1]
        if val:
            out.append(val)
    return out


# Las opciones de jq con valor: (cuantos tokens se lleva, cuales de ellos
# son un archivo). `--arg n v` y `--argjson n v` son cadenas; `--slurpfile`,
# `--rawfile` y `--argfile` leen el segundo; `-f`/`--from-file` lee el filtro
# de un archivo (y entonces TODOS los posicionales son entradas); `-L`/
# `--library-path` es un directorio de modulos; `--run-tests` corre un
# archivo de tests (no sale en `jq --help`: el re-review del carril 1 lo
# paso con ~/.aws/credentials). jq 1.8 no acepta `--opcion=valor`.
JQ_OPCIONES = {"--arg": (2, ()), "--argjson": (2, ()), "--slurpfile": (2, (1,)), "--rawfile": (2, (1,)),
               "--argfile": (2, (1,)), "--from-file": (1, (0,)), "--indent": (1, ()), "-f": (1, (0,)),
               "-L": (1, (0,)), "--library-path": (1, (0,)), "--run-tests": (1, (0,))}
# Las banderas largas SIN valor de jq 1.8 (`jq --help` mas `--binary`, que
# solo hace algo en Windows). Cualquier otra opcion larga se DENIEGA: la
# lista de las que leen un archivo nunca esta completa por construccion
# (fail-closed, como el resto del hook), y jq mismo rechaza lo que no
# conoce, asi que no se pierde nada legitimo.
JQ_BANDERAS = frozenset((
    "--null-input", "--raw-input", "--slurp", "--compact-output", "--raw-output", "--raw-output0",
    "--join-output", "--ascii-output", "--sort-keys", "--color-output", "--monochrome-output", "--tab",
    "--unbuffered", "--stream", "--stream-errors", "--seq", "--exit-status", "--version",
    "--build-configuration", "--help", "--binary", "--args", "--jsonargs"))


def _archivos_de_jq(argv: list[str]) -> tuple[list[str], str | None]:
    """(lo que `jq` lee, motivo para DENEGAR): los archivos de entrada (los
    posicionales despues del filtro, que no es una ruta aunque empiece con
    `.`), los de sus opciones con archivo y el filtro de `-f`. Despues de
    `--args` o `--jsonargs` los posicionales son cadenas, no archivos;
    despues de `--` todo es posicional. Una opcion larga que no esta en
    JQ_OPCIONES ni en JQ_BANDERAS deniega: no se sabe que lee."""
    out: list[str] = []
    filtro_visto = cadenas = solo_pos = False
    toks = argv[1:]
    i = 0
    while i < len(toks):
        tok = toks[i]
        if solo_pos:
            if not filtro_visto:
                filtro_visto = True
            elif not cadenas:
                out.append(tok)
        elif tok == "--":
            solo_pos = True
        elif tok in ("--args", "--jsonargs"):
            cadenas = True
        elif tok in JQ_OPCIONES:
            n, archivos = JQ_OPCIONES[tok]
            valores = toks[i + 1:i + 1 + n]
            out.extend(valores[k] for k in archivos if k < len(valores))
            if tok in ("-f", "--from-file"):
                filtro_visto = True
            i += n
        elif tok.startswith("--"):
            if tok not in JQ_BANDERAS:
                return [], f"jq {tok}: opcion desconocida"
        elif tok.startswith("-") and len(tok) > 1:
            letra = next((ch for ch in tok[1:] if ch in "fL"), None)
            if letra:
                resto = tok[tok.index(letra) + 1:]
                if resto:
                    out.append(resto)
                elif i + 1 < len(toks):
                    out.append(toks[i + 1])
                    i += 1
                filtro_visto = filtro_visto or letra == "f"
        elif not filtro_visto:
            filtro_visto = True
        elif not cadenas:
            out.append(tok)
        i += 1
    return out, None


def _rutas_resueltas(exe: str, argv: list[str], cwd: str | None) -> tuple[list[pathlib.Path], str | None]:
    """Todos los candidatos de ruta de la argv, resueltos (o el motivo para
    DENEGAR)."""
    if exe == "jq":
        tokens, motivo = _archivos_de_jq(argv)
        if motivo:
            return [], motivo
        return _resolver_formas(exe, tokens, cwd)
    return _resolver_formas(exe, _candidatos_de_ruta(exe, argv), cwd)


def _resolver_formas(exe: str, tokens: list[str], cwd: str | None) -> tuple[list[pathlib.Path], str | None]:
    """(rutas resueltas, motivo para DENEGAR). Primero las llaves (bash las
    abre antes que nada: `{~,x}` da `~`). Una forma con pinta de ruta (lleva
    `/` o empieza con `~` o `.`) con una variable adentro se deniega: bash la
    expande despues del hook y no se ve adonde apunta; con un glob se
    expande aca y entra cada match (o el literal si no hay ninguno), salvo
    que lo literal antes del primer glob sea el home o `/` (`rm -rf ~/*`,
    `~/*/`, `~/*/x`, `/*`): entonces vale ese padre. Globs y llaves comparten
    el presupuesto del comando; agotarlo deniega."""
    rutas: list[pathlib.Path] = []
    presupuesto = Presupuesto(PRESUPUESTO_EXPANSION)
    for tok in tokens:
        try:
            formas = _expandir_llaves(tok, presupuesto) if "{" in tok else [tok]
            for forma in formas:
                if not _pinta_de_ruta(forma):
                    rutas.append(_resolver(forma, cwd))
                    continue
                if _tiene_variable(forma):
                    return [], f"{exe}: variable en la ruta {forma}, no se ve adonde apunta"
                if not any(ch in forma for ch in GLOB):
                    rutas.append(_resolver(forma, cwd))
                    continue
                padre = _padre_del_glob(forma, cwd)
                if _home_o_raiz(padre):
                    rutas.append(Abarca(padre))
                    continue
                rutas.extend(_expandir(forma, cwd, presupuesto))
        except PresupuestoAgotado as exc:
            return [], f"{exe}: la expansion de {tok} agota el presupuesto ({exc}): no se sabe que abarca"
    return rutas, None


def _valores_de(argv: list[str], cortas: str, largas: tuple[str, ...]) -> list[str]:
    """Los valores de las opciones dadas, como las lee getopt: `-o v`,
    `-ov`, `-sSLo v` (la letra con valor se lleva el resto del cluster o el
    token siguiente), `--out v`, `--out=v`. `-` es stdout, no un valor."""
    out: list[str] = []
    siguiente = False
    for tok in argv[1:]:
        if siguiente:
            out.append(tok)
            siguiente = False
            continue
        if tok == "--":
            break
        if tok.startswith("--"):
            base, _, val = tok.partition("=")
            if base in largas:
                if val:
                    out.append(val)
                else:
                    siguiente = True
            continue
        if tok.startswith("-") and len(tok) > 1:
            for k, ch in enumerate(tok[1:], 1):
                if ch in cortas:
                    resto = tok[k + 1:]
                    if resto:
                        out.append(resto)
                    else:
                        siguiente = True
                    break
    return [v for v in out if v != "-"]


def _posicionales(argv: list[str], cortas: str, largas: tuple[str, ...]) -> list[str]:
    """Los argumentos que no son opcion ni valor de una opcion (cortas y
    largas son las que toman valor); despues de `--` todo es posicional."""
    out: list[str] = []
    siguiente = solo_pos = False
    for tok in argv[1:]:
        if siguiente:
            siguiente = False
            continue
        if solo_pos or tok == "-" or not tok.startswith("-"):
            out.append(tok)
            continue
        if tok == "--":
            solo_pos = True
            continue
        if tok.startswith("--"):
            siguiente = "=" not in tok and tok in largas
            continue
        for k, ch in enumerate(tok[1:], 1):
            if ch in cortas:
                siguiente = k == len(tok) - 1
                break
    return out


def _archivos_de_sed(argv: list[str]) -> list[str] | None:
    """Los archivos que `sed -i` reescribe (None si no es in-place). El
    script no es un archivo: es el primer posicional salvo que venga por
    `-e`/`-f`; `-ie` es `-i` con sufijo `e` (como lo lee GNU sed)."""
    in_place = tiene_script = False
    posicionales: list[str] = []
    siguiente = solo_pos = False
    for tok in argv[1:]:
        if siguiente:
            siguiente = False
            continue
        if solo_pos or tok == "-" or not tok.startswith("-"):
            posicionales.append(tok)
            continue
        if tok == "--":
            solo_pos = True
            continue
        if tok.startswith("--"):
            base, _, val = tok.partition("=")
            if base == "--in-place":
                in_place = True
            elif base in ("--expression", "--file"):
                tiene_script = True
                siguiente = not val
            elif base == "--line-length":
                siguiente = not val
            continue
        for k, ch in enumerate(tok[1:], 1):
            if ch == "i":
                in_place = True
                break
            if ch in "ef":
                tiene_script = True
                siguiente = k == len(tok) - 1
                break
            if ch == "l":
                siguiente = k == len(tok) - 1
                break
    if not in_place:
        return None
    return posicionales if tiene_script else posicionales[1:]


def _destinos_de_tar(argv: list[str]) -> tuple[list[str], str | None]:
    """(destinos, motivo para DENEGAR) de tar: al extraer, el `-C` (sin
    `-C`, el cwd); al crear/agregar, el `-f`. Las letras con valor (`f`,
    `C`, `T`, `X`) se llevan el resto del cluster o el token siguiente; en
    el estilo viejo (`tar xfC a.tar dir`) los valores vienen en orden.
    `-P` al extraer escribe rutas absolutas del archivo: se deniega."""
    modo = ""
    absolutas = a_stdout = False
    archivos: list[str] = []
    dirs: list[str] = []
    pendientes: list[str] = []
    for i, tok in enumerate(argv[1:], 1):
        if pendientes:
            letra = pendientes.pop(0)
            if letra == "f":
                archivos.append(tok)
            elif letra == "C":
                dirs.append(tok)
            continue
        if tok.startswith("--"):
            base, _, val = tok.partition("=")
            if base in ("--extract", "--get"):
                modo += "x"
            elif base in ("--create", "--append", "--update"):
                modo += "c"
            elif base == "--absolute-names":
                absolutas = True
            elif base == "--to-stdout":
                a_stdout = True
            elif base in ("--file", "--directory", "--files-from", "--exclude-from"):
                letra = {"--file": "f", "--directory": "C"}.get(base, "T")
                if val:
                    (archivos if letra == "f" else dirs if letra == "C" else []).append(val)
                else:
                    pendientes.append(letra)
            continue
        viejo = i == 1 and not tok.startswith("-") and tok.isalpha()
        if not viejo and not (tok.startswith("-") and len(tok) > 1):
            continue
        cuerpo = tok if viejo else tok[1:]
        for k, ch in enumerate(cuerpo):
            if ch in "xcru":
                modo += "x" if ch == "x" else "c"
            elif ch == "P":
                absolutas = True
            elif ch == "O":
                a_stdout = True
            elif ch in "fCTX":
                resto = cuerpo[k + 1:]
                if viejo:
                    pendientes.append(ch)
                    continue
                if resto:
                    (archivos if ch == "f" else dirs if ch == "C" else []).append(resto)
                else:
                    pendientes.append(ch)
                break
    if "x" in modo:
        if absolutas:
            return [], "tar -P al extraer: escribe rutas absolutas del archivo"
        if a_stdout:
            return [], None
        return dirs or ["."], None
    if "c" in modo:
        return [a for a in archivos if a != "-"], None
    return [], None


def _modo(argv: list[str], con_valor: str) -> str:
    """Las letras de MODO de los clusters cortos de argv: cada cluster se
    corta en la primera letra que toma valor (`d` de unzip, `S` de gzip),
    porque lo pegado a ella es el valor, no mas letras (`-d/tmp/x` es el
    destino /tmp/x, no el modo lista `l` mas `t` y `p`; `-S.txt` no es
    `-t`). Re-review del carril 1 (H2 parcial)."""
    letras = ""
    for tok in argv[1:]:
        if tok == "--":
            break
        if tok.startswith("-") and not tok.startswith("--") and len(tok) > 1:
            for ch in tok[1:]:
                if ch in con_valor:
                    break
                letras += ch
    return letras


def _tokens_destino(exe: str, argv: list[str]) -> tuple[list[str], str | None]:
    """(tokens destino, motivo para DENEGAR) de un escritor (ESCRITORES)."""
    if exe == "tar":
        return _destinos_de_tar(argv)
    if exe == "sed":
        return _archivos_de_sed(argv) or [], None
    if exe == "find":
        return [argv[i + 1] for i, t in enumerate(argv[:-1]) if t in FIND_ESCRIBE], None
    if exe == "dd":
        return [t.split("=", 1)[1] for t in argv[1:] if t.startswith("of=")], None
    if exe in ("curl", "wget"):
        return _valores_de(argv, *OPCIONES_DESTINO[exe]), None
    if exe == "unzip":
        if set(_modo(argv, "dPOI")) & set("ltpcz"):
            return [], None
        return _valores_de(argv, *OPCIONES_DESTINO[exe]) or ["."], None
    cortas, largas = OPCIONES_CON_VALOR.get(exe, ("", ()))
    posicionales = _posicionales(argv, cortas, largas)
    if exe in ("gzip", "gunzip"):
        if any(t in ("--stdout", "--to-stdout", "--test", "--list") for t in argv[1:]) \
                or set(_modo(argv, cortas)) & set("ctl"):
            return [], None
        return posicionales, None
    if exe == "zip":
        return _valores_de(argv, *OPCIONES_DESTINO[exe]) + posicionales[:1], None
    if exe in OPCIONES_DESTINO:
        return _valores_de(argv, *OPCIONES_DESTINO[exe]) or posicionales[-1:], None
    return posicionales, None


def _raiz_de(p: pathlib.Path) -> str:
    """La raiz que se le pediria a Pedro por este destino: el directorio si
    ya lo es, si no el padre (como el `raiz` de Write)."""
    try:
        if p.is_dir():
            return str(p)
    except OSError:
        pass
    return str(p.parent)


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


def _nunca(familia: str | None, motivo: str, forma: dict | None = None) -> tuple[str, str, dict | None]:
    """La salida de lo que no se hace jamas: la familia de la tabla cuando
    existe (FAMILIAS_NUNCA) o la etiqueta "NUNCA" cuando no; el motivo con
    el prefijo NUNCA: en los dos casos."""
    return familia or "NUNCA", f"NUNCA: {motivo}", forma


def _codigo_inline(exe: str, argv: list[str]) -> str | None:
    """El token de argv[1:] que es codigo inline para este interprete
    (INTERPRETES), en cualquier posicion; None si no hay o no es uno."""
    base = exe.rstrip("0123456789.")
    if base not in INTERPRETES:
        return None
    letras = LETRAS_INLINE | LETRAS_INLINE_POR_EXE.get(base, frozenset())
    con_valor = LETRAS_CON_VALOR.get(base, "")
    for tok in argv[1:]:
        if tok.startswith("--"):
            if tok.split("=", 1)[0] in OPCIONES_INLINE:
                return tok
            continue
        if len(tok) < 2 or not tok.startswith("-"):
            continue
        for ch in tok[1:]:
            if not ch.isalpha():
                break
            if ch in letras:
                return tok
            if ch in con_valor:
                break
    return None


def _script_del_clon(argv: list[str], compuertas: dict) -> pathlib.Path | None:
    """`bash script.sh [args]`: el script (el primer argumento, sin flags,
    sin variable ni glob) resuelto dentro del clon y fuera de la
    auto-escalada; None si la forma es otra (entonces es un envoltorio)."""
    if len(argv) < 2 or argv[1].startswith("-"):
        return None
    tok = argv[1]
    if _tiene_variable(tok) or "{" in tok or any(ch in tok for ch in GLOB):
        return None
    p = _resolver(tok, compuertas.get("cwd"))
    if _en_alcance(p, compuertas) != "repo" or _auto_escalada(p, compuertas):
        return None
    return p


def _rebase_ejecuta(resto: list[str]) -> str | None:
    """El token de `git rebase` que ejecuta una cadena que el hook no ve
    (`--exec`/`-x`, tambien pegado o en un cluster: `-ix`) o abre el editor
    de la lista (`-i`/`--interactive`, donde viven las lineas exec). Las
    letras que toman valor (`-X`, `-s`, `-S`, `-C`) se llevan el resto."""
    for t in resto:
        if t.startswith("--"):
            if t.split("=", 1)[0] in ("--exec", "--interactive"):
                return t
        elif t.startswith("-") and len(t) > 1:
            for ch in t[1:]:
                if ch in "xi":
                    return t
                if ch in "XsSC":
                    break
    return None


def _familia_git(argv: list[str]) -> tuple[str | None, str, dict | None]:
    resto = argv[1:]
    for tok in resto:
        if tok in GIT_OPCIONES_PROHIBIDAS or any(tok.startswith(o + "=") for o in GIT_OPCIONES_PROHIBIDAS):
            return "DENEGAR", f"git con {tok}: sale del clon", None
    sub = next((t for t in resto if not t.startswith("-")), None)
    if sub == "push":
        return _nunca("publicar", "git push: el push lo hace Calipso con el dale de Pedro (compuerta push)")
    if sub in GIT_PROHIBIDOS or sub is None:
        return "DENEGAR", f"git {sub}: fuera del allow-list del clon", None
    if sub == "branch" and any(t in ("-D", "-d", "--delete") for t in resto):
        return "DENEGAR", "git branch -D: fuera del allow-list", None
    if sub not in GIT_PERMITIDOS:
        return "DENEGAR", f"git {sub}: fuera del allow-list del clon", None
    if sub == "rebase":
        tok = _rebase_ejecuta(resto)
        if tok:
            return "DENEGAR", f"git rebase {tok}: ejecuta una cadena que el hook no ve", None
    if sub == "config":
        if not any(t in GIT_CONFIG_LEE for t in resto):
            return "DENEGAR", "git config escribe: un alias !cmd es un envoltorio", None
        fuera = next((t for t in resto if t in GIT_CONFIG_FUERA or t.startswith("--file=")), None)
        if fuera:
            return "DENEGAR", f"git config {fuera}: sale de la config del clon", None
    return None, f"git {sub} en el clon", None


def familia_de_argv(argv: list[str], compuertas: dict) -> tuple[str | None, str, dict | None]:
    """(familia, motivo, forma). familia None = comando simple permitido;
    "DENEGAR" = no se sabe parsear o no esta en el allow-list; una familia
    de la tabla = una compuerta con su forma concreta (ruling 15.11). Lo que
    no se hace jamas sale con su familia de FAMILIAS_NUNCA (publicar,
    datos_de_pedro, ...) o con la etiqueta "NUNCA" si no tiene una (escalar
    privilegios, auto-escalada), siempre con el motivo `NUNCA: ...`."""
    if not argv:
        return "DENEGAR", "comando vacio", None
    exe, donde = _exe_de(argv, compuertas)
    if exe in NUNCA_EXES:
        familia = FAMILIA_DEL_EXE_NUNCA.get(exe)
        return _nunca(familia, f"{exe}: {familia or 'escalar privilegios'} no se hace desde un golpe")
    tok = _codigo_inline(exe, argv)
    if tok:
        return "DENEGAR", f"{exe} {tok}: codigo inline: el hook no puede leer lo que ejecuta", None
    if exe in SHELLS and _script_del_clon(argv, compuertas) is not None:
        return None, f"{exe} {argv[1]}: script del clon (lo que corre adentro lo contiene el sandbox)", None
    if exe in ENVOLTORIOS:
        return "DENEGAR", f"{exe}: envoltorio, no se ve adentro", None
    if exe == "npx":
        return "DENEGAR", "npx ejecuta paquetes arbitrarios", None
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
                return _nunca("datos_de_pedro", f"rm sobre {p}: datos de Pedro", {"ruta": str(p)})
            if _auto_escalada(p, compuertas):
                return _nunca(None, f"rm sobre {p}: auto-escalada (.claude, .git/hooks, .git/config)",
                              {"ruta": str(p)})
        for p in rutas:
            if _en_alcance(p, compuertas) is None:
                return "borrar_fuera", f"rm fuera del clon y las raices: {p}", {"ruta": str(p)}
        return None, "rm dentro del clon o de una raiz", None
    if exe in EXES_CON_RUTAS:
        rutas, motivo = _rutas_resueltas(exe, argv, cwd)
        if motivo:
            return "DENEGAR", motivo, None
        recorre = exe not in LEEN_SIN_RECORRER or _recursivo(argv)
        for p in rutas:
            if _protegida_para_leer(p):
                return _nunca("datos_de_pedro", f"{exe} sobre {p}: datos de Pedro", {"ruta": str(p)})
            if recorre and _abarca_el_home(p):
                return _nunca("datos_de_pedro", f"{exe} sobre {p}: abarca el home de Pedro", {"ruta": str(p)})
            if exe in EXES_QUE_ESCRIBEN and _auto_escalada(p, compuertas):
                return _nunca(None, f"{exe} sobre {p}: auto-escalada (.claude, .git/hooks, .git/config)",
                              {"ruta": str(p)})
        if exe == "find" and any(t in ("-exec", "-execdir", "-ok", "-okdir", "-delete") for t in argv):
            return "DENEGAR", "find con -exec/-delete: no se ve adentro", None
        urls = [t for t in argv[1:] if "://" in t] if exe in SUBEN_ARCHIVOS else []
        if exe in SUBEN_ARCHIVOS and (not urls or not all(_dominio_permitido(u, compuertas) for u in urls)):
            return "DENEGAR", "dominio no declarado", None
        if exe in ESCRITORES:
            tokens, motivo = _tokens_destino(exe, argv)
            if motivo:
                return "DENEGAR", motivo, None
            destinos, motivo = _resolver_formas(exe, tokens, cwd)
            if motivo:
                return "DENEGAR", motivo, None
            for p in destinos:
                if _protegida(p):
                    return _nunca("datos_de_pedro", f"{exe} sobre {p}: datos de Pedro", {"ruta": str(p)})
                if _auto_escalada(p, compuertas):
                    return _nunca(None, f"{exe} sobre {p}: auto-escalada (.claude, .git/hooks, .git/config)",
                                  {"ruta": str(p)})
            for p in destinos:
                if str(p) != "/dev/null" and _en_alcance(p, compuertas) is None:
                    return "raiz_nueva", f"{exe} escribe fuera del alcance: {p}", {"raiz": _raiz_de(p)}
        for p in rutas:
            if _bajo_home(p) and _en_alcance(p, compuertas) is None:
                return "raiz_nueva", f"{exe} lee fuera del alcance: {p}", {"raiz": _raiz_de(p)}
        if exe in SUBEN_ARCHIVOS:
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
            return _nunca("flatpak_remote_delete", "flatpak remote-delete/modify")
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
            return _nunca("rpm_ostree_rebase", "rpm-ostree rebase/reset/rollback: nunca")
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
    if familia == "NUNCA" or familia in FAMILIAS_NUNCA:
        # por nombre y ANTES de la tabla: ningun nivel ni preautorizacion lo relaja
        return Decision(False, motivo if motivo.startswith("NUNCA:") else f"NUNCA: {motivo}", familia, forma)
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
        if _protegida_para_leer(p):
            return Decision(False, f"NUNCA: {tool} sobre {p}: datos de Pedro", "datos_de_pedro", {"ruta": str(p)})
        if _abarca_el_home(p):
            # Grep y Glob recorren (entran al home); Read de un directorio no es nada
            return Decision(False, f"NUNCA: {tool} sobre {p}: abarca el home de Pedro", "datos_de_pedro",
                            {"ruta": str(p)})
        if _bajo_home(p) and _en_alcance(p, compuertas) is None:
            return _aplicar_tabla("raiz_nueva", f"{tool} lee fuera del alcance: {p}", {"raiz": _raiz_de(p)},
                                  compuertas)
        return Decision(True, f"{tool} permitido", None)
    if not ruta:
        return Decision(False, f"{tool} sin file_path", None)
    p = _resolver(ruta, cwd)
    if _protegida(p):
        return Decision(False, f"NUNCA: {tool} sobre {p}: datos de Pedro", "datos_de_pedro", {"ruta": str(p)})
    if _auto_escalada(p, compuertas):
        # sin familia en la tabla: la etiqueta NUNCA (el motor la mapea al nivel nunca)
        return Decision(False, f"NUNCA: {tool} sobre {p}: auto-escalada (.claude, .git/hooks, .git/config)",
                        "NUNCA", {"ruta": str(p)})
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
        if not isinstance(evento, dict):
            raise RuntimeError("evento inesperado: no es un objeto")
        # El nombre del evento se exige explicito (C4 del cierre: sin nombre
        # se tomaba como PreToolUse). Sin nombre es un JSON que no se
        # entiende: deny. Con OTRO nombre no hay nada que decidir (el hook
        # esta registrado solo en PreToolUse; si llega un Stop o un
        # PostToolUse es el CLI o la config): exit 0 sin decidir, sin fila
        # en el registro, y no es un allow (un exit 2 ahi bloquearia cosas
        # que no se juzgan, como el fin de la sesion).
        nombre = evento.get("hook_event_name")
        if not isinstance(nombre, str) or not nombre:
            raise RuntimeError("evento inesperado: sin hook_event_name")
        if nombre != "PreToolUse":
            stderr.write(f"goal_hook: evento {nombre} sin decidir (solo decide PreToolUse)\n")
            return 0
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
