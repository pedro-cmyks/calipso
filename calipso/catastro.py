#!/usr/bin/env python3
"""
calipso/catastro.py - indice de los proyectos que hay en la maquina.

Antes de este modulo, Calipso conocia un solo proyecto por vez: el que
apunta ROOT (calipso/server.py). Pedro le preguntaba por otro repo y
contestaba que no sabia que era, aunque el repo estuviera al lado, en el
mismo disco. Pedro lo pidio, textual: "todos mis proyectos deberian de
estar en contexto de calipso de alguna manera o pues ser accesible".

El catastro es un escaneo de RAICES DECLARADAS (no del disco entero, y no
por turno: corre como rutina, kind "catastro" en routines.KINDS). Guarda
una entrada liviana por proyecto: nombre, rama, ultimo commit y un resumen
de dos lineas de README. No lee contenido de los repos mas alla de eso --
el resto sigue siendo trabajo de `_repo_brief` en calipso/server.py, bajo
demanda, nunca precargado (3.4 del spec).

Un proyecto es una carpeta con `.git`. Es el unico criterio (3.2).

Dos trampas de esta maquina que el modulo tiene que respetar:

- `/home` es un symlink a `/var/home`. Toda comparacion de rutas (raices,
  techo de `_switch_project` en server.py) se hace sobre rutas ya resueltas
  (`pathlib.Path.resolve()`), o la frontera se corre sola con solo escribir
  la ruta distinto.
- Un repo puede ser un WORKTREE: ahi `.git` es un ARCHIVO de una linea
  ("gitdir: ...") y no una carpeta. El criterio "carpeta con .git" acepta
  archivo o carpeta (`Path.exists()`, nunca `.is_dir()`), y la rama y el
  ultimo commit se piden con `git` -- nunca leyendo ".git/HEAD" a mano,
  porque ahi ".git" no es una carpeta y no hay ningun "HEAD" adentro que
  leer.

Y una regla de seguridad que no es negociable: leer un repo ajeno ya es
ejecutar codigo ajeno si se usa `git` sin blindar. Verificado en esta
maquina con un repo de prueba: un `.git/config` con
`core.fsmonitor = "touch X; false"` corre ese comando en un `git status`
comun, sin pedir permiso. Toda invocacion de `git` de este modulo va con
`-c core.fsmonitor= -c diff.external= -c core.pager=cat` y
`GIT_CONFIG_GLOBAL=/dev/null` en el entorno del subproceso (ver `_git`).
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import pathlib
import re
import subprocess
import threading
from typing import Any

from calipso import config as calipso_config

def calipso_home() -> pathlib.Path:
    """Carpeta base de Calipso, resuelta DE NUEVO en cada llamada -- nunca
    cacheada en una constante de modulo.

    La alternativa obvia (`CALIPSO_HOME = pathlib.Path(os.environ.get(...))`
    a nivel de modulo, el patron que usa el resto del repo) se resuelve
    UNA sola vez, la primera vez que algo importa este archivo. Python
    cachea modulos en `sys.modules`: si otro archivo de la suite de tests
    ya importo `calipso.server` (que importa este modulo) con el
    `CALIPSO_HOME` real de la maquina, cualquier test posterior que fije
    la variable de entorno y recien despues importe `calipso.catastro` se
    encuentra con el modulo ya cacheado -- la variable de entorno nueva no
    hace nada, y las funciones de este archivo siguen escribiendo en el
    `~/.calipso` real. Pasó exactamente eso: verificado corriendo la
    suite completa, `~/.calipso/catastro.json` de la maquina real
    terminaba pisado por tests que se pensaban aislados.

    La funcion evita el problema de raiz: no hay nada que quede fijado al
    importar, asi que no importa CUANDO se fijo `CALIPSO_HOME` en el
    entorno, sino que este seteado en el momento en que se LLAMA a esta
    funcion -- que es lo que un test puede controlar con total certeza
    (`monkeypatch.setenv`), sin depender de que su archivo sea el primero
    en importar nada."""
    return pathlib.Path(os.environ.get(
        "CALIPSO_HOME", os.path.expanduser("~/.calipso")))

# Carpetas que no vale la pena pisar durante el escaneo de raices: ni son
# proyectos ni tiene sentido bajar mas adentro buscando otro .git ahi.
IGNORE_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
    ".cache", "chroma", ".chroma", "target",
}

PROFUNDIDAD_DEFECTO = 3
# La reconciliacion de slugs (`_raices_extra_por_slug`) baja mas hondo que
# la raiz declarada: es la unica forma de encontrar un worktree como
# calipso/.claude/worktrees/<rama>, que a profundidad 3 desde el home no
# aparece (esta adentro de una carpeta oculta, ".claude"). Con techo y un
# limite de carpetas visitadas para que un home con muchas carpetas no
# vuelva cara esta segunda pasada.
PROFUNDIDAD_EXTRA_SLUGS = 8
LIMITE_CARPETAS_VISITADAS = 8000

GIT_TIMEOUT = 5


def _file() -> pathlib.Path:
    home = calipso_home()
    home.mkdir(parents=True, exist_ok=True)
    return home / "catastro.json"


def _slug(path: pathlib.Path) -> str:
    """Mismo algoritmo que `calipso/memory.py:_slug`, duplicado a proposito:
    memory.py importa chromadb (pesado, con modelo de embeddings) y el
    catastro no necesita nada de eso -- solo reconocer los nombres de
    carpeta que memory.py ya genero bajo ~/.calipso/projects/."""
    return re.sub(r"[^a-z0-9]+", "-", str(path).lower()).strip("-")[:80] or "root"


def _es_repo(path: pathlib.Path) -> bool:
    """Un proyecto es una carpeta con .git. Es el unico criterio (3.2).
    exists(), no is_dir(): en un worktree .git es un archivo de una linea
    ("gitdir: ..."), no una carpeta."""
    return (path / ".git").exists()


def _git(args: list[str], cwd: pathlib.Path) -> subprocess.CompletedProcess:
    """git blindado contra lo que declare el .git/config del repo que se
    esta leyendo. Un repo ajeno puede traer un .git/config con
    core.fsmonitor="comando; false" y ese comando corre en cualquier
    operacion de git normal, `git status` incluido -- verificado con un
    repo de prueba antes de escribir esto. Estas tres banderas mas
    GIT_CONFIG_GLOBAL=/dev/null (para que tampoco importe un config global
    del propio Pedro) lo cierran sin cambiar la salida de los comandos de
    solo lectura que usa este modulo."""
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=", "-c", "diff.external=",
         "-c", "core.pager=cat", *args],
        cwd=str(cwd), env=env, text=True, capture_output=True,
        timeout=GIT_TIMEOUT)


def _rama_y_commit(path: pathlib.Path) -> tuple[str | None, str | None]:
    """Rama y fecha ISO del ultimo commit, siempre via `git` -- nunca
    leyendo ".git/HEAD" a mano: en un worktree ".git" es un archivo, no una
    carpeta, y ahi adentro no hay ningun "HEAD" que abrir. `git` sabe
    resolver un worktree solo; leer el archivo a mano, no."""
    rama = None
    commit = None
    try:
        r = _git(["rev-parse", "--abbrev-ref", "HEAD"], path)
        if r.returncode == 0:
            rama = r.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        pass
    try:
        r = _git(["log", "-1", "--format=%cI"], path)
        if r.returncode == 0:
            commit = r.stdout.strip() or None
    except (subprocess.SubprocessError, OSError):
        pass
    return rama, commit


def _resumen_readme(path: pathlib.Path) -> str:
    """Las dos primeras lineas del README, y nada mas de todo el repo: ni
    el resto del archivo, ni ningun otro archivo. Es lo que hace que
    escanear el home sea barato y que un repo hostil recien clonado no
    tenga contenido en el contexto por el solo hecho de existir (3.3)."""
    for nombre in ("README.md", "Readme.md", "README", "README.txt"):
        p = path / nombre
        if p.exists() and p.is_file():
            try:
                lineas = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                return ""
            texto = " ".join(l.strip() for l in lineas[:2] if l.strip())
            return texto[:240]
    return ""


# --------------------------------------------------------------------------
# Persistencia: ~/.calipso/catastro.json = {"raices": [...], "proyectos": [...]}
# --------------------------------------------------------------------------

def _raiz_por_defecto() -> dict[str, Any]:
    return {"ruta": str(pathlib.Path.home().resolve()),
            "profundidad": PROFUNDIDAD_DEFECTO}


def _cargar_json() -> dict[str, Any]:
    f = _file()
    if not f.exists():
        return {"raices": [_raiz_por_defecto()], "proyectos": []}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"raices": [_raiz_por_defecto()], "proyectos": []}
    if not isinstance(data, dict):
        return {"raices": [_raiz_por_defecto()], "proyectos": []}
    data.setdefault("raices", [_raiz_por_defecto()])
    data.setdefault("proyectos", [])
    return data


def _guardar_json(data: dict[str, Any]) -> None:
    """Atomico, mismo patron que routines.save(): temporal en el mismo
    directorio + os.replace, para que un lector concurrente nunca vea un
    JSON a medio escribir."""
    p = _file()
    tmp = p.with_name(f"{p.name}.tmp{os.getpid()}.{threading.get_ident()}")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, p)
    finally:
        with contextlib.suppress(OSError):
            tmp.unlink()


def raices() -> list[dict[str, Any]]:
    return _cargar_json()["raices"]


def raices_resueltas() -> list[pathlib.Path]:
    out = []
    for r in raices():
        try:
            out.append(pathlib.Path(r["ruta"]).expanduser().resolve())
        except (OSError, KeyError, TypeError):
            continue
    return out


def dentro_de_alguna_raiz(path: pathlib.Path) -> bool:
    """Techo de `_switch_project` en calipso/server.py (hallazgo S4 del
    spec): un proyecto se abre DENTRO de una raiz declarada, nunca en
    cualquier lado; "/" no puede ser raiz porque no es descendiente de
    ninguna raiz declarada por defecto. Comparacion sobre rutas resueltas:
    en esta maquina /home es symlink a /var/home, y una comparacion sobre
    texto se corre sola con solo escribir la ruta distinto."""
    p = path.resolve()
    for r in raices_resueltas():
        if p == r or r in p.parents:
            return True
    return False


def marcar_visto(ruta: pathlib.Path) -> None:
    """Actualiza "visto" del proyecto que se acaba de abrir (llamado desde
    `_switch_project`), para que la lista de Proyectos del prompt lo
    ordene arriba -- "visto" es orden de uso reciente, no fecha de
    escaneo. Si el proyecto todavia no esta en el catastro (recien
    clonado, o el ultimo escaneo no llego a verlo) no hace nada: el
    proximo escaneo lo va a encontrar solo."""
    clave = str(ruta.resolve())
    data = _cargar_json()
    cambiado = False
    for p in data["proyectos"]:
        if p["ruta"] == clave:
            p["visto"] = datetime.datetime.now().isoformat(timespec="seconds")
            cambiado = True
            break
    if cambiado:
        _guardar_json(data)


# --------------------------------------------------------------------------
# Escaneo
# --------------------------------------------------------------------------

def _escanear_bajo(raiz: pathlib.Path, profundidad_max: int,
                   permitir_ocultos: bool = False,
                   limite: int | None = None,
                   descender_en_encontrados: bool = False) -> list[pathlib.Path]:
    """Recorre `raiz` hasta `profundidad_max` niveles buscando carpetas con
    .git. Por default no desciende adentro de un proyecto ya encontrado (no
    tiene sentido buscar otro .git adentro de un repo) ni adentro de
    IGNORE_DIRS. No sigue symlinks (evita ciclos). `limite` acota cuantas
    carpetas se visitan en total.

    `descender_en_encontrados` lo prende la pasada extendida de
    reconciliacion de slugs (`_raices_extra_por_slug`): un worktree como
    calipso/.claude/worktrees/<rama> vive ADENTRO de un repo que el
    escaneo normal ya encontro (calipso), asi que si esta pasada tambien
    cortara ahi nunca lo alcanzaria."""
    encontrados: list[pathlib.Path] = []
    visitadas = 0

    def _recorrer(actual: pathlib.Path, restante: int) -> None:
        nonlocal visitadas
        if limite is not None and visitadas >= limite:
            return
        visitadas += 1
        if _es_repo(actual):
            encontrados.append(actual)
            if not descender_en_encontrados:
                return  # no bajar adentro de un repo ya encontrado
        if restante <= 0:
            return
        try:
            hijos = sorted(actual.iterdir(), key=lambda e: e.name.lower())
        except OSError:
            return
        for h in hijos:
            if limite is not None and visitadas >= limite:
                return
            try:
                if h.is_symlink() or not h.is_dir():
                    continue
            except OSError:
                continue
            if h.name in IGNORE_DIRS:
                continue
            if h.name.startswith(".") and not permitir_ocultos:
                continue
            _recorrer(h, restante - 1)

    try:
        if not raiz.is_dir():
            return []
    except OSError:
        return []
    _recorrer(raiz, profundidad_max)
    return encontrados


def _profundidad_de(raiz: pathlib.Path) -> int:
    for r in raices():
        try:
            if pathlib.Path(r["ruta"]).expanduser().resolve() == raiz:
                return int(r.get("profundidad", PROFUNDIDAD_DEFECTO))
        except (OSError, TypeError, ValueError):
            continue
    return PROFUNDIDAD_DEFECTO


def _raices_desde_recientes() -> list[pathlib.Path]:
    """config.projects.recent (calipso/config.py) guarda, en texto plano,
    las rutas que Pedro ya abrio con /api/project/open. No hay nada que
    reconciliar: se resuelven y se verifica que sigan siendo un repo."""
    cfg = calipso_config.load_config()
    out = []
    for raw in cfg.get("projects", {}).get("recent", []) or []:
        try:
            p = pathlib.Path(str(raw)).expanduser().resolve()
        except OSError:
            continue
        if p.exists() and _es_repo(p):
            out.append(p)
    return out


def _raices_extra_por_slug(ya_encontrados: list[pathlib.Path]) -> list[pathlib.Path]:
    """Los slugs de ~/.calipso/projects/ (calipso/memory.py:_slug) son la
    unica pista que la memoria hibrida ya tiene de proyectos que el
    escaneo de raices, acotado a su profundidad declarada, no encuentra --
    tipicamente un worktree como calipso/.claude/worktrees/<rama>, que
    vive adentro de una carpeta oculta.

    El slug es CON PERDIDA: memory.py reemplaza cualquier caracter no
    alfanumerico -- "/" y "." incluidos -- por un solo "-", asi que dos
    rutas distintas pueden dar el mismo slug y no hay forma general de
    invertirlo. Por eso esta funcion no adivina una ruta a partir de un
    slug: busca mas hondo y acepta un candidato solo cuando SU slug,
    calculado hacia adelante, coincide exacto con uno de los que ya
    existen en ~/.calipso/projects/. Se confirma, nunca se infiere.

    Dos pasadas, en orden de costo:

    1. ADENTRO de los proyectos que el escaneo normal ya encontro, con
       carpetas ocultas permitidas. Es el caso real de esta maquina: un
       worktree vive en <repo>/.claude/worktrees/<rama>, y ese ".claude"
       esta adentro de un repo que "calipso" (por ejemplo) ya confirmo
       como proyecto -- la busqueda queda acotada al tamano de ESE repo,
       no del home entero.
    2. Si todavia falta algo, una pasada mas honda que la declarada (hasta
       PROFUNDIDAD_EXTRA_SLUGS) desde cada raiz, pero SIN carpetas
       ocultas -- mismo criterio que el escaneo normal, solo que mas
       profundo. Cubre un repo que este mas hondo que la profundidad
       declarada y que no sea un worktree anidado.

    Las dos van con techo de carpetas visitadas: un home con .cache,
    .mozilla o .npm gigantes no puede volver cara esta reconciliacion --
    y es justamente por eso que la pasada 1 no vale la pena hacerla desde
    la raiz entera con carpetas ocultas permitidas: antes de llegar a
    calipso/.claude, un recorrido asi se gasta el techo entero adentro de
    esas carpetas de cache, que ordenan antes alfabeticamente."""
    carpeta = calipso_home() / "projects"
    if not carpeta.is_dir():
        return []
    try:
        slugs_conocidos = {p.name for p in carpeta.iterdir() if p.is_dir()}
    except OSError:
        return []
    faltantes = slugs_conocidos - {_slug(p) for p in ya_encontrados}
    if not faltantes:
        return []
    extra: list[pathlib.Path] = []
    vistos = set(ya_encontrados)

    for base in ya_encontrados:
        if not faltantes:
            break
        anidados = _escanear_bajo(
            base, PROFUNDIDAD_EXTRA_SLUGS, permitir_ocultos=True,
            limite=LIMITE_CARPETAS_VISITADAS, descender_en_encontrados=True)
        for c in anidados:
            if c in vistos:
                continue
            s = _slug(c)
            if s in faltantes:
                extra.append(c)
                vistos.add(c)
                faltantes.discard(s)

    if faltantes:
        for r in raices_resueltas():
            if not faltantes:
                break
            candidatos = _escanear_bajo(
                r, PROFUNDIDAD_EXTRA_SLUGS, permitir_ocultos=False,
                limite=LIMITE_CARPETAS_VISITADAS)
            for c in candidatos:
                if c in vistos:
                    continue
                s = _slug(c)
                if s in faltantes:
                    extra.append(c)
                    vistos.add(c)
                    faltantes.discard(s)

    return extra


def escanear() -> list[dict[str, Any]]:
    """Un escaneo completo: recorre las raices declaradas, suma lo que ya
    se sabe por config.projects.recent, y reconcilia los slugs de
    ~/.calipso/projects/ que quedaron afuera. Corre como rutina
    (routines.KINDS suma "catastro"), no por turno -- escanear el home en
    cada mensaje no se paga (3.2). Preserva "departamento" (lo escribe
    Pedro, no el escaneo) y "visto" (orden de uso, no de escaneo) de la
    entrada previa cuando el proyecto ya estaba en el catastro."""
    encontrados: list[pathlib.Path] = []
    vistos: set[pathlib.Path] = set()
    for r in raices_resueltas():
        for c in _escanear_bajo(r, _profundidad_de(r)):
            if c not in vistos:
                vistos.add(c)
                encontrados.append(c)
    for c in _raices_desde_recientes():
        if c not in vistos:
            vistos.add(c)
            encontrados.append(c)
    for c in _raices_extra_por_slug(encontrados):
        if c not in vistos:
            vistos.add(c)
            encontrados.append(c)

    anteriores = {p["ruta"]: p for p in _cargar_json()["proyectos"]}
    ahora = datetime.datetime.now().isoformat(timespec="seconds")
    proyectos = []
    for ruta in encontrados:
        clave = str(ruta)
        previo = anteriores.get(clave)
        rama, commit = _rama_y_commit(ruta)
        proyectos.append({
            "ruta": clave,
            "nombre": ruta.name,
            "rama": rama,
            "ultimo_commit": commit,
            "resumen": _resumen_readme(ruta),
            "departamento": previo.get("departamento") if previo else None,
            "visto": (previo.get("visto") if previo else None) or ahora,
        })
    proyectos.sort(key=lambda p: p["visto"] or "", reverse=True)

    data = _cargar_json()
    data["proyectos"] = proyectos
    _guardar_json(data)
    return proyectos


def cargar(forzar_escaneo: bool = False) -> list[dict[str, Any]]:
    """Lista de proyectos, cacheada en catastro.json. Sin forzar, la
    PRIMERA lectura de la vida del catastro dispara un escaneo -- igual
    que `routines._cargar_estricto` siembra su seed la primera vez -- para
    que "que proyectos tengo" conteste bien desde el primer turno, sin
    esperar a que la rutina periodica tique por primera vez. De ahi en mas,
    la rutina "catastro" (calipso/routines.py, handler en
    calipso/server.py:_routine_handlers) es quien lo mantiene fresco:
    leer nunca vuelve a escanear el disco."""
    if forzar_escaneo or not _file().exists():
        return escanear()
    return _cargar_json()["proyectos"]


def obtener(nombre: str) -> dict[str, Any] | None:
    nombre_norm = nombre.strip().lower()
    for p in cargar():
        if p["nombre"].lower() == nombre_norm:
            return p
    return None


def nombres() -> list[str]:
    """Los nombres del catastro SIN escanear jamas: para el contrato del
    abismo, que corre en cada turno y en tests con home vacio. Un catastro
    que todavia no existe da una lista vacia; el escaneo de la primera vez
    sigue siendo de `cargar()` (lo dispara `proyectos_brief` en el mismo
    turno). Orden: el de `cargar`, por `visto` descendente -- los mas usados
    primero, que es lo que el recorte del contrato quiere conservar."""
    if not _file().exists():
        return []
    return [p["nombre"] for p in _cargar_json()["proyectos"]]
