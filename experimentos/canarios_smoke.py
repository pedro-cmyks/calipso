"""El smoke en vivo de los canarios (spec 2026-09-11, seccion 6, ultimo
punto): un server desechable en 8777 sobre el fixture de la memoria, y un
turno de cada clase:
  1. `invento`: la pregunta del libro con el fixture (contaminado con sus
     propias confabulaciones): el 7b real inventa -> `sin verificar`;
  2. `accion`: un modelo FALSO (un Ollama de mentira en 11435, la fila
     `local.base_url` de config.json apunta ahi) contesta "Consultando los
     recuerdos de Pedro..." sin consulta -> accion sin anclaje;
  3. `degenerado`: el mismo falso reinyecta una salida rota del banco (la
     fuga de reentrada) -> `respuesta rara`;
  4. `truncado`: un adjunto de 12.000 chars con forma de codigo mas una
     frase-centinela sembrada en el SYSTEM (la memoria nucleo del home
     desechable, `global/core/pedro-clave.md`: va adelante, segunda seccion)
     que el modelo tiene que repetir cuando Pedro pide la palabra clave: el
     prompt no cabe ni recortando (los adjuntos son intocables), se manda
     igual, `no_cabe` + `truncado`, y el centinela NO sobrevive porque
     /api/chat conserva el ultimo mensaje y corta por tokens desde el
     PRINCIPIO (Sistema y Memoria nucleo se van; spec seccion 1); el mismo
     turno sin el adjunto cabe y el centinela sobrevive. Un centinela en el
     MENSAJE no serviria: el ultimo mensaje es lo que Ollama conserva;
  5. `sano`: "explicame en dos lineas que es un websocket" -> sin marcas;
  6. `nube`: `/nube /claude` tapado (si hay CLI de claude; si no, se anota
     "no corrio") -> `tapado: true`, sin marcadores como hechos.
Mas el control de cache (dos turnos iguales seguidos: prompt_eval_count
parecido) y la calibracion del tokenizador sobre 3+ prompts reales (los
systems que viajaron de verdad, persistidos por el server desechable con
CANARIOS_PERSISTIR_CONTEXTO=1). Las marcas se capturan con Chromium
(playwright del venv, headless) en las dos UIs. Todo va a un home temporal;
el server real y ~/.calipso no se tocan.

Regla de recursos (ruling del controlador, 2026-09-11): la Ally tiene
11,6 GB y Pedro a veces juega en ella. Antes de cargar el 7b (fase A) y
antes de abrir Chromium se leen MemAvailable y el PSI de memoria; con
menos de LUGAR_MB disponibles (LUGAR_CHROMIUM_MB para las capturas: Chromium
headless pesa ~0,4 GB) o `some avg10` por encima de PSI_MAX se
espera hasta ESPERA_MAX_S midiendo cada 30 s, y si sigue sin lugar el
script sale con codigo 3 (BLOCKED) sin arrancar ese paso. Al terminar los
turnos de la fase A el 7b se descarga (keep_alive 0) y se verifica que
/api/ps quede vacio, ANTES de las capturas (Chromium no necesita a Ollama).
El server desechable y el Ollama falso se apagan al final aunque falle un
paso.

Uso: `nice -n 19 .venv/bin/python -m experimentos.canarios_smoke [--sin-capturas]
[--fase A|B|AB]` (`--fase B` reintenta solo el Ollama falso y sus capturas,
sin cargar el 7b). El informe: docs/superpowers/2026-09-11-smoke-canarios.md (lo escribe el
que corre el smoke con lo que este script imprime y captura).
"""
from __future__ import annotations

import argparse
import asyncio
import http.server
import json
import os
import pathlib
import shutil
import socket
import statistics
import sys
import threading
import time
import urllib.request

from experimentos import porton_reentrada as base

