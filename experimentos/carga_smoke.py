"""El smoke en vivo de la carga (spec 2026-09-11, seccion 6, ultimo punto):
un server desechable en 8778 sobre el fixture de la memoria, Ollama REAL, y
carga REAL: un reservador de memoria (subproceso) que aparta de a 512 MB
de bytes aleatorios (zram no los comprime), midiendo con el sensor despues
de cada paso, hasta
`cargada`, con tope duro (nunca deja MemAvailable por debajo de TOPE_DURO_MB
ni pasa de MAX_RESERVA_MB). Sin Chromium: las marcas de las UIs las cubren
los tests de node; aca se verifica que carga.js sirve y que index.html lo
importa (T7 del terreno).

Los pasos, en este orden (cada uno imprime su veredicto y sigue):
  0. `python -m calipso.carga --esperar` (subproceso, home temporal): espera
     a NO cargada (`justa` o `holgada`: ruling del controlador, ledger de la
     carga tras la Task 1; `--holgada` exigiria holgada). Con 3, BLOQUEADO y
     no arranca nada (la Ally es de Pedro primero).
  1. el server desechable arriba; GET /static/fabrica/carga.js 200 y el
     import en index.html. Se imprime la medicion con el server arriba: el
     server pesa ~1,5 GB (la memoria construye su SentenceTransformer al
     importar), y A, N y V presuponen que la maquina siga NO cargada con el
     server arriba (si ya es cargada ahi, fallan por la maquina, no por el
     producto: se dice en una nota).
  A. `/local` bajo no cargada: carga el 7b; sin senal `carga`; /api/ps lista
     el 7b con context_length 8192 y un expires_at a ~5 min (keep_alive "5m"
     bajo holgada; "2m" bajo justa).
  N. `/nube /local` (el juez corre local con num_ctx = CHAT_NUM_CTX): /api/ps
     sigue con context_length 8192 -> el runner no se recreo.
  M. la medicion con el 7b cargado: en esta maquina eso ya es `cargada`
     (MemAvailable no cuenta al modelo: ruling 9.1). Se anota.
  V. el vigia: como N corrio bajo `cargada` (el 7b adentro ya es cargada)
     con keep_alive 0, el 7b se va solo al terminar N; se espera /api/ps
     vacio y se recarga desde afuera con keep_alive "5m" (lo que dejaria un
     turno bajo holgada) para que sea el VIGIA el que descargue: en <= 90 s
     una fila `descarga` en telemetry.jsonl y /api/ps vacio; el local queda
     suspendido. Al descargar, MemAvailable vuelve a subir: por eso lo que
     sigue necesita carga REAL.
  R. el reservador SIN el modelo cargado: aparta hasta `cargada` (o tope duro)
     -> la calibracion "cargada de verdad" (MemAvailable, PSI, load1, swap en
     ese momento: ES la fila que se anota en carga.CALIBRACION). Se mantiene
     apartada durante B y C (y se completa antes de P: abajo).
  B. un turno sin gesto que por capacidad iria local (`traduce al ingles:
     hola de nuevo`; `hola` a secas rankea opus primero): senal `carga` antes
     del primer chunk con ruta subscription y "contesto por ..." (o, si la
     CLI no esta o falla, local/fallback con "puede tardar o fallar"), la
     misma marca en meta.carga del chat (GET /api/chats/{id}), y el texto
     visible SIN el aviso.
  C. `/local escribi cinco lineas sobre el mar` (carga el 7b bajo cargada,
     con ~5,7 GB libres: la zram absorbe, como el 18:22 del terreno): senal
     con "/local es local, puede tardar o fallar"; A MITAD DEL STREAM el
     smoke manda un keep_alive 0 desde afuera (lo que haria el vigia): el
     turno termina con done, sin error y con texto -> keep_alive 0 no corta
     una request viva; despues /api/ps queda vacio en <= 30 s (el keep_alive
     0 del propio turno).
  P. cargar el 7b en C manda paginas frias de otros procesos a zram y al
     descargarse sobra memoria (la reserva sola ya no alcanza): el reservador
     vuelve a apartar hasta `cargada`; despues una rutina `catastro`
     habilitada (interval 60, sin last_run): en <= 90 s una fila `pospone` y
     last_run sigue None.
  L. libera la memoria: se espera `holgada` hasta 120 s (o se reporta el
     nivel alcanzado: hoy en reposo la Ally dio `justa`, 5876 MB); la rutina
     corre al tick siguiente (last_run puesto) si el nivel lo permite.
  D. `traduce al ingles: hola` (va local por capacidad): con holgada, local
     sin senal (la histeresis se levanto sola); con justa, suscripcion con
     motivo "local suspendido hasta holgada" (se REPORTA: es el diseno, y el
     dato para el ruling de umbrales de Pedro).
Todo va a un home temporal; el server real (8000) y ~/.calipso no se tocan.
Ollama SI es el real y compartido: el smoke presupone el server real apagado
(ruling del controlador: con el real arriba, 1,5 GB, la Ally no llega) y el
evict de C y el del final descargan el 7b lo haya cargado quien lo haya
cargado (no cortan una request viva).
El reservador y el server se apagan al final aunque falle un paso, y el 7b
que deja D (keep_alive 5m) se descarga.

Lo que el reservador aprendio en las corridas 1 y 2 (2026-09-11, informe):
zram comprime una reserva de paginas casi vacias a nada, asi que aparta bytes
ALEATORIOS; y el nivel que dejo no sobrevive a que el 7b entre y salga.

Uso: `nice -n 19 .venv/bin/python -m experimentos.carga_smoke` desde la raiz
del repo. El informe: docs/superpowers/2026-09-11-smoke-carga.md (lo escribe
el que corre el smoke con lo que este script imprime).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import pathlib
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
# el home del PROCESO del smoke (importa calipso.carga, que no toca el home,
# pero la regla del repo es exportarlo antes de importar `calipso`)
os.environ.setdefault("CALIPSO_HOME", tempfile.mkdtemp(prefix="carga-smoke-agente-"))
sys.path.insert(0, str(RAIZ))
from calipso import carga  # noqa: E402

FIXTURE = RAIZ / "experimentos" / "fixtures" / "memoria_smoke_home"
PUERTO = 8778
BASE = f"http://127.0.0.1:{PUERTO}"
WS = f"ws://127.0.0.1:{PUERTO}/ws/chat"
OLLAMA = "http://127.0.0.1:11434"
MODELO = "qwen2.5:7b"
PASO_MB = 512
TOPE_DURO_MB = 1500        # jamas se reserva si MemAvailable quedaria por debajo
MAX_RESERVA_MB = 9000
TICK_S = 60                # el ticker de las rutinas
ESPERA_TICK_S = 90
SALIDA_BLOQUEADO = 3

RESERVADOR = r'''
import gc, os, sys
PASO = int(sys.argv[1]) * 2**20
bloques = []
for linea in sys.stdin:
    orden = linea.strip()
    if orden == "mas":
        # bytes ALEATORIOS, no un bytearray tocado: el swap de la Ally es
        # zram y una pagina casi vacia se comprime a nada, asi que cuando
        # el 7b cargo (paso C de la corrida 1) el kernel mando la reserva
        # entera a zram, MemAvailable subio 1 GB y la maquina dejo de estar
        # cargada (la rutina de P corrio). Lo aleatorio no se comprime:
        # mandarlo a zram no libera nada y el kernel no gana con eso.
        b = bytearray(PASO)
        with open("/dev/urandom", "rb") as f:
            f.readinto(b)             # sin copia transitoria: el tope duro vale
        bloques.append(b)
        print(f"ok {len(bloques) * PASO // 2**20}", flush=True)
    elif orden == "libera":
        bloques.clear()
        gc.collect()
        print("libre", flush=True)
    elif orden == "fin":
        break
'''


# --- la regla de recursos --------------------------------------------------------

def esperar_no_cargada() -> None:
    """Paso 0: el propio helper del producto, como subproceso, con el home del
    smoke. El default de --esperar abre con `justa` o `holgada` (ruling del
    controlador). Con 3, BLOQUEADO: los finally de main no tienen nada que
    apagar."""
    r = subprocess.run([sys.executable, "-m", "calipso.carga", "--esperar", "--tope", "600"],
                       cwd=str(RAIZ), env=os.environ)
    if r.returncode != 0:
        print(f"[recursos] --esperar salio con {r.returncode}: BLOQUEADO, no arranco nada", flush=True)
        sys.exit(SALIDA_BLOQUEADO)


def medir() -> carga.Carga:
    return carga.medir(MODELO, ncpu=os.cpu_count())     # inyectado: sin cache


def linea(c: carga.Carga) -> str:
    return (f"{c.nivel} mem={c.mem_disponible_mb} necesidad={c.necesidad_mb} "
            f"psi_mem={c.psi_mem_some10}/{c.psi_mem_full10} psi_cpu={c.psi_cpu_some10} "
            f"load1={c.load1}/{c.ncpu} swap_usado={c.swap_usado_mb} modelos={c.modelos_cargados}"
            + (f" ({c.motivo})" if c.motivo else ""))


class Reservador:
    """Aparta memoria de verdad en un subproceso (asi liberarla es soltar
    bloques, y si algo sale mal se mata el proceso y vuelve todo)."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen([sys.executable, "-c", RESERVADOR, str(PASO_MB)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.total_mb = 0

    def _orden(self, texto: str) -> str:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(texto + "\n")
        self.proc.stdin.flush()
        return self.proc.stdout.readline().strip()

    def mas(self) -> int:
        r = self._orden("mas")
        self.total_mb = int(r.split()[1])
        return self.total_mb

    def libera(self) -> None:
        if self.total_mb:
            self._orden("libera")
        self.total_mb = 0

    def cerrar(self) -> None:
        try:
            self._orden("fin")
            self.proc.wait(10)
        except Exception:
            self.proc.kill()


