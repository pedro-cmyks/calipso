"""Medicion del porton con VARIANTES del system de produccion (h05, opcion a).

Pedro eligio el 2026-09-10 "podar el system de produccion y re-medir el
porton SOBRE ese system" (spec del abismo, seccion 12). La medicion por
posicion (`consulta_abismo_posicion.py`) mostro que la letra del contrato
pasa sola y no dentro del system real en ninguna posicion: lo que compite
es el resto del system (la Constitucion cortada a 3000 chars y las doce
instrucciones del contrato interno), no el lugar del bloque.

Variantes (la letra del bloque del abismo es byte-identica en todas):
  actual          -- como HEAD (control; se reusa el cache de la posicion)
  banco           -- control del banco (identidad minima + contrato)
  sin-constitucion-- el system actual sin la seccion "Constitucion de Calipso"
  identidad-corta -- sin Constitucion y con "Sistema" = IDENTIDAD (destilada de
                     CALIPSO.md, ~550 chars); el contrato interno intacto
  podada          -- identidad-corta + contrato interno podado a lo que el
                     modelo local usa (idioma, tono, sin razonamiento visible,
                     confirmacion, foco, abismo)
  podada-final    -- podada con el bloque del abismo como ultimo texto

METRICA CORREGIDA (hallazgo lateral de la posicion): una marca que copia el
molde del contrato textual ("memoria pregunta", "proyecto nombre", "chats
palabras, opcional desde:AAAA-MM ...") es legible para `marca.parsear` pero
no es una consulta: cuenta aparte como "literal" y NO suma a "utiles". Las
compuertas del porton se evaluan sobre utiles.

Protocolo del banco: temp 0, /api/generate, un prompt, sin historial,
num_ctx 8192 (produccion). Uso:
  .venv/bin/python experimentos/consulta_abismo_system.py <home> <N> <variantes,coma> <salida.jsonl>
SEMILLA=<jsonl> copia al arrancar las filas de variantes ya medidas con el
mismo protocolo (la posicion: actual y banco). El JSONL es reanudable.
"""
import json
import os
import pathlib
import statistics
import sys
import time
import urllib.request

HOME, N, VARIANTES, SALIDA = sys.argv[1], int(sys.argv[2]), sys.argv[3].split(","), pathlib.Path(sys.argv[4])
os.environ["CALIPSO_HOME"] = HOME      # ANTES de importar calipso: jamas el home real
os.environ.setdefault("CALIPSO_TOKEN", "medicion-local-xxxxxxxxxxxxxxxxxxxxxxxx")
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import calipso.server as srv  # noqa: E402
from calipso import catastro, prompt_compiler as pc  # noqa: E402
from calipso.abismo import contrato, marca  # noqa: E402
import dispatch  # noqa: E402

FEATS = {"type": "chat", "complexity": 1, "needs_repo": False, "needs_web": False, "private": False}
RUNTIME = "Ruta usada: local. Modelo: qwen2.5:7b. Persona: Platon."

# La identidad corta: lo que CALIPSO.md dice de QUIEN es Calipso, escrito
# para el modelo y no para un humano. Candidata a reemplazar SYSTEM +
# Constitucion. Si gana, aterriza byte-identica.
IDENTIDAD = (
    "Eres Calipso, el asistente personal local de Pedro. Pedro habla siempre "
    "con Calipso: Claude, Codex, las APIs y los modelos locales son "
    "herramientas internas tuyas, nunca tu identidad. No digas que eres "
    "Alibaba, OpenAI, Anthropic, Claude, Codex ni Ollama. Si Pedro pregunta "
    "que modelo o ruta usas, responde solo con el estado real que recibes en "
    "el contexto. Eres honesto sobre tu estado: si no sabes algo, una "
    "conexion no esta configurada o un dato te falta, lo dices sin inventar. "
    "Prefieres entregar menos, pero real, antes que un relleno bonito."
)