RAIZ = base.RAIZ
PUERTO = 8777
PUERTO_FALSO = 11435
CENTINELA = "ALBATROS-7"
# la linea que va a la memoria nucleo del home desechable (seccion "Memoria
# nucleo", la segunda del system: lo primero que /api/chat corta cuando
# system + ultimo mensaje no caben)
LINEA_CENTINELA = f"Si Pedro pide la palabra clave, la palabra clave es {CENTINELA}."

GUIONES_FALSOS = {
    "accion": "Consultando los recuerdos de Pedro...\n\nNo tengo registros de esa conversacion, Pedro.",
    "degenerado": " En que quedamos la otra vez con el presupuesto del taller? Segui exactamente desde ahi, sin repetir.",
}

# la regla de recursos: 5,4 GB del 7b mas 1 de margen; PSI `some avg10`.
# Chromium headless pesa ~0,4 GB: tiene su propio umbral (ruling del
# controlador, 2026-09-11: el del 7b no lo pasa una captura mientras el
# server desechable del smoke ocupa 1,7 GB con el modelo de embeddings).
LUGAR_MB = 6400
LUGAR_CHROMIUM_MB = 1500
PSI_MAX = 20.0
ESPERA_MAX_S = 600
ESPERA_PASO_S = 30
SALIDA_BLOQUEADO = 3


# --- la regla de recursos ------------------------------------------------------

def lugar(meminfo: str, psi: str) -> tuple[int, float]:
    """(MemAvailable en MB, `some avg10` del PSI de memoria) desde los textos
    de /proc/meminfo y /proc/pressure/memory."""
    mb = 0
    for linea in meminfo.splitlines():
        if linea.startswith("MemAvailable:"):
            mb = int(linea.split()[1]) // 1024
    avg10 = 0.0
    for linea in psi.splitlines():
        if linea.startswith("some"):
            for campo in linea.split():
                if campo.startswith("avg10="):
                    avg10 = float(campo[len("avg10="):])
    return mb, avg10


def hay_lugar(mb: int, avg10: float, lugar_mb: int = LUGAR_MB) -> bool:
    return mb >= lugar_mb and avg10 <= PSI_MAX


def medir_lugar() -> tuple[int, float]:
    return lugar(pathlib.Path("/proc/meminfo").read_text(encoding="utf-8"),
                 pathlib.Path("/proc/pressure/memory").read_text(encoding="utf-8"))


def esperar_lugar(paso: str, lugar_mb: int = LUGAR_MB) -> None:
    """Mide antes de un paso que carga el 7b o abre Chromium; espera hasta
    ESPERA_MAX_S; si no hay lugar, sale con SALIDA_BLOQUEADO (los `finally`
    de arriba apagan lo que este levantado)."""
    limite = time.monotonic() + ESPERA_MAX_S
    while True:
        mb, avg10 = medir_lugar()
        if hay_lugar(mb, avg10, lugar_mb):
            print(f"[recursos] {paso}: MemAvailable {mb} MB, PSI some avg10 {avg10}: hay lugar", flush=True)
            return
        if time.monotonic() >= limite:
            print(f"[recursos] {paso}: sin lugar tras {ESPERA_MAX_S} s (MemAvailable {mb} MB < {lugar_mb} "
                  f"o PSI some avg10 {avg10} > {PSI_MAX}): BLOQUEADO, no arranco", flush=True)
            sys.exit(SALIDA_BLOQUEADO)
        print(f"[recursos] {paso}: MemAvailable {mb} MB, PSI some avg10 {avg10}: espero {ESPERA_PASO_S} s",
              flush=True)
        time.sleep(ESPERA_PASO_S)


