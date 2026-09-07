#!/usr/bin/env python3
"""
experimentos/consulta_abismo.py -- el porton de la rebanada 1a del abismo
(spec 2026-09-07, seccion 12).

La apuesta: que el 7b local, con el contrato y el indice puestos, sepa emitir
la marca ⟦abismo:fuente pregunta⟧ cuando le falta contexto -- y abstenerse
cuando no. Antes de cablear el filtro al chat vivo (plan 1b), esto lo mide.

QUE MIDE, sobre N corridas a temperatura 0 (el modelo no es determinista):
  1. MARCA CUANDO DEBE: en los positivos (la respuesta correcta EXIGE
     consultar), tasa de corridas con marca legible. Piso: >= 5/6 por fuente.
  2. ABSTENERSE CUANDO NO DEBE: en los negativos, tasa de corridas con alguna
     marca (espurias). Techo: <= 1/6.
  3. RUTEO: entre las marcas legibles de los positivos, cuantas eligen la
     fuente esperada. Piso: >= 90%.
Tambien reporta latencia y marcas ilegibles (emitio pero mal formada).

Los umbrales son los del spec; si al armar items nuevos hay razon para
moverlos, el cambio queda escrito ACA con su razon.

No decide nada solo: imprime los numeros y los lee Pedro (plan 1b arranca
solo despues de esa lectura).

CALIPSO_HOME va a un temporal ANTES de importar nada del paquete.
"""
import json
import os
import pathlib
import statistics
import sys
import tempfile
import time

os.environ["CALIPSO_HOME"] = tempfile.mkdtemp(prefix="abismo-exp-")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import dispatch  # noqa: E402
from calipso.abismo import contrato, marca  # noqa: E402

N = int(os.environ.get("ABISMO_N", "6"))
NUM_CTX = 4096

# El system del banco: representativo del turno real -- identidad minima +
# el contrato REAL (la misma funcion que el 1b va a cablear) con nombres de
# proyectos plausibles.
PROYECTOS = ("calipso", "atlas", "calipso-lector")
SISTEMA = "\n".join([
    "Sos Calipso, el asistente personal de Pedro. Respondele en su idioma,",
    "directo y natural.",
    contrato.bloque_contrato(PROYECTOS),
])

