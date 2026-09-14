"""
calipso/goals_runner.py - el bucle del goal (spec 2026-09-13, seccion 5).

`Runner.iteracion()` es UNA vuelta del bucle, sincrona y pura sobre
inyecciones (manos, juez, carga, consumo, pagador, preguntar,
evaluar_solicitud, sondear, clonar, diff, diff_completo, criterio, aduana): los
tests la llaman directo; en produccion el server la corre en hilo desde una
tarea asyncio propia por goal (`_GOALS_EN_CURSO`, cada GOAL_TICK_S).

Cada vuelta, con el goal `active`:
  0. si no hay clon, clona (o crea `trabajo/` para el goal sin repo); los
     dos viven en `goals.dir_trabajo(id)`, FUERA de ~/.calipso (ruling del
     controlador 2026-09-14: ~/.calipso es DENY_READ del sandbox y
     PROTEGIDA del hook, y el martillo tiene que leer su propio clon);
     antes del primer golpe sondea el hook (gh pr create -> exit 2) o
     `failed` motivo `hook inactivo` sin invocar nada (ruling 15.5);
  1. el tope (golpes, minutos, unidades, mm): `waiting` motivo `tope`;
  2. la carga: bajo `cargada` pospone sin gastar (fila carga/pospone);
  3. la cuota (consumo pasivo + el rate_limit del ultimo golpe): `waiting`
     motivo `cuota`, NUNCA el 7b ni la otra familia (ruling 15.12);
  4. la fila `inicio` del ledger, las compuertas, el contrato, el prompt (el
     ledger resumido con el diff_stat y las `falta` SIN recortar), el
     golpe (la cabeza ES el martillo: una sesion headless con herramientas,
     --resume entre golpes; ruling 15.1);
  5. despues: diff_stat (contra el `base_sha` de la rama del goal, no
     contra HEAD: el contrato manda commitear y un commit es diff nuevo),
     comandos, unidades reales, las compuertas usadas segun hook.jsonl (con
     la linea de deshacer de cada instalacion: spec 7/8, ruling 15.14), el
     detector de secretos, la fila de la aduana, el cobro, la fila `fin`;
  6. `cancelar` puesto (parar, apagar) -> la fila dice cancelado, no cuenta
     para el tope y la vuelta termina SIN juez ni transicion (transiciona el
     que cancelo); hook inactivo / mcp inesperado -> `failed`; fallo por
     cuota -> `waiting` cuota (no cuenta contra el tope de golpes); timeout
     -> cuenta;
  7. el veredicto: `preguntar` -> una solicitud estacionada (pregunta,
     compuerta o raiz_nueva; lo NUNCA no se pregunta) y `waiting`;
     `terminar` -> el juez: criterio medible primero (comando/archivo/
     numero; el comando corre CONFINADO bajo bwrap espejo del sandbox, con
     su Popen en `golpe_en_curso`: lo que ejecuta lo escribio el martillo),
     despues el revisor de OTRA familia (cuenta como golpe: su fila
     `inicio` va ANTES de invocarlo, invariante 3; la cuota de SU familia
     se mira antes de invocarlo; cruza la aduana y se cobra con sus
     unidades reales; `sin_golpe` apagado y su Popen en `golpe_en_curso`
     mientras corre; `independencia`; si falla, su fila dice por que);
     cumplido -> `waiting` motivo `cumplido` con la solicitud `cerrar` para
     Pedro; no cumplido -> la `falta` al ledger y el martillo sigue; sin
     otra familia -> Pedro sin veredicto de modelo;
  8. no convergencia (tres golpes sin diff nuevo, la misma falta dos veces,
     el mismo comando fallando igual) -> `waiting` con diagnostico y
     opciones; y el tope, de nuevo.
Con el goal `waiting` mira la solicitud (aprobada/negada) y retoma o cierra;
todo waiting que no espera nada del martillo (tope, cuota, no convergencia;
parado y server apagado/reiniciado los estaciona el server) lleva una
solicitud `retomar` (`estacionar_retomar`: Pedro no se pierde), y sin
solicitud la vuelta devuelve `nada` (el bucle no gira en vano).
Nunca levanta: cualquier excepcion deja el goal `failed` con motivo
(invariante 6); un ErrorGoal (otro goal en curso) deja evento y telemetria,
nunca pasa en silencio.

`goals.escribir` es last-writer-wins (salvo `status`): el runner recarga el
goal con `goals.load` inmediatamente antes de cada `escribir` (Pedro puede
haber sumado preautorizadas, raices o una nota por el inbox mientras el
golpe corria). La fila 0 del ledger es la propuesta (`_proponer_goal`, sin
herramientas): no es un golpe del martillo y queda fuera del resumen, del
numero del golpe siguiente y de la no convergencia.
"""
from __future__ import annotations

import contextlib
import json
import os
import pathlib
import subprocess
import threading
import time
from typing import Callable

from calipso import github as calipso_github
from calipso import goals
from calipso import goals_hook
from calipso import goals_manos as gm
from calipso import telemetry

GOAL_TICK_S = 5.0
INDEPENDENCIAS = ("proveedor_distinto", "modelo_distinto_mismo_cliente", "ninguna")
MOTIVOS_WAITING = ("tope", "cuota", "no_convergencia", "cumplido", "pregunta", "compuerta",
                   "raiz_nueva", "parado por Pedro", "server apagado", "server reiniciado")
CUOTA_CODEX_MAX = 90.0
CUOTA_CLAUDE_MAX = 0.95
OPCIONES_NO_CONVERGENCIA = ("cambiar el plan (/goal segui <nota con el plan nuevo>)",
                            "pedir a Pedro (contesta lo que falta con /goal segui <nota>)",
                            "cambiar de manos (/goal segui con: codex|claude)",
                            "achicar el alcance (/goal no y un /goal mas chico)")


def _cwd_de(goal: dict) -> str:
    """El cwd del golpe: el clon, o `trabajo/` bajo dir_trabajo (goal sin repo)."""
    return goal.get("repo") or str(goals.dir_trabajo(goal["id"]) / "trabajo")


def _golpes_del_martillo(filas: list[dict]) -> list[dict]:
    """Las filas del ledger que son golpes (o revisiones): la fila 0 de la
    propuesta (`tipo: propuesta`) queda afuera."""
    return [f for f in filas if f.get("tipo") != "propuesta"]


def _siguiente_n(filas: list[dict]) -> int:
    """El numero del golpe que viene: max(n) + 1 (con la propuesta en la
    fila 0, `len + 1` etiquetaria el primer golpe como 2)."""
    return max((int(f.get("n") or 0) for f in filas), default=0) + 1


# --------------------------------------------------------------------------
# textos: el contrato, el prompt, el resumen del ledger
# --------------------------------------------------------------------------

def contrato_del_goal(goal: dict) -> str:
    """El system del golpe (`--append-system-prompt-file`, fuera del clon).
    Lo que se hace con el trabajo depende de las manos: claude commitea en
    la rama del clon; codex NO (ruling del controlador, Task 7: bajo
    `codex exec -s workspace-write` el .git del clon es de solo lectura y
    cada golpe gastaba intentando commitear; el runner mide el diff del
    arbol contra base_sha, asi que el trabajo sin commitear cuenta igual)."""
    c = goal.get("compuertas") or {}
    niveles = c.get("niveles") or goals.NIVEL_DE
    if (goal.get("manos") or "claude") == "codex":
        cierre = ("No commitees: el .git es de solo lectura en tu sandbox; el runner mide el diff del "
                  "arbol contra base_sha.")
    else:
        cierre = "commitea en la rama del clon lo que termines."
    lineas = [
        "CONTRATO DEL GOAL (Calipso, 2026-09-13)",
        f"goal: {goal.get('id')} -- {goal.get('title')}",
        f"objetivo: {goal.get('objective')}",
        f"criterio de listo: {json.dumps(goal.get('criterio') or {}, ensure_ascii=False)}",
        f"tope: {json.dumps(goal.get('tope') or {}, ensure_ascii=False)} (el primero que se alcance para)",
        f"cwd: {goal.get('repo') or 'carpeta de trabajo vacia (goal sin repo)'}",
        f"raices fuera del repo (lectura y escritura): {', '.join(c.get('raices') or []) or 'ninguna'}",
        f"dominios de red: {', '.join(goal.get('dominios') or []) or 'ninguno (solo api.anthropic.com)'}",
        "compuertas: directo = " + ", ".join(f for f, n in niveles.items() if n == "directo")
        + "; pregunta = " + ", ".join(f for f, n in niveles.items() if n == "pregunta")
        + "; NUNCA = " + ", ".join(f for f, n in niveles.items() if n == "nunca"),
        "plan: " + " -> ".join(goal.get("plan") or []) if goal.get("plan") else "plan: el que armes",
        "",
        "Reglas: sos las manos de Calipso dentro de un sandbox; trabaja solo en el cwd y las raices; "
        "no hagas push, PR, correo, gastos ni toques datos de Pedro (el hook lo deniega y el sandbox lo "
        "impide); instala solo dentro del cwd (venv, npm sin -g); si necesitas una compuerta en "
        "pregunta (instalar en el home o el sistema, borrar fuera, una raiz nueva), termina el golpe con "
        "estado \"preguntar\", la pregunta y la compuerta (familia y forma exacta); " + cierre
        + " Termina SIEMPRE con el veredicto del esquema: estado sigo (hay mas "
        "por hacer), terminar (creo que el criterio se cumple: el juez lo verifica), preguntar; y un "
        "resumen de una o dos lineas de lo que hiciste.",
    ]
    return "\n".join(lineas)


