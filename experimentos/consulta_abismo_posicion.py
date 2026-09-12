"""Medicion del porton con el system de PRODUCCION (h05 del cierre del 1b).

Variantes de POSICION del bloque del contrato (letra byte-identica) dentro
del system local REAL (`_build_context` sobre una copia del home del smoke):
  actual  -- como HEAD: dentro de "Contrato interno" (4a de 10 secciones)
  final   -- el bloque como ultimo texto del system (donde lo midio el banco)
  primero -- el bloque antes de todo
  banco   -- control: el system del banco (identidad minima + contrato)
Protocolo del banco: temp 0, /api/generate, un solo prompt, sin historial.
num_ctx 8192 (el de produccion). Uso:
  .venv/bin/python experimentos/consulta_abismo_posicion.py <home> <N> <variantes,coma> <salida.jsonl>

El home es una COPIA (solo lectura del real) con catastro.json, core y chats
sembrados: `_build_context` corre de verdad (recall, economia, catastro).
El JSONL es reanudable: las (variante, item, corrida) ya hechas se saltean.
Corrida del 2026-09-08 (cierre del 1b, hallazgo h05):
consulta_abismo_posicion_produccion.{jsonl,md}.
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
from calipso import catastro  # noqa: E402
from calipso.abismo import contrato, marca  # noqa: E402
import dispatch  # noqa: E402

FEATS = {"type": "chat", "complexity": 1, "needs_repo": False, "needs_web": False, "private": False}
RUNTIME = "Ruta usada: local. Modelo: qwen2.5:7b. Persona: Platon."
system_actual = srv.prompt_compiler.render_context(srv._build_context("hola", RUNTIME, FEATS))
bloque = contrato.bloque_contrato(catastro.nombres())
assert bloque in system_actual, "el bloque no esta en el system real"
sin_bloque = system_actual.replace("\n" + bloque, "", 1)
assert bloque not in sin_bloque
SISTEMAS = {
    "actual": system_actual,
    "final": sin_bloque + "\n\n" + bloque,
    "primero": bloque + "\n\n" + sin_bloque,
    "banco": "\n".join(["Sos Calipso, el asistente personal de Pedro. Respondele en su idioma,",
                        "directo y natural.",
                        contrato.bloque_contrato(("calipso", "atlas", "calipso-lector"))]),
}
# el banco lo importo DESPUES de armar los systems: al importarse cambia CALIPSO_HOME
sys.path.insert(0, str(ROOT / "experimentos"))
import consulta_abismo as banco_mod  # noqa: E402
BANCO = banco_mod.BANCO
URL = dispatch.CONFIG["local"]["base_url"]
MODELO = dispatch.CONFIG["local"]["model"]
NUM_CTX = 8192


def preguntar(sistema, mensaje):
    payload = {"model": MODELO, "system": sistema, "prompt": mensaje, "stream": False,
               "options": {"temperature": 0, "num_ctx": NUM_CTX}}
    t0 = time.monotonic()
    # timeout largo: el 7b corre en CPU en la Ally y cualquier carga en
    # paralelo (la suite de tests) lo frena mas alla de los 120 s de dispatch
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=1800) as resp:
        data = json.loads(resp.read().decode())
    return data.get("response", ""), int((time.monotonic() - t0) * 1000)


hechos = set()
if SALIDA.exists():
    for linea in SALIDA.read_text(encoding="utf-8").splitlines():
        if linea.strip():
            f = json.loads(linea)
            hechos.add((f["variante"], f["item"], f["corrida"]))

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
                marcas = marca.encontrar(salida)
                fila = {"variante": v, "item": item["id"], "tipo": item["tipo"],
                        "fuente": item.get("fuente"), "corrida": corrida, "ms": ms,
                        "marcas": [(m.fuente if m else None) for m in marcas],
                        "salida": salida[:400]}
                out.write(json.dumps(fila, ensure_ascii=False) + "\n")
                out.flush()
                print(f"  {v} {item['id']} #{corrida}: {fila['marcas']} ({ms} ms)", flush=True)

# resumen con las compuertas del porton
filas = [json.loads(l) for l in SALIDA.read_text(encoding="utf-8").splitlines() if l.strip()]
lineas = ["# Medicion de posicion del contrato con el system de produccion", ""]
for v in VARIANTES:
    fv = [f for f in filas if f["variante"] == v]
    lineas.append(f"## {v} (system {len(SISTEMAS[v])} chars, {len(fv)} llamadas)")
    for fuente in ("memoria", "chats", "proyecto"):
        pos = [f for f in fv if f["tipo"] == "positivo" and f["fuente"] == fuente]
        leg = [f for f in pos if any(m for m in f["marcas"])]
        rut = [f for f in leg if [m for m in f["marcas"] if m][0] == fuente]
        tasa = len(leg) / len(pos) if pos else 0
        lineas.append(f"- {fuente}: marca legible {len(leg)}/{len(pos)} ({tasa:.0%}) -> "
                      f"{'PASA' if tasa >= 5 / 6 else 'NO PASA'} (piso 5/6); ruteo ok {len(rut)}/{len(leg)}")
    neg = [f for f in fv if f["tipo"] == "negativo"]
    esp = [f for f in neg if f["marcas"]]
    tasa = len(esp) / len(neg) if neg else 0
    lineas.append(f"- espurias: {len(esp)}/{len(neg)} ({tasa:.0%}) -> {'PASA' if tasa <= 1 / 6 else 'NO PASA'} (techo 1/6)")
    if fv:
        lineas.append(f"- latencia mediana {statistics.median(f['ms'] for f in fv):.0f} ms")
    lineas.append("")
resumen = "\n".join(lineas)
SALIDA.with_suffix(".md").write_text(resumen, encoding="utf-8")
print(resumen, flush=True)
