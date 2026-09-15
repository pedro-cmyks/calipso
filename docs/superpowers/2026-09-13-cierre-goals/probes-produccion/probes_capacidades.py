"""Probe de capacidades del chat REAL (pedido de Pedro, 2026-09-15): un turno
por capacidad -- ruteo por defecto, /fast, /think, /ultrathink, /claude,
/codex, /local, /nube, /web (busqueda), /plan, imagen, PDF, descargar e
instalar una app, y un goal que instala torch en el venv del clon y lo
verifica. Anota por turno la ruta, el modelo, el tier, el tiempo, la web,
el canario y el texto."""
import asyncio, json, os, pathlib, re, subprocess, sys, time, urllib.request
import websockets

BASE = "http://127.0.0.1:8000"; WS = "ws://127.0.0.1:8000/ws/chat"
TOKEN = pathlib.Path.home().joinpath(".calipso/token").read_text().strip()
HOME = pathlib.Path.home() / ".calipso"
FILAS = []

def http(metodo, ruta, cuerpo=None, timeout=60):
    req = urllib.request.Request(f"{BASE}{ruta}", data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"Cookie": f"calipso_token={TOKEN}", "Content-Type": "application/json"}, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b"{}")
        except Exception: return e.code, {}

async def _turno(mensaje, cid, plazo=420):
    texto, error, meta, web, extra = [], None, {}, {}, {}
    t0 = time.monotonic()
    async with websockets.connect(WS, additional_headers={"Cookie": f"calipso_token={TOKEN}"}, max_size=None) as ws:
        await ws.send(json.dumps({"text": mensaje, "chat_id": cid}))
        while True:
            try: raw = await asyncio.wait_for(ws.recv(), timeout=plazo)
            except asyncio.TimeoutError: error = f"sin done en {plazo}s"; break
            try: pkt = json.loads(raw)
            except Exception: continue
            t = pkt.get("type", "")
            if t == "chunk": texto.append(pkt.get("text", ""))
            elif t == "error": error = pkt.get("text")
            elif t == "meta": meta = {k: pkt.get(k) for k in ("route", "used", "model", "tier", "effort", "client", "why")}
            elif t == "web" and pkt.get("action") == "results": web = {"results": len(pkt.get("results") or []), "pages": [p.get("url") for p in (pkt.get("pages") or [])][:3]}
            elif t in ("canario", "carga", "cost", "privacidad", "plan", "agent", "goal"): extra.setdefault(t, []).append({k: v for k, v in pkt.items() if k != "type"})
            elif t == "done": break
    return {"texto": "".join(texto), "error": error, "meta": meta, "web": web, "extra": extra, "s": round(time.monotonic() - t0, 1)}

def turno(nombre, mensaje, cid, plazo=420):
    r = asyncio.run(_turno(mensaje, cid, plazo))
    m = r["meta"]; ex = r["extra"]
    can = [c.get("marcas") or c.get("veredicto") or c for c in ex.get("canario", [])][:1]
    fila = {"probe": nombre, "ruta": m.get("used") or m.get("route"), "modelo": m.get("model"), "tier": m.get("tier"), "effort": m.get("effort"),
            "s": r["s"], "web": r["web"] or None, "carga": [c.get("nivel") or c for c in ex.get("carga", [])][:1] or None,
            "canario": can or None, "plan": bool(ex.get("plan")), "error": r["error"], "texto": r["texto"].strip()}
    FILAS.append(fila)
    print(f"\n### {nombre}  [{fila['ruta']} {fila['modelo']} tier={fila['tier']} effort={fila['effort']} {fila['s']}s]" + (f" web={fila['web']}" if fila['web'] else "") + (f" carga={fila['carga']}" if fila['carga'] else "") + (f" ERROR={fila['error']}" if fila['error'] else ""), flush=True)
    print("   " + fila["texto"][:700].replace("\n", "\n   "), flush=True)
    return r

s, c = http("POST", "/api/chats", {"title": "probe capacidades"}); cid = c["id"]; http("POST", f"/api/chats/{cid}/activate", {})
s, cg = http("GET", "/api/carga"); print("carga al arrancar:", (cg.get("medicion") or cg).get("nivel"), (cg.get("medicion") or cg).get("mem_disponible_mb"), "MB")