def resumen_ledger(filas: list[dict]) -> str:
    """El ledger resumido para el prompt y el revisor: por golpe, el
    veredicto, los comandos (con la cola del resultado), el diff_stat y las
    `falta` del juez SIN recortar (spec seccion 5.2)."""
    out = []
    for f in _golpes_del_martillo(filas):
        v = f.get("veredicto_del_golpe") or {}
        out.append(f"golpe {f.get('n')} ({f.get('manos')}): {v.get('estado', f.get('motivo') or '?')} - "
                   f"{v.get('resumen', '')}")
        for c in (f.get("comandos") or [])[:12]:
            cola = (c.get("resultado_tail") or "").strip().replace("\n", " ")[-120:]
            out.append(f"  $ {c.get('cmd')}" + (f" -> {cola}" if cola else ""))
        if f.get("diff_stat"):
            out.append("  diff: " + f["diff_stat"].replace("\n", "; ")[:600])
        j = f.get("juez") or {}
        if j.get("criterio"):
            out.append(f"  criterio: {'ok' if j['criterio'].get('ok') else 'NO'} - {j['criterio'].get('salida', '')[:300]}")
        if j.get("falta"):
            out.append("  falta segun el revisor (" + str(j.get("revisor") or "") + "):")
            out.extend(f"   - {x}" for x in j["falta"])
        if j.get("nota"):
            out.append(f"  nota del revisor: {j['nota']}")
        if f.get("veredicto_invalido"):
            out.append("  (el veredicto de este golpe no fue valido)")
    return "\n".join(out)


def prompt_del_golpe(goal: dict, filas: list[dict], nota: str | None = None) -> str:
    golpes = _golpes_del_martillo(filas)
    n = _siguiente_n(filas)
    partes = [f"GOLPE {n} del goal: {goal.get('objective')}"]
    if golpes:
        partes.append("LO QUE PASO HASTA AHORA:\n" + resumen_ledger(golpes))
        ultimo = golpes[-1]
        if ultimo.get("veredicto_invalido"):
            partes.append("Tu veredicto anterior no fue valido (no era el JSON del esquema): "
                          "termina este golpe con el veredicto correcto.")
        criterio = (ultimo.get("juez") or {}).get("criterio") or {}
        if criterio.get("ok") is False:
            partes.append("El criterio medible NO se cumplio: " + str(criterio.get("salida", "")))
    else:
        partes.append("Es el primer golpe: lee lo que haga falta y arranca por el plan.")
    if nota:
        partes.append("NOTA DE PEDRO: " + nota)
    partes.append("Al terminar este golpe, el veredicto del esquema (sigo | terminar | preguntar).")
    return "\n\n".join(partes)


# --------------------------------------------------------------------------
# las compuertas usadas y la linea de deshacer (spec 7/8, ruling 15.14)
# --------------------------------------------------------------------------

def linea_de_deshacer(familia: str | None, forma: dict | None) -> str | None:
    """La linea que deshace una instalacion, derivada de la forma concreta
    que anoto el hook: pip -> `uninstall -y`, npm/pnpm -> `uninstall`,
    yarn -> `remove`, flatpak -> `uninstall` con el mismo --user/--system,
    rpm-ostree -> `uninstall`. None si no es una instalacion o no hay
    paquetes sueltos (-r requirements, -e .). El estado antes/despues
    (`pip list`, `npm ls`, `flatpak list`) NO se toma en esta tanda."""
    if not familia or not str(familia).startswith("instalar"):
        return None
    argv = [str(t) for t in ((forma or {}).get("argv") or [])]
    if not argv:
        return None
    base = os.path.basename(argv[0])
    es_pip = base in ("pip", "pip3") or argv[1:3] == ["-m", "pip"] or (base == "uv" and argv[1:2] == ["pip"])
    if es_pip:
        i = next((k for k, t in enumerate(argv) if t == "install"), None)
        if i is None:
            return None
        resto = argv[i + 1:]
        if any(t in ("-r", "--requirement", "-e", "--editable") for t in resto):
            return None
        paquetes = [t for t in resto if not t.startswith("-")]
        return " ".join(argv[:i] + ["uninstall", "-y", *paquetes]) if paquetes else None
    if base in ("npm", "pnpm", "yarn"):
        if base == "yarn" and argv[1:3] == ["global", "add"]:
            paquetes = [t for t in argv[3:] if not t.startswith("-")]
            return " ".join([base, "global", "remove", *paquetes]) if paquetes else None
        i = next((k for k, t in enumerate(argv) if t in ("install", "i", "ci", "add")), None)
        if i is None:
            return None
        paquetes = [t for t in argv[i + 1:] if not t.startswith("-")]
        if not paquetes:
            return None
        g = ["-g"] if any(t in ("-g", "--global") for t in argv) else []
        return " ".join([base, "remove" if base == "yarn" else "uninstall", *g, *paquetes])
    if base == "flatpak" and "install" in argv:
        ambito = [t for t in argv if t in ("--user", "--system")]
        pos = [t for t in argv[argv.index("install") + 1:] if not t.startswith("-")]
        return " ".join(["flatpak", "uninstall", *ambito, pos[-1]]) if pos else None
    if base == "rpm-ostree" and "install" in argv:
        paquetes = [t for t in argv[argv.index("install") + 1:] if not t.startswith("-")]
        return " ".join(["rpm-ostree", "uninstall", *paquetes]) if paquetes else None
    return None


def _lineas_de(ruta: str) -> int:
    try:
        with open(ruta, "r", encoding="utf-8", errors="replace") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def compuertas_usadas(registro: str, desde: int = 0) -> list[dict]:
    """Las decisiones del hook (hook.jsonl, goals_hook.anotar) desde la
    linea `desde` que tocaron una compuerta de la tabla (las de un comando
    simple, sin familia, no): familia, forma, decision, resumen y la linea
    de deshacer. Van a la fila `fin` (`compuertas_usadas`) y a la carga del
    cruce de la aduana (spec seccion 8)."""
    out: list[dict] = []
    try:
        with open(registro, "r", encoding="utf-8", errors="replace") as f:
            lineas = f.readlines()[desde:]
    except OSError:
        return out
    for l in lineas:
        try:
            fila = json.loads(l)
        except json.JSONDecodeError:
            continue
        if not fila.get("familia"):
            continue
        out.append({"ts": fila.get("ts"), "tool": fila.get("tool"), "decision": fila.get("decision"),
                    "familia": fila.get("familia"), "forma": fila.get("forma"),
                    "resumen": fila.get("resumen"),
                    "deshacer": linea_de_deshacer(fila.get("familia"), fila.get("forma"))})
        if len(out) >= 50:
            break
    return out


# --------------------------------------------------------------------------
# no convergencia (ruling 15.8) y el criterio medible
# --------------------------------------------------------------------------

def _tail_fallido(c: dict) -> str | None:
    """La cola de un comando que FALLO segun el `is_error` del tool_result
    (Parser: comandos[].error); None si salio bien o no se sabe (un ledger
    viejo sin la clave). Antes se decidia por substring ('error', 'failed',
    'traceback') y dos `ls` con errors.py en la salida eran no
    convergencia con diagnostico falso."""
    if c.get("error") is True:
        return (c.get("resultado_tail") or "").lower()
    return None