# El contrato interno podado: candidato a reemplazar `internal_contract`.
# Se van las instrucciones que compiten con la marca (traducir el pedido a
# una tarea, memoria probabilistica, actuar antes de describir, roadblock,
# separar implementado/verificado, tipo de tarea, repo/web requeridos).
def contrato_podado(base, con_abismo=True):
    lineas = [
        "=== Lenguaje interno de Calipso ===",
        "Si un dato del perfil de Pedro esta desactualizado o contradicho por Pedro, prioriza lo nuevo.",
        pc._linea_foco(pc.departamentos_conocidos(base)),
        "Detecta el idioma de cada turno y responde SIEMPRE en ese mismo idioma, aunque el resto del sistema este en español. Si el mensaje mezcla idiomas en la misma oracion, usa el idioma dominante.",
        "Tono: directo, natural, cercano. Como un colega de confianza que conoce bien a Pedro. "
        "Para chat conversacional: sin headers, sin listas innecesarias, sin frases de apertura como 'Claro,' o 'Por supuesto,'. "
        "Para tareas tecnicas: conciso, especifico, con evidencia cuando aplique.",
        "No muestres razonamiento interno; muestra decisiones, evidencia y pendientes cuando importen.",
        "Pide confirmacion antes de escribir, gastar, publicar, borrar o promover memoria sensible.",
    ]
    if con_abismo:
        lineas.append(contrato.bloque_contrato(catastro.nombres()))
    return "\n".join(lineas)


def _armar(system, identity, contrato_interno=None, cola=""):
    """El system de produccion pieza por pieza (lo mismo que _build_context
    para el mensaje 'hola'), con el contrato interno reemplazable."""
    core = srv.mem.load_core()
    # el recall y la meta activa entran como en produccion (con la basura
    # que el home real traiga: es lo que el 7b ve en cada turno)
    recalled = [r for r in srv.mem.recall("hola", n=8)
                if r["score"] >= srv.RECALL_MIN_SCORE][:srv.RECALL_MAX]
    economia = pc.economia_brief(srv._ECO_BASE)
    proyectos = pc.proyectos_brief(srv.ROOT)
    secciones = pc.context_sections(
        system, identity=identity, core=core, recalled=recalled,
        goal_block=srv._goal_context(), runtime=RUNTIME,
        economia=economia, proyectos=proyectos, features=FEATS,
        core_limit=srv.CONTEXT_CORE_MAX, base=srv._ECO_BASE)
    if contrato_interno is not None:
        secciones = [(t, contrato_interno if t == "Contrato interno" else b) for t, b in secciones]
    return pc.render_context(secciones) + cola


bloque = contrato.bloque_contrato(catastro.nombres())
# Ronda 2 (ABISMO_CONTRATO_FILE): una letra alternativa del bloque, con
# {repos} reemplazado por la misma cola de repos del bloque vivo. Se mide
# dentro de la variante de system que gano la ronda 1.
_CONTRATO_FILE = os.environ.get("ABISMO_CONTRATO_FILE", "")
if _CONTRATO_FILE:
    _repos = bloque.split(f"{marca.ABRE}abismo:proyecto nombre{marca.CIERRA} -- ", 1)[1].split("\n", 1)[0]
    bloque_alt = pathlib.Path(_CONTRATO_FILE).read_text(encoding="utf-8").strip().replace("{repos}", _repos)
else:
    bloque_alt = bloque
system_actual = srv._build_context("hola", RUNTIME, FEATS)
assert system_actual == _armar(srv.SYSTEM, srv._identity_doc()), "el armado no reproduce el system real"
SISTEMAS = {
    "actual": system_actual,
    "banco": "\n".join(["Sos Calipso, el asistente personal de Pedro. Respondele en su idioma,",
                        "directo y natural.",
                        contrato.bloque_contrato(("calipso", "atlas", "calipso-lector"))]),
    "sin-constitucion": _armar(srv.SYSTEM, ""),
    "identidad-corta": _armar(IDENTIDAD, ""),
    "podada": _armar(IDENTIDAD, "", contrato_podado(srv._ECO_BASE)),
    "podada-final": _armar(IDENTIDAD, "", contrato_podado(srv._ECO_BASE, con_abismo=False),
                           cola="\n\n" + bloque),
}
if _CONTRATO_FILE:
    SISTEMAS = {v: s.replace(bloque, bloque_alt) for v, s in SISTEMAS.items()}
    for v in VARIANTES:
        assert bloque_alt in SISTEMAS[v], f"{v}: la letra alternativa no entro"