def reservar_hasta_cargada(reservador: Reservador) -> carga.Carga:
    """De a PASO_MB, midiendo: para en el primero de cargada / tope duro /
    MAX_RESERVA_MB. Devuelve la medicion final (la calibracion si es cargada)."""
    while True:
        c = medir()
        print(f"[reservador] {reservador.total_mb} MB apartados: {linea(c)}", flush=True)
        if c.nivel == "cargada":
            return c
        if c.mem_disponible_mb < TOPE_DURO_MB + PASO_MB:
            print(f"[reservador] tope duro: no aparto mas (MemAvailable {c.mem_disponible_mb} MB)", flush=True)
            return c
        if reservador.total_mb >= MAX_RESERVA_MB:
            print(f"[reservador] tope de {MAX_RESERVA_MB} MB: no aparto mas", flush=True)
            return c
        reservador.mas()
        time.sleep(1.5)        # que MemAvailable se asiente antes de medir


# --- Ollama y el server desechable ----------------------------------------------

def _ollama_listo() -> None:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5) as r:
            nombres = [m.get("name") for m in json.loads(r.read()).get("models", [])]
    except Exception as e:
        sys.exit(f"Ollama no responde en {OLLAMA}: {e}")
    if MODELO not in nombres:
        sys.exit(f"Ollama no tiene {MODELO}: {nombres}")