def no_converge(filas: list[dict]) -> str | None:
    golpes = _golpes_del_martillo(filas)
    fin = [f for f in golpes if f.get("fase") == "fin" and not (f.get("manos") or "").startswith("revisor:")]
    if len(fin) >= 3:
        ultimos = [f.get("diff_stat") or "" for f in fin[-3:]]
        if ultimos[0] == ultimos[1] == ultimos[2]:
            return "tres golpes seguidos sin diff nuevo en el clon"
    con_juez = [f for f in golpes if (f.get("juez") or {}).get("falta")]
    if len(con_juez) >= 2:
        a = sorted(str(x) for x in con_juez[-1]["juez"]["falta"])
        b = sorted(str(x) for x in con_juez[-2]["juez"]["falta"])
        if a == b:
            return "la misma falta del revisor dos veces seguidas: " + "; ".join(a)
    if len(fin) >= 2:
        prev = {c.get("cmd"): _tail_fallido(c) for c in fin[-2].get("comandos") or []}
        for c in fin[-1].get("comandos") or []:
            t = _tail_fallido(c)
            if t and prev.get(c.get("cmd")) == t:
                return f"el mismo comando fallando igual dos golpes seguidos: {c.get('cmd')}"
    return None


def _correr_criterio(comando: str, cwd: str, *, goal: dict, al_lanzar: Callable | None = None,
                     cancelar: threading.Event | None = None, n: int | None = None,
                     usar_systemd: bool | None = None) -> tuple[bool, str]:
    """El comando del criterio en el clon, salida 0 = cumplido. SIN shell:
    `goals_hook.partir` lo tokeniza y rechaza compuestos (`;`, `&&`, `|`,
    `$(`...) -- un criterio compuesto no se corre, falla. Y CONFINADO
    (critico del cierre 2026-09-14): lo que ejecuta (conftest.py, check.py,
    un Makefile) lo escribio el martillo en el clon, asi que corre bajo la
    misma barrera del golpe (goals_manos.correr_confinado: bwrap espejo del
    sandbox, sin red, home de solo lectura, DENY_READ tapado, env del golpe
    con CALIPSO_HOME vacio), en su scope `calipso-goal-<id>-criterio-<n>`,
    con el Popen publicado en el runner (parar/apagar lo matan) y 10
    minutos de tope. Sin bwrap no se corre: el juez dice por que."""
    argv = goals_hook.partir(comando)
    if argv is None:
        return False, "criterio compuesto o vacio: no se corre (usa un comando simple)"
    carpeta = goals.dir_goal(goal["id"])
    home_vacio = carpeta / "home_vacio"
    home_vacio.mkdir(exist_ok=True)
    env = gm.env_del_golpe(str(carpeta / "compuertas.json"), str(home_vacio))
    unidad = f"calipso-goal-{goal['id']}-criterio-{n}" if n else None
    r = gm.correr_confinado(argv, cwd=cwd, compuertas=goals.compuertas_de(goal),
                            timeout_s=gm.CRITERIO_TIMEOUT_S, unidad=unidad, al_lanzar=al_lanzar,
                            cancelar=cancelar, env=env, usar_systemd=usar_systemd)
    salida = ((r.stdout_tail or "") + (r.stderr_tail or "")).strip()[-1500:]
    if r.timeout:
        return False, f"el comando del criterio vencio a los {gm.CRITERIO_TIMEOUT_S} s"
    if r.motivo:
        return False, r.motivo + (f": {salida}" if salida else "")
    return r.exit == 0, salida or f"exit {r.exit}"


def juzgar_criterio(goal: dict, correr: Callable | None, *, al_lanzar: Callable | None = None,
                    cancelar: threading.Event | None = None, n: int | None = None,
                    usar_systemd: bool | None = None) -> tuple[bool | None, str]:
    """(None, motivo) si no hay criterio medible; si no (ok, salida). Los
    kwargs son para el criterio comando real: el runner publica su proceso
    (`al_lanzar`), lo corta (`cancelar`) y lo nombra (`n`)."""
    c = goal.get("criterio") or {}
    tipo = c.get("tipo")
    cwd = _cwd_de(goal)
    if tipo == "comando":
        if correr is not None:
            return correr(goal)
        return _correr_criterio(str(c.get("comando") or ""), cwd, goal=goal, al_lanzar=al_lanzar,
                                cancelar=cancelar, n=n, usar_systemd=usar_systemd)
    if tipo == "archivo":
        p = pathlib.Path(cwd) / str(c.get("ruta") or "")
        if not p.exists():
            return False, f"{p} no existe"
        if c.get("contiene") and c["contiene"] not in p.read_text(encoding="utf-8", errors="replace"):
            return False, f"{p} no contiene {c['contiene']!r}"
        return True, f"{p} existe"
    if tipo == "numero":
        consumo = goals.consumo(goal)
        valor = consumo.get(str(c.get("metrica")))
        if valor is None:
            return False, f"metrica desconocida: {c.get('metrica')}"
        umbral = float(c.get("umbral"))
        comp = c.get("comparacion") or "<="
        ok = {"<=": valor <= umbral, "<": valor < umbral, ">=": valor >= umbral, ">": valor > umbral,
              "==": valor == umbral}.get(comp, False)
        return ok, f"{c.get('metrica')} = {valor} {comp} {umbral}"
    return None, "sin criterio medible"


# --------------------------------------------------------------------------
# las manos reales: el golpe sobre el CLI (claude o codex)
# --------------------------------------------------------------------------

# Lo que la fila del golpe dice cuando la eleccion --session-id/--resume se
# corrigio con lo que contesto el CLI (clave: el `resume` corregido).
REINTENTOS_DE_SESION = {True: "--session-id en uso -> --resume",
                        False: "sesion no encontrada -> --session-id"}


def correccion_de_sesion(r: gm.Resultado, resume: bool,
                         cancelar: threading.Event | None = None) -> bool | None:
    """Pura. Si claude aborto por la eleccion --session-id / --resume,
    devuelve el `resume` corregido; None si no hay que reintentar. El
    ledger puede adivinar mal: el server murio durante el golpe 1 y la
    reconciliacion cerro la fila sin session_id, pero el CLI SI persistio
    la sesion en ~/.claude/projects/<slug del clon>/ (HOME es el real, el
    cwd es siempre el clon) y `--session-id` aborta con `Session ID x is
    already in use.`; o la fila tiene sesion y el CLI no la persistio, y
    `--resume` aborta con `No conversation found with session ID: x`
    (los dos textos, verificados en el binario 2.1.270). En ambos casos el
    CLI corta antes de tocar la API (exit 1, sin linea init: no gasta
    cuota, no deja veredicto), asi que su texto es la verdad y el mismo
    golpe se relanza con la otra eleccion. Nada con exit 0, matado
    (timeout, parar) o `cancelar` puesto; un solo sentido por vez (el
    llamador reintenta UNA vez: dos correcciones contradictorias no forman
    un bucle). El texto se busca en stderr y en stdout."""
    if r.exit in (0, None) or r.matado or (cancelar is not None and cancelar.is_set()):
        return None
    texto = f"{r.stderr_tail or ''}\n{r.stdout_tail or ''}"
    if not resume and "is already in use" in texto:
        return True
    if resume and "No conversation found with session ID" in texto:
        return False
    return None