# --- EL BANCO. Hecho a mano. -------------------------------------------------
# positivo: la respuesta correcta EXIGE consultar (fuente_esperada dice cual).
# negativo: consultar seria ruido (charla, conocimiento general, lo que ya
# esta en el mensaje). Adversariales incluidos: mensajes que MENCIONAN
# recuerdos o proyectos sin necesitar la consulta.
BANCO = [
    # -- positivos: memoria
    {"id": "mem-libro", "tipo": "positivo", "fuente": "memoria",
     "mensaje": "che, como se llamaba esa novela que te conte que me habia encantado?"},
    {"id": "mem-rutina", "tipo": "positivo", "fuente": "memoria",
     "mensaje": "que era lo que hacia yo los domingos a la manana?"},
    {"id": "mem-medico", "tipo": "positivo", "fuente": "memoria",
     "mensaje": "cuando fue la ultima vez que cambie de rutina de ejercicio?"},
    {"id": "mem-gustos", "tipo": "positivo", "fuente": "memoria",
     "mensaje": "armame un regalo para mi hermana, acordate de lo que te dije de ella"},
    {"id": "mem-fecha", "tipo": "positivo", "fuente": "memoria",
     "mensaje": "en que mes me mude de casa? lo tenes en la cronologia"},
    {"id": "mem-pref", "tipo": "positivo", "fuente": "memoria",
     "mensaje": "que estilo de musica te dije que no soporto?"},
    # -- positivos: chats
    {"id": "cha-agosto", "tipo": "positivo", "fuente": "chats",
     "mensaje": "que estuvimos hablando en agosto sobre el lector?"},
    {"id": "cha-receta", "tipo": "positivo", "fuente": "chats",
     "mensaje": "buscame la receta que te pase hace unas semanas en otra conversacion"},
    {"id": "cha-decision", "tipo": "positivo", "fuente": "chats",
     "mensaje": "en que quedamos la otra vez que discutimos lo del presupuesto?"},
    {"id": "cha-link", "tipo": "positivo", "fuente": "chats",
     "mensaje": "pasame de nuevo el link que te mande en un chat viejo sobre bazzite"},
    {"id": "cha-nombre", "tipo": "positivo", "fuente": "chats",
     "mensaje": "como se llamaba el bar que anotamos en una charla del mes pasado?"},
    {"id": "cha-idea", "tipo": "positivo", "fuente": "chats",
     "mensaje": "retoma la idea que dejamos a medias ayer en la otra conversacion"},
    # -- positivos: proyecto
    {"id": "pro-estado", "tipo": "positivo", "fuente": "proyecto",
     "mensaje": "como viene el repo de atlas? en que rama esta?"},
    {"id": "pro-detalle", "tipo": "positivo", "fuente": "proyecto",
     "mensaje": "dame el detalle del proyecto calipso-lector"},
    {"id": "pro-commit", "tipo": "positivo", "fuente": "proyecto",
     "mensaje": "cual fue el ultimo commit de calipso?"},
    {"id": "pro-brief", "tipo": "positivo", "fuente": "proyecto",
     "mensaje": "que hay adentro del repo atlas? no me acuerdo de que iba"},
    {"id": "pro-rama", "tipo": "positivo", "fuente": "proyecto",
     "mensaje": "revisa si el proyecto calipso tiene cambios sin commitear"},
    {"id": "pro-cual", "tipo": "positivo", "fuente": "proyecto",
     "mensaje": "de mis proyectos, cual toque mas recientemente? fijate en el catastro"},
    # -- negativos
    {"id": "neg-charla", "tipo": "negativo",
     "mensaje": "buen dia! como va todo?"},
    {"id": "neg-general", "tipo": "negativo",
     "mensaje": "explicame en dos lineas que es un websocket"},
    {"id": "neg-inline", "tipo": "negativo",
     "mensaje": "mi hermana cumple el 12 de octubre, anotalo"},
    {"id": "neg-codigo", "tipo": "negativo",
     "mensaje": "escribime un one-liner de python que invierta un string"},
    {"id": "neg-opinion", "tipo": "negativo",
     "mensaje": "que te parece mejor para nombres de funciones, espanol o ingles?"},
    {"id": "neg-menciona-recuerdo", "tipo": "negativo",
     "mensaje": "te acabo de contar que me gusta el cafe sin azucar, repetimelo"},
    {"id": "neg-menciona-proyecto", "tipo": "negativo",
     "mensaje": "calipso es el nombre de mi asistente, te gusta como suena?"},
    {"id": "neg-matematica", "tipo": "negativo",
     "mensaje": "cuanto es 15% de 84000?"},
    {"id": "neg-traduccion", "tipo": "negativo",
     "mensaje": "como se dice 'estanteria' en ingles?"},
    {"id": "neg-ahora", "tipo": "negativo",
     "mensaje": "resumime este parrafo: los patos migran en otono hacia el sur."},
]

# --- cache resumible (el molde de juez_privacidad.py:50-77) ------------------
CACHE_PATH = os.environ.get("ABISMO_CACHE", "")
_cache: dict = {}


def _cache_load():
    if CACHE_PATH and os.path.exists(CACHE_PATH):
        for linea in open(CACHE_PATH, encoding="utf-8"):
            try:
                r = json.loads(linea)
                _cache[(r["item"], r["corrida"])] = (r["salida"], r["ms"])
            except (json.JSONDecodeError, KeyError):
                pass
    if _cache:
        print(f"cache: {len(_cache)} respuestas guardadas, se retoman.", flush=True)


def _cache_put(item_id, corrida, salida, ms):
    _cache[(item_id, corrida)] = (salida, ms)
    if CACHE_PATH:
        with open(CACHE_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps({"item": item_id, "corrida": corrida,
                                "salida": salida, "ms": ms}) + "\n")