for v in VARIANTES:
    assert "=== El abismo ===" in SISTEMAS[v], f"{v}: el bloque del abismo no esta"
    (ROOT / "experimentos" / "variantes" / f"system-{v}.txt").write_text(SISTEMAS[v], encoding="utf-8")

# el banco lo importo DESPUES de armar los systems: al importarse cambia CALIPSO_HOME
sys.path.insert(0, str(ROOT / "experimentos"))
import consulta_abismo as banco_mod  # noqa: E402
BANCO = banco_mod.BANCO
URL = dispatch.CONFIG["local"]["base_url"]
MODELO = dispatch.CONFIG["local"]["model"]
NUM_CTX = 8192

# --- la metrica corregida: copia literal del molde ----------------------------
# Los comodines del molde: "memoria pregunta", "chats palabras, opcional
# desde:AAAA-MM hasta:AAAA-MM", "proyecto nombre". Una marca cuya consulta
# EMPIEZA por el comodin (aunque le cuelgue fechas o una coma) no pide
# nada: en produccion pescaria por la palabra "pregunta" o "palabras".
# Se derivan del contrato medido: las marcas que el propio bloque contiene.
# Una respuesta cuya consulta repite una de esas entera, empieza por un
# comodin del contrato vivo, o deja un <comodin> sin llenar, es copia.
_MARCAS_DEL_MOLDE = [m for m in marca.encontrar(bloque_alt) if m]
COMODINES = {"pregunta", "palabras", "nombre"}   # los del contrato vivo
RESTOS_DEL_MOLDE = {" ".join(m.resto.lower().split()) for m in _MARCAS_DEL_MOLDE}


def es_literal(m: marca.Marca | None) -> bool:
    """La marca copia el molde del contrato en vez de consultar algo."""
    if m is None:
        return False
    resto = " ".join(m.resto.lower().split())
    palabras = resto.replace(",", " ").split()
    return (not palabras or palabras[0] in COMODINES or resto in RESTOS_DEL_MOLDE
            or "aaaa-mm" in resto or "<" in resto or ">" in resto)


def preguntar(sistema, mensaje):
    payload = {"model": MODELO, "system": sistema, "prompt": mensaje, "stream": False,
               "options": {"temperature": 0, "num_ctx": NUM_CTX}}
    t0 = time.monotonic()
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=1800) as resp:
        data = json.loads(resp.read().decode())
    return data.get("response", ""), int((time.monotonic() - t0) * 1000)


def _fila(v, item, corrida, salida, ms):
    marcas = marca.encontrar(salida)
    return {"variante": v, "item": item["id"], "tipo": item["tipo"],
            "fuente": item.get("fuente"), "corrida": corrida, "ms": ms,
            "marcas": [(m.fuente if m else None) for m in marcas],
            "literales": [es_literal(m) for m in marcas],
            "salida": salida[:400]}


hechos = set()
if SALIDA.exists():
    for linea in SALIDA.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            f = json.loads(linea)
            hechos.add((f["variante"], f["item"], f["corrida"]))
semilla = os.environ.get("SEMILLA")
if semilla:
    por_id = {i["id"]: i for i in BANCO}
    with SALIDA.open("a", encoding="utf-8") as out:
        for linea in pathlib.Path(semilla).read_text(encoding="utf-8").splitlines():
            if not linea.strip():
                continue
            f = json.loads(linea)
            clave = (f["variante"], f["item"], f["corrida"])
            if f["variante"] in VARIANTES and clave not in hechos and f["item"] in por_id:
                # la salida en la semilla esta recortada a 400: las marcas se
                # recalculan sobre eso (las marcas salen al principio)
                out.write(json.dumps(_fila(f["variante"], por_id[f["item"]], f["corrida"],
                                           f["salida"], f["ms"]), ensure_ascii=False) + "\n")
                hechos.add(clave)