def manos_con_cli(exes: dict, *, timeout_s: int | None = None,
                  usar_systemd: bool | None = None,
                  al_lanzar: Callable | None = None) -> Callable:
    """Devuelve `manos(goal, n, prompt, contrato, cancelar) -> Resultado`
    sobre `goals_manos.golpear`: arma settings (sandbox + hook), argv
    (claude: --resume si el ledger tiene una fila de claude con la sesion
    del goal, si no --session-id -- tras golpes con codex o un golpe
    cortado antes de que el CLI persistiera la sesion; y como el ledger
    puede adivinar mal, la eleccion se autocorrige con lo que contesta el
    CLI: `correccion_de_sesion` relanza el MISMO golpe con la otra
    eleccion, una sola vez, sin fila extra ni cuota, y la fila lo dice en
    `reintento`; codex: -o y --output-schema en archivos del goal), env
    (CALIPSO_GOAL_COMPUERTAS, CALIPSO_HOME vacio), escribe el contrato
    FUERA del clon y lanza con la unidad `calipso-goal-<id>-<n>` (el
    compuertas.json se relee en CADA golpe: la raiz que Pedro aprobo por
    raiz_nueva entra al golpe siguiente como --add-dir y allowWrite; el
    reintento, `-<n>-r`). `al_lanzar` (= `runner.registrar_golpe`)
    publica el Popen en el runner apenas existe (decision 17)."""
    def manos(goal: dict, n: int, prompt: str, contrato: str,
              cancelar: threading.Event | None) -> gm.Resultado:
        carpeta = goals.dir_goal(goal["id"])
        cwd = _cwd_de(goal)
        pathlib.Path(cwd).mkdir(parents=True, exist_ok=True)
        home_vacio = carpeta / "home_vacio"
        home_vacio.mkdir(exist_ok=True)
        ruta_contrato = carpeta / "contrato.md"
        ruta_contrato.write_text(contrato, encoding="utf-8")
        compuertas_path = str(carpeta / "compuertas.json")
        compuertas = json.loads(pathlib.Path(compuertas_path).read_text(encoding="utf-8"))
        env = gm.env_del_golpe(compuertas_path, str(home_vacio))
        cliente = goal.get("manos") or "claude"
        exe = (exes or {}).get(cliente)
        if not exe:
            return gm.Resultado(exit=127, motivo=f"{cliente} no esta instalado")
        tout = timeout_s or gm.GOLPE_TIMEOUT_S()
        unidad = f"calipso-goal-{goal['id']}-{n}"
        if cliente == "claude":
            settings = gm.settings_del_goal(compuertas, compuertas_path=compuertas_path)
            resume = any(f.get("manos") == "claude" and f.get("session_id") == goal["session_id"]
                         for f in goals.golpes(goal["id"]))

            def _golpe(resume: bool, unidad: str) -> gm.Resultado:
                argv = gm.argv_claude(exe, contrato=str(ruta_contrato), settings=settings,
                                      schema=gm.ESQUEMA_VEREDICTO, session_id=goal["session_id"],
                                      resume=resume, model=_modelo_claude(goal),
                                      web=bool(goal.get("dominios")),
                                      raices=list(compuertas.get("raices") or []))
                return gm.golpear(argv=argv, stdin=prompt, cwd=cwd, env=env, timeout_s=tout,
                                  cancelar=cancelar, usar_systemd=usar_systemd, unidad=unidad,
                                  al_lanzar=al_lanzar)
            r = _golpe(resume, unidad)
            corregido = correccion_de_sesion(r, resume, cancelar)
            if corregido is not None:
                # el ledger adivino mal y el CLI aborto antes de la API: el
                # MISMO golpe con la otra eleccion, una sola vez, misma fila
                r = _golpe(corregido, f"{unidad}-r")
                r.reintento = REINTENTOS_DE_SESION[corregido]
            return r
        salida = carpeta / f"codex-{n}.json"
        schema_file = carpeta / "esquema-veredicto.json"
        # el modo estricto de OpenAI (smoke corrida 3): sin esto codex sale 1 antes de la primera llamada
        schema_file.write_text(json.dumps(gm.esquema_para_codex(gm.ESQUEMA_VEREDICTO)), encoding="utf-8")
        argv = gm.argv_codex(exe, cwd=cwd, raices=list(compuertas.get("raices") or []),
                             salida=str(salida), schema_file=str(schema_file))
        r = gm.golpear(argv=argv, stdin=f"{contrato}\n\n{prompt}", cwd=cwd, env=env, timeout_s=tout,
                       cancelar=cancelar, usar_systemd=usar_systemd, unidad=unidad, al_lanzar=al_lanzar)
        if r.veredicto is None and salida.exists():
            try:
                v = json.loads(salida.read_text(encoding="utf-8"))
                r.veredicto = gm.sin_nulos(v) if isinstance(v, dict) else None
            except (OSError, json.JSONDecodeError):
                pass
        if r.unidades == 0 and r.exit == 0:
            r.unidades = 1        # No confirmado 7: sin las lineas --json parseadas, al menos una llamada
        return r
    return manos


def _modelo_claude(goal: dict) -> str | None:
    """La cabeza que eligio el ruteo al proponer (`_proponer_goal` guarda
    `propuesta["modelo"]` = el model del top del ranking); sin eso, opus
    (piso frontera: el martillo nunca corre con un tier menor)."""
    m = ((goal.get("propuesta") or {}).get("modelo") or "").lower()
    return m if m in ("opus", "sonnet", "haiku") else "opus"


# --------------------------------------------------------------------------
# Pedro no se pierde: la solicitud `retomar` de un waiting sin martillo
# --------------------------------------------------------------------------

OPCIONES_RETOMAR = {
    "tope": ("si = seguir con el tope ampliado un 50 %",
             "no = cancelar el goal",
             "por el chat: /goal segui tope: <N golpes | Nm | N unidades>"),
    "cuota": ("si = reintentar cuando la ventana se libere",
              "no = cancelar el goal",
              "por el chat: /goal segui con: claude|codex (la otra familia)"),
    "no_convergencia": OPCIONES_NO_CONVERGENCIA,
}
OPCIONES_RETOMAR_DEFECTO = ("si = seguir donde quedo", "no = cancelar el goal",
                            "por el chat: /goal segui <nota>")


def _motivo_legible(goal: dict, espera: dict) -> str:
    """Lo que Pedro lee en el titulo de la solicitud: el motivo con el
    consumo contra el tope (tope), la familia (cuota) o el diagnostico
    (no convergencia)."""
    motivo = str(espera.get("motivo") or "")
    t = {**goals.TOPE_DEFECTO, **(goal.get("tope") or {})}
    c = goals.consumo(goal)
    consumo = (f"{c['golpes']}/{t['golpes']} golpes, {c['minutos']}/{t['minutos']} min, "
               f"{c['unidades']}/{t['unidades']} unidades")
    if motivo == "tope":
        return f"tope de {espera.get('tope') or '?'} alcanzado ({consumo})"
    if motivo == "cuota":
        return f"cuota de {espera.get('manos') or goal.get('manos')} agotada ({consumo})"
    if motivo == "no_convergencia":
        return f"no converge: {str(espera.get('diagnostico') or '')[:80]} ({consumo})"
    return f"{motivo} ({consumo})"


def estacionar_retomar(goal: dict, preguntar: Callable) -> dict:
    """Un waiting que no espera nada del martillo (goals.MOTIVOS_RETOMAR:
    tope, cuota, no convergencia, parado, server apagado/reiniciado) no
    aparecia en el inbox ni en el chat y Pedro se perdia justo ahi
    (rev:lente-spec, ruling del cierre). Estaciona una solicitud `retomar`
    (familia goal, siempre pregunta) por `preguntar(goal, "retomar", forma,
    titulo, n)` = `_estacionar_para_pedro` en el server, con la forma
    `{motivo, vez}` (la vez la hace unica: la pared de corrida y la
    idempotencia por forma del motor devolverian la solicitud ANTERIOR,
    ya contestada, y el goal retomaria solo), el titulo `goal: <titulo> --
    <motivo>: seguir?` y, en la espera, el consumo y las opciones. Deja
    `espera.solicitud` (recarga antes de escribir) y el evento
    `retomar_estacionado`. La usa el runner al dejar waiting por tope,
    cuota o no convergencia, y el server al parar, apagar y reconciliar.
    Sin motor (preguntar devuelve None) la espera queda sin solicitud."""
    g = goals.load(None, goal["id"]) or goal
    espera = dict(g.get("espera") or {})
    motivo = str(espera.get("motivo") or "")
    vez = 1 + sum(1 for e in goals.events(None, g["id"]) if e.get("action") == "retomar_estacionado")
    titulo = f"goal: {g.get('title')} -- {_motivo_legible(g, espera)}: seguir?"[:200]
    s = preguntar(g, "retomar", {"motivo": motivo, "vez": vez}, titulo, vez) or {}
    espera["solicitud"] = s.get("id")
    espera["consumo"] = goals.consumo(g)
    espera.setdefault("opciones", list(OPCIONES_RETOMAR.get(motivo, OPCIONES_RETOMAR_DEFECTO)))
    espera["vez"] = vez
    g["espera"] = espera
    goals.escribir(g)
    goals.event(None, g["id"], "retomar_estacionado", motivo=motivo, vez=vez, solicitud=s.get("id"))
    return g


# --------------------------------------------------------------------------
# el runner
# --------------------------------------------------------------------------

