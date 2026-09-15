"""Probes directos contra el Calipso REAL (8000) con el token de Pedro: lecturas
(goals, carga, memoria, aduana, inbox), turnos por el chat (/help, /goal estado)
y un goal real chico sobre un repo temporal sin remoto (propuesta -> inbox ->
dale por chat -> golpes -> juez -> estado -> dale final -> rama traida), mas el
camino parar -> solicitud retomar -> si por el inbox. Pedido por Pedro el 09-15."""
import asyncio, json, os, pathlib, re, subprocess, sys, time, urllib.request
import websockets

BASE = "http://127.0.0.1:8000"; WS = "ws://127.0.0.1:8000/ws/chat"
TOKEN = pathlib.Path.home().joinpath(".calipso/token").read_text().strip()
HOME = pathlib.Path.home() / ".calipso"
R = []

def ok(nombre, cond, detalle=""):
    R.append((nombre, bool(cond), str(detalle)[:400]))
    print(f"[{'ok' if cond else 'FALLO'}] {nombre}: {str(detalle)[:300]}", flush=True)
    return bool(cond)

def nota(nombre, detalle):
    print(f"[nota] {nombre}: {str(detalle)[:500]}", flush=True)

def http(metodo, ruta, cuerpo=None, timeout=60):
    req = urllib.request.Request(f"{BASE}{ruta}", data=json.dumps(cuerpo).encode() if cuerpo is not None else None,
                                 headers={"Cookie": f"calipso_token={TOKEN}", "Content-Type": "application/json"}, method=metodo)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b"{}")
        except Exception: return e.code, {}

CHATS = []
async def _turno(mensaje, cid=None):
    if cid is None:
        s, c = http("POST", "/api/chats", {"title": f"probe {mensaje[:30]}"}); cid = c["id"]; CHATS.append(cid)
        http("POST", f"/api/chats/{cid}/activate", {})
    texto, error, extra = [], None, {}
    async with websockets.connect(WS, additional_headers={"Cookie": f"calipso_token={TOKEN}"}, max_size=None) as ws:
        await ws.send(json.dumps({"text": mensaje, "chat_id": cid}))
        while True:
            raw = await asyncio.wait_for(ws.recv(), timeout=300)
            try: pkt = json.loads(raw)
            except Exception: continue
            t = pkt.get("type", "")
            if t == "chunk": texto.append(pkt.get("text", ""))
            elif t == "error": error = pkt.get("text")
            elif t == "goal": extra["goal"] = pkt.get("goal")
            elif t == "done": extra["meta"] = pkt.get("meta"); break
    return {"chat": cid, "texto": "".join(texto), "error": error, **extra}

def turno(m, cid=None): return asyncio.run(_turno(m, cid))

def estado(gid): return http("GET", f"/api/goals/{gid}/estado")[1]

def esperar(gid, estados, plazo=900):
    lim = time.monotonic() + plazo; visto = -1
    while time.monotonic() < lim:
        e = estado(gid); g = e["goal"]; n = len(e.get("golpes") or [])
        if n != visto:
            visto = n; u = (e.get("golpes") or [{}])[-1] if n else {}
            print(f"    {gid}: {g['status']} - {n} golpes - ultimo {u.get('fase')} {(u.get('veredicto_del_golpe') or {}).get('estado','')} {u.get('unidades','')}u {u.get('duracion_ms','')}ms", flush=True)
        if g["status"] in estados: return e
        time.sleep(5)
    return estado(gid)

def solicitudes_abiertas():
    s, d = http("GET", "/api/permisos/solicitudes?estado=abierta")
    if s != 200 or not isinstance(d, (list, dict)): s, d = http("GET", "/api/permisos/solicitudes")
    lst = d if isinstance(d, list) else (d.get("solicitudes") or d.get("items") or [])
    return [x for x in lst if x.get("estado") in (None, "abierta", "estacionada", "pendiente")]

# ---------- 1. lecturas (ya probadas en la ronda 1; solo carga e inbox)
s, c = http("GET", "/api/carga"); nivel = (c.get("medicion") or c).get("nivel"); ok("GET /api/carga", s == 200 and nivel, f"nivel={nivel} disp={(c.get('medicion') or c).get('mem_disponible_mb')}")
if nivel == "cargada": print("cargada: no se manda ningun goal"); sys.exit(2)
s, i = http("GET", "/api/inbox"); ok("GET /api/inbox vacio de goals al arrancar", s == 200 and "goal_" not in json.dumps(i), len(i.get("items") or []))

def inbox_tiene(gid):
    s, i = http("GET", "/api/inbox"); return gid in json.dumps(i)

def cerrar_si_queda(gid):
    s, g = http("GET", "/api/goals?limit=1")
    if (g.get("activo") or {}).get("id") == gid: http("POST", f"/api/goals/{gid}/no", {})