def ps() -> list[dict]:
    with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=10) as r:
        return json.loads(r.read()).get("models", [])


def cargar_desde_afuera(keep_alive: str) -> None:
    """Carga el 7b como lo dejaria un turno bajo holgada (keep_alive 5m):
    un prompt vacio a /api/generate solo carga el modelo."""
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate",
        data=json.dumps({"model": MODELO, "prompt": "", "stream": False,
                         "keep_alive": keep_alive}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        r.read()


def evict_desde_afuera() -> None:
    req = urllib.request.Request(
        f"{OLLAMA}/api/generate",
        data=json.dumps({"model": MODELO, "prompt": "", "stream": False, "keep_alive": 0}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()


def esperar_ps_vacio(segundos: int = 30) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        try:
            if not ps():
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def _puerto_libre() -> None:
    try:
        with socket.create_connection(("127.0.0.1", PUERTO), timeout=1):
            pass
    except OSError:
        return
    sys.exit(f"algo ya escucha en {BASE}: no levanto otro server ahi")


def restaurar_home() -> pathlib.Path:
    home = pathlib.Path(tempfile.mkdtemp(prefix="carga-smoke-"))
    shutil.copytree(FIXTURE, home, dirs_exist_ok=True)
    (home / "README.md").unlink(missing_ok=True)
    (home / "catastro.json").write_text(
        json.dumps({"raices": [{"ruta": str(RAIZ), "profundidad": 1}], "proyectos": []}),
        encoding="utf-8")
    return home


class Server:
    def __init__(self, home: pathlib.Path) -> None:
        self.home = home
        self.token = secrets.token_urlsafe(24)
        env = {**os.environ, "CALIPSO_HOME": str(home), "CALIPSO_ROOT": str(RAIZ),
               "CALIPSO_TOKEN": self.token, "CALIPSO_NO_TOTP": "1"}
        self.log = open(home / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "calipso.server:app",
             "--host", "127.0.0.1", "--port", str(PUERTO)],
            cwd=str(RAIZ), env=env, stdout=self.log, stderr=subprocess.STDOUT)

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

    def http(self, metodo: str, ruta: str, cuerpo: dict | None = None, timeout: int = 30):
        req = urllib.request.Request(
            f"{BASE}{ruta}", data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
            headers={"Cookie": f"calipso_token={self.token}", "Content-Type": "application/json"},
            method=metodo)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")

    def texto(self, ruta: str) -> str:
        req = urllib.request.Request(f"{BASE}{ruta}", headers={"Cookie": f"calipso_token={self.token}"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read().decode("utf-8", "replace")

    def telemetria(self, kind: str) -> list[dict]:
        ruta = self.home / "telemetry.jsonl"
        if not ruta.exists():
            return []
        filas = [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [f for f in filas if f.get("kind") == kind]

    def esperar_fila(self, kind: str, accion: str, segundos: int = ESPERA_TICK_S, **campos) -> dict | None:
        """La primera fila `kind` con esa `accion` y con TODOS los `campos`
        iguales (p. ej. `rutina_id=...`: el fixture no trae routines.json y el
        server siembra catastro y consumo habilitadas y vencidas, asi que bajo
        cargada hay filas `pospone` ajenas desde el primer tick)."""
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            for f in self.telemetria(kind):
                if f.get("accion") == accion and all(f.get(k) == v for k, v in campos.items()):
                    return f
            time.sleep(3)
        return None


# --- un turno --------------------------------------------------------------------

def chat_nuevo(server: Server, titulo: str) -> str:
    cid = server.http("POST", "/api/chats", {"title": titulo})["id"]
    server.http("POST", f"/api/chats/{cid}/activate", {})
    return cid


async def _turno(server: Server, mensaje: str, a_mitad=None) -> dict:
    import websockets   # en el .venv (lo usa test_chat_live.py)
    cid = chat_nuevo(server, f"carga {mensaje[:24]}")
    t0 = time.monotonic()
    eventos: list[str] = []
    texto, carga_ev, meta, error = [], [], None, None
    disparado = False
    async with websockets.connect(WS, additional_headers={"Cookie": f"calipso_token={server.token}"},
                                  max_size=None) as ws:
        await ws.send(json.dumps({"text": mensaje, "chat_id": cid}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=900)
            try:
                pkt = json.loads(raw)
            except Exception:
                continue
            t = pkt.get("type", "")
            eventos.append(t)
            if t == "chunk":
                texto.append(pkt.get("text", ""))
                if a_mitad and not disparado and len("".join(texto)) > 20:
                    disparado = True
                    threading.Thread(target=a_mitad, daemon=True).start()
            elif t == "carga":
                carga_ev.append(pkt)
            elif t == "meta" and meta is None:
                meta = pkt
            elif t == "error":
                error = pkt.get("text")
            elif t == "done":
                break
    return {"chat": cid, "eventos": eventos, "texto": "".join(texto), "carga": carga_ev,
            "meta": meta, "error": error, "ms": int((time.monotonic() - t0) * 1000)}


def turno(server: Server, mensaje: str, a_mitad=None) -> dict:
    return asyncio.run(_turno(server, mensaje, a_mitad))


def meta_carga_del_chat(server: Server, cid: str) -> dict | None:
    chat = server.http("GET", f"/api/chats/{cid}")
    for m in reversed(chat.get("messages", [])):
        if m.get("role") == "assistant":
            return (m.get("meta") or {}).get("carga")
    return None


# --- el smoke --------------------------------------------------------------------

class Resultados:
    def __init__(self) -> None:
        self.filas: list[tuple[str, bool, str]] = []

    def ok(self, paso: str, cond: bool, detalle: str = "") -> bool:
        self.filas.append((paso, bool(cond), detalle))
        print(f"[{'ok' if cond else 'FALLO'}] {paso}: {detalle}", flush=True)
        return bool(cond)

    def nota(self, paso: str, detalle: str) -> None:
        self.filas.append((paso, True, detalle))
        print(f"[nota] {paso}: {detalle}", flush=True)

    def fallos(self) -> int:
        return sum(1 for _, c, _ in self.filas if not c)


def antes_del_primer_chunk(eventos: list[str]) -> bool:
    return "carga" in eventos and "chunk" in eventos and eventos.index("carga") < eventos.index("chunk")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sin-esperar", action="store_true",
                    help="saltear el paso 0 (solo si YA mediste no cargada a mano)")
    args = ap.parse_args(argv)
    if not args.sin_esperar:
        esperar_no_cargada()
    _ollama_listo()
    _puerto_libre()
    res = Resultados()
    calibracion: list[tuple[str, carga.Carga]] = []
    home = restaurar_home()
    server = Server(home)
    reservador = Reservador()
    try:
        server.esperar()
        print(f"[smoke] server desechable en {BASE}, home {home}", flush=True)
        # la precondicion de A, N y V: no cargada CON el server arriba
        # (~1,5 GB de RSS: la memoria construye su SentenceTransformer al
        # importar calipso.server; con el server real de Pedro corriendo,
        # la Ally en reposo no llega)
        con_server = medir()
        calibracion.append(("con el server desechable arriba", con_server))
        res.nota("1 medicion con el server desechable arriba", linea(con_server))
        if con_server.nivel == "cargada":
            res.nota("1 precondicion de A, N y V", "la maquina YA es cargada con el server arriba: "
                     "A, N y V van a fallar por la maquina (el 7b no queda cargado bajo cargada: "
                     "keep_alive 0), no por el producto")

        # 1. las UIs sirven la marca
        res.ok("1 carga.js sirve", "textosDeCarga" in server.texto("/static/fabrica/carga.js"))
        res.ok("1 index importa carga.js", "/static/fabrica/carga.js" in server.texto("/"))

        # A. /local bajo no cargada
        a = turno(server, "/local decime hola en una sola linea")
        res.ok("A /local sin senal de carga", not a["carga"] and not a["error"] and a["texto"].strip() != "",
               f"{a['ms']} ms, texto={a['texto'][:60]!r}")
        cargados = ps()
        res.ok("A el 7b cargado con context_length 8192",
               any(m.get("name") == MODELO and m.get("context_length") == 8192 for m in cargados),
               json.dumps([(m.get("name"), m.get("context_length"), m.get("expires_at")) for m in cargados]))

        # N. el juez con CHAT_NUM_CTX: el runner no se recrea
        n = turno(server, "/nube /local que hora es, en una linea")
        cargados = ps()
        res.ok("N /nube no recreo el runner (context_length sigue 8192)",
               any(m.get("name") == MODELO and m.get("context_length") == 8192 for m in cargados),
               json.dumps([(m.get("name"), m.get("context_length")) for m in cargados]) + f" error={n['error']}")

        # M. la medicion con el 7b cargado
        m = medir()
        calibracion.append(("con el 7b cargado", m))
        res.nota("M medicion con el 7b cargado", linea(m))
        if m.nivel != "cargada":
            res.nota("M no es cargada con el 7b: aparto memoria hasta cargada", "")
            m = reservar_hasta_cargada(reservador)
            calibracion.append(("con el 7b + reservador", m))
        res.ok("M cargada", m.nivel == "cargada", linea(m))

        # V. el vigia descarga sin cortar nada. En la corrida 1 el 7b ya se
        # habia ido solo: N corrio bajo cargada y su propio keep_alive 0 lo
        # descargo antes del tick. Para que sea el VIGIA el que descarga, se
        # carga el 7b desde afuera con keep_alive "5m" (lo que dejaria un
        # turno bajo holgada) con la maquina cargada, y se espera la fila.
        # (Ollama tarda unos segundos en soltar el runner tras un keep_alive
        # 0: primero se espera a que el ps quede vacio, y recien ahi se
        # recarga; si N no lo descargo, se sigue con el que hay.)
        if esperar_ps_vacio(30):
            cargar_desde_afuera("5m")
            m = medir()
            calibracion.append(("con el 7b recargado para el vigia", m))
            res.nota("V el 7b recargado desde afuera (keep_alive 5m)", linea(m))
        fila = server.esperar_fila("carga", "descarga")
        res.ok("V el vigia descargo el 7b (fila descarga)", fila is not None and fila.get("modelo") == MODELO,
               json.dumps({k: fila.get(k) for k in ("modelo", "ok", "nivel", "mem_disponible_mb")}) if fila else "sin fila en 90 s")
        res.ok("V /api/ps vacio tras la descarga", esperar_ps_vacio(30), json.dumps([x.get("name") for x in ps()]))
        time.sleep(3)          # que MemAvailable se asiente tras la descarga

        # R. la calibracion "cargada de verdad": el reservador SIN el modelo
        # (lo que aparto queda apartado durante B, C y P)
        r = reservar_hasta_cargada(reservador)
        calibracion.append(("reservador sin modelo", r))
        res.ok("R cargada con carga real", r.nivel == "cargada", linea(r))
        via_api = server.http("GET", "/api/carga")
        res.ok("R GET /api/carga coincide", via_api["medicion"]["nivel"] == r.nivel,
               json.dumps({k: via_api["medicion"][k] for k in ("nivel", "mem_disponible_mb", "motivo")}) + f" hoy={via_api['hoy']}")

        # B. el turno sin gesto que iria local por capacidad: suscripcion con
        # aviso (o local/fallback con aviso si la CLI no esta o falla)
        b = turno(server, "traduce al ingles: hola de nuevo")
        senales = b["carga"]
        ruta_final = (b["meta"] or {}).get("used")
        res.ok("B senal carga antes del primer chunk", antes_del_primer_chunk(b["eventos"]),
               json.dumps([s.get("aviso") for s in senales]))
        if senales and senales[-1].get("ruta") == "subscription":
            res.ok("B por suscripcion con 'contesto por'", "contesto por" in senales[-1]["aviso"], senales[-1]["aviso"])
        else:
            res.ok("B fallback/local con 'puede tardar o fallar'",
                   bool(senales) and "puede tardar o fallar" in senales[-1]["aviso"],
                   f"ruta={ruta_final} avisos={[s.get('aviso') for s in senales]}")
        res.ok("B el aviso no entra en el texto", "maquina cargada" not in b["texto"], b["texto"][:80])
        mc = meta_carga_del_chat(server, b["chat"])
        res.ok("B meta.carga en el chat", bool(mc) and mc.get("aviso") == (senales[-1].get("aviso") if senales else None),
               json.dumps(mc))
        res.ok("B fila kind: carga (suscripcion o local_con_aviso)",
               any(f.get("accion") in ("suscripcion", "local_con_aviso") and f.get("chat") == b["chat"]
                   for f in server.telemetria("carga")))

        # C. /local bajo carga + keep_alive 0 desde afuera a mitad del stream
        c = turno(server, "/local escribi cinco lineas sobre el mar", a_mitad=evict_desde_afuera)
        res.ok("C /local avisa 'es local, puede tardar o fallar'",
               bool(c["carga"]) and c["carga"][0].get("gesto") == "/local" and "puede tardar o fallar" in c["carga"][0]["aviso"],
               json.dumps(c["carga"]))
        res.ok("C keep_alive 0 desde afuera no corto la request viva",
               c["error"] is None and len(c["texto"].strip()) > 40 and "done" in c["eventos"],
               f"{c['ms']} ms, {len(c['texto'])} chars, error={c['error']}")
        res.ok("C /api/ps vacio tras el turno (keep_alive 0 del propio turno)", esperar_ps_vacio(30),
               json.dumps([x.get("name") for x in ps()]))

        # P. la rutina pospuesta. La reserva sigue apartada, pero cargar el
        # 7b en C manda paginas frias de OTROS procesos a zram (comprimidas
        # 3:1) y al descargarse queda mas memoria libre que antes (corrida
        # 2: justa en vez de cargada): se vuelve a apartar hasta cargada.
        p_antes = reservar_hasta_cargada(reservador)
        calibracion.append(("reservador tras C, para P", p_antes))
        res.ok("P cargada antes de la rutina", p_antes.nivel == "cargada", linea(p_antes))
        rt = server.http("POST", "/api/routines", {"kind": "catastro", "label": "smoke carga",
                                                   "interval_minutes": 60, "enabled": True})
        rt_id = rt.get("id") or (rt.get("routine") or {}).get("id")
        fila = server.esperar_fila("carga", "pospone", rutina_id=rt_id)   # la del smoke, no la catastro sembrada
        res.ok("P la rutina se pospuso (fila pospone)", fila is not None and fila.get("rutina") == "catastro",
               json.dumps({k: fila.get(k) for k in ("rutina", "nivel")}) if fila else "sin fila en 90 s")
        rutinas = server.http("GET", "/api/routines")["routines"]
        mia = next((x for x in rutinas if x.get("id") == rt_id), {})
        res.ok("P last_run sigue None", mia.get("last_run") is None, json.dumps(mia.get("last_run")))

        # L. liberar y esperar holgada (o reportar)
        reservador.libera()
        limite = time.monotonic() + 120
        nivel = None
        while time.monotonic() < limite:
            nivel = server.http("GET", "/api/carga")["medicion"]["nivel"]
            if nivel == "holgada":
                break
            time.sleep(5)
        res.nota("L nivel tras liberar", f"{nivel} ({linea(medir())})")
        corrio = None
        limite = time.monotonic() + ESPERA_TICK_S
        while time.monotonic() < limite:
            rutinas = server.http("GET", "/api/routines")["routines"]
            mia = next((x for x in rutinas if x.get("id") == rt_id), {})
            if mia.get("last_run"):
                corrio = mia["last_run"]
                break
            time.sleep(5)
        if nivel in ("holgada", "justa"):        # catastro no es pesada: bajo justa corre
            res.ok("L la rutina pospuesta corrio al liberar", corrio is not None, json.dumps(corrio))
        else:
            res.nota("L la rutina sigue pospuesta", f"nivel {nivel}")

        # D. la histeresis
        d = turno(server, "traduce al ingles: hola")
        ruta_d = (d["meta"] or {}).get("used")
        if nivel == "holgada":
            res.ok("D holgada: el turno local volvio solo, sin senal", ruta_d == "local" and not d["carga"],
                   f"ruta={ruta_d} senales={[s.get('aviso') for s in d['carga']]}")
        else:
            res.nota("D sin holgada: la histeresis sigue vigente",
                     f"ruta={ruta_d} senales={[s.get('motivo') for s in d['carga']]} (diseno: el local vuelve solo en holgada; "
                     f"la Ally en reposo con este agente corriendo da {nivel}: dato para el ruling de umbrales)")
    finally:
        reservador.libera()
        reservador.cerrar()
        server.apagar()
        # el paso D deja el 7b cargado con keep_alive 5m (holgada): no se
        # le deja a la maquina de Pedro un modelo que nadie usa
        try:
            if any(x.get("name") == MODELO for x in ps()):
                evict_desde_afuera()
        except Exception as e:
            print(f"[smoke] no pude descargar el 7b al final: {e!r}", flush=True)
        print(f"[smoke] server apagado; home {home} (server.log y telemetry.jsonl adentro)", flush=True)

    print("\n=== calibracion (para carga.CALIBRACION) ===")
    for escena, c in calibracion:
        print(json.dumps({"cuando": c.medido_en, "escena": escena, "mem_disponible_mb": c.mem_disponible_mb,
                          "necesidad_mb": c.necesidad_mb, "psi_mem_some10": c.psi_mem_some10,
                          "psi_mem_full10": c.psi_mem_full10, "psi_cpu_some10": c.psi_cpu_some10,
                          "load1": c.load1, "ncpu": c.ncpu, "swap_usado_mb": c.swap_usado_mb,
                          "nivel": c.nivel}, ensure_ascii=False))
    print("\n=== resumen ===")
    for paso, ok, detalle in res.filas:
        print(f"  {'ok   ' if ok else 'FALLO'} {paso}" + (f" -- {detalle}" if detalle else ""))
    print(f"\n{res.fallos()} fallo(s)")
    return 1 if res.fallos() else 0


if __name__ == "__main__":
    sys.exit(main())