class Runner:
    def __init__(self, goal_id: str, *, manos: Callable | None = None, juez: Callable,
                 carga_fn: Callable, consumo_fn: Callable, pagador_fn: Callable,
                 preguntar: Callable, evaluar_solicitud: Callable,
                 sondear: Callable | None = None, clonar: Callable | None = None,
                 diff_fn: Callable | None = None, diff_completo_fn: Callable | None = None,
                 correr_criterio: Callable | None = None,
                 aduana_fn: Callable | None = None, telemetria: Callable | None = None,
                 usar_systemd: bool | None = None) -> None:
        """`manos` None = se asigna despues: las manos reales necesitan
        `runner.registrar_golpe` (server._runner_de las arma en dos pasos).
        `usar_systemd` es para el criterio confinado (None = si hay
        systemd-run; los tests ponen False)."""
        self.goal_id = goal_id
        self.manos = manos
        self.juez = juez
        self.carga_fn = carga_fn
        self.consumo_fn = consumo_fn
        self.pagador_fn = pagador_fn
        self.preguntar = preguntar
        self.evaluar_solicitud = evaluar_solicitud
        self.sondear = sondear or self._sondear_real
        self.clonar = clonar or self._clonar_real
        self.diff_fn = diff_fn or self._diff_real
        self.diff_completo_fn = diff_completo_fn or self._diff_completo_real
        self.correr_criterio = correr_criterio
        self.usar_systemd = usar_systemd
        self.aduana_fn = aduana_fn or (lambda *a, **k: None)
        self.telemetria = telemetria or telemetry.log_event
        self.cancelar = threading.Event()
        self.sin_golpe = threading.Event()      # apagado mientras corre un golpe
        self.sin_golpe.set()
        self.golpe_en_curso: subprocess.Popen | None = None
        self.unidad_en_curso: str | None = None
        self.hook_sondeado = False

    # -- inyecciones por defecto (produccion) --
    @staticmethod
    def _sondear_real(compuertas_path: str) -> tuple[bool, str]:
        return gm.sondear_hook(compuertas_path)

    @staticmethod
    def _clonar_real(goal: dict) -> dict:
        destino = str(goals.dir_trabajo(goal["id"]) / "repo")
        return calipso_github.clonar_para_goal(goal["proyecto"], destino, f"goal/{goal['id']}")

    @staticmethod
    def _diff_real(goal: dict) -> str:
        """Contra el `base_sha` de la rama del goal (lo guardo el clon), no
        contra HEAD: el contrato manda commitear al cerrar cada golpe, y
        contra HEAD un golpe que commiteo daria '' (falsa no convergencia y
        un revisor sin diff). Sin base (clon viejo), HEAD."""
        if goal.get("repo"):
            return calipso_github.diff_stat(goal["repo"], base=goal.get("base_sha") or "HEAD")
        trabajo = goals.dir_trabajo(goal["id"]) / "trabajo"
        return "\n".join(f"?? {p.relative_to(trabajo)}" for p in sorted(trabajo.rglob("*")) if p.is_file())

    @staticmethod
    def _diff_completo_real(goal: dict) -> str:
        """El diff REAL para el revisor (ruling 15.1), acumulado desde el
        `base_sha`; sin repo, el contenido de la carpeta de trabajo."""
        if goal.get("repo"):
            return calipso_github.diff_completo(goal["repo"], base=goal.get("base_sha") or "HEAD")
        trabajo = goals.dir_trabajo(goal["id"]) / "trabajo"
        partes = []
        for p in sorted(trabajo.rglob("*")):
            if p.is_file():
                with contextlib.suppress(OSError):
                    partes.append(f"?? {p.relative_to(trabajo)}\n"
                                  + p.read_text(encoding="utf-8", errors="replace")[:8000])
        return "\n".join(partes)[:calipso_github.DIFF_COMPLETO_MAX]

    def registrar_golpe(self, proc: subprocess.Popen | None, unidad: str | None = None) -> None:
        """`al_lanzar` de goals_manos.golpear (decision 17): el handle del
        Popen y la unidad del scope de systemd (None sin systemd) viven aca
        mientras el golpe corre; `matar_golpe` los usa: sin la unidad, lo
        que un script del clon deje en otra sesion (setsid/nohup adentro de
        ./script.sh: el hook no lo ve) sobrevivia al killpg hasta
        RuntimeMaxSec."""
        self.golpe_en_curso = proc
        self.unidad_en_curso = unidad if proc is not None else None

    def esperar_golpe(self, plazo: float) -> bool:
        """True si no hay golpe en curso (o termino antes de `plazo`): el
        apagado, /goal parar y /goal no lo esperan antes de transicionar,
        asi la fila `fin` y el cobro quedan escritos."""
        return self.sin_golpe.wait(plazo)

    def matar_golpe(self) -> None:
        proc = self.golpe_en_curso
        if proc is not None and proc.poll() is None:
            gm.matar(proc, self.unidad_en_curso)

    # -- una vuelta --
    def iteracion(self) -> dict:
        goal = goals.load(None, self.goal_id)
        if goal is None:
            return {"accion": "nada", "estado": None}
        try:
            if goal.get("status") == goals.WAITING or (goal.get("status") == goals.PROPOSED
                                                        and (goal.get("espera") or {}).get("solicitud")):
                return self._esperando(goal)
            if goal.get("status") in goals.FINAL_STATES:
                self._limpiar_preautorizadas(goal)      # expira con el goal (decision 9)
                return {"accion": "nada", "estado": goal.get("status")}
            if goal.get("status") != goals.ACTIVE:
                return {"accion": "nada", "estado": goal.get("status")}
            return self._activo(goal)
        except goals.ErrorGoal as exc:
            # nunca en silencio: evento y telemetria (otro goal en curso, un
            # status viejo en memoria...)
            estado = (goals.load(None, self.goal_id) or {}).get("status")
            with contextlib.suppress(Exception):
                goals.event(None, self.goal_id, "error", error=str(exc), estado=estado)
                self.telemetria("goal", accion="error", goal_id=self.goal_id, error=str(exc))
            return {"accion": "nada", "estado": estado, "error": str(exc)}
        except Exception as exc:  # invariante 6: nunca tumba nada
            try:
                g = goals.transicionar(self.goal_id, goals.FAILED, f"el runner revento: {exc}")
                self._limpiar_preautorizadas(g)
            except Exception:
                pass
            return {"accion": "failed", "estado": goals.FAILED, "error": str(exc)}

    # -- waiting --
    @staticmethod
    def _respuesta(r) -> tuple[str | None, str | None]:
        """Lo que devuelve `evaluar_solicitud`: 'aprobada' | 'negada' | None,
        o con la nota que Pedro escribio al responder (carril 3, `solicitud
        ["nota"]`) como (estado, nota) o {estado, nota}."""
        if isinstance(r, tuple):
            return (r[0] if r else None), (str(r[1]) if len(r) > 1 and r[1] else None)
        if isinstance(r, dict):
            return r.get("estado"), (str(r["nota"]) if r.get("nota") else None)
        return r, None

    def _esperando(self, goal: dict) -> dict:
        espera = goal.get("espera") or {}
        sid = espera.get("solicitud")
        if not sid:
            # nada que sondear: el bucle termina (dale/segui relanzan). Un
            # waiting sin solicitud no deberia existir (cada motivo estaciona
            # la suya), pero si existe no gira en vano leyendo goal.json
            return {"accion": "nada", "estado": goal["status"], "motivo": espera.get("motivo")}
        r, nota = self._respuesta(self.evaluar_solicitud(sid))
        if r is None:
            return {"accion": "esperando", "estado": goal["status"], "motivo": espera.get("motivo")}
        motivo = espera.get("motivo")
        if motivo == "dale":
            if r == "aprobada":
                if nota:
                    goals.nota_de_pedro(self.goal_id, nota)
                return self._retomar(goal, espera, "dale de Pedro (inbox)")
            g = goals.transicionar(self.goal_id, goals.CANCELLED, "no de Pedro (inbox)")
            self._limpiar_preautorizadas(g)
            return {"accion": "cancelado", "estado": g["status"]}
        if motivo == "cumplido":
            if r == "aprobada":
                g = goals.transicionar(self.goal_id, goals.COMPLETE, "dale final de Pedro (inbox)")
                self._limpiar_preautorizadas(g)
                return {"accion": "complete", "estado": g["status"]}
            goals.nota_de_pedro(self.goal_id, nota or "Pedro dijo que no esta cumplido: falta algo")
            g = goals.load(None, self.goal_id)
            g["espera"] = {**espera, "solicitud": None, "respuesta": "no"}
            goals.escribir(g)
            return {"accion": "esperando", "estado": g["status"], "motivo": "cumplido", "respuesta": "no"}
        if motivo in goals.RESPUESTAS_QUE_APLICAN:
            # la preautorizacion / la raiz / la nota: lo mismo que aplica
            # /goal segui por el chat (goals.aplicar_respuesta, Task 1)
            goal = goals.aplicar_respuesta(self.goal_id, r, nota=nota)
            return self._retomar(goal, goal.get("espera") or espera, f"respuesta de Pedro: {r}")
        if motivo in goals.MOTIVOS_RETOMAR:
            # la solicitud `retomar`: si = seguir (con el tope ampliado si
            # era tope: aplicar_respuesta), no = cancelar
            if r == "aprobada":
                goal = goals.aplicar_respuesta(self.goal_id, r, nota=nota)
                return self._retomar(goal, goal.get("espera") or espera, f"retomar de Pedro (inbox): {motivo}")
            g = goals.transicionar(self.goal_id, goals.CANCELLED,
                                   "Pedro dijo que no" + (f": {nota}" if nota else ""))
            self._limpiar_preautorizadas(g)
            return {"accion": "cancelado", "estado": g["status"]}
        return {"accion": "esperando", "estado": goal["status"], "motivo": motivo}

    def _retomar(self, goal: dict, espera: dict, motivo: str) -> dict:
        """waiting/proposed -> active tras la respuesta de Pedro. Si otro goal
        esta en curso (invariante 8: transicionar levanta) no se muere en
        silencio: la espera queda con motivo `otro goal activo` (la
        solicitud ya se consumio: no se vuelve a sondear), el evento y la
        telemetria lo dicen, y Pedro lo retoma (`/goal segui` o `/goal
        dale`) cuando el otro cierre."""
        try:
            g = goals.transicionar(self.goal_id, goals.ACTIVE, motivo)
        except goals.ErrorGoal as exc:
            g = goals.load(None, self.goal_id)
            g["espera"] = {**espera, "motivo": "otro goal activo", "solicitud": None,
                           "detalle": str(exc), "respuesta_de_pedro": motivo}
            goals.escribir(g)
            goals.event(None, self.goal_id, "error", error=str(exc), estado=g.get("status"))
            self.telemetria("goal", accion="error", goal_id=self.goal_id, error=str(exc))
            return {"accion": "esperando", "estado": g["status"], "motivo": "otro goal activo",
                    "error": str(exc)}
        return {"accion": "retomado", "estado": g["status"]}

    # -- active --
    def _cancelado(self, n: int | None = None, accion: str = "golpe") -> dict:
        """La vuelta corta porque parar/apagar pusieron `cancelar`: sin juez
        ni transicion (transiciona el que cancelo; si no, tope/no
        convergencia/cumplido correrian contra 'parado por Pedro' y uno de
        los dos reventaria con waiting -> waiting)."""
        estado = (goals.load(None, self.goal_id) or {}).get("status")
        out = {"accion": accion, "estado": estado, "motivo": "cancelado"}
        if n is not None:
            out["n"] = n
        return out

    def _activo(self, goal: dict) -> dict:
        carpeta = goals.dir_goal(goal["id"])
        if self.cancelar.is_set():
            return self._cancelado(accion="nada")
        # 0. el clon (o la carpeta de trabajo) y la sonda del hook
        if goal.get("proyecto") and not goal.get("repo"):
            r = self.clonar(goal)
            if not r.get("ok"):
                return self._failed(f"no se pudo clonar {goal['proyecto']}: {r.get('error')}")
            # recargar antes de escribir: el clon tardo y Pedro pudo tocar
            # el goal (o pararlo) en el medio; `repo` se escribe igual para
            # que un reintento no encuentre el destino "ya existe"
            goal = goals.load(None, self.goal_id)
            goal["repo"] = r["clon"]
            goal["base_sha"] = r.get("base_sha")        # la base de la rama: los diffs se miden contra ella
            goals.escribir(goal)
            if goal.get("status") != goals.ACTIVE:
                return {"accion": "clonado", "estado": goal.get("status")}
        if not goal.get("repo"):
            pathlib.Path(_cwd_de(goal)).mkdir(parents=True, exist_ok=True)
        compuertas_path = goals.escribir_compuertas(goal)
        if not self.hook_sondeado:
            ok, motivo = self.sondear(str(compuertas_path))
            if not ok:
                return self._failed(f"hook inactivo: {motivo}")
            self.hook_sondeado = True
        # 1. el tope
        tope = goals.tope_alcanzado(goal)
        if tope:
            return self._waiting_tope(goal, tope, "tope")
        # 2. la carga (molde _tick_con_carga: un fallo del sensor deja su fila
        # `vigia_error` y el goal golpea sin nivel; nunca queda failed por eso)
        try:
            medida = self.carga_fn()
        except Exception as exc:
            self.telemetria("carga", accion="vigia_error", rutina="goal", rutina_id=goal["id"],
                            error=str(exc))
            medida = None
        if medida is not None and getattr(medida, "nivel", "holgada") == "cargada":
            try:
                from calipso import carga as _carga
                fila = _carga.fila(medida)
            except Exception:
                fila = {}
            self.telemetria("carga", accion="pospone", rutina="goal", rutina_id=goal["id"], **fila)
            return {"accion": "pospuesto", "estado": goal["status"]}
        # 3. la cuota
        cuota = self._cuota(goal)
        if cuota:
            g = goals.transicionar(self.goal_id, goals.WAITING, "cuota", motivo_detalle=cuota)
            estacionar_retomar(g, self.preguntar)
            return {"accion": "cuota", "estado": g["status"], **cuota}
        # 4. el golpe
        if self.manos is None:
            return self._failed("runner sin manos")
        filas = goals.golpes(goal["id"])
        n = _siguiente_n(filas)
        contrato = contrato_del_goal(goal)
        prompt = prompt_del_golpe(goal, filas, goal.get("ultima_nota"))
        prompt, tapados_p = gm.tapar(prompt)
        contrato, tapados_c = gm.tapar(contrato)
        (carpeta / "contrato.md").write_text(contrato, encoding="utf-8")   # fuera del clon (decision 21)
        plan = goal.get("plan") or []
        paso = plan[min(n - 1, len(plan) - 1)] if plan else None
        registro = str(carpeta / "hook.jsonl")                  # = compuertas["registro"]
        desde = _lineas_de(registro)
        if self.cancelar.is_set():           # llego parar/apagar mientras clonaba o sondeaba: no se lanza nada
            return self._cancelado(accion="nada")
        # `sin_golpe` apagado desde la fila `inicio` hasta la fila `fin` y la
        # aduana: el apagado y /goal parar esperan esto antes de transicionar
        self.sin_golpe.clear()
        try:
            goals.golpe_inicio(goal["id"], n, manos=goal.get("manos"), paso=paso)
            self.aduana_fn(goal, n, "inicio", manos=goal.get("manos"))
            self.telemetria("goal", accion="golpe", goal_id=goal["id"], n=n, manos=goal.get("manos"))
            resultado = self.manos(goal, n, prompt, contrato, self.cancelar)
            if goal.get("ultima_nota"):
                g = goals.load(None, self.goal_id)
                if g and g.get("status") == goals.ACTIVE:
                    g["ultima_nota"] = None
                    goals.escribir(g)
            # 5. despues del golpe
            goal = goals.load(None, self.goal_id)
            diff = self.diff_fn(goal)
            usadas = compuertas_usadas(registro, desde)          # spec 7/8, ruling 15.14
            cobro = self.pagador_fn(goal, resultado.unidades, goal.get("manos")) if resultado.unidades else \
                {"cuenta": None, "cobrado": False, "unidades": 0}
            veredicto = resultado.veredicto if isinstance(resultado.veredicto, dict) else None
            valido = bool(veredicto) and veredicto.get("estado") in ("sigo", "terminar", "preguntar")
            # el limite puede venir por stderr o en el result con is_error del
            # stream (gm.texto_de_fallo): antes solo se miraba stderr
            cuota_fallo = resultado.exit not in (0, None) and gm.es_fallo_de_cuota(gm.texto_de_fallo(resultado))
            # parar/apagar matan el CLI y el sondeo de golpear puede verlo
            # muerto antes que `cancelar`: la fila lo dice igual y el golpe
            # cortado no cuenta contra el tope (las unidades si se suman)
            cancelado = resultado.motivo == "cancelado" or self.cancelar.is_set()
            fila = {"manos": goal.get("manos"), "session_id": resultado.session_id,
                    "unidades": resultado.unidades, "duracion_ms": resultado.duracion_ms,
                    "veredicto_del_golpe": veredicto if valido else None,
                    "veredicto_invalido": (not valido) and not resultado.matado and resultado.exit == 0
                    and not cancelado,
                    "comandos": resultado.comandos, "diff_stat": diff, "exit": resultado.exit,
                    "motivo": resultado.motivo or ("cancelado" if cancelado else None), "cobro": cobro,
                    "rate_limit": resultado.rate_limit,
                    "denials": resultado.denials, "costo_usd": resultado.costo_usd,
                    "cuenta_para_tope": not cuota_fallo and not cancelado,
                    "stderr_tail": resultado.stderr_tail[-500:],
                    "model": resultado.model, "reintento": resultado.reintento,
                    "compuertas_usadas": usadas}
            # ruling 2026-09-14: un golpe que falla dice por que en el ledger
            # (invariante "nunca muere en silencio"): con exit != 0, matado, o
            # sin veredicto ni linea `result`, la fila lleva la cola del stdout
            # crudo (1500 caracteres; tapar_fila la pasa por el detector). Con
            # veredicto y exit 0 no: el stream ya esta resumido en la fila.
            if resultado.exit != 0 or resultado.matado or (not valido and not resultado.subtype):
                fila["salida_tail"] = (resultado.stdout_tail or "")[-1500:]
            fila, tapados = gm.tapar_fila(fila)
            fila["secretos_tapados"] = tapados + tapados_p + tapados_c
            goals.golpe_fin(goal["id"], n, **fila)
            self.aduana_fn(goal, n, "fin", comandos=[c.get("cmd") for c in resultado.comandos],
                           bytes_entrados=len(resultado.stdout_tail or ""),
                           dominios=list(goal.get("dominios") or []), compuertas=usadas)
        finally:
            self.golpe_en_curso, self.unidad_en_curso = None, None
            self.sin_golpe.set()
        # 6. lo que corta
        if cancelado:
            return self._cancelado(n)                   # parar/apagar transicionan; aca no se juzga nada
        if goal.get("status") != goals.ACTIVE:
            return {"accion": "golpe", "estado": goal["status"], "n": n}      # lo paro Pedro o el apagado
        if resultado.motivo and (resultado.motivo.startswith("hook inactivo")
                                 or resultado.motivo.startswith("mcp inesperado")):
            return self._failed(resultado.motivo)
        if cuota_fallo:
            detalle = {"motivo": "cuota", "detalle": gm.texto_de_fallo(resultado).strip()[-300:],
                       "resets_at": None, "manos": goal.get("manos")}
            g = goals.transicionar(self.goal_id, goals.WAITING, "cuota", motivo_detalle=detalle)
            estacionar_retomar(g, self.preguntar)
            return {"accion": "cuota", "estado": g["status"], "n": n}
        # 7. el veredicto
        accion = "golpe"
        if valido and veredicto["estado"] == "preguntar":
            return self._preguntar(goal, n, veredicto)
        if valido and veredicto["estado"] == "terminar":
            salida = self._juez(goal, n, resultado, diff)
            if salida is not None:
                return salida
            accion = "juez"            # el juez dijo que falta: el martillo sigue
        # 8. no convergencia y el tope, otra vez
        filas = goals.golpes(goal["id"])
        diag = no_converge(filas)
        if diag:
            g = goals.transicionar(self.goal_id, goals.WAITING, "no_convergencia",
                                   motivo_detalle={"diagnostico": diag,
                                                   "opciones": list(OPCIONES_NO_CONVERGENCIA)})
            estacionar_retomar(g, self.preguntar)
            return {"accion": accion, "estado": g["status"], "n": n, "diagnostico": diag}
        goal = goals.load(None, self.goal_id)
        tope = goals.tope_alcanzado(goal)
        if tope:
            r = self._waiting_tope(goal, tope, "tope")
            return {**r, "accion": accion, "n": n}
        return {"accion": accion, "estado": goals.ACTIVE, "n": n}

    @staticmethod
    def _ventana_vencida(resets_at) -> bool:
        """True si la lectura es de una ventana que ya se reseteo: el freno
        pasivo no puede ser pegajoso (nadie refresca la lectura sin
        golpear). Sin `resets_at` no se sabe: la lectura vale."""
        try:
            return resets_at is not None and float(resets_at) <= time.time()
        except (TypeError, ValueError):
            return False

    def _ultima_activacion(self) -> str:
        """El ts de la ultima transicion a `active` (events.jsonl), '' si no
        hay: una lectura del ledger anterior a ella ya freno una vez y el
        `/goal segui` de Pedro es una activacion nueva."""
        ts = ""
        for e in goals.events(None, self.goal_id):
            if e.get("action") == "transicion" and e.get("a") == goals.ACTIVE:
                ts = e.get("ts") or ts
        return ts

    def _cuota(self, goal: dict) -> dict | None:
        return self._cuota_de(goal.get("manos"), goal)

    def _cuota_de(self, manos: str | None, goal: dict) -> dict | None:
        """La cuota de UNA familia (las manos antes del golpe; la del
        revisor antes de invocarlo: un revisor con la cuota agotada fallaba
        en silencio como 'sin otra familia'). None = puede salir."""
        try:
            c = self.consumo_fn() or {}
        except Exception:
            c = {}
        if self._ventana_vencida(c.get("resets_at")):
            c = {}
        if manos == "codex" and (c.get("codex_used_percent") or 0) > CUOTA_CODEX_MAX:
            return {"motivo": "cuota", "manos": "codex", "used_percent": c.get("codex_used_percent"),
                    "resets_at": c.get("resets_at")}
        if manos == "claude":
            if c.get("claude_limite"):
                return {"motivo": "cuota", "manos": "claude", "resets_at": c.get("resets_at")}
            filas = goals.golpes(goal["id"])
            ultimo = next((f for f in reversed(filas) if f.get("rate_limit")), None)
            if ultimo:
                rl = ultimo["rate_limit"] or {}
                u = rl.get("five_hour")
                # estricto: `_now()` resuelve segundos y un empate cuenta como
                # lectura nueva (frena: lo conservador)
                vieja = self._ventana_vencida(rl.get("resets_at")) \
                    or (ultimo.get("ts_fin") or ultimo.get("ts") or "") < self._ultima_activacion()
                if u is not None and float(u) >= CUOTA_CLAUDE_MAX and not vieja:
                    return {"motivo": "cuota", "manos": "claude", "five_hour": u,
                            "resets_at": rl.get("resets_at")}
        return None

    def _waiting_tope(self, goal: dict, tope: str, motivo: str) -> dict:
        g = goals.transicionar(self.goal_id, goals.WAITING, motivo,
                               motivo_detalle={"tope": tope, "consumo": goals.consumo(goal)})
        estacionar_retomar(g, self.preguntar)
        return {"accion": "tope", "estado": g["status"], "tope": tope}

    def _failed(self, motivo: str) -> dict:
        g = goals.transicionar(self.goal_id, goals.FAILED, motivo)
        self._limpiar_preautorizadas(g)
        return {"accion": "failed", "estado": g["status"], "motivo": motivo}

    def _limpiar_preautorizadas(self, goal: dict) -> None:
        """La preautorizacion vive en el goal y expira al cerrarlo (decision 9).
        Recarga antes de escribir (last-writer-wins)."""
        try:
            goal = goals.load(None, goal["id"]) or goal
            c = goal.setdefault("compuertas", {})
            if c.get("preautorizadas"):
                c["preautorizadas"] = []
                goals.escribir(goal)
            goals.escribir_compuertas(goal)
        except Exception:
            pass

    def _preguntar(self, goal: dict, n: int, veredicto: dict) -> dict:
        pregunta = str(veredicto.get("pregunta") or veredicto.get("resumen") or "")
        compuerta = veredicto.get("compuerta") if isinstance(veredicto.get("compuerta"), dict) else None
        familia = (compuerta or {}).get("familia")
        niveles = (goal.get("compuertas") or {}).get("niveles") or goals.NIVEL_DE
        if familia and niveles.get(familia) == "nunca":
            goals.nota_de_pedro(goal["id"], f"la compuerta {familia} es NUNCA: no se pregunta, no se hace")
            return {"accion": "golpe", "estado": goals.ACTIVE, "n": n, "nunca": familia}
        if familia == "raiz_nueva":
            operacion, forma, detalle = "raiz_nueva", {"raiz": (compuerta.get("forma") or {}).get("raiz")}, \
                {"motivo": "raiz_nueva", "pregunta": pregunta, "raiz": (compuerta.get("forma") or {}).get("raiz")}
        elif familia and niveles.get(familia) == "pregunta":
            operacion, forma = "compuerta", {"familia": familia, "forma": compuerta.get("forma") or {}}
            detalle = {"motivo": "compuerta", "pregunta": pregunta, "compuerta": compuerta}
        else:
            operacion, forma, detalle = "pregunta", {"n": n, "pregunta": pregunta}, \
                {"motivo": "pregunta", "pregunta": pregunta}
        s = self.preguntar(goal, operacion, forma, f"goal {goal['title']}: {pregunta}"[:200], n) or {}
        detalle["solicitud"] = s.get("id")
        g = goals.transicionar(self.goal_id, goals.WAITING, detalle["motivo"], motivo_detalle=detalle)
        return {"accion": "pregunta", "estado": g["status"], "n": n, "operacion": operacion}

    def _juez(self, goal: dict, n: int, resultado: gm.Resultado, diff: str) -> dict | None:
        """None = no cumplido, el martillo sigue (la falta ya esta en el
        ledger). `diff` es el diff_stat de la fila; el revisor recibe el diff
        REAL (`diff_completo_fn`, ruling 15.1). El criterio (hasta 600 s) y
        el revisor (hasta 300 s) corren con `sin_golpe` apagado: parar y el
        apagado los esperan (y matan al revisor por `golpe_en_curso`) en vez
        de transicionar por encima."""
        self.sin_golpe.clear()
        try:
            return self._juzgar(goal, n, resultado)
        finally:
            self.golpe_en_curso, self.unidad_en_curso = None, None
            self.sin_golpe.set()

    def _juzgar(self, goal: dict, n: int, resultado: gm.Resultado) -> dict | None:
        # el criterio comando real corre confinado con su Popen en
        # golpe_en_curso (parar/apagar lo matan) y su scope propio
        ok, salida = juzgar_criterio(goal, self.correr_criterio, al_lanzar=self.registrar_golpe,
                                     cancelar=self.cancelar, n=n, usar_systemd=self.usar_systemd)
        self.golpe_en_curso, self.unidad_en_curso = None, None
        juez: dict = {}
        if ok is not None:
            juez["criterio"] = {"ok": ok, "salida": salida}
        if self.cancelar.is_set():                    # parar/apagar durante el criterio: el revisor ni sale
            self._anotar_juez(goal["id"], n, juez)
            return self._cancelado(n, accion="juez")
        if ok is False:
            self._anotar_juez(goal["id"], n, juez)
            return None
        filas = goals.golpes(goal["id"])
        salidas = "\n".join((c.get("resultado_tail") or "") for c in resultado.comandos)
        # el revisor de OTRA familia cuenta como golpe (spec 6.2): su fila
        # `inicio` ANTES de invocarlo (invariante 3: un crash en el medio
        # deja rastro) y su Popen en golpe_en_curso (al_lanzar de revisar)
        m = n + 1
        otra = gm.otra_familia(goal.get("manos"))
        revisor = f"revisor:{otra}"
        goals.golpe_inicio(goal["id"], m, manos=revisor, paso="revisar")
        self.telemetria("goal", accion="golpe", goal_id=goal["id"], n=m, manos=revisor)
        t0 = time.monotonic()
        # la cuota de la familia del REVISOR antes de invocarlo (la de las
        # manos ya se miro antes del golpe): agotada = no sale, y la fila
        # lo dice en vez de 'sin otra familia'
        cuota = self._cuota_de(otra, goal)
        if cuota:
            revision = {"cumplido": None, "motivo": "cuota del revisor", "revisor": otra, "unidades": 0,
                        "cuota": cuota}
        else:
            # el revisor sale a la suscripcion como el martillo (invariante 9,
            # spec 8): su cruce de la aduana envuelve la invocacion
            self.aduana_fn(goal, m, "inicio", manos=revisor)
            # el revisor ve el diff REAL (ruling 15.1, spec 6.2), no el
            # diff_stat que va al ledger y al prompt
            revision = self.juez(goal, resumen_ledger(filas), self.diff_completo_fn(goal), salidas)
            self.aduana_fn(goal, m, "fin", comandos=[],
                           bytes_entrados=len(str((revision or {}).get("salida_tail") or "")),
                           dominios=list(goal.get("dominios") or []), compuertas=[])
        duracion_ms = int((time.monotonic() - t0) * 1000)
        self.golpe_en_curso, self.unidad_en_curso = None, None
        # las unidades REALES del revisor (ruling 15.12): las del stream de
        # claude, 1 para codex; un revisor viejo sin la clave contesto, asi
        # que gasto al menos una
        unidades = int((revision or {}).get("unidades") or (1 if revision and revision.get("cumplido") is not None
                                                            else 0))
        if revision and revision.get("cumplido") is not None:
            cobro = self.pagador_fn(goal, unidades, revisor)
            juez_rev = {**revision, "independencia": "proveedor_distinto"}
            goals.golpe_fin(goal["id"], m, unidades=unidades, duracion_ms=duracion_ms, juez=juez_rev, cobro=cobro,
                            veredicto_del_golpe={"estado": "revisar", "resumen": revision.get("nota", "")})
            juez["independencia"] = "proveedor_distinto"
            self._anotar_juez(goal["id"], n, juez)
            if self.cancelar.is_set():                # contesto justo antes de parar: anotado, sin transicion
                return self._cancelado(n, accion="juez")
            if not revision.get("cumplido"):
                return None
            detalle = {"motivo": "cumplido", "resumen": (resultado.veredicto or {}).get("resumen", ""),
                       "criterio": juez.get("criterio"), "independencia": "proveedor_distinto",
                       "revisor": revision, "sin_veredicto_de_modelo": False}
        elif self.cancelar.is_set():                  # parar/apagar lo mataron: la fila lo dice, sin cobro
            goals.golpe_fin(goal["id"], m, unidades=0, duracion_ms=duracion_ms, motivo="cancelado",
                            cuenta_para_tope=False)
            self._anotar_juez(goal["id"], n, juez)
            return self._cancelado(n, accion="juez")
        else:
            # sin revisor: no esta la otra familia (None), o esta y fallo
            # (dict con cumplido None: exit != 0, timeout, hook inactivo,
            # sin JSON): la fila dice el motivo y la cola del stdout, y lo
            # que gasto se cobra igual; el goal pasa a Pedro sin veredicto
            # de modelo diciendo por que
            motivo = (revision or {}).get("motivo") or "sin otra familia"
            fila_rev: dict = {"unidades": unidades, "duracion_ms": duracion_ms, "motivo": motivo,
                              "cuenta_para_tope": False}
            if revision and revision.get("salida_tail"):
                fila_rev["salida_tail"] = str(revision["salida_tail"])[-1500:]
            if revision and revision.get("cuota"):
                fila_rev["cuota"] = revision["cuota"]
            if unidades:
                fila_rev["cobro"] = self.pagador_fn(goal, unidades, revisor)
            fila_rev, _ = gm.tapar_fila(fila_rev)
            goals.golpe_fin(goal["id"], m, **fila_rev)
            juez["independencia"] = "ninguna"
            self._anotar_juez(goal["id"], n, juez)
            por_que = ("no hay otra familia disponible" if revision is None
                       else f"el revisor {revision.get('revisor')} fallo: {motivo}")
            detalle = {"motivo": "cumplido",
                       "resumen": ((resultado.veredicto or {}).get("resumen", "")
                                   + (" (criterio medible ok; " if ok else " (")
                                   + f"sin veredicto de modelo: {por_que})"),
                       "criterio": juez.get("criterio"), "independencia": "ninguna",
                       "sin_veredicto_de_modelo": True}
        s = self.preguntar(goal, "cerrar", {"n": n}, f"goal {goal['title']}: cumplido? {detalle['resumen']}"[:200], n) or {}
        detalle["solicitud"] = s.get("id")
        g = goals.transicionar(self.goal_id, goals.WAITING, "cumplido", motivo_detalle=detalle)
        return {"accion": "juez", "estado": g["status"], "n": n}

    @staticmethod
    def _anotar_juez(goal_id: str, n: int, juez: dict) -> None:
        goals.golpe_fin(goal_id, n, juez=juez)
