#!/usr/bin/env python3
"""El smoke de la memoria por Ollama (spec 2026-09-12, seccion 5): un server
DESECHABLE en 8779 sobre un CALIPSO_HOME temporal restaurado del fixture (las
dos colecciones), Ollama REAL (bge-m3 y el 7b) y un proxy TCP local
(127.0.0.1:11435 -> 11434) al que el server apunta por CALIPSO_EMBED_URL:
cortar el proxy es "Ollama caido" para el embedder sin tocar el Ollama real.
El server real (8000, ~/.calipso) no se toca.

Pasos:
  0  la regla de recursos (`python -m calipso.carga --esperar`; 3 = BLOQUEADO), Ollama con los dos
     modelos, los puertos libres, el home restaurado, el proxy y el server arriba
  A  GET /api/memory: 16 episodios, sin_reindexar 0, recall_ok True
  R1 recall real por bge-m3 en ESTE proceso sobre otra copia del fixture: la pregunta del fixture
     trae su episodio arriba (score y tiempo, con la carga fria); un segundo recall caliente
  R2 un turno por el server con recall real: sin recall_fallo, texto, ruta
  D  `done` antes del remember: ms entre el ultimo chunk y done; segundos hasta que
     global_episodes pasa de 16 a 17 (el remember de fondo)
  C  Ollama caido a mitad (el proxy cortado): el turno entero con recall_fallo y remember_fallo,
     /api/memory con recall_ok False y ultimo_recall_fallo; el proxy vuelve y el turno siguiente
     deja recall_ok True
  X  el reindex sobre copias: idempotente sobre el fixture (0 copiados, 16 ya estaban) y desde cero
     (la viva borrada EN LA COPIA: 16 copiados, ids iguales), con los tiempos
  V  la descarga del embedder por /api/embed (carga.ollama_evict(..., embedding=True)): se calienta bge-m3
     con un POST propio con keep_alive 5m (bajo justa/cargada keep_alive_embed es 0 y el modelo se
     descargaria solo: el evict tiene que actuar sobre un modelo RESIDENTE), se espera verlo en /api/ps
     y recien ahi se evicta: /api/ps sin bge-m3
  J  la convivencia con el 7b (ruling 8.4): con el 7b cargado, un turno completo midiendo /api/ps
     antes, tras el done y tras el remember; si el 7b desaparece mientras bge-m3 esta, PARADA
     (se le dice a Pedro con los numeros; candidatas en el spec)

Salida: una linea [ok]/[FALLO]/[nota] por paso, el resumen y `resultados.json` en el home del smoke.
El informe se escribe a mano en docs/superpowers/2026-09-12-smoke-memoria.md. Codigos: 0 ok, 1 con
fallos (incluida la PARADA de J), 3 bloqueado por recursos.

    CALIPSO_HOME=$(mktemp -d) nice -n 19 .venv/bin/python experimentos/memoria_smoke.py
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
HOME_AGENTE = pathlib.Path(tempfile.mkdtemp(prefix="memoria-smoke-agente-"))
os.environ["CALIPSO_HOME"] = str(HOME_AGENTE)          # este proceso: jamas el home real
os.environ.pop("CALIPSO_EMBED_FALSA", None)             # el smoke embebe de verdad
os.environ.pop("CALIPSO_EMBED_URL", None)               # este proceso va directo a Ollama
sys.path.insert(0, str(RAIZ))

import chromadb  # noqa: E402

from calipso import carga  # noqa: E402
from calipso import config as calipso_config  # noqa: E402
from calipso import memoria_embed as me  # noqa: E402

FIXTURE = RAIZ / "experimentos" / "fixtures" / "memoria_smoke_home"
PUERTO = 8779
BASE = f"http://127.0.0.1:{PUERTO}"
WS = f"ws://127.0.0.1:{PUERTO}/ws/chat"
OLLAMA = "http://127.0.0.1:11434"
PUERTO_PROXY = 11435
EMBED_URL = f"http://127.0.0.1:{PUERTO_PROXY}"
MODELO = "qwen2.5:7b"
EMBED = calipso_config.EMBED_MODEL
SALIDA_BLOQUEADO = 3
PLAZO_TURNO_S = 900


# --- la regla de recursos --------------------------------------------------------

def esperar_no_cargada() -> None:
    r = subprocess.run([sys.executable, "-m", "calipso.carga", "--esperar", "--tope", "600"],
                       cwd=str(RAIZ), env=os.environ)
    if r.returncode != 0:
        print(f"[recursos] --esperar salio con {r.returncode}: BLOQUEADO, no arranco nada", flush=True)
        sys.exit(SALIDA_BLOQUEADO)


def medir() -> carga.Carga:
    return carga.medir(MODELO, ncpu=os.cpu_count(), modelos_propios={MODELO, EMBED})   # inyectado: sin cache


# --- Ollama ------------------------------------------------------------------------

def ps() -> list[dict]:
    with urllib.request.urlopen(f"{OLLAMA}/api/ps", timeout=10) as r:
        return json.loads(r.read()).get("models", [])


def nombres(lista: list[dict]) -> list[str]:
    return [m.get("name", "") for m in lista]


def cargado(nombre: str, lista: list[dict] | None = None) -> bool:
    return any(carga.mismo_modelo(n, nombre) for n in nombres(ps() if lista is None else lista))


def esperar_ps(condicion, segundos: int = 30) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        try:
            if condicion(ps()):
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def calentar_embed() -> None:
    """Carga bge-m3 con keep_alive 5m EXPLICITO, sin pasar por OllamaEmbed:
    bajo `justa`/`cargada` `keep_alive_embed` es 0 y el modelo se descargaria
    solo al terminar, y el evict del paso V actuaria sobre un modelo no
    residente (lo cargaria y descargaria: un [ok] vacuo)."""
    datos = json.dumps({"model": EMBED, "input": ["x"], "truncate": True, "keep_alive": "5m"}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/embed", data=datos, method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=120):
        pass


def _ollama_listo() -> None:
    try:
        with urllib.request.urlopen(f"{OLLAMA}/api/tags", timeout=5) as r:
            tags = nombres(json.loads(r.read()).get("models", []))
    except Exception as e:
        sys.exit(f"Ollama no responde en {OLLAMA}: {e}")
    for modelo in (MODELO, EMBED):
        if not any(carga.mismo_modelo(t, modelo) for t in tags):
            sys.exit(f"Ollama no tiene {modelo}: {tags}")


def _puerto_libre(puerto: int) -> None:
    try:
        with socket.create_connection(("127.0.0.1", puerto), timeout=1):
            pass
    except OSError:
        return
    sys.exit(f"algo ya escucha en 127.0.0.1:{puerto}: no levanto nada ahi")


# --- el proxy ("Ollama caido" sin matar a Ollama) ---------------------------------

class Proxy:
    """Un reenvio TCP 127.0.0.1:PUERTO_PROXY -> 127.0.0.1:11434 que se corta
    (cierra el listener y las conexiones vivas) y se reanuda. El server
    desechable apunta su embedder aca (CALIPSO_EMBED_URL); el sensor de la
    carga y el 7b van directo (carga.OLLAMA, dispatch)."""

    def __init__(self, destino=("127.0.0.1", 11434)) -> None:
        self.destino = destino
        self.listener: socket.socket | None = None
        self.conexiones: set[socket.socket] = set()
        self.lock = threading.Lock()

    def reanudar(self) -> None:
        l = socket.socket()
        l.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        l.bind(("127.0.0.1", PUERTO_PROXY))
        l.listen(16)
        self.listener = l
        threading.Thread(target=self._aceptar, args=(l,), daemon=True).start()

    def cortar(self) -> None:
        l, self.listener = self.listener, None
        if l is not None:
            # shutdown ANTES de close: en Linux, close() sobre un listener con
            # otro hilo bloqueado en accept() no despierta ese accept, y el
            # listener sigue vivo hasta que devuelve: la PRIMERA conexion tras
            # el corte pasaba (corrida 1 del smoke: el recall del turno C llego
            # a Ollama y solo fallaron las consultas del abismo y el remember).
            # shutdown(SHUT_RDWR) lo saca con EINVAL y el puerto rechaza en el acto.
            try:
                l.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            l.close()
        with self.lock:
            for s in list(self.conexiones):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    s.close()
                except OSError:
                    pass
            self.conexiones.clear()

    def _aceptar(self, l: socket.socket) -> None:
        while True:
            try:
                cliente, _ = l.accept()
            except OSError:
                return
            try:
                arriba = socket.create_connection(self.destino, timeout=10)
            except OSError:
                cliente.close()
                continue
            with self.lock:
                self.conexiones.update({cliente, arriba})
            for a, b in ((cliente, arriba), (arriba, cliente)):
                threading.Thread(target=self._bombear, args=(a, b), daemon=True).start()

    def _bombear(self, a: socket.socket, b: socket.socket) -> None:
        try:
            while True:
                datos = a.recv(65536)
                if not datos:
                    break
                b.sendall(datos)
        except OSError:
            pass
        finally:
            for s in (a, b):
                try:
                    s.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    s.close()
                except OSError:
                    pass
            with self.lock:
                self.conexiones.discard(a)
                self.conexiones.discard(b)


# --- el server desechable ------------------------------------------------------------

def restaurar_home() -> pathlib.Path:
    home = pathlib.Path(tempfile.mkdtemp(prefix="memoria-smoke-"))
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
               "CALIPSO_TOKEN": self.token, "CALIPSO_NO_TOTP": "1",
               "CALIPSO_EMBED_URL": EMBED_URL}
        env.pop("CALIPSO_EMBED_FALSA", None)
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

    def telemetria(self, kind: str) -> list[dict]:
        ruta = self.home / "telemetry.jsonl"
        if not ruta.exists():
            return []
        filas = [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
        return [f for f in filas if f.get("kind") == kind]

    def esperar_fila(self, kind: str, accion: str, segundos: int = 60) -> dict | None:
        limite = time.monotonic() + segundos
        while time.monotonic() < limite:
            for f in self.telemetria(kind):
                if f.get("accion") == accion:
                    return f
            time.sleep(1)
        return None

    def esperar_episodios(self, n: int, segundos: int = 120) -> float | None:
        """Segundos hasta que /api/memory dice global_episodes >= n (el
        remember de fondo), o None."""
        t0 = time.monotonic()
        limite = t0 + segundos
        while time.monotonic() < limite:
            if self.http("GET", "/api/memory")["global_episodes"] >= n:
                return round(time.monotonic() - t0, 2)
            time.sleep(0.2)
        return None


# --- un turno ------------------------------------------------------------------------

def chat_nuevo(server: Server, titulo: str) -> str:
    cid = server.http("POST", "/api/chats", {"title": titulo})["id"]
    server.http("POST", f"/api/chats/{cid}/activate", {})
    return cid


async def _turno(server: Server, mensaje: str) -> dict:
    import websockets   # en el .venv (lo usa test_chat_live.py)
    cid = chat_nuevo(server, f"memoria {mensaje[:24]}")
    t0 = time.monotonic()
    texto, meta, error = [], None, None
    t_ultimo_chunk = t_done = None
    async with websockets.connect(WS, additional_headers={"Cookie": f"calipso_token={server.token}"},
                                  max_size=None) as ws:
        await ws.send(json.dumps({"text": mensaje, "chat_id": cid}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=PLAZO_TURNO_S)
            try:
                pkt = json.loads(raw)
            except Exception:
                continue
            t = pkt.get("type", "")
            if t == "chunk":
                texto.append(pkt.get("text", ""))
                t_ultimo_chunk = time.monotonic()
            elif t == "meta" and meta is None:
                meta = pkt
            elif t == "error":
                error = pkt.get("text")
            elif t == "done":
                t_done = time.monotonic()
                break
    return {"chat": cid, "texto": "".join(texto), "meta": meta, "error": error,
            "ms": int((time.monotonic() - t0) * 1000),
            "done_tras_ultimo_chunk_ms": (int((t_done - t_ultimo_chunk) * 1000)
                                          if t_done and t_ultimo_chunk else None)}


def turno(server: Server, mensaje: str) -> dict:
    return asyncio.run(_turno(server, mensaje))


# --- el reindex sobre copias ------------------------------------------------------------

def reindex_sobre_copia(borrar_viva: bool) -> dict:
    copia = pathlib.Path(tempfile.mkdtemp(prefix="memoria-smoke-reindex-"))
    shutil.copytree(FIXTURE, copia, dirs_exist_ok=True)
    if borrar_viva:                                  # EN LA COPIA, jamas en el fixture ni en un home
        for sub in ("global/chroma", "projects/var-home-pedro-calipso/chroma"):
            try:
                chromadb.PersistentClient(path=str(copia / sub)).delete_collection(me.COLECCION_VIVA)
            except Exception:
                pass                                     # la copia del proyecto puede no tener la viva
    env = {**os.environ, "CALIPSO_HOME": str(copia), "CALIPSO_PORT": "1"}
    env.pop("CALIPSO_EMBED_URL", None)
    t0 = time.monotonic()
    r = subprocess.run([sys.executable, "-m", "calipso.memoria_reindex", "--embeddings"],
                       cwd=str(RAIZ), env=env, capture_output=True, text=True, timeout=900)
    cli = chromadb.PersistentClient(path=str(copia / "global" / "chroma"))
    return {"texto": r.stdout + r.stderr, "codigo": r.returncode, "s": time.monotonic() - t0,
            "ids_iguales": me.ids_de(cli, me.COLECCION_VIEJA) == me.ids_de(cli, me.COLECCION_VIVA),
            "sin_reindexar": me.sin_reindexar(cli)}


# --- los resultados ---------------------------------------------------------------------

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


# --- el smoke ------------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="el smoke de la memoria por Ollama")
    ap.add_argument("--sin-esperar", action="store_true", help="saltar --esperar (solo si ya se corrio a mano)")
    args = ap.parse_args(argv)
    R = Resultados()
    # 0
    if not args.sin_esperar:
        esperar_no_cargada()
    _ollama_listo()
    _puerto_libre(PUERTO)
    _puerto_libre(PUERTO_PROXY)
    c0 = medir()
    R.nota("0 la maquina", f"{c0.nivel} ({c0.motivo}) mem_disponible {c0.mem_disponible_mb} MB efectiva "
                           f"{c0.mem_efectiva_mb}; /api/ps {nombres(ps())}")
    proxy = Proxy()
    proxy.reanudar()
    home = restaurar_home()
    server = Server(home)
    server.esperar()
    R.nota("0 server", f"8779 arriba sobre {home}; embedder por el proxy {EMBED_URL}")
    try:
        # A
        m = server.http("GET", "/api/memory")
        R.ok("A /api/memory", m["global_episodes"] == 16 and m["sin_reindexar"] == {"global": 0, "project": 0}
             and m["recall_ok"] is True and m["ultimo_recall_fallo"] is None,
             json.dumps({k: m.get(k) for k in ("global_episodes", "project_episodes", "sin_reindexar",
                                                "recall_ok", "ultimo_recall_fallo")}))
        # R1: recall real en este proceso sobre otra copia
        from calipso import memory
        memory.CALIPSO_HOME = restaurar_home()
        mem = memory.Memory(project_root=str(RAIZ))
        assert type(mem._embed) is me.OllamaEmbed, "el smoke construyo la EF falsa"
        t0 = time.monotonic()
        hits = mem.recall("hola, que libro te conte que empece?", n=4)
        dt = time.monotonic() - t0
        R.ok("R1 recall real por bge-m3 (frio)", bool(hits) and mem.recall_ok and "libro" in hits[0]["text"].lower(),
             f"{dt:.2f} s; top-4: " + " | ".join(f"{h['score']} {h['text'][16:70]!r}" for h in hits))
        t0 = time.monotonic()
        hits = mem.recall("che, quien me presto el libro rosa? no me acuerdo", n=4)
        dt = time.monotonic() - t0
        R.ok("R1 recall caliente", bool(hits) and "rosa" in hits[0]["text"].lower(),
             f"{dt:.2f} s; top-1 {hits[0]['score']} {hits[0]['text'][16:70]!r}")
        R.nota("R1 /api/ps", str(nombres(ps())))
        # R2 + D
        t = turno(server, "/local hola, que libro te conte que empece?")
        fallos_recall = [f for f in server.telemetria("memoria") if f["accion"] == "recall_fallo"]
        R.ok("R2 turno con recall por el server", t["error"] is None and t["texto"].strip() != "" and not fallos_recall,
             f"{t['ms']} ms; ruta {(t['meta'] or {}).get('route')}/{(t['meta'] or {}).get('model')}; "
             f"texto {t['texto'][:80]!r}")
        R.ok("D done antes del remember", t["done_tras_ultimo_chunk_ms"] is not None and t["done_tras_ultimo_chunk_ms"] < 500,
             f"{t['done_tras_ultimo_chunk_ms']} ms entre el ultimo chunk y done")
        s_rem = server.esperar_episodios(17)
        R.ok("D el remember de fondo", s_rem is not None, f"global_episodes 16 -> 17 en {s_rem} s tras el done")
        R.nota("D /api/ps tras el turno", str(nombres(ps())))
        # C: Ollama caido a mitad (para el embedder)
        proxy.cortar()
        t = turno(server, "/local en que quedamos la otra vez con el presupuesto del taller?")
        fallos_recall = [f for f in server.telemetria("memoria") if f["accion"] == "recall_fallo"]
        R.ok("C turno con Ollama caido para el embedder", t["error"] is None and t["texto"].strip() != "" and bool(fallos_recall),
             f"{t['ms']} ms; recall_fallo: {(fallos_recall[-1]['error'][:90] if fallos_recall else None)!r}")
        rf = server.esperar_fila("memoria", "remember_fallo", 60)
        R.ok("C remember_fallo", rf is not None, (rf or {}).get("error", "")[:90])
        m = server.http("GET", "/api/memory")
        R.ok("C /api/memory con recall_ok False", m["recall_ok"] is False and bool(m["ultimo_recall_fallo"]),
             json.dumps(m["ultimo_recall_fallo"]))
        proxy.reanudar()
        t = turno(server, "/local hola de nuevo")
        m = server.http("GET", "/api/memory")
        R.ok("C se recupera solo", t["error"] is None and m["recall_ok"] is True, f"recall_ok {m['recall_ok']}")
        server.esperar_episodios(18)
        # X
        r1 = reindex_sobre_copia(borrar_viva=False)
        R.ok("X reindex idempotente sobre el fixture", r1["codigo"] == 0 and "0 copiados" in r1["texto"]
             and "16 ya estaban" in r1["texto"] and r1["sin_reindexar"] == 0, f"{r1['s']:.1f} s")
        r2 = reindex_sobre_copia(borrar_viva=True)
        R.ok("X reindex desde cero (la viva borrada en la copia)", r2["codigo"] == 0 and "16 copiados" in r2["texto"]
             and r2["ids_iguales"] and r2["sin_reindexar"] == 0, f"{r2['s']:.1f} s para 16 documentos")
        # V
        calentar_embed()                                   # keep_alive 5m explicito: residente pase lo que pase con el nivel
        residente = esperar_ps(lambda l: cargado(EMBED, l), 20)
        cv = medir()
        ok = carga.ollama_evict(EMBED, embedding=True)
        R.ok("V descarga del embedder por /api/embed", residente and ok and esperar_ps(lambda l: not cargado(EMBED, l), 20),
             f"residente antes del evict {residente}; nivel {cv.nivel} (keep_alive_embed {carga.keep_alive_embed(cv.nivel)!r}); "
             f"ollama_evict {ok}; /api/ps {nombres(ps())}")
        # J
        antes = ps()
        c1 = medir()
        t1 = turno(server, "/local decime en una linea que es un websocket")
        ps_done1 = ps()
        server.esperar_episodios(19)
        ps_rem1 = ps()
        R.nota("J nivel", f"{c1.nivel} ({c1.motivo}) mem_disponible {c1.mem_disponible_mb} efectiva {c1.mem_efectiva_mb}; "
                          f"keep_alive_embed {carga.keep_alive_embed(c1.nivel)!r}")
        R.nota("J turno 1 (carga el 7b)", f"antes {nombres(antes)}; tras done {nombres(ps_done1)}; tras remember "
                                          f"{nombres(ps_rem1)}; {t1['ms']} ms")
        antes2 = ps()
        c2 = medir()
        t2 = turno(server, "/local y en dos lineas, que es http?")
        ps_done2 = ps()
        s_rem2 = server.esperar_episodios(20)
        ps_rem2 = ps()
        desalojado = cargado(MODELO, antes2) and (not cargado(MODELO, ps_done2) or not cargado(MODELO, ps_rem2))
        R.ok("J convivencia con el 7b", not desalojado,
             f"nivel {c2.nivel}; antes {nombres(antes2)}; tras done {nombres(ps_done2)}; tras remember {nombres(ps_rem2)}; "
             f"turno {t2['ms']} ms, remember {s_rem2} s"
             + ("  PARADA: Ollama desalojo al 7b (ruling 8.4): decidir con Pedro" if desalojado else ""))
    finally:
        server.apagar()
        proxy.cortar()
    print("\n== resumen ==")
    for paso, cond, detalle in R.filas:
        print(f"  [{'ok' if cond else 'FALLO'}] {paso}: {detalle[:160]}")
    (HOME_AGENTE / "resultados.json").write_text(
        json.dumps([{"paso": p, "ok": c, "detalle": d} for p, c, d in R.filas], ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"resultados: {HOME_AGENTE / 'resultados.json'}; server.log: {home / 'server.log'}; fallos: {R.fallos()}")
    return 1 if R.fallos() else 0


if __name__ == "__main__":
    sys.exit(main())
