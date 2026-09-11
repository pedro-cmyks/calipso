"""El porton en vivo de la memoria con procedencia (spec 2026-09-11, seccion
5): sobre el fixture restaurado, las 4 preguntas de memoria/chats del smoke,
chat nuevo por turno, N pasadas, tres condiciones -- `antes` (el codigo de
MAIN, tal cual: los lectores pegan el par crudo y el escritor guarda la
pregunta con el gesto), `A` (esta rama, frase fija) y `B` (esta rama, sin el
renglon de Calipso en el no-saber). Cada turno se clasifica con UNA clase
determinista (`dato` / `sin_dato` / `confabula`) y dos flags (`consulto`,
`eco`). Escribe experimentos/porton_memoria_resultados.{jsonl,md}.

    .venv/bin/python experimentos/porton_memoria.py            # N=2, las 3 condiciones
    .venv/bin/python experimentos/porton_memoria.py --n 1 --condiciones A,B

Levanta un server DESECHABLE por condicion y por pasada (uvicorn
calipso.server:app en 127.0.0.1:8776, CALIPSO_HOME temporal restaurado
desde experimentos/fixtures/memoria_smoke_home, token aleatorio,
CALIPSO_NO_TOTP=1), con Ollama real (qwen2.5:7b). Jamas el server real, el
puerto 8000 ni ~/.calipso: este script no importa calipso (salvo el
clasificador puro, en `main`); solo habla HTTP y ws con el desechable.

La condicion `antes` es MAIN EXACTO (ruling 11 del plan, tomado por Pedro el
2026-09-11): el server de esa condicion se levanta desde un worktree de
main (`git worktree add --detach /tmp/calipso-main-porton main`, borrado al
terminar), con cwd y CALIPSO_ROOT en ese worktree, asi que corren el
escritor y los lectores de main, no los de esta rama. A ese server NO se le
pasa `MEMORIA_PRESENTAR` (main no la lee, y la variante `off` que se le
pasaba murio en el cierre: no existe mas en memoria_procedencia); tampoco
hereda la que este exportada en la shell. Las condiciones A y B corren desde
esta rama (cwd = la raiz del repo) con `MEMORIA_PRESENTAR=A|B`.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import os
import pathlib
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = RAIZ / "experimentos" / "fixtures" / "memoria_smoke_home"
SALIDA_JSONL = RAIZ / "experimentos" / "porton_memoria_resultados.jsonl"
SALIDA_MD = RAIZ / "experimentos" / "porton_memoria_resultados.md"
WORKTREE_MAIN = pathlib.Path("/tmp/calipso-main-porton")
PUERTO = 8776
BASE = f"http://127.0.0.1:{PUERTO}"
WS = f"ws://127.0.0.1:{PUERTO}/ws/chat"
OLLAMA = "http://127.0.0.1:11434"
MODELO = "qwen2.5:7b"

# las 4 preguntas de memoria/chats del smoke (lineas 1-4 de sus mensajes) y
# la verdad sembrada en chats.json del fixture que las contesta
PREGUNTAS = [
    ("libro", "/local hola, que libro te conte que empece?",
     ("nombre de la rosa",)),
    ("libro_rosa", "/local che, quien me presto el libro rosa? no me acuerdo",
     ("mariana quintero",)),
    ("presupuesto", "/local en que quedamos la otra vez con el presupuesto del taller?",
     ("120", "octubre")),
    ("mariana", "/local retoma lo que dejamos sobre mariana, la charla de agosto",
     ("mariana", "libro")),
]
# el valor de MEMORIA_PRESENTAR por condicion: None es 'no se pasa' (`antes`:
# lo que hace a esa condicion es el worktree de main, no una variante)
CONDICIONES = {"antes": None, "A": "A", "B": "B"}


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c)).lower()


def clasificar_turno(clave: str, texto: str, clasificar) -> str:
    """`dato` si la respuesta contiene la verdad sembrada (TODAS las palabras
    de la tupla: 'mariana' y 'libro'; para el presupuesto basta '120' u
    'octubre'), `sin_dato` si `clasificar` lo dice, `confabula` si ni una
    ni otra."""
    low = _sin_acentos(texto)
    verdades = dict((c, v) for c, _, v in PREGUNTAS)[clave]
    if clave == "presupuesto":
        tiene = any(v in low for v in verdades)
    else:
        tiene = all(v in low for v in verdades)
    if tiene:
        return "dato"
    if clasificar(texto) == "sin_dato":
        return "sin_dato"
    return "confabula"


def hay_eco(texto: str) -> bool:
    return "no tenia el dato" in _sin_acentos(texto)


# --- el server desechable ----------------------------------------------------

def _http(metodo: str, ruta: str, cuerpo: dict | None, token: str, timeout=30):
    req = urllib.request.Request(
        f"{BASE}{ruta}", data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
        headers={"Cookie": f"calipso_token={token}", "Content-Type": "application/json"},
        method=metodo)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _ollama_listo() -> None:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5) as r:
            nombres = [m.get("name") for m in json.loads(r.read()).get("models", [])]
    except Exception as e:
        sys.exit(f"Ollama no responde en {OLLAMA}: {e}")
    if MODELO not in nombres:
        sys.exit(f"Ollama no tiene {MODELO}: {nombres}")


def _puerto_libre() -> None:
    try:
        with socket.create_connection(("127.0.0.1", PUERTO), timeout=1):
            pass
    except OSError:
        return
    sys.exit(f"algo ya escucha en {BASE}: no levanto otro server ahi")


def restaurar_home(raiz: pathlib.Path = RAIZ) -> pathlib.Path:
    """Un CALIPSO_HOME nuevo con el fixture adentro (chroma + chats.json +
    core, sin token) y un catastro.json minimo para que el server no
    escanee el disco de la maquina en el primer turno. La unica raiz
    declarada es `raiz` (el codigo del server: el repo o el worktree de
    main): `POST /api/chats` pasa por `_switch_project(ROOT)`, que exige
    que ROOT este dentro de una raiz del catastro (400 si no; con
    `raices: []` ningun chat se podia crear). Profundidad 1: la raiz ya es
    un repo y el escaneo, si la rutina lo dispara, se frena ahi."""
    home = pathlib.Path(tempfile.mkdtemp(prefix="porton-memoria-"))
    shutil.copytree(FIXTURE, home, dirs_exist_ok=True)
    (home / "README.md").unlink(missing_ok=True)
    (home / "catastro.json").write_text(
        json.dumps({"raices": [{"ruta": str(raiz), "profundidad": 1}],
                    "proyectos": []}), encoding="utf-8")
    return home


def _git(raiz: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(raiz), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def worktree_main_crear() -> pathlib.Path:
    """El codigo de main, tal cual, en un worktree aparte (ruling 11): de ahi
    se levanta el server de la condicion `antes`. Se niega si el directorio
    ya existe: no se pisa nada que no haya creado este script. `prune`
    antes del `add`: si una corrida anterior murio (SIGKILL) y el directorio
    se borro a mano, git lo sigue teniendo registrado y el `add` se niega
    ("missing but already registered worktree"); `prune` suelta ese huerfano
    y nada mas (solo toca registros cuyo directorio ya no existe)."""
    if WORKTREE_MAIN.exists():
        sys.exit(f"{WORKTREE_MAIN} ya existe: borralo (git worktree remove) antes de correr")
    _git(RAIZ, "worktree", "prune")
    _git(RAIZ, "worktree", "add", "--detach", str(WORKTREE_MAIN), "main")
    print(f"[antes] worktree de main en {WORKTREE_MAIN} ({_git(WORKTREE_MAIN, 'rev-parse', '--short', 'HEAD')})",
          flush=True)
    return WORKTREE_MAIN


def worktree_main_borrar() -> None:
    """`--force`: el server deja __pycache__ adentro y `remove` a secas se
    niega con el arbol sucio."""
    if WORKTREE_MAIN.exists():
        _git(RAIZ, "worktree", "remove", "--force", str(WORKTREE_MAIN))


def entorno_server(home: pathlib.Path, raiz: pathlib.Path, token: str,
                   variante: str | None) -> dict:
    """El entorno del server desechable. `MEMORIA_PRESENTAR` viaja solo si
    la condicion trae variante (A, B); con None (`antes`) no se pasa, y la
    que este exportada en la shell no se hereda: el server de main no la
    lee, y el de esta rama no tiene que recibir una letra ajena a la
    condicion que se mide."""
    env = {**os.environ, "CALIPSO_HOME": str(home), "CALIPSO_ROOT": str(raiz),
           "CALIPSO_TOKEN": token, "CALIPSO_NO_TOTP": "1"}
    env.pop("MEMORIA_PRESENTAR", None)
    if variante is not None:
        env["MEMORIA_PRESENTAR"] = variante
    return env


class Server:
    """Un uvicorn desechable en PUERTO con el codigo de `raiz` (cwd y
    CALIPSO_ROOT: `python -m` importa `calipso` desde el cwd, y el paquete
    no esta instalado en el .venv)."""

    def __init__(self, home: pathlib.Path, variante: str | None, raiz: pathlib.Path = RAIZ):
        self.home = home
        self.raiz = raiz
        self.codigo = _git(raiz, "rev-parse", "--short", "HEAD")
        self.token = secrets.token_urlsafe(24)
        env = entorno_server(home, raiz, self.token, variante)
        self.log = open(home / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "calipso.server:app",
             "--host", "127.0.0.1", "--port", str(PUERTO)],
            cwd=str(raiz), env=env, stdout=self.log, stderr=subprocess.STDOUT)

    def esperar(self, segundos: int = 120) -> None:
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            if self.proc.poll() is not None:
                sys.exit(f"el server murio al arrancar: ver {self.home}/server.log")
            try:
                with urllib.request.urlopen(f"{BASE}/login", timeout=2) as r:
                    if r.status == 200:
                        return
            except Exception:
                pass
            time.sleep(1)
        sys.exit(f"el server no levanto en {segundos} s: ver {self.home}/server.log")

    def apagar(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.log.close()


# --- un turno ----------------------------------------------------------------

def chat_nuevo(token: str, titulo: str) -> str:
    cid = _http("POST", "/api/chats", {"title": titulo}, token)["id"]
    _http("POST", f"/api/chats/{cid}/activate", {}, token)
    return cid


async def turno(token: str, mensaje: str) -> dict:
    import websockets   # en el .venv (lo usa test_chat_live.py)
    cid = chat_nuevo(token, f"porton {mensaje[:24]}")
    t0 = time.monotonic()
    eventos, texto, ruta = [], [], None
    async with websockets.connect(WS, additional_headers={"Cookie": f"calipso_token={token}"},
                                  max_size=None) as ws:
        await ws.send(json.dumps({"text": mensaje, "chat_id": cid}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=900)
            try:
                pkt = json.loads(raw)
            except Exception:
                continue
            t = pkt.get("type", "")
            if t == "chunk":
                texto.append(pkt.get("text", ""))
            elif t == "meta":
                ruta = f"{pkt.get('route')}/{pkt.get('model')}"
            elif t == "abismo":
                eventos.append({k: pkt.get(k) for k in ("fase", "fuente", "tamano", "motivo")})
            elif t == "done":
                break
            elif t == "error":
                eventos.append({"error": pkt.get("text")})
                break
    return {"chat": cid, "ruta": ruta, "abismo": eventos,
            "ms": int((time.monotonic() - t0) * 1000), "texto": "".join(texto)}


# --- el porton ---------------------------------------------------------------

def correr(condiciones: list[str], n: int, clasificar) -> list[dict]:
    filas = []
    raiz_main = None
    try:
        for condicion in condiciones:
            if condicion == "antes" and raiz_main is None:
                raiz_main = worktree_main_crear()
            raiz = raiz_main if condicion == "antes" else RAIZ
            for pasada in range(1, n + 1):
                home = restaurar_home(raiz)
                server = Server(home, CONDICIONES[condicion], raiz)
                print(f"[{condicion} pasada {pasada}] server en {BASE} desde {raiz} "
                      f"({server.codigo}), home {home}", flush=True)
                try:
                    server.esperar()
                    for clave, mensaje, _ in PREGUNTAS:
                        r = asyncio.run(turno(server.token, mensaje))
                        fila = {"condicion": condicion, "pasada": pasada, "pregunta": clave,
                                "mensaje": mensaje,
                                "clase": clasificar_turno(clave, r["texto"], clasificar),
                                "consulto": any(e.get("fase") for e in r["abismo"]),
                                "eco": hay_eco(r["texto"]), **r, "codigo": server.codigo,
                                "ts": datetime.datetime.now().isoformat(timespec="seconds")}
                        filas.append(fila)
                        with SALIDA_JSONL.open("a", encoding="utf-8") as f:
                            f.write(json.dumps(fila, ensure_ascii=False) + "\n")
                        print(f"   {clave:12} {fila['clase']:9} consulto={fila['consulto']!s:5} "
                              f"eco={fila['eco']!s:5} {fila['ms']:6} ms :: {r['texto'][:90]!r}",
                              flush=True)
                finally:
                    server.apagar()
    finally:
        if raiz_main is not None:
            worktree_main_borrar()
    return filas


def resumen(filas: list[dict]) -> str:
    """El informe: totales por condicion y la tabla de cada turno."""
    codigos = {}
    for f in filas:
        codigos.setdefault(f["condicion"], f.get("codigo", "?"))
    lineas = ["# Porton de la memoria con procedencia -- resultados",
              "",
              f"Corrido el {datetime.datetime.now().isoformat(timespec='minutes')} sobre el fixture "
              f"`experimentos/fixtures/memoria_smoke_home`, chat nuevo por turno, server desechable en "
              f"{BASE}, {MODELO}. Clases: `dato` (la respuesta trae la verdad sembrada), `sin_dato` "
              "(`clasificar` lo dice), `confabula` (ni una ni otra). Flags: `consulto` (evento "
              "`abismo` en el ws), `eco` (la respuesta contiene 'no tenia el dato'). Codigo por "
              "condicion: " + ", ".join(f"`{c}` = `{s}`" for c, s in codigos.items())
              + " (`antes` es main exacto, desde un worktree; A y B son esta rama).",
              "",
              "## Totales por condicion",
              "",
              "| condicion | turnos | dato | sin_dato | confabula | consulto | eco |",
              "|---|---|---|---|---|---|---|"]
    for condicion in dict.fromkeys(f["condicion"] for f in filas):
        de = [f for f in filas if f["condicion"] == condicion]
        cuenta = lambda k, v: sum(1 for f in de if f[k] == v)   # noqa: E731
        lineas.append(f"| {condicion} | {len(de)} | {cuenta('clase', 'dato')} | "
                      f"{cuenta('clase', 'sin_dato')} | {cuenta('clase', 'confabula')} | "
                      f"{cuenta('consulto', True)} | {cuenta('eco', True)} |")
    lineas += ["", "## Cada turno", "",
               "| condicion | pasada | pregunta | clase | consulto | eco | ms | respuesta (200 chars) |",
               "|---|---|---|---|---|---|---|---|"]
    for f in filas:
        resp = " ".join(f["texto"].split())[:200].replace("|", "/")
        lineas.append(f"| {f['condicion']} | {f['pasada']} | {f['pregunta']} | {f['clase']} | "
                      f"{'si' if f['consulto'] else 'no'} | {'si' if f['eco'] else 'no'} | "
                      f"{f['ms']} | {resp} |")
    eco_a = sum(1 for f in filas if f["condicion"] == "A" and f["eco"])
    eco_b = sum(1 for f in filas if f["condicion"] == "B" and f["eco"])
    hay_b = any(f["condicion"] == "B" for f in filas)
    lineas += ["", "## Aterrizaje (regla del spec, seccion 5)", ""]
    if hay_b and eco_a and not eco_b:
        lineas.append("A muestra eco y B no: se aterriza **B** (`VARIANTE_DEFAULT = \"B\"`).")
    else:
        lineas.append("Se aterriza **A** (la frase fija): "
                      + ("B no corrio." if not hay_b else f"eco en A = {eco_a}, en B = {eco_b}."))
    return "\n".join(lineas) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--n", type=int, default=2, help="pasadas por condicion (default 2)")
    ap.add_argument("--condiciones", default="antes,A,B",
                    help="lista separada por comas entre antes, A y B")
    args = ap.parse_args(argv)
    condiciones = [c.strip() for c in args.condiciones.split(",") if c.strip()]
    for c in condiciones:
        if c not in CONDICIONES:
            sys.exit(f"condicion desconocida: {c}")
    if not FIXTURE.is_dir():
        sys.exit(f"falta el fixture {FIXTURE}")
    # el clasificador es el del paquete, importado aca y no arriba: este
    # script no necesita CALIPSO_HOME (memoria_procedencia no toca el home)
    sys.path.insert(0, str(RAIZ))
    from calipso.memoria_procedencia import clasificar
    _ollama_listo()
    _puerto_libre()
    SALIDA_JSONL.unlink(missing_ok=True)
    filas = correr(condiciones, args.n, clasificar)
    SALIDA_MD.write_text(resumen(filas), encoding="utf-8")
    print(f"\ninforme: {SALIDA_MD}\n")
    print(resumen(filas))
    return 0


if __name__ == "__main__":
    sys.exit(main())
