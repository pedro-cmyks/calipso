"""El porton de la letra de la reentrada (spec canarios 2026-09-11, seccion
4 y 6): las 4 preguntas del fixture de la memoria, chat nuevo por turno,
N=3 por condicion (12 turnos por condicion; con N=2 el porton de la memoria
vario 2-4 en el ruido), en dos condiciones sobre ESTA rama y el mismo
server: `vieja` (CALIPSO_REENTRADA=vieja: la letra de siempre aunque haya
bloques) y `nueva` (la letra con bloques). Por turno se cuentan:
- `sin_anclaje`: del evento `canario` del ws (len(anclaje.sin_anclaje));
- `sin_dato`: `memoria_procedencia.clasificar(texto) == "sin_dato"`;
- `sin_dato falso`: es sin_dato Y la verdad sembrada del fixture aparece en
  un bloque que subio en ese turno (la fila `chat_turn` del server
  desechable lleva los bloques: CANARIOS_PERSISTIR_CONTEXTO=1; en
  produccion no).
Una fila cuenta en los totales SOLO si la contesto el 7b bajo prueba
(`valida`: ruta `local/...` y no el aviso `[Calipso] ...` del server); las
otras se listan aparte en el informe y no tocan el veredicto. La corrida
del 2026-09-11 lo mostro: con Ollama caido por un OOM, un turno `/local` se
fue a subscription/opus (server.py: el filtro de force_route cae al
ranking entero) y otro fue el aviso del server; un "no trae el dato" de
Opus habria contado como sin_dato de `nueva` y mandado LETRA_DEFAULT a
"vieja" por un modelo que no esta bajo prueba.
Regla de aterrizaje: la letra nueva queda (LETRA_DEFAULT="nueva") solo si
NO empeora en ninguna de las tres; si empeora en alguna, LETRA_DEFAULT pasa
a "vieja" y el informe lo dice. Molde: experimentos/porton_memoria.py
(server desechable uvicorn en 8776, home restaurado desde el fixture por
condicion y por pasada, jamas ~/.calipso ni el server real; Ollama real en
11434 con qwen2.5:7b; `websockets` del .venv). Ademas persiste, por fila,
el contexto que viajo (system, historial, bloques): es el material del
banco de anclaje con contexto exacto.

Uso: `.venv/bin/python -m experimentos.porton_reentrada [--n 3]
[--condiciones vieja,nueva]`; `--informe` relee el JSONL de la ultima
corrida y reescribe el MD sin levantar nada (ni Ollama ni server).
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
SALIDA_JSONL = RAIZ / "experimentos" / "porton_reentrada_resultados.jsonl"
SALIDA_MD = RAIZ / "experimentos" / "porton_reentrada_resultados.md"
PUERTO = 8776
BASE = f"http://127.0.0.1:{PUERTO}"
WS = f"ws://127.0.0.1:{PUERTO}/ws/chat"
OLLAMA = "http://127.0.0.1:11434"
MODELO = "qwen2.5:7b"

# las mismas 4 preguntas y verdades del porton de la memoria
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
CONDICIONES = ("vieja", "nueva")


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c)).lower()


def verdades_de(clave: str) -> tuple:
    return dict((c, v) for c, _, v in PREGUNTAS)[clave]


def tiene_verdad(clave: str, texto: str) -> bool:
    low = _sin_acentos(texto)
    verdades = verdades_de(clave)
    return any(v in low for v in verdades) if clave == "presupuesto" else all(v in low for v in verdades)


def clasificar_turno(clave: str, texto: str, clasificar) -> str:
    if tiene_verdad(clave, texto):
        return "dato"
    if clasificar(texto) == "sin_dato":
        return "sin_dato"
    return "confabula"


def sin_dato_falso(clave: str, clase: str, bloques: list[str]) -> bool:
    """No-saber con la verdad a la vista: la respuesta es sin_dato y algun
    bloque que subio en el turno trae la verdad sembrada."""
    return clase == "sin_dato" and any(tiene_verdad(clave, b) for b in bloques)


AVISO_DEL_SERVER = "[Calipso]"


def es_valida(ruta: str | None, texto: str) -> bool:
    """La fila la contesto el 7b bajo prueba: ruta `local/...` (no la nube,
    a la que un `/local` cae si Ollama figura caido) y no el aviso del
    server (`[Calipso] no puedo contestar esto con el modelo local: ...`,
    que sale cuando Ollama no esta). Lo demas no mide la letra."""
    return (ruta or "").startswith("local/") and not texto.lstrip().startswith(AVISO_DEL_SERVER)


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
    """Un CALIPSO_HOME nuevo con el fixture adentro y un catastro.json minimo
    (la raiz declarada es el repo: POST /api/chats exige que ROOT este en
    una raiz del catastro; profundidad 1 frena el escaneo ahi)."""
    home = pathlib.Path(tempfile.mkdtemp(prefix="porton-reentrada-"))
    shutil.copytree(FIXTURE, home, dirs_exist_ok=True)
    (home / "README.md").unlink(missing_ok=True)
    (home / "catastro.json").write_text(
        json.dumps({"raices": [{"ruta": str(raiz), "profundidad": 1}],
                    "proyectos": []}), encoding="utf-8")
    return home


def entorno_server(home: pathlib.Path, raiz: pathlib.Path, token: str, condicion: str) -> dict:
    env = {**os.environ, "CALIPSO_HOME": str(home), "CALIPSO_ROOT": str(raiz),
           "CALIPSO_TOKEN": token, "CALIPSO_NO_TOTP": "1",
           "CALIPSO_REENTRADA": condicion, "CANARIOS_PERSISTIR_CONTEXTO": "1"}
    env.pop("MEMORIA_PRESENTAR", None)
    return env


class Server:
    def __init__(self, home: pathlib.Path, condicion: str, raiz: pathlib.Path = RAIZ):
        self.home = home
        self.codigo = subprocess.run(["git", "-C", str(raiz), "rev-parse", "--short", "HEAD"],
                                     check=True, capture_output=True, text=True).stdout.strip()
        self.token = secrets.token_urlsafe(24)
        self.log = open(home / "server.log", "w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "calipso.server:app",
             "--host", "127.0.0.1", "--port", str(PUERTO)],
            cwd=str(raiz), env=entorno_server(home, raiz, self.token, condicion),
            stdout=self.log, stderr=subprocess.STDOUT)

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
    eventos, texto, ruta, canario = [], [], None, None
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
            elif t == "canario":
                canario = pkt
            elif t == "done":
                break
            elif t == "error":
                eventos.append({"error": pkt.get("text")})
                break
    return {"chat": cid, "ruta": ruta, "abismo": eventos, "canario": canario,
            "ms": int((time.monotonic() - t0) * 1000), "texto": "".join(texto)}


def ultima_fila_chat_turn(home: pathlib.Path) -> dict:
    ruta = home / "telemetry.jsonl"
    filas = [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
    turnos = [f for f in filas if f.get("kind") == "chat_turn"]
    return turnos[-1] if turnos else {}


# --- el porton ---------------------------------------------------------------

def fila_de(condicion, pasada, clave, mensaje, r, fila_tele, clasificar, codigo) -> dict:
    clase = clasificar_turno(clave, r["texto"], clasificar)
    bloques = (fila_tele.get("contexto") or {}).get("bloques") or []
    a = ((r.get("canario") or {}).get("anclaje")) or {}
    return {"condicion": condicion, "pasada": pasada, "pregunta": clave, "mensaje": mensaje,
            "clase": clase, "consulto": any(e.get("fase") for e in r["abismo"]),
            "sin_anclaje": len(a.get("sin_anclaje") or []),
            "aplica": bool(a.get("aplica")),
            "degeneracion": [s.get("senal") for s in (r.get("canario") or {}).get("degeneracion") or []],
            "sin_dato": clase == "sin_dato",
            "sin_dato_falso": sin_dato_falso(clave, clase, bloques),
            "bloques": bloques, "contexto": fila_tele.get("contexto"),
            "chat": r["chat"], "ruta": r["ruta"], "valida": es_valida(r["ruta"], r["texto"]),
            "abismo": r["abismo"], "ms": r["ms"],
            "texto": r["texto"], "codigo": codigo,
            "ts": datetime.datetime.now().isoformat(timespec="seconds")}


def correr(condiciones: list[str], n: int, clasificar) -> list[dict]:
    filas = []
    for condicion in condiciones:
        for pasada in range(1, n + 1):
            home = restaurar_home()
            server = Server(home, condicion)
            print(f"[{condicion} pasada {pasada}] server en {BASE} ({server.codigo}), home {home}", flush=True)
            try:
                server.esperar()
                for clave, mensaje, _ in PREGUNTAS:
                    r = asyncio.run(turno(server.token, mensaje))
                    fila = fila_de(condicion, pasada, clave, mensaje, r,
                                   ultima_fila_chat_turn(home), clasificar, server.codigo)
                    filas.append(fila)
                    with SALIDA_JSONL.open("a", encoding="utf-8") as f:
                        f.write(json.dumps(fila, ensure_ascii=False) + "\n")
                    print(f"   {clave:12} {fila['clase']:9} consulto={fila['consulto']!s:5} "
                          f"sin_anclaje={fila['sin_anclaje']} sdf={fila['sin_dato_falso']!s:5} "
                          f"{fila['ms']:6} ms {fila['ruta']}"
                          f"{'' if fila['valida'] else ' (NO CUENTA)'} :: {r['texto'][:90]!r}",
                          flush=True)
            finally:
                server.apagar()
    return filas


def filas_excluidas(filas: list[dict]) -> list[dict]:
    return [f for f in filas if not f["valida"]]


def cargar_filas(ruta: pathlib.Path = SALIDA_JSONL) -> list[dict]:
    """Las filas de una corrida; a las anteriores a la columna `valida` se
    les deriva de su ruta y su texto (la corrida del 2026-09-11)."""
    filas = [json.loads(l) for l in ruta.read_text(encoding="utf-8").splitlines() if l.strip()]
    for f in filas:
        f.setdefault("valida", es_valida(f.get("ruta"), f.get("texto") or ""))
    return filas


def totales(filas: list[dict]) -> dict:
    """Por condicion, SOLO sobre las filas validas (las que contesto el 7b
    bajo prueba); `excluidas` cuenta las otras, que no entran en nada."""
    t = {}
    for c in dict.fromkeys(f["condicion"] for f in filas):
        todas = [f for f in filas if f["condicion"] == c]
        de = [f for f in todas if f["valida"]]
        t[c] = {"turnos": len(de),
                "dato": sum(1 for f in de if f["clase"] == "dato"),
                "confabula": sum(1 for f in de if f["clase"] == "confabula"),
                "sin_anclaje": sum(f["sin_anclaje"] for f in de),
                "sin_dato": sum(1 for f in de if f["sin_dato"]),
                "sin_dato_falso": sum(1 for f in de if f["sin_dato_falso"]),
                "consulto": sum(1 for f in de if f["consulto"]),
                "degeneracion": sum(1 for f in de if f["degeneracion"]),
                "excluidas": len(todas) - len(de)}
    return t


def aterriza_nueva(t: dict) -> bool | None:
    """La regla del spec: solo si no empeora en NINGUNA de las tres. None si
    falta una condicion."""
    if "vieja" not in t or "nueva" not in t:
        return None
    v, n = t["vieja"], t["nueva"]
    return all(n[k] <= v[k] for k in ("sin_anclaje", "sin_dato", "sin_dato_falso"))


def resumen(filas: list[dict]) -> str:
    t = totales(filas)
    # la fecha y el codigo son los de la corrida (las filas), no los de
    # cuando se escribe el informe (--informe lo regenera despues)
    corrido = (filas[-1].get("ts") if filas else None) or datetime.datetime.now().isoformat(timespec="seconds")
    codigo = (filas[-1].get("codigo") if filas else None) or "?"
    lineas = ["# Porton de la letra de la reentrada -- resultados", "",
              f"Corrido el {corrido[:16]} (arbol `{codigo}`) sobre el fixture "
              f"`experimentos/fixtures/memoria_smoke_home`, chat nuevo por turno, server desechable en "
              f"{BASE}, {MODELO}, CANARIOS_PERSISTIR_CONTEXTO=1. Condiciones: `vieja` "
              "(CALIPSO_REENTRADA=vieja, la letra de siempre) y `nueva` (la letra con bloques). "
              "Se cuentan `sin_anclaje` (del canario), `sin_dato` (clasificar) y `sin_dato falso` "
              "(no-saber con la verdad en un bloque que subio). Cuenta SOLO la fila que contesto "
              f"el 7b bajo prueba (`valida`: ruta `local/` y no el aviso `{AVISO_DEL_SERVER} ...` "
              "del server); las otras se listan aparte y no entran en los totales ni en el veredicto.", "",
              "## Totales por condicion (solo filas validas)", "",
              "| condicion | turnos | dato | sin_dato | confabula | sin_anclaje | sin_dato falso | consulto | degeneracion | excluidas |",
              "|---|---|---|---|---|---|---|---|---|---|"]
    for c, x in t.items():
        lineas.append(f"| {c} | {x['turnos']} | {x['dato']} | {x['sin_dato']} | {x['confabula']} | "
                      f"{x['sin_anclaje']} | {x['sin_dato_falso']} | {x['consulto']} | {x['degeneracion']} | "
                      f"{x['excluidas']} |")
    lineas += ["", "## Cada turno", "",
               "| condicion | pasada | pregunta | clase | ruta | valida | consulto | sin_anclaje | sdf | senales | ms | respuesta (200 chars) |",
               "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for f in filas:
        resp = " ".join(f["texto"].split())[:200].replace("|", "/")
        lineas.append(f"| {f['condicion']} | {f['pasada']} | {f['pregunta']} | {f['clase']} | "
                      f"{f['ruta'] or '-'} | {'si' if f['valida'] else 'no'} | "
                      f"{'si' if f['consulto'] else 'no'} | {f['sin_anclaje']} | "
                      f"{'si' if f['sin_dato_falso'] else 'no'} | {','.join(f['degeneracion']) or '-'} | "
                      f"{f['ms']} | {resp} |")
    excluidas = filas_excluidas(filas)
    lineas += ["", "## Filas excluidas (no las contesto el 7b bajo prueba)", ""]
    if not excluidas:
        lineas.append("Ninguna: las contesto todas el 7b local.")
    for f in excluidas:
        motivo = ("el aviso del server (Ollama no estaba)"
                  if (f["texto"] or "").lstrip().startswith(AVISO_DEL_SERVER)
                  else f"ruta `{f['ruta'] or '-'}`, no local")
        lineas.append(f"- `{f['condicion']}/{f['pasada']}/{f['pregunta']}`: {motivo}; clase `{f['clase']}`, "
                      f"sin_anclaje {f['sin_anclaje']}, sin_dato {'si' if f['sin_dato'] else 'no'}, "
                      f"sdf {'si' if f['sin_dato_falso'] else 'no'} (no suman).")
    lineas += ["", "## Aterrizaje (regla del spec, seccion 6)", ""]
    veredicto = aterriza_nueva(t)
    nota = f" Se leyo con {len(excluidas)} filas excluidas (las de arriba)." if excluidas else ""
    if veredicto is None:
        lineas.append("Falta una condicion: no se decide." + nota)
    elif veredicto:
        lineas.append("La letra nueva no empeora en ninguna de las tres: queda `LETRA_DEFAULT = \"nueva\"`." + nota)
    else:
        lineas.append("La letra nueva empeora en alguna de las tres: `LETRA_DEFAULT` pasa a `\"vieja\"` "
                      "(la letra queda en el archivo de variantes como medida, sin aterrizar)." + nota)
    return "\n".join(lineas) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--n", type=int, default=3, help="pasadas por condicion (default 3)")
    ap.add_argument("--condiciones", default="vieja,nueva")
    ap.add_argument("--informe", action="store_true",
                    help="no corre nada: relee el JSONL de la ultima corrida y reescribe el MD")
    args = ap.parse_args(argv)
    if args.informe:
        if not SALIDA_JSONL.is_file():
            sys.exit(f"no hay corrida que releer: falta {SALIDA_JSONL}")
        SALIDA_MD.write_text(resumen(cargar_filas(SALIDA_JSONL)), encoding="utf-8")
        print(f"informe regenerado: {SALIDA_MD}")
        return 0
    condiciones = [c.strip() for c in args.condiciones.split(",") if c.strip()]
    for c in condiciones:
        if c not in CONDICIONES:
            sys.exit(f"condicion desconocida: {c}")
    if not FIXTURE.is_dir():
        sys.exit(f"falta el fixture {FIXTURE}")
    sys.path.insert(0, str(RAIZ))
    from calipso.memoria_procedencia import clasificar   # puro: no toca el home
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