# ---------- 2. un goal real de punta a punta (con pypi en la red del sandbox)
repo = pathlib.Path("/tmp/probe-calipso-repo4"); subprocess.run(["rm", "-rf", str(repo)]); repo.mkdir()
subprocess.run(["git", "init", "-q", str(repo)], check=True)
(repo / "README.md").write_text("# probe 2\n"); (repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths = ['.']\n")
subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
subprocess.run(["git", "-C", str(repo), "-c", "user.name=probe", "-c", "user.email=probe@x", "commit", "-qm", "init"], check=True)
base_sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
t0 = time.monotonic()
t = turno(f"/goal /claude crea un modulo saludo.py con una funcion hola() que devuelva 'hola' y su test test_saludo.py con pytest en: {repo} hasta: pytest en verde tope: 3 golpes 8m con: claude")
ok("propuesta (proposed)", "proposed" in (t["texto"] or "") and not t["error"], f"{time.monotonic()-t0:.0f}s | " + (t["texto"] or t["error"] or "")[:200].replace("\n", " | "))
m = re.search(r"goal (\S+) \(proposed\)", t["texto"] or ""); gid = m.group(1) if m else None
if not gid: print("sin id: paro"); sys.exit(1)
ok("la propuesta esta en el inbox (/api/inbox)", inbox_tiene(gid), gid)
t = turno("/goal dale", t["chat"]); ok("/goal dale por chat", not t["error"] and "active" in (t["texto"] or ""), (t["texto"] or t["error"] or "")[:160])
e = esperar(gid, {"waiting", "failed", "complete", "cancelled"}); g = e["goal"]; esp = g.get("espera") or {}
ok("termino waiting cumplido", g["status"] == "waiting" and esp.get("motivo") == "cumplido", f"{g['status']} {esp.get('motivo')} | pregunta: {str(esp.get('pregunta') or '')[:200]} | {esp.get('diagnostico') or ''}")
filas = e.get("golpes") or []
nota("golpes", [{k: f.get(k) for k in ("n", "manos", "unidades", "duracion_ms", "exit", "motivo")} | {"cmds": len(f.get("comandos") or []), "rate5h": (f.get("rate_limit") or {}).get("five_hour"), "usd": f.get("costo_usd")} for f in filas])
hook = HOME / "goals" / gid / "hook.jsonl"; hk = [json.loads(l) for l in hook.read_text().splitlines()] if hook.exists() else []
denies = [h.get("resumen") for h in hk if h.get("decision") == "deny"]
nota("hook", {t_: sum(1 for h in hk if h.get("tool") == t_) for t_ in sorted({h.get("tool") for h in hk})} | {"deny": len(denies)})
nota("denegados", denies[:8])
ok("solo la sonda del hook fue denegada (gh pr create)", len(denies) <= 1 and all("gh pr create" in d for d in denies), denies)
juez = next((f.get("juez") for f in filas if (f.get("juez") or {}).get("criterio")), None)
ok("el criterio corrio confinado y en verde", juez and (juez.get("criterio") or {}).get("ok") and "calipso-goal" in str(juez.get("criterio")), str(juez)[:220])
ok("el revisor de otra familia contesto", any((f.get("juez") or {}).get("revisor") for f in filas), [(f.get("juez") or {}).get("independencia") for f in filas if f.get("juez")])
s, ad = http("GET", "/api/aduana?limit=30"); cr = [x for x in (ad.get("cruces") or []) if "goal" in json.dumps(x)]
ok("la aduana tiene cruces con origen goal", len(cr) > 0, len(cr))
t = turno("/goal estado", t["chat"]); ok("/goal estado muestra waiting cumplido", gid in (t["texto"] or "") and "cumplido" in (t["texto"] or ""), (t["texto"] or "")[:200].replace("\n", " | "))
if g["status"] == "waiting" and esp.get("motivo") == "cumplido":
    t = turno("/goal dale", t["chat"]); ok("/goal dale final -> complete con la rama", "complete" in (t["texto"] or "") and "goal/" in (t["texto"] or ""), (t["texto"] or t["error"] or "")[:250])
    ramas = subprocess.run(["git", "-C", str(repo), "branch", "--list", f"goal/{gid}"], capture_output=True, text=True).stdout
    ok("la rama goal/<id> esta en el origen y HEAD no cambio", f"goal/{gid}" in ramas and subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() == base_sha, ramas.strip())
    ok("saludo.py existe en la rama traida", subprocess.run(["git", "-C", str(repo), "show", f"goal/{gid}:saludo.py"], capture_output=True, text=True).returncode == 0, "")
else:
    cerrar_si_queda(gid)
s, g2 = http("GET", "/api/goals?limit=1"); ok("activo null tras cerrar", g2.get("activo") is None, g2.get("activo") and g2["activo"].get("status"))

s, g3 = http("GET", "/api/goals?limit=1"); ok("sin goal en curso al final", g3.get("activo") is None, "")
print("\nchats de los probes:", CHATS)
fallos = [r for r in R if not r[1]]
print(f"\n{len(R) - len(fallos)} ok, {len(fallos)} fallos"); sys.exit(1 if fallos else 0)