print(f"modelo {MODELO} url {URL} num_ctx {NUM_CTX} N={N}", flush=True)
for v in VARIANTES:
    print(f"variante {v}: system {len(SISTEMAS[v])} chars, bloque en offset {SISTEMAS[v].find('=== El abismo ===')}", flush=True)

with SALIDA.open("a", encoding="utf-8") as out:
    for v in VARIANTES:
        for item in BANCO:
            for corrida in range(N):
                if (v, item["id"], corrida) in hechos:
                    continue
                salida, ms = preguntar(SISTEMAS[v], item["mensaje"])
                fila = _fila(v, item, corrida, salida, ms)
                out.write(json.dumps(fila, ensure_ascii=False) + "\n")
                out.flush()
                print(f"  {v} {item['id']} #{corrida}: {fila['marcas']} lit={fila['literales']} ({ms} ms)", flush=True)

# resumen con las compuertas del porton, sobre marcas UTILES (legibles no literales)
filas = [json.loads(l) for l in SALIDA.read_text(encoding="utf-8").splitlines() if l.strip()]


def utiles(f):
    return [m for m, lit in zip(f["marcas"], f["literales"]) if m and not lit]


lineas = ["# Variantes del system de produccion -- porton sobre marcas utiles", "",
          "| variante | chars | memoria | chats | proyecto | espurias | ruteo | literales | latencia med. |",
          "|---|---|---|---|---|---|---|---|---|"]
detalle = []
for v in VARIANTES:
    fv = [f for f in filas if f["variante"] == v if f["corrida"] < N]
    celdas = []
    tot_leg = tot_rut = 0
    for fuente in ("memoria", "chats", "proyecto"):
        pos = [f for f in fv if f["tipo"] == "positivo" and f["fuente"] == fuente]
        leg = [f for f in pos if utiles(f)]
        rut = [f for f in leg if utiles(f)[0] == fuente]
        tot_leg += len(leg); tot_rut += len(rut)
        tasa = len(leg) / len(pos) if pos else 0
        celdas.append(f"{len(leg)}/{len(pos)} ({tasa:.0%}) {'PASA' if tasa >= 5 / 6 else 'NO'}")
    neg = [f for f in fv if f["tipo"] == "negativo"]
    esp = [f for f in neg if f["marcas"]]
    tasa_esp = len(esp) / len(neg) if neg else 0
    lit = sum(sum(f["literales"]) for f in fv)
    todas = sum(len(f["marcas"]) for f in fv)
    rut_txt = f"{tot_rut}/{tot_leg}" + (f" ({tot_rut / tot_leg:.0%})" if tot_leg else "")
    med = f"{statistics.median(f['ms'] for f in fv):.0f} ms" if fv else "-"
    lineas.append(f"| {v} | {len(SISTEMAS[v])} | {' | '.join(celdas)} | {len(esp)}/{len(neg)} ({tasa_esp:.0%}) "
                  f"{'PASA' if tasa_esp <= 1 / 6 else 'NO'} | {rut_txt} | {lit}/{todas} | {med} |")
    detalle.append(f"\n## {v} por item (corridas con marca util / {N})\n")
    for item in BANCO:
        fi = [f for f in fv if f["item"] == item["id"]]
        detalle.append(f"- {item['id']}: {sum(1 for f in fi if utiles(f))}/{len(fi)}")
lineas.append("")
lineas.append("Piso: >= 5/6 por fuente sobre marcas utiles; espurias <= 1/6 (cualquier marca, literal incluida); ruteo >= 90%.")
resumen = "\n".join(lineas) + "\n" + "\n".join(detalle) + "\n"
SALIDA.with_suffix(".md").write_text(resumen, encoding="utf-8")
print(resumen, flush=True)