def preguntar(mensaje: str) -> tuple[str, int]:
    """Una llamada al 7b con el system del banco. Devuelve (texto, ms)."""
    payload = {
        "model": dispatch.CONFIG["local"]["model"],
        "system": SISTEMA,
        "prompt": mensaje,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": NUM_CTX},
    }
    t0 = time.monotonic()
    data = dispatch._http_post_json(dispatch.CONFIG["local"]["base_url"], payload)
    ms = int((time.monotonic() - t0) * 1000)
    return data.get("response", ""), ms


def main():
    _cache_load()
    limite = int(os.environ.get("ABISMO_LIMIT", "0")) or len(BANCO)
    banco = BANCO[:limite]
    modelo = dispatch.CONFIG["local"]["model"]
    print(f"\n{'=' * 72}\nPORTON DEL ABISMO -- {modelo} (temp 0, {N} corridas x "
          f"{len(banco)} items)\n{'=' * 72}", flush=True)

    fuentes_pos = sorted({i["fuente"] for i in banco if i["tipo"] == "positivo"})
    stats = {f: {"corridas": 0, "legibles": 0, "ruteo_ok": 0, "ilegibles": 0}
             for f in fuentes_pos}
    neg_corridas = neg_con_marca = 0
    latencias = []

    for item in banco:
        for corrida in range(N):
            key = (item["id"], corrida)
            if key in _cache:
                salida, ms = _cache[key]
            else:
                salida, ms = preguntar(item["mensaje"])
                _cache_put(item["id"], corrida, salida, ms)
            latencias.append(ms)
            marcas = marca.encontrar(salida)
            legibles = [m for m in marcas if m is not None]
            if item["tipo"] == "negativo":
                neg_corridas += 1
                if marcas:
                    neg_con_marca += 1
                continue
            s = stats[item["fuente"]]
            s["corridas"] += 1
            s["ilegibles"] += sum(1 for m in marcas if m is None)
            if legibles:
                s["legibles"] += 1
                if legibles[0].fuente == item["fuente"]:
                    s["ruteo_ok"] += 1
        print(f"  {item['id']}: listo", flush=True)

    lineas = ["# Porton del abismo -- resultados", "",
              f"Modelo: {modelo}. N={N}, temp 0, num_ctx={NUM_CTX}.",
              f"Items: {len(banco)} ({sum(1 for i in banco if i['tipo'] == 'positivo')} "
              f"positivos, {neg_corridas // N if N else 0} negativos).", ""]
    total_leg = total_ruteo = 0
    for f in fuentes_pos:
        s = stats[f]
        tasa = s["legibles"] / s["corridas"] if s["corridas"] else 0
        veredicto = "PASA" if tasa >= 5 / 6 else "NO PASA"
        lineas.append(f"- {f}: marca legible {s['legibles']}/{s['corridas']} "
                      f"({tasa:.0%}) -> {veredicto} (piso 5/6). "
                      f"Ilegibles: {s['ilegibles']}.")
        total_leg += s["legibles"]
        total_ruteo += s["ruteo_ok"]
    esp = neg_con_marca / neg_corridas if neg_corridas else 0
    lineas.append(f"- espurias en negativos: {neg_con_marca}/{neg_corridas} "
                  f"({esp:.0%}) -> {'PASA' if esp <= 1 / 6 else 'NO PASA'} (techo 1/6).")
    rut = total_ruteo / total_leg if total_leg else 0
    lineas.append(f"- ruteo correcto: {total_ruteo}/{total_leg} ({rut:.0%}) -> "
                  f"{'PASA' if rut >= 0.9 else 'NO PASA'} (piso 90%).")
    lineas.append(f"- latencia por llamada: mediana "
                  f"{statistics.median(latencias):.0f} ms, "
                  f"max {max(latencias)} ms.")
    reporte = "\n".join(lineas) + "\n"
    print("\n" + reporte, flush=True)
    out = pathlib.Path(__file__).parent / "consulta_abismo_resultados.md"
    out.write_text(reporte, encoding="utf-8")
    print(f"reporte escrito en {out}", flush=True)


if __name__ == "__main__":
    main()