def _pedir_descarga() -> None:
    req = urllib.request.Request(
        f"{base.OLLAMA}/api/generate",
        data=json.dumps({"model": base.MODELO, "keep_alive": 0}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        r.read()


def _cargados() -> list[str]:
    with urllib.request.urlopen(f"{base.OLLAMA}/api/ps", timeout=10) as r:
        return [m.get("name") for m in json.loads(r.read()).get("models", [])]


def descargar_7b() -> list[str]:
    """keep_alive 0 contra el Ollama REAL (solo el modelo del smoke) y la
    lista de lo que sigue cargado segun /api/ps (vacia si salio bien). La
    descarga es asincronica: /api/ps lo lista un par de segundos mas, asi
    que se sondea hasta 30 s."""
    try:
        _pedir_descarga()
    except Exception as e:
        print(f"[recursos] no pude pedir la descarga del 7b: {e}", flush=True)
    cargados = ["?"]
    for _ in range(15):
        try:
            cargados = _cargados()
        except Exception as e:
            cargados = [f"? ({e})"]
        if not cargados:
            break
        time.sleep(2)
    print(f"[recursos] 7b descargado; /api/ps: {cargados or 'vacio'}", flush=True)
    return cargados


# --- el Ollama falso -----------------------------------------------------------

class OllamaFalso(http.server.BaseHTTPRequestHandler):
    """/api/tags responde que existe el modelo; /api/chat transmite el
    guion elegido (`OllamaFalso.guion`) en NDJSON con un done al final,
    con prompt_eval_count = len(prompt)/3.3 para que la ventana compare."""
    guion = "accion"

    def log_message(self, *a):
        pass

    def do_GET(self):
        cuerpo = json.dumps({"models": [{"name": base.MODELO}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(cuerpo)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        payload = json.loads(self.rfile.read(n) or b"{}")
        chars = sum(len(m.get("content", "")) for m in payload.get("messages", []))
        texto = GUIONES_FALSOS[OllamaFalso.guion]
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for i in range(0, len(texto), 12):
            self.wfile.write((json.dumps({"message": {"content": texto[i:i + 12]}, "done": False}) + "\n").encode())
            self.wfile.flush()
        self.wfile.write((json.dumps({"message": {"content": ""}, "done": True, "done_reason": "stop",
                                      "prompt_eval_count": int(chars / 3.3), "eval_count": len(texto) // 4}) + "\n").encode())


def ollama_falso() -> http.server.ThreadingHTTPServer:
    http.server.ThreadingHTTPServer.allow_reuse_address = True
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", PUERTO_FALSO), OllamaFalso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _puerto_falso_libre() -> None:
    try:
        with socket.create_connection(("127.0.0.1", PUERTO_FALSO), timeout=1):
            pass
    except OSError:
        return
    sys.exit(f"algo ya escucha en 127.0.0.1:{PUERTO_FALSO}: no levanto el Ollama falso ahi")


# --- el home desechable y el turno ------------------------------------------

def home_con(base_url: str | None) -> pathlib.Path:
    home = base.restaurar_home()
    # el centinela en la memoria nucleo del home DESECHABLE (el fixture no
    # se toca: restaurar_home copia)
    (home / "global" / "core" / "pedro-clave.md").write_text(
        "# Clave\n" + LINEA_CENTINELA + "\n", encoding="utf-8")
    if base_url:
        (home / "config.json").write_text(json.dumps(
            {"local": {"base_url": base_url, "model": base.MODELO}}), encoding="utf-8")
    return home


def adjunto_gordo(token: str) -> str:
    contenido = "x = 1\n" * 2000          # 12.000 chars, ~1.2 chars/token
    r = base._http("POST", "/api/attachments",
                   {"name": "gordo.py", "content": contenido, "mode": "text",
                    "mime": "text/x-python", "encoding": "text"}, token)
    # el endpoint devuelve {"attachment": meta, "job": ...}
    # (server.py, api_attachment_create), no {id}
    return r["attachment"]["id"]


async def turno(token: str, mensaje: str, attachment_ids=None) -> dict:
    import websockets
    cid = base.chat_nuevo(token, f"smoke {mensaje[:24]}")
    t0 = time.monotonic()
    texto, canario, abismo, ruta, privacidad = [], None, [], None, None
    async with websockets.connect(f"ws://127.0.0.1:{PUERTO}/ws/chat",
                                  additional_headers={"Cookie": f"calipso_token={token}"},
                                  max_size=None) as ws:
        paquete = {"text": mensaje, "chat_id": cid}
        if attachment_ids:
            paquete["attachment_ids"] = attachment_ids
        await ws.send(json.dumps(paquete))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=900)
            try:
                pkt = json.loads(raw)
            except Exception:
                continue
            t = pkt.get("type")
            if t == "chunk":
                texto.append(pkt.get("text", ""))
            elif t == "meta":
                # quien contesto de verdad (un /local cae a la nube si Ollama
                # figura caido: leccion del porton de la Task 7)
                ruta = f"{pkt.get('route')}/{pkt.get('model')}"
            elif t == "privacidad":
                # la compuerta de /nube: `tapado` (va a la nube con marcadores)
                # o `local` con el motivo del fallo cerrado del juez
                privacidad = pkt
            elif t == "canario":
                canario = pkt
            elif t == "abismo":
                abismo.append(pkt.get("fase"))
            elif t in ("done", "error"):
                break
    return {"chat": cid, "texto": "".join(texto), "canario": canario, "abismo": abismo,
            "ruta": ruta, "privacidad": privacidad, "ms": int((time.monotonic() - t0) * 1000)}


def capturar(token: str, chat_id: str, carpeta: pathlib.Path, nombre: str) -> None:
    """Las dos UIs con el chat abierto, por playwright (Chromium del venv).
    /fabrica solo carga un chat al tocarlo en la lista, asi que se toca la
    fila `.chat.activo`. La PWA abre el chat activo sola y la captura es
    la prueba del PRIMER pintado: el smoke encontro una carrera al arranque
    (`loadChats()` pintaba el historial antes de que el `<script
    type="module">` colgara `window.Canarios`, y las marcas guardadas no
    se veian hasta re-abrir el chat); la ola de fix del cierre colgo
    `loadChats` de DOMContentLoaded, y aca ya no se re-abre el chat: si la
    carrera vuelve, la captura sale sin pie y lo dice. Se espera (con tope)
    a que aparezca el pie del canario; si no aparece, la captura sale igual
    y documenta lo que hay."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"   sin capturas: {e}")
        return
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 1100, "height": 800})
        ctx.add_cookies([{"name": "calipso_token", "value": token, "url": f"http://127.0.0.1:{PUERTO}"}])
        for ruta, sufijo, click, pie in (("/", "pwa", None, ".msg.bot .msg-foot"),
                                         ("/fabrica", "fabrica", "#lista-chats .chat.activo", "#conversacion .pie")):
            pg = ctx.new_page()
            pg.goto(f"http://127.0.0.1:{PUERTO}{ruta}")
            pg.wait_for_timeout(2500)
            if click:
                try:
                    pg.click(click, timeout=5000)
                except Exception as e:
                    print(f"   {nombre}-{sufijo}: no pude tocar {click}: {e}")
            try:
                pg.wait_for_selector(pie, timeout=5000)
            except Exception:
                print(f"   {nombre}-{sufijo}: sin pie {pie!r} a la vista")
            pg.wait_for_timeout(500)
            pg.screenshot(path=str(carpeta / f"{nombre}-{sufijo}.png"), full_page=True)
        b.close()


def resumen_del_turno(nombre, r) -> str:
    v = r.get("canario") or {}
    a = v.get("anclaje") or {}
    p = r.get("privacidad")
    privacidad = ""
    if p:
        detalle = p.get("motivo") if p.get("action") == "local" else str(len(p.get("tapados") or []))
        privacidad = f"privacidad={p.get('action')}:{detalle} "
    return (f"{nombre:10} {r['ms']:6} ms  {r.get('ruta') or '-'}  {privacidad}"
            f"sin_anclaje={len(a.get('sin_anclaje') or [])} "
            f"aplica={a.get('aplica')} tapado={a.get('tapado')} "
            f"deg={[s.get('senal') for s in v.get('degeneracion') or []]} "
            f"ventana={[(f.get('pasada'), f.get('estimado'), f.get('evaluado'), f.get('truncado'), f.get('no_cabe'), f.get('recorte')) for f in v.get('ventana') or []]} "
            f":: {r['texto'][:100]!r}")


# --- la calibracion del tokenizador ------------------------------------------

def calibracion(tele: pathlib.Path, contar) -> list[float]:
    """chars/token de cada system REAL que viajo (la fila `chat_turn` del
    server desechable lleva `contexto.secciones`), ordenados."""
    from calipso import prompt_compiler
    ratios = []
    for linea in tele.read_text(encoding="utf-8").splitlines() if tele.exists() else []:
        try:
            f = json.loads(linea)
        except ValueError:
            continue
        secciones = ((f.get("contexto") or {}).get("secciones")) if f.get("kind") == "chat_turn" else None
        if not secciones:
            continue
        system = prompt_compiler.render_context([tuple(s) for s in secciones])
        tokens = contar(system)
        if tokens:
            ratios.append(len(system) / tokens)
    return sorted(ratios)


def texto_calibracion(ratios: list[float]) -> str:
    if not ratios:
        return "calibracion del tokenizador: sin systems persistidos"
    return (f"calibracion del tokenizador (chars/token sobre {len(ratios)} systems reales): "
            f"min {ratios[0]:.2f}, mediana {statistics.median(ratios):.2f}, max {ratios[-1]:.2f}")


# --- el smoke -------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-capturas", action="store_true")
    ap.add_argument("--fase", choices=("A", "B", "AB"), default="AB",
                    help="A: solo el Ollama real; B: solo el falso (barato: sin el 7b, "
                         "para reintentar sus capturas); AB: las dos (default)")
    args = ap.parse_args(argv)
    base.PUERTO = PUERTO
    base.BASE = f"http://127.0.0.1:{PUERTO}"
    base.WS = f"ws://127.0.0.1:{PUERTO}/ws/chat"
    if "A" in args.fase:
        base._ollama_listo()
    base._puerto_libre()
    _puerto_falso_libre()
    capturas = pathlib.Path(__file__).resolve().parent / "canarios_smoke_capturas"
    capturas.mkdir(exist_ok=True)
    resultados = {}
    telemetrias = []
    if "A" in args.fase:
        fase_a(args, capturas, resultados, telemetrias)
    if "B" in args.fase:
        fase_b(args, capturas, resultados, telemetrias)
    mirar(capturas, resultados, telemetrias)
    return 0


def fase_a(args, capturas, resultados, telemetrias) -> None:
    """Ollama real: invento, truncado, cabe, sano, cache, nube."""
    esperar_lugar("fase A (carga el 7b)")
    home_a = home_con(None)
    server = base.Server(home_a, "nueva")
    print(f"[fase A] server {base.BASE} home {home_a} ({server.codigo})", flush=True)
    try:
        server.esperar()
        resultados["invento"] = asyncio.run(turno(server.token, "/local hola, que libro te conte que empece?"))
        print(resumen_del_turno("invento", resultados["invento"]), flush=True)
        adj = adjunto_gordo(server.token)
        msg = "/local cual es la palabra clave? contesta solo la palabra clave"
        resultados["truncado"] = asyncio.run(turno(server.token, msg, [adj]))
        print(resumen_del_turno("truncado", resultados["truncado"]), flush=True)
        resultados["cabe"] = asyncio.run(turno(server.token, msg))
        print(resumen_del_turno("cabe", resultados["cabe"]), flush=True)
        resultados["sano"] = asyncio.run(turno(server.token, "/local explicame en dos lineas que es un websocket"))
        print(resumen_del_turno("sano", resultados["sano"]), flush=True)
        resultados["cache"] = asyncio.run(turno(server.token, "/local explicame en dos lineas que es un websocket"))
        print(resumen_del_turno("cache", resultados["cache"]), flush=True)
        if shutil.which("claude"):
            resultados["nube"] = asyncio.run(turno(server.token, "/nube /claude que hablamos con Marta del libro rosa?"))
            print(resumen_del_turno("nube", resultados["nube"]), flush=True)
        else:
            print("nube: no corrio (sin CLI de claude)", flush=True)
        # el 7b se va ANTES de las capturas: Chromium no lo necesita y la
        # regla de recursos pide lugar antes de abrirlo
        descargar_7b()
        if not args.sin_capturas:
            esperar_lugar("capturas de la fase A (Chromium)", LUGAR_CHROMIUM_MB)
            for nombre in ("invento", "truncado", "sano"):
                base._http("POST", f"/api/chats/{resultados[nombre]['chat']}/activate", {}, server.token)
                capturar(server.token, resultados[nombre]["chat"], capturas, nombre)
        telemetrias.append(home_a / "telemetry.jsonl")
    finally:
        server.apagar()
        descargar_7b()


def fase_b(args, capturas, resultados, telemetrias) -> None:
    """El Ollama falso: accion sin accion, degenerado."""
    falso = ollama_falso()
    home_b = home_con(f"http://127.0.0.1:{PUERTO_FALSO}/api/generate")
    server = base.Server(home_b, "nueva")
    print(f"[fase B] server {base.BASE} home {home_b} con Ollama falso en {PUERTO_FALSO}", flush=True)
    try:
        server.esperar()
        for nombre in ("accion", "degenerado"):
            OllamaFalso.guion = nombre
            resultados[nombre] = asyncio.run(turno(server.token, "/local en que quedamos la otra vez con el presupuesto?"))
            print(resumen_del_turno(nombre, resultados[nombre]), flush=True)
            if not args.sin_capturas:
                esperar_lugar(f"captura de {nombre} (Chromium)", LUGAR_CHROMIUM_MB)
                base._http("POST", f"/api/chats/{resultados[nombre]['chat']}/activate", {}, server.token)
                capturar(server.token, resultados[nombre]["chat"], capturas, nombre)
        telemetrias.append(home_b / "telemetry.jsonl")
    finally:
        server.apagar()
        falso.shutdown()
        falso.server_close()


def mirar(capturas, resultados, telemetrias) -> None:
    """Lo que hay que mirar al final: el control de cache y el centinela (si
    corrio la fase A), la calibracion sobre los systems persistidos y el
    resumen de canarios_resumen sobre las telemetrias que haya."""
    if "sano" in resultados and "cache" in resultados:
        print("\ncontrol de cache (prompt_eval_count de dos turnos iguales seguidos):",
              [(f.get("pasada"), f.get("evaluado")) for f in (resultados["sano"]["canario"] or {}).get("ventana") or []],
              [(f.get("pasada"), f.get("evaluado")) for f in (resultados["cache"]["canario"] or {}).get("ventana") or []])
    if "cabe" in resultados and "truncado" in resultados:
        print("el centinela del system sobrevive sin adjunto:", CENTINELA.lower() in resultados["cabe"]["texto"].lower(),
              "| con el adjunto gordo:", CENTINELA.lower() in resultados["truncado"]["texto"].lower(),
              "(esperado: True | False)")
    print(f"telemetria: {' y '.join(str(t) for t in telemetrias)}; capturas: {capturas}")
    if telemetrias:
        # el tokenizador real, con el cache bajo el home desechable de la
        # primera fase (CALIPSO_HOME exportado ANTES de importar calipso:
        # regla del repo)
        os.environ.setdefault("CALIPSO_HOME", str(telemetrias[0].parent))
        from calipso import tokenizador
        contar, origen = tokenizador.contador(base.MODELO)
        print(texto_calibracion(calibracion(telemetrias[0], contar)), f"[tokenizador={origen}]")
    print("resumen:")
    from experimentos import canarios_resumen as cr
    print(cr.texto(cr.resumir([f for t in telemetrias for f in cr.leer(t)])))


if __name__ == "__main__":
    sys.exit(main())