turno("1 default", "hola Calipso, en una linea: que sabes hacer hoy?", cid)
turno("2 /fast", "/fast cuanto es 17 por 23? solo el numero", cid)
turno("3 /think", "/think explica en tres lineas por que el cielo es azul", cid)
turno("4 /ultrathink", "/ultrathink en dos lineas: que es un goal en Calipso y que lo frena?", cid)
turno("5 /claude", "/claude en una linea: que modelo sos y por que ruta llegaste? responde con lo que dice tu contexto", cid)
turno("6 /codex", "/codex en una linea: que modelo sos y por que ruta llegaste? responde con lo que dice tu contexto", cid)
turno("7 /local", "/local que hora es en Bogota ahora mismo? si no lo sabes decilo", cid)
turno("8 /web", "/web cual es la ultima version estable de Python y en que fecha salio? cita la fuente", cid)
turno("9 imagen", "genera una imagen de un ave azul posada en una rama", cid)
turno("10 pdf", "hazme un PDF de una pagina con un resumen de que es Calipso y dejalo en mi carpeta de Descargas", cid)
turno("11 instalar app", "descarga e instala en mi computador una aplicacion para editar audio que sirva para trabajar", cid)
turno("12 /plan", "/plan disena en tres pasos como agregarle un test a un repo python que no tiene ninguno", cid)
turno("13 /nube", "/nube en una linea: que es un sandbox de procesos?", cid)
turno("14 /goal estado", "/goal estado", cid)

# el goal con torch: instalar en el venv del clon (instalar_en_goal, directo) y verificar
repo = pathlib.Path("/tmp/probe-torch"); subprocess.run(["rm", "-rf", str(repo)]); repo.mkdir()
subprocess.run(["git", "init", "-q", str(repo)], check=True); (repo / "README.md").write_text("# torch probe\n")
subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
subprocess.run(["git", "-C", str(repo), "-c", "user.name=probe", "-c", "user.email=probe@x", "commit", "-qm", "init"], check=True)
r = turno("15 /goal torch", f"/goal /claude crea un venv en el repo, instala torch (la version cpu alcanza) y un script verifica.py que importe torch e imprima torch.__version__ y el resultado de multiplicar dos tensores 2x2 en: {repo} hasta: python verifica.py tope: 4 golpes 15m con: claude", cid, plazo=300)
m = re.search(r"goal (\S+) \(proposed\)", r["texto"] or ""); gid = m.group(1) if m else None
if gid:
    turno("16 /goal dale", "/goal dale", cid)
    lim = time.monotonic() + 1500; visto = -1
    while time.monotonic() < lim:
        s, e = http("GET", f"/api/goals/{gid}/estado"); g = e["goal"]; n = len(e.get("golpes") or [])
        if n != visto:
            visto = n; u = (e.get("golpes") or [{}])[-1] if n else {}
            print(f"    {gid}: {g['status']} - {n} golpes - ultimo {u.get('fase')} {(u.get('veredicto_del_golpe') or {}).get('estado','')} {u.get('duracion_ms','')}ms", flush=True)
        if g["status"] in ("waiting", "failed", "complete", "cancelled"): break
        time.sleep(10)
    esp = g.get("espera") or {}
    print(f"\n### 17 goal torch termino: {g['status']} {esp.get('motivo')} | pregunta: {str(esp.get('pregunta') or '')[:300]} | consumo: {e.get('consumo')}", flush=True)
    for f in e.get("golpes") or []:
        if f.get("fase") == "fin" or f.get("juez"):
            print(f"   golpe {f.get('n')} {f.get('manos')} exit={f.get('exit')} {f.get('duracion_ms')}ms u={f.get('unidades')} usd={f.get('costo_usd')} veredicto={json.dumps((f.get('veredicto_del_golpe') or {}).get('resumen'), ensure_ascii=False)[:250]} juez={json.dumps(f.get('juez'), ensure_ascii=False)[:250]}", flush=True)
            for c_ in (f.get("comandos") or [])[:14]: print("     $", str(c_.get("cmd"))[:100], "->", str(c_.get("resultado_tail"))[-80:].replace("\n", " "), flush=True)
    hk = HOME / "goals" / gid / "hook.jsonl"
    if hk.exists():
        d = [json.loads(l) for l in hk.read_text().splitlines()]
        print("   hook denies:", [h.get("resumen") for h in d if h.get("decision") == "deny"][:6], flush=True)
    turno("18 /goal estado", "/goal estado", cid)
    if g["status"] == "waiting" and esp.get("motivo") == "cumplido":
        turno("19 /goal dale final", "/goal dale", cid)
        print("   verifica.py en la rama:", subprocess.run(["git", "-C", str(repo), "show", f"goal/{gid}:verifica.py"], capture_output=True, text=True).stdout[:300], flush=True)
    else:
        http("POST", f"/api/goals/{gid}/no", {})
s, cg = http("GET", "/api/carga"); print("\ncarga al final:", (cg.get("medicion") or cg).get("nivel"), (cg.get("medicion") or cg).get("mem_disponible_mb"), "MB")
print("\nchat:", cid)
json.dump(FILAS, open(os.path.expanduser("~/.calipso/logs/probe-capacidades.json"), "w"), ensure_ascii=False, indent=1)
